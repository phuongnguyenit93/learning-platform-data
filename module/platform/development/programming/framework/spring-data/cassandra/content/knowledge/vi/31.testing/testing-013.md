# Phân biệt bằng chứng một node với kiểm thử nhất quán trên cụm nhiều node trong Spring Data Cassandra

Một bài kiểm thử **Spring Data Cassandra** chạy xanh trên một container Cassandra là tín hiệu tốt: entity được ánh xạ đúng, repository gọi được CQL, dữ liệu đọc lại theo partition key và xử lý ngoại lệ cơ bản hoạt động. Nhưng kết quả đó **chưa chứng minh** ứng dụng xử lý đúng khi dữ liệu nằm trên nhiều replica, một node ngừng hoạt động, coordinator thay đổi hoặc hai client cập nhật cùng lúc qua các node khác nhau.

Trong chương **Kiểm thử**, bài này hướng dẫn cách diễn giải phạm vi bằng chứng, tổ chức kiểm thử từ một node đến cụm nhiều node, xây dựng tình huống về replication, consistency level, LWT, paging và lỗi mạng, đồng thời báo cáo kết quả với giới hạn kết luận rõ ràng. Đây là phần thực hành gắn với thiết kế bảng theo truy vấn và mô hình dữ liệu phân tán của module `SPRING_DATA_CASSANDRA`.

## 1. Một bài kiểm thử thực sự chứng minh điều gì?

Kiểm thử chỉ hỗ trợ những kết luận tương ứng với **mô hình hệ thống, dữ liệu, lỗi và cách đo** đã được thực thi. Cần tách bốn tầng:

| Tầng kiểm thử | Môi trường | Có thể chứng minh | Chưa thể kết luận |
| --- | --- | --- | --- |
| **Unit test** | Mock repository, mapper hoặc service | Quy tắc nghiệp vụ, ranh giới thời gian, phân loại exception, nhánh retry | Cassandra có thực thi CQL/mapping/LWT đúng hay không |
| **Integration test một node** | Một Cassandra thực, thường qua Testcontainers; RF=1 | Cấu trúc bảng, key mapping, CQL, repository, `CassandraTemplate`, paging cơ bản, TTL và LWT trong một node | Replica phân tán, mất node, quorum nhiều replica, đồng thuận dưới lỗi mạng |
| **Integration test cụm nhiều node** | Nhiều node thực sự thuộc **cùng một cluster**, keyspace với RF phù hợp | Ứng dụng dưới nhiều coordinator/replica, tính khả dụng khi node lỗi, hành vi consistency, LWT cạnh tranh | Tự động chứng minh mọi phân vùng mạng, mọi thời điểm, mọi data center chưa thử |
| **Thử nghiệm chịu lỗi/vận hành** | Cụm với fault injection, quan sát trace/metric, tải và thời gian đủ lớn | Hành vi ứng dụng trong các lỗi được kiểm soát, tải cao, hồi phục/đối soát | Bảo đảm tuyệt đối ngoài phạm vi topology, cấu hình và lỗi đã mô phỏng |

**Ví dụ cách phát biểu đúng:**

> “`ResourceRepository.findById()` đọc đúng entity có composite partition key trên Cassandra một node, với schema và bản ghi kiểm thử đã tạo.”

Không nên biến kết quả đó thành “repository bảo đảm đọc nhất quán khi một replica mất kết nối”. Hai câu nói kiểm tra **hai đặc tính khác nhau**.

### 1.1. Nhận diện bằng chứng trực tiếp và suy luận

| Quan sát | Kết luận có cơ sở | Kết luận vượt quá bằng chứng |
| --- | --- | --- |
| `save()` rồi `findById()` trả cùng giá trị trên RF=1 | Mapping và đường đọc/ghi hoạt động trong ca thử | Giá trị luôn được đọc mới nhất từ mọi replica |
| LWT `IF version = 1` trả `[applied]=false` ở lần ghi thứ hai trên một node | Điều kiện CAS đã được đánh giá trong môi trường này | LWT vẫn hoạt động đúng khi coordinator hoặc replica gặp sự cố |
| Truy vấn `LOCAL_QUORUM` thành công khi cả ba node khỏe | Cụm đáp ứng truy vấn với cấu hình CL đã gửi | Cụm vẫn sẵn sàng nếu có hai replica mất kết nối |
| `LOCAL_QUORUM` thành công khi một node của nhóm replica dừng | Còn đủ replica cho quorum trong tình huống đã tạo | Mọi thao tác đều an toàn trước mọi lỗi mạng hoặc toàn DC bị mất |
| Hai LWT tranh chấp cùng key qua hai coordinator, chỉ một được áp dụng | Ghi có điều kiện loại trừ nhau trong ca đồng thời này | Mọi hiệu ứng ngoài Cassandra cũng được thực thi chính xác một lần |

## 2. Nền tảng cần hiểu trước khi thiết kế test cụm

### 2.1. Partition key, replication factor và consistency level

Partition key quyết định partition và tập replica lưu dữ liệu. **Replication factor (RF)** là số replica dự kiến trong một data center cho keyspace phù hợp; **consistency level (CL)** là số replica hoặc mức phản hồi cần thiết cho một thao tác. Nhiều node trong Docker **chưa đủ**: chúng phải gia nhập cùng cluster và keyspace thực sự có RF đúng.

Ví dụ một data center `dc1` với **3 node, RF=3**:

| CL trong một DC | Yêu cầu thông thường với RF=3 | Khi chỉ còn hai replica có thể trả lời |
| --- | --- | --- |
| `ONE` | 1 phản hồi replica | Có thể đáp ứng nếu truy cập được replica thích hợp |
| `LOCAL_QUORUM` | Đa số replica ở DC cục bộ: `floor(3/2)+1 = 2` | Có thể đáp ứng |
| `ALL` | Đủ 3 replica | Không đáp ứng được nếu một replica không thể trả lời |

Với **RF=1**, `QUORUM` về mặt số học chỉ yêu cầu **một** replica. Dùng `QUORUM` trong test một node không biến nó thành bài kiểm thử quorum phân tán. Ngược lại, thiết lập RF=3 khi chỉ có một node khả dụng thường khiến thao tác yêu cầu quorum/ALL không đủ replica; điều này cũng không phải bằng chứng rằng cơ chế nhiều node đã được kiểm thử.

Trong Cassandra, dữ liệu được hòa giải theo timestamp và trạng thái replica, có thể phát sinh khác biệt tạm thời. Với RF=3, đọc và ghi đều dùng quorum thường có giao nhau về replica, nhưng **không nên diễn giải một cách vô điều kiện** là mọi thao tác đọc đều tuyến tính hóa được trước mọi ghi đồng thời. Phải xét kiểu thao tác, timestamp, lỗi mạng, repair và điều kiện cạnh tranh. Nếu cần *compare-and-set* theo trạng thái hoặc phiên bản, phải sử dụng LWT/optimistic locking theo giao thức tương ứng.

### 2.2. Hai loại nhất quán cần tách riêng

- **Consistency của đọc/ghi thông thường** (`ONE`, `LOCAL_QUORUM`, `ALL`...): liên quan số replica cần phản hồi và sự đánh đổi giữa tính khả dụng, độ trễ và độ mới của dữ liệu.
- **Serial consistency của LWT** (`SERIAL`, `LOCAL_SERIAL`): liên quan giao thức đồng thuận cho thao tác điều kiện `IF`. Một LWT còn có consistency level thông thường cho pha ghi/đọc. Cần cấu hình và kiểm thử cả hai khi kết luận về LWT.

`@Version` của Spring Data Cassandra có thể triển khai optimistic locking qua mutation có điều kiện. Một test xung đột `@Version` trên một node hữu ích để kiểm tra phiên bản và exception, nhưng chưa đủ để đánh giá sự cố Paxos hoặc trường hợp nhiều coordinator. Việc dùng repository, `CassandraTemplate` hoặc CQL trực tiếp cũng cần được phân biệt vì mỗi đường ghi có thể có cấu hình CL hoặc giao thức kiểm soát version khác nhau.

## 3. Lớp bằng chứng một node: thiết kế và giới hạn

### 3.1. Các mục tiêu nên đặt cho Testcontainers một node

Tập trung vào các hợp đồng **có thể xác định tại một node**:

1. Mapping `@Table`, `@PrimaryKey`, `@PrimaryKeyClass`, `@Column`, kiểu `UUID`, `Instant`, collection, enum/converter.
2. Repository và `CassandraTemplate` thực sự đọc/ghi đúng khóa, không tạo partition hoặc truy vấn không mong muốn.
3. CQL hợp lệ với schema thực; kiểm tra `INSERT`, `UPDATE`, `DELETE`, truy vấn theo khóa và điều kiện `IF`.
4. Biên trang của `Slice`/`Pageable` hoặc paging state của driver, kiểm tra các hàng không bị trùng/thiếu trong **tập dữ liệu ổn định**.
5. TTL và timestamp: test hết hạn theo thời gian có giới hạn; không yêu cầu tombstone phải được compaction ngay.
6. Thao tác `@Version` hoặc LWT thất bại vì phiên bản cũ và được dịch thành lỗi nghiệp vụ phù hợp.

Không dùng `@DataCassandraTest` với repository giả lập làm bằng chứng rằng Cassandra thật đã chạy. Một test Spring slice hoặc `@SpringBootTest` chỉ chứng minh tương tác thực khi nó thật sự kết nối đến container Cassandra đang hoạt động.

### 3.2. Ví dụ integration test với một Cassandra thực

Ví dụ dưới dùng JUnit 5, Java Driver 4 và module Cassandra của Testcontainers. Package `CassandraContainer` có thể khác nhau giữa các major version Testcontainers; cần ghim dependency theo stack của dự án.

```java
@Testcontainers
class SingleNodeCassandraIT {
    @Container
    static final CassandraContainer<?> cassandra =
        new CassandraContainer<>(DockerImageName.parse("cassandra:4.1"));

    @Test
    void writesAndReadsByFullPartitionKey() {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(
                    cassandra.getHost(), cassandra.getMappedPort(9042)))
                .withLocalDatacenter("datacenter1")
                .build()) {

            session.execute("CREATE KEYSPACE IF NOT EXISTS evidence_one " +
                "WITH replication = {'class':'SimpleStrategy', " +
                "'replication_factor':1}");
            session.execute("CREATE TABLE IF NOT EXISTS " +
                "evidence_one.orders_by_id (" +
                "tenant_id uuid, order_id uuid, status text, " +
                "version bigint, PRIMARY KEY ((tenant_id, order_id)))");

            UUID tenantId = UUID.randomUUID();
            UUID orderId = UUID.randomUUID();
            session.execute(SimpleStatement.newInstance(
                "INSERT INTO evidence_one.orders_by_id " +
                "(tenant_id, order_id, status, version) " +
                "VALUES (?, ?, ?, ?)",
                tenantId, orderId, "PENDING", 1L));

            Row row = session.execute(SimpleStatement.newInstance(
                "SELECT status, version FROM evidence_one.orders_by_id " +
                "WHERE tenant_id = ? AND order_id = ?",
                tenantId, orderId)).one();

            assertNotNull(row);
            assertEquals("PENDING", row.getString("status"));
            assertEquals(1L, row.getLong("version"));
        }
    }
}
```

Với Spring Boot, nối `spring.cassandra.contact-points`, `spring.cassandra.local-datacenter` và keyspace/schema tương ứng qua `@DynamicPropertySource` (tên property phụ thuộc phiên bản Spring Boot). Sau đó dùng repository/service thật để kiểm tra mapping và hành vi `@Version`. Khi test chỉ dùng `CqlSession` trực tiếp như ví dụ, kết luận chỉ bao gồm driver và CQL, **chưa trực tiếp xác nhận** mapping repository.

Đây là bằng chứng: *câu CQL và round-trip dữ liệu hoạt động với keyspace RF=1 và một node*. Nó không mô phỏng mất replica, coordinator chuyển node, gossip, hinted handoff, read repair hoặc sự cố giữa các pha LWT trên nhiều replica.

### 3.3. Kiểm thử LWT tại một node vẫn có ích

Khởi tạo `status='PENDING', version=1`, chạy hai mutation điều kiện trên cùng key:

```sql
UPDATE evidence_one.orders_by_id
SET status = 'CONFIRMED', version = 2
WHERE tenant_id = ? AND order_id = ?
IF status = 'PENDING' AND version = 1;

-- Chạy lại đúng mutation ở trên: điều kiện version = 1 không còn đúng.
```

Kỳ vọng lần đầu `[applied]=true`, lần sau `[applied]=false`. Test này kiểm tra quy tắc CAS cơ bản; nó **không** kiểm tra hai lệnh đến từ hai coordinator khác nhau hoặc lỗi giữa quá trình đồng thuận. Nếu cần chứng minh lỗi domain được map đúng, hãy test lớp service nhận `[applied]=false` hay `OptimisticLockingFailureException` và trả `409 Conflict` (hoặc hợp đồng API khác), nhưng ghi rõ đây là kiểm thử dịch lỗi.

## 4. Dựng cụm nhiều node để kiểm thử consistency

### 4.1. Những điều kiện phải chứng minh trước khi chạy test

Một môi trường tối thiểu để thử quorum trong **một data center** gồm ba node Cassandra thuộc **cùng cluster**, với keyspace sử dụng `NetworkTopologyStrategy` và RF=3 ở `dc1`:

```sql
CREATE KEYSPACE consistency_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE consistency_lab.orders_by_id (
    tenant_id uuid,
    order_id uuid,
    status text,
    version bigint,
    command_id uuid,
    PRIMARY KEY ((tenant_id, order_id))
);
```

Tên `dc1` là ví dụ; phải kiểm tra tên data center thực tế và dùng đúng trong schema và cấu hình driver. Khi dựng bằng Docker Compose, Testcontainers hoặc cluster test độc lập, xác nhận:

1. **Ba process khác nhau, ba node thực** (không phải ba kết nối đến cùng một container).
2. Các node có chung cluster name, seed discovery đúng, snitch và data center được khai báo nhất quán.
3. `nodetool status` hiển thị ba node **UN (Up/Normal)** trước khi ghi và sau khi cluster ổn định; không lấy việc container đã báo `running` làm điều kiện readiness duy nhất.
4. `system_schema.keyspaces` xác nhận replication strategy và RF; kiểm tra lại sau tạo schema.
5. Driver đã nhận metadata topology của cluster và có thể nối nhiều coordinator; đặt `local-datacenter` đúng.
6. Cấu hình consistency, timeout và retry policy được lưu kèm kết quả test. Không dựa vào CL mặc định nếu đang kiểm tra đặc tính của một CL cụ thể.

Một cụm ba node cùng DC không đủ để kết luận về **mất cả data center** hoặc so sánh `SERIAL` với `LOCAL_SERIAL` trên nhiều data center. Những mục tiêu đó cần topology ít nhất hai DC với replication và routing phù hợp.

### 4.2. Cấu hình consistency tại chính câu lệnh được thử

Ví dụ Java Driver 4: yêu cầu LWT so sánh `status` và `version` trên một partition, đồng thời nêu cả regular CL và serial CL:

```java
SimpleStatement cas = SimpleStatement.builder(
        "UPDATE consistency_lab.orders_by_id " +
        "SET status = ?, version = ?, command_id = ? " +
        "WHERE tenant_id = ? AND order_id = ? " +
        "IF status = ? AND version = ?")
    .addPositionalValues(
        "CONFIRMED", 2L, commandId, tenantId, orderId,
        "PENDING", 1L)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
    .build();

Row result = session.execute(cas).one();
assertNotNull(result);
boolean applied = result.getBoolean("[applied]");
```

Trong bài test, giá trị `expectedVersion` nên được truyền từ phiên bản đã đọc, không hardcode như `1L`; đoạn trên dùng giá trị cố định chỉ để minh họa cú pháp. Các writer của cùng một invariant phải tuân thủ cùng giao thức CAS/version. Nếu một service còn dùng `UPDATE` không điều kiện, không thể kết luận invariant được bảo vệ chỉ vì test LWT của service khác đi qua.

Đối với read/write thông thường, đặt `setConsistencyLevel(...)` trên câu `SELECT`/`INSERT` tương ứng. Kiểm tra cả mã gửi câu lệnh, thông số request, kết quả driver và log/metric; một ứng dụng có thể có execution profile hoặc cấu hình repository khác với đoạn CQL chạy thủ công.

## 5. Ma trận thí nghiệm consistency cho RF=3, một DC

Mỗi kịch bản phải có **dữ liệu đầu vào, lỗi được tiêm, CL thực tế, kết quả mong đợi và giới hạn kết luận**. Giả sử ba replica A/B/C của partition được thử đều ở `dc1`:

| Kịch bản | Thiết lập và thao tác | Kết quả dự kiến | Kết luận hợp lệ |
| --- | --- | --- | --- |
| **A. Cụm khỏe** | A/B/C đều UN; ghi rồi đọc với `LOCAL_QUORUM` | Đọc/ghi thành công | CL được cấu hình hoạt động khi cụm khỏe |
| **B. Một replica dừng** | Dừng C, đợi phát hiện trạng thái; đọc/ghi qua A/B với `LOCAL_QUORUM` | Vẫn có thể thành công vì còn 2/3 replica | Quorum duy trì khả dụng trong lỗi một replica đã mô phỏng |
| **C. ALL mất một replica** | C dừng; thao tác `ALL` | Không thể nhận đủ ba phản hồi, có thể báo unavailable hoặc timeout | `ALL` đánh đổi khả dụng khi thiếu replica |
| **D. Hai replica dừng** | Chỉ còn A; thử `LOCAL_QUORUM` và `ONE` qua coordinator còn kết nối | `LOCAL_QUORUM` không đủ quorum; `ONE` có thể đáp ứng | Sự khác nhau về số replica yêu cầu |
| **E. Hai writer tranh chấp** | Hai client qua coordinator khác nhau cùng gửi CAS `IF version=1` trên cùng partition | Nếu cả hai nhận kết quả xác định, đúng một lần `[applied]=true` | CAS bảo vệ invariant trong kịch bản cạnh tranh đã chạy |
| **F. Timeout LWT** | Làm chậm/ngắt kết nối trong lúc gửi CAS | Có thể không xác định được lệnh đã áp dụng chưa | Cần đối soát, không suy ra rollback từ timeout |
| **G. Hồi phục node** | Khôi phục C, quan sát trạng thái/repair và kiểm tra dữ liệu | Kết quả phụ thuộc đường ghi và cơ chế đồng bộ; cần xác minh hội tụ | Cụm hội tụ trong điều kiện và khoảng quan sát thực tế |

Đừng viết assertion cứng “`ONE` chắc chắn đọc dữ liệu cũ” khi không kiểm soát replica được đọc. Đọc ở `ONE` **có thể** gặp dữ liệu cũ, nhưng nếu replica được chọn đã cập nhật thì đọc sẽ trả dữ liệu mới. Muốn kiểm tra trường hợp đọc stale, phải điều khiển đường mạng/replica nhận ghi và replica phục vụ đọc hoặc thu thập bằng chứng cụ thể về replica được chọn.

Tương tự, khi một thao tác `ALL` bị timeout hoặc unavailable, **không được coi đó là bằng chứng dữ liệu chưa được ghi trên bất kỳ replica nào**. Một số replica có thể đã nhận mutation trước khi client nhận lỗi.

### 5.1. Làm cho thử nghiệm lỗi node có thể tái lập

Đối với môi trường Docker có tên node rõ ràng, quy trình minh họa:

```text
1. Xác nhận A, B, C đang Up/Normal và keyspace RF=3.
2. Ghi dữ liệu ban đầu với LOCAL_QUORUM và kiểm tra version.
3. Ngắt C (ví dụ: dừng container cassandra-c trong môi trường lab).
4. Chờ driver/topology nhận biết C không còn khả dụng.
5. Gửi SELECT/UPDATE với LOCAL_QUORUM; ghi lại kết quả và latency.
6. Gửi SELECT/UPDATE với ALL; ghi lại loại lỗi, không giả định rollback.
7. Khởi động lại C, chờ cluster phục hồi; xác minh trạng thái và dữ liệu.
8. Dọn dữ liệu test có kiểm soát; không dùng kết quả từ lần chạy trước.
```

Khởi động/dừng node không giống **network partition** chỉ cô lập một chiều hoặc làm trễ các thông điệp giữa coordinator/replica. Muốn kiểm tra các lỗi đó, dùng công cụ fault injection có khả năng chặn/độ trễ mạng theo đường kết nối và ghi rõ cấu hình. Thử nghiệm lỗi hạ tầng cần chạy trong cluster test riêng, không phá hủy cluster dùng chung.

### 5.2. Tránh điều kiện chờ gây test chập chờn

`Thread.sleep(5000)` không đảm bảo Cassandra đã nhận metadata hoặc replica đã sẵn sàng. Dùng polling có deadline và điều kiện rõ ràng:

- Trước thử nghiệm: đợi số node UN đúng, schema đã lan truyền và CQL probe thành công.
- Sau khi tiêm lỗi: đợi driver coi node không khả dụng hoặc xác minh request tới nó thất bại theo kế hoạch.
- Sau khi phục hồi: đợi node trở về UN, đường đọc theo CL yêu cầu hoạt động; khi cần đối soát dùng cơ chế repair và quan sát theo đúng cấu hình.
- Ghi lại cả **thời gian đạt điều kiện** và lần chạy timeout; không xóa thất bại bằng retry vô hạn.

Mục tiêu là tái lập cùng một kiểu lỗi và đo được hành vi, không phải làm bài test “đôi lúc xanh” bằng cách tăng thời gian ngủ tùy ý.

## 6. Kiểm thử LWT và `@Version` qua nhiều coordinator

### 6.1. Tạo xung đột có kiểm soát

Với booking `PENDING, version=7`, hai client A/B cùng đọc trạng thái và chuẩn bị hai ý định loại trừ nhau:

```text
             cùng snapshot: status=PENDING, version=7
                /                              \
    Client A / coordinator A        Client B / coordinator B
       Confirm (IF 7)                  Cancel (IF 7)
                \                              /
              Một mutation được áp dụng thành công
              Mutation còn lại không đạt điều kiện
```

Kịch bản thực hiện:

1. Tạo một bản ghi riêng cho từng test với `status='PENDING'`, `version=7`.
2. Cho hai client **đọc xong cùng snapshot** trước khi mở cổng đồng bộ (ví dụ `CountDownLatch`), tránh dùng `sleep` để giả định đồng thời.
3. Điều khiển/ràng buộc việc định tuyến nếu yêu cầu **hai coordinator khác nhau**; kiểm chứng bằng trace/driver log/topology. Chỉ mở hai `CqlSession` không tự chứng minh coordinator khác nhau.
4. Gửi hai câu `UPDATE ... IF status='PENDING' AND version=7` với kết quả mới `CONFIRMED` hoặc `CANCELLED`, tăng version thành 8.
5. Khi cả hai trả lời xác định, kiểm tra chính xác **một `[applied]=true`**, một `[applied]=false`; đọc trạng thái cuối và xác nhận chỉ có một chuyển trạng thái hợp lệ.
6. Nếu có timeout, chuyển sang nhánh **unknown outcome**; không gán timeout thành `[applied]=false`.

Với đường Spring Data Cassandra dùng `@Version`, cùng ý tưởng nhưng mỗi client giữ một bản entity có version cũ, gọi `repository.save()` và kiểm tra một thao tác được chấp nhận, thao tác kia báo optimistic-lock conflict. Để chứng minh điều kiện nhiều node, phải chạy qua cluster thật và xác minh đường đi của hai lời gọi; test repository trên một node chỉ kiểm tra behavior cục bộ của optimistic locking.

### 6.2. Timeout, retry và idempotency

Khi một LWT timeout sau khi gửi, có thể xảy ra ba tình huống: chưa được xử lý, đang được xử lý hoặc đã được áp dụng nhưng mất phản hồi. Không được retry bằng cách bỏ `IF` hoặc tự thay version cho đến khi “thành công”; việc đó có thể phá trạng thái nghiệp vụ.

Thiết kế test cần thêm `command_id` ổn định khi nghiệp vụ có khả năng gửi lặp, đọc lại nguồn theo khóa và kiểm tra **lệnh nào** đã thực sự thắng. Một cột `command_id` cuối cùng không phải sổ cái idempotency vĩnh viễn nếu các lệnh sau có thể ghi đè; những hệ thống cần đối soát lâu dài cần lưu lịch sử lệnh với retention được xác định.

Trong bài test, xác nhận ba điều:

- Không có hai command khác nhau cùng được coi là đã thắng một chuyển trạng thái loại trừ nhau.
- Retry của cùng command không tạo tác động nghiệp vụ mới nếu hợp đồng quy định thao tác idempotent.
- Khi chưa thể xác định kết quả, API trả trạng thái tạm thời hoặc có quy trình đối soát; không báo “đã thất bại chắc chắn” chỉ vì driver timeout.

LWT chỉ đảm bảo phần thay đổi có điều kiện trong Cassandra theo phạm vi hỗ trợ. Nó không làm cho gửi email, thanh toán, publish message hoặc cập nhật nhiều bảng trở thành giao dịch nguyên tử. Nếu test có side effect, cần thêm outbox, deduplication hoặc đối soát và kiểm tra riêng.

## 7. Đọc nhất quán, dữ liệu stale, paging và bảng theo truy vấn

### 7.1. Đừng dùng một lần `SELECT` để kết luận hội tụ

Giả sử ghi ở `ONE` được replica A nhận, trong khi B/C chưa cập nhật do lỗi mạng. Một lần đọc ở `ONE` có thể đi tới A và trả dữ liệu mới; lần khác có thể đi tới B và trả dữ liệu cũ. **Một lần đọc thành công không chứng minh tất cả replica đã đồng bộ.**

Để thí nghiệm có ý nghĩa, lưu: key/partition được thử, CL của mỗi read/write, coordinator, trạng thái replica, timestamp dữ liệu (nếu thích hợp), lỗi/timeout và phạm vi đồng bộ. Cần quan sát đủ nhiều lần, hoặc dùng fault injection có kiểm soát đường đọc; không biến kết quả ngẫu nhiên thành bảo đảm thiết kế.

Quá trình hội tụ phụ thuộc cơ chế đồng bộ, hinted handoff, read repair/anti-entropy repair và thời gian node lỗi. Test kiểm tra “hội tụ sau 10 giây” chỉ có nghĩa dưới đúng workload và cấu hình đó; không thể biến một số giây cố định thành SLA chung cho Cassandra nếu không có cơ sở vận hành.

### 7.2. Bảng phục vụ truy vấn không có giao dịch chung

Một ứng dụng có thể có `orders_by_id` (nguồn trạng thái) và `orders_by_customer` (phục vụ danh sách). Cập nhật hai bảng, kể cả với `LOCAL_QUORUM`, không mặc nhiên tạo **giao dịch phân tán nguyên tử** giữa các partition hoặc bảng. Khi một thao tác trên bảng nguồn thành công nhưng cập nhật bảng đọc lỗi, giao diện danh sách có thể hiển thị dữ liệu trễ.

Tách hai bộ test:

| Mục tiêu | Bằng chứng cần |
| --- | --- |
| Đường đọc theo khóa trong bảng nguồn | Read/write với full partition key, CL được ghi nhận |
| Đồng bộ bảng danh sách | Tạo lỗi giữa hai mutation, kiểm tra retry/đối soát và ranh giới trễ cho phép |
| Hành động quan trọng dựa trên trạng thái mới nhất | Service xác minh trạng thái nguồn trước khi thực hiện tác động |
| Paging một danh sách | Dữ liệu ổn định khi kiểm tra số hàng; test riêng khi dữ liệu thay đổi giữa các trang |

### 7.3. Paging không phải snapshot phân tán

Paging state của driver và phân trang Spring Data giúp lấy kết quả theo từng phần, **không phải snapshot bất biến** xuyên suốt nhiều lần đọc. Khi có mutation giữa trang 1 và trang 2, kết quả có thể khác giả định của test dữ liệu tĩnh. Kiểm thử ít nhất hai kiểu:

1. **Dữ liệu cố định:** đủ nhiều hàng trong các partition phù hợp, kiểm tra thứ tự theo clustering key, kích thước trang và không trùng/mất hàng theo hợp đồng.
2. **Dữ liệu đổi giữa các trang:** thêm/xóa/cập nhật hàng trong khi phân trang; xác định UI/API chấp nhận thay đổi nào, có continuation token hay cần mô hình snapshot riêng.

Không đánh giá consistency của nhiều replica chỉ bằng cách một lần duyệt đủ trang trên Testcontainers một node. Các bảng thiết kế theo truy vấn, partition lớn, tombstone và tải đồng thời cũng cần thử nghiệm hiệu năng độc lập phù hợp với cấu hình cluster thật.

## 8. Xây dựng test suite theo mục tiêu bằng chứng

Một tổ chức phù hợp là chạy nhanh bài đơn node ở mỗi thay đổi, và chạy cluster/fault test trong pipeline hoặc môi trường chuyên biệt với thời gian và tài nguyên đủ dùng:

| Nhóm bài test | Tần suất gợi ý | Điều kiện PASS chính |
| --- | --- | --- |
| Unit test domain/error mapping | Mỗi commit | Quy tắc, mã lỗi, retry/idempotency theo hợp đồng |
| Cassandra one-node integration | Mỗi PR nếu hạ tầng cho phép | CQL/schema/mapping/repository/query/paging/TTL/LWT cơ bản |
| Multi-node RF=3 consistency | PR thay đổi đường ghi/CL hoặc nightly | Kịch bản quorum, coordinator, tranh chấp version và lỗi replica như đã định nghĩa |
| Fault injection có network delay/partition | Theo lịch, trước thay đổi vận hành quan trọng | Outcome unknown, hồi phục, đối soát, khả năng phục vụ dưới lỗi được kiểm soát |
| Multi-DC test | Khi ứng dụng chạy nhiều DC | Routing, RF theo DC, CL/serial CL và chiến lược failover xuyên DC |

Các tên test nên nêu **bằng chứng được thực thi**. Ví dụ `saveAndReadWithRfOne`, `localQuorumWithOneReplicaDown`, `concurrentCasAcrossTwoCoordinators`, `unknownOutcomeAfterCoordinatorTimeout` phản ánh phạm vi rõ hơn `cassandraConsistencyIsCorrect`.

Không yêu cầu mọi lỗi mạng xuất hiện ngẫu nhiên trong CI. Dùng dữ liệu và fault có thể điều khiển, ID duy nhất cho từng ca, cleanup sau test, deadline cố định và lưu log có cấu trúc. Tránh `TRUNCATE` bảng được dùng chung khi nhiều suite chạy song song; ưu tiên keyspace/test ID riêng để tránh nhiễu chéo.

## 9. Bảng thu thập bằng chứng sau mỗi lần chạy

Một báo cáo kiểm thử nhất quán cần đủ thông tin để người khác **tái hiện và phản biện kết luận**:

| Trường | Ví dụ giá trị cần ghi |
| --- | --- |
| Build/phiên bản | Git revision, Spring Boot/Spring Data Cassandra, Cassandra, Java Driver |
| Topology | 3 node, cùng cluster, `dc1`; số node UN trước/sau test |
| Replication | `NetworkTopologyStrategy`, `dc1: 3` |
| Partition và dữ liệu | Tenant/order ID riêng cho test; version ban đầu, trạng thái cuối |
| Request | CQL hoặc method repository, regular CL, serial CL, coordinator nếu xác minh được |
| Fault | Node C dừng tại bước nào, độ trễ/chặn kết nối, thời gian lỗi kéo dài |
| Kết quả | Thành công, `[applied]`, exception, timeout, số lần retry |
| Quan sát | p95/p99 latency nếu đo tải, driver node state, log Cassandra, trace/metrics |
| Phục hồi | Node trở lại UN, truy vấn sau hồi phục, repair/đối soát nếu có |
| Phạm vi kết luận | Một DC RF=3, một kiểu fault, một mức tải, chưa bao phủ đa DC |

Ví dụ cách ghi kết luận có giới hạn:

> “Trong cụm ba node cùng `dc1`, keyspace RF=3, thao tác `LOCAL_QUORUM` vẫn hoàn tất khi một replica được dừng trước khi gửi request; thao tác `ALL` không lấy đủ phản hồi. Test chưa mô phỏng network partition bất đối xứng hoặc lỗi đồng thời hai replica.”

Đây là kết luận hữu ích, có thể tái lập và phù hợp với kiến trúc. Không gọi tên một SLA độ trễ hoặc mức chịu lỗi rộng hơn nếu chưa đo.

## 10. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Testcontainers một node chạy xanh nên consistency đã đúng” | Một node không có replica độc lập để thử quorum và mất node | Đặt nhãn one-node integration, thêm cluster RF=3 |
| “Tạo ba Cassandra container là cụm ba node” | Container có thể thuộc ba cluster riêng | Kiểm tra cluster membership, data center, UN và replication |
| “CL `QUORUM` trên RF=1 xác nhận strong consistency nhiều replica” | Quorum RF=1 chỉ cần một replica | Thử đúng RF và topology sản xuất |
| “Đọc `ONE` bắt buộc thấy stale sau một lần ghi” | Kết quả tùy replica được đọc và trạng thái đồng bộ | Tiêm lỗi/kiểm soát routing và quan sát replica |
| “`ALL` timeout tức ghi chưa xảy ra” | Một số replica có thể đã nhận mutation | Đối soát lệnh, xử lý unknown outcome |
| “Hai CqlSession bảo đảm hai coordinator khác nhau” | Driver tự chọn coordinator theo load balancing | Xác minh route bằng tracing/metric hoặc cấu hình lab |
| “Một test CAS trên một node đã chứng minh Paxos chịu lỗi” | Chưa có node/đường mạng thất bại | Thêm contention và fault trên nhiều replica |
| “`@Version` bảo vệ cả lệnh CQL thủ công” | Ghi không điều kiện có thể bỏ qua kiểm tra version | Thống nhất giao thức cho mọi writer |
| “Paging là ảnh chụp dữ liệu cố định” | Dữ liệu có thể đổi giữa các lần fetch | Kiểm thử riêng trạng thái dữ liệu tĩnh và động |
| “`Thread.sleep` đủ lâu là cluster đã sẵn sàng” | Thời gian khởi động và schema agreement thay đổi | Poll readiness có deadline và kiểm chứng schema |

## 11. Bài tập áp dụng

**Bối cảnh:** dịch vụ dùng Spring Data Cassandra lưu yêu cầu đặt chỗ theo `(tenant_id, booking_id)`. Hai endpoint `confirm` và `cancel` chỉ được thực hiện khi `status='PENDING'`. Để giảm xung đột, service sử dụng LWT `IF status='PENDING' AND version=?`; bảng danh sách được cập nhật sau khi lệnh nguồn thành công.

Thiết kế ba mức bằng chứng:

1. **Một node:** chứng minh mapping khóa ghép, một lần `confirm` thành công, lần `cancel` với version cũ bị từ chối; service phân loại thành `409` theo quy tắc domain.
2. **Ba node, RF=3:** hai client đọc cùng version và gửi lệnh tới hai coordinator khác nhau; xác nhận một CAS thành công, một CAS không được áp dụng. Dừng một replica và đo `LOCAL_QUORUM`/`ALL` theo ma trận.
3. **Sự cố giữa các bước:** gây timeout LWT hoặc lỗi ghi bảng danh sách; xác nhận API không báo thành công giả, không tạo side effect lặp và có đường đối soát/truy vấn nguồn để hoàn tất.

Với mỗi mức, viết câu kết luận **chỉ nói về những thuộc tính đã thực sự được quan sát**. Nếu mức thứ ba không kiểm soát được lỗi network theo cách tái lập, ghi rõ giới hạn và lên lịch test chuyên biệt thay vì coi một lần chạy xanh là bằng chứng hoàn chỉnh.

## 12. Checklist trước khi chấp nhận kết quả kiểm thử

- Mục tiêu kiểm thử nêu rõ đang kiểm tra mapping, business rule, consistency, LWT, availability hay recovery.
- Số node, cluster membership, topology DC, RF và trạng thái UN được kiểm chứng thực tế.
- Regular CL và serial CL của từng truy vấn quan trọng được xác định, không chỉ suy từ cấu hình mặc định.
- Bài test xung đột có cùng snapshot/version, điều khiển bắt đầu và xác minh coordinator khi kết luận về multi-node.
- Có ca success, conflict, unavailable/timeout và outcome chưa xác định; lỗi hạ tầng không bị map nhầm thành conflict.
- Mọi retry của mutation nhạy cảm được ràng buộc bằng idempotency và trạng thái nghiệp vụ.
- Đường đọc theo partition key, bảng danh sách, paging và cập nhật nhiều bảng được kiểm tra theo hợp đồng riêng.
- Readiness và recovery dùng điều kiện đo được với deadline; lưu đủ log/metric để tái lập.
- Báo cáo nêu rõ cấu hình cụm, kịch bản lỗi, điều đã quan sát và điều **chưa** kiểm chứng.

**Kết luận:** kiểm thử một node của Spring Data Cassandra là nền tảng cần thiết để chứng minh CQL, mapping, repository, `CassandraTemplate` và xử lý lỗi cục bộ. Muốn tuyên bố ứng dụng hoạt động đúng dưới replication, quorum, nhiều coordinator hoặc sự cố phân tán, phải thực thi các trường hợp đó trên **cụm nhiều node có RF, CL và fault được kiểm soát**. Giá trị của bài test nằm ở mức độ khớp giữa lời khẳng định và bằng chứng đã đo được.
