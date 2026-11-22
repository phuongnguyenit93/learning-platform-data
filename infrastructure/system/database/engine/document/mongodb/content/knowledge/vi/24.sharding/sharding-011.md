# Refine shard key, resharding và điều kiện hỗ trợ trong MongoDB

## 1. Bài toán: shard key từng hợp lý nhưng không còn phù hợp

Một ứng dụng SaaS lưu đơn hàng của nhiều khách hàng doanh nghiệp trong collection `orders`. Ban đầu nhóm phát triển chọn shard key:

```javascript
{ tenantId: 1 }
```

Ứng dụng chủ yếu truy vấn theo tenant, nên lựa chọn này có vẻ hợp lý. Sau một thời gian, tenant lớn nhất tăng lên hàng chục triệu đơn hàng, tạo phần lớn lưu lượng ghi của toàn hệ thống. Trong khi các shard khác còn dư tài nguyên, shard chứa khoảng khóa của tenant này trở thành điểm nóng.

Một số phương án được đưa ra:

1. **Thêm `orderId` vào sau `tenantId`** để key có độ phân biệt cao hơn, vẫn giữ trường đầu là tenant.
2. **Đổi hẳn sang `{orderId: "hashed"}`** để phân bố write trên toàn cluster.
3. **Đổi thứ tự sang `{regionId: 1, tenantId: 1}`** vì truy vấn sản phẩm hiện nay chủ yếu theo khu vực.

Ba phương án không thể thực hiện bằng cùng một lệnh. MongoDB phân biệt:

- **Refine shard key**: mở rộng shard key hiện tại bằng cách **thêm các trường ở phía sau**, giữ nguyên phần key đã có.
- **Resharding**: tổ chức lại một sharded collection theo **shard key mới**, có thể đổi trường, thứ tự, kiểu phân bố range/hashed khi được phiên bản MongoDB hỗ trợ.

Cả hai đều ảnh hưởng đến routing, index, mô hình truy vấn và cách vận hành; nhưng **refine shard key thường là thay đổi metadata không tự tái phân phối document ngay**, trong khi **resharding là một quá trình chuyển đổi phân bố dữ liệu thực sự**.

Sau bài học thuộc chương **Sharding** của MongoDB, bạn sẽ có thể:

1. Giải thích thế nào là shard key và vì sao không nên chọn chỉ dựa vào một query.
2. Phân biệt refine shard key với resharding và biết trường hợp nào cần mỗi cách.
3. Hiểu quy tắc **prefix + suffix** của `refineCollectionShardKey`.
4. Biết những điều kiện cần rà soát trước thay đổi: topology, phiên bản/FCV, index, dữ liệu, unique index, collation, zone và tải hệ thống.
5. Hiểu các giai đoạn resharding, tài nguyên cần thiết và giới hạn của việc “online”.
6. Xem tác động đến query routing, scatter-gather, chunk, jumbo/hotspot và application writes.
7. Thực hiện ví dụ `mongosh` trên một sharded cluster **thử nghiệm cô lập**.
8. Thiết kế kế hoạch triển khai, giám sát và phục hồi phù hợp cho production.

## 2. Ôn lại các thành phần thiết yếu của sharding

### 2.1. Shard key quyết định cách phân vùng dữ liệu

Trong MongoDB sharded cluster, một collection được phân bố theo **shard key**. Ví dụ:

```javascript
{ tenantId: 1, orderId: 1 }
```

Hai trường này tạo thành một **compound shard key**. Các trường và thứ tự của chúng ảnh hưởng trực tiếp đến:

- Cách chia không gian giá trị thành các khoảng khóa/chunk.
- Cách `mongos` định tuyến truy vấn và thao tác ghi.
- Mức độ phân bố dữ liệu và lượng ghi trên các shard.
- Khả năng dùng shard key để lọc truy vấn.
- Các điều kiện ràng buộc unique index trong sharded collection.

Shard key không phải chỉ là một index để tăng tốc: nó là một phần của **kiến trúc phân bố dữ liệu**.

### 2.2. Các thành phần trong cluster

```text
             Application / MongoDB Driver
                         |
                         v
                       mongos
                         |
                Shard metadata/routing
                         |
        +----------------+----------------+
        |                |                |
        v                v                v
    Shard A          Shard B          Shard C
  (replica set)    (replica set)    (replica set)
        |                |                |
      Data             Data             Data
```

Các thành phần:

- **`mongos`**: router chuyển truy vấn tới shard phù hợp dựa trên metadata và query.
- **Shards**: nơi lưu document; thường triển khai dưới dạng replica set.
- **Config server replica set**: duy trì metadata sharding.
- **Balancer và các cơ chế phân phối chunk/range**: giúp phân bổ dữ liệu theo chính sách hiện tại.

Không phải mỗi tenant tương ứng một shard cố định. Dữ liệu/chunk có thể được phân bổ, di chuyển hoặc tổ chức lại theo thời gian.

### 2.3. Ranged và hashed shard key

**Ranged sharding** dùng thứ tự giá trị khóa:

```javascript
{ orderId: 1 }
{ tenantId: 1, orderId: 1 }
```

Nó có thể hỗ trợ query theo khoảng và locality theo key, nhưng có nguy cơ hotspot nếu phần khóa được ghi tăng đơn điệu hoặc có độ phân biệt thấp.

**Hashed sharding** dùng giá trị hash của một trường key:

```javascript
{ orderId: "hashed" }
```

Hash giúp phân tán nhiều giá trị khác nhau trên không gian khóa nhưng làm thay đổi lợi thế của query theo khoảng giá trị gốc. Chọn hashed không có nghĩa mọi query đều được target tốt hơn, và **hashed index không hỗ trợ unique constraint** trực tiếp.

### 2.4. Shard key tốt phải được đánh giá trên workload thực

| Yếu tố | Câu hỏi cần trả lời |
| --- | --- |
| Cardinality | Có đủ giá trị shard key khác nhau không? |
| Frequency/skew | Một giá trị hoặc một nhóm giá trị có chiếm phần lớn dữ liệu không? |
| Monotonicity | Giá trị có tăng tuần tự tạo hotspot tại một phía range không? |
| Query routing | API quan trọng có biết shard key để target thay vì scatter-gather không? |
| Write distribution | Tốc độ ghi có phân bố đều giữa các shard không? |
| Data growth | Dự kiến tenant, vùng hoặc collection tăng trưởng như thế nào? |
| Uniqueness | Các unique index bắt buộc có tương thích shard key không? |
| Zones | Có yêu cầu cư trú dữ liệu theo vùng hoặc tier không? |
| Migration cost | Có đủ dung lượng, network và thời gian thực hiện thay đổi không? |

Đổi shard key khi chưa đo workload có thể chỉ chuyển hotspot từ nơi này sang nơi khác.

## 3. Hai thao tác khác nhau: refine và reshard

### 3.1. Refine là bổ sung suffix

Giả sử shard key hiện tại:

```javascript
{ tenantId: 1 }
```

Một shard key refined hợp lệ về mặt hình dạng:

```javascript
{ tenantId: 1, orderId: 1 }
```

Vì key mới **giữ nguyên tiền tố** `tenantId:1` rồi thêm `orderId:1` ở cuối.

Ví dụ nhiều suffix:

```javascript
// Cũ
{ regionId: 1, tenantId: 1 }

// Refine bằng cách thêm hai field ở cuối
{
  regionId: 1,
  tenantId: 1,
  orderMonth: 1,
  orderId: 1
}
```

Điểm quan trọng: refine **không thay thế, xóa hoặc đảo thứ tự** các field shard key đang có. Nó cũng không tự đổi một component từ `1` sang `"hashed"`.

### 3.2. Reshard là chọn một key mới và tổ chức lại dữ liệu

Nếu cần từ:

```javascript
{ tenantId: 1 }
```

chuyển sang:

```javascript
{ orderId: "hashed" }
```

thì đây là **resharding** chứ không phải refinement, vì key mới không giữ prefix cũ.

Resharding cũng phù hợp khi muốn:

- Thay `tenantId` bằng `customerId`.
- Đổi thứ tự trường trong compound key.
- Bỏ một trường không còn cần thiết khỏi shard key.
- Thay đổi cách phân vùng giữa range và hash, nếu được tính năng/phiên bản hỗ trợ.
- Phân phối lại collection theo một key đã được thiết kế mới.

Resharding không phải một thao tác đổi tên index đơn thuần. Hệ thống phải chuyển đổi dữ liệu/metadata để collection hoạt động theo phân phối mới.

### 3.3. Bảng so sánh

| Tiêu chí | Refine shard key | Resharding |
| --- | --- | --- |
| Mục đích | Thêm độ phân biệt ở **cuối** key hiện có | Thay đổi cách shard collection |
| Được xóa/reorder field cũ không? | Không | Có thể chọn key mới theo điều kiện hỗ trợ |
| Được chuyển `{a:1}` sang `{a:1,b:1}`? | Có, nếu thỏa điều kiện | Có thể cân nhắc, nhưng thường không cần nếu refine đáp ứng |
| Được chuyển `{a:1}` sang `{b:1}`? | Không | Có |
| Tự phân phối lại toàn bộ dữ liệu ngay? | Không | Có quá trình redistributing/resharding |
| Chi phí network/storage lớn | Thường thấp hơn; vẫn cần index và metadata | Có thể rất lớn, cần capacity planning |
| Có thể hoàn tác bằng cách bỏ suffix đơn giản? | Không | Không có “undo” tức thì; cần kế hoạch reshard tiếp hoặc khôi phục |
| Cần hỗ trợ của server/FCV | Có | Có |
| Có tác động tới query/unique/zone không? | Có | Có |
| Có nên chạy tùy tiện trên production không? | Không | Không |

**Quy tắc lựa chọn nhanh:** nếu yêu cầu chỉ là **thêm các field ở đuôi shard key** và vẫn muốn giữ các trường cũ theo thứ tự, hãy nghiên cứu **refine** trước. Nếu yêu cầu **thay đổi cấu trúc nền tảng của key**, cần đánh giá **resharding**.

## 4. Quy tắc prefix của refine shard key

### 4.1. Thứ tự trường là bắt buộc

Với shard key hiện tại:

```javascript
{ tenantId: 1, regionId: 1 }
```

các key mới xét về quy tắc giữ tiền tố:

```javascript
// Có cấu trúc refinement: giữ prefix cũ, thêm suffix.
{ tenantId: 1, regionId: 1, orderId: 1 }

// Thêm nhiều suffix:
{ tenantId: 1, regionId: 1, orderMonth: 1, orderId: 1 }
```

Các key **không phải refinement**:

```javascript
// Bỏ regionId
{ tenantId: 1, orderId: 1 }

// Đảo thứ tự trường cũ
{ regionId: 1, tenantId: 1, orderId: 1 }

// Chèn trường vào giữa prefix hiện có
{ tenantId: 1, orderId: 1, regionId: 1 }

// Đổi field đầu
{ customerId: 1, regionId: 1 }

// Đổi kiểu field đầu
{ tenantId: "hashed", regionId: 1 }
```

Việc những key này có thể được dùng trong một **resharding operation** hay không phải kiểm tra theo giới hạn phiên bản, index, topology và dữ liệu thực tế. Điều chắc chắn là chúng **không thỏa quy tắc suffix-only của refine**.

### 4.2. Vì sao MongoDB giới hạn refine như vậy?

Refine mở rộng không gian key bằng cách đặt các giá trị suffix sau phần prefix hiện có:

```text
Key cũ:

  tenantId
  T1 | T2 | T3 | ...

Key refined:

  (tenantId, orderId)
  (T1, O001) (T1, O002) ... (T2, O001) ...
```

Giữ prefix cho phép MongoDB chuyển metadata các range/chunk hiện tại sang dạng key dài hơn mà **không bắt buộc ngay lập tức chép mọi document sang nơi khác theo một không gian key không liên quan**.

Nếu đổi trường đầu hoặc thứ tự, những document trước đây gần nhau theo key cũ có thể cần được sắp xếp/phân phối hoàn toàn khác; đó là công việc của resharding.

### 4.3. Refine không phải chỉ thêm một compound index

Lệnh:

```javascript
db.orders.createIndex({ tenantId: 1, orderId: 1 });
```

chỉ tạo **index**. Nó không tự cập nhật metadata shard key của collection.

Sau khi chuẩn bị index, thao tác refine cần lệnh quản trị riêng:

```javascript
sh.refineCollectionShardKey(
  "sales.orders",
  { tenantId: 1, orderId: 1 }
);
```

Ngược lại, `refineCollectionShardKey` không phải nơi tạo tự động mọi index phụ trợ cho query nghiệp vụ. Cần xem điều kiện **index hỗ trợ new shard key** trước khi chạy.

### 4.4. Metadata được cập nhật, không tự tái cân bằng dữ liệu ngay

Sau khi refine:

- Metadata shard key của collection sử dụng key mới.
- Các khoảng/chunk hiện hữu có thể được biểu diễn bằng key dài hơn.
- Dữ liệu hiện có **không được tự động sao chép toàn bộ tới vị trí mới chỉ vì câu lệnh refine vừa trả thành công**.
- Phân bố có thể thay đổi dần qua cơ chế split/move/chunk balancing theo tính năng và điều kiện của phiên bản đang chạy.
- Các query và write sau refinement phải tương thích với key mới, đặc biệt khi cần targeted routing.

Nếu mục tiêu bắt buộc là **tái phân phối ngay một collection bị lệch nghiêm trọng**, chỉ refine có thể chưa giải quyết sự mất cân bằng. Cần theo dõi chunk/range distribution và đánh giá các bước tiếp theo.

## 5. Điều kiện hỗ trợ của refine

### 5.1. Version và feature compatibility

MongoDB giới thiệu khả năng **refine shard key** từ dòng phiên bản **4.4**. Tuy nhiên, khi áp dụng vào cluster thật cần kiểm tra:

- Tất cả thành phần của sharded cluster đã chạy phiên bản tương thích chưa?
- **Feature Compatibility Version (FCV)** đã đáp ứng yêu cầu của tính năng chưa?
- Driver và `mongosh` có cú pháp hỗ trợ không?
- Collection thuộc loại có được phép refine theo bản phát hành đó không?
- Cluster đang trong trạng thái DDL/resharding/balancing đặc biệt nào có thể gây xung đột với refinement?
- Nếu là dịch vụ managed, thao tác có được nhà cung cấp hỗ trợ cho tier/deployment đó không?

Một cluster có binary mới nhưng FCV chưa được nâng tương ứng có thể vẫn không cho phép các tính năng mới. Không dựa duy nhất vào số version của một `mongod` được kết nối để kết luận khả dụng toàn cluster.

### 5.2. Collection phải đã được shard

Refinement là thao tác **trên một sharded collection**. Nó không dùng để biến một collection chưa sharded thành sharded.

Nếu collection chưa sharded, cần đánh giá quy trình tạo shard key ban đầu với `sh.shardCollection` hoặc lệnh quản trị tương ứng.

```javascript
// Shard collection lần đầu (chỉ ví dụ, không chạy trên production).
sh.shardCollection(
  "sales.orders",
  { tenantId: 1 }
);

// Sau đó mới có thể xét refine.
sh.refineCollectionShardKey(
  "sales.orders",
  { tenantId: 1, orderId: 1 }
);
```

Không gọi `sh.shardCollection` lần thứ hai với key mới rồi kỳ vọng nó biến thành lệnh reshard. Đó là hai thao tác khác nhau.

### 5.3. Phải có index hỗ trợ new shard key

Trước refine, MongoDB yêu cầu một **index hỗ trợ shard key đã mở rộng** theo quy tắc phiên bản hiện hành. Ví dụ:

```javascript
use sales

db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { name: "tenant_order_refined" }
);

// Chỉ sau khi kiểm tra điều kiện mới thực hiện:
sh.refineCollectionShardKey(
  "sales.orders",
  { tenantId: 1, orderId: 1 }
);
```

Chỉ mục hỗ trợ thường cần:

- Có phần key pattern tương thích với shard key refined.
- Không dựa trên index sparse/partial làm mất document có thể được shard.
- Không là multikey ở những thành phần không được phép làm shard key.
- Thỏa điều kiện về collation và loại index.
- Không xung đột với các ràng buộc unique hiện có.

Không coi `createIndex()` thành công là đủ chứng minh refine chắc chắn thành công; nó mới là **một phần của preflight**.

### 5.4. Field suffix phải phù hợp dữ liệu

Nếu muốn thêm `orderId`:

```javascript
{ tenantId: 1, orderId: 1 }
```

hãy khảo sát:

- Bao nhiêu document không có `orderId`?
- Có document nào `orderId: null` hoặc kiểu không nhất quán?
- Có document chứa `orderId` là mảng không?
- `orderId` có độ phân biệt đủ trong từng tenant không?
- Trường này có bị sửa thường xuyên không?
- Các API ghi mới có bảo đảm field tồn tại và đúng kiểu không?

Không mặc định mọi phiên bản từ chối tất cả document thiếu suffix theo cùng một cách: MongoDB có thay đổi khả năng xử lý **missing shard key fields** qua các release. Cần kiểm tra tính năng và đặc điểm collection thực tế. Dù server cho phép missing/null, hàng loạt document thiếu suffix có thể cùng nằm trong một vùng giá trị và **không giúp phân bố tốt hơn**.

Với dữ liệu legacy, có thể cần migration để bổ sung key **theo chính sách đã xác định** trước hoặc sau thao tác. Migration phải dùng các lệnh có phạm vi an toàn và tránh tự tạo giá trị giả không đúng nghiệp vụ.

### 5.5. Unique index và quy tắc shard-key-prefix

Đối với ranged sharded collection, các **unique index** thường phải có **toàn bộ shard key làm prefix** để MongoDB có thể cưỡng chế uniqueness trên các shard. Default `_id` index có ngoại lệ về phạm vi nếu `_id` không nằm trong shard key.

Ví dụ trước khi refine:

```javascript
// Shard key:
{ tenantId: 1 }

// Unique theo business key:
{ tenantId: 1, externalOrderId: 1 }
```

Nếu muốn refine thành:

```javascript
{ tenantId: 1, orderMonth: 1 }
```

thì unique index hiện hữu `{tenantId, externalOrderId}` **không có toàn bộ key mới làm prefix**. Đây là xung đột thiết kế phải giải quyết **trước khi refine**, không phải lý do để xóa unique index mà không có thay thế.

Cần phân tích:

1. Unique invariant nào đang được index bảo vệ?
2. Sau khi thêm shard key suffix, unique index nào còn tương thích?
3. Nếu dùng `{tenantId, orderMonth, externalOrderId}` unique, có làm mất quy tắc “externalOrderId duy nhất trong tenant xuyên mọi tháng” không?
4. Có thể chọn một refined key khác giữ được invariant không?
5. Nếu không, cần reshard theo key phù hợp hoặc thiết kế registry/proxy collection để bảo vệ global/business uniqueness?

**Index unique hợp lệ về cú pháp không có nghĩa bảo vệ đúng phạm vi nghiệp vụ**. Ví dụ thêm `orderMonth` vào khóa unique sẽ cho phép cùng mã đơn xuất hiện ở hai tháng khác nhau.

Không được chọn/refine shard key chỉ dựa vào hiệu năng mà bỏ qua uniqueness và authorization.

### 5.6. Zone sharding và chính sách lưu trú dữ liệu

Cluster có thể dùng **zones** để ràng buộc những khoảng shard key vào tập shard cụ thể; ví dụ dữ liệu `regionId:"EU"` chỉ được phân bổ trên các shard nằm trong vùng phù hợp.

Khi refine:

- Các zone ranges được định nghĩa theo key cũ có thể cần điều chỉnh/được xử lý theo quy tắc phiên bản.
- Các bound phải có hình dạng phù hợp shard key mới theo lệnh quản trị liên quan.
- Không được để thay đổi key khiến dữ liệu vi phạm chính sách residency.
- Kiểm tra các ràng buộc zone và thao tác DDL khác trước khi đổi shard key.

Phải tham khảo trình tự xử lý zone ranges **theo phiên bản MongoDB**, vì thao tác tự động mở rộng bounds hay yêu cầu chuẩn bị trước có thể khác giữa các release và trường hợp sử dụng.

### 5.7. Hashed shard keys và giới hạn liên quan

Quy tắc chung của refine vẫn là **giữ nguyên các thành phần cũ và chỉ bổ sung suffix**. Nếu key cũ chứa `"hashed"`, không được dùng refine để biến component đó thành `1` hoặc ngược lại.

Khả năng thêm suffix vào một hashed/compound shard key phải đối chiếu **cụ thể với giới hạn index và shard key của phiên bản**, thay vì suy luận từ một ví dụ ranged key.

Đặc biệt:

- **Hashed index không hỗ trợ unique constraint** trực tiếp.
- Việc refine không tự tạo uniqueness cho hashed key.
- Nếu yêu cầu chính là đổi mô hình range ↔ hashed, phải đánh giá resharding.

## 6. Một ví dụ refine từ tenant sang tenant + order

### 6.1. Trước refinement

Collection `sales.orders` sharded theo:

```javascript
{ tenantId: 1 }
```

Một tenant có nhiều đơn:

```javascript
{ tenantId: "T1", orderId: "O-100", amount: 120000 }
{ tenantId: "T1", orderId: "O-101", amount:  50000 }
{ tenantId: "T1", orderId: "O-102", amount:  88000 }
{ tenantId: "T2", orderId: "O-200", amount:  35000 }
```

Nếu chỉ phân biệt theo `tenantId`, tất cả document cùng tenant có cùng shard key value. Với tenant lớn, dữ liệu và lượng write có thể tập trung theo một khoảng key.

### 6.2. Sau refinement

Key mới:

```javascript
{ tenantId: 1, orderId: 1 }
```

Giá trị shard key của mỗi đơn nay có thêm `orderId`:

```text
(T1, O-100)
(T1, O-101)
(T1, O-102)
(T2, O-200)
```

Lợi ích tiềm năng:

- Có thêm khả năng phân biệt/split giữa các đơn cùng tenant.
- Những thao tác truy vấn/ghi có **đủ hai field** có thể target chính xác hơn theo metadata mới.
- Trong điều kiện thích hợp, data movement/balancing về sau có thể phân phối các khoảng key nhỏ hơn.

Nhưng:

- Chỉ refine **không lập tức chia đều các document T1 trên tất cả shard**.
- Query chỉ có `tenantId:"T1"` có thể phải truy cập nhiều range/chunk và có thể nhiều shard sau khi phân phối.
- Một tenant quá nóng vẫn cần đo khả năng phân bố write thực tế.
- Nếu `orderId` tăng dần, có thể phát sinh kiểu write hotspot theo đuôi range trong một phạm vi tenant; thêm suffix không tự bảo đảm cân bằng tải.

### 6.3. Query routing thay đổi như thế nào?

Trước refinement:

```javascript
db.orders.find({ tenantId: "T1" });
```

thường có thể được router hướng tới khoảng key tenant nhất định. Sau refinement, filter `tenantId` vẫn là **prefix** nên MongoDB có thể dùng nó để giới hạn phạm vi, nhưng tenant có thể đã trải trên nhiều chunk/shard.

Query:

```javascript
db.orders.findOne({
  tenantId: "T1",
  orderId: "O-101"
});
```

có **đầy đủ key mới**, giúp router có khả năng xác định range chính xác hơn. Để biết có bao nhiêu shard được chạm thật, dùng `explain()` trên workload đại diện, không suy luận chỉ từ tên index.

### 6.4. Giới hạn của refinement với tenant quá lớn

Nếu yêu cầu mới là phân bổ write của một tenant lớn đồng thời cân bằng giữa các shard, refine theo `{tenantId,orderId}` có thể hữu ích, nhưng nó vẫn giữ tenant là field đầu. Nếu workload chủ yếu chạy một key monotonically increasing trong mỗi tenant, cân nhắc liệu hashed key hoặc một thiết kế shard key khác giải quyết tốt hơn hay không.

Nếu phải bỏ `tenantId` khỏi đầu key, refine **không thể** thực hiện thay đổi đó. Cần so sánh lợi ích của **resharding** với chi phí tăng fanout cho các query tenant.

## 7. Resharding: thay đổi shard key thật sự

### 7.1. Tại sao cần resharding?

Những lý do thường gặp:

- Shard key ban đầu có cardinality thấp.
- Một vài giá trị key chiếm phần lớn dung lượng hoặc traffic.
- Mô hình query chủ đạo của ứng dụng đã thay đổi.
- Key tăng đơn điệu dẫn tới hotspot khi ghi.
- Chiến lược zone hoặc geographic residency được thiết kế lại.
- Muốn đổi từ range sang hashed hoặc thay thứ tự trường.
- Cần thay shard key cũ mà chỉ thêm suffix không đủ.

Resharding đưa collection sang **không gian shard key mới**. Nó có thể làm thay đổi đáng kể vị trí document, số chunk, số shard được query và hiệu năng các thao tác.

### 7.2. Cú pháp cơ bản

MongoDB hỗ trợ **reshardCollection** từ dòng phiên bản **5.0**. Ví dụ `mongosh`:

```javascript
sh.reshardCollection(
  "sales.orders",
  { orderId: "hashed" }
);
```

Hoặc dạng command được triển khai hỗ trợ:

```javascript
db.adminCommand({
  reshardCollection: "sales.orders",
  key: { orderId: "hashed" }
});
```

Đây là **lệnh DDL có tác động lớn**, không phải một ví dụ nên chạy tùy tiện trên collection thật. Namespace, key mới, quyền, điều kiện tính năng và các tham số tùy chọn phải được xác nhận theo phiên bản server.

### 7.3. Những thay đổi không thể thực hiện bằng refine

| Shard key hiện tại | Key mong muốn | Refine được không? | Hướng nghiên cứu |
| --- | --- | --- | --- |
| `{tenantId:1}` | `{tenantId:1,orderId:1}` | Có về hình dạng; còn cần đủ điều kiện | Refine |
| `{tenantId:1}` | `{orderId:1}` | Không | Reshard |
| `{tenantId:1}` | `{orderId:"hashed"}` | Không | Reshard |
| `{regionId:1,tenantId:1}` | `{tenantId:1,regionId:1}` | Không | Reshard |
| `{tenantId:1,orderId:1}` | `{tenantId:1}` | Không; refine không gỡ suffix | Reshard hoặc thiết kế lại |
| `{tenantId:1}` | `{regionId:1,tenantId:1}` | Không; thêm tiền tố chứ không phải suffix | Reshard |

Đánh dấu “hướng reshard” trong bảng không phải lời cam kết mọi key mới đều được server chấp nhận: vẫn cần kiểm tra **điều kiện hỗ trợ, unique index, loại collection, dữ liệu và tài nguyên**.

### 7.4. Các giai đoạn khái niệm của resharding

Một quá trình online resharding thường gồm:

```text
Application continues reads/writes (with caveats)
                     |
                     v
       Prepare / initialize metadata
                     |
                     v
      Copy existing data to new layout
                     |
                     v
       Catch up writes during copying
                     |
                     v
      Final commit / critical section
                     |
                     v
        New shard key becomes active
                     |
                     v
            Cleanup old layout
```

Đây là **sơ đồ ý tưởng**, không phải danh sách tên state nội bộ cố định cho mọi release. Tùy phiên bản, MongoDB có cơ chế donor/recipient, temporary collection, oplog application và commit coordination khác nhau.

Điểm quan trọng là resharding:

- Đọc/copy khối lượng dữ liệu hiện tại.
- Theo dõi những ghi phát sinh trong lúc copy.
- Phải chuyển sang phân bố mới ở một thời điểm nhất quán.
- Có thể có khoảng **critical section** khiến một số thao tác bị chờ/chặn tạm thời.
- Cần khả năng rollback/abort của chính resharding operation trước khi commit trong phạm vi phiên bản hỗ trợ.

Vì vậy “online resharding” **không đồng nghĩa zero-cost hoặc bảo đảm zero interruption** cho mọi workload.

### 7.5. Sau resharding, ứng dụng phải dùng key mới

Nếu key từ:

```javascript
{ tenantId: 1 }
```

chuyển sang:

```javascript
{ orderId: "hashed" }
```

thì query `find({tenantId:"T1"})` có thể phải đi đến **nhiều shard** nếu thiếu field shard key mới, trong khi `find({orderId:"O-101"})` có thể target hiệu quả hơn.

Việc giảm hotspot ghi có thể đi kèm tăng chi phí truy vấn tenant. Cần:

- Sửa query patterns quan trọng.
- Xem index phục vụ truy vấn tenant sau resharding.
- Cập nhật những update/delete/upsert cần targeted routing theo phiên bản.
- Điều chỉnh telemetry và playbook hỗ trợ shard key mới.
- Test trên workload đọc lẫn ghi, không chỉ test việc insert.

## 8. Điều kiện hỗ trợ của resharding

### 8.1. Server version và FCV

Resharding được giới thiệu từ MongoDB **5.0**, sau đó tiếp tục có các cải tiến và thay đổi giới hạn trong các phiên bản mới.

Trước khi dùng:

1. Xác định phiên bản **`mongos`, config servers và mọi shard replica set**.
2. Kiểm tra **FCV của cluster**.
3. Xem có upgrade/downgrade đang tiến hành không.
4. Xác định deployment tự quản lý hay managed service.
5. Kiểm tra phiên bản có hỗ trợ reshard loại collection/namespace đó không.
6. Xem các thay đổi về thời gian chặn ghi, state recovery, abort/commit, zone và các tùy chọn reshard theo release.

Không nên lấy hướng dẫn cho MongoDB 8.x áp dụng nguyên xi lên cluster 5.x, hoặc ngược lại.

### 8.2. Collection và key mới phải hợp lệ

Collection cần được sharded và ở trạng thái cho phép operation. New shard key phải đáp ứng các giới hạn về:

- Loại field và kiểu index được hỗ trợ.
- Không sử dụng những shard key field không hợp lệ như array theo giới hạn multikey.
- Cách xử lý field thiếu, `null`, dữ liệu legacy và collation.
- Unique constraint hiện có hoặc yêu cầu uniqueness của collection.
- Zone ranges và chính sách phân bố.
- Đặc tính hashed/ranged của key.
- Những hạn chế đặc thù của time-series, special collections, view hoặc những loại namespace theo phiên bản.

Một key hợp lệ về mặt cú pháp vẫn có thể **rất tệ về performance**. Ví dụ `status` chỉ có ba giá trị là shard key có cardinality thấp, thường không tạo được phân bố dữ liệu hiệu quả.

### 8.3. Unique index là ràng buộc kiến trúc

Giả sử collection đang có unique index:

```javascript
{ tenantId: 1, externalOrderId: 1 }
```

và sản phẩm đòi hỏi **mã đơn duy nhất trong từng tenant**.

Nhóm vận hành muốn reshard theo:

```javascript
{ regionId: 1 }
```

Unique index cũ không có new shard key `regionId` làm prefix. Theo các giới hạn uniqueness của sharded collection, kế hoạch **không tương thích nếu không giải quyết invariant và index phù hợp**.

Các lựa chọn:

- Chọn key mới vẫn biểu diễn được uniqueness cần bảo vệ.
- Điều chỉnh phạm vi unique khi sản phẩm cho phép, có migration rõ ràng.
- Dùng một **registry/proxy collection** có unique index thích hợp để bảo vệ business key toàn hệ thống.
- Giữ collection với key cũ hoặc tách mô hình dữ liệu thay vì reshard chỉ vì phân bố.

**Không drop unique index để qua được lệnh DDL rồi hy vọng ứng dụng tự bắt mọi trùng khi có concurrent writes.** Đây là đánh đổi tính đúng đắn dữ liệu.

### 8.4. Không có index shard key mới có sao không?

Yêu cầu về index chuẩn bị trước, index được server tạo trong quá trình chuyển đổi và các tùy chọn liên quan **khác nhau theo version và kiểu reshard**. Không áp dụng quy tắc “reshard luôn tự tạo mọi index” hoặc “bắt buộc create index trước” một cách không kiểm chứng.

Trước production:

- Liệt kê các index hiện có và hidden/unique index liên quan.
- Xác định new shard key index mà version yêu cầu.
- Xem thời gian/index build impact trên từng shard.
- Đo chi phí ghi bổ sung của index mới.
- Kiểm tra lệnh preflight và thông báo lỗi trên cluster staging cùng version.

Tối thiểu, cần có kế hoạch **index phục vụ query sau reshard**, ngay cả khi thao tác DDL có thể tự chuẩn bị index shard key cơ bản.

### 8.5. Zones và placement

Nếu collection sử dụng **zone sharding**, resharding phải xem:

- Các region/tier nào phải ở shard nào?
- Zone ranges mới có tương thích key mới không?
- Có cần cung cấp zone ranges cho operation trong những phiên bản hỗ trợ?
- Có tạm thời dữ liệu xuất hiện ở những recipient shard khác trong quá trình chuyển đổi hay không, và điều đó có vi phạm yêu cầu residency?
- Băng thông/data transfer giữa các vùng có bị hạn chế không?

Chính sách residency là yêu cầu **bảo mật và tuân thủ**, không chỉ yêu cầu hiệu năng. Nếu cần giữ dữ liệu trong một vùng nhất định, nên có review của chủ sở hữu dữ liệu trước khi reshard.

### 8.6. DDL, balancer và các hoạt động cluster đang diễn ra

Resharding có thể tương tác với:

- Chunk migration/balancer.
- Các thao tác DDL khác (create/drop/rename/index).
- Transaction kéo dài.
- Oplog retention và replication lag.
- Backup/PITR, change streams và tài nguyên của cluster.
- Metadata updates trong config servers.

Tùy phiên bản, một số thao tác được phối hợp tự động, một số bị chặn và một số không được hỗ trợ khi reshard đang chạy. Đừng tự suy ra rằng có thể chạy mọi DDL song song chỉ vì cluster vẫn đọc/ghi online.

## 9. Vì sao resharding cần nhiều tài nguyên?

### 9.1. Copy dữ liệu và network

Resharding phải tạo ra một phân bố dữ liệu mới theo shard key mới. Nếu một phần lớn document đổi vị trí, cluster phải truyền dữ liệu qua network và ghi lại lên recipient shards.

Ví dụ minh họa:

```text
Collection size:       2 TiB
Current distribution:  Shard A 1.3 TiB
                       Shard B 0.4 TiB
                       Shard C 0.3 TiB

Proposed new key:      { orderId: "hashed" }
```

Không thể suy ra thời gian reshard chỉ bằng 2 TiB / băng thông lý thuyết. Tổng chi phí còn phụ thuộc:

- Dữ liệu thực sự cần copy.
- Tốc độ read/write của shards.
- Network và disk IOPS.
- Index build.
- Transaction/majority commit.
- Tốc độ ghi trong thời gian reshard và backlog cần catch-up.
- Chunk placement và tài nguyên tạm.

### 9.2. Dung lượng lưu trữ tạm thời

Quá trình chuyển đổi có thể cần **thêm dung lượng** để giữ bản phân bố/tập dữ liệu mới và các cấu trúc tạm liên quan trước khi dọn dữ liệu cũ.

Do đó không nên reshard khi các shard đã gần đầy disk. Phải lập capacity plan cho **peak disk usage**, kể cả index, oplog và khoảng an toàn cho công việc đang chạy.

Một quy tắc dự phòng cố định “chỉ cần thêm 10%” hoặc “luôn phải gấp đôi ở mọi shard” đều có thể sai. Tính headroom theo **phân bố mới dự kiến, size từng shard, version và workflow thực tế**.

### 9.3. CPU, cache, oplog và replication

Resharding cần scan/copy tài liệu, áp dụng các ghi phát sinh và xây dựng cấu trúc liên quan. Nó cạnh tranh với workload ứng dụng về:

- CPU để xử lý BSON, routing, index.
- WiredTiger cache.
- Disk reads/writes và checkpoint.
- Network giữa shards.
- Tốc độ sao chép oplog và khả năng secondary bắt kịp.
- Tài nguyên transaction hoặc DDL coordinator.

Nếu write rate đang rất cao, khối lượng thay đổi cần catch-up có thể lớn; quá trình reshard vì vậy có thể kéo dài hoặc gây áp lực lên secondary.

### 9.4. Critical section và latency người dùng

Ngay cả khi hệ thống hỗ trợ **online resharding**, giai đoạn cuối chuyển đổi có thể cần một khoảng phối hợp mà một số read/write hoặc DDL bị chặn/chờ.

Hậu quả ở ứng dụng có thể là:

- P99 latency tăng.
- Tăng server selection/command timeout.
- Một số transaction phải retry.
- Throughput tạm giảm.
- Operation log/monitoring ghi nhận trạng thái chuyển đổi.

Đây là lý do runbook cần **định nghĩa SLO**, thời điểm triển khai, rollback/abort criteria và người chịu trách nhiệm, không chỉ chọn một câu lệnh rồi chờ.

## 10. Refine và reshard có tác động đến truy vấn như thế nào?

### 10.1. Targeted query so với scatter-gather

MongoDB `mongos` cố gắng gửi query tới shard phù hợp theo shard key và điều kiện query. Nếu không xác định được vùng khóa, router có thể phải gửi query tới nhiều shard.

Ví dụ sau reshard sang `{orderId:"hashed"}`:

```javascript
// Có shard key mới; có cơ hội target.
db.orders.findOne({ orderId: "O-100" });

// Chỉ có tenantId; có thể scatter-gather.
db.orders.find({ tenantId: "T1" });
```

Nếu 90% traffic vẫn là “liệt kê đơn của tenant T1”, key mới có thể khiến phần lớn query phải đi qua nhiều shard, tăng network và merge cost.

Không chỉ quan tâm write distribution; query fanout có thể là chi phí lớn hơn phần lợi ích.

### 10.2. Index của shard key và index phục vụ query

Một collection sharded theo `orderId` vẫn có thể có index:

```javascript
{ tenantId: 1, createdAt: -1 }
```

để cải thiện truy vấn tenant *trên từng shard*. Nhưng index này **không tự giúp router biết đúng shard nào chứa tenant** nếu query thiếu shard key. Query có thể vẫn fan out, chỉ là mỗi shard đọc dữ liệu hiệu quả hơn.

Phân biệt:

- **Shard key**: quyết định phân bố và routing.
- **Secondary indexes**: tăng tốc truy vấn tại các shard liên quan.

Chỉ tạo index không biến một query thiếu shard key thành targeted query.

### 10.3. Write routing, upsert và thao tác một document

Sau khi đổi shard key, các lệnh:

```javascript
updateOne(...)
deleteOne(...)
findOneAndUpdate(...)
upsert: true
```

có thể có yêu cầu định tuyến khác nhau tùy phiên bản MongoDB và query filter. Đặc biệt, upsert có thể cần thông tin shard key hoặc có những hành vi mới ở các release gần đây.

Trước reshard, cần kiểm tra **mọi write path**, không chỉ query đọc:

1. API có biết new shard key không?
2. Filter có đủ field để target theo quy tắc phiên bản không?
3. Nếu không có field key, operation có được hỗ trợ hay phải phân tán tới nhiều shard?
4. Unique indexes có bảo đảm chống trùng khi concurrent upsert không?
5. Có script nhập dữ liệu hoặc background worker dùng filter cũ không?

**Không đoán quy tắc định tuyến theo ví dụ của một phiên bản khác**. MongoDB đã thay đổi hỗ trợ update/upsert trong sharded collections theo thời gian.

### 10.4. Thay đổi giá trị shard key ở document là bài toán khác

MongoDB có những khả năng cập nhật **giá trị** shard key trên document với điều kiện và giới hạn theo phiên bản. Nhưng đó **không phải refine shard key và cũng không phải resharding**:

- Update giá trị shard key: thay field của **một document**.
- Refine: đổi **định nghĩa shard key** bằng cách thêm suffix.
- Reshard: đổi **định nghĩa và phân bố collection** theo key mới.

Không dùng updateMany để thay field shard key rồi coi toàn collection đã được reshard.

## 11. Thiết kế kế hoạch preflight trước khi đổi key

### 11.1. Bước 1: mô tả vấn đề bằng số liệu

Ví dụ:

```text
P95 list-orders latency:        280 ms
P99 list-orders latency:        2.4 s
Shard A write utilization:      92%
Shard B write utilization:      35%
Shard C write utilization:      28%
Tenant T1 share of writes:      64%
Scatter-gather share:           18%
```

Các số trên chỉ là **dữ liệu giả định** minh họa cách diễn đạt vấn đề. Một kế hoạch có thể nhắm:

- Giảm hot-shard write utilization.
- Cân bằng data size/chunk.
- Giữ P95/P99 query trong SLO.
- Giảm scatter-gather.
- Không làm mất uniqueness hoặc residency invariant.

Nếu không có baseline, sau thay đổi khó biết reshard đã giúp hay làm xấu hệ thống.

### 11.2. Bước 2: đo candidate shard keys

Với mỗi candidate:

```javascript
{ tenantId: 1, orderId: 1 }
{ orderId: "hashed" }
{ regionId: 1, tenantId: 1 }
```

hỏi:

- Cardinality?
- Tần suất cùng một giá trị?
- Monotonicity/hotspot?
- Các query phổ biến có field tương ứng?
- Có nhiều document thiếu key không?
- Unique constraints đang tồn tại?
- Có field key nào thường thay đổi không?
- Có cần zones/residency?
- Ước lượng chunk sizes/data movement?

Trong các phiên bản MongoDB hỗ trợ, lệnh **`analyzeShardKey`** và query sampling có thể giúp phân tích candidate key trên workload. Việc sử dụng tính năng này, quyền và cú pháp cần kiểm tra theo release; không xem kết quả phân tích là chứng minh chắc chắn hiệu năng sau migration.

### 11.3. Bước 3: khảo sát cấu trúc dữ liệu

Ví dụ kiểm tra một collection cụ thể:

```javascript
const sales = db.getSiblingDB("sales");

// Lưu ý: có thể tốn tài nguyên trên collection lớn;
// chỉ chạy sau khi đánh giá phạm vi/chi phí.
const sample = sales.orders.find(
  {},
  {
    _id: 1,
    tenantId: 1,
    orderId: 1,
    regionId: 1
  }
).limit(20).toArray();

printjson(sample);
```

Kiểm tra tỷ lệ thiếu `orderId` bằng aggregation mẫu:

```javascript
sales.orders.aggregate([
  { $sample: { size: 1000 } },
  {
    $group: {
      _id: { $type: "$orderId" },
      documents: { $sum: 1 }
    }
  },
  { $sort: { documents: -1 } }
]);
```

`$sample` là một cách khảo sát ban đầu, **không bảo đảm phát hiện mọi document lỗi**. Với quyết định production, cần kiểm tra toàn bộ dữ liệu theo quy trình phù hợp, có thống kê schema và xem số lượng document legacy.

Không làm thay đổi dữ liệu thật chỉ để “đủ field” mà chưa có hợp đồng nghiệp vụ.

### 11.4. Bước 4: kiểm tra metadata và index

Trong `mongosh` có quyền phù hợp:

```javascript
sh.status();

const sales = db.getSiblingDB("sales");
printjson(sales.orders.getIndexes());
```

Đội DBA có thể xem metadata config collection và distribution bằng công cụ/lệnh được hỗ trợ theo phiên bản. Không sửa trực tiếp các collection `config` để thay shard key.

Tập trung trả lời:

- Collection hiện sharded theo pattern gì?
- Có unique index nào?
- Index nào hỗ trợ refined key?
- Có zone range nào?
- Có chunks jumbo/hot ranges không?
- Cluster có đang chạy resharding hoặc DDL khác không?

### 11.5. Bước 5: điều kiện resource và SLO

Trước reshard:

- Còn đủ **disk headroom trên từng recipient**.
- Network giữa shards đủ cho data movement.
- Replica set healthy và oplog window/replication lag ở mức an toàn.
- Không có backup, migration, index build lớn xung đột lịch trình.
- Có cách quan sát progress, errors và duration.
- Có runbook cho timeout/abort/khôi phục.
- Có checkpoint xác nhận ứng dụng hoạt động tốt sau switch.

Refine ít data movement hơn vẫn cần preflight: index build lớn có thể tốn I/O; metadata update và các ràng buộc có thể khiến operation thất bại.

## 12. Thực hành refine trên sharded cluster thử nghiệm

### 12.1. Phạm vi an toàn

**Yêu cầu:** một **sharded cluster test riêng**, `mongosh` kết nối tới `mongos`, và quyền `shardCollection`/`createIndex`/`refineCollectionShardKey`. Không chạy phần DDL này trên cluster production hoặc shared staging chỉ để học.

Tên database test:

```text
mongo_shardkey_row266_lab
```

Nếu database/collection đã tồn tại với dữ liệu của người khác, **không tái sử dụng**; chọn một môi trường thử nghiệm cô lập đã được cấp quyền, không tự drop namespace để làm mới.

### 12.2. Kết nối tới `mongos`

```bash
mongosh "mongodb://mongos.example.internal:27017/"
```

URI là placeholder: thay hostname/TLS/authentication theo môi trường.

```javascript
sh.status();
printjson(db.adminCommand({ hello: 1 }));
```

Kiểm tra rằng kết nối đúng router của sharded cluster test. Nếu thiếu quyền, dừng trước thao tác DDL.

### 12.3. Chuẩn bị collection demo chưa có dữ liệu

Chỉ chạy khi chắc chắn namespace không tồn tại và thuộc về bạn:

```javascript
const lab = db.getSiblingDB("mongo_shardkey_row266_lab");
const name = "orders_refine_demo";

if (lab.getCollectionNames().includes(name)) {
  throw new Error("Namespace đã tồn tại; không ghi đè bài test.");
}

lab.createCollection(name);
const orders = lab.getCollection(name);

// Index hỗ trợ shard key ban đầu.
orders.createIndex(
  { tenantId: 1 },
  { name: "tenant_shard_key" }
);

// Shard collection khi còn trống.
sh.shardCollection(
  "mongo_shardkey_row266_lab.orders_refine_demo",
  { tenantId: 1 }
);
```

Một số môi trường/phiên bản có thể tự tạo supporting index khi shard một collection trống; đoạn trên tạo rõ để học cấu trúc. Không coi mọi lỗi DDL là do thiếu index: còn các điều kiện quyền, FCV, namespace và cluster state.

### 12.4. Thêm các document riêng của lượt thực hành

```javascript
const runId = "row266-" + new ObjectId().toHexString();
const tenantA = runId + "-T1";
const tenantB = runId + "-T2";

const docs = [
  {
    _id: new ObjectId(),
    runId,
    tenantId: tenantA,
    orderId: "O-100",
    status: "NEW"
  },
  {
    _id: new ObjectId(),
    runId,
    tenantId: tenantA,
    orderId: "O-101",
    status: "PAID"
  },
  {
    _id: new ObjectId(),
    runId,
    tenantId: tenantB,
    orderId: "O-200",
    status: "PAID"
  }
];

printjson(orders.insertMany(docs));
printjson(orders.find({ runId }).toArray());
```

Chỉ ba document không đủ đo hiệu năng sharding hay chứng minh balancing. Mục đích là minh họa thay đổi **định nghĩa shard key**, không phải benchmark phân bố chunk.

### 12.5. Tạo index hỗ trợ refined key

```javascript
printjson(orders.getIndexes());

orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { name: "tenant_order_refined" }
);
```

Tạo index trước để đáp ứng precondition quan trọng của refine. Với dữ liệu thật, index build có thể chiếm tài nguyên và cần được lên lịch riêng.

### 12.6. Thực hiện refinement

```javascript
sh.refineCollectionShardKey(
  "mongo_shardkey_row266_lab.orders_refine_demo",
  { tenantId: 1, orderId: 1 }
);
```

Nếu cluster/test version phù hợp và mọi điều kiện đáp ứng, metadata shard key của collection chuyển sang compound key có suffix `orderId`.

**Không** kỳ vọng sau lệnh:

- Ba document demo lập tức nằm trên ba shard khác nhau.
- Các chunk được cân lại ngay lập tức.
- Tốc độ query tự động cải thiện.
- Index unique được tự thêm.
- Những document thiếu `orderId` được sửa tự động theo nhu cầu nghiệp vụ.

### 12.7. Quan sát sau refinement

```javascript
sh.status();
printjson(orders.getIndexes());

// Query có đầy đủ key refined.
printjson(
  orders.findOne({
    tenantId: tenantA,
    orderId: "O-101"
  })
);

// Query chỉ có prefix cũ vẫn có ý nghĩa.
printjson(
  orders.find({ tenantId: tenantA }).toArray()
);
```

Nếu muốn khảo sát kế hoạch routing:

```javascript
printjson(
  orders.find({
    tenantId: tenantA,
    orderId: "O-101"
  }).explain("queryPlanner")
);
```

Kế hoạch hiển thị có thể khác nhau theo phiên bản và phân bố chunks. Với ba document, chưa thể kết luận key mới tốt hơn cho workload thực.

### 12.8. Dọn document demo an toàn

Chỉ khi chắc chắn `runId` và danh sách `docs` đúng với phiên test này:

```javascript
print("database=" + lab.getName());
print("runId=" + runId);

const owned = orders.find(
  { runId },
  { _id: 1, tenantId: 1, orderId: 1, runId: 1 }
).toArray();

printjson(owned);

for (const doc of owned) {
  const result = orders.deleteOne({
    _id: doc._id,
    tenantId: doc.tenantId,
    orderId: doc.orderId,
    runId
  });
  print(doc.orderId + ": deleted=" + result.deletedCount);
}

print("remaining=" + orders.countDocuments({ runId }));
```

Việc xóa các document **không hoàn tác refinement**. Collection, index và sharding metadata vẫn còn. Nếu cần thu hồi namespace của cluster test, dùng quy trình DDL của môi trường được cấp quyền và xác minh không có người khác sử dụng. **Không chạy `dropDatabase()` hoặc sửa trực tiếp collection `config` để dọn ví dụ.**

## 13. Thực hành resharding: chuẩn bị một collection riêng

### 13.1. Không thử reshard trên collection refinements đang phục vụ người khác

Vì resharding có thể di chuyển dữ liệu và tạm thời ảnh hưởng read/write, phần này chỉ là **bài thực hành tùy chọn** trên sharded cluster cô lập, có dung lượng dư và không phục vụ ứng dụng thật.

Không cần chạy `reshardCollection` để học ý tưởng; đọc các giai đoạn và hoạch định trước là đủ khi không có môi trường cô lập.

### 13.2. Tạo collection demo riêng

```javascript
const lab = db.getSiblingDB("mongo_shardkey_row266_lab");
const reshardName = "orders_reshard_demo";

if (lab.getCollectionNames().includes(reshardName)) {
  throw new Error("Namespace reshard demo đã tồn tại.");
}

lab.createCollection(reshardName);
const reorders = lab.getCollection(reshardName);

reorders.createIndex(
  { tenantId: 1 },
  { name: "tenant_key" }
);

sh.shardCollection(
  "mongo_shardkey_row266_lab.orders_reshard_demo",
  { tenantId: 1 }
);

const reshardRunId = "row266-reshard-" + new ObjectId().toHexString();

reorders.insertMany([
  {
    _id: new ObjectId(),
    runId: reshardRunId,
    tenantId: reshardRunId + "-T1",
    orderId: "O-301",
    status: "NEW"
  },
  {
    _id: new ObjectId(),
    runId: reshardRunId,
    tenantId: reshardRunId + "-T2",
    orderId: "O-302",
    status: "PAID"
  }
]);
```

Không có unique index phụ trên `{tenantId, orderId}` trong ví dụ để tránh đặt thêm invariant cần đánh giá khi reshard sang key mới. Trên production, unique indexes là thành phần bắt buộc của preflight, không được bỏ qua.

### 13.3. Chuyển sang hashed shard key

Sau khi xác nhận cluster/FCV hỗ trợ và tuân thủ quy trình DDL của môi trường test:

```javascript
sh.reshardCollection(
  "mongo_shardkey_row266_lab.orders_reshard_demo",
  { orderId: "hashed" }
);
```

Khác refine, lệnh này yêu cầu **chuyển sang phân bố theo hash của `orderId`**. Với dữ liệu nhỏ, toàn bộ operation có thể hoàn tất nhanh và không thể hiện rõ chi phí sản xuất; với collection lớn, chi phí có thể đáng kể.

Không được kỳ vọng thao tác này sửa nội dung field `tenantId` hoặc `orderId` trong document. Nó thay **cách collection được phân mảnh**.

### 13.4. Xem và dọn dữ liệu demo

```javascript
sh.status();
printjson(reorders.getIndexes());

printjson(
  reorders.find({ runId: reshardRunId }).toArray()
);
```

Khi cần dọn record:

```javascript
const owned = reorders.find(
  { runId: reshardRunId },
  { _id: 1, runId: 1, orderId: 1 }
).toArray();

printjson(owned);

for (const doc of owned) {
  printjson(
    reorders.deleteOne({
      _id: doc._id,
      orderId: doc.orderId,
      runId: reshardRunId
    })
  );
}

print("remaining=" + reorders.countDocuments({
  runId: reshardRunId
}));
```

Sharding metadata và collection vẫn tồn tại sau xóa document. Không coi dọn dữ liệu là hoàn tác resharding; việc thu hồi những tài nguyên DDL phải do người quản lý cluster thực hiện trong một runbook riêng.

## 14. Đảm bảo ứng dụng an toàn trong quá trình đổi shard key

### 14.1. Kiểm kê đường đọc và ghi

Ví dụ một service có các luồng:

```text
GET /tenants/:tenantId/orders
GET /orders/:orderId
PATCH /orders/:orderId/status
POST /orders
Worker: sync order state
Worker: expire old orders
Job: monthly reporting
```

Với mỗi luồng:

- Filter có chứa shard key cũ/new key không?
- Query có bị scatter-gather sau thay đổi không?
- Upsert có được target đúng và chống trùng bằng unique index không?
- Có dựa vào thứ tự/field key cũ để sort và paginate không?
- Có downstream job đọc dữ liệu qua pipeline cũ không?
- Có cần sửa auth/tenant scope khi key mới không còn bắt đầu bằng tenant?

Một reshard để tăng tốc `GET /orders/:orderId` có thể làm chậm nhiều lần `GET /tenants/:tenantId/orders` nếu chỉ đổi key mà không thiết kế lại truy vấn.

### 14.2. Compatibility của các bản triển khai ứng dụng

Trong thực tế, hệ thống có thể chạy nhiều version ứng dụng đồng thời trong khi rolling deployment.

Cần lên kế hoạch:

1. Version cũ có còn viết đúng dữ liệu khi shard key refined không?
2. Các request mới có đủ field suffix không?
3. Sau reshard, code cũ có thể tạo query không tối ưu hoặc bị hạn chế không?
4. Migration dữ liệu và application deployment có thứ tự thích hợp chưa?
5. Có feature flag để đổi routing/query pattern khi metadata switch không?

Không thực hiện DDL rồi mới phát hiện worker cũ dùng filter không đủ theo shard key mới.

### 14.3. Unique key và upsert đồng thời

Giả sử mã đơn phải unique theo tenant:

```javascript
{
  tenantId: "T1",
  externalOrderId: "E-100"
}
```

Nếu new shard key không tương thích unique index `{tenantId, externalOrderId}`, các request upsert cạnh tranh có thể làm thay đổi tính đúng đắn hoặc DDL bị từ chối.

Không có giải pháp “dùng upsert rồi mong MongoDB sẽ không bao giờ tạo trùng” khi thiếu unique constraint thích hợp. Phải thống nhất **routing + business uniqueness + idempotency** trước khi đổi key.

### 14.4. Change streams và các consumer dữ liệu

Nếu ứng dụng có change streams, Debezium hoặc một đồng bộ hóa khác, cần kiểm tra giới hạn và khả năng resume trong lúc reshard theo phiên bản MongoDB.

Đừng mặc định mọi resume token, transaction hoặc tailing workflow đều không bị ảnh hưởng qua mọi release. Chuẩn bị:

- Lưu checkpoint.
- Theo dõi lỗi/resume và backlog.
- Có khả năng khởi động lại/đối soát.
- Giám sát oplog window trong thời gian thao tác.

Nếu một consumer quan trọng bị lỗi trong lúc migration, bản thân reshard thành công cũng chưa có nghĩa toàn bộ hệ sinh thái ứng dụng đã an toàn.

## 15. Quy trình triển khai production: từ kế hoạch đến xác nhận

### 15.1. Giai đoạn A — Thiết kế và review

- Chỉ rõ pain point và KPI cần cải thiện.
- Thu thập các candidate shard keys.
- Phân tích cardinality, skew, growth, hotspot và query routing.
- Phân loại yêu cầu **refine** hay **reshard**.
- Kiểm kê unique constraints, zones, đặc tính dữ liệu.
- Review với DBA/SRE, team ứng dụng và chủ sở hữu nghiệp vụ.

Kết quả cần có là một **quyết định kiến trúc được đo lường**, không chỉ một lệnh `mongosh`.

### 15.2. Giai đoạn B — Staging/preflight

- Dựng môi trường tương đương version/FCV/topology.
- Dùng dữ liệu và tỷ lệ tải đại diện, có bảo vệ dữ liệu nhạy cảm.
- Kiểm tra supporting indexes và lỗi dữ liệu legacy.
- Kiểm tra tất cả read/write paths.
- Chạy thử với kịch bản update, upsert, transaction và unique conflict.
- Đo duration, peak disk, network, CPU và latency.
- Xác định rủi ro DDL/zone constraints.

Không kết luận performance production từ ví dụ vài document trên cluster test.

### 15.3. Giai đoạn C — Chuẩn bị rollback/abort

Với **refine**:

- Không có thao tác “gỡ suffix” đơn giản để quay về shard key cũ.
- Lên kế hoạch sửa query/index nếu performance kém.
- Nếu thực sự cần key cũ, phải đánh giá resharding hoặc phương án phục hồi tương ứng.

Với **reshard**:

- Tìm hiểu khả năng abort khi operation **chưa commit**, theo phiên bản.
- Sau khi commit sang key mới, không mặc định có một cú pháp “undo” tức thì.
- Phục hồi có thể đòi hỏi **một resharding khác**, thay đổi ứng dụng hoặc khôi phục theo runbook.
- Backup là lớp bảo vệ dữ liệu quan trọng nhưng không phải cách rollback kiến trúc shard key tức thời khi hệ thống đang ghi liên tục.

Đặt rõ **điểm trước/đang/sau commit** để tránh dùng nhầm hành động abort/rollback.

### 15.4. Giai đoạn D — Triển khai có giám sát

Theo dõi:

| Metric | Nguyên nhân phải quan sát |
| --- | --- |
| Progress/state của resharding hoặc refine DDL | Biết thao tác đang ở đâu, có lỗi hay không |
| Per-shard CPU/disk/cache | Phát hiện nghẽn tài nguyên |
| Disk headroom của donor/recipient | Tránh đầy disk giữa chừng |
| Network throughput | Đánh giá data movement và backlog |
| Oplog window/replication lag | Đảm bảo secondary theo kịp |
| P95/P99 read/write latency | Kiểm tra SLO ứng dụng |
| Error rate và timeouts | Phát hiện ảnh hưởng tới client |
| Chunk/range distribution | Xem phân bố thực tế sau thay đổi |
| Scatter-gather và targeted query share | Kiểm tra routing có đúng kỳ vọng |
| Unique conflicts/data correctness | Đảm bảo invariant không bị phá |

Đặt cảnh báo và người chịu trách nhiệm xử lý sự cố trước khi bắt đầu.

### 15.5. Giai đoạn E — Xác minh sau chuyển đổi

Không chỉ kiểm tra “lệnh DDL trả success”. Cần:

1. Xác nhận **metadata shard key mới**.
2. Xác nhận ứng dụng vẫn đọc/ghi đúng dữ liệu.
3. Kiểm tra dữ liệu và business key ở mức phù hợp.
4. Kiểm tra query plans đại diện.
5. Đo phân bố dữ liệu/traffic theo từng shard.
6. Kiểm tra replication lag và cache/disk ổn định.
7. Xác nhận consumer, backup và change streams tiếp tục hoạt động.
8. Chỉ kết luận mục tiêu đạt khi KPI cải thiện theo thời gian sau migration.

Đối với refine, có thể cần quan sát thêm balancer/chunk distribution trong một khoảng thời gian vì metadata đổi **không có nghĩa physical redistribution ngay**.

## 16. Các vấn đề thường gặp và cách xử lý

| Triệu chứng | Khả năng nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Refine báo không có index hỗ trợ | Chưa có supporting index đúng pattern | Tạo/kiểm tra index hợp lệ trên môi trường phù hợp |
| Refine báo new key không hợp lệ | Thiếu prefix cũ, đảo thứ tự hoặc đổi key type | Dùng suffix-only hoặc đánh giá reshard |
| Refine thất bại do uniqueness | Unique index không tương thích key refined | Thiết kế lại invariant/index trước DDL |
| Refine thành công nhưng dữ liệu vẫn lệch | Refine không tự tái phân phối ngay | Quan sát chunk/balancer, đánh giá placement |
| Refine xong query tenant chậm hơn | Tenant trải nhiều chunk/shard, query thiếu suffix | Kiểm tra routing/index và workload |
| Reshard thất bại ở preflight | Key/namespace/FCV/index/zone không phù hợp | Đọc lỗi và đối chiếu docs theo version |
| Reshard kéo dài | Dữ liệu lớn, write churn, disk/network bottleneck | Đo progress, capacity, backlog, chọn cửa sổ triển khai |
| Reshard tăng latency | Copy/commit coordination/critical section | Monitoring và quản lý tải theo runbook |
| Ghi bị timeout khi chuyển đổi | Routing/topology/critical phase hoặc vấn đề tải | Xử lý lỗi driver/idempotency, không retry vô hạn |
| Sau reshard nhiều scatter-gather | Query còn dựa key cũ | Sửa query, index và/hoặc xem lại key selection |
| Vẫn còn hotspot | Key mới skew/monotonic hoặc workload hot document | Phân tích phân bố, contention và cardinality |
| Secondary lag tăng | Write load/reshard data movement | Theo dõi oplog window, disk/network và capacity |
| Data residency không đúng kỳ vọng | Zones/placement chưa được thiết kế đúng | Kiểm tra zone ranges và quy định tuân thủ |
| Dữ liệu legacy thiếu suffix | Key cardinality kém hoặc lỗi theo phiên bản | Migration có kiểm soát và schema validation |
| Muốn “undo” refine bằng `dropIndex` | Index không phải shard key metadata | Không làm; lập kế hoạch reshard hoặc remediation |
| Muốn “undo” reshard bằng `shardCollection` | Sai loại thao tác | Xem runbook phục hồi/reshard lại |

## 17. Những nhầm lẫn nguy hiểm

### 17.1. “Refine giúp thay mọi shard key”

Sai. Refine chỉ **thêm suffix**, không bỏ, không đổi thứ tự hoặc đổi các component cũ. Muốn key khác căn bản phải đánh giá reshard.

### 17.2. “Refine xong là dữ liệu cân bằng ngay”

Sai. Thay metadata không tương đương physical redistribution tức thì. Key dài hơn có thể mở khả năng phân chia thêm, nhưng phân bố thực tế phải được đo.

### 17.3. “Reshard online nên không ảnh hưởng ứng dụng”

Sai. Online resharding vẫn có chi phí data copy, index, oplog apply, commit coordination và có thể chặn/chờ ở giai đoạn cuối. Tác động thực tế phụ thuộc phiên bản và workload.

### 17.4. “Đổi shard key chỉ cần thêm index”

Sai. Index là cấu trúc truy vấn, còn shard key là metadata/routing của collection. Cần lệnh refine/reshard đúng loại.

### 17.5. “Chỉ cần chọn hashed là hết hotspot”

Không hẳn. Hashed có thể phân tán các giá trị khác nhau nhưng không giải quyết hai writer tranh **cùng một document**, không bảo vệ uniqueness và có thể làm query range/tenant fanout hơn.

### 17.6. “Thay unique `{tenantId,orderId}` bằng unique `{tenantId,month,orderId}` không đổi nghiệp vụ”

Sai. Hai khóa unique bảo vệ phạm vi khác nhau. Key có thêm month cho phép cùng orderId lặp giữa các tháng trong một tenant. Phải xác định business invariant trước.

### 17.7. “Reshard là backup và rollback”

Sai. Resharding thay cấu trúc phân bố, không thay backup. Sau commit, việc quay lại có thể đòi một thao tác reshard khác hoặc recovery có kế hoạch.

### 17.8. “Một shard nhiều data nghĩa shard key sai”

Không thể kết luận chỉ từ data size. Cần xem data size, chunk distribution, write/read hotspots, workload, balancer health và capacity từng shard. Có trường hợp một shard lớn hơn là chủ đích của zone placement hoặc khác biệt về hardware.

### 17.9. “Reshard xong là mọi query cũ còn target một shard”

Sai. Query routing phụ thuộc **key mới**. Query chỉ có old shard key có thể fan out; cần kiểm tra explain/monitoring sau migration.

### 17.10. “Thao tác thêm field orderId vào từng document là refine”

Sai. Đó chỉ là **migration dữ liệu**. Refine phải thay metadata shard key bằng command được hỗ trợ.

## 18. Câu hỏi thực hành và bài tập thiết kế

### Bài A. Xác định thao tác phù hợp

Với key hiện tại:

```javascript
{ tenantId: 1, regionId: 1 }
```

Hãy phân loại mỗi key mong muốn là **refine về hình dạng**, **phải reshard** hay **cần nghiên cứu giới hạn khác**:

```javascript
// A
{ tenantId: 1, regionId: 1, orderId: 1 }

// B
{ regionId: 1, tenantId: 1 }

// C
{ tenantId: 1 }

// D
{ tenantId: 1, regionId: 1, orderMonth: 1, orderId: 1 }

// E
{ tenantId: "hashed", regionId: 1 }
```

Gợi ý: A và D giữ nguyên toàn bộ prefix cũ, thêm suffix; B/C/E không phải refine.

### Bài B. Tenant lớn làm nóng một shard

Collection đang shard theo `{tenantId:1}`. Một tenant T1 chiếm 70% writes, nhưng 90% read queries là:

```javascript
db.orders.find({
  tenantId: "T1",
  status: "PAID"
}).sort({ createdAt: -1 });
```

Hãy đánh giá:

1. Refine thành `{tenantId:1,orderId:1}` có lợi gì?
2. Có thể ảnh hưởng thế nào đến query chỉ dùng tenant?
3. Reshard thành `{orderId:"hashed"}` có thể ảnh hưởng route đọc ra sao?
4. Nên đo KPI nào trước và sau?
5. Nếu có unique `{tenantId:1,externalOrderId:1}`, việc đổi key bị ràng buộc gì?

### Bài C. Unique business ID và reshard

Ứng dụng muốn mỗi `externalOrderId` **chỉ xuất hiện một lần trong một tenant, xuyên mọi tháng**. Key mới đề xuất:

```javascript
{ tenantId: 1, monthBucket: 1 }
```

Một developer đề xuất unique index:

```javascript
{ tenantId: 1, monthBucket: 1, externalOrderId: 1 }
```

Giải thích vì sao index này **không bảo đảm invariant xuyên tháng**, dù nó có shard key làm prefix. Đề xuất ít nhất một hướng thiết kế giữ invariant, ví dụ key khác hoặc registry với unique key phù hợp.

### Bài D. Refine hoàn tất nhưng distribution không đổi

Sau `refineCollectionShardKey`:

```text
Shard A: 800 GB
Shard B: 120 GB
Shard C:  90 GB
```

Hãy trả lời:

- Điều này có đủ kết luận refine đã thất bại không?
- Vì sao metadata shard key đổi không đồng nghĩa data copy?
- Cần xem chunk/range distribution, balancer và workload nào?
- Khi nào cân nhắc reshard hoặc cải thiện cluster capacity?

### Bài E. Resharding trong giờ cao điểm

Cluster có 2 TiB dữ liệu, replica lag đang tăng, disk trên một shard chỉ còn 12%, và backup chuẩn bị bắt đầu. Nhóm muốn reshard ngay để giảm hotspot.

Hãy liệt kê:

- Những rủi ro capacity/latency/retention?
- Điều kiện nào khiến nên hoãn?
- Các số liệu cần thu trước khi quyết định?
- Lệnh `reshardCollection` có nên được coi là “không downtime” không?
- Runbook cần xác định việc abort trước commit và xử lý sau commit như thế nào?

### Bài F. Vòng đời ứng dụng

Hệ thống triển khai rolling update gồm hai phiên bản service:

```text
Service v1: updateOne({_id, tenantId}, ...)
Service v2: updateOne({_id, tenantId, orderId}, ...)
```

Collection sắp refine từ `{tenantId:1}` thành `{tenantId:1,orderId:1}`.

Hãy phân tích các điều kiện router, targeted operations, uniqueness và tương thích theo **MongoDB version**. Vì sao cần thử cả v1/v2 trong lúc triển khai thay vì chỉ test service mới?

## 19. Tài liệu tham khảo chính thức

Các điều kiện rất nhạy với phiên bản MongoDB và loại deployment. Trước khi thay production, tra đúng bộ tài liệu của **release/FCV đang chạy**:

- [Shard Keys — MongoDB Manual](https://www.mongodb.com/docs/manual/core/sharding-shard-key/) — vai trò và lựa chọn shard key.
- [Refine a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-refine-a-shard-key/) — quy trình refinement và giới hạn.
- [refineCollectionShardKey command](https://www.mongodb.com/docs/manual/reference/command/refineCollectionShardKey/) — cú pháp và yêu cầu lệnh.
- [sh.refineCollectionShardKey()](https://www.mongodb.com/docs/manual/reference/method/sh.refineCollectionShardKey/) — helper trong `mongosh`.
- [Reshard a Collection](https://www.mongodb.com/docs/manual/core/sharding-reshard-a-collection/) — quá trình và cân nhắc resharding.
- [reshardCollection command](https://www.mongodb.com/docs/manual/reference/command/reshardCollection/) — cú pháp, tùy chọn và giới hạn theo phiên bản.
- [sh.reshardCollection()](https://www.mongodb.com/docs/manual/reference/method/sh.reshardCollection/) — helper resharding.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — unique index trong các mô hình dữ liệu.
- [Sharding Analyze Shard Key](https://www.mongodb.com/docs/manual/core/sharding-analyze-shard-key/) — phân tích candidate key và workload ở phiên bản hỗ trợ.
- [Zone Sharding](https://www.mongodb.com/docs/manual/core/zone-sharding/) — quy tắc phân bố theo zone.
- [Sharding Production Considerations](https://www.mongodb.com/docs/manual/core/sharded-cluster-requirements/) — xem các yêu cầu vận hành và topology phù hợp release.

## 20. Kết luận

**Refine shard key** và **resharding** đều giúp MongoDB thích nghi khi workload thay đổi, nhưng không thể dùng thay thế nhau. Refine **giữ nguyên toàn bộ shard key cũ và chỉ thêm suffix**, cần supporting index và các điều kiện về dữ liệu/uniqueness; nó thay metadata nhưng **không tự tái phân phối ngay toàn bộ document**. Resharding cho phép chọn **một shard key mới** và tổ chức lại dữ liệu, đổi lại là chi phí copy, indexing, oplog, tài nguyên và khả năng ảnh hưởng latency trong quá trình chuyển đổi.

Để chọn đúng, hãy bắt đầu từ **mục tiêu hiệu năng và bất biến nghiệp vụ**: key mới có thực sự giảm skew/hotspot không, query có bị scatter-gather nhiều hơn không, unique index và zone constraints có còn đúng không, ứng dụng đã tương thích chưa? Trước mọi thay đổi, cần kiểm tra **MongoDB version, FCV, loại collection, supporting indexes, dữ liệu legacy, cluster capacity và runbook**. Sau lệnh thành công, vẫn phải đo phân bố, routing, replication và mức đúng đắn dữ liệu.

**Nguyên tắc cốt lõi:** chỉ *refine* khi có thể giữ prefix cũ và bổ sung suffix; dùng *resharding* khi cần thay đổi bản chất của shard key, và luôn coi đây là một quyết định kiến trúc có kiểm chứng chứ không phải một câu lệnh DDL đơn lẻ.
