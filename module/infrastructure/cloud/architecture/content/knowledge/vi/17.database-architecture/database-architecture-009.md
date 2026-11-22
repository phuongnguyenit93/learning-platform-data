# Tách kho tìm kiếm khỏi cơ sở dữ liệu nghiệp vụ

## 1. Vì sao không nên dùng database giao dịch cho mọi kiểu truy vấn?

Một cơ sở dữ liệu nghiệp vụ thường được tối ưu cho các giao dịch có cấu trúc rõ: tạo booking, cập nhật trạng thái thanh toán, kiểm tra quyền sở hữu và bảo đảm ràng buộc dữ liệu. Đây là nhóm tải **OLTP (Online Transaction Processing)**, thường có nhiều thao tác đọc/ghi nhỏ, cần transaction, tính nhất quán và khả năng truy cập theo khóa hoặc index có kiểm soát.

Khi sản phẩm cần tìm kiếm toàn văn, gợi ý, lọc nhiều thuộc tính, xếp hạng theo mức liên quan, phân tích văn bản hoặc tìm kiếm trên hàng triệu tài liệu, việc chạy tất cả trên cùng database giao dịch có thể làm tăng CPU, I/O, lock, kích thước index và độ trễ của giao dịch quan trọng. Truy vấn tìm kiếm phức tạp cũng thường có access pattern khác với thao tác ghi booking.

Một kiến trúc thường dùng là **tách kho tìm kiếm (search store/index) khỏi cơ sở dữ liệu nghiệp vụ (operational database)**:

- Database nghiệp vụ giữ dữ liệu có thẩm quyền và thực hiện transaction.
- Search store giữ một projection/index được tổ chức cho truy vấn tìm kiếm, lọc, phân tích và xếp hạng.
- Một pipeline đồng bộ chuyển những thay đổi cần thiết từ database nghiệp vụ sang search store.
- Ứng dụng dùng search store để tìm ứng viên, sau đó xác minh dữ liệu và quyền ở nguồn có thẩm quyền trước thao tác nghiệp vụ quan trọng.

Trong module **CLOUD_ARCHITECTURE**, đây là quyết định liên quan tới kiến trúc dữ liệu, compute, mạng và mô hình triển khai. Cần cân bằng **độ tin cậy, bảo mật, hiệu năng, khả năng mở rộng, chi phí và vận hành** theo tư duy Well-Architected.

Ví dụ xuyên suốt: nền tảng đặt chỗ có hàng triệu phòng/property. Khách tìm theo thành phố, ngày nhận/trả phòng, số khách, tiện nghi, mức giá, đánh giá và từ khóa. Database nghiệp vụ vẫn quản lý giá cuối cùng, tồn phòng, booking và thanh toán; search store phục vụ lọc và xếp hạng kết quả nhanh.

## 2. Phân biệt OLTP database và search store

Hai hệ thống có mục tiêu khác nhau:

| Tiêu chí | Database nghiệp vụ (OLTP) | Search store |
| --- | --- | --- |
| Mục tiêu chính | Ghi/đọc trạng thái nghiệp vụ chính xác | Tìm kiếm, lọc, phân tích và xếp hạng nhanh |
| Cấu trúc | Bảng/quan hệ, document hoặc key-value theo mô hình giao dịch | Inverted index, term dictionary, field index, vector hoặc cấu trúc chuyên tìm kiếm |
| Ghi dữ liệu | Transaction nghiệp vụ, ràng buộc, cập nhật có kiểm soát | Thường nhận projection/batch/event từ nguồn khác |
| Truy vấn | Lookup, join và điều kiện có cấu trúc | Full-text, fuzzy, faceted filtering, relevance, geo hoặc vector search tùy sản phẩm |
| Nhất quán | Thường là nguồn có thẩm quyền cho giao dịch | Có thể trễ so với nguồn, tùy pipeline |
| Mẫu tải | Read/write ngắn, transaction và cập nhật đồng thời | Read-heavy, truy vấn đa điều kiện, refresh/indexing và phân tích |
| Khả năng phục hồi | Backup, replication, transaction recovery | Có thể tái tạo từ nguồn có thẩm quyền và pipeline |
| Chi phí | Tính theo transaction, compute, storage, replica và backup | Tính theo shard/partition, replica, index size, ingest, query và vận hành |

Search store không đơn giản là một bản sao đầy đủ của database. Thông thường nó chứa **read model/projection**: chỉ các trường và cấu trúc cần cho những truy vấn tìm kiếm đã được xác định. Một document tìm kiếm có thể tổng hợp dữ liệu từ property, địa điểm, tiện nghi và đánh giá, nhưng không nhất thiết giữ toàn bộ lịch sử thanh toán hay thông tin cá nhân.

### 2.1. Search index không phải nguồn dữ liệu có thẩm quyền

Search index có thể cập nhật chậm, nhận event lặp hoặc tạm thời chứa dữ liệu chưa phản ánh thay đổi mới nhất. Vì vậy:

- Không dùng kết quả search index làm bằng chứng cuối cùng rằng phòng vẫn còn trống.
- Không cập nhật giá hoặc trạng thái thanh toán chỉ dựa trên document trong search store.
- Trước khi xác nhận booking, phải kiểm tra tồn phòng, giá và điều kiện nghiệp vụ ở service/database có thẩm quyền.
- Khi index lỗi hoặc trễ, xác định rõ chức năng nào có thể tiếp tục, chức năng nào cần từ chối hoặc hiển thị dữ liệu cũ có nhãn.

**Search trả lời “những đối tượng nào có vẻ phù hợp để hiển thị?”; database nghiệp vụ trả lời “thao tác này có hợp lệ và được phép commit không?”**

## 3. Kiến trúc tổng thể và đường đi dữ liệu

~~~mermaid
flowchart LR
    USER["Web / Mobile"]
    API["Search API"]
    DB[("Operational DB<br/>Nguồn dữ liệu có thẩm quyền")]
    OUTBOX["Outbox / CDC / Change Stream"]
    PIPE["Indexer / Projection Worker"]
    SEARCH[("Search Store<br/>Inverted index / Search documents")]
    BOOK["Booking Service"]
    USER --> API --> SEARCH
    API -->|"Ứng viên và ID"| BOOK
    BOOK --> DB
    DB --> OUTBOX --> PIPE --> SEARCH
~~~

Luồng đọc và luồng đồng bộ được tách riêng:

1. Search API nhận bộ lọc, kiểm tra request và truy vấn search store.
2. Search store trả ID, điểm liên quan và một số trường hiển thị được phép.
3. API có thể lấy chi tiết cần thiết từ read model hoặc service tương ứng; với dữ liệu nhạy cảm/quyết định giao dịch, cần xác minh ở nguồn có thẩm quyền.
4. Database nghiệp vụ commit thay đổi.
5. Outbox, CDC hoặc change stream chuyển thay đổi tới indexer.
6. Indexer chuyển dữ liệu nguồn sang search document theo mapping, rồi tạo/cập nhật/xóa document trong search store.

Các thành phần cụ thể tùy nền tảng. Outbox là mẫu ứng dụng; CDC đọc log thay đổi; change stream là cơ chế do database cung cấp; indexer có thể là worker tự quản lý hoặc dịch vụ tích hợp. Điều quan trọng là có thể **truy vết từ thay đổi nguồn tới trạng thái index** và xử lý được lỗi giữa các bước.

### 3.1. Ví dụ search document

Một document dành cho tìm kiếm property có thể có dạng:

~~~json
{
  "propertyId": "property-91",
  "cityId": "city-hcm",
  "name": "Riverside Garden Hotel",
  "description": "Khách sạn gần trung tâm và bờ sông",
  "amenities": ["wifi", "pool", "parking"],
  "location": {
    "lat": 10.776,
    "lon": 106.701
  },
  "rating": 4.6,
  "priceFrom": 1250000,
  "currency": "VND",
  "searchable": true,
  "sourceVersion": 1842,
  "indexedAt": "2026-11-18T04:30:00Z"
}
~~~

Các trường trên là ví dụ. Document chỉ nên chứa dữ liệu cần để tìm/lọc/xếp hạng và hiển thị, không chứa thông tin thanh toán hoặc dữ liệu cá nhân không cần thiết. Cần thống nhất đơn vị tiền tệ, tọa độ, cách chuẩn hóa tiện nghi, thời điểm cập nhật và ý nghĩa searchable.

## 4. Xác định access pattern trước khi chọn search engine

Không phải mọi yêu cầu tìm kiếm đều cần một search engine độc lập. Hãy đo và liệt kê truy vấn thực tế:

| Nhu cầu | Ví dụ | Cơ chế có thể phù hợp |
| --- | --- | --- |
| Lookup theo ID | Lấy property bằng ID chính xác | Primary key/index trong database hoặc cache |
| Lọc có cấu trúc | Thành phố, ngày, số khách, trạng thái | B-tree/index, search filter hoặc cả hai tùy tải |
| Tìm toàn văn | Từ khóa trong tên và mô tả | Full-text/inverted index |
| Fuzzy/autocomplete | Gõ sai chính tả, gợi ý khi nhập | Analyzer, n-gram, edge n-gram hoặc completion feature |
| Faceted search | Đếm kết quả theo khu vực, tiện nghi, mức giá | Aggregation/facet trên search store |
| Geo search | Trong bán kính hoặc vùng bản đồ | Geo index/query |
| Semantic/vector search | Tìm nội dung gần về ý nghĩa | Vector index và mô hình embedding |
| Quyết định giao dịch | Phòng còn trống và giá cuối | Database nghiệp vụ hoặc service giao dịch có thẩm quyền |

Nếu chỉ có vài truy vấn lọc đơn giản và database đáp ứng SLO với chi phí thấp, thêm search cluster có thể làm kiến trúc phức tạp hơn mức cần thiết. Search store đáng cân nhắc khi truy vấn đa dạng, read-heavy, full-text/fuzzy/geo/aggregation hoặc tải tìm kiếm ảnh hưởng đáng kể tới giao dịch.

## 5. Thiết kế projection và mapping từ nguồn sang index

Indexer không nên sao chép mọi field một cách máy móc. Cần định nghĩa **projection contract**:

- Những entity nào tạo nên một search document?
- Trường nào được chuẩn hóa, tổng hợp hoặc biến đổi?
- Khi entity liên quan thay đổi, document nào phải cập nhật?
- Trường nào cần searchable, filterable, sortable, facetable hay chỉ lưu để hiển thị?
- Field nào cần được loại bỏ vì nhạy cảm hoặc không cần thiết?
- Nếu một document phụ thuộc nhiều nguồn, dữ liệu được ghép với version nào?

### 5.1. Mapping field theo cách sử dụng

| Field | Cách dùng | Cách biểu diễn cần cân nhắc |
| --- | --- | --- |
| propertyId | Định danh chính xác | Keyword/exact value; dùng làm document ID nếu phù hợp |
| name | Tìm toàn văn, autocomplete | Text với analyzer và có thể thêm subfield exact/sort |
| cityId | Lọc chính xác | Keyword hoặc field có semantics tương ứng |
| amenities | Lọc nhiều giá trị | Array/set field với exact matching |
| priceFrom | Filter/sort/range | Numeric, đơn vị tiền tệ rõ |
| rating | Sort/filter/range | Numeric; xử lý missing value |
| location | Radius/map query | Geo point hoặc cấu trúc geo được engine hỗ trợ |
| description | Full-text | Text analyzer phù hợp ngôn ngữ |
| indexedAt/sourceVersion | Vận hành/đối soát | Timestamp và version number |

Field full-text và field exact match thường cần cách index khác nhau. Nếu cityId được phân tích như văn bản thường, truy vấn có thể tokenize ngoài ý muốn. Nếu description chỉ được lưu dưới dạng keyword, tìm từ ngữ bên trong sẽ không hoạt động theo kỳ vọng.

### 5.2. Analyzer và ngôn ngữ

Tìm kiếm tiếng Việt cần chú ý dấu, biến thể viết, tokenization, từ ghép và chính tả. Có thể cần:

- Chuẩn hóa Unicode và quy tắc so sánh dấu.
- Analyzer/tokenizer phù hợp tiếng Việt hoặc bộ phân tích tùy chỉnh được kiểm thử.
- Trường riêng cho tìm kiếm không dấu nếu sản phẩm yêu cầu; không thay thế dữ liệu hiển thị gốc.
- Đồng nghĩa (synonym) có version và quy trình cập nhật.
- Kiểm tra các truy vấn thực tế: tên địa danh, tên thương hiệu, từ khóa ngắn, lỗi gõ và cụm từ.

Không bật stemming, bỏ dấu hoặc synonym toàn cục theo cảm tính. Những biến đổi này có thể tăng recall nhưng giảm precision, khiến kết quả không liên quan xuất hiện trước.

## 6. Đồng bộ dữ liệu: outbox, CDC và polling

Tách database khỏi search store đồng nghĩa tồn tại một pipeline cập nhật. Có ba cách thường gặp:

| Cách | Hoạt động | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| Transactional outbox | Ghi dữ liệu nghiệp vụ và outbox event trong cùng transaction; publisher phát event | Kiểm soát event ở tầng ứng dụng, tránh khoảng trống commit/publish | Cần quản lý outbox, publisher, cleanup và backlog |
| CDC (Change Data Capture) | Đọc log thay đổi của database và chuyển thành stream | Giảm việc polling bảng, có thể gần thời gian thực | Phụ thuộc log/connector, schema source và quyền đọc; cần xử lý snapshot/restart |
| Polling theo watermark | Định kỳ đọc bản ghi thay đổi từ timestamp/version tăng dần | Dễ bắt đầu, ít hạ tầng chuyên biệt | Độ trễ theo chu kỳ, tải đọc lặp, khó đảm bảo không bỏ sót khi watermark sai |

### 6.1. Transactional outbox

Khi booking/property thay đổi, ứng dụng ghi entity và outbox record trong cùng transaction:

~~~sql
BEGIN;

UPDATE property
SET name = 'Riverside Garden Hotel',
    version = version + 1
WHERE property_id = 'property-91';

INSERT INTO outbox_events (
    event_id, aggregate_type, aggregate_id, aggregate_version, event_type
)
VALUES (
    'evt-abc', 'Property', 'property-91', 1842, 'PropertyUpdated'
);

COMMIT;
~~~

Publisher đọc outbox và chuyển event tới broker/indexer. Nếu transaction rollback, cả cập nhật property và event đều không tồn tại. Nếu publisher phát event rồi crash trước khi đánh dấu hoàn tất, event có thể được phát lại; indexer phải idempotent theo event ID/version.

### 6.2. CDC

CDC đọc thay đổi từ write-ahead log/binlog/change stream hoặc cơ chế log tương ứng. Đây là cách hữu ích khi muốn đồng bộ dữ liệu hiện có hoặc nhiều bảng mà không thêm event publish trong từng đường code nghiệp vụ.

CDC đòi hỏi hiểu rõ:

- DDL/schema change và cách connector phát sự kiện thay đổi.
- Snapshot ban đầu kết hợp với log streaming như thế nào.
- Offset/checkpoint được lưu và khôi phục ra sao.
- Replication slot/log retention có thể làm nguồn dữ liệu tăng dung lượng nếu connector ngừng lâu.
- Delete, truncate, transaction nhiều bản ghi và thứ tự thay đổi được biểu diễn thế nào.
- Trường dữ liệu nhạy cảm nào không được phép đưa vào stream/index.

CDC phản ánh thay đổi ở database; nó không tự cung cấp đầy đủ ngữ nghĩa nghiệp vụ. Một row update không phải lúc nào cũng đủ để hiểu “booking đã xác nhận” nếu quy tắc nghiệp vụ trải qua nhiều bảng hoặc nhiều trạng thái.

### 6.3. Polling

Polling có thể sử dụng cột version hoặc updatedAt. Nhưng timestamp có độ chính xác thấp, đồng hồ lệch, transaction commit trễ hoặc nhiều bản ghi cùng timestamp có thể khiến bỏ sót dữ liệu nếu truy vấn dùng watermark quá đơn giản. Nên dùng composite cursor, overlap window và deduplication, đồng thời có reconciliation định kỳ.

## 7. Nhất quán cuối cùng và freshness của search index

Search index thường được cập nhật bất đồng bộ, vì vậy có **eventual consistency**. Sau khi user cập nhật property, search result có thể vẫn hiển thị trạng thái cũ trong một khoảng thời gian.

Cần định nghĩa freshness SLO theo nghiệp vụ:

| Loại thay đổi | Độ trễ chấp nhận minh họa | Hành vi khi chưa đồng bộ |
| --- | --- | --- |
| Mô tả/ảnh property | Vài phút | Có thể hiển thị nội dung cũ tạm thời |
| Tiện nghi/đặc điểm | Vài chục giây | Kết quả lọc có thể trễ; UI cần xử lý khi chi tiết khác index |
| Giá quảng cáo | Rất ngắn hoặc phải xác minh realtime | Không dùng giá trong index để chốt giao dịch |
| Tồn phòng | Không dùng index làm nguồn xác nhận | Kiểm tra tại inventory/booking service trước khi giữ phòng |
| Xóa/ẩn nội dung vi phạm | Theo SLA chặt do bảo mật/chính sách | Có thể cần tombstone hoặc chặn ngay ở serving layer |

Các mốc thời gian chỉ là ví dụ. Với từng field cần xác định p95/p99 của thời gian từ source commit tới index visible, không chỉ thời gian broker nhận event.

### 7.1. Read-after-write

Nếu người quản trị sửa tên property rồi ngay lập tức tìm lại nhưng index chưa cập nhật, trải nghiệm có thể gây nhầm lẫn. Một số lựa chọn:

- Trả trạng thái cập nhật đang chờ index và cung cấp version hiện tại.
- Sau khi ghi, giao diện đọc chi tiết từ operational database trong một khoảng ngắn.
- Dùng read-your-writes session/version token để truy vấn chỉ khi index đạt version mong muốn.
- Với một số truy vấn nhỏ, kết hợp kết quả search với dữ liệu mới từ source có kiểm soát.

Không bắt search index thực hiện synchronous refresh sau mọi write nếu điều đó làm giảm throughput và tăng latency. Chỉ dùng cơ chế refresh tức thời khi nghiệp vụ thật sự cần và đã đo chi phí.

## 8. Xử lý event trùng, sai thứ tự và cập nhật cũ

Event pipeline có thể giao lặp hoặc không đúng thứ tự do retry, nhiều publisher, partition và xử lý song song. Nếu indexer ghi trực tiếp theo event đến cuối cùng, một event cũ có thể ghi đè projection mới.

### 8.1. Version theo entity

Mỗi entity có version tăng đơn điệu. Search document lưu sourceVersion. Indexer chỉ áp dụng bản cập nhật nếu version mới hơn version hiện tại:

~~~text
if event.aggregateVersion > document.sourceVersion:
    apply_projection(event)
else:
    ignore_as_duplicate_or_stale()
~~~

Đây là pseudocode. Cần atomic conditional update hoặc cơ chế optimistic concurrency mà search engine hỗ trợ; kiểm tra version trong ứng dụng rồi ghi không điều kiện vẫn có race giữa hai worker.

### 8.2. Delete và tombstone

Nếu source xóa một property, pipeline phải tạo hành vi tương ứng ở search store. Delete event có thể được xử lý chậm hoặc đến trước một update cũ đang retry. Có thể lưu tombstone/version để ngăn sự kiện cũ tái tạo document đã xóa.

Đối với nội dung cần gỡ ngay vì yêu cầu an toàn/chính sách, không nên chỉ chờ indexer. Có thể dùng serving denylist hoặc kiểm tra trạng thái/visibility từ nguồn tin cậy, song song với pipeline xóa. Cần tránh denylist trở thành một dependency không có HA.

## 9. Xóa, mapping và cập nhật document tổng hợp

Một search document có thể kết hợp nhiều entity. Ví dụ property document lấy thông tin property, city, tiện nghi, đánh giá và chính sách. Khi một entity phụ thay đổi, indexer cần biết document nào bị ảnh hưởng.

Các lựa chọn:

- **Denormalize vào document:** truy vấn nhanh, ít join lúc search, nhưng cập nhật thay đổi liên quan cần fan-out.
- **Lưu ID tham chiếu:** indexer hoặc API lấy chi tiết từ service khác, giảm trùng dữ liệu nhưng tăng call và latency.
- **Projection theo domain:** một projector sở hữu document search, tổng hợp từ các event cần thiết.
- **Join ở query time:** linh hoạt hơn trong một số hệ, nhưng có thể tăng latency và phức tạp phân tán.

Khi property đổi city hoặc bị xóa, phải xác định các document liên quan, cache và kết quả đã được lưu. Với quan hệ một-nhiều lớn, fan-out update cần queue và batch để không tạo burst.

## 10. Reindex, backfill và thay đổi mapping

Khi analyzer, field mapping hoặc cấu trúc document thay đổi, không nên sửa index production theo cách không có đường quay lại. Một quy trình phổ biến là **blue-green index**:

~~~mermaid
flowchart TD
    SRC[("Operational DB / CDC")]
    PIPE["Projection pipeline"]
    OLD[("Search Index v1")]
    NEW[("Search Index v2")]
    ALIAS["Read alias"]
    SRC --> PIPE
    PIPE --> OLD
    PIPE --> NEW
    OLD --> ALIAS
    NEW -. build + validate .-> ALIAS
~~~

Quy trình:

1. Tạo index v2 với mapping/analyzer mới.
2. Chụp snapshot dữ liệu nguồn hoặc lấy điểm bắt đầu phù hợp.
3. Backfill theo batch vào v2.
4. Đồng thời phát/áp dụng các thay đổi mới trong lúc backfill; dùng watermark/version để tránh ghi đè dữ liệu mới bằng snapshot cũ.
5. So sánh document count, field coverage, sample query, relevance, freshness và lỗi mapping.
6. Đưa truy vấn thử nghiệm/canary sang v2.
7. Chuyển alias/routing sang v2 khi tiêu chí đạt.
8. Giữ v1 trong thời gian rollback đã xác định, sau đó mới retire.

Không thể chỉ đếm số document để khẳng định reindex chính xác. Một document có thể thiếu field, dùng sai analyzer hoặc chứa version cũ dù tổng số lượng trùng. Cần kiểm tra chất lượng theo mẫu, tập truy vấn đại diện và đối chiếu nguồn.

### 10.1. Backfill không được gây quá tải database

Backfill hàng triệu record có thể tạo read load lớn trên OLTP. Cần:

- Dùng replica đọc hoặc snapshot/export phù hợp nếu kiến trúc hỗ trợ và dữ liệu đủ mới.
- Chia batch có giới hạn concurrency, rate và checkpoint.
- Ưu tiên tải thấp hoặc chạy theo cửa sổ được phê duyệt.
- Theo dõi CPU, I/O, lock, replication lag và latency giao dịch.
- Có pause/resume, retry idempotent và kiểm tra tiến độ.
- Tách luồng backfill với luồng realtime để realtime không bị starvation.

## 11. Search query và bảo vệ database nghiệp vụ

Tách search store chỉ có ích khi search API không biến mọi kết quả thành hàng loạt lookup nặng ở database nghiệp vụ.

### 11.1. Tránh N+1 lookup

Giả sử search trả 100 property ID, rồi API gọi database 100 lần để lấy tên, ảnh và giá. Hệ thống vẫn tạo tải lớn lên OLTP, dù truy vấn chính chạy ở search store.

Có thể:

- Lưu trường hiển thị không nhạy cảm trong search document và dùng trực tiếp cho kết quả.
- Batch lookup một nhóm ID thay vì gọi từng ID.
- Dùng read model/cache cho dữ liệu hiển thị ít nhạy cảm.
- Chỉ truy vấn nguồn có thẩm quyền cho dữ liệu cần kiểm tra trước hành động giao dịch.
- Giới hạn page size và field trả về.

### 11.2. Tìm kiếm và xác nhận booking

Luồng tham khảo:

1. Search store tìm property/room phù hợp và trả danh sách ứng viên.
2. Người dùng chọn một lựa chọn.
3. Booking Service nhận yêu cầu và kiểm tra quyền, ngày, số khách, giá và tồn phòng ở nguồn có thẩm quyền.
4. Service thực hiện hold/transaction theo quy tắc concurrency.
5. Sau commit, outbox/event cập nhật search projection khi cần.

Search result có thể là stale nhưng không được phép biến thành xác nhận sai. Khi nguồn có thẩm quyền từ chối, UI cần giải thích rằng lựa chọn vừa hết khả dụng hoặc giá đã thay đổi.

## 12. HA, backup và phục hồi cho search store

Search store thường có thể tái tạo từ source và pipeline, nhưng điều đó không đồng nghĩa có thể bỏ backup hoặc không cần HA. Thời gian reindex từ hàng tỷ record có thể kéo dài, gây áp lực lên source và ảnh hưởng SLO.

| Mục tiêu | Câu hỏi thiết kế |
| --- | --- |
| Availability | Search cluster có replica/shard phân bố qua failure domain phù hợp không? |
| Recovery | Có thể khôi phục từ snapshot hay bắt buộc rebuild; mất bao lâu? |
| RPO | Có thể mất bao nhiêu thay đổi index khi phục hồi? Source và log/event retention có đủ để tái tạo không? |
| RTO | Search có phải hoạt động lại trong vài phút hay có thể degraded mode trong thời gian rebuild? |
| Capacity | Node mới có đủ CPU/memory/disk để allocate shard và chạy indexing không? |
| Pipeline | Offset/checkpoint, outbox/CDC backlog và schema mapping có thể tiếp tục sau lỗi không? |

### 12.1. Kế hoạch suy giảm có kiểm soát

Nếu search store tạm thời không khả dụng:

- Trả thông báo lỗi có thể thử lại hoặc phục vụ một tập kết quả cached nếu an toàn.
- Giữ các giao dịch booking và trạng thái dữ liệu có thẩm quyền hoạt động độc lập nếu nghiệp vụ cho phép.
- Không fallback bằng cách chạy một truy vấn full scan nặng lên OLTP.
- Hạn chế hoặc tạm tắt một số bộ lọc nâng cao thay vì làm quá tải database.
- Theo dõi backlog đồng bộ và thực hiện catch-up sau khi search store hồi phục.

Một cache kết quả search cũng có freshness và privacy constraints riêng. Không dùng cache của tenant này cho tenant khác hoặc giữ kết quả đã bị ẩn/xóa khi chính sách yêu cầu gỡ ngay.

## 13. Bảo mật và quản lý dữ liệu trong search store

Search index thường được mở quyền đọc rộng hơn database nghiệp vụ để phục vụ nhiều ứng dụng. Vì vậy phải thiết kế quyền và dữ liệu có chủ đích:

- Chỉ index field cần thiết; tránh đưa password, token, payment details hoặc PII không cần vào document.
- Dùng network private endpoint/security policy và TLS cho đường từ app/indexer tới search cluster.
- Xác thực service identity, giới hạn index/collection và quyền query/write/admin.
- Tenant filtering phải được áp tại server theo identity đã xác minh; không chỉ tin filter tenant do client gửi.
- Field-level access và response projection phải bảo vệ dữ liệu nhạy cảm.
- Log query có thể chứa từ khóa cá nhân; cần mask, retention và quyền đọc log.
- Snapshot/search backup và export cũng phải có mã hóa, quyền và chính sách vị trí dữ liệu.

### 13.1. Search query injection và resource abuse

Không nối chuỗi query của client vào DSL/query language mà không validate. Giới hạn độ sâu query, số clause, wildcard/regex, aggregation bucket, page size và timeout theo khả năng engine. Một truy vấn hợp lệ cú pháp vẫn có thể rất đắt. Rate limit nên xét route và chi phí query, không chỉ request/giây.

## 14. Quan sát pipeline và chất lượng tìm kiếm

Cần đo cả hai phía: **sức khỏe kỹ thuật của index** và **chất lượng kết quả người dùng nhận được**.

| Nhóm | Metric/signal cần theo dõi |
| --- | --- |
| Source | Transaction latency, DB CPU/IO, log retention, replication lag |
| Pipeline | Outbox/CDC backlog, oldest event age, consumer lag, retry, DLQ, processing rate |
| Indexing | Indexing latency, bulk failure, rejected documents, mapping exception, refresh lag |
| Search cluster | Query p95/p99, CPU, memory/heap, disk, shard allocation, rejected query, cache hit |
| Freshness | Thời gian source commit tới lúc document version xuất hiện trong search |
| Correctness | Document count, missing field, duplicate/stale version, mismatch theo sample |
| Search quality | Zero-result rate, click-through, conversion, relevance feedback, filter success |
| Security | Cross-tenant access attempt, forbidden field exposure, unusual export/query |
| Cost | Storage/index replica, ingest, query compute, cross-zone traffic, snapshot và reindex |

Không tối ưu NDCG hoặc click-through bằng cách hy sinh tính đúng đắn của giá/tồn phòng. Search relevance là mục tiêu xếp hạng; nguồn có thẩm quyền và chính sách nghiệp vụ vẫn là điều kiện bắt buộc của giao dịch.

## 15. Quy trình thiết kế và quyết định kiến trúc

~~~mermaid
flowchart TD
    A["Xác định search access patterns và SLO"]
    A --> B{"OLTP đáp ứng tải và tính năng?"}
    B -->|Có| C["Giữ truy vấn phù hợp trong database"]
    B -->|Không| D["Thiết kế search projection/store"]
    D --> E["Chọn outbox, CDC hoặc polling"]
    E --> F["Định nghĩa mapping, freshness và version"]
    F --> G["Backfill + dual-run + validation"]
    G --> H["Canary / cutover / rollback"]
    H --> I["Observe freshness, quality, SLO và cost"]
    I --> J["Reconcile, tune và review"]
~~~

Với mỗi luồng truy vấn, ghi:

1. Người dùng/chủ thể và mục tiêu nghiệp vụ.
2. Trường cần tìm, filter, sort, aggregate và hiển thị.
3. Dữ liệu nào có thể trễ; dữ liệu nào phải xác minh realtime.
4. Nguồn có thẩm quyền cho từng field và quy trình xử lý delete.
5. Tần suất ghi, đọc, burst, kích thước document và tốc độ tăng.
6. Cách sync, version, dedupe, retry, backfill và reconciliation.
7. Bảo mật, tenant isolation, retention, backup và quyền truy cập.
8. SLI/SLO, runbook, degraded mode, RTO/RPO và chi phí.

## 16. Bài thực hành: tách search khỏi hệ thống booking

**Bối cảnh giả định:** nền tảng có 5 triệu property/room, 20 triệu lượt truy vấn tìm kiếm mỗi ngày, dữ liệu property thay đổi 100.000 lần/ngày, giá/tồn phòng thay đổi thường xuyên hơn. OLTP đang phục vụ booking và payment; search hiện chạy bằng nhiều truy vấn join nặng và làm p95 transaction tăng.

### Nhiệm vụ

1. Liệt kê tối thiểu tám access pattern tìm kiếm và phân loại truy vấn nào vẫn nên ở database.
2. Thiết kế search document/projection; chỉ rõ field searchable, filterable, sortable, facetable, field nhạy cảm không được index.
3. Chọn outbox, CDC hoặc polling; vẽ luồng source commit → pipeline → index visible.
4. Định nghĩa freshness SLO cho mô tả, tiện nghi, giá, tồn phòng và nội dung bị ẩn/xóa.
5. Thiết kế versioning, idempotency, xử lý event lặp/sai thứ tự, tombstone và reconciliation.
6. Xây dựng quy trình reindex v2 với backfill, catch-up stream, kiểm tra chất lượng, canary, cutover và rollback.
7. Thiết kế degraded mode khi search store ngừng hoạt động mà không gây quá tải OLTP.
8. Xác định metric pipeline, search cluster, search relevance, security và cost.
9. Viết ADR giải thích vì sao cần search store độc lập, phương án bị loại và những đánh đổi còn lại.

### Mẫu ma trận source-of-truth

| Trường | Nguồn có thẩm quyền | Có index? | Dùng để xác nhận giao dịch? |
| --- | --- | --- | --- |
| Property name/description | Property Service DB | Có | Không |
| City/amenities | Property Service DB | Có | Có thể dùng để lọc ứng viên, không phải điều kiện commit |
| Search rating summary | Review Service DB/projection | Có | Không |
| Advertised price | Pricing Service DB | Có thể index để xếp hạng sơ bộ | Phải xác minh giá cuối ở Pricing/Booking |
| Availability | Inventory/Booking Service | Có thể cache/projection | Phải xác minh realtime trước hold/booking |
| Payment status | Payment Service DB | Không cần cho search | Chỉ Payment Service có thẩm quyền |

### Tiêu chí hoàn thành

- Phân biệt rõ OLTP và search store, không coi index là nguồn sự thật.
- Search projection đáp ứng query mà không sao chép dữ liệu nhạy cảm không cần thiết.
- Có pipeline có thể retry, dedupe, backfill và reconciliation.
- Freshness được đo từ source commit đến index visible, có SLO theo field.
- Reindex không làm quá tải OLTP và có cutover/rollback.
- Lỗi search không kéo theo lỗi giao dịch hoặc fallback full scan nguy hiểm.
- Có kiểm soát tenant, quyền, retention, backup, RTO/RPO và chi phí.

## 17. Checklist Well-Architected trước khi đưa search store vào production

- [ ] Đã xác nhận truy vấn và tải thực sự cần search store độc lập.
- [ ] Database nghiệp vụ vẫn là nguồn có thẩm quyền cho trạng thái giao dịch.
- [ ] Search projection chỉ chứa field cần thiết và có owner/mapping contract.
- [ ] Field full-text, exact, numeric, geo, vector và analyzer được chọn đúng access pattern.
- [ ] Có outbox/CDC/polling với checkpoint, retry, deduplication và delete semantics rõ.
- [ ] Có version theo entity để tránh event cũ ghi đè document mới.
- [ ] Freshness SLO được đo từ source commit đến index visible.
- [ ] Giá, tồn phòng, quyền và trạng thái nhạy cảm được xác minh ở nguồn có thẩm quyền.
- [ ] Có backfill/reindex, dual-run, validation, canary, alias switch và rollback.
- [ ] Backfill không làm quá tải OLTP; pipeline realtime không bị starvation.
- [ ] Có reconciliation để phát hiện thiếu, trùng, stale hoặc sai mapping.
- [ ] Search store có HA, backup/rebuild strategy, capacity và RTO/RPO phù hợp.
- [ ] Degraded mode không tạo fallback gây full scan/áp lực lên database giao dịch.
- [ ] Tenant isolation, IAM, TLS, field minimization, retention và audit được kiểm chứng.
- [ ] Có metric cho query latency, index freshness, backlog, relevance, security và cost.
- [ ] ADR ghi rõ đánh đổi reliability, security, performance, cost và operations.

**Điểm cốt lõi:** tách kho tìm kiếm khỏi database nghiệp vụ giúp mỗi hệ thống tối ưu cho một loại tải và giảm cạnh tranh tài nguyên. Đổi lại, kiến trúc phải quản lý **projection, đồng bộ bất đồng bộ, độ trễ nhất quán, event lặp, reindex, bảo mật và phục hồi**. Thiết kế chỉ thực sự tốt khi search store tăng tốc truy vấn mà không được phép làm sai dữ liệu có thẩm quyền hoặc đe dọa các giao dịch nghiệp vụ.
