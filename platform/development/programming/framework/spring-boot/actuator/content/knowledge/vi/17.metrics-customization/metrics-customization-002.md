# Áp dụng quy tắc đặt tên và hiểu cách registry chuyển đổi tên chỉ số

## 1. Một chỉ số có thể xuất hiện dưới nhiều tên ở các tầng khác nhau

Bạn đăng ký một timer trong Java bằng tên `checkout.payment`, nhưng khi mở dữ liệu Prometheus lại thấy `checkout_payment_seconds_count` và `checkout_payment_seconds_sum`. Trong khi đó, gọi Actuator bằng tên có gạch dưới không tìm được chỉ số.

Đây có thể là hành vi bình thường: **tên dùng để khai báo meter** và **tên chuỗi số liệu được xuất sang hệ thống giám sát** phục vụ hai lớp khác nhau.

Trong bài này:

- **Meter** là bộ đo của Micrometer, chẳng hạn `Counter` hoặc `Timer`.
- **Registry** là nơi đăng ký meter và tổ chức việc xuất số đo.
- **Quy ước đặt tên (naming convention)** chuyển tên sang dạng phù hợp với hệ thống nhận.
- **Nhãn (tag/label)** bổ sung chiều phân loại, gồm khóa và giá trị.
- **Chuỗi thời gian (time series)** là một chuỗi số liệu có tên và tập nhãn cụ thể trong hệ thống giám sát.

Mục tiêu là đặt tên có ý nghĩa ngay trong mã, giữ khả năng dùng nhiều hệ thống giám sát và tìm đúng tên ở đúng nơi khi kiểm tra dữ liệu.

Có thể hình dung đường đi như sau:

```text
Tên và nhãn khai báo trong mã
    → MeterFilter nếu có thay đổi danh tính
    → Meter.Id trong registry
        → Actuator metrics dùng tên meter
        → Quy ước và bộ xuất của từng registry
            → Tên, đơn vị và các chuỗi thống kê ở hệ thống đích
```

Không phải mọi sự thay đổi ở đầu ra đều là một lần đổi tên `Meter.Id`. Ngược lại, nếu có filter thật sự đổi danh tính, tên có hiệu lực trong registry cũng cần được kiểm tra lại.

## 2. Đặt tên gốc theo ý nghĩa của đại lượng

### 2.1. Ưu tiên chữ thường và dấu chấm

Micrometer khuyến nghị dạng các từ viết thường, ngăn cách bằng dấu chấm:

```text
checkout.orders
checkout.payment
inventory.refresh
upload.payload
```

Hãy viết tên theo dạng trung lập này thay vì chép nguyên tên chuỗi Prometheus vào mã. Registry có quy ước riêng để chuyển sang dạng phù hợp khi xuất. [Tài liệu Naming Meters của Micrometer](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html) giải thích lựa chọn chữ thường và dấu chấm để tăng khả năng dùng với nhiều hệ thống.

Một cấu trúc dễ đọc là “miền chức năng → đối tượng hoặc thao tác”. Đây là cách tổ chức của dự án, không phải cú pháp bắt buộc phải có đúng hai hoặc ba phần.

| Tên chưa rõ hoặc khó duy trì | Cách cải thiện | Lý do |
| --- | --- | --- |
| `count` | `checkout.orders` | Biết đang đếm đối tượng gì |
| `paymentTime` | `checkout.payment` với loại Timer | Rõ miền chức năng và thống nhất kiểu tên |
| `checkout.payment.12345` | `checkout.payment` | Mã giao dịch không phải một loại metric mới |
| `checkout.payment.prod` | `checkout.payment` cùng nhãn môi trường | Môi trường là chiều phân loại |
| `checkout.payment.seconds.sum` | `checkout.payment` với Timer | Để registry tạo thống kê và tên đầu ra |
| `calls` dùng chung cho HTTP và cơ sở dữ liệu | Tách `http.calls` và `database.calls` | Tổng của hai loại hoạt động không cùng ý nghĩa |

Loại meter và mô tả phải làm rõ tên. Ví dụ, `checkout.orders` có thể dùng Counter để đếm các đơn theo một sự kiện đã xác định; `checkout.payment` dùng Timer để đo thời lượng một lần xử lý thanh toán. Không dùng cùng tên và cùng nhãn cho những loại meter hoặc đại lượng không tương thích.

Tên nên có đủ ngữ cảnh để khi bỏ bộ lọc nhãn, người đọc vẫn hiểu số đo đang nói về điều gì. Không tạo một metric chung cho cả số lượng, dung lượng và thời gian rồi dùng nhãn để phân biệt ba đại lượng ấy.

### 2.2. Giữ dữ liệu thay đổi ở nhãn, với số giá trị được kiểm soát

Thay vì tạo tên mới theo từng loại phương thức thanh toán:

```text
checkout.payment.creditcard
checkout.payment.banktransfer
```

có thể giữ một tên `checkout.payment` và dùng nhãn `payment.method` với tập giá trị đã thống nhất.

Khóa nhãn cũng nên dùng chữ thường và dấu chấm, chẳng hạn `payment.method` hoặc `order.type`. Giá trị nhãn là dữ liệu phân loại; đừng mặc định registry sẽ biến `CreditCard`, `creditcard` và `credit_card` thành cùng một nhóm.

Đội phát triển nên chuẩn hóa giá trị nghiệp vụ ngay tại điểm tạo nhãn. Ví dụ, thống nhất một tập giá trị hữu hạn cho phương thức thanh toán và một giá trị dự phòng cho trường hợp không xác định.

Không chuyển request ID, email, thời điểm hiện tại hoặc mã giao dịch sang nhãn như một cách “sửa” tên có quá nhiều giá trị. Mỗi tổ hợp nhãn khác nhau vẫn có thể tạo chuỗi số liệu mới. Quy tắc của Prometheus cũng nhấn mạnh rằng các chiều phân loại phải có ý nghĩa và cần tránh tập giá trị không giới hạn. [Metric and label naming của Prometheus](https://prometheus.io/docs/practices/naming/).

### 2.3. Đơn vị phải nhất quán, không suy ra chỉ từ chuỗi tên

Với Timer, đưa thời gian vào bằng `Duration` hoặc API có đơn vị rõ ràng:

```java
payment.record(Duration.ofMillis(120));
payment.record(Duration.ofMillis(180));
```

Đoạn này minh họa với một timer `payment` đã được đăng ký. Registry biết đây là thời lượng và chuyển sang đơn vị cơ sở của hệ thống đích khi xuất.

Không đổi tên timer thành có hậu tố `millis` rồi giả định dữ liệu xuất chắc chắn giữ đơn vị mili giây. Tên không thay thế cơ chế chuyển đơn vị của Timer. Cũng không trộn số đo byte với số đo số phần tử trong cùng một metric.

Micrometer cho phép đọc lại thời lượng bằng đơn vị được chỉ định, ví dụ `totalTime(TimeUnit.MILLISECONDS)`. Đầu ra Prometheus của cùng timer có thể biểu diễn thời lượng theo giây. [Tài liệu Timers](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html) mô tả vai trò của đơn vị trong API và khi xuất số đo.

## 3. Registry chuyển đổi những gì?

### 3.1. Chuyển kiểu tên và xử lý ký tự không phù hợp

Từ tên `checkout.payment`, một quy ước có thể tạo:

| Quy ước minh họa | Kết quả đổi kiểu tên |
| --- | --- |
| Dạng dấu chấm | `checkout.payment` |
| Dạng gạch dưới | `checkout_payment` |
| Dạng camel case | `checkoutPayment` |

Đây mới là ví dụ về **đổi kiểu tên**. Tên chuỗi cuối cùng còn phụ thuộc loại meter, đơn vị, bộ xuất và phiên bản thư viện.

Tên có dấu cách, dấu gạch nối hoặc ký tự đặc biệt có thể được xử lý khác nhau giữa các hệ thống. Không dựa vào việc một registry chấp nhận tên khó đọc để coi tên đó là quy ước chung cho toàn ứng dụng. Dùng một tập từ chữ thường đơn giản ngay từ đầu giúp giảm bất ngờ.

### 3.2. Một meter có thể tạo nhiều chuỗi thống kê

Trong ví dụ Prometheus của bài:

| Meter trong Java | Chuỗi được xuất | Ý nghĩa |
| --- | --- | --- |
| Counter `checkout.orders` | `checkout_orders_total` | Số lượng tích lũy |
| Timer `checkout.payment` | `checkout_payment_seconds_count` | Số lần được timer ghi nhận |
| Timer `checkout.payment` | `checkout_payment_seconds_sum` | Tổng thời lượng tính bằng giây |
| Timer `checkout.payment` | `checkout_payment_seconds_max` | Thời lượng lớn nhất theo cơ chế thống kê của timer |

Nhiều dòng không có nghĩa ứng dụng đăng ký nhiều timer cho cùng công việc. Chúng có thể chỉ là những thống kê của một meter.

Nếu bật histogram hoặc các thống kê khác, đầu ra có thể có thêm chuỗi. Không coi bảng trên là danh sách cố định cho mọi registry và mọi cấu hình.

### 3.3. Khóa nhãn và giá trị nhãn có vai trò khác nhau

Trong thí nghiệm sắp chạy:

```text
Trong Java:   payment.method = CreditCard
Prometheus:   payment_method = CreditCard
```

Khóa nhãn đã đổi cách biểu diễn; giá trị vẫn giữ nguyên. Vì vậy, khi truy vấn dữ liệu Prometheus phải dùng khóa mà Prometheus thật sự nhận, đồng thời dùng đúng giá trị của nhóm cần xem.

Không lấy quy tắc chuyển tên của một phiên bản áp dụng như cam kết tuyệt đối cho mọi phiên bản. Các thư viện có thể thay đổi quy tắc xử lý ký tự và hậu tố; kiểm tra dữ liệu xuất thực tế là bước cần thiết khi nâng cấp.

## 4. Thí nghiệm Java hoàn chỉnh với Prometheus registry

Ví dụ dùng JDK 21 và `micrometer-registry-prometheus:1.13.0`. Đây là chương trình Micrometer độc lập, không cần chạy máy chủ Prometheus và không khởi động Spring Boot.

Nó sử dụng registry thật rồi gọi `scrape()` để xem dữ liệu xuất. Cách cung cấp dữ liệu này được mô tả trong [tài liệu Micrometer Prometheus](https://docs.micrometer.io/micrometer/reference/1.13/implementations/prometheus.html).

### 4.1. Dependency

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>meter-naming-lab</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

Phiên bản được ghi rõ để tái lập thí nghiệm. Khi đưa thư viện vào ứng dụng Spring Boot, dùng phiên bản do Spring Boot quản lý để giữ các thành phần tương thích.

Ở phiên bản này, registry dùng Prometheus Java client mới có package `io.micrometer.prometheusmetrics`. Không trộn import với package của biến thể `prometheus-simpleclient`.

### 4.2. Mã nguồn

Lưu tại `src/main/java/demo/MeterNamingDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.config.NamingConvention;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class MeterNamingDemo {
    public static void main(String[] args) {
        PrometheusMeterRegistry registry =
                new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);
        try {
            Counter orders = Counter.builder("checkout.orders")
                    .tag("order.type", "Express")
                    .register(registry);
            orders.increment(2);

            Timer payment = Timer.builder("checkout.payment")
                    .tag("payment.method", "CreditCard")
                    .register(registry);
            payment.record(Duration.ofMillis(120));
            payment.record(Duration.ofMillis(180));

            System.out.println("counterId=" + orders.getId().getName());
            System.out.println("timerId=" + payment.getId().getName());
            System.out.println("tagKey=" +
                    payment.getId().getTags().get(0).getKey());
            System.out.println("tagValue=" +
                    payment.getId().getTag("payment.method"));
            System.out.println("snake=" +
                    NamingConvention.snakeCase.name(
                            "checkout.payment", Meter.Type.TIMER));
            System.out.println("camel=" +
                    NamingConvention.camelCase.name(
                            "checkout.payment", Meter.Type.TIMER));
            System.out.printf(Locale.ROOT, "timerCount=%d timerMs=%.0f%n",
                    payment.count(), payment.totalTime(TimeUnit.MILLISECONDS));

            registry.scrape().lines()
                    .filter(line -> line.startsWith("checkout_"))
                    .sorted()
                    .forEach(System.out::println);
        } finally {
            registry.close();
        }
    }
}
```

Chương trình ghi hai đơn và hai mẫu thời gian 120 ms, 180 ms. Các thời lượng được cung cấp trực tiếp nên không phụ thuộc tốc độ máy.

Hai lời gọi `NamingConvention.snakeCase.name(...)` và `NamingConvention.camelCase.name(...)` chỉ giúp quan sát phép đổi kiểu tên độc lập. Phần `scrape()` cho thấy kết quả thực tế sau khi cả registry và bộ xuất đã xử lý loại meter cùng đơn vị.

### 4.3. Biên dịch và chạy

Từ thư mục chứa `pom.xml`, dùng Maven tải dependency rồi dùng JDK 21 biên dịch. Lần tải đầu cần kết nối kho Maven.

Trên PowerShell/Windows:

```powershell
mvn -q dependency:copy-dependencies -DoutputDirectory=target/dependency
javac --release 21 -cp "target/dependency/*" -d target/classes src/main/java/demo/MeterNamingDemo.java
java -cp "target/classes;target/dependency/*" demo.MeterNamingDemo
```

Trên Linux/macOS, dùng hai lệnh đầu tương tự và thay lệnh chạy bằng:

```bash
java -cp "target/classes:target/dependency/*" demo.MeterNamingDemo
```

Stdout:

```text
counterId=checkout.orders
timerId=checkout.payment
tagKey=payment.method
tagValue=CreditCard
snake=checkout_payment
camel=checkoutPayment
timerCount=2 timerMs=300
checkout_orders_total{order_type="Express"} 2.0
checkout_payment_seconds_count{payment_method="CreditCard"} 2
checkout_payment_seconds_max{payment_method="CreditCard"} 0.18
checkout_payment_seconds_sum{payment_method="CreditCard"} 0.3
```

Chương trình chỉ in các dòng dữ liệu bắt đầu bằng `checkout_` và sắp xếp chúng để thứ tự ổn định. Đây không phải toàn bộ văn bản scrape: các dòng mô tả loại và trợ giúp bắt đầu bằng `#` đã được bỏ khỏi phần in.

### 4.4. Đọc kết quả đúng tầng

- `getId().getName()` vẫn trả về `checkout.orders` và `checkout.payment`.
- Trong danh tính meter, khóa nhãn vẫn là `payment.method`.
- Quy ước gạch dưới đơn giản tạo `checkout_payment`; nó chưa biểu diễn đầy đủ các hậu tố đầu ra của Timer.
- Prometheus xuất thời lượng theo giây: 120 + 180 ms tương ứng tổng 0,3 giây.
- `_count` bằng 2 là số lần đo, không phải số giây.
- `_max` bằng 0,18 giây ở lần đọc ngay sau hai mẫu trong chương trình.

Giá trị lớn nhất của timer còn phụ thuộc cửa sổ thống kê; không suy ra nó luôn là cực đại từ khi JVM khởi động. Với bài này, điểm cần nắm là tên chuỗi cho biết đang đọc thống kê nào và phải đọc đúng đơn vị.

## 5. Áp dụng trong Spring Boot Actuator

### 5.1. Đăng ký bằng tên gốc và registry của ứng dụng

Trong ứng dụng Spring Boot, tiêm `MeterRegistry` đã được cấu hình rồi đăng ký bằng tên gốc:

```java
Timer payment = Timer.builder("checkout.payment")
        .tag("payment.method", "CreditCard")
        .register(meterRegistry);
```

Đây là đoạn minh họa với `meterRegistry` được cung cấp bởi ứng dụng. Không cần tự thay tên thành `checkout_payment_seconds` trong Java chỉ vì đang dùng Prometheus.

Việc `new PrometheusMeterRegistry(...)` ở phần 4 phục vụ thí nghiệm độc lập. Trong service của Spring Boot, tự tạo thêm registry riêng có thể khiến số đo nằm ngoài registry mà Actuator và bộ xuất của ứng dụng đang sử dụng.

Để xuất Prometheus trong một ứng dụng Spring Boot đã có Actuator, thêm dependency `io.micrometer:micrometer-registry-prometheus` do Spring Boot quản lý và expose endpoint cần thử:

```properties
management.endpoints.web.exposure.include=health,metrics,prometheus
```

Đây là phần cấu hình dành cho môi trường thực hành; quyền truy cập management endpoint vẫn theo cấu hình bảo mật của ứng dụng.

### 5.2. Tìm tên gốc qua endpoint metrics

Giả sử ứng dụng đang chạy tại cổng 8080 và đã ghi nhận timer trên:

```bash
curl "http://127.0.0.1:8080/actuator/metrics"
curl --get "http://127.0.0.1:8080/actuator/metrics/checkout.payment" --data-urlencode "tag=payment.method:CreditCard"
```

Trên PowerShell có thể gọi `curl.exe` để tránh bí danh. Nếu ứng dụng có đường dẫn hoặc cổng management riêng, dùng URL tương ứng.

Với endpoint `metrics`, dùng `checkout.payment` và khóa nhãn `payment.method` như trong registry. Không dùng `checkout_payment_seconds_sum` làm tên selector của endpoint này.

Sau đó đọc dữ liệu Prometheus:

```bash
curl "http://127.0.0.1:8080/actuator/prometheus"
```

Ở đầu ra này, tìm tên chuỗi đã xuất, chẳng hạn `checkout_payment_seconds_sum` cùng khóa nhãn `payment_method` trong bộ phiên bản của thí nghiệm.

[Tài liệu Metrics Endpoint của Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.endpoint) yêu cầu dùng tên meter, thay vì tên đã được chuẩn hóa cho hệ thống giám sát, khi chọn chỉ số qua `/actuator/metrics/{name}`.

### 5.3. Cấu hình theo tên gốc khi sử dụng cơ chế của Spring Boot

Ví dụ, cấu hình histogram cho timer được chọn bằng tên meter:

```properties
management.metrics.distribution.percentiles-histogram.checkout.payment=true
```

Trong khi đó, một truy vấn trên Prometheus dùng tên đã xuất:

```promql
checkout_payment_seconds_sum{payment_method="CreditCard"}
```

Truy vấn này chọn tổng thời lượng tích lũy của nhóm tương ứng; nó không tự tính thời lượng trung bình hoặc tốc độ xử lý.

Phân biệt hai nơi giúp tránh tình huống cấu hình theo tên Prometheus ở tầng Spring Boot, hoặc truy vấn tên có dấu chấm như thể đó là tên chuỗi đã được bộ xuất tạo.

## 6. NamingConvention khác với thay đổi danh tính bằng MeterFilter

Có ba thay đổi khác nhau:

| Thay đổi | Tác động chính |
| --- | --- |
| Đổi tên trong lời khai báo meter | Đổi tên mà mã ứng dụng đăng ký |
| `MeterFilter` ánh xạ tên/nhãn | Có thể thay đổi danh tính được đăng ký trong registry |
| `NamingConvention` và bộ xuất | Chuyển cách biểu diễn phù hợp với hệ thống nhận |

`MeterFilter` có thể thay tên, thêm hoặc bỏ nhãn và điều chỉnh thống kê. Nó không chỉ là công cụ đổi dấu chấm thành gạch dưới. [Tài liệu Meter Filters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html) mô tả các trách nhiệm này.

Micrometer cũng cho phép cài một quy ước riêng:

```java
registry.config().namingConvention(customConvention);
```

Đây là điểm mở rộng, với `customConvention` là một triển khai `NamingConvention` do ứng dụng cung cấp. Cần cấu hình từ giai đoạn khởi tạo, trước khi đăng ký các meter liên quan.

Không thay quy ước mặc định của mọi registry bằng `NamingConvention.snakeCase` chỉ để làm cho tên “đồng nhất”. Quy ước dành riêng cho một hệ thống còn có thể xét loại meter, đơn vị và những hạn chế riêng. Dùng một phép đổi kiểu chuỗi đơn giản có thể làm mất phần xử lý đó.

Trong Spring Boot, `MeterRegistryCustomizer` là điểm thích hợp để tùy biến registry trước khi meter được đăng ký. Nếu chỉ một hệ thống đích cần thay đổi, giới hạn tùy biến vào loại registry đó. Khi dùng nhiều registry đích, cùng một tên gốc có thể hợp lý khi xuất thành các tên khác nhau.

Một thay đổi như vậy cần được xem là thay đổi hợp đồng dữ liệu giám sát: phải kiểm tra tên thực tế, truy vấn, dashboard và cảnh báo sử dụng chúng.

## 7. Xung đột tên sau chuyển đổi và hậu tố dành riêng

### 7.1. Hai tên gốc khác nhau vẫn có thể xuất thành cùng tên

Ví dụ cần xem xét trước khi dùng:

```text
checkout.payment
checkout_payment
```

Khi một hệ thống chuẩn hóa dấu chấm thành gạch dưới, hai tên trên có thể mất sự phân biệt ở đầu ra.

Điều tương tự có thể xảy ra với hai khóa nhãn:

```text
payment.method
payment_method
```

Không dùng cả hai để biểu diễn hai ý nghĩa khác nhau rồi dựa vào registry để giữ nguyên sự khác biệt. Cách phản ứng với xung đột tùy bộ xuất và phiên bản: có thể có cảnh báo, lỗi đăng ký hoặc dữ liệu không xuất như dự định. Không dựa vào một hành vi ngầm để thiết kế tên.

Cách phòng tránh là thống nhất một kiểu tên gốc, dùng mỗi tên cho một đại lượng rõ ràng và kiểm tra ánh xạ sang từng hệ thống đích.

### 7.2. Không tự gắn các hậu tố thống kê của bộ xuất

Với Counter và Timer của Micrometer, nên để bộ xuất xử lý những hậu tố như `_total`, `_count`, `_sum` và `_bucket` theo loại meter.

Đặc biệt, Micrometer 1.13 chuyển registry Prometheus sang client Java mới và có quy tắc xử lý các hậu tố dành riêng như `.total`, `.created`, `.bucket` và `.info`. Một hậu tố tự thêm vào tên gốc có thể bị loại bỏ hoặc được tạo lại theo loại meter; vì thế đổi chuỗi tên theo trực giác không bảo đảm đầu ra mong muốn.

Hướng dẫn chuyển phiên bản cũng nêu trường hợp `.info` có ý nghĩa riêng với Gauge, nên không biến khuyến nghị này thành quy tắc cấm mọi tên có chữ `info`. Điểm chính là biết hậu tố thuộc quy ước loại meter nào trước khi sử dụng. [Micrometer 1.13 Migration Guide — Invalid Meter suffixes](https://github.com/micrometer-metrics/micrometer/wiki/1.13-Migration-Guide#invalid-meter-suffixes).

Với thí nghiệm của bài, chọn `checkout.orders` cho Counter và `checkout.payment` cho Timer là đủ; không cần tự tạo thêm những meter mang tên các chuỗi thống kê đầu ra.

## 8. Chẩn đoán khi không tìm thấy chỉ số theo tên dự đoán

Thực hiện theo hướng từ mã tới dữ liệu thật:

1. Xác nhận tên và nhãn tại lời đăng ký meter; kiểm tra loại bộ đo và đơn vị.
2. Kiểm tra `MeterFilter` có đổi danh tính, từ chối meter hoặc bỏ nhãn không.
3. Đọc danh sách `/actuator/metrics` và chi tiết bằng tên có hiệu lực trong registry.
4. Xác nhận registry đích và bộ xuất đang được cấu hình.
5. Đọc `/actuator/prometheus` hoặc dữ liệu tương đương của hệ thống đích.
6. Đối chiếu cả tên chuỗi, khóa nhãn, giá trị nhãn, đơn vị và thống kê.
7. Nếu vừa nâng cấp thư viện, kiểm tra thay đổi quy tắc xuất trước khi sửa mã khai báo.

| Triệu chứng | Điểm cần kiểm tra |
| --- | --- |
| Actuator không nhận tên có gạch dưới | Đang dùng tên xuất Prometheus ở nơi cần tên meter |
| Prometheus không có tên có dấu chấm như trong Java | Tên đã được chuẩn hóa khi xuất |
| Tên metric đúng nhưng bộ lọc nhãn không khớp | Khóa nhãn đã đổi dạng hoặc giá trị khác chữ hoa/thường |
| `sum` nhỏ hơn số mili giây dự đoán 1.000 lần | Có thể đang đọc giây thay vì mili giây |
| Có nhiều dòng cho một timer | Kiểm tra đó là count, sum, max hoặc bucket |
| Tên gốc khác nhau nhưng dữ liệu xuất thiếu/bất thường | Kiểm tra xung đột sau chuyển đổi và hậu tố dành riêng |
| Đổi quy ước nhưng dữ liệu không nhất quán | Kiểm tra thời điểm cấu hình, registry được tác động và meter đã đăng ký |

Số đo bị lọc, chưa được đăng ký hoặc nằm trong registry khác không được giải quyết bằng cách chỉ đổi tên truy vấn. Đừng kết luận mọi trường hợp “không tìm thấy” đều do dấu chấm và gạch dưới.

## 9. Khi đổi tên, bảo vệ cách người khác đang sử dụng số liệu

Tên metric và khóa nhãn là một phần của hợp đồng giữa ứng dụng với hệ thống giám sát. Đổi `checkout.payment` thành một tên mới có thể làm dashboard cũ không còn nhận dữ liệu, dù mã vẫn biên dịch và ứng dụng vẫn chạy.

Trước khi đổi, cần xác định:

- Tên gốc, loại meter và đơn vị có thay đổi ý nghĩa không.
- Tên xuất trên các registry đang sử dụng sẽ trở thành gì.
- Truy vấn, recording rule, dashboard và cảnh báo nào đang tham chiếu tên hoặc nhãn cũ.
- Giai đoạn chuyển tiếp được biểu diễn như thế nào để người đọc không cộng nhầm số liệu cũ và mới.

Việc đổi tên chỉ để “đẹp hơn” vẫn có chi phí tương thích. Với chỉ số do framework tạo, ưu tiên dùng tên được tích hợp hỗ trợ hoặc cơ chế đổi tên được tài liệu hóa; tránh sửa hàng loạt theo tên chuỗi đầu ra đang nhìn thấy.

## 10. Tự kiểm tra cách hiểu

1. Java đăng ký `checkout.payment`, nhưng Prometheus xuất `checkout_payment_seconds_sum`. Tên nào dùng để chọn meter qua Actuator?
2. Hai mẫu 120 ms và 180 ms tạo `_count` và `_sum` bằng bao nhiêu trong thí nghiệm?
3. Vì sao `NamingConvention.snakeCase.name(...)` chỉ in `checkout_payment` mà scrape còn có `_seconds_count`?
4. Khóa nhãn `payment.method` đổi thành `payment_method` thì giá trị `CreditCard` có tự thành `credit_card` không?
5. Hai tên `checkout.payment` và `checkout_payment` có luôn an toàn để biểu diễn hai đại lượng khác nhau không?

Đối chiếu: dùng tên gốc `checkout.payment`; count bằng 2 và sum bằng 0,3 giây; vì phép đổi kiểu tên chưa bao gồm toàn bộ xử lý loại meter/đơn vị/thống kê của bộ xuất; giá trị không tự đổi như giả định đó; hai tên có thể xung đột sau chuẩn hóa.

Khi đọc được tên gốc, ánh xạ được sang tên đầu ra thực tế và giải thích đúng từng nhãn, đơn vị, hậu tố thống kê, bạn có thể đặt tên mới nhất quán và chẩn đoán lỗi tìm kiếm chỉ số mà không phải đoán.
