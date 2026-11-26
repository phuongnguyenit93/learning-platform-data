# Execution profile, thời gian chờ và tùy chọn truy vấn

> **Chương:** Cấu hình kết nối  
> **Công nghệ:** Spring Data Cassandra, Spring Boot, Apache Cassandra và Java driver cho Cassandra.  
> **Trọng tâm:** thiết lập cấu hình mặc định, nhóm truy vấn theo execution profile, đặt timeout và các tùy chọn CQL theo đặc điểm nghiệp vụ, đồng thời kiểm chứng tác động đến tính nhất quán, phân trang và hiệu năng.

## 1. Bài toán: cùng một cluster nhưng các thao tác có yêu cầu khác nhau

Giả sử ứng dụng nhận sự kiện từ thiết bị IoT, lưu vào Apache Cassandra và cung cấp hai API:

1. `GET /devices/{id}/events?day=...`: tải 50 sự kiện gần nhất của một thiết bị trong một ngày UTC. Người dùng muốn trang đầu phản hồi nhanh, có thể tải tiếp.
2. `POST /device-events`: nhận sự kiện và ghi dữ liệu ổn định. Với sự kiện quan trọng, hệ thống ưu tiên xác nhận từ đủ replica trước khi trả kết quả thành công.

Một thao tác quản trị khác, ví dụ xuất lịch sử thiết bị trong khoảng thời gian được giới hạn, có thể chấp nhận thời gian chờ dài hơn API tương tác.

Tất cả cùng dùng một `CqlSession` và cluster Cassandra, nhưng không nhất thiết có cùng:

- **Độ trễ mục tiêu:** màn hình tương tác và tác vụ nền có ngân sách thời gian khác nhau.
- **Consistency level:** mức xác nhận cần thiết khi đọc hoặc ghi.
- **Fetch page size:** số row driver lấy trong mỗi trang dữ liệu từ Cassandra.
- **Retry và idempotency:** thao tác nào có thể chạy lại an toàn khi timeout.
- **Phạm vi dữ liệu:** một partition đã biết hay nhiều bucket thời gian.

Thay vì cài một timeout lớn cho mọi truy vấn hoặc cho phép từng nơi tùy ý thay đổi, Java driver hỗ trợ **execution profile**: một tập cấu hình được đặt tên để các statement có thể lựa chọn theo công việc.

Điều cốt lõi: execution profile điều chỉnh **cách driver thực thi yêu cầu**. Nó không thay đổi partition key, không tạo index và không làm một câu CQL quét nhiều partition trở thành truy vấn hiệu quả.

### Sơ đồ tổng quan

~~~mermaid
flowchart LR
    A["API lịch sử thiết bị"] --> B["Statement đọc"]
    C["Luồng ingest"] --> D["Statement ghi"]
    E["Tác vụ xuất dữ liệu"] --> F["Statement xuất"]
    B --> P["Profile: timeline-read"]
    D --> Q["Profile: durable-write"]
    F --> R["Profile: export-read"]
    P --> S["CqlSession / Cassandra driver"]
    Q --> S
    R --> S
    S --> T["Cassandra cluster"]
~~~

Một cấu hình tốt cần liên kết rõ **hợp đồng nghiệp vụ**, **hình dạng CQL** và **tùy chọn driver**. Cài profile theo tên “fast” hoặc “safe” mà không đo latency, replication factor và hành vi retry sẽ không đủ.

## 2. Execution profile trong Java driver là gì?

Java driver 4.x của Cassandra có **default execution profile** và các **named execution profiles**. Mỗi profile chứa các giá trị cho một số tùy chọn của driver. Statement thường dùng profile mặc định; code có thể chỉ định tên profile để áp dụng bộ cấu hình khác.

Các tùy chọn hay gặp trong phần này:

| Khái niệm | Cấu hình ở driver | Ý nghĩa |
| --- | --- | --- |
| Request timeout | `basic.request.timeout` | Ngân sách thời gian client dành cho một yêu cầu |
| Consistency mặc định | `basic.request.consistency` | Mức xác nhận replica cho đọc/ghi thông thường |
| Serial consistency | `basic.request.serial-consistency` | Dùng với thao tác điều kiện/LWT khi phù hợp |
| Page size | `basic.request.page-size` | Kích thước fetch page, không phải `LIMIT` |
| Execution profile | `profiles.<tên>` | Bộ tùy chọn đặt tên, có thể kế thừa giá trị mặc định |
| Per-statement override | `setTimeout`, `setConsistencyLevel`, `setPageSize` | Ưu tiên cụ thể cho một statement |

Tên đường dẫn HOCON ở bảng trên là tên của **Java driver**; các khóa `spring.cassandra.*` là cấu hình của **Spring Boot**. Chúng liên quan nhưng không phải hai không gian cấu hình có thể thay thế máy móc cho nhau.

Thứ tự suy nghĩ khi driver thực thi một statement:

1. Lấy các giá trị trong **default profile**.
2. Nếu statement chọn **named profile**, dùng các giá trị của profile đó cho phần được khai báo; phần khác kế thừa theo cơ chế cấu hình driver.
3. Nếu statement gán **tùy chọn trực tiếp**, tùy chọn ấy được ưu tiên cho statement tương ứng.

Ví dụ, profile `timeline-read` có timeout 800 ms nhưng một statement riêng đặt timeout 2 giây thì statement đó dùng 2 giây. Không nên phân tán override không có lý do vì khi đó profile mất tác dụng như một chính sách chung.

**Named profile không đồng nghĩa một `CqlSession` mới, transaction riêng hoặc pool vật lý độc lập.** Đây trước hết là bộ tham số thực thi. Tùy chọn định tuyến/load balancing có thể liên quan đến cấu hình profile và driver version, nhưng việc tạo nhiều profile không tự mang lại cách ly tài nguyên như hai cluster khác nhau.

## 3. Phân biệt bốn loại thời gian chờ

Trong sự cố thực tế, từ “timeout” có thể chỉ nhiều tầng khác nhau. Phải xác định tầng báo lỗi trước khi chỉnh giá trị.

| Loại timeout | Giai đoạn bị giới hạn | Điều cần hiểu |
| --- | --- | --- |
| **Connect timeout** | Thiết lập kết nối TCP tới node | Cluster không truy cập được hoặc mạng chậm thì request timeout không cứu được kết nối |
| **Session/initialization timeout** | Khởi tạo hoặc kiểm tra phiên, truy vấn khởi tạo | Liên quan khởi động ứng dụng; kiểm tra cấu hình và khả năng sẵn sàng của cluster |
| **Request timeout ở driver** | Client chờ một yêu cầu CQL hoàn tất | Hết thời gian trên client không chứng minh Cassandra đã hủy thao tác |
| **Timeout ở API/gateway** | Toàn bộ request HTTP hoặc tác vụ nghiệp vụ | Gồm xác thực, tìm dữ liệu, nhiều truy vấn, chuyển đổi và truyền mạng |

Ngoài ra, Cassandra server có thể trả lỗi timeout/unavailable theo điều kiện replica và consistency. Cần phân biệt **client tự hết hạn chờ** với **server/coordinator báo không đủ phản hồi**. Hai trường hợp không nhất thiết có cùng nguyên nhân hoặc cách sửa.

Ví dụ một API có SLO p95 ≤ 300 ms:

~~~text
Budget API tổng:      300 ms (mục tiêu p95, không phải hard timeout)
Xác thực + routing:   30 ms (giả định)
Đọc Cassandra:       180 ms (ngân sách mục tiêu)
Serialize + network:  50 ms (giả định)
Dự phòng:             40 ms
~~~

Từ phân bổ này, việc đặt `basic.request.timeout = 30 seconds` để “tránh lỗi” là không phù hợp. Nhưng cũng không nên đặt 180 ms một cách máy móc: timeout là **ngưỡng chặn**, phải tính đến phân phối tail latency và độ ổn định dưới tải; SLO p95 và hard timeout không phải một khái niệm. Cần đo p95, p99 và tỷ lệ timeout trước khi chọn.

**Điểm an toàn khi ghi:** client timeout không đảm bảo truy vấn ghi đã thất bại. Coordinator/replica có thể đã áp dụng mutation nhưng phản hồi không đến kịp. Khi retry, phải biết ghi đó có idempotent hay không, đặc biệt với counter, list append, batch không thích hợp hoặc các thao tác điều kiện.

## 4. Cấu hình mặc định trong Spring Boot

Với một ứng dụng Spring Boot 3.x sử dụng starter đồng bộ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-cassandra'
}
~~~

Spring Boot thường tự cấu hình `CqlSession`, mapping, `CassandraTemplate` và phần tích hợp repository khi các dependency và thông tin kết nối hợp lệ.

Ví dụ `src/main/resources/application.yml` cho môi trường phát triển:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: telemetry
    schema-action: none
    request:
      timeout: 2s
~~~

Giải thích:

- `contact-points` và `port` chỉ nơi driver bắt đầu khám phá topology.
- `local-datacenter` phải là tên datacenter **thực** trong Cassandra cluster; không mặc định đặt `datacenter1` nếu cluster đang dùng tên khác.
- `keyspace-name` là keyspace mặc định của session; keyspace và bảng phải tồn tại nếu chọn `schema-action: none`.
- `request.timeout` là cấu hình timeout ở mức Spring Boot dành cho yêu cầu driver.
- `schema-action: none` tránh để ứng dụng tùy tiện tạo/sửa schema ở thời điểm khởi động; trong môi trường thực dùng quy trình migration riêng.

**Lưu ý:** property names và auto-configuration có thể thay đổi giữa các thế hệ Spring Boot. Mã trong bài dùng cách đặt tên của dòng Spring Boot 3.x; khi nâng version, kiểm tra configuration metadata và release notes đi kèm chính phiên bản dự án.

Để cấu hình nhiều named profiles, Spring Boot có hook tùy biến trình tạo **driver config loader**. Không nhất thiết thay cả `CqlSession` chỉ để thêm một profile. Hãy dùng điểm mở rộng đúng của Boot để giữ những thuộc tính kết nối, bảo mật và lifecycle mà Boot đang quản lý.

## 5. Tạo named execution profiles bằng Spring Boot

Trường hợp cần ba chính sách:

- `timeline-read`: trang lịch sử tương tác, timeout tương đối ngắn, page size nhỏ.
- `durable-write`: ghi sự kiện, mong muốn quorum trong datacenter hiện tại.
- `export-read`: truy vấn từng phần cho job nền, timeout dài hơn nhưng vẫn giới hạn lượng dữ liệu.

Trong Spring Boot 3.x có thể đăng ký `DriverConfigLoaderBuilderCustomizer`:

~~~java
import java.time.Duration;

import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import org.springframework.boot.autoconfigure.cassandra.DriverConfigLoaderBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CassandraExecutionProfileConfig {

    @Bean
    DriverConfigLoaderBuilderCustomizer executionProfiles() {
        return builder -> builder
            // Cấu hình mặc định cho yêu cầu chưa chọn profile riêng.
            .withDuration(DefaultDriverOption.REQUEST_TIMEOUT,
                          Duration.ofSeconds(2))
            .withInt(DefaultDriverOption.REQUEST_PAGE_SIZE, 200)

            // Truy vấn tương tác: tập trung giảm dung lượng mỗi fetch.
            .startProfile("timeline-read")
            .withDuration(DefaultDriverOption.REQUEST_TIMEOUT,
                          Duration.ofMillis(800))
            .withInt(DefaultDriverOption.REQUEST_PAGE_SIZE, 50)
            .withString(DefaultDriverOption.REQUEST_CONSISTENCY, "LOCAL_ONE")
            .endProfile()

            // Ghi sự kiện: yêu cầu quorum tại datacenter địa phương.
            .startProfile("durable-write")
            .withDuration(DefaultDriverOption.REQUEST_TIMEOUT,
                          Duration.ofSeconds(3))
            .withString(DefaultDriverOption.REQUEST_CONSISTENCY,
                        "LOCAL_QUORUM")
            .endProfile()

            // Đọc theo lô, vẫn dùng paging và giới hạn công việc.
            .startProfile("export-read")
            .withDuration(DefaultDriverOption.REQUEST_TIMEOUT,
                          Duration.ofSeconds(8))
            .withInt(DefaultDriverOption.REQUEST_PAGE_SIZE, 500)
            .endProfile();
    }
}
~~~

`DriverConfigLoaderBuilderCustomizer` tùy biến cấu hình Java driver trong quá trình Boot dựng session. Trong dự án thật, cần kiểm tra điểm mở rộng, package và builder API theo **phiên bản Boot/driver đang được dependency management chọn**; ví dụ không chủ trương trộn thủ công một driver version khác với Spring Data Cassandra.

Các giá trị 800 ms, 3 giây, 8 giây, 50, 200 và 500 chỉ là **tham số minh họa để luyện phân biệt chính sách**, không phải khuyến nghị mặc định cho mọi cluster. Phải đo latency và throughput trên dữ liệu đại diện rồi hiệu chỉnh.

### Một cách khác: file HOCON của Java driver

Nếu ứng dụng Java thuần dùng Java driver, hoặc dự án đã có cơ chế nạp driver configuration phù hợp, cú pháp HOCON tương đương có thể là:

~~~hocon
datastax-java-driver {
  basic.request {
    timeout = 2 seconds
    page-size = 200
  }

  profiles {
    timeline-read {
      basic.request {
        timeout = 800 milliseconds
        page-size = 50
        consistency = LOCAL_ONE
      }
    }

    durable-write {
      basic.request {
        timeout = 3 seconds
        consistency = LOCAL_QUORUM
      }
    }

    export-read {
      basic.request {
        timeout = 8 seconds
        page-size = 500
      }
    }
  }
}
~~~

**Không giả định một file HOCON tự động ghi đè mọi property của Spring Boot.** Nguồn config, cơ chế nạp `DriverConfigLoader` và thứ tự ưu tiên của customizer phụ thuộc phiên bản và cách ứng dụng tạo `CqlSession`. Chọn **một con đường cấu hình có chủ đích**, kiểm tra giá trị resolved ở runtime rồi mới triển khai. Nếu tự `withConfigLoader(...)` trên `CqlSessionBuilderCustomizer`, cần xác minh việc này không bỏ qua các tùy chỉnh mà Boot đã thiết lập.

### Profile không phải tên quyền hạn

Các tên `timeline-read` hoặc `durable-write` là chính sách hiệu năng/consistency của **client**. Chúng không cấp quyền CQL cho người dùng. Phân quyền tenant, thiết bị và truy vấn vẫn phải được thực thi ở tầng ứng dụng và Cassandra role/keyspace/table khi phù hợp. Không nhận chuỗi profile do người dùng HTTP tự gửi rồi đưa trực tiếp vào statement.

## 6. Áp profile vào câu CQL cụ thể bằng Java driver

Giả sử có bảng thiết kế theo truy vấn timeline:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry.events_by_device_day (
    device_id   uuid,
    event_day   date,
    event_time  timestamp,
    event_id    uuid,
    kind        text,
    payload     text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Partition key là `(device_id, event_day)`, clustering keys là `event_time` và `event_id`. Một truy vấn chỉ định đầy đủ partition key và giới hạn dữ liệu có thể được driver thực thi theo profile riêng.

~~~java
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.stereotype.Repository;

@Repository
public class TimelineCqlReader {
    private final CqlSession session;

    public TimelineCqlReader(CqlSession session) {
        this.session = session;
    }

    public ResultSet readDay(UUID deviceId, LocalDate utcDay) {
        SimpleStatement statement = SimpleStatement.newInstance(
            "SELECT event_time, event_id, kind, payload "
          + "FROM telemetry.events_by_device_day "
          + "WHERE device_id = ? AND event_day = ? LIMIT 50",
            deviceId, utcDay
        )
        .setExecutionProfileName("timeline-read")
        .setIdempotent(true);

        return session.execute(statement);
    }
}
~~~

`SimpleStatement.newInstance(...)` ở đây dùng positional bind values cho dấu `?`; không nối `deviceId`/`utcDay` vào chuỗi CQL. Trong code thật, có thể dùng prepared statement cho truy vấn lặp lại nhiều lần nhằm tái sử dụng việc chuẩn bị câu lệnh và kiểm soát kiểu dữ liệu.

Một repository hoặc template của Spring Data Cassandra có thể tiếp tục xử lý entity mapping. Chỉ nên dùng `CqlSession` trực tiếp ở nơi cần kiểm soát sâu một số tùy chọn driver mà abstraction cấp cao chưa biểu đạt thuận tiện. Chọn đường đi nhất quán cho một luồng nghiệp vụ và kiểm thử cả mapping lẫn CQL.

**Quan trọng:** `LIMIT 50` giới hạn tổng số row truy vấn được phép trả về, còn profile `page-size = 50` quy định kích thước trang driver tìm nạp. Nếu đặt `LIMIT 500` cùng `page-size = 50`, có thể phải fetch nhiều trang để lấy đủ 500 row. Đọc `ResultSet` tới hết có thể kéo thêm các trang phía sau; không biến tất cả kết quả thành `List` không giới hạn chỉ vì profile có page size nhỏ.

## 7. Override tùy chọn trên từng statement

Named profile đưa ra chính sách chung, nhưng một statement đặc biệt có thể cần giới hạn nhỏ hơn hoặc consistency mạnh hơn. Ví dụ:

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

public class StatementOptionsExample {
    public SimpleStatement create(UUID deviceId, LocalDate day) {
        return SimpleStatement.newInstance(
            "SELECT event_time, event_id, kind "
          + "FROM telemetry.events_by_device_day "
          + "WHERE device_id = ? AND event_day = ? LIMIT 20",
            deviceId, day
        )
        .setExecutionProfileName("timeline-read")
        .setTimeout(Duration.ofSeconds(1))
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setPageSize(20)
        .setIdempotent(true);
    }
}
~~~

Trong ví dụ này:

| Tùy chọn | Profile `timeline-read` | Giá trị statement thực dùng |
| --- | --- | --- |
| Timeout | 800 ms | 1 giây |
| Consistency | `LOCAL_ONE` | `LOCAL_QUORUM` |
| Page size | 50 | 20 |
| Idempotent | Cần xác định theo statement | `true` vì truy vấn `SELECT` ở ví dụ có thể retry theo cùng điều kiện |

Các phương thức `set...` của statement trong Java driver 4 trả về statement với tùy chọn đã cập nhật; nên dùng kết quả được trả về hoặc nối chuỗi như trong mã. Không nên giả định việc gọi `set...` mà bỏ qua giá trị trả về sẽ sửa object theo kiểu mutable.

**Nguyên tắc quản trị:** dùng profile cho nhóm yêu cầu có cùng chính sách; dùng override cho ngoại lệ có lý do kỹ thuật; đo số lượng ngoại lệ. Nếu gần như mọi statement đều override timeout và consistency, cấu trúc profile cần được thiết kế lại.

## 8. Timeout không thay thế thiết kế bảng theo truy vấn

Ví dụ đúng schema của mục 6:

~~~sql
SELECT *
FROM telemetry.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time >= ?
  AND event_time < ?
LIMIT 100;
~~~

Truy vấn này định tuyến đến đúng một partition, sau đó lấy dải clustering key `event_time`.

Ngược lại:

~~~sql
-- Đây không phải truy vấn phù hợp với primary key hiện tại:
SELECT * FROM telemetry.events_by_device_day
WHERE kind = 'BATTERY_LOW';
~~~

`kind` không có trong partition key; Cassandra sẽ không tự quét hiệu quả toàn bộ cluster để trả lời câu hỏi này. Tăng timeout từ 2 giây lên 30 giây hoặc tăng page size không tạo ra partition key cần thiết. Nếu sản phẩm cần cảnh báo pin yếu theo chi nhánh, phải đánh giá bảng đọc khác, index phù hợp với phiên bản Cassandra đang dùng hoặc hệ truy vấn/phân tích chuyên biệt.

Trước khi điều chỉnh timeout, hãy trả lời:

- Truy vấn có đầy đủ partition key không?
- Partition có quá lớn hoặc tập trung lưu lượng không?
- Có tombstone, compaction backlog hoặc cross-datacenter network latency không?
- Consistency cần bao nhiêu replica phản hồi?
- Query có đang quét nhiều bucket ngày không?
- Client có đang vô tình đọc hết mọi trang kết quả không?

Đây thường là những nguồn gốc gây chậm quan trọng hơn một giá trị timeout cụ thể.

## 9. Chọn consistency theo hợp đồng đọc/ghi

Consistency là lựa chọn liên quan trực tiếp đến tính nhất quán phân tán.

| Consistency | Ý nghĩa khái quát | Tình huống cân nhắc |
| --- | --- | --- |
| `LOCAL_ONE` | Một replica trong local datacenter phản hồi | Đọc timeline chấp nhận có lúc chưa thấy bản ghi mới nhất |
| `LOCAL_QUORUM` | Đa số replica trong local datacenter phản hồi | Đọc/ghi cần mức xác nhận mạnh hơn trong local DC |
| `ALL` | Tất cả replica liên quan phải phản hồi | Khả năng sẵn sàng thấp hơn khi một replica gặp sự cố; thường không chọn cho ingest liên tục |
| `LOCAL_SERIAL` | Serial consistency của bước điều kiện LWT | Chỉ áp dụng trong ngữ cảnh LWT phù hợp, không phải thay thế trực tiếp `LOCAL_QUORUM` cho mọi query |

Giả sử keyspace có replication factor 3 trong một datacenter, `LOCAL_QUORUM` cần 2 replica phản hồi. Khi cùng một tập replica tham gia và hệ thống vận hành bình thường, đọc và ghi cùng mức quorum có tập giao nhau; điều này có ích để đọc dữ liệu vừa ghi. Tuy nhiên, sự giao nhau **không tự cung cấp transaction ACID đa partition**, và các trường hợp ghi đồng thời, clock skew, hinted handoff, sự cố replica hoặc write timestamp vẫn cần được phân tích.

### Phân biệt tính nhất quán và độ mới dữ liệu của pipeline

Một hệ thống có thể ghi `events_by_device_day` trước và sau đó ghi bản chiếu `alerts_by_site_day` bằng worker bất đồng bộ. Dù cả hai thao tác đều dùng `LOCAL_QUORUM`, bản chiếu thứ hai vẫn **chưa có sự kiện** khi worker chưa xử lý. Consistency level của Cassandra chỉ điều chỉnh xác nhận của từng yêu cầu với replica, không làm hai lệnh ghi khác partition tự đồng bộ như transaction.

### Khi nào không dùng cùng consistency cho mọi việc?

Ví dụ nhu cầu được chốt:

- Trang timeline chỉ mang tính quan sát: có thể chọn `LOCAL_ONE` nếu chấp nhận đọc hơi cũ để ưu tiên latency/availability.
- Ghi sự kiện quan trọng: có thể chọn `LOCAL_QUORUM` khi yêu cầu xác nhận từ đa số replica.
- Đọc ngay sau một hành động vừa ghi và phải hiển thị trạng thái mới: cần đánh giá mức đọc phù hợp, cơ chế read-your-writes của ứng dụng, và kết quả ghi thành công.
- Tác vụ đối soát dữ liệu: consistency có thể cần khắt khe hơn, nhưng không tự sửa lỗi nguồn dữ liệu hay pipeline.

Không chọn profile chỉ bằng cảm giác “LOCAL_ONE nhanh hơn” hay “QUORUM luôn an toàn”. Hãy tính toán RF, topology, SLO, yêu cầu đọc dữ liệu mới, khả năng chịu lỗi và tỷ lệ timeout.

## 10. Retry, speculative execution và idempotency

Khi query timeout hoặc node không phản hồi, driver có thể dùng retry policy; một số cấu hình còn cho phép speculative execution để gửi request bổ sung trước khi request đầu trả về. Hai cơ chế này ảnh hưởng mạnh tới tải cluster.

| Tình huống | Câu hỏi cần trả lời trước khi retry |
| --- | --- |
| `SELECT` chỉ đọc | Query có thể chạy lại với cùng filter/cursor mà không gây side effect không? |
| `INSERT` cùng khóa và cùng giá trị | Retry có đổi timestamp, TTL, trạng thái cạnh tranh hoặc side effect ngoài Cassandra không? |
| Counter update | Tăng thêm một lần có gây đếm trùng không? |
| Append vào collection/list | Lặp lại có thêm phần tử hai lần không? |
| Lightweight transaction `IF NOT EXISTS` | Conditional result/việc ghi đã hoàn tất chưa, cần kiểm tra lại trạng thái thế nào? |
| Gửi sự kiện sang hệ ngoài song song | Retry có khiến HTTP/webhook hoặc message bị phát lại ngoài dự kiến không? |

Cách gắn idempotency ở statement:

~~~java
SimpleStatement readStatement = SimpleStatement.newInstance(
    "SELECT event_time FROM telemetry.events_by_device_day "
  + "WHERE device_id = ? AND event_day = ? LIMIT 50",
    deviceId, day
).setExecutionProfileName("timeline-read")
 .setIdempotent(true);
~~~

**Không đánh dấu mọi statement là idempotent theo thói quen.** Với một row sự kiện có khóa `(deviceId, day, eventTime, eventId)` ổn định và giá trị ghi không thay đổi, ghi lặp thường có thể được thiết kế idempotent. Nhưng nếu mỗi lần retry tạo `eventId` mới, thay thời gian, làm mới TTL hoặc phát sinh thao tác bổ sung, phải đánh giá lại.

Một hard timeout quá ngắn có thể làm tăng retry và tải đúng lúc cluster đang chậm. Đó là vòng phản hồi bất lợi: cluster chậm → timeout → retry nhiều hơn → cluster càng tải nặng. Phải giám sát tỷ lệ retry/speculative execution và đặt giới hạn phù hợp; không xem chúng như cách che truy vấn thiếu partition key.

## 11. Page size, LIMIT và cursor là ba khái niệm khác nhau

Trong Cassandra:

- `LIMIT n`: giới hạn tổng số row query trả về theo CQL.
- **Fetch page size**: số row mục tiêu mà driver yêu cầu lấy trong một lần fetch. Không phải tổng số row cho API.
- **Paging state**: trạng thái tiếp tục đọc tập kết quả, gắn với cùng truy vấn, điều kiện và cách thực thi.

Giả sử bảng có 1.000 sự kiện cho một thiết bị/ngày:

| Thiết lập | Tác động |
| --- | --- |
| `LIMIT 50` và page size 100 | Query trả tối đa 50 row |
| `LIMIT 500` và page size 50 | Đọc tới 500 row có thể cần nhiều lần fetch |
| `LIMIT 500` và page size 500 | Có thể tăng khối lượng dữ liệu/chuyển mạng mỗi lần fetch |
| Page size 50, không có `LIMIT` | Driver vẫn có thể tiếp tục lấy nhiều trang cho đến hết dữ liệu nếu ứng dụng duyệt hết |

Với Spring Data Cassandra, repository có thể trả `Slice<T>` cùng `CassandraPageRequest` để duyệt tiếp:

~~~java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, DeviceEventKey> {

    @Query("SELECT * FROM events_by_device_day "
         + "WHERE device_id = ?0 AND event_day = ?1")
    Slice<DeviceEvent> findByDeviceAndDay(
        UUID deviceId, LocalDate eventDay, Pageable pageable);
}
~~~

Ở trên, `DeviceEvent` và `DeviceEventKey` là hai lớp entity/key được ánh xạ với bảng CQL bằng các annotation tương ứng như `@Table`, `@PrimaryKey` và `@PrimaryKeyClass`.

Gọi:

~~~java
import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.domain.Slice;

Slice<DeviceEvent> first =
    repository.findByDeviceAndDay(deviceId, day,
                                  CassandraPageRequest.first(50));

if (first.hasNext()) {
    Slice<DeviceEvent> second =
        repository.findByDeviceAndDay(deviceId, day, first.nextPageable());
}
~~~

Không dùng offset để nhảy tùy ý đến trang thứ 1.000. Paging state tiếp tục dòng dữ liệu của truy vấn trước, không phải chỉ số trang số học. Nếu API cần gửi cursor ra ngoài, phải xác thực hoặc ký token, giới hạn thời gian sống, buộc token gắn với `deviceId`, `day`, filter và kích thước trang, đồng thời tính đến sự kiện mới/xóa xảy ra trong lúc đang phân trang.

**Named profile không thay thế phân trang của Spring Data.** Trường hợp repository đã dùng `CassandraPageRequest.first(50)`, hãy kiểm tra semantics size của Spring Data và driver; đừng cộng dồn một kích thước page ngầm định khác mà không đo dữ liệu thực tế.

## 12. Kết hợp Spring Data repository, CassandraTemplate và CqlSession

Spring Data Cassandra có ba mức làm việc phổ biến:

| API | Ưu điểm | Lựa chọn khi cần tùy chọn driver |
| --- | --- | --- |
| `CassandraRepository` | CRUD và các truy vấn được định nghĩa gọn theo domain | Mặc định kế thừa cấu hình driver; dùng annotation/API được hỗ trợ cho trường hợp riêng |
| `CassandraTemplate` | Truy vấn với `Query`/`Criteria`, entity mapping, thao tác dữ liệu linh hoạt | Phù hợp logic cần tự dựng điều kiện nhưng vẫn tuân thủ partition key; tùy chọn driver cụ thể cần đối chiếu API phiên bản |
| `CqlSession` | Kiểm soát trực tiếp CQL statement, execution profile, timeout, page size, consistency | Dùng khi truy vấn cần điều khiển chi tiết mà repository/template không biểu đạt rõ ràng |

Ví dụ repository có yêu cầu consistency riêng:

~~~java
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Consistency;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, DeviceEventKey> {

    @Consistency(DefaultConsistencyLevel.LOCAL_QUORUM)
    @Query("SELECT * FROM events_by_device_day "
         + "WHERE device_id = ?0 AND event_day = ?1")
    Slice<DeviceEvent> findByDeviceAndDay(
        UUID deviceId, LocalDate day, Pageable pageable);
}
~~~

Annotation `@Consistency` trong ví dụ này áp dụng cho **phương thức repository được đánh dấu**, không có nghĩa mọi `save(...)` ở repository tự động chuyển sang cùng consistency. Nếu nghiệp vụ yêu cầu ghi quorum, cần xác định đường ghi và cấu hình consistency cho chính thao tác ghi.

Ví dụ `CassandraTemplate` với truy vấn có khóa đầy đủ:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class DeviceEventLookup {
    private final CassandraTemplate template;

    public DeviceEventLookup(CassandraTemplate template) {
        this.template = template;
    }

    public List<DeviceEvent> latest(UUID deviceId, LocalDate utcDay) {
        Query query = Query
            .query(Criteria.where("device_id").is(deviceId))
            .and(Criteria.where("event_day").is(utcDay))
            .limit(50);

        return template.select(query, DeviceEvent.class);
    }
}
~~~

`CassandraTemplate` vẫn sinh CQL phục vụ **một partition cụ thể**. Việc thay repository bằng template không giúp lọc toàn cluster theo `kind`. Khi cần custom profile/timeout cấp driver, có thể xây một repository fragment riêng sử dụng `CqlSession` để toàn ứng dụng vẫn có interface domain nhất quán.

Không nên trộn Spring Data repository với `CqlSession` ngẫu hứng cho cùng một tác vụ: cần quy định rõ nơi áp consistency, timeout và paging, vì nếu không hai đường đọc có thể trả kết quả khác nhau khi cluster đang cập nhật.

## 13. Kỹ thuật kiểm chứng profile đang áp dụng

Lỗi rất phổ biến: khai báo một profile trong config nhưng statement không thực sự chọn profile đó. Khi đó số liệu tưởng là của `timeline-read` nhưng thực ra vẫn thuộc default.

Quy trình xác minh:

1. Khởi động ứng dụng với cấu hình và phiên bản driver đã chốt.
2. Xác nhận tên profile tồn tại trong **runtime driver configuration** của `CqlSession`.
3. Tạo statement đúng tên bằng `setExecutionProfileName("timeline-read")`.
4. Kiểm tra timeout, consistency và page size đã resolve, không chỉ kiểm tra file cấu hình.
5. Chạy một CQL trên partition mẫu và đo latency/response; quan sát timeout/errors/retry.
6. So sánh với statement cùng câu CQL nhưng dùng profile khác, với cùng dữ liệu và tải thử nghiệm.

Có thể kiểm tra giá trị cấu hình driver tại runtime bằng API config của session:

~~~java
import java.time.Duration;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverExecutionProfile;

public class ProfileInspector {
    public Duration readTimeout(CqlSession session) {
        DriverExecutionProfile profile = session.getContext()
            .getConfig()
            .getProfile("timeline-read");

        return profile.getDuration(DefaultDriverOption.REQUEST_TIMEOUT);
    }
}
~~~

API đọc config dùng để kiểm tra chính sách, **không nên log username/password, token, endpoint bí mật hoặc toàn bộ config** vào môi trường production. Đặt health check và metrics để quan sát driver và cluster; chỉ log những tùy chọn cần thiết phục vụ chẩn đoán.

Khi profile bị khai báo sai tên, đừng dựa vào “chạy được” để cho là đúng: cần kiểm tra lỗi cấu hình hoặc giá trị thực đang dùng. Tên profile là chuỗi có ý nghĩa chính xác; chuẩn hóa bằng hằng số hoặc enum trong mã nguồn để tránh typo.

## 14. Cách chọn các giá trị timeout bằng số liệu

Giả sử đã có số đo cho một partition-read trong môi trường staging đại diện:

| Chỉ số | Quan sát giả định |
| --- | ---: |
| p50 | 18 ms |
| p95 | 85 ms |
| p99 | 230 ms |
| p99.9 | 600 ms |
| Timeout hiện tại | 2.000 ms |
| API SLO p95 | 300 ms |
| Tỷ lệ request lỗi | 0,1% |

Không nên suy ra rằng timeout 250 ms luôn đúng chỉ vì p99 = 230 ms. Timeout thấp có thể làm tăng lỗi trong giờ cao điểm, khi GC/compaction hoặc network congestion xảy ra. Cũng không nên lấy p99.9 làm timeout cho mọi operation khi API có hard deadline nhỏ hơn.

Một quy trình điều chỉnh có kiểm soát:

1. **Đo end-to-end** ở API: phân biệt thời gian chờ Cassandra với serialization, auth và network.
2. **Phân nhóm query**: timeline một partition, ghi ingest, xuất dữ liệu nhiều trang. Không trộn latency histogram của các nhóm khác nhau.
3. **Xác định ngân sách**: timeout của từng query phải nằm trong ngân sách request tổng; đối với thao tác nhiều truy vấn liên tiếp, xem xét deadline chung.
4. **Chọn ngưỡng thử nghiệm** từ phân phối độ trễ, tỷ lệ lỗi chấp nhận được và nhu cầu sẵn sàng.
5. **Canary** trên một phần traffic; so sánh timeout rate, retry, p95/p99, CPU, pending requests và compaction.
6. **Điều chỉnh tiếp** nếu số liệu cho thấy tăng lỗi, tăng tail latency hoặc quá tải replica.

Khi request timeout tăng nhưng latency vẫn xấu, phải quay lại kiểm tra câu CQL, partition size, tombstone, fetch page, consistency và trạng thái cluster. **Timeout là chính sách kết thúc chờ đợi, không phải cơ chế tối ưu truy vấn.**

## 15. Ví dụ tình huống: đọc nhanh nhưng không đánh đổi mù quáng

Bài toán: dashboard hiển thị 50 sự kiện gần nhất theo `deviceId` và ngày UTC; dữ liệu được ghi với `LOCAL_QUORUM`. Product chấp nhận dashboard đôi khi chậm cập nhật một vài giây, nhưng trang cần phản hồi nhanh.

Một cấu hình khả dĩ:

~~~text
Profile timeline-read:
  REQUEST_TIMEOUT       = 800 ms
  REQUEST_PAGE_SIZE     = 50
  REQUEST_CONSISTENCY   = LOCAL_ONE

Profile durable-write:
  REQUEST_TIMEOUT       = 3 s
  REQUEST_CONSISTENCY   = LOCAL_QUORUM
~~~

Đánh đổi: đọc `LOCAL_ONE` có thể chưa thấy bản ghi vừa ghi, vì read có thể được phục vụ bởi một replica chưa nhận dữ liệu mới trong một số tình huống. Nếu UI hiển thị “đã lưu” rồi ngay lập tức gọi timeline và yêu cầu **chắc chắn thấy bản ghi**, hợp đồng này không còn phù hợp; cần thay đổi mức consistency hoặc UX/luồng xác nhận, và test các tình huống replica chậm.

Việc chọn nhanh/chậm phụ thuộc hệ số nhân bản:

- RF=1 ở môi trường demo: `LOCAL_QUORUM` thực tế tương đương một replica trong local DC; không thể từ demo suy ra độ trễ của RF=3.
- RF=3 local DC: quorum cần 2 replica; tăng xác nhận thường tăng yêu cầu sẵn sàng và có thể ảnh hưởng latency.
- Nhiều datacenter: `LOCAL_*` nhấn mạnh datacenter cục bộ; phải kiểm tra config `local-datacenter` đúng với topology thực.

Nếu người dùng xem một sự kiện vừa ghi qua một pipeline projection bất đồng bộ, không có consistency level nào trên bảng projection bảo đảm row đã có mặt trước khi projector xử lý. Cần đo cả **projection lag**.

## 16. Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có khả năng | Cách xử lý |
| --- | --- | --- |
| Profile khai báo nhưng timeout không đổi | Statement chưa chọn tên profile, bị override trực tiếp hoặc nguồn config khác ưu tiên | Đọc runtime resolved config, kiểm tra tên profile và statement |
| Timeout ngắn gây nhiều lỗi dù query trước đây chạy được | Tail latency cao, retry/speculative tăng, áp lực replica | So sánh histogram, giảm tải, tối ưu schema và cân nhắc timeout hợp lý |
| Tăng timeout lên 30 giây nhưng API vẫn fail sau 2 giây | Gateway/API deadline hoặc timeout tầng khác ngắn hơn | Vẽ timeline của từng tầng, điều chỉnh ngân sách thống nhất |
| Đọc `LOCAL_ONE` không thấy sự kiện mới | Replica được đọc chưa có mutation mới nhất | Đánh giá read/write consistency và yêu cầu UX |
| Ghi báo timeout nhưng row xuất hiện sau đó | Timeout ở client không hủy chắc chắn mutation trên server | Thiết kế idempotent retry, đối soát theo event ID |
| Trang đầu chậm khi page size quá lớn | Fetch quá nhiều row/byte, row lớn hoặc workload vượt mục tiêu | Đo row size, giảm page size, giới hạn `LIMIT` phù hợp |
| Màn hình báo “không có trang tiếp” sai | Đọc theo offset hoặc xử lý paging state sai | Dùng `Slice`/`CassandraPageRequest` hoặc driver paging theo đúng API |
| Query chậm dù profile “fast” | Thiếu partition key, hot partition, tombstone/compaction | Sửa mô hình dữ liệu và pattern truy vấn |
| Boot property không phản ánh trong driver | Có custom config loader hoặc thứ tự config ngoài dự kiến | Kiểm tra customizer, HOCON, resolved profile và dependency version |
| Nhầm `LOCAL_SERIAL` với read consistency thông thường | Cấu hình serial consistency cho truy vấn không phải LWT | Dùng serial consistency có mục đích cho thao tác điều kiện |

## 17. Checklist đưa execution profiles vào sản xuất

Trước khi rollout thay đổi cấu hình, hoàn thành bảng kiểm sau:

| Kiểm tra | Câu hỏi cụ thể |
| --- | --- |
| Hợp đồng query | Mỗi nhóm API có partition key, giới hạn, SLO và mức độ mới dữ liệu rõ ràng chưa? |
| Đúng profile | Statement nào chọn profile nào? Có trường hợp dùng default vô tình không? |
| Precedence | Boot properties, profile config và statement overrides có xung đột không? |
| Timeout budget | Timeout driver có nằm trong deadline của API/job không? |
| RF và consistency | RF/DC có đáp ứng consistency đã chọn và SLO không? |
| Page size | Đã đo row byte/page và dữ liệu nhiều trang chưa? |
| Retry/idempotency | Những thao tác được retry có thật sự idempotent không? |
| Môi trường | Contact points, local DC, TLS/auth và keyspace có đúng không? |
| Metrics | Có p95/p99, timeout, unavailable, retry, speculative, page fetch latency không? |
| Rollback | Có thể quay về profile cũ nhanh chóng và kiểm tra lại kết quả không? |

Khi áp dụng cấu hình mới, nên canary một nhóm nhỏ traffic trước; kiểm tra cả **lỗi và áp lực cluster**, không chỉ latency client. Một profile giảm thời gian chờ người dùng nhưng khiến số retry tăng gấp nhiều lần có thể làm hệ thống kém ổn định hơn.

## 18. Bài tập thực hành

### Bài A — Nhận diện nguồn timeout

Một API dùng profile `timeline-read` timeout 800 ms. Người dùng thấy HTTP 504 sau 2 giây; log driver không ghi query timeout. Hãy chỉ ra những tầng có thể tạo 504, cần đo gì để phân biệt lỗi gateway/API với Cassandra driver, và vì sao tăng `REQUEST_TIMEOUT` lên 10 giây chưa chắc giải quyết được vấn đề.

### Bài B — Thiết kế profile theo hợp đồng

Cho ba luồng:

1. Trang lịch sử thiết bị: đọc một partition, 50 row, cho phép dữ liệu chưa mới nhất.
2. Ghi sự kiện quan trọng: cần quorum trong local DC, có retry idempotent theo `eventId`.
3. Xuất dữ liệu nền: đọc tối đa 7 bucket ngày, chia trang và giới hạn concurrency.

Hãy đề xuất tên profile, timeout thử nghiệm, consistency và page size cho từng luồng. Với mỗi thông số, giải thích **giả định cần đo** chứ không chỉ đưa con số.

### Bài C — Xác minh override

Profile `timeline-read` có `timeout=800ms`, `consistency=LOCAL_ONE`, `page-size=50`. Một statement chọn profile này rồi gọi:

~~~java
statement = statement
    .setTimeout(Duration.ofSeconds(2))
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(20);
~~~

Giá trị cuối cùng của ba tùy chọn là gì? Vì sao cần kiểm tra runtime resolved config và không nên cho phép tùy ý override ở mọi service?

### Bài D — Đánh giá query sai partition key

Bảng `events_by_device_day` có khóa `((device_id, event_day), event_time, event_id)`. Sản phẩm yêu cầu tìm mọi `BATTERY_LOW` trên toàn hệ thống trong ngày. Có nên tăng timeout/page size cho query theo `kind`? Hãy đề xuất một bảng đọc phù hợp hơn hoặc kiến trúc khác, nêu chi phí ghi thêm và ảnh hưởng tới consistency.

### Bài E — Timeout sau khi ghi

Client gửi một `INSERT`, nhận timeout rồi thử lại. Hãy mô tả cách thiết kế primary key dựa vào `deviceId`, `eventTime` và `eventId` để tránh tạo row trùng; trường hợp nào retry không an toàn (counter, list append, ID ngẫu nhiên mới, TTL đổi)? Phân biệt “client timeout” với “Cassandra chắc chắn không ghi”.

### Bài F — Phân trang

Repository đọc lịch sử một thiết bị bằng `Slice<DeviceEvent>`, page size 50. Hãy viết luồng lấy hai trang bằng `CassandraPageRequest.first(50)` và `nextPageable()`, sau đó chỉ ra vì sao `page=1000` kiểu SQL offset không phù hợp; thiết kế một cursor API chỉ có hiệu lực với cùng filter và bucket.

**Tiêu chí đạt:** người học giải thích được default/named profiles, thứ tự ưu tiên cấu hình, khác biệt request timeout và API deadline, cách consistency liên quan replica, cách page size khác `LIMIT`, quy tắc retry idempotent và giới hạn của profile đối với query-driven data modeling.

## Tài liệu tham khảo

- [Spring Boot — Data / NoSQL](https://docs.spring.io/spring-boot/reference/data/nosql.html): cấu hình Cassandra và extension points trong Boot.
- [Spring Data Cassandra — Reference](https://docs.spring.io/spring-data/cassandra/reference/): repository, `CassandraTemplate`, entity mapping và truy vấn.
- [Java Driver 4 — Configuration](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/configuration/): default/named execution profiles và cấu hình driver.
- [Java Driver 4 — Query Execution](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/): tùy chọn statement, timeout, consistency và paging.
- [Apache Cassandra — CQL Reference](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/cql_singlefile.html): `SELECT`, partition key, `LIMIT` và replication.
