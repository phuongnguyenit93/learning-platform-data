# Ràng buộc unique index trong sharded collection của MongoDB

## 1. Bài toán đặt ra

Một ứng dụng nhiều tenant lưu tài khoản trong MongoDB. Ban đầu collection chưa phân mảnh và dùng unique index để ngăn trùng email trong mỗi tenant:

```javascript
db.accounts.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
```

Sau đó hệ thống muốn mở rộng bằng **sharding** để phân phối dữ liệu trên nhiều shard. Có thể giữ nguyên ràng buộc unique không? Nếu shard theo `tenantId` thì sao? Nếu shard theo `regionId` hoặc `createdAt` thì sao? Nếu muốn email duy nhất **toàn hệ thống**, chứ không chỉ trong từng tenant, cần thiết kế khác như thế nào?

Những câu hỏi này không chỉ liên quan hiệu năng, mà liên quan đến **tính đúng đắn của dữ liệu**. MongoDB không thể kiểm tra mọi khóa trùng trên nhiều shard theo cùng cách kiểm tra trên một collection không sharded. Cơ chế unique index ở sharded collection phải tuân theo quy tắc về **shard key**.

Sau bài học, bạn có thể:

1. Giải thích vì sao uniqueness ở cluster phân mảnh khó hơn ở một node.
2. Nhận diện điều kiện **toàn bộ shard key là tiền tố của unique index** trong ranged sharding.
3. Phân biệt unique cho một khóa ghép với unique cho từng thành phần.
4. Hiểu giới hạn của `_id` index nếu `_id` không phải shard key.
5. Phân biệt unique ranged shard key với hashed shard key.
6. Thiết kế cách bảo vệ business key nằm ngoài shard key.
7. Thực hành trên `mongos`, xem cấu hình index và xử lý xung đột đúng cách.

## 2. Unique index bảo đảm điều gì?

### 2.1. Chỉ mục duy nhất

Unique index ngăn các document có cùng khóa index trong phạm vi được MongoDB thực thi ràng buộc đó. Ví dụ:

```javascript
db.users.createIndex({ username: 1 }, { unique: true });
```

Khi một document có `username: "minh"` đã tồn tại, việc chèn thêm document với giá trị đó thường bị từ chối bởi lỗi **duplicate key** mã `11000` (thường hiển thị `E11000`).

Đối với **compound unique index**:

```javascript
db.accounts.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
```

MongoDB ngăn trùng **toàn bộ cặp** `(tenantId, emailKey)`. Không có nghĩa `tenantId` phải unique, cũng không có nghĩa `emailKey` phải unique ở mọi tenant.

| tenantId | emailKey | Có thể cùng tồn tại? |
| --- | --- | --- |
| `T1` | `an@example.test` | Bản ghi đầu tiên hợp lệ |
| `T1` | `binh@example.test` | Có, khác email |
| `T2` | `an@example.test` | Có, khác tenant |
| `T1` | `an@example.test` | Không, cặp khóa đã tồn tại |

**Điểm mấu chốt:** lựa chọn trường trong unique key là lựa chọn phạm vi của một quy tắc nghiệp vụ. Việc tạo index hợp lệ không chứng minh rằng index đó đã biểu diễn đúng mong muốn của sản phẩm.

### 2.2. Không nên nhầm unique với các ràng buộc khác

Unique index không bảo đảm:

- Field là email có định dạng hợp lệ.
- Document được tạo bởi người dùng có quyền truy cập tenant.
- Một ID tham chiếu có document đích tồn tại.
- Trạng thái được chuyển theo đúng quy trình.
- Hai request cùng email nhưng khác cách viết chữ hoa/thường được chuẩn hóa giống nhau, nếu ứng dụng chưa quy định việc đó.

MongoDB schema validation, tầng ứng dụng, quyền truy cập và transaction giải quyết những vấn đề khác; chúng phối hợp với unique index chứ không thay thế nó.

## 3. Sharding thay đổi điều gì?

### 3.1. Shard key và định tuyến dữ liệu

Một MongoDB sharded cluster lưu document trên nhiều shard, ứng dụng thường gửi truy vấn qua `mongos`:

```text
Ứng dụng / mongosh
        |
        v
      mongos
        |
        +----------+----------+
        |          |          |
        v          v          v
      Shard A    Shard B    Shard C
```

**Shard key** là field hoặc tổ hợp field được MongoDB sử dụng để phân chia và định tuyến dữ liệu. Chẳng hạn:

```javascript
{ tenantId: 1 }
```

MongoDB phân chia không gian giá trị shard key thành những chunk/range, sau đó phân bổ chunk giữa các shard. Cách phân bổ có thể thay đổi khi cân bằng dữ liệu. Tuy nhiên, mọi document có một giá trị shard key xác định đều được định tuyến tới vùng khóa tương ứng.

Không nên coi một tenant luôn được gắn cố định với một máy chủ từ đầu tới cuối; hệ thống có thể di chuyển chunk. Tính nhất quán của định tuyến theo shard key mới là đặc tính quan trọng.

### 3.2. Vì sao unique theo field khác shard key khó thực thi?

Giả sử shard key là `{tenantId:1}` nhưng ứng dụng muốn `emailKey` unique **toàn cluster**:

```javascript
{ tenantId: "T1", emailKey: "an@example.test" }
{ tenantId: "T2", emailKey: "an@example.test" }
```

Hai document có tenant khác nhau có thể được đặt ở các shard khác nhau. Unique index cục bộ trên `emailKey` tại một shard không thể tự phát hiện giá trị đã có ở shard khác.

Nếu index thay bằng `{tenantId:1,emailKey:1}`, hai document có cùng **cặp khóa** luôn có cùng giá trị `tenantId`; MongoDB có thể kiểm tra chúng trong phạm vi được định tuyến theo shard key. Đây là cơ sở của quy tắc shard-key-prefix.

## 4. Quy tắc tiền tố shard key của unique index

Đối với **ranged sharded collection**, MongoDB có thể cưỡng chế unique xuyên shard khi:

1. Index unique chính là index trên shard key.
2. Index unique ghép có **toàn bộ shard key làm tiền tố**.
3. Default `_id` index vẫn tồn tại, nhưng có **ngoại lệ về phạm vi** nếu `_id` không phải shard key.

MongoDB không cho tạo unique index tùy ý thiếu shard key prefix trên một collection đã shard theo range. Nếu collection chưa shard có unique index không tương thích, thao tác sharding collection cũng có thể bị từ chối.

### 4.1. Trường hợp shard key một field

Với shard key:

```javascript
{ tenantId: 1 }
```

| Index muốn tạo với `unique:true` | Hỗ trợ? | Điều được bảo vệ |
| --- | --- | --- |
| `{tenantId:1}` | Có | Chỉ một document cho mỗi tenant; thường quá chặt |
| `{tenantId:1,emailKey:1}` | Có | Một email cho mỗi tenant |
| `{tenantId:1,externalOrderId:1}` | Có | Một external order ID cho mỗi tenant |
| `{emailKey:1}` | Không theo quy tắc prefix | Thiếu shard key |
| `{emailKey:1,tenantId:1}` | Không | Có shard key nhưng **không ở đầu** |
| `{status:1,tenantId:1}` | Không | Shard key không phải tiền tố |

**Thứ tự field là yếu tố bắt buộc.** Có `tenantId` nằm ở đâu đó trong index không đủ; nó phải là phần đầu liên tiếp.

### 4.2. Shard key nhiều field

Với shard key:

```javascript
{ tenantId: 1, monthBucket: 1 }
```

các index phù hợp về mặt tiền tố:

```javascript
{ tenantId: 1, monthBucket: 1 }
{ tenantId: 1, monthBucket: 1, orderId: 1 }
{ tenantId: 1, monthBucket: 1, customerId: 1 }
```

Các index không chứa **toàn bộ** shard key ở đầu:

```javascript
{ tenantId: 1 }
{ tenantId: 1, orderId: 1 }
{ monthBucket: 1, tenantId: 1, orderId: 1 }
{ tenantId: 1, orderId: 1, monthBucket: 1 }
{ orderId: 1 }
```

`{tenantId,orderId}` có prefix `tenantId`, nhưng lại bỏ qua `monthBucket` vốn thuộc shard key. Nó không phải unique index hợp lệ cho sharded collection có shard key `{tenantId,monthBucket}` theo quy tắc đang xét.

### 4.3. Unique áp dụng cho **toàn bộ** tổ hợp

Giả sử index hợp lệ là:

```javascript
{ tenantId: 1, monthBucket: 1, orderId: 1 }
```

Ba document sau có thể tồn tại:

```javascript
{ tenantId: "T1", monthBucket: 202610, orderId: "O-10" }
{ tenantId: "T1", monthBucket: 202611, orderId: "O-10" }
{ tenantId: "T2", monthBucket: 202611, orderId: "O-10" }
```

Chúng không trùng toàn bộ khóa. Nếu nghiệp vụ yêu cầu mỗi `orderId` chỉ xuất hiện **một lần trong tenant bất kể tháng nào**, unique index này **chưa giải quyết yêu cầu**. Thêm `monthBucket` vào khóa unique có thể làm thay đổi phạm vi bảo vệ dù giúp index đúng quy tắc shard-key-prefix.

Đó là lý do chọn shard key phải đồng thời xem xét **business uniqueness**, không chỉ cân bằng dữ liệu.

## 5. Phân biệt unique shard key với unique compound index

### 5.1. Chỉ unique cặp tenant + email

Nếu mỗi tenant có nhiều tài khoản, shard key `{tenantId:1}` không cần unique. Có thể tạo index ghép:

```javascript
db.accounts.createIndex({ tenantId: 1 });

db.accounts.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);

// Chạy qua mongos trên namespace chính xác.
sh.shardCollection("shop.accounts", { tenantId: 1 });
```

Index ghép bảo đảm cặp tenant + email duy nhất. Nó **không bắt mọi tenant chỉ có một document**.

### 5.2. Muốn chính shard key values unique

Trong một collection cấu hình, mỗi vùng có đúng một record. Khi đó mới có thể cần unique trên chính `regionId`:

```javascript
db.regionConfig.createIndex(
  { regionId: 1 },
  { unique: true }
);

// Tham số thứ ba của sh.shardCollection yêu cầu unique shard key.
sh.shardCollection(
  "shop.regionConfig",
  { regionId: 1 },
  true
);
```

Khi yêu cầu unique shard key bằng `true`:

- Nếu collection trống, MongoDB có thể tạo unique index trên shard key nếu chưa có.
- Nếu collection đã có dữ liệu, cần tạo unique index trên shard key trước khi shard.
- Nếu một index hỗ trợ shard key đã tồn tại nhưng không unique, thao tác có thể báo lỗi.
- Một unique index `{regionId:1,emailKey:1}` **không thay thế** unique index chính trên `{regionId:1}`.

Ví dụ `shop.regionConfig` và `shop.accounts` là hai collection khác nhau minh họa hai nhu cầu nghiệp vụ khác nhau. Không bật unique shard key cho account collection có nhiều user trong cùng tenant.

## 6. Ngoại lệ quan trọng của default `_id` index

### 6.1. `_id` không phải shard key

Ở collection không sharded, `_id` unique trong collection. Tuy nhiên, **nếu một sharded collection có shard key không phải `_id`**, MongoDB chỉ cưỡng chế tính duy nhất của default `_id` index **trong từng shard**, không mặc định trên toàn bộ cluster.

Ví dụ collection sharded theo `{regionId:1}`:

```javascript
// Có khả năng thuộc shard A:
{ _id: "ACCOUNT-1", regionId: "north", emailKey: "a@example.test" }

// Có khả năng thuộc shard B:
{ _id: "ACCOUNT-1", regionId: "south", emailKey: "b@example.test" }
```

Nếu các record nằm trên những shard khác nhau, default index `_id` cục bộ có thể không ngăn giá trị `_id` bị lặp giữa các shard. Đây là **điều được tài liệu cảnh báo**, không phải cách nên cố tình tạo dữ liệu thử nghiệm.

### 6.2. Khi `_id` là shard key

Nếu shard key là `{_id:1}`, document trùng `_id` cũng trùng shard key; cơ chế định tuyến cho phép bảo vệ uniqueness theo quy tắc được hỗ trợ.

Nhưng nếu shard key là `{tenantId:1,_id:1}`, unique compound index trên `{tenantId:1,_id:1}` chỉ bảo vệ **cặp** tenant + ID. Nó không tự làm `_id` unique toàn cluster, bất kể tenant.

### 6.3. Trách nhiệm tạo ID của ứng dụng

Khi `_id` không phải shard key, MongoDB kỳ vọng ứng dụng dùng ID phù hợp để tránh trùng giữa các shard, chẳng hạn ObjectId chuẩn, UUID hoặc một chiến lược phát ID toàn hệ thống có quản lý.

Một ObjectId được sinh chuẩn có xác suất trùng rất thấp, nhưng đó là **đặc tính chiến lược sinh ID**, không phải bảo đảm của một unique index toàn cluster trên `_id` trong mô hình shard key không tương thích.

Nếu nghiệp vụ cần invariant được server cưỡng chế tuyệt đối cho một định danh độc lập shard key, hãy cân nhắc chọn shard key khác hoặc dùng registry/proxy collection như mục 9.

## 7. Hashed shard key và giới hạn unique

### 7.1. Khác biệt giữa ranged và hashed sharding

Ranged sharding dùng khoảng giá trị shard key, ví dụ:

```javascript
{ accountId: 1 }
```

Hashed sharding phân bố bằng giá trị hash:

```javascript
{ accountId: "hashed" }
```

Hashed sharding có thể cải thiện phân bố ghi khi key tăng đơn điệu, nhưng **MongoDB không cho tạo unique constraint trên hashed index** và không cho bật tùy chọn unique shard key với hashed shard key.

Một lệnh như sau là **ví dụ không được hỗ trợ**, không dùng để cấu hình:

```javascript
db.accounts.createIndex(
  { accountId: "hashed" },
  { unique: true }
);
```

Hash không tự tạo tính duy nhất theo business key. Khi yêu cầu unique toàn cluster quan trọng, cần cân nhắc shard key theo range phù hợp hoặc cơ chế registry riêng.

### 7.2. Lựa chọn shard key không chỉ nhằm cân tải

Một shard key tốt cần được đánh giá trên nhiều chiều:

| Yếu tố | Câu hỏi thiết kế |
| --- | --- |
| Phân bố | Các giá trị shard key có trải đều dữ liệu và write load không? |
| Query routing | Truy vấn quan trọng có chứa shard key để hướng đến shard đích không? |
| Uniqueness | Unique index bắt buộc có thể chứa shard key đầy đủ làm tiền tố không? |
| Cardinality | Có quá nhiều bản ghi cùng một giá trị shard key không? |
| Thay đổi key | Shard key có hay thay đổi trong vòng đời record không? |
| Khả năng tăng trưởng | Khi tăng shard và dữ liệu, quy tắc vẫn phù hợp không? |
| Resharding | Nếu đổi key trong tương lai, các unique index còn hợp lệ không? |

Không chọn hashed shard key chỉ vì mong phân bố tốt rồi mặc định MongoDB vẫn cưỡng chế được mọi unique key nghiệp vụ.

## 8. Collation, `null` và field thiếu

### 8.1. Unique index và collation

Collation quyết định cách so sánh string theo ngôn ngữ, chữ hoa/thường và dấu. Với unique index trên sharded collection, quy tắc được tài liệu MongoDB nêu ra yêu cầu **simple collation** trong trường hợp collation áp dụng cho index key cần bảo đảm uniqueness.

Vì vậy không nên sao chép một index unique case-insensitive trên collection chưa sharded sang sharded collection mà chưa xem giới hạn tương ứng.

Một cách triển khai thực dụng là chuẩn hóa khóa business trong ứng dụng:

```javascript
{
  tenantId: "TENANT-A",
  emailDisplay: "An@Example.Test",
  emailKey: "an@example.test"
}
```

Nếu shard key là `{tenantId:1}`, unique index:

```javascript
db.accounts.createIndex(
  { tenantId: 1, emailKey: 1 },
  {
    unique: true,
    collation: { locale: "simple" }
  }
);
```

bảo vệ cặp tenant + khóa email **đã chuẩn hóa**. Quy tắc chuẩn hóa phải nhất quán ở mọi writer; việc xử lý email quốc tế, Unicode và case folding cần chính sách cụ thể theo ứng dụng.

### 8.2. Missing và null

Đối với unique index, field bị thiếu có thể tham gia vào khóa index như một giá trị `null` theo quy tắc của MongoDB. Ví dụ với unique `{tenantId:1,emailKey:1}`, nhiều document cùng tenant thiếu `emailKey` có thể xung đột trên tổ hợp chứa `null`.

Nên kiểm tra ở các lớp:

- Ứng dụng xác định business key bắt buộc, không cho truyền giá trị rỗng sai quy ước.
- Collection validator có thể yêu cầu field và kiểu BSON phù hợp.
- Unique index cưỡng chế chống trùng với những document được index.
- Quy trình migration kiểm tra document legacy thiếu field trước khi bật ràng buộc.

Không coi unique index là giải pháp thay cho kiểm tra dữ liệu đầu vào.

### 8.3. Partial/sparse không tự bỏ qua quy tắc shard-key-prefix

Partial unique index chỉ kiểm soát uniqueness trong tập document khớp partial filter; sparse index có phạm vi document được index riêng. Dù vậy, chúng **không phải lối tắt** để tạo unique index trên một field không có shard key prefix ở sharded collection.

Nếu nghiệp vụ cần “email duy nhất trong các account active”, phải đồng thời thiết kế phạm vi unique, quy tắc khi khôi phục account, điều kiện shard key và các giới hạn của loại index cụ thể. Tính đúng đắn khi state thay đổi cần được thử với dữ liệu thực tế.

## 9. Khi cần unique toàn hệ thống trên field không thuộc shard key

### 9.1. Vì sao `{tenantId,emailKey}` chưa đủ?

Giả sử collection `accounts` sharded theo `{tenantId:1}`, nhưng sản phẩm đòi hỏi **không có hai account cùng email trên toàn hệ thống**, dù khác tenant.

```javascript
// Hợp lệ về quy tắc shard-key-prefix, nhưng phạm vi chưa đủ.
{ tenantId: 1, emailKey: 1 }
```

Index trên không ngăn một email xuất hiện ở `T1` và `T2`. Tạo trực tiếp unique index `{emailKey:1}` lại không đáp ứng quy tắc shard-key-prefix cho collection này.

Phải lựa chọn một thiết kế khác, không chỉ đổi thứ tự field mà vẫn giữ nguyên nghiệp vụ.

### 9.2. Phương án 1: thiết kế lại shard key

Nếu có thể shard theo `emailKey` (ranged) với unique index trên key đó, MongoDB có thể cưỡng chế uniqueness trực tiếp. Tuy nhiên, shard key theo email có thể làm truy vấn theo tenant kém thuận lợi; cần đánh giá:

- tần suất đọc và ghi theo tenant;
- phân bố giá trị và hotspot;
- khả năng route query tới shard cụ thể;
- chi phí reshard hoặc migration;
- yêu cầu giữ email ổn định hay thay đổi.

Chỉ đổi shard key khi đã đánh giá toàn bộ các yếu tố này.

### 9.3. Phương án 2: proxy hoặc registry collection

MongoDB có hướng dẫn sử dụng một collection độc lập làm **registry** cho khóa cần unique khi khóa đó không thể là shard key của collection chính:

```text
              Application
                   |
           normalizedEmail
                   |
                   v
            +-------------+
            | emailKeys   |
            | unique _id  |
            +-------------+
                   |
            nếu khóa hợp lệ
                   v
            +-------------+
            | accounts    |
            | sharded by  |
            | tenantId    |
            +-------------+
```

Ví dụ registry lưu:

```javascript
{
  _id: "an@example.test",
  accountId: ObjectId("66a000000000000000000001"),
  createdAt: ISODate("2026-11-14T01:00:00Z")
}
```

Collection chính lưu:

```javascript
{
  _id: ObjectId("66a000000000000000000001"),
  tenantId: "TENANT-A",
  emailKey: "an@example.test",
  displayName: "An"
}
```

Nếu registry là **collection không sharded** trong cùng cluster, default `_id` unique index bảo vệ email ở registry. Nếu registry cần shard, shard key của chính registry phải được chọn để unique email vẫn được cưỡng chế theo giới hạn đã nêu.

### 9.4. Phải phối hợp ghi hai collection

Chỉ chèn registry trước rồi account sau có thể tạo registry “mồ côi” khi bước thứ hai lỗi. Chèn account trước rồi registry sau cũng có thể để lại account có email không đăng ký được.

Nếu hai collection thuộc cùng MongoDB cluster có hỗ trợ giao dịch, có thể dùng **multi-document transaction** để tạo/đăng ký khóa và tạo account cùng thành công hoặc cùng rollback.

```javascript
// Node.js MongoDB driver - minh họa luồng ghi.
import { ObjectId } from "mongodb";

async function createAccount(client, database, input) {
  const session = client.startSession();
  const accountId = new ObjectId();

  try {
    await session.withTransaction(async () => {
      await database.collection("emailKeys").insertOne(
        {
          _id: input.emailKey,
          accountId,
          createdAt: new Date()
        },
        { session }
      );

      await database.collection("accounts").insertOne(
        {
          _id: accountId,
          tenantId: input.tenantId,
          emailKey: input.emailKey,
          displayName: input.displayName
        },
        { session }
      );
    });

    return accountId;
  } finally {
    await session.endSession();
  }
}
```

Ví dụ giả định `emailKeys` có unique index phù hợp (ở đây `_id` trên collection không sharded), cả hai collection ở cùng cluster, và tầng API đã xác thực tenant và chuẩn hóa input.

Trong sản phẩm thật:

1. Nếu hai request cùng đăng ký email, một request có thể nhận `E11000` từ registry; ánh xạ thành lỗi nghiệp vụ thay vì tạo account trùng.
2. Transaction không tự thay thế unique constraint; index trên registry mới là phần bảo vệ chống trùng.
3. Callback transaction có thể được driver thử lại sau một số lỗi tạm thời; không gọi dịch vụ email/thanh toán ngoài database trong callback nếu chưa có cơ chế idempotency/outbox.
4. Cần định nghĩa quy tắc đổi email, giải phóng khóa cũ, xóa mềm, tái sử dụng email và kiểm soát conflict.
5. Khi client retry một request có thể đã commit nhưng mất response, nên có idempotency key cấp nghiệp vụ.

### 9.5. Nhiều unique key độc lập

Nếu cần cả email và số điện thoại đều unique trên toàn hệ thống trong khi collection chính sharded theo tenant, có thể cần nhiều registry/proxy với index và shard key thích hợp từng khóa. Transaction phối hợp ghi các registry và document chính.

Điều này tăng độ phức tạp vận hành; vì vậy nên phân tích invariant uniqueness ngay khi thiết kế sharding, không chỉ khi hệ thống đã có hàng triệu document.

## 10. Thực hành với `mongosh` trên một sharded cluster

**Điều kiện thực hành:** có MongoDB sharded cluster thử nghiệm, URI tới `mongos`, và quyền tạo collection/index/shard namespace. Một server `mongod` standalone không thay thế được cluster sharded cho toàn bộ phần thử nghiệm này.

Chỉ chạy các lệnh thay đổi cluster trên môi trường bạn được phép quản lý. Tên database minh họa: `mongo_unique_row165_lab`.

### 10.1. Kiểm tra kết nối

```bash
mongosh "mongodb://router.example.internal:27017/"
```

URI trên là placeholder; thay đúng hostname, TLS, authentication của hệ thống thử nghiệm. Sau khi kết nối:

```javascript
sh.status();
```

Quan sát các shard và metadata của sharded cluster. Nếu thiếu quyền hoặc không kết nối được tới `mongos`, dừng phần thay đổi cấu hình thay vì cố chạy trên môi trường khác.

### 10.2. Tạo collection và unique index phù hợp

Ví dụ dành cho **database/collection mới**. Không chạy `createCollection` hoặc `shardCollection` lặp lại nếu namespace đã tồn tại với cấu hình riêng:

```javascript
const lab = db.getSiblingDB("mongo_unique_row165_lab");

lab.createCollection("accounts_demo");
const accounts = lab.getCollection("accounts_demo");

// Index hỗ trợ ranged shard key.
accounts.createIndex(
  { regionId: 1 },
  { name: "region_shard_key" }
);

// Chỉ mỗi cặp regionId + emailKey là duy nhất.
accounts.createIndex(
  { regionId: 1, emailKey: 1 },
  { unique: true, name: "uniq_region_email" }
);

printjson(accounts.getIndexes());

sh.shardCollection(
  "mongo_unique_row165_lab.accounts_demo",
  { regionId: 1 }
);
```

Không thêm tham số thứ ba `true` ở lệnh `sh.shardCollection` này, vì một region được phép chứa nhiều account; chỉ cặp region + email cần duy nhất.

### 10.3. Chèn hai email giống nhau ở hai region

```javascript
const runId = "row165-" + new ObjectId().toHexString();
const regionNorth = runId + "-north";
const regionSouth = runId + "-south";

const inserted = accounts.insertMany([
  {
    runId,
    regionId: regionNorth,
    emailKey: "an@example.test",
    displayName: "An Bắc"
  },
  {
    runId,
    regionId: regionNorth,
    emailKey: "binh@example.test",
    displayName: "Bình Bắc"
  },
  {
    runId,
    regionId: regionSouth,
    emailKey: "an@example.test",
    displayName: "An Nam"
  }
]);

printjson(inserted.insertedIds);
printjson(accounts.find(
  { runId },
  { _id: 1, regionId: 1, emailKey: 1 }
).toArray());
```

Hai document cùng `emailKey: "an@example.test"` nhưng khác region được phép tồn tại, vì compound key không trùng.

### 10.4. Chèn trùng cùng region

```javascript
try {
  accounts.insertOne({
    runId,
    regionId: regionNorth,
    emailKey: "an@example.test",
    displayName: "Bản ghi trùng"
  });
  print("Unexpected: duplicate accepted");
} catch (error) {
  print("Error code: " + error.code);
  print("Error: " + error.message);
}
```

Nếu index đã tạo và collection hoạt động bình thường, lỗi dự kiến là mã `11000`. Nếu thấy lỗi khác, kiểm tra quyền, kết nối và metadata trước khi kết luận.

Với vài document nhỏ, MongoDB có thể chưa phân phối chúng lên nhiều shard. Ví dụ minh họa quy tắc unique của một sharded collection, không phải bài benchmark cân bằng chunk.

### 10.5. Đọc metadata và dọn dữ liệu đúng lượt

```javascript
sh.status();
printjson(accounts.getIndexes());

print("north/an=" + accounts.countDocuments({
  regionId: regionNorth,
  emailKey: "an@example.test"
}));

print("database=" + lab.getName());
print("runId=" + runId);

const owned = accounts.find(
  { runId },
  { _id: 1, regionId: 1, runId: 1, emailKey: 1 }
).toArray();
printjson(owned);
```

Sau khi xác nhận từng document thuộc **lượt thực hành của bạn**, xóa theo ID, đầy đủ shard key và `runId`:

```javascript
for (const doc of owned) {
  const result = accounts.deleteOne({
    _id: doc._id,
    regionId: doc.regionId,
    runId
  });
  print(doc.emailKey + ": deleted=" + result.deletedCount);
}

print("remaining=" + accounts.countDocuments({ runId }));
```

Không dùng `deleteMany({})`, `drop()` hoặc `dropDatabase()` trên môi trường dùng chung. Xóa các document demo không tự xóa collection, index hay cấu hình sharding; những tài nguyên này cần quy trình quản trị riêng.

## 11. Tạo unique index trên collection **đã sharded**

### 11.1. Xác định shard key trước khi tạo

Với một collection đang sharded theo `{tenantId:1}`, muốn tạo index unique cho external order ID có thể thực hiện qua `mongos`:

```javascript
// Đầu tiên xem metadata.
sh.status();

// Chọn đúng database và collection.
const inventory = db.getSiblingDB("inventory");
printjson(inventory.orders.getIndexes());

// Chỉ chạy khi shard key đúng là {tenantId: 1} và dữ liệu đủ điều kiện.
inventory.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true, name: "uniq_tenant_external" }
);
```

Chỉ mục `{externalOrderId:1}` unique hoặc `{externalOrderId:1,tenantId:1}` unique **không được hỗ trợ** cho cấu hình shard key này vì thiếu tiền tố đúng.

### 11.2. Kiểm tra dữ liệu trùng trước khi tạo index

Nếu collection đã có document trùng key, thao tác tạo unique index có thể thất bại. Một cách khảo sát:

```javascript
inventory.orders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      },
      count: { $sum: 1 }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $limit: 20 }
]);
```

Đây là **truy vấn minh họa**: trong hệ thống thật, cần xét kiểu BSON, collation, tài nguyên aggregation, thay đổi đồng thời và quy trình kiểm tra toàn bộ dữ liệu, chứ không kết luận an toàn chỉ vì 20 kết quả đầu tiên trống.

Tài liệu MongoDB cảnh báo khi xây index trên sharded collection đang có dữ liệu trùng ở một shard, có thể một số shard tạo index thành công và shard khác thất bại, dẫn tới **index không nhất quán giữa shards**. Sau thao tác DDL, cần kiểm tra trạng thái trên cluster và xử lý lỗi theo quy trình vận hành, không xem một lỗi trả về như thể mọi shard tự rollback về cùng trạng thái index.

### 11.3. Collection có unique index từ trước khi shard

Nếu một collection chưa sharded có unique index `{emailKey:1}`, rồi muốn shard theo `{tenantId:1}`, kế hoạch này không tương thích với quy tắc prefix. Sharding có thể bị từ chối.

Không xóa unique index cũ để chạy được lệnh sharding khi chưa có phương án khác bảo đảm tính đúng đắn. Cần lựa chọn:

- Điều chỉnh phạm vi uniqueness thành tenant + email nếu nghiệp vụ cho phép.
- Đổi shard key sao cho compatible với unique key cần giữ.
- Dùng registry/proxy để giữ global uniqueness.
- Giữ collection không sharded nếu khối lượng cho phép và sự đơn giản quan trọng hơn phân mảnh.

### 11.4. Metadata consistency

Khi có nhiều shard và thao tác index build/migration, đội vận hành cần kiểm tra metadata/index consistency bằng các công cụ phù hợp với phiên bản MongoDB đang triển khai. MongoDB có lệnh `checkMetadataConsistency` và các tùy chọn liên quan trong những phiên bản hỗ trợ. Cần tham khảo đúng cú pháp/quyền của phiên bản cụ thể, không tự suy ra từ một môi trường khác.

## 12. Resharding có thể làm unique index không còn tương thích

Giả sử ban đầu:

```javascript
// Shard key cũ:
{ tenantId: 1 }

// Unique index hiện hành:
{ tenantId: 1, emailKey: 1 }
```

Đội vận hành muốn reshard collection theo:

```javascript
{ regionId: 1 }
```

Unique index cũ `{tenantId,emailKey}` không có shard key mới `regionId` làm prefix. MongoDB yêu cầu shard key mới phải thỏa các giới hạn unique index đang áp dụng. Vì vậy reshard không thể được xem là chỉ một lệnh thay đổi phân bố dữ liệu mà bỏ qua invariant.

Kế hoạch reshard cần xem:

1. Những index unique nào đang tồn tại?
2. Chúng bảo vệ invariant nghiệp vụ nào?
3. Invariant đó còn biểu diễn được với shard key mới không?
4. Có cần migration dữ liệu, sửa index hoặc registry trước?
5. Ứng dụng có đang truy vấn/ghi theo shard key cũ không?
6. Lệnh và thứ tự thao tác có được phiên bản MongoDB hỗ trợ không?

**Shard key là quyết định kiến trúc dài hạn**, liên quan đến dữ liệu, index, hiệu năng và cả API.

## 13. Concurrent writes, upsert và lỗi `E11000`

### 13.1. Có unique index không có nghĩa mọi request sẽ tự chờ nhau

Nếu hai request đồng thời đăng ký cùng `{tenantId,username}`:

```javascript
db.users.updateOne(
  { tenantId: "TENANT-A", username: "an" },
  {
    $setOnInsert: {
      displayName: "An",
      createdAt: new Date()
    }
  },
  { upsert: true }
);
```

Unique index hợp lệ trên `{tenantId:1,username:1}` ngăn hai document trùng tổ hợp khóa. Nhưng cạnh tranh giữa hai upsert có thể kết thúc bằng một lần insert và một lần update/no-op, hoặc một request nhận lỗi duplicate key tùy điều kiện thực thi.

Ứng dụng cần xử lý:

- `upsertedCount:1`: tạo mới.
- `matchedCount:1`: đã có document khớp.
- `11000`: đối soát xem đã có đúng business key và payload hay có xung đột khác.
- Lỗi mạng không rõ kết quả: đối soát bằng stable key và chính sách retry/idempotency.

### 13.2. Không trộn điều kiện trạng thái vào filter upsert tùy tiện

Khi cần chuyển một document từ `PENDING` sang `ACTIVE`, hãy dùng update có điều kiện **không upsert**:

```javascript
db.users.updateOne(
  {
    tenantId: "TENANT-A",
    username: "an",
    status: "PENDING"
  },
  { $set: { status: "ACTIVE" } }
);
```

Nếu thêm `upsert:true` cho filter chứa trạng thái, lúc document đã chuyển trạng thái khác lệnh có thể cố insert document mới cùng unique key và nhận `11000`. Đây là lỗi thiết kế luồng cập nhật, không phải dấu hiệu unique index sai.

### 13.3. Unique không thay authorization

Một request cần lấy `tenantId` từ ngữ cảnh người dùng đã xác thực, không tin tenant do client tự khai báo. Unique index bảo vệ ràng buộc lưu trữ; chính sách phân quyền bảo đảm request có quyền thao tác trong đúng tenant.

## 14. Ma trận quyết định thiết kế

| Nghiệp vụ | Shard key | Unique index/giải pháp | Tính duy nhất thực sự |
| --- | --- | --- | --- |
| Username unique trong tenant | `{tenantId:1}` | `{tenantId:1,username:1}` unique | Theo cặp tenant + username |
| Email unique trong region | `{regionId:1}` | `{regionId:1,emailKey:1}` unique | Theo cặp region + email |
| Một cấu hình trên mỗi region | `{regionId:1}` | `{regionId:1}` unique | Mỗi region một document |
| Order ID unique trong tenant nhưng shard theo tenant + tháng | `{tenantId:1,monthBucket:1}` | Index `{tenantId,monthBucket,orderId}` **không đủ** nếu ID không được trùng xuyên tháng | Chỉ unique theo cả ba trường |
| Email unique toàn hệ thống, account sharded theo tenant | `{tenantId:1}` | Registry/proxy global hoặc thay shard key | Global theo registry nếu triển khai đúng |
| `_id` phải unique toàn hệ thống, `_id` không phải shard key | `{tenantId:1}` | ID generation strategy hoặc registry/đổi key | Default `_id` index chỉ duy nhất từng shard |
| Dữ liệu sharded bằng hashed key | `{accountId:"hashed"}` | Không tạo unique hashed index | Cần thiết kế constraint khác nếu yêu cầu |

Đừng nhầm “index hợp lệ theo MongoDB” với “index bảo vệ đúng phạm vi nghiệp vụ”. Thiết kế phải đáp ứng **cả hai**.

## 15. Lỗi phổ biến và cách tránh

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Có shard key ở cuối unique index | Không thỏa quy tắc prefix | Đặt đầy đủ shard key làm tiền tố đúng thứ tự |
| Dùng unique `{tenantId,email}` để bảo vệ email global | Hai tenant có thể chứa email giống nhau | Registry hoặc đổi shard key |
| Chọn shard key hai field nhưng index chỉ có field đầu | Thiếu shard key đầy đủ | Dùng full compound shard key prefix |
| Tin default `_id` luôn unique toàn cluster | Có thể trùng giữa các shard | Sinh ID có chiến lược global hoặc registry |
| Cố dùng `unique:true` trên hashed index | Cấu hình không được hỗ trợ | Chọn mô hình shard/index khác |
| Tưởng unique compound bắt từng thành phần unique | Tạo phạm vi quá rộng hoặc quá hẹp | Phân tích entire compound key |
| Không chuẩn hóa emailKey | Case/Unicode khác nhau làm khóa khác | Chuẩn hóa theo chính sách nhất quán |
| Chỉ query kiểm tra tồn tại rồi insert | Race condition giữa hai request | Ràng buộc unique ở điểm ghi |
| Không kiểm tra null/missing | Xung đột hoặc dữ liệu khóa sai | Schema validation và quy tắc input |
| Tạo index unique trên dữ liệu trùng | Index build thất bại; có thể lệch shards | Khảo sát, xử lý trùng, kiểm tra consistency |
| Bỏ unique index để shard thành công | Mất invariant dữ liệu | Thiết kế phương án thay thế trước |
| Reshard mà quên unique indexes | Shard key mới không tương thích | Lập kế hoạch migration và invariant |
| Dùng transaction mà không có unique registry | Transaction không tự tạo uniqueness | Unique index đúng chỗ + transaction phối hợp |

## 16. Bài tập

### Bài A: Nhận diện index hợp lệ

Collection `orders` sharded theo:

```javascript
{ tenantId: 1, quarter: 1 }
```

Xét các index sau:

```javascript
// A
{ tenantId: 1, quarter: 1, orderId: 1 }
// B
{ tenantId: 1, orderId: 1 }
// C
{ quarter: 1, tenantId: 1, orderId: 1 }
// D
{ tenantId: 1, quarter: 1 }
// E
{ orderId: 1 }
```

Hãy chỉ ra index nào có **toàn bộ shard key làm prefix**, và index nào không. Nếu orderId phải unique trong tenant **qua mọi quý**, tại sao A vẫn chưa đủ?

Gợi ý: A và D có tiền tố phù hợp. A unique trên cả tenant + quý + order; một ID có thể được dùng ở quý khác mà không trùng toàn bộ key.

### Bài B: Phân tích `_id`

Một collection sharded theo `{regionId:1}`, mỗi vùng tự cấp ID tăng dần từ 1. Trả lời:

1. Default `_id` index chặn trùng trong phạm vi nào?
2. Vì sao hai vùng có thể sinh cùng `_id`?
3. Nên thay chiến lược sinh ID hoặc mô hình unique thế nào để tránh lỗi?

### Bài C: Global unique email

Hệ thống account sharded theo tenant nhưng email unique toàn bộ ứng dụng. Hãy vẽ:

```text
Client -> API -> Normalize -> Registry -> Accounts
```

Trong thiết kế, phải giải thích:

- Registry có unique key nào?
- Hai request cùng email có thể gây lỗi gì?
- Vì sao cần phối hợp registry và account bằng transaction?
- Khi đổi email hoặc xóa account, xử lý key cũ thế nào?
- Vì sao unique `{tenantId,emailKey}` không đáp ứng global uniqueness?

### Bài D: Chuẩn bị shard một collection hiện có

Collection chưa shard đang có unique index `{emailKey:1}`. Đội vận hành muốn shard theo `{regionId:1}`. Hãy giải thích tại sao kế hoạch có vấn đề, và đề xuất ít nhất hai phương án bảo vệ lại invariant email.

## 17. Tài liệu tham khảo

Khi quản trị cluster thật, dùng hướng dẫn **theo đúng phiên bản MongoDB**:

- [Maintain Uniqueness in Sharded Clusters](https://www.mongodb.com/docs/manual/tutorial/maintain-uniqueness-in-sharded-clusters/) — nguyên tắc shard key prefix và ngoại lệ `_id`.
- [Shard Key Indexes](https://www.mongodb.com/docs/manual/core/sharding-shard-key-indexes/) — index hỗ trợ shard key.
- [Create a Unique Index on Existing Sharded Collection](https://www.mongodb.com/docs/manual/tutorial/create-unique-index-on-sharded-collection/) — tạo unique sau khi shard.
- [Enforce Uniqueness on the Shard Key Values](https://www.mongodb.com/docs/manual/tutorial/enforce-uniqueness-on-shard-key-values/) — unique trên chính shard key.
- [Enforce Uniqueness on a Field That Is Not the Shard Key](https://www.mongodb.com/docs/manual/tutorial/enforce-uniqueness-on-non-shard-key-field/) — sử dụng registry/proxy collection.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — khái niệm unique, compound key, collation và field thiếu.

## 18. Kết luận

Trên một **ranged sharded collection**, MongoDB cưỡng chế uniqueness xuyên các shard khi unique index nằm trên shard key hoặc có **toàn bộ shard key làm tiền tố**. Unique của compound index áp dụng cho **cả tổ hợp key**, không cho từng trường. Default `_id` index không bảo đảm uniqueness xuyên cluster khi `_id` không phải shard key; hashed index không hỗ trợ unique constraint.

Nếu business key cần unique toàn hệ thống nhưng không phù hợp shard key, hãy xem lại thiết kế sharding hoặc dùng **registry/proxy collection** với ràng buộc được cưỡng chế, kết hợp transaction và idempotency khi thích hợp. Chọn shard key, index và phạm vi ràng buộc phải là **một quyết định thiết kế thống nhất**, không phải các bước tách rời.
