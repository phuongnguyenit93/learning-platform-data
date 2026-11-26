# Contact points, local datacenter, keyspace và thông tin xác thực

Khi ứng dụng **Spring Data Cassandra** khởi động, một phần lớn lỗi thường xảy ra **trước khi** repository hay `CassandraTemplate` thực hiện truy vấn: driver không tới được node nào, không biết datacenter cục bộ, không tìm thấy keyspace hoặc bị từ chối xác thực. Hiểu đúng bốn thông số này là điều kiện đầu tiên để truy cập Apache Cassandra ổn định trong môi trường phân tán.

Bài học thuộc chương **Cấu hình kết nối** của module **SPRING_DATA_CASSANDRA**. Chúng ta sẽ cấu hình ứng dụng Spring Boot, hiểu đường đi từ contact points đến Cassandra cluster, phân biệt keyspace với bảng và partition key, xử lý tài khoản/secret an toàn, rồi kiểm tra kết nối bằng một entity, repository và CQL. Các ví dụ sử dụng Spring Boot 3.x với Spring Data Cassandra và Java Driver 4.x; nếu dự án dùng dòng phiên bản khác, cần đối chiếu tên thuộc tính và API với phiên bản thực tế.

## 1. Bốn thông số và trách nhiệm của từng thông số

| Thông số | Ví dụ | Trả lời câu hỏi nào? | Hậu quả khi sai |
|---|---|---|---|
| **Contact points** | `cass-1.internal:9042`, `cass-2.internal:9042` | Driver **ban đầu** tìm cluster ở địa chỉ nào? | Không bootstrap được hoặc chỉ tiếp cận địa chỉ không truy cập được |
| **Local datacenter** | `dc1` | Driver nên xem datacenter nào là **cục bộ** để định tuyến? | Driver không khởi tạo đúng hoặc định tuyến không như mong đợi |
| **Keyspace** | `app_data` | Các bảng CQL mặc định thuộc không gian dữ liệu nào? | Lỗi không tìm thấy keyspace/bảng, hoặc truy vấn nhầm dữ liệu |
| **Authentication** | Username + password | Ứng dụng được xác thực với cluster bằng tài khoản nào? | Đăng nhập thất bại hoặc thiếu quyền đọc/ghi |

Một sơ đồ khái niệm:

~~~text
Spring Boot / Spring Data Cassandra
         |
         | application.yml hoặc cấu hình CqlSession
         v
   Cassandra Java Driver (CqlSession)
         |
         +-- Contact points: node ban đầu để khám phá topology
         +-- Local datacenter: ưu tiên node trong DC tương ứng
         +-- Credentials + TLS: xác thực, bảo vệ kênh truyền
         +-- Keyspace: ngữ cảnh bảng mặc định
         |
         v
     Cassandra cluster
         |
         +-- dc1: node-a, node-b, node-c
         +-- dc2: node-d, node-e, node-f
         |
         +-- keyspace app_data
               +-- device_state_by_id
               +-- events_by_device_day
~~~

**Contact point không phải partition key** và **keyspace không phải một node**. Driver tìm node và định tuyến câu lệnh; Cassandra tự xác định replica dựa trên partition key và cấu hình replication của keyspace. Sự phân biệt này giúp tránh một hiểu nhầm phổ biến: “chỉ định đúng địa chỉ node là đã quyết định dữ liệu sẽ nằm ở node đó”.

## 2. Contact points: điểm bắt đầu, không phải danh sách cố định mọi replica

**Contact points** là một hoặc nhiều địa chỉ `host:port` để driver kết nối khi khởi tạo `CqlSession`. Sau khi liên lạc được với cluster, Java Driver lấy metadata để khám phá những node khác và cập nhật topology. Driver không chỉ gửi mọi câu lệnh tới đúng contact point đầu tiên.

Ví dụ cluster có ba node thuộc datacenter `dc1`:

~~~text
dc1
├── cass-1.internal   10.10.1.11:9042
├── cass-2.internal   10.10.1.12:9042
└── cass-3.internal   10.10.1.13:9042
~~~

Ứng dụng có thể bắt đầu từ hai điểm:

~~~yaml
spring:
  cassandra:
    contact-points:
      - cass-1.internal:9042
      - cass-2.internal:9042
~~~

Sử dụng nhiều điểm hợp lệ giúp bootstrap khi một điểm tạm không khả dụng. Trong môi trường production, contact points phải là địa chỉ **ứng dụng thực sự truy cập được**, và các địa chỉ node mà cluster quảng bá sau khi khám phá cũng phải phù hợp với mạng của ứng dụng.

### 2.1. Cổng nào được dùng?

- **9042/TCP** thường là cổng **CQL native transport** của Cassandra và driver Java.
- Các cổng cho kết nối node-to-node hoặc JMX không thay thế cổng CQL.
- Nếu hệ thống đổi native transport port, khai báo đúng cổng được vận hành; không giả định mọi cluster luôn dùng `9042`.
- Kiểm tra DNS, firewall, network policy, security group và đường kết nối giữa container/pod/application host với các node Cassandra.

### 2.2. `localhost` phụ thuộc nơi ứng dụng chạy

Trong ứng dụng chạy trực tiếp trên cùng máy với Cassandra phát triển, `127.0.0.1:9042` có thể phù hợp. Nhưng khi ứng dụng ở **container Docker khác**, `localhost` trỏ về chính container ứng dụng, không phải container Cassandra. Khi đó nên dùng DNS/service name trên mạng chung (ví dụ `cassandra:9042`), tùy hệ thống triển khai.

Trong Kubernetes, Service/DNS và địa chỉ mà Cassandra **advertise** phải được thiết kế để driver khám phá và kết nối tới node thực tế. Việc ping được một Service không bảo đảm mọi địa chỉ node mà driver khám phá đều truy cập được.

### 2.3. Contact points không quyết định phân bố dữ liệu

Câu lệnh:

~~~sql
SELECT * FROM app_data.device_state_by_id
WHERE device_id = 4f91c3ec-c09f-4e99-bf22-b6138bc64510;
~~~

sử dụng `device_id` làm partition key. Cassandra xác định replica theo token, keyspace replication và topology. Tên node được đặt trong danh sách contact points **không ép** dữ liệu của thiết bị này lưu trên node đó.

## 3. Local datacenter: tên DC thực của cluster

**Datacenter (DC)** là đơn vị topology logic của Cassandra. Trong hệ thống nhiều DC, ứng dụng thường ưu tiên các node cùng DC để giảm độ trễ, chi phí đường truyền và tăng khả năng kiểm soát locality. Java Driver 4 sử dụng một **local datacenter** để xác định node cục bộ theo chính sách load balancing.

Ví dụ:

~~~yaml
spring:
  cassandra:
    local-datacenter: dc1
~~~

`dc1` phải khớp **tên DC mà Cassandra công bố**, không phải tên AWS region hoặc tên môi trường tự đặt tùy ý. Có thể kiểm tra thông qua công cụ quản trị như `nodetool status` (hiển thị nhóm `Datacenter: ...`) hoặc metadata của cluster.

~~~text
Datacenter: dc1
===============
Status=Up/Down
|/ State=Normal/Leaving/Joining/Moving
--  Address       Load        Tokens  Owns  Host ID  Rack
UN  10.10.1.11    ...
UN  10.10.1.12    ...
UN  10.10.1.13    ...
~~~

Đoạn trên chỉ minh họa nhãn DC và trạng thái `UN`; các giá trị tải, token, rack và UUID node phụ thuộc cluster thực. Nếu cluster dùng tên `datacenter1` thì phải cấu hình `datacenter1`, không đổi thành `dc1` theo ví dụ.

### 3.1. Nếu ứng dụng và cluster ở hai DC?

Giả sử `dc1` ở Hà Nội và `dc2` ở Singapore. Một instance ứng dụng chạy gần `dc2` thông thường nên định tuyến tới các node của `dc2`, với điều kiện keyspace đã được replication phù hợp ở đó và yêu cầu nghiệp vụ cho phép. Không nên chọn DC chỉ dựa trên node contact point ngẫu nhiên.

Hành vi thực tế còn chịu ảnh hưởng của cấu hình load balancing, topology, availability và consistency level; `local-datacenter` **không tự sao chép dữ liệu** sang DC đó.

### 3.2. Liên hệ với consistency

- `LOCAL_ONE`: thao tác đọc/ghi cần phản hồi từ một replica thuộc DC cục bộ theo ngữ nghĩa consistency tương ứng.
- `LOCAL_QUORUM`: cần đa số replica của DC cục bộ đối với keyspace/replication đang dùng. Nếu replication factor tại `dc1` là 3, quorum cục bộ là 2.
- `local-datacenter` là lựa chọn định tuyến trong driver; **replication factor** là thuộc tính keyspace; **consistency level** là yêu cầu xác nhận của thao tác. Đây là ba khái niệm liên quan nhưng khác nhau.

Chọn consistency dựa trên mức nhất quán, khả năng chịu lỗi và SLA của nghiệp vụ, không chỉ vì ứng dụng đã khai báo `local-datacenter`.

## 4. Keyspace: không gian bảng và chính sách replication

**Keyspace** nhóm các bảng CQL và mang thông tin về cách dữ liệu được replication. Ứng dụng thường cấu hình một keyspace mặc định để tránh viết tên đầy đủ `keyspace.table` trong mọi truy vấn.

Ví dụ keyspace production gồm ba replica trong `dc1`:

~~~sql
-- Chạy bởi người/luồng quản trị có quyền tạo keyspace.
-- Đảm bảo dc1 tồn tại và có đủ node trước khi chọn RF=3.
CREATE KEYSPACE IF NOT EXISTS app_data
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;
~~~

Replication factor 3 ở ví dụ là một **quyết định triển khai**, không phải giá trị bắt buộc cho mọi cluster. Với cluster một node để học, RF 3 không có đủ replica để thỏa các yêu cầu consistency cao; cần cấu hình replication phù hợp số node và mục tiêu thực tế.

Ứng dụng trỏ vào keyspace:

~~~yaml
spring:
  cassandra:
    keyspace-name: app_data
~~~

Sau đó CQL:

~~~sql
SELECT * FROM device_state_by_id WHERE device_id = ?;
~~~

được giải quyết trong ngữ cảnh keyspace mặc định `app_data` khi session đã chọn keyspace đó. Câu lệnh khai báo rõ `app_data.device_state_by_id` vẫn có thể được dùng khi thích hợp và người dùng có quyền.

### 4.1. Phân biệt keyspace, bảng, partition và tenant

| Cấp | Ví dụ | Chứa/điều khiển |
|---|---|---|
| Cluster | `orders-cluster` | Nhiều node và DC |
| Keyspace | `app_data` | Bảng, chính sách replication |
| Table | `device_state_by_id` | Cấu trúc cột, primary key |
| Partition | `device_id = ...` | Một nhóm hàng cùng partition key |
| Row | `device_id = ...` với các cột dữ liệu | Một bản ghi theo toàn bộ primary key |

Không nên mặc định tạo **một keyspace cho mỗi tenant** chỉ vì ứng dụng đa tenant. Số lượng keyspace/table lớn kéo theo chi phí schema và vận hành; nhiều hệ thống dùng `tenant_id` trong primary key và kiểm soát quyền ở tầng ứng dụng. Cần chọn phương án cô lập dữ liệu theo bảo mật, quy mô và yêu cầu vận hành cụ thể.

### 4.2. Keyspace không được tự tạo bởi cấu hình kết nối

Khai báo `keyspace-name: app_data` **không đồng nghĩa keyspace đã tồn tại**. Trước khi ứng dụng khởi động, keyspace và các bảng cần được tạo theo quy trình migration/provisioning của dự án. Trong production, không nên giao quyền sửa schema rộng rãi cho tài khoản chạy API.

Các môi trường thường có quy trình riêng cho CQL migration và kiểm soát thay đổi schema. Dù Spring Data Cassandra có các tùy chọn quản lý schema phục vụ phát triển, cần tránh phụ thuộc vào việc ứng dụng tự tạo/xóa schema khi triển khai production.

## 5. Xác thực: username, password và quyền CQL

Khi cluster bật xác thực (ví dụ Cassandra cấu hình `PasswordAuthenticator`), ứng dụng cần credentials hợp lệ. **Authentication** là kiểm tra danh tính; **authorization** là xác định vai trò đó được đọc, ghi hoặc thay đổi schema ở đâu.

Trong Spring Boot:

~~~yaml
spring:
  cassandra:
    username: ${CASSANDRA_USERNAME}
    password: ${CASSANDRA_PASSWORD}
~~~

`CASSANDRA_USERNAME` và `CASSANDRA_PASSWORD` ở đây là **biến môi trường** do môi trường chạy cung cấp. Giá trị không được chép cứng vào mã nguồn hoặc commit trong file cấu hình chứa mật khẩu thật.

### 5.1. Quyền tối thiểu

Một tài khoản chạy API thường chỉ cần quyền đọc và/hoặc ghi dữ liệu trên những keyspace/table phục vụ nghiệp vụ. Tài khoản này thường không cần `CREATE KEYSPACE`, `ALTER` hay `DROP`. Ví dụ, do quản trị viên thực hiện sau khi tạo role:

~~~sql
-- Vai trò app_rw đã được tạo và xác thực theo chính sách cluster.
GRANT SELECT ON KEYSPACE app_data TO app_rw;
GRANT MODIFY ON KEYSPACE app_data TO app_rw;
~~~

Cú pháp và cơ chế cấp quyền có thể khác nếu dùng Cassandra được quản lý hoặc nhà cung cấp tích hợp IAM. Trong trường hợp đó, ưu tiên cơ chế được nhà cung cấp hỗ trợ và xác minh quyền tối thiểu.

Một tài khoản có thể **đăng nhập thành công** nhưng vẫn gặp lỗi `Unauthorized` khi truy cập bảng; lúc này vấn đề thuộc **authorization**, không phải DNS/contact points.

### 5.2. Bảo vệ đường truyền

Username/password **không tự mã hóa** traffic. Trong môi trường sản xuất, kết nối đến Cassandra cần thiết kế **TLS**, kiểm tra chứng chỉ máy chủ/truststore và xác định chính sách chứng thực phù hợp. Cấu hình chi tiết phụ thuộc Spring Boot, Java Driver và hạ tầng; khi dùng cloud/managed Cassandra, có thể phải dùng secure connect bundle hoặc cách cấu hình riêng của nhà cung cấp.

Không tắt xác minh chứng chỉ để khắc phục lỗi TLS trong production. Hãy kiểm tra CA, tên máy, hạn chứng chỉ, hostname verification và đường dẫn tới truststore/certificate.

### 5.3. Secret và vòng đời credential

- Lưu bí mật trong secret manager, Kubernetes Secret hoặc cơ chế quản lý cấu hình bảo mật đã được phê duyệt; không ghi mật khẩu vào log hay URL.
- Chỉ sử dụng credential có quyền tối thiểu cho môi trường cụ thể (dev/staging/prod).
- Khi xoay vòng mật khẩu, cần biết thời điểm ứng dụng phải tạo lại session hoặc restart để nhận credential mới. Thay biến môi trường của process đang chạy không tự cập nhật session đã tạo.
- Kiểm tra cẩn thận cách hệ thống giám sát che giá trị bí mật trong cấu hình, error report và diagnostic dump.

## 6. Cấu hình Spring Boot hoàn chỉnh

Với ứng dụng Spring Boot 3.x sử dụng starter cho Cassandra và Spring Data Cassandra, ví dụ sau đủ thể hiện bốn giá trị cốt lõi:

~~~yaml
# application.yml — ví dụ cho môi trường có dc1 và keyspace đã tạo.
spring:
  cassandra:
    contact-points:
      - cass-1.internal:9042
      - cass-2.internal:9042
    local-datacenter: dc1
    keyspace-name: app_data
    username: ${CASSANDRA_USERNAME}
    password: ${CASSANDRA_PASSWORD}
    schema-action: none
~~~

Spring Boot thực hiện cấu hình Java Driver/Cassandra session và Spring Data Cassandra theo các auto-configuration phù hợp với dependency trên classpath. Nếu đã dùng cách này, thông thường **không cần tự tạo thêm `CqlSession`**.

**Ranh giới phiên bản:** ở một số dự án Spring Boot 2.x, các thuộc tính có tiền tố `spring.data.cassandra.*`; Spring Boot 3.x dùng `spring.cassandra.*`. Không trộn hai dạng theo trí nhớ: phải đối chiếu phiên bản Spring Boot và configuration metadata trong dự án. Các thuộc tính driver nâng cao cũng có thể được khai báo qua cơ chế cấu hình riêng của Java Driver.

### 6.1. Tách môi trường chạy

Một ứng dụng thường cần contact points và keyspace khác nhau giữa các môi trường:

~~~yaml
# application-local.yml — chỉ là ví dụ cho máy phát triển.
spring:
  cassandra:
    contact-points:
      - 127.0.0.1:9042
    local-datacenter: datacenter1
    keyspace-name: app_data_local
~~~

Các giá trị local chỉ đúng khi cluster thực tế có DC `datacenter1` và keyspace `app_data_local`. Kích hoạt Spring profile `local` theo cách dự án quy định, không copy cấu hình local sang production.

Đối với ứng dụng chạy trong Docker/Kubernetes, thay `127.0.0.1` bằng tên dịch vụ hoặc địa chỉ node nội bộ đúng với mạng runtime. Cấu hình thực tế còn cần bảo mật TLS, quản lý secret, timeout, resource limits và quan sát vận hành.

### 6.2. Về kết nối của Spring Data Cassandra

Spring Data Cassandra cung cấp các abstraction thường gặp:

- `CassandraRepository`: thao tác CRUD và truy vấn khai báo từ interface.
- `CassandraTemplate`/`CassandraOperations`: truy cập dữ liệu bằng template, hỗ trợ query/mapping linh hoạt.
- `ReactiveCassandraTemplate` và reactive repositories: pipeline `Mono/Flux` cho ứng dụng phản ứng.

Các abstraction này đều phụ thuộc vào **cấu hình kết nối hợp lệ**. Việc chuyển từ repository sang template hoặc reactive không giải quyết lỗi keyspace chưa tồn tại, sai local DC hay thiếu quyền.

## 7. Cấu hình CqlSession trực tiếp khi không dùng auto-configuration

Khi cần cấu hình programmatic hoặc dùng Spring Data Cassandra mà không dựa vào auto-configuration của Spring Boot, có thể tạo `CqlSession`:

~~~java
import java.net.InetSocketAddress;
import com.datastax.oss.driver.api.core.CqlSession;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CassandraSessionConfig {

    @Bean(destroyMethod = "close")
    CqlSession cqlSession(
            @Value("${app.cassandra.host}") String host,
            @Value("${app.cassandra.port:9042}") int port,
            @Value("${app.cassandra.local-datacenter}") String dc,
            @Value("${app.cassandra.keyspace}") String keyspace,
            @Value("${app.cassandra.username}") String username,
            @Value("${app.cassandra.password}") String password) {

        return CqlSession.builder()
                .addContactPoint(new InetSocketAddress(host, port))
                .withLocalDatacenter(dc)
                .withKeyspace(keyspace)
                .withAuthCredentials(username, password)
                .build();
    }
}
~~~

Để ví dụ hoạt động, các giá trị `app.cassandra.*` phải được cung cấp từ cấu hình ứng dụng. Đây là **phương án thay thế** cho session do Spring Boot tự cấu hình, không nên khai báo trùng một cách vô ý. Ví dụ chỉ minh họa bốn thành phần cơ bản; cần bổ sung TLS và cấu hình driver theo môi trường production.

### 7.1. Vì sao nên dùng một CqlSession được quản lý vòng đời?

`CqlSession` là một thành phần tương đối tốn tài nguyên: nó duy trì thông tin topology và kết nối tới cluster. Không nên tạo/đóng session ở **mỗi HTTP request** hoặc mỗi phương thức repository. Thường dùng một bean được chia sẻ có vòng đời gắn với ứng dụng; lúc shutdown, Spring gọi `close()` để thu hồi tài nguyên.

Driver đảm nhiệm connection pooling và xử lý topology; không cần tự tạo nhiều `CqlSession` để “song song hóa” mỗi lệnh CQL.

## 8. Kiểm tra kết nối bằng CQL và một truy vấn Spring Data

Trước tiên, người quản trị tạo bảng theo yêu cầu nghiệp vụ:

~~~sql
CREATE TABLE IF NOT EXISTS app_data.device_state_by_id (
    device_id uuid PRIMARY KEY,
    status text,
    updated_at timestamp
);
~~~

Ở Spring Data Cassandra, entity có thể được định nghĩa:

~~~java
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("device_state_by_id")
public class DeviceState {
    @PrimaryKey("device_id")
    private UUID deviceId;

    @Column("status")
    private String status;

    @Column("updated_at")
    private Instant updatedAt;

    public DeviceState() {}

    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID deviceId) { this.deviceId = deviceId; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant updatedAt) { this.updatedAt = updatedAt; }
}
~~~

Một repository:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface DeviceStateRepository
        extends CassandraRepository<DeviceState, UUID> {
}
~~~

Với `DeviceStateRepository` đã được Spring tạo bean, truy vấn:

~~~java
Optional<DeviceState> state = repository.findById(deviceId);
~~~

sẽ truy cập bảng `device_state_by_id` thuộc keyspace mặc định của session, sử dụng `device_id` làm partition key. `deviceId` là một `UUID` do API hoặc nghiệp vụ cung cấp; `findById` trả `Optional.empty()` nếu không có hàng.

Truy vấn tương tự qua `CassandraTemplate`:

~~~java
// Trong service đã inject CassandraTemplate template:
DeviceState state = template.selectOneById(deviceId, DeviceState.class);
// Không tìm thấy hàng: có thể trả null.
~~~

Những truy vấn này chỉ thành công khi **session kết nối được cluster, tài khoản có quyền, keyspace tồn tại và bảng đúng schema**. Nếu bảng thiếu, đây là lỗi schema/data setup, không phải bằng chứng cần đổi `CassandraRepository` sang `ReactiveCassandraRepository`.

### 8.1. Kiểm tra riêng kết nối và schema

Khi được cấp quyền, công cụ CQL có thể kiểm tra metadata:

~~~sql
-- Thông tin node đang nhận câu lệnh (trong system keyspace).
SELECT cluster_name, data_center FROM system.local;

-- Kiểm tra keyspace có tồn tại.
SELECT keyspace_name
FROM system_schema.keyspaces
WHERE keyspace_name = 'app_data';

-- Kiểm tra bảng có tồn tại trong keyspace.
SELECT table_name
FROM system_schema.tables
WHERE keyspace_name = 'app_data'
  AND table_name = 'device_state_by_id';
~~~

Chạy `cqlsh` thành công từ máy quản trị **chưa chứng minh** ứng dụng chạy ở Docker/Kubernetes có DNS, mạng, TLS và credential tương đương. Thực hiện bước kiểm tra từ **môi trường mạng của ứng dụng** hoặc qua health check được triển khai có kiểm soát.

## 9. Lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Khả năng cần kiểm tra | Hành động phù hợp |
|---|---|---|
| Driver không thể kết nối contact points | Host sai, DNS lỗi, firewall, port CQL không mở | Kiểm tra DNS/TCP từ nơi ứng dụng chạy và địa chỉ/port thực |
| Kết nối contact point được nhưng các node khác không dùng được | Node advertise địa chỉ không truy cập từ mạng ứng dụng | Kiểm tra topology và địa chỉ node được quảng bá |
| Lỗi local datacenter hoặc không có node phù hợp | Sai tên DC, cấu hình load balancing không khớp topology | Đối chiếu `nodetool status`/cluster metadata, cấu hình đúng tên DC |
| `AuthenticationException` hoặc đăng nhập bị từ chối | Sai username/password; cluster dùng cơ chế auth khác | Kiểm tra secret, cơ chế auth, vòng đời credential |
| `Unauthorized` với SELECT/INSERT | Role không được cấp quyền dữ liệu | Kiểm tra grants theo keyspace/table, không mở rộng quyền tùy tiện |
| Không tìm thấy keyspace | Keyspace chưa tạo hoặc sai tên | Kiểm tra `system_schema.keyspaces` và migration |
| `unconfigured table` / table không tồn tại | Sai keyspace mặc định, sai tên bảng, migration chưa chạy | Đối chiếu `@Table`, schema và keyspace session |
| TLS handshake/SSL errors | CA/truststore/hostname/certificate không khớp | Sửa certificate chain và trust config phù hợp |
| Khởi động được nhưng truy vấn chậm/timeout | Hot partition, consistency, tải cluster, network, driver settings | Đo p95/p99, tombstones, timeout và thiết kế bảng theo truy vấn |

Lỗi **timeout** không tự chứng minh host/credential sai; timeout có thể xảy ra sau khi kết nối đã hình thành nhưng cluster không kịp đáp ứng một statement. Ngược lại, ứng dụng có thể kết nối thành công nhưng không có quyền với một keyspace cụ thể.

### 9.1. Trình tự chẩn đoán có thể lặp lại

1. **Kiểm tra môi trường:** ứng dụng đang chạy ở host, container, pod hoặc cloud network nào; DNS nào được sử dụng?
2. **Kiểm tra transport:** contact points và port có truy cập được không; các node được driver khám phá có địa chỉ hợp lệ không?
3. **Kiểm tra topology:** tên local DC có đúng như cluster báo cáo không?
4. **Kiểm tra bảo mật:** TLS handshake, chứng chỉ, username/password và quyền CQL đã chính xác chưa?
5. **Kiểm tra schema:** keyspace và bảng có tồn tại, đúng phiên bản migration chưa?
6. **Kiểm tra truy vấn:** partition key, consistency, paging, hot partition, số lượng request đồng thời và driver timeout.

Phân loại lỗi theo từng bước tránh tình trạng thay đồng loạt timeout, contact points, password và consistency rồi không biết thay đổi nào thực sự xử lý được vấn đề.

## 10. Cấu hình kết nối liên quan thế nào đến hiệu năng phân tán?

Kết nối thành công mới là điều kiện cần. Để hệ thống đáp ứng SLA, cần nhìn đồng thời **topology, schema và tải**.

### 10.1. Không lẫn cấu hình kết nối với thiết kế partition key

Giả sử schema:

~~~sql
CREATE TABLE app_data.events_by_device_day (
    device_id uuid,
    day_bucket date,
    event_id timeuuid,
    event_type text,
    PRIMARY KEY ((device_id, day_bucket), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);
~~~

Truy vấn hiệu quả cho đường truy cập đó:

~~~sql
SELECT event_id, event_type
FROM app_data.events_by_device_day
WHERE device_id = ?
  AND day_bucket = ?
LIMIT 50;
~~~

Ngay cả khi contact points, local DC và keyspace hoàn toàn đúng, một thiết bị có hàng triệu sự kiện/ngày vẫn có thể tạo partition rất lớn hoặc nóng. Thay đổi contact points **không thay đổi partition key**. Cần xem xét bucket thời gian, giới hạn đọc, paging và đặc điểm phân phối ghi.

### 10.2. Driver và CassandraTemplate

Khi truy vấn lớn, Cassandra thường trả dữ liệu theo trang. Driver có khả năng paging; Spring Data Cassandra cung cấp các API truy vấn/paging phù hợp. Không trả `findAll()` vô hạn để “thử xem kết nối có nhanh không”.

Các thông số cần đo/tinh chỉnh theo tải:

- **Request timeout:** đặt theo SLA nhưng tránh dùng timeout rất lớn che giấu vấn đề query/cluster.
- **Connection pool và concurrency:** dùng cấu hình driver tương thích, giới hạn số thao tác đang bay; không tạo session mới cho mỗi request.
- **Page size/fetch size:** kiểm soát memory và số lần lấy dữ liệu qua mạng.
- **Consistency level:** chọn theo replication, khả năng chịu lỗi và yêu cầu tính nhất quán của thao tác.
- **Retry:** chỉ áp dụng an toàn theo idempotency và chính sách driver; tránh bão retry khi node chậm.
- **Observability:** theo dõi khởi tạo session, số node khả dụng, p50/p95/p99 latency, timeout, số request đang xử lý, phân phối partition và lỗi authorization.

Không có một giá trị timeout hay pool size lý tưởng cho mọi cluster. Cần benchmark dưới tải, độ trễ mạng và phân phối dữ liệu giống production.

## 11. Bài tập cấu hình theo môi trường

Giả sử hệ thống quản lý thiết bị có:

~~~text
Ứng dụng chạy tại: Kubernetes trong DC dc2
Cassandra:
  dc1: cass-a1, cass-a2, cass-a3
  dc2: cass-b1, cass-b2, cass-b3
Native transport: 9042
Keyspace: telemetry_data
Tài khoản ứng dụng: telemetry_api (được cấp quyền SELECT/MODIFY)
Authentication: bật
Replication của telemetry_data: dc1=3, dc2=3
~~~

Hãy xác định cấu hình cốt lõi nếu ứng dụng có thể kết nối tới các node ở `dc2`, còn password được inject bằng secret.

Một đáp án tham khảo:

~~~yaml
spring:
  cassandra:
    contact-points:
      - cass-b1.internal:9042
      - cass-b2.internal:9042
    local-datacenter: dc2
    keyspace-name: telemetry_data
    username: telemetry_api
    password: ${CASSANDRA_PASSWORD}
~~~

Các hostname chỉ là ví dụ. Cấu hình bảo mật thực tế phải bổ sung TLS/trust và mọi yêu cầu của hạ tầng. Việc `telemetry_data` có RF=3 ở cả hai DC là dữ liệu đã được quản trị trên cluster; ứng dụng chỉ khai báo tên keyspace, không tạo replication bằng YAML trên.

**Câu hỏi tự kiểm tra:**

1. Vì sao hai contact points đều hoạt động không đảm bảo driver sẽ truy cập được mọi node đã khám phá?
2. Nếu `nodetool status` hiển thị `datacenter1`, cấu hình `local-datacenter: dc1` có đúng không?
3. Vì sao `keyspace-name` không tạo keyspace và không quyết định partition key?
4. Ứng dụng đăng nhập được nhưng `SELECT` báo `Unauthorized`: nên sửa contact point hay kiểm tra quyền?
5. Vì sao `localhost:9042` đôi khi hoạt động trên máy phát triển nhưng thất bại khi chạy cùng ứng dụng trong container?
6. Một cluster có RF=3 trong `dc2`; `LOCAL_QUORUM` cần bao nhiêu replica của DC cục bộ phản hồi?

**Gợi ý đáp án:** (1) metadata có thể quảng bá địa chỉ node không thể truy cập từ mạng ứng dụng; (2) không, phải dùng tên thực `datacenter1`; (3) keyspace là ngữ cảnh và replication, còn schema/primary key được định nghĩa riêng; (4) kiểm tra authorization; (5) `localhost` trỏ tới chính container; (6) hai replica.

## 12. Checklist trước khi triển khai

- [ ] Có ít nhất một contact point hợp lệ; nên có dự phòng và xác minh node được discover cũng truy cập được.
- [ ] Đã xác nhận chính xác tên local DC từ Cassandra.
- [ ] Keyspace tồn tại, có replication phù hợp với topology và SLA.
- [ ] Schema/bảng được provision và migration rõ ràng trước khi app phụ thuộc vào chúng.
- [ ] Credentials lấy từ secret, không chép cứng trong repository hoặc log.
- [ ] Role ứng dụng có quyền tối thiểu, tách biệt với tài khoản quản trị schema.
- [ ] TLS được cấu hình và kiểm tra chứng chỉ theo yêu cầu môi trường.
- [ ] Có một `CqlSession` được quản lý vòng đời, không tạo session cho từng request.
- [ ] Kiểm tra kết nối **từ đúng mạng runtime** của ứng dụng.
- [ ] Đã thực hiện truy vấn nhỏ theo partition key và kiểm tra keyspace/bảng đúng.
- [ ] Theo dõi timeout, latency, số node khả dụng, paging và sự cố phân vùng nóng.

## Tài liệu tham khảo

- [Spring Boot Reference — Working with NoSQL Technologies, Cassandra](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.cassandra).
- [Spring Data Cassandra — Configuration](https://docs.spring.io/spring-data/cassandra/reference/cassandra/configuration.html).
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html).
- [Apache Cassandra — CQL Data Definition](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/ddl.html).
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html).
