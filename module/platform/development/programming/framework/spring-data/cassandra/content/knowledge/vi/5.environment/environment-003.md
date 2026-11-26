# Khởi tạo Cassandra bằng Docker cho môi trường học tập

## 1. Mục tiêu và phạm vi

**Apache Cassandra** là cơ sở dữ liệu NoSQL phân tán, lưu dữ liệu theo partition và nhân bản giữa nhiều node. Để thực hành **Spring Data Cassandra**, chúng ta cần một Cassandra instance có thể kết nối từ ứng dụng Java để thử entity mapping, repository, `CassandraTemplate`, CQL, paging và consistency level (CL).

Sử dụng **Docker** giúp tạo môi trường thực hành có thể tái lập mà không phải tự cài Java, Cassandra Server và công cụ `cqlsh` lên hệ điều hành. Bài này thiết lập **một node Cassandra** phục vụ học tập và kiểm tra kết nối từ ứng dụng Spring Boot.

Sau khi hoàn thành, bạn có thể:

1. Tạo một container Cassandra bằng Docker Compose, dùng volume để giữ dữ liệu qua lần khởi động lại.
2. Kiểm tra Cassandra đã sẵn sàng, xác định data center, cluster và trạng thái node.
3. Tạo keyspace, bảng dữ liệu theo partition key, ghi và đọc dữ liệu bằng CQL.
4. Cấu hình Spring Data Cassandra kết nối đúng host, port, keyspace và local data center.
5. Nhận biết các lỗi thường gặp như Cassandra chưa sẵn sàng, thiếu bộ nhớ, trùng cổng hay đặt sai DC.
6. Phân biệt điều có thể thực hành trên cluster một node với hành vi nhân bản, quorum và chịu lỗi cần nhiều node.

> **Giới hạn của môi trường này:** Một container Cassandra thích hợp để học CQL và Spring Data, nhưng **không mô phỏng được** mất một replica trong cluster có RF = 3, quorum nhiều replica, mạng giữa các data center hoặc hiệu năng production. Không dùng cấu hình mẫu này làm cấu hình triển khai production.

## 2. Luồng kết nối và những thành phần cần biết

Khi chạy Docker trên máy cá nhân, ta có ba lớp chính:

```mermaid
flowchart LR
    A["Ứng dụng Spring Boot<br/>Spring Data Cassandra"] -->| "127.0.0.1:9042" | B["Cổng CQL trên máy host"]
    B --> C["Container Cassandra<br/>node đơn lẻ, DC dc1"]
    C --> D[("Docker named volume<br/>cassandra-data")]
    E["Docker CLI / Compose"] -->| "Quản lý vòng đời" | C
    F["cqlsh bên trong container"] --> C
```

- **Container Cassandra** chạy database server và lắng nghe CQL native transport ở cổng `9042`.
- **Port mapping** `127.0.0.1:9042:9042` cho ứng dụng đang chạy **trực tiếp trên máy host** kết nối tới container. Địa chỉ `127.0.0.1` giới hạn cổng được công bố ở loopback host.
- **Named volume** giữ dữ liệu ở `/var/lib/cassandra` của container ngay cả khi container được xóa và tạo lại bằng Compose.
- **`cqlsh`** là shell thực thi CQL; có sẵn trong image Cassandra, nên ta không phải cài thêm công cụ vào host.
- **Data center (DC)** ở đây tên `dc1`; tên này phải khớp với cấu hình `local-datacenter` trong Java Driver/Spring Data Cassandra.
- **Keyspace** nhóm các bảng và khai báo chiến lược replication. Có thể hiểu tương tự một cấp tổ chức dữ liệu, nhưng không được coi là schema quan hệ có thể join tùy ý.

## 3. Chuẩn bị Docker

Bạn cần có **Docker Engine** đang chạy và **Docker Compose v2** (Docker Desktop cho Windows/macOS thường bao gồm Compose v2). Trên Windows, có thể dùng PowerShell; lệnh Docker bên dưới cũng dùng được với terminal macOS/Linux.

Kiểm tra công cụ:

```powershell
docker version
docker compose version
```

`docker version` cần hiển thị cả phần **Client** và **Server**. Nếu chỉ thấy Client hoặc báo không kết nối được daemon, hãy khởi động Docker Desktop/Engine trước. `docker compose version` giúp chắc chắn đang dùng cú pháp `docker compose` (có khoảng trắng).

Cassandra sử dụng JVM và cần thời gian khởi động; nên cấp đủ tài nguyên cho Docker Desktop, ví dụ **ít nhất khoảng 4 GiB RAM dành cho Docker** để có dư địa cho database và hệ điều hành/container khác. Khi máy thiếu tài nguyên, có thể cần giảm workload thử nghiệm hoặc điều chỉnh heap một cách có kiểm soát. Cũng cần vài GiB dung lượng đĩa trống và truy cập mạng để tải image lần đầu.

Tạo một thư mục ví dụ `cassandra-lab` ở bất kỳ vị trí phù hợp trên máy và đặt tệp `compose.yaml` bên trong. Thư mục này là **tệp cấu hình mẫu do người học tự tạo**; bài giảng không yêu cầu sửa bất kỳ tệp dự án Java nào.

## 4. Tạo container Cassandra với Docker Compose

Nội dung `compose.yaml`:

```yaml
name: cassandra-learning

services:
  cassandra:
    image: cassandra:4.1
    ports:
      - "127.0.0.1:9042:9042"
    environment:
      CASSANDRA_CLUSTER_NAME: learning-cluster
      CASSANDRA_DC: dc1
      CASSANDRA_RACK: rack1
      CASSANDRA_ENDPOINT_SNITCH: GossipingPropertyFileSnitch
      MAX_HEAP_SIZE: 1024M
      HEAP_NEWSIZE: 256M
    volumes:
      - cassandra-data:/var/lib/cassandra

volumes:
  cassandra-data:
```

Giải thích các lựa chọn:

| Thành phần | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `image: cassandra:4.1` | Dùng nhánh Cassandra 4.1 cho ví dụ có thể tái lập ở mức phiên bản chính/phụ. | Tag này có thể được cập nhật bản vá; nếu nhóm cần kết quả byte-for-byte ổn định, pin bản phát hành cụ thể hoặc image digest. |
| `ports` | Ánh xạ CQL 9042 từ container ra loopback của máy host. | Nếu cổng 9042 đã bị sử dụng, cần đổi cổng **bên host** và cập nhật cấu hình ứng dụng. |
| `CASSANDRA_CLUSTER_NAME` | Đặt tên hiển thị cho cluster học tập. | Không liên quan đến địa chỉ TCP mà client sử dụng. |
| `CASSANDRA_DC`, `CASSANDRA_RACK` | Định danh data center/rack của node. | Phải thống nhất với keyspace replication và local DC của driver. |
| `CASSANDRA_ENDPOINT_SNITCH` | Dùng snitch nhận biết DC/rack, phù hợp để thực hành khái niệm topology. | Cluster nhiều DC/rack thực tế cần thiết kế topology riêng. |
| `MAX_HEAP_SIZE`, `HEAP_NEWSIZE` | Giới hạn/điều chỉnh heap JVM cho môi trường học tập. | Thông số phù hợp còn tùy phiên bản Cassandra và tài nguyên máy; không sao chép giá trị này vào production. |
| `cassandra-data` | Volume lưu dữ liệu và metadata của Cassandra. | `docker compose down` vẫn giữ volume; `down -v` xóa volume do Compose quản lý. |

> **Vì sao dùng `cassandra:4.1`?** Bài học chọn một nhánh phiên bản rõ ràng để người mới theo dõi dễ hơn. Khi dùng image hoặc Java Driver/Spring Boot ở phiên bản khác, hãy kiểm tra tương thích và tài liệu chính thức của các thành phần tương ứng. Không suy ra “bản mới nhất” từ ví dụ này.

Trong terminal đang ở thư mục chứa `compose.yaml`, kiểm tra cấu hình:

```powershell
docker compose config
```

Lệnh hiển thị cấu hình Compose đã được xử lý và báo lỗi nếu YAML sai cú pháp. Sau đó tạo và chạy container:

```powershell
docker compose up -d
```

Để kiểm tra quá trình khởi động:

```powershell
docker compose ps
docker compose logs --tail=100 cassandra
```

Lần đầu Docker phải tải image và Cassandra khởi tạo dữ liệu hệ thống nên có thể mất một khoảng thời gian. **Trạng thái container “Up” không có nghĩa CQL đã sẵn sàng**. Không cần đoán số giây cố định: hãy dùng truy vấn kiểm tra ở phần tiếp theo.

### Có thể dùng `docker run` không?

Có, nhưng Compose thuận tiện hơn khi cần lưu cấu hình, chạy lại hoặc thêm dịch vụ ứng dụng sau này. Nếu chỉ muốn tạo một instance tạm thời, cùng ý tưởng có thể biểu diễn bằng `docker run` với tùy chọn `-p`, `-e` và `-v`; tránh chạy **cả hai** instance cùng sử dụng cổng host 9042. Các phần sau của bài dùng Compose làm quy trình chính.

## 5. Xác nhận Cassandra đã sẵn sàng

Kiểm tra node bằng `nodetool`:

```powershell
docker compose exec cassandra nodetool status
```

Với một node hoạt động bình thường, bảng trạng thái thường hiển thị node có mã `UN`, tương ứng **Up/Normal**. Nếu lệnh chưa chạy được vì Cassandra đang khởi động, xem lại log và thử lại sau khi các dịch vụ đã sẵn sàng.

Kiểm tra CQL và metadata của node:

```powershell
docker compose exec cassandra cqlsh -e "SELECT cluster_name, data_center, release_version FROM system.local;"
```

Kết quả mong đợi có `learning-cluster`, `dc1` và phiên bản Cassandra thuộc nhánh image đã chọn. Chính giá trị `data_center` trả về ở đây là căn cứ để cấu hình `local-datacenter` cho ứng dụng Spring; không cần đoán tên DC từ địa chỉ IP.

Mở shell CQL tương tác:

```powershell
docker compose exec cassandra cqlsh
```

Trong `cqlsh`, thử:

```sql
DESCRIBE KEYSPACES;
SELECT data_center, rack FROM system.local;
```

Lệnh `exit` thoát `cqlsh`. Khi sử dụng `docker compose exec ... cqlsh`, kết nối diễn ra **bên trong container**; vì vậy nó có thể hoạt động ngay cả khi ứng dụng host chưa kết nối được qua port mapping. Hai đường kết nối cần kiểm tra độc lập khi có sự cố.

## 6. Tạo keyspace và bảng dữ liệu thử nghiệm

Để học thiết kế bảng theo truy vấn, giả sử chức năng cần lấy **các đơn hàng mới nhất của một khách hàng trong một tháng**. Ta dùng khóa partition gồm `customer_id` và `bucket_yyyymm`, sau đó sắp xếp kết quả theo thời điểm tạo đơn.

Trong phiên `cqlsh`, chạy:

```sql
CREATE KEYSPACE IF NOT EXISTS learning
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 1
};

USE learning;

CREATE TABLE IF NOT EXISTS orders_by_customer_month (
    customer_id uuid,
    bucket_yyyymm int,
    created_at timestamp,
    order_id uuid,
    status text,
    total decimal,
    PRIMARY KEY ((customer_id, bucket_yyyymm), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

**Tại sao replication factor là 1?** Cluster thực hành chỉ có một node ở DC `dc1`, do đó `'dc1': 1` là cấu hình tương ứng. `NetworkTopologyStrategy` được dùng để làm quen khái niệm replication theo DC. Nó **không mang lại chịu lỗi** khi chỉ có một bản sao. Ở cluster production, RF và cách trải replica giữa node/rack/DC do nhóm vận hành thiết kế theo yêu cầu thực tế.

Ghi dữ liệu mẫu:

```sql
INSERT INTO orders_by_customer_month (
    customer_id, bucket_yyyymm, created_at, order_id, status, total
) VALUES (
    11111111-1111-1111-1111-111111111111,
    202611,
    '2026-11-25T02:00:00Z',
    22222222-2222-2222-2222-222222222222,
    'PAID',
    125000.00
);

INSERT INTO orders_by_customer_month (
    customer_id, bucket_yyyymm, created_at, order_id, status, total
) VALUES (
    11111111-1111-1111-1111-111111111111,
    202611,
    '2026-11-24T02:00:00Z',
    33333333-3333-3333-3333-333333333333,
    'PENDING',
    99000.00
);
```

Đọc lại theo khóa partition:

```sql
SELECT customer_id, bucket_yyyymm, created_at, order_id, status, total
FROM orders_by_customer_month
WHERE customer_id = 11111111-1111-1111-1111-111111111111
  AND bucket_yyyymm = 202611
LIMIT 10;
```

Kết quả thường hiển thị dòng `2026-11-25` trước `2026-11-24` vì `created_at DESC`. Dữ liệu có cùng khóa partition được bố trí để phục vụ query theo khách hàng và bucket; `order_id` là khóa clustering bổ sung giúp xác định hàng duy nhất khi có các đơn cùng timestamp.

Một số khái niệm rút ra từ ví dụ:

- **Partition key**: cặp `(customer_id, bucket_yyyymm)` quyết định partition mà coordinator cần tìm replica để đọc/ghi.
- **Clustering columns**: `created_at` và `order_id` định nghĩa thứ tự của hàng *trong* một partition. Chúng không tạo thứ tự toàn cục giữa các partition.
- **Thiết kế theo truy vấn**: để đọc theo trạng thái của tất cả khách hàng, không nên tự động dùng `ALLOW FILTERING` trên bảng này; cần xem lại query pattern và bảng/chỉ mục phù hợp.
- **Bucketing**: chia dữ liệu theo tháng giảm nguy cơ một khách hàng có lịch sử vô hạn trong cùng partition, nhưng một tháng cực nhiều đơn vẫn có thể là partition lớn; phải đánh giá theo workload.
- **Paging**: `LIMIT 10` giới hạn tối đa số hàng của query. Khi dữ liệu lớn, Java Driver dùng page size/paging state để lấy các trang; không áp dụng `OFFSET` kiểu SQL quan hệ để bỏ qua hàng tùy ý.

### Consistency level trên môi trường một node

Trong `cqlsh`, có thể xem và chọn mức nhất quán cho phiên tương tác:

```sql
CONSISTENCY;
CONSISTENCY LOCAL_ONE;
```

Với RF = 1 tại DC `dc1`, `LOCAL_ONE` yêu cầu phản hồi từ một replica ở DC địa phương. Quorum của một replica cũng chỉ là một replica; vì thế, **thử `QUORUM` trên một node không giúp bạn kiểm nghiệm cách Cassandra chịu lỗi khi một replica ngừng hoạt động**. Muốn thực hành những tình huống đó cần dựng cụm nhiều node, RF phù hợp và quan sát số replica có mặt.

Đừng dùng `ALL`/`QUORUM` trên ví dụ này để suy ra các bảo đảm giao nhau giữa nhiều bản sao. Trong ứng dụng thực, read CL, write CL, RF và các cạnh tranh ghi/timestamp phải được xem xét cùng nhau.

## 7. Kết nối Spring Data Cassandra từ máy host

Trong ứng dụng **Spring Boot 3.x** có dependency `spring-boot-starter-data-cassandra`, có thể khai báo cấu hình tương đương sau trong `application.yml` của **ứng dụng**:

```yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: dc1
    keyspace-name: learning
    schema-action: NONE
```

Nếu dự án dùng dòng Spring Boot khác, hãy đối chiếu prefix và thuộc tính của phiên bản đó; ví dụ một số phiên bản Spring Boot 2.x dùng nhóm thuộc tính `spring.data.cassandra.*`. Không trộn hai namespace theo suy đoán.

| Thuộc tính | Đặt giá trị | Vì sao cần |
| --- | --- | --- |
| `contact-points` | `127.0.0.1` khi ứng dụng chạy trên host | Trỏ tới cổng host Docker publish; không phải tên container. |
| `port` | `9042` | Phải khớp cổng phía host trong `ports`. |
| `local-datacenter` | `dc1` | Java Driver cần biết DC địa phương để định tuyến và áp dụng CL có prefix `LOCAL_`. |
| `keyspace-name` | `learning` | Keyspace đã tạo qua `cqlsh` trước khi ứng dụng truy cập. |
| `schema-action` | `NONE` | Không để ứng dụng tự tạo/xóa bảng ở bước học kết nối; tự chuẩn bị schema bằng CQL. |

Với Gradle (dự án Spring Boot đã được cấu hình plugin và dependency management phù hợp), dependency tương ứng là:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-cassandra'
}
```

Để kiểm tra kết nối mà chưa cần tạo entity, có thể dùng `CqlSession` do Spring Boot cấu hình. Ví dụ:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.Row;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CassandraConnectionCheck {

    @Bean
    CommandLineRunner verifyCassandra(CqlSession session) {
        return args -> {
            Row row = session.execute(
                "SELECT data_center, release_version FROM system.local"
            ).one();

            if (row == null) {
                throw new IllegalStateException("Khong doc duoc system.local");
            }

            System.out.printf("Cassandra DC=%s, version=%s%n",
                row.getString("data_center"),
                row.getString("release_version"));
        };
    }
}
```

Khi ứng dụng khởi chạy thành công, log in ra `DC=dc1` và phiên bản Cassandra cho biết kết nối CQL đã được thiết lập. Đây là một **smoke test**, chưa thay thế kiểm thử mapping/repository hoặc kiểm tra hiệu năng.

Tiếp theo, khi viết entity cho `orders_by_customer_month`, cần ánh xạ đầy đủ **composite partition key** `(customer_id, bucket_yyyymm)` và **clustering columns** `(created_at, order_id)`. Có thể dùng `@PrimaryKeyClass`, `@PrimaryKeyColumn`, `@PrimaryKey`, cùng `CassandraRepository` hoặc `CassandraTemplate`. Tên cột và kiểu Java (ví dụ UUID, Instant, BigDecimal) phải tương thích kiểu CQL. Spring Data đơn giản hóa code truy cập nhưng không tự chọn partition key đúng giúp bạn.

### Nếu cả Spring Boot cũng chạy trong Docker

Ứng dụng ở **cùng Docker Compose network** với service Cassandra phải sử dụng địa chỉ dịch vụ Docker, ví dụ:

```yaml
spring:
  cassandra:
    contact-points: cassandra
    port: 9042
    local-datacenter: dc1
    keyspace-name: learning
    schema-action: NONE
```

Trong container ứng dụng, `localhost` là **chính container ứng dụng**, không phải container Cassandra. Vì vậy cấu hình `127.0.0.1:9042` phía trên chỉ dành cho ứng dụng chạy trên host. Nếu ứng dụng thuộc một Compose project hoặc mạng Docker khác, cần kết nối chúng vào cùng network thích hợp; chỉ đặt hostname `cassandra` chưa đủ nếu Docker DNS không nhìn thấy service đó.

Đừng nhầm **container đang chạy** với **database đã sẵn sàng**: ngay cả khi Compose khởi động hai service theo thứ tự, ứng dụng vẫn cần cơ chế chờ kết nối, readiness check hoặc retry có giới hạn tại startup khi Cassandra còn khởi động.

## 8. Quản lý vòng đời, volume và làm sạch môi trường

Các lệnh sau chạy từ thư mục chứa `compose.yaml`:

| Lệnh | Tác dụng | Trạng thái dữ liệu |
| --- | --- | --- |
| `docker compose ps` | Xem container đang chạy và cổng. | Không thay đổi. |
| `docker compose logs --tail=100 cassandra` | Xem 100 dòng log gần nhất. | Không thay đổi. |
| `docker compose stop cassandra` | Dừng node Cassandra. | Volume vẫn còn. |
| `docker compose start cassandra` | Chạy lại service đã dừng. | Dữ liệu trong volume vẫn còn. |
| `docker compose down` | Xóa container/network Compose. | Named volume vẫn còn theo mặc định. |
| `docker compose up -d` | Dựng/chạy lại từ Compose config. | Tái sử dụng named volume nếu chưa bị xóa. |
| `docker compose down -v` | Xóa container, network và volume do Compose quản lý. | **Mất dữ liệu học tập** lưu trong volume. |

Để tự kiểm tra tính bền vững của dữ liệu:

1. Chạy các lệnh `INSERT` ở phần 6.
2. Thoát `cqlsh`, chạy `docker compose down`, sau đó `docker compose up -d`.
3. Đợi Cassandra sẵn sàng rồi kết nối lại `cqlsh`.
4. Chạy lại `SELECT` trên bảng trong keyspace `learning`. Hai dòng đơn hàng vẫn tồn tại vì dữ liệu được giữ ở named volume.

Nếu muốn **xóa sạch dữ liệu để làm lại bài**, chỉ khi đã chắc chắn không cần dữ liệu cũ mới dùng:

```powershell
docker compose down -v
```

Lệnh này có tính phá hủy đối với volume của môi trường Compose; không thể dùng `up -d` để khôi phục các dòng đã xóa nếu không có bản sao lưu.

**Lưu ý về thay đổi cấu hình:** Các giá trị cluster/DC, metadata Cassandra và dữ liệu đã ghi có thể tồn tại trong volume. Sửa tên DC/cluster trong Compose rồi khởi động lại container **không đồng nghĩa** Cassandra sẽ tự di chuyển hoặc tái cấu hình dữ liệu như một môi trường mới. Với bài thực hành muốn đổi topology từ đầu, hãy tạo môi trường/volume riêng hoặc reset dữ liệu một cách có chủ đích.

## 9. Những lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân hay gặp | Cách kiểm tra/xử lý |
| --- | --- | --- |
| `docker version` báo không kết nối Docker daemon | Docker Desktop/Engine chưa chạy hoặc context sai. | Mở Docker Desktop; kiểm tra `docker context ls`, chạy lại `docker version`. |
| `docker compose up -d` báo cổng 9042 đã được sử dụng | Một Cassandra khác hoặc dịch vụ khác giữ cổng host. | Kiểm tra process/container chiếm cổng; đổi mapping thành `127.0.0.1:19042:9042` và Spring port thành `19042` nếu cần. |
| Container có trạng thái `Up` nhưng `cqlsh` chưa kết nối | Cassandra đang khởi động, init hoặc phục hồi dữ liệu. | Xem `docker compose logs --tail=100 cassandra`; thử lại CQL khi server sẵn sàng. |
| Container tự dừng/exit code 137 | Có thể bị OOM kill vì thiếu bộ nhớ. | Xem `docker compose ps -a`, log và tài nguyên Docker; cân đối bộ nhớ máy/heap. |
| `nodetool status` không có node `UN` như mong đợi | Node chưa sẵn sàng hoặc có lỗi startup. | Kiểm tra log Cassandra và thông tin `nodetool`, chưa chạy workload khi node chưa normal. |
| Driver báo `AllNodesFailedException` hoặc không kết nối được | Host/port sai, CQL chưa sẵn sàng, Docker network hoặc driver config chưa đúng. | Xác minh truy vấn `cqlsh` trong container, rồi kiểm tra cổng host và `contact-points`. |
| Driver báo lỗi local DC hoặc không thấy node phù hợp | `local-datacenter` không khớp DC thực tế. | `SELECT data_center FROM system.local;` rồi đặt chính xác `dc1` nếu đó là giá trị trả về. |
| `Keyspace learning does not exist` hoặc lỗi `unconfigured table` | Chưa chạy lệnh tạo keyspace/bảng, hoặc ứng dụng trỏ sang instance khác. | `DESCRIBE KEYSPACE learning;` trong `cqlsh`; kiểm tra host/port/keyspace. |
| Truy vấn CQL phải dùng `ALLOW FILTERING` hoặc bị từ chối | Query thiếu partition key hoặc không phù hợp clustering/index. | Thiết kế bảng theo truy vấn, truyền đủ khóa partition, đừng dùng lọc rộng để che lỗi schema. |
| Đọc/ghi chậm bất thường trên máy học | Thiếu CPU/RAM, host dùng ổ đĩa chậm, JVM warmup, query/tombstone/partition lớn. | Quan sát tài nguyên Docker và kích thước truy vấn; đừng lấy benchmark một node làm SLO production. |
| Restart rồi thấy “mất dữ liệu” | Volume đã bị xóa, đổi Compose project/volume, hoặc kết nối nhầm cluster mới. | Xem tên volume hiện tại bằng `docker volume ls`, kiểm tra Compose project và keyspace; tránh `down -v` ngoài ý muốn. |

### Checklist chẩn đoán theo thứ tự

```text
Docker daemon hoạt động?
  |
  +-- Không --> Khởi động Docker Desktop/Engine
  |
  +-- Có --> Container đã chạy?  (docker compose ps)
              |
              +-- Không --> Xem log và tài nguyên Docker
              |
              +-- Có --> cqlsh trong container kết nối được?
                          |
                          +-- Không --> Chờ startup; xem log Cassandra
                          |
                          +-- Có --> Host port 9042/19042 kết nối được?
                                      |
                                      +-- Không --> Kiểm tra port mapping/firewall
                                      |
                                      +-- Có --> Đúng DC + keyspace + bảng?
                                                  |
                                                  +-- Không --> Kiểm tra cấu hình Spring và CQL
                                                  |
                                                  +-- Có --> Kiểm tra entity, query, paging, CL
```

Sơ đồ đưa ra thứ tự khoanh vùng hợp lý. Không nên điều chỉnh CL, tăng timeout hoặc bật `ALLOW FILTERING` ngay khi thấy lỗi kết nối; những lựa chọn đó xử lý các vấn đề khác nhau và có thể che mất nguyên nhân ban đầu.

## 10. Mở rộng bài thực hành và giới hạn cần nhớ

Sau khi kết nối thành công, có thể chuyển từ các lệnh CQL sang một số bài tập Spring Data Cassandra:

- **Entity mapping:** ánh xạ `orders_by_customer_month` với composite key và kiểm tra serialize/deserialize `UUID`, `Instant`, `BigDecimal`.
- **Repository:** xây API lấy đơn hàng mới nhất theo `customer_id` và `bucket_yyyymm`; quan sát lý do phải cung cấp đủ partition key.
- **`CassandraTemplate`:** tạo truy vấn với điều kiện khóa phù hợp, kiểm tra dữ liệu trả về và khác biệt giữa API mapping với thao tác `CqlSession` trực tiếp.
- **Paging:** ghi thêm hàng và dùng page size/paging state khi truy xuất nhiều trang; phân biệt paging với `LIMIT` của CQL.
- **Consistency:** quan sát `LOCAL_ONE` trong môi trường RF = 1; ghi lại những giả thuyết chưa thể kiểm chứng nếu không có nhiều replica.
- **Hiệu năng:** thử số lượng dữ liệu vừa phải, quan sát log và thời gian truy vấn; tránh chuyển kết luận từ laptop một node sang cluster nhiều node.

Để kiểm tra replication, các lựa chọn `LOCAL_QUORUM` thực sự có ý nghĩa trên nhiều replica, hành vi coordinator khi node lỗi hoặc phân vùng mạng, cần bài lab nhiều node với RF tương ứng và tài nguyên Docker đủ lớn. Khi đó cũng cần tìm hiểu token/replica placement, repair và chiến lược consistency. **Không tăng RF lên 3 trong cluster chỉ có một node rồi coi như đã nhân bản ba bản sao độc lập.**

### Tự kiểm tra sau khi hoàn thành

1. Tại sao ứng dụng Spring Boot chạy trên host dùng `127.0.0.1`, nhưng ứng dụng trong cùng Compose network lại dùng hostname `cassandra`?
2. Vì sao `docker compose ps` báo container đang chạy chưa đủ để kết luận Cassandra đã sẵn sàng nhận CQL?
3. `CASSANDRA_DC`, keyspace replication và `spring.cassandra.local-datacenter` có quan hệ gì?
4. Điều gì sẽ xảy ra với dữ liệu sau `docker compose down` so với `docker compose down -v`?
5. Với `PRIMARY KEY ((customer_id, bucket_yyyymm), created_at, order_id)`, tại sao truy vấn theo `customer_id` **mà thiếu `bucket_yyyymm`** không phải một truy vấn partition chính xác?
6. Với RF = 1, tại sao không thể dùng lab này để chứng minh ứng dụng vẫn hoạt động khi một replica mất kết nối?

**Kết quả mong đợi:** Bạn có thể khởi tạo Cassandra cục bộ, dùng `cqlsh` để tạo và đọc dữ liệu, kết nối Spring Data Cassandra tới `learning` với DC `dc1`, và phân biệt rõ kiến thức môi trường/kết nối với những đặc tính phân tán cần nhiều node để đánh giá đúng.
