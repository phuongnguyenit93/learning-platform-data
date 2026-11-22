# Duy trì tính nhất quán giữa các bản biểu diễn cùng dữ liệu trong NoSQL

## 1. Vì sao thiết kế theo truy vấn thường tạo ra nhiều bản dữ liệu?

Trong NoSQL, dữ liệu thường được **tổ chức theo những cách ứng dụng cần đọc và ghi**, thay vì mặc định chỉ có một cấu trúc chuẩn hóa dùng cho mọi truy vấn. Để một màn hình phản hồi nhanh, hệ thống có thể:

- Lưu sản phẩm gốc trong một collection tài liệu.
- Đưa một số trường sản phẩm vào bộ nhớ đệm (cache) để đọc nhanh.
- Tạo một bản tìm kiếm có trường đã chuẩn hóa hoặc vector embedding.
- Nhúng tên và giá sản phẩm vào dòng hàng của đơn để ghi lại lịch sử giao dịch.
- Duy trì các bộ đếm hoặc bảng tổng hợp theo danh mục, ngày hoặc người bán.

Những cách lưu này làm cùng một thông tin xuất hiện ở nhiều nơi. Ưu điểm là **đọc đúng mẫu truy vấn nhanh hơn**; rủi ro là **các bản biểu diễn có thể không còn đồng bộ**.

Giả sử sản phẩm `P101` có tên và giá như sau:

```json
{
  "productId": "P101",
  "name": "Sổ tay bìa cứng",
  "priceVnd": 120000,
  "category": "stationery",
  "active": true,
  "version": 7
}
```

Ứng dụng sử dụng các bản biểu diễn:

```text
                         +------------------------+
                         | MongoDB: products      |
                         | P101, version=7        |
                         | priceVnd=120000        |
                         +------------------------+
                            |       |        |
                 đồng bộ    |       |        | tạo ảnh chụp lúc mua
                            v       v        v
                +---------------+ +---------------+ +---------------------+
                | Redis cache   | | Search index  | | Order snapshot      |
                | product:P101  | | catalog:P101  | | order.items[].price |
                +---------------+ +---------------+ +---------------------+
                      |                 |
                      v                 v
                Chi tiết sản phẩm    Kết quả tìm kiếm
```

Khi giá sản phẩm đổi từ **120.000** lên **145.000 VND**, câu hỏi không chỉ là “ghi vào MongoDB thế nào?” mà còn là:

1. Cache và search index phải thay đổi ra sao?
2. Nếu một lần cập nhật thành công ở MongoDB nhưng thất bại ở search index thì sao?
3. Nếu hai lần cập nhật đến hệ tìm kiếm **ngược thứ tự**, dữ liệu có bị quay về giá cũ không?
4. Trong bao lâu người dùng có thể thấy giá cũ?
5. Giá trong **đơn đã thanh toán** có cần thay đổi theo giá mới không?

Đây là bài toán **duy trì tính nhất quán giữa các bản biểu diễn cùng dữ liệu** (*consistency across denormalized representations*).

## 2. Phân biệt bản sao, bản dẫn xuất và ảnh chụp lịch sử

Không phải hai giá trị giống nhau ở hai nơi đều phải được cập nhật giống nhau mãi mãi. Trước tiên cần xác định **ý nghĩa của mỗi bản biểu diễn**.

| Bản biểu diễn | Mục đích | Có cần phản ánh dữ liệu hiện tại? |
|---|---|---|
| `products` trong MongoDB | Nguồn quản lý tên, giá và trạng thái sản phẩm | Có; là nguồn có thẩm quyền cho các trường này |
| `product:P101` trong Redis | Cache phục vụ trang chi tiết | Có; có thể trễ trong giới hạn cho phép |
| `catalog:P101` trong search index | Tìm và lọc danh mục nhanh | Có; thường cập nhật bất đồng bộ |
| Tổng số sản phẩm theo danh mục | Read model/aggregate cho dashboard | Có; có thể trễ theo SLA |
| `orders.items[].unitPriceAtPurchase` | Đơn giá tại thời điểm đặt hàng | **Không**; phải giữ lịch sử giao dịch |

**Điểm quan trọng:** `unitPriceAtPurchase` và `products.priceVnd` có thể bằng nhau khi tạo đơn, nhưng sau đó mang **ngữ nghĩa khác nhau**. Cập nhật đơn cũ mỗi khi giá sản phẩm đổi sẽ làm sai lịch sử.

Ta có thể chia dữ liệu thành ba nhóm:

- **Source of truth (nguồn có thẩm quyền):** nơi ứng dụng quyết định giá trị hiện tại của một thuộc tính nghiệp vụ.
- **Projection/materialized view (bản dẫn xuất phục vụ đọc):** dữ liệu biến đổi từ nguồn để trả lời một nhóm truy vấn cụ thể, có thể được xây lại từ nguồn hoặc từ log sự kiện đủ tin cậy.
- **Immutable snapshot (ảnh chụp bất biến):** ghi nhận thông tin tại một thời điểm như giá mua, địa chỉ giao hàng, điều khoản hợp đồng. Không đồng bộ theo giá trị hiện tại, trừ khi có một nghiệp vụ sửa lịch sử được kiểm soát riêng.

Lỗi thiết kế thường bắt đầu khi nhóm phát triển gọi tất cả chúng chung là “bản sao” và áp cùng một chính sách cập nhật.

## 3. Chọn chủ sở hữu dữ liệu theo từng trường

Một hệ thống có nhiều collection/service không nhất thiết phải có một database duy nhất sở hữu mọi trường. Điều cần rõ ràng là **mỗi giá trị nghiệp vụ có nguồn có thẩm quyền**.

Ví dụ:

| Trường hoặc giá trị | Chủ sở hữu | Bản biểu diễn dẫn xuất |
|---|---|---|
| Tên/mô tả/giá niêm yết sản phẩm | Catalog service, collection `products` | Cache chi tiết, search index |
| Tồn kho có thể bán | Inventory service hoặc hệ tồn kho được chỉ định | Nhãn “còn hàng” trên trang, cache/filter tìm kiếm |
| Giá đã chốt trong đơn | Order service, document `orders` | Hóa đơn, lịch sử đơn hàng |
| Tổng doanh thu theo ngày | Được tính từ giao dịch đủ điều kiện | Dashboard/analytics |
| Quyền đọc tài liệu | Identity/authorization service hoặc hệ được giao quản lý ACL | Search index và cache metadata quyền |

Không nên để cả catalog, search worker và cache job cùng “chỉnh” giá hiện tại một cách độc lập. Nếu ba đường ghi có thể quyết định ba giá trị khác nhau, hệ thống không biết nên tin ai khi xảy ra xung đột.

Một nguyên tắc khả dụng:

> **Một trường nghiệp vụ có một nguồn quyết định; nhiều bản phục vụ đọc chỉ phản ánh quyết định đó.**

Nguyên tắc này không loại trừ những mô hình có nhiều writer hoặc CRDT; nhưng nếu nghiệp vụ cần nhiều writer thì phải xác định **quy tắc giải quyết xung đột**, không được mặc định đồng bộ tự xảy ra.

## 4. “Nhất quán” cần được định nghĩa theo yêu cầu thực tế

Một số nhóm yêu cầu:

### 4.1. Nhất quán mạnh ở điểm quyết định nghiệp vụ

Khi xử lý đặt hàng, hệ thống không được cho hai đơn cùng bán số lượng tồn kho cuối nếu nghiệp vụ yêu cầu “không bán quá hàng”. Khi chuyển tiền, không được xác nhận hai lần ghi nợ vượt hạn mức.

Những bất biến như vậy cần được bảo vệ bởi thao tác nguyên tử, điều kiện ghi, transaction hoặc giao thức điều phối thích hợp **tại nguồn có thẩm quyền**. Việc search index cập nhật nhanh hay chậm không thể thay thế phép kiểm tra tồn kho lúc chốt đơn.

### 4.2. Eventual consistency cho read model

Sau khi thay đổi giá ở nguồn, bản tìm kiếm có thể giữ giá cũ vài giây, sau đó hội tụ về giá mới khi sự kiện đồng bộ được xử lý thành công.

Đây là **eventual consistency**, nhưng từ “eventual” không có nghĩa chắc chắn tự sửa sau mọi lỗi. Cần có hàng đợi bền vững, retry, phát hiện sự kiện kẹt và cơ chế đối soát để đạt hội tụ trên thực tế.

### 4.3. Read-your-writes trong trải nghiệm người dùng

Người quản trị sửa tên sản phẩm rồi tải lại ngay trang chi tiết và mong thấy tên mới. Nếu trang đọc Redis/search index đang trễ, họ có thể tưởng thao tác lưu thất bại.

Có thể đáp ứng yêu cầu này bằng cách trả **giá trị mới từ nguồn** sau ghi, hoặc đọc nguồn có thẩm quyền cho màn hình vừa cập nhật. Một phương án khác là dựa trên **version barrier**: chỉ trả khi projection đã bắt kịp version vừa ghi, nếu không thì fallback.

### 4.4. Độ mới tính theo thời gian và sai lệch nghiệp vụ

Không có một mức trễ phù hợp mọi trường:

- Tên hiển thị sản phẩm: có thể chấp nhận chậm vài giây tùy sản phẩm.
- Thống kê lượt xem: có thể chậm vài phút.
- Trạng thái thu hồi quyền truy cập: thường phải được thực thi ngay ở đường đọc có thẩm quyền.
- Giá thanh toán và tồn kho cuối: phải được xác thực tại thời điểm xác nhận đơn.

Vì vậy, cần ghi rõ **mỗi read model chấp nhận chậm tối đa bao lâu**, khi nào fallback, và ai chịu trách nhiệm xử lý khi vượt ngưỡng. Không nên gọi mọi mức độ trễ là “ổn vì NoSQL eventual consistency”.

## 5. Vì sao ghi trực tiếp hai nơi dễ mất nhất quán?

Một cách triển khai tưởng đơn giản:

```text
API cập nhật sản phẩm:
  1. UPDATE MongoDB products
  2. SET Redis product cache
  3. UPDATE search index
  4. Trả HTTP 200
```

Đây là **dual-write/multi-write từ ứng dụng**. Các bước độc lập, không nằm trong một transaction chung xuyên MongoDB, Redis và search engine.

### Tình huống lỗi 1: ghi nguồn thành công, ghi bản dẫn xuất thất bại

```text
T0: products[P101].price = 120000, version = 7
T1: MongoDB cập nhật price = 145000, version = 8   OK
T2: Mạng tới search index bị lỗi                  FAILED
T3: HTTP handler timeout

Kết quả:
  MongoDB:      145000 / v8
  Search index: 120000 / v7
```

Client có thể retry, nhưng retry API có thể tạo thao tác không mong muốn nếu request không có cơ chế idempotency. Nếu handler trả thành công ngay sau MongoDB, search index cũng có thể trễ mà không có cơ chế theo dõi.

### Tình huống lỗi 2: sự kiện đến ngược thứ tự

```text
Nguồn: v7 -> v8 (145000) -> v9 (138000)

Worker A gửi v8, mạng chậm
Worker B gửi v9, thành công
Worker A gửi lại v8, thành công muộn

Nếu chỉ ghi đè vô điều kiện:
Search index cuối cùng có thể là v8, sai so với nguồn v9
```

Chỉ có retry là **chưa đủ**. Hệ thống phải xử lý **thứ tự và version** để một bản cũ không thay thế bản mới.

### Tình huống lỗi 3: cập nhật một phần trường

Search index có tên `"Sổ tay A5"` nhưng giá mới lại bị ghi bằng event cũ. Nếu nhiều pipeline thay riêng các trường mà không có quy tắc version/ownership, một record có thể trở thành **hỗn hợp của nhiều thời điểm**.

### Tình huống lỗi 4: xóa nguồn nhưng còn cache/index

Sản phẩm bị ẩn hoặc tài liệu bị thu hồi quyền, nhưng các bản tìm kiếm vẫn trả dữ liệu cũ. Với dữ liệu nhạy cảm, đây không còn là vấn đề UI chậm mà có thể là **lỗ hổng kiểm soát truy cập**.

Vì các lỗi này, với dữ liệu quan trọng không nên coi một chuỗi `save()` tới nhiều hệ là một transaction.

## 6. Các chiến lược đồng bộ phổ biến

| Chiến lược | Cách hoạt động | Ưu điểm | Giới hạn |
|---|---|---|---|
| Cập nhật đồng bộ trong cùng transaction | Ghi nguồn và bản dẫn xuất trong một phạm vi transaction | Có thể đảm bảo cùng commit/rollback | Chỉ áp dụng trong phạm vi mà datastore thực sự hỗ trợ |
| Transactional outbox | Ghi nguồn + thông điệp outbox nguyên tử, worker phát tới bản đọc | Không làm mất “ý định đồng bộ” khi process chết | Cần relay, idempotency, retry và quản lý thứ tự |
| Change Data Capture (CDC) | Theo dõi các thay đổi đã commit từ nguồn | Hạn chế thay đổi ứng dụng, nguồn sự kiện từ database | Phải quản lý resume/offset, snapshot, schema và hành vi capture |
| Write-through cache | Ghi nguồn và cache trong một luồng xử lý | Dữ liệu cache có thể cập nhật nhanh | Không tự có transaction xuyên hệ; vẫn có race/failure |
| Cache-aside + invalidation | Ghi nguồn, xóa cache; khi đọc miss thì tải lại | Đơn giản, thường thực dụng | Có race và cửa sổ stale nếu không kiểm soát |
| TTL/cache expiration | Cache tự hết hạn rồi được nạp lại | Giới hạn thời gian tồn tại thông thường của giá trị cũ | Không đủ cho yêu cầu mạnh hoặc thu hồi quyền ngay |
| Đối soát định kỳ | So sánh bản dẫn xuất với nguồn rồi sửa | Phát hiện lệch do sự cố bị bỏ sót | Chỉ sửa sau một độ trễ; cần xác định cách so sánh |
| Tính lại/bổ sung backfill | Xây lại projection từ nguồn hoặc lịch sử sự kiện | Phục hồi, migration, đổi schema | Tốn tài nguyên; phải xử lý cập nhật đang diễn ra |

Trong thực tế, hệ đáng tin cậy thường **kết hợp nhiều cách**: nguồn dữ liệu chuẩn, transactional outbox hoặc CDC để phát thay đổi, consumer idempotent, cache invalidation và đối soát nền.

## 7. Transactional outbox: ghi nguồn và “ý định cập nhật” cùng nhau

Giải pháp cốt lõi: **không yêu cầu request API cập nhật đồng thời MongoDB và search index**. Thay vào đó, commit **dữ liệu nguồn** và **một bản ghi sự kiện chờ phát (outbox)** trong một transaction của chính nguồn.

```text
                    Cùng transaction tại database nguồn
                         +-----------------------+
API update P101 --------> | 1. UPDATE products    |
                         | 2. INSERT outbox      |
                         +-----------------------+
                                    |
                                    | commit thành công
                                    v
                            Outbox relay / CDC
                                    |
                              Event broker
                               /         \
                              v           v
                       Cache projector   Search projector
                              |           |
                              v           v
                            Redis     Search index
```

Nếu transaction **commit**, cả cập nhật sản phẩm và bản ghi sự kiện đều tồn tại. Nếu transaction **rollback**, không có thay đổi nguồn được coi là hoàn tất và không có thông điệp outbox cho thay đổi đó.

**Điều kiện rất quan trọng:** tính nguyên tử trên áp dụng khi **nguồn và outbox được ghi trong cùng một transaction được datastore hỗ trợ**. Trong MongoDB, transaction nhiều document/collection yêu cầu triển khai phù hợp như replica set hoặc sharded cluster. Một MongoDB standalone không được cấu hình cho transaction nhiều document sẽ không thể sao chép nguyên vẹn mô hình này.

Nếu ứng dụng gom sự kiện pending trong cùng document nguồn để tận dụng tính nguyên tử một document, cần kiểm soát kích thước document và cách dọn sự kiện; **không để mảng outbox tăng vô hạn**.

### Ví dụ cấu trúc nguồn và sự kiện

```javascript
// products (document nguồn)
{
  _id: "P101",
  name: "Sổ tay bìa cứng A5",
  priceVnd: 145000,
  category: "stationery",
  active: true,
  version: 8,
  updatedAt: ISODate("2026-11-14T08:00:00Z")
}

// outbox (record chờ phát)
{
  _id: "product:P101:v8",
  aggregateType: "Product",
  aggregateId: "P101",
  aggregateVersion: 8,
  eventType: "ProductChanged",
  eventSchemaVersion: 1,
  occurredAt: ISODate("2026-11-14T08:00:00Z"),
  state: {
    productId: "P101",
    name: "Sổ tay bìa cứng A5",
    priceVnd: 145000,
    category: "stationery",
    active: true
  }
}
```

**Vì sao sự kiện có version và đủ trạng thái?**

- `aggregateId` xác định thực thể mà event thuộc về.
- `aggregateVersion` giúp phân biệt sự kiện mới/cũ cho cùng sản phẩm.
- `eventSchemaVersion` cho phép consumer xử lý sự tiến hóa cấu trúc sự kiện.
- `state` chứa những trường projector cần để tạo bản đọc; “full state” phù hợp giúp consumer **upsert** mà không phải đoán kết quả từ một chuỗi patch bị thiếu sự kiện. Không nhất thiết phải đưa mọi trường nhạy cảm của source vào event.
- `_id` của event tạo cơ sở cho deduplication; vẫn cần cơ chế xử lý request lặp ở phía nghiệp vụ.

Ví dụ này giả định **một luồng thay đổi version tuần tự cho một sản phẩm**. Với các nguồn ghi cạnh tranh, phải thiết kế cách cấp version và transaction sao cho không có hai lần commit cùng một version của cùng product.

## 8. Ví dụ MongoDB: cập nhật có điều kiện và phát outbox

Trước hết, đặt một document nguồn trong collection `products`:

```javascript
db.products.insertOne({
  _id: "P101",
  name: "Sổ tay bìa cứng",
  priceVnd: 120000,
  category: "stationery",
  active: true,
  version: 7,
  updatedAt: ISODate("2026-11-13T08:00:00Z")
});
```

Ta muốn cập nhật giá và tên khi version hiện tại đúng bằng 7. Một thao tác nguyên tử **trên một document** có thể dùng điều kiện so sánh version:

```javascript
const result = db.products.updateOne(
  { _id: "P101", version: 7 },
  {
    $set: {
      name: "Sổ tay bìa cứng A5",
      priceVnd: 145000,
      updatedAt: new Date()
    },
    $inc: { version: 1 }
  }
);

printjson(result);
```

Nếu `matchedCount = 1`, điều kiện version khớp tại thời điểm cập nhật; một thao tác cạnh tranh đã thay đổi version có thể khiến `matchedCount = 0`. Tầng nghiệp vụ cần quyết định nên đọc lại, báo xung đột hay thử lại dựa trên yêu cầu, không được ghi đè mù.

Đoạn lệnh trên **chỉ cập nhật nguồn**, chưa phải triển khai outbox. Để tạo outbox an toàn, hai thao tác phải nằm trong cùng transaction:

```text
PSEUDOCODE (MongoDB transaction trên replica set/sharded cluster thích hợp)

BEGIN TRANSACTION

  update products where (_id = "P101" AND version = 7)
    set name = "Sổ tay bìa cứng A5",
        priceVnd = 145000,
        updatedAt = timestamp
    increment version by 1

  IF updated_document_count != 1:
    ROLLBACK and report CONFLICT

  insert into outbox:
    eventId = "product:P101:v8"
    aggregateId = "P101"
    aggregateVersion = 8
    eventType = "ProductChanged"
    state = post-update fields used by projections

COMMIT with suitable durability/write concern
```

**Hai ví dụ là hai cách nhìn khác nhau:** khi triển khai outbox, không chạy `updateOne` bên ngoài transaction rồi chạy tiếp pseudo-transaction để cập nhật **lần thứ hai**. Hãy đưa chính phép cập nhật có điều kiện vào transaction với phép chèn event.

Ứng dụng thực tế còn cần:

- Transaction/session do MongoDB driver quản lý.
- Xử lý lỗi commit không rõ kết quả, retry cho lỗi tạm thời theo hướng dẫn driver.
- Request idempotency key nếu client có thể gửi lại cùng thao tác.
- Chỉ báo API thành công sau khi biết commit nguồn đã xảy ra.
- Cơ chế relay/outbox cleanup sao cho không mất các event chưa phát.

Một transaction trong MongoDB không tự biến việc ghi Redis hoặc search index thành một phần của cùng giao dịch ACID. Các hệ đó vẫn được cập nhật **bất đồng bộ** từ sự kiện đã commit.

## 9. CDC: lấy thay đổi từ nguồn thay vì phát event trực tiếp

**Change Data Capture (CDC)** là cách quan sát những thay đổi đã được commit trong database nguồn. Nó có thể thay thế hoặc hỗ trợ outbox relay.

Ví dụ, **MongoDB change streams** cho phép ứng dụng quan sát các thao tác insert/update/delete trên collection hoặc database trong những topology được hỗ trợ. Luồng thay đổi dùng cơ chế của MongoDB để stream các event; consumer cần lưu **resume token** bền vững để tiếp tục sau lỗi.

Sơ đồ:

```text
MongoDB products
       |
       | change stream (insert/update/delete)
       v
CDC consumer + saved resume token
       |
       +--> cập nhật search projection
       +--> invalidation Redis cache
       +--> metric / reconciliation state
```

**Chú ý giới hạn dữ liệu sự kiện:**

- Event thay đổi có thể chứa delta chứ không luôn có toàn bộ document ở đúng thời điểm commit.
- Tùy cách cấu hình, chế độ lấy `fullDocument` như `updateLookup` có thể trả trạng thái hiện tại lúc lookup, **không nhất thiết đúng ảnh chụp ngay tại event** nếu nhiều thay đổi xảy ra sát nhau.
- Không giả định resume token có thể được dùng vô hạn: khả năng resume phụ thuộc việc lịch sử thay đổi còn khả dụng và các điều kiện của triển khai.
- Khi đổi schema, đổi collection hoặc backfill, consumer phải có quy tắc đồng bộ phù hợp.

Vì thế, **outbox ghi trạng thái nghiệp vụ/version chủ động** và **CDC từ thao tác storage** là hai kỹ thuật có điểm mạnh khác nhau. Cần chọn theo khả năng của nguồn và yêu cầu đối với thứ tự, metadata và replay.

## 10. Consumer phải idempotent: xử lý lại không được làm sai dữ liệu

Hệ thống phát event thường chọn giao hàng **at-least-once**: sự kiện có thể đến **hơn một lần** do retry, consumer restart hoặc lỗi ở bước xác nhận.

Giả sử consumer nhận:

```text
ProductChanged(P101, version=8, price=145000)
ProductChanged(P101, version=8, price=145000)  // lặp
```

Nếu consumer thực hiện thao tác “đặt toàn bộ trạng thái sản phẩm ở version 8” thì việc lặp có thể không làm khác giá trị. Nhưng nếu event là “tăng tổng doanh thu 145000”, xử lý hai lần sẽ cộng hai lần.

**Idempotency** có nghĩa cùng một thông điệp logic xử lý lại không làm hệ thống thay đổi sai thêm. Một số cách:

1. Dùng `eventId` để ghi nhận những event đã xử lý.
2. Lưu `lastAppliedVersion` theo từng thực thể trong read model.
3. Dùng upsert trạng thái tuyệt đối thay vì cộng dồn không kiểm soát, nếu nghiệp vụ cho phép.
4. Với bộ đếm/sự kiện phát sinh, dùng deduplication gắn với event ID ở phạm vi nguyên tử thích hợp.

### Quy tắc apply theo version

Với bản tìm kiếm của `P101`, có thể diễn đạt:

```text
apply(event):
    current = searchProjection.get(event.aggregateId)

    if current exists and current.version >= event.aggregateVersion:
        return ALREADY_APPLIED_OR_STALE

    searchProjection.conditionalUpsert(
        id      = event.aggregateId,
        version = event.aggregateVersion,
        fields  = transform(event.state),
        only_if_stored_version_is_lower = true
    )
```

Đây là **pseudocode về hành vi mong muốn**, không phải API chung cho mọi search engine.

**Điểm rất quan trọng:** việc đọc version rồi ghi ở hai request độc lập **không đủ an toàn** nếu hai worker có thể ghi đồng thời. Phải bảo đảm điều kiện “chỉ apply nếu version mới hơn” được kiểm soát nguyên tử bởi datastore đích, hoặc bảo đảm chỉ một worker được phép ghi một thực thể tại một thời điểm với quy tắc thứ tự/khôi phục phù hợp.

Nếu search engine hỗ trợ cơ chế external versioning hoặc compare-and-set tương ứng, có thể tận dụng; nếu không, phải chọn chiến lược tránh write race khác. Dù event được chuyển đúng thứ tự trong queue, retry và các nhánh xử lý song song vẫn có thể tạo ghi đảo thứ tự khi chưa thiết kế cẩn thận.

## 11. Thứ tự sự kiện theo thực thể quan trọng hơn thứ tự toàn hệ thống

Một hệ thống có hàng triệu sản phẩm không nhất thiết cần thứ tự tuyệt đối cho mọi sự kiện. Thường điều cần giữ là:

\[
\text{P101: }v_7 \rightarrow v_8 \rightarrow v_9
\]

Trong khi sự kiện của `P202` có thể chạy song song, không cần chờ `P101`.

Một broker phân vùng có thể định tuyến các event theo `productId` để những event của cùng sản phẩm đi vào cùng partition. Nhưng thứ tự của broker **không thay thế** version và idempotency, bởi còn tồn tại reprocessing, chuyển worker, thao tác ghi bất đồng bộ đến downstream và các đợt backfill.

### Khi thiếu một version

Giả sử search index đang ở `v7` và nhận `v9` trước `v8`. Nếu `v9` mang **full state**, việc áp dụng trực tiếp `v9` có thể hợp lệ cho read model “trạng thái hiện tại”; khi `v8` tới sau, nó bị bỏ qua vì cũ hơn.

Nếu event chỉ mang **delta** như “tăng tồn kho 2” hoặc “đổi một trường có phụ thuộc vào bản trước”, bỏ qua `v8` có thể làm kết quả sai. Khi đó cần phát hiện lỗ hổng version, đợi/replay event bị thiếu, hoặc nạp lại snapshot mới nhất từ nguồn.

**Full-state event và delta event có yêu cầu áp dụng khác nhau**. Không nên dùng một logic replay cho cả hai.

### Hành vi khi ghi thất bại

Nếu consumer không áp dụng được `v8` do search engine tạm thời lỗi, không được âm thầm đánh dấu `v8` hoàn tất rồi mất dấu. Cần retry có giới hạn/backoff, lưu trạng thái thất bại, và cảnh báo khi quá ngưỡng. Một event lỗi không sửa được có thể chuyển vào **dead-letter queue (DLQ)** để phân tích và xử lý có kiểm soát.

## 12. Cache: mất hiệu lực, cập nhật và những race condition

**Cache-aside** là mô hình phổ biến:

```text
GET product:P101
    |
    +-- cache hit --> trả cache
    |
    +-- cache miss --> đọc MongoDB --> ghi Redis --> trả kết quả
```

Khi cập nhật sản phẩm, một phương án là **invalidate cache**:

```text
UPDATE MongoDB products[P101]
COMMIT
     |
     +--> event ProductChanged(P101, v8)
                   |
                   v
            DEL product:P101
```

Lần đọc tiếp theo thấy cache miss sẽ nạp trạng thái mới từ nguồn. Tuy nhiên, invalidation không tự bảo đảm không bao giờ trả dữ liệu cũ.

### Race giữa cache miss và invalidation

```text
T0 Reader A cache miss
T1 Reader A bắt đầu đọc nguồn version 7
T2 Writer commit nguồn version 8
T3 Invalidation xóa cache P101
T4 Reader A ghi lại giá trị version 7 vào cache
```

Kết quả: cache có thể bị **nạp lại bằng giá trị cũ sau khi đã xóa**.

Những cách giảm rủi ro tùy yêu cầu:

- TTL phù hợp: giới hạn khoảng thời gian stale thông thường.
- Cache versioned value hoặc key versioned: chỉ cho ghi cache nếu version không cũ hơn bản đang có; việc so sánh phải nguyên tử nếu có cạnh tranh.
- Request coalescing/điều phối đọc và điền cache để giảm race.
- Sau khi ghi, ưu tiên đọc thẳng nguồn cho request cần read-your-writes.
- Với dữ liệu nhạy cảm hoặc yêu cầu nhất quán mạnh, **không lấy cache làm nơi quyết định cuối cùng**.

### Cache key mang version

Có thể lưu:

```text
product:P101:v8 -> {name, priceVnd, ...}
product:P101:currentVersion -> 8
```

Đọc version hiện tại rồi đọc theo key version giúp tránh overwrite cùng một key bằng bản cũ, nhưng chỉ đúng khi **currentVersion** được cập nhật theo thứ tự thích hợp và các điểm đọc/ghi được điều phối. Nó còn có chi phí quản lý TTL và xóa những key version cũ. Đây là kỹ thuật, không phải cơ chế nhất quán tự động.

## 13. Đọc ngay sau khi ghi: tránh giao diện “đã lưu nhưng vẫn cũ”

Giả sử admin cập nhật sản phẩm P101 từ version 7 lên version 8, nhưng trang quản trị đọc từ search index đang ở version 7.

Các phương án:

**Phương án A — trả tài liệu đã cập nhật từ nguồn.** API trả payload mới và version 8 sau commit. UI dùng giá trị đó cho vùng hiển thị vừa sửa. Các trang công khai khác có thể vẫn đọc projection theo SLA.

**Phương án B — đọc nguồn theo quyền.** Trang chi tiết dành cho admin lấy MongoDB làm nguồn cho những trường cần nhất quán tức thời, thay vì dùng search index.

**Phương án C — chờ projection bắt kịp version.** API hoặc UI nhận `expectedVersion = 8`, chỉ coi read model đủ mới khi `projection.version >= 8`. Nếu không đạt trong timeout, dùng fallback hoặc hiển thị trạng thái đang đồng bộ.

Một API có thể trả:

```json
{
  "productId": "P101",
  "name": "Sổ tay bìa cứng A5",
  "priceVnd": 145000,
  "version": 8,
  "syncStatus": "PENDING_PROJECTION"
}
```

`syncStatus` là ví dụ hợp đồng API do ứng dụng tự thiết kế, không phải trường tự sinh của MongoDB. Nếu UI hiển thị “đã lưu”, cần xác định rõ là **đã commit nguồn** hay **đã đồng bộ mọi bản phục vụ đọc**.

## 14. Xử lý dữ liệu dẫn xuất khi thay đổi schema

Một projection được thiết kế cho truy vấn cụ thể nên có thể đổi cấu trúc khi UI/search thay đổi. Ví dụ search index cũ dùng:

```json
{
  "productId": "P101",
  "title": "Sổ tay bìa cứng",
  "priceVnd": 120000
}
```

Phiên bản mới muốn có trường `normalizedTitle` và `categoryPath`:

```json
{
  "productId": "P101",
  "title": "Sổ tay bìa cứng A5",
  "normalizedTitle": "so tay bia cung a5",
  "categoryPath": ["office", "stationery"],
  "priceVnd": 145000,
  "sourceVersion": 8
}
```

Không nên đổi mapper rồi giả định tất cả bản cũ tự chuyển đổi. Một quy trình **rebuild/backfill** có thể gồm:

1. Xác định version schema/index mới và cách biến đổi từ source.
2. Tạo read model/index mới song song, không ghi đè bản đang phục vụ.
3. Duyệt nguồn với snapshot/checkpoint phù hợp và đưa từng bản vào index mới.
4. Đồng thời ghi nhận thay đổi đang phát sinh để không bỏ sót các cập nhật trong lúc backfill.
5. Bắt kịp checkpoint hoặc version trước khi chuyển luồng đọc.
6. So sánh số lượng, bản mẫu, độ mới và quyền truy cập; chuyển luồng đọc sang index mới theo quy trình triển khai.
7. Chỉ dọn index cũ khi có đường rollback hoặc cửa sổ quan sát đủ an toàn.

Điểm khó là **đường ghi mới đang chạy trong khi dữ liệu cũ được quét lại**. Nếu backfill của version 7 ghi sau event version 8, projection có thể bị lùi. Chính sách compare-and-set theo sourceVersion cũng cần áp dụng trong bước rebuild.

## 15. Xóa, thu hồi quyền và “tombstone”

Sự kiện **xóa** đòi hỏi quan tâm nhiều hơn thay một tên hiển thị. Nếu sản phẩm bị ngừng bán hoặc tài liệu bị xóa, các bản cache/search có thể tiếp tục trả bản cũ nếu thiếu cơ chế lan truyền.

Một sự kiện:

```json
{
  "eventId": "product:P101:v10",
  "aggregateId": "P101",
  "aggregateVersion": 10,
  "eventType": "ProductDeleted",
  "deletedAt": "2026-11-14T10:00:00Z"
}
```

Một **tombstone** là dấu hiệu có version rằng thực thể đã bị xóa/ẩn. Nó giúp tránh kịch bản:

```text
v10: delete -> search xóa bản ghi
v9: update đến muộn -> search tạo lại bản ghi đã xóa
```

Nếu hệ đích xóa hoàn toàn cả bản ghi lẫn version, consumer cần một cách khác để nhớ **version tombstone** hoặc bảo đảm các event cũ không thể hồi sinh bản ghi. Quy tắc cần xét cả thời gian giữ sự kiện, replay và việc ID có thể được tái sử dụng hay không.

Với thông tin nhạy cảm, **xóa hoặc thu hồi quyền** cần được xử lý theo yêu cầu bảo mật và pháp lý, bao gồm cache, search index, bản dẫn xuất và bản sao/backup theo chính sách. Eventual consistency thông thường có thể không đáp ứng yêu cầu thu hồi ngay. Cần chặn truy cập tại đường có thẩm quyền trong khi hệ thống đang dọn dữ liệu dẫn xuất.

## 16. Đối soát: tự phát hiện và sửa bản biểu diễn bị lệch

Không một pipeline bất đồng bộ nào nên chỉ dựa vào hy vọng rằng mọi event đều được xử lý đúng. Cần thiết kế **reconciliation** (đối soát):

```text
Periodically:
  sample or scan source products
      |
      +--> compare version/hash/key fields with search index
      +--> compare cache metadata if appropriate
      |
      +--> mismatches --> repair/rebuild
      +--> missing records --> re-index
      +--> extra/deleted records --> remove or tombstone
```

### Cách phát hiện chênh lệch

- **So sánh version:** `source.version` với `projection.sourceVersion`. Nếu projection thấp hơn, có thể chưa bắt kịp.
- **So sánh checksum/hash** của các trường được projection biểu diễn: giúp phát hiện mapper lỗi ngay cả khi version được ghi bằng nhau.
- **So sánh số lượng và tập ID:** tìm phần tử bị thiếu hoặc tồn tại thừa.
- **Kiểm tra độ trễ event:** phát hiện consumer bị kẹt dù chưa có alert lỗi rõ ràng.
- **Truy vấn mẫu theo kịch bản nghiệp vụ:** kiểm tra trạng thái sản phẩm, giá, phân quyền và kết quả tìm kiếm quan trọng.

### So sánh theo cùng thời điểm

Trong khi source tiếp tục thay đổi, một phép quét “nguồn lúc 10:00” và “index lúc 10:05” có thể thấy khác nhau dù pipeline hoạt động đúng. Đối soát cần định nghĩa **mốc phiên bản/checkpoint**, khoảng trễ được phép và cách tránh kết luận sai do cập nhật đang diễn ra.

### Chính sách sửa lỗi

Nếu projection **được xây hoàn toàn từ source**, cách sửa an toàn thường là **tạo lại bản đọc từ giá trị nguồn có thẩm quyền** rồi ghi theo version mới nhất. Không sửa ngược source bằng giá trị search index. Với dữ liệu tổng hợp hoặc sự kiện nhiều nguồn, phải xác định quy tắc tái tính toán theo đúng trạng thái và thời điểm nghiệp vụ.

## 17. Monitoring và giới hạn độ trễ

Cần đo các chỉ số gắn với người dùng và trạng thái thực của pipeline:

| Chỉ số | Ý nghĩa | Dấu hiệu đáng chú ý |
|---|---|---|
| `outbox_pending_count` | Số event đã commit nhưng chưa phát/hoàn tất | Tăng liên tục |
| `oldest_pending_age` | Tuổi của event cũ nhất đang kẹt | Vượt ngưỡng cho phép |
| `consumer_lag_seconds` | Độ trễ đồng bộ từ nguồn tới read model | Tăng đột biến hoặc không giảm |
| `projection_version_gap` | Chênh version của thực thể giữa nguồn và projection | Gap kéo dài |
| `retry_count` và `dlq_count` | Lỗi và sự kiện cần xử lý thủ công | Tăng kéo dài |
| `reconciliation_mismatch_rate` | Tỷ lệ bản đọc không khớp nguồn theo định nghĩa | Tăng dù consumer không báo lỗi |
| `cache_stale_read_rate` | Tỷ lệ đọc thấy phiên bản cũ trong mẫu đo | Vượt ngưỡng trải nghiệm |
| `rebuild_progress` | Tỷ lệ index mới đã backfill và bắt kịp event | Dừng hoặc tụt lại |

Một mục tiêu dịch vụ ví dụ:

> 99% thay đổi tên/giá sản phẩm xuất hiện trên tìm kiếm trong vòng 10 giây; trường hợp vượt 60 giây phải cảnh báo và có phương án phục hồi.

Đây chỉ là **SLO minh họa**. Ngưỡng thật cần dựa vào yêu cầu nghiệp vụ, tần suất cập nhật, tải, chi phí, bảo mật và khả năng hệ thống. Đối với điều kiện chốt giá thanh toán, không nên dùng SLO của search projection thay thế việc kiểm tra giá hiện hành ở source.

## 18. Truy vấn từ nhiều bản biểu diễn: hiểu nguồn của mỗi kết quả

Một request có thể kết hợp dữ liệu từ nhiều nơi:

```text
Search index -> IDs, tên tóm tắt, category, score
Redis        -> cache trang chi tiết
MongoDB      -> giá/tồn kho/điều kiện hiện hành ở nguồn
Order store  -> giá đã chốt của đơn cũ
```

Khi ứng dụng hiện danh sách tìm kiếm, có thể cho phép một số trường trễ. Nhưng khi người dùng thêm vào giỏ hoặc chốt đơn, hệ thống cần xác minh **giá và tồn kho tại nơi có thẩm quyền**.

### Tránh trộn phiên bản trên cùng một giao diện

Nếu tên lấy từ search index v8 và giá lấy từ cache v7, người dùng thấy một bản kết hợp chưa từng là trạng thái được commit đầy đủ. Có thể:

- Trả toàn bộ các trường cần hiển thị từ một projection được cập nhật nguyên khối theo version.
- Kèm `sourceVersion` trên kết quả để phát hiện hoặc kiểm soát khác phiên bản.
- Đọc nguồn cho những vùng UI cần chính xác đồng bộ.
- Tránh ghép các trường yêu cầu cùng trạng thái từ hai nguồn không có mốc nhất quán chung.

**Không nên nhầm nhất quán giao diện với nhất quán giao dịch.** Dù người dùng thấy một snapshot đúng version, quyết định mua vẫn cần kiểm tra lại ở bước commit nghiệp vụ để tránh race với người mua khác.

## 19. Những lựa chọn không thể thay thế lẫn nhau

### 19.1. CQRS có giải quyết nhất quán tự động không?

**CQRS (Command Query Responsibility Segregation)** tách đường xử lý ghi (command) và đường đọc (query). Nó cho phép thiết kế read model theo nhu cầu truy vấn, nhưng **không tự đồng bộ dữ liệu**. Cần chọn event propagation, versioning, error recovery và nhất quán phù hợp.

### 19.2. Event sourcing có bắt buộc không?

**Event sourcing** lưu lịch sử các sự kiện nghiệp vụ làm nguồn để tái dựng trạng thái. Đây là một kiến trúc riêng, không phải điều kiện bắt buộc để duy trì search projection. Một hệ thống vẫn có thể dùng MongoDB document hiện tại làm nguồn và outbox/CDC để cập nhật các bản dẫn xuất.

Nếu dùng event sourcing, cần định nghĩa phiên bản sự kiện, replay, snapshot, tính tương thích và bất biến. Event log có thể giúp tái dựng read model, nhưng replay sự kiện cũ vào hệ ngoài có hiệu ứng phụ phải được kiểm soát.

### 19.3. CRDT có áp dụng cho tất cả trường không?

**CRDT** hỗ trợ một số kiểu dữ liệu hội tụ khi cập nhật phân tán theo quy tắc hợp nhất xác định. Một bộ đếm cộng dồn có thể phù hợp hơn một phép ghi trạng thái bất kỳ; nhưng tên sản phẩm, giá thanh toán hoặc quyền truy cập có thể cần quyết định nghiệp vụ một chiều. Không thể lấy quy tắc hợp nhất của counter rồi áp cho mọi dữ liệu.

### 19.4. Last-write-wins có luôn an toàn không?

Nếu chọn bản ghi có timestamp “mới nhất” khi đồng bộ hai writer, có thể gặp vấn đề lệch đồng hồ, sự kiện đến muộn và tình trạng mất cập nhật. **Last-write-wins** là một chính sách giải quyết xung đột có đánh đổi, không phải đảm bảo dữ liệu đúng nghiệp vụ. Với một nguồn ghi tuần tự, version do nguồn cấp thường rõ hơn timestamp do các máy khác nhau tự tạo.

## 20. Ma trận chọn giải pháp theo yêu cầu

| Nhu cầu | Mức nhất quán cần ưu tiên | Cách tiếp cận thường hợp lý |
|---|---|---|
| Hiển thị tên/mô tả sản phẩm | Có thể eventual | Cache và search projection từ source, event + đối soát |
| Tìm kiếm nhiều trường và sắp xếp | Có thể eventual theo SLO | Materialized view/index tối ưu truy vấn, cập nhật phiên bản |
| Trang admin vừa sửa sản phẩm | Read-your-writes | Trả nguồn sau ghi hoặc version barrier/fallback |
| Thống kê doanh thu theo ngày | Có thể chậm theo kỳ | Tổng hợp từ giao dịch hợp lệ, dedup và reconciliation |
| Giá đã chốt trong đơn | Giữ ảnh chụp lịch sử | Immutable snapshot của giao dịch, không cập nhật theo giá hiện tại |
| Bán món hàng cuối cùng | Cần bất biến mạnh khi commit | Kiểm tra/giảm tồn kho nguyên tử tại source, không dựa vào cache |
| Quyền xem tài liệu | Phải bảo vệ chính xác ở đường đọc | Authorization có thẩm quyền; đồng bộ ACL và thu hồi an toàn |
| Dữ liệu public cache được rộng rãi | Stale có giới hạn | TTL, invalidation, chống cache stampede |
| Đổi schema read model lớn | Không mất cập nhật trong chuyển đổi | Backfill + capture thay đổi + version + cutover |

## 21. Quy trình thiết kế một projection mới

Khi một đội muốn thêm read model để hỗ trợ truy vấn nhanh hơn, có thể thực hiện theo trình tự:

**Bước 1 — Ghi access pattern.** Cần tìm theo khóa nào, lọc/sắp xếp gì, tải và độ trễ mục tiêu bao nhiêu?

**Bước 2 — Chỉ rõ source of truth và các trường dẫn xuất.** Trường nào do service nào sở hữu, trường nào là snapshot không đổi?

**Bước 3 — Xác định hợp đồng nhất quán.** Chấp nhận stale bao lâu? Truy vấn nào cần source? Có cần read-your-writes không? Có trường bảo mật phải đồng bộ tức thời không?

**Bước 4 — Thiết kế event.** Mỗi event mang ID, aggregate ID, version, schema version, kiểu thao tác và dữ liệu tối thiểu cần thiết; xác định full-state hay delta.

**Bước 5 — Chọn đường phát tin cậy.** Transactional outbox, CDC hoặc cơ chế phù hợp với topology; không sử dụng dual-write không kiểm soát cho dữ liệu quan trọng.

**Bước 6 — Thiết kế projector.** Idempotency, version guard, thứ tự theo thực thể, retry/backoff, DLQ, xóa/tombstone và xử lý lỗi schema.

**Bước 7 — Thiết kế đọc.** UI cần lấy ở đâu để đủ mới? Khi projection trễ thì fallback ra sao? Có kiểm tra lại nguồn trước khi commit giao dịch không?

**Bước 8 — Lập kế hoạch backfill và cutover.** Xây index, bắt kịp thay đổi đang diễn ra, đối soát rồi mới chuyển lưu lượng đọc.

**Bước 9 — Theo dõi và sửa lỗi.** Đặt SLO lag, version gap, DLQ, reconciliation, cảnh báo và runbook khôi phục.

**Bước 10 — Kiểm thử tình huống hỏng.** Ngắt kết nối index sau khi commit, gửi event trùng, đảo thứ tự, crash consumer, rollback transaction, gửi delete trước update cũ và kiểm tra hành vi thực.

## 22. Bài tập tình huống

### Bài 1 — Phân biệt dữ liệu cần đồng bộ và snapshot lịch sử

Một sản phẩm `P101` đổi tên từ “Sổ tay cũ” thành “Sổ tay mới”. Dữ liệu xuất hiện trong catalog, Redis cache, kết quả tìm kiếm và ba đơn hàng đã thanh toán.

Hãy phân loại nơi nào cần phản ánh tên hiện tại, nơi nào nên giữ tên sản phẩm tại thời điểm mua. Giải thích vì sao không thể dùng một event cập nhật vô điều kiện lên tất cả nơi lưu tên.

### Bài 2 — Phát hiện lỗi dual-write

API lần lượt ghi MongoDB rồi ghi search index. MongoDB thành công nhưng HTTP request tới search index timeout. Client retry.

Hãy nêu các nguy cơ, đề xuất transactional outbox/CDC, và chỉ ra vì sao **retry đơn thuần** không đảm bảo cả tính duy nhất lẫn thứ tự của kết quả.

### Bài 3 — Event đến ngược thứ tự

Search index ở `v7`. Consumer B đã áp `v9`, sau đó consumer A nhận lại `v8`. Hãy viết quy tắc quyết định apply cho **full-state event**. Sau đó mô tả vì sao quy tắc tương tự có thể sai với **delta event** nếu bỏ qua một version ở giữa.

Gợi ý hành vi cần bảo vệ:

```text
if incoming.version <= stored.version:
    ignore
else:
    apply according to event semantics
```

Điều kiện so sánh và ghi phải được bảo đảm nguyên tử hoặc được điều phối có kiểm soát.

### Bài 4 — Cache invalidation race

Một reader đọc dữ liệu v7, writer commit v8 và xóa cache, sau đó reader ghi lại v7 vào Redis. Hãy đề xuất hai biện pháp giảm rủi ro và giải thích vì sao TTL chỉ giới hạn độ cũ, không tự loại bỏ race.

### Bài 5 — Chuyển index tìm kiếm sang schema mới

Đội search thêm `categoryPath`. Họ quét toàn bộ MongoDB để tạo index mới trong 90 phút, trong khi sản phẩm vẫn thay đổi.

Hãy thiết kế các bước backfill, capture cập nhật sau mốc bắt đầu, áp version, đối soát, chuyển alias/đường đọc và rollback. Nêu rủi ro nếu backfill v7 ghi đè event v8.

### Bài 6 — Kiểm tra độ mới và phân quyền

Một tài liệu nội bộ thuộc tenant T01 bị thu hồi khỏi nhóm `support`. Search index cập nhật ACL chậm 30 giây. Hãy chỉ ra vì sao “eventual consistency 30 giây” có thể không chấp nhận được, và cần lớp kiểm tra quyền nào tại thời điểm trả nội dung.

## 23. Kết luận

**Thiết kế theo truy vấn** trong NoSQL thường dẫn tới các dạng **denormalization, cache và materialized view** để mỗi đường đọc hiệu quả hơn. Đổi lại, cùng một thông tin có thể tồn tại ở nhiều nơi với thời điểm cập nhật khác nhau.

Để duy trì tính nhất quán một cách có chủ đích:

1. Phân biệt **nguồn có thẩm quyền, bản dẫn xuất và snapshot lịch sử**.
2. Định nghĩa mức nhất quán cần thiết cho từng thao tác và từng trường.
3. Tránh **dual-write** thiếu cơ chế phục hồi; sử dụng transaction trong phạm vi hỗ trợ kết hợp outbox/CDC cho các đích ngoài.
4. Thiết kế **event ID, version, thứ tự theo thực thể và idempotency** để replay hoặc ghi trễ không làm lùi dữ liệu.
5. Quản lý cache race, delete/tombstone, schema migration và quyền truy cập.
6. Có **quan sát độ trễ, đối soát và backfill** để phát hiện rồi sửa lệch sau sự cố.

Mục tiêu không phải ép mọi read model luôn đồng bộ tức thời bằng mọi giá, mà là **biết chính xác bản nào được phép trễ, trong bao lâu, và bằng cơ chế nào hệ thống chắc chắn hội tụ trở lại** — đồng thời giữ các quyết định nghiệp vụ quan trọng ở nguồn có khả năng bảo vệ tính đúng đắn.
