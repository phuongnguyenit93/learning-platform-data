# OpenSearch Serverless và lựa chọn workload phù hợp

## Mục tiêu bài học

Trong hệ sinh thái CLOUD_PROVIDERS_AWS, Amazon OpenSearch Service cung cấp khả năng tìm kiếm toàn văn, phân tích log và tìm kiếm ngữ nghĩa trên vector embedding. Khi dùng domain provisioned, đội vận hành phải chọn instance, storage, shard, replica, nâng cấp phiên bản và điều chỉnh capacity. Amazon OpenSearch Serverless loại bỏ phần lớn công việc quản lý cluster bằng cách tự cấp phát và mở rộng compute cho từng collection.

Serverless không có nghĩa là mọi workload đều tự động rẻ hơn hoặc không cần thiết kế. Người dùng vẫn phải chọn collection type, thiết kế mapping và query, đặt giới hạn OpenSearch Compute Units (OCUs), kiểm soát quyền truy cập, chọn đường ingest và theo dõi latency/cost. Lựa chọn sai collection type hoặc giới hạn capacity có thể làm tăng chi phí, giảm hiệu năng hoặc khiến một API cần thiết không được hỗ trợ.

Sau bài học, người học có thể:

- Giải thích collection, index, OCU và kiến trúc tách biệt indexing/search.
- Phân biệt collection type Search, Time series và Vector search.
- Phân biệt thế hệ NextGen và Classic, collection group và scale-to-zero.
- Chọn OpenSearch Serverless hay provisioned domain theo đặc điểm workload.
- Thiết kế mapping, ingest pipeline, query và vector search cơ bản.
- Chọn OpenSearch Ingestion, Data Firehose, Fluent Bit, Lambda hoặc client trực tiếp để nạp dữ liệu.
- Cấu hình encryption, network và data access policies theo least privilege.
- Đo capacity, storage, latency, indexing throughput và chi phí.
- Nhận diện giới hạn API/plugin, snapshot, cross-account và cross-Region.
- Lập kế hoạch migration, kiểm thử tải và vận hành collection production.

## 1. OpenSearch Serverless giải quyết bài toán nào?

Amazon OpenSearch Serverless là lựa chọn triển khai theo nhu cầu của Amazon OpenSearch Service. Người dùng tạo collection và index, gửi tài liệu để lập chỉ mục, sau đó thực hiện truy vấn. Dịch vụ quản lý compute, shard placement, index lifecycle, software updates và scaling thay cho việc vận hành cluster node.

Một collection là nhóm các OpenSearch index phục vụ một workload hoặc mục đích sử dụng. Ví dụ:

- Collection product-search chứa index sản phẩm cho tìm kiếm trên website.
- Collection application-logs chứa log ứng dụng và truy vấn điều tra sự cố.
- Collection knowledge-vectors chứa embedding của tài liệu để tìm kiếm ngữ nghĩa và RAG.

Serverless phù hợp khi traffic không đều, có thời điểm nhàn rỗi, khó dự báo hoặc đội ngũ muốn tập trung vào dữ liệu và query thay vì quản lý cluster. Dịch vụ vẫn cần capacity để lập chỉ mục và truy vấn; compute được tính phí theo OCU và storage được tính riêng.

## 2. Kiến trúc: collection, index và OCU

Trong domain provisioned truyền thống, cùng một nhóm node thường xử lý cả indexing và search, còn dung lượng index gắn chặt với storage và compute của cluster. OpenSearch Serverless tách compute ingest khỏi compute query và dùng Amazon S3 làm lớp lưu trữ chính cho index.

~~~mermaid
flowchart LR
    P[Producers and applications] --> I[Indexing compute]
    I --> S3[(Managed storage on Amazon S3)]
    S3 --> Q[Search compute]
    Q --> C[Search clients and dashboards]
    I --> CW[CloudWatch metrics]
    Q --> CW
    S3 --> B[Collection and index metadata]
~~~

Khi producer ghi tài liệu, indexing compute xử lý và lưu index vào storage được quản lý. Khi ứng dụng truy vấn, search compute lấy dữ liệu index cần thiết từ storage hoặc cache cục bộ, rồi thực hiện search và aggregation. Hai loại compute có thể scale độc lập, nên một đợt bulk ingest không nhất thiết phải dùng cùng một mức compute như giờ cao điểm truy vấn.

Capacity được đo bằng OpenSearch Compute Unit:

- Một OCU gồm 6 GiB memory, vCPU tương ứng và khả năng truyền dữ liệu tới storage.
- Indexing capacity và search capacity được cấp phát, theo dõi riêng.
- Dịch vụ tăng OCU khi workload tăng và scale down khi workload giảm, trong phạm vi min/max đã cấu hình.
- Mức capacity tối đa là một giới hạn bảo vệ ngân sách; nếu đặt quá thấp, workload có thể bị giới hạn khi tải tăng.
- Storage trên managed storage được tính riêng với OCU-hours.

Serverless tự quản lý shard và index lifecycle. Người dùng không trực tiếp chọn data node, shard count hoặc replica topology như domain provisioned.

## 3. Ba collection type và cách chọn

Collection type được chọn khi tạo collection và không thể đổi type sau khi tạo. Hãy quyết định dựa trên dạng dữ liệu, cách truy vấn và yêu cầu cập nhật.

| Collection type | Dữ liệu và truy vấn | Workload phù hợp |
|---|---|---|
| Search | Tài liệu có cấu trúc hoặc bán cấu trúc; full-text, filter, sort, aggregation | Tìm kiếm sản phẩm, nội dung, hồ sơ, tài liệu nội bộ |
| Time series | Log, metric, trace và dữ liệu máy phát sinh theo thời gian | Log analytics, security analytics, vận hành hệ thống, phân tích hành vi |
| Vector search | Embedding và metadata; k-NN similarity search, lọc theo metadata | Semantic search, recommendation, image/document retrieval, RAG |

Search và Vector search giữ dữ liệu trên hot storage để ưu tiên tốc độ truy vấn. Time series có thể dùng hot và warm storage: dữ liệu gần đây ở hot, dữ liệu cũ chuyển sang warm theo cấu hình của NextGen time series.

Một số khác biệt quan trọng:

- Search và Time series không hỗ trợ k-NN vector index; cần vector search collection cho vector similarity search.
- Time series collection không hỗ trợ custom document ID khi index và không hỗ trợ upsert; có thể update bằng document ID theo các API được hỗ trợ.
- Search collection phù hợp với document ID do ứng dụng kiểm soát và cập nhật/upsert thường xuyên.
- Vector search collection dùng mapping kiểu knn_vector và có giới hạn, hành vi riêng theo generation.
- Không chọn collection type chỉ theo tên dữ liệu. Ví dụ log có thể chứa embedding, nhưng nếu workload chính là truy vấn log theo thời gian thì Time series phù hợp hơn; nếu cần semantic similarity thì phải thiết kế Vector search riêng.

## 4. Search collection: full-text và ứng dụng tìm kiếm

Search collection phù hợp khi người dùng cần tìm tài liệu theo từ khóa, cụm từ, trường dữ liệu hoặc bộ lọc nghiệp vụ. OpenSearch cung cấp analyzer, inverted index, relevance scoring, aggregations, sorting và query DSL.

Ví dụ website bán hàng cần tìm theo tên sản phẩm, lọc theo category và khoảng giá:

~~~json
{
  "mappings": {
    "properties": {
      "product_id": {"type": "keyword"},
      "name": {"type": "text"},
      "category": {"type": "keyword"},
      "price": {"type": "float"},
      "available": {"type": "boolean"},
      "updated_at": {"type": "date"}
    }
  }
}
~~~

Tạo index:

~~~http
PUT products
{
  "mappings": {
    "properties": {
      "product_id": {"type": "keyword"},
      "name": {"type": "text"},
      "category": {"type": "keyword"},
      "price": {"type": "float"},
      "available": {"type": "boolean"},
      "updated_at": {"type": "date"}
    }
  }
}
~~~

Truy vấn:

~~~http
POST products/_search
{
  "size": 10,
  "query": {
    "bool": {
      "must": [
        {"match": {"name": "wireless headphones"}}
      ],
      "filter": [
        {"term": {"category": "audio"}},
        {"term": {"available": true}},
        {"range": {"price": {"lte": 300}}}
      ]
    }
  },
  "sort": [
    {"updated_at": {"order": "desc"}}
  ]
}
~~~

Đặt trường dùng để filter, sort và join ở dạng keyword, numeric, date hoặc boolean phù hợp. Trường text dành cho full-text analysis; nếu vừa cần full-text vừa cần exact filter, có thể dùng multi-fields. Mapping phải phù hợp với query pattern vì thay đổi type của field đã được index thường yêu cầu tạo index mới và reindex.

## 5. Time series collection: log và dữ liệu vận hành

Time series collection dành cho dữ liệu máy phát sinh liên tục, thường có timestamp và metadata như service, host, environment, severity, trace ID hoặc tenant. Các truy vấn thường lọc theo thời gian, nhóm theo service/level và tính thống kê.

Ví dụ log document:

~~~json
{
  "@timestamp": "2026-11-20T06:30:00Z",
  "service": "checkout",
  "environment": "production",
  "level": "ERROR",
  "trace_id": "trace-8f21",
  "message": "Payment provider timeout",
  "duration_ms": 4200
}
~~~

Index time series nên có timestamp field rõ ràng và mapping cho các trường thường dùng trong filter/aggregation. Tránh tạo mapping động không kiểm soát làm phát sinh quá nhiều field.

### 5.1. Hot và warm storage trong NextGen

NextGen Time series collections hỗ trợ warm-after. Thiết lập index.warm.after chỉ định khoảng thời gian dữ liệu trong index ở hot storage trước khi OpenSearch Serverless chuyển dữ liệu cũ sang warm storage.

~~~http
PUT application-logs-2026.11
{
  "settings": {
    "index": {
      "warm": {
        "after": "7d"
      }
    }
  },
  "mappings": {
    "properties": {
      "@timestamp": {"type": "date"},
      "service": {"type": "keyword"},
      "level": {"type": "keyword"},
      "message": {"type": "text"}
    }
  }
}
~~~

Các điểm cần nhớ:

- warm-after chỉ áp dụng cho NextGen Time series collections, không áp dụng cho Search, Vector search hoặc Classic collections.
- Nếu không cấu hình, mặc định là 1 ngày; giá trị tối thiểu là 24 giờ.
- Giá trị có dạng số nguyên kèm d hoặc h, ví dụ 7d hoặc 36h.
- Nếu index có data retention, warm-after không được dài hơn thời hạn retention.
- Dữ liệu được chuyển theo thứ tự ingest và underlying storage; thời gian warm không nhất thiết được tính từ timestamp trong từng document.
- Sau khi dữ liệu vào warm storage, truy vấn vẫn dùng cùng index API nhưng có thể có đặc tính latency khác hot data.

Chọn warm-after theo cửa sổ truy vấn thường xuyên. Nếu dashboard chủ yếu truy vấn 7 ngày gần nhất, có thể giữ cửa sổ đó ở hot và chuyển dữ liệu cũ sang warm. Kiểm thử latency của các truy vấn lịch sử trước khi đặt SLA.

## 6. Vector search: semantic retrieval và RAG

Vector search lưu embedding dưới dạng vector số. Mô hình embedding chuyển văn bản, hình ảnh hoặc nội dung khác thành vector nhiều chiều; OpenSearch tìm các vector gần với query vector theo metric đã chọn.

Các metric similarity thường gặp:

- Cosine similarity: so sánh hướng của vector; thường phù hợp embedding văn bản đã chuẩn hóa.
- Euclidean distance (L2): đo khoảng cách hình học giữa vector.
- Dot product: tích vô hướng, thường dùng khi mô hình embedding được huấn luyện cho metric này.

Một vector index có thể lưu embedding cùng metadata như document ID, title, category, tenant, timestamp và ACL reference. Nhờ vậy, ứng dụng có thể tìm theo ngữ nghĩa rồi lọc theo quyền truy cập, loại tài liệu hoặc thuộc tính nghiệp vụ.

Ví dụ tạo vector index:

~~~http
PUT knowledge-vectors
{
  "settings": {
    "index.knn": true
  },
  "mappings": {
    "properties": {
      "embedding": {
        "type": "knn_vector",
        "dimension": 3,
        "space_type": "cosinesimil"
      },
      "document_id": {"type": "keyword"},
      "title": {"type": "text"},
      "tenant_id": {"type": "keyword"},
      "category": {"type": "keyword"}
    }
  }
}
~~~

Dimension trong ví dụ là 3 để minh họa; production phải khớp chính xác kích thước vector do model embedding tạo ra. Không thể index vector có dimension khác mapping.

Truy vấn k-NN:

~~~http
POST knowledge-vectors/_search
{
  "size": 5,
  "query": {
    "knn": {
      "embedding": {
        "vector": [0.12, 0.34, 0.56],
        "k": 5,
        "filter": {
          "term": {"tenant_id": "tenant-42"}
        }
      }
    }
  },
  "_source": ["document_id", "title", "tenant_id", "category"]
}
~~~

Kết quả vector search thường là bước retrieval trong RAG:

1. Chia tài liệu thành chunk có kích thước phù hợp.
2. Tạo embedding cho mỗi chunk bằng Amazon Bedrock hoặc model embedding khác.
3. Index vector và metadata vào Vector search collection.
4. Tạo embedding cho câu hỏi của người dùng.
5. Tìm top-k chunk gần nhất, áp dụng metadata/authorization filters.
6. Đưa context đã truy xuất vào prompt của foundation model.
7. Trả lời kèm nguồn hoặc reference để người dùng kiểm chứng.

OpenSearch Serverless hỗ trợ vector dimensions tới 16.000. Với NextGen vector collections, 32x compression được bật mặc định; có thể chọn compression level được hỗ trợ như 1x, 2x, 8x, 16x hoặc 32x. Compression giảm memory/storage footprint nhưng có thể ảnh hưởng recall; hãy đo chất lượng retrieval trên tập query đại diện trước khi chọn.

NextGen vector collections có GPU acceleration mặc định cho quá trình build index lớn và read-after-write refresh interval khoảng 5 giây. Classic vector collections có hành vi khác, bao gồm refresh interval khoảng 60 giây và giới hạn thuật toán HNSW với Faiss. Khi đọc tài liệu hoặc migration collection cũ, phải xác định generation trước khi áp dụng giới hạn.

## 7. NextGen và Classic: hai generation cần phân biệt

OpenSearch Serverless hiện có hai generation:

| Đặc điểm | NextGen | Classic |
|---|---|---|
| Trạng thái | Generation mới, là lựa chọn mặc định trong flow tạo collection hiện hành | Generation trước, vẫn có collection đang vận hành |
| Capacity management | Collection groups, chia sẻ OCU giữa collections cùng type | Capacity settings kiểu account-level/collection group Classic |
| Scale to zero | Collection group có thể đặt minimum indexing/search OCU bằng 0 | Classic collection group không hỗ trợ min OCU bằng 0 |
| Tạo collection | Express Create hoặc Standard Create | Wizard nhiều bước |
| Time series warm-after | Có | Không |
| Vector indexing | 32x compression mặc định, GPU index-build acceleration, refresh khoảng 5 giây | API và engine/algorithm constraints riêng; Classic không hỗ trợ Lucene ANN, IVF hoặc IVFQ theo tài liệu hiện hành; refresh khoảng 60 giây |

NextGen Express Create tự tạo collection group và các security policies cần thiết theo defaults. Standard Create cho phép kiểm soát collection group, KMS key, network policy và data access policy. Express Create mặc định có thể tạo network access công khai và cấp quyền data access rộng cho IAM principal hiện tại; phải xem lại các giá trị này trước khi dùng production.

Classic collections không tự chuyển generation. Nếu cần dùng tính năng NextGen, hãy thiết kế collection mới, reindex dữ liệu và chuyển ứng dụng theo quy trình migration.

## 8. Collection groups và chia sẻ capacity

Collection group là tài nguyên nhóm một hoặc nhiều collections và đặt giới hạn capacity chung. Collections trong cùng group chia sẻ compute OCUs; mỗi collection vẫn giữ encryption key và data access policy riêng.

Collection group giúp:

- Gộp các workload cùng loại để tận dụng compute capacity.
- Đặt min/max indexing OCU và search OCU ở một nơi.
- Giới hạn mức tiêu thụ tài nguyên theo nhóm.
- Chia nhóm theo môi trường, ứng dụng hoặc yêu cầu bảo mật.

Một collection group chỉ chứa một loại collection: Search, Time series hoặc Vector search. Không đưa ba loại workload vào cùng group. Collections có thể dùng KMS keys khác nhau trong cùng group; việc chia sẻ compute không làm mất encryption hoặc access isolation ở cấp collection.

Với NextGen, có thể đặt min indexing OCU và min search OCU bằng 0 để scale-to-zero khi idle. Điều này giúp giảm compute charges cho workload không liên tục, nhưng request đầu sau idle có thể có độ trễ khởi động/scale. Nếu workload cần latency ổn định, đặt minimum capacity lớn hơn 0 và đo chi phí duy trì capacity đó.

Maximum OCU là giới hạn scale và công cụ bảo vệ ngân sách. Nếu đặt quá thấp, capacity không thể tăng đủ khi ingest/search burst. Hãy đặt max dựa trên load test, SLA và budget, sau đó cảnh báo khi metric OCU tiến gần giới hạn.

## 9. Chọn OpenSearch Serverless hay provisioned domain?

OpenSearch Serverless và provisioned OpenSearch Service domain dùng cùng hệ sinh thái OpenSearch nhưng khác cách quản lý hạ tầng và mức kiểm soát.

| Tiêu chí | Serverless | Provisioned domain |
|---|---|---|
| Capacity | Tự scale theo OCU; có min/max | Người vận hành chọn instance, node và storage |
| Shard/index lifecycle | Dịch vụ tự quản lý nhiều quyết định hạ tầng | Kiểm soát chi tiết hơn |
| Ingest/search scaling | Compute indexing và search tách biệt | Phụ thuộc cluster topology và sizing |
| Plugin/API | Chỉ subset được hỗ trợ | Tập tính năng khác và có thể rộng hơn tùy version |
| Version/software updates | Dịch vụ tự nâng cấp | Người vận hành lên kế hoạch nâng cấp |
| Cost model | OCU-hours và managed storage | Instance-hours, storage và data transfer |
| Workload phù hợp | Biến động, intermittent, khó dự báo, ít vận hành cluster | Tải ổn định, cần kiểm soát node/shard/plugin/API và tối ưu chuyên sâu |

Ưu tiên Serverless khi:

- Không muốn vận hành cluster và capacity.
- Traffic ingest và query biến động hoặc có thời gian idle.
- Có thể dùng collection type và API subset được hỗ trợ.
- Muốn scale indexing và search độc lập.
- Muốn dùng managed vector search mà không quản lý vector database nodes.

Ưu tiên provisioned domain khi:

- Cần plugin, API hoặc tính năng không được Serverless hỗ trợ.
- Muốn kiểm soát shard, node topology, instance family, JVM và cấu hình cluster sâu.
- Có tải ổn định lớn, dễ dự báo và có thể tối ưu chi phí bằng sizing/Reserved Instance hoặc Database Savings Plans.
- Có yêu cầu cross-Region, cross-account hoặc vận hành đặc thù cần kiến trúc domain.
- Cần kiểm soát lịch nâng cấp và compatibility theo cách riêng.

Không quyết định chỉ dựa trên từ khóa serverless. Hãy lập bảng yêu cầu API/plugin, throughput, latency, data size, availability, security, retention và cost trước khi chọn.

### 9.1. Khi nào nên dùng dịch vụ khác?

Không phải mọi dữ liệu cần được index vào OpenSearch:

| Nhu cầu | Dịch vụ nên đánh giá | Vì sao |
|---|---|---|
| Tìm kiếm tương tác, full-text, filter và relevance ranking | OpenSearch Serverless hoặc provisioned domain | Được thiết kế cho search API có latency thấp |
| Điều tra nhanh log đang nằm trong Amazon CloudWatch Logs | CloudWatch Logs Insights | Truy vấn trực tiếp log group, không cần duy trì index riêng |
| SQL ad hoc trên dữ liệu đã lưu trong S3/data lake | Amazon Athena | Truy vấn theo nhu cầu mà không cần ingest bản sao vào search index |
| Dashboard log/metric vận hành theo thời gian thực | OpenSearch Time series hoặc dịch vụ observability phù hợp | Cần index và truy vấn lặp lại với filter/aggregation tương tác |

Nếu người dùng chỉ chạy truy vấn SQL thỉnh thoảng trên dữ liệu gốc trong S3, Athena có thể đơn giản và tiết kiệm hơn việc duy trì search index. Nếu cần autocomplete, relevance, semantic retrieval hoặc query tương tác liên tục, OpenSearch có thể phù hợp hơn.

## 10. Ingest dữ liệu: chọn pipeline phù hợp

OpenSearch Serverless hỗ trợ nhiều cách nạp dữ liệu:

| Nguồn/producer | Đường ingest thường dùng | Khi phù hợp |
|---|---|---|
| Ứng dụng web/backend | OpenSearch client trực tiếp qua HTTPS và SigV4 | Search document hoặc transactional indexing |
| Log/metric/trace | OpenSearch Ingestion hoặc Fluent Bit | Streaming observability data |
| Amazon Data Firehose | Firehose delivery destination | Managed buffering, retry và delivery |
| Kinesis Data Streams | Consumer/Lambda hoặc OpenSearch Ingestion theo pipeline hỗ trợ | Event streaming và near-real-time indexing |
| Amazon S3 | Batch pipeline, Lambda hoặc OpenSearch Ingestion theo nguồn hỗ trợ | Backfill, data lake export |
| DynamoDB | DynamoDB Streams + Lambda hoặc pipeline phù hợp | Đồng bộ thay đổi record |
| Amazon Bedrock | Private service access hoặc tích hợp retrieval được hỗ trợ | RAG và knowledge retrieval |

Amazon OpenSearch Ingestion là data collector serverless dựa trên Data Prepper. Nó có thể lọc, enrich, transform, normalize và aggregate trước khi ghi vào collection. Data Firehose cũng hỗ trợ OpenSearch Serverless làm destination; role của Firehose cần quyền WriteDocument trong data access policy và index đích phải tồn tại.

Với Fluent Bit, cấu hình output cần dùng AWS service name là aoss khi ký request. Với ứng dụng dùng AWS SDK/OpenSearch client, request phải ký SigV4 với service name aoss (khác es của provisioned domain), dùng TLS và credentials tạm thời từ IAM role khi có thể. Với client tự ký request, kiểm tra yêu cầu x-amz-content-sha256 và khả năng tương thích của phiên bản client với OpenSearch Serverless.

## 11. Ingest pipeline và chuẩn hóa document

OpenSearch ingest pipeline là chuỗi processor chạy trước khi document được index. Có thể dùng để parse timestamp, đổi tên field, chuẩn hóa giá trị, loại bỏ dữ liệu nhạy cảm hoặc tạo embedding trong các trường hợp tích hợp được hỗ trợ.

Ví dụ pipeline đơn giản chuẩn hóa timestamp và bỏ field không cần thiết:

~~~http
PUT _ingest/pipeline/normalize-logs
{
  "description": "Normalize application log documents",
  "processors": [
    {
      "set": {
        "field": "ingest_source",
        "value": "application"
      }
    },
    {
      "remove": {
        "field": "debug_payload",
        "ignore_missing": true
      }
    }
  ]
}
~~~

Gửi document qua pipeline:

~~~http
POST application-logs/_doc?pipeline=normalize-logs
{
  "@timestamp": "2026-11-20T06:30:00Z",
  "service": "checkout",
  "level": "INFO",
  "message": "Order accepted"
}
~~~

Pipeline giúp mọi producer áp dụng cùng logic chuẩn hóa, nhưng không thay thế data quality ở upstream. Hãy validate schema, event time, required fields và dữ liệu nhạy cảm trước khi index.

## 12. Security model: IAM, encryption, network và data access

OpenSearch Serverless có security model khác provisioned domain. Một collection cần được bảo vệ bởi ba nhóm policy:

1. Encryption policy xác định KMS key dùng để mã hóa collection.
2. Network policy xác định endpoint công khai hay private và nguồn mạng nào được phép truy cập.
3. Data access policy xác định principal nào được phép thực hiện OpenSearch operations trên collection/index.

Ngoài ra, IAM identity policy kiểm soát quyền gọi các OpenSearch Serverless control-plane/API operations. IAM và data access policy là hai lớp khác nhau; cấp quyền ở một lớp không tự động cấp quyền ở lớp còn lại.

~~~mermaid
flowchart TD
    U[IAM role or SAML identity] --> IAM[IAM identity policy]
    IAM --> API[OpenSearch Serverless API access]
    U --> DAP[Data access policy]
    NET[Network policy: public or VPC endpoint] --> C[Collection endpoint]
    ENC[Encryption policy: AWS owned or KMS CMK] --> C
    API --> C
    DAP --> C
    C --> IDX[Indexes and documents]
~~~

Để truy cập collection endpoint, principal thường cần IAM permission aoss:APIAccessAll. Nếu truy cập Dashboards, cần thêm aoss:DashboardsAccessAll. Data access policy tiếp tục cấp quyền cụ thể như CreateIndex, WriteDocument, ReadDocument hoặc UpdateIndex. Nếu thiếu một lớp, request có thể nhận HTTP 403 dù các policy khác đã cho phép.

### 12.1. Encryption policy

Encryption at rest luôn bật cho collection. Người dùng chọn AWS owned key hoặc customer managed KMS key; không thể tắt mã hóa. Encryption policy có thể áp dụng cho một collection hoặc pattern nhiều collection.

Nếu dùng customer managed key, key policy/grant phải cho phép OpenSearch Serverless sử dụng key. Không disable hoặc schedule deletion key khi collection còn phụ thuộc vào key đó; dịch vụ có thể không truy cập được dữ liệu và trả KMSKeyInaccessibleException.

Encryption in transit dùng TLS 1.2. Client cần gọi endpoint bằng HTTPS và ký request theo yêu cầu.

### 12.2. Network policy

Network policy có thể cho phép public access hoặc private access qua OpenSearch Serverless-managed VPC endpoint. Có thể cấu hình riêng cho collection endpoint và OpenSearch Dashboards endpoint.

Private endpoint giúp ứng dụng trong VPC truy cập collection mà không cần public internet path. Khi tạo policy có VPC endpoint, phải tạo OpenSearch Serverless-managed VPC endpoint trước và đưa endpoint ID vào policy. AWS service private access như Amazon Bedrock chỉ áp dụng cho collection endpoint, không áp dụng cho Dashboards endpoint.

Ví dụ network policy private:

~~~json
[
  {
    "Description": "Private access for product search",
    "Rules": [
      {
        "ResourceType": "collection",
        "Resource": ["collection/product-search"]
      },
      {
        "ResourceType": "dashboard",
        "Resource": ["collection/product-search"]
      }
    ],
    "AllowFromPublic": false,
    "SourceVPCEs": ["vpce-0123456789abcdef0"]
  }
]
~~~

Đây là cấu hình minh họa; thay VPC endpoint ID bằng endpoint thực tế. Kiểm tra policy precedence khi nhiều network policy cùng khớp một collection.

### 12.3. Data access policy

Data access policy gắn principal với quyền ở cấp collection hoặc index. Ví dụ role ứng dụng được tạo index và ghi/đọc documents trong index products:

~~~json
[
  {
    "Rules": [
      {
        "ResourceType": "collection",
        "Resource": ["collection/product-search"],
        "Permission": ["aoss:DescribeCollectionItems"]
      },
      {
        "ResourceType": "index",
        "Resource": ["index/product-search/products*"],
        "Permission": [
          "aoss:CreateIndex",
          "aoss:UpdateIndex",
          "aoss:DescribeIndex",
          "aoss:ReadDocument",
          "aoss:WriteDocument"
        ]
      }
    ],
    "Principal": [
      "arn:aws:iam::111122223333:role/ProductSearchAppRole"
    ]
  }
]
~~~

Tách role ingest và role query nếu workload có yêu cầu phân quyền khác nhau. Producer chỉ cần WriteDocument và quyền index phù hợp; consumer tìm kiếm chỉ cần ReadDocument. Tránh dùng aoss:* cho mọi principal trong production.

Các data access policies có tính cộng dồn: nhiều policy cùng khớp một principal/resource sẽ cộng quyền; một policy hẹp hơn không ghi đè quyền rộng đã được cấp bởi policy khác. Data access policy không cung cấp explicit deny. Khi thu hẹp quyền, phải rà soát tất cả policy có wildcard hoặc pattern trùng với collection/index đó.

## 13. Tạo collection và triển khai theo môi trường

Quy trình tạo collection an toàn:

1. Chọn Region được OpenSearch Serverless hỗ trợ và đáp ứng yêu cầu data residency.
2. Xác định workload là Search, Time series hay Vector search.
3. Chọn NextGen hoặc giữ Classic nếu cần tương thích với collection hiện có.
4. Với NextGen, chọn collection group phù hợp và đặt min/max indexing/search OCU.
5. Tạo encryption policy với AWS owned key hoặc customer managed key.
6. Tạo network policy public/private theo đường truy cập thực tế.
7. Tạo data access policy cho IAM roles hoặc SAML identities.
8. Tạo collection và đợi trạng thái Active.
9. Tạo index mapping, ingest pipeline và index template nếu cần.
10. Kiểm tra request signing, query, latency và metrics bằng role ứng dụng.

Express Create giúp tạo nhanh collection và các policy mặc định. Tuy nhiên, mặc định có thể mở public network và cấp quyền rộng cho principal tạo collection. Dùng Express Create cho sandbox sau khi hiểu defaults; với production nên dùng Standard Create hoặc review tất cả policy trước khi gửi dữ liệu thật.

Tên collection phải duy nhất trong account/Region, dài từ 3 đến 64 ký tự và chỉ dùng chữ thường a-z, chữ số, dấu gạch ngang hoặc gạch dưới. Nên đặt tên theo domain, workload và môi trường, ví dụ product-search-prod hoặc app-logs-staging. Không đưa tên khách hàng hay dữ liệu nhạy cảm vào resource name.

## 14. Capacity planning, OCU và scale-to-zero

OCU được tính riêng cho indexing và search. Hãy dự báo hai luồng tải độc lập:

- Indexing: document/second, bytes/second, bulk size, update rate, vector dimension và ingest transformation.
- Search: query/second, concurrency, query complexity, aggregation, vector k và latency target.

Với NextGen collection group, có thể đặt min/max cho cả hai:

~~~json
{
  "minIndexingCapacityInOCU": 0,
  "maxIndexingCapacityInOCU": 16,
  "minSearchCapacityInOCU": 0,
  "maxSearchCapacityInOCU": 16
}
~~~

Đây là ví dụ giới hạn cho một nhóm workload nhỏ, không phải cấu hình mặc định hay cam kết capacity. Chạy load test để xác định mức phù hợp.

Scale-to-zero hữu ích khi collection idle trong thời gian dài, nhưng cần cân nhắc cold-start/scale-up latency. Nếu ứng dụng có traffic 24/7 và SLA nghiêm ngặt, giữ minimum OCU lớn hơn 0 có thể tạo latency ổn định hơn. Nếu workload có burst lớn, max OCU cần đủ cao để hấp thụ peak.

Đặt max quá thấp có thể làm tăng throttling hoặc latency khi vượt capacity. Đặt max quá cao không trực tiếp làm dịch vụ tiêu thụ toàn bộ capacity ngay lập tức, nhưng làm mất một phần rào chắn ngân sách. Hãy dùng CloudWatch alarms cho SearchOCU và IndexingOCU.

## 15. Tối ưu index, query và vector retrieval

### Search

- Chọn mapping đúng cho text, keyword, numeric, date và geo fields.
- Dùng filter context cho điều kiện lọc không cần relevance scoring.
- Chỉ trả về source fields cần thiết để giảm payload.
- Tránh wildcard query trên field cardinality cao nếu không cần.
- Dùng bulk indexing cho ingest lớn và kiểm soát batch size.
- Tạo index mới và reindex khi cần thay mapping không tương thích.

### Time series

- Đặt timestamp field rõ ràng.
- Dùng keyword cho service, host, environment và severity thường lọc.
- Giới hạn field explosion do dynamic mapping.
- Chọn warm-after theo cửa sổ truy vấn phổ biến.
- Đặt retention theo yêu cầu audit và vận hành.

### Vector search

- Dùng đúng embedding model và dimension nhất quán cho index/query.
- Chọn similarity metric khớp với model.
- Kiểm thử recall/latency khi thay đổi compression.
- Lưu metadata cần thiết để filter tenant, ACL, category và version.
- Chọn chunk size/overlap dựa trên loại tài liệu và retrieval evaluation.
- Đo recall@k, precision@k, MRR hoặc metric phù hợp với ứng dụng.
- Xóa/reindex embedding cũ khi model hoặc preprocessing thay đổi.

Không dùng vector similarity làm cơ chế authorization. Luôn áp dụng access-control filter hoặc kiểm tra quyền ở application trước khi đưa nội dung vào prompt của mô hình.

## 16. Observability và vận hành

CloudWatch metrics cho biết collection đang sử dụng bao nhiêu compute và mức tải ingest/search. Theo dõi ít nhất:

| Nhóm | Metric hoặc tín hiệu | Câu hỏi vận hành |
|---|---|---|
| Capacity | SearchOCU, IndexingOCU | Có gần max OCU hay scale quá thường xuyên? |
| Ingest | Ingestion requests, indexing errors, rejected requests | Producer có ghi được dữ liệu? Có mapping error? |
| Search | Search request rate, latency, rejected requests | Query có đáp ứng SLA? |
| Storage | Managed storage usage | Tăng trưởng dữ liệu có vượt ngân sách? |
| Security | 403, KMS errors, network connection failures | Principal, key hoặc VPC policy có sai? |
| Pipeline | OpenSearch Ingestion pipeline health, DLQ/error logs | Dữ liệu có bị backlog hoặc drop? |

Tạo dashboard theo collection/workload và alarm cho:

- SearchOCU hoặc IndexingOCU tiến gần maximum capacity.
- Search/indexing rejection tăng.
- P95/P99 query latency vượt SLA.
- Storage tăng nhanh hơn forecast.
- Ingestion pipeline lỗi hoặc backlog tăng.
- KMSKeyInaccessibleException hoặc request 403 tăng bất thường.

Log request nên có correlation ID, index, query class và latency; tránh log toàn bộ document hoặc thông tin cá nhân nếu không cần. Với vector search/RAG, theo dõi retrieval quality và số chunk được truy xuất, không chỉ latency API.

## 17. Backup, migration và giới hạn cần kiểm tra

OpenSearch Serverless hỗ trợ automated snapshots, nhưng không hỗ trợ manual snapshots theo cách domain provisioned có thể cung cấp. Không giả định có thể tạo snapshot thủ công trước mọi thay đổi. Thiết kế backup/recovery cần đối chiếu khả năng snapshot tự động, retention, export/reindex và nguồn dữ liệu gốc ở S3 hoặc hệ thống upstream.

Một số giới hạn quan trọng:

- Không phải mọi OpenSearch API operation hoặc plugin đều được hỗ trợ.
- Custom OpenSearch plugins không được hỗ trợ.
- Collection không hỗ trợ resource policy cross-account trực tiếp. Người dùng ở account khác có thể assume một IAM role trong account sở hữu collection; role đó phải được khai báo trong data access policy và có IAM permissions tương ứng.
- Cross-Region search và replication không được hỗ trợ như một tính năng collection.
- Shard count, shard interval và refresh interval không được người dùng tùy chỉnh như domain provisioned.
- Search/Time series refresh interval thường khoảng 10 giây; NextGen vector khoảng 5 giây và Classic vector khoảng 60 giây theo generation.
- Một collection có giới hạn số index và các service quota khác; kiểm tra Service Quotas ở đúng Region.
- Migration từ managed domain sang Serverless cần reindex dữ liệu; không có thao tác chuyển đổi tự động tại chỗ.
- Collection type không thể thay đổi sau khi tạo.

Trước khi chọn Serverless, lập danh sách API, plugin, analyzer, ingest processor, snapshot, cross-account và cross-Region requirements. Kiểm tra supported operations theo collection type và generation. Nếu một yêu cầu bắt buộc không được hỗ trợ, chọn provisioned domain hoặc kiến trúc bổ trợ.

## 18. Chi phí và lựa chọn workload

Chi phí Serverless có các thành phần chính:

- OCU-hours cho indexing compute.
- OCU-hours cho search compute.
- Managed storage tính theo dung lượng lưu trữ.
- Các dịch vụ liên quan như OpenSearch Ingestion, Firehose, KMS customer managed key, CloudWatch logs/metrics và data transfer nếu có.

NextGen collection groups giúp nhiều collections cùng type chia sẻ OCU. Min OCU bằng 0 có thể giảm compute cost khi idle, nhưng không có nghĩa storage hoặc các dịch vụ ingest liên quan miễn phí. Classic có capacity model khác; không lấy mức tối thiểu hoặc ví dụ giá của Classic áp dụng cho NextGen.

Một cách đánh giá workload:

| Workload | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Website product search, traffic dao động | Search collection | Full-text, filter, sort và auto scaling |
| Log ứng dụng/CloudTrail với retention nhiều giai đoạn | NextGen Time series | Hot/warm và truy vấn theo thời gian |
| RAG knowledge base hoặc semantic search | Vector search collection | k-NN và metadata filtering |
| Search cluster chạy tải ổn định, cần kiểm soát shard/plugin | Provisioned domain | Sizing và tuning chi tiết |
| Search cần custom plugin hoặc API không hỗ trợ | Provisioned domain | Serverless có API/plugin subset |
| Batch ingest theo đợt và query không liên tục | NextGen Serverless, đánh giá scale-to-zero | Có thể giảm compute khi idle |

Để estimate, lấy workload thực tế trong ít nhất một chu kỳ: ingest bytes/day, document size, query/second, concurrency, p95/p99 latency, vector dimension, retention và giờ idle. Tạo benchmark nhỏ, đo OCU peak/average và storage growth, rồi dùng AWS Pricing Calculator hoặc trang pricing theo Region.

## 19. Ví dụ kiến trúc: product search và RAG

Một doanh nghiệp có hai nhu cầu: tìm kiếm sản phẩm trên website và hỏi đáp tài liệu nội bộ.

~~~mermaid
flowchart TD
    subgraph ProductSearch
        A[Product catalog DB] --> B[CDC or application event]
        B --> C[Ingestion pipeline]
        C --> D[Search collection]
        U[Web application] --> D
        D --> R[Product results]
    end
    subgraph KnowledgeRAG
        S3[(S3 documents)] --> E[Chunk and embedding pipeline]
        E --> V[Vector search collection]
        Q[User question] --> M[Query embedding]
        M --> V
        V --> K[Top-k chunks and metadata filters]
        K --> L[Amazon Bedrock model]
        L --> O[Answer with sources]
    end
~~~

Product search dùng Search collection vì cần full-text match, category filter, sort theo giá và cập nhật document theo product ID. RAG dùng Vector search collection vì cần embedding similarity và metadata filter theo tenant/document permission.

Hai collection có thể thuộc các collection groups khác nhau vì collection type khác nhau. Nếu có nhiều product-search collections theo môi trường hoặc tenant, có thể nhóm những collection cùng type để chia sẻ capacity. Dù chia sẻ OCU, mỗi collection vẫn giữ policy và encryption riêng.

## 20. Checklist chọn workload và triển khai production

Trước khi tạo collection, trả lời các câu hỏi:

1. Dữ liệu là document search, time-series logs hay embedding vectors?
2. Cần full-text, aggregation, k-NN, geospatial hay hybrid retrieval?
3. Collection type có hỗ trợ API và operation cần thiết không?
4. Nên dùng NextGen hay giữ Classic vì compatibility?
5. Traffic ingest và query có biến động không?
6. Có thể scale-to-zero hay cần minimum OCU để giữ latency?
7. Có nhiều collection cùng type để chia sẻ capacity qua collection group không?
8. Dữ liệu có yêu cầu KMS customer managed key, private endpoint hoặc SAML không?
9. Role ingest và query đã được tách least privilege chưa?
10. Producer dùng OpenSearch Ingestion, Firehose, Fluent Bit, Lambda hay client trực tiếp?
11. Có chiến lược retry, dead-letter và idempotent indexing không?
12. Mapping và index template có được version control không?
13. Có load test cho ingest burst, query concurrency và vector recall không?
14. Có dashboard/alarms cho OCU, latency, rejection, storage và pipeline health không?
15. Có backup, reindex và migration runbook không?
16. Có xác minh supported Region, API/plugin và Service Quotas không?

Một lần triển khai production nên có sandbox, staging và production collection tách biệt. Dùng Infrastructure as Code để quản lý collection, collection group, encryption/network/data access policies và ingest pipelines. Thử thay đổi policy trên staging trước; policy wildcard có thể ảnh hưởng nhiều collection cùng lúc.

## Kết luận

Amazon OpenSearch Serverless cung cấp collection được quản lý với compute indexing và search tách biệt, tự scale theo workload và storage được quản lý. Ba collection type phục vụ ba nhu cầu khác nhau: Search cho full-text, Time series cho log/metric theo thời gian và Vector search cho semantic retrieval. Collection type không thể đổi sau khi tạo, nên cần chọn dựa trên dữ liệu, query và API requirements.

NextGen collection groups cho phép nhiều collections cùng type chia sẻ OCU, đặt min/max capacity và scale-to-zero khi phù hợp. Classic vẫn tồn tại với capacity và tính năng riêng. Serverless giảm công việc vận hành nhưng vẫn cần thiết kế mapping, ingest, capacity, security, observability và cost guardrails.

Hãy chọn Serverless khi muốn giảm quản lý hạ tầng và workload phù hợp với collection type/API được hỗ trợ. Chọn provisioned domain khi cần kiểm soát cluster sâu, plugin/API đặc thù hoặc yêu cầu vận hành mà Serverless chưa đáp ứng. Quyết định cuối cùng nên dựa trên benchmark dữ liệu thực, kiểm tra giới hạn dịch vụ và tổng chi phí của toàn pipeline.

## Tài liệu tham khảo

- [Amazon OpenSearch Serverless overview](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless.html)
- [What is Amazon OpenSearch Serverless?](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-overview.html)
- [Choosing a collection type](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-overview.html)
- [Creating collections: NextGen and Classic](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-create.html)
- [Amazon OpenSearch Serverless collection groups](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-collection-groups.html)
- [Managing capacity limits](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-scaling.html)
- [Collection group capacity limits](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/collection-groups-capacity-limits.html)
- [Working with vector search collections](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-vector-search.html)
- [Using warm-after in time series collections](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-warm-after.html)
- [Security overview for OpenSearch Serverless](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-security.html)
- [Encryption in OpenSearch Serverless](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-encryption.html)
- [Network access for OpenSearch Serverless](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-network.html)
- [Data access control for OpenSearch Serverless](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-data-access.html)
- [Ingesting data into OpenSearch Serverless collections](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-clients.html)
- [Overview of Amazon OpenSearch Ingestion](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/ingestion.html)
- [Comparing provisioned and Serverless OpenSearch](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-comparison.html)
- [OpenSearch Serverless quotas and endpoints](https://docs.aws.amazon.com/general/latest/gr/opensearch-service.html)
- [Amazon OpenSearch Service pricing](https://aws.amazon.com/opensearch-service/pricing/)

