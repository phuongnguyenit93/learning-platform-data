# Tính tốc độ tại ứng dụng hoặc tại hệ thống truy vấn

Micrometer thường ghi nhận Counter dưới dạng số đếm tích lũy. Tốc độ sự kiện (rate) được suy ra từ mức tăng của counter trong một khoảng thời gian. Có hai nơi có thể thực hiện phép tính này: ngay trong ứng dụng hoặc tại hệ thống truy vấn metrics như Prometheus.

Tính ở ứng dụng tạo ra một giá trị rate đã được tổng hợp theo cửa sổ mà ứng dụng chọn. Tính ở hệ thống truy vấn giữ counter tích lũy làm dữ liệu gốc và cho phép người vận hành chọn cửa sổ, nhóm instance hoặc chiều phân tích khi truy vấn. Với hệ thống phân tán, cách thứ hai thường linh hoạt và dễ tổng hợp hơn. Tính tại ứng dụng phù hợp khi chính ứng dụng cần một tốc độ cục bộ hoặc cần xuất một chỉ số rate đã được định nghĩa rõ.

## 1. Counter là dữ liệu gốc để tính tốc độ

Counter biểu diễn số sự kiện tích lũy. Nó tăng khi sự kiện xảy ra và không giảm trong vòng đời của process.

~~~java
Counter ordersCreated = Counter.builder("orders.created")
    .description("Tổng số đơn hàng được tạo")
    .register(registry);

public void orderCreated() {
    ordersCreated.increment();
}
~~~

Nếu trong 10 giây counter tăng từ 100 lên 150, tốc độ trung bình trong khoảng đó là:

\[
rate = \frac{150 - 100}{10} = 5 \text{ sự kiện/giây}
\]

Counter chỉ cung cấp tổng số lần xảy ra. Nó không tự biểu diễn số sự kiện mỗi giây. Hệ thống truy vấn cần ít nhất hai mẫu counter theo thời gian để tính tốc độ.

Không nên tự tăng counter theo giá trị tốc độ. Ví dụ, nếu mỗi giây có 5 đơn hàng thì vẫn gọi increment() năm lần khi có năm sự kiện. Không ghi 5 vào một counter theo lịch, vì như vậy counter không còn đại diện cho tổng sự kiện.

## 2. Tính rate tại hệ thống truy vấn

Với backend hỗ trợ truy vấn theo chuỗi thời gian, ứng dụng chỉ cần xuất counter tích lũy. Backend tính mức tăng trong cửa sổ thời gian được chọn.

Ví dụ Prometheus:

~~~promql
rate(orders_created_total[5m])
~~~

Biểu thức trên tính tốc độ trung bình mỗi giây trong cửa sổ 5 phút. Tên series thực tế phụ thuộc registry và quy tắc chuyển đổi tên của Prometheus; hãy kiểm tra endpoint scrape để xác nhận tên metric đã xuất.

Có thể nhóm tốc độ theo một chiều tag:

~~~promql
sum by (channel) (
  rate(orders_created_total[5m])
)
~~~

Kết quả là tổng tốc độ tạo đơn hàng theo channel trên tất cả series được chọn, chẳng hạn web, mobile và partner.

### Vì sao phải tính rate trước khi sum?

Mỗi instance có một counter riêng. Khi instance khởi động lại, counter của instance đó có thể trở về 0. Prometheus nhận diện counter reset khi tính rate trên từng series.

Vì vậy, nên tính rate cho từng series trước, sau đó mới tổng hợp:

~~~promql
sum by (service) (
  rate(orders_created_total[5m])
)
~~~

Cách này cho phép rate() xử lý reset của từng counter độc lập trước khi cộng kết quả.

Không nên cộng các counter của nhiều instance trước rồi mới tính rate, vì phép tổng hợp có thể che mất reset của một instance và tạo ra mức giảm giả trong chuỗi tổng hợp.

### rate, irate và increase

| Hàm | Ý nghĩa | Dùng khi |
|---|---|---|
| rate(counter[5m]) | Tốc độ trung bình mỗi giây trong cửa sổ | Dashboard và alert ổn định |
| irate(counter[5m]) | Tốc độ tức thời dựa trên hai mẫu gần nhất | Quan sát thay đổi ngắn hạn, chấp nhận nhiễu |
| increase(counter[1h]) | Tổng mức tăng trong cửa sổ một giờ | Đếm số sự kiện trong khoảng thời gian |

Ví dụ:

~~~promql
increase(orders_created_total[1h])
~~~

Biểu thức này ước tính số đơn hàng được tạo trong một giờ gần nhất. Kết quả có thể là số thập phân vì Prometheus nội suy theo thời gian giữa các mẫu; nếu cần số lượng nghiệp vụ chính xác, hãy đọc dữ liệu giao dịch có thẩm quyền.

Cửa sổ 5 phút làm mượt dao động ngắn hạn. Cửa sổ 30 giây phản ứng nhanh hơn nhưng dễ biến động và nhạy với chu kỳ scrape. Chọn cửa sổ theo mục tiêu dashboard hoặc cảnh báo, đồng thời bảo đảm cửa sổ có đủ mẫu.

## 3. Counter reset khi ứng dụng khởi động lại

Counter trong một process thường bắt đầu lại từ 0 sau khi process khởi động lại. Đây là hành vi bình thường, không phải lỗi của Micrometer.

Ví dụ một instance có các mẫu:

~~~text
Thời điểm       Counter
10:00:00        100
10:00:15        120
10:00:30        140
10:00:45          3   <- process khởi động lại
10:01:00         18
~~~

Nếu chỉ lấy hiệu số 18 - 140, kết quả là -122 và không có ý nghĩa là tốc độ sự kiện. Hàm rate dành cho counter sẽ nhận diện reset và ước lượng mức tăng phù hợp qua lần reset.

Đây là một lý do quan trọng để giữ counter tích lũy ở ứng dụng và để backend có khả năng xử lý reset. Nếu ứng dụng tự tính rate rồi xuất Gauge, backend không thể tự khôi phục các sự kiện đã xảy ra trước khi process restart.

Rate tại ứng dụng thường trở về 0 hoặc bắt đầu lại khi process khởi động. Nếu dashboard tổng hợp nhiều instance, các rate cục bộ có thể được cộng, nhưng phải hiểu rằng mỗi instance đang tính theo cửa sổ và thời điểm riêng.

## 4. Tính rate ngay trong ứng dụng

Có những trường hợp ứng dụng cần một tốc độ cục bộ đã được tính sẵn, ví dụ:

- Hiển thị tốc độ xử lý trong một endpoint nội bộ.
- Theo dõi throughput cục bộ của một worker pool.
- Xuất một Gauge rate để hệ thống giám sát đọc trực tiếp.
- Tính thống kê theo cửa sổ nghiệp vụ cố định mà backend không cung cấp thuận tiện.

Khi đó, ứng dụng phải giữ số sự kiện trong cửa sổ, đo thời gian thực đã trôi qua và cập nhật một giá trị rate. Gauge chỉ đọc giá trị rate đã tính; không nên để hàm Gauge tự thay đổi trạng thái hoặc tính delta có side effect khi backend scrape.

Ví dụ dưới đây tính tốc độ trung bình giữa hai lần lấy mẫu định kỳ:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.LongAdder;

@Component
public class LocalOrderRate {
    private final Counter totalCreated;
    private final LongAdder eventsSinceSample = new LongAdder();

    private volatile double eventsPerSecond;
    private long lastSampleNanos = System.nanoTime();

    public LocalOrderRate(MeterRegistry registry) {
        this.totalCreated = Counter.builder("orders.created")
            .description("Tổng số đơn hàng được tạo")
            .register(registry);

        Gauge.builder(
                "orders.created.rate.local",
                this,
                LocalOrderRate::eventsPerSecond
            )
            .description("Tốc độ tạo đơn hàng cục bộ")
            .register(registry);
    }

    public void recordCreated() {
        totalCreated.increment();
        eventsSinceSample.increment();
    }

    public double eventsPerSecond() {
        return eventsPerSecond;
    }

    @Scheduled(fixedDelay = 1000)
    public void refreshRate() {
        long now = System.nanoTime();
        long elapsedNanos = now - lastSampleNanos;

        if (elapsedNanos <= 0) {
            return;
        }

        long count = eventsSinceSample.sumThenReset();
        eventsPerSecond =
            count * 1_000_000_000.0 / elapsedNanos;

        lastSampleNanos = now;
    }
}
~~~

Để kích hoạt @Scheduled, ứng dụng cần bật scheduling, ví dụ bằng @EnableScheduling trên một cấu hình Spring.

Trong ví dụ:

- Counter orders.created giữ tổng số đơn hàng đã tạo.
- LongAdder eventsSinceSample tích lũy số sự kiện kể từ lần lấy mẫu gần nhất.
- refreshRate() đọc số sự kiện, chia cho thời gian thực đã trôi qua và lưu rate mới.
- Gauge orders.created.rate.local chỉ đọc trường eventsPerSecond đã được cập nhật.

Dùng System.nanoTime() để đo khoảng thời gian đã trôi qua. Không dùng System.currentTimeMillis() cho phép tính duration vì đồng hồ hệ thống có thể được điều chỉnh bởi NTP hoặc thao tác quản trị.

### Vì sao phải chia cho thời gian thực đã trôi qua?

Lịch chạy mỗi giây không bảo đảm phương thức luôn được gọi đúng mỗi 1.000 ms. Thread có thể bị trì hoãn bởi tải CPU, GC hoặc scheduler.

Công thức nên là:

\[
rate = \frac{eventCount \times 10^9}{elapsedNanos}
\]

Nếu scheduler thực tế mất 1,2 giây giữa hai lần lấy mẫu, chia cho 1 giây sẽ làm rate cao hơn thực tế. Dùng elapsedNanos đo bằng nanoTime giúp phản ánh đúng khoảng thời gian quan sát.

LongAdder phù hợp khi nhiều thread cập nhật số sự kiện đồng thời. sumThenReset() lấy tổng hiện tại và đặt bộ đếm về 0. Khi có cập nhật đúng lúc reset, một số sự kiện có thể thuộc cửa sổ trước hoặc sau; đây là ước lượng rate theo cửa sổ, không phải phép chụp trạng thái tuyệt đối đồng bộ với từng sự kiện.

### Cẩn thận với vòng đời và ý nghĩa của rate

Gauge chỉ đọc giá trị gần nhất mà scheduler đã tính. Nếu scheduler dừng, giá trị có thể bị cũ nhưng vẫn được xuất. Trong môi trường Spring, hãy bảo đảm scheduler và bean có vòng đời phù hợp.

Rate cục bộ cũng chỉ đại diện cho process hiện tại. Nếu có 10 instance, mỗi instance xuất một rate riêng. Muốn tốc độ toàn hệ thống, có thể cộng các rate cục bộ nếu chúng cùng định nghĩa và cùng đơn vị, nhưng cách này mất khả năng xử lý counter reset từ dữ liệu gốc và có thể có sai lệch do cửa sổ lấy mẫu khác nhau. Thông thường, giữ counter của từng instance và tính rate ở backend sẽ đáng tin cậy hơn.

## 5. So sánh tính rate tại ứng dụng và tại query system

| Tiêu chí | Tính tại ứng dụng | Tính tại hệ thống truy vấn |
|---|---|---|
| Dữ liệu xuất | Rate đã tính, thường là Gauge | Counter tích lũy |
| Cửa sổ thời gian | Thường cố định theo code hoặc scheduler | Người dùng truy vấn có thể chọn |
| Restart process | Rate state thường reset | Backend xử lý counter reset |
| Tổng hợp nhiều instance | Phải cộng các rate cục bộ | Tính rate từng series rồi sum |
| Thay đổi dashboard | Cần sửa code nếu muốn cửa sổ khác | Thay truy vấn |
| Chi phí ứng dụng | Có bộ đếm cửa sổ và scheduler | Thấp hơn, chỉ tăng counter |
| Độ chính xác | Phụ thuộc cửa sổ và cách lấy mẫu | Phụ thuộc scrape interval và thuật toán backend |
| Dùng phù hợp | Rate cục bộ hoặc logic nội bộ cần sẵn giá trị | Dashboard, alert và phân tích toàn hệ thống |

Đối với metrics vận hành thông thường, nên ưu tiên xuất counter tích lũy và tính rate tại backend. Tính tại ứng dụng khi có yêu cầu rõ ràng về rate cục bộ hoặc cửa sổ nghiệp vụ mà backend không đáp ứng.

## 6. Chọn cửa sổ thời gian

Rate không có ý nghĩa nếu không nói rõ cửa sổ tính. Cùng một counter có thể có nhiều tốc độ khác nhau tùy khoảng quan sát.

Giả sử counter tăng 600 sự kiện trong 5 phút:

\[
rate_{5m} = \frac{600}{300} = 2 \text{ sự kiện/giây}
\]

Trong một phút cuối có 240 sự kiện:

\[
rate_{1m} = \frac{240}{60} = 4 \text{ sự kiện/giây}
\]

Hai kết quả đều đúng nhưng mô tả hai khoảng thời gian khác nhau. Dashboard nên ghi rõ cửa sổ hoặc đặt tên panel để người xem không nhầm rate trung bình dài hạn với tốc độ gần nhất.

Các nguyên tắc chọn cửa sổ:

- Cửa sổ dài hơn làm mượt dao động và phù hợp dashboard tổng quan.
- Cửa sổ ngắn hơn phản ứng nhanh nhưng dễ nhiễu khi traffic thấp.
- Cửa sổ phải đủ dài để chứa nhiều mẫu scrape.
- Alert cần cân bằng độ nhạy và nguy cơ cảnh báo do dao động ngắn.
- So sánh các dịch vụ phải dùng cùng định nghĩa cửa sổ và cùng đơn vị.

Với Prometheus, rate() cần nhiều hơn một mẫu trong range vector. Nếu cửa sổ quá ngắn so với scrape interval, biểu thức có thể không có đủ mẫu để tính.

## 7. Rate theo instance, route và outcome

Counter thường có tag như service, method, route hoặc outcome. Khi truy vấn, có thể giữ hoặc loại bỏ các chiều để trả lời câu hỏi vận hành.

Tốc độ theo route:

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

Tốc độ lỗi theo service:

~~~promql
sum by (service) (
  rate(http_server_requests_seconds_count{status=~"5.."}[5m])
)
~~~

Tỷ lệ lỗi trên tổng request:

~~~promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
~~~

Biểu thức tỷ lệ lỗi cần xử lý trường hợp mẫu số bằng 0 trong dashboard hoặc alert. Tên metric và tag thực tế phụ thuộc cấu hình Spring Boot, Micrometer và registry; kiểm tra dữ liệu scrape trước khi dùng truy vấn.

Chỉ nhóm theo tag có cardinality hữu hạn. Route nên là route template như /orders/{id}, không phải URL chứa ID thực. Không đưa request ID, user ID hoặc dữ liệu tự do vào tag chỉ để tạo chiều phân tích.

## 8. Tốc độ không giống tổng số lượng

Ba truy vấn sau trả lời ba câu hỏi khác nhau:

~~~promql
rate(orders_created_total[5m])
~~~

Số sự kiện trung bình mỗi giây trong 5 phút gần nhất.

~~~promql
increase(orders_created_total[1h])
~~~

Số sự kiện ước tính tăng trong một giờ gần nhất.

~~~promql
orders_created_total
~~~

Tổng counter hiện tại của từng series, thường từ lúc process khởi động hoặc từ khi nguồn đếm được khởi tạo.

Không dùng giá trị counter hiện tại để so sánh throughput giữa các instance đã chạy trong thời gian khác nhau. Instance chạy lâu hơn có thể có counter lớn hơn dù tốc độ hiện tại thấp hơn.

Nếu cần throughput, dùng rate. Nếu cần số lượng trong khoảng, dùng increase. Nếu cần tổng tích lũy của process, đọc counter.

## 9. Kiểm thử tính rate

Khi tính rate ở ứng dụng, nên kiểm thử logic bằng clock có thể điều khiển hoặc tách phần tính toán ra khỏi scheduler để không phụ thuộc thời gian thực.

Ví dụ kiểm thử một hàm thuần tính rate:

~~~java
static double calculateRate(long eventCount, long elapsedNanos) {
    if (elapsedNanos <= 0) {
        throw new IllegalArgumentException("elapsedNanos must be positive");
    }
    return eventCount * 1_000_000_000.0 / elapsedNanos;
}
~~~

Một số trường hợp cần kiểm tra:

- 100 sự kiện trong 10 giây cho kết quả 10 sự kiện/giây.
- Không có sự kiện trong cửa sổ cho kết quả 0.
- elapsedNanos bằng 0 hoặc âm phải được xử lý rõ.
- Scheduler bị trễ thì phép tính vẫn dùng thời gian thực đã trôi qua.
- Nhiều thread cùng tăng bộ đếm không làm mất phần lớn sự kiện.
- Process restart làm rate cục bộ bắt đầu lại theo đúng chính sách.

Với query system, nên kiểm thử PromQL hoặc truy vấn backend trên dữ liệu có counter reset. Xác minh rate được tính cho từng series trước khi sum, cửa sổ có đủ mẫu và kết quả có đơn vị mong muốn.

## 10. Các lỗi thường gặp

- **Tính hiệu số counter mà không xử lý reset:** restart có thể làm rate âm hoặc sai.
- **Cộng counter nhiều instance trước khi tính rate:** có thể che mất reset của từng series.
- **Dùng Gauge để lưu tổng sự kiện:** Counter phù hợp với số đếm tích lũy.
- **Tính rate bằng currentTimeMillis:** đồng hồ tường có thể nhảy; dùng nanoTime cho elapsed time.
- **Giả định scheduler chạy đúng mỗi giây:** phải chia cho elapsed time thực tế.
- **Để hàm Gauge có side effect:** scrape có thể gọi hàm nhiều lần hoặc vào thời điểm không dự kiến; Gauge chỉ nên đọc snapshot.
- **Dùng rate cục bộ làm tốc độ toàn hệ thống:** mỗi process chỉ biết phần việc của nó.
- **Chọn cửa sổ quá ngắn:** thiếu mẫu và tạo rate nhiễu.
- **Nhầm rate với increase:** một đại lượng là tốc độ mỗi giây, đại lượng kia là tổng mức tăng trong cửa sổ.
- **Xuất cả rate cục bộ và rate backend nhưng không phân biệt:** dashboard có thể so sánh hai cửa sổ hoặc semantics khác nhau.

## 11. Checklist lựa chọn

- [ ] Xác định cần tốc độ cục bộ hay tốc độ toàn hệ thống.
- [ ] Giữ Counter tích lũy làm dữ liệu gốc cho sự kiện.
- [ ] Ưu tiên rate() tại backend cho dashboard và alert phân tán.
- [ ] Tính rate tại ứng dụng chỉ khi có nhu cầu cụ thể.
- [ ] Dùng System.nanoTime() để đo thời gian đã trôi qua.
- [ ] Chia cho elapsed time thực tế thay vì giả định lịch chạy chính xác.
- [ ] Gauge rate chỉ đọc snapshot đã tính, không tự thay đổi trạng thái.
- [ ] Xử lý restart và cửa sổ lấy mẫu rõ ràng.
- [ ] Tính rate từng series trước khi tổng hợp nhiều instance.
- [ ] Chọn cửa sổ phù hợp với scrape interval và mục tiêu vận hành.
- [ ] Phân biệt rate, increase và giá trị counter tích lũy.
- [ ] Dùng tag có cardinality hữu hạn khi nhóm truy vấn.

Micrometer cung cấp counter nhất quán để ghi nhận sự kiện. Ứng dụng có thể tính rate cục bộ bằng cửa sổ và đồng hồ monotonic, còn hệ thống truy vấn có thể suy ra rate linh hoạt từ counter tích lũy. Chọn nơi tính dựa trên phạm vi cần quan sát: một process hay toàn bộ hệ thống. Với dashboard và cảnh báo phân tán, giữ counter làm nguồn dữ liệu và tính rate ở backend thường giúp xử lý reset, tổng hợp instance và thay đổi cửa sổ thuận tiện hơn.

