# Đánh giá chất lượng tìm kiếm và ranh giới với công cụ tìm kiếm riêng trong PostgreSQL

## 1. Tình huống: kết quả tìm kiếm “nhanh” nhưng người dùng không tìm được thứ họ cần

Một ứng dụng thương mại có kho sản phẩm, hướng dẫn sử dụng và bài viết hỗ trợ. Nhóm phát triển dùng PostgreSQL làm cơ sở dữ liệu chính, đồng thời triển khai chức năng tìm kiếm bằng Full Text Search (FTS).

Người dùng gõ:

```text
cà phê pha phin
```

Hệ thống trả về mười tài liệu trong 25 ms. Nhưng ba kết quả đầu là các bài có nhắc đến “cà phê” ở phần ghi chú phụ; bài hướng dẫn pha phin chuẩn bị ở vị trí thứ tám. Từ góc nhìn database, query không chậm. Từ góc nhìn người dùng, **tìm kiếm chưa tốt**.

Một yêu cầu khác:

```text
ca phe phin
```

không có dấu tiếng Việt; hệ thống dùng token so khớp có dấu và trả “Không có kết quả”. Thêm một truy vấn:

```text
bảo hành máy xay
```

lại đưa những sản phẩm hết hạn bảo hành lên đầu, mặc dù người dùng đang tìm chính sách hỗ trợ.

Những ví dụ này cho thấy chất lượng tìm kiếm gồm **nhiều chiều**:

- **Đúng:** tài liệu liên quan đến ý định người dùng.
- **Xếp hạng tốt:** tài liệu hữu ích nhất xuất hiện sớm.
- **Bao phủ:** truy vấn hợp lệ không bị bỏ trống do cách tách từ, dấu hoặc biến thể cách viết.
- **An toàn:** không trả tài liệu sai tenant, sai quyền, chưa công bố hoặc đã xóa.
- **Cập nhật:** dữ liệu và quyền trong kết quả phản ánh nguồn sự thật với độ trễ chấp nhận được.
- **Hiệu năng:** p95/p99 latency, tải CPU/I/O và throughput đáp ứng SLO.
- **Vận hành:** chỉ mục, đồng bộ, giám sát, khôi phục và chi phí vẫn nằm trong khả năng đội ngũ.

> Bài học quan trọng: **không nên quyết định “PostgreSQL hay công cụ tìm kiếm riêng” chỉ từ một query EXPLAIN, số lượng bản ghi hoặc một câu trả lời nhanh/chậm.** Trước tiên phải định nghĩa chất lượng và đo nó theo workload thật.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xây dựng bộ truy vấn đánh giá có **mức độ liên quan đã gán nhãn** (*relevance judgments/qrels*).
2. Hiểu và sử dụng Precision@k, Recall@k, Success@k, MRR, MAP, NDCG@k và tỷ lệ không có kết quả.
3. Phân biệt chất lượng **truy xuất ứng viên** với chất lượng **xếp hạng**.
4. Thiết kế kiểm thử có phân đoạn theo loại truy vấn, ngôn ngữ, tenant và mức độ phổ biến.
5. Áp dụng `tsvector`, `tsquery`, `@@`, `ts_rank`, `ts_rank_cd`, GIN và `pg_trgm` trong PostgreSQL khi phù hợp.
6. Nhận biết giới hạn xử lý tiếng Việt, dấu, lỗi chính tả, từ đồng nghĩa, cụm từ và ngữ nghĩa.
7. Đọc `EXPLAIN (ANALYZE, BUFFERS)` và đo thời gian thực thi theo p50/p95/p99.
8. Đánh giá khi nào PostgreSQL FTS là đủ và khi nào một search engine riêng đem lại giá trị.
9. Thiết kế đồng bộ từ PostgreSQL **source of truth** sang search index có xử lý create/update/delete, replay, rebuild và quyền truy cập.
10. Hiểu khác biệt giữa full-text lexical search, trigram fuzzy matching và vector/semantic search.
11. Tổ chức quy trình offline evaluation, A/B testing, rollout và rollback mà không hi sinh tính đúng nghiệp vụ.

---

## 2. “Chất lượng tìm kiếm” là một hợp đồng sản phẩm

Trước khi đo, cần trả lời:

- **Người dùng là ai?** Khách hàng, nhân viên hỗ trợ, quản trị viên hay hệ thống nội bộ?
- **Họ muốn tìm gì?** Sản phẩm đúng mã, tài liệu hướng dẫn, chính sách, một câu trả lời ngữ nghĩa hay tất cả hồ sơ khớp?
- **Thế nào là kết quả tốt?** Tìm đúng bản ghi duy nhất, một vài gợi ý hữu ích hay bao phủ đầy đủ hàng nghìn văn bản?
- **Các tài liệu nào được phép hiển thị?** Tenant, nhóm quyền, trạng thái công bố, vùng địa lý, thời hạn dữ liệu.
- **Cần mới đến mức nào?** Sau cập nhật ngay lập tức, vài giây hay vài phút?
- **Khi thiếu kết quả thì sao?** Gợi ý sửa lỗi, dùng từ đồng nghĩa, chuyển truy vấn sang cú pháp khác, hoặc trả “không có”.

Nếu là ô tìm mã đơn:

```text
ORD-2026-000123
```

thì chất lượng chủ yếu là **exactness và correctness**: phải tìm đúng đơn, không trả đơn “gần giống” thuộc tenant khác. B-tree trên mã đơn có thể tốt hơn mọi hệ thống xếp hạng fuzzy phức tạp.

Nếu là ô tìm tài liệu:

```text
làm sao khôi phục mật khẩu khi mất số điện thoại
```

thì người dùng cần **tài liệu giải quyết vấn đề**, dù tiêu đề không chứa đúng mọi từ họ đã gõ. Bài toán có thêm ngữ nghĩa, từ đồng nghĩa, ý định và xếp hạng.

### 2.1. Phân loại ý định truy vấn

| Loại | Ví dụ | Mục tiêu chính |
|---|---|---|
| Exact ID | `ORD-12345` | Đúng một bản ghi theo quyền |
| Navigational | `chính sách đổi trả` | Đúng trang/bài chính thức ở đầu |
| Product lookup | `máy pha cà phê` | Sản phẩm đúng loại, còn hiển thị |
| Informational | `cách vệ sinh máy xay` | Nội dung giải quyết câu hỏi |
| Exploratory | `quà tặng dưới 500k` | Kết hợp từ khóa và bộ lọc |
| Typo | `may pha cafe` | Chấp nhận lỗi gõ/không dấu phù hợp |
| Multi-language | `coffee grinder` | Phục vụ ngôn ngữ/từ vựng khác |
| No-answer | `sản phẩm không tồn tại` | Không bịa kết quả sai |
| Restricted | `hồ sơ nội bộ của tenant khác` | Tuyệt đối không lộ dữ liệu |

Không nên gộp tất cả query vào một chỉ số chung rồi bỏ qua việc phân khúc này.

## 3. Những khái niệm cốt lõi: candidate, relevance, ranking

Một hệ thống tìm kiếm thường có ít nhất hai tầng logic:

```text
Truy vấn người dùng
       |
       v
Phân tích/tạo tsquery, token, sửa lỗi gõ...
       |
       v
Candidate retrieval
  (lấy các tài liệu có khả năng liên quan)
       |
       v
Filtering theo tenant, quyền và trạng thái
       |
       v
Ranking
  (chấm điểm và sắp thứ tự)
       |
       v
Top-k kết quả, snippet, highlight
       |
       v
Tương tác của người dùng
```

**Retrieval** quyết định tài liệu nào có cơ hội xuất hiện. **Ranking** quyết định thứ tự những tài liệu ấy.

Nếu tài liệu thực sự liên quan **không được retrieval trả về**, thay công thức `ORDER BY ts_rank(...)` không thể đưa nó lên đầu. Ngược lại, nếu tài liệu liên quan đã nằm trong candidate set nhưng xếp ở vị trí 50, cần cải thiện ranking.

### 3.1. Relevance khác lexical overlap

Một tài liệu chứa ba lần từ “bảo hành” chưa chắc hữu ích hơn trang “Quy trình yêu cầu sửa chữa sau mua” đối với truy vấn hỏi cách gửi bảo hành.

Sự liên quan thường bao gồm:

- Khớp chủ đề.
- Khớp ý định.
- Mức độ giải quyết nhu cầu.
- Tính chính xác của thông tin.
- Tính mới/hợp lệ.
- Loại tài liệu người dùng đang tìm.
- Điều kiện bộ lọc (giá, trạng thái, tenant, quyền).

### 3.2. Ranking không thay hard filter

Nếu hàng có `is_published = false` hoặc sai `tenant_id`, không thể giải quyết bằng cách “trừ thật nhiều điểm”. Nó phải được **loại khỏi tập ứng viên hợp lệ** theo quy tắc truy cập.

Cấu trúc:

```sql
WHERE tenant_id = ...
  AND is_published = true
  AND search_vector @@ query
```

an toàn về ý tưởng hơn cách lấy cả dữ liệu cấm rồi chỉ giảm điểm trong xếp hạng.

## 4. PostgreSQL Full Text Search làm được gì?

PostgreSQL có những cấu phần:

| Cấu phần | Vai trò |
|---|---|
| `to_tsvector(config, text)` | Chuyển văn bản thành lexemes theo text search configuration |
| `plainto_tsquery` | Tạo tsquery từ văn bản đầu vào đơn giản |
| `phraseto_tsquery` | Tạo tsquery giữ quan hệ thứ tự/khoảng cách token phù hợp |
| `websearch_to_tsquery` | Cú pháp truy vấn gần cách nhập web search, thuận tiện cho input người dùng |
| `@@` | Kiểm tra tsvector có match tsquery không |
| `ts_rank` | Điểm relevance dựa trên thống kê lexeme/weight theo hàm |
| `ts_rank_cd` | Cover-density ranking, nhạy với vị trí/gần nhau khi có positional data |
| `setweight` | Gán mức trọng số A/B/C/D cho các phần của tài liệu |
| `ts_headline` | Tạo trích đoạn/highlight từ nội dung |
| `GIN(search_vector)` | Tăng tốc truy xuất ứng viên cho nhiều loại tsquery |

FTS là lựa chọn tốt cho nhiều ứng dụng nội bộ, knowledge base vừa phải, catalog có yêu cầu text matching rõ, hoặc hệ thống đã có PostgreSQL và không cần một search cluster độc lập.

Nhưng cần phân biệt: **PostgreSQL hỗ trợ FTS tốt không đồng nghĩa tự có sẵn mọi tính năng sản phẩm của search engine chuyên dụng**, ví dụ hệ thống quản trị synonyms đa ngôn ngữ, typo-tolerant autocomplete, aggregations/facets lớn, truy vấn phân tán quy mô lớn hoặc mô hình hybrid ranking hoàn chỉnh.

## 5. Lab: tạo tập tài liệu để đánh giá

Các lệnh sau chỉ dành cho database học tập. Không chạy trên dữ liệu production.

### 5.1. Tạo schema và bảng

```sql
CREATE SCHEMA IF NOT EXISTS search330;

CREATE TABLE search330.documents (
    document_id integer PRIMARY KEY,
    tenant_id integer NOT NULL,
    title text NOT NULL,
    body text NOT NULL,
    category text NOT NULL,
    language_code text NOT NULL DEFAULT 'vi',
    is_published boolean NOT NULL DEFAULT true,
    published_at timestamptz NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(
            to_tsvector('pg_catalog.simple'::regconfig, coalesce(title, '')),
            'A'
        )
        ||
        setweight(
            to_tsvector('pg_catalog.simple'::regconfig, coalesce(body, '')),
            'B'
        )
    ) STORED
);
```

Dùng cấu hình `simple` để tập trung vào bài **đo chất lượng**. Nó không phải một bộ tách từ/ngôn ngữ tiếng Việt chuyên dụng. Với tiếng Việt, cách chia âm tiết theo khoảng trắng, dấu và từ ghép ảnh hưởng mạnh đến relevance.

`GENERATED ... STORED` giữ `search_vector` đồng bộ theo title/body khi PostgreSQL ghi thay đổi lên bảng. Hàm `to_tsvector` có config cụ thể và các hàm dùng trong generated expression phải đáp ứng yêu cầu immutability của PostgreSQL.

### 5.2. Thêm dữ liệu mẫu

```sql
INSERT INTO search330.documents(
    document_id, tenant_id, title, body, category,
    language_code, is_published, published_at
)
VALUES
(101, 7, 'Hướng dẫn pha cà phê phin',
 'Các bước chọn cà phê, ủ bột và pha phin tại nhà.',
 'guide', 'vi', true, '2026-08-10 00:00+00'),

(102, 7, 'Cách vệ sinh phin cà phê',
 'Làm sạch dụng cụ pha phin và giữ hương vị cà phê.',
 'guide', 'vi', true, '2026-08-20 00:00+00'),

(103, 7, 'Cà phê hạt rang mộc',
 'Giới thiệu loại hạt cà phê và mức rang phù hợp.',
 'product', 'vi', true, '2026-08-15 00:00+00'),

(104, 7, 'Máy xay cà phê mini',
 'Máy xay dùng cho cà phê phin và pha máy.',
 'product', 'vi', true, '2026-08-14 00:00+00'),

(105, 7, 'Quy định bảo hành máy xay',
 'Điều kiện bảo hành, thời gian và cách gửi yêu cầu sửa chữa.',
 'policy', 'vi', true, '2026-09-01 00:00+00'),

(106, 7, 'Câu hỏi thường gặp về đổi trả',
 'Quy trình đổi trả sản phẩm và hoàn tiền.',
 'policy', 'vi', true, '2026-08-08 00:00+00'),

(107, 7, 'Cách chọn phin và cà phê',
 'Lựa chọn phin theo khẩu vị, kích thước và cách pha.',
 'guide', 'vi', true, '2026-08-12 00:00+00'),

(108, 7, 'Cà phê pha lạnh',
 'Cách ủ cold brew và bảo quản nước cà phê.',
 'guide', 'vi', true, '2026-08-05 00:00+00'),

(109, 7, 'Mẹo xay cà phê',
 'Điều chỉnh độ mịn cho phin, espresso và pour over.',
 'guide', 'vi', true, '2026-08-11 00:00+00'),

(110, 7, 'Máy pha cà phê tự động',
 'Hướng dẫn sử dụng và làm sạch máy pha cà phê.',
 'product', 'vi', true, '2026-09-10 00:00+00'),

(111, 7, 'Bảo hành và sửa máy pha',
 'Liên hệ trung tâm hỗ trợ để bảo hành máy pha.',
 'policy', 'vi', true, '2026-09-20 00:00+00'),

(112, 7, 'Hỗ trợ lấy lại mật khẩu',
 'Khôi phục quyền truy cập tài khoản bằng email.',
 'support', 'vi', true, '2026-10-01 00:00+00'),

(113, 7, 'Bản nháp chính sách bảo hành',
 'Dự thảo chưa công bố về điều kiện bảo hành.',
 'policy', 'vi', false, '2026-10-03 00:00+00'),

(114, 8, 'Tài liệu máy xay của tenant khác',
 'Hướng dẫn nội bộ cho tenant 8.',
 'guide', 'vi', true, '2026-10-04 00:00+00');
```

Hai hàng **113** và **114** là phép thử bảo mật:

- Document 113 chưa được công bố.
- Document 114 thuộc tenant khác.

Một kết quả search của người dùng tenant 7 thông thường **không được trả hai tài liệu đó**, bất kể text score cao đến đâu.

### 5.3. Tạo GIN index cho FTS

```sql
CREATE INDEX idx_search330_doc_vector
ON search330.documents
USING gin (search_vector);

CREATE INDEX idx_search330_doc_tenant_visibility
ON search330.documents(tenant_id, is_published);

ANALYZE search330.documents;
```

Index trên bảng nhỏ chỉ minh họa cấu trúc. Planner có thể chọn `Seq Scan` vì toàn bộ bảng có 14 hàng, không phải vì index GIN vô hiệu.

## 6. Query baseline: truy xuất ứng viên và xếp hạng

Dùng cùng text search configuration khi xây vector và query:

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.simple'::regconfig,
        'cà phê phin'
    ) AS tsq
)
SELECT
    d.document_id,
    d.title,
    ts_rank_cd(d.search_vector, q.tsq) AS relevance_score
FROM search330.documents AS d
CROSS JOIN q
WHERE d.tenant_id = 7
  AND d.is_published = true
  AND d.search_vector @@ q.tsq
ORDER BY
    relevance_score DESC,
    d.document_id ASC
LIMIT 10;
```

Những ý cần kiểm tra:

- `@@` lọc những tài liệu match tsquery.
- `ts_rank_cd` cho một **điểm xếp hạng**, không phải xác suất “tài liệu đúng”.
- `ORDER BY ... document_id` tạo tie-breaker ổn định khi score bằng nhau.
- `LIMIT 10` phản ánh giao diện top-k; cũng có thể khiến tài liệu thứ 11 bị bỏ lỡ.
- Filter tenant và trạng thái công bố phải nằm trong truy vấn truy xuất.

### 6.1. Giải nghĩa truy vấn sau khi phân tích

```sql
SELECT
    websearch_to_tsquery(
        'pg_catalog.simple'::regconfig,
        'cà phê phin'
    ) AS parsed_query,
    to_tsvector(
        'pg_catalog.simple'::regconfig,
        'Cà phê pha phin'
    ) AS parsed_document;
```

Hãy quan sát lexemes thật thay vì tự giả định một chuỗi tiếng Việt được tách thành đúng “từ” theo ngôn ngữ học.

Với tiếng Việt, các thành phần cách nhau bởi khoảng trắng thường là **âm tiết**, còn từ ghép có thể chứa nhiều âm tiết. Tìm đúng ngữ nghĩa “cà phê” là bài toán khác so với đơn giản so sánh token “cà” và “phê”.

### 6.2. Dùng ts_rank hay ts_rank_cd?

`ts_rank` và `ts_rank_cd` là các hàm xếp hạng built-in có cách tính khác nhau. `ts_rank_cd` tính đến sự gần nhau của lexemes thông qua cover density khi có vị trí thích hợp.

Không kết luận một hàm luôn tốt hơn bằng tên gọi. Với tập qrels có gán nhãn, hãy đo **NDCG@k/MRR** của từng phương án, đồng thời kiểm tra latency.

## 7. Trọng số title/body và các yếu tố ranking

Trong schema, title được đặt weight `A`, body weight `B`.

```sql
setweight(to_tsvector('simple', title), 'A')
||
setweight(to_tsvector('simple', body), 'B')
```

Ý tưởng:

- Một truy vấn trùng từ ở title thường có tín hiệu mạnh.
- Từ xuất hiện trong body vẫn quan trọng nhưng có thể kém ưu tiên hơn.
- Các weight trong vector có thể được dùng khi tính `ts_rank` hoặc `ts_rank_cd`.

### 7.1. Không trộn thang điểm tùy ý

Giả sử thêm tín hiệu:

- Text relevance score.
- Độ mới của bài viết.
- Ưu tiên tài liệu chính thức.
- Lượt sử dụng.
- Giá trị kinh doanh.

Không nên viết tùy tiện:

```text
score = ts_rank + 10 * popularity + 0.5 * recency
```

nếu các thành phần nằm trên những thang khác nhau. Popularity có thể áp đảo hoàn toàn relevance và đưa tài liệu không giải quyết câu hỏi lên đầu.

Một cách tiếp cận có kiểm soát:

1. Định nghĩa trọng số và chuẩn hóa thang điểm.
2. Giữ các hard filters tách riêng.
3. Đo trên qrels offline.
4. Đánh giá theo segment.
5. A/B với guardrails.
6. Kiểm tra kết quả đối với những truy vấn quan trọng.

### 7.2. Phân biệt business ranking và relevance

Đưa sản phẩm tồn kho lên cao hơn sản phẩm hết hàng có thể là yêu cầu sản phẩm hợp lý. Nhưng nếu từ khóa là “điều kiện bảo hành”, nên ưu tiên tài liệu trả lời đúng câu hỏi hơn quảng bá sản phẩm.

Cần định nghĩa rõ **mục tiêu** của từng loại truy vấn. Không tối ưu toàn bộ search chỉ theo tỷ lệ click hoặc doanh thu.

## 8. Snippet và highlight: ảnh hưởng trải nghiệm, không chỉ ranking

PostgreSQL có `ts_headline` để chọn đoạn văn bản có lexemes liên quan:

```sql
WITH q AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.simple'::regconfig,
        'bảo hành máy xay'
    ) AS tsq
)
SELECT
    d.document_id,
    d.title,
    ts_headline(
        'pg_catalog.simple'::regconfig,
        d.body,
        q.tsq,
        'StartSel=<mark>, StopSel=</mark>, MaxWords=25'
    ) AS snippet
FROM search330.documents AS d
CROSS JOIN q
WHERE d.tenant_id = 7
  AND d.is_published
  AND d.search_vector @@ q.tsq
ORDER BY ts_rank_cd(d.search_vector, q.tsq) DESC,
         d.document_id
LIMIT 10;
```

**Lưu ý an toàn:** không tự chèn chuỗi `ts_headline` vào DOM dưới dạng HTML tin cậy. Nguồn text có thể chứa ký tự markup hoặc nội dung không an toàn. Ứng dụng cần escape/sanitize phù hợp trước khi render, tách riêng phần đánh dấu highlight do hệ thống tạo.

Chất lượng snippet có thể được đánh giá theo:

- Có giải thích vì sao kết quả liên quan không?
- Có làm rõ các từ được match không?
- Có cắt sai ngữ cảnh khiến người dùng hiểu lầm không?
- Có vô tình lộ đoạn bị giới hạn quyền không?
- Có hỗ trợ thiết bị di động và accessibility không?

## 9. Tiếng Việt là một case phải đánh giá riêng

Tìm kiếm tiếng Việt có những thách thức đặc thù:

| Vấn đề | Ví dụ | Tác động |
|---|---|---|
| Có dấu/không dấu | `cà phê` / `ca phe` | Có thể không khớp token |
| Từ ghép nhiều âm tiết | `máy pha cà phê` | Tokenization không phản ánh từ/cụm từ |
| Gõ sai | `may pha ca phee` | Lexical FTS có thể không match |
| Từ đồng nghĩa | `đổi trả` / `hoàn hàng` | Match từ vựng yếu |
| Viết tắt | `BH` / `bảo hành` | Cần dictionary/alias theo ngữ cảnh |
| Mã sản phẩm | `MX-100` / `MX100` | Tách dấu gạch có thể khác |
| Tiếng Anh lẫn tiếng Việt | `coffee grinder máy xay` | Nhiều cấu hình/ngôn ngữ |
| Địa danh/tên riêng | `Đà Nẵng` / `Da Nang` | Cần normalization cẩn trọng |

Cấu hình `simple` không tự giải quyết các yêu cầu ấy.

### 9.1. unaccent là công cụ, không phải toàn bộ nghiệm

Extension `unaccent` có thể hỗ trợ chuyển một số ký tự có dấu sang dạng đơn giản:

```sql
-- Chỉ trên môi trường được phép cài extension:
CREATE EXTENSION IF NOT EXISTS unaccent;

SELECT unaccent('Cà phê pha phin');
```

Nhưng:

- Cần kiểm tra extension có sẵn và role có quyền cài không.
- Không phải mọi phép bỏ dấu đều giữ nguyên ý định; một số tên riêng có thể bị đồng nhất.
- Phải áp dụng normalization **nhất quán** cho document và query.
- Những hàm/dictionary từ extension có tính chất volatility; không mặc định dùng trực tiếp `unaccent(...)` trong generated column hoặc expression index đòi IMMUTABLE.
- Nếu dictionary thay đổi, index đã tạo từ normalization cũ có thể cần tái xây dựng.

Tránh “sửa” lỗi PostgreSQL bằng một wrapper khai báo `IMMUTABLE` sai sự thật mà không quản lý bất biến dictionary, phiên bản và reindex.

### 9.2. Đánh giá riêng nhóm query không dấu

Tạo tập qrels riêng:

```text
q1: cà phê pha phin
q2: ca phe pha phin
q3: máy xay cà phê
q4: may xay ca phe
```

Không chỉ nhìn metric gộp; một hệ thống tốt với query có dấu nhưng thất bại hoàn toàn với query không dấu có thể không phù hợp người dùng thực tế.

### 9.3. Phân tách từ chuyên sâu

Nếu nghiệp vụ cần tìm kiếm tiếng Việt chất lượng cao trên kho lớn, có thể xem:

- Pipeline NLP/tách từ tiếng Việt phù hợp.
- Chuẩn hóa từ khóa và từ đồng nghĩa.
- Bộ phân tích trong search engine có khả năng tùy chỉnh.
- Tầng query rewriting.
- Hybrid lexical + semantic retrieval khi có dữ liệu/chi phí phù hợp.

Mỗi lựa chọn cần được đo trên qrels, không chỉ trình diễn một vài truy vấn đẹp.

## 10. LIKE, trigram và FTS phục vụ những mục tiêu khác nhau

Một truy vấn:

```sql
WHERE title ILIKE '%cafe%'
```

khác với:

```sql
WHERE search_vector @@ websearch_to_tsquery(...)
```

Và cũng khác fuzzy matching dựa trên trigram.

### 10.1. LIKE / ILIKE

- Dễ hiểu cho kiểm tra chuỗi hoặc prefix.
- Với prefix có cấu hình collation/operator class phù hợp, B-tree có thể hỗ trợ.
- Với substring `'%abc%'`, B-tree thường không có phạm vi hữu ích.
- `ILIKE` không tự giải quyết thiếu dấu, typo hay từ đồng nghĩa.

### 10.2. pg_trgm

`pg_trgm` có thể hữu ích cho substring và tương tự chuỗi:

```sql
-- Nếu extension có sẵn và được cấp quyền:
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_search330_title_trgm
ON search330.documents
USING gin (title gin_trgm_ops);
```

Ví dụ:

```sql
SELECT document_id, title
FROM search330.documents
WHERE title ILIKE '%pha phin%'
ORDER BY document_id;
```

Và một dạng so độ tương tự:

```sql
SELECT document_id, title,
       similarity(title, 'may xay ca phe') AS sim
FROM search330.documents
WHERE title % 'may xay ca phe'
ORDER BY sim DESC, document_id;
```

Toán tử `%` dựa trên ngưỡng similarity hiện hành; nó không có nghĩa kết quả chắc chắn đúng ý định người dùng. Với chuỗi cực ngắn, các ngưỡng và cách tách trigram có thể cho chất lượng khác.

### 10.3. pg_trgm không tự biến thành semantic search

Từ “hoàn tiền” và “refund” có thể liên quan về nghĩa nhưng rất khác ký tự. Trigram giải quyết **tương tự bề mặt chuỗi**, không thay thế synonym dictionary hoặc semantic retrieval.

### 10.4. Kết hợp đúng nhu cầu

Một chiến lược có thể:

- Exact ID → B-tree equality.
- Keyword documents → FTS.
- Typo/fuzzy tên sản phẩm → trigram.
- Từ đồng nghĩa/domain terms → query expansion được kiểm soát.
- Ý định ngôn ngữ tự nhiên khó khớp lexical → cân nhắc semantic/hybrid.

Đừng dùng một kỹ thuật cho tất cả loại truy vấn.

## 11. Xây tập truy vấn đánh giá (query set)

Một bộ query tốt là nền tảng của mọi chỉ số.

Nên thu thập từ:

1. Search logs đã khử thông tin nhạy cảm.
2. Câu hỏi thực tế từ bộ phận hỗ trợ.
3. Tên/mã sản phẩm thường được gõ.
4. Query không có kết quả.
5. Query có click nhưng người dùng quay lại tìm tiếp.
6. Query có lỗi chính tả/không dấu.
7. Từ khóa hiếm (*tail queries*).
8. Trường hợp nhiều tenant, quyền và tài liệu mới/xóa.
9. Tình huống không có đáp án thực sự.
10. Các câu hỏi nghiệp vụ quan trọng dù tần suất thấp.

### 11.1. Không chỉ lấy top-10 truy vấn phổ biến

Nếu bộ đánh giá toàn là truy vấn “máy pha cà phê” mà thiếu “mất hóa đơn đổi trả”, metric tổng thể có thể cao nhưng hệ thống thất bại trong những trường hợp người dùng cần nhất.

Chia query set theo:

```text
Exact match / navigation / informational / exploratory
Có dấu / không dấu / tiếng Anh / mixed language
Head / torso / tail queries
Mới / cũ / dài / ngắn
Có đáp án / không có đáp án
Public / tenant-restricted
```

### 11.2. Phân tách development và holdout

Dùng:

- **Development set** để chỉnh weights, synonyms, tokenizer và ranking.
- **Validation/holdout set** để đánh giá cuối, tránh “luyện thuộc” một số query đã biết.

Khi chính những người thiết kế ranking tự gán nhãn và tối ưu trên đúng tập query ấy, metric có thể bị overfit. Nên có reviewer độc lập và rubric nhãn rõ.

## 12. Qrels: tài liệu nào liên quan ở mức nào?

Trong information retrieval, **qrels** là bảng judgment đánh giá mức độ liên quan của cặp:

```text
(query_id, document_id) -> relevance_grade
```

Một thang graded relevance thường gặp:

| Grade | Ý nghĩa |
|---:|---|
| 0 | Không liên quan |
| 1 | Chỉ liên quan yếu / nhắc đến từ khóa, chưa giải quyết nhu cầu |
| 2 | Liên quan rõ, hữu ích |
| 3 | Rất liên quan hoặc là kết quả ưu tiên đúng nhu cầu |

Thang này **là quy ước đánh giá**, cần được các người gán nhãn thống nhất.

Ví dụ với query “cà phê pha phin”:

| Document | Grade minh họa | Lý do |
|---|---:|---|
| 101 — Hướng dẫn pha cà phê phin | 3 | Giải quyết trực tiếp |
| 107 — Cách chọn phin và cà phê | 2 | Hữu ích cho cùng ý định |
| 102 — Cách vệ sinh phin cà phê | 1 | Có liên quan nhưng khác bước |
| 104 — Máy xay cà phê mini | 1 | Sản phẩm phụ trợ, không trả lời cách pha |
| 103 — Cà phê hạt rang mộc | 1 | Liên quan nguyên liệu |
| 105 — Bảo hành máy xay | 0 | Không giải quyết nhu cầu |

Không có grade “đúng tuyệt đối” cho mọi sản phẩm; nó phụ thuộc ý định đã định nghĩa.

### 12.1. Gán nhãn theo tài liệu đầy đủ

Người gán nhãn không nên chỉ nhìn title/snippet nếu relevance phụ thuộc nội dung. Họ cần xem tài liệu đầy đủ hoặc ngữ cảnh đủ để xác định nó có thực sự trả lời câu hỏi hay không.

### 12.2. Không dùng click làm nhãn chân lý tự động

Người dùng thường click những gì xuất hiện ở đầu trang; click cũng phụ thuộc title, snippet và giao diện. Một tài liệu được click nhiều có thể chỉ vì nó được xếp cao, không phải nó tốt nhất.

Click logs có giá trị, nhưng **không tương đương qrels độc lập**.

## 13. Lưu query và qrels trong PostgreSQL

Một schema đánh giá tối giản:

```sql
CREATE TABLE search330.eval_queries (
    query_id integer PRIMARY KEY,
    query_text text NOT NULL,
    intent text NOT NULL,
    segment text NOT NULL
);

CREATE TABLE search330.eval_qrels (
    query_id integer NOT NULL
        REFERENCES search330.eval_queries(query_id),
    document_id integer NOT NULL
        REFERENCES search330.documents(document_id),
    relevance_grade smallint NOT NULL
        CHECK (relevance_grade BETWEEN 0 AND 3),
    PRIMARY KEY (query_id, document_id)
);

INSERT INTO search330.eval_queries(
    query_id, query_text, intent, segment
)
VALUES
    (1, 'cà phê pha phin', 'informational', 'vi_accented'),
    (2, 'ca phe pha phin', 'informational', 'vi_unaccented'),
    (3, 'bảo hành máy xay', 'navigational', 'vi_accented'),
    (4, 'máy xay cà phê', 'product', 'vi_accented');

INSERT INTO search330.eval_qrels(
    query_id, document_id, relevance_grade
)
VALUES
    (1, 101, 3),
    (1, 107, 2),
    (1, 102, 1),
    (1, 103, 1),
    (1, 104, 1),
    (1, 105, 0),

    (2, 101, 3),
    (2, 107, 2),
    (2, 102, 1),

    (3, 105, 3),
    (3, 111, 2),
    (3, 104, 1),
    (3, 106, 1),

    (4, 104, 3),
    (4, 110, 2),
    (4, 109, 1),
    (4, 103, 1);
```

### 13.1. Các qrels này chưa phải “complete judgments”

Bảng chỉ gán nhãn một số cặp query–document để minh họa. Nếu giả định **mọi document không được gán nhãn đều không liên quan**, metric có thể bị lệch.

Trong đánh giá thật:

- Tạo candidate pool từ nhiều retrieval methods.
- Gán nhãn đủ sâu cho những document có khả năng lọt top-k.
- Theo dõi `judgment coverage`.
- Phân biệt **unjudged** với grade 0.
- Bổ sung qrels khi ranking mới đưa document chưa từng thấy vào top-k.

Không nên gọi một bộ qrels chỉ có vài hàng là “ground truth toàn hệ thống”.

## 14. Precision@k: bao nhiêu kết quả trong top-k là hữu ích?

**Precision@k** đo tỷ lệ kết quả liên quan trong top-k, sau khi quy định “liên quan” là gì.

Giả sử grade >= 2 được coi là relevant.

Công thức:

\[
P@k = \frac{\#\{\text{kết quả liên quan trong top-k}\}}{k}
\]

Ví dụ một thứ hạng minh họa cho query q1:

| Vị trí | Tài liệu | Grade | Relevant (>=2)? |
|---:|---|---:|---|
| 1 | 101 | 3 | Có |
| 2 | 104 | 1 | Không |
| 3 | 107 | 2 | Có |
| 4 | 103 | 1 | Không |
| 5 | 102 | 1 | Không |

Ở top-3 có 2 kết quả relevant:

\[
P@3 = 2/3 \approx 0.667
\]

Ở top-5 có 2 kết quả relevant:

\[
P@5 = 2/5 = 0.4
\]

Đây là **thứ hạng giả định để tính metric**, không phải kết quả đã chạy FTS lab.

### 14.1. Precision@k phù hợp với giao diện top-k

Nếu một trang chỉ hiển thị 5 kết quả đầu, P@5 trực quan. Nó trả lời “trên màn hình có bao nhiêu lựa chọn hữu ích?”.

Nhưng P@k không cho biết còn bao nhiêu tài liệu tốt **không được tìm thấy**.

### 14.2. Khi kết quả ít hơn k

Theo định nghĩa thường dùng cho top-k, vẫn chia cho k. Ví dụ hệ thống trả chỉ một kết quả relevant khi k=5:

```text
P@5 = 1/5
```

Tuy nhiên cần nêu rõ quy ước đo của tổ chức, vì một số dashboard có thể dùng precision trên số result thực trả. Đừng trộn hai công thức rồi so sánh giữa hệ thống.

### 14.3. P@k chỉ xem có/không liên quan

Grade 2 và 3 đều được tính như relevant. Nếu muốn phân biệt “rất tốt” với “chấp nhận được” và vị trí khác nhau, cân nhắc NDCG@k.

## 15. Recall@k: hệ thống tìm thấy bao nhiêu tài liệu liên quan?

**Recall@k** đo phần relevant documents đã được tìm thấy trong top-k:

\[
R@k = \frac{\#\{\text{kết quả liên quan trong top-k}\}}
{\#\{\text{mọi tài liệu liên quan trong phạm vi được đánh giá}\}}
\]

Giả sử q1 có ba tài liệu relevant trong corpus: 101, 107 và 120. Nếu top-3 chỉ tìm được 101 và 107:

\[
R@3 = 2/3 \approx 0.667
\]

**Document 120 chỉ là tài liệu giả định trong ví dụ tính tay**, không thuộc fixture search330.

### 15.1. Recall phụ thuộc biết “tất cả relevant” là gì

Nếu đánh giá một triệu tài liệu nhưng chỉ có 10 tài liệu được gán nhãn, không thể biết chính xác total relevant của toàn corpus.

Trong thực hành, hệ thống thường dùng:

- Candidate pooling từ nhiều hệ tìm kiếm.
- Nhãn trên một tập đủ đại diện.
- Các định nghĩa Recall@k theo corpus hoặc judged pool đã được nêu rõ.
- Đánh giá riêng về coverage/retrieval stage.

### 15.2. Khi không có tài liệu nào thực sự relevant

Mẫu số = 0. Không nên tự chia cho 0 hoặc tuyên bố Recall@k=100% trong mọi trường hợp. Hãy quy định metric riêng cho nhóm **no-answer queries**, hoặc loại nhóm ấy khỏi phép tính Recall@k theo báo cáo rõ ràng.

## 16. Success@k và MRR: tài liệu đúng đầu tiên nằm ở đâu?

Đối với truy vấn định hướng “tìm đúng một tài liệu/đáp án”, chỉ số **Success@k** hữu ích:

```text
Success@k = 1 nếu có ít nhất một tài liệu relevant trong top-k
            0 nếu không
```

Ví dụ q “chính sách bảo hành máy xay”:

- Kết quả đúng ở vị trí 1 → Success@3 = 1.
- Kết quả đúng ở vị trí 3 → Success@3 = 1.
- Kết quả đúng ở vị trí 8 → Success@3 = 0.

Success@k không phân biệt vị trí 1 với vị trí 3 nếu cả hai nằm trong top-k.

### 16.1. Reciprocal Rank (RR)

Nếu tài liệu relevant đầu tiên ở vị trí `r`:

\[
RR = 1/r
\]

Ví dụ:

| Vị trí relevant đầu tiên | RR |
|---:|---:|
| 1 | 1.0 |
| 2 | 0.5 |
| 3 | 0.333 |
| 5 | 0.2 |
| Không có trong cutoff | 0 |

**Mean Reciprocal Rank (MRR)** là trung bình RR qua tập query.

### 16.2. Khi nào dùng MRR?

MRR hợp lý khi người dùng thường cần **một đáp án chính**, chẳng hạn:

- Tìm đúng trang hướng dẫn.
- Tìm tài liệu policy.
- Tìm mã hồ sơ hoặc mục hỗ trợ.
- Tìm entrypoint cho một tác vụ.

MRR không phản ánh đầy đủ chất lượng của tất cả kết quả relevant; query có năm tài liệu tốt nhưng chỉ cần một nằm đầu có thể đạt RR=1.

## 17. Average Precision và MAP

**Average Precision (AP)** kết hợp precision tại các vị trí có tài liệu relevant, có xét tổng số relevant documents theo quy ước đánh giá.

Một định nghĩa phổ biến khi đã có nhãn nhị phân:

\[
AP = \frac{1}{R}
\sum_{i=1}^{n} P@i \cdot rel_i
\]

Trong đó:

- `R` là tổng số tài liệu relevant trong tập đánh giá.
- `rel_i` bằng 1 nếu kết quả vị trí i relevant, ngược lại bằng 0.
- `P@i` là precision tính tới vị trí i.
- `n` là chiều dài danh sách đánh giá/cutoff đã quy định.

**MAP** = trung bình AP qua các query.

### 17.1. Tại sao MAP hữu ích?

Nếu một hệ thống đưa nhiều tài liệu relevant lên đầu, AP cao. Nếu relevant documents bị rải phía dưới giữa nhiều tài liệu không liên quan, AP giảm.

Tuy nhiên:

- Cần có nhãn relevant khá đầy đủ để biết `R`.
- Phải quy định cutoff nếu không đánh giá toàn ranking.
- Với dữ liệu graded relevance 0–3, MAP thường dùng ngưỡng nhị phân; NDCG có thể phù hợp hơn để khai thác mức độ liên quan.

Không tính MAP chỉ từ click logs thiếu nhãn và kết luận chính xác tuyệt đối.

## 18. NDCG@k: đo chất lượng thứ tự với nhiều mức liên quan

**Normalized Discounted Cumulative Gain** đặc biệt phổ biến khi qrels có grade 0,1,2,3.

Một dạng công thức:

\[
DCG@k =
\sum_{i=1}^{k}
\frac{2^{rel_i}-1}{\log_2(i+1)}
\]

Trong đó:

- `rel_i` là grade tài liệu ở vị trí i.
- Gain cao hơn cho tài liệu rất liên quan.
- Mẫu số giảm đóng góp của những vị trí thấp.

Để chuẩn hóa:

\[
NDCG@k = \frac{DCG@k}{IDCG@k}
\]

`IDCG@k` là DCG của thứ tự **lý tưởng** theo grades, trong cùng phạm vi đánh giá.

### 18.1. Vì sao NDCG phù hợp tìm kiếm tài liệu?

Giả sử grade 3 là tài liệu giải quyết trực tiếp câu hỏi, grade 2 là bổ trợ hữu ích, grade 1 chỉ nhắc sơ qua.

Đưa grade 3 lên vị trí 1 nên tốt hơn đặt grade 1 ở vị trí 1 rồi grade 3 ở vị trí 5. P@5 với ngưỡng >=2 chỉ phản ánh số lượng liên quan, trong khi NDCG còn phản ánh **mức độ và thứ tự**.

### 18.2. Không thể diễn giải NDCG nếu qrels thiếu nghiêm trọng

Nếu tài liệu mới được ranking đưa lên đầu nhưng chưa được đánh giá, việc gán mặc định grade 0 có thể phạt oan hệ thống mới.

Cần báo cáo:

- NDCG@k.
- Tỷ lệ top-k đã được gán nhãn.
- Quy mô judged pool.
- Segment/query coverage.
- Quy tắc unjudged documents.

### 18.3. NDCG không đo điều gì?

NDCG không tự đo:

- Latency.
- Quyền truy cập.
- Freshness của search index.
- Chi phí vận hành.
- Người dùng có thực sự hoàn thành tác vụ không.

Nó là một thành phần, không phải “điểm tổng chất lượng” toàn diện.

## 19. Một phép tính SQL: Precision@5 trên query đã gán nhãn

Với fixture `search330`, có thể tính một **chỉ số mang tính minh họa**. Các tài liệu chưa được qrels gán nhãn cần được xử lý minh bạch; dưới đây cố ý giả định unjudged=0 chỉ để biểu diễn SQL, **không dùng như kết luận production**.

```sql
WITH q AS (
    SELECT
        query_id,
        websearch_to_tsquery(
            'pg_catalog.simple'::regconfig,
            query_text
        ) AS tsq
    FROM search330.eval_queries
    WHERE query_id = 1
),
candidate_scores AS (
    SELECT
        d.document_id,
        ts_rank_cd(d.search_vector, q.tsq) AS score
    FROM search330.documents AS d
    CROSS JOIN q
    WHERE d.tenant_id = 7
      AND d.is_published
      AND d.search_vector @@ q.tsq
),
ranked AS (
    SELECT
        document_id,
        row_number() OVER (
            ORDER BY score DESC, document_id
        ) AS position
    FROM candidate_scores
)
SELECT
    COALESCE(
        SUM(
            CASE WHEN COALESCE(j.relevance_grade, 0) >= 2
                 THEN 1 ELSE 0 END
        ),
        0
    )::numeric / 5 AS precision_at_5
FROM ranked AS r
LEFT JOIN search330.eval_qrels AS j
    ON j.query_id = 1
   AND j.document_id = r.document_id
WHERE r.position <= 5;
```

### 19.1. Diễn giải đúng kết quả

Query trên cho **P@5 của một lần chạy cụ thể**, không phải chất lượng mọi truy vấn.

Nếu chỉ có hai kết quả được trả nhưng cả hai relevant, công thức vẫn chia cho 5 theo quy ước P@5 đã chọn.

Nếu một tài liệu chưa được gán nhãn nhưng thực ra relevant, `COALESCE(grade,0)` sẽ khiến P@5 bị thấp hơn sự thật.

### 19.2. Nếu muốn đánh giá nhiều query

Chạy cùng pipeline cho từng query_id trong tập đánh giá, lưu danh sách top-k và score theo **một run/version xác định**. Sau đó join với qrels và tổng hợp trung bình có báo phân đoạn.

Để tránh mỗi lần tính lại search và đổi kết quả giữa các run, một pipeline evaluation nghiêm túc nên lưu:

```text
run_id
query_id
document_id
rank_position
score
retriever_version
ranker_version
index_snapshot
evaluated_at
```

Không chỉ ghi một con số “P@5=0.8” không biết nó đến từ index hay phiên bản nào.

## 20. Kiểm tra coverage và zero-result rate

Nhiều truy vấn quan trọng không trả kết quả do:

- Từ không dấu khác từ có dấu.
- Lỗi chính tả.
- Đổi tên sản phẩm.
- Từ đồng nghĩa không được mở rộng.
- Cách tokenization không khớp.
- Tài liệu chưa đồng bộ hoặc chưa công bố.
- Quyền truy cập đúng nhưng tập tài liệu được phép là rỗng.

**Zero-result rate**:

\[
ZRR = \frac{\#\{\text{truy vấn trả 0 kết quả}\}}
{\#\{\text{truy vấn được tính}\}}
\]

### 20.1. Zero-result rate thấp không đồng nghĩa hệ thống tốt

Một hệ thống luôn trả tài liệu phổ biến bất kể query có thể có ZRR=0, nhưng relevance rất tệ.

Vì vậy hãy đo song song:

- Zero-result rate.
- Precision/NDCG.
- No-answer correctness.
- Query reformulation rate.
- Search abandonment.
- Tỷ lệ click và task success khi có dữ liệu phù hợp.

### 20.2. No-answer cũng có thể là kết quả đúng

Nếu người dùng tìm một sản phẩm không tồn tại hoặc tài liệu họ không có quyền xem, việc không trả kết quả là hợp lý. Không nên tối ưu ZRR bằng cách trả tài liệu sai hoặc lộ dữ liệu.

## 21. Search abandonment và query reformulation

Một số tín hiệu online:

| Tín hiệu | Có thể hàm ý | Hạn chế |
|---|---|---|
| Không click kết quả | Không tìm được nội dung hoặc câu trả lời đã có ngay trong snippet | Không phải lúc nào cũng là thất bại |
| Sửa query ngay sau đó | Từ khóa ban đầu không tốt/không ra kết quả | Có thể là quá trình khám phá bình thường |
| Click kết quả đầu | Có thể là relevance tốt | Chịu position bias |
| Quay lại search ngay | Có thể trang không giải quyết nhu cầu | Cần ngữ cảnh phiên |
| Dwell time dài | Có thể người dùng đọc kỹ | Cũng có thể trang khó hiểu |
| Hoàn thành tác vụ | Tín hiệu giá trị mạnh | Khó đo và phụ thuộc funnel |

Không biến một chỉ số hành vi đơn lẻ thành nhãn sự thật.

### 21.1. Privacy và search logs

Search queries có thể chứa tên khách, số đơn, email, thông tin sức khỏe, bí mật nội bộ hoặc dữ liệu thương mại.

Khi lưu logs:

- Loại bỏ/ẩn danh query nhạy cảm theo chính sách.
- Xác định retention.
- Giới hạn quyền truy cập.
- Không log tokens/API credentials.
- Không dùng log của tenant A để huấn luyện/recommend cho tenant B mà không có cơ sở quyền và chính sách phù hợp.
- Tách dữ liệu đánh giá khỏi dữ liệu có thể nhận diện người dùng.

## 22. Đánh giá theo phân đoạn, không chỉ trung bình

Giả sử kết quả:

```text
NDCG@10 tổng thể = 0.86
```

Nhưng chi tiết:

| Segment | NDCG@10 minh họa | Vấn đề |
|---|---:|---|
| Query có dấu, phổ biến | 0.93 | Tốt |
| Query không dấu | 0.42 | Khớp yếu |
| Exact mã sản phẩm | 0.98 | Rất tốt |
| Query hỏi chính sách | 0.61 | Bài đúng bị xếp thấp |
| Query tiếng Anh | 0.53 | Analyzer/từ vựng chưa phù hợp |

Đây là **số minh họa**, không phải kết quả của lab hoặc một dịch vụ cụ thể.

Nếu sản phẩm có lượng lớn người dùng tìm không dấu, metric chung 0.86 không đủ để tuyên bố search đã đạt.

### 22.1. Phân đoạn theo tenant

Đối với hệ thống nhiều tenant:

- Tenant có kho rất ít tài liệu có đặc tính khác kho vài triệu tài liệu.
- RLS/ACL có thể làm tập ứng viên thay đổi mạnh.
- Một index/hệ thống ranking tối ưu trên tenant lớn chưa chắc phù hợp tenant nhỏ.

Ngoài relevance, phải có test **không trả kết quả ngoài quyền**. Đây là hard constraint, không phải một metric chỉ cần đạt 99%.

### 22.2. Head và tail query

Các query phổ biến thường có nhiều dữ liệu click/qrels. Tail queries hiếm cần sampling và gán nhãn thủ công để không bị bỏ quên.

Tối ưu chỉ cho top queries dễ làm hệ thống thất bại ở những truy vấn ít xuất hiện nhưng mang giá trị cao.

## 23. Offline evaluation: so sánh trên cùng một bộ query và corpus

Một quy trình cơ bản:

1. Chụp hoặc cố định phiên bản corpus.
2. Định nghĩa tập query.
3. Gán nhãn qrels theo rubric thống nhất.
4. Chạy baseline PostgreSQL FTS.
5. Chạy phương án mới (đổi weight, trigram, analyzer, search engine).
6. Lưu top-k result lists của mỗi run.
7. Tính các metrics với cùng cutoff và quy tắc unjudged.
8. So sánh theo segment.
9. Xem query-level regressions, không chỉ tổng trung bình.
10. Chỉ chuyển sang online test khi không vi phạm hard constraints và chất lượng đạt ngưỡng.

### 23.1. Đừng so hai hệ thống trên hai corpus khác nhau

Nếu PostgreSQL index đã cập nhật tới hôm nay nhưng search index ngoài mới cập nhật tới hôm qua, các kết quả khác nhau có thể do **freshness lag**, không phải ranking.

Khi đánh giá relevance thuần, nên dùng cùng một snapshot/tập tài liệu đủ tương đương.

Khi đánh giá hệ thống end-to-end, **freshness lag là một metric riêng** cần báo cáo.

### 23.2. Ghi thông tin phiên bản

Báo cáo benchmark cần:

```text
dataset_id
snapshot_time
query_set_version
qrels_version
retriever_version
ranking_version
normalization_version
index_configuration
hardware/configuration
metric_definition
cutoff
```

Nếu không lưu cấu hình, khó tái hiện việc hệ thống mới “tốt hơn”.

## 24. A/B testing: kết quả offline tốt chưa đủ

Offline relevance là công cụ mạnh để so biến thể ranking, nhưng không phản ánh hoàn toàn trải nghiệm thực tế.

A/B testing có thể đánh giá:

- Search success/task completion.
- Reformulation/abandonment.
- Click-through rate sau khi xét bias.
- Conversion hoặc resolution rate khi phù hợp.
- p95/p99 latency.
- Error/timeout rate.
- Quyền/truy cập và tỷ lệ kết quả bị loại.
- Tác động lên chi phí/CPU của PostgreSQL và search cluster.

### 24.1. Tránh tối ưu “click bằng mọi giá”

Một snippet trả lời ngay có thể giảm click nhưng tăng trải nghiệm. Ngược lại, một tiêu đề giật gân có thể tăng click nhưng giảm task success.

Cần chọn **primary outcome metric** theo nghiệp vụ và **guardrail metrics** để ngăn tác hại phụ.

### 24.2. Phân nhóm thử nghiệm

Cần phân ngẫu nhiên một cách nhất quán theo user/session/tenant tùy thiết kế, đồng thời tránh một người liên tục thấy hai ranking khác nhau gây nhiễu.

Đặc biệt với hệ thống nhiều tenant, không nên tạo thử nghiệm khiến một tenant nhận tài liệu của tenant khác.

### 24.3. Can thiệp ranking có thể gây hiệu ứng dài hạn

Thay ranking thay đổi click logs, từ đó thay dữ liệu dùng để học ranking sau này. Đây là feedback loop. Cần phân biệt tác động ngắn hạn của experiment và ảnh hưởng lâu dài nếu dùng các tín hiệu hành vi.

## 25. Độ trễ: không chỉ đo một lần SELECT

Một hệ thống cần đo end-to-end:

```text
Request nhận query
    |
    +-- xác thực/ủy quyền
    +-- normalization / query parsing
    +-- PostgreSQL hoặc search retrieval
    +-- ranking / optional reranking
    +-- hydrate dữ liệu hiển thị
    +-- render snippet/facets
    +-- gửi response
```

Thời gian người dùng cảm nhận là tổng các bước và độ trễ do mạng/tài nguyên.

### 25.1. Các percentile nên theo dõi

| Chỉ số | Ý nghĩa |
|---|---|
| p50 | Trung vị, trải nghiệm phổ biến |
| p95 | 95% request có latency không vượt ngưỡng này |
| p99 | Phần đuôi chậm, quan trọng cho SLO |
| Error rate | Query lỗi, timeout, quá tải |
| Throughput | Query/giây theo workload |
| CPU/I/O | Chi phí sử dụng tài nguyên |
| Connection pool waits | Thời gian chờ lấy DB connection |
| Index freshness lag | Độ chậm cập nhật dữ liệu nếu dùng search ngoài |

**Các ngưỡng SLO phải được đặt theo sản phẩm**, ví dụ mục tiêu 200 ms ở p95 chỉ là một giả định nếu chưa có yêu cầu thật. Không tuyên bố một ngưỡng phổ quát cho mọi search.

### 25.2. Đọc p95 thay vì chỉ average

Một query bình thường 20 ms nhưng những query rộng dùng sort/ranking kéo dài 3 giây có thể tạo tail latency nghiêm trọng. Average có thể che vấn đề.

Cần đo theo:

- Độ dài query.
- Số từ trong tsquery.
- Truy vấn rất phổ biến.
- Truy vấn không có kết quả.
- Tenant lớn.
- Trang đầu và phân trang sâu.
- Tải đồng thời.
- Cache ấm/lạnh.

## 26. EXPLAIN: xem candidate retrieval và ranking tốn gì

Một truy vấn phân tích:

```sql
EXPLAIN (ANALYZE, BUFFERS)
WITH q AS (
    SELECT websearch_to_tsquery(
        'pg_catalog.simple'::regconfig,
        'cà phê'
    ) AS tsq
)
SELECT
    d.document_id,
    ts_rank_cd(d.search_vector, q.tsq) AS score
FROM search330.documents AS d
CROSS JOIN q
WHERE d.tenant_id = 7
  AND d.is_published
  AND d.search_vector @@ q.tsq
ORDER BY score DESC, d.document_id
LIMIT 10;
```

Một số node có thể gặp:

- `Seq Scan`.
- `Bitmap Index Scan` trên GIN.
- `Bitmap Heap Scan`.
- `Sort` hoặc `top-N heapsort` ở những trường hợp thích hợp.
- `Limit`.

### 26.1. GIN không bảo đảm ORDER BY rank tự có thứ tự

GIN hỗ trợ tìm các hàng có lexemes khớp tsquery. Nó **không** tự lưu các kết quả theo điểm `ts_rank_cd` được tính từ một query động.

Vì vậy, với nhiều candidate, PostgreSQL có thể phải **tính score cho nhiều hàng rồi chọn top-k**, kể cả khi GIN retrieval khá nhanh.

Đây là một trong những nguyên nhân khiến nhu cầu ranking rất phức tạp trên corpus lớn trở thành bài toán không chỉ “thêm một GIN index”.

### 26.2. Ts_rank/ts_rank_cd không phải một metric chất lượng

Hai hàm trả **điểm thuật toán của PostgreSQL**, không phải Precision@10 hoặc NDCG@10. Chúng có thể được dùng để xếp hạng, sau đó cần qrels để đánh giá ranking.

### 26.3. EXPLAIN ANALYZE thực thi SELECT

Với SELECT, EXPLAIN ANALYZE thực hiện query để đo. Với DML (INSERT/UPDATE/DELETE), nó thực thi thay đổi. Không chạy EXPLAIN ANALYZE DML tùy tiện trên production.

### 26.4. Fixture rất nhỏ không đủ benchmark

Trên 14 hàng, Seq Scan thường rẻ hơn GIN index. Đó là một lựa chọn hợp lý về chi phí, không phải bằng chứng PostgreSQL FTS không scale.

## 27. Hiệu năng ghi và chi phí duy trì search_vector

FTS index không miễn phí:

- INSERT phải tạo `search_vector` và cập nhật GIN.
- UPDATE title/body có thể tính lại vector và cập nhật index.
- DELETE tạo công việc dọn dẹp MVCC/index phù hợp.
- VACUUM, WAL, checkpoint và backup đều chịu thêm tải.
- Tài liệu quá lớn làm ranking/snippet và truy xuất thêm tốn tài nguyên.

### 27.1. Generated column hay expression index?

Có thể dùng expression GIN:

```sql
CREATE INDEX idx_example_expression_fts
ON some_table
USING gin (
    to_tsvector('simple'::regconfig, coalesce(body, ''))
);
```

hoặc lưu `search_vector` dưới dạng generated stored như lab. Cần chọn theo:

- Độ phức tạp trọng số title/body.
- Frequency update.
- Có cần truy cập vector để rank hay không.
- Khả năng match biểu thức query với index.
- Tính ổn định của text search configuration.

Không dùng tùy tiện `to_tsvector(body)` không chỉ định config trong index nếu muốn hành vi độc lập với mặc định phiên làm việc và các yêu cầu immutable/index expression.

### 27.2. Kiểm tra tác động workload OLTP

Nếu PostgreSQL còn phục vụ đơn hàng, thanh toán hoặc giao dịch nóng, search queries nhiều candidate có thể cạnh tranh CPU/RAM/I/O với workload OLTP.

Một search engine riêng có thể có giá trị **cô lập tải** kể cả khi chất lượng lexical của FTS vẫn đủ tốt. Nhưng đổi lại sẽ tăng độ phức tạp đồng bộ và vận hành.

## 28. Ranh giới kỹ thuật: khi nào PostgreSQL thường là lựa chọn hợp lý?

PostgreSQL thường đáng ưu tiên khi:

- Corpus và tốc độ query nằm trong ngân sách tài nguyên đã đo.
- Các truy vấn chủ yếu là exact match, filters, prefix/fuzzy vừa phải hoặc FTS lexical.
- Cần transaction consistency trực tiếp với dữ liệu gốc.
- Quyền truy cập/tenant filters gắn chặt với quan hệ PostgreSQL và RLS.
- Không có yêu cầu cao về synonyms, morphology đa ngôn ngữ, faceting phức tạp hoặc semantic ranking.
- Team muốn hạn chế số hệ thống phải vận hành.
- p95/p99 latency dưới tải thực tế đạt SLO.
- Chi phí thêm một search cluster chưa có lợi ích rõ ràng.

### 28.1. “Corpus nhỏ” không phải điều kiện đủ

Ngay cả corpus nhỏ cũng có thể cần search engine chuyên dụng nếu sản phẩm phụ thuộc mạnh vào:

- Phân tích từ tiếng Việt chất lượng cao.
- Typo-tolerant autocomplete.
- Synonym mapping phức tạp.
- Ranking theo nhiều tín hiệu và cá nhân hóa.
- Facets sâu với nhiều bộ lọc.
- Vector/hybrid retrieval có tooling phù hợp.

Ngược lại, một bảng rất lớn với query theo khóa và vài tiêu chí chính có thể vẫn dùng PostgreSQL hiệu quả nếu indexing, partitioning và workload phù hợp.

**Ranh giới nên dựa trên yêu cầu và đo lường, không phải số hàng duy nhất.**

## 29. Khi nào cân nhắc một search engine riêng?

Các dấu hiệu thường gặp:

1. **Recall thấp do analyzer/tokenization** mà cấu hình PostgreSQL đang dùng khó đáp ứng trong chi phí cho phép.
2. **Truy vấn không dấu/typo/synonym** chiếm tỷ trọng lớn và có yêu cầu UX rất cụ thể.
3. **Autocomplete/search-as-you-type** với ranking, typo tolerance và latency nghiêm ngặt.
4. **Faceted navigation** có nhiều chiều, buckets và tổ hợp filter theo realtime trên corpus lớn.
5. **Relevance tuning** cần nhiều bộ cấu hình, tín hiệu và kiểm thử.
6. **Tải search tăng** gây ảnh hưởng rõ đến OLTP, cần scale và cô lập độc lập.
7. **Phân tán corpus** qua nhiều node, index lifecycle/rebalancing và throughput vượt thiết kế single-instance PostgreSQL.
8. **Fuzzy/phonetic/multilingual analysis** có yêu cầu chuyên sâu.
9. **Hybrid lexical/semantic ranking** cần pipeline và tooling chuyên biệt.
10. Tỷ lệ lỗi/latency dù đã tối ưu PostgreSQL vẫn không đạt SLO với cấu hình và chi phí chấp nhận được.

Các công cụ có thể được cân nhắc tùy bối cảnh gồm Elasticsearch, OpenSearch, Solr, Typesense, Meilisearch và các dịch vụ tìm kiếm quản lý khác. **Không giả định mọi công cụ đều hỗ trợ mọi khả năng y hệt nhau.** Cần xác minh theo phiên bản, loại dữ liệu, license, giới hạn triển khai và đội ngũ.

### 29.1. Dedicated search engine không tự bảo đảm relevance tốt

Nếu analyzer chọn sai, qrels nghèo nàn, mapping lỗi hoặc ranking weights không phù hợp, công cụ chuyên dụng vẫn có thể trả kết quả tệ.

Việc chuyển hạ tầng mà không có bộ đánh giá chất lượng là đổi **nơi chạy** của một hệ thống search, chưa chắc đổi **chất lượng**.

## 30. Bảng quyết định: PostgreSQL hay công cụ tìm kiếm chuyên dụng?

| Tiêu chí | PostgreSQL FTS / SQL | Dedicated search engine |
|---|---|---|
| Exact lookup theo ID | Rất tự nhiên với B-tree/UNIQUE | Thường làm được nhưng không cần thiết |
| Truy vấn FTS lexical cơ bản | Có built-in `tsvector`/`tsquery` | Có bộ phân tích và ranking chuyên dụng tùy sản phẩm |
| Join quan hệ phức tạp | Là điểm mạnh | Thường cần denormalize hoặc truy vấn nguồn ngoài |
| Transaction consistency | Cùng DB với dữ liệu gốc | Thường phải đồng bộ và chấp nhận độ trễ |
| RLS/SQL permissions | Tích hợp vào PostgreSQL | Cần thiết kế bảo vệ ACL riêng |
| Typo/autocomplete phức tạp | Có thể kết hợp trigram/custom logic | Nhiều sản phẩm có chức năng chuyên biệt |
| Synonyms/ngôn ngữ | Text search configuration/dictionary, custom pipeline | Thường nhiều lựa chọn analyzer/configuration |
| Facets/aggregations lớn | SQL GROUP BY/filters; cần đo | Nhiều sản phẩm tối ưu cho search aggregations |
| Ranking nhiều tín hiệu | Tự viết SQL/expressions và tuning | Có tooling xếp hạng tùy công cụ |
| Semantic/hybrid search | Có thể tích hợp extension/hệ khác | Có hệ hỗ trợ, mức độ tùy sản phẩm |
| Scale search độc lập | Thường chia sẻ tài nguyên PostgreSQL hoặc replicas | Có thể scale cụm search riêng |
| Vận hành | Một hệ DB nhưng index/tuning có chi phí | Thêm cluster, sync, monitoring, recovery |
| Nguồn dữ liệu chính | Có thể vừa source of truth vừa search | Thường nên là derived index |
| Freshness | Dữ liệu commit trong DB được truy vấn theo transaction/snapshot | Phụ thuộc pipeline đồng bộ/index refresh |
| Tổng chi phí | Có thể thấp khi yêu cầu vừa | Thêm tài nguyên, nhân lực và phí dịch vụ |

Bảng là **khung ra quyết định**, không phải phép chấm điểm tuyệt đối hoặc so sánh benchmark của sản phẩm cụ thể.

## 31. Decision gate: đặt tiêu chí đủ rõ để không tối ưu vô tận

Một nhóm có thể đặt ra các điều kiện theo mục tiêu thật:

| Loại gate | Ví dụ mục tiêu giả định |
|---|---|
| Relevance | NDCG@10 không thấp hơn baseline trên mọi segment trọng yếu |
| Navigational | MRR ở nhóm tìm đúng policy đạt ngưỡng sản phẩm |
| Typo/no-accent | Success@5 vượt ngưỡng trong bộ query không dấu |
| Security | 0 kết quả ngoài quyền trong bộ kiểm thử cấm truy cập |
| Freshness | P99 index lag nằm trong SLO cập nhật |
| Latency | p95/p99 search request dưới ngưỡng sản phẩm |
| Reliability | Error/timeout rate dưới giới hạn |
| Cost | Tổng chi phí hạ tầng + vận hành nằm trong ngân sách |
| Operations | Có rollback, replay và reindex documented |

**Không có các con số SLO phổ quát** cho mọi hệ thống. Team phải điền ngưỡng từ mục tiêu kinh doanh, tải và mức rủi ro. Một prototype chỉ chạy query nhanh trong môi trường rỗng chưa vượt qua decision gate.

## 32. Kiến trúc tách search: PostgreSQL là nguồn sự thật

Khi dùng search engine riêng, cấu trúc thường là:

```text
Ứng dụng ghi dữ liệu
        |
        v
PostgreSQL (source of truth)
        |
        +---- transaction commit
        |
        +---- outbox / CDC / sync job
                      |
                      v
              Search indexing pipeline
                      |
                      v
              Dedicated search index
                      |
                      v
                 Search API
                      |
                      +---- query/filter/rank top-k
                      |
                      v
                Kết quả cho người dùng
```

**Source of truth** nên được xác định rõ. Tài liệu trong search index là một bản **dẫn xuất để truy vấn**, không nhất thiết là bản ghi có tính pháp lý/nghiệp vụ cuối cùng.

### 32.1. Vì sao không dual-write ngây thơ?

Không nên làm:

```text
1. UPDATE PostgreSQL thành công
2. Gửi API cập nhật search engine
3. Nếu bước 2 lỗi thì ...
```

Nếu PostgreSQL đã commit và bước 2 thất bại, dữ liệu search bị cũ. Nếu search cập nhật trước rồi transaction DB rollback, search có thể hiển thị tài liệu chưa commit.

Đây là vấn đề **dual-write không nguyên tử qua hai hệ**. Chỉ retry đơn giản phía client mà không có log bền có thể mất sự kiện.

### 32.2. Dùng transactional outbox

Một mô hình:

```sql
BEGIN;

UPDATE documents
SET title = ..., body = ...
WHERE document_id = ...;

INSERT INTO search_outbox(
    entity_type, entity_id, event_type, payload
)
VALUES ('document', ..., 'UPSERT', ...);

COMMIT;
```

Đây là khuôn mẫu, không phải SQL chạy trực tiếp trong lab vì bảng và các dấu `...` chưa được định nghĩa.

Điểm quan trọng:

- Dữ liệu gốc và outbox event được ghi **trong cùng transaction PostgreSQL**.
- Worker đọc outbox và cập nhật search index.
- Nếu worker lỗi, event còn lại để xử lý lại.
- Consumer phải thiết kế idempotent, vì giao hàng lại cùng event có thể xảy ra.
- Cần đánh dấu sự kiện đã xử lý theo quy tắc không làm mất event khi có crash.

## 33. CDC: đọc thay đổi từ log thay vì sửa từng nơi

**Change Data Capture (CDC)** theo luồng thay đổi PostgreSQL là một lựa chọn khác.

Ý tưởng:

```text
PostgreSQL WAL / logical decoding
         |
         v
      CDC stream
         |
         v
 Transformation + enrichment
         |
         v
      Search index
```

Ưu điểm tiềm năng:

- Có thể thu được thay đổi mà không cần mọi service tự gọi search API.
- Xây dựng pipeline tái sử dụng cho nhiều downstream consumers.
- Có log/offset để theo dõi và phục hồi theo kiến trúc phù hợp.

Nhưng phải xử lý:

- Snapshot ban đầu + chuyển tiếp sang stream.
- Schema changes.
- Transaction boundaries và thứ tự sự kiện.
- Delete/tombstone.
- Retry/deduplication.
- Lag và backpressure.
- Quyền truy cập replication và an toàn dữ liệu.
- Lựa chọn dữ liệu cần đưa sang index.

CDC **không tự giải quyết relevance**; nó giải quyết đồng bộ trạng thái nguồn.

## 34. Đúng dữ liệu: out-of-order, update và delete

Một pipeline search có thể nhận:

```text
Event A: document 101 -> version 5
Event B: document 101 -> version 6
```

Nếu hệ thống xử lý event B trước rồi event A sau, search index có thể bị **ghi lùi** về version 5 nếu không có bảo vệ.

### 34.1. Thêm version/revision để phát hiện sự kiện cũ

Một chiến lược:

```text
document_id
source_version
last_modified_at
is_deleted
payload
```

Khi index document, consumer so version và không để một event cũ ghi đè trạng thái mới, theo cơ chế concurrency/versioning của công cụ được chọn.

Không giả định chỉ dùng timestamp ứng dụng là luôn bảo đảm thứ tự chính xác; clock skew và đồng hồ các node có thể khác nhau. Nếu cần thứ tự, chọn source sequence/revision được thiết kế rõ.

### 34.2. Delete là một sự kiện quan trọng

Nếu một tài liệu bị xóa/unpublish/đổi tenant hoặc mất quyền xem, search index phải cập nhật trạng thái tương ứng.

Sai:

```text
DELETE từ PostgreSQL
    nhưng search index vẫn giữ bản cũ
    -> kết quả tìm kiếm có thể lộ nội dung đã xóa
```

Một pipeline đúng cần hỗ trợ:

- Tombstone hoặc delete event.
- Xóa khỏi index.
- Đối soát định kỳ để tìm ghost documents.
- Retry khi delete lỗi.
- Chính sách bảo toàn hoặc xóa bản sao theo yêu cầu pháp lý.

### 34.3. Rebuild có thể đụng update mới

Nếu rebuild index từ snapshot cũ trong lúc hệ thống tiếp tục ghi, một bản cập nhật mới có thể bị snapshot cũ ghi đè sau đó nếu không có kỹ thuật cutover/checkpoint đúng.

Cần phối hợp snapshot, change stream và version ordering.

## 35. Freshness và consistency: chấp nhận trễ tới mức nào?

Khi PostgreSQL là source of truth:

```text
T=0s:  DB commit title mới
T=1s:  search index chưa nhận event
T=3s:  search index áp dụng event
```

Trong khoảng T=0..3s, query search có thể trả title cũ hoặc chưa tìm thấy nội dung mới.

### 35.1. Các mức kỳ vọng khác nhau

| Nhu cầu | Freshness cần thiết |
|---|---|
| Tìm bài viết đã công bố cách đây nhiều ngày | Có thể chịu trễ ngắn theo SLO |
| Chỉnh tên sản phẩm trong catalog | Tùy kỳ vọng người dùng và quy trình |
| Thu hồi quyền tài liệu nhạy cảm | Cần cơ chế không hiển thị ngay sau thu hồi theo chính sách |
| Xóa nội dung pháp lý/riêng tư | Cần quy trình xóa kịp và kiểm chứng |
| Tìm mã đơn vừa tạo rồi trả kết quả | Có thể cần read-your-writes hoặc lookup trực tiếp DB |

### 35.2. Read-your-writes

Nếu người dùng vừa tạo đơn rồi gõ mã đơn ngay, một search index eventual consistent có thể chưa thấy đơn.

Giải pháp tùy nghiệp vụ:

- Với exact ID, tra trực tiếp PostgreSQL source of truth.
- Dùng API riêng trả resource vừa tạo, không bắt người dùng chờ search.
- Có cơ chế đồng bộ/cập nhật ưu tiên hoặc read-your-writes khi công cụ hỗ trợ phù hợp.
- Hiển thị trạng thái “đang lập chỉ mục” nếu chấp nhận được.

Không đưa ra lời hứa “mọi document mới được tìm thấy tức thì” khi pipeline thực tế bất đồng bộ.

## 36. ACL, RLS và quyền trong search index riêng

Trong PostgreSQL, RLS có thể hạn chế hàng theo role/policy. Khi dữ liệu được copy sang search engine, **không tự động kế thừa cơ chế RLS của PostgreSQL**.

Mỗi search request phải bảo đảm:

1. Người gọi đã được xác thực.
2. Tenant scope đúng.
3. Nhóm/quyền tài liệu được áp dụng.
4. Trạng thái công bố, soft delete, hạn sử dụng đúng.
5. Metadata nhạy cảm không bị lộ qua facets, counts, snippets, suggestions.
6. Quyền vừa bị thu hồi không bị lộ do sync lag hoặc cache.

### 36.1. Filter ở ứng dụng sau khi search có thể chưa đủ

Nếu search engine trả top-10 từ toàn corpus, rồi ứng dụng loại các document sai quyền:

- Có thể còn rất ít hoặc 0 kết quả dù còn nhiều tài liệu được phép ở rank thấp.
- Ranking có thể bị lệch bởi những tài liệu người dùng không có quyền thấy.
- Counts/facets/suggestions có thể lộ thông tin trước bước filter.
- Một lỗi code ở bước hậu lọc có thể làm lộ dữ liệu.

Nên thiết kế tenant/ACL filtering **trong retrieval plan**, hoặc dùng một tầng bảo vệ được chứng minh an toàn; khi cần có thể hydrate và tái kiểm tra quyền ở PostgreSQL trước khi xuất dữ liệu nhạy cảm.

### 36.2. Count là thông tin có thể nhạy cảm

Ngay cả khi không trả title/document body, việc hiển thị “147 kết quả” cho một từ khóa trong một tenant không được phép có thể tiết lộ sự tồn tại của tài liệu.

Bảo mật phải áp dụng cả aggregations, autocomplete và phân tích hành vi.

### 36.3. Quyền có thể thay đổi nhanh hơn nội dung

Một ACL bị thu hồi cần được xử lý như thay đổi dữ liệu cấp bách, không phải event cập nhật nội dung thông thường nằm cuối hàng đợi không có SLO.

## 37. Reindex và blue-green cutover

Khi đổi analyzer, synonyms hoặc ranking input, search engine thường cần xây dựng lại index tùy công nghệ/loại thay đổi.

Một quy trình an toàn:

```text
index_v1 (đang phục vụ)
      |
      +-- snapshot source of truth
      |
      v
xây index_v2
      |
      +-- replay changes từ checkpoint
      +-- đối soát count/ID/ACL
      +-- đánh giá offline và latency
      |
      v
canary traffic tới index_v2
      |
      v
đổi routing/alias sang index_v2
      |
      +-- theo dõi rollback window
      |
      v
ngừng index_v1 khi đã an toàn
```

### 37.1. Những điều cần xác minh trước cutover

- Tỷ lệ document thiếu/dư.
- Schema mappings và analyzer version.
- Khả năng truy vấn sau thay đổi.
- Quyền/tenant/visibility.
- Delete/tombstone đã áp dụng.
- Freshness lag đã bắt kịp.
- NDCG@k/MRR so baseline theo segment.
- P95/P99 latency và error rate.
- Có đường rollback nhanh không.

Không chỉ so số document tổng: hai tập index có cùng COUNT nhưng khác ID hoặc quyền.

## 38. Hybrid retrieval: lexical, trigram, semantic

Một số search có lợi khi kết hợp nhiều nguồn candidate:

```text
                  Query
                    |
          +---------+----------+
          |         |          |
       Lexical    Trigram    Semantic
        FTS        fuzzy      vectors
          |         |          |
          +---------+----------+
                    |
              Deduplicate
                    |
            Merge / rerank
                    |
              ACL filtering
                    |
                  Top-k
```

Sơ đồ logic; trong hệ thống thật, **ACL phải được áp dụng đúng từ retrieval** ở nơi cần thiết, không chờ tới cuối pipeline một cách mù quáng.

### 38.1. Semantic search là gì?

Semantic retrieval dùng biểu diễn ý nghĩa (thường là embedding vectors) để tìm những văn bản gần nhau về nội dung dù không có nhiều từ trùng.

Có thể hữu ích cho:

```text
"không nhận được mã xác minh"
```

và tài liệu:

```text
"khắc phục lỗi OTP không gửi về điện thoại"
```

nhưng embedding không tự bảo đảm đúng sự thật, chính xác ID, ngữ cảnh pháp lý hoặc quyền truy cập.

### 38.2. Vector search trong PostgreSQL có thể không cần tách hệ ngay

PostgreSQL có hệ sinh thái extension cho vector similarity (ví dụ pgvector nếu triển khai được), nên một yêu cầu semantic vừa phải **không tự động bắt buộc** search engine riêng.

Tuy nhiên extension, index types, filter performance, recall/latency và vận hành cần được đánh giá theo phiên bản và dữ liệu thật.

### 38.3. Kết hợp thứ hạng bằng RRF

**Reciprocal Rank Fusion (RRF)** là một cách gộp các ranking lists khác nhau dựa vào vị trí:

\[
RRF(d) = \sum_{r \in \text{retrievers}}
\frac{1}{c + rank_r(d)}
\]

Trong đó c là hằng số làm giảm ảnh hưởng của thứ hạng cực cao.

Lợi ích: không bắt buộc score của lexical và vector có cùng thang đo.

Giới hạn:

- Cần candidate quality tốt từ mỗi nguồn.
- Không tự tạo relevance nếu cả hai retrieval đều bỏ sót tài liệu.
- Quyền truy cập phải được bảo vệ.
- Vẫn cần qrels/NDCG/MRR và latency benchmark.
- Không có một giá trị c tối ưu cho mọi hệ thống.

## 39. Khi ranking cá nhân hóa: thêm rủi ro và metric

Nếu search dùng lịch sử người dùng/đề xuất cá nhân hóa:

- Một kết quả tốt cho người này có thể không phù hợp người khác.
- Không nên đánh giá chỉ bằng một bộ qrels không có ngữ cảnh.
- Feedback loop có thể đẩy tài liệu phổ biến lên quá mức.
- Dễ tăng filter bubble hoặc giảm khả năng khám phá nội dung mới.
- Cần bảo vệ dữ liệu cá nhân và chính sách sử dụng tín hiệu hành vi.

Một chiến lược có thể kết hợp:

- Baseline lexical relevance.
- Hard filters.
- Preferences được phép.
- Recency/quality signals.
- Diversification.
- Kiểm thử trải nghiệm nhóm người dùng khác nhau.

Không để cá nhân hóa biến các tài liệu không đủ quyền thành candidate, dù chúng có score cao.

## 40. Quan sát production: chỉ số nào nên có dashboard?

Một dashboard hữu ích có ít nhất bốn nhóm.

### 40.1. Quality

- NDCG@5, NDCG@10 theo qrels có kiểm soát.
- MRR/Success@k cho navigational queries.
- Precision@k, Recall@k hoặc retrieval recall theo bộ qrels.
- Zero-result rate.
- Query reformulation/abandonment.
- Qrels coverage và unjudged@k.
- Metric theo ngôn ngữ/tenant/loại query.

### 40.2. Performance

- Query request rate.
- p50/p95/p99 latency end-to-end.
- Search backend latency.
- Timeouts/errors.
- CPU/RAM/I/O.
- Connection pool/executor queues.
- Slow query categories và top resource consumers.

### 40.3. Freshness và reliability

- Consumer/outbox/CDC lag.
- Số event chưa xử lý.
- Tỷ lệ replay/retry.
- Số index docs thiếu/dư.
- Tỷ lệ delete/unpublish chưa áp dụng.
- Độ trễ index rebuild.
- Health/capacity/quota của search backend.

### 40.4. Security

- Test vi phạm tenant/ACL/visibility.
- Tỷ lệ kết quả bị loại do quyền.
- Trường hợp user không được xem nhưng suggestions/count có thể lộ.
- Chứng từ audit thay đổi quyền và xử lý delete.
- Không log thông tin nhạy cảm trong query, snippet hoặc telemetry.

### 40.5. Không biến dashboard thành số liệu tự trấn an

Một biểu đồ NDCG trung bình tăng nhưng p99 tăng gấp đôi, tenant nhỏ bị lỗi quyền hoặc unaccent queries giảm mạnh **không phải một chiến thắng có thể rollout ngay**.

## 41. Quy trình quyết định chuyển hệ thống tìm kiếm

Một lộ trình có kiểm soát:

### Giai đoạn A — Định nghĩa mục tiêu

- Viết SLO search.
- Chọn hard constraints.
- Chọn phân đoạn.
- Tạo qrels và nguồn query.
- Ghi baseline quality/performance/cost.

### Giai đoạn B — Tối ưu PostgreSQL hợp lý

- Kiểm tra query parsing/config.
- Tạo/duy trì GIN phù hợp.
- Đánh giá weight title/body.
- Xử lý exact ID bằng B-tree.
- Thử trigram cho typo/substrings.
- Cân nhắc normalization tiếng Việt.
- Đọc EXPLAIN và giảm workload không cần thiết.
- Đo impact lên OLTP.

### Giai đoạn C — Prototype dedicated search

- Đưa cùng corpus snapshot vào hệ mới.
- Chọn analyzer và synonyms có phiên bản.
- Implement đúng tenant/ACL filters.
- Tính cùng metrics offline.
- So latency dưới cùng tải đại diện.
- Ước lượng nguồn lực đồng bộ và vận hành.

### Giai đoạn D — Đánh giá end-to-end

- Xây outbox/CDC và replay.
- Xử lý update/delete.
- Test index lag và read-your-writes.
- Thử rebuild/rollback.
- Test security/facets/suggestions.
- So total cost of ownership.

### Giai đoạn E — Canary, A/B và quyết định

- Rollout nhỏ cho tập traffic được kiểm soát.
- Theo dõi metric và query-level regressions.
- Rollback nếu security, latency hoặc quality không đạt.
- Tăng traffic khi có bằng chứng.
- Không xóa ngay search path cũ trước khi đã hoàn tất chuyển đổi/khôi phục.

## 42. Một số anti-pattern dễ gặp

### 42.1. “FTS query 30 ms nên search chắc chắn tốt”

Latency chỉ là một chiều; không nói gì về relevance và coverage.

### 42.2. “FTS chưa hỗ trợ typo nên bắt buộc chuyển ngay”

Có thể thử normalization, pg_trgm hoặc query expansion trước. Chuyển hạ tầng chỉ hợp lý nếu nhu cầu và bằng chứng đáng giá.

### 42.3. “Search engine riêng luôn nhanh hơn PostgreSQL”

Không có quy luật tuyệt đối. Tải, index, query, network, analyzer, sort và scale quyết định. Một lookup theo PK ở PostgreSQL có thể đơn giản và chính xác hơn.

### 42.4. “Thêm synonyms càng nhiều càng tốt”

Synonym expansion quá rộng có thể làm giảm precision, ví dụ từ “phin” liên quan đến một sản phẩm khác trong ngữ cảnh khác. Cần đo từng nhóm query.

### 42.5. “Tăng CTR là cải thiện relevance”

CTR có position bias, presentation bias và phụ thuộc intent. Cần guardrails và task outcome.

### 42.6. “Dùng P@10 là đủ”

P@10 không đo tổng recall, vị trí relevant đầu tiên, graded relevance, latency, fairness hoặc security.

### 42.7. “Không có kết quả luôn là lỗi”

No-answer có thể đúng khi nội dung không tồn tại hoặc không được phép xem.

### 42.8. “Unjudged tài liệu = không liên quan”

Có thể làm metric thiên lệch chống lại retriever mới. Cần mở rộng qrels.

### 42.9. “Dùng search index như source of truth”

Derived index thường bất đồng bộ và có thể rebuild. Bản ghi nghiệp vụ chính, ràng buộc dữ liệu và giao dịch nên có nguồn sự thật rõ.

### 42.10. “Dual-write DB và search API đủ an toàn”

Hai bước ngoài một transaction nguyên tử có thể lệch khi mạng/worker lỗi. Dùng outbox/CDC hoặc chiến lược đồng bộ bền phù hợp.

### 42.11. “Search index tự áp RLS của PostgreSQL”

Sai. Phải thiết kế tenant/ACL riêng và test cả counts/snippets/suggestions.

### 42.12. “Dùng client-side filter để sửa mọi lỗi quyền”

Có thể lộ thông tin trung gian và làm top-k mất ý nghĩa. Quyền nên là một phần của retrieval/access design.

### 42.13. “Reindex xong khi COUNT bằng nhau”

Có thể vẫn thiếu ID, ghi đè version mới, sai analyzer hoặc còn document đã xóa.

### 42.14. “Một test query đủ chứng minh bộ analyzer tiếng Việt”

Cần qrels theo có dấu/không dấu/typo/từ ghép/tên riêng và query dài/ngắn.

### 42.15. “Cứ thêm GIN là ORDER BY ts_rank không cần sort”

GIN giúp retrieval candidates, không lưu thứ tự relevance score cho mọi tsquery động.

### 42.16. “Vector search hiểu đúng mọi ngữ nghĩa”

Embedding có false positives/false negatives. ID và quyền phải được bảo vệ cứng, quality vẫn phải được gán nhãn/đo.

### 42.17. “Có p50 tốt thì đủ”

Tail p95/p99 và timeout mới có thể là phần người dùng phàn nàn nhiều.

### 42.18. “Cải thiện qrels development nghĩa là cải thiện mọi query”

Có thể overfit. Cần holdout, segment analysis và online tests.

## 43. Bài tập thực hành có gợi ý và đáp án

### Bài 1. Chọn metric cho ô tìm đúng mã đơn

**Đề:** Người dùng nhập `ORD-123`, mong đúng một đơn.

**Đáp án:** ưu tiên exact correctness, Success@1/MRR và không trả sai tenant; kiểm soát latency. B-tree equality theo mã có thể là hướng phù hợp hơn fuzzy ranking.

### Bài 2. Chọn metric cho bài viết hướng dẫn

**Đề:** Một query có nhiều tài liệu hữu ích ở các mức khác nhau.

**Đáp án:** NDCG@5/@10 phù hợp với graded qrels. Có thể thêm Recall@k và Success@k.

### Bài 3. P@5 có ba kết quả relevant là bao nhiêu?

**Đáp án:** `3/5 = 0.6`, theo ngưỡng relevant đã định nghĩa.

### Bài 4. R@5 nếu corpus có 8 tài liệu relevant và top-5 có 3?

**Đáp án:** `3/8 = 0.375` nếu toàn bộ 8 tài liệu relevant đã được xác định đúng.

### Bài 5. RR nếu tài liệu relevant đầu tiên ở vị trí 4?

**Đáp án:** `1/4 = 0.25`.

### Bài 6. Success@3 khi tài liệu đầu tiên đúng ở vị trí 4?

**Đáp án:** 0.

### Bài 7. Có dùng MRR để đo cả 20 tài liệu relevant không?

**Đáp án:** MRR chủ yếu đo vị trí của relevant result đầu tiên. Với nhiều tài liệu hữu ích, dùng thêm MAP/NDCG/Recall.

### Bài 8. Tại sao NDCG@10 tốt hơn P@10 ở một số bài toán?

**Đáp án:** NDCG xét **grade và vị trí** của tài liệu; P@10 nhị phân hóa relevance.

### Bài 9. Nếu top-10 toàn tài liệu chưa được gán nhãn thì NDCG có đáng tin?

**Đáp án:** không nên mặc định unjudged=0 rồi kết luận. Cần tăng judged pool/coverage và báo độ bất định.

### Bài 10. Vì sao không dùng click làm ground truth duy nhất?

**Đáp án:** position bias, snippet bias, feedback loops và khác biệt intent.

### Bài 11. Tìm tài liệu tenant 7 bằng FTS

```sql
WITH q AS (
    SELECT websearch_to_tsquery('simple', 'máy xay') AS tsq
)
SELECT d.document_id, d.title
FROM search330.documents d CROSS JOIN q
WHERE d.tenant_id=7
  AND d.is_published
  AND d.search_vector @@ q.tsq;
```

**Đáp án:** phải giữ tenant/visibility filter; không trả document 113/114.

### Bài 12. Vì sao `ts_rank_cd` không phải NDCG?

**Đáp án:** nó là score để xếp kết quả cho một tsquery; NDCG là metric đánh giá ranking dựa trên qrels.

### Bài 13. Phân biệt candidate retrieval với ranking

**Đáp án:** retrieval quyết định tập ứng viên; ranking quyết định thứ tự. Nếu tài liệu đúng không có trong ứng viên, thay ranking không giúp.

### Bài 14. Vì sao “ca phe” có thể không match “cà phê” trong lab?

**Đáp án:** token có dấu/không dấu khác; config `simple` chưa tự normal hóa dấu. Cần đánh giá normalization/analyzer.

### Bài 15. `unaccent` tự làm generated column được không?

**Đáp án:** không mặc định; phải xét volatility/immutability, dictionary và việc tái tạo index nếu normalization thay đổi.

### Bài 16. pg_trgm cải thiện gì?

**Đáp án:** tìm theo substring và tương tự chuỗi; không tự hiểu mọi synonym hay ngữ nghĩa.

### Bài 17. GIN giúp ORDER BY `ts_rank_cd` có sẵn thứ tự không?

**Đáp án:** không. GIN hỗ trợ tìm các candidate khớp, rank phụ thuộc query và có thể cần tính/sắp xếp.

### Bài 18. Zero-result rate bằng 0 có đủ gọi search tốt?

**Đáp án:** không. Có thể hệ thống trả tài liệu sai cho mọi query; cần relevance/no-answer correctness.

### Bài 19. Muốn kiểm tra query dài, phải chia segment nào?

**Đáp án:** theo intent, số token, ngôn ngữ, query có/không dấu, phổ biến/hiếm và tài liệu có/không có đáp án.

### Bài 20. Vì sao hai lần benchmark phải dùng cùng corpus?

**Đáp án:** tránh nhầm chênh lệch do dữ liệu mới/xóa/ACL với chênh lệch do thuật toán xếp hạng.

### Bài 21. Khi nào nên giữ PostgreSQL?

**Đáp án:** FTS đáp ứng relevance/latency/cost, giao dịch/ACL dễ bảo vệ, workload không cần khả năng đặc thù mà công cụ ngoài mới cung cấp.

### Bài 22. Khi nào cân nhắc dedicated search?

**Đáp án:** khi yêu cầu analyzer, typo/autocomplete, facets, relevance tuning hoặc scale độc lập vượt phạm vi giải pháp PostgreSQL hợp lý và được đo rõ.

### Bài 23. Vì sao search engine mới chưa chắc tốt hơn?

**Đáp án:** cấu hình analyzer, index mapping, quyền và ranking vẫn có thể sai; cần benchmark/qrels.

### Bài 24. Điểm yếu của dual-write là gì?

**Đáp án:** PostgreSQL commit và search API update không nguyên tử; lỗi một phía tạo lệch dữ liệu.

### Bài 25. Transactional outbox giúp gì?

**Đáp án:** lưu sự kiện cần đồng bộ cùng transaction với dữ liệu gốc, hỗ trợ retry/replay không bỏ mất thay đổi sau commit.

### Bài 26. CDC có tự xếp hạng tốt hơn không?

**Đáp án:** không. CDC đồng bộ dữ liệu, không cải thiện relevance nếu ranking không đổi.

### Bài 27. Tại sao consumer cần version?

**Đáp án:** sự kiện đến sai thứ tự có thể ghi đè tài liệu mới bằng phiên bản cũ.

### Bài 28. Document đã xóa khỏi PostgreSQL nhưng còn trong index thì sao?

**Đáp án:** có nguy cơ hiển thị tài liệu đã xóa, lộ dữ liệu; cần tombstone/delete replay và đối soát.

### Bài 29. RLS PostgreSQL có đi cùng tài liệu sang search engine không?

**Đáp án:** không tự động; phải thiết kế ACL/tenant filters trong search index/request và kiểm thử.

### Bài 30. Tại sao top-10 rồi lọc quyền ở ứng dụng dễ làm mất recall?

**Đáp án:** các kết quả ngoài quyền chiếm các vị trí đầu, bị loại đi nhưng những tài liệu hợp lệ ở vị trí sâu chưa được retrieval trả về.

### Bài 31. MRR tăng mà p99 tăng mạnh thì có thể rollout ngay?

**Đáp án:** chưa chắc. Phải xét SLO và guardrails cùng độ tăng chất lượng, tần suất truy vấn và trải nghiệm người dùng.

### Bài 32. Dấu hiệu cần rebuild search index?

**Đáp án:** thay analyzer/mapping hoặc schema có tác động tới token/indexed fields theo khả năng công cụ; cần kiểm tra quy trình chính xác, không mặc định mọi thay đổi đều cần full rebuild.

### Bài 33. Định nghĩa hard filters và soft ranking

**Đáp án:** hard filters gồm quyền, tenant, publish state và quy tắc dữ liệu bắt buộc; ranking sắp xếp tập hợp đã hợp lệ theo relevance/các tín hiệu mềm.

### Bài 34. Vì sao một query không có đáp án nên trả rỗng?

**Đáp án:** trả kết quả sai hoặc ngoài quyền để giảm zero-result rate làm suy giảm correctness và trust.

### Bài 35. Tại sao cần holdout query set?

**Đáp án:** tránh overfit vào những query đã dùng để chỉnh weights/analyzer, kiểm tra khả năng tổng quát hóa.

### Bài 36. Nếu kết quả offline tốt nhưng online task success giảm, làm gì?

**Đáp án:** điều tra segment, instrumentation, presentation bias và các khác biệt dữ liệu; dùng guardrail, rollback/canary khi cần, không áp đặt metric offline là chân lý.

## 44. Checklist thiết kế và đánh giá tìm kiếm

| Câu hỏi | Việc cần xác minh |
|---|---|
| Tìm kiếm giải quyết tác vụ gì? | Navigational, informational, exact, exploratory |
| Có qrels được gán nhãn đủ sâu không? | Không nhầm unjudged với nonrelevant |
| Đã định nghĩa grade và relevant threshold? | Metric giữa run so được |
| Có holdout query set? | Tránh overfit |
| Có query không dấu/typo/tiếng Anh? | Phù hợp người dùng thực tế |
| Có query không có đáp án? | Đo no-answer correctness |
| Có đo Precision/Recall/Success/MRR/NDCG đúng bài toán? | Không dùng một metric cho mọi mục tiêu |
| Có xem top regressions từng query? | Trung bình không che lỗi |
| Query parser/config có nhất quán với tsvector? | Tránh mất candidate |
| Có title/body weights hợp lý? | Tránh ranking lệch |
| Có fallback cho exact ID? | Không làm hỏng correctness |
| Có policy tenant/ACL/visibility? | Không lộ dữ liệu |
| PostgreSQL search có làm chậm OLTP? | Cô lập tải/chi phí |
| Có đo p50/p95/p99 và throughput? | Không chỉ average |
| Có đánh giá cập nhật index và chi phí ghi? | WAL/GIN/memory |
| Search index ngoài có source of truth rõ? | Tránh dữ liệu mâu thuẫn |
| Có outbox/CDC và khả năng replay? | Không mất event |
| Có xử lý out-of-order/version? | Tránh stale overwrite |
| Có delete/unpublish propagation? | Tránh ghost documents |
| Có đo freshness lag? | SLO nhất quán |
| Có đối soát index IDs/ACL? | Không chỉ đếm tổng |
| Có reindex/cutover/rollback? | Khôi phục khi lỗi |
| Có đánh giá tổng chi phí hạ tầng + nhân lực? | Tránh phức tạp không cần thiết |
| Có canary/A-B và guardrails? | Kiểm chứng trải nghiệm thật |
| Có logging/privacy/retention phù hợp? | Bảo vệ dữ liệu người dùng |

## 45. Tài liệu và nguồn tham khảo

Tài liệu PostgreSQL chính thức để tra cứu theo phiên bản thực tế:

- [Text Search Introduction](https://www.postgresql.org/docs/current/textsearch-intro.html): khái niệm Full Text Search.
- [Text Search Controls](https://www.postgresql.org/docs/current/textsearch-controls.html): `tsquery`, `websearch_to_tsquery`, ranking và highlighting.
- [Text Search Dictionaries](https://www.postgresql.org/docs/current/textsearch-dictionaries.html): cấu hình xử lý lexemes.
- [Text Search Indexes](https://www.postgresql.org/docs/current/textsearch-indexes.html): GIN/GiST cho FTS.
- [Text Search Configuration](https://www.postgresql.org/docs/current/textsearch-configuration.html): cấu hình parser/dictionaries.
- [pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html): tìm kiếm tương tự chuỗi và hỗ trợ index.
- [unaccent](https://www.postgresql.org/docs/current/unaccent.html): dictionary lọc dấu, giới hạn sử dụng.
- [Generated Columns](https://www.postgresql.org/docs/current/ddl-generated-columns.html): quy tắc expression cho generated column.
- [GIN Indexes](https://www.postgresql.org/docs/current/gin.html): đặc điểm GIN.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): đọc kế hoạch và actual metrics.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): chính sách hàng.
- [Logical Decoding](https://www.postgresql.org/docs/current/logicaldecoding.html): nền tảng CDC.

Tài liệu khái niệm Information Retrieval:

- **Precision, Recall, AP/MAP, Reciprocal Rank/MRR, DCG/NDCG**: các metrics chuẩn trong đánh giá hệ thống truy xuất thông tin; chú ý định nghĩa cụ thể, cutoff và xử lý unjudged documents.
- **Offline relevance judgments, pooling, inter-annotator agreement, click/position bias**: các chủ đề quan trọng để xây bộ đánh giá đáng tin.
- **Online experimentation/A-B testing**: phải đo cả outcome lẫn guardrails, đồng thời tuân thủ chính sách privacy và quyền truy cập.

Không dùng bài học này làm bằng chứng mọi công cụ tìm kiếm có tính năng giống nhau. Chọn sản phẩm cần xác minh phiên bản, cấu hình, license và benchmark trên dữ liệu thật.

## 46. Tổng kết: đo chất lượng trước khi quyết định tách search

### 46.1. PostgreSQL vẫn có thể là công cụ tìm kiếm tốt

Với `tsvector`, `tsquery`, `@@`, `ts_rank`/`ts_rank_cd`, GIN, `pg_trgm`, B-tree và SQL filters, PostgreSQL phục vụ nhiều bài toán tìm kiếm văn bản mà không cần một hệ thống ngoài.

Nhưng chức năng có sẵn không đồng nghĩa chất lượng sản phẩm mặc nhiên tốt. Cần đo trên query thật.

### 46.2. Ba lớp đánh giá quan trọng

```text
                       SEARCH QUALITY
                              |
        +---------------------+----------------------+
        |                     |                      |
  Relevance/coverage    Latency/cost           Correctness/safety
        |                     |                      |
  P@k, R@k, MRR,        p50,p95,p99,            Tenant, ACL,
  MAP, NDCG, ZRR        throughput, CPU         delete, freshness
```

Một hệ thống chỉ đạt hai trong ba lớp có thể vẫn chưa dùng được.

### 46.3. Ranh giới chọn hệ không nằm ở một con số dữ liệu

Đừng quyết định chỉ vì:

```text
Có 1 triệu tài liệu -> bắt buộc Elasticsearch
```

hoặc:

```text
PostgreSQL đã có GIN -> không bao giờ cần search engine
```

Thay vào đó:

1. Xác định intent và search SLO.
2. Xây query set và qrels.
3. Đo ranking quality theo từng segment.
4. Đo candidate recall, zero-result và typo/non-accent handling.
5. Đo p95/p99, resource use và tác động OLTP.
6. Thử tối ưu PostgreSQL hợp lý.
7. Prototype search engine riêng trên cùng corpus nếu còn khoảng thiếu.
8. Xác minh đồng bộ, ACL, delete, freshness và khôi phục.
9. Chỉ rollout khi lợi ích rõ hơn tổng chi phí/độ phức tạp.

### 46.4. Search engine riêng là hệ dữ liệu dẫn xuất

Nếu tách search:

```text
PostgreSQL (source of truth)
       |
   Outbox / CDC
       |
   Search index
       |
  Search API
```

Phải coi:

- Out-of-order update.
- Retry/idempotency.
- Delete/tombstone.
- ACL/tenant boundaries.
- Rebuild/cutover.
- Freshness lag.
- Read-your-writes.
- Monitoring và rollback.

là những phần thiết kế **bắt buộc**, không phải chi tiết hậu kỳ.

**Một câu để nhớ:** PostgreSQL Full Text Search có thể đủ cho nhiều bài toán; hãy **đánh giá độ liên quan, độ bao phủ, thứ tự kết quả, độ trễ và tính an toàn trên workload thực tế** trước khi quyết định cần một công cụ tìm kiếm chuyên dụng, và nếu tách hệ thì phải quản lý search index như một bản sao dẫn xuất luôn có khả năng trễ, sai lệch hoặc cần xây lại.

