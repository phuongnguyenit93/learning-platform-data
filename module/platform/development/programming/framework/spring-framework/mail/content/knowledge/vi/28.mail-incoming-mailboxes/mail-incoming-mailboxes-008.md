# Lưu message ID và trạng thái xử lý

## 1. Vì sao ứng dụng nhận thư cần ghi nhớ đã xử lý đến đâu?

Trong một hệ thống dùng **Spring Framework Mail**, chúng ta thường biết `JavaMailSender` để **gửi** email qua SMTP. Nhưng nhiều ứng dụng còn cần **nhận thư** từ hộp thư hỗ trợ khách hàng, hộp thư phản hồi, mailbox đối soát, đơn đăng ký qua email hoặc hệ thống xử lý DSN/bounce.

Ví dụ:

- Khách hàng gửi email tới `support@example.com`, ứng dụng tạo một ticket.
- Hệ thống nhận phản hồi trả lời email đơn hàng và gắn nó với đơn hàng trước đó.
- Mailbox tự động nhận báo cáo từ đối tác, trích xuất thông tin và lưu vào database.
- Địa chỉ bounce nhận thư báo lỗi giao thư để cập nhật trạng thái delivery.

Ứng dụng thường **poll** hộp thư qua IMAP, nhận webhook từ provider hoặc nhận sự kiện từ một inbound email gateway. Trong tất cả cách này, **một email có thể được quan sát nhiều lần**:

- Poller khởi động lại và đọc lại cùng email.
- Consumer crash giữa khi lưu ticket và khi ghi nhận email đã xử lý.
- Webhook bị provider gửi lại vì request timeout.
- Một worker đang xử lý chậm khiến lease hết hạn và worker khác lấy lại cùng job.
- Người dùng chuyển thư giữa folder khiến ID IMAP của thư thay đổi.
- Hộp thư được khôi phục/migrate, làm thay đổi `UIDVALIDITY` hoặc ID do server cấp.

Nếu chỉ dùng `message.getSubject()` hay trạng thái `SEEN` của mailbox để xác định đã xử lý, hệ thống có thể tạo trùng ticket, bỏ qua thư chưa xử lý, hoặc mất khả năng phục hồi sau sự cố.

**Mục tiêu:** Lưu định danh phù hợp cho từng email nhận được, theo dõi trạng thái xử lý qua các lần poll/worker restart, và tạo các thao tác nghiệp vụ **idempotent** để một thư không gây side effect trùng ngoài dự kiến.

~~~text
Mailbox / inbound provider
           |
           v
    Fetch message metadata
           |
           v
  Establish mailbox-scoped identity
    (IMAP UID / UIDVALIDITY)
           |
           v
    Persist discovery record
           |
           v
         Work queue
           |
           v
 Claim + parse + validate + process
           |
        +--+----------------+----------------+
        |                   |                |
        v                   v                v
    PROCESSED             RETRY           FAILED
        |                   |                |
        v                   v                v
 Business effect      Next attempt    Review / dead letter
        |
        v
   Audit + metrics
~~~

> **Ranh giới cần nhớ:** Spring Framework Mail chủ yếu cung cấp API gửi (`JavaMailSender`). Đọc IMAP/POP3, lưu cursor, phân tích MIME, xử lý inbound webhook, lưu state/idempotency thường dùng **Jakarta Mail** cùng service, repository và worker do ứng dụng xây dựng; chúng không tự phát sinh từ `spring-boot-starter-mail`.

## 2. Phân biệt các loại ID liên quan đến một email

“Message ID” không phải chỉ có một loại. Cần tách ít nhất các khái niệm:

| Định danh | Ai cấp? | Phạm vi/đặc điểm | Dùng để làm gì? |
| --- | --- | --- | --- |
| **RFC `Message-ID` header** | Bên gửi/thư viện gửi, theo định dạng email | Có thể thiếu, trùng hoặc bị giả mạo | Liên kết hội thoại, tra cứu email gốc, đối soát phụ trợ |
| **IMAP UID** | IMAP server | Chỉ có ý nghĩa trong **một mailbox/folder cùng UIDVALIDITY** | Nhận diện bản ghi thư trên server, incremental sync |
| **IMAP UIDVALIDITY** | IMAP server | Đánh dấu “thế hệ” của UID trong folder | Phát hiện UID cũ không còn hợp lệ |
| **IMAP message sequence number** | Trạng thái folder hiện tại | Có thể thay đổi khi thư bị xóa/expunge | Chỉ để truy cập trong phiên, **không phải khóa bền vững** |
| **POP3 UIDL** | POP3 server nếu hỗ trợ | Token để nhận diện message qua nhiều phiên, theo mailbox/server | Chống đọc lặp trong mô hình POP3 |
| **Provider inbound event ID** | Provider/gateway | Theo hợp đồng của provider | Deduplicate webhook/event deliveries |
| **Application `inboundMessageId`** | Database của ứng dụng | UUID/ID nội bộ, bất biến | Khóa chính, trạng thái xử lý, audit |
| **`In-Reply-To` / `References`** | Header do mail client tạo | Tham chiếu Message-ID của thư khác | Threading/correlation, không phải UID của email hiện tại |

Một thiết kế tốt thường có **hai lớp định danh**:

1. **Source identity:** một khóa định danh email như nó được nhận tại một nguồn cụ thể, ví dụ `(mailbox_id, folder_key, uid_validity, uid)`.
2. **Internal identity:** `inbound_message.id` (UUID) do ứng dụng tạo và dùng ở tất cả bảng nghiệp vụ/log/attempt.

Header `Message-ID` nên được **lưu làm metadata và correlation**, nhưng không mặc định là unique key toàn cầu cho tất cả email inbound.

### 2.1. RFC Message-ID là một header, không phải khóa database được tin tuyệt đối

Một email có thể chứa:

~~~text
From: customer@example.net
To: support@example.com
Subject: Tôi cần hỗ trợ
Date: Thu, 12 Nov 2026 10:00:00 +0700
Message-ID: <request.20261112.abc123@example.net>
~~~

`Message-ID` được thiết kế làm identifier của một message theo chuẩn Internet Message Format (RFC 5322), và chương trình gửi thông thường cố tạo giá trị đủ duy nhất. Nhưng ở **ranh giới nhận thư**, không nên giả định:

- Mọi email đều có `Message-ID`.
- Header luôn hợp lệ về cú pháp.
- Hai thư khác nhau không bao giờ có cùng `Message-ID`.
- Giá trị do sender khai báo là đáng tin hoặc có quyền tác động đến dữ liệu nội bộ.
- Header đó sẽ được giữ nguyên qua mọi gateway, forward hoặc import.

Kẻ tấn công có thể tự tạo message với một `Message-ID` trùng message cũ. Nếu schema có `UNIQUE(message_id)` trên toàn bộ hệ thống rồi bỏ qua bản đến sau, người dùng hợp lệ có thể bị mất thư hoặc attacker gây gián đoạn xử lý.

### 2.2. IMAP UID chỉ bền vững trong phạm vi đúng

Giả sử hai folder:

~~~text
Mailbox: support@example.com
  INBOX:
    UIDVALIDITY = 1710000000
    UID 1200 -> message A

  Processed:
    UIDVALIDITY = 1710000500
    UID 1200 -> message B
~~~

Hai UID bằng `1200` không chứng minh hai bản ghi là cùng một email. Ngay cả **cùng folder**, khi `UIDVALIDITY` thay đổi, UID cũ không còn dùng làm khóa ổn định nữa.

Do đó, khóa IMAP gợi ý:

~~~text
(mailbox_id, folder_key, uid_validity, uid)
~~~

`mailbox_id` phải là định danh nguồn tài khoản/hộp thư **nội bộ được quản lý**, không chỉ một chuỗi display email có thể trùng giữa các môi trường. `folder_key` là khóa folder canonical theo account/server, nhất quán với quy tắc namespace của hệ thống.

### 2.3. Sequence number không được làm checkpoint

Trong IMAP, `Message.getMessageNumber()` là vị trí thứ tự trong folder ở một thời điểm. Sau khi thư bị expunge, vị trí của các message còn lại có thể thay đổi.

~~~text
Before expunge: seq=1(A), seq=2(B), seq=3(C)
Delete + expunge A
After expunge:  seq=1(B), seq=2(C)
~~~

Nếu lưu “đã xử lý đến messageNumber=2”, lần poll tiếp theo có thể bỏ sót C hoặc xử lý nhầm. Dùng UID và UIDVALIDITY khi IMAP server hỗ trợ, không dùng sequence number làm khóa database.

### 2.4. Provider ID và Message-ID không phải một

Một inbound email provider có thể gửi:

~~~json
{
  "eventId": "evt-5e2f...",
  "providerMessageId": "msg-a490...",
  "headers": {
    "Message-ID": "<request.abc@example.net>"
  }
}
~~~

`eventId` thường đại diện cho **lần phát sự kiện**; `providerMessageId` đại diện cho message theo hệ provider; header `Message-ID` do bên gửi email công bố. Cần dựa trên hợp đồng cụ thể của provider để định nghĩa khóa deduplication. Không trộn ba trường thành một `messageId` không rõ nguồn gốc.

## 3. Hai tình huống có thể gây mất thư hoặc tạo trùng

### 3.1. Dùng Message-ID làm UNIQUE toàn hệ thống

Giả sử khách hàng gửi hai email khác nhau nhưng mail client bị lỗi và tái dùng:

~~~text
Email #1:
  IMAP UID=501
  Message-ID=<same-id@example.net>
  Body="Tôi muốn đổi địa chỉ."

Email #2:
  IMAP UID=502
  Message-ID=<same-id@example.net>
  Body="Tôi muốn hủy đơn."
~~~

Nếu code thực hiện:

~~~sql
INSERT INTO inbound_message(message_id, body)
VALUES (:message_id, :body)
ON CONFLICT (message_id) DO NOTHING;
~~~

Email #2 có thể bị bỏ qua. Với source IMAP, nên nhận diện mỗi entry theo `mailbox_id/folder/uid_validity/uid` và lưu RFC Message-ID dưới dạng **non-unique, indexed metadata**.

### 3.2. Dựa vào cờ SEEN làm bằng chứng đã xử lý

Giả sử:

~~~text
Poller opens email
  |
  v
Marks message SEEN
  |
  v
Process crashes before saving ticket
  |
  v
Next poll searches UNSEEN only
  |
  v
Message is skipped forever
~~~

`\\Seen` của IMAP phản ánh trạng thái hiển thị/đọc ở mailbox, không phải transaction commit của ứng dụng. Mail client của nhân viên cũng có thể đặt cờ SEEN, hoặc server/library thay đổi cờ theo thao tác đọc.

Để lưu processing state, sử dụng **database/outbox nội bộ** và chỉ dùng IMAP flags như tín hiệu phụ hoặc workflow giao tiếp với người dùng khi thật sự cần.

### 3.3. Cần phân biệt “discovered” và “processed”

Một email đã được phát hiện nhưng chưa xử lý có thể nằm trong database:

~~~text
id = 9ad...
source = IMAP
mailbox_id = support-vn
folder_key = INBOX
uid_validity = 1710000000
uid = 501
rfc_message_id = <same-id@example.net>
status = DISCOVERED
~~~

Sau khi worker tạo ticket và commit trạng thái:

~~~text
status = PROCESSED
processed_at = ...
ticket_id = ...
~~~

Hai bước không nên bị gộp vào một dấu “đã đọc” trên IMAP server.

## 4. Định nghĩa vòng đời trạng thái xử lý

Một workflow inbound có thể dùng:

| Trạng thái | Ý nghĩa | Worker có được lấy? |
| --- | --- | --- |
| `DISCOVERED` | Đã ghi bền vững metadata/nguồn thư | Có khi đủ điều kiện |
| `FETCHED` (tùy chọn) | Đã tải/snapshot nội dung về storage nội bộ | Có |
| `PROCESSING` | Worker đang giữ claim/lease | Không claim lại khi lease hợp lệ |
| `RETRY` | Lỗi có thể hồi phục, đã lưu lịch thử tiếp | Có khi `next_attempt_at` đến hạn |
| `PROCESSED` | Side effect nghiệp vụ theo định nghĩa đã commit | Không xử lý tự động lần nữa |
| `IGNORED` | Bỏ qua có chủ đích theo rule, có reason | Không |
| `FAILED` | Dừng retry tự động, chờ triage/dead letter | Không |
| `QUARANTINED` | Nội dung đáng ngờ/chưa đạt điều kiện bảo mật | Không cho handler thường |
| `UNKNOWN` (tùy chọn) | Kết quả tác vụ bên ngoài chưa rõ | Cần đối soát |

Một đồ thị trạng thái:

~~~text
DISCOVERED ---> FETCHED (optional)
     |               |
     +-------+-------+
             |
             v
         PROCESSING
             |
     +-------+----------+---------------+--------------+
     |                  |               |              |
     v                  v               v              v
 PROCESSED            RETRY           FAILED        IGNORED
                        |               |
                        |               v
                        |          Operator triage
                        |               |
                        +-- next due <--+  (approved redrive)

Any suspicious input -> QUARANTINED
Ambiguous external side effect -> UNKNOWN/reconciliation
~~~

### 4.1. “Processed” phải có nghĩa cụ thể

Tùy nghiệp vụ:

- Email support: ticket đã được tạo và liên kết với inbound message.
- Email nhận hóa đơn: dữ liệu đã được parse, validate và lưu vào hệ thống.
- Email trả lời: comment/reply được gắn vào conversation.
- DSN/bounce: event đã được normalize, correlate và cập nhật delivery theo policy.

Không đánh dấu `PROCESSED` chỉ vì `getContent()` không ném exception, vì đó mới là đọc/parse MIME. Ngược lại, một thư rác bị bỏ qua có chủ đích có thể được đánh dấu `IGNORED`, không cần giả thành một ticket đã xử lý.

### 4.2. Trạng thái cuối không nhất thiết nghĩa thư bị xóa

`PROCESSED` và `FAILED` ở database là trạng thái nghiệp vụ nội bộ. Thư gốc có thể vẫn nằm trong INBOX hoặc được di chuyển sang folder khác tùy retention/workflow. Di chuyển/xóa trên IMAP không nên là bước duy nhất quyết định đã xử lý.

### 4.3. Retry count là số attempt nghiệp vụ

Một mô hình rõ ràng:

~~~text
attempt_count = 0  chưa worker nào claim
attempt_count = 1  đã bắt đầu xử lý lần đầu
attempt_count = 2  đã bắt đầu retry đầu tiên
...
~~~

Nếu chỉ tăng attempt count trong `catch(Exception)`, crash trước catch có thể làm lượt xử lý bị thất lạc khỏi lịch sử. Nên tăng trong một **transaction claim** và có attempt event riêng khi cần audit.

## 5. Kiến trúc tiếp nhận: discovery và processing là hai bước riêng

Với IMAP, một kiến trúc có thể chia thành:

~~~text
IMAP server
   |
   | Poll/read UID metadata
   v
Mailbox sync worker
   |
   +--> Compare UIDVALIDITY
   +--> Discover new UIDs
   +--> Insert inbound_message rows (idempotent)
   +--> Commit sync cursor only after inserts
   |
   v
Durable database / queue
   |
   v
Processing worker
   |
   +--> Atomically claim a row
   +--> Load/snapshot MIME content
   +--> Validate sender/content/attachments
   +--> Apply business handler
   +--> Commit outcome
   |
   v
Business database / event outbox
   |
   v
Optional IMAP mark/move + downstream actions
~~~

Ưu điểm:

- Poller chỉ cần phát hiện và ghi bền vững các email mới, không bị một file đính kèm lớn làm trì hoãn cả folder.
- Worker xử lý có thể retry độc lập với việc polling.
- Một email trùng UID có thể được phát hiện nhiều lần nhưng chỉ tạo **một record** nhờ unique constraint.
- Sau restart, các hàng `DISCOVERED`, `RETRY` và `PROCESSING` hết lease vẫn có thể được xử lý tiếp.
- Checkpoint phản ánh tiến độ **phát hiện an toàn**, không giả vờ mọi email trước cursor đã `PROCESSED`.

### 5.1. Discovery cursor khác processing checkpoint

Giả sử ở một thời điểm:

~~~text
IMAP UID 701 -> PROCESSED
IMAP UID 702 -> RETRY (timeout)
IMAP UID 703 -> PROCESSED
IMAP UID 704 -> DISCOVERED

last_discovered_uid = 704
~~~

Đây là trạng thái hợp lệ. Poller đã lưu các email tới UID 704 nhưng worker chưa xử lý xong 702 và 704. **Không thể dùng `last_discovered_uid=704` để kết luận tất cả email ≤704 đều hoàn tất**.

Processing state và attempt history phải gắn với từng row inbound. Nếu chỉ có một con số “last processed UID”, một email lỗi ở giữa khiến hệ thống phải chọn giữa đọc lại tất cả hoặc bỏ qua thư chưa xử lý.

### 5.2. Khi nào nên snapshot nội dung?

Có hai phương án:

| Phương án | Ưu điểm | Rủi ro |
| --- | --- | --- |
| **Lưu metadata + IMAP UID**, worker fetch MIME khi xử lý | Ít storage nội bộ, discovery nhanh | Email có thể bị xóa/move trước khi worker fetch; IMAP dependency kéo dài |
| **Lưu snapshot MIME/parsed payload** vào storage bền vững trước khi cho worker xử lý | Có thể retry kể cả khi IMAP folder thay đổi | Tốn storage, chứa PII/attachment, phải có quota, mã hóa, retention |

Nếu ứng dụng cần bảo đảm mỗi email đã tiếp nhận có thể được xử lý ngay cả khi nhân viên xóa/move thư, nên cân nhắc snapshot payload. Nếu chỉ dùng UID, cần định nghĩa trạng thái `SOURCE_MISSING` khi nguồn không còn có thể đọc và quy trình điều tra tương ứng; **không đánh dấu PROCESSED** để bỏ qua lỗi.

Đối với snapshot, không nhất thiết lưu nguyên email trong cột database. Có thể lưu MIME dưới dạng object trong storage riêng và chỉ giữ `payload_ref`, checksum, size, tenant/retention metadata ở DB. Thứ tự công việc phải bảo đảm object đã ghi bền vững trước khi record xử lý tham chiếu đến nó; có reconciler cho object mồ côi nếu transaction DB thất bại.

### 5.3. Một email có nhiều workflow độc lập

Nếu email vừa phải tạo ticket vừa phải cập nhật báo cáo thống kê, không nên đánh dấu cả hai việc trong một flag duy nhất mà không rõ nghĩa. Có thể dùng:

~~~text
inbound_message (message identity + snapshot)
    |
    +--> inbound_workflow_state(type="TICKET")
    |       DISCOVERED -> PROCESSING -> PROCESSED
    |
    +--> inbound_workflow_state(type="ANALYTICS")
            DISCOVERED -> PROCESSING -> RETRY
~~~

Mỗi workflow có unique key `(inbound_message_id, workflow_type)` và attempt history riêng. Với hệ thống nhỏ chỉ có một inbound handler, một trạng thái trên `inbound_message` có thể đủ; cần chọn schema theo nghiệp vụ.

## 6. Schema PostgreSQL cho message identity và trạng thái

Một thiết kế đơn giản bao gồm **mailbox nguồn**, **sync cursor**, **email đã phát hiện** và **lịch sử attempt**. SQL dưới đây minh họa cho mô hình IMAP một workflow; ứng dụng thực tế có thể thêm bảng tenant, data retention, encrypted payload reference và ownership.

### 6.1. Định danh mailbox nguồn

~~~sql
CREATE TABLE inbound_mailbox (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    logical_name VARCHAR(120) NOT NULL,
    source_type VARCHAR(30) NOT NULL DEFAULT 'IMAP',
    account_ref VARCHAR(200) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(tenant_id, logical_name)
);
~~~

`account_ref` là định danh cấu hình/secret reference do hệ thống quản lý, **không lưu password IMAP** vào bảng này. Một địa chỉ hiển thị như `support@example.com` có thể thuộc nhiều môi trường hoặc được đổi provider; `id` của mailbox cho phép giữ identity rõ ràng.

### 6.2. Sync cursor theo folder

~~~sql
CREATE TABLE inbound_mailbox_cursor (
    mailbox_id UUID NOT NULL REFERENCES inbound_mailbox(id),
    folder_key VARCHAR(250) NOT NULL,
    uid_validity BIGINT,
    last_discovered_uid BIGINT NOT NULL DEFAULT 0,
    last_successful_scan_at TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(mailbox_id, folder_key)
);
~~~

Ý nghĩa:

- `uid_validity`: thế hệ UID hiện tại của folder.
- `last_discovered_uid`: giới hạn UID đã **được quét thành công và lưu nhận dạng**, không phải UID đã xử lý nghiệp vụ.
- `last_successful_scan_at`: biết poller có còn hoạt động không.
- `last_error_code`: mã lỗi đã chuẩn hóa để cảnh báo.

Khi `UIDVALIDITY` thay đổi, không tiếp tục với cursor của thế hệ cũ. Cần khởi tạo đợt quét mới cho epoch mới, có reconciliation để tránh side effect trùng.

### 6.3. Bảng inbound_message

~~~sql
CREATE TABLE inbound_message (
    id UUID PRIMARY KEY,
    mailbox_id UUID NOT NULL REFERENCES inbound_mailbox(id),
    folder_key VARCHAR(250) NOT NULL,
    uid_validity BIGINT NOT NULL,
    imap_uid BIGINT NOT NULL,

    rfc_message_id VARCHAR(512),
    subject_excerpt VARCHAR(300),
    payload_ref VARCHAR(500),
    payload_sha256 CHAR(64),

    status VARCHAR(30) NOT NULL DEFAULT 'DISCOVERED',
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claim_token UUID,
    lease_owner VARCHAR(100),
    lease_until TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    last_error_kind VARCHAR(30),
    terminal_reason VARCHAR(100),

    discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_inbound_imap_identity UNIQUE(
        mailbox_id, folder_key, uid_validity, imap_uid
    ),
    CONSTRAINT chk_inbound_uid_positive CHECK (imap_uid > 0),
    CONSTRAINT chk_inbound_attempt_nonnegative CHECK (attempt_count >= 0)
);

CREATE INDEX ix_inbound_ready
    ON inbound_message(status, next_attempt_at);

CREATE INDEX ix_inbound_lease
    ON inbound_message(status, lease_until);

CREATE INDEX ix_inbound_header_message_id
    ON inbound_message(rfc_message_id);

CREATE INDEX ix_inbound_mailbox_recent
    ON inbound_message(mailbox_id, discovered_at DESC);
~~~

**Hai điểm quan trọng:**

1. Unique constraint nằm trên `mailbox_id + folder_key + uid_validity + imap_uid`, không nằm trên `rfc_message_id`.
2. `rfc_message_id` được index để tìm kiếm/correlation nhưng **không bắt buộc unique hoặc NOT NULL**.

Trong production, nếu cần lưu một header Message-ID dài hơn ngưỡng `VARCHAR(512)`, có thể giữ raw header trong vùng metadata giới hạn/ký số fingerprint với kiểm soát size, hoặc thay đổi schema theo policy. Không cắt một giá trị dài rồi coi chuỗi đã cắt là ID chính xác. Đặt giới hạn ingestion để chống payload bất thường là hợp lý, nhưng kết quả phải được ghi nhận rõ.

`subject_excerpt` chỉ để minh họa; subject có thể chứa PII. Không bắt buộc lưu subject, body hoặc địa chỉ gửi trong database nếu nghiệp vụ không cần. Với hệ thống nhạy cảm, chỉ lưu minimal metadata và encrypted payload reference.

### 6.4. Lịch sử xử lý và side effect

~~~sql
CREATE TABLE inbound_processing_attempt (
    id UUID PRIMARY KEY,
    inbound_message_id UUID NOT NULL
        REFERENCES inbound_message(id),
    attempt_no INT NOT NULL,
    claim_token UUID NOT NULL,
    worker_id VARCHAR(100),
    outcome VARCHAR(40) NOT NULL DEFAULT 'STARTED',
    error_code VARCHAR(100),
    safe_reason VARCHAR(300),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    UNIQUE(inbound_message_id, attempt_no)
);

CREATE TABLE support_ticket_origin (
    id UUID PRIMARY KEY,
    inbound_message_id UUID NOT NULL
        REFERENCES inbound_message(id),
    ticket_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(inbound_message_id)
);
~~~

`support_ticket_origin.UNIQUE(inbound_message_id)` là một lớp bảo vệ **business idempotency**: nếu worker retry sau crash, cùng bản inbound record không được tạo thêm ticket nữa. Nếu một message phục vụ nhiều loại workflow, dùng khóa kết hợp workflow type.

Lịch sử attempt cho biết số lần worker bắt đầu, khi nào thất bại, với lỗi gì. Không cần serialize toàn bộ exception, SMTP/IMAP transcript hoặc MIME body vào bảng audit.

### 6.5. Nhận lại cùng UID không được reset trạng thái

Khi poller thấy cùng UID nhiều lần:

~~~sql
INSERT INTO inbound_message (
    id, mailbox_id, folder_key, uid_validity,
    imap_uid, rfc_message_id, status
)
VALUES (
    :id, :mailbox_id, :folder_key, :uid_validity,
    :imap_uid, :message_id, 'DISCOVERED'
)
ON CONFLICT (
    mailbox_id, folder_key, uid_validity, imap_uid
) DO NOTHING;
~~~

`DO NOTHING` giữ nguyên row cũ, gồm `PROCESSED`, `RETRY`, `FAILED`, attempt count và audit. **Không viết `ON CONFLICT DO UPDATE SET status='DISCOVERED'`**: làm vậy một poller có thể kéo email đã xử lý trở về hàng chờ mỗi lần quét.

Nếu muốn cập nhật header metadata mới, cần bảo đảm update chỉ động tới các trường được phép, không reset state hoặc âm thầm thay body snapshot của delivery đã xử lý.

## 7. Đọc IMAP bằng Jakarta Mail và lấy UID đúng cách

Đối với IMAP, có thể dùng API của **Jakarta Mail** như `Session`, `Store`, `Folder`, `Message` và `UIDFolder`. Ví dụ dưới đây dùng `imaps` để kết nối có TLS tới server thử nghiệm hoặc provider được tổ chức ủy quyền.

### 7.1. Khởi tạo kết nối

~~~java
import java.util.Properties;
import jakarta.mail.Session;
import jakarta.mail.Store;

Properties props = new Properties();
props.setProperty("mail.store.protocol", "imaps");
props.setProperty("mail.imaps.ssl.checkserveridentity", "true");
props.setProperty("mail.imaps.connectiontimeout", "5000");
props.setProperty("mail.imaps.timeout", "15000");
props.setProperty("mail.imaps.writetimeout", "15000");

Session session = Session.getInstance(props);
Store store = session.getStore("imaps");
store.connect(
        "imap.example.net",
        993,
        imapUsername,
        imapPassword);
~~~

`imapUsername` và `imapPassword` phải được inject từ cấu hình runtime/secret manager, không hard-code. Nhiều mailbox provider yêu cầu OAuth2 hoặc app-specific credentials; **đăng nhập bằng password là ví dụ giao thức**, không phải chỉ dẫn bỏ qua chính sách xác thực provider.

`mail.imaps.ssl.checkserveridentity=true` giúp kiểm tra danh tính host với chứng chỉ. Không tắt certificate verification chỉ để test pass trên production. Với IMAP qua STARTTLS/port 143, các property khác với `imaps` và phải phù hợp endpoint thực tế.

### 7.2. Mở folder và đọc UIDVALIDITY

~~~java
import jakarta.mail.Folder;
import jakarta.mail.UIDFolder;

Folder folder = store.getFolder("INBOX");
folder.open(Folder.READ_ONLY);

if (!(folder instanceof UIDFolder uidFolder)) {
    throw new IllegalStateException(
            "IMAP folder does not expose UID operations");
}

long uidValidity = uidFolder.getUIDValidity();
long nextUid = uidFolder.getUIDNext();
~~~

**Đọc UIDVALIDITY trước khi dùng cursor cũ.** `getUIDNext()` cho biết dự đoán UID tiếp theo của folder tại thời điểm hỏi; `uidNext - 1` có thể dùng làm giới hạn upper bound cho một lượt scan có snapshot metadata. Nếu server không cung cấp giá trị hữu ích hoặc folder không ổn định, adapter phải có chiến lược an toàn khác, không tự giả định upper bound bất kỳ.

### 7.3. Vì sao không quét tới một UID tương lai tùy ý?

Giả sử:

~~~text
last_discovered_uid = 100
current UIDNEXT = 121

Poller queries UID range 101..600
Existing messages: 101..120
Poller stores cursor = 600

New mail arrives with UID 121
Next scan starts at 601 => UID 121 was skipped!
~~~

Đây là lỗi tinh vi. Chỉ đánh dấu quét xong tới **giới hạn server đã cấp tại thời điểm snapshot** (thường `UIDNEXT - 1`) hoặc tới UID cuối đã được xác thực theo một thuật toán scan an toàn. Không dùng `start + batchSize` làm cursor cuối vô điều kiện khi nó vượt quá UID đã có thể được cấp.

### 7.4. Poller minh họa với batch giới hạn

Một skeleton tách phần kết nối khỏi repository:

~~~java
package com.example.mail.inbound;

import java.util.ArrayList;
import java.util.List;
import java.util.Properties;
import java.util.UUID;

import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.Store;
import jakarta.mail.UIDFolder;
import jakarta.mail.internet.MimeMessage;

public final class ImapDiscoveryPoller {

    private static final int BATCH_UID_RANGE = 200;

    private final InboundDiscoveryRepository repository;
    private final InboundCursorService cursorService;

    public ImapDiscoveryPoller(
            InboundDiscoveryRepository repository,
            InboundCursorService cursorService) {
        this.repository = repository;
        this.cursorService = cursorService;
    }

    public void scan(
            UUID mailboxId,
            String host,
            String username,
            String password) throws Exception {

        Properties props = new Properties();
        props.put("mail.store.protocol", "imaps");
        props.put("mail.imaps.ssl.checkserveridentity", "true");
        props.put("mail.imaps.connectiontimeout", "5000");
        props.put("mail.imaps.timeout", "15000");

        Session session = Session.getInstance(props);
        Store store = null;
        Folder folder = null;

        try {
            store = session.getStore("imaps");
            store.connect(host, 993, username, password);
            folder = store.getFolder("INBOX");
            folder.open(Folder.READ_ONLY);

            if (!(folder instanceof UIDFolder uidFolder)) {
                throw new IllegalStateException(
                        "UIDFolder required for durable IMAP sync");
            }

            String folderKey = "INBOX";
            long validity = uidFolder.getUIDValidity();
            long uidNext = uidFolder.getUIDNext();

            if (validity <= 0 || uidNext <= 0) {
                throw new IllegalStateException(
                        "Invalid IMAP UID metadata");
            }

            CursorSnapshot cursor = cursorService
                    .forCurrentGeneration(
                            mailboxId, folderKey, validity);

            long highestAllocatedAtStart = uidNext - 1;
            long start = Math.max(1L, cursor.lastDiscoveredUid() + 1);

            while (start <= highestAllocatedAtStart) {
                long end = Math.min(
                        highestAllocatedAtStart,
                        start + BATCH_UID_RANGE - 1L);

                Message[] messages =
                        uidFolder.getMessagesByUID(start, end);
                List<DiscoveredImapMessage> found =
                        new ArrayList<>();

                for (Message message : messages) {
                    if (message == null) {
                        continue;
                    }
                    long uid = uidFolder.getUID(message);
                    if (uid <= 0) {
                        continue;
                    }
                    String rfcId =
                            message instanceof MimeMessage mime
                                    ? mime.getMessageID()
                                    : null;
                    found.add(new DiscoveredImapMessage(
                            uid, rfcId));
                }

                // Atomic DB transaction:
                // insert all discovered identities idempotently;
                // update cursor only after that persistence succeeds,
                // and only for matching mailbox/folder/UIDVALIDITY.
                repository.persistBatchAndAdvanceCursor(
                        mailboxId, folderKey, validity,
                        cursor, end, found);

                cursor = new CursorSnapshot(validity, end);
                start = end + 1;
            }
        } finally {
            if (folder != null && folder.isOpen()) {
                folder.close(false);
            }
            if (store != null && store.isConnected()) {
                store.close();
            }
        }
    }
}
~~~

`InboundDiscoveryRepository`, `InboundCursorService`, `CursorSnapshot` và `DiscoveredImapMessage` là **abstraction do ứng dụng triển khai**, không phải API built-in của Jakarta Mail hoặc Spring. Trong Java, khai báo các record/class tương ứng ở file phù hợp.

Ví dụ record:

~~~java
public record CursorSnapshot(
        long uidValidity,
        long lastDiscoveredUid) {
}

public record DiscoveredImapMessage(
        long uid,
        String rfcMessageId) {
}
~~~

Lớp trên là **skeleton kỹ thuật**, chưa có backoff, mailbox-level lease, storage snapshot, size limit, retry per-folder, handling server-side expunge hoặc version-aware reconciliation. Không copy nguyên xi như một mail importer production.

**Vấn đề concurrency:** nếu hai poller quét cùng mailbox/folder, phương thức `persistBatchAndAdvanceCursor` phải dùng transaction và optimistic compare-and-swap hoặc một mailbox-level lease để tránh hai tiến trình ghi cursor nhảy qua các batch chưa lưu. Một poller duy nhất theo mailbox/folder là lựa chọn dễ hiểu lúc ban đầu.

**Vấn đề thay đổi UIDVALIDITY:** nếu server thay đổi thế hệ UID trong lúc scan, batch mới không được ghi đè cursor của thế hệ khác. Đọc lại UIDVALIDITY, dùng generation guard trong transaction và khởi động lại scan khi phát hiện thay đổi.

### 7.5. Khi server đã xóa một UID trong khoảng

IMAP UID có thể có khoảng trống vì message bị expunge. Một batch UID 101..200 có thể chỉ còn message 105, 109 và 193. Điều này **không** có nghĩa 194..200 chưa được quét; với upper bound snapshot hợp lệ, có thể đánh dấu khoảng đã kiểm tra.

Nếu message bị xóa **trước khi poller khám phá**, hệ thống không thể dùng IMAP hiện tại để khôi phục nội dung đã mất. Nếu cần cam kết không mất email trong những workflow quan trọng, có thể dùng inbound gateway push, journal của provider hoặc policy giữ mail đủ lâu và snapshot kịp thời. Chỉ lưu cursor không tạo ra bảo đảm “không mất email” khi nguồn cho phép xóa trước lúc scan.

### 7.6. IMAP polling không nên tự động mark SEEN

Mở folder với `Folder.READ_ONLY` khi chỉ khám phá là cách đơn giản tránh chủ động cập nhật flags của mailbox. Không thiết kế poller dựa trên `Flag.SEEN` để xác định cần scan. Worker có thể đọc bằng `READ_ONLY` và lưu trạng thái ứng dụng trong database.

Nếu sau khi xử lý cần chuyển thư sang một folder `Processed` hoặc gắn flag, hãy coi đó là **bước hậu xử lý có thể retry/idempotent**, không phải transaction duy nhất xác nhận nghiệp vụ.

## 8. Commit cursor đúng cách để không bỏ sót

Một thuật toán an toàn cho mỗi batch:

~~~text
Read current mailbox cursor C and generation V
          |
          v
Read IMAP snapshot for UID range (C+1)..E
          |
          v
BEGIN DB transaction
          |
          +--> Verify cursor generation still V
          +--> Insert each discovered UID (ON CONFLICT DO NOTHING)
          +--> Update cursor to E, guarded by V and old C
          |
          v
COMMIT
          |
          v
Continue next batch
~~~

Nếu insert bất kỳ message nào hoặc cập nhật cursor thất bại, **rollback cả batch và không nâng cursor**. Lần poll kế tiếp sẽ đọc lại range đó. Unique constraint giúp lặp an toàn.

### 8.1. Ví dụ cập nhật cursor có điều kiện

~~~sql
UPDATE inbound_mailbox_cursor
SET last_discovered_uid = :end_uid,
    last_successful_scan_at = now(),
    updated_at = now()
WHERE mailbox_id = :mailbox_id
  AND folder_key = :folder_key
  AND uid_validity = :expected_validity
  AND last_discovered_uid = :expected_previous_uid;
~~~

Ứng dụng phải kiểm tra **số hàng được update là 1**. Nếu bằng 0, có poller khác đã thay cursor hoặc UIDVALIDITY vừa thay đổi; cần reload state và quyết định quét lại phần cần thiết, không coi batch đã commit thành công.

Đây chỉ là một phần của transaction. Toàn bộ `INSERT` và `UPDATE` cho batch phải commit cùng nhau. Nếu transaction rollback, không được cập nhật cursor ở một cache in-memory rồi persist sau.

### 8.2. Nếu cần hiệu năng cao hơn

Có thể:

- Dùng nhiều worker **xử lý** các inbound records đã lưu.
- Giữ **một coordinator khám phá** cho mỗi mailbox/folder hoặc lease phân vùng rõ.
- Dùng batch insert và index trên source identity.
- Chỉ fetch metadata ở discovery, chuyển attachment tải lớn sang worker.
- Dùng IMAP IDLE hoặc push notification **như tín hiệu thức dậy**, vẫn dùng UID/cursor để đối soát.

Không chia một folder IMAP thành các UID ranges do nhiều poller xử lý mà không có cơ chế theo dõi hoàn tất từng range, nếu chỉ có một cursor số nguyên. Một range cao commit trước trong khi range thấp chưa được lưu sẽ có nguy cơ bỏ sót.

### 8.3. IMAP IDLE không thay thế checkpoint

IMAP `IDLE` có thể giảm polling liên tục khi server hỗ trợ. Nhưng kết nối có thể ngắt, mạng có thể chập chờn và notification không phải event log bền vững của ứng dụng. Khi reconnect, vẫn cần **quét lại các UID sau cursor đã commit** để tránh mất message trong khoảng downtime.

## 9. Atomic claim: không để hai worker xử lý cùng một thư đồng thời

Sau bước discovery, nhiều worker có thể đọc các hàng `DISCOVERED` và `RETRY`. Nếu cả hai cùng:

~~~text
SELECT ... WHERE status='DISCOVERED'
       |
       +-- worker A thấy row #1
       +-- worker B cũng thấy row #1
       |
       +-- A tạo ticket
       +-- B tạo ticket lần nữa
~~~

thì xử lý bị trùng. Dùng một transaction **claim atomically** và thiết lập lease/claim token trước khi làm việc nặng.

### 9.1. PostgreSQL: FOR UPDATE SKIP LOCKED

Ví dụ chọn một inbound job đến hạn:

~~~sql
WITH selected AS (
    SELECT id
    FROM inbound_message
    WHERE status IN ('DISCOVERED', 'FETCHED', 'RETRY')
      AND next_attempt_at <= now()
    ORDER BY next_attempt_at, discovered_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE inbound_message AS m
SET status = 'PROCESSING',
    attempt_count = m.attempt_count + 1,
    claim_token = :claim_token,
    lease_owner = :worker_id,
    lease_until = now() + INTERVAL '2 minutes',
    updated_at = now()
FROM selected
WHERE m.id = selected.id
RETURNING m.id,
          m.attempt_count,
          m.mailbox_id,
          m.folder_key,
          m.uid_validity,
          m.imap_uid,
          m.payload_ref;
~~~

`:claim_token` là UUID do worker tạo riêng cho mỗi lượt claim. Với nhiều worker, một bản ghi có thể bị khóa bởi worker khác; `SKIP LOCKED` giúp các worker chọn những hàng khác mà không chờ lâu.

**Thực hiện claim trong một transaction ngắn rồi commit**, không giữ transaction/row lock trong suốt thời gian đọc MIME hoặc gọi API nghiệp vụ.

### 9.2. Lưu attempt history trong cùng transaction claim

Sau khi claim:

~~~sql
INSERT INTO inbound_processing_attempt (
    id, inbound_message_id, attempt_no,
    claim_token, worker_id, outcome
)
VALUES (
    :attempt_id, :inbound_message_id, :attempt_no,
    :claim_token, :worker_id, 'STARTED'
);
~~~

Claim và `INSERT attempt` nên nằm **trong cùng transaction**, để nếu insert lịch sử thất bại thì row không bị kẹt trong `PROCESSING` mà không có bằng chứng nào.

### 9.3. Cập nhật kết quả phải có fencing

Sau khi xử lý xong, worker cập nhật:

~~~sql
UPDATE inbound_message
SET status = 'PROCESSED',
    processed_at = now(),
    claim_token = NULL,
    lease_owner = NULL,
    lease_until = NULL,
    last_error_code = NULL,
    updated_at = now()
WHERE id = :inbound_message_id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token;
~~~

Nếu update count bằng `0`, worker có thể đã mất quyền sở hữu job hoặc một worker khác đã reclaim. **Không ghi đè trạng thái mới** bằng kết quả của một attempt cũ.

Nếu worker cần heartbeat/extend lease khi xử lý attachment lâu:

~~~sql
UPDATE inbound_message
SET lease_until = now() + INTERVAL '2 minutes'
WHERE id = :inbound_message_id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token;
~~~

Heartbeat chỉ thành công khi token còn hợp lệ. Không kéo dài lease vô hạn nếu worker đã không tiến triển; hệ thống cần timeout và quy tắc xử lý job treo.

### 9.4. Claim token chỉ ngăn stale write, không tự ngăn side effect

Giả sử:

~~~text
Worker A claims job, lease=2m
Worker A is blocked on external ticket API
Lease expires
Worker B reclaims and starts same job
Worker A resumes and calls ticket API
Worker B also calls ticket API
~~~

Fencing token bảo vệ **database status update**, nhưng nếu ticket API không dùng idempotency key, có thể vẫn tạo **hai ticket**. Cần phối hợp atomic DB transaction hoặc idempotency key ở hệ thống nhận side effect.

## 10. Xử lý nghiệp vụ idempotent

Hệ thống inbound qua IMAP/webhook thường có ngữ nghĩa **at-least-once**: một message hoặc event có thể được đọc/phát lại sau crash. Mục tiêu là **không tạo side effect trùng** dù số lần chạy handler lớn hơn một.

### 10.1. Tạo ticket và đánh dấu PROCESSED trong một transaction

Nếu ticket và inbound state nằm cùng PostgreSQL database, có thể dùng **một database transaction**:

~~~text
Worker owns inbound_message claim token
        |
        v
BEGIN transaction
        |
        +--> Validate claim still current
        |
        +--> INSERT business ticket / comment
        |
        +--> INSERT support_ticket_origin
        |    UNIQUE(inbound_message_id)
        |
        +--> UPDATE inbound_message status=PROCESSED
        |    WHERE id and claim_token match
        |
        v
COMMIT
~~~

Nếu transaction rollback, cả ticket và trạng thái `PROCESSED` đều rollback. Khi retry, worker có thể thực hiện lại mà không tạo một ticket chỉ được commit một nửa.

Trong code thật, thứ tự thao tác/khóa cần được thiết kế để không có tình huống origin đã tồn tại nhưng worker vẫn tạo ticket mới trước khi phát hiện unique violation. Có thể dùng `INSERT ... ON CONFLICT`, tra record nguồn trước hoặc một service idempotent thực hiện atomically.

### 10.2. Java/Spring @Transactional minh họa

~~~java
package com.example.mail.inbound;

import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class InboundTicketHandler {

    private final InboundMessageRepository inbound;
    private final SupportTicketRepository tickets;

    public InboundTicketHandler(
            InboundMessageRepository inbound,
            SupportTicketRepository tickets) {
        this.inbound = inbound;
        this.tickets = tickets;
    }

    @Transactional
    public void completeTicketProcessing(
            UUID inboundId,
            UUID claimToken,
            ParsedInboundMail parsed) {

        InboundRecord current = inbound
                .lockForClaim(inboundId, claimToken)
                .orElseThrow(() ->
                        new StaleClaimException(inboundId));

        if (current.isProcessed()) {
            return;
        }

        tickets.createFromInboundOnce(
                current.tenantId(),
                inboundId,
                parsed);

        if (!inbound.markProcessed(inboundId, claimToken)) {
            throw new StaleClaimException(inboundId);
        }
    }
}
~~~

`InboundMessageRepository`, `SupportTicketRepository`, `ParsedInboundMail`, `StaleClaimException` là **abstraction do ứng dụng triển khai**, không phải class sẵn có của Spring Mail.

Hai method `createFromInboundOnce` và `markProcessed` phải dùng database uniqueness/claim guard thật; một `exists(...)` check in memory **không đủ** trước concurrent workers. Transaction chỉ bao phủ các bảng cùng transaction manager/database.

### 10.3. Khi side effect nằm ở service bên ngoài

Giả sử handler gọi HTTP API tạo ticket ở hệ thống khác:

~~~text
POST remote ticket API -> success
      |
      v
Local DB commit fails
      |
      v
Inbound row remains RETRY/PROCESSING
      |
      v
Retry calls POST again -> duplicate ticket possible
~~~

Không có transaction duy nhất giữa IMAP, local DB và HTTP API. Các giải pháp:

- Gửi `Idempotency-Key` ổn định theo **business operation** nếu API bên ngoài hỗ trợ.
- Dùng **transactional outbox** để ghi ý định tạo ticket cùng commit xử lý inbound, rồi dispatcher gửi command ra API.
- Lưu external object ID và reconcile nếu request timeout sau khi remote service đã xử lý.
- Nếu không thể dedupe, định nghĩa rủi ro duplicate và quy trình vận hành thay vì tuyên bố exactly-once.

Ví dụ:

~~~text
inbound_message.id = 8c4...
business operation = CREATE_SUPPORT_TICKET
idempotencyKey = "inbound-ticket:8c4..."
~~~

Một inbound email có thể dẫn đến nhiều business operation khác nhau, vì vậy key cần gắn với **operation**, không chỉ message ID. Không tạo key mới ngẫu nhiên cho mỗi retry nếu mục tiêu là idempotent.

### 10.4. Khi một email tới nhiều mailbox hoặc folder

Sẽ có hai nhu cầu khác nhau:

1. **Dedupe kỹ thuật:** cùng entry trong cùng folder/UIDVALIDITY chỉ tạo một inbound row.
2. **Dedupe nghiệp vụ:** cùng yêu cầu khách hàng được forward/copy tới nhiều mailbox nhưng sản phẩm chỉ muốn một ticket.

Khóa IMAP xử lý điều (1); điều (2) phải dựa trên quy tắc nghiệp vụ đáng tin cậy, ví dụ case ID do ứng dụng phát hành, token trả lời được xác thực, external document reference hoặc business identifier có kiểm tra tenant.

**Không dùng duy nhất RFC `Message-ID` để hợp nhất mọi email qua mọi mailbox**: attacker có thể tự khai cùng header nhằm bỏ qua hoặc gắn nhầm nội dung; mail client cũng có thể tạo ra sự trùng không chủ ý.

## 11. Retry và dead letter của email inbound

Một lỗi đọc mail hoặc xử lý payload có thể là tạm thời hoặc vĩnh viễn:

| Giai đoạn | Ví dụ | Cách xử lý đề xuất |
| --- | --- | --- |
| IMAP connect/auth | Server unavailable, credential sai | Retry connect có backoff; cảnh báo auth nếu credential bị revoke |
| IMAP source read | Timeout, folder temporarily unavailable | Retry fetch nếu source identity còn hợp lệ |
| MIME parse | MIME hỏng, quá sâu, charset lạ | Phân loại; quarantine/FAILED nếu không thể xử lý an toàn |
| Attachment scanning | Scanner tạm offline | Retry sau backoff |
| Attachment malicious | File độc hại hoặc không được phép | QUARANTINED, không retry thông thường |
| Business validation | Thiếu mã đơn hàng, tenant không khớp | IGNORED/FAILED theo policy; không đoán |
| Database write | Deadlock/temporary outage | Retry có giới hạn |
| External API | Timeout sau khi tác vụ có thể đã thành công | UNKNOWN/reconcile/idempotency key |
| Source disappeared | Email bị xóa/move trước khi fetch | FAILED/SOURCE_MISSING hoặc tìm snapshot hợp lệ |

Không gọi mọi exception là “IMAP lỗi”. Cần lưu `failure_stage` và `error_code` đã chuẩn hóa để biết phải sửa kết nối, MIME parser, dữ liệu nghiệp vụ hay hệ thống bên ngoài.

### 11.1. Backoff và max attempts

Một chính sách ví dụ:

~~~text
max_attempts = 5
initial_delay = 30 seconds
max_delay = 15 minutes
jitter = enabled

Attempt #1 fails transiently -> RETRY after 30s
Attempt #2 fails transiently -> RETRY after 60s
Attempt #3 fails transiently -> RETRY after 120s
Attempt #4 fails transiently -> RETRY after 240s
Attempt #5 fails transiently -> FAILED / dead letter
~~~

Đây là **ví dụ chính sách**, không phải mặc định Spring Mail. Với email quan trọng, retention của nguồn IMAP phải đủ lâu để worker còn truy cập được nội dung trong suốt thời gian retry; nếu không, cần snapshot bền vững trước.

### 11.2. Cập nhật RETRY có claim token

~~~sql
UPDATE inbound_message
SET status = 'RETRY',
    next_attempt_at = :next_attempt_at,
    last_error_code = :error_code,
    last_error_kind = 'TRANSIENT',
    lease_owner = NULL,
    claim_token = NULL,
    lease_until = NULL,
    updated_at = now()
WHERE id = :inbound_message_id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token;
~~~

Transaction xử lý retry nên cập nhật attempt history và row inbound cùng nhau. Nếu đã hết lượt, trạng thái có thể là `FAILED` với `terminal_reason=MAX_ATTEMPTS_EXHAUSTED`. Không đổi mọi transient error thành “permanent” chỉ vì hết retry; giữ cả **loại lỗi** và **lý do dừng**.

### 11.3. Dead letter cần còn đủ thông tin phục hồi

Một record `FAILED` nên giữ:

- Inbound source identity: mailbox/folder/UIDVALIDITY/UID hoặc provider event ID.
- Internal inbound message ID và tenant/workflow scope.
- Trạng thái và lịch sử attempt.
- Mã lỗi đã chuẩn hóa và giai đoạn lỗi.
- Metadata về snapshot/correlation đã bảo vệ, nếu được giữ.
- Thời điểm thất bại, số lượt đã thử và người xử lý/redrive.

Nếu payload đã bị xóa theo retention, không được redrive mù rồi tin rằng sẽ có dữ liệu. Cần báo `PAYLOAD_UNAVAILABLE` hoặc yêu cầu nguồn gửi lại bằng một kênh hợp lệ.

### 11.4. Redrive phải có audit

Một thao tác retry thủ công nên:

1. Kiểm tra quyền operator và phạm vi tenant.
2. Xác nhận nguyên nhân đã khắc phục.
3. Kiểm tra source/snapshot còn khả dụng, deadline và security policy.
4. Đảm bảo không có side effect đã hoàn thành mà chưa ghi trạng thái.
5. Ghi audit actor, reason, timestamp, trạng thái trước/sau.
6. Đưa vào lịch xử lý có giới hạn concurrency/rate.

Không reset `attempt_count` về 0 hoặc xóa attempt history chỉ để “cho retry tiếp”. Nếu cấp một retry cycle mới, định nghĩa rõ trong policy và giữ audit trước đó.

## 12. UIDVALIDITY thay đổi: một trong những trường hợp quan trọng nhất

Theo cơ chế IMAP, UID chỉ được xem là định danh bền trong **một mailbox với cùng UIDVALIDITY**. Khi server rebuild folder, restore dữ liệu, migrate hộp thư hoặc có thay đổi thế hệ UID, `UIDVALIDITY` có thể thay đổi.

Giả sử:

~~~text
Before restore:
  folder=INBOX
  UIDVALIDITY=1000
  UID=50 -> Customer mail A
  last_discovered_uid=300

After restore:
  folder=INBOX
  UIDVALIDITY=2000
  UID=50 -> Customer mail B
  next UID=75
~~~

Nếu poller không kiểm tra UIDVALIDITY và tiếp tục scan từ `301`, nó **bỏ qua toàn bộ thư trong thế hệ mới**. Nếu coi UID=50 của thế hệ mới là cùng thư cũ, nó có thể **bỏ qua nhầm customer mail B**.

### 12.1. Cơ chế phát hiện

Mỗi lần mở folder:

~~~text
stored UIDVALIDITY = 1000
server UIDVALIDITY = 2000
           |
           v
Generation mismatch
           |
           v
Stop using old cursor
           |
           v
Start new epoch scan / reconciliation
~~~

Không ghi `uid_validity=2000` nhưng giữ `last_discovered_uid=300`. Cần reset cursor theo epoch mới **có audit**, ví dụ trở về `0` trước khi scan, và không xóa các inbound row của epoch cũ để chỉ dùng lại UID trùng.

### 12.2. Không xóa lịch sử cũ khi UIDVALIDITY đổi

Thay vì:

~~~sql
DELETE FROM inbound_message
WHERE mailbox_id = :mailbox_id
  AND folder_key = :folder_key;
~~~

nên giữ lịch sử theo `uid_validity`, còn cursor là pointer của thế hệ hiện tại. Nếu nội dung xuất hiện lại trong epoch mới, có thể tạo một source identity mới và đưa qua **business deduplication** để quyết định có nên tạo side effect lần nữa.

Không dùng `Message-ID` làm khóa duy nhất để tự động bỏ mọi bản trong epoch mới, vì có thể có message bị spoof/duplicate hoặc message mới hợp lệ mang cùng header.

### 12.3. Atomic reset cursor

Ví dụ SQL trong transaction, dưới một mailbox-level lock/lease:

~~~sql
UPDATE inbound_mailbox_cursor
SET uid_validity = :new_uid_validity,
    last_discovered_uid = 0,
    last_error_code = NULL,
    updated_at = now()
WHERE mailbox_id = :mailbox_id
  AND folder_key = :folder_key
  AND uid_validity = :old_uid_validity;
~~~

Nếu cursor chưa được khởi tạo, dùng một nhánh `INSERT` riêng. Kiểm tra update count, vì poller khác có thể vừa cập nhật epoch. Không chạy reset lặp lại chỉ dựa trên một biến in-memory stale.

Một đợt scan lại có thể tạo nhiều record inbound mới do những thư cũ còn trong folder. Hãy phân biệt **duplicate source copy** và **business duplicate**; có thể cần manual review với luồng tạo side effect nhạy cảm.

### 12.4. Trạng thái PROCESSING từ epoch cũ

Nếu worker đã claim row có `UIDVALIDITY=1000` nhưng server hiện chỉ còn epoch 2000, worker không còn có thể fetch lại thư bằng UID cũ. Nếu đã có snapshot bền vững, xử lý tiếp theo snapshot đó. Nếu chưa:

- Mark attempt lỗi `SOURCE_GENERATION_CHANGED` hoặc `SOURCE_UNAVAILABLE`.
- Không âm thầm fetch cùng số UID trong epoch mới.
- Không đánh dấu PROCESSED nếu chưa có đủ dữ liệu để hoàn thành side effect.
- Có thể tìm lại nguồn tương ứng bằng metadata bổ sung nếu chính sách cho phép, nhưng đừng dựa duy nhất vào RFC Message-ID.

Đây là lý do snapshot content có thể cần thiết với inbound workflow quan trọng.

## 13. Chuyển hoặc sao chép thư giữa folder

Với IMAP, UID nằm trong phạm vi folder. Di chuyển một email từ `INBOX` sang `Processed` thường khiến nó có UID khác trong folder đích, vì server có thể tạo một entry mới.

~~~text
INBOX:
  (UIDVALIDITY=10, UID=201) -> mail A
            |
            | MOVE/COPY
            v
Processed:
  (UIDVALIDITY=20, UID=87) -> mail A
~~~

Hai source identities khác nhau có thể cùng chứa một nội dung email. Vì vậy:

- Nếu ứng dụng chỉ quét `INBOX`, di chuyển thư sau khi xử lý có thể là một workflow hữu ích.
- Nếu quét cả `INBOX` và `Processed`, phải tránh tạo side effect hai lần theo business policy.
- Đừng giả định UID ở folder đích bằng UID nguồn.
- Không chuyển thư sang `Processed` **trước** khi commit trạng thái nghiệp vụ nếu hậu quả là poller không còn tìm được nội dung cần xử lý lại.

### 13.1. Thứ tự sau khi xử lý

~~~text
Fetch/parse input
   |
   v
Commit business side effect + inbound PROCESSED
   |
   v
Optional IMAP flag/move
   |
   v
Record move/flag result for retry if needed
~~~

Nếu bước move thất bại, DB vẫn biết email đã `PROCESSED`; lần thử thao tác folder sau không được tạo ticket thêm.

Nếu ứng dụng có requirement “chỉ đánh dấu PROCESSED sau khi email đã di chuyển thành công”, hãy mô hình hóa thêm một trạng thái như `POST_PROCESSING_PENDING` thay vì biến mọi lỗi move thành lý do chạy lại business handler.

### 13.2. Không dùng Message-ID để chứng minh hai entry là một

Một email copy qua folder có thể giữ cùng RFC Message-ID, nhưng một attacker cũng có thể gửi thư khác cùng header. Để tránh duplicate side effect, có thể lưu:

- Link do ứng dụng tạo ở lúc move nếu biết source và destination.
- Provider message identity nếu provider có định danh xuyên folder đáng tin cậy.
- Payload fingerprint/normalized content hash **chỉ như tín hiệu hỗ trợ** với policy chặt.
- Một business operation key được xác minh qua tenant/conversation/ticket.

Không đồng nhất nội dung gần giống nhau với cùng một hành động. Hai phản hồi “OK” từ cùng khách hàng có thể là hai email hợp lệ khác nhau.

## 14. POP3 UIDL và sự khác biệt với IMAP

Nếu hệ thống nhận thư qua **POP3**, nó thường không có khái niệm folder/UIDVALIDITY giống IMAP. Nhiều POP3 server cung cấp lệnh `UIDL` để trả một ID ổn định cho từng message trong mailbox qua các phiên.

~~~text
POP3 mailbox:
  message sequence 1 -> UIDL ab123
  message sequence 2 -> UIDL xy456
~~~

**Không lưu POP3 message number** như khóa bền vững vì message list có thể thay đổi khi thư bị xóa. Nên lưu một source key:

~~~text
(pop3_account_id, uidl)
~~~

Đây là mô hình thường dùng khi server hỗ trợ UIDL đúng cách. Phải kiểm tra hợp đồng/implementation thật; server có thể có hành vi khác khi migrate/rebuild mailbox, và POP3 cung cấp ít metadata/khả năng đồng bộ hơn IMAP.

### 14.1. POP3 có rủi ro khi xóa thư sau khi đọc

Một flow POP3:

~~~text
Connect
  |
  v
List UIDL values
  |
  v
Fetch mail
  |
  v
Persist durable inbound record
  |
  v
Process safely
  |
  v
Delete from server when policy allows
~~~

Đừng xóa message ngay khi fetch nếu database chưa lưu bền vững và workflow có yêu cầu phục hồi. POP3 delete thường có các quy tắc commit khi session kết thúc; adapter cần hiểu cách server xử lý DELETE/QUIT và lỗi connection.

### 14.2. Nếu POP3 server không hỗ trợ UIDL

Không có một khóa bền vững tương đương IMAP UID+UIDVALIDITY. Có thể:

- Ưu tiên chuyển sang IMAP hoặc inbound gateway nếu hạ tầng cho phép.
- Tạo fingerprint từ metadata + content với giới hạn size, xem là heuristic chứ không phải định danh tuyệt đối.
- Snapshot nội dung ngay khi nhận và dùng DB record/idempotency nghiệp vụ.
- Có cơ chế manual review với các collision/duplicate case.

**Không dùng RFC Message-ID đơn lẻ làm thay thế hoàn hảo cho UIDL.**

## 15. Webhook inbound: event ID và message ID cần lưu riêng

Một số dịch vụ email cung cấp **inbound routing** và gọi webhook HTTP tới ứng dụng khi có thư mới. Khác IMAP polling, cần nhận và xác minh event trước khi parse nội dung.

~~~text
Inbound email provider
       |
       v
POST /webhooks/inbound-mail
       |
       v
Verify provider signature / timestamp
       |
       v
Extract provider event ID + message ID
       |
       v
Persist durable event (unique provider + event ID)
       |
       v
Ack HTTP only after durable receipt
       |
       v
Worker parses MIME / performs business handler
~~~

Một provider có thể gửi lại **cùng event** khi request timeout. Trong trường hợp này, unique key như:

~~~text
(provider_id, provider_event_id)
~~~

có thể chặn webhook redelivery theo hợp đồng provider. Nhưng **một email có thể sinh nhiều event khác nhau**, và một provider event ID không nhất thiết bằng provider message ID. Nếu ứng dụng cũng poll IMAP cho cùng mailbox, cần một tầng correlation/dedupe nghiệp vụ chung, không trộn hai source key.

### 15.1. Schema webhook event

~~~sql
CREATE TABLE inbound_provider_event (
    id UUID PRIMARY KEY,
    provider_id VARCHAR(100) NOT NULL,
    provider_event_id VARCHAR(250) NOT NULL,
    provider_message_id VARCHAR(250),
    rfc_message_id VARCHAR(512),
    inbound_message_id UUID,
    status VARCHAR(40) NOT NULL DEFAULT 'RECEIVED',
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(provider_id, provider_event_id)
);
~~~

Chỉ áp dụng unique constraint khi provider **bảo đảm event ID ổn định qua các lần delivery lại** và có namespace rõ ràng. Nếu provider dùng một ID cho nhiều event type, cần thêm `event_type` vào composite key theo schema thật.

### 15.2. Ngăn xử lý hai lần khi webhook bị gửi lại

Ví dụ:

~~~text
POST event E1
  -> signature valid
  -> INSERT event E1
  -> COMMIT
  -> return 200/202

Provider retries E1
  -> signature valid
  -> ON CONFLICT DO NOTHING
  -> return 200/202
  -> no duplicate processing side effect
~~~

Điều kiện: event đã được **lưu bền vững** trước khi trả response thành công. Nếu code trả `200` rồi mới đẩy vào một queue in-memory, crash có thể làm mất email mà provider tưởng đã được tiếp nhận.

### 15.3. Không tin webhook không xác thực

Email chứa header tùy ý có thể đến từ người ngoài; webhook HTTP cũng có thể bị giả nếu endpoint công khai. Hãy:

- Xác minh chữ ký/secret/mTLS theo provider.
- Dùng raw request body nếu thuật toán ký yêu cầu.
- Chặn replay bằng timestamp/event ID khi provider hỗ trợ.
- Giới hạn request size, số attachment và MIME nesting.
- Không cho phép payload tự khai `tenantId` hoặc mailbox owner mà bỏ qua ánh xạ account đã được ủy quyền.
- Không log raw body có PII/attachment.

## 16. Message-ID trong luồng trả lời và conversation threading

Ngoài chống xử lý trùng, RFC `Message-ID` rất hữu ích khi ứng dụng cần nhận **email trả lời**. Mail client thường thêm `In-Reply-To` hoặc `References` chứa ID của các message trước đó trong cuộc hội thoại.

Ví dụ hệ thống gửi email hỗ trợ:

~~~text
Outbound email:
  From: support@example.com
  To: customer@example.net
  Subject: Ticket #T123
  Message-ID: <ticket-T123-001@mail.example.com>

Inbound reply:
  From: customer@example.net
  To: support@example.com
  Subject: Re: Ticket #T123
  Message-ID: <reply-customer-777@example.net>
  In-Reply-To: <ticket-T123-001@mail.example.com>
  References: <ticket-T123-001@mail.example.com>
~~~

Trong trường hợp này:

- `Message-ID` của **email nhận** là `<reply-customer-777@example.net>`.
- `In-Reply-To` trỏ tới ID của **email trước đó**.
- `References` thể hiện chuỗi tham chiếu.
- `IMAP UID` của email trả lời **khác hoàn toàn** các header trên.

Nếu lưu cả ba loại dữ liệu, hệ thống có thể:

1. Dùng IMAP UID + UIDVALIDITY để biết thư đã được phát hiện chưa.
2. Dùng internal inbound ID để quản lý trạng thái xử lý.
3. Dùng `In-Reply-To`/`References` để **tìm ticket/conversation ứng viên**.

### 16.1. Lưu outbound Message-ID để đối chiếu

Một bảng mapping đơn giản:

~~~sql
CREATE TABLE outbound_message_reference (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    ticket_id UUID NOT NULL,
    outbound_delivery_id UUID NOT NULL,
    rfc_message_id VARCHAR(512) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(tenant_id, outbound_delivery_id)
);

CREATE INDEX ix_outbound_reference_message_id
    ON outbound_message_reference(tenant_id, rfc_message_id);
~~~

Không ép `rfc_message_id` unique toàn hệ thống nếu ứng dụng không thể cam kết ID được tạo và giữ chính xác, và không tin ID do email inbound khai là một quyền truy cập. Với email outbound do ứng dụng quản lý, nên chủ động tạo hoặc ghi nhận Message-ID đã được transport thực sự sử dụng theo Jakarta Mail/provider, rồi lưu mapping bền vững.

Nếu dùng SMTP, `JavaMailSender.send(...)` không trả một provider-specific message ID chuẩn. Việc lấy/đặt Message-ID và bảo đảm header được giữ cần được kiểm tra với MIME/Jakarta Mail implementation thực tế. Một số transport có thể tạo hoặc thay header khi `saveChanges()`/send. Vì vậy, lưu thông tin correlation cùng attempt và quan sát message được gửi thực tế.

### 16.2. Không tin In-Reply-To để cho phép sửa ticket

Một attacker có thể gửi:

~~~text
From: attacker@example.net
In-Reply-To: <ticket-T123-001@mail.example.com>
~~~

Nếu ứng dụng chỉ cần tìm thấy `In-Reply-To` rồi gắn nội dung vào ticket của khách hàng khác, có thể xảy ra **conversation hijacking** hoặc lộ dữ liệu.

Một bộ kiểm tra nên bao gồm:

- Ticket thuộc đúng tenant và vùng dữ liệu.
- Sender/correspondent có được phép tham gia ticket không.
- Các địa chỉ và thread references được canonicalize theo chính sách an toàn.
- Reply token nếu được sử dụng phải có entropy đủ cao, có expiry/scope và không thể đoán.
- Nội dung/attachment phải được sanitize/quarantine trước khi tạo comment hiển thị.
- Không suy từ header `From` đơn lẻ rằng người gửi đã được xác thực; email From có thể bị spoof.

`In-Reply-To` hỗ trợ **tìm kiếm ngữ cảnh**, không thay authorization.

### 16.3. Parse References có giới hạn

`References` có thể chứa nhiều Message-ID:

~~~text
References:
  <root@example.com>
  <followup@example.net>
  <ticket-T123-001@mail.example.com>
~~~

Ứng dụng nên:

1. Parse theo định dạng header email, không dùng `split(" ")` đơn giản cho mọi trường hợp.
2. Giới hạn số lượng token/header bytes.
3. Giữ đúng dạng/giá trị ID khi lưu; đừng tùy tiện lowercase toàn chuỗi.
4. Chỉ tra cứu trong tenant/conversation scope phù hợp.
5. Giải quyết trường hợp nhiều reference map tới các ticket khác nhau bằng policy rõ, không ghép nhầm.

Đối với support mailbox, một **reply-to alias có token riêng** (ví dụ `support+opaqueTicketToken@example.com`) đôi khi ổn định hơn chỉ dựa vào subject/thread header, nhưng cũng cần bảo vệ, routing và authorization. Không tạo token từ số ticket tuần tự có thể đoán rồi coi đó là bí mật.

### 16.4. Subject không phải conversation ID

Ví dụ nhiều email cùng subject:

~~~text
Subject: Báo lỗi
Subject: Re: Báo lỗi
Subject: Báo lỗi
~~~

Không chứng minh chúng cùng một ticket. Subject có thể bị sửa, chuẩn hóa prefix `Re:` không đồng nhất giữa client/ngôn ngữ, và attacker có thể tự đặt subject. Nếu không có correlation đáng tin cậy, tạo một conversation mới hoặc đưa vào hàng chờ phân loại theo policy.

## 17. Xử lý DSN/bounce bằng message ID

Một hệ thống inbound còn có thể nhận email bounce:

~~~text
Original outbound:
  Message-ID: <delivery-abc@mail.example.com>
  Envelope MAIL FROM: bounces@bounce.example.com

Later inbound DSN:
  MIME type: multipart/report
  Inner part: message/delivery-status
  Final-Recipient: rfc822; unknown@example.net
  Action: failed
  Status: 5.1.1
~~~

Một DSN có thể đính kèm header hoặc message gốc, từ đó chứa original `Message-ID`. Nhưng không phải DSN nào cũng trả đủ metadata, và một DSN có thể báo trạng thái cho **nhiều recipient**.

Vì vậy:

- Lưu inbound IMAP identity của **chính DSN** để tránh xử lý nó hai lần.
- Lưu provider/DSN event ID nếu có để chống redelivery.
- Parse per-recipient `Action`, `Status` và `Final-Recipient`.
- Correlate tới outbound delivery và recipient theo nguồn đáng tin, có thể dùng envelope token/VERP hoặc provider message ID.
- Không dùng một RFC `Message-ID` duy nhất để cập nhật tất cả recipient trong một outbound batch.
- Không suppress địa chỉ chỉ vì một email có `From: MAILER-DAEMON` hoặc một DSN tự khai trạng thái lỗi; thư nhận có thể giả mạo.

Nếu DSN chưa xác thực hoặc không map được outbound delivery, trạng thái nên là `UNKNOWN/NEEDS_REVIEW`. Bỏ qua những nguyên tắc này có thể khiến attacker làm hệ thống ngừng gửi thông báo cho người dùng hợp lệ.

## 18. Bảo mật và quyền riêng tư khi lưu metadata inbound

Email nhận có thể chứa dữ liệu nhạy cảm hơn email gửi: nội dung khách hàng chưa được kiểm soát, file lạ, thông tin cá nhân hoặc bí mật bị gửi nhầm. Lưu state/message ID phải kèm chính sách bảo vệ dữ liệu.

### 18.1. Phân loại dữ liệu

| Dữ liệu | Rủi ro | Gợi ý |
| --- | --- | --- |
| `rfc_message_id` | Có thể chứa tên miền/định danh người gửi | Không dùng làm metric label, giới hạn log |
| `From` / `To` / `Reply-To` | PII, có thể bị giả mạo | Lưu tối thiểu, kiểm soát quyền |
| `Subject` | Có thể chứa thông tin bệnh án, hóa đơn, tài khoản | Tránh lưu nếu không cần; không log raw |
| MIME body/attachments | PII, malware, secret, HTML nguy hiểm | Quarantine/scan, lưu mã hóa với retention |
| IMAP UID | Metadata kỹ thuật | Luôn scope theo mailbox/folder/UIDVALIDITY |
| Credential IMAP/OAuth | Bí mật truy cập mailbox | Secret manager, scope tối thiểu, rotation |
| Processing state/attempts | Thông tin nội bộ, event history | RBAC, audit và retention |
| Inbound webhook raw payload | Có thể chứa toàn bộ MIME | Verify trước khi xử lý, hạn chế lưu |

### 18.2. Message-ID và header khác đều là dữ liệu không tin cậy

Khi lưu vào SQL:

- Dùng prepared statements/ORM binding, không nối trực tiếp header vào SQL.
- Giới hạn độ dài/charset/control characters theo hợp đồng dữ liệu.
- Không đưa raw header vào HTML dashboard mà không escape đúng context.
- Không dùng header làm filesystem path, object key tùy ý hoặc tên metric label.
- Không lưu `Message-ID` như một quyền để sửa ticket.
- Khi log, dùng internal UUID/opaque correlation ID thay vì raw email address.

Header có thể chứa newline/folding. Khi parse hoặc chuyển metadata sang response HTTP, không cho phép CRLF injection vào các HTTP headers hoặc log fields.

### 18.3. Không tự mở attachment chưa kiểm tra

Inbound parser có thể gặp:

- `multipart/mixed` với file PDF/ZIP/Office.
- HTML chứa script/link tracking.
- `message/rfc822` lồng nhau.
- Archive nén nhiều lớp hoặc MIME tree sâu.
- Attachment khai báo content type sai.

Tầng nhận nên có:

1. Giới hạn message bytes và attachment bytes.
2. Giới hạn MIME depth, part count, charset decoding.
3. Malware scanning/allowlist theo workflow.
4. Không tin filename/content-type là bằng chứng an toàn.
5. Không tự thực thi attachment hoặc load HTML active content.
6. Tách quarantine khỏi nghiệp vụ xử lý thường.
7. Hạn chế số worker xử lý message lớn để tránh DoS.

Một thư không parse được hoặc chứa file nguy hiểm không nên bị retry vô hạn. Lưu trạng thái `QUARANTINED` hoặc `FAILED` có reason cụ thể.

### 18.4. Data residency và multi-tenant

Nếu một ứng dụng có nhiều mailbox theo tenant/region:

- `mailbox_id` phải liên kết với tenant được cấp quyền.
- Queue, snapshot object storage và audit phải tuân thủ phạm vi dữ liệu được duyệt.
- Worker không được xử lý inbound message của tenant khác chỉ vì biết UUID.
- `In-Reply-To` và `References` lookup phải lọc theo tenant.
- Không gửi MIME raw về dashboard tổng hợp không có phân quyền.
- Đổi provider/mailbox không được vô tình làm mọi email thành một namespace ID chung.

Đặt tên mailbox `eu-support` không chứng minh dữ liệu/backup/log được xử lý trong EU. Chính sách data residency cần xem xét toàn bộ đường ingest → storage → processing → events.

### 18.5. Retention và quyền xóa

Một chiến lược retention có thể tách:

~~~text
Original MIME snapshot: short, encrypted retention
Attachments: quarantine/TTL according to content policy
Processing events: sufficient for audit, without raw body
RFC Message-ID: retain only as long as correlation requires
Business ticket: separate domain retention and legal policy
~~~

Không có một số ngày chung cho tất cả ứng dụng. Khi payload bị xóa theo yêu cầu, không để dead-letter redrive ngầm tái tạo/xuất lại dữ liệu vượt phạm vi được phép.

## 19. Logs, metrics và cảnh báo

Một hệ thống nhận mail cần quan sát **đầu vào, tiến độ đồng bộ và kết quả handler**; chỉ biết IMAP còn kết nối không đủ.

| Metric | Loại | Câu hỏi |
| --- | --- | --- |
| `inbound_discovered_total` | Counter | Có bao nhiêu source messages mới đã được ghi? |
| `inbound_discovery_duplicate_total` | Counter | Có bao nhiêu lần UID đã có được quét lại? |
| `inbound_processing_attempt_total` | Counter | Worker đã thử xử lý bao nhiêu lượt? |
| `inbound_processing_completed_total` | Counter | Bao nhiêu workflow thực sự hoàn tất? |
| `inbound_processing_failed_total` | Counter | Lỗi terminal theo reason/stage nào? |
| `inbound_retry_scheduled_total` | Counter | Có bao nhiêu lần lên lịch xử lý lại? |
| `inbound_queue_ready` | Gauge | Còn bao nhiêu email tới hạn chưa xử lý? |
| `inbound_queue_inflight` | Gauge | Bao nhiêu email đang giữ lease? |
| `inbound_oldest_ready_age_seconds` | Gauge | Thư đến hạn lâu nhất đang chờ bao lâu? |
| `inbound_imap_poll_duration_seconds` | Timer | Mất bao lâu để quét folder? |
| `inbound_mailbox_last_scan_age_seconds` | Gauge | Poller có dừng từ lâu không? |
| `inbound_uidvalidity_reset_total` | Counter | Server có đổi thế hệ UID không? |
| `inbound_expired_lease_total` | Counter | Có bao nhiêu job bị reclaim sau lease? |
| `inbound_source_missing_total` | Counter | Bao nhiêu UID không còn có thể fetch? |
| `inbound_unmatched_reply_total` | Counter | Có bao nhiêu reply chưa map được ticket? |

### 19.1. Phân biệt số mail phát hiện với số mail xử lý

Giả sử:

~~~text
discovered_last_5m = 200
processed_last_5m = 50
retry_due = 30
processing = 10
oldest_ready_age = 12 minutes
~~~

Poller vẫn hoạt động, nhưng worker xử lý không theo kịp. Nếu dashboard chỉ hiển thị `IMAP connected=true`, người vận hành có thể bỏ qua backlog đang tăng.

Ngược lại, nếu `discovered=0` trong khi mailbox thực sự không có thư, đây có thể là trạng thái bình thường. Cần kết hợp nguồn tạo email/schedule và thời điểm quét thành công để phân biệt **không có thư mới** với **poller đã chết**.

### 19.2. Structured log

~~~json
{
  "event": "inbound.processing.retry_scheduled",
  "inboundMessageId": "opaque-uuid",
  "sourceType": "IMAP",
  "mailboxLogicalGroup": "support",
  "workflow": "TICKET",
  "attempt": 3,
  "failureStage": "BUSINESS_API",
  "safeErrorCode": "REMOTE_TIMEOUT",
  "nextAttemptAt": "2026-11-12T12:15:00Z"
}
~~~

Đừng log password, OAuth token, toàn bộ message body, attachment hoặc raw error message có thể chứa PII. Nếu cần tìm theo UID, lưu ID nội bộ vào log và tra source identity qua hệ quản trị có quyền truy cập.

### 19.3. Cảnh báo có thể hành động

- **Mailbox không được poll thành công trong khoảng vượt SLO:** kiểm tra mạng, AUTH, UIDVALIDITY/IMAP error.
- **Oldest ready age tăng:** worker backlog hoặc business handler chậm.
- **UIDVALIDITY reset tăng:** có khả năng server migrate/restore, cần đánh giá duplicate/rerun.
- **Source missing tăng:** user/client có thể move/delete trước snapshot, hoặc dữ liệu retention quá ngắn.
- **Failed/quarantine tăng:** parser regression, malware campaign hoặc dữ liệu không tương thích.
- **Expired leases tăng:** worker crash, timeout dài hoặc lease quá ngắn.
- **External side-effect UNKNOWN tăng:** cần reconciliation trước retry.

Không dùng địa chỉ email, RFC Message-ID, UID hoặc tenant UUID có cardinality lớn làm Prometheus label. Có thể dùng source type, mailbox group, workflow, status, error category với danh sách giá trị hữu hạn.

## 20. Kiểm thử lưu ID, cursor và trạng thái xử lý

Đối với cơ chế inbound, test không chỉ cần một email đọc được. Những lỗi khó nhất nằm ở **retry, race condition, folder mutation, UIDVALIDITY, duplicate header và ranh giới database transaction**.

### 20.1. Ma trận test tối thiểu

| Kịch bản | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| IMAP UID mới | `UIDVALIDITY=1, UID=10` chưa tồn tại | Insert một row `DISCOVERED` |
| Quét lại cùng UID | Lần thứ hai thấy `(mailbox, folder, 1, 10)` | Không thêm row, không reset state |
| Hai UID, cùng RFC Message-ID | UID 10 và 11 cùng header | Lưu **hai source records**, không bỏ thư 11 |
| Không có Message-ID | Header thiếu/null | Vẫn lưu source record theo UID |
| UID giống nhau ở hai folder | `INBOX/10` và `Archive/10` | Hai source identities khác nhau |
| UID giống nhau, UIDVALIDITY khác | `V1/10` và `V2/10` | Không coi là cùng source identity |
| Sequence number đổi sau expunge | Message numbers thay đổi | Dedupe/cursor vẫn theo UID |
| User mark SEEN trước poll | Flag SEEN đã bật | Poller vẫn phát hiện UID chưa ghi |
| Poller crash trước commit batch | Insert/cursor transaction chưa commit | Batch được quét lại, không skip |
| Poller crash sau commit batch | DB đã ghi rows + cursor | Không tạo side effect trùng |
| Worker crash trước xử lý | Row PROCESSING, lease hết hạn | Được reclaim theo policy |
| Worker crash sau ticket commit | Ticket+PROCESSED cùng transaction | Không tạo ticket thứ hai |
| External API success, local commit fail | Outcome mơ hồ | Reconcile hoặc idempotency key |
| MIME lỗi hoặc oversized | Payload cố ý không hợp lệ | FAILED/QUARANTINED, không retry vô hạn |
| Mail chuyển folder | UID mới ở folder đích | Hành vi nghiệp vụ theo dedupe policy |
| Webhook gửi lại cùng event ID | Hai HTTP POST giống nhau | Một durable event, một side effect |
| In-Reply-To giả mạo | Header trỏ tới ticket khác tenant | Không được nối vào ticket trái quyền |
| Cursor generation đổi giữa batch | UIDVALIDITY update cạnh tranh | Abort/reload, không advance nhầm epoch |
| Quá nhiều UID gaps | Range chứa ít message | Cursor vẫn tiến theo snapshot upper bound hợp lệ |

### 20.2. Unit test khóa định danh

Ví dụ model identity:

~~~java
import java.util.UUID;

public record ImapSourceIdentity(
        UUID mailboxId,
        String folderKey,
        long uidValidity,
        long uid) {

    public ImapSourceIdentity {
        if (mailboxId == null || folderKey == null
                || folderKey.isBlank()
                || uidValidity <= 0 || uid <= 0) {
            throw new IllegalArgumentException(
                    "Invalid IMAP source identity");
        }
    }
}
~~~

JUnit test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;

class ImapIdentityTest {

    @Test
    void uidMustBeScopedByFolderAndValidity() {
        UUID mailboxId = UUID.randomUUID();

        ImapSourceIdentity inboxOld =
                new ImapSourceIdentity(
                        mailboxId, "INBOX", 100, 22);
        ImapSourceIdentity inboxNew =
                new ImapSourceIdentity(
                        mailboxId, "INBOX", 200, 22);
        ImapSourceIdentity archive =
                new ImapSourceIdentity(
                        mailboxId, "Archive", 100, 22);

        assertThat(inboxOld).isNotEqualTo(inboxNew);
        assertThat(inboxOld).isNotEqualTo(archive);
    }
}
~~~

Test này chỉ kiểm tra **domain model**, chưa chứng minh database unique constraint được thiết lập đúng. Nên có integration test dùng database engine phù hợp production.

### 20.3. Test unique constraint với PostgreSQL

Với Testcontainers PostgreSQL hoặc một database test tương thích production:

1. Insert row `(M1, INBOX, V1, UID10)`.
2. Insert lại đúng source identity, `ON CONFLICT DO NOTHING`.
3. Assert số inbound rows = 1 và trạng thái ban đầu không bị reset.
4. Insert row `(M1, INBOX, V1, UID11)` với **cùng `rfc_message_id`**.
5. Assert số rows = 2.
6. Insert row `(M1, Archive, V1, UID10)`.
7. Assert số rows = 3.
8. Insert row `(M1, INBOX, V2, UID10)`.
9. Assert số rows = 4.

Không dùng H2 mặc định để chứng minh hành vi `ON CONFLICT`, row lock hoặc `SKIP LOCKED` của PostgreSQL đúng, vì SQL dialect và concurrency semantics có thể khác.

### 20.4. Test atomic cursor advance

Kịch bản:

~~~text
Stored cursor: lastUid=100, validity=10
IMAP UIDNEXT snapshot: 121
Available UIDs: 101, 102, 108, 120

Expected:
  persist each available identity
  commit lastDiscoveredUid=120
  no skipping of UID121 arriving later
~~~

Thêm fault injection:

- Repository insert throw exception trước commit.
- Transaction rollback hoàn toàn.
- Cursor giữ `100`.
- Lần tiếp theo vẫn scan UID 101..120.

Nếu code commit cursor trước khi insert đủ records, test này phải thất bại.

### 20.5. Test UIDVALIDITY reset

Fixture:

~~~text
Database: validity=100, cursor=700
IMAP server: validity=200, nextUid=41
~~~

Kỳ vọng:

- Không scan từ UID701.
- Không cập nhật validity=200 mà giữ cursor=700.
- Tạo/activate generation mới với cursor 0 theo policy.
- Scan UIDs trong generation 200.
- Không xóa lịch sử generation 100.
- Dedupe business side effects nếu những thư cũ xuất hiện trở lại và policy xác định là cùng nghiệp vụ.

Việc ép một server IMAP test đổi UIDVALIDITY có thể khó; có thể test **cursor service** bằng fake UID metadata, còn integration test sử dụng GreenMail/IMAP server để xác nhận đường đi thực tế.

### 20.6. Test hai worker claim đồng thời

Kịch bản:

~~~text
Insert DISCOVERED row D1
Worker A and worker B claim at the same time
       |
       v
Exactly one obtains claimToken for D1
       |
       v
attempt_count = 1
one STARTED attempt row
~~~

Với PostgreSQL, chạy hai transaction ở các connection độc lập, xác nhận logic `FOR UPDATE SKIP LOCKED`/claim state. Sau đó mô phỏng lease hết hạn, worker C reclaim và thử cho worker A ghi `PROCESSED` bằng token cũ: update count phải bằng 0.

### 20.7. Test idempotency của business handler

Giả sử một inbound email tạo ticket:

~~~text
Attempt 1:
  inboundId=D1
  create ticket T1
  commit support_ticket_origin(D1 -> T1)
  commit inbound_message.PROCESSED

Attempt 2 (manual replay):
  inboundId=D1
  should not create T2
  result still maps to T1
~~~

Nếu side effect nằm ngoài database, test phải giả lập retry của external API với **cùng idempotency key** và phản hồi duplicate theo hợp đồng API.

### 20.8. Test webhook redelivery

- Event E1 với signature hợp lệ → ghi vào DB.
- Gửi E1 một lần nữa → một record/event, không tăng business counter lần hai.
- Signature sai → không ghi dữ liệu.
- Event ID E1 của provider khác → xử lý namespace đúng theo hợp đồng.
- Same provider message ID nhưng event ID khác → không tự coi mọi event là một.
- Event đến không đúng thứ tự → projection không bị ghi đè sai.

Đừng test webhook bằng một controller trả `200` mà không kiểm tra transaction đã commit; đó là đúng điểm hệ thống dễ làm mất event.

### 20.9. Test IMAP thực bằng mail server giả lập

Một mail server test hỗ trợ SMTP+IMAP như **GreenMail** có thể dùng để:

1. Khởi động mailbox test, với account riêng và credential giả.
2. Gửi email mẫu qua SMTP vào mailbox test.
3. Kết nối IMAP bằng Jakarta Mail.
4. Đọc UID, UIDVALIDITY và RFC Message-ID.
5. Chạy poller, xác nhận inbound row được lưu.
6. Chạy poller lần nữa, xác nhận không trùng row.
7. Mark SEEN qua IMAP client khác; xác nhận poller không bỏ email chưa có record.
8. Cho worker xử lý, xác nhận database state và business side effect.

Chọn dependency GreenMail tương thích với `jakarta.mail.*` trong Spring Boot phiên bản dùng. SMTP sink chỉ nhận và giữ mail như Mailpit **không nhất thiết cung cấp IMAP server**, vì vậy test nhận thư cần công cụ hỗ trợ đúng giao thức.

Test server giúp kiểm chứng luồng SMTP→IMAP local, không chứng minh behavior của mọi IMAP provider production; cần staging smoke test với account được phép nếu provider có đặc tính riêng.

## 21. Runbook: thư nhận bị xử lý trùng

Khi người dùng báo một email tạo hai ticket hoặc cùng một hóa đơn bị import hai lần:

**Bước 1 — Tìm internal inbound ID.** Xác định ticket/business records, source mailbox, thời điểm phát hiện và request correlation. Không tìm chỉ bằng subject, vì subject có thể trùng.

**Bước 2 — So source identity.** Hai side effects đến từ:

- Cùng một `(mailbox, folder, uid_validity, uid)`? → Có khả năng **claim/idempotency** sai.
- Hai UID khác nhau nhưng cùng RFC Message-ID? → Có thể hai email riêng, bản copy/forward hoặc Message-ID trùng.
- Hai folder/epoch khác nhau nhưng cùng nội dung? → Kiểm tra move/copy/UIDVALIDITY reset.
- Webhook và IMAP cùng ingest một thư? → Kiểm tra multi-source business dedupe.

**Bước 3 — Kiểm tra attempt history.** Có nhiều worker claim song song? Có `PROCESSING` hết lease, worker cũ tiếp tục side effect? Có error sau side effect nhưng trước commit `PROCESSED`?

**Bước 4 — Kiểm tra unique constraints.** `uq_inbound_imap_identity` và unique business origin key có tồn tại trong database thật không? Application chỉ `existsBy...` rồi insert có thể race.

**Bước 5 — Xác định tác động.** Có bao nhiêu ticket/comment/billing operation bị trùng? Xử lý reconcile theo nghiệp vụ, không xóa tự động email gốc hoặc audit.

**Bước 6 — Khắc phục và test lại.** Bổ sung atomic claim/fencing, idempotency business key, và test crash window trước khi đưa worker chạy lại.

### 21.1. Vì sao “UNIQUE(Message-ID)” không phải bản sửa lỗi hoàn chỉnh?

Nó có thể giảm một số duplicate nhưng còn tạo lỗi mới:

- Chặn email hợp lệ do sender tạo header trùng.
- Bị attacker lợi dụng để khiến email mới bị bỏ qua.
- Không xử lý khi email **không có Message-ID**.
- Không giải quyết business side effect đã xảy ra nhưng state commit thất bại.
- Không phân biệt webhook event ID và thư gốc.

Chống xử lý trùng cần **source-level dedup + business-level idempotency**, không chỉ một unique index trên header.

## 22. Runbook: thư bị bỏ sót sau restart

Triệu chứng: hộp thư có email nhưng ứng dụng không tạo record, thường xuất hiện sau deploy, restore hoặc kết nối gián đoạn.

1. Kiểm tra mailbox/folder cấu hình có đúng, account có quyền đọc không.
2. Kiểm tra `last_successful_scan_at` và error code của poller.
3. So `UIDVALIDITY` hiện tại với DB; nếu khác, không dùng cursor cũ.
4. Xác nhận `last_discovered_uid` không lớn hơn upper bound của generation mới.
5. Kiểm tra code có dùng `getMessageNumber()` hoặc `SEEN` làm checkpoint không.
6. Kiểm tra cursor có được commit **trước** khi insert hết inbound rows hay không.
7. Kiểm tra có người dùng/client đã move/expunge email trước khi poller quét không.
8. Nếu cần backfill, chọn lại khoảng UID/generation dưới một mailbox-level lock và để unique constraint ngăn insert trùng.
9. Không reset tất cả state `PROCESSED` thành `DISCOVERED` để “đọc lại cho chắc”.

### 22.1. Xử lý cursor lệch generation

Ví dụ:

~~~text
Database:
  UIDVALIDITY=1422
  last_discovered_uid=58000

IMAP:
  UIDVALIDITY=1433
  UIDNEXT=90
~~~

Giải pháp đúng là ghi nhận **new UID generation** và scan từ đầu thế hệ mới, không tiếp tục UID58001. Những email đã được xử lý trong thế hệ cũ giữ nguyên audit; nếu bản copy xuất hiện lại, xử lý qua chính sách business deduplication.

## 23. Runbook: trạng thái PROCESSING không bao giờ kết thúc

Một inbound record `PROCESSING` lâu bất thường có thể do:

- Worker chết sau claim.
- IMAP fetch treo hoặc attachment lớn.
- MIME parser/antivirus scanner đang chạy quá thời hạn.
- External ticket API không trả lời.
- Lease/heartbeat bị lỗi.
- Database không cập nhật được outcome.

Trước khi reclaim:

1. Xem `lease_until` và claim token hiện tại.
2. Xem worker heartbeat và log theo internal inbound ID.
3. Xác định side effect bên ngoài **có thể đã hoàn thành** chưa.
4. Nếu chỉ là worker chết trước khi xử lý, có thể retry.
5. Nếu external API outcome mơ hồ, dùng reconciliation/idempotency key trước khi gọi lại.
6. Khi worker mới claim, tạo claim token mới và yêu cầu mọi state update kiểm tra token.
7. Theo dõi số lần reclaim và nguyên nhân để điều chỉnh timeout/concurrency.

Không tăng thời gian lease vô hạn chỉ để che worker bị treo. Ngược lại, lease quá ngắn có thể khiến hai worker xử lý trùng một MIME attachment lớn; cần timeout và heartbeat phù hợp.

## 24. Bảng xử lý sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Đọc lại tất cả thư mỗi lần start | Không lưu cursor hoặc cursor chỉ ở memory | Dùng DB cursor theo mailbox/folder/generation |
| Bỏ sót mail sau restore | UIDVALIDITY đổi, cursor không reset | Detect epoch change + reconciliation |
| Bỏ sót mail sau khi nhân viên đọc | Chỉ search UNSEEN | Scan UID; state lưu ở database |
| Một mail tạo hai ticket | Claim race hoặc side effect thiếu idempotency | Atomic claim + business unique key |
| Hai mail khác nhau bị coi là một | Dùng RFC Message-ID làm unique | Source-scoped IMAP UID key |
| Email không có Message-ID bị từ chối | Schema `NOT NULL` trên header | Cho phép null; dùng source identity |
| UID giống nhau ở hai folder bị conflict | Unique constraint chỉ dùng UID | Thêm mailbox/folder/UIDVALIDITY |
| UID sequence biến đổi gây skip | Lưu message number | Dùng UIDFolder API |
| New mail bị bỏ sót sau scan | Cursor nâng vượt UIDNEXT snapshot | Bound range theo UIDNEXT-1; commit batch |
| Crash khi ghi batch làm mất mail | Cursor commit trước inserts | Một transaction cho inserts + cursor |
| MOVE sang Processed làm xuất hiện thư mới | Folder đích có UID khác | Tách source identity và business idempotency |
| IMAP message không fetch được | Bị xóa/move hoặc generation đổi | Snapshot bền vững hoặc SOURCE_MISSING |
| POP3 đọc trùng sau restart | Không lưu UIDL hoặc chỉ lưu sequence | UIDL-scoped key và state database |
| Webhook tạo hai tác vụ | Retry cùng event ID, thiếu unique constraint | Event key + atomic ingestion |
| Webhook mất email sau trả 200 | Ack trước khi persist durable | Persist/queue bền vững rồi ack |
| Reply gắn nhầm ticket | Tin In-Reply-To/subject mà không authorize | Tenant + sender/ticket permission checks |
| Failed handler retry vô hạn | Không phân loại permanent/limit | Retry policy và terminal state |
| Quá nhiều IMAP connections | Mỗi email mở Store mới hoặc pool không giới hạn | Per-mailbox poll lifecycle/capacity controls |
| Heap tăng khi nhận attachment | Load toàn bộ MIME vào memory | Streaming/size cap và worker limit |
| Dashboard hiện không có mail | Collector mất kết nối DB nhưng gauge=0 | Snapshot freshness/error metric |
| Log lộ nội dung email | Ghi raw MIME/headers/ticket token | Structured safe logs, RBAC, retention |

## 25. Các câu hỏi thường gặp

**“Message-ID và IMAP UID có giống nhau không?”**  
Không. RFC `Message-ID` là header của email do phía gửi tạo; IMAP UID do server hộp thư cấp cho một entry trong folder, có giá trị trong phạm vi UIDVALIDITY tương ứng. Chúng phục vụ hai mục đích khác nhau.

**“Có nên dùng Message-ID làm primary key?”**  
Thường không cho ingestion từ email không tin cậy. Header có thể thiếu, trùng hoặc bị giả mạo. Dùng UUID nội bộ làm primary key và unique source identity cho IMAP, giữ Message-ID để tìm kiếm/threading.

**“Nếu email không có Message-ID thì làm sao?”**  
Vẫn ghi nhận bằng khóa nguồn như `mailbox + folder + UIDVALIDITY + UID`. Có thể để `rfc_message_id=NULL` và chỉ bật các tính năng correlation khi có đủ dữ liệu.

**“Nếu cùng Message-ID xuất hiện hai lần thì có phải duplicate?”**  
Chưa chắc. Có thể là cùng message được copy/forward, một lỗi phía gửi hoặc thư bị giả mạo. Dedupe nguồn theo UID; dedupe nghiệp vụ dựa trên điều kiện và khóa được xác minh.

**“Nếu Message-ID khác nhưng body giống thì sao?”**  
Hai email vẫn có thể là hai hành động riêng hợp lệ. Content hash chỉ nên là tín hiệu hỗ trợ, không tự merge mọi thư có body giống nhau.

**“Có thể lưu hash của Message-ID thay vì raw string không?”**  
Có thể nếu cần tra cứu chính xác mà giảm lưu raw header, nhưng hash không giải quyết vấn đề Message-ID trùng/giả mạo. Cần canonicalization ổn định và policy bảo mật phù hợp.

**“Có cần lưu IMAP folder name không?”**  
Có nếu dùng UID như source identity; cùng UID ở hai folder không có nghĩa cùng entry. Lưu một folder key ổn định theo namespace của account/server.

**“UID có liên tục như 1, 2, 3 không?”**  
Không nhất thiết. UID có thể có khoảng trống vì server không còn message tương ứng. Poller phải xử lý UID gaps mà không coi đó là lỗi.

**“UIDVALIDITY dùng để làm gì?”**  
Nó cho biết UID đang thuộc thế hệ nào của folder. Nếu UIDVALIDITY đổi, các UID cũ không được sử dụng để đồng nhất message trong thế hệ mới.

**“Có nên lưu message.getMessageNumber()?”**  
Có thể lưu tạm để debug một phiên, nhưng không làm khóa nhận dạng hay checkpoint bền vững; message number có thể thay đổi khi folder expunge.

**“Làm thế nào để không bỏ sót thư mới khi quét UID range?”**  
Chọn upper bound từ snapshot UID metadata hợp lệ (ví dụ `UIDNEXT-1`), lưu mọi record trong range, rồi commit cursor cùng transaction. Không nâng cursor tới một UID tương lai chưa được server cấp.

**“Có thể chỉ đọc UNSEEN để tiết kiệm thời gian không?”**  
Chỉ dùng như một bộ lọc phụ nếu nghiệp vụ chấp nhận rủi ro. Với hệ thống cần ingest đầy đủ, cờ SEEN có thể do người dùng/mail client thay đổi; unique UID + cursor đáng tin hơn.

**“Có thể mark SEEN khi đã xử lý không?”**  
Có thể như một hành động hậu xử lý, nhưng database `PROCESSED` vẫn là nguồn trạng thái nghiệp vụ. Nếu thao tác IMAP thất bại, không nên tạo side effect lần nữa.

**“Nếu move email sang folder Processed thì UID có giữ nguyên không?”**  
Không nên giả định. UID được cấp trong folder đích có thể khác; identity cần bao gồm folder và UIDVALIDITY.

**“Tại sao cursor đã vượt UID của email mà row vẫn là RETRY?”**  
Cursor discovery chỉ cho biết email đã được tìm thấy/lưu. Trạng thái xử lý độc lập; một email UID thấp có thể còn retry trong khi UID cao đã processed.

**“Một inbound mailbox có thể có nhiều poller không?”**  
Có thể, nhưng phải có mailbox-level lease hoặc cơ chế chia range/completion rõ. Với một cursor đơn giản, một poller phối hợp theo folder thường dễ tránh skip và race hơn.

**“Nếu server xóa email trước khi worker fetch thì sao?”**  
Nếu chỉ lưu UID, content có thể không còn. Cần đánh dấu lỗi source missing hoặc thử khôi phục từ snapshot; với workflow quan trọng nên lưu payload bền vững trước khi quá muộn.

**“POP3 có UIDVALIDITY không?”**  
Không theo mô hình IMAP. POP3 thường có UIDL để xác định message qua các phiên nếu server hỗ trợ. Đừng dùng POP3 sequence number làm khóa bền vững.

**“Nếu POP3 không hỗ trợ UIDL thì sao?”**  
Cân nhắc chuyển IMAP/inbound provider hoặc dùng snapshot + fingerprint/heuristic được giám sát. RFC Message-ID không phải sự thay thế hoàn hảo.

**“Webhook event ID có phải Message-ID của email không?”**  
Không nhất thiết. Event ID mô tả event delivery từ provider, provider message ID là ID nội bộ của họ, RFC Message-ID là header bên gửi. Cần lưu riêng theo schema provider.

**“Tại sao trả HTTP 200 sau khi nhận webhook vẫn mất email?”**  
Nếu chưa lưu event vào database/durable queue mà đã trả 200, crash có thể khiến event mất dù provider tin đã nhận thành công. Ack chỉ sau bước tiếp nhận bền vững.

**“At-least-once và idempotent nghĩa là gì?”**  
At-least-once cho phép cùng email được gửi đến handler nhiều lần. Idempotency đảm bảo thực thi lại không tạo thêm side effect ngoài ý muốn, nhờ khóa nghiệp vụ và transaction/remote idempotency key.

**“Claim token bảo đảm chỉ tạo một ticket đúng không?”**  
Không tự nó. Claim token bảo vệ state update của worker, nhưng external side effect có thể chạy hai lần trong cửa sổ lease race. Cần unique business origin hoặc idempotency key cho tác vụ thực.

**“Có nên retry mọi lỗi MIME?”**  
Không. MIME hỏng/attachment độc hại thường không tự trở nên hợp lệ sau vài giây. Cần phân loại, quarantine/FAILED và quy trình điều tra.

**“Sau bao nhiêu lần retry thì nên FAILED?”**  
Không có con số chung. Dựa trên SLA, khả năng nguồn thư còn tồn tại, loại lỗi, business deadline và chi phí. Lưu `max_attempts` và terminal reason rõ ràng.

**“Nếu tạo ticket qua API bên ngoài rồi DB commit lỗi thì sao?”**  
Kết quả side effect có thể mơ hồ. Dùng remote idempotency key, transactional outbox hoặc reconciliation; không gửi lại request mới với key mới mỗi retry.

**“In-Reply-To có thể dùng để xác định ticket không?”**  
Có thể dùng làm tín hiệu tìm ticket ứng viên, kết hợp với `References` hoặc reply token. Nhưng không được bỏ qua kiểm tra tenant/sender authorization vì header có thể giả mạo.

**“Subject Re: Ticket #123 có đủ để gắn comment không?”**  
Không. Subject có thể bị sửa hoặc spoof. Cần correlation đáng tin cậy và kiểm tra quyền trước khi cập nhật ticket.

**“Có nên lưu toàn bộ email gốc trong database?”**  
Tùy nghiệp vụ. Nếu cần replay/audit, có thể lưu encrypted MIME snapshot ở object storage và reference trong DB. Giới hạn kích thước, quyền truy cập, retention và xử lý attachment độc hại.

**“PROCESSED có nghĩa đã xóa mail khỏi server?”**  
Không. Nó có nghĩa handler nghiệp vụ hoàn tất theo định nghĩa của ứng dụng. Cờ SEEN, MOVE hoặc DELETE trên server là những thao tác khác.

**“Tại sao UIDVALIDITY reset làm tăng duplicate count?”**  
Khi thế hệ UID đổi, các bản copy cũ có thể được khám phá lại dưới identity mới. Đây là nguồn mới về mặt kỹ thuật; business deduplication/reconciliation quyết định có cần side effect mới hay không.

**“Metrics inbound nên gắn email address làm label không?”**  
Không. Nó làm bùng nổ số time series và lộ PII. Dùng group/source type/workflow/error category hữu hạn, còn UUID/UID ở log có phân quyền nếu cần.

## 26. Checklist thiết kế lưu message ID và trạng thái

### Định danh nguồn

1. Xác định nguồn nhận: IMAP, POP3 UIDL hay inbound webhook.
2. Với IMAP, dùng composite identity `mailbox_id + folder_key + uid_validity + uid`.
3. Không dùng IMAP message sequence number làm checkpoint.
4. Kiểm tra `UIDVALIDITY` mỗi lần bắt đầu scan và xử lý thay đổi generation.
5. Với POP3, dùng UIDL khi server hỗ trợ; không dùng sequence number.
6. Với webhook, lưu provider ID và event/message ID theo đúng hợp đồng provider.
7. Lưu RFC `Message-ID` dạng nullable, non-unique metadata cho threading/correlation.
8. Không tin Header From, Message-ID, Subject hoặc References như bằng chứng quyền sở hữu.
9. Có internal inbound UUID ổn định để liên kết processing state và audit.

### Discovery và cursor

10. Cursor là tiến độ **phát hiện**, không phải tiến độ xử lý nghiệp vụ.
11. Đọc UID theo upper bound đã quan sát, không nâng cursor vượt `UIDNEXT-1` tùy tiện.
12. Chấp nhận UID gaps khi message đã expunge.
13. Insert inbound rows và advance cursor trong **cùng transaction**.
14. Dùng unique source identity + `ON CONFLICT DO NOTHING`, không reset `PROCESSED` khi quét lại.
15. Nếu nhiều poller, dùng mailbox-level ownership hoặc cursor compare-and-swap.
16. Không phụ thuộc cờ SEEN/UNSEEN để chống xử lý trùng.
17. Nếu cần bảo đảm xử lý sau khi nguồn thay đổi, lưu MIME snapshot bền vững có quota.

### Xử lý và idempotency

18. Định nghĩa rõ `DISCOVERED`, `PROCESSING`, `RETRY`, `PROCESSED`, `FAILED`, `IGNORED` và `QUARANTINED` khi cần.
19. Claim job atomically và tăng `attempt_count` ngay ở ranh giới claim.
20. Dùng lease và claim token/fencing để ngăn stale worker ghi state.
21. Khi side effect nằm cùng DB, commit nó cùng trạng thái `PROCESSED` trong một transaction.
22. Có unique business operation key hoặc origin mapping để không tạo ticket/comment trùng.
23. Với hệ thống bên ngoài, dùng idempotency key hoặc outbox/reconciliation.
24. Retry chỉ khi có khả năng hồi phục; có backoff, jitter và giới hạn số lượt.
25. FAILED/dead letter phải giữ error code, stage, attempt history và thông tin audit.
26. Redrive cần kiểm tra quyền, tính sẵn có của payload và trạng thái side effect trước đó.

### Threading và quyền truy cập

27. Phân biệt Message-ID của email hiện tại với `In-Reply-To`/`References` trỏ thư trước.
28. Dùng References/Message-ID như tín hiệu tìm conversation, không phải authorization.
29. Kiểm tra ticket/tenant/sender permissions trước khi gắn reply.
30. Không match conversation chỉ bằng Subject.
31. Với DSN/bounce, xử lý per-recipient và xác minh source/correlation trước suppression.

### Bảo mật, kiểm thử và vận hành

32. Mailbox credential/OAuth secret đến từ nguồn runtime an toàn.
33. Dùng IMAPS/TLS với hostname verification theo endpoint.
34. Giới hạn kích thước MIME, số part, attachment và parser depth.
35. Quarantine dữ liệu đáng ngờ; không thực thi attachment chưa được xác minh.
36. Không đưa MIME body, password, PII hoặc raw Message-ID vào metric labels.
37. Có retention/encryption/RBAC cho snapshot và audit.
38. Test duplicate header, thiếu header, UID gaps, UIDVALIDITY change, folder move.
39. Test transaction rollback giữa insert records và cursor commit.
40. Test hai worker claim đồng thời, expired lease và stale worker update.
41. Test webhook signature/redelivery và idempotency của side effect.
42. Có metric freshness, backlog age, retry count, failed/quarantine và UIDVALIDITY resets.

## 27. Ví dụ end-to-end: email hỗ trợ được xử lý đúng một lần

Giả sử hệ thống nhận thư tại mailbox `support@example.com` và tạo ticket. Một khách hàng gửi email:

~~~text
From: customer@example.net
To: support@example.com
Subject: Không đăng nhập được
Message-ID: <m-a1@example.net>
~~~

### Bước 1 — Phát hiện

Poller kết nối IMAP:

~~~text
mailbox_id = M1
folder_key = INBOX
UIDVALIDITY = 500
UID = 2201
rfc_message_id = <m-a1@example.net>
~~~

Poller lưu row:

~~~text
inbound_id = D1
source_identity = (M1, INBOX, 500, 2201)
status = DISCOVERED
attempt_count = 0
~~~

Unique constraint bảo đảm nếu poller đọc lại UID 2201 thì vẫn chỉ có một `D1`. Cursor sau khi lưu batch có thể tiến tới UID 2201 hoặc một upper bound đã quét an toàn.

### Bước 2 — Worker claim

Worker A thực hiện atomic claim:

~~~text
inbound_id = D1
status = PROCESSING
attempt_count = 1
claim_token = C1
lease_until = ...
~~~

Attempt history ghi `STARTED`. Worker đọc snapshot hoặc fetch đúng `UID=2201` trong `UIDVALIDITY=500`, parse MIME và validate policy.

### Bước 3 — Tạo ticket

Trong một transaction:

~~~text
ticket_id = T1
support_ticket_origin(D1 -> T1)
inbound_message(D1).status = PROCESSED
processed_at = ...
COMMIT
~~~

Nếu worker crash trước commit, transaction rollback và worker khác có thể retry. Nếu commit thành công nhưng worker crash trước khi gắn cờ SEEN hoặc move email, database vẫn biết `D1` đã xử lý.

### Bước 4 — Poller quét lại

IMAP vẫn chứa UID 2201. Poller cố insert cùng source identity, unique constraint gặp conflict và `DO NOTHING`.

~~~text
Existing D1:
  status = PROCESSED
  ticket_id = T1
No new ticket
~~~

Ngay cả khi thư đã chuyển sang folder khác và được scan lại như một source copy mới, business policy vẫn có thể kiểm tra mapping/correlation để quyết định có phát sinh hành động mới hợp lệ không.

### Bước 5 — Khách hàng gửi reply

Email mới:

~~~text
Message-ID: <m-a2@example.net>
In-Reply-To: <outbound-ticket-T1@mail.example.com>
Subject: Re: Không đăng nhập được
~~~

Đây là **một inbound message mới**, với UID mới và internal ID mới. Handler có thể tìm ticket T1 bằng `In-Reply-To`/mapping từ thư outbound, nhưng chỉ gắn comment sau khi kiểm tra người gửi và quyền truy cập. Không coi reply là bản duplicate của email ban đầu chỉ vì cùng subject.

### Bước 6 — Reconcile sau UIDVALIDITY reset

Vài tuần sau, server restore folder và UIDVALIDITY đổi từ 500 sang 600. Poller bắt đầu generation mới thay vì scan theo cursor cũ. Nếu bản copy của thư D1 xuất hiện dưới UID mới:

- Database có thể lưu **source record mới** để phản ánh IMAP entry thật.
- Không tự tạo ticket T2 nếu business deduplication xác định nó chỉ là bản copy của cùng nghiệp vụ theo bằng chứng được phép.
- Không dựa duy nhất vào `<m-a1@example.net>` để gộp nếu nội dung/nguồn không đáng tin.
- Lưu audit để vận hành biết đã xảy ra UID generation reset.

## 28. Sơ đồ tổng kết

~~~text
               IMAP / POP3 / inbound webhook
                            |
                            v
                Verify connection/source
                            |
                            v
                   Extract source identity
               IMAP: mailbox + folder + validity + UID
               POP3: account + UIDL
               Webhook: provider + event ID
                            |
                            v
                  Durable ingestion transaction
                   - unique source identity
                   - record metadata/snapshot
                   - advance discovery cursor if IMAP
                            |
                            v
                        DISCOVERED
                            |
                            v
                    Atomic worker claim
                     lease + claim token
                            |
                            v
                         PROCESSING
                            |
             +--------------+----------------+
             |              |                |
             v              v                v
        Business OK     Transient error    Terminal error
             |              |                |
             v              v                v
      Commit side effect   RETRY          FAILED/QUARANTINED
      + status PROCESSED      |                |
             |               |                v
             |               +-- due --> Operator / controlled redrive
             |
             v
      Optional IMAP move/flag
             |
             v
      Metrics, audit, correlation, retention
~~~

### Những nguyên tắc cần nhớ

- **RFC Message-ID không phải IMAP UID** và không đủ tin cậy để làm khóa deduplication toàn hệ thống.
- **IMAP UID chỉ có ý nghĩa trong mailbox/folder cùng UIDVALIDITY**.
- **Cursor phát hiện khác trạng thái xử lý**; UID cao được quét xong không chứng minh UID thấp đã hoàn tất nghiệp vụ.
- **Không dùng SEEN/UNSEEN hoặc message sequence number thay database state**.
- **Persist source identity và cursor trong cùng transaction**, tránh crash làm bỏ sót UID.
- **Atomic claim + attempt history + fencing token** giúp xử lý concurrency; **business idempotency** mới chống side effect trùng.
- **In-Reply-To/References hỗ trợ threading**, không thay authorization.
- **Quarantine và retry cần policy riêng**, không nuốt lỗi hoặc retry vô hạn.
- **Có snapshot, retention và kiểm soát dữ liệu** nếu nguồn IMAP có thể mất trước khi worker xử lý.

## Kết luận

**Lưu message ID và trạng thái xử lý** là nền tảng để xây dựng một hệ thống nhận email đáng tin cậy trong ứng dụng dùng Spring Framework Mail. Thay vì coi header `Message-ID` hay cờ `SEEN` là “đã đọc xong”, ứng dụng cần lưu **định danh nguồn đúng phạm vi**, tạo một **ID nội bộ**, ghi **tiến độ discovery** và **trạng thái nghiệp vụ** thành hai lớp độc lập.

Với IMAP, bộ khóa `mailbox + folder + UIDVALIDITY + UID` cùng checkpoint transaction giúp tránh bỏ sót hoặc nhận diện nhầm message. Với webhook, event ID cần được xác minh và deduplicate theo provider; với POP3, UIDL giúp theo dõi qua nhiều phiên khi được hỗ trợ. Cuối cùng, **claim có lease, xử lý idempotent, lưu attempt history và chiến lược retry/dead letter** cho phép hệ thống phục hồi sau crash mà vẫn giữ khả năng giải thích, kiểm toán và bảo vệ dữ liệu khách hàng.
