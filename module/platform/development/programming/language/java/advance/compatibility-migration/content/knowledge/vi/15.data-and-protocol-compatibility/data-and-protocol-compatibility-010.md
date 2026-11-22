# Phối hợp thay đổi schema theo cách mở rộng trước, thu hẹp sau

Trong chủ đề **Java Advance Compatibility Migration**, một đợt nâng JDK, framework, ORM, serializer hoặc giao thức có thể phải đi kèm thay đổi dữ liệu. Thao tác đổi tên một cột, đặt một constraint mới hay thay tên thuộc tính JSON tưởng đơn giản, nhưng sẽ nguy hiểm nếu các phiên bản ứng dụng cũ và mới vẫn cùng hoạt động.

Chiến lược **expand-and-contract** — *mở rộng trước, thu hẹp sau* — cho phép các thành phần chuyển đổi qua một khoảng tương thích, thay vì yêu cầu mọi producer, consumer và database thay đổi chính xác cùng một thời điểm.

**Nguyên tắc:** mở rộng schema theo cách không phá consumer cũ, di chuyển code và dữ liệu qua các mốc được kiểm chứng, rồi chỉ thu hẹp khi không thành phần được hỗ trợ nào còn phụ thuộc cấu trúc cũ.

Bài học thuộc nhóm **Dữ liệu và giao thức**. Trọng tâm là phối hợp database, HTTP/JSON, event, Avro/Protobuf và các consumer Java độc lập. Expand-and-contract không phải phép bảo đảm rằng một thay đổi bất kỳ đều tương thích. Nó là quy trình quản lý sự cùng tồn tại, tính nhất quán và thời điểm cho phép một breaking change.

## 1. Vì sao một lần đổi schema có thể phá hệ thống?

Giả sử phiên bản A của ứng dụng Java đọc cột **customer_name**:

~~~sql
CREATE TABLE customer_profile (
    id BIGINT PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL
);
~~~

Phiên bản B muốn đổi tên thành **recipient_name**. Nếu áp dụng trực tiếp:

~~~sql
ALTER TABLE customer_profile
    RENAME COLUMN customer_name TO recipient_name;
~~~

các container A còn chạy có thể thất bại khi thực thi SQL hoặc nạp entity có mapping cũ. Nếu triển khai B trước khi đổi schema, B lại có thể thất bại vì cột recipient_name chưa tồn tại.

Một giai đoạn rollout thường trông như sau:

~~~text
Thời gian ------------------------------------------>

App A:     [old][old][old] ---> drain
App B:          [new][new][new][new]
Batch A:            [chạy theo lịch]
Queue:     [events cũ][events cũ + mới]
Database:  [cùng một schema dùng chung]
~~~

Ngay cả khi các HTTP instance cũ đã dừng, queue còn message cũ hoặc một batch cũ chỉ chạy mỗi tuần vẫn có thể phụ thuộc hợp đồng dữ liệu trước migration.

### 1.1. Schema không chỉ là database

| Loại schema | Ví dụ thay đổi | Consumer bị ảnh hưởng |
|---|---|---|
| SQL database | Rename/drop column, đổi type, NOT NULL | Repository, ORM, report, batch |
| JSON/REST | Rename field, đổi required/optional | Mobile/web client, partner |
| XML | Thay element, namespace, schema | Parser, integration adapter |
| Event/message | Thêm field hoặc message version | Producer, Kafka consumer, replay |
| Avro | Field/default/schema registry compatibility | Stream processor, serializer |
| Protobuf | Field number, oneof, enum | gRPC client/service |
| Cache/session | Key/shape của object lưu tạm | Nhiều phiên bản runtime |
| File/snapshot | Định dạng dữ liệu lịch sử | Import/export, recovery job |

Cùng một thuộc tính Java có thể xuất hiện ở nhiều biên. Thay tên **recipientName** trong entity không tự động đổi JSON contract, event payload hoặc native SQL của một hệ thống khác.

### 1.2. Các loại tương thích cần phân biệt

- **Source compatibility:** mã nguồn cũ còn biên dịch được với API mới?
- **Binary compatibility:** class/JAR đã biên dịch có liên kết được với dependency mới?
- **Data compatibility:** dữ liệu cũ/mới có được đọc, ghi và diễn giải đúng?
- **Protocol compatibility:** producer và consumer khác phiên bản có giao tiếp được?
- **Behavioral compatibility:** cùng dữ liệu có còn dẫn đến kết quả nghiệp vụ đúng?
- **Operational compatibility:** các phiên bản có cùng chạy và rollback được?

Expand-and-contract chủ yếu xử lý tương thích dữ liệu, giao thức và vận hành. Nó không tự giải quyết lỗi binary khi JDK hoặc framework thay đổi class/method.

## 2. Ba pha: Expand, Migrate/Coexist, Contract

### 2.1. Expand — bổ sung trước, không phá trước

Pha **expand** chuẩn bị cấu trúc mới nhưng giữ cấu trúc cũ còn dùng được:

- Thêm cột nullable.
- Thêm bảng mới song song bảng cũ.
- Thêm thuộc tính optional vào payload.
- Thêm message version hoặc endpoint mới.
- Thêm index cho đường query mới.
- Cho consumer hiểu kiểu/field mới trước khi producer phát nó.
- Triển khai reader có thể nhận cả payload cũ và mới.

Lựa chọn cụ thể phải phù hợp database và giao thức. Một field mới trong JSON không luôn tương thích với client sử dụng strict validation. Một cột mới có thể ảnh hưởng câu **SELECT *** hoặc mapper dựa trên thứ tự column.

### 2.2. Migrate/Coexist — di chuyển dần, giữ nhất quán

Trong giai đoạn chuyển tiếp:

- Backfill dữ liệu lịch sử.
- Xác định source of truth.
- Bảo đảm dữ liệu ghi bởi writer cũ và mới không mâu thuẫn.
- Chuyển reader/consumer sang schema mới.
- Theo dõi fallback và mismatch.
- Kiểm thử các tổ hợp phiên bản.
- Giữ đường rollback phù hợp.

Đây thường là pha tốn nhiều công sức nhất. Nếu chỉ thêm cột mới rồi gọi đó là expand-and-contract, nhóm chưa giải quyết được bài toán dữ liệu cập nhật đồng thời.

### 2.3. Contract — bỏ phần cũ khi đã hết phụ thuộc

Contract có thể gồm:

- Xóa cột/bảng cũ.
- Áp NOT NULL hoặc constraint cuối.
- Loại bỏ property JSON cũ.
- Dừng publish event v1.
- Loại field cũ khỏi schema công bố.
- Xóa fallback, dual-write, trigger đồng bộ và code adapter.
- Ngừng chấp nhận các định dạng legacy không còn được hỗ trợ.

**Contract phải là mốc riêng có điều kiện Go/No-Go**, không chỉ là bước SQL cuối trong cùng một deployment.

~~~text
Baseline
  DB: customer_name
  App A: đọc/ghi customer_name
           |
           v
EXPAND
  DB: customer_name + recipient_name
  App A vẫn hoạt động
           |
           v
COEXIST / MIGRATE
  App B hiểu cả hai
  Đồng bộ writer + backfill + reconciliation
           |
           v
CUTOVER
  Không còn app/job cần customer_name
  New source of truth = recipient_name
           |
           v
CONTRACT
  Gỡ legacy reader/writer
  Bỏ customer_name khi rollback window cho phép
           |
           v
Target
~~~

## 3. Tương thích khi nhiều phiên bản cùng chạy

Giả sử có ba năng lực ứng dụng:

- **A:** chỉ đọc/ghi customer_name.
- **B:** hiểu cả customer_name và recipient_name.
- **C:** chỉ đọc/ghi recipient_name.

| Application | Schema cũ | Schema expanded | Schema contracted |
|---|---|---|---|
| A | Hợp lệ | Thường hợp lệ nếu cột cũ còn | Không còn được hỗ trợ |
| B | Có thể lỗi nếu query bắt buộc cột mới | Hợp lệ trong giai đoạn chuyển tiếp | Có thể lỗi nếu còn query cột cũ |
| C | Không hợp lệ | Hợp lệ khi dữ liệu đã sẵn sàng | Hợp lệ ở target |

Vì vậy thứ tự điển hình là:

1. Expand database.
2. Deploy B với khả năng tương thích.
3. Backfill và quản lý mọi writer đang hoạt động.
4. Cutover sang C.
5. Quan sát và xác nhận không còn A/B cần cột cũ.
6. Contract.

Nếu bỏ qua bước 3, ứng dụng có thể chạy được nhưng đọc dữ liệu sai. Nếu bỏ qua bước 5, rollback hoặc batch cũ có thể thất bại sau khi drop cột.

### 3.1. Không dùng chỉ số version làm bằng chứng

Hai artifact cùng ghi **version 2.3** có thể khác cấu hình feature flag và behavior. Một consumer v1.9 chạy trong batch có thể chỉ hoạt động mỗi tháng.

Theo dõi **capability** cụ thể: consumer nào đọc trường nào, writer nào có thể tạo dữ liệu mới, job nào cần schema cũ, và chúng còn trong phạm vi hỗ trợ hay không.

## 4. Ví dụ PostgreSQL: đổi tên cột mà vẫn hỗ trợ rollback

Giả sử muốn chuyển từ **customer_name** sang **recipient_name**. Các ví dụ SQL dưới đây minh họa PostgreSQL; không áp dụng nguyên xi cho mọi database hoặc version.

### 4.1. Mốc E1: mở rộng schema

~~~sql
ALTER TABLE customer_profile
    ADD COLUMN recipient_name VARCHAR(200);
~~~

Cột mới tạm thời cho phép null. Cột cũ vẫn còn để ứng dụng A chạy.

Không thêm **NOT NULL** cho cột mới ngay nếu writer A chưa biết nó. Không drop hoặc rename customer_name trong migration này.

**Lưu ý vận hành:** DDL có thể cần lock, ảnh hưởng transaction đang chạy và replication. Thời gian/tải tùy database version, kích thước bảng, constraint và cách triển khai. Cần đánh giá trên workload đại diện.

### 4.2. Mốc E2: entity hỗ trợ cả hai tên

Ví dụ JPA với mapping chuyển tiếp:

~~~java
package com.example.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_profile")
public class CustomerProfile {
    @Id
    private Long id;

    @Column(name = "customer_name")
    private String legacyCustomerName;

    @Column(name = "recipient_name")
    private String recipientName;

    protected CustomerProfile() {
    }

    public String displayName() {
        return recipientName != null
            ? recipientName
            : legacyCustomerName;
    }

    public void changeName(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("name");
        }
        legacyCustomerName = value;
        recipientName = value;
    }
}
~~~

Đây là cách biểu diễn tạm **dual-read/dual-write** khi code B thực hiện thay đổi. Nó chưa đủ để bảo đảm hai cột đồng bộ nếu code A vẫn đang cập nhật cột cũ.

### 4.3. Mốc M1: backfill dữ liệu cũ

Ví dụ cập nhật theo batch khóa chính:

~~~sql
UPDATE customer_profile
SET recipient_name = customer_name
WHERE recipient_name IS NULL
  AND id >= 100001
  AND id < 110001;
~~~

Hệ thống lớn thường cần chạy nhiều batch có giới hạn, checkpoint và throttle. Không mặc định một UPDATE toàn bảng là an toàn khi production đang có tải.

Các thuộc tính cần có:

- **Idempotent:** có thể chạy lại sau failure.
- **Resumable:** có thể bắt đầu từ checkpoint phù hợp.
- **Bounded:** batch không giữ lock/transaction quá lâu.
- **Observable:** có số lượng, tốc độ, lỗi và dữ liệu còn lại.
- **Conflict-aware:** không ghi đè dữ liệu mới hợp lệ.
- **Auditable:** biết job version và khoảng dữ liệu đã xử lý.

Lệnh trên chỉ cập nhật khi recipient_name chưa có giá trị. Nó không xử lý trường hợp writer A thay customer_name sau khi recipient_name đã được backfill.

### 4.4. Phản ví dụ: COALESCE có thể đọc dữ liệu cũ

~~~text
T0: customer_name = "An";  recipient_name = "An"
T1: App A đổi customer_name thành "Bình"
T2: recipient_name vẫn là "An"
T3: App B dùng COALESCE(recipient_name, customer_name)
T4: App B trả về "An" (stale)
~~~

**COALESCE** tìm giá trị không null đầu tiên; nó không biết giá trị nào cập nhật gần nhất.

Điều tương tự xảy ra nếu code B luôn ưu tiên recipient_name khi hai cột bất đồng. Fallback chỉ xử lý **missing values**, không giải quyết vấn đề **freshness/concurrency**.

### 4.5. Chọn một chiến lược đồng bộ writer

| Chiến lược | Điều kiện sử dụng | Rủi ro cần kiểm thử |
|---|---|---|
| Cutover single writer | Có thể ngừng writer A trước khi B ghi schema mới | Khoảng chuyển đổi và rollback |
| Database trigger đồng bộ | Có thể kiểm soát DDL, row update và transaction | Recursion, lock, conflict, logic cập nhật |
| Service ghi chung | Mọi writer đi qua service hỗ trợ cả hai field | Legacy batch/direct SQL bypass |
| CDC/event đồng bộ | Có pipeline theo dõi thay đổi đáng tin cậy | Lag, ordering, duplicate, retry |
| Version/optimistic locking | Có version đáng tin cậy cho cập nhật | Lost update, conflict resolution |
| Reconciliation định kỳ | Cho phép cửa sổ sai khác được kiểm soát | Stale reads trong khoảng trễ |

Đối với dữ liệu quan trọng, lựa chọn phải dựa trên đặc tính update thực tế. Ví dụ trigger đơn giản "luôn copy cột cũ sang cột mới" sẽ phá thao tác writer B cập nhật cột mới nếu không thiết kế hướng đồng bộ.

**Không có một đoạn SQL dual-write nào đúng cho mọi hệ thống.** Cần xác định single source of truth, thứ tự conflict và giao thức rollback trước khi áp dụng.

### 4.6. Mốc M2: đối soát dữ liệu

Ví dụ:

~~~sql
SELECT COUNT(*) AS missing_new_value
FROM customer_profile
WHERE recipient_name IS NULL;
~~~

Với hai cột mang cùng ý nghĩa, PostgreSQL cho phép tìm sai khác kể cả null:

~~~sql
SELECT COUNT(*) AS mismatch
FROM customer_profile
WHERE customer_name IS DISTINCT FROM recipient_name;
~~~

Kết quả **0** tại một thời điểm chưa đủ nếu writer A vẫn có thể tạo sai khác mới. Cần theo dõi metric liên tục và có một vòng đối soát trước cutover.

Nếu schema mới thay đổi ý nghĩa dữ liệu, không dùng so sánh trực tiếp. Hãy xây dựng invariant hoặc hàm chuyển đổi được công bố, ví dụ chuẩn hóa đơn vị tiền tệ hoặc mô hình địa chỉ mới.

### 4.7. Mốc C1: chuyển reader và đặt constraint

Sau khi tất cả writer tuân thủ dữ liệu mới và backfill đạt:

~~~sql
ALTER TABLE customer_profile
    ALTER COLUMN recipient_name SET NOT NULL;
~~~

Đây vẫn là DDL có thể tác động lock/scan tùy version. Đặt constraint sau khi xác nhận writer cũ không tiếp tục insert null và dữ liệu lịch sử đã đạt điều kiện.

Sau đó có thể triển khai code C đọc/ghi recipient_name, nhưng vẫn chưa nên xóa cột cũ khi cần rollback về A hoặc B.

### 4.8. Mốc C2: thu hẹp

Chỉ khi không còn consumer hỗ trợ cũ:

~~~sql
ALTER TABLE customer_profile
    DROP COLUMN customer_name;
~~~

Thao tác này có thể khiến app A hoàn toàn không chạy được. Cần được tách ra khỏi release mở rộng ban đầu, có quyết định Go/No-Go, backup và kế hoạch phục hồi phù hợp.

## 5. Nhiều dạng biến đổi schema hơn một lần rename

### 5.1. Thêm trường required

Muốn thêm **order_status NOT NULL**, nhưng writer cũ chưa cung cấp:

1. Add cột nullable hoặc default có chủ đích.
2. Deploy writer mới bắt đầu ghi status.
3. Backfill dữ liệu lịch sử.
4. Xác nhận không còn writer cũ vi phạm.
5. Kiểm tra bản ghi null và business invariant.
6. Bổ sung NOT NULL trong mốc sau.

Default kỹ thuật không tự bảo đảm giá trị có ý nghĩa nghiệp vụ. Gán tất cả order cũ thành **COMPLETED** vì dễ viết migration có thể tạo dữ liệu sai.

### 5.2. Đổi kiểu số hoặc ID

Ví dụ đổi **INT** sang **BIGINT**, hoặc tiền từ floating-point sang **DECIMAL**:

- Expand cột mới.
- Xác định phép chuyển đổi có mất precision/overflow hay không.
- Backfill theo batch và đối chiếu tổng.
- Chuyển code Java/JDBC mapping.
- Kiểm tra JSON/message type nếu giá trị đi ra ngoài DB.
- Không contract cho đến khi mọi consumer hiểu representation mới.

Một DDL đổi kiểu trực tiếp đôi khi phù hợp trên hệ thống nhỏ, nhưng cần xem lock, time, data range và sự cùng tồn tại của ứng dụng cũ.

### 5.3. Tách một trường thành nhiều trường

Ví dụ đổi **full_name** sang **first_name** và **last_name**:

~~~sql
ALTER TABLE person
    ADD COLUMN first_name VARCHAR(100);

ALTER TABLE person
    ADD COLUMN last_name VARCHAR(100);
~~~

Phép tách tên không phải lúc nào cũng duy nhất. Một số dữ liệu không thể phân tách chính xác. Cần định nghĩa semantics của trường mới, trạng thái unknown và cách duy trì consumer cũ. Không coi đây chỉ là thay đổi kỹ thuật của JPA mapping.

### 5.4. Thêm unique constraint

Trước khi thêm **UNIQUE(email)**:

- Khảo sát dữ liệu trùng.
- Định nghĩa quy tắc hợp nhất/xử lý.
- Triển khai writer mới có thể xử lý conflict.
- Kiểm tra race giữa hai transaction cùng insert.
- Chọn cách tạo index/constraint phù hợp với DB.
- Test exception mapping và retry behavior.

Validation trong Java không tự thay thế ràng buộc DB nếu nhiều writer đồng thời.

### 5.5. Tách bảng

Ví dụ **shipping_address** chuyển từ cột trong orders sang bảng **order_address**:

~~~text
orders.shipping_address
          |
          v
Expand: tạo order_address, giữ cột cũ
          |
          v
Migrate: ghi/đọc song song với đồng bộ phù hợp
          |
          v
Backfill + xác nhận từng order có address đúng
          |
          v
Cutover queries và ORM mappings
          |
          v
Contract: bỏ cột cũ
~~~

Cần test transaction, dữ liệu orphan, foreign key và hiệu năng join. Với bảng nhiều dữ liệu, thiết kế batch/reindex và độ trễ replication.

## 6. HTTP/JSON: thay field theo cách tương thích

Response cũ:

~~~json
{
  "orderId": "O-100",
  "customerName": "An"
}
~~~

Response mục tiêu:

~~~json
{
  "orderId": "O-100",
  "recipientName": "An"
}
~~~

Đổi trực tiếp có thể khiến client cũ không tìm thấy customerName.

### 6.1. Expand bằng dual-field response

Trong giai đoạn chuyển tiếp:

~~~json
{
  "orderId": "O-100",
  "customerName": "An",
  "recipientName": "An"
}
~~~

Client cũ tiếp tục đọc customerName; client mới chuyển sang recipientName.

Nhưng một client dùng strict deserializer hoặc schema validator có thể từ chối unknown fields. Vì vậy, cần test consumer cũ thật sự; **thêm optional field không phải mặc định an toàn trong mọi giao thức**.

### 6.2. Chấp nhận request cũ và mới

Server có thể chấp nhận:

~~~json
{"customerName":"An"}
~~~

hoặc:

~~~json
{"recipientName":"An"}
~~~

Phải xác định trường hợp cả hai cùng có nhưng khác giá trị:

~~~json
{
  "customerName": "An",
  "recipientName": "Bình"
}
~~~

Các phương án gồm reject conflict, chọn precedence có tài liệu hoặc yêu cầu một API version tách biệt. Không nên âm thầm chọn giá trị dựa trên thứ tự field trong JSON khi đó là dữ liệu quan trọng.

### 6.3. Jackson alias

Ví dụ hỗ trợ tên cũ khi deserialize:

~~~java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public record RecipientRequest(
    @JsonProperty("recipientName")
    @JsonAlias("customerName")
    String recipientName
) {
}
~~~

**@JsonAlias** hỗ trợ tên thay thế ở chiều đọc; không tự động tạo response có cả tên cũ và mới. Nếu muốn dual-field response, thiết kế DTO và serialization contract riêng.

Nếu client gửi cả alias lẫn canonical name, cần policy conflict rõ thay vì dựa vào hành vi tình cờ của mapper.

### 6.4. Không chỉ thay tên, còn phải giữ semantics

Consumer quan tâm:

- Required/optional.
- Null so với field vắng mặt.
- Kiểu number/string.
- Enum và các giá trị mới.
- Default.
- Ý nghĩa nghiệp vụ.
- HTTP status/error code.
- Quy tắc authorization.
- Khả năng retry và idempotency.

Một field mới có đúng kiểu String nhưng thay ý nghĩa từ "tên chủ tài khoản" sang "tên người nhận" có thể gây lỗi nghiệp vụ dù parser vẫn chạy.

## 7. Event schema và nhiều consumer độc lập

Với queue hoặc Kafka, event có thể được lưu và replay sau khi producer cũ đã dừng.

~~~text
Producer A ----+
               |
               +--> Topic/Queue --> Consumer A
               |                --> Consumer B
Producer B ----+                --> Batch/replay
~~~

Thời gian coexist phải xét:

- Event retention.
- Consumer lag.
- Dead-letter queue.
- Replay/reprocessing.
- Consumer offline.
- Đối tác có chu kỳ phát hành khác.
- Schema registry compatibility mode.
- Dữ liệu lịch sử đã lưu.

### 7.1. Consumer-first khi thêm field/giá trị mới

Một cách tổ chức phổ biến:

1. Thiết kế schema mới và cách consumer cũ xử lý unknown fields.
2. Nâng consumer để hiểu payload mới.
3. Xác nhận producer A vẫn được các consumer mới hỗ trợ.
4. Chỉ sau đó cho producer B phát field/giá trị mới.
5. Theo dõi decode errors, lag, DLQ và business invariants.
6. Dừng field/event cũ khi hết support/replay window.

Nếu consumer cũ không hiểu payload mới và không thể nâng kịp, có thể phải duy trì event v1 hoặc topic version mới. Lựa chọn phụ thuộc semantics và chi phí vận hành.

### 7.2. Dual-publish cần chống duplicate

Producer phát cả event V1 và V2 có thể khiến consumer đăng ký cả hai xử lý cùng một giao dịch hai lần.

Cần:

- Stable business event ID.
- Idempotent consumer.
- Quy tắc deduplication.
- Kế hoạch chuyển subscription.
- Xác định một sự kiện nghiệp vụ có bao nhiêu representation.
- Kế hoạch replay không lặp side effect.

**Hai message version không tự động đại diện cho hai sự kiện nghiệp vụ khác nhau.**

### 7.3. Transactional outbox

Nếu ứng dụng phải cập nhật DB và publish event, hai thao tác có thể không cùng transaction:

~~~text
UPDATE database: success
PUBLISH event: failure
=> Database và event không đồng bộ
~~~

Transactional outbox ghi business update cùng outbox record trong một transaction DB, sau đó publisher chuyển outbox record tới broker. Consumer vẫn cần xử lý duplicate vì delivery có thể lặp.

Expand-and-contract giúp schema coexist, nhưng không thay thế thiết kế consistency, ordering và retry của hệ thống phân tán.

## 8. Avro và Schema Registry

Avro dùng writer schema và reader schema để diễn giải payload. Khi thêm field, một default phù hợp có thể giúp reader mới xử lý dữ liệu cũ.

Schema ban đầu:

~~~json
{
  "type": "record",
  "name": "OrderEvent",
  "namespace": "com.example.event",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "customerName", "type": "string"}
  ]
}
~~~

Schema expanded:

~~~json
{
  "type": "record",
  "name": "OrderEvent",
  "namespace": "com.example.event",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "customerName", "type": "string"},
    {"name": "recipientName", "type": ["null", "string"], "default": null}
  ]
}
~~~

Default null có thể hỗ trợ reader mới khi đọc record cũ thiếu recipientName, nhưng logic nghiệp vụ vẫn phải quyết định fallback và validation.

### 8.1. Phân biệt chiều tương thích

| Khái niệm | Ý nghĩa |
|---|---|
| Backward | Reader mới đọc dữ liệu do writer cũ tạo |
| Forward | Reader cũ đọc dữ liệu do writer mới tạo |
| Full | Hai chiều theo chính sách được định nghĩa |
| Transitive | Kiểm tra tương thích với nhiều phiên bản lịch sử, không chỉ liền trước |

Tên mode và mức enforcement cụ thể thuộc schema registry đang dùng. Không mặc định một mode **BACKWARD** là đủ nếu rolling deployment cần producer B phát dữ liệu cho consumer A.

### 8.2. Schema hợp lệ chưa chắc business logic hợp lệ

Reader mới có thể parse thành công event có recipientName null, nhưng nếu business code v2 luôn dùng recipientName như required, chương trình vẫn có thể thất bại.

Cần test:

- Old payload → new reader.
- New payload → old reader, nếu cùng tồn tại.
- Default/null semantics.
- Trường cũ/mới mâu thuẫn.
- Unknown enum.
- Replayed event từ nhiều release.
- Consumer batch với payload lịch sử.

## 9. Protocol Buffers: không tái sử dụng field number

Protobuf gắn field trên wire với **field number**. Khi xóa một field, không nên tái sử dụng number cho ý nghĩa khác.

Ví dụ v1:

~~~proto
syntax = "proto3";

package example.orders;

message Order {
  string order_id = 1;
  string customer_name = 2;
}
~~~

Expand:

~~~proto
syntax = "proto3";

package example.orders;

message Order {
  string order_id = 1;
  string customer_name = 2 [deprecated = true];
  string recipient_name = 3;
}
~~~

Ở giai đoạn chuyển tiếp, producer/consumer có thể đọc cả hai field. Cần quy tắc khi giá trị khác nhau.

Sau contract, giữ định danh cũ ở trạng thái reserved:

~~~proto
syntax = "proto3";

package example.orders;

message Order {
  reserved 2;
  reserved "customer_name";

  string order_id = 1;
  string recipient_name = 3;
}
~~~

**Không dùng số 2 cho một field mới có semantics khác.** Consumer cũ có thể diễn giải dữ liệu mới sai mà không phát hiện lỗi parse.

### 9.1. Presence và giá trị mặc định

Trong Protobuf, cần phân biệt trường vắng mặt với giá trị mặc định theo cơ chế presence cụ thể. Với proto3, một scalar như chuỗi rỗng hoặc số 0 không luôn chứng minh producer đã chủ động gán giá trị.

Nếu nghiệp vụ cần phân biệt missing/explicit, dùng **optional** hoặc shape phù hợp và test codegen/consumer versions liên quan. Không áp required semantics chỉ từ giả định về giá trị mặc định.

## 10. Vai trò của Java, Spring Boot, Hibernate và migration tools

Nâng JDK không tự động làm đổi database schema. Nhưng migration Java thường kéo theo nâng Spring, Hibernate/Jakarta Persistence, JDBC driver, Jackson và Flyway/Liquibase.

Những thay đổi có thể ảnh hưởng:

- Naming strategy trong ORM.
- Kiểu dữ liệu và mapping.
- Enum persistence.
- DDL được framework gợi ý.
- Query generation.
- Default serialization.
- Schema validation trong ứng dụng.
- Cách lấy connection/transaction.

Vì thế cần tách **thay đổi code/runtime** khỏi **thay đổi schema**, với thứ tự thực thi có kiểm soát.

### 10.1. Thứ tự tham khảo

~~~text
Inventory producers/consumers
           |
           v
Expand schema additive
           |
           v
Deploy compatible application
           |
           v
Backfill + đồng bộ dữ liệu
           |
           v
Cutover readers/writers
           |
           v
Verify no legacy consumers
           |
           v
Contract schema
~~~

Các bước có thể gồm nhiều release. Một trạng thái kỹ thuật giữa đường có thể chỉ là checkpoint test, không nhất thiết phải chạy production dài hạn.

### 10.2. Flyway

Ví dụ:

~~~text
V101__add_recipient_name.sql
V102__support_recipient_name_index.sql
V103__enforce_recipient_name_not_null.sql
V104__drop_customer_name.sql
~~~

**Tách file không đủ** nếu migration runner áp dụng tất cả phiên bản chưa chạy trong cùng một startup. Phải quản lý release gate: chỉ phân phối/cho chạy script contract khi đã đủ điều kiện sau coexist/cutover.

### 10.3. Liquibase

Liquibase changesets cũng phải chia theo mốc triển khai và preconditions phù hợp. Rollback script cho DDL không đồng nghĩa khôi phục được dữ liệu đã mất sau **DROP COLUMN**.

### 10.4. Không để ORM tự phá schema production

Các cấu hình schema generation/auto-DDL cần được quản lý chặt. Tránh để ứng dụng mới tự đổi/drop schema khi khởi động mà không có quyết định rõ, vì app A đang chạy vẫn có thể cần cột cũ.

Production migration nên có artifact/script có version, owner, review, evidence và kế hoạch phục hồi.

## 11. Backfill ở quy mô lớn

Một backfill production cần hơn câu lệnh UPDATE đúng cú pháp.

### 11.1. Các yêu cầu

- **Idempotency:** chạy lại sau crash không tạo giá trị sai.
- **Batching:** giới hạn rows/time/transaction.
- **Checkpoint:** biết tiến độ và cách resume.
- **Throttling:** tránh quá tải I/O, CPU, WAL/binlog.
- **Concurrency control:** xử lý update từ writer đang chạy.
- **Reconciliation:** kiểm chứng dữ liệu đã chuyển.
- **Observability:** có logs, metrics và alert.

### 11.2. Các nguy cơ vận hành

Một UPDATE lớn có thể gây lock contention, transaction log tăng, replication lag hoặc làm query production chậm. Chọn batch size theo tải thực tế; không dùng một con số cố định cho mọi bảng.

Nếu dùng primary key window:

~~~sql
UPDATE customer_profile
SET recipient_name = customer_name
WHERE recipient_name IS NULL
  AND id > 200000
  AND id <= 210000;
~~~

job có thể lưu last processed key, nhưng **watermark không thay thế đối soát**. Update phát sinh sau khi batch đi qua có thể tạo mismatch mới. Cần kiểm tra lại theo invariant sau khi writer đã được điều phối.

### 11.3. Không overwrite giá trị mới

Lệnh nguy hiểm:

~~~sql
UPDATE customer_profile
SET recipient_name = customer_name;
~~~

có thể xóa giá trị recipient_name hợp lệ do code B mới ghi. Ngay cả điều kiện **WHERE recipient_name IS NULL** cũng không đủ nếu writer A vẫn thay customer_name ở row đã backfill.

Giải pháp phải bắt đầu từ chiến lược đồng bộ writer, không chỉ tinh chỉnh câu SQL.

### 11.4. Xác minh tổng hợp và lấy mẫu

Ví dụ PostgreSQL:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(recipient_name) AS filled_rows,
    COUNT(*) FILTER (WHERE recipient_name IS NULL) AS missing_rows
FROM customer_profile;
~~~

Có thể dùng sampling, reconciliation theo ID, so sánh hash đã chuẩn hóa hoặc các invariant nghiệp vụ. Hai bộ dữ liệu có cùng số dòng không nhất thiết có nội dung tương đương.

## 12. Rollback ở mỗi pha

| Trạng thái | Có thể rollback application? | Điều kiện data |
|---|---|---|
| Trước expand | Về baseline | Dữ liệu cũ chưa thay |
| Sau expand | Thường dễ hơn | Cột cũ vẫn tồn tại |
| Coexist | Có thể, nếu writer/new data còn được old code hiểu | Cần giữ đồng bộ và format cũ |
| Sau cutover | Không tự động | Dữ liệu mới có thể không biểu diễn được trong schema cũ |
| Sau contract | Old app thường không còn chạy | Phục hồi cột/data có thể cần backup/forward-fix |

**Rollback code không đồng nghĩa rollback dữ liệu.**

Nếu B đã phát event mới hoặc ghi giá trị không hợp lệ với A, chỉ redeploy A có thể gây lỗi. Tương tự, không nên drop cột mới chỉ để khôi phục code cũ trong lúc incident nếu phần expand vẫn an toàn và có thể giữ nguyên.

### 12.1. Feature flag không phải thuốc chữa mọi vấn đề

Feature flag có thể hỗ trợ chuyển read path hoặc write path nhưng:

- Không khôi phục dữ liệu đã drop.
- Không xóa event đã publish.
- Không đảm bảo writer A hiểu value mới.
- Không thay thế migration hồi phục dữ liệu.

Cần xác định rõ những điểm **không thể quay lại đơn giản**.

### 12.2. Runbook rollback nên có

~~~text
Rollback candidate artifact:
Current schema version:
Old schema fields still available:
New-only data already written:
Old app understands new-only data: yes/no
Producer versions to pause:
Queue/DLQ/replay plan:
Backups and restore location:
Forward-fix option:
Go/No-Go owner:
Evidence:
~~~

## 13. Ma trận kiểm thử cần chạy

### 13.1. Ứng dụng với DB schema

| Test | Application | DB schema | Mục tiêu |
|---|---|---|---|
| T1 | Old A | Old | Baseline |
| T2 | Old A | Expanded | Old reader/writer không hỏng |
| T3 | Compatible B | Expanded | New reader/writer và fallback |
| T4 | A + B cùng chạy | Expanded | Đồng bộ, race, lost update |
| T5 | New-only C | Expanded sau backfill | Cutover hoạt động |
| T6 | New-only C | Contracted | Target hoạt động |
| T7 | Old A | Contracted | Biết rõ không còn được hỗ trợ |

T7 không phải acceptance để A vẫn chạy sau contract; nó giúp minh họa ranh giới phá vỡ và ngăn deployment nhầm.

### 13.2. Producer với consumer

~~~text
                   Consumer A       Consumer B
Producer A           A -> A           A -> B
Producer B           B -> A           B -> B
~~~

Nếu **B → A** không được hỗ trợ, phải nêu rõ cách ngăn nó xảy ra trước khi producer B phát dữ liệu mới.

### 13.3. Test biên

- Field mới vắng mặt/null.
- Field cũ và mới khác giá trị.
- Writer A ghi sau backfill.
- Writer B ghi và rollback.
- Hai writer cùng cập nhật một ID.
- Transaction giữa chừng thất bại.
- Event duplicate/out of order.
- DLQ replay event cũ.
- Unknown enum/field.
- Batch chạy theo lịch cũ.
- Cache/session chưa hết hạn.
- Dữ liệu lớn hoặc thiếu dữ liệu lịch sử.
- Schema registry từ chối version không hợp lệ.
- Consumer strict JSON không cho unknown field.
- Rollback về artifact A sau khi B đã viết dữ liệu mới.

Không chỉ chạy code B với một test fixture tạo bởi B rồi kết luận tương thích với A. Cần golden payload/artifact thật từ phiên bản cũ.

## 14. Tiêu chí quyết định từng mốc

### M0 — Baseline

- Danh sách schema, producer, consumer và owner.
- Artifact/test baseline.
- Dữ liệu lịch sử và retention.
- Contract định nghĩa old/new semantics.
- Kế hoạch rollout/rollback.

**Go:** thông tin đủ để biết đối tượng nào sẽ bị ảnh hưởng.

### M1 — Expand

- Additive DDL/field/schema đã triển khai.
- App A vẫn chạy.
- Không có destructive DDL.
- Tác động lock/performance được kiểm soát.
- Test A với expanded schema đạt.

**Go:** cấu trúc mới sẵn sàng mà chưa phá cũ.

### M2 — Coexist

- App B xử lý old/new.
- Write consistency được thiết kế và test.
- Backfill có checkpoint.
- Mixed-version tests đạt.
- Fallback/mismatch có telemetry.

**Go:** hai phiên bản cùng chạy trong phạm vi dự kiến.

### M3 — Cutover

- Backfill và reconciliation đạt.
- Không còn writer A.
- Consumer mới là source of truth.
- New-only path đã vận hành ổn định.
- Kế hoạch rollback phù hợp dữ liệu mới.

**Go:** cấu trúc mới có thể đứng độc lập.

### M4 — Contract

- Không còn reader/writer/report/batch cũ được hỗ trợ.
- Queue/DLQ/replay/cache legacy đã được xử lý.
- Không còn phụ thuộc trong rollback window.
- Có approval của các owner.
- DDL/protocol contract được triển khai riêng.
- Có backup hoặc recovery plan.

**Go:** loại bỏ cấu trúc cũ không phá thành phần còn được hỗ trợ.

**PENDING không được xem là GO.**

## 15. Observability để biết khi nào được contract

Một số tín hiệu:

| Metric | Mục đích |
|---|---|
| Old field reads/writes | Biết đường legacy còn hoạt động |
| Fallback reads | Đánh giá còn dữ liệu cũ không |
| Mismatch count | Hai representation có lệch không |
| Backfill remaining | Tiến độ dữ liệu |
| Backfill latency/errors | Rủi ro vận hành |
| Old app instances | Đã thay hết runtime cũ chưa |
| Queue consumer lag | Còn message cũ cần xử lý không |
| DLQ age/count | Có message lịch sử chưa giải quyết không |
| Schema decode errors | Giao thức mới gây lỗi reader không |
| Legacy API requests | Consumer cũ vẫn gọi endpoint không |
| Rollback eligibility | Còn thể chạy lại artifact cũ không |

Một metric bằng 0 không tự chứng minh không còn consumer. Nó có thể không ghi nhận batch hàng tháng, report offline, native SQL không instrumented hoặc queue tạm ngưng.

Cần kết hợp metrics, logs, query inventory, xác nhận owner và thời gian quan sát tương ứng với chu kỳ thực tế.

### 15.1. Contract gate mẫu

~~~text
Gate ID: REMOVE_CUSTOMER_NAME

[ ] App A instances = 0
[ ] Old DB writer = 0
[ ] Old DB reader/report/batch = 0
[ ] Fallback count = 0 trong thời gian quan sát
[ ] Backfill completed
[ ] Missing/mismatch rows resolved
[ ] DLQ/replay/cache legacy addressed
[ ] Consumer owners acknowledged cutover
[ ] Rollback window closed or recovery approved
[ ] DDL lock/performance reviewed
[ ] Backup/recovery evidence available

Decision: GO / NO-GO / PENDING
Owner:
Evidence:
Time:
~~~

Không nên mở gate chỉ vì đã qua một ngày. Thời gian quan sát phải phù hợp batch, message retention, lịch phát hành của client và chính sách support.

## 16. Phối hợp nhiều nhóm

| Vai trò | Công việc chính |
|---|---|
| DBA/Data | DDL, lock, index, constraint, backup, backfill |
| Java application | Entity, repository, read/write migration |
| API team | JSON/HTTP schema, SDK, compatibility |
| Messaging | Event version, schema registry, retry, DLQ |
| Consumer owners | Xác nhận thay đổi và cutover |
| SRE/Operations | Monitoring, canary, rollback, incident |
| QA/Integration | Mixed-version test, golden fixtures |
| Security/Governance | Data retention, dữ liệu nhạy cảm, ownership |

Một migration có thể cần các mốc chấp thuận khác nhau:

1. DBA cho phép additive DDL.
2. App team triển khai compatible reader/writer.
3. Consumer owners xác nhận đã hiểu schema mới.
4. Data team đối soát backfill.
5. Operations xác nhận old traffic/instances đã hết.
6. Owner phê duyệt destructive contract.

Đừng coi “DBA đã chạy script” là bằng chứng cả hệ thống đã hoàn tất migration.

## 17. Các sai lầm thường gặp

### 17.1. Rename/drop ngay cùng release code mới

Hệ thống cũ có thể vẫn chạy, hoặc rollback về code cũ sẽ không thành công.

**Cách xử lý:** add mới, migration/coexist, rồi contract riêng.

### 17.2. Dựa hoàn toàn vào COALESCE

COALESCE giải quyết missing value, không giải quyết stale value sau khi writer A tiếp tục update.

**Cách xử lý:** có source of truth và chiến lược đồng bộ writer.

### 17.3. Dual-write thiếu transaction/consistency

Ghi hai cột hoặc hai hệ thống có thể thất bại giữa chừng.

**Cách xử lý:** transaction phù hợp, reconciliation, outbox/idempotency cho cross-system writes.

### 17.4. Thêm NOT NULL quá sớm

Writer cũ không biết cột mới, insert bắt đầu thất bại.

**Cách xử lý:** nullable/default có chủ đích, backfill và chuyển writer trước.

### 17.5. Backfill ghi đè dữ liệu mới

UPDATE không có điều kiện có thể xóa giá trị do app B mới ghi.

**Cách xử lý:** conflict-aware migration, snapshot/source-of-truth và kiểm chứng.

### 17.6. Chỉ test old producer → new consumer

Trong rolling upgrade, new producer → old consumer cũng có thể xảy ra.

**Cách xử lý:** test hai chiều hoặc chặn chiều không hỗ trợ.

### 17.7. Bỏ qua batch, report và replay

Đã tắt web instance cũ không có nghĩa mọi consumer cũ đã biến mất.

**Cách xử lý:** inventory cả SQL/report, cron, DLQ, cache, backup và retention.

### 17.8. Protobuf tái sử dụng field number

Consumer cũ có thể diễn giải sai dữ liệu mới.

**Cách xử lý:** reserve field identifiers đã retired.

### 17.9. Dual-publish mà không deduplicate

Một nghiệp vụ bị xử lý hai lần.

**Cách xử lý:** stable event identity và idempotent consumer.

### 17.10. Migration tools tự chạy luôn contract

Tách DDL thành nhiều file không tạo release gate nếu runner áp dụng tất cả file trong một lần startup.

**Cách xử lý:** kiểm soát thời điểm phân phối hoặc thực thi migration destructive.

### 17.11. Lạm dụng rollback code sau khi dữ liệu đã đổi

Re-deploy A không tự biến dữ liệu B thành định dạng A đọc được.

**Cách xử lý:** có kế hoạch rollback dữ liệu hoặc forward-fix riêng.

### 17.12. Coi metric bằng 0 là không còn dependency

Một consumer chạy hàng tháng có thể chưa xuất hiện trong cửa sổ metric.

**Cách xử lý:** xác nhận từ owner và đối chiếu chu kỳ vận hành thực tế.

## 18. Mẫu tài liệu migration

~~~text
Migration ID:
Business goal:
Schema baseline:
Schema target:
Producer versions:
Consumer versions:
Owner list:
Supported coexist window:
Data retention/replay:

Expand operations:
Compatibility readers:
Write synchronization strategy:
Backfill plan:
Conflict resolution:
Reconciliation criteria:
Cutover switch:
Contract operations:

Old artifacts still supported:
Rollback-compatible schema states:
Data rollback / forward-fix:
Evidence location:
Observability:
Go/No-Go gates:
Approvals:
Residual risks:
~~~

Ví dụ minh họa:

~~~text
ID: CUSTOMER-RECIPIENT-01
Baseline: customer_profile.customer_name
Target: customer_profile.recipient_name
Expand: add nullable recipient_name
Coexist: B reads both; writer synchronization required
Backfill: bounded, resumable, non-overwriting
Cutover: all writers use recipient_name; mismatch = 0
Contract: drop customer_name in later release
Rollback: A only before contract and while data compatible
Evidence: SQL checks + A/B integration + owner confirmations
~~~

Mẫu này cần được điều chỉnh theo rủi ro dữ liệu và hệ thống cụ thể. Không có một khoảng thời gian cố định phù hợp cho mọi consumer.

## 19. Checklist trước khi kết thúc migration

### Khảo sát

- [ ] Đã xác định mọi database, JSON và event schema liên quan.
- [ ] Có danh sách consumer, producer và chủ sở hữu.
- [ ] Có dữ liệu lịch sử/retention/replay policy.
- [ ] Đã phân biệt source, binary, data và protocol compatibility.
- [ ] Đã chốt semantics của field cũ/mới.

### Expand

- [ ] Thay đổi ban đầu additive và không phá reader/writer cũ.
- [ ] Cột/field mới có nullable/default phù hợp.
- [ ] DDL lock và hiệu năng đã được đánh giá.
- [ ] Consumer cũ có thể chấp nhận schema expanded, hoặc producer chưa phát phần mới.
- [ ] Migration mở rộng được tách khỏi destructive contract.

### Coexist

- [ ] Có source of truth cho mutable data.
- [ ] Có chiến lược dual-write/sync được kiểm chứng.
- [ ] Có test concurrency và stale read.
- [ ] Backfill idempotent, bounded, resumable.
- [ ] Reconciliation độc lập với tiến độ job.
- [ ] Có test A→B và B→A khi cần.
- [ ] Message dual-publish có idempotency.
- [ ] Có telemetry về fallback/mismatch/error.

### Contract

- [ ] Không còn reader, writer, report hoặc batch dùng schema cũ.
- [ ] Queue/DLQ/cache/replay legacy đã được xử lý.
- [ ] Dữ liệu mới đạt invariant và constraint.
- [ ] Rollback window đóng hoặc có recovery rõ.
- [ ] Owner phê duyệt quyết định GO.
- [ ] DDL/protocol contract có plan và evidence.
- [ ] Không tái sử dụng sai field identifiers đã retired.
- [ ] Code adapter/fallback/trigger tạm được gỡ ở thời điểm an toàn.

## 20. Tài liệu để đối chiếu khi triển khai thực tế

Phải đọc tài liệu theo đúng phiên bản database, ORM và giao thức:

- **PostgreSQL ALTER TABLE:** https://www.postgresql.org/docs/current/sql-altertable.html
- **PostgreSQL transactions:** https://www.postgresql.org/docs/current/transaction-iso.html
- **Flyway:** https://documentation.red-gate.com/fd/
- **Liquibase:** https://docs.liquibase.com/
- **Jakarta Persistence:** https://jakarta.ee/specifications/persistence/
- **Spring Boot database initialization:** https://docs.spring.io/spring-boot/reference/howto/data-initialization.html
- **Apache Avro specification:** https://avro.apache.org/docs/current/specification/
- **Protocol Buffers schema evolution:** https://protobuf.dev/programming-guides/proto3/#updating
- **Protocol Buffers reserved values:** https://protobuf.dev/programming-guides/proto3/#reserved

Không áp dụng nguyên xi cú pháp online DDL, transaction hoặc lock strategy từ một hệ quản trị sang hệ quản trị khác. Các quy tắc schema compatibility cũng thay đổi theo registry mode và serialization library.

---

**Kết luận:** Mở rộng trước, thu hẹp sau không phải hai lệnh SQL add/drop cách nhau vài phút. Đó là **một lộ trình tương thích có bằng chứng**: mở cấu trúc mới mà không phá cũ, đồng bộ writer, chuyển dữ liệu, kiểm chứng cả producer/consumer cũ và mới, rồi chỉ contract khi không còn thành phần được hỗ trợ cần schema cũ. Trong Java migration, quản lý đúng các release gates, dữ liệu lịch sử, transaction, retry, rollback và ranh giới API giúp giảm khả năng một lần đổi schema làm gián đoạn cả hệ thống.
