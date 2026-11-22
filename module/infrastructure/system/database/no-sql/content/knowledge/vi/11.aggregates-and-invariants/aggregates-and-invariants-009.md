# Chấp nhận nhất quán sau cùng khi nghiệp vụ cho phép

## 1. Tình huống mở đầu: dữ liệu đúng nhưng chưa xuất hiện ở mọi nơi

Một nền tảng thương mại có hai giao diện:

- **Trang quản trị sản phẩm**: người bán sửa tên, mô tả và giá bán.
- **Trang tìm kiếm sản phẩm**: khách hàng lọc, tìm theo từ khóa và xem danh sách sản phẩm.

Lúc 10:00:00, người bán đổi tên sản phẩm từ “Tai nghe A” thành “Tai nghe A Pro”. Cơ sở dữ liệu nguồn đã ghi thành công. Nhưng hệ thống tìm kiếm dùng một bản chỉ mục riêng và cập nhật đến 10:00:02 mới nhận thay đổi.

~~~text
10:00:00.000  Người bán lưu tên mới
10:00:00.020  Database nguồn xác nhận ghi thành công
10:00:00.200  Khách tìm kiếm: danh sách vẫn hiển thị tên cũ
10:00:01.400  Bộ đồng bộ xử lý sự kiện thay đổi
10:00:02.000  Search index hiển thị tên mới
~~~

Trong hai giây ấy, **hai nơi có thể cho kết quả khác nhau về cùng một sản phẩm**. Hệ thống đang có một trạng thái **chưa hội tụ**, không nhất thiết đã xảy ra lỗi dữ liệu. Nếu hợp đồng sản phẩm chấp nhận rằng danh sách tìm kiếm chậm hơn vài giây, đây có thể là lựa chọn kiến trúc hợp lý.

Nhưng nếu thay đổi là **thu hồi quyền truy cập vào tài liệu bí mật**, **xác nhận thanh toán** hoặc **giảm số lượng tồn kho xuống 0**, việc hiển thị/truy cập dựa trên bản sao cũ có thể gây hậu quả nghiêm trọng. Do đó, không thể tuyên bố “NoSQL nên dùng eventual consistency” như một quy tắc chung.

**Mục tiêu bài học:** biết khi nào có thể chấp nhận **nhất quán sau cùng (eventual consistency)**, khi nào bất biến nghiệp vụ buộc phải có bảo đảm mạnh hơn, và làm cách nào để hệ thống hội tụ đáng tin cậy thay vì chỉ “hy vọng dữ liệu sẽ đồng bộ”.

## 2. Nhất quán sau cùng là gì?

Ở mức khái niệm, eventual consistency mô tả một hệ có nhiều bản sao hoặc nhiều biểu diễn của cùng trạng thái: sau khi các cập nhật mới **ngừng xảy ra**, nếu các thông điệp được truyền và xử lý thành công, các bản sao **cuối cùng sẽ hội tụ** về trạng thái nhất quán theo quy tắc của hệ.

Đây là khẳng định về sự hội tụ khi những điều kiện cần được đáp ứng; nó **không tự đưa ra giới hạn thời gian cụ thể** và **không tự bảo đảm dữ liệu sẽ hội tụ nếu thông điệp bị mất vĩnh viễn, lỗi xử lý không được sửa hoặc quy tắc giải quyết xung đột sai**.

Ví dụ logic:

~~~text
Thời điểm T0:
  Source = version 8
  Read model A = version 7
  Read model B = version 6

Sau khi sự kiện được truyền và áp dụng:
  Source = version 8
  Read model A = version 8
  Read model B = version 8
~~~

Trong khoảng giữa, một người dùng có thể thấy version 7 hoặc 8 tùy đường đọc. Đến khi hội tụ, các bản sao cùng phản ánh version 8 theo mô hình cập nhật đã chọn.

### 2.1. Phân biệt các khái niệm dễ nhầm

| Khái niệm | Nội dung | Ví dụ |
| --- | --- | --- |
| **Strong consistency / linearizable read-write** | Thao tác có vẻ có hiệu lực tức thời tại một điểm giữa lúc bắt đầu và kết thúc, theo hợp đồng tương ứng | Đọc sau một ghi đã xác nhận thấy phiên bản mới nhất |
| **Eventual consistency** | Các bản sao có thể tạm khác nhau nhưng hội tụ khi không còn cập nhật và hệ vận hành bình thường | Search index cập nhật sau database nguồn |
| **Read-your-writes consistency** | Một phiên/người dùng thấy cập nhật của chính mình trong các lần đọc tiếp theo | Người bán lưu tên mới, trang quản trị thấy tên mới |
| **Monotonic reads** | Một phiên không bị đọc lùi về phiên bản cũ hơn đã thấy | Đã xem version 8 thì không bị quay lại version 7 |
| **Causal consistency** | Những cập nhật có quan hệ nhân quả được quan sát theo thứ tự phù hợp | Thấy bình luận trả lời sau khi đã thấy bình luận gốc |
| **Bounded staleness** | Độ cũ được giới hạn theo thời gian hoặc số phiên bản, tùy hợp đồng sản phẩm | Bản đọc không được trễ quá một ngưỡng đã quy định |
| **Durability** | Ghi đã xác nhận sống sót qua những loại lỗi hệ thống cam kết bảo vệ | Máy chủ khởi động lại nhưng dữ liệu đã commit còn |
| **Availability** | Hệ có thể phục vụ yêu cầu trong phạm vi lỗi đã xác định | Một replica lỗi, dịch vụ vẫn đáp ứng |

**Độ bền (durability)** không đồng nghĩa **độ nhất quán (consistency)**. Một bản sao có thể lưu rất bền dữ liệu **cũ**; một hệ trả kết quả nhất quán mạnh có thể vẫn cần thiết kế backup và khôi phục khi xóa nhầm.

### 2.2. “Nhất quán sau cùng” không phải “muốn sai bao lâu cũng được”

Một hợp đồng kỹ thuật thiếu cụ thể:

> Search sẽ đồng bộ sau một lúc.

Một hợp đồng tốt hơn:

> Khi pipeline khỏe và tải trong mức thiết kế, 99% thay đổi tên sản phẩm sẽ có thể tìm thấy qua search trong vòng 5 giây. Các thay đổi còn lại phải có cơ chế retry, cảnh báo, đối soát và khả năng rebuild; khi độ trễ vượt ngưỡng, hệ chuyển sang trạng thái suy giảm có kiểm soát.

Các con số trên chỉ là **ví dụ mục tiêu SLO** để minh họa cách viết yêu cầu, không phải cam kết mặc định của bất kỳ sản phẩm NoSQL nào.

## 3. Nhóm dữ liệu và bất biến nghiệp vụ: ranh giới quan trọng nhất

**Bất biến (invariant)** là điều kiện luôn phải đúng tại những thời điểm và phạm vi mà nghiệp vụ yêu cầu. Ví dụ:

- Một mã đơn chỉ được tính tiền **một lần**.
- Tồn kho không được bán vượt số lượng khả dụng theo chính sách đặt hàng.
- Tổng tiền của một giao dịch phải bằng tổng những khoản được ghi nhận theo quy tắc kế toán.
- Người đã bị thu hồi quyền không được truy cập tài liệu bí mật.
- Không được có hai người cùng giữ một chỗ ngồi độc quyền đã xác nhận.

Khác với một dữ liệu được hiển thị hơi chậm, vi phạm bất biến có thể tạo ra **quyết định nghiệp vụ không thể tự sửa bằng cách chờ hội tụ**.

### 3.1. “Nhóm dữ liệu” giúp xác định nơi phải nhất quán mạnh

Một **aggregate** hoặc **nhóm dữ liệu nghiệp vụ** có thể được định nghĩa là tập trạng thái được quản lý như một đơn vị bảo vệ một số bất biến. Ví dụ, một giỏ hàng có:

~~~json
{
  "cartId": "CART-072",
  "userId": "U01",
  "version": 12,
  "items": [
    { "sku": "P10", "quantity": 2 },
    { "sku": "P20", "quantity": 1 }
  ],
  "updatedAt": "2026-11-14T10:00:00Z"
}
~~~

Nếu bất biến là “một dòng sản phẩm không có quantity âm, tổng số item không vượt 30”, ứng dụng có thể cân nhắc giữ toàn giỏ trong **một document** và dùng **conditional write/CAS theo version** để cập nhật atomic trong ranh giới document đó, nếu hệ quản trị hỗ trợ.

Nhưng bất biến “tổng hàng trong mọi giỏ không vượt tồn kho thật” là **xuyên nhiều giỏ và kho hàng**, không thể được bảo vệ chỉ bằng việc cập nhật riêng từng cart document.

### 3.2. Một bảng quyết định theo bất biến

| Thao tác | Có thể chấp nhận đọc chậm? | Có được chấp nhận vi phạm bất biến? | Gợi ý thiết kế |
| --- | --- | --- | --- |
| Tăng lượt xem bài viết | Thường có | Có thể chấp nhận sai lệch tạm trong dashboard | Bộ đếm/analytics hội tụ, xử lý trùng |
| Cập nhật gợi ý sản phẩm | Thường có | Ranking chậm thay đổi thường không phá giao dịch | Bản chiếu tìm kiếm hoặc đề xuất bất đồng bộ |
| Hiển thị avatar mới | Thường có | Không nhất thiết phải thấy ở mọi trang ngay lập tức | Cache invalidation, phiên đọc của chủ tài khoản |
| Người bán sửa mô tả sản phẩm | Có thể vài giây | Tùy hợp đồng xuất bản | Source ghi trước, index hội tụ |
| Xác nhận thanh toán | Không nên dựa vào bản đọc cũ để quyết định | **Không** được thu tiền hai lần | Transaction/idempotency và nguồn dữ liệu có bảo đảm phù hợp |
| Giữ chỗ cuối cùng | Rủi ro cao | **Không** được xác nhận hai khách cho một chỗ độc quyền | Một nơi phân xử nhất quán, conditional write/transaction |
| Thu hồi quyền truy cập | Hiển thị có thể trễ, nhưng quyền thực thi không được trễ theo yêu cầu bảo mật | **Không** được cho phép truy cập trái quyền | Authorization kiểm tra nguồn đáng tin hoặc cơ chế thu hồi mạnh |

Điểm cốt lõi: **không nhất thiết toàn bộ hệ thống phải nhất quán mạnh**. Hãy bảo vệ bất biến ở đúng ranh giới và cho phép các **bản chiếu đọc** hội tụ ở những nơi hậu quả của độ trễ là chấp nhận được.

### 3.3. Tách “quyết định” khỏi “hiển thị”

Một trang sản phẩm có thể hiển thị nhãn **“Còn hàng”** dựa trên search index hoặc cache. Nhưng khi khách nhấn **Đặt hàng**, hệ phải kiểm tra/đặt giữ số lượng ở nguồn tồn kho có cơ chế ghi điều kiện hoặc giao dịch thích hợp.

~~~text
Danh sách tìm kiếm: "Còn hàng" (có thể trễ)
                ↓
Người dùng bấm Mua
                ↓
Nguồn tồn kho kiểm tra và đặt giữ theo bất biến
                ↓
Chỉ trả "Đặt hàng thành công" nếu điều kiện được bảo đảm
~~~

Lối thiết kế này cho phép giao diện phản hồi nhanh mà không biến dữ liệu hơi cũ thành cơ sở xác nhận một cam kết nghiệp vụ.

## 4. Nhất quán trong một thực thể và nhất quán giữa các thực thể

Các NoSQL khác nhau có mức atomicity, consistency và transaction khác nhau. Một hệ có thể bảo đảm cập nhật atomic **một document/item** nhưng không mặc định bảo đảm các thay đổi qua **nhiều document, nhiều partition hoặc nhiều dịch vụ**.

Ví dụ luồng đặt hàng:

~~~text
Order O9001     -> status = PAID
Payment TX100   -> captured = true
Inventory P10   -> available = 8
Search index    -> badge = "Còn hàng"
Notification    -> email xác nhận
~~~

Không nên áp một chính sách consistency cho tất cả:

1. **Order/Payment/Inventory** chứa các quyết định cần bảo vệ bất biến. Cần cơ chế transaction, ghi có điều kiện, idempotency hoặc quy trình phân tán có kiểm soát.
2. **Search index** là bản chiếu đọc; có thể cập nhật chậm nếu giao diện không cam kết tồn kho tức thời và bước đặt hàng kiểm tra lại.
3. **Notification** có thể gửi sau khi đơn đã commit, thông qua một hàng đợi sự kiện tin cậy. Gửi chậm vài giây thường khác hoàn toàn với việc ghi sai trạng thái thanh toán.

Điều này là tinh thần của **tách write model và read model theo nhu cầu**: trạng thái quyết định được bảo vệ chặt, còn mô hình đọc có thể ưu tiên hiệu năng và khả năng mở rộng.

## 5. Tình huống mẫu: nguồn chính và bản chiếu tìm kiếm

Giả sử hệ thống quản lý sản phẩm có:

- **Product DB**: nguồn sự thật cho tên, mô tả, giá niêm yết và trạng thái sản phẩm.
- **Search index**: bản chiếu phục vụ full-text search, lọc và sắp xếp.
- **API đặt hàng**: kiểm tra giá và tồn kho ở nguồn có thẩm quyền trước khi cam kết.

~~~mermaid
flowchart LR
    A["Admin API"] --> B[("Product DB - nguồn chính")]
    B --> C["Transactional outbox / CDC"]
    C --> D["Indexer"]
    D --> E[("Search index - bản chiếu")]
    F["Search API"] --> E
    G["Checkout API"] --> H[("Order/Inventory - quyết định")]
    F -. "Người dùng chọn sản phẩm" .-> G
~~~

Các câu hỏi phải trả lời rõ:

| Câu hỏi | Ví dụ câu trả lời của hệ |
| --- | --- |
| Khi nào cập nhật sản phẩm được coi thành công? | Khi transaction nguồn commit |
| Khi nào search có thể thấy thay đổi? | Khi sự kiện được index và refresh |
| Search có thể trễ không? | Có, trong ngưỡng đã công bố |
| Có thể dùng search index để chốt giá thanh toán không? | Không, phải kiểm tra nguồn giá có thẩm quyền |
| Khi indexer chết, thay đổi có mất không? | Không nếu outbox/event log còn và có retry/replay |
| Nếu index bị hỏng, khôi phục bằng cách nào? | Rebuild từ nguồn chính và phát lại thay đổi |

### 5.1. Một chuỗi sự kiện

~~~mermaid
sequenceDiagram
    participant A as Admin
    participant DB as Product DB
    participant O as Outbox
    participant W as Indexer
    participant S as Search
    A->>DB: Update product P10, version 42
    DB->>O: Ghi ProductUpdated trong cùng transaction
    DB-->>A: Commit thành công
    Note over A,S: Search tạm thời còn version 41
    W->>O: Nhận sự kiện version 42
    W->>S: Upsert bản chiếu version 42
    S-->>W: Đã chấp nhận cập nhật
    Note over A,S: Sau refresh, truy vấn thấy version 42
~~~

Sơ đồ cho thấy **khác biệt giữa xác nhận ghi ở nguồn và khả năng đọc ở bản chiếu**. Việc search index chấp nhận thao tác upsert cũng có thể khác thời điểm thay đổi đã hiển thị trong truy vấn, tùy cơ chế refresh/visibility của sản phẩm.

## 6. Transactional outbox: không để mất thay đổi ở giữa hai hệ

Một lỗi thường gặp:

~~~text
1. UPDATE product DB                  -> thành công
2. Publish event ProductUpdated       -> lỗi mạng
3. API đã trả thành công cho người bán
4. Search không bao giờ nhận thay đổi
~~~

Nếu hai bước ghi thuộc hai hệ không có transaction chung, lỗi giữa chúng có thể khiến bản chiếu lệch vô thời hạn. Eventual consistency **không sửa được một sự kiện không bao giờ được truyền**.

**Transactional outbox** giải quyết một lớp lỗi này bằng cách ghi dữ liệu nguồn và bản ghi thông báo **trong cùng transaction của nguồn**.

### 6.1. Mô hình đơn giản

~~~sql
BEGIN;

UPDATE products
SET name = 'Tai nghe A Pro',
    version = version + 1
WHERE product_id = 'P10';

INSERT INTO outbox (
    event_id, aggregate_id, event_type, payload, created_at
) VALUES (
    'EVT-420',
    'P10',
    'ProductUpdated',
    '{"productId":"P10","version":42}',
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

Đây là **ví dụ ý tưởng SQL** cho một nguồn dữ liệu có transaction; không phải cú pháp chung của mọi NoSQL. Nếu hệ NoSQL nguồn hỗ trợ transaction/atomic write theo phạm vi nhất định, cần thiết kế tương đương trong đúng ranh giới được bảo đảm. Nếu không, phải cân nhắc nguồn sự kiện khác, thay đổi ranh giới aggregate hoặc cơ chế phục hồi thiếu sự kiện.

Sau commit:

1. Worker/CDC đọc outbox.
2. Gửi sự kiện cho queue/broker hoặc xử lý trực tiếp.
3. Indexer cập nhật bản chiếu.
4. Ghi nhận trạng thái hoàn thành và xử lý retry nếu lỗi.

### 6.2. Outbox không làm toàn pipeline “exactly once”

Một tình huống có thể xảy ra:

~~~text
Indexer ghi version 42 vào search thành công
Indexer crash trước khi xác nhận đã xử lý event
Worker chạy lại cùng event version 42
~~~

Vì vậy, consumer nên **idempotent**: xử lý lặp cùng một sự kiện không làm trạng thái sai. Thường dùng **ID ổn định, version tăng theo aggregate** hoặc điều kiện ghi để tránh sự kiện cũ ghi đè sự kiện mới.

Một outbox có thể giảm nguy cơ mất thay đổi nguồn–event, nhưng vẫn cần:

- Retry với backoff và giới hạn phù hợp.
- Dead-letter queue hoặc khu vực lưu lỗi để điều tra.
- Theo dõi sự kiện xử lý chậm.
- Replay được sau outage.
- Quy tắc xử lý message trùng/đảo thứ tự.
- Reconciliation giữa nguồn và bản chiếu.

## 7. Version và thứ tự sự kiện: điều kiện để hội tụ đúng

Giả sử sản phẩm P10 trải qua hai lần cập nhật:

~~~text
Version 41: name = "Tai nghe A"
Version 42: name = "Tai nghe A Pro"
Version 43: name = "Tai nghe A Pro 2026"
~~~

Nếu các sự kiện đến indexer theo thứ tự:

~~~text
43 đến trước 42
~~~

và indexer ghi đè mù, bản chiếu có thể kết thúc ở **version 42**, tức **trở về dữ liệu cũ**. Chờ thêm không giúp nó tự hội tụ nếu không có event khác.

Một chiến lược là gắn version đơn điệu theo **mỗi aggregate**:

~~~json
{
  "eventId": "EVT-430",
  "aggregateType": "Product",
  "aggregateId": "P10",
  "aggregateVersion": 43,
  "eventType": "ProductUpdated",
  "occurredAt": "2026-11-14T10:00:10Z",
  "payload": {
    "name": "Tai nghe A Pro 2026",
    "status": "PUBLISHED"
  }
}
~~~

Indexer áp dụng nguyên tắc:

~~~text
Incoming event version < stored version  -> bỏ qua
Incoming event version = stored version  -> xử lý idempotent/kiểm tra trùng
Incoming event version > stored version  -> áp dụng nếu payload là trạng thái đầy đủ
~~~

**Điều kiện quan trọng:** Nếu sự kiện chỉ chứa **delta** như “tăng số lượt xem thêm 1” hoặc “đổi trường X”, không thể luôn bỏ qua các version trung gian. Lúc đó consumer có thể cần xử lý đúng thứ tự, phát hiện gap và replay event còn thiếu, hoặc lấy **snapshot trạng thái đầy đủ** từ nguồn trước khi ghi projection.

### 7.1. Phân biệt event ID, aggregate ID và version

| Giá trị | Vai trò |
| --- | --- |
| **eventId** | Nhận diện một thông điệp/sự kiện để chống xử lý trùng |
| **aggregateId** | Xác định thực thể nguồn, ví dụ product P10 |
| **aggregateVersion** | Thứ tự thay đổi của cùng một aggregate |
| **occurredAt** | Thời điểm nghiệp vụ phát sinh |
| **processedAt** | Thời điểm consumer áp dụng vào bản chiếu |

Không dùng timestamp đồng hồ của nhiều máy làm **version có trật tự tuyệt đối** nếu chưa có cơ chế kiểm soát clock skew. Khi các cập nhật đồng thời từ nhiều nơi, cần một bộ phân xử version/sequence phù hợp với mô hình ghi.

### 7.2. Trạng thái xóa cần có version

Giả sử:

~~~text
Version 44: sản phẩm P10 bị xóa
Version 43: ProductUpdated đến muộn sau đó
~~~

Nếu bản chiếu chỉ xóa hoàn toàn record mà không giữ thông tin version/tombstone đủ lâu, event version 43 có thể **tạo lại sản phẩm đã xóa**.

Một lựa chọn là giữ **tombstone có version 44**, để từ chối mọi sự kiện cũ hơn. Thời gian lưu tombstone và khả năng xử lý replay rất cũ cần được xác định; xóa vật lý ngay không phải lúc nào cũng an toàn cho pipeline bất đồng bộ.

## 8. Nhân bản dữ liệu: eventual consistency còn xảy ra trong cùng database

Không chỉ mô hình “DB nguồn → search” mới có dữ liệu cũ. Một NoSQL cluster có nhiều replica cũng có thể cho kết quả khác nhau tùy mô hình replication và mức đọc/ghi.

Ví dụ:

~~~text
Primary/leader: version 9
Replica R1:     version 9
Replica R2:     version 8
~~~

Một client đọc R2 có thể thấy phiên bản cũ, dù ghi mới đã được xác nhận ở nơi khác.

### 8.1. Từng sản phẩm có hợp đồng khác nhau

- **DynamoDB:** Một số thao tác đọc trên bảng và local secondary index có thể yêu cầu strongly consistent read trong phạm vi hỗ trợ; truy vấn qua global secondary index là eventual consistency. Thiết kế phải phân biệt đường đọc nào được dùng.
- **Cassandra:** Replication factor cùng mức consistency đọc/ghi như ONE, LOCAL_QUORUM hoặc QUORUM ảnh hưởng mức xác nhận và khả năng quan sát thay đổi. Các quy tắc quorum phụ thuộc topology và giả định; không thể coi một công thức chung là bảo đảm tuyệt đối cho mọi tình huống.
- **MongoDB replica set:** Read preference và read concern cùng write concern quyết định khả năng đọc từ node nào, mức xác nhận ghi và những bảo đảm có thể yêu cầu. Đọc từ secondary có thể trễ primary; cần chọn semantics theo nghiệp vụ.
- **Redis replication:** Trong nhiều cấu hình, truyền thay đổi từ primary tới replica là bất đồng bộ; chuyển leader và đọc replica cần được đánh giá theo độ trễ cùng hợp đồng dữ liệu.

Các mô tả trên nhấn mạnh **khả năng cấu hình**; tính năng chính xác phải được kiểm tra theo phiên bản, loại dịch vụ, topology và SDK thực tế. Không thể suy từ tên “NoSQL” rằng mọi hệ chỉ cung cấp eventual consistency hoặc mọi hệ đều hỗ trợ linearizability.

### 8.2. R + W > N không phải “công thức thần kỳ”

Một nguyên tắc thường được dạy cho hệ quorum có **N replica**, yêu cầu **R replica cho đọc** và **W replica cho ghi**, là:

\[
R + W > N
\]

Khi các tập replica phù hợp, công thức này diễn tả điều kiện **giao nhau** giữa read quorum và write quorum. Nhưng nó **không tự bảo đảm** mọi lần đọc là linearizable:

- Hệ phải định nghĩa read/write acknowledgment tương ứng.
- Replica phải có cơ chế xác định version và giải quyết cập nhật đồng thời.
- Cần xét hinted handoff, sloppy quorum, node thay thế, repair và topology thực tế nếu có.
- Các ca phân vùng mạng, xung đột giữa writer và thời điểm đọc/ghi đồng thời có thể cần giao thức mạnh hơn.

Vì vậy, hãy dựa vào **bảo đảm chính thức của hệ cụ thể**, không lấy bất đẳng thức để thay thế thiết kế hoặc thử nghiệm.

## 9. Xung đột cập nhật: hội tụ thành giá trị nào?

Eventual consistency không nhất thiết chỉ là “replica A chậm hơn replica B”. Trong hệ cho phép nhiều nơi ghi đồng thời, có thể xuất hiện **xung đột**.

Ví dụ hai thiết bị cùng chỉnh mô tả profile khi offline:

~~~text
T0: name = "An"

Thiết bị A: name = "An Nguyễn"
Thiết bị B: name = "An N."
~~~

Khi kết nối lại, hệ phải quyết định giữ giá trị nào, hợp nhất ra sao hoặc yêu cầu người dùng xử lý.

### 9.1. Last-write-wins (LWW)

Quy tắc **ghi cuối thắng** có thể đơn giản và cho phép các replica hội tụ, nhưng đặt ra câu hỏi:

- “Cuối” được xác định bằng timestamp client, timestamp server, version hay thứ tự leader?
- Đồng hồ của các thiết bị có bị lệch không?
- Giá trị bị thua có chứa cập nhật hợp lệ cần giữ không?

LWW có thể phù hợp với một số **tùy chọn hiển thị không quan trọng**, nhưng có nguy cơ mất cập nhật trong giỏ hàng, chỉnh sửa tài liệu hoặc thông tin tài chính nếu dùng thiếu kiểm soát.

### 9.2. Optimistic concurrency control / CAS

Khi cập nhật cùng một record ở nguồn chính, có thể dùng version:

~~~text
Read profile version = 5
Write new profile IF version = 5
  -> nếu thành công, version = 6
  -> nếu xung đột, trả lỗi và yêu cầu tính lại
~~~

CAS giúp ngăn ghi đè mù, nhưng cần engine hỗ trợ **conditional write atomic** ở đúng phạm vi. Nếu người dùng chỉnh nhiều trường trong hai tab, ứng dụng có thể thử merge hoặc trình bày xung đột rõ ràng.

### 9.3. Các phép toán có thể gộp

Một số thao tác có thể được thiết kế sao cho kết quả ít phụ thuộc vào thứ tự:

- **Set union:** thêm một nhãn vào tập nhãn.
- **Max:** giữ timestamp lớn nhất đã thấy cho một chỉ số.
- **Counter có semantics rõ:** hợp nhất các thành phần bộ đếm theo cơ chế phù hợp.
- **CRDT:** kiểu dữ liệu được thiết kế để các replica hợp nhất và hội tụ dù nhận cập nhật theo thứ tự khác nhau, với các điều kiện của thuật toán.

Ví dụ một bộ đếm theo **G-Counter**:

~~~text
Replica A: [A: 3, B: 0]
Replica B: [A: 1, B: 4]

Merge lấy max từng thành phần:
  [A: 3, B: 4]

Giá trị tổng = 7
~~~

Đây là ví dụ trực giác, không phải khẳng định mọi bộ đếm Redis/Cassandra tự là CRDT. Cần triển khai hoặc chọn kiểu dữ liệu phù hợp, quản lý định danh replica và giới hạn của thao tác.

**Quan trọng:** CRDT giúp hội tụ trong một số mô hình dữ liệu nhưng không tự bảo vệ bất biến như “số dư không âm” hoặc “chỉ còn một chỗ ngồi”. Các invariant cần phối hợp toàn cục có thể vẫn cần cơ chế phân xử mạnh.

### 9.4. Khi cần phát hiện xung đột thay vì tự chọn

Với tài liệu biên tập chung, hồ sơ có giá trị pháp lý hoặc thông tin cấu hình quan trọng, đôi khi lựa chọn an toàn là lưu các phiên bản xung đột và yêu cầu người dùng/quy trình nghiệp vụ quyết định. Tự động lấy “bản mới nhất” có thể làm mất sửa đổi hợp lệ.

## 10. Các mức cam kết nhất quán theo trải nghiệm người dùng

Một ứng dụng không nhất thiết phải cho mọi người dùng nhìn cùng phiên bản ở mọi thời điểm. Nhưng trải nghiệm tệ nếu người vừa nhấn **Lưu** lại thấy dữ liệu cũ ngay trên trang của chính mình.

### 10.1. Read-your-writes cho người vừa chỉnh sửa

Giải pháp có thể gồm:

1. Sau ghi thành công, trả lại **document mới nhất** từ nguồn và cập nhật UI ngay.
2. Tạm thời đọc trực tiếp từ **nguồn nhất quán hơn** thay vì replica/index chậm.
3. Dùng **session token/version** để biết bản đọc đã đạt version mong muốn hay chưa.
4. Hiển thị trạng thái **“Đã lưu; kết quả tìm kiếm đang cập nhật”** nếu search có thể trễ.

Ví dụ:

~~~text
Admin lưu tên mới      -> nguồn version 42
Admin xem chi tiết     -> thấy version 42 từ nguồn
Khách tìm kiếm ngay    -> có thể thấy version 41 trong vài giây
Sau đồng bộ            -> search thấy version 42
~~~

Điều này cho người sửa có trải nghiệm nhất quán trong khi vẫn chấp nhận các bản chiếu đọc hội tụ.

### 10.2. Monotonic reads trong phiên

Nếu request 1 thấy version 42 nhưng request 2 bị chuyển sang replica còn version 41, người dùng thấy trạng thái “quay ngược”. Có thể cải thiện bằng:

- Session affinity tới một đường đọc có trạng thái không kém lần trước.
- Version/session token để yêu cầu mức đọc tối thiểu.
- Cache theo phiên với cơ chế invalidation hợp lý.
- Cơ chế đảm bảo đọc đơn điệu mà hệ quản trị có sẵn.

Không phải cách nào cũng có trên mọi NoSQL; phải cân nhắc failover, TTL và chi phí.

### 10.3. Optimistic UI không thay ghi thành công

Ứng dụng có thể tăng số lượt thích trên giao diện trước khi server phản hồi. Nhưng cần:

~~~text
Người dùng nhấn Like
  -> UI tăng số hiển thị tạm
  -> gửi request có ID ổn định
  -> server xác nhận thành công: giữ trạng thái
  -> server thất bại: rollback hoặc hiển thị lỗi
~~~

Nếu việc “like” tạo tác động nghiệp vụ quan trọng (ví dụ bỏ phiếu có hạn mức), không thể chỉ dựa vào số đếm optimistic ở UI.

## 11. Những tình huống thường chấp nhận eventual consistency

### 11.1. Lượt xem, lượt thích và thống kê

Dashboard lượt xem chậm vài giây hoặc vài phút có thể hoàn toàn chấp nhận, nếu không dùng số đó để tính khoản tiền hoặc quota phải chính xác tức thời.

Thiết kế thường gặp:

~~~text
UserViewedArticle
    ↓
Event stream
    ↓
Aggregator
    ↓
Read model: views_per_article
~~~

Nếu hệ phát event theo kiểu **at-least-once**, consumer phải xử lý trùng để tránh đếm gấp đôi nếu hợp đồng đòi độ chính xác. Nếu cho phép số gần đúng, có thể dùng thuật toán thống kê phù hợp và công bố rõ độ sai lệch.

Không được đồng nhất “eventual” với “được phép đếm sai mãi mãi”. **Có độ trễ** và **có sai số** là hai quyết định khác nhau.

### 11.2. News feed và đề xuất

Một bài viết vừa xuất bản có thể mất vài giây trước khi xuất hiện trên feed của tất cả người theo dõi. Dùng fan-out bất đồng bộ hoặc read model theo người dùng có thể giúp giảm độ trễ của thao tác đăng bài.

Điều kiện chấp nhận:

- Bài gốc đã được lưu bền vững.
- Feed có thể được rebuild hoặc bổ sung bản ghi thiếu.
- Không để bài private xuất hiện cho người không có quyền.
- Giao diện không cam kết mọi người nhận cùng một feed tức thì.

### 11.3. Tìm kiếm sản phẩm và tài liệu

Search index có thể chậm cập nhật tên và mô tả, miễn là:

- Có cơ chế hội tụ và theo dõi lag.
- Sản phẩm bị thu hồi/ẩn được xử lý phù hợp với yêu cầu quyền và an toàn.
- Quyết định mua hàng kiểm tra lại nguồn dữ liệu có thẩm quyền.
- Reindex có thể khôi phục bản chiếu bị thiếu.

### 11.4. Hồ sơ người dùng công khai

Đổi avatar, tiểu sử hoặc tên hiển thị có thể lan dần qua cache/CDN và read model. Nhưng nếu thay đổi liên quan đến **mật khẩu, quyền truy cập hoặc khóa bảo mật**, không nên đưa vào cùng chính sách trễ như avatar.

### 11.5. Giỏ hàng ngoại tuyến

Giỏ hàng trên nhiều thiết bị có thể cho phép chỉnh offline và hợp nhất sau. Tuy nhiên, quy tắc merge phải được thiết kế:

- Cộng số lượng hay dùng giá trị lớn nhất?
- Xóa item có thắng cập nhật offline cũ không?
- Có giữ lịch sử thao tác và version không?
- Khi checkout, tồn kho và giá có được xác nhận lại không?

“Cứ LWW” không đủ với thao tác thêm/xóa item không giao hoán. Giỏ hàng có thể hội tụ theo chính sách riêng, nhưng checkout vẫn cần bất biến mạnh hơn.

## 12. Những tình huống không nên chỉ dựa vào eventual consistency

### 12.1. Sổ cái và thanh toán

Nếu hai request cùng kiểm tra số dư 100 rồi trừ 80:

~~~text
Client A đọc balance = 100
Client B đọc balance = 100
Client A ghi balance = 20
Client B ghi balance = 20
~~~

Kết quả có thể mất một lần trừ, hoặc nếu xử lý theo kiểu cộng delta không kiểm soát có thể cho số dư âm. Dữ liệu các replica hội tụ về cùng giá trị **không chứng minh giá trị đó đúng theo bất biến**.

Với tiền, thanh toán và sổ cái cần cơ chế giao dịch, bất biến nguồn, idempotency, phân xử đồng thời và đối soát. Một bộ đọc analytics về giao dịch có thể eventual; **lệnh ghi cam kết chuyển tiền** không thể dựa vào bản sao cũ tùy tiện.

### 12.2. Bán sản phẩm có tồn kho giới hạn

Nếu hai vùng đều thấy “còn 1 sản phẩm” từ replica chậm rồi cùng xác nhận bán, có thể oversell. Bài toán cần quyết định một trong các chiến lược:

- Một nơi phân xử giữ hàng bằng transaction/conditional write.
- Phân chia trước quota/tồn kho theo vùng với giới hạn không thể vượt; chuyển quota được quản lý bằng cơ chế phù hợp.
- Cho phép backorder/oversell có kiểm soát nếu **nghiệp vụ thật sự cho phép**, và xử lý bù trừ minh bạch.

Chỉ chọn eventual vì nó giúp ghi nhanh không giải quyết hậu quả giao hàng thất bại.

### 12.3. Cấp phát tên hoặc tài nguyên duy nhất

Hai người cùng tạo username “minh” trên hai replica chưa hội tụ. Nếu cả hai đều được xác nhận thành công, bất biến **username duy nhất** bị vi phạm.

Cần một cơ chế unique/conditional write với phạm vi nhất quán phù hợp, hoặc chấp nhận quy trình giữ chỗ tạm rồi xác nhận khi có phân xử trung tâm. Nếu dùng phương án thứ hai, không được báo “đã sở hữu username vĩnh viễn” trước khi hoàn tất.

### 12.4. Thu hồi quyền và bảo mật

Nếu quyền truy cập bị thu hồi lúc 10:00 nhưng hệ tìm kiếm dùng ACL cũ đến 10:05, người bị thu hồi có thể xem dữ liệu nhạy cảm trong khoảng đó.

Có thể chấp nhận độ trễ hiển thị (ví dụ tên phòng tài liệu chưa biến mất), nhưng **đường thực thi quyền truy cập** cần mức nhất quán đáp ứng chính sách bảo mật. Các lựa chọn gồm kiểm tra quyền từ một dịch vụ authoritative, token phiên có vòng đời ngắn cộng cơ chế revoke, hoặc cơ chế đồng bộ quyền chặt hơn.

Không nên lưu ACL chỉ trong bản chiếu eventual rồi tuyên bố dữ liệu được bảo vệ nếu hậu quả truy cập sai là không chấp nhận được.

## 13. Saga và giao dịch nhiều dịch vụ: eventual consistency có điều kiện

Một workflow đặt hàng đi qua nhiều dịch vụ:

~~~text
Order Service
    ↓
Inventory Service
    ↓
Payment Service
    ↓
Shipping Service
~~~

Không phải hệ thống nào cũng có thể thực hiện một transaction ACID xuyên tất cả dịch vụ, đặc biệt khi còn cổng thanh toán bên ngoài. Một lựa chọn là **saga**: mỗi bước có transaction cục bộ và nếu bước sau thất bại, các thao tác bù trừ được kích hoạt theo quy tắc nghiệp vụ.

Ví dụ trạng thái:

~~~text
PENDING
   ├── inventory reserved
   ├── payment authorized
   └── order CONFIRMED

Nếu payment thất bại:
   └── release reserved inventory
       -> order CANCELLED
~~~

Một saga có thể cho phép trạng thái giữa các dịch vụ tạm chưa đồng bộ. Nhưng đó không phải lời bảo đảm rằng **mọi sai lệch cuối cùng đều được khôi phục an toàn**:

- Bù trừ có thể thất bại và phải retry.
- Một số hành động không thể hoàn tác (email đã gửi, gói hàng đã vận chuyển).
- Nếu không idempotent, retry có thể tạo tác dụng phụ lặp lại.
- Có những điều kiện phải được bảo vệ ngay tại bước cục bộ, ví dụ giữ số lượng hàng không vượt khả dụng.

**Saga quản lý quy trình nhiều bước**, còn các bất biến quan trọng vẫn cần được bảo vệ ở những điểm quyết định tương ứng.

### 13.1. Trạng thái trung gian phải là trạng thái nghiệp vụ hợp lệ

Không nên chỉ có:

~~~text
PAID / NOT_PAID
~~~

khi hệ thực tế còn đang chờ cổng thanh toán hoặc xử lý hoàn tiền. Có thể cần:

~~~text
CREATED
PENDING_PAYMENT
PAYMENT_AUTHORIZED
CONFIRMED
CANCEL_PENDING
CANCELLED
REFUND_PENDING
REFUNDED
~~~

Những trạng thái này cho phép hệ diễn giải một khoảng “chưa hội tụ” **mà không nói sai với người dùng**. Ví dụ, API không được trả “Đã hoàn tiền” chỉ vì đã gửi yêu cầu hoàn tiền nhưng chưa có kết quả xác nhận cần thiết.

## 14. Độ trễ hội tụ phải đo được

Nếu nghiệp vụ cho phép dữ liệu trễ 5 giây, hệ phải biết **thực tế đang trễ bao nhiêu**.

### 14.1. Các loại độ trễ

Ví dụ một sự kiện thay đổi sản phẩm:

~~~text
sourceCommittedAt = 10:00:00.020
publishedAt       = 10:00:00.080
consumedAt        = 10:00:00.300
indexedAt         = 10:00:00.450
searchVisibleAt   = 10:00:01.000
~~~

Có thể đo:

- **Publish lag:** commit nguồn đến lúc sự kiện sẵn sàng.
- **Consumer lag:** sự kiện sẵn sàng đến lúc consumer nhận/xử lý.
- **Index lag:** consumer xử lý đến khi bản chiếu nhận trạng thái.
- **Visibility lag:** dữ liệu đã ghi vào index đến khi truy vấn thấy được.
- **End-to-end staleness:** commit nguồn đến khi người đọc từ bản chiếu thấy version mới.

Không phải sản phẩm nào cũng cung cấp toàn bộ timestamp trên. Đo theo đồng hồ các máy khác nhau phải cân nhắc clock skew; một số độ trễ có thể suy từ sequence/watermark thay vì so sánh timestamp trực tiếp.

### 14.2. Cần nhiều chỉ số hơn độ trễ trung bình

Một dashboard chỉ ghi “độ trễ trung bình 1 giây” có thể che giấu 1% sự kiện chậm 30 phút.

Các chỉ báo hữu ích:

| Nhóm | Ví dụ |
| --- | --- |
| Thời gian hội tụ | p50, p95, p99 của end-to-end lag |
| Backlog | Số event chưa xử lý, tuổi event cũ nhất |
| Tính đầy đủ | Phần trăm aggregate có projection version bắt kịp source |
| Lỗi | Số event retry, dead-letter, lỗi index |
| Thứ tự | Số version gap, event cũ bị từ chối, xung đột |
| Khôi phục | Thời gian replay backlog sau outage, thời gian rebuild |
| Quyền | Tỷ lệ và độ trễ thay đổi ACL/visibility quan trọng |

Ngoài ngưỡng cảnh báo tức thời, cần định nghĩa **error budget** hoặc mức suy giảm được phép. Nếu 99% event hội tụ trong 5 giây nhưng phần còn lại đôi khi mất một ngày, có thể vẫn không phù hợp với quy trình xuất bản hoặc kiểm duyệt.

### 14.3. Cơ chế đối soát

Một pipeline thành công theo log không bảo đảm bản chiếu không thiếu dữ liệu lâu dài. Có thể có bug, sự kiện bị bỏ qua hoặc mapping không tương thích.

Một job reconciliation có thể:

1. Chọn từng phân đoạn dữ liệu nguồn theo thời gian, ID hoặc tenant.
2. So sánh version/checksum/số lượng với bản chiếu.
3. Ghi lại những aggregate bị thiếu, quá cũ hoặc thừa.
4. Lấy trạng thái authoritative từ nguồn để sửa projection.
5. Báo cáo độ lệch và theo dõi đến khi phục hồi.

Ví dụ:

~~~text
Product P10:
  Source version     = 43
  Search version     = 41
  Status             = STALE
  Repair action      = reindex P10 from source
~~~

Đối soát nên idempotent và không gây ghi đè version mới bằng bản snapshot cũ trong lúc source tiếp tục cập nhật.

## 15. Khi dữ liệu chậm vượt ngưỡng: hệ phải làm gì?

Eventual consistency có thể được chấp nhận ở trạng thái khỏe, nhưng **outage hoặc backlog** có thể khiến độ trễ vượt xa dự kiến.

Ví dụ search index chậm 30 phút:

| Tình huống | Hành vi có thể lựa chọn |
| --- | --- |
| Bài viết mới chưa tìm thấy | Hiển thị thông báo indexing, cho tác giả truy cập qua link trực tiếp |
| Danh sách sản phẩm có giá cũ | Xác nhận lại giá tại product/checkout source |
| Search index chứa sản phẩm đã ẩn | Filter trạng thái/quyền ở nguồn đáng tin hoặc ngừng phục vụ đoạn dữ liệu rủi ro |
| Dashboard lượt xem chậm | Hiển thị “Dữ liệu cập nhật đến 09:30” |
| Hàng đợi cập nhật đầy | Giới hạn tải, mở rộng consumer, retry và điều tra sự cố |

Không phải lúc nào cũng đúng khi “fallback sang DB nguồn” cho mọi truy vấn. Full-text search hoặc aggregate trên hàng triệu bản ghi có thể không được nguồn chính hỗ trợ với tải tương đương. Khi fallback không an toàn hoặc quá tốn, **degrade gracefully** (giới hạn tính năng, thông báo dữ liệu cũ, trả lỗi rõ ràng) có thể tốt hơn truy vấn quét gây sập nguồn.

### 15.1. Quy tắc vận hành cho lỗi kéo dài

Một quy trình rõ ràng nên chỉ định:

- Ai nhận cảnh báo khi lag vượt ngưỡng?
- Khi nào tạm ngừng nhận thao tác có phụ thuộc dữ liệu mới?
- Cách phân biệt một replica chậm với sự kiện đã mất.
- Khi nào có thể replay; khi nào phải rebuild toàn bộ index.
- Cách bảo đảm bản chiếu không vô tình tái xuất dữ liệu đã xóa.
- Cách thông báo cho người dùng khi dịch vụ suy giảm.

Hệ thống càng phụ thuộc vào dữ liệu eventual, **khả năng quan sát và tự phục hồi** càng phải được xem như một phần của tính năng, không phải công việc làm sau.

## 16. CAP và đánh đổi tính nhất quán: hiểu đúng phạm vi

CAP thường được dùng để thảo luận về hệ phân tán khi có **network partition**. Ý chính: dưới những điều kiện và định nghĩa nhất quán/sẵn sàng cụ thể, một hệ không thể đồng thời bảo đảm mọi yêu cầu vẫn được phục vụ và duy trì một số bảo đảm nhất quán mạnh trong khi các phía không liên lạc được với nhau.

Không nên rút gọn thành “NoSQL luôn chọn AP còn SQL luôn chọn CP”, vì:

- Nhiều NoSQL cung cấp cấu hình hoặc thao tác có bảo đảm mạnh.
- Cơ sở dữ liệu quan hệ phân tán cũng phải giải quyết partition.
- Một sản phẩm có thể có nhiều mức consistency cho các loại thao tác.
- CAP không thay thế phân tích **latency, durability, conflict resolution và invariant** trong lúc mạng bình thường.

### 16.1. Hai lựa chọn trong một phân vùng mạng

Giả sử hai vùng không liên lạc:

**Lựa chọn A: Tiếp tục chấp nhận ghi ở cả hai vùng.**

- Ưu điểm: duy trì khả năng nhận ghi tại chỗ.
- Rủi ro: có thể có xung đột; cần quy tắc merge và chấp nhận dữ liệu tạm khác nhau.
- Phù hợp hơn với thao tác có thể gộp an toàn hoặc nghiệp vụ chịu được giải quyết sau.

**Lựa chọn B: Chỉ phía có quyền phân xử/quorum mới được ghi.**

- Ưu điểm: có thể bảo vệ bất biến/độ nhất quán theo giao thức được thiết kế.
- Rủi ro: phía còn lại phải từ chối hoặc trì hoãn một số thao tác.
- Phù hợp hơn với cập nhật cần một kết quả duy nhất, như giữ chỗ độc quyền.

Trong thực tế, lựa chọn có thể thực hiện **theo loại dữ liệu và loại thao tác**: lượt xem có thể chấp nhận ghi offline rồi gộp; thanh toán phải được xác nhận qua đường ghi có tính phân xử phù hợp.

## 17. Thiết kế theo lớp: bất biến mạnh, bản đọc mềm

Một kiến trúc thường hữu ích:

~~~mermaid
flowchart TD
    C["Client / API"] --> W["Command / Write handler"]
    W --> A[("Nguồn trạng thái + invariant")]
    A --> E["Outbox / Event log"]
    E --> P1[("Search projection")]
    E --> P2[("Feed projection")]
    E --> P3[("Analytics projection")]
    R["Read API"] --> P1
    R --> P2
    R --> P3
    R -. "Đọc authoritative khi cần" .-> A
~~~

Đây là một biến thể **CQRS/read model separation**, không có nghĩa phải áp dụng toàn bộ CQRS hoặc event sourcing cho mọi ứng dụng.

Các nguyên tắc:

1. **Nguồn trạng thái** chịu trách nhiệm bất biến đã phân định.
2. **Event/outbox** là đường truyền đáng tin cậy về các thay đổi đã commit.
3. **Projection** phục vụ các kiểu đọc khác nhau và có thể eventual.
4. **Quy tắc đồng bộ** phải xử lý duplicate, retry, out-of-order và delete.
5. **API nghiệp vụ** không đưa ra quyết định không thể hoàn tác dựa trên projection chưa được xác minh.

Nếu một projection bị xóa, có thể dựng lại từ nguồn và log phù hợp. Nếu nguồn bị mất, chỉ dựa vào projection có thể không đủ để khôi phục mọi bất biến và lịch sử.

### 17.1. Event sourcing không bắt buộc

Event sourcing lưu chuỗi sự kiện như nguồn sự thật; CQRS tách cách ghi và cách đọc. Eventual consistency thường xuất hiện ở read projections, nhưng:

- Có thể dùng outbox trên một database state-based bình thường mà không cần event sourcing.
- Có thể dùng event sourcing nhưng một số đường đọc vẫn yêu cầu nhất quán mạnh hoặc đọc trực tiếp aggregate.
- Không phải mọi nghiệp vụ cần tách hàng loạt read model ngay từ đầu.

Chỉ thêm độ phức tạp khi có lợi ích đo được về truy vấn, khả năng mở rộng hoặc mô hình nghiệp vụ.

## 18. Kiểm thử eventual consistency: kiểm tra hội tụ và hành vi lúc chưa hội tụ

Một bộ test chỉ kiểm tra “sau 2 giây search thấy tên mới” có thể bỏ sót lỗi hiếm. Cần thử **cả trạng thái chuyển tiếp, lỗi và khôi phục**.

### 18.1. Test sự kiện trễ

~~~text
1. Nguồn commit version 42.
2. Chủ động làm chậm consumer trong môi trường test.
3. Xác nhận API quản trị thấy version 42.
4. Xác nhận search có thể còn version 41 nhưng không lộ dữ liệu trái quyền.
5. Cho consumer chạy tiếp.
6. Xác nhận search cuối cùng thấy version 42.
~~~

### 18.2. Test event đảo thứ tự và lặp

~~~text
Gửi tới consumer:
  ProductUpdated version 43
  ProductUpdated version 42
  ProductUpdated version 43 lần nữa
~~~

Nếu event mang trạng thái đầy đủ và dùng version guard, projection cuối cùng phải ở **version 43**. Nếu event mang delta, consumer phải phát hiện thiếu thứ tự hoặc có quy tắc xử lý đúng riêng.

### 18.3. Test xóa và “hồi sinh”

~~~text
1. Product version 50 được tạo.
2. Delete version 51 đã áp dụng.
3. Update version 50 đến rất muộn.
4. Projection không được tạo lại product từ event cũ.
~~~

Test này quan trọng với quyền truy cập, bài viết bị gỡ và dữ liệu phải xóa theo quy định.

### 18.4. Test outage và replay

Tắt consumer hoặc chặn kết nối tới index trong môi trường thử. Tiếp tục ghi nguồn, sau đó khôi phục pipeline và xác nhận:

- Backlog không mất.
- Các event xử lý idempotent.
- Độ trễ quay về ngưỡng bình thường.
- Projection hội tụ bằng version/checksum với nguồn.
- Thời gian recovery đáp ứng mục tiêu vận hành.

### 18.5. Test invariant xuyên nhóm

Với tồn kho còn 1, chạy đồng thời nhiều yêu cầu đặt mua qua các đường đọc có thể trễ. Kết quả phải thỏa bất biến ở nguồn: chỉ số đơn được xác nhận phù hợp với chính sách giữ hàng; những yêu cầu khác nhận trạng thái chờ/thất bại hoặc backorder theo hợp đồng nghiệp vụ.

**Đừng chỉ test sự hội tụ của dữ liệu; hãy test những quyết định đã được đưa ra trong lúc dữ liệu chưa hội tụ.**

## 19. Bảng ra quyết định: khi nào cho phép eventual?

Trước khi chọn consistency model, trả lời từng câu:

| Câu hỏi | Nếu câu trả lời là “có” | Hướng đánh giá |
| --- | --- | --- |
| Dữ liệu là bản chiếu có thể rebuild? | Mất bản chiếu không đồng nghĩa mất nguồn | Eventual thường dễ chấp nhận hơn |
| Người dùng có thể chấp nhận hiển thị chậm? | Trễ không phá cam kết sản phẩm | Đặt SLO và UI về freshness |
| Đọc dữ liệu cũ có thể gây tổn thất/vi phạm quyền? | Quyết định từ bản cũ có thể nguy hiểm | Đọc authoritative hoặc bảo đảm mạnh hơn |
| Có bất biến xuyên nhiều aggregate? | Các bản ghi phải phối hợp để đúng | Xác định transaction/conditional write/saga |
| Có nhiều writer độc lập/offline? | Có thể sinh xung đột | Định nghĩa version/merge/conflict resolution |
| Có thể replay và sửa sai lệch? | Projection có đường phục hồi | Outbox/CDC, idempotency, reconciliation |
| Đã có giới hạn độ trễ và cảnh báo? | Có khả năng kiểm soát staleness | Cho phép eventual trong phạm vi đo được |
| Có tình huống không được phép tạm sai? | Bất biến cần bảo vệ ngay | Tách thao tác ghi/đọc với bảo đảm phù hợp |

### 19.1. Cây quyết định đơn giản

~~~mermaid
flowchart TD
    A["Thao tác/đường đọc này có thể thấy dữ liệu cũ?"] -->|"Không"| B["Cần đường đọc hoặc phân xử nhất quán phù hợp"]
    A -->|"Có"| C{"Dữ liệu cũ có thể gây quyết định không thể sửa?"}
    C -->|"Có"| D["Kiểm tra lại nguồn trước khi cam kết"]
    C -->|"Không"| E{"Có pipeline hội tụ + replay + giám sát?"}
    E -->|"Không"| F["Thiết kế đường đồng bộ và phục hồi trước"]
    E -->|"Có"| G["Đặt SLO độ trễ và thử lỗi thực tế"]
~~~

Đây là công cụ suy luận, không phải chứng chỉ an toàn cho một kiến trúc. Độ nghiêm trọng, ràng buộc pháp lý và hợp đồng kỹ thuật thực tế vẫn quyết định lựa chọn.

## 20. Những sai lầm phổ biến

### 20.1. Dùng eventual cho mọi dữ liệu vì “NoSQL vốn như vậy”

NoSQL là tập hợp nhiều mô hình và sản phẩm. Chọn mức consistency phải xuất phát từ **invariant và access pattern**, không phải nhãn công nghệ.

### 20.2. Coi độ trễ đồng bộ là lỗi hiếm có thể bỏ qua

Nếu ứng dụng có read model bất đồng bộ, tồn tại khoảng chưa hội tụ **ngay cả khi hệ khỏe**. UI, API và nghiệp vụ phải xử lý trạng thái này như một phần thiết kế bình thường.

### 20.3. Không phân biệt “trạng thái đang xử lý” với “đã hoàn thành”

Đã gửi lệnh hoàn tiền không có nghĩa đã hoàn tiền; đã gửi email vào queue không nghĩa người dùng nhận email. Dùng state machine và tên trạng thái chính xác.

### 20.4. Dùng timestamp của client làm thứ tự phiên bản

Đồng hồ lệch và cập nhật offline có thể khiến dữ liệu cũ được coi mới. Cần cơ chế version hoặc conflict resolution có định nghĩa rõ.

### 20.5. Dùng sự kiện delta nhưng bỏ qua version trung gian

Với event “tăng 1”, version 10 và 12 không đủ để suy ra thiếu version 11; bỏ qua v11 gây sai tổng. Delta phải được xử lý đúng thứ tự/không thiếu hoặc dùng mô hình gộp khác.

### 20.6. Chỉ nhân bản, không có đường đối soát

Replication có thể tạo nhiều bản sao của cùng một lỗi hoặc cập nhật sai. Bản chiếu cần replay/rebuild; dữ liệu nguồn cần backup/restore theo yêu cầu.

### 20.7. Cache hoặc index cũ quyết định quyền

ACL đã thu hồi có thể vẫn tồn tại trong cache. Đường bảo vệ tài nguyên phải đáp ứng yêu cầu thu hồi, không chỉ hy vọng cache hết hạn sớm.

### 20.8. Tất cả bản ghi đọc đều “có thể trễ”

Trong một giao diện, các trường có thể có rủi ro khác nhau: tên sản phẩm trễ thường ít nghiêm trọng hơn giá thanh toán hoặc quyền xem. Cần phân loại **theo trường, thao tác và hậu quả**, không chỉ theo table.

### 20.9. Không tính đến thay đổi schema và rebuild

Khi projection schema thay đổi, dữ liệu cũ có thể không phù hợp. Phải có version schema, cách reindex/backfill, chuyển traffic và rollback.

### 20.10. Bỏ qua tình huống lỗi kéo dài

“Sau cùng sẽ đồng bộ” không có ý nghĩa nếu pipeline chết cả tuần. Cần đo tuổi backlog, cảnh báo, retry có kiểm soát và kịch bản phục hồi.

## 21. Quy trình thực hành áp dụng cho một tính năng mới

**Bước 1 — Viết câu lệnh nghiệp vụ chính xác.** Ví dụ: “Người bán cập nhật mô tả, trang chi tiết của chính họ phải thấy bản mới ngay; search toàn hệ thống có thể trễ tối đa vài giây khi bình thường.”

**Bước 2 — Liệt kê bất biến.** Ví dụ: “Không có sản phẩm PRIVATE được đọc bởi người không có quyền; checkout không dùng giá chậm của index để chốt hóa đơn.”

**Bước 3 — Chọn nguồn có thẩm quyền.** Mỗi quyết định cần biết hệ nào bảo vệ invariant. Tránh để hai hệ cùng tuyên bố mình là nguồn cuối cùng mà không có giao thức giải quyết xung đột.

**Bước 4 — Tách read model nếu có lợi ích.** Chỉ tạo bản chiếu khi nó giảm chi phí truy vấn, tăng hiệu năng hoặc hỗ trợ access pattern quan trọng. Quyết định độ trễ được phép cho từng bản chiếu.

**Bước 5 — Xây đường cập nhật đáng tin cậy.** Sử dụng transaction/outbox/CDC, event ID, aggregate ID, version, retry và xử lý xóa theo khả năng hệ nguồn.

**Bước 6 — Thiết kế UX của độ trễ.** Chọn read-your-writes, trạng thái đang đồng bộ, timestamp “cập nhật đến lúc”, kiểm tra lại nguồn khi thực thi thao tác quan trọng.

**Bước 7 — Đặt SLO và theo dõi.** Đo lag p95/p99, tuổi backlog, tỷ lệ projection trễ và lỗi theo tenant/loại event.

**Bước 8 — Tạo reconciliation và playbook.** Phải có cách so bản chiếu với nguồn, replay/backfill, xử lý sự kiện cũ và khôi phục sau outage.

**Bước 9 — Kiểm thử lỗi.** Trễ, trùng, đảo thứ tự, mất kết nối, failover, xóa rồi replay, đọc quyền cũ, tranh chấp đồng thời ở invariant.

**Bước 10 — Quyết định theo rủi ro thật.** Nếu hậu quả đọc/ghi sai lớn hơn lợi ích giảm độ trễ hay tăng availability, không chọn eventual ở đường quyết định đó.

## 22. Bài tập thực hành

### Bài 1: Phân loại dữ liệu

Một hệ học trực tuyến có:

1. Số lượt xem bài học.
2. Điểm thi cuối khóa dùng để cấp chứng chỉ.
3. Gợi ý bài học liên quan.
4. Quyền truy cập khóa học trả phí.
5. Avatar người dùng.

**Câu hỏi:** Những dữ liệu nào có thể chấp nhận eventual, dữ liệu nào phải bảo vệ chặt hơn?

**Gợi ý:** Lượt xem, gợi ý và avatar thường cho phép đọc chậm. Điểm cấp chứng chỉ và quyền truy cập có các bất biến quan trọng; quyết định cấp chứng chỉ/cho phép xem phải dựa trên nguồn có bảo đảm phù hợp. Một dashboard điểm thi có thể chậm, nhưng nguồn ghi điểm chính thức không được sai.

### Bài 2: Sự kiện đảo thứ tự

Product P10 có:

~~~text
v10: name = "A"
v11: name = "B"
v12: name = "C"
~~~

Indexer nhận v12 rồi v11; cả hai sự kiện chứa **full state**.

**Câu hỏi:** Vì sao ghi đè mù tạo kết quả sai? Cách sửa?

**Gợi ý:** Ghi v11 sau v12 làm bản chiếu về B. Ghi kèm version và chỉ áp dụng trạng thái mới hơn; event trùng/đến muộn không được hạ version.

### Bài 3: Sự kiện delta

Một bộ đếm bắt đầu từ 10. Hai event hợp lệ có tác dụng “+1” ở version 20 và 21. Consumer nhận version 21 trước.

**Câu hỏi:** Có thể áp dụng quy tắc “chỉ nhận version mới nhất, bỏ version cũ” như full state không?

**Gợi ý:** Không. Nếu bỏ v20, kết quả có thể thiếu một lần tăng. Cần bảo đảm xử lý mọi delta đúng một lần theo semantics mong muốn, phục hồi gap, hoặc dùng mô hình gộp/aggregate khác.

### Bài 4: Giỏ hàng trên hai thiết bị

Ban đầu giỏ hàng có 1 sản phẩm P10. Thiết bị A offline tăng lên 2; thiết bị B offline xóa P10. Khi đồng bộ, nếu dùng LWW, điều gì xảy ra?

**Gợi ý:** Kết quả phụ thuộc quy tắc chọn bản thắng; một thao tác hợp lệ có thể mất. Hãy xác định ý định nghiệp vụ, event/operation identity, conflict policy và cách trình bày cho người dùng khi không merge tự động an toàn.

### Bài 5: Bản chiếu tìm kiếm bị chậm

Người bán đổi sản phẩm P10 sang PRIVATE lúc 09:00; search index chậm đến 09:03.

**Câu hỏi:** Cách nào bảo đảm khách không thể xem nội dung private trong khoảng 3 phút?

**Gợi ý:** Không chỉ dựa vào index. Search/API chi tiết phải kiểm tra quyền từ nguồn đáng tin hoặc cơ chế thu hồi mạnh đáp ứng yêu cầu; snippet/search result cũng cần kiểm soát quyền. Có thể tạm không hiển thị kết quả khi không xác minh được quyền.

### Bài 6: Thanh toán hai lần

Client gọi API thanh toán, server đã xử lý nhưng phản hồi bị mất; client retry.

**Câu hỏi:** Eventual consistency có giúp tránh thu tiền hai lần không?

**Gợi ý:** Không. Cần idempotency key ổn định, quy tắc transaction/ghi có điều kiện và cách tra cứu kết quả đã xử lý ở nguồn đáng tin. Bản chiếu giao diện thanh toán có thể trễ, nhưng hành động thu tiền phải đúng.

### Bài 7: Tính SLO

Trong 10.000 thay đổi, 9.950 thay đổi xuất hiện trong search trước 5 giây, 50 thay đổi lâu hơn 5 giây.

**Câu hỏi:** Tỷ lệ hội tụ trong 5 giây là bao nhiêu? Có đạt SLO 99% không?

**Gợi ý:** \(9.950 / 10.000 = 99,5\%\), nên đạt SLO 99% trên tập đo này. Tuy nhiên, cần thêm thông tin về 50 trường hợp chậm, đặc biệt nếu chúng kéo dài nhiều giờ hoặc ảnh hưởng thay đổi quyền.

### Bài 8: Sự kiện xóa đến trước sự kiện sửa

Một document bị xóa ở version 16 nhưng sự kiện update version 15 đến trễ. Consumer đã xóa document khỏi index và mất thông tin về version 16.

**Câu hỏi:** Có rủi ro gì? Có thể thiết kế thế nào?

**Gợi ý:** Event v15 có thể tạo lại document cũ. Dùng tombstone/version hoặc điều kiện đối chiếu nguồn, giữ khả năng từ chối event cũ ngay cả khi document đã bị xóa khỏi giao diện tìm kiếm.

### Bài 9: Lựa chọn availability khi đứt mạng

Ứng dụng có hai tính năng:

1. Ghi thêm một lượt xem bài.
2. Giữ chỗ cuối cùng của chuyến xe.

Hai datacenter bị chia cắt nhưng mỗi bên vẫn có người dùng gửi yêu cầu.

**Câu hỏi:** Nên đánh đổi như nhau không?

**Gợi ý:** Lượt xem có thể ghi tại chỗ rồi hợp nhất nếu có cơ chế tránh đếm trùng; giữ chỗ cuối cùng phải có một nơi phân xử hoặc trả trạng thái chờ/từ chối trên phía không thể xác nhận. Chọn theo invariant và hậu quả, không chỉ theo yêu cầu availability chung.

## 23. Kết luận

**Nhất quán sau cùng là một lựa chọn kiến trúc có điều kiện, không phải sự cho phép dữ liệu sai vô thời hạn.** Nó phù hợp khi độ trễ quan sát có hậu quả chấp nhận được, những cập nhật có thể hội tụ theo quy tắc rõ ràng và hệ có đường xử lý retry, trùng, đảo thứ tự, xóa và đối soát.

Trong mô hình NoSQL, hãy xác định **nhóm dữ liệu và những bất biến phải đúng ngay**. Bảo vệ chúng bằng khả năng ghi có điều kiện, giao dịch, phân xử hoặc quy trình nghiệp vụ phù hợp. Các bản chiếu đọc như search, feed, cache và analytics có thể được cập nhật bất đồng bộ nếu không được dùng để đưa ra cam kết nguy hiểm dựa trên dữ liệu cũ.

Cuối cùng, quyết định chấp nhận eventual consistency chỉ hoàn chỉnh khi đã xác định **độ trễ được phép, hành vi người dùng trong lúc chưa hội tụ, cơ chế phục hồi và chỉ số vận hành**. Một hệ thống có thể nhất quán sau cùng mà vẫn chính xác về nghiệp vụ, nếu ranh giới quyết định quan trọng được thiết kế đúng.
