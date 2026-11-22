# Đánh giá mức liên quan bằng tập truy vấn và kết quả kỳ vọng

Một truy vấn Elasticsearch chạy thành công và trả về nhiều document chưa chứng minh rằng chức năng tìm kiếm hoạt động tốt. Người dùng quan tâm đến việc những document hữu ích có xuất hiện hay không, chúng nằm ở vị trí nào và kết quả có phù hợp với ý định của truy vấn hay không. Vì vậy, khi xây dựng chức năng tìm kiếm bằng Spring Data Elasticsearch, cần có một tập truy vấn đại diện cùng các kết quả kỳ vọng để đo chất lượng xếp hạng.

Quy trình đánh giá thường gồm:

1. Thu thập các truy vấn thực tế hoặc truy vấn đại diện cho nhu cầu người dùng.
2. Xác định những document liên quan đến từng truy vấn và mức độ liên quan của chúng.
3. Chạy cùng bộ truy vấn trên phiên bản search hiện tại và phiên bản thử nghiệm.
4. So sánh tập kết quả và thứ tự xếp hạng bằng các metric phù hợp.
5. Phân tích các truy vấn bị giảm chất lượng, điều chỉnh analyzer/query/boost rồi chạy lại.

```text
Query set                  Relevance judgments
   |                              |
   | query + filters              | query ID -> document ID -> grade
   +---------------+--------------+
                   |
                   v
           Evaluation dataset
                   |
          +--------+--------+
          |                 |
          v                 v
       Search v1          Search v2
          |                 |
          v                 v
      Ranked list        Ranked list
          |                 |
          +--------+--------+
                   |
                   v
        Precision / Recall / MRR
              MAP / NDCG
                   |
                   v
       Relevance regression report
```

## 1. Vì sao cần đánh giá relevance?

Một truy vấn có thể trả về đúng cú pháp nhưng chất lượng kém vì nhiều nguyên nhân:

- Analyzer tách token không phù hợp với ngôn ngữ hoặc dữ liệu.
- Trọng số giữa title, description và các field khác chưa hợp lý.
- Synonym làm tăng false positive.
- Filter đặt sai vị trí hoặc điều kiện bắt buộc bị đưa vào `should`.
- Boost quá cao khiến document nổi bật nhưng không liên quan vượt lên trên kết quả phù hợp.
- Sort theo ngày hoặc giá vô tình thay thế thứ tự relevance.
- Mapping hoặc dữ liệu index mới không tương thích với query cũ.

Đánh giá relevance giúp phát hiện các thay đổi này bằng dữ liệu có thể lặp lại. Thay vì chỉ nhìn một vài kết quả bằng mắt, nhóm phát triển có thể biết phiên bản mới cải thiện hay làm giảm chất lượng trên cả tập truy vấn.

Relevance và performance là hai chiều đánh giá khác nhau:

| Chiều đánh giá | Câu hỏi | Ví dụ metric |
|---|---|---|
| Relevance | Kết quả có hữu ích và được xếp đúng thứ tự không? | Precision@k, Recall@k, MRR, MAP, NDCG@k. |
| Performance | Truy vấn phản hồi nhanh và ổn định đến đâu? | p50/p95/p99 latency, throughput, error rate, CPU, heap. |
| Correctness | Điều kiện nghiệp vụ và phân quyền có được áp dụng đúng không? | Tập document thỏa filter, tenant isolation, expected IDs. |

Một thay đổi có thể tăng relevance nhưng làm query chậm hơn, hoặc giảm latency nhưng khiến kết quả kém phù hợp. Cần đo các chiều riêng biệt trước khi quyết định.

## 2. Xây dựng tập truy vấn đánh giá

Tập truy vấn đánh giá (query set hoặc benchmark set) là danh sách các truy vấn đại diện cho cách người dùng tìm kiếm. Mỗi truy vấn nên có định danh ổn định, nội dung tìm kiếm, các filter liên quan và ngữ cảnh cần thiết để tái hiện request.

Ví dụ query set cho hệ thống tìm kiếm sản phẩm:

| Query ID | Nội dung tìm kiếm | Filter | Ý định |
|---|---|---|---|
| Q001 | `mechanical keyboard` | `status=ACTIVE` | Tìm bàn phím cơ. |
| Q002 | `wireless mouse` | `category=ACCESSORIES` | Tìm chuột không dây. |
| Q003 | `SKU-KB-100` | Không có | Tra cứu mã sản phẩm chính xác. |
| Q004 | `quiet keyboard for office` | `status=ACTIVE` | Tìm sản phẩm theo nhu cầu sử dụng. |
| Q005 | `usb c hub` | `price <= 1500000` | Tìm hub USB-C trong ngân sách. |
| Q006 | `bluetooth mouse` | `brand=ACME` | Tìm sản phẩm theo thương hiệu và kết nối. |

Đây chỉ là dữ liệu minh họa. Query set thật nên xuất phát từ log tìm kiếm đã được xử lý phù hợp quyền riêng tư, phản hồi người dùng, yêu cầu sản phẩm và các truy vấn do domain expert xây dựng.

### 2.1. Bao phủ nhiều loại ý định tìm kiếm

Không nên chỉ lấy các truy vấn phổ biến nhất. Một benchmark hữu ích cần bao phủ các kiểu truy vấn khác nhau:

- **Exact lookup:** mã sản phẩm, mã đơn hàng hoặc mã định danh.
- **Full-text:** tìm theo tiêu đề, tên, mô tả hoặc nội dung dài.
- **Synonym:** từ đồng nghĩa, viết tắt và cách gọi khác nhau.
- **Typo/fuzzy:** lỗi gõ hoặc cách viết gần đúng.
- **Multi-field:** nội dung có thể xuất hiện ở title, description, category hoặc tags.
- **Filtered search:** kết hợp từ khóa với category, status, tenant, giá hoặc thời gian.
- **Long-tail:** truy vấn ít phổ biến nhưng có giá trị nghiệp vụ.
- **No-result:** truy vấn không có document phù hợp hoặc không nên trả kết quả.

Nếu benchmark chỉ chứa query phổ biến, một thay đổi có thể trông tốt trên điểm trung bình nhưng làm hỏng exact lookup, synonym hoặc các nhóm truy vấn ít gặp. Nên phân loại query theo intent để xem chất lượng theo từng nhóm.

### 2.2. Chọn truy vấn đại diện và tránh thiên lệch

Một bộ truy vấn tốt thường kết hợp:

1. Truy vấn thực tế đã được ẩn danh và loại bỏ dữ liệu cá nhân không cần thiết.
2. Truy vấn do nhóm sản phẩm/support tổng hợp từ các vấn đề thường gặp.
3. Truy vấn khó do chuyên gia domain viết để kiểm tra các trường hợp biên.
4. Truy vấn mới phát sinh sau mỗi lần phát hiện lỗi relevance.

Không nên chỉ chọn những truy vấn mà phiên bản hiện tại đã xử lý tốt. Hãy đưa cả các truy vấn đang thất bại vào benchmark để ngăn regression và đo được cải thiện thực sự.

Giữ một phần query set cố định làm regression benchmark. Có thể bổ sung một tập mới theo chu kỳ để phản ánh hành vi người dùng thay đổi, nhưng cần ghi version và ngày cập nhật để so sánh kết quả có ý nghĩa.

## 3. Relevance judgments: kết quả nào được xem là liên quan?

Với mỗi query, cần xác định document nào liên quan. Danh sách đánh giá này thường được gọi là relevance judgments hoặc qrels (query relevance judgments).

Có thể dùng nhãn nhị phân:

- `0`: không liên quan.
- `1`: liên quan.

Tuy nhiên, với nhiều hệ thống tìm kiếm, mức độ liên quan không chỉ có đúng/sai. Có thể dùng thang điểm graded relevance:

| Grade | Ý nghĩa ví dụ |
|---:|---|
| 0 | Không liên quan hoặc không đáp ứng nhu cầu. |
| 1 | Có liên quan một phần, hữu ích hạn chế. |
| 2 | Liên quan tốt, đáp ứng phần lớn ý định. |
| 3 | Rất liên quan, đáp ứng trực tiếp ý định tìm kiếm. |

Ví dụ query `mechanical keyboard`:

| Document | Nội dung | Grade |
|---|---|---:|
| P100 | Bàn phím cơ full-size | 3 |
| P101 | Bàn phím cơ compact | 3 |
| P102 | Keycap thay thế cho bàn phím cơ | 2 |
| P103 | Bàn phím màng văn phòng | 1 |
| P104 | Chuột không dây | 0 |

Thang điểm cần được định nghĩa rõ trong nhóm đánh giá. Một grade `2` ở domain sản phẩm phải có ý nghĩa nhất quán giữa người chấm và giữa các phiên bản benchmark.

### 3.1. Cách tạo judgments

Một quy trình thực tế có thể gồm:

1. Chọn query đại diện.
2. Thu thập candidate documents từ nhiều nguồn: kết quả search hiện tại, truy vấn lexical khác, truy vấn semantic hoặc danh sách do chuyên gia chọn.
3. Ẩn thông tin cho biết document đến từ hệ thống/ranking version nào nếu có thể.
4. Đưa query và candidate document cho người đánh giá theo guideline.
5. Ghi grade, lý do và người/nhóm đánh giá khi quy trình yêu cầu.
6. Giải quyết bất đồng giữa người chấm cho các query quan trọng.

Không nên chỉ gán nhãn cho top kết quả của một phiên bản search duy nhất. Nếu chỉ đánh giá những document mà hệ thống hiện tại đã trả về, benchmark có thể bỏ sót document tốt mà phiên bản mới tìm được. Cần bổ sung candidate từ các nguồn độc lập và rà soát một phần document không xuất hiện trong top hiện tại.

### 3.2. Unjudged không đồng nghĩa với irrelevant

Nếu một document không có trong qrels, điều đó có thể có nghĩa là chưa được đánh giá, không nhất thiết là không liên quan. Khi benchmark chưa đầy đủ, coi tất cả document chưa gán nhãn là grade 0 có thể làm sai lệch metric.

Nên phân biệt:

- **Judged irrelevant:** người đánh giá đã xem và cho grade 0.
- **Unjudged:** chưa có kết luận về relevance.
- **Judged relevant:** đã có grade lớn hơn ngưỡng liên quan.

Khi dùng metric hoặc công cụ đánh giá, cần xác định cách xử lý unjudged documents. Với benchmark quan trọng, hãy tăng độ bao phủ judgments trước khi dùng điểm số để ra quyết định phát hành.

## 4. Lưu query set và qrels dưới dạng dữ liệu có version

Nên lưu query set và judgments ở dạng có thể review, diff và tái sử dụng trong source control hoặc kho dữ liệu kiểm thử.

Ví dụ query set JSON:

```json
[
  {
    "id": "Q001",
    "text": "mechanical keyboard",
    "filters": {
      "status": "ACTIVE"
    },
    "intent": "product-category-search"
  },
  {
    "id": "Q002",
    "text": "wireless mouse",
    "filters": {
      "category": "ACCESSORIES"
    },
    "intent": "product-feature-search"
  }
]
```

Ví dụ qrels JSON:

```json
[
  {
    "queryId": "Q001",
    "documentId": "P100",
    "relevance": 3
  },
  {
    "queryId": "Q001",
    "documentId": "P101",
    "relevance": 3
  },
  {
    "queryId": "Q001",
    "documentId": "P102",
    "relevance": 2
  },
  {
    "queryId": "Q001",
    "documentId": "P104",
    "relevance": 0
  }
]
```

Mỗi document ID phải ổn định trong index snapshot dùng để đánh giá. Nếu reindex làm thay đổi ID, cần có cách ánh xạ ID cũ sang ID mới để qrels vẫn tham chiếu đúng document.

### 4.1. Ghi lại môi trường đánh giá

Điểm relevance chỉ có thể so sánh công bằng khi dữ liệu và cấu hình đủ tương đồng. Mỗi lần chạy benchmark nên ghi:

- Version của query set và qrels.
- Tên/version của index hoặc alias được đánh giá.
- Snapshot hoặc mốc dữ liệu dùng cho benchmark.
- Mapping và analyzer version.
- Query DSL hoặc version của search service.
- Các tham số như page size, sort, filters, boosts và similarity.
- Elasticsearch server, Spring Data Elasticsearch và Java client version.
- Thời điểm chạy và trạng thái cluster nếu đo thêm performance.

Nếu index thay đổi dữ liệu giữa hai lần chạy, metric có thể thay đổi dù query không thay đổi. Với benchmark cần tính lặp lại cao, dùng index snapshot hoặc môi trường dữ liệu cố định.

## 5. Precision@k và Recall@k

Precision và Recall là hai metric cơ bản khi đánh giá tập kết quả.

### Precision@k

Precision@k cho biết trong `k` kết quả đầu tiên, có bao nhiêu kết quả được đánh giá là liên quan:

\[
Precision@k = \frac{\text{số document liên quan trong top k}}{k}
\]

Ví dụ top 5 có 4 document liên quan:

\[
Precision@5 = \frac{4}{5} = 0.8
\]

Precision@k cao phù hợp khi người dùng chủ yếu xem một số kết quả đầu và muốn hạn chế kết quả không hữu ích.

### Recall@k

Recall@k cho biết trong tất cả document liên quan đã biết cho query, có bao nhiêu document xuất hiện trong top k:

\[
Recall@k = \frac{\text{số document liên quan trong top k}}{\text{tổng document liên quan đã được đánh giá}}
\]

Nếu qrels có 10 document liên quan và top 5 trả về 4 document trong số đó:

\[
Recall@5 = \frac{4}{10} = 0.4
\]

Recall quan trọng khi người dùng cần tìm đủ các tài liệu phù hợp, ví dụ tìm hồ sơ, tài liệu kỹ thuật hoặc các bản ghi cần rà soát.

### Precision và Recall có thể đánh đổi

Một truy vấn trả ít kết quả rất chính xác có thể có Precision cao nhưng Recall thấp. Một truy vấn trả nhiều kết quả có thể tăng Recall nhưng đưa thêm nhiều document không liên quan, làm Precision giảm.

Chọn `k` theo giao diện và hành vi người dùng. Nếu trang chỉ hiển thị 10 kết quả đầu, Precision@10 và NDCG@10 thường có ý nghĩa hơn Precision trên toàn bộ index.

## 6. Mean Reciprocal Rank (MRR)

MRR đánh giá vị trí của kết quả liên quan đầu tiên. Với một query, reciprocal rank là nghịch đảo vị trí của document liên quan đầu tiên:

\[
RR = \frac{1}{\text{rank của kết quả liên quan đầu tiên}}
\]

Nếu document liên quan đầu tiên đứng ở vị trí 1, RR = 1. Nếu đứng ở vị trí 4, RR = 0.25. Nếu không có kết quả liên quan trong phạm vi đánh giá, RR = 0.

MRR là trung bình RR trên tất cả query:

\[
MRR = \frac{1}{|Q|}\sum_{q \in Q} RR(q)
\]

Ví dụ ba query có kết quả liên quan đầu tiên ở vị trí 1, 2 và 4:

\[
MRR = \frac{1 + 0.5 + 0.25}{3} \approx 0.583
\]

MRR phù hợp với tác vụ mà người dùng thường cần tìm một kết quả đúng đầu tiên, ví dụ tra cứu một tài liệu hoặc câu trả lời. Nó không đánh giá đầy đủ chất lượng của tất cả kết quả phía sau.

## 7. Average Precision và Mean Average Precision (MAP)

Average Precision (AP) kết hợp Precision tại từng vị trí có document liên quan. Metric này đánh giá việc các kết quả liên quan được tập trung ở vị trí cao đến đâu.

Với một query có `R` document liên quan:

\[
AP = \frac{1}{R}\sum_{k=1}^{n} P@k \times rel(k)
\]

Trong đó:

- `P@k` là Precision tại vị trí k.
- `rel(k)` bằng 1 nếu document ở vị trí k được xem là liên quan, ngược lại bằng 0.
- `R` là tổng số document liên quan đã được gán nhãn cho query.

MAP là trung bình AP trên tất cả query:

\[
MAP = \frac{1}{|Q|}\sum_{q \in Q} AP(q)
\]

MAP phù hợp khi có nhiều document liên quan và muốn đánh giá việc hệ thống đưa chúng lên các vị trí cao. MAP cơ bản thường dùng relevance nhị phân; nếu cần phân biệt nhiều mức độ liên quan, NDCG phù hợp hơn.

## 8. Discounted Cumulative Gain và NDCG

Trong nhiều hệ thống, relevance có nhiều mức độ. Một document rất hữu ích nên được ưu tiên hơn document chỉ liên quan một phần. NDCG (Normalized Discounted Cumulative Gain) đánh giá thứ tự xếp hạng với graded relevance.

### DCG@k

Một công thức DCG phổ biến:

\[
DCG@k = \sum_{i=1}^{k}\frac{2^{rel_i}-1}{\log_2(i+1)}
\]

Trong đó `rel_i` là grade relevance của document ở vị trí i. Gain giảm theo vị trí vì document ở đầu danh sách có giá trị hiển thị cao hơn.

### IDCG@k

IDCG là DCG lý tưởng nếu các document được sắp theo grade relevance từ cao xuống thấp. Đây là mốc để chuẩn hóa kết quả.

### NDCG@k

\[
NDCG@k = \frac{DCG@k}{IDCG@k}
\]

NDCG thường nằm trong khoảng 0 đến 1 khi IDCG lớn hơn 0. Giá trị gần 1 nghĩa là thứ tự kết quả gần với thứ tự lý tưởng theo relevance judgments.

Ví dụ qrels cho một query:

| Document | Grade |
|---|---:|
| P100 | 3 |
| P101 | 2 |
| P102 | 1 |
| P103 | 0 |

Nếu hệ thống trả thứ tự `P100, P103, P101, P102`, grade theo thứ tự là `[3, 0, 2, 1]`. Document grade 3 đứng đầu là tốt, nhưng document grade 0 ở vị trí thứ hai làm giảm DCG so với thứ tự lý tưởng `[3, 2, 1, 0]`.

NDCG phù hợp với tìm kiếm sản phẩm, tài liệu hoặc nội dung khi người đánh giá có thể phân biệt “rất liên quan”, “có liên quan” và “ít liên quan”. Chọn `k` theo số kết quả người dùng thực sự nhìn thấy, chẳng hạn NDCG@5 hoặc NDCG@10.

## 9. Chọn metric theo mục tiêu sản phẩm

Không có một metric duy nhất phù hợp cho mọi loại tìm kiếm.

| Mục tiêu | Metric nên xem xét | Lý do |
|---|---|---|
| Người dùng cần một kết quả đúng đầu tiên | MRR | Tập trung vào vị trí kết quả liên quan đầu tiên. |
| Trang đầu cần ít kết quả không liên quan | Precision@k | Đo tỷ lệ kết quả tốt trong top-k. |
| Người dùng cần tìm đủ nhiều tài liệu liên quan | Recall@k | Đo tỷ lệ tài liệu liên quan được tìm thấy. |
| Có nhiều mức độ relevance và thứ tự quan trọng | NDCG@k | Dùng graded relevance và phạt kết quả tốt nằm quá thấp. |
| Cần đánh giá nhiều kết quả liên quan trên toàn danh sách | MAP | Đánh giá precision tại các vị trí có kết quả liên quan. |
| Cần đánh giá hệ thống đồng thời về tốc độ | Relevance metric + latency percentiles | Chất lượng và tốc độ là hai chiều riêng biệt. |

Ví dụ:

- Search box tra cứu một mã tài liệu: MRR hoặc top-1 success có thể quan trọng.
- Search tài liệu nội bộ: Recall@20 và NDCG@10 có thể hữu ích.
- Search sản phẩm thương mại: NDCG@10 kết hợp conversion hoặc click metrics có thể phản ánh tốt hơn trải nghiệm.
- Search hồ sơ cần rà soát: Recall@k có thể quan trọng vì bỏ sót document liên quan gây hậu quả lớn.

Hãy chọn metric trước khi điều chỉnh query. Nếu chỉ chọn metric sau khi nhìn kết quả, nhóm phát triển dễ vô tình tối ưu theo chỉ số có lợi cho thay đổi mình vừa thực hiện.

## 10. Ví dụ tính metric cho một query

Giả sử qrels có hai document được coi là liên quan với ngưỡng grade từ 2 trở lên:

| Document | Grade | Relevant với threshold 2? |
|---|---:|---:|
| D1 | 3 | Có |
| D2 | 1 | Không |
| D3 | 2 | Có |
| D4 | 0 | Không |

Hệ thống trả top 4 theo thứ tự `D1, D2, D3, D4`.

- Precision@3 = 2/3 ≈ 0.667.
- Recall@3 = 2/2 = 1.0.
- Reciprocal rank = 1/1 = 1.0 vì D1 là kết quả liên quan đầu tiên.
- Average Precision = `(1/1 + 2/3) / 2` ≈ 0.833.

Với NDCG, dùng grade đầy đủ `[3, 1, 2, 0]`. Thứ tự lý tưởng là `[3, 2, 1, 0]`; NDCG phản ánh việc D2 grade 1 đứng trước D3 grade 2. Một query có thể có MRR = 1 nhưng NDCG thấp hơn 1 vì MRR chỉ quan tâm kết quả liên quan đầu tiên.

Điều này cho thấy nên dùng nhiều metric bổ sung nhau. Không nên kết luận toàn bộ ranking tốt chỉ vì MRR cao.

## 11. Elasticsearch Rank Evaluation API

Elasticsearch cung cấp Rank Evaluation API (`_rank_eval`) để đánh giá query trên một tập relevance judgments. API nhận nhiều request search cùng danh sách document đã gán grade và một metric cần tính.

Ví dụ đánh giá Precision@3:

```json
POST /products/_rank_eval
{
  "requests": [
    {
      "id": "Q001",
      "request": {
        "query": {
          "match": {
            "name": "mechanical keyboard"
          }
        }
      },
      "ratings": [
        { "_index": "products", "_id": "P100", "rating": 3 },
        { "_index": "products", "_id": "P101", "rating": 3 },
        { "_index": "products", "_id": "P102", "rating": 2 },
        { "_index": "products", "_id": "P104", "rating": 0 }
      ]
    }
  ],
  "metric": {
    "precision": {
      "k": 3,
      "relevant_rating_threshold": 2
    }
  }
}
```

Trong request:

- `id` định danh truy vấn trong benchmark.
- `request` chứa phần search request được đánh giá.
- `ratings` gắn document ID với grade relevance.
- `metric` xác định công thức đánh giá và các tham số liên quan.

API trả metric tổng hợp và chi tiết theo từng query. Có thể dùng endpoint này để đánh giá nhiều query trong cùng một lần gọi.

### Đánh giá MRR hoặc NDCG

Metric có thể đổi tùy mục tiêu. Ví dụ cấu hình MRR:

```json
POST /products/_rank_eval
{
  "requests": [
    {
      "id": "Q001",
      "request": {
        "query": {
          "match": {
            "name": "mechanical keyboard"
          }
        }
      },
      "ratings": [
        { "_index": "products", "_id": "P100", "rating": 3 },
        { "_index": "products", "_id": "P101", "rating": 3 },
        { "_index": "products", "_id": "P102", "rating": 2 },
        { "_index": "products", "_id": "P104", "rating": 0 }
      ]
    }
  ],
  "metric": {
    "mean_reciprocal_rank": {
      "k": 10,
      "relevant_rating_threshold": 2
    }
  }
}
```

Ví dụ NDCG:

```json
POST /products/_rank_eval
{
  "requests": [
    {
      "id": "Q001",
      "request": {
        "query": {
          "match": {
            "name": "mechanical keyboard"
          }
        }
      },
      "ratings": [
        { "_index": "products", "_id": "P100", "rating": 3 },
        { "_index": "products", "_id": "P101", "rating": 3 },
        { "_index": "products", "_id": "P102", "rating": 2 },
        { "_index": "products", "_id": "P104", "rating": 0 }
      ]
    }
  ],
  "metric": {
    "dcg": {
      "k": 10,
      "normalize": true
    }
  }
}
```

Tên metric và tùy chọn cụ thể cần đối chiếu với phiên bản Elasticsearch đang chạy. Rank Evaluation API hỗ trợ các metric như precision, recall, mean reciprocal rank, discounted cumulative gain và expected reciprocal rank ở các phiên bản tương ứng.

### Giới hạn của Rank Evaluation API

- API đánh giá query và judgments đã cung cấp; nó không tự tạo relevance labels.
- Qrels không đầy đủ có thể làm metric sai lệch.
- Query phải phản ánh đúng request production, bao gồm filter, sort và các tham số cần đánh giá.
- Cần cố định index/data snapshot khi so sánh các phiên bản.
- Rank evaluation có chi phí thực thi search nhiều lần; không nên gọi trên mỗi request người dùng.

## 12. Tích hợp đánh giá vào dự án Spring Data Elasticsearch

Spring Data Elasticsearch thường thực hiện search qua `ElasticsearchOperations`, repository hoặc Java API Client. Có thể xây dựng một integration-test harness để chạy query set, lấy danh sách ID theo thứ tự và so sánh với judgments.

### Mô hình dữ liệu kiểm thử

Ví dụ record Java:

```java
public record SearchCase(
        String id,
        String text,
        Map<String, String> filters,
        String intent
) {}

public record RelevanceJudgment(
        String queryId,
        String documentId,
        int grade
) {}
```

Query set và qrels có thể được lưu trong `src/test/resources/search-evaluation/` dưới dạng JSON/CSV. Test đọc các file này để chạy benchmark.

### Chạy một truy vấn qua ElasticsearchOperations

Ví dụ service tìm sản phẩm:

```java
public SearchHits<ProductDocument> search(String text, String status) {
    Query queryDsl = Query.of(q -> q
            .bool(b -> b
                    .must(m -> m.match(mm -> mm
                            .field("name")
                            .query(text)
                    ))
                    .filter(f -> f.term(t -> t
                            .field("status")
                            .value(FieldValue.of(status))
                    ))
            )
    );

    NativeQuery query = NativeQuery.builder()
            .withQuery(queryDsl)
            .withPageable(PageRequest.of(0, 20))
            .build();

    return operations.search(query, ProductDocument.class);
}
```

Harness có thể gọi service cho từng `SearchCase`, sau đó lấy thứ tự document ID từ `SearchHit.getId()` hoặc entity ID và tính metric ở phía test.

### Tính Precision@k trong test

Ví dụ hàm tính Precision@k với relevance nhị phân:

```java
static double precisionAtK(
        List<String> rankedIds,
        Set<String> relevantIds,
        int k) {

    if (k <= 0) {
        throw new IllegalArgumentException("k must be positive");
    }

    long relevantInTopK = rankedIds.stream()
            .limit(k)
            .filter(relevantIds::contains)
            .count();

    return (double) relevantInTopK / k;
}
```

Nếu số kết quả thực tế ít hơn `k`, công thức Precision@k vẫn thường dùng mẫu số `k` để phản ánh các vị trí không có kết quả. Một số benchmark có thể chọn quy ước khác; cần ghi rõ quy ước để so sánh nhất quán.

### Tính Recall@k

```java
static double recallAtK(
        List<String> rankedIds,
        Set<String> relevantIds,
        int k) {

    if (relevantIds.isEmpty()) {
        return 0.0;
    }

    long relevantInTopK = rankedIds.stream()
            .limit(k)
            .filter(relevantIds::contains)
            .count();

    return (double) relevantInTopK / relevantIds.size();
}
```

Trong thực tế, nên phân biệt query không có document liên quan với query thiếu judgments. Không đưa query có qrels rỗng vào phép tính trung bình một cách tùy tiện; quy ước loại trừ hoặc tính điểm 0 phải được ghi rõ.

### Tính MRR

```java
static double reciprocalRank(
        List<String> rankedIds,
        Set<String> relevantIds) {

    for (int i = 0; i < rankedIds.size(); i++) {
        if (relevantIds.contains(rankedIds.get(i))) {
            return 1.0 / (i + 1);
        }
    }

    return 0.0;
}
```

Sau khi tính reciprocal rank cho từng query, lấy trung bình để có MRR. Với graded relevance, phải chọn threshold để xác định grade nào được coi là relevant.

### Tính NDCG với graded relevance

```java
static double dcgAtK(List<Integer> grades, int k) {
    double dcg = 0.0;

    for (int i = 0; i < Math.min(k, grades.size()); i++) {
        int grade = grades.get(i);
        double gain = Math.pow(2.0, grade) - 1.0;
        double discount = Math.log(i + 2.0) / Math.log(2.0);
        dcg += gain / discount;
    }

    return dcg;
}

static double ndcgAtK(
        List<Integer> rankedGrades,
        List<Integer> allJudgedGrades,
        int k) {
    double dcg = dcgAtK(rankedGrades, k);

    List<Integer> idealGrades = allJudgedGrades.stream()
            .sorted(Comparator.reverseOrder())
            .toList();

    double idcg = dcgAtK(idealGrades, k);
    return idcg == 0.0 ? 0.0 : dcg / idcg;
}
```

Trong harness thực tế, truyền `rankedGrades` theo thứ tự kết quả search và `allJudgedGrades` từ **toàn bộ judgments của query**. Không tạo IDCG chỉ từ các document search đã trả về, vì như vậy sẽ bỏ qua các document liên quan mà hệ thống chưa tìm thấy.

## 13. Ví dụ cấu trúc một relevance regression test

Một test có thể tổ chức như sau:

```java
@SpringBootTest
class ProductSearchRelevanceTest {

    @Autowired
    private ProductSearchService searchService;

    @Test
    void benchmarkQueriesShouldMeetRelevanceThresholds() {
        // 1. Nạp dữ liệu fixture vào index test.
        // 2. Đọc query set và relevance judgments.
        // 3. Chạy từng query bằng searchService.
        // 4. Lấy document IDs theo đúng thứ tự trả về.
        // 5. Tính NDCG@10, MRR hoặc Precision@k.
        // 6. So sánh với ngưỡng baseline đã thống nhất.
    }
}
```

Test nên chạy trên Elasticsearch thật hoặc Testcontainers với phiên bản tương thích. Mock `ElasticsearchOperations` phù hợp để kiểm tra cách service xây dựng tham số, nhưng không thể xác nhận analyzer, Query DSL, relevance scoring và thứ tự kết quả thực tế của Elasticsearch.

Nếu dùng Testcontainers:

- Cố định phiên bản Elasticsearch cho test để kết quả có thể lặp lại.
- Tạo index và mapping từ fixture hoặc migration tương ứng.
- Index dữ liệu trước khi chạy benchmark.
- Refresh index rõ ràng trước search; không dựa vào `Thread.sleep`.
- Xóa/recreate index giữa các test khi cần cô lập dữ liệu.
- Không dùng dữ liệu production nhạy cảm trực tiếp trong test fixture.

## 14. So sánh baseline và phiên bản query mới

Giả sử nhóm phát triển thay analyzer hoặc điều chỉnh boost. Cần chạy cùng query set và qrels trên hai phiên bản:

| Metric | Baseline | Candidate | Thay đổi |
|---|---:|---:|---:|
| Precision@10 | 0.78 | 0.82 | +0.04 |
| Recall@10 | 0.61 | 0.59 | -0.02 |
| MRR | 0.74 | 0.80 | +0.06 |
| NDCG@10 | 0.76 | 0.81 | +0.05 |
| p95 latency | 85 ms | 112 ms | +27 ms |

Các con số trên chỉ minh họa cách báo cáo. Candidate có thể cải thiện xếp hạng đầu nhưng giảm Recall@10 và tăng latency. Quyết định phát hành phụ thuộc mục tiêu sản phẩm, mức độ quan trọng của Recall và ngân sách latency.

Không nên chỉ nhìn điểm trung bình toàn bộ query. Hãy so sánh theo nhóm intent:

| Nhóm query | Precision@10 delta | NDCG@10 delta | p95 delta |
|---|---:|---:|---:|
| Exact lookup | +0.01 | +0.00 | +5 ms |
| Full-text | +0.06 | +0.08 | +20 ms |
| Synonym | -0.04 | -0.06 | +18 ms |
| Filtered search | +0.03 | +0.02 | +10 ms |

Ví dụ này cho thấy điểm tổng thể có thể che giấu regression ở nhóm synonym. Cần kiểm tra query cụ thể bị giảm chất lượng trước khi kết luận candidate tốt hơn.

## 15. Phân tích lỗi bằng từng query

Khi metric giảm, hãy mở danh sách query bị ảnh hưởng và so sánh ranked list cũ/mới:

| Vị trí | Baseline | Grade | Candidate | Grade |
|---:|---|---:|---|---:|
| 1 | P100 | 3 | P104 | 0 |
| 2 | P101 | 3 | P100 | 3 |
| 3 | P102 | 2 | P101 | 3 |
| 4 | P104 | 0 | P102 | 2 |

Candidate vẫn trả đủ document liên quan, nhưng một document không liên quan đã lên vị trí đầu. NDCG và Precision ở top 1 giảm dù Recall toàn bộ có thể không đổi.

Các bước chẩn đoán:

1. Kiểm tra query DSL thực tế được gửi.
2. Kiểm tra analyzer bằng `_analyze` cho cả nội dung index và query.
3. Dùng Explain API cho document được xếp quá cao hoặc quá thấp.
4. Kiểm tra mapping, synonym, boost và filter.
5. Xác định lỗi thuộc dữ liệu, query, analyzer hay judgments.
6. Thêm trường hợp lỗi vào regression set sau khi xác nhận expected relevance.

Không nên điều chỉnh boost chỉ để làm một query đơn lẻ có kết quả như ý nếu điều đó làm hỏng nhiều query khác. Hãy tìm nguyên nhân có tính hệ thống và đánh giá lại toàn benchmark.

## 16. Đánh giá offline và online

### Offline evaluation

Offline evaluation chạy query set và qrels trên một index snapshot, không cần đưa thay đổi đến người dùng. Ưu điểm:

- Có thể chạy lặp lại trong CI hoặc trước khi release.
- So sánh các analyzer, query DSL và boost theo cùng dữ liệu.
- Phát hiện regression sớm.
- Không ảnh hưởng trải nghiệm người dùng production.

Hạn chế là judgments có thể không bao phủ hết ý định thực tế, dữ liệu benchmark có thể cũ và metric offline không phản ánh đầy đủ hành vi người dùng.

### Online evaluation

Online evaluation quan sát hành vi thực tế hoặc thử nghiệm hai phiên bản trên traffic được kiểm soát. Các chỉ số có thể gồm:

- Click-through rate (CTR) theo vị trí và loại truy vấn.
- Tỷ lệ truy vấn không có click.
- Tỷ lệ người dùng sửa query hoặc tìm lại ngay sau đó.
- Conversion hoặc hành động hoàn tất nếu phù hợp nghiệp vụ.
- Thời gian hoàn tất tác vụ tìm kiếm.
- p95/p99 latency và error rate.

Click không phải lúc nào cũng đồng nghĩa relevance. Một document có thể được click do tiêu đề hấp dẫn nhưng không giải quyết được nhu cầu; một kết quả tốt có thể không cần click nếu snippet đã trả lời câu hỏi. Online metric cần được diễn giải cùng mục tiêu sản phẩm và dữ liệu đánh giá chuyên gia.

### A/B test

Khi thay đổi ảnh hưởng lớn đến trải nghiệm, có thể chạy A/B test:

1. Chia traffic ngẫu nhiên thành nhóm baseline và candidate.
2. Giữ cách phân chia ổn định trong suốt thí nghiệm.
3. Đặt metric chính và guardrail trước khi bắt đầu.
4. Theo dõi đủ thời gian và lượng traffic để giảm ảnh hưởng biến động ngẫu nhiên.
5. Kiểm tra các phân khúc query/tenant/device để phát hiện tác động không đồng đều.
6. Chỉ rollout rộng khi kết quả và guardrail đáp ứng tiêu chí đã thống nhất.

Không chạy A/B test nếu hai nhóm nhận dữ liệu hoặc cấu hình không tương đương mà không ghi nhận khác biệt đó. Với search, việc phân phối index, cache và personalization cũng có thể tạo bias nếu không được kiểm soát.

## 17. Những sai lầm thường gặp khi đánh giá relevance

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ đánh giá một vài query thủ công | Không phát hiện regression ở nhóm truy vấn khác. | Xây dựng query set đại diện và phân nhóm intent. |
| Không có qrels hoặc expected results | Không có cơ sở khách quan để đo relevance. | Gán nhãn document theo query với guideline rõ ràng. |
| Coi mọi document chưa đánh giá là irrelevant | Precision/Recall có thể bị sai lệch. | Phân biệt unjudged với judged irrelevant và tăng coverage. |
| Chỉ lấy candidate từ phiên bản hiện tại | Bỏ sót document tốt mà phiên bản mới có thể tìm thấy. | Tạo pool candidate từ nhiều nguồn/ranker. |
| Chỉ dùng một metric | Có thể tối ưu một chiều và làm hỏng chiều khác. | Kết hợp metric phù hợp như NDCG, MRR, Precision và Recall. |
| So sánh trên dữ liệu index khác nhau | Không biết metric đổi do query hay do corpus. | Cố định snapshot hoặc ghi rõ data version. |
| Chỉ xem điểm trung bình | Che giấu nhóm query bị giảm chất lượng. | Báo cáo theo intent, locale, tenant và mức độ phổ biến. |
| Dùng click làm ground truth tuyệt đối | Click bị ảnh hưởng bởi vị trí, giao diện và nội dung hiển thị. | Kết hợp judgments, click signals và thí nghiệm có kiểm soát. |
| Chạy Rank Eval API trên mọi request | Tăng chi phí và độ trễ không cần thiết. | Chạy offline trong benchmark/test pipeline. |
| Đặt threshold sau khi đã xem kết quả | Dễ chọn tiêu chí có lợi cho candidate. | Xác định metric và ngưỡng trước khi đánh giá. |

## 18. Quy trình relevance regression cho Spring Data Elasticsearch

Một quy trình có thể đưa vào vòng đời phát triển:

1. **Tạo baseline:** lưu query set, qrels, index snapshot và metric hiện tại.
2. **Thay đổi search:** chỉnh analyzer, mapping, CriteriaQuery, NativeQuery, boost hoặc sort.
3. **Tạo index thử nghiệm:** dùng cùng dữ liệu và mapping/version đã định nghĩa.
4. **Chạy query set:** gọi cùng search service hoặc Rank Evaluation API.
5. **Tính metric:** Precision@k, Recall@k, MRR, MAP hoặc NDCG@k theo mục tiêu.
6. **So sánh baseline:** xem metric tổng thể và theo từng intent.
7. **Điều tra regression:** so sánh ranked list, `_score`, Explain API và analyzer tokens.
8. **Cập nhật qrels có kiểm soát:** chỉ thêm nhãn sau khi có đánh giá, không tự coi kết quả candidate là expected.
9. **Lưu báo cáo:** ghi query version, index version, metric, thời điểm và thay đổi search.
10. **Đưa vào CI/release gate:** chỉ chặn release theo ngưỡng đã thống nhất và có cơ chế xem xét các trường hợp ngoại lệ.

Một release gate có thể yêu cầu NDCG@10 không giảm quá một ngưỡng nhất định, không có nhóm query quan trọng bị regression nghiêm trọng và p95 latency vẫn trong ngân sách. Ngưỡng cụ thể phải dựa trên mục tiêu sản phẩm và dữ liệu thực tế, không có một con số chung cho mọi hệ thống.

## 19. Gợi ý cấu trúc thư mục benchmark

Có thể tổ chức dữ liệu kiểm thử như sau:

```text
src/test/resources/search-evaluation/
  product-search-v1/
    queries.json
    qrels.json
    README.md
  article-search-v1/
    queries.json
    qrels.json
    README.md
```

`README.md` của từng bộ nên ghi:

- Mục đích và phạm vi query set.
- Định nghĩa grade relevance.
- Nguồn dữ liệu và cách ẩn danh.
- Ngày/version judgments.
- Metric chính và metric guardrail.
- Các query có ngoại lệ hoặc cần diễn giải riêng.

Không đưa thông tin cá nhân hoặc dữ liệu production nhạy cảm vào fixture nếu không cần thiết. Nếu cần tái hiện query thực tế, hãy ẩn danh và giữ nguyên cấu trúc cần thiết cho việc đánh giá.

## 20. Những điểm cần nhớ

- Đánh giá relevance cần query set đại diện và relevance judgments cho từng query.
- Relevance judgments có thể dùng nhãn nhị phân hoặc graded relevance; phải có guideline nhất quán.
- Unjudged document không mặc nhiên là irrelevant.
- Precision@k đo độ chính xác trong top-k; Recall@k đo tỷ lệ document liên quan được tìm thấy.
- MRR tập trung vào vị trí kết quả liên quan đầu tiên; MAP đánh giá các vị trí liên quan; NDCG hỗ trợ graded relevance và thứ tự xếp hạng.
- Chọn metric theo mục tiêu sản phẩm, không tối ưu chỉ một con số.
- Elasticsearch Rank Evaluation API (`_rank_eval`) có thể chạy query trên tập ratings đã gán.
- Spring Data có thể chạy benchmark qua `ElasticsearchOperations`, Repository hoặc Java API Client; mock không xác nhận được relevance scoring thực tế.
- Cần cố định query set, qrels, index snapshot, mapping/analyzer version và cấu hình khi so sánh.
- Offline evaluation phù hợp cho regression; online evaluation và A/B test bổ sung bằng chứng từ hành vi thực tế.
- Báo cáo theo nhóm intent để tránh điểm trung bình che giấu regression.
- Tách relevance khỏi latency/performance và correctness; cần theo dõi cả ba chiều.

Đánh giá mức liên quan bằng tập truy vấn và kết quả kỳ vọng biến chất lượng tìm kiếm thành thứ có thể đo, so sánh và cải thiện qua từng lần thay đổi. Khi xây dựng Spring Data Elasticsearch, hãy duy trì query set và qrels có version, chọn metric phù hợp với trải nghiệm người dùng, rồi đưa relevance regression vào quy trình kiểm thử trước khi phát hành.
