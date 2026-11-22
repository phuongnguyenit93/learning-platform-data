# Phân biệt Elasticsearch với OpenSearch và phạm vi tương thích

Elasticsearch và OpenSearch có nhiều điểm giống nhau vì OpenSearch bắt đầu từ một nhánh mã nguồn của Elasticsearch. Cả hai đều là search engine phân tán, dùng Lucene, lưu document dạng JSON và cung cấp REST API với Query DSL quen thuộc. Vì vậy, một truy vấn đơn giản hoặc một request HTTP có thể trông gần như giống nhau trên hai hệ thống.

Tuy nhiên, **Elasticsearch và OpenSearch hiện là hai sản phẩm phát triển độc lập**. API, client, plugin, bảo mật, công cụ vận hành và nhịp phát hành đã dần khác nhau. Một ứng dụng dùng Spring Data Elasticsearch có thể kết nối tới một OpenSearch cluster trong một số cấu hình hoặc phiên bản nhất định, nhưng điều đó không chứng minh toàn bộ tính năng được hỗ trợ hoặc tương thích lâu dài.

Khi đánh giá khả năng tương thích, cần xác định rõ đang nói về tương thích ở lớp nào: giao thức HTTP, REST endpoint, Query DSL, mapping, Java client, Spring Data abstraction, plugin, snapshot hay quy trình vận hành. Không nên dùng một câu chung như “tương thích Elasticsearch” để thay thế ma trận phiên bản và kiểm thử thực tế.

## 1. Elasticsearch và OpenSearch là gì?

**Elasticsearch** là search engine và analytics engine phân tán được phát triển bởi Elastic. Nó thường được dùng để lập chỉ mục, tìm kiếm toàn văn, lọc, tổng hợp dữ liệu, quan sát log và xây dựng các chức năng search trong ứng dụng.

**OpenSearch** là một dự án mã nguồn mở được hình thành từ nhánh Elasticsearch 7.10.2 và Kibana 7.10.2. Dự án được công bố sau khi Elastic thay đổi mô hình cấp phép cho các phiên bản Elasticsearch mới hơn. OpenSearch tiếp tục phát triển độc lập, cùng với OpenSearch Dashboards và hệ sinh thái plugin riêng.

Cả hai có chung nền tảng lịch sử và nhiều khái niệm:

- Cluster, node, shard và replica.
- Index và document.
- Mapping và field type.
- Inverted index và Lucene.
- REST API sử dụng JSON.
- Query DSL với match, term, bool, range và các truy vấn khác.
- Aggregation để tính thống kê.
- Bulk API để ghi nhiều document.
- Snapshot và cơ chế quản lý index ở các hình thức tương ứng.

Sự tương đồng này giúp việc chuyển đổi một số use case cơ bản dễ hơn. Nó không đồng nghĩa hai sản phẩm có cùng mã nguồn hiện tại, cùng lịch phát hành hoặc cùng hợp đồng API.

## 2. Nguồn gốc và điểm tách nhánh

OpenSearch được tạo từ mã nguồn Elasticsearch 7.10.2 và Kibana 7.10.2. Đây là mốc lịch sử quan trọng khi đọc tài liệu tương thích.

~~~text
Elasticsearch / Kibana
        |
        | 7.10.2
        |
        +----------------------+
        |                      |
        v                      v
Elasticsearch tiếp tục     OpenSearch bắt đầu
phát triển bởi Elastic     từ nhánh 7.10.2
        |                      |
        v                      v
API, features, release     API, features, release
và licensing riêng        và governance riêng
~~~

Ở thời điểm tách nhánh, nhiều API và khái niệm gần như giống nhau. Qua các phiên bản tiếp theo, hai nhóm phát triển đã bổ sung tính năng, sửa lỗi và thay đổi nội bộ theo các hướng khác nhau.

Vì vậy, một ví dụ cũ chạy được trên Elasticsearch 7.10.2 có thể cần ít thay đổi khi chạy trên OpenSearch 1.x, nhưng không thể lấy điều đó để kết luận một ứng dụng hiện đại dùng Elasticsearch mới nhất sẽ chạy nguyên trạng trên OpenSearch mới nhất.

## 3. Khác biệt về giấy phép và governance

Một lý do quan trọng dẫn tới sự ra đời của OpenSearch là khác biệt về mô hình cấp phép.

- Các phiên bản Elasticsearch trước 7.11 được phát hành theo Apache License 2.0.
- Từ Elasticsearch 7.11, Elastic thay đổi giấy phép cho một số phần của distribution và mã nguồn, sử dụng Elastic License 2.0 và SSPL theo mô hình áp dụng của từng thành phần/phiên bản.
- OpenSearch được phát hành theo Apache License 2.0.

Không nên chỉ nhìn tên sản phẩm để kết luận toàn bộ thành phần, plugin hoặc dịch vụ đi kèm có cùng giấy phép. Cần kiểm tra license của đúng phiên bản và đúng artifact mà tổ chức định sử dụng.

Về governance:

- Elasticsearch do Elastic phát triển và phát hành.
- OpenSearch là dự án mã nguồn mở do cộng đồng và các tổ chức tham gia phát triển dưới governance của dự án OpenSearch.
- Các dịch vụ managed, support contract và distribution thương mại có điều khoản riêng.

Với dự án doanh nghiệp, license, support, security patch policy và khả năng nhận hỗ trợ là một phần của quyết định kiến trúc, không chỉ là chi tiết pháp lý sau khi code đã hoàn thành.

## 4. Điểm giống nhau ở kiến trúc và mô hình dữ liệu

Cả hai hệ thống đều tổ chức dữ liệu theo index và document JSON. Ứng dụng thường gửi request HTTP đến cluster, sau đó cluster phân phối công việc qua shard.

| Khái niệm | Elasticsearch | OpenSearch |
|---|---|---|
| Cluster | Có | Có |
| Node roles | Có | Có |
| Index | Có | Có |
| Primary/replica shard | Có | Có |
| Document JSON | Có | Có |
| Mapping | Có | Có |
| Analyzer/tokenizer | Có | Có |
| Query DSL | Có | Có |
| Aggregation | Có | Có |
| Bulk indexing | Có | Có |
| Snapshot/restore | Có | Có |
| REST API | Có | Có |

Tên khái niệm giống nhau nhưng chi tiết implementation và các option có thể khác theo phiên bản. Ví dụ, cùng có index template không có nghĩa toàn bộ template API, component template, lifecycle integration hoặc defaults giống nhau.

## 5. Khác biệt về REST API và Query DSL

Nhiều REST endpoint cơ bản có cấu trúc tương tự:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
~~~

Các truy vấn đơn giản như match, term, bool, range, sort, from/size, aggregation và bulk thường có mức tương đồng cao. Tuy nhiên, các tính năng mới và các tham số ít phổ biến có thể khác:

- Tên endpoint hoặc request parameter.
- Cấu trúc response và error body.
- Query option mới được thêm ở một sản phẩm.
- Hành vi mặc định của scoring hoặc sort.
- Field type và mapping option.
- Plugin query hoặc aggregation.
- Search pipeline và ingest processor.
- Vector, semantic hoặc hybrid search.
- Security API và authorization behavior.

Không nên kiểm tra tương thích bằng một request match đơn giản. Cần lấy đúng tập API mà ứng dụng sử dụng và chạy integration test trên cả hai server nếu muốn hỗ trợ cả hai.

## 6. Tương thích cú pháp không đồng nghĩa tương thích ngữ nghĩa

Hai server có thể chấp nhận cùng một JSON request nhưng trả kết quả khác nhau do analyzer, mapping, scoring, default setting hoặc implementation khác nhau.

Ví dụ:

- Analyzer dùng synonym hoặc tokenizer plugin có thể không giống nhau.
- Keyword normalizer và collation behavior có thể khác.
- Query có nested field phụ thuộc mapping giống nhau.
- Terms aggregation có thể có khác biệt về option hoặc giới hạn.
- Highlight fragment có thể khác do highlighter và analyzer.
- Vector search hoặc hybrid ranking có thể dùng API riêng.
- Painless script và script context cần được kiểm tra theo từng sản phẩm.

Vì thế, test tương thích phải xác nhận cả hai điều:

1. Request được server chấp nhận.
2. Kết quả và semantics đáp ứng hợp đồng ứng dụng.

Chỉ kiểm tra HTTP 200 là chưa đủ.

## 7. Client Java của hai hệ sinh thái

Đây là một trong những ranh giới quan trọng nhất khi tích hợp Spring.

Elasticsearch có các client Java riêng, trong đó có:

- Elasticsearch Java API Client với package và artifact thuộc hệ sinh thái Elasticsearch.
- RestClient cấp thấp dùng HTTP.
- RestHighLevelClient trong các ứng dụng cũ; client này đã được thay thế bởi Java API Client trong hướng phát triển hiện đại của Elasticsearch.

OpenSearch có các client riêng, ví dụ:

- OpenSearch Java Client.
- OpenSearch REST Client.
- Các client/adapter tương thích với ứng dụng cũ trong phạm vi phiên bản được hỗ trợ.

Ví dụ dependency có tên artifact khác nhau:

~~~xml
<!-- Elasticsearch Java API Client -->
<dependency>
    <groupId>co.elastic.clients</groupId>
    <artifactId>elasticsearch-java</artifactId>
    <version>...</version>
</dependency>
~~~

~~~xml
<!-- OpenSearch Java Client -->
<dependency>
    <groupId>org.opensearch.client</groupId>
    <artifactId>opensearch-java</artifactId>
    <version>...</version>
</dependency>
~~~

Không thay một dependency bằng dependency còn lại chỉ bằng cách sửa groupId. Các class, builder, request/response type, transport, serialization và exception có thể khác nhau.

Nếu ứng dụng chỉ cần HTTP REST cơ bản, có thể tự xây client HTTP hoặc dùng low-level client tương ứng. Tuy nhiên, cách đó đồng nghĩa ứng dụng phải tự quản lý serialization, retry, timeout, authentication, TLS và API evolution.

## 8. Elasticsearch Java API Client không phải OpenSearch Java Client

Hai client có thể cung cấp những thao tác tương tự như search, index, update, delete và bulk. Nhưng package và model type không giống nhau.

~~~java
// Elasticsearch Java API Client
co.elastic.clients.elasticsearch.ElasticsearchClient
~~~

~~~java
// OpenSearch Java Client
org.opensearch.client.opensearch.OpenSearchClient
~~~

Các lớp request như SearchRequest, BulkRequest hoặc response hit được sinh từ API specification riêng của từng sản phẩm.

Do đó:

- Code import package Elasticsearch không tự biên dịch với OpenSearch client.
- Builder lambda có thể khác.
- Enum và kiểu dữ liệu có thể khác.
- Exception mapping khác.
- Cách cấu hình transport và credential provider khác.
- Phiên bản client phải tương thích với server mục tiêu.

Nếu muốn một ứng dụng hỗ trợ hai backend, hãy đặt một interface nghiệp vụ ở giữa và viết adapter riêng cho từng client thay vì rải hai loại client trong service.

## 9. Spring Data Elasticsearch hỗ trợ điều gì?

Spring Data Elasticsearch cung cấp abstraction theo mô hình Spring Data, ví dụ:

- ElasticsearchRepository.
- ReactiveElasticsearchRepository.
- ElasticsearchOperations.
- ReactiveElasticsearchOperations.
- Query và NativeQuery.
- Mapping/conversion giữa entity và document.
- Repository query derivation.
- Auditing và các integration theo phiên bản.

Spring Data Elasticsearch được phát triển để tích hợp với Elasticsearch và các client mà phiên bản Spring Data đó hỗ trợ. Mỗi release train có ma trận tương thích riêng giữa Spring Data Elasticsearch, Spring Framework, Spring Boot, Elasticsearch server và Java client.

Không thể suy ra tương thích chỉ từ việc ứng dụng đang dùng Spring Boot hoặc vì hai server có REST API gần giống nhau.

Khi nâng Spring Data Elasticsearch, cần kiểm tra bảng compatibility chính thức của đúng release train, không lấy version mới nhất của từng dependency rồi ghép tùy ý.

## 10. Spring Data Elasticsearch có thể kết nối OpenSearch không?

Câu trả lời phụ thuộc vào phiên bản, client transport, API mà ứng dụng sử dụng và cấu hình cluster. Một số ứng dụng dùng Spring Data Elasticsearch có thể kết nối tới một số phiên bản OpenSearch thông qua giao thức HTTP tương thích, đặc biệt với các API cơ bản gần nhau.

Nhưng có ba mức cần phân biệt:

1. **Kết nối được:** TCP/TLS/authentication và HTTP request hoạt động.
2. **Một số API hoạt động:** search, index hoặc bulk cơ bản được server chấp nhận.
3. **Được hỗ trợ và tương thích đầy đủ:** Spring Data abstraction, client, mapping, query, repository, aggregation, exception và các tính năng ứng dụng đều nằm trong ma trận hỗ trợ đã xác nhận.

Mức 1 hoặc 2 không tự chứng minh mức 3.

Nếu dùng Elasticsearch Java API Client với OpenSearch server, cần kiểm tra cụ thể khả năng tương thích của client/server version. Không giả định mọi request hoặc response của Java API Client sẽ hoạt động trên OpenSearch.

Nếu yêu cầu chính là OpenSearch, nên đánh giá OpenSearch Java Client và integration Spring Data dành cho OpenSearch ở đúng phiên bản. Dự án Spring Data OpenSearch trong hệ sinh thái OpenSearch là một integration riêng; cần kiểm tra release matrix, mức duy trì và tương thích với Spring Boot/Spring Framework đang dùng. Không coi nó là cùng một artifact hoặc cùng release train với Spring Data Elasticsearch.

## 11. REST compatibility mode không phải bảo đảm tương thích chéo

Một số Elasticsearch client cung cấp compatibility mode để hỗ trợ giao tiếp với một major version liền trước trong phạm vi chính sách tương thích của Elasticsearch. Cơ chế này thường liên quan tới media type/HTTP headers và cách serialize request/response.

Compatibility mode đó có phạm vi riêng:

- Không biến Elasticsearch client thành OpenSearch client.
- Không bảo đảm các endpoint chỉ có ở một sản phẩm sẽ tồn tại ở sản phẩm kia.
- Không đồng bộ mapping, plugin hoặc security feature.
- Không bảo đảm query semantics giống nhau.
- Không thay thế kiểm thử server/client matrix.

Nếu một tài liệu nói client có “compatibility mode”, hãy đọc rõ nó nói về các major version của cùng sản phẩm hay tương thích với một sản phẩm fork. Hai khái niệm này khác nhau.

## 12. Mapping và field types

Các field type cơ bản như keyword, text, date, boolean và numeric có mức tương đồng cao. Tuy nhiên, mapping option mới, field type đặc biệt và plugin-backed type có thể không có ở cả hai sản phẩm hoặc có semantics khác.

Khi chuyển đổi cần kiểm tra:

- Text analyzer, tokenizer và token filter.
- Synonym sets và synonym graph.
- Normalizer.
- Nested và flattened.
- Runtime fields hoặc các kiểu field động.
- Dense vector, sparse vector và vector search.
- Geo point/shape.
- Rank feature và rank features.
- Percolator hoặc field type chuyên biệt.
- Dynamic templates và multi-fields.
- Doc values, fielddata và ignore_above.

Không chỉ copy mapping JSON rồi giả định thành công. Tạo index mới trên server đích và xác nhận mapping được chấp nhận, sau đó index fixture và chạy query/aggregation thực tế.

Một field mapping có thể được chấp nhận nhưng có analyzer hoặc scoring behavior khác. Test nên kiểm tra kết quả tìm kiếm chứ không dừng ở create index thành công.

## 13. Analyzer, synonym và language processing

Analyzer là thành phần quan trọng của full-text search. Hai cluster có thể dùng cùng tên analyzer nhưng cấu hình hoặc plugin không giống nhau.

Ví dụ một index có thể phụ thuộc vào:

- ICU analysis.
- Vietnamese tokenizer hoặc plugin ngôn ngữ.
- Synonym file hoặc synonym API.
- Edge n-gram cho autocomplete.
- Stemmer và stopword.
- Character filter tùy chỉnh.

Plugin analysis thường phải được cài trên các node tương ứng và tương thích với đúng phiên bản server. Plugin build cho Elasticsearch không thể mặc định cài vào OpenSearch, hoặc ngược lại.

Khi migrate:

1. Liệt kê analyzer và plugin đang dùng.
2. Xác định plugin có bản tương ứng ở server đích không.
3. So sánh tokenizer/filter configuration.
4. Chạy Analyze API với bộ từ khóa đại diện.
5. So sánh token stream và search result.
6. Reindex nếu analyzer/mapping thay đổi.

Đối với tiếng Việt, kiểm tra dấu, từ ghép, stemming, synonym và cách tách từ bằng fixture thực tế. Hai analyzer khác nhau có thể làm kết quả search thay đổi dù query JSON không đổi.

## 14. Aggregation, sorting và pagination

Các aggregation cơ bản như terms, range, histogram, stats và date histogram thường có cách dùng tương tự. Tuy nhiên, các tính năng nâng cao và plugin-specific aggregation có thể khác.

Cần kiểm tra:

- Terms aggregation và bucket ordering.
- Composite aggregation và after_key.
- Nested/reverse_nested.
- Pipeline aggregation.
- Cardinality precision.
- Significant terms hoặc các thống kê chuyên biệt.
- Search after, PIT và scroll.
- Sort mode, missing values và nested sort.
- Total hits và track_total_hits.

Không chỉ so sánh response có cùng tên bucket. Hãy dùng dữ liệu fixture biết trước để xác nhận doc_count, thứ tự, biên range và semantics.

Nếu ứng dụng phụ thuộc deep pagination hoặc PIT, cần xác nhận API và client version hỗ trợ đầy đủ ở cả hai backend. Đây là tính năng cần test riêng, không suy ra từ việc search cơ bản hoạt động.

## 15. Vector search và semantic search

Vector search là một lĩnh vực có tốc độ phát triển cao, và hai sản phẩm đã phát triển tính năng riêng sau khi tách nhánh.

Cần phân biệt:

- Mapping cho vector field.
- Cách index vector.
- Similarity metric.
- Approximate nearest neighbor algorithm.
- KNN query syntax.
- Filter kết hợp vector search.
- Hybrid search giữa lexical và vector.
- Reranking và search pipeline.
- Model integration và inference processor.

Không giả định tên field type hoặc query DSL giống nhau thì thuật toán và kết quả ranking cũng giống nhau. Có thể có cùng khái niệm KNN nhưng API, giới hạn, tuning parameter hoặc plugin dependency khác nhau.

Nếu ứng dụng có semantic search, hãy xây test chất lượng retrieval riêng: bộ query chuẩn, expected relevant documents, recall@k hoặc metric phù hợp. HTTP 200 không chứng minh kết quả ranking tương đương.

## 16. Ingest pipeline và data lifecycle

Các pipeline ingest có thể dùng processor như set, rename, remove, date, grok, script, attachment hoặc enrichment. Một số processor thuộc core, một số phụ thuộc plugin hoặc feature riêng.

Ngoài ingest, hai hệ sinh thái có cách quản lý vòng đời index khác nhau:

- Elasticsearch có các cơ chế như Index Lifecycle Management (ILM) và các API liên quan.
- OpenSearch có Index State Management (ISM) và các API/plugin liên quan.

Tên mục tiêu như rollover, warm/cold tier, retention hoặc delete có thể giống nhau, nhưng policy schema, action, transition và API không nhất thiết giống nhau.

Không copy ILM policy rồi đổi endpoint để mong nó thành ISM policy. Hãy chuyển đổi từng state/action và kiểm tra:

- Rollover alias/data stream.
- Retention và delete.
- Allocation/tier.
- Snapshot action.
- Force merge.
- Policy transition.
- Retry và error state.
- Quyền security cần thiết.

## 17. Security và authentication khác nhau

Cả hai sản phẩm đều có cơ chế bảo mật, TLS và authorization, nhưng API và mô hình cấu hình có thể khác.

Elasticsearch thường dùng các tính năng security trong Elastic Stack, với API và cấu hình theo phiên bản/license. OpenSearch có OpenSearch Security plugin và các API/configuration riêng, bao gồm role, user, backend role, tenant và fine-grained access control theo cách của sản phẩm.

Các điểm cần kiểm tra:

- Basic authentication hoặc service account.
- API key và credential lifecycle.
- TLS certificate/truststore.
- Role mapping và backend roles.
- Index-level permissions.
- Document-level và field-level security.
- Audit logging.
- Security plugin compatibility.
- Authentication provider như LDAP/SAML/OIDC theo cấu hình.
- CORS và network boundary nếu có browser client.

Không giả định role Elasticsearch có thể import trực tiếp thành OpenSearch role. Không giả định tên API security giống nhau hoặc quyền có cùng semantics.

Nếu backend dùng một service credential có quyền đọc mọi tenant, ứng dụng vẫn phải áp dụng tenant authorization ở tầng service cho mọi request. Security ở cluster và authorization của người dùng cuối là hai lớp khác nhau.

## 18. Plugin và extension không thể dùng thay thế tùy ý

Plugin thường gắn chặt với:

- Sản phẩm (Elasticsearch hoặc OpenSearch).
- Phiên bản server.
- Phiên bản Lucene.
- Plugin API và binary compatibility.
- Cấu hình node và cluster.

Một plugin được build cho Elasticsearch không mặc định chạy trên OpenSearch. Ngược lại, plugin OpenSearch cũng không được xem là plugin Elasticsearch.

Lập danh sách plugin đang sử dụng:

| Nhóm | Ví dụ nhu cầu | Việc cần xác minh |
|---|---|---|
| Analysis | ICU, language analyzer | Plugin có bản tương ứng không |
| Security | Auth, audit, DLS/FLS | Feature/license/API khác nhau thế nào |
| Ingest | Attachment, enrichment | Processor có tồn tại và cùng semantics không |
| Vector | KNN, ANN | Mapping, query, algorithm và tuning |
| Observability | Metrics, tracing | Integration và endpoint |
| Storage | Repository snapshot | Plugin và repository compatibility |

Không triển khai server mới nếu một plugin bắt buộc của ứng dụng chưa có phương án thay thế đã kiểm thử.

## 19. Kibana và OpenSearch Dashboards

OpenSearch Dashboards bắt nguồn từ Kibana 7.10.2 nhưng đã phát triển độc lập. Các khái niệm dashboard, visualization, saved object và data view có thể tương tự, nhưng không nên giả định saved object export từ một sản phẩm luôn import trực tiếp được sang sản phẩm kia.

Cần kiểm tra:

- Dashboard và visualization type.
- Saved object schema/version.
- Data view/index pattern.
- Security tenant/workspace.
- Plugin visualization.
- Alerting và reporting.
- Query language và Dev Tools.
- Role/permission mapping.

Nếu dashboard là một phần của deliverable migration, hãy export/import trên môi trường test và xác nhận từng visualization, filter, alert và quyền truy cập.

## 20. Snapshot, restore và data migration

Snapshot là dữ liệu nhị phân gắn với metadata và format của sản phẩm/phiên bản. Không nên giả định snapshot của Elasticsearch mới có thể restore trực tiếp vào OpenSearch hoặc ngược lại.

Khả năng tương thích phụ thuộc:

- Phiên bản nguồn và đích.
- Mốc fork.
- Snapshot format.
- Index metadata và mapping.
- Plugin field type.
- Feature state/system index.
- Repository type.
- Cluster setting và security configuration.

Một số đường migration có thể hỗ trợ snapshot từ các phiên bản Elasticsearch cũ gần mốc fork, nhưng phải xác nhận chính xác tài liệu migration của phiên bản nguồn/đích. Không dùng việc “snapshot tạo thành công” làm bằng chứng restore tương thích.

Các chiến lược phổ biến:

1. Snapshot/restore nếu đúng cặp phiên bản được hỗ trợ.
2. Reindex từ remote hoặc export/import qua API.
3. Rebuild projection từ database/source of truth.
4. Dual-write/dual-read có kiểm soát trong giai đoạn chuyển đổi.
5. Tạo index mới, kiểm tra rồi chuyển alias.

Reindex qua REST API có thể cần cấu hình remote allowlist, network access, authentication và giới hạn tải. Hãy kiểm tra mapping, analyzer và pipeline riêng trên target trước khi nạp dữ liệu lớn.

## 21. Không thể trộn node của hai sản phẩm trong cùng cluster

Elasticsearch và OpenSearch là hai distribution phát triển độc lập. Không đưa một node Elasticsearch vào OpenSearch cluster hoặc ngược lại như thể chúng là các node cùng một sản phẩm.

Cluster coordination, transport protocol, metadata và version compatibility không được thiết kế để trộn node của hai sản phẩm. Việc cả hai dùng Lucene và có REST API tương tự không làm internal node protocol tương thích.

Nếu muốn chuyển đổi, hãy xây cluster đích riêng, di chuyển hoặc tái tạo dữ liệu, xác nhận kết quả và chuyển traffic theo kế hoạch. Không thực hiện rolling upgrade xuyên sản phẩm bằng cách thay binary node từng cái một.

## 22. Ma trận tương thích cần xác minh

Không có một con số version duy nhất mô tả toàn bộ khả năng tương thích. Với ứng dụng Spring, nên lập ma trận:

| Thành phần | Ví dụ cần ghi rõ |
|---|---|
| Spring Boot | Phiên bản chính xác |
| Spring Framework | Phiên bản được Boot quản lý |
| Spring Data release train | Phiên bản chính xác |
| Spring Data Elasticsearch | Phiên bản artifact |
| Java runtime | JDK version |
| Server | Elasticsearch hoặc OpenSearch và phiên bản |
| Java client | Elasticsearch Java API Client hoặc OpenSearch Java Client |
| Transport | HTTP/REST client và TLS/auth setup |
| Plugins | Tên và phiên bản từng plugin |
| Index mapping | Versioned schema |
| Dashboards | Kibana hoặc OpenSearch Dashboards version |

Mỗi dòng trong ma trận cần có trạng thái:

- Supported theo tài liệu chính thức.
- Tested by project integration tests.
- Works with limited feature set.
- Unsupported/unknown.
- Blocked bởi plugin hoặc API.

Đừng ghi “compatible” nếu chỉ mới kiểm tra health endpoint hoặc một query match.

## 23. Phân biệt supported, compatible và tested

Ba từ này nên được dùng rõ ràng:

**Supported**: nhà cung cấp hoặc dự án xác nhận cặp phiên bản nằm trong phạm vi hỗ trợ và có thể nhận bug fix theo policy.

**Compatible**: các thành phần có thể giao tiếp ở một phạm vi nhất định, nhưng chưa chắc nằm trong ma trận hỗ trợ chính thức.

**Tested**: nhóm dự án đã chạy bộ test cụ thể trên cặp phiên bản và ghi nhận kết quả.

Một cặp server/client có thể “works” trong môi trường test nhưng không được support. Khi nâng cấp, API mới có thể làm integration hỏng mà không có cam kết từ nhà cung cấp.

Trong tài liệu kiến trúc, ghi cả phiên bản và feature scope. Ví dụ: “Search, index và bulk cơ bản đã được kiểm thử trên cặp A/B; PIT và vector search chưa được xác nhận” rõ ràng hơn “OpenSearch compatible”.

## 24. Cách kiểm tra version compatibility của Spring Data

Khi chọn Spring Data Elasticsearch:

1. Xác định Spring Boot version.
2. Xác định Spring Data release train do dependency management quản lý.
3. Tra compatibility matrix của đúng Spring Data release.
4. Xác định Elasticsearch server version được hỗ trợ.
5. Xác định Java API Client version mà release train dùng.
6. Kiểm tra JDK tối thiểu.
7. Kiểm tra API đã deprecated hoặc removed.
8. Chạy integration test trên server version thực tế.

Không override riêng Java client version mà không hiểu dependency alignment. Spring Data Elasticsearch có thể dựa vào các class/client API cụ thể; ép một client version không tương thích có thể gây NoSuchMethodError, ClassNotFoundException hoặc lỗi serialization/runtime.

Dùng dependency management của Spring Boot/Spring Data khi có thể. Nếu cần override, ghi rõ lý do và kiểm tra dependency tree.

## 25. Kiểm tra client/server bằng smoke test

Một smoke test tối thiểu cần làm nhiều hơn health check:

1. Kết nối và xác thực.
2. Lấy cluster/server version.
3. Tạo index với mapping cần dùng.
4. Index một document.
5. Get document theo ID.
6. Search bằng match và term.
7. Sort trên keyword/numeric/date field.
8. Pagination bằng from/size.
9. Bulk index và đọc item-level response.
10. Aggregation.
11. Highlight nếu ứng dụng dùng.
12. Update và delete.
13. Kiểm tra alias/template/ingest nếu có.
14. Kiểm tra security và tenant isolation.
15. Kiểm tra PIT/search_after nếu ứng dụng dùng.

Chạy smoke test trên mỗi cặp server/client dự định hỗ trợ. Lưu server version, client version, dependency lock và kết quả test cùng release artifact.

## 26. Kiểm thử Query DSL thực tế

Tạo fixture có dữ liệu biết trước và chạy cùng một bộ query trên hai server. So sánh:

- Số lượng hit.
- ID và thứ tự kết quả.
- Score nếu ứng dụng phụ thuộc ranking.
- Sort values.
- Highlight fragments theo semantics cho phép.
- Aggregation bucket keys và counts.
- Date boundary/timezone.
- Nested query behavior.
- Null/missing field behavior.
- Error response cho query không hợp lệ.

Không nên yêu cầu score tuyệt đối giống nhau nếu implementation/analyzer khác nhau và sản phẩm không cam kết. Thay vào đó, định nghĩa tiêu chí nghiệp vụ: các document quan trọng có nằm trong top K hay không, filter có chính xác không, bucket counts có đúng không.

## 27. Kiểm thử mapping và dữ liệu

Một bài test migration nên tạo index mới từ mapping target, không chỉ restore dữ liệu.

Kiểm tra:

- Tất cả field type.
- Multi-field và normalizer.
- Analyzer và token stream.
- Nested path.
- Date format và timezone.
- Numeric precision.
- Null/missing values.
- Dynamic template.
- Alias và routing.
- Ingest pipeline.
- Source filtering và stored fields.

Nếu mapping thay đổi, có thể cần transform dữ liệu. Ví dụ một field text ở source có thể cần keyword multi-field mới ở target để sort/aggregation. Một analyzer plugin có thể cần thay bằng analyzer khác, dẫn tới kết quả search khác.

Không sửa dữ liệu gốc chỉ để phù hợp target nếu chưa xác định rõ transformation và khả năng rollback.

## 28. Các rủi ro khi dùng Spring Data Elasticsearch với OpenSearch

Một ứng dụng có thể build và kết nối thành công nhưng gặp vấn đề ở runtime:

- Java API Client gửi request option không được OpenSearch hỗ trợ.
- Response JSON khác khiến deserialization lỗi.
- Spring Data dùng API Elasticsearch mới hơn server target.
- Repository query derivation tạo DSL khác kỳ vọng.
- NativeQuery dùng option chưa có trên OpenSearch.
- Aggregation container hoặc hit metadata khác.
- Security plugin từ chối request do credential/role khác.
- Plugin analysis/vector không có hoặc khác phiên bản.
- Error mapping của client không nhận diện status/error type.
- PIT/search_after behavior không khớp giả định.

Nếu dùng Spring Data Elasticsearch với OpenSearch trong production, hãy ghi rõ feature subset đã được xác nhận và khóa version. Đừng để việc “kết nối thành công” trở thành một cam kết tương thích không có căn cứ.

## 29. Chiến lược nếu cần hỗ trợ cả hai backend

Nếu sản phẩm cần chạy trên cả Elasticsearch và OpenSearch, hãy tránh để code nghiệp vụ phụ thuộc trực tiếp vào client cụ thể.

~~~text
Application service
        |
        v
SearchPort (application interface)
        |
        +----------------------+
        |                      |
        v                      v
Elasticsearch adapter     OpenSearch adapter
        |                      |
        v                      v
Elasticsearch Java        OpenSearch Java
API Client                 Client
        |                      |
        v                      v
Elasticsearch cluster     OpenSearch cluster
~~~

Interface nên biểu diễn use case, không expose request type của client:

~~~java
public interface ProductSearchPort {

    ProductSearchPage search(ProductSearchCriteria criteria);

    void index(ProductDocument document);

    void delete(String productId);
}
~~~

Hai adapter có thể dùng model query nội bộ chung rồi chuyển thành DSL tương ứng. Không dùng SearchRequest của Elasticsearch trong interface nếu adapter OpenSearch phải triển khai cùng interface.

Nếu ứng dụng reactive, định nghĩa contract bằng Mono/Flux hoặc một abstraction async nhất quán. Không để một adapter block còn adapter kia non-blocking mà caller không biết semantics.

## 30. Tránh abstraction chung quá mức

Không phải mọi feature đều có thể biểu diễn hoàn toàn giống nhau. Vector search, search pipeline, security API hoặc plugin-specific query có thể chỉ có ở một backend hoặc khác semantics.

Một interface quá chung có thể:

- Ẩn mất feature quan trọng.
- Tạo nhiều tham số tùy chọn khó hiểu.
- Ép backend yếu hơn mô phỏng hành vi không có.
- Làm caller không biết feature có được hỗ trợ hay không.

Có thể chia capability:

~~~java
public interface ProductSearchPort {
    ProductSearchPage search(ProductSearchCriteria criteria);
}

public interface VectorSearchCapability {
    VectorSearchPage searchSimilar(VectorSearchCriteria criteria);
}

public interface SearchAdministrationCapability {
    void createIndex(ProductIndexDefinition definition);
}
~~~

Ứng dụng có thể kiểm tra capability khi khởi động hoặc dùng cấu hình rõ ràng. Nếu một backend không hỗ trợ use case bắt buộc, fail fast thay vì trả kết quả giả hoặc bỏ qua filter.

## 31. Migration từ Elasticsearch sang OpenSearch

Một quy trình chuyển đổi nên có:

1. **Inventory:** liệt kê server/client/Spring Data version, index, mapping, template, alias, plugin, ingest pipeline, security và dashboard.
2. **Feature mapping:** ghép từng feature với API/feature tương ứng trên OpenSearch.
3. **Compatibility spike:** tạo proof of concept cho các query và operation quan trọng.
4. **Target design:** chọn OpenSearch version, Java client, Spring integration và plugin.
5. **Data migration:** snapshot nếu cặp phiên bản được hỗ trợ, hoặc reindex/export-import/rebuild.
6. **Validation:** so sánh count, sample, query result, sort, aggregation và security.
7. **Performance test:** đo throughput, latency, memory và recovery.
8. **Cutover:** chuyển traffic qua endpoint/alias/service discovery theo kế hoạch.
9. **Observe:** theo dõi error, lag, search quality và resource.
10. **Rollback:** giữ source/index cũ và điều kiện quay lại trong thời gian xác định.

Không chuyển production bằng cách chỉ thay hostname trong cấu hình rồi chờ xem. Điều đó bỏ qua khác biệt client, plugin, mapping và security.

## 32. Migration dữ liệu và reindex

Nếu snapshot không nằm trong phạm vi hỗ trợ, có thể dùng các cách khác:

- Reindex từ remote nếu target/source hỗ trợ và được cấu hình.
- Export theo batch rồi bulk index.
- Dùng ETL pipeline.
- Rebuild index từ database/source of truth.
- Dùng dual-write hoặc change stream trong giai đoạn catch-up.

Với dữ liệu lớn, nên tạo index target version mới, nạp dữ liệu theo batch, rồi replay các thay đổi phát sinh sau snapshot.

Cần kiểm tra:

- ID ổn định.
- Version/order của update.
- Delete event.
- Date/number conversion.
- Analyzer và field transform.
- Partial bulk failure.
- Retry và DLQ.
- Count và checksum.
- Alias switch và rollback.

Không chỉ so sánh tổng count. Hãy đối chiếu theo tenant, loại document, trạng thái và khoảng thời gian để tìm lỗi lệch cục bộ.

## 33. Dual-run và so sánh kết quả

Trong một giai đoạn kiểm chứng, có thể gửi cùng query tới cả cluster cũ và mới nhưng chỉ trả response của hệ thống đang được chọn. Kết quả cluster còn lại dùng để so sánh.

Cần giới hạn dual-run để không nhân đôi tải ngoài dự kiến. Có thể sampling một phần request hoặc chạy trên traffic replay đã được masking.

So sánh:

- Success/error rate.
- Latency p50/p95/p99.
- Hit IDs và thứ tự top K.
- Aggregation counts.
- Highlight behavior.
- Mapping errors.
- Bulk indexing success.
- Data freshness.
- Security/tenant filtering.

Không log toàn bộ query hoặc response có dữ liệu nhạy cảm. Dùng request ID và các metric đã giảm dữ liệu.

## 34. Cutover và rollback

Một chiến lược cutover thường có:

~~~text
             Source of truth
                    |
             Sync / CDC stream
                /       \
               v         v
        Old search     New search
           cluster       cluster
               \         /
                \       /
             Compare / validate
                    |
                    v
              Switch traffic
                    |
                    v
                Observe
                    |
          +---------+---------+
          |                   |
          v                   v
        Keep                Rollback
        target              to old
~~~

Trước cutover:

- Catch up backlog.
- Chạy reconciliation.
- Xác nhận security và role.
- Chạy smoke/performance test.
- Chuẩn bị rollback endpoint/config.
- Xác định ai có quyền thực hiện cutover.
- Giữ dữ liệu nguồn đủ để rebuild nếu cần.

Sau cutover, không xóa cluster cũ ngay. Giữ trong thời gian rollback đã định, nhưng tránh dual-write vô thời hạn nếu chưa có cơ chế nhất quán.

## 35. Khi nào nên chọn Elasticsearch hoặc OpenSearch?

Quyết định phụ thuộc nhiều yếu tố:

- Feature cần dùng.
- License và yêu cầu pháp lý.
- Managed service đang có.
- Hệ sinh thái plugin.
- Spring integration/client support.
- Kỹ năng vận hành của đội.
- Security và compliance.
- Search quality và performance.
- Chi phí hạ tầng/support.
- Lộ trình nâng cấp và migration.

Không có lựa chọn tốt nhất cho mọi ứng dụng. Nếu dự án phụ thuộc sâu vào Elastic-specific feature hoặc Elastic Stack integration, hãy đánh giá chi phí chuyển đổi kỹ. Nếu dự án cần distribution Apache 2.0 và feature OpenSearch đáp ứng use case, OpenSearch có thể phù hợp. Quyết định cần dựa trên phiên bản và feature thực tế, không chỉ tên sản phẩm.

## 36. Checklist xác nhận tương thích

**Server và client**

- Xác định chính xác Elasticsearch/OpenSearch version.
- Xác định Java client artifact và version.
- Không trộn package/client của hai sản phẩm tùy tiện.
- Kiểm tra JDK và TLS/authentication.
- Kiểm tra dependency tree và version alignment.

**Spring**

- Xác nhận Spring Boot và Spring Data release train.
- Tra compatibility matrix chính thức.
- Kiểm tra repository, Operations và NativeQuery.
- Kiểm tra mapping/conversion.
- Kiểm tra reactive API nếu dùng WebFlux.
- Kiểm tra lỗi runtime và serialization.

**Feature**

- Query DSL và filter.
- Sort, pagination, search_after và PIT.
- Aggregation và composite aggregation.
- Highlight.
- Bulk, update và delete.
- Analyzer, synonym và plugin.
- Ingest pipeline.
- Vector/hybrid search.
- Security/DLS/FLS.
- Snapshot/restore, alias và lifecycle.

**Vận hành**

- Index template và settings.
- Plugin binary/version.
- Dashboard và saved objects.
- Backup/recovery.
- Monitoring và alert.
- Performance benchmark.
- Data reconciliation.
- Rollback plan.

## 37. Các lỗi thường gặp khi đánh giá tương thích

| Nhận định sai | Vì sao sai | Cách xác minh |
|---|---|---|
| Cả hai dùng Lucene nên hoàn toàn tương thích | API và feature đã phát triển riêng | Test REST, query và semantics |
| Cùng có REST API nên đổi hostname là đủ | Client model, endpoint và response có thể khác | Chạy smoke test trên cặp version |
| Spring Data Elasticsearch hỗ trợ mọi OpenSearch | Spring Data có release matrix theo Elasticsearch/client | Kiểm tra integration/version cụ thể |
| Java client Elasticsearch dùng được nguyên trạng với OpenSearch | Client model và API khác nhau | Dùng client đúng hệ sinh thái hoặc test rõ scope |
| Compatibility mode bảo đảm cross-product | Mode có phạm vi major-version cụ thể | Đọc contract của client/server |
| Snapshot nào cũng restore được | Snapshot phụ thuộc version, product và plugin | Kiểm tra migration matrix và thử restore |
| Plugin Elasticsearch chạy trên OpenSearch | Plugin binary/API gắn với product/version | Tìm plugin build đúng target |
| Query trả 200 nghĩa là kết quả giống nhau | Analyzer/scoring/mapping có thể khác | So sánh fixture và retrieval semantics |
| Có cùng tên security role | Security model/API khác nhau | Test authorization thực tế |
| Có thể rolling upgrade xuyên sản phẩm | Cluster protocol/metadata không tương thích | Dựng cluster đích riêng và migrate |

## 38. Quy trình ra quyết định cho dự án Spring

1. Ghi lại server hiện tại và server mục tiêu với version đầy đủ.
2. Ghi lại Spring Boot, Spring Data Elasticsearch và Java client.
3. Liệt kê các API Spring Data đang dùng.
4. Liệt kê plugin, analyzer, mapping và security feature.
5. Đánh dấu feature nào bắt buộc và feature nào có thể thay thế.
6. Tra compatibility matrix của Spring Data và client.
7. Nếu dùng OpenSearch, kiểm tra OpenSearch Java Client hoặc Spring integration tương ứng.
8. Dựng integration environment với đúng version.
9. Chạy smoke test và query fixture.
10. Chạy load test, recovery test và security test.
11. Lập migration/rollback plan.
12. Ghi rõ feature scope đã hỗ trợ, chưa hỗ trợ và chưa xác minh.

Nếu chưa xác minh được một tính năng, đánh dấu unknown thay vì suy đoán. Đây là thông tin quan trọng để quyết định có thể đưa backend đó vào production hay không.

Elasticsearch và OpenSearch có chung lịch sử, Lucene và nhiều khái niệm REST/Query DSL, nhưng hiện là hai sản phẩm độc lập. Spring Data Elasticsearch được thiết kế theo compatibility matrix của từng release với Elasticsearch và Java client tương ứng; kết nối tới OpenSearch trong một số trường hợp không đồng nghĩa được hỗ trợ đầy đủ. Khi chọn hoặc chuyển backend, cần xác minh riêng server, client, Spring Data, mapping, analyzer, plugin, security, aggregation, pagination và snapshot. Một ma trận version rõ ràng cùng integration test trên đúng cặp sản phẩm là cơ sở đáng tin cậy hơn giả định rằng hai hệ thống có thể thay thế trực tiếp cho nhau.
