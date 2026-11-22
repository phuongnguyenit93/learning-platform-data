# Đồng bộ dữ liệu gốc với kho tìm kiếm, vector hoặc phân tích

## 1. Vì sao một hệ thống lại có nhiều nơi chứa cùng dữ liệu?

Giả sử một ứng dụng thương mại điện tử quản lý sản phẩm trong một cơ sở dữ liệu giao dịch. Ứng dụng cần đáp ứng đồng thời các yêu cầu:

- Cập nhật giá, tên, trạng thái bán và tồn kho của sản phẩm một cách đáng tin cậy.
- Tìm sản phẩm theo từ khóa, lỗi gõ, bộ lọc và mức độ liên quan.
- Gợi ý sản phẩm theo ý nghĩa của mô tả hoặc nội dung người dùng tìm kiếm.
- Phân tích doanh thu, tỷ lệ chuyển đổi và mức tồn kho theo ngày, danh mục, khu vực.

Mỗi tác vụ có kiểu truy vấn khác nhau. Một cơ sở dữ liệu quan hệ hoặc document database có thể phù hợp để **ghi và kiểm soát dữ liệu nghiệp vụ**, nhưng kho tìm kiếm toàn văn, cơ sở dữ liệu vector và hệ phân tích lại có các cấu trúc lập chỉ mục/tổ chức dữ liệu được tối ưu cho những câu hỏi chuyên biệt.

Ví dụ kiến trúc:

~~~text
                    Ứng dụng / API
                          |
                    Ghi nghiệp vụ
                          |
                          v
                 Database nguồn chính
                 (Product, Order, ...)
                          |
                  Thay đổi dữ liệu
                          |
                  CDC / Outbox / Event
                          |
                  Dòng sự kiện bền vững
                          |
           +--------------+---------------+
           |              |               |
           v              v               v
     Search index    Embedding pipeline   Analytics pipeline
           |              |               |
           v              v               v
     Kho tìm kiếm      Kho vector        Kho phân tích
     Từ khóa, lọc      Tương đồng        SQL/OLAP, báo cáo
~~~

Điểm cần làm rõ: **ba kho phía dưới là các hình chiếu (projection/read model) được dẫn xuất từ dữ liệu gốc**. Chúng có thể chứa bản sao toàn bộ hoặc một phần dữ liệu, chuyển đổi cấu trúc, ghép thêm trường, chia thành các đoạn văn bản (chunk), hoặc tổng hợp thành các con số.

Đồng bộ dữ liệu không chỉ là “copy một bản ghi sang nơi khác”. Hệ thống phải xác định:

1. **Nguồn sự thật (source of truth)** nằm ở đâu?
2. Làm sao biết dữ liệu nguồn đã thay đổi?
3. Sự thay đổi được biến đổi thế nào cho từng kho đích?
4. Làm sao xử lý lỗi, sự kiện trùng, đến muộn hoặc sai thứ tự?
5. Xóa ở nguồn có xóa hoặc vô hiệu hóa đúng mọi bản sao không?
6. Làm sao biết kho đích đã đủ mới, đầy đủ và nhất quán để phục vụ yêu cầu?

Bài học sử dụng ví dụ sản phẩm để giải thích các nguyên tắc có thể áp dụng cho NoSQL document, search engine, vector database và hệ phân tích. Những sản phẩm cụ thể như MongoDB, Elasticsearch/OpenSearch, các vector store hoặc data warehouse có khả năng và API khác nhau; ví dụ công nghệ chỉ nhằm minh họa cơ chế.

## 2. Phân biệt nguồn dữ liệu gốc và kho dữ liệu dẫn xuất

### 2.1. Source of truth là nơi quyết định trạng thái nghiệp vụ

Giả sử sản phẩm `P100` có dữ liệu:

~~~json
{
  "productId": "P100",
  "name": "Tai nghe không dây",
  "description": "Chống ồn chủ động, pin 30 giờ",
  "priceCents": 149900,
  "currency": "USD",
  "stock": 12,
  "status": "ACTIVE",
  "version": 17
}
~~~

Nếu `P100` được bán hết, thao tác giảm tồn kho phải tuân thủ quy tắc nghiệp vụ tại nguồn quản lý tồn kho. Cơ sở dữ liệu nguồn ghi nhận bản cập nhật thành công, rồi những kho chuyên dụng mới nhận được sự thay đổi.

**Kho tìm kiếm hoặc vector không nên mặc định là nơi xác nhận còn hàng hay giá thanh toán cuối cùng**. Chỉ mục có thể chưa nhận bản cập nhật gần nhất; kết quả tìm kiếm phản ánh phiên bản dữ liệu đã được đồng bộ, không phải cam kết giao dịch trực tiếp.

Các hệ phân tích cũng thường cập nhật chậm hơn nguồn và có thể dùng cách tổng hợp khác với dữ liệu giao dịch. Nếu con số trên dashboard thay đổi chậm vài phút là chấp nhận được, điều đó cần được tuyên bố rõ; nếu một nghiệp vụ yêu cầu chốt tiền tức thời, không nên lấy từ một bảng tổng hợp có độ trễ không được kiểm soát.

### 2.2. Read model có thể có schema khác nguồn

Bản ghi sản phẩm ở nguồn có thể chuẩn hóa hoặc chia thành nhiều thực thể:

~~~text
products:      product_id, name, description, category_id, status
prices:        product_id, currency, price_cents
inventory:     product_id, available_units
categories:    category_id, category_name
~~~

Để tìm kiếm, một tài liệu search có thể gom trường:

~~~json
{
  "productId": "P100",
  "title": "Tai nghe không dây",
  "searchableText": "Tai nghe không dây. Chống ồn chủ động, pin 30 giờ",
  "categoryName": "Âm thanh",
  "priceCents": 149900,
  "available": true
}
~~~

Để tìm kiếm ngữ nghĩa, kho vector có thể chỉ cần `productId`, các đoạn văn bản, embedding và metadata lọc. Để phân tích, kho OLAP có thể có fact bán hàng theo thời gian, danh mục và khu vực.

**Cùng một thực thể nghiệp vụ không nhất thiết tương ứng với cùng một hàng hoặc cùng một kiểu dữ liệu tại mọi kho.** Chính việc chuyển đổi này tạo ra lợi ích chuyên biệt, đồng thời tạo ra trách nhiệm đồng bộ.

### 2.3. Replication không đồng nghĩa với đồng bộ read model

| Khái niệm | Mục đích chủ yếu | Ví dụ |
|---|---|---|
| Database replication | Giữ các bản sao dữ liệu để tăng chịu lỗi, sẵn sàng và đôi khi tăng khả năng đọc | Một collection được sao chép sang nhiều replica |
| Đồng bộ read model | Biến đổi dữ liệu sang cấu trúc phục vụ một kiểu truy vấn | `products` → tài liệu search với trường tìm kiếm |
| Event streaming | Phân phối dòng thay đổi hoặc sự kiện đến các consumer | ProductUpdated được nhiều pipeline nhận |
| ETL/ELT | Trích xuất, biến đổi, nạp dữ liệu cho phân tích | Order → fact sales, dimension product |
| Reindex/rebuild | Dựng lại kho dẫn xuất từ nguồn hoặc lịch sử sự kiện | Tạo search index mới bằng schema mới |

Replication của database gốc có thể bảo vệ khả năng phục hồi nội bộ của database, nhưng **không tự xây dựng** văn bản tìm kiếm, vector embedding hoặc bảng tổng hợp.

## 3. Các mô hình đồng bộ phổ biến

### 3.1. Ghi trực tiếp sang hai nơi (dual write)

Cách dễ nghĩ đến nhất:

~~~text
API updateProduct
   |
   +--> Ghi database nguồn
   |
   +--> Ghi search index
   |
   +--> Trả kết quả
~~~

Ưu điểm là cách triển khai ban đầu có vẻ đơn giản. Nhưng xem tình huống:

1. Ghi database nguồn thành công.
2. Ghi search index thất bại vì lỗi mạng.
3. API bị timeout hoặc không biết nên trả kết quả gì.

Lúc này sản phẩm đã đổi ở nguồn nhưng còn cũ trong search. Nếu đảo thứ tự ghi, search lại có thể hiển thị dữ liệu chưa được xác nhận ở nguồn.

Ngay cả khi hai lệnh đều trả thành công, một cập nhật khác có thể xen vào giữa và dẫn đến **sai thứ tự**.

~~~text
Request A: ghi nguồn version 18 -------- chậm ghi search ------> search v18
Request B:      ghi nguồn version 19 -> ghi search v19
~~~

Nếu A hoàn thành ghi search sau B mà sink không kiểm tra phiên bản, search có thể quay lại v18. Dual write thiếu cơ chế khôi phục và thứ tự thường khó bảo đảm đúng khi có concurrency và lỗi từng phần.

**Ứng dụng có thể dùng dual write ở tải nhỏ nếu chấp nhận rủi ro và có cơ chế tự sửa**, nhưng không nên coi “gọi hai API liên tiếp” là một giao dịch nguyên tử.

### 3.2. Đồng bộ định kỳ theo lô

Ví dụ 5 phút một lần chạy:

~~~sql
SELECT *
FROM products
WHERE updated_at >= :last_sync_time;
~~~

Sau đó ghi các bản ghi tìm được sang search/vector/analytics.

Ưu điểm:

- Dễ triển khai khi nhu cầu độ mới không cao.
- Có thể nạp lượng dữ liệu lớn theo batch, tận dụng API bulk.
- Phù hợp một số báo cáo định kỳ.

Nhược điểm:

- Dữ liệu đích trễ ít nhất đến kỳ chạy tiếp theo, có thể lâu hơn.
- Điều kiện dựa vào `updated_at` rất dễ bỏ sót khi timestamp đồng độ phân giải, đồng hồ lệch, transaction commit trễ hoặc batch đang chạy.
- **Hard delete** thường không để lại bản ghi cho truy vấn `WHERE updated_at ...`.
- Một lần quét quá lớn có thể gây tải đáng kể lên nguồn.
- Retry và xử lý một phần batch vẫn cần cơ chế riêng.

Nếu dùng incremental polling, cần **watermark/cursor an toàn**, phân trang ổn định, vùng thời gian chồng lấp hoặc nguồn thay đổi đáng tin cậy hơn. Không chỉ lấy thời điểm hiện tại làm “đã xử lý hết” khi chưa xác nhận những hàng thực sự được ghi thành công.

### 3.3. Change Data Capture (CDC)

**CDC** là cơ chế quan sát những thay đổi đã xảy ra ở cơ sở dữ liệu nguồn và chuyển chúng thành các sự kiện. Tùy hệ thống, CDC có thể đọc transaction log, oplog hoặc luồng thay đổi do database cung cấp.

~~~text
Ứng dụng -> Database nguồn
                   |
            Log thay đổi/CDC
                   |
                Connector
                   |
              Event broker
                   |
          Search / Vector / Analytics
~~~

Ví dụ khả năng CDC:

- Hệ quan hệ có thể có connector đọc nhật ký thay đổi được database hỗ trợ.
- MongoDB hỗ trợ change streams dựa trên cơ chế thay đổi của replica set/sharded cluster trong những cấu hình phù hợp; consumer có thể dùng resume token để tiếp tục.
- Một số database managed cung cấp event stream hoặc change feed riêng.

CDC có thể giảm nhu cầu sửa code nghiệp vụ để phát sự kiện, nhưng cần hiểu **có dữ liệu trước/sau cập nhật không, có xóa không, cách checkpoint ra sao, thời gian giữ log, thứ tự nào được bảo đảm và giới hạn tải**.

CDC phản ánh thay đổi dữ liệu; nó không luôn chứa đầy đủ **ý nghĩa nghiệp vụ**. Ví dụ thay đổi ba cột có thể là một hành động “PublishProduct”, nhưng CDC thô chỉ nói các hàng đã đổi. Pipeline phải biết cách kết hợp và diễn giải.

### 3.4. Transactional outbox

**Outbox** phù hợp khi ứng dụng cần ghi dữ liệu nghiệp vụ và ghi một thông điệp thay đổi **trong cùng một transaction** của nguồn giao dịch có hỗ trợ.

~~~text
          Cùng một transaction tại nguồn
       +-----------------------------------+
       | UPDATE products                   |
       | INSERT outbox_events              |
       | COMMIT                            |
       +-----------------------------------+
                          |
                     Outbox relay
                          |
                    Event broker
                          |
                 Các consumer/sink
~~~

Nếu transaction commit, cả trạng thái nghiệp vụ và bản ghi outbox cùng tồn tại. Nếu rollback, cả hai cùng bị hủy. Một relay sau đó phát outbox sang broker.

Điều này xử lý **lỗ hổng giữa “ghi DB thành công” và “phát event thất bại”** trong điều kiện outbox được ghi cùng transaction. Tuy nhiên, relay vẫn có thể phát trùng sau crash, và consumer vẫn có thể xử lý trùng. Outbox **không tự tạo exactly-once từ nguồn đến mọi hệ đích**.

Khi database nguồn không hỗ trợ transaction nhiều bản ghi phù hợp, phải đánh giá cách khác: CDC, event log có bảo đảm riêng, hoặc thiết kế idempotent và reconciliation; không thể giả định rằng outbox luôn nguyên tử ở mọi NoSQL.

### 3.5. Bảng so sánh

| Cách đồng bộ | Độ mới thường đạt được | Lợi ích | Thách thức |
|---|---|---|---|
| Dual write trực tiếp | Có thể gần tức thời | Dễ bắt đầu, ít thành phần | Ghi một phần, retry, sai thứ tự |
| Polling theo đợt | Theo phút/giờ tùy lịch | Đơn giản, dễ bulk | Lag, xóa, watermark, tải quét |
| CDC/change stream | Thường gần thời gian thực | Theo dõi thay đổi đã commit | Hạ tầng connector, retention log, thứ tự/checkpoint |
| Transactional outbox | Thường gần thời gian thực | Gắn event với transaction nguồn | Relay, duplicate, schema event, vận hành |
| Snapshot + stream | Phục vụ bootstrap và hoạt động liên tục | Dựng dữ liệu cũ rồi theo dõi thay đổi | Đảm bảo không có khoảng trống giữa snapshot và stream |

Độ mới không chỉ phụ thuộc cách thu nhận event. Search còn có thể đợi refresh index, vector phải tạo embedding và analytics phải xử lý streaming/batch, nên **end-to-end lag** có thể lớn hơn thời gian đưa event đến broker.

## 4. Ví dụ transactional outbox từ nguồn giao dịch

Xét một nguồn PostgreSQL để minh họa tính nguyên tử của outbox. Ý tưởng tương tự áp dụng cho hệ khác nếu cơ chế transaction đáp ứng điều kiện cần.

### 4.1. Schema đơn giản

~~~sql
CREATE TABLE products (
    product_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    price_cents BIGINT NOT NULL,
    status TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);
~~~

`aggregate_id` xác định thực thể, `aggregate_version` giúp consumer nhận biết thay đổi mới/cũ của cùng thực thể, còn `event_id` là định danh duy nhất của thông điệp.

### 4.2. Cập nhật sản phẩm và outbox trong một transaction

Đoạn SQL dưới mô tả nguyên tắc: ứng dụng bắt đầu transaction, cập nhật `P100` với phiên bản tăng một, nhận phiên bản mới rồi ghi event. Giả sử `:event_id` là UUID duy nhất và các tham số đã được kiểm tra.

~~~sql
BEGIN;

UPDATE products
SET name = :new_name,
    description = :new_description,
    version = version + 1,
    updated_at = now()
WHERE product_id = :product_id
RETURNING product_id, name, description,
          price_cents, status, version, updated_at;

-- Ứng dụng sử dụng dữ liệu RETURNING làm payload của event.
INSERT INTO outbox_events (
    event_id, aggregate_type, aggregate_id,
    aggregate_version, event_type, payload
)
VALUES (
    :event_id, 'Product', :product_id,
    :new_version, 'ProductChanged', :payload_jsonb
);

COMMIT;
~~~

Đây là **hai bước trong một transaction**, không phải một đoạn SQL tự động chạy được nếu thiếu các biến được ứng dụng bind từ kết quả `RETURNING`. Nếu `UPDATE` không tìm thấy sản phẩm, ứng dụng phải rollback hoặc xử lý riêng, không phát sự kiện thay đổi giả.

Trong ứng dụng, mọi đường ghi có thể làm thay đổi thuộc tính cần đồng bộ phải **tuân thủ quy ước ghi outbox**. Nếu một service cập nhật `products` mà bỏ qua outbox, kho dẫn xuất sẽ thiếu sự kiện.

### 4.3. Relay và xác nhận xuất bản

Relay đọc những outbox event chưa được phát, gửi đến broker rồi ghi nhận trạng thái đã phát.

~~~text
Đọc outbox event E
     |
     v
Gửi E đến broker
     |
     +--> broker xác nhận
              |
              v
       Đánh dấu E đã phát
~~~

Nếu relay crash **sau khi broker đã nhận E nhưng trước khi đánh dấu**, E có thể được gửi lại. Vì thế, thiết kế thực tế chấp nhận **at-least-once delivery** ở nhiều bước và dựa vào idempotency ở consumer.

Outbox cũng cần cơ chế xử lý nhiều worker, chia công việc, retry, retention/cleanup và giám sát backlog. Có thể dùng một relay đọc outbox, hoặc connector CDC đọc chính bảng outbox; lựa chọn tùy sản phẩm và năng lực vận hành.

## 5. Thiết kế event contract cho nhiều kho đích

Một event nên mang đủ thông tin để các consumer xử lý **đúng thực thể, đúng phiên bản và đúng loại thay đổi**.

Ví dụ:

~~~json
{
  "eventId": "d341e6b6-7ce6-47b0-a197-ae7f45afac54",
  "eventType": "ProductChanged",
  "schemaVersion": 2,
  "aggregateType": "Product",
  "aggregateId": "P100",
  "aggregateVersion": 18,
  "occurredAt": "2026-11-14T08:30:00Z",
  "operation": "UPSERT",
  "data": {
    "productId": "P100",
    "name": "Tai nghe chống ồn không dây",
    "description": "Chống ồn chủ động, pin 30 giờ",
    "priceCents": 149900,
    "currency": "USD",
    "status": "ACTIVE",
    "categoryId": "audio"
  }
}
~~~

Những trường cần suy nghĩ:

| Trường | Vai trò |
|---|---|
| `eventId` | Nhận diện event để ghi log và chống xử lý trùng khi cần |
| `aggregateId` | ID thực thể nguồn; dùng làm key định tuyến và ID trong các read model |
| `aggregateVersion` | Phân biệt trạng thái cũ/mới của cùng thực thể |
| `eventType` / `operation` | Phân biệt tạo, sửa, xóa hoặc sự kiện nghiệp vụ |
| `schemaVersion` | Cho phép consumer xử lý nhiều phiên bản hợp đồng dữ liệu |
| `occurredAt` | Thời điểm được quy ước là xảy ra thay đổi |
| `data` | Nội dung đủ để cập nhật read model hoặc tham chiếu để lấy lại dữ liệu |

### 5.1. Full snapshot hay sự kiện thay đổi từng trường?

**Full-state event** mang trạng thái cần thiết cho một hình chiếu:

~~~json
{
  "aggregateId": "P100",
  "aggregateVersion": 18,
  "operation": "UPSERT",
  "data": {
    "name": "Tai nghe chống ồn không dây",
    "status": "ACTIVE"
  }
}
~~~

Nếu sink luôn thay thế tài liệu theo phiên bản mới, việc nhận lại cùng event tương đối dễ xử lý. Tuy nhiên, nếu bản ghi đích cần `description`, `category` và `price` thì payload ở trên **chưa đủ** để tái dựng hoàn chỉnh.

**Delta event** mang sự thay đổi:

~~~json
{
  "aggregateId": "P100",
  "aggregateVersion": 18,
  "operation": "PATCH",
  "changedFields": {
    "name": "Tai nghe chống ồn không dây"
  }
}
~~~

Delta thường gọn nhưng yêu cầu consumer đã có trạng thái trước đó và xử lý event đúng thứ tự. Nếu bỏ sót một delta, hình chiếu có thể bị sai. Với pipeline cần dễ replay và chịu event đến muộn, full-state event hoặc cơ chế **fetch latest state by ID** thường dễ phục hồi hơn. Đổi lại, fetch trực tiếp có thể gây tải lên nguồn và cần xử lý race.

### 5.2. Ordering theo aggregate

Nếu dùng broker phân vùng theo key, có thể chọn `aggregateId` làm message key để những event của cùng sản phẩm đi cùng partition và được duy trì thứ tự **trong phạm vi bảo đảm của broker/producer**.

Không nên mặc định mọi sự kiện ở nhiều partition có một thứ tự toàn cục. Thay đổi từ hai bảng nguồn khác nhau có thể không có cùng một `aggregateVersion` trừ khi ứng dụng chủ động xây cơ chế phiên bản hóa.

### 5.3. Event time, commit time và processing time

Ba loại thời gian khác nhau:

- **Event time:** thời điểm sự kiện nghiệp vụ được cho là xảy ra.
- **Commit time:** thời điểm thay đổi được xác nhận ở nguồn (nếu có thông tin).
- **Processing time:** thời điểm consumer xử lý event.

Một event đến muộn có thể có event time cũ nhưng processing time mới. Dùng processing time để suy ra “đây là cập nhật mới nhất” có thể sai; cập nhật trạng thái cần dựa trên phiên bản, thứ tự nguồn hoặc quy tắc domain phù hợp.

## 6. Từ nguồn chính sang kho tìm kiếm toàn văn

### 6.1. Search index giữ những trường nào?

Kho tìm kiếm như Elasticsearch hoặc OpenSearch có thể cần:

~~~json
{
  "productId": "P100",
  "title": "Tai nghe chống ồn không dây",
  "bodyText": "Tai nghe chống ồn không dây. Chống ồn chủ động, pin 30 giờ.",
  "categoryId": "audio",
  "categoryName": "Âm thanh",
  "priceCents": 149900,
  "available": true,
  "sourceVersion": 18
}
~~~

Các trường đã được **biến đổi cho mục đích tìm kiếm**:

- `title` và `bodyText` có thể được analyzer phân tích thành các term.
- `categoryId` và `available` dùng để lọc chính xác.
- `priceCents` dùng cho khoảng giá và sắp xếp.
- `sourceVersion` phục vụ chống cập nhật lùi.
- Các trường từ nhiều bảng nguồn có thể được kết hợp thành một tài liệu tìm kiếm.

Search index không nhất thiết cần lưu thông tin nhạy cảm, chi tiết giao dịch hoặc mọi trường gốc.

### 6.2. Quy tắc ID ổn định

Nếu một sản phẩm luôn mang `productId = P100` thì search document nên có ID ổn định tương ứng, ví dụ `products/P100`.

~~~text
Nguồn: Product P100 (v18)
             |
             v
Search document ID: P100, sourceVersion: 18
~~~

Consumer có thể sử dụng **upsert theo document ID** khi nhận phiên bản mới. Không nên tạo một ID search ngẫu nhiên mới cho mỗi sự kiện thay đổi vì có thể tạo nhiều tài liệu trùng sản phẩm.

### 6.3. Không để event cũ ghi đè event mới

Giả sử hai sự kiện:

~~~text
ProductChanged(P100, version=18)
ProductChanged(P100, version=19)
~~~

Đường truyền có thể khiến v19 được xử lý trước v18. Nếu sink chỉ ghi đè không điều kiện:

~~~text
Index v19
    |
Nhận v18 đến muộn
    |
Index quay lại v18  <-- sai
~~~

Consumer cần quy tắc: **chỉ chấp nhận cập nhật có phiên bản mới hơn phiên bản đang có**, bằng cơ chế concurrency/conditional update của sink hoặc cơ chế đặt hàng đảm bảo thứ tự. Kiểm tra phiên bản chỉ trong memory của một worker sẽ không đủ khi có nhiều worker và retry cạnh tranh.

Với Elasticsearch, có các cơ chế kiểm soát phiên bản/optimistic concurrency tùy API. Khi triển khai cần đọc đúng API/phiên bản sản phẩm, nhất là xử lý delete và việc tái tạo tài liệu sau xóa.

### 6.4. Độ trễ hiển thị còn phụ thuộc refresh

Một sự kiện có thể đã được consumer ghi vào search index nhưng chưa thấy ngay trong truy vấn search vì search engine có cơ chế refresh/visibility riêng. Do đó:

~~~text
Source commit -> Event emitted -> Consumer update -> Index refresh -> Search visible
      T0             T1               T2              T3
~~~

**Search freshness** nên đo từ `T0` đến thời điểm kết quả truy vấn thật sự phản ánh bản cập nhật `T3`, chứ không chỉ đo broker consumer lag.

### 6.5. Xóa hoặc ẩn sản phẩm

Có hai nghiệp vụ khác nhau:

1. Sản phẩm chuyển `status = INACTIVE`, có thể giữ tài liệu search nhưng lọc không hiển thị.
2. Sản phẩm bị xóa theo chính sách dữ liệu, cần loại tài liệu khỏi search hoặc áp dụng cách xóa được thỏa thuận.

Event cần thể hiện rõ `UPSERT`, `DEACTIVATE`, `DELETE` thay vì để consumer đoán dựa trên thiếu trường. Nếu sản phẩm đã xóa, sự kiện cũ đến sau có thể “hồi sinh” search document; cần giữ dấu phiên bản/tombstone hoặc một cơ chế chống resurrection trong khoảng replay phù hợp.

## 7. Từ nguồn chính sang kho vector

### 7.1. Vector index dùng để làm gì?

Tìm kiếm truyền thống chủ yếu dựa trên từ khóa và bộ lọc; tìm kiếm vector dùng **embedding** biểu diễn nội dung trong một không gian số. Hai đoạn văn bản có ý nghĩa gần nhau có thể có vector gần nhau theo metric và mô hình được chọn.

Ví dụ mô tả:

~~~text
"Sản phẩm tai nghe chống ồn cho văn phòng"
       |
       v
Embedding model
       |
       v
[0.12, -0.08, 0.31, ...]  (minh họa)
       |
       v
Vector store / ANN index
~~~

Kho vector có thể là vector database chuyên dụng hoặc một khả năng vector search trong search/document/relational engine. Nó giữ các vector, ID và metadata, thường hỗ trợ tìm top-k vector gần nhất và lọc theo metadata.

**Vector là dữ liệu dẫn xuất** từ nội dung và phiên bản mô hình embedding. Nó không thay thế tên, giá, quyền truy cập hay trạng thái nghiệp vụ tại nguồn.

### 7.2. Pipeline vector khác search vì phải tính embedding

~~~text
ProductChanged(P100, v18)
            |
            v
    Chuẩn hóa nội dung
            |
            v
  Chia thành chunk (nếu cần)
            |
            v
     Tính embedding
            |
            v
  Upsert vector + metadata
            |
            v
  Đánh dấu phiên bản đã công bố
~~~

Một tài liệu có thể sinh ra **nhiều vector**. Ví dụ:

~~~text
P100
  |
  +--> P100/chunk-0
  +--> P100/chunk-1
  +--> P100/chunk-2
~~~

Khi nội dung thay đổi, số lượng chunk có thể từ ba thành hai hoặc bốn. Nếu chỉ upsert chunk mới mà quên xóa chunk cũ, vector store sẽ chứa những đoạn nội dung đã lỗi thời.

Do đó pipeline cần quản lý **tập chunk thuộc về một phiên bản** và quy tắc loại bỏ chunk không còn hợp lệ.

### 7.3. ID vector và metadata phiên bản

Một ID có cấu trúc:

~~~text
productId / contentVersion / chunkIndex
P100      / 18             / 0
P100      / 18             / 1
~~~

Metadata có thể gồm:

~~~json
{
  "productId": "P100",
  "sourceVersion": 18,
  "embeddingModelVersion": "embedding-v3",
  "chunkerVersion": "split-v2",
  "chunkIndex": 0,
  "categoryId": "audio",
  "tenantId": "T1",
  "visibility": "PUBLIC"
}
~~~

Một vector phụ thuộc ít nhất vào:

- Nội dung gốc hoặc bản nội dung được chuẩn hóa.
- Cách chia chunk và quy tắc chọn trường.
- Phiên bản embedding model.
- Metadata lọc và quyền truy cập.
- Metric/index vector (cosine, dot product, Euclidean... theo tính chất mô hình và sản phẩm).

Nếu đổi embedding model, vector cũ và mới có thể **không cùng một không gian biểu diễn**, nên không được mặc định trộn chúng vào một tập tìm kiếm duy nhất với khoảng cách có ý nghĩa tương đương.

### 7.4. Race condition khi tính embedding chậm

Giả sử:

~~~text
T0: nhận v18, bắt đầu gọi embedding API (mất 20 giây)
T1: nhận v19, bắt đầu embedding (mất 2 giây)
T2: v19 được ghi vào vector store
T3: v18 hoàn thành muộn và ghi đè lại dữ liệu
~~~

Ngay cả khi event broker bảo đảm thứ tự nhận, **tác vụ tính embedding bất đồng bộ có thời gian hoàn thành khác nhau**. Chỉ sắp xếp event lúc nhận chưa đủ.

Cần cơ chế kiểm tra **sourceVersion tại thời điểm công bố**, không chỉ lúc bắt đầu tính. Một cách thiết kế:

1. Vector của một phiên bản được ghi vào tập ID có version.
2. Chỉ khi mọi chunk đã ghi thành công mới đánh dấu phiên bản mới là **active**.
3. Việc chuyển active version phải có cơ chế kiểm tra phiên bản nguyên tử hoặc một đầu mối tuần tự phù hợp.
4. Kết quả tìm kiếm chỉ lấy những vector thuộc phiên bản đang được công bố.
5. Vector phiên bản cũ được dọn sau khi phiên bản mới đã sẵn sàng.

Cách này phụ thuộc khả năng truy vấn/lọc/đổi trạng thái nguyên tử của vector store. Nếu sink không hỗ trợ chuyển phiên bản nguyên tử, cần thiết kế tầng metadata/manifest riêng hoặc chấp nhận cửa sổ dữ liệu hỗn hợp có giới hạn.

### 7.5. Từ nội dung gốc sang văn bản cho embedding

Ví dụ sản phẩm có các trường:

~~~json
{
  "name": "Tai nghe chống ồn",
  "description": "Pin 30 giờ, chống ồn chủ động",
  "color": "black",
  "priceCents": 149900
}
~~~

Ta có thể chuẩn hóa văn bản:

~~~text
Sản phẩm: Tai nghe chống ồn.
Mô tả: Pin 30 giờ, chống ồn chủ động.
Màu sắc: black.
~~~

Không phải trường nào cũng nên đưa vào embedding. Giá và tồn kho thay đổi thường xuyên và thường phục vụ **lọc chính xác**, nên có thể để ở metadata hoặc lấy từ nguồn mới nhất. Đưa các trường biến động nhanh vào nội dung embedding sẽ khiến pipeline phải tính lại vector quá thường xuyên.

Quy tắc thực tế:

- **Nội dung có ý nghĩa ngữ nghĩa** → embedding.
- **Thuộc tính cần lọc chính xác** → metadata filter.
- **Dữ liệu quan trọng cần mới nhất** → đối chiếu nguồn nghiệp vụ tại thời điểm hành động.

### 7.6. Vector search phải tôn trọng quyền truy cập

Giả sử người dùng tenant T1 chỉ được xem tài liệu của T1. Dù embedding mang thông tin giống nhau, truy vấn vector không được trả nội dung của T2.

Có thể lọc `tenantId`, `visibility` và quyền theo metadata, nhưng phải kiểm chứng **bộ lọc được thực thi đúng trong pipeline tìm kiếm**, cả trước và sau truy xuất ứng viên khi cần. Thao tác đổi quyền truy cập ở nguồn phải được đồng bộ hoặc kiểm tra trực tiếp ở lớp ứng dụng.

Một bản sao vector hoặc nội dung chunk vẫn có thể chứa thông tin nhạy cảm. Xóa dữ liệu cá nhân cần bao phủ **cả vector, metadata, nội dung chunk, cache và bản xuất liên quan** theo chính sách áp dụng.

### 7.7. Hybrid search và tính nhất quán

Một API tìm kiếm có thể kết hợp từ khóa + vector:

~~~text
        Câu truy vấn người dùng
                   |
            +------+------+
            |             |
      Keyword search   Vector search
            |             |
            +------+------+
                   |
           Hợp nhất/xếp hạng
                   |
          Lọc quyền và trạng thái
                   |
          Đối chiếu dữ liệu cần mới
                   |
                Kết quả
~~~

Search index có thể đang ở `sourceVersion = 19`, còn vector mới nhất chỉ có v18 vì embedding trễ. Nếu hai nguồn được hợp nhất không kiểm soát, kết quả tìm kiếm có thể hiển thị mô tả cũ cùng giá mới. Có thể chấp nhận mức lệch này cho gợi ý, nhưng phải xác định rõ phạm vi và cách xử lý các trường hợp đòi hỏi đồng nhất phiên bản.

## 8. Từ nguồn chính sang kho phân tích (OLAP / warehouse)

### 8.1. Mục tiêu khác với kho tìm kiếm

Hệ phân tích thường trả lời:

- Tổng doanh thu mỗi ngày và khu vực.
- Tỷ lệ đơn hủy theo phương thức vận chuyển.
- Số sản phẩm còn hàng theo danh mục mỗi giờ.
- Mức tăng trưởng, cohort, retention và xu hướng dài hạn.

Các câu hỏi thường cần **quét, nhóm và tổng hợp nhiều bản ghi**, khác với đọc một sản phẩm theo ID hay tìm top-k vector tương đồng.

Kho phân tích có thể tổ chức:

~~~text
fact_order_items
  order_id, product_id, customer_id,
  quantity, amount_cents, event_time, status

dim_product
  product_id, category_id, brand, effective_from, effective_to

dim_customer
  customer_id, region, segment

aggregate_daily_sales
  day, region, total_orders, gross_amount_cents
~~~

Một bản ghi giao dịch nguồn có thể được chuyển thành fact; thuộc tính sản phẩm thành dimension; các bảng tổng hợp được xây thêm để phục vụ dashboard.

### 8.2. ETL, ELT và streaming ingestion

- **ETL:** lấy dữ liệu, biến đổi rồi nạp vào đích.
- **ELT:** nạp dữ liệu thô/tương đối thô, sau đó biến đổi ngay tại kho phân tích.
- **Streaming:** đọc sự kiện liên tục và cập nhật fact/aggregate gần thời gian thực.
- **Batch:** nạp dữ liệu theo lịch giờ/ngày khi chấp nhận độ trễ lớn hơn.

Một kiến trúc lakehouse/warehouse thường tách:

~~~text
CDC / Event stream
        |
        v
Raw change log / Bronze
        |
        v
Chuẩn hóa, khử trùng, diễn giải CDC / Silver
        |
        v
Fact, Dimension, Aggregate / Gold
        |
        v
Dashboard và báo cáo
~~~

Tên Bronze/Silver/Gold chỉ là một cách tổ chức tầng dữ liệu. Điều quan trọng là giữ được **dấu vết nguồn, phiên bản, thời điểm và quy tắc biến đổi**, để kết quả phân tích có thể kiểm chứng.

### 8.3. Snapshot trạng thái và lịch sử sự kiện

Có hai nhu cầu rất khác:

1. **Current-state analytics:** sản phẩm P100 hiện còn bao nhiêu, trạng thái mới nhất là gì?
2. **Historical analytics:** ngày 01/11 giá của P100 là bao nhiêu, doanh thu tháng đó theo mức giá nào?

Nếu pipeline chỉ ghi đè một hàng `products_current`, nó phù hợp câu hỏi thứ nhất nhưng không đủ cho câu hỏi lịch sử trừ khi nguồn khác còn lưu thay đổi theo thời gian.

Đối với lịch sử, có thể giữ **event log** hoặc tạo dimension có hiệu lực theo giai đoạn (thường gọi là **slowly changing dimension, Type 2** trong kho phân tích):

~~~text
product_id | category | valid_from | valid_to
P100       | audio    | 2026-01-01 | 2026-10-01
P100       | premium  | 2026-10-01 | null
~~~

Một báo cáo “doanh thu theo danh mục tại thời điểm bán” phải ghép fact với dimension có hiệu lực ở thời điểm giao dịch, hoặc lưu category snapshot trong fact theo hợp đồng rõ ràng. Nếu ghép toàn bộ đơn quá khứ với category mới nhất, báo cáo lịch sử có thể thay đổi ngoài ý muốn.

### 8.4. Upsert, delete và dữ liệu đến muộn

Consumer analytics có thể nhận cùng một đơn nhiều lần do retry. Nếu mỗi event `OrderPaid` đều cộng thêm doanh thu, duplicate sẽ làm số liệu tăng sai.

Có thể dùng một bảng fact với khóa nghiệp vụ ổn định:

~~~text
(order_id, order_item_id) -> một fact được cập nhật/idempotent
~~~

Sau đó tổng hợp từ fact đã chuẩn hóa, hoặc dùng cơ chế xử lý stream bảo đảm update/retract phù hợp. Với sự kiện thay đổi trạng thái, cần biết **khi nào ghi nhận doanh thu**; việc cộng từ mỗi event cập nhật không đúng nếu event không phải phát sinh doanh thu mới.

Khi đơn bị hoàn tiền hoặc hủy, số liệu cần phản ánh quy tắc kế toán/nghiệp vụ: ghi một sự kiện điều chỉnh, thay đổi trạng thái fact hoặc tạo khoản âm theo hợp đồng. Không nên đơn giản xóa mọi dấu vết lịch sử nếu báo cáo cần audit.

Dữ liệu **late-arriving** (đến muộn) có thể rơi vào một cửa sổ ngày đã kết thúc. Pipeline phải có chính sách cập nhật lại aggregate, window watermark, tính toán lại theo partition hoặc ghi điều chỉnh. Không có khẳng định chung rằng dashboard cuối ngày sẽ không bao giờ thay đổi.

### 8.5. Event time, watermark và độ mới phân tích

Một sự kiện có:

~~~json
{
  "orderId": "O100",
  "eventTime": "2026-11-13T23:55:00Z",
  "ingestedAt": "2026-11-14T00:10:00Z",
  "amountCents": 12000
}
~~~

Nếu báo cáo nhóm theo ngày giao dịch, cần dùng **eventTime** theo múi giờ nghiệp vụ đã định nghĩa, không mặc định theo thời điểm pipeline nhận event. Watermark giúp hệ streaming ước lượng ranh giới event time có thể coi là đủ hoàn chỉnh trong phạm vi độ trễ được phép.

Một số sự kiện đến quá muộn so với watermark có thể cần luồng xử lý ngoại lệ hoặc cập nhật bù. **Watermark không tự làm dữ liệu quá khứ tuyệt đối hoàn chỉnh.**

## 9. Đồng bộ lần đầu: snapshot và thay đổi liên tục

Khi tạo một search index mới, không thể chỉ nghe các sự kiện từ bây giờ vì kho nguồn có thể đã có hàng triệu sản phẩm.

Cần phối hợp:

1. **Snapshot:** lấy trạng thái hiện có tại một thời điểm hoặc một phạm vi nhất quán được xác định.
2. **Change stream:** thu nhận mọi thay đổi trong lúc chụp và nạp snapshot.
3. **Catch-up:** áp dụng những thay đổi chưa được phản ánh.
4. **Cutover:** chỉ chuyển traffic khi read model đủ đầy và đủ mới.

~~~text
Nguồn gốc:  [ dữ liệu cũ ] + [ thay đổi tiếp tục đến ... ]
                   |                     |
                   v                     v
                Snapshot          CDC/Event stream
                   |                     |
                   +----------+----------+
                              |
                         Merge theo ID
                         và phiên bản
                              |
                      Read model hoàn chỉnh
~~~

### 9.1. Rủi ro khoảng trống giữa snapshot và stream

Cách làm nguy hiểm:

~~~text
T0: bắt đầu SELECT toàn bộ sản phẩm
T1: một sản phẩm thay đổi
T2: SELECT hoàn tất
T3: bắt đầu nghe CDC
~~~

Thay đổi tại T1 có thể không có trong snapshot ở phiên bản cuối cùng lẫn stream bắt đầu từ T3. Đây là **gap** dẫn đến mất cập nhật.

Cần một phương án snapshot + CDC được thiết kế có vị trí log/offset hoặc cơ chế kiểm soát nhất quán, thay vì tự ghép hai giai đoạn không liên hệ.

### 9.2. Snapshot cũ không được ghi đè thay đổi mới

Giả sử snapshot chứa `P100 v18`, nhưng event stream đã cập nhật `P100 v19` vào search trước khi batch snapshot xử lý xong.

Nếu snapshot ghi đè vô điều kiện, index quay về v18. Vì thế, cả **snapshot** và **stream** đều phải tuân theo cùng quy tắc phiên bản/ordering tại sink.

Nếu nguồn không có trường version, có thể dựa vào CDC offset/sequence hợp lệ theo phạm vi nguồn, hoặc thiết kế version mới trước khi triển khai. Không nên so sánh `updatedAt` một cách tùy tiện khi đồng hồ và transaction có thể sai thứ tự.

### 9.3. Xử lý ID đã bị xóa trong lúc snapshot

Một sản phẩm có trong snapshot nhưng bị xóa ngay sau đó. Event delete có thể đến trước khi snapshot upsert xử lý xong. Nếu sink không giữ thông tin “đã xóa ở phiên bản mới hơn”, snapshot có thể tạo lại sản phẩm.

Một phương án là lưu **tombstone/version marker** đủ lâu để chặn cập nhật cũ. Phương án khác là snapshot ở mốc log có thể chứng minh đúng và giải quyết replay theo thứ tự, hoặc đối chiếu trạng thái nguồn trước cutover. Chi tiết tùy hệ thống.

## 10. Bảo đảm giao nhận: at-most-once, at-least-once và exactly-once

### 10.1. Ba cách diễn đạt

- **At-most-once:** một event có thể bị mất nếu lỗi, nhưng không bị xử lý lại qua đường giao nhận đang xét.
- **At-least-once:** cố gắng giao lại đến khi được xác nhận; consumer phải xử lý duplicate.
- **Exactly-once:** một bảo đảm được định nghĩa trong **phạm vi cụ thể** của hệ thống và giao thức, không phải phép màu khiến mọi database, broker và search/vector sink đồng thời có giao dịch chung.

Nhiều hệ streaming hỗ trợ những tính năng exactly-once trong phạm vi pipeline nội bộ, nhưng **tác động lên một hệ ngoài qua HTTP/API** vẫn phải được thiết kế theo khả năng của sink. Thực tế thường chọn at-least-once + **idempotent upsert/version guard**.

### 10.2. Event ID có đủ để chống mọi lỗi không?

Không. `eventId` giúp nhận ra một event bị phát lại. Nhưng hai event **khác ID** vẫn có thể cập nhật cùng sản phẩm theo thứ tự ngược:

~~~text
E18 -> P100 v18
E19 -> P100 v19
~~~

Deduplicate theo eventId giải quyết việc **cùng một event bị xử lý hai lần**. Kiểm tra `aggregateVersion` giải quyết việc **event cũ hơn ghi đè trạng thái mới hơn**. Hai vấn đề liên quan nhưng không giống nhau.

### 10.3. Upsert theo phiên bản

Giả mã cho sink lưu một trạng thái mới nhất:

~~~text
function applyProductEvent(event):
    id = event.aggregateId
    incomingVersion = event.aggregateVersion

    current = sink.readMetadata(id)

    if current exists and incomingVersion <= current.sourceVersion:
        return ACK_IGNORED_OLD_OR_DUPLICATE

    if event.operation == "DELETE":
        sink.markDeletedOrDeleteWithVersionGuard(
            id, incomingVersion
        )
    else:
        document = transformForSink(event.data)
        sink.upsertIfVersionNewer(
            id, document, incomingVersion
        )

    return ACK_APPLIED
~~~

Đây là **giả mã mô tả yêu cầu**, không phải API dùng nguyên xi. Việc `readMetadata` rồi `upsert` riêng biệt có thể tạo race nếu hai worker cùng xử lý; kiểm tra phiên bản phải được bảo vệ **nguyên tử** bằng cơ chế sink, hoặc bởi một thành phần tuần tự bảo đảm không có race.

### 10.4. Không ack trước khi trạng thái đích được ghi bền

Một consumer an toàn thường chỉ xác nhận event/offset sau khi:

- Sink đã ghi thành công theo mức bảo đảm yêu cầu;
- Hoặc event được chuyển vào một cơ chế retry bền vững đã nhận trách nhiệm xử lý;
- Hoặc event được xác định là cũ/trùng theo một quy tắc có thể chứng minh.

Nếu ack trước khi ghi sink và worker crash, event có thể mất khỏi đường xử lý. Nếu ghi sink thành công rồi crash trước khi ack, event có thể xử lý lại. Đây là lý do thiết kế idempotency là nền tảng.

## 11. Xóa dữ liệu: trường hợp dễ bị bỏ sót

### 11.1. Soft delete và hard delete

**Soft delete** là thay đổi trạng thái ở nguồn:

~~~json
{
  "productId": "P100",
  "status": "DELETED",
  "version": 20
}
~~~

Consumer có thể xóa tài liệu khỏi search/vector hoặc ẩn nó theo metadata, tùy yêu cầu. Trong analytics, dữ liệu lịch sử có thể cần giữ một số trường không nhạy cảm theo chính sách.

**Hard delete** là loại bỏ bản ghi nguồn. Nếu chỉ dùng polling “lấy hàng có `updatedAt` mới”, không có hàng nào để báo rằng sản phẩm đã biến mất. Cần **sự kiện DELETE**, change stream/CDC có thao tác xóa, hoặc cơ chế phát hiện xóa riêng.

### 11.2. Delete phải lan truyền sang mọi read model

~~~text
DELETE Product P100 tại nguồn
           |
           v
       ProductDeleted
           |
     +-----+----------+-------------+
     |                |             |
     v                v             v
 Search delete     Vector delete   Analytics policy
     |                |             |
  index/docs      vectors/chunks  xóa/ẩn/giữ lịch sử
~~~

Đặc biệt với vector, một sản phẩm có thể có nhiều chunk và nhiều phiên bản embedding. Xóa chỉ một vector ID không đủ nếu cùng `productId` còn vector phụ.

### 11.3. Chống “hồi sinh” dữ liệu sau delete

Giả sử sink xử lý:

~~~text
T1: DELETE(P100, version=20)
T2: UPSERT(P100, version=18) đến muộn
~~~

Nếu `DELETE` chỉ xóa vật lý tài liệu và làm mất toàn bộ metadata phiên bản, `UPSERT v18` có thể tạo lại tài liệu. Cần cơ chế chặn theo version, tombstone, danh sách ID đã xóa hoặc bảo đảm replay/cutover có trật tự.

Chiến lược tombstone phải xét **thời gian lưu sự kiện, thời gian replay/backfill, retention và quyền xóa**. Một tombstone quá ngắn có thể không chặn được event cũ rất muộn.

### 11.4. Bảo vệ dữ liệu cá nhân

Dữ liệu gốc có thể chứa thông tin người dùng. Khi đồng bộ sang search, vector và analytics, phải xác định:

- Trường nào thật sự cần sao chép?
- Kho nào lưu nội dung nguyên văn, cache hoặc snapshot?
- Embedding/chunk có thể lưu dấu nội dung nhạy cảm không?
- Những bản xuất, object storage hoặc backup nào chứa bản sao?
- Luồng xóa/cập nhật quyền truy cập đến từng hệ bằng cơ chế nào?
- Làm sao kiểm chứng việc xóa/ẩn đã hoàn tất theo chính sách?

Không nên mặc định “đã xóa document ở database gốc” nghĩa là dữ liệu đã biến mất khỏi mọi hệ dẫn xuất. Cũng không nên tự động coi embedding là dữ liệu vô danh; mức độ nhạy cảm và yêu cầu xử lý phụ thuộc nguồn dữ liệu, nội dung và chính sách áp dụng.

## 12. Xây lại read model khi đổi schema, analyzer hoặc embedding model

### 12.1. Vì sao cần rebuild?

Các trường hợp:

- Search cần thay mapping hoặc analyzer.
- Muốn bổ sung trường `categoryName` vào tài liệu đã lưu.
- Đổi thuật toán chia chunk từ `split-v1` sang `split-v2`.
- Nâng embedding model, dẫn tới vector dimension hoặc không gian embedding mới.
- Sửa một lỗi tính toán doanh thu trong bảng tổng hợp.
- Phát hiện sink đã mất event trong một giai đoạn.

Khi đó, sửa consumer từ thời điểm hiện tại **không đủ** để cập nhật dữ liệu lịch sử. Cần backfill/reindex hoặc replay để xây lại đúng tập dữ liệu.

### 12.2. Blue–green index và chuyển đổi traffic

Một cách triển khai cho search:

~~~text
                   Event stream
                         |
             +-----------+-----------+
             |                       |
             v                       v
       products_v1              products_v2
       (đang phục vụ)           (đang xây mới)
             |                       |
           Alias                Snapshot + catch-up
             |                       |
          Search API          Đo độ đầy đủ/lag
                                     |
                              Đạt điều kiện cutover
                                     |
                          Alias chuyển sang v2
~~~

Các hệ search thường có cơ chế index/alias cụ thể; cần kiểm tra thao tác chuyển alias, cách index ghi tiếp tục được cập nhật và yêu cầu của cluster. Mục tiêu là **đọc từ chỉ mục mới khi nó đủ đầy và đủ mới**.

Đừng chỉ đếm tài liệu để quyết định cutover: cùng số lượng vẫn có thể sai nội dung, thiếu phiên bản hoặc chứa bản ghi đáng lẽ đã xóa.

### 12.3. Tái tạo embedding

Khi đổi mô hình embedding:

1. Định nghĩa `embeddingModelVersion`, dimension, metric và quy tắc chuẩn hóa.
2. Tạo namespace/index đích mới hoặc tập phiên bản tách biệt.
3. Lấy nội dung nguồn theo snapshot/replay có mốc theo dõi.
4. Tính embedding mới cho tất cả tài liệu/chunk cần thiết.
5. Tiếp nhận các thay đổi phát sinh trong thời gian build.
6. Kiểm tra độ đầy đủ, chất lượng tìm kiếm và giới hạn lag.
7. Chuyển truy vấn sang tập embedding mới.
8. Dọn dữ liệu cũ theo kế hoạch an toàn.

Không nên trộn embedding hai mô hình khác nhau vào một chỉ mục chỉ vì có cùng số chiều. Hai mô hình có thể dùng không gian vector không tương thích.

### 12.4. Xây lại phân tích và định nghĩa số liệu

Nếu báo cáo doanh thu trước đây tính cả đơn chưa thanh toán, cần sửa **định nghĩa metric** và tái tính dữ liệu lịch sử. Consumer mới nhận event tương lai không tự sửa tổng doanh thu các tháng trước.

Cần lưu version của pipeline/transform, quy tắc tính toán, thời gian hiệu lực và khả năng tái tạo từ fact hoặc raw event. Báo cáo quan trọng nên có quá trình đối soát với nguồn/số liệu đã xác nhận.

## 13. Dữ liệu kết hợp từ nhiều nguồn và vấn đề version

Giả sử một search document cần:

~~~text
Product (tên, mô tả)
Category (tên danh mục)
Pricing (giá hiện tại)
Inventory (còn hàng không)
~~~

Bốn thành phần có thể được quản lý bởi bốn bảng hoặc bốn dịch vụ. Mỗi nguồn có version riêng:

~~~text
productVersion  = 18
categoryVersion = 7
priceVersion    = 45
stockVersion    = 206
~~~

Không thể coi `productVersion` là version của toàn bộ tài liệu search nếu một sự kiện thay đổi giá có thể đến mà productVersion không đổi.

### 13.1. Hai cách hình thành projection

**Cách A — mỗi event làm mới toàn bộ tài liệu từ nguồn:** khi nhận Product/Price/StockChanged, projector đọc các nguồn hiện tại rồi tạo một tài liệu hoàn chỉnh.

Ưu điểm: đơn giản hóa logic merge, hữu ích nếu đọc nguồn nhanh và có cơ chế snapshot nhất quán. Hạn chế: nhiều lần đọc, có thể lấy trạng thái ở các thời điểm khác nhau, dễ gây tải/độ trễ và race nếu có nhiều worker.

**Cách B — projector duy trì trạng thái từng phần:** giữ một bản trạng thái theo `productId`, áp dụng update từ từng nguồn và tạo tài liệu search từ tập trạng thái hiện tại.

Ưu điểm: giảm số lần đọc ngược nguồn, có thể xử lý event stream hiệu quả. Hạn chế: cần quản lý phiên bản cho từng nguồn, khởi tạo snapshot, xử lý thiếu event, xóa và reconciliation.

### 13.2. Dùng version vector hoặc snapshot đã xác định

Một metadata projection có thể ghi:

~~~json
{
  "productId": "P100",
  "versions": {
    "product": 18,
    "category": 7,
    "price": 45,
    "stock": 206
  }
}
~~~

Đây chỉ là ví dụ **theo dõi phiên bản từng thành phần**, không phải thuật toán vector clock phân tán đầy đủ. Khi nhận `PriceChanged(priceVersion=44)`, projector biết dữ liệu giá đã cũ mà không cần so sánh với `productVersion`.

Nếu cần xem toàn bộ dữ liệu như một ảnh chụp nhất quán qua nhiều dịch vụ, thiết kế này chưa đủ; có thể cần cơ chế transaction/điểm chụp hoặc thỏa thuận về mức sai lệch được phép.

### 13.3. Giá và tồn kho cần chiến lược riêng

Trong nhiều sản phẩm, cập nhật mô tả chậm vài giây có thể chấp nhận được, nhưng **tồn kho và giá thanh toán** cần xác minh ở dịch vụ nguồn khi khách đặt hàng.

Một mô hình hợp lý:

- Search/vector phục vụ **khám phá sản phẩm**.
- API chi tiết có thể làm mới thuộc tính quan trọng khi cần.
- Checkout luôn kiểm tra **giá, quyền mua, tồn kho và giao dịch** theo bảo đảm nghiệp vụ.

Không nhất thiết buộc mọi read model phải đồng bộ tức thời nếu một số trường có thể đọc lại từ nguồn trước khi thực hiện hành động nhạy cảm.

## 14. Theo dõi độ trễ và chất lượng đồng bộ

### 14.1. “Consumer lag bằng 0” chưa đủ

Một pipeline có các mốc:

~~~text
T0  Source transaction commit
T1  CDC/outbox thu nhận
T2  Broker nhận event
T3  Consumer bắt đầu xử lý
T4  Sink xác nhận ghi
T5  Dữ liệu nhìn thấy trong truy vấn đích
~~~

Các chỉ số khác nhau:

- `T1 - T0`: độ trễ thu nhận thay đổi.
- `T3 - T2`: độ trễ hàng đợi/consumer.
- `T4 - T3`: thời gian xử lý, transform, embedding hoặc ghi sink.
- `T5 - T4`: thời gian refresh/visibility.
- `T5 - T0`: **độ mới toàn tuyến (end-to-end freshness)**.

Vector có thể tốn thời gian embedding, còn phân tích có thể chờ một window tổng hợp; do đó chỉ nhìn broker offset không đủ.

### 14.2. Bộ metric nên có

| Nhóm | Metric gợi ý | Câu hỏi trả lời |
|---|---|---|
| Source/CDC | Capture lag, lỗi connector, log retention còn lại | Có thay đổi nào chưa được thu nhận? |
| Broker | Consumer lag, age of oldest unprocessed event, retry count | Có backlog hoặc sự kiện tồn đọng? |
| Projector | Số event xử lý/s, thời gian transform, duplicate/out-of-order | Công việc xử lý có theo kịp? |
| Search | Indexing errors, refresh/visibility lag, mismatch theo version | Search đã nhìn thấy dữ liệu mới chưa? |
| Vector | Embedding latency, job failures, active model/version, orphan chunk | Vector có đúng tập nội dung không? |
| Analytics | Watermark, late events, fact reconciliation, job duration | Dashboard đầy đủ và mới đến đâu? |
| Data quality | Missing IDs, schema errors, count/hash mismatch, delete debt | Có bản ghi sai hoặc còn sót? |
| Availability | DLQ depth, retry backlog, sink/API errors | Pipeline phục hồi được sau lỗi không? |

Cần phân tách metric theo **tenant, collection/table, partition, event type, pipeline và sink** khi phù hợp. Trung bình toàn hệ có thể che một tenant hoặc phân vùng đang chậm.

### 14.3. SLI/SLO cho dữ liệu đồng bộ

Một SLO minh họa cho search:

> Trong cửa sổ 30 ngày, ít nhất 99,9% thay đổi sản phẩm hợp lệ đã commit ở nguồn phải xuất hiện đúng trong truy vấn search trong vòng 30 giây, trừ các trường hợp ngoại lệ được định nghĩa trước.

Để đo SLO này, cần kiểm tra **trạng thái truy vấn đích theo phiên bản**, không chỉ ghi nhận consumer đã ack event.

SLO vector có thể dài hơn do thời gian embedding; SLO analytics có thể quy định theo watermark hoặc giờ chốt báo cáo. Đây là mục tiêu phải **thỏa thuận theo nhu cầu sản phẩm**, không có một ngưỡng chuẩn áp dụng cho mọi hệ thống.

### 14.4. Alert về độ lệch và mất cập nhật

Các chỉ số cần cảnh báo có thể gồm:

- Consumer không tiến lên trong một khoảng thời gian.
- Oldest event age vượt ngưỡng.
- Tỷ lệ mapping/schema failures tăng.
- Embedding job tồn đọng kéo dài.
- Tỷ lệ cập nhật search thành công nhưng query visibility chưa đạt.
- Số bản ghi thiếu hoặc lệch theo phiên bản vượt giới hạn.
- Xóa dữ liệu quá thời hạn xử lý cho phép.

Một dashboard chỉ có “requests/s” không chứng minh đồng bộ đang đúng.

## 15. Xử lý lỗi, retry và Dead Letter Queue

### 15.1. Phân loại lỗi trước khi retry

**Lỗi tạm thời:** timeout mạng, sink quá tải, lỗi kết nối; có thể retry với backoff và jitter, giới hạn số lần hoặc thời gian.

**Lỗi dữ liệu:** event sai schema, thiếu field bắt buộc, vector dimension không khớp, ID không hợp lệ; retry lặp lại không sửa được nếu dữ liệu hoặc code không đổi.

**Lỗi nghiệp vụ:** nguồn đã xóa sản phẩm, trạng thái không cho phép, thiếu thông tin liên kết; cần quyết định bỏ qua, chờ dữ liệu bổ sung hoặc gửi đi xử lý riêng.

### 15.2. Dead Letter Queue (DLQ)

DLQ chứa những event không thể xử lý theo con đường thông thường sau chính sách retry:

~~~text
Event -> Consumer -> Transform/Write
                     |
                     +--> Thành công -> Ack
                     |
                     +--> Lỗi tạm -> Retry có giới hạn
                     |
                     +--> Lỗi không phục hồi -> DLQ + cảnh báo
~~~

Một bản ghi DLQ nên giữ đủ thông tin:

- Event ID, aggregate ID và version.
- Event payload hoặc tham chiếu bảo mật đến payload.
- Tên consumer/sink, mã lỗi, giai đoạn xử lý.
- Thời điểm, số lần thử và metadata có thể truy vết.

**Đưa vào DLQ không có nghĩa dữ liệu đích đã đúng.** Nó là cơ chế cô lập lỗi để pipeline vẫn có thể tiếp tục, đồng thời tạo nghĩa vụ sửa lỗi/replay. Với dữ liệu quan trọng, cần giám sát số event ở DLQ và độ tuổi tồn đọng.

### 15.3. Retry phải idempotent

Ví dụ sink đã ghi thành công nhưng phản hồi HTTP bị mất; consumer nghĩ thất bại và gửi lại. Nếu thao tác là `UPSERT product by stable ID and version`, có thể xử lý an toàn hơn so với “tạo một record ID ngẫu nhiên mới” hoặc “cộng doanh thu thêm một lần”.

Không nên gọi thao tác cộng dồn không idempotent từ một consumer at-least-once mà không có cơ chế dedup/transaction phù hợp.

## 16. Đối soát dữ liệu (reconciliation)

Ngay cả pipeline có CDC, retry và version guard vẫn có thể xuất hiện sai lệch do bug, thao tác quản trị, mất checkpoint, schema thay đổi hoặc dữ liệu bị xóa nhầm. Vì thế cần **reconciliation** độc lập với đường stream.

### 16.1. So sánh theo ID và version

Một cách kiểm tra:

1. Lấy tập ID nguồn trong một phân vùng hoặc khoảng thời gian.
2. Lấy tập ID tương ứng ở sink.
3. So sánh ID thiếu, ID thừa và version.
4. Với các ID lệch, tính lại projection từ nguồn chuẩn.
5. Ghi nhận số lượng, nguyên nhân, thời gian sửa và kiểm tra sau sửa.

Ví dụ:

| Product ID | Source version | Search version | Kết luận |
|---|---:|---:|---|
| P100 | 19 | 19 | Khớp phiên bản |
| P101 | 7 | 6 | Search chậm/cũ |
| P102 | 10 | — | Thiếu trong search |
| P103 | Đã xóa v22 | 21 | Search còn dữ liệu cũ |

**Khớp version chưa chứng minh toàn bộ nội dung đúng** nếu phép transform có bug hoặc dữ liệu tham chiếu từ nguồn khác chưa cập nhật. Có thể so thêm checksum/hash của trường chuẩn hóa, số chunk/manifest hoặc các chỉ tiêu nghiệp vụ.

### 16.2. Không tin tuyệt đối vào số lượng document

Hai tập đều có 1 triệu document vẫn có thể khác nhau 100.000 ID. Nếu một bản ghi bị thiếu và một bản ghi khác bị thừa, count tổng vẫn khớp.

Kiểm tra nên dựa trên **ID, version, tập trường quan trọng, dấu xóa và phạm vi được phép hiển thị**, có thể kết hợp kiểm tra toàn bộ định kỳ và lấy mẫu theo mức rủi ro.

### 16.3. Tự sửa dựa trên nguồn chuẩn

Khi phát hiện search chứa bản cũ, có thể phát lại sự kiện hoặc đọc trạng thái nguồn rồi dựng lại tài liệu đích. Với vector, cần xóa chunk lỗi và tính lại embedding đúng model version. Với analytics, có thể chạy lại transform từ raw events hoặc backfill fact/aggregate.

Quy trình sửa phải tránh **ghi lùi phiên bản** và phải để lại dấu vết kiểm tra. Nếu một bản ghi đã bị xóa theo yêu cầu, hành động repair không được vô tình nạp lại từ snapshot cũ.

## 17. Kiến trúc tham khảo cho sản phẩm có search, vector và analytics

Một kiến trúc có thể là:

~~~text
                          Product API
                               |
                   Transaction / Validation
                               |
                               v
                    Database nguồn chính
                               |
                          CDC / Outbox
                               |
                               v
                     Durable Event Stream
                               |
             +-----------------+--------------------+
             |                 |                    |
             v                 v                    v
     Search Projector   Vector Projector      Analytics Ingest
             |                 |                    |
       Enrich/Mappings   Text + Chunking       Raw change log
             |                 |                    |
       Version-guard     Embedding model        Facts/Dimensions
             |                 |                    |
             v                 v                    v
        Search Index       Vector Store         OLAP/Warehouse
             |                 |                    |
             +--------+--------+                    |
                      |                             |
              Hybrid Search API                Dashboards
                      |
            Check ACL / business data
                      |
                User-facing result

     Shared operational services:
     Metrics + Tracing + Retry/DLQ + Reconciliation + Rebuild
~~~

### 17.1. Một thay đổi tên sản phẩm đi qua hệ thống thế nào?

1. API xác thực yêu cầu và cập nhật tên của `P100` tại nguồn.
2. Sự thay đổi được ghi nhận qua outbox/CDC cùng ID và version.
3. Search projector nhận event, dựng lại trường `title` và `bodyText`.
4. Vector projector kiểm tra văn bản embedding đã thay đổi, tạo chunk/embedding mới.
5. Analytics pipeline cập nhật dimension sản phẩm nếu báo cáo cần tên mới.
6. Mỗi sink xác nhận đã ghi bản phù hợp; metric theo dõi khi nào dữ liệu **thực sự truy vấn thấy**.
7. Nếu projector lỗi, event được retry hoặc vào DLQ; reconciliation phát hiện chênh lệch kéo dài.

### 17.2. Một thay đổi tồn kho đi qua hệ thống thế nào?

Nếu `stock` đổi từ 12 xuống 0:

- Nguồn tồn kho ghi nhận trạng thái đúng.
- Search có thể cập nhật `available = false` để sản phẩm không xuất hiện trong bộ lọc “còn hàng”.
- Vector có thể **không cần tính lại embedding** nếu nội dung dùng cho embedding không thay đổi; chỉ cập nhật metadata nếu filter dùng `available`.
- Analytics có thể cập nhật snapshot tồn kho hoặc phát fact biến động kho tùy mô hình.
- Checkout vẫn phải kiểm tra nguồn tồn kho theo cơ chế chống bán vượt hàng.

Điều này cho thấy không phải một sự kiện đều yêu cầu **tạo lại mọi hình chiếu từ đầu**. Pipeline có thể xác định **loại thay đổi** và chỉ cập nhật phần cần thiết.

### 17.3. Một thao tác xóa sản phẩm đi qua hệ thống thế nào?

- Nguồn ghi nhận delete hoặc thay đổi trạng thái tương ứng.
- Event delete mang ID và version.
- Search xóa hoặc ẩn tài liệu.
- Vector xóa hoặc vô hiệu hóa toàn bộ chunk/phiên bản liên quan.
- Analytics áp dụng chính sách lưu lịch sử/xóa theo loại dữ liệu.
- Reconciliation xác nhận không còn bản sao không được phép phục vụ.
- Tombstone/version guard ngăn event cũ dựng lại dữ liệu đã xóa.

## 18. Thiết kế luồng đồng bộ từ yêu cầu thực tế

Có thể dùng bảng sau để đặc tả từng sink trước khi xây pipeline:

| Câu hỏi | Search | Vector | Analytics |
|---|---|---|---|
| Dữ liệu nguồn | Sản phẩm, danh mục, giá, trạng thái | Mô tả, nội dung, metadata quyền | Đơn hàng, sự kiện, sản phẩm, khách hàng |
| Đơn vị đích | Document theo ID | Một/nhiều embedding theo thực thể/chunk | Fact, dimension, aggregate |
| Phép biến đổi | Analyzer, gộp trường, mapping | Chuẩn hóa văn bản, chunk, embedding | Làm sạch, join, tổng hợp, window |
| ID/phiên bản | `productId` + source/component version | `productId` + content/model/chunk version | Business key + event/version |
| Cập nhật | Upsert/partial update | Re-embed khi nội dung đổi; metadata update khi có thể | Upsert fact, dimension history, recompute |
| Xóa | Delete/hide + chống resurrection | Delete chunks/metadata + manifest | Theo retention, audit và chính sách dữ liệu |
| Freshness mục tiêu | Giây đến chục giây (ví dụ) | Giây/phút tùy inference (ví dụ) | Phút/giờ hoặc theo kỳ báo cáo |
| Đối soát | ID, version, searchable fields | ID, số chunk, model version, ACL | Count, sum, watermark, fact correctness |

Những mức độ trễ trong bảng là ví dụ, phải được chuyển thành SLO đo được theo nhu cầu của sản phẩm.

### 18.1. Nên chọn cách đồng bộ nào?

**Tình huống A — Dữ liệu nhỏ, cập nhật ít, trễ 1 giờ chấp nhận được:** batch export định kỳ có thể đáp ứng, miễn có cơ chế xóa, watermark, replay và reconciliation.

**Tình huống B — Tìm kiếm sản phẩm cần cập nhật trong vài giây:** CDC hoặc outbox + stream thường thích hợp, kết hợp version guard và theo dõi search visibility.

**Tình huống C — Embedding tốn nhiều thời gian:** event stream + job queue/worker cho embedding, quản lý model version và atomic publication/read version hoặc cơ chế tương đương.

**Tình huống D — Báo cáo cần truy vết lịch sử:** ingest raw events/CDC vào tầng lưu trữ bền vững rồi xây fact/dimension/aggregate, có backfill và xử lý late-arriving events.

**Tình huống E — Nhiều nguồn độc lập:** cần định nghĩa nguồn chuẩn từng trường, component versions và quy tắc hợp nhất; không mặc định một event version đơn lẻ đại diện cho toàn bộ projection.

## 19. Những hiểu lầm cần tránh

**“Ghi thành công ở nguồn thì search ngay lập tức có dữ liệu mới.”** Không phải luôn đúng. CDC, broker, consumer, index refresh và các tác vụ biến đổi đều có độ trễ.

**“Dùng Kafka hay broker là tự có exactly-once đến mọi kho.”** Không đúng. Bảo đảm có phạm vi cụ thể; sink ngoài vẫn có retry, duplicate và race.

**“Có eventId rồi thì không còn dữ liệu đến sai thứ tự.”** Event ID giúp dedup một event, còn event version/ordering bảo vệ trạng thái mới nhất.

**“Snapshot xong rồi mới nghe stream là an toàn.”** Có thể mất các thay đổi xảy ra giữa hai giai đoạn. Cần mốc CDC/snapshot nhất quán hoặc cơ chế bắt kịp có kiểm chứng.

**“Dùng một timestamp để quyết định thay đổi nào mới hơn luôn đủ.”** Không nếu đồng hồ lệch, transaction commit thứ tự khác, nhiều dịch vụ nguồn hoặc timestamp độ phân giải không đủ. Nên ưu tiên version/sequence có bảo đảm rõ.

**“Chỉ mục vector chỉ cần upsert embedding mới.”** Không đủ nếu số chunk thay đổi, model version khác hoặc dữ liệu cũ phải được xóa.

**“Embeddings không chứa dữ liệu nhạy cảm vì là các con số.”** Không thể suy luận như vậy; cần kiểm soát nguồn, metadata, truy xuất và chính sách xóa.

**“Search và vector có thể quyết định trạng thái mua hàng cuối cùng.”** Không nên mặc định khi đó là read model có thể cập nhật trễ. Giao dịch quan trọng phải dựa vào nguồn có bảo đảm nghiệp vụ.

**“Số document giữa hai kho bằng nhau nghĩa là đồng bộ chính xác.”** Không; cần kiểm tra ID, version, trường quan trọng và dấu xóa.

**“Sửa consumer là tự sửa dữ liệu lịch sử.”** Không. Dữ liệu cũ cần backfill, replay hoặc rebuild theo phương án kiểm soát phiên bản.

**“Đưa lỗi vào DLQ nghĩa là đã xử lý xong.”** Không. DLQ vẫn cần sửa dữ liệu, replay và đo mức tồn đọng.

## 20. Bài tập tự vận dụng

### Bài tập 1: lỗi dual write

Một API cập nhật giá trong database thành công nhưng kết nối tới search bị timeout. API trả lỗi, client retry. Lần retry tạo một event khác, đồng thời người bán đã cập nhật giá lần nữa.

**Câu hỏi:** Những sai lệch nào có thể xảy ra? Thiết kế nào giúp giảm rủi ro?

**Gợi ý:** Cần tránh sự kiện cũ ghi đè giá mới, xử lý cập nhật một phần và duplicate. Có thể dùng outbox/CDC từ nguồn, ID/version ổn định và conditional upsert ở search. Không nên chỉ retry ghi search không có guard.

### Bài tập 2: tính freshness

Một sản phẩm commit tại nguồn lúc 10:00:00, event vào broker lúc 10:00:02, consumer bắt đầu 10:00:07, sink ghi thành công 10:00:09, search nhìn thấy cập nhật lúc 10:00:11.

**Câu hỏi:** End-to-end freshness lag là bao nhiêu? Vì sao không lấy broker consumer lag làm kết quả cuối?

**Gợi ý:** Từ 10:00:00 đến 10:00:11 là **11 giây**. Broker lag không bao gồm toàn bộ capture, transform, sink write và visibility.

### Bài tập 3: vector cập nhật sai thứ tự

Event v8 bắt đầu tính embedding lâu hơn v9. V9 ghi xong trước, nhưng v8 hoàn thành sau.

**Câu hỏi:** Nếu vector ID chỉ là `productId` và upsert không có version guard, điều gì xảy ra?

**Gợi ý:** V8 có thể ghi đè v9. Nên dùng source/content version, kiểm tra lúc công bố hoặc lưu vector theo phiên bản kèm cơ chế chuyển active version an toàn.

### Bài tập 4: delete và snapshot

Một sản phẩm v20 đã bị xóa; event delete vào search thành công. Batch snapshot cũ sau đó đưa lại v18.

**Câu hỏi:** Cần giữ điều kiện gì để không tái tạo dữ liệu?

**Gợi ý:** Không áp dụng snapshot v18 nếu sink đã biết tombstone/delete v20. Version guard và quy trình snapshot + CDC có mốc nhất quán là những thành phần cần có.

### Bài tập 5: analytics duplicate

Pipeline nhận hai lần sự kiện `OrderPaid(orderId=O1, amount=100)` và mỗi lần cộng 100 vào `daily_sales`.

**Câu hỏi:** Con số sai như thế nào và sửa ra sao?

**Gợi ý:** Tổng tăng 200 thay vì 100. Có thể khử trùng theo ID/sự kiện và tạo fact idempotent theo business key, rồi tổng hợp từ trạng thái đã chuẩn hóa hoặc dùng cơ chế update/retract đúng.

### Bài tập 6: chọn read model

Một nền tảng học trực tuyến cần: tìm khóa học theo từ khóa, gợi ý khóa học theo nội dung bài giảng và dashboard tỷ lệ hoàn thành theo tháng.

**Câu hỏi:** Ba nhu cầu đó khác nhau về cấu trúc dữ liệu dẫn xuất ra sao?

**Gợi ý:** Search có tài liệu khóa học và chỉ mục full-text; vector có chunk/embedding của nội dung cùng model version; analytics có fact học tập, thời gian, học viên và bảng tổng hợp theo tháng. Định danh, cách cập nhật, xóa và SLO của mỗi sink phải khác nhau theo nhu cầu.

### Bài tập 7: nhiều nguồn tạo một tài liệu search

Một tài liệu search cần `name` từ Product, `price` từ Pricing và `available` từ Inventory. Product v7, Pricing v12, Inventory v88.

**Câu hỏi:** Có thể dùng một trường `sourceVersion = 7` để chặn mọi event cũ không?

**Gợi ý:** Không. Mỗi thành phần có phiên bản riêng; cần component versions, quy tắc hợp nhất hoặc một snapshot chung có định nghĩa rõ.

### Bài tập 8: lập kế hoạch rebuild

Nhóm đổi embedding model, từ vector 384 chiều sang 768 chiều. Kho cũ đang phục vụ production và dữ liệu nguồn vẫn cập nhật liên tục.

**Câu hỏi:** Hãy mô tả kế hoạch không bỏ sót thay đổi.

**Gợi ý:** Dựng index/namespace mới, snapshot có mốc CDC, tính embedding mới, catch-up event, xác nhận độ đầy đủ và chất lượng, chuyển truy vấn, rồi dọn index cũ khi bảo đảm an toàn. Cần đảm bảo không trộn hai embedding space không tương thích.

## 21. Kết luận

Đồng bộ dữ liệu gốc sang kho tìm kiếm, vector hoặc phân tích là một cách **xây nhiều read model chuyên biệt trên cùng dữ liệu nghiệp vụ**. Search tối ưu cho từ khóa và bộ lọc; vector tối ưu cho tìm kiếm tương đồng ngữ nghĩa; analytics tối ưu cho lịch sử, tổng hợp và báo cáo. Những mô hình này thường cập nhật qua CDC, outbox, event stream hoặc batch thay vì được coi là nơi ghi nhận giao dịch chính.

Một hệ đồng bộ đáng tin cậy cần đồng thời giải quyết **thu nhận đầy đủ thay đổi, ID và phiên bản ổn định, idempotency, thứ tự cập nhật, xóa dữ liệu, snapshot/replay, rebuild và đối soát**. Cần đo độ mới từ lúc nguồn commit đến khi người dùng thực sự đọc thấy trạng thái mới ở kho đích; chỉ consumer đã ack hoặc broker lag thấp chưa chứng minh dữ liệu đúng.

Khi thiết kế, hãy bắt đầu từ **nguồn sự thật của từng trường và yêu cầu chính xác/độ mới của từng kiểu truy vấn**. Sau đó mới chọn pipeline đồng bộ và cấu trúc kho đích phù hợp. Cách tiếp cận này giúp các mô hình NoSQL chuyên biệt bổ trợ nhau mà vẫn giữ được khả năng phục hồi và giải thích kết quả.

