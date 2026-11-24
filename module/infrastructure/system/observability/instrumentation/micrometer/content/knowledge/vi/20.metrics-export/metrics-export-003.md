# StatsD registry và ý nghĩa của giao thức gửi tới bộ gom số liệu

StatsD là giao thức metrics nhẹ, thường dùng để gửi số liệu từ ứng dụng đến một tiến trình agent hoặc aggregator. Micrometer cung cấp StatsdMeterRegistry để chuyển Counter, Gauge, Timer và các meter khác thành các dòng dữ liệu theo dialect StatsD rồi gửi đến địa chỉ đã cấu hình.

Khác với Prometheus pull, StatsD thường hoạt động theo mô hình push: ứng dụng gửi dữ liệu đến StatsD agent, agent gom các mẫu trong một khoảng thời gian rồi chuyển tiếp đến backend. Vì vậy, cần hiểu rõ ba thành phần: registry trong ứng dụng, giao thức truyền từ ứng dụng đến agent và cơ chế flush/forward từ agent đến hệ thống lưu trữ.

## 1. Kiến trúc gửi metrics qua StatsD

Luồng cơ bản:

~~~mermaid
flowchart LR
    A["Mã ứng dụng"] --> B["Micrometer MeterRegistry"]
    B --> C["StatsD registry"]
    C -->|"UDP hoặc TCP"| D["StatsD agent / aggregator"]
    D --> E["Backend metrics"]
    E --> F["Dashboard / Alert"]
~~~

Mã nghiệp vụ ghi nhận meter thông qua API Micrometer. StatsD registry chuyển meter thành các dòng theo định dạng StatsD và gửi đến agent. Agent nhận các dòng, tổng hợp số liệu theo quy tắc của nó, sau đó flush hoặc forward đến backend.

Trong triển khai phổ biến, agent chạy gần ứng dụng, chẳng hạn trên cùng host, trong sidecar container hoặc daemon của node. Ứng dụng chỉ cần biết host và port của agent. Backend cuối cùng có thể là một hệ thống giám sát hoặc nền tảng metrics khác mà agent hỗ trợ.

StatsD agent không nhất thiết là backend lưu trữ cuối cùng. Nó thường là điểm nhận trung gian để giảm phụ thuộc mạng của ứng dụng và thực hiện aggregation trước khi chuyển tiếp.

## 2. StatsD line protocol

StatsD cổ điển dùng dòng văn bản có cấu trúc đơn giản:

~~~text
<metric_name>:<value>|<type>
~~~

Ví dụ:

~~~text
orders.created:1|c
orders.queue.depth:12|g
orders.create.duration:25|ms
~~~

Trong đó:

- metric_name là tên metric.
- value là giá trị được gửi.
- type cho biết loại dữ liệu, ví dụ c cho counter, g cho gauge và ms cho timing trong dialect StatsD cổ điển.

StatsD có nhiều biến thể. Một số dialect bổ sung sampling rate, tags hoặc kiểu dữ liệu khác. Do đó, dòng dữ liệu cụ thể phụ thuộc flavor được cấu hình trong Micrometer.

### Các loại dữ liệu thường gặp

| Loại meter Micrometer | Ý nghĩa khi gửi | Ví dụ cách biểu diễn StatsD |
| --- | --- | --- |
| Counter | Lượng sự kiện tăng thêm | orders.created:1\|c |
| Gauge | Giá trị trạng thái tại thời điểm gửi | orders.queue.depth:12\|g |
| Timer | Thời gian thực hiện và thống kê liên quan | Dạng timing, thường dùng hậu tố ms trong dialect cổ điển |
| DistributionSummary | Phân phối của một đại lượng như kích thước payload | Dạng histogram/distribution tùy flavor và agent |

Các ví dụ chỉ minh họa cú pháp phổ biến. Cách Micrometer chuyển Timer hoặc DistributionSummary thành một hay nhiều dòng, cũng như agent tổng hợp chúng ra sao, phụ thuộc StatsD flavor và tính năng của receiver.

## 3. Chọn StatsD flavor tương thích với agent

StatsD không có một định dạng mở rộng duy nhất được mọi agent triển khai giống hệt nhau. Micrometer cho phép chọn flavor để tạo dòng dữ liệu phù hợp với receiver.

Các flavor thường gặp:

| Flavor | Đặc điểm | Khi nào dùng |
| --- | --- | --- |
| Etsy | Giao thức StatsD cổ điển, cú pháp metric/value/type cơ bản | Agent tương thích StatsD truyền thống |
| Datadog | Hỗ trợ phần mở rộng DogStatsD, gồm tags theo định dạng Datadog | Datadog Agent hoặc receiver tương thích DogStatsD |
| Telegraf | Dialect được hỗ trợ bởi StatsD input plugin của Telegraf | Telegraf đang làm agent nhận và chuyển tiếp |

Ví dụ, Datadog flavor có thể biểu diễn tags theo dạng:

~~~text
orders.created:1|c|#service:order-service,channel:web
~~~

Agent cần hỗ trợ đúng phần mở rộng này mới hiểu được tags. Nếu gửi cú pháp Datadog đến một agent chỉ hiểu StatsD cổ điển, phần tags có thể bị bỏ qua hoặc dòng dữ liệu bị xử lý sai.

Hãy chọn flavor dựa trên tài liệu của agent đang chạy, không chỉ dựa trên backend cuối cùng. Nếu Telegraf nhận dữ liệu rồi chuyển tiếp sang một backend khác, receiver trực tiếp vẫn là Telegraf StatsD input plugin.

## 4. UDP và TCP: ý nghĩa của giao thức truyền

StatsD thường dùng UDP vì datagram nhỏ, không cần thiết lập kết nối và có chi phí thấp. Micrometer cũng có thể được cấu hình dùng TCP nếu agent hỗ trợ.

| Tiêu chí | UDP | TCP |
| --- | --- | --- |
| Kiểu truyền | Datagram độc lập | Luồng byte có kết nối |
| Xác nhận nhận dữ liệu | Không có ACK ở tầng UDP | TCP xác nhận truyền ở tầng vận chuyển |
| Độ tin cậy | Có thể mất gói mà sender không biết | Tin cậy hơn trong phạm vi kết nối, nhưng vẫn có thể lỗi khi kết nối đứt |
| Overhead | Thấp, phù hợp metric packet nhỏ | Cao hơn do kết nối và quản lý luồng |
| Backpressure | Không có cơ chế backpressure trực tiếp từ receiver qua UDP | Có thể phát sinh backpressure khi receiver hoặc network chậm |
| Phù hợp | Agent cục bộ, metric không yêu cầu bảo đảm từng packet | Môi trường cần truyền tin cậy hơn và agent hỗ trợ TCP |

### UDP: nhanh và best-effort

Với UDP, ứng dụng gửi datagram đến agent mà không chờ xác nhận từng packet. Nếu agent dừng, mạng mất gói, buffer đầy hoặc datagram bị loại, ứng dụng thường không biết chính xác metric nào đã mất.

Ưu điểm là thao tác gửi nhẹ và không cần giữ kết nối. Đây là lý do UDP thường phù hợp với agent chạy trên cùng host hoặc node. Tuy nhiên, không nên dùng StatsD/UDP làm kênh lưu trữ giao dịch hoặc dữ liệu cần bảo đảm không mất.

### TCP: có xác nhận truyền nhưng có thể gây chờ

TCP bảo đảm thứ tự byte và truyền lại trong phạm vi kết nối khi có lỗi mạng có thể khắc phục. Tuy nhiên, ứng dụng có thể bị ảnh hưởng khi agent không đọc kịp, kết nối bị reset hoặc quá trình gửi bị chặn bởi backpressure.

TCP không bảo đảm dữ liệu đã được backend lưu bền vững. Nó chỉ cung cấp độ tin cậy ở tầng transport giữa sender và receiver. Nếu agent nhận dữ liệu rồi gặp lỗi trước khi flush đến backend, vẫn có thể mất metrics.

Chỉ chọn TCP khi StatsD agent thực sự mở listener TCP và hỗ trợ đúng dialect. Không đổi protocol trong ứng dụng mà không thay cấu hình receiver tương ứng.

## 5. Thêm dependency StatsD registry

Với Spring Boot, thêm Actuator và registry StatsD:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-statsd")
}
~~~

Nên để Spring Boot BOM quản lý phiên bản Micrometer để các module cùng phiên bản tương thích. Registry được auto-configure khi dependency có mặt và cấu hình export phù hợp.

Mã nghiệp vụ tiếp tục sử dụng MeterRegistry, không cần biết metrics sẽ được gửi bằng UDP hay TCP:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderMetrics {

    private final MeterRegistry registry;

    public OrderMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordCreated(String channel) {
        registry.counter(
            "orders.created",
            "channel", channel
        ).increment();
    }
}
~~~

Trong ứng dụng thực tế, channel phải được chuẩn hóa về tập giá trị hữu hạn như web, mobile, partner hoặc other. Không đưa mã đơn hàng hay request ID vào tag.

## 6. Cấu hình StatsD trong Spring Boot

Ví dụ application.yml cho agent Datadog-compatible chạy cùng network với ứng dụng:

~~~yaml
management:
  statsd:
    metrics:
      export:
        enabled: true
        host: statsd-agent
        port: 8125
        protocol: udp
        flavor: datadog
        step: 30s
        max-packet-length: 1400
~~~

Ý nghĩa các thuộc tính:

| Thuộc tính | Vai trò |
| --- | --- |
| enabled | Bật hoặc tắt StatsD export |
| host | Host hoặc địa chỉ của StatsD agent |
| port | Port agent đang lắng nghe |
| protocol | Chọn udp hoặc tcp theo receiver |
| flavor | Chọn dialect như etsy, datadog hoặc telegraf |
| step | Chu kỳ publish của registry |
| max-packet-length | Giới hạn độ dài packet theo khả năng cấu hình của registry |

Tên property và giá trị mặc định có thể thay đổi theo phiên bản Spring Boot/Micrometer. Đối chiếu configuration metadata của phiên bản dự án trước khi dùng; chỉ khai báo thuộc tính mà phiên bản registry thực sự hỗ trợ.

Nếu agent chỉ hỗ trợ StatsD cổ điển qua UDP, hãy chọn flavor etsy và protocol udp. Nếu dùng Telegraf, xác nhận StatsD input plugin đang bật đúng protocol, port và dialect mà registry sẽ gửi.

## 7. Step của Micrometer khác flush interval của agent

Đây là hai chu kỳ khác nhau:

1. Micrometer step: khoảng thời gian registry thu thập và publish dữ liệu từ ứng dụng đến StatsD agent.
2. Agent flush interval: khoảng thời gian agent gom dữ liệu đã nhận và chuyển tiếp đến backend.

Ví dụ:

~~~text
Ứng dụng / Micrometer        StatsD Agent              Backend
        |                         |                       |
        |-- publish step 30s ---->|                       |
        |                         |-- aggregate/flush ---->|
        |                         |     theo 10s           |
        |                         |                       |
~~~

Nếu Micrometer publish mỗi 30 giây và agent flush mỗi 10 giây, agent vẫn chỉ có dữ liệu mới sau khi ứng dụng gửi batch tiếp theo. Flush interval ngắn không làm ứng dụng gửi metrics thường xuyên hơn.

| Cấu hình | Ảnh hưởng |
| --- | --- |
| Giảm Micrometer step | Ứng dụng gửi thường xuyên hơn, dữ liệu đến agent nhanh hơn và overhead gửi tăng |
| Tăng Micrometer step | Ít lần gửi hơn nhưng dữ liệu cập nhật chậm hơn |
| Giảm agent flush interval | Agent chuyển dữ liệu đã nhận đến backend thường xuyên hơn |
| Tăng agent flush interval | Agent gom lâu hơn, giảm tần suất forward nhưng tăng độ trễ hiển thị |

Chọn hai chu kỳ độc lập theo yêu cầu freshness, tải mạng và khả năng xử lý của agent/backend.

## 8. Packet length, buffering và giới hạn UDP

UDP datagram có giới hạn kích thước thực tế phụ thuộc mạng và cấu hình socket. Packet quá lớn có thể bị phân mảnh IP; khi một mảnh bị mất, toàn bộ datagram không thể được tái lắp ráp. Một số agent hoặc network policy cũng giới hạn kích thước packet nhận.

max-packet-length giúp registry giới hạn độ dài packet theo khả năng cấu hình của nó. Không nên đặt giá trị lớn tùy tiện để gom thật nhiều metric vào một packet.

Các yếu tố ảnh hưởng packet size:

- Số lượng meter được publish trong một step.
- Số tags của từng meter.
- Độ dài metric name và tag values.
- Histogram hoặc distribution tạo thêm nhiều số liệu.
- Flavor có cú pháp tags dài hơn.

Nếu packet bị cắt hoặc vượt giới hạn, một số metric có thể không đến được agent. Hãy kiểm tra log/metrics của agent, packet size và cấu hình registry. Với lượng dữ liệu lớn, cân nhắc giảm cardinality, điều chỉnh step, giới hạn packet phù hợp hoặc chọn transport/collector phù hợp hơn.

## 9. Aggregation ở StatsD agent

StatsD agent thường nhận các mẫu và gom theo metric name cùng dimensions trong một khoảng flush. Chi tiết aggregation phụ thuộc implementation:

- Counter thường được cộng các delta nhận được trong khoảng.
- Gauge thường giữ hoặc chuyển giá trị mới nhất theo quy tắc của agent.
- Timing/histogram có thể được tổng hợp thành count, sum, mean, percentile hoặc bucket.
- Sampling rate, tags và kiểu metric mở rộng phụ thuộc flavor.

Không giả định mọi StatsD agent tính percentile hoặc histogram giống nhau. Nếu dashboard cần p95/p99, hãy xác nhận agent hỗ trợ timing aggregation tương ứng và cấu hình flush/retention phù hợp.

Với counter, cần hiểu semantics delta. Registry gửi phần phát sinh trong step; agent cộng các delta nhận được. Không diễn giải mỗi packet counter như một tổng tích lũy kể từ khi ứng dụng khởi động.

Với gauge, nếu ứng dụng gửi giá trị 12 rồi không gửi lại trong thời gian dài, backend có thể tiếp tục hiển thị giá trị cuối cùng hoặc coi series đã cũ tùy agent và backend. Vì vậy, cần xác định cách xử lý stale metrics ở hệ thống nhận.

## 10. Tags, naming và cardinality

StatsD cổ điển không có tags chuẩn như mọi flavor mở rộng. Datadog và một số dialect hỗ trợ tags; cách mã hóa khác nhau theo flavor. Dù agent hỗ trợ tags, cardinality vẫn cần được kiểm soát.

Nên dùng:

- service=order-service
- environment=production
- channel=web
- result=success
- operation=create

Tránh:

- order_id
- request_id
- user_id
- email hoặc session ID
- URL thô chứa ID tài nguyên

Nếu agent không hỗ trợ tags hoặc đang dùng Etsy flavor, cần cân nhắc cách đặt tên metric theo quy ước của hệ thống. Không mã hóa giá trị động vào tên metric vì sẽ tạo số lượng series khó kiểm soát và làm truy vấn phức tạp.

## 11. Khi nào nên dùng StatsD?

StatsD phù hợp khi:

- Ứng dụng cần push metrics đến agent gần nó.
- Hệ thống giám sát đã có StatsD hoặc DogStatsD receiver.
- Muốn giảm phụ thuộc trực tiếp vào API của backend.
- Chấp nhận semantics aggregation và khả năng mất dữ liệu phù hợp với transport.
- Cần tích hợp nhanh với hệ thống legacy hoặc agent đang có.

Nên cân nhắc registry khác khi:

- Cần pull/scrape trực tiếp từ Prometheus.
- Cần telemetry OTLP chuẩn hóa để đi qua OpenTelemetry Collector.
- Cần bảo đảm delivery hoặc lưu trữ bền vững cho từng sự kiện.
- Cần histogram/percentile với semantics chính xác và nhất quán qua nhiều backend nhưng agent StatsD hiện tại không hỗ trợ phù hợp.

StatsD là giao thức gửi metrics, không phải hàng đợi bền vững và cũng không phải hệ thống lưu trữ. Không dùng nó thay cho event log, audit trail hoặc dữ liệu giao dịch.

## 12. Xử lý lỗi gửi đến agent

| Dấu hiệu | Nguyên nhân cần kiểm tra |
| --- | --- |
| Không thấy metrics | Sai host/port, agent chưa chạy, sai flavor hoặc registry chưa publish |
| UDP gửi nhưng agent không nhận | Network policy, firewall, packet drop hoặc agent bind sai interface |
| TCP connection refused | Agent chưa bật TCP listener hoặc port sai |
| Metrics có tên lạ | Naming convention hoặc flavor không khớp |
| Tags biến mất | Agent không hỗ trợ flavor/tag syntax đã gửi |
| Một số metric bị thiếu | Packet quá dài, packet drop hoặc giới hạn parser |
| Counter tăng sai | Nhầm delta với cumulative hoặc agent aggregation không như kỳ vọng |
| Timer/p95 không xuất hiện | Agent chưa bật timing aggregation hoặc dialect không hỗ trợ kiểu đó |
| Backend cập nhật chậm | Micrometer step hoặc agent flush interval quá dài |

Quy trình điều tra:

1. Kiểm tra registry có được tạo và publish theo step không.
2. Xác minh host/port từ đúng container hoặc host chạy ứng dụng.
3. Kiểm tra agent có listener đúng UDP/TCP không.
4. Kiểm tra flavor và cú pháp tags.
5. Kiểm tra packet length, log và internal metrics của agent.
6. Kiểm tra agent có forward đến backend và backend có nhận series không.
7. So sánh thời điểm publish của Micrometer với flush interval của agent.

Với UDP, việc không nhận được packet không nhất thiết tạo exception ở ứng dụng. Do đó, cần theo dõi cả internal metrics của agent và một metric smoke test có tên dễ nhận biết.

## 13. Kiểm thử StatsD registry

Unit test với SimpleMeterRegistry kiểm tra logic instrumentation nhưng không kiểm tra giao thức StatsD. Để xác minh export, cần dùng StatsD receiver thử nghiệm hoặc agent test trong môi trường CI.

Một quy trình kiểm thử:

1. Khởi chạy receiver với đúng flavor và protocol dự kiến.
2. Khởi chạy ứng dụng với micrometer-registry-statsd.
3. Đăng ký một Counter, Gauge và Timer có tên dễ nhận diện.
4. Gọi thao tác nghiệp vụ để tạo số liệu.
5. Chờ ít nhất một Micrometer step.
6. Kiểm tra receiver nhận đúng dòng metric, tags và loại dữ liệu.
7. Nếu kiểm tra đường forward, xác nhận agent flush dữ liệu đến backend thử nghiệm.

Ví dụ mã instrumentation:

~~~java
Counter created = registry.counter(
    "orders.created",
    "channel", "web"
);

Timer duration = registry.timer(
    "orders.create.duration",
    "operation", "create"
);

created.increment();
duration.record(() -> orderService.create(command));
~~~

Receiver test cần kiểm tra cú pháp tương ứng với flavor đã cấu hình. Không dùng một assertion cố định cho mọi flavor vì cú pháp tags và biểu diễn timing có thể khác nhau.

## 14. Checklist triển khai

- [ ] Đã thêm micrometer-registry-statsd đúng phiên bản BOM.
- [ ] Đã xác định agent nhận trực tiếp và host/port có thể truy cập.
- [ ] Protocol UDP/TCP khớp với listener của agent.
- [ ] Flavor Etsy/Datadog/Telegraf khớp với parser của agent.
- [ ] Micrometer step được chọn theo yêu cầu độ mới dữ liệu.
- [ ] Agent flush interval được cấu hình độc lập.
- [ ] Packet length phù hợp với network và agent.
- [ ] Tags và metric names có cardinality được kiểm soát.
- [ ] Đã hiểu counter delta và quy tắc aggregation của agent.
- [ ] Đã kiểm thử metric thực tế qua receiver và đường forward.
- [ ] Có theo dõi packet drop, queue, lỗi parser và lỗi backend.

StatsD registry chuyển metrics của Micrometer thành dữ liệu theo dialect mà agent hiểu và gửi qua UDP hoặc TCP. UDP nhẹ nhưng best-effort; TCP có cơ chế truyền tin cậy hơn nhưng vẫn phụ thuộc receiver và backend. Micrometer step quyết định nhịp gửi từ ứng dụng, còn agent flush interval quyết định nhịp chuyển tiếp. Khi chọn đúng flavor, protocol, packet size và quy tắc aggregation, StatsD trở thành một đường export phù hợp cho hệ thống đã có agent/aggregator tương thích.
