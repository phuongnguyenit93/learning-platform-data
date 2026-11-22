# Chọn chức năng theo bài toán và kiểm tra giới hạn của từng sản phẩm NoSQL

Các hệ cơ sở dữ liệu NoSQL không phải những lựa chọn có thể thay thế cho nhau chỉ vì cùng lưu dữ liệu ngoài mô hình quan hệ truyền thống. Một hệ tối ưu **tìm kiếm toàn văn** cần xử lý phân tích ngôn ngữ và xếp hạng; một hệ **chuỗi thời gian** cần nạp sự kiện liên tục, giữ dữ liệu theo thời hạn và tổng hợp theo cửa sổ; một hệ **vector** cần tìm các đối tượng gần nhau về ngữ nghĩa; một hệ **đồ thị** cần duyệt quan hệ nhiều bước. Ngoài ra còn có hệ khóa–giá trị, tài liệu và cột rộng, mỗi loại có những đường truy cập và đặc tính vận hành riêng.

Khi chọn sản phẩm, câu hỏi đầu tiên phải là **“ứng dụng phải làm gì với dữ liệu?”**, sau đó mới đến “sản phẩm nào có API hỗ trợ?”. Hai sản phẩm đều quảng cáo “full-text search”, “vector search” hoặc “distributed transactions” chưa chắc có cùng cách truy vấn, mức độ chính xác, giới hạn kiểu dữ liệu, độ nhất quán, chi phí ghi, cơ chế phân phối và khả năng phục hồi.

Bài học này hướng dẫn một quy trình ra quyết định có thể kiểm chứng:

1. Chuyển yêu cầu nghiệp vụ thành mẫu truy cập và tiêu chí đo.
2. Nhận diện chức năng chuyên biệt thật sự cần thiết.
3. Lập danh sách năng lực, điều kiện tiên quyết và giới hạn phải xác minh ở **sản phẩm, phiên bản, edition và cấu hình cụ thể**.
4. Thử hành vi truy vấn, dữ liệu biên và tình huống lỗi bằng ví dụ nhỏ.
5. Đo hiệu năng, mức tiêu thụ tài nguyên và chi phí vận hành bằng workload đại diện.
6. Chọn công nghệ hoặc cách kết hợp công nghệ; ghi lại những gì đã được xác nhận và những gì còn là giả thuyết.

Những ví dụ dưới đây dùng MongoDB, Redis, Elasticsearch/OpenSearch, các hệ chuỗi thời gian, vector database và graph database để minh họa cách đặt câu hỏi. **Không có bảng thông số cứng nào áp dụng chung cho mọi phiên bản sản phẩm.** Các số liệu mục tiêu được ghi là giả định của một dự án mẫu, không phải giới hạn mặc định hay kết quả benchmark.

## 1. Phân biệt chức năng nghiệp vụ và tên loại cơ sở dữ liệu

Một nhóm phát triển có thể nói “chúng tôi cần Elasticsearch” trong khi yêu cầu thực là “người dùng phải tìm được sản phẩm theo từ khóa có lỗi chính tả và lọc được giá”. Hoặc “chúng tôi cần vector database” trong khi yêu cầu thực là “tìm tài liệu có nội dung tương tự câu hỏi của người dùng”. Tên sản phẩm chỉ là phương án triển khai; **hợp đồng kết quả** mới là điều cần định nghĩa.

| Yêu cầu phát biểu ban đầu | Chuyển thành bài toán kỹ thuật | Dấu hiệu cần chức năng chuyên biệt |
|---|---|---|
| “Tìm sản phẩm thông minh” | Tokenization, tìm từ, phrase, fuzzy, lọc thuộc tính, xếp hạng | Full-text search / hybrid retrieval |
| “Xem dữ liệu cảm biến tháng trước” | Ingest nhiều điểm, lọc thiết bị và thời gian, aggregate theo cửa sổ, retention | Time-series và mô hình phân vùng theo thời gian |
| “Tìm cửa hàng gần tôi” | Lọc tọa độ trong bán kính, đa giác, sắp theo khoảng cách | Geospatial index / geographic query |
| “Tìm bài viết tương tự” | Embedding, nearest neighbor, lọc metadata, đo recall | Vector similarity search |
| “Tìm đường liên quan giữa tài khoản” | Duyệt cạnh nhiều hop, lọc theo loại quan hệ, giới hạn frontier | Graph traversal |
| “Đọc trạng thái phiên thật nhanh” | Truy cập trực tiếp bằng khóa, TTL, atomic counter / conditional write | Key–value |
| “Lấy đơn hàng cùng các dòng hàng” | Truy xuất aggregate, truy vấn trường lồng nhau và cập nhật có điều kiện | Document model |
| “Đọc sự kiện mới nhất theo thiết bị” | Partition key, clustering theo thời gian, giới hạn kích thước phân vùng | Wide-column |
| “Tổng hợp hàng tỷ bản ghi theo nhiều chiều” | Quét cột, aggregate lớn, phân tích theo lô | Analytical/columnar engine có thể phù hợp hơn OLTP NoSQL |

Bảng này là **định hướng lựa chọn tính năng**, không phải quy tắc “mỗi nhu cầu bắt buộc một database”. Nhiều hệ hiện đại hỗ trợ hơn một chức năng; một hệ quan hệ cũng có thể hỗ trợ JSON, full-text, geospatial hoặc vector. Phải xem khả năng cụ thể có đáp ứng **chất lượng, tốc độ và vận hành** của workload hay không.

## 2. Thiết lập một tình huống xuyên suốt

Giả sử ứng dụng quản lý sản phẩm, hoạt động người dùng và gợi ý nội dung có các thành phần sau:

- **Catalog:** mỗi sản phẩm có ID, tên, mô tả, danh mục, giá, tình trạng bán và thuộc tính mở rộng.
- **Địa điểm:** một số sản phẩm gắn với cửa hàng có tọa độ và khu vực giao hàng.
- **Sự kiện:** mỗi lần xem sản phẩm hoặc tìm kiếm phát sinh một sự kiện gắn user, product và timestamp.
- **Nội dung:** mô tả sản phẩm hoặc tài liệu hướng dẫn có thể được chuyển thành embedding để tìm ngữ nghĩa tương tự.
- **Quan hệ:** user thích sản phẩm, sản phẩm cùng nhà sản xuất, danh mục có quan hệ phân cấp.

Một số mục tiêu **giả định để lập bài thực hành**:

| Nhu cầu | Điều kiện chấp nhận cần định nghĩa |
|---|---|
| Đọc chi tiết sản phẩm | Đúng ID, trả trạng thái và giá theo cam kết đọc/ghi nghiệp vụ |
| Tìm từ khóa | Top 20 kết quả, lọc hàng đang bán, p95 dưới 250 ms tại tải mục tiêu |
| Tìm cửa hàng gần điểm X | Kết quả trong bán kính, đúng hệ tọa độ và đơn vị; p95 dưới 200 ms |
| Tìm sản phẩm tương tự | Recall@10 đạt ngưỡng do nhóm xác định so với ground truth |
| Biểu đồ lượt xem | Dữ liệu theo phút; cho phép trễ cập nhật tối đa 2 phút |
| Đề xuất theo quan hệ | Duyệt tối đa 2 hop và trả tối đa 20 kết quả phù hợp |
| Ghi sự kiện | Không mất bản ghi đã được xác nhận theo hợp đồng và có xử lý retry |
| Khả năng vận hành | Đạt RPO/RTO, khả năng restore và giới hạn chi phí được chấp thuận |

Các mốc ms/phút là giả định của tình huống, không phải cam kết mà một công nghệ cụ thể mặc định cung cấp. Cần xác định cả tải, kích thước, topology, concurrency, dữ liệu nóng và đặc điểm phân bố mới có thể kiểm chứng.

## 3. Phân tách yêu cầu thành “đúng kết quả” và “đủ nhanh”

Không nên tối ưu độ trễ trước khi xác định câu truy vấn có trả **đúng tập kết quả** hay không. Những chức năng chuyên biệt có các tiêu chí đúng đắn rất khác nhau:

- **Tra cứu theo ID:** giá trị chính xác, đúng tenant và quyền truy cập.
- **Tìm kiếm từ khóa:** cách tách từ, xử lý dấu, lỗi chính tả, synonym và đánh giá ranking.
- **Tìm theo vị trí:** kinh/vĩ độ, đơn vị khoảng cách, ranh giới bán kính/đa giác.
- **Tìm vector:** phép đo tương tự (cosine, dot product, Euclidean), recall và tác động filter.
- **Dữ liệu thời gian:** timezone, late arrivals, duplicate events, window boundary và aggregation.
- **Đồ thị:** hướng cạnh, số hop, sự khác biệt giữa “không có đường” và “truy vấn chưa đầy đủ”.
- **Ghi nghiệp vụ:** tính nguyên tử, uniqueness, idempotency, thứ tự cập nhật và retry.

Một sản phẩm có thể đạt p95 rất tốt nhưng vẫn không đạt vì bỏ sót dữ liệu trong filter, tìm sai bán kính hoặc không bảo toàn bất biến giao dịch. Hãy đánh giá hai trục song song:

| Trục | Câu hỏi | Bằng chứng |
|---|---|---|
| **Semantic fit** | Truy vấn và cập nhật có diễn đạt được đúng nghĩa nghiệp vụ không? | Bộ dữ liệu mẫu có kết quả mong đợi, test biên |
| **Operational fit** | Có chạy đủ nhanh, đúng và ổn định tại quy mô dự kiến không? | Benchmark, giám sát, diễn tập lỗi và restore |

Một chức năng chỉ “có trong tài liệu quảng bá” chưa đủ để kết luận đáp ứng cả hai trục.

## 4. Chức năng tìm kiếm toàn văn: nhiều hơn lọc chuỗi

Một truy vấn `name contains "phone"` khác với một công cụ tìm kiếm toàn văn có analyzer, stemming, synonyms, fuzzy matching, ranking và highlight. Khi lựa chọn công cụ tìm kiếm, phải xác định chính xác người dùng nhập gì và mong kết quả được xếp thứ tự ra sao.

Các thành phần thường gặp:

1. **Analyzer/tokenizer:** biến text thành token; ngôn ngữ, dấu câu, chữ hoa/thường và ký tự đặc biệt ảnh hưởng kết quả.
2. **Normalization:** chuẩn hóa dạng văn bản; không được mặc định mọi ngôn ngữ có cùng quy tắc.
3. **Inverted index:** ánh xạ token đến tài liệu chứa token.
4. **Relevance/ranking:** chấm điểm và sắp xếp, chẳng hạn dựa trên BM25 trong một số hệ tìm kiếm.
5. **Filtering:** áp điều kiện trạng thái, giá, tenant, category mà không làm sai tập kết quả.
6. **Update/refresh:** tài liệu vừa cập nhật có được tìm thấy ngay không, cần chờ refresh hay truy vấn lại nguồn gốc?

### 4.1. Ví dụ truy vấn bằng Elasticsearch/OpenSearch

Cú pháp dưới đây minh họa Query DSL quen thuộc với các hệ tìm kiếm tương thích; mapping, analyzer và đường API phải được đối chiếu với phiên bản đang dùng.

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "tai nghe chống ồn",
            "fields": ["name^3", "description"]
          }
        }
      ],
      "filter": [
        { "term": { "tenantId": "t01" } },
        { "term": { "status": "ACTIVE" } },
        { "range": { "price": { "lte": 3000000 } } }
      ]
    }
  },
  "size": 20
}
~~~

Trong một index hợp lý, các trường `tenantId` và `status` thường được mapping như từ khóa chính xác; `price` dùng kiểu số; `name` và `description` dùng trường văn bản có analyzer phù hợp. Việc ghi `"name^3"` là một cách gợi ý trọng số tìm kiếm; không tự bảo đảm chất lượng ranking.

**Giới hạn phải kiểm tra:**

- Analyzer nào hỗ trợ ngôn ngữ và dữ liệu thực tế? Có xử lý tiếng Việt, dấu và từ ghép theo yêu cầu không?
- Exact match, phrase, wildcard, fuzzy, n-gram và synonym có những giới hạn cú pháp/hiệu năng nào?
- Có phân biệt `text` với `keyword` khi lọc/sort/aggregation không?
- Có hỗ trợ sort ổn định cùng điểm relevance khi nhiều kết quả bằng điểm không?
- Refresh/indexing latency và kết quả đọc ngay sau ghi được cam kết thế nào?
- Query tìm quá rộng, nhiều token hoặc regexp nặng có thể gây chi phí gì?
- Phân trang sâu sử dụng cơ chế nào, có hỗ trợ point-in-time hoặc cursor phù hợp không?
- Ranking có thể giải thích/đánh giá theo bộ câu hỏi thật bằng NDCG, MRR hoặc Precision@K không?

Một query nhanh nhưng xếp hạng sai 10 kết quả đầu không đạt yêu cầu tìm kiếm. Cần xây tập truy vấn đại diện và đánh giá cả **relevance** lẫn latency.

## 5. Chức năng time-series: từ ghi sự kiện đến cửa sổ thời gian

Dữ liệu chuỗi thời gian thường có dạng:

~~~json
{
  "deviceId": "d42",
  "timestamp": "2026-11-14T08:00:00Z",
  "temperatureC": 26.8,
  "site": "north-warehouse",
  "quality": "OK"
}
~~~

Các nhu cầu phổ biến: nạp nhiều sự kiện liên tục, đọc theo device trong khoảng thời gian, lấy mẫu gần nhất, tính trung bình/min/max theo phút, giữ raw data trong thời hạn nhất định và lưu aggregate dài hạn.

Một mô hình lập kế hoạch truy vấn:

~~~text
(deviceId = d42, time in [08:00, 09:00))
             ↓
Chọn partition/chunk/bucket theo thời gian
             ↓
Đọc điểm phù hợp
             ↓
Tính aggregate theo 1 phút
             ↓
Trả 60 điểm cho biểu đồ
~~~

### 5.1. Những năng lực phải thử

| Năng lực | Trường hợp thử | Giới hạn cần khám phá |
|---|---|---|
| Ingest nhiều điểm | 10.000 thiết bị gửi song song | Write throughput, batch size, backpressure |
| Lọc theo tag/device | Một thiết bị hoặc một site | Index/tag cardinality và partition skew |
| Window aggregate | Trung bình mỗi phút | Chính sách xử lý bucket rỗng, null, late data |
| Retention | Xóa raw sau 30 ngày | TTL/delete, compaction, không gian và timing |
| Downsampling | Giữ aggregate theo giờ một năm | Độ chính xác, truy vết, backfill |
| Truy vấn khoảng dài | 1 giờ, 7 ngày, 1 năm | Số chunk/partition phải đọc và memory |
| Sự kiện đến muộn | Event hôm qua được gửi hôm nay | Cập nhật lại cửa sổ tổng hợp hay giữ nguyên? |
| Dữ liệu trùng | Gửi lại cùng event ID | Upsert/dedup có theo khóa định danh ổn định không? |

Không nên chỉ hỏi “có TTL không?” mà phải hỏi “TTL tính từ **thời điểm ghi** hay **event timestamp**, xóa ở mức nào, và có thể chậm bao lâu?”. Tương tự, “có continuous aggregation” không tự nói rõ việc chỉnh sửa dữ liệu cũ có được phản ánh vào aggregate hay không.

### 5.2. Ví dụ truy vấn khái niệm

~~~sql
-- Cú pháp SQL minh họa ý tưởng, không cam kết chạy nguyên văn trên mọi engine.
SELECT
    time_bucket('1 minute', event_time) AS minute_bucket,
    avg(temperature_c) AS avg_temperature
FROM sensor_readings
WHERE device_id = 'd42'
  AND event_time >= :start_time
  AND event_time <  :end_time
GROUP BY time_bucket('1 minute', event_time)
ORDER BY minute_bucket;
~~~

`time_bucket` là tên hàm phổ biến trong một số hệ thống; **không phải cú pháp SQL tiêu chuẩn được mọi time-series database hỗ trợ**. Trong sản phẩm chỉ dùng query language riêng, phải chuyển đúng câu hỏi nghiệp vụ sang cú pháp tương ứng.

Mức chọn lọc và hiệu năng thường phụ thuộc vào **thời gian + tag/partition key**, phân bố series, số khoảng dữ liệu bị đọc và cấu hình retention/compression. Một hệ chuyên lưu time-series có thể lợi thế rõ trên chuỗi dữ liệu liên tục, nhưng không chắc phù hợp nếu ứng dụng chủ yếu cần giao dịch cập nhật nhiều thực thể.

## 6. Chức năng geospatial: phải xác định hệ tọa độ và ý nghĩa khoảng cách

Ứng dụng “tìm các cửa hàng trong bán kính 3 km” không thể thực hiện chính xác chỉ bằng so sánh hai trường `latitude` và `longitude` dưới dạng số thông thường. Cần thống nhất **hệ tọa độ**, thứ tự kinh/vĩ độ, đơn vị và cách tính khoảng cách trên bề mặt Trái Đất.

Dữ liệu GeoJSON thường biểu diễn điểm:

~~~json
{
  "type": "Point",
  "coordinates": [106.7000, 10.8000]
}
~~~

Với GeoJSON, thứ tự tọa độ là **[longitude, latitude]**, không phải [latitude, longitude]. Đảo thứ tự có thể dẫn tới kết quả sai hoặc điểm nằm ở vị trí khác.

Ví dụ MongoDB với GeoJSON point:

~~~javascript
db.stores.createIndex({ location: "2dsphere" });

db.stores.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.8000]
      },
      $maxDistance: 3000
    }
  }
});
~~~

Trong ngữ cảnh truy vấn GeoJSON với chỉ mục `2dsphere`, `$maxDistance` được diễn đạt bằng mét theo hợp đồng MongoDB tương ứng. Một truy vấn bán kính khác với “đi bộ mất 15 phút”: **khoảng cách địa lý** không tự xét đường đi, giao thông, cầu, sông, ranh giới hành chính hoặc thời gian di chuyển.

### Các giới hạn cần kiểm tra

- Sản phẩm hỗ trợ những hình học nào: point, polygon, multipolygon, line, geometry collection?
- Hệ tọa độ (CRS) nào được chấp nhận? Có cần chuẩn hóa sang WGS84/GeoJSON không?
- Khoảng cách tính theo độ, mét hay đơn vị khác? Có phân biệt hình cầu với mặt phẳng không?
- Điểm nằm đúng trên biên polygon/bán kính được tính là “trong” hay “ngoài” theo predicate cụ thể?
- Polygon có lỗ, tự cắt, đi qua kinh tuyến ±180° hoặc gần cực được xử lý thế nào?
- Lọc đồng thời theo tenant, trạng thái cửa hàng và khoảng cách có sử dụng index hiệu quả không?
- Có giới hạn số đối tượng, độ phức tạp hình học hoặc thời gian xử lý khi polygon rất nhiều đỉnh không?
- Độ trễ khi cập nhật vị trí liên tục và sự ổn định của sort theo khoảng cách ra sao?

Nếu yêu cầu thực là **tuyến đường ngắn nhất trên bản đồ giao thông**, cần công nghệ routing/graph đường đi phù hợp; geospatial index chỉ là một phần hỗ trợ xác định điểm/vùng.

## 7. Chức năng vector similarity: tìm gần nhất không đồng nghĩa tìm chính xác

Vector search xử lý các embedding số biểu diễn văn bản, hình ảnh hoặc đối tượng khác. Một embedding có thể có hàng trăm hoặc hàng nghìn chiều. Truy vấn thường tìm `k` vector “gần” vector câu hỏi theo một phép đo.

Ví dụ khái niệm:

~~~text
Câu hỏi người dùng
    ↓ embedding model M phiên bản v3
Query vector q
    ↓
ANN/vector index: tìm ứng viên gần q
    ↓
Lọc tenant, trạng thái, quyền truy cập
    ↓
Có thể rerank và trả top-k
~~~

Định nghĩa khoảng cách/độ tương tự:

- **Cosine similarity:** so sánh hướng vector, thường được dùng cho embedding văn bản đã phù hợp với cách chuẩn hóa của model.
- **Dot product:** phụ thuộc tích vô hướng; độ dài vector có thể ảnh hưởng kết quả nếu chưa chuẩn hóa.
- **Euclidean distance:** độ dài khoảng cách theo không gian vector.

Không được mặc định mọi embedding model phải dùng cosine hoặc mọi vector database trả điểm theo cùng thang giá trị. **Model embedding, phép đo và cách chuẩn hóa** phải là một hợp đồng nhất quán giữa indexing và querying.

### 7.1. Exact nearest neighbor và approximate nearest neighbor

Tìm exact nearest neighbor có thể so sánh vector truy vấn với toàn bộ tập dữ liệu liên quan. ANN (approximate nearest neighbor) dùng cấu trúc tìm kiếm tăng tốc nhưng có thể **bỏ sót láng giềng thực sự gần nhất**.

Một tiêu chí đánh giá phổ biến:

\[
\mathrm{Recall@K} =
\frac{|\text{TopK}_{\text{ANN}} \cap \text{TopK}_{\text{exact}}|}{K}
\]

Ví dụ top-10 ANN trùng 9 mục với top-10 exact thì `Recall@10 = 0,9` trên câu hỏi đó. Đo nhiều query đại diện, gồm cả query khó, filter hiếm, dữ liệu mới và các trường hợp nhiều vector rất gần nhau.

| Chức năng cần hỏi | Lý do |
|---|---|
| Số chiều embedding được hỗ trợ | Không thể nạp vector khác schema/độ dài mong đợi |
| Metric tương tự | Kết quả ranking khác theo cosine/dot/Euclidean |
| Kiểu index ANN và thông số | Ảnh hưởng memory, tốc độ tìm và recall |
| Metadata filtering | Filter trước/sau ANN ảnh hưởng cả đúng đắn và hiệu năng |
| Hybrid lexical + vector | Một câu hỏi chứa mã SKU, tên riêng hoặc keyword có thể cần cả hai |
| Update/delete vector | Tác động freshness, rebuild và storage |
| Multi-tenancy | Filter quyền truy cập phải đúng ngay cả khi ANN gần dữ liệu tenant khác |
| Batch indexing và backfill | Trạng thái index xây dựng và tác động lên query |
| Khả năng giải thích ranking | Có thể cần rerank hoặc hiển thị chứng cứ |

### 7.2. Một failure case quan trọng

Giả sử user thuộc tenant T01, truy vấn vector tìm 10 sản phẩm tương tự, nhưng index có sản phẩm của nhiều tenant. Nếu engine lấy top-10 ANN toàn cục rồi **lọc bỏ** các kết quả tenant khác, có thể còn hai sản phẩm T01, dù có 10 sản phẩm phù hợp hơn ở xa hơn. Cần kiểm tra query plan và cách engine thực hiện filtering, tăng số candidates nếu phù hợp hoặc dùng partition/index theo tenant khi quy mô/semantics yêu cầu.

Đừng tự khẳng định “có metadata filter” đồng nghĩa “luôn tìm đủ top-k hợp lệ với cùng recall và latency” trong mọi chế độ phân phối.

### 7.3. Thay embedding model là thay schema ngữ nghĩa

Nếu chuyển từ model M-v2 sang M-v3, dù số chiều bằng nhau, tọa độ và ý nghĩa vector có thể thay đổi. Kết quả tìm giữa vector query của model mới và data index của model cũ có thể vô nghĩa. Hệ thống nên quản lý `embeddingModelVersion`, kế hoạch re-embed/backfill và thời gian hai phiên bản cùng tồn tại.

Một document truy xuất minh họa:

~~~json
{
  "documentId": "doc-771",
  "tenantId": "t01",
  "embeddingModelVersion": "m-v3",
  "sourceVersion": 12,
  "textChecksum": "sha256:...",
  "indexedAt": "2026-11-14T08:30:00Z"
}
~~~

Các trường phụ này hỗ trợ đối soát; bản thân chúng không bảo đảm đồng bộ, vẫn cần quy trình update/version/repair.

## 8. Chức năng đồ thị: giới hạn số hop, độ bậc và chi phí mở rộng

Graph traversal có ý nghĩa khi nghiệp vụ đặt câu hỏi về **quan hệ nhiều bước**: ai quen ai, thiết bị nào dùng chung, sản phẩm nào thường được kết nối, tài khoản nào nằm trong một chuỗi giao dịch.

Cú pháp Cypher minh họa:

~~~cypher
MATCH (a:Account {id: $accountId})-[:USES]->(d:Device)
      <-[:USES]-(other:Account)
WHERE other <> a
RETURN DISTINCT other.id AS relatedAccountId
LIMIT 100;
~~~

Đây là truy vấn 2-hop qua `Device`. Chức năng chuyên biệt cần không chỉ là “truy vấn có dấu mũi tên”. Phải kiểm tra:

- Có hỗ trợ quan hệ có hướng, loại cạnh, thuộc tính cạnh, path matching và variable-length paths như yêu cầu không?
- Có index/lookup tốt cho đỉnh bắt đầu không?
- Với hub có hàng triệu cạnh, giới hạn frontier và độ trễ thực ra sao?
- Query `LIMIT 100` có phải vẫn duyệt hàng triệu ứng viên trước khi cắt không?
- Khi traversal đi qua shard hoặc region, có bao nhiêu RPC, byte truyền và vòng phụ thuộc?
- Khi một shard timeout, “không có đường đi” có bị nhầm với “không thể xác định” không?
- Ghi và xóa cạnh có những bảo đảm atomicity/consistency nào khi đỉnh liên quan nằm khác phân vùng?
- Hệ hỗ trợ thuật toán toàn đồ thị như connected components/PageRank ở engine OLTP hay cần pipeline analytics riêng?

Một graph engine có thể rất tốt cho 2-hop từ một ID, nhưng không phù hợp nếu ứng dụng yêu cầu aggregate nhiều tỷ cạnh liên tục trong cùng cluster giao dịch. **Độ sâu duyệt và phân bố bậc đỉnh** thường có ảnh hưởng lớn hơn chỉ đếm số đỉnh.

## 9. Chức năng key–value: cache, session, counter và TTL

Khi ứng dụng chủ yếu biết khóa đầy đủ và đọc một giá trị, key–value store thường là ứng viên đơn giản. Ví dụ với Redis:

~~~redis
SET cache:product:v4:t01:p42 "{\"name\":\"Keyboard\",\"status\":\"ACTIVE\"}" EX 300
GET cache:product:v4:t01:p42
INCR metrics:catalog:view:20261114
~~~

Nhưng “có lệnh `GET` và `SET`” không trả lời đầy đủ:

| Nhu cầu | Câu hỏi về giới hạn và hành vi |
|---|---|
| Cache | Hit/miss, TTL, eviction, stale cache, cache stampede |
| Session | Dữ liệu bền vững đến mức nào; mất node có mất session không? |
| Counter | Atomicity của INCR, độ chính xác toàn cluster, hot key |
| Distributed lock | Set-if-absent/expiry; chủ sở hữu, fencing, mất kết nối và clock |
| Pub/Sub/stream | Delivery guarantee, ordering, replay, consumer group, retention |
| Rate limit | Đồng hồ, window, Lua/transaction, consistency khi phân tán |
| Collection under one key | Big key, thao tác quét toàn bộ, giới hạn kích thước |
| Multi-key operation | Các key có cùng shard/slot không; cross-shard semantics thế nào? |

Ví dụ dùng `SET lock:key token NX PX ...` có thể tạo một cơ chế thuê tạm khóa, nhưng **không tự tạo distributed mutex an toàn cho nghiệp vụ có hậu quả nghiêm trọng**: cần nghĩ tới lock hết hạn khi client còn xử lý, owner token, thao tác giải phóng có điều kiện và cơ chế fencing ở tài nguyên đích.

Tương tự, Redis có thể dùng làm cache với một số lựa chọn persistence; không nên mặc định cache có durability và consistency phù hợp để làm nguồn giao dịch quan trọng mà chưa chứng minh.

## 10. Chức năng document: truy vấn trường lồng nhau, mảng và transaction

Document database hữu ích khi ứng dụng thường đọc/ghi một **aggregate** như đơn hàng chứa dòng hàng, địa chỉ và snapshot giá. Những tiêu chí cần xác nhận:

- Trường lồng nhau có thể truy vấn bằng dotted path không?
- Mảng scalar hoặc object có được lập chỉ mục và tìm theo phần tử không?
- Có phân biệt điều kiện áp vào **cùng một phần tử mảng** so với các phần tử khác nhau không?
- Truy vấn ghép equality, sort và range có tận dụng compound index không?
- Giới hạn kích thước một document và số/index entry thực tế là bao nhiêu?
- Atomicity ở cấp document và transaction đa document được hỗ trợ với điều kiện nào?
- Có thay đổi schema an toàn, validation và versioning không?

Ví dụ MongoDB:

~~~javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "ix_orders_customer_recent" }
);

db.orders.find({ customerId: "c42" })
  .sort({ createdAt: -1 })
  .limit(20);
~~~

Với mảng `items`, nếu muốn tìm một dòng có cả SKU-A và số lượng ít nhất 3, cần thể hiện **cùng phần tử**:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "SKU-A",
      quantity: { $gte: 3 }
    }
  }
});
~~~

Nếu bỏ `$elemMatch` và dùng hai điều kiện độc lập trên `items.sku` và `items.quantity`, một tài liệu có thể khớp bởi hai dòng hàng khác nhau. **Tính năng tồn tại chưa đủ; phải dùng đúng ngữ nghĩa.**

Transaction đa document có thể được một hệ document hỗ trợ nhưng vẫn có chi phí, điều kiện cấu hình và phạm vi bảo đảm riêng. Đừng suy luận “NoSQL luôn thiếu transaction” hay “có transaction nghĩa là mọi thao tác phân tán không có đánh đổi”.

## 11. Chức năng wide-column: đọc theo phân vùng và thứ tự trong nhóm

Với log hoặc sự kiện có khóa truy cập được biết trước, hệ cột rộng như Cassandra/ScyllaDB có thể phù hợp. Chìa khóa thiết kế thường là **partition key** và **clustering columns**.

Ví dụ mô hình CQL:

~~~sql
CREATE TABLE access_by_user_day (
    tenant_id text,
    user_id text,
    bucket_day date,
    occurred_at timestamp,
    event_id uuid,
    action text,
    PRIMARY KEY (
        (tenant_id, user_id, bucket_day),
        occurred_at, event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

Truy vấn đọc 20 sự kiện mới nhất trong một ngày:

~~~sql
SELECT occurred_at, event_id, action
FROM access_by_user_day
WHERE tenant_id = 't01'
  AND user_id = 'u42'
  AND bucket_day = '2026-11-14'
LIMIT 20;
~~~

Giới hạn cần xem:

- Điều kiện lọc có đầy đủ partition key và tiền tố clustering theo khả năng của engine không?
- Một user nóng có làm partition quá lớn hoặc hot partition không?
- Bucket giờ/ngày làm tăng fan-out khi truy vấn lịch sử dài ra sao?
- Secondary index, materialized view, LWT hoặc transaction có hỗ trợ đúng use case không?
- Consistency level và replication factor có đáp ứng yêu cầu read-after-write không?
- TTL, tombstone, compaction và repair ảnh hưởng truy vấn lịch sử thế nào?

Wide-column không nên bị ép làm một hệ phân tích ad hoc có thể lọc mọi trường và JOIN tùy ý. Nếu màn hình mới có access pattern khác, cần cân nhắc bảng/projection đọc khác và cách đồng bộ.

## 12. Khi sản phẩm quảng cáo “multi-model”

Một sản phẩm multi-model có thể hỗ trợ document + graph, document + vector, key–value + search hoặc nhiều kiểu dữ liệu khác trong cùng hệ sinh thái. Điều đó có lợi khi giảm số hệ cần quản lý, nhưng **tên tính năng không chứng minh chất lượng và giới hạn tương đương sản phẩm chuyên dụng**.

Ví dụ một document database có vector index: nếu ứng dụng cần lọc metadata đơn giản và ANN với số lượng vector vừa phải, nó có thể đáp ứng. Nhưng nếu workload cần hàng trăm triệu vector, recall rất cao sau filter phức tạp, re-index thường xuyên và search concurrency lớn, vẫn phải đo và kiểm tra cấu hình cụ thể.

Ngược lại, đưa mọi chức năng sang từng sản phẩm chuyên dụng cũng tạo **chi phí đồng bộ dữ liệu, vận hành, bảo mật, backup, đào tạo và xử lý sự cố**. Không có số lượng database tối ưu chung.

Cần tách ba câu hỏi:

1. Sản phẩm **diễn đạt được truy vấn** không?
2. Sản phẩm **đạt SLO/correctness** cho dữ liệu và tải thực tế không?
3. Sản phẩm **vận hành và tiến hóa** được trong ràng buộc nhóm phát triển không?

Nếu một engine đủ cả ba, thêm engine khác chỉ vì tính năng nghe hấp dẫn có thể làm hệ thống phức tạp hơn mức cần thiết.

## 13. Ma trận chọn chức năng theo access pattern

Bảng dưới đây chỉ là **bộ lọc ứng viên ban đầu**. Dấu “nên đánh giá” không khẳng định sản phẩm tương ứng chắc chắn đủ mọi yêu cầu.

| Access pattern chính | Nhóm chức năng nên đánh giá | Dữ liệu/khóa quan trọng | Phép thử quyết định |
|---|---|---|---|
| `GET` theo ID, TTL, cập nhật counter | Key–value | Key, TTL, value size | p99, hit/miss, hot key, persistence |
| Aggregate có nested fields | Document | Document ID, dotted path, array | Query explain, index size, update semantics |
| Sự kiện theo user và thời gian | Wide-column / time-series | Partition key, timestamp, bucket | p95, partition skew, retention |
| Tổng hợp số đo theo cửa sổ | Time-series | Tag/series, time range | Ingest, downsampling, late events |
| Text có relevance ranking | Full-text search | Text, analyzer, filters | MRR/NDCG, p95, refresh lag |
| Tìm trong bán kính hoặc polygon | Geospatial | WGS84 coords, geometry, filters | Sai số biên, distance, query p95 |
| Top-k ngữ nghĩa | Vector | Embedding model, metric, metadata | Recall@K, filter correctness, p99 |
| Quan hệ 2–4 hop | Graph | Vertex/edge type, starting ID | Frontier growth, remote hops, correctness |
| Aggregate nhiều chiều trên toàn bộ tập | Analytics engine | Column, time partition, batch | Scan throughput, query concurrency, cost |

Với một yêu cầu kết hợp, chẳng hạn “tìm 10 cửa hàng gần nhất có mô tả chứa ‘cà phê’”, cần kiểm tra **sự kết hợp giữa geo và full-text** có thực hiện được trong cùng truy vấn và đúng ranking/filter không. Hai chức năng được hỗ trợ riêng lẻ chưa chắc kết hợp hiệu quả.

Một yêu cầu khác: “tìm tài liệu tương tự nhưng chỉ trong tenant T01, còn hiệu lực, sau đó sort theo giá”. Cần kiểm tra vector index, metadata filter, exact sort và pagination **cùng nhau**. Đừng suy kết quả tổ hợp từ danh sách tính năng độc lập.

## 14. Chia giới hạn sản phẩm thành sáu nhóm

Khi đọc tài liệu một sản phẩm, nên phân loại giới hạn trước khi đánh giá:

| Nhóm giới hạn | Ví dụ câu hỏi | Nếu không kiểm tra |
|---|---|---|
| **Hard limit/schema** | Tối đa kích thước document/value, số chiều vector, độ dài key, số field/index, kiểu geometry | Ghi lỗi hoặc dữ liệu không thể biểu diễn |
| **Query semantics** | Hỗ trợ toán tử, JOIN/traversal, sort, filter, transaction/consistency | Kết quả sai hoặc không diễn đạt được nghiệp vụ |
| **Scale/performance** | Thông lượng ingest, index build, shard imbalance, giới hạn scan | p95/p99 tăng khi tải hoặc dữ liệu tăng |
| **Distribution/failure** | Replica, failover, cross-region, read freshness, quórum và recovery | Mất dữ liệu/đọc cũ hoặc không đạt RTO |
| **Product/edition/service** | Tính năng chỉ có ở bản enterprise, cloud plan hoặc plugin; quota/region | POC chạy nhưng production không khả dụng |
| **Operation/lifecycle** | Backfill, reindex, upgrade, backup/restore, retention, metrics | Khó vận hành, downtime hoặc chi phí lớn |

Cần phân biệt:

- **Hard limit:** mức hệ quản trị/API từ chối hoặc không hỗ trợ.
- **Operational limit:** ngưỡng nhóm đặt **thấp hơn** để giữ độ trễ/chi phí chấp nhận được.
- **Observed limit:** mức đạt được trong **một phép thử cụ thể** với version, cấu hình và dữ liệu cụ thể.

Một engine cho phép tạo index với hàng triệu bản ghi không có nghĩa index đó sẽ đáp ứng p99 ở tốc độ nạp mong muốn. Ngược lại, một benchmark nhỏ chậm có thể do mapping, query, driver hoặc cấu hình thử chưa phù hợp; không nên suy thành kết luận vĩnh viễn về sản phẩm.

## 15. Vì sao phải ghi rõ phiên bản, edition và chế độ triển khai?

Những câu như “sản phẩm X hỗ trợ vector search”, “sản phẩm Y có distributed transaction” thiếu ít nhất bốn thành phần:

1. **Phiên bản chính xác** của server/cluster, plugin và client/driver.
2. **Edition/gói dịch vụ**: bản cộng đồng, thương mại hay dịch vụ managed nào.
3. **Topology**: một node, replica set, sharded cluster, một hay nhiều region.
4. **Cấu hình kích hoạt**: index type, feature flag, consistency/replication, memory và quota.

Ví dụ một chức năng có thể chạy trên một node nhưng có ràng buộc khác khi sharding; một loại index có thể hỗ trợ equality mà không hỗ trợ sort mong muốn; một tính năng được giới thiệu ở phiên bản mới nhưng client library cũ chưa có API tương ứng.

Khi tài liệu quảng bá và API thực tế có vẻ mâu thuẫn, cần **kiểm tra tài liệu của đúng phiên bản, feature matrix, release notes và thí nghiệm nhỏ** trước khi chốt kiến trúc. Không tự điền các giới hạn bằng con số đọc được từ một bài blog cũ hoặc sản phẩm khác cùng họ.

## 16. Quy trình xác minh chức năng theo từng sản phẩm

Với mỗi tính năng ứng viên, lập một **capability record** gồm yêu cầu, bằng chứng, giới hạn và trạng thái. Ví dụ:

~~~yaml
capabilityId: "catalog-fulltext-with-filter"
businessQuestion: "Find 20 relevant active products in the current tenant"
mustHave:
  - "Correct tenant and status filter"
  - "Vietnamese text handling per test queries"
  - "Stable pagination"
  - "Freshness within the agreed window"
candidate:
  product: "<product-name>"
  serverVersion: "<exact-version>"
  edition: "<edition-or-managed-tier>"
  topology: "<nodes-shards-replicas-regions>"
evidence:
  officialDocs: "<version-specific-doc-reference>"
  reproducibleQuery: "<test-script-or-query>"
  expectedResultFixture: "<fixture-name>"
  benchmark: "<measurement-report>"
openQuestions:
  - "Effect of rare filters on ranking and p99"
  - "Rebuild and rollback procedures"
decision: "UNVERIFIED"
~~~

Các chuỗi trong ngoặc nhọn chỉ là chỗ điền thông tin, không phải số liệu được xác nhận. Một record nên có người chịu trách nhiệm và ngày xác minh, vì tính năng có thể thay đổi khi nâng phiên bản/gói dịch vụ.

### Trình tự kiểm tra

1. **Viết hợp đồng truy vấn/cập nhật** bằng ngôn ngữ nghiệp vụ, có kết quả đúng mong muốn.
2. **Xác định product/version/edition/topology** của POC và production.
3. **Đọc tài liệu chính thức đúng phiên bản**: API, feature availability, constraints, known limitations, upgrade notes.
4. **Dựng fixture nhỏ** có trường thiếu, giá trị trùng, ký tự đặc biệt, filter nhiều tenant và ranh giới thời gian.
5. **Chạy query/update có thể tái tạo**; lưu đầu vào và kết quả thực.
6. **Thử điều kiện biên**: null, array, long text, tọa độ biên, vector kích thước sai, hot key, graph hub.
7. **Thử cấu hình phân tán cần thiết**: replica, shard, consistency, lỗi node và độ mới dữ liệu.
8. **Benchmark với dữ liệu và tải đại diện**; đo cả tốc độ và mức sử dụng tài nguyên.
9. **Ghi kết luận có phạm vi**: được xác nhận ở đâu, chưa biết ở đâu, cần kiểm tra lại khi nào.

Một POC chạy thành công trên một node không chứng minh các mức nhất quán và failure semantics của cụm nhiều region. Cần phân biệt rõ “đã thử” và “được tài liệu mô tả” trong bản quyết định.

## 17. Test biên để phát hiện khác biệt giữa hai sản phẩm

Hai hệ có thể trả cùng kết quả với dữ liệu đơn giản nhưng khác nhau ở trường hợp biên. Bộ fixture cần có những câu hỏi như:

| Chức năng | Dữ liệu biên | Kết quả cần kiểm tra |
|---|---|---|
| Full-text | “cafe”, “cà phê”, từ ghép, chính tả sai, stopword | Analyzer/ranking có phù hợp tiếng Việt? |
| Exact filter | Trường không tồn tại, `null`, chuỗi rỗng | Kết quả có đúng quy tắc thiếu dữ liệu? |
| Time-series | Timestamp đúng 00:00 UTC, event đến muộn, duplicate | Bucket và aggregate có đếm đúng? |
| Geospatial | Điểm ngay sát ranh giới, đổi thứ tự lat/lon | Hệ tọa độ/đơn vị và predicate có đúng? |
| Vector | Hai embedding bằng nhau, filter hiếm, model version khác | Recall và lọc quyền truy cập có đúng? |
| Graph | Supernode, chu trình, cạnh hai chiều, shard timeout | Không đếm trùng, giới hạn traversal, lỗi rõ? |
| Key–value | Giá trị lớn, TTL hết hạn, hot key, retry | Timeout, eviction và idempotency ra sao? |
| Document | Hai array elements thỏa hai điều kiện khác nhau | Predicate có yêu cầu cùng một phần tử? |

Đặc biệt, **không được bỏ qua tenant/authorization**. Nếu bộ tìm kiếm hay vector index chứa dữ liệu nhiều tenant, kiểm tra rằng đường truy vấn thật sự áp filter và không để lộ dữ liệu qua kết quả, gợi ý tự động, cache hoặc error response.

## 18. Chỉ kiểm tra cú pháp là chưa đủ

Một câu query chạy được có thể vẫn dùng đường thực thi rất đắt. Ví dụ:

~~~text
Đầu vào: top-20 sản phẩm có tên khớp query
  ↓
Index chỉ giúp lọc 20 triệu kết quả ứng viên
  ↓
Engine phải sort toàn bộ kết quả theo một trường khác
  ↓
Trả 20 mục, nhưng p99 tăng đột biến
~~~

Vì thế, với mỗi khả năng đã xác nhận về mặt **ngữ nghĩa**, còn cần đọc:

- **Query plan hoặc profiler:** có quét index phù hợp, quét collection, bước sort, aggregation hoặc remote call không?
- **Candidate expansion:** ANN truy bao nhiêu vector, graph duyệt bao nhiêu cạnh, search trả bao nhiêu document trung gian?
- **Network hops:** có scatter/gather qua shard hoặc region không?
- **Write amplification:** thêm index/projection ảnh hưởng INSERT/UPDATE/DELETE thế nào?
- **Memory/CPU/I/O:** thao tác nào làm tăng cache miss, compaction, GC hoặc queue?
- **Data movement:** backfill/reindex và failover có tốn băng thông, egress không?

Đừng đồng nhất **“có index” với “query luôn nhanh”**. Index chỉ tốt khi phù hợp điều kiện lọc/sort và dữ liệu. Một projection được tạo để đọc nhanh cũng cần chi phí đồng bộ và quản lý thay đổi.

## 19. Thử chức năng chuyên biệt bằng hai lớp phép đo

Một kế hoạch thí nghiệm nên có hai giai đoạn riêng.

### 19.1. Giai đoạn A — Semantic conformance

Giai đoạn này kiểm tra câu trả lời có đúng và ổn định:

~~~text
Fixture nhỏ có expected outputs
   |
   +-- Từ khóa / analyzer / relevance
   +-- Filter tenant, giá, trạng thái
   +-- Địa lý: khoảng cách, polygon, ranh giới
   +-- Vector: top-k exact baseline, metric, metadata filter
   +-- Time: UTC windows, late event, dedup
   +-- Graph: chiều cạnh, cycle, maximum depth
   +-- Ghi: uniqueness, retry, concurrent update
   |
   v
Ghi PASS / FAIL / NEEDS INVESTIGATION
~~~

Ví dụ vector dùng một tập nhỏ có thể tính exact nearest neighbor bằng brute force làm chuẩn đối chiếu ANN; geospatial cần một tập điểm có khoảng cách và kết quả nằm trong/ngoài được kiểm tra độc lập. Với search relevance không có một đáp án duy nhất cho mọi truy vấn, cần bộ câu hỏi có đánh giá mức độ liên quan do người hiểu nghiệp vụ cung cấp.

### 19.2. Giai đoạn B — Performance và operations

Sau khi truy vấn đúng, đo ở quy mô đại diện:

| Nhóm chỉ số | Cần đo |
|---|---|
| Latency | p50/p95/p99 end-to-end theo từng query |
| Throughput | Số request/giây thực hoàn thành và offered load |
| Đúng đắn | Error rate, recall, missing/stale result, duplicate events |
| Mức mới dữ liệu | Indexing/replication/projection lag |
| Tài nguyên | CPU, RAM, disk I/O, network, storage và cache |
| Hiệu quả index | Index size, build time, keys/docs/candidates scanned |
| Quy mô | Shard skew, hot key/partition, batch size, fan-out |
| Chi phí | Chi phí node, license, storage, backup, egress |
| Độ bền | Failover behavior, RPO/RTO và restore thành công |

Không nên gộp kết quả p95 của full-text query với p95 của key–value GET rồi kết luận “sản phẩm A nhanh hơn B”, vì chúng giải quyết chức năng khác nhau và kích thước response có thể khác. Benchmark phải so sánh **đường nghiệp vụ tương đương**, hoặc nêu rõ khác biệt.

## 20. Ví dụ kiến trúc: một nguồn chuẩn và nhiều đường đọc

Giả sử hệ thống giữ **catalog sản phẩm** ở một nguồn giao dịch có thẩm quyền, sau đó phục vụ các truy vấn phụ bằng chỉ mục tìm kiếm, vector hoặc cache.

~~~mermaid
flowchart TD
    A["Product Command API"] --> B["Nguồn catalog có thẩm quyền"]
    B --> C["Outbox hoặc CDC có cơ chế phát lại"]
    C --> D["Search projection"]
    C --> E["Vector / semantic projection"]
    C --> F["Cache invalidation hoặc refresh"]
    D --> G["Keyword + filter API"]
    E --> H["Semantic search API"]
    B --> I["Product detail API"]
    F --> J["Cached read API"]
~~~

Sơ đồ thể hiện **một phương án kiến trúc**, không phải yêu cầu phải triển khai đủ bốn hệ. Nếu một sản phẩm duy nhất đáp ứng các access pattern, giảm số tầng có thể đơn giản hơn. Nếu chọn nhiều hệ, cần xác định:

- Ai là **nguồn chân lý** về sản phẩm, giá, trạng thái và quyền truy cập?
- Khi sản phẩm bị ngừng bán, search/vector/cache phải cập nhật trong bao lâu?
- Event thay đổi có định danh và version để consumer xử lý retry/out-of-order không?
- Khi consumer bỏ lỡ sự kiện, có thể backfill/rebuild projection từ nguồn chuẩn không?
- Nếu index thiếu một sản phẩm, API có trả kết quả thiếu và theo dõi lag hay fallback?
- Nếu giá từ search index cũ, bước kiểm tra cuối trước khi mua dùng dữ liệu nào?
- Backup/restore của từng projection có cần cùng thời điểm với nguồn chuẩn không?

**Dual-write trực tiếp** từ ứng dụng sang hai hệ mà không có quy trình phát lại/đối soát rất dễ tạo lệch dữ liệu khi một thao tác thành công và thao tác còn lại thất bại. Outbox/CDC là các hướng thiết kế phổ biến, song bản thân chúng vẫn cần xử lý duplicates, ordering, replay, poison messages và schema evolution.

### 20.1. Tính mới của dữ liệu là hợp đồng

Ví dụ catalog có cam kết:

- Giá và tồn kho chính xác tại bước xác nhận đơn hàng: đọc từ nguồn nghiệp vụ có bảo đảm phù hợp.
- Kết quả tìm kiếm có thể chậm cập nhật trạng thái tối đa vài giây theo thỏa thuận.
- Gợi ý vector có thể cập nhật theo batch nếu sản phẩm không đòi hỏi tức thời.
- Cache sản phẩm phải có cơ chế invalidate khi thay đổi nhạy cảm.

Cần ghi rõ **độ trễ được phép**, không dùng câu “eventual consistency là đủ” mà không định nghĩa bao lâu hoặc trường hợp nào.

### 20.2. Phiên bản dữ liệu và sự kiện đến sai thứ tự

Ví dụ cùng sản phẩm `p42` có hai update:

~~~text
v11: status = ACTIVE
v12: status = DISCONTINUED
~~~

Nếu consumer nhận v12 rồi nhận lại v11 vì retry, projection không nên tự động quay về ACTIVE. Có thể ghi version và áp điều kiện **chỉ nhận version mới hơn** theo cơ chế storage hỗ trợ; khi dữ liệu có nhiều nguồn cập nhật, cần quy tắc so sánh/versioning phù hợp, không tự tin chỉ dựa trên đồng hồ của client.

## 21. Khi chỉ một database là đủ và khi nên tách chuyên biệt

Cần so sánh chi phí tổng thể, không chỉ tốc độ của một query:

| Phương án | Phù hợp khi | Chi phí/rủi ro |
|---|---|---|
| Một engine đáp ứng toàn bộ query | Quy mô vừa, feature đủ tốt, nhóm vận hành nhỏ | Một engine phải chịu nhiều loại workload, tính năng phụ có thể giới hạn |
| Engine nguồn chuẩn + search | Cần relevance tốt, analyzer và filter chuyên dụng | Projection lag, reindex, đồng bộ trạng thái |
| Nguồn chuẩn + vector | Cần semantic retrieval hoặc hybrid search | Embedding lifecycle, ANN recall, filter semantics |
| Nguồn chuẩn + time-series | Sự kiện rất nhiều, aggregate/retention chuyên dụng | Ingest pipeline, timestamp/duplicate/late-event handling |
| Nguồn chuẩn + graph | Quan hệ nhiều hop là tính năng chính | Duy trì edge/vertex projection, consistency, graph operations |
| Nhiều hệ chuyên biệt cùng lúc | Các workload đủ lớn, khác biệt và có SLO riêng | Nhiều cluster, bảo mật, backup, chi phí và khắc phục sự cố |

Ví dụ một ứng dụng nhỏ có vài nghìn sản phẩm có thể chưa cần vector database riêng, nếu full-text và filters đã đáp ứng nhu cầu. Nhưng nếu tính năng tìm kiếm ngữ nghĩa là chức năng cốt lõi, quy mô lớn và đòi hỏi recall/latency cụ thể, việc đánh giá vector engine chuyên biệt là hợp lý.

Cách quyết định hữu ích: chỉ thêm một hệ khi **bằng chứng** cho thấy chức năng cần thiết không được đáp ứng đủ bởi kiến trúc đơn giản hơn hoặc khi chi phí vận hành của phương án đơn trở nên kém chấp nhận.

## 22. Các bẫy khi đọc tính năng sản phẩm

| Nhận định vội vàng | Vì sao không đủ | Việc cần xác minh |
|---|---|---|
| “Có full-text index” | Có thể thiếu analyzer hoặc ranking phù hợp | Tập query tiếng Việt, MRR/NDCG, filter và refresh |
| “Có vector search” | Chưa biết recall, metric, filtered ANN, model lifecycle | Recall@K, latency, dimension, version |
| “Có geo query” | Có thể khác hệ tọa độ, đơn vị và geometry support | Điểm/polygon biên, khoảng cách và hiệu năng |
| “Có time-series” | Có thể khác về late events, retention, downsampling | Window semantics, TTL, series cardinality |
| “Có graph traversal” | Chưa biết hỗ trợ phân tán hay giới hạn supernode | Hop depth, remote RPC, failure behavior |
| “Có distributed transaction” | Mức cô lập, phạm vi và giới hạn tùy topology | Concurrent updates, lỗi node, retry/idempotency |
| “Có TTL” | TTL tính theo thời gian ghi hay event time? | Expiry semantics, tác động tombstone/eviction |
| “Scale horizontal” | Hot key/shard, global sort hoặc cross-region có thể nghẽn | Workload skew, p99, repartition |
| “Một triệu record rất nhanh” | Chưa biết độ lớn record, phân bố và query mix | Dữ liệu/tải đại diện, kết quả end-to-end |
| “Cloud managed nên không phải vận hành” | Vẫn cần schema, index, backup, quota, alert, migration | Runbook, restore, cost và ownership |

Một checklist khả năng không thể thay thế **thí nghiệm đúng tác vụ**. Khi kết quả của fixture không đúng, phải xem lại ngữ nghĩa, schema hoặc chọn công nghệ, kể cả khi kết quả benchmark rất nhanh.

## 23. Bài thực hành: xây bảng quyết định cho một hệ tìm sản phẩm

**Đề bài:** một ứng dụng có 2 triệu sản phẩm, vài triệu sự kiện xem mỗi ngày và nhiều tenant. Người dùng cần tìm sản phẩm bằng từ khóa, lọc theo địa điểm, nhận gợi ý tương tự, xem sản phẩm chi tiết và xem số lượt xem theo giờ. Bộ dữ liệu và lưu lượng là **kịch bản giả định** để thiết kế bài tập.

### Phần A — Viết yêu cầu đo được

1. Xác định các query dùng ID, text, geo, vector và time-series. Với mỗi query, viết input, output, filter và thứ tự sắp xếp.
2. Nêu kết quả nào phải chính xác tuyệt đối, kết quả nào được phép approximate hoặc trễ; định nghĩa độ trễ cho phép.
3. Đề xuất SLO p95 và tỷ lệ lỗi theo từng API; ghi tải dự kiến và kích thước response.
4. Định nghĩa tenant boundary, trường nào được phép xuất hiện trong search/gợi ý và sự kiện nào là dữ liệu nhạy cảm.

### Phần B — Chọn khả năng và sản phẩm ứng viên

Tạo ma trận ít nhất ba sản phẩm/nhóm sản phẩm. **Không cần giả định rằng một sản phẩm sẽ thắng toàn bộ bài toán.**

| Yêu cầu | Chức năng phải chứng minh | Test quyết định |
|---|---|---|
| Tìm từ khóa | Analyzer, phrase/fuzzy, filter, ranking | Bộ 100 truy vấn có đánh giá liên quan |
| Tìm gần | Geo point, radius, distance, sort/filter | Trường hợp biên và dataset tọa độ đúng |
| Gợi ý tương tự | Vector metric, top-k, tenant filter | Exact baseline, Recall@10, p99 |
| Thống kê lượt xem | Event ingest, window aggregation, retention | Late events, duplicates, 1/7/30 ngày |
| Đọc sản phẩm | Lookup ID, tính nhất quán giá/trạng thái | Concurrent update, read-after-write |
| Quan hệ sản phẩm | Graph link hoặc projection đơn giản | 1-hop/2-hop, supernode/fan-out |

Ghi rõ version/edition/topology. Nếu chưa tìm được bằng chứng chính thức về một tính năng, trạng thái là **UNVERIFIED**; không đánh dấu “hỗ trợ” dựa trên tên marketing.

### Phần C — Dựng fixture và test biên

- Tạo hai sản phẩm tên gần giống nhau, một từ có dấu và một từ không dấu; thử analyzer và ranking.
- Tạo cửa hàng ở đúng gần ranh giới bán kính 3 km; thử đơn vị và thứ tự tọa độ.
- Tạo 100 embedding giả định có thể tính khoảng cách chính xác, rồi so kết quả ANN với exact top-k.
- Tạo sự kiện đúng mốc `00:00:00Z`, sự kiện đến muộn một ngày và một event được gửi hai lần.
- Tạo cùng một `productId` ở hai tenant theo quy tắc định danh của ứng dụng, xác nhận mọi filter và cache bảo toàn phạm vi tenant.
- Xóa hoặc thay đổi trạng thái sản phẩm; đo thời gian cho search/vector/cache cập nhật kết quả.

**Đầu ra** phải là kết quả mong đợi, kết quả thực và ghi chú về bất kỳ khác biệt nào, thay vì chỉ ảnh chụp giao diện thành công.

### Phần D — Benchmark

Thiết lập các bài tải có phân bố dữ liệu thực tế: sản phẩm hot/ít hot, truy vấn ngắn/dài, tenant lớn/nhỏ, event liên tục/đột biến. Đo:

- p50/p95/p99, lỗi, timeout và throughput thực đạt.
- Precision/recall hoặc chỉ số relevance đối với tìm kiếm.
- Độ trễ index/replica/projection sau update.
- Số ứng viên phải quét, số shard truy cập, bytes trả về.
- CPU/RAM/I/O/network, index size, quá trình rebuild.
- Khả năng phục hồi khi tắt một replica hoặc ngắt kết nối với projection trong môi trường thử thích hợp.

Đặt một **tiêu chí chấp nhận có số** cho từng chức năng trước khi đo. Nếu không đạt, chỉ thay một nhóm biến quan trọng mỗi lượt: query, index, schema, topology hoặc workload. Lưu dữ liệu thô và cấu hình để người khác tái hiện.

### Phần E — Chốt quyết định

Viết một đoạn quyết định cho mỗi chức năng:

~~~text
Bài toán và truy vấn:
Các phương án đã kiểm tra:
Phiên bản/edition/topology:
Semantics đã xác nhận:
Các giới hạn từ tài liệu chính thức:
Các giới hạn quan sát được trong thử nghiệm:
Chi phí đồng bộ và vận hành:
Nguyên nhân chọn/bác bỏ:
Giới hạn của kết luận:
Tín hiệu phải đánh giá lại trong tương lai:
~~~

Đừng chỉ viết “chọn X vì phổ biến”. Hãy giải thích bằng **đúng yêu cầu nào, test nào đã qua, giá phải trả và điều kiện nào khiến quyết định phải đổi**.

## 24. Câu hỏi tự kiểm tra

1. Vì sao “hỗ trợ full-text search” chưa đủ để khẳng định tìm tiếng Việt và relevance đạt yêu cầu?
2. Vì sao kết quả vector ANN có thể khác kết quả exact top-k, và metric nào cần dùng để định lượng?
3. Một vector query có tenant filter có thể bị giảm recall như thế nào nếu việc lọc không được xét đúng trong tìm kiếm?
4. Để tìm cửa hàng trong 3 km, cần phân biệt tọa độ, đơn vị và đường đi giao thông ra sao?
5. Khi một time-series event đến muộn, TTL 30 ngày tính từ lúc ghi có khác retention theo event time không?
6. Vì sao có graph traversal 2-hop không tự bảo đảm truy vấn đủ nhanh khi đi qua supernode và nhiều region?
7. Khi source catalog cập nhật status thành INACTIVE nhưng search index còn ACTIVE, hệ thống nên đáp ứng hợp đồng freshness và kiểm tra bước mua như thế nào?
8. “Hard limit”, “operational limit” và “observed limit” khác nhau ra sao?
9. Vì sao cần ghi exact version, edition, topology và driver khi xác nhận tính năng?
10. Khi một sản phẩm multi-model đáp ứng cú pháp query, còn cần kiểm tra những gì trước khi bỏ một sản phẩm chuyên biệt?
11. Vì sao phải đo cả INSERT/UPDATE/DELETE khi bổ sung index mới để cải thiện đọc?
12. Một POC trên một node có thể chứng minh và không thể chứng minh những gì về failover, consistency và cross-region?
13. Khi dùng outbox/CDC để đồng bộ projection, cần giải quyết duplicate event và cập nhật sai thứ tự như thế nào?
14. Vì sao cùng p95 100 ms giữa hai engine không đủ để kết luận chúng tương đương nếu dữ liệu, query mix, correctness và resource khác nhau?

## 25. Cách đưa quyết định vào vận hành

Chọn chức năng chuyên biệt là một vòng lặp, vì **workload, dữ liệu, nhà cung cấp và phiên bản luôn có thể thay đổi**. Khi sản phẩm tăng từ vài trăm nghìn lên hàng chục triệu bản ghi, khi xuất hiện tenant cực lớn hoặc khi nâng major version, những giới hạn từng được kiểm chứng cần được đo lại.

Một nhóm vận hành nên giữ:

- **Capability register**: yêu cầu, product/version/edition, tính năng đã xác nhận, giới hạn và người sở hữu.
- **Benchmark baseline**: fixture, seed, workload, kết quả p95/p99, chất lượng tìm kiếm và chi phí.
- **Schema/index record**: index/vector dimension/analyzer/partition key và cách backfill.
- **Data ownership map**: nguồn chuẩn, các projection, cách sync, freshness SLO và cơ chế reconciliation.
- **Runbook**: phát hiện lag, xử lý index lỗi, rebuild, failover, restore và kiểm tra tính đúng đắn.
- **Trigger đánh giá lại**: vượt ngưỡng dữ liệu, thay query pattern, tăng chi phí, giảm recall/relevance hoặc thay edition/version.

Một quyết định tốt phải trả lời được **chức năng nào phục vụ yêu cầu nào, đã kiểm chứng giới hạn bằng bằng chứng gì, chi phí vận hành ra sao và dấu hiệu nào cho biết cần đổi thiết kế**. Đó là cách lựa chọn mô hình chuyên biệt trong NoSQL mà không biến tên công nghệ thành lời giải mặc định.
