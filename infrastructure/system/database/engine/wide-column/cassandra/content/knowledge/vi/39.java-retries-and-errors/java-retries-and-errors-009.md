# Retry cùng nút hoặc nút khác và ảnh hưởng locality trong Cassandra Java

## 1. Mục tiêu và bối cảnh

Khi ứng dụng Java gửi một câu lệnh CQL đến Apache Cassandra, **nút nhận yêu cầu (coordinator)** chịu trách nhiệm liên hệ các replica, tổng hợp phản hồi và trả kết quả. Nếu một lần thực thi thất bại hoặc quá thời gian, Java Driver có thể quyết định **retry tại chính coordinator đó** hoặc **chuyển sang một coordinator khác**, tùy loại lỗi, chính sách retry và tính an toàn của câu lệnh.

Hai cách retry không tương đương: chúng tạo ra đường đi mạng và tải hệ thống khác nhau. Đặc biệt, trong Cassandra phân tán trên nhiều datacenter (DC), lựa chọn coordinator liên quan trực tiếp đến **locality**: đặt request gần replica/ứng dụng, hạn chế đường truyền xuyên DC và hiểu đúng phạm vi nhất quán của `LOCAL_ONE` hoặc `LOCAL_QUORUM`.

Sau bài này, người học có thể:

- Phân biệt **retry cùng nút**, **retry nút khác**, **retry ở tầng ứng dụng** và **speculative execution**.
- Giải thích vai trò của *coordinator*, *replica*, khóa phân vùng, routing key, load balancing và local DC.
- Đánh giá retry ảnh hưởng thế nào đến độ trễ, chi phí mạng, tính sẵn sàng và nhất quán đọc/ghi.
- Chọn trường hợp nên retry, trường hợp cần trả lỗi hoặc đối soát kết quả ghi chưa xác định.
- Cấu hình và sử dụng Java Driver 4.x theo hướng ưu tiên locality, đánh dấu idempotence đúng và theo dõi retry trong vận hành.

## 2. Coordinator không đồng nghĩa với replica

Xét keyspace sử dụng `NetworkTopologyStrategy`, có hai datacenter `dc1`, `dc2`, mỗi DC có replication factor (RF) bằng 3. Một bản ghi được xác định vị trí bằng token của **partition key**. Các replica của phân vùng do token ring và chiến lược replication quyết định; **đổi coordinator không làm đổi replica sở hữu dữ liệu**.

Đường đi của một request thông thường:

1. Ứng dụng Java gửi CQL qua kết nối tới một node được Java Driver chọn làm coordinator.
2. Coordinator xác định các replica phù hợp với partition key và replication topology.
3. Coordinator trao đổi với replica để đáp ứng consistency level (CL), rồi trả kết quả hoặc thông báo lỗi.
4. Nếu có lỗi thuộc diện được xem xét retry, driver áp dụng retry policy và có thể thử lại trên node hiện tại hoặc node kế tiếp.

~~~mermaid
flowchart TD
    A["Ứng dụng Java"] --> B["Driver: chọn coordinator theo local DC và routing key"]
    B --> C["Coordinator A - dc1"]
    C --> D["Replica của partition"]
    D --> E{"Đủ phản hồi theo CL?"}
    E -->|Có| F["Trả kết quả"]
    E -->|Không / lỗi| G{"Retry policy + idempotence + ngân sách thời gian"}
    G -->|Retry same| C
    G -->|Retry next| H["Coordinator B - thường vẫn trong dc1"]
    H --> D
    G -->|Rethrow| I["Trả lỗi cho ứng dụng"]
~~~

**Hai khái niệm locality cần tách biệt:**

- **Coordinator locality**: ứng dụng kết nối tới coordinator trong DC gần nó, thường là local DC mà driver đã cấu hình.
- **Replica locality**: coordinator ưu tiên liên hệ replica có thể đáp ứng CL với chi phí mạng thấp, ví dụ replica cùng DC. Token-aware routing giúp driver chọn coordinator gần tập replica của partition, khi driver xác định được routing key.

Với truy vấn thiếu partition key, truy vấn không cho driver suy ra routing key, hoặc cấu hình routing không phù hợp, coordinator được chọn có thể không phải là replica của phân vùng. Retry sang node khác không sửa được thiết kế truy vấn thiếu khóa phân vùng.

## 3. Retry cùng nút, nút khác và speculative execution

| Cách xử lý | Điều xảy ra | Lợi ích có thể có | Chi phí hoặc rủi ro |
| --- | --- | --- | --- |
| **Retry cùng coordinator** (*same node*) | Gửi lại cùng CQL tới coordinator đã trả lỗi | Có thể vượt qua lỗi ngắn hạn; giữ đường kết nối và DC hiện tại | Nếu coordinator quá tải hoặc đang mất kết nối tới replica, request mới có thể tiếp tục thất bại và làm tăng tải |
| **Retry coordinator kế tiếp** (*next node*) | Driver lấy node khác từ kế hoạch truy vấn của load-balancing policy | Tránh node lỗi, nghẽn hoặc mất kết nối; có thể đổi đường tới replica | Tốn thêm một lần điều phối và mạng; nút mới chưa chắc đáp ứng được CL |
| **Retry từ ứng dụng** | Service chủ động gửi một request logic mới sau lỗi | Có thể thêm backoff, jitter, giới hạn theo nghiệp vụ và đối soát trạng thái | Có thể nhân số lần thử nếu driver cũng đã retry; request ghi cũ có thể đã thành công |
| **Speculative execution** | Gửi thêm execution song song trước khi execution đầu tiên hoàn tất | Có thể giảm tail latency khi một coordinator chậm | Tăng số request đồng thời và lưu lượng tới replica; phải chỉ dùng cho thao tác idempotent |

**Retry tuần tự khác speculative execution.** Retry xảy ra sau một kết quả lỗi hoặc điều kiện mà driver nhận diện được; speculative execution phát thêm một execution khi execution đầu vẫn có thể đang chạy. Cả hai đều có thể tạo nhiều lần thực thi CQL và đều phải cân nhắc idempotence.

“Retry nút khác” nghĩa là **coordinator khác**, không có nghĩa dữ liệu sẽ được đọc từ một bộ replica hoàn toàn khác. Coordinator mới vẫn sử dụng topology của partition. Nó có thể chọn replica hoặc thời điểm gửi khác, nhưng lỗi thiếu replica để đạt CL vẫn có thể giữ nguyên.

## 4. Locality ảnh hưởng đến kết quả như thế nào?

### 4.1. Retry trong cùng datacenter

Giả sử ứng dụng đặt tại `dc1`, local DC của driver cũng là `dc1`, keyspace có RF = 3 tại DC này và câu lệnh chạy với `LOCAL_QUORUM`. Muốn thành công, request cần đủ **2 trong 3 replica thuộc `dc1`** (đọc còn phải có phản hồi dữ liệu thích hợp). Coordinator A chậm nên driver thử coordinator B, cũng ở `dc1`:

- Nếu lỗi ở **coordinator A** hoặc đường kết nối từ A, B có thể xử lý thành công.
- Nếu chỉ một replica không sẵn sàng, hai replica còn lại vẫn có thể đáp ứng `LOCAL_QUORUM`; retry thường không cần thiết nếu lần đầu chưa bị timeout.
- Nếu hai trong ba replica của DC bị mất và `LOCAL_QUORUM` không thể đạt được, chuyển A sang B **không tự khôi phục quorum**. Cần phục hồi replica hoặc xử lý sự cố thay vì lặp retry vô hạn.

Chuyển coordinator có thể thay đổi connection pool, độ trễ giữa coordinator và replica hoặc mức tải tại từng node. Nó **không thay đổi partition key, token, RF hay consistency level** của câu lệnh.

### 4.2. Retry xuyên datacenter

Trong mô hình nhiều DC, chính sách load balancing của Java Driver 4.x thông thường ưu tiên những node thuộc **local DC đã cấu hình**. “Retry next node” tự thân **không có nghĩa driver tự động failover sang DC từ xa**. Chỉ khi topology/chính sách routing hoặc cơ chế failover được thiết kế cho phép coordinator ở DC khác, mới cần xét tình huống xuyên DC:

- Thêm round trip qua WAN có thể tăng đáng kể latency, độ biến thiên độ trễ và chi phí băng thông.
- Coordinator ở DC khác có thể điều phối replica khác; dữ liệu tại các DC có thể chưa đồng bộ hoàn toàn tại một thời điểm.
- Với `LOCAL_QUORUM`, chữ “LOCAL” được tính **theo DC của coordinator đang thực thi**, không cố định theo vị trí vật lý của ứng dụng. Nếu coordinator đã chuyển từ `dc1` sang `dc2`, quorum cục bộ lúc này thuộc `dc2`. Điều đó có ý nghĩa đặc biệt đối với mức độ mới của dữ liệu và kỳ vọng đọc sau ghi.
- Việc đổi `LOCAL_QUORUM` thành `QUORUM` hoặc giảm xuống `ONE` để “cứu retry” là **thay đổi yêu cầu nhất quán**, phải do thiết kế nghiệp vụ quyết định; không được coi là thao tác tự động mặc định.

Nếu một DC ngừng hoạt động, chiến lược DR/failover cần xác định rõ DC đích, consistency level, cách dẫn lưu lượng và điều kiện chuyển về. Một retry policy đơn lẻ không thể thay thế thiết kế failover.

### 4.3. Partition key và token-aware routing

Ví dụ bảng truy vấn sự kiện theo tenant và ngày:

~~~sql
CREATE KEYSPACE app_events
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 3
};

CREATE TABLE app_events.events_by_day (
  tenant_id uuid,
  event_day date,
  event_id uuid,
  payload text,
  PRIMARY KEY ((tenant_id, event_day), event_id)
);

SELECT payload
FROM app_events.events_by_day
WHERE tenant_id = ?
  AND event_day = ?;
~~~

Ở đây, `(tenant_id, event_day)` là **partition key ghép**. Khi dùng prepared statement với đủ giá trị hai thành phần khóa, driver có cơ sở tính routing key để chọn coordinator phù hợp với replicas trong local DC. Nếu ứng dụng đổi `event_id` mỗi lần retry một lệnh `INSERT`, đó là **nhiều bản ghi khác nhau**, dù client tưởng đang gửi lại cùng một sự kiện.

## 5. Loại lỗi quyết định retry có ý nghĩa hay không

Không có quy tắc “gặp timeout thì thử node khác”. Phải xác định lỗi phát sinh ở client, coordinator hay replica; đồng thời xem xét CL và khả năng câu lệnh đã được áp dụng.

| Tín hiệu hoặc lỗi | Điều có thể đã xảy ra | Cách đánh giá |
| --- | --- | --- |
| **Read timeout** | Coordinator không nhận đủ phản hồi đọc đúng hạn, hoặc chưa nhận được phản hồi dữ liệu cần thiết | Với đọc thuần túy, retry có thể hợp lý nếu policy cho phép và còn ngân sách thời gian. Đổi coordinator không sửa được replica thiếu quorum |
| **Write timeout** | Một số replica có thể đã nhận và áp dụng mutation, nhưng coordinator chưa đạt số xác nhận cần thiết | **Trạng thái ghi có thể chưa xác định**. Chỉ retry khi thao tác thực sự idempotent; nếu không, đối soát theo định danh nghiệp vụ |
| **Unavailable** | Không đủ replica đang sống để đáp ứng CL tại thời điểm kiểm tra | Retry tức thì sang coordinator khác thường không giúp nếu tính sẵn sàng của replica chưa thay đổi |
| **Client/driver timeout** | Ứng dụng hết thời hạn chờ, trong khi server có thể vẫn đang xử lý hoặc đã hoàn tất | Không suy ra “ghi thất bại”. Tránh cộng thêm vòng retry không giới hạn ở tầng ứng dụng |
| **Mất kết nối, node lỗi, quá tải** | Coordinator hoặc đường truyền có vấn đề; replica vẫn có thể khỏe | Retry node khác **trong local DC** có thể hữu ích cho thao tác an toàn; nếu quá tải toàn cụm, phải giảm tốc độ, backoff hoặc từ chối tải |
| **Sai cú pháp, bảng không tồn tại, kiểu dữ liệu sai** | Lỗi yêu cầu không hợp lệ | Không retry; sửa truy vấn hoặc schema |

Cần phân biệt **server-side `ReadTimeoutException`/`WriteTimeoutException`** với **driver-side `DriverTimeoutException`**: thời hạn ở coordinator và thời hạn request ở driver đo hai phạm vi khác nhau. Những hành vi retry cụ thể phụ thuộc **phiên bản Java Driver, retry policy đang lắp và loại lỗi**. Không nên suy luận toàn bộ hành vi thực tế chỉ từ tên `DefaultRetryPolicy`; hãy kiểm tra policy và cấu hình của phiên bản triển khai.

## 6. Idempotence: điều kiện trước khi phát lại request

Một câu lệnh **idempotent** khi thực thi lặp lại với **cùng đầu vào** không làm thay đổi kết quả nghiệp vụ theo cách không mong muốn. Cassandra không cung cấp bảo đảm *exactly once* chỉ vì driver có retry.

| Câu lệnh | Có thể đánh dấu idempotent? | Lưu ý |
| --- | --- | --- |
| `SELECT` đọc thông thường | Thường có | Retry có thể làm thay đổi thời điểm và replica phục vụ kết quả; cần giữ CL theo yêu cầu |
| `INSERT`/`UPDATE` gán giá trị cố định theo cùng primary key | Thường có, nếu nghiệp vụ chấp nhận | Giữ nguyên primary key, giá trị, timestamp khi cần; chú ý TTL, ghi đồng thời và timestamp do server tạo |
| `UPDATE counter = counter + 1` | **Không** | Lặp lại làm tăng counter lần nữa |
| Thêm phần tử vào list bằng phép cộng/phép cập nhật không idempotent | Thường **không** | Có thể làm lặp phần tử hoặc thay đổi thứ tự |
| `INSERT ... IF NOT EXISTS` và các thao tác LWT | **Phải xét riêng** | Lần đầu có thể đã commit nhưng response bị mất; lần lặp có thể trả `[applied] = false`, khác kết quả lần đầu |
| Tạo event ID mới mỗi lần thử | **Không** đối với mục tiêu “một event” | Mỗi lần có thể ghi thêm một hàng riêng |

Ngay cả `INSERT` cùng key và giá trị cũng cần xét **timestamp và concurrency**. Nếu retry tạo timestamp mới, lần ghi sau có thể thắng một cập nhật đồng thời; nếu dùng TTL, thời điểm hết hạn có thể thay đổi. Với yêu cầu chống trùng chặt chẽ, nên dùng event ID cố định, cơ chế đối soát hoặc quy trình nghiệp vụ phù hợp; không xem thuộc tính idempotent của driver như khóa chống trùng tự động.

Khi một `WriteTimeout` xảy ra, ứng dụng có thể đọc lại theo định danh đã biết hoặc đối soát với hệ thống nguồn. Tuy nhiên, **không tìm thấy bản ghi ngay sau timeout không chứng minh request cũ chắc chắn chưa ghi**, vì thao tác cũ có thể còn đang lan truyền hoặc xử lý.

## 7. Java Driver 4.x: thực hành giữ locality và idempotence

Ví dụ tối giản dùng API `com.datastax.oss.driver.api`. Tên DC phải khớp cấu hình thực tế; hostname và thông tin xác thực cần thay theo môi trường.

~~~java
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class EventWriter {
    public static void writeEvent(
            UUID tenantId, LocalDate day, UUID eventId, String payload) {
        // Trong ứng dụng thật, CqlSession nên được quản lý và tái sử dụng.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("cassandra-dc1.example", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                "INSERT INTO app_events.events_by_day " +
                "(tenant_id, event_day, event_id, payload) " +
                "VALUES (?, ?, ?, ?)");

            BoundStatement statement = prepared.boundStatementBuilder()
                .setUuid(0, tenantId)
                .setLocalDate(1, day)
                .setUuid(2, eventId)
                .setString(3, payload)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                // Chỉ đặt true sau khi đã kiểm tra ngữ nghĩa ghi lặp.
                .setIdempotent(true)
                .build();

            session.execute(statement);
        }
    }
}
~~~

**Điều quan trọng trong ví dụ:**

1. `withLocalDatacenter("dc1")` thiết lập local DC của driver; kết hợp cơ chế load balancing/token awareness để ưu tiên coordinator phù hợp. Một contact point là điểm khám phá cluster, không phải địa chỉ cố định để mọi request luôn gửi tới.
2. Prepared statement và cả hai giá trị partition key giúp driver xác định routing key. Đó là nền tảng để chọn node tốt trong cùng DC.
3. `LOCAL_QUORUM` yêu cầu quorum ở DC của coordinator; nó không có nghĩa chắc chắn nhận xác nhận quorum ở tất cả DC.
4. `setIdempotent(true)` là **khai báo ngữ nghĩa do lập trình viên chịu trách nhiệm**, không phải phép biến đổi CQL thành idempotent. Cùng `eventId` phải được tái sử dụng nếu thao tác được phát lại.
5. Trong service thực tế, khởi tạo `CqlSession` một lần rồi dùng chung, thay vì mở/đóng session mỗi request như ví dụ minh họa độc lập trên.

Cấu hình mặc định có thể đặt local DC, consistency và thời gian chờ như sau (các khóa dưới đây theo Java Driver 4.x):

~~~hocon
datastax-java-driver {
  basic {
    load-balancing-policy.local-datacenter = dc1
    request {
      consistency = LOCAL_QUORUM
      timeout = 2 seconds
    }
  }
}
~~~

Timeout 2 giây **chỉ là ví dụ**, không phải giá trị phù hợp cho mọi workload. Request timeout nên dựa trên latency thực đo, service-level objective và tổng ngân sách của lời gọi từ ứng dụng. Policy retry có thể là policy mặc định hoặc policy do hệ thống cấu hình; cần đọc hành vi thực tế trước khi thay đổi.

## 8. Chọn same-node hay next-node theo nguyên nhân

Một cách suy nghĩ thực tế cho từng request:

~~~text
Yêu cầu gặp lỗi / quá thời gian
  |
  +-- CQL không hợp lệ, CL không thể đáp ứng, hoặc hết deadline?
  |      -> Trả lỗi / báo trạng thái; không retry mù
  |
  +-- Ghi không idempotent hoặc chưa biết request cũ đã commit?
  |      -> Trả trạng thái chưa xác định; đối soát theo nghiệp vụ
  |
  +-- Lỗi thoáng qua và thao tác an toàn để lặp?
         |
         +-- Coordinator còn khỏe, vấn đề nhất thời ở phản hồi?
         |      -> Có thể retry same-node nếu policy cho phép
         |
         +-- Coordinator/kết nối lỗi hoặc bị nghẽn?
                -> Có thể retry next-node trong local DC
                -> Luôn chịu giới hạn attempt/deadline/backpressure
~~~

Đây là **khung đánh giá**, không phải bản sao logic của `DefaultRetryPolicy`. Quyết định chính xác trong driver còn bị chi phối bởi loại exception, số lần đã retry, idempotence, thời hạn request và danh sách node đủ điều kiện. Đừng tự triển khai vòng `while (true)` ở service bao quanh một driver đã retry nội bộ.

Một số nguyên tắc vận hành:

- **Đặt giới hạn tổng** về số attempt và deadline từ API đến Cassandra. Nếu mỗi tầng API, repository và driver đều retry 3 lần, số request có thể tăng theo cấp số nhân khi gặp sự cố.
- **Backoff có jitter** khi retry ở tầng ứng dụng sau lỗi quá tải; tránh hàng nghìn client đồng loạt thử lại. Không dùng `Thread.sleep` chặn luồng event loop của driver trong callback retry.
- **Giữ local DC và routing key đúng**; không tự chuyển sang DC xa vì một lần timeout lẻ tẻ.
- **Không tự động hạ CL** để cứu request: trả kết quả với `ONE` thay cho `LOCAL_QUORUM` có thể vi phạm hợp đồng nhất quán của API.
- **Giới hạn speculative execution** cho request đã được xác nhận idempotent; đo rõ chi phí tăng lên cho các replica.
- **Thiết kế đường thoát cho ghi không rõ trạng thái**, chẳng hạn event ID duy nhất, truy vấn đối soát hoặc đánh dấu “pending” cho quy trình bất đồng bộ.

## 9. Tình huống phân tích: timeout, retry và locality

**Tình huống A — lỗi coordinator, replica còn khỏe.** Ứng dụng tại `dc1` ghi một event cố định với `LOCAL_QUORUM`. Coordinator A mất kết nối, nhưng hai replica địa phương vẫn hoạt động. Nếu lệnh idempotent và còn thời gian, retry trên coordinator B cùng `dc1` có thể thành công. Đây là ví dụ retry next-node phát huy tác dụng vì đã đổi điểm điều phối bị lỗi.

**Tình huống B — mất quorum tại local DC.** Hai trong ba replica của `dc1` ngừng hoạt động. Dù đổi từ A sang B hay C, `LOCAL_QUORUM` vẫn cần hai xác nhận tại DC đó. Retry sang coordinator khác không giải quyết thiếu replica. Giảm CL hoặc chuyển DC cần là quyết định failover/nhất quán có chủ đích, không phải phản xạ với lỗi timeout.

**Tình huống C — ghi thành công nhưng response biến mất.** Coordinator đã nhận đủ ACK ghi, nhưng kết nối về ứng dụng đứt trước khi trả thành công. Ứng dụng thấy timeout và gửi `counter + 1` thêm lần nữa: counter có thể tăng **hai lần**. Với event được ghi theo cùng primary key, retry ít rủi ro trùng hàng hơn, nhưng vẫn phải xét timestamp, TTL và cạnh tranh ghi.

**Tình huống D — failover nhầm sang DC2.** Ứng dụng và dữ liệu phục vụ chính ở `dc1`; vì cấu hình failover không rõ ràng, request được chuyển tới coordinator `dc2`. Độ trễ tăng qua WAN. Nếu CL là `LOCAL_QUORUM`, quorum giờ thuộc `dc2`, nên hành vi đọc sau ghi có thể khác kỳ vọng ban đầu. Cần xem lại cấu hình routing/failover trước khi tăng số retry.

## 10. Quan sát và chẩn đoán trong production

Để phân biệt “thử nút khác giải quyết lỗi” với “retry đang che giấu cụm quá tải”, cần quan sát **request gốc và các attempt**:

| Nhóm tín hiệu | Nên theo dõi | Gợi ý diễn giải |
| --- | --- | --- |
| Routing/locality | Local DC cấu hình, coordinator thực tế, routing key, tỷ lệ request sang remote DC | Remote coordinator bất ngờ có thể báo hiệu cấu hình sai hoặc failover ngoài dự kiến |
| Retry | Retry count theo loại lỗi, same/next node, successful-after-retry, exhausted retries | Tăng mạnh thường là triệu chứng, không phải giải pháp lâu dài |
| Hiệu năng | Latency p95/p99, request timeout, inflight requests, pool saturation, throughput | Retry có thể làm tăng tail latency và tải khi hệ thống đã chậm |
| Replica/cluster | Node up/down, dropped messages, read/write timeout, overload, disk/compaction/GC | Xác định lỗi gốc thuộc coordinator, replica, hoặc tài nguyên cluster |
| Nghiệp vụ | Event ID trùng, trạng thái pending, đối soát sau write timeout | Giúp phát hiện các lần ghi lặp hoặc kết quả không xác định |

Khi điều tra một sự cố cụ thể, có thể:

1. Ghi lại loại exception, consistency level, idempotence và request deadline; tránh log payload hoặc dữ liệu nhạy cảm.
2. Kiểm tra metrics/tracing của Java Driver để biết coordinator và số attempt thực tế; khả năng quan sát chi tiết phụ thuộc phiên bản driver và cấu hình telemetry.
3. Dùng `nodetool status` để xác định node/DC đang sống; kết hợp `nodetool tpstats`, `nodetool netstats` và metrics để xác định nghẽn hoặc hoạt động mạng.
4. Bật tracing CQL **có chọn lọc** cho request tái hiện được lỗi để xem coordinator tương tác với replica ra sao; tránh bật rộng trên production vì overhead.
5. So sánh các lần lỗi với p95/p99 latency và thay đổi topology trước khi chỉnh retry policy hoặc timeout.

## 11. Những điều cần nhớ

- **Retry same-node** có thể giải quyết lỗi rất ngắn hạn nhưng không tránh được một coordinator đang hỏng hay quá tải; **retry next-node** có thể tránh coordinator lỗi nhưng không tạo thêm replica hoặc tự khôi phục quorum.
- **Locality gồm cả vị trí coordinator lẫn vị trí replica**. Java Driver cần local DC đúng, partition key rõ và cơ chế token-aware routing để giảm chi phí mạng; retry sang node khác thường vẫn nên ở cùng DC.
- `LOCAL_QUORUM` gắn với **DC của coordinator thực thi**. Chuyển coordinator sang DC khác có thể thay đổi phạm vi nhất quán và độ trễ.
- **Timeout ghi không chứng minh ghi thất bại**. Chỉ đánh dấu idempotence khi thực sự an toàn để lặp; với counter, LWT và thao tác có hiệu ứng phụ, phải xem xét kỹ ngữ nghĩa nghiệp vụ.
- Retry cần **giới hạn, đo đạc và phối hợp giữa driver với ứng dụng**. Khi nguyên nhân là thiếu quorum hoặc quá tải kéo dài, khôi phục cluster và điều tiết tải quan trọng hơn tăng số lần thử.
