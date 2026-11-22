# Đưa dữ liệu sang tìm kiếm hoặc phân tích với tiến độ đồng bộ rõ ràng

## 1. Bài toán: một nguồn dữ liệu, nhiều cách đọc

Apache Cassandra phù hợp với những luồng ghi lớn, phân tán qua nhiều nút và truy xuất đã biết trước khóa phân vùng. Một bảng Cassandra thường được thiết kế **theo truy vấn**: chọn partition key và clustering columns sao cho ứng dụng đọc đúng partition, tránh quét bảng hoặc lọc tùy ý. Đây là một lợi thế cho API nghiệp vụ, nhưng không tự động đáp ứng:

- **Tìm kiếm:** tra cứu toàn văn, xếp hạng theo độ liên quan, lọc kết hợp nhiều thuộc tính hoặc autocomplete.
- **Phân tích:** tổng hợp dữ liệu trên nhiều khách hàng, đối chiếu theo thời gian, tính chỉ số và chạy truy vấn ad hoc trên tập dữ liệu lớn.

Ví dụ, một dịch vụ đơn hàng lưu đơn trong Cassandra và đọc bằng cặp (tenant_id, order_id). Nhân viên hỗ trợ lại muốn tìm đơn theo từ khóa, trạng thái, địa chỉ giao hàng; bộ phận phân tích muốn biết doanh thu theo ngày và khu vực. Nếu liên tục thêm bảng Cassandra cho mọi tổ hợp bộ lọc hoặc dùng truy vấn quét toàn cụm, độ phức tạp vận hành và chi phí đọc sẽ tăng nhanh.

Giải pháp thường là duy trì **Cassandra làm nguồn dữ liệu nghiệp vụ**, đồng bộ bản chiếu (projection) sang hệ thống phù hợp với từng kiểu truy vấn:

| Nhu cầu | Hệ đích ví dụ | Mô hình dữ liệu tại đích |
| --- | --- | --- |
| Tìm kiếm văn bản, lọc, sắp xếp | OpenSearch/Elasticsearch | Một document cho mỗi thực thể; chỉ lập chỉ mục các trường cần tìm |
| Báo cáo, BI, tổng hợp | ClickHouse, kho dữ liệu hoặc data lake | Bảng sự kiện/bảng fact, bảng chiều hoặc bản chụp trạng thái hiện tại |
| Truy xuất giao dịch theo ID | Cassandra | Bảng theo partition key và truy vấn nghiệp vụ xác định trước |

**Đồng bộ không có nghĩa là mọi hệ trả cùng kết quả tại mọi thời điểm.** Cần thiết kế rõ độ trễ cho phép (freshness), cách chuyển tiếp thay đổi, quy tắc xử lý sai lệch, trạng thái tiến độ và quy trình hồi phục.

### Tiêu chí hoàn thành cần thống nhất từ đầu

Một pipeline được coi là vận hành được khi trả lời được năm câu hỏi:

1. **Đang đồng bộ gì?** Bảng nguồn, phạm vi tenant, phiên bản schema, loại sự kiện và các trường được phép xuất.
2. **Đã đồng bộ đến đâu?** Phần dữ liệu lịch sử đã quét, vị trí luồng thay đổi đã xử lý và phần nào thực sự được hệ đích xác nhận.
3. **Dữ liệu mới trễ bao lâu?** Độ trễ đầu cuối và ngưỡng chấp nhận cho từng hệ đích.
4. **Lỗi rồi chạy lại có an toàn không?** Có idempotency, xử lý phiên bản cũ và checkpoint bền vững hay không.
5. **Làm sao phát hiện thất lạc?** Có đối soát, cảnh báo, cơ chế replay và rebuild hay không.

## 2. Kiến trúc tham chiếu

~~~mermaid
flowchart LR
    APP["Ứng dụng Java"] --> CAS[("Cassandra: dữ liệu nghiệp vụ")]
    CAS -->|"Đọc lịch sử theo token range"| BF["Backfill có checkpoint"]
    CAS -->|"CDC từ commit log"| CDC["CDC connector / agent"]
    CDC --> BUS[("Luồng sự kiện bền vững")]
    BF --> NORM["Chuẩn hóa sự kiện và phiên bản"]
    BUS --> NORM
    NORM --> SEARCH["Consumer tìm kiếm"]
    NORM --> ANALYTICS["Consumer phân tích"]
    SEARCH --> OS[("Search index")]
    ANALYTICS --> WH[("Kho phân tích")]
    SEARCH --> CS[("Checkpoint tìm kiếm")]
    ANALYTICS --> CA[("Checkpoint phân tích")]
    CS --> MON["Theo dõi lag, lỗi, tiến độ"]
    CA --> MON
~~~

Ở đây **backfill** nạp dữ liệu hiện có; **Change Data Capture (CDC)** chuyển tiếp cập nhật sau đó. Dòng sự kiện bền vững, ví dụ một topic Kafka, giúp tách tốc độ ghi Cassandra khỏi khả năng xử lý của từng hệ đích. Mỗi consumer có checkpoint riêng: tìm kiếm đã theo kịp không chứng minh kho phân tích cũng đã theo kịp.

Sơ đồ là **kiến trúc logic**. CDC của Cassandra đọc thay đổi từ cơ chế commit log thông qua connector/agent phù hợp với phiên bản và môi trường vận hành; nó không phải một topic CDC tự sinh ra khi chỉ bật một cờ trong bảng. Nếu tổ chức chọn mô hình sự kiện làm nguồn sự thật, ứng dụng có thể ghi vào event log bền vững trước, sau đó nhiều consumer lần lượt dựng Cassandra, search index và kho phân tích. Mô hình đó cần thiết kế lại luồng ghi và quyền sở hữu dữ liệu.

### Vì sao không ghi song song trực tiếp từ Java?

Đoạn xử lý “ghi Cassandra thành công, sau đó gọi API lập chỉ mục” tồn tại cửa sổ lỗi: tiến trình chết giữa hai lần ghi sẽ làm Cassandra và search khác nhau. Đảo thứ tự hai thao tác chỉ đổi phía có nguy cơ thất lạc; retry còn có thể sinh bản ghi trùng. Cassandra cũng không cung cấp transaction ACID xuyên Cassandra và search engine.

Các hướng đáng tin cậy hơn gồm: CDC được vận hành có kiểm soát; event log bền vững làm nguồn sự thật; hoặc outbox có cơ chế đảm bảo ghi sự kiện cùng với thay đổi nghiệp vụ **đúng theo giới hạn giao dịch thực tế**. Không được mặc định rằng hai ghi đến hai partition Cassandra hoặc đến hai hệ thống khác nhau là một transaction nguyên tử.

## 3. Chuẩn bị dữ liệu nguồn và contract

Giả sử API lấy đơn bằng tenant và ID:

~~~sql
CREATE TABLE orders_by_id (
    tenant_id uuid,
    order_id uuid,
    customer_id uuid,
    status text,
    total_amount decimal,
    updated_at timestamp,
    change_version bigint,
    is_deleted boolean,
    PRIMARY KEY ((tenant_id, order_id))
) WITH cdc = true;
~~~

Mỗi đơn là một partition. Truy vấn nghiệp vụ sử dụng đầy đủ partition key:

~~~sql
SELECT order_id, customer_id, status, total_amount, updated_at
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
~~~

Đây là **schema minh họa**, không phải thiết kế duy nhất cho mọi hệ thống đơn hàng. Chọn khóa phân vùng cần xét lưu lượng, kích thước partition, chiến lược tenant và các truy vấn thật. Bật **cdc = true** trên bảng chỉ là một phần cấu hình; cluster còn cần hỗ trợ và cấu hình CDC, dung lượng đĩa, agent đọc, theo dõi backlog và quy trình xử lý khi CDC ngừng nhận dữ liệu.

Định nghĩa một contract sự kiện trung gian:

~~~json
{
  "event_id": "a1b2c3-example",
  "entity_type": "order",
  "entity_key": "tenant-17/order-932",
  "operation": "UPSERT",
  "version": 104,
  "occurred_at": "2026-11-21T08:20:00Z",
  "source_position": {
    "stream": "order-changes",
    "partition": 3,
    "offset": 18720
  },
  "payload": {
    "tenant_id": "tenant-17",
    "order_id": "order-932",
    "status": "PAID",
    "total_amount": "125000.00"
  }
}
~~~

Các ID và giá trị JSON chỉ để minh họa; ứng dụng thực tế cần dùng định dạng tương thích với UUID/CQL. Contract phải chỉ rõ:

- **entity_key:** khóa ổn định ở mọi hệ; với đa tenant, luôn bao gồm tenant_id để tránh đè document giữa các tenant.
- **operation:** UPSERT, DELETE và nếu cần các loại thay đổi khác.
- **version:** thứ tự tăng đơn điệu **theo từng thực thể**, do cơ chế ghi nguồn đáng tin cậy tạo ra. updated_at theo đồng hồ ứng dụng không mặc nhiên là version an toàn khi nhiều writer chạy đồng thời.
- **event_id:** định danh phục vụ phát hiện lặp và truy vết.
- **source_position:** vị trí stream dùng checkpoint/replay. Offset chỉ so sánh trong **cùng partition**, không phải số thứ tự toàn cục.
- **schema_version** (nếu áp dụng): hỗ trợ đổi định dạng payload mà consumer cũ vẫn phân biệt được.

CDC có thể chứa **mutation của các cột**, không nhất thiết là ảnh đầy đủ của cả hàng sau mỗi update. Connector hoặc tầng chuẩn hóa phải biết cách ghép trạng thái hiện tại, lấy lại từ Cassandra khi phù hợp, hoặc phát các domain event chứa đầy đủ thông tin cần cho projection. Khi lấy lại từ nguồn, phải kiểm soát trường hợp một update khác đã xảy ra giữa lúc nhận event và lúc đọc hàng.

**Version phải được bảo đảm bằng thiết kế**, chẳng hạn single writer cho mỗi entity, bộ tuần tự hóa theo entity trước khi phát stream, hoặc cập nhật có điều kiện/LWT cho phiên bản tại Cassandra nếu tải và độ trễ cho phép. Không tự suy ra thứ tự chính xác từ timestamp hoặc offset của các CDC agent khác nhau.

## 4. Chọn cách đưa thay đổi ra khỏi Cassandra

| Cách tiếp cận | Khi phù hợp | Điểm phải giải quyết |
| --- | --- | --- |
| CDC từ commit log | Cần bắt các mutation đã đi qua Cassandra và giảm sửa đổi vào luồng ghi ứng dụng | Triển khai connector theo phiên bản; xử lý duplicate, partial update, delete/TTL, backlog, lưu giữ và recovery |
| Event log là nguồn sự thật | Chủ động thiết kế lại luồng ghi; nhiều consumer cần cùng lịch sử sự kiện | Ghi và sắp thứ tự sự kiện, dựng projection Cassandra, idempotency và dữ liệu tồn tại trước khi áp dụng |
| Outbox do ứng dụng quản lý | Ứng dụng sở hữu nghiệp vụ và có cơ chế ghi outbox đáng tin cậy | Chứng minh tính nguyên tử đúng với storage và partition; có relay, retry, dọn outbox |
| Quét định kỳ | Bài toán nhỏ, chấp nhận độ trễ lớn, chưa có luồng thay đổi | Quét tốn tài nguyên; khó phát hiện delete/TTL; phải đối soát đầy đủ |

### Các giới hạn quan trọng của CDC

1. CDC gắn với commit log và nút Cassandra. Việc thu thập từ nhiều replica/nút có thể sinh sự kiện trùng và thay đổi thứ tự khi quan sát; connector phải có chiến lược chuẩn hóa.
2. Bộ đệm CDC và đĩa là hữu hạn. Nếu pipeline đọc không kịp, tùy phiên bản/cấu hình, áp lực lên vùng CDC có thể ảnh hưởng khả năng ghi vào bảng đã bật CDC. Cần cảnh báo sớm, tính toán lưu giữ và kịch bản mất kết nối.
3. **TTL hết hạn không đồng nghĩa có một sự kiện DELETE phát đúng lúc hết hạn.** Một giá trị có TTL có thể tự hết hiệu lực mà không có mutation mới ở thời điểm hết hạn. Nếu hệ đích cần xóa chính xác, hãy truyền thời điểm hết hạn vào document để hệ đích xử lý, phát sự kiện hết hạn từ nghiệp vụ, hoặc chạy đối soát/dọn dẹp định kỳ.
4. Một lệnh DELETE có thể tạo tombstone; consumer phải chuyển thành xóa/ẩn đối tượng ở hệ đích. Phải tính cả DELETE cấp cột, hàng, partition nếu schema cho phép, không chỉ xử lý INSERT/UPDATE.
5. CDC không thay thế sao lưu, snapshot hay một nhật ký lịch sử vô hạn. Quy trình recovery phải biết rõ khoảng dữ liệu có thể replay và phải khởi tạo lại nếu vượt quá thời gian lưu giữ.

## 5. Kết hợp nạp lịch sử (backfill) với luồng thay đổi

Đây là phần dễ sai nhất. Nếu quét các hàng đang tồn tại rồi **mới** bắt CDC, những update hoặc delete xảy ra trong lúc quét có thể biến mất khỏi hệ đích.

Một quy trình triển khai an toàn hơn:

1. **Khởi động thu nhận CDC** và bảo đảm có nơi lưu bền vững các sự kiện. Ghi nhận tập vị trí bắt đầu theo từng stream/partition. Xác minh thời gian lưu giữ sự kiện đủ bao phủ toàn bộ backfill và phần dự phòng khi sự cố.
2. **Chia backfill thành token ranges** và kiểm soát số luồng quét, page size, tốc độ đọc. Cassandra được tối ưu cho truy vấn có partition key; quét toàn bộ nhiều token range vẫn tốn I/O/CPU và có thể ảnh hưởng tải sản xuất.
3. **Xuất từng hàng thành UPSERT có version**, đưa qua cùng logic idempotency của consumer hoặc một luồng backfill riêng đã thống nhất cách hòa trộn với live events.
4. **Ghi checkpoint backfill sau khi dữ liệu được hệ đích xác nhận**; lưu range và khóa/vị trí an toàn để tiếp tục, cho phép đọc lặp vùng cuối sau restart.
5. **Phát và áp dụng backlog CDC**, giữ thứ tự theo entity, bỏ qua sự kiện cũ so với version đã áp dụng. Không áp dụng một ảnh chụp cũ lên trên phiên bản mới hơn.
6. **Đối soát phạm vi và số lượng**, chỉ chuyển sang trạng thái “đã bắt kịp” khi mọi range hoàn tất và mọi CDC partition đã vượt qua mốc mục tiêu được chụp cho lần đánh giá đó.

~~~mermaid
sequenceDiagram
    participant S as Cassandra
    participant B as Backfill
    participant E as CDC/Event log
    participant T as Search/Analytics
    Note over E: Bắt đầu giữ sự kiện tại vị trí C0
    S-->>E: version 12: cập nhật đơn X
    S-->>B: Bản quét đơn X (version 11 hoặc 12)
    B->>T: UPSERT X từ backfill
    E->>T: UPSERT X version 12
    Note over T: Chỉ giữ version cao nhất
    S-->>E: version 13: xóa đơn X
    E->>T: DELETE X version 13
    Note over T: Lưu dấu xóa/version để chống hồi sinh
~~~

**Không mặc định backfill là snapshot nhất quán tại một thời điểm.** Một lượt quét Cassandra thông thường có thể thấy nhiều thời điểm khác nhau trên các partition. Quy tắc version và đối soát giúp xử lý các thay đổi chen vào; khi không có version đủ tin cậy, cần cơ chế cắt mốc/ghép luồng mạnh hơn hoặc quy trình rebuild có khóa/kiểm chứng bổ sung.

Checkpoint quét bằng paging state chỉ nên dùng nếu hiểu rõ giới hạn vòng đời và khả năng khôi phục của driver. Với job dài ngày, nên thiết kế đơn vị công việc là token range nhỏ và checkpoint các phần đã hoàn tất hoặc khóa cuối đã áp dụng; sau lỗi, chấp nhận quét lại phần chưa xác nhận vì consumer idempotent.

### Khi cần rebuild toàn bộ chỉ mục

Nên dựng **index phiên bản mới**, nạp lịch sử, theo kịp các thay đổi, kiểm chứng số lượng/mẫu dữ liệu rồi chuyển alias truy vấn sang index mới. Không xóa ngay index cũ trước khi kiểm chứng. Kho phân tích có thể dùng partition/table staging tương tự, tùy khả năng atomic swap của engine.

## 6. Chống trùng lặp, sai thứ tự và xóa nhầm

Trong hệ phân tán, **at-least-once** thường là mô hình thực tế: consumer xử lý lại event khi timeout, crash trước khi commit offset hoặc khi replay. Vì vậy sink phải idempotent.

Với mỗi entity, dùng quy tắc logic:

~~~text
handle(event):
    key = event.entity_key
    current = sink_state.get(key)

    if current exists and event.version < current.version:
        return ACK_OLD_EVENT
    if current exists and event.version == current.version:
        if same_semantic_event(current, event):
            return ACK_DUPLICATE
        return CONFLICT_REQUIRES_INVESTIGATION

    if event.operation == DELETE:
        persist_tombstone(key, event.version)
        remove_or_hide_document(key)
    else:
        upsert_projection(key, event.payload, event.version)

    return ACK_AFTER_DURABLE_SINK_SUCCESS
~~~

Đây là **pseudocode mô tả tính đúng đắn**, không phải transaction có sẵn trong mọi search engine. Kiểm tra version và ghi trạng thái mới cần đủ nguyên tử để hai consumer/worker đồng thời không làm một event cũ ghi đè event mới. Có thể dùng kiểm soát version có điều kiện của sink hoặc một state store giao dịch cùng pipeline. Nếu có cạnh tranh ghi, logic “đọc version rồi ghi” rời rạc chưa đủ.

Lưu ý đặc biệt với DELETE: một số search engine chỉ giữ tombstone/version của document đã xóa trong thời gian hữu hạn. Replay một UPSERT rất cũ sau khi dấu xóa hết hạn có nguy cơ “hồi sinh” document. Với yêu cầu nghiêm ngặt, lưu **phiên bản xóa bền vững** trong projection/state store, hoặc thể hiện bản ghi bị xóa bằng trạng thái ẩn có version, cho đến khi chắc chắn mọi event cũ đã hết khả năng replay.

Khóa phân vùng Kafka theo entity_key thường giúp duy trì thứ tự các event cùng thực thể **trên một luồng sản xuất đã tuần tự hóa**. Nó không tự sửa được tình trạng nhiều CDC replica phát các mutation lệch thứ tự trước khi vào Kafka. Bảo vệ bằng version và kiểm chứng xung đột vẫn cần thiết.

## 7. Định nghĩa tiến độ đồng bộ có thể kiểm chứng

Hiển thị “đã xử lý 100%” chỉ dựa trên số hàng quét là chưa đủ. Pipeline có ít nhất **hai chiều tiến độ khác nhau**: lịch sử đã backfill đến đâu và luồng thay đổi đã apply đến đâu. Mỗi hệ đích lại có tiến độ riêng.

### 7.1. Checkpoint gồm những gì?

Một record kiểm soát tiến độ có thể lưu:

~~~json
{
  "pipeline": "orders-to-search",
  "target": "search-v4",
  "phase": "CATCHING_UP",
  "backfill": {
    "completed_ranges": 238,
    "total_ranges": 256,
    "active_range": "range-239",
    "last_durable_key": "opaque-resume-key"
  },
  "stream": {
    "topic": "order-changes",
    "partition": 3,
    "committed_offset": 18720,
    "observed_head_offset": 18960
  },
  "last_sink_ack_at": "2026-11-21T08:20:10Z",
  "error_count": 0
}
~~~

Ví dụ này chỉ hiển thị **một partition**. Trong triển khai thực, phải có offset/checkpoint của **tất cả partition và tất cả token range** thuộc phạm vi job, kèm phiên bản job, snapshot/cutover marker và loại hệ đích. Không có một offset Kafka duy nhất biểu diễn tiến độ toàn topic; càng không có một offset chung cho nhiều agent CDC/nút Cassandra.

Các trạng thái nên được định nghĩa rõ:

| Trạng thái | Điều kiện có thể xác minh |
| --- | --- |
| INITIALIZING | Connector, mapping/schema, quyền truy cập và điểm bắt đầu CDC được chuẩn bị |
| BACKFILLING | Còn token range chưa xác nhận apply vào sink |
| CATCHING_UP | Backfill hoàn tất; đang xử lý backlog CDC đến mốc đích |
| LIVE | Backfill hoàn tất và lag nằm trong SLO trong một khoảng quan sát |
| DEGRADED | Pipeline còn chạy nhưng lag, lỗi hoặc tỉ lệ retry vượt ngưỡng |
| BLOCKED | Thiếu nguồn sự kiện, hết retention, lỗi schema/credential hoặc sink không tiếp nhận được |
| REBUILDING | Đang dựng projection mới, chưa thể tuyên bố nó đã sẵn sàng phục vụ |

### 7.2. Quy tắc ghi nhận thành công

**Chỉ tiến checkpoint sau khi sink xác nhận các thao tác tương ứng đã thành công bền vững theo hợp đồng của sink.** Nếu batch gồm 100 document mà 2 document bị từ chối, không được commit offset vượt qua 2 document ấy rồi coi là hoàn thành. Có thể retry, lưu tiến độ chi tiết và xử lý DLQ, nhưng phải giữ khả năng replay đúng chỗ.

Ví dụ Kafka consumer:

~~~text
poll records from partition P
validate and transform each record
apply to target using idempotent writes
verify each item/bulk result (including partial failures)
persist target-specific checkpoint / commit only safe offset
on crash: replay from last safe offset
~~~

Nếu checkpoint và sink là hai hệ thống khác nhau, crash ở giữa có thể khiến event xử lý lại. Chính idempotency và version guard làm replay an toàn. Ghi checkpoint trước khi sink xác nhận có thể tạo **mất dữ liệu không tự hồi phục**.

Một số search engine trả ACK khi ghi index nhưng document chưa xuất hiện ngay trong kết quả search do chu kỳ refresh. Vì vậy cần đo thêm **search-visible latency** bằng truy vấn kiểm chứng; không đánh đồng ACK ghi thành công với “người dùng đã tìm thấy”.

### 7.3. Đọc đúng chỉ số lag

| Chỉ số | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| Backfill coverage | Số token range hoàn tất / tổng range | Tỉ lệ range không đồng nghĩa tỉ lệ số hàng; range có thể không đều |
| Stream offset lag | Head offset − committed offset theo từng partition | Phải xem max/sum theo cách có giải thích, không so offset giữa các partition |
| End-to-end freshness | Thời điểm đọc thấy dữ liệu ở đích − thời điểm thay đổi nguồn | Dùng đồng hồ có đồng bộ, xét skew và event đến muộn |
| Last successful apply | Lần gần nhất đích xác nhận ghi | Nếu đầu vào không có event, giá trị cũ không tự chứng minh pipeline hỏng |
| Retry/DLQ count | Số bản ghi gặp lỗi tạm thời/vĩnh viễn | DLQ khác 0 có thể đồng nghĩa chưa hoàn tất về mặt dữ liệu |
| Reconciliation mismatch | Số khóa/số bản ghi lệch trong mẫu hoặc phạm vi so sánh | Bổ sung kiểm chứng ngoài offset |
| CDC disk/backlog | Áp lực lên agent, queue, đĩa và retention | Phát hiện nguy cơ mất sự kiện trước khi hết cửa sổ replay |

Với dashboard, nên công khai mốc đánh giá cụ thể: “Backfill 256/256 ranges; toàn bộ 12 partitions của stream đã apply ít nhất tới head chụp lúc 10:00:00 UTC; p95 freshness 8 giây; 0 bản ghi pending DLQ”. Đây là khẳng định có phạm vi và thời điểm, khác với nhãn mơ hồ “synchronized”.

## 8. Hai hệ đích, hai kiểu projection

### 8.1. Index tìm kiếm

Một document có thể chứa khóa nghiệp vụ, thuộc tính lọc, chuỗi cần tìm, version và trạng thái xóa. ID document nên được tạo ổn định, ví dụ từ (tenant_id, order_id). Consumer có thể cập nhật theo ID đó, dùng version guard để không cho bản ghi cũ ghi đè.

Thiết kế mapping cần xác định trước:

- Trường nào cần full-text, trường nào phải là keyword để lọc và tổng hợp chính xác.
- Cách token hóa tiếng Việt, stemming, chuẩn hóa dấu/ký tự và thử nghiệm chất lượng tìm kiếm.
- Chính sách thay đổi mapping/index version, alias và thời điểm chuyển sang index mới.
- Dữ liệu nhạy cảm nào **không được** mang sang chỉ mục; phân quyền tenant khi truy vấn.

API có thể đọc kết quả search để lấy danh sách ID, rồi đọc bản ghi nghiệp vụ hiện hành từ Cassandra khi yêu cầu độ chính xác cao hoặc cần kiểm tra phân quyền lần cuối. Cách này cũng giảm ảnh hưởng của một document tìm kiếm đã hơi cũ, nhưng làm tăng số lần đọc và cần hạn chế N+1 queries.

### 8.2. Kho phân tích

Phải chọn rõ **ngữ nghĩa bảng đích**:

- **Current-state table:** mỗi order có một hàng hiện tại, dùng UPSERT có version và xóa khi cần.
- **Event fact table:** mỗi lần đổi trạng thái là một sự kiện độc lập, có event_id để chống đúp; dùng cho câu hỏi “đơn đổi trạng thái lúc nào”.
- **Daily/hourly aggregate:** bảng tổng hợp phát sinh từ fact; cần quy tắc cập nhật/recompute khi có sự kiện đến muộn.

Không trộn lẫn hai khái niệm: nếu chỉ đồng bộ ảnh hiện tại của hàng Cassandra thì không thể tự suy ra **lịch sử thay đổi** trước khi CDC được kích hoạt. Với báo cáo theo ngày, phải xác định timezone nghiệp vụ, cửa sổ chốt số liệu và cách sửa số liệu muộn (late arrival/retractions).

Pipeline tìm kiếm và pipeline phân tích có thể độc lập về tốc độ, mapping, offset và cơ chế khôi phục. Một đích bị chậm không nên ép mất sự kiện ở đích còn lại.

## 9. Nhất quán Cassandra và độ mới của projection

Cassandra sao chép dữ liệu giữa replica theo replication factor và chính sách nhất quán đọc/ghi. Ứng dụng Java thường chọn consistency level phù hợp như LOCAL_QUORUM để đánh đổi độ trễ, tính sẵn sàng và khả năng đọc lại bản ghi vừa ghi trong một datacenter; các bảo đảm cụ thể phụ thuộc replication factor, topology và điều kiện lỗi.

Nhưng **LOCAL_QUORUM ở Cassandra không biến search engine thành một bản sao đồng bộ theo transaction**. Sau khi API trả thành công, vẫn có các giai đoạn: mutation được CDC quan sát, event đến queue, consumer apply, search index refresh và cache truy vấn hết hạn.

Mô tả rõ yêu cầu nhất quán ở phía người dùng:

| Thao tác | Cách đáp ứng tham khảo |
| --- | --- |
| Màn hình chi tiết đơn ngay sau khi lưu | Đọc Cassandra theo ID; không bắt buộc đợi search |
| Bộ lọc/tìm kiếm danh sách | Chấp nhận eventual consistency có SLO, ví dụ p95 thấy thay đổi trong 10 giây |
| Nút “tìm ngay đơn vừa tạo” | Dùng ID trả về để đọc Cassandra hoặc có cơ chế đợi/read-your-writes riêng |
| Báo cáo cuối ngày | Chốt mốc nguồn, chờ pipeline theo kịp mốc, đối soát rồi công bố số liệu |

Các giá trị SLO trong bảng chỉ là **ví dụ**; phải đo thực tế trên hạ tầng và tải của hệ thống. Khi dùng nhiều datacenter, cần làm rõ CDC được lấy từ DC/replica nào và ranh giới consistency đối với dữ liệu đang lan truyền liên vùng.

## 10. Xử lý sự cố và phục hồi

| Tình huống | Dấu hiệu | Cách phục hồi an toàn |
| --- | --- | --- |
| Consumer chết giữa batch | Offset không tăng, retry tăng | Restart từ checkpoint bền vững; deduplicate/version guard khi apply lại |
| Hệ tìm kiếm quá tải/429 | Lag tăng, bulk partial failure | Retry có backoff và giới hạn tốc độ; không commit qua record thất bại |
| Event không hợp schema | Poison message, DLQ tăng | Cách ly event, cảnh báo, sửa parser/mapping rồi replay; không lặng lẽ coi là xong |
| CDC agent tụt quá retention | Khoảng offset/segment không còn đọc được | Đánh dấu BLOCKED, xác định khoảng mất và chạy rebuild/đối soát từ nguồn |
| Backfill bị dừng | Còn ranges chưa hoàn thành | Quét lại range dang dở, áp version guard và tiếp tục CDC đã giữ lại |
| DELETE hoặc TTL chưa phản ánh | Document “ma”, chênh lệch đối soát | Phát delete nghiệp vụ, kiểm tra TTL theo expire_at hoặc reconciliation và dọn |
| Sink nhận sự kiện sai thứ tự | Version giảm/xung đột | Bỏ event cũ hoặc điều tra nguồn version; tránh chấp nhận last-write-wins bằng thời gian máy |
| Thay đổi mapping/schema | Index lỗi ghi, trường mới không tìm được | Dùng schema contract, index version mới và quy trình cutover có kiểm chứng |

Khi phát hiện sự cố, cần biết **mốc nguồn cuối cùng đã lưu giữ, mốc consumer cuối cùng đã apply, thời gian đầu tiên có lỗi và các entity bị ảnh hưởng**. Không xóa queue, bỏ qua offset hoặc “đánh dấu xanh” để giảm cảnh báo khi chưa có kế hoạch bù dữ liệu.

### Đối soát định kỳ

Ngay cả khi offset đã theo kịp, vẫn cần kiểm chứng dữ liệu. Có thể chia theo tenant, bucket thời gian hoặc token range; so số hàng đang hiệu lực, tổng kiểm có quy tắc chuẩn hóa, lấy mẫu khóa và phiên bản rồi đối chiếu với sink. Đếm tổng đơn giản chưa đủ để phát hiện hai lỗi bù trừ nhau. Cần tính cả dữ liệu xóa và TTL; xác định rõ thời điểm chốt so sánh để tránh báo sai do cập nhật đồng thời.

Đối với search, chạy các query canary theo những ID/term đã biết sau khi index refresh. Đối với phân tích, kiểm thử tổng hợp chuẩn trên một ngày đã đóng và dữ liệu được sửa muộn. Mismatch phải dẫn đến repair theo khóa/phạm vi hoặc rebuild, kèm log có thể kiểm toán.

## 11. Kết nối từ ứng dụng Java và ranh giới trách nhiệm

Ứng dụng Java có thể dùng DataStax/Apache Cassandra Java Driver tương thích với phiên bản cluster để thực hiện truy vấn CQL bằng prepared statement, gắn consistency level theo nhu cầu và đặt timeout/retry hợp lý. Trách nhiệm nghiệp vụ là bảo đảm bản ghi nguồn có khóa, version và dữ liệu cần thiết; **không đặt tính đúng đắn của đồng bộ vào một lời gọi HTTP thứ hai không có phục hồi**.

Một ví dụ khái niệm:

~~~java
PreparedStatement selectOrder = session.prepare(
    "SELECT status, total_amount, change_version " +
    "FROM orders_by_id WHERE tenant_id = ? AND order_id = ?");

BoundStatement query = selectOrder.bind(tenantId, orderId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

Row row = session.execute(query).one();
~~~

Mã trên là **đọc trực tiếp Cassandra theo partition key**, không phải consumer CDC hoàn chỉnh. Session cần được quản lý vòng đời ở tầng ứng dụng; các thư viện, import và API cụ thể phải chọn theo driver thực tế. Nếu muốn đảm bảo tăng change_version với nhiều writer, cần cơ chế tuần tự hóa/CAS phù hợp, chấp nhận chi phí Paxos/LWT và xử lý cạnh tranh phiên bản; không lấy giờ hệ thống làm một thứ tự tuyệt đối.

Trách nhiệm nên phân định rõ: service sở hữu model nghiệp vụ và dữ liệu nguồn; CDC/stream platform chịu trách nhiệm giao sự kiện và retention; consumer tìm kiếm/analytics chịu trách nhiệm projection, idempotency và checkpoint **riêng**; vận hành chịu trách nhiệm cảnh báo, đối soát và kế hoạch rebuild.

## 12. Ví dụ diễn tiến từ ghi đến truy vấn

Giả sử đơn X vừa được tạo với version 41, sau đó chuyển sang PAID version 42 rồi bị hủy version 43:

| Thời điểm | Cassandra | Stream nhận được | Trạng thái search hợp lệ |
| --- | --- | --- | --- |
| T0 | X = NEW, v41 | UPSERT v41 | X = NEW, v41 |
| T1 | X = PAID, v42 | UPSERT v42 | X = PAID, v42 |
| T2 | X bị xóa/hủy, v43 | DELETE v43 | X bị ẩn/xóa, lưu v43 |
| T3 | Không có thay đổi | Replay UPSERT v41 | Vẫn bị ẩn/xóa, v43 |

Nếu một backfill cũ gửi X = NEW v41 sau T2, version guard phải từ chối nó. Nếu v42 đến trước v41, hệ đích giữ v42. Nếu hai sự kiện cùng version nhưng payload khác nhau, đó là **xung đột contract** cần điều tra, không phải duplicate an toàn.

Ví dụ báo cáo tiến độ lúc 10:00 UTC:

~~~text
Pipeline: orders-to-search
Backfill: 256/256 ranges applied
CDC: 12/12 partitions applied through captured 09:59:55 head
Worst consumer lag: 250 records (partition 7)
p95 end-to-end freshness: 7.2 seconds
Failed records awaiting replay: 0
State: LIVE (SLO <= 15 seconds)
~~~

Trạng thái LIVE ở đây hợp lệ vì tiêu chí SLO đã định nghĩa, **không có nghĩa dữ liệu ở search hoàn toàn đồng bộ tức thời**. Khi người dùng yêu cầu dữ liệu tới đúng 10:00:00, hệ thống phải chụp mốc mới và chờ các partition đạt mốc đó; nếu không thì công bố thời điểm mới nhất được bảo đảm.

## 13. Kịch bản kiểm thử trước khi đưa vào vận hành

1. **Backfill có ghi đồng thời:** cập nhật một hàng nhiều lần và xóa trong lúc quét; hệ đích cuối cùng phải giống phiên bản mới nhất hợp lệ.
2. **Replay và duplicate:** phát lại cùng event_id/offset sau khi sink đã ACK; số document/fact không tăng sai và version không lùi.
3. **Out-of-order:** đưa v12 đến trước v11, rồi DELETE v13 trước một UPSERT cũ; không hồi sinh dữ liệu.
4. **Crash giữa ghi sink và commit checkpoint:** restart không làm mất record, dù xử lý lặp.
5. **Bulk partial failure:** một phần batch bị từ chối; offset chỉ tiến qua vùng đã xử lý an toàn.
6. **CDC thiếu dữ liệu hoặc mất retention:** pipeline hiển thị BLOCKED, có quy trình rebuild và xác nhận lại độ phủ.
7. **TTL/delete:** kiểm chứng document hết hạn/xóa biến mất theo SLO định nghĩa.
8. **Tải lớn:** đo áp lực scan lên Cassandra, dung lượng CDC, offset lag, refresh/search latency và throughput của sink.
9. **Đối soát:** cố ý làm sai hoặc bỏ một document và chắc chắn job đối soát phát hiện, sửa lại được.
10. **Tenant và quyền:** không xuất trường nhạy cảm trái chính sách, không để truy vấn tenant A thấy dữ liệu tenant B.

Chỉ số đạt phải được định lượng theo hệ thống: thời gian nhận biết sự cố, thời gian bắt kịp tối đa, độ trễ p95/p99, tỷ lệ bản ghi lỗi, thời gian tối đa được phép ngừng pipeline trước khi hết CDC retention và độ lệch được phép khi chốt báo cáo.

## 14. Checklist thiết kế trước khi triển khai

Trước khi xây dựng, trả lời được các câu sau:

- Bảng Cassandra nào là nguồn sự thật? Partition key có cho phép nạp lịch sử theo token ranges mà không làm quá tải cluster?
- Event đến từ CDC, event-first hay outbox? Ai chịu trách nhiệm giữ dữ liệu khi sink ngừng hoạt động?
- Event có khóa ổn định, version tăng đúng theo thực thể, thông tin DELETE/TTL và schema version chưa?
- Đã định nghĩa cách chống trùng, xử lý sai thứ tự và giữ tombstone/version để replay không làm dữ liệu hồi sinh chưa?
- Backfill bắt đầu sau khi đảm bảo CDC giữ đầy đủ thay đổi chưa? Có đủ retention và checkpoint từng range/partition chưa?
- Checkpoint chỉ được tiến sau ACK của đích chưa? Bulk partial error, DLQ và replay có đường xử lý rõ ràng chưa?
- Dashboard có tách **backfill coverage**, **stream progress**, **freshness**, **search visibility** và **reconciliation** chưa?
- Có SLO riêng cho tìm kiếm và phân tích, chiến lược báo cáo theo mốc dữ liệu và kịch bản rebuild an toàn chưa?

**Nguyên tắc cốt lõi:** với Cassandra, bảng được thiết kế theo truy vấn nghiệp vụ; search engine và kho phân tích là các projection phục vụ cách đọc khác. Chất lượng kiến trúc phụ thuộc vào khả năng truyền thay đổi an toàn, áp dụng idempotent, theo dõi tiến độ đã được đích xác nhận và phát hiện/khôi phục những khác biệt còn lại.
