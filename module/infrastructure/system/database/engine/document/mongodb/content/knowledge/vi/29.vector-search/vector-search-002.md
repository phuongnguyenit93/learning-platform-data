# Điều kiện sử dụng Atlas Vector Search theo môi trường và phiên bản

## Mục tiêu bài học

**Atlas Vector Search**, trong các tài liệu MongoDB mới thường được gọi rộng hơn là **MongoDB Vector Search**, cho phép lưu embeddings cạnh dữ liệu document, tạo **vector search index** và truy vấn bằng aggregation stage `$vectorSearch`. Tính năng phục vụ semantic search, gợi ý nội dung, hệ thống hỏi–đáp trên dữ liệu nội bộ (RAG) và hybrid search.

Tuy nhiên, một câu lệnh `$vectorSearch` viết đúng cú pháp vẫn có thể thất bại vì ứng dụng đang chạy trên **môi trường hoặc phiên bản không hỗ trợ**, cluster thiếu search service, index chưa sẵn sàng, quyền tạo index không đủ, hoặc tính năng chỉ hỗ trợ ở một phiên bản cụ thể. Cần phân biệt ít nhất năm lớp điều kiện:

1. **Deployment:** Atlas cloud, Atlas CLI local, MongoDB Community/Enterprise self-managed.
2. **Phiên bản:** các ngưỡng MongoDB Server và phiên bản công cụ/driver.
3. **Tier và kiến trúc:** Free, Flex, Dedicated, Search Nodes, Linux self-managed, tài nguyên.
4. **Index và dữ liệu:** loại index `vectorSearch`, path, dimensions, similarity, filter fields, embedding model.
5. **Vận hành:** quyền truy cập, network, tính sẵn sàng của search process, consistency, quota và benchmark.

Bài thuộc **Database Engine Document MongoDB → Tìm kiếm vector → Điều kiện sử dụng Atlas Vector Search theo môi trường và phiên bản**. Sau khi học, bạn có thể:

- Phân biệt vector search với chỉ mục B-tree, text index, `2dsphere`, `$search` và tính khoảng cách vector trong ứng dụng.
- Xác định điều kiện sử dụng `$vectorSearch` trên Atlas và các hướng local/self-managed.
- Biết ngưỡng phiên bản cho **ANN** và **ENN** cũng như một số tính năng aggregation liên quan.
- Phân biệt **Atlas Free**, **Flex**, **Dedicated** và **Dedicated Search Nodes**.
- Hiểu vì sao “MongoDB Server chạy được” chưa chứng minh search service đang hoạt động.
- Kiểm tra permissions, network access, TLS, driver, index readiness.
- Tạo và thử vector index với GeoJSON không liên quan, dữ liệu mẫu và query vector hợp lệ.
- Phân biệt `queryVector` do ứng dụng tạo với embedding tự động (nếu môi trường hỗ trợ).
- Xử lý lỗi stage unsupported, command not found, index not found, dimensions mismatch và filter index mismatch.
- Thiết kế ma trận kiểm tra tương thích trước nâng cấp, CI/CD và production rollout.
- Lập kế hoạch chi phí, RAM, index build time, search latency, recall và resource isolation.

> **Lưu ý về thời điểm:** Các điều kiện cụ thể theo phiên bản/tier trong bài được trình bày theo tài liệu MongoDB tham khảo tại **14/11/2026**. MongoDB có thể thay đổi chính sách Free/Flex, Search Nodes, preview/GA và khả năng tạo index theo từng phiên bản. Trước khi triển khai, luôn đối chiếu trang tài liệu chính thức và **cấu hình cluster thực tế**; không dùng một con số phiên bản lịch sử như lời bảo đảm vĩnh viễn.

---

## 1. Vector Search là gì và yêu cầu những thành phần nào?

### 1.1. Từ văn bản đến vector

Giả sử ba sản phẩm:

~~~javascript
{
  _id: "P-101",
  title: "Áo khoác chống nước",
  category: "OUTDOOR",
  tenantId: "tenant-a",
  status: "PUBLISHED",
  embedding: [0.10, 0.60, 0.20, 0.30]
}

{
  _id: "P-102",
  title: "Ô đi mưa gấp gọn",
  category: "ACCESSORY",
  tenantId: "tenant-a",
  status: "PUBLISHED",
  embedding: [0.14, 0.57, 0.23, 0.28]
}
~~~

Trường `embedding` minh họa một vector gồm bốn giá trị số. Trong ứng dụng thật, embedding model thường sinh vector nhiều chiều hơn. Một câu hỏi như “đồ dùng khi trời mưa” được chuyển thành **query embedding** bởi cùng embedding model (hoặc mô hình tương thích), sau đó hệ thống tìm những vector gần query nhất theo metric được cấu hình.

### 1.2. Luồng tối thiểu

~~~text
Nội dung / document
        |
        v
Embedding model / inference service
        |
        v
Vector [v1, v2, ..., vn]
        |
        v
Lưu vector trong MongoDB document
        |
        v
Tạo MongoDB Vector Search index
        |
        v
Ứng dụng tạo query vector
        |
        v
Aggregation: $vectorSearch
        |
        v
Results + vectorSearchScore
~~~

### 1.3. Năm điều kiện tối thiểu

Để chạy vector search thật:

1. MongoDB deployment có **Vector Search support** cho phiên bản/tier đang chạy.
2. Search process hoặc dịch vụ chỉ mục tương ứng hoạt động.
3. Collection có dữ liệu embedding đúng kiểu, số chiều và path.
4. Vector Search index được tạo và **build xong**.
5. Query `$vectorSearch` hợp lệ, sử dụng tên index/path và query vector khớp.

Tạo vector array trong BSON không tự làm MongoDB tìm nearest neighbor được; cần index/service và stage thích hợp.

### 1.4. Các nhóm khái niệm hay bị nhầm

| Thành phần | Mục đích | Có thay Vector Search index không? |
|---|---|---|
| MongoDB document field `embedding` | Lưu vector | Không |
| B-tree index `{embedding:1}` | Chỉ mục field thông thường | Không |
| MongoDB text index | Full-text theo tokenizer của text index | Không |
| MongoDB Search index | Full-text/search features, một số cách vector legacy/hybrid | Không tự là dedicated `vectorSearch` index |
| MongoDB Vector Search index | Index các vector và filter fields | Có, đây là index cần cho `$vectorSearch` |
| `$search` | Search pipeline (full-text/hybrid và chức năng liên quan) | Khác stage `$vectorSearch` |
| `$vectorSearch` | ANN/ENN truy vấn vector | Cần môi trường, index và dữ liệu đúng |
| Embedding model | Sinh vector | Không tạo hoặc vận hành search index |
| `mongot` | Search service/process trong kiến trúc MongoDB Search | Cần triển khai/quản lý tương ứng tùy deployment |

---

## 2. Phân biệt MongoDB Atlas và MongoDB tự quản lý

### 2.1. Atlas Cloud

**MongoDB Atlas** là dịch vụ database managed trên cloud. Với cluster phù hợp, Atlas quản lý hạ tầng database và các thành phần Search/Vector Search theo kiến trúc deployment. Đây là hướng đơn giản để bắt đầu làm quen với `$vectorSearch`.

Một ứng dụng có thể kết nối bằng MongoDB connection string và chạy aggregation qua mongosh/driver sau khi index được tạo.

### 2.2. MongoDB Community/Enterprise tự quản lý

Đến 2026, không còn chính xác khi khẳng định “Vector Search **chỉ** chạy được trên Atlas cloud”. MongoDB đã công bố khả năng Search/Vector Search cho **self-managed**, với ngưỡng hỗ trợ ở MongoDB **8.2 trở lên** trong các deployment tương ứng và yêu cầu triển khai thành phần search.

Điểm khác biệt:

- Atlas cloud: Atlas quản lý nhiều phần của search infrastructure.
- Self-managed: đội vận hành cần triển khai, cấu hình và theo dõi `mongod`/`mongot` và hạ tầng hỗ trợ.
- Không phải mọi bản MongoDB Community cũ có thể nhận `$vectorSearch` sau khi chỉ cập nhật driver.

### 2.3. Local Atlas Deployment

**Atlas CLI local deployment** là lựa chọn học tập/phát triển cục bộ, thường thông qua container, giúp thử Search/Vector Search trên máy phát triển theo cách MongoDB hỗ trợ.

Đây **không** đồng nghĩa với việc cài một standalone `mongod` tùy phiên bản rồi có Vector Search. Local Atlas deployment có quy trình setup, image và search services riêng.

### 2.4. Ví dụ đúng/sai về điều kiện môi trường

| Môi trường | Có thể chạy `$vectorSearch`? | Điều kiện quan trọng |
|---|---|---|
| Atlas cloud với server/tier hỗ trợ | Có | Version, index, permissions, cluster capacity |
| Atlas Free/Flex được hỗ trợ | Có cho học/test với giới hạn | Quota, cách tạo index, tài nguyên, không mặc định production-ready |
| Atlas Dedicated | Có | Cấu hình cluster/search phù hợp |
| Atlas Dedicated + Search Nodes | Có | Search node support tại region/tier, sizing |
| Atlas CLI local đúng phiên bản | Có | Atlas CLI, Docker/image và deployment tương thích |
| Community self-managed 8.2+ được cấu hình đúng | Có | Hỗ trợ OS, `mongot`, kết nối và tài nguyên |
| Enterprise self-managed 8.2+ theo mô hình hỗ trợ | Có | Operator/deployment/edition requirement theo docs |
| Community self-managed 6.0/7.0/8.0 thông thường | Không thể mặc định có | Không đồng nhất với Atlas cluster cùng version |
| MongoDB standalone cũ chỉ có `mongod` | Không thể coi là sẵn sàng | Không có search process/index phù hợp |

**Kết luận:** Server version là **điều kiện cần theo nhánh**, không phải điều kiện đủ. Kiểm tra deployment type, search infrastructure và feature support.

---

## 3. Ma trận tương thích theo phiên bản MongoDB

### 3.1. ANN trên Atlas

**Approximate Nearest Neighbors (ANN)** qua `$vectorSearch` được MongoDB nêu cho Atlas:

- Nhánh **6.0**: từ **6.0.11** theo ngưỡng được công bố.
- Nhánh **7.0**: từ **7.0.2**.
- Các nhánh mới hơn: theo phiên bản được MongoDB công bố hỗ trợ.

Không đọc “6.0.11+” thành “mọi bản 7.0.0/7.0.1 chắc chắn được hỗ trợ”; các nhánh có **ngưỡng minor/patch riêng**.

### 3.2. ENN — Exact Nearest Neighbors

**Exact Nearest Neighbors (ENN)** có ngưỡng cao hơn ANN. Tài liệu MongoDB nêu mốc **6.0.16**, **7.0.10**, **7.3.2** hoặc phiên bản hỗ trợ sau đó theo nhánh.

Tại sao cần phân biệt?

- ANN dùng cấu trúc tìm kiếm xấp xỉ để cân bằng recall và latency.
- ENN duyệt vector theo cơ chế exhaustive/precise search, thường tốn nhiều chi phí hơn.
- Code thêm `exact:true` trên server cũ không tự bật khả năng ENN.
- Hành vi tương thích phải được xác minh ở cluster thực tế, không chỉ so major version.

### 3.3. `$unionWith` và `$vectorSearch`

Theo MongoDB Manual, từ **MongoDB 8.0** có hỗ trợ `$vectorSearch` trong `$unionWith` theo giới hạn stage tương ứng.

Với bản cũ hơn, một pipeline có `$unionWith` lồng `$vectorSearch` có thể không tương thích dù query vector đơn giản vẫn chạy.

### 3.4. `$facet` và `$lookup` subpipeline

`$vectorSearch` **không được đặt bên trong**:

- `$facet` pipeline.
- `$lookup` subpipeline.

Nhưng có thể đưa results từ `$vectorSearch` sang những stages downstream phù hợp, ví dụ `$lookup` sau khi vector results đã được tạo. Đây là sự khác biệt giữa **stage nằm bên trong subpipeline** và **stage khác xử lý kết quả của Vector Search**.

### 3.5. Tính năng mới không chỉ phụ thuộc binary version

Một số tính năng Search/Vector Search (ví dụ cấu hình hybrid ranking, automated embeddings, indexing options, view support, tuning/quantization) còn phụ thuộc:

- Search component/rollout.
- Cluster tier/search architecture.
- Preview/GA status.
- Region và edition.
- Index definition format.
- Tùy chọn API đang được docs hỗ trợ.

Không lấy mốc ANN tối thiểu để suy ra **mọi** tính năng Search mới đều có.

### 3.6. Bảng kiểm nhanh

| Tính năng | Atlas version được tài liệu nêu | Điều kiện khác |
|---|---|---|
| ANN với `$vectorSearch` | 6.0.11 trên nhánh 6.0; 7.0.2 trên nhánh 7.0; các bản mới hơn được hỗ trợ | Vector Search index và cluster tương thích |
| ENN (`exact:true`) | 6.0.16, 7.0.10, 7.3.2 và các nhánh/bản hỗ trợ | Index và query phù hợp, chi phí tính toán |
| `$vectorSearch` bên trong `$unionWith` | Bắt đầu từ 8.0 | Giới hạn aggregation hiện hành |
| `$vectorSearch` bên trong `$facet` | Không hỗ trợ theo giới hạn hiện hành | Cần thiết kế pipeline khác |
| `$vectorSearch` bên trong `$lookup` subpipeline | Không hỗ trợ theo giới hạn hiện hành | Có thể `$lookup` sau kết quả vector |
| Community self-managed Vector Search | 8.2+ trên môi trường/OS được hỗ trợ | Cài và vận hành search components |
| Enterprise self-managed Vector Search | 8.2+ theo yêu cầu triển khai được công bố | Kiểm tra Kubernetes Operator/edition support |
| Atlas CLI local Vector Search | Local deployment tương thích; tài liệu local nêu MongoDB 7.0.5+ | Atlas CLI, Docker, image hỗ trợ |
| Automated embedding | Phụ thuộc deployment/tính năng; một số self-managed capabilities còn preview | Xem trang tính năng riêng, không suy từ ANN gate |

Bảng mang tính hướng dẫn tại thời điểm biên soạn; **khả năng thực tế phải được kiểm chứng** trên deployment đích.

---

## 4. Tại sao "cùng MongoDB 7.0" nhưng Atlas và self-managed khác nhau?

### 4.1. Server version không chứa toàn bộ search architecture

Một Atlas cluster 7.0.x phù hợp có search service do Atlas triển khai. Một máy cài MongoDB Community 7.0.x thuần túy không tự có cùng hạ tầng.

~~~text
Atlas phù hợp:
  mongod
    + managed search process/index
    + Atlas control plane
    + quyền và cấu hình tương ứng
  -> $vectorSearch

Community 7.0 cài thông thường:
  mongod
  -> không nên kỳ vọng $vectorSearch có sẵn
~~~

### 4.2. `mongot` là gì?

MongoDB Search/Vector Search sử dụng search process/index infrastructure (thường được biết đến với `mongot`). Đây không phải một B-tree index nằm hoàn toàn trong engine `mongod` theo cùng cách với `createIndex({field:1})`.

Trên Atlas, search workload có thể dùng tài nguyên trên các node cùng nơi với database hoặc **Dedicated Search Nodes**. Trên self-managed 8.2+, đội vận hành phải triển khai những thành phần search theo tài liệu tương ứng.

### 4.3. Phải kiểm tra cả hai phần

~~~text
MongoDB version có đủ?
        |
        +-- Không -> upgrade/migrate
        |
        +-- Có
              |
              v
Deployment/tier hỗ trợ?
        |
        +-- Không -> chuyển deployment
        |
        +-- Có
              |
              v
Search service/index đã active?
        |
        +-- Không -> cấu hình/build/diagnose
        |
        +-- Có
              |
              v
Vector query phù hợp?
~~~

### 4.4. Những tình huống dễ nhầm

- Cài Atlas CLI không tự làm cluster cloud cũ hỗ trợ phiên bản mới.
- Nâng Java driver không nâng MongoDB Server hoặc search service.
- Tạo B-tree index lên vector array không thay thế vector index.
- Một MongoDB 8.2 server mới vẫn cần cách cài đặt Search/Vector Search đúng môi trường tự quản lý.
- Test trong Atlas Flex không bảo đảm production throughput.
- Test trong Atlas local không tự bảo đảm Atlas cloud cùng phiên bản/index options.

---

## 5. Atlas Free, Flex và Dedicated: chọn môi trường nào?

### 5.1. Free cluster

Free tier (trong nhiều tài liệu cũ gọi là `M0`) được dùng để học và thử một số khả năng Search/Vector Search trong giới hạn.

Một số giới hạn đang được tài liệu MongoDB nêu:

- Tối đa **3 Search/Vector indexes** kết hợp trên Free.
- Có thể có hạn chế về **cách tạo index bằng mongosh/driver**; khi programmatic create thất bại trên Free, kiểm tra phương án tạo trong **Atlas UI** theo tài liệu tier.
- CPU/RAM/dung lượng và lưu lượng nhỏ; không đặt production SLO trên một lab Free.

### 5.2. Flex cluster

Flex là lựa chọn chi phí thấp cho development/POC:

- Theo tài liệu giới hạn index liên quan, tối đa **10 Search/Vector indexes** trên Flex.
- Có resource contention và latency biến động, không tương đương dedicated Search Nodes.
- Atlas tự quản lý version nâng cấp theo chính sách Flex; người dùng không nhất thiết chọn được release cadence.

### 5.3. Dedicated cluster

Các tier Dedicated từ `M10` trở lên cho phép cấu hình năng lực phù hợp hơn. M10/M20 có thể dùng để prototyping, nhưng RAM/index size và shared resource contention vẫn quan trọng.

Đối với production, nên đo workload để chọn cluster tier và số lượng/tier Search Nodes thích hợp.

### 5.4. Dedicated Search Nodes

Với search workloads lớn, tách Search Nodes khỏi database nodes giúp:

- Giảm tranh chấp RAM/CPU giữa `mongod` và search service.
- Scale search và database tương đối độc lập.
- Có tài nguyên riêng cho index và query.
- Quan sát latency, memory và search saturation rõ hơn.

Tuy vậy, **Dedicated Search Nodes không có sẵn ở mọi region/provider/tier**. Theo tài liệu triển khai Vector Search, tính sẵn có khác nhau giữa AWS, Azure và Google Cloud. Cần kiểm tra cloud region của cluster thật.

### 5.5. Bảng lựa chọn

| Mục tiêu | Gợi ý môi trường | Lưu ý |
|---|---|---|
| Học cú pháp, 10–100 documents | Atlas Free hoặc Atlas CLI local tương thích | Kiểm tra quyền, index quota |
| Demo nhỏ cho nhóm | Flex hoặc Dedicated nhỏ | Không suy ra production SLA |
| POC cần tích hợp backend | Dedicated tier nhỏ/khá hoặc local nếu phù hợp | Đo indexing latency và query p95 |
| Production latency ổn định | Dedicated và cân nhắc Search Nodes riêng | Capacity planning, alerts, region support |
| Dữ liệu buộc on-prem/self-managed | Community/Enterprise 8.2+ với search infrastructure | Hỗ trợ OS, vận hành `mongot`, backup/upgrades |
| CI cần end-to-end Vector Search | Atlas test cluster hoặc Atlas local được hỗ trợ | Không dùng standalone MongoDB cũ rồi kỳ vọng stage chạy |

### 5.6. Đừng đồng nhất "Free được phép dùng" với "đủ cho production"

Tính năng được hỗ trợ trên Free không có nghĩa:

- Không có quota.
- Latency luôn thấp.
- Được quyền tạo index bằng mọi API.
- Không có ảnh hưởng khi index rebuild.
- Có Search Nodes chuyên dụng.
- Có backup, HA và SLO như Dedicated.

---

## 6. Atlas Local và các trường hợp chạy trên máy phát triển

### 6.1. Mô hình Atlas CLI local

MongoDB có tài liệu tạo **local Atlas deployment** bằng Atlas CLI, dùng Docker hoặc runtime hỗ trợ để triển khai single-node replica set và các khả năng Search.

Ví dụ lệnh tương tác:

~~~bash
atlas local setup
~~~

Sau khi deployment được tạo thành công và driver kết nối được, tạo Search/Vector Search index bằng công cụ mà local deployment hỗ trợ, ví dụ Atlas CLI local search index commands hoặc mongosh theo compatibility.

### 6.2. Điều kiện được tài liệu nêu

Tài liệu Atlas CLI local nêu:

- Cần phiên bản **Atlas CLI tương thích** (lệnh hiện hành dùng namespace `atlas local`).
- Phải cài Docker hoặc container runtime được hỗ trợ.
- Với Vector Search local, tài liệu nêu **MongoDB 7.0.5 hoặc mới hơn** trong local Atlas deployment để có khả năng phù hợp.
- Các local deployment cũ không tự upgrade hoàn toàn; có thể phải thay images/deployments theo hướng dẫn sau khi bảo toàn dữ liệu quan trọng.
- Tài nguyên CPU/RAM/disk máy cá nhân là giới hạn thực tế.

### 6.3. Windows và macOS: phân biệt hai trường hợp

Có hai tuyên bố khác nhau:

1. Atlas CLI local deployment dùng container được tài liệu hướng dẫn trên các hệ điều hành phát triển, bao gồm Windows/macOS theo điều kiện container runtime.
2. MongoDB Community self-managed Search/Vector Search 8.2+ được tài liệu sản phẩm mô tả hỗ trợ **Linux**, có Docker/container, và **không hỗ trợ cài native Search/Vector Search trên Windows/macOS** theo thông tin đó.

Không lấy khả năng chạy **Atlas local qua Docker trên Windows** để suy rằng **Community native `mongot` trên Windows** được hỗ trợ như nhau.

### 6.4. Cẩn thận với Docker MongoDB thường

Ví dụ:

~~~bash
docker run --name ordinary-mongo -p 27017:27017 mongo:7
~~~

chỉ khởi tạo một image MongoDB thông thường, **không** chứng minh MongoDB Vector Search đã được bật. Nó cũng có thể là standalone `mongod` mà không có search service. Vì vậy test `db.collection.aggregate([{$vectorSearch:...}])` trên image này có thể lỗi.

### 6.5. Local là nơi học, không phải replica production

Single-node local deployment không có multi-region HA, autoscaling, backup policy và Search Node isolation như production Atlas. Dữ liệu và indexes demo phải có quy trình di chuyển/khởi tạo lại khi promote sang Atlas cloud hoặc self-managed production.

---

## 7. Community/Enterprise self-managed từ MongoDB 8.2

### 7.1. Bước ngoặt về sản phẩm

MongoDB công bố preview của Search/Vector Search trên Community/Enterprise tự quản lý năm 2025, rồi công bố phát hành rộng hơn trong năm 2026. Do đó các bài viết cũ nói “chỉ Atlas” có thể đã lỗi thời.

### 7.2. Điều kiện không chỉ là binary `mongod`

Một triển khai self-managed phải có:

- MongoDB Server bản phù hợp, tối thiểu nhánh hỗ trợ như 8.2+.
- Search/Vector Search process `mongot`, cấu hình và kết nối phù hợp.
- Hệ điều hành/kiến trúc được tài liệu hỗ trợ.
- Cấu hình bảo mật, TLS, users/roles.
- Năng lực RAM/CPU/disk cho vectors/index.
- Cơ chế vận hành index builds, backups và upgrades.
- Network giữa các thành phần.
- Monitoring cho search service và database.

### 7.3. Community Edition

Tài liệu MongoDB Community Edition hiện mô tả Search/Vector Search cho Community 8.2+ trên Linux distributions được hỗ trợ, gồm Docker/container và Kubernetes scenarios. Không suy ra cài native Windows/macOS có cùng tính năng.

### 7.4. Enterprise

Tài liệu MongoDB Manual nêu support `$vectorSearch` ở các MongoDB Enterprise deployments 8.2+ **với Kubernetes Operator** trong điều kiện tương ứng. Các mô hình Enterprise Advanced tự quản lý cần tham khảo tài liệu deployment và `mongot` compatibility của đúng bản/edition.

Không khẳng định mọi Enterprise standalone 8.2 chạy bằng một command đều có sẵn search process.

### 7.5. Trade-off self-managed

Lợi ích:

- Kiểm soát vị trí dữ liệu/on-prem.
- Tùy chỉnh hạ tầng.
- Tích hợp chính sách bảo mật nội bộ.
- Tránh phụ thuộc hoàn toàn vào Atlas cloud cho khả năng search.

Đánh đổi:

- Đội vận hành chịu trách nhiệm version compatibility và search process.
- Phải sizing RAM/index/query workload.
- Tự xử lý upgrades, failover, monitoring và bảo trì.
- Tính năng preview/GA hoặc một số advanced options có thể khác Atlas.
- Kết quả benchmark local không tự khớp production.

---

## 8. Điều kiện về index: Search index khác B-tree index

### 8.1. Không dùng `createIndex({embedding:1})`

Câu lệnh:

~~~javascript
db.products.createIndex({
  embedding: 1
});
~~~

tạo ordinary index, **không** tạo vector-search ANN index.

### 8.2. Index definition cho `vectorSearch`

Ví dụ Vector Search index dành cho embeddings 4 chiều:

~~~javascript
{
  name: "product_vector_index",
  type: "vectorSearch",
  definition: {
    fields: [
      {
        type: "vector",
        path: "embedding",
        numDimensions: 4,
        similarity: "cosine"
      },
      {
        type: "filter",
        path: "tenantId"
      },
      {
        type: "filter",
        path: "status"
      },
      {
        type: "filter",
        path: "category"
      }
    ]
  }
}
~~~

- `type:"vectorSearch"` xác định loại Search index.
- Field `type:"vector"` xác định vector path và số chiều.
- `numDimensions` phải phù hợp embedding model.
- `similarity` chọn metric trong các metric được tài liệu hỗ trợ.
- Field `type:"filter"` cho phép pre-filter trên metadata phù hợp.
- Index name sẽ được tham chiếu bởi `$vectorSearch.index`.

### 8.3. Tạo index bằng mongosh khi tier/phiên bản cho phép

~~~javascript
use vector_compat_lab

db.products.createSearchIndex({
  name: "product_vector_index",
  type: "vectorSearch",
  definition: {
    fields: [
      {
        type: "vector",
        path: "embedding",
        numDimensions: 4,
        similarity: "cosine"
      },
      {
        type: "filter",
        path: "tenantId"
      },
      {
        type: "filter",
        path: "status"
      },
      {
        type: "filter",
        path: "category"
      }
    ]
  }
});
~~~

**Quan trọng:** Ví dụ dùng API tạo Search index mà môi trường phải hỗ trợ. Nếu Free cluster có hạn chế programmatic create, hãy tạo bằng **Atlas UI** theo tài liệu tier thay vì coi `Command not found` là bằng chứng mọi Vector Search đều không dùng được.

### 8.4. Trạng thái index

Lệnh tạo index không đồng nghĩa index đã xong. Index có thể ở trạng thái đang build/sync. Query ngay sau đó có thể chưa trả đầy đủ hoặc báo chưa sẵn sàng.

Dùng Atlas UI / Search index list hoặc các API tương ứng để xác nhận index status trước integration test.

### 8.5. Đổi index definition

Khi sửa fields, dimensions, similarity hoặc quantization:

- Search index có thể phải rebuild.
- Có thời gian index chưa cập nhật xong.
- Tài nguyên search tăng trong quá trình build.
- Cần kiểm tra backward compatibility với ứng dụng đang query.
- Production nên có rollout/rollback strategy, có thể dùng index name mới trước cutover.

Không sửa `numDimensions` trong index khi data/query vẫn là vector chiều cũ.

---

## 9. Điều kiện về embedding dimensions và dữ liệu

### 9.1. `numDimensions` phải khớp

Giả sử embedding model trả vector gồm 768 số. Index phải dùng số chiều phù hợp, ví dụ:

~~~javascript
{
  type: "vector",
  path: "embedding",
  numDimensions: 768,
  similarity: "cosine"
}
~~~

Nếu query vector có 384 chiều trong khi index yêu cầu 768, query không hợp lệ hoặc không hoạt động như mong đợi.

### 9.2. Giới hạn chiều

Tài liệu MongoDB Vector Search nêu giới hạn vector tối đa **8192 dimensions** cho các kiểu/cấu hình được hỗ trợ. Một số dạng quantized vectors có yêu cầu bổ sung như bội số của 8 khi dùng binary quantization.

Không chỉ kiểm tra `length <=8192`; còn phải kiểm tra loại representation, dimension chính xác, model và option quantization.

### 9.3. Vector dữ liệu mẫu

~~~javascript
use vector_compat_lab

db.products.insertMany([
  {
    _id: "P-101",
    tenantId: "tenant-a",
    title: "Áo khoác chống mưa",
    category: "OUTDOOR",
    status: "PUBLISHED",
    embedding: [0.10, 0.60, 0.20, 0.30]
  },
  {
    _id: "P-102",
    tenantId: "tenant-a",
    title: "Ô đi mưa gấp gọn",
    category: "ACCESSORY",
    status: "PUBLISHED",
    embedding: [0.14, 0.57, 0.23, 0.28]
  },
  {
    _id: "P-103",
    tenantId: "tenant-b",
    title: "Áo mưa trẻ em",
    category: "OUTDOOR",
    status: "PUBLISHED",
    embedding: [0.12, 0.59, 0.19, 0.31]
  },
  {
    _id: "P-104",
    tenantId: "tenant-a",
    title: "Sản phẩm chưa công khai",
    category: "OUTDOOR",
    status: "DRAFT",
    embedding: [0.13, 0.56, 0.25, 0.29]
  }
]);
~~~

Các vectors bốn chiều ở đây **chỉ dùng để thử khả năng chạy và cú pháp**. Chúng không được tạo từ embedding model thật, nên không dùng kết quả để đánh giá chất lượng semantic search.

### 9.4. Vectors phải cùng embedding space

Không trộn embeddings của model A (384 chiều) và model B (768 chiều). Ngay cả khi hai models tình cờ cùng số chiều, chúng không nhất thiết nằm trong cùng semantic space.

Một query vector được tạo bởi model khác có thể trả ranking vô nghĩa dù kích thước khớp.

### 9.5. Khi nâng cấp embedding model

Cần kế hoạch:

1. Chọn model/version mới.
2. Xây trường embedding mới, ví dụ `embeddingV2`.
3. Re-embed data theo pipeline có khả năng retry.
4. Tạo index mới tương ứng.
5. Query kiểm tra recall/latency.
6. Chuyển traffic dần sang index mới.
7. Dọn index/field cũ sau khi ổn định.

Không thay model query trước khi đã re-index dữ liệu phù hợp.

### 9.6. Kiểu dữ liệu

Vector có thể được lưu theo array số hoặc dạng BSON BinData được hỗ trợ trong những cấu hình nhất định. Khi dùng quantization, có thêm ràng buộc precision/encoding. Đừng tự chuyển float array sang binary blob tùy ý rồi kỳ vọng vector index hiểu.

---

## 10. ANN và ENN: điều kiện truy vấn khác nhau

### 10.1. ANN — Approximate Nearest Neighbors

ANN dùng cấu trúc tìm kiếm xấp xỉ để giảm thời gian so với exhaustive scan. Query thường khai báo:

~~~javascript
{
  $vectorSearch: {
    index: "product_vector_index",
    path: "embedding",
    queryVector: [0.11, 0.58, 0.22, 0.29],
    numCandidates: 100,
    limit: 5
  }
}
~~~

`numCandidates` kiểm soát số ứng viên thuật toán xem xét. Tăng lên có thể tăng recall nhưng cũng tăng latency/chi phí.

### 10.2. Quy tắc chọn `numCandidates`

MongoDB nêu hướng dẫn khởi đầu thường dùng `numCandidates` ít nhất khoảng **20 lần `limit`** cho ANN để cải thiện recall, nhưng phải benchmark theo phân bố dữ liệu và mức lọc. Ví dụ `limit:5` và `numCandidates:100` là lựa chọn thử nghiệm.

Đây không phải công thức bảo đảm recall tối thiểu trong mọi dataset.

### 10.3. ENN — Exact Nearest Neighbors

ENN dùng `exact:true`:

~~~javascript
{
  $vectorSearch: {
    index: "product_vector_index",
    path: "embedding",
    queryVector: [0.11, 0.58, 0.22, 0.29],
    exact: true,
    limit: 5
  }
}
~~~

Không đặt `numCandidates` như parameter bắt buộc cho ENN. Kiểm tra ngưỡng phiên bản ENN trước khi sử dụng, vì cụm có ANN nhưng chưa chắc ENN.

### 10.4. Khi dùng loại nào?

| Tình huống | ANN | ENN |
|---|---|---|
| Dataset lớn, latency thấp quan trọng | Thường phù hợp | Có thể rất tốn |
| Cần benchmark recall | Query đang tối ưu | Làm tham chiếu ground truth |
| Dataset ít sau pre-filter chặt | Có thể dùng | Có thể phù hợp để lấy top-k chính xác |
| Cluster version chỉ hỗ trợ ANN | Có | Không |
| Yêu cầu exact nearest vector ranking | Không bảo đảm tuyệt đối | Phù hợp nếu được hỗ trợ và đủ tài nguyên |

### 10.5. Không nhầm "exact vector" với sự thật nghiệp vụ

ENN chỉ tính exact nearest theo metric trên vectors được index. Nếu embedding model không biểu diễn đúng ý nghĩa, ENN vẫn trả kết quả không phù hợp với người dùng. Exact nearest không bảo đảm factual correctness của RAG.

---

## 11. Ví dụ truy vấn end-to-end trên Atlas phù hợp

### 11.1. Đảm bảo các bước trước

- Cluster hỗ trợ `$vectorSearch`.
- Có collection `vector_compat_lab.products`.
- Index `product_vector_index` đã build.
- Index `embedding` có 4 chiều.
- User có quyền đọc collection.
- Query vector bốn chiều hợp lệ.

### 11.2. Query có pre-filter

~~~javascript
const queryEmbedding = [0.11, 0.58, 0.22, 0.29];

db.products.aggregate([
  {
    $vectorSearch: {
      index: "product_vector_index",
      path: "embedding",
      queryVector: queryEmbedding,
      numCandidates: 100,
      limit: 5,
      filter: {
        tenantId: "tenant-a",
        status: "PUBLISHED"
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      category: 1,
      tenantId: 1,
      status: 1,
      score: {
        $meta: "vectorSearchScore"
      }
    }
  }
]);
~~~

### 11.3. Vai trò của pre-filter

`filter` hạn chế candidate space để tránh đưa documents không đúng tenant/trạng thái vào ranking. Điều này đặc biệt quan trọng với ứng dụng đa tenant.

**Không** lấy tenantId do client tự gửi để xác định quyền truy cập. Trong production, tenant/permission filters phải được xây từ authenticated context.

### 11.4. Điều kiện để field có thể pre-filter

Các field muốn lọc trong `$vectorSearch.filter` cần được index với `type:"filter"` trong vector search index. Những kiểu dữ liệu và toán tử filter được hỗ trợ **không đồng nhất** với mọi MongoDB aggregation/MQL operator.

Ví dụ nếu index chỉ có `embedding` mà không có `tenantId`, query filter theo `tenantId` có thể lỗi hoặc không hoạt động theo cách mong đợi.

### 11.5. Không giả định `filter` hỗ trợ toàn bộ MQL

Tài liệu nêu các nhóm field filter như boolean, date, numeric, ObjectId, string, UUID và arrays tương ứng; danh sách operators được hỗ trợ có giới hạn. Không đưa geo predicates, regex phức tạp hoặc arbitrary aggregation expressions vào `filter` mà chưa đối chiếu trang hỗ trợ.

### 11.6. `$project` ở cuối

`$project` giúp chỉ trả fields cần thiết và score; tránh gửi toàn bộ embedding vector lớn tới frontend nếu không cần.

### 11.7. Score là gì?

`{$meta:"vectorSearchScore"}` trả score do search stage tính. Score phục vụ **xếp hạng tương đối** trong cùng query/index, không tự là xác suất “sản phẩm đúng 94%”.

Nếu thay metric/model hoặc dùng ANN khác ENN, score distribution có thể khác; đừng đặt hard-coded threshold mà không đánh giá.

---

## 12. Tạo index theo Atlas UI và bằng API

### 12.1. Tại sao nên hiểu cả hai cách?

Có những môi trường/tier cho phép tạo index bằng Atlas UI nhưng hạn chế command programmatic; ngược lại CI/CD production thường cần index-as-code.

### 12.2. Atlas UI

Quy trình tổng quát:

1. Chọn đúng Atlas project và cluster.
2. Mở chức năng Search/Vector Search indexes.
3. Chọn database và collection.
4. Tạo index loại `Vector Search`.
5. Khai báo vector path, dimensions, similarity và filter fields.
6. Chờ trạng thái index active/ready.
7. Chạy query thử trên UI/mongosh.

Tên màn hình có thể thay đổi theo UI; bám vào docs mới khi thao tác.

### 12.3. Programmatic index creation

Trên deployment hỗ trợ:

~~~javascript
db.products.createSearchIndex({
  name: "product_vector_index",
  type: "vectorSearch",
  definition: {
    fields: [
      {
        type: "vector",
        path: "embedding",
        numDimensions: 4,
        similarity: "cosine"
      },
      {
        type: "filter",
        path: "tenantId"
      },
      {
        type: "filter",
        path: "status"
      }
    ]
  }
});
~~~

Câu lệnh minh họa cách tạo; khi chạy lại cùng tên index hoặc khi index quota đã đầy, cần xử lý trạng thái thay vì tạo lặp.

### 12.4. Kiểm tra danh sách index

Trên các server/driver hỗ trợ, có những helper methods để liệt kê search indexes, ví dụ:

~~~javascript
db.products.getSearchIndexes();
~~~

Kết quả có metadata/index status tùy phiên bản. Nếu helper không có, sử dụng Atlas UI hoặc API tương đương; không tự coi helper missing là toàn bộ vector feature unsupported.

### 12.5. Đừng dùng `getIndexes()` như công cụ duy nhất

`getIndexes()` thường được dùng kiểm tra các indexes thông thường của collection. MongoDB Search/Vector Search indexes được quản lý qua các API Search index riêng; đừng chỉ nhìn danh sách B-tree indexes rồi kết luận vector index không tồn tại.

---

## 13. Quyền truy cập và cấu hình mạng

### 13.1. Các lớp quyền khác nhau

- **Atlas project permissions**: quyền quản lý Search index qua UI/API.
- **Database user permissions**: quyền đọc dữ liệu và chạy queries.
- **Index management privileges**: quyền tạo/chỉnh/xóa Search indexes trong môi trường tương ứng.
- **Network allowlist/private endpoints**: client được phép kết nối hay không.
- **TLS/credentials**: xác thực kết nối.

Một user đọc được collection không nhất thiết có quyền tạo index.

### 13.2. Quyền tạo Search index

Tài liệu Atlas nêu các vai trò liên quan như `Project Search Index Editor` hoặc vai trò đủ cao để quản lý/quan sát Search indexes. Quyền database tương ứng và phương thức quản lý index qua UI/driver cũng cần xác định.

Trong production, ưu tiên least privilege:

- CI/CD hoặc admin service quản lý index.
- Runtime ứng dụng chỉ cần query/đọc cần thiết.
- Không cung cấp Project Owner cho service chỉ thực hiện retrieval.

### 13.3. Lỗi network khác lỗi Vector Search

Nếu client không kết nối được Atlas do IP allowlist, DNS, TLS, user/password hoặc private endpoint, `$vectorSearch` chưa có cơ hội chạy. Đừng sửa index definition để khắc phục lỗi không kết nối MongoDB.

### 13.4. Embedding provider cũng có điều kiện riêng

Nếu ứng dụng dùng API ngoài để tạo embeddings:

- Key và quota của provider.
- Mô hình và số chiều.
- Data residency/chính sách PII.
- Latency và timeout.
- Rate limiting.
- Quyền gửi dữ liệu sang bên thứ ba.

MongoDB Vector Search **không tự** bảo đảm provider embeddings luôn khả dụng.

---

## 14. Search index là eventual-consistent

### 14.1. Index build không ngay tức thì

Khi ứng dụng insert/update documents, Search process phải nhận và index thay đổi. Các Search indexes được cập nhật **bất đồng bộ**; có thể có indexing lag.

~~~text
T0: insert document MongoDB
T1: commit/ack thành công
T2: Search index nhận thay đổi
T3: Vector Search query bắt đầu nhìn thấy document
~~~

Tại T1, tài liệu đã ghi thành công nhưng query vector có thể chưa trả document mới.

### 14.2. Không hứa read-your-writes bằng vector search

Một transaction MongoDB commit với `w:"majority"` không chứng minh index Search đã cập nhật đồng bộ. Vector Search không phải công cụ kiểm tra ngay tức khắc một write có tồn tại như primary read thông thường.

### 14.3. Với nghiệp vụ yêu cầu tính đúng tức thời

Ví dụ kiểm tra sản phẩm còn hàng trước khi bán:

1. `$vectorSearch` gợi ý ứng viên dựa trên indexed metadata.
2. Ứng dụng có thể đọc lại trạng thái authoritative từ MongoDB.
3. Khi tạo đơn, dùng **atomic conditional update/transaction** để kiểm tra tồn kho và quyền.
4. Không dùng vector index như lock/reservation.

### 14.4. Lúc index rebuild

Index definition mới cần build/rebuild. Cần tránh roll out query phụ thuộc field mới trước khi index sẵn sàng. Theo tài liệu, một số quá trình rebuild vẫn phục vụ query theo index definition cũ trong khi index mới được dựng, nhưng không có nghĩa tính năng mới đã active.

### 14.5. RAG và truy xuất tài liệu mới

Nếu ứng dụng RAG cần hiển thị tài liệu ngay sau upload, có thể:

- Đợi pipeline embedding/indexing hoàn tất theo trạng thái riêng.
- Cho client xem tài liệu mới qua đường MongoDB read thông thường.
- Có “processing” UI state.
- Không khẳng định “upload xong là retrieval query chắc đã tìm thấy”.

---

## 15. Hạn chế aggregation theo phiên bản và stage

### 15.1. `$vectorSearch` ở đầu pipeline

Query thông dụng:

~~~javascript
db.products.aggregate([
  {
    $vectorSearch: {
      index: "product_vector_index",
      path: "embedding",
      queryVector: [0.11, 0.58, 0.22, 0.29],
      numCandidates: 100,
      limit: 5
    }
  },
  {
    $project: {
      title: 1,
      score: {
        $meta: "vectorSearchScore"
      }
    }
  }
]);
~~~

### 15.2. Vì sao không `$match` trước?

Không viết:

~~~javascript
db.products.aggregate([
  { $match: { tenantId: "tenant-a" } },
  {
    $vectorSearch: {
      index: "product_vector_index",
      path: "embedding",
      queryVector: [0.11, 0.58, 0.22, 0.29],
      numCandidates: 100,
      limit: 5
    }
  }
]);
~~~

`$vectorSearch` phải là stage đầu trong pipeline nơi nó xuất hiện. Đưa predicate phù hợp vào `filter` đã được index; các business filters không hỗ trợ pre-filter thì có thể xử lý sau nhưng phải hiểu khả năng giảm số kết quả.

### 15.3. Pre-filter khác post-filter

Nếu lấy 5 candidates rồi mới `$match:{tenantId:"tenant-a"}`, có thể còn 0–2 docs dù tenant-a còn nhiều docs tương tự khác ngoài top 5 toàn cluster.

Nếu mục tiêu là “top 5 **trong tenant-a**”, phải dùng **pre-filter tenant** bên trong `$vectorSearch` và vector index có filter field phù hợp.

### 15.4. `$facet`/`$lookup`/`$unionWith`

- Không lồng `$vectorSearch` vào `$facet` stage.
- Không lồng `$vectorSearch` vào `$lookup` subpipeline.
- Có thể đặt `$lookup` **sau** `$vectorSearch` để enrich kết quả theo pipeline semantics.
- Từ MongoDB 8.0, có quy tắc cho `$vectorSearch` trong `$unionWith`.

Nếu nhu cầu hybrid search đòi phối hợp text/vector, cần chọn pipeline và feature/version tương thích, không chỉ copy ví dụ của MongoDB 8.x sang 6.0.

### 15.5. Views và time-series collections

MongoDB Search/Vector Search có những giới hạn theo loại collection/view và phiên bản. Tài liệu Search feature compatibility nêu không hỗ trợ time-series collections; từ một số bản mới như 8.3, query Search/Vector Search trên time-series có thể trả lỗi rõ thay vì kết quả trống.

Không chuyển một pipeline đang chạy trên regular collection sang time-series/view và cho rằng stage hỗ trợ giống nhau. Kiểm tra tài liệu của **đúng version**.

---

## 16. Vector Search index và filter index fields

### 16.1. Index nhiều loại field

~~~javascript
{
  fields: [
    {
      type: "vector",
      path: "embedding",
      numDimensions: 768,
      similarity: "cosine"
    },
    {
      type: "filter",
      path: "tenantId"
    },
    {
      type: "filter",
      path: "status"
    },
    {
      type: "filter",
      path: "price"
    }
  ]
}
~~~

Ví dụ này cho phép thử pre-filter theo tenant, status và price trong phạm vi operators/field types MongoDB hỗ trợ.

### 16.2. Khả năng filter không tùy ý

Một số types được hỗ trợ gồm string, numeric, boolean, date, ObjectId, UUID và arrays thuộc nhóm phù hợp. Đừng suy từ `$match` có thể viết `$regex`, `$geoWithin` hoặc một `$expr` phức tạp để chắc chắn `$vectorSearch.filter` cũng hiểu.

### 16.3. Boolean combinations

Có thể dùng các operators được hỗ trợ như `$and`, `$or`, `$in`, `$eq` và range comparisons trong phạm vi tài liệu. Ví dụ:

~~~javascript
filter: {
  $and: [
    { tenantId: "tenant-a" },
    { status: "PUBLISHED" },
    { category: { $in: ["OUTDOOR", "ACCESSORY"] } }
  ]
}
~~~

Nếu field không được index `filter`, cần bổ sung index definition rồi đợi build xong.

### 16.4. Security quan trọng

Một vector index chứa embeddings của nhiều tenants. Nếu ứng dụng không pre-filter theo trusted tenant context và trả kết quả từ mọi tenant, dữ liệu có thể bị lộ qua similarity results.

Đừng cho client gửi arbitrary filter BSON để tự quyết định tenant; xây filter từ user auth và whitelist fields.

### 16.5. Index nhiều fields tăng chi phí

Mỗi Search index tiêu thụ RAM/CPU/disk và tăng chi phí đồng bộ khi documents thay đổi. Không tạo một index cho mọi tổ hợp filters; thiết kế theo workloads chính và đo.

---

## 17. Java Sync Driver: chạy `$vectorSearch` khi server hỗ trợ

### 17.1. Driver và server là hai điều kiện riêng

Java Sync Driver cung cấp MongoDB aggregation API. Một driver mới không làm cluster cũ hỗ trợ stage mới; một cluster mới cũng có thể cần driver version/codec hỗ trợ tạo index và xử lý BSON phù hợp.

Thông thường, có thể xây raw aggregation stage bằng `Document` ở những driver hỗ trợ aggregation dù helper builder chuyên biệt khác nhau theo version.

### 17.2. Ví dụ Java query

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.List;

public class AtlasVectorSearchExample {

    public static void search(MongoClient client) {
        MongoDatabase database =
            client.getDatabase("vector_compat_lab");

        MongoCollection<Document> products =
            database.getCollection("products");

        List<Double> queryVector =
            List.of(0.11, 0.58, 0.22, 0.29);

        Document filter =
            new Document("tenantId", "tenant-a")
                .append("status", "PUBLISHED");

        Document vectorSpec =
            new Document(
                "index",
                "product_vector_index"
            )
                .append("path", "embedding")
                .append("queryVector", queryVector)
                .append("numCandidates", 100)
                .append("limit", 5)
                .append("filter", filter);

        Document vectorStage =
            new Document("$vectorSearch", vectorSpec);

        Document projection =
            new Document(
                "$project",
                new Document("title", 1)
                    .append("category", 1)
                    .append(
                        "score",
                        new Document(
                            "$meta",
                            "vectorSearchScore"
                        )
                    )
            );

        products.aggregate(
            List.of(vectorStage, projection)
        ).forEach(System.out::println);
    }
}
~~~

### 17.3. Điều kiện chạy thành công

- `MongoClient` đã kết nối/auth thành công.
- Vector Search được hỗ trợ trong deployment.
- Index name chính xác.
- Index path và dimensions khớp.
- Query vector là numeric values được codec serialize phù hợp.
- `tenantId` và `status` được index làm filter fields.
- Index build hoàn tất.
- Server cho phép stage `$vectorSearch`.

### 17.4. Java model dimension

Trong ứng dụng thật, không hard-code một vector bốn chiều. Có thể thiết kế:

~~~java
public final class EmbeddingRequest {
    private final String modelId;
    private final List<Double> vector;

    public EmbeddingRequest(
            String modelId,
            List<Double> vector) {

        this.modelId = modelId;
        this.vector = vector;
    }

    public int dimension() {
        return vector.size();
    }
}
~~~

Service cần xác thực model ID, dimension, giá trị số hữu hạn và index tương ứng trước khi query.

### 17.5. Java 5.x requirement với tính năng cao cấp

Một số hướng dẫn MongoDB Vector Search dùng ví dụ driver Java 5.x khi triển khai các API mới hoặc automated embeddings. Đừng lấy một version table của tính năng **automated embedding** để kết luận mọi raw aggregation `$vectorSearch` có cùng tối thiểu driver; kiểm tra driver API cụ thể.

### 17.6. Không tạo client mới cho mỗi query

Quản lý `MongoClient` lâu dài trong application để dùng pooling. Đặt timeout/retry policy phù hợp, không in URI/password trong logs.

---

## 18. Chẩn đoán lỗi theo môi trường và phiên bản

### 18.1. `Unrecognized pipeline stage name: '$vectorSearch'`

Khả năng:

- Server/deployment chưa hỗ trợ stage.
- Đang kết nối nhầm cluster/host.
- Self-managed chỉ có `mongod` mà thiếu search infrastructure.
- Server version thuộc nhánh cũ.

Hướng kiểm tra:

1. In `db.version()` hoặc `buildInfo` từ cluster thực.
2. Xem cluster trong Atlas UI để xác nhận deployment/tier.
3. Đối chiếu compatibility matrix.
4. Kiểm tra index/search service.
5. Chạy một query tối thiểu trên đúng collection.

Không “nâng driver là xong” khi server không có feature.

### 18.2. `Command not found` khi tạo index

Khả năng:

- Cluster/version không hỗ trợ createSearchIndex command/helper.
- Tier Free có giới hạn programmatic creation.
- Driver/mongosh quá cũ cho helper method.
- Kết nối nhầm môi trường.

Hướng xử lý: dùng Atlas UI theo khả năng tier; đối chiếu yêu cầu version cho programmatic Search index management; kiểm tra quyền.

### 18.3. Index không tồn tại hoặc tên sai

Query:

~~~javascript
{
  $vectorSearch: {
    index: "product_vector_index",
    path: "embedding",
    queryVector: [0.11, 0.58, 0.22, 0.29],
    numCandidates: 100,
    limit: 5
  }
}
~~~

Nếu `product_vector_index` không đúng tên hoặc chưa sẵn sàng, query có thể báo lỗi hoặc không ra kết quả. Kiểm tra đúng database/collection/index.

### 18.4. Không có kết quả dù collection có documents

Kiểm tra:

- Index đang build?
- Vector field đúng path và kiểu?
- Embeddings có được index?
- Dimensions đúng?
- Query model và stored model có tương thích?
- Pre-filter có loại hết documents?
- Chọn nhầm tenant/status?
- ANN recall/numCandidates quá thấp?
- Search index đang lag so với writes?
- Có collection/view restrictions?

### 18.5. Filter field chưa index

Nếu dùng:

~~~javascript
filter: {
  tenantId: "tenant-a"
}
~~~

nhưng index chỉ định nghĩa vector field, cần bổ sung:

~~~javascript
{
  type: "filter",
  path: "tenantId"
}
~~~

đúng phiên bản index definition, đợi rebuild/sync.

### 18.6. Dimension mismatch

Index 768 nhưng query vector 1536 chiều không hợp lệ. Không sửa bằng cách cắt 768 số đầu tùy tiện; cần dùng embedding model và dimension đúng.

### 18.7. Query timeout / error 489

MongoDB Vector Search có cơ chế bảo vệ overload, có thể reject query khi demand vượt search capacity. Cần:

- Kiểm tra search node saturation/queue/rejection metrics.
- Giảm `numCandidates` nếu benchmark cho phép.
- Giới hạn concurrency/retry với backoff.
- Điều chỉnh tier/Search Nodes.
- Tối ưu pre-filter/index/payload.
- Không retry vô hạn cùng tải khiến hệ thống tệ hơn.

### 18.8. Query quá chậm nhưng không lỗi

Khả năng:

- ANN numCandidates quá cao.
- ENN trên dataset quá lớn.
- Filter selectivity/representation chưa tốt.
- Search memory thiếu.
- Không có Search Nodes riêng.
- Index rất lớn, quantization chưa phù hợp.
- Downstream projection, network hoặc aggregation stages bổ sung nặng.

Benchmark `p50/p95/p99`, recall và index memory thay vì chỉ nhìn một lần query.

---

## 19. Quy trình xác minh môi trường từng bước

Một quy trình dễ dùng khi nhận một cluster mới:

~~~text
1. Có thể kết nối tới MongoDB?
          |
          v
2. Xác nhận deployment type:
   Atlas cloud / Atlas local / self-managed
          |
          v
3. Kiểm tra MongoDB Server version
   và feature compatibility
          |
          v
4. Kiểm tra tier, region, search service
          |
          v
5. Kiểm tra quyền Search index
          |
          v
6. Tạo/quan sát Vector Search index
          |
          v
7. Đợi index READY / ACTIVE
          |
          v
8. Chạy $vectorSearch tối thiểu
          |
          v
9. Thử pre-filter và score
          |
          v
10. Đo recall/latency/resource
          |
          v
11. Xác nhận production readiness
~~~

### 19.1. Kiểm tra version trên mongosh

~~~javascript
db.version();

db.adminCommand({
  buildInfo: 1
});
~~~

Không chia sẻ output có dữ liệu nhạy cảm của môi trường khi báo lỗi ngoài nhóm được phép.

### 19.2. Kiểm tra phiên bản không thay được deployment inspection

`db.version()` có thể cho biết MongoDB Server, nhưng không tiết lộ đầy đủ:

- Tier Free/Flex/Dedicated.
- Search Node availability.
- Preview flags/feature rollout.
- Index quota còn lại.
- Runtime resource pressure.
- Search service readiness.

Cần kiểm tra Atlas UI/management API hoặc self-managed config.

### 19.3. Kiểm tra collection/index

~~~javascript
use vector_compat_lab

db.products.countDocuments();

db.products.getSearchIndexes();
~~~

`getSearchIndexes()` chỉ dùng khi môi trường/công cụ hỗ trợ helper. Nếu không có, xem Atlas UI hoặc phương thức admin được tài liệu hỗ trợ.

### 19.4. Truy vấn smoke test

~~~javascript
db.products.aggregate([
  {
    $vectorSearch: {
      index: "product_vector_index",
      path: "embedding",
      queryVector: [0.11, 0.58, 0.22, 0.29],
      numCandidates: 100,
      limit: 5
    }
  },
  {
    $project: {
      title: 1,
      score: {
        $meta: "vectorSearchScore"
      }
    }
  }
]);
~~~

Nếu smoke test pass, mới thêm tenant filters, semantic evaluation và throughput test.

---

## 20. Ma trận áp dụng theo các môi trường ứng dụng

### 20.1. Máy cá nhân mới cài MongoDB Community 7.0

- Có thể lưu array embedding như BSON.
- Không nên kỳ vọng `$vectorSearch` chạy chỉ vì data là vector.
- Dùng Atlas cloud/local tương thích hoặc self-managed 8.2+ với search components theo tài liệu.

### 20.2. Atlas Free cluster chạy phiên bản hỗ trợ

- Có thể thử tính năng trong giới hạn tier.
- Index quota nhỏ.
- Nếu helper tạo index lỗi, sử dụng Atlas UI theo hỗ trợ của Free.
- Không dùng benchmark Free để kết luận production performance.

### 20.3. Atlas Flex

- Phù hợp development/POC theo docs.
- Kiểm tra tổng số Search/Vector indexes và quota.
- Version được Atlas quản lý.
- Có thể gặp contention/latency variation.

### 20.4. Atlas Dedicated trên AWS/Azure/Google Cloud

- Xác nhận Search Nodes hỗ trợ ở region và tier cụ thể.
- Chọn dữ liệu/lưu lượng và latency SLO.
- Benchmark trên production-like dataset.
- Kế hoạch index rebuild và scaling.
- Điều chỉnh search tier riêng khi có Dedicated Search Nodes.

### 20.5. Self-managed 8.2+ trên Linux

- Cấu hình mongod/mongot.
- Kiểm tra OS, container/Kubernetes support.
- Test Search index management và query.
- Đặt monitoring, resource limits, backup/upgrades.
- Không giả định các features preview/Atlas-only có sẵn.

### 20.6. Java backend trên một cluster đúng

- Kiểm tra MongoDB Java driver có hỗ trợ API được sử dụng.
- Dùng raw BSON aggregation hoặc builder phù hợp.
- Quản lý connection pooling.
- Hạn chế query concurrency.
- Có fallback khi search index đang build/unavailable.

---

## 21. So sánh `$vectorSearch` với legacy `knnBeta`

### 21.1. Vì sao dễ gặp tài liệu cũ?

Một số bài viết đời đầu của Atlas Vector Search dùng `$search` với operator `knnBeta`. Các hướng dẫn mới sử dụng `$vectorSearch` và index loại `vectorSearch`.

### 21.2. Không sao chép một nửa của hai hệ cú pháp

Ví dụ dạng legacy có thể dùng:

~~~javascript
{
  $search: {
    index: "legacy_index_name",
    knnBeta: {
      vector: [0.11, 0.58, 0.22, 0.29],
      path: "embedding",
      k: 5
    }
  }
}
~~~

Ví dụ này chỉ để **nhận diện tài liệu cũ**, không phải lời khuyên triển khai mới. Sự hỗ trợ, ngừng hỗ trợ và lộ trình chuyển đổi phụ thuộc phiên bản.

### 21.3. API hiện hành

~~~javascript
{
  $vectorSearch: {
    index: "product_vector_index",
    path: "embedding",
    queryVector: [0.11, 0.58, 0.22, 0.29],
    numCandidates: 100,
    limit: 5
  }
}
~~~

### 21.4. Khi nâng cấp hệ thống cũ

Cần kiểm tra:

- Legacy Search index definition.
- `knnBeta` syntax/behavior.
- `$vectorSearch` stage availability.
- Dedicated vectorSearch index creation.
- Similarity metric.
- Embedding dimensions.
- Pre-filter fields/operators.
- Result scores và ranking.
- Query latency/recall.
- Feature flags và rollback.

Không chỉ thay tên `knnBeta` thành `$vectorSearch`.

---

## 22. Automated Embeddings và BYO embeddings

### 22.1. BYO (Bring Your Own) embeddings

Ứng dụng tự tạo vector bằng mô hình ngoài:

~~~text
Document
   |
Embedding provider/model
   |
Embedding array
   |
MongoDB store/index
   |
Query embedding từ cùng model
   |
$vectorSearch
~~~

Ưu điểm: dễ kiểm soát model, version, chunking, dữ liệu được gửi sang đâu. Đánh đổi: tự quản lý embedding jobs, retries, model upgrades và index compatibility.

### 22.2. Automated Embeddings

MongoDB có hướng phát triển **Automated Embedding** cho một số môi trường/tính năng, giúp tạo embeddings từ text khi ingest/query trong khả năng được hỗ trợ.

Không được mặc định tính năng này có trên mọi Free/Flex, self-managed, region hoặc MongoDB version chỉ vì cơ bản `$vectorSearch` chạy được.

### 22.3. Preview khác GA

Một số deployment/tính năng Automated Embedding được tài liệu đánh dấu **Preview**. Những chức năng preview có thể:

- Thay đổi API/availability.
- Có giới hạn region và data processing.
- Không có bảo đảm production tương đương GA.
- Có điều kiện riêng về model/inference/chi phí.

Trước khi dùng dữ liệu nhạy cảm, kiểm tra data residency, scope inference, chính sách retention, quota và trang cảnh báo Preview hiện hành.

### 22.4. Tác động lên thiết kế index

BYO vector thường dùng:

~~~javascript
{
  type: "vector",
  path: "embedding",
  numDimensions: 768,
  similarity: "cosine"
}
~~~

Automated embedding có thể dùng định nghĩa index và dạng query khác, ví dụ field mapping tự sinh hoặc cung cấp text query thay `queryVector` tùy docs. **Không dùng cú pháp của một workflow cho workflow kia**.

---

## 23. RAM, index size, quantization và Search Nodes

### 23.1. Vectors tiêu tốn bộ nhớ

Giả sử có 1.000.000 documents với embedding 1.536 chiều kiểu float32:

\[
1\,000\,000 \times 1\,536 \times 4\text{ bytes}
=6\,144\,000\,000\text{ bytes}
\]

Xấp xỉ **6,14 GB** vector raw data (decimal GB), **chưa bao gồm** ANN graph/index metadata, runtime, JVM và dữ liệu khác.

Đây chỉ là công thức ước lượng kích thước raw float data; không phải RAM sizing đủ cho Search index.

### 23.2. Search index cần RAM và disk

Tài liệu MongoDB Vector Search nêu search index và `mongot` cần memory; với full precision thường yêu cầu tài nguyên lớn hơn dạng quantized. Khi automatic quantization dùng full fidelity vectors để rescoring/ENN, có thể cần disk tương ứng.

### 23.3. Quantization

Quantization có thể giảm memory footprint của vectors, đổi lại ảnh hưởng quality/latency và yêu cầu version/encoding riêng. Không bật binary/scalar quantization chỉ vì thấy RAM giảm; cần đo recall và kiểm tra hỗ trợ trên deployment.

### 23.4. Co-located vs dedicated search

| Mô hình | Lợi ích | Đánh đổi |
|---|---|---|
| Search cùng database node | Đơn giản, phù hợp demo/POC | Tranh CPU/RAM với `mongod` |
| Dedicated Search Nodes | Tách workload, scale search riêng | Chi phí và region/tier requirements |
| Self-managed co-located | Kiểm soát máy, ít node | Vận hành và tài nguyên chung |
| Self-managed separate hosts | Tách resource theo thiết kế | Network và vận hành phức tạp hơn |

### 23.5. Capacity planning

Xác định:

- Số documents/vector fields.
- Dimension và representation.
- Tốc độ ingest/update.
- Query requests/second.
- `numCandidates`, `limit`, filter selectivity.
- RAM cho index/JVM.
- Disk cho index build/quantized full fidelity.
- Search node CPU và network.
- Index rebuild time.
- p95/p99 latency và recall target.

Không dùng cấu hình M10 chỉ vì “tính năng có thể bật” nếu workload vượt tài nguyên.

---

## 24. ANN recall, latency và ENN làm mốc tham chiếu

### 24.1. Recall là gì?

Giả sử ENN cho top 10 document IDs chính xác theo metric, ANN cũng trả top 10 nhưng chỉ trùng 9 IDs. Một phép đo phổ biến:

\[
\text{Recall@10} =
\frac{\#\text{documents trùng với ENN top 10}}{10}
\]

Trong ví dụ là 0,9 (90%).

### 24.2. Trade-off

Tăng `numCandidates` có thể cải thiện recall nhưng tăng tài nguyên/latency. Giảm nó có thể giảm latency nhưng tăng rủi ro bỏ lỡ những neighbors tốt.

### 24.3. ENN benchmark cần đúng version

Trước khi dùng ENN làm ground truth, kiểm tra phiên bản hỗ trợ `exact:true`. Nếu cluster chỉ hỗ trợ ANN, có thể dùng bộ tính distance offline được kiểm soát cho dataset nhỏ để benchmark, nhưng phải dùng cùng metric và vector preprocessing.

### 24.4. Không chỉ nhìn query time một lần

Đo:

- p50/p95/p99.
- Recall@K.
- Candidate counts.
- Filter selectivity.
- Vector index memory.
- Search node CPU.
- Query rejection.
- Indexing lag.
- Cost/query.

### 24.5. Khi version upgrade

Tìm kiếm xấp xỉ có thể thay đổi ranking một số trường hợp do search engine và index rebuild. Integration tests nên kiểm tra **quality bands/recall** thay vì yêu cầu mọi ID phải giống 100% trong mọi ANN response giữa versions.

---

## 25. Tính sẵn sàng và consistency trong ứng dụng RAG

### 25.1. RAG pipeline

~~~text
User question
    |
    v
Embedding of question
    |
    v
$vectorSearch
    |
    v
Retrieve authorized relevant chunks
    |
    v
Optional reranking
    |
    v
LLM receives context
    |
    v
Generated answer with references
~~~

### 25.2. Vector Search được bật chưa đủ để RAG tốt

Cần:

- Chunking policy.
- Embedding model phù hợp ngôn ngữ/domain.
- Metadata/permission filters.
- Source document and citation IDs.
- Versioning và re-embedding.
- Retrieval evaluation.
- Freshness/indexing latency.
- Prompt/context safety.
- Query cost/latency.
- Sensitive data policy.

### 25.3. Permissions trước khi gửi context tới LLM

Nếu Vector Search trả text chunks nội bộ, quyền xem tài liệu phải được áp dụng **trước khi cung cấp cho model**. Không rely vào LLM để “tự không đọc” dữ liệu mà retrieval đã đưa vào context.

### 25.4. Khi search unavailable

Ứng dụng có thể:

- Trả thông báo retrieval tạm thời chưa khả dụng.
- Dùng keyword search fallback nếu đã được thiết kế và kiểm tra quyền.
- Trả từ cache có TTL/chính sách phù hợp.
- Không tự tưởng tượng kết quả hoặc khẳng định đã tra cứu nguồn khi search lỗi.

### 25.5. Khi tài liệu mới chưa index

UI có thể hiển thị trạng thái `PROCESSING` và chỉ đánh dấu `SEARCHABLE` khi pipeline embedding và index readiness đã được kiểm tra theo cơ chế ứng dụng. Đừng coi insert acknowledgment đồng nghĩa vector index đã cập nhật.

---

## 26. Production rollout: từ POC đến triển khai

### Giai đoạn 1 — POC

- Chọn Atlas Free/Flex/local tương thích.
- Dùng small sample và index thử.
- Chạy `$vectorSearch` ANN.
- Thử filter tenant/status.
- Kiểm tra dimensions và model.
- Đo latency cơ bản.
- Ghi lại exact server/tier/driver versions.

### Giai đoạn 2 — Staging

- Dữ liệu gần production scale.
- Tạo index cùng model/dimensions.
- Benchmark ANN/ENN khi support.
- Thử high selectivity và low selectivity filters.
- Test index rebuild.
- Test lỗi search unavailable.
- Quan sát disk/RAM/search queue.

### Giai đoạn 3 — Production

- Dedicated tier/Search Nodes theo nhu cầu và region support.
- Quyền riêng cho runtime và index admin.
- Backup/source embeddings để rebuild.
- Monitoring p95/p99, indexing lag, resource and errors.
- Canary queries và rollback.
- Capacity kế hoạch cho lượng vectors mới.
- Index migration khi nâng model.

### 26.1. Không chuyển từ Free thẳng sang production theo cảm tính

Giới hạn tài nguyên Free/Flex khiến latency, index build, search node architecture và autoscaling khác Dedicated. Cần benchmark staging tương tự production.

### 26.2. Rollback search indexes

Nếu đổi index definition hoặc model:

1. Tạo index mới tên khác khi có thể.
2. Cho ingest đồng thời embeddings cũ/mới hoặc backfill.
3. Kiểm tra index ready.
4. Canary traffic.
5. So sánh quality/latency.
6. Chuyển traffic dần.
7. Giữ đường rollback trong một giai đoạn.
8. Xóa index cũ theo quota/cost policy.

### 26.3. Quản lý index quota

Free chỉ có vài indexes; không thể vô hạn tạo index mới mỗi lần deploy. Khi quản lý rollout trên tier nhỏ, có thể cần dọn indexes demo hoặc nâng tier có chủ đích. Tránh xóa index đang phục vụ ứng dụng thật mà chưa có replacement.

---

## 27. Kiểm tra phiên bản và capability trong ứng dụng

### 27.1. Không chỉ if version string

Code kiểu:

~~~javascript
if (db.version() >= "7.0.2") {
  // use vectorSearch
}
~~~

có hai vấn đề:

- So sánh strings không phản ánh numeric semver.
- Version không nói hết deployment type/tier/search service.

### 27.2. Capability probe

Một integration test có thể:

1. Xác nhận kết nối.
2. Kiểm tra version/topology.
3. Kiểm tra search index tồn tại và ready.
4. Chạy query nhỏ hợp lệ.
5. Ghi nhận loại lỗi.
6. Đánh dấu ứng dụng search-ready khi probe thành công.

Đây là cách kiểm tra **tính năng thật**, không phải chỉ suy từ version.

### 27.3. Không chạy probe quá dày

Một truy vấn vector probe cũng tiêu thụ search resources. Health checks có thể dùng mức cache/interval phù hợp, không phát search query 10 lần/giây trên mọi application instance.

### 27.4. Khác nhau giữa readiness và liveness

- **Liveness:** tiến trình ứng dụng còn chạy.
- **Readiness:** ứng dụng đủ dependencies để phục vụ chức năng vector search.
- **Degraded mode:** API còn chạy nhưng vector retrieval tạm ngừng.

Nếu vector search là tính năng phụ, search outage không nhất thiết khiến mọi API của service bị đánh dấu liveness failed và restart storm.

---

## 28. Bài toán kiểm soát phiên bản driver, mongosh, Atlas CLI

### 28.1. Bộ ba phiên bản

~~~text
MongoDB Server/search service version
        +
MongoDB Driver/mongosh version
        +
Atlas CLI/management tooling version
~~~

Mỗi phần có capability khác nhau.

### 28.2. Driver

Driver có thể chạy aggregation raw BSON nếu hỗ trợ API cần thiết, nhưng một số helper methods/index management APIs chỉ xuất hiện ở các version nhất định. Kiểm tra chính xác Java Sync Driver docs cho phiên bản dự án.

### 28.3. Mongosh

`db.collection.createSearchIndex()` và `getSearchIndexes()` phụ thuộc helper availability; mongosh cũ có thể thiếu method ngay khi cluster có Search support. Có thể dùng Atlas UI/management API để quản lý nếu phù hợp.

### 28.4. Atlas CLI

Một số lệnh lịch sử như `atlas deployments` đã thay đổi/deprecated; tài liệu local hiện hướng tới namespace `atlas local`. Khi tham khảo một blog cũ, kiểm tra Atlas CLI version và syntax thay vì copy nguyên.

### 28.5. Pin versions và test

Trong CI/staging:

- Ghi chính xác server version/FCV khi cần.
- Pin phiên bản Java driver và BOM phù hợp.
- Pin container images cho local integration.
- Pin embedding model ID.
- Lưu index definition trong version control.
- Chạy compatibility tests trước major/minor upgrades.

### 28.6. FCV và cluster upgrades

Feature Compatibility Version (FCV) có thể quyết định một số tính năng sau khi nâng MongoDB binaries. Không mặc định nâng binary là mọi feature gate lập tức sẵn. Với Atlas Auto Upgrades, cách quản lý FCV có thể khác self-managed; kiểm tra tài liệu version management.

---

## 29. Ma trận chẩn đoán nhanh

| Hiện tượng | Khả năng chính | Hướng xác minh |
|---|---|---|
| Kết nối Atlas bị từ chối | IP allowlist/TLS/auth | Test `ping` và Atlas network/user settings |
| Stage `$vectorSearch` không nhận | Version/deployment unsupported | `db.version()` + Atlas/self-managed compatibility |
| Tạo index qua mongosh `Command not found` | Tier Free hạn chế/API cũ/server | Atlas UI + version/index management docs |
| Query báo index không tồn tại | Tên sai/chưa tạo/nhầm collection | Search index listing/Atlas UI |
| Query không có kết quả | Index chưa ready/dimension/filter | Kiểm tra index status, path, filter fields |
| Query thiếu kết quả tenant | Filter sau `limit` | Đưa tenant vào pre-filter được index |
| Query lỗi dimension | Model/index/query vector không khớp | Kiểm tra số chiều và model version |
| `exact:true` lỗi | ENN chưa hỗ trợ ở phiên bản đó | Kiểm tra ENN minimum patch version |
| `$vectorSearch` trong `$facet` lỗi | Stage placement không hỗ trợ | Thiết kế pipeline khác |
| `$unionWith` lỗi trên bản cũ | Feature gate phiên bản | Kiểm tra từ 8.0 và docs nhánh |
| Query chậm trên Free/Flex | Resource contention/tier limit | Benchmark Dedicated/search capacity |
| Error 489/load shedding | Search quá tải | Giảm concurrency/tune/scale |
| Document vừa insert không được tìm thấy | Indexing eventual consistency | Kiểm tra index lag và readiness |
| Query trả tài liệu tenant khác | Thiếu trusted pre-filter | Security fix + test isolation |
| Local Docker `mongo:7` không chạy vector | Không có Search infrastructure | Dùng Atlas local đúng setup/self-managed 8.2+ |
| Self-managed Windows không hoạt động | Platform support mismatch | Kiểm tra Linux/container/Atlas CLI local option |
| Deploy index mới nhưng query cũ vẫn dùng schema trước | Rebuild chưa xong | Kiểm tra active index definition/status |

---

## 30. Các lỗi hiểu sai cần tránh

**Sai lầm 1:** “Atlas Vector Search chỉ có trên Atlas cloud mãi mãi.”

→ Đã có support tự quản lý ở những phiên bản/môi trường mới. Cần kiểm tra điều kiện chính xác.

**Sai lầm 2:** “MongoDB 6.0 bất kỳ đều chạy `$vectorSearch`.”

→ Ngưỡng ANN được công bố cho nhánh 6.0 bắt đầu từ 6.0.11, không phải mọi 6.0.x.

**Sai lầm 3:** “MongoDB 7.0.0 chắc chắn chạy như 7.0.10.”

→ ANN/ENN và các APIs có patch-version gates.

**Sai lầm 4:** “Cài Java driver mới sẽ bật tính năng trên server cũ.”

→ Driver và server có chức năng khác nhau.

**Sai lầm 5:** “MongoDB Community 7.0 self-managed giống Atlas 7.0.”

→ Atlas có managed Search infrastructure; Community self-managed support mới có ngưỡng/thiết lập riêng.

**Sai lầm 6:** “Docker MongoDB bình thường tương đương Atlas CLI local.”

→ Cần local deployment có Search/Vector Search service đúng chuẩn.

**Sai lầm 7:** “Free tier không bao giờ dùng Vector Search.”

→ Có thể thử trên tier được hỗ trợ, nhưng hạn chế quota/API/tài nguyên.

**Sai lầm 8:** “Free/Flex có Vector Search thì production-ready.”

→ Resource contention, latency, scaling và index quota khác Dedicated.

**Sai lầm 9:** “Tạo B-tree index trên array là đủ.”

→ Phải tạo MongoDB Vector Search index.

**Sai lầm 10:** “Index create trả success nghĩa là query đã có đủ dữ liệu.”

→ Index build/sync bất đồng bộ.

**Sai lầm 11:** “Đổi số chiều của index là sửa được query vector.”

→ Model, stored embeddings và query embeddings phải tương thích.

**Sai lầm 12:** “Chỉ cần cùng số chiều là hai embedding models tương thích.”

→ Không đủ; semantic space có thể khác.

**Sai lầm 13:** “ENN có trên mọi phiên bản có ANN.”

→ ENN có ngưỡng hỗ trợ riêng.

**Sai lầm 14:** “`numCandidates:100` đảm bảo recall 100%.”

→ ANN là xấp xỉ; cần benchmark với ENN/ground truth.

**Sai lầm 15:** “`$vectorSearch` có thể đặt sau `$match` bất kỳ.”

→ Stage placement có quy tắc; dùng `filter` phù hợp.

**Sai lầm 16:** “Vector Search pre-filter hiểu mọi MQL predicate.”

→ Chỉ hỗ trợ nhóm field/operator nhất định, cần khai báo filter type.

**Sai lầm 17:** “Sau vectorSearch limit 5 rồi match tenant sẽ cho top 5 tenant.”

→ Có thể loại bớt và mất top-k hợp lệ; phải pre-filter.

**Sai lầm 18:** “MongoDB write concern majority đồng nghĩa Search index đã nhận dữ liệu.”

→ Search index eventual-consistent.

**Sai lầm 19:** “VectorSearchScore là xác suất sự thật.”

→ Là điểm ranking, cần đánh giá theo model/index.

**Sai lầm 20:** “Chạy được trên Atlas local là đủ xác nhận performance production.”

→ Cần test trên hạ tầng/tier tương tự production.

**Sai lầm 21:** “Tính năng preview có thể dùng production mà không kiểm tra.”

→ Preview có giới hạn và yêu cầu riêng.

**Sai lầm 22:** “Mọi region đều có Search Nodes.”

→ Availability phụ thuộc region/provider và tier.

**Sai lầm 23:** “Search index được quản lý bằng `getIndexes()` giống mọi B-tree.”

→ Dùng Search index management API riêng.

**Sai lầm 24:** “Không được phép tạo index thì query vector chắc cũng không được.”

→ Quyền/tier cho create index và quyền chạy query là hai vấn đề khác nhau.

**Sai lầm 25:** “Có vector search rồi thì dữ liệu được bảo mật tự động.”

→ Phải kiểm tra authenticated metadata filters và không đưa dữ liệu trái phép vào RAG context.

---

## 31. Checklist trước khi triển khai theo môi trường

### 31.1. Kiểm tra deployment

- [ ] Atlas cloud, Atlas local hay self-managed?
- [ ] Server version và branch patch đủ cho ANN/ENN?
- [ ] Search service/process thực sự hoạt động?
- [ ] Cluster tier có hỗ trợ feature và đủ quota?
- [ ] Nếu Dedicated Search Nodes, region/tier có sẵn không?
- [ ] Nếu self-managed, OS và mô hình `mongot` đúng yêu cầu?
- [ ] Nếu local, Atlas CLI/Docker/image versions tương thích?
- [ ] Có chính sách upgrade/rollback?

### 31.2. Kiểm tra index

- [ ] Collection và vector path tồn tại?
- [ ] Embeddings numeric hợp lệ?
- [ ] `numDimensions` khớp model?
- [ ] Similarity metric được chọn có chủ đích?
- [ ] Filter fields được khai báo kiểu `filter`?
- [ ] Search index đã ready?
- [ ] Không vượt Free/Flex index quota?
- [ ] Có monitoring index size/build status?

### 31.3. Kiểm tra query

- [ ] `$vectorSearch` đặt đúng vị trí?
- [ ] Tên index/path đúng?
- [ ] Query vector cùng model và số chiều?
- [ ] ANN có `numCandidates` phù hợp, ENN có `exact:true` và version hỗ trợ?
- [ ] `limit` hợp lệ và không vượt policy?
- [ ] Tenant/visibility filters từ nguồn đáng tin?
- [ ] `$project` chỉ trả fields cần?
- [ ] Không lồng stage trong `$facet`/`$lookup` subpipeline?
- [ ] Đã thử query không filter, rồi mới thêm filter?

### 31.4. Kiểm tra production

- [ ] SLO query p95/p99 và target recall?
- [ ] Benchmark dữ liệu thật với kích thước index dự kiến?
- [ ] Capacity memory/disk/search nodes?
- [ ] Retry/backoff khi overload?
- [ ] Indexing lag được đo?
- [ ] Model/embedding/index version được quản lý?
- [ ] Backup data đủ để re-embed/rebuild?
- [ ] Feature fallback khi search unavailable?
- [ ] Logs không lộ credentials/embeddings nhạy cảm?
- [ ] Không dùng search result như business invariant tức thời?

---

## 32. Bài tập thực hành

### Bài tập 1 — Đánh giá môi trường

Cho năm môi trường:

1. Atlas 6.0.10.
2. Atlas 6.0.11.
3. Atlas 7.0.2.
4. Community 7.0 chạy Docker `mongo:7` thông thường.
5. Community 8.2+ Linux với Search infrastructure được cấu hình.

Phân loại khả năng ANN `$vectorSearch`; giải thích những điều kiện cần xác minh thêm thay vì chỉ so version.

### Bài tập 2 — ANN và ENN

Một Atlas cluster v7.0.5 chạy ANN được. Có được mặc định dùng `exact:true` không? Tra ngưỡng ENN, đưa ra hướng nâng cấp hoặc dùng ANN/benchmark thay thế.

### Bài tập 3 — Atlas Free index

Tạo một Vector Search index trên Free qua UI. Sau đó thử programmatic create (nếu muốn) và ghi lại behavior, quota. Vì sao không suy luận “Command not found = Vector Search không hỗ trợ”?

### Bài tập 4 — Atlas Flex

Thiết kế POC có ba vector indexes và hai text Search indexes trên Flex. Kiểm tra tổng quota hiện hành, chi phí và khả năng scale.

### Bài tập 5 — Atlas local

Lập môi trường Atlas CLI local theo docs, xác nhận Docker/image versions, tạo collection và vector index rồi chạy query. So sánh với Docker image MongoDB standalone thông thường.

### Bài tập 6 — Self-managed 8.2

Thiết kế checklist để chạy MongoDB Community 8.2+ với Search/Vector Search trên Linux. Nêu vai trò `mongot`, memory, TLS, monitoring và failover.

### Bài tập 7 — Vector index definition

Tạo index `product_vector_index` với `embedding` 4 chiều và filter fields `tenantId`/`status`. Giải thích từng field.

### Bài tập 8 — Truy vấn ANN

Viết `$vectorSearch` với query vector bốn chiều, `numCandidates:100` và `limit:5`, projection title/score.

### Bài tập 9 — Truy vấn ENN

Đổi query sang `exact:true` trên môi trường hỗ trợ. So sánh kết quả và latency trên nhiều vector values.

### Bài tập 10 — Dimension mismatch

Đặt index 4 chiều nhưng query 3 chiều. Ghi lỗi mongosh và giải thích vì sao không nên pad/cắt vector tùy ý.

### Bài tập 11 — Filter không được index

Thử filter theo `tenantId` khi index chỉ có vector field. Thêm `type:"filter"`, chờ rebuild và thử lại.

### Bài tập 12 — Pre-filter vs post-filter

So sánh:

- `$vectorSearch.filter:{tenantId:"tenant-a"}`.
- `$vectorSearch.limit:5` rồi `$match:{tenantId:"tenant-a"}`.

Giải thích khi nào cách sau bỏ sót kết quả tenant hợp lệ.

### Bài tập 13 — Index build readiness

Insert documents, tạo index rồi query ngay. Quan sát trạng thái build và thời điểm kết quả bắt đầu đầy đủ; không giả định dữ liệu có ngay sau command.

### Bài tập 14 — Java Sync Driver

Viết Java code dùng `Document` cho `$vectorSearch`. Tách query vector, trusted tenant filter và projection.

### Bài tập 15 — Search Nodes

Tính toán sơ bộ raw vector size của 500.000 embeddings, 1536 chiều float32. Giải thích vì sao không thể suy RAM cuối cùng chỉ từ phép tính đó.

### Bài tập 16 — ANN recall

Dùng một dataset đủ nhỏ để chạy ENN và ANN. Đo recall@10 và p95 latency theo `numCandidates`.

### Bài tập 17 — Version upgrade

Ứng dụng dùng Atlas 7.0.2 muốn dùng ENN và `$unionWith` chứa Vector Search. Lập kế hoạch upgrade dựa trên compatibility gates và integration tests.

### Bài tập 18 — Hybrid retrieval

Phác thảo một pipeline kết hợp semantic và keyword retrieval; kiểm tra stage support của đúng MongoDB version. Không nhầm legacy `knnBeta` với dedicated vector index.

### Bài tập 19 — Model migration

Đang dùng embeddings 768 chiều, chuyển sang model 1024 chiều. Thiết kế dual-index rollout mà không phá query hiện tại.

### Bài tập 20 — Troubleshooting

Một query trả 0 results trong khi data tồn tại. Viết thứ tự kiểm tra: server/tier → index ready → path/dimensions → model → filter → ANN candidates → indexing lag.

### Bài tập 21 — Tenant isolation

Viết integration test bảo đảm user tenant-a không thể lấy kết quả tenant-b dù vector tenant-b giống query hơn.

### Bài tập 22 — Production SLO

Đề xuất metrics: p50/p95/p99, errors, query rejection, index memory, build latency, indexing lag, ANN recall, cost/query và alerts.

### Bài tập 23 — Automated Embedding

So sánh BYO embeddings với Automated Embedding: ai quản lý model, data residency, API availability, preview status và version gate?

### Bài tập 24 — QA theo môi trường

Thiết kế test matrix gồm Atlas Free, Flex, Dedicated, Atlas Local và self-managed 8.2. Nêu những tests nào bắt buộc chạy trên deployment thật thay vì unit tests/mock.

---

## 33. Câu hỏi ôn tập

1. Atlas Vector Search và MongoDB Vector Search khác nhau về cách gọi trong tài liệu mới như thế nào?
2. Vì sao lưu vector array không đủ để tìm nearest neighbors?
3. Vì sao ordinary MongoDB index không thay vector index?
4. `mongot` có vai trò gì?
5. Atlas cloud khác self-managed ở trách nhiệm vận hành search process ra sao?
6. `$vectorSearch` ANN có những ngưỡng patch-version nào trên Atlas?
7. Vì sao Atlas 7.0.0 và 7.0.10 không thể coi như nhau?
8. ENN có cùng ngưỡng hỗ trợ với ANN không?
9. `exact:true` dùng để làm gì?
10. `numCandidates` có ý nghĩa gì?
11. Tại sao tăng numCandidates có thể tăng latency?
12. `$vectorSearch` có hỗ trợ bên trong `$facet` không?
13. Có thể lồng `$vectorSearch` trong `$lookup` subpipeline không?
14. Từ phiên bản nào có hướng hỗ trợ `$vectorSearch` trong `$unionWith`?
15. Community self-managed 7.0 có mặc định hỗ trợ Vector Search không?
16. Community self-managed Vector Search 8.2+ cần kiểm tra OS/search infrastructure gì?
17. Vì sao Windows chạy Atlas Local qua Docker khác Community Search native Windows?
18. Atlas CLI local cần gì?
19. Vì sao Docker `mongo:7` thông thường chưa đủ?
20. Free/Flex có giới hạn gì về Search index count?
21. Free tier có thể có hạn chế gì khi tạo index qua mongosh?
22. Dedicated Search Nodes khác co-located search process thế nào?
23. Tại sao Search Nodes không có ở mọi cloud region?
24. Index definition cần những trường nào?
25. `numDimensions` phải khớp với gì?
26. Số chiều tối đa được MongoDB Vector Search tài liệu nêu là bao nhiêu?
27. Similarity metric quyết định điều gì?
28. Stored embedding và query embedding có cần cùng model không?
29. Vì sao cùng dimension nhưng khác model vẫn có thể sai?
30. Field `type:"filter"` phục vụ mục tiêu gì?
31. Vì sao post-filter sau limit có thể bỏ sót top K tenant?
32. `$vectorSearch` phải nằm đâu trong pipeline?
33. Làm thế nào để lấy `vectorSearchScore`?
34. Điểm score có phải xác suất câu trả lời đúng không?
35. Search index có cập nhật ngay sau MongoDB insert không?
36. `w:"majority"` có bảo đảm tài liệu xuất hiện ngay trong Vector Search không?
37. Tại sao khi index rebuild phải chờ ready trước khi rollout?
38. Vì sao server version không đủ để đánh giá search readiness?
39. Driver mới có thể tự nâng server capability không?
40. Khi nào chọn ANN, khi nào ENN?
41. Lỗi "Command not found" có luôn nghĩa Vector Search không hỗ trợ không?
42. Khi gặp dimension mismatch phải khắc phục thế nào?
43. Vì sao nên giảm concurrency/tăng Search Nodes khi query overload?
44. Automated Embedding khác BYO embedding thế nào?
45. Tính năng Preview cần kiểm tra thêm điều kiện gì?
46. Vì sao không đưa documents ngoài tenant vào RAG context?
47. Cần bảo vệ model/version/index như thế nào khi migration?
48. Vì sao Free POC không đủ chứng minh p99 production?
49. Khi nào cần fallback nếu vector search unavailable?
50. Những tiêu chí nào phải có trong compatibility test matrix?

---

## 34. Tổng kết

**Điều kiện sử dụng Atlas/MongoDB Vector Search không thể được xác định chỉ bằng câu hỏi “MongoDB version bao nhiêu?”.** Phải kiểm tra **deployment type, version branch, tier, search process, index state, data/embedding schema, driver/API, quyền và tài nguyên**.

Nhớ những mốc chính:

- Atlas ANN `$vectorSearch`: các ngưỡng được tài liệu nêu như **6.0.11** ở nhánh 6.0, **7.0.2** ở nhánh 7.0 và các bản sau được hỗ trợ.
- Atlas ENN: mốc **6.0.16**, **7.0.10**, **7.3.2** theo nhánh, không đồng nhất với ANN.
- `$vectorSearch` trong `$unionWith`: bắt đầu có hỗ trợ từ **8.0** theo Manual.
- Self-managed Community/Enterprise Search/Vector Search: các mô hình hỗ trợ bắt đầu từ **8.2+**, với `mongot` và yêu cầu triển khai riêng.
- Atlas CLI local: cần Atlas CLI/container deployment phù hợp; tài liệu local nêu MongoDB **7.0.5+** cho Vector Search.
- Free/Flex: phục vụ học/POC theo giới hạn index/quota/resource, không tự là production-ready.
- Dedicated Search Nodes: giúp cô lập search workload, nhưng cần tier/region được hỗ trợ.
- Vector Search index phải đúng `type:"vectorSearch"`, vector path, dimensions và filter fields; index phải sẵn sàng.
- Search index được cập nhật bất đồng bộ; **MongoDB commit không đồng nghĩa Vector Search đã thấy document mới**.
- RAG cần authorization filters, model/version consistency, đánh giá recall/latency và bảo vệ dữ liệu.

Quy trình quyết định thực tế:

~~~text
Đúng môi trường?
    |
Đúng phiên bản và tier?
    |
Search service/index có sẵn?
    |
Embedding model và dimensions đúng?
    |
Query/API/permissions đúng?
    |
Đã benchmark workload thật?
    |
Mới đánh giá production readiness.
~~~

Khi nắm rõ từng lớp điều kiện, bạn sẽ phân biệt được **lỗi cú pháp**, **thiếu index**, **không tương thích phiên bản**, **hạn chế tier**, **thiếu Search service**, và **vấn đề hiệu năng** — tránh chữa sai nguyên nhân.

## Tài liệu MongoDB chính thức và nguồn tham khảo

- [MongoDB Vector Search — Overview](https://www.mongodb.com/docs/vector-search/)
- [MongoDB Vector Search — Deployment Options](https://www.mongodb.com/docs/vector-search/deployment/deployment-options/)
- [MongoDB Vector Search — Create Vector Search Indexes](https://www.mongodb.com/docs/vector-search/indexes/vector-search-type/)
- [MongoDB Vector Search — Run ANN and ENN Queries](https://www.mongodb.com/docs/vector-search/query/aggregation-stages/vector-search-stage/)
- [MongoDB Vector Search — Troubleshooting](https://www.mongodb.com/docs/vector-search/troubleshooting/)
- [MongoDB Manual — $vectorSearch Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/vectorsearch/)
- [MongoDB Atlas — Cluster Types](https://www.mongodb.com/docs/atlas/create-database-deployment/)
- [MongoDB Atlas CLI — Create a Local Atlas Deployment](https://www.mongodb.com/docs/atlas/cli/current/atlas-cli-deploy-local/)
- [MongoDB Community Edition — Search and Vector Search Support](https://www.mongodb.com/products/self-managed/community-edition)
- [MongoDB Search — Compatibility and Limitations](https://www.mongodb.com/docs/search/deployment/feature-compatibility/)
- [MongoDB Search — Manage Search Indexes](https://www.mongodb.com/docs/search/indexes/manage-indexes/)
- [MongoDB Search — Improve Search Index Performance](https://www.mongodb.com/docs/search/performance/index-performance/)
- [MongoDB Versions and Upgrade Paths](https://www.mongodb.com/docs/mongodb-versions/)
- [MongoDB Search and Vector Search Now Run Anywhere — 01/07/2026](https://www.mongodb.com/company/blog/product-release-announcements/mongodb-search-vector-search-now-run-anywhere)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
