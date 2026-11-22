# Quản lý keyspace và chỉ mục khi nhiều ứng dụng cùng ghi dữ liệu

Trong **Spring Data Redis Repositories**, annotation `@RedisHash` xác định nơi lưu thực thể theo keyspace, còn `@Indexed` cho phép truy vấn một số thuộc tính thông qua secondary index. Cả hai cơ chế đều đơn giản khi chỉ có một ứng dụng sở hữu dữ liệu. Khi nhiều ứng dụng cùng kết nối một Redis instance hoặc cluster, keyspace và chỉ mục trở thành **hợp đồng dữ liệu giữa các ứng dụng**.

Hai ứng dụng có thể vô tình ghi vào cùng một khóa. Ngay cả khi không đụng khóa chính, một ứng dụng cập nhật Redis Hash trực tiếp trong khi ứng dụng kia dùng repository có thể làm **Hash và secondary index mất đồng bộ**. Kết quả là đọc theo ID thấy dữ liệu mới, nhưng tìm theo `findByStatus(...)` lại không thấy hoặc dựa trên index cũ.

Để vận hành an toàn, phải quản lý cùng lúc **tên keyspace, phạm vi ID, quyền sở hữu ghi, schema và serializer, chỉ mục, TTL, quá trình nâng phiên bản và phương án đối soát**.

## 1. Keyspace của Redis Repository là gì?

Redis là kho dữ liệu key-value. Tên khóa phải duy nhất trong Redis database nơi ứng dụng đang kết nối. Redis không tự hiểu một nhóm khóa thuộc dịch vụ nào; các ứng dụng cần thống nhất tiền tố và quy tắc đặt tên.

Ví dụ Spring Data Redis:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("orders")
public class OrderRecord {

    @Id
    private String id;

    private String status;

    // Constructors, getters và setters...
}
```

Một bản ghi có ID `o-1001` thường được lưu tại khóa có dạng:

```text
orders:o-1001
```

Trong mô hình đó, `orders` là **keyspace**, còn `o-1001` là **ID của thực thể**. Redis Repository dùng Redis Hash và cơ chế mapping để lưu các thuộc tính của entity. Khi không khai báo `@RedisHash` với tên cụ thể, mapping context có quy tắc suy ra keyspace từ kiểu entity/cấu hình. Trong môi trường nhiều ứng dụng, nên đặt keyspace tường minh theo hợp đồng dữ liệu để thay tên Java class/package không vô tình đổi địa chỉ lưu trữ.

**Keyspace là tên logic, không phải một Redis database hay bảng SQL riêng.** Hai dịch vụ cùng kết nối database và cùng ghi `orders:o-1001` đang sửa cùng một khóa. Ngoài khóa Hash thực thể, repository còn có thể tạo khóa phụ để quản lý danh sách ID trong keyspace và các secondary index. Vì vậy, phạm vi namespace cần bao gồm **cả các khóa metadata do framework tạo**.

## 2. Quy ước keyspace khi nhiều ứng dụng dùng Redis chung

Một quy ước dễ kiểm soát:

```text
<domain-hoac-service>:<environment>:<entity>:<schema-version>
```

Ví dụ:

```text
commerce:prod:orders:v2
commerce:staging:orders:v2
catalog:prod:products:v1
identity:prod:sessions:v3
fulfillment:prod:tasks:v1
```

Đây là quy ước do hệ thống lựa chọn, không phải cú pháp Spring Data Redis bắt buộc. Với:

```java
@RedisHash("commerce:prod:orders:v2")
public class OrderRecord {
    @Id
    private String id;
}
```

ID `o-1001` thường được ánh xạ sang khóa thực thể:

```text
commerce:prod:orders:v2:o-1001
```

Mỗi thành phần giải quyết một nhu cầu:

| Thành phần | Ý nghĩa | Rủi ro khi thiếu |
|---|---|---|
| Domain hoặc service | Xác định nơi chịu trách nhiệm dữ liệu | Hai dịch vụ cùng sửa khóa |
| Environment | Tách phát triển, staging, production | Test làm hỏng dữ liệu production |
| Entity | Phân biệt đơn hàng, sản phẩm, phiên truy cập | Hai loại entity dùng trùng ID |
| Schema version | Phân biệt hợp đồng lưu trữ không tương thích | Ứng dụng cũ đọc sai payload mới |
| ID | Định danh duy nhất trong keyspace | Ghi đè bản ghi của nguồn khác |

### 2.1. ID phải duy nhất trên phạm vi thực sự chia sẻ

Nếu ứng dụng A và B đều tạo đơn hàng với ID `123` rồi cùng dùng keyspace `commerce:prod:orders:v2`, cả hai có thể ghi khóa `commerce:prod:orders:v2:123`. Việc phân chia service ở tầng code không giúp Redis nhận ra hai thực thể khác nhau.

Các lựa chọn gồm UUID/ULID hoặc ID kết hợp tenant/nguồn:

```text
o-01J...
tenant-17:o-1001
partner-a:order-1001
```

Khi ghép các phần, phải quy định cách mã hóa dấu phân tách và ký tự đặc biệt. Đặc biệt, ID phải ổn định: đổi ID về bản chất là chuyển sang khóa mới, kéo theo cập nhật index và mọi tham chiếu.

### 2.2. Môi trường và Redis Cluster

Nếu Redis instance được chia sẻ giữa dev/staging/prod, tiền tố có environment giúp nhận diện dữ liệu, nhưng **không cung cấp ranh giới bảo mật tuyệt đối**. Với dữ liệu nhạy cảm hoặc rủi ro vận hành cao, nên tách tài nguyên và quyền truy cập phù hợp.

Không coi Redis logical database number là giải pháp chung cho Redis Cluster: chế độ Redis Cluster thông thường chỉ hỗ trợ database 0. Thiết kế namespace và Redis ACL/tách cluster phải phù hợp topology thực tế.

Giá trị truyền trong `@RedisHash("...")` là một hằng trong annotation. Nếu môi trường cần chọn keyspace động, hãy sử dụng cơ chế cấu hình keyspace trong Spring Data Redis mapping hoặc tách deployment theo kết nối. Không mặc định annotation tự thay mọi placeholder môi trường nếu chưa cấu hình cơ chế hỗ trợ.

## 3. Secondary index của `@Indexed` hoạt động ra sao?

Redis Hash không tự có khả năng truy vấn tùy ý theo field. Spring Data Redis Repositories hỗ trợ **secondary index** cho những thuộc tính được đánh dấu `@Indexed`.

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("commerce:prod:orders:v2")
public class OrderRecord {

    @Id
    private String id;

    @Indexed
    private String status;

    @Indexed
    private String shopId;

    private long totalInCents;

    public OrderRecord() {
    }

    public OrderRecord(
            String id, String status, String shopId, long totalInCents) {
        this.id = id;
        this.status = status;
        this.shopId = shopId;
        this.totalInCents = totalInCents;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public String getShopId() { return shopId; }
    public void setShopId(String shopId) { this.shopId = shopId; }

    public long getTotalInCents() { return totalInCents; }
    public void setTotalInCents(long totalInCents) {
        this.totalInCents = totalInCents;
    }
}
```

Repository:

```java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface OrderRecordRepository
        extends CrudRepository<OrderRecord, String> {

    List<OrderRecord> findByStatus(String status);
    List<OrderRecord> findByShopId(String shopId);
}
```

Ý nghĩa logic của dữ liệu:

```text
commerce:prod:orders:v2:o-1001
    |
    +-- status = "CREATED"
    +-- shopId = "shop-7"
    +-- totalInCents = 250000

Secondary index theo status:
    CREATED -> o-1001, o-1002, ...

Secondary index theo shopId:
    shop-7  -> o-1001, o-1010, ...
```

Spring Data Redis có thể sử dụng Redis Set để duy trì danh sách khóa thực thể gắn với giá trị index. Các khóa index và metadata cụ thể tùy thuộc mapping và phiên bản thư viện; sơ đồ trên **diễn tả quan hệ**, không phải tên khóa nội bộ cố định để ứng dụng tự thao tác.

Khi entity được ghi qua repository, framework biết những thuộc tính được index và thực hiện thao tác quản lý liên quan. Lúc `status` đổi từ `CREATED` sang `PAID`, membership của trạng thái cũ và mới phải được cập nhật tương ứng.

### `@Indexed` không phải unique constraint

Nhiều đơn hàng có thể cùng `status = CREATED` và cùng nằm trong index. Tương tự, đánh dấu `@Indexed` cho `externalOrderCode` không ngăn hai entity có chung mã. Nếu nghiệp vụ yêu cầu giá trị duy nhất, cần cơ chế ghi/kiểm tra nguyên tử ở nơi cung cấp được ràng buộc đó; không dựa vào `@Indexed` để tự ngăn trùng.

## 4. Vì sao ghi trực tiếp Hash có thể làm lệch index?

Giả sử ứng dụng A lưu đơn hàng qua repository:

```java
orderRepository.save(
        new OrderRecord("o-1001", "CREATED", "shop-7", 250000L));
```

Từ góc nhìn hệ thống, Hash `o-1001` và metadata chỉ mục `status=CREATED` được duy trì theo cơ chế của Spring Data Redis.

Ứng dụng B có thể chỉ biết Redis key, rồi chạy:

```redis
HSET commerce:prod:orders:v2:o-1001 status PAID
```

Lệnh `HSET` thay giá trị trong Hash, nhưng **không chạy bộ ánh xạ và quản lý secondary index của Spring Data Redis Repository**. Kết quả có thể là:

```text
Hash o-1001:
    status = PAID

Index CREATED:
    vẫn có o-1001

Index PAID:
    chưa có o-1001
```

Khi đó:

```text
findById("o-1001")       -> đọc Hash, thấy PAID
findByStatus("PAID")     -> có thể bỏ sót o-1001
findByStatus("CREATED")  -> có thể còn đi theo membership cũ
```

Tùy quy trình ánh xạ kết quả, index cũ có thể dẫn đến dữ liệu trả không khớp điều kiện hoặc đọc thừa. Vấn đề là **Hash và chỉ mục không còn phản ánh cùng một phiên bản**.

Một số thao tác dễ tạo sai lệch:

- `HSET` hoặc `HDEL` trực tiếp trên field có `@Indexed`.
- `DEL` khóa chính mà không sử dụng cơ chế dọn index tương ứng.
- Ghi lại Hash bằng một Redis client/ngôn ngữ khác mà không hiểu metadata do repository tạo.
- Hai ứng dụng cùng dùng repository nhưng có **khác nhau về trường `@Indexed`, converter, mapping hoặc phiên bản schema**.
- Import dữ liệu thẳng vào Redis rồi truy vấn bằng `findBy...` khi chưa dựng secondary index cho dữ liệu mới.

**Hợp đồng quan trọng:** Một keyspace do repository quản lý cần có **một cơ chế ghi nhất quán cho cả Hash và index**. Không chỉ yêu cầu “mọi ứng dụng cùng đặt tên khóa” mà còn phải thống nhất cách cập nhật và xóa dữ liệu.

## 5. Ba mô hình dùng chung Redis giữa các ứng dụng

### Mô hình A — Mỗi ứng dụng sở hữu một keyspace

```text
Redis chung
  |
  +-- catalog:prod:products:v1:*     <- catalog-service
  +-- commerce:prod:orders:v2:*      <- order-service
  +-- identity:prod:sessions:v3:*    <- identity-service
  +-- analytics:prod:projections:v1:*<- analytics-service
```

Mỗi dịch vụ quản lý schema và index của riêng mình; dịch vụ khác yêu cầu dữ liệu qua API/event. Đây thường là mô hình dễ vận hành nhất nếu không có nhu cầu đặc biệt phải ghi trực tiếp vào cùng tập thực thể.

### Mô hình B — Một dịch vụ ghi, nhiều dịch vụ đọc

`order-service` tạo/cập nhật đơn hàng, `report-service` chỉ đọc.

Đọc chung yêu cầu hiểu đúng keyspace, serializer, field names, ý nghĩa ID và chính sách thay đổi schema. Nếu `report-service` chỉ cần báo cáo, việc dùng API hoặc projection riêng thường giảm phụ thuộc vào internal mapping.

Điểm cần nhớ: chỉ đọc trực tiếp vẫn là **ghép nối với định dạng lưu trữ**. Đổi class/package hoặc converter trong ứng dụng sở hữu có thể phá khả năng đọc của ứng dụng còn lại.

### Mô hình C — Nhiều ứng dụng cùng ghi một keyspace

`order-api` tạo đơn; `billing-worker` chuyển trạng thái sau thanh toán; `sync-worker` đồng bộ đơn bên ngoài.

Rủi ro bao gồm:

1. Trùng ID và ghi đè bản ghi.
2. Bất đồng serializer, tên field hoặc enum.
3. Không đồng nhất tập thuộc tính được index.
4. Một bên làm mất/thay TTL khi ghi.
5. Ghi đồng thời tạo lost update.
6. Một bên xóa khóa, bên khác giữ metadata stale.
7. Triển khai song song phiên bản cũ/mới không cùng schema.

Nếu bắt buộc cùng ghi, các bên phải thống nhất **hợp đồng versioned**, sử dụng chung cơ chế ghi/đồng thời và có quy trình triển khai phối hợp. Chỉ cùng khai báo `@RedisHash` chưa đủ.

## 6. Một keyspace cần có chủ sở hữu dữ liệu

Có thể mô tả quyền sở hữu bằng bảng:

| Keyspace | Dịch vụ sở hữu | Bên sử dụng khác | Indexed fields | TTL |
|---|---|---|---|---|
| `commerce:prod:orders:v2` | `order-service` | `report-service` qua API/event | `status`, `shopId` | Theo vòng đời đơn |
| `catalog:prod:products:v1` | `catalog-service` | `commerce-service` qua API/event | `categoryId` | Theo chính sách cache |
| `identity:prod:sessions:v3` | `identity-service` | Dịch vụ được ủy quyền | Theo nhu cầu truy vấn | TTL bắt buộc |

Đây là **bảng quản trị đề xuất**, không có tác dụng cấu hình tự động. Nó giúp đội triển khai trả lời:

- Ai được tạo, sửa và xóa entity? Ai chỉ được đọc?
- Những field nào có thể thay đổi, thay đổi bằng command hay event gì?
- Ai sở hữu schema, converter, TTL và logic `@Indexed`?
- Khi bản ghi bị xóa hoặc hết hạn, ai chịu trách nhiệm dọn index?
- Ai có quyền đổi keyspace, thêm/bỏ index và chạy backfill?
- Khi có sai lệch, đội nào thực hiện đối soát?

**Một chủ sở hữu logic không đồng nghĩa một JVM duy nhất.** Một service có thể có nhiều replica hoặc worker. Các replica vẫn cần giải quyết đồng thời, nhưng tất cả phải tuân theo **cùng một hợp đồng cập nhật**.

Nếu service khác muốn cập nhật trạng thái đơn, một thiết kế dễ kiểm soát là gửi command/event tới service sở hữu rồi để service đó ghi qua repository. Service cần dữ liệu để truy vấn báo cáo có thể tạo **read projection riêng** trong namespace của chính nó.

## 7. Ghi đồng thời có thể gây lost update hoặc index sai

Giả sử hai worker cùng đọc đơn hàng:

```text
             Trạng thái ban đầu: CREATED
                         |
              +----------+-----------+
              |                      |
          Worker A                Worker B
       đọc CREATED             đọc CREATED
              |                      |
      đặt status=PAID        đặt status=CANCELLED
              |                      |
      repository.save(...)   repository.save(...)
              |                      |
              +----------+-----------+
                         |
       Kết quả phụ thuộc thứ tự và xen kẽ thao tác
```

Redis xử lý từng lệnh theo ngữ nghĩa nguyên tử của lệnh đó, nhưng một thao tác repository có thể tạo **nhiều lệnh** để ghi Hash, cập nhật index, quản lý danh sách khóa và TTL. Không tự coi `repository.save(...)` là một transaction nghiệp vụ xuyên mọi khóa.

Để bảo vệ trạng thái:

- Điều phối cập nhật tại một dịch vụ sở hữu.
- Áp dụng quy tắc chuyển trạng thái rõ ràng, ví dụ chỉ cho phép `CREATED → PAID` khi chưa hủy.
- Dùng idempotency key cho message có thể được phát lại.
- Nếu cần compare-and-set/optimistic concurrency, chọn cơ chế thực sự **kiểm tra và ghi nguyên tử** ở nguồn quyết định.
- Với nghiệp vụ đòi tính nhất quán mạnh, cân nhắc đặt dữ liệu gốc trong hệ thống giao dịch thích hợp và để Redis là projection/cache.

Không chỉ dùng một script `HSET` nguyên tử để “sửa” vấn đề nếu field thuộc secondary index: script có thể sửa Hash nhưng index vẫn sai. Trong Redis Cluster, script và transaction đa khóa còn bị ràng buộc bởi hash slot; entity key và index key có thể không cùng slot. Vì vậy, đảm bảo nguyên tử xuyên Hash và các index liên quan cần thiết kế có chủ đích, không thể giả định framework tự làm thay.

## 8. Chi phí và giới hạn của `@Indexed`

Mỗi index tăng công việc ghi và dùng thêm bộ nhớ. Khi thay giá trị có index, membership cũ phải được loại bỏ và membership mới phải được tạo. Redis Repository còn có thể duy trì tập ID theo keyspace để phục vụ thao tác repository.

| Sự kiện | Ảnh hưởng tới dữ liệu | Điều phải chú ý |
|---|---|---|
| Tạo entity | Ghi Hash và index membership | Số field được index quyết định thêm công việc |
| Đổi field có `@Indexed` | Cập nhật Hash và membership | Không sửa raw Hash bỏ qua index |
| Đổi field không index | Chỉ thay đổi dữ liệu thực thể theo mapping | Không thêm index nếu không có truy vấn cần |
| Xóa bằng repository | Xóa entity và dọn metadata liên quan | Tránh bypass bằng `DEL` |
| Hết hạn TTL | Hash được Redis loại bỏ | Dọn index phụ thuộc cấu hình/sự kiện |
| Thêm `@Indexed` vào code | Mapping mới biết field cần index | Dữ liệu cũ cần backfill/reindex |

Một field `status` có ít giá trị sẽ tạo tập index có thể rất lớn. Một field có hàng triệu giá trị phân biệt có thể tạo rất nhiều tập nhỏ. Cả hai gây chi phí metadata; không đánh `@Indexed` cho mọi thuộc tính “để dự phòng”.

Secondary index repository cũng **không phải công cụ tìm kiếm tổng quát**. Nếu API yêu cầu full-text search, xếp hạng, sắp xếp hoặc phân trang phức tạp trên tập rất lớn, cần đánh giá read model hay giải pháp truy vấn phù hợp.

Dữ liệu của field được index có thể xuất hiện trong tên khóa metadata. Tránh đưa bí mật, token hoặc dữ liệu cá nhân nhạy cảm vào key/index dạng thô.

## 9. TTL, sự kiện hết hạn và chỉ mục còn sót

Một entity có thể được lưu với TTL, ví dụ thông qua `@RedisHash(timeToLive = ...)` hoặc `@TimeToLive`. Redis sẽ làm hết hạn khóa chính, nhưng Redis không biết secondary index của Spring Data Redis đang tham chiếu tới khóa đó.

Spring Data Redis có cơ chế **keyspace expiration events** hỗ trợ dọn metadata/index khi entity hết hạn. Cơ chế này có giới hạn:

- Redis phải phát sự kiện liên quan đến expiration; listener ở ứng dụng phải được cấu hình/hoạt động.
- Sự kiện Redis Pub/Sub không được lưu bền cho subscriber mất kết nối; ứng dụng khởi động muộn có thể bỏ lỡ event cũ.
- Trong Redis Cluster, sự kiện có phạm vi node; cần hiểu topology và cơ chế subscribe.
- Hết hạn vật lý và phát sự kiện không nhất thiết xảy ra ngay đúng giây TTL đạt 0.
- Tùy cấu hình, Spring Data Redis có thể lưu thêm **shadow copy/phantom copy** tồn tại lâu hơn khóa chính để phát sự kiện có dữ liệu entity; cần tính cả chi phí bộ nhớ đó.

Ví dụ:

```text
10:00:00  Lưu session:s7 với TTL 15 phút;
          index userId=u1 có membership liên quan.

10:15:00  Khóa chính hết hạn.

10:15:00  Listener bị gián đoạn, không nhận được event.

10:20:00  Index có thể vẫn giữ membership tới khóa đã mất.
```

Đây là lý do **TTL không bảo đảm index tự sạch trong mọi hoàn cảnh**. Khi có nhiều ứng dụng cùng ghi, tránh việc mỗi ứng dụng tự ý đặt TTL hoặc tự bật/tắt cơ chế sự kiện không đồng nhất.

Một thiết kế ổn định nên:

1. Xác định thành phần chịu trách nhiệm theo dõi và xử lý expiration cho keyspace.
2. Cấu hình notification của Redis tại hạ tầng nếu môi trường managed Redis không cho ứng dụng chạy lệnh cấu hình.
3. Xử lý trường hợp truy vấn index gặp entity đã mất.
4. Có quy trình đối soát hoặc rebuild index theo lô khi bỏ lỡ event.
5. Đo số lượng stale membership và chi phí shadow copy, đặc biệt với entity TTL ngắn.

Không xóa ồ ạt các khóa trông giống metadata của repository khi chưa hiểu cấu trúc phiên bản đang chạy; việc xóa nhầm có thể làm hỏng truy vấn hoặc cơ chế dọn của framework.

## 10. Schema và serializer cũng là một phần của hợp đồng

Hai ứng dụng cùng dùng keyspace vẫn có thể hiểu dữ liệu khác nhau.

```text
Ứng dụng A                  Ứng dụng B
-----------                 -----------
status: String              status: enum khác tên giá trị
totalInCents: long          total: BigDecimal
@Indexed(status)            Không có @Indexed(status)
TTL: 7 ngày                 TTL: 30 phút
```

Spring Data Redis Repositories có cơ chế mapping và converter. Dữ liệu phức tạp/đa hình có thể dựa trên metadata kiểu, converter tùy chỉnh hoặc quy tắc tên thuộc tính. Thay đổi Java class/package, serializer hay đơn vị tiền có thể khiến ứng dụng khác đọc sai dữ liệu mà vẫn nhìn thấy cùng khóa Redis.

Nếu phải chia sẻ trực tiếp, hợp đồng nên xác định:

- Tên field, kiểu, định dạng ID, đơn vị và ý nghĩa `null`.
- Quy tắc chuyển đổi và representation của các kiểu đặc biệt.
- Những thuộc tính được index và cách duy trì index khi ghi.
- TTL, điều kiện xóa, chính sách phục hồi dữ liệu mất.
- Khả năng tương thích của phiên bản cũ và mới trong thời gian rolling deployment.
- Cách xử lý dữ liệu không đọc được hoặc dữ liệu bị thiếu.

Giữa Java và ứng dụng ngôn ngữ khác, không nên xem biểu diễn nội bộ của `@RedisHash` là một giao thức liên hệ thống bất biến. API/event với payload được version hóa thường là ranh giới ổn định hơn.

## 11. Thêm chỉ mục vào dữ liệu đã có: cần backfill

Giả sử một triệu bản ghi `OrderRecord` được lưu khi thuộc tính `status` chưa có `@Indexed`. Sau một deployment, developer thêm:

```java
@Indexed
private String status;
```

Việc thay đổi annotation **không tự quét toàn bộ một triệu Hash và tạo membership đầy đủ cho dữ liệu đã có**. Những bản ghi được lưu qua mapping mới có thể xuất hiện trong index, trong khi bản ghi cũ chưa được dựng index. Kết quả `findByStatus("PAID")` có thể trả một tập thiếu.

Cách triển khai:

1. Xác định số ID hiện có và các nguồn ghi đang hoạt động.
2. Chốt phiên bản entity mới, schema và index mong muốn.
3. Backfill qua cơ chế mapping có khả năng tạo index tương ứng, theo batch có giới hạn tải.
4. Theo dõi những cập nhật xảy ra trong lúc backfill; tránh ghi đè bản mới bằng snapshot cũ.
5. Đối chiếu theo mẫu giữa Hash và membership index; chỉ chuyển query sang index mới sau khi đủ dữ liệu theo tiêu chí nghiệp vụ.

Nếu phải quét bằng Redis `SCAN`, cần duyệt hết cursor; một lần gọi không bảo đảm lấy đủ toàn bộ khóa, và tập khóa có thể thay đổi trong lúc quét. Không suy luận “đã backfill xong” chỉ từ số lượng phần tử của một batch.

## 12. Thay keyspace và triển khai phiên bản mới

Đổi annotation:

```java
// Phiên bản cũ
@RedisHash("orders")

// Phiên bản mới
@RedisHash("commerce:prod:orders:v2")
```

không tự chuyển dữ liệu cũ. Đây là **thay đổi địa chỉ lưu entity và metadata**. Reader mới có thể không tìm thấy khóa cũ; writer cũ vẫn ghi namespace cũ trong thời gian rollout.

Một quy trình an toàn gồm các giai đoạn:

### Giai đoạn A — Kiểm kê

Tìm các writer/readers hiện hữu, schema, secondary index, TTL, khối lượng key, nguồn ID và quy tắc xóa.

### Giai đoạn B — Thiết lập namespace mới

Chốt `v2`, ID, converter, các field có `@Indexed`, dịch vụ sở hữu và quyền truy cập. Chuẩn bị cách đọc v1 để hỗ trợ migration.

### Giai đoạn C — Chuyển dữ liệu theo lô

Đọc v1 theo batch, biến đổi rồi lưu bằng mapping v2 nhằm tạo cả Hash và index đúng. Nếu có dữ liệu thay đổi trong quá trình chuyển, cần cơ chế change event/điều phối để v2 theo kịp và không bị backfill cũ ghi đè.

### Giai đoạn D — Chuyển reader và writer

Khi dữ liệu v2 đã đáp ứng tiêu chí đối soát, chuyển luồng đọc và ghi theo kế hoạch. Nếu dùng dual-write tạm thời, phải tính đến retry/idempotency và trường hợp ghi v1 thành công nhưng v2 thất bại. Hai lần `save` riêng biệt không đương nhiên tạo một transaction xuyên hai keyspace.

### Giai đoạn E — Ngừng sử dụng v1

Chỉ dọn v1 sau khi không còn application hoặc consumer nào phụ thuộc, đủ thời gian bảo lưu và đã xác nhận migration. Dọn cả metadata/index cũ theo quy trình, không chỉ xóa Hash chính.

```text
                    Migration window
                           |
             +-------------+--------------+
             |                            |
         old keyspace                  v2 keyspace
           orders:*              commerce:prod:orders:v2:*
             |                            ^
             +----- backfill + changes ---+
                                          |
                                    reader/writer v2
                                          |
                                   cutover và đối soát
                                          |
                                      retire v1
```

Một schema migration hoàn thành khi **đọc theo ID và truy vấn dựa trên index** đều phản ánh tập dữ liệu đích theo yêu cầu.

## 13. Multi-tenant và kiểm soát quyền truy cập

Nếu hai tenant cùng có ID `order-1`, keyspace chung `commerce:prod:orders:v2` cần chiến lược định danh để tránh đè khóa.

Ví dụ:

```text
commerce:prod:orders:v2:tenant-17:order-1
commerce:prod:orders:v2:tenant-29:order-1
```

Có thể dùng ID ghép tenant hoặc keyspace riêng cho từng tenant tùy mô hình và số lượng tenant. Dù dùng cách nào, các truy vấn repository phải giới hạn đúng tenant tại ranh giới nghiệp vụ. Chỉ có field `tenantId` được index không bảo đảm tự động ngăn truy vấn sai phạm vi.

Khi các service cùng kết nối Redis, có thể dùng **Redis ACL** với credential riêng và mẫu khóa được phép để giảm phạm vi ghi. Tuy nhiên, ACL phải cho phép chính xác các khóa framework sử dụng: Hash entity, index Set, keyspace metadata và dữ liệu phụ khi bật TTL shadow copy. Nếu ACL chỉ cho phép khóa Hash nhưng từ chối key index, thao tác repository có thể lỗi một phần.

Với dữ liệu có yêu cầu cách ly cao, tách Redis deployment/instance hoặc boundary mạng có thể đáng tin cậy hơn việc chỉ dùng prefix.

## 14. Phát hiện và điều tra index không nhất quán

Các triệu chứng thường gặp:

| Triệu chứng | Nguyên nhân cần điều tra |
|---|---|
| `findById(id)` có dữ liệu, `findByStatus(status)` không có | Chưa reindex, ghi Hash raw hoặc index bị lệch |
| Index trỏ tới ID không còn Hash | Khóa bị xóa/hết hạn, listener bỏ lỡ expiration |
| Lỗi deserialize sau một deployment | Schema, type metadata hoặc converter không tương thích |
| TTL thay đổi bất thường | Nhiều writer có chính sách khác nhau |
| Index tăng số lượng khóa nhanh | Thêm field hoặc field cardinality cao |
| Truy vấn trả kết quả khác giữa các service | Keyspace/mapping/index không đồng nhất |

Các lệnh hỗ trợ khảo sát:

```bash
# Quét theo cursor, theo một namespace xác định:
redis-cli --scan --pattern 'commerce:prod:orders:v2:*'

# Xem kiểu và nội dung một entity:
redis-cli TYPE 'commerce:prod:orders:v2:o-1001'
redis-cli HGETALL 'commerce:prod:orders:v2:o-1001'
redis-cli TTL 'commerce:prod:orders:v2:o-1001'

# Thống kê tổng thể Redis:
redis-cli INFO commandstats
redis-cli INFO memory
redis-cli SLOWLOG GET 10
```

Lệnh `--scan` dùng SCAN phù hợp hơn `KEYS *` để khảo sát instance lớn, nhưng vẫn cần giới hạn tốc độ và phạm vi. Tránh `KEYS *` trên Redis production có nhiều khóa.

Nếu đã xác định đúng **tên khóa index thực tế** từ mapping và phiên bản, có thể dùng `TYPE`, `SCARD`, `SSCAN` để khảo sát membership của Redis Set. Đừng dựa vào sơ đồ khái niệm rồi chỉnh sửa trực tiếp mọi khóa có cùng prefix.

`INFO commandstats` là thống kê theo cả Redis instance; `SLOWLOG` chỉ ghi những lệnh vượt ngưỡng thời gian xử lý phía Redis, không biểu diễn đầy đủ số lượt đọc hay độ trễ mạng. Cần bổ sung telemetry theo service, trace ID, phiên bản triển khai và số lượng thao tác repository.

### Đối soát dữ liệu và index

Một lần đối soát có thể lấy mẫu ID hoặc một tập ID đã biết, đọc Hash, kiểm tra giá trị field index, so membership trong index tương ứng và ghi nhận:

- **Missing membership:** Hash tồn tại, có giá trị được index nhưng không thấy trong index tương ứng.
- **Stale membership:** Index có ID nhưng Hash không tồn tại hoặc giá trị field đã khác.
- **Mapping error:** Khóa tồn tại nhưng không ánh xạ được về entity theo hợp đồng.

Nên tìm **đường ghi gây sai lệch** trước khi sửa hàng loạt. Nếu một ứng dụng vẫn gọi `HSET` trực tiếp, index sẽ tiếp tục bị lệch dù vừa được rebuild. Công cụ sửa phải hiểu cả bookkeeping của repository, không chỉ chỉnh một Redis Set đơn lẻ.

## 15. Tình huống ứng dụng: Order API và Billing Worker

Giả sử ba ứng dụng:

- `order-api` tạo đơn hàng, trả danh sách và tìm theo `status`.
- `billing-worker` nhận kết quả thanh toán và đánh dấu đơn `PAID`.
- `report-service` cần báo cáo những đơn đã thanh toán.

Tất cả cùng dùng Redis.

### Thiết kế dễ gây lỗi

```text
1. order-api:
   repository.save(Order("o-1001", status="CREATED"))
   -> Hash = CREATED
   -> index CREATED chứa o-1001

2. billing-worker:
   HSET commerce:prod:orders:v2:o-1001 status PAID
   -> Hash = PAID
   -> index CREATED chưa được gỡ o-1001
   -> index PAID chưa có o-1001

3. report-service:
   findByStatus("PAID")
   -> có thể không tìm thấy o-1001
```

Redis đã thực thi đúng `HSET`. Lỗi nằm ở **việc bypass quy tắc quản lý index của repository**.

### Thiết kế có chủ sở hữu logic

```text
billing-worker
    |
    +-- PaymentConfirmed(orderId, eventId)
                    |
                    v
               order-service
                    |
         Xử lý event idempotent
         Kiểm tra chuyển trạng thái
                    |
                    v
           repository.save(...)
                    |
           +--------+--------+
           |                 |
        Order Hash        Index metadata
           |                 |
           +--------+--------+
                    |
              OrderPaid event
                    |
                    v
              report-service
          (API hoặc projection riêng)
```

Ở mô hình này, `order-service` chịu trách nhiệm logic ghi, schema và index cho keyspace đơn hàng. `billing-worker` yêu cầu thay đổi bằng một command/event được kiểm soát; `report-service` đọc qua API hoặc projection riêng. Nếu nhiều instance `order-service` có thể cùng xử lý một ID, vẫn phải giải quyết race condition và idempotency ở tầng nghiệp vụ.

Khi chưa thể bỏ mô hình nhiều writer, tối thiểu cần một hợp đồng dùng chung có version, quy trình triển khai tương thích, một cơ chế ghi có khả năng cập nhật index và chiến lược đối soát; đồng thời lên kế hoạch giảm bớt các điểm ghi độc lập.

## 16. Quy trình chọn thiết kế trước khi mở rộng ứng dụng

```text
Một ứng dụng mới cần ghi Redis?
               |
               v
Dữ liệu thuộc keyspace đã có owner?
      |                        |
     Có                       Không
      |                        |
      v                        v
Yêu cầu owner             Chọn namespace và ID
cấp API/event             có ranh giới rõ ràng
      |                        |
      v                        v
Nếu cần đọc trực tiếp:     Xác định schema, TTL,
thống nhất hợp đồng        @Indexed, converter
đọc và version                 |
      |                        v
      |                   Chốt chủ sở hữu ghi
      |                        |
      +-------------+----------+
                    |
                    v
          Thiết kế concurrency,
          ACL, migration và quan sát
```

Trước khi thêm một keyspace/index mới, hãy tự trả lời: Ai sở hữu nó? ID có duy nhất không? Ai được sửa field index? Dữ liệu cũ sẽ được reindex thế nào? Nếu một entity hết hạn lúc listener không hoạt động thì xử lý ra sao? Nếu hai phiên bản triển khai cùng ghi, có thể gây lost update không?

## 17. Những sai lầm cần tránh

- **Dùng `@RedisHash("orders")` trong nhiều dịch vụ không phối hợp:** dễ xung đột ID và index.
- **Đổi keyspace rồi kỳ vọng dữ liệu tự chuyển:** thực thể và metadata cũ không được migrate tự động.
- **Coi `@Indexed` là unique constraint:** index không tự ngăn hai entity có cùng giá trị.
- **Sửa Hash bằng `HSET` nhưng truy vấn bằng repository:** Hash có thể thay đổi trong khi secondary index không cập nhật.
- **Cho writer dùng serializer/schema khác nhau:** có thể đọc sai field hoặc mất khả năng ánh xạ.
- **Thêm `@Indexed` mà không reindex dữ liệu cũ:** `findBy...` có thể trả danh sách thiếu.
- **Giả định `save` là transaction xuyên Hash/index:** không có bảo đảm đó cho mọi kịch bản đồng thời.
- **Tin expiration event luôn được nhận:** Pub/Sub có thể mất thông báo; cần phương án đối soát.
- **Chỉ phân quyền khóa Hash:** quên các khóa index và metadata do repository tạo.
- **Dùng `KEYS *` để rà soát production:** gây tải lớn trên Redis dùng chung.
- **Quên giới hạn tenant trong query:** keyspace và `@Indexed` không tự thực thi kiểm soát truy cập.

**Nguyên tắc:** Spring Data Redis Repository quản lý một **mô hình gồm thực thể và metadata index**, không chỉ một Redis Hash đơn lẻ. Khi nhiều ứng dụng cùng ghi, keyspace là hợp đồng về định danh, schema và quyền sở hữu; secondary index là dữ liệu phải được cập nhật đồng bộ với entity. Hãy thiết kế một chủ sở hữu logic cho mỗi keyspace, dùng namespace có phiên bản và kiểm soát mọi đường ghi, rồi kiểm chứng bằng các trường hợp thay trạng thái, TTL, backfill và triển khai đồng thời nhiều phiên bản.

