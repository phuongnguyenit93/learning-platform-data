# Optimistic locking qua @Version và cơ chế cập nhật có điều kiện

## 1. Tình huống: hai người cùng sửa cấu hình, ai sẽ thắng?

Một dịch vụ Spring Boot quản lý chế độ hoạt động của thiết bị trên **Apache Cassandra**. Quản trị viên A và B cùng mở màn hình cấu hình của `device-7`, đều nhìn thấy chế độ `AUTO`. A chuyển sang `MAINTENANCE`, B chuyển sang `MANUAL`. Nếu backend thực hiện `SELECT`, sửa Java object rồi `UPDATE` thông thường, cả hai thao tác có thể thành công; một thay đổi bị ghi đè theo quy tắc hòa giải mutation của Cassandra mà không có thông báo xung đột cho người dùng.

~~~mermaid
sequenceDiagram
    participant A as Admin A
    participant B as Admin B
    participant API as Spring Boot API
    participant DB as Cassandra
    A->>API: GET device-7
    API->>DB: SELECT mode, version
    DB-->>A: AUTO, version=7
    B->>API: GET device-7
    API->>DB: SELECT mode, version
    DB-->>B: AUTO, version=7
    A->>API: PUT MAINTENANCE, expectedVersion=7
    API->>DB: UPDATE ... IF version=7
    DB-->>API: applied=true, version=8
    API-->>A: Thành công, version=8
    B->>API: PUT MANUAL, expectedVersion=7
    API->>DB: UPDATE ... IF version=7
    DB-->>API: applied=false
    API-->>B: Xung đột; tải lại version=8
~~~

Trong ví dụ này, kết quả mong muốn là **không mất cập nhật một cách âm thầm**. A được chấp nhận; yêu cầu của B phải biết dữ liệu đã thay đổi, cân nhắc đọc lại rồi quyết định tiếp. Đây là bài toán **optimistic concurrency control** (điều khiển cạnh tranh lạc quan).

Với Spring Data Cassandra, thuộc tính Java gắn **`@Version`** hỗ trợ tự động phát hiện bản entity cũ khi lưu, dựa trên **lightweight transaction (LWT)** của Cassandra. Cũng có thể tự viết CQL `INSERT ... IF NOT EXISTS`, `UPDATE ... IF version = ?`, `DELETE ... IF version = ?` và đọc kết quả **`[applied]`**. Cả hai cách đều tạo công việc điều phối thêm, không phải phép màu miễn phí.

Bài này thuộc chương **Spring Boot và Spring Data** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, kết nối mô hình wide-column, partition key, replica/coordinator, consistency đọc ghi và thao tác từ Java với xử lý lỗi production.

**Mục tiêu học tập:**

1. Nhận ra *lost update* khi đọc–sửa–ghi trong Cassandra và lý do timestamp/LWW không thay cho kiểm tra phiên bản.
2. Hiểu `@Version`, trạng thái entity mới, `IF NOT EXISTS`, `IF version = ?` và `OptimisticLockingFailureException`.
3. Viết CQL có điều kiện trên đúng **full primary key** và kiểm tra `[applied]` thay vì chỉ dựa vào HTTP status.
4. Phân biệt **regular consistency** (`LOCAL_QUORUM`) và **serial consistency** (`SERIAL`/`LOCAL_SERIAL`) của LWT.
5. Dùng Spring Boot, Spring Data repository/template hoặc Java Driver 4.x để triển khai kiểm tra xung đột rõ ràng.
6. Thiết kế HTTP `If-Match`/ETag, retry theo trường hợp, idempotency và phản hồi 409/412 không làm mất dữ liệu.
7. Đánh giá chi phí Paxos, hot partition, TTL/tombstones, nhiều DC và thực hành test cạnh tranh thực tế.

> **Phạm vi:** ví dụ dùng Spring Boot 3.x, Spring Data Cassandra 4.x, Java Driver 4.x, Cassandra với `NetworkTopologyStrategy`, full replicas và DC `dc1`. Tên API, version patch, tính năng Paxos, metrics và behavior cụ thể phải kiểm tra theo bộ phiên bản đang chạy. Không thực hiện thao tác trên production trước khi có kiểm thử, quyền và runbook phù hợp.

## 2. Optimistic locking bảo vệ điều gì?

### 2.1. Ba cách xử lý ghi cạnh tranh

| Cách tiếp cận | Kết quả có thể xảy ra | Khi nào phù hợp |
| --- | --- | --- |
| **UPDATE không điều kiện** | Một mutation thắng theo timestamp/semantics Cassandra; caller có thể không biết bản đọc đã cũ. | Dữ liệu có thể ghi đè, event/upsert idempotent hoặc hệ có nguồn thứ tự chuẩn khác. |
| **CQL `IF version = ?`** | Chỉ thay đổi khi version trên hàng vẫn đúng giá trị kỳ vọng; trả `[applied]`. | Read-modify-write của một hàng/điều kiện nhỏ, cần phát hiện lost update. |
| **Spring Data `@Version`** | Repository/template tích hợp kiểm tra version, tự nâng version khi lưu; mismatch dẫn đến exception. | Entity Spring Data CRUD cần kiểm soát cạnh tranh trên một hàng. |
| **Pessimistic/distributed lock ngoài DB** | Cố lấy khóa trước khi thao tác; cần lease/fencing/failure recovery. | Một số workflow đặc biệt, không nên mặc định vì độ phức tạp vận hành lớn. |

Trong Cassandra, **last-write-wins (LWW)** theo cell timestamp không phải “request đến sau luôn thắng” trong nghĩa wall-clock mà ứng dụng thấy. Timestamp có thể do coordinator/client tạo; replay, clock skew và tombstone có thể ảnh hưởng hòa giải. Do đó không dùng timestamp so sánh sau khi ghi như cách phát hiện chắc chắn việc hai admin đã xung đột.

### 2.2. Optimistic locking không phải một hàng được khóa suốt HTTP request

Ứng dụng có thể đọc `version=7`, chờ người dùng sửa form trong ba phút rồi gửi yêu cầu. **Không có lock được giữ trong ba phút đó**. Khi save, Cassandra thực hiện kiểm tra điều kiện tại thời điểm LWT; nếu phiên bản không còn bằng 7, lần ghi bị từ chối.

Đây là lý do gọi là “lạc quan”: phần lớn thời gian các writers không tranh chấp nên ta cho phép cùng đọc; khi ghi mới phát hiện xung đột. Đổi lại, **mọi conditional mutation** trả thêm chi phí Paxos ngay cả khi không có conflict.

### 2.3. Phạm vi nhất quán của một entity

`@Version` của Spring Data Cassandra được tài liệu chính thức mô tả là hỗ trợ **single-entity operations**, **không dành cho batch operations**. Nó không tự biến một nghiệp vụ cập nhật hai bảng, hai partition hoặc một chuỗi nhiều câu CQL thành ACID transaction nhiều hàng.

~~~text
Supported logical use case:
  Read one device_settings row -> change mode -> save if version matches.

NOT automatically atomic:
  Save device_settings row
  + append audit row
  + publish Kafka event
  + update secondary projection
~~~

Nếu phải giữ hai bảng cùng phản ánh một thay đổi, hãy thiết kế **durable event/outbox ở nguồn thích hợp, CDC/reconciliation hoặc idempotent projection updater**. Một LWT trên bảng cấu hình không tạo transaction bao phủ Kafka hay bảng khác.

## 3. LWT và Paxos: điều kiện được kiểm tra tại replica, không phải trong Java

### 3.1. Khác gì so với `if` ở service?

Phản mẫu:

~~~java
DeviceSetting setting = repository.findById(key).orElseThrow();
if (setting.getVersion().equals(expectedVersion)) {
    setting.setMode(newMode);
    repository.saveWithoutVersionCondition(setting); // API giả định: phản mẫu
}
~~~

`saveWithoutVersionCondition` là **tên giả định để chỉ ra lỗi**, không phải một API Spring Data có sẵn. Giữa lệnh `SELECT` và `UPDATE`, writer khác có thể ghi, nên **kiểm tra trong bộ nhớ Java không đủ**. Condition phải đi **cùng mutation** tới Cassandra.

~~~mermaid
flowchart TD
    A["Client gửi UPDATE ... IF version=7"] --> B["Coordinator nhận conditional mutation"]
    B --> C["Replica tham gia pha đồng thuận LWT/Paxos"]
    C --> D{"Giá trị version còn là 7?"}
    D -->|Có| E["Đề xuất/chấp nhận mutation mới; version=8"]
    D -->|Không| F["Không áp dụng, báo conflict"]
    E --> G["Phản hồi applied=true nếu hoàn tất theo CL"]
    F --> H["Phản hồi applied=false"]
~~~

Sơ đồ là **mô hình khái niệm**: số pha/round-trip, fast path và cơ chế Paxos có thể khác theo Cassandra version, contention và topology. Không khẳng định mọi phiên bản đều thực thi một số bước cố định. Ý quan trọng: kiểm tra điều kiện có **đồng thuận giữa các replica phù hợp**, không phải đọc tùy ý một replica rồi ghi đè.

### 3.2. `IF NOT EXISTS`, `IF EXISTS` và `IF version` khác nhau

| Điều kiện | Cam kết chính | Không bảo đảm |
| --- | --- | --- |
| `INSERT ... IF NOT EXISTS` | Chỉ tạo khi hàng đích chưa tồn tại theo conditional semantics. | Không tạo transaction với hàng/bảng khác; không thể tùy tiện retry với ID mới. |
| `UPDATE ... IF EXISTS` | Chỉ sửa nếu hàng tồn tại. | **Không phát hiện** một writer khác vừa sửa cùng hàng; cả hai update vẫn có thể thành công lần lượt. |
| `UPDATE ... IF version=7` | Chỉ sửa khi version vẫn đúng kỳ vọng. | Không giữ phiên bản nếu writer khác bypass và không tăng `version`. |
| `DELETE ... IF version=7` | Chỉ xóa khi hàng còn có phiên bản 7. | Không chặn workflow khác xóa và tạo lại bằng đường không điều kiện. |

**`IF EXISTS` không phải optimistic locking đầy đủ**: nó chỉ kiểm tra tồn tại, không so sánh state cụ thể. `IF version = ?` được gọi là *compare-and-set* (CAS) ở phạm vi hàng/điều kiện.

### 3.3. Serial consistency và regular consistency là hai lựa chọn

Với conditional mutation, Cassandra có hai phần cần suy nghĩ:

- **Serial consistency** (`SERIAL` hoặc `LOCAL_SERIAL`) điều khiển phạm vi đồng thuận cho pha điều kiện/Paxos.
- **Regular consistency** (ví dụ `LOCAL_QUORUM`) điều khiển yêu cầu phản hồi/applied visibility của pha ghi thông thường.

Không dùng `SERIAL` như một synonym của `LOCAL_QUORUM`. Không gọi `LOCAL_QUORUM` là “khóa lạc quan”: một write `LOCAL_QUORUM` **không có `IF`** vẫn là unconditional write.

## 4. CQL lab: một hàng cấu hình theo tenant và thiết bị

### 4.1. Keyspace và partition key

Giả sử lab có **ba full replicas tại `dc1`**, chạy các lệnh với quyền tạo schema trên lab:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_locking
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_locking.device_settings (
  tenant_id text,
  device_id text,
  mode text,
  updated_at timestamp,
  updated_by text,
  version bigint,
  PRIMARY KEY ((tenant_id, device_id))
);
~~~

**Chọn khóa:** `(tenant_id, device_id)` là composite **partition key**; mỗi cặp tenant–device tạo một partition chứa một hàng cấu hình. Cassandra hash toàn bộ composite key để định tuyến token và chọn natural replicas. Truy cập cấu hình một thiết bị cần đủ hai phần khóa, tránh `SELECT *` hoặc lọc theo `mode` xuyên toàn cluster.

Ví dụ này không thay thế bảng wide-column cho timeline sự kiện; nó minh họa một **bảng phục vụ truy vấn cập nhật trạng thái theo key**, có kích thước nhỏ, nơi LWT tương đối dễ dự đoán. Nếu hàng có collections lớn/hotspot hoặc mỗi thiết bị cập nhật hàng nghìn lần/giây, riêng LWT cũng có thể thành nút thắt.

`version bigint` là cột dữ liệu CQL do ứng dụng/mapper duy trì. Cassandra **không tự tăng version** khi một writer gửi `UPDATE` bình thường. Vì thế phải nhất quán trong mọi đường ghi.

### 4.2. Thiết lập consistency cho cqlsh

~~~sql
-- Đây là lệnh cqlsh, KHÔNG phải CQL gửi từ Java Driver.
CONSISTENCY LOCAL_QUORUM;
SERIAL CONSISTENCY LOCAL_SERIAL;
~~~

Với RF=3 full replicas trong `dc1`, `LOCAL_QUORUM` thường cần hai phản hồi. `LOCAL_SERIAL` giới hạn pha serial ở phạm vi local DC theo semantics phiên bản. Nếu hệ có **nhiều DC đều cho phép ghi tranh chấp cùng một key**, không tự cho rằng `LOCAL_SERIAL` ở các DC cung cấp một thứ tự toàn cục: phải đánh giá dùng `SERIAL` và tính đúng/độ trễ của thiết kế đa DC.

**Cú pháp cqlsh và hỗ trợ serial consistency** cần kiểm tra theo Cassandra version; có thể dùng `HELP` trong cqlsh. Trong Java Driver, hai CL được đặt riêng trên statement/profile.

## 5. Thực hành CQL: tạo, sửa, từ chối sửa và xóa có điều kiện

### 5.1. Tạo chỉ khi chưa tồn tại

~~~sql
INSERT INTO telemetry_locking.device_settings
  (tenant_id, device_id, mode, updated_at, updated_by, version)
VALUES
  ('tenant-a', 'device-7', 'AUTO',
   '2026-11-21T09:00:00Z', 'operator-a', 0)
IF NOT EXISTS;
~~~

Kết quả thành công của một conditional mutation thường có cột **`[applied]` = true**. Lặp lại lệnh trên cùng key sẽ cho **`[applied]` = false** khi hàng đã tồn tại, thay vì upsert bình thường.

~~~text
Lần 1 (lab trống):
  [applied] = true

Lần 2 (cùng primary key):
  [applied] = false
  Có thể có thông tin về giá trị hiện hành trong result.
~~~

Không giả định shape/giá trị các cột đi kèm failure luôn giống nhau giữa versions; Java nên kiểm tra **applied flag**, rồi đọc lại một cách có kiểm soát nếu cần state hiện tại.

### 5.2. Update có kiểm tra phiên bản

~~~sql
UPDATE telemetry_locking.device_settings
SET mode = 'MAINTENANCE',
    updated_at = '2026-11-21T09:01:00Z',
    updated_by = 'operator-a',
    version = 1
WHERE tenant_id = 'tenant-a'
  AND device_id = 'device-7'
IF version = 0;
~~~

Khi hàng đang có `version = 0`, mutation được áp dụng và `version = 1`. Lặp lại chính câu lệnh sẽ nhận `[applied] = false`: phiên bản không còn là 0.

~~~sql
SELECT tenant_id, device_id, mode, version, updated_at, updated_by
FROM telemetry_locking.device_settings
WHERE tenant_id = 'tenant-a'
  AND device_id = 'device-7';
~~~

**Đừng chỉ kiểm tra `version` bằng một SELECT rồi gửi UPDATE không `IF`**. Khoảng thời gian giữa hai request vẫn có race condition.

### 5.3. Cùng version, hai writers

Giả sử B chưa thấy cập nhật của A, vẫn gửi:

~~~sql
UPDATE telemetry_locking.device_settings
SET mode = 'MANUAL',
    updated_at = '2026-11-21T09:02:00Z',
    updated_by = 'operator-b',
    version = 1
WHERE tenant_id = 'tenant-a'
  AND device_id = 'device-7'
IF version = 0;
~~~

Yêu cầu B **không được áp dụng** vì version đang là 1. Nếu B quyết định tiếp tục dựa trên state mới, B cần đọc lại, kiểm tra quyền/quy tắc nghiệp vụ và tạo một yêu cầu **với expectedVersion=1, nextVersion=2**. Không sửa expectedVersion một cách mù quáng sau failure.

### 5.4. `IF EXISTS` chưa đủ để ngăn lost update

~~~sql
-- Phản ví dụ: cả A và B đều có thể được áp dụng nối tiếp,
-- miễn là hàng còn tồn tại.
UPDATE telemetry_locking.device_settings
SET mode = 'MANUAL'
WHERE tenant_id = 'tenant-a'
  AND device_id = 'device-7'
IF EXISTS;
~~~

`IF EXISTS` giúp ngăn update tạo một hàng mới ngoài dự kiến; nó **không kiểm tra bản mà người dùng đã đọc**. Dùng `IF version = ?` hoặc các điều kiện nghiệp vụ tương ứng khi cần so sánh state.

### 5.5. Xóa có kiểm tra version

~~~sql
DELETE FROM telemetry_locking.device_settings
WHERE tenant_id = 'tenant-a'
  AND device_id = 'device-7'
IF version = 1;
~~~

Chỉ áp dụng nếu version còn là 1. Thao tác `DELETE` có thể để lại **tombstone** cần bảo trì qua replication/repair/compaction và grace period phù hợp. Nếu muốn giữ audit/không cho tái tạo cùng key, một chiến lược *soft delete* với version/generation hoặc bảng tombstone nghiệp vụ có thể phù hợp hơn; **không giả định xóa vật lý tự chặn việc tạo lại**.

### 5.6. Phân biệt CQL và SQL

| Cassandra | Cách hiểu |
| --- | --- |
| `INSERT` không `IF NOT EXISTS` | Có thể upsert cùng primary key, không báo duplicate như SQL PK constraint theo nghĩa phổ biến. |
| `UPDATE` không `IF` | Có thể tạo/cập nhật hàng, không tự phát hiện lost update. |
| `UPDATE ... IF version=?` | Có conditional mutation với LWT/Paxos, cần kiểm tra `[applied]`. |
| `DELETE ... IF version=?` | Kiểm tra state trước delete, vẫn tạo tombstone khi được áp dụng. |
| `BEGIN BATCH` | Không đồng nghĩa ACID transaction đa partition của RDBMS; không thay @Version. |

**Lưu ý tính đúng:** mẫu ở mục 5.1–5.5 giả định lab bắt đầu sạch. Nếu bạn đã chạy lệnh nhiều lần, version có thể đã thay đổi hoặc hàng đã bị xóa; phải reset dữ liệu **trong lab được phép** trước khi lặp phép thử.

## 6. Tích hợp Spring Boot: dependency và cấu hình cơ sở

### 6.1. Starter và BOM

Ví dụ `pom.xml` dùng dòng Spring Boot 3.x (minh họa bằng một bản 3.4.x); chọn patch thực tế theo BOM/security policy của dự án:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example.telemetry</groupId>
  <artifactId>spring-cassandra-locking</artifactId>
  <version>1.0.0-SNAPSHOT</version>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.4.0</version>
    <relativePath/>
  </parent>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-cassandra</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
~~~

**Vì sao không chèn version riêng cho Spring Data/Java Driver?** Spring Boot BOM quản lý các thư viện liên quan. Nếu ghi đè từng JAR tùy tiện, ứng dụng có thể gặp lỗi class/method/codec/runtime dù source compile được. Khi dùng Boot khác, kiểm tra **resolved dependency graph** và release notes, không suy rằng server Cassandra cùng số version với Spring Data.

**`3.4.0` chỉ là một phiên bản ví dụ, không phải khuyến nghị mới nhất hoặc bản patch production đã được xác nhận.**

### 6.2. Kết nối Cassandra trên Spring Boot 3.x

~~~yaml
# application.yml — mọi biến nhạy cảm/endpoint cần cấp từ môi trường.
spring:
  application:
    name: telemetry-locking-api
  cassandra:
    contact-points: ${CASSANDRA_CONTACT_POINTS}
    port: ${CASSANDRA_PORT:9042}
    local-datacenter: ${CASSANDRA_LOCAL_DC}
    keyspace-name: telemetry_locking
    username: ${CASSANDRA_APP_USER}
    password: ${CASSANDRA_APP_PASSWORD}
    schema-action: none
~~~

- `spring.cassandra.*` là prefix phù hợp với nhiều bản **Boot 3.x**; Boot 2.x có thể dùng `spring.data.cassandra.*`. Kiểm tra **property metadata** bản Boot đang chạy khi nâng cấp.
- Chỉ bật CQL authentication đúng với cluster; production cần **TLS xác thực server** cùng secret manager/network policy, không copy password vào Git.
- `local-datacenter` phải bằng tên DC của snitch, không phải region cloud tự đặt. Nếu cấu hình sai, driver có thể không route được tới node.
- `schema-action: none` nhằm không tự tạo/drop schema khi start; pipeline migration chịu trách nhiệm DDL/RF, không trao quyền schema cho role của API.
- Đừng tự tạo một `CqlSession` cho mỗi HTTP request; inject bean session do Spring quản lý khi cần Core API.
- Không cho `application-dev.yml` fallback sang production khi thiếu biến. Dev, staging, prod phải có cluster, credentials, TLS trust và data riêng.

### 6.3. Chọn consistency có chủ đích

Đối với lab này, regular CL `LOCAL_QUORUM` và serial CL `LOCAL_SERIAL` là **ví dụ**. Spring Data repository có thể dùng default profile/driver config cho các statement được sinh. Phải **đo và xác minh effective settings** theo version; không suy `@Version` tự áp đặt đúng CL cho mọi topology.

~~~hocon
# Ví dụ driver 4.x: áp dụng qua config loader/customization đã kiểm thử.
datastax-java-driver {
  basic.request {
    consistency = LOCAL_QUORUM
    serial-consistency = LOCAL_SERIAL
    timeout = 3 seconds
  }
}
~~~

Các giá trị này không sửa `read_request_timeout_in_ms` hay `cas_contention_timeout_in_ms` của Cassandra server. HOCON chỉ có hiệu lực khi **config loader thực sự được sử dụng** và không bị Spring/custom builder ghi đè. Trong multi-DC active-active, cần xét `SERIAL` thay vì mặc định `LOCAL_SERIAL`; đánh giá trade-off độ trễ và semantics với bản Cassandra thực.

## 7. Spring Data: composite key là hợp đồng với token placement

### 7.1. `@PrimaryKeyClass`

~~~java
// DeviceKey.java
package example.telemetry;

import java.io.Serializable;
import java.util.Objects;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class DeviceKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(
        name = "tenant_id", ordinal = 0, type = PrimaryKeyType.PARTITIONED)
    private String tenantId;

    @PrimaryKeyColumn(
        name = "device_id", ordinal = 1, type = PrimaryKeyType.PARTITIONED)
    private String deviceId;

    public DeviceKey() {}

    public DeviceKey(String tenantId, String deviceId) {
        this.tenantId = tenantId;
        this.deviceId = deviceId;
    }

    public String getTenantId() { return tenantId; }
    public void setTenantId(String value) { tenantId = value; }

    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String value) { deviceId = value; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof DeviceKey)) return false;
        DeviceKey that = (DeviceKey) o;
        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(deviceId, that.deviceId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, deviceId);
    }
}
~~~

**Hai field `PARTITIONED`** là toàn bộ partition key của bảng; không có clustering column trong ví dụ này. Nếu schema có thêm clustering key, cần khai báo đúng loại/thứ tự tương ứng. Một `DeviceKey` thiếu `tenantId` có thể vô tình phá **tenant isolation và token routing**. Entity mapping không thay thế authorization nghiệp vụ: service vẫn phải xác minh caller được phép thao tác tenant/device ấy.

## 8. `@Version` trên entity: Spring Data gắn kiểm tra khi ghi

### 8.1. Entity ánh xạ bảng CQL

~~~java
// DeviceSetting.java
package example.telemetry;

import java.time.Instant;
import org.springframework.data.annotation.Version;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("device_settings")
public class DeviceSetting {
    @PrimaryKey
    private DeviceKey key;

    @Column("mode")
    private String mode;

    @Column("updated_at")
    private Instant updatedAt;

    @Column("updated_by")
    private String updatedBy;

    @Version
    @Column("version")
    private Long version;

    public DeviceSetting() {}

    public DeviceSetting(
            DeviceKey key, String mode, Instant updatedAt, String updatedBy) {
        this.key = key;
        this.mode = mode;
        this.updatedAt = updatedAt;
        this.updatedBy = updatedBy;
        // Với entity mới, dùng null để Spring Data nhận biết là mới.
        this.version = null;
    }

    public DeviceKey getKey() { return key; }
    public void setKey(DeviceKey value) { key = value; }

    public String getMode() { return mode; }
    public void setMode(String value) { mode = value; }

    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant value) { updatedAt = value; }

    public String getUpdatedBy() { return updatedBy; }
    public void setUpdatedBy(String value) { updatedBy = value; }

    public Long getVersion() { return version; }
    public void setVersion(Long value) { version = value; }
}
~~~

**Điểm cần nhận diện trong imports:**

- `@Version` là **`org.springframework.data.annotation.Version`**, không phải `jakarta.persistence.Version` của JPA. Dùng sai annotation có thể khiến Spring Data Cassandra không áp dụng version check.
- `Long` là **wrapper nullable**, phù hợp ví dụ Spring Data: `null` cho biết entity mới; khi insert thành công, phiên bản khởi tạo là `0`. Cách Spring Data nhận biết entity mới cũng phụ thuộc `Persistable` nếu bạn tự cài đặt nó.
- `@Column("version")` yêu cầu trong CQL có cột `version bigint`. Không dùng `counter` làm version này.
- Sau update có điều kiện thành công, version chuyển từ `0` sang `1`, rồi `2`...; cập nhật bị từ chối phải được xử lý như **conflict**, không coi là một ghi thành công.
- Entity là ánh xạ một hàng Cassandra, **không** phải JPA persistence context có dirty checking tự động.

### 8.2. Vòng đời phiên bản

~~~mermaid
stateDiagram-v2
    [*] --> New: version == null
    New --> Stored0: INSERT IF NOT EXISTS áp dụng
    New --> Conflict: Hàng đã tồn tại
    Stored0 --> Stored1: UPDATE IF version=0
    Stored0 --> Conflict: Một writer khác đã đổi version
    Stored1 --> Stored2: UPDATE IF version=1
    Stored1 --> Conflict: Dùng snapshot cũ
    Conflict --> Reload: Trả 409/412, người dùng quyết định lại
    Reload --> Stored2: Thử lại khi còn hợp lệ
~~~

Sơ đồ là mô hình logic cho ví dụ với `Long` nullable, **không thay thế chính sách retry**. Nếu hàng bị delete và tạo lại, phiên bản có thể được tái khởi tạo; với nghiệp vụ cần tránh tình huống ABA, thêm **generation/identity bất biến hoặc lifecycle tombstone** thay vì dựa duy nhất vào counter version.

### 8.3. `@Version` là field của hàng, không là `writetime`

| `version bigint` | CQL write timestamp |
| --- | --- |
| Do application/framework duy trì như **số thứ tự logic** khi conditional update thành công. | Timestamp microsecond dùng để hòa giải mutation/cell của Cassandra theo semantics storage. |
| Kiểm tra bằng `IF version = ?`. | Dùng để quyết định cell nào thắng và xử lý tombstone. |
| Được tăng theo hợp đồng nghiệp vụ; không nhất thiết là timestamp. | Không phải một con số thể hiện “số lần người dùng sửa”. |
| Có thể bị hỏng nếu writer bypass không cập nhật nó. | Có thể bị ảnh hưởng clock skew/custom timestamp và compaction/repair. |

**Đừng thay `@Version` bằng việc so `updatedAt` trong Java**, vì giữa SELECT và UPDATE vẫn có race. Nếu chọn chính `updated_at` làm điều kiện CAS của một CQL custom, vẫn phải ghi điều kiện **trong mutation**, quản lý precision/nullable và xác định tính duy nhất của giá trị.

## 9. Repository: tạo mới và lưu có điều kiện

### 9.1. Repository theo composite key

~~~java
// DeviceSettingRepository.java
package example.telemetry;

import org.springframework.data.cassandra.repository.CassandraRepository;

public interface DeviceSettingRepository
        extends CassandraRepository<DeviceSetting, DeviceKey> {
}
~~~

Không cần viết `UPDATE ... IF version=?` thủ công trong repository cho đường save entity **được Spring Data Cassandra hỗ trợ optimistic locking**. Spring Data theo dõi `@Version` khi thực hiện các thao tác single-entity tương ứng và dùng LWT phía Cassandra. Tuy nhiên, khi dùng `@Query` custom/Driver Core bypass repository, **đừng giả định mọi query tự được bọc version check**.

### 9.2. Tạo entity mới bằng `CassandraTemplate.insert`

~~~java
// DeviceSettingBootstrap.java
package example.telemetry;

import java.time.Instant;
import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.stereotype.Service;

@Service
public class DeviceSettingBootstrap {
    private final CassandraTemplate template;

    public DeviceSettingBootstrap(CassandraTemplate template) {
        this.template = template;
    }

    public DeviceSetting createOnce(
            String tenantId, String deviceId, String operator) {
        DeviceSetting fresh = new DeviceSetting(
            new DeviceKey(tenantId, deviceId),
            "AUTO",
            Instant.now(),
            operator);

        // @Version Long đang null -> phiên bản mới, conditional INSERT.
        // Nếu hàng đã tồn tại, Spring Data có thể ném
        // OptimisticLockingFailureException.
        return template.insert(fresh);
    }
}
~~~

Trong ví dụ được Spring Data chính thức mô tả, **insert entity có version null** tạo bản đầu với version `0`, dùng `INSERT ... IF NOT EXISTS`; duplicate create bị từ chối. Bản Spring Data cụ thể cần được test vì việc dùng `template.insert`, `repository.save`, `Persistable.isNew()` và custom converters có thể ảnh hưởng nhận biết entity mới.

**Lưu ý:** `@Version` không tự sinh `tenantId`/`deviceId`. Toàn bộ full primary key phải có từ trước. Không ghi `null` cho partition key.

### 9.3. Cập nhật bằng `repository.save`

~~~java
// Trích đoạn trong service, giả định repository đã được inject.
DeviceKey key = new DeviceKey("tenant-a", "device-7");
DeviceSetting current = repository.findById(key).orElseThrow();

Long versionBefore = current.getVersion(); // ví dụ 0
current.setMode("MAINTENANCE");
current.setUpdatedBy("operator-a");
current.setUpdatedAt(Instant.now());

DeviceSetting saved = repository.save(current);
Long versionAfter = saved.getVersion();    // thường là 1 sau cập nhật
~~~

Nếu một writer khác đã sửa sau lúc `findById`, khi save phiên bản cũ Spring Data phát hiện điều kiện không thỏa và ném **`OptimisticLockingFailureException`** (`org.springframework.dao`). Điều này khác `ReadTimeout`/`WriteTimeout`: một conflict được xác nhận có nghĩa **mutation điều kiện không được áp dụng**, còn timeout có thể khiến kết quả không chắc chắn.

### 9.4. Vì sao `saveAll` không phải transaction nhiều entity?

Spring Data Cassandra chỉ bảo đảm optimistic locking theo **single-entity operation** được hỗ trợ. `saveAll` có thể thực hiện nhiều thao tác, mỗi entity có kết quả riêng; nó **không biến danh sách entity thành một transaction đa partition**.

~~~text
Update entity A version=3 -> áp dụng.
Update entity B version=8 -> conflict.

Kết quả có thể:
  A đã thay đổi, B bị từ chối.
Không được suy toàn bộ saveAll đã rollback về trạng thái ban đầu.
~~~

Với workflow bắt buộc đồng bộ A/B, thiết kế dữ liệu theo phạm vi atomicity phù hợp hoặc dùng durable mutation log/reconciliation. Không dùng `@Transactional` trong Spring để giả định một transaction Cassandra giống SQL/JPA.

## 10. Race condition thực tế: hai service instance cùng sửa một entity

### 10.1. Khi không có `@Version`

~~~text
T0: A SELECT mode=AUTO
T1: B SELECT mode=AUTO
T2: A UPDATE mode=MAINTENANCE (ACK)
T3: B UPDATE mode=MANUAL       (ACK)

Không có conflict flag.
Giá trị cuối phụ thuộc timestamp/mutation reconciliation.
Người dùng A có thể không biết thay đổi đã bị ghi đè.
~~~

### 10.2. Khi có `@Version`

~~~text
T0: A SELECT mode=AUTO, version=5
T1: B SELECT mode=AUTO, version=5
T2: A SAVE IF version=5 -> applied=true, version=6
T3: B SAVE IF version=5 -> applied=false

A: thành công.
B: OptimisticLockingFailureException.
Hàng vẫn giữ thay đổi của A; không bị B ghi đè âm thầm.
~~~

**Các trạng thái ở đây chỉ là ví dụ.** Một test concurrency thật không được giả định writer A luôn thắng; nếu hai request tranh cùng version, **chỉ một conditional mutation phù hợp được áp dụng** trong tình huống cạnh tranh được điều phối đúng, còn request kia thấy conflict/timeout tùy sự cố.

### 10.3. Phân biệt ba kết cục

| Kết cục | Bằng chứng | Hành động |
| --- | --- | --- |
| **Applied** | LWT xác nhận điều kiện thỏa và mutation được chấp nhận theo CL. | Trả object/version mới, ghi audit/metrics theo policy. |
| **Not applied / version mismatch** | `[applied]=false` hoặc exception optimistic locking đã xác định conflict. | Trả 409/412, yêu cầu caller đọc lại/giải quyết xung đột. |
| **Unknown/timeout** | Request timed out/connection mất ở pha điều kiện hoặc apply. | Không tự kết luận failed; kiểm tra phiên bản/state và idempotency trước retry. |

**Nên gắn correlation ID và request ID** (không phải mỗi timeout đều được retry). Nếu write có side effect bên ngoài Cassandra, cần cơ chế dedup/outbox để ứng dụng biết một attempt đã xử lý hay chưa.

## 11. Service: bảo vệ version kỳ vọng từ client tới Cassandra

Một lỗi thiết kế HTTP phổ biến là **đọc lại entity mới nhất rồi luôn save**, bỏ qua version mà browser đã thấy khi mở form. Điều đó vẫn gây *lost update* ở mức giao diện người dùng, dù repository có `@Version`:

~~~text
Browser B gửi expectedVersion=5 từ form cũ.
Service đọc lại version=6 nhưng KHÔNG so với expectedVersion.
Service áp thay đổi B lên version=6 rồi save; CAS thành công.
=> đã ghi đè quyết định của A theo cách người dùng không mong muốn.
~~~

Vì vậy service phải kiểm tra **expectedVersion từ client**, đồng thời `repository.save` dùng CAS để loại khoảng race **sau khi service đọc lại**.

### 11.1. Service với precondition và xử lý conflict

~~~java
// DeviceSettingsService.java
package example.telemetry;

import java.time.Instant;
import java.util.Objects;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.stereotype.Service;

@Service
public class DeviceSettingsService {
    private final DeviceSettingRepository repository;

    public DeviceSettingsService(DeviceSettingRepository repository) {
        this.repository = repository;
    }

    public DeviceSetting changeMode(
            String tenantId,
            String deviceId,
            long expectedVersion,
            String mode,
            String operator) {

        if (!("AUTO".equals(mode)
                || "MANUAL".equals(mode)
                || "MAINTENANCE".equals(mode))) {
            throw new IllegalArgumentException("Unsupported device mode");
        }

        DeviceKey key = new DeviceKey(tenantId, deviceId);
        DeviceSetting current = repository.findById(key)
            .orElseThrow(() -> new DeviceSettingNotFoundException());

        // So expectedVersion của browser với state MỚI đọc.
        if (!Objects.equals(current.getVersion(), expectedVersion)) {
            throw new StaleDeviceVersionException();
        }

        current.setMode(mode);
        current.setUpdatedAt(Instant.now());
        current.setUpdatedBy(operator);

        try {
            // Có @Version: CAS ngăn race giữa lần đọc và lần save.
            return repository.save(current);
        } catch (OptimisticLockingFailureException conflict) {
            throw new StaleDeviceVersionException(conflict);
        }
    }

    public static final class DeviceSettingNotFoundException
            extends RuntimeException {}

    public static final class StaleDeviceVersionException
            extends RuntimeException {
        public StaleDeviceVersionException() {
            super("Device setting changed; reload before editing");
        }
        public StaleDeviceVersionException(Throwable cause) {
            super("Device setting changed; reload before editing", cause);
        }
    }
}
~~~

**Phạm vi:** đây là service lab cho một entity. Production phải kiểm tra **tenant authorization** và identity của operator trước khi gọi repository, giới hạn rate/timeout, tránh ghi log dữ liệu nhạy cảm và có contract riêng khi Cassandra trả kết quả **unknown**, không chỉ conflict.

### 11.2. Hai cơ chế so version có khác nhau

1. **So với `expectedVersion` từ HTTP:** ngăn người dùng dùng form cũ để ghi đè một thay đổi đã biết trong DB lúc request bắt đầu.
2. **`@Version`/LWT khi save:** ngăn race xảy ra **giữa lúc service đọc và lúc service ghi**.

Chỉ có số 1 mà không có số 2 vẫn còn race; chỉ có số 2 mà bỏ qua version của browser có thể gây hành vi “lấy state mới nhất rồi cố ghi lệnh cũ” trái ý người dùng.

### 11.3. Khi nhận exception không phải conflict

Không bắt mọi `RuntimeException` rồi trả `StaleDeviceVersionException`. Lỗi `Unauthorized`, `Unavailable`, `CASWriteTimeout`, request timeout, mapping/codec hoặc schema mismatch **không chứng minh** version đã thay đổi. Hãy để exception propagates tới handler phù hợp và trả lỗi tạm thời/không xác định, hoặc reconciliation theo runbook.

## 12. HTTP ETag / If-Match: gửi precondition qua API

Một pattern tiêu chuẩn để browser gửi version mà nó đã thấy:

~~~http
GET /api/tenants/tenant-a/devices/device-7/settings

HTTP/1.1 200 OK
ETag: "7"
Content-Type: application/json

{"mode":"AUTO","version":7}
~~~

Sau đó client gửi:

~~~http
PUT /api/tenants/tenant-a/devices/device-7/settings/mode
If-Match: "7"
Content-Type: application/json

{"mode":"MAINTENANCE"}
~~~

Nếu một người khác đã lưu version 8, API trả:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json

{"title":"Version conflict","detail":"Reload the setting and retry"}
~~~

**HTTP 412** thích hợp khi **`If-Match` precondition** không thỏa; **409 Conflict** cũng được nhiều API dùng cho conflict cấp nghiệp vụ mà không dựa vào header. Chọn một contract rõ, có test và không ép 409/412 thành 500.

### 12.1. Controller kiểm tra ETag số nguyên

~~~java
// DeviceSettingsController.java
package example.telemetry;

import java.util.Objects;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/tenants/{tenantId}/devices/{deviceId}/settings")
public class DeviceSettingsController {
    public record ModeRequest(String mode) {}
    public record ModeResponse(String mode, long version) {}

    private final DeviceSettingsService service;

    public DeviceSettingsController(DeviceSettingsService service) {
        this.service = service;
    }

    @PutMapping("/mode")
    public ResponseEntity<ModeResponse> setMode(
            @PathVariable String tenantId,
            @PathVariable String deviceId,
            @RequestHeader("If-Match") String ifMatch,
            @RequestBody ModeRequest request) {

        // API ví dụ chỉ nhận strong ETag dạng "7"; không nhận W/"7"
        // hoặc dấu sao nếu không định nghĩa semantics của chúng.
        if (!ifMatch.matches("\"[0-9]+\"")) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Expected strong numeric ETag");
        }
        long expected;
        try {
            expected = Long.parseLong(
                ifMatch.substring(1, ifMatch.length() - 1));
        } catch (NumberFormatException invalid) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid version number");
        }

        // Giả định authorization kiểm tra caller/tenant ở service filter.
        DeviceSetting saved = service.changeMode(
            tenantId, deviceId, expected, request.mode(), "api-operator");

        return ResponseEntity.ok()
            .eTag("\"" + Objects.requireNonNull(saved.getVersion()) + "\"")
            .body(new ModeResponse(saved.getMode(), saved.getVersion()));
    }

    @ExceptionHandler(DeviceSettingsService.StaleDeviceVersionException.class)
    public ResponseEntity<String> stale() {
        return ResponseEntity.status(HttpStatus.PRECONDITION_FAILED)
            .body("Version conflict; reload current resource");
    }

    @ExceptionHandler(DeviceSettingsService.DeviceSettingNotFoundException.class)
    public ResponseEntity<String> missing() {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body("Device setting not found");
    }
}
~~~

**Đây là API học tập**, không phải HTTP implementation hoàn chỉnh. Production còn cần phân quyền tenant, validation, tránh hardcode operator, kiểm soát kích thước payload, error responses không lộ state và cơ chế cấp **428 Precondition Required** nếu header bắt buộc bị thiếu. Cần định nghĩa ETag không bị thay đổi bởi serialization/representation không liên quan và test với reverse proxy/cache.

Nếu API trả về version 8 sau ghi, client phải lưu **ETag mới** cho lần sửa tiếp theo. Browser không được tự tăng version từ 7 lên 8 rồi retry một thay đổi dựa trên form cũ khi chưa đọc hoặc xử lý conflict.

## 13. Java Driver Core: tự phát CQL điều kiện và đọc `wasApplied()`

Spring Data `@Version` phù hợp cho CRUD entity. Khi cần một statement **chỉ cập nhật một vài cột** hoặc muốn điều khiển CL/serial CL per-request, có thể dùng Java Driver 4.x trực tiếp — **với điều kiện tất cả các writer của cùng hàng vẫn tuân thủ protocol version**.

### 13.1. Prepared CAS update

~~~java
// ConditionalModeUpdate.java
package example.telemetry;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.Instant;

public final class ConditionalModeUpdate {
    private final CqlSession session;
    private final PreparedStatement cas;

    public ConditionalModeUpdate(CqlSession session) {
        this.session = session;
        this.cas = session.prepare(
            "UPDATE telemetry_locking.device_settings " +
            "SET mode = ?, updated_at = ?, updated_by = ?, version = ? " +
            "WHERE tenant_id = ? AND device_id = ? IF version = ?");
    }

    public boolean trySetMode(
            String tenantId, String deviceId,
            long expectedVersion, String newMode, String operator) {
        if (expectedVersion == Long.MAX_VALUE) {
            throw new IllegalArgumentException("Version overflow");
        }

        BoundStatement statement = cas.bind(
                newMode,
                Instant.now(),
                operator,
                expectedVersion + 1,
                tenantId,
                deviceId,
                expectedVersion)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

        ResultSet result = session.execute(statement);
        // Với CQL conditional mutation, true = điều kiện được áp dụng.
        return result.wasApplied();
    }
}
~~~

`setSerialConsistencyLevel` là API của statement Java Driver 4.x; `LOCAL_SERIAL` dành cho pha LWT theo topology phù hợp. `wasApplied()` **không phải** “HTTP status đã nhận 200”; nó là trạng thái áp dụng **conditional statement** mà driver nhận được. Nếu `execute()` ném timeout, **không có `ResultSet` để gọi `wasApplied()`** và outcome có thể chưa chắc chắn.

### 13.2. Không trộn version schemes khác nhau

Nếu repository dùng `@Version Long` nhưng một job backfill dùng:

~~~sql
-- PHẢN MẪU: bỏ qua kiểm tra và cập nhật version.
UPDATE telemetry_locking.device_settings
SET mode = 'AUTO'
WHERE tenant_id = 'tenant-a'
  AND device_id = 'device-7';
~~~

thì job có thể sửa `mode` mà **giữ nguyên version**, khiến một client cũ vẫn vượt `IF version = 7` sau đó và ghi đè. Tất cả các đường ghi (API, batch, migration, admin tool) phải:

- Tuân theo **một hợp đồng CAS/version chung**, hoặc
- Làm việc trong maintenance window đóng băng writes và có chứng cứ reconciliation/cutover, với rủi ro được phê duyệt.

**Không** tạo bộ ghi có điều kiện và bộ ghi vô điều kiện cùng chạy trên một hàng rồi tuyên bố đã bảo đảm optimistic locking.

### 13.3. Tại sao không chỉ cần `UPDATE ... IF mode = 'AUTO'`?

Conditional update có thể so một thuộc tính nghiệp vụ thay vì version:

~~~sql
UPDATE telemetry_locking.device_settings
SET mode = 'MAINTENANCE'
WHERE tenant_id = 'tenant-a'
  AND device_id = 'device-7'
IF mode = 'AUTO';
~~~

Điều này hữu ích nếu **quy tắc nghiệp vụ chỉ quan tâm mode**. Nhưng hai thay đổi khác nhau (ví dụ `updated_by`, policy quota hoặc một field khác) có thể không đổi `mode`, dẫn đến một stale client vẫn áp dụng được. **Version tăng với mọi mutation có ý nghĩa nghiệp vụ** giúp phát hiện tập thay đổi rộng hơn. Chọn condition theo invariant cần bảo vệ, không dùng version như thủ tục trang trí.

## 14. `SERIAL` và `LOCAL_SERIAL` trong hệ đa datacenter

### 14.1. Một DC

Giả định `NetworkTopologyStrategy {'dc1':3}`, ba full replicas:

| Thiết lập | Phạm vi | Ý nghĩa |
| --- | --- | --- |
| `LOCAL_QUORUM` regular CL | Local DC `dc1` | Phản hồi đủ quorum local ở pha regular write/read. |
| `LOCAL_SERIAL` serial CL | Serial phase trong local DC | Phục vụ conditional coordination theo phiên bản/replica placement. |
| `SERIAL` serial CL | Rộng hơn local, có thể bao trùm các DC trong policy multi-DC | Phù hợp khi cần thứ tự điều kiện xuyên DC; tăng phụ thuộc WAN/latency. |

Một request dùng **cả regular và serial CL** theo hai vai trò. `SERIAL` chỉ nên được chọn khi hợp đồng consistency cần phạm vi đó; **không tự giả định nó giúp performance**.

### 14.2. Hai DC cùng có writers

~~~mermaid
flowchart TD
    A["Writer A tại dc1"] --> C["Hàng (tenant-a, device-7) có replicas ở dc1/dc2"]
    B["Writer B tại dc2"] --> C
    C --> D{"LWT scope đã duyệt?"}
    D -->|LOCAL_SERIAL riêng từng DC| E["Cần đánh giá rủi ro ordering/visibility xuyên DC"]
    D -->|SERIAL toàn phạm vi yêu cầu| F["Đồng thuận rộng hơn, WAN latency và availability trade-off"]
    E --> G["Test conflict, outage và recovery thực tế"]
    F --> G
~~~

Với `NetworkTopologyStrategy {'dc1':3,'dc2':3}`, một ứng dụng active-active ở cả hai DC phải **chốt invariants**: có cho hai admin ở hai DC thay đổi cùng thiết bị đồng thời không? Có yêu cầu **linearizability toàn cluster** cho những conditional writes không? Nếu có, thiết kế/kiểm chứng serial CL theo docs bản Cassandra và chịu thêm độ trễ, availability constraints của liên kết DC.

**Không tự chọn `LOCAL_SERIAL`** chỉ vì hai service đều nằm “gần một replica”. `LOCAL_SERIAL` có phạm vi đồng thuận địa phương; cơ chế replication bất đồng bộ/độ trễ WAN có thể làm sai giả định “chỉ một writer toàn thế giới”.

### 14.3. Serial read không đồng nghĩa read bình thường

Theo mô tả của Cassandra, serial consistency có thể dùng trong bối cảnh conditional read/đọc state gần LWT đang diễn ra. Nhưng không nên chuyển toàn bộ các SELECT sang `SERIAL` theo cảm tính. Với dữ liệu bình thường, một `SELECT` theo partition key và CL phù hợp giúp tránh chi phí không cần thiết. **Không xem `SERIAL` là tùy chọn “read mới nhất với chi phí bằng `LOCAL_ONE`”.**

## 15. TTL, delete, tombstone và phiên bản bị đặt lại

### 15.1. Version phải sống lâu bằng invariant cần bảo vệ

Với dữ liệu time-series, TTL là lựa chọn phổ biến để hết hạn tự động. Nhưng bảng `device_settings` chứa **state và version kiểm soát cạnh tranh**. Nếu đặt TTL cho version mà state vẫn còn sống, phiên bản có thể biến mất trước khi user lưu:

~~~text
09:00: mode = MANUAL, version = 7
09:05: version cell hết TTL, mode cell còn tồn tại
09:06: API gửi IF version = 7
       -> condition không khớp vì version không còn tồn tại như trước
~~~

Không dùng `default_time_to_live` tùy tiện cho bảng điều khiển cấu hình nếu giao dịch cần giữ phiên bản ổn định. Nếu nghiệp vụ muốn cấu hình tự hết hạn, phải xác định **entire-row lifecycle, version/generation, re-create semantics và audit**.

### 15.2. TTL không dựa vào `updated_at`

~~~sql
-- Chỉ là ví dụ biểu diễn một cột có TTL; KHÔNG dùng trên bảng
-- device_settings đang tham gia @Version nếu chưa thiết kế lifecycle.
UPDATE telemetry_locking.device_settings
USING TTL 300
SET updated_by = 'temporary-operator'
WHERE tenant_id = 'tenant-a'
  AND device_id = 'device-7';
~~~

TTL tính theo semantics ghi của Cassandra, **không tự tính theo thời điểm trong cột `updated_at`**. Khi một cell hết TTL, việc thu hồi vật lý diễn ra thông qua cơ chế tombstone/SSTable/compaction; không suy ngay “file đã biến mất”. Restore logical hoặc retry với TTL mới có thể **gia hạn** dữ liệu ngoài ý muốn.

### 15.3. Delete và ABA

Ví dụ:

~~~text
Hàng đời 1: tenant-a/device-7, version=2, mode=MANUAL
Xóa hàng -> tombstone
Tạo lại cùng primary key -> version=0

Một client cũ từng đọc version=0 của đời trước
có thể nhầm state mới nếu chỉ so số version, khi reset/lifecycle phức tạp.
~~~

Đây là biến thể rủi ro **ABA**: một state/phiên bản có thể trở về cùng giá trị nhưng đại diện **đời dữ liệu khác**. Trong nghiệp vụ không được phép tái tạo cùng identity hoặc cần phân biệt vòng đời, dùng **incarnation ID/generation** bất biến hoặc **soft delete** có version không reset tùy thiết kế. Nếu dùng các bảng audit/projection, bảo đảm delete và phục hồi tuân theo hợp đồng.

### 15.4. Tombstone, repair và `gc_grace_seconds`

Conditional delete được áp dụng vẫn tạo tombstone. Replica có thể bỏ lỡ một số mutation nếu down/partition, vì vậy phải có kế hoạch **repair** và khoảng grace phù hợp trước khi tombstone có thể được thu hồi an toàn. **Không giảm `gc_grace_seconds` tùy tiện** để tối ưu dung lượng vì có thể gây zombie data khi replica cũ trở lại.

**Tóm lại:** optimistic locking bảo vệ việc ghi cạnh tranh theo version; nó **không tự giải quyết retention, expiry, tombstones, replay hoặc phục hồi từ backup**.

## 16. Phân biệt conflict, timeout, unavailable và lỗi ứng dụng

Một hệ thống production phải phân loại outcome trước khi quyết định retry.

| Kết quả/lỗi | Có biết conditional mutation đã được áp dụng? | Xử lý |
| --- | --- | --- |
| `wasApplied() == true` | Có xác nhận từ driver theo semantics CL. | Trả version mới; ghi metric success. |
| `wasApplied() == false` | Biết điều kiện **không được chấp nhận** cho lần đó. | Conflict; không tự đổi dữ liệu của người khác. |
| `OptimisticLockingFailureException` vì version cũ | Spring Data xác nhận xung đột optimistic locking trong đường hỗ trợ. | Trả 409/412, yêu cầu đọc lại/merge hoặc huỷ thao tác. |
| `Unavailable` | Không có đủ replica phù hợp CL tại thời điểm nhận yêu cầu. | Kiểm tra RF/DC/node, không tăng timeout hay hạ CL vô điều kiện. |
| `ReadTimeout` | Không hoàn tất read trong thời hạn. | Có thể retry read có budget khi an toàn, không trả “not found”. |
| `WriteTimeout`/CAS timeout | **Có thể chưa biết** request đã được chấp nhận đến đâu. | Đọc/reconcile state, giữ request ID, tránh retry mutation không idempotent. |
| Driver request timeout/connection lost | Không có phản hồi đủ tin cậy. | Tìm root cause/traffics, outcome unknown khi request có thể đã gửi. |
| `Unauthorized` | CQL role không được phép. | Sửa RBAC/identity, không retry liên tục hoặc dùng superuser. |
| Schema/codec mismatch | CQL hoặc Java mapping không tương thích. | Sửa schema/driver/converter, không trả conflict giả. |

**Đừng viết `catch (Exception ignored) { return false; }`** cho CAS. Nó biến lỗi hạ tầng hoặc quyền truy cập thành “phiên bản không khớp” và khiến caller có thể hành động sai.

### 16.1. Retry conflict khác retry timeout

- **Conflict xác nhận:** lần CAS hiện tại không áp dụng; service có thể yêu cầu người dùng kiểm tra lại state. Với phép cập nhật **commutative** hoặc quy tắc nghiệp vụ cho phép auto-merge, có thể đọc lại và tính mutation mới, nhưng phải có **số lần thử và deadline tối đa**.
- **Timeout không rõ kết quả:** có thể đã apply. Trước retry phải xem **state hiện tại** và kiểm chứng **operation ID/version/desired state**, vì một retry `IF version=old` có thể trả false đơn giản do **chính lần đầu đã thành công**, không phải do một người khác.
- **Unavailable:** không có đủ replica cho CL, retry nhanh liên tục thường chỉ tăng tải. Điều tra topology và capacity.
- **Auth/schema/validation:** không retry tự động cùng input như lỗi tạm thời.

### 16.2. CAS false sau timeout không chứng minh lần đầu thất bại

~~~text
Client gửi: IF version=7, SET version=8, mode=MANUAL
Cassandra có thể đã áp dụng, nhưng response bị mất.
Client retry y hệt: IF version=7 -> applied=false (đang là 8).

Nếu service diễn giải applied=false của lần retry = "thao tác thất bại",
nó có thể báo sai kết quả dù mode=MANUAL đã được ghi.
~~~

Để phân biệt **“chính request đã thành công”** với **“writer khác đã đổi state”**, cân nhắc một `last_operation_id`/mutation ID trong cùng hàng, được ghi cùng conditional update và đọc lại trong reconciliation, với uniqueness/retention policy rõ. Với side effects ngoài Cassandra, cần durable idempotency log/outbox thích hợp — **không** chỉ dựa vào mode bằng nhau.

### 16.3. Đặt retry budget và backoff

~~~text
Ví dụ policy (không phải default Cassandra):
  API deadline tổng: 800 ms
  CAS attempts: tối đa 2 nếu nghiệp vụ thật sự cho phép
  Backoff: bounded exponential + jitter
  Không retry tự động: Unauthorized, InvalidQuery, stale If-Match
  Unknown timeout: reconciliation/idempotency policy
  Retry budget toàn fleet: ngưỡng lỗi/traffic rõ ràng
~~~

Chỉ đặt **số lần retry** mà không đặt deadline và in-flight budget vẫn có thể tạo retry storm. Không `Thread.sleep` trong driver/event-loop callback; dùng scheduler/backoff có giới hạn khi pipeline bất đồng bộ.

## 17. Chi phí LWT: mỗi điều kiện tạo thêm coordination

### 17.1. Vì sao LWT đắt hơn upsert thường?

`INSERT`/ `UPDATE` không điều kiện thường không phải chạy giao thức serial consensus. `IF NOT EXISTS` hoặc `IF version` cần các replica tham gia **đồng thuận/kiểm tra trạng thái** phù hợp, thêm round-trips, CPU, network, khả năng tranh chấp và latency đặc biệt khi WAN/DC chậm.

~~~mermaid
flowchart LR
    A["Write thường: INSERT / UPDATE"] --> B["Coordinator"]
    B --> C["Replicas + regular CL ACK"]
    D["LWT: UPDATE ... IF version"] --> E["Coordinator"]
    E --> F["Serial agreement / Paxos"]
    F --> G["Conditional mutation + regular CL"]
    G --> H["applied true/false hoặc lỗi"]
~~~

Không mô tả “LWT chậm chính xác N lần” cho mọi cluster; số bước, tối ưu hóa Paxos, contention, replica health và topology **khác theo version**. Cần benchmark với workload cụ thể.

### 17.2. Ví dụ số đo giả lập

| Chỉ số (giả lập) | UPDATE thông thường | UPDATE có `IF version` |
| --- | ---: | ---: |
| Read/modify/write bên ứng dụng | Không bắt buộc | Có thể đọc trước nếu cần state nghiệp vụ. |
| Median latency | 3 ms | 11 ms |
| p99 latency | 15 ms | 42 ms |
| Conflict rate | Không phát hiện | 4% |
| Replica/client round-trips | Ít hơn | Có thêm pha điều kiện/consensus |
| Rủi ro lost update | Có nếu state dựa vào bản đọc cũ | Giảm khi mọi writer tuân thủ version protocol |

**Các con số hoàn toàn giả lập**, không phải benchmark hay ngưỡng khuyến nghị Cassandra. Chúng minh họa cần đo thêm **p95/p99, CAS contention, rejection/conflict, coordinator/replica latency và CPU/network** thay vì chỉ đánh giá code Java có ngắn hay không.

### 17.3. Hot partition và contention

Một bảng có partition key **duy nhất** như `global_config` sẽ gom mọi writer của cả công ty vào một partition/LWT contention domain. Nếu 5.000 clients cùng sửa một version trong mỗi giây, hầu hết sẽ đọc version cũ rồi **bị conflict** hoặc tăng tail latency.

Với `PRIMARY KEY ((tenant_id,device_id))`, các thiết bị khác nhau có thể hash ra token/replica khác nhau, giúp phân tán, nhưng **một thiết bị cực nóng** vẫn tranh cùng hàng. Giải pháp có thể là:

- Thiết kế một **owner/single writer** cho key nóng, serialize commands từ queue upstream.
- Chuyển từ “mỗi heartbeat sửa mode/version” sang append-only event hoặc aggregation có ranh giới.
- Giới hạn rate theo tenant/device, cache read hợp lệ và sử dụng idempotency.
- Phân biệt state cần CAS thật sự với telemetry event có thể ghi bình thường.

**Không dùng LWT cho mọi event ingest** chỉ để “bảo đảm dữ liệu tốt hơn”. Với append-only time-series, immutable event ID và upsert/idempotency có thể đủ; dành LWT cho invariant thực sự cần compare-and-set.

### 17.4. Metrics cho CAS

| Nguồn | Metric cần theo dõi | Ý nghĩa |
| --- | --- | --- |
| Spring API | `cas_success`, `cas_conflict`, `cas_timeout`, `cas_unknown`, p95/p99. | Phân biệt conflict nghiệp vụ và backend failure. |
| Driver | Request latency, retry attempts, in-flight, throttler queue, coordinator distribution. | Phát hiện overload phía client và route. |
| Cassandra | CAS/Paxos latency/contention theo metric phiên bản, read/write latency, dropped/pending tasks. | Kiểm tra coordination bottleneck. |
| Replica JVM/OS | CPU, GC, disk latency, network RTT/retransmits. | Tách vấn đề physical capacity khỏi code `@Version`. |
| Application | ETag/If-Match mismatch, per-key contention mẫu hóa, retry age/budget. | Phát hiện UX/client đang gửi state cũ. |

**Không gắn `tenant_id`, `device_id`, request UUID hoặc raw payload vào metric labels** nếu có cardinality lớn hoặc nhạy cảm. Dùng `query_name`, `outcome`, `environment`, `local_dc` và endpoint; điều tra key nóng bằng sampling an toàn.

## 18. Batch, counter và nhiều bảng: giới hạn của abstraction

### 18.1. `@Version` không thay transaction nhiều entity

Giả sử một yêu cầu đồng thời:

~~~text
1. UPDATE device_settings IF version=7 -> applied=true
2. INSERT device_audit_event            -> timeout
3. UPDATE site_settings                -> applied=false
~~~

Không thể gọi chuỗi đó là một transaction đã rollback toàn bộ chỉ vì step 1 dùng `@Version`. Nếu audit event bắt buộc, cân nhắc nguồn lệnh/bản ghi **durable log** và một worker idempotent tạo projection/audit; thiết kế thứ tự và reconciliation khi một bước thất bại.

### 18.2. Counter có semantics riêng

Không dùng `counter` column làm `version` để viết kiểu `SET version = version + 1 IF ...`; Cassandra counter update và CAS có những giới hạn khác. **Phiên bản logic** dùng kiểu integer thường (ví dụ `bigint`) và được ứng dụng tăng theo **cùng conditional mutation**.

### 18.3. LWT không tự cấp global uniqueness trên mọi key

`INSERT ... IF NOT EXISTS` chỉ bảo vệ **primary key/điều kiện cụ thể**. Nếu hai tenant dùng khác partition key, việc có một `email` hoặc `deviceSerial` xuất hiện một lần toàn hệ thống **không** được bảo đảm chỉ nhờ CAS trên `(tenant_id,device_id)`. Cần **uniqueness-claim table** keyed theo giá trị duy nhất cùng workflow/idempotency/reconciliation, hoặc cơ chế dữ liệu khác phù hợp.

Không viết một câu `SELECT` toàn bảng để kiểm tra “chưa ai dùng serial này” rồi `INSERT`: giữa SELECT và INSERT vẫn có race, và query có thể scan rất tốn kém.

### 18.4. Không dùng `IF` để thay data modeling

CQL `UPDATE ... IF` theo **full primary key** có thể chặn lost update trên hàng, nhưng không biến `WHERE mode='AUTO' ALLOW FILTERING` thành indexed update hàng loạt. Muốn thao tác hàng loạt có điều kiện, hãy xác định partition/key từ nguồn dữ liệu hoặc bảng theo truy vấn, giới hạn concurrency và xử lý từng result/idempotency.

## 19. Kiểm thử Spring Data `@Version` bằng Cassandra thật

### 19.1. Tại sao unit test với mock không đủ?

Một unit test mock `DeviceSettingRepository.save` trả object có `version+1` có thể xanh, nhưng **không chứng minh Spring Data đã phát CQL LWT**. Phải có integration test với:

1. Cassandra version được dự án hỗ trợ, native protocol/driver tương ứng.
2. Keyspace và schema **có cột `version bigint`** và đúng composite partition key.
3. Hai bản entity khác nhau cùng đọc một version.
4. Writer thứ nhất lưu thành công; writer thứ hai dùng bản cũ bị từ chối.
5. Tạo trùng key và xóa stale entity có behavior đúng.
6. Regular CL/serial CL, TLS/RBAC/permissions đúng theo môi trường test.

### 19.2. JUnit integration test cho phiên bản cũ

~~~java
// DeviceSettingVersionIT.java
package example.telemetry;

import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.test.context.ActiveProfiles;
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
@ActiveProfiles("test")
class DeviceSettingVersionIT {
    @Autowired DeviceSettingRepository repository;

    @Test
    void staleEntityCannotOverwriteSuccessfulUpdate() {
        DeviceKey key = new DeviceKey(
            "tenant-test", "device-" + UUID.randomUUID());

        DeviceSetting fresh = new DeviceSetting(
            key, "AUTO", Instant.now(), "test-seed");
        DeviceSetting created = repository.save(fresh);
        assertThat(created.getVersion()).isEqualTo(0L);

        // Hai object được đọc riêng nhưng cùng version=0.
        DeviceSetting copyA = repository.findById(key).orElseThrow();
        DeviceSetting copyB = repository.findById(key).orElseThrow();
        assertThat(copyA.getVersion()).isEqualTo(copyB.getVersion());

        copyA.setMode("MAINTENANCE");
        copyA.setUpdatedAt(Instant.now());
        copyA.setUpdatedBy("test-a");
        DeviceSetting accepted = repository.save(copyA);
        assertThat(accepted.getVersion()).isEqualTo(1L);

        copyB.setMode("MANUAL");
        copyB.setUpdatedAt(Instant.now());
        copyB.setUpdatedBy("test-b");
        assertThrows(OptimisticLockingFailureException.class,
            () -> repository.save(copyB));

        DeviceSetting finalState = repository.findById(key).orElseThrow();
        assertThat(finalState.getMode()).isEqualTo("MAINTENANCE");
        assertThat(finalState.getVersion()).isEqualTo(1L);
    }
}
~~~

**Điều kiện để test đáng tin:**

- `application-test.yml` phải trỏ tới **cluster test cô lập**, có đúng keyspace/DDL và các replicas phù hợp. Không dùng cluster production, không chạy khi application context tự tạo/drop bảng không được duyệt.
- Mỗi test dùng key riêng, tránh kết quả phụ thuộc lần chạy trước. Cleanup phải theo chính sách test/TTL; khi `deleteById` bỏ qua version check ở một đường nào đó, không dùng cleanup ấy làm bằng chứng optimistic delete.
- Nếu có `@Version` custom converter hoặc `Persistable`, test cả new detection và version initial `null -> 0`.
- Trường hợp `@Version` không được nhận diện, một `save` có thể là upsert bình thường và test stale phải **thất bại**. Đó chính là mục tiêu kiểm chứng.
- Một test single-thread stale copy như trên dễ tái lập; cần thêm **stress/parallel test** để đánh giá contention và timeout chứ không chỉ correctness.

### 19.3. Kiểm thử hai request chạy đồng thời

Không tạo hai tasks rồi để mỗi task **đọc** state sau khi một task kia đã ghi; như vậy có thể không cùng version và test không tái hiện conflict. Hãy:

~~~text
1. Seed một DeviceSetting version=0.
2. Đọc hai object copyA và copyB TRƯỚC khi nhả barrier.
3. Barrier mở cho hai threads đồng thời gọi repository.save(copyX).
4. Đếm outcome: một applied; một optimistic conflict
   trong điều kiện không có timeout/sự cố node.
5. Đọc lại state, xác minh mode/version cuối khớp writer thắng.
6. Lặp nhiều lần trên keys riêng, đo p99 và CAS contention.
~~~

Trong test failure injection (replica down, packet loss, clock/GC, multi-DC), có thể xuất hiện **timeout/unknown**, nên assertion không được đồng nhất mọi lỗi với version conflict. Đừng dùng `Thread.sleep` để “hy vọng tạo race”; barrier/latches cho phép chủ động điều phối.

### 19.4. Bộ trường hợp biên

| Test | Kỳ vọng |
| --- | --- |
| Insert mới `@Version Long == null`. | Tạo bằng conditional insert, version ban đầu 0. |
| Insert trùng full PK. | Không ghi đè entity hiện có; báo duplicate/conflict theo Spring Data. |
| Hai snapshots version=0, lần lượt save. | Lần đầu version=1, lần sau lỗi optimistic locking. |
| Delete entity bằng bản stale. | Không xóa dữ liệu mới hơn khi dùng đường delete được version check hỗ trợ. |
| `deleteById(key)` custom hoặc raw CQL. | **Không giả định** version check; phải kiểm generated statement/contract. |
| Version null nhưng row tồn tại do migration. | Không âm thầm coi là entity mới rồi ghi đè; có migration/backfill version. |
| User HTTP `If-Match:"7"`, DB version=8. | Trả 412/409 trước CAS, không áp yêu cầu cũ. |
| CAS timeout rồi retry. | Reconcile state/operation ID, không báo chắc chắn failed/success khi chưa biết. |
| 100 writers vào cùng key. | Conflict/latency trong giới hạn, app không retry storm, backend không quá tải. |
| Hai DC cùng nhận writes. | Serial scope và data correctness đáp ứng hợp đồng, không suy local=global. |
| TTL/delete/recreate cùng key. | Generation/identity và retention đúng, không có ABA ngoài dự kiến. |
| Writer ngoài Spring Data bypass version. | Test phát hiện data drift và policy vi phạm. |

## 20. Reactive Spring Data: `@Version` vẫn cần xử lý conflict

Với ứng dụng Spring WebFlux và starter reactive tương thích, Spring Data Cassandra cung cấp đường repository/template phản ứng. `@Version` vẫn biểu diễn **optimistic locking của entity**, nhưng outcome xuất hiện **khi publisher được subscribe/executed**, không phải lúc bạn chỉ tạo một `Mono`.

~~~java
// ReactiveDeviceSettingRepository.java
package example.telemetry;

import org.springframework.data.cassandra.repository.ReactiveCassandraRepository;

public interface ReactiveDeviceSettingRepository
        extends ReactiveCassandraRepository<DeviceSetting, DeviceKey> {
}
~~~

Ví dụ service conceptual trong một reactive application:

~~~java
// Trích đoạn trong service reactive, không phải class độc lập.
Mono<DeviceSetting> result = reactiveRepository.findById(key)
    .switchIfEmpty(Mono.error(new DeviceSettingNotFoundException()))
    .flatMap(current -> {
        if (!Objects.equals(current.getVersion(), expectedVersion)) {
            return Mono.error(new StaleDeviceVersionException());
        }
        current.setMode(newMode);
        current.setUpdatedAt(Instant.now());
        return reactiveRepository.save(current);
    })
    .onErrorMap(OptimisticLockingFailureException.class,
        conflict -> new StaleDeviceVersionException(conflict));
~~~

`Mono`, `Objects`, `Instant` và các exception trong đoạn này đến từ Java/Reactor/ứng dụng; không copy nguyên snippet vào class thiếu imports/beans. **Không dùng**:

~~~java
// PHẢN MẪU: che mọi conflict và lỗi Cassandra bằng kết quả rỗng.
reactiveRepository.save(current)
    .onErrorResume(error -> Mono.empty());
~~~

Nếu biến `OptimisticLockingFailureException` thành `Mono.empty()`, HTTP layer có thể trả 200/404 sai. Dùng `onErrorMap` hoặc error handler rõ loại lỗi; không `block()` trên event-loop. Khi retry reactive, dùng retry filter cho **lỗi tạm thời thực sự**, không tự retry stale precondition vô hạn.

**Reactive không miễn phí Paxos:** số CQL conditions, round-trips, serial CL, replica contention và cost trên Cassandra giống nhau cho cùng query. Nó chỉ thay cách ứng dụng Java chờ I/O và xử lý pipeline.

## 21. Runbook khi conflict hoặc CAS timeout tăng bất thường

### 21.1. Khi `cas_conflict` tăng

1. Xác nhận **type of failure**: `OptimisticLockingFailureException` do stale state, `wasApplied=false`, hay timeout bị map nhầm thành conflict?
2. Kiểm tra **request rate theo query/workload**, số active users, client `If-Match` ages, retry attempts và thời gian người dùng giữ form.
3. Tìm có **batch job, scheduler hoặc admin tool** bypass `@Version` và cập nhật `mode` không.
4. Phân tích **hot keys** có sampling bảo vệ dữ liệu; tránh metric labels theo tenant/device ID có cardinality lớn.
5. Đánh giá người dùng cần **manual merge**, chỉ sửa một phần field hay có thể dùng operation semantics commutative.
6. Nếu một key quá nóng, cân nhắc single writer/queue/rate limit theo thiết kế thay vì retry nhanh liên tục.
7. Kiểm tra Cassandra CAS contention, coordinator/replica p99 và CPU/network; tránh nhầm conflict bình thường với node lỗi.

### 21.2. Khi `CAS timeout` tăng

1. Đo client request timeout, regular/serial CL, latency/queue/throttler và retry amplification.
2. Kiểm tra `nodetool status`, `tpstats`, `compactionstats`, `proxyhistograms` và metric CAS/Paxos theo version trên **từng DC/replica**.
3. Xem GC logs, network retransmits/RTT WAN và disk latency; kiểm tra repair/streaming/compaction gây áp lực.
4. Xác định có **nhiều writers cùng key** hoặc `SERIAL` trên đường WAN có vấn đề.
5. **Không hạ serial CL** hoặc đổi `LOCAL_QUORUM` âm thầm để giảm timeout; phải đánh giá correctness và đổi có phê duyệt.
6. Tránh retry storm; giữ **bounded in-flight, queue, retry budget và backoff**. Giảm tải batch/maintenance nếu đang quá giới hạn.
7. Với outcome unknown, dùng **version/state/lastOperationId reconciliation**; không tạo ID mới cho retry dẫn đến double side effect.
8. Sau khi phục hồi, chạy regression tests và hậu kiểm theo RPO/RTO/SLO và consistency yêu cầu.

### 21.3. Lệnh và dấu hiệu liên quan

~~~bash
# Trên node lab hoặc theo runbook vận hành production được phê duyệt.
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool proxyhistograms
nodetool gcstats
nodetool tablestats telemetry_locking.device_settings
~~~

Lệnh/metric cụ thể có thể thay đổi theo phiên bản Cassandra; `status` `UN` không chứng minh partition cụ thể không nghẽn. Dữ liệu tracing phải được lấy **có chọn lọc**, không bật toàn traffic lúc LWT contention cao vì tracing thêm overhead. Xem logs theo **UTC, node/DC, query name, change ID**, nhưng redact tenant/device IDs và payload theo chính sách.

## 22. Case study: hàng nóng và retry tự động biến 409 thành incident

### 22.1. Bối cảnh giả lập

Một hệ thống điều khiển trạng thái một gateway chung (`tenant-a/gateway-1`) cho 3.000 người dùng. Sau một chiến dịch, rất nhiều UI clients cùng đọc `version=11` rồi thử chuyển `mode`. Service cấu hình **retry ba lần không backoff khi gặp optimistic conflict**.

| Chỉ số giả lập | Trước cao điểm | Khi retry storm | Diễn giải |
| --- | ---: | ---: | --- |
| Unique user write requests/s | 20 | 800 | Tăng đầu vào. |
| CAS attempts/request trung bình | 1,0 | 2,7 | Retry khuếch đại lưu lượng. |
| CAS attempts/s (ước tính) | 20 | 2.160 | Tăng nhiều hơn user requests. |
| Conflict rate | 2% | 78% | Nhiều clients giữ version cũ của cùng key. |
| CAS p99 | 24 ms | 310 ms | Contention/queue/WAN có thể góp phần. |
| Outcome unknown/timeout | Thấp | Tăng | Khó phân biệt conflict với backend failure. |

**Các số liệu chỉ để học cách phân tích, không phải benchmark Cassandra.**

### 22.2. Vì sao retry version cũ là sai?

Nếu client vẫn giữ version=11 và server đã lên version=12, gửi `IF version=11` thêm ba lần **không làm điều kiện đúng trở lại**. Nếu service tự đọc version=12 rồi ghi cùng quyết định người dùng đã chọn khi thấy version=11, nó có thể **ghi đè quyết định mới** mà không được người dùng đồng ý.

### 22.3. Phương án cải thiện

1. Trả **412 Precondition Failed** với hướng dẫn refresh/review đối với update qua `If-Match`.
2. Chỉ auto-merge các thao tác **có semantics an toàn**, ví dụ cập nhật metadata độc lập thực sự; không auto-overwrite state máy.
3. Giới hạn **in-flight CAS theo key/tenant** và global fleet, có queue bounded/rate limit.
4. Với một gateway là tài nguyên chung cực nóng, cân nhắc command processor **single writer**, ghi ý định vào durable log rồi cập nhật state có version theo một đường được kiểm soát.
5. Dashboard tách `conflict` hợp lệ khỏi `timeout/unavailable`, tránh SLO lỗi hạ tầng bị nhiễu do hành vi người dùng.
6. Kiểm thử multi-DC serial consistency, node failure và rollback config trước khi mở lại traffic lớn.

**Kết quả mong đợi:** giảm sự khuếch đại tải và giữ đúng quyết định người dùng, không chỉ giảm số HTTP 409 bằng cách âm thầm bỏ qua precondition.

## 23. Khi nào dùng `@Version`, `IF` thủ công hoặc thiết kế khác?

| Nhu cầu | Phương án thường hợp lý | Tại sao |
| --- | --- | --- |
| CRUD một hàng config qua Spring Data | **`@Version Long`** + repository/template. | Hợp đồng entity rõ, code ít lặp, conflict exception có sẵn. |
| Conditional update chỉ một vài cột | **Prepared CQL `IF version=?`** qua Driver Core. | Kiểm soát projection/mutation/serial CL và `wasApplied`. |
| Tạo singleton resource một lần | **`INSERT ... IF NOT EXISTS`**. | Bảo vệ cùng primary key khỏi upsert trùng. |
| Ngăn update tạo hàng mới nhưng không quan tâm bản cũ | **`UPDATE ... IF EXISTS`** nếu thật sự chỉ cần tồn tại. | Không có version conflict detection. |
| Append-only event với UUID ổn định | **Unconditional idempotent upsert** khi hợp đồng cho phép. | Tránh Paxos cost không cần thiết. |
| Counter/metrics aggregate tăng liên tục | Mô hình counter/aggregation phù hợp, **không dùng @Version để emulate counter**. | Semantics retry và throughput khác. |
| Multi-table projections/audit | Durable command log/CDC/reconciliation. | CAS một hàng không atomic qua các bảng/hệ thống. |
| Global uniqueness | Uniqueness claim key/thiết kế chuyên biệt, test conflict. | `IF NOT EXISTS` trên key khác không bảo vệ giá trị toàn cục. |
| Hàng hot hàng nghìn writers | Single writer/queue/rate control hoặc thiết kế lại state. | LWT contention gây nhiều conflict và tail latency. |
| Active-active multi-DC cùng key | Đánh giá `SERIAL` global, topology và SLO có chủ đích. | `LOCAL_SERIAL` không mặc định là global ordering. |
| UI edit form kéo dài | HTTP `If-Match` + CAS + conflict UX. | Bảo vệ ý định người dùng khỏi stale update. |

### 23.1. Thứ tự quyết định

~~~mermaid
flowchart TD
    A["Có mutation trên Cassandra"] --> B{"Có cần phát hiện lost update/điều kiện không?"}
    B -->|Không| C["Unconditional write, idempotency và CL phù hợp"]
    B -->|Có| D{"Một hàng Spring Data entity?"}
    D -->|Có| E["@Version Long + repository/template"]
    D -->|Không / column-specific| F["Prepared CQL IF ... + wasApplied"]
    E --> G["Chốt regular CL + serial CL theo topology"]
    F --> G
    G --> H["Bảo vệ mọi writer, API If-Match và retry budget"]
    H --> I["Test concurrency, delete/TTL, timeout và multi-DC"]
    I --> J{"Correctness + p99 + contention đạt?"}
    J -->|Có| K["Canary rồi rollout có giám sát"]
    J -->|Không| L["Giảm contention/đổi mô hình hoặc chọn giải pháp khác"]
~~~

## 24. Nhận định đúng/sai thường gặp

| Nhận định | Đúng/sai | Giải thích |
| --- | --- | --- |
| “`@Version` của Spring Data Cassandra dùng LWT.” | **Đúng** | Conditional insert/update/delete trên single entity. |
| “`@Version` tương đương một lock giữ từ lúc GET đến PUT.” | **Sai** | CAS kiểm tra lúc mutation; không giữ lock qua HTTP round-trip. |
| “Mọi `repository.save` có `@Version` đều là upsert thường.” | **Sai** | Spring Data dùng conditional behavior cho entity versioned theo API hỗ trợ. |
| “Chỉ kiểm tra version trong Java rồi UPDATE không IF là đủ.” | **Sai** | Vẫn có race giữa read và write. |
| “`IF EXISTS` luôn ngăn lost update.” | **Sai** | Chỉ kiểm tra tồn tại, không so bản đã đọc. |
| “Khi `IF version=7` trả `applied=false`, mutation đó đã ghi mode mới.” | **Sai** | Điều kiện không thỏa; không áp mutation có điều kiện đó. |
| “Write timeout chứng minh chưa replica nào ghi.” | **Sai** | Outcome có thể chưa xác định; cần reconciliation. |
| “Retry cùng CAS sau timeout có thể trả false do lần trước đã áp dụng.” | **Đúng** | Version đã được chính lần đầu nâng. |
| “`LOCAL_QUORUM` tự kích hoạt Paxos.” | **Sai** | Phải có conditional CQL/`@Version` path; regular CL khác serial CL. |
| “`LOCAL_SERIAL` luôn cung cấp global linearizability xuyên DC.” | **Sai** | Phạm vi local DC, cần đánh giá multi-DC semantics. |
| “`saveAll` với `@Version` là transaction toàn bộ danh sách.” | **Sai** | Version locking được hỗ trợ ở single-entity operation, không batch. |
| “Cassandra tự tăng version bigint với mọi UPDATE.” | **Sai** | Writer phải dùng conditional/version protocol thống nhất. |
| “`updated_at` giống một `@Version` bảo đảm concurrency.” | **Sai** | Timestamp field không tự CAS; nếu muốn điều kiện phải phát `IF`. |
| “`@Version Long` có thể bắt đầu null và được khởi tạo 0 khi insert.” | **Đúng** | Theo example Spring Data; test theo version/mapper thật. |
| “Xóa rồi tạo lại cùng key không thể gây ABA.” | **Sai** | Version/generation có thể reset, cần lifecycle contract. |
| “CQL CAS miễn phí nếu không có conflict.” | **Sai** | Vẫn cần coordination/Paxos. |
| “Một test mock repository đủ chứng minh LWT được áp dụng.” | **Sai** | Cần integration test trên Cassandra thật. |
| “HTTP `If-Match` từ browser và CAS trong DB bảo vệ hai khoảng race khác nhau.” | **Đúng** | Một kiểm tra stale form, một kiểm tra tranh chấp lúc ghi. |

## 25. Bài tập tự kiểm tra có đáp án

**Bài 1.** Hai admin đọc `version=3`. A ghi `mode=MANUAL`, B ghi `mode=MAINTENANCE` bằng `UPDATE` thông thường. Có được bảo đảm một người thấy lỗi version conflict không?

**Đáp án:** **Không.** Unconditional writes được hòa giải theo semantics timestamp/cell Cassandra. Muốn phát hiện lost update, dùng `UPDATE ... IF version=3` hoặc Spring Data `@Version` khi mọi writer tuân thủ.

**Bài 2.** Vì sao chỉ `if (row.getVersion()==expected) repository.saveWithoutCondition(row)` không an toàn?

**Đáp án:** Có thể có writer khác ghi giữa thời điểm read và update (**TOCTOU race**). Kiểm tra version phải được gắn **cùng conditional mutation** và thực thi trong Cassandra qua LWT.

**Bài 3.** Spring Data Cassandra import `@Version` từ package nào khi làm optimistic locking?

**Đáp án:** **`org.springframework.data.annotation.Version`**. Không dùng `jakarta.persistence.Version` thay thế theo thói quen JPA. Mapping phải có cột CQL tương ứng, ví dụ `version bigint`.

**Bài 4.** Một entity mới có `@Version Long version=null`. Theo ví dụ Spring Data chính thức, insert đầu thành công đặt version nào?

**Đáp án:** **0**. Khi insert dùng `IF NOT EXISTS`, nếu full primary key đã tồn tại thì không áp dụng và framework báo optimistic conflict theo đường được hỗ trợ. Với cấu hình `Persistable`/custom mapping cần integration test.

**Bài 5.** Hàng `tenant-a/device-7` đang `version=7`. CQL `UPDATE SET mode='MANUAL',version=8 ... IF version=7` chạy hai lần. Kết quả?

**Đáp án:** Lần đầu có thể `[applied]=true` và version lên 8; lần sau **`[applied]=false`** do version không còn là 7. Không được tự kết luận lần sau thất bại là một writer khác đã cạnh tranh.

**Bài 6.** `IF EXISTS` có bảo vệ khỏi hai admin cùng ghi đè mode trong khi hàng vẫn tồn tại không?

**Đáp án:** **Không.** `IF EXISTS` kiểm tra tồn tại, không kiểm tra state mà người dùng đã đọc; cả hai cập nhật có thể áp dụng nối tiếp. Dùng `IF version=?` nếu invariant là không mất cập nhật.

**Bài 7.** Một conditional write dùng `LOCAL_QUORUM` regular CL và `LOCAL_SERIAL` serial CL. Hai thiết lập có cùng chức năng không?

**Đáp án:** **Không.** Serial CL điều khiển pha điều kiện/Paxos; regular CL điều khiển pha ghi/visibility phù hợp. Không coi `LOCAL_QUORUM` tự kích hoạt LWT.

**Bài 8.** Cluster có RF=3 tại `dc1`, một replica down. `LOCAL_QUORUM` cần mấy full replicas phản hồi, và có thể thành công không?

**Đáp án:** Cần **hai**. Nếu hai replica còn lại khả dụng và các điều kiện operation/serial CL được đáp ứng, request **có thể** hoàn tất; không mặc định chỉ cần quorum là mọi LWT trong mọi tình trạng luôn thành công.

**Bài 9.** Cùng một thiết bị được ghi từ `dc1` và `dc2`. Có thể mặc định dùng `LOCAL_SERIAL` ở cả hai để bảo đảm một thứ tự global duy nhất không?

**Đáp án:** **Không.** `LOCAL_SERIAL` giới hạn phạm vi serial ở local DC. Phải xem phạm vi write contention thực, semantics phiên bản và cân nhắc `SERIAL` toàn phạm vi khi cần thứ tự/linearizability global, với trade-off WAN.

**Bài 10.** API nhận `If-Match:"7"`, nhưng service đọc DB mới có version=8 rồi gọi save với object version=8. Vì sao không đúng nếu đây là một form edit?

**Đáp án:** Service đã bỏ qua **precondition từ client**; nó có thể ghi quyết định dựa trên form cũ lên state mới. So expectedVersion=7 với version DB=8 và trả 412/409, không tự thay bằng 8.

**Bài 11.** Sau `WriteTimeout` của CAS, retry cùng expectedVersion trả `applied=false`. Có thể kết luận lần đầu bị từ chối?

**Đáp án:** **Không.** Lần đầu có thể đã áp dụng, nâng version, nhưng mất response. Cần đọc/reconcile `version`, `mode`, `lastOperationId` nếu có, rồi quyết định theo idempotency contract.

**Bài 12.** `repository.saveAll` cập nhật A thành công rồi B conflict. Có rollback A tự động vì `@Version` không?

**Đáp án:** **Không.** Spring Data `@Version` hỗ trợ single-entity operations, không tạo atomic transaction nhiều hàng. Cần workflow reconciliation hoặc kiến trúc dữ liệu khác nếu cần cùng thành công/thất bại.

**Bài 13.** Nếu một batch job dùng `UPDATE mode='AUTO'` không điều kiện và không tăng version, có còn bảo đảm optimistic locking cho mọi writer không?

**Đáp án:** **Không.** Batch có thể thay `mode` mà giữ version cũ; lần CAS sau vẫn thấy version phù hợp và có thể ghi đè. Tất cả writers phải tuân thủ cùng hợp đồng version hoặc chạy trong migration window riêng có kiểm soát.

**Bài 14.** Vì sao không đặt TTL ngắn hơn vòng đời cấu hình cho cột `version`?

**Đáp án:** Version có thể hết hạn trong khi state vẫn sống, làm `IF version=?` không khớp hoặc phá logic lifecycle. Phải quản lý expiry/delete/generation cho **toàn trạng thái nghiệp vụ**, không tùy tiện expire version.

**Bài 15.** Xóa entity version=8 rồi tạo lại cùng primary key với version=0. Có rủi ro nào nếu client cũ đã giữ version=0 từ một đời dữ liệu trước?

**Đáp án:** Rủi ro **ABA/version reuse** trong các lifecycle phức tạp. Dùng generation/immutable incarnation ID, soft delete hoặc uniqueness policy nếu không được phép nhầm hai đời của cùng key.

**Bài 16.** Có nên dùng `@Version` và LWT cho từng event telemetry append-only khi producer đã có UUID bền vững không?

**Đáp án:** **Không nhất thiết.** Nếu upsert idempotent theo full primary key đáp ứng invariant, LWT chỉ thêm Paxos overhead. Dùng conditional mutation khi thật sự phải kiểm tra tồn tại/state.

**Bài 17.** 15 Java pods, mỗi pod có 80 requests CAS in-flight, chưa tính retries. Trần tổng lý thuyết là bao nhiêu?

**Đáp án:** `15 × 80 = 1.200` CAS requests đồng thời trong fleet. Đây không phải throughput 1.200 requests/giây hay số connections; nếu 80% cùng tranh một key, server có thể nghẽn mạnh dù có nhiều nodes.

**Bài 18.** JUnit test mock repository tự tăng version xanh. Đã chứng minh Cassandra thật phát `IF version` chưa?

**Đáp án:** **Chưa.** Cần integration test trên Cassandra có DDL đúng, đọc hai entity cùng version, save bản A, kiểm tra bản B nhận optimistic conflict; kiểm tra effective serial/regular CL và code path.

**Bài 19.** Khi service bắt mọi `RuntimeException` và trả HTTP 409, điều gì sai?

**Đáp án:** `Unauthorized`, `Unavailable`, timeout hoặc codec errors sẽ bị gắn nhãn xung đột sai. Chỉ ánh xạ **xung đột đã xác nhận** sang 409/412; các lỗi khác giữ semantics đúng và có observability.

**Bài 20.** Một API cập nhật `mode` của device đang bị 3.000 admin cùng sửa, CAS conflict rate tăng. Đầu tiên nên tăng retries hay giảm concurrency/thiết kế lại ownership?

**Đáp án:** **Không retry mù.** Phân tích contention, số writers cùng key, tuổi ETag và SLO. Có thể cần single writer/queue và UI conflict resolution; tăng retries cho stale version chỉ khuếch đại tải.

## 26. Checklist đưa optimistic locking vào production

~~~text
DATA MODEL / CQL
[ ] Bảng dùng full primary key đúng query, không cần ALLOW FILTERING.
[ ] Cột version bigint tồn tại; mọi mutation quan trọng tăng version.
[ ] Không dùng counter làm version; không tự đổi partition/clustering key.
[ ] Conditional insert/update/delete và [applied] được hiểu đúng.
[ ] TTL/delete/recreate có generation/lifecycle rõ, không phá version.
[ ] Audit/projections khác bảng có reconciliation/idempotency.

SPRING DATA / JAVA
[ ] Dùng org.springframework.data.annotation.Version, Long nullable phù hợp.
[ ] Entity mapping và new detection được integration test.
[ ] Repository/template chỉ thao tác một entity theo API optimistic lock hỗ trợ.
[ ] saveAll/batch không bị coi là transaction đa entity.
[ ] Không có writer raw CQL bypass/không tăng version.
[ ] Core Driver custom CAS đặt đúng WHERE và IF, đọc wasApplied().
[ ] Một CqlSession được Spring quản lý, không tạo session theo request.

CONSISTENCY / RELIABILITY
[ ] Regular CL và serial CL được duyệt theo RF/DC và kiểu workload.
[ ] Nhiều DC có quyết định rõ về LOCAL_SERIAL hay SERIAL.
[ ] Conflict confirmed khác timeout/outcome unknown và Unavailable.
[ ] Có idempotency/operation ID, reconciliation và retry budget.
[ ] Admission, in-flight và queue hữu hạn; hot key contention được đo.
[ ] Không hạ CL hoặc tăng timeout vô căn cứ để che lỗi.

HTTP / SECURITY
[ ] If-Match/ETag từ client được so với state mới đọc trước CAS.
[ ] 409/412/404/503 được ánh xạ đúng theo hợp đồng API.
[ ] User được authorization theo tenant/device, không chỉ CQL RBAC.
[ ] TLS peer verification, secret manager, role least privilege hoạt động.
[ ] Không log mật khẩu, raw payload hoặc key nhạy cảm vào metric labels.

TEST / OPERATIONS
[ ] Test insert version 0, stale update, conditional delete và duplicate.
[ ] Có test hai snapshots cùng version, one-winner conflict behavior.
[ ] Test LWT timeout, CAS false sau unknown retry và client disconnect.
[ ] Test multi-DC, replica failure, version TTL/delete/recreate.
[ ] Dashboard CAS p50/p95/p99, contention/conflicts, timeout, retries.
[ ] Canary/load test với traffic/data shape thật; có rollback plan.
~~~

~~~mermaid
flowchart TD
    A["Client muốn đổi trạng thái một hàng Cassandra"] --> B["Đọc state + version và cấp ETag"]
    B --> C["Client gửi update với If-Match cũ"]
    C --> D{"Version client còn giống state đã đọc lại?"}
    D -->|Không| E["412/409: conflict; yêu cầu quyết định lại"]
    D -->|Có| F["Spring Data @Version hoặc CQL IF version=?"]
    F --> G["LWT/Paxos theo serial CL, regular CL"]
    G --> H{"Outcome?"}
    H -->|Applied| I["Trả version mới; metric success"]
    H -->|Not applied| E
    H -->|Timeout / Unknown| J["Reconcile state/operation ID, bounded retry"]
    J --> K["Không suy write thất bại; giữ deadline"]
    I --> L["Metrics, canary, điều tra contention nếu tăng"]
    E --> L
    K --> L
~~~

## 27. Nguồn tham khảo và kết luận

Những nguyên tắc then chốt trong bài có thể được kiểm chứng bằng tài liệu chính thức:

1. [Spring Data Cassandra — Persisting Entities, Optimistic Locking](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): `@Version`, `IF NOT EXISTS`, `IF version`, `OptimisticLockingFailureException`, giới hạn single-entity.
2. [Spring Data Cassandra — Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): vai trò annotation `@Version` và entity mapping.
3. [Spring Data — Repository Entity State Detection](https://docs.spring.io/spring-data/cassandra/reference/repositories/core-concepts.html): version nullable/new detection, `Persistable`, ID.
4. [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `INSERT IF NOT EXISTS`, `UPDATE/DELETE IF`, TTL, timestamp, batch và chi phí Paxos.
5. [Apache Cassandra — cqlsh, Consistency và Serial Consistency](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): regular/serial CL và hành vi conditional updates.
6. [DataStax Java Driver 4.17 — Statement API](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/Statement.html): `setConsistencyLevel`, `setSerialConsistencyLevel`, timeout và statement options. Dùng đúng tài liệu của driver version thực khi nâng cấp.

**Kết luận:** optimistic locking bằng **Spring Data Cassandra `@Version`** không phải một mutex Java, một lock giữ qua HTTP hay một transaction nhiều bảng. Nó dựa trên **LWT/Paxos** để kiểm tra **phiên bản ngay trong mutation** rồi chấp nhận hoặc từ chối một cập nhật trên entity. `INSERT ... IF NOT EXISTS` bảo vệ tạo mới theo key; `UPDATE/DELETE ... IF version=?` bảo vệ state đã đọc; `[applied]` hoặc `OptimisticLockingFailureException` thể hiện conflict đã xác định. Muốn đúng trong production phải bảo vệ cả **HTTP If-Match, mọi writer, TTL/delete/generation, regular và serial CL, multi-DC, retry outcome unknown, rate/contention và test tích hợp**. Chọn LWT **khi cần invariant** thay vì bật cho mọi write, bởi correctness được cải thiện luôn phải đi cùng khả năng chịu tải và quan sát vận hành.




