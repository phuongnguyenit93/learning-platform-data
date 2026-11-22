# Đánh giá giải pháp bằng tính đúng đắn, mức liên quan và hiệu năng

Một giải pháp tìm kiếm có thể chạy nhanh nhưng trả về tài liệu sai, hoặc trả về tài liệu phù hợp nhưng xếp hạng kém. Cũng có giải pháp cho kết quả tốt trên vài truy vấn demo nhưng chậm khi dữ liệu tăng, nhiều người dùng tìm kiếm đồng thời hoặc hệ thống đang index dữ liệu mới.

Vì vậy, đánh giá một giải pháp Spring Data Elasticsearch cần xem ba trục riêng biệt:

- **Tính đúng đắn (correctness):** truy vấn đúng dữ liệu, áp dụng đúng điều kiện, trả đúng cấu trúc và tuân thủ quy tắc nghiệp vụ/bảo mật.
- **Mức liên quan (relevance):** kết quả phù hợp với ý định người dùng có xuất hiện và được xếp ở vị trí tốt hay không.
- **Hiệu năng (performance):** hệ thống đáp ứng độ trễ, thông lượng, độ tươi dữ liệu và chi phí tài nguyên trong điều kiện tải dự kiến hay không.

Ba trục này bổ sung cho nhau nhưng không thể thay thế nhau. Một truy vấn trả về đúng 10 document theo filter chưa chắc đã xếp hạng tốt. Một ranking có NDCG cao chưa chứng minh tenant filter không làm lộ dữ liệu. Một benchmark có p95 thấp chưa chứng minh hệ thống đáp ứng được khi dữ liệu tăng gấp mười lần.

Bài học này trình bày cách xác định tiêu chí, xây bộ dữ liệu đánh giá, kiểm tra giải pháp bằng Spring Data Elasticsearch, đo chất lượng ranking và benchmark hiệu năng theo một quy trình có thể lặp lại.

## 1. Xác định bài toán trước khi chọn cách đo

Không có một bộ metric phù hợp cho mọi chức năng tìm kiếm. Trước tiên cần mô tả người dùng đang muốn làm gì và hệ thống phải trả lời ra sao.

Ví dụ một catalog thương mại điện tử có các use case:

| Use case | Ý định | Hành vi mong đợi |
|---|---|---|
| Tìm theo tên | Tìm sản phẩm có cụm từ người dùng nhập | Tên phù hợp xuất hiện ở đầu |
| Tìm theo mã SKU | Tra cứu một mã chính xác | Sản phẩm có SKU đó được trả về chính xác |
| Lọc danh mục | Thu hẹp kết quả theo category | Không có sản phẩm ngoài category |
| Lọc giá | Tìm sản phẩm trong khoảng giá | Mọi kết quả thỏa điều kiện range |
| Tìm ngữ nghĩa | Tìm sản phẩm theo mô tả nhu cầu | Kết quả phù hợp dù không trùng từ |
| Autocomplete | Hoàn thành truy vấn khi người dùng đang gõ | Gợi ý nhanh và đúng ý |
| Trang quản trị | Tìm theo trạng thái, ngày tạo và chủ sở hữu | Filter và quyền truy cập chính xác |

Mỗi use case cần một bộ query đại diện và tiêu chí thành công riêng. Với tìm SKU, exact match gần như là yêu cầu correctness. Với truy vấn tự nhiên, nhiều kết quả có thể cùng liên quan ở các mức khác nhau, nên cần đánh giá ranking.

### 1.1. Viết yêu cầu có thể kiểm chứng

Tránh yêu cầu chung chung như “search phải tốt và nhanh”. Hãy chuyển thành điều kiện đo được:

- SKU chính xác phải tìm đúng một sản phẩm đang tồn tại.
- Filter tenant phải loại bỏ mọi document thuộc tenant khác.
- Query tên sản phẩm phải trả các sản phẩm liên quan trong top 10.
- p95 latency không vượt ngưỡng đã thỏa thuận ở tải mục tiêu.
- Thay đổi từ database phải xuất hiện trong search index trong khoảng thời gian freshness đã cam kết.
- Khi dữ liệu tăng, throughput index vẫn đạt tốc độ ingest dự kiến.

Ngưỡng cụ thể phụ thuộc sản phẩm, hạ tầng và SLA. Không nên sao chép một con số latency hoặc relevance từ hệ thống khác rồi xem đó là tiêu chuẩn mặc định.

## 2. Ba trục đánh giá và mối quan hệ giữa chúng

| Trục | Câu hỏi chính | Ví dụ bằng chứng |
|---|---|---|
| Correctness | Kết quả có đúng quy tắc và dữ liệu không? | Assertions, integration tests, data reconciliation |
| Relevance | Kết quả hữu ích có được xếp cao không? | Precision@k, Recall@k, MRR, NDCG |
| Performance | Hệ thống đáp ứng tải với chi phí nào? | p95/p99 latency, throughput, resource usage |

Có thể hình dung quá trình đánh giá theo thứ tự:

~~~text
                  Search solution
                        |
                        v
               Correctness checks
                 /           \
              fail           pass
               |               |
          Fix behavior         v
                         Relevance evaluation
                           /          \
                        fail          pass
                         |              |
                   Tune ranking         v
                                  Performance benchmark
                                    /           \
                                  fail          pass
                                   |              |
                              Optimize system    v
                                           Release decision
~~~

Đây là thứ tự ưu tiên thực tế: trước khi đo ranking hoặc tốc độ, phải bảo đảm truy vấn đang thực hiện đúng điều kiện. Nếu filter category bị thiếu, một benchmark nhanh có thể đang đo một tập dữ liệu nhỏ hơn yêu cầu; nếu tenant filter bị sai, ranking tốt cũng không có ý nghĩa.

Không gộp cả ba trục thành một điểm trung bình duy nhất nếu chưa xác định rõ mức độ ưu tiên và ngưỡng bắt buộc. Một lỗi correctness nghiêm trọng không thể được bù bằng p95 thấp.

## 3. Đánh giá tính đúng đắn của giải pháp

Correctness kiểm tra hệ thống có thực hiện đúng hợp đồng của use case hay không. Với Spring Data Elasticsearch, cần kiểm tra từ dữ liệu đầu vào, mapping, truy vấn cho tới kết quả trả về.

### 3.1. Đúng schema và mapping

Kiểm tra:

- Field text được index bằng analyzer mong muốn.
- Field keyword dùng cho exact match, filter, sort hoặc aggregation.
- Numeric/date field có kiểu và format phù hợp.
- Nested field được truy vấn bằng nested query khi cần giữ quan hệ giữa các phần tử.
- Dense vector có đúng dimensions và similarity.
- Dynamic mapping không tự tạo kiểu ngoài dự kiến.

Có thể đọc mapping thực tế:

~~~http
GET /products-read/_mapping
~~~

Không chỉ kiểm tra annotation `@Field` trong Java. Index có thể đã được tạo trước khi code đổi, hoặc index template có thể tạo mapping khác với mapping mong đợi.

### 3.2. Đúng điều kiện truy vấn

Một query thường kết hợp:

- Điều kiện full-text.
- Filter chính xác.
- Range.
- Trạng thái hoạt động.
- Tenant hoặc quyền truy cập.
- Sort và pagination.

Ví dụ yêu cầu: tìm laptop có nội dung liên quan đến “lightweight laptop”, chỉ lấy sản phẩm đang bán, thuộc tenant hiện tại, giá từ 500 đến 1500.

Query phải bảo đảm điều kiện nghiệp vụ được áp dụng trong mọi nhánh tìm kiếm, kể cả khi thêm kNN hoặc hybrid search. Không chỉ kiểm tra query text; hãy kiểm tra filter được gửi xuống Elasticsearch và kết quả không chứa document ngoài phạm vi.

### 3.3. Đúng kết quả và cardinality

Với một số use case, kết quả mong đợi có thể xác định chính xác:

- SKU chính xác trả về document có ID cụ thể.
- Một document đã xóa không xuất hiện.
- Filter status=ACTIVE không trả document INACTIVE.
- Range giá không trả giá nằm ngoài biên.
- Query theo ID không trả nhầm document cùng tên.

Kiểm tra cả trường hợp không có kết quả, chỉ có một kết quả, nhiều kết quả, dữ liệu trùng và dữ liệu thiếu field.

### 3.4. Đúng sort và pagination

Nếu nhiều document có cùng giá trị sort, thứ tự có thể không ổn định nếu không có tie-breaker. Khi người dùng chuyển trang, document có thể bị lặp hoặc bỏ qua nếu dữ liệu thay đổi giữa các request.

Với pagination sâu, `search_after` thường phù hợp hơn việc tăng `from` rất lớn. Nếu cần giữ một snapshot ổn định trong khi người dùng duyệt nhiều trang, cân nhắc Point in Time (PIT) cùng `search_after` theo API Elasticsearch version đang dùng.

Correctness của pagination bao gồm:

- Không lặp document trong cùng một phiên duyệt.
- Không bỏ sót document do sort không xác định.
- Tie-breaker ổn định, thường là một field duy nhất phù hợp mapping.
- PIT/search_after được dùng đúng vòng đời nếu cần snapshot.

### 3.5. Đúng aggregation và total hits

Aggregation phải dùng field phù hợp. Ví dụ đếm category nên dùng keyword field hoặc subfield keyword, không dựa trên token của text field nếu mục tiêu là nhóm theo giá trị nguyên bản.

Đối với truy vấn có `track_total_hits` bị giới hạn, total hits có thể là giá trị ước lượng hoặc chỉ chính xác tới ngưỡng. Nếu API cần số lượng chính xác, cấu hình query phù hợp và đo thêm chi phí. Không đánh giá correctness chỉ bằng danh sách hit nếu response còn có total, facets hoặc aggregation.

### 3.6. Đúng freshness và consistency

Elasticsearch là hệ thống near-real-time. Document vừa được index có thể chưa xuất hiện trong search cho tới khi refresh. Vì vậy cần phân biệt:

- Get theo ID có semantics đọc document khác với Search.
- Search phụ thuộc refresh visibility.
- Outbox/event consumer có độ trễ riêng.
- Bulk indexing có thể thành công một phần.

Định nghĩa freshness SLA, ví dụ thời gian từ commit database đến khi document có thể tìm thấy. Đo bằng timestamp hoặc event position; không giả định thao tác save đồng nghĩa document lập tức xuất hiện trong mọi query.

### 3.7. Đúng quyền truy cập và tenant isolation

Đây là một phần của correctness, không phải một bước hardening tùy chọn. Mọi query phải áp dụng filter tenant/ACL ở server-side. Người dùng không được tự gửi điều kiện để mở rộng phạm vi truy cập.

Tạo test có document của nhiều tenant, rồi xác nhận:

- User tenant A không thấy document tenant B.
- Filter vẫn được áp dụng khi dùng hybrid search.
- Aggregation không làm lộ dữ liệu tenant khác.
- Autocomplete và suggestion cũng tuân thủ quyền.
- Search after, PIT và cache không làm rò dữ liệu giữa người dùng.

### 3.8. Đúng khi có dữ liệu lỗi hoặc thay đổi đồng thời

Kiểm tra field null hoặc thiếu, Unicode/dấu tiếng Việt/dấu câu/chuỗi dài, converter format cũ, event tới trùng hoặc không theo thứ tự, version conflict và document bị xóa trong lúc query hoặc pagination.

Một giải pháp chỉ đúng trên dữ liệu sạch ban đầu chưa đủ để đưa vào vận hành.

## 4. Xây bộ dữ liệu kiểm thử correctness

Nên tạo fixture nhỏ nhưng có chủ đích. Ví dụ:

| ID | Name | Category | Price | Status | Tenant |
|---|---|---|---:|---|---|
| p-101 | Lightweight Laptop | Computers | 899 | ACTIVE | A |
| p-102 | Gaming Laptop | Computers | 1499 | ACTIVE | A |
| p-103 | Laptop Sleeve | Accessories | 29 | ACTIVE | A |
| p-104 | Lightweight Laptop | Computers | 799 | INACTIVE | A |
| p-105 | Lightweight Laptop | Computers | 999 | ACTIVE | B |

Một số assertion:

- Query “lightweight laptop” với tenant A và status ACTIVE không được trả p-104 hoặc p-105.
- Filter price từ 500 đến 1500 không được trả p-103.
- SKU hoặc ID chính xác phải trả đúng record.
- Query “laptop” có thể trả p-101 và p-102 trước p-103 tùy relevance labels.

Với correctness, hãy xác định expected set hoặc các invariant rõ ràng. Với relevance, có thể có nhiều kết quả hợp lý và cần mức đánh giá theo thứ tự; không nên ép một thứ tự duy nhất nếu nghiệp vụ không yêu cầu.

## 5. Kiểm thử với Spring Data Elasticsearch

Unit test phù hợp để kiểm tra logic tạo query, mapper, normalization và quy tắc nghiệp vụ. Integration test với Elasticsearch thật cần thiết khi muốn xác nhận mapping, analyzer, query DSL và semantics của cluster.

### 5.1. Integration test bằng Elasticsearch thật

Có thể dùng Testcontainers với Elasticsearch image tương thích với phiên bản client:

~~~java
@Testcontainers
@SpringBootTest
class ProductSearchIntegrationTest {

    @Container
    static final ElasticsearchContainer elasticsearch =
            new ElasticsearchContainer(
                    DockerImageName.parse(
                            "docker.elastic.co/elasticsearch/elasticsearch:8.15.5"
                    )
            );

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.elasticsearch.uris",
                elasticsearch::getHttpHostAddress
        );
    }
}
~~~

Đây là ví dụ cấu trúc; image, security, credentials và property cần khớp Spring Boot/Elasticsearch version của dự án. Không dùng tag `latest` trong integration test vì kết quả có thể đổi khi image mới được phát hành.

### 5.2. Test kết quả filter

Ví dụ với `ElasticsearchOperations` và `NativeQuery`:

~~~java
Query query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
                .must(m -> m.match(mm -> mm
                        .field("name")
                        .query("lightweight laptop")
                ))
                .filter(f -> f.term(t -> t
                        .field("tenantId")
                        .value("A")
                ))
                .filter(f -> f.term(t -> t
                        .field("status")
                        .value("ACTIVE")
                ))
                .filter(f -> f.range(r -> r
                        .number(n -> n
                                .field("price")
                                .gte(500.0)
                                .lte(1500.0)
                        )
                ))
        ))
        .build();

SearchHits<ProductSearchDocument> hits =
        operations.search(query, ProductSearchDocument.class);

assertThat(hits.getSearchHits())
        .allSatisfy(hit -> {
            assertThat(hit.getContent().getTenantId()).isEqualTo("A");
            assertThat(hit.getContent().getStatus()).isEqualTo("ACTIVE");
            assertThat(hit.getContent().getPrice())
                    .isBetween(new BigDecimal("500"), new BigDecimal("1500"));
        });
~~~

Đây là snippet minh họa; kiểu field và builder API phụ thuộc release train, nhất là phần range query. Mục tiêu của test là xác nhận mọi hit đều thỏa filter. Ngoài ra nên assert expected IDs để bắt trường hợp query bỏ sót điều kiện hoặc trả thiếu dữ liệu.

### 5.3. Kiểm tra query thực tế

Khi test thất bại, cần xem query DSL được gửi xuống Elasticsearch. Có thể bật logging phù hợp cho client hoặc dùng Elasticsearch profile/explain API. Không dựa vào việc query builder Java trông có vẻ đúng.

`_explain` hữu ích để hiểu vì sao một document được match và score ra sao. Profile API cho biết các phần tốn thời gian trong query execution. Đây là công cụ chẩn đoán, không phải benchmark tải đại diện.

## 6. Đánh giá mức liên quan (Relevance)

Relevance trả lời câu hỏi: với một query cụ thể, kết quả nào thực sự hữu ích và kết quả hữu ích có được xếp cao không?

Một query thường có nhiều kết quả liên quan ở các mức khác nhau. Ví dụ tìm “quiet keyboard for office”:

- Bàn phím silent switch có thể rất liên quan.
- Bàn phím cơ thông thường có thể liên quan một phần.
- Một chiếc chuột không dây có thể không liên quan.

Vì vậy, relevance cần một bộ query và judgment về mức độ phù hợp.

### 6.1. Tạo bộ query đánh giá

Thu thập query từ search logs đã xử lý dữ liệu cá nhân phù hợp chính sách, câu hỏi thực tế từ người dùng, query do domain expert viết và query đại diện cho từ đồng nghĩa, typo, ngôn ngữ và ý định khác nhau.

Chia query thành các nhóm để tránh kết quả trung bình che giấu lỗi:

| Nhóm | Ví dụ | Điều cần đánh giá |
|---|---|---|
| Exact term | SKU, mã model | Exact match |
| Natural language | “máy tính nhẹ để đi công tác” | Ý nghĩa và ngữ cảnh |
| Synonym | “laptop” / “notebook” | Từ đồng nghĩa |
| Typo | Sai một vài ký tự | Tolerance với lỗi gõ |
| Multilingual | Có dấu/không dấu, Anh/Việt | Analyzer và embedding |
| Filtered query | “laptop dưới 1000” | Relevance trong tập đã lọc |
| Ambiguous | “apple” | Hiểu ý định theo context |

### 6.2. Gán nhãn relevance

Với mỗi cặp query-document, người đánh giá gán mức phù hợp. Ví dụ thang 0–3:

| Nhãn | Ý nghĩa |
|---:|---|
| 0 | Không liên quan |
| 1 | Có liên quan rất ít hoặc chỉ trùng một phần |
| 2 | Liên quan và có thể hữu ích |
| 3 | Rất phù hợp với ý định truy vấn |

Nên có guideline và ví dụ để các assessor chấm nhất quán. Với query quan trọng, có thể có hai người đánh giá độc lập và giải quyết bất đồng.

Đừng chỉ gán nhãn cho những document mà một giải pháp đã trả về. Nếu không, tài liệu liên quan mà cả hai giải pháp đều bỏ sót sẽ không được phát hiện. Có thể kết hợp pool kết quả từ BM25, vector search, hybrid search và một số tài liệu được chuyên gia chọn.

### 6.3. Precision@k

Precision@k đo tỷ lệ kết quả liên quan trong k vị trí đầu:

\[
Precision@k =
\frac{\text{số kết quả liên quan trong top k}}{k}
\]

Ví dụ top 5 có 4 kết quả được đánh nhãn liên quan thì Precision@5 = 0.8.

Metric này hữu ích khi người dùng thường chỉ xem một số kết quả đầu. Cần định nghĩa ngưỡng relevance nào được coi là relevant, ví dụ nhãn 2 hoặc 3.

### 6.4. Recall@k

Recall@k đo tỷ lệ tài liệu liên quan đã biết được tìm thấy trong top k:

\[
Recall@k =
\frac{\text{số tài liệu liên quan được tìm thấy trong top k}}
{\text{tổng số tài liệu liên quan trong bộ đánh giá}}
\]

Recall hữu ích khi cần tìm đủ tài liệu liên quan, ví dụ tìm kiếm tài liệu nội bộ hoặc tra cứu hồ sơ. Kết quả phụ thuộc độ đầy đủ của relevance judgments; nếu chưa gán nhãn đủ tài liệu liên quan, Recall có thể bị đánh giá sai.

### 6.5. Mean Reciprocal Rank (MRR)

MRR tập trung vào vị trí kết quả liên quan đầu tiên:

\[
MRR =
\frac{1}{|Q|}
\sum_{q \in Q}
\frac{1}{rank_q}
\]

Trong đó `rank_q` là vị trí đầu tiên có kết quả được xem là relevant. Nếu không có kết quả liên quan trong danh sách, reciprocal rank của query đó bằng 0.

MRR phù hợp với use case mà người dùng cần tìm được một đáp án đúng sớm, ví dụ tìm một trang hướng dẫn hoặc một sản phẩm theo mã/tên.

### 6.6. Mean Average Precision (MAP)

Average Precision cho một query là trung bình Precision tại các vị trí có kết quả relevant. MAP là trung bình AP trên tập query.

MAP đánh giá việc tìm và sắp xếp nhiều kết quả relevant trong danh sách, nhưng thường dùng nhãn relevant/not relevant nhị phân. Nếu có graded relevance, NDCG thường phù hợp hơn.

### 6.7. Normalized Discounted Cumulative Gain (NDCG)

NDCG hỗ trợ mức relevance nhiều cấp và giảm trọng số của kết quả nằm sâu:

\[
DCG@k =
\sum_{i=1}^{k}
\frac{2^{rel_i}-1}{\log_2(i+1)}
\]

\[
NDCG@k =
\frac{DCG@k}{IDCG@k}
\]

`rel_i` là relevance grade của kết quả tại vị trí i; `IDCG` là DCG của thứ tự lý tưởng. NDCG@k thường nằm trong khoảng 0 đến 1 khi tính theo định nghĩa chuẩn.

Ví dụ, một kết quả grade 3 ở vị trí đầu có đóng góp lớn hơn kết quả grade 3 ở vị trí thứ mười. NDCG phù hợp khi mức độ hữu ích khác nhau và thứ tự hiển thị quan trọng.

### 6.8. Chọn metric theo use case

| Use case | Metric nên quan tâm |
|---|---|
| Tra cứu một đáp án | MRR, Precision@1 |
| Trang kết quả top 10 | NDCG@10, Precision@10 |
| Tìm đủ tài liệu liên quan | Recall@k |
| Nhiều kết quả relevant | MAP, NDCG@k |
| Autocomplete | Success rate, MRR, latency |
| Semantic retrieval | Recall@k, NDCG@k và latency |

Không cần báo cáo mọi metric cho mọi hệ thống. Chọn metric phản ánh hành vi người dùng và giải thích rõ cách tính.

## 7. So sánh BM25, vector search và hybrid search

Với cùng một tập query và relevance labels, có thể so sánh:

1. **BM25:** baseline lexical search.
2. **Vector kNN:** semantic retrieval bằng embedding.
3. **Hybrid:** kết hợp lexical và vector ranking.
4. **Hybrid + reranker:** lấy candidate từ nhiều nguồn rồi dùng model khác xếp hạng lại.

Ví dụ bảng kết quả giả định:

| Phương án | NDCG@10 | Recall@50 | p95 query |
|---|---:|---:|---:|
| BM25 | 0.68 | 0.74 | 42 ms |
| Vector kNN | 0.71 | 0.82 | 67 ms |
| Hybrid RRF | 0.78 | 0.87 | 81 ms |
| Hybrid + reranker | 0.83 | 0.88 | 145 ms |

Đây chỉ là số minh họa để giải thích trade-off, không phải benchmark của Elasticsearch hoặc Spring Data. Trong dự án, cần đo trên dữ liệu và hạ tầng của chính hệ thống.

### 7.1. Hybrid ranking

BM25 và vector score có thang điểm khác nhau. Không cộng trực tiếp chúng nếu chưa chuẩn hóa hoặc hiệu chỉnh. Reciprocal Rank Fusion (RRF) kết hợp theo thứ hạng thay vì cộng raw scores:

\[
RRF(d) =
\sum_{r \in R}
\frac{1}{c + rank_r(d)}
\]

Một document xuất hiện cao trong nhiều danh sách có thể nhận điểm tổng hợp tốt. RRF thường là baseline hữu ích để so sánh hybrid search.

### 7.2. Reranking

Reranker nhận query và một tập candidate nhỏ, sau đó đánh giá mức liên quan chi tiết hơn. Nó có thể cải thiện thứ tự nhưng tăng chi phí và latency.

Đánh giá reranker cần:

- Candidate recall: tài liệu liên quan có được bước retrieval đưa vào tập candidate không?
- NDCG/MRR sau rerank.
- Thời gian rerank và tổng end-to-end latency.
- Chi phí inference và khả năng phục vụ concurrency.

Reranker không thể xếp một tài liệu lên đầu nếu bước retrieval ban đầu không đưa tài liệu đó vào candidate set.

## 8. Đánh giá hiệu năng (Performance)

Performance không chỉ là thời gian Elasticsearch trả response. Người dùng trải nghiệm toàn bộ đường đi:

~~~text
HTTP request
    |
    v
Application validation
    |
    v
Query embedding (nếu có)
    |
    v
Spring Data / Java Client
    |
    v
Elasticsearch coordination + shards
    |
    v
Result mapping / response assembly
    |
    v
HTTP response
~~~

Đo end-to-end latency để biết người dùng thực sự chờ bao lâu. Đồng thời đo từng phần để tìm bottleneck: embedding provider, application, network, Elasticsearch query, result conversion hay downstream service.

### 8.1. Các chỉ số latency

- **p50:** một nửa request hoàn tất trong thời gian này hoặc nhanh hơn.
- **p95:** 95% request hoàn tất trong thời gian này hoặc nhanh hơn.
- **p99:** 99% request hoàn tất trong thời gian này hoặc nhanh hơn.
- **Max:** request chậm nhất trong cửa sổ đo; dễ bị ảnh hưởng bởi outlier.

Average latency có thể che giấu tail latency. Một hệ thống có average tốt nhưng p99 rất cao vẫn có thể gây timeout hoặc trải nghiệm không ổn định.

### 8.2. Throughput và concurrency

Đo QPS, documents indexed per second, số request đồng thời, tỷ lệ lỗi/timeout, queue depth/backpressure và thời gian xử lý bulk batch.

QPS cao trong một benchmark một user không chứng minh hệ thống chịu được tải đồng thời. Hãy tăng concurrency theo các mức dự kiến và ghi lại khi nào latency hoặc error rate vượt ngưỡng.

### 8.3. Indexing latency và freshness

Với hệ thống cập nhật search index từ database/event, đo thời gian từ commit nghiệp vụ tới outbox publish, thời gian consumer nhận event, thời gian embedding (nếu có), thời gian index document và thời gian tới khi document search-visible sau refresh.

Freshness là một phần của hiệu năng vận hành. Một query trả trong 20 ms nhưng dữ liệu trễ 10 phút có thể không đáp ứng use case quản trị tồn kho.

### 8.4. Tài nguyên và chi phí

Theo dõi CPU và load trên data nodes, JVM heap, garbage collection và memory pressure, disk I/O/storage/segment count, network throughput, thread pool queue/rejections, shard count và shard size, cache hit/miss, chi phí embedding/reranking nếu có.

Một phương án nhanh hơn nhưng tiêu tốn gấp nhiều lần memory hoặc inference cost có thể không phù hợp khi scale.

## 9. Thiết kế benchmark có thể lặp lại

Một benchmark đáng tin cậy cần giữ các biến so sánh ổn định.

### 9.1. Chuẩn bị dữ liệu

Dataset nên phản ánh số lượng document dự kiến ở production, phân bố độ dài field, tỷ lệ document có field thiếu/null, cardinality của keyword fields, số lượng nested objects, phân bố tenant/category/status, tỷ lệ update/delete và tốc độ ingest, số lượng vector nếu dùng semantic search.

Benchmark trên 10.000 document trong khi production có 100 triệu document có thể cho kết luận sai về shard, memory và ANN.

### 9.2. Chuẩn bị cluster

Ghi lại Elasticsearch version và JVM, số node và role, CPU/RAM/disk, số primary shards và replicas, mapping/analyzer/index settings, refresh interval, cache state nếu kiểm soát được, hạ tầng client/application và network.

Không so sánh hai phương án nếu một bên chạy trên cluster mạnh hơn hoặc có cache warm còn bên kia cold.

### 9.3. Chuẩn bị workload

Tạo workload từ query distribution thực tế hoặc nhóm query có trọng số. Bao gồm query đơn giản/phức tạp, exact match, full-text, filter, range, aggregation, sort và pagination, vector/hybrid query nếu có, query không có kết quả, query có kết quả rất nhiều, tỷ lệ request lặp và request mới.

Nếu chỉ dùng một query cố định, cache có thể làm kết quả benchmark lạc quan hơn thực tế.

### 9.4. Warm-up và thời gian đo

Một quy trình benchmark:

1. Tạo index và nạp dữ liệu.
2. Chờ index ổn định/refresh theo điều kiện test.
3. Chạy warm-up để JVM, connection pool và cache đạt trạng thái ổn định.
4. Chạy workload ở concurrency mục tiêu.
5. Ghi latency distribution, throughput, error rate và tài nguyên.
6. Lặp lại nhiều lần với cùng cấu hình.
7. So sánh median và phân bố, không chỉ chọn lần chạy đẹp nhất.

Nếu cần đo cold start, chạy một bài benchmark riêng và mô tả rõ cache/index state. Không trộn cold-start result với steady-state result.

## 10. Dùng Elasticsearch Rally và công cụ đo phù hợp

Elasticsearch Rally là công cụ benchmark dành cho Elasticsearch. Rally có thể chạy track với dữ liệu và workload xác định, đo throughput, latency và các chỉ số liên quan. Nó hữu ích khi muốn so sánh cấu hình cluster, mapping, shard hoặc query workload ở cấp Elasticsearch.

Ở cấp ứng dụng, cần thêm load test qua HTTP API hoặc service layer để đo chi phí tạo query, thời gian gọi embedding, serialization/deserialization, network/client connection, response mapping và business logic.

JMH phù hợp đo các đoạn Java thuần như mapper hoặc transform dữ liệu trong JVM. Nó không thay thế benchmark Elasticsearch cluster vì không đo được shard coordination, disk, network và distributed query execution.

Không dùng một con số từ Rally để kết luận end-to-end API đã đáp ứng SLA. Hai lớp benchmark trả lời hai câu hỏi khác nhau.

## 11. Phân tích query chậm

Khi một query chậm, bắt đầu bằng cách xác định phần tốn thời gian: query execution trên shard, fetch phase/source loading, aggregation, network/coordination, client-side mapping hoặc embedding/reranking.

Elasticsearch Profile API có thể chỉ ra query component tốn thời gian. Nó thêm overhead, vì vậy dùng để chẩn đoán, không lấy profile timing làm kết quả benchmark chính.

`_explain` giúp giải thích score cho một document. Nó không phải công cụ đo throughput.

Các điểm cần xem:

- Có wildcard hoặc regexp quá rộng không?
- Có dùng script score trên quá nhiều document không?
- Filter có dùng field keyword/numeric phù hợp không?
- Có tải `_source` quá nhiều field không?
- Aggregation có cardinality rất cao không?
- `track_total_hits` có cần chính xác toàn bộ không?
- Pagination có dùng `from` quá sâu không?
- Query có fan-out tới quá nhiều shard không?

## 12. Các cách tối ưu thường gặp

Chỉ tối ưu sau khi đã xác nhận correctness và biết bottleneck.

### 12.1. Dùng filter context cho điều kiện không cần score

Các điều kiện như tenant, status, category hoặc range thường không cần đóng góp relevance score. Đưa chúng vào filter context trong bool query giúp thể hiện đúng semantics và có thể tận dụng filter cache trong điều kiện phù hợp.

Không chuyển mọi điều kiện sang filter nếu điều kiện đó cần ảnh hưởng ranking. `must`/`should` và `filter` có vai trò khác nhau.

### 12.2. Chọn đúng field type

- `text` cho full-text search.
- `keyword` cho exact match, filter, sort và aggregation.
- Numeric/date cho range và sort.
- `nested` khi cần giữ quan hệ giữa field trong cùng object array.

Dùng field type sai có thể vừa làm query chậm vừa làm kết quả sai.

### 12.3. Giảm dữ liệu trả về

Dùng source filtering hoặc DTO phù hợp để chỉ lấy field cần thiết. Nếu search result chỉ cần ID, name và thumbnail, không cần tải toàn bộ description, metadata và vector.

### 12.4. Pagination

Với trang đầu hoặc số trang nhỏ, `from`/`size` có thể đủ. Với pagination sâu, cân nhắc `search_after` và PIT. Luôn có sort ổn định và tie-breaker.

### 12.5. Bulk indexing

Bulk API giảm overhead khi index nhiều document. Chọn batch size bằng benchmark, theo dõi partial failure, retry item lỗi phù hợp và tránh batch quá lớn gây áp lực memory hoặc request timeout.

### 12.6. Refresh interval

Refresh thường xuyên giúp dữ liệu search-visible nhanh hơn nhưng có thể tăng chi phí indexing. Nếu use case chấp nhận eventual consistency, có thể điều chỉnh refresh interval trong giới hạn freshness SLA.

Không tắt refresh chỉ để benchmark ingest nếu production cần search visibility gần real-time. Benchmark phải phản ánh yêu cầu thực tế.

### 12.7. Shard và replica

Quá nhiều shard làm tăng overhead; quá ít shard có thể hạn chế khả năng phân phối tải và dung lượng. Replica tăng khả năng phục vụ search và resilience nhưng tốn storage, CPU và network cho indexing.

Không có một số shard/replica tối ưu cho mọi dataset. Đo theo shard size, query concurrency, indexing rate và tài nguyên node.

## 13. Benchmark vector search và hybrid search

Với dense vector, performance và relevance thường có trade-off rõ:

- Tăng `num_candidates` có thể tăng recall nhưng tăng latency/CPU.
- Tăng số chiều có thể tăng dung lượng và chi phí similarity.
- HNSW parameters ảnh hưởng recall, memory và indexing time.
- Reranking cải thiện thứ hạng nhưng tăng end-to-end latency.
- Chunking có thể tăng recall nhưng làm tăng số vector và duplicate hits.

Một thí nghiệm nên giữ dataset, query và phần cứng cố định, sau đó thay từng tham số:

| Experiment | Tham số thay đổi | Đo |
|---|---|---|
| A | num_candidates | Recall@10, p95, CPU |
| B | dimensions/model | NDCG@10, memory, index size |
| C | chunk size/overlap | Recall@20, duplicate rate, storage |
| D | reranker on/off | NDCG@10, end-to-end p95, cost |
| E | HNSW/index options | Recall@k, indexing time, memory |

Thay một nhóm tham số cùng lúc khiến khó biết yếu tố nào tạo ra cải thiện hoặc regression.

## 14. Đánh giá bằng baseline và thí nghiệm có kiểm soát

Không đánh giá một giải pháp trong khoảng trống. Cần baseline:

- Cách tìm kiếm đang chạy production.
- BM25 đơn giản.
- Query DSL hiện tại.
- Cấu hình mapping/index hiện tại.
- Một phương án thay thế được đề xuất.

Mỗi phương án dùng cùng bộ query, relevance labels, dataset và điều kiện tải.

### 14.1. Offline evaluation

Chạy bộ query có nhãn trên từng phương án, tính metric relevance và correctness. Ưu điểm là có thể lặp lại và so sánh nhanh trước khi triển khai.

Hạn chế: bộ query có nhãn có thể không đại diện mọi hành vi người dùng; nhãn cũng có thể lỗi thời khi catalog thay đổi.

### 14.2. Online A/B test

Khi đã qua correctness và offline evaluation, có thể chia traffic giữa baseline và phương án mới. Theo dõi click-through rate, search-to-detail conversion, add-to-cart hoặc task completion, reformulation rate, zero-result rate, latency và error rate.

Không dùng click làm relevance label tuyệt đối: vị trí hiển thị, thiết kế UI, giá và tồn kho đều ảnh hưởng hành vi click. Cần đọc kết quả cùng bối cảnh.

### 14.3. Canary rollout

Triển khai phương án mới cho một tỷ lệ nhỏ traffic hoặc một nhóm người dùng trước. Theo dõi correctness, latency, error rate và các chỉ số hành vi. Có thể tăng traffic dần nếu các ngưỡng đều đạt.

Không để thử nghiệm relevance làm lộ dữ liệu tenant hoặc bỏ qua filter bảo mật. Những điều kiện correctness bắt buộc phải giữ nguyên ở mọi nhánh A/B.

## 15. Tạo scorecard để ra quyết định

Ví dụ scorecard:

| Tiêu chí | Baseline | Candidate | Ngưỡng quyết định |
|---|---:|---:|---|
| Correctness test pass | 100% | 100% | Bắt buộc 100% cho invariant |
| NDCG@10 | 0.72 | 0.79 | Candidate không thấp hơn baseline |
| Recall@50 | 0.81 | 0.86 | Đạt mục tiêu use case |
| p95 query latency | 65 ms | 92 ms | Không vượt SLA |
| Error rate | 0.05% | 0.04% | Không tăng vượt ngưỡng |
| Index freshness p95 | 4 s | 5 s | Trong freshness SLA |
| Memory per million docs | 3.2 GB | 4.1 GB | Trong budget |

Các số trong bảng chỉ là ví dụ. Một phương án có relevance tốt hơn nhưng p95 cao hơn có thể vẫn chấp nhận được nếu còn trong SLA và cải thiện có giá trị cho người dùng. Nếu vượt ngưỡng bắt buộc, cần tối ưu hoặc chọn phương án khác.

Đừng cộng các tiêu chí thành một điểm tổng duy nhất mà không có lý do. Correctness/security thường là hard gate; relevance và performance được cân bằng theo mục tiêu sản phẩm; chi phí là giới hạn vận hành.

## 16. Phân tích regression

Khi candidate kém hơn baseline, chia theo query cohort thay vì chỉ nhìn điểm trung bình:

- Exact SKU có bị giảm không?
- Query tiếng Việt có dấu/không dấu thay đổi thế nào?
- Query dài có cải thiện nhưng query ngắn giảm không?
- Filter category hoặc tenant có làm recall giảm không?
- Document mới có được index và xuất hiện đúng không?
- Vector search có đưa kết quả không liên quan lên trước không?
- p99 có tăng do một loại aggregation cụ thể không?

Tìm các query có regression lớn nhất, xem top results và giải thích score. Sau đó xác định nguyên nhân ở analyzer, mapping, query DSL, embedding, filter, ranking, cache hoặc cluster resource.

Không điều chỉnh boost hoặc similarity chỉ để cải thiện vài query demo. Thay đổi ranking cần được đánh giá lại trên toàn bộ query set và các cohort quan trọng.

## 17. Quan sát sau khi triển khai

Evaluation không kết thúc khi deploy. Dữ liệu, hành vi người dùng và tải hệ thống thay đổi theo thời gian.

Theo dõi định kỳ:

- Query volume theo use case.
- Zero-result rate.
- Search latency p50/p95/p99.
- Error/timeout rate.
- Repeated query/reformulation rate.
- Indexing throughput và backlog.
- Projection freshness.
- Shard/node resource usage.
- Embedding failure và vector indexing errors.
- Search conversion hoặc task completion.

Đặt alert cho regression vượt ngưỡng. Khi thay mapping, analyzer, model hoặc query, lưu phiên bản cấu hình để có thể liên hệ thay đổi với metric.

## 18. Một quy trình đánh giá hoàn chỉnh

Có thể áp dụng quy trình sau cho một đề xuất thay đổi search:

1. **Mô tả use case:** xác định người dùng, query pattern và hành vi mong đợi.
2. **Định nghĩa correctness:** lập invariant cho filter, tenant, exact lookup, pagination, aggregation và freshness.
3. **Tạo dataset:** lấy dữ liệu đại diện và query thực tế, xử lý thông tin nhạy cảm.
4. **Gán relevance labels:** dùng guideline thống nhất và nhiều mức khi cần.
5. **Chạy baseline:** lưu query, result, metric và cấu hình cluster.
6. **Chạy candidate:** cùng dữ liệu và điều kiện để so sánh công bằng.
7. **Tính relevance metrics:** chọn Precision/Recall/MRR/MAP/NDCG theo use case.
8. **Benchmark performance:** đo p50/p95/p99, throughput, error rate, freshness và resource usage.
9. **Phân tích cohort:** tìm loại query hoặc dữ liệu có regression.
10. **Quyết định:** áp dụng hard gates cho correctness/security, sau đó cân bằng relevance, latency và cost.
11. **Canary/A-B:** kiểm chứng trên traffic thật với rollback plan.
12. **Theo dõi:** giữ dashboard và alert để phát hiện drift sau triển khai.

## 19. Checklist đánh giá giải pháp

**Tính đúng đắn**

- [ ] Mapping và analyzer thực tế đúng với thiết kế.
- [ ] Exact lookup, full-text, filter và range trả đúng kết quả.
- [ ] Tenant/ACL filter được áp dụng cho mọi query path.
- [ ] Sort, pagination và tie-breaker ổn định.
- [ ] Aggregation và total hits đúng theo hợp đồng.
- [ ] Delete, update và freshness có semantics rõ.
- [ ] Dữ liệu null, Unicode và format cũ được xử lý.

**Mức liên quan**

- [ ] Có query set đại diện cho người dùng thật.
- [ ] Có relevance judgments và guideline chấm điểm.
- [ ] Metric phù hợp use case đã được chọn.
- [ ] Có baseline để so sánh.
- [ ] Đã phân tích query cohort và regression.
- [ ] Hybrid/reranking được đánh giá trên cùng tập query nếu áp dụng.

**Hiệu năng**

- [ ] Dataset và cluster phản ánh quy mô production.
- [ ] Có warm-up và workload/concurrency rõ ràng.
- [ ] Đã đo p50, p95, p99, throughput và error rate.
- [ ] Đã đo indexing latency và search freshness.
- [ ] Đã theo dõi CPU, heap, GC, disk, network và shard.
- [ ] Benchmark có thể lặp lại và ghi lại cấu hình.
- [ ] Đạt SLA và budget tài nguyên.

**Triển khai**

- [ ] Có scorecard và tiêu chí release.
- [ ] Có canary/A-B khi thay đổi ranking đáng kể.
- [ ] Có dashboard và alert sau release.
- [ ] Có rollback plan nếu correctness, relevance hoặc performance regression.

## 20. Kết luận

Đánh giá một giải pháp Spring Data Elasticsearch cần tách tính đúng đắn, mức liên quan và hiệu năng thành các trục có bằng chứng riêng. Correctness bảo đảm query, mapping, filter, quyền truy cập, pagination và freshness đúng hợp đồng. Relevance đo khả năng tìm và xếp hạng tài liệu phù hợp bằng bộ query có nhãn và metric như Precision@k, Recall@k, MRR, MAP hoặc NDCG. Performance đo trải nghiệm thực tế bằng latency distribution, throughput, error rate, indexing freshness và chi phí tài nguyên.

Hãy xây baseline, dùng cùng dataset và workload, thay đổi từng yếu tố có kiểm soát rồi phân tích regression theo nhóm query. Correctness và security là điều kiện bắt buộc; relevance, latency và cost được cân bằng theo SLA và mục tiêu sản phẩm. Sau khi offline evaluation đạt yêu cầu, canary hoặc A/B test giúp xác nhận tác động trên traffic thật. Một giải pháp chỉ nên được chọn khi kết quả đúng, hữu ích với người dùng và vận hành được ở quy mô dự kiến.
