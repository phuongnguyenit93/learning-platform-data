# Chỉ mục vector gần đúng, độ chính xác truy hồi và chi phí

Khi tìm một tài liệu bằng mã \`documentId\`, cơ sở dữ liệu có thể tra cứu trực tiếp theo khóa. Nhưng khi người dùng hỏi **“Những tài liệu nào có nội dung gần với câu hỏi này?”**, không có một khóa đơn giản nào mô tả đầy đủ ý nghĩa câu hỏi. Một cách giải quyết phổ biến là chuyển văn bản, hình ảnh hoặc đối tượng khác thành **vector embedding** rồi tìm các vector gần nhau trong không gian nhiều chiều.

Nếu hệ thống có hàng triệu vector, việc tính khoảng cách từ một câu hỏi đến **tất cả** vector có thể tốn nhiều phép tính và băng thông bộ nhớ. Các hệ cơ sở dữ liệu NoSQL chuyên biệt cho tìm kiếm vector thường triển khai **chỉ mục láng giềng gần đúng** (*Approximate Nearest Neighbor – ANN*) để giảm lượng dữ liệu cần xét.

ANN có thể giúp truy vấn nhanh và rẻ hơn, nhưng không bảo đảm luôn trả về đúng toàn bộ \`k\` vector gần nhất theo phép đo đã chọn. Do đó, khi thiết kế một ứng dụng tìm kiếm ngữ nghĩa, cần hiểu đồng thời:

1. **Chỉ mục vector gần đúng được tổ chức và truy vấn như thế nào?**
2. **Độ chính xác truy hồi (*recall*) được đo ra sao, và khác gì với mức liên quan nghiệp vụ?**
3. **Độ trễ, CPU, RAM, dung lượng lưu trữ, xây dựng chỉ mục và cập nhật dữ liệu đánh đổi với recall như thế nào?**

Bài học trình bày các khái niệm đó qua một ví dụ xuyên suốt, so sánh các họ chỉ mục phổ biến, đưa ra chương trình thí nghiệm và cách xây dựng quy trình lựa chọn cấu hình cho workload thực tế.

## 1. Bài toán: tìm tài liệu gần nghĩa trong một kho tri thức

Giả sử một hệ thống hỏi đáp nội bộ có **1 triệu đoạn tài liệu** (*chunks*). Mỗi đoạn được mô hình embedding biểu diễn bằng vector gồm **768 số thực**:

~~~json
{
  "id": "doc-2026-00042#chunk-03",
  "tenantId": "org-a",
  "documentId": "doc-2026-00042",
  "title": "Quy trình hoàn tiền",
  "text": "Yêu cầu hoàn tiền được xem xét sau khi...",
  "embeddingModel": "embedding-model-v1",
  "embedding": [0.012, -0.083, 0.041, 0.097]
}
~~~

Trường \`embedding\` chỉ hiển thị **4 số để minh họa**; trong dữ liệu thật của ví dụ, nó có đủ 768 phần tử. Tên mô hình cũng chỉ là ký hiệu. Các vector muốn so sánh có ý nghĩa cần được tạo theo **cùng cấu hình biểu diễn tương thích**.

Khi người dùng hỏi:

> “Làm sao xử lý yêu cầu trả lại tiền sau khi hủy đơn?”

Ứng dụng tạo vector cho câu hỏi, rồi tìm những vector tài liệu gần nó nhất. Các tài liệu tìm được có thể dùng làm kết quả tìm kiếm hoặc làm ngữ cảnh cho hệ thống RAG (*retrieval-augmented generation*).

~~~mermaid
flowchart LR
    A["Tài liệu"] --> B["Cắt thành các đoạn"]
    B --> C["Mô hình embedding"]
    C --> D["Vector + ID + metadata"]
    D --> E["Chỉ mục ANN"]
    Q["Câu hỏi người dùng"] --> F["Embedding của câu hỏi"]
    F --> E
    E --> G["Ứng viên gần nhất"]
    G --> H["Lọc quyền, lấy nội dung, rerank nếu cần"]
    H --> I["Trả kết quả hoặc đưa vào RAG"]
~~~

Một yêu cầu tìm kiếm có thể có những ràng buộc:

| Thuộc tính | Giá trị minh họa | Tác động đến thiết kế |
| --- | --- | --- |
| Số vector | 1.000.000, dự kiến tăng lên 10.000.000 | Bộ nhớ, phân mảnh, thời gian xây chỉ mục |
| Số chiều | 768 | Chi phí lưu trữ và tính khoảng cách |
| Định dạng | Float32 | 4 byte cho mỗi chiều, trước overhead |
| Số kết quả | \`topK = 10\` | Số láng giềng cần trả về |
| Lọc bắt buộc | \`tenantId\`, quyền truy cập tài liệu | Tính đúng đắn và bảo mật |
| Thời gian phản hồi | Có mục tiêu p95 riêng của sản phẩm | Cấu hình mức tìm kiếm và tài nguyên |
| Tần suất cập nhật | Thêm, sửa, xóa tài liệu mỗi ngày | Freshness, cập nhật/rebuild chỉ mục |

Các giá trị trên là **giả định để giải thích phương pháp**, không phải thông số mặc định của một sản phẩm vector database.

## 2. Từ embedding đến khoảng cách giữa hai vector

### 2.1. Vector embedding

Một embedding là một dãy số:

\[
\mathbf{x} = (x_1, x_2, \ldots, x_d)
\]

Trong đó \`d\` là số chiều. Một mô hình embedding được huấn luyện để các đối tượng có quan hệ ngữ nghĩa phù hợp nằm gần nhau theo một phép đo tương ứng.

Ví dụ hình dung hai vector hai chiều:

~~~text
Tài liệu A: (0.9, 0.1)
Tài liệu B: (0.8, 0.2)
Tài liệu C: (-0.7, -0.5)
Truy vấn Q: (1.0, 0.0)
~~~

Theo trực giác hình học, A và B gần Q hơn C. Trong thực tế, một vector có thể có vài trăm đến hàng nghìn chiều; không thể dựa vào hình vẽ 2D để biết mức gần nghĩa chính xác.

### 2.2. Các phép đo phổ biến

**Khoảng cách Euclid (L2):**

\[
d_{L2}(\mathbf{q},\mathbf{x}) =
\sqrt{\sum_{i=1}^{d}(q_i-x_i)^2}
\]

Khoảng cách **càng nhỏ** thì vector càng gần.

**Tích vô hướng (dot product / inner product):**

\[
s_{\mathrm{dot}}(\mathbf{q},\mathbf{x}) =
\sum_{i=1}^{d} q_i x_i
\]

Khi dùng làm độ tương đồng, điểm **càng lớn** thường càng tốt. Độ lớn vector ảnh hưởng đến điểm dot product.

**Cosine similarity:**

\[
s_{\cos}(\mathbf{q},\mathbf{x}) =
\frac{\mathbf{q}\cdot\mathbf{x}}
{\|\mathbf{q}\|_2 \|\mathbf{x}\|_2}
\]

Cosine đo độ tương đồng về **hướng**, không chỉ độ lớn. Cosine distance thường được biểu diễn là \`1 - cosine_similarity\`, nhưng các API có thể quy định điểm trả về khác nhau.

| Phép đo | Tối ưu theo | Cần chú ý |
| --- | --- | --- |
| L2 | Khoảng cách nhỏ nhất | Nhạy với cả hướng và độ lớn vector |
| Dot product | Điểm tích vô hướng lớn nhất | Vector có norm lớn có thể chiếm ưu thế |
| Cosine | Góc giữa hai vector | Cần xử lý vector có norm bằng 0; kiểm tra chuẩn hóa |

**Hệ quả quan trọng:** chọn sai metric làm thay đổi thứ tự láng giềng, dù chỉ mục ANN được xây rất tốt. Metric phải phù hợp với mô hình embedding và tiêu chí mà ứng dụng cần đo.

### 2.3. Chuẩn hóa vector

Với vector khác vector không, phép chuẩn hóa L2:

\[
\hat{\mathbf{x}} = \frac{\mathbf{x}}{\|\mathbf{x}\|_2}
\]

đưa vector về norm 1. Khi cả truy vấn và tài liệu đều có norm 1:

\[
\hat{\mathbf{q}}\cdot\hat{\mathbf{x}}
= \operatorname{cosine}(\mathbf{q},\mathbf{x})
\]

và:

\[
\|\hat{\mathbf{q}}-\hat{\mathbf{x}}\|_2^2
= 2 - 2(\hat{\mathbf{q}}\cdot\hat{\mathbf{x}})
\]

Do đó, **trên vector đã chuẩn hóa**, xếp hạng theo cosine, dot product và L2 tương đương về thứ tự nếu không có yếu tố khác. Không được áp dụng kết luận này cho vector chưa chuẩn hóa hoặc vector không hợp lệ. Nếu một thư viện tự chuẩn hóa còn thư viện khác không tự làm, benchmark cần áp dụng cùng quy tắc để có kết quả so sánh công bằng.

## 3. Tìm kiếm chính xác (exact kNN) và gần đúng (ANN)

### 3.1. Exact kNN

Với câu hỏi \`q\`, tập \`N\` vector dữ liệu \`x1 ... xN\` và \`k = 10\`, **exact k-nearest neighbors** tính điểm theo metric cho mọi ứng viên hợp lệ rồi chọn 10 vector tốt nhất.

~~~text
INPUT: vector truy vấn q, dữ liệu X, số kết quả k

scores = []
FOR each vector x IN X:
    scores.ADD(distance_or_similarity(q, x))

RETURN k phần tử đứng đầu theo metric đã chọn
~~~

Nếu mỗi vector có \`d\` chiều, việc tính khoảng cách cho \`N\` vector cần lượng phép tính xấp xỉ tỷ lệ với:

\[
O(Nd)
\]

Chưa tính chi phí chọn top-\`k\`, lọc metadata, đọc dữ liệu từ bộ nhớ/đĩa và vận chuyển kết quả. Khi \`N\` lớn, việc đọc qua toàn bộ vector cho từng truy vấn có thể là nút thắt, dù thực hiện phép nhân vector rất hiệu quả trên CPU/GPU.

Exact kNN vẫn có những ưu điểm:

- Trả về **đúng top-\`k\` theo metric** và tập dữ liệu được xét, trong phạm vi sai số số học.
- Không phải điều chỉnh mức tìm kiếm gần đúng.
- Dùng làm **đường chuẩn (ground truth)** để đánh giá ANN.
- Có thể đủ nhanh cho tập dữ liệu nhỏ, tập đã lọc hẹp hoặc workload xử lý theo batch trên phần cứng phù hợp.

Không nên mặc định ANN luôn tốt hơn exact: nếu sau khi lọc chỉ còn 200 vector, tính chính xác trên 200 ứng viên có thể đơn giản và hiệu quả hơn duy trì một cấu trúc ANN lớn.

### 3.2. ANN

Thay vì tính khoảng cách tới tất cả vector, ANN dùng cấu trúc chỉ mục để ưu tiên những vùng hoặc những đường đi có khả năng chứa láng giềng gần nhất.

~~~mermaid
flowchart TD
    Q["Vector truy vấn q"] --> S{"Phương pháp tìm kiếm"}
    S -->|Exact| A["So điểm với tất cả ứng viên hợp lệ"]
    S -->|ANN| B["Chọn vùng/cạnh/ứng viên có triển vọng"]
    B --> C["Tính điểm trên tập ứng viên nhỏ hơn"]
    A --> D["Top-k chính xác"]
    C --> E["Top-k gần đúng"]
    E --> F["So với exact để đo recall@k"]
~~~

Ưu điểm thường hướng tới là **độ trễ thấp hơn hoặc throughput cao hơn với tài nguyên giới hạn**. Đổi lại, tập ứng viên mà ANN xem xét có thể bỏ sót một hoặc nhiều vector thuộc top-\`k\` chính xác.

Mức mất mát tùy thuật toán, tham số, phân bố vector, metric, số chiều, bộ lọc và ngân sách truy vấn. Không có một con số “ANN đúng 95%” áp dụng cho mọi dữ liệu và cấu hình.

## 4. Các họ chỉ mục vector thường gặp

Có nhiều cách lập chỉ mục; ba nhóm quan trọng để hiểu trade-off là **đồ thị lân cận HNSW**, **phân cụm IVF** và **nén vector bằng quantization/PQ**. Một số hệ kết hợp nhiều kỹ thuật hoặc tối ưu cho SSD/GPU.

### 4.1. HNSW: tìm kiếm qua mạng láng giềng

**Hierarchical Navigable Small World (HNSW)** xây dựng một cấu trúc đồ thị nhiều lớp. Mỗi vector là một đỉnh; các cạnh nối tới những vector lân cận theo quy tắc xây dựng đồ thị.

Khi truy vấn, thuật toán thường bắt đầu ở lớp trên với ít đỉnh hơn, di chuyển tới những vị trí có triển vọng, rồi xuống các lớp dưới để mở rộng tập láng giềng.

~~~mermaid
flowchart TD
    Q["Vector truy vấn"] --> L2["Lớp trên: ít nút, tìm vùng gần"]
    L2 --> L1["Lớp trung gian: điều hướng"]
    L1 --> L0["Lớp đáy: mở rộng ứng viên"]
    L0 --> TOP["Chọn k láng giềng tốt nhất đã tìm"]
~~~

Những tham số hay gặp trong các thư viện HNSW:

| Tham số | Vai trò | Tăng tham số thường có hệ quả gì? |
| --- | --- | --- |
| \`M\` | Giới hạn/định hướng số liên kết láng giềng khi xây đồ thị | Có thể cải thiện đường tìm nhưng tốn thêm RAM và thời gian xây dựng |
| \`efConstruction\` | Quy mô tập ứng viên khi thêm vector vào chỉ mục | Có thể tăng chất lượng cấu trúc đồ thị nhưng xây lâu hơn |
| \`efSearch\` hoặc \`ef\` | Quy mô tập ứng viên duy trì lúc tìm kiếm | Thường tăng recall, đồng thời tăng CPU và latency |

Tên và ngữ nghĩa chi tiết có thể khác giữa HNSWlib, Faiss, các vector database hoặc sản phẩm tích hợp ANN. Không nên coi \`M\` là đúng bằng số cạnh vật lý của mọi đỉnh; HNSW có nhiều lớp và chính sách liên kết riêng.

**Ưu điểm thường gặp:** recall tốt ở độ trễ thấp trên nhiều workload, linh hoạt điều chỉnh tham số truy vấn, phù hợp khi chỉ mục có thể nằm trong bộ nhớ hoặc trong kiến trúc hỗ trợ tương ứng.

**Đánh đổi:** tốn bộ nhớ cho đồ thị và vector, thời gian xây dựng có thể đáng kể, cập nhật/xóa lượng lớn hoặc phân mảnh dữ liệu có thể cần tối ưu lại hay rebuild tùy engine.

### 4.2. IVF: tìm trong một số cụm gần truy vấn

**Inverted File Index (IVF)** chia không gian vector thành các nhóm/cụm bằng những điểm đại diện (*centroids*). Khi truy vấn:

1. Xác định những centroid gần vector truy vấn.
2. Chỉ xét các danh sách vector thuộc những cụm đã chọn.
3. Tính điểm và chọn top-\`k\`.

~~~text
Toàn bộ vector
  ├── Cụm 0: x1, x8, x20, ...
  ├── Cụm 1: x2, x3, x31, ...
  ├── Cụm 2: x4, x19, ...
  └── Cụm N: ...

Truy vấn q
  -> chọn một số cụm gần q
  -> so điểm trong các cụm đó
  -> lấy top-k
~~~

Hai tham số thường gặp:

- **\`nlist\`**: số cụm/danh sách được tạo.
- **\`nprobe\`**: số cụm được tra khi truy vấn.

Nếu \`nprobe\` thấp, truy vấn nhanh hơn vì ít vector được xem xét, nhưng có thể bỏ sót láng giềng nằm ở cụm sát ranh giới. Tăng \`nprobe\` thường cải thiện recall với chi phí tính điểm và đọc dữ liệu cao hơn.

**IVF-Flat** lưu vector đầy đủ trong các danh sách. **IVF-PQ** kết hợp phân cụm với mã nén vector để giảm bộ nhớ; đổi lại việc so điểm có thêm sai số xấp xỉ.

IVF thường cần bước **huấn luyện centroid** trên tập vector đại diện. Nếu dữ liệu thay đổi phân bố đáng kể theo thời gian, centroid cũ có thể không còn phù hợp, dẫn tới nhu cầu huấn luyện lại/rebuild.

### 4.3. PQ và các hình thức lượng tử hóa

Vector Float32 có \`d\` chiều cần xấp xỉ \`4d\` byte cho dữ liệu số thô. Khi số vector lớn, phần lưu vector đã có thể chiếm hàng chục GB trước khi tính chỉ mục.

**Product Quantization (PQ)** chia vector thành nhiều đoạn con và mã hóa mỗi đoạn bằng mã trỏ đến một centroid trong codebook. Thay vì lưu mọi số Float32, hệ thống có thể lưu một chuỗi mã ngắn hơn.

Ví dụ minh họa:

~~~text
Vector gốc 768 chiều Float32:
  768 × 4 = 3.072 byte/vector

Chia thành 96 subvector, mỗi subvector có 256 mã:
  96 × 1 byte = 96 byte mã/vector
~~~

Đây là so sánh **phần dữ liệu vector và mã PQ thuần**, chưa bao gồm codebook, ID, centroid, vector dư, metadata, các lớp đồ thị hoặc bản sao. PQ có thể giảm đáng kể dung lượng vector cần xét, nhưng khoảng cách tính trên mã nén chỉ là **ước lượng** so với vector gốc.

Các phương án liên quan:

| Cách lưu/tính | Ý nghĩa | Đánh đổi |
| --- | --- | --- |
| Float32 | Vector đầy đủ, 4 byte/chiều | Dễ so điểm, tốn RAM/dung lượng |
| Float16 | Khoảng 2 byte/chiều | Giảm dung lượng, có sai số số học, phụ thuộc engine |
| Scalar quantization (ví dụ int8) | Lượng tử hóa giá trị từng chiều | Tiết kiệm bộ nhớ, có sai số khi tính độ tương đồng |
| Product quantization | Mã hóa các phần vector bằng codebook | Nén mạnh hơn trong một số cấu hình, phải tính điểm gần đúng |
| PQ + rerank | Dùng mã nén để lấy ứng viên, so lại bằng vector đầy đủ | Tăng recall cuối, cần lưu/đọc vector gốc cho bước rerank |

Quantization không chỉ là “nén file”: nó có thể **đổi thứ tự láng giềng** vì điểm so khớp bị xấp xỉ. Nếu yêu cầu chất lượng cao, cần đo riêng ảnh hưởng của ANN search và sai số lượng tử hóa.

### 4.4. Chỉ mục tối ưu cho SSD hoặc cấu trúc lai

Khi dữ liệu không vừa RAM, một số kiến trúc ANN giữ một phần cấu trúc điều hướng trong bộ nhớ và phần vector/chỉ mục ở SSD, đồng thời dùng cache và đọc trước để giảm số I/O ngẫu nhiên.

Những hướng kiểu **disk-based ANN** có thể đánh đổi:

- Ít RAM hơn nhưng nhiều I/O và phụ thuộc latency SSD.
- Thời gian xây và công đoạn tối ưu dữ liệu có thể cao.
- Hiệu năng nhạy với cache hit, truy vấn đồng thời và đặc điểm phần cứng.

Không có một cấu hình HNSW, IVF-PQ hoặc disk-based ANN thắng mọi workload. Bảng dưới đây chỉ mô tả xu hướng thiết kế:

| Phương án | Điểm mạnh điển hình | Chi phí/rủi ro cần đo |
| --- | --- | --- |
| Exact Flat | Đường chuẩn chính xác, triển khai đơn giản | Phải xét nhiều vector mỗi truy vấn |
| HNSW | Truy hồi chất lượng cao với đường tìm đồ thị | RAM cho đồ thị, thời gian xây, bảo trì cập nhật |
| IVF-Flat | Tìm trong cụm, điều chỉnh bằng nprobe | Chất lượng phân cụm, quét nhiều khi tăng nprobe |
| IVF-PQ | Cân bằng ANN và nén vector | Sai số lượng tử hóa, huấn luyện codebook, rerank |
| Disk-based ANN | Dung lượng lớn hơn RAM có sẵn | Độ trễ I/O, cache và vận hành storage |

## 5. Độ chính xác truy hồi: Recall@k là gì?

Trong đánh giá **khả năng tìm đúng láng giềng gần nhất**, ta cần so kết quả ANN với tập top-\`k\` chính xác theo **cùng vector, cùng metric, cùng dữ liệu và cùng điều kiện lọc**.

Gọi:

- \`G_k(q)\`: tập ID của \`k\` láng giềng gần nhất theo exact search cho truy vấn \`q\`.
- \`A_k(q)\`: tập ID của \`k\` kết quả ANN cho cùng truy vấn.

Khi cả hai đều xét cùng tập dữ liệu hợp lệ và có đủ \`k\` phần tử:

\[
\operatorname{Recall@k}(q)
= \frac{|G_k(q) \cap A_k(q)|}{k}
\]

### 5.1. Ví dụ tính Recall@10

Tập top-10 chính xác:

~~~text
Ground truth:
  A, B, C, D, E, F, G, H, I, J
~~~

Kết quả ANN:

~~~text
ANN:
  A, B, C, D, E, F, G, H, X, Y
~~~

Hai tập có **8 ID chung** nên:

\[
\operatorname{Recall@10} = \frac{8}{10} = 0.8 = 80\%
\]

Nếu truy vấn khác có đủ 10/10 ID chung, recall là 100%. Nếu kết quả ANN chứa đúng 8 ID nhưng thứ tự khác ground truth, **set-based Recall@10 vẫn là 80%**: metric này chủ yếu đo **bao nhiêu láng giềng đúng được tìm thấy**, không trực tiếp thưởng/phạt thứ tự trong top-\`k\`.

### 5.2. Recall trung bình theo tập truy vấn

Với \`Q\` truy vấn đại diện:

\[
\operatorname{MeanRecall@k}
= \frac{1}{Q}
  \sum_{i=1}^{Q} \operatorname{Recall@k}(q_i)
\]

Ngoài trung bình, nên xem **phân bố recall theo truy vấn**:

- Query dễ có recall cao, query khó có recall thấp?
- Query thuộc tenant nhỏ và tenant lớn có khác nhau?
- Query cần lọc metadata rất chặt có bị hụt kết quả?
- Query thuộc ngôn ngữ hoặc chủ đề hiếm có recall thấp hơn?

Trung bình recall 95% vẫn có thể che giấu nhóm query quan trọng chỉ đạt 50%.

### 5.3. Đặt tên đúng cho con số “độ chính xác”

**ANN Recall@k không phải “95% câu trả lời đúng”.** Nó chỉ so **kết quả của chỉ mục gần đúng với kết quả exact theo metric**.

Có ít nhất ba tầng chất lượng:

| Tầng | Câu hỏi | Cách đánh giá |
| --- | --- | --- |
| **Độ đúng của ANN** | Chỉ mục có tìm đúng láng giềng exact không? | Recall@k đối chiếu exact kNN |
| **Độ liên quan của retrieval** | Những đoạn gần vector có hữu ích cho người đọc không? | Nhãn relevance, Precision@k, nDCG, MRR, Recall trên tài liệu liên quan |
| **Chất lượng ứng dụng/RAG** | Câu trả lời cuối có đúng và có căn cứ không? | Bộ câu hỏi có đáp án, kiểm tra trích dẫn, đánh giá chuyên môn |

Một embedding kém chất lượng có thể trả top-10 exact **không liên quan**, dù chỉ mục ANN đạt Recall@10 = 100%. Ngược lại, một kết quả ANN bỏ sót một láng giềng exact nhưng tìm được tài liệu khác phù hợp vẫn có thể hữu ích cho người dùng.

Vì thế, cần vừa đo **ANN recall** để lựa chọn cấu trúc chỉ mục, vừa đo **relevance/answer quality** để kiểm tra giá trị nghiệp vụ.

### 5.4. Các trường hợp cần quy ước trước khi đo

- **Điểm bằng nhau (ties):** nếu nhiều vector có cùng khoảng cách tại ranh giới top-\`k\`, các tập top-\`k\` đều có thể hợp lệ. Cần quy tắc tie-break hoặc metric đánh giá chấp nhận các kết quả đồng hạng.
- **Số ứng viên hợp lệ nhỏ hơn k:** mẫu số và cách tính phải được nêu rõ, ví dụ \`min(k, N_eligible)\`, để tránh đánh giá sai query lọc hẹp.
- **ID trùng:** cần chuẩn hóa kết quả theo ID đối tượng mong muốn; chunk ID và document ID không nhất thiết cùng đơn vị đánh giá.
- **Dữ liệu thay đổi:** exact và ANN phải sử dụng snapshot/cửa sổ dữ liệu tương ứng, nếu không recall bị méo do insert/delete.
- **Metric khác nhau:** không so exact dùng cosine với ANN dùng dot product trên vector chưa chuẩn hóa.
- **Hậu xử lý:** nếu dùng reranker, tách metric recall của bước ANN thô khỏi chất lượng thứ tự sau rerank.

## 6. Recall, độ trễ và chi phí tạo thành một bài toán đánh đổi

Thường có thể tăng recall bằng cách **xét nhiều ứng viên hơn**, nhưng điều đó làm tăng lượng tính toán và có thể tăng độ trễ.

Với HNSW:

~~~text
efSearch thấp
  -> ít ứng viên được mở rộng
  -> truy vấn thường nhanh hơn
  -> có thể bỏ sót nhiều láng giềng exact hơn

efSearch cao
  -> nhiều ứng viên được mở rộng
  -> recall thường tăng
  -> CPU và latency thường tăng
~~~

Với IVF:

~~~text
nprobe thấp -> tìm trong ít cụm -> nhanh hơn, có thể recall thấp hơn
nprobe cao  -> tìm trong nhiều cụm -> recall cao hơn, tốn tài nguyên hơn
~~~

### 6.1. Bảng thông số giả định

Giả sử một nhóm chạy benchmark HNSW trên tập vector riêng và nhận được các số **thuần minh họa** sau:

| \`efSearch\` | Mean Recall@10 | p95 latency/query | CPU/query (tương đối) |
| ---: | ---: | ---: | ---: |
| 20 | 0,82 | 12 ms | 1,0× |
| 50 | 0,93 | 22 ms | 1,8× |
| 100 | 0,97 | 39 ms | 3,1× |
| 200 | 0,99 | 73 ms | 5,7× |

Các số trên **không phải benchmark được đo trong bài**, cũng không phải cam kết của HNSW. Chúng minh họa cách lập bảng khi đo trên dữ liệu thật.

Nếu yêu cầu là \`Recall@10 >= 0,95\` và \`p95 <= 50 ms\`, cấu hình 100 trong bảng giả định có vẻ phù hợp; 50 không đạt recall, còn 200 vượt ngân sách latency. Tuy nhiên, phải xét thêm throughput, chi phí RAM, tail latency, độ mới dữ liệu và khả năng chịu đỉnh.

### 6.2. Đường Pareto

Một cấu hình **A trội hơn B** nếu A cho chất lượng ít nhất bằng B trong khi chi phí không cao hơn trên các tiêu chí đang xét, và tốt hơn ở ít nhất một tiêu chí. Tập những cấu hình không bị cấu hình khác trội hoàn toàn tạo thành **Pareto frontier**.

Ví dụ, trong khi một cấu hình đạt Recall@10 = 0,95 với 20 ms, cấu hình khác cũng đạt 0,95 nhưng mất 40 ms và dùng nhiều RAM hơn, thì cấu hình thứ hai không hấp dẫn nếu không có lợi thế vận hành khác.

Không nên tối ưu mỗi recall rồi bỏ qua chi phí; cũng không nên tối ưu chỉ số latency thấp nhất rồi chấp nhận bỏ sót nhiều kết quả quan trọng mà không đo tác động đến ứng dụng.

## 7. Phân tích chi phí lưu trữ và RAM

### 7.1. Dung lượng vector thô

Với \`N\` vector, \`d\` chiều và \`b\` byte mỗi chiều:

\[
S_{\text{raw}} = N \times d \times b
\]

Với 1 triệu vector 768 chiều ở Float32:

~~~text
N = 1.000.000
d = 768
b = 4 byte

S_raw = 1.000.000 × 768 × 4
      = 3.072.000.000 byte
      ≈ 3,072 GB (đơn vị thập phân)
      ≈ 2,861 GiB (đơn vị nhị phân)
~~~

Nếu tăng lên **10 triệu vector** mà giữ cùng chiều và định dạng:

~~~text
10.000.000 × 768 × 4
  = 30.720.000.000 byte
  ≈ 30,72 GB
  ≈ 28,61 GiB
~~~

Đây mới là **dung lượng vector thô**, chưa phải yêu cầu RAM thực tế hay dung lượng toàn hệ thống.

### 7.2. Các thành phần cần cộng thêm

Ước lượng đầy đủ hơn:

~~~text
Dung lượng mỗi bản sao ≈
    vector được lưu
  + cấu trúc ANN (cạnh graph / centroid / posting list / codebook)
  + ID và metadata
  + index/filter phụ
  + dữ liệu văn bản/đối tượng nếu lưu cùng hệ
  + overhead của engine và allocator
  + headroom cho cập nhật, compact và rebuild

Dung lượng toàn cụm ≈
    tổng dung lượng từng shard và replica
  + snapshot/backup theo chính sách
  + overhead vận hành và dữ liệu tạm
~~~

Ví dụ, nếu mỗi bản sao chứa toàn bộ vector Float32 như trên và có **3 bản sao đầy đủ**, riêng phần vector thô là:

~~~text
3 × 3,072 GB = 9,216 GB
~~~

Hệ thống có thể còn lưu vector ở nhiều định dạng (bản gốc và bản nén), hoặc đặt index trong RAM và dữ liệu gốc trên SSD. Vì vậy **số byte vector × số replica không đủ để dự báo RAM**. Cần xem kiến trúc cụ thể và metric resident memory/working set.

### 7.3. Chi phí HNSW

Ngoài vector, HNSW lưu danh sách các cạnh láng giềng và dữ liệu điều hướng. Một ước lượng rất thô:

~~~text
Đồ thị cạnh ≈ số vector × số cạnh lưu trung bình × byte mỗi tham chiếu
~~~

Ví dụ minh họa: \`1.000.000 × 16 × 8 = 128.000.000 byte\` nếu giả sử trung bình 16 tham chiếu, mỗi tham chiếu 8 byte. Nhưng số này **không phải công thức bộ nhớ HNSW thực tế**: còn nhiều lớp, bộ nhớ cấp phát, cấu trúc nội bộ, metadata và mức liên kết khác nhau. Dùng nó để hiểu rằng số cạnh ảnh hưởng đến RAM, không dùng để mua máy.

### 7.4. Chi phí mã nén

Với PQ gồm 96 subvector và mã 8 bit/subvector:

~~~text
Mã PQ cho 1.000.000 vector = 1.000.000 × 96 byte
                           = 96.000.000 byte
                           ≈ 91,55 MiB
~~~

So với **3.072.000.000 byte** Float32 gốc, phần mã vector nhỏ hơn đáng kể. Tuy nhiên, nếu hệ thống vẫn giữ vector đầy đủ để rerank hoặc phục vụ xuất dữ liệu, phần dung lượng gốc vẫn tồn tại ở đâu đó.

### 7.5. Chi phí lưu trữ không độc lập với độ mới

Nếu phải xây lại chỉ mục trong khi phiên bản cũ vẫn phục vụ truy vấn, có thể cần không gian cho **hai thế hệ chỉ mục** trong giai đoạn chuyển đổi. Khi cập nhật/xóa nhiều, có thể xuất hiện tombstone, vùng trống, bảng delta hoặc bộ nhớ dành cho merge/rebuild.

Một cấu hình “vừa đủ RAM ở trạng thái ổn định” chưa chắc đủ RAM khi **rolling rebuild, load cao, failover hoặc thay thế replica**.

## 8. Chi phí CPU, thời gian xây và cập nhật chỉ mục

ANN thường giảm công việc truy vấn bằng cách làm thêm một số công việc **trước khi truy vấn**:

| Giai đoạn | Công việc | Chi phí có thể phát sinh |
| --- | --- | --- |
| Embedding | Chuyển dữ liệu và truy vấn thành vector | CPU/GPU, API embedding, tiền xử lý |
| Train index | Học centroid/codebook ở IVF/PQ | CPU/GPU, dữ liệu mẫu, thời gian huấn luyện |
| Build/add | Thêm vector vào cấu trúc graph/list | CPU, RAM, I/O, tăng độ trễ ingestion |
| Query | Tìm ứng viên và tính điểm | CPU/GPU, RAM/SSD, request latency |
| Filter + rerank | Lọc quyền/metadata, so lại ứng viên | CPU, đọc dữ liệu gốc, tăng thời gian xử lý |
| Update/delete | Thay vector, đánh dấu xóa, cập nhật index | Phân mảnh, độ trễ hiển thị, chi phí rebuild |
| Replicate/backup | Duy trì nhiều bản sao và khôi phục | Dung lượng, network, thời gian phục hồi |

Các tham số như \`efConstruction\` cao hoặc số centroid lớn có thể làm **xây chỉ mục lâu hơn**, bù lại hỗ trợ tìm kiếm tốt hơn ở một số workload. Cần đo **thời gian build ban đầu** và **tốc độ cập nhật liên tục**, không chỉ thời gian mỗi query sau khi index đã sẵn sàng.

### 8.1. Workload đọc nhiều và ghi nhiều

Một index có thể rất phù hợp cho **kho tài liệu ít thay đổi**, nhưng kém phù hợp nếu mỗi giây phải thay thế hàng chục nghìn vector. Cần đặt câu hỏi:

- Có hỗ trợ thêm vector trực tiếp (*online insertion*) không?
- Khi xóa, vector biến mất ngay khỏi kết quả hay chỉ bị đánh dấu?
- Cập nhật embedding là sửa tại chỗ hay xóa rồi thêm?
- Index có cần rebuild định kỳ để duy trì chất lượng/tốc độ không?
- Search có nhìn thấy dữ liệu mới ngay hay sau một khoảng trễ?

HNSW của từng thư viện có cách quản lý xóa khác nhau; IVF/PQ có thể cần huấn luyện lại khi phân bố embedding thay đổi. Không nên suy diễn khả năng **real-time update** chỉ từ tên thuật toán.

### 8.2. Cập nhật mô hình embedding làm thay đổi toàn bộ không gian

Giả sử hệ thống chuyển từ \`embedding-model-v1\` sang \`embedding-model-v2\`. Dù cùng 768 chiều, vector mới **không mặc nhiên so sánh được** với vector cũ.

Một quy trình chuyển đổi thường cần:

1. Ghi version mô hình embedding cùng tài liệu và index.
2. Tạo lại embedding cho dữ liệu theo mô hình mới.
3. Xây chỉ mục thế hệ mới, giữ index cũ phục vụ query khi cần.
4. Chạy đánh giá recall và chất lượng retrieval trên tập truy vấn đại diện.
5. Chuyển luồng truy vấn sang mô hình mới theo kế hoạch, theo dõi chất lượng.
6. Xóa chỉ mục cũ khi đã an toàn và đáp ứng chính sách dữ liệu.

Đưa vector của hai mô hình không tương thích vào cùng một index để tính khoảng cách có thể tạo kết quả vô nghĩa, ngay cả khi hệ quản trị chấp nhận cùng kích thước.

## 9. Bộ lọc metadata có thể làm thay đổi recall và chi phí

Trong kho tri thức nhiều tenant, một truy vấn thường yêu cầu:

~~~text
tenantId = "org-a"
AND visibility = "PUBLIC_OR_AUTHORIZED"
AND language = "vi"
~~~

Chỉ mục phải tìm được vector **gần truy vấn và đồng thời hợp lệ theo bộ lọc**.

### 9.1. Pre-filter và post-filter

Hai cách xử lý khái niệm:

**Pre-filter (lọc trước/tích hợp khi truy vấn):**

~~~text
1. Xác định tập vector thuộc tenant/ngôn ngữ/quyền hợp lệ.
2. Tìm top-k gần nhất trong tập hợp lệ.
~~~

**Post-filter (lọc sau khi lấy ứng viên):**

~~~text
1. ANN lấy một nhóm ứng viên gần truy vấn từ tập rộng.
2. Loại ứng viên không thỏa điều kiện.
3. Trả các ứng viên còn lại.
~~~

Trong thực tế, nhiều engine có cơ chế **lọc trong khi traversal**, bitset, partition/shard theo tenant, hoặc kết hợp pre/post-filter. Tên gọi trên chỉ giúp so sánh hai cực.

### 9.2. Rủi ro thiếu kết quả khi lọc sau

Giả sử chỉ **1% vector** thuộc tenant được phép. ANN tìm 10 ứng viên gần nhất toàn cục rồi lọc theo tenant. Có thể chỉ 0 hoặc 1 ứng viên thuộc tenant, dù bên trong tenant vẫn có rất nhiều tài liệu phù hợp.

Để tìm đủ \`topK = 10\`, ta có thể tăng số ứng viên ban đầu (*overfetch*) lên 100, 500 hoặc hơn. Nhưng overfetch làm tăng CPU, RAM tạm, độ trễ và vẫn **không bảo đảm** đủ kết quả nếu tập hợp lệ rất nhỏ hoặc phân bố vector lệch.

**Đường chuẩn đúng khi có filter** là exact kNN **chỉ trên tập dữ liệu được phép**. Nếu lấy exact top-10 toàn cục rồi đem so với ANN top-10 có filter, phép đo recall không cùng điều kiện và không có ý nghĩa.

### 9.3. Lọc quyền là yêu cầu bắt buộc

Bất kể index chọn prefilter hay postfilter về mặt thuật toán, API **chỉ được trả nội dung và metadata mà người dùng có quyền truy cập**. Không gửi ID/tên/đoạn trích của tài liệu không được phép ra client chỉ để cho client lọc tiếp.

Nếu quyền có thể thay đổi giữa lúc xây index và lúc trả kết quả, hệ thống cần có cơ chế kiểm tra quyền tại thời điểm phục vụ và chính sách nhất quán phù hợp. ANN recall không quan trọng hơn việc không lộ dữ liệu của tenant khác.

### 9.4. Partition hay shard theo tenant?

Với tenant nhỏ, có thể lưu nhiều tenant trong một index rồi lọc theo thuộc tính. Với tenant lớn hoặc yêu cầu cách ly cao, có thể cân nhắc partition/index riêng. Đánh đổi:

| Chiến lược | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- |
| Index chung, lọc metadata | Dễ chia sẻ tài nguyên, ít index nhỏ | Bộ lọc rất chọn lọc có thể làm giảm hiệu suất và recall |
| Index riêng theo tenant | Cách ly dữ liệu và định tuyến rõ | Nhiều index, overhead vận hành và phân bổ tài nguyên |
| Chia nhóm/shard có kiểm soát | Cân bằng cách ly và quy mô | Fan-out, routing và merge top-k phức tạp |

Không nên tự chia thành hàng nghìn index cực nhỏ nếu mỗi index chỉ chứa rất ít vector và hệ thống phải duy trì nhiều cấu trúc quản lý. Hãy đo theo phân bố tenant thực tế.

## 10. Reranking và tìm kiếm lai

ANN có thể rất tốt trong việc chọn **ứng viên**, nhưng thứ tự cuối chưa chắc tối ưu cho người dùng.

Một pipeline phổ biến:

~~~text
Câu hỏi
  -> embedding
  -> ANN top-100
  -> lọc dữ liệu được phép
  -> rerank top-100 bằng mô hình/metric chi tiết hơn
  -> chọn top-10 hiển thị hoặc dùng làm RAG context
~~~

**Rerank bằng vector gốc:** nếu index nén PQ, có thể lấy 100 ứng viên bằng mã nén rồi tính lại điểm chính xác trên vector gốc. Việc này thường cải thiện thứ tự **trong tập ứng viên đã tìm được**, nhưng không tự cứu được một vector tốt đã bị ANN bỏ sót ngay từ bước tìm ứng viên.

**Rerank ngữ nghĩa:** mô hình cross-encoder hoặc mô hình relevance khác có thể đánh giá cặp *truy vấn–đoạn tài liệu* sâu hơn. Chi phí tính toán thường cao hơn mỗi cặp so với khoảng cách vector, nên chỉ dùng trên một nhóm ứng viên giới hạn.

**Tìm kiếm lai (hybrid search):** kết hợp vector search với tìm kiếm từ khóa/BM25. Ví dụ:

- Query “cách xử lý yêu cầu hoàn tiền” cần ngữ nghĩa, ANN có thể hữu ích.
- Query chứa mã lỗi \`ERR-4027\` hoặc số hợp đồng chính xác thường được hỗ trợ tốt bởi tìm kiếm từ khóa.
- Kết hợp hai nhánh có thể dùng điểm chuẩn hóa, weighted fusion hoặc Reciprocal Rank Fusion (RRF), tùy hệ thống.

Chi phí pipeline tăng khi thêm nhánh tìm kiếm, tăng số ứng viên hoặc dùng reranker. Nên đo **end-to-end latency và chất lượng thực tế**, không chỉ latency của API vector search.

## 11. Thực nghiệm Python: xây HNSW và đo Recall@10

Để thấy rõ recall thay đổi theo \`efSearch\`, ta có thể so kết quả HNSW với exact kNN trên **cùng bộ vector thử nghiệm**.

Thực nghiệm sau dùng thư viện:

- \`numpy\` để sinh vector, chuẩn hóa và tính exact top-\`k\`.
- \`hnswlib\` để xây chỉ mục HNSW và truy vấn.
- \`time.perf_counter\` để đo thời gian từ phía chương trình.

**Đây là đoạn mã thực hành được cung cấp để chạy trong môi trường học tập; số liệu phải lấy từ kết quả chạy thật trên máy của người học.** Dữ liệu được sinh ngẫu nhiên để hiểu cách đo chỉ mục, chưa đại diện cho phân bố embedding thực tế.

### 11.1. Cài đặt

Với Python 3.10+:

~~~bash
python -m pip install numpy hnswlib
~~~

Thư viện \`hnswlib\` có thành phần biên dịch native; một số hệ điều hành có thể cần công cụ build hoặc wheel tương thích.

### 11.2. Chương trình đánh giá

Tạo file \`ann_recall_lab.py\`:

~~~python
import time
import numpy as np
import hnswlib

SEED = 42
N = 20_000
DIM = 128
QUERY_COUNT = 100
K = 10

rng = np.random.default_rng(SEED)


def unit_normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-12)


# Float32, cùng số chiều; vector có norm ~1.
base = unit_normalize(
    rng.normal(size=(N, DIM)).astype(np.float32)
)
queries = unit_normalize(
    rng.normal(size=(QUERY_COUNT, DIM)).astype(np.float32)
)

# Exact top-k theo cosine:
# Vì tất cả vector đã được chuẩn hóa, dot product có cùng xếp hạng.
exact_start = time.perf_counter()
scores = queries @ base.T
exact_ids = np.argsort(-scores, axis=1)[:, :K]
exact_ms = (time.perf_counter() - exact_start) * 1000

# Chỉ mục HNSW với cùng metric.
index = hnswlib.Index(space="cosine", dim=DIM)
build_start = time.perf_counter()
index.init_index(
    max_elements=N,
    M=16,
    ef_construction=200,
    random_seed=SEED,
)
index.add_items(base, np.arange(N), num_threads=1)
build_seconds = time.perf_counter() - build_start

print(f"Vectors: {N}, dim: {DIM}, queries: {QUERY_COUNT}, k: {K}")
print(f"Exact total for {QUERY_COUNT} queries: {exact_ms:.1f} ms")
print(f"HNSW build: {build_seconds:.2f} s")


for ef in (10, 40, 120):
    index.set_ef(ef)
    query_recalls = []
    query_latencies_ms = []

    for i, q in enumerate(queries):
        started = time.perf_counter()
        labels, distances = index.knn_query(
            q.reshape(1, -1),
            k=K,
            num_threads=1,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        query_latencies_ms.append(latency_ms)

        ground_truth = set(exact_ids[i].tolist())
        ann_results = set(labels[0].tolist())
        query_recalls.append(len(ground_truth & ann_results) / K)

    print(
        f"ef={ef:3} | "
        f"mean_recall@{K}={np.mean(query_recalls):.3f} | "
        f"mean_ms={np.mean(query_latencies_ms):.3f} | "
        f"p95_ms={np.percentile(query_latencies_ms, 95):.3f}"
    )
~~~

Chạy:

~~~bash
python ann_recall_lab.py
~~~

### 11.3. Cách đọc kết quả

Chương trình sẽ in:

~~~text
Vectors: 20000, dim: 128, queries: 100, k: 10
Exact total for 100 queries: ...
HNSW build: ... s
ef= 10 | mean_recall@10=... | mean_ms=... | p95_ms=...
ef= 40 | mean_recall@10=... | mean_ms=... | p95_ms=...
ef=120 | mean_recall@10=... | mean_ms=... | p95_ms=...
~~~

Những dấu \`...\` **phải được thay bằng kết quả thực tế khi chạy**, không có một giá trị cố định cho mọi máy. Thông thường \`ef\` cao hơn có xu hướng tăng recall và tốn thêm thời gian tìm kiếm, nhưng mẫu ngẫu nhiên nhỏ, thời gian warmup, cache và nhiễu hệ thống có thể khiến kết quả không tăng đều tuyệt đối.

Điều quan trọng trong chương trình:

1. **Exact ground truth** được tính bằng điểm \`queries @ base.T\` trên vector đã chuẩn hóa.
2. **ANN dùng \`space="cosine"\`**, khớp với mục tiêu xếp hạng của exact.
3. **ID vector được gán ổn định** từ \`0\` đến \`N-1\`, nên có thể so tập ID.
4. **\`ef\` thay đổi lúc query**, còn cấu trúc đồ thị và vector giữ nguyên.
5. Kết quả đo **truy vấn HNSW trong cùng tiến trình**, chưa gồm HTTP, truy vấn metadata, mạng, filter, storage service hay reranker.

### 11.4. Giới hạn của phép thực nghiệm

- Vector được sinh ngẫu nhiên, không phản ánh sự phân bố có cụm, mất cân bằng hoặc tương quan của embedding tài liệu.
- 20.000 vector 128 chiều nhỏ hơn nhiều so với 1 triệu vector 768 chiều của tình huống nghiệp vụ.
- Chưa có insert/delete trong lúc truy vấn, chưa có tenant filter.
- Đo một request HNSW mỗi lần, không mô phỏng tải từ nhiều client đồng thời.
- Không có số đo RAM chính xác của index; với dữ liệu lớn phải đo resident memory/peak memory ở mức tiến trình.
- Kết quả exact \`numpy\` và ANN \`hnswlib\` không phải benchmark công bằng về tối ưu phần cứng khi dùng để chọn sản phẩm, vì cả hai có các kiểu thực thi khác nhau.

Chương trình này nhằm **giúp hiểu cách đo Recall@k và ảnh hưởng của efSearch**, không dùng làm cơ sở duy nhất để chọn engine trong production.

## 12. Mở rộng thực nghiệm: đánh giá IVF và lượng tử hóa

Với IVF, một quy trình thực nghiệm tương đương:

~~~text
Tập vector gốc
  -> lấy tập huấn luyện đại diện
  -> train centroid (nlist)
  -> add vector vào IVF index
  -> đặt nprobe
  -> search top-k
  -> so với exact top-k
  -> ghi recall, p95, QPS, peak RAM
~~~

Để đánh giá IVF-PQ, cần ghi thêm **kích thước mã PQ**, sai số do quantization và tác động của bước rerank. Một bảng kết quả nên phân biệt:

| Kịch bản | Tham số điều chỉnh | Chỉ số cần quan sát |
| --- | --- | --- |
| Exact Flat | Batch size, CPU/GPU | Recall quy ước 100%, latency, throughput |
| HNSW | \`M\`, \`efConstruction\`, \`efSearch\` | Recall, build time, RAM, latency |
| IVF-Flat | \`nlist\`, \`nprobe\` | Recall, phân bố cụm, train/build time, latency |
| IVF-PQ | \`nlist\`, \`nprobe\`, mã PQ | Recall, bytes/vector, latency, chi phí rerank |
| Index trên SSD | Cache, mức I/O, concurrency | p95/p99, SSD IOPS, RAM, hit rate |

Đừng so hai cấu hình ở hai metric khác nhau hoặc khác tập lọc rồi quy kết chênh lệch là do thuật toán.

## 13. Thiết kế một benchmark gần với production

Một benchmark hữu ích cần đại diện cho **dữ liệu, truy vấn, bộ lọc và thời gian hoạt động thực tế**.

### 13.1. Chuẩn bị dữ liệu

Trước khi xây chỉ mục:

- Lấy embedding từ **đúng model và version dự kiến sử dụng**.
- Dùng dữ liệu đã loại trùng, làm sạch và chia đoạn theo quy tắc ứng dụng thật.
- Giữ metadata cần lọc: \`tenantId\`, \`language\`, \`documentType\`, \`visibility\`, \`updatedAt\`.
- Bảo đảm ID ổn định và có quy tắc xử lý khi một document bị sửa hay xóa.
- Dùng một tập dữ liệu đủ lớn để xuất hiện tenant lớn, chủ đề phổ biến và bản ghi dài/hiếm.

**Tách tập train và tập evaluation nếu thuật toán có bước huấn luyện centroid/codebook**, để tránh chọn tham số dựa hoàn toàn vào cùng một tập query dùng tối ưu.

### 13.2. Tập truy vấn đại diện

Không chỉ sinh query ngẫu nhiên. Hãy đưa vào:

- Query phổ biến, query hiếm và query dài.
- Query có từ khóa chính xác (mã tài liệu, số lỗi) và query diễn đạt ngữ nghĩa.
- Query nhiều ngôn ngữ nếu sản phẩm hỗ trợ.
- Query của tenant lớn và tenant nhỏ.
- Query lọc hẹp theo quyền, loại tài liệu hoặc thời gian.
- Query không có tài liệu phù hợp về mặt nghiệp vụ.

Tập kiểm thử nên được thu thập theo cách tôn trọng quyền và dữ liệu cá nhân, sau đó được **ẩn danh hoặc tổng hợp** phù hợp.

### 13.3. Tạo ground truth

Với mỗi query:

1. Xác định **tập vector được phép** theo filter và snapshot.
2. Tính điểm theo **metric chính thức** với đủ độ chính xác số học.
3. Lấy top-\`k\` exact làm ground truth của ANN.
4. Lưu ID và (nếu cần) điểm/tie-break để tái lập phép đo.
5. Đo ANN recall trên cùng tập dữ liệu và chính sách lọc.

Nếu N quá lớn để exact trên một máy, có thể chạy tính điểm theo batch trên CPU/GPU rồi hợp nhất top-\`k\` chính xác của các batch. Tuyệt đối không lấy một thuật toán ANN khác làm “ground truth tuyệt đối” nếu chưa biết độ chính xác của nó.

### 13.4. Đo chất lượng và chi phí cùng nhau

Một bảng benchmark tối thiểu:

| Nhóm | Chỉ số |
| --- | --- |
| ANN quality | Mean Recall@10, p10 recall theo query, tỷ lệ query recall thấp |
| Search latency | p50/p95/p99 end-to-end và riêng index search |
| Throughput | QPS ở các mức client concurrency |
| Search resource | CPU, RAM, disk I/O, network |
| Index footprint | Bytes/vector, tổng dung lượng, số replica |
| Build/update | Thời gian build, insert/update/delete throughput, index lag |
| Filter behavior | Recall và latency theo mức chọn lọc metadata |
| Reliability | Lỗi/timeouts, recovery/failover, dữ liệu mới nhìn thấy sau bao lâu |

Khi đo QPS, phải cố định rõ **latency SLA**. Một hệ thống có thể xử lý nhiều query/giây nhưng p99 tăng quá cao; con số throughput đứng riêng không đủ để kết luận nó đáp ứng yêu cầu.

### 13.5. Tuning có hệ thống

Một quy trình thực dụng:

~~~text
1. Đặt mục tiêu về recall, p95/p99, QPS, RAM và freshness.
2. Đo exact baseline trên tập có thể xử lý chính xác.
3. Chọn 2–3 họ index phù hợp điều kiện bộ nhớ/ghi.
4. Với từng họ, thay đổi tham số theo một dải có kiểm soát.
5. Ghi recall + latency + resource tại mỗi điểm.
6. Loại cấu hình không đạt ràng buộc bắt buộc.
7. So sánh các cấu hình còn lại theo chi phí vận hành.
8. Kiểm tra lại ở dữ liệu lớn hơn, filter hẹp, concurrent load.
9. Đánh giá chất lượng relevance/RAG ngoài ANN recall.
10. Triển khai canary và theo dõi chất lượng theo thời gian.
~~~

Nếu thay đổi nhiều tham số cùng lúc mà không ghi lại cấu hình, sẽ khó biết yếu tố nào thực sự cải thiện kết quả.

## 14. Bài toán cụ thể: chọn index trong ba kịch bản

### 14.1. Kịch bản A — Kho nhỏ, lọc hẹp

Một service có 50.000 vector, nhưng mọi truy vấn luôn lọc về một nhóm khoảng 100–500 vector.

**Hướng cân nhắc:** exact search trên tập được lọc có thể đủ tốt và dễ giải thích. ANN toàn cục kèm hậu lọc có thể bỏ sót tài liệu hợp lệ nếu filter quá chặt. Chi phí duy trì index phức tạp có thể không tương xứng với lợi ích.

### 14.2. Kịch bản B — Kho đọc nhiều, cập nhật ít

Một kho 5 triệu đoạn tài liệu, có hàng trăm truy vấn đồng thời và dữ liệu chỉ cập nhật theo lô hằng ngày.

**Hướng cân nhắc:** HNSW hoặc phương án ANN khác được tối ưu cho truy vấn có thể phù hợp nếu đáp ứng RAM và độ trễ; nếu RAM hạn chế, cân nhắc IVF-PQ hoặc kiến trúc SSD. Cần tính chi phí build/rebuild theo ngày và giai đoạn tồn tại đồng thời index cũ/mới.

### 14.3. Kịch bản C — Dòng dữ liệu liên tục

Một hệ theo dõi sự kiện cần thêm và xóa hàng chục nghìn embedding mỗi phút, trong khi người dùng muốn truy vấn gần như ngay sau khi ghi.

**Hướng cân nhắc:** kiểm tra khả năng online insert/delete của engine, index lag, chất lượng sau nhiều cập nhật, cơ chế delta index/rebuild, và chi phí khi có nhiều shard. Một thuật toán có recall cao khi index tĩnh chưa chắc đáp ứng tốt vòng đời ghi liên tục.

Không chọn chỉ mục chỉ dựa trên kích thước N; **tỷ lệ đọc/ghi và yêu cầu thấy dữ liệu mới** cũng quyết định kiến trúc.

## 15. Những sai lầm thường gặp

| Nhận định hoặc cách làm | Vì sao có thể sai | Cách tiếp cận tốt hơn |
| --- | --- | --- |
| “Vector search có Recall@10 = 100% nên câu trả lời chắc chắn đúng.” | Recall ANN đo sự giống exact kNN, không đo tính liên quan hay factuality. | Đo relevance và chất lượng câu trả lời riêng. |
| “ANN luôn nhanh hơn exact.” | Tập dữ liệu nhỏ hoặc lọc hẹp có thể chạy exact rất hiệu quả. | Benchmark cả exact baseline. |
| “Cứ tăng efSearch thật cao là tốt nhất.” | CPU, độ trễ và throughput có thể xấu đi. | Tuning theo yêu cầu recall và ngân sách tài nguyên. |
| “Đo recall trên top-10 toàn cục rồi áp dụng filter tenant.” | Ground truth không cùng tập ứng viên hợp lệ. | Tính exact top-k trên dữ liệu đã lọc. |
| “Cosine và dot product luôn tương đương.” | Chỉ tương đương về thứ tự khi vector được chuẩn hóa phù hợp. | Thống nhất preprocessing và metric. |
| “Số chiều giống nhau nghĩa là vector của hai model so sánh được.” | Hai không gian embedding có thể không tương thích. | Gắn model version, re-embed và reindex khi đổi model. |
| “PQ giảm 32 lần thì toàn bộ chi phí lưu trữ giảm 32 lần.” | ID, codebook, graph, metadata, replica và vector gốc vẫn tốn dung lượng. | Đo tổng footprint thực tế. |
| “LIMIT 10 luôn trả đủ 10 tài liệu sau filter.” | Post-filter có thể loại phần lớn ứng viên. | Thiết kế filtered ANN/overfetch có kiểm chứng. |
| “Index hỗ trợ DELETE tức là mọi kết quả cũ biến mất ngay.” | Có thể có độ trễ cập nhật, tombstone, cache hoặc replica. | Kiểm tra freshness và ngữ nghĩa xóa của engine. |
| “Benchmark 10.000 vector ngẫu nhiên đại diện production.” | Dữ liệu thật có cụm, tenant lệch, hot query và filter phức tạp. | Đánh giá trên tập đại diện và mức tải thật. |

## 16. Bài tập tự vận dụng

### Bài 1 — Tính dung lượng vector

Hệ thống có 2,5 triệu vector, 1.024 chiều, Float32. Hãy:

1. Tính số byte vector thô.
2. Đổi ra GB (10^9 byte) và GiB (2^30 byte).
3. Tính riêng phần vector nếu lưu 2 bản sao đầy đủ.
4. Liệt kê ít nhất bốn khoản chi phí khác cần cộng trước khi chọn máy.

### Bài 2 — Tính Recall@5

~~~text
Exact top-5:  A, B, C, D, E
ANN top-5:    A, C, E, X, Y
~~~

Hãy tính Recall@5, sau đó giải thích vì sao chỉ đổi thứ tự ba ID đúng không làm tăng recall. Nếu \`X\` là một tài liệu rất phù hợp với người dùng, chất lượng tìm kiếm nghiệp vụ có thể khác kết luận ANN recall như thế nào?

### Bài 3 — Tuning HNSW

Một nhóm thử \`efSearch = 20, 50, 100, 200\` với cùng index, cùng tập query. Hãy thiết kế bảng ghi mean Recall@10, p95/p99 latency, CPU/query và QPS. Nếu ràng buộc là \`Recall@10 >= 0,96\` và \`p95 <= 40 ms\`, hãy giải thích cách chọn cấu hình thay vì chỉ chọn efSearch lớn nhất.

### Bài 4 — Bộ lọc tenant

Một chỉ mục chứa 10 triệu vector, trong đó chỉ 0,2% thuộc tenant đang đăng nhập. Query cần top-10 của riêng tenant đó.

Hãy phân tích:

- Điều gì xảy ra nếu lấy ANN top-10 toàn cục rồi lọc tenant?
- Vì sao overfetch không tự tạo bảo đảm tìm đủ 10?
- Nên tính ground truth để đo recall theo tập nào?
- Khi nào index/shard riêng cho tenant có thể hữu ích?

### Bài 5 — Cập nhật embedding

Hệ thống chuyển từ mô hình embedding A sang B. Hãy vẽ luồng re-embed, xây chỉ mục thế hệ mới, kiểm tra chất lượng và chuyển đổi truy vấn. Giải thích vì sao không nên trộn vector của hai mô hình không tương thích vào một index.

### Bài 6 — ANN và RAG

Giả sử ANN Recall@10 tăng từ 0,90 lên 0,97 nhưng tỷ lệ câu trả lời RAG được người đánh giá chấp nhận gần như không đổi. Hãy đưa ra các giả thuyết có thể kiểm tra:

- Các láng giềng mới tìm được có thực sự liên quan?
- Việc chia chunk có đang làm mất ngữ cảnh?
- Reranker có thay đổi thứ tự quá mạnh?
- Prompt có dùng đúng tài liệu được lấy?
- Câu trả lời sai đến từ retrieval hay từ bước tổng hợp?

## Kết luận

Chỉ mục vector gần đúng giúp hệ thống tìm những đối tượng gần nhau trong không gian embedding mà thường không phải so điểm với mọi vector. **HNSW** điều hướng trên đồ thị láng giềng, **IVF** giới hạn tìm kiếm vào những cụm có triển vọng, còn **PQ/quantization** giảm dung lượng bằng cách chấp nhận sai số biểu diễn. Các kỹ thuật có thể kết hợp trong một hệ thống.

Việc lựa chọn chỉ mục cần đồng thời nhìn vào ba nhóm yếu tố:

- **Độ chính xác truy hồi:** Recall@k được so với exact kNN trên cùng metric, tập dữ liệu và bộ lọc; phải đo thêm relevance nghiệp vụ vì recall của ANN không phải độ đúng của câu trả lời.
- **Chi phí truy vấn:** p95/p99 latency, QPS, CPU, I/O và khả năng xử lý truy vấn đồng thời, đặc biệt với filter hẹp và query khó.
- **Chi phí vòng đời:** dung lượng vector, cấu trúc chỉ mục, RAM, thời gian train/build, thêm/sửa/xóa, rebuild, replication và chuyển đổi mô hình embedding.

Không có “cấu hình ANN tốt nhất” cho mọi workload. Thiết kế phù hợp là cấu hình **đạt chất lượng truy hồi mà ứng dụng thực sự cần** trong **ngân sách độ trễ, tài nguyên và vận hành có thể kiểm chứng bằng số đo**.
