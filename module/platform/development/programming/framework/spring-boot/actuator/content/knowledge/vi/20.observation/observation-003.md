# Tạo Observation cho một thao tác nghiệp vụ

## 1. Quan sát một việc có ý nghĩa đối với nghiệp vụ

Observation là một lần quan sát có ranh giới bắt đầu và kết thúc, kèm tên hoạt động, dữ liệu mô tả và lỗi nếu có. Khi gắn Observation vào một thao tác nghiệp vụ, ta muốn biết thao tác đó đã được gọi bao nhiêu lần, mất bao lâu, thất bại theo cách nào và có thể nằm ở đâu trong dấu vết thực thi.

Ví dụ: dịch vụ kho nhận yêu cầu giữ hai sản phẩm cho một đơn hàng. Một request HTTP có thể còn làm nhiều việc khác, nên số đo của toàn request chưa trả lời riêng bước giữ hàng. Một observation tên `stock.reserve` đặt tại tầng dịch vụ biểu diễn đúng câu hỏi: **một lần thử giữ hàng hợp lệ đã diễn ra như thế nào?**

Mã đặt điểm quan sát phát ra vòng đời; các bộ xử lý (`ObservationHandler`) quyết định tạo phép đo, span hoặc xử lý bổ sung. Vì thế mã nghiệp vụ không cần tự biết địa chỉ máy chủ giám sát. Trong Spring Boot, có thể tiêm `ObservationRegistry` để tạo observation riêng. [Nguồn: Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Bài này dùng API trực tiếp, không yêu cầu annotation hay AOP để quan sát phương thức. Ví dụ chạy với Spring Boot 3.3.0 và Java 17 trở lên, khởi động dưới dạng ứng dụng không có máy chủ web.

## 2. Chọn ranh giới trước khi viết mã

### 2.1. Bắt đầu ở đâu, kết thúc ở đâu?

Trước khi tạo observation, cần xác định:

- Một lần ghi đại diện cho một lần gọi hợp lệ, một lần thử lại, hay toàn bộ yêu cầu nghiệp vụ?
- Kiểm tra đầu vào có nằm trong khoảng quan sát không?
- Trường hợp nào được coi là lỗi, trường hợp nào là kết quả từ chối bình thường?
- Những chiều phân loại nào có ích để tổng hợp số liệu?

Trong ví dụ của bài:

```text
reserve(sku, quantity, channel)
    → kiểm tra đầu vào
    → bắt đầu observation stock.reserve
    → đọc số lượng hiện có
    → đủ hàng: trừ tồn và trả kết quả
      thiếu hàng: ném OutOfStockException
    → kết thúc observation trong cả hai trường hợp
```

Đầu vào có số lượng bằng 0 bị từ chối trước observation. Yêu cầu có đầu vào hợp lệ nhưng thiếu hàng nằm bên trong observation. Đây là lựa chọn định nghĩa số đo của ví dụ, không phải một quy tắc bắt buộc cho mọi hệ thống.

Nếu muốn thống kê cả yêu cầu sai định dạng, hãy đưa phần kiểm tra tương ứng vào ranh giới hoặc tạo số đo có ý nghĩa riêng. Không đổi vị trí kiểm tra một cách tùy tiện rồi giữ nguyên cách giải thích số liệu cũ.

### 2.2. Đặt tại tầng chứa thao tác cần đo

Quan sát trong dịch vụ giúp cùng một thao tác được ghi nhận khi được gọi từ HTTP, tác vụ nền hoặc chương trình dòng lệnh. Một lớp bao ngoài có thể đo toàn quy trình; một observation con có thể đo bước cụ thể. Hai ranh giới đó cần có tên và ý nghĩa khác nhau.

Đừng bọc một observation mới quanh mọi phương thức nhỏ chỉ để tăng lượng dữ liệu. Bắt đầu từ thao tác mà người vận hành thực sự cần phân biệt: giữ hàng, tính giá, xác nhận thanh toán hoặc tạo chứng từ.

## 3. Chuẩn bị registry và dữ liệu mô tả

### 3.1. Dùng ObservationRegistry do Spring quản lý

Trong ứng dụng Boot có Actuator, dịch vụ nhận `ObservationRegistry` qua hàm khởi tạo. Không cần tạo registry mới cho từng lượt gọi. Boot tạo bean registry khi cần và cấu hình các handler cùng các thành phần quan sát thông qua bộ xử lý bean. [Nguồn: ObservationAutoConfiguration 3.3.0](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/observation/ObservationAutoConfiguration.java).

Điểm phân biệt:

| Đối tượng | Cách sử dụng |
| --- | --- |
| `ObservationRegistry` | Dùng chung theo cấu hình ứng dụng, được tiêm vào dịch vụ |
| `Observation` | Tạo mới cho từng lần thực hiện thao tác |
| `Observation.Context` | Dữ liệu của một lần quan sát, được các handler sử dụng |
| `MeterRegistry` | Nơi quản lý các phép đo; không thay thế ObservationRegistry |

Nếu tự gọi `ObservationRegistry.create()` trong dịch vụ, registry riêng đó không tự nhận toàn bộ cấu hình đã có trên bean của Boot. Mã có thể vẫn chạy nhưng không có handler tạo dữ liệu mong muốn.

Không giữ một đối tượng Observation đang hoạt động trong trường của singleton rồi dùng lại cho nhiều yêu cầu. Tên và quy ước có thể dùng chung; khoảng đời, lỗi và dữ liệu của từng lần gọi phải độc lập.

### 3.2. Tên ổn định, nhãn có giới hạn

Thiết kế cho thao tác giữ hàng:

| Thành phần | Giá trị trong ví dụ | Mục đích |
| --- | --- | --- |
| Tên observation | `stock.reserve` | Nhận diện cùng một loại thao tác qua nhiều lượt gọi |
| Tên theo ngữ cảnh | `reserve-stock` | Tên dễ đọc cho các handler sử dụng tên ngữ cảnh, chẳng hạn tracing |
| Nhãn có độ đa dạng thấp | `channel=web` hoặc `channel=mobile` | Tổng hợp theo kênh gọi có tập giá trị nhỏ |
| Nhãn có độ đa dạng cao | `sku=SKU-A` | Dữ liệu tra cứu cụ thể, không làm nhãn metrics mặc định |

Độ đa dạng giá trị (cardinality) là số giá trị hoặc tổ hợp nhãn có thể xuất hiện. Dùng enum cho `channel` giúp giới hạn tập giá trị ngay trong API ví dụ. Không dùng chuỗi tùy ý do người gọi gửi vào làm nhãn low cardinality mà chưa chuẩn hóa.

Không đặt tên thành `stock.reserve.SKU-A` rồi tạo một tên mới cho mỗi mã sản phẩm. Cũng không thêm mã yêu cầu hoặc mã trace vào nhãn metrics để tìm một lần gọi cụ thể.

Với luồng xử lý chuẩn, nhãn low cardinality có thể đi vào cả metrics và trace; nhãn high cardinality không được dùng làm nhãn metrics mặc định. High cardinality vẫn phải được chọn lọc, không phải chỗ ghi toàn bộ yêu cầu hoặc thông tin bí mật. [Nguồn: Spring Boot — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

## 4. Dùng observe để quản lý vòng đời và trả kết quả

Phần quan trọng trong dịch vụ của ví dụ là tạo observation ở trạng thái chưa bắt đầu, gắn dữ liệu đã biết rồi gọi `observe(...)`. Với tác vụ có kết quả, overload nhận `Supplier<T>` trả lại kết quả của tác vụ.

`observe(...)` quản lý bắt đầu, mở phạm vi ngữ cảnh (scope), chạy tác vụ, ghi lỗi khi tác vụ ném lỗi, đóng scope và dừng observation. Nhờ đó nhánh thành công và nhánh ngoại lệ đều đi qua phần kết thúc. [Nguồn: Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html).

Từ góc nhìn phương thức dịch vụ:

- Tác vụ trả về `Reservation` thì phương thức tiếp tục trả về kết quả đó.
- Tác vụ ném `OutOfStockException` thì ngoại lệ tiếp tục ra ngoài; Observation không đổi nó thành một giá trị thành công.
- Việc ghi nhận lỗi không tự hoàn tác thay đổi dữ liệu và không thay cơ chế giao dịch.

Nên gắn các nhãn đã biết trước khi bắt đầu. Một số handler tạo phép đo ngay lúc bắt đầu, nên thêm nhãn muộn không bảo đảm nhãn đó xuất hiện trên mọi phép đo đang hoạt động. [Nguồn: DefaultMeterObservationHandler 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/observation/DefaultMeterObservationHandler.java).

## 5. Chương trình Spring Boot hoàn chỉnh

### 5.1. Những gì chương trình chứng minh

Kho ban đầu có 3 sản phẩm `SKU-A`. Chương trình thực hiện bốn lời gọi:

1. Kênh web giữ 2 sản phẩm: thành công, còn 1.
2. Kênh web muốn giữ tiếp 2 sản phẩm: thiếu hàng, ném lỗi.
3. Kênh web gửi số lượng 0: đầu vào không hợp lệ, bị từ chối trước observation.
4. Kênh mobile giữ 1 sản phẩm còn lại: thành công, còn 0.

Do ranh giới đã chọn, có **ba lần quan sát**, gồm hai thành công và một lỗi nghiệp vụ. Một handler nhỏ đếm các sự kiện vòng đời để kiểm chứng; handler metrics do Boot cấu hình vẫn xử lý số đo riêng.

Ví dụ dùng `HashMap` trong một luồng để giữ bài tập độc lập. Nó không mô phỏng giao dịch cơ sở dữ liệu hay giải quyết tranh chấp tồn kho giữa nhiều yêu cầu. Không có máy chủ HTTP, API giả hoặc kết nối đến dịch vụ giám sát bên ngoài.

### 5.2. Tệp pom.xml

Cần JDK 17 trở lên và Maven. Tạo thư mục thực hành riêng, đặt `pom.xml` và `StockObservationApplication.java` cạnh nhau. Maven được dùng để tải dependency; mã được biên dịch bằng lệnh `javac` bên dưới.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.0</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>stock-observation-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
  </dependencies>
</project>
```

Parent quản lý bộ phiên bản Spring Boot và Micrometer tương thích. Không cần thêm một registry bên ngoài để kiểm tra số đo trong bộ nhớ. Lần tải dependency đầu cần kết nối mạng.

### 5.3. Tệp StockObservationApplication.java

```java
package example.stock;

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableAutoConfiguration
public class StockObservationApplication {
    static final String OBSERVATION_NAME = "stock.reserve";

    enum Channel { WEB, MOBILE }

    record Reservation(String sku, int quantity, int remaining) {}

    static final class OutOfStockException extends RuntimeException {
        OutOfStockException() {
            super("Not enough stock");
        }
    }

    static final class StockService {
        private final ObservationRegistry registry;
        private final Map<String, Integer> stock = new HashMap<>(Map.of("SKU-A", 3));

        StockService(ObservationRegistry registry) {
            this.registry = registry;
        }

        Reservation reserve(String sku, int quantity, Channel channel) {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(channel, "channel");
            if (sku.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("sku must be nonblank and quantity must be positive");
            }
            return Observation.createNotStarted(OBSERVATION_NAME, registry)
                .contextualName("reserve-stock")
                .lowCardinalityKeyValue("channel", channel.name().toLowerCase(Locale.ROOT))
                .highCardinalityKeyValue("sku", sku)
                .observe(() -> reserveInternal(sku, quantity));
        }

        private Reservation reserveInternal(String sku, int quantity) {
            int available = stock.getOrDefault(sku, 0);
            if (available < quantity) {
                throw new OutOfStockException();
            }
            int remaining = available - quantity;
            stock.put(sku, remaining);
            return new Reservation(sku, quantity, remaining);
        }
    }

    static final class LifecycleRecorder implements ObservationHandler<Observation.Context> {
        int starts;
        int errors;
        int stops;
        int scopeOpens;
        int scopeCloses;

        @Override
        public boolean supportsContext(Observation.Context context) {
            return OBSERVATION_NAME.equals(context.getName());
        }

        @Override
        public void onStart(Observation.Context context) {
            starts++;
        }

        @Override
        public void onError(Observation.Context context) {
            errors++;
        }

        @Override
        public void onStop(Observation.Context context) {
            stops++;
        }

        @Override
        public void onScopeOpened(Observation.Context context) {
            scopeOpens++;
        }

        @Override
        public void onScopeClosed(Observation.Context context) {
            scopeCloses++;
        }
    }

    @Bean
    StockService stockService(ObservationRegistry registry) {
        return new StockService(registry);
    }

    @Bean
    LifecycleRecorder lifecycleRecorder() {
        return new LifecycleRecorder();
    }

    private static long count(MeterRegistry meters, String channel, String error) {
        return meters.get(OBSERVATION_NAME)
            .tags("channel", channel, "error", error).timer().count();
    }

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(StockObservationApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);
        application.setDefaultProperties(Map.of(
            "logging.level.root", "OFF",
            "management.metrics.use-global-registry", "false"));

        try (ConfigurableApplicationContext context = application.run(args)) {
            StockService stock = context.getBean(StockService.class);
            MeterRegistry meters = context.getBean(MeterRegistry.class);
            ObservationRegistry observations = context.getBean(ObservationRegistry.class);
            LifecycleRecorder lifecycle = context.getBean(LifecycleRecorder.class);

            Reservation first = stock.reserve("SKU-A", 2, Channel.WEB);
            System.out.println("first.remaining=" + first.remaining());

            try {
                stock.reserve("SKU-A", 2, Channel.WEB);
            } catch (OutOfStockException error) {
                System.out.println("rejected=" + error.getClass().getSimpleName());
            }

            try {
                stock.reserve("SKU-A", 0, Channel.WEB);
            } catch (IllegalArgumentException error) {
                System.out.println("invalid=" + error.getClass().getSimpleName());
            }

            Reservation last = stock.reserve("SKU-A", 1, Channel.MOBILE);
            System.out.println("last.remaining=" + last.remaining());
            System.out.println("web.success=" + count(meters, "web", "none"));
            System.out.println("web.failure=" + count(meters, "web", "OutOfStockException"));
            System.out.println("mobile.success=" + count(meters, "mobile", "none"));
            long total = meters.find(OBSERVATION_NAME).timers().stream()
                .mapToLong(Timer::count).sum();
            System.out.println("observed.total=" + total);
            boolean skuIsMetricTag = meters.find(OBSERVATION_NAME).timers().stream()
                .anyMatch(timer -> timer.getId().getTag("sku") != null);
            System.out.println("sku.isMetricTag=" + skuIsMetricTag);
            System.out.println("lifecycle=" + lifecycle.starts + "/"
                + lifecycle.errors + "/" + lifecycle.stops);
            System.out.println("scopes=" + lifecycle.scopeOpens + "/" + lifecycle.scopeCloses);
            System.out.println("current.cleared=" + (observations.getCurrentObservation() == null));
        }
    }
}
```

### 5.4. Biên dịch và chạy

Trong PowerShell, tại thư mục chứa hai tệp:

```powershell
mvn dependency:copy-dependencies -DincludeScope=runtime
New-Item -ItemType Directory -Force -Path target/classes | Out-Null
javac --release 17 -encoding UTF-8 -cp "target/dependency/*" -d target/classes StockObservationApplication.java
java -cp "target/classes;target/dependency/*" example.stock.StockObservationApplication
```

Tệp có khai báo package `example.stock`, nên tên đầy đủ khi chạy là `example.stock.StockObservationApplication`. Với cách gọi `javac` trực tiếp này, `-d` tạo thư mục package trong `target/classes`. Trong dự án Maven thông thường, chuyển tệp vào đúng cây `src/main/java/example/stock/`.

Trên Linux/macOS, tạo thư mục bằng `mkdir -p target/classes` và dùng dấu `:` thay `;` giữa hai mục classpath của lệnh `java`.

Chương trình tắt banner và log khởi động để phần stdout thực hành rõ ràng; đây không phải yêu cầu tắt log của ứng dụng thực tế. Chạy ví dụ nguyên trạng, không thêm cấu hình tắt quan sát hoặc registry, sẽ có stdout:

```text
first.remaining=1
rejected=OutOfStockException
invalid=IllegalArgumentException
last.remaining=0
web.success=1
web.failure=1
mobile.success=1
observed.total=3
sku.isMetricTag=false
lifecycle=3/1/3
scopes=3/3
current.cleared=true
```

### 5.5. Đối chiếu từng bằng chứng

| Output | Điều được chứng minh |
| --- | --- |
| `first.remaining=1` | Nhánh thành công trả kết quả nghiệp vụ và cập nhật tồn kho |
| `rejected=OutOfStockException` | Ngoại lệ từ tác vụ vẫn được truyền ra cho mã gọi xử lý |
| `invalid=IllegalArgumentException` | Đầu vào sai bị chặn trước ranh giới quan sát đã chọn |
| `last.remaining=0` | Nhánh thiếu hàng không trừ tồn; lượt cuối vẫn giữ được sản phẩm còn lại |
| `web.success=1` | Một timer có nhãn `channel=web`, `error=none` đã ghi một lượt |
| `web.failure=1` | Timer của nhánh web lỗi ghi một lượt với tên loại ngoại lệ |
| `mobile.success=1` | Cùng tên hoạt động nhưng nhãn kênh khác tạo nhóm tổng hợp riêng |
| `observed.total=3` | Tổng số lần ghi timer bằng số lượt thực sự vào observation |
| `sku.isMetricTag=false` | Nhãn high cardinality không trở thành nhãn timer mặc định |
| `lifecycle=3/1/3` | Handler nhận 3 lần bắt đầu, 1 lần báo lỗi và 3 lần kết thúc |
| `scopes=3/3` | Cả ba scope được mở và đóng |
| `current.cleared=true` | Sau các lượt gọi, không còn observation hiện tại trong luồng của ví dụ |

Timer mặc định của Micrometer 1.13 thêm nhãn `error=none` khi không có lỗi, hoặc tên đơn giản của lớp ngoại lệ khi có lỗi. Đây là lý do mã kiểm tra tìm `OutOfStockException`, không tìm toàn bộ nội dung thông báo ngoại lệ. [Nguồn: DefaultMeterObservationHandler](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/observation/DefaultMeterObservationHandler.java).

Chương trình không in thời gian thực thi cố định vì thời gian thật phụ thuộc lần chạy. `Timer.count()` là số lần ghi phép đo thời gian, không yêu cầu tạo thêm một Counter độc lập để có số lượt gọi.

`sku.isMetricTag=false` chỉ kiểm tra nhãn metrics. Ví dụ không cài tracer/bộ xuất trace nên không dùng kết quả đó để tuyên bố đã có span chứa SKU tại một máy chủ khác.

## 6. Vì sao cấu hình ví dụ hoạt động?

`@Configuration` khai báo các bean của bài tập; `@EnableAutoConfiguration` bật cơ chế cấu hình tự động của Boot. `StockService` nhận đúng `ObservationRegistry` của context qua phương thức `@Bean`. Bên trong dịch vụ, mỗi lần gọi hợp lệ tạo một observation mới.

`LifecycleRecorder` cũng là một bean handler. Boot tự đăng ký các bean `ObservationHandler` vào registry; không có dòng đăng ký thủ công trong dịch vụ. Handler chỉ nhận context có tên `stock.reserve` để các quan sát khác của ứng dụng không làm sai số đếm bài tập. [Nguồn: Spring Boot — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Trong cấu hình mặc định của bài, Simple registry là nơi giữ metrics trong bộ nhớ khi không có registry khác. Vì vậy có thể lấy timer trực tiếp qua bean `MeterRegistry` mà không mở endpoint HTTP hay chạy Prometheus. [Nguồn: Spring Boot — Simple](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#supported-monitoring-systems.simple).

Thuộc tính `management.metrics.use-global-registry=false` giữ ví dụ sử dụng đường ghi qua các bean của context mà không cần liên kết với registry tĩnh toàn cục. Nó không tắt các timer đang quan sát.

Trong ứng dụng thật, các lớp lồng nhau có thể được tách thành tệp riêng. Dịch vụ có thể được đăng ký bằng `@Service` với hàm khởi tạo nhận `ObservationRegistry`; không tạo thêm context Boot tại mỗi lời gọi. Handler đếm vòng đời là công cụ giải thích của bài, không phải phần bắt buộc của mọi dịch vụ.

## 7. Khi cần tự điều khiển vòng đời

Với thao tác đồng bộ thông thường, dùng `observe(...)` giúp giảm việc quản lý thủ công. Nếu có lý do cần nắm trực tiếp đối tượng observation, phải quản lý đủ cả scope lẫn khoảng đời.

Đoạn dưới là **phương án thay thế** cho phần `return Observation...observe(...)` trong phương thức `reserve` của lớp ví dụ; giữ nguyên kiểm tra đầu vào ở phía trước và không chạy đồng thời hai cách quanh cùng một thao tác:

```java
Observation observation = Observation.createNotStarted(OBSERVATION_NAME, registry)
    .contextualName("reserve-stock")
    .lowCardinalityKeyValue("channel", channel.name().toLowerCase(Locale.ROOT))
    .highCardinalityKeyValue("sku", sku)
    .start();
try (Observation.Scope scope = observation.openScope()) {
    return reserveInternal(sku, quantity);
} catch (RuntimeException | Error error) {
    observation.error(error);
    throw error;
} finally {
    observation.stop();
}
```

`start()` không thay cho `openScope()`. Đóng scope không thay cho `stop()`. Trong đoạn thay thế, `try` bảo đảm khôi phục ngữ cảnh, còn `finally` bảo đảm kết thúc lần quan sát; nhánh lỗi vẫn báo lỗi và ném lại ngoại lệ.

`observation.error(error)` là thao tác phát tín hiệu lỗi cho handler, không tự ném ngoại lệ. API cũng có sự kiện (`Observation.Event`) để mô tả những mốc xảy ra trong hoạt động; chỉ thêm các mốc có ích, không biến chúng thành bản sao toàn bộ log. [Nguồn: Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html).

## 8. Diễn giải đúng kết quả nghiệp vụ

### 8.1. Trả về bình thường chưa chắc là được chấp nhận

Trong bài tập, thiếu hàng được mô hình hóa bằng ngoại lệ nên timer có nhãn lỗi. Một hệ thống khác có thể trả `ReservationResult.REJECTED` như một kết quả bình thường. Nếu lambda trả về bình thường, Observation không tự biết enum hoặc mã trạng thái đó có ý nghĩa thất bại.

Khi cần phân biệt chấp nhận/từ chối mà không coi từ chối là lỗi kỹ thuật, có thể thiết kế nhãn `outcome` với tập giá trị nhỏ như `accepted`, `rejected`. Việc dùng ngoại lệ hay kết quả trả về phải theo hợp đồng nghiệp vụ; đừng thay đổi hợp đồng chỉ để tiện xem metrics.

Không đưa thông báo lỗi tùy ý vào nhãn low cardinality. Hai thông báo chứa mã đơn hàng khác nhau có thể tạo hàng loạt giá trị nhãn mới dù cùng một loại lỗi.

### 8.2. Không che mất ngoại lệ trước điểm quan sát

Nếu mã trong lambda bắt `OutOfStockException` rồi trả một kết quả thay thế, `observe(...)` không còn thấy ngoại lệ thoát ra. Nếu vẫn cần phản ánh lỗi trên observation, chủ động báo vào observation hoặc biểu diễn outcome phù hợp.

Cũng không bọc một lỗi thành một lỗi mới chỉ để đổi nhãn giám sát, hoặc trả thành công giả sau khi quan sát. Việc đặt điểm quan sát cần bảo toàn hành vi và hợp đồng của thao tác.

### 8.3. Thử lại, giao dịch và tác vụ bất đồng bộ

Với cơ chế thử lại, quan sát bên ngoài toàn bộ vòng thử biểu diễn một yêu cầu logic; quan sát từng lần thử biểu diễn các lần thực thi. Nếu dùng cả hai, cần tên riêng và biết rõ số đếm nào đang được đọc.

Với giao dịch khai báo của Spring, proxy giao dịch bao quanh lời gọi phương thức. Suy ra, observation chỉ nằm trong thân phương thức có thể kết thúc trước khi proxy hoàn tất commit. Nếu câu hỏi cần tính cả commit và lỗi tại commit, ranh giới phải bao trùm lời gọi qua proxy thích hợp; không mặc định “lambda trả về” đồng nghĩa “giao dịch đã commit”. [Nguồn cơ chế proxy: Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html).

Với tác vụ trả `CompletableFuture`, một `observe(...)` đồng bộ chỉ bao quanh lời gọi trả về future thường mới đo bước tạo/lên lịch. Nó không tự chờ công việc hoàn thành. Chuyển luồng hoặc dùng reactive pipeline còn cần tích hợp truyền ngữ cảnh và vòng đời phù hợp; không giữ một scope mở trên luồng gọi rồi đóng tùy ý ở luồng khác.

## 9. Kiểm tra khi không thấy dữ liệu

| Hiện tượng | Kiểm tra trước |
| --- | --- |
| Mã chạy nhưng không có timer | Có dùng registry bean của Boot, có handler metrics, observation có bị tắt hoặc meter có bị lọc không? |
| Tên hoạt động xuất hiện thành rất nhiều biến thể | Có nối SKU, mã đơn hoặc dữ liệu đầu vào vào tên observation không? |
| Số lượt ghi lớn hơn số lượt nghiệp vụ mong đợi | Có quan sát trùng cùng ranh giới, thêm annotation trên mã đã được quan sát, hoặc đang đếm từng lần thử lại không? |
| Lỗi nghiệp vụ không hiện trên observation | Ngoại lệ có bị bắt bên trong lambda, hoặc nghiệp vụ đang trả trạng thái từ chối bình thường không? |
| Observation hiện tại vẫn còn sau lời gọi | Nếu quản lý thủ công, scope đã được đóng và trạng thái ban đầu đã được khôi phục chưa? |
| Không có trace dù có timer | Đã có tracer/handler/bộ xuất trace thích hợp chưa, trace có được lấy mẫu không? |
| Số đo không xuất hiện qua HTTP | Endpoint là đường đọc riêng; trước hết kiểm tra timer nội bộ có dữ liệu hay không |

Không bọc thêm `@Observed` hoặc thêm handler tạo timer thứ hai chỉ để sửa hiện tượng chưa hiểu rõ. Trước tiên xác minh một lần gọi đã đi vào đúng ranh giới và đúng registry. Các thành phần quan sát có thể được tùy biến bằng convention, predicate hoặc filter khi cần chính sách dùng chung; một thao tác đơn giản chưa bắt buộc phải tạo đầy đủ mọi loại thành phần.

## 10. Bài tập tự kiểm tra

1. Tại sao chương trình gọi `reserve` bốn lần nhưng `observed.total` bằng 3?
2. Nếu chuyển kiểm tra `quantity <= 0` vào bên trong lambda, cần thay đổi cách diễn giải số liệu như thế nào?
3. Nếu còn một sản phẩm nhưng yêu cầu giữ hai, vì sao lần giữ tiếp theo vẫn có thể thành công?
4. Có thể dùng SKU làm nhãn low cardinality chỉ vì hiện tại mới có một sản phẩm thử nghiệm không?
5. Vì sao dịch vụ giữ `ObservationRegistry` trong trường nhưng không giữ một Observation dùng chung?
6. Khi trả kết quả `REJECTED` bình thường, API có tự báo lỗi không?
7. Trong cách thủ công, điều gì quản lý scope và điều gì bảo đảm kết thúc observation?

Đáp án: (1) Đầu vào số lượng 0 bị từ chối trước điểm quan sát. (2) Yêu cầu đó sẽ nằm trong tập lượt quan sát và có lỗi đầu vào; tổng số ghi và định nghĩa mẫu số đều thay đổi. (3) Nhánh thiếu hàng kiểm tra rồi ném ngoại lệ trước khi cập nhật tồn. (4) Không nên suy từ dữ liệu thử nghiệm ra tập giá trị dài hạn; cần thiết kế theo số giá trị thực tế có thể phát sinh. (5) Registry là cấu hình dùng chung, Observation là trạng thái của từng lần gọi. (6) Không; cần phân loại outcome hoặc báo lỗi theo hợp đồng đã chọn. (7) `try` với resource đóng scope; `finally` gọi `stop()`; nhánh bắt lỗi báo lỗi và ném lại.
