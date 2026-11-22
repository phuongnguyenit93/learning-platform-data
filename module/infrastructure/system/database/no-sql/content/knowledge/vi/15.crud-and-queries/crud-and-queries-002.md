# Insert, upsert và phân biệt tạo mới với ghi đè

Khi ứng dụng ghi dữ liệu vào NoSQL, hai yêu cầu nghe rất giống nhau nhưng có hậu quả khác nhau:

- **“Tạo đơn hàng mới.”** Nếu đơn có cùng định danh đã tồn tại, thao tác phải báo trùng, không được âm thầm sửa đơn cũ.
- **“Đồng bộ hồ sơ khách hàng.”** Nếu hồ sơ chưa có thì tạo, nếu đã có thì cập nhật một số trường cho đúng dữ liệu hiện tại.

Yêu cầu thứ nhất gần với **insert**; yêu cầu thứ hai thường là **upsert**. Một yêu cầu khác, “thay toàn bộ cấu hình bằng bản mới”, có thể cần **replace**. Trong khi đó, “chỉ sửa địa chỉ giao hàng” nên là **update từng trường**, không phải ghi đè toàn bộ document.

Sự khác nhau không chỉ nằm ở tên API. Nó quyết định điều gì xảy ra khi **khóa đã tồn tại, khóa chưa tồn tại, request được retry, hai client ghi đồng thời, dữ liệu thiếu trường hoặc phiên bản mới vừa cập nhật**. Chọn nhầm thao tác có thể xóa mất field, tạo bản ghi trùng, ghi đè giá trị mới bằng giá trị cũ hoặc áp dụng một hiệu ứng nghiệp vụ hai lần.

Bài học dùng **MongoDB/mongosh** làm ví dụ chính, sau đó đối chiếu Redis, DynamoDB, Cassandra và Couchbase. Mỗi sản phẩm có ngữ nghĩa ghi khác nhau; đừng suy rằng từ **INSERT** hoặc **upsert** có nghĩa giống hệt giữa mọi hệ NoSQL.

## 1. Bốn ý định ghi dữ liệu cần phân biệt

| Ý định nghiệp vụ | Nếu chưa có bản ghi | Nếu đã có bản ghi | Thao tác ứng viên |
|---|---|---|---|
| **Chỉ tạo mới** | Tạo | Từ chối hoặc báo xung đột | Insert / conditional create |
| **Chỉ cập nhật** | Không sửa gì hoặc báo không tìm thấy | Sửa các trường được chỉ định | Update không upsert |
| **Tạo nếu thiếu, cập nhật nếu có** | Tạo | Cập nhật có kiểm soát | Upsert |
| **Thay toàn bộ bản ghi** | Có thể tạo nếu cho phép | Thay nội dung document/item theo ngữ nghĩa engine | Replace / put |

Trong MongoDB, có thể liên hệ:

~~~javascript
db.orders.insertOne(document);

db.orders.updateOne(filter, { $set: fields });

db.orders.updateOne(filter, updateOperators, { upsert: true });

db.orders.replaceOne(filter, replacementDocument);
~~~

Chỉ **updateOne** và **replaceOne** có thể sử dụng tùy chọn **upsert** để tạo khi không tìm thấy bản ghi. **insertOne** vốn đã có ý định tạo mới. Trong ví dụ này, **updateOne** không khai báo **upsert** chỉ cập nhật khi tìm thấy document khớp.

**Lưu ý về thuật ngữ:** “upsert” diễn tả **ý định nếu có thì cập nhật, nếu không có thì chèn**. Còn **“ghi đè”** có thể có nghĩa ghi đè một field, nhiều field hoặc cả document; cần nói rõ phạm vi ghi đè, không dùng các từ này như từ đồng nghĩa.

## 2. Xây dựng ví dụ nghiệp vụ thống nhất

Giả sử ứng dụng quản lý đơn hàng của nhiều cửa hàng. Mỗi order có:

~~~text
tenantId             Mã cửa hàng/tổ chức sở hữu
externalOrderId      ID đơn do hệ thống đặt hàng cung cấp
customerId           ID khách hàng
status               PENDING | PAID | CANCELLED
totalMinor           Số tiền theo đơn vị tiền nhỏ nhất
currency             VND
createdAt            Thời điểm tạo đơn
updatedAt            Thời điểm sửa gần nhất
shippingAddress      Địa chỉ giao hàng
checkoutRequestId    ID của một ý định checkout
~~~

Giả sử với tenant **shop-a**, order **web-1001** có dữ liệu:

~~~javascript
{
  _id: "order-1001",
  tenantId: "shop-a",
  externalOrderId: "web-1001",
  customerId: "customer-07",
  status: "PENDING",
  totalMinor: NumberLong("240000"),
  currency: "VND",
  createdAt: ISODate("2026-11-14T09:00:00Z"),
  updatedAt: ISODate("2026-11-14T09:00:00Z"),
  shippingAddress: {
    city: "Da Nang",
    street: "12 Nguyen Van Linh"
  }
}
~~~

Trong ví dụ, **totalMinor = 240000** là số tiền của đơn đã tính theo quy tắc nghiệp vụ; việc tạo document không tự xác minh số tiền đúng với giỏ hàng. Các trường như **tenantId**, **externalOrderId** và **checkoutRequestId** có vai trò khác nhau: tenant giới hạn quyền, externalOrderId định danh đơn trong một nguồn, requestId có thể định danh **một lần yêu cầu** để chống retry tạo trùng.

Ta sẽ dùng cùng một order để quan sát hiệu ứng của các thao tác ghi.

## 3. Khóa là cơ sở để biết “đã tồn tại”

Một thao tác “nếu đã có” phải trả lời trước câu hỏi:

> **Có theo khóa nào?**

MongoDB luôn có trường **_id** duy nhất trong một collection. Nếu ứng dụng không cung cấp **_id**, driver/mongosh thường tự gán một **ObjectId** mới cho document được chèn. Vì vậy, gửi cùng nội dung hai lần nhưng để mỗi lần tự có _id khác nhau **có thể tạo hai document khác nhau**.

Nếu nghiệp vụ định danh order theo cặp **(tenantId, externalOrderId)**, hãy biểu diễn quy tắc duy nhất ấy ở database:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true, name: "uniq_tenant_external_order" }
);
~~~

Khi index đã tạo thành công, hai document không được có cùng bộ giá trị khóa theo ngữ nghĩa uniqueness của index. Điều này quan trọng khi **hai request đồng thời** đều muốn tạo cùng order.

Trong production, còn cần bảo đảm **externalOrderId** có kiểu/giá trị hợp lệ và không bị thiếu hoặc null ngoài chính sách. Unique index trên trường có giá trị thiếu/null có những ngữ nghĩa riêng, không thay thế schema validation. Nếu collection đã có các bộ khóa trùng, việc tạo unique index có thể thất bại và phải giải quyết dữ liệu cũ trước.

**Một ID không phải khóa toàn cục nếu nghiệp vụ chỉ bảo đảm nó duy nhất trong một tenant.** Nếu hai cửa hàng đều có order **web-1001**, khóa duy nhất nên phản ánh phạm vi tenant thay vì vô tình cấm điều hợp lệ.

## 4. Insert: tạo mới, không âm thầm sửa bản ghi cũ

### insertOne

~~~javascript
db.orders.insertOne({
  _id: "order-1001",
  tenantId: "shop-a",
  externalOrderId: "web-1001",
  customerId: "customer-07",
  status: "PENDING",
  totalMinor: NumberLong("240000"),
  currency: "VND",
  createdAt: ISODate("2026-11-14T09:00:00Z"),
  updatedAt: ISODate("2026-11-14T09:00:00Z")
});
~~~

Khi chèn thành công, mongosh báo **acknowledged** và **insertedId** theo API. Một lần chèn thành công nghĩa là bản ghi mới đã được tạo theo write concern của thao tác; nó **không tự bảo đảm** mọi hệ thống khác như payment, cache hoặc search index đã cập nhật.

Nếu chạy lại **cùng lệnh** với **_id: "order-1001"**, MongoDB sẽ từ chối vì _id đã tồn tại, thường dưới dạng **duplicate key error**. Nếu dùng một _id khác nhưng lặp cùng **(tenantId, externalOrderId)**, unique index ở trên cũng ngăn bản ghi trùng nghiệp vụ.

Đó là khác biệt quan trọng với upsert:

~~~text
Insert:
  Chưa tồn tại -> tạo document
  Đã tồn tại   -> báo duplicate key/xung đột

Không có nhánh "đã tồn tại thì cập nhật status".
~~~

### Khi nào insert phù hợp?

- Tạo **order**, **payment event**, **certificate** hoặc **audit event** có danh tính mới.
- Ghi một giao dịch phải được phân biệt rõ với giao dịch đã tồn tại.
- Tạo tài khoản bằng username/email đã có quy tắc uniqueness.
- Ghi các bản ghi bất biến sau khi chốt, như snapshot hóa đơn hoặc sự kiện ledger.

Nếu client gửi lại cùng request vì mất phản hồi, lỗi duplicate key **có thể** cho biết tác vụ trước đã thành công. Nhưng không nên tự động kết luận duplicate là thành công: phải đối chiếu khóa, chủ sở hữu và payload/ý định của lần ghi trước.

## 5. insertMany không phải “hoặc tất cả hoặc không gì cả”

MongoDB hỗ trợ chèn nhiều document:

~~~javascript
db.orders.insertMany(
  [
    {
      _id: "order-1002",
      tenantId: "shop-a",
      externalOrderId: "web-1002",
      status: "PENDING"
    },
    {
      _id: "order-1003",
      tenantId: "shop-a",
      externalOrderId: "web-1003",
      status: "PENDING"
    }
  ],
  { ordered: true }
);
~~~

Hai chế độ cần hiểu:

| Tùy chọn | Hành vi khi một document gặp lỗi ghi |
|---|---|
| **ordered: true** | Thực hiện theo thứ tự và ngừng xử lý batch sau lỗi đầu tiên theo ngữ nghĩa thao tác |
| **ordered: false** | Có thể tiếp tục chèn các document khác dù một số document lỗi; thứ tự thực thi không được bảo đảm như ordered |

Trong cả hai trường hợp, nếu một phần ghi đã thành công trước lỗi, **không được mặc định toàn bộ batch tự rollback**. Muốn “tất cả các bản ghi này cùng thành công hoặc không cái nào thành công”, cần xem transaction và giới hạn của database, hoặc thiết kế workflow trạng thái/đối soát phù hợp.

Khi import dữ liệu, nên kiểm tra số bản ghi thành công, các ID bị duplicate, các lỗi validation, checkpoint và khả năng retry batch. Nếu một batch lỗi giữa chừng, retry với ID ổn định và kiểm soát trùng an toàn hơn tạo ID ngẫu nhiên mới cho mọi lần thử.

## 6. Update: chỉ sửa bản ghi đã tồn tại

Giả sử đơn **order-1001** đang có **status = PENDING** và cần cập nhật địa chỉ giao hàng.

~~~javascript
db.orders.updateOne(
  {
    _id: "order-1001",
    tenantId: "shop-a"
  },
  {
    $set: {
      "shippingAddress.city": "Hue",
      updatedAt: ISODate("2026-11-14T09:30:00Z")
    }
  }
);
~~~

**$set** sửa đúng các đường dẫn được chỉ định. Các trường **totalMinor**, **currency**, **createdAt** và **status** vẫn giữ nguyên.

Nếu không có document khớp filter, với tùy chọn mặc định **upsert: false**:

~~~text
matchedCount  = 0
modifiedCount = 0
Không có document mới.
~~~

Nếu tìm thấy nhưng giá trị mới giống hệt giá trị đã lưu, có thể thấy:

~~~text
matchedCount  = 1
modifiedCount = 0
~~~

Vì vậy **modifiedCount = 0 không đồng nghĩa “không tìm thấy bản ghi”**. Cần nhìn **matchedCount** để phân biệt trường hợp không match với match nhưng không làm thay đổi dữ liệu.

### Các update operators thường gặp

| Operator | Mục đích | Ví dụ |
|---|---|---|
| **$set** | Gán giá trị cho field | Đổi địa chỉ giao hàng |
| **$unset** | Xóa field khỏi document | Loại field tạm không còn dùng |
| **$inc** | Tăng/giảm giá trị số | Cộng bộ đếm hoặc giảm tồn có điều kiện |
| **$addToSet** | Thêm phần tử vào array nếu chưa tồn tại theo cách so sánh của MongoDB | Thêm một tag không trùng |
| **$push** | Thêm phần tử vào array | Ghi log nhỏ có giới hạn nếu mô hình phù hợp |
| **$pull** | Loại phần tử array khớp điều kiện | Bỏ một tag |
| **$currentDate** | Đặt thời gian hiện tại bằng phía database theo API | Ghi mốc update kỹ thuật |

Không phải operator nào cũng **idempotent** khi request lặp. **$set status = PAID** có thể ghi cùng giá trị nhiều lần, nhưng **$inc points = 100** sẽ cộng thêm 100 mỗi lần. **$push** cũng có thể nhân đôi phần tử khi chạy lại.

## 7. Upsert: update nếu có, insert nếu chưa có

Trong MongoDB, **updateOne** có thể nhận tùy chọn **upsert: true**:

~~~javascript
db.customerPreferences.updateOne(
  {
    tenantId: "shop-a",
    customerId: "customer-07"
  },
  {
    $set: {
      language: "vi",
      theme: "dark",
      updatedAt: ISODate("2026-11-14T10:00:00Z")
    },
    $setOnInsert: {
      createdAt: ISODate("2026-11-14T10:00:00Z"),
      schemaVersion: 1
    }
  },
  { upsert: true }
);
~~~

Nếu preferences của **(shop-a, customer-07)** chưa tồn tại, MongoDB tạo document. Nếu đã có, MongoDB chỉ sửa **language**, **theme** và **updatedAt** từ **$set**, còn **createdAt** và **schemaVersion** trong **$setOnInsert** không bị sửa.

**$setOnInsert** là điểm khác biệt quan trọng khi thiết kế dữ liệu có trường chỉ được đặt tại thời điểm tạo:

~~~text
Nhánh INSERT:
  nhận các giá trị từ điều kiện equality phù hợp,
  các update operators và $setOnInsert

Nhánh UPDATE:
  chỉ chạy update operators áp dụng cho bản ghi đã có;
  không áp dụng $setOnInsert
~~~

Để tránh tạo hai preferences cho cùng một khách, cần thêm ràng buộc uniqueness:

~~~javascript
db.customerPreferences.createIndex(
  { tenantId: 1, customerId: 1 },
  { unique: true, name: "uniq_preferences_by_customer" }
);
~~~

### Một ví dụ rất ngắn

~~~javascript
db.counters.updateOne(
  { _id: "daily-2026-11-14" },
  {
    $setOnInsert: { label: "Daily requests" },
    $set: { updatedBy: "metrics-job" }
  },
  { upsert: true }
);
~~~

Lệnh này bảo đảm logic **“có thì cập nhật metadata, chưa có thì tạo”** ở một khóa xác định, không cộng bộ đếm. Nếu muốn đếm số request, cần thiết kế tính đúng đắn khi retry riêng; thêm **$inc** vào một upsert mà không có idempotency có thể làm đếm trùng.

## 8. Kết quả updateOne cho biết đã tạo hay đã cập nhật?

Với một thao tác **updateOne(..., {upsert: true})** được xác nhận, các trường kết quả quan trọng là:

| Trường kết quả | Ý nghĩa | Trường hợp đáng chú ý |
|---|---|---|
| **acknowledged** | Server đã xác nhận thao tác theo write concern | Không có nghĩa consumer khác cũng đã cập nhật |
| **matchedCount** | Số document khớp filter trong nhánh cập nhật | Thường 1 nếu tìm thấy, 0 nếu chèn mới |
| **modifiedCount** | Số document thực sự bị thay đổi | Có thể 0 nếu giá trị cũ đã giống giá trị mới |
| **upsertedCount** | Số document được chèn do upsert | 1 khi upsert tạo mới trong updateOne |
| **upsertedId** | ID document chèn bằng upsert | Có giá trị khi tạo mới |

Ví dụ cách đọc kết quả:

~~~javascript
const result = db.customerPreferences.updateOne(
  { tenantId: "shop-a", customerId: "customer-07" },
  { $set: { language: "en" } },
  { upsert: true }
);

if (result.upsertedCount === 1) {
  print("Đã tạo preferences mới");
} else if (result.matchedCount === 1 && result.modifiedCount === 1) {
  print("Đã cập nhật preferences");
} else if (result.matchedCount === 1) {
  print("Đã tìm thấy nhưng nội dung không đổi");
} else {
  print("Cần kiểm tra phản hồi/điều kiện ghi");
}
~~~

Đây là cách hiểu kết quả **khi thao tác đã có phản hồi xác định**. Nếu kết nối bị đứt trong lúc commit, client có thể không biết lệnh đã thành công hay chưa. Lúc đó không được chỉ dựa vào việc chưa thấy response rồi tạo lại với ID mới; cần xem chính sách retry và định danh nghiệp vụ.

## 9. Upsert không có nghĩa “không thể bị trùng”

Giả sử hai service instance cùng chạy:

~~~javascript
db.customerPreferences.updateOne(
  { tenantId: "shop-a", customerId: "customer-07" },
  { $set: { language: "vi" } },
  { upsert: true }
);
~~~

Nếu không có **unique index** trên bộ khóa, cả hai thao tác có thể cùng thấy chưa có document, rồi mỗi thao tác tạo một document mới. Kết quả là **hai preferences cho một khách**.

Với unique index phù hợp, ràng buộc database ngăn hai document cùng bộ khóa. Tuy nhiên, khi upsert đồng thời, tùy filter/index/update và thứ tự thực thi, một request có thể đi sang nhánh cập nhật hoặc có thể gặp **duplicate key error**. Không nên coi mọi cuộc đua upsert đều tự động hòa giải thành một update thành công.

~~~mermaid
flowchart TD
    A["Hai request upsert cùng logical key"] --> B{"Có unique constraint phù hợp?"}
    B -->|"Không"| C["Nguy cơ tạo hai document cùng nghĩa"]
    B -->|"Có"| D["Database ngăn tồn tại hai document trùng khóa"]
    D --> E{"Request gặp duplicate key?"}
    E -->|"Có"| F["Đọc lại và xử lý theo ý định nghiệp vụ"]
    E -->|"Không"| G["Tạo mới hoặc cập nhật theo kết quả"]
~~~

Kết luận thực hành: **upsert + logical key ổn định + unique constraint + xử lý retry/xung đột** mới là một thiết kế đáng tin cậy. Chỉ viết **upsert: true** chưa phải thiết kế chống trùng hoàn chỉnh.

## 10. Replace: khác hoàn toàn với cập nhật một vài trường

Giả sử document đã có:

~~~javascript
{
  _id: "profile-07",
  tenantId: "shop-a",
  displayName: "An",
  phone: "0900000000",
  notificationSettings: {
    email: true,
    sms: false
  },
  createdAt: ISODate("2026-11-10T08:00:00Z")
}
~~~

Ứng dụng muốn sửa tên nhưng gửi:

~~~javascript
db.profiles.replaceOne(
  { _id: "profile-07", tenantId: "shop-a" },
  {
    tenantId: "shop-a",
    displayName: "An Nguyen"
  }
);
~~~

Kết quả khi tìm thấy document là **thay nội dung document bằng replacement**. Những trường không được đưa vào replacement như **phone**, **notificationSettings** và **createdAt** sẽ không còn tồn tại trong document mới. **_id** của document khớp được giữ nguyên khi replacement không cung cấp _id khác; không được thay đổi _id của document đã có.

Nếu mục tiêu chỉ sửa displayName, nên dùng:

~~~javascript
db.profiles.updateOne(
  { _id: "profile-07", tenantId: "shop-a" },
  { $set: { displayName: "An Nguyen" } }
);
~~~

Khi đó **phone**, **notificationSettings** và **createdAt** vẫn giữ nguyên.

### So sánh bằng ví dụ

~~~text
Trước:
  { _id: "p1", name: "An", age: 20, city: "Hue" }

Update $set name:
  { _id: "p1", name: "Binh", age: 20, city: "Hue" }

Replace với {name:"Binh"}:
  { _id: "p1", name: "Binh" }
  -> age và city bị loại
~~~

Vì vậy **replaceOne** phù hợp khi replacement là **toàn bộ trạng thái mong muốn** của một record và ứng dụng có quyền sở hữu đầy đủ các field được thay. Nó nguy hiểm với API cập nhật một phần (PATCH) hoặc khi nhiều service sở hữu những field khác nhau trong cùng document.

## 11. Replace với upsert là hai quyết định kết hợp

**replaceOne** cũng có thể nhận **upsert: true**:

~~~javascript
db.profiles.replaceOne(
  { _id: "profile-07" },
  {
    displayName: "An Nguyen",
    notificationSettings: {
      email: true,
      sms: true
    },
    schemaVersion: 2
  },
  { upsert: true }
);
~~~

Nếu document chưa có, thao tác có thể tạo document. Nếu đã có, nó thay toàn bộ nội dung không phải _id bằng replacement tương ứng. **Upsert quyết định có được phép tạo khi thiếu**, còn **replace quyết định cách sửa khi đã có**.

Đó là hai trục lựa chọn độc lập:

| Cách gọi | Khi chưa có | Khi đã có |
|---|---|---|
| **updateOne + $set** | Không tạo | Sửa field chỉ định |
| **updateOne + $set + upsert** | Tạo | Sửa field chỉ định |
| **replaceOne** | Không tạo | Thay document |
| **replaceOne + upsert** | Tạo | Thay document |

Với **replaceOne**, không được gửi replacement là một document chứa những update operator như **$set**. Với **updateOne**, không nên đưa một plain object làm đối số update nếu API yêu cầu operator/pipeline; phải dùng đúng hình thức cập nhật được MongoDB hỗ trợ.

## 12. Khi nào nên dùng findOneAndUpdate?

Nhiều nghiệp vụ muốn **thực hiện ghi và nhận lại trạng thái hiện tại**:

~~~javascript
const current = db.customerPreferences.findOneAndUpdate(
  { tenantId: "shop-a", customerId: "customer-07" },
  {
    $set: {
      language: "en",
      updatedAt: ISODate("2026-11-14T11:00:00Z")
    },
    $setOnInsert: {
      createdAt: ISODate("2026-11-14T11:00:00Z")
    }
  },
  {
    upsert: true,
    returnDocument: "after"
  }
);
~~~

Tùy API/phiên bản driver, mặc định có thể trả **bản trước khi cập nhật**; lựa chọn **returnDocument: "after"** yêu cầu lấy bản sau thao tác. Cần đọc tài liệu phiên bản driver đang dùng, bởi hình dạng kết quả có thể khác giữa shell và client library.

Nếu cần phân biệt rõ **đã insert hay đã update**, kết quả thống kê từ **updateOne** (ví dụ **upsertedCount**, **upsertedId**) thường trực tiếp hơn việc chỉ đọc document trả về của **findOneAndUpdate**. Không nên suy ra từ **createdAt == updatedAt** rằng document vừa được chèn, vì một document cũ cũng có thể chưa từng được sửa.

## 13. Chọn filter upsert theo danh tính, không theo trạng thái thay đổi

Một lỗi thiết kế phổ biến:

~~~javascript
// Có rủi ro nếu ý định là "tìm đúng order và chuyển trạng thái".
db.orders.updateOne(
  {
    _id: "order-1001",
    status: "PENDING"
  },
  {
    $set: { status: "PAID" }
  },
  { upsert: true }
);
~~~

Nếu order tồn tại nhưng **status đã là CANCELLED**, filter **không khớp**. Vì có **upsert: true**, MongoDB có thể thử tạo một document mới dựa trên filter và cập nhật, rồi bị chặn bởi unique _id — hoặc nếu dùng một filter không có khóa duy nhất ổn định, có thể tạo một record sai.

Đây không phải cách phù hợp để xử lý chuyển trạng thái.

Đúng hơn, với một order đã tồn tại và chỉ cho phép chuyển **PENDING → PAID**:

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "order-1001",
    tenantId: "shop-a",
    status: "PENDING"
  },
  {
    $set: {
      status: "PAID",
      paidAt: ISODate("2026-11-14T11:10:00Z")
    }
  }
);

if (result.matchedCount === 0) {
  print("Order không tồn tại, sai tenant hoặc không còn PENDING");
}
~~~

**Không bật upsert** vì nghiệp vụ **không cho phép tự tạo order trong lúc nhận kết quả thanh toán**. Nếu filter thất bại, ứng dụng cần đọc trạng thái hiện tại, phân loại trường hợp đã PAID do retry, CANCELLED hoặc thiếu order, rồi xử lý theo state machine.

**Quy tắc nhớ:** nếu thao tác có nghĩa **“đổi trạng thái của một bản ghi đã biết”**, thường phải dùng **conditional update, upsert: false**. Nếu có nghĩa **“đảm bảo một cấu hình tồn tại”**, có thể xem xét upsert bằng **khóa danh tính**.

## 14. “Kiểm tra rồi insert” không thay thế unique constraint

Giả sử tạo tài khoản theo email:

~~~javascript
const found = db.users.findOne({
  tenantId: "shop-a",
  normalizedEmail: "an@example.com"
});

if (!found) {
  db.users.insertOne({
    tenantId: "shop-a",
    normalizedEmail: "an@example.com"
  });
}
~~~

Hai request có thể cùng chạy **findOne** trước khi bên nào chèn. Cả hai đều thấy chưa tồn tại và đều gọi **insertOne**. Đây là **race condition** kinh điển của bước kiểm tra tách khỏi bước ghi.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as Database
    A->>DB: findOne(email)
    B->>DB: findOne(email)
    DB-->>A: không có
    DB-->>B: không có
    A->>DB: insertOne(email)
    B->>DB: insertOne(email)
    Note over DB: Unique index quyết định có cho phép trùng hay không
~~~

Nếu ràng buộc nghiệp vụ là “mỗi tenant chỉ có một tài khoản cho một normalizedEmail”, tạo unique index:

~~~javascript
db.users.createIndex(
  { tenantId: 1, normalizedEmail: 1 },
  { unique: true }
);
~~~

Sau đó **xử lý duplicate key như một kết quả bình thường của cạnh tranh**, chứ không coi việc check trước đã loại hết khả năng trùng.

**normalizedEmail** phải được tạo từ quy tắc chuẩn hóa đã xác nhận; unique index không tự quyết định có phân biệt chữ hoa/chữ thường hoặc Unicode hay không nếu ứng dụng không thiết kế đúng field/collation.

## 15. Retry sau timeout: upsert có phải idempotent không?

Một thao tác **idempotent** là thao tác khi lặp lại cùng ý định không tạo thêm hiệu ứng nghiệp vụ không mong muốn.

So sánh:

~~~javascript
// Gán cùng một giá trị:
db.profiles.updateOne(
  { _id: "profile-07" },
  { $set: { language: "vi" } },
  { upsert: true }
);

// Mỗi lần gọi đều tăng counter:
db.counters.updateOne(
  { _id: "daily-2026-11-14" },
  { $inc: { requests: 1 } },
  { upsert: true }
);
~~~

Trong trường hợp đơn giản, gọi lại lệnh **$set language = vi** với cùng khóa chỉ đưa field đó về cùng giá trị; nhưng gọi lại **$inc requests = 1** sẽ tăng thêm một lần. Vì vậy:

> **Upsert không tự đồng nghĩa với idempotency.**

Nếu một request ghi **$set: {updatedAt: thời điểm hiện tại}**, gọi lại có thể làm thay đổi timestamp. Nếu một event dùng **$addToSet** với ID ổn định, khả năng chống trùng khác với **$push**. Nếu có side effect bên ngoài database, ngay cả một lệnh upsert idempotent cũng chưa bảo vệ chúng.

### Idempotency key cho checkout

Giả sử client gọi tạo order với:

~~~text
POST /orders
Idempotency-Key: checkout-req-123
~~~

API có thể sử dụng **insert** trên order với unique key **(tenantId, checkoutRequestId)**:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, checkoutRequestId: 1 },
  { unique: true, name: "uniq_checkout_intent" }
);
~~~

Lần đầu tạo order. Nếu response bị mất nhưng client retry cùng key, lần sau có thể gặp duplicate key. Ứng dụng **đọc lại order tương ứng và so fingerprint/payload** để biết đó thật sự là cùng ý định, rồi trả kết quả phù hợp, không tạo order thứ hai.

Nếu client dùng cùng idempotency key nhưng gửi **số lượng hoặc tổng tiền khác**, không được lặng lẽ coi đó là cùng yêu cầu. Cần từ chối hoặc áp dụng quy tắc sản phẩm rõ ràng.

## 16. Upsert của một bản đọc dẫn xuất khác insert nghiệp vụ

Một hệ thống có nguồn chính **orders** và read model **recentOrdersByCustomer**. Consumer nhận event **OrderUpdated** có thể viết:

~~~javascript
db.recentOrdersByCustomer.updateOne(
  {
    tenantId: "shop-a",
    orderId: "order-1001"
  },
  {
    $set: {
      customerId: "customer-07",
      status: "PAID",
      totalMinor: NumberLong("240000"),
      sourceVersion: 7
    },
    $setOnInsert: {
      createdInProjectionAt: ISODate("2026-11-14T11:20:00Z")
    }
  },
  { upsert: true }
);
~~~

Ở đây, upsert có ý nghĩa **“đảm bảo read model có một bản cho order này”**. Nó không tự tạo một order mới ở nguồn chính.

Tuy nhiên, nếu event **version 6** tới sau **version 7**, upsert không điều kiện ở trên có thể ghi lại status cũ. Cần bảo vệ bằng **sourceVersion**, thứ tự event hoặc cơ chế đối soát nguồn.

Một ví dụ điều kiện theo version chỉ để hình dung:

~~~javascript
db.recentOrdersByCustomer.updateOne(
  {
    tenantId: "shop-a",
    orderId: "order-1001",
    sourceVersion: { $lt: 8 }
  },
  {
    $set: {
      status: "PAID",
      sourceVersion: 8
    }
  }
);
~~~

Ví dụ này **không bật upsert** có chủ đích: nếu document chưa có thì không tạo. Muốn vừa **tạo khi thiếu**, vừa **chỉ cập nhật nếu version mới hơn**, không nên thêm **upsert: true** tùy tiện vào filter có điều kiện version; một document đã có với version cao sẽ không match và nhánh insert có thể va chạm unique key. Cần thiết kế workflow như **conditional create bằng unique key → nếu trùng thì conditional update**, hoặc cơ chế transaction/atomic pipeline có kiểm soát và retry theo khả năng engine.

Đây là ví dụ cho thấy **ý định create-if-missing và điều kiện update-if-newer có thể cần hai nhánh nghiệp vụ**, không phải một câu upsert chung bất kể điều kiện.

## 17. Ghi đè một phần nested object: lưu ý đường dẫn

Giả sử document:

~~~javascript
{
  _id: "profile-07",
  shippingAddress: {
    city: "Da Nang",
    street: "12 Nguyen Van Linh",
    postalCode: "550000"
  }
}
~~~

Hai update khác nhau:

~~~javascript
// Chỉ sửa city, giữ street và postalCode.
db.profiles.updateOne(
  { _id: "profile-07" },
  { $set: { "shippingAddress.city": "Hue" } }
);

// Thay toàn bộ object shippingAddress trong document.
db.profiles.updateOne(
  { _id: "profile-07" },
  { $set: { shippingAddress: { city: "Hue" } } }
);
~~~

Trong trường hợp thứ hai, object mới **không có street và postalCode**, nên những trường con đó bị mất khỏi **shippingAddress**. Mặc dù dùng **$set** chứ không dùng **replaceOne**, ta vẫn có thể **ghi đè nguyên một object con**.

Vì vậy, khi nhận request PATCH:

- Phân biệt **field vắng mặt** với field có giá trị **null**.
- Xác định request muốn **xóa field**, **đặt null** hay **không thay đổi**.
- Tránh serialize object con chỉ có một vài field rồi **$set** toàn bộ object.
- Nếu các service khác cùng sửa object, cân nhắc version check/CAS.

**Null không đồng nghĩa với unset**: **$set: {phone: null}** giữ field phone với giá trị null; **$unset: {phone: ""}** xóa field đó khỏi document.

## 18. Lost update: update và replace đều có thể ghi đè thay đổi mới

Giả sử hai nhân viên cùng mở hồ sơ khách:

~~~text
09:00  A đọc: {name:"An", phone:"111"}
09:00  B đọc: {name:"An", phone:"111"}

09:01  A sửa phone thành "222" và lưu
09:02  B sửa name thành "An Nguyen", nhưng gửi lại
       toàn bộ document cũ có phone:"111"
~~~

Nếu B dùng **replaceOne** với toàn bộ bản đọc trước đó, **phone** có thể quay lại **111**, làm mất cập nhật của A. Nếu B chỉ dùng **$set: {name:"An Nguyen"}**, phone mới của A được giữ; nhưng vẫn có thể có race nếu A và B cùng sửa **name**.

Một cách bảo vệ **optimistic concurrency** là lưu **revision**:

~~~javascript
{
  _id: "profile-07",
  tenantId: "shop-a",
  revision: 5,
  name: "An",
  phone: "111"
}
~~~

Khi B đã đọc revision 5, thao tác:

~~~javascript
const result = db.profiles.updateOne(
  {
    _id: "profile-07",
    tenantId: "shop-a",
    revision: 5
  },
  {
    $set: { name: "An Nguyen" },
    $inc: { revision: 1 }
  }
);

if (result.matchedCount === 0) {
  print("Version đã đổi hoặc document không tồn tại; đọc lại");
}
~~~

Nếu A cập nhật trước và tăng revision thành 6, B không còn match revision 5. B phải **đọc lại, giải quyết xung đột rồi thử lại**, thay vì tự bật upsert.

Điều kiện tiên quyết là **mọi writer tác động tới dữ liệu cần bảo vệ đều tăng revision nhất quán**. Nếu có job nền âm thầm sửa field mà không tăng revision, cơ chế này không phát hiện được xung đột ấy.

## 19. Insert, upsert và bất biến khi ghi đồng thời

### Trường hợp A — Tạo một bản ghi duy nhất

Yêu cầu: một email trong một tenant chỉ tạo tối đa một account.

Giải pháp: **insert với unique index**, xử lý duplicate key và xác minh payload/owner khi retry. Không cần tìm trước để bảo vệ uniqueness.

### Trường hợp B — Cấu hình tồn tại hoặc cập nhật

Yêu cầu: mỗi user có một preferences record, có thể chưa tồn tại ở lần đầu.

Giải pháp: **upsert với khóa danh tính duy nhất**, dùng **$set** cho trường đang cập nhật và **$setOnInsert** cho giá trị khởi tạo.

### Trường hợp C — Chuyển trạng thái đơn

Yêu cầu: chỉ **RESERVED → PAID**, không tạo order mới.

Giải pháp: **conditional update** trên **_id + tenantId + status**, **không upsert**.

### Trường hợp D — Thay cấu hình do hệ thống sở hữu trọn vẹn

Yêu cầu: deploy bản config mới, tất cả trường từ bản cũ phải được thay bằng cấu hình hiện tại.

Giải pháp: **replace** với cơ chế version/điều kiện nếu có writer đồng thời; chỉ bật upsert nếu muốn cho phép tạo config khi thiếu.

### Trường hợp E — Một sự kiện được giao nhiều lần

Yêu cầu: một provider event không được cộng tiền hai lần.

Giải pháp: **insert eventId duy nhất** để nhận diện sự kiện đã có, sau đó phối hợp lưu trạng thái xử lý và hiệu ứng nghiệp vụ bằng transaction/outbox/inbox hoặc workflow idempotent. Không chỉ dựa vào **upsert** bộ đếm.

## 20. Write result và lỗi cần được phân loại

Không phải lỗi ghi nào cũng nên retry như nhau.

| Tình huống | Ví dụ | Hướng xử lý |
|---|---|---|
| **Duplicate key** | Insert account có email đã có | Trả conflict hoặc đối chiếu idempotency |
| **Validation error** | totalMinor sai kiểu, status không hợp lệ | Sửa input/logic writer; không retry vô hạn |
| **MatchedCount = 0** | Update status với expected status không khớp | Kiểm tra trạng thái hiện tại; không tự tạo |
| **Transient network error** | Timeout khi gửi/nhận response | Có thể cần xác minh kết quả, retry theo cơ chế hỗ trợ và ID ổn định |
| **Write conflict** | Hai transaction đụng cùng dữ liệu | Retry transaction theo chính sách, kiểm soát contention |
| **Unauthorized / wrong tenant** | Client sửa ID không thuộc quyền | Từ chối; không chuyển thành thao tác tạo |
| **Schema/version conflict** | Revision không còn khớp | Đọc lại, hợp nhất hoặc báo người dùng giải quyết |
| **Rate limit / overload** | Quá nhiều ghi cùng hot key | Backoff, queue, giới hạn tải; tránh bão retry |

Ví dụ xử lý duplicate key trong JavaScript:

~~~javascript
try {
  db.orders.insertOne({
    _id: "order-2001",
    tenantId: "shop-a",
    externalOrderId: "web-2001",
    status: "PENDING"
  });
  print("CREATED");
} catch (error) {
  if (error.code === 11000) {
    print("DUPLICATE_KEY: cần đối chiếu record đã tồn tại");
  } else {
    throw error;
  }
}
~~~

Trong ví dụ **mongosh**, mã **11000** thường biểu thị lỗi duplicate key MongoDB. Mẫu xử lý lỗi cụ thể trong Node.js/Java/Spring Data sẽ khác hình dạng exception. Không nên nuốt mọi lỗi thành “đã tồn tại”, bởi lỗi mạng, quyền hoặc validation cần xử lý riêng.

## 21. Chọn _id ổn định giúp retry an toàn

So sánh hai cách tạo một job nhập dữ liệu:

**Cách không ổn định:**

~~~javascript
db.importedOrders.insertOne({
  tenantId: "shop-a",
  sourceOrderId: "source-501",
  amountMinor: 120000
  // Không cung cấp _id hoặc unique index theo sourceOrderId.
});
~~~

Nếu job bị timeout và chạy lại, mỗi lần insert có thể có ObjectId mới, làm tăng số order trùng nghĩa.

**Cách ổn định:**

~~~javascript
db.importedOrders.createIndex(
  { tenantId: 1, sourceOrderId: 1 },
  { unique: true }
);

db.importedOrders.insertOne({
  _id: "shop-a:source-501",
  tenantId: "shop-a",
  sourceOrderId: "source-501",
  amountMinor: 120000
});
~~~

Một key ổn định giúp phát hiện replay. Tuy nhiên, trước khi xây _id từ chuỗi ghép, cần quy tắc escaping/encoding để không tạo collision kiểu **("a:b","c")** và **("a","b:c")**. Một unique compound index thường rõ ràng hơn nếu các phần khóa có thể chứa ký tự phân cách.

Nếu bản ghi nguồn thay đổi có chủ đích, cần quyết định đó là **update một order đang tồn tại** hay **một phiên bản sự kiện mới**. Không dùng một unique key để vô tình ghi đè lịch sử bất biến.

## 22. Upsert khi filter rộng hoặc không ổn định

Lệnh sau rất dễ gây sai:

~~~javascript
db.products.updateOne(
  { category: "stationery" },
  { $set: { priceMinor: 90000 } },
  { upsert: true }
);
~~~

Nếu danh mục có 1.000 sản phẩm, **updateOne** chỉ cập nhật **một document khớp** theo cách chọn của database, không phải tất cả. Nếu chưa có sản phẩm nào trong category, upsert có thể tạo một document chỉ chứa category và price, **không có productId/title hợp lệ**.

Filter upsert cần định vị **một thực thể logic duy nhất**:

~~~javascript
db.products.updateOne(
  { tenantId: "shop-a", productId: "p-42" },
  {
    $set: {
      priceMinor: 90000,
      updatedAt: ISODate("2026-11-14T12:00:00Z")
    },
    $setOnInsert: {
      title: "Sổ tay A5",
      currency: "VND"
    }
  },
  { upsert: true }
);
~~~

Ngay cả vậy, chỉ dùng ví dụ này nếu nghiệp vụ thực sự cho phép **tạo sản phẩm p-42 khi thiếu**. Nếu thao tác là “đổi giá sản phẩm đã được duyệt”, cần **update-only**, vì việc tự tạo một sản phẩm chưa có đủ thông tin có thể vi phạm quy trình kiểm duyệt.

**updateMany với upsert:** nếu có những bản ghi khớp, nó cập nhật nhiều bản ghi. Nếu **không có bản ghi nào khớp**, upsert có thể tạo **một** document mới, không phải tạo một document cho mỗi phần tử mà ứng dụng tưởng tượng. Vì vậy, không nên dùng **updateMany(..., {upsert: true})** để “tạo nhiều thực thể thiếu” mà không thiết kế rõ khóa và dữ liệu đầu vào.

## 23. Tạo mới và cập nhật trong bulkWrite

Khi đồng bộ dữ liệu theo batch, MongoDB cung cấp **bulkWrite** với nhiều kiểu thao tác:

~~~javascript
db.products.bulkWrite(
  [
    {
      insertOne: {
        document: {
          _id: "p-51",
          tenantId: "shop-a",
          title: "Bút đỏ",
          priceMinor: 12000
        }
      }
    },
    {
      updateOne: {
        filter: { _id: "p-42", tenantId: "shop-a" },
        update: { $set: { priceMinor: 90000 } },
        upsert: false
      }
    },
    {
      updateOne: {
        filter: { _id: "p-52", tenantId: "shop-a" },
        update: {
          $set: { title: "Giấy ghi chú" },
          $setOnInsert: { createdAt: ISODate("2026-11-14T12:00:00Z") }
        },
        upsert: true
      }
    }
  ],
  { ordered: false }
);
~~~

Đây là một batch chứa **ba ý định khác nhau**: tạo mới, cập nhật-only và upsert. Kết quả bulk có những thống kê như số inserted/matched/modified/upserted theo API.

**ordered: false** giúp tiếp tục những thao tác không phụ thuộc nhau khi một thao tác lỗi, nhưng không khiến mọi lỗi tự biến mất hoặc batch có tính nguyên tử toàn phần. Với các thao tác có phụ thuộc thứ tự, phải thiết kế workflow và transaction/ordering phù hợp, không chỉ đổi ordered.

Bulk write có thể giảm overhead của nhiều request nhưng vẫn cần kiểm soát retry, unique index, idempotency, kết quả từng thao tác và kích thước batch.

## 24. Khi một thao tác chạm nhiều document

Giả sử checkout có hai bước:

~~~text
1. Tạo order mới.
2. Giảm stock trong inventory.
~~~

Lưu một order bằng insert và giảm tồn bằng update là **hai thao tác trên hai document**. Nếu một bước thành công và bước kia thất bại, hệ thống có thể rơi vào trạng thái dở dang.

Một transaction MongoDB trong deployment hỗ trợ có thể nhóm những thay đổi cần nguyên tử trong phạm vi database. Nhưng:

- Vẫn cần unique index để tránh hai order có cùng ý định.
- Vẫn cần update tồn kho **có điều kiện**, chẳng hạn **availableStock >= quantity**.
- Transaction có chi phí, giới hạn và tình huống write conflict/commit result không chắc chắn.
- Lời gọi cổng thanh toán ngoài database **không tự rollback** cùng transaction.
- Nếu workflow trải nhiều dịch vụ, cần idempotency/reservation/saga/outbox hoặc một cơ chế phối hợp khác.

**Upsert không phải một transaction xuyên nhiều aggregate.** Đừng dùng “tạo nếu thiếu” để thay thế thiết kế bất biến nghiệp vụ nhiều bước.

## 25. Phân biệt thao tác trên MongoDB với các hệ NoSQL khác

### Redis: SET, NX, XX và ghi đè key

Trong Redis:

~~~redis
SET profile:customer-07 "{\"name\":\"An\"}"

SET profile:customer-07 "{\"name\":\"An Nguyen\"}"

SET profile:customer-07 "{\"name\":\"Binh\"}" NX

SET profile:customer-07 "{\"name\":\"Binh\"}" XX
~~~

Ý nghĩa:

| Lệnh/điều kiện | Khi key chưa có | Khi key đã có |
|---|---|---|
| **SET key value** | Tạo | Ghi đè value hiện tại |
| **SET key value NX** | Tạo | Không ghi |
| **SET key value XX** | Không ghi | Ghi đè value |

Trong Redis, **SET** với value JSON String thường thay **toàn value**, không tự merge các field bên trong JSON. Nếu value là Hash, **HSET** có thể thêm/cập nhật **một field** mà không thay toàn bộ Hash.

Một hệ dùng **GET rồi SET NX** vẫn cần hiểu kết quả SET và những writer khác đang chạy. Không được coi GET trước đó là một khóa đồng bộ.

Redis còn có TTL, transaction/script và Redis Cluster với giới hạn thao tác nhiều key. Khi dùng SET để thay một key đang có TTL, cần xem các tùy chọn giữ TTL hay tạo TTL mới theo lệnh cụ thể; không mặc định lifetime của key được giữ nguyên trong mọi hình thức ghi.

### DynamoDB: PutItem và UpdateItem

DynamoDB có hai nhóm thao tác dễ nhầm:

**PutItem** đặt một item theo primary key. Nếu item đã có, một **PutItem không điều kiện** có thể **thay thế toàn bộ item**, không phải chỉ thêm các attribute còn thiếu.

**UpdateItem** sửa attribute theo UpdateExpression và điều kiện; mặc định có thể tạo item khi key chưa tồn tại nếu thao tác/biểu thức cho phép. Muốn update-only, cần **ConditionExpression** thích hợp, ví dụ **attribute_exists(PK)** với primary key thực tế.

Muốn **create-only** khi PutItem, dùng condition như:

~~~text
ConditionExpression:
  attribute_not_exists(PK)
~~~

Các điều kiện này được xử lý tại thao tác ghi và giúp chống cạnh tranh tốt hơn “GetItem rồi PutItem”. Trong bảng có partition key/sort key, phải thiết kế điều kiện cho item và khóa đúng theo schema bảng; không sử dụng placeholder **PK** như một cột có thật nếu bảng được đặt tên khóa khác.

Ví dụ phân biệt:

| Ý định | DynamoDB ứng viên |
|---|---|
| Chỉ tạo item chưa có | PutItem + ConditionExpression attribute_not_exists(key) |
| Thay toàn item nếu cho phép | PutItem không điều kiện hoặc thao tác có điều kiện phù hợp |
| Cập nhật field của item đã có | UpdateItem + điều kiện exists |
| Tăng bộ đếm | UpdateItem với biểu thức số và kiểm soát retry/idempotency |
| Nhiều item phải cùng thỏa điều kiện | TransactWriteItems trong giới hạn hỗ trợ |

### Cassandra: INSERT vốn có ngữ nghĩa upsert

Trong Cassandra CQL, **INSERT** thông thường không mang ý nghĩa “chỉ chèn khi khóa chưa tồn tại” như MongoDB **insertOne**. Với cùng primary key, ghi các giá trị mới có thể **upsert** các cột tương ứng.

Ví dụ:

~~~sql
-- Ví dụ trên keyspace demo đã tạo sẵn
CREATE TABLE demo.preferences (
  tenant_id text,
  customer_id text,
  language text,
  theme text,
  PRIMARY KEY ((tenant_id, customer_id))
);

INSERT INTO demo.preferences
  (tenant_id, customer_id, language)
VALUES ('shop-a', 'customer-07', 'vi');

INSERT INTO demo.preferences
  (tenant_id, customer_id, language)
VALUES ('shop-a', 'customer-07', 'en');
~~~

Sau hai lệnh, giá trị **language** được ghi lại theo quy tắc xung đột/timestamp của Cassandra; không nên suy rằng lệnh thứ hai bị từ chối vì key đã tồn tại. Các cột **không được nêu trong INSERT** không tự có ngữ nghĩa “replace toàn row” giống MongoDB **replaceOne**; behavior còn phụ thuộc writes, null và tombstones.

Nếu cần **chỉ tạo khi chưa có**, Cassandra hỗ trợ điều kiện **IF NOT EXISTS** theo ngữ nghĩa lightweight transaction (LWT):

~~~sql
INSERT INTO demo.preferences
  (tenant_id, customer_id, language)
VALUES ('shop-a', 'customer-08', 'vi')
IF NOT EXISTS;
~~~

LWT có thêm chi phí phối hợp, cần chọn khi thực sự cần tính duy nhất/compare-and-set ở phạm vi hỗ trợ. Không được suy rằng một **INSERT** CQL thông thường tương đương SQL INSERT có unique constraint trên mọi bộ khóa logic.

### Couchbase: tên API thường biểu thị rõ ý định

Ở giao diện key–value/document của Couchbase, các thao tác thường có tên phân biệt **insert**, **upsert** và **replace**:

- **insert:** chỉ tạo document khi key chưa tồn tại; báo lỗi nếu key đã có.
- **upsert:** tạo nếu thiếu hoặc cập nhật/ghi đè document khi key đã có theo API tương ứng.
- **replace:** thay document đã tồn tại; báo lỗi nếu không tìm thấy.

Couchbase cũng có **CAS (compare-and-swap)** để bảo vệ chống lost update. Cần đọc tài liệu và dùng đúng SDK/phiên bản, vì ngữ nghĩa chi tiết về expiry, durability và return value có thể khác các ví dụ MongoDB.

## 26. Bảng đối chiếu đa hệ

| Hệ | Chỉ tạo khi chưa có | Tạo hoặc sửa | Sửa chỉ khi đã có | Nguy cơ ghi đè |
|---|---|---|---|---|
| MongoDB | insertOne + unique key | updateOne upsert | updateOne mặc định | replaceOne hoặc $set object con |
| Redis | SET NX | SET | SET XX / HSET theo ngữ nghĩa key | SET thay toàn value |
| DynamoDB | PutItem với condition not exists | PutItem/UpdateItem theo ngữ nghĩa lệnh | UpdateItem với condition exists | PutItem thay item |
| Cassandra | INSERT IF NOT EXISTS (LWT) | INSERT/UPDATE CQL thường có thể upsert | Conditional UPDATE/IF EXISTS tùy mục đích | Ghi lại cột theo timestamp/conflict rules |
| Couchbase | insert | upsert | replace | upsert/replace thay document theo API |

Bảng cho thấy **tên “INSERT” không đủ để suy ra create-only**. Khi chuyển từ MongoDB sang Cassandra hoặc DynamoDB, cần viết lại điều kiện ghi theo API sản phẩm thay vì dịch máy móc tên lệnh.

## 27. Quyền truy cập và tenant phải nằm trong đường ghi

Một API nhận:

~~~text
PATCH /orders/order-1001
Body: { tenantId: "shop-a", status: "CANCELLED" }
~~~

không được mặc định **tenantId** do client gửi là đáng tin. Nếu người dùng của **shop-b** truyền ID thuộc **shop-a**, một update chỉ lọc theo **_id** có thể sửa dữ liệu trái phép.

Một filter minh họa:

~~~javascript
db.orders.updateOne(
  {
    _id: "order-1001",
    tenantId: authenticatedTenantId,
    customerId: authenticatedCustomerId,
    status: "PENDING"
  },
  {
    $set: { status: "CANCELLED" }
  }
);
~~~

**authenticatedTenantId** và **authenticatedCustomerId** phải đến từ ngữ cảnh xác thực/ủy quyền đã kiểm chứng, không phải body tự khai. Các vai trò khác như nhân viên và quản trị viên có thể có đường ghi khác theo chính sách.

Nếu dùng **upsert** cho endpoint vốn chỉ sửa một record thuộc quyền, filter sai tenant có thể không match rồi **thử tạo record mới** ngoài ý định. Đây là một lý do nữa để xác định rõ **create-only, update-only hoặc create-or-update** ở tầng API.

Không được lấy **upsert thành công** làm bằng chứng thao tác được phép; authorization phải được thực thi trước và trong điều kiện dữ liệu phù hợp.

## 28. Ghi đè và schema evolution

Giả sử phiên bản ứng dụng cũ chỉ biết:

~~~javascript
{
  _id: "profile-07",
  name: "An",
  phone: "111"
}
~~~

Phiên bản mới đã bổ sung:

~~~javascript
{
  _id: "profile-07",
  name: "An",
  phone: "111",
  consent: {
    marketingEmail: false
  },
  schemaVersion: 2
}
~~~

Nếu client cũ đọc document rồi **replaceOne** bằng bản không có **consent**, field mới biến mất. Vấn đề này đặc biệt nguy hiểm với các trường quyền riêng tư, trạng thái đồng ý, audit hoặc version.

Những lựa chọn bảo vệ:

1. **Patch/update từng field** do client được phép sở hữu.
2. **Schema validation** để từ chối replacement làm thiếu trường bắt buộc.
3. **Version/CAS** để không ghi đè từ dữ liệu đọc cũ.
4. **API chuyển đổi phiên bản**: client cũ gửi ý định thay đổi, server cập nhật document hiện tại thay vì chấp nhận toàn document từ client.
5. **Migration có giai đoạn tương thích** trước khi loại field cũ.

Upsert có thể khiến vấn đề khó thấy hơn: một bộ cập nhật vốn chỉ có vài trường có thể tạo **document mới thiếu field bắt buộc** nếu không có **$setOnInsert**, defaults hoặc validation.

## 29. TTL, soft delete và tái tạo bản ghi đã xóa

Giả sử tài khoản được **soft delete**:

~~~javascript
{
  _id: "profile-07",
  deletedAt: ISODate("2026-11-14T12:00:00Z"),
  status: "DELETED"
}
~~~

Một job đồng bộ cũ chạy:

~~~javascript
db.profiles.updateOne(
  { externalId: "customer-07", status: "ACTIVE" },
  { $set: { displayName: "An" } },
  { upsert: true }
);
~~~

Vì record hiện tại không còn **ACTIVE**, filter có thể không match và upsert thử tạo record mới. Nếu không có uniqueness đúng trên logical identity, job có thể **làm xuất hiện hồ sơ mới** dù tài khoản đã bị xóa.

Với soft delete, phải xác định:

- ID logical vẫn dành riêng hay có được tái sử dụng?
- Data pipeline có được phép tạo lại đối tượng đã xóa không?
- Có **tombstone/deletion ledger/version** để chặn sự kiện cũ không?
- Unique index áp dụng cho mọi record hay chỉ record active?
- Khi restore backup, làm sao áp dụng lại trạng thái xóa?

Với TTL, dọn vật lý thường bất đồng bộ và không bảo đảm bản ghi biến mất đúng một mili giây cụ thể. Một upsert sau khi dữ liệu hết hạn hoặc được dọn cần tuân theo **hợp đồng vòng đời**, chứ không được tự suy “không có record thì tạo mới là hợp lệ”.

## 30. Quan sát kết quả ghi trong vận hành

Để biết ứng dụng có đang dùng insert/upsert đúng ý định hay không, có thể theo dõi:

| Metric | Ý nghĩa |
|---|---|
| insert_success_total | Số insert tạo mới thành công |
| duplicate_key_total | Tỷ lệ xung đột khóa duy nhất |
| update_matched_total | Số update tìm thấy document |
| update_no_match_total | Số update không match; có thể là xung đột trạng thái/tenant/missing |
| upsert_insert_total | Số lần upsert thực sự chèn mới |
| upsert_update_total | Số lần upsert đi nhánh cập nhật |
| replace_total | Số lần thay toàn document |
| optimistic_conflict_total | Số lần revision/CAS không còn khớp |
| retry_after_timeout_total | Số lần request lặp do kết quả chưa rõ |
| idempotency_replay_total | Số yêu cầu lặp được nhận diện |
| schema_validation_failure_total | Số ghi không đạt hợp đồng dữ liệu |
| projection_stale_event_total | Số event cũ bị chặn khỏi ghi đè read model |

Không phải mọi hệ/driver tự xuất toàn bộ các metric trên. Đây là **nhóm chỉ số ứng viên ở tầng ứng dụng/vận hành**, cần định nghĩa cách đo cụ thể.

Một dấu hiệu đáng kiểm tra: API mang tên **“update profile”** nhưng **upsert_insert_total tăng đột biến**. Có thể filter đang sai tenant, sai kiểu ID hoặc ngầm tạo document mới mỗi khi không match.

Tương tự, **duplicate_key_total** tăng sau khi triển khai import job có thể cho thấy retry nhiều, producer lặp ID hoặc dữ liệu cũ đã tồn tại; không nên tự kết luận đó là lỗi hoàn toàn nếu idempotency được thiết kế từ đầu.

## 31. Các tình huống thử nghiệm quan trọng

| Thử nghiệm | Trạng thái ban đầu | Hành động | Kết quả kỳ vọng |
|---|---|---|---|
| Insert mới | Chưa có key | insertOne | Tạo 1 document |
| Insert trùng | Đã có _id | insertOne cùng _id | Duplicate key, không sửa bản cũ |
| Update missing | Chưa có key | updateOne không upsert | matchedCount=0, không tạo |
| Upsert missing | Chưa có key | updateOne upsert=true | Tạo document; có upsertedId |
| Upsert existing | Đã có key | updateOne upsert=true | Sửa field; createdAt không bị $setOnInsert đổi |
| Update no-op | Giá trị mới bằng cũ | $set cùng giá trị | matched=1, modified có thể 0 |
| Replace thiếu field | Đã có phone, createdAt | replaceOne chỉ có name | Field không nêu bị loại |
| Patch nested field | Có city, street | $set address.city | Giữ street |
| Ghi đồng thời | Hai request tạo cùng key | Insert/upsert | Unique constraint chặn hai document trùng |
| CAS conflict | Revision đã tăng | Update với revision cũ | matchedCount=0 |
| Retry $inc | Request đếm bị lặp | Upsert với $inc | Có nguy cơ đếm hai lần nếu không có idempotency |
| State transition | Order CANCELLED | Update PENDING → PAID | Không match; không tạo |
| Wrong tenant | Order của shop-b | Request shop-a cập nhật | Không có sửa ngoài quyền |
| Event sai thứ tự | Read model version 8 | Consumer nhận version 7 | Không hạ version |
| Soft-deleted | Record đã DELETED | Job đồng bộ cũ upsert ACTIVE | Không tái tạo sai theo hợp đồng xóa |

Trong test concurrency, cần chạy các thao tác gần như đồng thời và kiểm tra **trạng thái dữ liệu cuối**; chỉ kiểm tra HTTP 200/409 chưa đủ để chứng minh không tạo trùng hoặc không bị mất cập nhật.

## 32. Quy trình quyết định thao tác ghi

~~~mermaid
flowchart TD
    A["Yêu cầu ghi nghiệp vụ"] --> B{"Bản ghi phải tồn tại trước?"}
    B -->|"Có"| C["Update-only/replace-only có điều kiện"]
    B -->|"Không"| D{"Nếu đã tồn tại có được sửa?"}
    D -->|"Không"| E["Insert/conditional create"]
    D -->|"Có"| F{"Muốn sửa một số field hay toàn record?"}
    F -->|"Một số field"| G["Update operators + upsert nếu cần"]
    F -->|"Toàn record"| H["Replace/upsert có kiểm soát"]
    C --> I["Đặt filter theo identity + state/version"]
    E --> J["Unique key + xử lý duplicate"]
    G --> K["Khóa identity, $setOnInsert, uniqueness"]
    H --> L["Đảm bảo replacement đầy đủ + CAS"]
    I --> M["Retry, idempotency và quyền"]
    J --> M
    K --> M
    L --> M
    M --> N["Đọc write result, đo và kiểm chứng"]
~~~

Các câu hỏi cần trả lời trước khi viết lệnh:

1. **Thao tác được phép tạo mới không?** Nếu không, tuyệt đối không bật upsert.
2. **Bản ghi được định danh bằng gì?** _id, composite key hay external ID có unique constraint?
3. **Nếu đã tồn tại thì phải làm gì?** Từ chối, sửa một field, merge có quy tắc hay thay toàn bộ?
4. **Field nào chỉ được đặt khi tạo?** createdAt, chủ sở hữu, nguồn ban đầu; cân nhắc $setOnInsert.
5. **Field nào tuyệt đối không được sửa?** Snapshot lịch sử, khóa danh tính, dữ liệu tài chính đã chốt.
6. **Có writer đồng thời không?** Cần state condition, version/CAS hoặc transaction?
7. **Request có thể được gửi lại không?** $inc/$push, external side effect và việc tạo ID ngẫu nhiên có làm trùng không?
8. **Quyền truy cập được xác minh ở đâu?** Tenant và owner phải được xác thực đáng tin cậy.
9. **Kết quả ghi được hiểu thế nào?** Matched, modified, upserted, duplicate, timeout.
10. **Bản sao và dữ liệu đã xóa xử lý ra sao?** Read model, replay và TTL có được phép tạo lại record?

## 33. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách làm đúng |
|---|---|---|
| “INSERT ở mọi NoSQL đều chỉ tạo mới” | Cassandra INSERT thường có ngữ nghĩa upsert | Đọc API của engine cụ thể |
| “Upsert luôn an toàn khi chạy lại” | $inc/$push và side effects có thể lặp | Dùng key/idempotency và ngữ nghĩa operator phù hợp |
| “Upsert tự chặn record trùng” | Không có unique index, hai writer có thể cùng chèn | Khóa danh tính và unique constraint |
| “Filter có status giúp upsert chặt chẽ hơn” | Status đổi khiến filter không match và nhánh insert có thể xảy ra | Conditional update không upsert cho state transition |
| “Replace chỉ sửa field đã gửi” | Replacement có thể loại mọi field không được nêu | Dùng $set cho patch |
| “$set object con giống $set dotted path” | $set cả object thay tất cả field con | Dùng dotted path khi chỉ sửa một field |
| “modifiedCount=0 nghĩa là không tồn tại” | Có thể match nhưng no-op | Phân biệt matchedCount/modifiedCount |
| “GET rồi insert là chống trùng” | Race giữa hai request | Unique key và conditional create |
| “Timeout nghĩa là chưa ghi” | Server có thể đã commit trước khi response mất | Retry có kiểm soát và xác minh theo key |
| “Tạo _id mới mỗi lần retry là vô hại” | Có thể tạo trùng thực thể nghiệp vụ | Dùng logical key ổn định |
| “Một upsert là transaction nhiều bảng” | Chỉ một thao tác tại ranh giới hỗ trợ | Transaction/workflow khi có nhiều record/dịch vụ |
| “Cập nhật read model không cần version” | Event cũ có thể ghi đè giá trị mới | Version, CAS, replay/đối soát |
| “Dữ liệu bị xóa thì upsert tạo lại luôn đúng” | Có thể hồi sinh soft-deleted record | Quy tắc lifecycle/tombstone |
| “Dùng replace để đồng bộ schema cho nhanh” | Client cũ xóa field do client mới tạo | Patch, version và validation |

## 34. Bài tập thực hành

### Bài tập 1 — Phân biệt bốn thao tác

Một API có bốn yêu cầu: **tạo order**, **sửa địa chỉ của order đã tồn tại**, **đảm bảo preferences của user tồn tại**, **thay toàn cấu hình của một job**. Hãy chọn insert, update-only, upsert hoặc replace cho từng yêu cầu. Nêu điều gì xảy ra khi khóa đã tồn tại và khi chưa tồn tại.

### Bài tập 2 — Đọc kết quả update

Cho ba kết quả:

~~~javascript
{ matchedCount: 0, modifiedCount: 0, upsertedCount: 1 }
{ matchedCount: 1, modifiedCount: 1, upsertedCount: 0 }
{ matchedCount: 1, modifiedCount: 0, upsertedCount: 0 }
~~~

Hãy giải thích nhánh nào đã chạy. Vì sao kết quả thứ ba không đủ để khẳng định update thất bại?

### Bài tập 3 — Chống trùng khi tạo order

Hai request cùng muốn tạo order với **tenantId=shop-a** và **externalOrderId=web-1001**. Viết unique compound index và insertOne. Mô tả kết quả khi hai request đến gần như đồng thời, và cách phân biệt duplicate do retry với một payload khác ý định.

### Bài tập 4 — Upsert có $setOnInsert

Thiết kế customerPreferences gồm **tenantId**, **customerId**, **language**, **theme**, **createdAt**, **updatedAt**. Viết updateOne upsert=true để createdAt chỉ được đặt khi tạo. Nêu cần unique index nào và kết quả nếu request lặp lại.

### Bài tập 5 — Nguy cơ replaceOne

Document có **name**, **phone**, **address**, **consent**. Client cũ chỉ gửi **name** và **phone** qua replaceOne. Hãy nêu những field sẽ bị mất và viết lại bằng updateOne/$set để chỉ đổi name và phone.

### Bài tập 6 — Cập nhật object con

Document có **shippingAddress.city**, **street**, **postalCode**. So sánh:

~~~javascript
{ $set: { shippingAddress: { city: "Hue" } } }
{ $set: { "shippingAddress.city": "Hue" } }
~~~

Trường nào giữ nguyên và trường nào có thể bị loại?

### Bài tập 7 — Trạng thái đơn hàng

Một webhook muốn chuyển order **PENDING → PAID**, nhưng order có thể đã **CANCELLED**. Vì sao **upsert: true** là lựa chọn sai? Viết conditional update và mô tả cách phân loại matchedCount=0.

### Bài tập 8 — Ghi đồng thời và revision

Hai nhân viên mở profile revision 5. Một người đổi phone, người kia đổi name dựa trên dữ liệu cũ. Thiết kế update có **revision = 5** và tăng revision nguyên tử. Giải thích cách nhận biết xung đột và xử lý sau khi đọc lại.

### Bài tập 9 — Retry bộ đếm

Job nhận một event ID **evt-77**, chạy **$inc: {dailyCount: 1}**, sau đó timeout và retry. Tại sao upsert không ngăn đếm hai lần? Đề xuất một cơ chế inbox/dedup theo event ID rồi mới cập nhật counter, nêu ranh giới transaction hoặc đối soát cần thiết.

### Bài tập 10 — So sánh các NoSQL engine

Với mục tiêu “chỉ tạo user khi key chưa có”, viết phương án phù hợp cho **MongoDB**, **Redis**, **DynamoDB** và **Cassandra**. Giải thích tại sao **INSERT** trong Cassandra không đồng nghĩa **insertOne** trong MongoDB.

### Bài tập 11 — Read model theo phiên bản

Consumer nhận event của order theo thứ tự version **7, 9, 8**. Hãy đề xuất cách bảo vệ trạng thái version 9 không bị version 8 ghi đè, và cách xử lý khi bản read model chưa tồn tại. Vì sao filter **sourceVersion < incomingVersion** với upsert=true không tự giải quyết mọi tình huống?

### Bài tập 12 — Soft delete và đồng bộ

Một profile bị đánh dấu **DELETED**, nhưng job import cũ tiếp tục upsert theo điều kiện **status=ACTIVE**. Hãy phân tích nguy cơ tái tạo record, chọn khóa logical và quy tắc tombstone/version để chặn dữ liệu cũ.

### Bài tập 13 — Bulk import có duplicate

Một batch 1.000 order có 20 ID đã tồn tại. So sánh **insertMany ordered=true**, **ordered=false** và **bulkWrite với upsert** theo mục tiêu: dữ liệu gốc là lịch sử bất biến, còn metadata có thể cập nhật. Nêu cách checkpoint, phân loại lỗi và không ghi đè giao dịch cũ.

### Bài tập 14 — Bảo vệ tenant

API cho phép khách tự gửi **tenantId** trong request body rồi sửa document bằng _id. Hãy chỉ ra rủi ro khi dùng update hoặc upsert. Viết filter dựa trên tenant/customer từ ngữ cảnh xác thực và state hiện tại, đồng thời xác định trường hợp nào cần từ chối tạo.

### Bài tập 15 — Thiết kế theo ý định nghiệp vụ

Một đồng nghiệp đề xuất thay tất cả **insertOne**, **updateOne** và **replaceOne** bằng một hàm **save(record)** tự động upsert để “đơn giản hóa code”. Hãy lập bảng những nghiệp vụ có thể bị sai: tạo order, thanh toán, chuyển trạng thái, đổi profile, cập nhật schema, event replay và xóa tài khoản. Đề xuất API ghi có tên thể hiện rõ ý định và điều kiện bảo vệ.

---

**Kết luận:** Khi viết CRUD trên NoSQL, câu hỏi quan trọng nhất không phải **“lệnh nào ghi được dữ liệu?”** mà là **“nghiệp vụ cho phép tạo, cập nhật hay thay thế trong điều kiện nào?”**. **Insert** thể hiện ý định tạo mới và cần khóa duy nhất để ngăn trùng; **update** sửa phạm vi xác định của bản ghi đã có; **upsert** kết hợp tạo và sửa nhưng đòi hỏi logical key, unique constraint và xử lý retry; **replace** có thể xóa những trường không có trong bản thay thế. Khi có ghi đồng thời, event trùng, nhiều tenant hoặc state machine, phải bổ sung **conditional write, version/CAS, idempotency và kiểm chứng kết quả**. Chọn đúng thao tác ghi nghĩa là bảo vệ ý nghĩa dữ liệu, không chỉ làm cho một câu lệnh chạy thành công.
