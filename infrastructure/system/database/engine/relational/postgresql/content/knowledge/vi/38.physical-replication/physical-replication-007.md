# Lựa chọn synchronous_standby_names và mức xác nhận trong PostgreSQL

## 1. Vì sao phải chọn standby và mức xác nhận?

PostgreSQL hỗ trợ **synchronous streaming replication** để primary chỉ xác nhận một transaction COMMIT sau khi một hoặc nhiều standby đã phản hồi ở mức mà transaction yêu cầu. Cơ chế này giúp giảm nguy cơ mất những transaction đã được xác nhận khi primary gặp sự cố, với điều kiện quá trình failover chọn đúng standby có WAL cần thiết.

Hai cấu hình phối hợp với nhau:

- **`synchronous_standby_names`** xác định standby nào có thể tham gia đồng bộ và primary cần bao nhiêu standby phản hồi. Có hai cách chọn chính: theo ưu tiên `FIRST` và theo quorum `ANY`.
- **`synchronous_commit`** xác định primary phải chờ tới mức nào: standby đã ghi WAL, đã flush WAL xuống storage, hay đã replay WAL để thay đổi có thể được đọc.

Chọn đúng hai tham số này là một quyết định về durability, availability, latency và topology. Chọn mức xác nhận mạnh hơn có thể giảm RPO nhưng làm COMMIT phụ thuộc network và sức khỏe standby. Chọn quorum có thể tăng khả năng tiếp tục commit khi một số standby không sẵn sàng, nhưng yêu cầu hiểu rõ quorum và cách chọn node để promote.

Bài này tập trung vào physical streaming replication trong PostgreSQL. Logical replication có semantics và cấu hình riêng; không áp dụng máy móc các ví dụ synchronous standby bên dưới cho subscriber logical.

### 1.1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích synchronous replication và đường đi của WAL từ primary tới standby.
2. Phân biệt standby được cấu hình, standby đang kết nối và standby đang được chọn đồng bộ.
3. Viết cấu hình `synchronous_standby_names` dùng `FIRST` và `ANY`.
4. Phân biệt priority-based replication với quorum-based replication.
5. Hiểu các mức `synchronous_commit`: `off`, `local`, `remote_write`, `on` và `remote_apply`.
6. Chọn mức xác nhận phù hợp với yêu cầu RPO, RTO và read-after-write.
7. Theo dõi sync state, LSN positions và backend đang chờ `SyncRep`.
8. Xử lý standby disconnect, lag, network partition và synchronous commit stall.
9. Thiết kế topology có đủ standby, failure domains và quy trình promotion an toàn.
10. Thực hành cấu hình, quan sát và chẩn đoán trong môi trường lab.

### 1.2. Các nguyên tắc cần nhớ

- `synchronous_standby_names` chọn **standby participants**; `synchronous_commit` chọn **acknowledgement level** cho transaction.
- Standby được liệt kê trong cấu hình chưa chắc đang là synchronous standby ở thời điểm hiện tại.
- `remote_write`, `on` và `remote_apply` có các mức bảo đảm khác nhau.
- `local` và `off` không chờ synchronous standby phản hồi.
- Synchronous replication có thể làm COMMIT chờ khi không đủ standby đáp ứng quorum/priority set.
- Synchronous replication không tự động thực hiện failover và không thay thế backup/PITR.
- Sau failover, phải promote standby có WAL mới nhất phù hợp với các commits đã được xác nhận; không chỉ chọn node có tên ưu tiên cao nhất.
- Cần kiểm tra cấu hình và trạng thái thực tế bằng system views, logs và diễn tập.

---

## 2. Đường đi của WAL trong synchronous replication

### 2.1. Thành phần

Một topology cơ bản có:

- **Primary:** nhận writes từ ứng dụng, tạo WAL records và gửi WAL qua replication connection.
- **WAL sender:** process trên primary gửi WAL tới standby.
- **Standby:** nhận WAL, ghi/flush vào WAL files và replay để áp dụng changes.
- **WAL receiver:** process trên standby nhận stream từ primary.
- **Synchronous replication wait logic:** primary chờ phản hồi từ số standby được cấu hình trước khi trả kết quả COMMIT theo mức yêu cầu.

### 2.2. Luồng tổng quát

~~~text
Application
    |
    | BEGIN / UPDATE / COMMIT
    v
Primary backend
    |
    +--> Create WAL records
    |
    +--> Local WAL write/flush
    |
    +--> WAL sender streams records
             |
             v
        Standby WAL receiver
             |
             +--> Write WAL
             |
             +--> Flush WAL
             |
             +--> Replay WAL
             |
             +--> Send progress feedback
                      |
                      v
Primary evaluates synchronous_standby_names
                      |
                      v
Commit acknowledgement when requested level is met
~~~

Sơ đồ là mô hình khái niệm. PostgreSQL có thể batch writes, group commit và xử lý nhiều standby đồng thời. Các mốc cụ thể phụ thuộc `synchronous_commit`.

### 2.3. Vì sao primary phải chờ?

Nếu primary xác nhận COMMIT ngay sau local write/flush mà không chờ standby, ứng dụng có thể nhận success trong khi standby chưa có WAL tương ứng. Nếu primary mất và một standby cũ được promote, transaction vừa xác nhận có thể bị mất.

Synchronous replication cho phép primary chờ một mức xác nhận từ standby. Điều này giảm cửa sổ mất dữ liệu khi failover được thực hiện đúng.

### 2.4. Ba giai đoạn phía standby

Có thể phân biệt ba mốc:

1. **Write:** standby đã ghi WAL bytes tới OS/file layer theo semantics của PostgreSQL.
2. **Flush:** standby đã flush WAL tới persistent storage theo sync method/storage stack.
3. **Replay/apply:** standby đã phát lại WAL và áp dụng changes lên data files.

Các mốc này tiến theo thứ tự thông thường, nhưng không đồng nghĩa:
- WAL đã write chưa chắc đã durable qua OS crash/power loss.
- WAL đã flush chưa chắc query trên standby đã thấy transaction vì replay có thể chậm.
- WAL đã replay không tự làm một transaction đang mở với snapshot cũ nhìn thấy changes đó.

### 2.5. Primary nhận phản hồi nào?

Standby gửi feedback về progress của WAL. Primary dùng write/flush/replay positions để quyết định liệu standby đã đạt acknowledgement level của transaction hay chưa.

Không nên dùng một con số lag duy nhất để đại diện mọi thứ. Cần biết đang quan tâm write lag, flush lag hay replay lag.

---

## 3. Hai tham số chính và mối quan hệ

### 3.1. synchronous_standby_names

Tham số này được cấu hình trên primary. Nó liệt kê tên standby và cách chọn số lượng cần phản hồi. Standby name phải khớp với `application_name` của replication connection trên standby.

Ví dụ:

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
~~~

Primary ưu tiên `standby_a`; nếu standby đó không còn eligible/connected, `standby_b` có thể được chọn làm synchronous standby.

### 3.2. synchronous_commit

Tham số này điều khiển transaction cần đợi tới mức acknowledgement nào. Giá trị có thể đặt ở cấp server, session hoặc transaction.

Ví dụ:

~~~sql
SHOW synchronous_commit;

BEGIN;
SET LOCAL synchronous_commit = 'remote_apply';

UPDATE app.orders
SET status = 'paid'
WHERE order_id = 1001;

COMMIT;
~~~

Trong ví dụ, transaction yêu cầu chờ tới khi synchronous standby replay commit record theo semantics của PostgreSQL.

### 3.3. Phân vai

| Tham số | Trả lời câu hỏi |
|---|---|
| `synchronous_standby_names` | Standby nào tham gia và cần bao nhiêu phản hồi? |
| `synchronous_commit` | Transaction phải chờ phản hồi ở mức write, flush hay apply? |

Có thể cấu hình nhiều standby nhưng transaction chỉ yêu cầu local commit; ngược lại có thể đặt `remote_apply` nhưng nếu không có synchronous standby được cấu hình thì không có remote apply acknowledgement để chờ.

### 3.4. Không nhầm với synchronous_commit=on

`synchronous_standby_names` không tự chọn mức commit acknowledgment. `synchronous_commit` mới quyết định mức chờ. Ví dụ, nếu `synchronous_standby_names` đã chọn một standby nhưng transaction đặt `synchronous_commit=local`, transaction đó chỉ chờ local flush.

### 3.5. Cấu hình theo transaction

Các workload khác nhau có thể cần mức xác nhận khác nhau. Một transaction quan trọng có thể yêu cầu `remote_apply`; một tác vụ có thể tái tạo từ nguồn khác có thể dùng mức yếu hơn theo policy.

Dùng `SET LOCAL` bên trong transaction để phạm vi thay đổi chỉ kéo dài trong transaction đó:

~~~sql
BEGIN;
SET LOCAL synchronous_commit = 'on';

INSERT INTO app.payment_ledger(payment_id, amount)
VALUES ('pay-1001', 250.00);

COMMIT;
~~~

Đặt mức yếu hơn phải là quyết định có chủ đích, không nên để connection pool vô tình giữ setting cho request tiếp theo.

---

## 4. synchronous_standby_names: cú pháp và standby names

### 4.1. Cú pháp FIRST

Dạng priority-based:

~~~conf
synchronous_standby_names = 'FIRST num_sync (standby_name [, ...])'
~~~

`num_sync` là số standby mà transaction cần nhận phản hồi. Các tên trong danh sách được sắp theo ưu tiên từ trái sang phải.

Ví dụ:

~~~conf
synchronous_standby_names = 'FIRST 1 (dc1_standby, dc2_standby, dc3_standby)'
~~~

Primary chọn standby đầu tiên đang kết nối và đủ điều kiện theo danh sách. Nếu standby ưu tiên cao hơn mất kết nối, standby kế tiếp có thể được chọn.

### 4.2. Cú pháp ANY

Dạng quorum-based:

~~~conf
synchronous_standby_names = 'ANY num_sync (standby_name [, ...])'
~~~

Ví dụ:

~~~conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
~~~

Primary chờ phản hồi từ bất kỳ hai standby trong danh sách. Các standby trong quorum list có cùng vai trò về ưu tiên; số lượng phản hồi cần thiết là `num_sync`.

### 4.3. Không có FIRST/ANY

Dạng cấu hình truyền thống không ghi keyword `FIRST` được hiểu là priority-based selection:

~~~conf
synchronous_standby_names = '1 (standby_a, standby_b)'
~~~

Có thể viết tường minh `FIRST 1` để người vận hành đọc dễ hơn.

### 4.4. Tên phải khớp application_name

Ví dụ trên standby, replication connection có thể được cấu hình:

~~~conf
primary_conninfo = 'host=primary.example.net port=5432 user=replicator application_name=standby_a'
~~~

Giá trị `application_name=standby_a` phải khớp tên `standby_a` trên primary.

Nếu cấu hình sai tên, standby vẫn có thể streaming nhưng không được chọn làm synchronous standby. Vì vậy kiểm tra `pg_stat_replication.application_name` và `sync_state` thay vì chỉ nhìn connection đã established.

### 4.5. Tên duy nhất và rõ ràng

Nên dùng tên duy nhất cho mỗi standby:
- `dc1_standby_a`
- `dc1_standby_b`
- `dc2_standby_a`

Tránh để nhiều standbys dùng cùng một application_name nếu không có lý do được thiết kế. Tên rõ ràng giúp đọc monitoring, priority và incident logs.

### 4.6. Tham số này nằm ở đâu?

`synchronous_standby_names` được cấu hình trên primary. Nó không được đặt trên standby để standby tự chọn node khác làm synchronous partner.

Có thể kiểm tra:

~~~sql
SHOW synchronous_standby_names;

SELECT
    name,
    setting,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN ('synchronous_standby_names', 'synchronous_commit');
~~~

### 4.7. Số lượng không hợp lệ hoặc không khả thi

Nếu `num_sync` lớn hơn số standby names hoặc lớn hơn số standby có thể kết nối, primary có thể không bao giờ có đủ phản hồi để giải phóng synchronous commit waits. Thiết kế cần có đủ nodes và failure tolerance tương ứng.

### 4.8. Empty configuration

Nếu `synchronous_standby_names` để trống, không có synchronous standby được chọn. Physical streaming replication vẫn có thể chạy asynchronous; các commit không chờ remote acknowledgement.

Đây là một thay đổi ảnh hưởng trực tiếp durability. Nếu thay trong incident để giải phóng commits, phải ghi nhận rõ RPO exposure và thời điểm bật lại synchronous policy.

---

## 5. FIRST: priority-based synchronous replication

### 5.1. FIRST 1 với hai standby

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
~~~

Giả sử:
- `standby_a` đang streaming.
- `standby_b` đang streaming.

`standby_a` có priority cao hơn nên được chọn làm synchronous standby. `standby_b` vẫn là một physical standby hữu ích nhưng không nhất thiết tham gia acknowledgement cho mỗi commit.

Nếu `standby_a` disconnect, `standby_b` có thể trở thành synchronous standby sau khi được chọn.

### 5.2. FIRST 2 với ba standby

~~~conf
synchronous_standby_names = 'FIRST 2 (standby_a, standby_b, standby_c)'
~~~

Primary chọn hai standby ưu tiên cao nhất trong số những node đủ điều kiện. Nếu cả ba đều kết nối, `standby_a` và `standby_b` là hai node được chọn; `standby_c` có thể là potential standby.

Nếu một trong hai node ưu tiên mất kết nối, node kế tiếp có thể thay thế để duy trì số lượng hai, miễn là còn đủ standby đủ điều kiện.

### 5.3. Ý nghĩa priority

Danh sách là thứ tự ưu tiên, không phải thứ tự network latency. Nếu `standby_a` vẫn được xem là connected/eligible nhưng phản hồi chậm, primary có thể tiếp tục chờ nó theo priority policy thay vì tự động chuyển sang standby nhanh hơn.

Đừng dùng FIRST như một cơ chế latency-aware load balancing.

### 5.4. Ưu điểm

- Xác định được standby ưu tiên để phục vụ HA.
- Có thể chỉ định site/region chính làm synchronous partner.
- Có fallback theo thứ tự danh sách khi standby ưu tiên không còn eligible.
- Dễ diễn giải topology đơn giản như một primary và một synchronous standby chính.

### 5.5. Hạn chế

- Nếu standby ưu tiên vẫn kết nối nhưng bị chậm, commit latency có thể tăng.
- Với `FIRST 1`, chỉ một standby được chọn làm synchronous participant tại một thời điểm.
- Standby khác có thể lag và không có mọi commit đã xác nhận tại thời điểm primary fail.
- Promotion cần chọn node có WAL mới nhất phù hợp, không chỉ chọn node đầu danh sách.

### 5.6. Khi phù hợp

Dùng FIRST khi có standby chính được ưu tiên rõ ràng, chẳng hạn một node ở site gần primary có latency thấp, và các standby khác làm fallback/DR. Cần có runbook kiểm tra sync state và failover selection.

---

## 6. ANY: quorum-based synchronous replication

### 6.1. ANY 1 trong ba standby

~~~conf
synchronous_standby_names = 'ANY 1 (standby_a, standby_b, standby_c)'
~~~

Transaction cần một phản hồi từ bất kỳ standby nào trong ba node. Node nào đáp ứng trước có thể đóng góp vào quorum cho commit đó.

### 6.2. ANY 2 trong ba standby

~~~conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
~~~

Transaction cần hai phản hồi từ bất kỳ hai standby trong danh sách. Nếu một standby không sẵn sàng nhưng hai node còn lại hoạt động, commit vẫn có thể đạt quorum.

### 6.3. Ý nghĩa quorum

Quorum là số lượng phản hồi cần có để xác nhận commit. Với `ANY 2` trong ba nodes, mỗi commit cần ít nhất hai acknowledgements ở mức được yêu cầu bởi `synchronous_commit`.

Quorum không có nghĩa tất cả standby luôn có cùng LSN. Các nodes có thể có lag khác nhau và tập nodes đáp ứng nhanh nhất có thể thay đổi giữa các commits.

### 6.4. Ưu điểm

- Không phụ thuộc cố định vào một standby cụ thể.
- Có thể tiếp tục commit khi một số standby chậm hoặc unavailable, miễn đủ quorum.
- Hữu ích trong topology có nhiều standby ở các failure domains khác nhau.
- Có thể giảm tail latency so với đợi tất cả standby nếu cấu hình số quorum nhỏ hơn tổng số node.

### 6.5. Hạn chế

- Cần hiểu node nào thực sự đã nhận WAL mới nhất trước khi promotion.
- Các standby có thể có progress khác nhau.
- Chọn sai node để promote có thể làm mất những commits mà node đó chưa có.
- Quorum chỉ có ý nghĩa nếu danh sách, số lượng nodes và failure domains được thiết kế đúng.

### 6.6. ANY không đồng nghĩa mọi node đều synchronous

Nếu cấu hình `ANY 2` với ba standbys, mỗi transaction chỉ cần hai phản hồi. Node thứ ba có thể chưa flush tới commit LSN đó khi commit được xác nhận.

### 6.7. Khi phù hợp

ANY phù hợp khi có nhiều standby tương đương và muốn chịu được một hoặc nhiều node/network failure mà vẫn giữ quorum. Số lượng quorum cần căn cứ topology, latency, failure correlation và promotion policy.

---

## 7. So sánh FIRST và ANY

| Tiêu chí | FIRST (priority) | ANY (quorum) |
|---|---|---|
| Cách chọn | Theo thứ tự ưu tiên | Bất kỳ đủ số lượng |
| Standby phản hồi | Các node được chọn theo priority | Bất kỳ `num_sync` node |
| Fallback | Chuyển sang node kế tiếp đủ điều kiện | Node còn lại có thể đóng góp quorum |
| Node ưu tiên | Có | Không dùng priority để chọn quorum |
| Phù hợp | Một standby chính và fallback | Nhiều standby ngang vai trò |
| Điều cần chú ý | Node ưu tiên chậm có thể kéo commit latency | Promotion phải chọn node có WAL mới nhất |

### 7.1. Ví dụ chọn cấu hình

**Topology A:** primary ở region A, standby A1 cùng region có latency thấp, standby B1 ở region B để DR.

Có thể dùng:

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a1, standby_b1)'
~~~

Cần đánh giá nếu standby A1 mất kết nối thì commit chờ B1 qua WAN sẽ có latency khác.

**Topology B:** primary ở site chính, ba standby tương đương ở ba failure domains.

Có thể cân nhắc:

~~~conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
~~~

Cần chọn quorum và promotion policy phù hợp; không promote node chỉ vì nó còn process chạy.

### 7.2. Không có một cấu hình tốt cho mọi topology

Cấu hình phụ thuộc:
- Số standby và failure domains.
- RTT giữa primary/standby.
- Storage flush latency.
- RPO/RTO.
- Khả năng chịu standby outage.
- Cách HA manager chọn/promote node.
- Workload commit rate.
- Mức độ chấp nhận write unavailability.

### 7.3. FIRST 1 so với ANY 1

Cả hai đều cần một phản hồi, nhưng cách chọn khác:
- FIRST 1 chọn node ưu tiên cao nhất đủ điều kiện.
- ANY 1 cho phép bất kỳ node nào trong quorum list đáp ứng.

ANY 1 có thể giảm phụ thuộc vào một node ưu tiên, nhưng failover selection vẫn cần xem WAL progress.

### 7.4. FIRST N so với ANY N

Với FIRST N, primary đợi N standby được chọn theo priority. Với ANY N, primary đợi N phản hồi bất kỳ từ danh sách. Nếu N bằng tổng số standby names thì cả hai đều cần toàn bộ nodes trong danh sách phản hồi, dù semantics selection khác.

---

## 8. synchronous_commit: các mức xác nhận

### 8.1. Bảng tổng quan

| Giá trị | Local WAL flush | Remote write | Remote flush | Remote apply |
|---|---:|---:|---:|---:|
| `off` | Không đợi | Không đợi | Không đợi | Không đợi |
| `local` | Có | Không đợi | Không đợi | Không đợi |
| `remote_write` | Có | Có | Không yêu cầu | Không yêu cầu |
| `on` | Có | Có và flush | Có | Không yêu cầu |
| `remote_apply` | Có | Có và flush | Có | Có |

Bảng diễn tả mức yêu cầu trong synchronous replication. Khi không có synchronous standby được cấu hình, các mức remote không tạo ra một remote acknowledgement để chờ; durability còn phụ thuộc local WAL behavior.

### 8.2. off

`synchronous_commit=off` cho phép server trả COMMIT success trước khi WAL tương ứng được flush xuống local storage. Điều này có thể giảm commit latency.

Trade-off:
- Có thể mất một số transactions vừa được xác nhận nếu server/OS/storage crash trước flush.
- Database vẫn được thiết kế để giữ consistency; async commit không đồng nghĩa cho phép corruption.
- WAL vẫn được tạo; `off` không tắt WAL logging.
- Không phù hợp cho mọi business transactions.

### 8.3. local

`synchronous_commit=local` chờ local WAL flush nhưng không chờ synchronous standby. Đây là mức local durability: transaction được xác nhận sau local flush theo storage assumptions, nhưng remote standby có thể chưa nhận/flush commit record.

Dùng khi transaction cần local durability nhưng không cần remote synchronous acknowledgement, hoặc trong một policy có chủ đích.

### 8.4. remote_write

`synchronous_commit=remote_write` chờ local WAL flush và standby xác nhận WAL đã được ghi tới OS/file layer. Nó không đợi remote fsync/flush bền xuống persistent storage.

Ưu điểm là thường có latency thấp hơn remote flush. Trade-off là standby OS crash hoặc power loss có thể làm mất WAL bytes chưa được flush bền. Cần hiểu chính xác semantics storage/OS.

### 8.5. on

`synchronous_commit=on` là giá trị mặc định phổ biến. Khi synchronous replication được cấu hình, primary chờ local WAL flush và synchronous standby flush WAL tới persistent storage theo cơ chế PostgreSQL.

Đây là lựa chọn thường dùng khi muốn acknowledged commits được bảo vệ trên primary và synchronous standby, với điều kiện failover promote đúng node có WAL đó.

### 8.6. remote_apply

`synchronous_commit=remote_apply` chờ synchronous standby replay commit record, tức transaction đã được áp dụng và có thể được nhìn thấy bởi các query mới trên standby theo MVCC.

Dùng khi cần read-after-write từ standby:
1. Client ghi trên primary.
2. COMMIT chờ standby replay.
3. Sau khi COMMIT trả về, client đọc bằng một transaction/snapshot mới trên standby.
4. Query có thể thấy transaction đã commit.

Một transaction đọc đã mở snapshot cũ vẫn có thể không thấy row mới dù standby đã replay; `remote_apply` không thay đổi snapshot isolation.

### 8.7. Vì sao remote_apply chậm hơn on?

Remote apply bao gồm việc standby replay WAL, không chỉ ghi/flush bytes. Replay có thể bị giới hạn bởi CPU, I/O, workload trên standby hoặc hot standby conflicts. Với read-heavy standby, long-running queries có thể ảnh hưởng recovery/replay tùy conflict settings.

### 8.8. Mức nào là “strongest”?

Trong các mức trên, `remote_apply` đòi hỏi tiến độ xa nhất ở standby: replay. Tuy nhiên “mạnh nhất” không có nghĩa mọi loại failure đều được giải quyết. Cần xét storage durability, số standby, failure domains, promotion policy, backups và corruption scenarios.

### 8.9. Không nhầm remote_write với remote_flush

- Remote write: WAL đã được ghi tới OS/file layer trên standby.
- Remote flush: WAL đã được flush theo durability path.
- Remote apply: WAL đã được replay.

Đây là các acknowledgement levels khác nhau và có latency/risk khác nhau.

---

## 9. Mối quan hệ giữa standby count và commit level

### 9.1. FIRST 1 + on

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
~~~

Primary chờ một standby được chọn theo priority flush WAL. Standby còn lại có thể tiếp tục asynchronous/potential tùy trạng thái selection.

### 9.2. FIRST 2 + on

~~~conf
synchronous_standby_names = 'FIRST 2 (standby_a, standby_b, standby_c)'
synchronous_commit = on
~~~

Primary chờ hai standby được chọn flush WAL. Nếu chỉ một node đủ điều kiện, các commits yêu cầu synchronous acknowledgement có thể chờ.

### 9.3. ANY 2 + on

~~~conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
synchronous_commit = on
~~~

Primary chờ hai standby bất kỳ trong danh sách flush commit WAL. Nếu một node mất kết nối, hai node còn lại vẫn có thể đáp ứng quorum.

### 9.4. ANY 2 + remote_apply

~~~conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
synchronous_commit = remote_apply
~~~

Primary chờ hai standby bất kỳ replay commit record. Điều này mạnh hơn về read visibility trên các standby tham gia phản hồi, nhưng có thể tăng latency đáng kể.

### 9.5. local override

Ngay cả khi primary có synchronous standby names:

~~~sql
BEGIN;
SET LOCAL synchronous_commit = local;
UPDATE app.metrics SET value = value + 1 WHERE metric_id = 10;
COMMIT;
~~~

Transaction này chỉ chờ local WAL flush. Nó không được bảo vệ bằng remote synchronous acknowledgement như transaction dùng `on`/`remote_apply`.

### 9.6. Off override

~~~sql
BEGIN;
SET LOCAL synchronous_commit = off;
INSERT INTO app.rebuild_queue(job_id) VALUES ('rebuild-42');
COMMIT;
~~~

Chỉ dùng nếu business chấp nhận rủi ro mất transaction vừa được xác nhận trong crash. Nếu queue là nguồn duy nhất cho công việc quan trọng, `off` có thể không phù hợp.

---

## 10. Standby selection và trạng thái trong pg_stat_replication

### 10.1. Quan sát trên primary

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sync_priority,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication
ORDER BY sync_priority, application_name;
~~~

View này cho biết các WAL sender connections đang hoạt động và trạng thái đồng bộ của từng standby.

### 10.2. Các sync_state thường gặp

Các giá trị thường thấy gồm:
- `async`: standby đang asynchronous.
- `potential`: standby đủ điều kiện có thể được chọn theo priority nhưng hiện không nằm trong synchronous set.
- `sync`: standby được chọn synchronous trong priority-based configuration.
- `quorum`: standby tham gia quorum-based synchronous configuration.

Tên/trạng thái chính xác cần đối chiếu version; đọc `sync_priority` cùng `sync_state` và cấu hình hiện tại.

### 10.3. sync_priority

Trong priority-based setup, số priority giúp hiểu thứ tự lựa chọn. Standby được chọn có thể có priority cao hơn theo thứ tự list. Với quorum setup, không diễn giải priority như một thứ tự quyết định node thắng quorum.

### 10.4. LSN positions

- `sent_lsn`: vị trí WAL sender đã gửi.
- `write_lsn`: vị trí standby đã ghi.
- `flush_lsn`: vị trí standby đã flush.
- `replay_lsn`: vị trí standby đã replay.

Khoảng cách bytes có thể tính:

~~~sql
SELECT
    application_name,
    sync_state,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn)::bigint
    ) AS flush_behind,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)::bigint
    ) AS replay_behind
FROM pg_stat_replication
WHERE flush_lsn IS NOT NULL;
~~~

Đây là các LSN distances gần thời điểm lấy mẫu, không phải latency thời gian chính xác. Nếu primary idle, lag timestamps có thể không phản ánh đúng độ trễ theo giây.

### 10.5. Xem backend đang chờ SyncRep

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    query
FROM pg_stat_activity
WHERE wait_event = 'SyncRep';
~~~

Wait event `SyncRep` cho biết backend đang chờ synchronous replication response. Đây là tín hiệu hữu ích khi COMMIT bị chậm do thiếu standby acknowledgement.

### 10.6. Quan sát receiver trên standby

~~~sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    latest_end_lsn,
    latest_end_time,
    sender_host,
    sender_port
FROM pg_stat_wal_receiver;
~~~

Các cột có thể thay đổi theo major version. View này giúp quan sát receiver progress phía standby; cần kết hợp replay LSN và logs để hiểu apply lag.

### 10.7. Kiểm tra cấu hình thực tế

~~~sql
SHOW synchronous_standby_names;
SHOW synchronous_commit;

SELECT
    name,
    setting,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'synchronous_standby_names',
    'synchronous_commit',
    'wal_level',
    'wal_sender_timeout'
);
~~~

Kiểm tra cấu hình đang được server sử dụng, không chỉ file cấu hình trong repository hoặc automation. Một config file đã đổi nhưng chưa reload có thể chưa có hiệu lực.

---

## 11. Thay đổi cấu hình và áp dụng an toàn

### 11.1. Thay đổi synchronous_standby_names

Tham số synchronous_standby_names có thể reload trong các PostgreSQL versions hiện đại; không cần restart server cho thay đổi thông thường. Ví dụ dùng ALTER SYSTEM trong lab:

~~~sql
ALTER SYSTEM SET synchronous_standby_names =
    'FIRST 1 (standby_a, standby_b)';

SELECT pg_reload_conf();

SHOW synchronous_standby_names;
~~~

Trong production, cấu hình có thể được quản lý bằng configuration management hoặc file include. Chỉ dùng một nguồn quản lý có thẩm quyền để tránh drift giữa file và ALTER SYSTEM.

### 11.2. Kiểm tra reload có thành công

pg_reload_conf() trả kết quả cho biết tín hiệu reload đã được gửi; điều đó chưa bảo đảm mọi setting hợp lệ hoặc standby đã được chọn. Kiểm tra:
- PostgreSQL logs có lỗi parsing/configuration không.
- SHOW synchronous_standby_names có giá trị mong đợi không.
- pg_stat_replication.sync_state có thay đổi đúng không.
- Commit behavior có đáp ứng mức yêu cầu không.

### 11.3. Đặt synchronous_commit cho session

~~~sql
SET synchronous_commit = 'on';
SHOW synchronous_commit;
~~~

Setting session có thể tồn tại qua nhiều transactions trên cùng connection. Connection pool phải reset session state hoặc ứng dụng nên dùng SET LOCAL trong transaction để tránh rò setting giữa requests.

### 11.4. Đặt mức theo transaction

~~~sql
BEGIN;
SET LOCAL synchronous_commit = 'remote_apply';

UPDATE app.account_balance
SET balance = balance - 50
WHERE account_id = 10;

COMMIT;
~~~

SET LOCAL chỉ có hiệu lực trong transaction hiện tại. Khi transaction kết thúc, setting trước đó của session được khôi phục.

### 11.5. Thay đổi standby application_name

Nếu standby đổi application_name trong primary_conninfo, primary có thể không còn nhận diện standby theo tên cũ. Cần phối hợp thay đổi connection string và synchronous_standby_names để không tạo khoảng trống không có synchronous standby.

### 11.6. Thứ tự rollout

Một cách rollout có kiểm soát:
1. Kiểm tra mọi standby đã streaming và có tên duy nhất.
2. Xác nhận latency, write/flush/replay progress.
3. Cập nhật standby connection identity nếu cần.
4. Cập nhật danh sách standby trên primary.
5. Reload và kiểm tra sync_state.
6. Chạy transaction test với acknowledgement level mong muốn.
7. Kiểm tra wait events, commit latency và logs.
8. Cập nhật runbook/failover policy.

Không đổi đồng thời nhiều yếu tố như topology, application_name, quorum size và commit level mà không có cách xác định nguyên nhân khi failure.

---

## 12. Điều gì xảy ra khi standby không sẵn sàng?

### 12.1. FIRST 1: standby ưu tiên mất kết nối

Với:

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
~~~

Nếu standby_a disconnect và standby_b đủ điều kiện, standby_b có thể được chọn thay thế. Commit wait có thể tiếp tục sau khi primary xác định được synchronous standby mới.

### 12.2. FIRST 1: standby ưu tiên vẫn kết nối nhưng chậm

Nếu standby ưu tiên vẫn connected nhưng phản hồi WAL chậm, primary có thể tiếp tục chờ node đó. Một node fallback có thể không tự thay thế chỉ vì nó nhanh hơn; selection dựa vào policy và eligibility, không phải latency-aware routing.

### 12.3. ANY 2: một standby mất kết nối

Với:

~~~conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
~~~

Nếu một node disconnect, hai node còn lại vẫn có thể đáp ứng quorum. Nếu chỉ còn một node đủ điều kiện, commits cần remote acknowledgement sẽ chờ cho tới khi quorum được khôi phục hoặc cấu hình/policy thay đổi.

### 12.4. Không đủ standby để đạt num_sync

Nếu số standby đủ điều kiện thấp hơn num_sync:
- Transactions dùng on, remote_write hoặc remote_apply có thể chờ synchronous acknowledgement.
- Transactions dùng local vẫn chờ local WAL flush nhưng không chờ standby.
- Transactions dùng off có thể được xác nhận trước local WAL flush.
- Read-only transactions thường không phải chờ synchronous commit như một write transaction.

Đừng mặc định primary bị hỏng chỉ vì COMMIT đang chờ. Kiểm tra wait event và trạng thái standby trước khi hành động.

### 12.5. Network partition

Network partition có thể làm WAL sender không nhận feedback từ standby. Từ góc nhìn primary, standby có thể vẫn tồn tại nhưng không đáp ứng. Khi connection timeout/disconnect, selection policy có thể chọn node khác nếu còn đủ.

Đây là nơi durability và write availability xung đột: chờ standby giữ mức xác nhận; bỏ chờ làm giảm bảo đảm remote.

### 12.6. Primary vẫn nhận SELECT?

Synchronous replication chủ yếu ảnh hưởng transactions cần synchronous commit. Primary vẫn có thể phục vụ reads và một số hoạt động khác. Tuy nhiên, write transactions có thể bị chặn ở COMMIT, làm giữ connections và tài nguyên ứng dụng.

### 12.7. Giải pháp khi commits bị treo

Theo thứ tự:
1. Xem backend đang chờ SyncRep.
2. Xem pg_stat_replication và standby sync_state.
3. Kiểm tra network/WAL sender/receiver và logs.
4. Kiểm tra standby disk flush/replay bottleneck.
5. Khôi phục standby hoặc network.
6. Nếu business cần khôi phục writes khẩn cấp, cân nhắc thay đổi policy để chuyển sang asynchronous theo quy trình incident có phê duyệt.
7. Ghi rõ RPO exposure và xác minh lại synchronous mode sau incident.

Không kill backend hàng loạt hoặc drop standby/slot trước khi hiểu trạng thái transaction và failover plan.

### 12.8. Synchronous replication không tự timeout commit theo một ngưỡng business

Không có một setting chung trong synchronous_standby_names mang ý nghĩa “chờ standby 5 giây rồi tự động commit asynchronous”. Các timeout kết nối/keepalive và timeout ở ứng dụng có semantics khác. Nếu muốn fallback sau một ngưỡng, cần orchestration/policy rõ ràng; không nhầm timeout network với một cơ chế quorum tự hạ mức xác nhận.

---

## 13. Latency, throughput và chi phí của mức xác nhận

### 13.1. Commit latency

Với synchronous replication, thời gian COMMIT chịu ảnh hưởng của:
- Local WAL flush.
- Network RTT primary–standby.
- Standby WAL write/flush latency.
- Replay speed nếu dùng remote_apply.
- Số standby cần phản hồi.
- Group commit và concurrency.
- Storage queue depth và CPU contention.

### 13.2. FIRST 1

FIRST 1 thường làm commit latency phụ thuộc standby được chọn. Nếu node đó ở gần primary, latency có thể thấp; nếu fallback ở xa được chọn, latency có thể tăng đáng kể.

### 13.3. FIRST 2

FIRST 2 đợi cả hai standby được chọn. Latency thường bị chi phối bởi node chậm hơn trong nhóm cần phản hồi, vì transaction cần đủ hai acknowledgements.

### 13.4. ANY 2

ANY 2 đợi hai phản hồi từ nhóm. Nếu ba nodes có latency khác nhau, hai node phản hồi nhanh hơn có thể đủ quorum. Đây có thể giảm tail latency so với chờ tất cả ba, nhưng chỉ khi network/storage paths và node selection thực tế phù hợp.

### 13.5. remote_write, on và remote_apply

- remote_write dừng ở remote OS write acknowledgement, thường ít chờ hơn remote flush.
- on chờ remote flush; tăng durability qua remote storage.
- remote_apply chờ replay; có thể tăng latency khi standby apply chậm.

Không chọn chỉ theo benchmark một transaction đơn lẻ. Đo p50/p95/p99 commit latency dưới tải đại diện.

### 13.6. Throughput và group commit

Group commit có thể gom nhiều commits vào cùng một flush round, giúp giảm chi phí sync cho từng transaction. Tuy vậy, synchronous replication thêm điều kiện chờ standby; khi standby bottleneck, throughput write có thể giảm và queue backend có thể tăng.

### 13.7. Backpressure

Nếu standby không theo kịp, primary có thể giữ nhiều WAL và các commit waiters. Cần theo dõi:
- Số backend chờ SyncRep.
- Commit latency.
- WAL sender send/write/flush/replay positions.
- Standby CPU/I/O.
- Disk queue/latency.
- Replication slot retention và pg_wal size.

### 13.8. Chọn quorum size

Tăng num_sync:
- Tăng số node có xác nhận cho mỗi commit.
- Có thể cải thiện khả năng tồn tại dữ liệu trên nhiều failure domains.
- Tăng latency và giảm khả năng commit khi nodes không sẵn sàng.

Giảm num_sync:
- Tăng khả năng tiếp tục commit khi một số nodes lỗi.
- Giảm số acknowledgement cần đợi.
- Giảm số standby chắc chắn đã xác nhận mỗi commit.

Quyết định phải dựa trên RPO, failure model và promotion policy, không chỉ số lượng máy.

---

## 14. Thiết kế topology và failover

### 14.1. Một synchronous standby và một asynchronous standby

~~~text
             +--> standby_sync (priority 1)
Primary -----|
             +--> standby_dr (async / fallback)
~~~

Cấu hình FIRST 1 có thể ưu tiên standby gần primary. Standby DR có thể được chọn làm synchronous standby khi node ưu tiên không còn eligible. Cần xác định latency khi fallback và đảm bảo DR node có đủ WAL trước promotion.

### 14.2. Ba standby với quorum

~~~text
                  +--> standby_a
Primary ----------+--> standby_b
                  +--> standby_c

synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
~~~

Mỗi commit cần hai acknowledgements. Nếu một node lỗi, hai node còn lại có thể duy trì quorum.

### 14.3. Failure domains

Đặt tất cả synchronous standbys trên cùng một host/rack/storage array có thể tạo correlated failure. Nên phân bố theo failure domains phù hợp, đồng thời đánh giá network latency và khả năng vận hành. Một topology đa region nhưng RTT cao có thể làm commit latency lớn.

### 14.4. Chọn node để promote

Khi primary mất:
- Xác định node nào có WAL mới nhất.
- So sánh receive/flush/replay LSN.
- Xem sync_state và cấu hình đã có hiệu lực trước sự cố.
- Kiểm tra timeline/history.
- Xác nhận node được chọn chứa commit WAL cần bảo vệ.
- Fence primary cũ để tránh split brain.
- Promote theo HA manager/runbook.

Không chỉ chọn standby đầu tiên trong cấu hình FIRST hoặc một standby bất kỳ trong ANY.

### 14.5. FIRST không phải fencing

Priority list quyết định synchronous standby selection trên primary đang chạy. Nó không ngăn primary cũ tiếp tục nhận writes sau partition và không tự đảm bảo một node duy nhất là leader. Fencing/STONITH/lease/quorum của HA layer là trách nhiệm riêng.

### 14.6. ANY không phải consensus leader election

Quorum acknowledgement của synchronous replication không thay thế distributed consensus hoặc HA manager. Nó quy định số standby phản hồi WAL cho commit; quyết định ai được phép làm primary vẫn cần failover coordination và fencing.

### 14.7. Synchronous replication và backup

Một standby synchronous có thể chứa mọi commit đã được xác nhận tới mức tương ứng, nhưng vẫn có thể replicate thao tác phá hoại hoặc lỗi logic. Cần base backup, WAL archive, retention và PITR độc lập.

### 14.8. RPO bằng 0 có điều kiện

Synchronous replication có thể đạt mục tiêu không mất acknowledged commits trong failure model đã thiết kế nếu:
- Transaction dùng mức remote phù hợp.
- Standby acknowledgement đã đạt.
- Node được promote thực sự có WAL đó.
- Storage/host failure không làm mất đồng thời các bản đã xác nhận.
- Primary cũ được fence.
- Không có transaction override sang local/off ngoài policy.

Không tuyên bố RPO=0 chỉ vì synchronous_standby_names không rỗng.

---

## 15. Read-after-write trên standby

### 15.1. Vấn đề replication lag

Ứng dụng ghi trên primary rồi đọc ngay từ standby có thể không thấy row vừa ghi nếu standby chưa replay tới commit record. Đây là eventual consistency thông thường của asynchronous replication và cũng có thể xảy ra trong synchronous replication nếu mức chờ chỉ là remote write/flush.

### 15.2. remote_apply

synchronous_commit=remote_apply đợi synchronous standby replay commit record trước khi primary xác nhận commit. Sau khi commit response trả về, một transaction mới trên standby có thể thấy changes đó.

### 15.3. Snapshot cũ

Nếu ứng dụng giữ transaction đọc đã mở trước khi commit, snapshot cũ vẫn có thể không thấy changes. Hãy mở transaction/read snapshot mới sau commit khi cần read-after-write.

### 15.4. Chỉ một số standby được xác nhận

Với ANY 1 trong nhiều standbys, một transaction có thể được replay trên một node đáp ứng quorum; node khác có thể lag. Nếu ứng dụng đọc ngẫu nhiên từ mọi standby, remote_apply acknowledgement trên một standby không tự bảo đảm mọi replica đã replay.

### 15.5. Read routing

Nếu yêu cầu read-after-write nghiêm ngặt:
- Đọc từ primary cho các reads ngay sau write; hoặc
- Gắn session/tenant vào standby đã xác nhận transaction nếu architecture hỗ trợ; hoặc
- Dùng remote_apply và route tới synchronous standby đáp ứng; hoặc
- Chờ replica replay tới commit LSN trước khi đọc.

Không dựa vào sleep cố định như một bảo đảm nhất quán.

---

## 16. Troubleshooting các tình huống thường gặp

### 16.1. Standby streaming nhưng sync_state=async

Kiểm tra:
1. application_name trên standby có khớp danh sách không?
2. synchronous_standby_names đã reload chưa?
3. Đang nhìn đúng primary không?
4. Standby connection có phải WAL sender phù hợp không?
5. num_sync và list names có khả thi không?
6. Một standby ưu tiên khác đang được chọn thay thế không?

### 16.2. sync_state=potential nhưng không phải sync

Trong priority mode, standby có thể đủ điều kiện nhưng có priority thấp hơn node đang được chọn. Kiểm tra standby ưu tiên trước nó và tình trạng connection/sync state.

### 16.3. COMMIT chờ lâu

Xem:
- pg_stat_activity.wait_event='SyncRep'.
- pg_stat_replication.
- Network latency/loss.
- Standby flush/replay progress.
- Standby storage latency.
- Số standby cần phản hồi.
- synchronous_commit ở session/transaction.

### 16.4. Chỉ remote_apply chậm

Nếu write/flush LSN theo kịp nhưng replay LSN chậm, điều tra apply/replay:
- CPU/IO trên standby.
- Long-running read queries/hot standby conflicts.
- WAL record workload nặng.
- Recovery process wait events/logs.
- Query workload cạnh tranh trên standby.

### 16.5. Standby reconnect nhưng commits vẫn chờ

Kiểm tra:
- Standby có đúng application_name không?
- Đã trở thành sync/quorum state chưa?
- WAL receiver có bắt kịp không?
- Đang cần đủ num_sync nodes không?
- Có nhiều standby names bị duplicate/không hợp lệ không?

### 16.6. Commit latency tăng sau failover

Sau khi fallback standby ở xa trở thành synchronous partner, network RTT có thể tăng. Đo lại commit latency và xác nhận topology hiện tại; không giả định failover giữ nguyên performance profile.

### 16.7. WAL disk tăng

Synchronous standby chậm có thể liên quan replication progress và slots; nhưng disk growth còn phụ thuộc archive/retention. Kiểm tra slot restart_lsn, archive failures, checkpoint và WAL generation trước khi kết luận.

### 16.8. Không đủ synchronous standby

Nếu cần duy trì writes nhưng không còn đủ node:
- Khôi phục standby/network nếu có thể.
- Cân nhắc giảm num_sync hoặc chuyển async chỉ theo incident policy.
- Ghi nhận khoảng thời gian và transactions chịu mức durability thấp hơn.
- Xác minh node nào đã nhận/flush WAL.
- Khi standby trở lại, kiểm tra sync state và lag trước khi xem hệ thống healthy.

---

## 17. Runbook khi synchronous commits bị stall

1. Xác nhận phạm vi: tất cả writes hay một application/transaction class.
2. Kiểm tra pg_stat_activity và số backend chờ SyncRep.
3. Đọc SHOW synchronous_standby_names và SHOW synchronous_commit.
4. Xem pg_stat_replication: application_name, state, sync_state, priority, flush/replay LSN.
5. Xem logs primary/standby, WAL sender/receiver và network.
6. Kiểm tra storage latency và replay bottleneck trên standby.
7. Xác định số standby hiện đủ điều kiện so với num_sync.
8. Khôi phục node/network hoặc giảm tải standby.
9. Nếu phải chuyển async để khôi phục writes, ghi rõ phê duyệt, thời điểm, RPO exposure và cách bật lại.
10. Sau incident, xác nhận đúng synchronous standby đã được chọn và chạy transaction test.
11. Kiểm tra failover/promotion policy và cập nhật postmortem.

Không kill toàn bộ backend chờ SyncRep như cách xử lý mặc định. Một COMMIT bị hủy/connection bị mất có thể tạo unknown outcome; ứng dụng cần idempotency và reconciliation.

---

## 18. Tài liệu tham khảo PostgreSQL

Ưu tiên tài liệu đúng major version server:

- [PostgreSQL — Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION): synchronous standby selection và acknowledgement.
- [PostgreSQL — Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html): synchronous_standby_names và replication settings.
- [PostgreSQL — WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): synchronous_commit và durability settings.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): pg_stat_replication, pg_stat_wal_receiver và wait events.
- [PostgreSQL — Warm Standby](https://www.postgresql.org/docs/current/warm-standby.html): streaming replication và failover.
- [PostgreSQL — Administrative Functions](https://www.postgresql.org/docs/current/functions-admin.html): reload configuration và WAL/LSN functions.
- [PostgreSQL — High Availability](https://www.postgresql.org/docs/current/high-availability.html): các kiến trúc HA và replication.

Các trang /current/ có thể đổi theo thời gian. Kiểm tra cú pháp, wait event, view columns và semantics với major version đang chạy.

---

## 19. Bài lab: cấu hình và quan sát FIRST 1

### 19.1. Mô hình lab

Giả sử có:
- Primary: node ghi dữ liệu.
- Standby A: application_name là standby_a.
- Standby B: application_name là standby_b.

Cả hai standby phải được cấu hình physical streaming replication, kết nối được tới primary và ở trạng thái streaming. Lab này chỉ mô tả cấu hình; thực hiện trên cluster test có thể bỏ và dựng lại.

### 19.2. Kiểm tra WAL level

Trên primary:

~~~sql
SHOW wal_level;
~~~

Physical streaming replication cần mức WAL phù hợp, thường là replica hoặc mức cao hơn theo version. Nếu setting không đáp ứng, cần thay đổi cấu hình và restart theo yêu cầu parameter; không thay đổi production chỉ để chạy lab.

### 19.3. Đặt application_name trên standby

Ví dụ phần connection string trên standby A:

~~~conf
primary_conninfo = 'host=primary.lab port=5432 user=replicator application_name=standby_a'
~~~

Standby B dùng application_name khác. Không để cả hai dùng cùng tên nếu muốn theo dõi/selection độc lập.

### 19.4. Cấu hình FIRST 1 trên primary

~~~sql
ALTER SYSTEM SET synchronous_standby_names =
    'FIRST 1 (standby_a, standby_b)';

SELECT pg_reload_conf();

SHOW synchronous_standby_names;
~~~

### 19.5. Quan sát selection

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    sync_priority,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication
ORDER BY sync_priority, application_name;
~~~

Khi cả hai standby kết nối và đủ điều kiện, node ưu tiên cao hơn có thể được chọn làm sync; node còn lại có thể là potential/async theo version và state. Quan sát output thực tế thay vì giả định chỉ vì connection đang streaming.

### 19.6. Chạy transaction commit

~~~sql
CREATE SCHEMA IF NOT EXISTS sync_lab;

CREATE TABLE IF NOT EXISTS sync_lab.events (
    event_id bigint PRIMARY KEY,
    payload text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

BEGIN;
SET LOCAL synchronous_commit = 'on';

INSERT INTO sync_lab.events(event_id, payload)
VALUES (1, 'first synchronous commit');

COMMIT;
~~~

COMMIT sẽ chờ mức local/remote flush cần thiết theo cấu hình và sync standby đang được chọn.

### 19.7. So sánh với local

~~~sql
BEGIN;
SET LOCAL synchronous_commit = 'local';

INSERT INTO sync_lab.events(event_id, payload)
VALUES (2, 'local acknowledgement only');

COMMIT;
~~~

Transaction thứ hai chờ local WAL flush nhưng không đợi remote synchronous acknowledgement. Standby vẫn nhận WAL theo streaming replication bình thường.

### 19.8. Quan sát backend chờ

Trong một session khác, khi tạo tình huống standby chậm/disconnected có kiểm soát trong lab:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE wait_event = 'SyncRep';
~~~

Nếu transaction đang đợi remote acknowledgement, có thể thấy wait event SyncRep. Kết quả phụ thuộc timing và phiên bản.

---

## 20. Bài lab: quorum ANY 2

### 20.1. Cấu hình

Với ba standbys có application_name riêng:

~~~sql
ALTER SYSTEM SET synchronous_standby_names =
    'ANY 2 (standby_a, standby_b, standby_c)';

SELECT pg_reload_conf();
~~~

### 20.2. Xác nhận quorum state

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    sync_priority,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication
ORDER BY application_name;
~~~

Xem những nodes tham gia quorum theo sync_state và trạng thái thực tế. Đừng suy rằng cả ba node đã flush cùng một commit chỉ vì chúng đều nằm trong list.

### 20.3. Thử một standby mất kết nối

Trong lab:
1. Ghi nhận LSN positions và sync states.
2. Dừng một standby bằng quy trình quản trị test.
3. Xác nhận hai standby còn lại đang streaming và đủ quorum.
4. Chạy transaction dùng synchronous_commit=on.
5. Quan sát COMMIT và pg_stat_activity.
6. Khởi động lại standby bị dừng.
7. Theo dõi catch-up và sync state.

Không dừng standby production để thử. Nếu chỉ còn một standby đủ điều kiện, commits cần quorum hai có thể chờ.

### 20.4. Thử quorum không đủ

Trong môi trường test, dừng hai standby để chỉ còn một node trong cấu hình ANY 2. Quan sát backend chờ SyncRep. Khôi phục một node và kiểm tra commits tiếp tục khi quorum đạt.

### 20.5. So sánh FIRST và ANY

Lặp lại cùng topology với FIRST 1 và ANY 1. Ghi:
- Standby nào được chọn.
- Sync state.
- Commit latency.
- Behavior khi node ưu tiên disconnect.
- Node nào có flush/replay LSN mới nhất.

### 20.6. Reset cấu hình lab

Sau test, đặt cấu hình đúng với mục tiêu lab tiếp theo hoặc khôi phục cấu hình ban đầu đã lưu. Không để cluster test ở trạng thái quorum/commit level không chủ đích.

---

## 21. Bài lab: so sánh acknowledgement levels

### 21.1. Mẫu workload

~~~sql
CREATE TABLE IF NOT EXISTS sync_lab.commit_probe (
    id bigserial PRIMARY KEY,
    mode text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

Thử từng mức trong transaction riêng:

~~~sql
BEGIN;
SET LOCAL synchronous_commit = 'local';
INSERT INTO sync_lab.commit_probe(mode) VALUES ('local');
COMMIT;
~~~

~~~sql
BEGIN;
SET LOCAL synchronous_commit = 'remote_write';
INSERT INTO sync_lab.commit_probe(mode) VALUES ('remote_write');
COMMIT;
~~~

~~~sql
BEGIN;
SET LOCAL synchronous_commit = 'on';
INSERT INTO sync_lab.commit_probe(mode) VALUES ('on');
COMMIT;
~~~

~~~sql
BEGIN;
SET LOCAL synchronous_commit = 'remote_apply';
INSERT INTO sync_lab.commit_probe(mode) VALUES ('remote_apply');
COMMIT;
~~~

### 21.2. Đo latency

Dùng client benchmark/script đo nhiều commits, ghi p50/p95/p99 và tải hệ thống. Không chỉ chạy một transaction duy nhất vì group commit, cache và scheduling làm kết quả nhiễu.

### 21.3. Đối chiếu progress

Trên primary:

~~~sql
SELECT
    application_name,
    sync_state,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

Với remote_write, quan tâm write progress; với on, quan tâm flush progress; với remote_apply, quan tâm replay progress. Dùng logs/metrics cùng thời điểm để diễn giải latency.

### 21.4. Read-after-write test

Sau transaction remote_apply:
1. Mở một transaction mới trên standby.
2. Query row vừa ghi.
3. Xác nhận row có thể được nhìn thấy sau replay.
4. Thử lại với transaction snapshot mở trước khi commit để hiểu snapshot isolation.

### 21.5. Ghi kết quả

Lưu cấu hình, version, số standby, RTT, storage type, commit mode, quorum, latency percentile và failure behavior. Không lấy kết quả của một môi trường lab để khẳng định production có cùng latency.

---

## 22. Bài tập thực hành

Các bài dùng PostgreSQL lab. Không gây mất kết nối hoặc dừng standby production để thử failure scenarios.

### Bài 1 — synchronous replication

Giải thích synchronous replication giải quyết vấn đề gì khi primary failover.

### Bài 2 — Hai tham số

Phân biệt vai trò của synchronous_standby_names và synchronous_commit.

### Bài 3 — Standby name

Standby name trong synchronous_standby_names phải khớp với setting nào trên replication connection?

### Bài 4 — FIRST 1

Với FIRST 1 (a,b,c), node nào được ưu tiên? Điều gì có thể xảy ra khi a disconnect?

### Bài 5 — FIRST 2

Với FIRST 2 (a,b,c), hai node nào được chọn khi cả ba đủ điều kiện? Node thứ ba có vai trò gì?

### Bài 6 — ANY 2

Với ANY 2 (a,b,c), cần bao nhiêu phản hồi? Nếu c disconnect thì có thể commit không?

### Bài 7 — Quorum

Quorum acknowledgement có nghĩa mọi standby đều đã nhận commit không? Giải thích.

### Bài 8 — FIRST và ANY

Nêu khác biệt quan trọng nhất về selection giữa FIRST và ANY.

### Bài 9 — synchronous_commit off

off có tắt WAL không? Rủi ro chính là gì?

### Bài 10 — local

local chờ điều gì và không chờ điều gì?

### Bài 11 — remote_write

Standby đã remote_write acknowledge có bảo đảm WAL bền qua power loss của standby không? Vì sao?

### Bài 12 — on

on chờ mức remote nào? Nó có bắt buộc standby đã replay không?

### Bài 13 — remote_apply

remote_apply hữu ích trong tình huống ứng dụng nào? Vì sao snapshot cũ vẫn có thể không thấy row mới?

### Bài 14 — Không có synchronous standby

Nếu synchronous_standby_names trống, remote modes có standby để chờ không? Commit behavior ra sao?

### Bài 15 — Không đủ quorum

ANY 2 có ba standbys nhưng chỉ một node đủ điều kiện. Điều gì xảy ra với COMMIT dùng on?

### Bài 16 — Standby ưu tiên chậm

FIRST 1 (a,b), a vẫn connected nhưng rất chậm, b nhanh. Vì sao b không nhất thiết tự thay thế a?

### Bài 17 — Sync state

Nêu ý nghĩa khái quát của async, potential, sync và quorum trong pg_stat_replication.

### Bài 18 — Wait event

Viết query tìm các backends đang chờ SyncRep.

### Bài 19 — Replication progress

Nêu ý nghĩa sent_lsn, write_lsn, flush_lsn và replay_lsn.

### Bài 20 — Reload

synchronous_standby_names có cần restart server cho thay đổi thông thường không? Làm sao xác nhận reload có hiệu lực?

### Bài 21 — Session override

Viết transaction dùng SET LOCAL synchronous_commit='remote_apply'.

### Bài 22 — Connection pool

Vì sao SET synchronous_commit ở session level có thể gây lỗi policy giữa các requests nếu pool không reset session?

### Bài 23 — Latency

Với FIRST 2, latency commit thường chịu ảnh hưởng của node nào trong hai node được chọn? Giải thích.

### Bài 24 — ANY 2 latency

Vì sao ANY 2 có thể giảm tail latency so với chờ cả ba standbys?

### Bài 25 — remote_apply chậm

Write/flush LSN theo kịp nhưng replay LSN chậm. Cần điều tra những gì?

### Bài 26 — Promotion

Khi primary mất, vì sao không được chỉ promote standby đầu danh sách FIRST?

### Bài 27 — Quorum và failover

ANY 2 trong ba standbys có cho phép promote một node bất kỳ không? Điều gì cần kiểm tra?

### Bài 28 — RPO zero

Nêu các điều kiện cần để synchronous replication hỗ trợ mục tiêu không mất acknowledged commits.

### Bài 29 — Synchronous replication và backup

Vì sao synchronous standby không thay thế base backup/WAL archive/PITR?

### Bài 30 — Network partition

Primary không nhận được feedback từ standby. Vì sao commits có thể bị chờ? Các lựa chọn vận hành là gì?

### Bài 31 — wal_level

wal_level cần đáp ứng mức nào cho physical streaming replication? Vì sao minimal không phù hợp?

### Bài 32 — Standby application_name sai

Standby vẫn streaming nhưng sync_state=async. Nêu các bước điều tra.

### Bài 33 — RPO và quorum size

Tăng num_sync có những trade-offs nào về durability, latency và availability?

### Bài 34 — FIRST 1 so với ANY 1

Hai cấu hình đều cần một response. Vì sao hành vi có thể khác?

### Bài 35 — Read-after-write

Một transaction commit với on, ứng dụng đọc ngay từ standby và không thấy row. Giải thích và đề xuất cách xử lý.

### Bài 36 — remote_apply và read routing

ANY 1 có ba standby; remote_apply trả success. Ứng dụng có thể đọc ngẫu nhiên bất kỳ standby nào và chắc chắn thấy row không? Vì sao?

### Bài 37 — Synchronous commit stall

Nêu thứ tự điều tra khi nhiều backends chờ SyncRep.

### Bài 38 — Fallback async

Trong incident, DBA cân nhắc xóa synchronous_standby_names để giải phóng writes. Nêu tác động và thông tin cần ghi nhận.

### Bài 39 — Failure domains

Vì sao đặt mọi synchronous standby trong cùng một rack có thể làm giảm khả năng chống sự cố?

### Bài 40 — Runbook

Viết runbook ngắn để xử lý commit latency tăng sau khi synchronous standby chính bị failover sang node ở region khác.

---

## 23. Lời giải — bài 1 đến 20

### Bài 1 — synchronous replication

Nó cho phép primary chờ standby nhận WAL tới một mức acknowledgement trước khi xác nhận COMMIT. Điều này giảm nguy cơ mất acknowledged commits khi primary fail và một standby đã xác nhận được promote.

### Bài 2 — Hai tham số

synchronous_standby_names xác định standby nào tham gia và cần bao nhiêu response. synchronous_commit xác định transaction chờ remote write, remote flush hay remote apply; local/off không chờ remote acknowledgement.

### Bài 3 — Standby name

Tên phải khớp với application_name của physical replication connection, thường được đặt trong primary_conninfo trên standby.

### Bài 4 — FIRST 1

a có priority cao nhất. Nếu a disconnect và b đủ điều kiện, b có thể được chọn làm synchronous standby thay thế.

### Bài 5 — FIRST 2

Khi cả ba đủ điều kiện, a và b được chọn theo thứ tự ưu tiên. c là standby dự phòng/potential theo trạng thái selection và version.

### Bài 6 — ANY 2

Cần hai phản hồi. Nếu c disconnect nhưng a và b vẫn đủ điều kiện, quorum vẫn đạt và commit có thể tiếp tục.

### Bài 7 — Quorum

Không. ANY 2 trong ba chỉ cần hai nodes phản hồi cho commit đó; node thứ ba có thể chưa flush/replay tới cùng commit LSN.

### Bài 8 — FIRST và ANY

FIRST chọn theo priority order; ANY đợi bất kỳ num_sync nodes trong danh sách. FIRST ưu tiên node cụ thể; ANY cho phép quorum từ các nodes tương đương.

### Bài 9 — off

off không tắt WAL. Nó cho phép COMMIT trả về trước local WAL flush, nên một số commits vừa được xác nhận có thể mất khi server/OS/storage crash trước flush.

### Bài 10 — local

local chờ local WAL flush nhưng không chờ synchronous standby write/flush/apply.

### Bài 11 — remote_write

Không. Remote write chỉ xác nhận WAL đã được ghi tới OS/file layer trên standby; nếu chưa fsync/flush bền, power loss/OS crash có thể làm mất bytes đó.

### Bài 12 — on

on chờ synchronous standby flush WAL theo durability path. Nó không bắt buộc standby đã replay; replay có thể chậm hơn flush.

### Bài 13 — remote_apply

Dùng khi cần đọc lại từ standby sau write và muốn standby đã replay commit. Snapshot cũ của transaction đã mở trước commit vẫn có thể không thấy changes do MVCC snapshot semantics.

### Bài 14 — Không có synchronous standby

Không có remote standby được chọn để chờ. Khi không cấu hình synchronous standby, các mức remote không tạo remote wait; commit behavior về cơ bản dựa trên local WAL flush trừ khi synchronous_commit=off.

### Bài 15 — Không đủ quorum

COMMIT dùng on có thể chờ vì chỉ một trong hai acknowledgements yêu cầu đã có. Khôi phục node thứ hai hoặc thay đổi policy theo incident procedure.

### Bài 16 — Standby ưu tiên chậm

FIRST selection dựa vào priority và eligibility, không tự chọn node nhanh nhất. Nếu a vẫn connected/eligible, primary có thể tiếp tục chờ a dù b phản hồi nhanh hơn.

### Bài 17 — Sync state

async là asynchronous; potential là standby có thể được chọn theo priority nhưng chưa được chọn; sync là standby đang được chọn synchronous trong priority mode; quorum là node tham gia quorum-based synchronous set. Chi tiết cần xem đúng version.

### Bài 18 — Wait event

~~~sql
SELECT
    pid,
    application_name,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE wait_event = 'SyncRep';
~~~

### Bài 19 — Replication progress

sent_lsn là vị trí sender đã gửi; write_lsn là standby đã ghi; flush_lsn là standby đã flush; replay_lsn là standby đã apply/replay WAL.

### Bài 20 — Reload

synchronous_standby_names thường có thể reload, không cần restart. Dùng pg_reload_conf(), kiểm tra SHOW synchronous_standby_names, PostgreSQL logs và pg_stat_replication.sync_state.

### Bài 21 — Session override

~~~sql
BEGIN;
SET LOCAL synchronous_commit = 'remote_apply';
UPDATE app.orders
SET status = 'confirmed'
WHERE order_id = 2001;
COMMIT;
~~~

### Bài 22 — Connection pool

SET ở session level tồn tại sau transaction và có thể được giữ khi connection quay lại pool. Request sau có thể nhận một connection với commit level không mong muốn. Dùng SET LOCAL trong transaction hoặc reset session state khi trả connection về pool.

### Bài 23 — FIRST 2 latency

Transaction cần hai acknowledgements từ hai standby được chọn. Thường phải đợi node chậm hơn trong nhóm cần phản hồi, vì response thứ hai mới đủ num_sync.

### Bài 24 — ANY 2 latency

ANY 2 chỉ cần hai responses. Nếu có ba standby với latency khác nhau, hai node nhanh hơn có thể đủ quorum, thay vì phải chờ cả ba.

### Bài 25 — remote_apply chậm

Kiểm tra replay process, CPU/I/O standby, hot standby conflicts, long-running readers, recovery logs, wait events và workload cạnh tranh. Write/flush theo kịp cho thấy receive/storage có thể ổn nhưng apply chưa theo kịp.

### Bài 26 — Promotion

Node đầu danh sách FIRST chỉ là node được ưu tiên trong synchronous selection khi primary đang chạy. Sau sự cố, node đó có thể đã mất, stale hoặc không còn truy cập. Phải so sánh WAL progress và xác định node có commit WAL mới nhất trước promotion.

### Bài 27 — Quorum và failover

Không promote tùy ý. Kiểm tra receive/flush/replay LSN, timeline, sync configuration tại thời điểm sự cố, WAL continuity và fencing primary cũ. Chọn node có WAL mới nhất phù hợp với các commits đã được xác nhận.

### Bài 28 — RPO zero

Cần transaction chờ remote acknowledgement ở mức phù hợp, standby xác nhận commit, promote đúng node có WAL đó, storage giữ được WAL, primary cũ được fence và không có override local/off ngoài policy. Mục tiêu chỉ đúng trong failure model đã định.

### Bài 29 — Không thay backup

Synchronous replication cũng replicate thao tác phá hoại, lỗi logic và corruption được ghi vào WAL. Backup độc lập, retention và PITR cho phép quay về trước sự cố; standby chủ yếu phục vụ HA.

### Bài 30 — Network partition

Primary không nhận feedback nên không đủ remote acknowledgements; COMMIT có thể chờ SyncRep. Lựa chọn gồm khôi phục network/standby, chờ quorum, hoặc chuyển asynchronous theo incident policy với RPO exposure được ghi nhận.

### Bài 31 — wal_level

Physical streaming replication cần wal_level ở mức replica hoặc cao hơn theo version. minimal không cung cấp đầy đủ WAL information cần cho physical standby streaming thông thường.

### Bài 32 — application_name sai

1. SHOW synchronous_standby_names trên primary.
2. Xem pg_stat_replication.application_name.
3. Kiểm tra primary_conninfo trên standby.
4. Xác nhận exact spelling/case và tên duy nhất.
5. Kiểm tra reload/config logs.
6. Xem sync_state và sync_priority sau khi reconnect.

### Bài 33 — Quorum size

Tăng num_sync làm nhiều standby xác nhận mỗi commit, tăng số bản có WAL nhưng tăng latency và giảm khả năng commit khi nodes lỗi. Giảm num_sync tăng availability/giảm latency nhưng ít standby hơn đã xác nhận mỗi commit.

### Bài 34 — FIRST 1 so với ANY 1

FIRST 1 chọn node ưu tiên cao nhất đủ điều kiện. ANY 1 chấp nhận bất kỳ node nào trong list phản hồi. Khi node ưu tiên chậm nhưng vẫn connected, FIRST có thể tiếp tục chờ nó; ANY có thể dùng node phản hồi nhanh khác.

### Bài 35 — Read-after-write

Với on, standby đã flush WAL nhưng có thể chưa replay. Đọc từ primary, dùng remote_apply cho transaction cần read-after-write trên standby, hoặc chờ replay tới commit LSN. Không dùng sleep cố định như một bảo đảm.

### Bài 36 — remote_apply và read routing

Không. ANY 1 chỉ chờ một standby trong quorum list replay. Standby khác có thể chưa replay tới commit. Ứng dụng phải route tới node đã đáp ứng hoặc đọc primary/chờ từng node tới LSN cần thiết.

### Bài 37 — Synchronous commit stall

1. Xác định backend chờ SyncRep.
2. Kiểm tra synchronous_standby_names và synchronous_commit.
3. Xem pg_stat_replication và sync_state.
4. So sánh sent/write/flush/replay LSN.
5. Kiểm tra network và logs.
6. Kiểm tra standby storage/replay bottleneck.
7. Khôi phục quorum hoặc thay đổi policy theo incident process.

### Bài 38 — Fallback async

Xóa synchronous_standby_names làm mất remote synchronous wait cho các commits tiếp theo; commit dựa trên local behavior. Cần ghi phê duyệt, thời điểm, cluster, transactions/workloads, RPO exposure, lý do, thời điểm bật lại và kết quả xác nhận sync state.

### Bài 39 — Failure domains

Một rack failure có thể làm primary và tất cả standbys cùng mất. Đặt nodes trong failure domains độc lập giúp giảm correlated failure, dù cần cân bằng latency và network reliability.

### Bài 40 — Runbook sau failover sang region xa

1. Đo commit latency p50/p95/p99 và xác định thời điểm thay đổi.
2. Kiểm tra pg_stat_replication, sync_state và standby đang được chọn.
3. Đo RTT, packet loss và standby flush latency ở region mới.
4. Kiểm tra quorum/priority list và num_sync.
5. Xác định node cũ có thể trở lại hay không; tránh tự động đổi selection thiếu kiểm soát.
6. Nếu topology cho phép, khôi phục standby gần primary theo kế hoạch và xác minh catch-up.
7. Thay đổi synchronous policy chỉ khi đánh giá RPO/availability và có phê duyệt.
8. Chạy workload test, xác nhận latency và failover readiness.
9. Cập nhật topology/runbook và theo dõi sau incident.

---

## 24. Tổng kết

synchronous_standby_names và synchronous_commit phải được thiết kế cùng nhau. Một tham số chọn nhóm standby và số phản hồi; tham số còn lại xác định transaction phải đợi write, flush hay replay. Lựa chọn ảnh hưởng trực tiếp đến durability, commit latency và khả năng tiếp tục writes khi standby/network gặp sự cố.

Các nguyên tắc quan trọng:

1. FIRST là priority-based selection; ANY là quorum-based selection.
2. FIRST 1 (a,b) ưu tiên a, có thể chuyển sang b khi a không còn eligible.
3. ANY 2 (a,b,c) cần hai phản hồi bất kỳ; node thứ ba có thể chưa xác nhận commit đó.
4. Standby name phải khớp application_name trên physical replication connection.
5. off không chờ local WAL flush; local chờ local flush; remote_write chờ remote OS write; on chờ remote flush; remote_apply chờ replay.
6. remote_write có mức bảo vệ yếu hơn remote flush trước OS/power failure trên standby.
7. remote_apply hỗ trợ read-after-write trên standby với snapshot mới, nhưng không khiến mọi standby trong quorum đồng bộ ngay lập tức.
8. Không đủ num_sync standby có thể khiến COMMIT chờ; đó là trade-off giữa write availability và synchronous durability.
9. pg_stat_replication và pg_stat_activity là hai nơi quan trọng để quan sát sync state và SyncRep wait.
10. LSN write/flush/replay phải được đọc riêng; một chỉ số lag không đại diện mọi acknowledgement level.
11. FIRST không tự chọn standby nhanh nhất; ANY có thể dùng responses nhanh nhất đủ quorum.
12. Promotion phải dựa trên WAL progress/timeline và fencing; không chỉ theo thứ tự cấu hình.
13. Synchronous replication không thay backup, WAL archive và PITR.
14. Không tuyên bố RPO bằng 0 nếu không xác định failure model, commit level, standby được promote và các transaction overrides.
15. Thay đổi cấu hình cần reload, kiểm tra trạng thái thực tế và đo commit latency.
16. Nếu cần fallback asynchronous trong incident, ghi rõ thời gian và RPO exposure, rồi xác minh bật lại synchronous policy.

Quy trình lựa chọn: **xác định RPO/RTO và failure domains → chọn FIRST hay ANY → chọn num_sync theo số node và availability cần giữ → chọn synchronous_commit theo durability/read visibility → đo latency dưới tải → diễn tập standby failure và promotion → giám sát SyncRep, sync_state và LSN progress liên tục**.
