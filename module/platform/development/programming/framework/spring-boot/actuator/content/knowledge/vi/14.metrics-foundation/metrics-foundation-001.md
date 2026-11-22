# Micrometer cung cấp lớp trừu tượng cho chỉ số đo lường như thế nào

Một dịch vụ xử lý đơn hàng có thể cần biết mỗi phút có bao nhiêu yêu cầu bị từ chối, những lần xử lý thành công mất bao lâu và hiện còn bao nhiêu đơn đang chờ. Đó là các câu hỏi về số lượng, thời gian và trạng thái có thể biểu diễn bằng số.

Nếu mỗi nơi trong mã nghiệp vụ gọi trực tiếp API của một sản phẩm giám sát, việc đổi sản phẩm sẽ kéo theo thay đổi ở nhiều lớp. Micrometer đặt một API đo lường chung giữa ứng dụng và các cách thu thập, xuất dữ liệu khác nhau.

Sau bài này, bạn có thể giải thích vai trò của `Meter`, `MeterRegistry` và registry cho từng hệ thống giám sát; đọc một điểm đo có tên và tag; đồng thời kiểm chứng rằng cùng mã đo lường hoạt động qua các registry khác nhau. Ví dụ dùng Micrometer 1.13.0, thuộc dòng Micrometer dùng cùng Spring Boot 3.3.x, với mã Java 17 chạy được trên JDK 21.

## 1. Hiểu chỉ số đo lường trước khi hiểu lớp trừu tượng

Chỉ số đo lường (metric) là thông tin định lượng về ứng dụng. Khi được thu thập theo thời gian, nó giúp trả lời các câu hỏi như:

- Số yêu cầu bị từ chối đang tăng nhanh hay chậm?
- Thời gian xử lý trung bình đang thay đổi thế nào?
- Có bao nhiêu phần tử đang nằm trong hàng đợi?

Ví dụ, bộ đếm `shop.checkout.rejected` có tag `reason=validation` biểu diễn số lần yêu cầu thanh toán bị từ chối vì không hợp lệ. Hệ thống giám sát có thể dùng các mẫu theo thời gian để tính tốc độ từ chối trong một khoảng thời gian.

Thông tin này khác với một bản ghi log mô tả chi tiết một lần thất bại, hoặc một trace theo dõi đường đi của một yêu cầu qua nhiều thành phần. Metrics thường hữu ích cho việc nhìn xu hướng và so sánh các nhóm; muốn biết chi tiết một yêu cầu cụ thể, cần thêm nguồn quan sát thích hợp.

Ở mức đầu vào, ứng dụng quyết định **đo điều gì và khi nào**. Ở mức đầu ra, hệ thống giám sát quyết định **lưu, truy vấn và hiển thị số đo ra sao**. Micrometer cung cấp cách nối hai mức đó bằng một mô hình đo lường chung.

## 2. Micrometer giải quyết sự phụ thuộc nào?

Giả sử ứng dụng muốn ghi nhận số lần thanh toán bị từ chối. Khi gắn trực tiếp với một thư viện giám sát riêng, điểm đo có thể phụ thuộc vào cách thư viện đó tạo bộ đếm, đặt tên và gắn nhãn. Khi bổ sung một nơi nhận thứ hai, các lớp nghiệp vụ có thể phải biết thêm một API nữa.

Với Micrometer, mã tại điểm đo chỉ sử dụng API chung:

```java
Counter rejected = registry.counter(
        "shop.checkout.rejected", "reason", "validation");
rejected.increment();
```

Đây là đoạn trích cần có biến `registry` kiểu `MeterRegistry` và import `io.micrometer.core.instrument.Counter`. Ví dụ độc lập ở phần 6 sẽ cung cấp đầy đủ các thành phần.

Mã gọi `increment()` không cần biết dữ liệu cuối cùng đi tới Prometheus, một dịch vụ giám sát khác hay chỉ ở trong bộ nhớ khi kiểm thử. Cách nối với nơi nhận nằm trong cấu hình và implementation của registry.

Micrometer được thiết kế như một lớp API chung cho việc gắn phép đo vào ứng dụng JVM, giúp mã đo lường bớt phụ thuộc vào một nhà cung cấp. [Mục đích của Micrometer](https://docs.micrometer.io/micrometer/reference/concepts.html).

Lợi ích có giới hạn rõ: việc đổi hệ thống giám sát thường tập trung ở phụ thuộc, cấu hình xuất dữ liệu và phần vận hành. Ngữ nghĩa nghiệp vụ của điểm đo vẫn do ứng dụng chịu trách nhiệm. Một bộ đếm đặt sai chỗ sẽ vẫn cho số liệu gây hiểu nhầm dù đổi registry thành công.

## 3. Các thành phần liên hệ với nhau ra sao?

```text
Mã ứng dụng và các thành phần đo sẵn
        |
        v
API chung: Counter, Timer, Gauge, ...
        |
        v
MeterRegistry
        |
        +--> registry bộ nhớ để kiểm thử
        |
        +--> registry cho hệ thống giám sát A
        |
        +--> registry cho hệ thống giám sát B
                      |
                      v
           Thu thập/xuất, lưu và truy vấn
                      |
                      v
             Biểu đồ và cảnh báo
```

| Thành phần | Trách nhiệm | Câu hỏi nó giải quyết |
| --- | --- | --- |
| Mã gắn phép đo vào ứng dụng (instrumentation) | Chọn thời điểm và dữ liệu cần đo | Khi nào tăng số lần từ chối? |
| `Meter` | Mô hình chung của một công cụ thu thập số đo | Công cụ này có những phép đo nào? |
| `Counter`, `Timer`, `Gauge` | API cho các ngữ nghĩa đo khác nhau | Đếm sự kiện, đo thời gian hay đọc trạng thái hiện tại? |
| `MeterRegistry` | Đăng ký, quản lý và tìm meter; cung cấp implementation thích hợp | Meter thuộc registry nào? |
| Registry cho hệ thống cụ thể | Chuyển mô hình Micrometer sang cách biểu diễn và xuất dữ liệu của hệ thống đó | Dữ liệu được định dạng và đưa ra ngoài ra sao? |
| Hệ thống giám sát | Tiếp nhận, lưu, tính toán và phục vụ truy vấn | Tốc độ lỗi trong năm phút gần nhất là bao nhiêu? |
| Spring Boot Actuator | Tích hợp, tự cấu hình và cung cấp các khả năng quản lý trong ứng dụng Spring Boot | Registry và các phép đo sẵn được nối vào ứng dụng thế nào? |

`MeterRegistry` là một **lớp trừu tượng trong Java**, còn `Counter`, `Timer` và `Gauge` là các giao diện đo. Không nên hiểu “lớp trừu tượng” trong tên bài chỉ là một từ khóa `abstract`: ở cấp thiết kế, nó còn là hợp đồng chung giúp mã gọi tách khỏi cách hiện thực của từng hệ thống.

Micrometer không tự trở thành một máy chủ lưu lịch sử, bảng điều khiển hay bộ cảnh báo. Những chức năng đó thường nằm ở hệ thống giám sát và các thành phần vận hành đi cùng.

### Ba registry giúp nhìn rõ vai trò

- `SimpleMeterRegistry`: giữ số đo trong bộ nhớ, thích hợp cho thử nghiệm; không tự xuất dữ liệu tới một máy chủ giám sát.
- Registry chuyên cho một hệ thống: ví dụ `PrometheusMeterRegistry`, có phần hiện thực phù hợp với hệ thống đích.
- `CompositeMeterRegistry`: kết nối nhiều registry con để các điểm đo có thể ghi tới nhiều nơi nhận.

Các registry là nơi tạo và giữ meter; registry tổng hợp cho phép dùng chung đường ghi với nhiều registry con. [Khái niệm registry của Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/registry.html).

## 4. Hợp đồng chung gồm tên, tag và kiểu đo

### 4.1. Tên mô tả đại lượng; tag mô tả chiều phân loại

Xét ba bộ đếm:

```text
shop.checkout.rejected {channel=web, reason=validation}
shop.checkout.rejected {channel=mobile, reason=validation}
shop.checkout.rejected {channel=web, reason=stock}
```

Tên chung cho biết đại lượng được đếm. Tag, còn gọi là chiều phân loại (dimension), cho biết số liệu thuộc nhóm nào. Người vận hành có thể xem tổng các nhóm hoặc lọc theo kênh và lý do.

Trong cùng một registry, meter được nhận diện bằng tổ hợp **tên và tập tag**. Đổi một giá trị tag tạo một định danh khác. Đăng ký lại cùng tên và tag cho cùng loại công cụ sẽ lấy lại meter đã có; không tự tạo một bộ đếm độc lập cho mỗi biến Java. [Mô hình Meter](https://docs.micrometer.io/micrometer/reference/concepts/meters.html).

```java
Counter first = registry.counter(
        "shop.checkout.rejected", "reason", "validation");
Counter same = registry.counter(
        "shop.checkout.rejected", "reason", "validation");
first.increment();
System.out.println(same.count());
```

Trong `SimpleMeterRegistry`, đoạn trích trên in `1.0`. Hai biến tham chiếu cùng bộ đếm. Khi chuyển sang registry khác, vẫn cần hiểu cách implementation đó tổng hợp và cung cấp số liệu để diễn giải kết quả đọc.

Không đăng ký một `Counter` rồi dùng cùng định danh đó cho `Timer`. Với phiên bản trong ví dụ, registry báo lỗi `IllegalArgumentException` khi gặp xung đột loại này. Kiểu đo là một phần của hợp đồng cần giữ nhất quán, không phải cách tạo thêm một kênh dữ liệu dưới cùng định danh.

### 4.2. Tên logic không nhất thiết giống tên xuất ra ngoài

Micrometer khuyến nghị tên gồm các từ viết thường, cách nhau bằng dấu chấm, chẳng hạn `shop.checkout.duration`. Registry có thể chuyển tên sang quy ước của hệ thống đích, kèm cách biểu diễn đơn vị và các phép đo tương ứng. [Quy ước đặt tên meter](https://docs.micrometer.io/micrometer/reference/concepts/naming.html).

Vì vậy, khi đọc mã Java hãy tìm tên logic được đăng ký; khi viết truy vấn cho hệ thống giám sát hãy kiểm tra tên và cấu trúc thực tế được xuất. Không suy ra tên một chuỗi thời gian chỉ bằng cách chép nguyên tên Java hoặc tự nối hậu tố theo trí nhớ.

### 4.3. Số meter và số chuỗi thời gian có thể khác nhau

Một meter không nhất thiết chỉ tạo một giá trị. Một `Timer` tối thiểu cung cấp số lần ghi nhận và tổng thời gian; các thống kê bổ sung phụ thuộc loại registry và cấu hình. Vì vậy, hai tag tạo hai định danh meter chưa có nghĩa hệ thống giám sát chỉ phải lưu hai chuỗi thời gian.

Giữ schema tên và tag nhất quán cho cùng một đại lượng giúp các bộ đếm hoặc bộ đo thời gian được truy vấn và so sánh đúng nghĩa. Chẳng hạn, các nhóm của `shop.checkout.duration` đều nên dùng cùng ý nghĩa cho tag `outcome`.

## 5. Chọn công cụ theo ý nghĩa của câu hỏi

| Câu hỏi | Công cụ thường phù hợp | Điểm cần hiểu |
| --- | --- | --- |
| Đã có bao nhiêu lần bị từ chối? | `Counter` | Tăng theo các lần ghi nhận; thích hợp để tính tốc độ sự kiện |
| Các lần xử lý đã ghi nhận mất bao lâu? | `Timer` | Có số lần và tổng thời gian, nhận đơn vị thời gian rõ ràng |
| Hàng đợi hiện dài bao nhiêu? | `Gauge` | Đọc trạng thái hiện tại tại lúc quan sát |
| Kích thước các gói dữ liệu phân bố ra sao? | `DistributionSummary` | Ghi phân bố giá trị không phải thời gian, chẳng hạn số byte |
| Hiện có tác vụ dài nào còn đang chạy và đã chạy bao lâu? | `LongTaskTimer` | Phù hợp theo dõi tác vụ còn hoạt động |

Bảng này là định hướng chọn ngữ nghĩa, không phải yêu cầu phải dùng hết mọi loại meter trong một ứng dụng.

### Counter và Gauge không thay thế nhau

`Counter` dùng cho lượng tăng tích lũy do các sự kiện. Không dùng thao tác giảm bộ đếm để biểu diễn số yêu cầu đang xử lý. Số tác vụ đang chạy hoặc độ dài hàng đợi có thể tăng rồi giảm, nên thường cần phép đo trạng thái hiện tại.

`Gauge` quan sát một đối tượng hoặc hàm lấy giá trị. Những thay đổi xảy ra giữa hai lần thu thập không tự trở thành lịch sử đầy đủ. Nếu cần biết tổng số lần một sự kiện xảy ra, việc chỉ đọc giá trị hiện tại là chưa đủ. [Ngữ nghĩa Gauge](https://docs.micrometer.io/micrometer/reference/1.13/concepts/gauges.html).

### Timer đã có số lần ghi nhận

Nếu mỗi lần xử lý đã được ghi vào `Timer`, có thể dùng số lần của timer để biết số sự kiện đó; không cần thêm counter chỉ để đếm lại đúng cùng tập sự kiện. Counter phù hợp hơn khi câu hỏi đếm có ý nghĩa riêng. [Ngữ nghĩa Counter](https://docs.micrometer.io/micrometer/reference/1.13/concepts/counters.html).

Trong ví dụ tiếp theo:

- Counter đếm yêu cầu bị từ chối do kiểm tra đầu vào.
- Timer đo các lần thanh toán thành công.

Đó là hai tập sự kiện khác nhau. Một lần bị từ chối không tự làm tăng số lần thành công của timer.

### Đơn vị là một phần của hợp đồng

`Timer.record(Duration)` hoặc `Timer.record(amount, TimeUnit)` biểu diễn đơn vị rõ ràng. Registry chuyển số đo sang đơn vị phù hợp với nơi nhận. Khi đọc lại bằng `totalTime(...)`, người gọi cũng chỉ định đơn vị mong muốn. [Timer và đơn vị thời gian](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html).

Ví dụ, 120 ms và 80 ms có tổng 200 ms, cũng là 0,2 giây. Hai cách biểu diễn này mô tả cùng một lượng thời gian. Đặt tên có chữ “milliseconds” nhưng truyền một số không có đơn vị vào công cụ khác không đem lại hợp đồng rõ như API thời gian.

## 6. Ví dụ Java: cùng mã đo lường, các registry khác nhau

Ví dụ tạo một registry bộ nhớ độc lập và một registry tổng hợp nối tới hai registry bộ nhớ khác. Mục đích là quan sát cách tách mã đo khỏi nơi nhận; chương trình không kết nối máy chủ bên ngoài.

### 6.1. Chuẩn bị phụ thuộc

Tạo một thư mục thử nghiệm riêng với hai tệp:

```text
micrometer-abstraction-demo/
├── pom.xml
└── MicrometerAbstractionDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>micrometer-abstraction-demo</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

Phiên bản được cố định để tái lập ví dụ độc lập. Trong dự án Spring Boot dùng cơ chế quản lý phụ thuộc của Boot, nên dùng phiên bản Micrometer do tập phụ thuộc của Boot quản lý thay vì chép số phiên bản thử nghiệm này vào từng module.

### 6.2. Mã đầy đủ

Nội dung `MicrometerAbstractionDemo.java`:

```java
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.composite.CompositeMeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class MicrometerAbstractionDemo {

    static final class CheckoutMetrics {
        private final Counter rejected;
        private final Timer successfulDuration;

        CheckoutMetrics(MeterRegistry registry) {
            rejected = Counter.builder("shop.checkout.rejected")
                    .description("Checkout requests rejected by validation")
                    .tag("channel", "web")
                    .tag("reason", "validation")
                    .register(registry);

            successfulDuration = Timer.builder("shop.checkout.duration")
                    .description("Duration of successful checkouts")
                    .tag("channel", "web")
                    .tag("outcome", "success")
                    .register(registry);
        }

        void rejectedByValidation() {
            rejected.increment();
        }

        void successfulCheckout(Duration duration) {
            successfulDuration.record(duration);
        }
    }

    public static void main(String[] args) {
        SimpleMeterRegistry local = new SimpleMeterRegistry();
        SimpleMeterRegistry first = new SimpleMeterRegistry();
        SimpleMeterRegistry second = new SimpleMeterRegistry();
        CompositeMeterRegistry composite = new CompositeMeterRegistry();
        try {

            composite.add(first);
            composite.add(second);

            runScenario(new CheckoutMetrics(local));
            runScenario(new CheckoutMetrics(composite));

            printSnapshot("local", local);
            printSnapshot("first", first);
            printSnapshot("second", second);
        } finally {
            composite.close();
            first.close();
            second.close();
            local.close();
        }
    }

    private static void runScenario(CheckoutMetrics metrics) {
        metrics.rejectedByValidation();
        metrics.successfulCheckout(Duration.ofMillis(120));
        metrics.successfulCheckout(Duration.ofMillis(80));
    }

    private static void printSnapshot(
            String label, MeterRegistry registry) {
        Counter rejected = registry.get("shop.checkout.rejected")
                .tags("channel", "web", "reason", "validation")
                .counter();
        Timer duration = registry.get("shop.checkout.duration")
                .tags("channel", "web", "outcome", "success")
                .timer();

        System.out.printf(Locale.ROOT,
                "%s rejected=%.0f completed=%d totalMs=%.0f meanMs=%.0f%n",
                label, rejected.count(), duration.count(),
                duration.totalTime(TimeUnit.MILLISECONDS),
                duration.mean(TimeUnit.MILLISECONDS));
    }
}
```

Các lớp có vai trò khác nhau:

1. `CheckoutMetrics` chỉ phụ thuộc API chung `MeterRegistry`, `Counter` và `Timer`. Hai meter được đăng ký một lần trong hàm khởi tạo rồi giữ trong các trường.
2. `runScenario(...)` chỉ mô tả các lần ghi nhận. Nó không kiểm tra registry có kiểu gì, không có nhánh riêng cho từng nơi xuất.
3. `main` sở hữu cách kết nối các registry. Các registry con được thêm trước khi tạo meter và trước khi chạy kịch bản.
4. `printSnapshot(...)` đọc dữ liệu bằng tên và tag để kiểm chứng các nơi nhận.
5. Phần `finally` đóng các registry do chương trình tự tạo. Với API 1.13.0 dùng ở đây, chương trình gọi `close()` trực tiếp.

Hai giá trị thời gian được truyền cố định để đầu ra có thể kiểm chứng. Chương trình không tuyên bố một nghiệp vụ thật luôn chạy trong 120 ms hoặc 80 ms và không dùng `Thread.sleep(...)` để giả làm kết quả đo hiệu năng.

### 6.3. Biên dịch và chạy

Cần Maven và JDK 17 trở lên. Dùng JDK 21 vẫn biên dịch với mức ngôn ngữ Java 17. Tại thư mục chứa hai tệp, tải các phụ thuộc chạy vào `lib`:

```shell
mvn -q dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=lib
```

Trên PowerShell/Windows:

```powershell
New-Item -ItemType Directory -Path out -Force | Out-Null
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out MicrometerAbstractionDemo.java
java -cp "out;lib/*" MicrometerAbstractionDemo
```

Trên Linux/macOS:

```shell
mkdir -p out
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out MicrometerAbstractionDemo.java
java -cp "out:lib/*" MicrometerAbstractionDemo
```

Dấu phân cách giữa các mục classpath là `;` trên Windows và `:` trên Linux/macOS. Maven cần truy cập kho phụ thuộc trong lần đầu nếu máy chưa có các thư viện.

Stdout:

```text
local rejected=1 completed=2 totalMs=200 meanMs=100
first rejected=1 completed=2 totalMs=200 meanMs=100
second rejected=1 completed=2 totalMs=200 meanMs=100
```

`Locale.ROOT` giúp định dạng số ổn định giữa các thiết lập ngôn ngữ của máy.

### 6.4. Điều gì chứng minh lớp trừu tượng đang hoạt động?

Cùng một hàm khởi tạo `CheckoutMetrics(MeterRegistry)` nhận được cả `SimpleMeterRegistry` lẫn `CompositeMeterRegistry`. Cùng `runScenario(...)` tạo kết quả đúng ở các nơi nhận mà không đổi cách gọi `increment()` hay `record(...)`.

`local` nhận một kịch bản độc lập. `first` và `second` đều nhận kịch bản được ghi vào `composite`; không phải ứng dụng đã thực hiện nghiệp vụ hai lần để có dữ liệu cho hai nơi.

Mỗi nơi có một lần bị từ chối và hai lần thành công. Timer có tổng 200 ms, nên trung bình là 100 ms. Số `completed` lấy từ `Timer.count()`, không từ counter từ chối.

Hai registry con cùng thuộc loại bộ nhớ để thí nghiệm không cần mạng. Điều này chứng minh sự tách biệt ở API và cơ chế phân phối. Khi dùng registry cho hệ thống bên ngoài, vẫn cần kiểm chứng cấu hình xuất dữ liệu và kết quả thực tế ở hệ thống đó.

## 7. Ranh giới của khả năng dùng chung

### 7.1. Mã ghi nhận giữ nguyên, cấu hình đầu ra có thể thay đổi

Các yếu tố thường giữ được:

- Tên logic và ý nghĩa của điểm đo.
- Cách gọi API `Counter`, `Timer`, `Gauge`.
- Thời điểm tăng bộ đếm hoặc ghi thời gian trong luồng nghiệp vụ.
- Quy ước phân loại bằng tag có số giá trị được kiểm soát.

Các yếu tố vẫn cần xét khi đổi hệ thống giám sát:

- Thư viện registry, địa chỉ đích, quyền kết nối và cấu hình vận hành.
- Cách đặt tên vật lý, đơn vị xuất và dạng dữ liệu.
- Cơ chế kéo dữ liệu về (pull) hoặc đẩy dữ liệu đi (push).
- Chu kỳ tổng hợp, cách biểu diễn bộ đếm và các cửa sổ thống kê.
- Truy vấn, biểu đồ, cảnh báo và tính năng thống kê mà nơi nhận hỗ trợ.

Ví dụ, không thể kỳ vọng một câu truy vấn của hệ thống này chạy nguyên văn ở hệ thống khác chỉ vì cả hai cùng nhận dữ liệu từ Micrometer. Lớp trừu tượng giúp giữ mã tại điểm đo ổn định, còn việc diễn giải dữ liệu đầu ra cần đúng với hệ thống đích.

### 7.2. Registry tổng hợp không phải kho phát lại lịch sử

Một lần tăng counter khi registry tổng hợp chưa có nơi nhận sẽ không được phát lại chỉ vì sau đó thêm registry con. Registry con mới bắt đầu nhận các lần ghi về sau. Thêm registry giữa lúc ứng dụng đang hoạt động không tự dựng lại dữ liệu đã xảy ra trước đó.

Với các công cụ đọc trạng thái như gauge, thời điểm quan sát lại có ý nghĩa khác với việc phát lại các lần tăng counter. Khi kiểm chứng, hãy xác định loại meter thay vì áp dụng quy tắc của bộ đếm cho tất cả công cụ.

### 7.3. Số đo trong bộ nhớ chưa chứng minh dữ liệu đã tới máy chủ

Lệnh `increment()` thành công không phải biên nhận rằng máy chủ giám sát đã lưu dữ liệu. Cần kiểm tra lần lượt: meter có được ghi, registry đúng có được cấu hình, dữ liệu có được xuất hoặc thu thập, rồi nơi nhận có dữ liệu đúng hay không.

Đặc biệt, `SimpleMeterRegistry` là công cụ hữu ích cho kiểm thử nhưng không tự tạo biểu đồ lịch sử bên ngoài. Ngược lại, dữ liệu đã nằm trong hệ thống giám sát có thể còn được truy vấn dù tiến trình ứng dụng vừa khởi động lại và bộ đếm cục bộ bắt đầu lại.

### 7.4. Chọn cách tổng hợp đúng nghĩa

Giá trị tuyệt đối của counter có thể phụ thuộc thời gian sống của tiến trình. Với câu hỏi “đang xảy ra bao nhiêu lần mỗi giây”, cần tốc độ thay đổi trong khoảng thời gian phù hợp thay vì chỉ nhìn tổng hiện tại.

Với timer, hai instance có số lần xử lý khác nhau không nên được tính trung bình bằng cách lấy trung bình cộng hai giá trị trung bình. Chẳng hạn:

```text
Instance A: tổng 200 ms cho 2 lần -> trung bình 100 ms
Instance B: tổng 800 ms cho 1 lần -> trung bình 800 ms
Toàn bộ: tổng 1000 ms cho 3 lần -> trung bình khoảng 333,33 ms
```

Giá trị 450 ms từ `(100 + 800) / 2` không phải trung bình của ba lần xử lý. Phép tính phải dùng những đại lượng cùng khoảng thời gian và cùng ý nghĩa. API chung không tự sửa một truy vấn tổng hợp sai.

Không mặc định timer luôn có mọi phân vị hoặc histogram. Những thống kê đó cần được cấu hình và được nơi nhận hỗ trợ phù hợp; bài này chỉ dựa vào số lần và tổng thời gian để kiểm chứng.

## 8. Tag hữu ích khi số giá trị được kiểm soát

Số tổ hợp tag khác nhau thường được gọi là độ phân tán định danh (cardinality). Chẳng hạn, một điểm đo có ba kênh, hai kết quả và bốn vùng có tối đa `3 × 2 × 4 = 24` tổ hợp trước khi tính thêm các chiều khác. Không phải mọi tổ hợp đều phải xuất hiện.

Mỗi tổ hợp có thể kéo theo nhiều chuỗi thời gian tùy loại meter và cấu hình. Thêm tag theo từng người dùng hoặc từng yêu cầu có thể làm số lượng định danh tăng liên tục.

| Tag | Ví dụ | Đánh giá theo mục đích đo |
| --- | --- | --- |
| `channel` | `web`, `mobile` | Hợp lý nếu tập giá trị được giới hạn |
| `outcome` | `success`, `failure` | Hợp lý khi ý nghĩa nhất quán |
| `reason` | `validation`, `stock` | Hợp lý khi chuẩn hóa thành nhóm rõ ràng |
| `requestId` | Một mã mới cho mỗi yêu cầu | Thường làm số tổ hợp tăng theo từng yêu cầu |
| `userId` | Một giá trị cho mỗi người dùng | Thường không phù hợp để phân loại metrics thông thường |
| `uri` | Đường dẫn chứa mã đơn cụ thể | Cần chuẩn hóa thành mẫu tuyến đường khi dùng để đo HTTP |

Dữ liệu do người dùng cung cấp cần được chuẩn hóa và giới hạn trước khi trở thành tag. Với định danh chi tiết của từng yêu cầu, log hoặc trace thường là nơi phù hợp hơn để tra cứu, theo thiết kế quan sát của ứng dụng.

Một công cụ kiểm soát ở cấp registry là `MeterFilter`: có thể chặn meter, biến đổi định danh hoặc cấu hình thống kê. Filter từ chối đăng ký có thể trả về công cụ không ghi nhận số liệu (no-op), nên mã gọi vẫn chạy nhưng không có dữ liệu đo được lưu. [MeterFilter](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html).

Filter là một lớp kiểm soát bổ sung. Nó không thay thế việc chọn tag có ý nghĩa và có số giá trị được quản lý ngay từ điểm đo. Cấu hình các quy tắc chung trước khi tạo meter giúp hành vi nhất quán.

## 9. Đưa mô hình này vào Spring Boot Actuator

Trong Spring Boot, thường đưa `spring-boot-starter-actuator` vào dự án, dùng phiên bản phụ thuộc do Boot quản lý và nhận `MeterRegistry` do Spring cung cấp. Các thư viện registry tương ứng trên classpath được tự cấu hình khi các điều kiện và thuộc tính liên quan cho phép. [Metrics trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Có thể chuyển `CheckoutMetrics` trong ví dụ thành một bean của ứng dụng và tiêm `MeterRegistry` qua hàm khởi tạo. Phần nghiệp vụ tiếp tục gọi `rejectedByValidation()` hoặc `successfulCheckout(...)`; phần cấu hình chọn nơi nhận dữ liệu.

Đặt tên ứng dụng hoặc vùng chạy bằng cấu hình dùng chung giúp các meter được phân loại nhất quán. Ví dụ sau là tệp cấu hình cho một ứng dụng Spring Boot đã có phụ thuộc Actuator, không phải phần cần thêm vào chương trình Java độc lập:

```java
package example.metrics;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {
    @Bean
    MeterRegistryCustomizer<MeterRegistry> commonMetricsTags() {
        return registry -> registry.config().commonTags(
                "application", "checkout-service",
                "region", "vn-south");
    }
}
```

Tệp đặt tại `example/metrics/MetricsConfiguration.java` trong source root và phải nằm trong phạm vi Spring quét hoặc được import. Các tag dùng chung được thiết lập trước khi đăng ký meter. [API MeterRegistryCustomizer 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/metrics/MeterRegistryCustomizer.html).

Trong ứng dụng web, endpoint `metrics` của Actuator giúp kiểm tra số đo đang có; nơi xuất cho một hệ thống giám sát và việc mở endpoint quản lý là các phần cấu hình khác nhau. Có số liệu ở endpoint kiểm tra chưa chứng minh một máy chủ bên ngoài đang thu thập dữ liệu. Khi cung cấp giao diện quản lý qua mạng, áp dụng quyền truy cập phù hợp với dữ liệu được hiển thị.

Actuator còn tích hợp nhiều phép đo sẵn. Các chỉ số nghiệp vụ riêng vẫn cần được ứng dụng định nghĩa đúng ý nghĩa. Trước khi thêm một phép đo, kiểm tra xem đã có đại lượng tương đương để tránh ghi trùng hoặc tạo hai tên gây nhầm lẫn.

## 10. Lỗi thường gặp và cách nhận ra

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| Gọi `increment()` nhưng nơi giám sát không có dữ liệu | Registry thực sự được dùng, filter, cấu hình xuất, đường thu thập và thời điểm đọc |
| Thêm registry con sau đó nhưng không thấy giá trị counter cũ | Registry tổng hợp không phát lại các lần tăng trước khi có nơi nhận |
| Mỗi biến Java được kỳ vọng có bộ đếm riêng nhưng số liệu cộng dồn | Tên và tag có trùng nhau trong cùng registry không? |
| Lỗi khi đăng ký meter | Có dùng cùng định danh cho các loại công cụ khác nhau không? |
| Số chuỗi thời gian tăng rất nhanh | Tag có mã yêu cầu, người dùng hoặc dữ liệu chưa chuẩn hóa không? |
| Một chỗ đo ms, biểu đồ lại hiện đơn vị khác | Kiểm tra đơn vị đầu vào, đơn vị xuất và truy vấn |
| Dùng timer rồi thêm counter cùng đếm mỗi lần thành công | Có cần hai đại lượng khác nhau hay đang ghi lại cùng một ý nghĩa? |
| Gauge về `NaN` hoặc mất dữ liệu | Đối tượng trạng thái có còn được giữ bằng tham chiếu mạnh không? |

Gauge thường giữ tham chiếu yếu tới đối tượng được quan sát. Nếu đăng ký một đối tượng tạm rồi không còn giữ nó, bộ thu gom rác có thể thu hồi đối tượng đó. Với một `AtomicInteger` biểu diễn trạng thái, ứng dụng cần giữ đối tượng sống theo đúng vòng đời của phép đo, chẳng hạn trong một trường của bean.

Giữ đúng vòng đời cũng quan trọng với registry. Trong chương trình độc lập, bạn sở hữu việc tạo và đóng registry. Trong Spring Boot, sử dụng bean do Spring quản lý giúp các điểm đo đi theo cấu hình và vòng đời chung.

## 11. Thực hành để kiểm chứng cách hiểu

Thực hiện từng thay đổi trên chương trình độc lập và dự đoán kết quả trước khi chạy:

1. Thêm một lần `successfulCheckout(Duration.ofMillis(50))` vào `runScenario(...)`. Mỗi nơi nhận phải có `completed=3`, `totalMs=250`; trung bình được định dạng thành `83` do mẫu in dùng `%.0f`.
2. Bỏ `composite.add(second)`. `first` vẫn có dữ liệu; đoạn `printSnapshot("second", second)` sẽ báo không tìm thấy meter vì ví dụ dùng cách tra cứu bắt buộc `get(...)`. Điều này giúp phân biệt lỗi kết nối nơi nhận với lỗi tại điểm đo.
3. Đăng ký thêm counter có cùng tên nhưng tag `reason=stock`, rồi tăng một lần. Bộ đếm `reason=validation` giữ nguyên; truy vấn phải chọn đúng nhóm cần xem.
4. Trong một thí nghiệm riêng với registry tổng hợp mới, tạo counter rồi tăng khi chưa có registry con. Sau đó thêm registry con và đọc lại: các lần tăng trước đó không được phục hồi. Tăng tiếp để kiểm tra đường ghi mới.
5. Trong registry bộ nhớ mới, đăng ký counter cùng tên và cùng tag qua hai biến rồi tăng qua một biến. Đọc qua biến còn lại để kiểm tra chúng đang dùng chung một meter.

Với kiểm thử tích hợp của ứng dụng thật, tách hai câu hỏi: điểm đo đã ghi đúng dữ liệu vào registry chưa, và hệ thống giám sát đã thu được dữ liệu xuất ra chưa. Mỗi câu hỏi cần bằng chứng ở đúng vị trí.

