# Giới hạn lưu giữ theo nghiệp vụ và phạm vi áp dụng của từng hệ

Trong một ứng dụng NoSQL, dữ liệu không tồn tại mãi chỉ vì cơ sở dữ liệu còn đủ dung lượng. Một phiên đăng nhập có thể hết hiệu lực sau 30 phút; giỏ hàng bỏ dở có thể được giữ thêm vài ngày; dữ liệu đo cảm biến có thể chỉ cần ở dạng chi tiết trong một khoảng ngắn nhưng được tổng hợp để phân tích lâu hơn; đơn hàng và chứng từ có thể phải được lưu theo những nghĩa vụ riêng. Ngoài cơ sở dữ liệu chính, cùng một thông tin còn xuất hiện trong **cache, chỉ mục tìm kiếm, bản sao đọc, hàng đợi, log, file xuất, kho phân tích và bản sao lưu**.

Vì vậy, thiết kế **vòng đời dữ liệu** (*data lifecycle*) cần trả lời hai nhóm câu hỏi:

1. **Giới hạn lưu giữ theo nghiệp vụ:** dữ liệu loại nào được giữ bao lâu, tính từ sự kiện nào, có trường hợp ngoại lệ hay không, và khi hết hạn ứng dụng phải làm gì?
2. **Phạm vi áp dụng ở từng hệ:** chính sách đó được thực thi ra sao trong MongoDB, Cassandra, DynamoDB, Redis, hệ tìm kiếm, object storage, event stream, backup và các bản sao dữ liệu khác?

Không thể giải quyết toàn bộ bài toán bằng cách thêm một trường `ttl` vào mọi bản ghi. **Hết hiệu lực nghiệp vụ, không còn hiển thị, bị xóa logic, được xóa khỏi index và được thu hồi vật lý** là những trạng thái khác nhau; mỗi hệ lưu trữ có khả năng và thời điểm thực thi khác nhau.

Bài học này sử dụng ví dụ một nền tảng bán hàng đa tenant để xây dựng chính sách retention, mô hình thời gian, quy trình xóa, cách tránh dữ liệu “hồi sinh” khi replay hoặc khôi phục backup, và cách kiểm tra chính sách đã được áp dụng thực sự.

> **Lưu ý phạm vi:** Các khoảng 30 phút, 7 ngày, 90 ngày, 5 năm trong ví dụ là **giả định thiết kế để học**, không phải thời hạn lưu trữ được luật yêu cầu. Retention thực tế phải được xác định theo nghiệp vụ, hợp đồng, nghĩa vụ áp dụng và chính sách của tổ chức. Cú pháp, TTL, replication và cơ chế xóa có thể khác nhau theo phiên bản/sản phẩm NoSQL.

## 1. Vì sao vòng đời dữ liệu là một phần của schema?

Giả sử mỗi ngày một hệ thống tạo 300.000 bản ghi thao tác. Nếu mỗi bản ghi có dữ liệu logic trung bình 1 KiB, số byte sẽ tăng xấp xỉ:

~~~text
Một ngày  = 300.000 × 1 KiB ≈ 293 MiB
90 ngày   = 27.000.000 × 1 KiB ≈ 25,75 GiB
365 ngày  = 109.500.000 × 1 KiB ≈ 104,43 GiB
~~~

Đây mới là dữ liệu logic, **chưa có bản sao (replica), chỉ mục, tombstone, metadata, log, backup và bản sao phân tích**. Nếu bỏ qua retention, dung lượng và thời gian truy vấn có thể tăng liên tục, trong khi nhiều dữ liệu đã không còn giá trị cho sản phẩm.

Mặt khác, xóa quá sớm cũng nguy hiểm:

- Khách không xem được đơn vừa mua.
- Bộ phận hỗ trợ mất dữ liệu để xử lý khiếu nại.
- Báo cáo bị thiếu số liệu gốc mà chính sách yêu cầu giữ.
- Hệ thống không thể giải thích vì sao một khoản thanh toán hoặc thay đổi trạng thái xảy ra.
- Quá trình đồng bộ vẫn còn sự kiện cũ nhưng không còn dữ liệu chuẩn để xác minh.

Retention không chỉ là tối ưu dung lượng. Nó đồng thời liên quan đến **tính đúng đắn, chi phí, khả năng khôi phục, bảo mật, quyền riêng tư và khả năng kiểm toán**.

### 1.1. Các mốc khác nhau trong vòng đời

~~~mermaid
flowchart LR
    A["Tạo dữ liệu"] --> B["Đang có hiệu lực"]
    B --> C["Hết hiệu lực nghiệp vụ"]
    C --> D["Ngừng phục vụ / ẩn dữ liệu"]
    D --> E["Xóa hoặc chuyển kho theo chính sách"]
    E --> F["Dọn các bản sao và dữ liệu dẫn xuất"]
    F --> G["Xác nhận hoàn tất theo phạm vi"]
~~~

Một số dữ liệu không đi theo đúng chuỗi này: chứng từ có thể chuyển sang **archive** để chỉ được truy cập bởi vai trò nhất định; một yêu cầu xóa hợp lệ có thể rút ngắn vòng đời; hoặc một **legal hold** được phê duyệt có thể tạm dừng khâu xóa theo phạm vi nhất định. Vì thế vòng đời phải được định nghĩa **theo loại dữ liệu và mục đích sử dụng**, không phải một cài đặt toàn cục.

## 2. Phân biệt các khái niệm dễ bị đánh đồng

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| **Business validity** | Dữ liệu/tác vụ còn hợp lệ với nghiệp vụ không? | Token hết quyền dùng sau 30 phút |
| **Retention period** | Cần giữ dữ liệu bao lâu từ mốc xác định? | Giữ event thô 90 ngày từ lúc xảy ra |
| **Visibility** | Ai còn được xem hoặc tìm thấy dữ liệu? | Đơn đã đóng chỉ hiện trong lịch sử |
| **Logical deletion** | Ứng dụng có xem bản ghi như đã bị xóa không? | `deletedAt` hoặc trạng thái `DELETED` |
| **Physical deletion** | Dữ liệu bị loại khỏi lưu trữ vật lý chưa? | Compaction thu hồi tombstone, xóa object |
| **TTL** | Engine dọn/cho hết hạn theo cơ chế nào? | MongoDB TTL index, Cassandra `USING TTL` |
| **Archive** | Dữ liệu được chuyển sang tầng giữ lâu hơn/ít truy cập? | Dữ liệu lịch sử lưu object storage |
| **Backup retention** | Bản sao lưu/snapshot tồn tại bao lâu? | Snapshot tự hết vòng đời sau N ngày |
| **Deletion propagation** | Dữ liệu dẫn xuất và bản sao khác đã nhận yêu cầu xóa chưa? | Search index, cache, read model |
| **Legal hold / preservation hold** | Có ngoại lệ cần giữ dữ liệu không? | Hồ sơ đang được bảo toàn cho một vụ việc được phê duyệt |

Các khái niệm này có liên hệ nhưng **không đồng nghĩa**.

Ví dụ, khi token hết hiệu lực lúc 10:30:00, API phải từ chối token từ mốc ấy. Redis có thể dọn khóa rất sớm hoặc có độ trễ tùy vận hành, nhưng **quyền truy cập không được phụ thuộc duy nhất vào lúc byte vật lý biến mất**.

### 2.1. “Xóa” là một hợp đồng có phạm vi

Khi một API ghi “đã xóa”, cần làm rõ:

- Không còn hiển thị với người dùng thường?
- Không còn được trả từ API trực tiếp?
- Không còn ở read model hoặc công cụ tìm kiếm?
- Không còn được cấp quyền qua cache, token hay liên kết chia sẻ?
- Đã gửi yêu cầu xóa tới các hệ downstream?
- Đã xóa khỏi storage chính?
- Dữ liệu còn trong backup theo chu kỳ bảo toàn đã công bố hay không?

Một trạng thái `DELETE_REQUESTED` không giống `DELETION_COMPLETED`. Nếu quy trình gồm nhiều hệ thống, trạng thái hoàn tất phải có **tiêu chí đo lường rõ**.

## 3. Ví dụ: các loại dữ liệu của nền tảng bán hàng

Giả sử hệ thống có những loại dữ liệu sau:

| Loại dữ liệu | Mục đích | Mốc bắt đầu giữ (*anchor*) | Chính sách minh họa |
| --- | --- | --- | --- |
| **Session đăng nhập** | Cho phép truy cập trong phiên | `issuedAt` hoặc `lastActivityAt` theo hợp đồng | Hết quyền sau 30 phút không hoạt động |
| **Giỏ hàng bỏ dở** | Giúp khách quay lại mua | `lastUpdatedAt` | Dọn sau 7 ngày không cập nhật |
| **Event thao tác thô** | Phân tích hành vi | `occurredAt` đã chuẩn hóa và kiểm soát | Giữ 90 ngày |
| **Đơn hàng** | Lịch sử giao dịch và phục vụ hỗ trợ | `completedAt` hoặc mốc có nghĩa theo chính sách | Ví dụ 5 năm nếu chính sách đã phê duyệt |
| **Nhật ký hệ thống kỹ thuật** | Gỡ lỗi vận hành | `ingestedAt` hoặc ngày tạo log | Ví dụ 14 ngày ở tầng tra cứu nóng |
| **Chỉ số thống kê theo ngày** | Báo cáo xu hướng | `reportDate` | Ví dụ 18 tháng, nếu không chứa dữ liệu nhạy cảm không cần thiết |
| **Bản sao cache danh mục** | Giảm tải đọc Catalog | Lúc làm mới cache | TTL ngắn theo yêu cầu freshness |
| **Tài liệu hỗ trợ** | Xử lý yêu cầu hỗ trợ | `caseClosedAt` | Theo chính sách hỗ trợ và nghĩa vụ áp dụng |

Các cột “giữ 90 ngày” hoặc “giữ 5 năm” chỉ là **đề xuất bài tập**, không được triển khai vào sản phẩm thật trước khi được owner nghiệp vụ và các bên chịu trách nhiệm chính sách chấp thuận.

### 3.1. Không được đặt một TTL chung cho tất cả bảng

Nếu áp dụng TTL 90 ngày cho mọi record:

- Session có thể còn tồn tại lâu hơn thời hạn truy cập 30 phút.
- Đơn hàng có thể mất sớm hơn nghĩa vụ hỗ trợ hoặc lưu trữ.
- Log kỹ thuật tồn tại lâu hơn mức cần thiết.
- Bảng tổng hợp có thể bị xóa không đúng lịch báo cáo.

Giải pháp là một **danh mục lớp dữ liệu (*data classification and retention catalog*)** gắn với mục đích, chủ sở hữu, mốc thời gian và các hệ đang giữ bản sao.

### 3.2. Một dữ kiện xuất hiện ở nhiều hệ

Ví dụ trạng thái đơn O900 có thể có mặt ở:

~~~text
Orders (nguồn chuẩn)
  ├── Customer order history (read model)
  ├── Shop dashboard (read model)
  ├── Search index
  ├── Redis cache
  ├── Event stream / CDC
  ├── Analytics warehouse
  ├── Log/tracing có chứa orderId
  └── Backup/snapshot của các hệ trên
~~~

**Xóa một bản ghi trong Orders không bảo đảm các bản sao còn lại tự biến mất.** Mỗi đường phát tán dữ liệu phải có quy tắc retention hoặc deletion propagation tương ứng.

## 4. Xác định chính xác mốc bắt đầu tính thời hạn

Một chính sách “giữ 90 ngày” vẫn chưa đủ nếu không nói **90 ngày từ khi nào**.

Trong hệ thống phân tán có nhiều timestamp:

| Trường | Do ai ghi nhận? | Có thể dùng cho retention nào? |
| --- | --- | --- |
| `occurredAt` | Nguồn sự kiện/client/thiết bị | Giữ event theo lúc quan sát, có kiểm tra clock |
| `receivedAt` | API hoặc ingress server | Giữ theo lúc hệ thống tiếp nhận |
| `createdAt` | Dịch vụ sở hữu bản ghi hoặc DB | Giữ từ lúc bản ghi được tạo |
| `lastActivityAt` | Dịch vụ xác thực/giỏ hàng | Sliding expiration theo hoạt động hợp lệ |
| `completedAt` | Workflow xác nhận đơn đã hoàn tất | Bắt đầu lưu giữ sau hoàn tất |
| `closedAt` | Dịch vụ hỗ trợ xác nhận đóng vụ việc | Retention sau đóng case |
| `issuedAt` | Dịch vụ phát hành chứng từ/token | Tính thời hạn từ lúc phát hành |
| `expiresAt` | Được tính theo chính sách | Deadline tuyệt đối để kiểm tra hoặc dọn |
| `deletedAt` | Dịch vụ có thẩm quyền thực hiện/xác nhận xóa | Audit trạng thái xóa, không tự thay thế ngày hết hạn |

### 4.1. Event time so với ingest time

Thiết bị gửi một event:

~~~text
occurredAt = 2026-08-01T09:00:00Z
receivedAt = 2026-08-20T10:00:00Z
~~~

Nếu retention là “90 ngày từ `occurredAt`”, deadline phải được tính từ **01/08**, không phải **20/08**. Nếu dùng TTL 90 ngày ngay tại lúc insert 20/08, dữ liệu tồn tại vật lý lâu hơn định nghĩa nghiệp vụ khoảng 19 ngày.

Ngược lại, nếu chính sách là “90 ngày kể từ khi hệ thống nhận được event”, `receivedAt` mới là mốc đúng. Hai cách đều có thể hợp lý, nhưng **không được đánh tráo**.

### 4.2. Client time có thể sai

Đồng hồ thiết bị có thể chạy sớm hoặc muộn; một actor không đáng tin có thể gửi `occurredAt` hàng chục năm trước để khiến event bị dọn ngay, hoặc gửi timestamp tương lai để kéo dài lưu trữ.

Một chiến lược có thể:

1. Giữ nguyên timestamp nguồn trong phạm vi cho phép để phục vụ lịch sử.
2. Ghi `receivedAt` từ server đáng tin cậy.
3. Kiểm tra độ lệch giữa hai mốc theo quy tắc từng loại sự kiện.
4. Gắn cờ những event có clock bất thường.
5. Xác định rõ với trường hợp bất thường, **anchor retention nào có thẩm quyền**.

Không nên tự động lấy mọi `occurredAt` do client gửi làm mốc quyết định xóa dữ liệu quan trọng mà không kiểm tra.

### 4.3. Retention tuyệt đối và sliding expiration

**Thời hạn tuyệt đối:**

~~~text
issuedAt   = 10:00
expiresAt  = 10:30
Hoạt động lúc 10:20 không làm thay đổi expiresAt.
~~~

**Thời hạn trượt theo hoạt động:**

~~~text
lastActivityAt = 10:00 -> expiresAt = 10:30
Hoạt động hợp lệ lúc 10:20 -> expiresAt = 10:50
~~~

Khi dùng sliding expiration, phải cập nhật deadline ở nguồn chính sách và cơ chế TTL/cache tương ứng. Đồng thời có thể đặt **hạn tuyệt đối tối đa**, chẳng hạn không cho phiên kéo dài vô hạn dù liên tục hoạt động.

Một hợp đồng có thể quy định:

\[
\text{expiresAt} =
\min(\text{lastActivityAt} + 30\ \text{phút},
     \text{issuedAt} + 12\ \text{giờ})
\]

Đây là ví dụ nghiệp vụ, không phải thời hạn mặc định của hệ xác thực.

## 5. Duration, ngày lịch và múi giờ

“Giữ 30 ngày” có thể có hai cách hiểu:

1. **30 × 24 giờ** tính từ một instant.
2. **Đến hết ngày lịch thứ 30** theo múi giờ được chỉ định.

Hai cách không hoàn toàn giống nhau, nhất là ở vùng có **daylight saving time (DST)**.

### 5.1. Thời hạn theo số giây

Ví dụ session sống chính xác 30 phút:

\[
\text{expiresAt} = \text{issuedAt} + 1800\ \text{giây}
\]

Với yêu cầu tính bằng khoảng thời gian tuyệt đối như vậy, dùng instant UTC và `Duration` là phù hợp.

### 5.2. Thời hạn theo lịch

Ví dụ “giữ đến hết ngày 31/12 theo giờ của đơn vị nghiệp vụ”. Khi đó phải biết **IANA time zone** của đơn vị, tính ranh giới ngày tiếp theo theo timezone đó, rồi chuyển sang instant.

~~~text
retentionEndLocalDate = 2027-12-31
zone = Asia/Ho_Chi_Minh

deadline = đầu ngày 2028-01-01 tại Asia/Ho_Chi_Minh
           chuyển sang UTC instant
~~~

Không nên lấy UTC midnight nếu nghiệp vụ nói về ngày của cửa hàng ở một múi giờ khác.

### 5.3. Dùng khoảng [from, to)

Để đọc hoặc xác định dữ liệu đã hết hạn, nên dùng khoảng **bao gồm mốc đầu và không bao gồm mốc cuối**:

~~~text
createdAt >= from
AND createdAt < to
~~~

Điều này tránh phải đoán “mili giây cuối cùng của ngày” trên những hệ có độ chính xác khác nhau. Một event có timestamp đúng bằng `to` thuộc khoảng tiếp theo.

## 6. Viết chính sách retention thành một hợp đồng

Một chính sách cần đủ thông tin để triển khai và kiểm tra, thay vì ghi chung “giữ một thời gian hợp lý”.

Ví dụ YAML **minh họa**, không phải cấu hình mặc định của bất kỳ database nào:

~~~yaml
policyId: raw-events-v1
dataClass: EVENT_RAW
businessOwner: analytics-team
systemOwner: data-platform-team
retention:
  anchorField: occurredAt
  duration: P90D
  timezone: UTC
  policyVersion: 1
access:
  visibleAfterExpiry: false
  allowedPurposes:
    - operational-analytics
deletion:
  source: events_primary
  derived:
    - events_search
    - events_data_lake_raw
    - events_cache
  streamHandling: replay-with-expiry-gate
  backupHandling: expiry-and-restore-reconciliation
exceptions:
  allowed: true
  approvalRequired: true
  auditRequired: true
observability:
  measureExpiredReadableRecords: true
  measureDeletionLag: true
~~~

`P90D` là ký hiệu ISO-8601 duration theo ngày được dùng để minh họa chính sách. Khi triển khai phải quyết định dùng **90 ngày lịch** hay **90 × 24 giờ**, đặc biệt nếu một ngày được diễn giải theo timezone có DST.

### 6.1. Các trường tối thiểu cần có

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `policyId/version` | Xác định phiên bản chính sách đã được áp dụng |
| `dataClass` | Loại dữ liệu hoặc bản ghi mà chính sách quản lý |
| `businessOwner` | Ai có quyền quyết định mục đích và thời hạn |
| `systemOwner` | Ai triển khai, vận hành, kiểm tra |
| `anchor` | Thời điểm bắt đầu tính thời hạn |
| `duration/deadline` | Bao lâu hoặc chính xác đến lúc nào |
| `scope` | Những database, index, cache, file, log, backup và downstream liên quan |
| `action` | Ẩn, hết quyền, xóa, chuyển archive, tổng hợp hoặc hủy định danh |
| `exception/hold` | Ai có quyền trì hoãn xóa, trong phạm vi nào |
| `evidence` | Cách chứng minh mỗi hệ đã áp dụng chính sách |

### 6.2. Không phải mọi dữ liệu dẫn xuất đều còn định danh

Một bảng thống kê chỉ chứa số lượng giao dịch theo ngày có thể có chính sách khác dữ liệu đơn hàng cá nhân. Nhưng **gộp số liệu không tự động có nghĩa đã ẩn danh hoàn toàn**: nhóm quá nhỏ, khóa có thể liên kết lại hoặc thông tin đặc thù có thể khiến người dùng vẫn nhận diện được.

Trước khi cho phép giữ dữ liệu tổng hợp lâu hơn, cần xác định nó có còn chứa thông tin cần bảo vệ hoặc có thể liên kết tới cá nhân hay không.

## 7. Phân loại các hệ và phạm vi thực thi

Một chính sách retention cần đi theo **đường di chuyển của dữ liệu** từ nguồn tới mọi hệ đích.

~~~mermaid
flowchart TD
    A["Nguồn chuẩn / Primary DB"] --> B["Read model / Projection"]
    A --> C["Search index"]
    A --> D["Redis cache"]
    A --> E["CDC / Event stream"]
    E --> F["Analytics / Data lake"]
    E --> G["DLQ / Replay store"]
    A --> H["Backup / Snapshot"]
    B --> I["Backup projection"]
    C --> J["Snapshot search"]
    F --> K["Export / Report"]
~~~

Một danh mục phạm vi có thể chia như sau:

| Hệ hoặc vị trí | Chức năng | Phải làm gì khi dữ liệu hết hạn? |
| --- | --- | --- |
| Primary DB | Nguồn dữ liệu chuẩn | Ngừng phục vụ theo quy tắc; xóa/archive khi đủ điều kiện |
| Replica | Bản sao phục vụ đọc/chịu lỗi | Đảm bảo mutation hoặc TTL lan theo cơ chế replication |
| Read model | Bảng theo truy vấn | Xóa/chỉnh bản chiếu; ngăn event cũ tạo lại |
| Cache | Giảm độ trễ | TTL/invalidation; không coi cache miss là xóa nguồn |
| Search/vector index | Tìm kiếm | Xóa nội dung và metadata; kiểm tra kết quả tìm không lộ |
| Event stream / CDC | Phân phối thay đổi | Retention log, quyền truy cập, replay gate |
| DLQ / retry storage | Lưu event lỗi để xử lý lại | Giới hạn vòng đời; kiểm tra trước replay |
| Data lake/analytics | Tổng hợp và phân tích | Expiration, partition/object deletion, xử lý bản dẫn xuất |
| Log/trace/APM | Chẩn đoán hệ thống | Tránh log payload nhạy cảm; retention riêng |
| Object storage | File, ảnh, export, archive | Lifecycle, delete marker/versioning, bản copy vùng khác |
| Backup/snapshot | Khôi phục khi sự cố | Chu kỳ bảo toàn, quyền hạn, restore-safe deletion |
| Thiết bị offline | Dữ liệu được đồng bộ sau | Chính sách client storage, xóa/sync nếu có thể |

### 7.1. Trọng tâm: nguồn chuẩn không đồng nghĩa chỉ có một bản vật lý

Một Order có thể có **nguồn nghiệp vụ duy nhất** ở Orders service, nhưng tồn tại ở nhiều replica của Cassandra hoặc MongoDB. Replica **không phải nguồn nghiệp vụ độc lập**, song bản sao vật lý vẫn phải thuộc phạm vi thực thi retention.

Nếu bản chiếu Customer History giữ một số trường của Order, nó cũng có retention và cơ chế xóa; không được viện lý do “đây chỉ là cache” để bỏ qua dữ liệu đang được người dùng truy cập.

### 7.2. Xóa trong một hệ không bảo đảm xóa hệ khác

Ví dụ:

~~~text
Order O900 được đánh dấu DELETED trong source.
Search index vẫn chứa O900 trong 20 phút.
Redis cache còn title/tổng tiền của O900.
Event stream vẫn giữ event cũ.
Một worker replay event cũ và ghi lại O900 vào search index.
~~~

Nếu API query source đã chặn, nhưng công cụ tìm kiếm vẫn trả thông tin, chính sách chưa được thực thi đầy đủ. **Phạm vi áp dụng phải bao gồm cả đường truy cập gián tiếp và cơ chế hồi sinh dữ liệu**.

## 8. TTL của NoSQL chỉ là một cơ chế thực thi

TTL (*time to live*) là khả năng đánh dấu hoặc xóa dữ liệu khi đủ tuổi theo cơ chế của hệ lưu trữ. TTL rất hữu ích cho dữ liệu có vòng đời đơn giản, nhưng có những giới hạn:

- Có hệ tính TTL từ **thời điểm ghi**, không phải `occurredAt` nghiệp vụ.
- Có hệ cần trường **deadline tuyệt đối**.
- Cleanup có thể diễn ra **bất đồng bộ**.
- Dữ liệu có thể tiếp tục tồn tại trong backup/snapshot.
- TTL không tự xóa file export, cache khác hay log.
- TTL và lệnh cập nhật có thể tương tác: ghi mới có thể thay đổi hoặc bỏ trạng thái hết hạn.
- Một chính sách có **ngoại lệ/legal hold** thường không thể triển khai an toàn chỉ bằng TTL cứng trên mọi hàng.

| Câu hỏi | TTL tự giải quyết được không? |
| --- | --- |
| Xóa record thử nghiệm sau 7 ngày từ lúc ghi | Có thể rất phù hợp |
| Không cho dùng session từ đúng deadline | **Không đủ**; API phải kiểm tra hạn |
| Giữ 5 năm từ lúc đơn hoàn tất | Phải tính anchor đúng; có thể cần workflow riêng |
| Không xóa đơn đang có hold | Cần cơ chế ngoại lệ và kiểm soát quyền |
| Xóa cùng một dữ kiện ở 7 hệ downstream | Không; cần orchestration/propagation |
| Ngăn replay event cũ tái tạo dữ liệu đã xóa | Không; cần version/tombstone và expiry gate |
| Bảo đảm dữ liệu không còn trong bản backup cũ | Không; cần retention/restore policy |

Các mục tiếp theo minh họa những cơ chế TTL khác nhau.

## 9. MongoDB: TTL index theo deadline

MongoDB có kiểu BSON `Date` (mili giây từ Unix epoch) và hỗ trợ **TTL index** để xóa document khi hết hạn theo chính sách index. TTL monitor chạy nền; xóa có thể trễ so với thời điểm được định nghĩa.

### 9.1. Session có deadline tuyệt đối

Ví dụ một collection session:

~~~javascript
db.sessions.insertOne({
  _id: "sess-123",
  tenantId: "merchant-a",
  userId: "U42",
  issuedAt: ISODate("2026-11-14T09:00:00Z"),
  expiresAt: ISODate("2026-11-14T09:30:00Z")
});

db.sessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
~~~

`expireAfterSeconds: 0` có nghĩa thời điểm hết hạn được lấy từ **giá trị `expiresAt` của từng document**. Đây là cách trực tiếp để lưu những session có thời hạn không giống nhau.

Vì cleanup không bảo đảm chạy đúng ở từng mili giây, ứng dụng xác thực vẫn cần:

~~~text
IF session không tồn tại OR now >= session.expiresAt:
    từ chối phiên
ELSE:
    tiếp tục các kiểm tra quyền khác
~~~

Không thể sử dụng `findOne` trả document còn tồn tại làm bằng chứng phiên vẫn hợp lệ.

### 9.2. TTL tính theo ngày tạo

Nếu toàn bộ log kỹ thuật chỉ giữ trong **14 × 24 giờ từ lúc ghi**, có thể tạo index trên `createdAt` với khoảng giây:

~~~javascript
db.technicalLogs.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 1209600 }
);
~~~

`1209600 = 14 × 24 × 3600`. Nếu một log có `createdAt` trong quá khứ, thời hạn sẽ tính từ giá trị trường chứ không mặc định từ lúc tạo index.

Khi yêu cầu là **ngày lịch theo timezone nghiệp vụ**, tốt hơn nên tính một `expiresAt` chính xác ở tầng sở hữu chính sách rồi dùng TTL theo deadline, thay vì áp số giây có thể sai với ranh giới lịch.

### 9.3. Những điều TTL index không làm thay

- Không tự xóa document đã được export sang object storage.
- Không tự sửa bản cache hoặc hệ tìm kiếm do ứng dụng quản lý.
- Không tự biết một document có legal hold hay không nếu thiết kế TTL không xét được ngoại lệ.
- Không bảo đảm mọi backup trước đó không còn chứa document.
- Không cung cấp bảo đảm “document biến mất vật lý chính xác tại `expiresAt`”.

Nếu một loại bản ghi có yêu cầu bảo toàn ngoại lệ, cần **đường lưu trữ hoặc quy trình xóa có xét hold**, thay vì gắn TTL không phân biệt rồi hy vọng hold được tôn trọng.

## 10. Cassandra: TTL, tombstone và compaction

Trong Cassandra, TTL có thể được đặt cho dữ liệu khi ghi bằng CQL. Đây là kỹ thuật hợp lý với dữ liệu sự kiện có vòng đời tương đối đồng nhất, nhưng **TTL về bản chất gắn với thời điểm ghi**, không biết mốc nghiệp vụ trong một cột `occurred_at`.

### 10.1. Bảng event theo ngày

~~~sql
CREATE TABLE raw_events_by_tenant_day (
    tenant_id text,
    day_utc date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY (
        (tenant_id, day_utc),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

`day_utc` là bucket được tính từ `occurred_at` theo UTC. Query đọc một ngày cần cung cấp đủ partition key. Nếu dữ liệu đi qua nhiều ngày, ứng dụng phải truy vấn nhiều partition rồi tổng hợp.

### 10.2. TTL 90 ngày từ lúc ghi

~~~sql
INSERT INTO raw_events_by_tenant_day (
    tenant_id, day_utc, occurred_at,
    event_id, event_type, payload
) VALUES (
    'merchant-a',
    '2026-11-14',
    '2026-11-14T09:00:00Z',
    85c1bdc5-9367-4648-a283-408cfc74e5db,
    'ORDER_VIEWED',
    '{"orderId":"O900"}'
) USING TTL 7776000;
~~~

`7776000 = 90 × 24 × 3600` giây. Theo cơ chế TTL, dữ liệu sẽ hết hạn tương đối với thời điểm ghi, **không tự tính từ `occurred_at`**.

Nếu chính sách nghiệp vụ yêu cầu giữ tới:

\[
\text{deadline} = \text{occurredAt} + 90\ \text{ngày}
\]

thì ứng dụng có thể tính **TTL còn lại tại thời điểm ghi**, hoặc thực hiện một quy trình dọn theo deadline. Cần đặc biệt xử lý event đến muộn và khoảng TTL đã hết trước khi ghi.

Ví dụ:

~~~text
occurredAt   = 2026-08-01T09:00:00Z
receivedAt   = 2026-10-29T09:00:00Z
deadline     = 2026-10-30T09:00:00Z

TTL còn lại tại lúc ghi ≈ 1 ngày,
không phải 90 ngày.
~~~

Nếu deadline đã qua, chính sách có thể **không ghi raw event vào kho nóng**, thay vì ghi rồi gắn TTL 0 tùy ngữ nghĩa engine. Việc có giữ sự kiện trong kho khác để điều tra phải được quy định riêng.

### 10.3. Tombstone không biến mất ngay

Khi dữ liệu Cassandra hết TTL hoặc bị xóa, hệ thống có thể tạo/duy trì **tombstone** để đảm bảo các replica và quá trình đọc biết dữ liệu đã bị loại bỏ. Việc thu hồi vật lý phụ thuộc **compaction, điều kiện an toàn và lịch repair**.

Hệ quả:

- TTL không có nghĩa byte vật lý biến mất ngay khi đến hạn.
- Đọc một partition có nhiều dữ liệu hết hạn có thể phải xét nhiều tombstone.
- Một truy vấn `LIMIT 20` vẫn có thể tốn tài nguyên nếu phải đi qua nhiều dấu xóa để tìm 20 hàng sống.
- Xóa lượng lớn trong partition có thể gây áp lực I/O và compaction.

**Không tùy tiện hạ `gc_grace_seconds` chỉ để dọn nhanh hơn.** Khi dữ liệu phân tán giữa các replica, việc thu hồi tombstone quá sớm khi replica chưa được đồng bộ có thể làm dữ liệu cũ xuất hiện lại. Quyết định liên quan cần xét chiến lược repair và đặc tính triển khai thực tế.

### 10.4. TTL trên cập nhật dữ liệu

Trong Cassandra, TTL liên quan tới giá trị được ghi và quy tắc cell-level; một `UPDATE` có thể làm thay đổi TTL của các cột được cập nhật. Không nên giả định một hàng có cùng deadline vĩnh viễn sau mọi lần ghi.

Với chính sách “giữ 90 ngày từ khi event xảy ra”, cần kiểm tra tất cả đường ghi/cập nhật cùng áp **deadline thống nhất**, tránh một lần cập nhật payload vô tình kéo dài vòng đời dữ liệu.

### 10.5. Time-window compaction và dữ liệu theo thời gian

Các bảng event ghi chủ yếu theo thời gian với TTL gần tương đồng có thể phù hợp với chiến lược compaction dành cho time-series như **TimeWindowCompactionStrategy** trong những triển khai Cassandra tương ứng.

Tuy nhiên cần xét:

- Sự kiện đến muộn có ghi vào khoảng thời gian cũ hay không.
- Có nhiều TTL khác nhau trong một bảng không.
- Có cập nhật/xóa nhiều hàng cũ không.
- Khoảng ghi có tạo SSTable với dữ liệu hết hạn không đồng nhất không.

Không phải cứ có `occurredAt` và TTL là TWCS tự tối ưu hoàn hảo. Cần đo tombstone, SSTable, read latency và compaction trên workload thực.

## 11. DynamoDB: TTL bằng epoch seconds

DynamoDB hỗ trợ cơ chế TTL dựa trên một thuộc tính Number chứa **Unix epoch timestamp tính bằng giây**, được cấu hình cho bảng.

Ví dụ một item:

~~~json
{
  "PK": "SESSION#sess-123",
  "SK": "META",
  "tenantId": "merchant-a",
  "userId": "U42",
  "expiresAtEpochSeconds": 1794648600
}
~~~

Giá trị epoch trên chỉ mang tính minh họa định dạng. Khi triển khai phải tính từ instant thật và **không nhầm seconds với milliseconds**.

Trong Java:

~~~java
long expiresAtEpochSeconds = expiresAtInstant.getEpochSecond();
~~~

### 11.1. Dữ liệu hết hạn vẫn có thể được đọc trước khi được dọn

DynamoDB xử lý xóa item TTL theo cơ chế **bất đồng bộ**, không có bảo đảm item biến mất đúng khoảnh khắc deadline. Query có thể vẫn thấy item đã quá hạn cho tới khi cơ chế xóa hoàn thành.

Với session:

~~~text
Đọc item bằng PK/SK
    -> nếu không tồn tại: từ chối
    -> nếu now >= expiresAtEpochSeconds: từ chối
    -> nếu còn hạn: tiếp tục kiểm tra quyền
~~~

Nếu dùng filter expression để loại item quá hạn, lưu ý DynamoDB có thể đọc/tiêu tốn tài nguyên trước khi áp dụng filter; filter không tự làm một access path rộng trở nên rẻ.

### 11.2. TTL và chỉ mục phụ

Item có thể đồng thời có mặt qua các Global Secondary Index. Khi item ở bảng nguồn bị xóa theo TTL, các chỉ mục được cập nhật theo cơ chế hệ thống, song **việc TTL cleanup chưa chạy** vẫn có nghĩa item tồn tại và có thể được truy vấn.

Không dùng sự hiện diện/biến mất của item trong GSI làm quy tắc quyền truy cập duy nhất. Đồng thời phải tính đến việc index, replica/cross-region và luồng sự kiện có độ trễ riêng.

### 11.3. TTL không áp dụng cho mọi data store liên kết

Nếu một item DynamoDB được đưa qua stream sang OpenSearch hoặc kho phân tích, TTL của bảng **không tự áp trực tiếp** lên document đã xuất sang hệ khác. Consumer phải hiểu các event xóa, hoặc cần một job reconciliation/expiry riêng.

Nếu event cũ được replay, consumer phải kiểm tra retention hiện tại trước khi tái tạo document trong read model.

## 12. Redis: vòng đời ngắn và TTL tương đối

Redis thường được dùng cho session, cache, rate-limit state và những dữ liệu tạm. Vì thế TTL là công cụ phổ biến, nhưng cũng không nên đánh đồng Redis với nguồn chuẩn cho mọi nghiệp vụ.

### 12.1. Hết hạn sau một khoảng thời gian

~~~text
SET session:sess-123 active EX 1800
TTL session:sess-123
PTTL session:sess-123
~~~

`EX 1800` là thời gian sống 1.800 giây (30 phút) tính từ khi Redis áp dụng lệnh. `TTL` cho số giây còn lại, `PTTL` cho mili giây.

### 12.2. Deadline tuyệt đối

Redis cũng hỗ trợ thiết lập thời điểm hết hạn tuyệt đối bằng các lệnh và tùy chọn phù hợp:

~~~text
SET session:sess-123 active EXAT 1794648600
~~~

`EXAT` dùng **Unix epoch seconds**; có dạng tương ứng theo mili giây. Khi dùng deadline tuyệt đối, cần tính mốc từ nguồn nghiệp vụ đáng tin cậy, không lấy một con số client gửi tự do cho token an ninh.

### 12.3. Cập nhật có thể ảnh hưởng TTL

Một lần ghi đè giá trị bằng `SET` không kèm tùy chọn giữ TTL có thể làm thay đổi trạng thái hết hạn của key. Ví dụ service cập nhật nội dung cache nhưng quên duy trì deadline, key có thể tồn tại lâu hơn chính sách dự kiến.

Với sliding session, ứng dụng phải chủ động tính và cập nhật deadline; với absolute session, không được vô tình gia hạn hạn tối đa khi mỗi request tới.

### 12.4. Eviction không phải expiration

Redis có thể được cấu hình chính sách **eviction** khi thiếu bộ nhớ. Một key cache có thể bị đẩy ra **trước** TTL. Ngược lại, một token hết hạn về nghiệp vụ vẫn phải bị chặn ở lớp xác thực dù cơ chế xóa/keyspace xử lý theo lịch riêng.

Vì vậy:

- **Cache miss** không có nghĩa dữ kiện nghiệp vụ chưa từng tồn tại.
- **Cache hit** không đủ chứng minh quyền còn hiệu lực.
- Không dùng Redis cache duy nhất để lưu chứng cứ giao dịch cần lưu lâu dài.

## 13. Hệ tìm kiếm và chỉ mục vector: retention của bản chiếu

Một nền tảng có thể đưa mô tả đơn hàng, sản phẩm hoặc bài viết vào **search index** để tìm kiếm văn bản hoặc embedding vector. Dữ liệu trong index là **dữ liệu dẫn xuất**, nhưng vẫn có thể chứa thông tin nhạy cảm.

### 13.1. Xóa source không tự thu hồi kết quả tìm kiếm

Giả sử nguồn xóa tài liệu `doc-101`:

~~~text
Primary database: doc-101 = DELETED
Search index:      doc-101 vẫn được tìm thấy
Vector index:      embedding của doc-101 còn tồn tại
Cache search:      kết quả cũ vẫn được lưu
~~~

Để hoàn tất chính sách, pipeline phải thực hiện **delete/upsert theo trạng thái mới**, rồi kiểm tra document không còn được trả qua các API có quyền truy cập tương ứng.

Nếu index có quá trình refresh hoặc merge bất đồng bộ, việc xóa logic khỏi kết quả truy vấn và thu hồi byte vật lý có thể khác thời điểm.

### 13.2. Retention theo index/time bucket

Những hệ tìm kiếm như Elasticsearch/OpenSearch thường có cơ chế quản lý vòng đời index hoặc chính sách rollover/xóa index theo tuổi, dung lượng hay điều kiện vận hành.

Ví dụ:

~~~text
events-2026-11-12
events-2026-11-13
events-2026-11-14
~~~

Nếu mọi dữ liệu trong một index có cùng thời hạn và cùng anchor, **xóa nguyên index theo bucket** có thể đơn giản hơn xóa từng document. Tuy nhiên:

- Tuổi index không nhất thiết bằng tuổi từng event bên trong.
- Event đến muộn có thể được ghi vào index mới nhưng `occurredAt` cũ.
- Một index có nhiều loại dữ liệu với TTL khác nhau không phù hợp để xóa đồng loạt.
- Snapshot index, bản sao hoặc file export cần retention riêng.

**Quy tắc quản lý index không tự bảo đảm retention theo từng document**, trừ khi cách bucket và các mốc thời gian thực sự được thiết kế tương thích.

### 13.3. Embedding cũng là dữ liệu phải kiểm soát

Ngay cả khi đã xóa đoạn văn bản gốc, embedding, metadata, ID liên kết hoặc index ANN có thể vẫn phản ánh thông tin cần bảo vệ. Không nên giả định vector embedding tự động là dữ liệu ẩn danh.

Khi xóa nguồn cần xét:

- Bản vector gốc.
- ID và metadata trong vector store.
- Các bản sao/shard/replica.
- Cache kết quả tìm kiếm.
- Bản snapshot phục vụ rebuild.
- Pipeline reindex có thể đưa tài liệu đã xóa trở lại.

## 14. Object storage, data lake và file xuất

Rất nhiều hệ NoSQL có pipeline xuất dữ liệu sang file JSON/Parquet/CSV hoặc object storage để phân tích. **TTL trong database gốc không chạy trên các file đã xuất**.

### 14.1. Retention theo file hoặc partition

Một data lake có cấu trúc:

~~~text
s3://example-analytics/events/day=2026-11-12/part-000.parquet
s3://example-analytics/events/day=2026-11-13/part-001.parquet
...
~~~

Nếu mọi hàng trong file thuộc cùng lớp retention và ngày dữ liệu, lifecycle theo partition/object có thể đơn giản. Nhưng nếu file trộn dữ liệu nhiều ngày hoặc có dữ liệu nhiều tenant với chính sách khác nhau, xóa cả file có thể:

- Xóa sớm dữ liệu vẫn phải giữ.
- Hoặc giữ quá lâu một số hàng đã hết hạn.

Khi đó cần thiết kế **partitioning theo retention class, data rewrite hoặc record-level deletion** phù hợp với định dạng bảng/data lake.

### 14.2. Object versioning và delete marker

Ở object storage có bật versioning, xóa object thường có thể chỉ tạo một **delete marker** hoặc thay đổi phiên bản hiện hành. Các phiên bản cũ có thể còn tồn tại và được người có quyền truy cập vào lịch sử phiên bản khôi phục.

Chính sách phải xem:

- Current versions.
- Noncurrent versions.
- Replication sang vùng/bucket khác.
- Snapshot và backup.
- Bản xuất được lưu ở đường dẫn khác.

Không được tuyên bố “đã xóa vật lý” chỉ vì lệnh delete trên key hiện hành thành công.

### 14.3. Archive là thay đổi quyền truy cập, không phải miễn retention

Đưa một Order sang kho archive giúp giảm tải truy vấn nóng, nhưng dữ liệu archive vẫn cần:

- Mục đích giữ hợp lệ.
- Thời hạn và mốc hết hạn.
- Phân quyền chặt hơn nếu cần.
- Khả năng tra cứu đúng phạm vi.
- Cơ chế xóa/khôi phục theo chính sách.

Một chính sách chuyển sang archive sau 1 năm và xóa sau 5 năm là **hai mốc riêng**, không phải “archive nên được giữ mãi”.

## 15. Log, metrics, tracing, queue và dead-letter queue

Những hệ thống phục vụ vận hành rất dễ trở thành **bản sao ngoài ý muốn** của dữ liệu nghiệp vụ.

### 15.1. Log không nên chứa toàn bộ payload nhạy cảm

Ví dụ log:

~~~text
INFO order_request tenant=merchant-a orderId=O900 status=PAID
~~~

thường ít rủi ro hơn việc log nguyên request có số điện thoại, địa chỉ, token hoặc nội dung thanh toán. Nhưng ngay cả `orderId` và `tenantId` cũng có thể là thông tin phải bảo vệ tùy bối cảnh.

Chính sách log nên bao gồm:

- Những trường được phép ghi.
- Redaction/masking tại nguồn.
- Retention của log nóng và archive.
- Quyền truy cập và export log.
- Truy vết việc xóa khi có yêu cầu phù hợp.

### 15.2. Queue retention khác business retention

Một event stream có thể giữ message 7 ngày để consumer phát lại. Điều này **không có nghĩa dữ liệu nghiệp vụ trong message được phép giữ thêm 7 ngày ngoài retention của source**, hoặc consumer được phép hồi sinh dữ liệu đã hết hạn.

Khi replay:

~~~text
for each event:
    xác định dataClass, sourceVersion, deletion marker
    kiểm tra data còn được phép tạo projection không
    nếu đã hết hạn/xóa theo policy: bỏ qua hoặc thực hiện delete
    nếu còn hợp lệ: áp event idempotently
~~~

### 15.3. DLQ và retry storage

Dead-letter queue lưu những event không xử lý được. Nếu không có retention và quyền phù hợp, nó có thể giữ payload lâu hơn cả primary DB.

Cần:

- TTL/retention riêng cho DLQ.
- Cảnh báo trước khi message hết hạn mà lỗi chưa được xử lý.
- Quy trình replay có kiểm tra quyền và policy hiện tại.
- Không cho phép message lỗi cũ vô tình tái tạo dữ liệu đã xóa.

## 16. Backup, snapshot và khôi phục không được hồi sinh dữ liệu cũ

Backup là trường hợp khó vì mục đích của nó là **giữ lại trạng thái trong quá khứ** để phục hồi khi có sự cố. Một bản backup trước thời điểm xóa có thể chứa record đã bị xóa khỏi production.

### 16.1. Hai chiều thời gian cần quản lý

Giả sử:

~~~text
01/11: Snapshot B1 được tạo, có Order O900.
05/11: O900 được xóa theo chính sách.
10/11: Primary DB gặp sự cố, phục hồi từ B1.
~~~

Nếu phục hồi nguyên trạng rồi mở API, O900 **có thể xuất hiện lại** dù quyết định xóa trước đó đã hoàn tất.

Do vậy phải có **restore-safe deletion strategy**:

1. Lưu dấu xóa hoặc ledger có thẩm quyền đủ bền, theo chính sách phù hợp.
2. Sau restore và trước khi phục vụ truy vấn, áp các quyết định xóa đã diễn ra sau mốc snapshot.
3. Chạy expiry/reconciliation cho những record đã hết hạn theo thời điểm hiện tại.
4. Rebuild hoặc đồng bộ lại search, cache và read model.
5. Kiểm tra quyền truy cập trước khi mở hệ thống trở lại.

### 16.2. Giữ dấu xóa mà không giữ payload

Một **deletion ledger** có thể lưu tối thiểu:

~~~json
{
  "subjectType": "ORDER",
  "subjectKeyHash": "hash-or-pseudonymous-reference",
  "deletionVersion": 12,
  "deletedAt": "2026-11-05T10:00:00Z",
  "policyId": "orders-retention-v2"
}
~~~

Đây là ví dụ thiết kế; hash/ID giả danh vẫn có thể là dữ liệu cần bảo vệ và không bảo đảm ẩn danh tuyệt đối. Giữ ledger chỉ với mục đích cần thiết, giới hạn quyền và retention riêng.

Ledger phải đủ khả năng xác định **bản ghi nào cần bị ngăn phục hồi**, nhưng không nên giữ nguyên nội dung nhạy cảm đã có yêu cầu xóa.

### 16.3. Backup retention khác primary retention

Một hệ thống có thể quy định vòng đời backup khác dữ liệu nóng, nhưng phải được phê duyệt theo nghĩa vụ và khả năng kỹ thuật. Cần biết:

- Snapshot tạo ở đâu và được mã hóa như thế nào?
- Ai có thể restore?
- Backup tồn tại bao lâu, bao gồm bản sao ở vùng khác?
- Có bất kỳ bản copy thủ công nào ngoài chu kỳ không?
- Khi restore, áp deletion ledger và policy mới thế nào?

**Không thể bảo đảm “xóa hoàn toàn khỏi mọi backup lập tức” chỉ bằng TTL trong primary DB.** Nếu yêu cầu mức bảo đảm cao hơn, phải thiết kế riêng phương án xóa, bảo vệ key hoặc vòng đời backup phù hợp với hạ tầng.

## 17. Xóa an toàn theo nhiều hệ: trạng thái và saga

Một quy trình xóa xuyên nhiều hệ thường cần orchestration và theo dõi từng bước, thay vì chỉ phát một sự kiện rồi coi mọi việc đã xong.

~~~mermaid
sequenceDiagram
    participant API as Data Lifecycle API
    participant P as Primary DB
    participant L as Deletion Ledger
    participant S as Search/Projection
    participant C as Cache
    participant A as Analytics

    API->>P: Chặn truy cập / đánh dấu xóa theo version
    P-->>API: Xác nhận trạng thái nguồn
    API->>L: Ghi quyết định xóa bền vững
    API->>S: Yêu cầu thu hồi bản chiếu
    API->>C: Invalidate các key liên quan
    API->>A: Xóa hoặc cập nhật dữ liệu dẫn xuất
    S-->>API: Acknowledgment
    C-->>API: Acknowledgment
    A-->>API: Acknowledgment
    API->>L: Ghi kết quả/ngoại lệ
~~~

Sơ đồ chỉ diễn tả các bước logic. Thứ tự thực tế phải được thiết kế sao cho **crash giữa các bước vẫn có thể tiếp tục an toàn**. Nếu các hệ không có transaction chung, cần cơ chế retry, idempotency và tiến độ bền vững.

### 17.1. Trạng thái deletion workflow

Ví dụ:

~~~text
REQUESTED
  -> VALIDATED
  -> ACCESS_BLOCKED
  -> PROPAGATING
  -> VERIFIED
  -> COMPLETED
~~~

Nhánh ngoại lệ:

~~~text
REQUESTED
  -> HOLD_REVIEW
  -> HELD (nếu có căn cứ và phê duyệt)
  -> RESUMED (khi hold hết hiệu lực)
  -> ...
~~~

Một bước có thể thất bại; không nên chuyển thẳng `COMPLETED` khi chưa biết các hệ bắt buộc đã xác nhận hoặc đã được bao phủ bởi cơ chế retention/khôi phục cho phép.

### 17.2. Idempotent deletion

Worker có thể nhận yêu cầu xóa `O900` hai lần. Kết quả mong muốn:

~~~text
DELETE O900 (lần 1) -> đã xóa hoặc chặn truy cập
DELETE O900 (lần 2) -> vẫn ở trạng thái đã xóa
~~~

Không nên tạo tác động nghiệp vụ mới mỗi lần nhận duplicate event. Định danh xóa, phiên bản và trạng thái tiến độ giúp việc retry an toàn.

### 17.3. Mất một hệ downstream

Giả sử search index tạm không truy cập được:

~~~text
Primary: ACCESS_BLOCKED
Cache:   INVALIDATED
Search:  PENDING_RETRY
Lake:    COMPLETED
~~~

Workflow phải giữ thông tin `PENDING_RETRY`, đặt lịch thử lại và cảnh báo nếu vượt SLA. Trong thời gian đó, có thể cần chặn trả kết quả ở lớp API search bằng cách **kiểm tra trạng thái xóa có thẩm quyền** nếu policy yêu cầu.

## 18. Tránh dữ liệu “hồi sinh” do event cũ hoặc backfill

Một tình huống phổ biến:

~~~text
v1: tạo Order O900
v2: cập nhật Order O900
v3: xóa Order O900

Projector đã xử lý v3.
Sau đó broker replay lại v2.
~~~

Nếu projector chỉ thấy `UPSERT` ở v2 và tạo hàng, O900 xuất hiện lại trong read model.

### 18.1. Không chỉ dùng TTL mà cần version/deletion gate

Một thuật toán ý tưởng:

~~~text
apply(event):
    policy = retentionPolicyFor(event.dataClass)
    currentState = authoritativeStateOrLedger(event.entityId)

    if event.version <= currentState.lastAppliedVersion:
        ignore or confirm already applied
        return

    if currentState.deleted:
        do not recreate from older event
        return

    if event.payload has expired under current policy:
        do not create readable projection
        record handling result
        return

    apply projection mutation idempotently
    persist progress safely
~~~

Đây là pseudocode mô tả chính sách, **không phải giao dịch nguyên tử hoàn chỉnh**. Nếu cập nhật projection và ghi `lastAppliedVersion` ở hai nơi độc lập, worker vẫn có thể chết giữa hai bước. Cần transaction phù hợp hoặc mô hình retry/reconciliation để không đánh dấu thành công khi projection chưa được xử lý.

### 18.2. Tại sao watermark của việc xóa quan trọng?

Nếu bảng phụ xóa hẳn hàng và đồng thời mất luôn thông tin phiên bản, một event `UPSERT` cũ không có gì để so sánh và có thể thêm hàng trở lại.

Giải pháp có thể gồm:

- Giữ **tombstone nghiệp vụ/deletion ledger** có version đủ lâu cho chu kỳ replay và restore.
- Dùng cùng khóa entity để định tuyến xử lý tuần tự, khi hạ tầng có bảo đảm phù hợp.
- Với mọi event, kiểm tra deadline và trạng thái nguồn trước khi tạo read model.
- Sau backfill/restore, quét đối soát để loại hàng đã hết hạn hoặc bị xóa.

### 18.3. Không coi event time là version

Một sự kiện có `occurredAt` lớn hơn chưa chắc là cập nhật được authority chấp nhận sau. Client có thể sai đồng hồ, và event có thể đến trễ. Với bản ghi nghiệp vụ có trạng thái:

~~~text
sourceVersion / sequence
    quyết định thứ tự thay đổi được xác nhận

occurredAt
    mô tả thời gian sự kiện được quan sát

receivedAt
    mô tả thời gian hệ thống nhận
~~~

Không dùng thay thế lẫn nhau khi áp deletion hoặc replay.

## 19. Ngoại lệ: legal hold, điều tra và dữ liệu phải bảo toàn

Một chính sách retention tự động có thể gặp dữ liệu đang thuộc diện **giữ lại tạm thời vì mục đích hợp lệ và được phê duyệt**. Cách xử lý cần được tổ chức rõ:

1. Ai có quyền tạo hoặc gỡ hold?
2. Hold áp dụng cho những entity/dataset nào?
3. Hold bắt đầu và kết thúc theo điều kiện nào?
4. Bản sao nào phải được giữ, bản sao nào vẫn cần hạn chế quyền truy cập?
5. Cơ chế TTL có thể bị vô hiệu hóa hoặc chuyển dữ liệu sang vùng lưu giữ riêng không?
6. Những thay đổi hold có được audit và review định kỳ không?

Ví dụ metadata:

~~~json
{
  "entityType": "ORDER",
  "entityId": "O900",
  "holdId": "hold-2026-014",
  "state": "ACTIVE",
  "scope": ["orders_primary", "orders_archive"],
  "approvedByRole": "authorized-reviewer",
  "reviewAt": "2027-01-31T00:00:00Z"
}
~~~

`holdId` chỉ là định danh minh họa. Không dùng một cờ `held=true` không owner, không phạm vi và không thời hạn review để giữ dữ liệu mãi mãi.

### 19.1. Hold không nhất thiết có nghĩa giữ mọi bản sao hiển thị

Nếu hồ sơ đang được bảo toàn để phục vụ xử lý riêng, có thể cần giữ **bản gốc ở kho hạn chế truy cập**, đồng thời vẫn xóa hoặc ẩn bản hiển thị công khai, cache hoặc search index. Quyết định phạm vi phải dựa trên nghĩa vụ và chính sách, không suy diễn rằng toàn bộ hệ thống được phép tiếp tục truy cập dữ liệu.

### 19.2. Đừng để TTL tự động xóa dữ liệu đang được hold

Một document có TTL index không phân biệt hold có thể vẫn bị TTL monitor xóa khi đến deadline. Nếu có ngoại lệ giữ lại, cần điều chỉnh **thiết kế lưu trữ và cơ chế thực thi**:

- Tách dữ liệu có hold vào collection/bucket/kho riêng được quản lý.
- Hoặc dùng cleanup service có kiểm tra hold trước khi xóa.
- Hoặc mô hình deadline có cơ chế cập nhật an toàn theo hold, nếu phù hợp với engine.

Phải đảm bảo cùng quy tắc áp dụng cho backup, archive, read model và downstream liên quan.

## 20. Thay đổi chính sách retention khi dữ liệu đã tồn tại

Giả sử trước đây raw events được giữ 180 ngày, nay tổ chức quyết định giảm còn 90 ngày.

### 20.1. Không chỉ thay TTL của dữ liệu ghi mới

Nếu chỉ sửa code ingest:

~~~text
Event mới: TTL 90 ngày
Event cũ:  TTL đã đặt 180 ngày
~~~

thì dữ liệu cũ có thể tiếp tục tồn tại theo chính sách trước đó. Cần một **migration/cleanup** có kiểm soát cho dữ liệu hiện hữu, kèm đánh giá ngoại lệ và phạm vi các hệ phụ.

### 20.2. Rollout chính sách theo giai đoạn

Một quy trình:

1. **Phê duyệt policy v2:** xác định lý do, anchor, phạm vi, thời điểm hiệu lực và ngoại lệ.
2. **Kiểm kê hệ chịu ảnh hưởng:** primary, replica, search, cache, stream, lake, backup, export.
3. **Ước lượng khối lượng:** bao nhiêu hàng/partition/file sẽ hết hạn ngay?
4. **Lập kế hoạch dọn an toàn:** hạn chế tốc độ để tránh đột biến I/O, tombstone, index merge.
5. **Đổi đường ghi mới:** áp deadline v2, ghi metadata policy version nếu cần.
6. **Dọn dữ liệu cũ theo lô:** checkpoint, retry và xác nhận hàng không còn được phục vụ.
7. **Đối soát downstream và snapshot:** tránh bản cũ tồn tại ngoài scope.
8. **Theo dõi và kết thúc:** báo cáo tỷ lệ hoàn tất, ngoại lệ và tài nguyên tiêu thụ.

### 20.3. Tăng thời hạn cũng cần cân nhắc

Nếu dữ liệu cũ đã bị xóa vật lý và không còn nguồn phục hồi hợp lệ, **tăng retention từ 90 lên 180 ngày không tự tạo lại dữ liệu quá khứ**. Nên áp dụng chính sách mới cho dữ liệu còn hợp lệ và ghi rõ điểm bắt đầu hiệu lực, không hứa khôi phục dữ liệu đã xóa.

### 20.4. Không chạy xóa hàng loạt mù quáng

Trong Cassandra, xóa rất nhiều hàng có thể tạo lượng tombstone lớn; với MongoDB, index TTL chạy nền và xóa hàng loạt cũng tạo tải; ở data lake, một số cấu trúc cần rewrite file. Hãy chia theo batch/time bucket, có kiểm soát tốc độ và rollback về **trạng thái policy** khi cần, không tự khôi phục dữ liệu đã xóa trái với nghĩa vụ.

## 21. Một service tính deadline nhất quán trong Java

Mục tiêu của lớp này không phải kết nối trực tiếp tới database, mà là cho thấy **mốc tính retention có thể được chuẩn hóa và kiểm thử độc lập**.

### 21.1. Deadline theo duration

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class RetentionDeadline {
    private RetentionDeadline() {}

    public static Instant fromEventTime(
            Instant occurredAt, Duration retention) {
        Objects.requireNonNull(occurredAt);
        Objects.requireNonNull(retention);
        if (retention.isNegative() || retention.isZero()) {
            throw new IllegalArgumentException(
                "retention must be strictly positive");
        }
        return occurredAt.plus(retention);
    }

    public static boolean isExpired(
            Instant deadline, Instant now) {
        Objects.requireNonNull(deadline);
        Objects.requireNonNull(now);
        return !now.isBefore(deadline);
    }
}
~~~

Ví dụ:

~~~java
Instant eventTime =
    Instant.parse("2026-11-14T09:00:00Z");
Instant deadline = RetentionDeadline.fromEventTime(
    eventTime, Duration.ofDays(90));

System.out.println(deadline);
// 2027-02-12T09:00:00Z

System.out.println(
    RetentionDeadline.isExpired(deadline, deadline)
);
// true: hết hạn ngay tại deadline
~~~

Theo hợp đồng trên, `now >= deadline` nghĩa là hết hạn. Khi một API cần giữ khả năng truy cập **đến hết một ngày lịch**, nên tính deadline là **đầu ngày kế tiếp theo timezone thích hợp**, thay vì dùng một “23:59:59.999” phụ thuộc precision.

### 21.2. Deadline theo ngày lịch

~~~java
import java.time.*;

public final class CalendarRetention {
    private CalendarRetention() {}

    public static Instant afterCalendarDays(
            LocalDate anchorDate, int days, ZoneId zone) {
        if (days < 0) {
            throw new IllegalArgumentException("days must be >= 0");
        }
        return anchorDate.plusDays(days)
            .atStartOfDay(zone)
            .toInstant();
    }
}
~~~

Đây là một quy tắc **đến đầu ngày sau N ngày**, không nhất thiết đồng nghĩa “giữ đến hết ngày thứ N”. Định nghĩa business phải chọn chính xác có tính ngày bắt đầu hay không và đặt tên API phù hợp.

Ví dụ retention 30 ngày lịch tính đến đầu ngày cách 30 ngày:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant deadline = CalendarRetention.afterCalendarDays(
    LocalDate.parse("2026-11-14"), 30, zone);
~~~

Ở vùng có DST, khoảng thời gian tính theo hai mốc local date có thể khác `30 × 24 giờ`. Đây là lý do hợp đồng phải quyết định duration hay calendar period.

### 21.3. Không lấy clock của client làm source authority

Một service nhận event đã xảy ra có thể lưu:

~~~java
record RetainedEvent(
    String eventId,
    Instant occurredAt,
    Instant receivedAt,
    Instant expiresAt
) {}
~~~

Khi ingest:

~~~text
1. Validate occurredAt và độ lệch với clock server.
2. Chọn retention anchor theo policy của event class.
3. Tính expiresAt từ anchor đã xác thực.
4. Lưu expiresAt bằng kiểu dữ liệu tương thích với engine.
5. Khi đọc, kiểm tra now < expiresAt nếu policy yêu cầu chặn ngay.
6. Cleanup theo TTL/sweeper, nhưng không cho phép dữ liệu hết hạn được phục vụ.
~~~

Nếu client gửi timestamp bất hợp lý, service phải có chính sách xử lý; không thể mặc định `expiresAt` dựa vào giá trị bất kỳ do client khai báo.

## 22. Khi TTL không đủ: cleanup worker có checkpoint

Với retention có nhiều điều kiện, ví dụ:

~~~text
Chỉ xóa khi:
    now >= retentionDeadline
AND legalHold = false
AND archiveStatus = COMPLETED (nếu policy cần archive)
AND không còn workflow nghiệp vụ bắt buộc giữ
~~~

một **cleanup worker** có thể thích hợp hơn TTL thuần.

### 22.1. Pseudocode

~~~text
while worker is running:
    cutoff = trustedClock.now()
    page = findCandidates(
        expiresAt <= cutoff,
        cursor = lastCheckpoint,
        limit = 500
    )

    for record in page:
        current = recheckAuthoritativeState(record.id)

        if current already deleted:
            recordSuccess(record.id)
            continue

        if current.policyChanged or current.legalHoldActive:
            recordSkipReason(record.id)
            continue

        if trustedClock.now() < current.expiresAt:
            recordSkipReason(record.id)
            continue

        markAccessBlockedOrDeletionIntent(current)
        enqueueDependentDeletes(current.id, current.version)
        deleteOrArchiveCurrentVersion(current)
        recordProgressIdempotently(current.id, current.version)

    persistCheckpoint(page.nextCursor)
    throttleAccordingToClusterHealth()
~~~

Pseudocode minh họa **đường xử lý**, không phải transaction đã được cài đặt. Cần cẩn trọng nếu checkpoint trang được ghi trước khi mọi bản ghi được xử lý thành công: worker có thể **bỏ sót những record thất bại**.

Một thiết kế thường cần:

- Checkpoint chỉ đánh dấu phạm vi đã hoàn tất.
- Retry queue cho từng record thất bại.
- Idempotency theo entity/version.
- Điều kiện xóa hoặc update nguyên tử phù hợp với engine.
- Tách `DELETE_REQUESTED` khỏi `DELETE_COMPLETED`.
- Khả năng chạy lại an toàn sau crash.

### 22.2. Index để tìm ứng viên hết hạn

Nếu có hàng trăm triệu record, query:

~~~text
SELECT * WHERE expiresAt <= now
~~~

không tự hiệu quả trong mọi NoSQL. Cần **đường truy cập dành cho cleanup**:

- MongoDB: TTL index hoặc index/range phù hợp.
- Cassandra: bucket thời gian và bảng chỉ mục phục vụ worker, hoặc thiết kế xóa theo partition/time window phù hợp.
- DynamoDB: TTL native hoặc index/query theo deadline khi workflow cần chủ động.
- Object storage: lifecycle theo prefix/tag/age hoặc inventory + batch deletion.

**Quy trình xóa cũng là một workload truy vấn.** Nó phải được thiết kế theo khóa, index và dữ liệu thực tế, không nên dựa vào scan toàn bộ mỗi phút.

### 22.3. Xóa theo bucket thay vì từng hàng

Nếu các event trong cùng bucket có **cùng mốc retention và không có hold riêng**, có thể xóa cả partition/index/object group khi toàn bộ bucket đã hết hạn. Cách này thường đơn giản và tiết kiệm hơn xóa từng record.

Nhưng không được xóa cả bucket nếu:

- Có event đến muộn với deadline khác.
- Có dữ liệu nhiều loại retention.
- Có một phần record đang được hold.
- Bucket lưu theo `receivedAt`, trong khi retention tính từ `occurredAt` với độ lệch lớn.

Chọn bucket trước khi dữ liệu phát triển thường có ảnh hưởng lớn đến độ khó của retention sau này.

## 23. Thực nghiệm: tính số bản ghi sống và hết hạn

Ví dụ Python thuần dùng để quan sát ngữ nghĩa deadline, không kết nối tới NoSQL cụ thể:

~~~python
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
now = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
retention = timedelta(days=7)

events = [
    {"id": "E1",
     "occurred_at": datetime(2026, 11, 1, 10, 0, tzinfo=UTC)},
    {"id": "E2",
     "occurred_at": datetime(2026, 11, 10, 10, 0, tzinfo=UTC)},
    {"id": "E3",
     "occurred_at": datetime(2026, 11, 14, 11, 0, tzinfo=UTC)},
]

for event in events:
    deadline = event["occurred_at"] + retention
    expired = now >= deadline
    print(event["id"], deadline.isoformat(), expired)
~~~

Ý nghĩa mong đợi:

~~~text
E1: đã hết hạn theo occurredAt + 7 ngày.
E2: còn hạn.
E3: còn hạn.
~~~

Đổi sang retention từ `receivedAt` hoặc đưa vào một event đến muộn để xem kết quả khác nhau. Tiếp theo, thử thiết kế cùng chính sách bằng:

1. MongoDB `expiresAt` + TTL index.
2. Cassandra `USING TTL` tính theo thời gian còn lại từ deadline.
3. DynamoDB `expiresAtEpochSeconds`.
4. Redis `EXAT` cho một cache/session ngắn hạn.

Với từng hệ, chỉ ra **điểm mà TTL không đủ** và lớp ứng dụng phải kiểm tra gì.

## 24. Kiểm chứng chính sách không chỉ bằng số lượng record

Một hệ thống có thể báo “đã xóa 10.000 hàng” nhưng vẫn có **tài liệu hết hạn** đang xuất hiện qua search hoặc cache. Kiểm chứng phải theo cả **tính đúng đắn khi truy cập** và **tiến độ xóa trên từng hệ**.

| Metric / phép kiểm | Điều cần quan sát |
| --- | --- |
| `expired_readable_count` | Số record đã hết hạn vẫn có thể đọc qua API |
| `retention_delete_lag_seconds` | Thời gian từ deadline tới lúc đường xóa hoàn thành |
| `deletion_pending_by_system` | Số yêu cầu còn chờ ở primary/search/cache/lake |
| `deletion_failure_total` | Lỗi xóa theo loại và hệ |
| `replayed_expired_events_total` | Event hết hạn được replay và xử lý ra sao |
| `resurrected_records_detected` | Bản ghi đã xóa xuất hiện lại sau replay/restore |
| `legal_hold_exception_count` | Số ngoại lệ được phê duyệt và đang mở |
| `backup_retention_overdue` | Snapshot quá hạn còn tồn tại |
| `orphan_projection_count` | Dữ liệu phụ không còn nguồn hoặc không đúng version |
| `ttl_tombstones_scanned` | Tác động TTL/xóa tới truy vấn Cassandra |
| `retention_storage_bytes` | Chi phí vật lý theo lớp dữ liệu và hệ |
| `cleanup_worker_backlog` | Số bản ghi cần xử lý đang tồn |

### 24.1. So sánh theo snapshot/mốc thời gian

Nếu source thay đổi liên tục, đọc dữ liệu lúc 10:00 và so với search lúc 10:05 có thể tạo sai khác vì dữ liệu đã được cập nhật. Khi đối soát retention cần xác định:

- Cùng một mốc thời gian logic hoặc một cutoff có thể giải thích.
- Khoảng trễ đồng bộ được phép.
- Tập ID đã hết hạn theo chính sách tại cutoff.
- Những record có hold/ngoại lệ.
- Những bản sao đã xóa và chưa xóa.

Một hệ eventual-consistent có thể có **độ trễ được công bố**, nhưng không được dùng eventual consistency để chấp nhận dữ liệu hết hạn **không bao giờ được dọn**.

### 24.2. Kiểm thử qua các đường truy cập

Một kiểm thử mạnh cho Order O900:

~~~text
1. Tạo O900 và các bản chiếu/caches tương ứng.
2. Kiểm tra O900 xuất hiện đúng trong nguồn, danh sách, search.
3. Đưa O900 tới deadline hoặc yêu cầu xóa hợp lệ.
4. Kiểm tra API không trả dữ liệu sau khi bị chặn.
5. Chờ/điều khiển pipeline xóa, xác nhận các hệ đích.
6. Replay event UPDATE cũ, kiểm tra O900 không hồi sinh.
7. Khôi phục test snapshot trước thời điểm xóa.
8. Áp deletion ledger/reconciliation.
9. Chỉ mở API test khi O900 vẫn không thể được phục vụ.
~~~

Đây là luồng kiểm thử kiến trúc, không phải yêu cầu chạy trên dữ liệu production. Nó kiểm tra cả **đường sinh dữ liệu, xóa dữ liệu và khôi phục dữ liệu**.

## 25. Ví dụ thiết kế chính sách hoàn chỉnh theo từng hệ

Giả sử hệ thống xử lý event thao tác thô và cần:

> “Giữ event chi tiết 90 ngày từ lúc xảy ra; sau đó không phục vụ event thô. Dữ liệu thống kê theo ngày được giữ lâu hơn nếu đã được đánh giá phù hợp. Khi người dùng yêu cầu xóa hợp lệ, mọi bản chiếu liên quan phải được xử lý theo phạm vi chính sách.”

### 25.1. Bảng phân chia trách nhiệm

| Hệ | Dữ liệu giữ | Cơ chế thực thi | Cần kiểm tra bổ sung |
| --- | --- | --- | --- |
| Cassandra primary | Raw event theo tenant/ngày | TTL còn lại hoặc cleanup theo bucket | Event đến muộn, tombstone, repair/compaction |
| MongoDB document store | Event tra cứu hoặc một số metadata | `expiresAt` + TTL index hoặc cleanup worker | Không trả expired record trước khi TTL dọn |
| DynamoDB workflow item | Trạng thái tạm | TTL epoch seconds | Filter/kiểm tra deadline trong API |
| Redis cache | Kết quả truy vấn nóng | EX/EXAT + invalidation | Không giữ quyền truy cập sau deadline |
| Search/vector index | Nội dung/embedding dẫn xuất | Delete event và expiry sweep | Không lộ qua query, không hồi sinh khi reindex |
| Kafka-like stream | Event phục vụ replay | Retention log theo khả năng nền tảng | Consumer dùng expiry gate trước khi upsert |
| Data lake | File raw, aggregate | Lifecycle theo partition hoặc record-level deletion | Anchor/retention class, versioned objects |
| Observability | Log/trace | Retention riêng, hạn chế payload | Không sao chép dữ liệu nhạy cảm quá mức |
| Backups | Snapshot khôi phục | Backup lifecycle + restore policy | Không hồi sinh record sau restore |

Tên các hệ và công nghệ ở đây là các **phương án minh họa**; không nhất thiết một sản phẩm phải dùng tất cả. Trọng tâm là gắn **phạm vi và cơ chế cụ thể** cho mọi nơi dữ liệu thực sự đi qua.

### 25.2. Thứ tự triển khai đề xuất

~~~text
1. Xác định business policy và dữ liệu thuộc phạm vi.
2. Tìm nguồn chuẩn và vẽ tất cả đường phát tán dữ liệu.
3. Định nghĩa anchor, duration/deadline, ngoại lệ và access rule.
4. Chọn TTL native ở nơi có ngữ nghĩa tương thích.
5. Chọn cleanup service/bucket deletion nơi TTL không đủ.
6. Thiết kế deletion event, idempotency, version và anti-resurrection.
7. Quy định retention cho stream, log, backup và object versions.
8. Chạy thử với event đến muộn, hold, replay và restore.
9. Triển khai theo giai đoạn, có checkpoint và giới hạn tải.
10. Theo dõi độ trễ xóa, phạm vi hoàn tất và chi phí.
~~~

### 25.3. Đối chiếu giữa lời hứa và khả năng engine

Không nên viết hợp đồng:

~~~text
"Document bị xóa hoàn toàn khỏi tất cả hệ đúng 00:00:00"
~~~

nếu cơ chế thực tế gồm TTL monitor, compaction, eventual consistency và backup có vòng đời riêng. Thay vào đó cần **phân tách các cam kết**:

~~~text
Từ deadline:
    API không còn phục vụ dữ liệu đã hết hạn.

Trong ngân sách xóa đã phê duyệt:
    Các hệ dẫn xuất và vùng lưu trữ nóng được làm sạch.

Theo backup policy:
    Snapshot hết vòng đời và restore áp deletion ledger.
~~~

Các ngân sách cụ thể phải được tổ chức xác nhận và đo bằng hệ thống thật. Việc nói đúng phạm vi cam kết tốt hơn đưa một tuyên bố xóa vật lý không thể kiểm chứng.

## 26. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách tiếp cận phù hợp |
| --- | --- | --- |
| Đặt TTL giống nhau cho mọi loại dữ liệu | Xóa sớm dữ liệu cần giữ, giữ lâu dữ liệu không cần | Retention theo data class và purpose |
| Viết “90 ngày” nhưng không nêu anchor | Hệ này tính từ xảy ra, hệ khác tính từ lúc nhận | Định nghĩa `anchorField` rõ ràng |
| Xem cache hit là phiên còn hiệu lực | Token hết hạn có thể vẫn được chấp nhận | Kiểm tra deadline ở lớp xác thực |
| Coi TTL là xóa vật lý tức thì | Dữ liệu có thể còn trong TTL queue, compaction, backup | Tách logical expiry, cleanup và physical purge |
| Dùng epoch milliseconds cho DynamoDB TTL seconds | Deadline sai rất lớn | Chuẩn hóa đơn vị và test serialize |
| Gắn TTL từ lúc ingest cho event đến muộn | Giữ quá lâu theo event-time policy | Tính TTL còn lại hoặc cleanup theo absolute deadline |
| Bỏ qua read model/search/cache | Dữ liệu vẫn được truy cập qua đường phụ | Inventory dữ liệu và deletion propagation |
| Chỉ xóa file hiện hành ở object versioning | Phiên bản cũ còn tồn tại | Quản lý noncurrent versions và replication |
| Tái tạo projection từ stream mà không kiểm tra policy | Dữ liệu hết hạn/xóa hồi sinh | Deletion/version gate và reconciliation |
| Chỉ dựa vào timestamp client để phân xử | Client có thể sai clock hoặc giả mạo | Authority, server checks và version |
| Thiết kế bucket trộn nhiều loại retention | Không thể xóa nguyên bucket an toàn | Partition theo retention class/anchor thích hợp |
| TTL mọi record kể cả đang legal hold | Vi phạm ngoại lệ đã được phê duyệt | Hold-aware storage và cleanup |
| Gỡ hold nhưng quên tiếp tục xóa | Dữ liệu bị giữ vô thời hạn | Review, expiry và workflow resume |
| Backup restore mở API trước đối soát xóa | Record đã xóa xuất hiện trở lại | Restore gate + deletion ledger |
| Log toàn bộ payload “để dễ debug” | Tạo bản sao dữ liệu nhạy cảm ngoài policy | Logging tối thiểu, redaction và retention riêng |
| Đo số lượng xóa mà không kiểm tra quyền đọc | Vẫn có expired record qua API | Test `expired_readable_count` và downstream |
| Coi dữ liệu aggregate mặc nhiên ẩn danh | Có thể tái nhận diện hoặc liên kết | Đánh giá dữ liệu dẫn xuất và phạm vi bảo vệ |

## 27. Bài tập vận dụng

### Bài 1 — Chọn retention anchor

Hệ thống nhận ba event:

~~~text
E1: occurredAt=01/08, receivedAt=01/08
E2: occurredAt=01/08, receivedAt=20/08
E3: occurredAt=20/08, receivedAt=20/08
~~~

Chính sách giữ event thô **90 ngày từ `occurredAt`**. Hãy:

1. Tính deadline của từng event theo UTC (giả sử ngày là 00:00 UTC).
2. Giải thích vì sao dùng cùng TTL 90 ngày khi ingest khiến E2 bị giữ lâu hơn quy định.
3. Thiết kế cách tính TTL còn lại cho E2 và cách xử lý event nhận khi deadline đã qua.
4. Nếu client có thể gửi sai clock, bổ sung chính sách xác minh.

### Bài 2 — Session và quyền truy cập

Một session được phát lúc 10:00, hết hạn lúc 10:30. DynamoDB TTL chưa dọn item lúc 10:31. Redis vẫn còn một key cache mô tả phiên.

Hãy giải thích:

- API có được chấp nhận session lúc 10:31 không?
- TTL của mỗi hệ phục vụ mục đích gì?
- Những trường hợp nào cần xóa/invalidate ngay lập tức?
- Nếu dùng sliding session, những mốc nào được cập nhật và có hạn tuyệt đối không?

### Bài 3 — Thiết kế xóa theo data map

Một hồ sơ người dùng tồn tại trong:

~~~text
MongoDB primary
Redis cache
Search index
CDC stream
Analytics dataset
Object storage exports
Backup snapshot
~~~

Hãy vẽ luồng xóa hợp lệ và nêu cách xử lý ở **từng hệ**, gồm replay, phiên bản object cũ, retention của backup và dấu vết tiến độ xóa. Chỉ ra lúc nào có thể trả trạng thái `DELETION_COMPLETED`.

### Bài 4 — Cassandra TTL và tombstones

Một bảng Cassandra chứa event thô, TTL 7 ngày, mỗi partition có hàng trăm nghìn sự kiện và có cập nhật/xóa dữ liệu cũ thường xuyên.

Hãy mô tả:

- Vì sao `LIMIT 20` vẫn có thể chậm khi nhiều tombstone?
- Vì sao không nên giảm `gc_grace_seconds` tùy tiện?
- Khi nào dữ liệu theo time bucket giúp cleanup?
- Khi nào time-window compaction không còn lý tưởng?
- Cần quan sát những metric nào trước khi đổi compaction strategy?

### Bài 5 — Khôi phục snapshot và dữ liệu đã xóa

~~~text
01/11: Backup B1 có User U42.
05/11: U42 được xóa theo yêu cầu hợp lệ.
10/11: Hệ thống restore từ B1.
~~~

Hãy thiết kế **restore gate** ngăn U42 xuất hiện lại qua API, search và cache. Đề xuất loại metadata tối thiểu cần giữ trong deletion ledger và cách xử lý event cũ được replay sau restore.

### Bài 6 — Policy v2 rút ngắn thời hạn

Raw events trước đây lưu 180 ngày, nay giảm còn 90 ngày. Dữ liệu được lưu ở Cassandra, search và data lake.

Hãy lập kế hoạch:

1. Kiểm kê và phê duyệt.
2. Ước lượng record/file phải dọn.
3. Thay đổi ingest mới.
4. Dọn dữ liệu cũ theo batch mà không gây quá tải.
5. Kiểm tra hold/ngoại lệ.
6. Xác nhận dữ liệu không còn được trả qua search/API.
7. Bảo đảm backup/restore không hồi sinh dữ liệu.

### Bài 7 — Retention theo ngày địa phương

Một tổ chức yêu cầu giữ tài liệu “đến hết ngày thứ 30 sau ngày đóng case” theo `Europe/Paris`. Hãy:

- Viết rõ quy tắc có tính ngày đóng case hay không.
- Tính deadline bằng `LocalDate` và `ZoneId` trong Java.
- Giải thích tại sao cộng đơn giản `30 × 24` giờ có thể sai khi qua DST.
- Chỉ ra cách lưu deadline bằng instant ở NoSQL.

### Bài 8 — Đánh giá thiết kế theo chi phí

Một ứng dụng có 200.000 event/ngày, trung bình 1 KiB/event, replication factor 3 và chỉ lưu 90 ngày.

Hãy tính:

1. Dung lượng logic 90 ngày.
2. Phần dữ liệu logic nhân bản 3 lần.
3. Những overhead không nằm trong phép nhân đó.
4. Sự khác nhau giữa giữ 90 và 365 ngày đối với dung lượng thô.
5. Những điều kiện nào khiến dùng bucket/ngày và xóa theo partition hoặc index hợp lý?

### Bài 9 — Chọn hệ để thực thi

Ứng dụng có:

- Giỏ hàng bỏ dở.
- Session đăng nhập.
- Event đo cảm biến.
- Chứng từ đã phát hành.
- Dữ liệu tìm kiếm sản phẩm.

Hãy lựa chọn giữa TTL native, cleanup worker, archive và deletion pipeline cho từng loại. Nêu **vì sao không thể chọn chỉ dựa trên tên hệ quản trị** mà phải xét chính sách nghiệp vụ và các bản sao thực tế.

## Kết luận

Thiết kế **giới hạn lưu giữ theo nghiệp vụ** không đơn thuần là chọn một số ngày cho TTL. Một chính sách đúng cần mô tả **dữ liệu nào, giữ vì mục đích gì, tính từ mốc nào, được xem ở đâu, hết hiệu lực khi nào, hành động xóa/archive nào phải xảy ra và bằng chứng hoàn tất là gì**.

Trong NoSQL, những điểm đặc biệt cần nhớ:

- **Hết hiệu lực nghiệp vụ không đồng nghĩa bị xóa vật lý ngay lập tức**. API phải thực thi deadline khi cần chặn truy cập; TTL và cleanup xử lý vòng đời storage.
- **Mỗi engine có ngữ nghĩa riêng**: MongoDB TTL index dựa trên Date, Cassandra TTL gắn với ghi và tombstone, DynamoDB TTL dùng epoch seconds và dọn bất đồng bộ, Redis TTL/EXAT thích hợp cho cache/session ngắn hạn.
- **Phạm vi là toàn bộ đường phát tán dữ liệu**, không chỉ bảng primary: read model, search/vector index, cache, event stream, DLQ, data lake, log, object versions và backup.
- **Dữ liệu đến muộn, backfill, replay và restore có thể làm sai retention** nếu không có deadline, version, deletion ledger và cơ chế đối soát.
- **Ngoại lệ như hold phải có owner, phạm vi và cơ chế bảo vệ rõ**; không để TTL tự động phá vỡ những quyết định giữ dữ liệu hợp lệ.
- **Chính sách cần được vận hành và đo** bằng số record đã hết hạn còn đọc được, deletion lag, retry/backlog, khả năng sửa lệch và kiểm tra khôi phục.

Một hệ thống có vòng đời dữ liệu bền vững là hệ thống **biết chính xác dữ liệu phải tồn tại đến khi nào, ở những đâu, cho mục đích nào và có cách kiểm chứng rằng từng bản sao đã được xử lý đúng chính sách**.
