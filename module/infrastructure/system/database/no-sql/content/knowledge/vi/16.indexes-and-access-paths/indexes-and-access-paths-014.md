# Triển khai và gỡ chỉ mục trong khi ứng dụng hoạt động

Một hệ thống NoSQL đang phục vụ người dùng liên tục không thể tùy tiện dừng ứng dụng mỗi khi cần thêm hoặc xóa chỉ mục. Tuy vậy, **tạo chỉ mục trên dữ liệu lớn là một công việc thật sự**: database phải đọc dữ liệu hiện có, xây cấu trúc truy cập, tiếp nhận các thay đổi phát sinh trong thời gian xây, đồng bộ bản sao/phân vùng và cuối cùng đưa chỉ mục vào trạng thái có thể phục vụ truy vấn. **Gỡ chỉ mục** cũng không chỉ là xóa một tên trong cấu hình: những request phụ thuộc vào chỉ mục ấy có thể đổi query plan, bị từ chối hoặc phải quét nhiều dữ liệu hơn.

Ví dụ, API **“20 đơn đã thanh toán mới nhất của một khách”** đang chậm vì tập đơn tăng nhanh. Đội vận hành muốn thêm một compound index mới, chuyển lưu lượng đọc sang kế hoạch tốt hơn, sau đó gỡ index cũ để giảm chi phí ghi và dung lượng. Nếu thực hiện thiếu thứ tự, hệ thống có thể rơi vào một trong các tình huống:

- Chỉ mục mới đang xây làm **p99 latency** và I/O tăng đột biến.
- Một **unique index** mới bị lỗi vì dữ liệu lịch sử có cặp khóa trùng.
- Request bắt đầu sử dụng index **trước khi nó sẵn sàng** trên hệ có backfill bất đồng bộ.
- Chỉ mục cũ bị xóa nhưng một batch job còn dùng **hint** trỏ đúng index đó.
- Index TTL mới khiến hàng triệu bản ghi hết hạn bị dọn, trái với kỳ vọng triển khai “chỉ thêm index”.
- Một truy vấn hiếm trở thành collection/table scan sau khi gỡ index dù dashboard trung bình vẫn có vẻ bình thường.

Để làm việc an toàn, ta cần coi thay đổi chỉ mục là **một đợt triển khai có vòng đời, kế hoạch đo lường, phương án quay lui và trách nhiệm theo dõi**. Bài học dùng **MongoDB** làm ví dụ thực hành chính; sau đó đối chiếu với **DynamoDB GSI**, **Cassandra secondary index/SAI**, **Redis secondary structures** và **search index/alias**. Những thao tác và bảo đảm phụ thuộc phiên bản, topology và cấu hình của từng sản phẩm, vì vậy các câu lệnh minh họa không phải lệnh được phép chạy trực tiếp trên production mà không qua quy trình kiểm soát.

## 1. Chỉ mục đang hoạt động là thành phần của hợp đồng truy cập

**Chỉ mục (index)** là cấu trúc giúp database tìm những bản ghi cần thiết mà không phải kiểm tra toàn bộ dữ liệu gốc. Với một số NoSQL, chỉ mục được engine quản lý; với hệ khác, ứng dụng duy trì những **bảng truy cập**, **Set/Sorted Set** hoặc **read model** đóng vai trò tương đương một đường truy vấn bổ sung.

Ta phải phân biệt:

| Khái niệm | Ví dụ | Ai chịu trách nhiệm chính? |
|---|---|---|
| **Khóa lưu trữ/chính** | MongoDB _id; DynamoDB table PK/SK; Cassandra partition/clustering key | Schema và engine |
| **Secondary index do engine quản lý** | MongoDB compound index; DynamoDB GSI; Cassandra index theo loại hỗ trợ | Engine, với các giới hạn của sản phẩm |
| **Chỉ mục truy cập do ứng dụng duy trì** | Redis Sorted Set theo customer; Cassandra bảng by_status | Ứng dụng/pipeline ghi và đối soát |
| **Search index chuyên dụng** | OpenSearch/Elasticsearch index theo văn bản | Search engine và luồng đồng bộ dữ liệu |

Ví dụ, **MongoDB createIndex** xây cấu trúc engine quản lý từ các document trong collection; ứng dụng không tự duy trì từng entry của index. Ngược lại, nếu lưu order bằng Redis key rồi lưu ID trong một Sorted Set theo khách hàng, mỗi thao tác tạo/xóa order có thể phải cập nhật **cả value lẫn Sorted Set** theo hợp đồng nghiệp vụ.

**Vận hành chỉ mục là vận hành một đường truy cập.** Khi thêm hoặc gỡ, phải biết request nào đang sử dụng đường đó, bảo đảm kết quả còn đúng và kiểm soát tài nguyên phát sinh.

## 2. “Online” không có nghĩa hoàn toàn không tốn tài nguyên hoặc không có khóa

Trong ngữ cảnh này, **triển khai chỉ mục khi ứng dụng hoạt động (online index deployment)** nghĩa là hệ vẫn tiếp nhận workload trong quá trình thay đổi theo khả năng engine và topology, thay vì chủ động dừng toàn bộ ứng dụng để sửa dữ liệu.

Tuy nhiên, mức “online” có giới hạn:

- Engine có thể cần **khóa ngắn** ở một vài giai đoạn, tùy phiên bản và loại thao tác.
- Xây index đọc lượng dữ liệu lớn và dùng **CPU, RAM, disk I/O, temporary files** hoặc lưu trữ bổ sung.
- Replication, log thay đổi, compaction và hoạt động nền vẫn tiêu thụ tài nguyên.
- Nếu index được dựng ở nhiều replica/shard, mỗi nơi có thể trải qua trạng thái và mức tải khác nhau.
- Công việc build cần theo kịp **ghi mới và cập nhật** xảy ra trong lúc xây.
- Khi index sẵn sàng, query planner và plan cache có thể chọn kế hoạch mới, dẫn đến **độ trễ thay đổi** theo hướng tốt hoặc xấu.
- Một số chỉ mục có **tác dụng nghiệp vụ** như uniqueness hoặc TTL; thêm chúng không chỉ là tối ưu đọc.

Vì vậy không nên cam kết “zero impact” chỉ vì một tài liệu sản phẩm mô tả tính năng online index build. Mục tiêu thực tế là **không gián đoạn dịch vụ vượt SLO, giữ nguyên dữ liệu và bất biến, đồng thời có cách dừng hoặc khôi phục khi chi phí vượt giới hạn**.

## 3. Vòng đời thay đổi chỉ mục

Một đợt thay đổi an toàn thường có các trạng thái:

~~~mermaid
flowchart TD
    A["Đề xuất chỉ mục mới"] --> B["Kiểm kê truy vấn, chỉ mục và dữ liệu"]
    B --> C["Ước lượng chi phí + kế hoạch rollback"]
    C --> D["Tạo chỉ mục / bắt đầu build hoặc backfill"]
    D --> E["Theo dõi tiến độ, lỗi và tải"]
    E --> F{"Chỉ mục sẵn sàng?"}
    F -->|"Không / lỗi"| G["Điều tra, giảm tải hoặc dừng theo runbook"]
    F -->|"Có"| H["Đo query plan + canary"]
    H --> I{"Đạt đúng đắn & SLO?"}
    I -->|"Không"| J["Rollback đường đọc, giữ hoặc gỡ index mới có kiểm soát"]
    I -->|"Có"| K["Chuyển lưu lượng và theo dõi"]
    K --> L["Kiểm kê phụ thuộc index cũ"]
    L --> M["Ẩn/thử không dùng index cũ nếu hỗ trợ"]
    M --> N{"Mọi đường đọc vẫn đạt?"}
    N -->|"Không"| O["Hiện lại/khôi phục đường đọc cũ"]
    N -->|"Có"| P["Gỡ chỉ mục cũ, giám sát sau gỡ"]
~~~

Quy trình gồm **hai thay đổi khác nhau**: thêm đường truy cập mới và bỏ đường truy cập cũ. Không nên gộp chúng thành một bước **drop old → create new** khi hệ đang phục vụ request, vì giữa hai thao tác có thể xuất hiện khoảng trống hiệu năng hoặc thất bại khi xây index mới.

## 4. Ví dụ xuyên suốt: lịch sử đơn hàng của một khách

Giả sử collection MongoDB **orders** có dữ liệu:

~~~javascript
{
  _id: "order-1001",
  tenantId: "shop-a",
  customerId: "customer-07",
  status: "PAID",
  createdAt: ISODate("2026-11-14T09:00:00Z"),
  totalMinor: NumberLong("240000"),
  currency: "VND"
}
~~~

API mới cần:

~~~text
Input:
  tenantId = shop-a
  customerId = customer-07
  status = PAID
  pageSize = 20

Output:
  20 order PAID mới nhất
  thứ tự createdAt DESC, _id DESC
~~~

Query:

~~~javascript
db.orders.find(
  {
    tenantId: "shop-a",
    customerId: "customer-07",
    status: "PAID"
  },
  {
    _id: 1,
    status: 1,
    createdAt: 1,
    totalMinor: 1,
    currency: 1
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Giả sử ứng dụng đang có index:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_customer_recent_v1" }
);
~~~

Index v1 phục vụ lịch sử đơn **không lọc status** khá hợp lý, nhưng query PAID có thể phải duyệt nhiều order PENDING hoặc CANCELLED trước khi tìm đủ 20 order PAID. Một ứng viên mới là:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_customer_status_recent_v2" }
);
~~~

Các field equality được đặt trước, sau đó là các field sort. **V2 không mặc nhiên thay thế V1 cho mọi truy vấn**: nếu một màn hình khác lấy tất cả trạng thái của khách theo thời gian, V1 vẫn có thể tốt hơn vì V2 chèn **status** vào giữa khóa khách và thời gian.

Đây là ví dụ quan trọng: **hai chỉ mục nhìn tương tự không nhất thiết dư thừa**. Trước khi bỏ V1, phải kiểm kê cả đường đọc **có status** và **không status**.

## 5. Lập danh sách các truy vấn và phụ thuộc trước khi tạo hoặc gỡ

Một **query inventory** tối thiểu nên liệt kê:

| Query hoặc workflow | Điều kiện và sort | Tần suất | Đường truy cập hiện tại | Hậu quả nếu mất đường này |
|---|---|---|---|---|
| Chi tiết order | _id, tenantId/owner | Rất thường | _id index | Lookup chậm/sai quyền nếu fallback yếu |
| Lịch sử mọi trạng thái | tenantId + customerId, createdAt DESC | Thường | idx_customer_recent_v1 | Có thể cần scan/sort |
| Lịch sử PAID | tenantId + customerId + status, createdAt DESC | Thường | V1 + filter; dự kiến V2 | Độ trễ cao khi ít PAID |
| Quản trị viên xem đơn theo status | tenantId + status, createdAt DESC | Vừa | Index/read model riêng nếu có | Có thể quét nhiều khách |
| Worker timeout order | status + updatedAt range | Định kỳ | Một index khác | Job quá hạn, tăng backlog |
| Tạo/đổi trạng thái | _id, expected status | Thường xuyên | _id index + conditional update | Không được làm hỏng logic ghi |
| Báo cáo tháng | tenantId + time range | Hàng ngày | Analytics hoặc đường đọc riêng | Có thể kéo dài batch |

Hãy xem cả **đường truy cập ít xuất hiện nhưng quan trọng**: batch đối soát cuối tháng, quy trình xử lý sự cố, màn hình admin, các phiên bản ứng dụng cũ và những query có **hint(indexName)** cố định.

Nếu một client vẫn gọi **hint("idx_customer_recent_v1")** mà index bị ẩn hoặc gỡ, query đó có thể lỗi thay vì tự chuyển sang index mới. Do đó cần kiểm tra dependency trong source, truy vấn được ghi nhận, dashboard và các job đang chạy theo quy trình của đội vận hành.

**Việc một index ít được dùng trong giờ cao điểm không đủ để khẳng định nó không còn cần thiết.**

## 6. Chuẩn bị trước khi chạy index build

Một bản **preflight** nên có:

1. **Phiên bản engine và topology:** standalone, replica set, sharded cluster, managed service; các khả năng/giới hạn index build cụ thể.
2. **Thống kê dữ liệu:** số document, kích thước, phân bố tenant, tỷ lệ null/missing, mảng lớn, tốc độ tăng.
3. **Trạng thái chỉ mục:** tên, key pattern, options, uniqueness, partial filter, TTL, collation và dung lượng hiện tại.
4. **Truy vấn hiện tại:** p50/p95/p99, keys/docs examined, tỷ lệ scan, số lượng sort, throughput.
5. **Tài nguyên:** dung lượng trống, RAM, IOPS, CPU, log/replication lag, khả năng xử lý peak traffic.
6. **Dự báo tác động:** ước lượng index size, thời gian build qua thử nghiệm đại diện, write amplification sau build.
7. **Dữ liệu sai:** duplicate candidates, giá trị không hợp lệ, kiểu mảng/chỉ mục không tương thích.
8. **Lịch và cửa sổ triển khai:** chọn khoảng tải phù hợp, biết các job lớn đang chạy, có ngưỡng dừng.
9. **Phương án rollback:** query flag, index cũ còn hay không, cách khôi phục nếu drop, chủ sở hữu xử lý.
10. **Chỉ số cảnh báo:** latency, error rate, read/write throttling, replication lag, free disk và thời gian build.

Trong MongoDB, trên môi trường được phép quan sát:

~~~javascript
// Danh sách index và các thuộc tính hiện tại
db.orders.getIndexes();

// Số document hiện tại, chỉ là một phần của dự báo kích thước
db.orders.estimatedDocumentCount();

// Thống kê collection và kích thước index
db.orders.stats();

// Cách các index đã được truy cập trong khoảng thống kê
db.orders.aggregate([{ $indexStats: {} }]);
~~~

**$indexStats** có thể giúp nhận diện index được dùng, nhưng số lần truy cập cần được hiểu trong **khoảng thời gian mà thống kê có hiệu lực**, có thể bị reset khi restart hoặc các thay đổi liên quan. Nó không đo đầy đủ tầm quan trọng của index, không thay thế query inventory và không chứng minh index không dùng khi số đếm bằng 0.

**estimatedDocumentCount** là phép ước lượng dựa trên metadata trong những ngữ cảnh phù hợp; không được dùng như số kiểm kê chính xác tuyệt đối cho migration phức tạp.

## 7. Thiết lập baseline bằng explain và số liệu API

Trước khi tạo index mới, đo query đại diện:

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  customerId: "customer-07",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

Một số trường nên xem trong kết quả MongoDB:

| Chỉ số | Câu hỏi |
|---|---|
| **winningPlan** | Query planner chọn đường nào? |
| **IXSCAN / COLLSCAN** | Duyệt index hay scan collection? |
| **SORT** | Có sort riêng ngoài đường truy cập index không? |
| **nReturned** | Có bao nhiêu document được trả về? |
| **totalKeysExamined** | Bao nhiêu index keys đã được xét? |
| **totalDocsExamined** | Bao nhiêu document gốc đã được xét? |
| **executionTimeMillis** | Thời gian thực thi ở phép đo đó là bao nhiêu? |

Không nên dựa vào một lần **explain** trên 10 document mẫu để dự đoán production có 100 triệu document. Độ chọn lọc, dữ liệu skew, cache nóng/lạnh, quyền đọc của tenant và mức đồng thời có thể thay đổi kết quả.

Ghi thêm metric ở API: **p95/p99 latency**, timeout, error rate, số request đang chờ, tải primary/replica và độ trễ replication. **Một query plan đẹp nhưng khiến write latency tăng quá SLO vẫn có thể là một rollout không đạt**.

## 8. Tạo compound index MongoDB khi ứng dụng vẫn phục vụ request

Ví dụ thay đổi tăng thêm, **không gỡ V1**:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_customer_status_recent_v2"
  }
);
~~~

Ý nghĩa:

- MongoDB phải xây entry từ các document đã tồn tại.
- Trong khi build, hệ còn nhận những thay đổi tùy theo cơ chế của phiên bản/topology.
- Index được đưa vào sử dụng khi build hoàn thành và đáp ứng điều kiện cam kết/đồng bộ của deployment.
- Có thể có tăng disk, I/O, CPU và ảnh hưởng đến tốc độ ghi.
- Sau khi sẵn sàng, planner có thể chọn index mới cho query phù hợp.

**Không nên nói lệnh này luôn chạy “hoàn toàn nền, không khóa”.** Trên các phiên bản MongoDB hiện đại, cơ chế build được tối ưu để phần lớn thời gian vẫn cho phép truy cập đồng thời, nhưng có các giai đoạn cần phối hợp/khóa, và chi tiết khác nhau theo phiên bản/triển khai. Tùy chọn legacy **background: true** không phải một cách chung đáng tin để ép việc build trên mọi phiên bản mới; phải tham chiếu cơ chế index build của engine đang dùng.

Đặc biệt trong replica set/sharded cluster, cần tuân thủ quy trình tạo index phù hợp với **commit quorum, các member và shard**, thay vì chỉ nhìn việc command trên một node trả kết quả. Khi triển khai thực tế, hãy dùng endpoint và hướng dẫn quản trị của sản phẩm/phiên bản đang chạy.

## 9. Vì sao build lâu không có nghĩa command bị treo?

Đối với collection lớn, build có thể phải:

~~~text
Quét dữ liệu hiện có
    |
    v
Tạo/ghi index entries và các cấu trúc trung gian
    |
    v
Theo dõi hoặc hợp nhất các thay đổi phát sinh trong lúc build
    |
    v
Phối hợp commit/sẵn sàng theo topology
    |
    v
Index có thể được dùng theo hợp đồng engine
~~~

Chi phí phụ thuộc:

- Số lượng document và số index entries tạo ra.
- Số phần tử array trong multikey index.
- Kích thước khóa index, collation và loại index.
- Số ghi đồng thời, đặc biệt những ghi sửa indexed fields.
- Dung lượng bộ nhớ cấp cho build, temporary files, disk bandwidth.
- Replication health và topology.
- Những index build/maintenance task khác đang cạnh tranh tài nguyên.

Một index trên trường mảng có thể tạo **nhiều entry cho một document**. Vì thế 10 triệu document không nhất thiết chỉ tạo 10 triệu index keys.

Trong đợt build cần có dashboard cho tiến độ/thời gian, CPU, memory, disk free, read/write throughput, replication lag và API tail latency. Nếu chỉ thấy “command chưa trả” mà không có dấu hiệu về tác động và tiến độ, rất khó phân biệt build bình thường với bế tắc vận hành.

## 10. Sẵn sàng sử dụng không chỉ là index xuất hiện trong schema

Khi lệnh tạo index hoàn thành thành công trong MongoDB, ta có thể kiểm tra:

~~~javascript
db.orders.getIndexes();

db.orders.find({
  tenantId: "shop-a",
  customerId: "customer-07",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

Đầu ra **getIndexes** cần có đúng **name, key pattern và options** dự kiến, không chỉ một tên gần giống. Nếu muốn xác định query có dùng index mới, xem plan. Một index có tồn tại không bảo đảm planner luôn chọn nó; điều đó phụ thuộc dữ liệu và query shape.

Trong các hệ có chỉ mục được build/backfill bất đồng bộ như **DynamoDB GSI**, một index ở trạng thái đang tạo **chưa tương đương** với index đã **ACTIVE**. Không được áp quy tắc “command đã gửi nên client Query ngay” lên mọi NoSQL.

## 11. Đánh giá chỉ mục mới trước khi chuyển toàn bộ lưu lượng

Một chỉ mục có thể cải thiện query đích nhưng làm xấu query khác hoặc làm tăng chi phí ghi:

| Nhóm đánh giá | Cần quan sát |
|---|---|
| **Đúng kết quả** | Filter/status/range/sort trả đúng bộ record và thứ tự |
| **Đường đọc đích** | Ít keys/docs examined hơn, không sort tốn kém ngoài mong muốn |
| **Đường đọc cũ** | Query không status, admin reports và worker vẫn ổn |
| **Ghi** | Insert/update throughput, write latency, lock/conflict/throttling |
| **Replication** | Lag, health, khả năng catch-up |
| **Dung lượng** | Index size, free disk, growth |
| **Tính mới của dữ liệu** | Không chuyển dữ liệu bất biến sang nguồn eventual không phù hợp |
| **Độ ổn định** | p95/p99 dưới concurrency và traffic skew |

Nếu ứng dụng có **feature flag**, có thể chuyển một tỷ lệ request sang đường truy cập/query shape mới. Nếu query không đổi mà chỉ thêm index engine-managed, vẫn nên quan sát phân bố query plan và có cách rollback an toàn khi một số request bị chậm.

Không nên ép **hint(index mới)** trên mọi query chỉ để báo cáo rằng index đã được sử dụng. Một hint có thể bỏ qua lựa chọn tốt hơn của planner và trở thành dependency nguy hiểm khi index bị ẩn/gỡ. Chỉ dùng hint trong thử nghiệm có kiểm soát nếu cần so sánh, rồi quản lý việc loại bỏ hint khỏi production.

## 12. Hidden index: thử bỏ đường truy cập trước khi xóa

MongoDB hỗ trợ **hidden indexes** ở những phiên bản hỗ trợ tính năng này. Một index **hidden** vẫn tồn tại và tiếp tục được duy trì khi dữ liệu ghi thay đổi, nhưng query planner **không xét dùng index đó**.

Điều này giúp mô phỏng hiệu ứng của việc gỡ index ở khía cạnh **kế hoạch truy vấn** mà chưa phải tái xây nếu quyết định sai:

~~~javascript
// Chỉ làm ở bước thử nghiệm gỡ được phê duyệt.
db.orders.hideIndex("idx_customer_recent_v1");
~~~

Sau đó đo các đường đọc:

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  customerId: "customer-07"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

Nếu query lịch sử mọi trạng thái chậm rõ rệt hoặc một client dựa vào hint bị lỗi, **hiện lại index**:

~~~javascript
db.orders.unhideIndex("idx_customer_recent_v1");
~~~

**Những giới hạn quan trọng của hidden index:**

- Index vẫn chiếm dung lượng và vẫn có chi phí duy trì khi ghi; **hide không đo được đầy đủ lợi ích giảm chi phí ghi/dung lượng của drop**.
- Nếu index là **unique**, việc hide **không tắt ràng buộc duy nhất**.
- Nếu index là **TTL**, việc hide **không dừng tác dụng TTL/xóa dữ liệu hết hạn**.
- Query dùng **hint** để chỉ rõ hidden index không thể dựa vào nó như trước, tùy API sẽ bị từ chối.
- Có thể có khác biệt về plan cache và hành vi planner sau khi đổi trạng thái hidden; cần đo lại dưới tải thực.

Vì thế hidden index là **công cụ thử nghiệm khả năng bỏ index cho truy vấn**, không phải cách tắt mọi tác dụng của chỉ mục.

## 13. Gỡ index cũ là một đợt triển khai riêng

Giả sử V2 đã hoạt động tốt. **Không được gỡ V1 chỉ vì V2 có nhiều field hơn**. Phải xác nhận V1 không còn cần cho các query bỏ qua status.

Một lịch gỡ hợp lý:

1. **Kiểm kê** mọi đường đọc/ghi và mọi hint liên quan V1.
2. **Xác nhận** V2 hoặc các index khác đáp ứng truy vấn còn lại.
3. **Ẩn V1** trong một khoảng quan sát có đại diện workload nếu phiên bản hỗ trợ.
4. **Đo** latency, scanned/returned, errors, CPU, memory và các job định kỳ.
5. **Hiện lại** nếu có regression; chưa phải xây lại từ đầu.
6. **Chỉ sau khi được chấp thuận**, gỡ V1 trong một lần triển khai riêng.
7. **Theo dõi sau gỡ** và giữ tài liệu tạo lại index nếu cần.

Minh họa thao tác:

~~~javascript
// Chỉ thực hiện sau khi đã đánh giá phụ thuộc và chấp thuận.
db.orders.dropIndex("idx_customer_recent_v1");
~~~

**dropIndex là thay đổi thật**: index không còn dùng cho các truy vấn, không còn duy trì khi ghi và phải được **build lại** nếu muốn khôi phục. Thời gian khôi phục có thể lớn với collection hàng trăm triệu document; do đó rollback của **drop** khác rollback của **hide**.

Không nên tự động gỡ index theo một rule như “số accesses bằng 0 trong 24 giờ”. Một query kiểm toán hàng tháng hoặc quy trình khắc phục sự cố có thể là lý do duy nhất index tồn tại.

## 14. Unique index không chỉ là tối ưu hiệu năng

Một unique index bảo vệ **bất biến dữ liệu**, ví dụ không có hai enrollment hiện hành cho cùng cặp:

~~~text
tenantId + studentId + courseId
    -> tối đa một enrollment theo quy tắc nghiệp vụ
~~~

Tạo một unique index trên collection đang chứa dữ liệu không sạch có thể thất bại:

~~~javascript
db.enrollments.createIndex(
  { tenantId: 1, studentId: 1, courseId: 1 },
  {
    unique: true,
    name: "uniq_enrollment_pair"
  }
);
~~~

Trước khi tạo, cần **khảo sát duplicate** trên dữ liệu thực:

~~~javascript
db.enrollments.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        studentId: "$studentId",
        courseId: "$courseId"
      },
      count: { $sum: 1 }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $limit: 20 }
]);
~~~

**Một sample không có duplicate chưa chứng minh toàn collection sạch.** Trước khi tạo unique index, cần kiểm kê đầy đủ trong phạm vi liên quan hoặc có cơ chế xác minh đủ mạnh. Cũng phải xét **missing/null**, dạng dữ liệu khác kiểu, cách chuẩn hóa ID và dữ liệu tenant.

Vấn đề khó hơn là **khoảng đua (race window)**: sau khi job kiểm tra xong nhưng trước khi unique index build hoàn tất, writer đang chạy vẫn có thể tạo duplicate. Nếu uniqueness là bất biến cứng, cần kế hoạch chuyển writer sang cơ chế chống trùng phù hợp, khóa/điều phối, cửa sổ kiểm soát ghi hoặc phương án migration được engine hỗ trợ. Chỉ chạy aggregate rồi createIndex trong lúc ghi tự do không chứng minh việc build sẽ thành công.

### Không gỡ unique index như gỡ index hiệu năng

Nếu unique index là **lớp bảo vệ duy nhất** chống trùng ở database, gỡ nó có thể làm dữ liệu bị ghi trùng ngay sau đó. Việc API có câu **findOne trước khi insert** không bảo vệ được hai request đồng thời.

Muốn thay unique constraint, cần:

- Xác định rõ invariant mới.
- Thiết kế unique key/index thay thế hoặc cơ chế bảo vệ ghi tương đương.
- Backfill và giải quyết dữ liệu không đạt điều kiện.
- Đưa constraint mới vào trạng thái có hiệu lực.
- Chuyển writer nếu key/logic thay đổi.
- Chỉ gỡ constraint cũ khi bất biến còn được bảo vệ.

**Hide unique index không tắt tính unique**, nên không thể dùng hide để thử nghiệm tính đúng của việc bỏ constraint. Đây là thay đổi nghiệp vụ, không chỉ đổi query planner.

## 15. Partial index: ít dữ liệu hơn nhưng query phải phù hợp điều kiện

MongoDB cho phép **partialFilterExpression** để chỉ index document thỏa một điều kiện:

~~~javascript
db.enrollments.createIndex(
  { tenantId: 1, studentId: 1, courseId: 1 },
  {
    name: "uniq_active_enrollment",
    unique: true,
    partialFilterExpression: { status: "ACTIVE" }
  }
);
~~~

Ví dụ này bảo vệ **tối đa một enrollment ACTIVE cho cùng cặp**, trong khi các bản ở trạng thái khác không tham gia unique constraint đó. Nếu nghiệp vụ cho phép nhiều lượt đăng ký lịch sử, partial unique có thể phù hợp hơn unique tuyệt đối trên cặp ID.

Nhưng cần hiểu:

- Một document đổi từ **PAUSED → ACTIVE** vẫn phải thỏa uniqueness.
- Một query không có điều kiện đủ để chứng minh subset của partial filter có thể không được planner chọn dùng index theo cách mong đợi.
- Tập giá trị **status** cần được chuẩn hóa; **ACTIVE**, **active** và missing không tự tương đương.
- Nếu nghiệp vụ phân biệt các kiểu trạng thái active khác, partial filter phải phản ánh đúng hợp đồng.
- Việc đổi partial filter là thay đổi ý nghĩa chỉ mục; cần kế hoạch index mới và bỏ index cũ, không mặc định có thể “sửa trực tiếp” mọi index option.

Khi online rollout một partial unique index, phải kiểm tra cả **độ bao phủ query** lẫn **bất biến ghi**, vì một thay đổi index có thể ảnh hưởng đến hai phương diện cùng lúc.

## 16. TTL index: triển khai online có thể tạo tác động xóa dữ liệu

**TTL index** là trường hợp đặc biệt: nó phục vụ vòng đời dữ liệu bằng cách khiến engine xóa document hết hạn theo điều kiện TTL.

Ví dụ collection session có trường **expiresAt** kiểu BSON Date:

~~~javascript
{
  _id: "session-101",
  tenantId: "shop-a",
  expiresAt: ISODate("2026-11-15T00:00:00Z")
}
~~~

Một TTL index có thể được cấu hình:

~~~javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  {
    name: "ttl_sessions_expiry",
    expireAfterSeconds: 0
  }
);
~~~

Ví dụ này có nghĩa document đạt thời điểm **expiresAt** là ứng viên để TTL monitor dọn theo cơ chế của MongoDB. **Không bảo đảm** document bị xóa chính xác đúng mili giây đó; TTL deletion diễn ra bất đồng bộ.

Rủi ro khi tạo TTL index trên collection cũ:

- Có thể có rất nhiều document **đã quá hạn** ngay từ trước khi tạo index.
- Sau khi index hoạt động, TTL monitor có thể bắt đầu dọn số lượng lớn, tạo tải I/O và replication.
- Nếu **expiresAt** sai timezone, sai kiểu hoặc bị ghi nhầm, quy tắc xóa có thể không đúng dự kiến.
- Việc xóa có thể ảnh hưởng read models, cache, analytics hoặc retention/chứng từ.
- Xóa dữ liệu là hành động **khó đảo ngược** nếu không có backup/khả năng phục hồi phù hợp.

Trước khi tạo TTL index, phải có khảo sát dữ liệu sắp bị xóa, xác nhận chính sách retention, chọn lộ trình dọn theo batch nếu cần và theo dõi delete rate. **Hidden TTL index vẫn có hành vi TTL**, nên không dùng **hideIndex** để thử “tạm dừng xóa”. Nếu muốn thay chính sách retention, phải nghiên cứu cách sửa/gỡ TTL theo phiên bản và bảo đảm không vi phạm nghĩa vụ lưu giữ.

## 17. Index trên field mảng và những giới hạn bất ngờ

Một collection có thể chứa:

~~~javascript
{
  _id: "order-1001",
  tenantId: "shop-a",
  items: [
    { sku: "BOOK-01", quantity: 2 },
    { sku: "PEN-02", quantity: 1 }
  ]
}
~~~

Nếu cần tìm order theo SKU:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, "items.sku": 1 },
  { name: "idx_orders_by_item_sku" }
);
~~~

Vì **items.sku** lấy giá trị từ mảng, MongoDB có thể tạo **multikey index**. Một document có nhiều SKU có thể đóng góp nhiều index entries. Khi đo chi phí build, không được lấy **document count** làm số index entries một-một.

Nếu định thêm nhiều trường mảng vào cùng một compound index, cần kiểm tra quy tắc của MongoDB về **compound multikey indexes** và dữ liệu thực tế; một số tổ hợp nhiều array field không được phép và có thể khiến index creation thất bại hoặc write sau đó bị từ chối.

Đối với collection lớn, **kiểm kê hình dạng dữ liệu và thử nghiệm representative data** là bước quan trọng trước khi triển khai index trên nested/multikey fields.

## 18. Replica set và sharded cluster: index rollout là công việc phân tán

Trong một hệ nhiều node, index build có thêm chiều phối hợp:

~~~text
Ứng dụng / driver
        |
        v
Replica set hoặc mongos/sharded cluster
        |
        +-- Member/shard A: xây index
        +-- Member/shard B: xây index
        +-- Member/shard C: xây index
        |
        v
Chỉ mục đủ điều kiện hoàn tất theo cơ chế triển khai
~~~

Cần làm rõ:

- Lệnh index build được **gửi qua endpoint nào**?
- Ai chịu trách nhiệm build trên replica members/shards?
- **Commit quorum** hoặc cơ chế hoàn tất của phiên bản đang dùng là gì?
- Nếu một member không khả dụng hoặc chậm, index build tiến triển ra sao?
- Replication lag có tăng trong giai đoạn build hoặc sau đó không?
- Shard nào đang nóng, có đủ disk/memory không?
- Có truy vấn nào được route theo shard key nhưng index mới chỉ giúp filter trong shard không?
- Các unique constraints có giới hạn khi collection được sharding không?

Không nên tự thực hiện createIndex trên một node thứ cấp hoặc mỗi shard theo một script tùy tiện nếu hướng dẫn sản phẩm yêu cầu thao tác ở endpoint khác. Quy trình vận hành index của standalone MongoDB không tự áp dụng nguyên vẹn cho sharded deployment.

Nếu có **rolling upgrade** của cluster, cần xác định phiên bản/feature compatibility và các thao tác index được hỗ trợ trước khi thay đổi. Câu lệnh có thể được chấp nhận ở một version nhưng có giới hạn khác ở version khác.

## 19. Điều kiện dừng khi index build ảnh hưởng sản xuất

Trước rollout, viết ra **stop conditions** thay vì quyết định theo cảm giác trong lúc hệ đã chậm:

| Tín hiệu | Ví dụ ngưỡng cần đặt theo SLO nội bộ | Hướng hành động |
|---|---|---|
| p99 latency tăng | Vượt ngưỡng cảnh báo liên tục | Giảm tải/đánh giá dừng index build |
| Error/timeout rate tăng | Vượt error budget giai đoạn rollout | Dừng mở rộng canary, điều tra |
| Disk free giảm | Tiệm cận ngưỡng an toàn cho dữ liệu/index/tmp | Tạm dừng hoặc dừng theo runbook |
| Replication lag tăng | Vượt mức app cho phép đọc/khôi phục | Giảm áp lực, xem topology |
| Write throttling/conflict tăng | Ảnh hưởng checkout hoặc thao tác nghiệp vụ | Ưu tiên an toàn ghi |
| Job nền tồn đọng | Queue lag/backlog tăng nhanh | Tránh đẩy thêm workload |
| Index build thất bại | Duplicate, invalid data, resource/coordination | Giữ index cũ, sửa nguyên nhân |
| Query plan regression | Một nhóm query quan trọng chậm | Rollback query flag/hiện index cũ |

Ngưỡng số cụ thể phải dựa trên baseline và SLO của chính dịch vụ. Không nên lấy một ngưỡng CPU hay thời gian build cố định áp dụng cho mọi cluster.

**Dừng một index build** cũng là thao tác quản trị có cơ chế riêng theo version. Không tùy tiện kill một process hoặc node database chỉ vì build lâu; hãy dùng cơ chế abort/cancel được sản phẩm hỗ trợ và hiểu hậu quả tới replica set/shard. Dù build bị dừng, vẫn cần xác nhận trạng thái index và tài nguyên sau đó.

## 20. Kế hoạch rollback phải phân biệt các mốc thay đổi

Rollback không phải một nút chung:

| Mốc | Trạng thái | Rollback ứng viên |
|---|---|---|
| Chưa build | Chỉ có proposal | Không thực hiện index mới |
| Build đang chạy | Có tác động tài nguyên | Hủy theo cơ chế hỗ trợ, xác minh trạng thái |
| Build hoàn tất, chưa đổi query | Index mới tồn tại, V1 còn | Giữ hoặc gỡ index mới khi an toàn |
| Canary đã đổi query | Một phần traffic theo đường mới | Tắt flag/hủy hint, trở về query cũ |
| V1 đã hide | V1 còn tồn tại nhưng planner không dùng | **unhideIndex** để khôi phục nhanh |
| V1 đã drop | V1 không còn | Phải **createIndex** lại, có thể build lâu |
| Unique index đã gỡ | Constraint nghiệp vụ có thể mất | Khôi phục bảo vệ ghi trước, đối soát dữ liệu phát sinh |
| TTL index đã bắt đầu xóa | Dữ liệu có thể bị xóa thật | Dừng tác động theo chính sách; cần phục hồi dữ liệu nếu phải khôi phục |

Một deployment nên có **người chịu trách nhiệm quyết định rollback**, cách liên lạc, dấu hiệu xác nhận khôi phục và khoảng quan sát sau rollback.

**Khôi phục hiệu năng** và **khôi phục dữ liệu** là hai vấn đề khác nhau. Có thể xây lại một index bị drop, nhưng không thể chỉ xây lại index để lấy lại những document đã bị TTL xóa.

## 21. Chỉ mục mới không nên làm thay đổi kết quả nghiệp vụ ngoài ý định

Về nguyên tắc, index thường phục vụ việc tìm bản ghi, không được làm API tự đổi ý nghĩa lọc. Tuy nhiên, một số sai lầm rollout khiến kết quả thay đổi:

### Query dùng Limit trước điều kiện đúng

Nếu một read model được xây theo customer/time rồi ứng dụng lấy 20 order và **lọc status=PAID trong app**, kết quả có thể ít hơn 20 dù tồn tại nhiều PAID sâu hơn. Một access path mới theo customer/status/time có thể sửa vấn đề; lúc chuyển phải xác nhận **limit sau đúng điều kiện**, không chỉ so latency.

### Thay đổi collation

Một index dùng **collation** khác có thể ảnh hưởng việc so sánh/sort chuỗi và được planner sử dụng tùy query collation. Không nên thay index tên giống nhau nhưng thay đổi quy tắc phân biệt chữ hoa/dấu mà không kiểm chứng kết quả.

### Sparse/partial index

Một partial index chỉ chứa document thỏa filter. Nếu query muốn cả bản ghi không thỏa filter, không được ép dùng index mà bỏ sót những bản đó.

### Unique index

Index unique có thể làm thao tác ghi mới bị từ chối, là thay đổi hành vi API theo chủ đích nếu hợp đồng yêu cầu. Cần chuẩn bị mã lỗi và xử lý duplicate, không chỉ benchmark query.

### TTL index

Index có thể làm thay đổi **tập dữ liệu thực tế** vì xóa document hết hạn. Phải tách kiểm chứng tính đúng của retention khỏi kiểm chứng tốc độ đọc.

## 22. DynamoDB: thêm hoặc xóa GSI khi table đang phục vụ traffic

**Global Secondary Index (GSI)** cho phép Query table theo một partition/sort key khác khóa chính. DynamoDB hỗ trợ thêm GSI vào table hiện hữu theo cơ chế online; trong khi tạo, hệ thống phải **backfill** index từ các item hiện có và xử lý thay đổi mới.

Giả sử table **Orders** dùng khóa chính theo orderId nhưng cần đọc theo tenant/customer/status/time:

~~~text
Table primary key:
  PK = ORDER#order-1001

GSI ứng viên:
  GSI1PK = TENANT#shop-a#CUSTOMER#customer-07#STATUS#PAID
  GSI1SK = 2026-11-14T09:00:00.000Z#order-1001
~~~

Lộ trình:

1. **Xác định** GSI partition/sort key, projected attributes, những item được index và chi phí duy trì.
2. **Kiểm kê** các item có attribute key sai kiểu hoặc không đủ điều kiện; GSI có thể là **sparse index** nếu key attributes không tồn tại.
3. **Ước lượng dung lượng và write capacity** của GSI trên dữ liệu hiện có.
4. **Tạo GSI** bằng cơ chế cập nhật table được DynamoDB hỗ trợ.
5. **Theo dõi trạng thái** tạo/backfill và những chỉ số capacity/throttling.
6. **Chỉ chuyển Query** khi index ở trạng thái **ACTIVE** theo hợp đồng sản phẩm.
7. **Đo latency, ConsumedCapacity và số item đọc/trả** cùng tính đúng của kết quả.
8. **Xóa GSI cũ** sau khi ứng dụng không còn Query index ấy, và theo dõi sau gỡ.

Trong DynamoDB, **GSI chỉ hỗ trợ đọc nhất quán sau cùng (eventually consistent reads)**; không nên dùng một GSI làm nguồn duy nhất cho quyết định cứng như “một người chỉ được sở hữu một vé” hoặc “tồn kho không âm”. Những bất biến đó cần điều kiện ghi/transaction tại nguồn có thẩm quyền.

**Local Secondary Index (LSI)** khác GSI: LSI gắn với thiết kế table và nhìn chung phải được khai báo **khi tạo table**, không thể thêm vào table đã tồn tại như GSI. Vì vậy “thêm chỉ mục online” không phải tính năng chung cho mọi loại index DynamoDB.

### Rủi ro backfill và ghi mới

Trong quá trình GSI build, write capacity dành cho index và việc xử lý dữ liệu cũ/mới có thể gây áp lực lên table. Nếu GSI bị thiếu capacity, thao tác ghi vào table có thể bị ảnh hưởng bởi throttling liên quan index. Cần theo dõi trạng thái index và các metric online index build theo phiên bản/tài khoản, điều chỉnh capacity và traffic phù hợp.

Khi drop GSI, Query chỉ rõ **IndexName** đó sẽ không còn hoạt động. Do đó đổi ứng dụng/feature flag phải đi **trước** thao tác xóa GSI. Việc index được xóa không khiến API tự chuyển mọi Query sang scan base table.

## 23. Cassandra: thêm secondary index/SAI không thể thay thiết kế khóa chính

Trong Cassandra, đường truy cập nền tảng là **partition key + clustering key**. Một số phiên bản/triển khai hỗ trợ **secondary indexes** hoặc **Storage-Attached Index (SAI)** cho những truy vấn phù hợp.

Ví dụ bảng:

~~~sql
CREATE TABLE orders_by_customer (
    tenant_id text,
    customer_id text,
    created_at timestamp,
    order_id text,
    status text,
    total_minor bigint,
    PRIMARY KEY ((tenant_id, customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
~~~

Query theo customer/time đã phù hợp primary key. Nếu đội muốn tìm theo **status**, việc thêm một index lên status không mặc nhiên khiến query xuyên tất cả khách trở nên rẻ:

~~~text
Input:
  tenantId = shop-a
  status = PAID
  date range = 30 ngày

Partition gốc:
  tenantId + customerId

Thiếu customerId:
  vẫn có nguy cơ truy cập rất nhiều partition
~~~

Tùy loại index và phiên bản, hệ có thể hỗ trợ một số truy vấn index với chi phí và giới hạn khác nhau. Trước khi tạo:

- Kiểm tra **Cassandra version/distribution** có hỗ trợ SAI hoặc index type dự định không.
- Xác nhận **loại dữ liệu và predicate** được index hỗ trợ.
- Đo **selectivity**, số partition và fan-out.
- Ước lượng tác động của xây index trên dữ liệu SSTable hiện có, compaction và ghi mới.
- Kiểm tra trạng thái/khả năng truy vấn trong và sau xây theo cơ chế của engine.
- Thử nghiệm rollback/gỡ index với đúng version và topology.

Ví dụ tạo index chỉ nên được chọn theo **cú pháp đúng cho phiên bản đang chạy**. Không nên suy rằng một lệnh **CREATE INDEX** chung sẽ có kết quả, thời gian build và chi phí giống nhau giữa Cassandra 4.x, Cassandra 5.x, các bản phân phối hoặc dịch vụ quản lý.

Trong nhiều hệ Cassandra, một **bảng truy cập theo truy vấn** như **orders_by_tenant_status_day** có thể phù hợp hơn khi request cần một partition rõ và thứ tự theo thời gian. Nhưng bảng dẫn xuất cần pipeline ghi đồng bộ/đối soát, khác với secondary index do engine quản lý.

### Khi gỡ index Cassandra

Trước khi bỏ index, xác nhận không có query quan trọng chỉ chạy được nhờ nó hoặc đang sử dụng một fallback scan/filter có chi phí không chấp nhận được. **DROP INDEX** không tự chuyển query sang thiết kế table khác. Một số truy vấn có thể bị từ chối nếu thiếu access path phù hợp, thay vì chỉ “chậm hơn một chút”.

## 24. Redis: chỉ mục phụ do ứng dụng duy trì cần cutover riêng

Redis key–value không tự tạo một B-tree query index trên mọi thuộc tính của value. Một ứng dụng có thể lưu:

~~~redis
SET order:shop-a:order-1001 "{\"customerId\":\"customer-07\",\"status\":\"PAID\"}"

ZADD orders:shop-a:customer-07:by-time 1794646800 order-1001
~~~

Nếu cần đổi từ Sorted Set **by-time** sang một index theo **status + time**, hãy coi đây là migration của **dữ liệu dẫn xuất**:

~~~text
Nguồn order:
  order:shop-a:order-1001

Index cũ:
  orders:shop-a:customer-07:by-time

Index mới:
  orders:shop-a:customer-07:paid-by-time
~~~

Quy trình:

1. Định nghĩa key pattern và ngữ nghĩa status/time.
2. **Bắt đầu ghi delta** để không bỏ lỡ order tạo/đổi status trong lúc backfill.
3. Backfill index mới từ nguồn chính bằng batch, idempotent.
4. Dùng ID ổn định và version/event ID để xử lý retry/sai thứ tự.
5. So số lượng/ID và kết quả trang mẫu giữa index mới với nguồn.
6. Chuyển read path qua feature flag.
7. Quan sát cache misses, latency, bộ nhớ và dữ liệu lỗi thời.
8. Chỉ xóa Sorted Set cũ khi không còn client nào dùng nó.

Nếu hai key nằm ở các **hash slots khác nhau trong Redis Cluster**, thao tác nhiều key có những giới hạn nhất định. Không được giả định một lần cập nhật order value và cả hai sorted sets là nguyên tử trong mọi topology. Có thể dùng pipeline sự kiện hoặc thiết kế key theo slot/transaction phù hợp với yêu cầu.

**Xóa Redis index key** có thể cắt đứt khả năng liệt kê order theo một chiều, dù các order value vẫn còn. Vì vậy, việc xóa một Sorted Set cũng là thay đổi đường truy cập production, không chỉ giải phóng RAM.

Nếu dùng Redis Search/Redis Query Engine, lệnh quản trị index và các tùy chọn xóa dữ liệu nguồn có ngữ nghĩa riêng; phải kiểm tra kỹ trước khi drop, đặc biệt với tùy chọn có thể tác động tới document/key.

## 25. Search index: xây phiên bản mới rồi chuyển alias

Đối với Elasticsearch/OpenSearch hoặc search engine tương đương, việc thay mapping/index schema có thể cần **tạo index phiên bản mới** rồi **reindex** dữ liệu.

Một cách tổ chức:

~~~text
products_v1   <-- alias products_read

Chuẩn bị:
products_v2   (mapping/analyzers mới)

Backfill / catch-up:
source of truth -> products_v2

Cutover:
products_read  --> products_v2

Sau thời gian quan sát:
retire products_v1 theo chính sách
~~~

**Alias switch** có thể được thực hiện như một thay đổi atomic đối với alias theo API hỗ trợ của engine, giảm khả năng client nhìn thấy khoảng alias trỏ sai trong lúc chuyển. Nhưng alias đổi đích **không tự bảo đảm** mọi thay đổi nguồn phát sinh trong quá trình reindex đã được bắt và áp dụng vào index mới.

Các điểm cần giữ:

- **Nguồn dữ liệu có thẩm quyền** nằm ở đâu?
- Dữ liệu mới/đổi/xóa được ghi vào cả phiên bản nào trong giai đoạn chuyển?
- Reindex sử dụng snapshot ở thời điểm nào, có catch-up/CDC không?
- Delete event có version/tombstone để không làm “hồi sinh” document khi replay không?
- Mapping và analyzer mới có làm kết quả search/ranking thay đổi có chủ ý không?
- Read alias và write alias có vai trò riêng không?
- Sau cutover có thể đảo alias lại không, và bản v1 có còn nhận delta hay đã stale?

Đây là cùng một nguyên tắc **build → backfill → validate → cutover → observe → retire**, nhưng cơ chế khác hoàn toàn với một MongoDB B-tree index trên collection.

## 26. Rollout an toàn khi ứng dụng có nhiều phiên bản

Ứng dụng web, mobile, worker và các job định kỳ có thể được triển khai ở thời điểm khác nhau. Một số phiên bản dùng index cũ bằng **query shape** hoặc **IndexName** cố định.

Một lộ trình tương thích:

~~~text
Phase A: Server phiên bản cũ vẫn chạy
         Chưa bỏ index cũ

Phase B: Thêm index mới và đợi ready
         Server cũ + mới có thể cùng tồn tại

Phase C: Server mới đọc đường mới qua flag
         Đo request của từng phiên bản

Phase D: Ngừng/đổi mọi client phụ thuộc index cũ
         Quan sát một chu kỳ workload đủ đại diện

Phase E: Hide index cũ (nếu hỗ trợ), đo regression
         Có thể unhide nhanh

Phase F: Drop index cũ trong một deployment riêng
         Theo dõi, có runbook tạo lại
~~~

**Không nên để client mobile trực tiếp quyết định tên index database**. Thường nên đặt truy cập dữ liệu sau API server để đội vận hành có thể thay đường truy vấn mà không cần chờ mọi thiết bị cập nhật.

Nếu một API cũ còn phụ thuộc query shape cũ, có thể tiếp tục giữ index cũ trong một thời gian. **Chi phí giữ thêm index tạm thời thường thấp hơn rủi ro xóa đường truy cập trước khi client hết sử dụng**, nhưng vẫn phải tính dung lượng và write amplification.

## 27. “Thay index” đôi khi thực ra là thay data model

Giả sử API trước đây đọc:

~~~text
orders_by_customer
  PK = customerId
  SK = createdAt#orderId
~~~

Sau đó muốn đọc:

~~~text
orders_by_status
  PK = tenantId#status#day
  SK = createdAt#orderId
~~~

Trong DynamoDB hoặc Cassandra, đây có thể cần **GSI/bảng truy cập mới**, không chỉ sửa tên index. Khi bản đọc mới là một cấu trúc dữ liệu riêng, những thay đổi order phải được đồng bộ và đối soát.

Cần phân biệt:

| Tình huống | Bản chất thay đổi | Điểm rủi ro |
|---|---|---|
| MongoDB thêm compound index | Engine index cùng collection | Build cost, planner, disk |
| MongoDB đổi unique constraint | Bảo đảm ghi/bất biến | Duplicate data và race |
| MongoDB thêm TTL | Vòng đời và xóa dữ liệu | Dọn hàng loạt, retention |
| DynamoDB thêm GSI | Đường Query khác trên index | Backfill, capacity, eventual consistency |
| Cassandra thêm query-specific table | Bản dữ liệu phục vụ khóa khác | Dual write/CDC, drift, hot partition |
| Redis thêm Sorted Set | Index do app duy trì | Missed update, stale membership, memory |
| Search engine reindex + alias | Bản index phiên bản mới | Catch-up, ranking/mapping, cutover |

Mọi tình huống đều có giai đoạn **tạo mới trước, kiểm chứng, chuyển dùng, rồi mới bỏ cũ**, nhưng cách kiểm chứng phải phù hợp loại thay đổi.

## 28. Đo hiệu năng trước và sau thay đổi bằng cùng workload

Một báo cáo sau triển khai không nên chỉ ghi **“index created successfully”**. Nó cần chứng minh đường đọc được cải thiện và workload khác không bị hại đáng kể.

| Metric | Trước | Sau | Cách diễn giải |
|---|---:|---:|---|
| API PAID history p95 | 210 ms | 35 ms | Đường đích tốt hơn trong workload minh họa |
| API PAID history p99 | 850 ms | 90 ms | Tail latency giảm |
| Keys examined/request | 12.000 | 22 | Giảm truy cập index dư thừa |
| Docs examined/request | 400 | 20 | Giảm fetch không cần thiết |
| API all-status history p95 | 40 ms | 41 ms | Đường cũ chưa bị ảnh hưởng lớn |
| Write p95 | 15 ms | 19 ms | Có thêm chi phí duy trì index |
| Free disk | 180 GB | 162 GB | Index chiếm dung lượng |
| Replication lag p95 | 1 s | 2 s | Cần quan sát sau build |

**Các số trên hoàn toàn giả định để minh họa cách trình bày**, không phải benchmark MongoDB hoặc ngưỡng khuyến nghị.

Phải so sánh với **cùng kiểu query, tenant/data distribution, cỡ trang, giờ tải và số lượng request đủ lớn**. Một query trên cache nóng sau build có thể nhanh hơn chỉ vì cache, không phải vì index. Tương tự, load giảm cuối ngày có thể che giấu write amplification.

Điểm quan trọng là **lợi ích đọc phải được cân bằng với tác động ghi, dung lượng, replication và rủi ro vận hành**.

## 29. Bảng quyết định: có nên thêm, giữ hay gỡ chỉ mục?

| Câu hỏi | Nếu “có” | Quyết định ứng viên |
|---|---|---|
| Query quan trọng phải scan/sort rộng và SLO không đạt? | Có | Đánh giá index phù hợp |
| Index mới phục vụ filter/sort rõ ràng và dữ liệu đủ chọn lọc? | Có | Thử build/benchmark |
| Tạo index mới làm ghi/replica quá tải? | Có | Điều chỉnh lịch, thiết kế hoặc workload |
| Index cũ chỉ có số đếm truy cập 0 trong vài giờ? | Có | **Chưa đủ** lý do drop |
| Có client/job dùng hint(index cũ)? | Có | Gỡ phụ thuộc trước |
| Index cũ đang bảo vệ unique constraint? | Có | Không drop như index hiệu năng |
| Index cũ là TTL index? | Có | Đánh giá retention/deletion, không dựa vào hide |
| Chỉ mục mới ACTIVE và canary đạt? | Có | Chuyển traffic có kiểm soát |
| Hidden index cũ gây regression? | Có | Unhide và giữ/điều chỉnh |
| Đã qua đủ chu kỳ traffic và không còn dependency? | Có | Lập lịch drop riêng |
| Không có đủ khả năng rebuild/rollback nếu drop? | Có | Hoãn drop hoặc nâng khả năng phục hồi |

Không phải mọi index “không tối ưu” đều cần xóa ngay. Một index phục vụ thao tác cứu hộ rất hiếm có thể vẫn đáng giữ nếu dung lượng/chi phí ghi của nó hợp lý. Ngược lại, một index không còn dùng và liên tục tăng theo dữ liệu mới là chi phí vận hành cần được đánh giá lại.

## 30. Runbook triển khai chỉ mục trên production

Dưới đây là **mẫu runbook** có thể điều chỉnh theo engine và tổ chức, không phải lệnh tự động để chạy không cần phê duyệt.

### Giai đoạn A — Chuẩn bị

~~~text
Change ID:
  orders-index-customer-status-v2

Mục tiêu:
  Giảm độ trễ query lịch sử order PAID theo customer

Index mới:
  idx_customer_status_recent_v2

Index hiện có:
  idx_customer_recent_v1 (vẫn giữ)

Baseline:
  API p95/p99, keys/docs examined, write p95,
  replication lag, index size, free disk

Thử nghiệm:
  Dữ liệu đại diện, nhiều tenant, dữ liệu skew,
  hai query có/không status, canary

Rollback:
  Tắt flag query mới, giữ index V1;
  nếu đã hide V1 thì unhide;
  nếu đã drop phải rebuild theo runbook

Owner:
  Người phụ trách database + ứng dụng + on-call
~~~

### Giai đoạn B — Xây chỉ mục

Thực hiện trong cửa sổ tải phù hợp, bằng tài khoản và endpoint quản trị được cho phép. Theo dõi tài nguyên và xác nhận index đã build thành công. Nếu gặp lỗi duplicate/index option/resource, giữ nguyên đường cũ và xử lý nguyên nhân; không bỏ V1 để “dọn chỗ” mà không biết đường đọc còn hoạt động.

### Giai đoạn C — Kiểm chứng và chuyển đọc

Đo query plan/latency trên tập đại diện. Canary với flag, theo dõi p95/p99, lỗi và các đường đọc khác. Khi đủ bằng chứng, chuyển traffic dần, nhưng vẫn giữ đường cũ để rollback.

### Giai đoạn D — Thử retire index cũ

Kiểm kê các phụ thuộc sau một chu kỳ workload có cả job định kỳ. Nếu engine hỗ trợ hidden index, hide để thử, theo dõi regressions và unhide nếu cần. Không dùng bước này cho mục đích tắt uniqueness hoặc TTL.

### Giai đoạn E — Gỡ và theo dõi

Gỡ index cũ trong change riêng, theo dõi API, batch job, query planner, write throughput và free disk. Giữ tài liệu tạo lại index và dấu mốc thay đổi, vì hiệu ứng của drop có thể chỉ bộc lộ khi một job hiếm chạy trở lại.

## 31. Những hiểu nhầm dễ dẫn đến sự cố

| Nhầm lẫn | Hậu quả | Cách làm đúng |
|---|---|---|
| “Online build nên không ảnh hưởng traffic” | CPU/I/O/lock và p99 có thể tăng | Đo tải, đặt stop conditions |
| “CreateIndex trả success nên mọi query nhanh” | Planner có thể chọn index khác | Explain và benchmark query shape |
| “Index mới có nhiều field hơn thì index cũ dư” | Query thiếu field giữa có thể chậm | Kiểm kê equality/sort của mọi query |
| “Index không có access hôm nay thì xóa được” | Query tháng hoặc job sự cố bị ảnh hưởng | Quan sát đủ chu kỳ và kiểm kê dependency |
| “Hide giống drop” | Vẫn tốn disk/ghi; unique/TTL vẫn hoạt động | Hiểu hidden chỉ loại khỏi planner |
| “Ẩn unique index sẽ tắt ràng buộc” | Duplicate vẫn bị chặn | Thay constraint phải có kế hoạch riêng |
| “Ẩn TTL index sẽ ngừng xóa” | TTL vẫn có hiệu lực | Đổi chính sách TTL bằng cơ chế được hỗ trợ |
| “Dữ liệu không trùng ở sample nên unique build chắc chắn thành công” | Duplicate lịch sử hoặc race mới | Kiểm kê đủ phạm vi, kiểm soát writer |
| “GSI Query chạy ngay sau lệnh tạo” | Index có thể đang backfill/CREATING | Đợi ACTIVE và xác minh |
| “GSI có strong consistent reads” | Quyết định theo bản đọc trễ | Bảo vệ bất biến tại nguồn |
| “FilterExpression làm Query chỉ đọc 20 item” | Vẫn đọc/filter nhiều item, phân trang thiếu | Chọn key/GSI và đo ScannedCount |
| “Cassandra index giúp mọi query xuyên partition” | Fan-out lớn hoặc query không được hỗ trợ | Benchmark, xem table by-query |
| “Redis index key xóa không ảnh hưởng order values” | Dữ liệu vẫn còn nhưng API không liệt kê được | Cutover đường đọc trước khi xóa key |
| “Alias switch đã đảm bảo reindex không mất event” | Dữ liệu mới/xóa trong lúc reindex có thể lệch | Catch-up, version, đối soát |
| “Drop rồi rollback bằng một nút” | Rebuild có thể kéo dài; TTL delete không đảo ngược | Lộ trình hide → observe → drop |
| “Có index là có authorization” | Lộ dữ liệu tenant/owner | Xác thực và lọc quyền riêng |
| “Query Limit 20 thì đọc đúng 20” | Scan/read amplification có thể rất lớn | Đo số item/row thực đọc |
| “Index chỉ ảnh hưởng read” | Unique, TTL, write overhead thay đổi hành vi | Phân loại index theo chức năng |

## 32. Bài tập thực hành

### Bài tập 1 — Thêm compound index cho lịch sử đơn

Collection **orders** có V1 là **(tenantId, customerId, createdAt DESC, _id DESC)**. API mới lọc thêm **status=PAID**. Hãy đề xuất index V2, giải thích thứ tự field và liệt kê những query vẫn có thể cần V1.

### Bài tập 2 — Đo query trước/sau

Query trả 20 document nhưng trước khi thêm index phải xem **15.000 keys** và **700 docs**, sau index còn **25 keys** và **20 docs**. Hãy lập bảng baseline/sau rollout và nêu vì sao vẫn phải quan sát write p95, disk và replication lag.

### Bài tập 3 — Hidden index

Đội muốn xóa một index đã ít dùng. Hãy viết quy trình MongoDB **hide → explain/measure → unhide nếu regression → drop sau khi đủ bằng chứng**. Giải thích hidden index không giúp kiểm chứng lợi ích giảm write cost và không vô hiệu hóa unique/TTL.

### Bài tập 4 — Unique index trên dữ liệu lịch sử

Collection enrollments có 3 triệu document. Có những cặp **(tenantId, studentId, courseId)** trùng do import cũ. Hãy viết aggregation để tìm nhóm trùng, đề xuất cách quyết định record nguồn và xử lý race với writer live trước khi tạo unique index.

### Bài tập 5 — Unique partial theo trạng thái

Một học viên có thể đăng ký lại nhiều lần nhưng không được có hơn một enrollment **ACTIVE** cho cùng course. Hãy đề xuất partial unique index, giải thích điều xảy ra khi chuyển **PAUSED → ACTIVE** trong lúc một ACTIVE khác đã tồn tại.

### Bài tập 6 — TTL migration

Một collection sessions có 20 triệu document, nhiều session có **expiresAt** cũ hoặc sai timezone. Hãy lập preflight trước khi tạo TTL index, nêu rủi ro dọn dữ liệu hàng loạt và vì sao hideIndex không phải nút dừng TTL deletion.

### Bài tập 7 — Traffic spike trong lúc build

Trong khi MongoDB đang xây index, p99 checkout tăng gấp ba, disk free giảm nhanh và replication lag tăng. Hãy thiết kế stop conditions, người quyết định rollback, những số liệu cần thu và vì sao không nên tự kill database process.

### Bài tập 8 — DynamoDB GSI

Table có PK theo orderId, nhưng cần Query theo **tenantId + status + createdAt**. Hãy đề xuất GSI keys, projection, cách theo dõi build/backfill, trạng thái ACTIVE và rủi ro GSI eventual consistency với một workflow thanh toán.

### Bài tập 9 — DynamoDB drop GSI

Một ứng dụng cũ vẫn dùng **IndexName=OrdersByStatus** trong Query. Nếu xóa GSI trước khi deploy client mới thì điều gì xảy ra? Lập lộ trình chuyển API, canary, quan sát và xóa index đúng thứ tự.

### Bài tập 10 — Cassandra

Bảng có partition key **(tenantId, customerId)** và clustering **createdAt**. Trang mới cần mọi order PAID của tenant theo ngày. Hãy so sánh secondary index/SAI với bảng **orders_by_tenant_status_day**, giải thích vì sao không thể giả định một index đơn trên status luôn đủ.

### Bài tập 11 — Redis

Order value được lưu theo orderId, còn Sorted Set theo customer/time. Đội muốn thêm Sorted Set theo customer/status/time. Hãy thiết kế dual write/delta, backfill, idempotency, xử lý thứ tự event, chuyển query và xóa key chỉ mục cũ.

### Bài tập 12 — Search alias

Một search index sản phẩm cần đổi analyzer và mapping. Hãy xây **products_v2**, backfill, bắt thay đổi mới, so kết quả, chuyển alias và rollback. Vì sao alias switch không tự bắt tất cả sự kiện đến trong lúc reindex?

### Bài tập 13 — Đánh giá index không được dùng

**$indexStats** cho thấy một index có 0 accesses trong 3 ngày. Tuy nhiên, báo cáo tài chính dùng index này chỉ chạy ngày đầu tháng. Hãy giải thích kết luận nào được phép rút ra, kết luận nào chưa đủ bằng chứng, và cách tổ chức thời gian quan sát.

### Bài tập 14 — Mỗi lần thêm index đều có chi phí

Một collection nhận 15.000 inserts/s, đã có 12 index; nhóm muốn thêm 5 index mới. Hãy lập bảng chi phí cần đo: index entries, kích thước, I/O, write latency, cache pressure, build resource và read improvement. Nêu tiêu chí chọn giữ/gỡ index.

### Bài tập 15 — Phân biệt index và bất biến

Cho ba chỉ mục: compound read index, unique enrollment index và TTL sessions index. Hãy chỉ ra thay đổi nào **chủ yếu tác động query plan**, thay đổi nào **chặn ghi trùng**, thay đổi nào **có thể xóa dữ liệu**; từ đó đề xuất chính sách rollback phù hợp từng loại.

### Bài tập 16 — Viết runbook hoàn chỉnh

Một dịch vụ có 100 triệu orders cần đổi index v1 sang v2 trong khi vẫn nhận ghi liên tục. Hãy viết runbook gồm **query inventory, baseline, capacity preflight, index build, giám sát, canary, hidden index, rollback, phụ thuộc hint, unique/TTL audit, thời gian quan sát và tiêu chí drop**. Xác định người chịu trách nhiệm quyết định dừng và cách chứng minh không làm mất dữ liệu hoặc gián đoạn vượt SLO.

---

**Kết luận:** Triển khai và gỡ chỉ mục trong khi ứng dụng hoạt động là một **thay đổi đường truy cập có kiểm soát**, không phải hai lệnh **createIndex/dropIndex** độc lập. Trình tự an toàn thường là **hiểu workload → đo baseline → tạo chỉ mục mới khi vẫn giữ đường cũ → theo dõi build/backfill → kiểm chứng truy vấn và tác động ghi → chuyển traffic → thử ẩn index cũ nếu hỗ trợ → gỡ sau khi hết phụ thuộc và có kế hoạch rollback**. Với **unique index**, phải bảo vệ bất biến và giải quyết duplicate/race; với **TTL index**, phải kiểm soát chính sách xóa; với **GSI, read model và search alias**, phải quản lý trạng thái sẵn sàng, đồng bộ và độ mới. Mục tiêu không chỉ là truy vấn nhanh hơn mà là **giữ dịch vụ đúng, ổn định và có thể phục hồi trong suốt vòng đời thay đổi chỉ mục**.
