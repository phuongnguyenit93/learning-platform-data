# Đánh giá độ phù hợp, độ trễ, bộ nhớ và chi phí lưu vector trong MongoDB

## 1. Vì sao cần đánh giá nhiều chiều?

Khi triển khai **MongoDB Vector Search** để tìm tài liệu tương tự, gợi ý sản phẩm hoặc xây hệ thống RAG (*retrieval-augmented generation*), việc `$vectorSearch` trả về vài document có vẻ liên quan chưa chứng minh thiết kế đã tốt. Một hệ thống có thể:

- Trả đúng một số câu hỏi mẫu nhưng **bỏ sót** tài liệu quan trọng ở các câu hỏi thực tế.
- Có **latency trung bình thấp**, nhưng p99 tăng cao khi số request đồng thời tăng.
- Lưu vector có kích thước nhỏ trong collection, nhưng **Search index/HNSW graph** cần nhiều RAM.
- Giảm RAM bằng quantization nhưng làm **giảm recall**, hoặc tốn thêm I/O khi rescoring.
- Có phí database hợp lý nhưng chi phí **embedding API, Search Nodes, network, reranking, LLM và reindex** vượt ngân sách.
- Trả tài liệu gần nghĩa nhưng **khác tenant**, đã bị xóa hoặc không còn quyền truy cập.
- Đạt ANN recall gần 100% so với ENN mà vẫn không có **độ phù hợp nghiệp vụ** tốt.

Bài học này thuộc chương **Tìm kiếm vector** và tập trung vào bốn nhóm quyết định:

| Trục | Câu hỏi phải trả lời | Chỉ số thường dùng |
| --- | --- | --- |
| **Độ phù hợp** | Kết quả có trả lời nhu cầu thật và được xếp đúng thứ tự? | Precision@k, Recall@k, nDCG@k, MRR, hit rate |
| **Độ chính xác truy hồi vector** | ANN có tìm gần đủ top-k của ENN theo cùng model và metric? | ANN recall@k, overlap với ENN |
| **Độ trễ và throughput** | Tìm kiếm mất bao lâu khi tải tăng? | p50/p95/p99, QPS, timeout/error rate |
| **RAM và storage** | Cần bao nhiêu bytes nguồn, chỉ mục và headroom? | Bytes/vector, Search index RAM/disk, IOPS |
| **Tổng chi phí** | Số lượng vector, request và cập nhật tăng thì TCO ra sao? | USD/tháng, USD/triệu query, cost/successful answer |

Mục tiêu cuối cùng là tìm **cấu hình rẻ nhất vẫn đạt các điều kiện bắt buộc về chất lượng, latency, freshness và bảo mật**, không tối ưu một metric riêng lẻ.

### Sau bài này, bạn có thể

1. Phân biệt **human relevance** với **ANN recall so với ENN**.
2. Lựa chọn similarity metric, `limit`, `numCandidates`, `exact` và pre-filter.
3. Đo p95/p99 của MongoDB và toàn pipeline, không nhầm mean latency với tail latency.
4. Ước lượng dữ liệu vector theo `N × D × bytesPerDimension`.
5. Phân biệt BSON numeric arrays, BinData float32, quantization, graph overhead và Search index.
6. Lập benchmark có golden queries, labels, ENN baseline, concurrency và filter selectivity.
7. Dự toán phí source data, replication, Search Nodes, embedding, rerank, LLM và reindex.
8. Chọn cấu hình bằng scorecard và tránh kết quả vector vi phạm ACL/tenant isolation.

## 2. Vector Search nằm ở đâu trong kiến trúc MongoDB?

Một pipeline điển hình:

```text
Tài liệu / sản phẩm / đoạn văn gốc
             |
      Clean + chunk + metadata
             |
         Embedding model
             |
      Vector D chiều / chunk
             |
      MongoDB source collection
             |
    MongoDB Vector Search index
       HNSW / flat + filters
             |
User query -> query embedding cùng model/space
             |
         $vectorSearch
             |
      Top-k IDs + scores
             |
      Hydrate / rerank
             |
    UI, API hoặc RAG context
```

**Ba loại tài nguyên không được gộp:**

- **Nguồn dữ liệu**: text, metadata, vector lưu trong BSON documents trên `mongod`.
- **Vector Search index**: vectors/index representations, HNSW graph, filter structures và runtime của Search service (`mongot`/Search Nodes tùy triển khai).
- **Dịch vụ khác**: model tạo query embedding, preprocessing, reranker, LLM, cache và API.

Trên một số Atlas tiers, Search và MongoDB process dùng chung tài nguyên; với **dedicated Search Nodes** có thể tách compute/RAM cho search. Cấu hình, topology và dịch vụ self-managed khác nhau theo phiên bản. Không được suy từ **RAM còn của `mongod`** rằng Search index có đủ RAM.

## 3. Embedding, số chiều và similarity

Embedding là vector:

\[
\mathbf{x} = [x_1,x_2,\ldots,x_D]
\]

`D` là **số chiều**. Query vector và document vectors phải cùng embedding space: cùng model/version/tiền xử lý và số chiều phù hợp index.

### 3.1. Các hàm đo độ gần

| Similarity | Ý nghĩa | Đánh đổi |
| --- | --- | --- |
| `cosine` | Đo góc giữa các vector | Phù hợp khi hướng quan trọng hơn magnitude |
| `dotProduct` | Tích vô hướng | Có thể ảnh hưởng bởi magnitude nếu vector chưa normalized |
| `euclidean` | Khoảng cách L2 | Phù hợp khi model/index sử dụng khoảng cách Euclidean |

Công thức:

\[
\mathrm{cosine}(\mathbf{q},\mathbf{x}) =
\frac{\mathbf{q}\cdot\mathbf{x}}{\|\mathbf{q}\|_2\|\mathbf{x}\|_2}
\]

\[
\mathbf{q}\cdot\mathbf{x}=\sum_{i=1}^{D}q_ix_i
\]

\[
\mathrm{distance}_{L2}=\sqrt{\sum_{i=1}^{D}(q_i-x_i)^2}
\]

Nếu mọi vector đều **L2-normalized** thì cosine và dotProduct có thể cho cùng thứ hạng. Nhưng **không đúng nói chung** khi magnitude khác. Phải chọn hàm similarity theo embedding model và đánh giá tập query thực tế, không tùy ý đổi chỉ để điểm số trông cao hơn.

### 3.2. `vectorSearchScore` không phải xác suất

MongoDB Vector Search trả điểm metadata:

```javascript
{
  $project: {
    title: 1,
    score: { $meta: "vectorSearchScore" }
  }
}
```

`vectorSearchScore` nằm trong khoảng **0 đến 1**, theo phép biến đổi score của similarity được dùng. Điểm `0.87` **không có nghĩa** xác suất câu trả lời đúng là 87%. Nó không phải chỉ số được hiệu chuẩn theo ground truth nghiệp vụ.

Ngưỡng `score >= 0.80` có thể thích hợp cho một corpus/model nhưng không còn đúng khi đổi model, dimension, chunking hoặc quantization. Muốn chọn threshold hãy dùng relevance labels, false-positive/false-negative cost và đánh giá theo nhóm query.

## 4. Hai loại “độ đúng”: relevance và ANN recall

**Relevance** hỏi: “Kết quả có giải quyết nhu cầu người dùng không?”

**ANN accuracy** hỏi: “ANN có tìm được những vector lân cận mà **exact nearest neighbors** (ENN) tìm thấy hay không?”

Cả hai cần đo. ANN hoàn toàn khớp ENN vẫn có thể trả nội dung sai nghĩa nếu model hoặc dữ liệu kém.

### 4.1. Golden query set và qrels

Dùng tập câu hỏi đại diện có nhãn relevance:

```text
queryId, question, documentId, relevanceGrade, tenant, locale

Q1, "cách hoàn tiền", DOC-101, 3, tenantA, vi
Q1, "chính sách đổi trả", DOC-102, 2, tenantA, vi
Q1, "giá vận chuyển", DOC-103, 0, tenantA, vi
Q2, "xử lý lỗi E42", DOC-217, 3, tenantA, vi
```

Ví dụ thang nhãn:

- **3:** Trả lời trực tiếp, đầy đủ, có chứng cứ.
- **2:** Liên quan mạnh, giúp trả lời.
- **1:** Liên quan một phần hoặc cùng chủ đề.
- **0:** Không liên quan.

Nên lấy query từ usage thực và được phép xử lý, gồm query dễ/khó, mã lỗi, câu hỏi tự nhiên, tiếng Việt có/không dấu, query không có đáp án và query cần quyền truy cập. Với RAG, thêm nhãn về **evidence coverage** và **answer faithfulness**.

### 4.2. Precision@k

\[
\mathrm{Precision@k} =
\frac{\text{số kết quả được xem là relevant trong top-k}}{k}
\]

Nếu top-5 có ba kết quả grade ≥2 thì Precision@5 = **3/5 = 0.6**.

### 4.3. Recall@k theo nhãn

\[
\mathrm{Recall@k} =
\frac{\text{số tài liệu relevant tìm được trong top-k}}
{\text{tổng tài liệu relevant đã biết}}
\]

Nếu bộ nhãn có bốn tài liệu relevant và top-5 lấy ba, Recall@5 = **0.75**.

Cảnh giác: ở corpus rất lớn, khó gán nhãn **toàn bộ** tài liệu relevant. “Recall” dựa trên qrels có thể bị sai lệch nếu qrels chưa bao phủ; dùng pooling từ nhiều phương pháp, đánh giá chuyên gia và ghi chú phạm vi.

### 4.4. MRR và nDCG

**MRR** tập trung vào vị trí kết quả relevant đầu tiên:

\[
\mathrm{RR}(q)=\frac{1}{\mathrm{rank\ của\ kết\ quả\ relevant\ đầu\ tiên}}
\]

Nếu kết quả relevant đầu tiên ở rank 2, RR = **0.5**. Lấy trung bình qua nhiều query là MRR.

**DCG@k** dùng relevance grades:

\[
\mathrm{DCG@k} =
\sum_{i=1}^{k} \frac{2^{rel_i}-1}{\log_2(i+1)}
\]

**nDCG@k = DCG@k / IDCG@k**, trong đó IDCG là DCG của thứ tự lý tưởng. nDCG hữu ích khi xếp kết quả grade 3 ở rank 1 tốt hơn xếp nó ở rank 10.

Cần chọn metrics đúng UX: hỗ trợ khách hàng thường ưu tiên kết quả đầu tiên chính xác; RAG có thể ưu tiên evidence coverage trong top-N chunks.

## 5. ENN và ANN: hiểu trade-off trước khi benchmark

MongoDB Vector Search hỗ trợ tìm:

- **ENN** (*Exact Nearest Neighbor*): so độ gần với toàn bộ tập vector đủ điều kiện theo metric/index, chọn top-k chính xác.
- **ANN** (*Approximate Nearest Neighbor*): dùng cấu trúc index như **HNSW** để tìm candidates mà không phải so từng vector, chấp nhận có thể bỏ sót một số hàng xóm.

| Tiêu chí | ENN | ANN |
| --- | --- | --- |
| Kết quả theo embedding metric | Exact trong phạm vi index/filter | Xấp xỉ |
| Tác vụ benchmark | Làm baseline cho ANN recall | Đo so với ENN |
| Corpus lớn không filter | Có thể rất tốn tài nguyên | Thường phù hợp hơn |
| Filter cực chọn lọc | Có thể hợp lý | Có thể gặp khó khăn trong graph |
| Chất lượng nghiệp vụ | Không bảo đảm | Không bảo đảm |
| Latency tăng theo N | Thường đáng kể | Thường hiệu quả hơn ở N lớn |

### 5.1. ANN recall@k

Gọi \(T_k(q)\) là các ID của **ENN top-k** và \(A_k(q)\) là các ID của **ANN top-k**.

\[
\mathrm{ANNRecall@k}(q) =
\frac{|A_k(q)\cap T_k(q)|}{|T_k(q)|}
\]

Trung bình:

\[
\overline{\mathrm{ANNRecall@k}} =
\frac{1}{Q}\sum_{q=1}^{Q}\mathrm{ANNRecall@k}(q)
\]

Ví dụ:

```text
ENN top-5 = [A, B, C, D, E]
ANN top-5 = [A, B, F, D, G]

Intersection = [A, B, D]
ANN recall@5 = 3/5 = 0.60
```

Điểm quan trọng: **ENN chỉ “đúng” theo embeddings và similarity metric đã chọn**, không hiểu nhãn nghiệp vụ. Một hệ thống có ANN recall@10 = 0.99 nhưng human nDCG@10 = 0.35 có thể cần thay model/chunking chứ không phải tăng `numCandidates`.

Nếu có nhiều tied scores ở ranh giới top-k, phép overlap theo ID có thể đánh giá khác biệt không thực sự đáng kể; ghi nhận ties hoặc đo relevance đồng thời.

## 6. `numCandidates`, `limit` và tốc độ

Trong MongoDB Vector Search:

- `limit`: số results tối đa trả về.
- `numCandidates`: kích thước tập ứng viên HNSW xem xét trong ANN query.
- `exact: true`: yêu cầu ENN, không dùng `numCandidates` như ANN.
- `exact: false` hoặc bỏ `exact`: ANN theo cấu hình hỗ trợ.

```javascript
{
  $vectorSearch: {
    index: "embedding_index",
    path: "embedding",
    queryVector: queryEmbedding,
    numCandidates: 200,
    limit: 10
  }
}
```

MongoDB đưa ra điểm khởi đầu thường dùng: **`numCandidates` ít nhất khoảng 20 lần `limit`**, sau đó đo lại trên corpus, filters, quantization và workload thực. Không được diễn giải đây là bảo đảm recall.

| limit | numCandidates | Tỷ lệ | Gợi ý |
| ---: | ---: | ---: | --- |
| 10 | 50 | 5× | Có thể nhanh, phải kiểm tra recall |
| 10 | 100 | 10× | So sánh trung gian |
| 10 | 200 | 20× | Điểm khởi đầu tham khảo |
| 10 | 500 | 50× | Có thể tăng recall và latency |
| 20 | 400 | 20× | Ví dụ cho top-20 |

Trong các API tương ứng hiện hành, ANN `numCandidates` phải không nhỏ hơn `limit` và có giới hạn tối đa (ví dụ 10.000 theo tài liệu MongoDB). Cần đối chiếu phiên bản/loại index trước khi dùng cấu hình vượt ngưỡng.

**Tăng candidates không làm recall tăng chắc chắn từng bước.** Có điểm bão hòa, khác biệt theo query và chi phí CPU/latency.

### 6.1. HNSW và flat

MongoDB Vector Search có các kiểu index theo phiên bản:

- **`hnsw`**: graph-based, phục vụ ANN ở corpus lớn; có thể chạy ENN bằng `exact: true`.
- **`flat`**: không xây graph HNSW, dùng exhaustive search, thích hợp khi tập sau pre-filter rất nhỏ hoặc yêu cầu exact.

Trong kiểu `flat`, tuning `numCandidates` không có ý nghĩa tương đương HNSW. Lựa chọn index method phải dựa trên phiên bản hỗ trợ, kích thước corpus, độ chọn lọc filter và benchmark.

### 6.2. Khi nào ENN đáng chọn?

- Tập dữ liệu sau pre-filter có rất ít documents.
- Corpus nhỏ nhưng cần exact neighbors.
- Cần tạo ground truth kỹ thuật cho ANN.
- Có yêu cầu tính chính xác vector-neighbor cao hơn chi phí latency.
- Muốn kiểm thử sự khác biệt do quantization hoặc index graph.

Không mặc định ENN phù hợp query không filter trên hàng chục triệu vectors.

## 7. Pre-filter và post-filter: không chỉ ảnh hưởng latency

Các bộ lọc thường gặp: `tenantId`, `isActive`, `language`, `category`, `securityLevel`, quyền xem tài liệu.

### 7.1. Pre-filter đúng

```javascript
{
  $vectorSearch: {
    index: "embedding_index",
    path: "embedding",
    queryVector: queryEmbedding,
    filter: {
      tenantId: "tenantA",
      isActive: true
    },
    numCandidates: 200,
    limit: 10
  }
}
```

Các field được dùng trong `filter` phải được khai báo là **`filter` type** trong Vector Search index. Filter này giới hạn tập vector đủ điều kiện ngay trong Search.

**Cảnh giác:** Filter càng chọn lọc không có nghĩa luôn chạy nhanh hơn. Trên HNSW, nó có thể buộc tìm kiếm phải duyệt nhiều graph nodes hơn để đủ candidates. Hãy benchmark cả query không filter, filter rộng và filter rất hẹp.

### 7.2. Post-filter không tương đương

```javascript
[
  {
    $vectorSearch: {
      index: "embedding_index",
      path: "embedding",
      queryVector: queryEmbedding,
      numCandidates: 200,
      limit: 10
    }
  },
  { $match: { tenantId: "tenantA" } }
]
```

Query lấy **top-10 toàn corpus** rồi mới lọc. Có thể chỉ còn hai kết quả của tenant A dù tenant này còn hàng nghìn tài liệu phù hợp. Với ACL/tenant isolation, không dùng post-filter top-k như thể nó trả đủ những ứng viên có quyền.

### 7.3. Bảng filter selectivity cần thử

| Scenario | % tài liệu qua filter (giả định) | Mục đích |
| --- | ---: | --- |
| Không filter | 100% | Baseline |
| Category lớn | 40% | Filter rộng |
| Category nhỏ | 5% | Filter chọn lọc |
| Tenant nhỏ | 0,2% | Kiểm tra ANN/ENN sau filter |
| Document gần đây | 1% | Freshness và selectivity |

Phải đo quality, số results, latency và tài nguyên từng trường hợp. **Đừng xem filter chỉ là điều kiện bổ sung miễn phí.**

## 8. Lab MongoDB Vector Search tự chứa

Các ví dụ chỉ chạy được trên **deployment hỗ trợ MongoDB Vector Search và Search index**. Một MongoDB standalone không có Search service/index phù hợp sẽ không chạy `$vectorSearch` chỉ vì collection có mảng số.

Dữ liệu lab dùng vector **bốn chiều do ta tự tạo** để dễ hiểu cú pháp; nó **không phải embedding semantic chất lượng production**.

### 8.1. Chuẩn bị collection

Mở `mongosh` vào môi trường thử nghiệm, **không chạy `drop()` trên production**:

```javascript
const lab = db.getSiblingDB("vector_eval_lab");

lab.items.drop();

lab.items.insertMany([
  {
    _id: "D1",
    tenantId: "A",
    isActive: true,
    category: "database",
    title: "Giới thiệu MongoDB",
    embedding: [1.0, 0.0, 0.0, 0.0]
  },
  {
    _id: "D2",
    tenantId: "A",
    isActive: true,
    category: "database",
    title: "Replica set và failover",
    embedding: [0.8, 0.2, 0.0, 0.0]
  },
  {
    _id: "D3",
    tenantId: "A",
    isActive: true,
    category: "database",
    title: "Sharding",
    embedding: [0.5, 0.5, 0.0, 0.0]
  },
  {
    _id: "D4",
    tenantId: "A",
    isActive: true,
    category: "search",
    title: "Vector Search",
    embedding: [0.0, 0.8, 0.2, 0.0]
  },
  {
    _id: "D5",
    tenantId: "B",
    isActive: true,
    category: "database",
    title: "Tài liệu riêng của B",
    embedding: [0.99, 0.01, 0.0, 0.0]
  },
  {
    _id: "D6",
    tenantId: "A",
    isActive: false,
    category: "database",
    title: "Tài liệu đã ẩn",
    embedding: [0.98, 0.02, 0.0, 0.0]
  },
  {
    _id: "D7",
    tenantId: "A",
    isActive: true,
    category: "search",
    title: "Phân tích văn bản",
    embedding: [0.0, 0.6, 0.4, 0.0]
  },
  {
    _id: "D8",
    tenantId: "A",
    isActive: true,
    category: "other",
    title: "Tài liệu khác",
    embedding: [0.0, 0.0, 0.0, 1.0]
  }
]);
```

### 8.2. Tạo Vector Search index

Ví dụ với `mongosh` và deployment hỗ trợ `createSearchIndex`:

```javascript
lab.items.createSearchIndex({
  name: "toy_vector_index",
  type: "vectorSearch",
  definition: {
    fields: [
      {
        type: "vector",
        path: "embedding",
        numDimensions: 4,
        similarity: "cosine"
      },
      { type: "filter", path: "tenantId" },
      { type: "filter", path: "isActive" },
      { type: "filter", path: "category" }
    ]
  }
});
```

Index build **bất đồng bộ**. Kiểm tra:

```javascript
lab.items.listSearchIndexes().toArray();
```

Chỉ query khi index đã `queryable`/READY theo API của phiên bản. Tham số `quantization`, `indexingMethod` và các option HNSW cần theo tài liệu của deployment đang dùng.

### 8.3. Truy vấn ANN

```javascript
const q = [0.9, 0.1, 0.0, 0.0];

const ann = lab.items.aggregate([
  {
    $vectorSearch: {
      index: "toy_vector_index",
      path: "embedding",
      queryVector: q,
      filter: { tenantId: "A", isActive: true },
      numCandidates: 40,
      limit: 3
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      category: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]).toArray();

printjson(ann);
```

`$vectorSearch` phải là **stage đầu tiên** của pipeline. Do pre-filter, kết quả không được chứa `D5` tenant B hoặc `D6` inactive.

### 8.4. ENN làm baseline

```javascript
const enn = lab.items.aggregate([
  {
    $vectorSearch: {
      index: "toy_vector_index",
      path: "embedding",
      queryVector: q,
      filter: { tenantId: "A", isActive: true },
      exact: true,
      limit: 3
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]).toArray();

printjson(enn);
```

ENN tìm exact neighbors **trong tập vector đủ điều kiện theo index và filter**, không bảo đảm document có relevance theo nhu cầu thật. Với lab tám docs, ANN và ENN có thể trả cùng top-3; điều đó không chứng minh ANN trên hàng triệu vectors có recall 100%.

### 8.5. Tính overlap

```javascript
function recallAtK(annDocs, ennDocs) {
  const groundTruth = new Set(ennDocs.map(d => String(d._id)));
  const hits = annDocs.filter(
    d => groundTruth.has(String(d._id))
  ).length;

  return groundTruth.size ? hits / groundTruth.size : 1;
}

print("ANN recall@3:", recallAtK(ann, enn));
```

Ở production, tính trung bình qua nhiều query và nhiều mức `numCandidates`, giữ **cùng filter, similarity và index** khi so.

## 9. Lab đánh giá relevance theo nhãn

Tạo nhãn giả lập:

```javascript
const relevance = {
  Q1: { D1: 3, D2: 2, D3: 1, D4: 0, D7: 0, D8: 0 },
  Q2: { D4: 3, D7: 2, D3: 1, D1: 0, D2: 0, D8: 0 }
};

function precisionAtK(ids, labels, k, relevantGrade = 2) {
  let n = 0;
  for (const id of ids.slice(0, k)) {
    if ((labels[id] || 0) >= relevantGrade) n++;
  }
  return n / k;
}

function dcgAtK(ids, labels, k) {
  return ids.slice(0, k).reduce((sum, id, i) => {
    const rel = labels[id] || 0;
    return sum + (Math.pow(2, rel) - 1) / Math.log2(i + 2);
  }, 0);
}

function ndcgAtK(ids, labels, k) {
  const ideal = Object.keys(labels).sort(
    (a, b) => labels[b] - labels[a]
  );
  const best = dcgAtK(ideal, labels, k);
  return best ? dcgAtK(ids, labels, k) / best : 1;
}

const resultIds = ["D1", "D3", "D2", "D4", "D7"];

print("P@3:", precisionAtK(resultIds, relevance.Q1, 3));
print("nDCG@3:", ndcgAtK(resultIds, relevance.Q1, 3));
```

Với Q1, nếu relevant là grade ≥2, danh sách `[D1,D3,D2]` có Precision@3 = **2/3**. nDCG giảm vì D3 (grade 1) đứng trước D2 (grade 2).

Không dùng điểm vector search thay **human labels**. Cần giữ evaluation set cố định khi so model/index/chunking và có holdout chống overfit.

## 10. Latency: tách thời gian của từng bước

Một request tìm kiếm có thể bao gồm:

```text
User request
    |
    +-- Authentication + network
    +-- Preprocessing
    +-- Query embedding API
    +-- MongoDB $vectorSearch
    +-- Hydration / $project
    +-- Optional reranker
    +-- Optional LLM generation
    +-- Serialization / response
```

Nếu user thấy 600 ms trong khi MongoDB Vector Search chỉ mất 35 ms, giảm MongoDB xuống 25 ms không giải quyết phần lớn latency.

| Metric | Mốc đo | Mục đích |
| --- | --- | --- |
| `embeddingLatencyMs` | Gửi text tới embedding model → nhận vector | Provider/model latency |
| `vectorQueryLatencyMs` | Gửi aggregation → nhận đủ kết quả | MongoDB/search + network |
| `hydrationLatencyMs` | Lấy nội dung nguồn/metadata | Payload/I/O |
| `rerankLatencyMs` | Gửi candidates → nhận thứ tự mới | Reranker |
| `searchApiLatencyMs` | HTTP request → response | User-facing SLO |
| `ragAnswerLatencyMs` | Question → answer | RAG UX |

Nếu xử lý song song, không thể cộng đơn giản các p95 thành p95 tổng; **đo end-to-end trực tiếp**.

## 11. p50, p95, p99 và error rate

Mean latency có thể che tail latency. Giả sử hầu hết queries trả trong 40 ms nhưng 1% queries tốn 1.000 ms, người dùng ở percentile cao sẽ gặp delay rất khó chịu.

- **p50:** một nửa request nhanh hơn ngưỡng.
- **p95:** 95% request hoàn thành không quá ngưỡng (theo phép tính percentile của dữ liệu).
- **p99:** tập trung vào tail.
- **QPS:** throughput thực tế đạt được, không phải số request gửi vào load generator.
- **Error rate:** timeout, reject, stale/incomplete results nếu có cách xác định.

### 11.1. Benchmark nhỏ trong mongosh

```javascript
const candidatesList = [20, 40, 80, 160];
const vectors = [
  [0.9, 0.1, 0, 0],
  [0.1, 0.9, 0, 0],
  [0.5, 0.5, 0, 0]
];

function searchOnce(queryVector, numCandidates) {
  return lab.items.aggregate([
    {
      $vectorSearch: {
        index: "toy_vector_index",
        path: "embedding",
        queryVector,
        filter: { tenantId: "A", isActive: true },
        numCandidates,
        limit: 3
      }
    },
    {
      $project: {
        _id: 1,
        score: { $meta: "vectorSearchScore" }
      }
    }
  ]).toArray();
}

function percentile(samples, p) {
  const sorted = [...samples].sort((a, b) => a - b);
  const i = Math.ceil(p * sorted.length) - 1;
  return sorted[Math.max(0, Math.min(i, sorted.length - 1))];
}

for (const n of candidatesList) {
  // Warm up trước khi đo.
  for (const v of vectors) searchOnce(v, n);

  const samplesMs = [];

  for (let i = 0; i < 30; i++) {
    const v = vectors[i % vectors.length];
    const t0 = Date.now();
    searchOnce(v, n);  // .toArray() lấy đủ kết quả.
    samplesMs.push(Date.now() - t0);
  }

  printjson({
    numCandidates: n,
    p50: percentile(samplesMs, 0.50),
    p95: percentile(samplesMs, 0.95),
    p99: percentile(samplesMs, 0.99)
  });
}
```

**Cảnh báo:** 30 lần đo, dữ liệu chỉ 8 docs và timer millisecond chưa đủ để đánh giá p99 production; network, caches và scheduling dễ chi phối. Đây chỉ là hướng dẫn instrument. Production cần benchmark **hàng trăm/hàng nghìn truy vấn đại diện**, thời gian đủ dài, warm/cold tests, concurrency, error rate, Search index đã sẵn sàng và cùng môi trường cấu hình.

### 11.2. Theo dõi p95/p99 theo nhóm truy vấn

Không chỉ một con số cho toàn service. Nên tách:

- Query có filter tenant nhỏ/lớn.
- Query tiếng Việt, tiếng Anh và mã định danh.
- Query trả 5/10/20/50 results.
- Query với nhiều dimension/model khác nhau.
- Query chạy khi index đang cập nhật.
- Concurrency 1, 10, 50, 100 users.
- Corpus nhỏ/lớn và cached/uncached.

Một mức `numCandidates` tốt cho global queries chưa chắc tốt cho highly selective filters.

## 12. Concurrency và capacity serving

Nếu chỉ có một client, truy vấn 70 ms có thể rất ổn. Nhưng 100 clients đồng thời có thể làm Search CPU, thread pools, network hoặc disk I/O bão hòa; request bị queue và p99 tăng mạnh.

**Little's Law** cho hệ thống ổn định:

\[
L=\lambda W
\]

- \(L\): số requests trung bình đang ở hệ thống.
- \(\lambda\): throughput requests/s.
- \(W\): thời gian trung bình trong hệ thống (giây).

Với \(\lambda=100\) QPS và \(W=0.1\) s, trung bình khoảng **10 requests in flight**. Đây không phải cam kết 10 concurrent slots đủ cho bursts/tail latency.

Các mức concurrency có thể thử:

```text
1, 5, 10, 20, 50, 100 clients
```

Mỗi mức đo QPS thực, p50/p95/p99, timeout/rejection, CPU/RAM Search nodes, disk I/O, network và index freshness. Khi QPS không tăng nữa mà latency/error tăng, hệ thống đang ở vùng saturation.

**Chất lượng phải giữ cố định khi tối ưu tải.** Nếu giảm `numCandidates` hoặc đổi quantization để chạy nhanh hơn, phải đo lại recall và human relevance.

## 13. Công thức bộ nhớ vector cơ bản

Với:

- \(N\): số vector.
- \(D\): số chiều/vector.
- \(b\): bytes/dimension của representation.

Payload số học lý tưởng:

\[
B=N\times D\times b
\]

| Kiểu | Bytes/dimension | D=1536, payload/vector |
| --- | ---: | ---: |
| Float64/double | 8 | 12.288 bytes |
| Float32 | 4 | 6.144 bytes |
| Int8/scalar | 1 | 1.536 bytes |
| Int1/binary | 1/8 | 192 bytes |

Với D không chia hết cho 8, bit-packed representation phải làm tròn lên tới byte cần thiết. Các số trên **chưa** tính metadata, array overhead, graph, runtime, replicas, disk page hoặc compression.

### 13.1. Một triệu vectors 1536 chiều

\[
1{,}000{,}000 \times1536\times4
=6{,}144{,}000{,}000 \text{ bytes}
\]

Tức khoảng **6.144 GB thập phân** hoặc **5.72 GiB** payload float32.

So sánh:

| Representation | 1 triệu vectors, 1536D |
| --- | ---: |
| Float64 | 12.288 GB |
| Float32 | 6.144 GB |
| Int8 | 1.536 GB |
| Binary int1 | 0.192 GB |

**10 triệu vectors 1536D float32 = 61.44 GB payload**, không phải dung lượng index hay RAM toàn cluster.

### 13.2. BSON numeric arrays khác BinData float32

```javascript
{
  embedding: [0.1, 0.2, 0.3]
}
```

Trong BSON, các phần tử JavaScript Number thường lưu là **Double 64-bit** (8 bytes) và BSON array có overhead cho **type + key name từng phần tử**.

Với **BSON BinData vector subtype float32** được driver/SDK hỗ trợ, numeric payload có thể gần 4 bytes/dimension. Tuy nhiên:

- Cần đúng subtype/data format được MongoDB Vector Search hỗ trợ.
- Source storage còn có document fields, metadata, compression.
- Search index vẫn có bản representation, graph và runtime riêng.

Không dùng kích thước JSON chuỗi hoặc chỉ số \(N×D×4\) làm dự báo `storageSize` chính xác.

### 13.3. Bảng kích thước thô

| N vectors | D | Float32 | Int8 | Int1 |
| ---: | ---: | ---: | ---: | ---: |
| 100.000 | 768 | 0.3072 GB | 0.0768 GB | 0.0096 GB |
| 1.000.000 | 1536 | 6.144 GB | 1.536 GB | 0.192 GB |
| 5.000.000 | 1536 | 30.72 GB | 7.68 GB | 0.96 GB |
| 10.000.000 | 2048 | 81.92 GB | 20.48 GB | 2.56 GB |

Đây là **payload không kể overhead**, không phải benchmark MongoDB.

## 14. Bộ nhớ Search index khác payload vector

Một mô hình RAM:

```text
Search RAM ≈
   vector representations
 + HNSW graph connections
 + segment / doc ID structures
 + metadata filter index
 + JVM/runtime/buffers
 + safety headroom
```

HNSW graph tạo các cạnh giữa vectors để ANN tìm kiếm nhanh. Kích thước graph phụ thuộc N, số cạnh, cách chia segment, parameters, version và dữ liệu.

Không suy từ payload 6.144 GB rằng Search RAM cần đúng 6.144 GB. Và không coi `totalIndexSize` của B-tree indexes trong MongoDB source collection là kích thước toàn bộ MongoDB Vector Search index.

### 14.1. Phân biệt ba lớp disk

1. **Document storage**: văn bản/chunk metadata và vector nguồn.
2. **Search index storage**: vector index representation, graph, filter structures, có thể giữ full-precision vectors cho ENN/rescore.
3. **Backup/replica/storage phụ trợ**: những bản sao, snapshot, rebuild data và disk headroom.

Trên Atlas, theo dõi chỉ số **Search Index Size** và **Required Memory** trong Search UI/metrics để phân biệt disk và memory thực tế. Chi tiết đo theo tier và version.

### 14.2. Rebuild cần dự phòng

Khi đổi index definition, model/dimension hoặc quantization, index có thể rebuild bất đồng bộ. Trong thời gian này:

- Có thêm CPU/I/O/network.
- Có thể cần nhiều disk tạm.
- Index cũ và index mới có thể cùng tồn tại trong giai đoạn chuyển đổi theo cơ chế deployment.
- Search freshness/capacity có thể thay đổi.

Đây là chi phí vòng đời phải dự trù, không phải việc chỉnh config miễn phí.

## 15. Quantization: giảm RAM nhưng có trade-off

**Quantization** chuyển vectors nhiều bit sang biểu diễn ít bit hơn. Mục tiêu chủ yếu là giảm RAM, memory bandwidth, đôi khi cải thiện latency/cost; không bảo đảm giữ nguyên relevance.

### 15.1. Float/full precision

- Duy trì thông tin đầy đủ của embedding gốc.
- Thường tiêu thụ RAM nhiều hơn.
- Dùng làm baseline để so sánh quantized configurations.
- Không tự làm model hiểu đúng mọi query.

### 15.2. Scalar quantization

Float32 → representation gần 8-bit/chiều:

- Payload vector lý tưởng giảm khoảng **4 lần**.
- Có thể giảm RAM serving và chi phí tính toán.
- Giá trị bị lượng tử hóa, thứ hạng nearest-neighbor có thể thay đổi.
- Cần kiểm tra ANN recall và nDCG.

### 15.3. Binary quantization

Float32 → representation khoảng **1 bit/chiều**:

- Payload số học lý tưởng nhỏ hơn khoảng **32 lần**.
- Có thể rất hiệu quả về RAM.
- Sai lệch vector so với full precision thường tăng.
- Với **binary + rescoring**, hệ thống có thể đọc vector đầy đủ từ disk để sắp hạng lại top candidates, cải thiện chất lượng nhưng tốn CPU/I/O và latency.

Với automatic quantization, MongoDB có thể giữ **full-precision vectors trên disk** để hỗ trợ ENN hoặc rescoring. Vì vậy giảm RAM index **không đồng nghĩa** disk giảm 32 lần.

### 15.4. Overhead làm tỷ lệ thực khác lý thuyết

Tài liệu benchmark MongoDB ghi nhận mức giảm RAM của Search index trong một số cấu hình khoảng **3.75× cho scalar** và **24× cho binary**, thấp hơn tỷ lệ payload 4×/32× do graph và các cấu trúc khác không nén cùng tỷ lệ.

Tỷ lệ này chỉ là **tham khảo theo workload**, không cam kết ở index của bạn. Lấy Search index RAM/disk đã đo làm cơ sở sizing.

### 15.5. `binaryNoRescore` và auto embedding

Các tài liệu mới có lựa chọn như `binaryNoRescore` ở một số cấu hình Automated Embedding: giảm chi phí rescoring nhưng có thể giảm accuracy. Danh sách quantization options/default **khác nhau theo BYO vectors, automated embeddings, index type và version**. Không copy một option từ tutorial môi trường khác mà không kiểm tra API.

| Cấu hình | RAM | Recall/relevance | Query latency | Disk |
| --- | --- | --- | --- | --- |
| Float/HNSW | Cao | Baseline vector fidelity | ANN thường nhanh ở N lớn | Full precision + graph |
| Scalar/HNSW | Thấp hơn | Có thể giảm nhẹ | Có thể tốt hơn | Có thể giữ full-precision disk |
| Binary+rescore/HNSW | Rất thấp | Có thể gần baseline sau rerank | Có thêm rescoring I/O | Full-precision disk có thể còn |
| Binary no rescore | Rất thấp | Có thể giảm mạnh | Giảm chi phí rescore | Tùy index |
| Flat/ENN | Ít graph | Exact theo metric/index | Có thể chậm khi N lớn | Tùy format |

**Không có lựa chọn tốt nhất cho mọi ứng dụng.** Quyết định bằng SLO + relevance + latency + cost sau khi đo.

## 16. Number of vectors và chunking mới là yếu tố nhân chi phí

Có thể một tài liệu gốc tạo nhiều chunks:

```text
100,000 tài liệu
20 chunks/tài liệu
= 2,000,000 vectors
```

Nếu nâng overlap hoặc chia chunks nhỏ hơn thành **40 chunks/tài liệu**, số vectors thành **4 triệu**, gấp đôi source embedding payload và ảnh hưởng search index/embedding cost.

### 16.1. Chunk quá lớn

- Một vector chứa nhiều chủ đề, tín hiệu semantic loãng.
- Kết quả trả về nhiều text thừa.
- Reranking/LLM context tốn tokens.
- Đoạn trả lời nhỏ có thể bị mất điểm.

### 16.2. Chunk quá nhỏ

- Mất ngữ cảnh.
- Số embeddings/index entries tăng.
- Nhiều near-duplicate chunks làm kết quả lặp.
- Tăng embedding API cost, storage và index rebuild.

Nên đánh giá **nDCG/MRR/answer correctness theo chunking strategy** và số vectors, không chỉ so index memory.

### 16.3. Dimension cũng nhân chi phí

Nếu tăng từ D=768 sang D=1536 ở cùng N và float32, payload vector lý tưởng tăng **gấp đôi**. Chất lượng **không mặc định tăng gấp đôi**; cần đánh giá theo model và domain.

### 16.4. Đổi embedding model là migration

Một kế hoạch an toàn:

1. Version hóa model/vector/index.
2. Tạo embeddings mới ở field/collection mới.
3. Xây Search index tương ứng chiều và similarity.
4. Đo quality, recall, p95/p99 và TCO.
5. Chuyển query embedding sang đúng model mới.
6. Canary/cutover và có phương án quay về index cũ.
7. Dọn vector/index cũ khi đã hết giai đoạn rollback.

**Cùng số chiều không nghĩa cùng embedding space.** Không trộn vector của hai model không tương thích.

## 17. Dự toán source storage và replication

Với 1 triệu vectors, D=1536, float32:

```text
1,000,000 × 1,536 × 4 = 6.144 GB payload
```

Nếu source MongoDB có **ba data-bearing copies** đầy đủ và bỏ qua compression/overhead:

```text
6.144 GB × 3 = 18.432 GB payload vector nguồn
```

Nhưng Search index có thể lưu một representation riêng, thêm graph/filter structures, và managed billing đã có thể tính replication trong giá tier. Đừng nhân ba lần nữa nếu hóa đơn đã bao gồm các bản sao.

Một công thức:

```text
Source storage footprint =
   document/chunk text + original embedding
 + BSON overhead + MongoDB indexes
 × replication/storage policy

Search footprint =
   search vectors/quantized representations
 + graph/filters/segments
 + full-precision disk for ENN/rescore (nếu có)
 × serving topology

Extra =
   backups/snapshots + temporary rebuild
 + network transfer + logs/monitoring
```

Các phép nhân phải áp dụng đúng phạm vi và tránh tính trùng. Nên xác nhận thực tế bằng cluster metrics và cost estimator theo cloud/region/tier.

## 18. Chi phí embedding và re-embedding

Đối với BYO embeddings từ provider ngoài, chi phí tạo vectors có thể tính:

\[
C_{\mathrm{embed}} =
\frac{\mathrm{inputTokens}}{10^6}
\times \mathrm{pricePerMillionTokens}
\]

**Ví dụ giả định, không phải báo giá nhà cung cấp:**

- 2 triệu chunks.
- 1.000 tokens/chunk.
- Tổng **2 tỷ tokens**.
- Giả định $0.05/1 triệu input tokens.

Chi phí ban đầu: \(2000\times0.05=\) **$100** theo giả định. Nếu đổi embedding model và tạo lại toàn bộ vectors, phát sinh chi phí embedding mới, cộng index rebuild/dual serving.

### 18.1. Chi phí query embedding

Nếu 1 triệu queries/tháng, 100 tokens/query:

```text
100,000,000 tokens/tháng
= 100 triệu tokens
```

Ở đơn giá ví dụ $0.05/triệu tokens, query embedding cost = **$5/tháng**. Nhưng đây không bao gồm Search Nodes, source data, retrieval, network, rerank hoặc LLM.

### 18.2. Reranker và LLM thường là khoản đáng kể

```text
Query embedding
   -> vectorSearch top-50
   -> rerank top-8
   -> LLM trả lời trên evidence
```

Nếu gửi 50 chunks dài thẳng vào LLM, token cost có thể lớn. Reranker có thể cải thiện relevance/giảm context nhưng cũng có latency và chi phí riêng. Hãy tính **cost per useful answer**, không chỉ cost per vector search.

## 19. Total Cost of Ownership (TCO)

Mô hình hàng tháng:

\[
\begin{aligned}
C_{\mathrm{month}} ={}&
C_{\mathrm{DatabaseCompute}}+
C_{\mathrm{SourceStorage}}+
C_{\mathrm{SearchNodes}}\\
&+C_{\mathrm{Embedding}}+
C_{\mathrm{Rerank}}+
C_{\mathrm{LLM}}\\
&+C_{\mathrm{Network}}+
C_{\mathrm{Backup}}+
C_{\mathrm{Operations}}
\end{aligned}
\]

Một thước đo kinh tế phù hợp với UX:

\[
C_{\mathrm{perUsefulAnswer}} =
\frac{C_{\mathrm{month}}}
{\mathrm{numberOfUsefulAnswers}}
\]

### 19.1. Ví dụ Search Nodes với giá giả định

Hai Search Nodes, giả định mỗi node **$0.50/giờ**, chạy 720 giờ/tháng:

```text
2 × $0.50/h × 720 h = $720/tháng
```

Nếu phải tăng Search tier và giả định giá thành **$1.20/giờ/node**:

```text
2 × $1.20/h × 720 h = $1,728/tháng
```

Chênh lệch $1,008/tháng. **Không phải giá MongoDB Atlas thực tế**; cần lấy bảng giá hiện hành theo region/cloud/tier trước khi trình ngân sách.

### 19.2. Chi phí mỗi triệu search

Giả sử Search serving và overhead trực tiếp = $1,200/tháng, chạy 2 triệu search requests:

```text
$1,200 / 2 = $600 cho mỗi triệu search queries
```

Chưa kể embedding API, source reads, RAG generation và operations. Nếu relevance thấp, **chi phí cho một kết quả hữu ích** cao hơn nhiều.

### 19.3. Ba lỗi dự toán

- **Đếm thiếu:** Chỉ tính vector bytes mà bỏ Search graph, replicas, index rebuild và reranking.
- **Đếm trùng:** Nhân storage replicas khi managed tier đã bao gồm chúng.
- **Đếm sai đơn vị:** Nhầm GB (10^9 bytes) với GiB (2^30 bytes), hoặc nhầm memory resident và disk index size.

Cần có bảng BOM minh bạch và ghi nguồn giá/cấu hình.

## 20. Những cách tối ưu và thứ phải đo lại

| Biện pháp | Lợi ích tiềm năng | Phải đo lại |
| --- | --- | --- |
| Giảm vector dimensions | Giảm numeric payload | Human nDCG, ANN recall |
| Chunking hợp lý | Giảm N hoặc cải thiện context | Coverage, tokens, index size |
| BinData float32 | Source storage nhỏ hơn BSON Double arrays | Driver/index compatibility |
| Scalar quantization | Giảm Search RAM | Recall, p99, disk |
| Binary + rescore | Rất ít RAM | Rescore I/O/QPS, accuracy |
| Giảm `numCandidates` | Giảm ANN work | ANN recall, critical misses |
| Tăng `numCandidates` | Có thể cải thiện recall | Tail latency/QPS |
| Pre-filter đúng | Đảm bảo scope và kết quả phù hợp | Selectivity/latency |
| Flat/ENN với tập nhỏ | Exact neighbors | Latency khi N tăng |
| Projection bỏ embedding | Giảm network/hydration | E2E latency |
| Cache query vectors | Ít embedding API calls | Freshness/privacy |
| Rerank top-N | Có thể tăng nDCG | Latency/cost |
| Hybrid lexical + semantic | Exact codes và ngữ nghĩa | Fusion/relevance |
| Dedicated Search Nodes | Cách ly tài nguyên | TCO và Search capacity |

### 20.1. Không trả mảng embedding dài nếu UI không cần

```javascript
lab.items.aggregate([
  {
    $vectorSearch: {
      index: "toy_vector_index",
      path: "embedding",
      queryVector: q,
      numCandidates: 40,
      limit: 3
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      category: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]);
```

Projection giúp giảm payload nếu không cần `embedding` dài. Với corpus lớn và high QPS, giảm JSON/serialization/network có thể cải thiện latency tổng.

## 21. Hybrid search, reranking và kết quả chính xác theo nghiệp vụ

Query chứa **mã lỗi, SKU, API field** hoặc version cụ thể có thể không được xếp cao chỉ bởi vector similarity.

Ví dụ:

```text
"Khắc phục MongoDB ERR-1042"
         |
         +-- Lexical text search -> match exact error code
         |
         +-- Vector Search ------> tìm ngữ nghĩa
         |
       Merge/rerank
         |
       Top-k cho user
```

Hybrid có thể tăng coverage, nhưng phải trả thêm index/queries/merge/rerank. So sánh với vector-only trên cùng golden queries, đặc biệt các câu hỏi tiếng Việt và query có mã định danh.

Đối với RAG, thêm các chỉ số:

- **Context recall/precision:** các chunks có chứa bằng chứng đúng?
- **Answer correctness:** câu trả lời có giải quyết câu hỏi?
- **Groundedness/faithfulness:** câu trả lời có được hỗ trợ bởi retrieved evidence?
- **Citation accuracy:** trích dẫn có trỏ đúng đoạn?
- **Cost per successful answer** và độ trễ end-to-end.

Retrieval metrics tốt không tự đảm bảo generation tốt.

## 22. Freshness và quyền truy cập

Vector Search index có quá trình đồng bộ với source MongoDB. Sau insert/update/delete, kết quả **có thể chưa phản ánh thay đổi ngay** trong Search index.

Cần đo:

- Thời gian từ source insert tới searchable.
- Thời gian từ delete/visibility change tới search không còn trả tài liệu.
- Index lag trong ingest burst.
- Trạng thái index build/rebuild.
- Chi phí re-embed khi document thay đổi.

### 22.1. Multi-tenant/ACL không thể dựa riêng vào score

Nếu tài liệu bị thu hồi quyền, kết quả vector search có thể còn ID đó do index lag. API phải áp dụng quyền truy cập từ nguồn authoritative ở thời điểm phục vụ, không coi Search index hay vectorScore là bộ máy authorization.

Những thông tin trong embeddings/metadata/logs cũng cần quản lý theo chính sách bảo mật. Không log nguyên tài liệu nhạy cảm chỉ để benchmark.

## 23. Thiết kế benchmark công bằng

### 23.1. Ba nhóm dữ liệu

**Corpus:** đủ lớn, có distribution như production về document, chunks, dimension, metadata, tenant skew, ngôn ngữ, date và duplicate documents.

**Queries:** có short/long, mã ID, query đa ngôn ngữ, không có đáp án, pre-filter rất hẹp, query dễ/khó và tài liệu mới/xóa.

**Qrels:** relevance labels đủ tin cậy, với holdout để không tune quá mức trên bộ đánh giá.

### 23.2. Các trục thí nghiệm

| Nhóm | Biến thay đổi | Chỉ số |
| --- | --- | --- |
| Embedding model | Model, D=768/1536 | nDCG/MRR, cost |
| ANN | numCandidates 50/100/200/500 | Recall@k, latency |
| Quantization | float/scalar/binary | Recall, Search RAM/disk, p99 |
| Index method | HNSW/flat | Exactness, latency, index size |
| Filter | 100%/40%/5%/0.2% | Recall, p95, result count |
| Concurrency | 1/10/50/100 | QPS, p99, errors |
| Cache | Cold/warm | Latency variance |
| Freshness | Insert/update/delete -> searchable | Index lag |
| Chunking | Chunk size/overlap | N vectors, relevance |
| Rerank/hybrid | Vector-only vs hybrid | nDCG/answer correctness |

Đổi **một nhóm biến mỗi lần**, giữ nguyên dataset, query mix và tài nguyên để không suy luận sai nguyên nhân.

### 23.3. Quy trình thử

1. Xác định SLO chất lượng/latency/freshness và cost budget.
2. Nạp corpus/query labels đại diện.
3. Tạo indexes, đợi trạng thái READY/queryable.
4. Warmup theo chế độ và ghi nhận cache state.
5. Chạy ENN baseline với cùng filter/metric.
6. Chạy ANN và tính overlap + relevance.
7. Tăng concurrency, thu p95/p99/QPS/errors.
8. Đo RAM/disk/index size/CPU/IOPS thực.
9. Chạy update/delete để đo index freshness.
10. Tính TCO và cost per useful answer.
11. So sánh scorecard rồi quyết định.

### 23.4. Không so sánh sai

- Dùng một câu hỏi mẫu duy nhất.
- Query vectors từ model khác indexed vectors.
- ANN và ENN dùng filter khác.
- Tính trung bình trên requests thành công nhưng bỏ lỗi timeout.
- Báo p99 từ 20 requests.
- So cold index với warm index.
- Coi ANN recall là human relevance.
- Báo Search index chỉ bằng source BSON vector payload.
- Bỏ qua Search nodes/reindex/backup.
- Không đo latency của embedding/reranking/LLM.
- Không kiểm soát ACL và search index freshness.

## 24. Scorecard ra quyết định

SLO ví dụ (**chỉ giả định**):

- Human nDCG@10 ≥ **0.78**.
- ANN recall@10 ≥ **0.92**.
- p95 vector query ≤ **120 ms**.
- p99 vector query ≤ **250 ms**.
- Không có kết quả vi phạm tenant/ACL.
- TCO nằm trong ngân sách.

Bảng kết quả **giả lập**, không phải benchmark của MongoDB:

| Candidate | nDCG@10 | ANN recall@10 | p95 ms | p99 ms | Search RAM GB | Cost/mo USD | Kết luận |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A float, candidates 200 | 0.83 | 0.97 | 110 | 210 | 28 | 1,500 | Đạt |
| B scalar, candidates 200 | 0.82 | 0.95 | 80 | 170 | 11 | 1,050 | Đạt |
| C binary, candidates 100 | 0.73 | 0.85 | 55 | 130 | 4 | 820 | Không đạt relevance |
| D binary+rescore, candidates 500 | 0.80 | 0.93 | 150 | 310 | 5 | 920 | Không đạt latency |
| E scalar, candidates 100 | 0.79 | 0.90 | 62 | 140 | 11 | 980 | Không đạt ANN recall |

Nếu chỉ xét bảng và các điều kiện trên, **B** là cấu hình rẻ hơn A nhưng vẫn đạt. Không chọn C chỉ vì rẻ, không chọn D chỉ vì RAM thấp. Nếu application có ngưỡng khác, quyết định cũng khác.

### 24.1. Pareto và tiêu chí bắt buộc

Một candidate có thể bị loại nếu một candidate khác có chất lượng bằng/tốt hơn, latency bằng/thấp hơn, cost bằng/thấp hơn và ít nhất một chiều trội hơn.

Nhưng các điều kiện **không được vi phạm** như ACL, dữ liệu nhạy cảm hoặc chính xác nghiệp vụ phải là *gates*, không được biến thành một số điểm cộng để bù bằng chi phí thấp.

## 25. Những tình huống thực tế

### 25.1. RAG tài liệu kỹ thuật nhiều mã lỗi

Kết hợp vector search, lexical search và rerank; đo nDCG/groundedness/citation correctness. Nếu query có exact identifier `ERR-1042`, không nên chỉ dựa vào semantic similarity.

### 25.2. Recommendation hàng triệu sản phẩm

HNSW và quantization có thể giảm RAM/query cost. Đo thêm diversity, near duplicates, isActive/stock, traffic spikes, index freshness và updates.

### 25.3. Tenant nhỏ, filter rất hẹp

Với vài trăm eligible vectors, ENN/flat có thể đáng cân nhắc. Cần đo thật thay vì mặc định ANN luôn nhanh.

### 25.4. Tìm hồ sơ cần độ đúng đắn cao

Nếu một false negative gây hậu quả nghiêm trọng, không chỉ tăng candidates; cân nhắc human review, hybrid retrieval, kiểm chứng kết quả và business rules.

### 25.5. Corpus tiếng Việt

Đánh giá query có dấu/không dấu, tên riêng, viết tắt, mã số và câu hỏi diễn đạt khác nhau. Model embedding đa ngôn ngữ không mặc định xử lý hoàn hảo mọi kiểu viết tiếng Việt.

## 26. Lỗi thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Score 0.9 là 90% đúng” | Score là độ gần, không phải xác suất | Qrels/calibration |
| “ANN recall 100% = search đúng ngữ nghĩa” | ENN chỉ exact theo metric | Human relevance |
| “20× limit bảo đảm recall” | Chỉ là điểm khởi đầu | Benchmark |
| “ENN luôn tốt hơn ANN cho mọi tải” | Exhaustive search tốn nhiều work | Chọn theo N/filter |
| “Filter càng hẹp càng nhanh” | HNSW filtered search có thể khó | Đo selectivity |
| “Post-filter top-k giống pre-filter” | Có thể trả rất ít kết quả | Filter trong `$vectorSearch` |
| “Không cần search index, chỉ lưu vector array” | `$vectorSearch` cần index/service hỗ trợ | Tạo index đúng |
| “Index vừa tạo dùng ngay” | Build có thể async | Đợi queryable |
| “Quantization giảm RAM/disk đúng 32×” | Graph/full-precision disk/rescore overhead | Đo actual RAM/disk |
| “Float32 chỉ tốn một nửa BSON disk luôn” | BSON và compression khác | Đo storage |
| “Một document là một vector” | Chunking tạo nhiều vectors | Size theo chunks |
| “D lớn hơn luôn đúng hơn” | Chất lượng phụ thuộc model | Golden set |
| “Cùng dimension dùng model khác được” | Không cùng embedding space | Versioned model |
| “Query nhanh một client thì chịu 100 QPS” | Queue/saturation | Load tests |
| “Average latency là đủ” | Tail p99 có thể tệ | p95/p99/errors |
| “Không cần tính rerank/LLM” | Đây là chi phí end-to-end | Trace/TCO |
| “Index refresh ngay mọi write” | Indexing có thể async | Freshness monitoring |
| “Score cao thì khỏi kiểm tra quyền” | Similarity không phải authorization | ACL authoritative |
| “Bản sao MongoDB là bản sao Search index tính sẵn” | Serving/index có topology riêng | Đo từng phần |
| “Đổi index/model miễn phí” | Reindex/re-embed có chi phí | Migration/runbook |

## 27. Bài tập thực hành

### Bài 1 — Relevance vs ANN accuracy

ANN recall@10 = 0.98 so với ENN nhưng human nDCG@10 = 0.42. Nên điều tra gì?

**Đáp án:** ANN không phải bottleneck chính; xem model, chunking, corpus, query intent và reranking.

### Bài 2 — Tính overlap

```text
ENN: [A,B,C,D,E]
ANN: [A,B,F,D,G]
```

ANN recall@5?

**Đáp án:** 3/5 = **0.6**.

### Bài 3 — Precision

Top-5 có relevance grades `[3,0,2,1,3]`, grade ≥2 được coi relevant. Precision@5?

**Đáp án:** 3/5 = **0.6**.

### Bài 4 — MRR

Kết quả relevant đầu tiên của ba queries xuất hiện ở rank 1, 2, 5. MRR?

**Đáp án:** \((1+1/2+1/5)/3=0.5667\).

### Bài 5 — Score

Một kết quả có vectorSearchScore=0.88. Có thể nói 88% khả năng câu trả lời đúng không?

**Đáp án:** Không; score không phải xác suất calibrated.

### Bài 6 — Candidates sweep

Ở limit=10, các cấu hình numCandidates 50/100/200/500 đạt recall 0.89/0.92/0.96/0.961 và p95 35/47/70/130 ms. Nếu cần recall≥0.95, p95≤100 ms, chọn gì?

**Đáp án:** `numCandidates=200`.

### Bài 7 — ENN dùng khi nào?

Đưa ra hai trường hợp chọn ENN thay ANN và hai trường hợp ANN thường phù hợp hơn. Vì sao ENN không đảm bảo relevance?

### Bài 8 — Pre-filter

Viết `$vectorSearch` chỉ trả tenant A và document active bằng pre-filter. Vì sao `$match` sau top-10 không tương đương?

### Bài 9 — Stage order

Có thể đặt `$match` trước `$vectorSearch` không?

**Đáp án:** `$vectorSearch` phải là stage đầu; dùng `filter` trong stage.

### Bài 10 — Float32 sizing

Một triệu vectors × 1536D × 4 bytes = bao nhiêu GB thập phân?

**Đáp án:** 6.144 GB payload.

### Bài 11 — Float64 vs Float32

Một triệu vectors 1536D: Double payload bao nhiêu, float32 payload bao nhiêu?

**Đáp án:** 12.288 GB và 6.144 GB, chưa kể BSON/index overhead.

### Bài 12 — Scalar/binary

Một vector 1536D dạng float32/int8/int1 có payload bao nhiêu?

**Đáp án:** 6144 B / 1536 B / 192 B.

### Bài 13 — Chunking

100.000 tài liệu, mỗi tài liệu 20 chunks. Nếu tăng thành 40 chunks, N vectors thay đổi thế nào?

**Đáp án:** 2 triệu → 4 triệu vectors; payload và số embedding calls lý tưởng tăng gấp đôi.

### Bài 14 — Quantization

Tại sao binary quantization giảm index RAM nhưng có thể vẫn cần nhiều disk? Rescoring có chi phí gì?

### Bài 15 — Little's Law

100 QPS với mean latency 100 ms tương đương average in-flight requests bao nhiêu?

**Đáp án:** 10 requests; không đảm bảo không có bursts/tails.

### Bài 16 — Serving cost

Hai Search Nodes $0.50/giờ, 720 giờ/tháng (giá giả định). Chi phí?

**Đáp án:** $720/tháng.

### Bài 17 — Embedding cost

Hai triệu chunks × 1.000 tokens, giá minh họa $0.05/triệu tokens. Chi phí?

**Đáp án:** 2 tỷ tokens, $100 theo đơn giá giả định.

### Bài 18 — Model migration

Đổi embedding model 768D sang 1536D. Nêu kế hoạch re-embed, index mới, canary, rollback, không trộn query/document vectors.

### Bài 19 — Index freshness và ACL

Một tài liệu vừa mất quyền truy cập nhưng Search index chưa đồng bộ. API phải làm gì để không lộ nội dung?

**Đáp án:** Xác minh quyền ở nguồn authoritative, không chỉ dựa Search index.

### Bài 20 — Benchmark production

Hãy lập kế hoạch benchmark có: golden queries, ENN baseline, ANN sweep, filters 0.2%–100%, concurrent clients, p95/p99, Search RAM/disk, freshness và TCO.

### Bài 21 — Scorecard

Theo bảng ở mục 24, candidate nào đáp ứng đồng thời nDCG≥0.78, ANN recall≥0.92, p95≤120, p99≤250? Nếu ưu tiên chi phí, chọn gì?

**Đáp án:** A và B đạt; B rẻ hơn trong ví dụ.

### Bài 22 — Hybrid retrieval

Tại sao query chứa mã lỗi `ERR-1042` có thể cần lexical search kết hợp vector search? Đo chất lượng và chi phí như thế nào?

## 28. Tổng kết

Đánh giá MongoDB Vector Search phải dựa trên **các trục độc lập nhưng liên hệ**:

1. **Độ phù hợp:** Precision@k, Recall@k, nDCG/MRR và golden qrels; không coi vectorSearchScore là xác suất đúng.
2. **ANN recall:** So ANN top-k với ENN top-k theo cùng metric, filter và index; `numCandidates` tạo trade-off recall–latency.
3. **Latency:** Đo embedding, MongoDB, hydration, rerank và toàn API, gồm p95/p99, QPS và concurrency.
4. **Bộ nhớ:** Tính payload `N×D×bytes`, sau đó thêm BSON, HNSW graph, Search index, filters, runtime, replicas và headroom.
5. **Chi phí:** Tính Search Nodes, source data, embedding, network, backup, reindex và RAG serving; tối ưu **cost per useful result**.
6. **Correctness:** Pre-filter theo tenant, xử lý Search index freshness, enforce ACL ở authoritative layer.

**Không có index format, dimension hoặc quantization nào tốt cho mọi corpus.** Hãy benchmark với dữ liệu và query thật, chọn cấu hình đạt SLO và giữ khả năng quan sát khi dữ liệu tăng.

### Tài liệu MongoDB chính thức

- [MongoDB Vector Search](https://www.mongodb.com/docs/vector-search/) — tổng quan kiến trúc.
- [Index Fields for MongoDB Vector Search](https://www.mongodb.com/docs/vector-search/indexes/vector-search-type/) — vector/filter fields, similarity, index method và quantization.
- [Run ANN and ENN Queries](https://www.mongodb.com/docs/vector-search/query/aggregation-stages/vector-search-stage/) — cú pháp `$vectorSearch`, `numCandidates`, `exact`, `filter`.
- [Explain Vector Search Results](https://www.mongodb.com/docs/vector-search/query/explain/) — query performance.
- [Vector Search Benchmark Overview](https://www.mongodb.com/docs/vector-search/benchmark/overview/) — index RAM/disk, quantization và testing.
- [Vector Search Benchmark Results](https://www.mongodb.com/docs/vector-search/benchmark/results/) — recall/latency/concurrency.
- [Vector Search Benchmark Tests](https://www.mongodb.com/docs/vector-search/benchmark/benchmark-tests/) — cách tiến hành benchmark.
- [Vector Search Deployment Options](https://www.mongodb.com/docs/vector-search/deployment/deployment-options/) — Search Nodes, RAM, disk và serving.
- [Vector Quantization](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-quantization/) — scalar/binary và rescoring.
- [BSON Binary Data](https://www.mongodb.com/docs/manual/reference/bson-types/) — source vector formats.
- [Aggregation `$project`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/) — loại field lớn khỏi results.
