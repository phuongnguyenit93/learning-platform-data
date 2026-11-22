# Sao chép dữ liệu có chủ đích và trách nhiệm cập nhật trong Microservices

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Quyền sở hữu dữ liệu.
>
> **Mục tiêu:** biết khi nào nên sao chép dữ liệu giữa các service mà không phá vỡ data ownership; phân biệt dữ liệu nguồn, snapshot nghiệp vụ, cache, read model và bản sao phân tích; xác định bên nào phát hành cập nhật, bên nào áp dụng và vận hành bản sao; chọn mức nhất quán phù hợp; xử lý dữ liệu đến trễ, lặp, sai thứ tự, mất event, backfill, đối soát và quyền riêng tư.

## 1. Sao chép dữ liệu không đồng nghĩa vi phạm Database per Service

Một trong những hiểu lầm phổ biến là: “Mỗi microservice sở hữu database riêng, do đó không được có cùng một thông tin ở hai service”. Cách hiểu này quá cứng nhắc.

Trên thực tế, một luồng nghiệp vụ thường cần một số dữ liệu xuất phát từ context khác. Ví dụ:

- Order cần tên và giá sản phẩm tại thời điểm khách mua để lập lịch sử đơn hàng.
- Search cần tên, danh mục, trạng thái hiển thị và thuộc tính sản phẩm để dựng chỉ mục tìm kiếm.
- Recommendation cần một số thuộc tính Catalog phục vụ thuật toán gợi ý.
- Shipping cần tên người nhận và địa chỉ giao cho một kiện hàng cụ thể.
- Analytics cần số liệu đã phát sinh từ Order, Payment và Inventory để tổng hợp báo cáo.

Nếu mọi service phải gọi đồng bộ sang nguồn dữ liệu khác cho mỗi lần hiển thị hoặc xử lý, hệ có thể tạo chuỗi gọi mạng dài, coupling về thời gian chạy và các điểm lỗi mới. Một **bản sao cục bộ được thiết kế có chủ đích** có thể giảm số lời gọi, cho phép mô hình đọc phù hợp use case và giảm phụ thuộc vào thời điểm service nguồn đang online.

Nhưng sao chép không tự động an toàn. Nếu không quy định owner, nguồn cập nhật, semantics sự kiện và cơ chế khôi phục, hai bản dữ liệu có thể âm thầm phân kỳ. Consumer có thể đưa ra quyết định sai dựa trên dữ liệu cũ, hoặc dữ liệu nhạy cảm tồn tại lâu hơn yêu cầu.

**Nguyên tắc:** được phép có nhiều bản biểu diễn dữ liệu, nhưng phải xác định rõ **bản nào có thẩm quyền về điều gì**, **bản nào chỉ phục vụ mục đích cụ thể**, và **ai chịu trách nhiệm đồng bộ, sửa lỗi và xóa dữ liệu**.

### 1.1. Ví dụ đơn giản

~~~text
                          Product Catalog
                         (nguồn mô tả hiện tại)
                                  |
                   ProductPublished / ProductUpdated
                                  |
                   +--------------+--------------+
                   |              |              |
                   v              v              v
            Search Index    Recommendation   Local Read Model
             (bản chiếu)     Projection       (bản chiếu)
                                  |
Customer đặt đơn                  |
        |                         |
        v                         |
      Order Service <-------------+
       lưu PurchasedItemSnapshot
       (thông tin đã cam kết lúc mua)
~~~

Catalog có thẩm quyền về mô tả sản phẩm hiện tại. Search là owner kỹ thuật của chỉ mục tìm kiếm và cách cập nhật chỉ mục, nhưng không được tự sửa nghĩa vụ của Catalog. Order lại có thẩm quyền với **snapshot đã chốt của dòng đơn hàng**: nó không nhất thiết bị viết lại khi Catalog đổi tên hoặc giá niêm yết sau ngày mua.

Đây là khác biệt quan trọng giữa “bản sao của dữ liệu hiện tại” và “sự kiện/bằng chứng lịch sử đã trở thành dữ liệu nghiệp vụ của một bounded context khác”.

## 2. Những khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ai quyết định giá trị chuẩn? |
| --- | --- | --- |
| Source of truth | Nguồn có thẩm quyền cho một sự thật nghiệp vụ tại thời điểm hiện tại | Service owner của sự thật đó |
| Authoritative write | Thao tác làm thay đổi dữ liệu chuẩn hoặc invariant | Chỉ owner hoặc cơ chế được ủy quyền |
| Replica / projection | Bản sao suy ra từ nguồn, thường dùng cho đọc | Giá trị nguồn do producer quyết định; projection do consumer duy trì |
| Cache | Bản sao tạm để tăng tốc, có TTL/invalidation | Nguồn ban đầu hoặc contract cache |
| Read model | Cấu trúc tối ưu cho truy vấn, có thể tổng hợp nhiều nguồn | Owner từng nguồn; consumer sở hữu cách tạo model |
| Historical snapshot | Bản ghi tình trạng đã được sử dụng trong quyết định/giao dịch quá khứ | Context tạo ra sự kiện nghiệp vụ có thẩm quyền với snapshot của chính nó |
| Integration event | Thông báo công khai về sự kiện đã xảy ra | Producer công bố và cam kết semantics |
| Change Data Capture (CDC) | Trích thay đổi từ log lưu trữ của nguồn | Database owner kiểm soát việc xuất bản dữ liệu |
| Materialized view | Dữ liệu đã tính sẵn cho truy vấn | View owner duy trì; nguồn nghiệp vụ vẫn là nguồn chuẩn |
| Eventual consistency | Bản sao có thể tạm thời cũ và hội tụ sau khi cập nhật được áp dụng | Hai bên cam kết điều kiện hội tụ và vận hành pipeline |

Một từ như “Customer” có thể mang nghĩa khác nhau trong CRM, Billing và Shipping. Không nên mặc định mọi service phải chia sẻ một CustomerEntity hoặc giữ cùng một bản Customer hoàn chỉnh. Nên nói rõ **những thuộc tính và ngữ nghĩa nào thực sự cần được sao chép**.

## 3. Quyền sở hữu dữ liệu là theo sự thật nghiệp vụ, không chỉ theo tên bảng

Một service có thể sở hữu một phần ý nghĩa của đối tượng tổng quát. Ví dụ:

- Catalog quyết định tên/mô tả sản phẩm hiện hành.
- Pricing quyết định báo giá hợp lệ theo điều kiện kinh doanh.
- Inventory quyết định lượng hàng có thể giữ tại thời điểm reservation.
- Order quyết định giá đã được chấp nhận và snapshot trong đơn.
- Payment quyết định trạng thái một giao dịch thanh toán.

Vì vậy, “giá sản phẩm” ở Pricing và “giá dòng đơn” trong Order có thể giống nhau tại thời điểm đặt hàng nhưng **không có cùng vòng đời**.

~~~text
Pricing: CurrentQuote
    amount = 250000
    validUntil = 10:15

Order: PurchasedItem
    agreedAmount = 250000
    placedAt = 10:13

Sau 10:15, Pricing cập nhật thành 270000.
Order không tự động sửa đơn đã chốt thành 270000.
~~~

Quyền ghi độc lập không nhất thiết tạo mâu thuẫn nếu hai khái niệm đã được tách rõ. Ngược lại, nếu Search tự cập nhật tên sản phẩm nguồn rồi đẩy ngược về Catalog, có thể hình thành multi-writer không chủ đích.

### 3.1. Ba câu hỏi cho mỗi trường dữ liệu

1. **Ai có thẩm quyền quyết định?** Ai có đủ quy tắc nghiệp vụ để nói giá trị này đúng?
2. **Ai đang giữ bản sao để làm gì?** Tìm kiếm, cache, hiển thị, kiểm toán, tối ưu latency hay quyết định nghiệp vụ?
3. **Khi giá trị thay đổi, chuyện gì phải xảy ra?** Cập nhật tất cả bản sao, chỉ cập nhật những projection nhất định, hay giữ nguyên historical snapshot?

Không trả lời được ba câu hỏi trên thì chưa nên sao chép thêm dữ liệu.

## 4. Sao chép có chủ đích phải phục vụ một mục tiêu cụ thể

Những mục tiêu hợp lý thường gặp:

- **Giảm temporal coupling:** consumer có thể đọc bản sao khi producer tạm thời không phản hồi.
- **Giảm độ trễ:** tránh một remote call cho từng dòng dữ liệu trong response.
- **Tối ưu mô hình đọc:** dựng search index, aggregate báo cáo hoặc read model khác với transaction schema.
- **Giảm tải nguồn:** lưu projection để nhiều truy vấn không dồn vào OLTP database.
- **Khác biệt SLA hoặc vùng địa lý:** đặt bản sao dữ liệu được phép stale gần người sử dụng.
- **Lưu dấu vết lịch sử:** chụp điều kiện và giá trị tại thời điểm cam kết đơn hàng.
- **Cô lập blast radius:** lỗi một dependency không làm hỏng tất cả các luồng không cần dữ liệu mới nhất.
- **Phân tích và machine learning:** xây nguồn dữ liệu chuyên dụng, được quản trị độc lập khỏi business transaction.

Các động cơ không đủ rõ: “để giảm số JOIN trên sơ đồ”, “vì nhiều service cần ProductEntity”, “copy toàn bộ bảng cho tiện” hoặc “chuyển tất cả sang Kafka cho đúng microservices”.

Mỗi bản sao phải có **quyết định kiến trúc, mục tiêu đo được và giới hạn sử dụng**. Nếu không, duplication tăng nhanh theo số context và khó xóa/khôi phục.

## 5. Các dạng sao chép và đánh đổi

### 5.1. Cache cục bộ

Cache lưu dữ liệu tạm để giảm read latency. Nó có thể nằm trong process, Redis hoặc một cache cluster. Phần lớn cache không được xem là nguồn chuẩn; khi lỗi có thể làm mới từ source theo contract.

Câu hỏi thiết kế:

- TTL bao lâu? Có phù hợp với dữ liệu và rủi ro không?
- Có invalidation qua event không? Nếu event mất thì sao?
- Khi miss, có được gọi nguồn ngay hay phải chấp nhận degraded response?
- Có thể cache thông tin nhạy cảm không? Mã hóa, phân quyền, eviction thế nào?
- Dữ liệu nào không được phép stale khi quyết định?

Không dùng cache tồn kho 60 giây để tự xác nhận bán đơn vị hàng cuối cùng nếu Inventory có invariant chống oversell, trừ khi kiến trúc có quota/escrow rõ.

### 5.2. Local read model / CQRS projection

Consumer duy trì dữ liệu tối ưu cho truy vấn của mình, thường từ events của một hoặc nhiều producer.

~~~text
Catalog ProductUpdated -> Search Consumer -> Search Index
Order OrderConfirmed   -> Reporting Consumer -> Order Summary
Payment Captured       -> Reporting Consumer -> Revenue Summary
~~~

Projection có schema theo nhu cầu truy vấn, không nhất thiết giống bảng của producer. Đổi internal schema của Catalog không bắt buộc Search sửa nếu public ProductUpdated contract không đổi.

### 5.3. Snapshot nghiệp vụ

Snapshot ghi lại sự thật **tại lúc một quyết định được chốt**. Ví dụ tên người nhận, địa chỉ giao và giá tại thời điểm khách đặt hàng. Nó có thể trở thành dữ liệu nguồn của Order/Shipping cho tác vụ tương ứng.

Không tự động ghi đè snapshot lịch sử bằng mọi sự kiện cập nhật từ upstream. Nếu địa chỉ khách hiện tại thay đổi, điều đó không chứng minh phải thay địa chỉ của kiện hàng đã xuất kho; chính sách thay đổi sau khi đặt hàng cần một command nghiệp vụ riêng.

### 5.4. Search index

Search index tổ chức dữ liệu theo thuật toán tìm kiếm và ranking. Catalog vẫn sở hữu thông tin sản phẩm, Search sở hữu việc build/rebuild index và freshness, dữ liệu public được công bố qua event/schema.

Index có thể stale. Search có thể hiển thị một sản phẩm mới được cập nhật trễ, nhưng thao tác mua cần một bước xác nhận từ owner của điều kiện thực thi.

### 5.5. Analytical warehouse / reporting

Báo cáo đa miền thường cần snapshot hoặc stream dữ liệu của nhiều owner, có thể trễ vài phút. Đây là mục đích khác với xác nhận payment thành công trong checkout.

Cần định nghĩa độ trễ báo cáo, độ hoàn chỉnh của batch, thời điểm khóa sổ, quyền truy cập PII, cách sửa số liệu sau hoàn/hủy và đối soát với nguồn nghiệp vụ.

### 5.6. Replica cùng hệ quản trị cơ sở dữ liệu

Database read replica có thể được dùng để tăng công suất đọc hoặc dự phòng. Nhưng đây là **cơ chế nhân bản ở tầng hạ tầng**, khác với việc một service tiêu thụ public event để xây local domain projection.

Read replica thường sao chép schema và dữ liệu gốc tương đối sát, chịu replication lag và failure modes riêng. Nó không làm biến mất ownership; service khác không tự nhiên được quyền truy vấn mọi bảng private chỉ vì endpoint là read replica.

### 5.7. Multi-region replica

Bản sao đặt tại vùng khác hỗ trợ latency và recovery. Nếu mọi vùng đều có quyền ghi, hệ phải giải quyết conflict, ordering, quorum, phân vùng mạng và các invariant rất cẩn thận. Không suy ra rằng “mỗi service có local copy” là cho phép tất cả cùng ghi vào một sự thật nghiệp vụ.

## 6. Ma trận quyết định khi lựa chọn phương án

| Nhu cầu | Phương án thường xem xét | Điều phải định nghĩa |
| --- | --- | --- |
| Đọc dữ liệu ít đổi, có thể stale | Cache có TTL | Freshness, invalidation, fallback |
| Hiển thị thông tin tổng hợp nhiều service | API composition hoặc read model | Latency, availability, consistency |
| Tìm kiếm full-text và filter | Search projection | Event pipeline, index freshness, rebuild |
| Lịch sử giá/tên của đơn đã chốt | Immutable business snapshot | Thời điểm ghi, điều kiện sửa, retention |
| Báo cáo doanh thu gần thời gian thực | Materialized projection / event pipeline | Lag, correction events, reconciliation |
| Truy vấn nghiệp vụ cần dữ liệu mạnh | Gọi owner hoặc mô hình phân quyền phù hợp | Invariant, deadline, failure policy |
| Cross-region đọc dữ liệu | Replica/cache theo vùng | Lag, failover, staleness |
| Ghi song song một nguồn dữ liệu | Thiết kế multi-writer có chủ đích | Conflict resolution, consensus, ownership |

Nếu truy vấn cần kết quả mới nhất và không thể chấp nhận dữ liệu cũ, cố tạo cache/projection chỉ để bỏ cuộc gọi owner có thể gây lỗi tính đúng đắn. Nếu chỉ cần tìm kiếm danh mục, buộc mọi click/search gọi trực tiếp Catalog database lại có thể gây coupling và tải không cần thiết.

## 7. Trách nhiệm cập nhật: producer và consumer làm gì?

Một pipeline sao chép hiệu quả có **hai nhóm trách nhiệm tách biệt nhưng phối hợp được**.

### 7.1. Trách nhiệm của producer / owner

Service nguồn có trách nhiệm:

1. Xác định ngữ nghĩa và dữ liệu có thẩm quyền.
2. Chỉ phát hành **những thay đổi được phép công bố**.
3. Định nghĩa schema, event type, version, ID, timestamp và semantics.
4. Bảo vệ invariant và commit dữ liệu nguồn bằng transaction/cơ chế phù hợp.
5. Không phát event tuyên bố thành công trước khi trạng thái nguồn được commit đáng tin cậy, trừ khi contract công bố trạng thái trung gian.
6. Có cơ chế publish tin cậy, ví dụ outbox/CDC khi phù hợp.
7. Duy trì cửa sổ tương thích contract và chính sách deprecation.
8. Cung cấp cách lấy snapshot/backfill hoặc tra cứu nguồn để khôi phục projection nếu cần.
9. Phát tín hiệu correction, deletion hoặc tombstone theo chính sách dữ liệu.
10. Cung cấp observability phù hợp về event backlog, lỗi phát hành và dữ liệu chưa công bố.

Producer **không nhất thiết phải tự cập nhật database của mọi consumer**. Nếu nó tự kết nối và ghi trực tiếp vào nhiều database khác nhau, sẽ tạo distributed write coupling và khó rollback khi một destination lỗi.

### 7.2. Trách nhiệm của consumer / projection owner

Consumer có trách nhiệm:

1. Chỉ nhận những dữ liệu thực sự cần theo hợp đồng đã công bố.
2. Ánh xạ sự kiện sang schema/mô hình của mình.
3. Xác định freshness/SLO của bản sao cho use case.
4. Xử lý duplicate, out-of-order và retry một cách idempotent.
5. Quản lý local storage, index, migrations, encryption và quyền truy cập.
6. Theo dõi consumer lag, dead-letter queue và lỗi schema.
7. Có khả năng replay, rebuild hoặc đối soát khi event bị mất.
8. Xử lý correction/deletion và chính sách retention.
9. Quy định hành vi khi bản sao stale hoặc chưa khởi tạo xong.
10. Không tạo ra một cập nhật có thẩm quyền trái với owner.

Consumer được quyền thiết kế index cho Search hoặc bảng Reporting, nhưng **không được tự phát minh sự thật nghiệp vụ nguồn** rồi đồng bộ ngược nếu không có giao thức đồng sở hữu rõ.

### 7.3. Trách nhiệm chung và hợp đồng vận hành

Những điểm phải được thống nhất: quyền truy cập event stream, giới hạn schema, khả năng replay, retention của broker, cách phát sự kiện sửa/xóa, độ trễ chấp nhận, xử lý version cũ, trách nhiệm incident, cách trao đổi khi producer thay behavior.

Ranh giới trách nhiệm cần đủ rõ để khi một dashboard không cập nhật, đội có thể xác định: producer chưa publish, broker lag, consumer lỗi parser hay read model bị corrupt?

## 8. Tránh “dual write” ngẫu nhiên sang nhiều database

Một anti-pattern:

~~~text
Order Service
    |
    +-- UPDATE order_db.orders
    |
    +-- UPDATE reporting_db.order_summary
    |
    +-- PUBLISH OrderConfirmed
~~~

Nếu UPDATE order_db thành công nhưng reporting_db lỗi, hệ sẽ phân kỳ. Nếu publish event thất bại sau DB commit, consumer không nhận được sự kiện. Retry toàn request có thể làm lặp nghiệp vụ khác.

**Một transaction cục bộ thông thường không làm ba thao tác trên nguyên tử.**

### 8.1. Transactional Outbox

Một cách phổ biến giảm rủi ro mất event:

~~~text
Order database transaction
    +-- UPDATE orders SET status = CONFIRMED
    +-- INSERT INTO order_outbox(event_id, type, payload, ...)
COMMIT

Outbox dispatcher
    -> publish OrderConfirmed
    -> broker

Reporting Consumer
    -> idempotent UPDATE local read model
~~~

Outbox bảo đảm dữ liệu nghiệp vụ và bản ghi cần phát event được ghi trong cùng transaction local, nếu cùng database/transaction boundary. Nó **không bảo đảm broker delivery duy nhất một lần** hoặc consumer xử lý duy nhất một lần. Dispatcher có thể gửi lại khi không biết ACK đã nhận chưa, nên consumer phải xử lý duplicate.

### 8.2. Ví dụ schema outbox

~~~sql
CREATE TABLE order_outbox (
    event_id       UUID PRIMARY KEY,
    aggregate_id   VARCHAR(100) NOT NULL,
    aggregate_ver  BIGINT NOT NULL,
    event_type     VARCHAR(100) NOT NULL,
    schema_version INTEGER NOT NULL,
    occurred_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    payload        JSONB NOT NULL,
    published_at   TIMESTAMP WITH TIME ZONE
);

-- Cập nhật order và insert outbox phải ở cùng
-- transaction cục bộ của Order Service.
~~~

Schema trên mang tính minh họa PostgreSQL. Sản phẩm thực tế cần indexes, retention, batching, locking/lease, restart/retry, monitoring và bảo mật payload. Đừng lưu toàn bộ dữ liệu nhạy cảm vào outbox chỉ vì JSON thuận tiện.

### 8.3. Khi nào dùng CDC?

Change Data Capture có thể đọc transaction log và phát các thay đổi database hoặc outbox. Nó hữu ích khi cần nhân bản thay đổi liên tục và giảm phụ thuộc vào cách ứng dụng trực tiếp publish message.

Nhưng **raw row-level CDC** thường gắn consumer vào internal table/column names, có nguy cơ làm database schema trở thành contract ngầm. Nếu dùng CDC, nên cân nhắc outbox pattern hoặc lớp chuyển đổi từ thay đổi lưu trữ sang **public business events** để giữ ownership.

CDC cũng cần quản lý snapshot ban đầu, transaction ordering, schema evolution, lag, resume offsets, retention và quyền truy cập log.

## 9. Thiết kế event contract cho đồng bộ dữ liệu

Không nên phát event mơ hồ như “EntityUpdated” chứa toàn bộ object nội bộ mà không mô tả semantics.

Một public event mẫu:

~~~json
{
  "eventId": "evt-20481",
  "eventType": "ProductDisplayInfoChanged",
  "schemaVersion": 2,
  "aggregateType": "Product",
  "aggregateId": "sku-100",
  "aggregateVersion": 42,
  "occurredAt": "2026-11-11T08:00:00Z",
  "producer": "catalog-service",
  "data": {
    "name": "Bình giữ nhiệt",
    "category": "Outdoor",
    "visibility": "VISIBLE"
  }
}
~~~

Các trường có mục đích:

- **eventId**: định danh duy nhất để deduplication/trace.
- **eventType**: ý nghĩa thay đổi được công bố.
- **schemaVersion**: version của cấu trúc và semantics.
- **aggregateId**: biết đối tượng cần cập nhật.
- **aggregateVersion**: hỗ trợ sắp thứ tự cập nhật của một aggregate.
- **occurredAt**: thời điểm producer ghi nhận sự kiện; hữu ích để đo lag nhưng không thay thế version/ordering.
- **producer**: service có thẩm quyền.
- **data**: tập trường cần thiết và được phép công bố.

Không phải event nào cũng cần mọi trường; cần chọn contract phù hợp transport và use case. Dù có eventId, một consumer vẫn phải bảo đảm việc cập nhật local projection và ghi nhận event đã xử lý diễn ra an toàn.

### 9.1. Event notification hay event-carried state transfer?

**Event notification:** “ProductChanged(sku)” và consumer gọi API Catalog để lấy phiên bản mới. Payload nhỏ nhưng phụ thuộc vào availability/latency của Catalog khi xử lý event.

**Event-carried state transfer:** sự kiện mang đủ những thuộc tính được công bố để consumer cập nhật projection mà không phải gọi lại producer. Giảm temporal coupling, nhưng có thêm trách nhiệm kiểm soát PII, version và khả năng payload lớn.

Có thể kết hợp cả hai. Mấu chốt là contract phải nói rõ **event phản ánh một thay đổi hay chứa toàn bộ trạng thái cần thiết**, và consumer nên xử lý ra sao khi bỏ lỡ version.

### 9.2. Event một phần và event snapshot

- **Delta event:** chỉ nêu phần thay đổi. Nhỏ, nhưng dễ yêu cầu thứ tự và replay đầy đủ.
- **State snapshot event:** mô tả phần trạng thái công khai mới nhất. Có thể áp dụng version cao hơn trực tiếp, giúp rebuild dễ hơn, nhưng payload lớn và phải xử lý deletion/field removal rõ.

Nếu event chỉ mang field name mới, consumer cần hiểu field nào phải xóa hoặc giữ. Những ambiguity nhỏ gây lệch dữ liệu lâu dài.

## 10. Idempotency: event có thể đến nhiều lần

Message broker hoặc dispatcher thường ưu tiên không làm mất message; do đó một event có thể được gửi/nhận nhiều lần. Consumer không được tăng số liệu doanh thu hai lần chỉ vì xử lý lại PaymentCaptured.

Ví dụ:

~~~text
PaymentCaptured(eventId=E1, paymentId=P9, amount=250000)
  -> Consumer nhận E1
  -> Ghi revenue +250000
  -> ACK bị mất

Broker gửi lại E1
  -> Consumer nhận E1 lần nữa
  -> Phải bỏ qua phần tác động đã commit
~~~

Một pattern đơn giản:

~~~sql
BEGIN;

-- Bảng processed_event phải cùng transaction
-- với thay đổi projection, nếu dùng một database.
INSERT INTO processed_events(consumer_name, event_id)
VALUES ('revenue-projector', :event_id)
ON CONFLICT DO NOTHING;

-- Chỉ áp dụng cập nhật revenue khi insert thực sự
-- tạo bản ghi mới; nếu event_id đã tồn tại thì bỏ qua.

COMMIT;
~~~

Ví dụ này minh họa **nguyên tắc** chứ không phải SQL hoàn chỉnh cho nghiệp vụ doanh thu. Trong thực tế code phải kiểm tra rows affected hoặc cơ chế atomic tương ứng để không cập nhật projection nếu event đã xử lý. Với hai storage khác nhau, việc đánh dấu processed và ghi projection cần chiến lược nhất quán riêng.

### 10.1. Idempotency theo event ID và theo entity version

Event ID giúp deduplication bản giao lặp của một event. Nhưng hai event khác nhau vẫn có thể đại diện cho những trạng thái đã bị thay thế. Dùng aggregate version để bỏ qua update cũ hoặc phát hiện khoảng trống:

~~~text
ProductVersion 41 -> đã áp dụng
ProductVersion 43 -> đến trước version 42

Consumer:
  - Nếu event là snapshot đầy đủ và quy tắc cho phép,
    có thể áp dụng version 43.
  - Nếu event là delta cần lần lượt 42 rồi 43,
    phải chờ/replay hoặc đồng bộ lại.
~~~

Đừng luôn chọn “event có occurredAt mới nhất” nếu đồng hồ giữa các hệ không đồng bộ hoặc producer có thể publish trễ. Với một aggregate do một owner ghi, monotonic version hoặc sequence number thường đáng tin hơn timestamp đơn thuần.

### 10.2. Exactly-once không phải phép màu

Ngay cả khi broker hoặc stream processor cung cấp một số đảm bảo exactly-once trong phạm vi cụ thể, tác động lên database ngoài broker, HTTP API hoặc side effect khác vẫn có thể bị lặp sau crash/retry. Phải nêu rõ **phạm vi đảm bảo** và làm consumer idempotent ở nơi cần.

## 11. Event đến sai thứ tự và dữ liệu cuối cùng bị ghi đè

Ví dụ Catalog xuất:

~~~text
Version 100: name = "Áo xanh"
Version 101: name = "Áo xanh mới"

Consumer nhận version 101 trước.
Sau đó nhận lại version 100.
~~~

Nếu consumer chỉ UPDATE theo message đến cuối, bản sao bị lùi về tên cũ. Có thể giải quyết bằng một phép ghi có điều kiện:

~~~sql
-- Projection lưu last_applied_version.
UPDATE product_projection
SET name = :name,
    last_applied_version = :incoming_version
WHERE product_id = :id
  AND last_applied_version < :incoming_version;
~~~

Trong thực tế cần xử lý trường hợp chưa tồn tại row (UPSERT), concurrent consumers, transaction race và event type cụ thể. Quy tắc version chỉ hoạt động khi producer bảo đảm version tăng theo cùng một đối tượng có thẩm quyền.

Nếu một event là delta thay vì state snapshot, không thể đơn giản bỏ version trung gian. Consumer phải phát hiện gap và replay hoặc lấy snapshot mới.

### 11.1. Ordering trong broker

Các hệ message thường có ordering theo partition hoặc key, không nhất thiết theo toàn bộ topic. Khi cần thứ tự theo một Product ID, có thể partition theo aggregateId và dùng cùng producer/sequence policy. Nhưng vẫn phải bảo vệ khi replay, rebalance hoặc xử lý nhiều consumer.

Không ép một topic toàn hệ vào một partition chỉ để có thứ tự tổng quát nếu nghiệp vụ chỉ yêu cầu thứ tự theo entity. Điều đó có thể giới hạn throughput không cần thiết.

## 12. Backfill: tạo bản sao đầu tiên an toàn

Một consumer mới cần lấy tất cả sản phẩm hiện có trước khi xử lý các cập nhật tiếp theo. Nếu chỉ bắt đầu lắng nghe events từ hôm nay, những sản phẩm cũ chưa hề cập nhật sẽ không có trong projection.

Một quy trình backfill thường cần:

1. Chọn nguồn snapshot được hỗ trợ bởi owner, ví dụ export hoặc query API có cursor.
2. Xác định checkpoint/watermark liên hệ snapshot và stream cập nhật.
3. Tạo projection từ snapshot theo version/updatedAt có semantics rõ.
4. Thu nhận hoặc replay những events phát sinh trong lúc backfill.
5. Áp dụng events idempotently, đúng version.
6. Kiểm tra counts, checksums hoặc invariants thích hợp.
7. Chuyển đọc sang projection khi lag và correctness đạt ngưỡng công bố.
8. Giữ cách rollback nếu dữ liệu chưa đủ tin cậy.

### 12.1. Nguy cơ race giữa snapshot và event stream

~~~text
T1: Snapshot đọc Product v10
T2: Product được đổi thành v11
T3: Consumer bắt đầu đọc events từ sau T2
=> Consumer có thể bỏ lỡ v11.
~~~

Nếu không có checkpoint liên kết hai nguồn, bản sao có thể sai vĩnh viễn. Một cách giải quyết là **bắt đầu capture stream trước khi snapshot rồi replay**, hoặc dùng **consistent snapshot + log position** từ CDC/hạ tầng, hoặc public export có version cursor chính xác theo contract. Chi tiết phụ thuộc DBMS và broker.

Không khẳng định một timestamp lấy từ đồng hồ consumer tự động tạo checkpoint nhất quán với transaction log của producer.

### 12.2. Rebuild projection

Search index có thể cần rebuild sau khi đổi tokenizer, schema hoặc mapping. Phương án an toàn thường là:

~~~text
Old index v1 -> đang phục vụ traffic

Build new index v2
   -> backfill
   -> replay update events
   -> đối soát
   -> switch alias/traffic

Old index giữ lại để rollback theo policy.
~~~

Đừng xóa index đang phục vụ trước khi bản mới đủ dữ liệu nếu availability/freshness là yêu cầu quan trọng.

## 13. Reconciliation: bản sao có thể sai dù pipeline đang chạy

Event consumer không báo lỗi không có nghĩa bản sao chắc chắn giống nguồn. Có thể có bugs trong mapper, event bị bỏ sót trước khi bật retention, schema drift, logic xóa sai hoặc dữ liệu nguồn được sửa thủ công không phát event.

**Reconciliation** là quá trình đối chiếu có chủ đích giữa nguồn có thẩm quyền và bản sao, phát hiện chênh lệch rồi sửa theo policy.

Một chiến lược:

- Đối chiếu counts theo tenant/partition/ngày để phát hiện thiếu bất thường.
- So sánh version cuối cùng đã áp dụng cho từng aggregate quan trọng.
- Tính checksum/hash trên tập thuộc tính được công bố ở từng phân vùng.
- Lấy mẫu có chủ đích đối với dữ liệu nhạy hoặc quan trọng.
- Có job sửa projection bằng re-fetch/replay/snapshot.
- Ghi audit về số record mismatch, nguyên nhân và thời gian khôi phục.
- Phân biệt dữ liệu stale tạm thời với dữ liệu sai vĩnh viễn.

Cần tránh đối chiếu toàn bộ mọi row trong peak traffic, gây tải lên nguồn OLTP. Có thể chạy theo partition, rate limit và dùng snapshot/export phù hợp.

### 13.1. Reconciliation của dữ liệu tiền và trạng thái

Với Payment, reconciliation có thể cần kiểm tra giao dịch thực tế ở gateway hoặc sổ cái với trạng thái Payment owner. Consumer báo cáo doanh thu chỉ nên nhận những trạng thái public phù hợp, không tự đưa ra quyết định thanh toán từ cache của mình.

Việc báo cáo sai số có thể được sửa bằng correction event hoặc rebuild; nhưng **không được “chữa” sai lệch bằng cách cập nhật ngược transaction Payment** nếu Reporting không có thẩm quyền.

## 14. Data freshness và consistency là một cam kết cần đo

Không phải mọi projection đều phải đồng bộ trong vài mili giây. Mức độ cần thiết tùy use case:

| Use case | Có thể chấp nhận stale? | Quyết định bắt buộc |
| --- | --- | --- |
| Search danh mục sản phẩm | Có thể vài giây, theo SLO cụ thể | Hiển thị kết quả tìm kiếm |
| Dashboard vận hành | Có thể chậm theo cửa sổ công bố | Báo cáo/giám sát |
| Lịch sử đơn đã chốt | Snapshot là dữ liệu chuẩn của đơn | Hiển thị đúng điều đã cam kết |
| Gợi ý sản phẩm | Thường có thể stale một phần | Tính toán ranking |
| Kiểm tra tồn trước khi chốt giữ hàng | Không tùy tiện dựa vào projection stale | Quyết định reservation thuộc Inventory |
| Kiểm tra số dư/credit limit | Cần authority/invariant tương ứng | Không tự cho phép dựa vào cache cũ |
| Thanh toán/hoàn tiền | Phụ thuộc quyết định của Payment | Không kết luận từ event chưa rõ |
| Quyền truy cập và khóa tài khoản | Thường yêu cầu freshness chặt | Phải có revoke/cache policy an toàn |

Những mức thời gian trong bảng chỉ là **loại yêu cầu để thảo luận**, không phải giá trị SLO mặc định. Nên định nghĩa bằng văn bản: “95% bản cập nhật hiện trên Search trong X giây, 99.9% trong Y giây”, rồi đo end-to-end từ commit của producer đến query tại consumer.

### 14.1. Staleness có nhiều chiều

- **Publication lag:** từ DB commit đến message sẵn sàng trên broker.
- **Transport lag:** message chờ và di chuyển qua broker.
- **Processing lag:** consumer nhận đến khi projection commit.
- **Serving lag:** projection đã commit nhưng cache/index serving chưa refresh.
- **Replay lag:** consumer khôi phục sau outage, còn nợ event cũ.

Một dashboard chỉ theo dõi broker consumer lag có thể bỏ qua sự chậm trễ trước khi publish hoặc sau khi index update. Cần có timestamp/version và metrics qua toàn pipeline.

### 14.2. Đọc dữ liệu cũ phải được nhận diện

Với giao diện nội bộ, có thể hiển thị thời điểm làm mới cuối cùng. Với API, có thể công bố lastUpdatedAt/projectionVersion hoặc degraded status khi freshness quá ngưỡng. Nhưng khi liên quan invariant mạnh, không chỉ “cảnh báo dữ liệu cũ” rồi vẫn cho phép commit sai.

Một lựa chọn đúng có thể là **không thực hiện thao tác** nếu không thể xác nhận điều kiện mới nhất từ owner; chi phí availability là tradeoff có chủ đích.

## 15. Sao chép cho mục đích đọc không được biến thành multi-writer ngầm định

Phân biệt hai mô hình:

~~~text
SINGLE WRITER + MULTIPLE READ MODELS

       Catalog
         |
  ProductUpdated event
    /      |        \
 Search  Reco     Reporting

Không có cạnh "Search -> UPDATE Catalog" tùy tiện.
~~~

~~~text
MULTI-WRITER (cần giao thức riêng)

Region A -----+
              +--> cùng cập nhật một giá trị nghiệp vụ
Region B -----+
              |
          Conflict resolution/consensus/invariant
~~~

Nếu cả hai nơi có thể ghi độc lập khi mất kết nối, sẽ xuất hiện conflict. Một số loại dữ liệu có thể dùng CRDT/merge policy; nhưng những invariant như giữ duy nhất một ghế hoặc không tiêu số dư vượt hạn mức không tự động được bảo vệ bằng “last write wins”.

Sao chép có chủ đích trong Database per Service thường bắt đầu với **single authoritative writer** và nhiều bản sao đọc, vì dễ định nghĩa quyền quyết định và cách khôi phục hơn.

### 15.1. Quy tắc chống vòng cập nhật

Nếu consumer nhận event rồi ghi projection của mình, không nên mặc định publish lại cùng một cập nhật như thể nó là sự thật mới của producer. Những vòng A → B → A có thể gây duplicate events, feedback loops và xung đột version.

Nếu một service muốn đề nghị sửa nguồn, hãy gửi **command có nghĩa nghiệp vụ** tới owner (ví dụ RequestProductCorrection) và chờ owner ra quyết định. Đừng trực tiếp thay dữ liệu nguồn hoặc “sync ngược” tất cả field.

## 16. Trách nhiệm sửa và xóa dữ liệu

Cập nhật không chỉ là UPSERT. Trong đời thực có:

- Xóa sản phẩm khỏi danh mục.
- Ẩn một mục vì không được phép kinh doanh.
- Khóa một tài khoản, thu hồi quyền.
- Sửa dữ liệu do nhập nhầm.
- Thay đổi thông tin cá nhân theo yêu cầu hợp lệ.
- Hết hạn dữ liệu theo chính sách retention.
- Hủy giao dịch/đơn và điều chỉnh báo cáo.

Producer phải công bố semantics đủ rõ để consumer biết **xóa, ẩn, vô hiệu hóa hay giữ lịch sử**. Một event “ProductDeleted” có thể khiến Search xóa document, nhưng Order vẫn phải giữ snapshot của đơn hàng đã chốt theo yêu cầu kế toán/lưu trữ phù hợp.

### 16.1. Tombstone và deletion event

~~~json
{
  "eventId": "evt-del-500",
  "eventType": "ProductVisibilityRevoked",
  "schemaVersion": 1,
  "aggregateId": "sku-100",
  "aggregateVersion": 43,
  "occurredAt": "2026-11-11T09:00:00Z",
  "reasonCode": "UNPUBLISHED"
}
~~~

Consumer cần biết sự kiện này có nghĩa xóa khỏi search index, đổi cờ visibility hay xóa vĩnh viễn record. Không suy diễn semantics chỉ từ tên event.

### 16.2. Dữ liệu cá nhân và quyền riêng tư

Khi sao chép PII, một yêu cầu xóa hoặc sửa ở nguồn có thể phải được truyền tới nhiều projection, cache, index và backup theo chính sách pháp lý áp dụng. Các trách nhiệm cần ghi rõ:

- Những loại PII nào được phép chuyển?
- Dữ liệu có cần được token hóa, rút gọn hoặc ẩn trường?
- Những nơi nào lưu, bao gồm logs, DLQ, event retention và backups?
- Ai nhận deletion/correction event, trong bao lâu?
- Có bằng chứng consumer đã xử lý việc xóa không?
- Dữ liệu immutable snapshot có nghĩa vụ retention khác không?
- Ai xử lý yêu cầu liên quan bản sao của mình?

Không phát toàn bộ CustomerEntity chứa điện thoại, địa chỉ và ngày sinh chỉ vì Search cần tên hiển thị. **Data minimization** phải được áp dụng ngay từ contract.

### 16.3. Backup và retention

Xóa document trong Search không nhất thiết xóa bản sao trong snapshot backup ngay lập tức. Đội cần quy trình retention, encryption, restore và re-apply deletion. Khi khôi phục bản backup cũ, phải tránh làm sống lại dữ liệu đã được xóa/ẩn theo policy.

## 17. Schema evolution và contract versioning

Nếu producer thêm field, đổi nghĩa trạng thái, thay đơn vị tiền hoặc đổi cách biểu diễn null, consumer projection có thể gặp lỗi dù message vẫn parse được.

### 17.1. Thay đổi additive

Thêm một trường tùy chọn có thể tương thích nếu consumer có khả năng bỏ qua field lạ và semantics cũ giữ nguyên. Nhưng decoder strict hoặc schema registry có thể từ chối; phải kiểm tra contract thật và phiên bản consumer đang vận hành.

### 17.2. Breaking changes

- Xóa/đổi tên field đang được consumer dùng.
- Đổi đơn vị tiền từ VND sang đơn vị nhỏ nhất mà không đổi contract.
- Đổi enum từ “PAID = đã authorize” thành “PAID = đã settle”.
- Đổi nghĩa timestamp từ UTC sang local timezone.
- Thay event delta bằng snapshot mà consumer không được thông báo.
- Đổi partition key làm thứ tự theo aggregate không còn được bảo đảm.
- Đổi identifier và bỏ các mapping đang tồn tại.

### 17.3. Expand → migrate → contract

Một chiến lược:

1. Producer công bố format mới nhưng vẫn hỗ trợ cũ trong compatibility window.
2. Consumer nâng mapper và projection schema.
3. Chạy đồng thời phiên bản producer/consumer cũ-mới có kiểm thử.
4. Backfill hoặc rebuild dữ liệu mới nếu cần.
5. Xác minh không còn consumer cũ, rồi loại bỏ format cũ theo policy.

Versioning là một hợp đồng vận hành, không chỉ là trường schemaVersion trong JSON. Cần biết ai còn tiêu thụ version cũ và message cũ có thể được replay sau nhiều ngày hay không.

## 18. Service sử dụng dữ liệu được sao chép phải quyết định rủi ro stale

Ví dụ Search dựa vào ProductUpdated event để hiển thị một mặt hàng. Catalog vừa đánh dấu mặt hàng ngừng bán, nhưng Search chưa nhận event. Search vẫn hiển thị mặt hàng trong vài giây. Đây có thể là degraded behavior chấp nhận được nếu checkout luôn kiểm tra điều kiện bán/giữ hàng tại owner.

Ngược lại, nếu Checkout lấy Search index làm nguồn duy nhất để quyết định “còn hàng”, sẽ có nguy cơ xác nhận sai.

### 18.1. Quy tắc thiết kế theo loại quyết định

- **Gợi ý/hiển thị:** có thể dùng projection stale nếu có freshness policy.
- **Ghi nhận lịch sử:** dùng snapshot đã được cam kết tại thời điểm nghiệp vụ.
- **Ra quyết định có invariant mạnh:** phải sử dụng owner hoặc cơ chế phân quyền/quota có bảo đảm tương ứng.
- **Báo cáo:** có thể dùng projection cuối ngày, nhưng cần cut-off, reconciliation và correction.
- **Kiểm soát truy cập:** phải xem xét nguy cơ stale permission và cơ chế revoke phù hợp, không mặc định event lag là an toàn.

Không phải bản sao nào cũng cần “strong consistency”. Nhưng phải biết **consistency nào thực sự cần cho từng use case**, và những failure mode nào có thể khiến hệ vi phạm lời hứa với người dùng.

## 19. Ví dụ thực tế: thương mại điện tử với bốn bản biểu diễn Product

Giả sử hệ có Catalog, Pricing, Order, Search và Inventory.

### 19.1. Dữ liệu nguồn

~~~text
Catalog
  ProductInfo
    productId
    title
    description
    category
    visibility

Pricing
  PriceQuote
    sku
    amount
    currency
    validUntil

Inventory
  StockBalance / Reservation
    sku
    quantity
    holds

Order
  PurchasedItemSnapshot
    sku
    titleAtPurchase
    agreedPrice
    currency
~~~

Bốn context sử dụng các thuộc tính liên quan đến cùng SKU nhưng không có một “UniversalProductEntity” quản trị tất cả.

### 19.2. Dòng cập nhật

~~~text
Catalog publish ProductDisplayChanged(v42)
                 |
        +--------+---------+
        |                  |
        v                  v
  Search projector    Recommendation projector
        |
        v
    Search index

Pricing publish PriceQuoteChanged
        |
        v
    Price display projection (nếu cần)

Order PlaceOrder
  -> xác thực price quote/terms theo policy
  -> Inventory ReserveStock
  -> lưu PurchasedItemSnapshot vào Order DB
~~~

Search có thể hiển thị tên sản phẩm hơi trễ. Khi Order đã chốt, snapshot phản ánh điều đã được khách và hệ thống chấp nhận, không chạy theo mô tả hiện tại.

### 19.3. Trách nhiệm của từng bên

| Thành phần | Trách nhiệm | Không được làm |
| --- | --- | --- |
| Catalog | Duy trì mô tả hiện hành, public event, snapshot/backfill | Sửa Order snapshot của lịch sử đã chốt bằng cách ghi DB chéo |
| Search | Consume event, build index, theo dõi freshness, rebuild | Quyết định nguồn dữ liệu Catalog đã thay đổi và ghi ngược |
| Pricing | Công bố báo giá và điều kiện hợp lệ | Đòi mọi service dùng chung bảng prices |
| Inventory | Quyết định reserve/confirm/release theo invariant | Cho Order tự giảm tồn qua direct SQL |
| Order | Ghi order aggregate và agreed snapshot, xử lý workflow | Coi bản sao Search là xác nhận tồn kho mạnh |
| Analytics | Projection, đối soát số liệu, cung cấp báo cáo | Tự cập nhật Payment ledger để sửa report |

### 19.4. Tình huống cập nhật và lỗi

**Tình huống A — Catalog đổi tên sản phẩm.** Search cập nhật index qua event. Order cũ giữ titleAtPurchase theo chính sách lịch sử. Đơn mới có thể chốt snapshot tên/giá từ các nguồn được phép tại thời điểm xử lý.

**Tình huống B — Event tới Search hai lần.** Consumer dùng eventId để dedupe và version để không lùi trạng thái. Chỉ mục không nhân đôi document.

**Tình huống C — Search offline hai giờ.** Broker giữ events theo retention; Search resume từ offset, theo dõi lag và có thể rebuild nếu hết retention. Giao diện xử lý trạng thái chỉ mục chưa đủ mới bằng policy đã công bố.

**Tình huống D — Product bị ẩn do vi phạm quy định.** Catalog phát visibility revocation. Search có thể cần ưu tiên cập nhật nhanh hơn các sự kiện mô tả thông thường, có cơ chế flush/invalidate hoặc fail closed phù hợp với yêu cầu thực tế.

**Tình huống E — Order nhận giá cũ.** Nếu chính sách yêu cầu xác thực giá tại checkout, Order phải dùng official quote/confirmation từ Pricing, không dùng cache giá chưa được xác nhận.

## 20. Ví dụ pseudocode consumer idempotent

Ví dụ một projector xử lý ProductDisplayInfoChanged. Nó cần giữ bảng chứa version đã áp dụng cho mỗi Product và bảng deduplication. Pseudocode:

~~~java
public void onProductDisplayChanged(ProductEvent event) {
    transaction.execute(() -> {
        if (processedEvents.exists("search-projector", event.eventId())) {
            return; // event đã được áp dụng và commit
        }

        ProductProjection current =
            projections.findForUpdate(event.productId());

        if (current == null ||
            event.aggregateVersion() > current.lastAppliedVersion()) {

            // Chỉ đúng nếu event là public state snapshot
            // đầy đủ cho những fields cần giữ trong projection.
            projections.upsert(
                event.productId(),
                event.name(),
                event.category(),
                event.visibility(),
                event.aggregateVersion()
            );
        }

        processedEvents.insert("search-projector", event.eventId());
    });
}
~~~

Đây là pseudocode để giải thích atomicity, không phải code compile được ngay. Nếu projection nằm trên search engine còn processedEvents ở relational DB, chúng **không chia sẻ transaction cục bộ**. Khi đó cần chiến lược idempotency tại index (document ID ổn định và version guard), thao tác có thể retry, hoặc luồng checkpoint phù hợp để tránh lệch.

Nếu event chỉ chứa delta, một version gap phải được phát hiện và replay/snapshot; không được bỏ qua phần trung gian làm sai trạng thái.

## 21. Dùng API composition khi bản sao chưa đáng đầu tư

Không phải mọi nhu cầu dữ liệu chéo đều cần event pipeline. Một màn hình quản trị hiếm khi mở, cần dữ liệu khá mới và có vài service nguồn, có thể dùng API composition:

~~~text
Admin endpoint
   -> Order API
   -> Payment API
   -> Shipping API
   -> compose response
~~~

Ưu điểm: dữ liệu lấy từ owner, không cần giữ local projection và cơ chế đồng bộ. Đánh đổi: thêm network latency, lỗi một dependency có thể ảnh hưởng response, có thể tạo N+1 calls. Nên dùng batching, timeout budget, caching có chính sách và partial response có nghĩa rõ khi phù hợp.

Chỉ xây projection khi có lý do đo được: truy vấn lặp lại nhiều, latency của composition quá cao, giảm tải nguồn hoặc cần availability độc lập.

## 22. Thiết kế Data Replication Contract

Một bản hợp đồng sao chép nên ghi rõ:

| Nhóm | Nội dung phải có |
| --- | --- |
| Nguồn có thẩm quyền | Service/bounded context và entity/attribute được công bố |
| Consumer | Tên service, mục đích bản sao, owner vận hành |
| Dữ liệu được phép chia sẻ | Danh sách fields, classification và giới hạn PII |
| Transport | API, event broker, CDC, batch export |
| Semantics | Event notification/delta/snapshot, unit, timezone, meaning |
| Identity & ordering | Aggregate ID, event ID, monotonic version, partition key |
| Consistency | Freshness SLO, staleness tolerance, cách xử lý lag |
| Delivery | At-least-once/other actual guarantees, duplicate/out-of-order policy |
| Bootstrap | Snapshot, checkpoint, backfill và replay |
| Repair | Reconciliation, rebuild, correction/deletion |
| Security | ACL, encryption, audit, secret scope, retention |
| Change management | Schema version, deprecation, contract tests |
| Observability | Lag, error, DLQ, mismatches, last successful checkpoint |
| Operations | On-call, alert threshold, incident escalation, recovery plan |

Nếu không có hợp đồng này, một bản sao có thể trở thành dependency ẩn giống việc các service đọc chung database.

### 22.1. Mẫu mô tả ngắn

~~~text
Nguồn: Catalog Service
Bản sao: Search ProductProjection
Mục đích: full-text search và filter danh mục
Fields: productId, title, category, visibility
Không có: customer PII, cost price, internal audit note
Cập nhật: ProductDisplayInfoChanged event (public state snapshot)
Dedupe: eventId
Ordering: aggregateVersion theo productId
Freshness: SLO do đội Search/Catalog thống nhất
Bootstrap: Catalog snapshot + stream checkpoint
Repair: periodic reconciliation và full reindex
Xóa: ProductVisibilityRevoked, tombstone theo contract
Owner: Catalog (facts/schema event), Search (projection)
Không dùng để: xác nhận tồn kho hoặc giá chính thức
~~~

## 23. Observability cho sao chép dữ liệu

Một pipeline tốt cần metrics từ producer đến consumer. Những chỉ số gợi ý:

- **Outbox backlog/age:** bao nhiêu event đã commit nhưng chưa publish?
- **Publish failures:** số lỗi broker, retry, permission, schema validation.
- **Consumer lag:** offset/time lag theo partition và consumer group.
- **Projection apply latency:** thời gian từ nhận event đến commit local state.
- **End-to-end freshness:** tuổi dữ liệu từ producer commit đến truy vấn hiện tại.
- **Duplicate rate:** số eventId nhận lại và được bỏ qua an toàn.
- **Out-of-order/version gaps:** số lần nhận version cũ hoặc thiếu version.
- **Dead-letter queue size/age:** event lỗi đang bị giữ lại lâu bao nhiêu?
- **Reconciliation mismatch:** số record sai khác và thời gian sửa.
- **Snapshot/backfill progress:** tỷ lệ hoàn thành, checkpoint, records còn thiếu.
- **Deletion compliance:** số yêu cầu xóa/correction chưa được xác nhận.
- **Projection availability:** tỉ lệ query thành công và sự khác biệt giữa vùng/pod.
- **Data quality:** required fields missing, unknown enum, schema incompatibility.

Không dùng raw userId/productId không giới hạn làm metric labels vì cardinality có thể tăng lớn. Có thể dùng exemplars/tracing/logging có quyền truy cập phù hợp để điều tra từng ID cụ thể.

### 23.1. SLO minh họa

Một đội có thể định nghĩa:

- Phần lớn cập nhật Catalog hiển thị trên Search trong một ngưỡng thời gian đã đo.
- Khi pipeline lag vượt ngưỡng, dashboard báo degraded và on-call nhận alert.
- Không cho phép một phiên bản thấp hơn ghi đè version mới trong projection.
- Có khả năng rebuild toàn bộ Search index theo kế hoạch vận hành.
- Mọi yêu cầu visibility revocation theo chính sách phải được xử lý với mức ưu tiên xác định.

Các ngưỡng cụ thể phải xuất phát từ yêu cầu sản phẩm và đo thực tế, không lấy từ ví dụ bất kỳ.

## 24. Runbook khi bản sao sai hoặc chậm

### Bước 1 — Xác định loại lỗi

- Producer chưa commit hay chưa phát event?
- Outbox dispatcher bị lỗi?
- Broker giữ backlog lớn hoặc mất quyền?
- Consumer crash, deserialize lỗi hay dừng?
- Projection database/index đầy, lock hoặc lỗi quyền?
- Event đến sai thứ tự hoặc mapper ghi dữ liệu không đúng?
- Một lô correction/deletion chưa được áp dụng?

### Bước 2 — Đánh giá phạm vi ảnh hưởng

Những chức năng nào dùng projection? Có quyết định nhạy cảm đang dựa vào dữ liệu cũ không? Có cần chuyển sang direct owner query hoặc tạm chặn use case không? Có rủi ro PII/visibility/permission cần ưu tiên xử lý không?

### Bước 3 — Giới hạn sự cố

Tạm dừng consumer lỗi nếu nó đang liên tục ghi sai; cô lập bad event; bật degraded mode theo contract; áp dụng rate limit để tránh overload producer trong lúc repair.

### Bước 4 — Khôi phục theo bằng chứng

- Resume từ offset đã kiểm chứng nếu stream còn đủ.
- Replay một partition/aggregate theo version.
- Lấy snapshot mới hoặc rebuild projection khi đã mất events.
- Đối chiếu counts/version/checksum theo phần.
- Kiểm tra deletion/tombstone và dữ liệu nhạy cảm.
- Đưa traffic trở lại khi đạt ngưỡng đã công bố.

### Bước 5 — Điều tra nguyên nhân gốc

Khắc phục source, event contract, mapper, monitoring, retention hoặc quy trình deployment. Không chỉ chạy rebuild xong rồi coi như đã giải quyết nguyên nhân khiến projection sai.

## 25. Kịch bản kiểm thử quan trọng

### 25.1. Duplicate delivery

Gửi cùng eventId hai lần. Xác nhận projection và các aggregate counters không bị tăng/ghi trùng.

### 25.2. Out-of-order delivery

Gửi version 12 trước version 11. Xác minh consumer không ghi lùi; nếu event là delta, phải phát hiện thiếu version và phục hồi đúng.

### 25.3. Producer commit nhưng broker down

Kiểm tra outbox giữ event sau transaction, dispatcher gửi lại khi broker phục hồi và không mất dữ liệu có thẩm quyền.

### 25.4. Consumer crash sau khi ghi projection nhưng trước ACK

Broker gửi lại. Consumer phải nhận biết event đã áp dụng hoặc phép ghi vào projection phải idempotent.

### 25.5. Backfill trong lúc dữ liệu thay đổi

Tạo snapshot và đồng thời phát update/delete; kiểm chứng checkpoint/watermark bảo đảm kết quả cuối không bỏ sót biến động.

### 25.6. Event contract thay đổi

Consumer cũ nhận field mới, enum mới hoặc version mới. Kiểm tra fallback an toàn, migration plan và compatibility window.

### 25.7. Correction và deletion

Xác nhận bản sao xử lý cập nhật sửa sai, xóa khỏi index, không làm sống lại dữ liệu khi replay version cũ hoặc restore backup.

### 25.8. Consumer lag kéo dài

Tạo backlog lớn; đo thời gian bắt kịp, memory, retry, tác động tới source và cách báo trạng thái dữ liệu cũ.

### 25.9. DLQ và poison message

Một message không thể parse không được chặn toàn pipeline vô hạn. DLQ có owner, alert, cách sửa và replay; không âm thầm bỏ event quan trọng.

### 25.10. Data invariant

Projection không được dùng để commit một quyết định cần strong consistency từ owner; test trường hợp cache stale và network partition để bảo vệ điều kiện nghiệp vụ.

## 26. Anti-pattern và cách sửa

### 26.1. Copy toàn bộ bảng của service khác

**Vấn đề:** lộ internal schema, sao chép dữ liệu không cần thiết, coupling về migration và rủi ro bảo mật.  
**Cách sửa:** công bố event/DTO tối giản hoặc read API theo nhu cầu, chỉ chứa dữ liệu được phép sử dụng.

### 26.2. Producer ghi trực tiếp database của tất cả consumer

**Vấn đề:** distributed dual writes, thiếu atomicity, khó deploy độc lập, quyền truy cập lan rộng.  
**Cách sửa:** owner publish contract, consumer tự duy trì projection của mình.

### 26.3. Consumer sửa ngược bản nguồn theo field vừa nhận

**Vấn đề:** phát sinh vòng update, multi-writer không chủ đích và conflict.  
**Cách sửa:** consumer gửi command có nghĩa tới owner để yêu cầu thay đổi, owner quyết định.

### 26.4. Chỉ dùng timestamp để xác định event mới nhất

**Vấn đề:** clock skew và publish delay làm event sai thứ tự; timestamp không thay thế monotonic version.  
**Cách sửa:** version/sequence theo aggregate hoặc protocol ordering thích hợp, kèm gap detection khi cần.

### 26.5. Đồng bộ dựa vào polling nhưng không có checkpoint

**Vấn đề:** có thể bỏ sót thay đổi giữa hai lần quét, trùng records hoặc không xử lý deletion.  
**Cách sửa:** cursor/updated version bền vững, phân trang có semantics rõ, reconciliation; cân nhắc event/CDC khi phù hợp.

### 26.6. Giả định event chỉ được giao một lần

**Vấn đề:** crash sau commit nhưng trước ACK tạo duplicate; counters bị cộng hai lần.  
**Cách sửa:** idempotent consumer, event IDs, transactional/integrated checkpoints, version guards.

### 26.7. Quên khởi tạo dữ liệu cũ

**Vấn đề:** service mới chỉ nhận events mới, không có đối tượng lịch sử.  
**Cách sửa:** consistent snapshot + replay hoặc API backfill có checkpoint.

### 26.8. Coi mọi projection là nguồn mạnh cho checkout

**Vấn đề:** stale data dẫn đến oversell, sai giá, cấp quyền sai.  
**Cách sửa:** quyết định có invariant ở owner hoặc giao thức phân quyền phù hợp.

### 26.9. Không có trách nhiệm vận hành bản sao

**Vấn đề:** projection stale nhiều ngày mà không đội nào nhận trách nhiệm.  
**Cách sửa:** owner của pipeline và projection, lag SLO, alert, runbook, reconciliation.

### 26.10. Xóa ở nguồn nhưng không xóa ở consumer

**Vấn đề:** PII, visibility, retention và data minimization bị vi phạm.  
**Cách sửa:** deletion/correction contract, tombstone, audit, restore reapplication và thời hạn xử lý rõ.

## 27. Phương pháp thiết kế từng bước

**Bước 1 — Nêu use case và mức chấp nhận dữ liệu cũ.** Ví dụ Search cần tên sản phẩm gần thời gian thực, không cần xác nhận hàng còn đủ để chốt đơn.

**Bước 2 — Chỉ ra source of truth theo từng thuộc tính.** Không dừng ở tên đối tượng Product hay Customer; xác định cụ thể name, price, reservation, payment, permissions.

**Bước 3 — Chọn dạng bản sao.** Cache, business snapshot, local read model, search index, analytical warehouse hoặc API composition nếu không cần sao chép.

**Bước 4 — Định nghĩa trách nhiệm owner/consumer.** Producer công bố business event đúng semantics; consumer sở hữu projection, lag, replay, repair và access controls.

**Bước 5 — Thiết kế schema/event contract.** Event ID, aggregate ID/version, type, timestamp, fields, deletion semantics, compatibility window.

**Bước 6 — Thiết kế delivery và xử lý lỗi.** Outbox/CDC, at-least-once, idempotency, ordering/gaps, retry budget, DLQ và poison messages.

**Bước 7 — Thiết kế backfill và reconciliation.** Snapshot có checkpoint, replay trong giai đoạn đồng thời cập nhật, đối soát và rebuild.

**Bước 8 — Bảo vệ privacy/security.** Data minimization, PII classification, deletion, retention, encryption, audit và quyền cấp cho consumer.

**Bước 9 — Đặt SLO/monitoring.** Đo end-to-end freshness, lag, mismatch, error, DLQ và khả năng phục hồi.

**Bước 10 — Kiểm thử và đưa vào vận hành.** Test duplicate, out-of-order, crash, network outage, rollout schema và correction; dùng canary/shadow reads trước khi chuyển critical traffic khi cần.

## 28. Bài tập thực hành: hệ thống đặt vé sự kiện

Một hệ thống có:

- Show Catalog: thông tin sự kiện và hình ảnh.
- Seat Inventory: trạng thái ghế, reservation, quota còn được bán.
- Payment: thanh toán và refund.
- Ticket Issuance: cấp mã vé đã xác thực.
- Search: tìm sự kiện và venue.
- Analytics: doanh thu theo show.

### Bài 1 — Owner và bản sao

Hãy xác định source of truth cho trạng thái ghế, thông tin show, kết quả thanh toán và vé đã phát hành. Search và Analytics cần giữ bản sao gì? Có được cho Search tự xác nhận ghế còn trống không?

### Bài 2 — Event design

Thiết kế ShowDisplayInfoChanged, SeatReservationExpired và PaymentCaptured với event ID, aggregate ID, version, timestamp và dữ liệu tối thiểu. Mô tả sự kiện nào chứa state snapshot, sự kiện nào là event nghiệp vụ và consumer nào cần nhận.

### Bài 3 — Độ trễ và quyết định

Search còn hiển thị một buổi diễn vừa bị hủy do chưa cập nhật event. Hãy mô tả degraded behavior, freshness SLO và bước xác nhận chính thức ở checkout.

### Bài 4 — Duplicate và out-of-order

PaymentCaptured đến Analytics hai lần; ShowUpdated v15 đến trước v14; TicketIssued đến trễ. Hãy giải thích cách dedupe, version guard và kiểm tra state machine.

### Bài 5 — Khôi phục

Search index mất hoàn toàn nhưng broker retention chỉ giữ events bảy ngày. Hãy xây quy trình snapshot/backfill/checkpoint/replay với Show Catalog và cách đối soát sau rebuild.

### Bài 6 — Xóa dữ liệu

Người dùng yêu cầu thay đổi thông tin cá nhân, còn Ticket Issuance cần giữ một số dữ liệu tối thiểu theo quy định. Xác định trách nhiệm Producer/Consumer, retention, deletion event, backup và audit theo chính sách áp dụng.

**Kết quả mong đợi:** bảng ownership từng nguồn, kiến trúc truyền dữ liệu, hợp đồng event, freshness requirements, quy tắc idempotency, runbook và một test plan.

## 29. Câu hỏi tự kiểm tra

1. Vì sao Database per Service vẫn cho phép nhiều bản sao của cùng một thông tin?
2. Source of truth khác local projection và historical snapshot ra sao?
3. Khi nào nên dùng cache, khi nào nên dùng event-driven read model và khi nào chỉ cần API composition?
4. Sao chép dữ liệu có chủ đích giúp giảm coupling kiểu gì và tạo coupling mới kiểu gì?
5. Tại sao producer không nên tự cập nhật thẳng các database của mọi consumer?
6. Transactional outbox giải quyết vấn đề gì? Nó có bảo đảm consumer không bao giờ nhận duplicate không?
7. Event-carried state và event notification khác nhau về availability và payload ra sao?
8. Với một aggregate version 42, tại sao version 41 đến sau không được ghi đè bản sao hiện tại?
9. Nếu event là delta và mất version 12, có thể áp dụng version 13 ngay mà không cần điều tra không?
10. Vì sao eventId và aggregateVersion phục vụ hai mục đích khác nhau?
11. Snapshot backfill và event stream cần checkpoint/watermark để giải quyết race nào?
12. Vì sao consumer lag bằng 0 vẫn có thể không chứng minh dữ liệu hiện hành đã được sao chép đầy đủ?
13. Reconciliation khác replay như thế nào?
14. Vì sao Search có thể dùng dữ liệu stale nhưng Inventory reservation thường không?
15. Khi nào một ProductSnapshot trong Order có quyền giữ nguyên dù Catalog đổi tên?
16. Khi owner xóa dữ liệu cá nhân, những projection/cache/backup nào có thể cần xử lý?
17. Trong hệ có nhiều vùng ghi, tại sao “last write wins” không bảo đảm invariant giữ một ghế duy nhất?
18. Nếu consumer nhận event, cập nhật index rồi crash trước ACK, cần xử lý thế nào?
19. Đâu là trách nhiệm của producer và đâu là trách nhiệm của consumer khi DLQ tăng?
20. Một event chỉ công bố thay đổi nội bộ tên cột có phải contract nghiệp vụ tốt không? Vì sao?

## 30. Tóm tắt

- **Sao chép có chủ đích không phá vỡ quyền sở hữu dữ liệu** nếu xác định rõ nguồn có thẩm quyền, mục đích bản sao và trách nhiệm cập nhật.
- **Không sao chép toàn bộ domain model chỉ để tránh gọi API.** Chọn đúng fields, loại dữ liệu, quyền truy cập và freshness theo use case.
- **Producer sở hữu sự thật và public contract; consumer sở hữu projection và cách vận hành nó.** Không để producer ghi trực tiếp mọi database consumer.
- **Historical snapshot khác cache cập nhật liên tục.** Snapshot đã chốt của Order có thể có semantics và vòng đời riêng.
- **Outbox/CDC hỗ trợ publish tin cậy**, nhưng không thay consumer idempotency, versioning, replay và reconciliation.
- **Duplicate, out-of-order và replay là tình huống phải thiết kế trước.** EventId, aggregateVersion, checkpoints và conditional writes giúp tránh ghi trùng/lùi dữ liệu.
- **Backfill phải xử lý biến động đang diễn ra**, không chỉ chép một lần toàn bộ bảng rồi bắt đầu nghe events ở thời điểm tùy ý.
- **Freshness là một cam kết vận hành có thể đo**, không chỉ là chữ “eventual consistency”. Dữ liệu stale phải được chấp nhận hoặc từ chối theo invariant của use case.
- **Deletion, correction, retention, privacy và backup** là một phần của trách nhiệm đồng bộ, không phải công việc bổ sung sau cùng.
- **Có runbook để sửa projection** và test mất event, duplicate, out-of-order, schema change, lag và mất index.

**Câu hỏi quyết định:** *Nếu ngày mai Catalog đổi một thuộc tính, Search đang offline và Order vừa chốt giao dịch, ai biết giá trị nào là chuẩn, bản sao nào phải cập nhật, bản lịch sử nào phải giữ nguyên, và bằng chứng nào cho thấy hệ cuối cùng sẽ hội tụ?* Thiết kế sao chép dữ liệu có chủ đích phải trả lời rõ toàn bộ chuỗi câu hỏi đó.
