# Dữ liệu vector, độ tương đồng và truy vấn kết hợp điều kiện trong NoSQL

## 1. Vì sao cần cơ sở dữ liệu vector?

Giả sử một cửa hàng trực tuyến có hàng trăm nghìn sản phẩm. Người dùng nhập:

> “Tìm sổ tay nhỏ gọn để tặng bạn, giá dưới 200.000 đồng, còn hàng.”

Nếu chỉ tìm bằng phép so khớp từ khóa, hệ thống có thể bỏ lỡ sản phẩm được mô tả là “quà tặng văn phòng phẩm”, “sổ ghi chép bỏ túi” hoặc “notebook bìa cứng”. Những câu này có thể gần nhau về **ngữ nghĩa** dù không trùng chuỗi ký tự.

**Tìm kiếm vector (vector search)** giải quyết một phần bài toán này bằng cách biến văn bản, hình ảnh hoặc dữ liệu khác thành một dãy số gọi là **vector biểu diễn (embedding)**. Một mô hình embedding được huấn luyện để các đối tượng có quan hệ ngữ nghĩa phù hợp nằm gần nhau trong một không gian vector. Cơ sở dữ liệu lưu vector, dùng phép đo độ gần để tìm những đối tượng tương tự, rồi trả về nội dung hoặc ID tương ứng.

Tuy nhiên, yêu cầu của người dùng thường có cả điều kiện chính xác: **giá tối đa**, **còn hàng**, **ngôn ngữ**, **loại sản phẩm**, **quyền xem của người dùng**. Vì vậy ứng dụng cần **truy vấn kết hợp**: tìm gần theo vector *và* lọc theo metadata có cấu trúc.

Trong hệ NoSQL, một số cơ sở dữ liệu được xây chuyên cho vector; một số cơ sở dữ liệu document hoặc search engine tích hợp vector index. Bài này dùng cách nhìn chung và minh họa API của **Qdrant**, một vector database, để làm rõ thuật toán và giới hạn triển khai. Ví dụ không có nghĩa mọi hệ NoSQL hỗ trợ cùng cú pháp hay cùng cơ chế đánh chỉ mục.

## 2. Một bản ghi vector gồm những gì?

Một bản ghi trong vector store thường có ba nhóm dữ liệu:

1. **Định danh**: ID duy nhất của điểm dữ liệu (point), đoạn văn hoặc sản phẩm.
2. **Vector**: dãy số thực mô tả nội dung, được tạo bởi mô hình embedding.
3. **Payload/metadata**: các trường có cấu trúc dùng để lọc, kiểm soát truy cập hoặc hiển thị.

Ví dụ dạng khái niệm:

```json
{
  "id": 101,
  "vector": [0.8, 0.6, 0.0, 0.0],
  "payload": {
    "productId": "P101",
    "title": "Sổ tay bìa cứng A5",
    "tenantId": "T01",
    "category": "stationery",
    "language": "vi",
    "available": true,
    "priceVnd": 120000
  }
}
```

Trong ví dụ học tập, vector chỉ có **4 chiều** để dễ quan sát. Embedding thực tế thường có số chiều lớn hơn, do model quyết định. Không được hiểu rằng dãy `[0.8, 0.6, 0, 0]` tự nhiên tương ứng với ý nghĩa “sổ tay”: nó chỉ là **vector giả lập** cho phần thực hành, chưa được sinh từ một mô hình ngôn ngữ.

Các giá trị metadata có hai vai trò khác nhau:

| Trường | Vai trò |
|---|---|
| `productId` | Liên kết kết quả vector với sản phẩm nguồn |
| `title` | Hiển thị nhanh hoặc giúp kiểm tra dữ liệu |
| `tenantId` | Giới hạn phạm vi dữ liệu của tổ chức/người dùng |
| `category`, `language` | Lọc theo yêu cầu chính xác |
| `available` | Chỉ lấy sản phẩm còn hàng |
| `priceVnd` | Lọc theo khoảng số |
| `vector` | Xếp hạng mức gần của nội dung với câu hỏi |

**Vector không thay thế metadata.** Không nên mã hóa `tenantId` hay trạng thái còn hàng chỉ bằng embedding rồi hy vọng phép đo tương đồng có thể đảm bảo các điều kiện này. Quyền truy cập và các ràng buộc nghiệp vụ phải được kiểm tra như điều kiện xác định.

## 3. Embedding: biểu diễn nội dung trong không gian số

Giả sử mô hình embedding là hàm \(f\), nhận đầu vào \(x\) (văn bản hoặc ảnh) và trả vector \(d\) chiều:

\[
f(x)=\mathbf{v}=[v_1,v_2,\ldots,v_d]\in\mathbb{R}^d
\]

Ví dụ khái niệm:

```text
"Sổ tay A5 bìa cứng" ----> embedding model ----> [0.08, -0.12, ..., 0.27]
"Notebook nhỏ gọn" -----> embedding model ----> [0.07, -0.10, ..., 0.25]
"Máy xay sinh tố" -------> embedding model ----> [-0.31, 0.20, ..., -0.14]
```

Các con số trên chỉ minh họa. Không thể diễn giải rằng một tọa độ riêng lẻ luôn có nghĩa cố định như “sổ”, “giá rẻ” hoặc “tiếng Việt”. Ý nghĩa thường nằm ở **cách các chiều phối hợp** và cấu trúc không gian mà mô hình đã học.

### Yêu cầu để hai vector có thể so sánh có ý nghĩa

- **Tương thích về mô hình**: vector truy vấn và vector dữ liệu cần được tạo bằng cùng mô hình hoặc cặp mô hình được thiết kế cho cùng không gian embedding.
- **Cùng số chiều và thứ tự chiều**: vector 768 chiều không thể tùy tiện so trực tiếp với vector 1536 chiều; thay đổi số chiều không phải chỉ thêm hoặc cắt số tùy ý.
- **Cùng cách tiền xử lý cần thiết**: làm sạch văn bản, tách đoạn, bổ sung ngữ cảnh và loại nội dung đầu vào ảnh hưởng chất lượng.
- **Nhất quán về chuẩn hóa/metric**: nếu dùng cosine, dot product hoặc Euclidean distance, phải hiểu mô hình và kho chỉ mục xử lý độ dài vector thế nào.
- **Quản lý phiên bản embedding**: thay model có thể làm thay đổi không gian vector, ngay cả khi hai model trùng số chiều.

Một số mô hình tạo embedding văn bản đơn thuần; một số mô hình đa phương thức hỗ trợ tìm hình ảnh bằng văn bản. Tương đồng ở đây là **tương đồng do mô hình học được**, không phải bằng chứng hai đối tượng đúng sự thật, giống hệt nhau hoặc có quyền được truy cập.

### Đơn vị lưu vector: cả tài liệu hay từng đoạn?

Nếu một tài liệu dài gồm nhiều chủ đề, một embedding duy nhất có thể không mô tả đủ từng phần. Ứng dụng hỏi đáp thường chia thành **chunk**, lưu mỗi chunk thành một point:

```text
Document DOC-10
├── chunk 0 -> vector V0, payload {docId: "DOC-10", chunkIndex: 0}
├── chunk 1 -> vector V1, payload {docId: "DOC-10", chunkIndex: 1}
└── chunk 2 -> vector V2, payload {docId: "DOC-10", chunkIndex: 2}
```

Metadata của mỗi chunk phải mang đủ thông tin lọc và phân quyền, chẳng hạn `tenantId`, `documentId`, trạng thái phát hành và nhãn truy cập. Việc chia nhỏ quá mức có thể mất ngữ cảnh; chunk quá dài có thể pha trộn nhiều chủ đề. Kích thước, overlap và cách gắn tiêu đề nên được quyết định theo loại tài liệu và chất lượng truy vấn thực tế.

## 4. Độ tương đồng: cosine, dot product và khoảng cách Euclidean

Vector store cần một **độ đo** để tìm những vector gần với vector truy vấn \(\mathbf{q}\).

### 4.1. Cosine similarity

Cosine đo góc giữa hai vector khác 0:

\[
\operatorname{cos}(\mathbf{q},\mathbf{x})
=\frac{\mathbf{q}\cdot\mathbf{x}}
{\|\mathbf{q}\|_2\|\mathbf{x}\|_2}
\]

Giá trị nằm trong khoảng \([-1,1]\) với vector thực khác 0. Điểm càng gần 1 tức hướng càng giống nhau; 0 nghĩa là vuông góc; gần -1 nghĩa là ngược hướng. Cách diễn giải “gần nhau về ý nghĩa” còn phụ thuộc mô hình embedding và dữ liệu.

Ví dụ:

\[
\mathbf{q}=[1,0],\quad
\mathbf{a}=[0.8,0.6],\quad
\mathbf{b}=[0.6,0.8]
\]

Ba vector này đều có độ dài 1:

\[
\operatorname{cos}(\mathbf{q},\mathbf{a})=0.8,\qquad
\operatorname{cos}(\mathbf{q},\mathbf{b})=0.6
\]

Do đó, theo cosine, `a` được xếp gần `q` hơn `b`. Đây là phép tính hình học, chưa nói gì về nội dung sản phẩm thật.

### 4.2. Dot product (tích vô hướng)

\[
\mathbf{q}\cdot\mathbf{x}=\sum_{i=1}^{d}q_i x_i
\]

Nếu các vector đều được **chuẩn hóa về độ dài 1**, dot product bằng cosine similarity. Nếu không chuẩn hóa, độ dài vector ảnh hưởng kết quả: vector dài hơn có thể nhận điểm lớn ngay cả khi góc kém phù hợp hơn. Một số mô hình được huấn luyện để dot product có ý nghĩa riêng; không nên tự thay metric mà chưa kiểm chứng.

### 4.3. Euclidean / L2 distance

\[
d_{L2}(\mathbf{q},\mathbf{x})
=\sqrt{\sum_{i=1}^{d}(q_i-x_i)^2}
\]

Với khoảng cách, **nhỏ hơn là gần hơn**, khác với điểm cosine thường **lớn hơn là gần hơn**. Một số API trả khoảng cách, một số trả điểm tương đồng hoặc điểm đã biến đổi; vì thế không thể so trực tiếp mọi `score` giữa các hệ thống.

### So sánh nhanh

| Độ đo | Ý nghĩa | Xếp hạng ưu tiên | Lưu ý |
|---|---|---|---|
| Cosine | Góc giữa vector | Giá trị lớn hơn | Vector 0 không có cosine xác định |
| Dot product | Tích vô hướng | Giá trị lớn hơn | Độ dài vector ảnh hưởng nếu chưa chuẩn hóa |
| Euclidean/L2 | Khoảng cách hình học | Giá trị nhỏ hơn | Nhạy với thang đo và độ dài |

**Không có metric tốt nhất tuyệt đối.** Chọn theo cách mô hình embedding được huấn luyện, khả năng của hệ lưu trữ và chất lượng đánh giá trên các câu hỏi đại diện.

## 5. Tìm k láng giềng gần nhất: exact kNN và ANN

Với \(N\) vector lưu trữ, bài toán **k-nearest neighbors (kNN)** trả về \(k\) vector gần truy vấn nhất theo metric đã chọn.

### Exact search

Cách đơn giản nhất là tính điểm giữa \(\mathbf{q}\) với **tất cả** vector, rồi lấy \(k\) kết quả tốt nhất:

```text
query vector q
    |
    +--> score(q, vector_1)
    +--> score(q, vector_2)
    +--> ...
    +--> score(q, vector_N)
    |
    +--> sort/rank --> top-k
```

Nếu phải so sánh toàn bộ \(N\) vector có \(d\) chiều, phần tính điểm thường có chi phí bậc \(O(Nd)\). Với dữ liệu nhỏ, exact search có thể đơn giản và đáp ứng đủ. Khi có hàng triệu vector và lưu lượng truy vấn cao, việc quét toàn bộ có thể trở nên tốn CPU, RAM và độ trễ.

### Approximate nearest neighbor (ANN)

**ANN** tìm tập kết quả *xấp xỉ* láng giềng gần nhất, giảm số phép so sánh cần thực hiện. Đổi lại có khả năng bỏ sót một số kết quả đúng thuộc top-k exact.

Những họ kỹ thuật thường gặp:

- **HNSW:** xây cấu trúc đồ thị láng giềng nhiều tầng để tìm kiếm gần đúng nhanh.
- **IVF:** chia không gian vector thành các nhóm (cluster/list), truy cập một số nhóm ứng viên.
- **Quantization / vector compression:** giảm dung lượng lưu hoặc tăng khả năng tính toán, có thể đổi lấy sai số xếp hạng.
- **Disk-oriented ANN:** hướng tới tập dữ liệu vượt xa dung lượng RAM, đánh đổi cách truy xuất và độ trễ I/O.

Chúng không đồng nhất về cách hoạt động hay tính năng trong từng sản phẩm. Tên “vector database” không đảm bảo cơ sở dữ liệu dùng một thuật toán ANN cụ thể.

### Đánh đổi quan trọng

| Mục tiêu | Thông thường cần cân nhắc |
|---|---|
| Độ chính xác kết quả gần nhất | Tăng phạm vi tìm kiếm ANN hoặc dùng exact ở tập nhỏ |
| Độ trễ truy vấn | Giảm số ứng viên duyệt, tận dụng chỉ mục và bộ nhớ |
| RAM/đĩa | Vector nhiều chiều, index lớn, quantization |
| Tốc độ ghi/cập nhật | Chi phí cập nhật cấu trúc chỉ mục |
| Dữ liệu thay đổi liên tục | Hành vi upsert, delete, tái xây chỉ mục và độ mới của kết quả |

ANN phù hợp khi độ trễ thấp với tập vector lớn quan trọng hơn việc luôn tìm đúng tuyệt đối top-k theo metric. Với truy vấn phải thỏa điều kiện quyền truy cập, **xấp xỉ chỉ được phép ở khâu xếp hạng vector**, không được phép xấp xỉ tính đúng/sai của điều kiện phân quyền.

## 6. Truy vấn kết hợp điều kiện: semantic similarity + metadata filter

Quay lại yêu cầu: “Tìm sổ tay tương tự mô tả quà tặng, giá dưới 200.000 đồng, còn hàng, tiếng Việt, chỉ trong dữ liệu tenant T01.”

Ta có hai loại điều kiện:

1. **Điều kiện mềm:** nội dung gần với câu hỏi. Có thể xếp hạng theo vector similarity.
2. **Điều kiện cứng:** `tenantId = T01`, `category = stationery`, `available = true`, `language = vi`, `priceVnd <= 200000`. Kết quả không được vi phạm điều kiện này.

Một cách mô tả logic:

\[
\operatorname{TopK}_{x\in D,\ \mathrm{filter}(x)=\mathrm{true}}
\operatorname{similarity}(\mathbf{q},\mathbf{v}_x)
\]

Tức là **lấy top-k trong tập các điểm đủ điều kiện**. Đây là khác biệt trọng yếu so với cách “lấy top-k gần nhất toàn bộ database, rồi loại những điểm không đạt điều kiện”.

### Ví dụ dữ liệu

Giả sử vector truy vấn giả lập là `[1, 0, 0, 0]`. Ta có sáu sản phẩm sau:

| ID | Điểm cosine với query | Tenant | Category | Language | Có hàng | Giá VND |
|---|---:|---|---|---|---|---:|
| 101 | 0.80 | T01 | stationery | vi | Có | 120.000 |
| 102 | 0.60 | T01 | stationery | vi | Có | 165.000 |
| 103 | 1.00 | T01 | electronics | vi | Có | 100.000 |
| 104 | 0.99 | T02 | stationery | vi | Có | 110.000 |
| 105 | 0.94 | T01 | stationery | en | Có | 90.000 |
| 106 | 0.95 | T01 | stationery | vi | Có | 350.000 |

Nếu chỉ xếp hạng theo vector, các điểm 103 và 104 đứng đầu. Nhưng 103 sai loại sản phẩm, 104 thuộc tenant khác; 105 sai ngôn ngữ và 106 vượt mức giá. **Kết quả hợp lệ** cho điều kiện của ví dụ chỉ còn điểm 101 và 102, xếp theo similarity là `101 → 102`.

Các con số minh họa được chọn sẵn, không phải kết quả do một mô hình embedding thật tạo ra.

## 7. Pre-filter, post-filter và lọc trong lúc tìm ANN

Đây là phần ảnh hưởng trực tiếp đến **đúng điều kiện** và **chất lượng top-k**.

### 7.1. Pre-filter: xác định tập hợp hợp lệ trước

```text
Tất cả điểm
    |
    v
lọc tenant/category/language/price/available
    |
    v
tập điểm hợp lệ
    |
    v
tìm láng giềng gần nhất trong tập hợp lệ
    |
    v
top-k hợp lệ
```

Ưu điểm: diễn đạt đúng ý nghĩa **top-k trong tập thỏa điều kiện**. Với điều kiện rất chọn lọc, tập còn lại nhỏ có thể khiến exact search hợp lý. Nhược điểm: cách triển khai đơn giản có thể phải tạo hoặc duyệt tập ứng viên lớn, tùy hệ thống và index. Các vector database hiện đại thường tích hợp filter vào quá trình duyệt ANN thay vì thực hiện đúng từng hộp trong sơ đồ.

### 7.2. Post-filter: tìm trước, lọc sau

```text
ANN top-3 toàn bộ dữ liệu
    |
    v
loại điểm sai tenant/loại/ngôn ngữ/giá
    |
    v
có thể còn 0 hoặc 1 kết quả
```

Với bảng ở trên, ANN top-3 toàn bộ có thể là 103, 104 và 106. Cả ba đều bị loại, dù database vẫn có hai kết quả hợp lệ 101, 102. **Post-filter trên top-k toàn cục không bảo đảm tìm được top-k hợp lệ.**

Có thể lấy nhiều hơn `k` ứng viên rồi lọc, gọi là **overfetch**, nhưng nếu điều kiện rất hẹp hoặc tập dữ liệu phân bố lệch thì vẫn có thể không đủ. Overfetch cũng không thay thế cơ chế phân quyền an toàn.

### 7.3. Filter-aware ANN

Một số hệ vector hỗ trợ phối hợp **payload index và vector index**, kiểm tra điều kiện ngay trong quá trình tìm kiếm. Hệ thống có thể thay đổi chiến lược tùy tính chọn lọc của filter:

- Tập lọc nhỏ: lấy các điểm hợp lệ rồi tính điểm vector trực tiếp.
- Tập lọc lớn: duyệt ANN và kiểm tra metadata ngay trong quá trình lấy ứng viên.
- Điều kiện phức tạp: dùng cấu trúc index hoặc kế hoạch khác để cân bằng độ trễ và recall.

Chiến lược thực tế khác nhau giữa sản phẩm và phiên bản; vì ANN vẫn có tính xấp xỉ, **đạt điều kiện lọc chính xác không đồng nghĩa bảo đảm thứ hạng top-k hoàn toàn đúng như exact search**.

### Điều kiện bắt buộc là điều kiện cứng

Quyền truy cập, tenant, trạng thái phát hành và phạm vi dữ liệu phải được áp dụng ở **phía máy chủ** dựa trên danh tính đã xác thực. Không cho client tự gửi `tenantId` tùy ý để vượt qua phân quyền. Metadata filter giúp thu hẹp truy vấn nhưng không tự thay thế hệ thống xác thực, phân quyền, kiểm tra nguồn dữ liệu và kiểm soát những đường đọc khác.

## 8. Ví dụ Qdrant: lưu vector và truy vấn có lọc

Ví dụ dưới đây trình bày **HTTP API của Qdrant** với vector 4 chiều và metric Cosine. Mục đích là minh họa luồng:

```text
Tạo collection -> Upsert vectors + payload -> Tạo payload index
       -> Truy vấn vector có filter -> Trả point IDs + score + payload
```

Các API dùng endpoint Qdrant thông dụng. Khi sử dụng một phiên bản cụ thể hoặc dịch vụ được quản lý, cần đối chiếu API/khả năng cấu hình của phiên bản đó. Ví dụ giả định đã có Qdrant chạy ở `http://localhost:6333` trong môi trường thử nghiệm riêng.

### 8.1. Tạo collection 4 chiều

```http
PUT /collections/catalog_demo
Content-Type: application/json

{
  "vectors": {
    "size": 4,
    "distance": "Cosine"
  }
}
```

Trong thực tế, `size` phải khớp chính xác số chiều do embedding model tạo ra. Nếu model trả 768 chiều, một collection cấu hình size 4 sẽ không thể nhận trực tiếp vector 768 chiều. Việc thay đổi model có thể yêu cầu lập collection/index mới và tái tạo embedding.

### 8.2. Ghi các điểm dữ liệu mẫu

```http
PUT /collections/catalog_demo/points?wait=true
Content-Type: application/json

{
  "points": [
    {
      "id": 101,
      "vector": [0.80, 0.60, 0.00, 0.00],
      "payload": {
        "productId": "P101",
        "title": "Sổ tay A5",
        "tenantId": "T01",
        "category": "stationery",
        "language": "vi",
        "available": true,
        "priceVnd": 120000
      }
    },
    {
      "id": 102,
      "vector": [0.60, 0.80, 0.00, 0.00],
      "payload": {
        "productId": "P102",
        "title": "Sổ tay bỏ túi",
        "tenantId": "T01",
        "category": "stationery",
        "language": "vi",
        "available": true,
        "priceVnd": 165000
      }
    },
    {
      "id": 103,
      "vector": [1.00, 0.00, 0.00, 0.00],
      "payload": {
        "productId": "P103",
        "title": "Thiết bị điện tử",
        "tenantId": "T01",
        "category": "electronics",
        "language": "vi",
        "available": true,
        "priceVnd": 100000
      }
    },
    {
      "id": 104,
      "vector": [0.99, 0.141067, 0.00, 0.00],
      "payload": {
        "productId": "P104",
        "title": "Sổ tay khách hàng khác",
        "tenantId": "T02",
        "category": "stationery",
        "language": "vi",
        "available": true,
        "priceVnd": 110000
      }
    },
    {
      "id": 105,
      "vector": [0.94, 0.341174, 0.00, 0.00],
      "payload": {
        "productId": "P105",
        "title": "Notebook English",
        "tenantId": "T01",
        "category": "stationery",
        "language": "en",
        "available": true,
        "priceVnd": 90000
      }
    },
    {
      "id": 106,
      "vector": [0.95, 0.31225, 0.00, 0.00],
      "payload": {
        "productId": "P106",
        "title": "Sổ tay cao cấp",
        "tenantId": "T01",
        "category": "stationery",
        "language": "vi",
        "available": true,
        "priceVnd": 350000
      }
    }
  ]
}
```

Các vector mẫu được chọn có độ dài xấp xỉ 1; với Qdrant ở chế độ Cosine, việc chuẩn hóa vector là chi tiết được hệ thống hỗ trợ. Đây là tập dữ liệu toán học để minh họa kết quả lọc, **không phải embedding thực của các mô tả sản phẩm**.

### 8.3. Tạo payload index cho các trường lọc thường xuyên

Khi collection lớn, điều kiện lọc nên được hỗ trợ bằng **payload index** phù hợp. Ví dụ tạo index dạng keyword cho `tenantId`:

```http
PUT /collections/catalog_demo/index?wait=true
Content-Type: application/json

{
  "field_name": "tenantId",
  "field_schema": "keyword"
}
```

Có thể tạo tương tự cho `category` và `language`. Với `available`, dùng schema kiểu boolean; với `priceVnd`, dùng index số nguyên thích hợp khi truy vấn khoảng giá phổ biến:

```http
PUT /collections/catalog_demo/index?wait=true
Content-Type: application/json

{
  "field_name": "priceVnd",
  "field_schema": "integer"
}
```

**Index không miễn phí**: tốn dung lượng và có chi phí cập nhật. Ưu tiên những trường lọc thường xuyên, có ảnh hưởng thực tế đến hiệu năng và mức chọn lọc dữ liệu. Tùy quy mô và chức năng của phiên bản Qdrant, nên tạo các payload index cần thiết trước khi nạp tập dữ liệu rất lớn.

### 8.4. Truy vấn vector kết hợp nhiều điều kiện AND

```http
POST /collections/catalog_demo/points/query
Content-Type: application/json

{
  "query": [1.0, 0.0, 0.0, 0.0],
  "filter": {
    "must": [
      { "key": "tenantId", "match": { "value": "T01" } },
      { "key": "category", "match": { "value": "stationery" } },
      { "key": "language", "match": { "value": "vi" } },
      { "key": "available", "match": { "value": true } },
      { "key": "priceVnd", "range": { "lte": 200000 } }
    ]
  },
  "limit": 5,
  "with_payload": true
}
```

`must` diễn đạt điều kiện **AND**: chỉ những point thỏa **tất cả** điều kiện mới được đưa vào kết quả. Với dữ liệu mẫu, các point hợp lệ là **101 và 102**; point 103 sai category, 104 sai tenant, 105 sai language và 106 vượt giá.

Hệ thống trả về ID, điểm tương đồng và payload theo cấu trúc response của API. Kết quả thực tế có thể chứa trường metadata hệ thống và thứ tự/chi tiết tính điểm do phiên bản xử lý. Ta chỉ cần hiểu ý nghĩa nghiệp vụ: **xếp hạng theo vector trong tập dữ liệu đã đáp ứng điều kiện cứng**.

### 8.5. Điều kiện OR, phủ định và khoảng

Ngoài AND, nhiều vector store hỗ trợ cấu trúc điều kiện như **OR**, **NOT**, khoảng số hoặc khoảng thời gian. Với Qdrant, một dạng OR có thể biểu diễn qua `should`:

```json
{
  "filter": {
    "must": [
      { "key": "tenantId", "match": { "value": "T01" } },
      { "key": "available", "match": { "value": true } }
    ],
    "should": [
      { "key": "category", "match": { "value": "stationery" } },
      { "key": "category", "match": { "value": "gift" } }
    ],
    "must_not": [
      { "key": "language", "match": { "value": "en" } }
    ]
  }
}
```

Ý định ở đây là giới hạn tenant T01, chỉ hàng còn bán, thuộc một trong hai nhóm `stationery` hoặc `gift`, đồng thời loại ngôn ngữ `en`. Cần xem chính xác ngữ nghĩa của từng nhóm điều kiện trong phiên bản API sử dụng, nhất là với trường thiếu/null, mảng metadata hoặc điều kiện lồng nhau.

## 9. Kết hợp tìm kiếm vector với từ khóa

Vector search hữu ích khi câu hỏi và tài liệu **khác từ ngữ nhưng gần nghĩa**. Tuy vậy có những yêu cầu đòi khớp chính xác:

- Mã sản phẩm `BK-101`.
- Số phiên bản `v2.3.1`.
- Tên lớp, mã lỗi, số hợp đồng.
- Điều khoản hoặc cụm từ pháp lý phải xuất hiện nguyên văn.

Đối với các trường hợp này, chỉ tìm kiếm vector có thể trả về tài liệu “gần ý” nhưng sai mã. **Hybrid search** kết hợp kết quả semantic/vector với tìm kiếm lexical/keyword.

Một pipeline tham khảo:

```text
                              +--> Vector retrieval --------+
User query -> phân tích query |                            +--> hợp nhất --> rerank --> kết quả
                              +--> Keyword/BM25 retrieval --+
                                         |
                              Áp dụng tenant/ACL/metadata
                              vào mọi nhánh phù hợp
```

Các hệ triển khai khác nhau có thể hỗ trợ vector, sparse vector, full-text và fusion ở những lớp riêng. Không nên giả định hệ vector nào cũng tích hợp đầy đủ tìm kiếm văn bản.

### Hợp nhất xếp hạng bằng Reciprocal Rank Fusion

Khi hai nhánh tìm kiếm trả **điểm ở thang đo khác nhau**, cộng thẳng cosine score và BM25 score có thể gây lệch. Một kỹ thuật hợp nhất thứ hạng là **Reciprocal Rank Fusion (RRF)**:

\[
\operatorname{RRF}(d)=\sum_{r\in R}
\frac{1}{k+\operatorname{rank}_r(d)}
\]

Trong đó \(R\) là các danh sách kết quả và \(k\) là hằng số làm trơn (thường chọn theo cấu hình, ví dụ 60). Văn bản đứng thứ hạng cao ở nhiều danh sách sẽ nhận điểm hợp nhất tốt. RRF giải quyết khác biệt *thang điểm*, nhưng chất lượng cuối cùng vẫn cần đánh giá bằng truy vấn thực tế.

### Reranking và điều kiện cứng

Sau retrieval có thể dùng mô hình reranker để đánh giá sâu hơn mối liên hệ giữa câu hỏi và các ứng viên. Reranking thường chậm hơn so với việc tra ANN đơn thuần, vì vậy thường chỉ áp dụng trên một tập ứng viên giới hạn.

**Reranker không được “cứu lại” tài liệu không đủ quyền truy cập hoặc sai filter bắt buộc.** Tập dữ liệu đi vào bước rerank phải tuân thủ điều kiện an toàn và phạm vi truy vấn do server quyết định.

## 10. Từ câu hỏi người dùng đến truy vấn kết hợp: luồng ứng dụng

Với một endpoint tìm kiếm sản phẩm, luồng xử lý hợp lý có thể là:

```text
Client
  |
  v
API xác thực user/session
  |
  +--> lấy tenantId và quyền xem từ identity đáng tin cậy
  +--> kiểm tra điều kiện nghiệp vụ (giá, loại, ngôn ngữ, trạng thái)
  |
  v
Embedding query text (đúng model/version)
  |
  v
Vector DB: similarity + mandatory metadata/ACL filters
  |
  v
IDs + scores + payload
  |
  +--> tùy chọn hybrid retrieval / reranking
  +--> tùy chọn đọc nguồn dữ liệu chính và xác minh quyền/trạng thái mới nhất
  |
  v
Danh sách kết quả an toàn, được xếp hạng
```

Pseudo-code ở tầng dịch vụ:

```python
def search_products(user, text, category, max_price_vnd, limit=10):
    tenant_id = authorize_and_get_tenant(user)
    query_vector = embed(text, model="catalog-embedding-v1")

    mandatory_filter = {
        "tenantId": tenant_id,       # lấy từ identity đã xác thực
        "category": category,
        "available": True,
        "priceVnd_lte": max_price_vnd,
    }

    candidates = vector_store.search(
        vector=query_vector,
        filter=mandatory_filter,
        limit=limit,
    )

    # Bước này chỉ minh họa; không phải cú pháp SDK của vendor.
    return verify_current_access_and_stock(candidates, user)
```

Ở đây `max_price_vnd` phải được kiểm tra kiểu, giới hạn hợp lệ và đơn vị tiền. `tenantId` không lấy từ trường do client tùy ý gửi. Nếu metadata tồn kho cập nhật chậm hoặc quyền thay đổi khẩn cấp, xác minh lại nguồn chính ở đường trả kết quả có thể là lớp bảo vệ bổ sung.

**Không nên phụ thuộc hoàn toàn vào bước kiểm tra sau retrieval để đảm bảo cách ly tenant:** truy vấn lấy ứng viên ngay từ đầu phải được giới hạn đúng quyền; còn các đường đọc payload, truy vấn theo ID và log cũng phải được kiểm soát.

## 11. Ingestion, cập nhật và xóa dữ liệu vector

Kết quả tìm kiếm chỉ đúng nếu vector và metadata được đồng bộ với dữ liệu nguồn. Một pipeline nạp dữ liệu:

```text
Nguồn sản phẩm / tài liệu
     |
     v
Chuẩn hóa nội dung -> tách chunk (nếu cần)
     |
     v
Gọi embedding model
     |
     v
Upsert {pointId, vector, payload, embeddingVersion}
     |
     v
Vector index / payload index có thể truy vấn
```

Các điểm cần quyết định:

1. **ID ổn định**: cùng một sản phẩm/chunk cập nhật nhiều lần nên dùng cùng định danh point hoặc một quy tắc mapping nhất quán để upsert không tạo bản sao không cần thiết.
2. **Phiên bản dữ liệu nguồn**: lưu `sourceVersion`, `updatedAt` hoặc event sequence để bỏ qua sự kiện cũ đến muộn.
3. **Version embedding**: cùng một collection có thể cần quy ước rõ model/version; đổi model phải có kế hoạch tái tạo vector.
4. **Tính idempotent**: sự kiện xử lý lại không được tạo ra các point trùng hoặc ghi đè phiên bản mới bằng dữ liệu cũ.
5. **Xóa và thu hồi quyền**: phải xóa/điều chỉnh point, payload/index và cache trong thời gian đáp ứng chính sách. Với nội dung nhạy cảm, không được mặc định một luồng đồng bộ cuối cùng sẽ bảo vệ tức thời mọi yêu cầu.
6. **Độ mới kết quả**: cần xác định thời gian từ khi sản phẩm đổi giá/hết hàng đến khi vector index phản ánh sự thay đổi.

Không phải thay đổi nào cũng cần tạo lại embedding: cập nhật giá hoặc trạng thái còn hàng thường chỉ làm thay đổi **payload**. Nếu văn bản dùng tạo embedding thay đổi đáng kể, cần tạo vector mới. Khi chọn bước tối ưu này, phải biết chính xác nội dung nào được đưa vào embedding.

## 12. Tính đúng đắn khi kết hợp bộ lọc

Trong một hệ vector có metadata filter, cần phân biệt rõ:

| Vấn đề | Cần đảm bảo |
|---|---|
| Giá ≤ 200.000 đồng | So sánh số trên trường số, không so chuỗi giá |
| Ngôn ngữ `vi` | Quy ước mã ngôn ngữ thống nhất; xử lý trường thiếu rõ ràng |
| Hàng còn bán | Metadata đủ mới hoặc xác minh lại nguồn giao dịch |
| Tenant/user ACL | Filter bắt buộc do server tạo từ định danh tin cậy |
| Nhiều điều kiện AND | Mọi điều kiện phải được thỏa đồng thời |
| Điều kiện OR | Bảo toàn đúng nhóm logic, đặc biệt khi kết hợp với AND |
| Top-k | Lấy top-k trong tập hợp lệ, không chỉ lọc top-k toàn cục |
| Độ tương đồng | Metric, model và chiến lược index phải nhất quán |
| Tài liệu xóa/ẩn | Không trả lại qua cache, search index hoặc đường đọc phụ |

### Metadata ở cấp document và cấp chunk

Một tài liệu nội bộ có thể có nhiều chunk. Nếu quyền truy cập nằm ở tài liệu cha nhưng vector store lưu từng chunk, mỗi chunk cần được gắn metadata đúng quyền, hoặc cơ chế truy vấn phải có một cách giới hạn tương đương **trước khi trả nội dung**.

Ví dụ:

```json
{
  "pointId": 1001,
  "documentId": "DOC-88",
  "chunkIndex": 2,
  "tenantId": "T01",
  "accessGroups": ["engineering"],
  "published": true,
  "embeddingVersion": "v1"
}
```

Nhóm truy cập là **metadata có cấu trúc**, không nên được suy ra bằng similarity. Cần có chính sách cập nhật những chunk đã index khi quyền của document cha thay đổi. Trong ứng dụng nội bộ quan trọng, truy vấn và việc trả nội dung gốc cần kiểm tra thêm phân quyền ở hệ chủ quản.

## 13. Đánh giá chất lượng và hiệu năng vector search

Một tập vector tạo được chỉ mục và trả về kết quả không đồng nghĩa trải nghiệm tìm kiếm đã tốt. Cần đánh giá **hai nhóm tiêu chí**: tính phù hợp và hiệu năng/vận hành.

### 13.1. Chất lượng xếp hạng

Chuẩn bị bộ câu hỏi thực tế cùng các kết quả được đánh dấu liên quan (*relevance judgments*). Sau đó xem:

- **Recall@k:** trong các kết quả liên quan đã biết, có bao nhiêu xuất hiện trong top-k. Với ANN, cần phân biệt recall đối với top-k exact theo metric và recall đối với đánh giá liên quan nghiệp vụ.
- **Precision@k:** tỷ lệ kết quả trong top-k thật sự liên quan.
- **MRR:** phù hợp nếu người dùng chủ yếu tìm kết quả đúng đầu tiên.
- **nDCG@k:** hữu ích khi có nhiều mức độ liên quan và cần đánh giá thứ tự.
- **Tỷ lệ vi phạm filter:** phải bằng 0 cho điều kiện cứng, đặc biệt là quyền truy cập.

Có thể tách bộ câu hỏi thành: truy vấn ngắn, ngôn ngữ khác nhau, mã sản phẩm chính xác, truy vấn có giá/loại, câu hỏi đa nghĩa, tài liệu mới và quyền truy cập phức tạp. Một tập benchmark chỉ gồm câu rất dễ thường cho kết quả lạc quan.

### 13.2. Hiệu năng hệ thống

Theo dõi:

- Độ trễ trung vị và **p95/p99** khi tải tăng.
- QPS, CPU, bộ nhớ, I/O và dung lượng vector/index/payload.
- Thời gian ingest và độ trễ cập nhật index.
- Số ứng viên ANN được kiểm tra, độ chọn lọc của filter, chất lượng top-k sau filter.
- Chi phí gọi embedding/rerank model và kích thước dữ liệu truyền tải.
- Hành vi khi một tenant hoặc một danh mục chiếm phần lớn lưu lượng (**hot partition/tenant**).

Ví dụ, một truy vấn không filter có thể rất nhanh nhưng truy vấn có filter chỉ giữ 0,01% dữ liệu có thể kích hoạt chiến lược tìm kiếm khác. Benchmark phải phản ánh **phân bố metadata và sự kết hợp điều kiện thực**, không chỉ số lượng vector.

## 14. Các lựa chọn thiết kế ảnh hưởng đến truy vấn kết hợp

### 14.1. Một collection hay nhiều collection?

Có thể để nhiều tenant trong một collection và filter theo `tenantId`, hoặc phân tách thành collection/namespace riêng. Các yếu tố quyết định gồm số tenant, yêu cầu cô lập, khả năng phân quyền, cách vận hành index, tần suất truy vấn và giới hạn của nhà cung cấp.

Không có lựa chọn chung cho mọi trường hợp. Với dữ liệu phải cách ly mạnh, cần đánh giá cả bảo vệ ở tầng storage/network, không chỉ filter ở lớp ứng dụng. Với số tenant rất lớn, tạo một collection nhỏ cho từng tenant có thể làm tăng chi phí quản lý.

### 14.2. Một vector hay nhiều vector cho một bản ghi?

Sản phẩm có tiêu đề, mô tả dài và hình ảnh. Có thể:

- Ghép nội dung liên quan rồi tạo **một vector**.
- Tạo nhiều vector/điểm theo từng chunk hoặc từng loại nội dung.
- Sử dụng **named vectors** hoặc mô hình đa phương thức nếu hệ lưu trữ hỗ trợ.

Nhiều vector cho cùng một thực thể giúp tìm chính xác phần liên quan nhưng đòi cơ chế gộp/deduplicate kết quả theo `productId` hoặc `documentId`, tránh trả một tài liệu lặp lại nhiều lần.

### 14.3. Ngưỡng similarity và top-k

Không nên mặc định mọi điểm cosine trên 0,8 đều “đúng” hay dưới 0,8 đều “sai”. Phân bố score phụ thuộc model, corpus và dạng câu hỏi. Một ngưỡng lọc score cần được hiệu chỉnh theo dữ liệu đánh giá. Nếu vừa đặt ngưỡng quá cao vừa dùng metadata filter rất hẹp, ứng dụng có thể trả rỗng ngay cả khi có nội dung hữu ích.

Với tập kết quả ít, cần thiết kế trải nghiệm rõ ràng: thông báo không có kết quả phù hợp điều kiện, hoặc đề nghị người dùng nới bớt **điều kiện tùy chọn**; tuyệt đối không tự nới quyền truy cập hay tenant.

## 15. Tình huống thực hành: tìm tài liệu kỹ thuật theo quyền truy cập

Một công ty lưu tài liệu kỹ thuật theo cấu trúc:

```text
Document
├── docId
├── title
├── language
├── department
├── visibility / allowedGroups
├── version
└── chunks[]
       ├── chunkId
       ├── text
       └── embedding
```

Người dùng hỏi: “Cách xử lý lỗi kết nối MongoDB khi service khởi động?” và chỉ được xem tài liệu nhóm `backend` của tenant `T01`.

Các bước truy vấn đề xuất:

1. Xác thực người dùng và tra nhóm truy cập tại nguồn đáng tin cậy.
2. Chuyển câu hỏi thành embedding theo model/version phù hợp với các chunk được index.
3. Áp filter `tenantId = T01`, `published = true` và các điều kiện quyền truy cập ở truy vấn vector (hoặc cơ chế tương đương an toàn).
4. Lấy một tập ứng viên; kết hợp thêm keyword search cho tên lỗi, mã lỗi hoặc chính xác từ `MongoDB` khi có công cụ hỗ trợ.
5. Gộp kết quả trùng `docId`, rerank nếu cần, xác minh quyền và trạng thái nguồn trước khi trả trích đoạn/nội dung.
6. Nếu dùng kết quả cho hệ thống hỏi đáp, trả ID tài liệu, tiêu đề, vị trí chunk để có thể dẫn nguồn.

Một schema payload minh họa:

```json
{
  "docId": "DOC-88",
  "chunkIndex": 3,
  "tenantId": "T01",
  "department": "backend",
  "language": "vi",
  "published": true,
  "allowedGroups": ["backend", "sre"],
  "embeddingVersion": "catalog-embedding-v1"
}
```

Nếu khách hàng yêu cầu “chỉ tài liệu tiếng Việt cập nhật từ 2026”, có thể bổ sung điều kiện metadata cho `language` và `updatedAt` bằng kiểu dữ liệu/ngữ nghĩa khoảng thời gian phù hợp của hệ lưu trữ. Không nên nhúng ngày tháng hay quyền truy cập vào câu hỏi embedding rồi coi đó là bộ lọc chính xác.

### Ví dụ điều kiện mở rộng

| Điều kiện | Thuộc nhóm nào? | Cách xử lý |
|---|---|---|
| “cách xử lý lỗi kết nối” | Ngữ nghĩa | Vector similarity và có thể thêm keyword |
| Có từ “MongoDB” | Từ khóa chính xác nếu được yêu cầu | Lexical/text matching |
| Chỉ tài liệu tiếng Việt | Metadata | `language = vi` |
| Chỉ tài liệu đã phát hành | Metadata | `published = true` |
| Chỉ tài liệu tenant T01 | Phân quyền/phạm vi | Filter bắt buộc từ identity |
| Chỉ tài liệu nhóm backend được xem | Phân quyền | Chính sách ACL và filter/kiểm tra nguồn |
| Tài liệu cập nhật sau một ngày | Metadata có điều kiện khoảng | Date/time range phù hợp |

## 16. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Trộn vector từ hai embedding model khác không gian | Similarity mất ý nghĩa | Gắn version, tái tạo vector/index khi đổi model |
| Chọn metric theo thói quen | Xếp hạng khác mục tiêu model | Dùng metric được khuyến nghị và đo trên tập đánh giá |
| Dùng embedding thay điều kiện giá, trạng thái hay ACL | Có thể trả kết quả sai hoặc lộ dữ liệu | Filter metadata chính xác, chính sách server-side |
| Lấy ANN top-k toàn cục rồi mới lọc | Có thể thiếu hoặc mất hết kết quả hợp lệ | Dùng filtered retrieval, kiểm tra recall khi filter hẹp |
| Cộng thẳng score cosine với BM25 | Hai score khác thang đo | Chuẩn hóa có căn cứ hoặc dùng fusion theo thứ hạng |
| Chỉ dùng vector cho mã sản phẩm/mã lỗi | Có thể trả nội dung gần nghĩa nhưng sai mã | Kết hợp keyword/exact filter |
| Chia tài liệu thành nhiều chunk mà không mang quyền xuống chunk | Truy xuất nhầm nội dung hạn chế | Đồng bộ và kiểm soát metadata/ACL ở cấp point |
| Cập nhật sản phẩm gốc nhưng quên vector/payload | Giá, tồn kho hoặc nội dung kết quả lỗi thời | Ingestion/upsert/delete có version và độ trễ đã định |
| Đánh giá chỉ bằng độ trễ truy vấn không filter | Bỏ sót rủi ro khi metadata rất chọn lọc | Benchmark truy vấn kết hợp thật |
| Tự nhận score 0,8 là ngưỡng đúng mọi corpus | Loại kết quả tốt hoặc giữ kết quả kém | Hiệu chỉnh threshold theo model và bài toán |
| Coi ANN trả top-k tuyệt đối chính xác | Bỏ sót kết quả gần hơn | Đo recall và điều chỉnh search/index parameters |
| Dùng một kết quả truy vấn để tự động quyết định giao dịch | Similarity không bảo đảm tính đúng về nghiệp vụ | Xác minh bản ghi/điều kiện tại hệ nguồn có thẩm quyền |

## 17. Bài tập kiểm tra hiểu biết

### Bài 1 — Phân biệt similarity và filter

Cho bảng sáu sản phẩm ở mục 6. Truy vấn vector có điểm 103 cao nhất nhưng yêu cầu chỉ nhóm `stationery`, tenant `T01`, giá tối đa `200000`, tiếng Việt và còn hàng. Hãy viết danh sách kết quả hợp lệ.

*Gợi ý:* `101` và `102`. Điểm tương đồng cao hơn không có quyền vượt qua điều kiện cứng.

### Bài 2 — Vì sao post-filter top-3 có thể sai?

Với bảng mẫu, top-3 vector toàn bộ tập dữ liệu là `103`, `104`, `106`. Sau lọc, cả ba bị loại. Hãy giải thích vì sao hệ thống không được kết luận rằng **không có sản phẩm phù hợp**, và đề xuất thay đổi trong pipeline truy vấn.

### Bài 3 — Chọn metric

Cho \(\mathbf{q}=[1,0]\), \(\mathbf{a}=[0.8,0.6]\), \(\mathbf{b}=[0.6,0.8]\). Tính cosine và cho biết vector nào gần `q` hơn. Sau đó giải thích điều gì thay đổi nếu vector chưa chuẩn hóa và ta sử dụng dot product.

### Bài 4 — Cập nhật metadata

Sản phẩm `P101` hết hàng nhưng mô tả không thay đổi. Có cần gọi lại embedding model không? Trường nào phải cập nhật, và vì sao không thể chỉ chờ chỉ mục vector tự suy ra tình trạng còn hàng?

*Gợi ý:* cập nhật `available` trong payload; embedding chỉ phản ánh dữ liệu được đưa vào model, không tự biết tồn kho hiện tại.

### Bài 5 — Thiết kế an toàn cho tài liệu nội bộ

Một hệ thống tìm tài liệu có metadata `tenantId`, `allowedGroups`, `published`. Client gửi `tenantId = T02` trong khi người dùng đăng nhập thuộc T01. Hãy chỉ ra các bước xác thực, lấy tenant từ nguồn đáng tin cậy, filter quyền và kiểm tra lại trước khi trả nội dung.

### Bài 6 — Đánh giá ANN kết hợp filter

Một index ANN đạt recall@10 cao khi không lọc; nhưng khi `category` chỉ còn 0,1% dữ liệu, tỷ lệ trả đủ mười kết quả giảm mạnh. Hãy giải thích vai trò của selectivity, chiến lược filtered ANN, payload index, và cách xây tập benchmark theo các điều kiện thật.

## 18. Kết luận

**Dữ liệu vector** biểu diễn nội dung bằng dãy số và hỗ trợ truy xuất gần nghĩa thông qua các độ đo như **cosine similarity, dot product hoặc L2 distance**. **Vector index và ANN** giúp giảm chi phí tìm láng giềng trong tập dữ liệu lớn, với đánh đổi giữa tốc độ, bộ nhớ và độ chính xác xếp hạng.

Trong ứng dụng thật, tìm gần theo vector chỉ là một phần của câu hỏi. Người dùng còn đưa ra điều kiện có cấu trúc về giá, danh mục, ngôn ngữ, thời gian, trạng thái và quyền truy cập. **Truy vấn kết hợp điều kiện** phải trả top-k theo similarity **trong tập dữ liệu thỏa filter**, thay vì tùy tiện lọc top-k toàn cục rồi chấp nhận thiếu kết quả. Metadata filter, version embedding, đồng bộ nguồn, ACL và đánh giá chất lượng là những thành phần không thể bỏ qua.

Khi thiết kế một tính năng vector search trong NoSQL, hãy xác định **đơn vị được embedding**, **metric**, **access pattern**, **các điều kiện bắt buộc**, **mức độ mới của dữ liệu** và **cách đánh giá recall/độ trễ**. Từ đó chọn schema payload, index và pipeline truy vấn phù hợp với nghiệp vụ.
