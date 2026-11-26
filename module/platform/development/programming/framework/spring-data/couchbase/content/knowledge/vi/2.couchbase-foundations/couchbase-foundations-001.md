# Cluster, node và các dịch vụ dữ liệu, truy vấn, chỉ mục trong Couchbase

> **Chương:** Nền tảng Couchbase  
> **Ngữ cảnh học tập:** Spring Data Couchbase — xây dựng tầng truy cập dữ liệu bằng document mapping, repository, CouchbaseTemplate và truy vấn SQL++.

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

- Phân biệt **cluster**, **node**, **service** với **bucket**, **scope** và **collection**; biết mỗi khái niệm giải quyết vấn đề nào.
- Giải thích đường đi của thao tác **key-value (KV)** so với truy vấn **SQL++** và vai trò riêng của Data, Query, Index Service.
- Đọc một cấu hình cluster có nhiều node, đánh giá cơ bản khả năng chịu lỗi, phân phối tải và nhu cầu chỉ mục.
- Thiết kế chỉ mục ban đầu cho một truy vấn, biết dùng `EXPLAIN` để kiểm chứng và hiểu tính nhất quán giữa ghi KV với đọc qua SQL++.
- Liên hệ các thao tác của **Spring Data Couchbase** với dịch vụ Couchbase phía sau để xử lý lỗi và tối ưu hiệu năng đúng chỗ.

## 2. Bức tranh tổng thể: cluster, node, service và dữ liệu

**Couchbase cluster** là một nhóm máy chủ Couchbase cùng quản lý tập dữ liệu và các dịch vụ xử lý. Một **node** là một máy chủ/instance tham gia cluster. Mỗi node có thể chạy một hoặc nhiều **service** (dịch vụ), chẳng hạn Data, Query và Index. Các node trao đổi thông tin để ứng dụng có thể truy cập cluster qua SDK.

Ở lớp tổ chức dữ liệu, ta thường gặp:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Cluster** | Nhóm node cùng vận hành và phân phối các dịch vụ | Cluster cho hệ thống bán hàng |
| **Node** | Một thành viên của cluster, có CPU/RAM/đĩa và dịch vụ được gán | `cb-1`, `cb-2`, `cb-3` |
| **Service** | Thành phần thực thi một chức năng: giữ tài liệu, xử lý SQL++, quản lý chỉ mục… | Data, Query, Index |
| **Bucket** | Không gian lưu trữ dữ liệu có cấu hình tài nguyên, replica và chính sách ở mức bucket | `shop` |
| **Scope** | Nhóm logic các collection trong một bucket | `sales` |
| **Collection** | Tập hợp các document cùng miền nghiệp vụ; mỗi document có khóa riêng | `orders`, `customers` |
| **Document** | Bản ghi JSON cùng **document ID** duy nhất trong collection | ID `order::1001` |

Ví dụ đường dẫn đầy đủ một collection là `shop.sales.orders`, tương ứng bucket `shop`, scope `sales`, collection `orders`. Một document trong collection này có thể có nội dung:

~~~json
{
  "type": "order",
  "tenantId": "tenant-42",
  "status": "PAID",
  "createdAt": "2026-11-25T02:00:00Z",
  "total": 1490000
}
~~~

**Lưu ý:** `order::1001` là *document ID* nằm ở metadata, không mặc nhiên là trường JSON trong document. Trong SQL++, có thể lấy ID bằng `META(o).id`.

Phân cấp bucket/scope/collection là cách **tổ chức dữ liệu**; cluster/node/service là cách **triển khai xử lý**. Một collection không thuộc cố định một node: các phần dữ liệu của bucket được phân phối giữa những Data node.

## 3. Ba dịch vụ cốt lõi

### 3.1. Data Service — lưu và truy cập document theo khóa

Data Service quản lý các document và thao tác KV như `get`, `insert`, `upsert`, `replace`, `remove`. Dữ liệu của bucket được chia thành các **vBucket** (phân vùng logic). Tại một thời điểm, mỗi vBucket có bản **active** ở một Data node; nếu bucket được cấu hình replica, còn có các bản sao vBucket trên node khác.

Điều này giúp Couchbase:

- Phân phối document theo khóa trên nhiều Data node, phục vụ nhiều thao tác KV song song.
- Phục hồi hoạt động khi một Data node hỏng nếu có replica phù hợp để chuyển vai trò.
- Chuyển phân vùng khi thêm, bớt hoặc cân bằng lại node.

SDK định tuyến yêu cầu KV đến node giữ phân vùng active tương ứng với khóa, thay vì gửi tất cả thao tác đến một máy chủ trung tâm. Data Service sử dụng bộ nhớ và lưu trữ bền vững để phục vụ dữ liệu; **không nên giả định mọi document đều phải nằm hoàn toàn trong RAM**.

Ví dụ: `repository.findById("order::1001")` hoặc `repository.save(order)` thường dựa vào đường KV. Nếu thao tác theo một ID đã biết, KV thường phù hợp hơn việc viết một truy vấn SQL++ chỉ để tìm đúng document đó.

### 3.2. Query Service — phân tích và thực thi SQL++

Query Service nhận câu lệnh **SQL++** (trước đây thường được nhắc tới với tên N1QL), phân tích cú pháp, lập kế hoạch thực thi, truy cập chỉ mục/dữ liệu khi cần và trả về các dòng kết quả. Nó giúp truy vấn theo trường JSON, lọc, sắp xếp, gom nhóm và nối dữ liệu mà không cần biết trước document ID.

Ví dụ: “Tìm 20 đơn đã thanh toán gần nhất của khách thuê `tenant-42`” phù hợp với SQL++, vì phải lọc theo `tenantId`, `status` và sắp xếp theo `createdAt`.

Query Service chủ yếu thực hiện vai trò **điều phối truy vấn**. Nó không thay thế Data Service làm nơi lưu document và không tự đảm bảo mọi điều kiện lọc đều có chỉ mục tốt. Một cluster có thể có nhiều Query node để chia tải và tăng khả năng sẵn sàng.

### 3.3. Index Service — tổ chức chỉ mục cho truy vấn

Index Service tạo, cập nhật và phục vụ **Global Secondary Index (GSI)** trên các collection. Nó nhận luồng thay đổi dữ liệu và xây dựng cấu trúc chỉ mục để Query Service có thể tìm các document phù hợp mà không phải quét toàn bộ dữ liệu.

Ba khái niệm cần phân biệt:

- **Primary index**: có thể phục vụ những truy vấn không có chỉ mục thứ cấp phù hợp, nhưng thường tốn tài nguyên nếu dùng như giải pháp mặc định cho tải lớn.
- **Secondary index**: đánh chỉ mục các trường và biểu thức cụ thể; nên thiết kế từ những truy vấn thực tế.
- **Covering index**: chứa đủ thông tin cần cho một truy vấn, giúp tránh bước `Fetch` lấy toàn bộ document từ Data Service trong kế hoạch thực thi tương ứng.

**Index Service phục vụ SQL++**, không phải điều kiện tiên quyết cho `get(documentId)` qua KV. Ngược lại, một truy vấn SQL++ thông thường có thể cần chỉ mục hợp lệ để lập kế hoạch; thiếu chỉ mục phù hợp có thể khiến truy vấn thất bại hoặc chọn kế hoạch rất tốn kém.

Một số phiên bản/triển khai Couchbase còn có Search, Analytics hoặc Eventing Service với nhiệm vụ riêng. **Full-text Search** không đồng nghĩa với Index Service dùng cho GSI của SQL++.

## 4. Hai đường đi của một yêu cầu từ Spring Data Couchbase

~~~mermaid
flowchart LR
    A["Ứng dụng<br/>Spring Data / Couchbase SDK"]
    D["Data Service<br/>Document và KV"]
    Q["Query Service<br/>SQL++ và kế hoạch"]
    I["Index Service<br/>GSI"]
    A -->|"get / upsert theo ID"| D
    D -->|"Kết quả KV"| A
    A -->|"Truy vấn SQL++"| Q
    Q -->|"Index scan"| I
    I -->|"Khóa / giá trị được lập chỉ mục"| Q
    Q -->|"Fetch document nếu cần"| D
    D -->|"Document"| Q
    Q -->|"Các dòng kết quả"| A
~~~

**Đường KV:** khi đã có document ID, SDK xác định vBucket và Data node phù hợp. Không cần đi qua Query hoặc Index Service.

**Đường SQL++:** Query Service nhận câu lệnh, dùng chỉ mục được chọn để tìm dữ liệu; tùy kế hoạch, nó có thể yêu cầu Data Service lấy document đầy đủ. Với covering index phù hợp, bước đọc document bổ sung có thể không cần thiết.

Hệ quả thực tế: độ trễ KV tăng có thể là vấn đề Data node, phân vùng, I/O hoặc mạng; còn SQL++ chậm cần kiểm tra thêm Query node, **kế hoạch thực thi** và sức khỏe của Index Service. Không nên kết luận “Couchbase chậm” chỉ từ một phép đo chung.

## 5. Phân phối service lên node và khả năng chịu lỗi

Couchbase cho phép đặt nhiều service chung trên node (**multi-dimensional scaling**), hoặc dùng các node chuyên trách khi khối lượng công việc lớn. Ví dụ một cluster ba node:

| Node | Service minh họa | Vai trò |
|---|---|---|
| `cb-1` | Data, Query | Giữ một phần dữ liệu; tiếp nhận SQL++ |
| `cb-2` | Data, Index | Giữ một phần dữ liệu; xây dựng/phục vụ GSI |
| `cb-3` | Data, Query, Index | Giữ dữ liệu; bổ sung năng lực Query và Index |

Đây chỉ là **mô hình để phân tích**, không phải cấu hình production áp dụng cho mọi tải. Dung lượng tài nguyên và số node còn phụ thuộc dữ liệu, số truy vấn, SLA, replica, khả năng mất một node và dịch vụ khác đang chạy.

Các tình huống cần phân biệt:

| Tình huống | Tác động có thể xảy ra | Cách thiết kế/ứng phó |
|---|---|---|
| Một **Data node** lỗi | Các vBucket active của node đó không còn phục vụ trên node cũ | Cấu hình replica dữ liệu và quy trình failover/phục hồi phù hợp |
| Một **Query node** lỗi | Yêu cầu SQL++ đến node đó bị gián đoạn | Có Query node khác để SDK/ứng dụng chuyển hướng và retry có kiểm soát |
| Một **Index node** lỗi | Chỉ mục chỉ nằm trên node đó có thể không khả dụng; SQL++ chịu ảnh hưởng | Bố trí index replica hoặc cơ chế phục hồi phù hợp và kiểm tra khả năng tiếp quản |
| Tăng/giảm Data node | Phân vùng có thể cần di chuyển; I/O, CPU, mạng tăng trong quá trình chuyển | Lập kế hoạch **rebalance**, theo dõi tải và đủ dung lượng trống |
| Bùng nổ truy vấn có `ORDER BY`/`JOIN` | Query/Index tiêu tốn CPU, RAM và có thể phát sinh fetch/sort nhiều | Tối ưu câu lệnh, GSI, covering, phân phối service và giới hạn tải |

**Replica dữ liệu** và **replica chỉ mục** là hai cấu hình khác nhau: bản sao document không tự động thay thế bản sao GSI. Tương tự, **rebalance** là phân phối lại dữ liệu/khối lượng công việc theo thành viên cluster; **failover** là chuyển xử lý khi node không thể tiếp tục phục vụ. Hai thao tác có mục đích và rủi ro vận hành khác nhau.

Replica và failover cũng **không thay thế backup**: xóa nhầm, ghi sai dữ liệu hoặc lỗi logic có thể lan sang bản sao. Khi cần bảo vệ dữ liệu dài hạn phải có quy trình backup/restore và kiểm tra khôi phục độc lập.

## 6. Ví dụ SQL++ và thiết kế chỉ mục theo truy vấn

Giả sử mỗi document trong `shop.sales.orders` có `type = "order"`. Câu hỏi nghiệp vụ: lấy 20 đơn `PAID` mới nhất của một tenant.

~~~sql
SELECT
    META(o).id AS id,
    o.status,
    o.createdAt,
    o.total
FROM `shop`.`sales`.`orders` AS o
WHERE o.type = "order"
  AND o.tenantId = $tenantId
  AND o.status = $status
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Ứng dụng truyền tham số `tenantId = "tenant-42"`, `status = "PAID"`. Tham số giúp tách dữ liệu đầu vào khỏi câu lệnh, tránh tự ghép chuỗi SQL++.

Một chỉ mục khởi đầu để xem xét:

~~~sql
CREATE INDEX ix_orders_tenant_status_created
ON `shop`.`sales`.`orders`(tenantId, status, createdAt)
WHERE type = "order";
~~~

Cách đọc thiết kế:

1. `tenantId` và `status` xuất hiện trong điều kiện bằng (`=`), giúp thu hẹp tập ứng viên.
2. `createdAt` hỗ trợ truy cập theo thời gian và có thể giúp giảm chi phí sắp xếp tùy kế hoạch.
3. `WHERE type = "order"` tạo **partial index**: chỉ lập chỉ mục document thỏa điều kiện đó. Query muốn dùng index này phải chứng minh được điều kiện tương ứng.
4. Kế hoạch vẫn có thể cần `Fetch` để đọc `total` vì trường này chưa có trong khóa chỉ mục.

Nếu đây là truy vấn được gọi rất nhiều, có thể đánh giá một index bao phủ hơn:

~~~sql
CREATE INDEX ix_orders_tenant_status_created_total
ON `shop`.`sales`.`orders`(tenantId, status, createdAt, total)
WHERE type = "order";
~~~

Không nên mặc định tạo cả hai chỉ mục. Chỉ mục rộng hơn tốn không gian lưu trữ và chi phí cập nhật khi document thay đổi. Quyết định dựa trên số lần đọc/ghi, thống kê và kế hoạch thực thi thực tế.

Dùng `EXPLAIN` để kiểm chứng kế hoạch:

~~~sql
EXPLAIN
SELECT META(o).id AS id, o.status, o.createdAt, o.total
FROM `shop`.`sales`.`orders` AS o
WHERE o.type = "order"
  AND o.tenantId = "tenant-42"
  AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Trong kết quả, tìm tên index được chọn, các toán tử scan, `Fetch`, `Order` và số lượng/cách phân phối xử lý nếu có. `EXPLAIN` là **kế hoạch**, còn số liệu độ trễ và tài nguyên dưới tải thật mới xác nhận hiệu quả. Một truy vấn chạy nhanh trên 100 document chưa chứng minh sẽ chạy tốt trên hàng triệu document.

**Lỗi thiết kế phổ biến:** tạo primary index để mọi truy vấn “chạy được”, sau đó bỏ qua chi phí quét; tạo quá nhiều secondary index khiến tốc độ ghi giảm; hay dùng partial index `WHERE type = "order"` trong khi truy vấn sinh ra không có điều kiện `type` nên optimizer không thể sử dụng.

## 7. Kết nối với Spring Data Couchbase

Spring Data Couchbase cung cấp document mapping, `CouchbaseRepository` và `CouchbaseTemplate` để truy cập Couchbase từ ứng dụng Java. Phần trừu tượng ở Java không xóa bỏ các ranh giới giữa service.

Ví dụ mapping một document vào collection `sales.orders`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("orders")
public class OrderDocument {
    @Id
    private String id;

    @Field
    private String tenantId;

    @Field
    private String status;

    @Field
    private String createdAt;

    @Field
    private Long total;

    // Constructor và getter/setter được lược bớt để tập trung vào mapping.
}
~~~

Repository ví dụ:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByTenantIdAndStatus(
            String tenantId, String status);
}
~~~

Liên hệ với kiến trúc:

| Thao tác ứng dụng | Đường thực thi thường gặp | Điểm cần lưu ý |
|---|---|---|
| `findById(id)` | KV → Data Service | ID và collection đúng; tối ưu cho truy cập một document |
| `save(document)` / `deleteById(id)` | KV → Data Service | CAS/độ bền ghi, xung đột cập nhật và TTL khi cần |
| `findByTenantIdAndStatus(...)` | SQL++ → Query, Index và có thể Data | Phải có GSI khớp điều kiện truy vấn được **Spring Data sinh thực tế** |
| `CouchbaseTemplate` với truy vấn tùy chỉnh | Phụ thuộc API được gọi | Thao tác theo ID có thể là KV; truy vấn theo field thường dùng SQL++ |

**Chi tiết quan trọng:** Spring Data Couchbase có thể thêm điều kiện phân biệt loại entity, thường dựa trên trường như `_class`. Vì vậy index ví dụ dựa trên `type = "order"` ở phần trước **không chắc phù hợp** với truy vấn repository tự sinh. Hãy xem SQL++ thực sự được thực thi, xác định các điều kiện trên `_class`/`type` rồi tạo index tương ứng; sau đó kiểm tra bằng `EXPLAIN`. Tên trường, mapping và cú pháp cấu hình cần đối chiếu phiên bản Spring Data Couchbase của dự án.

Trong ứng dụng Spring Boot, kết nối thường được thiết lập qua cấu hình kết nối cluster, thông tin xác thực và bucket; SDK sẽ khám phá các node/service từ cluster. Nếu dùng Couchbase Capella hoặc TLS, dùng endpoint và cơ chế kết nối được môi trường triển khai cung cấp. Không nhúng mật khẩu thật trong mã nguồn.

## 8. Nhất quán: vì sao vừa ghi xong có thể chưa thấy qua SQL++?

Đây là điểm dễ gây hiểu nhầm khi chuyển từ cơ sở dữ liệu quan hệ sang Couchbase.

- Sau khi một thao tác ghi KV được xác nhận, dữ liệu đã được xử lý theo mức durability được chọn. Truy cập KV theo đúng document ID có đường đọc trực tiếp qua Data Service.
- GSI được cập nhật từ luồng thay đổi của dữ liệu và có thể **trễ một khoảng thời gian** so với ghi KV. Vì vậy truy vấn SQL++ ở chế độ mặc định có thể chưa trả về document vừa ghi.
- Query Service hỗ trợ các mức **scan consistency**. `not_bounded` ưu tiên độ trễ; `request_plus` đợi chỉ mục bắt kịp các thay đổi có trước lúc yêu cầu truy vấn được bắt đầu, thường đổi lấy thêm thời gian chờ. `at_plus`/mutation-state là lựa chọn có mục tiêu hơn trong các API hỗ trợ.

Ví dụ với Couchbase Java SDK để minh họa tùy chọn truy vấn:

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;

cluster.query(
    "SELECT META(o).id AS id FROM `shop`.`sales`.`orders` AS o " +
    "WHERE o.tenantId = $tenantId",
    queryOptions()
        .parameters(
            com.couchbase.client.java.json.JsonObject.create()
                .put("tenantId", "tenant-42"))
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS));
~~~

Đây là ví dụ **SDK** để làm rõ thuộc tính nhất quán; khi dùng Spring Data, cần chọn API/cấu hình tương ứng với phiên bản đang triển khai. `request_plus` không tự biến toàn bộ một chuỗi thao tác thành transaction, cũng không thay thế khóa phiên bản CAS.

Ngoài ra, cần phân biệt:

- **CAS (Compare-And-Swap)**: token phiên bản giúp phát hiện/kiểm soát cập nhật cạnh tranh trên document.
- **TTL/expiry**: quy định tuổi thọ document; document hết hạn ảnh hưởng Data và rồi đến chỉ mục/truy vấn.
- **Durability**: mức đảm bảo ghi được xác nhận tại các bản sao/đĩa theo chính sách.
- **Transaction**: cơ chế cho thao tác nhiều document cần tính nguyên tử; có yêu cầu và chi phí riêng.

Các chủ đề này liên quan đến thiết kế tầng truy cập dữ liệu nhưng không phải chức năng thay thế của Query hay Index Service.

## 9. Vận hành và theo dõi theo từng dịch vụ

Khi tối ưu hệ thống, hãy gắn triệu chứng với đúng lớp:

| Dấu hiệu | Nơi kiểm tra đầu tiên | Câu hỏi chẩn đoán |
|---|---|---|
| `get`/`upsert` chậm | Data node, mạng, dung lượng/I/O, hàng đợi KV | Chậm ở một khóa/vBucket hay toàn cluster? Có rebalance/failover không? |
| Truy vấn SQL++ chậm | Query Service, `EXPLAIN`, Index Service | Có scan quá rộng, `Fetch` nhiều, sort nặng, thiếu index hay không? |
| Vừa ghi xong nhưng truy vấn chưa thấy | Scan consistency, tiến độ cập nhật GSI | Query đang dùng `not_bounded` hay cần `request_plus`? |
| Tốc độ ghi giảm sau khi thêm chỉ mục | Index Service và tài nguyên Data | Có quá nhiều index, index quá rộng hoặc tồn đọng cập nhật không? |
| Lỗi truy vấn sau mất node | Query/Index availability, routing, replica | Có Query node thay thế và bản sao index đang hoạt động không? |

Các chỉ số có ích gồm: độ trễ thao tác KV; CPU/RAM/đĩa của từng loại node; kích thước dữ liệu và replica; số truy vấn, timeout và truy vấn chậm; thời gian thực thi từng toán tử; tình trạng/độ trễ cập nhật GSI; tiến độ rebalance. Không tăng tài nguyên ngẫu nhiên trước khi xác định service đang nghẽn.

**Quy tắc cấu hình cơ bản:**

1. Phân tách quyền truy cập theo vai trò (RBAC): tài khoản ứng dụng chỉ nên có quyền đọc/ghi hoặc truy vấn cần thiết; việc tạo index dùng quyền quản trị thích hợp.
2. Cấu hình replica dữ liệu, index availability và số Query node theo mục tiêu chịu lỗi cụ thể; kiểm tra kịch bản một node không khả dụng.
3. Theo dõi tài nguyên trong lúc rebalance, tạo index và chạy tải đồng thời; đây đều có thể là công việc nặng.
4. Ưu tiên KV cho truy cập bằng ID; sử dụng SQL++ và GSI khi tìm theo thuộc tính; tạo chỉ mục từ truy vấn thật.
5. Dùng TLS/endpoint thích hợp, giám sát, backup và diễn tập khôi phục như một phần của thiết kế vận hành.

## 10. Bài tập tình huống

**Tình huống A — chọn đường truy cập.** API `GET /orders/order::1001` có ID cụ thể, chỉ cần nội dung document. Bạn chọn `findById` hay SQL++ `WHERE META().id = ...`? **Gợi ý:** `findById` đi qua KV, tránh thêm chi phí lập kế hoạch Query/Index không cần thiết.

**Tình huống B — một API danh sách chậm.** API lọc `tenantId`, `status` và sắp xếp `createdAt`. Dùng `EXPLAIN` kiểm tra index được chọn và các toán tử `Fetch`/`Order`. Đề xuất index phù hợp, kiểm tra query thực tế của Spring Data có thêm `_class` hay không, rồi đo trên dữ liệu đủ lớn.

**Tình huống C — đọc sau ghi.** Ứng dụng `save(order)` thành công nhưng ngay sau đó `findByTenantIdAndStatus(...)` chưa thấy đơn. Nêu lý do tại sao đây có thể là vấn đề độ trễ cập nhật GSI; cân nhắc `request_plus`/mutation-state cho luồng cần đọc ngay, hoặc đọc KV theo ID nếu đã biết ID.

**Tình huống D — mất một node.** Cluster có ba Data node nhưng chỉ một Index node. Khi Index node lỗi, KV có thể vẫn hoạt động, trong khi SQL++ gặp lỗi vì không còn bản index khả dụng. Hãy giải thích vì sao chỉ tăng replica bucket không sửa được sự cố Index Service và đề xuất phương án tăng khả dụng chỉ mục.

## 11. Tự kiểm tra kiến thức

1. **Node khác bucket thế nào?** Node là thành viên hạ tầng chạy service; bucket là không gian dữ liệu được phân phối trên Data node.
2. **Query Service có lưu toàn bộ document không?** Không; Data Service quản lý dữ liệu, Query Service điều phối truy vấn và có thể đọc document từ Data.
3. **Mọi thao tác đọc có cần GSI không?** Không; `get` theo ID dùng KV. SQL++ theo thuộc tính thường cần GSI phù hợp.
4. **Vì sao thêm Index node không nhất thiết làm `get(id)` nhanh hơn?** `get(id)` không dùng Index Service.
5. **Vì sao SQL++ có thể chưa thấy document vừa ghi?** GSI có thể chưa cập nhật xong; cần hiểu scan consistency của truy vấn.
6. **Replica vBucket có thay thế index replica và backup không?** Không; đó là ba cơ chế phục vụ mục đích khác nhau.

Khi nắm được sự khác biệt giữa **Data để lưu/KV**, **Query để thực thi SQL++** và **Index để thu hẹp phạm vi truy vấn**, bạn sẽ biết nên điều chỉnh repository, câu lệnh, chỉ mục hay topology cluster khi xây dựng tầng truy cập Couchbase bằng Spring Data.
