# Chọn mô hình trạng thái hoặc mô hình sự kiện theo yêu cầu thực tế

## 1. Điểm xuất phát: doanh nghiệp cần biết trạng thái hiện tại hay cần hiểu diễn tiến?

Khi mô hình hóa dữ liệu, một yêu cầu nghe rất đơn giản như “hiển thị trạng thái đơn hàng” thường che giấu nhiều câu hỏi khác nhau:

- Đơn **đang** ở trạng thái nào?
- Đơn **đã đi qua** những bước nào, ai quyết định và dựa trên bằng chứng nào?
- Tại sao trạng thái lại thay đổi; có từng bị hủy rồi mở lại không?
- Nếu công thức tính phí thay đổi, có phải tính lại kết quả từ lịch sử không?
- Khi hệ thống khác nhận thông báo chậm hoặc trùng, kết quả cuối có còn đúng không?

Không có một mô hình dữ liệu nào tối ưu mọi câu hỏi. **Mô hình trạng thái (state-oriented)** ưu tiên lưu giá trị hiện hành của thực thể. **Mô hình sự kiện (event-oriented)** ưu tiên ghi những sự việc có ý nghĩa. Trong một biến thể đặc biệt là **event sourcing**, các sự kiện đã chấp nhận là nguồn sự thật, còn trạng thái hiện tại được dựng từ sự kiện.

Quyết định đúng không dựa trên việc kiến trúc nào “hiện đại” hơn. Nó dựa trên **bất biến nghiệp vụ, giá trị của lịch sử, nhu cầu truy vấn, yêu cầu nhất quán, khả năng kiểm chứng và chi phí vận hành**. Đây cũng là mục tiêu của mô hình hóa dữ liệu: từ yêu cầu nghiệp vụ, xác định thực thể, quan hệ, khóa, ràng buộc và lược đồ vật lý phù hợp, có khả năng tiến hóa.

Ví dụ xuyên suốt là một nền tảng cho thuê thiết bị:

- Khách tạo hợp đồng thuê, đặt cọc, gia hạn và trả thiết bị.
- Nhân viên có thể điều chỉnh phí nếu phát hiện chứng từ gia hạn bị bỏ sót.
- Cổng thanh toán xác nhận thu tiền và hoàn tiền bất đồng bộ.
- Bộ phận vận hành cần tra cứu hợp đồng hiện hành; bộ phận kiểm toán cần giải thích lịch sử.

Nếu chỉ cần biết hợp đồng nào còn mở, một bảng `rental_contract` có thể đủ. Nếu cần giải thích từng quyết định và xây lại các góc nhìn dữ liệu từ lịch sử, phải cân nhắc cách lưu sự kiện nghiêm túc hơn.

## 2. Năm lựa chọn thường gặp, không chỉ có hai cực

Trong thực tế có nhiều phương án nằm giữa “chỉ lưu trạng thái” và “mọi thứ đều event sourced”.

| Phương án | Nguồn sự thật của state | Lịch sử/cơ chế trao đổi | Phù hợp khi |
| --- | --- | --- | --- |
| **A. State-only** | Hàng/document hiện hành. | Có thể chỉ có `created_at`, `updated_at`. | CRUD đơn giản, không cần giải thích từng chuyển tiếp. |
| **B. State + audit history** | Hàng/document hiện hành. | Audit log ghi ai sửa gì và khi nào. | Cần truy vết thao tác, nhưng không cần replay event để tính state. |
| **C. State + domain/integration events + outbox** | Trạng thái hiện hành. | Ghi sự việc nghiệp vụ và phát message tin cậy đến hệ khác. | Cần tích hợp đáng tin mà không cần event sourcing. |
| **D. Event sourcing** | Chuỗi event nghiệp vụ đã chấp nhận. | State và read model là dữ liệu dẫn xuất, có thể replay. | Lịch sử và khả năng dựng lại state là yêu cầu cốt lõi. |
| **E. Hybrid theo bounded context** | Mỗi miền chọn một nguồn sự thật rõ ràng. | Các miền trao đổi bằng hợp đồng tích hợp. | Hệ thống lớn có các nhu cầu rất khác nhau. |

**Lưu ý quan trọng:**

- Có **bảng `events`**, **Kafka**, **CDC** hoặc **transactional outbox** không tự làm hệ thống trở thành event sourced.
- Có một **audit trail** không chứng minh dữ liệu trong audit đủ nghĩa, đủ thứ tự và đủ đầy để dựng lại trạng thái.
- **CQRS** (tách mô hình ghi/đọc) có thể đi cùng state-first hoặc event sourcing; nó không bắt buộc thay đổi nguồn sự thật thành event.
- Một sổ cái giao dịch bất biến là thiết kế có giá trị cho tài chính, nhưng việc dùng append-only ledger **không tự đồng nghĩa** mọi aggregate của sản phẩm dùng event sourcing.

Quy tắc nhận diện: khi dữ liệu xung đột, bản ghi nào được xem là **chuẩn**? Nếu bảng trạng thái là chuẩn và event log chỉ phục vụ theo dõi, đó là state-first. Nếu chuỗi event là chuẩn và trạng thái có thể bị bỏ đi, tái tạo từ event, đó mới là event sourcing theo nghĩa kiến trúc.

## 3. Chuyển yêu cầu nghiệp vụ thành tiêu chí lựa chọn

Trước khi chọn database hoặc vẽ schema, đặt câu hỏi với người sở hữu nghiệp vụ và vận hành.

| Câu hỏi cần làm rõ | Nghiêng về state-first | Nghiêng về event sourcing |
| --- | --- | --- |
| **Cần truy vấn điều gì?** | Phần lớn là giá trị hiện hành và lọc danh sách. | Cần dựng diễn tiến, nhiều góc nhìn lịch sử và tính lại kết quả từ sự việc. |
| **Lịch sử có vai trò gì?** | Phục vụ điều tra giới hạn hoặc audit thao tác. | Là dữ liệu nghiệp vụ cốt lõi, ảnh hưởng kết quả và giải thích quyết định. |
| **Có cần tái tính toán?** | Có thể cập nhật/migrate trạng thái theo quy tắc rõ. | Cần dựng lại nhiều projection bằng replay lịch sử có nghĩa. |
| **Bất biến nằm ở đâu?** | Thường rõ trong một/hai hàng và constraint. | Cần biểu diễn chuỗi chuyển tiếp của aggregate; vẫn phải bảo vệ bằng transaction. |
| **Dữ liệu có bị sửa thường xuyên?** | Sửa state trực tiếp có thể đơn giản hơn. | Điều chỉnh cần event mới và logic reversal/correction. |
| **Truy vấn hiện hành có SLO chặt?** | Dùng chỉ mục và bảng hiện hành trực tiếp. | Thường phải xây read model riêng, quy định độ trễ projection. |
| **Schema/lịch sử tồn tại bao lâu?** | Migration thường làm trên dữ liệu hiện hành và audit cần thiết. | Cần reader/upcaster cho sự kiện cũ, lưu lịch sử và snapshot phù hợp. |
| **Quyền riêng tư/xóa dữ liệu?** | Có thể tập trung cập nhật/xóa dữ liệu hiện hành hơn. | Lịch sử append-only cần chiến lược riêng cho dữ liệu nhạy cảm. |
| **Đội ngũ có khả năng vận hành gì?** | CRUD, transaction và audit có thể đủ. | Cần thêm replay, versioning, projection, checkpoint, rebuild, giám sát. |

**Không có cột nào tự quyết định hoàn toàn.** Một nhu cầu kiểm toán rất cao có thể yêu cầu audit log bất biến có ký số, nhưng **không yêu cầu** event sourcing nếu không cần dựng state từ sự kiện. Ngược lại, hệ thống ít lưu lượng vẫn có thể dùng event sourcing vì diễn tiến nghiệp vụ là bản chất dữ liệu, không phải vì cần throughput.

### Những số liệu phải thu thập

Một cuộc khảo sát kiến trúc có ích cần những dữ kiện có thể kiểm chứng:

- Tần suất đọc/ghi, số đối tượng và độ dài vòng đời của mỗi đối tượng.
- Số chuyển tiếp trung bình và P95/P99 của mỗi aggregate.
- SLO đọc/ghi (độ trễ, độ sẵn sàng) và mức stale read được chấp nhận.
- Các câu hỏi audit cụ thể: ai, bằng chứng gì, khi nào; chỉ cần trước/sau hay phải diễn giải sự việc?
- Thời hạn lưu trữ, yêu cầu xóa/ẩn danh, số lượng consumer và các hợp đồng dữ liệu hiện hữu.
- Số loại schema event dự kiến, tần suất thay đổi quy tắc và khả năng thử nghiệm replay.

Nếu các đầu vào này chưa có, nên bắt đầu bằng mô hình tối giản có ranh giới nhất quán rõ, đo workload rồi điều chỉnh; tránh viết event store lớn chỉ dựa trên giả định.

## 4. Mô hình trạng thái: chọn khi thực thể hiện hành là dữ liệu chính

Một bảng trạng thái rất phù hợp khi nghiệp vụ chủ yếu thao tác và tra cứu những thực thể hiện tại như danh mục thiết bị, địa chỉ kho, cấu hình thông báo hoặc yêu cầu có ít bước.

Ví dụ với một hợp đồng thuê:

~~~sql
CREATE TABLE rental_contract (
    rental_id           VARCHAR(64) PRIMARY KEY,
    customer_id         VARCHAR(64) NOT NULL,
    equipment_id        VARCHAR(64) NOT NULL,
    rental_status       VARCHAR(24) NOT NULL,
    due_at              TIMESTAMPTZ NOT NULL,
    deposit_minor       BIGINT NOT NULL
                        CHECK (deposit_minor >= 0),
    deposit_currency    CHAR(3) NOT NULL,
    version             BIGINT NOT NULL DEFAULT 0
                        CHECK (version >= 0),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        rental_status IN (
            'ACTIVE', 'RETURNED', 'CLOSED', 'CANCELLED'
        )
    )
);

CREATE INDEX ix_rental_status_due
    ON rental_contract (rental_status, due_at);
~~~

Bảng này cho phép lấy trạng thái theo khóa chính, lọc các hợp đồng đang hoạt động và sắp xếp theo hạn trả. Ràng buộc `CHECK` chặn trạng thái không nằm trong tập cho phép, nhưng không tự chứng minh mọi **chuyển tiếp** như `CLOSED -> ACTIVE` hợp lệ. Logic chuyển trạng thái và transaction vẫn phải thực thi quy tắc nghiệp vụ.

Nếu hai request cùng cập nhật hợp đồng, có thể dùng **optimistic concurrency**:

~~~sql
UPDATE rental_contract
SET due_at = :new_due_at,
    version = version + 1,
    updated_at = now()
WHERE rental_id = :rental_id
  AND version = :expected_version
  AND rental_status = 'ACTIVE'
RETURNING rental_id, version;
~~~

Nếu không có hàng trả về, dữ liệu đã thay đổi hoặc không thỏa điều kiện. Ứng dụng cần tải lại state và quyết định từ đầu, không tự coi command đã thành công. `version` này là **phiên bản hàng trạng thái**, không phải stream version của event sourcing.

### Những gì mô hình này làm tốt

- Sơ đồ ít thành phần; khóa, foreign key, unique và check constraint dễ thể hiện.
- Truy vấn “hiện tại” nhanh, ít phép chuyển đổi trước khi đọc.
- Dễ dùng transaction và ràng buộc quan hệ để bảo vệ một số bất biến.
- Migration dữ liệu hiện hành thường đơn giản hơn việc phải giữ nhiều phiên bản event.

### Những điều nó không tự đáp ứng

Bảng `rental_contract` chỉ giữ `due_at` cuối, nên **không thể tự nói** ai đã thay hạn, giá trị cũ là gì và thời điểm có hiệu lực. Thêm `updated_at` không thay thế lịch sử nghiệp vụ; cũng không thể replay một chuỗi sự kiện chưa từng được lưu.

Nếu cần các câu hỏi đó, có thể thêm audit hoặc sự kiện; không nhất thiết phải đổi ngay nguồn sự thật thành event stream.

## 5. State + audit log: khi cần giải thích thao tác nhưng không cần replay để phục hồi

Giả sử đội vận hành cần biết nhân viên nào sửa hạn trả và giá trị cũ/mới. Có thể lưu audit record trong cùng giao dịch với thay đổi trạng thái:

~~~sql
CREATE TABLE rental_audit (
    audit_id            UUID PRIMARY KEY,
    rental_id           VARCHAR(64) NOT NULL,
    action              VARCHAR(80) NOT NULL,
    actor_id            VARCHAR(64),
    old_values          JSONB,
    new_values          JSONB,
    reason_code         VARCHAR(80),
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (rental_id) REFERENCES rental_contract(rental_id)
);

CREATE INDEX ix_rental_audit_history
    ON rental_audit (rental_id, recorded_at, audit_id);
~~~

Một giao dịch gia hạn sẽ kiểm tra quyền, trạng thái và version, cập nhật `rental_contract` rồi ghi `rental_audit`, sau đó commit atomically. Khi đó:

- `rental_contract` là nguồn sự thật của trạng thái hiện hành.
- `rental_audit` phục vụ truy vết, giải thích thao tác.
- Việc có thể **khôi phục toàn bộ state bằng audit** hay không phụ thuộc vào mức đầy đủ và quy tắc tạo audit, không được mặc định.

Phân biệt:

| Loại dấu vết | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Audit log thay đổi dữ liệu** | Ai/something đã sửa trường nào từ giá trị gì sang gì? | `due_at: 10:00 -> 11:00` bởi nhân viên A. |
| **Domain event** | Sự việc nghiệp vụ nào đã xảy ra? | `RentalExtensionApproved` do người có thẩm quyền duyệt. |
| **CDC record** | DB đã ghi `INSERT`/`UPDATE`/`DELETE` nào? | Hàng `rental_contract` đổi một số cột. |

Có thể lưu cả audit và domain event nếu mục tiêu khác nhau. Nhưng tránh “ghi hai bảng cho chắc” mà không xác định bên nào là chuẩn, cách đối soát và thời hạn lưu. Một audit log có tính chất pháp lý còn cần cơ chế chống sửa, phân quyền, retention và lưu bằng chứng phù hợp ngoài việc có một bảng SQL.

## 6. State + event + outbox: khi cần thông báo đáng tin nhưng state vẫn là chuẩn

Một dịch vụ có thể cần công bố `RentalClosed` cho CRM và kế toán, trong khi vẫn muốn giữ bảng `rental_contract` là nguồn sự thật. **Transactional outbox** phù hợp với tình huống này.

~~~mermaid
flowchart TD
    C["Command CloseRental"] --> V{"Kiểm tra bất biến"}
    V -->|"Không hợp lệ"| X["Từ chối"]
    V -->|"Hợp lệ"| T["Transaction DB: cập nhật rental_contract + INSERT outbox"]
    T --> O[("Outbox row đã commit")]
    T --> S[("rental_contract: nguồn trạng thái")]
    O --> R["Relay / CDC connector"]
    R --> E["Integration event RentalClosed.v1"]
    E --> A["CRM"]
    E --> B["Accounting"]
~~~

Lược đồ outbox minh họa:

~~~sql
CREATE TABLE integration_outbox (
    message_id       UUID PRIMARY KEY,
    aggregate_id     VARCHAR(64) NOT NULL,
    event_type       VARCHAR(100) NOT NULL,
    schema_version   SMALLINT NOT NULL CHECK (schema_version > 0),
    payload          JSONB NOT NULL
                     CHECK (jsonb_typeof(payload) = 'object'),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at     TIMESTAMPTZ
);

CREATE INDEX ix_outbox_unpublished
    ON integration_outbox (created_at, message_id)
    WHERE published_at IS NULL;
~~~

Ứng dụng ghi **trạng thái** và **ý định phát thông điệp** trong cùng transaction. Relay gửi message sau commit. Nếu relay gửi thành công nhưng chết trước khi đánh dấu đã phát, message có thể được gửi lại; consumer cần xử lý **idempotent** theo `message_id` hoặc khóa nghiệp vụ thích hợp. Outbox ngăn mất ý định phát do khoảng trống giữa commit dữ liệu và gọi broker, nhưng **không tự tạo bảo đảm exactly-once xuyên mọi hệ thống**.

Đây là lựa chọn hợp lý khi cần tích hợp và gửi thông báo đáng tin, nhưng **không cần replay toàn bộ lịch sử để dựng state**. Event phát ra cho consumer có hợp đồng chia sẻ riêng, không nhất thiết trùng dữ liệu nội bộ hoặc row CDC.

## 7. Event sourcing: khi diễn tiến là nguồn dữ liệu cần bảo vệ

Trong event sourcing, một aggregate được định nghĩa bằng **chuỗi event đã được chấp nhận**. Bảng trạng thái có thể được xóa, tạo lại hoặc xây projection khác từ lịch sử nếu sự kiện đủ, reader còn tương thích và các điều kiện phục hồi được đáp ứng.

Ví dụ một `Rental`:

| stream_version | Sự kiện | Dữ kiện chủ chốt |
| ---: | --- | --- |
| 1 | `RentalStarted` | Thiết bị, hạn trả, tiền cọc theo hợp đồng. |
| 2 | `DepositCaptured` | Đã thu khoản cọc được nhà thanh toán xác nhận. |
| 3 | `RentalDueDateExtended` | Hạn trả mới và bằng chứng duyệt. |
| 4 | `EquipmentDroppedOff` | Thiết bị được giao tại điểm tiếp nhận. |
| 5 | `EquipmentReturnAccepted` | Nghiệm thu được chấp nhận. |
| 6 | `DepositRefundConfirmed` | Khoản hoàn được xác nhận thực tế. |
| 7 | `RentalClosed` | Hợp đồng chính thức đóng. |

Trạng thái hiện tại là kết quả của:

~~~text
state@version7 = fold(initial_state, event1 ... event7)
~~~

Ví dụ envelope event:

~~~json
{
  "event_id": "458a91ea-8537-446a-954c-c26cb802b1bc",
  "aggregate_type": "Rental",
  "aggregate_id": "RENT-204",
  "stream_version": 6,
  "event_type": "DepositRefundConfirmed",
  "event_schema_version": 1,
  "occurred_at": "2026-11-20T05:20:00Z",
  "recorded_at": "2026-11-20T05:20:02Z",
  "payload": {
    "refund_id": "REF-702",
    "amount_minor": 200000,
    "currency": "VND",
    "provider_confirmation_id": "GW-559"
  }
}
~~~

`stream_version` biểu diễn **thứ tự trong Rental**, không phải thứ tự toàn hệ thống. `event_schema_version` xác định cách đọc payload. `occurred_at` là thời điểm nghiệp vụ đã được xác nhận; `recorded_at` là khi hệ thống ghi nhận. Tiền phải có đơn vị, loại tiền và nguồn xác nhận rõ.

### Mô hình vật lý tối thiểu

~~~sql
CREATE TABLE rental_event_stream (
    rental_id        VARCHAR(64) PRIMARY KEY,
    current_version  BIGINT NOT NULL DEFAULT 0
                     CHECK (current_version >= 0)
);

CREATE TABLE rental_event (
    event_id             UUID PRIMARY KEY,
    rental_id            VARCHAR(64) NOT NULL
                         REFERENCES rental_event_stream(rental_id),
    stream_version       BIGINT NOT NULL CHECK (stream_version > 0),
    event_type           VARCHAR(120) NOT NULL,
    event_schema_version SMALLINT NOT NULL
                         CHECK (event_schema_version > 0),
    occurred_at          TIMESTAMPTZ NOT NULL,
    recorded_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload              JSONB NOT NULL
                         CHECK (jsonb_typeof(payload) = 'object'),
    UNIQUE (rental_id, stream_version)
);

CREATE INDEX ix_rental_event_type_date
    ON rental_event (event_type, occurred_at);
~~~

Một command phải đọc state mới nhất, kiểm tra bất biến và append event với **expected version** trong transaction. Có thể khóa dòng `rental_event_stream` hoặc dùng conditional update/CAS; cập nhật `current_version` và chèn event phải commit cùng nhau. Chỉ có `UNIQUE(rental_id, stream_version)` không đủ để ngăn một command hợp thức hóa quyết định dựa trên state cũ bằng cách đơn thuần tăng version rồi chèn event.

### Đổi lại được gì và phải gánh gì?

**Lợi ích tiềm năng:** lịch sử nghiệp vụ giàu ý nghĩa, giải thích nguồn gốc state, tái tạo nhiều projection, kiểm tra diễn tiến, mô hình hóa correction/reversal rõ ràng.

**Chi phí bắt buộc:** phiên bản event tồn tại lâu, upcaster/reader lịch sử, snapshot khi stream dài, dedup/checkpoint của projector, eventual consistency nếu dùng read model bất đồng bộ, khả năng khôi phục và các quy tắc quyền riêng tư trong lịch sử append-only.

Event sourcing **không** làm tự nhiên biến mất việc xử lý đồng thời, giao dịch phân tán, lỗi provider, dữ liệu đến muộn hoặc nhu cầu bảo vệ dữ liệu. Tất cả vẫn cần thiết kế cụ thể.

## 8. So sánh bằng các tình huống nghiệp vụ khác nhau

### Tình huống A — Danh mục thiết bị

Yêu cầu: người quản trị đổi tên thiết bị, mô tả, nhóm và trạng thái cho thuê; người dùng tra cứu danh sách với bộ lọc. Thay đổi ít ảnh hưởng đến quyết định đã diễn ra.

**Lựa chọn khởi đầu:** state-first với `equipment` và các khóa/ràng buộc phù hợp. Thêm audit nếu cần biết ai đã sửa dữ liệu. Event sourcing toàn bộ danh mục thường làm tăng phức tạp mà không tạo lợi ích tương xứng.

Ngoại lệ: nếu giá và điều kiện thuê được dùng để tính hợp đồng lịch sử, cần **version hóa bảng giá hoặc lưu snapshot giá/chính sách tại thời điểm ký**. Nhưng điều đó vẫn **không bắt buộc** biến catalog thành event sourced aggregate.

### Tình huống B — Thay đổi cấu hình ứng dụng

Yêu cầu: chỉ cần cấu hình đang hiệu lực, có thể rollback về vài phiên bản gần nhất, mỗi lần deploy đều có kiểm soát.

**Lựa chọn:** state hoặc versioned configuration document với metadata tác giả/phiên bản/phê duyệt. Khả năng rollback được giải quyết bằng versioned state; không cần diễn giải mọi lần đổi như một sự kiện miền.

### Tình huống C — Vòng đời hợp đồng phức tạp

Yêu cầu: gia hạn nhiều lần, điều chỉnh phí, nghiệm thu, hoàn cọc, tranh chấp; có thể phải giải thích lịch sử trước và sau điều chỉnh, dựng lại các báo cáo theo quy tắc được công bố.

**Lựa chọn:** cân nhắc event sourcing cho aggregate `Rental` hoặc `BillingLedger` nếu chuỗi sự kiện và replay có giá trị thực sự. Nếu chỉ cần một số mốc xác nhận và trạng thái nhanh, `rental_contract + domain event/audit + outbox` có thể đơn giản hơn.

### Tình huống D — Ghi nhận tiền và nghĩa vụ tài chính

Yêu cầu: giải thích mọi khoản thu, hoàn, điều chỉnh, đối soát provider, phân biệt khoản phải thu với tiền thực nhận.

**Lựa chọn:** một **ledger bất biến có bút toán đầy đủ** là nền tảng quan trọng. Ledger có thể là nguồn sự thật tài chính, kết hợp state-first cho hợp đồng và sự kiện tích hợp. Có thể áp dụng event sourcing ở ranh giới phù hợp, nhưng **không suy rằng một dòng PaymentCaptured tương đương toàn bộ bút toán kế toán** hoặc rằng mọi aggregate cần event source.

### Tình huống E — Đồng bộ sang kho phân tích

Yêu cầu: đồng bộ bảng đơn/khách hàng phục vụ báo cáo, không cần xây state từ event lịch sử.

**Lựa chọn:** CDC hoặc pipeline ETL/ELT với xử lý snapshot khởi tạo, upsert/delete, khóa và schema evolution. Bản ghi CDC mô tả thao tác lưu trữ, **không đồng nghĩa** sự kiện đã xảy ra về mặt nghiệp vụ. Nếu báo cáo cần xác nhận “giao hàng thành công”, phải lấy event/bằng chứng nghiệp vụ ở nguồn có thẩm quyền.

## 9. Chiến lược hybrid: chọn mô hình theo ranh giới nghiệp vụ, không theo toàn hệ thống

Một hệ thống thực tế có thể có:

- `EquipmentCatalog` lưu trạng thái hiện hành.
- `Rental` lưu event sourcing nếu vòng đời hợp đồng cần tái tạo.
- `Payment` lưu giao dịch và sổ cái theo ràng buộc tài chính riêng.
- `CRM` nhận integration event với hợp đồng ổn định, không đọc trực tiếp bảng nội bộ.
- `Analytics` nhận sự kiện nghiệp vụ hoặc CDC với quy tắc dedup/time rõ ràng.

~~~mermaid
flowchart LR
    CAT[("Equipment Catalog: state")] --> API["Rental workflow"]
    API --> EV[("Rental event store")]
    EV --> RP[("Rental read model")]
    EV --> OUT["Outbox / publisher"]
    OUT --> MSG["Integration contracts"]
    PAY[("Payment / ledger")] --> OUT2["Payment publisher"]
    OUT2 --> MSG
    MSG --> CRM["CRM"]
    MSG --> AN["Analytics"]
~~~

Sơ đồ là **một phương án logic**, không quy định một loại transaction chung cho các database. Dữ liệu thanh toán/hoàn tiền được công nhận theo nguồn có thẩm quyền của `Payment`; `Rental` phải tiếp nhận thông tin qua một quy trình có hợp đồng và idempotency, không tự suy “đã hoàn tiền” chỉ vì đã gửi yêu cầu.

### Ranh giới nguồn sự thật phải được ghi thành hợp đồng

| Khái niệm | Nguồn có thẩm quyền | Những nơi chỉ giữ bản dẫn xuất |
| --- | --- | --- |
| Tên và thông số thiết bị | EquipmentCatalog. | Chi tiết hiển thị trong hợp đồng, cache, tìm kiếm. |
| Diễn tiến thuê và nghiệm thu | Rental aggregate/event store (nếu chọn event sourcing). | `rental_current`, timeline, dashboard. |
| Capture/refund thực tế | Payment/ledger và xác nhận provider. | Trạng thái thanh toán trong Rental, CRM, báo cáo. |
| Chỉ số trả trễ | Event/nguồn nghiệp vụ + định nghĩa KPI có version. | Bảng tổng hợp phân tích. |

Khi một hệ thống ngoài trả dữ liệu đến muộn, mọi bên phải phân biệt **sự thật nguồn**, **thông điệp đã nhận** và **trạng thái được chiếu**. Hybrid là cách giảm phạm vi phức tạp nhưng không loại bỏ các vấn đề tích hợp.

## 10. Quy tắc nhất quán và cập nhật đồng thời quyết định ranh giới mô hình

Một câu hỏi quan trọng hơn tên kiến trúc là: **bất biến nào phải đúng ngay trong transaction?**

| Bất biến | Ví dụ | Điểm bảo vệ cần thiết |
| --- | --- | --- |
| Không nghiệm thu cùng thiết bị hai lần trong một lượt thuê | Hai nhân viên cùng nhấn chấp nhận trả. | Khóa/version và điều kiện theo Rental, cộng idempotency của command. |
| Không hoàn cọc vượt tiền đã thu | Hai yêu cầu refund cạnh tranh. | Nguồn quản lý nghĩa vụ/ledger, kiểm tra số dư và khóa giao dịch thích hợp. |
| Không bán cùng một ghế cho hai người | Hai Booking khác nhau chọn cùng ghế. | Unique/lock/reservation tại nguồn quản lý ghế, không chỉ khóa từng Booking. |
| Không gửi lại một tác động bên ngoài gây thu tiền hai lần | Callback hoặc API retry. | Idempotency key ở cổng/provider và dedup trong hệ thống. |

**Event sourcing không tự giải quyết bất biến xuyên aggregate**. Nếu nhiều booking dùng chung tồn kho, mỗi `Booking` có event stream riêng không bảo đảm ghế không bán trùng; cần aggregate/chủ sở hữu tồn kho hoặc constraint/giao dịch ở điểm nhất quán chung.

Bất kể state-first hay event-first, phải xử lý:

1. **Concurrent commands:** compare-and-swap theo version, khóa phù hợp hoặc transaction isolation thích hợp.
2. **Retry cùng request:** idempotency key có phạm vi và chính sách phản hồi rõ.
3. **Side effect bên ngoài:** ghi ý định trong outbox rồi gửi, đối soát kết quả trước khi khẳng định thành công.
4. **Message đến lặp/sai thứ tự:** consumer dedup và kiểm soát version/điều kiện trạng thái.
5. **Dữ liệu đến muộn:** phân biệt thời điểm xảy ra, thời điểm ghi nhận và thời điểm xử lý.

### Chọn event sourcing chỉ vì muốn “không mất cập nhật” là sai mục tiêu

Cả state-first lẫn event sourcing đều có thể dùng optimistic concurrency. Ví dụ `UPDATE state WHERE version = expected` và `append event WHERE current_stream_version = expected` đều giải quyết tranh chấp cục bộ khi thiết kế transaction đúng. Giá trị riêng của event sourcing là **lịch sử nghiệp vụ làm nguồn sự thật**, không phải một kỹ thuật khóa kỳ diệu.

## 11. Thời gian, chỉnh sửa và cách hiểu dữ liệu cũ

Mô hình trạng thái thường dễ cho câu hỏi “**hiện giờ** giá trị là gì?”. Mô hình sự kiện có ưu thế khi cần biết “**tại sao** trạng thái đó hình thành?” nhưng phải thiết kế thời gian rõ ràng.

Một trường hợp sửa hạn trả:

- 10:00: hợp đồng được ghi nhận hạn trả 10:00.
- 10:30: khách bàn giao thiết bị.
- 11:00: hệ thống tính phí trễ dựa trên hạn đang lưu.
- 12:00: quản lý duyệt điều chỉnh, chứng minh hạn hợp lệ phải là 11:00.

Có ít nhất hai cách nhìn:

- **Thông tin hệ thống đã biết vào lúc 11:00:** hạn trả 10:00 và một khoản phí đã được đánh giá.
- **Thông tin được công nhận sau khi điều chỉnh:** hạn trả 11:00 và khoản phí trễ có thể cần đảo.

Với state-first, có thể ghi `due_at = 11:00` và thêm audit/correction. Với event sourcing, có thể append `RentalDueDateCorrectionApproved` và `LateFeeAssessmentReversed` theo quy tắc nghiệp vụ. **Dù chọn mô hình nào**, nếu tiền đã thu thì đảo khoản phải thu không tự hoàn tiền; cần hành động refund thực tế và sự kiện xác nhận.

Các trường nên phân biệt:

| Trường | Ý nghĩa |
| --- | --- |
| `occurred_at` | Sự việc được nguồn có thẩm quyền xác nhận xảy ra lúc nào. |
| `recorded_at` | Hệ thống ghi nhận sự việc vào lúc nào. |
| `effective_at` | Giá trị/điều chỉnh có hiệu lực từ lúc nào nếu khác thời điểm ghi. |
| `stream_version` | Thứ tự logic sự kiện được chấp nhận trong một luồng, không phải ngày giờ. |

Event có `effective_at` cũ vẫn được append với stream version mới. Muốn trả lời đồng thời “hệ thống biết gì tại thời điểm X?” và “dữ kiện hiện nay được công nhận có hiệu lực lúc X?”, cần một quy tắc thời gian rõ, có thể cần **bitemporal model**. Chỉ chuyển từ bảng trạng thái sang event log không tự làm mọi truy vấn lịch sử trở nên đúng.

## 12. Hiệu năng, truy vấn và chi phí vận hành

Một đánh đổi thường bị hiểu đơn giản là “state nhanh, event chậm”. Điều đó không chính xác cho mọi workload.

**State-first** có thể lấy trạng thái bằng một phép tra khóa chính; nếu cần lịch sử dài, có thể vẫn phải truy vấn audit. **Event sourcing** có thể phục vụ màn hình rất nhanh qua read model phù hợp; độ trễ phụ thuộc cách projector được cập nhật và cơ chế bảo đảm tính mới. Ngược lại, việc dựng aggregate bằng replay hàng nghìn event mỗi command có thể tốn kém nếu không có snapshot và tối ưu phù hợp.

| Thành phần | State-first | Event sourcing |
| --- | --- | --- |
| Đọc trạng thái hiện hành | Đọc hàng/document chuẩn. | Đọc projection hoặc snapshot + tail event. |
| Ghi một thay đổi | Cập nhật state và có thể audit/outbox. | Append event, bảo vệ version, có thể cập nhật projection/outbox. |
| Truy vấn lịch sử | Phụ thuộc mức đầy đủ của audit/history. | Truy cập event có nghĩa; vẫn cần schema/index/read model chuyên biệt. |
| Thay cách tính báo cáo | Migrate hoặc tái xử lý từ dữ liệu đã giữ. | Replay event nếu còn đủ lịch sử và reader phù hợp. |
| Tiến hóa dữ liệu | Migration hàng hiện hành, version audit nếu cần. | Lưu nhiều event schema, upcaster/reducer/snapshot version. |
| Vận hành và giám sát | Transaction, backup, index, audit/outbox nếu có. | Thêm replay, snapshot, projector lag, checkpoint, rebuild và drift. |
| Riêng tư | Kiểm soát dữ liệu hiện hành/audit/backups. | Kiểm soát thêm lịch sử event append-only và bản dẫn xuất. |

Đừng kết luận bằng benchmark không cùng điều kiện. Một thử nghiệm có ích cần cùng yêu cầu truy vấn và bất biến:

1. Tạo bộ dữ liệu thực tế về số aggregate và số event/hàng mỗi aggregate.
2. Đo **P50/P95/P99** thời gian nạp trạng thái, xử lý command và truy vấn danh sách/tổng hợp.
3. Tạo tải ghi đồng thời để đo số xung đột, retry, thời gian khóa và tỷ lệ lỗi.
4. Với event sourcing, đo độ trễ projection, chi phí snapshot, replay từ đầu và rebuild read model.
5. Đánh giá dung lượng, số chỉ mục, backup/restore, chi phí vận hành và số lần cần sửa schema.
6. So sánh với **mức SLO thực tế**, không chỉ so sánh thời gian xử lý trong demo.

Event sourcing không phải mặc định có chi phí thấp hơn khi lượng dữ liệu tăng; state-first cũng không mặc định đơn giản nếu phải tự xây lịch sử, audit nghiêm ngặt và nhiều pipeline tích hợp.

## 13. Khả năng tái tạo, quyền riêng tư và giới hạn “append-only”

“Có thể rebuild từ event” là một cam kết có điều kiện:

- Sự kiện lịch sử phải **đủ, chính xác về ngữ nghĩa và giữ được thứ tự**.
- Reader phải hiểu `event_type + schema_version` cũ.
- Reducer cần tất định, không gọi API ngoài hay dùng bảng giá hiện tại để quyết định lại quá khứ.
- Snapshot tương thích chỉ là điểm bắt đầu, không thay thế event gốc nếu projection cần lịch sử chi tiết.
- Việc xóa/ẩn danh theo chính sách có thể làm giới hạn replay; cần công bố và thiết kế trước.

Một log append-only không đồng nghĩa dữ liệu có thể lưu mãi bất chấp chính sách. Event có thể chứa tên khách, mã thanh toán hoặc thông tin nhạy cảm không nên nhân bản cho mọi consumer. Dù chọn mô hình nào, hãy xác định:

- Ai được đọc/ghi/sửa/xóa dữ liệu; các quyền có được kiểm soát ở cả ứng dụng và database không?
- Dữ liệu cá nhân nằm trong state, event, audit, outbox, projection, backup và log ở những nơi nào?
- Chính sách retention, xử lý yêu cầu xóa hoặc ẩn danh có tương thích yêu cầu pháp lý và khả năng khôi phục không?
- Cần bằng chứng chống sửa nào: audit truy cập, backup, hash chain/chữ ký và quản lý khóa có phù hợp không?
- Migration schema có giữ được nghĩa dữ liệu lịch sử và tránh làm thay đổi những KPI đã công bố không?

Nếu event không được phép giữ đầy đủ trong dài hạn, có thể tách dữ liệu cá nhân khỏi event, lưu ID tham chiếu, có chính sách hủy/ẩn danh hoặc giới hạn phạm vi event sourcing. Không có một thủ thuật chung có thể vừa xóa mọi dấu vết nhạy cảm vừa giữ trọn mọi khả năng replay mà không đánh đổi.

## 14. Phương pháp chấm điểm lựa chọn bằng chứng cứ, không bằng sở thích

Có thể dùng một **phiếu quyết định** cho mỗi bounded context. Điểm số chỉ là công cụ để thảo luận, không phải công thức tự động chọn kiến trúc.

| Tiêu chí | 0 = ít/không cần | 1 = có mức vừa | 2 = yêu cầu trọng tâm |
| --- | --- | --- | --- |
| Cần khôi phục state bằng replay | Không cần. | Có thể hữu ích cho một số ca. | Bắt buộc cho vận hành/phân tích. |
| Lịch sử có ngữ nghĩa nghiệp vụ | Chỉ cần biết state mới. | Có một số mốc cần lưu. | Mọi quyết định/chuyển tiếp quan trọng là dữ liệu cốt lõi. |
| Cần xây nhiều projection lịch sử | Hiếm thay đổi báo cáo. | Có vài góc nhìn. | Thường xuyên tái tính toán với định nghĩa mới. |
| Khó chứng minh tính đúng nếu chỉ lưu state | Bất biến dễ kiểm bằng constraint. | Một số quyết định cần dấu vết. | Chuỗi sự việc và nguồn bằng chứng quyết định tính đúng. |
| Năng lực vận hành event sourcing | Chưa có. | Có thể thí điểm nhỏ. | Có đội ngũ và quy trình replay/rebuild/monitoring. |

**Cách sử dụng:** điểm cao ở bốn tiêu chí nhu cầu cho thấy đáng **đánh giá event sourcing**, còn điểm thấp về năng lực vận hành là rủi ro cần xử lý, không phải động lực tăng thêm điểm. Ngay cả khi tổng điểm “cao”, các ràng buộc không thể thương lượng như quyền riêng tư, pháp lý hoặc giao dịch xuyên hệ thống vẫn phải được giải quyết riêng.

### Một quyết định mẫu

Cho `Rental` với các yêu cầu: khách xem trạng thái tức thời; vận hành cần lịch sử gia hạn/nghiệm thu; kế toán cần đối soát hoàn cọc; kiểm toán yêu cầu giữ bằng chứng 5 năm; chỉ có vài event cho mỗi hợp đồng; đội ngũ chưa có hạ tầng replay.

Có thể chọn **state + domain history + audit/outbox** trước vì:

- Trạng thái hiện hành là câu hỏi chủ yếu.
- Lịch sử cần lưu nhưng chưa có yêu cầu khôi phục tất cả state từ event.
- Số lần chuyển tiếp thấp, lợi ích hiệu năng snapshot/replay nhỏ.
- Đội ngũ dễ quản lý transaction và bảng lịch sử có khóa rõ ràng.

Nếu về sau phát sinh yêu cầu tái tính toán nhiều projection từ lịch sử đầy đủ và các sự kiện đủ nghĩa được chuẩn hóa, có thể xem xét **event sourcing cho một phần miền**. Không cần tuyên bố cả hệ thống phải chuyển đổi.

### Artifact quyết định nên có gì?

Một **Architecture Decision Record (ADR)** ngắn nên ghi: yêu cầu nghiệp vụ, nguồn sự thật, bất biến, phạm vi aggregate, các phương án đã so sánh, lợi ích/chi phí, SLO, retention, rủi ro, phương án migration, điều kiện đánh giá lại và cách kiểm chứng. Nhờ đó khi đội ngũ thay đổi, quyết định vẫn có căn cứ.

## 15. Di chuyển giữa các mô hình: tránh tạo lịch sử giả hoặc hai nguồn sự thật

### Từ state-first sang event sourcing

Đây không phải chỉ là “tạo bảng event rồi đổ từng hàng trạng thái thành event quá khứ”.

1. **Xác định ranh giới** aggregate/nguồn sự thật muốn chuyển. Không chuyển các bảng không liên quan chỉ để đồng nhất công nghệ.
2. **Định nghĩa event contract** với điều kiện chốt nghiệp vụ, khóa ID, version, thời gian và chính sách schema.
3. **Kiểm kê lịch sử sẵn có.** Nếu chỉ có state hiện hành, không thể biết toàn bộ sự kiện đã xảy ra trong quá khứ. Có thể tạo **initialization/baseline event** mang ý nghĩa “đây là state tại mốc chuyển đổi” hoặc snapshot có nguồn gốc rõ; **không đặt giả thành các sự kiện nghiệp vụ trước đó**.
4. **Chọn một điểm chuyển nguồn sự thật** có kiểm soát. Không cho state và event store ghi độc lập cùng là chuẩn trong thời gian dài mà không có cách chứng minh nhất quán.
5. **Thực hiện đồng bộ/migration nhất quán:** xử lý các thay đổi phát sinh trong lúc copy, dùng cursor có bảo đảm commit hoặc một cơ chế dual-write có bảo vệ và đối chiếu được.
6. **Xây read model, kiểm chứng và cutover**. Đối chiếu state tại mốc với dữ liệu cũ, kiểm thử concurrency, idempotency và rollback.

Nếu event lịch sử được khôi phục từ audit có chất lượng đủ, phải kiểm chứng ngữ nghĩa, thứ tự, bản ghi thiếu và quy tắc chuyển đổi. CDC của một hàng sau khi đã bị update nhiều lần không thể tự tạo lại những sự việc nghiệp vụ từng xảy ra nếu các dữ kiện gốc không được lưu.

### Từ event sourcing sang state-first

Cũng có những tình huống cần **đơn giản hóa**: event sourcing làm chi phí vận hành quá lớn so với nhu cầu hiện tại.

1. Xác định state tại mốc chốt và quy tắc chuyển đổi mọi event liên quan.
2. Tạo bảng state mới và kiểm chứng bằng replay/đối chiếu.
3. Trong giai đoạn chuyển, xử lý event mới phát sinh để không mất thay đổi.
4. Quy định trạng thái nào trở thành nguồn sự thật sau cutover.
5. Giữ hay lưu trữ event gốc theo nghĩa vụ audit, pháp lý và nhu cầu tra cứu; không xóa lịch sử chỉ vì không còn dùng để ra lệnh.
6. Bảo đảm các consumer trước đây phụ thuộc event stream có hợp đồng thay thế phù hợp.

**Sai lầm nguy hiểm nhất là có hai nguồn sự thật không được điều phối.** Nếu một dịch vụ coi `rental_contract` là chuẩn nhưng một dịch vụ khác coi `rental_events` là chuẩn, cả hai ghi độc lập, việc khôi phục và xử lý xung đột sẽ trở nên mơ hồ.

## 16. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| “Cần audit nên phải dùng event sourcing.” | Audit thay đổi có thể đủ; event sourcing chỉ cần khi event là nguồn sự thật và replay có giá trị. |
| “Có Kafka nghĩa là đã event sourcing.” | Kafka có thể chỉ truyền integration event; nguồn state vẫn là bảng hiện hành. |
| “Mọi UPDATE trong CDC đều là domain event.” | CDC ghi thay đổi lưu trữ; không tự biết lý do và mốc sự thật nghiệp vụ. |
| “Event sourcing luôn nhanh hơn CRUD.” | Nạp state có thể cần replay/snapshot; đọc thường cần projection. Phải đo workload. |
| “Event sourcing giải quyết exactly-once.” | Retry và message lặp vẫn tồn tại; cần idempotency, transaction và đối soát. |
| “Append-only có nghĩa không bao giờ cần sửa sai.” | Cần correction/reversal/compensation có nghĩa nghiệp vụ và chính sách xử lý dữ liệu. |
| “Có snapshot là xóa được toàn bộ event cũ.” | Snapshot không thay thế lịch sử chi tiết phục vụ audit và projection mới. |
| “Chỉ cần sửa schema JSON là tương thích.” | Còn phải giữ ý nghĩa event cũ, reader/upcaster và consumer contract. |
| “Mọi bounded context phải theo cùng một mô hình.” | Hybrid theo ranh giới nghiệp vụ thường thực tế hơn. |
| “Tăng throughput bằng chia nhỏ aggregate luôn an toàn.” | Chia sai ranh giới có thể phá bất biến xuyên stream. |

## 17. Bài tập thiết kế: chọn phương án cho ba miền cùng hệ thống

**Tình huống:** một nền tảng bán vé và quản lý sự kiện có ba nhóm yêu cầu.

**Nhóm A — Catalog sự kiện:** cập nhật tên chương trình, mô tả, banner, giá niêm yết; quản trị viên muốn biết ai sửa giá. Khách cần tìm kiếm nhanh các sự kiện còn mở bán.

**Nhóm B — Booking và ghế:** khách giữ ghế, thanh toán, hủy, đổi ghế. Hai khách có thể tranh cùng ghế; callback thanh toán đến trễ hoặc lặp. Đội hỗ trợ muốn xem diễn tiến đặt vé và tranh chấp.

**Nhóm C — Thanh toán và đối soát:** có thu tiền, hoàn một phần, hoàn thất bại, phí nhà cung cấp và báo cáo dòng tiền theo ngày. Đối soát cần bằng chứng bên cung cấp, lịch sử không mất và báo cáo có thể tính lại.

### Yêu cầu thực hành

1. **Chọn nguồn sự thật riêng** cho A, B và C: state-only, state + audit/outbox, event sourcing, ledger hoặc hybrid. Nêu **lý do từ yêu cầu**, không chỉ dựa trên sở thích công nghệ.
2. **Xác định aggregate và bất biến:** `SeatInventory` hay `SeatReservation` phải bảo vệ không bán một ghế hai lần; `Booking` có thể có version riêng. Giải thích vì sao khóa một booking không đủ bảo vệ toàn bộ ghế.
3. **Thiết kế khóa và schema:** nêu PK, FK, UNIQUE, index có ích cho truy vấn Catalog, Booking và dòng tiền. Đề xuất một mẫu transaction kiểm tra ghế và ghi kết quả nhất quán.
4. **Ghi dấu vết:** phân biệt audit của việc đổi giá, domain event `BookingCancelled`, integration event thông báo và CDC đồng bộ Catalog.
5. **Xử lý tiền:** mô tả các mốc `RefundRequested` và `RefundConfirmed`; không cộng tiền đã hoàn khi mới gửi request; xử lý provider timeout bằng đối soát.
6. **Tích hợp:** đề xuất outbox và khóa idempotency khi Booking cần thông báo cho email hoặc Payment; phân biệt kết quả đã commit với message đã xử lý.
7. **Lịch sử và KPI:** định nghĩa “tỷ lệ hủy”, “tổng thu gộp”, “tổng hoàn” và “tiền ròng”; quyết định dữ liệu gốc và cách xử lý event đến muộn.
8. **Hiệu năng:** nêu workload dự kiến và phép đo P95/P99, điểm nghẽn tranh ghế, lag projection, chi phí index và rebuild.
9. **Chính sách dữ liệu:** xác định thông tin cá nhân nên nằm ở đâu; làm gì với audit/event/outbox/backup khi có yêu cầu retention hoặc xóa.
10. **ADR:** viết quyết định một trang cho từng miền, gồm phương án đã loại bỏ và điều kiện khiến bạn sẽ đánh giá lại lựa chọn.

### Bảng kiểm tự đánh giá

| Kiểm tra | Kết quả đạt yêu cầu |
| --- | --- |
| **Nguồn sự thật** | Với mỗi miền có một nguồn chuẩn rõ, không hai nơi cùng được ghi độc lập. |
| **Bất biến** | Không giữ/sell một ghế hai lần; hoàn tiền không vượt số tiền hợp lệ và có đối soát. |
| **Ngữ nghĩa** | Phân biệt trạng thái hiện hành, sự việc nghiệp vụ, audit, CDC và integration event. |
| **Đồng thời** | Transaction/locking/version/idempotency giải quyết command cạnh tranh và retry. |
| **Dữ liệu lịch sử** | Có thể trả lời những câu hỏi đã cam kết, không bịa lịch sử từ state hiện hành. |
| **Truy vấn** | Khóa, chỉ mục và read model phù hợp dạng câu hỏi và SLO cụ thể. |
| **Tiến hóa** | Có kế hoạch schema/version/migration, kiểm chứng cutover khi thay nguồn sự thật. |
| **Vận hành/riêng tư** | Có phương án backup, giám sát, xử lý lỗi và retention phù hợp. |

**Kết luận:** chọn mô hình trạng thái hay sự kiện là quyết định **đặt nguồn sự thật ở đâu và bảo đảm điều gì có thể khôi phục, giải thích, kiểm chứng**. State-first phù hợp khi giá trị hiện hành là dữ liệu chính; state + audit/outbox phù hợp khi cần truy vết và tích hợp mà không cần replay; event sourcing đáng cân nhắc khi diễn tiến có ý nghĩa là dữ liệu gốc cần giữ lâu dài và tái tạo được. Một thiết kế hybrid theo bounded context thường cho phép đáp ứng đúng yêu cầu với chi phí hợp lý hơn việc áp dụng một mô hình cho toàn hệ thống.
