# Ảnh hưởng của thay đổi RF đến dữ liệu đã tồn tại trong Apache Cassandra

> **Chương:** Token và sao chép  
> **Trọng tâm:** Khi thay đổi replication factor (RF) của một keyspace, các bản sao của dữ liệu cũ được giữ, bổ sung hoặc dọn dẹp như thế nào; cách chuyển đổi an toàn và kiểm chứng kết quả.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao đổi RF thay đổi **tập replica được chỉ định** nhưng không tự động di chuyển toàn bộ dữ liệu đã ghi trước đó.
2. Phân biệt quy trình **tăng RF: full repair** và **giảm RF: cleanup**, cùng ảnh hưởng lên độ sẵn sàng, độ bền dữ liệu và dung lượng đĩa.
3. Nhận diện nguy cơ đọc thiếu dữ liệu trong giai đoạn chuyển tiếp, đặc biệt khi dùng mức nhất quán ONE hoặc LOCAL_ONE.
4. Đọc cấu hình keyspace, xác định replica của một partition và lên kế hoạch thực hiện thao tác trên từng node/DC.
5. Giải thích tác động tới ứng dụng Java sử dụng Cassandra driver và lựa chọn consistency level phù hợp.

Phạm vi ví dụ là **Apache Cassandra dùng các bản sao đầy đủ (full replicas)** với NetworkTopologyStrategy. Transient replication, chuyển đổi snitch, thay token hoặc thay topology đồng thời là những tình huống cần quy trình riêng.

## 2. RF chi phối điều gì?

Cassandra chia không gian khóa bằng **token**. Partition key được băm thành token; chiến lược replication của keyspace chọn các node chịu trách nhiệm lưu bản sao của mỗi khoảng token. Tập node được chọn gọi là **natural replicas**.

- **Replication factor (RF)** là số bản sao mục tiêu cho một khoảng token; với NetworkTopologyStrategy, cấu hình được tính riêng cho từng datacenter (DC).
- **Replication strategy** quyết định replica được chọn từ những node/rack nào.
- **Consistency level (CL)** quyết định số phản hồi cần thiết cho mỗi thao tác đọc/ghi; CL không tự tạo ra dữ liệu còn thiếu trên replica.
- **Repair** đối chiếu dữ liệu giữa các replica và truyền phần chênh lệch; **cleanup** dọn dữ liệu của những token range mà node không còn chịu trách nhiệm lưu.

Ví dụ keyspace có cấu hình:

~~~sql
CREATE KEYSPACE learning_events
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '2',
  'dc2': '2'
}
AND durable_writes = true;
~~~

RF ở đây là **2 trong dc1 và 2 trong dc2** cho mỗi khoảng token, không phải RF bằng 2 cho toàn cluster. Với topology phù hợp, mỗi partition có tổng cộng 4 bản sao đầy đủ, phân bổ trên hai DC. RF là thuộc tính của **keyspace**, nên đổi RF ảnh hưởng đến tất cả bảng trong keyspace đó.

> Trong hệ thống production, nên dùng NetworkTopologyStrategy và đúng tên DC do cluster khai báo. SimpleStrategy không xét bố trí datacenter, không phù hợp với nhiều triển khai thực tế.

### Metadata và bản sao vật lý là hai trạng thái khác nhau

Lệnh ALTER KEYSPACE cập nhật **quy tắc đặt bản sao**. Sau khi schema được các node thống nhất, coordinator sẽ dùng quy tắc mới để định tuyến đọc/ghi. Tuy nhiên, những SSTable ghi trước đó không được tự động sao chép hoặc xóa toàn bộ chỉ nhờ lệnh ALTER.

Hãy phân biệt:

| Thành phần | Sau khi tăng RF | Sau khi giảm RF |
|---|---|---|
| Metadata của keyspace | Chỉ định thêm replica cho các token range | Chỉ định ít replica hơn |
| Ghi mới, sau khi schema thống nhất | Hướng tới tập replica mới | Hướng tới tập replica mới |
| Dữ liệu đã tồn tại | Có thể **chưa có** trên replica vừa được thêm | Có thể **vẫn còn** trên node không còn là replica |
| Việc vận hành cần làm | **Full repair** để chuyển dữ liệu cũ đến các replica cần thiết | **Cleanup** để thu hồi dữ liệu dư |
| Nguy cơ chủ đạo | Đọc thiếu dữ liệu cũ; thiếu bản sao thực tế; tải mạng/đĩa khi repair | Giảm dự phòng nếu cấu hình RF quá thấp; dữ liệu dư chiếm dung lượng trước cleanup |

Quá trình chuyển đổi có **khoảng thời gian chưa hội tụ** giữa metadata và dữ liệu vật lý. Thao tác ALTER thành công chưa chứng minh việc phân phối các bản sao cũ đã hoàn tất.

## 3. Tăng RF: dữ liệu cũ chưa tự xuất hiện ở replica mới

Giả sử một DC có bốn node N1, N2, N3, N4 và một partition P. Minh họa đơn giản hóa: trước khi đổi RF, natural replicas của P là N1 và N2.

~~~text
Trước: RF = 2
P ──> N1 [có P]
  └─> N2 [có P]
      N3 [chưa được chỉ định]
      N4

Sau ALTER: RF = 3, trước full repair
P ──> N1 [có P]
  ├─> N2 [có P]
  └─> N3 [được chỉ định nhưng có thể chưa có P]
      N4

Sau full repair thành công
P ──> N1 [có P]
  ├─> N2 [có P]
  └─> N3 [đã nhận P]
~~~

Đây chỉ là hình minh họa cho một partition; replica thực tế phụ thuộc token ring, chiến lược replication và bố trí rack. Không thể suy ra rằng N3 luôn là replica mới của mọi partition.

### Điều gì xảy ra với đọc và ghi?

**Ghi sau khi đổi RF.** Khi các node đã nhận schema mới, coordinator chọn tập replica theo RF mới. Một bản ghi mới có thể đi tới N1, N2, N3. Điều này **không sửa các bản ghi cũ** trên N3. Nếu node gặp lỗi trong lúc ghi, hinted handoff chỉ hỗ trợ một số lần ghi bị bỏ lỡ; đó không phải giải pháp sao chép dữ liệu lịch sử khi đổi RF.

**Đọc trước khi repair.** Coordinator cũng có thể hỏi N3 theo metadata mới. Nếu N3 chưa có partition P, đọc với ONE/LOCAL_ONE có thể nhận kết quả rỗng dù P vẫn tồn tại trên N1 và N2. Đây là một nguy cơ nghiêm trọng khi RF thay đổi trên keyspace đang hoạt động.

**Đọc với QUORUM/LOCAL_QUORUM không phải thuốc chữa cho mọi trường hợp.** Với ví dụ RF 2 → 3, LOCAL_QUORUM trong dc1 yêu cầu hai phản hồi; trong ba replica mới, hai phản hồi bất kỳ phải giao với ít nhất một trong hai replica cũ, nếu tập replica đúng như hình. Nhưng nếu chuyển **RF 1 → 3**, hai replica mới cùng chưa có dữ liệu vẫn có thể tạo thành hai phản hồi; LOCAL_QUORUM không bảo đảm đọc được lịch sử. Mức ALL liên hệ tới tất cả replica và có thể giúp đọc từ một bản sao cũ nếu còn sẵn sàng, nhưng đánh đổi rất lớn về độ sẵn sàng. Vì vậy cần **phân tích tập replica cũ/mới, mức CL và tình trạng node**, rồi ưu tiên hoàn thành full repair sớm.

Số phản hồi cần cho quorum trong một DC với full replicas:

| RF trong DC | LOCAL_ONE | LOCAL_QUORUM |
|---:|---:|---:|
| 1 | 1 | 1 |
| 2 | 1 | 2 |
| 3 | 1 | 2 |
| 4 | 1 | 3 |

Chỉ số phản hồi là **điều kiện nhất quán của thao tác**, không phải bằng chứng mọi replica thực sự đã lưu dữ liệu. Với cluster nhiều DC, QUORUM theo tổng RF khác với LOCAL_QUORUM theo RF của DC cục bộ; **ALL** yêu cầu tất cả replica trên các DC, không có mức nhất quán tên LOCAL_ALL.

### Vì sao bắt buộc full repair?

~~~bash
nodetool repair --full learning_events
~~~

Repair so sánh các replica của các token range liên quan (thông qua Merkle tree) rồi stream phần dữ liệu còn thiếu. **Full repair** xem xét toàn bộ dữ liệu của range; **incremental repair** mặc định có thể bỏ qua dữ liệu đã được đánh dấu repaired trước đó. Vì thế chỉ chạy lệnh repair mặc định, hoặc chỉ trông chờ hinted handoff/read repair, là chưa đủ khi tăng RF.

Trong quy trình quét **toàn cluster**, một cách thường dùng là chạy trên **từng node của từng DC**, theo lịch điều phối để tránh chồng tải:

~~~bash
# Thực hiện lần lượt trên từng node/DC;
# -pr giới hạn vào primary token ranges của node này.
nodetool repair --full -pr learning_events
~~~

Mỗi lần gọi nodetool chỉ sửa những range thuộc phạm vi node/lệnh đó; một lần chạy trên một node **không** tương đương full repair toàn cluster. Chỉ tuyên bố hoàn tất khi toàn bộ range cần thiết đã được repair thành công, trên các node/DC liên quan. Với môi trường lớn, dùng lịch sửa chữa có giám sát, kiểm soát đồng thời và dung lượng trống.

### Chi phí khi tăng RF

- **Dung lượng:** tổng lượng bản sao mục tiêu tăng xấp xỉ theo RF cho dữ liệu được phân phối ở DC đó. Ví dụ RF 2 → 3 tương ứng khoảng 50% dung lượng bản sao nhiều hơn trong DC xét riêng, trước khi tính overhead, nén, tombstone, index và chênh lệch phân phối.
- **Mạng:** full repair có thể truyền đáng kể dữ liệu giữa các replica, đặc biệt khi tăng RF ở DC khác.
- **CPU và đĩa:** xây Merkle tree, đọc SSTable, stream dữ liệu và compaction có thể ảnh hưởng độ trễ truy vấn.
- **Rủi ro chuyển tiếp:** trước khi repair hoàn tất, số **replica được cấu hình** có thể lớn hơn số **replica đang chứa dữ liệu cũ**.

Không đặt RF lớn hơn số node đủ điều kiện trong DC. Số rack, phân bố node và tình trạng node cũng ảnh hưởng khả năng chịu lỗi thực tế; chỉ đếm số node là chưa đủ để bảo đảm phân tán lỗi.

## 4. Giảm RF: bản sao dư vẫn chiếm đĩa

Giả sử cùng partition P đang có ba replica N1, N2, N3 và RF trong dc1 giảm từ 3 xuống 2:

~~~text
Trước: RF = 3
P ──> N1 [có P]
  ├─> N2 [có P]
  └─> N3 [có P]

Sau ALTER: RF = 2, trước cleanup
P ──> N1 [replica được chỉ định]
  └─> N2 [replica được chỉ định]
      N3 [có thể vẫn giữ bản sao cũ, không còn là replica]

Sau cleanup trên những node liên quan
P ──> N1 [replica được chỉ định]
  └─> N2 [replica được chỉ định]
      N3 [dữ liệu không còn thuộc trách nhiệm đã được dọn]
~~~

Việc giảm RF có hiệu lực với **tập replica mục tiêu** sau khi schema thống nhất. Cassandra không mặc nhiên xóa hết các SSTable dư ngay tại thời điểm ALTER. Các bản sao không còn được định tuyến có thể tiếp tục chiếm không gian đĩa.

Để dọn dữ liệu không còn được node sở hữu:

~~~bash
# Chạy theo lịch trên từng node có dữ liệu thuộc keyspace.
nodetool cleanup learning_events
~~~

Cleanup là thao tác **theo từng node**. Nó loại bỏ các phần dữ liệu của token range mà node không còn phải lưu theo topology/replication hiện hành. Không nên coi cleanup là một kiểu full repair: cleanup **không xây thêm bản sao bị thiếu**.

Nếu chỉ giảm RF và không thay đổi topology/strategy, không có nhu cầu tăng số bản sao như trường hợp tăng RF. Tuy nhiên, phải chắc rằng các replica **còn được giữ lại** có dữ liệu nhất quán và khỏe mạnh trước khi giảm khả năng dự phòng. Nếu đồng thời chuyển DC, thay snitch, bootstrap/decommission node hoặc đổi strategy, cần kế hoạch migration riêng; không suy ra quy trình từ ví dụ giản lược này.

### Điều gì thay đổi về độ bền và mức nhất quán?

- RF 3 chịu lỗi một replica tốt hơn RF 2; giảm RF là **giảm ngân sách chịu lỗi**, dù dữ liệu dư vẫn tạm nằm trên đĩa.
- Với RF 3, LOCAL_QUORUM cần 2 phản hồi; với RF 2, LOCAL_QUORUM cũng cần 2 phản hồi, nghĩa là việc mất một replica sẽ khiến thao tác LOCAL_QUORUM không thể hoàn thành tại DC đó.
- Những bản sao nằm ngoài tập natural replicas **không được tính** là dự phòng hợp lệ cho yêu cầu mới. Không nên dựa vào chúng để phục hồi hoặc duy trì ứng dụng.
- Dung lượng không nhất thiết giảm ngay hoặc đúng tuyến tính sau cleanup vì snapshots, compaction, tombstones và dữ liệu của các keyspace khác.

Trước khi hạ RF, xem lại SLA, backup, mức CL của ứng dụng, tình trạng repair và các lỗi node gần đây. Đừng hạ RF chỉ để giải quyết tình trạng đĩa sắp đầy khi cluster đang mất replica hoặc có dữ liệu chưa đồng bộ.

## 5. Ví dụ CQL đầy đủ với hai datacenter

Giả sử cluster dùng các DC tên chính xác là dc1 và dc2. Keyspace ban đầu:

~~~sql
DESCRIBE KEYSPACE learning_events;

-- Cấu hình mong đợi trước khi đổi:
-- {'class':'NetworkTopologyStrategy','dc1':'2','dc2':'2'}
~~~

### Kịch bản A: tăng RF ở dc1 từ 2 lên 3

~~~sql
ALTER KEYSPACE learning_events
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '3',
  'dc2': '2'
};

DESCRIBE KEYSPACE learning_events;
~~~

Điều cần hiểu:

1. dc1 bắt đầu chỉ định thêm replica theo token ring; **dữ liệu cũ ở dc1 chưa tự được copy đủ**.
2. dc2 vẫn có RF bằng 2 vì ta **giữ nguyên** cấu hình của dc2 trong câu ALTER.
3. Sau schema agreement, lên lịch full repair bao phủ tất cả range bị ảnh hưởng và kiểm tra kết quả; không lấy việc DESCRIBE hiển thị RF 3 làm dấu hiệu hoàn tất.

### Kịch bản B: sau khi đã hội tụ, giảm RF ở dc1 từ 3 về 2

~~~sql
ALTER KEYSPACE learning_events
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '2',
  'dc2': '2'
};

DESCRIBE KEYSPACE learning_events;
~~~

Sau đó, dọn bản sao dư bằng cleanup trên những node liên quan theo quy trình vận hành. Không bỏ trường dc2 khỏi cấu hình một cách vô tình; với NetworkTopologyStrategy, ý nghĩa các tùy chọn và hành vi cập nhật mặc định phụ thuộc phiên bản, nên hãy **khai báo rõ đầy đủ các DC cần giữ** và kiểm tra cấu hình sau ALTER.

> **Lưu ý:** Trong Cassandra hiện đại, một số cách khai báo RF có thể dùng cú pháp mở rộng tự động theo DC. Khi thay đổi keyspace production, cấu hình rõ RF của từng DC giúp dễ review hơn. Không copy tên dc1/dc2 nếu cluster của bạn dùng tên khác.

## 6. Runbook thay đổi RF trên cluster đang phục vụ lưu lượng

### Bước 1: xác nhận trạng thái trước khi đổi

Kiểm tra những điểm sau:

| Hạng mục | Câu hỏi vận hành |
|---|---|
| Mục tiêu | Tăng khả năng chịu lỗi, mở thêm DC, hay giảm chi phí lưu trữ? |
| Topology | Mỗi DC có đủ node/rack để đáp ứng RF mới không? |
| Sức khỏe | Tất cả node liên quan có ở trạng thái Up/Normal? Có node đang bootstrap/leave? |
| Dữ liệu | Repair trước đó có lỗi? Có tombstone tồn đọng, backup/snapshot khôi phục được? |
| Dung lượng | Đủ disk/network headroom cho bản sao tăng thêm và repair/cleanup? |
| Ứng dụng | Java driver đang dùng LOCAL_ONE, LOCAL_QUORUM, QUORUM hay mức khác? |
| Rollback | Nếu tăng RF phải quay lại, có kế hoạch cleanup; nếu giảm RF phải tăng lại, có kế hoạch full repair? |

Các lệnh tham khảo, thực hiện trên môi trường đã có quyền vận hành:

~~~bash
nodetool status
nodetool describecluster
~~~

Trong cqlsh:

~~~sql
DESCRIBE KEYSPACE learning_events;
CONSISTENCY;
~~~

Kiểm tra consistency của **ứng dụng** từ cấu hình driver, vì mức được hiển thị trong cqlsh chỉ là mức của phiên cqlsh đó. Với một partition key cụ thể, lệnh sau giúp kiểm tra **những endpoint được chỉ định**:

~~~bash
# Ví dụ bảng có partition key là tenant_id kiểu text
nodetool getendpoints learning_events events tenant_a
~~~

Lệnh getendpoints cho biết **vị trí dự kiến**, không chứng minh dữ liệu đã thực sự hiện diện trên ổ đĩa của endpoint.

### Bước 2: thay đổi metadata một cách có kiểm soát

Ghi lại cấu hình cũ, thực hiện ALTER KEYSPACE, xác nhận schema agreement giữa các node và chạy lại DESCRIBE để chắc rằng RF từng DC đúng mục tiêu. Trong thời gian metadata đang lan truyền, chú ý lỗi schema hoặc truy vấn điều phối qua các node chưa nhất quán.

### Bước 3A: nếu tăng RF, lập tức triển khai full repair

Chạy full repair cho keyspace, **bao phủ tất cả range/DC cần thiết**. Có thể dùng --full cùng -pr trên **từng node**, lần lượt và có điều phối. Theo dõi thông báo hoàn thành, lỗi streaming, mức sử dụng disk, network throughput, read/write latency và mức tải compaction. Không chạy nhiều job nặng đồng thời khi chưa đánh giá khả năng chịu tải.

~~~bash
# Cú pháp mẫu trên từng node theo lịch điều phối:
nodetool repair --full -pr learning_events

# Tham khảo hoạt động stream tại thời điểm kiểm tra:
nodetool netstats
~~~

Tùy phiên bản, tham số và công cụ điều phối repair có thể khác; đọc help đúng phiên bản đang chạy trước khi áp dụng cho production. Một job báo success không có nghĩa các node khác đã hoàn tất.

### Bước 3B: nếu giảm RF, cleanup bản sao dư

Sau khi xác nhận những replica còn lại đủ khỏe và dữ liệu đã đồng bộ, chạy cleanup trên các node phù hợp, theo lịch để tránh tranh chấp disk I/O:

~~~bash
nodetool cleanup learning_events
~~~

Theo dõi disk, compaction và không gian còn lại. Nếu có snapshot giữ SSTable, dung lượng hệ thống file có thể không giảm như mong đợi dù cleanup thành công.

### Bước 4: xác minh sau thay đổi

Không dừng ở một câu SELECT trả đúng bản ghi. Tối thiểu:

1. DESCRIBE cho thấy RF đúng trên từng DC; schema đã thống nhất.
2. Các node/rack mong đợi còn Up/Normal; không có replica mới bị thiếu hay lỗi liên tục.
3. Repair hoặc cleanup kết thúc thành công **trên toàn phạm vi dự kiến**.
4. Đọc tập khóa mẫu đã tồn tại trước khi đổi RF, bao gồm các partition/token range khác nhau; so sánh với dữ liệu gốc hoặc kiểm kê ứng dụng.
5. Giám sát lỗi đọc/ghi, timeout/unavailable, độ trễ, disk, streaming và repair metrics sau thay đổi.
6. Xác nhận backup và lịch repair định kỳ vẫn phù hợp với RF, workload và gc_grace_seconds.

Các kết quả phải được ghi lại theo **node, DC, thời điểm, phiên bản Cassandra, lệnh và trạng thái**, để người tiếp quản biết toàn bộ phạm vi đã hoàn tất.

## 7. Ảnh hưởng đến mức nhất quán và ứng dụng Java

Với các replica đầy đủ, số phản hồi cần cho consistency level phụ thuộc RF. Trong một DC, LOCAL_QUORUM yêu cầu ⌊RF_DC / 2⌋ + 1 replica; LOCAL_ONE yêu cầu một. Tăng RF từ 2 lên 3 vẫn cần 2 phản hồi cho LOCAL_QUORUM, nhưng giảm từ 3 xuống 2 làm mất khả năng tiếp tục đạt LOCAL_QUORUM nếu một trong hai replica xuống.

Khi phân tích quan hệ đọc/ghi, công thức thường dùng là **R + W > RF** để có phần giao giữa tập phản hồi đọc và ghi, *nếu dữ liệu và replica đã hội tụ và các giả định liên quan đúng*. Công thức này không sửa được dữ liệu lịch sử chưa được stream sau khi đổi RF, không bảo đảm tuyến tính cho mọi trường hợp Cassandra, và không thay thế repair.

Ví dụ với Java Driver 4.x, cấu hình consistency trên từng statement:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

public final class EventReader {
    // Session được tạo sẵn bởi ứng dụng, với local datacenter phù hợp.
    public static String findPayload(
            CqlSession session, String tenantId, int eventId) {
        SimpleStatement query = SimpleStatement.builder(
                "SELECT payload FROM rf_lab.events " +
                "WHERE tenant_id = ? AND event_id = ?")
            .addPositionalValues(tenantId, eventId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .build();

        Row row = session.execute(query).one();
        return row == null ? null : row.getString("payload");
    }
}
~~~

**Lưu ý về mẫu Java:** Hàm nhận một CqlSession hợp lệ đã được ứng dụng tạo và tái sử dụng theo vòng đời, không tạo/đóng session cho từng truy vấn. Ví dụ áp dụng cho bảng rf_lab.events ở bài thực hành; tên DC và mức CL phải được chọn theo topology thật.

Mức CL của Java driver **không tự thay đổi khi RF đổi**. Sau khi tăng/giảm RF, phải rà soát cấu hình CL mặc định, override theo statement, timeout, retry policy, khả năng chịu lỗi và chọn local DC của driver. Trong giai đoạn chuyển tiếp, tránh thao tác kiểm tra bằng LOCAL_ONE rồi kết luận dữ liệu bị mất nếu full repair chưa hoàn tất; ngược lại, không coi việc đọc đúng một số khóa là bằng chứng đã đồng bộ toàn bộ token range.

## 8. Những nhầm lẫn thường gây sự cố

| Nhầm lẫn | Điều đúng cần nhớ |
|---|---|
| “ALTER KEYSPACE thành công nghĩa là mọi dữ liệu cũ đã có RF mới.” | ALTER đổi quy tắc định vị replica; **tăng RF phải full repair** dữ liệu cũ. |
| “Incremental repair mặc định là đủ sau khi tăng RF.” | Full repair cần thiết vì dữ liệu đã đánh dấu repaired có thể bị bỏ qua bởi incremental repair. |
| “Hinted handoff hoặc read repair sẽ tự cân bằng mọi partition.” | Các cơ chế này không bảo đảm truyền toàn bộ dữ liệu lịch sử tới replica mới. |
| “SELECT trả đúng vài bản ghi nghĩa là mọi token range đã ổn.” | Cần xác minh kết quả repair theo phạm vi và kiểm tra nhiều partition. |
| “Giảm RF giúp giải phóng đĩa ngay.” | Bản sao dư có thể còn trên đĩa cho đến khi cleanup; snapshot cũng có thể giữ dung lượng. |
| “Cleanup và compaction sẽ sửa thiếu replica sau khi tăng RF.” | Cleanup xóa dữ liệu ngoài ownership; compaction tổ chức dữ liệu cục bộ; **repair** mới đồng bộ replica. |
| “RF = 3 trong hai DC nghĩa là ba bản sao tổng cộng.” | Với NetworkTopologyStrategy, RF được đặt riêng theo từng DC, ví dụ dc1=3, dc2=2 là mục tiêu 5 bản sao. |
| “Đọc QUORUM lúc chuyển đổi luôn an toàn.” | Phải xét RF cũ, RF mới và giao của tập replica; RF 1 → 3 là phản ví dụ. |

### Tombstone và nguy cơ dữ liệu đã xóa xuất hiện lại

Cassandra dùng tombstone để biểu thị xóa. Nếu một replica bỏ lỡ tombstone, dữ liệu cũ trên node đó có thể trở thành vấn đề khi tombstone trên các replica khác đã bị loại sau thời gian grace và compaction. Thay đổi RF giữa giai đoạn chưa hội tụ khiến việc theo dõi tình trạng các bản sao càng quan trọng. Giữ lịch repair phù hợp với gc_grace_seconds và không tự ý giảm grace period để giải phóng đĩa nhanh.

## 9. Bài thực hành có kiểm soát

**Điều kiện:** cluster lab có ít nhất ba node hoạt động trong dc1, đủ tài nguyên; thay thế tên DC nếu khác. Không chạy thử trên keyspace production. Bài này kiểm tra thay đổi RF của **dữ liệu đã tồn tại**, không chỉ dữ liệu ghi mới.

**Chuẩn bị:**

~~~sql
CREATE KEYSPACE rf_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '2'
};

CREATE TABLE rf_lab.events (
  tenant_id text,
  event_id int,
  payload text,
  PRIMARY KEY ((tenant_id), event_id)
);

INSERT INTO rf_lab.events (tenant_id, event_id, payload)
VALUES ('team_a', 1, 'before-rf-change');

INSERT INTO rf_lab.events (tenant_id, event_id, payload)
VALUES ('team_b', 2, 'also-before-rf-change');

SELECT * FROM rf_lab.events WHERE tenant_id = 'team_a';
~~~

**Quan sát RF trước và sau ALTER:**

~~~bash
nodetool status
nodetool getendpoints rf_lab events team_a
~~~

~~~sql
ALTER KEYSPACE rf_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '3'
};

DESCRIBE KEYSPACE rf_lab;
~~~

Chạy lại getendpoints cho team_a và team_b để quan sát tập replica **được chỉ định**. Ghi nhận rằng thay đổi endpoint chưa chứng minh dữ liệu cũ đã được stream. Sau đó thực hiện full repair theo lịch trên tất cả node liên quan:

~~~bash
nodetool repair --full -pr rf_lab
~~~

Kiểm tra log/success của mọi node đã chạy, đọc lại hai partition và đo mức tải. Khi đã xác nhận full repair hội tụ, thử giảm RF về 2:

~~~sql
ALTER KEYSPACE rf_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '2'
};
~~~

Tiến hành cleanup theo node trong lab rồi kiểm tra lại getendpoints, dung lượng và read success. Câu hỏi tự kiểm tra:

1. Nếu ALTER từ RF 2 lên 3 đã xong nhưng full repair chưa chạy, vì sao truy vấn với ONE có thể trả rỗng?
2. Tại sao một lần chạy repair trên một node không đủ khẳng định cluster đã được sửa toàn bộ?
3. Nếu hạ RF 3 xuống 2, vì sao khả năng đáp ứng LOCAL_QUORUM khi một replica chết thay đổi?
4. Tại sao cleanup không thể thay cho full repair khi tăng RF?
5. Nếu DC có hai node mà đặt RF 3, vấn đề nằm ở metadata, số bản sao vật lý hay cả khả năng đáp ứng CL?

**Đáp án định hướng:** (1) replica mới có thể chưa chứa dữ liệu lịch sử; (2) repair chỉ bao phủ phạm vi node/lệnh; (3) với RF 2, quorum cần cả hai; (4) cleanup dọn dữ liệu ngoài ownership, không stream dữ liệu cũ cho replica mới; (5) mục tiêu ba replica độc lập không thể đạt với hai node.

## 10. Ghi nhớ khi vận hành

Việc đổi RF là một **quy trình thay đổi phân bố dữ liệu** qua nhiều bước, không chỉ một câu CQL:

~~~text
Tăng RF:
  Kiểm tra sức khỏe/dung lượng
      -> ALTER KEYSPACE
      -> schema agreement
      -> FULL REPAIR bao phủ toàn cluster liên quan
      -> kiểm chứng dữ liệu + metrics

Giảm RF:
  Kiểm tra độ bền/backup/CL
      -> ALTER KEYSPACE
      -> schema agreement
      -> CLEANUP trên các node liên quan
      -> kiểm chứng dữ liệu + dung lượng + metrics
~~~

Hai nguyên tắc quyết định: **tăng RF cần bổ sung dữ liệu cũ trên replica mới; giảm RF cần dọn bản sao dư và chấp nhận mức chịu lỗi mới**. Kế hoạch kiểm thử, repair, cleanup và giám sát phải xét cả topology, token range, DC, consistency level và những phân vùng đã tồn tại trước khi thay đổi.

## Tài liệu tham khảo

- [Apache Cassandra — Frequently Asked Questions: Can I change the replication factor on a live cluster?](https://cassandra.apache.org/doc/stable/cassandra/overview/faq/index.html)
- [Apache Cassandra — Repair: full vs. incremental, primary range, vận hành repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html)
- [Apache Cassandra — CQL Data Definition: CREATE/ALTER KEYSPACE và NetworkTopologyStrategy](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra — Production recommendations](https://cassandra.apache.org/doc/stable/cassandra/getting-started/production.html)
