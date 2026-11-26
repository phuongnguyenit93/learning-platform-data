# Ước lượng bộ nhớ trước khi chạy thuật toán trên dữ liệu lớn trong Neo4j

## 1. Vì sao phải ước lượng bộ nhớ trước khi chạy thuật toán?

Trong **property graph** của Neo4j, node biểu diễn thực thể, relationship mô tả liên kết và thuộc tính lưu dữ liệu liên quan. Những truy vấn Cypher thông thường thường truy cập một phần graph bằng index và traversal. Ngược lại, nhiều thuật toán **Graph Data Science (GDS)** như PageRank, Weakly Connected Components (WCC), Louvain, Node Similarity hoặc thuật toán đường đi cần xử lý một phần lớn cấu trúc liên kết trong bộ nhớ.

Ví dụ, hệ thống gợi ý đối tác có hàng chục triệu node `Company` và hàng trăm triệu relationship `TRADES_WITH`. Nếu chạy PageRank trực tiếp theo giả định “máy chủ còn 16 GiB RAM nên chắc đủ”, công việc có thể bị từ chối trước khi bắt đầu, gây áp lực lên JVM heap, hoặc thất bại khi thuật toán đang xử lý. Thất bại này còn ảnh hưởng đến các transaction Cypher, Java Driver và Spring Data Neo4j đang chia sẻ cùng Neo4j DBMS.

**Bài học thuộc chương “Thuật toán đồ thị” tập trung vào việc lập ngân sách bộ nhớ cho toàn bộ vòng đời GDS:**

1. Đếm và **ước lượng phần graph sẽ được nạp vào memory** (*projection*).
2. Ước lượng **bộ nhớ riêng của thuật toán** theo mode và cấu hình thực thi.
3. Xem xét những phần đã chiếm heap: graph catalog, Neo4j, transaction, các job GDS khác.
4. Chọn cách thu nhỏ phạm vi, điều chỉnh cấu hình, chạy thử và giám sát trước khi xử lý dữ liệu lớn.
5. Thu hồi graph/properties không còn sử dụng để giải phóng tài nguyên.

> **Phạm vi:** Ví dụ dùng Neo4j Graph Data Science (GDS) 2.x hiện hành. Cần cài và cấp quyền GDS tương thích với Neo4j. `gds.*` là API của plugin/sản phẩm **Graph Data Science**, không phải Cypher built-in, Neo4j APOC hay chức năng tự có khi chỉ thêm Java Driver.

## 2. Phân biệt ba vùng bộ nhớ và hai giai đoạn công việc

GDS dùng **JVM heap** để lưu graph đã project và trạng thái tính toán của thuật toán. Bộ nhớ heap này tách biệt với **Neo4j page cache** dùng hỗ trợ truy cập database store và những vùng native/off-heap khác. Mỗi vùng có vai trò riêng.

| Thành phần | Chứa gì? | Khi nào chiếm bộ nhớ? |
| --- | --- | --- |
| **GDS graph catalog** | Node ID, topology/adjacency, relationship, các thuộc tính số được project, thuộc tính kết quả `mutate` | Từ khi tạo named graph cho đến khi `gds.graph.drop` hoặc vòng đời catalog kết thúc |
| **Trạng thái thuật toán GDS** | Mảng điểm PageRank, nhãn component, cấu trúc cộng đồng, hàng đợi/working set, bộ đệm theo worker | Khi thuật toán chạy; phụ thuộc thuật toán, mode, graph, cấu hình |
| **Các workload khác trong JVM** | Transaction state, bộ nhớ truy vấn Cypher, DBMS runtime, những graph/job GDS khác, GC overhead | Có thể cùng tồn tại với job GDS |
| **Page cache** | Các page dữ liệu Neo4j được cache để đọc/ghi | Theo cấu hình DBMS và hoạt động truy vấn, projection, ghi kết quả |
| **Native/off-heap & OS** | Bộ nhớ JVM khác heap, thread stack, Arrow (nếu bật), OS và các tiến trình khác | Tùy công nghệ và môi trường triển khai |

Hai thao tác GDS thường diễn ra nối tiếp:

```text
             Neo4j database (node + relationship)
                           |
           [1] graph projection, tốn bộ nhớ lúc tạo
                           |
                           v
              GDS graph catalog trên heap
                           |
           [2] PageRank / WCC / Louvain / ...
                           |
                  Bộ nhớ làm việc tạm thời
                           |
          +----------------+----------------+
          |                |                |
        stream           mutate            write
  trả kết quả cho    lưu kết quả vào   ghi kết quả về
    client/Cypher      graph GDS      database Neo4j
```

**Không được nhầm phần “graph đang chiếm heap” với phần “algorithm cần thêm khi chạy”.** Nếu đã project graph 7 GiB rồi chạy thuật toán cần thêm 3 GiB, cả hai có thể đồng thời tồn tại. Nếu dùng cách ước lượng kết hợp một lần cho projection và thuật toán, cần xem ý nghĩa estimate để **tránh cộng đúp**.

### Một số yếu tố làm graph project phình bộ nhớ

- **Số node** và số relationship **sau khi project**, không phải luôn là tổng toàn database.
- **Hướng relationship:** khi chọn `UNDIRECTED`, GDS lưu cấu trúc quan hệ theo hai hướng; yêu cầu bộ nhớ có thể khác so với `NATURAL`.
- **Thuộc tính được nạp:** trọng số, điểm số hoặc nhiều cột số trên node/relationship làm tăng dung lượng.
- **Biểu diễn đồ thị, phân bố bậc node và compression**; không có “mỗi node luôn tốn đúng X byte” áp dụng cho mọi graph.
- **Các kết quả mutate** đang nằm trong graph catalog và những graph khác chưa được drop.

## 3. API `.estimate`: đọc đúng ý nghĩa của kết quả

GDS cung cấp chế độ **ước lượng** khi gọi các procedure có hỗ trợ `.estimate`. Với thuật toán, cú pháp tổng quát:

```cypher
CALL gds.<algorithm>.<executionMode>.estimate(
  'graphName',
  {concurrency: 4 /* và tham số riêng của thuật toán */}
)
YIELD nodeCount, relationshipCount,
      requiredMemory, bytesMin, bytesMax,
      heapPercentageMin, heapPercentageMax,
      treeView, mapView
RETURN nodeCount, relationshipCount,
       requiredMemory, bytesMin, bytesMax,
       heapPercentageMin, heapPercentageMax,
       treeView, mapView;
```

Đoạn trên là **mẫu cú pháp**, không phải một truy vấn chạy nguyên văn vì `<algorithm>` và `<executionMode>` cần được thay bằng tên thật, chẳng hạn `gds.pageRank.stream.estimate`.

| Field | Đọc như thế nào? | Giới hạn cần nhớ |
| --- | --- | --- |
| `nodeCount` | Số node trong graph được ước lượng hoặc đang project | Có thể khác số node trong toàn database |
| `relationshipCount` | Số relationship trong graph GDS tương ứng | Hướng/project/filter có thể thay đổi số cấu trúc phải xử lý |
| `requiredMemory` | Chuỗi dễ đọc về khoảng bộ nhớ ước lượng | Phù hợp trình bày, không nên parse để tính toán |
| `bytesMin` | Cận dưới bộ nhớ ước lượng, tính theo byte | Không phải lượng heap hiện còn rảnh |
| `bytesMax` | Cận trên bộ nhớ ước lượng, tính theo byte | Không phải cam kết chắc chắn không vượt ngưỡng |
| `heapPercentageMin`, `heapPercentageMax` | Tỷ lệ so với **maximum JVM heap đã cấu hình** | Không phải tỷ lệ RAM vật lý của máy hoặc phần heap đang rảnh |
| `treeView` | Cây thành phần ước lượng dạng văn bản | Hữu ích khi tìm cấu phần chiếm nhiều nhất |
| `mapView` | Cấu trúc chi tiết của các phần ước lượng dạng map | Phù hợp xử lý tự động, cần xét cấu trúc theo phiên bản |

**Chọn `bytesMax` làm đầu vào thận trọng để lập kế hoạch**, rồi cộng phần chiếm chỗ đồng thời và dự phòng phù hợp. Không suy ra “`bytesMax = 8 GiB` thì chỉ cần máy có đúng 8 GiB RAM”.

### Những giới hạn quan trọng của `.estimate`

- Nó **không chạy thuật toán thật** và không thể đo chính xác thời gian hoàn thành.
- Nó mô hình hóa bộ nhớ theo thông tin về graph và các cấu trúc thuật toán; dữ liệu lệch, trạng thái thực thi hoặc workload đồng thời vẫn có thể tạo biến động.
- Với graph estimate, công cụ có thể phải lấy số lượng node/relationship từ database; một số kiểu projection phức tạp cần thực hiện truy vấn đếm và **không nhất thiết có chi phí bằng 0**.
- Các thuật toán ở **production-ready tier** được bảo đảm có `.estimate`; không được giả định mọi thuật toán experimental/alpha đều hỗ trợ.
- Các tham số của câu `.estimate` phải **khớp với lần chạy thật**, đặc biệt mode, relationship orientation, trọng số, `concurrency` và tham số ảnh hưởng kích thước kết quả.

## 4. Ước lượng bộ nhớ *trước khi tạo graph projection*

### 4.1. Ước lượng từ label/type đang có

Cú pháp native projection estimate:

```cypher
CALL gds.graph.project.estimate(
  'Person',
  'KNOWS',
  {readConcurrency: 4}
)
YIELD nodeCount, relationshipCount, requiredMemory,
      bytesMin, bytesMax, treeView
RETURN nodeCount, relationshipCount,
       requiredMemory, bytesMin, bytesMax, treeView;
```

GDS ước lượng graph gồm node mang label `Person` và relationship type `KNOWS` theo cấu hình. Lệnh này **chưa tạo graph có tên** và chưa giữ một bản projection lâu dài trong catalog.

Nếu graph thực tế chỉ cần công ty đang hoạt động, không nên project toàn bộ label `Company` rồi kỳ vọng thuật toán tự biết phải bỏ công ty không hoạt động. Hãy xác định đúng projection/filter theo bài toán và đánh giá cost trên tập cần xử lý.

### 4.2. Ước lượng theo kịch bản giả định khi chưa có dữ liệu

Giả sử bản thiết kế dự kiến có **10 triệu node** và **80 triệu relationship**. Có thể làm thử một capacity estimate trước khi ingest dữ liệu:

```cypher
CALL gds.graph.project.estimate(
  '*',
  '*',
  {
    nodeCount: 10000000,
    relationshipCount: 80000000
  }
)
YIELD nodeCount, relationshipCount,
      bytesMin, bytesMax, requiredMemory
RETURN nodeCount, relationshipCount,
       bytesMin, bytesMax, requiredMemory;
```

Ở chế độ này, `'*'` chỉ đóng vai trò cú pháp projection hợp lệ; `nodeCount` và `relationshipCount` được **cung cấp như thông số giả định**, không phản ánh số liệu đang tồn tại trong database. Kết quả phụ thuộc engine GDS, cấu hình và cấu trúc graph, nên **không bịa một số GiB cố định** cho kịch bản 10 triệu/80 triệu.

Ước lượng giả định có ích trong giai đoạn thiết kế hạ tầng, nhưng cần chạy lại với graph/projection thật sau khi đã nạp dữ liệu. Nếu graph cần trọng số, label, property, hãy đưa chúng vào cấu hình estimate khi phiên bản/cú pháp hỗ trợ; không dựa vào hai số node và relationship để xác định đầy đủ chi phí.

### 4.3. Độ lớn còn phụ thuộc hướng relationship

Ví dụ native projection theo hướng không định hướng:

```cypher
CALL gds.graph.project.estimate(
  'Person',
  {
    KNOWS: {
      type: 'KNOWS',
      orientation: 'UNDIRECTED'
    }
  },
  {readConcurrency: 4}
)
YIELD nodeCount, relationshipCount,
      bytesMin, bytesMax, requiredMemory
RETURN nodeCount, relationshipCount,
       bytesMin, bytesMax, requiredMemory;
```

Một quan hệ nguồn có thể được biểu diễn ở cả hai hướng khi project `UNDIRECTED`. Vì vậy, đừng lấy số relationship từ `MATCH ()-[r:KNOWS]->() RETURN count(r)` rồi nhân một “hệ số byte/relationship” bất biến. Hãy ước lượng bằng **đúng projection config** mà thuật toán sẽ chạy.

## 5. Ví dụ thực hành: tạo graph nhỏ để kiểm chứng quy trình

Các ví dụ tiếp theo dùng label/type riêng `GdsDemoPerson` và `GDS_LINK` trong **database thử nghiệm**. Dùng `MERGE` theo khóa để có thể chạy lại mà không sinh trùng node/relationship cùng hai đầu.

### 5.1. Tạo dữ liệu mẫu

```cypher
UNWIND [
  {id: 'u1', name: 'An'},
  {id: 'u2', name: 'Bình'},
  {id: 'u3', name: 'Chi'},
  {id: 'u4', name: 'Dũng'}
] AS row
MERGE (p:GdsDemoPerson {id: row.id})
SET p.name = row.name;
```

```cypher
UNWIND [
  {from: 'u1', to: 'u2'},
  {from: 'u2', to: 'u3'},
  {from: 'u3', to: 'u1'},
  {from: 'u3', to: 'u4'},
  {from: 'u4', to: 'u2'}
] AS row
MATCH (a:GdsDemoPerson {id: row.from})
MATCH (b:GdsDemoPerson {id: row.to})
MERGE (a)-[:GDS_LINK]->(b);
```

Graph mẫu có 4 node và 5 relationship được định hướng. Nếu database đã có dữ liệu cùng label/khóa, kết quả đếm có thể khác; chỉ nên chạy trong vùng test đã xác định.

### 5.2. Ước lượng projection trước

```cypher
CALL gds.graph.project.estimate(
  'GdsDemoPerson',
  'GDS_LINK',
  {readConcurrency: 2}
)
YIELD nodeCount, relationshipCount,
      requiredMemory, bytesMin, bytesMax, treeView
RETURN nodeCount, relationshipCount,
       requiredMemory, bytesMin, bytesMax, treeView;
```

Ghi lại kết quả. Trên tập demo ít node, fixed overhead có thể chiếm tỷ lệ lớn; **không lấy số byte trên mỗi node từ graph 4 node rồi ngoại suy thẳng lên 40 triệu node**.

### 5.3. Tạo graph được đặt tên trong GDS catalog

Sau khi xác nhận projection phù hợp, thực hiện:

```cypher
CALL gds.graph.project(
  'gdsDemoGraph',
  'GdsDemoPerson',
  'GDS_LINK'
)
YIELD graphName, nodeCount, relationshipCount, projectMillis
RETURN graphName, nodeCount, relationshipCount, projectMillis;
```

Graph `gdsDemoGraph` nằm trong **GDS graph catalog**, chiếm JVM heap. Việc tạo graph này không tự thay đổi node/relationship của database Neo4j.

Kiểm tra graph đang giữ trong heap:

```cypher
CALL gds.graph.list('gdsDemoGraph')
YIELD graphName, nodeCount, relationshipCount,
      sizeInBytes, memoryUsage
RETURN graphName, nodeCount, relationshipCount,
       sizeInBytes, memoryUsage;
```

`sizeInBytes` và `memoryUsage` cho biết kích thước graph đã project **khi môi trường/JDK hỗ trợ đo đạc**; chúng có thể là `-1` hoặc `null` trên những JDK không hỗ trợ. Không xem giá trị thiếu là graph chiếm 0 byte.

### 5.4. Ước lượng PageRank trước khi chạy

Chọn cùng mode và tham số với lần chạy dự kiến:

```cypher
CALL gds.pageRank.stream.estimate(
  'gdsDemoGraph',
  {
    concurrency: 2,
    maxIterations: 20,
    dampingFactor: 0.85
  }
)
YIELD nodeCount, relationshipCount,
      bytesMin, bytesMax, requiredMemory,
      heapPercentageMax, treeView
RETURN nodeCount, relationshipCount,
       bytesMin, bytesMax, requiredMemory,
       heapPercentageMax, treeView;
```

Đây là **ước lượng phần PageRank chạy trên graph đã tồn tại**. Để quyết định có đủ heap, còn phải xét lượng bộ nhớ graph `gdsDemoGraph` đang giữ, các graph khác và các workload đồng thời.

Nếu kết quả chấp nhận được và **chỉ khi cần chạy thử thật**, câu lệnh:

```cypher
CALL gds.pageRank.stream(
  'gdsDemoGraph',
  {
    concurrency: 2,
    maxIterations: 20,
    dampingFactor: 0.85
  }
)
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).id AS personId, score
ORDER BY score DESC;
```

Mọi điểm PageRank là kết quả cho graph **được project**, không tự cập nhật khi database thay đổi sau đó. Nếu thay đổi `GDS_LINK` hoặc node của DBMS, cần đánh giá lại graph catalog, cập nhật hoặc project lại trước khi phân tích.

## 6. Mode thực thi quyết định chi phí và tác dụng phụ

GDS có các mode phổ biến: `stream`, `stats`, `mutate` và `write`. Chúng có tác dụng và mô hình bộ nhớ khác nhau.

| Mode | Tác dụng | Lưu ý bộ nhớ/vận hành |
| --- | --- | --- |
| `stream` | Trả kết quả từng dòng để Cypher/driver tiêu thụ | Bộ nhớ thuật toán + khả năng tạo luồng kết quả rất lớn; client có thể giữ thêm bộ nhớ nếu gọi `list()` |
| `stats` | Trả một dòng thống kê tổng hợp | Không ghi database, nhưng tính toán thuật toán vẫn có thể tốn nhiều bộ nhớ |
| `mutate` | Lưu kết quả vào **graph GDS trong catalog** | Kết quả mới tiếp tục chiếm heap sau khi chạy, cần quản lý vòng đời |
| `write` | Ghi kết quả về **database Neo4j** | Ngoài bộ nhớ thuật toán còn có transaction state, page cache và chi phí ghi storage |

Chẳng hạn, ước lượng hai mode của cùng thuật toán:

```cypher
CALL gds.pageRank.mutate.estimate(
  'gdsDemoGraph',
  {mutateProperty: 'pageRank', concurrency: 2}
)
YIELD bytesMin, bytesMax, requiredMemory
RETURN bytesMin, bytesMax, requiredMemory;
```

```cypher
CALL gds.pageRank.write.estimate(
  'gdsDemoGraph',
  {writeProperty: 'pageRank', concurrency: 2}
)
YIELD bytesMin, bytesMax, requiredMemory
RETURN bytesMin, bytesMax, requiredMemory;
```

Có thể còn mode `stats` nếu thuật toán cụ thể hỗ trợ. **Không mặc định cả bốn mode luôn có cho mọi thuật toán.** Kiểm tra trang tài liệu thuật toán và procedure được đăng ký ở phiên bản GDS hiện dùng.

### Hai ngộ nhận phổ biến

- “`stats` chỉ trả một dòng nên gần như không tốn RAM.” Thực tế vẫn có thể phải tính điểm số/nhãn cho toàn graph để ra thống kê.
- “`stream` không ghi dữ liệu nên không nguy hiểm.” Một stream cho hàng chục triệu node có thể đẩy một lượng kết quả rất lớn đến client. `RETURN ... LIMIT 10` giúp hạn chế kết quả chuyển về nhưng **không nhất thiết hạn chế phần thuật toán cần tính**.

## 7. Từ `bytesMax` tới quyết định cấp phát heap

### 7.1. Đặt ngân sách theo *đỉnh đồng thời*

Với **một graph đã project**, có thể lập ngân sách sơ bộ:

```text
Heap cần tại đỉnh công việc (mô hình khái niệm)
  ≈ memory của graph catalog đang giữ
  + memory làm việc của các job GDS chạy đồng thời
  + memory Neo4j/transaction/queries khác đang hoạt động
  + vùng dự phòng cho biến động, GC và chênh lệch estimate
```

Khi vừa project graph mới vừa chạy thuật toán, xét thêm dung lượng **projection mới**. Nếu estimate thuật toán đã dùng cấu hình kết hợp projection + execution, phải hiểu phần đã tính trước khi cộng với estimate khác.

**Đây là công thức lập kế hoạch, không phải phép cộng chính xác những bộ nhớ đỉnh không đồng thời.** Cần dùng số đo thực tế và quy trình chạy để xác định các thành phần có chồng lấn thời gian hay không.

### 7.2. Ví dụ ngân sách minh họa

Giả sử server có **JVM heap tối đa 16 GiB**. Theo phép đo/đánh giá riêng của đội vận hành (các con số **giả định**):

| Nhu cầu heap | Ước tính ví dụ |
| --- | ---: |
| Neo4j và transaction khác đang hoạt động | 3 GiB |
| Các graph đã giữ trong GDS catalog | 7 GiB |
| Phần làm việc của PageRank tại đỉnh | 4 GiB |
| Dự phòng vận hành | 3 GiB |
| **Tổng dự trù** | **17 GiB** |

Ngay cả khi `gds.pageRank.stream.estimate` chỉ báo khoảng 4 GiB, ngân sách này **không đủ cho heap 16 GiB** theo các giả định. Có thể giải quyết bằng cách bỏ graph cũ không còn sử dụng, giảm phạm vi projection, phân lịch job hoặc mở rộng heap có kiểm soát.

Không được đọc `heapPercentageMax = 25` rồi kết luận “còn 75% heap trống”. Field này chỉ liên hệ **ước lượng của thao tác** với maximum heap đã cấu hình, không trừ đi các ứng dụng đang dùng heap.

### 7.3. JVM heap khác RAM của máy và page cache

Trên Neo4j tự vận hành, cấu hình heap thường gồm:

```properties
# neo4j.conf — cú pháp minh họa, cần điều chỉnh theo RAM thật
server.memory.heap.initial_size=16G
server.memory.heap.max_size=16G
```

**Không sao chép 16G vào máy có 16 GiB RAM vật lý.** Máy còn cần page cache, native memory, OS và tiến trình khác. Cấu hình heap nên được lập từ tổng ngân sách RAM, loại tải (transaction + analytics), edition/triển khai, page cache và khả năng mở rộng.

Đối với một máy chủ vừa phục vụ API vừa chạy GDS, **không giảm page cache vô điều kiện** để nhường hết RAM cho heap: điều đó có thể làm các truy vấn Cypher đọc/ghi chậm hơn đáng kể. Trên job chuyên phân tích, cân đối có thể khác.

## 8. Những tham số làm thay đổi ước lượng

| Yếu tố | Ảnh hưởng tới footprint | Cách đánh giá |
| --- | --- | --- |
| `nodeCount` | Nhiều thuật toán cần mảng trạng thái theo node | Đo số node trong projection thật |
| `relationshipCount` | Adjacency/graph traversal có thể lớn | Cân nhắc loại, hướng, filter relationship |
| `orientation` | `UNDIRECTED` có thể nhân đôi các cạnh được lưu theo hướng | So estimate với `NATURAL` và nhu cầu thuật toán |
| `nodeProperties`, `relationshipProperties` | Nạp thuộc tính số/weight bổ sung | Chỉ project property thực sự cần |
| `concurrency` | Nhiều worker thường tăng bộ đệm/working set cho một số thuật toán | Chạy `.estimate` với chính xác giá trị dự định |
| `readConcurrency` | Điều khiển đọc khi project; có thể ảnh hưởng chi phí quá trình tạo graph | So với khả năng I/O, CPU, page cache |
| `maxIterations`, `tolerance` | Thường ảnh hưởng thời gian/số vòng; tùy thuật toán có thể ảnh hưởng bộ nhớ | Kiểm tra tài liệu và thay đổi estimate, không suy đoán |
| `mutateProperty` | Kết quả được giữ thêm trong graph GDS | Dự trù footprint sau chạy |
| `writeProperty` và ghi kết quả | Ghi lại store, có transaction và page cache | Đánh giá cả đường ghi dữ liệu và tải DBMS |
| Job đồng thời | Có thể cộng nhiều working sets cùng lúc | Lập lịch và dùng công cụ monitor |
| Node bậc lớn hoặc phân bố lệch | Có thể làm các cấu trúc thuật toán/partition mất cân bằng | Test với mẫu phản ánh high-degree nodes |

**Giảm `concurrency` không bảo đảm giảm bộ nhớ theo tỷ lệ tuyến tính.** Một phần cấu trúc thuật toán phải có bất kể số luồng; ngoài ra điều chỉnh concurrency có thể ảnh hưởng thời gian chạy, CPU và I/O. Phải so estimate và benchmark trên bản thử.

## 9. Kịch bản: graph 50 triệu node, 400 triệu relationship

Giả sử ứng dụng phân tích chuỗi cung ứng muốn chạy PageRank cho graph:

- 50.000.000 node `Company`.
- 400.000.000 relationship `TRADES_WITH`.
- Một số relationship có thuộc tính `annualVolume` nhưng PageRank chưa chắc cần trọng số.
- Neo4j còn đang phục vụ các request Cypher từ Java Driver và Spring Data Neo4j.

Quy trình quyết định:

1. **Xác định đúng câu hỏi:** PageRank có cần mọi doanh nghiệp và mọi quan hệ không? Có cần trọng số `annualVolume` không?
2. **Ước lượng projection giả định** bằng `gds.graph.project.estimate('*', '*', {nodeCount: 50000000, relationshipCount: 400000000})`; nhớ đây là kịch bản thô.
3. **Ước lượng projection theo cấu hình thật** khi đã có dữ liệu; chọn label/type, orientation, properties.
4. **Đo heap hiện tại** và footprint các graph đang tồn tại; xét những job có thể chạy song song.
5. **Ước lượng thuật toán theo từng mode** khi đã có named graph hoặc qua khả năng estimate kết hợp projection của phiên bản GDS.
6. **Đánh giá cận trên và headroom**, quyết định chạy trên cụm/hạ tầng analytics riêng, chia lịch hoặc thu nhỏ tập dữ liệu.
7. **Thử trên tập đại diện**, đo thời gian, GC, page cache và bộ nhớ thực tế. Không chỉ lấy 1% node ngẫu nhiên rồi giả định degree distribution giữ nguyên.
8. Chỉ chạy full workload khi có chỗ trống hợp lý và cơ chế theo dõi, giới hạn, xử lý lỗi.

### Tại sao không nên tự tính “400 triệu cạnh × 8 byte”?

Nếu relationship có hướng, không hướng, property weight, cấu trúc nén hoặc các mảng thuật toán khác nhau thì phép nhân đơn giản sẽ sai. Hai graph có cùng node/relationship count vẫn có thể tiêu thụ tài nguyên khác nhau vì cấu hình projection và dữ liệu thực. **Estimate của GDS là điểm xuất phát đáng tin cậy hơn phép nhân tùy ý**, nhưng vẫn cần quan sát tải thực tế.

### Giảm áp lực bộ nhớ mà không phá bài toán

- Project **đúng tập node/relationship nghiệp vụ cần**. Tránh `'*'` trong production nếu chỉ phân tích một subgraph.
- Tránh project thuộc tính không dùng; nhiều thuật toán graph có thể chạy chỉ với cấu trúc liên kết.
- Sử dụng orientation theo yêu cầu toán học của thuật toán; đừng chuyển `UNDIRECTED` tùy tiện.
- Bỏ các graph GDS và thuộc tính kết quả đã cũ khỏi catalog.
- Cân nhắc giảm concurrency hoặc không chạy đồng thời nhiều job đỉnh nặng.
- Nếu yêu cầu chỉ cần lấy mẫu/kết quả gần đúng, cân nhắc sampling **nhưng nêu rõ ảnh hưởng đến chất lượng phân tích**.
- Tránh giả định có thể chia PageRank thành các partition độc lập rồi ghép kết quả mà vẫn giữ nguyên ngữ nghĩa của toàn graph.

## 10. Giám sát công việc GDS và thu hồi bộ nhớ

### 10.1. Quan sát graph catalog

```cypher
CALL gds.graph.list()
YIELD graphName, nodeCount, relationshipCount,
      sizeInBytes, memoryUsage
RETURN graphName, nodeCount, relationshipCount,
       sizeInBytes, memoryUsage
ORDER BY graphName;
```

Lệnh này giúp nhận biết graph đang giữ heap. Để tránh tốn công tính thống kê không cần thiết trên graph rất lớn, **chỉ `YIELD` các trường định dùng**, chẳng hạn không yêu cầu `degreeDistribution` nếu không phân tích bậc node.

### 10.2. Xem footprint graph và job

Trên môi trường/edition GDS có các procedure monitor tương ứng:

```cypher
CALL gds.memory.list()
YIELD user, name, entity, memoryInBytes
RETURN user, name, entity, memoryInBytes
ORDER BY memoryInBytes DESC;
```

Theo tài liệu GDS, với **graph** đây là dung lượng hiện giữ; với **task đang chạy**, con số là **ước lượng yêu cầu cực đại**, không phải mức dùng chính xác từng mili-giây. Các quyền user/admin quyết định phạm vi có thể xem.

```cypher
CALL gds.systemMonitor()
YIELD freeHeap, totalHeap, maxHeap, ongoingGdsProcedures
RETURN freeHeap, totalHeap, maxHeap, ongoingGdsProcedures;
```

`gds.systemMonitor` cung cấp toàn cảnh JVM heap và các job đang chạy khi tính năng được cung cấp/được cấp quyền. Không được đồng nhất `freeHeap` với RAM vật lý còn trống, hoặc mặc định phép đo tại một thời điểm sẽ giữ nguyên khi job khác bắt đầu.

### 10.3. Giải phóng graph đã dùng xong

Chỉ sau khi mọi job đang dùng named graph đã kết thúc, có thể drop graph demo:

```cypher
CALL gds.graph.drop('gdsDemoGraph')
YIELD graphName
RETURN graphName;
```

Lệnh này **xóa graph projection khỏi GDS catalog**, không xóa node/relationship từ Neo4j database. Nếu graph còn được dùng chung bởi job hoặc user khác, phải xác nhận ownership và kế hoạch phân tích trước khi drop.

Nếu `mutate` tạo nhiều property không còn dùng nhưng vẫn cần giữ graph, xem `gds.graph.nodeProperties.drop` để bỏ property không cần thiết trong catalog. Các thao tác này khác `REMOVE` property trên node Neo4j.

## 11. Kiểm tra tự động và giới hạn của cơ chế chặn thiếu bộ nhớ

GDS có cơ chế **ước lượng tự động trước khi thực thi** với những procedure hỗ trợ estimation, bao gồm tạo graph. Nếu hệ thống xác định chắc chắn lượng heap hiện có không đủ, GDS có thể **từ chối công việc trước khi chạy**.

Điều này giúp tránh một số lần lỗi tốn tài nguyên, nhưng:

- **Được chạy không có nghĩa chắc chắn thành công**. Cơ chế chặn chủ yếu loại các lần chạy chắc chắn không đủ bộ nhớ.
- Lượng heap rảnh có thể thay đổi khi job khác bắt đầu, query transaction tăng tải hoặc graph mới được project.
- GDS không tự đảm bảo toàn bộ môi trường Java/OS còn đủ bộ nhớ ngoài heap.
- Một số thuật toán/mode ở tier thử nghiệm có thể không hỗ trợ estimate đầy đủ.

Tài liệu có đề cập cấu hình `sudo: true` để bỏ qua cơ chế chặn trong một số procedure. **Không dùng `sudo: true` như cách sửa lỗi thiếu heap** khi vận hành graph lớn: nó chỉ vô hiệu hóa hàng rào kiểm tra và có thể dẫn tới mất thời gian, áp lực GC hoặc lỗi memory.

Khi estimate cho thấy nguy cơ cao, ưu tiên **giải phóng graph không dùng, thu nhỏ projection, giảm đồng thời hoặc nâng cấu hình heap có kiểm soát**.

## 12. Java Driver và Spring Data Neo4j: vận hành có kế hoạch

### 12.1. Java Driver gọi `estimate` trước job

Ứng dụng có thể đặt bước estimate thành một **preflight query chỉ đọc**. Ví dụ sau giả sử đã có `Driver driver`, named graph `supplyGraph` được project trước đó và GDS hỗ trợ PageRank:

```java
import java.util.Map;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

String estimateCypher = """
    CALL gds.pageRank.stream.estimate(
      $graphName,
      {concurrency: $concurrency, maxIterations: $iterations}
    )
    YIELD nodeCount, relationshipCount, bytesMin, bytesMax,
          requiredMemory
    RETURN nodeCount, relationshipCount,
           bytesMin, bytesMax, requiredMemory
    """;

try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {

    var estimate = session.executeRead(tx ->
        tx.run(estimateCypher, Map.of(
            "graphName", "supplyGraph",
            "concurrency", 4,
            "iterations", 20
        )).single()
    );

    long bytesMax = estimate.get("bytesMax").asLong();
    System.out.println("GDS estimate upper bound = "
        + bytesMax + " bytes");
}
```

`bytesMax` là dữ liệu số, tốt hơn việc cố parse chuỗi `requiredMemory` như `"2 GiB"`. Trong service thực tế, một bước kiểm tra còn phải biết heap và workload đồng thời; **không tự phê duyệt dựa trên một điều kiện `bytesMax < maxHeap`**.

Nếu tiếp tục chạy thuật toán sau preflight, hãy dùng đúng graph, mode, các tham số của estimate và cơ chế điều phối phù hợp. Không chuyển từ `stream.estimate` sang `mutate` có cấu hình khác rồi giả định ước lượng vẫn đúng.

### 12.2. Spring Data Neo4j

Một Spring service dùng `Neo4jClient` hoặc `@Query` có thể gọi GDS **nếu GDS được cài trên server**. Để chạy một tác vụ phân tích lớn:

1. Tách rõ bước tạo graph, estimate, quyết định tài nguyên, chạy thuật toán và dọn graph.
2. Xác thực quyền đọc schema/project/algorithm; không nhầm Java dependency với plugin GDS cài trên server.
3. Tránh thiết kế một HTTP request ngắn bắt buộc trả hàng triệu kết quả stream trước khi hết timeout. Dùng job/queue theo cơ chế ứng dụng nếu khối lượng yêu cầu.
4. Kiểm soát retry: gọi lại `mutate` hoặc `write` khi kết nối mất có thể tạo/tái ghi thuộc tính; chỉ retry khi đã biết trạng thái job.
5. Đối với kết quả stream lớn, dùng cách tiêu thụ/phân trang/phân lô hợp lý ở client; gọi `list()` sẽ **materialize toàn bộ kết quả vào Java heap của client**.
6. Ghi lại phiên bản Neo4j, GDS, cấu hình projection và số đo estimate để điều tra các thay đổi hiệu năng.

### 12.3. Bộ nhớ của máy chủ và client là hai vấn đề khác nhau

Giả sử GDS đủ heap để tính điểm cho 40 triệu node, nhưng Java Driver gọi `Result.list()` với 40 triệu record; chương trình Java **vẫn có thể hết heap riêng**, dù Neo4j chạy thuật toán thành công. Bởi vậy báo cáo capacity nên có ít nhất:

- **JVM heap Neo4j/GDS** để project và chạy thuật toán.
- **RAM/page cache/native** của host.
- **Client heap và network throughput** để đọc kết quả.
- **Thời gian, concurrency và queue** ở tầng ứng dụng.

## 13. Chẩn đoán các tình huống thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| GDS báo “estimate exceeds available memory” | Graph/algorithm không vừa heap đang rảnh | Xem `bytesMax`, catalog và job khác; giảm tải hoặc tăng heap hợp lý |
| `.estimate` nhỏ nhưng chạy thật bị OOM | Dữ liệu/worker khác biến động, overhead, sai khác estimate | Kiểm tra log, heap, concurrent jobs, cấu hình thực chạy và GC |
| Estimate graph khác xa số row trong database | Filter, orientation, nhãn/loại quan hệ được chọn khác | Xem projection config, `nodeCount`, `relationshipCount` |
| Vừa chạy thuật toán xong vẫn mất nhiều heap | Named graph/mutate properties còn giữ trong catalog | `gds.graph.list`, drop graph/property không còn dùng |
| `gds.graph.list` báo `sizeInBytes = -1` | JDK không hỗ trợ cách đo kích thước graph | Dùng công cụ monitor khác; không coi là 0 byte |
| Giảm `concurrency` không giảm nhiều RAM | Phần lớn memory là state chung của thuật toán | So `.estimate` và benchmark; không kỳ vọng tuyến tính |
| `stream` không ghi DB nhưng ứng dụng Java OOM | Client collect mọi dòng vào `list()` | Tiêu thụ kết quả theo luồng và kiểm soát đầu ra |
| `WRITE` chậm dù estimate đủ | Page cache, transaction state, I/O, index và DBMS contention | Đo đường ghi và tài nguyên storage, không chỉ GDS heap |
| `gds.<algo>.estimate` không tồn tại | Sai tên/mode, GDS thiếu, phiên bản/tier không hỗ trợ | Xem `gds.version()`, `SHOW PROCEDURES`, docs thuật toán |
| Kết quả PageRank không phản ánh quan hệ mới | Graph catalog có thể đã cũ so với database | Cập nhật/reproject graph theo quy trình |
| Lệnh bị chặn nhưng dùng `sudo` thì chạy | Đã bỏ chặn estimate, rủi ro vẫn còn | Không xem là fix; xác minh capacity thực tế |

## 14. Checklist trước một job phân tích lớn

1. **Nghiệp vụ:** chọn thuật toán, output mode, tập node/relationship, weight và độ chính xác cần thiết.
2. **Phiên bản:** kiểm tra Neo4j/GDS và `.estimate` được hỗ trợ cho đúng algorithm/mode.
3. **Graph:** dùng projection thực, ước lượng `gds.graph.project.estimate` và kiểm tra số node/relationship.
4. **Algorithm:** dùng `gds.<algorithm>.<mode>.estimate` với tham số giống lần chạy thật; ghi `bytesMin`, `bytesMax`, `treeView`.
5. **Tài nguyên:** kiểm tra JVM heap max, graph catalog, các công việc đồng thời, page cache, OS và RAM client.
6. **Headroom:** duy trì dự phòng cho biến động, GC và transaction workload; không chỉ xét `heapPercentageMax`.
7. **Thử nghiệm:** chạy trên dữ liệu đại diện có degree distribution tương tự, ghi CPU, bộ nhớ, GC, thời gian.
8. **Điều phối:** giới hạn số job lớn chạy đồng thời, xác định timeout, recovery và retry.
9. **Giám sát:** theo dõi bộ nhớ, tiến độ, log lỗi và chất lượng kết quả.
10. **Dọn dẹp:** chỉ drop graph/mutate properties khi không còn job phụ thuộc; xác nhận bộ nhớ giải phóng.

## 15. Bài tập tự luyện

1. Có graph 2 triệu node, 18 triệu relationship. Viết câu `gds.graph.project.estimate` cho kịch bản giả định và chỉ rõ vì sao đây chưa phải estimate đủ nếu graph cần weight và `UNDIRECTED`.
2. Tạo graph `gdsDemoGraph` trong bài, chạy `gds.pageRank.stream.estimate` và `gds.pageRank.write.estimate`. So sánh `bytesMax` và giải thích tác động thêm của việc ghi kết quả về database.
3. Một máy có maximum heap 24 GiB; graph catalog giữ 10 GiB, các job đang chạy cần tối đa thêm 6 GiB, DBMS/transaction khoảng 3 GiB, job mới cần tối đa 7 GiB. Với giả định các mức chiếm bộ nhớ đồng thời, có nên chạy ngay không? Vì sao?
4. Tại sao `RETURN nodeId, score LIMIT 10` sau `gds.pageRank.stream` không bảo đảm thuật toán chỉ xử lý 10 node?
5. Giải thích sự khác nhau giữa `gds.graph.list`, `gds.memory.list` và `gds.systemMonitor`; số liệu nào dùng để xem projected graph và số liệu nào phản ánh job đang chạy?
6. Nếu thay toàn bộ relationship từ `NATURAL` sang `UNDIRECTED`, những số nào và điều kiện toán học nào cần kiểm tra lại?
7. Thiết kế trình tự preflight cho một Spring service chạy PageRank hàng đêm. Nêu cách tránh retry job ghi trùng, thu hồi catalog và theo dõi heap client lẫn server.

## 16. Ghi nhớ

- **GDS graph projection và thuật toán đều dùng JVM heap**. Graph đã project tồn tại trong catalog cho tới khi được drop hoặc kết thúc vòng đời tương ứng.
- **Ước lượng trước khi nạp graph** bằng `gds.graph.project.estimate(...)`; **ước lượng thuật toán** bằng `gds.<algorithm>.<mode>.estimate(...)`.
- `bytesMin`, `bytesMax` và `treeView` giúp lập kế hoạch, nhưng **không đo bộ nhớ trống** và **không bảo đảm chắc chắn job sẽ thành công**.
- Dự trù **các phần cùng tồn tại trong heap**: graph catalog, thuật toán, Neo4j/transaction và những job khác; giữ dự phòng hợp lý.
- Số node, relationship, orientation, properties, output mode và concurrency ảnh hưởng estimate. Không ngoại suy đơn giản từ một graph quá nhỏ.
- `stream`, `stats`, `mutate`, `write` có **tác dụng và footprint khác nhau**. `mutate` giữ kết quả trong catalog; `write` còn chịu tải ghi database.
- Quan sát `gds.graph.list`, các lệnh memory/monitor khi hỗ trợ và **drop graph không còn dùng**. GDS chạy được không có nghĩa Java client có đủ RAM để lưu hết kết quả.
- **Không bỏ qua kiểm tra heap bằng `sudo`** để chữa tình trạng thiếu bộ nhớ; giảm tải hoặc cấp phát tài nguyên đúng cách.

### Tài liệu tham khảo chính thức

- [Neo4j GDS — Memory Estimation](https://neo4j.com/docs/graph-data-science/current/common-usage/memory-estimation/)
- [Neo4j GDS — System Requirements](https://neo4j.com/docs/graph-data-science/current/installation/System-requirements/)
- [Neo4j GDS — Native projection](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/graph-project/)
- [Neo4j GDS — Cypher projection](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/graph-project-cypher-projection/)
- [Neo4j GDS — Algorithm syntax and execution modes](https://neo4j.com/docs/graph-data-science/current/algorithms/syntax/)
- [Neo4j GDS — PageRank](https://neo4j.com/docs/graph-data-science/current/algorithms/page-rank/)
- [Neo4j GDS — Graph list](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-list/)
- [Neo4j GDS — Dropping graphs](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-drop/)
- [Neo4j GDS — Monitoring system](https://neo4j.com/docs/graph-data-science/current/common-usage/monitoring-system/)
