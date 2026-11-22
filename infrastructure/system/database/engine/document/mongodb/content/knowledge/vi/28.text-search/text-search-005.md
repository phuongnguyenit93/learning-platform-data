# Atlas Search: phạm vi dịch vụ và điều kiện triển khai

**Atlas Search** là tên gọi quen thuộc của năng lực tìm kiếm toàn văn được tích hợp vào **MongoDB Atlas**. Trong tài liệu MongoDB hiện nay, năng lực này thường được gọi là **MongoDB Search**. Nó sử dụng công nghệ **Apache Lucene** để xây dựng chỉ mục tìm kiếm và xử lý các bài toán mà MongoDB B-tree index hoặc toán tử `$text` truyền thống không được thiết kế để đáp ứng đầy đủ: tìm kiếm theo ngôn ngữ tự nhiên, độ liên quan, autocomplete, fuzzy search, synonyms, highlight, facet, tìm kiếm kết hợp nhiều điều kiện và xếp hạng kết quả.

Tuy nhiên, “Atlas Search” không chỉ là một toán tử thêm vào `find()`. Muốn sử dụng đúng cần hiểu **nơi dịch vụ được hỗ trợ**, **ai vận hành tiến trình tìm kiếm**, **cluster tier nào phù hợp**, **làm thế nào tạo Search index**, **khi nào index sẵn sàng**, **giới hạn đồng bộ và tài nguyên**, cùng những yêu cầu bảo mật và vận hành khi đưa tính năng lên production.

Bài học thuộc chương **Tìm kiếm văn bản** nhằm trả lời:

1. Atlas Search cung cấp những khả năng nào và không thay thế những chức năng gì của MongoDB?
2. Search index khác gì index B-tree thông thường và text index `$text`?
3. Kiến trúc `mongod` — `mongot` hoạt động ra sao?
4. Có thể sử dụng trên Free, Flex, Dedicated, Search Nodes riêng, môi trường local và self-managed hay không?
5. Điều kiện nào cần kiểm tra trước khi tạo Search index, chạy `$search`, `$searchMeta`?
6. Vì sao Search có thể trả kết quả trễ so với một lần ghi vừa thành công?
7. Khi nào nên scale lên Dedicated Search Nodes, và cần đo những chỉ số nào?
8. Thiết kế bảo mật, capacity, giám sát và quy trình triển khai an toàn thế nào?

> **Thông điệp chính:** Atlas Search là một **search engine được tích hợp vào đường truy vấn MongoDB**, nhưng Search index có vòng đời và độ trễ đồng bộ riêng với dữ liệu nguồn. **Tạo được index không có nghĩa index đã sẵn sàng, chạy được `$search` không có nghĩa kết quả mới nhất theo giao dịch, và có Free/Flex tier không đồng nghĩa có cùng năng lực/SLA với Search Nodes chuyên dụng.**

## 1. Đặt Atlas Search trong hệ sinh thái MongoDB

MongoDB phục vụ hai nhóm nhu cầu liên quan nhưng khác nhau:

- **Truy xuất dữ liệu chính xác và nghiệp vụ:** tìm document theo `_id`, mã đơn hàng, khoảng giá, cập nhật có điều kiện, transaction, uniqueness, quyền truy cập.
- **Tìm kiếm theo nội dung và mức độ liên quan:** người dùng nhập một vài từ, tìm kết quả “có vẻ đúng ý”, cho phép sai chính tả, gợi ý hoàn thành, xếp hạng theo độ liên quan và lọc nhiều chiều.

Ví dụ collection sản phẩm:

```javascript
{
  _id: "SKU-001",
  tenantId: "SHOP-A",
  title: "Tai nghe không dây",
  description: "Tai nghe Bluetooth có chống ồn",
  category: "audio",
  price: 1350000,
  published: true
}
```

Các câu hỏi khác nhau:

| Câu hỏi | Công cụ thường phù hợp |
|---|---|
| Tìm đúng `_id = "SKU-001"` | B-tree index trên `_id` |
| Lọc `tenantId` và `price` trong khoảng | Compound B-tree index |
| Bảo đảm `sku` không trùng | Unique index |
| Tìm chữ “tai nghe” trong tiêu đề/mô tả và xếp hạng | MongoDB Search / Atlas Search |
| Gợi ý tên sản phẩm khi mới nhập “tai ng” | Search `autocomplete` với mapping phù hợp |
| Chấp nhận một số lỗi đánh máy | Search `text`/`autocomplete` với fuzzy options |
| Tìm sản phẩm “gần nghĩa” bằng embedding | MongoDB Vector Search, bài toán liên quan nhưng **khác** |
| Ghi một đơn hàng và giữ invariant tồn kho | Atomic update/transaction, **không** do Search index đảm bảo |

Atlas Search làm mạnh năng lực tìm kiếm, **không thay thế** B-tree index, unique constraint, transaction, schema validation hay các rule bảo mật ở tầng ứng dụng.

### 1.1. Vì sao tên dịch vụ có thể gây nhầm?

Trong tài liệu và code cũ, thuật ngữ **Atlas Search** được sử dụng rất nhiều. Tài liệu mới dùng **MongoDB Search** để nói về search engine và các stage `$search`, `$searchMeta`.

Cần phân biệt ba ngữ cảnh:

- **Atlas Search trên MongoDB Atlas:** Atlas cung cấp và vận hành phần Search như một dịch vụ managed.
- **MongoDB Search trên self-managed deployment:** có khả năng triển khai trên những tổ hợp MongoDB Server/`mongot` được hỗ trợ, nhưng **đơn vị vận hành tự cài đặt, cấu hình, monitor và nâng cấp** phần Search.
- **Local Atlas deployment:** môi trường thử nghiệm có `mongod` và `mongot` đi kèm; phù hợp học tập, không mặc nhiên đủ HA cho production.

Vì tên sản phẩm và các điều kiện hỗ trợ phát triển theo phiên bản, không dùng quy tắc lỗi thời rằng “mọi bản self-managed MongoDB đều không thể dùng Search”, cũng không suy ngược rằng “chỉ cần cài Community Edition bất kỳ là `$search` sẽ chạy”.

## 2. Search engine: có một lớp chỉ mục riêng

Kiến trúc khái quát của một Search query:

```text
Client / Java / mongosh
          |
          | MongoDB aggregation pipeline
          v
       mongod / mongos
          |
          | $search hoặc $searchMeta
          v
       mongot (Apache Lucene)
          |
          | Search index
          v
   Document IDs + score + metadata
          |
          v
  MongoDB đọc document nguồn
  hoặc dùng stored source khi phù hợp
          |
          v
       Kết quả cho client
```

`mongot` là tiến trình Search riêng với `mongod`. Nó:

1. Xây dựng và duy trì chỉ mục Lucene từ collection MongoDB.
2. Theo dõi thay đổi dữ liệu nguồn bằng cơ chế đồng bộ có liên quan đến change streams.
3. Thực thi phần truy vấn tìm kiếm và tính search relevance score.
4. Phối hợp với `mongod`/`mongos` để trả kết quả trong aggregation pipeline.

**Ứng dụng kết nối tới MongoDB**, không cần mở kết nối trực tiếp tới `mongot` để gửi `$search`.

### 2.1. Search index không phải B-tree index

Các lệnh tạo index khác nhau:

```javascript
// B-tree index phục vụ điều kiện lọc/sắp xếp thông thường.
db.products.createIndex({
  tenantId: 1,
  price: 1
});

// Search index phục vụ truy vấn $search.
db.products.createSearchIndex(
  "product_text",
  { mappings: { dynamic: true } }
);
```

Hai index có **cấu trúc và vòng đời khác nhau**. `db.collection.getIndexes()` liệt kê database indexes truyền thống; để xem Search indexes dùng cơ chế quản lý riêng, ví dụ `$listSearchIndexes` trong phiên bản hỗ trợ.

### 2.2. Inverted index và phân tích từ

Ở mức ý tưởng, Lucene có thể tổ chức ánh xạ:

```text
"tai"       -> DOC-01, DOC-02, DOC-09
"nghe"      -> DOC-01, DOC-03, DOC-09
"bluetooth" -> DOC-01, DOC-07
"chống"     -> DOC-01, DOC-08
"ồn"        -> DOC-01, DOC-08
```

Khi người dùng nhập “tai nghe bluetooth”, search engine không cần duyệt mọi document để kiểm tra từng chuỗi ký tự. Nó sử dụng index và cơ chế scoring để tìm/xếp hạng ứng viên.

Đây là mô hình giải thích khái niệm; Lucene thực tế còn có token positions, term frequency, segment structure, analyzers và các tối ưu khác.

### 2.3. Relevance score không phải khóa sắp xếp tuyệt đối của nghiệp vụ

Search có thể xếp hạng dựa trên điểm mức độ liên quan. Kết quả có thể thay đổi khi:

- Dữ liệu được thêm/xóa;
- Analyzer/mapping thay đổi;
- Query hoặc boost được điều chỉnh;
- Index được xây lại;
- Cấu trúc corpus thay đổi làm thay đổi thống kê term;
- Ứng dụng thêm filter/sort.

Không dùng một score như **định danh duy nhất** hoặc transaction version. Nếu sản phẩm yêu cầu pagination ổn định, phải có thiết kế sort/tie-breaker hoặc phương thức phân trang Search được phiên bản triển khai hỗ trợ.

## 3. Phạm vi tính năng của Atlas Search

Các nhóm chức năng tiêu biểu:

| Nhóm | Mục tiêu | Ví dụ |
|---|---|---|
| Full-text | Tìm nội dung văn bản | “tai nghe chống ồn” |
| Relevance ranking | Xếp hạng kết quả | Tên khớp mạnh hơn mô tả |
| Autocomplete | Gợi ý khi đang nhập | “tai ng…” |
| Fuzzy search | Chấp nhận sai chính tả giới hạn | “blutooth” gần “bluetooth” |
| Phrase / proximity | Tìm cụm từ có quan hệ thứ tự | “sạc nhanh” |
| Synonyms | Ánh xạ từ đồng nghĩa | “điện thoại” / “smartphone” theo từ điển |
| Compound query | Kết hợp must/should/filter/mustNot | Text query + tenant + published |
| Highlight | Trả đoạn/trường khớp | Tô đậm phần từ phù hợp |
| Facets | Nhóm kết quả theo chiều lọc | Category, price bands |
| Search metadata | Đếm hoặc thống kê liên quan truy vấn | `$searchMeta` |
| Search-as-you-type | Trải nghiệm input phản hồi nhanh | Danh sách gợi ý |
| Search theo điều kiện bổ sung | Kết hợp toán tử kiểu equals/range/geo khi mapping hỗ trợ | Sản phẩm dưới 2 triệu đồng |

Mỗi nhóm có **mapping, operator và giới hạn phiên bản/cluster tier riêng**. Không mặc định tạo một index `dynamic: true` là mọi tính năng đều được tối ưu sẵn.

### 3.1. Những việc Atlas Search không tự làm

Atlas Search không phải:

- Hệ thống **uniqueness** để ngăn mã sản phẩm trùng;
- Transaction coordinator;
- Bản sao dữ liệu đủ để thay thế backup;
- Dịch vụ dịch máy;
- Bộ kiểm tra nội dung hợp pháp/đúng sự thật;
- Hệ thống phân quyền người dùng thay cho MongoDB/ứng dụng;
- Công cụ đồng bộ tức thời theo ngữ nghĩa linearizable;
- Engine định tuyến đường bộ hoặc tính ETA;
- Một index B-tree thay thế được mọi query `find()`.

Tính năng tìm kiếm mạnh không thay thế thiết kế dữ liệu và quyền truy cập.

## 4. Atlas Search so với `$text` truyền thống

MongoDB có **text index** và `$text` trong cơ chế database index truyền thống:

```javascript
db.products.createIndex({
  title: "text",
  description: "text"
});

db.products.find({
  $text: {
    $search: "tai nghe"
  }
});
```

Atlas Search sử dụng **Search index** và aggregation `$search`:

```javascript
db.products.aggregate([
  {
    $search: {
      index: "product_text",
      text: {
        query: "tai nghe",
        path: ["title", "description"]
      }
    }
  }
]);
```

Hai cách không dùng chung index.

| Tiêu chí | MongoDB `$text` | Atlas Search / MongoDB Search |
|---|---|---|
| Index | B-tree/text index của database | Search index dựa trên Lucene |
| Query entrypoint | `$text` trong `find` hoặc điều kiện tương đương | `$search`/`$searchMeta` trong aggregation |
| Full-text cơ bản | Có | Có |
| Autocomplete nâng cao | Không phải thế mạnh | Có operator/mapping riêng |
| Fuzzy matching | Hạn chế hơn | Có cấu hình fuzzy phù hợp |
| Ranking tùy biến | Hạn chế hơn | Nhiều lựa chọn score/boost |
| Facet/highlight | Không phải phạm vi chính | Có tính năng Search tương ứng |
| Vòng đời index | Gắn với MongoDB database indexes | Search index riêng, đồng bộ bất đồng bộ |
| Điều kiện triển khai | MongoDB hỗ trợ text index | Cần Search service/`mongot` khả dụng |
| Kết quả ngay sau ghi | Theo cơ chế read/index của database | Có thể có **indexing lag** |
| Chi phí vận hành | Chủ yếu tài nguyên database | Database + Search workload/index storage |

Không nên migration từ `$text` sang `$search` bằng cách **chỉ đổi toán tử**. Cần xây Search index, cấu hình mapping, thử ranking và điều chỉnh ứng dụng.

## 5. Phạm vi triển khai trên MongoDB Atlas

MongoDB Atlas cung cấp các deployment tiers khác nhau. Cần tách hai câu hỏi:

1. **Tier này có thể dùng MongoDB Search không?**
2. **Tier này có tài nguyên/feature set/SLA đủ để chạy workload của mình không?**

Hai câu hỏi có thể cho hai câu trả lời khác nhau.

### 5.1. Ma trận môi trường

| Môi trường | Search có thể sử dụng? | Kiến trúc / mục tiêu |
|---|---|---|
| Atlas Free cluster (tên cũ M0) | Có, với giới hạn riêng | Học tập, thử nghiệm nhẹ |
| Atlas Flex cluster | Có, với giới hạn riêng | Development, ứng dụng nhỏ, thử query |
| Atlas Dedicated M10/M20 và cao hơn | Có, theo khả năng phiên bản/tier | Prototype và production tùy tài nguyên |
| Atlas Dedicated với Search Nodes riêng | Có ở tier/region đủ điều kiện | Workload isolation, production Search |
| Atlas local deployment | Có trong cấu hình local Search phù hợp | Development/CI, không tự đủ HA |
| Atlas Infinite | Khả năng hỗ trợ theo chương trình/tình trạng triển khai hiện hành | Phải kiểm tra giới hạn/preview trước khi cam kết SLA |
| Self-managed Community / Enterprise | Có trên **tổ hợp server + `mongot` được hỗ trợ** | Tự triển khai/vận hành, không phải Atlas managed |

Bảng phản ánh các mô hình MongoDB công bố vào **2026**; tier, vùng, giới hạn, tên sản phẩm và phiên bản có thể thay đổi. Trước triển khai phải kiểm tra trang Compatibility & Limitations của chính release/region.

### 5.2. Free và Flex không đồng nghĩa hỗ trợ vô hạn

Trong tài liệu MongoDB Search ở thời điểm biên soạn, các giới hạn riêng có thể bao gồm:

- **Free:** tối đa **3 Search/Vector indexes** tổng hợp trên cluster.
- **Flex:** tối đa **10 indexes** loại Search/Vector trên cluster.
- **Định nghĩa index JSON tối đa 3 KB** ở hai loại tier này.
- **Một synonym mapping** trong mỗi index definition theo giới hạn tier.
- Các giới hạn về số field index, synonym collection, Lucene clause count và tính năng khác.

Những con số là **giới hạn theo tài liệu phiên bản/tier**, không phải khuyến nghị sizing. Hãy kiểm tra bản docs và Atlas UI trước khi dựa vào con số cho sản phẩm cụ thể.

Ví dụ, nếu một Free cluster đã có ba Search/Vector indexes, việc tạo index thứ tư có thể bị từ chối. Đổi tên index không làm giới hạn biến mất.

### 5.3. Học tập trên Free có phù hợp không?

Có thể dùng để:

- Thử tạo Search index;
- Thực hành `$search`, `$searchMeta`;
- Tìm hiểu mapping/analyzer;
- Viết proof of concept;
- Kiểm tra luồng index build/update;
- Đánh giá UX search cơ bản.

Không nên dùng benchmark vài nghìn document trên Free làm bằng chứng rằng hệ thống sẽ giữ p99 latency tốt ở hàng chục triệu sản phẩm hoặc tải production cao.

### 5.4. Flex phù hợp khi nào?

Flex có thể phục vụ thử nghiệm hoặc ứng dụng nhỏ, nhưng cần xem:

- Search index count và definition size;
- Dung lượng/tốc độ indexing;
- Giới hạn tài nguyên dùng chung;
- Mức độ tính năng nâng cao;
- SLO và concurrency thực tế;
- Kế hoạch chuyển sang dedicated khi cần.

Đừng suy từ việc Flex tạo được `autocomplete` rằng nó có cùng khả năng mở rộng hoặc node isolation như dedicated.

## 6. Dedicated cluster và Dedicated Search Nodes

Một Atlas Dedicated cluster có thể chạy hai tiến trình `mongod` và `mongot` **cùng một node** (co-located), hoặc bố trí **Search Nodes riêng** khi đáp ứng điều kiện.

### 6.1. Co-located Search

```text
Atlas database node
  ├── mongod: reads/writes, replication, database indexes
  └── mongot: Lucene index, search queries, indexing

Tài nguyên CPU / RAM / disk / I/O có thể cạnh tranh
```

Đây là cách bắt đầu đơn giản và có thể hiệu quả về chi phí nếu workload vừa phải.

Ưu điểm:

- Ít cấu hình hơn;
- Không cần một lớp Search Nodes trả phí riêng ngay từ đầu;
- Phù hợp prototype và tải hợp lý;
- Atlas quản lý Search process.

Đánh đổi:

- Search indexing/query có thể tranh chấp tài nguyên với database;
- Một burst autocomplete có thể ảnh hưởng latency read/write;
- Khi dữ liệu/index lớn, áp lực memory/disk tăng;
- Scale Search độc lập với database có giới hạn.

### 6.2. Dedicated Search Nodes

```text
Application
      |
   mongod/mongos                       Search Nodes
   (database)                       (mongot / Lucene)
      |                                     |
      |       search request               |
      +------------------------------------>
      |                                     |
      <------------------------------------+
      |
   Return results
```

Search Nodes riêng giúp:

- Tách tài nguyên tìm kiếm và dữ liệu;
- Scale CPU/RAM/storage cho Lucene theo Search workload;
- Giảm resource contention;
- Có thêm lựa chọn HA/workload isolation theo cấu hình;
- Theo dõi chi phí Search riêng hơn.

Tuy nhiên, nó không có nghĩa `$search` sẽ có **strong consistency**. Search vẫn dựa trên cơ chế chỉ mục riêng và cần được đồng bộ.

### 6.3. Điều kiện cơ bản cho Search Nodes riêng

Theo tài liệu Atlas, Search Nodes riêng áp dụng cho **Dedicated clusters M10 trở lên** với những yêu cầu server, cloud provider, region và search tier tương ứng. Free/Flex **không cho phép thêm Search Nodes riêng**.

Ở trang Deployment Options, một ví dụ khuyến nghị production là **M10+ database cluster** với **S20+ Search tier**, tại các cloud regions hỗ trợ. Đây là hướng dẫn sizing ban đầu, **không phải lời hứa mọi M10 ở mọi vùng đều bật được mọi cấu hình**.

Cần kiểm tra:

1. Atlas cluster tier có đủ điều kiện;
2. MongoDB Server version hỗ trợ Search Nodes;
3. Cloud provider/region có Search tier mong muốn;
4. Cluster topology có ràng buộc đặc biệt không (chẳng hạn global cluster);
5. Số Search Nodes tối thiểu và mô hình HA;
6. Search index size, query throughput, CPU/RAM;
7. Chi phí node và network transfer.

### 6.4. Search Nodes cũng có chi phí riêng

Khi thêm Dedicated Search Nodes, chi phí có thể bao gồm:

- **Số lượng Search Nodes** được triển khai;
- **Search tier** (CPU/RAM/storage);
- **Data transfer** giữa Search và database nodes;
- Mức sử dụng theo thời gian;
- Tài nguyên/index rebuild khi thay cấu hình.

Không thể gọi “Atlas Search luôn miễn phí” chỉ vì mô hình co-located không có dòng phí Search Node riêng. Co-located vẫn dùng tài nguyên cluster; Dedicated Search Nodes được tính phí theo cấu hình Atlas.

### 6.5. Khi nào cần tách node?

Một số tín hiệu:

- Search QPS tăng làm database write latency xấu;
- Mongot dùng nhiều CPU/RAM do index build/rebuild;
- Search index lớn làm memory pressure;
- Database scale chỉ để chịu Search mà không cần thêm database capacity;
- Search latency p95/p99 biến động mạnh khi có batch writes;
- Cần Search HA/scale độc lập;
- Có nhiều collection, analyzer và index lớn.

Chuyển sang Search Nodes không thay thế việc tối ưu mappings/query shapes. Một index quá rộng hoặc query không giới hạn có thể vẫn tốn tài nguyên trên node lớn.

## 7. Local development và self-managed: hiểu đúng phạm vi

### 7.1. Atlas local deployment

MongoDB cung cấp cách thử Search cục bộ bằng môi trường như **Atlas CLI local deployment** hoặc image `mongodb/mongodb-atlas-local` phù hợp.

Mô hình:

```text
Developer laptop / CI
   └── local MongoDB deployment
         ├── mongod
         └── mongot

Ứng dụng kết nối tới MongoDB thông thường.
```

Phù hợp:

- Học API `$search`;
- Phát triển analyzer/mapping;
- Chạy integration tests;
- Thử query trước khi cấp tài nguyên cloud;
- Demo POC.

Nhưng **local single-node deployment không phải phương án production HA**. Thiếu replication/high availability, backup policy và nhiều yêu cầu vận hành.

Một ví dụ image từ tài liệu MongoDB:

```bash
docker pull mongodb/mongodb-atlas-local:preview
docker run -p 27017:27017 mongodb/mongodb-atlas-local
```

Đây là lệnh tham khảo dành cho máy có Docker, image tag/điều kiện có thể thay đổi. Khi thử trên Windows/macOS, image chạy trong Linux container; không có nghĩa chạy native `mongot` Windows/macOS.

### 7.2. Self-managed MongoDB Search

Tài liệu MongoDB Search hiện đại có hướng triển khai self-managed. Kiến trúc:

```text
Self-managed replica set / sharded cluster
      mongod / mongos
            |
      gRPC / search integration
            |
         mongot
            |
      Lucene index files
```

Khác Atlas:

- Đội vận hành **cài và quản lý `mongot`**;
- Tự chọn máy/container/Kubernetes;
- Tự cấp storage/network;
- Tự chịu trách nhiệm topology và bảo mật kết nối;
- Tự theo dõi version compatibility;
- Tự quản lý nâng cấp, restart, restore và scaling.

`mongot` không phải một plugin chỉ cần thả vào bất kỳ `mongod` phiên bản nào. Cần đúng **MongoDB Server, mongot version, operating system, deployment management** theo bảng tương thích chính thức.

### 7.3. Ma trận tương thích có thể thay đổi theo release

Ở thời điểm tài liệu self-managed hiện hành (2026), hướng Kubernetes-managed có các mốc ví dụ như:

```text
MongoDB Server:        8.3.4 hoặc tương thích cao hơn
mongot:                1.70.1 hoặc tương thích cao hơn
Kubernetes Operator:   1.9.1 hoặc tương thích cao hơn
```

Đây là **mốc tối thiểu cho một nhánh triển khai/tài liệu cụ thể**, không thể áp dụng máy móc cho mọi cách đóng gói hoặc phiên bản tương lai. Tài liệu compatibility có thể đánh dấu những dòng server cũ hết hỗ trợ. Phải đọc bảng phiên bản **đúng ngày triển khai**.

Đối với Community self-managed, MongoDB công bố những đường cài đặt `mongot` qua Linux tarball/container và có lựa chọn operator phù hợp. Với Enterprise, các mô hình quản lý có điều kiện riêng, đặc biệt liên quan Kubernetes Operator.

**Không kết luận “MongoDB 8.x nào cũng có Search mặc định”.** Chức năng được cung cấp khi cả server và Search process được triển khai, tích hợp và hỗ trợ đúng.

### 7.4. Không làm lẫn Atlas managed với self-managed

| Công việc | Atlas Search managed | Self-managed Search |
|---|---|---|
| Provision Search process | Atlas hỗ trợ/quản lý | Đội vận hành |
| Search index định nghĩa | Ứng dụng/DB admin | Ứng dụng/DB admin |
| Compute sizing | Atlas tier/Search tier | Tự chọn host/container |
| Index synchronization | Search service xử lý, đội vận hành theo dõi | Search process xử lý, đội vận hành chịu trách nhiệm toàn bộ |
| Version compatibility | Atlas quản lý nhiều phần, vẫn cần kiểm tra | Bắt buộc tự kiểm tra ma trận |
| Network/TLS | Atlas project/network controls | Tự thiết kế/end-to-end |
| Logs/metrics | Atlas monitoring/API | Tự tích hợp observability |
| Backup/recovery | Theo Atlas plan và Search index strategy | Tự thiết kế toàn bộ |
| Chi phí | Cluster/Search Nodes/network theo tier | Infrastructure + nhân lực vận hành |

## 8. Điều kiện cần trước khi chạy Search trên Atlas

Trước khi tạo index, cần rà soát ít nhất sáu nhóm điều kiện.

### 8.1. Có một Atlas cluster hợp lệ

- Đã tạo project và deployment;
- Cluster đang chạy, không suspended;
- Tier hỗ trợ tính năng cần dùng;
- Server version phù hợp;
- Có collection và dữ liệu;
- Region có những Search options mong muốn.

Search index gắn với **collection hoặc view được hỗ trợ**, không phải một đối tượng tách rời mọi database.

### 8.2. Có quyền quản lý Search index

Các thao tác khác nhau đòi quyền khác nhau:

- Xem định nghĩa/trạng thái Search index;
- Tạo Search index;
- Sửa definition;
- Xóa index;
- Chạy query đọc từ collection.

Trên Atlas UI, Project role quyết định khả năng quản lý. Với `mongosh`/driver, database privileges tương ứng cũng rất quan trọng.

Theo tài liệu về Search Index Management, các database built-in roles như `read` thường cho phép liệt kê index, còn `readWrite` có các privilege actions quản lý index; khi dùng least privilege nên cấp role tùy biến phù hợp quy trình tổ chức.

Không cấp Project Owner hoặc database admin toàn quyền chỉ để một dịch vụ search API đọc danh sách sản phẩm.

### 8.3. Đường kết nối tới MongoDB

Cần:

- Connection string của cluster;
- Database user và credentials hợp lệ;
- Atlas IP access list, private endpoint/VPC networking khi cần;
- TLS theo chính sách kết nối;
- DNS/SRV resolution;
- Driver có khả năng kết nối tới deployment;
- Application secret management.

Ứng dụng **không** cần expose cổng `mongot` cho Internet. Với Atlas, gửi aggregation tới MongoDB như query thông thường.

### 8.4. Search index definition phù hợp schema

Cần biết:

- Field nào sẽ được tìm kiếm;
- Field nào cần exact filter;
- Field nào cần sort/facet;
- String dùng analyzer nào;
- Có dữ liệu đa ngôn ngữ không;
- Có cần autocomplete/fuzzy/synonyms không;
- Có nên bật dynamic mapping không;
- Có PII không được index không.

Một index mapping sai có thể khiến query không match hoặc match khác mong muốn dù cluster khỏe.

### 8.5. Index phải xây xong và queryable

Tạo Search index là **thao tác bất đồng bộ**. API có thể trả thành công khi yêu cầu tạo index được chấp nhận, nhưng indexing vẫn tiếp tục.

Quy trình hợp lý:

```text
Create Search Index
       |
       v
Index definition accepted
       |
       v
Initial index build / sync
       |
       v
Index becomes queryable/ready
       |
       v
Run Search tests and enable traffic
```

Không coi response `ok: 1` từ command quản lý index là chứng nhận index đã READY.

### 8.6. Có kế hoạch capacity và bảo mật

Ngay cả POC cũng nên giới hạn:

- Kích thước dữ liệu index;
- Số Search indexes;
- QPS dự kiến;
- Số kết quả trên mỗi query;
- Analyzer/index definition size;
- Network access;
- Collection chứa dữ liệu nhạy cảm.

Khi lên production cần thêm SLA, monitoring, backup/recovery, index lifecycle và ngân sách.

## 9. Tạo Search index: khác `createIndex()`

Ví dụ này sử dụng collection thử nghiệm `searchProductsLab` trong một deployment MongoDB Search đã được cấu hình hợp lệ. **Không chạy `drop()` trên collection sản xuất**.

### 9.1. Chuẩn bị dữ liệu

```javascript
use searchLab;

db.searchProductsLab.insertMany([
  {
    _id: "SKU-101",
    tenantId: "SHOP-A",
    title: "Tai nghe Bluetooth chống ồn",
    description: "Tai nghe không dây chụp tai, pin dùng lâu",
    category: "audio",
    price: 1350000,
    published: true
  },
  {
    _id: "SKU-102",
    tenantId: "SHOP-A",
    title: "Tai nghe có dây",
    description: "Tai nghe nhẹ dành cho học tập và họp trực tuyến",
    category: "audio",
    price: 250000,
    published: true
  },
  {
    _id: "SKU-103",
    tenantId: "SHOP-A",
    title: "Bàn phím cơ",
    description: "Bàn phím có kết nối Bluetooth",
    category: "keyboard",
    price: 950000,
    published: true
  },
  {
    _id: "SKU-104",
    tenantId: "SHOP-B",
    title: "Tai nghe du lịch",
    description: "Thiết kế gọn, dễ mang theo",
    category: "audio",
    price: 720000,
    published: true
  },
  {
    _id: "SKU-105",
    tenantId: "SHOP-A",
    title: "Tai nghe thử nghiệm",
    description: "Chưa công bố sản phẩm",
    category: "audio",
    price: 500000,
    published: false
  }
]);
```

Nếu chạy lại với cùng `_id`, `insertMany` sẽ gặp duplicate key. Hãy sử dụng database thử nghiệm mới hoặc dọn đúng document thử nghiệm theo quy trình được phép.

### 9.2. Mapping tường minh

Ta muốn:

- `title`, `description`: searchable text;
- `tenantId`, `category`: exact filter;
- `published`: boolean filter;
- `price`: numeric range.

Ví dụ:

```javascript
db.searchProductsLab.createSearchIndex(
  "catalog_text",
  {
    mappings: {
      dynamic: false,
      fields: {
        title: {
          type: "string",
          analyzer: "lucene.standard"
        },
        description: {
          type: "string",
          analyzer: "lucene.standard"
        },
        tenantId: {
          type: "token"
        },
        category: {
          type: "token"
        },
        published: {
          type: "boolean"
        },
        price: {
          type: "number"
        }
      }
    }
  }
);
```

**Lưu ý phiên bản:** `db.collection.createSearchIndex()` khả dụng khi MongoDB Server/driver/`mongosh` và deployment hỗ trợ index management commands. Với Atlas, công cụ/phiên bản cũ có thể cần dùng Atlas UI/Administration API thay vì method trên.

### 9.3. Vì sao `dynamic: false`?

`dynamic: true` có thể tự động index các field được hỗ trợ; điều này thuận tiện để thử nghiệm.

Nhưng production có thể muốn:

- Chỉ index các field có use case Search;
- Giảm dung lượng và chi phí indexing;
- Tránh đưa PII không cần thiết vào Search index;
- Kiểm soát cách text analyzer được áp dụng;
- Giữ definition ổn định khi schema thay đổi.

`dynamic: false` giúp kiểm soát rõ field. Đánh đổi là nếu sau này cần tìm field mới, phải cập nhật mapping.

### 9.4. `string` và `token` không giống nhau

Với Search mapping:

- `string`: phù hợp full-text analysis, tokenization và relevance.
- `token`: phù hợp một số **exact match/filter/facet/sort** theo điều kiện của Search operators và phiên bản.

Nếu `tenantId` được index như một chuỗi text với tokenizer thay vì token exact, filter exact string có thể không hoạt động như mong muốn. Trước khi chọn `equals`, xác minh field được index đúng data type mà operator yêu cầu.

### 9.5. Trạng thái index

Một cách kiểm tra trong mongosh:

```javascript
db.searchProductsLab.aggregate([
  {
    $listSearchIndexes: {
      name: "catalog_text"
    }
  }
]);
```

Hãy xem thông tin trạng thái/index queryable trong output thực tế. Trường cụ thể thay đổi theo phiên bản và công cụ, nhưng nguyên tắc là **đợi index sẵn sàng** rồi mới bật UI Search.

Lưu ý `$listSearchIndexes` là **aggregation stage quản lý Search index**, không phải query `$search`.

## 10. `$search`: truy vấn toàn văn cơ bản

Sau khi Search index sẵn sàng:

```javascript
db.searchProductsLab.aggregate([
  {
    $search: {
      index: "catalog_text",
      text: {
        query: "tai nghe",
        path: ["title", "description"]
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      description: 1,
      category: 1,
      score: {
        $meta: "searchScore"
      }
    }
  },
  { $limit: 10 }
]);
```

`$search` dùng index `"catalog_text"` để tìm các document phù hợp nội dung truy vấn. `searchScore` là điểm độ liên quan do Search engine tính theo mapping/query.

### 10.1. `$search` cần nằm đúng vị trí pipeline

Trong pipeline thông thường, `$search` là **stage đầu tiên**. Không đặt một `$match` phía trước rồi mong Search index tự hoạt động như một stage filter bất kỳ.

Sai về ý tưởng:

```javascript
db.searchProductsLab.aggregate([
  { $match: { published: true } },
  {
    $search: {
      index: "catalog_text",
      text: {
        query: "tai nghe",
        path: "title"
      }
    }
  }
]);
```

Đúng hơn, đưa các điều kiện Search hỗ trợ vào **`compound.filter`** hoặc tổ chức `$search` đầu tiên rồi dùng `$match` sau nếu cần kiểm tra trên document nguồn.

Có những trường hợp `$search` có thể đứng đầu **pipeline lồng trong `$lookup`/`$unionWith` hoặc view**, phụ thuộc phiên bản; quy tắc “đầu tiên” được hiểu đối với pipeline Search tương ứng, không phải áp máy móc lên toàn bộ chương trình.

## 11. Kết hợp text, tenant và trạng thái published

Trong hệ thống nhiều cửa hàng, một search API thường cần:

- Tìm từ khóa;
- Chỉ tìm trong `tenantId` được cấp quyền;
- Chỉ hiện sản phẩm đã published.

Dùng `compound`:

```javascript
db.searchProductsLab.aggregate([
  {
    $search: {
      index: "catalog_text",
      compound: {
        must: [
          {
            text: {
              query: "tai nghe",
              path: ["title", "description"]
            }
          }
        ],
        filter: [
          {
            equals: {
              path: "tenantId",
              value: "SHOP-A"
            }
          },
          {
            equals: {
              path: "published",
              value: true
            }
          }
        ]
      }
    }
  },
  {
    $project: {
      title: 1,
      category: 1,
      price: 1,
      score: {
        $meta: "searchScore"
      }
    }
  },
  { $limit: 10 }
]);
```

Điểm quan trọng:

- `must` góp phần vào logic matching/scoring theo Search semantics.
- `filter` dùng cho điều kiện bắt buộc **không nhằm cộng score**.
- `tenantId` cần mapping kiểu phù hợp với `equals`.
- Có `published` trong Search index giúp lọc trong Search query.

### 11.1. Filter trong Search index không phải lớp bảo mật duy nhất

Search index có **độ trễ đồng bộ**. Nếu sản phẩm vừa bị khóa hoặc quyền tenant vừa bị thu hồi, index có thể chưa phản ánh thay đổi ngay.

Do đó, với dữ liệu nhạy cảm, không nên dựa duy nhất vào kết quả từ Search index để quyết định quyền truy cập.

Kiến trúc an toàn hơn:

1. Xác thực người dùng và quyền tenant tại API.
2. Gắn filter tenant/visibility trong Search để giảm tập ứng viên.
3. Kiểm tra điều kiện cho phép ở dữ liệu nguồn hoặc lớp phân quyền đáng tin cậy khi cần.
4. Không trả PII/secret chỉ vì nó xuất hiện trong stored source hoặc search result.
5. Xử lý trường hợp Search index stale mà không rò rỉ dữ liệu.

**Search là công cụ truy xuất; authorization vẫn là hợp đồng an ninh của ứng dụng và database.**

### 11.2. Tại sao không luôn `$match` sau Search?

Một `$match` sau `$search` có thể kiểm tra dữ liệu hiện hành ở MongoDB, nhưng nó:

- Không làm Search index cập nhật nhanh hơn;
- Có thể dẫn đến ít kết quả hơn limit dự kiến nếu nhiều ứng viên bị loại;
- Không thay thế index-level filter cho hiệu năng;
- Cần thiết kế pagination/ranking phù hợp.

Trước khi đưa dữ liệu nhạy cảm vào Search, phải hiểu rõ đường đi của dữ liệu và chính sách quyền.

## 12. `$searchMeta`: đếm và thông tin tổng hợp

MongoDB Search hỗ trợ stage `$searchMeta` để lấy thông tin/metadata cho truy vấn.

Ví dụ:

```javascript
db.searchProductsLab.aggregate([
  {
    $searchMeta: {
      index: "catalog_text",
      text: {
        query: "tai nghe",
        path: ["title", "description"]
      },
      count: {
        type: "total"
      }
    }
  }
]);
```

Ví dụ thể hiện yêu cầu đếm tổng số kết quả phù hợp theo cơ chế Search. Tùy tình huống và chi phí, có thể dùng cơ chế đếm xấp xỉ/lower bound khi tài liệu cho phép.

### 12.1. `$searchMeta` không thay `$group` cho mọi số liệu

`$searchMeta` phục vụ metadata của Search request, ví dụ count/facet trong các cấu hình được hỗ trợ. Nó không phải một hệ thống BI tổng quát thay cho aggregation thông thường.

Nếu yêu cầu là báo cáo kế toán “doanh thu tất cả đơn đã thanh toán”, kết quả phải dựa trên nguồn dữ liệu có mức nhất quán và tính toán nghiệp vụ phù hợp, không coi số đếm trong một Search index có thể lag là sổ cái.

### 12.2. Facet cần field mapping đúng

Để faceting theo category/number/date, Search index có các kiểu field và quy tắc toán tử riêng. Một field index cho full-text chưa chắc đồng thời là field được dùng hợp lệ cho facet.

Với MongoDB Server/Search release hiện đại, `token` có thể tham gia những tính năng facet theo điều kiện hỗ trợ; các ví dụ dùng `stringFacet`/`numberFacet` trong tài liệu cũ có thể khác. Đừng copy một facet example cũ mà không đối chiếu phiên bản Search index mapping đang dùng.

## 13. Analyzer: điều kiện quyết định chất lượng tìm kiếm

**Analyzer** quyết định cách chuỗi được xử lý khi đưa vào index và/hoặc khi truy vấn:

```text
Input:
  "Tai nghe Bluetooth chống ồn"

Analyzer:
  normalize / tokenize / optional filters

Tokens:
  "tai", "nghe", "bluetooth", "chống", "ồn"
```

Đây là minh họa, token thực phụ thuộc analyzer.

### 13.1. Tại sao một index có thể tạo thành công nhưng tìm kiếm kém?

Ví dụ:

- Người dùng tìm “tai nghe” nhưng dữ liệu có “Tai-nghe”.
- Người dùng bỏ dấu: “chong on” nhưng dữ liệu là “chống ồn”.
- Sản phẩm có code “USB-C” nhưng tokenizer tách thành “usb”, “c”.
- Người dùng gõ thiếu chữ hoặc sai chính tả.
- Nhiều ngôn ngữ trộn cùng một field.
- Từ đồng nghĩa “laptop” và “máy tính xách tay” không được định nghĩa.

Search index chỉ tạo thành công nghĩa là mapping hợp lệ; **chất lượng relevance** vẫn phải kiểm chứng bằng tập query đại diện.

### 13.2. Tiếng Việt cần thử nghiệm riêng

Không nên mặc định analyzer tiếng Anh tự xử lý đúng:

- Dấu tiếng Việt;
- Tách từ đa âm tiết;
- Viết hoa/thường;
- Từ ghép;
- Tên thương hiệu;
- Từ viết tắt;
- Mã hàng hóa;
- Cách người dùng bỏ dấu;
- Từ đồng nghĩa theo ngành.

Có thể cần analyzer/token filters được MongoDB hỗ trợ, custom analyzer hoặc thiết kế nhiều field phục vụ các dạng query khác nhau. **Không hứa rằng chỉ cần `lucene.standard` là tìm kiếm tiếng Việt sẽ hiểu ý nghĩa ngôn ngữ đầy đủ.**

### 13.3. Analyzer là một phần của hợp đồng schema

Nếu định nghĩa index dùng analyzer A nhưng query path dùng cách phân tích không phù hợp, kết quả có thể khác kỳ vọng.

Khi đổi analyzer, cần:

1. Lập bộ query thử;
2. So sánh precision/recall và ranking;
3. Tạo/sửa index theo phương thức hỗ trợ;
4. Chờ build/sync hoàn tất;
5. Có kế hoạch rollout/rollback;
6. Giám sát search p95/p99 và no-result rate.

Đừng thay analyzer trực tiếp trên production rồi giả định Search index cập nhật ngay không có ảnh hưởng.

## 14. Autocomplete không phải `$regex` trên mọi field

Ứng dụng nhập:

```text
t
ta
tai
tai n
tai ng
```

Nếu cứ chạy regex không anchored trên hàng triệu document, truy vấn có thể đắt và xếp hạng kém.

Atlas Search có **`autocomplete`** operator với **index mapping `autocomplete`** phù hợp. Đây là tính năng được thiết kế cho search-as-you-type, khác với full-text `text`.

Một index cho autocomplete có thể dùng một field định nghĩa tương ứng, ví dụ:

```javascript
db.searchProductsLab.createSearchIndex(
  "catalog_autocomplete",
  {
    mappings: {
      dynamic: false,
      fields: {
        title: {
          type: "autocomplete",
          tokenization: "edgeGram",
          minGrams: 2,
          maxGrams: 15,
          foldDiacritics: true
        }
      }
    }
  }
);
```

Ví dụ query:

```javascript
db.searchProductsLab.aggregate([
  {
    $search: {
      index: "catalog_autocomplete",
      autocomplete: {
        query: "tai ng",
        path: "title"
      }
    }
  },
  {
    $project: {
      title: 1,
      score: {
        $meta: "searchScore"
      }
    }
  },
  { $limit: 10 }
]);
```

Cần kiểm tra support/cấu hình của `autocomplete` index và giới hạn gram fields ở phiên bản đang dùng.

### 14.1. Đánh đổi của autocomplete

- Index có thể lớn hơn vì nhiều token prefixes/ngrams.
- Query ngắn tạo nhiều kết quả không liên quan.
- Có thể cần debounce phía client.
- Cần minimum query length.
- Fuzzy tăng recall nhưng có thể làm kết quả lỏng và CPU tăng.
- Search index vừa tạo xong không đồng nghĩa sản phẩm vừa được cập nhật đã hiện tức thì.

Một sản phẩm “search-as-you-type” tốt cần cả **UI/UX, analyzer, index mapping và capacity**, không chỉ một operator.

## 15. Search index đồng bộ bất đồng bộ

Đây là điều kiện cực kỳ quan trọng về tính đúng đắn.

Dữ liệu nguồn được ghi ở MongoDB. Search index được duy trì qua cơ chế Search process và đồng bộ thay đổi. Có thể xuất hiện **khoảng trễ** giữa lúc ghi thành công và lúc Search index phản ánh nó.

Timeline:

```text
T0: Product SKU-101 đang published=true.
T1: Ứng dụng update published=false.
T2: MongoDB xác nhận ghi theo write concern.
T3: Search index chưa xử lý xong thay đổi.
T4: Một $search vẫn có thể thấy thông tin đã cũ.
T5: Search index bắt kịp; truy vấn phản ánh trạng thái mới.
```

Tại T4, việc query trả kết quả cũ không có nghĩa MongoDB mất write. Đó là sự khác biệt giữa **database source of truth** và **search projection**.

### 15.1. Read-your-writes không tự có qua `$search`

Nếu người dùng vừa thêm sản phẩm rồi ngay lập tức search tên sản phẩm, Search có thể chưa nhìn thấy sản phẩm đó.

Ứng dụng cần quyết định:

- Cho phép hiển thị trạng thái “Đang được lập chỉ mục”;
- Truy vấn trực tiếp document bằng `_id` để xác nhận;
- Poll trong giới hạn thời gian hợp lý;
- Thêm workflow cập nhật UI riêng;
- Chấp nhận eventual consistency cho search catalog.

Không dùng `$search` làm bước kiểm tra sau ghi bắt buộc phải thấy bản mới ngay nếu yêu cầu đòi linearizable read.

### 15.2. Search lag không được bỏ qua trong bảo mật

Ví dụ:

```text
T1: Admin thu hồi quyền xem một tài liệu.
T2: Database đã lưu permission mới.
T3: Search index chưa cập nhật.
T4: Người dùng query Search.
```

Search index có thể còn chứa term/metadata cũ. Quyết định **được phép trả document hay không** phải dựa vào cơ chế authorization hiện hành, không được phụ thuộc duy nhất vào một field vừa được index thay đổi.

### 15.3. Search index không thay thế write concern

`writeConcern: "majority"` làm mạnh bảo đảm ghi vào MongoDB data-bearing replicas; nó **không ép Search index đồng bộ xong trước khi ACK**.

Chính vì thế:

> **Majority-acknowledged write và Search-index visibility là hai mốc khác nhau.**

Nếu ứng dụng yêu cầu cập nhật tức thì một quyền bảo mật hoặc trạng thái đơn hàng, hãy đọc document nguồn theo mức concern phù hợp.

## 16. Index lifecycle: build, update, rollback và delete

Một Search index có nhiều trạng thái/vòng đời hơn một dòng config.

### 16.1. Khi tạo mới

```text
Definition submitted
        |
        v
Index build / initial sync
        |
        v
Queryable / ready
        |
        v
Serving production search
```

Tùy dữ liệu, index build có thể mất thời gian và tiêu thụ CPU/RAM/disk/network. Cần theo dõi trạng thái và tài nguyên thay vì chỉ nhìn response command.

### 16.2. Khi thay đổi definition

Ví dụ thêm field:

```text
catalog_text v1: title, description
catalog_text v2: title, description, brand
```

Một thay đổi có thể kích hoạt index rebuild hoặc quá trình cập nhật cần thời gian. Hãy xác định:

- Có thể cập nhật index đang dùng với cách nào?
- Có nên tạo index mới song song để so sánh?
- Số index đồng thời có vượt giới hạn tier không?
- Có đủ storage cho giai đoạn transition không?
- Backend có thể chọn index name theo feature flag không?

Với Free/Flex, giới hạn index count có thể cản trở chiến lược giữ v1/v2 cùng lúc.

### 16.3. Liệt kê Search index

```javascript
db.searchProductsLab.aggregate([
  { $listSearchIndexes: {} }
]);
```

`$listSearchIndexes` khác `getIndexes()` của database index thường.

### 16.4. Xóa Search index

```javascript
db.searchProductsLab.dropSearchIndex(
  "catalog_autocomplete"
);
```

Xóa index làm những query đang yêu cầu đúng tên index đó không thể tiếp tục dùng nó. Trước khi drop:

1. Kiểm tra ứng dụng đã chuyển sang index thay thế.
2. Đảm bảo không có job/search endpoint phụ thuộc.
3. Lập phương án rollback.
4. Xác minh Search metadata sau drop.
5. Chỉ thực hiện ở production theo quy trình thay đổi được phép.

Không dùng `db.collection.dropIndex()` như công cụ mặc định để xóa một MongoDB Search index.

### 16.5. Không hứa mọi backup tự giữ nguyên Search index ready

Sau restore/migrate/cluster tier change, cần kiểm tra Search index definitions và trạng thái build. Tùy Atlas plan, cách snapshot/restore và deployment, Search indexes có thể cần **sync/rebuild**.

Runbook restore phải xác minh **cả dữ liệu nguồn và Search readiness**, không chỉ thành công khi application kết nối được MongoDB.

## 17. Phạm vi quyền và quản trị Atlas

Atlas có ít nhất hai lớp quyền có thể liên quan:

- **Atlas project/organization roles:** tạo/xem deployment, quản lý Search index qua UI/API, Search Nodes.
- **MongoDB database user privileges:** đọc collection, chạy aggregate, quản lý Search index bằng `mongosh`/driver.

Không được coi có connection string là đã có mọi quyền.

### 17.1. Phân biệt role của application và operator

Application Search API thường cần:

- Kết nối và đọc collection được phép;
- Chạy aggregation Search;
- Không cần drop/rebuild index;
- Không cần quyền chỉnh Atlas project hoặc billing.

Operator/CI deployment cần:

- Tạo/sửa Search index;
- Xem trạng thái;
- Triển khai Search Nodes nếu có;
- Theo dõi metrics và settings.

Tách quyền hạn giúp giảm rủi ro một service bị lộ credential có thể xóa index hoặc thay cấu hình Search.

### 17.2. Không nhét credentials vào bài code

Sai:

```javascript
// Tránh hardcode URI chứa user/password trong repo.
const uri = "mongodb+srv://username:password@example.mongodb.net";
```

Thực tế nên dùng secret manager/environment variables và TLS. Ví dụ bài học dùng đối tượng `db` đã được kết nối bằng `mongosh` để không đưa secrets vào file.

### 17.3. Search index chứa những gì?

Search index lưu những biểu diễn dẫn xuất từ dữ liệu document để phục vụ search. Chúng có thể chứa tokens, field values, stored source hoặc dữ liệu cần thiết cho query.

Không đánh đồng “không lưu nguyên document” với “không có dữ liệu nhạy cảm”. Index text có thể chứa từ khóa nhạy cảm; stored source có thể giữ bản sao field. Bảo vệ Search Nodes và quyền truy cập phải tương xứng với dữ liệu nguồn.

## 18. Các tính năng phụ thuộc phiên bản

Không phải mọi tính năng MongoDB Search xuất hiện đồng thời trên mọi MongoDB Server version.

Một số nhóm có điều kiện phiên bản riêng:

- Programmatic Search index management;
- Query Search trên views;
- Search trên sharded views;
- Search trong `$lookup`/`$unionWith`;
- Sort và facet trên sharded clusters;
- Stored Source;
- Search pagination qua `searchAfter`/`searchBefore`;
- Các toán tử và tính năng ranking/hybrid search mới;
- Query/Index trên các loại collection đặc biệt.

Ví dụ các mốc công bố trong tài liệu Atlas Compatibility:

| Tính năng | Điều kiện phiên bản minh họa |
|---|---|
| Create Search index trên views | MongoDB 8.0+ theo docs |
| Query view trực tiếp với `$search`/`$searchMeta` | MongoDB 8.1+ |
| Search trên sharded views | MongoDB 8.2+ |
| `$lookup` với `$search` | Có các dòng hỗ trợ riêng theo version |
| Pagination `searchAfter`/`searchBefore` | Có các patch version tối thiểu theo docs |
| Dedicated Search Nodes | Cần tổ hợp Atlas tier, server version, cloud/region được hỗ trợ |

**Không dùng bảng này thay cho compatibility matrix chính thức**. Khi release mới ra hoặc cluster đang dùng patch version cũ, kiểm tra từng feature cụ thể trước khi áp dụng.

### 18.1. Time-series collection

MongoDB Search có **giới hạn đối với time-series collections**. Tài liệu compatibility hiện hành nêu Search không được hỗ trợ cho time-series, và các phiên bản mới có thể báo lỗi tường minh thay vì chỉ trả tập rỗng.

Nếu dữ liệu là sensor/time-series, cân nhắc:

- Query time-series bằng index/query thông thường phù hợp;
- Materialize dữ liệu cần tìm text sang regular collection;
- Tách search catalog khỏi raw time-series;
- Đối chiếu giới hạn của phiên bản server.

Không tạo Search index trên một time-series collection rồi kỳ vọng nó hành xử như regular collection.

### 18.2. Các feature preview không phải SLA phổ quát

Một số deployment mới như Atlas Infinite hoặc tính năng Search mở rộng có thể đang ở trạng thái preview. Preview có thể đi kèm:

- Giới hạn chức năng;
- Thay đổi API;
- Giới hạn region/tier;
- Ràng buộc support/SLA;
- Cách tính phí riêng.

Trong thiết kế production, phải xem **release status thực tế** và policy của tổ chức, không chỉ khả năng bật trong Atlas UI.

## 19. Atlas Search và MongoDB Vector Search

Hai khả năng có quan hệ về hạ tầng `mongot`, nhưng giải quyết những câu hỏi khác nhau.

**MongoDB Search**:

```text
Người dùng gõ "tai nghe chống ồn"
      |
Lucene/analyzer/keywords
      |
Văn bản khớp + relevance score
```

**MongoDB Vector Search**:

```text
Người dùng mô tả ý định
      |
Embedding model -> vector
      |
Vector similarity / ANN
      |
Document gần nghĩa theo không gian embedding
```

Các stage thông dụng:

- `$search` / `$searchMeta`: lexical Search và metadata tương ứng.
- `$vectorSearch`: vector similarity search trong cấu hình được hỗ trợ.

Không khẳng định “Atlas Search tự hiểu mọi từ đồng nghĩa” khi chưa có synonyms hoặc mô hình vector thích hợp.

### 19.1. Hybrid search

Một ứng dụng có thể kết hợp:

- Lexical Search cho tên, mã hàng và từ khóa chính xác;
- Vector Search cho câu hỏi theo ý nghĩa;
- Re-ranking/rank fusion theo tính năng và version.

Nhưng hybrid pipeline có thể cần nhiều Search/Vector indexes, tăng chi phí và gặp giới hạn tier. Trước khi thiết kế, hãy kiểm tra tính tương thích và đo lợi ích relevance thực.

## 20. Hiệu năng: điều gì khiến Search chậm?

Các yếu tố chính:

1. **Index size:** số document, field, tokens, analyzers.
2. **Query complexity:** fuzzy, compound, broad text, synonyms.
3. **Result count:** lấy top 10 khác quét hàng triệu.
4. **Stored source:** có cần fetch document từ database không.
5. **Cluster QPS/concurrency:** bao nhiêu query cùng lúc.
6. **Indexing rate:** tốc độ ingest/update/delete.
7. **Resource contention:** `mongod` và `mongot` dùng chung hay tách node.
8. **Network RTT:** app ↔ cluster, database ↔ Search nodes.
9. **Sharding:** search phải phối hợp bao nhiêu shards/partitions.
10. **Index freshness/rebuild:** Search đang initial sync hoặc catch-up.

### 20.1. Search không thay thế ứng dụng giới hạn dữ liệu

Một query không có limit hoặc returnStoredSource không kiểm soát có thể trả payload rất lớn.

Ví dụ cấu trúc API tốt:

```javascript
db.searchProductsLab.aggregate([
  {
    $search: {
      index: "catalog_text",
      text: {
        query: "tai nghe",
        path: "title"
      }
    }
  },
  { $limit: 20 },
  {
    $project: {
      _id: 1,
      title: 1,
      price: 1
    }
  }
]);
```

Các giới hạn của API nên gồm:

- Query length;
- Số ký tự autocomplete tối thiểu;
- Max page size;
- Rate limiting;
- Timeouts;
- Giới hạn fuzzy/prefix expansions;
- Query allowlist theo nghiệp vụ;
- Giám sát query patterns.

### 20.2. Không đếm mọi match nếu không cần

Nếu UI chỉ cần hiển thị “20 kết quả đầu”, việc tính tổng chính xác trên tập cực lớn có thể tốn thêm tài nguyên. Nên chọn count/facet theo yêu cầu UX và đánh giá cách dùng `$searchMeta` phù hợp.

### 20.3. Search score không chứng minh query nhanh

Một kết quả có score cao không liên quan tới p95 latency hoặc số tài nguyên đã dùng. Đừng dùng score để đánh giá hiệu năng.

## 21. Giám sát Search ở production

Những nhóm metric cần có:

| Nhóm | Điều cần đo |
|---|---|
| Search query | QPS, latency p50/p95/p99, error rate |
| Index sync | Indexing lag, số thay đổi chưa phản ánh |
| Index lifecycle | BUILDING/READY/STALE/error, rebuild duration |
| Tài nguyên | CPU, RAM, disk, IOPS của Search/DB |
| Search Nodes | Node count, health, restart, capacity |
| Network | DB↔Search transfer, RTT, saturation |
| Query quality | Zero-result rate, click-through, relevance test |
| Autocomplete | Prefix lengths, query volume, debouncing |
| Index footprint | Size/index count, field mapping growth |
| Application | Timeout, fallback rate, authorization rejects |
| Cost | Search Nodes/tier, bandwidth, cluster resources |

### 21.1. Kết quả Search cũ có thể không được phát hiện chỉ bằng uptime

Cluster có thể có:

```text
mongod: healthy
mongot: queryable
Search index: lagging / stale
API: HTTP 200
```

Người dùng vẫn nhận được kết quả, nhưng dữ liệu có thể chưa cập nhật.

Vì vậy phải theo dõi **index freshness**, không chỉ số lượng query thành công.

### 21.2. Giám sát API với canary data

Một cách thử trên môi trường thích hợp:

1. Ghi một document thử với ID riêng vào collection dành cho canary.
2. Đo thời gian từ lúc MongoDB ACK đến khi Search nhìn thấy nó.
3. Xóa/cập nhật canary và đo thời gian Search phản ánh.
4. Báo alert nếu lag vượt budget.
5. Loại canary khỏi các kết quả dành cho người dùng.

Không dùng thông tin canary làm tuyên bố đảm bảo consistency tuyệt đối; nó là một **chỉ số quan sát thực tế** trên đường đi đang kiểm thử.

## 22. Thiết kế chi phí: co-located hay Search Nodes?

Một bảng so sánh định hướng:

| Tiêu chí | Co-located `mongot` | Dedicated Search Nodes |
|---|---|---|
| Provisioning | Đơn giản | Cần cấu hình Search tier/nodes |
| Chi phí ban đầu | Có thể thấp hơn | Có phí node riêng |
| Cạnh tranh CPU/RAM với DB | Có thể có | Giảm đáng kể |
| Scale Search độc lập | Hạn chế hơn | Tốt hơn |
| Index rebuild load | Cùng hạ tầng DB | Cách ly tốt hơn |
| Hợp với dev/prototype | Rất phù hợp | Thường chưa cần |
| Production QPS cao | Cần benchmark kỹ | Thường nên cân nhắc |
| HA/region options | Theo cluster | Theo cấu hình Search Nodes được hỗ trợ |
| Network giữa Search và DB | Co-located | Có chi phí/RTT truyền dữ liệu riêng |

**Không nên chọn Search Nodes dựa trên con số document duy nhất.** Một triệu document với text dài, nhiều analyzer và fuzzy queries có thể nặng hơn hàng chục triệu document có vài field ngắn và truy vấn equality đơn giản.

Tài liệu MongoDB có các ngưỡng **khuyến nghị** cho môi trường thử nghiệm, chẳng hạn lượng document/indexed data/search queries, nhưng đó không phải hard limit phổ quát. Cần benchmark và sizing theo workload.

## 23. Java MongoDB Driver: chạy `$search`

Với Java Sync Driver, có thể xây aggregation pipeline bằng `Document`. Đây là ví dụ giữ cấu trúc BSON sát với MongoDB command.

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;

MongoDatabase database = mongoClient.getDatabase("searchLab");
MongoCollection<Document> products =
    database.getCollection("searchProductsLab");

Document search = new Document(
    "$search",
    new Document("index", "catalog_text")
        .append("text",
            new Document("query", "tai nghe")
                .append("path", Arrays.asList("title", "description")))
);

Document project = new Document(
    "$project",
    new Document("title", 1)
        .append("price", 1)
        .append("score", new Document("$meta", "searchScore"))
);

Document limit = new Document("$limit", 10);

List<Document> pipeline = Arrays.asList(search, project, limit);

for (Document item : products.aggregate(pipeline)) {
    System.out.println(item.toJson());
}
```

Điều kiện để code chạy:

- MongoClient đã kết nối tới deployment hỗ trợ Search;
- Có `catalog_text` Search index phù hợp;
- Index đã queryable;
- Database user có quyền đọc;
- Collection đã có dữ liệu và field đúng;
- Driver/server tương thích với pipeline đang dùng.

### 23.1. Không cần dùng Java driver phiên bản mới chỉ để viết BSON?

Khi chỉ **chạy** aggregation `$search`, nhiều phiên bản driver có thể truyền stage BSON tới server nếu server hỗ trợ. Nhưng nếu muốn **quản lý Search index** qua các helper APIs, cần driver version hỗ trợ method tương ứng.

Tài liệu quản lý Search index trên Atlas có nêu các **mốc phiên bản driver tối thiểu** riêng, ví dụ Java 4.11+ cho một số chức năng quản lý. Trước khi gọi create/update/drop Search index từ code, kiểm tra API docs của driver đang dùng.

### 23.2. Java: không hardcode credentials

Ví dụ kết nối nên lấy URI từ secret/config:

```java
String uri = System.getenv("MONGODB_URI");

if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("MONGODB_URI is required");
}

// MongoClient được tạo bằng MongoClients.create(uri)
// và đóng theo lifecycle của ứng dụng.
```

Không đưa URI thực, username/password hoặc chứng chỉ vào source code hay log.

## 24. Vì sao search không nên dùng để kiểm tra tính đúng đắn giao dịch?

Ví dụ sản phẩm vừa bị ẩn:

```javascript
db.products.updateOne(
  { _id: "SKU-001" },
  { $set: { published: false } }
);
```

Nếu API **phải bảo đảm không hiển thị sản phẩm ẩn**, một query Search chỉ filter `published: true` có thể còn trả ứng viên stale trong lúc indexing lag.

Khi đó cần:

- Filter trong Search để tối ưu;
- Kiểm tra trạng thái thực tại source nếu cần bảo đảm mạnh;
- Không dùng indexed fields làm nguồn authorization duy nhất;
- Có hành vi khi database/read concern không xác nhận được;
- Cân nhắc dữ liệu nào được lưu vào stored source.

Tương tự, không dùng `$search` để hỏi:

```text
"Đơn hàng có được thanh toán rồi chưa?"
"User này có còn quyền truy cập tài liệu không?"
"Kho còn đủ để trừ 1 sản phẩm không?"
```

như nguồn sự thật duy nhất. Các quyết định này cần query/transaction/unique constraints phù hợp với invariant nghiệp vụ.

## 25. Trường hợp Search thất bại: phân loại trước khi sửa

Một Search query có thể lỗi vì nhiều lý do khác nhau.

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| Unrecognized pipeline stage `$search` | Server/deployment chưa hỗ trợ hoặc không cấu hình Search | Cluster tier, version, `mongot`, connection target |
| Search index not found | Sai index name hoặc chưa tạo | `$listSearchIndexes`, namespace |
| Index chưa queryable | Initial build chưa xong | Status, logs, resource |
| Không có kết quả | Analyzer/mapping/query mismatch, lag, data thiếu | Sample data, mapping, query paths |
| Kết quả thiếu mới nhất | Indexing lag | Freshness metric, source read |
| Lỗi type của `equals` | Field mapping không phù hợp | `token`/number/boolean types |
| `$search` không được đứng vị trí này | Sai thứ tự pipeline | Đặt stage đầu pipeline tương ứng |
| Search latency cao | Resource, index size, query broad, contention | Atlas metrics, explain/search tracing nếu có |
| Tạo index lỗi | Permissions, tier limits, invalid definition | Role, index count, JSON size, server logs |
| Không tạo được Search Nodes | Tier/region/topology không đủ điều kiện | Atlas Search tier availability |
| Sau restore Search không trả kết quả | Index chưa sync/rebuild | Index status và deployment runbook |
| Dùng `$text` nhưng mong fuzzy/autocomplete | Dùng sai engine | Tạo Search index và `$search` |

Không nên kết luận mọi lỗi `$search` do index chưa build. Kiểm tra theo tầng: **deployment → permissions → index definition → index status → query shape → resource**.

### 25.1. Tránh sửa bằng cách tạo lại index liên tục

Một index lớn đang BUILDING cần thời gian và tài nguyên. Rebuild nhiều lần liên tiếp có thể tăng tải và làm tình trạng chậm tệ hơn. Trước tiên xem status, logs và khả năng tài nguyên, sau đó mới quyết định cập nhật/xóa/tạo lại.

### 25.2. Query không trả kết quả không đồng nghĩa không có document

Có thể document tồn tại trong collection nhưng:

- Field không được mapping;
- Analyzer khác query expectation;
- Index chưa bắt kịp;
- Filter bị áp sai kiểu;
- Search index đang lỗi;
- Tenant/visibility filter loại bỏ;
- Query dùng index name sai.

Dùng một `findOne({_id: ...})` có quyền hợp lệ để đối chiếu source document khi debug.

## 26. Triển khai production theo các giai đoạn

### Giai đoạn 1 — Xác định mục tiêu tìm kiếm

Ghi rõ:

- Người dùng tìm theo field nào?
- Query examples thật là gì?
- Có cần tiếng Việt có dấu/không dấu?
- Có cần autocomplete/fuzzy/synonyms?
- Dự kiến QPS, p95 latency, tỷ lệ zero-result?
- Bao nhiêu document, kích thước trung bình?
- Có dữ liệu nhạy cảm?
- Freshness SLO chấp nhận bao nhiêu giây?
- Có yêu cầu read-after-write không?

### Giai đoạn 2 — Xác nhận deployment

Kiểm tra:

- Atlas tier và region;
- Server version;
- Số Search indexes được phép;
- Có cần Dedicated Search Nodes không;
- Project/database roles;
- Network/TLS;
- Chi phí;
- Nếu self-managed: `mongot` compatibility và topology.

### Giai đoạn 3 — Chuẩn bị index definition

- Chọn dynamic/static mapping;
- Chọn searchable paths;
- Token fields cho exact filters;
- Analyzers;
- Synonym/autocomplete fields;
- Nhu cầu facet/sort/stored source;
- Ràng buộc privacy;
- Naming/versioning của indexes.

### Giai đoạn 4 — Build và kiểm tra trạng thái

- Tạo index từ UI/API/mongosh/driver;
- Chờ queryable;
- Đo thời gian initial sync;
- Kiểm tra sample queries;
- Đo search lag;
- Ghi metric tài nguyên.

### Giai đoạn 5 — Kiểm thử liên quan nghiệp vụ

- Query đúng tên sản phẩm;
- Query không dấu/sai chính tả;
- Query tenant isolation;
- Trường hợp sản phẩm vừa published/unpublished;
- Product vừa insert;
- Product vừa delete;
- Index rebuild;
- Nhiều concurrent users;
- Timeout/fallback;
- Authorization kiểm tra lại ở source nếu cần.

### Giai đoạn 6 — Rollout

- Feature flag cho Search endpoint;
- So sánh kết quả với hệ cũ trên tập query đại diện;
- Canary traffic;
- Theo dõi p95/p99 và search quality;
- Rollback bằng chuyển luồng ứng dụng, không vội drop index;
- Sau khi ổn định mới dọn index không còn sử dụng.

### Giai đoạn 7 — Runbook

Cần có câu trả lời cho:

- Search index lỗi/STALE thì API làm gì?
- Index đang rebuild thì có fallback không?
- Search Nodes hết RAM hoặc disk thì ai xử lý?
- Dữ liệu nguồn có sẵn nhưng Search chưa cập nhật thì UX ra sao?
- Các secrets và ACL được xoay vòng thế nào?
- Khi restore/region failover, làm sao xác minh Search ready?
- Khi index count chạm giới hạn tier, khi nào scale?
- Khi nào cần thay analyzer và so sánh relevance?

## 27. Các bài tập thực hành

### Bài 1 — Phạm vi Search so với database index

Cho những yêu cầu sau:

1. Tìm đúng sản phẩm theo `_id`.
2. Chặn trùng `sku`.
3. Tìm sản phẩm gần nội dung “tai nghe chống ồn”.
4. Gợi ý sản phẩm khi người dùng gõ 3 ký tự.
5. Xác nhận đơn hàng đã thanh toán trước khi giao.
6. Lọc danh sách theo khoảng giá và tenant.

Hãy chọn MongoDB B-tree index, unique index, transaction hoặc Atlas Search cho từng yêu cầu. Giải thích vì sao không có một Search index thay thế được tất cả.

### Bài 2 — Phân loại môi trường triển khai

So sánh:

- Atlas Free;
- Atlas Flex;
- Atlas Dedicated co-located;
- Dedicated Search Nodes;
- Atlas local deployment;
- Self-managed Search với `mongot`.

Với mỗi môi trường, ghi: ai quản lý Search process, hạn chế chính, mục tiêu phù hợp và điều kiện phải kiểm tra trước khi dùng production.

### Bài 3 — Tạo Search index

Trên MongoDB Search deployment thử nghiệm:

1. Tạo collection `searchProductsLab` với 5 document.
2. Tạo index `catalog_text`.
3. Cấu hình `title`/`description` là `string`.
4. Cấu hình `tenantId`/`category` là `token`.
5. Kiểm tra trạng thái với `$listSearchIndexes`.
6. Chỉ chạy query khi index queryable.

### Bài 4 — Tìm text và score

Viết `$search` tìm “tai nghe” trong title và description.

1. Trả title/price/score.
2. Limit 10.
3. So sánh top results.
4. Thay từ khóa bằng “bluetooth”.
5. Vì sao điểm searchScore không phải business version?

### Bài 5 — Compound Search

Cần trả kết quả chỉ thuộc SHOP-A và published true.

1. Dùng `compound.must` cho text.
2. Dùng `compound.filter` cho tenantId và published.
3. Giải thích vì sao `equals` cần field mapping phù hợp.
4. Vì sao vẫn cần authorization ở application?
5. Hệ quả khi field published vừa thay đổi nhưng Search index lag là gì?

### Bài 6 — Độ trễ Search index

Một sản phẩm vừa insert và MongoDB ACK majority. UI Search ngay sau đó không thấy sản phẩm.

1. Có thể là hành vi hợp lệ không?
2. Majority ACK và Search visibility khác nhau như thế nào?
3. Thiết kế UX khi index đang catch up.
4. Làm sao đo độ trễ từ write ACK đến Search visibility?
5. Khi nào phải đọc trực tiếp database thay vì Search?

### Bài 7 — Autocomplete

Tạo index autocomplete cho `title` trong môi trường hỗ trợ.

1. Query “tai ng”.
2. Đo số kết quả và thời gian trả.
3. Thử nhiều `minGrams`/`maxGrams` có kiểm soát.
4. Vì sao autocomplete có thể làm index lớn hơn?
5. Thiết kế debounce/min length cho UI.

### Bài 8 — Tiếng Việt và analyzer

Lập bộ query:

```text
tai nghe
tai-nghe
Tai Nghe
chống ồn
chong on
điện thoại
smartphone
bluetooth
blutooth
```

Kiểm tra:

- Query nào match với analyzer hiện tại?
- Có cần custom analyzer/fold diacritics?
- Có cần synonyms?
- Có chấp nhận fuzzy typo?
- Precision/recall thay đổi thế nào?

Không tự khẳng định index có hiểu tiếng Việt nếu chưa chạy thử trên dữ liệu thực.

### Bài 9 — Free/Flex limits

Một project đang dùng Free cluster đã có 3 Search/Vector indexes.

1. Có thể tạo thêm index thứ tư không theo giới hạn docs hiện hành?
2. Vì sao đổi tên index không tránh được quota?
3. Nếu cần blue/green index rollout, phải lên kế hoạch gì?
4. Khi scale lên Flex/Dedicated, cần xác minh việc rebuild/sync nào?
5. Con số giới hạn có thể được xác nhận ở đâu?

### Bài 10 — Dedicated Search Nodes

Giả sử database latency p99 tăng mạnh khi search QPS cao.

1. Làm sao xác định contention giữa `mongod` và `mongot`?
2. Dedicated Search Nodes hỗ trợ gì?
3. Chúng có làm Search linearizable không?
4. Chi phí nào có thể tăng?
5. Những metric nào cần đo trước và sau khi tách nodes?

### Bài 11 — Self-managed compatibility

Một nhóm đang chạy MongoDB Community Edition cũ trên một standalone Windows server.

1. Có thể kết luận ngay `$search` dùng được không?
2. Cần có những thành phần nào ngoài `mongod`?
3. Tại sao phải xem MongoDB Server–`mongot` compatibility matrix?
4. Có chạy native Windows `mongot` theo các tài liệu support hiện hành không?
5. Vì sao local container không đồng nghĩa production HA?

### Bài 12 — Search index lifecycle

Một index `catalog_text` được thay đổi analyzer.

1. Kế hoạch thử nghiệm trước khi đổi là gì?
2. Sau lệnh update definition có phải index sẵn sàng ngay không?
3. Có nên giữ index cũ song song không?
4. Tài nguyên nào tăng trong rebuild?
5. Khi nào được phép drop index cũ?

### Bài 13 — Search so với Vector Search

Đề bài:

- Tìm chính xác tên model “ABC-123”;
- Tìm văn bản “tai nghe chống ồn”;
- Tìm sản phẩm tương tự theo mô tả dài tự nhiên.

Hãy đề xuất lexical Search, vector Search hoặc hybrid và giải thích **điều kiện index, dữ liệu và hạ tầng** của mỗi cách.

### Bài 14 — Thiết kế API production

Xây thiết kế cho:

```text
GET /products/search?q=...&tenant=...&limit=...
```

Nêu:

- Authentication/authorization;
- Tenant filter;
- Text analyzer;
- Page size;
- Search index name/version;
- Retry/timeout/fallback;
- Index freshness SLO;
- Monitoring và alert;
- Xử lý index unavailable;
- Khi nào đọc dữ liệu nguồn;
- Cách rollout index mới.

### Bài 15 — Recovery

Một Atlas cluster phục hồi dữ liệu sau sự cố. API MongoDB `find()` hoạt động, nhưng `$search` trả lỗi index chưa sẵn sàng.

1. Đây có nhất thiết là lỗi dữ liệu nguồn không?
2. Cần kiểm tra những trạng thái nào của Search indexes?
3. Có nên cho ứng dụng nhận search traffic ngay không?
4. Khi nào dùng fallback?
5. Vì sao runbook DR phải bao gồm Search readiness?

## 28. Checklist trước khi triển khai

- [ ] Biết rõ dùng **Atlas managed**, local hay **self-managed `mongot`**.
- [ ] Đã đối chiếu cluster tier/region/server version với compatibility docs.
- [ ] Đã phân biệt Free/Flex feature limits với production capacity.
- [ ] Có Project/database roles đúng mức cần thiết.
- [ ] Kết nối MongoDB qua network/TLS/credentials hợp lệ.
- [ ] Tạo Search index bằng đúng API/UI hỗ trợ.
- [ ] Phân biệt `createSearchIndex()` với B-tree `createIndex()`.
- [ ] Đã đợi index READY/queryable sau initial build.
- [ ] Mapping rõ searchable text, token filters, numeric/boolean fields.
- [ ] Analyzer được thử trên ngôn ngữ/dữ liệu thực.
- [ ] `$search`/`$searchMeta` ở vị trí pipeline được hỗ trợ.
- [ ] Có giới hạn query length, page size, autocomplete load.
- [ ] Không dựa vào Search index để cưỡng chế uniqueness hoặc authorization.
- [ ] Đã thiết kế xử lý **eventual consistency/indexing lag**.
- [ ] Có metrics p95/p99, Search QPS, index size, sync lag và node health.
- [ ] Có capacity/cost plan cho co-located hoặc Dedicated Search Nodes.
- [ ] Không phụ thuộc tuyệt đối vào feature preview chưa đủ SLA.
- [ ] Có rollback và recovery khi index cần rebuild/không queryable.
- [ ] Có quy trình thử nghiệm trước khi sửa mappings/analyzers.
- [ ] Nếu self-managed, đã xác minh `mongot` runtime, OS, security và phiên bản tương thích.

## 29. Tài liệu chính thức tham khảo

Các trang dưới đây được dùng để đối chiếu những khái niệm, phạm vi triển khai và giới hạn phiên bản. Tài liệu MongoDB thay đổi theo release, cần kiểm tra **bản hiện hành tại ngày triển khai**.

- [MongoDB Search — tổng quan](https://www.mongodb.com/docs/search/)
- [MongoDB Search Deployment Options](https://www.mongodb.com/docs/search/deployment/deployment-options/)
- [MongoDB Search Compatibility & Limitations](https://www.mongodb.com/docs/search/deployment/feature-compatibility/)
- [MongoDB Search — Manage Indexes](https://www.mongodb.com/docs/search/indexes/manage-indexes/)
- [MongoDB Search and Vector Search on Self-Managed Deployments](https://www.mongodb.com/docs/search/self-managed/current/)
- [Self-Managed mongot Compatibility and Requirements](https://www.mongodb.com/docs/search/self-managed/current/deployment/compatibility-requirements/)
- [MongoDB Atlas Search Node Costs](https://www.mongodb.com/docs/atlas/billing/search-node/)
- [MongoDB Atlas Search Node Workload Isolation](https://www.mongodb.com/docs/atlas/cluster-config/multi-cloud-distribution/)
- [createSearchIndexes Database Command](https://www.mongodb.com/docs/manual/reference/command/createsearchindexes/)
- [$search Aggregation Stage](https://www.mongodb.com/docs/atlas/atlas-search/aggregation-stages/search/)
- [$searchMeta Aggregation Stage](https://www.mongodb.com/docs/atlas/atlas-search/aggregation-stages/searchMeta/)
- [MongoDB Search Index Mapping](https://www.mongodb.com/docs/atlas/atlas-search/define-field-mappings/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)

## Kết luận

**Atlas Search** là năng lực tìm kiếm toàn văn dựa trên Lucene được MongoDB Atlas cung cấp theo mô hình **managed**. Trong tài liệu sản phẩm hiện đại, nó thuộc **MongoDB Search**, với các stage như `$search`, `$searchMeta`, Search indexes và các tính năng ranking, autocomplete, fuzzy matching, synonyms, facet và highlight.

Điều kiện triển khai gồm nhiều lớp: **deployment phải hỗ trợ Search**, có quyền truy cập, Search index mapping phù hợp, **index phải queryable**, và hạ tầng phải có đủ tài nguyên. Atlas **Free/Flex** thích hợp cho học tập và nhu cầu nhỏ nhưng có giới hạn; **Dedicated cluster** phù hợp workload lớn hơn; **Dedicated Search Nodes** cho phép tách Search khỏi database khi tier/region đáp ứng điều kiện. Các mô hình **local** phù hợp phát triển, còn **self-managed MongoDB Search** là lựa chọn có thật trên những phiên bản/kiến trúc được hỗ trợ nhưng đội vận hành phải tự quản lý `mongot`.

Search index được **đồng bộ bất đồng bộ** với dữ liệu nguồn. Vì vậy, **Search không thay thế transaction, uniqueness, backup, authorization hay những truy vấn cần read-after-write/linearizable**. Một Search API production phải dự liệu indexing lag, index lifecycle, analyzer, filter bảo mật, resource contention, phiên bản, phí hạ tầng và khả năng phục hồi sau sự cố.

**Triển khai Atlas Search đúng không dừng ở việc chạy được `$search`: cần chọn đúng môi trường, index đúng dữ liệu, biết rõ giới hạn nhất quán và chứng minh hạ tầng đáp ứng workload trước khi cam kết trải nghiệm tìm kiếm cho người dùng.**

