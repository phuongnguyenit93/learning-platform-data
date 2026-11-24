# Giám sát bộ đệm kết nối cơ sở dữ liệu và giới hạn của dữ liệu được cung cấp

Connection pool giữ sẵn một nhóm kết nối cơ sở dữ liệu để ứng dụng có thể mượn và trả kết nối mà không phải thiết lập kết nối vật lý cho mọi thao tác. Pool giúp giảm chi phí tạo kết nối và giới hạn số kết nối đồng thời đến database. Tuy nhiên, pool cũng có thể trở thành điểm nghẽn: mọi kết nối đang được sử dụng, không còn kết nối rảnh và nhiều thread phải chờ.

Micrometer có thể công bố các phép đo có sẵn từ connection pool thông qua binder hoặc cơ chế tích hợp của framework. Những số liệu như số kết nối đang dùng, số kết nối rảnh, số thread đang chờ, thời gian lấy kết nối và số lần timeout giúp nhận biết tình trạng pool. Chúng không mô tả toàn bộ hoạt động của database và không tự chỉ ra câu SQL nào gây chậm.

## 1. Connection pool hoạt động như thế nào?

Khi ứng dụng cần truy cập database, nó yêu cầu một kết nối từ DataSource. Nếu pool có kết nối rảnh, kết nối được cấp cho caller. Khi caller đóng Connection, pool thường trả kết nối về pool thay vì đóng socket vật lý ngay lập tức.

Một pool điển hình quản lý:

- **Active connections:** kết nối đã được cấp cho ứng dụng và chưa được trả lại.
- **Idle connections:** kết nối đang nằm trong pool và có thể được cấp cho caller.
- **Pending threads:** số thread đang chờ được cấp kết nối vì chưa có kết nối rảnh.
- **Minimum size:** số kết nối tối thiểu pool cố gắng duy trì.
- **Maximum size:** giới hạn trên của số kết nối pool được phép tạo.

Luồng mượn và trả kết nối:

~~~mermaid
flowchart TD
    A[Ứng dụng yêu cầu Connection] --> B{Pool có kết nối rảnh?}
    B -->|Có| C[Cấp kết nối cho caller]
    B -->|Không| D{Còn chỗ tạo kết nối?}
    D -->|Có| E[Tạo kết nối mới]
    D -->|Không| F[Caller chờ trong giới hạn timeout]
    E --> C
    F -->|Có kết nối được trả| C
    F -->|Hết timeout| G[Phát sinh lỗi lấy kết nối]
    C --> H[Ứng dụng dùng Connection]
    H --> I[Đóng Connection logic]
    I --> J[Trả Connection về pool]
    J --> B
~~~

Connection pool quản lý việc cấp phát và tái sử dụng kết nối. Database vẫn thực hiện truy vấn, transaction, khóa và I/O; metric của pool chỉ phản ánh một phần quan sát ở phía ứng dụng.

## 2. Những metric thường có của connection pool

Với HikariCP, Micrometer có thể công bố các số đo thường gặp sau. Tên meter và cách chuẩn hóa thành tên của backend có thể thay đổi theo phiên bản Micrometer, Spring Boot và registry:

| Metric HikariCP | Ý nghĩa | Loại dữ liệu |
| --- | --- | --- |
| hikaricp.connections | Tổng số kết nối pool đang quản lý. | Gauge |
| hikaricp.connections.active | Số kết nối đang được ứng dụng mượn. | Gauge |
| hikaricp.connections.idle | Số kết nối hiện rảnh trong pool. | Gauge |
| hikaricp.connections.pending | Số thread đang chờ kết nối. | Gauge |
| hikaricp.connections.max | Giới hạn kết nối tối đa được cấu hình. | Gauge |
| hikaricp.connections.min | Mức kết nối tối thiểu được cấu hình. | Gauge |
| hikaricp.connections.acquire | Thời gian chờ để lấy được kết nối. | Timer |
| hikaricp.connections.usage | Thời gian một kết nối được giữ sau khi cấp cho caller. | Timer |
| hikaricp.connections.creation | Thời gian tạo kết nối vật lý. | Timer |
| hikaricp.connections.timeout | Số lần yêu cầu lấy kết nối hết thời gian chờ. | Counter |

Một số tích hợp chỉ công bố các metric chung của DataSource như active, idle, max và min. Metric pending, acquire, usage, creation hoặc timeout có thể phụ thuộc binder chuyên biệt của pool. Không nên giả định mọi DataSource đều cung cấp đầy đủ mọi trường.

### Metric chung và metric riêng của pool

Spring Boot Actuator có thể tự động thu thập metadata từ các loại DataSource được hỗ trợ và công bố nhóm metric chung, thường có tên dạng jdbc.connections.*. HikariCP còn có thể cung cấp các metric chuyên biệt, thường có tiền tố hikaricp.*.

Metric chung hữu ích khi ứng dụng có nhiều loại pool và muốn so sánh theo cùng một mô hình. Metric chuyên biệt hữu ích khi cần thêm thông tin mà API pool cụ thể cung cấp, chẳng hạn số thread đang chờ hoặc thời gian acquire.

Nếu dùng Spring Boot auto-configuration, hãy kiểm tra metric nào đã được đăng ký trước khi tự cấu hình MetricsTrackerFactory. Spring Boot có thể tự động công bố metric chung của DataSource và metric HikariCP; đăng ký thêm tracker thủ công vào cùng pool có thể tạo meter trùng hoặc gây xung đột cấu hình.

## 3. Tích hợp metric HikariCP với Micrometer

Trong ứng dụng Java tự cấu hình HikariCP, có thể gắn MetricsTrackerFactory của HikariCP với MeterRegistry:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.metrics.micrometer.MicrometerMetricsTrackerFactory;
import io.micrometer.core.instrument.MeterRegistry;

public final class DatabasePoolFactory {

    public HikariDataSource create(MeterRegistry registry) {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl("jdbc:postgresql://localhost:5432/orders");
        config.setUsername("app");
        config.setPassword("change-me");
        config.setPoolName("primary");
        config.setMaximumPoolSize(20);
        config.setMetricsTrackerFactory(
                new MicrometerMetricsTrackerFactory(registry));

        return new HikariDataSource(config);
    }
}
~~~

HikariCP cung cấp MetricsTrackerFactory riêng cho Micrometer. Khi cấu hình factory trước khi tạo HikariDataSource, pool tạo tracker và đăng ký các meter chuyên biệt vào registry. Cần giữ registry sống lâu hơn pool và đóng DataSource theo lifecycle của ứng dụng.

Trong Spring Boot, Actuator có thể tự động cấu hình metric cho DataSource được hỗ trợ. Trước khi tạo bean binder thủ công, kiểm tra endpoint metrics hoặc danh sách meter để tránh đăng ký trùng. Nếu cần cấu hình thủ công, hãy dùng một đường đăng ký duy nhất và giữ DataSource được quản lý bởi Spring.

Ví dụ cấu hình endpoint Prometheus trong Spring Boot:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Đoạn cấu hình chỉ expose endpoint nếu ứng dụng có dependency registry Prometheus và endpoint được cho phép bởi cấu hình bảo mật. Trong môi trường thật, không mở endpoint metrics công khai nếu nó chứa thông tin vận hành nội bộ.

## 4. Đặt tên pool và tag có kiểm soát

Khi ứng dụng có nhiều DataSource, cần phân biệt pool bằng tag ổn định như name hoặc pool. Ví dụ:

- pool=primary
- pool=reporting
- pool=warehouse

Tên pool nên được cấu hình rõ ràng trong ứng dụng. Không dùng user ID, tenant ID, request ID hoặc tên database được lấy từ input động làm tag. Mỗi tổ hợp tag tạo một series riêng và có thể làm cardinality tăng nhanh.

Nếu một service có ba pool cố định, tag pool giúp dashboard so sánh active, idle và pending giữa ba pool. Nếu hệ thống tạo hàng nghìn DataSource theo tenant, metrics tổng hợp theo loại pool hoặc nhóm workload thường phù hợp hơn việc tạo một series cho từng tenant.

## 5. Diễn giải active, idle và pending

Ba số đo này cần được đọc cùng nhau:

| Quan sát | Cách hiểu có thể có | Cần kiểm tra thêm |
| --- | --- | --- |
| Active thấp, idle cao, pending bằng 0 | Pool có dư khả năng phục vụ ở thời điểm lấy mẫu. | Mức sử dụng theo giờ cao điểm và cấu hình min/max. |
| Active gần max, idle bằng 0, pending tăng | Pool đang chịu áp lực; caller phải chờ kết nối. | Acquire latency, timeout, tốc độ tăng request và thời gian giữ Connection. |
| Active cao kéo dài nhưng pending bằng 0 | Nhiều kết nối đang được sử dụng, nhưng pool vẫn có thể đáp ứng nhu cầu hiện tại. | Transaction dài, code giữ Connection lâu, truy vấn chậm hoặc tải nền. |
| Active thấp nhưng pending cao | Có thể pool đang tạo kết nối chậm, kết nối bị lỗi hoặc snapshot metric không đồng thời. | Creation time, lỗi kết nối, database availability và log pool. |
| Idle bằng 0 trong một mẫu | Pool không có kết nối rảnh tại thời điểm đọc. | Xem xu hướng qua nhiều mẫu và pending; một mẫu đơn lẻ chưa đủ kết luận nghẽn. |

Active gần max không tự động có nghĩa pool bị nghẽn. Nếu pending bằng 0 và acquire latency vẫn thấp, pool có thể đang sử dụng hết công suất một cách bình thường. Dấu hiệu áp lực rõ hơn là active chạm giới hạn, idle cạn, pending tồn tại liên tục và thời gian acquire hoặc timeout tăng.

### Ước lượng tổng số kết nối

Trong một snapshot, tổng số kết nối đang được pool quản lý thường có thể ước lượng bằng active + idle. Tuy nhiên, các Gauge được đọc riêng lẻ; pool có thể thay đổi giữa các lần đọc nên tổng không phải lúc nào cũng là snapshot nguyên tử. Ngoài ra, một số implementation hoặc trạng thái chuyển tiếp có thể khiến cách tính khác biệt.

Không suy ra số kết nối toàn database bằng cách xem một pool. Database có thể nhận kết nối từ nhiều instance ứng dụng, job nền, công cụ quản trị và service khác.

## 6. Thời gian acquire không phải thời gian chạy SQL

Thời gian acquire phản ánh khoảng thời gian caller chờ pool cấp một Connection. Khoảng thời gian này có thể gồm:

- Chờ một kết nối đang được sử dụng được trả lại.
- Chờ pool tạo kết nối mới.
- Chờ các thao tác kiểm tra hoặc khởi tạo kết nối.
- Chi phí đồng bộ và lập lịch thread bên trong pool.

Nó không đo thời gian thực thi câu SQL sau khi Connection đã được cấp. Ví dụ:

- Acquire mất 5 ms, SQL mất 2 giây: pool cấp kết nối nhanh nhưng truy vấn hoặc database chậm.
- Acquire mất 800 ms, SQL mất 20 ms: ứng dụng có thể đang thiếu kết nối rảnh hoặc giữ Connection quá lâu ở nơi khác.
- Acquire và SQL đều chậm: có thể tồn tại đồng thời vấn đề pool và database.
- Usage kéo dài dù SQL span ngắn: kiểm tra logic ứng dụng hoặc thời gian chờ khác trong lúc Connection vẫn được giữ.

Để phân tích đầy đủ, kết hợp metric pool với Timer cho thời gian repository/service, tracing cho từng span và metric ở database. Không kết luận truy vấn SQL chậm chỉ từ acquire timer.

HikariCP còn có metric usage để đo khoảng thời gian Connection được giữ từ lúc cấp cho caller đến khi được trả lại pool. Usage dài có thể phản ánh transaction dài, nhiều câu SQL trong cùng một lần mượn kết nối hoặc code giữ Connection trong lúc làm việc khác. Nó vẫn không phải thời gian SQL thuần, vì khoảng đo có thể bao gồm toàn bộ thời gian caller giữ Connection.

## 7. Creation time và timeout count

Creation time đo thời gian pool tạo kết nối mới. Nếu chỉ số này tăng, cần xem xét DNS, TCP/TLS, xác thực, giới hạn kết nối của database hoặc tải trên database. Một pool thường tái sử dụng kết nối nên creation time không phải thời gian của mọi request.

Timeout count thường tăng khi caller không lấy được Connection trong thời gian chờ đã cấu hình. Đây là tín hiệu mạnh hơn việc chỉ thấy active cao, nhưng vẫn cần xem cùng pending, acquire latency và log exception.

Một timeout có thể xảy ra do:

- Pool đã đạt maximum size và các kết nối chưa được trả.
- Transaction hoặc thao tác giữ Connection quá lâu.
- Database chậm hoặc không chấp nhận kết nối mới.
- Pool không tạo được kết nối mới do lỗi mạng hoặc xác thực.
- Lưu lượng tăng đột biến vượt khả năng pool và database.

Không tăng maximum pool size ngay khi thấy timeout. Tăng pool có thể làm số kết nối đồng thời đến database cao hơn, gây tranh chấp CPU, memory, lock hoặc vượt giới hạn connection của database. Trước hết cần tìm nguyên nhân thời gian giữ Connection và năng lực thực tế của database.

## 8. Giới hạn của dữ liệu pool cung cấp

Metric pool rất hữu ích nhưng chỉ mô tả góc nhìn của pool tại ứng dụng. Các giới hạn quan trọng:

1. **Không phải metric truy vấn SQL:** active chỉ cho biết Connection đang được mượn; không nói câu SQL nào đang chạy.
2. **Không đo đầy đủ thời gian transaction:** Connection có thể được giữ trong lúc ứng dụng xử lý logic, gọi HTTP hoặc chờ lock.
3. **Không đại diện toàn database:** mỗi instance chỉ thấy pool của chính nó; database còn có các client khác.
4. **Không phải snapshot đồng thời:** active, idle và pending có thể được đọc ở các thời điểm rất gần nhưng không giống hệt nhau.
5. **Có thể bỏ lỡ đỉnh ngắn:** Prometheus chỉ scrape theo chu kỳ; một đợt pending ngắn giữa hai lần scrape có thể không xuất hiện.
6. **Phụ thuộc implementation:** pool khác nhau có API và metric khác nhau; generic DataSource metrics có thể không cung cấp pending hoặc timeout.
7. **Phụ thuộc trạng thái khởi tạo:** metric có thể chưa có trước khi pool được khởi tạo, hoặc không còn hữu ích sau khi pool đóng.
8. **Không giải thích nguyên nhân gốc:** metric cho biết triệu chứng; cần log, trace, database telemetry và kiểm tra cấu hình để tìm nguyên nhân.

Vì vậy, metric pool nên được xem là một phần của quan sát database access, không phải bộ chẩn đoán database hoàn chỉnh.

## 9. Gauge là ảnh chụp trạng thái tại thời điểm scrape

Active, idle, pending, max và min thường được công bố dưới dạng Gauge. Gauge phản ánh giá trị mà pool trả về khi Micrometer đọc nó. Nó không lưu lại mọi biến động giữa hai lần scrape.

Ví dụ pending tăng lên 20 trong 2 giây rồi trở về 0, trong khi Prometheus scrape mỗi 15 giây. Nếu cả hai lần scrape đều diễn ra lúc pending bằng 0, dashboard có thể không thấy đỉnh đó.

Khi cần phát hiện tình trạng chờ ngắn:

- Giảm scrape interval nếu chi phí và số lượng series cho phép.
- Theo dõi Timer acquire để quan sát phân phối thời gian chờ.
- Theo dõi Counter timeout để không bỏ lỡ sự kiện timeout.
- Dùng log hoặc trace để điều tra các request bị chậm cụ thể.

Không áp dụng rate() cho Gauge active hoặc pending như với Counter. Có thể dùng max_over_time, avg_over_time hoặc truy vấn giá trị trực tiếp tùy câu hỏi. Với Timer count và timeout Counter, dùng rate() hoặc increase() phù hợp.

## 10. Truy vấn PromQL để quan sát pool

Tên metric thực tế phụ thuộc registry và phiên bản. Với Prometheus, tên Micrometer có thể được chuẩn hóa sang chữ thường và dấu gạch dưới. Hãy kiểm tra endpoint exposition trước khi sao chép truy vấn.

### Số kết nối đang hoạt động

~~~promql
hikaricp_connections_active{pool="primary"}
~~~

### Tỷ lệ sử dụng pool so với giới hạn tối đa

Nếu metric active và max có cùng label pool:

~~~promql
hikaricp_connections_active{pool="primary"}
/
hikaricp_connections_max{pool="primary"}
~~~

Tỷ lệ này chỉ là một tín hiệu sử dụng tại thời điểm scrape. Cần xử lý trường hợp max bằng 0 hoặc metric max không có mặt, và không dùng riêng tỷ lệ này làm cảnh báo nghẽn.

### Số thread đang chờ

~~~promql
hikaricp_connections_pending{pool="primary"}
~~~

### Tốc độ timeout

~~~promql
rate(hikaricp_connections_timeout_total{pool="primary"}[5m])
~~~

### Thời gian acquire p95 từ histogram

Nếu Timer acquire được cấu hình xuất histogram:

~~~promql
histogram_quantile(
  0.95,
    sum by (pool, le) (
    rate(hikaricp_connections_acquire_seconds_bucket{pool="primary"}[5m])
  )
)
~~~

Nếu registry chỉ công bố count/sum hoặc client-side percentile, truy vấn bucket trên sẽ không có dữ liệu. Hãy kiểm tra cấu hình histogram và tên metric thực tế.

### So sánh các instance

~~~promql
max by (pool, instance) (hikaricp_connections_pending)
~~~

Giữ label instance giúp tìm pod hoặc JVM đang gặp áp lực. Khi tổng hợp toàn service, cần xác nhận các pool là độc lập và mỗi series chỉ được scrape một lần để tránh đếm trùng.

## 11. Kết hợp metric pool với dữ liệu khác

Một dashboard database pool có ích nên đặt các metric cạnh nhau:

| Nhóm | Số đo | Câu hỏi |
| --- | --- | --- |
| Pool capacity | active, idle, pending, max, min | Pool có cạn kết nối hay không? |
| Acquisition | acquire count, acquire duration, timeout count | Caller có phải chờ lâu hoặc timeout không? |
| Connection creation | creation duration, creation failures nếu có | Pool có khó tạo kết nối mới không? |
| Ứng dụng | request rate, latency, error rate | Áp lực pool có ảnh hưởng request không? |
| Database | CPU, active sessions, locks, wait events, query latency | Database có đang là nút thắt không? |
| Tracing/log | thời gian giữ connection, transaction, SQL span | Component hoặc câu truy vấn nào giữ kết nối lâu? |

Ví dụ:

- Pending tăng cùng acquire latency và timeout, trong khi database CPU thấp: kiểm tra transaction dài, connection leak, giới hạn pool và logic giữ kết nối.
- Pending tăng cùng database CPU và query latency: database có thể đang quá tải hoặc truy vấn đang tiêu thụ tài nguyên.
- Creation time tăng và timeout tăng: kiểm tra kết nối mạng, TLS, xác thực và khả năng nhận kết nối mới của database.
- Active cao nhưng pending bằng 0, request latency bình thường: có thể pool đang được sử dụng hiệu quả, chưa cần tăng giới hạn.

Đây là các hướng điều tra, không phải kết luận chắc chắn. Cần xác minh bằng dữ liệu database và ứng dụng.

## 12. Những giới hạn cần lưu ý khi dùng nhiều instance

Mỗi JVM thường có một pool riêng. Nếu có 8 instance và mỗi pool cho phép tối đa 30 kết nối, tổng khả năng mở kết nối từ service có thể lên đến 240, chưa tính job nền hoặc các service khác.

Vì vậy, cấu hình pool phải được xem ở cấp hệ thống:

- Tổng max connections của tất cả instance.
- Số kết nối dành cho admin, migration, background worker và service khác.
- Giới hạn connection của database.
- Khả năng chịu tải truy vấn đồng thời.
- Số instance tăng/giảm theo autoscaling.

Tăng số pod có thể làm tổng số kết nối tăng dù maximum size của mỗi pool không đổi. Dashboard chỉ hiển thị active của từng instance có thể bỏ sót áp lực tổng thể lên database.

Ví dụ tính giới hạn:

\[
8\ \text{instances} \times 30\ \text{connections} = 240\ \text{connections}
\]

Đây là giới hạn tiềm năng của service trong cấu hình ví dụ, không phải số kết nối đang mở thực tế. Muốn ước lượng tổng active hiện tại, cần tổng hợp các Gauge active của tất cả instance có label phân biệt đúng.

## 13. Kiểm tra metric trong Spring Boot Actuator

Khi endpoint metrics được expose, có thể kiểm tra danh sách metric:

~~~text
GET /actuator/metrics
~~~

Sau đó truy vấn một metric cụ thể:

~~~text
GET /actuator/metrics/jdbc.connections.active
~~~

Tên cụ thể có thể khác tùy pool và phiên bản. Endpoint metrics của Actuator thường cung cấp số đo theo cấu trúc nội bộ của Micrometer; endpoint Prometheus cung cấp exposition theo định dạng scrape.

Khi kiểm tra, cần xác nhận:

- Meter có xuất hiện sau khi DataSource khởi tạo không?
- Meter có tag pool/name đúng không?
- Giá trị active/idle có thay đổi khi ứng dụng mượn và trả Connection không?
- Metric timeout có tăng khi cố ý làm pool hết kết nối trong một kiểm thử cô lập không?
- Sau khi đóng pool, metric có còn được xuất hay không?

Không kiểm thử làm cạn pool trên database dùng chung hoặc môi trường production. Dùng database và pool dành riêng cho test.

## 14. Ví dụ kiểm thử hành vi pool

Kiểm thử tích hợp có thể tạo một HikariDataSource nhỏ, mượn Connection rồi kiểm tra Gauge active:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.metrics.micrometer.MicrometerMetricsTrackerFactory;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.sql.Connection;
import org.junit.jupiter.api.Test;

class HikariPoolMetricsTest {

    @Test
    void reportsAnActiveConnection() throws Exception {
        try (MeterRegistry registry = new SimpleMeterRegistry()) {
            HikariConfig config = new HikariConfig();
            config.setJdbcUrl("jdbc:h2:mem:poolmetrics;DB_CLOSE_DELAY=-1");
            config.setPoolName("test");
            config.setMaximumPoolSize(2);
            config.setMetricsTrackerFactory(
                    new MicrometerMetricsTrackerFactory(registry));

            try (HikariDataSource dataSource = new HikariDataSource(config)) {
                try (Connection ignored = dataSource.getConnection()) {
                    double active = registry.get("hikaricp.connections.active")
                            .tag("pool", "test")
                            .gauge()
                            .value();

                    assertThat(active).isEqualTo(1.0);
                }
            }
        }
    }
}
~~~

Đây là ví dụ minh họa cho HikariCP và H2; cần có dependency H2 trong test runtime. HikariCP tạo metric tracker khi pool khởi động. Nếu dự án dùng Spring Boot auto-configuration đã thiết lập tracker, không cấu hình thêm một factory khác cho cùng pool.

Kiểm thử nên xác minh cả trạng thái sau khi Connection được trả về. Do pool và metric là trạng thái đồng thời, nên tránh giả định mọi Gauge được cập nhật đồng bộ đúng cùng một nanosecond.

## 15. Lỗi thường gặp khi diễn giải metric pool

| Nhận định sai | Vì sao sai | Cách hiểu phù hợp |
| --- | --- | --- |
| Active bằng max nghĩa là pool đã lỗi | Có thể mọi kết nối đang bận nhưng không có thread chờ. | Xem pending, acquire latency và timeout cùng lúc. |
| Acquire latency là thời gian SQL | Acquire đo thời gian lấy Connection từ pool. | Dùng JDBC instrumentation, tracing hoặc database query metrics để đo SQL. |
| Idle bằng 0 luôn là sự cố | Pool có thể đang sử dụng hết kết nối nhưng vẫn đáp ứng nhu cầu. | Kiểm tra pending và độ trễ acquire. |
| Active cao chứng minh có connection leak | Transaction dài hoặc workload đồng thời cao cũng làm active tăng. | Xem thời gian giữ Connection, leak detection log và trace. |
| Timeout chỉ do pool quá nhỏ | Database hoặc mạng có thể khiến pool không tạo được kết nối. | Kiểm tra creation, DB availability, network và workload. |
| Pool max là số kết nối đang mở | Max là giới hạn cấu hình. | Xem active + idle và trạng thái pool tại thời điểm lấy mẫu. |
| Một pool metric đại diện mọi client database | Mỗi pool chỉ quan sát một DataSource. | Tổng hợp tất cả pool và các client khác ở cấp database. |
| Không thấy pending nghĩa là chưa từng có chờ | Scrape có thể bỏ lỡ đỉnh ngắn. | Xem acquire Timer và timeout Counter. |
| Metric không có nghĩa là giá trị bằng 0 | Có thể binder chưa chạy, meter bị filter hoặc pool chưa khởi tạo. | Kiểm tra endpoint, cấu hình registry và vòng đời DataSource. |

## 16. Checklist triển khai

- [ ] Đã xác định loại DataSource và connection pool thực tế.
- [ ] Đã biết metric nào do Spring Boot tự động cung cấp và metric nào cần binder riêng.
- [ ] Không đăng ký cùng binder hai lần trong một registry.
- [ ] Pool có tên ổn định và tag không chứa dữ liệu động.
- [ ] Đã quan sát active, idle, pending, max và min nếu pool hỗ trợ.
- [ ] Đã theo dõi acquire duration và timeout khi binder cung cấp.
- [ ] Không diễn giải acquire duration thành SQL execution time.
- [ ] Đã tính tổng giới hạn kết nối từ tất cả instance và workload.
- [ ] Đã kết hợp metric pool với request latency, tracing và database telemetry.
- [ ] Đã hiểu scrape có thể bỏ lỡ biến động Gauge ngắn.
- [ ] Đã kiểm tra endpoint Actuator/Prometheus và tên metric thực tế.
- [ ] Đã kiểm thử trong môi trường cô lập, không làm cạn pool production.

Metric connection pool giúp trả lời liệu ứng dụng có đang thiếu kết nối rảnh, phải chờ cấp phát hay gặp timeout. Chúng cung cấp góc nhìn về lớp quản lý kết nối ở phía ứng dụng; để xác định nguyên nhân gốc, cần kết hợp với thời gian giữ Connection, truy vấn SQL, transaction, tracing và số liệu từ database.

## Tài liệu tham khảo

- [Spring Boot Actuator - DataSource metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [HikariCP MicrometerMetricsTrackerFactory API](https://javadoc.io/static/com.zaxxer/HikariCP/7.1.0/com/zaxxer/hikari/metrics/micrometer/MicrometerMetricsTrackerFactory.html)
- [HikariCP MetricsTrackerFactory API](https://javadoc.io/static/com.zaxxer/HikariCP/7.1.0/com/zaxxer/hikari/metrics/MetricsTrackerFactory.html)
