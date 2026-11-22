# Consistency level, serial consistency và execution profile của statement

> **Chương:** Truy vấn từ Java  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Bối cảnh:** Apache Cassandra là hệ cơ sở dữ liệu phân tán theo mô hình wide-column. Khi ứng dụng Java thực thi CQL, lựa chọn consistency level phải xét partition key, replication, topology datacenter, đường đọc/ghi, compaction, repair, xử lý timeout và yêu cầu đúng đắn nghiệp vụ.

## 1. Bài toán: cùng một truy vấn, nhiều chính sách thực thi

Giả sử dịch vụ Java có ba loại thao tác:

- Hiển thị một trang sự kiện gần đây của khách hàng, ưu tiên độ trễ thấp và chấp nhận một mức dữ liệu có thể chưa cập nhật.
- Đọc trạng thái thanh toán vừa được ghi, cần chính sách nhất quán mạnh hơn trong datacenter hiện tại.
- Tạo đơn hàng **chỉ khi mã đơn hàng chưa tồn tại**, đòi hỏi thao tác so sánh-ghi có điều kiện (*lightweight transaction — LWT*).

Nếu tất cả request đều dùng một lựa chọn nhất quán, hệ thống dễ rơi vào một trong hai tình huống: **đọc quá đắt** so với yêu cầu, hoặc **không đáp ứng đúng cam kết nghiệp vụ** khi replica chậm/hỏng. Thêm nữa, LWT có một pha đồng thuận riêng nên chỉ đặt consistency level thông thường là chưa mô tả đầy đủ chính sách.

Trong Java Driver 4.x, ba khái niệm cần tách biệt:

1. **Consistency level (CL):** mức yêu cầu phản hồi của replica trong thao tác đọc/ghi CQL thông thường.
2. **Serial consistency level (serial CL):** phạm vi đồng thuận của pha Paxos dùng cho thao tác có điều kiện như **IF NOT EXISTS** hay **IF status = ?**.
3. **Execution profile:** một nhóm cấu hình thực thi (consistency mặc định, timeout, page size và những tùy chọn driver khác), có thể gắn cho statement để tránh lặp cấu hình.

Một execution profile **không phải một loại consistency level**: nó là nơi định nghĩa các giá trị mặc định và chính sách driver cho một nhóm request. Statement vẫn có thể đặt CL tường minh để ghi đè cấu hình tương ứng của profile.

Sau bài học, bạn có thể cấu hình CL ở tầng session/profile/statement, dùng serial CL đúng trong LWT, xử lý kết quả điều kiện, lựa chọn mức nhất quán theo topology và kiểm chứng qua Java/CQL khi có timeout hoặc replica bị lỗi.

## 2. Đường đi của request từ Java đến replica

Khi nhận CQL, Java driver chọn một coordinator theo thông tin cluster và chính sách định tuyến. Nếu bind đủ partition key, khả năng **token-aware routing** có thể giúp chọn coordinator gần các replica sở hữu partition; sau đó coordinator phối hợp các replica theo replication strategy và mức CL.

~~~mermaid
flowchart LR
    A["Java service"] --> B["Statement: query + bind + CL + profile"]
    B --> C["Java driver: routing và execution"]
    C --> D["Coordinator Cassandra"]
    D --> R1["Replica 1"]
    D --> R2["Replica 2"]
    D --> R3["Replica 3"]
    R1 --> K["Commitlog / memtable / SSTable"]
    R2 --> K
    R3 --> K
~~~

**Lưu ý về mô hình Cassandra:**

- **Partition key** định vị phân vùng; **clustering columns** sắp thứ tự các hàng bên trong một partition.
- **Replication factor (RF)** là số bản sao cấu hình theo datacenter/keyspace, không phải số replica đang khỏe tại mọi thời điểm.
- **Consistency level** chọn điều kiện thành công của request; nó không điều khiển vị trí dữ liệu được đặt và không tự cải thiện truy vấn thiếu partition key.
- **Compaction** hợp nhất SSTable và xử lý dữ liệu/tombstone theo cơ chế LSM; **repair** đối chiếu các replica. Hai công việc này ảnh hưởng độ trễ, khả dụng và chất lượng dữ liệu quan sát, nhưng không thay thế chọn CL đúng.
- **Retry** và **timeout** từ Java không có nghĩa request chắc chắn chưa được áp dụng. Điều này đặc biệt quan trọng với LWT hoặc các thao tác không idempotent.

## 3. Consistency level đọc/ghi: hiểu theo số replica và phạm vi DC

### 3.1. Các mức thường gặp

| CL | Ý nghĩa khái quát | Dùng khi nào cần cân nhắc |
|---|---|---|
| **ONE** | Thường cần một replica đáp ứng; phạm vi chọn replica phụ thuộc coordinator/topology | Đọc/ghi ưu tiên độ trễ hoặc availability và chấp nhận đánh đổi phù hợp |
| **LOCAL_ONE** | Cần một replica đáp ứng tại datacenter cục bộ | Ứng dụng chủ yếu làm việc với một local DC |
| **QUORUM** | Quorum tính theo tổng replica của phạm vi được định nghĩa | Muốn phần giao nhau trên tập replica, cân nhắc chi phí đa DC |
| **LOCAL_QUORUM** | Đa số replica trong local DC | Nhiều ứng dụng cần tính nhất quán cao hơn trong DC cục bộ |
| **EACH_QUORUM** | Với ghi, yêu cầu quorum ở từng DC liên quan | Các ghi cần xác nhận theo nhiều DC; chi phí/availability lớn hơn |
| **ALL** | Yêu cầu tất cả replica được tính cho thao tác | Đòi hỏi xác nhận rộng, dễ lỗi khi một replica không khả dụng |
| **SERIAL / LOCAL_SERIAL** | Mức **serial** liên quan pha đồng thuận LWT; cũng có ngữ nghĩa đặc biệt cho đọc serial tùy cách dùng | Không dùng như cách thay thế tùy tiện cho CL đọc/ghi thông thường |

Bảng không phải danh sách đầy đủ mọi CL của Cassandra. **ANY** là mức dành cho một số thao tác ghi, không phải lựa chọn đọc; các mức **TWO/THREE** cũng tồn tại trong những phiên bản. Ở Java Driver 4.x có enum **DefaultConsistencyLevel** cho các mức thông dụng.

**Không chọn CL chỉ dựa vào tên “QUORUM”** mà bỏ qua số replica và datacenter. Đặc biệt, **QUORUM** và **LOCAL_QUORUM** có phạm vi tính khác nhau trên một cluster nhiều DC.

### 3.2. Ví dụ RF = 3 trong một local datacenter

Giả sử keyspace có **RF = 3** ở **dc1** và ba replica của partition đều được phân bố/khả dụng:

| CL | Số phản hồi cần theo ý nghĩa thường dùng |
|---|---:|
| ONE / LOCAL_ONE (trong phạm vi thích hợp) | 1 |
| LOCAL_QUORUM tại dc1 | 2 |
| ALL (chỉ ba replica liên quan) | 3 |

Ví dụ một write LOCAL_QUORUM được coordinator xác nhận khi đủ **2/3 replica** trong local DC phản hồi theo điều kiện của thao tác. Điều này **không có nghĩa** replica thứ ba chắc chắn đã nhận và xử lý xong ghi ngay tại thời điểm client được trả kết quả.

Khi một replica lỗi, **LOCAL_QUORUM** vẫn có thể được đáp ứng nếu hai replica còn lại khỏe. Nhưng nếu một replica khác đang bị GC pause hoặc disk I/O quá tải, request có thể timeout dù RF được cấu hình là 3.

### 3.3. Đọc và ghi: phần giao nhau của replica

Với một tập replica đơn giản RF = 3, chọn write CL = 2 và read CL = 2 tạo quan hệ:

~~~text
R = số replica tham gia phản hồi đọc  = 2
W = số replica xác nhận ghi          = 2
RF = 3

R + W = 4 > RF = 3
~~~

Điều kiện **R + W > RF** thể hiện hai tập phản hồi phải có phần giao nhau khi xét cùng một tập replica. Đây là một công cụ tư duy quan trọng, **không phải chứng minh Cassandra cung cấp transaction isolation hoặc linearizability cho mọi thao tác**.

Cần xét thêm:

- Cùng **datacenter** và cùng phạm vi replica nào? LOCAL_QUORUM ở các DC khác nhau không tự tạo giao nhau giữa các tập local.
- Đồng hồ/timestamp, ghi đồng thời và quy tắc hòa giải của Cassandra có thể ảnh hưởng giá trị cuối cùng.
- Replica bị lỗi, repair chưa hoàn thành, các xóa/tombstone cũ và sự cố vận hành có thể ảnh hưởng tính đúng đắn.
- Một phép **read-modify-write** trong ứng dụng, dù đọc và ghi bằng LOCAL_QUORUM, **không phải compare-and-set atomic** nếu không dùng LWT hoặc một cơ chế đồng bộ phù hợp.

**Kết luận:** LOCAL_QUORUM thường hữu ích cho đọc/ghi cần mức nhất quán tốt trong local DC, nhưng một quy tắc nghiệp vụ như “chỉ tạo đơn hàng một lần” phải được giải quyết bằng điều kiện phù hợp, không chỉ bằng phép cộng R + W.

## 4. Đặt consistency level ở tầng Java statement

Java driver 4.x cho phép đặt mức CL trên một statement, ví dụ **BoundStatement** của prepared CQL. Điều này phù hợp khi cùng session có nhóm truy vấn với yêu cầu khác nhau.

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

// Giả sử session đã prepare SELECT có 2 bind markers:
// WHERE tenant_id = ? AND event_day = ?
PreparedStatement preparedRead = session.prepare(
    "SELECT happened_at, event_id, event_type " +
    "FROM shop.events_by_tenant_day " +
    "WHERE tenant_id = ? AND event_day = ? LIMIT 50");

BoundStatement read = preparedRead.bind(tenantId, eventDay)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM);

var result = session.execute(read);
~~~

Đoạn trên giả định các biến **session**, **tenantId**, **eventDay** và keyspace/bảng có trước; phần schema sẽ trình bày ở mục 7. **LOCAL_QUORUM** chỉ có ý nghĩa khi topology/RF thực tế đáp ứng điều kiện đó.

**BoundStatement của driver 4.x là đối tượng immutable.** Setter trả về statement mới. Nếu viết:

~~~java
BoundStatement original = preparedRead.bind(tenantId, eventDay);
original.setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

// Sai về ý định: original vẫn là statement chưa được cập nhật CL.
session.execute(original);
~~~

phải sửa thành:

~~~java
BoundStatement corrected = original
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
session.execute(corrected);
~~~

Hoặc nối các setter ngay trong quá trình tạo statement.

### 4.1. CL của từng request, không phải thay đổi toàn cluster

**setConsistencyLevel** không thay đổi RF trong keyspace, cũng không sửa cấu hình server. Nó đặt yêu cầu consistency cho **request đó**. Hai statement dùng chung CqlSession có thể có CL khác nhau:

~~~java
BoundStatement fastRead = preparedRead.bind(tenantId, eventDay)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_ONE);

BoundStatement importantRead = preparedRead.bind(tenantId, eventDay)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
~~~

Lựa chọn cần phù hợp SLA và hợp đồng nhất quán của ứng dụng; không thay CL tùy tiện theo từng lỗi. Đặc biệt, tự giảm CL sau khi gặp timeout có thể làm API **trả về dữ liệu cũ** mà người gọi không biết.

### 4.2. Đọc đúng partition key vẫn là điều kiện nền

Với bảng có khóa **((tenant_id, event_day), happened_at, event_id)**, điều kiện đọc phải bind **cả tenant_id lẫn event_day** để định vị một partition. Một câu truy vấn bỏ thành phần khóa hoặc quét nhiều partition sẽ tốn I/O và tạo fan-out; tăng CL không chữa được mô hình truy vấn đó.

## 5. Serial consistency: pha đồng thuận riêng của LWT

### 5.1. Tại sao LWT khác INSERT/UPDATE thường?

Cassandra có ngữ nghĩa **last-write-wins** dựa trên timestamp/tombstone ở đường ghi thường. Nếu hai ứng dụng cùng đọc “chưa có đơn hàng” rồi đều INSERT, việc đọc trước đó bằng LOCAL_QUORUM **không tự biến hai câu lệnh thành một phép kiểm tra-và-ghi atomic**.

CQL hỗ trợ **lightweight transactions (LWT)** thông qua điều kiện như:

~~~sql
INSERT INTO shop.order_state_by_id (
    tenant_id, order_id, status, created_at
) VALUES (?, ?, ?, ?)
IF NOT EXISTS;
~~~

Hoặc:

~~~sql
UPDATE shop.order_state_by_id
SET status = ?
WHERE tenant_id = ? AND order_id = ?
IF status = ?;
~~~

LWT sử dụng cơ chế **Paxos** để điều phối kiểm tra điều kiện và ghi theo phạm vi partition thích hợp, thay vì tự ghép một SELECT rồi một INSERT trong ứng dụng Java.

### 5.2. Hai loại CL tham gia LWT

Khi thực thi một câu lệnh có **IF**, cần phân biệt hai lớp:

| Lựa chọn | Điều khiển | Ví dụ |
|---|---|---|
| **Regular consistency level** | Mức xác nhận đọc/ghi thông thường, gồm giai đoạn commit của LWT theo cơ chế server | LOCAL_QUORUM |
| **Serial consistency level** | Phạm vi serial consensus/Paxos để đánh giá và phối hợp điều kiện LWT | SERIAL hoặc LOCAL_SERIAL |

Trong nhiều trường hợp, một LWT sẽ thực hiện công việc nhiều pha và nhiều lượt trao đổi hơn ghi thường, nên **độ trễ/CPU/network** tăng. Không chọn LWT cho mọi INSERT chỉ để “mạnh hơn” nếu nghiệp vụ không cần điều kiện atomic.

### 5.3. SERIAL và LOCAL_SERIAL

| Serial CL | Phạm vi khái quát | Điều cần cân nhắc |
|---|---|---|
| **SERIAL** | Pha serial consensus theo phạm vi replica của cơ chế LWT trên nhiều DC, khi có nhiều DC | Phù hợp hơn khi yêu cầu phối hợp ở phạm vi rộng; độ trễ và availability có thể bị ảnh hưởng bởi liên DC |
| **LOCAL_SERIAL** | Pha serial consensus trong local datacenter của coordinator | Có thể giảm phụ thuộc liên DC, nhưng phải đánh giá nếu invariant cần toàn bộ các DC |

**Điểm quan trọng với ứng dụng đa DC:** LOCAL_SERIAL không nên được lựa chọn chỉ vì nhanh hơn nếu nghiệp vụ muốn bảo đảm một thứ tự điều kiện thống nhất xuyên DC. Không nên **trộn SERIAL và LOCAL_SERIAL** cho cùng một tập bất biến nghiệp vụ mà không hiểu ngữ nghĩa và phạm vi điều phối; cần đọc tài liệu đúng phiên bản và kiểm thử kịch bản concurrent writes từ các DC.

Serial consistency **không phải một nút “nâng cấp mọi SELECT”**. Nó chủ yếu được dùng cho các phép LWT có điều kiện; Cassandra còn có ngữ nghĩa đặc biệt cho các serial reads, nhưng không nên tự đặt serial CL lên mọi câu truy vấn thông thường.

### 5.4. LWT có phạm vi atomic nào?

Các điều kiện CQL áp dụng trong phạm vi thao tác mà Cassandra hỗ trợ và ngữ nghĩa của **partition** liên quan. Một **INSERT IF NOT EXISTS** giúp kiểm soát việc tạo một row theo khóa chính. Nó **không biến nhiều partition khác nhau thành một giao dịch ACID đa bảng có rollback**.

Khi nghiệp vụ cần vừa tạo order vừa cập nhật nhiều bảng phục vụ các truy vấn khác nhau, phải thiết kế idempotency, outbox/event processing hoặc quy trình hòa giải phù hợp. **Consistency level** và **serial CL** không thay thế xử lý giao dịch đa thực thể ở tầng ứng dụng.

## 6. Kết quả LWT và trường [applied]

Cassandra thường trả một kết quả có cột **[applied]** cho conditional write:

| Giá trị | Ý nghĩa trong trường hợp request trả kết quả thành công |
|---|---|
| **true** | Điều kiện được chấp nhận và thao tác có điều kiện đã áp dụng theo kết quả server |
| **false** | Điều kiện không thỏa; thao tác được yêu cầu không được áp dụng |
| **Timeout/exception** | **Không đủ thông tin** để khẳng định đã áp dụng hay chưa |

Ví dụ nếu một order với **order_id** đã tồn tại, câu **INSERT ... IF NOT EXISTS** có thể trả **[applied] = false** kèm thông tin giá trị hiện có (phụ thuộc câu lệnh/phiên bản). Đây là **xung đột nghiệp vụ**, không mặc nhiên là lỗi hạ tầng cần retry.

Ngược lại, một LWT timeout có thể đã đi qua một số pha hoặc thậm chí đã hoàn tất nhưng client chưa nhận kết quả. **Không suy ra “timeout = không ghi”.** Điều này ảnh hưởng thiết kế API idempotency, request ID và lựa chọn retry.

### 6.1. Không nhầm false sau retry với thất bại lần đầu

Giả sử lần đầu **INSERT IF NOT EXISTS** đã áp dụng, nhưng phản hồi bị mất. Client retry cùng điều kiện; lần hai nhận **[applied] = false** vì row nay đã tồn tại. Nếu API giải thích false là “một người khác đã tạo đơn” mà không kiểm tra định danh/giá trị, có thể trả sai kết quả nghiệp vụ.

Phương án an toàn hơn:

1. Dùng **order_id cố định** từ yêu cầu, không tạo UUID mới sau mỗi lần retry.
2. Ghi lại **idempotency key** hoặc thông tin định danh của request theo thiết kế.
3. Khi kết quả không rõ, đọc/đối soát row theo partition key với CL phù hợp.
4. Phân biệt “đã được tạo bởi chính request trước” với “xung đột với nội dung khác”.
5. Chỉ retry tự động theo chính sách được thử nghiệm với LWT và loại lỗi cụ thể.

LWT hỗ trợ atomic condition cho một phạm vi dữ liệu, **không tự tạo cơ chế exactly-once cho toàn hệ thống**.

## 7. Mô hình dữ liệu CQL để thực hành

Hai bảng phục vụ hai access patterns riêng:

1. **events_by_tenant_day:** đọc các sự kiện theo tenant/ngày, có thể chấp nhận CL khác nhau tùy endpoint.
2. **order_state_by_id:** tra/cập nhật trạng thái của một order theo khóa, dùng **IF** khi cần compare-and-set.

~~~sql
-- Tên dc1 và RF = 3 phải phù hợp topology thật hoặc môi trường lab.
CREATE KEYSPACE IF NOT EXISTS shop
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS shop.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    happened_at timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id ASC);

CREATE TABLE IF NOT EXISTS shop.order_state_by_id (
    tenant_id uuid,
    order_id uuid,
    status text,
    created_at timestamp,
    version int,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

**Ý nghĩa về phân vùng:**

- Bảng sự kiện dùng bucket **event_day** để tránh một tenant có partition tăng vô hạn. Nếu một tenant cực nóng, còn phải tính kích thước và tải mỗi partition để chọn bucket nhỏ hơn.
- Bảng trạng thái dùng composite partition key **(tenant_id, order_id)**. Mỗi đơn thường có một partition nhỏ, thuận lợi cho LWT trên đơn đó và tránh tranh chấp trên một partition tenant chung.
- **PRIMARY KEY** quyết định đường định tuyến. CL tác động số replica cần phản hồi, không quyết định kích thước partition.
- Hai bảng theo truy vấn khác nhau có thể cùng mô tả dữ liệu một nghiệp vụ; Cassandra không tự cho tính atomic cross-table. Cần cơ chế đồng bộ/hòa giải nếu nghiệp vụ đòi hỏi.

### 7.1. Dữ liệu thử nghiệm

~~~sql
INSERT INTO shop.events_by_tenant_day (
    tenant_id, event_day, happened_at, event_id, event_type
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    22222222-2222-4222-8222-222222222222,
    'CHECKOUT_STARTED'
);

-- Thử câu có điều kiện trong cqlsh; nếu row đã tồn tại,
-- [applied] sẽ không còn true cho lần insert cùng khóa.
INSERT INTO shop.order_state_by_id (
    tenant_id, order_id, status, created_at, version
) VALUES (
    11111111-1111-4111-8111-111111111111,
    33333333-3333-4333-8333-333333333333,
    'NEW',
    '2026-11-21T08:05:00Z',
    0
) IF NOT EXISTS;
~~~

Các UUID chỉ là fixture. Khi chạy trên một lab có **ít hơn ba replica** trong dc1, không được giả định **LOCAL_QUORUM với RF 3** sẽ có các bảo đảm giống production. Hãy cấu hình topology/RF tương thích môi trường và ghi rõ khác biệt trong kết quả test.

## 8. Ví dụ Java Driver 4.x: regular CL ở mức statement

Java Driver 4.x dùng **DefaultConsistencyLevel** và các API immutable statement. Ví dụ sau mở CqlSession vào môi trường lab và đọc theo partition key.

~~~java
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public class ReadWithConsistency {
    public static void main(String[] args) {
        UUID tenantId = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");
        LocalDate day = LocalDate.of(2026, 11, 21);

        // Đổi contact point, dc và bảo mật theo môi trường lab.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                "SELECT happened_at, event_id, event_type " +
                "FROM shop.events_by_tenant_day " +
                "WHERE tenant_id = ? AND event_day = ? LIMIT ?");

            BoundStatement statement = prepared
                .bind(tenantId, day, 50)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM);

            ResultSet result = session.execute(statement);
            int count = 0;
            for (Row row : result) {
                if (row.getUuid("event_id") == null) {
                    throw new IllegalStateException(
                        "Event thiếu khóa định danh");
                }
                count++;
            }
            System.out.println("Rows: " + count);
        }
    }
}
~~~

**Giải thích:**

- **PreparedStatement** được chuẩn bị một lần; bind dữ liệu theo đúng **uuid, date, int** và tái sử dụng.
- Statement mang **LOCAL_QUORUM**; cùng prepared CQL có thể tạo statement khác với CL khác.
- **LIMIT ?** giới hạn số hàng trả về cho một partition, không biến partition lớn thành mô hình dữ liệu tốt.
- Ví dụ **không thiết lập TLS/auth** để tập trung vào CL. Môi trường thật cần xác thực và TLS phù hợp; không được tắt bảo mật để giải quyết lỗi kết nối.
- Trong service lâu dài, tái sử dụng **CqlSession** và PreparedStatement; không mở session mới cho từng HTTP request.
- Test trả kết quả không lỗi chưa đủ chứng minh dữ liệu chính xác: phải có fixture dự kiến và kiểm tra đúng event ID/value.

## 9. Ví dụ Java: LWT với regular CL và serial CL

Đối với yêu cầu “chỉ tạo order nếu chưa tồn tại”, dùng **INSERT ... IF NOT EXISTS** và cấu hình **hai CL tường minh**.

~~~java
import java.net.InetSocketAddress;
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public class CreateOrderIfAbsent {
    public static void main(String[] args) {
        UUID tenantId = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");
        UUID orderId = UUID.fromString(
            "33333333-3333-4333-8333-333333333333");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement insert = session.prepare(
                "INSERT INTO shop.order_state_by_id " +
                "(tenant_id, order_id, status, created_at, version) " +
                "VALUES (?, ?, ?, ?, ?) IF NOT EXISTS");

            BoundStatement conditional = insert.bind(
                    tenantId, orderId, "NEW",
                    Instant.parse("2026-11-21T08:05:00Z"), 0)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setSerialConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_SERIAL);

            Row row = session.execute(conditional).one();
            if (row == null) {
                throw new IllegalStateException(
                    "Không nhận được kết quả LWT");
            }

            if (row.getBoolean("[applied]")) {
                System.out.println("Order được tạo");
            } else {
                System.out.println(
                    "Order đã tồn tại; cần so thông tin nghiệp vụ");
            }
        }
    }
}
~~~

**Phân tích hai thuộc tính:**

- **setConsistencyLevel(LOCAL_QUORUM)**: regular CL cho phần ghi/commit theo điều kiện của request.
- **setSerialConsistencyLevel(LOCAL_SERIAL)**: serial CL cho pha đồng thuận LWT trong local DC.
- **[applied]** nói điều kiện có thỏa trong kết quả nhận được hay không. False không nên bị coi là lỗi hạ tầng và retry vô hạn.
- **orderId cố định** là điểm quan trọng cho idempotency. Nếu bị timeout trước khi biết kết quả, ứng dụng cần kiểm tra trạng thái đã ghi, không sinh order ID mới.
- Khi invariant phải được duy trì xuyên **nhiều datacenter**, cần phân tích phạm vi đồng thuận và lựa chọn **SERIAL** thay vì dùng LOCAL_SERIAL theo thói quen. Giữ chính sách serial nhất quán giữa các writers có liên quan.

### 9.1. Update trạng thái có điều kiện

Giả sử muốn chuyển trạng thái từ NEW sang PAID:

~~~sql
UPDATE shop.order_state_by_id
SET status = 'PAID', version = 1
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND order_id = 33333333-3333-4333-8333-333333333333
IF status = 'NEW' AND version = 0;
~~~

Đây là **compare-and-set** cho một order, không phải giải pháp transaction cho tất cả các bảng. Nếu cùng order đã được cập nhật bởi request khác, điều kiện không thỏa, trả **[applied] = false**. Ứng dụng cần quyết định retry theo trạng thái mới, báo xung đột, hoặc xử lý workflow riêng.

Nếu nhiều bảng theo truy vấn cùng biểu diễn trạng thái order, không thể suy từ việc một LWT ở **order_state_by_id** thành “mọi bảng khác đã cập nhật atomic”. Cần thiết kế sự kiện, idempotent projections và reconciliation.

## 10. Execution profile là gì?

Trong Java Driver 4.x, **execution profile** là cấu hình đặt tên để nhóm các lựa chọn thực thi thường dùng. Ví dụ một profile cho đọc nhẹ, một profile cho đọc cần LOCAL_QUORUM, một profile dành cho conditional write.

Nếu mỗi request đều phải gọi hàng loạt setter, mã dễ trùng lặp và thay đổi chính sách khó kiểm soát. Profile giúp tập trung **timeout, consistency mặc định, page size** và các tùy chọn khác theo nhóm request, đồng thời vẫn cho phép override có chủ đích.

### 10.1. Ví dụ cấu hình HOCON của Java Driver 4.x

Một dạng cấu hình trong tệp **application.conf** của ứng dụng dùng Java driver 4.x:

~~~hocon
datastax-java-driver {
  basic {
    contact-points = [ "127.0.0.1:9042" ]
    load-balancing-policy.local-datacenter = dc1

    request {
      consistency = LOCAL_ONE
      timeout = 2 seconds
      page-size = 500
    }
  }

  profiles {
    important-read {
      basic.request.consistency = LOCAL_QUORUM
      basic.request.timeout = 3 seconds
      basic.request.page-size = 100
    }

    conditional-write {
      basic.request.consistency = LOCAL_QUORUM
      basic.request.timeout = 5 seconds
    }
  }
}
~~~

Đây là **cấu hình minh họa**, không phải khuyến nghị cố định cho production. Tham số/tên option và khả năng hỗ trợ phụ thuộc **phiên bản driver 4.x cụ thể**; cần đối chiếu reference của driver, RF, datacenter, SLO và workload.

**Ba ý chính:**

1. **basic.request.consistency** ở cấu hình chung tạo một chính sách mặc định cho request không có override khác.
2. Profile **important-read** gắn LOCAL_QUORUM, timeout dài hơn và page size nhỏ hơn để phục vụ nhóm endpoint cụ thể.
3. Profile **conditional-write** đặt **regular CL**, còn **serial CL** của LWT sẽ được chỉ định rõ trên statement trong ví dụ sau. Không suy luận regular CL = LOCAL_QUORUM sẽ tự làm serial CL = LOCAL_SERIAL.

Với hệ thống nhiều môi trường, các giá trị contact point, DC, credential và TLS được cấp từ cấu hình deployment/secret manager phù hợp. Không nhúng password hoặc private key trong ví dụ cấu hình commit vào repository.

### 10.2. Gắn profile lên một statement

~~~java
BoundStatement important = preparedRead.bind(tenantId, eventDay)
    .setExecutionProfileName("important-read");

session.execute(important);
~~~

Với conditional write:

~~~java
BoundStatement lwt = preparedInsert.bind(
        tenantId, orderId, "NEW", createdAt, 0)
    .setExecutionProfileName("conditional-write")
    .setSerialConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_SERIAL);

Row result = session.execute(lwt).one();
~~~

Trong ví dụ này:

- Statement **important** thừa hưởng regular CL và timeout của profile **important-read** nếu không được override riêng.
- Statement **lwt** thừa hưởng regular CL từ **conditional-write** và **chọn serial CL tường minh**.
- Driver sẽ tìm profile theo tên. Nếu ứng dụng gõ sai tên hoặc profile không được khai báo trong cấu hình hiệu lực, có thể gặp lỗi cấu hình/statement; không coi profile không tồn tại là mặc nhiên rơi về profile mặc định.
- **setExecutionProfileName** trả một statement mới, vì statement immutable.

### 10.3. Profile và statement override: thứ tự ưu tiên thực tế

Xét:

~~~java
BoundStatement request = preparedRead.bind(tenantId, eventDay)
    .setExecutionProfileName("important-read")
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_ONE);
~~~

Cấu hình profile chọn **LOCAL_QUORUM**, nhưng statement đặt **LOCAL_ONE tường minh**. Vì vậy, **đối với CL của request này**, giá trị tường minh trên statement là lựa chọn cần được driver dùng thay cho mặc định của profile.

Một nguyên tắc hữu ích:

~~~text
Giá trị tường minh trên statement
    ưu tiên hơn giá trị tương ứng của execution profile.

Nếu statement không override:
    dùng execution profile được chọn.

Nếu không chọn named profile:
    dùng profile mặc định của session/config.
~~~

Các chi tiết cụ thể về inheritance giữa profile, override theo chương trình và giá trị mặc định phải được kiểm chứng ở phiên bản driver đang dùng. Một tính năng có thể có **cấu hình ở tầng driver và ở tầng server**; chúng không phải cùng một giới hạn. Ví dụ **driver request.timeout** không đồng nghĩa với tất cả **timeout server**.

### 10.4. Cách tránh profile bị lạm dụng

- Đặt tên theo **mục đích nghiệp vụ/loại tải**: **important-read**, **analytics-read**, **conditional-write**, thay vì tên mơ hồ như **profile1**.
- Dùng profile cho **nhóm request có chính sách chung**; dùng override trên statement khi có ngoại lệ được chấp thuận.
- Không tạo hàng trăm profile chỉ để thay CL theo từng request ID.
- Không tự giảm consistency level sau lỗi với lý do “profile nhanh hơn”; phải kiểm chứng rủi ro stale read và hợp đồng API.
- Khi muốn đổi profile, chạy test đúng endpoint và quan sát metrics; một thay đổi file cấu hình có thể ảnh hưởng rất nhiều request cùng lúc.
- Viết rõ **serial CL** cho LWT quan trọng để policy được review dễ dàng, thay vì dựa vào giả định của default.

## 11. Đặt CL ở từng tầng: lựa chọn nào nên dùng?

| Nhu cầu | Nơi đặt | Lý do |
|---|---|---|
| Phần lớn request dùng một CL chung | **Default profile** | Giảm lặp cấu hình trong ứng dụng |
| Một nhóm endpoint có SLA/timeout/page size khác | **Named execution profile** | Cấu hình có tên, dễ review và đo |
| Một câu lệnh cá biệt cần mức cao hơn | **Per-statement setConsistencyLevel** | Ý định cục bộ, rõ ràng trong code |
| Câu CQL có điều kiện cần Paxos | **Per-statement setSerialConsistencyLevel** và regular CL | Phân biệt hai pha của LWT |
| Một yêu cầu Java truy vấn ở DC khác | Xem lại **routing/local DC, topology và chính sách replica** | CL không tự chuyển service sang DC khác |
| Timeout hoặc unavailable tăng | **Điều tra nguyên nhân**, không tự động hạ CL | Tránh đánh đổi tính đúng đắn không được phê duyệt |

Dùng profile không làm driver “cache kết quả” hoặc làm query tự nhiên nhanh hơn; profile chỉ chọn chính sách. Nếu truy vấn chậm vì partition lớn, tombstone nhiều, compaction backlog hoặc node disk saturation, đổi profile có thể chỉ thay **khi nào request timeout** chứ không sửa nguyên nhân.

## 12. Xử lý timeout, retry và tính không chắc chắn của kết quả

Cassandra có thể báo lỗi khác nhau tùy nguồn gốc:

| Tín hiệu | Ý nghĩa cần phân biệt | Hướng xử lý |
|---|---|---|
| **Unavailable** | Không đủ replica đáp ứng CL theo đánh giá của coordinator | Kiểm tra RF/DC/replica health; không retry vô hạn |
| **ReadTimeout** | Không đủ phản hồi đọc trong timeout của server | Kiểm tra replica, read path, partition, tombstone, compaction và CL |
| **WriteTimeout** | Không đủ phản hồi ghi trong khoảng chờ | **Không suy ra ghi thất bại hoàn toàn**; đánh giá idempotency |
| **CAS/LWT timeout** | Không có kết luận chắc chắn về pha điều kiện | Kiểm tra lại trạng thái theo khóa/idempotency; không biến timeout thành applied=false |
| **Driver-side request timeout** | Client chờ quá thời hạn cục bộ | Phân biệt với timeout server; coordinator có thể vẫn xử lý |
| **Authentication/TLS/protocol** | Cấu hình/đường kết nối sai hoặc không tương thích | Sửa root cause; CL không khắc phục loại lỗi này |

Tên exception cụ thể và cách phân loại có thể khác theo phiên bản driver/server. Khi gặp lỗi thực, ghi **exception class**, statement operation, CL/serial CL, profile name, timeout, datacenter và trace ID có kiểm soát. Không ghi password, raw bind values hoặc dữ liệu khách hàng vào log.

### 12.1. Retry có thể làm tải tăng thêm

Nếu node chậm vì compaction/repair hoặc network, retry đồng loạt có thể tạo **retry storm**, tăng số request tới các replica vốn đã quá tải.

- Giới hạn số request đồng thời và có backpressure.
- Phân biệt **request idempotent** với thao tác có tác dụng phụ hoặc tạo ID mới.
- Với **counter increment**, không giả định retry an toàn khi kết quả không chắc chắn.
- Với **LWT IF NOT EXISTS**, kết quả sau retry có thể là false vì lần trước đã thành công. Phải so trạng thái nghiệp vụ thay vì tự báo xung đột.
- Không coi **consistency level thấp** là chữa mọi lỗi timeout. Nếu yêu cầu nghiệp vụ là LOCAL_QUORUM, hạ xuống LOCAL_ONE có thể làm kết quả trả về không đáp ứng hợp đồng.

### 12.2. Execution profile và timeout server khác nhau

Driver có một **request timeout** phía client. Cassandra còn có timeout và guardrails phía server. Khi điều chỉnh profile để tăng thời gian chờ, hãy đo:

- Request p95/p99 và tail latency của dịch vụ.
- Lỗi server-side ReadTimeout/WriteTimeout so với client-side timeout.
- Số request đang bay, hàng đợi driver, số retry và tải coordinator/replica.
- Khả năng đáp ứng deadline của HTTP/gRPC service gọi Cassandra.

Không đặt client timeout dài hơn deadline nghiệp vụ vô hạn định chỉ để làm giảm số exception quan sát. Một request chậm quá lâu vẫn có thể chiếm tài nguyên và bị caller hủy.

## 13. Ví dụ thiết kế chính sách cho ba endpoint

Giả sử dịch vụ có ba endpoint:

| Endpoint | Access pattern | Regular CL | Serial CL | Profile gợi ý |
|---|---|---|---|---|
| **GET /events/recent** | Một partition **(tenant_id, event_day)**, dữ liệu có thể hơi trễ | LOCAL_ONE nếu nghiệp vụ cho phép | Không cần | default/fast-read |
| **GET /orders/{id}** | Một partition **(tenant_id, order_id)**, trạng thái quan trọng | LOCAL_QUORUM | Không cần | important-read |
| **POST /orders** | **INSERT ... IF NOT EXISTS** theo một order | LOCAL_QUORUM | LOCAL_SERIAL hoặc SERIAL tùy yêu cầu đa DC | conditional-write |

Bảng chỉ minh họa một lựa chọn **phải được kiểm chứng theo topology, RF và cam kết nghiệp vụ**. Với order creation phân tán đa DC, SERIAL/LOCAL_SERIAL phải đánh giá theo invariant toàn cầu; **LOCAL_SERIAL không mặc nhiên đúng** cho mọi tổ chức.

### 13.1. Một thiết kế dễ sai

Ứng dụng đặt mặc định **LOCAL_ONE** cho mọi request rồi:

1. Đọc “chưa có order” bằng LOCAL_ONE.
2. Chạy **INSERT** không điều kiện bằng LOCAL_ONE.
3. Giả định chỉ một request trong hai request song song có thể tạo order.

Thiết kế này sai về tính atomic của read-modify-write. Tăng cả đọc và ghi thành LOCAL_QUORUM vẫn **không biến hai bước thành CAS**. Nếu cần điều kiện “chưa tồn tại”, dùng **LWT** hoặc cơ chế uniqueness/idempotency phù hợp.

### 13.2. Một thiết kế quá đắt

Ứng dụng dùng **SERIAL** hoặc LWT cho mọi sự kiện telemetry chỉ để “an toàn”, dù mỗi event đã có ID duy nhất và không có thao tác kiểm tra điều kiện. Khi số request lớn, chi phí Paxos tăng latency và tài nguyên. Nếu nghiệp vụ không cần conditional write, dùng INSERT thông thường với primary key và CL đáp ứng mục tiêu.

## 14. Quan sát và kiểm thử chính sách khi cluster gặp lỗi

### 14.1. Kiểm thử không phá dữ liệu production

Trên staging/lab có topology đại diện:

1. Tạo keyspace/table và fixture theo khóa phân vùng.
2. Xác định RF, DC/rack, SNITCH/topology và nơi driver chọn local DC.
3. Thực hiện cùng query với LOCAL_ONE và LOCAL_QUORUM, đo latency, không chỉ kiểm tra exception.
4. Chạy LWT **IF NOT EXISTS** hai lần với cùng khóa; xác minh [applied] lần đầu/lần sau.
5. Thực hiện hai conditional writes cạnh tranh trong test có kiểm soát; kiểm tra không có hai kết quả **true** cho cùng điều kiện tạo bản ghi.
6. Giả lập một replica chậm hoặc không khả dụng theo phương pháp vận hành được phép; quan sát hiệu ứng lên từng CL.
7. Dùng serial CL theo chính sách và kiểm tra kết quả sau timeout giả lập, đặc biệt idempotency.
8. So profile default, important-read và conditional-write; thử per-statement override để xác nhận precedence.
9. Chạy soak test có đo GC/heap/native, disk, compaction, repair/streaming và retry.
10. Ghi rõ những giới hạn: một lab một node không chứng minh hành vi **RF = 3, multi-DC hay LOCAL_QUORUM** của production.

Không tắt node production, chạy repair bừa bãi hoặc thay RF trực tiếp trong cluster thật để làm bài tập. Dùng môi trường kiểm thử được phê duyệt.

### 14.2. Metric nên theo dõi

| Tầng | Metric / sự kiện | Lý do |
|---|---|---|
| **Ứng dụng Java** | p50/p95/p99 theo endpoint, timeout, error rate | Biết người dùng cảm nhận ra sao |
| **Driver** | CL, profile name, retry count, coordinator/DC, in-flight requests | Phân biệt chính sách và tình trạng driver |
| **Cassandra node** | Read/write latency, timeout/unavailable, pending tasks | Xác định coordinator/replica quá tải |
| **LWT** | Conditional write latency, CAS contention/timeouts, applied true/false | Phân biệt xung đột nghiệp vụ và lỗi hạ tầng |
| **Storage** | SSTable/partition size, tombstone, disk I/O, compaction backlog | Tìm nguyên nhân truy vấn chậm |
| **Cluster** | Node health, schema agreement, RF/DC/rack, repair status | Kiểm tra khả năng phục vụ CL đã chọn |

**Applied=false không phải lỗi server**, nên đừng gộp nó với timeout thành một tỷ lệ lỗi hạ tầng. Tuy nhiên, applied=false tăng bất thường có thể là tín hiệu **contention/idempotency collision** ở tầng nghiệp vụ.

### 14.3. Không log dữ liệu nhạy cảm

Nên lưu **operation name, query shape, CL, serial CL, execution profile name, latency, exception class, retry count và request ID không chứa PII**. Tránh log raw BoundStatement, password, token, customer ID hoặc toàn bộ giá trị từ LWT thất bại.

## 15. Các lỗi cấu hình thường gặp

| Lỗi | Triệu chứng | Cách sửa |
|---|---|---|
| Dùng **LOCAL_QUORUM** với replica local không đủ | Unavailable/timeout | Xác minh RF/DC và node health; phục hồi replica hoặc điều chỉnh lab đúng mục tiêu |
| Đặt **serial CL** rồi tưởng regular CL cũng đổi | Ghi LWT có chính sách khác kỳ vọng | Đặt/kiểm tra **cả** regular và serial CL |
| Dùng LOCAL_SERIAL cho bất biến cần phối hợp đa DC | Kết quả nghiệp vụ không đạt giả định toàn cục | Thiết kế lại phạm vi đồng thuận và chính sách writer |
| Tự viết SELECT + INSERT thay CAS | Hai request cạnh tranh đều tin điều kiện đúng | Dùng IF NOT EXISTS/IF ... hoặc cơ chế uniqueness phù hợp |
| Chỉ nhìn **[applied]** sau retry | False bị hiểu nhầm là tạo thất bại hoàn toàn | Đối soát row/idempotency key khi kết quả lần trước không rõ |
| Set CL nhưng bỏ giá trị return | Request dùng giá trị cũ từ BoundStatement | Gán lại statement immutable |
| Profile đặt tên sai | Driver không tìm được profile như mong muốn | Kiểm tra application.conf, tên profile và effective configuration |
| Nghĩ profile đặt serial CL vì có regular CL | LWT dùng serial policy không được review | Đặt serial CL tường minh và kiểm thử |
| Đổi timeout để che truy vấn chậm | In-flight tăng, SLO vẫn xấu | Phân tích partition, tombstone, compaction, replica |
| Tự giảm CL sau timeout | Dữ liệu đọc/ghi không đáp ứng hợp đồng | Giữ consistency được cam kết, điều tra availability |
| Dùng LWT cho mọi event | CAS contention/latency/CPU tăng | Dùng ghi thường cho thao tác không cần điều kiện |
| Chỉ test trên một replica | Bỏ sót lỗi quorum, multi-DC | Dùng test topology đại diện và failure scenarios |

## 16. Bài tập tình huống

### Bài 1 — Đọc/ghi LOCAL_QUORUM trong RF = 3

Một keyspace có RF = 3 ở dc1. Ứng dụng dùng LOCAL_QUORUM cho đọc và ghi.

**Câu hỏi:** Thông thường cần bao nhiêu replica đáp ứng? Điều kiện R + W > RF có chứng minh transaction nhiều câu lệnh không?

**Đáp án gợi ý:** Cần đa số trong dc1, tức **2/3** cho mỗi loại request. R + W = 4 > 3 tạo phần giao nhau theo mô hình một tập replica, nhưng không cho transaction isolation hoặc compare-and-set cho chuỗi SELECT rồi UPDATE.

### Bài 2 — Lựa chọn regular hay serial CL

Một endpoint tạo đơn hàng bằng **INSERT ... IF NOT EXISTS**. Lập trình viên chỉ viết:

~~~java
BoundStatement b = prepared.bind(tenantId, orderId, "NEW", createdAt, 0)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
~~~

**Câu hỏi:** Câu lệnh thiếu thông tin chính sách nào nếu đội muốn review tường minh pha đồng thuận?

**Đáp án gợi ý:** Cần chỉ định **serial consistency** thích hợp, như **LOCAL_SERIAL** hoặc **SERIAL** tùy yêu cầu đa DC, bằng **setSerialConsistencyLevel**. Regular CL không tự mô tả toàn bộ chính sách LWT.

### Bài 3 — Execution profile và override

Profile **important-read** đặt LOCAL_QUORUM, một statement sử dụng profile nhưng gọi **setConsistencyLevel(LOCAL_ONE)** sau đó.

**Câu hỏi:** Regular CL của request là gì?

**Đáp án gợi ý:** **LOCAL_ONE**, vì giá trị tường minh của statement override giá trị tương ứng trong profile. Nếu muốn LOCAL_QUORUM từ profile, đừng đặt override trái ý định.

### Bài 4 — False sau timeout LWT

Lần đầu INSERT IF NOT EXISTS bị timeout. Client retry cùng order_id và nhận **[applied] = false**.

**Câu hỏi:** Có thể kết luận order không do request này tạo không?

**Đáp án gợi ý:** Không. Lần đầu có thể đã áp dụng trước khi phản hồi mất. Cần đọc/đối soát row theo khóa, idempotency key và giá trị nghiệp vụ, thay vì sinh order_id mới hoặc trả lỗi xung đột một cách máy móc.

### Bài 5 — Chọn policy cho multi-DC

Một tổ chức có hai datacenter và yêu cầu quy tắc “chỉ một order ID toàn cầu được tạo” khi hai DC có thể nhận request đồng thời.

**Câu hỏi:** LOCAL_SERIAL có mặc nhiên đủ không? Cần kiểm chứng điều gì?

**Đáp án gợi ý:** Không mặc nhiên. Phải xem phạm vi Paxos serial, replication strategy, writers ở từng DC và lựa chọn SERIAL khi cần invariant toàn cục; cần kiểm thử concurrent conditional writes và kịch bản DC mất kết nối.

### Bài 6 — Profile tăng timeout nhưng p99 vẫn xấu

Sau khi tăng **basic.request.timeout** từ 2 giây lên 8 giây trong profile, số timeout phía client giảm nhưng p99 của endpoint và số request inflight tăng.

**Câu hỏi:** Có phải hệ thống đã được tối ưu?

**Đáp án gợi ý:** Chưa. Tăng timeout chỉ cho phép chờ lâu hơn; cần đo disk latency, compaction, tombstone, partition size, replica health, retry và deadline ứng dụng. Chỉ giữ cấu hình mới nếu đáp ứng SLO và không gây quá tải.

### Bài 7 — Câu lệnh đọc thiếu khóa phân vùng

Một bảng có PRIMARY KEY **((tenant_id, event_day), happened_at, event_id)**. Ứng dụng chỉ truyền tenant_id và kỳ vọng dùng LOCAL_QUORUM để đọc “toàn bộ ngày”.

**Câu hỏi:** CL có giải quyết thiếu event_day không?

**Đáp án gợi ý:** Không. CQL phải đáp ứng quy tắc primary key; thiết kế API lấy từng bucket ngày hoặc xây bảng khác theo access pattern. CL chỉ điều khiển điều kiện phản hồi replica.

### Bài 8 — Correctness khi retry

Một thao tác counter increment bị timeout và driver tính đến retry. Một developer nói “mình chỉ đổi profile sang LOCAL_QUORUM thì retry an toàn”.

**Câu hỏi:** Sai ở đâu?

**Đáp án gợi ý:** CL không biến increment thành idempotent. Kết quả timeout có thể không xác định và retry có thể cộng thêm lần nữa. Cần thiết kế chống trùng, event model hoặc phương án nghiệp vụ phù hợp.

## 17. Checklist triển khai với Java Driver 4.x

- [ ] Đã xác định **RF, local datacenter và chính sách topology** của từng keyspace liên quan.
- [ ] Đã phân loại endpoint theo yêu cầu **đọc/ghi thông thường** và **LWT có điều kiện**.
- [ ] Regular CL được chọn theo SLO/availability/correctness, không vì tên nghe “mạnh nhất”.
- [ ] LWT có **serial CL được review riêng**, đặc biệt khi ứng dụng ghi từ nhiều DC.
- [ ] Không nhầm SERIAL/LOCAL_SERIAL với regular CL; không dùng LWT khi không cần điều kiện.
- [ ] Bảng CQL được thiết kế theo truy vấn và statement bind đủ partition key.
- [ ] CqlSession/PreparedStatement được tái sử dụng; BoundStatement immutable được gán giá trị mới.
- [ ] Execution profile có tên dễ hiểu, chứa các default cần thiết và được test khi override.
- [ ] Đã kiểm tra **tên profile, effective configuration, precedence** giữa profile và statement.
- [ ] Timeout driver và timeout server được phân biệt; retry policy có giới hạn/backpressure.
- [ ] Có xử lý **[applied] = false**, timeout/unknown outcome và idempotency key của LWT.
- [ ] Kiểm thử concurrency, multi-DC invariant, replica lỗi và retry theo topology tương ứng.
- [ ] Metrics có latency, CL/profile, LWT contention, errors, compaction/repair và node health.
- [ ] Không log credential, raw bind values, khách hàng hoặc payload nhạy cảm.
- [ ] Đã kiểm chứng TLS/auth, phiên bản driver/server và recovery/backup khi rollout cấu hình mới.

## 18. Tổng kết

**Consistency level** quy định điều kiện phản hồi của replica cho thao tác đọc/ghi Cassandra; **serial consistency** là chính sách riêng cho pha đồng thuận của **LWT**. Trong Java Driver 4.x, **execution profile** giúp gom những giá trị mặc định như CL, timeout và page size cho từng nhóm request, còn statement có thể override những thuộc tính cần kiểm soát riêng.

Không có một CL tối ưu cho mọi truy vấn. Phải bắt đầu từ **partition key, mô hình dữ liệu, replication/DC, SLA và invariant nghiệp vụ**. Với conditional write, kiểm tra **[applied]**, xử lý outcome không xác định sau timeout và giữ idempotency. Với profile, hiểu rõ cấu hình hiệu lực và precedence để tránh request vô tình chạy với chính sách khác ý định. Cuối cùng, đo độ trễ, lỗi, tính đúng đắn và tải nền **compaction/repair** trên topology đại diện trước khi đưa quyết định cấu hình vào production.
