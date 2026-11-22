# Mục đích phân mảnh và vai trò của mongos

## 1. Vấn đề mà sharding giải quyết

Trong một hệ thống sử dụng **Spring Data MongoDB**, ứng dụng có thể lưu document bằng **MongoTemplate** hoặc **MongoRepository**. Khi dữ liệu và lưu lượng tăng, một MongoDB replica set có thể gặp giới hạn về dung lượng đĩa, bộ nhớ, CPU hoặc thông lượng đọc/ghi. Tăng cấu hình máy chủ (vertical scaling) chỉ giải quyết được đến một ngưỡng và có thể tốn kém.

**Sharding (phân mảnh)** là cách MongoDB phân phối document của một collection trên **nhiều shard**, để các máy cùng gánh dung lượng lưu trữ và một phần công việc xử lý truy vấn. Đây là cơ chế **mở rộng ngang (horizontal scaling)**. Ứng dụng vẫn thao tác với tên database, collection và các API MongoDB thông thường; lớp định tuyến của cụm sẽ xác định shard nào cần nhận yêu cầu.

Ví dụ: collection **orders** có hàng trăm triệu đơn hàng của nhiều khách thuê (tenant). Nếu phân mảnh theo **tenantId**, dữ liệu được chia giữa nhiều shard thay vì dồn vào một máy. Một truy vấn chứa tenantId cụ thể có thể được chuyển đến đúng shard lưu tenant đó, trong khi một báo cáo thống kê toàn hệ thống có thể phải đọc dữ liệu trên nhiều shard.

Sau bài học, bạn có thể:

- Giải thích khi nào cần phân mảnh và phân biệt sharding với replication.
- Nhận diện các thành phần **shard**, **config server replica set** và **mongos** trong một sharded cluster.
- Mô tả cách **mongos** định tuyến thao tác dựa vào **shard key**, và vì sao một truy vấn có thể phải chạy trên nhiều shard.
- Kết nối Spring Data MongoDB qua mongos, kiểm tra phạm vi truy vấn và nhận ra các chi phí vận hành của sharding.

## 2. Sharding khác replication như thế nào?

Hai cơ chế bổ sung cho nhau nhưng giải quyết các nhu cầu khác nhau.

| Tiêu chí | Replication (replica set) | Sharding (sharded cluster) |
| --- | --- | --- |
| Cách tổ chức dữ liệu | Các thành viên replica set giữ bản sao của cùng tập dữ liệu. | Mỗi shard giữ một phần dữ liệu của collection đã được phân mảnh. |
| Mục đích nổi bật | Tăng tính sẵn sàng, phục hồi khi một node gặp sự cố; có thể phục vụ một số nhu cầu đọc. | Phân bố dung lượng và tải công việc trên nhiều shard. |
| Khả năng mở rộng ghi | Phần lớn ghi vẫn đi qua primary của một replica set. | Ghi có thể được phân tán giữa các shard nếu shard key và tải phù hợp. |
| Quan hệ giữa hai cơ chế | Có thể dùng riêng cho dữ liệu chưa cần phân mảnh. | Trong triển khai sản xuất, mỗi shard thường là một replica set để có khả năng chịu lỗi. |

**Điểm cần nhớ:** có ba replica trong một replica set không có nghĩa dung lượng lưu trữ khả dụng tăng gấp ba. Tương tự, thêm shard không tự động làm mọi truy vấn nhanh hơn: cách chọn shard key và mẫu truy cập mới quyết định lợi ích thực tế.

### Khi nào nên cân nhắc sharding?

- Kích thước dữ liệu hoặc tốc độ tăng trưởng vượt khả năng của một replica set.
- Tải ghi/đọc có thể phân phối theo một khóa rõ ràng (ví dụ khách hàng, tenant hoặc vùng dữ liệu).
- Một máy đã trở thành nút thắt sau khi tối ưu index, truy vấn, cấu hình và tài nguyên.
- Hệ thống có khả năng vận hành thêm nhiều thành phần phân tán và theo dõi sự cân bằng dữ liệu.

Nếu collection còn nhỏ, truy vấn chủ yếu chạy tốt trên một replica set hoặc phần lớn yêu cầu luôn tập trung vào cùng một nhóm document, sharding có thể làm tăng độ phức tạp mà đem lại ít lợi ích.

## 3. Thành phần của một sharded cluster

~~~mermaid
flowchart TB
    App["Ứng dụng Spring Data MongoDB<br/>MongoTemplate / Repository"]
    Driver["MongoDB Java Driver"]
    Router["mongos<br/>Query router"]
    Meta[("Config Server Replica Set<br/>Metadata phân mảnh")]
    A[("Shard A<br/>thường là replica set")]
    B[("Shard B<br/>thường là replica set")]
    C[("Shard C<br/>thường là replica set")]
    App --> Driver
    Driver --> Router
    Router <-.->|"Lấy và làm mới metadata"| Meta
    Router -->|"Đọc/ghi được định tuyến"| A
    Router -->|"Đọc/ghi được định tuyến"| B
    Router -->|"Đọc/ghi được định tuyến"| C
~~~

| Thành phần | Trách nhiệm | Điều không nên nhầm lẫn |
| --- | --- | --- |
| **Shard** | Lưu và xử lý một phần dữ liệu; thường triển khai dưới dạng replica set. | Shard không đồng nghĩa với một process mongos. |
| **Config server replica set (CSRS)** | Duy trì metadata của cụm, bao gồm cách các vùng giá trị shard key được ánh xạ tới shard. | Config server không phải nơi ứng dụng gửi mọi yêu cầu đọc document. |
| **mongos** | Nhận thao tác từ client, dùng metadata để xác định các shard liên quan, gửi yêu cầu và hợp nhất kết quả khi cần. | mongos là **router**, không phải kho lưu trữ document của ứng dụng. |
| **Balancer** | Điều phối việc di chuyển các vùng dữ liệu giữa shard để xử lý sự mất cân bằng theo chính sách của cụm. | Quá trình cân bằng dữ liệu là hoạt động quản trị nền, không phải trách nhiệm xử lý từng truy vấn của mongos. |

Cụm có thể triển khai **nhiều mongos** để ứng dụng có lựa chọn kết nối khi một router không khả dụng. Tuy mongos có thể được xem là thành phần định tuyến tương đối ít trạng thái bền vững, nó vẫn duy trì cache metadata và kết nối; không nên hiểu là nó hoàn toàn không có trạng thái trong bộ nhớ.

Trong MongoDB, **primary shard của database** (nơi đặt collection chưa phân mảnh và một số metadata liên quan) là khái niệm khác với **primary member của replica set** (node chấp nhận ghi). Hai từ “primary” này không thể thay thế cho nhau.

## 4. Shard key: cơ sở để phân phối và định tuyến

Khi một collection được sharding, MongoDB dùng **shard key** gồm một hoặc nhiều trường của document để xác định vùng dữ liệu thuộc về từng shard. Các vùng giá trị shard key được tổ chức thành những đơn vị phân phối dữ liệu; vị trí lưu trữ có thể thay đổi khi cụm cân bằng lại.

Có hai hướng lựa chọn thường gặp:

1. **Range-based sharding:** phân phối theo các khoảng giá trị khóa; hữu ích cho một số truy vấn theo phạm vi nhưng khóa tăng đều theo thời gian có thể làm tải ghi tập trung.
2. **Hashed sharding:** dùng giá trị băm của trường khóa để phân phối; có thể trải đều các giá trị khóa khác nhau, nhưng không thuận lợi cho truy vấn phạm vi trên trường được băm.

Ví dụ, một document đơn hàng:

~~~json
{
  "_id": "ord-9001",
  "tenantId": "tenant-204",
  "status": "PAID",
  "total": 240000,
  "createdAt": "2026-10-18T09:00:00Z"
}
~~~

Nếu sharding collection **commerce.orders** theo khóa **{ tenantId: "hashed" }**, các tenant có thể được phân phối giữa nhiều shard. Những truy vấn có điều kiện bằng trên tenantId thường cho phép mongos xác định chính xác shard cần truy cập:

~~~javascript
db.orders.find({ tenantId: "tenant-204", status: "PAID" })
~~~

Ngược lại, truy vấn sau không cung cấp shard key:

~~~javascript
db.orders.find({ status: "PAID" })
~~~

Với cấu hình ví dụ này, mongos thường phải gửi truy vấn tới nhiều shard và hợp nhất kết quả. Đó là **scatter-gather**. Mỗi shard có thể dùng index cục bộ, nhưng vẫn phát sinh tải xử lý và truyền dữ liệu ở quy mô toàn cụm.

**Lựa chọn shard key là một quyết định kiến trúc quan trọng**, vì nó ảnh hưởng đến phân phối dữ liệu, tốc độ ghi và khả năng định tuyến:

- **Cardinality:** nên có đủ nhiều giá trị khóa để dữ liệu có cơ hội phân bố.
- **Frequency distribution:** tránh một giá trị xuất hiện với tỷ lệ quá lớn gây tập trung tải.
- **Truy vấn phổ biến:** các truy vấn quan trọng nên có khả năng lọc bằng shard key; không chỉ chọn theo cấu trúc dữ liệu.
- **Tăng trưởng theo thời gian:** tránh tạo điểm nóng khi phần lớn bản ghi mới rơi vào một vùng khóa.
- **Nhu cầu cập nhật và ràng buộc dữ liệu:** xem xét trước các thao tác update, unique index và transaction, vì sharding đặt ra thêm điều kiện.

Với tenantId dạng hashed, các tenant khác nhau có thể được trải đều; tuy vậy, **một tenant cực lớn hoặc rất nhiều thao tác chỉ trên một tenant** vẫn có thể gây điểm nóng. Khi đó nên đánh giá khóa ghép hoặc chiến lược chia dữ liệu khác, dựa trên truy vấn thực tế. Không có một shard key tối ưu cho mọi ứng dụng.

## 5. mongos làm gì khi ứng dụng gửi yêu cầu?

Xét một thao tác đọc do **MongoTemplate** hoặc **MongoRepository** gửi qua MongoDB Java Driver:

1. **Client kết nối tới mongos.** Driver gửi thao tác MongoDB tới một router mongos phù hợp trong cấu hình kết nối.
2. **mongos xác định phạm vi dữ liệu.** Router dùng metadata phân mảnh đang cache để phân tích shard key trong filter và xác định các shard có thể chứa dữ liệu.
3. **mongos chuyển tiếp thao tác.** Với truy vấn có thể nhắm đích, yêu cầu đến một shard hoặc tập shard nhỏ; với truy vấn không đủ điều kiện định tuyến, yêu cầu có thể đến nhiều shard.
4. **Các shard thực thi.** Mỗi shard áp dụng truy vấn, index và kế hoạch thực thi trên phần dữ liệu nó quản lý.
5. **mongos tổng hợp phản hồi.** Router có thể hợp nhất kết quả, phối hợp phân trang/sắp xếp hoặc các giai đoạn aggregation theo kế hoạch truy vấn, rồi trả kết quả về driver.

Nếu vị trí dữ liệu đã thay đổi (ví dụ sau khi di chuyển vùng dữ liệu), mongos có thể phải **làm mới metadata và thử lại định tuyến** theo cơ chế của MongoDB. Ứng dụng không nên tự duy trì bản đồ “tenant nào ở shard nào”: chi tiết đó thuộc cụm dữ liệu.

### Targeted query và scatter-gather

| Trường hợp (khóa { tenantId: "hashed" }) | Phạm vi có thể phải truy cập | Hàm ý |
| --- | --- | --- |
| Tìm theo tenantId bằng một giá trị | Thường một shard dữ liệu | Giảm số shard tham gia và lưu lượng mạng. |
| Tìm theo tenantId và status | Thường một shard dữ liệu | Sau khi định tuyến, index trên shard vẫn quyết định tốc độ lọc. |
| Chỉ tìm theo status | Có thể tất cả các shard | Có nguy cơ scatter-gather, nhất là khi dữ liệu và số shard tăng. |
| Thống kê tổng doanh số toàn cụm | Có thể nhiều hoặc tất cả shard | Cần phân tích aggregation, chi phí hợp nhất và khối lượng dữ liệu. |

Định tuyến tốt không đồng nghĩa truy vấn đã tối ưu: một targeted query vẫn chậm nếu quét quá nhiều document ở shard đích. Ngược lại, scatter-gather không luôn là lỗi; nó có thể phù hợp với truy vấn phân tích hiếm, nhưng cần được nhận diện và đo lường.

### Vai trò của mongos trong aggregation

Với một pipeline aggregation, MongoDB có thể thực thi các giai đoạn đủ điều kiện trên từng shard rồi thực hiện phần **merge** ở thành phần thích hợp theo phiên bản và kế hoạch thực thi. Điều kiện **$match** có shard key ở đầu pipeline thường tạo cơ hội giảm shard tham gia hoặc giảm dữ liệu cần truyền. Các bước **$group**, **$sort**, **$lookup** trên tập dữ liệu lớn có thể tăng chi phí phân tán.

Spring Data MongoDB xây dựng pipeline giúp lập trình viên, nhưng **không tự biến một pipeline không có shard key thành truy vấn nhắm đích**. Luôn kiểm tra kế hoạch thực thi và lượng dữ liệu thực tế.

## 6. Thiết lập minh họa trên MongoDB

Ví dụ dưới đây giả định bạn đã có một **sharded cluster** hoạt động, có quyền quản trị phù hợp và đã kết nối **mongosh tới mongos**. Chạy trên môi trường thử nghiệm trước khi áp dụng vào hệ thống có dữ liệu thật.

~~~javascript
// Chọn database nghiệp vụ.
use commerce

// Index hashed dùng cho shard key (đặc biệt cần xét trước khi
// phân mảnh một collection đang chứa dữ liệu).
db.orders.createIndex({ tenantId: "hashed" })

// Phân mảnh collection theo giá trị băm của tenantId.
sh.shardCollection("commerce.orders", { tenantId: "hashed" })

// Index phục vụ mẫu truy vấn nghiệp vụ trong từng shard.
db.orders.createIndex({ tenantId: 1, status: 1, createdAt: -1 })
~~~

Giải thích:

- Lệnh **sh.shardCollection** khai báo shard key của collection. Quy trình chuẩn bị index và các điều kiện cho phép sharding còn phụ thuộc dữ liệu có sẵn và phiên bản MongoDB.
- **Index của shard key** giúp MongoDB quản lý cấu trúc phân mảnh. **Index truy vấn nghiệp vụ** giúp mỗi shard tìm document nhanh sau khi mongos đã định tuyến.
- Sharding không đồng nghĩa mọi document được phân bố đều ngay tại thời điểm chạy lệnh. Việc phân phối thực tế phụ thuộc lượng dữ liệu, shard key và quá trình cân bằng.
- Sau khi collection đã được sharding, thay đổi chiến lược shard key cần quy trình có chủ đích, phụ thuộc các khả năng và giới hạn của phiên bản đang chạy.

Có thể kiểm tra từ một phiên **mongosh kết nối tới mongos**:

~~~javascript
sh.status()

use commerce

db.orders.find({ tenantId: "tenant-204", status: "PAID" })
  .explain("executionStats")

db.orders.find({ status: "PAID" })
  .explain("executionStats")
~~~

So sánh các shard tham gia, số document được kiểm tra, số document trả về và thời gian thực thi. Cấu trúc trường trong kết quả **explain** thay đổi theo phiên bản MongoDB và loại truy vấn; hãy đọc kế hoạch thực tế thay vì dựa vào một tên stage cố định.

## 7. Kết nối từ Spring Data MongoDB

Trong ứng dụng Spring Data MongoDB, **mongos nằm giữa MongoDB Java Driver và các shard**. Tầng repository hoặc MongoTemplate không cần biết mỗi document nằm trên shard nào.

Ví dụ cấu hình kết nối của một ứng dụng Spring Boot sử dụng thuộc tính **spring.data.mongodb.uri**:

~~~yaml
spring:
  data:
    mongodb:
      uri: "mongodb://mongos-a.example.net:27017,mongos-b.example.net:27017/commerce?retryWrites=true"
~~~

Đây là địa chỉ minh họa, cần thay bằng các endpoint được cung cấp cho cụm thực tế. Với dịch vụ MongoDB được quản lý, hãy dùng connection string do nhà cung cấp cấp, kèm TLS và thông tin xác thực theo chính sách của hệ thống. Cú pháp property cấu hình có thể khác giữa các phiên bản Spring Boot; luôn kiểm tra phiên bản đang dùng.

Ví dụ ánh xạ document và truy vấn:

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.stereotype.Service;

@Document(collection = "orders")
record Order(
    @Id String id,
    String tenantId,
    String status,
    Instant createdAt
) {}

interface OrderRepository extends MongoRepository<Order, String> {
    List<Order> findByTenantIdAndStatus(String tenantId, String status);
}

@Service
class OrderLookupService {
    private final MongoTemplate mongoTemplate;

    OrderLookupService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    List<Order> findPaidByTenant(String tenantId) {
        Query targeted = Query.query(
            Criteria.where("tenantId").is(tenantId)
                    .and("status").is("PAID")
        );
        return mongoTemplate.find(targeted, Order.class);
    }
}
~~~

Trong dự án thực tế, các lớp trên nên được tách vào các file Java tương ứng. Ví dụ sử dụng **constructor injection** để Spring cung cấp MongoTemplate cho service; mỗi truy vấn truyền tenantId đang xử lý vào filter.

**Điều cần hiểu khi đọc code:**

- **@Document** ánh xạ lớp Java tới collection **orders**; record phải chứa trường **tenantId** phù hợp với shard key đã tạo.
- **MongoRepository** và **MongoTemplate** xây dựng filter rồi gửi qua driver. **mongos**, dựa trên shard key và metadata, mới là thành phần định tuyến.
- Cả hai cách truy vấn đều có thể nhắm vào shard đích nếu filter chứa điều kiện shard key thích hợp.
- Nếu chỉ gọi **findByStatus("PAID")**, ứng dụng vẫn hoạt động về mặt API nhưng truy vấn có thể phải đi nhiều shard. Sự thuận tiện của repository không loại bỏ chi phí phân tán.
- Tạo và tái sử dụng **MongoClient**/connection pool ở phạm vi ứng dụng; không tạo client mới sau mỗi request.

Đối với thao tác ghi, nên thiết kế document và điều kiện update/delete để mang thông tin shard key khi thích hợp. Một cập nhật theo tenantId và mã đơn sẽ dễ định tuyến và kiểm soát hơn truy vấn bỏ qua tenantId. Một số thao tác trên sharded collection còn có yêu cầu riêng tùy phiên bản MongoDB.

## 8. Các giới hạn và chi phí phải tính trước

### Tải lệch và điểm nóng (hotspot)

Một shard có thể nhận phần lớn ghi nếu khóa phân mảnh tăng đơn điệu hoặc một giá trị shard key quá phổ biến. Tăng số shard chưa chắc giải quyết được nếu workload luôn dồn vào cùng vùng dữ liệu. Đánh giá phân phối khóa bằng dữ liệu và mẫu truy cập thật.

### Truy vấn xuyên shard

Truy vấn thiếu shard key có thể cần truy cập nhiều shard, tăng lượng kết nối, I/O và truyền dữ liệu. Kết quả lớn, sort và aggregation xuyên shard đặc biệt cần chú ý. Việc tạo index cục bộ vẫn quan trọng, nhưng index không thay thế cho shard key trong định tuyến.

### Chi phí của transaction

MongoDB hỗ trợ transaction có thể liên quan tới nhiều shard trong các cấu hình và phiên bản thích hợp, song coordination giữa các thành phần làm tăng độ trễ và sử dụng tài nguyên. Với Spring Data MongoDB, **MongoTransactionManager** quản lý transaction ở mức framework; nó không loại bỏ chi phí của distributed transaction. Nên ưu tiên mô hình document và ranh giới nghiệp vụ giúp giảm số thao tác phải trải qua nhiều shard.

### Ràng buộc unique và nhất quán dữ liệu

Unique index trên sharded collection có các điều kiện liên quan đến shard key; không thể suy rằng mọi unique index trên một shard sẽ tự bảo đảm tính duy nhất toàn cụm. Khi thiết kế các trường như orderNumber, email hoặc mã nghiệp vụ, phải kiểm tra giới hạn theo phiên bản MongoDB và mô hình shard key cụ thể.

### Vận hành, bảo mật và tính sẵn sàng

- Theo dõi độ lệch dung lượng, mức sử dụng CPU/I/O, tốc độ truy vấn và độ trễ giữa các shard.
- Quan sát việc cân bằng dữ liệu, thay đổi topology và metadata; đây đều có thể ảnh hưởng tới độ trễ.
- Cấu hình nhiều mongos và kết nối thích hợp để tránh phụ thuộc vào một router duy nhất.
- Bảo vệ kết nối tới mongos bằng xác thực, TLS, quyền tối thiểu và quản lý secret an toàn.
- Triển khai replica set cho shard và config server theo kiến trúc có khả năng chịu lỗi; nhiều mongos **không thể bù đắp** cho một shard dữ liệu đang không khả dụng.

## 9. Tình huống lựa chọn kiến trúc

**Tình huống A — SaaS nhiều tenant:** Ứng dụng luôn gửi truy vấn kèm tenantId, các tenant có quy mô tương đối đồng đều. Shard key từ tenantId là ứng viên cần benchmark. Nếu dùng hashed tenantId, chú ý rằng một tenant rất lớn vẫn có thể gây tải cao tại một shard.

**Tình huống B — đơn hàng có báo cáo theo thời gian:** 95% truy vấn đọc một tenant nhưng 5% truy vấn tổng hợp doanh thu toàn hệ thống. Sharding có thể phục vụ tốt nhóm truy vấn tenant; nhóm báo cáo có thể phải chạy trên nhiều shard và cần tối ưu pipeline, index hoặc bố trí luồng phân tích riêng.

**Tình huống C — lượng dữ liệu thấp, ghi ít, yêu cầu sẵn sàng cao:** Một replica set được vận hành tốt có thể đơn giản và phù hợp hơn. Sharding không phải điều kiện bắt buộc để có failover.

**Tình huống D — một khách hàng tạo phần lớn dữ liệu:** Chọn tenantId làm shard key duy nhất có nguy cơ tập trung lượng ghi vào một shard, dù toàn hệ thống có nhiều shard. Cần khảo sát khóa ghép, phân phối truy cập và khả năng thay đổi mô hình lưu trữ trước khi chốt.

## 10. Checklist kiểm tra khi triển khai

1. **Xác định lý do mở rộng:** dung lượng, tải ghi, tải đọc hay cả ba? Đã tối ưu query/index và một replica set hay chưa?
2. **Thu thập workload:** filter được dùng nhiều, tỉ lệ query theo shard key, độ lớn document, phân bố tần suất khóa và xu hướng tăng trưởng.
3. **Chọn shard key dựa trên số liệu:** dự đoán targeted query, điểm nóng, vùng dữ liệu lớn và khả năng cân bằng.
4. **Thiết kế kết nối Spring Data MongoDB:** dùng endpoint mongos/endpoint cụm được hỗ trợ, connection pool, TLS, xác thực và timeout phù hợp.
5. **Đo trên môi trường mô phỏng:** so sánh explain, throughput, p95/p99 latency, lượng dữ liệu quét và số shard tham gia giữa truy vấn có/không có shard key.
6. **Theo dõi sau triển khai:** quan sát phân phối dữ liệu, cân bằng, lỗi router/shard và transaction xuyên shard; điều chỉnh theo số liệu.

### Câu hỏi tự kiểm tra

**1. Nếu mongos bị dừng, document có bị xóa không?** Không. mongos không phải nơi lưu document. Tuy nhiên client đang dùng router đó có thể mất kết nối cho tới khi chuyển sang router/endpoint khả dụng.

**2. Nếu một truy vấn có index trên mọi shard nhưng không có shard key, mongos có biết shard nào chứa kết quả không?** Thông thường không thể xác định chỉ từ index đó; truy vấn vẫn có thể phải đi nhiều shard.

**3. Có phải cứ thêm shard là thông lượng tăng theo tỉ lệ tuyến tính?** Không. Chi phí mạng, coordination, cân bằng, điểm nóng, truy vấn xuyên shard và giới hạn tài nguyên có thể làm lợi ích thấp hơn nhiều.

**4. Spring Data MongoDB cần API đặc biệt để chọn shard không?** Không. Ứng dụng dùng repository hoặc MongoTemplate bình thường; điều quan trọng là mô hình dữ liệu, filter và shard key hỗ trợ mongos định tuyến hiệu quả.

## Kết luận

Sharding mở rộng MongoDB bằng cách chia dữ liệu trên nhiều shard. **mongos là điểm định tuyến yêu cầu**: nhận thao tác từ driver, dựa vào metadata và shard key để chọn shard phù hợp, chuyển tiếp rồi tổng hợp kết quả khi cần. Trong ứng dụng Spring Data MongoDB, lợi ích của sharding không nằm ở một API riêng của MongoTemplate hay repository, mà nằm ở thiết kế **shard key, truy vấn, index và vận hành cụm**. Hãy kiểm chứng bằng workload và kế hoạch thực thi trước khi quyết định mở rộng ngang.
