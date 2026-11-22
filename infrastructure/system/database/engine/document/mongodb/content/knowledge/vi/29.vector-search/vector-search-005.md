# Tìm lân cận gần đúng, chính xác và lọc metadata theo hỗ trợ trong MongoDB Vector Search

## 1. Bài toán: tìm sản phẩm giống ý định, nhưng phải đúng điều kiện nghiệp vụ

Một hệ thống tìm căn hộ cho thuê có hàng trăm nghìn tin đăng. Người dùng nhập:

> “Căn hộ yên tĩnh, gần chỗ làm, có bàn làm việc và phù hợp làm việc từ xa.”

Những tin đăng phù hợp có thể dùng các câu chữ khác nhau: “cách âm tốt”, “góc làm việc riêng”, “internet ổn định”, “home office”. Tìm kiếm từ khóa thuần túy có thể bỏ qua một số kết quả liên quan về **ngữ nghĩa**.

Ứng dụng có thể chuyển mô tả tin đăng và câu truy vấn thành **embedding**: một dãy số biểu diễn đặc trưng ngữ nghĩa trong không gian nhiều chiều. Sau đó hệ thống tìm các vector **gần** vector của câu hỏi.

Nhưng không thể chỉ tìm “gần nhất” mà quên điều kiện thực tế. Người dùng còn yêu cầu:

- Thuộc **tenant được phép** xem.
- Tin đăng **đang hoạt động**.
- Thành phố **HCM**.
- Giá thuê **không quá 20 triệu đồng/tháng**.

Nếu tìm gần nhất trên toàn bộ hệ thống rồi mới bỏ những căn hộ sai tenant, sai thành phố hoặc vượt ngân sách, có thể còn rất ít kết quả, thậm chí bằng 0. Hơn nữa, với dữ liệu đa tenant, việc không ràng buộc quyền trước truy vấn là một lỗi thiết kế nghiêm trọng.

MongoDB Vector Search cho phép kết hợp:

1. **Approximate Nearest Neighbor (ANN):** tìm lân cận gần đúng để cân bằng tốc độ và độ bao phủ trên tập vector lớn.
2. **Exact Nearest Neighbor (ENN):** tìm lân cận chính xác theo phép đo tương đồng được cấu hình, trên tập vector đủ điều kiện tại thời điểm truy vấn.
3. **Metadata pre-filter:** giới hạn tập vector được xét bằng các field metadata đã được khai báo làm **filter** trong Vector Search index.

Sơ đồ luồng:

~~~text
Người dùng nhập truy vấn
           |
           v
Embedding model -> queryVector
           |
           +------------------------------+
           |                              |
           v                              v
Điều kiện nghiệp vụ                 Vector query
tenant, active, city, price         ANN hoặc ENN
           |                              |
           +--------------+---------------+
                          |
                          v
                 $vectorSearch stage
                  metadata pre-filter
                          |
                   Top-K theo score
                          |
                          v
              $project / $match / response
~~~

**Điểm chính:** ANN và ENN là **cách tìm lân cận**, còn metadata filter xác định **tập tài liệu nào được phép tham gia tìm kiếm**. Chúng phải được thiết kế cùng nhau nhưng không phải một lựa chọn duy nhất.

### Sau bài này, bạn sẽ làm được

- Hiểu **embedding**, **khoảng cách/tương đồng**, **top-K** và điều kiện metadata.
- Phân biệt **ANN** với **ENN**, khi nào dùng và trade-off recall/latency.
- Dùng **$vectorSearch** với **numCandidates**, **limit**, **exact** và **filter**.
- Tạo **Vector Search index** chứa trường vector và các trường filter.
- Phân biệt **prefilter trong $vectorSearch** với **$match sau $vectorSearch**.
- Xây dựng ví dụ **tìm tin đăng đúng tenant, trạng thái, khu vực, ngân sách**.
- Đánh giá **Recall@K**, độ trễ p95/p99, độ bao phủ của filter và tác động của numCandidates.
- Xử lý dữ liệu mới chưa được index, embedding sai chiều, thay đổi model và lỗi unsupported operator.
- Chạy lab mongosh với vector ba chiều có thể kiểm tra bằng phép tính thuần JavaScript.
- Chọn cấu hình phù hợp cho RAG, recommendation, tìm kiếm sản phẩm và các nhu cầu không đòi hỏi độ chính xác tuyệt đối giống nhau.

> **Phạm vi hỗ trợ:** MongoDB Vector Search và khả năng ANN/ENN phụ thuộc **loại triển khai, phiên bản MongoDB, phiên bản dịch vụ tìm kiếm và tính năng đã được bật**. Các ví dụ dùng cú pháp **$vectorSearch** và **Vector Search index** của những triển khai MongoDB hỗ trợ tính năng tương ứng, thường gặp trong MongoDB Atlas. Một **mongod standalone thông thường** hoặc một MongoDB server chưa có Vector Search không tự chạy được chỉ vì collection có Array số.

## 2. Vector là gì, và tại sao phải nhất quán model?

### 2.1. Embedding

Embedding là một vector số, ví dụ:

~~~javascript
{
  _id: "listing-1001",
  title: "Căn hộ có góc làm việc",
  embedding: [0.82, 0.12, -0.21, 0.35]
}
~~~

Trong ứng dụng thật, vector thường có hàng trăm hoặc hàng nghìn chiều, tùy model. Lab sẽ cố tình dùng **ba chiều** để người học có thể tự kiểm tra phép tính.

Một embedding model biến nội dung thành vector:

~~~text
Text / image / tài liệu
           |
     Embedding model
           |
           v
  [v1, v2, ..., vd]
~~~

Vector của một câu truy vấn phải được tạo bằng **model và quy trình preprocessing tương thích** với vector của dữ liệu đã index. Không thể kết hợp tùy ý:

- Document embedding được tạo bằng model A, 768 chiều.
- Query embedding được tạo bằng model B, 1.536 chiều.

Ngay cả khi **hai model cho cùng số chiều**, hệ tọa độ ngữ nghĩa của chúng cũng không mặc nhiên tương thích. Một truy vấn có thể trả kết quả nhưng ranking vô nghĩa.

### 2.2. Dimension

Nếu Vector Search index khai báo:

~~~javascript
numDimensions: 3
~~~

thì mỗi vector được index và query vector tương ứng phải phù hợp **ba chiều**. Vector chỉ có hai hoặc bốn giá trị không phải một vector ba chiều hợp lệ theo cấu hình đó.

Một trường vector cũng cần đúng kiểu dữ liệu và giá trị số theo các yêu cầu của bản MongoDB Vector Search đang dùng. Nên chặn **NaN**, **Infinity**, giá trị thiếu, mảng nested sai cấu trúc và vector không có ý nghĩa trước khi ghi.

### 2.3. Cosine similarity

Với hai vector không phải vector 0:

\[
\operatorname{cosine}(a,b)
=\frac{\sum_{i=1}^{d}a_i b_i}
{\sqrt{\sum_{i=1}^{d}a_i^2}\,\sqrt{\sum_{i=1}^{d}b_i^2}}
\]

Hai vector cùng hướng có cosine gần **1**, trực giao có cosine gần **0**, ngược hướng có cosine gần **-1**.

Lab dùng:

~~~javascript
const queryVector = [1, 0, 0];

const vectorA = [1, 0, 0];
const vectorB = [0.9, 0.1, 0];
const vectorC = [0, 1, 0];
~~~

Cosine(query, A) = **1**; cosine(query, B) gần **0,994**; cosine(query, C) = **0**.

**Quan trọng:** score được MongoDB trả qua **vectorSearchScore** có thể được chuẩn hóa/biến đổi theo metric. Không được giả định **score === cosine thô** hoặc mọi metric tạo điểm số cùng một thang diễn giải.

### 2.4. Dot product

Dot product:

\[
a\cdot b=\sum_{i=1}^{d}a_i b_i
\]

phụ thuộc cả hướng và độ lớn vector. Nếu model khuyến nghị normalize embeddings và dùng dotProduct, nên bảo đảm cách normalize đúng. Đừng chọn dotProduct chỉ vì tính nhanh hơn rồi bỏ qua ý nghĩa độ lớn.

### 2.5. Euclidean distance

Khoảng cách Euclid:

\[
d(a,b)=\sqrt{\sum_{i=1}^{d}(a_i-b_i)^2}
\]

Vector có khoảng cách **nhỏ hơn** được xem là gần hơn. Khi MongoDB tính vectorSearchScore cho metric Euclidean, cách biến đổi khoảng cách thành score phải được hiểu theo tài liệu phiên bản; không so sánh trực tiếp điểm này với điểm cosine của một index khác.

### 2.6. Chọn metric theo model

| Metric | Đặc tính | Câu hỏi thiết kế |
| --- | --- | --- |
| **cosine** | Quan tâm hướng vector | Model có được dùng/đánh giá bằng cosine không? |
| **dotProduct** | Phụ thuộc hướng và độ lớn | Embedding đã được normalize theo yêu cầu model chưa? |
| **euclidean** | Quan tâm khoảng cách hình học | Khoảng cách Euclid có ý nghĩa với representation này không? |

**Không có metric tốt nhất cho mọi model.** Hãy bắt đầu bằng khuyến nghị của nhà cung cấp embedding model và đánh giá offline trên chính bộ dữ liệu nghiệp vụ.

## 3. Top-K và sự khác nhau giữa “gần” và “đúng”

### 3.1. Top-K

Với câu hỏi:

~~~text
Tìm 5 căn hộ gần queryVector nhất.
~~~

K = **5**. MongoDB xếp hạng các vector phù hợp và trả tối đa số kết quả do **limit** yêu cầu.

Khi có filter:

~~~text
Chỉ xét tenant=t001, active=true, city=HCM, giá <= 20.
Trong tập này chọn tối đa 5 vector phù hợp nhất.
~~~

Top-K bây giờ là top của **tập đủ điều kiện**, không phải top của toàn bộ collection.

### 3.2. Hai cách trả sai kết quả

**Sai kiểu 1 — kết quả đúng vector nhưng sai nghiệp vụ:**

Tin đăng thuộc tenant khác có cosine rất cao. Nếu thiếu tenant filter, nó có thể xuất hiện trong top-K dù người dùng không được phép thấy.

**Sai kiểu 2 — dữ liệu hợp lệ nhưng không nằm trong top-K toàn cục:**

Giả sử top 20 toàn hệ thống đều đến từ thành phố khác. Nếu lấy top 20 rồi mới filter city=HCM, kết quả có thể rỗng, trong khi hệ thống thực sự có hàng nghìn tin HCM phù hợp.

Vì vậy, phải phân biệt **retrieval** và **filtering** trong pipeline.

### 3.3. Bốn tình huống thường gặp

| Tình huống | Nhu cầu | Hướng tiếp cận |
| --- | --- | --- |
| Tìm sản phẩm tương tự trong catalog rất lớn | Latency thấp, chấp nhận bỏ sót ít | **ANN + metadata pre-filter** |
| Kiểm tra kết quả chính xác trên tập nhỏ | Không muốn sai khác do thuật toán gần đúng | **ENN**, nếu deployment hỗ trợ |
| Đánh giá chất lượng index ANN | Có ground truth cho cùng filter/query | So ANN với **ENN** |
| Ràng buộc tenant, active, giá | Điều kiện bắt buộc trước ranking | **Filter trong $vectorSearch**, khi operator/field được hỗ trợ |

## 4. ANN — Approximate Nearest Neighbor

### 4.1. “Gần đúng” nghĩa là gì?

ANN sử dụng cấu trúc chỉ mục và thuật toán truy xuất để tìm **những vector rất gần** query vector mà không cần đánh giá chính xác mọi vector trong tập dữ liệu.

Một số hệ thống tìm kiếm vector, bao gồm các triển khai MongoDB Vector Search tương ứng, sử dụng cấu trúc gần đúng như **HNSW** hoặc các biến thể/chiến lược được tối ưu bởi dịch vụ. Chi tiết triển khai và kiểu lượng tử hóa có thể thay đổi theo phiên bản.

Hình dung:

~~~text
Tập vector rất lớn:
  V1 V2 V3 V4 ... V1,000,000

ENN:
  Đo/so sánh tất cả vector đủ điều kiện
  -> tìm top-K chính xác

ANN:
  Dùng cấu trúc index tìm các ứng viên tiềm năng
  -> đánh giá/xếp hạng ứng viên
  -> trả top-K gần đúng
~~~

**Gần đúng không có nghĩa MongoDB tính score một cách tùy tiện.** Nghĩa là thuật toán **có thể không xem xét mọi vector đủ điều kiện**, nên đôi khi bỏ qua một hàng xóm thật sự thuộc top-K.

### 4.2. Ưu điểm

- Thường phù hợp tập dữ liệu vector lớn.
- Latency thấp hơn ENN ở nhiều workload.
- Có thể điều chỉnh mức tìm kiếm để cân bằng **recall** và **chi phí**.
- Kết hợp được metadata pre-filter theo những toán tử được hỗ trợ.

### 4.3. Giới hạn

- Không hứa tìm đúng 100% top-K của metric.
- Kết quả có thể thay đổi khi index, thuật toán, dữ liệu hoặc tham số tìm kiếm thay đổi.
- Metadata filter có độ chọn lọc mạnh có thể ảnh hưởng cách ANN lấy ứng viên.
- Kết quả chịu tác động của embedding quality; ANN không sửa được model kém.

### 4.4. numCandidates

Trong **$vectorSearch** ở chế độ ANN, **numCandidates** điều khiển số ứng viên mà thuật toán sử dụng để tìm hàng xóm. Ví dụ:

~~~javascript
{
  $vectorSearch: {
    index: "vec314_listing_index",
    path: "embedding",
    queryVector: [1, 0, 0],
    numCandidates: 60,
    limit: 3
  }
}
~~~

Trong ví dụ:

- **limit = 3**: yêu cầu trả tối đa ba kết quả.
- **numCandidates = 60**: ngân sách tìm kiếm ứng viên phục vụ ANN, **không phải 60 kết quả trả về**.

Nhiều tài liệu MongoDB gợi ý bắt đầu thử **numCandidates khoảng 20 lần limit** rồi đánh giá/điều chỉnh. Đây là **điểm khởi đầu để benchmark**, không phải luật bảo đảm recall hay giá trị tối ưu cho mọi bộ lọc/dataset.

### 4.5. Đánh đổi

~~~text
numCandidates nhỏ
    -> thường ít công việc hơn
    -> có thể nhanh hơn
    -> nguy cơ bỏ sót top-K tăng

numCandidates lớn
    -> xét nhiều ứng viên hơn
    -> có thể cải thiện recall
    -> latency/CPU có thể tăng
~~~

Quan hệ này **không nhất thiết tuyến tính** trên mọi tập dữ liệu. Việc tăng gấp đôi numCandidates không đồng nghĩa tăng gấp đôi recall hoặc latency. Cần đo bằng tập truy vấn đại diện.

## 5. ENN — Exact Nearest Neighbor

### 5.1. Ý nghĩa

ENN tìm top-K chính xác theo metric được cấu hình **trên tập vector đủ điều kiện có trong chỉ mục/phạm vi truy vấn**. Nó là baseline hữu ích để so sánh độ bao phủ của ANN.

Ví dụ:

~~~javascript
{
  $vectorSearch: {
    index: "vec314_listing_index",
    path: "embedding",
    queryVector: [1, 0, 0],
    exact: true,
    limit: 3
  }
}
~~~

Khi đặt **exact: true**, không dùng **numCandidates** như chế độ ANN; phiên bản dịch vụ có thể yêu cầu bộ tham số khác nhau nên phải kiểm tra cú pháp được hỗ trợ.

### 5.2. “Chính xác” trong phạm vi nào?

ENN không biến mọi tài liệu trong MongoDB thành candidate bất kể điều kiện:

- Chỉ những vector **được index hợp lệ** và nằm trong **tập đủ điều kiện** mới có thể tham gia.
- **Metadata filter** có thể thu hẹp phạm vi trước khi tính top-K.
- Search index có thể cập nhật **bất đồng bộ**, nên tài liệu vừa ghi có thể chưa xuất hiện ngay trong chỉ mục.
- Vector sai số chiều/không được index không thể tự xuất hiện trong top-K.
- Kết quả chính xác phụ thuộc **metric** và **dữ liệu tại trạng thái index được truy vấn**, không phải một đáp án chân lý ngữ nghĩa của con người.

Vì vậy, **ENN là exact nearest neighbor trong không gian vector của dữ liệu đủ điều kiện**, không phải bảo đảm “kết quả phù hợp với ý người dùng tuyệt đối”.

### 5.3. Khi dùng ENN?

- Tập dữ liệu **nhỏ** hoặc filter rất chọn lọc.
- Đòi ranking gần nhất chính xác theo metric.
- Dùng làm **ground truth** để đo Recall@K của ANN.
- Debug query có kết quả ANN không như mong đợi.
- Một số workflow offline cần ổn định kết quả theo metric.

### 5.4. Trade-off

Nếu phải xem xét rất nhiều vector có số chiều lớn, ENN có thể tốn CPU/latency nhiều hơn. Không nên bật exact:true cho tất cả request production chỉ để cảm giác “chất lượng hơn”, nhất là nếu một ứng dụng có hàng triệu tài liệu và latency yêu cầu vài chục mili giây.

### 5.5. Hỗ trợ theo phiên bản

Chế độ ENN trong MongoDB Vector Search được cung cấp trong **các phiên bản/triển khai hỗ trợ exact vector search**; không phải mọi cluster đã bật ANN đều mặc nhiên có ENN.

Nếu chạy **exact: true** và nhận lỗi unsupported option:

1. Kiểm tra phiên bản MongoDB, dịch vụ Search và deployment.
2. Xem tài liệu MongoDB Vector Search **đúng phiên bản**.
3. Không tự thay exact:true bằng một numCandidates rất lớn rồi tuyên bố kết quả “chính xác”.
4. Với bộ dữ liệu nhỏ của lab, có thể dùng **phép tính thuần JavaScript** làm baseline minh họa khi ENN chưa được hỗ trợ.

## 6. Định nghĩa Vector Search index có vector field và filter fields

### 6.1. Index vector khác B-tree index

Một index thông thường:

~~~javascript
db.listings.createIndex({ tenantId: 1, city: 1 });
~~~

không tự biến field embedding thành vector search index. Để chạy **$vectorSearch**, collection cần một **Vector Search index** được định nghĩa theo schema dành cho chức năng vector search của deployment.

Ví dụ definition:

~~~javascript
{
  fields: [
    {
      type: "vector",
      path: "embedding",
      numDimensions: 3,
      similarity: "cosine"
    },
    {
      type: "filter",
      path: "tenantId"
    },
    {
      type: "filter",
      path: "city"
    },
    {
      type: "filter",
      path: "isActive"
    },
    {
      type: "filter",
      path: "rentMillion"
    }
  ]
}
~~~

Giải thích:

- **vector/path**: field chứa embeddings.
- **numDimensions**: số chiều mà index mong đợi.
- **similarity**: metric so sánh.
- **type:"filter"**: các field metadata được phép dùng để lọc trong **$vectorSearch.filter** theo những semantics hỗ trợ.

**Một field có mặt trong document không có nghĩa nó tự dùng được trong $vectorSearch.filter.** Nó cần được khai báo theo khả năng của Vector Search index.

### 6.2. Tại sao phải khai báo filter fields riêng?

Giả sử document có:

~~~javascript
{
  tenantId: "t001",
  city: "HCM",
  isActive: true,
  rentMillion: 12,
  embedding: [1, 0, 0]
}
~~~

Nếu Vector Search index chỉ có trường embedding, truy vấn:

~~~javascript
filter: {
  tenantId: "t001",
  city: "HCM"
}
~~~

có thể không được thực thi theo mong đợi hoặc phát lỗi vì **tenantId/city không nằm trong định nghĩa filter của index**. Cần thêm các field vào index definition rồi đợi trạng thái index đủ sẵn sàng theo dịch vụ.

Một **B-tree index trên tenantId** không thay thế tự động cho **type:"filter"** trong Vector Search index.

### 6.3. Kiểu dữ liệu cho filter

Các Vector Search deployments hỗ trợ một nhóm kiểu metadata tương ứng, thường gồm **string, boolean, số, date, ObjectId hoặc các kiểu khác tùy phiên bản**.

Không được giả định:

- Một object metadata lồng sâu bất kỳ đều lọc được như find().
- Regex, text search, $expr, arbitrary JavaScript hay mọi aggregation expression đều dùng được bên trong filter.
- Array/nested array có mọi semantics giống query thông thường.
- Null/missing và mixed-type data được xử lý y hệt ở mọi phiên bản.

Để tránh lỗi khó truy vết, chọn metadata có **kiểu ổn định**:

~~~javascript
tenantId: "t001"      // String
city: "HCM"           // String
isActive: true        // Boolean
rentMillion: 12       // Number
~~~

**Tránh** lưu rentMillion đôi lúc là "12" String, lúc khác là 12 Number. So sánh số học, range filter và index có thể cho kết quả khác hoặc không được hỗ trợ theo cách bạn dự tính.

### 6.4. Tạo Search index

Trên phiên bản mongosh/driver và deployment hỗ trợ quản lý Search indexes, có thể tạo index bằng lệnh tương ứng:

~~~javascript
const lab = db.getSiblingDB("mongo_vector_lab_314");
const listings = lab.getCollection("lab_listings");

listings.createSearchIndex({
  name: "vec314_listing_index",
  type: "vectorSearch",
  definition: {
    fields: [
      {
        type: "vector",
        path: "embedding",
        numDimensions: 3,
        similarity: "cosine"
      },
      { type: "filter", path: "tenantId" },
      { type: "filter", path: "city" },
      { type: "filter", path: "isActive" },
      { type: "filter", path: "rentMillion" }
    ]
  }
});
~~~

**Điều kiện:**

- Deployment hỗ trợ tạo và sử dụng Vector Search index.
- Có quyền quản lý Search index.
- Collection đã tồn tại và embeddings đúng cấu trúc.
- Chưa có index cùng tên theo cấu hình khác.

Trên MongoDB Atlas, cũng có thể tạo **Vector Search index** bằng giao diện/JSON definition tương ứng. Không đưa JSON index definition vào **createIndex() B-tree** rồi mong $vectorSearch sử dụng được.

### 6.5. Index build bất đồng bộ

Sau yêu cầu tạo hoặc cập nhật Vector Search index, index có thể cần thời gian xây dựng và đồng bộ. Vì vậy:

~~~text
createSearchIndex() hoàn tất lời gọi
             |
             v
    Index đang được xây dựng
             |
             v
   Index chuyển sang trạng thái sẵn sàng
             |
             v
        $vectorSearch
~~~

Trên phiên bản mongosh hỗ trợ:

~~~javascript
printjson(listings.getSearchIndexes());
~~~

Quan sát tên, definition và trạng thái của index. Những field trạng thái/output có thể khác nhau theo phiên bản dịch vụ. **Không dựa vào việc lệnh createSearchIndex trả kết quả để kết luận index đã truy vấn được ngay lập tức.**

## 7. $vectorSearch: các tham số trọng tâm

### 7.1. ANN

~~~javascript
db.lab_listings.aggregate([
  {
    $vectorSearch: {
      index: "vec314_listing_index",
      path: "embedding",
      queryVector: [1, 0, 0],
      numCandidates: 60,
      limit: 5
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      city: 1,
      rentMillion: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]);
~~~

Các field:

| Field | Ý nghĩa |
| --- | --- |
| **index** | Tên Vector Search index cần dùng |
| **path** | Field chứa vector; phải tương ứng index definition |
| **queryVector** | Embedding của truy vấn, đúng dimension/type |
| **numCandidates** | Ngân sách ứng viên của ANN |
| **limit** | Số hàng xóm tối đa muốn nhận |
| **filter** | Điều kiện metadata pre-filter được hỗ trợ |
| **exact** | Chọn chế độ exact khi hỗ trợ |

### 7.2. ENN

~~~javascript
db.lab_listings.aggregate([
  {
    $vectorSearch: {
      index: "vec314_listing_index",
      path: "embedding",
      queryVector: [1, 0, 0],
      exact: true,
      limit: 5
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]);
~~~

**Không gắn numCandidates vào ví dụ ENN**. Trong ANN, numCandidates là tham số quan trọng; trong ENN, exact:true xác định cách tìm kiếm khác.

### 7.3. $vectorSearch phải ở vị trí được hỗ trợ

Trong pipeline **aggregate** thông thường, **$vectorSearch phải là stage đầu tiên** theo quy tắc áp dụng cho tính năng này.

**Không đúng:**

~~~javascript
db.lab_listings.aggregate([
  { $match: { tenantId: "t001" } },
  {
    $vectorSearch: {
      index: "vec314_listing_index",
      path: "embedding",
      queryVector: [1, 0, 0],
      numCandidates: 60,
      limit: 5
    }
  }
]);
~~~

**Đúng hơn:** đưa điều kiện metadata được hỗ trợ vào **filter** bên trong $vectorSearch.

~~~javascript
db.lab_listings.aggregate([
  {
    $vectorSearch: {
      index: "vec314_listing_index",
      path: "embedding",
      queryVector: [1, 0, 0],
      numCandidates: 60,
      limit: 5,
      filter: { tenantId: "t001" }
    }
  }
]);
~~~

Một số khả năng đặt $vectorSearch trong các tổ hợp pipeline khác thay đổi theo phiên bản; không tự suy diễn rằng có thể đưa nó vào mọi subpipeline của $facet/$lookup.

### 7.4. Score

Truy xuất score bằng:

~~~javascript
{
  $project: {
    title: 1,
    score: { $meta: "vectorSearchScore" }
  }
}
~~~

Đọc score theo thứ tự **cao hơn thường nghĩa là phù hợp hơn** với metric và scoring hiện tại của Vector Search. Không kết luận:

- Score 0,85 nghĩa là **85% xác suất người dùng thích sản phẩm**.
- Score 0,85 giữa hai embedding models khác nhau là tương đương.
- Score của cosine có thể so trực tiếp với score của Euclidean.
- Một ngưỡng score cố định áp dụng cho mọi loại câu hỏi.

Score là **tín hiệu ranking**, cần hiệu chuẩn/đánh giá theo tác vụ.

## 8. Metadata pre-filter: tìm đúng tập dữ liệu trước khi xếp hạng

### 8.1. Ví dụ nhiều điều kiện

~~~javascript
const filter = {
  $and: [
    { tenantId: "t001" },
    { city: "HCM" },
    { isActive: true },
    { rentMillion: { $lte: 20 } }
  ]
};
~~~

Đây là một filter gồm:

- Equality theo tenant.
- Equality theo thành phố.
- Boolean active.
- Range theo giá.

Các field phải có cấu hình **type:"filter"** trong Vector Search index, và các operators dùng phải được deployment hỗ trợ.

### 8.2. Kết hợp ANN và pre-filter

~~~javascript
const results = listings.aggregate([
  {
    $vectorSearch: {
      index: "vec314_listing_index",
      path: "embedding",
      queryVector: [1, 0, 0],
      numCandidates: 60,
      limit: 3,
      filter: {
        $and: [
          { tenantId: "t001" },
          { city: "HCM" },
          { isActive: true },
          { rentMillion: { $lte: 20 } }
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      tenantId: 1,
      city: 1,
      rentMillion: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]).toArray();

printjson(results);
~~~

**Lưu ý projection:** $project trong pipeline trên liệt kê các field cần trả và tính **score**; field embedding không được liệt kê nên không xuất hiện trong output. Tránh trộn inclusion projection với exclusion không phải _id trong cùng một $project thông thường.

### 8.3. Pre-filter không có nghĩa chạy một B-tree find trước

Khi dùng **filter trong $vectorSearch**, metadata được xử lý trong cơ chế tìm kiếm vector/index tương ứng. Nó **không** có nghĩa MongoDB tự thực thi:

~~~javascript
db.listings.find({ tenantId: "t001" })
~~~

trên một B-tree index độc lập, rồi áp một phép tính vector thuần túy như hai câu lệnh ghép trong ứng dụng. Chiến lược nội bộ phụ thuộc dịch vụ và bộ index Vector Search.

### 8.4. Không phải mọi toán tử find() đều dùng được trong filter

Những toán tử thông dụng có thể được hỗ trợ trong các phiên bản tương ứng gồm equality, so sánh/range, tập hợp như **$in** và kết hợp logic **$and/$or/$not** theo cú pháp được tài liệu cho phép.

Không mặc định những cấu trúc dưới đây hợp lệ trong **$vectorSearch.filter**:

~~~javascript
// Những ví dụ KHÔNG được tự coi là pre-filter hỗ trợ:
{ title: { $regex: "studio" } }
{ $expr: { $gt: ["$rentMillion", "$depositMillion"] } }
{ description: { $text: { $search: "quiet" } } }
~~~

Với regex/full-text search hoặc biểu thức tính toán, cân nhắc:

1. Tiền xử lý thành metadata được index hợp lệ.
2. Một search pipeline khác, nếu deployment hỗ trợ tính năng hybrid/search phù hợp.
3. **Post-filter** sau Vector Search với hiểu biết về top-K bị hao hụt.
4. Thiết kế precomputed fields/read model thay vì gọi expression phức tạp tại lúc search.

### 8.5. Kết hợp các filters có giá trị thiếu

Giả sử một số tin đăng thiếu city. Filter:

~~~javascript
{ city: "HCM" }
~~~

chỉ nên được hiểu là lựa chọn những document đáp ứng equality này theo semantics của Vector Search index. Không tự mở rộng nó sang document missing city.

Với metadata có thể null/missing, cần xác định dữ liệu nên:

- Không xuất hiện cho tới khi bổ sung metadata.
- Được nhập giá trị sentinel được quản lý riêng.
- Nằm trong một chỉ mục/luồng xử lý khác.

**Đừng dùng wildcard hoặc $exists trong filter mà chưa xác minh toán tử được hỗ trợ**, nhất là khi logic quyền truy cập phụ thuộc vào nó.

## 9. Pre-filter so với post-filter: lỗi top-K thường gặp

### 9.1. Post-filter sau vector retrieval

Ví dụ:

~~~javascript
listings.aggregate([
  {
    $vectorSearch: {
      index: "vec314_listing_index",
      path: "embedding",
      queryVector: [1, 0, 0],
      numCandidates: 60,
      limit: 3
    }
  },
  {
    $match: {
      tenantId: "t001",
      city: "HCM",
      isActive: true,
      rentMillion: { $lte: 20 }
    }
  }
]);
~~~

Ở đây, **$vectorSearch tìm top 3 trên toàn bộ corpus**, rồi $match mới loại các kết quả không đáp ứng metadata.

Nếu top 3 toàn corpus đều thuộc tenant khác hoặc tin inactive, kết quả sau $match có thể là **0**, mặc dù trong collection vẫn có nhiều tin đáp ứng yêu cầu.

### 9.2. Pre-filter đúng mục tiêu

~~~javascript
listings.aggregate([
  {
    $vectorSearch: {
      index: "vec314_listing_index",
      path: "embedding",
      queryVector: [1, 0, 0],
      numCandidates: 60,
      limit: 3,
      filter: {
        tenantId: "t001",
        city: "HCM",
        isActive: true,
        rentMillion: { $lte: 20 }
      }
    }
  }
]);
~~~

Mục đích ở đây là **xếp hạng những hàng xóm trong tập tin đăng đủ điều kiện**.

### 9.3. Lấy nhiều rồi lọc sau có sửa được không?

Một workaround hay gặp là:

~~~text
Tìm top 100 trên toàn corpus
Lọc tenant/city/budget
Trả 5
~~~

Nó có thể giảm tỷ lệ trả rỗng trong một số workload, nhưng **không đảm bảo top 5 đúng** nếu kết quả đủ điều kiện nằm ngoài top 100 toàn corpus. Nó còn lãng phí tính toán và làm phức tạp an toàn đa tenant.

Khi filter được hỗ trợ, **prefilter là lựa chọn đúng về semantics**. Post-filter chỉ nên dùng cho các điều kiện thực sự không được Vector Search filter hỗ trợ, với chính sách rõ về số kết quả có thể bị giảm.

### 9.4. Bảo mật đa tenant

Điều kiện:

~~~javascript
tenantId: "t001"
~~~

phải đến từ **identity/security context được xác thực bởi server**, không lấy nguyên văn từ query parameter không đáng tin.

Một thiết kế an toàn còn cần:

- Quyền database/collection đúng phạm vi.
- Kiểm soát truy cập trước khi sinh query.
- Test rò rỉ qua các kiểu query khác nhau.
- Không đưa dữ liệu tenant khác vào reranking/service log.
- Không lấy kết quả chưa lọc về app rồi mới loại khi có thể lọc tại truy vấn.

**Metadata filter là một phần của thực thi policy, không phải hệ thống ủy quyền độc lập.** Nếu ứng dụng có quyền đọc toàn collection và lỡ bỏ tenantId, MongoDB không tự biết user nào đang đăng nhập ứng dụng.

## 10. Lab mongosh: 10 tin đăng và vector ba chiều

### 10.1. Kết quả học tập

Lab có các mục tiêu:

1. Tạo mười document có embedding **ba chiều**.
2. Tạo Vector Search index có field vector và bốn metadata filters.
3. Chạy ANN và ENN trên cùng query/filter.
4. Tính top-K bằng JavaScript thuần để hiểu thứ tự chính xác.
5. So sánh filter bên trong và bên ngoài $vectorSearch.

### 10.2. Điều kiện

- MongoDB deployment **có Vector Search** theo cú pháp bài học.
- Có quyền insert/update vào database lab và quản lý Vector Search indexes.
- Index ở trạng thái **READY/usable** trước khi chạy vector query.
- Embedding là **vector đồ chơi**, không tạo bằng model AI thật và không mang ý nghĩa ngữ nghĩa của văn bản.
- Không chạy trên collection production, không xóa search indexes ngoài bài.

### 10.3. Bộ dữ liệu cố định

Mọi vector đều có dạng [x, y, 0]; query vector là [1, 0, 0].

| ID | Tenant | City | Active | Giá (triệu/tháng) | Embedding |
| --- | --- | --- | --- | ---: | --- |
| **v314-a** | t001 | HCM | true | 12 | [1,0,0] |
| **v314-b** | t001 | HCM | true | 16 | [0.9,0.1,0] |
| **v314-c** | t001 | HCM | true | 25 | [0.98,0.02,0] |
| **v314-d** | t001 | HN | true | 14 | [0.99,0.01,0] |
| **v314-e** | t002 | HCM | true | 11 | [1,0,0] |
| **v314-f** | t001 | HCM | false | 10 | [0.999,0.001,0] |
| **v314-g** | t001 | HCM | true | 18 | [0.7,0.3,0] |
| **v314-h** | t001 | HCM | true | 9 | [0,1,0] |
| **v314-i** | t001 | HCM | true | 12 | [0.4,0.6,0] |
| **v314-j** | t001 | HCM | true | 20 | [0.2,0.8,0] |

Điều kiện tìm kiếm:

~~~javascript
{
  tenantId: "t001",
  city: "HCM",
  isActive: true,
  rentMillion: { $lte: 20 }
}
~~~

Tập **đủ điều kiện** là **a, b, g, h, i, j**.

**c** bị loại do giá; **d** sai city; **e** sai tenant; **f** không active.

### 10.4. Seed idempotent có kiểm soát

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_vector_lab_314");
  const listings = lab.getCollection("lab_listings");
  const tag = "vector314-v1";

  const records = [
    ["v314-a", "t001", "HCM", true, 12, [1, 0, 0], "Home office A"],
    ["v314-b", "t001", "HCM", true, 16, [0.9, 0.1, 0], "Quiet B"],
    ["v314-c", "t001", "HCM", true, 25, [0.98, 0.02, 0], "Premium C"],
    ["v314-d", "t001", "HN", true, 14, [0.99, 0.01, 0], "Hanoi D"],
    ["v314-e", "t002", "HCM", true, 11, [1, 0, 0], "Other tenant E"],
    ["v314-f", "t001", "HCM", false, 10, [0.999, 0.001, 0], "Inactive F"],
    ["v314-g", "t001", "HCM", true, 18, [0.7, 0.3, 0], "Work corner G"],
    ["v314-h", "t001", "HCM", true, 9, [0, 1, 0], "Garden H"],
    ["v314-i", "t001", "HCM", true, 12, [0.4, 0.6, 0], "Balcony I"],
    ["v314-j", "t001", "HCM", true, 20, [0.2, 0.8, 0], "Studio J"]
  ];

  for (const r of records) {
    listings.updateOne(
      { _id: r[0], labTag: tag },
      {
        $set: {
          labTag: tag,
          tenantId: r[1],
          city: r[2],
          isActive: r[3],
          rentMillion: r[4],
          embedding: r[5],
          title: r[6],
          embeddingModel: "toy-3d-v1"
        }
      },
      { upsert: true }
    );
  }

  printjson({
    count: listings.countDocuments({ labTag: tag }),
    sample: listings.find(
      { labTag: tag },
      { _id: 1, city: 1, rentMillion: 1, embedding: 1 }
    ).sort({ _id: 1 }).limit(3).toArray()
  });
})();
~~~

**Kết quả mong đợi:** count = **10**.

Script sử dụng **updateOne/upsert** với các ID cố định, nên có thể chạy lại để trả các field mẫu về giá trị ban đầu. Nó không drop database/collection. Tuy nhiên, nếu trong cùng database đã có tài liệu khác trùng _id mà không có labTag tương ứng, upsert có thể gặp duplicate key: phải dừng điều tra thay vì sửa dữ liệu không thuộc bài.

### 10.5. Tạo Vector Search index

Sau khi seed:

~~~javascript
const lab = db.getSiblingDB("mongo_vector_lab_314");
const listings = lab.getCollection("lab_listings");

listings.createSearchIndex({
  name: "vec314_listing_index",
  type: "vectorSearch",
  definition: {
    fields: [
      {
        type: "vector",
        path: "embedding",
        numDimensions: 3,
        similarity: "cosine"
      },
      { type: "filter", path: "tenantId" },
      { type: "filter", path: "city" },
      { type: "filter", path: "isActive" },
      { type: "filter", path: "rentMillion" }
    ]
  }
});
~~~

Nếu có index cùng tên, không tạo tiếp một bản trùng hoặc xóa index hiện có bừa bãi. Kiểm tra definition bằng:

~~~javascript
printjson(listings.getSearchIndexes());
~~~

Chỉ chạy $vectorSearch sau khi index ở trạng thái sẵn sàng. Một số phiên bản có helper/command quản lý Search index khác nhau; nếu không có **createSearchIndex** trong mongosh, sử dụng giao diện Atlas hoặc API index management phù hợp với deployment.

### 10.6. Tính top-K chính xác bằng JavaScript thuần

Đây là phần có thể chạy ngay cả khi cluster lab chưa hỗ trợ Vector Search, vì chỉ dùng **find()** và phép tính JavaScript trên mười document:

~~~javascript
const queryVector = [1, 0, 0];
const tag = "vector314-v1";

function cosineSimilarity(a, b) {
  if (!Array.isArray(a) ||
      !Array.isArray(b) ||
      a.length !== b.length ||
      a.length === 0) {
    throw new Error("Vector không có cùng số chiều hợp lệ.");
  }

  let dot = 0;
  let normA = 0;
  let normB = 0;

  for (let i = 0; i < a.length; i++) {
    const x = a[i];
    const y = b[i];
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      throw new Error("Vector chứa giá trị không hữu hạn.");
    }
    dot += x * y;
    normA += x * x;
    normB += y * y;
  }

  if (normA === 0 || normB === 0) {
    throw new Error("Cosine không xác định cho zero vector.");
  }

  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}

const candidates = listings.find({
  labTag: tag,
  tenantId: "t001",
  city: "HCM",
  isActive: true,
  rentMillion: { $lte: 20 }
}).toArray();

const ranked = candidates.map(d => ({
  _id: d._id,
  title: d.title,
  rawCosine: cosineSimilarity(queryVector, d.embedding)
})).sort((a, b) => {
  const scoreDifference = b.rawCosine - a.rawCosine;
  return scoreDifference !== 0
    ? scoreDifference
    : a._id.localeCompare(b._id);
});

printjson(ranked);
printjson({
  exactTop3: ranked.slice(0, 3).map(d => d._id)
});
~~~

**Kết quả top 3 mong đợi:**

~~~text
v314-a
v314-b
v314-g
~~~

Thứ tự còn lại theo raw cosine:

~~~text
v314-i
v314-j
v314-h
~~~

Giải thích:

- a khớp hoàn toàn hướng queryVector.
- b rất gần query.
- g gần hơn i/j/h.
- c/d/e/f có thể cực gần nhưng **bị loại bởi filter**.

Đây là phép tính **exact tham khảo trên mười document lab**, không phải thay thế cho thuật toán ENN tối ưu của server ở dữ liệu lớn.

### 10.7. ANN với pre-filter

~~~javascript
const ann = listings.aggregate([
  {
    $vectorSearch: {
      index: "vec314_listing_index",
      path: "embedding",
      queryVector: [1, 0, 0],
      numCandidates: 60,
      limit: 3,
      filter: {
        tenantId: "t001",
        city: "HCM",
        isActive: true,
        rentMillion: { $lte: 20 }
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      rentMillion: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]).toArray();

printjson(ann);
~~~

Với mười vector và numCandidates khá lớn so với corpus, **ANN thường sẽ tìm được top 3 như baseline**, nhưng đây không phải cam kết toán học của ANN. Nếu kết quả khác, kiểm tra index readiness, filter, queryVector, version và khả năng approximate retrieval.

### 10.8. ENN với cùng pre-filter

~~~javascript
const enn = listings.aggregate([
  {
    $vectorSearch: {
      index: "vec314_listing_index",
      path: "embedding",
      queryVector: [1, 0, 0],
      exact: true,
      limit: 3,
      filter: {
        tenantId: "t001",
        city: "HCM",
        isActive: true,
        rentMillion: { $lte: 20 }
      }
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
~~~

**Nếu deployment hỗ trợ ENN và Search index đã đồng bộ mười records**, top 3 nên là **v314-a, v314-b, v314-g**, cùng thứ tự theo cosine thô ở baseline. Có thể có chênh lệch nhỏ về score do công thức chuyển đổi/biểu diễn số; hãy so **ID và thứ tự top-K** trước khi so giá trị score.

### 10.9. So sánh post-filter

~~~javascript
const afterFilter = listings.aggregate([
  {
    $vectorSearch: {
      index: "vec314_listing_index",
      path: "embedding",
      queryVector: [1, 0, 0],
      exact: true,
      limit: 3
    }
  },
  {
    $match: {
      tenantId: "t001",
      city: "HCM",
      isActive: true,
      rentMillion: { $lte: 20 }
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

printjson(afterFilter);
~~~

**Mục tiêu bài lab:** quan sát rằng top 3 **toàn corpus** có thể bị chiếm bởi a/e/f/d/c vì chúng có hướng vector gần [1,0,0], nhưng nhiều document trong số đó **không đủ điều kiện**. Vì thế, sau $match có thể chỉ còn một vài kết quả, không phải ba document tốt nhất trong tập hợp hợp lệ.

Nếu môi trường không hỗ trợ ENN, thay **exact:true** bằng tham số ANN hợp lệ để quan sát vấn đề post-filter về mặt ý nghĩa, nhưng không được gọi kết quả ANN là “ground truth”.

### 10.10. Vì sao lab nhỏ không phải benchmark

Mười vector ba chiều:

- Không đo được hiệu năng trên một triệu vector 1.536 chiều.
- Không phản ánh phân bố metadata thực tế.
- Không chứng minh numCandidates nào phù hợp production.
- Không phản ánh chi phí index build, quantization và cập nhật liên tục.

Lab dùng để hiểu **semantics**. Việc lựa chọn cấu hình production cần một bộ truy vấn/đánh giá riêng.

## 11. Đo recall của ANN bằng ENN

### 11.1. Recall@K

Cho:

- **E_K**: tập ID top-K do ENN trả trên cùng filter/query.
- **A_K**: tập ID top-K do ANN trả trên cùng filter/query.

Khi cả hai có đủ K kết quả:

\[
\operatorname{Recall@K}
=\frac{|A_K\cap E_K|}{K}
\]

Ví dụ:

~~~text
ENN top 5 = [A, B, C, D, E]
ANN top 5 = [A, B, X, D, Y]

Giao = [A, B, D] -> Recall@5 = 3/5 = 0,6
~~~

Nếu tập đủ điều kiện có ít hơn K document, nên định nghĩa mẫu số theo số kết quả exact khả dụng hoặc tách trường hợp này trong báo cáo; không tùy tiện coi ANN “thiếu K” là lỗi retrieval khi bản thân corpus chỉ có hai ứng viên.

### 11.2. Đánh giá nhiều truy vấn

Một query test đơn lẻ có thể may mắn. Hãy xây tập:

- Truy vấn ngắn/dài.
- Truy vấn phổ biến và hiếm.
- Các mức metadata selectivity khác nhau.
- Tập tenant nhỏ và tenant lớn.
- Các loại giá/budget khác nhau.
- Các trường hợp nội dung tương đồng cao, gần đồng nghĩa hoặc có nhiều sản phẩm gần nhau.

Sau đó:

~~~text
Với mỗi query:
  1. Tạo query embedding cố định.
  2. Cố định filter.
  3. Lấy ENN top-K.
  4. Lấy ANN top-K ở từng numCandidates.
  5. Tính Recall@K.
  6. Đo latency và resource.

Tổng hợp:
  recall trung bình, recall p10,
  latency p50/p95/p99,
  số query thiếu kết quả, tỉ lệ timeout.
~~~

### 11.3. Code so top-K IDs

~~~javascript
function recallAtK(annIds, exactIds, k) {
  const exact = exactIds.slice(0, k);
  const approximate = annIds.slice(0, k);
  const denominator = Math.min(k, exact.length);
  if (denominator === 0) return 1;

  const annSet = new Set(approximate);
  const hits = exact.filter(id => annSet.has(id)).length;
  return hits / denominator;
}

print(recallAtK(
  ["A", "B", "X", "D", "Y"],
  ["A", "B", "C", "D", "E"],
  5
)); // 0.6
~~~

Hàm minh họa đánh giá **set overlap**, không xét đúng thứ tự ranking. Nếu nghiệp vụ quan tâm vị trí top 1/top 3, cần bổ sung các metric như **MRR, nDCG hoặc precision theo đánh giá người dùng**, không chỉ Recall@K.

### 11.4. Recall cao chưa chắc tốt cho sản phẩm

Một ANN có Recall@10 = 0,98 so với ENN nhưng cả hai trả những căn hộ không liên quan vì embedding model kém hoặc corpus thiếu nội dung tốt. **Recall so với ENN đo độ gần của thuật toán retrieval so với ranking vector chính xác**, không đo độ hài lòng người dùng.

Chất lượng thực tế cần:

- Relevance labels do người/đội nghiệp vụ đánh giá.
- CTR, conversion, save/contact rate.
- Latency và tỷ lệ thiếu kết quả.
- Thử nghiệm online/offline có kiểm soát.

## 12. Chọn numCandidates trong ANN

### 12.1. Ma trận thử nghiệm

Với limit=10, có thể bắt đầu benchmark các giá trị:

| Thử nghiệm | limit | numCandidates | Câu hỏi |
| --- | ---: | ---: | --- |
| A | 10 | 50 | Có nhanh nhưng recall thấp không? |
| B | 10 | 100 | Trade-off thế nào? |
| C | 10 | 200 | Recall có cải thiện đủ so với latency? |
| D | 10 | 400 | Có đạt vùng lợi ích giảm dần không? |

Các giá trị phải **tuân thủ giới hạn của bản MongoDB Vector Search đang dùng**, đặc biệt quan hệ hợp lệ giữa numCandidates/limit và giới hạn tối đa mà dịch vụ công bố. Đây là tập tham số benchmark minh họa, không phải lời khuyên sản xuất mặc định.

### 12.2. Filter selectivity

Giả sử:

~~~text
Corpus: 1.000.000 vector

Filter A:
  city=HCM -> 200.000 vector

Filter B:
  tenantId=t001, city=HCM, active=true, budget<=20
  -> 350 vector
~~~

ANN trên hai tập có profile hiệu năng/recall khác nhau. Với filter cực hẹp, **ENN trên vài trăm vector** có thể hợp lý. Với filter rộng, ANN có thể phù hợp hơn.

**Không** chỉ so tổng kích thước collection; cần biết **số vector đủ điều kiện sau metadata filter** và cấu trúc dữ liệu.

### 12.3. Thử ENN khi tập lọc rất nhỏ

Một chính sách kỹ thuật có thể là:

~~~text
Ứng dụng dự đoán candidate count rất nhỏ
  -> thử exact:true và đo latency.

Ứng dụng có tập ứng viên lớn
  -> ANN + tuning numCandidates.
~~~

Nhưng quyết định **ENN hay ANN trong request** không nên dựa trên một ước lượng candidate count thiếu chính xác mà không có telemetry. Cần đo theo tenant/query category và có fallback nếu hệ thống không hỗ trợ ENN.

### 12.4. Khi tăng numCandidates không cải thiện

Nếu recall không tăng dù numCandidates lớn:

- Kiểm tra filter và index definition.
- Kiểm tra vector dimension/model.
- Kiểm tra ground truth ENN có dùng đúng cùng filter/metric/corpus không.
- Kiểm tra dữ liệu index có mới/sẵn sàng chưa.
- Kiểm tra ANN parameters và giới hạn runtime.
- Đánh giá quantization/index configuration nếu có.

Không kết luận “vector search sai” khi hai phép tìm đang chạy trên **hai tập dữ liệu khác nhau**.

## 13. ANN, ENN và consistency của Search index

### 13.1. Indexing có thể bất đồng bộ

Ứng dụng:

~~~text
T0: insert listing L vào MongoDB
T1: nhận write acknowledgment
T2: Vector Search index nhận/index embedding của L
T3: $vectorSearch nhìn thấy L
~~~

Tùy deployment và tải indexing, **T1 có thể sớm hơn T2/T3**. Vì vậy:

- Tìm kiếm vector không nhất thiết có **read-your-writes ngay lập tức** như một find thông thường theo cùng giả định.
- Cả ANN và ENN có thể chưa trả listing mới nếu nó chưa được index.
- exact:true không làm cho indexing bất đồng bộ trở thành đồng bộ.

### 13.2. Không dùng exact để kiểm tra durability của write

Write concern và vector search index freshness là **hai vấn đề khác nhau**. Một write đã majority-acknowledged không có nghĩa vector search replica/index đã phản ánh ngay; ngược lại, vector search trả kết quả không thay thế xác nhận write concern.

Nếu UI cần “vừa đăng tin là thấy ngay”:

- Có thể dùng **read-after-write trực tiếp theo ID** để hiển thị tin vừa tạo.
- Hiển thị trạng thái “đang lập chỉ mục tìm kiếm”.
- Có cơ chế theo dõi index progress/freshness.
- Không hứa độ mới tuyệt đối từ vector search nếu không có SLA thực.

### 13.3. Deletion và quyền truy cập

Một tài liệu bị ẩn/xóa hoặc đổi quyền có thể cần thời gian để trạng thái Search index cập nhật. Đối với dữ liệu nhạy cảm, cần thiết kế **ủy quyền tại application, đảm bảo metadata filter phù hợp và kiểm soát khả năng trả dữ liệu đã thu hồi quyền**.

Nếu chính sách đòi cập nhật quyền **ngay lập tức**, không thể chỉ dựa vào tính eventual của một Search index. Cân nhắc bước xác thực kết quả với nguồn authoritative trước khi hiển thị nội dung, hoặc kiến trúc phân quyền phù hợp.

### 13.4. Re-embedding và migration model

Khi đổi embedding model:

~~~text
Model A -> embeddings_A -> vector index A
Model B -> embeddings_B -> vector index B
~~~

Không ghi đè một nửa corpus bằng model B rồi tiếp tục dùng cùng index/query vector model A mà vẫn kỳ vọng ranking đúng.

Một quy trình chuyển đổi có thể gồm:

1. Thêm field **embeddingV2**.
2. Backfill embeddingsV2.
3. Tạo Vector Search index v2 với numDimensions/metric tương ứng.
4. Đánh giá ANN vs ENN và relevance trên v2.
5. Chuyển traffic dần sang v2.
6. Theo dõi chất lượng và rollback.
7. Chỉ dọn v1 khi không còn consumer phụ thuộc.

## 14. Những giới hạn của metadata filter

### 14.1. Filter path phải đúng schema và index

Nếu định nghĩa index có:

~~~javascript
{ type: "filter", path: "metadata.city" }
~~~

thì query phải dùng field path tương ứng:

~~~javascript
filter: { "metadata.city": "HCM" }
~~~

Không thay tùy tiện thành **city** nếu document không có city ở cấp root.

### 14.2. Đa loại giá trị

Nếu dữ liệu:

~~~javascript
// Document A:
rentMillion: 12

// Document B:
rentMillion: "12"
~~~

thì:

~~~javascript
filter: { rentMillion: { $lte: 20 } }
~~~

không có nghĩa hai document chắc chắn được xử lý như nhau. Quy tắc so sánh, type support và index semantics phụ thuộc MongoDB Vector Search version. Chuẩn hóa kiểu dữ liệu trước khi index.

### 14.3. Giá trị computed

Nếu người dùng yêu cầu:

~~~text
Giá thuê + phí quản lý <= 20 triệu
~~~

không nên mặc định viết:

~~~javascript
filter: {
  $expr: {
    $lte: [
      { $add: ["$rentMillion", "$feeMillion"] },
      20
    ]
  }
}
~~~

và trông chờ $vectorSearch.filter hỗ trợ mọi $expr. Có thể tạo field **effectiveMonthlyCost** đã tính/chuẩn hóa:

~~~javascript
{
  rentMillion: 18,
  feeMillion: 1.5,
  effectiveMonthlyCost: 19.5
}
~~~

Sau đó khai báo **effectiveMonthlyCost** là type:"filter" và dùng range filter được hỗ trợ. Cần quản lý việc cập nhật field này nhất quán.

### 14.4. Array membership

Một listing có:

~~~javascript
amenities: ["desk", "wifi", "parking"]
~~~

Bạn có thể muốn lọc tiện ích desk/wifi. **Không được mặc định mọi toán tử Array của find() đều chạy trong Vector Search prefilter**. Cần kiểm tra hỗ trợ đối với **$in**, Array values hoặc nested fields trong phiên bản đang chạy. Nếu không phù hợp, dùng các field scalar được chuẩn hóa như **hasDesk: true**, **hasWifi: true**, hoặc một kiến trúc search khác.

### 14.5. Text + vector

Người dùng muốn vừa tìm “studio” theo từ khóa, vừa tìm gần ngữ nghĩa. Metadata pre-filter không phải giải pháp thay thế toàn bộ **full-text search** hoặc hybrid search.

Một hệ thống có thể kết hợp:

- Atlas Search/text search.
- MongoDB Vector Search.
- Fusion/reranking được phiên bản hỗ trợ.
- Filter/authorization thống nhất.

Không gọi **$regex trong $vectorSearch.filter** để “bật keyword search” nếu toán tử ấy không nằm trong tập được hỗ trợ.

## 15. Reranking và ngưỡng score

### 15.1. Hai tầng retrieval

Một kiến trúc phổ biến:

~~~text
Query + metadata
       |
       v
ANN lấy top 100 (candidate retrieval)
       |
       v
Reranker đánh giá chi tiết 100 candidates
       |
       v
Trả top 10 cuối
~~~

Reranker có thể là một model khác hoặc điểm tổng hợp từ text relevance, khoảng cách, thời gian đăng và business rules.

### 15.2. Không bỏ quyền truy cập trong reranking

Nếu ANN trả sai tenant ngay từ đầu rồi gửi 100 văn bản tới một reranker bên ngoài, dữ liệu đã có thể bị tiết lộ **trước khi API lọc kết quả trả về**. Vì vậy tenant/authorization phải được giải quyết đúng từ đầu, không phải “ẩn ở response là đủ”.

### 15.3. Score threshold

Sau $vectorSearch, một ứng dụng có thể lấy:

~~~javascript
{
  $project: {
    title: 1,
    score: { $meta: "vectorSearchScore" }
  }
}
~~~

rồi dùng:

~~~javascript
{ $match: { score: { $gte: 0.75 } } }
~~~

**0.75 chỉ là ví dụ**. Threshold cần được **hiệu chuẩn riêng theo embedding model, metric, loại truy vấn và mục tiêu sản phẩm**. Một threshold cao có thể làm mất kết quả hợp lệ cho những truy vấn khó, trong khi threshold thấp đưa nhiều noise.

Vì score được tạo sau retrieval, threshold cũng có thể khiến response ít hơn limit. Đây là quyết định ranking chất lượng, khác với metadata prefilter về quyền/giá/thành phố.

### 15.4. Reranking không sửa được thiếu candidate

Nếu ANN không đưa một document tốt vào danh sách ứng viên, reranker **không thể chọn document ấy**. Vì vậy cần đo **candidate recall** trước khi tối ưu reranker.

## 16. Node.js: xây pipeline vector query rõ ràng

### 16.1. Hàm truy vấn ANN

Ví dụ dùng MongoDB Node.js Driver; **queryVector đã được tạo bên ngoài**:

~~~javascript
import { MongoClient } from "mongodb";

function validateQueryVector(vector, dimensions = 3) {
  if (!Array.isArray(vector) ||
      vector.length !== dimensions ||
      !vector.every(
        value => typeof value === "number" &&
                 Number.isFinite(value)
      )) {
    throw new Error("queryVector sai số chiều hoặc chứa giá trị lỗi");
  }

  const lengthSquared = vector.reduce(
    (sum, value) => sum + value * value, 0
  );
  if (lengthSquared === 0) {
    throw new Error("Không dùng zero vector với cosine");
  }
}

async function searchListings({
  uri,
  queryVector,
  authorizedTenantId,
  city,
  maxRentMillion,
  limit = 10,
  numCandidates = 200
}) {
  validateQueryVector(queryVector, 3);

  if (!authorizedTenantId ||
      !["HCM", "HN"].includes(city) ||
      !Number.isFinite(maxRentMillion) ||
      maxRentMillion <= 0 ||
      !Number.isInteger(limit) ||
      limit < 1 ||
      limit > 50 ||
      !Number.isInteger(numCandidates) ||
      numCandidates < limit) {
    throw new Error("Tham số filter hoặc retrieval không hợp lệ");
  }

  const client = new MongoClient(uri);
  await client.connect();

  try {
    const collection = client
      .db("mongo_vector_lab_314")
      .collection("lab_listings");

    const pipeline = [
      {
        $vectorSearch: {
          index: "vec314_listing_index",
          path: "embedding",
          queryVector,
          numCandidates,
          limit,
          filter: {
            tenantId: authorizedTenantId,
            city,
            isActive: true,
            rentMillion: { $lte: maxRentMillion }
          }
        }
      },
      {
        $project: {
          _id: 1,
          title: 1,
          city: 1,
          rentMillion: 1,
          score: { $meta: "vectorSearchScore" }
        }
      }
    ];

    return await collection.aggregate(
      pipeline, { maxTimeMS: 5000 }
    ).toArray();
  } finally {
    await client.close();
  }
}

// const hits = await searchListings({
//   uri: process.env.MONGODB_URI,
//   queryVector: [1, 0, 0],
//   authorizedTenantId: "t001",
//   city: "HCM",
//   maxRentMillion: 20
// });
~~~

Đoạn code đặt hạn mức **limit<=50** và **maxTimeMS=5000** để minh họa phòng tránh request quá rộng. Đây là chính sách ứng dụng, không phải giới hạn cố định của MongoDB. Trong production, dùng **MongoClient dùng chung/pool**, không tạo client mới cho mỗi HTTP request như ví dụ độc lập.

**authorizedTenantId** phải được lấy từ server-side authentication context, không phải field do người dùng tự chọn. Trường **embeddingModel** và số chiều ba chỉ dành cho toy lab; production phải dựa trên model thật.

### 16.2. Hàm ENN cho đánh giá

~~~javascript
async function exactSearch(collection, queryVector, filter, limit) {
  return collection.aggregate([
    {
      $vectorSearch: {
        index: "vec314_listing_index",
        path: "embedding",
        queryVector,
        exact: true,
        limit,
        filter
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
~~~

Chỉ dùng khi cluster hỗ trợ ENN. Khi dùng để so với ANN, bảo đảm **cùng queryVector, filter, limit, metric, index và snapshot/freshness dữ liệu hợp lý**.

### 16.3. Những lỗi ứng dụng phải bắt

- Vector sai số chiều, không có số hữu hạn, zero vector.
- Không tìm thấy Vector Search index hoặc index chưa sẵn sàng.
- Field trong filter chưa khai báo type:"filter".
- Toán tử filter không được hỗ trợ.
- Tham số numCandidates/limit không hợp lệ.
- Timeout/query cancellation.
- Search index chậm cập nhật.
- Không có kết quả vì filter quá hẹp hoặc corpus thiếu embeddings.

Không chuyển tất cả lỗi thành “Không tìm thấy căn hộ” vì có những trường hợp hệ thống **không thực hiện được tìm kiếm**, khác với tìm thành công và trả 0.

## 17. Multi-tenancy và bộ lọc quyền truy cập

### 17.1. Filter phải là điều kiện không thể bỏ

API:

~~~text
POST /search
Body:
  query: "quiet apartment with desk"
  city: "HCM"
  maxRentMillion: 20

Security context:
  authorizedTenantId = "t001"
~~~

Backend:

~~~text
1. Xác thực user.
2. Xác định tenant/permissions có hiệu lực.
3. Tạo embedding từ query.
4. Dùng $vectorSearch.filter buộc tenantId + isActive.
5. Ghi nhận/query log an toàn.
6. Trả kết quả sau projection và kiểm tra quyền bổ sung nếu cần.
~~~

### 17.2. Không để API client ghi đè filter

Đoạn thiết kế lỗi:

~~~javascript
const filter = {
  tenantId: authorizedTenantId,
  ...req.body.filter
};
~~~

Nếu req.body.filter có tenantId, spread sau cùng có thể **ghi đè tenantId đã xác thực**.

Đúng hơn:

~~~javascript
const filter = {
  city: validatedCity,
  rentMillion: { $lte: validatedBudget },
  isActive: true,
  tenantId: authorizedTenantId
};
~~~

Hoặc xây một AST filter từ các trường cho phép rồi **áp điều kiện bắt buộc cuối cùng theo cách không thể override**. Cần test adversarial inputs và không cho khách hàng gửi trực tiếp aggregation pipeline tùy ý nếu họ không có quyền đó.

### 17.3. Filter scope và audit

Khi một service truy vấn nhiều tenant để làm báo cáo nội bộ, đó là một **use case phân quyền khác**, không phải lý do bỏ tenant filter trong API người dùng.

Với dữ liệu cá nhân hoặc tài liệu nhạy cảm:

- Giảm data trong projection.
- Tránh gửi raw content ra bên ngoài không cần thiết.
- Áp chính sách data residency/retention.
- Ghi audit các thao tác search có quyền cao.
- Kiểm tra kết quả khi tài liệu đã bị thu hồi quyền nhưng Search index chưa đồng bộ.

## 18. Nếu không hỗ trợ metadata filter mong muốn

### 18.1. Phân loại điều kiện

| Điều kiện | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Equality scalar | tenantId, city, isActive | Ưu tiên Vector Search pre-filter nếu hỗ trợ |
| Range number/date | price <=20, publishedAt >= ngày | Pre-filter khi field/operator được index và hỗ trợ |
| Full-text | title chứa từ cụ thể | Atlas Search/hybrid pipeline theo khả năng |
| Biểu thức computed | rent + fee <= 20 | Denormalize field số hoặc xử lý sau |
| Geospatial | gần ga tàu 2 km | Vector + geospatial/reranking theo kiến trúc phù hợp |
| Phân quyền phức tạp | ACL theo nhóm/người dùng | Chuẩn hóa filter index được, hoặc xử lý ở tầng authoritative |

### 18.2. Không “mở khóa” filter bằng $match phía trước

Vì $vectorSearch phải ở vị trí được hỗ trợ, thêm:

~~~javascript
{ $match: { ... } }
~~~

phía trước không phải giải pháp đúng. Metadata filter cần nằm trong cú pháp Vector Search hoặc được giải quyết bằng kiến trúc khác.

### 18.3. Post-filter có chủ đích

Nếu một điều kiện thực sự chỉ áp được sau retrieval, hãy:

1. Cố gắng đưa những điều kiện **bắt buộc và hỗ trợ** vào prefilter trước.
2. Xác định retrieval limit đủ lớn cho candidate pool.
3. Chấp nhận có thể trả ít hơn K.
4. Đo tỷ lệ **post-filter rejection** theo query category.
5. Không tiết lộ tài liệu không được phép vào bước reranking/external services.
6. Xem xét thêm read model/metadata field nếu rejection quá cao.

### 18.4. Query hai giai đoạn

Khi dữ liệu có ACL hoặc business rule rất phức tạp, có thể xây một **candidate authorization set** trong tầng ứng dụng hoặc collection phụ, nhưng cần tính đến:

- Tập ID có thể quá lớn để nhét vào $in.
- Filter operator/type support và giới hạn command.
- Chi phí truy vấn lần hai.
- Race condition khi quyền thay đổi.
- Dữ liệu nhạy cảm có thể bị lộ nếu kiểm tra quyền quá muộn.

Không xem hai giai đoạn là lối tắt luôn an toàn hơn metadata prefilter; phải thiết kế cụ thể theo threat model.

## 19. RAG: tìm tài liệu đúng tenant và đúng thời gian hiệu lực

### 19.1. Ví dụ

Một hệ thống hỏi đáp nội bộ có document chunks:

~~~javascript
{
  _id: "chunk-001",
  tenantId: "t001",
  docId: "policy-2026",
  isActive: true,
  validFrom: ISODate("2026-01-01T00:00:00Z"),
  validTo: ISODate("2027-01-01T00:00:00Z"),
  text: "Chính sách hoàn tiền ...",
  embedding: [/* vector model thật */]
}
~~~

Một truy vấn RAG cần:

- Lọc tenant.
- Lọc tài liệu active.
- Lọc thời gian hiệu lực nếu metadata filter hỗ trợ date/range tương ứng.
- Tìm top-K chunks theo embedding.
- Đưa văn bản những chunks được phép vào LLM.

### 19.2. Một câu trả lời đúng phải dựa trên tài liệu được phép

ANN có thể tìm chunks rất giống câu hỏi nhưng từ chính sách **đã hết hiệu lực**. Nếu metadata prefilter đúng, những chunks ấy không tham gia tập kết quả.

Nếu chỉ post-filter sau top-K, hệ thống có thể nhận không đủ chunks để trả lời; tệ hơn, một bước xử lý trước post-filter có thể đã gửi tài liệu hết hiệu lực/khác tenant tới model.

### 19.3. Recall@K của retrieval khác faithfulness của câu trả lời

Ngay cả khi ENN trả đúng top-K theo vector metric, LLM vẫn có thể:

- Hiểu sai nội dung.
- Trộn hai tài liệu có thời gian hiệu lực khác nhau.
- Trả lời khi nguồn không đầy đủ.
- Thiếu citation hoặc không tuân thủ quyền.

RAG cần thêm **citation, source metadata, prompt constraints, fallback “không đủ dữ liệu” và đánh giá answer quality**, không chỉ tuning numCandidates.

## 20. Recommendation và catalog đang thay đổi

### 20.1. Nhiều tin gần nhau

Một catalog có hàng chục bản đăng gần như trùng nhau có thể chiếm hết top-K. MongoDB Vector Search trả ranking theo vector metric, không tự bảo đảm **diversity** theo chủ nhà, dự án, loại căn hộ hoặc khu vực.

Có thể cần:

- Group/dedup theo propertyId sau retrieval.
- Reranking cân bằng sự đa dạng.
- Giới hạn số tin cùng chủ nhà.
- Điều kiện availability/active cập nhật đúng.

### 20.2. Giá và trạng thái thay đổi nhanh

Metadata **rentMillion, isActive** có thể đổi nhiều lần. Khi cập nhật:

- Search index cần đồng bộ filter fields mới.
- Giao diện không nên đưa ra lời hứa về giá/đặt cọc chỉ từ kết quả vector cũ.
- Trước hành động quan trọng, kiểm tra dữ liệu authoritative bằng _id.

Vector search là hệ thống **gợi ý/truy xuất ứng viên**, không tự thay transactional check của nghiệp vụ đặt thuê.

### 20.3. Product freshness

Nếu ứng dụng vừa tạo listing rồi tìm không thấy:

- Kiểm tra có embedding hợp lệ chưa.
- Kiểm tra index đã build/sync chưa.
- Kiểm tra filter loại listing vì isActive=false hoặc city khác.
- Kiểm tra embeddingModel/version.
- Không kết luận ANN bỏ sót trước khi xác nhận dữ liệu đã được index.

## 21. Quan sát và tối ưu hiệu năng

### 21.1. Các metric chính

| Metric | Ý nghĩa |
| --- | --- |
| **ANN latency p50/p95/p99** | Độ trễ thực của tìm kiếm |
| **ENN latency** | Chi phí tìm chính xác/baseline |
| **Recall@K ANN vs ENN** | Mức bỏ sót hàng xóm chính xác |
| **numCandidates** | Ngân sách ANN đang sử dụng |
| **limit / top-K** | Số kết quả yêu cầu |
| **Eligible candidate count** | Độ rộng tập dữ liệu sau metadata filter |
| **Empty-result rate** | Tỷ lệ trả 0; có thể do filter hoặc indexing |
| **Post-filter rejection rate** | Tỷ lệ loại sau retrieval |
| **Index build/sync status** | Tình trạng chỉ mục vector |
| **Embedding coverage** | Bao nhiêu document có vector hợp lệ đúng model |
| **Embedding age/version** | Dữ liệu có dùng cùng model không |
| **Timeout/error rate** | Có quá tải/unsupported index/operator không |
| **Resource usage** | CPU, RAM, storage, index footprint |

### 21.2. Gắn metric theo query category

Không chỉ đo average latency toàn hệ thống. Hãy tách:

~~~text
Query category:
  tenant nhỏ + filter rất hẹp
  tenant lớn + filter hẹp
  tenant lớn + filter rộng
  RAG 10-K
  recommendation 100 candidates
~~~

Một numCandidates phù hợp với loại A có thể không phù hợp loại B. Tuning chỉ theo một global p95 che giấu những truy vấn có recall thấp.

### 21.3. Giám sát score nhưng không coi score là xác suất

Theo dõi phân bố score theo model/query category để phát hiện drift, nhưng không hiển thị “98% khớp” cho người dùng trừ khi bạn đã xây dựng phương pháp hiệu chuẩn chứng minh ý nghĩa tỷ lệ đó.

### 21.4. Explain/profiling

Các công cụ explain, profiling và diagnostics của MongoDB Vector Search có những khả năng/giới hạn phụ thuộc phiên bản. Hãy dùng API được tài liệu hỗ trợ cho deployment của bạn để quan sát số ứng viên, plan/thời gian thực thi và index status.

Không giả định:

~~~javascript
db.collection.find({ embedding: ... }).explain()
~~~

sẽ hiển thị đầy đủ hoạt động ANN, vì **$vectorSearch là một aggregation/search stage riêng**, không phải equality/range query B-tree thông thường.

### 21.5. Benchmark đúng cách

Một benchmark hữu ích nên:

1. Cố định tập embedding và index definitions.
2. Chuẩn bị nhiều query vectors đại diện.
3. Cố định metadata filters.
4. Đợi index sẵn sàng và dữ liệu được đồng bộ.
5. Chạy warmup và nhiều lượt.
6. Đo ANN ở các numCandidates.
7. So ENN trên cùng corpus/filter khi được hỗ trợ.
8. Báo cáo recall, p95/p99, error và chi phí.
9. Lặp lại khi thay model, số chiều, quantization hoặc index settings.

**Một lượt chạy trên 10 documents không chứng minh được latency hay recall production.**

## 22. Các tình huống lỗi và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| $vectorSearch không được nhận diện | Deployment/version chưa hỗ trợ | Kiểm tra feature availability |
| Index not found | Sai tên index hoặc chưa tạo | getSearchIndexes/kiểm tra definition |
| Index chưa usable | Index build/sync bất đồng bộ | Kiểm tra trạng thái index |
| queryVector sai dimension | Vector tạo bởi model khác hoặc thiếu giá trị | Validate length/model version |
| Không hợp lệ khi dùng cosine | Zero vector hoặc giá trị không phù hợp | Chặn đầu vào và kiểm tra embeddings |
| filter path lỗi | Chưa khai báo type:"filter" | Thêm field vào index definition đúng cách |
| filter operator lỗi | Dùng toán tử không được hỗ trợ | Chuyển sang metadata đơn giản hoặc kiến trúc khác |
| Query trả 0 sau $match | Postfilter loại top-K toàn cục | Chuyển filter sang prefilter |
| Query trả ít hơn limit | Corpus đủ điều kiện ít hoặc post-filter/threshold | Kiểm tra selectivity và từng stage |
| ANN khác ENN | ANN gần đúng; numCandidates/quantization | Đo Recall@K, tuning |
| ENN chậm | Tập vector đủ điều kiện quá lớn | Dùng ANN hoặc lọc hẹp hơn |
| Search chưa thấy document vừa ghi | Indexing bất đồng bộ | Kiểm tra sync/freshness, fallback authoritative |
| Dữ liệu khác tenant lọt kết quả | Thiếu/override tenant filter | Enforce security context trên server |
| Score giữa model A/B khác biệt | Không cùng embedding space/metric | Không so score cross-model |
| Thay model nhưng ranking tệ | Corpus/query chưa migration đồng bộ | Dual-index rollout |
| Bị timeout khi prefilter rộng | Nhiều candidates, numCandidates lớn | Tối ưu filter, index, compute, deadline |
| Thay numCandidates không cải thiện | Vấn đề model/corpus/filter hoặc plateau | So ground truth và relevance |
| Bộ lọc giá sai | rentMillion lưu String lẫn Number | Chuẩn hóa type/đơn vị |
| RAG trả tài liệu hết hiệu lực | Không lọc validFrom/validTo | Index/filter metadata hiệu lực |
| RAG trả lời sai dù ENN đúng | Retrieval exact khác answer faithfulness | Eval answer, citations, policy |
| Score cao nhưng sản phẩm không phù hợp | Model/metric không phản ánh business relevance | Relevance evaluation, reranking |

## 23. Checklist thiết kế trước production

### 23.1. Embedding

- Dùng **một model/version tương thích** cho corpus và query.
- Đúng **numDimensions**.
- Giá trị số hữu hạn; xử lý zero vector theo metric.
- Định nghĩa cách chunking/normalization.
- Có quy trình re-embedding và migration index.
- Bảo vệ dữ liệu nhạy cảm trong text/embedding.

### 23.2. Vector Search index

- Field vector path đúng.
- Metric phù hợp model.
- Những metadata bắt buộc được khai báo **type:"filter"**.
- Kiểm tra data types, nested paths và operators hỗ trợ.
- Index build/sync đã sẵn sàng.
- Có observability và chiến lược rollback.

### 23.3. Query

- Chọn ANN/ENN theo workload và feature support.
- Với ANN, điều chỉnh **numCandidates** bằng benchmark.
- Chọn **limit** có giới hạn và phù hợp bước reranking.
- Đưa tenant/active/budget/city vào **prefilter** khi hỗ trợ.
- Không cho client tự override điều kiện quyền.
- Dùng projection để hạn chế dữ liệu trả.
- Có maxTimeMS/deadline và xử lý lỗi khác với kết quả rỗng.

### 23.4. Evaluation

- Có ENN hoặc baseline chính xác hợp lệ.
- So trên **cùng filter, metric, index/corpus**.
- Theo dõi Recall@K, relevance labels và latency.
- Đánh giá trường hợp filter rất hẹp/rất rộng.
- Đo freshness/indexing lag.
- Có test multi-tenant và dữ liệu vừa thu hồi quyền.

### 23.5. Vận hành

- Không đưa embeddings sai model vào cùng index.
- Không assume vector search là read-after-write đồng bộ.
- Theo dõi search index status/size/CPU/RAM.
- Có quy trình rebuild khi index lỗi.
- Đảm bảo quyền truy cập và data retention.
- Không dùng score như xác suất nghiệp vụ nếu chưa hiệu chuẩn.

## 24. Bài tập thực hành

### Bài 1 — ANN và ENN

Giải thích sự khác nhau giữa ANN và ENN: mỗi cách có thể phải đánh giá bao nhiêu vector, ưu/nhược về latency và recall, và khi nào ENN là ground truth hữu ích.

### Bài 2 — numCandidates vs limit

Pipeline có **numCandidates: 200** và **limit: 10**. Nó trả tối đa bao nhiêu document? numCandidates có phải số record ứng dụng nhận về không?

### Bài 3 — Metric cosine

Với query [1,0,0], tính cosine thô của [1,0,0], [0.9,0.1,0] và [0,1,0]. Vì sao score vectorSearchScore không nhất thiết bằng đúng cosine thô?

### Bài 4 — Model version

Document embedding 768 chiều từ model A; query embedding 768 chiều từ model B. Query có thể chạy nhưng vì sao ranking vẫn có thể sai? Thiết kế quy trình thay model an toàn.

### Bài 5 — Tạo index

Viết Vector Search index definition cho embedding ba chiều/cosine, và filter tenantId, city, isActive, rentMillion. Phân biệt **type:"filter"** trong Vector Search index với B-tree index tenantId.

### Bài 6 — Seed

Chạy seed mười records ở mục 10. Kiểm tra _id, dimension, số lượng document và giá trị metadata. Vì sao phải đợi Vector Search index usable trước khi đánh giá?

### Bài 7 — Exact top 3

Áp filter t001/HCM/active/giá <=20, rồi tính cosine. Dự đoán top 3 và giải thích tại sao c, d, e, f không nằm trong kết quả dù embedding có thể rất giống query.

### Bài 8 — Thử ANN

Chạy $vectorSearch ANN trên lab với limit=3, numCandidates=60. So ID và thứ tự với baseline JavaScript và (nếu hỗ trợ) ENN. Nếu khác, bạn sẽ kiểm tra những yếu tố nào?

### Bài 9 — Thử ENN

Chạy exact:true với cùng filter. Khi không có feature support, làm cách nào có baseline học thuật trên mười vector mà không gọi một ANN numCandidates lớn là “exact”?

### Bài 10 — Post-filter

Lấy top 3 trên toàn corpus rồi $match tenantId/city/active/budget. Vì sao có thể còn 0–2 record dù tồn tại ít nhất ba document phù hợp? Chuyển lại thành prefilter.

### Bài 11 — Security

Một API nhận filter JSON từ client. Developer trộn {tenantId:authorizedTenantId, ...clientFilter}. Chỉ ra lỗi và viết cách bảo đảm tenant không bị override.

### Bài 12 — Unsupported regex

Người dùng yêu cầu title khớp regex và vector similarity. Vì sao không được mặc định đưa $regex vào $vectorSearch.filter? Đề xuất hai phương án khác và trade-off.

### Bài 13 — Compound price condition

Điều kiện **rentMillion + feeMillion <=20** không được biểu diễn trực tiếp bằng filter expression tùy ý. Hãy đề xuất field denormalized, cách cập nhật và kiểm tra.

### Bài 14 — Metadata selectivity

Một filter còn 200 candidates, filter khác còn 300.000 candidates. Khi nào thử ENN, khi nào ưu tiên ANN? Vì sao cần đo latency/recall thay vì chỉ dựa vào tổng collection size?

### Bài 15 — Recall@5

ENN top 5 = [A,B,C,D,E], ANN top 5 = [A,B,X,D,Y]. Tính Recall@5. Nếu thứ tự top 1 sai nhưng Recall@5 cao, cần thêm metric nào?

### Bài 16 — Tuning

Thiết kế benchmark với numCandidates 50/100/200/400, limit=10. Ghi rõ cách chọn tập queries, metadata filters, latency p95, Recall@10 và khả năng lỗi.

### Bài 17 — Search freshness

Một listing vừa insert và được ACK majority nhưng chưa xuất hiện trong $vectorSearch exact:true. Hãy giải thích nguyên nhân có thể và cách xây UX không báo nhầm dữ liệu mất.

### Bài 18 — Deletion và quyền

Một listing vừa chuyển isActive=false nhưng Search index chưa cập nhật. Bạn cần chiến lược gì nếu policy yêu cầu user không còn thấy listing đó ngay lập tức?

### Bài 19 — Reranking

ANN chọn top 100, reranker chọn top 10. Nếu tài liệu tốt nhất không có trong top 100, reranker có tìm lại được không? Bạn cải thiện tầng nào trước?

### Bài 20 — RAG

Viết policy truy vấn tài liệu nội bộ gồm tenantId, isActive và validFrom/validTo. Giải thích vì sao câu trả lời của LLM vẫn có thể sai dù ENN tìm đúng top-K vector.

### Bài 21 — Nested metadata

Document chứa metadata.city và metadata.tenantId. Index khai báo filter theo dotted paths. Viết query đúng đường dẫn, nêu rủi ro khi client gửi field path khác hoặc field kiểu không thống nhất.

### Bài 22 — Vector index vs B-tree

Ứng dụng đã có createIndex({tenantId:1,city:1}) nhưng $vectorSearch.filter báo lỗi. Vì sao index đó không tự cung cấp filter metadata cho Vector Search?

### Bài 23 — Empty results

Một request tìm kiếm trả rỗng. Hãy đề xuất trình tự chẩn đoán: authorization, metadata filter, embedding coverage, index sync, queryVector/model, unsupported operators, ANN candidates và post-filter.

### Bài 24 — Score threshold

Một hệ thống chỉ trả kết quả với score >=0.80. Vì sao ngưỡng này có thể làm mất các kết quả tốt của một số loại query? Làm cách nào đánh giá/hiệu chuẩn threshold?

### Bài 25 — Cùng K nhưng khác filter

Thử ANN và ENN cùng query nhưng ANN filter thành phố HCM, còn ENN không filter city. Recall@K tính được có ý nghĩa không? Giải thích vì sao phải cố định eligibility set.

### Bài 26 — Zero vector

Tại sao cosine không định nghĩa cho [0,0,0]? Bạn cần kiểm tra vector ở cả ingestion và query path thế nào?

### Bài 27 — Đổi embeddings

Model A tạo 768 chiều, model B tạo 1024 chiều. Hãy thiết kế dual-index migration, backfill, thử nghiệm chất lượng, rollback và cleanup.

### Bài 28 — Khác nhau giữa gần đúng và liên quan

ANN có Recall@10 0.99 nhưng người dùng đánh giá kết quả kém. Những vấn đề nào về model, chunking, dữ liệu đầu vào, metric, đa dạng hoặc business rule có thể giải thích?

### Bài 29 — Thiết kế monitoring

Lập dashboard cho vector search có latency p95/p99, Recall@K, numCandidates, empty-result rate, post-filter rejection, index freshness, embedding coverage và lỗi theo tenant/query category.

### Bài 30 — End-to-end multi-tenant

Thiết kế một API tìm tin đăng từ mô tả tự nhiên với yêu cầu: không quá 20 triệu, tại HCM, tenant t001, chỉ active, trả 10 kết quả trong ngân sách latency. Mô tả đầy đủ embedding, index definition, prefilter, ANN tuning, fallback khi index chưa đồng bộ, authorization và evaluation.

## 25. Tài liệu tham khảo MongoDB

- MongoDB Atlas — [MongoDB Vector Search](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-overview/).
- MongoDB Atlas — [How to Index Fields for Vector Search](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-type/).
- MongoDB Atlas — [Run Vector Search Queries](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-stage/).
- MongoDB Atlas — [Pre-Filter Data for Vector Search](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-stage/#filter).
- MongoDB Atlas — [Vector Search Index Definition](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-type/#fields).
- MongoDB Atlas — [Exact Vector Search](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-stage/#exact).
- MongoDB Atlas — [Vector Search Score](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-stage/#score).
- MongoDB Manual — [Search Index Management](https://www.mongodb.com/docs/manual/reference/method/db.collection.createSearchIndex/).
- MongoDB Node.js Driver — [Run an Atlas Vector Search Query](https://www.mongodb.com/docs/drivers/node/current/atlas-vector-search/).
- MongoDB Manual — [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/).

**Kết luận:** **ANN** là lựa chọn hữu ích khi cần truy xuất lân cận nhanh trên corpus lớn và chấp nhận đánh đổi recall để giảm latency; **ENN** tìm top-K chính xác theo metric trên tập vector đủ điều kiện trong chỉ mục và là baseline tốt để đánh giá ANN, khi deployment hỗ trợ. **Metadata pre-filter** trong **$vectorSearch.filter** quyết định tập document tham gia tìm kiếm — đặc biệt quan trọng với **tenant, trạng thái, thành phố, ngân sách và hiệu lực dữ liệu**. Đừng thay prefilter bằng $match sau top-K rồi kỳ vọng vẫn tìm đủ hàng xóm tốt nhất. Muốn hệ thống đáng tin cậy, hãy thống nhất **embedding model/dimension/metric**, cấu hình **type:"filter"** cho đúng metadata, đo **Recall@K cùng latency**, theo dõi **index freshness**, và cưỡng chế **authorization** từ phía server. “Gần nhất theo vector” chỉ là một tầng của kết quả; sản phẩm đúng còn phải **đủ điều kiện nghiệp vụ và được phép hiển thị**.
