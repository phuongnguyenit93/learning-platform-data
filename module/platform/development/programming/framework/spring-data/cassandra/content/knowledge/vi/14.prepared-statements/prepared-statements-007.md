# Execution profile cho từng nhóm truy vấn

Trong **Spring Data Cassandra**, một ứng dụng thường có nhiều nhóm thao tác trên Apache Cassandra: đọc một đơn hàng theo ID, lấy trang lịch sử mới nhất, ghi trạng thái nghiệp vụ và đôi khi đọc một tập dữ liệu lớn hơn để đối soát. Những thao tác này không nhất thiết có cùng thời gian phản hồi mong muốn, mức nhất quán hay kích thước trang. **Execution profile** của **Cassandra Java Driver 4** cho phép gom các tùy chọn thực thi thành cấu hình **có tên**, sau đó gắn tên đó vào từng CQL statement.

Bài học thuộc chương **Prepared statement** trong module **SPRING_DATA_CASSANDRA**. Chúng ta sẽ thiết kế bảng theo truy vấn, định nghĩa các profile cho nhóm đọc/ghi, dùng `PreparedStatement` và `BoundStatement`, tích hợp với `CqlTemplate` và phân biệt với các API entity của `CassandraTemplate`. Các vấn đề consistency, retry, idempotency, paging và hiệu năng được đặt trong đúng bối cảnh hệ dữ liệu phân tán.

> **Nguyên tắc xuyên suốt:** Execution profile điều khiển **cách driver thực thi** một request; nó **không thay đổi CQL**, không tạo index, không sửa partition key, không cô lập tài nguyên của cluster thành những hàng đợi riêng và không biến một truy vấn sai thiết kế thành truy vấn nhanh.

## 1. Vì sao cần execution profile?

Giả sử hệ thống thương mại có các nhóm truy vấn:

| Nhóm thao tác | Ví dụ nghiệp vụ | Mục tiêu khác biệt |
|---|---|---|
| **Point read** | Lấy một đơn hàng theo `tenant_id + order_id` | Truy vấn ngắn, giới hạn thời gian chờ |
| **Timeline read** | Lấy trang lịch sử đơn của một khách trong tháng | Có thể có nhiều hàng, cần kiểm soát page size |
| **State write** | Đổi trạng thái đơn hàng | Consistency và idempotency theo quy tắc nghiệp vụ |
| **Conditional write** | Chỉ đổi `NEW → PAID` nếu điều kiện thỏa | LWT, serial consistency và xử lý kết quả `[applied]` |

Nếu mọi câu lệnh đều sử dụng một timeout quá ngắn, truy vấn lịch sử có thể thất bại không cần thiết. Nếu mọi câu lệnh đều dùng timeout quá dài, API đọc một đơn có thể chờ lâu hơn SLA và giữ request đang bay trong hệ thống.

Thay vì rải các dòng `.setTimeout(...)`, `.setConsistencyLevel(...)` hoặc `.setPageSize(...)` khắp codebase, ta có thể:

1. Đặt các tùy chọn chung trong **default profile**.
2. Định nghĩa **named profiles** như `point_read`, `timeline_read`, `state_write`.
3. Gắn tên profile trên **mỗi statement phù hợp**.
4. Đo, kiểm tra hành vi và điều chỉnh bằng quy trình cấu hình có kiểm soát.

Đây là cơ chế của Java Driver, **không phải annotation riêng** của `@Table`, `@Query` hay `@PrimaryKey`.

## 2. Cơ chế kế thừa profile trong Java Driver 4

Driver luôn có một **default execution profile** không đặt tên. Các profile được đặt tên có thể **kế thừa** các tùy chọn chưa được khai báo từ default profile và ghi đè những tùy chọn cụ thể.

~~~text
datastax-java-driver
     |
     +-- default profile
     |     +-- timeout
     |     +-- consistency
     |     +-- page size
     |     +-- default idempotence
     |
     +-- point_read
     |     +-- override timeout
     |     +-- inherit các tùy chọn còn lại
     |
     +-- timeline_read
     |     +-- override timeout và page size
     |
     +-- state_write
           +-- override consistency và timeout
~~~

Khi một statement **không chỉ định profile**, driver dùng default profile. Khi có `setExecutionProfileName("timeline_read")`, các tùy chọn hiệu lực lấy từ profile đó, cộng các giá trị kế thừa.

**Thứ tự ưu tiên cần nhớ:** tùy chọn đặt rõ trên statement, chẳng hạn `bound.setTimeout(Duration.ofMillis(900))`, có thể ghi đè tùy chọn tương ứng trong execution profile. Không nên phụ thuộc vào những override ngầm này quá nhiều: profile nên là nguồn cấu hình chính, override từng statement chỉ dùng cho trường hợp thật sự đặc biệt và có kiểm chứng.

### 2.1. Những gì profile thường có thể cấu hình

| Tùy chọn driver | Khóa HOCON | Vai trò |
|---|---|---|
| Request timeout | `basic.request.timeout` | Giới hạn thời gian request ở tầng driver |
| Consistency | `basic.request.consistency` | Mức xác nhận replica cho lệnh CQL |
| Serial consistency | `basic.request.serial-consistency` | Mức serial consistency của câu lệnh điều kiện/LWT |
| Page size | `basic.request.page-size` | Số hàng driver yêu cầu mỗi lần fetch |
| Default idempotence | `basic.request.default-idempotence` | Giá trị mặc định khi statement chưa đánh dấu idempotent |

Một số tùy chọn chính sách nâng cao cũng hỗ trợ cấu hình theo profile, nhưng **không phải mọi tùy chọn đều cho phép override theo profile**. Đặc biệt không nên mặc định tạo rất nhiều profile với chính sách load-balancing/connection khác nhau: điều đó có thể tăng chi phí tài nguyên và vận hành. Hãy kiểm tra **reference configuration** ứng với phiên bản driver cụ thể trước khi chọn tùy chọn nâng cao.

**Timeout ngắn không làm CQL nhanh hơn**: nó chỉ khiến request thất bại sớm hơn nếu không đạt giới hạn. **Page size nhỏ không sửa hot partition**. **Consistency cao hơn không thay thế một giao dịch ACID nhiều bảng**.

## 3. Thiết kế query pattern và bảng trước khi chia profile

Chúng ta sử dụng hai bảng vì hai đường đọc khác nhau.

### 3.1. Bảng tra một đơn hàng theo ID

~~~sql
CREATE TABLE orders_by_id (
    tenant_id uuid,
    order_id uuid,
    status text,
    total_amount decimal,
    updated_at timestamp,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

Truy vấn point read có đủ composite partition key:

~~~sql
SELECT status, total_amount, updated_at
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
~~~

Vì `(tenant_id, order_id)` là toàn bộ primary key, truy vấn định vị đúng một hàng. Các dấu `?` là bind markers của prepared statement, không phải chuỗi được nối từ dữ liệu người dùng.

### 3.2. Bảng đọc lịch sử theo khách hàng/tháng

~~~sql
CREATE TABLE orders_by_customer_month (
    tenant_id uuid,
    customer_id uuid,
    month_bucket date,
    created_at timestamp,
    order_id uuid,
    status text,
    PRIMARY KEY (
        (tenant_id, customer_id, month_bucket),
        created_at, order_id
    )
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

Truy vấn timeline read:

~~~sql
SELECT created_at, order_id, status
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?;
~~~

Partition key là bộ ba `(tenant_id, customer_id, month_bucket)`; bên trong partition, hàng được sắp theo `created_at DESC` rồi `order_id ASC`. Đọc lịch sử nhiều tháng nghĩa là đọc **nhiều partition**; một profile có page size nhỏ không gộp chúng thành một cursor toàn cục.

### 3.3. Lệnh thay đổi trạng thái

~~~sql
UPDATE orders_by_id
SET status = ?, updated_at = ?
WHERE tenant_id = ? AND order_id = ?;
~~~

Lệnh này sửa cột thường tại **một primary key xác định**, nhưng `UPDATE` vô điều kiện của Cassandra có **ngữ nghĩa upsert**: nếu hàng chưa có, nó có thể tạo hàng. Khi nghiệp vụ yêu cầu “phải tồn tại và trạng thái cũ phải là NEW”, cần lệnh điều kiện như:

~~~sql
UPDATE orders_by_id
SET status = ?, updated_at = ?
WHERE tenant_id = ? AND order_id = ?
IF status = 'NEW';
~~~

**Profile không làm thay đổi semantics của `UPDATE` hay `IF`**. Nó chỉ áp dụng các tùy chọn thực thi như timeout và consistency cho statement được chọn.

## 4. Định nghĩa các named profiles bằng HOCON

Java Driver 4 mặc định dùng **Typesafe Config / HOCON**. Một vị trí phổ biến là `src/main/resources/application.conf` trên classpath, với nội dung thuộc namespace `datastax-java-driver`.

~~~hocon
datastax-java-driver {
  # Cấu hình chung: các profile được đặt tên kế thừa các giá trị
  # không được ghi đè ở phía dưới.
  basic.request {
    timeout = 2 seconds
    consistency = LOCAL_ONE
    page-size = 500
    default-idempotence = false
  }

  profiles {
    point_read {
      basic.request.timeout = 500 milliseconds
      basic.request.consistency = LOCAL_ONE
      basic.request.page-size = 50
    }

    timeline_read {
      basic.request.timeout = 3 seconds
      basic.request.consistency = LOCAL_ONE
      basic.request.page-size = 100
    }

    state_write {
      basic.request.timeout = 2 seconds
      basic.request.consistency = LOCAL_QUORUM
      basic.request.default-idempotence = false
    }

    conditional_write {
      basic.request.timeout = 5 seconds
      basic.request.consistency = LOCAL_QUORUM
      basic.request.serial-consistency = LOCAL_SERIAL
      basic.request.default-idempotence = false
    }
  }
}
~~~

Các timeout, consistency và page size trên là **giá trị minh họa**, không phải ngưỡng khuyến nghị cố định. Chúng chỉ hợp lệ sau khi đã xem replication factor, datacenter, dữ liệu, network latency và SLA của ứng dụng. Ví dụ `LOCAL_QUORUM` có ý nghĩa khác nhau theo số replica được cấu hình trong DC cục bộ.

Lưu ý:

- `point_read` và `timeline_read` ghi đè timeout/page size và dùng `LOCAL_ONE` theo ví dụ; hai profile không thay đổi partition key.
- `state_write` đặt `LOCAL_QUORUM` và giữ default idempotence ở `false` để ứng dụng **chủ động** xác định statement ghi nào thực sự idempotent.
- `conditional_write` có thêm `LOCAL_SERIAL` cho LWT. Serial consistency chỉ liên quan câu lệnh điều kiện hỗ trợ; nó không biến `UPDATE` vô điều kiện thành LWT.
- `basic.request.page-size` tính theo **số hàng**, không phải số byte. Nó không tương đương `LIMIT` của CQL.
- Khi một profile không khai báo thuộc tính, thuộc tính hiệu lực đến từ default profile và cấu hình driver còn lại.

### 4.1. HOCON và Spring Boot YAML là hai tầng khác nhau

Spring Boot thường cấu hình kết nối bằng các thuộc tính như:

~~~yaml
# application.yml — kết nối đến cluster trong Spring Boot 3.x
spring:
  cassandra:
    contact-points:
      - cass-1.internal:9042
      - cass-2.internal:9042
    local-datacenter: dc1
    keyspace-name: app_data
    username: ${CASSANDRA_USERNAME}
    password: ${CASSANDRA_PASSWORD}
~~~

Trong khi đó, `application.conf` ở trên mô tả **các profile của driver**. Đừng tự ý đổi tiền tố `datastax-java-driver` thành `spring.cassandra.profiles` rồi giả định Spring Boot sẽ hiểu.

Khi ứng dụng dùng cấu hình session/custom driver loader, việc nạp HOCON, thứ tự override với thuộc tính Spring Boot và nguồn cấu hình cuối cùng có thể khác nhau. Vì vậy cần **kiểm tra profile thực tế từ `CqlSession`** (xem phần 5), không chỉ kiểm file đã có trong resources. Trong Spring Boot 2.x một số tên thuộc tính kết nối còn khác phiên bản 3.x.

Không đặt username/password thật trong ví dụ, file commit hoặc log. Một profile cũng **không phải** cơ chế phân quyền hoặc cô lập tenant.

## 5. Kiểm chứng profile đã được driver nạp

Trước khi gửi request sản xuất, có thể đọc cấu hình hiệu lực qua `CqlSession`:

~~~java
import java.time.Duration;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverConfig;
import com.datastax.oss.driver.api.core.config.DriverExecutionProfile;

public class ProfileInspector {

    public static void verify(CqlSession session) {
        DriverConfig config = session.getContext().getConfig();

        DriverExecutionProfile point = config.getProfile("point_read");
        DriverExecutionProfile timeline = config.getProfile("timeline_read");

        Duration pointTimeout =
                point.getDuration(DefaultDriverOption.REQUEST_TIMEOUT);
        int timelinePageSize =
                timeline.getInt(DefaultDriverOption.REQUEST_PAGE_SIZE);

        if (!Duration.ofMillis(500).equals(pointTimeout)) {
            throw new IllegalStateException("point_read timeout mismatch");
        }
        if (timelinePageSize != 100) {
            throw new IllegalStateException("timeline_read page size mismatch");
        }
    }
}
~~~

`config.getProfile("...")` sẽ không tạo profile mới khi thiếu tên hợp lệ; nên xác minh ngay trong integration test hoặc startup validation của dự án để phát hiện typo như `point-read` thay cho `point_read`.

Ngoài timeout và page size, hãy kiểm tra **consistency hiệu lực**, serial consistency, idempotence mặc định và hành vi tải HOCON đúng với môi trường. Khi đưa profile mới lên production, tránh chỉ dựa vào việc code vẫn biên dịch: statement với tên profile sai có thể thất bại khi thực thi.

## 6. Chọn execution profile trên BoundStatement

**Prepared statement** được chuẩn bị từ một CQL cố định và có thể dùng lại với nhiều giá trị tham số. **Bound statement** giữ các giá trị đã bind và tùy chọn của **một request cụ thể**, bao gồm tên execution profile.

~~~mermaid
flowchart LR
    A[CQL có bind markers] --> B[session.prepare]
    B --> C[PreparedStatement dùng lại]
    C --> D1[bind tenant A / order X]
    C --> D2[bind tenant B / order Y]
    D1 --> E1[BoundStatement + point_read]
    D2 --> E2[BoundStatement + point_read]
    E1 --> F[CqlSession.execute]
    E2 --> F
~~~

### 6.1. Đọc một đơn với `point_read`

Một DAO sử dụng `CqlSession` dùng chung và chuẩn bị statement khi được khởi tạo:

~~~java
package example.orders;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class OrderPointReader {
    private final CqlSession session;
    private final PreparedStatement selectById;

    public OrderPointReader(CqlSession session) {
        this.session = session;
        this.selectById = session.prepare(
                "SELECT status, total_amount, updated_at " +
                "FROM orders_by_id WHERE tenant_id = ? AND order_id = ?");
    }

    public Optional<OrderView> find(UUID tenantId, UUID orderId) {
        BoundStatement bound = selectById.bind(tenantId, orderId)
                .setExecutionProfileName("point_read")
                .setIdempotent(true);

        Row row = session.execute(bound).one();
        if (row == null) {
            return Optional.empty();
        }

        return Optional.of(new OrderView(
                orderId,
                row.getString("status"),
                row.getBigDecimal("total_amount"),
                row.getInstant("updated_at")));
    }

    public record OrderView(
            UUID orderId, String status, BigDecimal totalAmount,
            Instant updatedAt) {
    }
}
~~~

`PreparedStatement` được giữ để tái sử dụng; **mỗi lượt đọc sinh một `BoundStatement` mới** với `tenantId`, `orderId` cụ thể. Profile được đặt trên bound statement **trước khi gọi `execute`**.

Java Driver 4 dùng kiểu statement **bất biến** cho các triển khai dựng sẵn: `setExecutionProfileName` và `setIdempotent` trả về **một instance mới**, không sửa trực tiếp biến cũ. Nếu viết:

~~~java
BoundStatement bound = selectById.bind(tenantId, orderId);
bound.setExecutionProfileName("point_read"); // Bỏ qua giá trị trả về: sai.
session.execute(bound);                     // Vẫn có thể dùng default profile.
~~~

thì tên profile có thể **không được áp dụng**. Phải viết:

~~~java
bound = bound.setExecutionProfileName("point_read");
session.execute(bound);
~~~

Trong ví dụ đọc một đơn, `setIdempotent(true)` hợp lý vì câu `SELECT` này không gây mutation. Tuy nhiên **đọc cùng một partition** không nhất thiết trả cùng dữ liệu nếu writer cập nhật đồng thời: idempotence ở đây nói về **tác dụng của việc thực thi lặp lại**, không phải snapshot bất biến.

### 6.2. Cùng PreparedStatement có thể dùng profile khác

`PreparedStatement` mô tả CQL và metadata của các bind markers. Tên profile thuộc request/statement; cùng prepared statement có thể bind nhiều lần và gắn profile khác nhau khi nghiệp vụ thật sự yêu cầu:

~~~java
BoundStatement standardRead = selectById.bind(tenantId, orderId)
        .setExecutionProfileName("point_read");

BoundStatement slowerDiagnosticRead = selectById.bind(tenantId, orderId)
        .setExecutionProfileName("timeline_read");
~~~

Đây chỉ minh họa cơ chế. Không nên tùy tiện chọn profile `timeline_read` cho point read trong production nếu chưa có lý do và benchmark. Profile là **chính sách thực thi**; chuẩn bị lại nguyên CQL chỉ để thay timeout thường không cần thiết.

### 6.3. Dùng `setExecutionProfile` khi đã có object

Driver còn hỗ trợ:

~~~java
DriverExecutionProfile profile =
        session.getContext().getConfig().getProfile("point_read");

BoundStatement bound = selectById.bind(tenantId, orderId)
        .setExecutionProfile(profile);
~~~

`setExecutionProfileName(String)` thường đơn giản khi profile đã được khai báo trong HOCON. `setExecutionProfile(DriverExecutionProfile)` hữu ích khi cần truyền object đã được lấy từ cấu hình. Tránh tự sinh hàng nghìn derived profiles cho từng request; mỗi profile phái sinh có thể tăng chi phí cấu hình và khó quan sát.

## 7. Profile cho lịch sử và phân trang

Với bảng `orders_by_customer_month`, chuẩn bị truy vấn cố định và gắn `timeline_read`:

~~~java
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public class OrderTimelineReader {
    private final CqlSession session;
    private final PreparedStatement byCustomerMonth;

    public OrderTimelineReader(CqlSession session) {
        this.session = session;
        this.byCustomerMonth = session.prepare(
                "SELECT created_at, order_id, status " +
                "FROM orders_by_customer_month " +
                "WHERE tenant_id = ? AND customer_id = ? " +
                "AND month_bucket = ?");
    }

    public ResultSet execute(
            UUID tenantId, UUID customerId, LocalDate firstDayOfMonth) {
        BoundStatement request =
                byCustomerMonth.bind(tenantId, customerId, firstDayOfMonth)
                        .setExecutionProfileName("timeline_read")
                        .setIdempotent(true);

        return session.execute(request);
    }
}
~~~

Trong cấu hình minh họa, `timeline_read` có `page-size = 100`. Điều đó nghĩa là driver yêu cầu dữ liệu theo **trang có mục tiêu 100 hàng**, **không phải** tự động giới hạn toàn bộ kết quả ở 100 hàng. Khi duyệt `ResultSet` đồng bộ, driver có thể tự fetch các trang tiếp theo.

Nếu API yêu cầu **tối đa 50 đơn mới nhất**, CQL có thể thêm `LIMIT 50` vào câu được prepare. Nếu API yêu cầu một cursor nhiều trang, phải sử dụng **paging state** và chỉ tiêu thụ phần trang phù hợp. Đừng chỉ `setPageSize(50)` rồi duyệt toàn bộ `ResultSet` và nghĩ rằng chỉ có 50 hàng.

| Khái niệm | Vai trò | Không làm được |
|---|---|---|
| `LIMIT 50` | Giới hạn tổng số hàng của truy vấn | Không phải cursor trang kế tiếp |
| Profile `page-size = 100` | Kích thước yêu cầu trang mặc định của driver | Không hạn chế tổng số hàng |
| Statement `.setPageSize(50)` | Override page size cho một request | Không bảo đảm chỉ có một lần network fetch |
| Paging state | Theo dõi vị trí tiếp tục của một truy vấn phù hợp | Không dùng chung tùy ý giữa customer, tháng hoặc CQL khác |

**Không có OFFSET theo kiểu SQL quan hệ để nhảy trực tiếp tới trang 10000.** Nếu muốn duyệt nhiều tháng hoặc nhiều partition, ứng dụng phải quản lý cursor của từng truy vấn và cách hợp nhất kết quả. Profile không tự tạo một thứ tự toàn cục giữa các partition.

### 7.1. Thứ tự ưu tiên khi có page size ở statement

~~~java
BoundStatement request =
        byCustomerMonth.bind(tenantId, customerId, firstDayOfMonth)
                .setExecutionProfileName("timeline_read")
                .setPageSize(25); // Ghi đè page-size = 100 của profile.
~~~

Phương thức `setPageSize(25)` hữu ích khi một endpoint đã xác định page size riêng và có kiểm soát. Nhưng đặt nhiều override khác nhau khắp service sẽ làm mất lợi ích quản lý tập trung của named profiles; nên thống nhất chính sách ở tầng API.

## 8. Profile cho thao tác ghi: consistency không phải idempotency

Ví dụ lệnh ghi:

~~~sql
UPDATE orders_by_id
SET status = ?, updated_at = ?
WHERE tenant_id = ? AND order_id = ?;
~~~

Đặt profile `state_write`:

~~~java
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public class OrderStateWriter {
    private final CqlSession session;
    private final PreparedStatement updateState;

    public OrderStateWriter(CqlSession session) {
        this.session = session;
        this.updateState = session.prepare(
                "UPDATE orders_by_id SET status = ?, updated_at = ? " +
                "WHERE tenant_id = ? AND order_id = ?");
    }

    public void write(UUID tenantId, UUID orderId,
                      String status, Instant fixedUpdatedAt) {
        BoundStatement request = updateState.bind(
                status, fixedUpdatedAt, tenantId, orderId)
                .setExecutionProfileName("state_write")
                .setIdempotent(true);

        session.execute(request);
    }
}
~~~

Ở đây chỉ gắn `setIdempotent(true)` khi **cùng command** thực sự gửi lại **cùng khóa, trạng thái và timestamp đã được cố định trước đó**, không có counter/list append hoặc thao tác tạo ID mới. Không sinh `Instant.now()` bên trong mỗi lần retry để rồi cho rằng request không đổi.

Tuy nhiên, idempotence không đồng nghĩa **an toàn trước mọi race condition**. Nếu các trạng thái `NEW → PAID → SHIPPED` được nhiều writer gửi không theo thứ tự, một lệnh ghi `PAID` cũ có thể đến muộn. Khi cần ràng buộc tiến trình trạng thái, phải bổ sung version/conditional write và cơ chế đồng bộ phù hợp.

### 8.1. Khi nào không được đặt idempotent=true?

| Statement | Có nên đánh dấu idempotent? | Lý do |
|---|---|---|
| `SELECT ... WHERE full_partition_key` | Thông thường **có** | Đọc không tạo mutation |
| `UPDATE ... SET status = 'PAID'` cùng khóa/payload | Có thể, nếu không có ngữ nghĩa cạnh tranh đặc biệt | Ghi lại cùng giá trị theo command |
| `UPDATE counter = counter + 1` | **Không** | Chạy hai lần tăng hai lần |
| `UPDATE list_col = list_col + [value]` | **Không** | Retry có thể thêm trùng |
| `INSERT` với `now()` hoặc UUID mới mỗi lần retry | **Không** theo logic command | Mỗi lần có thể tạo khóa khác |
| LWT phụ thuộc trạng thái hiện tại | Cần đánh giá riêng | Retry có thể nhận `[applied]=false` sau lần đầu thành công |

Driver có tùy chọn `basic.request.default-idempotence` để xác định giá trị mặc định khi statement **chưa** được đánh dấu. Đặt mặc định `false` là lựa chọn phòng thủ; trên statement được chứng minh an toàn, đặt `setIdempotent(true)` rõ ràng. Idempotence liên quan đến khả năng driver retry/speculative execution; đánh dấu sai có thể dẫn đến thay đổi dữ liệu ngoài dự kiến.

## 9. Conditional write và serial consistency

LWT hỗ trợ thao tác có điều kiện:

~~~sql
UPDATE orders_by_id
SET status = ?, updated_at = ?
WHERE tenant_id = ? AND order_id = ?
IF status = 'NEW';
~~~

Với `conditional_write`, HOCON ví dụ có:

~~~hocon
profiles {
  conditional_write {
    basic.request.timeout = 5 seconds
    basic.request.consistency = LOCAL_QUORUM
    basic.request.serial-consistency = LOCAL_SERIAL
  }
}
~~~

`LOCAL_SERIAL` phục vụ **pha serial** của thao tác LWT trong datacenter phù hợp. `LOCAL_QUORUM` ở đây là consistency thông thường của statement. Cả hai phải phù hợp với replication, topology và yêu cầu tính nhất quán; không phải giá trị hợp lệ tuyệt đối cho mọi cluster.

Ví dụ:

~~~java
import com.datastax.oss.driver.api.core.cql.Row;

PreparedStatement transition = session.prepare(
        "UPDATE orders_by_id SET status = ?, updated_at = ? " +
        "WHERE tenant_id = ? AND order_id = ? IF status = 'NEW'");

BoundStatement command =
        transition.bind("PAID", fixedUpdatedAt, tenantId, orderId)
                .setExecutionProfileName("conditional_write");

Row outcome = session.execute(command).one();
if (outcome == null) {
    throw new IllegalStateException("Missing LWT result");
}

boolean applied = outcome.getBoolean("[applied]");
if (!applied) {
    // Trạng thái hiện tại không thỏa điều kiện hoặc dữ liệu đã thay đổi.
    // Xử lý domain conflict / retry theo quy tắc nghiệp vụ.
}
~~~

Không diễn giải `applied=false` thành “lệnh ghi chắc chắn chưa từng thành công ở lần thử trước”. Nếu lần đầu thành công nhưng response bị mất, lần retry có thể gặp trạng thái `PAID` và trả false. Cần idempotency key, đọc lại trạng thái hoặc quy trình đối soát theo hợp đồng nghiệp vụ.

**Profile không biến UPDATE vô điều kiện thành LWT**: phần `IF` phải xuất hiện trong CQL. Ngược lại, chỉ gắn profile `conditional_write` lên một `SELECT` không tạo hành vi compare-and-set.

## 10. Dùng execution profile từ CqlTemplate

Trong Spring Data Cassandra, `CqlTemplate`/`CqlOperations` làm việc với CQL và `RowMapper`. Khi cần điều khiển chính xác profile trên từng statement, có thể tự prepare/bind bằng Java Driver rồi truyền **`BoundStatement`** vào overload `query(Statement<?>, RowMapper<T>)` của `CqlOperations`.

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import org.springframework.data.cassandra.core.cql.CqlOperations;
import org.springframework.data.cassandra.core.cql.RowMapper;

public class OrderCqlReader {
    public record OrderSnapshot(
            String status, BigDecimal totalAmount, Instant updatedAt) {}

    private static final RowMapper<OrderSnapshot> MAPPER = (row, index) ->
            new OrderSnapshot(
                    row.getString("status"),
                    row.getBigDecimal("total_amount"),
                    row.getInstant("updated_at"));

    private final CqlOperations cql;
    private final PreparedStatement byId;

    public OrderCqlReader(CqlOperations cql, CqlSession session) {
        this.cql = cql;
        this.byId = session.prepare(
                "SELECT status, total_amount, updated_at " +
                "FROM orders_by_id WHERE tenant_id = ? AND order_id = ?");
    }

    public List<OrderSnapshot> find(UUID tenantId, UUID orderId) {
        BoundStatement bound = byId.bind(tenantId, orderId)
                .setExecutionProfileName("point_read")
                .setIdempotent(true);

        return cql.query(bound, MAPPER);
    }
}
~~~

Overload `cql.query(bound, MAPPER)` thực thi statement do ứng dụng cung cấp; các thuộc tính đã gắn trên `BoundStatement` được truyền qua đường gọi trực tiếp tới driver. Việc chọn statement có sẵn cũng cho phép kiểm soát rõ ràng bind markers, thay vì nối trực tiếp các giá trị người dùng vào chuỗi CQL.

Spring Data Cassandra còn hỗ trợ overload với `PreparedStatementCreator` và `PreparedStatementBinder`, ví dụ:

~~~java
List<OrderSnapshot> rows = cql.query(
        session -> session.prepare(
                "SELECT status, total_amount, updated_at " +
                "FROM orders_by_id WHERE tenant_id = ? AND order_id = ?"),
        ps -> ps.bind(tenantId, orderId)
                .setExecutionProfileName("point_read")
                .setIdempotent(true),
        MAPPER);
~~~

Mẫu này vẫn giữ `CqlTemplate` thực hiện mapping/exception translation. Java Driver 4 có cache cho prepared statements nên prepare cùng query cố định không nhất thiết gửi lại PREPARE tới server mỗi lần; tuy vậy, một DAO/bean giữ statement cố định vẫn giúp code thể hiện rõ quyền sở hữu và ý định.

### 10.1. Còn CassandraTemplate và repository?

`CassandraTemplate`/`CassandraOperations` làm việc ở mức entity, thường tự sinh CQL và sử dụng prepared statements. Repository xây trên các abstraction đó. Nhưng **không mặc nhiên có một annotation `@Query(profile="point_read")` phổ quát** làm driver tự chọn named profile.

Khi profile là yêu cầu của một truy vấn riêng:

- Dùng `CqlOperations` với `BoundStatement` đã chọn profile như ví dụ.
- Hoặc dùng `CqlSession` trực tiếp với prepared/bound statement.
- Với `CassandraTemplate` phiên bản đang dùng, kiểm tra rõ overload `Statement` và cách template prepare/bind để tránh giả định rằng mọi tùy chọn gắn trên `SimpleStatement` luôn được bảo toàn.
- Tổ chức lớp DAO hoặc custom repository phân nhóm truy vấn để profile không bị bỏ sót.

**Điều quan trọng:** sử dụng profile trong một đoạn code phải được **kiểm chứng thực tế**. Nếu chỉ gọi `template.select(Query, Entity.class)`, không thể tự kết luận statement bên dưới đã mang tên `timeline_read` chỉ vì tên service là TimelineService.

## 11. Thứ tự ưu tiên và những hiểu lầm về profile

Một request có thể nhận thông số từ nhiều nơi:

~~~text
Driver configuration:
   default profile
        |
        v
   named profile (nếu có)
        |
        v
   tùy chọn đặt trực tiếp trên Statement (nếu có)
        |
        v
   request gửi tới cluster
~~~

| Tình huống | Kết quả mong đợi |
|---|---|
| Không đặt tên profile | Dùng default profile |
| `setExecutionProfileName("point_read")` | Dùng named profile đó |
| `point_read` không khai báo page size | Kế thừa page size từ default |
| Bound statement gắn profile rồi `.setPageSize(10)` | Page size của statement được ưu tiên |
| Có profile timeout 500ms, server đang chậm | Request có thể timeout; server không tự nhanh hơn |
| Profile `LOCAL_QUORUM` nhưng keyspace thiếu replica khả dụng | Request có thể thất bại vì không đạt consistency |
| Gắn profile lên query thiếu partition key | Cassandra vẫn có thể từ chối hoặc query rất tốn kém |
| Tạo 100 profile chỉ khác timeout nhỏ lẻ | Làm phức tạp cấu hình/quan sát, chưa chắc tăng hiệu năng |

Không nên coi tên profile là **nhãn nghiệp vụ** được Cassandra hiểu. Cluster không biết `point_read` nghĩa là “SLA dưới 100ms”; driver chỉ áp dụng những tùy chọn đã được định nghĩa.

### 11.1. Request timeout và khởi tạo session

Request timeout của driver liên quan thời gian thực thi **một request**; nó không thay thế cấu hình connect timeout, TLS handshake, authentication hoặc session initialization. Một lỗi do contact points không truy cập được, local datacenter sai hay keyspace chưa tồn tại không được khắc phục bằng cách tăng `point_read.basic.request.timeout`.

### 11.2. Profile không thay thế quản lý tài nguyên ứng dụng

Nếu 10.000 request `timeline_read` cùng được gửi tới một hot partition, dù page size nhỏ vẫn có thể gây áp lực lớn lên Cassandra. Cần giới hạn concurrency, backpressure/rate limit, time bucketing, phù hợp partition key, timeout và cơ chế retry có kiểm soát.

Nhóm truy vấn nặng có thể cần worker pool/bộ giới hạn tải riêng ở ứng dụng hoặc dịch vụ xử lý khác. Execution profile **không tự dành riêng CPU, I/O hay replica** cho nhóm ấy.

## 12. Kiểm thử và quan sát hiệu năng theo profile

Để chứng minh profile hoạt động đúng, không chỉ kiểm tra có tên trong file cấu hình. Một kế hoạch validation có thể chia ba lớp:

### 12.1. Kiểm tra cấu hình

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.time.Duration;
import org.junit.jupiter.api.Test;

// Trong một integration test có inject CqlSession session:
@Test
void namedProfilesHaveExpectedSettings() {
    var config = session.getContext().getConfig();

    assertEquals(
            Duration.ofMillis(500),
            config.getProfile("point_read")
                    .getDuration(DefaultDriverOption.REQUEST_TIMEOUT));

    assertEquals(
            100,
            config.getProfile("timeline_read")
                    .getInt(DefaultDriverOption.REQUEST_PAGE_SIZE));
}
~~~

Đây là **khung test minh họa**: cần các import, fixture session và cấu hình HOCON được nạp trong test. Nó chưa phải kết quả test đã chạy trong phạm vi STEP 4.

### 12.2. Kiểm tra câu CQL thực thi

- Seed dữ liệu vào `orders_by_id` và `orders_by_customer_month` với cùng `tenant_id`, nhiều khách và nhiều tháng.
- Với `point_read`, đọc đúng một hàng theo `(tenant_id, order_id)`; không quét toàn bảng.
- Với `timeline_read`, đọc đúng một partition, kiểm tra thứ tự clustering và trang tiếp theo nếu có.
- Với `state_write`, cố tình thử retry **cùng ID/payload**, rồi kiểm tra cả các access tables cần được cập nhật.
- Với `conditional_write`, kiểm tra `[applied]` ở cả trường hợp trạng thái đúng và sai, cùng trường hợp timeout có kết quả chưa rõ.
- So sánh kết quả qua CQL trực tiếp và `CassandraTemplate` nếu cùng bảng/đường đọc.

Test dùng CQL/Java Driver thực hoặc Cassandra instance dành cho integration test. Unit test chỉ mock `CqlSession` chưa chứng minh HOCON được nạp, keyspace tồn tại hay consistency được cluster áp dụng.

### 12.3. Theo dõi theo nhóm truy vấn

| Chỉ số | Nhóm nào cần quan sát | Cách sử dụng |
|---|---|---|
| p50/p95/p99 latency | Mọi profile | So với SLO tương ứng, không chỉ so giá trị trung bình |
| Timeout/error rate | Point read, timeline, write | Phân biệt timeout, unavailable, lỗi bind và lỗi schema |
| Số request đang bay | Timeline và nhóm nặng | Kiểm tra giới hạn tải và backpressure |
| Số trang/fetch | Timeline read | Kiểm tra page size và kích thước payload |
| Retry/speculative execution | Nhóm được phép idempotent | Tránh amplification khi cluster chậm |
| Hot partitions/tombstones | Những đường đọc có lịch sử dài | Xem lại mô hình bảng, bucket và TTL |
| LWT latency và `[applied]` | Conditional write | Tách conflict hợp lệ khỏi lỗi hạ tầng |

Thống kê nên được gắn vào tên **nhóm truy vấn hoặc profile** với cardinality được kiểm soát. Không gắn trực tiếp `customerId`, `orderId` hoặc giá trị nhạy cảm vào metrics label. Khi benchmark, thay đổi một nhóm tùy chọn có chủ đích, ghi nhận trước/sau và đo cả tài nguyên cluster chứ không chỉ độ trễ tại client.

## 13. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Có profile trong HOCON nhưng không đặt trên statement | Request chạy theo default | Gắn `setExecutionProfileName` trên bound statement |
| Gọi setter nhưng bỏ qua object trả về | Statement cũ không đổi | Reassign hoặc chain các setter |
| Sai tên profile `point-read`/`point_read` | Không chọn được profile đã cấu hình | Kiểm tra runtime `getProfile(name)` và test |
| Dùng `setPageSize(50)` như `LIMIT 50` | Driver có thể fetch thêm nhiều trang | Dùng CQL LIMIT hoặc cursor paging đúng nghĩa |
| Tăng timeout để sửa truy vấn thiếu partition key | Hệ thống vẫn quét dữ liệu hoặc timeout | Sửa schema/đường truy vấn |
| Đánh dấu mọi write là idempotent | Counter/list append có thể bị lặp | Đánh giá từng CQL/command |
| Dùng LWT nhưng bỏ qua `[applied]` | Không phân biệt conflict với thành công | Đọc kết quả điều kiện và xử lý nghiệp vụ |
| Mặc định `LOCAL_QUORUM` là luôn có 2 replica | Sai nếu RF/topology khác | Kiểm tra replication trong local DC |
| Cho rằng Spring repository tự chọn profile | Query không có profile mong đợi | Custom repository/DAO với statement được kiểm soát |
| Quá nhiều profile gần giống nhau | Khó maintain, đo và triển khai | Phân nhóm theo SLA/semantics thật |
| Nhầm `request.timeout` với connect timeout | Chẩn đoán sai lỗi bootstrap | Kiểm tra từng tầng kết nối và driver |
| Thử nghiệm trên production không có rate limit | Làm tăng tải/độ trễ của cluster | Benchmark trong môi trường có kiểm soát |

## 14. Bài tập thực hành

Một hệ thống logistics có ba yêu cầu:

~~~text
GET  /packages/{packageId}                    → xem trạng thái hiện tại
GET  /packages/{packageId}/scans?day=2026-11-25 → 50 lần quét mới nhất
POST /packages/{packageId}/scans                → ghi sự kiện quét
~~~

Hai bảng tương ứng:

~~~sql
CREATE TABLE packages_by_id (
    package_id uuid PRIMARY KEY,
    state text,
    updated_at timestamp
);

CREATE TABLE scans_by_package_day (
    package_id uuid,
    scan_day date,
    scanned_at timestamp,
    scan_id uuid,
    hub_id uuid,
    PRIMARY KEY ((package_id, scan_day), scanned_at, scan_id)
) WITH CLUSTERING ORDER BY (scanned_at DESC, scan_id ASC);
~~~

Hãy:

1. Thiết kế named profiles `package_point_read`, `package_timeline_read`, `package_write` dựa trên ba nhóm thao tác, với timeout và page size minh họa.
2. Viết `PreparedStatement` cho point read, timeline và insert event; chỉ ra đúng thành phần partition key của từng bảng.
3. Trên mỗi `BoundStatement`, gọi `setExecutionProfileName(...)` và giải thích vì sao phải giữ object trả về.
4. Đánh giá idempotence của `INSERT` khi retry dùng **cùng** `scan_id` và `scanned_at`, so với sinh `scan_id` mới trên mỗi lượt thử.
5. Phân biệt `setPageSize(50)` với `LIMIT 50` nếu API chỉ cần 50 sự kiện mới nhất.
6. Giải thích vì sao nếu một package có hàng triệu lần quét/ngày, sửa timeout không đủ; hãy đề xuất bucket theo giờ hoặc shard có cân nhắc chi phí đọc.

Một hướng giải khởi đầu:

~~~java
PreparedStatement scanQuery = session.prepare(
        "SELECT scanned_at, scan_id, hub_id FROM scans_by_package_day " +
        "WHERE package_id = ? AND scan_day = ? LIMIT 50");

BoundStatement request = scanQuery.bind(packageId, scanDay)
        .setExecutionProfileName("package_timeline_read")
        .setIdempotent(true);

ResultSet result = session.execute(request);
// Tiêu thụ tối đa 50 hàng vì CQL đã có LIMIT 50.
~~~

`packageId` là `UUID`, `scanDay` là `LocalDate` và `session` là `CqlSession` đã được tạo sẵn. Khi triển khai, phải khai báo profile `package_timeline_read` trong driver config (khác tên ví dụ `timeline_read` ở phần trước) và kiểm tra đã được nạp.

### Câu hỏi tự kiểm tra

1. Execution profile nằm trong Spring Data annotation hay Cassandra Java Driver?
2. Nếu `timeline_read` không khai báo `default-idempotence`, nó lấy từ đâu?
3. `BoundStatement.setExecutionProfileName(...)` có sửa tại chỗ object cũ không?
4. Một prepared statement có thể được bind nhiều lần cho nhiều tenant và profile khác nhau không?
5. Profile với page size 100 có tự chặn truy vấn sau đúng 100 hàng không?
6. Dùng `LOCAL_QUORUM` có tự biến ghi hai bảng projection thành một giao dịch không?
7. Vì sao không nên đánh dấu phép tăng counter là idempotent?
8. Tại sao timeout dài hơn không giúp truy vấn `WHERE status=?` trên bảng không có đường đọc theo status?
9. Lệnh LWT có cần đọc `[applied]` không?

**Gợi ý đáp án:** (1) Java Driver; (2) default profile; (3) không với các statement dựng sẵn của Driver 4, phải nhận object trả về; (4) có; (5) không, driver có thể fetch trang tiếp; (6) không; (7) retry tăng thêm; (8) vì chi phí truy cập/schema không thay đổi; (9) có, để phân biệt thao tác được áp dụng hay không.

## 15. Checklist khi đưa profile vào production

- [ ] Đã phân loại truy vấn theo nhu cầu nghiệp vụ, SLA và đặc tính tải, không theo tên API tùy ý.
- [ ] Bảng truy cập có partition key và clustering columns phù hợp từng nhóm truy vấn.
- [ ] Default profile có timeout, consistency, page size và idempotence mặc định được quyết định rõ.
- [ ] Named profiles chỉ override những thông số thực sự cần khác.
- [ ] File HOCON được **driver thực sự nạp**, không chỉ tồn tại trong resources.
- [ ] Tên profile được xác thực trong integration test/startup.
- [ ] Mọi setter trên `BoundStatement` giữ object trả về, đặc biệt `setExecutionProfileName`.
- [ ] `PreparedStatement` được sử dụng lại, bind markers và thứ tự tham số đúng kiểu CQL.
- [ ] Không đánh dấu idempotent cho counter/list append hoặc mutation không an toàn khi retry.
- [ ] Hiểu `LOCAL_ONE`, `LOCAL_QUORUM`, `LOCAL_SERIAL` theo topology/keyspace thực tế.
- [ ] `page-size`, `LIMIT` và paging state được phân biệt rõ trong API.
- [ ] Không dùng profile để chữa hot partition, sai schema hoặc truy vấn lọc không theo khóa.
- [ ] Có metrics theo nhóm, giới hạn concurrency, retry/backoff và benchmark trên dữ liệu đại diện.
- [ ] Có bài kiểm tra `CqlTemplate`/driver và các hành vi LWT, timeout, pagination quan trọng.

## Tài liệu tham khảo

- [Apache Cassandra Java Driver 4 — Configuration and Execution Profiles](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/configuration/).
- [Apache Cassandra Java Driver 4 — Reference Configuration](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/configuration/reference/).
- [Apache Cassandra Java Driver 4 — Query Idempotence](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/idempotence/).
- [Spring Data Cassandra — Prepared Statements](https://docs.spring.io/spring-data/cassandra/reference/cassandra/prepared-statements.html).
- [Spring Data Cassandra — CQL Template API](https://docs.spring.io/spring-data/cassandra/reference/cassandra/cql-template.html).
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html).
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html).
