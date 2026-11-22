# Khả năng chuyên biệt bên trong hệ đa mô hình

Một ứng dụng đặt dịch vụ có thể cần lưu **thông tin nhà cung cấp dưới dạng document**, tìm những nhà cung cấp **gần vị trí khách hàng**, tra cứu theo **mô tả tự nhiên**, khám phá **quan hệ giữa khách hàng và dịch vụ**, phân tích **lịch sử hoạt động theo thời gian** và đề xuất những lựa chọn **tương tự về ngữ nghĩa**. Nếu mỗi nhu cầu được xử lý bằng một loại cơ sở dữ liệu riêng, ứng dụng phải đồng bộ nhiều bản sao dữ liệu, vận hành nhiều hệ thống và giải quyết các vấn đề nhất quán giữa chúng.

Một **hệ cơ sở dữ liệu đa mô hình (multi-model database)** hướng đến việc hỗ trợ nhiều kiểu biểu diễn dữ liệu hoặc nhiều nhóm thao tác trên cùng một nền tảng. Khả năng này có thể gồm document, key-value, graph, full-text search, geospatial, time series và vector search. Tuy nhiên, **cùng được quảng bá dưới nhãn “đa mô hình” không bảo đảm tất cả năng lực đều có cùng cách lưu, chung cú pháp truy vấn, cùng phạm vi transaction hoặc cập nhật index tức thời**.

Bài học tập trung vào câu hỏi: **khả năng chuyên biệt hoạt động bên trong một hệ đa mô hình như thế nào, khi nào nên sử dụng và cần kiểm tra những ranh giới nào trước khi thiết kế ứng dụng?** Ví dụ sử dụng một nền tảng dịch vụ và minh họa cú pháp cụ thể bằng một số cơ sở dữ liệu phổ biến. Cú pháp, index, độ nhất quán và giới hạn thực tế phụ thuộc sản phẩm, phiên bản, cấu hình và phương thức triển khai.

## 1. Từ “đa mô hình” đến “năng lực chuyên biệt”

Trước tiên cần tách ba khái niệm thường bị dùng lẫn nhau.

| Khái niệm | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| **Mô hình dữ liệu** | Thực thể được biểu diễn và liên kết ra sao? | Document, graph, key-value, wide-column |
| **Năng lực chuyên biệt** | Hệ thống tối ưu cho phép truy vấn hoặc xử lý gì? | Tìm kiếm từ khóa, đường đi trên graph, khoảng cách địa lý, tìm vector gần nhất, tổng hợp theo thời gian |
| **Kiến trúc triển khai** | Những năng lực đó nằm ở đâu và chia sẻ những gì? | Một engine, nhiều engine trong cùng dịch vụ, hoặc nhiều hệ lưu trữ đồng bộ bằng event |

Document database có thể cung cấp tìm kiếm địa lý mà không cần gọi đó là mô hình graph. Một graph database có thể có full-text index để tìm đỉnh, nhưng full-text search không vì vậy trở thành cùng một thao tác với graph traversal. Một nền tảng cung cấp nhiều API cũng không chắc cho phép cùng một bản ghi được truy vấn trực tiếp bằng tất cả API ấy.

### Ba kiến trúc dễ bị nhầm

1. **Một engine hỗ trợ nhiều mô hình hoặc kiểu truy vấn:** dữ liệu và các cấu trúc chuyên biệt nằm dưới cùng sản phẩm/engine; có thể có một ngôn ngữ truy vấn chung hoặc nhiều lớp truy vấn.
2. **Một dịch vụ quản lý nhiều API/mô hình:** nhà cung cấp thống nhất vận hành và giao diện quản trị, nhưng từng API có thể dùng tài khoản, định dạng, chỉ mục, transaction hoặc tập dữ liệu tách biệt.
3. **Polyglot persistence:** ứng dụng dùng nhiều sản phẩm chuyên môn hóa, chẳng hạn document database làm nguồn dữ liệu chính, search engine cho tìm kiếm và graph engine cho quan hệ.

Cả ba cách đều có thể đáp ứng nghiệp vụ. Khi đọc tài liệu của một sản phẩm “multi-model”, cần kiểm tra **dữ liệu có được chia sẻ thật không**, **truy vấn có thể kết hợp trong một lần thực thi không**, và **cập nhật ở mô hình này bao lâu mới nhìn thấy ở mô hình kia**.

## 2. Một ví dụ nghiệp vụ có nhiều mô hình

Giả sử nền tảng đặt dịch vụ có các thực thể:

- **Provider:** nhà cung cấp dịch vụ, gồm tên, địa chỉ, mô tả và danh mục.
- **Service:** dịch vụ được cung cấp, giá, điều kiện, thời lượng.
- **Customer:** khách hàng có quyền truy cập theo tenant hoặc tài khoản.
- **Booking:** lượt đặt dịch vụ và trạng thái xử lý.
- **Interaction:** lượt xem, tìm kiếm, đánh giá và sự kiện theo thời gian.
- **Relation:** nhà cung cấp thuộc danh mục nào, khách từng sử dụng dịch vụ nào, dịch vụ nào liên quan dịch vụ nào.
- **Embedding:** vector biểu diễn ngữ nghĩa của tên hoặc mô tả dịch vụ.

Một document mô tả dịch vụ có thể là:

~~~json
{
  "_id": "svc-101",
  "tenantId": "tenant-a",
  "providerId": "pro-17",
  "title": "Bảo trì máy lạnh tại nhà",
  "description": "Vệ sinh, kiểm tra gas và vận hành máy lạnh dân dụng",
  "category": "home-maintenance",
  "priceMinor": 350000,
  "currency": "VND",
  "status": "ACTIVE",
  "location": {
    "type": "Point",
    "coordinates": [106.7009, 10.7769]
  },
  "tags": ["may-lanh", "ve-sinh", "tai-nha"],
  "updatedAt": "2026-11-14T08:00:00Z"
}
~~~

Hệ thống có thể cần trả lời:

| Yêu cầu | Mô hình/năng lực thường phù hợp | Điều kiện kết quả đúng |
|---|---|---|
| Lấy chi tiết `svc-101` | Document hoặc key-value lookup | Đúng dịch vụ và quyền truy cập |
| Tìm dịch vụ có cụm “bảo trì máy lạnh” | Full-text search | Phân tích ngôn ngữ, xếp hạng và filter chính xác |
| Tìm dịch vụ trong bán kính 5 km | Geospatial | Tọa độ, đơn vị, hình học và khoảng cách đúng |
| Tìm chuỗi quan hệ khách → dịch vụ → nhà cung cấp | Graph traversal | Quan hệ có hướng, giới hạn số bước và phạm vi tenant |
| Đếm booking theo từng giờ | Time-series/aggregation | Thời điểm, múi giờ, dữ liệu đến muộn và retention |
| Tìm dịch vụ tương tự ý định “máy lạnh không mát” | Vector search | Embedding tương thích, độ liên quan và filter bắt buộc |

Đây không phải lý do bắt buộc phải dùng sáu database khác nhau. Một hệ đa mô hình có thể hỗ trợ nhiều nhu cầu trên cùng nền tảng, nhưng cần so sánh **năng lực cụ thể** với **yêu cầu thực tế**.

## 3. Hệ đa mô hình lưu những gì, và phần nào là nguồn sự thật?

Một cách nhìn hữu ích:

~~~mermaid
flowchart TD
    A["Ứng dụng đặt dịch vụ"] --> B["API và quy tắc nghiệp vụ"]
    B --> C["Nguồn dữ liệu chính: Service / Provider / Booking"]
    C --> D["Full-text index"]
    C --> E["Geospatial index"]
    C --> F["Graph vertices / edges"]
    C --> G["Vector index"]
    C --> H["Time-series / rollup"]
    D --> I["Query + ranking + filter"]
    E --> I
    F --> I
    G --> I
    H --> I
    I --> J["Kết quả theo quyền người dùng"]
~~~

Đây là sơ đồ **logic**, không khẳng định mọi hệ quản trị đều xây dựng từng cấu trúc theo cách trên.

Nếu một nền tảng đa mô hình lưu document chính và xây nhiều loại index trên document, index là **cách truy cập dữ liệu**, không nhất thiết là bản sao nghiệp vụ độc lập. Nếu graph hoặc search chạy trên kho riêng, chúng có thể là **projection** được tạo từ nguồn dữ liệu chính qua event/CDC. Hai cách kéo theo trách nhiệm khác nhau:

- Nguồn sự thật: nơi nào quyết định giá, trạng thái đặt chỗ hoặc quyền sở hữu có hiệu lực?
- Cập nhật: đổi tên dịch vụ hoặc xóa nhà cung cấp làm thay đổi index/edge/vector thế nào?
- Giao dịch: việc sửa document và cập nhật cấu trúc tìm kiếm có nguyên tử không?
- Khôi phục: sau backup/restore có cần dựng lại index và projection không?
- Lỗi đồng bộ: một kết quả tìm kiếm cũ có thể trỏ tới dịch vụ đã ngừng hoạt động không?

**Dùng một sản phẩm không mặc nhiên làm mọi mô hình nhất quán tức thời.** Phải hiểu rõ từng đường ghi và mức độ mới của kết quả.

## 4. Năng lực document: nền tảng linh hoạt cho thực thể

Mô hình document phù hợp khi một thực thể có cấu trúc lồng nhau và thường được đọc hoặc cập nhật như một đơn vị.

Ví dụ:

~~~json
{
  "_id": "pro-17",
  "name": "Điện lạnh An Tâm",
  "contacts": {
    "phone": "+84xxxxxxxxx",
    "email": "contact@example.invalid"
  },
  "serviceArea": {
    "cities": ["Ho Chi Minh City", "Binh Duong"],
    "remoteSupport": false
  },
  "certifications": [
    { "code": "CERT-A", "issuedYear": 2024 },
    { "code": "CERT-B", "issuedYear": 2025 }
  ]
}
~~~

Document cho phép mô hình hóa phần thuộc tính gắn với nhà cung cấp mà không buộc mỗi nhà cung cấp có đúng cùng danh sách chứng chỉ. Nhưng việc “linh hoạt” không có nghĩa bỏ validation:

- `providerId` và `tenantId` phải có kiểu và ý nghĩa rõ ràng.
- Danh sách chứng chỉ có thể được kiểm tra theo quy tắc nghiệp vụ.
- Mảng tăng không giới hạn gây vấn đề kích thước document và cập nhật đồng thời.
- Nếu truy vấn thường xuyên cần lọc theo chứng chỉ, index vào đường dẫn thích hợp có thể cần thiết.

Document là **nguồn thực thể** tốt, nhưng không vì vậy mà mọi bài toán quan hệ sâu, ranking văn bản, cửa sổ thời gian hay độ tương đồng vector đều nên viết bằng thao tác quét document thông thường.

## 5. Năng lực graph: truy vấn quan hệ như đối tượng hạng nhất

Trong mô hình graph, dữ liệu thường được nhìn thành **đỉnh (vertex)** và **cạnh (edge)**. Đỉnh biểu diễn thực thể; cạnh biểu diễn quan hệ có hướng hoặc vô hướng theo mô hình của engine.

~~~text
Customer (cus-7)
  ├── BOOKED ──> Service (svc-101)
  ├── FOLLOWS ──> Provider (pro-17)
  └── REVIEWED ──> Service (svc-205)

Service (svc-101)
  ├── OFFERED_BY ──> Provider (pro-17)
  └── RELATED_TO ──> Service (svc-205)
~~~

Document mô tả `service.relatedServiceIds` cũng lưu được liên kết, nhưng khi yêu cầu thành “tìm mọi dịch vụ liên quan trong hai hoặc ba bước, không đi qua nhà cung cấp bị khóa”, **graph traversal** thường phù hợp hơn một chuỗi truy vấn tự dựng ở ứng dụng.

### Những truy vấn chuyên biệt của graph

| Kiểu thao tác | Câu hỏi nghiệp vụ | Điều phải định nghĩa |
|---|---|---|
| Traversal theo độ sâu | Các dịch vụ liên quan trong tối đa 3 bước? | Hướng cạnh, giới hạn độ sâu, loại cạnh |
| Shortest path | Quan hệ ngắn nhất giữa hai thực thể là gì? | Có trọng số hay không, cạnh được phép |
| Reachability | Khách có thể truy cập dịch vụ qua nhóm quyền nào? | Quy tắc đường đi và bảo mật |
| Pattern matching | Những provider nào có khách từng đặt dịch vụ A rồi B? | Thứ tự, loại quan hệ, thời gian |
| Centrality/community | Provider hoặc dịch vụ nào nằm ở vị trí trung tâm mạng? | Thuật toán, batch/online, chi phí tính toán |

**Graph traversal không chỉ là JOIN nhiều lần.** Ý nghĩa truy vấn gắn với **đường đi**: có bao nhiêu bước, đi theo hướng nào, đi qua loại đỉnh/cạnh nào và có cho phép lặp đỉnh/cạnh không.

### Ví dụ minh họa cú pháp AQL của ArangoDB

Một hệ hỗ trợ document và graph như ArangoDB có thể truy vấn document và graph bằng AQL. Ví dụ sau giả định đã có collection `services` và một named graph `serviceRelations` với định nghĩa vertex/edge phù hợp.

~~~aql
FOR service IN services
  FILTER service.tenantId == @tenantId
  FILTER service.status == "ACTIVE"
  RETURN {
    id: service._id,
    title: service.title
  }
~~~

Ví dụ traversal:

~~~aql
FOR vertex, edge, path IN 1..2 OUTBOUND @startVertex
  GRAPH "serviceRelations"
  FILTER vertex.tenantId == @tenantId
  RETURN DISTINCT {
    id: vertex._id,
    title: vertex.title,
    relationType: edge.type
  }
~~~

Trong các ví dụ, `@tenantId` và `@startVertex` là bind parameters. `@startVertex` là định danh vertex hợp lệ, chẳng hạn dạng `collection/key` theo cấu hình. Tên collection và graph được định nghĩa trong hệ thống.

**Lưu ý bảo mật:** chỉ lọc `vertex.tenantId` trên vertex được trả về **chưa bảo đảm traversal không đi qua cạnh hoặc đỉnh của tenant khác**. Nếu graph dùng chung cho nhiều tenant, phải thiết kế cạnh hợp lệ, ràng buộc tenant cho cả đường đi, chặn traversal xuyên tenant và kiểm tra quyền từ vertex đầu vào. Ví dụ AQL trên nhằm minh họa **cú pháp traversal**, không phải chính sách phân quyền hoàn chỉnh.

### Khi graph không phải lựa chọn tốt

- Dữ liệu chỉ có một vài quan hệ đơn giản, đọc bằng ID là đủ.
- Query chủ yếu trả một document đầy đủ theo khóa.
- Cần ghi dữ liệu thời gian rất lớn nhưng hầu như không duyệt quan hệ.
- Cạnh quá dày hoặc có **supernode** với hàng triệu quan hệ khiến traversal lan rộng.
- Yêu cầu đường đi dài làm số tổ hợp tăng rất nhanh.

Số đỉnh/cạnh không tự nói lên chi phí. Cần xét **độ phân nhánh, độ sâu traversal, độ chọn lọc, phân vùng graph và mức chia sẻ đường đi giữa partition**.

## 6. Năng lực tìm kiếm toàn văn: hiểu văn bản thay vì so sánh chuỗi thô

Truy vấn kiểu:

~~~text
title == "bảo trì máy lạnh"
~~~

chỉ là so sánh giá trị. Một công cụ **full-text search** có thể hỗ trợ tách từ, chuẩn hóa, xếp hạng độ liên quan và tìm nhiều cách diễn đạt của cùng nhu cầu.

### Quy trình đơn giản hóa

~~~mermaid
flowchart LR
    A["Document văn bản"] --> B["Analyzer: tokenization, normalization"]
    B --> C["Inverted index: token → document"]
    D["Câu truy vấn"] --> E["Query analyzer"]
    E --> C
    C --> F["Candidate matching"]
    F --> G["Ranking và filter"]
    G --> H["Kết quả"]
~~~

Một **inverted index** ánh xạ token sang danh sách document có token đó. Thông thường engine còn lưu thêm thông tin vị trí, tần suất, thống kê corpus hoặc metadata khác để hỗ trợ phrase query và ranking.

Các năng lực có thể gồm:

- **Tokenization:** chia văn bản thành token.
- **Normalization:** xử lý chữ hoa/thường, dấu, ký tự và dạng chữ theo analyzer.
- **Stemming/lemmatization:** đưa từ về dạng gốc theo ngôn ngữ nếu engine hỗ trợ.
- **Phrase search:** tìm cụm từ với điều kiện thứ tự và khoảng cách từ.
- **Fuzzy search:** tìm gần đúng khi có lỗi gõ, với chi phí và quy tắc cụ thể.
- **Relevance scoring:** tính độ liên quan, ví dụ các họ scoring dựa trên BM25.
- **Field boosting:** ưu tiên khớp ở tiêu đề hơn mô tả nếu hợp đồng tìm kiếm quy định.

**Ngôn ngữ quan trọng.** Tách từ tiếng Việt, xử lý dấu và tên riêng không thể giả định sẽ có chất lượng tương tự tiếng Anh. Query `"sửa điều hòa"` và document `"bảo dưỡng máy lạnh"` còn khác nhau về ngữ nghĩa; full-text thuần túy có thể không kết nối chúng tốt nếu thiếu từ đồng nghĩa hoặc một phương pháp semantic search.

### Kết quả tìm kiếm còn cần filter nghiệp vụ

Giả sử query trả những dịch vụ phù hợp từ khóa nhưng có dịch vụ thuộc tenant khác hoặc đã tạm ngừng. Ứng dụng phải giới hạn:

~~~text
tenantId = người dùng được phép
AND status = ACTIVE
AND match_full_text(title, description, query)
ORDER BY relevance DESC
~~~

Filter phân quyền và trạng thái phải áp dụng ở **đúng thời điểm** trong pipeline. Nếu chỉ lấy top 10 toàn hệ thống rồi sau đó lọc tenant, có thể nhận ít kết quả hợp lệ và bỏ sót các dịch vụ phù hợp của tenant vì chúng không nằm trong top 10 ban đầu.

### Chỉ mục tìm kiếm có thể không nhìn thấy dữ liệu mới ngay

Một số kiến trúc duy trì inverted index bất đồng bộ hoặc có chính sách refresh. Vì vậy, một document vừa được ghi thành công có thể chưa xuất hiện trong kết quả search ngay lập tức. Nếu nghiệp vụ cần “ngay sau khi đăng dịch vụ phải tìm được”, phải kiểm tra **read-after-write visibility** của năng lực search trong sản phẩm đang dùng.

## 7. Năng lực geospatial: vị trí là dữ liệu có hình học

Một hệ thống đặt dịch vụ có thể cần:

- Nhà cung cấp trong bán kính 5 km.
- Cửa hàng nằm trong một đa giác khu vực phục vụ.
- Điểm giao hàng gần nhất theo khoảng cách.
- Bản ghi nằm trong vùng địa lý đã lưu.

Một vị trí không chỉ là hai con số tùy ý. Cần biết **hệ tọa độ**, thứ tự trục, đơn vị và hình học mà database hiểu.

### Ví dụ GeoJSON Point

~~~json
{
  "location": {
    "type": "Point",
    "coordinates": [106.7009, 10.7769]
  }
}
~~~

Với GeoJSON tọa độ địa lý phổ biến trong MongoDB, mảng theo thứ tự **[kinh độ, vĩ độ]**. Dùng nhầm [vĩ độ, kinh độ] khiến điểm dữ liệu nằm sai vị trí, dù hai số đều hợp lệ.

### Ví dụ MongoDB với 2dsphere index

MongoDB là document database có năng lực geospatial; ví dụ này minh họa **năng lực chuyên biệt tích hợp trong một hệ document**, không ngụ ý MongoDB hỗ trợ tất cả mô hình graph/time-series/vector bằng cùng một cơ chế.

~~~javascript
db.providers.createIndex({
  location: "2dsphere"
});

db.providers.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      $maxDistance: 5000
    }
  }
});
~~~

Trong ví dụ dùng GeoJSON Point và `2dsphere` index, `$maxDistance` được hiểu theo **mét**. Truy vấn tìm tài liệu gần điểm đã cho trong phạm vi tối đa 5.000 m theo ngữ nghĩa geospatial tương ứng. Cần kiểm tra phiên bản và các hạn chế của `$near` với toán tử khác, index và cấu trúc query.

### Khoảng cách địa lý và thời gian di chuyển khác nhau

Hai điểm cách nhau 2 km đường chim bay có thể phải đi đường bộ 7 km hoặc mất 20 phút. Geospatial index phù hợp với vị trí và hình học; **routing trên mạng đường** là bài toán bổ sung, có thể cần graph hoặc dịch vụ định tuyến riêng.

Các lưu ý:

- Khai báo CRS và thứ tự tọa độ thống nhất.
- Với vùng phục vụ, phân biệt **điểm nằm trong polygon** và **khoảng cách đến tâm**.
- Dữ liệu gần cực, đường đổi ngày và đa giác phức tạp cần xử lý đúng semantics địa lý.
- Vị trí di chuyển liên tục có tần suất cập nhật và thời gian hiệu lực khác địa chỉ tĩnh.
- Địa điểm và lịch sử vị trí có thể là thông tin nhạy cảm; quyền truy cập và chính sách lưu giữ phải rõ ràng.

## 8. Năng lực time-series: dữ liệu thay đổi theo thời gian

Time series là dữ liệu với trục thời gian mang ý nghĩa thiết yếu, chẳng hạn:

- Nhiệt độ thiết bị theo phút.
- Số booking theo giờ.
- Số request và latency theo mốc thời gian.
- Vị trí phương tiện theo thời điểm ghi nhận.
- Giá hoặc mức tồn kho được quan sát theo thời gian.

Một bản ghi sự kiện có thể là:

~~~json
{
  "tenantId": "tenant-a",
  "deviceId": "dev-51",
  "eventTime": "2026-11-14T08:10:00Z",
  "ingestedAt": "2026-11-14T08:10:04Z",
  "metrics": {
    "temperatureC": 24.6,
    "batteryPercent": 81
  }
}
~~~

### Cần phân biệt hai mốc thời gian

- **Event time:** thời điểm sự kiện xảy ra tại nguồn.
- **Ingestion time:** thời điểm hệ thống nhận hoặc lưu sự kiện.

Nếu thiết bị mất mạng rồi gửi bù, event có thể đến muộn 2 giờ. Đếm theo ingestion time sẽ ra biểu đồ khác với đếm theo event time. Không nên dùng một trường `createdAt` mơ hồ cho cả hai mục đích.

### Những năng lực time-series chuyên biệt

| Năng lực | Ý nghĩa | Tác động |
|---|---|---|
| Phân vùng theo thời gian | Gom hoặc tổ chức dữ liệu theo khoảng thời gian | Hỗ trợ đọc phạm vi, retention, quản trị dữ liệu |
| Tối ưu ghi append | Tập trung xử lý nhiều sự kiện mới | Giảm chi phí cho workload ghi liên tục tùy engine |
| Window aggregation | Tổng hợp 1 phút, 5 phút, 1 giờ | Tạo dashboard và cảnh báo |
| Downsampling/rollup | Lưu dữ liệu tổng hợp sau một thời gian | Giảm dung lượng và thời gian query lịch sử |
| Retention/TTL | Xóa dữ liệu vượt thời gian giữ | Kiểm soát chi phí và chính sách lưu giữ |
| Lưu tag/measurement | Chia theo thiết bị, tenant, metric | Ảnh hưởng index và phân bố workload |

Ví dụ một câu hỏi dữ liệu:

> “Tính số booking đã hoàn tất theo từng giờ của tenant-a trong 7 ngày.”

Để kết quả đúng cần thống nhất: tính theo thời điểm tạo hay hoàn tất, sử dụng UTC hay múi giờ kinh doanh, các booking được sửa trạng thái muộn có được cập nhật vào bucket cũ không, có loại sự kiện trùng do retry không.

### Khó khăn thường gặp

1. **Event đến muộn hoặc sai thứ tự.** Window “đã đóng” có được tính lại không?
2. **Độ chính xác timestamp.** Millisecond và second không thể trộn mà không quy đổi.
3. **Cardinality của tag.** Hàng triệu `deviceId` hoạt động cùng lúc có thể tạo chi phí index/metadata cao.
4. **Dữ liệu trùng.** Retry cần định danh sự kiện/idempotency khi muốn đúng số liệu.
5. **Retention.** Xóa raw event sau 30 ngày nhưng giữ báo cáo 12 tháng cần kế hoạch rollup và backfill rõ ràng.
6. **Tải đọc và ghi đối lập.** Dashboard aggregation lớn có thể cạnh tranh tài nguyên với ingest.

Năng lực time-series trong một hệ đa mô hình có thể tiện khi cần kết hợp dữ liệu thời gian với document chủ. Nhưng nếu lưu lượng ingest cực lớn, query phân tích nặng hoặc retention rất khác giao dịch online, một hệ chuyên dụng/warehouse có thể phù hợp hơn.

## 9. Năng lực vector search: tìm gần theo biểu diễn ngữ nghĩa

**Embedding** là vector số được một mô hình tạo từ văn bản, hình ảnh hoặc dữ liệu khác. Khi hai đối tượng có ngữ nghĩa gần nhau, embedding được huấn luyện phù hợp có thể khiến chúng gần nhau theo một metric đã chọn.

Ví dụ ý định:

> “Máy lạnh đang chạy nhưng không mát, cần thợ đến kiểm tra.”

Một danh mục dịch vụ có thể không chứa đúng các từ “không mát”. Full-text search có thể bỏ lỡ một số kết quả; vector search có thể giúp tìm các dịch vụ có nội dung gần với ý định.

### Dạng dữ liệu khái niệm

~~~json
{
  "serviceId": "svc-101",
  "embeddingModel": "embedding-model-v1",
  "embeddingVersion": 1,
  "embedding": [0.12, -0.03, 0.08, 0.19],
  "language": "vi"
}
~~~

Vector bốn chiều chỉ là **ví dụ minh họa hình dạng dữ liệu**. Embedding thật có thể có hàng trăm hoặc hàng nghìn chiều, và chiều dài phải khớp cấu hình index/metric của mô hình đang dùng.

### Các thành phần cần phân biệt

- **Model sinh vector:** quyết định cách nội dung biến thành biểu diễn số.
- **Dimension:** số phần tử của vector; index phải tương thích.
- **Distance/similarity metric:** cosine, inner product, Euclidean hoặc metric khác.
- **Vector index/ANN:** cấu trúc hỗ trợ tìm láng giềng gần đúng trong dữ liệu lớn.
- **Kết quả top-k:** danh sách ứng viên gần nhất theo metric/index.
- **Business filters:** tenant, trạng thái, quyền truy cập, khu vực, mức giá.
- **Reranking:** sắp xếp lại ứng viên dựa trên tiêu chí chính xác hoặc mô hình khác.

### Exact nearest neighbor và approximate nearest neighbor

Tìm kiếm chính xác theo khoảng cách có thể so sánh query vector với mọi vector hợp lệ; với tập dữ liệu lớn, chi phí cao. **Approximate nearest neighbor (ANN)** dùng index để giảm công việc và tăng tốc, đổi lại có thể bỏ sót một số láng giềng chính xác.

Cần đo:

- **Recall@k:** bao nhiêu kết quả đúng trong tập top-k chuẩn được tìm thấy?
- **Latency p95/p99:** truy vấn có đáp ứng mục tiêu hay không?
- **Độ liên quan nghiệp vụ:** kết quả có thật sự giúp người dùng, không chỉ gần về số?
- **Hiệu quả khi filter:** filter tenant/status có thay đổi recall hoặc latency không?
- **Chi phí cập nhật index:** dữ liệu có thường xuyên đổi vector không?

Một vector index không tạo ra sự hiểu biết nghiệp vụ tự động. Mô hình embedding kém với dữ liệu tiếng Việt hoặc không phù hợp lĩnh vực có thể khiến kết quả “gần” nhưng không hữu ích.

### Tương thích phiên bản embedding

Không nên trộn tùy tiện vector của các mô hình khác nhau trong cùng không gian tìm kiếm. Ngay cả khi số chiều giống nhau, ý nghĩa các chiều và phân bố vector có thể khác.

Nếu nâng cấp embedding model:

1. Công bố version của embedding hiện tại và version đích.
2. Quyết định có duy trì hai index/collection trong giai đoạn chuyển đổi không.
3. Tạo lại embedding cho dữ liệu nguồn theo kế hoạch backfill.
4. Chuyển query embedding sang model tương ứng với index được dùng.
5. Đo chất lượng và chi phí trước khi bỏ phiên bản cũ.

### Vector search và thông tin bị hạn chế

Nếu vector chứa nội dung của document riêng tư, một truy vấn không được phép không nên có cơ hội suy ra tài liệu của tenant khác từ ranking hoặc kết quả gần. Cần filter phân quyền với **ngữ nghĩa bảo đảm rõ ràng** trong quá trình candidate retrieval, kiểm tra lại quyền khi lấy document gốc, và kiểm soát cách lưu/ghi log dữ liệu truy vấn.

## 10. Năng lực key-value, cache và truy cập theo ID

Một hệ đa mô hình thường có thao tác lấy document/item bằng khóa rất nhanh. Nhưng cần phân biệt:

- **Đọc theo primary key từ database nguồn.**
- **Cache key-value** lưu bản sao kết quả để giảm đọc.
- **Trạng thái phiên** có TTL.
- **Bộ đếm hoặc trạng thái tạm thời** với yêu cầu đồng thời riêng.

Ví dụ:

~~~text
Key: service:svc-101
Value: JSON của dịch vụ đang hoạt động
TTL: 120 giây
~~~

Cache có thể tăng tốc trang chi tiết nhưng kéo theo câu hỏi:

- Nếu dịch vụ bị khóa ngay sau khi ghi cache, cache có còn trả nó cho người dùng không?
- TTL dài nhất được chấp nhận cho giá hoặc trạng thái là bao nhiêu?
- Khi cache bị xóa hàng loạt, database chịu được bao nhiêu request đồng thời?
- Có cần chống cache stampede hoặc request coalescing không?
- Mỗi tenant có namespace và quyền truy cập chính xác không?

Đừng xem cache như nguồn sự thật của booking hoặc thanh toán nếu quy tắc nghiệp vụ không cho phép mất dữ liệu hay đọc giá trị cũ. Có thể dùng cache cho khám phá/tìm kiếm, nhưng khi thực hiện giao dịch cần **đọc và kiểm tra lại nguồn dữ liệu có thẩm quyền** theo mức nhất quán yêu cầu.

## 11. Năng lực phân tích: tổng hợp và cấu trúc cột

Một số nền tảng đa mô hình cung cấp aggregation, index hướng cột hoặc công cụ phân tích tích hợp để trả lời những câu hỏi như:

- Số booking theo khu vực mỗi ngày.
- Doanh thu theo nhà cung cấp và nhóm dịch vụ.
- Phân phối điểm đánh giá theo tháng.
- Tỷ lệ chuyển đổi từ lượt xem sang đặt dịch vụ.

Truy vấn phân tích thường đọc nhiều bản ghi và gom nhóm, rất khác point lookup theo ID. Cần cân nhắc:

| Workload | Đặc điểm | Nút thắt thường gặp |
|---|---|---|
| **OLTP** | Đọc/ghi từng thực thể, độ trễ thấp, yêu cầu nhất quán | Tranh chấp ghi, index, latency đuôi |
| **Search** | Lấy ứng viên theo token, geo, vector và ranking | Fan-out index, refresh, recall, ranking |
| **Graph** | Duyệt nhiều cạnh/đỉnh có điều kiện | Độ phân nhánh, traversal depth, partition hops |
| **Time-series** | Ghi liên tục, lọc theo mốc thời gian | Ingest throughput, retention, cardinality |
| **OLAP/aggregation** | Quét và nhóm nhiều bản ghi | CPU, RAM, I/O, shuffle và cạnh tranh tài nguyên |

Dùng một engine cho OLTP và phân tích có thể giảm độ phức tạp tích hợp, nhưng truy vấn báo cáo nặng có thể tranh tài nguyên với booking thời gian thực. Cần xem **isolation tài nguyên**, read replica/compute tách biệt, giới hạn truy vấn hoặc pipeline xuất dữ liệu sang hệ phân tích riêng.

## 12. Truy vấn kết hợp nhiều khả năng: sức mạnh và ranh giới

Yêu cầu thực tế ít khi thuần một mô hình:

> “Tìm 10 dịch vụ bảo trì máy lạnh gần tôi trong bán kính 5 km, đang mở, có đánh giá tốt, từng được những khách hàng tương tự sử dụng, và xếp theo độ liên quan.”

Truy vấn cần phối hợp:

1. **Search:** hiểu từ khóa/ngữ nghĩa “bảo trì máy lạnh”.
2. **Geo:** giới hạn điểm cung cấp dịch vụ.
3. **Document:** kiểm tra tenant, trạng thái, danh mục, giá.
4. **Graph:** tìm quan hệ từ khách đến nhóm dịch vụ liên quan.
5. **Aggregation:** điểm đánh giá được tổng hợp theo chính sách.
6. **Ranking:** kết hợp nhiều tín hiệu thành kết quả cuối.

### Một pipeline minh họa

~~~mermaid
flowchart TD
    A["Từ khóa + tọa độ + ngữ cảnh người dùng"] --> B["Kiểm tra quyền và chuẩn hóa input"]
    B --> C["Tìm ứng viên bằng text/vector + geo"]
    C --> D["Lọc tenant, trạng thái, điều kiện cung cấp"]
    D --> E["Bổ sung tín hiệu graph và đánh giá"]
    E --> F["Tính điểm và sắp xếp"]
    F --> G["Đọc document hiện hành để xác nhận"]
    G --> H["Trả trang kết quả và cursor"]
~~~

**Thứ tự trên là ý tưởng logic**, không khẳng định mọi engine chạy tuần tự theo đúng sơ đồ. Query optimizer có thể đẩy điều kiện lọc xuống index sớm hơn hoặc thực thi song song.

### Ví dụ pseudo-query để làm rõ yêu cầu

~~~text
INPUT:
  tenant = tenant-a
  query = "máy lạnh không mát"
  location = (latitude: 10.7769, longitude: 106.7009)
  maxDistance = 5000 meters

CANDIDATES = semantic_or_text_search(
  query,
  where tenantId = tenant
    AND status = ACTIVE
)

NEARBY = geo_filter(CANDIDATES, location, maxDistance)

RANKED = rank(
  NEARBY,
  textScore,
  vectorScore,
  distanceScore,
  verifiedRatingScore
)

OUTPUT = hydrate_and_authorize(RANKED, limit = 10)
~~~

Đây là **pseudo-code độc lập sản phẩm**, không phải cú pháp query chạy trực tiếp.

Cần trả lời những câu hỏi kỹ thuật trước khi triển khai:

- Filter áp dụng **trước hay sau** tìm vector gần nhất? Kết quả có bị thiếu khi top-k bị lọc mạnh không?
- Search index có thấy cập nhật trạng thái mới nhất không?
- Điểm graph hoặc đánh giá được tính realtime hay dùng dữ liệu tổng hợp?
- Nếu một nguồn tín hiệu chưa sẵn sàng, trả kết quả suy giảm tính năng hay báo lỗi?
- Có cần giải thích vì sao một kết quả xếp hạng cao?
- Phân trang qua ranking thay đổi liên tục sẽ nhất quán đến mức nào?

## 13. Một câu truy vấn có thể kết hợp không có nghĩa một transaction được bảo đảm

Đây là giới hạn rất quan trọng của hệ đa mô hình.

Giả sử một nhà cung cấp ngừng hoạt động. Ứng dụng muốn:

1. Đổi `provider.status` thành `INACTIVE`.
2. Ngừng hiển thị mọi dịch vụ của họ.
3. Loại nhà cung cấp khỏi kết quả full-text và vector.
4. Ngăn booking mới.
5. Cập nhật quan hệ graph và chỉ số báo cáo.

Những bước này không nhất thiết nằm trong **một transaction nguyên tử**.

| Thành phần | Điều cần kiểm tra |
|---|---|
| Document gốc | Transaction hỗ trợ trên phạm vi document, collection hay nhiều shard? |
| Graph edge | Cạnh có nằm trong cùng phạm vi transaction với document đỉnh không? |
| Search index | Index cập nhật đồng bộ hay qua refresh/event? |
| Vector index | Xóa/chỉnh embedding có hiệu lực ngay không? |
| Time-series/analytics | Chỉ số tổng hợp được tính lại bằng cơ chế nào? |
| Cache | TTL hoặc invalidation có làm dữ liệu cũ lộ ra không? |

### Một thiết kế an toàn theo nghĩa nghiệp vụ

Với hành động **tạo booking**, dù search vừa trả một dịch vụ “đang mở”, service vẫn phải kiểm tra trạng thái khả dụng và quyền tại nguồn có thẩm quyền ngay trước thao tác đặt. Nếu một transaction/conditional write phù hợp hỗ trợ ràng buộc, áp dụng cơ chế đó để chặn đặt dịch vụ đã khóa.

Search, graph, cache hoặc vector có thể phục vụ **khám phá và gợi ý**. Những bất biến như “không đặt được khi provider đã khóa” phải được bảo vệ trong đường ghi nghiệp vụ, không chỉ bằng việc ẩn kết quả khỏi index.

### Eventual consistency không phải lỗi mặc định

Nếu yêu cầu là thống kê số lượt xem theo giờ, chậm vài phút có thể chấp nhận được. Nếu yêu cầu là không cho hai khách đặt cùng một slot, chậm vài phút là không chấp nhận được. Thiết kế phải chọn chính sách nhất quán **theo từng thao tác**, thay vì yêu cầu mọi hệ thống đồng bộ tức thì một cách không cần thiết.

## 14. Khóa, identity và quan hệ giữa các mô hình

Để phối hợp document, graph, search và vector, cần một **định danh ổn định**.

Ví dụ:

~~~text
serviceId = svc-101  (ID nghiệp vụ kỹ thuật ổn định)
document._id = svc-101
graphVertex.serviceId = svc-101
searchDocument.serviceId = svc-101
vectorRecord.serviceId = svc-101
event.serviceId = svc-101
~~~

Dù các hệ dùng ID nội bộ khác nhau, nên có cách ánh xạ rõ ràng về `serviceId` được ứng dụng tin cậy.

Nếu dùng title hoặc tên nhà cung cấp làm khóa liên kết, một lần đổi tên có thể phá vỡ graph edges, embedding mapping hoặc đồng bộ search. Nếu dùng ID nhưng không mang `tenantId` ở những nơi cần thiết, có thể gắn nhầm dữ liệu giữa các tenant.

### Phạm vi duy nhất phải được định nghĩa

- `serviceId` toàn cục hay chỉ duy nhất trong tenant?
- `providerId` do nền tảng cấp hay nhà cung cấp tự nhập?
- Cạnh `BOOKED` có thể trùng cho hai booking khác nhau không?
- Sự kiện có `eventId` để tránh nhập lặp không?
- Embedding được phân biệt bằng `(serviceId, modelVersion)` không?
- Các bản ghi lịch sử có cần giữ sau khi document chính bị xóa không?

Mô hình đa năng không tự giải quyết danh tính. **Tính nhất quán của identity** là một nền tảng để các năng lực chuyên biệt phối hợp được với nhau.

## 15. Index chuyên biệt và chi phí write amplification

Khi lưu một dịch vụ, engine có thể phải cập nhật nhiều cấu trúc:

~~~text
Document source
  ├── Index theo tenant + status
  ├── Full-text index theo title + description
  ├── Geospatial index theo location
  ├── Graph adjacency / edge indexes
  ├── Vector index theo embedding
  └── Aggregate / projection phục vụ dashboard
~~~

Mỗi index làm một số query nhanh hơn, nhưng cũng có giá:

- **Dung lượng lưu trữ** của index và metadata.
- **Chi phí ghi và cập nhật** khi document thay đổi.
- **Thời gian xây dựng/rebuild index**, đặc biệt khi có lượng dữ liệu lớn.
- **Nhu cầu bộ nhớ** để giữ index hoặc working set nóng.
- **Độ trễ đồng bộ** cho index/projection không cập nhật trực tiếp.
- **Ràng buộc về định dạng và version** của analyzer, tọa độ hoặc embedding model.

Ví dụ đổi mô tả dịch vụ có thể cần tạo embedding mới; nếu vừa cập nhật văn bản vừa cập nhật vector theo hai bước, sẽ có giai đoạn vector không còn tương ứng với mô tả hiện hành.

### Chọn index dựa trên truy vấn thực

Đừng tạo full-text, geo và vector index cho mọi collection theo thói quen. Cần đo:

- Truy vấn nào chạy thường xuyên?
- Độ trễ p95/p99 mục tiêu?
- Các filter nào có độ chọn lọc cao?
- Có bao nhiêu bản ghi và bao nhiêu giá trị khóa nóng?
- Dữ liệu được cập nhật với tần suất nào?
- Số giờ/chi phí để dựng lại index khi hỏng hoặc thay schema?
- Có thể bỏ một index ít sử dụng để giảm chi phí ghi không?

Nhiều khả năng chuyên biệt trong một engine chỉ hiệu quả khi **cách đánh index phù hợp với workload**, không phải khi bật toàn bộ tính năng.

## 16. Phân vùng dữ liệu và tác động đến các truy vấn chuyên biệt

Trong hệ phân tán, dữ liệu được đặt trên nhiều partition/shard. Một truy vấn đơn giản theo `serviceId` có thể định vị một partition; truy vấn graph nhiều bước hoặc tìm top-k vector toàn tenant có thể phải tiếp xúc nhiều partition.

| Khả năng | Rủi ro khi dữ liệu phân tán | Điều cần thiết kế |
|---|---|---|
| Document lookup | Truy vấn thiếu shard key gây fan-out | Khóa phân vùng phù hợp access pattern |
| Graph traversal | Cạnh nối các vertex ở nhiều shard | Partition locality, depth, supernode |
| Full-text search | Ranking hợp nhất nhiều shard | Top-k merge, thống kê scoring, filter |
| Geospatial | Vùng truy vấn cắt nhiều partition | Chiến lược phân vùng địa lý, hotspot |
| Time-series | Ghi mới tập trung vào một dải thời gian | Khóa kết hợp thời gian và entity/bucket |
| Vector search | ANN top-k trên nhiều shard, filter chọn lọc | Phân bố vector, hợp nhất ứng viên, recall |

### Ví dụ hotspot graph

Một nhà cung cấp được hàng triệu khách hàng theo dõi. Nếu cạnh `FOLLOWS` tập trung quanh cùng vertex, traversal từ vertex đó có thể tạo ra lượng lớn kết quả. Cần giới hạn độ sâu, số cạnh, quyền truy cập và cách phân trang. Có thể cần bản tổng hợp cho một số câu hỏi thay vì duyệt toàn bộ graph ở mỗi request.

### Ví dụ hotspot time-series

Nếu mọi thiết bị ghi vào một partition chỉ dựa trên `todayDate`, toàn bộ lưu lượng hôm nay có thể dồn vào cùng partition. Một khóa kết hợp `tenantId`, `deviceId` hoặc bucket thích hợp có thể phân tán tải, nhưng lại tăng chi phí truy vấn toàn khoảng thời gian. Không có partition key tối ưu cho mọi kiểu truy cập.

### Vector với filter chọn lọc

Một index ANN tìm được top-k trên toàn dữ liệu nhưng tenant chiếm tỷ lệ nhỏ có thể chỉ trả vài kết quả sau khi lọc. Thiết kế phải tìm hiểu engine hỗ trợ **pre-filter**, **post-filter**, partition theo tenant hoặc tăng tập ứng viên ra sao, và ảnh hưởng của từng lựa chọn lên recall/latency.

## 17. Khi tích hợp nhiều năng lực, thứ tự lọc quan trọng

Giả sử một bảng có 1 triệu dịch vụ, tenant-a chỉ được phép thấy 2.000 dịch vụ. Nếu tìm vector top 10 trên cả triệu rồi lọc tenant, 10 kết quả ban đầu có thể thuộc tenant khác hết.

Có thể cần một trong các chiến lược, tùy engine:

1. **Pre-filter:** chỉ tìm vector trong tập đã thỏa tenant/status.
2. **Index/partition scoped:** tổ chức dữ liệu để tìm trong không gian tenant hoặc nhóm quyền phù hợp.
3. **Candidate expansion:** lấy nhiều ứng viên hơn rồi lọc, chấp nhận tăng chi phí và nguy cơ thiếu kết quả nếu phân bố quá lệch.
4. **Two-stage retrieval:** tìm theo điều kiện bắt buộc trước rồi rerank bằng vector trên tập ứng viên.
5. **Hybrid retrieval:** kết hợp lexical và vector cùng cơ chế hợp nhất có kiểm soát.

Một truy vấn đúng về mặt quyền truy cập nhưng trả **ít kết quả hơn thực tế có thể có** vẫn có thể là lỗi chất lượng tìm kiếm. Ngược lại, truy vấn “đủ kết quả” nhưng cho phép nhìn thấy tài liệu trái quyền là lỗi nghiêm trọng hơn. Cần kiểm chứng đồng thời **authorization, recall, relevance và latency**.

## 18. Quan sát hiệu năng theo từng năng lực

Một dashboard chỉ có CPU, RAM và request/giây sẽ khó giải thích nguyên nhân search chậm hay graph traversal tăng đột biến.

| Năng lực | Chỉ số gợi ý | Câu hỏi |
|---|---|---|
| Document | latency theo query, documents examined, index usage | Có quét quá nhiều document không? |
| Graph | visited vertices/edges, depth, fan-out, traversal time | Đường đi có nở quá nhanh không? |
| Full-text | index size, refresh lag, ranking latency, token/analyzer stats | Index có mới và chọn lọc không? |
| Geospatial | candidate count, distance calculation cost, index usage | Truy vấn vùng có quá rộng không? |
| Time-series | ingest rate, event lag, rollup delay, retention backlog | Có ghi bù, thiếu hoặc dồn dữ liệu không? |
| Vector | recall@k, p95/p99, vector index memory, filter selectivity | Có cân bằng tốc độ và chất lượng không? |
| Tích hợp | replication/CDC lag, projection rebuild, dead-letter count | Các bản biểu diễn có lệch nguồn dữ liệu không? |

**Không phải sản phẩm nào cũng lộ đầy đủ các chỉ số này.** Có thể cần kết hợp profiler, query plan, logging có sampling, metric từ ứng dụng và kiểm thử đối chiếu để hiểu hoạt động thực tế.

## 19. Một quy trình triển khai năng lực chuyên biệt có kiểm soát

Giả sử phiên bản đầu của ứng dụng chỉ có document lưu dịch vụ. Sau này đội sản phẩm yêu cầu **tìm dịch vụ theo từ khóa và bán kính**.

### Giai đoạn 1 — Làm rõ hợp đồng nghiệp vụ

- “Gần” là bán kính theo đường chim bay hay thời gian đi đường?
- Người dùng tìm theo tiếng Việt có dấu/không dấu như thế nào?
- Có cho phép hiển thị dịch vụ mới đăng muộn vài giây?
- Khi provider bị khóa, kết quả phải biến mất ngay hay booking mới bị chặn ở bước đặt?
- Phạm vi tenant và quyền truy cập quyết định bởi trường nào?
- Cần trả top 20 theo ranking nào: liên quan, khoảng cách, chất lượng, giá?

### Giai đoạn 2 — Chọn nguồn dữ liệu và biểu diễn

Một document dịch vụ giữ `title`, `description`, `location`, `status` và `tenantId`. Có thể tạo index full-text và geo nếu engine hỗ trợ; nếu không, thiết kế projection sang search engine riêng.

### Giai đoạn 3 — Chọn cấu trúc chuyên biệt

- Analyzer tiếng Việt phù hợp, định nghĩa từ đồng nghĩa nếu có.
- Geospatial index dùng tọa độ và đơn vị thống nhất.
- Composite index phục vụ filter tenant/status khi cần.
- Chính sách cập nhật, refresh/rebuild và xử lý document bị xóa.

### Giai đoạn 4 — Xây truy vấn kết hợp

Kết quả phải được tìm theo text, lọc geo, tenant/status, rồi xếp hạng và trả document cần thiết. Cần tránh lọc tenant chỉ sau khi lấy top-k toàn hệ thống. Khi đặt dịch vụ thật, kiểm tra lại availability tại đường ghi nghiệp vụ.

### Giai đoạn 5 — Kiểm chứng tình huống biên

- Dịch vụ ở ngay ranh giới bán kính.
- Vị trí bị đảo latitude/longitude.
- Tên dịch vụ có dấu hoặc không dấu.
- Dịch vụ đã khóa vẫn còn trong search index cũ.
- Một tenant có quá nhiều dịch vụ gây phân bố lệch.
- Một dịch vụ bị sửa tên hoặc địa chỉ liên tục.
- Query chỉ có một từ rất phổ biến trả quá nhiều candidate.

### Giai đoạn 6 — Theo dõi vận hành

Đo latency, index refresh lag, kết quả sai quyền, số request không có kết quả, thời gian reindex và chi phí mỗi truy vấn. Nếu cần tăng trưởng, kiểm thử hotspot và khả năng phục hồi khi một node/index tạm thời không sẵn sàng.

## 20. Khi nào chọn một hệ đa mô hình, khi nào tách chuyên dụng?

Không có câu trả lời chung. Quyết định phụ thuộc **mức độ dùng chung dữ liệu**, **yêu cầu chuyên sâu**, **nhóm vận hành** và **mức nhất quán cần thiết**.

| Tiêu chí | Một nền tảng đa mô hình | Các hệ chuyên dụng tích hợp |
|---|---|---|
| Vận hành ban đầu | Có thể gọn nếu sản phẩm đáp ứng nhiều nhu cầu | Có nhiều dịch vụ, credential, backup và triển khai |
| Dữ liệu chia sẻ | Có thể giảm pipeline và sao chép | Cần đồng bộ từ nguồn chính sang projection |
| Truy vấn kết hợp | Có thể thuận tiện nếu engine hỗ trợ thật | Có thể cần truy vấn nhiều bước ở ứng dụng |
| Chức năng chuyên sâu | Phụ thuộc độ trưởng thành của từng năng lực trong sản phẩm | Có thể chọn engine mạnh nhất cho từng workload |
| Hiệu năng/scale | Có thể chia sẻ tài nguyên, khó cô lập workload nặng | Có thể scale search, graph, vector, analytics độc lập |
| Transaction/consistency | Có thể đơn giản hơn trong phạm vi engine hỗ trợ | Cần xử lý consistency xuyên hệ rõ ràng |
| Lock-in | Phụ thuộc API và index chuyên biệt của sản phẩm | Phụ thuộc nhiều API, connector và vận hành |
| Chi phí dài hạn | Một hệ có thể đơn giản nhưng cấu hình lớn | Nhiều hệ có chi phí vận hành và đồng bộ |
| Khôi phục dữ liệu | Có thể tập trung hơn nếu backup bao phủ các cấu trúc | Phải điều phối thứ tự restore/rebuild projection |

Một hệ đa mô hình có lợi khi nhiều kiểu truy vấn cần **cùng bộ dữ liệu cốt lõi**, độ phức tạp từng năng lực vừa phải và nền tảng có thể đáp ứng SLO tổng thể. Hệ chuyên dụng có thể phù hợp khi một workload có yêu cầu rất sâu, như graph traversal quy mô lớn, tìm kiếm văn bản nâng cao, vector retrieval với recall nghiêm ngặt hoặc time-series ingest cực lớn.

## 21. Kiểm tra khả năng “đa mô hình” của một sản phẩm bằng câu hỏi cụ thể

Khi đánh giá một sản phẩm, cần thu thập câu trả lời có thể kiểm chứng cho từng điểm:

1. **Các mô hình được hỗ trợ là gì?** Document, graph, search, geo, time-series, vector là native, plugin hay một dịch vụ đi kèm?
2. **Dữ liệu có cùng tồn tại và cùng được truy vấn không?** Một document có thể làm nguồn cho nhiều index/kiểu truy vấn không, hay phải import sang container khác?
3. **Ngôn ngữ truy vấn:** có kết hợp filter document, graph traversal và search trong một query được không?
4. **Giao dịch:** atomicity áp dụng trên document, nhiều document, collection, graph edge, index ở phạm vi nào?
5. **Độ mới:** sau commit bao lâu dữ liệu có thể tìm được trong full-text/vector index?
6. **Index:** analyzer, distance metric, ANN algorithm, geo CRS, uniqueness, rebuild và version có những giới hạn gì?
7. **Phân tán:** shard key ảnh hưởng graph, geo, vector top-k và time-series như thế nào?
8. **SLA/SLO thực tế:** latency p95/p99, throughput, failover và mức độ suy giảm khi workload đồng thời?
9. **Backup và restore:** có bảo toàn relation/index/projection cùng snapshot nhất quán hay cần dựng lại?
10. **Bảo mật:** có hỗ trợ tenant isolation, document/row-level security và filter tại index không?
11. **Quan sát:** có đo được query plan, traversal fan-out, search/index lag, vector recall không?
12. **Giới hạn phiên bản và giấy phép:** tính năng nào chỉ có ở dịch vụ managed, phiên bản cụ thể hoặc edition riêng?

Danh sách câu hỏi này quan trọng hơn nhãn marketing “multi-model”. Hai sản phẩm cùng hỗ trợ “vector search” có thể khác nhau hoàn toàn về kiểu index, filter support, update semantics và chất lượng tìm kiếm.

## 22. Những nhầm lẫn cần tránh

**“Một database lưu JSON thì cũng là graph database.”** Lưu trường `relatedIds` không đồng nghĩa engine có graph traversal, shortest-path hoặc index cạnh chuyên biệt.

**“Có full-text index nên chắc chắn hiểu ý định người dùng.”** Lexical search và semantic similarity là hai nhóm kỹ thuật khác nhau, có thể phối hợp nhưng không thay thế hoàn toàn cho nhau.

**“Có vector search nghĩa là tìm chính xác 100% láng giềng gần nhất.”** Nhiều chỉ mục dùng ANN, cần đo recall và latency. Kết quả gần theo metric cũng chưa chắc liên quan về nghiệp vụ.

**“Có tọa độ latitude/longitude thì tự biết thời gian di chuyển.”** Geospatial distance theo hình học không phải routing trên mạng đường.

**“Một hệ đa mô hình cho phép cập nhật mọi index trong cùng transaction.”** Phải kiểm tra khả năng atomic và refresh visibility của từng cấu trúc. Một số index/projection được cập nhật bất đồng bộ.

**“Top 10 vector rồi lọc tenant là đủ.”** Có thể làm thiếu kết quả phù hợp hoặc gây vấn đề quyền truy cập. Phải hiểu nơi filter được thực thi.

**“Đã search ra dịch vụ ACTIVE thì có thể tạo booking ngay.”** Index tìm kiếm có thể trễ; đường ghi phải kiểm tra trạng thái và bất biến tại nguồn có thẩm quyền.

**“Có một engine nên không cần thiết kế đồng bộ dữ liệu.”** Cache, projection, materialized view, graph edge và embedding vẫn có vòng đời khác nhau.

**“Thêm index nào cũng chỉ cải thiện hệ thống.”** Index có chi phí lưu trữ, write amplification, memory và rebuild. Index không dùng vẫn tiêu tốn tài nguyên.

**“Cùng nhà cung cấp tức là cùng model và API.”** Nhiều API có thể trỏ đến các cách lưu trữ hoặc account khác nhau. Kiểm tra phạm vi chia sẻ dữ liệu thật.

**“Sản phẩm nào đa mô hình cũng phù hợp mọi workload.”** Truy vấn graph cực rộng, analytics nặng hoặc ingest time-series lớn có thể cần tối ưu chuyên biệt và khả năng scale độc lập.

## 23. Bài tập tư duy

### Bài tập A — Tìm nhà cung cấp gần nhất

Nền tảng muốn tìm nhà cung cấp trong phạm vi 3 km và hiển thị theo thời gian di chuyển dự đoán.

**Câu hỏi:** Một geospatial index có đáp ứng toàn bộ yêu cầu không?

**Hướng suy luận:** geospatial index giúp tìm ứng viên theo khoảng cách hình học. Thời gian di chuyển cần dữ liệu đường đi, tốc độ hoặc một dịch vụ định tuyến phù hợp. Có thể dùng geo để lọc trước, rồi routing để xếp hạng ứng viên.

### Bài tập B — Đặt dịch vụ sau khi trạng thái thay đổi

Khách nhìn thấy dịch vụ ACTIVE trong search. Ngay sau đó nhà cung cấp chuyển INACTIVE nhưng search index chưa refresh. Khách gửi yêu cầu booking.

**Câu hỏi:** Tầng nào phải chặn booking?

**Hướng suy luận:** service xử lý booking phải kiểm tra trạng thái hiện hành và quy tắc đặt chỗ tại nguồn có thẩm quyền; nếu cần, dùng transaction hoặc conditional write phù hợp. Search index là kênh khám phá và có thể trễ.

### Bài tập C — Tìm kiếm hai tenant

Một vector index chứa 100.000 dịch vụ, tenant-a chỉ có 100. Query lấy top 20 trên toàn tập rồi lọc tenant và thường chỉ trả 0–1 kết quả.

**Câu hỏi:** Có phải tenant-a chỉ có tối đa một dịch vụ phù hợp?

**Hướng suy luận:** chưa chắc. Post-filter trên top-k toàn cục có thể loại gần hết ứng viên. Cần hỗ trợ filter theo tenant trong vector retrieval, chia index hoặc thiết kế hai giai đoạn phù hợp; đo recall trên tập có quyền.

### Bài tập D — Phân tích lượt đặt theo giờ

Có 20.000 booking được ghi nhận trong một ngày. Một số thiết bị gửi sự kiện hoàn tất chậm hai giờ.

**Câu hỏi:** Biểu đồ số booking hoàn tất theo giờ nên dùng `eventTime` hay `ingestedAt`?

**Hướng suy luận:** phụ thuộc mục đích. Nếu đo thời điểm dịch vụ thực sự hoàn tất, dùng event time và chính sách cập nhật bucket khi dữ liệu đến muộn. Nếu đo tải hệ thống tiếp nhận event, dùng ingestion time. Hai biểu đồ trả lời hai câu hỏi khác nhau.

### Bài tập E — Quan hệ khách hàng

Ứng dụng cần truy vấn “dịch vụ được khách có sở thích tương tự sử dụng trong ba bước quan hệ”, nhưng có một provider được hàng triệu khách theo dõi.

**Câu hỏi:** Graph traversal có rủi ro nào?

**Hướng suy luận:** độ phân nhánh lớn, supernode và fan-out qua shard. Cần giới hạn depth/candidate, filter sớm, đánh giá index cạnh và có thể tiền tính một số gợi ý.

### Bài tập F — Nâng cấp embedding model

Ứng dụng đang dùng embedding model v1, muốn chuyển sang v2. Hai model tạo vector cùng 768 chiều.

**Câu hỏi:** Có thể ghi đè một nửa vector trong index cũ bằng kết quả v2 không?

**Hướng suy luận:** không nên coi cùng dimension là cùng không gian ngữ nghĩa. Thiết kế version/index chuyển đổi, backfill, đo chất lượng, đồng bộ query model rồi mới loại bỏ v1.

## 24. Khung thiết kế khi đưa một khả năng chuyên biệt vào hệ đa mô hình

Một yêu cầu công nghệ chỉ nên trở thành thiết kế sau khi đã xác định **nghiệp vụ, dữ liệu, đường truy vấn và ràng buộc vận hành**.

~~~text
Nhu cầu nghiệp vụ
    ↓
Đơn vị dữ liệu gốc, identity và quyền truy cập
    ↓
Kiểu truy vấn cần tối ưu
    ├── Document / key lookup
    ├── Graph traversal
    ├── Full-text / vector retrieval
    ├── Geo filtering
    └── Time-window aggregation
    ↓
Index hoặc cấu trúc chuyên biệt
    ↓
Độ mới dữ liệu, transaction và cơ chế đồng bộ
    ↓
Query kết hợp + authorization + ranking
    ↓
SLO, benchmark, monitoring và kế hoạch recovery
~~~

Với mỗi năng lực, ghi lại:

| Thiết kế cần ghi | Ví dụ |
|---|---|
| **Nguồn sự thật** | Document `services` chứa trạng thái ACTIVE/INACTIVE |
| **Định danh ổn định** | `serviceId`, phạm vi `tenantId` |
| **Dữ liệu chuyên biệt** | Full-text index từ title/description; vector từ embedding model v1 |
| **Kiểu truy vấn** | Tìm dịch vụ theo từ khóa, bán kính và trạng thái |
| **Tính nhất quán** | Search có thể trễ; booking kiểm tra lại nguồn chính |
| **Phân vùng và index** | Tenant filter, 2dsphere, lexical/vector index theo cách engine hỗ trợ |
| **SLO** | Độ trễ tìm kiếm và mức độ mới dữ liệu được nghiệp vụ chấp nhận |
| **Khôi phục** | Rebuild index và đối chiếu với document gốc |
| **Quan sát** | Search latency, index lag, graph fan-out, ANN recall nếu có |

Khả năng chuyên biệt bên trong hệ đa mô hình phát huy giá trị khi nó **giải đúng một dạng truy vấn mà mô hình dữ liệu cơ bản xử lý kém**, đồng thời phối hợp được với nguồn dữ liệu, quyền truy cập và quy tắc nghiệp vụ của ứng dụng. Lợi ích lớn không nằm ở việc có nhiều nhãn tính năng trong cùng sản phẩm, mà ở khả năng dùng đúng thuật toán và index cho từng câu hỏi **mà vẫn giữ identity, tính đúng đắn, quan sát và vận hành thống nhất ở mức hệ thống**.
