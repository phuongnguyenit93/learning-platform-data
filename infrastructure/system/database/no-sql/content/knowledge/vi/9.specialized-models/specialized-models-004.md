# Khác biệt giữa công cụ tìm kiếm với nguồn lưu trữ nghiệp vụ

## 1. Vì sao không nên đánh đồng tìm kiếm với lưu trữ nghiệp vụ?

Trong một hệ thống bán hàng, người dùng nhập **“tai nghe chống ồn dưới 2 triệu”** và mong muốn thấy danh sách sản phẩm phù hợp, có thể lọc thương hiệu, sắp xếp theo độ liên quan hoặc giá. Cùng lúc, hệ thống cần bảo đảm mỗi đơn hàng có mã duy nhất, không bán quá số lượng tồn kho và ghi nhận đúng giá đã chốt khi thanh toán.

Hai nhóm yêu cầu này khác nhau về bản chất:

- **Tìm kiếm (search):** Tìm các đối tượng có khả năng phù hợp với từ khóa hoặc tiêu chí, xếp hạng và giúp người dùng khám phá dữ liệu.
- **Lưu trữ nghiệp vụ (business/operational storage):** Lưu trạng thái chính thức của các thực thể, thực hiện quy tắc cập nhật và bảo vệ những bất biến như số lượng tồn kho, quyền sở hữu, trạng thái đơn hàng hoặc số tiền phải thanh toán.

Các công cụ như **Elasticsearch, OpenSearch, Apache Solr** được tối ưu cho truy vấn tìm kiếm thông qua chỉ mục và cơ chế xếp hạng. Cơ sở dữ liệu nghiệp vụ có thể là PostgreSQL, MongoDB, DynamoDB, Cassandra hoặc một hệ lưu trữ phù hợp khác; **NoSQL không đồng nghĩa với công cụ tìm kiếm**, và công cụ tìm kiếm cũng không mặc nhiên thay thế được mọi chức năng của một cơ sở dữ liệu nghiệp vụ.

Một kiến trúc thường gặp là:

~~~text
                 GHI / CẬP NHẬT
Ứng dụng ---------------------------------> Nguồn dữ liệu nghiệp vụ
                                               |
                                               | sự kiện thay đổi / CDC / outbox
                                               v
                                         Chỉ mục tìm kiếm
                                               ^
                                               |
Người dùng --> Nhập từ khóa --> Search API -----+
                   |
                   v
             Kết quả ứng viên
                   |
                   v
         Kiểm tra chi tiết/giá/tồn kho ở
          nguồn dữ liệu có thẩm quyền
                   |
                   v
            Thực hiện nghiệp vụ
~~~

Điểm cốt lõi: **Chỉ mục tìm kiếm thường là một mô hình đọc chuyên biệt, được xây dựng từ dữ liệu có thẩm quyền, không phải nơi quyết định cuối cùng cho mọi thao tác nghiệp vụ.**

Sau bài học, bạn có thể phân biệt hai vai trò, hiểu vì sao chỉ mục tìm kiếm mạnh ở truy vấn văn bản và xếp hạng nhưng có độ trễ đồng bộ, mô tả luồng cập nhật từ nguồn dữ liệu sang search, thiết kế cách xử lý dữ liệu cũ hoặc thiếu và chọn vị trí kiểm tra bất biến phù hợp.

> **Giới hạn:** Các ví dụ dưới đây dùng cú pháp HTTP JSON kiểu Elasticsearch/OpenSearch để làm rõ ý tưởng; cách thiết lập mapping, analyzer, API, mức nhất quán và tính năng cụ thể phụ thuộc sản phẩm, phiên bản và cách triển khai. Tài liệu không giả định mọi sản phẩm tìm kiếm có cùng khả năng transaction hoặc retention.

## 2. Hai câu hỏi khác nhau dẫn đến hai mô hình lưu dữ liệu

### 2.1. Dữ liệu nghiệp vụ trả lời “Trạng thái chính thức là gì?”

Một bản ghi sản phẩm ở nguồn nghiệp vụ có thể có:

~~~json
{
  "productId": "P1001",
  "tenantId": "T1",
  "name": "Tai nghe chống ồn",
  "priceMinor": 1590000,
  "currency": "VND",
  "status": "ACTIVE",
  "stockAvailable": 3,
  "version": 42
}
~~~

Trong ví dụ này:

- **productId** là định danh sản phẩm được các dịch vụ tham chiếu.
- **priceMinor** lưu giá theo đơn vị nguyên nhỏ nhất đã thống nhất. Với VND, ví dụ này dùng đơn vị đồng, tránh tính toán tiền trực tiếp bằng số thực nhị phân.
- **status** phản ánh trạng thái bán.
- **stockAvailable** là số lượng đang có thể bán theo quy tắc nghiệp vụ đã chốt.
- **version** hỗ trợ nhận diện phiên bản dữ liệu khi cập nhật và đồng bộ.

Đối với một đơn đặt hàng, việc quyết định “có cho phép giữ ba sản phẩm hay không” phụ thuộc **trạng thái tồn kho chính thức tại thời điểm chốt**, không chỉ số tồn kho đã được đưa vào trang tìm kiếm.

### 2.2. Tài liệu tìm kiếm trả lời “Người dùng có thể tìm thấy gì?”

Một tài liệu trong search index có thể được tổ chức khác:

~~~json
{
  "productId": "P1001",
  "tenantId": "T1",
  "title": "Tai nghe chống ồn",
  "description": "Tai nghe không dây, phù hợp khi di chuyển",
  "brand": "AudioNova",
  "categoryId": "HEADPHONE",
  "categoryName": "Tai nghe",
  "tags": ["không dây", "chống ồn", "bluetooth"],
  "priceMinor": 1590000,
  "currency": "VND",
  "inStock": true,
  "status": "ACTIVE",
  "sourceVersion": 42,
  "sourceUpdatedAt": "2026-11-14T08:00:00Z"
}
~~~

Tài liệu này **phi chuẩn hóa có chủ đích**: tên danh mục, thương hiệu, tag, trạng thái còn hàng và giá được đưa vào cùng một tài liệu để hỗ trợ tìm kiếm nhanh. Nhiều trường có thể được lấy từ các thực thể khác nhau hoặc qua một bộ chuyển đổi.

Ví dụ:

- title/description phục vụ tìm kiếm văn bản.
- tags/categoryId/brand phục vụ bộ lọc.
- priceMinor phục vụ lọc theo khoảng và sắp xếp.
- inStock phục vụ ẩn sản phẩm tạm hết hàng.
- sourceVersion giúp nhận biết index đã phản ánh phiên bản nào của nguồn.

**Đây là bản sao tối ưu cho đọc, không nhất thiết là bản ghi nghiệp vụ đầy đủ.** Giá và tồn kho trong search có thể chậm hơn nguồn; các trường được bổ sung hoặc rút gọn theo yêu cầu khám phá dữ liệu.

### 2.3. Bảng so sánh vai trò

| Tiêu chí | Công cụ tìm kiếm | Nguồn lưu trữ nghiệp vụ |
|---|---|---|
| Mục tiêu chính | Tìm tài liệu phù hợp, lọc, xếp hạng, tổng hợp kết quả | Ghi và đọc trạng thái có thẩm quyền, bảo vệ quy tắc nghiệp vụ |
| Đường truy cập phổ biến | Từ khóa, token, field, filter, score, aggregation | Khóa chính, khóa nghiệp vụ, điều kiện truy vấn và giao dịch |
| Kết quả | Danh sách ứng viên, có thứ tự theo độ liên quan | Trạng thái/bản ghi nghiệp vụ cần chính xác theo bảo đảm đã chọn |
| Cập nhật | Có thể có giai đoạn indexing và refresh trước khi tìm thấy | Ghi theo cơ chế commit/acknowledgment của kho nguồn |
| Tính duy nhất | ID tài liệu trong index không tự bảo đảm mọi unique constraint nghiệp vụ | Ràng buộc, thao tác ghi điều kiện hoặc transaction được thiết kế |
| Tính nhất quán | Thường chấp nhận độ trễ giữa nguồn và kết quả tìm kiếm | Phải chọn mức bảo đảm phù hợp với bất biến nghiệp vụ |
| Phi chuẩn hóa | Phổ biến để tăng tốc tìm kiếm và lọc | Tùy mô hình dữ liệu và chính sách toàn vẹn |
| Khôi phục | Có thể xây lại từ nguồn và pipeline nếu nguồn đầy đủ | Cần bảo vệ như dữ liệu chính thức, theo yêu cầu backup/retention |
| Ví dụ | Tra sản phẩm theo từ khóa, gợi ý, faceted search | Đặt hàng, thanh toán, thay đổi quyền sở hữu, giữ tồn kho |

Không nên hiểu bảng là “search engine không thể lưu bền vững” hoặc “database thông thường không thể tìm kiếm văn bản”. Nhiều hệ có tính năng giao nhau. Phân biệt nằm ở **trách nhiệm được giao cho từng thành phần và bảo đảm được dùng trong thiết kế cụ thể**.

## 3. Vì sao công cụ tìm kiếm tra văn bản tốt?

### 3.1. Chỉ mục đảo (inverted index)

Với dữ liệu:

~~~text
D1: "Tai nghe chống ồn"
D2: "Tai nghe không dây"
D3: "Loa bluetooth"
~~~

Một công cụ tìm kiếm văn bản có thể biến câu thành **token** và tạo chỉ mục đảo:

~~~text
token       -> những tài liệu có token
"tai"       -> D1, D2
"nghe"      -> D1, D2
"chống"     -> D1
"ồn"        -> D1
"không"     -> D2
"dây"       -> D2
"loa"       -> D3
"bluetooth" -> D3
~~~

Thay vì mở từng tài liệu để kiểm tra toàn bộ chuỗi, công cụ bắt đầu từ các token trong truy vấn, lấy danh sách tài liệu liên quan rồi kết hợp, lọc và xếp hạng.

Đây là mô hình giản lược. Hệ tìm kiếm thực tế có thể lưu thêm tần suất từ, vị trí token, độ dài field và nhiều cấu trúc khác để phục vụ phrase query, highlight và tính điểm.

### 3.2. Analyzer quyết định “từ” nào được tìm

Một chuỗi đi qua các bước phân tích như:

~~~text
Văn bản gốc
   |
   v
Character filter (nếu có)
   |
   v
Tokenizer
   |
   v
Token filters (lowercase, stopwords, stemming, ...)
   |
   v
Token đưa vào inverted index
~~~

Ví dụ một quy tắc có thể đổi “Bluetooth” thành “bluetooth” để tìm không phân biệt chữ hoa. Nhưng **không được mặc định** analyzer tiêu chuẩn sẽ xử lý hoàn hảo tiếng Việt, dấu thanh, từ ghép nhiều âm tiết, chính tả hoặc đồng nghĩa.

Các từ “tai nghe chống ồn”, “headphone noise cancelling” và “tai nghe khử tiếng ồn” có thể cần dictionary, synonym, bộ tách từ hoặc pipeline xử lý ngôn ngữ phù hợp với miền nghiệp vụ.

**Hệ quả thiết kế:** Search index không chỉ sao chép dữ liệu; nó còn **diễn giải và biến đổi** dữ liệu để phục vụ truy vấn. Khi thay analyzer, thường phải cân nhắc việc tạo lại chỉ mục để tài liệu cũ được xử lý theo cùng quy tắc mới.

### 3.3. Tìm kiếm có xếp hạng theo độ liên quan

Một truy vấn văn bản thường có nhiều kết quả phù hợp ở mức độ khác nhau:

~~~text
Từ khóa: "tai nghe chống ồn"

P1001: "Tai nghe chống ồn"                   -> rất phù hợp
P1002: "Tai nghe không dây"                 -> phù hợp một phần
P1003: "Phụ kiện chống ồn cho tai nghe"     -> có từ khóa nhưng khác ý định
~~~

Các hệ search như Elasticsearch/OpenSearch thường dùng những cơ chế relevance scoring, chẳng hạn BM25, cùng trọng số trường (field boost), độ khớp, điều kiện lọc và các cấu hình khác.

Điểm số tìm kiếm **không phải tính đúng đắn nghiệp vụ**. Một tài liệu có score cao không có nghĩa là sản phẩm còn hàng, giá đã được chốt hoặc người dùng có quyền mua.

### 3.4. Search query khác truy vấn chính xác theo khóa

Truy vấn “tên chứa gần đúng tai nghe” có thể:

- Khớp nhiều sản phẩm.
- Có thứ tự theo score và các quy tắc sắp xếp.
- Thay đổi khi analyzer hoặc dữ liệu index thay đổi.
- Bị ảnh hưởng bởi sự kiện refresh chưa hoàn tất.

Truy vấn “lấy sản phẩm P1001 theo ID và phiên bản hiện hành” đặt ra yêu cầu khác: xác định **đúng một đối tượng**, đúng trạng thái theo mức nhất quán ứng dụng cần.

Trong nhiều kiến trúc, search API trả **danh sách ID ứng viên**; bước mua hoặc xem dữ liệu nhạy cảm sẽ kiểm tra lại theo ID ở nguồn có thẩm quyền.

## 4. Search hỗ trợ những thao tác gì mà kho nghiệp vụ có thể không tối ưu?

### 4.1. Full-text, phrase, fuzzy và prefix

Công cụ tìm kiếm có thể hỗ trợ:

- **Full-text search:** Khớp token từ các field văn bản.
- **Phrase search:** Khớp cụm từ có vị trí tương đối phù hợp.
- **Prefix/autocomplete:** Gợi ý khi người dùng đang nhập.
- **Fuzzy search:** Cho phép một số khác biệt ký tự, theo quy tắc thuật toán và cấu hình.
- **Synonym search:** Kết nối các cách gọi tương đương trong miền nghiệp vụ.

Các chức năng này khác với tìm đúng một khóa hoặc so sánh bằng trên trường nghiệp vụ. Chúng giúp **khám phá**, nhưng có thể làm kết quả rộng hơn hoặc khác kỳ vọng nếu phân tích từ và quy tắc ranking không được thiết kế.

### 4.2. Facets và aggregations

Khi tìm “tai nghe”, giao diện có thể hiển thị:

~~~text
Danh mục
- Tai nghe chụp tai   124
- Tai nghe nhét tai   310

Thương hiệu
- AudioNova           84
- SoundPeak          112

Giá
- Dưới 1 triệu       160
- Từ 1–3 triệu       221
~~~

Đây là **faceted search** hoặc aggregations theo kết quả truy vấn. Số đếm được tính trong tập tài liệu phù hợp với index và bộ lọc, **không mặc nhiên là số liệu giao dịch chính thức tại cùng thời điểm**.

Nếu yêu cầu là “tổng doanh thu đã thanh toán trong tháng”, phải định nghĩa trạng thái đơn, hoàn tiền, thuế, thời điểm ghi nhận và nguồn số liệu. Một aggregation trên index có thể hữu ích cho phân tích hoặc trải nghiệm, nhưng chỉ đúng như kỳ vọng nếu dữ liệu và chính sách đồng bộ đáp ứng yêu cầu kiểm toán.

### 4.3. Tìm kiếm vector và hybrid search

Một số công cụ tìm kiếm hiện đại hỗ trợ **vector search**, kết hợp embedding để tìm đối tượng tương đồng ngữ nghĩa. Ví dụ truy vấn “đồ dùng làm việc tại nhà yên tĩnh” có thể trả tai nghe chống ồn dù không trùng chính xác toàn bộ từ khóa.

**Hybrid search** có thể kết hợp lexical search (BM25) với semantic/vector search rồi xếp hạng lại. Điều này tăng năng lực khám phá, nhưng không làm search index trở thành nguồn xác thực thanh toán, tồn kho hay quyền truy cập.

Kết quả vector cũng có độ không chắc chắn về ý nghĩa; cần bộ lọc cấu trúc, giới hạn phạm vi, kiểm soát dữ liệu nhạy cảm và phép đánh giá chất lượng thích hợp.

## 5. Ví dụ cấu hình một chỉ mục tìm kiếm

Giả sử sản phẩm được quản lý chính thức bởi dịch vụ Catalog. Dịch vụ Search nhận bản chiếu dữ liệu để người dùng tìm kiếm.

### 5.1. Mapping minh họa

Ví dụ HTTP JSON kiểu Elasticsearch/OpenSearch:

~~~http
PUT /products_v1
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "productId":    { "type": "keyword" },
      "tenantId":     { "type": "keyword" },
      "title":        { "type": "text" },
      "description":  { "type": "text" },
      "brand":        { "type": "keyword" },
      "categoryId":   { "type": "keyword" },
      "tags":         { "type": "keyword" },
      "priceMinor":   { "type": "long" },
      "currency":     { "type": "keyword" },
      "inStock":      { "type": "boolean" },
      "status":       { "type": "keyword" },
      "sourceVersion": { "type": "long" },
      "sourceUpdatedAt": { "type": "date" }
    }
  }
}
~~~

Ý nghĩa:

- **text** được phân tích để tìm kiếm văn bản theo analyzer.
- **keyword** thích hợp cho giá trị chính xác như productId, tenantId, categoryId hoặc mã trạng thái.
- **long** giữ số nguyên để lọc theo khoảng và sắp xếp.
- **boolean/date** phản ánh kiểu dữ liệu dùng trong bộ lọc.
- **sourceVersion** cho biết index đang đại diện cho phiên bản dữ liệu nào ở nguồn.

Đây là mapping đơn giản phục vụ minh họa. Với tiếng Việt, cần kiểm tra analyzer/từ điển, chuẩn hóa dấu, quy tắc đồng nghĩa và cấu hình mapping theo sản phẩm thực tế. Không nên đổi mọi field thành text; một truy vấn filter chính xác trên trạng thái nghiệp vụ không nhất thiết nên chạy qua analyzer văn bản.

### 5.2. Ghi tài liệu vào index

~~~http
PUT /products_v1/_doc/T1%23P1001
Content-Type: application/json

{
  "productId": "P1001",
  "tenantId": "T1",
  "title": "Tai nghe chống ồn",
  "description": "Tai nghe không dây dùng khi di chuyển",
  "brand": "AudioNova",
  "categoryId": "HEADPHONE",
  "tags": ["không dây", "chống ồn"],
  "priceMinor": 1590000,
  "currency": "VND",
  "inStock": true,
  "status": "ACTIVE",
  "sourceVersion": 42,
  "sourceUpdatedAt": "2026-11-14T08:00:00Z"
}
~~~

ID của tài liệu trong ví dụ gồm tenant và productId, để tránh hai tenant có cùng productId đè nhau trong một index dùng chung. Cách mã hóa ID phải được quy định nhất quán và tránh các trường hợp ghép chuỗi mơ hồ.

**Lưu ý:** Lệnh index tài liệu phản ánh một bản chiếu tìm kiếm. Nó không phải thao tác tạo đơn hàng hoặc kiểm tra tồn kho; cập nhật bản chiếu có thể đến từ pipeline đồng bộ thay vì client gọi trực tiếp.

### 5.3. Tìm văn bản kết hợp bộ lọc

~~~http
GET /products_v1/_search
Content-Type: application/json

{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "tai nghe",
            "fields": ["title^3", "description"]
          }
        }
      ],
      "filter": [
        { "term": { "tenantId": "T1" } },
        { "term": { "status": "ACTIVE" } },
        { "range": { "priceMinor": { "gte": 500000, "lte": 2000000 } } }
      ]
    }
  },
  "sort": [
    { "_score": { "order": "desc" } },
    { "productId": { "order": "asc" } }
  ],
  "size": 10
}
~~~

Trong ví dụ:

- **multi_match** tìm trong nhiều field; title được tăng trọng số so với description.
- **term** dùng cho khớp chính xác trên những field keyword.
- **range** lọc theo khoảng giá.
- **_score** xếp hạng độ liên quan.
- **productId** được dùng làm tiêu chí phụ giúp thứ tự ổn định hơn khi điểm bằng nhau.

**Không nên diễn giải kết quả search là xác nhận có thể mua ngay**. Giá, trạng thái hoặc tồn kho có thể đã thay đổi tại nguồn ngay sau khi index được cập nhật.

## 6. Ghi thành công chưa chắc đã tìm thấy ngay

### 6.1. Chu kỳ cập nhật chỉ mục

Trong những search engine gần thời gian thực (**near-real-time search**), việc nhận thao tác ghi và việc tài liệu trở nên nhìn thấy qua truy vấn tìm kiếm có thể là hai thời điểm khác nhau.

~~~text
t0: Dịch vụ nghiệp vụ cập nhật sản phẩm P1001.
t1: Pipeline nhận thay đổi và gửi index request.
t2: Search engine xác nhận thao tác index.
t3: Cơ chế refresh làm phiên bản mới nhìn thấy trong search.
t4: Người dùng chạy truy vấn và thấy dữ liệu mới.
~~~

Khoảng trễ có thể xuất hiện:

1. Từ commit tại nguồn đến khi có event.
2. Từ event đến khi worker xử lý.
3. Từ worker gửi thao tác index đến khi hoàn tất.
4. Từ index operation đến refresh/search visibility.

**Độ trễ tổng** là tổng tác động của nhiều giai đoạn; không chỉ là giá trị refresh interval của search engine.

### 6.2. Refresh khác commit và replication

Các thuật ngữ cần phân biệt:

| Thuật ngữ | Câu hỏi |
|---|---|
| Acknowledged write | Search engine đã nhận và xử lý yêu cầu ghi theo ngữ nghĩa API nào? |
| Refresh | Tài liệu mới đã nhìn thấy trong những truy vấn search phù hợp chưa? |
| Flush / persistence | Trạng thái được ghi xuống các cấu trúc lưu trữ bền vững theo cơ chế nào? |
| Replica acknowledgment | Bao nhiêu replica được yêu cầu/chờ xác nhận ở thời điểm ghi? |
| Source commit | Trạng thái có thẩm quyền ở hệ nghiệp vụ đã được commit chưa? |

Việc search engine trả thành công cho một thao tác index không có nghĩa tài liệu nhất thiết đã xuất hiện trong mọi truy vấn ngay lập tức. Ngược lại, ép refresh thường xuyên để giảm độ trễ có thể tăng chi phí và làm giảm thông lượng; phải cân nhắc theo yêu cầu sản phẩm.

### 6.3. Tìm kiếm và lấy trực tiếp tài liệu theo ID

Một số search engine có đường đọc theo ID với ngữ nghĩa thời gian thực khác với truy vấn search theo inverted index. Vì thế có thể quan sát tình huống:

~~~text
Đọc theo ID tài liệu -> thấy cập nhật mới.
Tìm bằng query       -> tạm thời chưa thấy cập nhật đó.
~~~

Không được suy từ một kiểu đọc sang mọi kiểu đọc. Khả năng và mức nhất quán cụ thể phụ thuộc API, routing, replication và phiên bản. Đây càng không phải lý do dùng một bản ghi search làm bằng chứng cuối cùng rằng nguồn nghiệp vụ đã chốt đơn hàng.

## 7. Một luồng kiến trúc: nguồn nghiệp vụ → search index

### 7.1. Những thành phần điển hình

~~~mermaid
flowchart TD
    UI["Web / Mobile"] --> API["Catalog API"]
    API --> DB["CSDL nghiệp vụ"]
    DB --> OUT["Outbox / CDC"]
    OUT --> BUS["Hàng đợi / Event stream"]
    BUS --> WORKER["Search projection worker"]
    WORKER --> INDEX["Search index"]
    UI --> SEARCH["Search API"]
    SEARCH --> INDEX
    SEARCH --> API
    API --> CHECK["Kiểm tra giá, quyền, tồn kho ở nguồn"]
~~~

Luồng ghi và luồng đọc cần phân biệt:

**Luồng ghi:** Ứng dụng cập nhật trạng thái nghiệp vụ trong cơ sở dữ liệu có thẩm quyền. Thay đổi được phát đi và chuyển thành tài liệu tìm kiếm.

**Luồng đọc khám phá:** Search API truy vấn index để nhận danh sách phù hợp.

**Luồng thực hiện giao dịch:** Khi người dùng mua, giữ chỗ hoặc thanh toán, hệ thống kiểm tra điều kiện cần thiết ở nguồn có thẩm quyền và thực hiện thao tác ghi được bảo vệ.

### 7.2. Tại sao không ghi hai hệ độc lập rồi cho là xong?

Một đoạn mã tưởng đơn giản:

~~~javascript
await businessDatabase.updateProduct(productId, change);
await searchEngine.indexDocument(productId, projection);
return { ok: true };
~~~

có **rủi ro dual write**:

- Ghi business DB thành công, ghi search thất bại → index bị cũ.
- Ghi search thành công nhưng nghiệp vụ thất bại nếu đổi thứ tự → kết quả chứa dữ liệu chưa hợp lệ.
- Tiến trình chết giữa hai bước → không có yêu cầu nào tự khôi phục bước còn thiếu.
- Hai cập nhật đồng thời có thể tới search sai thứ tự → phiên bản cũ đè phiên bản mới.

Không thể mặc định hai API ở hai hệ độc lập tạo thành một transaction chỉ vì chúng được gọi liên tiếp. Cần cơ chế đồng bộ có thể phục hồi.

### 7.3. Transactional outbox

Một giải pháp phổ biến khi nguồn hỗ trợ transaction là ghi **bản ghi nghiệp vụ** và **outbox event** trong cùng transaction.

Ví dụ giả mã:

~~~text
transaction:
    UPDATE product P1001:
        priceMinor = 1490000
        version = 43

    INSERT outbox:
        eventId = EVT-9081
        entityType = PRODUCT
        entityId = P1001
        entityVersion = 43
        eventType = PRODUCT_CHANGED

commit
~~~

Worker đọc outbox hoặc một hệ CDC đọc thay đổi đã commit rồi cập nhật search index.

Ưu điểm: Khi transaction commit, thay đổi nghiệp vụ và thông tin cần phát sự kiện cùng tồn tại ở nguồn. Điều này giảm khoảng trống “DB đã cập nhật nhưng event bị mất vì ứng dụng chết trước khi gửi”.

**Giới hạn:** Outbox không tự bảo đảm worker chỉ nhận event một lần, không tự bảo đảm search cập nhật tức thì, và không thay thế xử lý thứ tự, retry hoặc giám sát. Cơ chế lấy event ra khỏi outbox phải có khả năng thử lại và tránh mất event.

### 7.4. CDC (Change Data Capture)

**CDC** trích xuất thay đổi từ nguồn dữ liệu theo cơ chế phù hợp, chẳng hạn log thay đổi của database hoặc change stream. Worker có thể dựng tài liệu search từ dữ liệu thay đổi.

Ví dụ:

~~~text
Product P1001 / version 42 -> price = 1.590.000
Product P1001 / version 43 -> price = 1.490.000
Product P1001 / version 44 -> status = INACTIVE
~~~

Một pipeline có thể nhận các thay đổi, tính projection rồi index lên tài liệu có ID cố định.

**Không được tự giả định** CDC của mọi nguồn cung cấp thứ tự toàn cục qua mọi partition, một lần giao sự kiện duy nhất hoặc khả năng giữ event vô hạn. Cần xem scope ordering, retention, consumer checkpoint và quy tắc khôi phục cụ thể.

### 7.5. Snapshot và luồng thay đổi

Khi xây index lần đầu, có thể cần:

1. Đọc một snapshot/đợt quét dữ liệu gốc.
2. Bắt đầu nhận các thay đổi trong thời gian snapshot chạy.
3. Giải quyết khoảng chồng lấp, trùng lặp hoặc sai thứ tự giữa snapshot và event.
4. Xác minh index đã bắt kịp nguồn đến mốc được chọn.

Chỉ quét toàn bộ nguồn rồi bật lắng nghe event **sau khi quét xong** có nguy cơ bỏ lỡ những thay đổi phát sinh ở khoảng trống. Phải chọn giao thức snapshot + CDC có khả năng nối tiếp dữ liệu chính xác.

## 8. Xử lý duplicate, sai thứ tự và sự kiện đến muộn

### 8.1. Một event có thể được chuyển nhiều lần

Trong hàng đợi hoặc event stream có cơ chế giao ít nhất một lần, worker có thể xử lý:

~~~text
EVT-9081: Product P1001, version 43
EVT-9081: Product P1001, version 43   // được gửi lại
~~~

Nếu projection tính theo trạng thái đầy đủ và ghi vào **cùng document ID**, thao tác có thể được thiết kế có tính idempotent. Nếu worker tự tăng bộ đếm dựa trên event mỗi lần, retry có thể tạo kết quả sai.

Cần phân biệt:

- **eventId:** Định danh một sự kiện được giao và có thể được gửi lại.
- **entityId:** Định danh thực thể nghiệp vụ.
- **entityVersion:** Thứ tự phiên bản của cùng thực thể.
- **projectionVersion/schemaVersion:** Phiên bản logic xây chỉ mục.

### 8.2. Event đến sai thứ tự

Giả sử:

~~~text
P1001 version 43: price = 1.490.000
P1001 version 44: status = INACTIVE
~~~

Do retry hoặc xử lý song song, sự kiện version 44 có thể tới search trước version 43. Nếu worker ghi đè vô điều kiện, index cuối cùng có thể quay về trạng thái cũ.

Một nguyên tắc phù hợp là:

> Chỉ áp dụng bản chiếu của một thực thể nếu phiên bản nguồn của nó **mới hơn phiên bản mà index đã đại diện**, hoặc áp dụng một cơ chế xác định thứ tự tương đương.

Ví dụ giả mã:

~~~text
onProductChanged(event):
    current = loadLatestProductFromSource(event.productId)
    candidate = project(current)

    conditionalIndexUpsert(
        documentId = current.tenantId + "#" + current.productId,
        payload = candidate,
        version = current.version,
        onlyIfNewerThanIndexedVersion = true
    )
~~~

Một số search engine có hỗ trợ versioning hoặc optimistic concurrency; cú pháp và ngữ nghĩa khác nhau theo API. Nếu không có cơ chế compare-and-set thích hợp, có thể cần xử lý tuần tự theo khóa thực thể, trạng thái version trong một kho hỗ trợ CAS hoặc phương án tương đương.

**Đọc lại nguồn** cũng không tự giải quyết mọi race: hai worker có thể cùng đọc hai phiên bản tại những thời điểm khác nhau, rồi ghi sai thứ tự. Cần bảo vệ tại bước áp dụng projection hoặc kiểm soát thứ tự thực thi.

### 8.3. Sự kiện xóa và nguy cơ “hồi sinh”

Nếu P1001 bị xóa ở version 45, worker xóa tài liệu khỏi index. Sau đó một event version 44 đến muộn và ghi lại tài liệu P1001, sản phẩm đã xóa có thể **xuất hiện trở lại**.

Giải pháp có thể gồm:

- Lưu **tombstone phiên bản** để ghi nhận thực thể đã xóa và từ chối event cũ.
- Giữ trạng thái DELETED/INACTIVE có version trong projection thay vì xóa vật lý ngay.
- Áp dụng cơ chế delete theo version của search engine nếu hỗ trợ, hiểu rõ retention của tombstone/version.
- Khi reindex, đối chiếu với nguồn và chỉ lấy thực thể còn đủ điều kiện hiển thị.

Không nên coi thao tác DELETE trong index là bảo đảm vĩnh viễn rằng một event cũ không thể tạo lại tài liệu.

### 8.4. Partial update nguy hiểm nếu event thiếu ngữ cảnh

Ví dụ event:

~~~json
{
  "productId": "P1001",
  "version": 46,
  "changedFields": { "categoryId": "HEADPHONE" }
}
~~~

Tài liệu search còn chứa categoryName, tags, quyền hiển thị, giá, tên thương hiệu. Một partial event có thể không đủ để xây lại mọi field dẫn xuất.

Hai chiến lược:

1. **Full projection:** Worker đọc đủ dữ liệu có thẩm quyền và xây lại toàn bộ tài liệu.
2. **Partial projection:** Worker cập nhật các field liên quan theo quy tắc rõ ràng, xử lý phụ thuộc và thứ tự phiên bản.

Full projection thường dễ tránh các trạng thái lai từ nhiều phiên bản nhưng có thể tốn thêm lượt đọc nguồn; partial projection tiết kiệm dữ liệu trong một số luồng nhưng phức tạp hơn nếu các field phụ thuộc nhau.

## 9. Nguồn nào được quyền quyết định tính đúng đắn?

### 9.1. Search result chỉ là ứng viên mua hàng

Giả sử search index đang hiển thị:

~~~json
{
  "productId": "P1001",
  "priceMinor": 1590000,
  "inStock": true,
  "status": "ACTIVE"
}
~~~

Trong khi đó, nguồn nghiệp vụ đã thay đổi:

~~~json
{
  "productId": "P1001",
  "priceMinor": 1690000,
  "stockAvailable": 0,
  "status": "ACTIVE",
  "version": 48
}
~~~

Nếu ứng dụng chấp nhận tạo đơn chỉ vì search trả inStock = true và giá 1.590.000, có thể dẫn đến **bán vượt tồn** hoặc chốt sai giá.

Luồng phù hợp hơn:

1. Search trả productId ứng viên và những thông tin hiển thị có thể tạm thời cũ.
2. Khi người dùng mở chi tiết hoặc bấm mua, ứng dụng lấy thông tin cần thiết từ dịch vụ có thẩm quyền.
3. Khi chốt đơn, dịch vụ nghiệp vụ kiểm tra giá, trạng thái và tồn kho theo quy tắc tại thời điểm ghi.
4. Nếu dữ liệu thay đổi, hiển thị thông báo và yêu cầu người dùng xác nhận điều kiện mới khi cần.

Kiểm tra ở bước chi tiết **vẫn không thay thế** kiểm tra tại thời điểm giữ tồn kho. Hai người dùng có thể cùng xem “còn 1”, rồi cùng mua. Bất biến phải được bảo vệ bằng thao tác ghi điều kiện hoặc transaction đúng phạm vi.

### 9.2. Tính duy nhất nghiệp vụ phải được bảo vệ ở nơi ghi

Search index có thể dùng productId làm document ID. Nhưng điều đó không tự tạo unique constraint cho:

- Mã đơn hàng ở dịch vụ Order.
- Username theo tenant.
- Số ghế trong một suất chiếu.
- Một idempotency key dùng tạo thanh toán.
- Mã giao dịch từ đối tác.

Ví dụ quy tắc “mỗi username trong tenant chỉ thuộc một tài khoản” phải được bảo vệ ở hệ quản lý tài khoản bằng ràng buộc, khóa đặt chỗ hoặc thao tác điều kiện phù hợp. Truy vấn search “chưa tìm thấy username” trước khi tạo tài khoản chỉ là **check-then-write** và có race condition.

### 9.3. Quyền sở hữu và trạng thái pháp lý

Trong ứng dụng thuê xe, một tài liệu search có thể hiển thị xe là “có sẵn”. Nhưng quyền quyết định xe có thể đặt trong khung giờ X còn phụ thuộc:

- Lịch đặt đã được xác nhận.
- Khoảng thời gian bảo trì hoặc xe bị khóa.
- Điều kiện của chủ xe.
- Chính sách hủy/giữ chỗ và trạng thái tranh chấp.

Các điều kiện này có thể thay đổi nhanh và liên quan nhiều bản ghi. Search giúp tìm xe theo thành phố, loại xe, tiện nghi, mức giá; **dịch vụ Booking** chịu trách nhiệm quyết định đặt được hay không.

Không nên dùng kết quả tìm kiếm như một **khóa giữ chỗ** hoặc bằng chứng có thể giao dịch.

## 10. Kiến trúc đọc: search, hydrate và xác minh

### 10.1. Tách “khám phá” và “thực hiện”

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant S as Search API
    participant I as Search index
    participant C as Catalog/Inventory
    participant O as Order service
    U->>S: Tìm "tai nghe" dưới 2 triệu
    S->>I: Full-text + filter
    I-->>S: Danh sách productId và score
    S-->>U: Danh sách ứng viên
    U->>C: Xem chi tiết P1001
    C-->>U: Giá và trạng thái hiện hành
    U->>O: Đặt mua P1001
    O->>C: Kiểm tra/giữ tồn kho theo điều kiện
    C-->>O: Thành công hoặc xung đột
    O-->>U: Kết quả đặt hàng
~~~

Khi hiển thị kết quả, có hai chiến lược thường dùng:

**A. Trả thông tin trực tiếp từ index:** Nhanh, ít lượt gọi, phù hợp dữ liệu mô tả chấp nhận cũ trong một thời gian ngắn.

**B. Search trả ID; ứng dụng hydrate những kết quả đầu từ nguồn:** Có thể hiện thông tin mới hơn và kiểm soát quyền chi tiết tốt hơn, nhưng thêm chi phí đọc và có thể làm danh sách thay đổi sau tìm kiếm.

Hai chiến lược có thể kết hợp: thông tin mô tả đọc từ index; giá cuối cùng, tồn kho, quyền truy cập hoặc trạng thái nhạy cảm luôn được xác minh từ nguồn trước thao tác quan trọng.

### 10.2. Những vấn đề khi hydrate

Nếu index trả 10 ID nhưng nguồn cho biết 3 sản phẩm đã bị ẩn hoặc xóa, Search API có thể còn 7 kết quả. Ứng dụng cần quyết định:

- Có tải thêm các ứng viên tiếp theo để đủ 10 không?
- Có giữ nguyên thứ tự score từ search không?
- Nếu tồn kho vừa về 0, có ẩn hay gắn nhãn “hết hàng”?
- Nếu index chứa tài liệu của tenant khác do lỗi lọc, hệ thống có chặn từ nguồn trước khi trả dữ liệu nhạy cảm không?

Không nên coi hydrate như cách vá mọi vấn đề index. Pipeline vẫn phải đồng bộ đúng, có giám sát và khả năng phục hồi.

### 10.3. Kết quả tìm kiếm có thể bị xáo trộn giữa các trang

Trong lúc người dùng xem trang 1, tài liệu mới được index hoặc score thay đổi. Nếu trang 2 dùng offset đơn giản, kết quả có thể lặp hoặc bỏ sót.

Các công cụ tìm kiếm có cơ chế phân trang sâu như search_after hoặc point-in-time/snapshot đọc tùy sản phẩm. Cần dùng thứ tự ổn định, cursor và giới hạn truy vấn phù hợp.

Một ảnh chụp index tại thời điểm T **không chứng minh giá/tồn kho vẫn đúng tại thời điểm chốt đơn T+1**. Hai nhu cầu “phân trang nhất quán” và “giao dịch đúng” phải được giải quyết riêng.

## 11. Mapping và mô hình dữ liệu của search khác schema nghiệp vụ

### 11.1. Field text và keyword phục vụ thao tác khác nhau

Ví dụ:

~~~text
name        = "Tai nghe chống ồn"  -> text, dùng full-text
productId   = "P1001"             -> keyword, dùng khớp chính xác
categoryId  = "HEADPHONE"         -> keyword, dùng filter/facet
priceMinor  = 1590000             -> long, dùng range/sort
updatedAt   = ISO timestamp       -> date, dùng time filter
~~~

Nếu map productId thành text với analyzer không phù hợp, việc lọc định danh chính xác có thể gây kết quả bất ngờ. Nếu map title chỉ thành keyword, việc tìm từ trong tên sẽ có hạn chế so với text analyzer. Một field có thể dùng multi-field theo nhu cầu vừa full-text vừa sort/filter.

**Schema nghiệp vụ** tập trung vào tính hợp lệ, mối quan hệ và quy tắc dữ liệu. **Mapping của search** tập trung vào cách truy vấn, phân tích token, scoring và cấu trúc index.

### 11.2. Phi chuẩn hóa có lợi nhưng có chi phí cập nhật

Ví dụ tên danh mục “Tai nghe” được lặp lại trong 100.000 tài liệu sản phẩm. Nhờ vậy màn hình search có thể hiển thị ngay tên danh mục, không phải JOIN tại thời điểm truy vấn.

Tuy nhiên, đổi tên danh mục có thể đòi hỏi cập nhật rất nhiều tài liệu. Một số hệ tìm kiếm có thao tác update-by-query hoặc reindex; cần tính ảnh hưởng lên CPU, IO, refresh và độ trễ. Không nên giả định thay đổi một thực thể nguồn luôn là một ghi nhỏ trong index.

**Quy tắc thực dụng:** Chỉ đưa vào index những field cần cho tìm kiếm, lọc, sắp xếp, faceting và hiển thị kết quả; tránh biến index thành bản sao đầy đủ không có mục tiêu của toàn bộ nguồn nghiệp vụ.

### 11.3. Thay mapping/analyzer có thể cần reindex

Một số thay đổi mapping áp dụng được khi index đang chạy, nhưng nhiều thay đổi về kiểu field hoặc cách phân tích văn bản yêu cầu **tạo index mới và index lại dữ liệu**.

Nếu một team đổi từ analyzer đơn giản sang bộ tách từ tiếng Việt chuyên biệt, những tài liệu đã index trước đó không tự được phân tích lại chỉ vì cấu hình mới được khai báo.

Vì vậy, search schema cần có **phiên bản và kế hoạch di trú riêng**, khác với migration của database nghiệp vụ.

## 12. Reindex, backfill và chuyển phiên bản an toàn

### 12.1. Vì sao phải có khả năng xây lại index?

Search index có thể cần được xây lại khi:

- Đổi analyzer hoặc mapping.
- Thêm trường tìm kiếm mới.
- Thay cách phi chuẩn hóa.
- Sửa lỗi projection khiến dữ liệu index không đúng.
- Cần khôi phục sau sự cố mất index.
- Chuyển sang phiên bản công cụ tìm kiếm hoặc chiến lược shard mới.

Nếu index là **mô hình đọc có thể tái tạo**, nguồn nghiệp vụ và pipeline phải có đủ dữ liệu để xây lại trạng thái hợp lệ.

### 12.2. Mẫu blue–green index

Thay vì sửa index đang phục vụ truy vấn một cách rủi ro:

~~~text
products_v1  <- Search API đang đọc

Tạo products_v2 với mapping mới
    |
    +-- Backfill dữ liệu nguồn
    +-- Nhận thay đổi mới từ CDC/outbox
    +-- Đối chiếu dữ liệu
    +-- Bắt kịp mốc thay đổi
    |
    v
Chuyển search alias từ products_v1 sang products_v2
    |
    v
Giám sát và giữ phương án rollback phù hợp
~~~

Alias có thể giúp đổi index đích mà không sửa mọi client. Tuy nhiên, việc đổi alias chỉ là một phần; phải bảo đảm **index mới đủ dữ liệu và đã bắt kịp thay đổi** trước khi công bố.

### 12.3. Kiểm tra trước khi chuyển

Không chỉ so số tài liệu bằng nhau. Nên xem:

- Số thực thể nguồn đủ điều kiện xuất hiện và số tài liệu trong index.
- Số ID thiếu, ID thừa hoặc bị trùng do cách đặt document ID.
- Sai khác ở các trường quan trọng: tenantId, status, price, category.
- Độ trễ đồng bộ và watermark/checkpoint của pipeline.
- Những truy vấn quan trọng: full-text, filter, facet, sort, autocomplete.
- Lỗi projection, sự kiện bị giữ ở dead-letter queue, khả năng retry.
- Tài liệu nhạy cảm hoặc đã xóa có bị hiển thị không?

**Không thể lấy độ lệch tổng số bằng 0 làm bằng chứng index đúng tuyệt đối.** Hai index có cùng số tài liệu nhưng khác nội dung hoặc khác tập ID vẫn có thể gây lỗi.

### 12.4. Nguồn thay đổi khi đang reindex

Nếu backfill kéo dài nhiều giờ, dữ liệu nguồn vẫn có thể được cập nhật. Một quy trình cần xác định mốc snapshot và cơ chế nhận những thay đổi sau mốc đó.

Ví dụ:

~~~text
T0: Ghi nhận mốc CDC.
T1: Bắt đầu quét nguồn cho products_v2.
T2: Trong lúc quét, P1001 chuyển từ ACTIVE sang INACTIVE.
T3: Backfill và CDC được hòa giải theo sourceVersion.
T4: Kiểm tra v2 đã bắt kịp mốc yêu cầu.
T5: Chuyển alias sang v2.
~~~

Nếu chỉ backfill rồi chuyển alias, index v2 có thể đại diện cho những phiên bản cũ hơn index v1. Một quy trình đúng cần đối chiếu phiên bản nguồn và bảo vệ trước event tới sai thứ tự.

## 13. Xóa dữ liệu, quyền riêng tư và bảo mật

### 13.1. Xóa ở nguồn chưa đồng nghĩa đã biến mất khỏi search

Khi một sản phẩm bị gỡ, bài viết bị ẩn hoặc thông tin cá nhân bị xóa ở nguồn:

1. Cần gửi sự kiện xóa/ẩn qua pipeline.
2. Worker phải xóa hoặc cập nhật projection.
3. Search engine phải khiến thay đổi đó trở nên nhìn thấy trong search theo cơ chế refresh.
4. Cache kết quả, gợi ý, snapshot hoặc những index cũ cũng có thể chứa dữ liệu cần xử lý.

Khoảng trễ này có thể là vấn đề nghiêm trọng đối với **dữ liệu cần xóa ngay vì quyền truy cập hoặc yêu cầu pháp lý**. Không nên dựa vào eventual consistency của search nếu hệ thống hứa rằng tài liệu nhạy cảm bị thu hồi sẽ không bao giờ được hiển thị sau thời điểm X.

Có thể cần lớp kiểm tra quyền ngay lúc trả kết quả, chặn ID đã thu hồi, cơ chế đồng bộ ưu tiên hoặc quy trình xóa với giám sát và bằng chứng thực thi.

### 13.2. Search không tự thay thế authorization

Một index dùng chung nhiều tenant có tài liệu:

~~~json
{
  "tenantId": "T1",
  "productId": "P1001",
  "title": "Sản phẩm nội bộ"
}
~~~

Search API phải thực thi bộ lọc tenant và các điều kiện quyền truy cập phù hợp. Nhưng việc chỉ dùng một **term filter** do client tự gửi là không an toàn nếu client có thể sửa tenantId tùy ý.

Các nguyên tắc:

- Tenant/identity được lấy từ ngữ cảnh xác thực đáng tin cậy, không tin tham số client tùy ý.
- Quyền đọc có thể cần xác minh tại nguồn hoặc qua cơ chế phân quyền tài liệu có bảo đảm phù hợp.
- Search index chỉ chứa các trường cần thiết; hạn chế đưa số định danh nhạy cảm, token, bí mật, thông tin cá nhân không cần tìm kiếm.
- Cân nhắc mã hóa truyền tải, quản lý quyền kết nối, audit và chính sách dữ liệu.
- Kết quả gợi ý, highlight và aggregation cũng có thể làm lộ thông tin nếu bộ lọc bảo mật áp dụng không nhất quán.

### 13.3. Số đếm cũng có thể tiết lộ thông tin

Giả sử người dùng không có quyền xem tài liệu thuộc nhóm bí mật. Nếu một truy vấn chỉ trả 0 tài liệu nhưng facet vẫn hiển thị “Tài liệu bí mật: 120”, ứng dụng đã làm lộ metadata không nên thấy.

Vì vậy, **mọi dạng kết quả search** — danh sách, tổng số, gợi ý, aggregation — cần tuân thủ cùng phạm vi quyền.

## 14. Những trường hợp có thể dùng search như kho chính

Quy tắc “search chỉ là bản sao” là một **mẫu kiến trúc rất phổ biến**, không phải định luật tuyệt đối. Có những hệ thống sử dụng công cụ search làm kho lưu trực tiếp cho:

- Log và dữ liệu quan sát hệ thống.
- Chỉ số sự kiện, tài liệu phục vụ khám phá hoặc phân tích.
- Một số tập dữ liệu mà thao tác tìm kiếm là chức năng chủ đạo.

Tuy nhiên, kể cả khi search là kho lưu chính, team vẫn phải trả lời:

1. Dữ liệu được tạo và giữ bền vững theo hợp đồng nào?
2. Có cần unique constraint ngoài document ID không?
3. Có giao dịch nhiều đối tượng hoặc bất biến về tiền/tồn kho không?
4. Có yêu cầu đọc nhất quán ngay sau ghi không?
5. Khi lỗi node, shard, index hoặc mapping, dữ liệu được khôi phục từ đâu?
6. Retention, backup, snapshot, audit và quyền riêng tư được xử lý thế nào?

Nếu chỉ cần lưu log có thể chấp nhận một số giới hạn và có pipeline tạo lại dữ liệu, lựa chọn khác với hệ thống chuyển tiền hoặc sổ cái bắt buộc phải đúng. **Chọn nguồn dữ liệu có thẩm quyền theo bất biến và trách nhiệm**, không chỉ theo tên sản phẩm.

## 15. Các failure mode điển hình

| Sự cố | Hiện tượng người dùng thấy | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|---|
| Search chưa thấy sản phẩm mới | Tạo sản phẩm xong nhưng tìm không ra | Pipeline trễ hoặc chưa refresh | Theo dõi lag, thiết kế read-after-write UX |
| Tìm thấy sản phẩm đã ẩn | Kết quả không còn hợp lệ | Event xóa trễ hoặc lỗi | Lọc quyền/trạng thái hiện hành; xử lý delete/tombstone |
| Giá trong search khác giỏ hàng | Giá thay đổi giữa hai màn | Index cũ hoặc chính sách giá khác | Chốt giá ở nguồn nghiệp vụ, thông báo khi đổi |
| Sản phẩm đã hết hàng vẫn có trong kết quả | Người dùng bấm mua rồi bị từ chối | Tồn kho thay đổi nhanh hơn index | Kiểm tra/giữ kho ở thời điểm giao dịch |
| Event cũ ghi đè mới | Tên, giá hoặc trạng thái quay về cũ | Delivery sai thứ tự | Kiểm soát sourceVersion tại bước áp dụng |
| Index thiếu nhiều sản phẩm | Tìm kiếm không đầy đủ | Worker dừng, DLQ đầy, backfill lỗi | Đo lag, retry, đối soát ID và reindex |
| Facet đếm sai | Bộ lọc có số lượng không khớp | Dữ liệu thiếu, độ trễ, scope sai | Định nghĩa ý nghĩa số đếm, xác minh pipeline |
| Search chậm sau thay analyzer | Latency tăng hoặc kết quả khác | Tokenization/reindex và tài nguyên | Đo benchmark, thử nghiệm index mới trước cutover |
| Rò dữ liệu tenant khác | Thấy tài liệu không có quyền | Filter/ACL sai hoặc projection chứa dữ liệu | Thực thi authorization tin cậy, chặn tại API |
| Đã xóa dữ liệu nhưng vẫn còn trong snapshot/index cũ | Rủi ro quyền riêng tư | Retention và quy trình xóa chưa hoàn chỉnh | Chính sách xóa/retention bao phủ tất cả bản sao |

## 16. Thiết kế các chỉ số vận hành cho pipeline tìm kiếm

### 16.1. Độ trễ từ nguồn tới index

Một chỉ số hữu ích:

\[
\text{index lag} =
t_{\text{visible in search}} -
t_{\text{source commit}}
\]

Nên đo theo phân vị (p50, p95, p99), không chỉ giá trị trung bình. Nếu chỉ đo thời gian worker gửi index request, có thể bỏ qua thời gian event nằm trong hàng đợi và thời gian refresh.

Ví dụ:

~~~text
Product P1001 commit lúc 08:00:00
Event tới worker lúc 08:00:08
Index request hoàn tất lúc 08:00:10
Tài liệu tìm kiếm được lúc 08:00:11

Lag quan sát từ commit tới searchable = 11 giây
~~~

Con số chỉ minh họa; độ trễ thực tế phụ thuộc tải, refresh, indexing, replication và nhiều yếu tố khác. Khi yêu cầu “sản phẩm mới xuất hiện trong 5 giây”, phải định nghĩa rõ chỉ tiêu áp dụng ở bao nhiêu phần trăm lần cập nhật, Region nào và được đo từ mốc nào.

### 16.2. Các chỉ số cần theo dõi

| Chỉ số | Phát hiện điều gì? |
|---|---|
| Event backlog / consumer lag | Pipeline đang chậm hoặc đứng |
| Oldest unprocessed event age | Có sự kiện bị giữ quá lâu |
| Projection failure / retry / DLQ | Dữ liệu thiếu do lỗi chuyển đổi |
| Search refresh/searchability lag | Index operation chưa nhìn thấy qua query |
| Source–index ID reconciliation | Tài liệu thiếu/thừa |
| SourceVersion gap | Index đại diện phiên bản cũ |
| Query latency p95/p99 | Search quá chậm dưới tải |
| Zero-hit rate | Từ khóa phổ biến không có kết quả |
| Authorization rejection | Rò hoặc sai lọc quyền cần điều tra |
| Index/storage growth | Chi phí shard, segment và retention |

Khi có SLA về độ mới, có thể đặt cảnh báo theo tuổi sự kiện chưa xử lý hoặc theo tỷ lệ bản chiếu cũ. Không chỉ nhìn CPU hoặc số request của search cluster.

### 16.3. Xử lý khi search tạm thời không hoạt động

Nếu search cluster gặp lỗi, ứng dụng cần chiến lược đã thỏa thuận:

- Trả lỗi tìm kiếm có thông báo rõ ràng và cho phép thử lại.
- Hiển thị danh mục hoặc dữ liệu đã cache với giới hạn độ mới.
- Cung cấp tìm kiếm đơn giản theo mã chính xác từ nguồn nếu đã thiết kế sẵn.
- Giữ đường tạo đơn hoặc xem đơn đang có hoạt động độc lập nếu nghiệp vụ cho phép.

Không nên tự động chuyển mọi search query thành quét toàn bộ database nguồn: việc đó có thể biến lỗi search thành quá tải nguồn nghiệp vụ.

## 17. Bài tập thực hành

### Bài 1. Phân loại trách nhiệm

Cho các yêu cầu:

1. Người dùng tìm “tai nghe bluetooth” và lọc thương hiệu.
2. Người dùng xem một sản phẩm còn hàng hay không.
3. Hệ thống giữ một đơn vị tồn kho khi khách bấm mua.
4. Người dùng nhận gợi ý các sản phẩm có từ khóa gần nghĩa.
5. Hệ thống bảo đảm mã đơn hàng không trùng.
6. Bộ phận chăm sóc khách hàng cần biết đơn đã thanh toán hay chưa.

Hãy phân loại: yêu cầu nào phù hợp với **search index**, yêu cầu nào cần **nguồn nghiệp vụ có thẩm quyền**, yêu cầu nào có thể dùng **cả hai ở những bước khác nhau**.

**Gợi ý:** 1 và 4 là tác vụ khám phá. 3 và 5 phải được bảo vệ ở điểm ghi nghiệp vụ. 2 có thể hiển thị trạng thái gần đúng từ search nhưng phải xác minh ở nguồn trước khi đặt; 6 phụ thuộc trạng thái chính thức của dịch vụ Order/Payment.

### Bài 2. Tìm lỗi dual write

Cho mã giả:

~~~javascript
await db.updateProduct(productId, { priceMinor: 1200000 });
await search.index(productId, { priceMinor: 1200000 });
~~~

Yêu cầu:

1. Nêu ít nhất ba cách hai hệ có thể lệch nhau.
2. Đề xuất luồng transactional outbox hoặc CDC thay thế.
3. Nếu worker nhận cùng event hai lần, cần bảo vệ điều gì?
4. Nếu event version 11 đến sau version 12, làm sao không ghi đè bản mới bằng bản cũ?

**Gợi ý:** Transaction tại nguồn chỉ bảo vệ các thay đổi trong transaction của nguồn, không tự bảo vệ API search bên ngoài. Outbox giúp lưu dấu thay đổi; worker vẫn cần retry, idempotency, version check và reconciliation.

### Bài 3. Dữ liệu xóa bị hồi sinh

Giả sử:

~~~text
v42: P1001 đang ACTIVE
v43: P1001 bị DELETED

Worker A xử lý v43 trước, xóa tài liệu.
Worker B xử lý v42 muộn hơn và index lại tài liệu ACTIVE.
~~~

Hãy:

1. Giải thích vì sao đây là lỗi thứ tự event.
2. Đề xuất tombstone chứa sourceVersion hoặc cơ chế delete theo version.
3. Nêu cách reindex để không tái tạo sản phẩm đã xóa từ snapshot cũ.
4. Giải thích vì sao chỉ gọi DELETE rồi quên trạng thái phiên bản có thể chưa đủ.

### Bài 4. Mapping và truy vấn

Giả sử cần tìm sản phẩm theo:

~~~text
title        : full-text
brand        : filter chính xác
priceMinor   : khoảng giá
tenantId     : lọc quyền theo tenant
createdAt    : sắp xếp gần đây
~~~

Hãy chọn kiểu mapping phù hợp cho từng trường (text, keyword, number, date), viết cấu trúc truy vấn bool với một điều kiện full-text và ít nhất hai filter. Giải thích tại sao tenantId không nên nhận trực tiếp từ tham số client chưa xác thực.

### Bài 5. Reindex không gián đoạn

Đội phát triển muốn thay analyzer tiếng Việt cho index sản phẩm.

Hãy lập kế hoạch gồm:

1. Tạo index phiên bản mới với mapping/analyzer mới.
2. Backfill từ nguồn nghiệp vụ.
3. Bắt thay đổi nguồn trong thời gian backfill.
4. Kiểm tra số ID, phiên bản, dữ liệu nhạy cảm và truy vấn trọng yếu.
5. Chuyển alias khi đạt điều kiện.
6. Theo dõi và có phương án phục hồi nếu kết quả mới không đạt yêu cầu.

Giải thích vì sao “đổi analyzer trên index đang dùng” không đồng nghĩa dữ liệu cũ tự được lập chỉ mục lại theo quy tắc mới.

### Bài 6. Tình huống thuê xe

Một ứng dụng thuê xe có danh sách xe theo địa điểm, loại xe, tiện nghi và giá tham khảo. Khách có thể lọc “xe 7 chỗ ở Đà Nẵng, có ghế trẻ em” rồi đặt xe từ 9:00 đến 17:00.

Hãy xác định:

- Những trường nào nên đưa vào search index để tìm và lọc?
- Những dữ liệu nào cần dịch vụ Booking kiểm tra trực tiếp trước khi xác nhận?
- Nếu chủ xe ẩn xe nhưng event cập nhật search đến chậm, API phải làm gì để không lộ xe đã bị khóa?
- Nếu hai khách cùng chọn một xe ở cùng khung giờ, tại sao kết quả search không đủ để ngăn đặt trùng?

**Gợi ý:** Search phục vụ khám phá theo địa điểm/tiện nghi; Booking chịu trách nhiệm xung đột lịch, quyền đặt và trạng thái khóa tại thời điểm xác nhận. Cần kiểm tra hoặc giữ chỗ có bảo vệ đồng thời ở nguồn có thẩm quyền.

## 18. Tổng kết

**Công cụ tìm kiếm** và **nguồn lưu trữ nghiệp vụ** thường phục vụ hai mục tiêu bổ sung:

1. **Search index** được tối ưu để tìm văn bản, lọc, xếp hạng, faceting, gợi ý và khám phá; dữ liệu có thể được biến đổi, phi chuẩn hóa và nhìn thấy sau một khoảng trễ.
2. **Nguồn nghiệp vụ** giữ trạng thái có thẩm quyền và thực thi các bất biến ở phạm vi mà công nghệ và thiết kế thực sự bảo đảm.
3. **Kết quả search là ứng viên**, không phải lời cam kết rằng đối tượng còn hàng, giá còn đúng hoặc thao tác giao dịch sẽ thành công.
4. **Outbox/CDC và projection worker** giúp chuyển dữ liệu từ nguồn sang index, nhưng cần giải quyết duplicate, thứ tự version, xóa, lag và phục hồi.
5. **Reindex, bảo mật và quyền riêng tư** là phần của thiết kế ngay từ đầu: index có thể chứa dữ liệu cũ, tài liệu đã xóa hoặc thông tin không nên công bố.
6. **Ngoại lệ có tồn tại:** Search engine có thể là kho chính cho một số bài toán như log/quan sát, nhưng phải lựa chọn dựa trên yêu cầu durability, transaction, consistency, audit và khôi phục cụ thể.

Một thiết kế tốt bắt đầu bằng câu hỏi: **“Thành phần nào có quyền quyết định sự thật nghiệp vụ, và thành phần nào chỉ giúp tìm ra những đối tượng có thể liên quan?”** Khi ranh giới này rõ ràng, hệ thống có thể tận dụng tốc độ và tính linh hoạt của search mà không đánh đổi tính đúng đắn của đơn hàng, thanh toán, tồn kho hay quyền truy cập.
