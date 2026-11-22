# Bất biến nghiệp vụ và điều kiện dữ liệu phải luôn thỏa mãn

Thiết kế dữ liệu NoSQL không chỉ là chọn cách lưu document, key hay partition sao cho truy vấn nhanh. Một hệ thống còn phải bảo vệ những điều kiện mà nghiệp vụ **không cho phép bị vi phạm**: tồn kho không âm khi chốt bán; một chỗ ngồi không thể được bán cho hai người trong cùng suất; tổng tiền của đơn khớp với các dòng hàng; giao dịch thanh toán không bị áp dụng hai lần; người dùng không được sửa dữ liệu thuộc tổ chức khác.

Những điều kiện ấy được gọi là **bất biến nghiệp vụ (business invariants)**. Chúng là đầu vào quan trọng để quyết định **nhóm dữ liệu nào cần ở cùng một ranh giới cập nhật**, thao tác ghi nào phải có điều kiện, khi nào cần transaction, và khi nào có thể chấp nhận xử lý bất đồng bộ.

Bài học dùng một hệ thống bán hàng và đặt chỗ làm ví dụ. Các câu lệnh minh họa chủ yếu dựa trên MongoDB, sau đó đối chiếu với Redis, DynamoDB và Cassandra. Mục tiêu không phải học thuộc cú pháp của từng engine, mà là đi từ **quy tắc nghiệp vụ → điều kiện dữ liệu → phạm vi bảo vệ → thao tác ghi đúng khi có cạnh tranh → bằng chứng kiểm chứng kết quả**.

## 1. Bất biến không phải chỉ là “dữ liệu hợp lệ”

Một **bất biến** là một mệnh đề phải đúng đối với những trạng thái hệ thống mà nghiệp vụ công nhận là hợp lệ. Bất biến có thể nói về một trường, nhiều trường trong một bản ghi, hoặc nhiều thực thể và thao tác khác nhau.

Ví dụ:

| Phát biểu nghiệp vụ | Biểu diễn thành điều kiện dữ liệu |
|---|---|
| Không bán quá tồn khả dụng | **availableStock ≥ 0** sau mọi lần giữ/trừ tồn hợp lệ |
| Một dòng hàng phải có số lượng dương | **quantity > 0** |
| Tổng tiền đơn khớp với dữ liệu đã chốt | **orderTotal = Σ(quantity × unitPriceAtPurchase)**, sau khi áp dụng quy tắc thuế/giảm giá đã công bố |
| Không có hai vé được xác nhận cho cùng ghế và suất | Với mỗi **(showId, seatId)**, tối đa một **active claim** theo quy tắc trạng thái |
| Một mã yêu cầu thanh toán không được xử lý hai lần | Một **idempotencyKey** chỉ ánh xạ đến một kết quả nghiệp vụ được xác định |
| Không được xác nhận đơn đã bị hủy | Chuyển trạng thái phải nằm trong tập cạnh hợp lệ của state machine |
| Người dùng chỉ sửa dữ liệu của tenant được cấp quyền | Tất cả thay đổi phải gắn với **tenantId** và quyền được xác thực |

Ngược lại, **“trang chủ phải tải trong 200 ms”** là yêu cầu hiệu năng, không phải bất biến dữ liệu. **“Số đếm trên dashboard cập nhật trong vòng 30 giây”** là yêu cầu về độ mới và vận hành; nó có thể cho phép bản đọc tạm thời khác với nguồn chính.

Để biến một phát biểu mơ hồ thành hợp đồng có thể triển khai, hãy hỏi:

1. **Điều kiện chính xác là gì?** Có đơn vị tiền, giới hạn, ngưỡng, trạng thái và trường hợp ngoại lệ nào?
2. **Phạm vi nào phải cùng thỏa mãn?** Một field, một document, một key hay một tập thực thể?
3. **Điều kiện cần đúng tại thời điểm nào?** Trước khi xác nhận ghi, trước khi trả kết quả thành công, hay sau một khoảng đồng bộ cho phép?
4. **Ai có thể làm điều kiện sai?** Hai request đồng thời, retry, consumer nhận sự kiện trễ, tác vụ TTL hay sửa tay?
5. **Nếu thất bại giữa chừng thì sao?** Dữ liệu giữ nguyên, rollback, ghi trạng thái đang xử lý hay có bước bù?
6. **Đo và kiểm tra bằng cách nào?** Trạng thái dữ liệu nào chứng minh thao tác đã bảo vệ điều kiện?

Một bất biến chỉ được viết trong tài liệu nhưng không gắn với **điểm thực thi** và **cách xác minh** thì chưa đủ để bảo vệ hệ thống.

## 2. Phân biệt bất biến tức thời và kết quả được phép hội tụ

Trong hệ phân tán, không phải mọi dữ liệu dẫn xuất đều cần cập nhật ngay cùng lúc. Vì vậy, chữ **“luôn”** phải được hiểu ở phạm vi trạng thái mà hệ thống cam kết, không được dùng để ngụ ý mọi replica, cache và màn hình sẽ nhìn thấy một bản cập nhật cùng một mili giây.

| Loại điều kiện | Ví dụ | Mức bảo đảm nghiệp vụ cần |
|---|---|---|
| **Bất biến cứng (hard invariant)** | Không tạo hai active seat claim cho cùng ghế | Không được xác nhận hai thao tác mâu thuẫn như đều thành công |
| **Bất biến trong một aggregate** | Tổng tiền và các dòng hàng đã chốt của một order nhất quán | Một thao tác thay đổi aggregate không được để trạng thái chốt dở dang thành hợp lệ |
| **Bất biến chuyển trạng thái** | CANCELLED không tự chuyển sang PAID | Chỉ cho phép cạnh chuyển trạng thái đã định nghĩa |
| **Điều kiện hội tụ (eventual consistency objective)** | Dashboard số đơn cập nhật theo event | Có thể trễ trong một khoảng được quy định và phải có cơ chế hồi phục |
| **Điều kiện thời gian (temporal rule)** | Reservation hết hạn sau 10 phút nếu chưa thanh toán | Phải định nghĩa mốc hết hạn, hành vi đọc và tác vụ dọn |
| **Điều kiện bảo mật** | Người dùng không xem được order của tenant khác | Kiểm soát ở mọi đường đọc/ghi, không phụ thuộc dữ liệu có đồng bộ hay chưa |

Ví dụ, một đơn mới được chốt và lưu thành công ở nguồn chính, nhưng dashboard tổng đơn vẫn hiện số cũ trong vài giây. Nếu sản phẩm cho phép dashboard trễ tối đa 30 giây, đó không nhất thiết là vi phạm. Ngược lại, một API trả **“đã đặt ghế thành công”** cho hai người cùng ghế lại vi phạm quy tắc kinh doanh ngay ở bước xác nhận.

Đừng diễn đạt “tất cả dữ liệu phải nhất quán tức thì” khi nghiệp vụ chỉ cần một vài điều kiện không thể vi phạm. Hãy **phân loại từng điều kiện** để chọn đúng cơ chế, tránh trả giá transaction hoặc đồng bộ toàn hệ thống ở những nơi không cần.

## 3. Ví dụ xuyên suốt: đặt đơn hàng từ một kho sản phẩm

Giả sử hệ thống bán sản phẩm **BOOK-01**, tồn khả dụng ban đầu là **5 quyển**. Có hai khách hàng cùng lúc đặt **4 quyển**. Nghiệp vụ yêu cầu:

- Không xác nhận bán quá lượng tồn có thể đáp ứng.
- Mỗi đơn có một ID và tập dòng hàng đã chốt.
- Không thanh toán trùng khi cổng thanh toán gửi webhook lại.
- Một lần hủy phải hoàn tồn/hoàn tiền theo chính sách, không hoàn hai lần.
- Tổng tiền đơn được tính từ đơn giá đã chốt, không đổi khi catalog tăng giá sau đó.

Một cách tách dữ liệu theo **nguồn sở hữu quy tắc**:

~~~text
products / catalog
  productId, title, currentPrice

inventory
  productId, availableStock

orders
  orderId, customerId, items[], orderTotal, status

payments / paymentEvents
  providerEventId, orderId, amount, status

read models
  dashboardCount, recentOrders, searchIndex...
~~~

Các nhóm này có liên quan, nhưng **không phải mọi trường phải nằm cùng một document**. Một order sở hữu snapshot dòng hàng; inventory thuộc sản phẩm và được chia sẻ bởi nhiều order; payment có định danh sự kiện riêng; dashboard là dữ liệu dẫn xuất.

~~~mermaid
flowchart TD
    A["Quy tắc nghiệp vụ"] --> B["Xác định bất biến"]
    B --> C{"Bất biến nằm trong một đơn vị dữ liệu?"}
    C -->|Có| D["Thiết kế atomic update/conditional write ở đơn vị đó"]
    C -->|Không| E["Transaction, reservation hoặc workflow nhiều bước"]
    D --> F["Xử lý concurrent requests và retry"]
    E --> F
    F --> G["Kiểm chứng trạng thái + lỗi một phần"]
    G --> H["Đưa vào quan sát vận hành"]
~~~

Quy tắc định hướng: **những trường cùng tạo thành một bất biến thường nên ở gần nhau để có thể được kiểm tra và cập nhật trong một ranh giới đủ mạnh**. Tuy nhiên, nếu các thực thể được chia sẻ rộng, tăng vô hạn hoặc có vòng đời độc lập, việc nhúng chúng vào một bản ghi có thể gây vấn đề lớn hơn lợi ích.

## 4. Viết bất biến thành công thức và trạng thái

Một số bất biến có thể diễn đạt bằng toán học:

### 4.1. Ràng buộc giá trị

\[
\text{quantity}_i \in \mathbb{Z},\quad \text{quantity}_i > 0
\]

\[
\text{availableStock} \in \mathbb{Z},\quad \text{availableStock} \ge 0
\]

Số lượng phải là số nguyên dương khi tạo dòng hàng. Nếu UI cho nhập **1,5 quyển**, việc tự động cắt thành 1 mà không thông báo có thể sai nghiệp vụ. Quy tắc làm tròn hoặc đơn vị đo cần được định nghĩa trước khi kiểm tra dữ liệu.

### 4.2. Ràng buộc giữa nhiều trường

Với một đơn không áp dụng thuế/phí/giảm giá ở ví dụ đơn giản:

\[
\text{orderTotal}
=\sum_{i=1}^{n}\text{quantity}_i\cdot\text{unitPriceAtPurchase}_i
\]

Nếu có thuế, phí giao hàng, khuyến mãi hay quy tắc làm tròn, công thức phải nêu rõ từng thành phần. Đừng đưa dữ liệu tiền dưới dạng số thực nhị phân rồi kỳ vọng mọi phép tính thập phân chính xác tuyệt đối; có thể dùng **đơn vị tiền nhỏ nhất dạng integer** hoặc kiểu decimal phù hợp với currency.

### 4.3. Ràng buộc duy nhất

Với một ghế thuộc một suất:

\[
\forall\,(\text{showId}, \text{seatId}):
\quad\#(\text{activeClaims})\le 1
\]

Điều kiện này áp dụng trên **tất cả thao tác đặt ghế đồng thời**. Không thể chỉ kiểm tra trong bộ nhớ của một instance API.

### 4.4. Ràng buộc chuyển trạng thái

Ví dụ:

~~~mermaid
flowchart LR
    A["CREATED"] -->|"đã giữ tồn"| B["RESERVED"]
    B -->|"thanh toán hợp lệ"| C["PAID"]
    A -->|"hủy"| D["CANCELLED"]
    B -->|"hết hạn/hủy"| D
    C -->|"quy trình hoàn"| E["REFUND_PENDING"]
    E -->|"hoàn thành"| F["REFUNDED"]
~~~

Các cạnh hợp lệ là một phần của hợp đồng nghiệp vụ. Ví dụ này **không** có cạnh trực tiếp từ **CANCELLED → PAID**. Nếu webhook thanh toán đến sau lúc hủy, hệ thống phải có cách giải quyết như từ chối áp dụng, xử lý hoàn hoặc chuyển vào quy trình ngoại lệ; không được tùy tiện ghi **PAID** chỉ vì nhận được event.

Không có state machine chung cho mọi sản phẩm. Với hàng hóa vật lý, giao hàng và hoàn tiền có thể có trạng thái riêng; với nội dung số, việc cấp quyền truy cập lại có điều kiện khác.

## 5. Xác định ranh giới nhóm dữ liệu từ bất biến

Giả sử đơn hàng có 2 dòng:

~~~javascript
{
  _id: "order-101",
  tenantId: "shop-a",
  customerId: "customer-17",
  status: "CREATED",
  currency: "VND",
  items: [
    {
      sku: "BOOK-01",
      quantity: 2,
      unitPriceAtPurchase: 80000
    },
    {
      sku: "PEN-02",
      quantity: 1,
      unitPriceAtPurchase: 100000
    }
  ],
  orderTotal: 260000
}
~~~

Tập **items + orderTotal + currency + status** mô tả một order; người dùng thường đọc chúng cùng nhau và một số quy tắc cần giữ nhất quán khi chốt đơn. Với đơn có số lượng dòng hàng nhỏ và giới hạn rõ, một **MongoDB document** là một ứng viên hợp lý.

Nếu orderTotal nằm ở document A còn items ghi ở nhiều document B/C mà API cho phép hiển thị order như đã chốt trước khi cả ba ghi hoàn tất, dữ liệu có thể bị lệch. Việc gom dữ liệu thuộc một order vào một document giảm số lần phối hợp cần thiết cho bất biến nội bộ của order.

Tuy vậy, **availableStock** không nên nhúng vào order, vì một SKU được chia sẻ bởi nhiều đơn. Nếu mỗi đơn lưu bản sao tồn kho rồi cùng giảm, các bản sao sẽ bất đồng và không còn nguồn sự thật để chống bán quá.

| Nhóm dữ liệu | Bất biến chủ yếu | Ranh giới ứng viên |
|---|---|---|
| Dòng hàng và tổng đơn | Các giá trị đã chốt của một order phải khớp nhau | Một order document nếu kích thước cho phép |
| Tồn của một SKU | Không giảm khả dụng xuống dưới 0 | Một inventory record được cập nhật có điều kiện |
| Đăng ký vào khóa học | Không tạo hai quan hệ hiện hành cho một cặp | Unique key/index của enrollment |
| Một ghế trong một suất | Tối đa một claim hiện hành | Seat claim theo (showId, seatId) với khóa duy nhất |
| Thanh toán một sự kiện | Một provider event chỉ có tác dụng một lần | Event/inbox/idempotency record có định danh duy nhất |
| Tổng số đơn trên dashboard | Phản ánh nguồn order trong giới hạn độ trễ được phép | Read model có đối soát và replay |

**Một nghiệp vụ có thể cần nhiều ranh giới.** Thiết kế aggregate tốt là tìm phạm vi **nhỏ nhất nhưng đủ bảo vệ bất biến**, không gom toàn bộ hệ thống thành một “aggregate siêu lớn”.

## 6. Kiểm tra ở API, schema và database là các lớp khác nhau

Một validation trong API giúp trả lỗi rõ ràng:

~~~javascript
function validateOrderInput(items) {
  if (!Array.isArray(items) || items.length === 0) {
    throw new Error("Order must have at least one item");
  }

  for (const item of items) {
    if (!Number.isSafeInteger(item.quantity) || item.quantity <= 0) {
      throw new Error("Quantity must be a positive safe integer");
    }
  }
}
~~~

Đây là validation trong ứng dụng, chưa ngăn các writer khác ghi dữ liệu sai nếu họ bỏ qua cùng quy tắc. Database có thể cung cấp validation kiểu dữ liệu, khóa duy nhất hoặc điều kiện cập nhật để tạo **lớp bảo vệ chung**.

Ví dụ MongoDB schema validator để chặn dữ liệu tồn kho có số âm hoặc không phải integer theo mẫu:

~~~javascript
db.createCollection("inventory", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "availableStock"],
      properties: {
        sku: { bsonType: "string" },
        availableStock: {
          bsonType: ["int", "long"],
          minimum: 0
        }
      }
    }
  },
  validationAction: "error"
});
~~~

Validator giúp từ chối một số document sai cấu trúc khi ghi, nhưng chưa giải quyết **hai request cùng đọc tồn = 5 rồi đều muốn trừ 4**. Ràng buộc dữ liệu tĩnh và kiểm soát cạnh tranh là hai vấn đề khác nhau.

Cũng không nên mặc định validator dạng JSON Schema đã tính được mọi công thức giữa nhiều phần tử mảng hoặc bảo vệ mọi logic thanh toán. Với bất biến **orderTotal = tổng dòng hàng**, ứng dụng cần tính và xác minh theo quy tắc, và chọn thao tác ghi/transaction đủ để lưu chúng nhất quán.

## 7. Cạnh tranh ghi: đọc rồi ghi có thể vi phạm bất biến

Ví dụ tồn kho ban đầu là 5:

~~~text
Tồn kho BOOK-01 = 5

Request A: đọc thấy 5; khách muốn 4
Request B: đọc thấy 5; khách muốn 4

A: kiểm tra 5 >= 4 -> đúng
B: kiểm tra 5 >= 4 -> đúng

A: ghi giảm tồn 4
B: ghi giảm tồn 4
~~~

Nếu cả hai thao tác ghi được chấp nhận mà không có kiểm tra nguyên tử trên trạng thái mới nhất, hệ thống có thể bán 8 quyển trong khi chỉ có 5. Với cách ghi đè giá trị đã tính trong bộ nhớ, còn có thể xảy ra **lost update**: hai request đều ghi tồn mới = 1, khiến dữ liệu kho trông hợp lệ nhưng số đơn xác nhận vượt khả năng đáp ứng.

**Điểm thực thi bất biến phải nằm trong thao tác ghi cạnh tranh**, không chỉ trong một truy vấn kiểm tra trước đó.

### MongoDB: cập nhật có điều kiện trên một inventory document

Giả sử collection **inventory** lưu:

~~~javascript
{
  _id: "BOOK-01",
  tenantId: "shop-a",
  availableStock: 5
}
~~~

Để giữ 4 quyển, dùng điều kiện **availableStock ≥ 4** ngay trong phép cập nhật:

~~~javascript
const requestedQuantity = 4;

const result = db.inventory.findOneAndUpdate(
  {
    _id: "BOOK-01",
    tenantId: "shop-a",
    availableStock: { $gte: requestedQuantity }
  },
  {
    $inc: { availableStock: -requestedQuantity }
  },
  {
    returnDocument: "after"
  }
);

if (result === null) {
  print("Không đủ tồn, hoặc bản ghi không tồn tại/không đúng tenant");
} else {
  print("Tồn khả dụng sau cập nhật:", result.availableStock);
}
~~~

Lệnh minh họa **mongosh**. Với dữ liệu ban đầu là 5, yêu cầu đầu tiên thành công để lại 1. Yêu cầu thứ hai đòi giữ 4 không còn thỏa điều kiện, nên **không được trừ tiếp**. Sự đúng đắn ở đây đến từ **filter và update được áp dụng nguyên tử trên cùng document**, không đến từ lệnh GET trước đó.

Vẫn cần kiểm tra đầu vào **requestedQuantity** là số nguyên dương và có phạm vi hợp lệ. Nếu số lượng bằng -4 mà ứng dụng không kiểm tra, phép **$inc: {availableStock: 4}** sẽ làm tăng tồn — trái ý nghĩa nghiệp vụ.

**Lưu ý:** ví dụ chỉ bảo vệ tồn kho của một SKU. Đơn có nhiều SKU cần phối hợp nhiều inventory records; cũng cần ghi nhận ai đã giữ hàng, cho đơn nào, và bảo đảm retry không trừ tồn nhiều lần.

## 8. Tính duy nhất phải chống được hai request đồng thời

Giả sử hai request đồng thời cố tạo đăng ký cho cặp **(tenantId, studentId, courseId)**. Cách làm:

~~~text
findOne -> chưa tồn tại
insertOne -> tạo enrollment
~~~

không đủ nếu cả hai request đều **findOne** trước khi bên nào insert.

Một MongoDB unique compound index bảo vệ bất biến:

~~~javascript
db.enrollments.createIndex(
  { tenantId: 1, studentId: 1, courseId: 1 },
  { unique: true, name: "uniq_enrollment_pair" }
);
~~~

Khi hai writer tạo cùng bộ khóa, chỉ một document được phép tồn tại theo ràng buộc unique của index. Writer còn lại phải xử lý lỗi duplicate key dựa trên nghiệp vụ: có thể trả “đã đăng ký”, hoặc báo xung đột nếu trạng thái/thuộc tính của đăng ký hiện tại khác ý định.

**Một unique index không thay thế các kiểm tra khác**: nó không chứng minh student hay course có thật, không tự kiểm tra tenant của hai đối tượng tham chiếu, và không quyết định liệu khóa học đã đóng đăng ký chưa.

### Khi unique chỉ áp dụng cho một số trạng thái

Với ghế xem phim, giả sử cần ngăn hai **active claim**, nhưng vẫn giữ lịch sử claim đã hủy. Có thể chọn một collection **activeSeatClaims** chỉ chứa claim đang giữ/xác nhận, còn lịch sử được lưu nơi khác.

~~~javascript
db.activeSeatClaims.createIndex(
  { showId: 1, seatId: 1 },
  { unique: true, name: "uniq_active_seat" }
);
~~~

Một document mẫu:

~~~javascript
{
  _id: "claim-009",
  showId: "show-71",
  seatId: "A12",
  customerId: "customer-17",
  status: "HELD",
  expiresAt: ISODate("2026-11-14T09:10:00Z")
}
~~~

Đặt ghế dùng **insert** (hoặc thao tác có điều kiện tương đương); unique index bảo vệ mỗi cặp **showId + seatId**. Khi claim hết hạn, cần có **quy trình thu hồi có điều kiện** để giải phóng ghế an toàn. Không được kết luận rằng một **TTL index** sẽ xóa claim đúng ngay giây hết hạn, bởi dọn TTL là bất đồng bộ; đường đặt ghế phải xử lý trạng thái hết hạn một cách có bảo vệ đồng thời.

Nếu nghiệp vụ định nghĩa **HELD** và **CONFIRMED** khác nhau về quyền chuyển trạng thái, logic cập nhật phải phản ánh điều đó. Giữ lịch sử ngoài active collection cũng cần thiết kế write order, idempotency và đối soát, để không tạo khoảng hở cho hai claim hiện hành khi thao tác lỗi.

## 9. Bất biến chuyển trạng thái: từ chối sự kiện đến sai thứ tự

Trong hệ phân tán, event có thể bị gửi lại hoặc tới muộn. Giả sử order đang **CANCELLED**, nhưng một consumer nhận sự kiện thanh toán **PAID** từ trước lúc hủy.

Một cập nhật không điều kiện:

~~~javascript
db.orders.updateOne(
  { _id: "order-101" },
  { $set: { status: "PAID" } }
);
~~~

có thể làm đơn bị hủy trở lại PAID mà không qua quy tắc nghiệp vụ.

Thay bằng cập nhật có điều kiện:

~~~javascript
db.orders.updateOne(
  {
    _id: "order-101",
    tenantId: "shop-a",
    status: "RESERVED"
  },
  {
    $set: {
      status: "PAID",
      paidAt: ISODate("2026-11-14T09:05:00Z")
    }
  }
);
~~~

Nếu order không còn **RESERVED**, **matchedCount = 0** và không có chuyển trạng thái nào diễn ra. Tầng nghiệp vụ cần phân biệt:

- Order đã ở **PAID** vì cùng event trước đó được xử lý: retry nên được đối xử idempotent.
- Order đã **CANCELLED**: có thể cần xử lý hoàn tiền hoặc ngoại lệ.
- Order không tồn tại hoặc không đúng tenant: là lỗi dữ liệu/quyền.
- Trạng thái khác **RESERVED**: có thể là bất thường của workflow.

Một filter không đủ để phân biệt mọi nguyên nhân; có thể cần đọc trạng thái hiện tại sau khi ghi có điều kiện thất bại và xử lý theo hợp đồng.

### Tại sao trạng thái và event ID nên được bảo vệ cùng nhau?

Nếu một webhook được nhận hai lần, chỉ ghi **status: "PAID"** lần hai có thể không thay đổi status, nhưng các tác vụ đi kèm như **cộng điểm thưởng**, **phát hành vé** hoặc **gửi hàng** vẫn có thể chạy lần hai. Cần quy tắc **một event hợp lệ chỉ tạo một tác dụng nghiệp vụ**, không chỉ “status cuối cùng trông đúng”.

## 10. Idempotency: một yêu cầu lặp lại không được tạo tác dụng lặp

Mạng có thể timeout sau khi database đã commit nhưng trước khi client nhận được phản hồi. Client có lý do để retry. Nếu mỗi lần retry tạo một order mới, tổng tiền hoặc tồn kho có thể bị ghi trùng.

Một **idempotency key** xác định một *ý định nghiệp vụ*; các lần lặp của cùng ý định phải được nhận diện.

~~~text
POST /orders
Idempotency-Key: checkout-req-123

Lần 1:
  server commit order nhưng response mất

Lần 2:
  client retry cùng idempotency key
  -> hệ thống trả lại kết quả cũ / trạng thái hiện tại
  -> không tạo order khác
~~~

Có thể dùng một collection yêu cầu hoặc một khóa duy nhất trên order:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, checkoutRequestId: 1 },
  { unique: true, name: "uniq_checkout_request" }
);
~~~

Với một yêu cầu **checkout-req-123**, chỉ một order có thể mang bộ **(tenantId, checkoutRequestId)**. Khi gặp duplicate key, không nên đơn giản trả “thành công” nếu payload lần retry khác lần đầu; cần so sánh fingerprint/thuộc tính quan trọng hoặc từ chối việc tái sử dụng key cho ý định khác.

Ràng buộc unique là một phần. Nếu thao tác tạo order còn có bước trừ tồn, gửi payment và phát event, cần đảm bảo **idempotency trên từng hiệu ứng** hoặc quy trình phối hợp toàn bộ các bước. Không được chỉ gắn request ID vào API rồi mặc định mọi side effect an toàn.

Một thiết kế inbox cho webhook có thể lưu **providerEventId** duy nhất, cùng trạng thái xử lý. Nếu consumer crash giữa ghi “đã nhận” và áp dụng hiệu ứng, cần cơ chế trạng thái/transaction/retry để không bỏ quên event. **Đánh dấu DONE** chỉ sau khi hiệu ứng bắt buộc đã thực sự hoàn tất.

## 11. Giao dịch nhiều document: khi ranh giới đơn lẻ chưa đủ

Giả sử nghiệp vụ yêu cầu thao tác **trừ tồn và tạo order** phải cùng thành công hoặc không được xác nhận thành công. Vì hai dữ liệu nằm ở hai document, cập nhật có điều kiện tồn kho riêng và tạo order riêng có thể gây lỗi một phần:

~~~text
Trừ tồn thành công
        |
        v
Tạo order thất bại do lỗi mạng hoặc duplicate key
        |
        v
Tồn bị giữ nhưng không có order tương ứng
~~~

Nếu cần tính nguyên tử giữa các ghi trong cùng MongoDB deployment hỗ trợ transaction, có thể dùng transaction nhiều document. Ví dụ **Node.js MongoDB driver**, rút gọn để minh họa cơ chế:

~~~javascript
const session = client.startSession();

try {
  await session.withTransaction(async () => {
    const inventory = client.db("shop").collection("inventory");
    const orders = client.db("shop").collection("orders");

    const result = await inventory.updateOne(
      {
        _id: "BOOK-01",
        tenantId: "shop-a",
        availableStock: { $gte: 4 }
      },
      { $inc: { availableStock: -4 } },
      { session }
    );

    if (result.modifiedCount !== 1) {
      throw new Error("INSUFFICIENT_STOCK");
    }

    await orders.insertOne(
      {
        _id: "order-101",
        tenantId: "shop-a",
        checkoutRequestId: "checkout-req-123",
        status: "RESERVED",
        items: [{ sku: "BOOK-01", quantity: 4, unitPriceAtPurchase: 80000 }],
        orderTotal: 320000
      },
      { session }
    );
  });
} finally {
  await session.endSession();
}
~~~

Đây là ví dụ **cấu trúc giao dịch**, không phải một endpoint production đầy đủ: trước đó phải kiểm tra input, quyền, giá, các SKU và tính toán tiền. Transaction cần deployment MongoDB phù hợp, cấu hình write concern/read concern đúng yêu cầu, xử lý lỗi có thể retry và các trường hợp kết quả commit chưa xác định do mạng. Với một giao dịch nhiều SKU còn phải xử lý giới hạn, cạnh tranh ghi và khả năng deadlock/write conflict.

**Không đặt lời gọi cổng thanh toán bên ngoài bên trong transaction DB rồi cho rằng nó có thể rollback cùng database.** Transaction chỉ điều phối những thao tác thuộc phạm vi hỗ trợ của database; một HTTP call đã thu tiền không tự được hoàn tác khi transaction database thất bại.

Transaction cũng không thay thế ràng buộc unique hay kiểm tra trạng thái: hai workflow cùng chạy vẫn cần bảo vệ bất biến bằng điều kiện và khóa đúng.

## 12. Khi trải qua nhiều dịch vụ: reservation và quy trình bù

Quy trình đặt hàng hoàn chỉnh có thể gồm inventory service, order service và payment provider. Không có một transaction đơn giản nào tự bao trùm tất cả các hệ độc lập ấy.

Một **workflow/saga** có thể đi theo các bước:

~~~mermaid
flowchart TD
    A["Nhận checkout request có idempotency key"] --> B["Tạo order PENDING"]
    B --> C["Giữ tồn kho có điều kiện"]
    C -->|"Thành công"| D["Gửi yêu cầu thanh toán idempotent"]
    C -->|"Không đủ tồn"| X["Hủy order, trả lỗi"]
    D -->|"Thanh toán thành công"| E["Chuyển order sang PAID"]
    D -->|"Thất bại đã xác nhận"| F["Giải phóng reservation"]
    F --> G["Chuyển order sang CANCELLED"]
    D -->|"Timeout/không rõ kết quả"| H["Đối soát trạng thái payment"]
    H --> D
~~~

Đây là sơ đồ khái niệm: **không nên retry thu tiền vô hạn** khi chưa biết lần gọi trước đã thành công hay chưa. Cần định danh giao dịch ở payment provider, khả năng truy vấn trạng thái và chính sách bù/hoàn tiền rõ.

Những bất biến xuyên dịch vụ cần được biến thành **điều kiện ở mỗi bước**:

| Bước | Điều kiện phải bảo vệ | Cơ chế ứng viên |
|---|---|---|
| Tạo order | Không tạo hai đơn cho một checkoutRequestId | Unique key, idempotent create |
| Giữ tồn | Không giữ quá stock; một order không giữ hai lần | Conditional update và reservationId duy nhất |
| Thanh toán | Một payment intent không thu hai lần | Provider idempotency key, đối soát |
| Xác nhận đơn | Chỉ PAID khi payment thực sự hợp lệ | State transition có điều kiện |
| Hủy/giải phóng | Không hoàn tồn hai lần | Reservation state và idempotent release |
| Read model | Cuối cùng phản ánh order hợp lệ | Event replay, dedup, reconciliation |

Tồn kho có thể theo dõi **available**, **reserved**, **committed**. Nhưng bất biến giữa ba trường chỉ có ý nghĩa nếu định nghĩa rõ nguồn dữ liệu và thao tác chuyển số lượng. Ví dụ:

\[
\text{physicalStock}
=\text{available}+\text{reserved}+\text{allocated}
\]

đúng **chỉ khi** nghiệp vụ định nghĩa đủ những trạng thái này, không có hàng hỏng/hàng chờ nhập, và các thao tác được ghi nhận theo đúng mô hình. Không nên sao chép công thức này mà bỏ qua điều chỉnh tồn kho, nhập hàng, trả hàng hay các trạng thái khác.

### Vì sao workflow cần trạng thái bền vững?

Nếu dịch vụ chết sau khi giữ tồn nhưng trước khi gọi thanh toán, hệ thống cần biết **reservationId** nào đang chờ, ai sở hữu, hạn giữ tới đâu và bước tiếp theo là gì. Một biến local trong tiến trình không đủ. Có thể lưu trạng thái saga, dùng outbox/event và các job quét tiến trình treo để retry/bù an toàn.

Nếu cần ghi dữ liệu và phát event cùng một quyết định nghiệp vụ, **transactional outbox** là một phương án: ghi thay đổi nguồn và một bản ghi outbox trong cùng transaction database, sau đó worker phát event và consumer xử lý idempotent. Outbox không bảo đảm event chỉ được giao đúng một lần cho mọi consumer; nó cung cấp cơ sở để **không mất sự kiện do lỗi giữa commit dữ liệu và publish**, khi được triển khai và vận hành phù hợp.

## 13. So sánh bảo vệ bất biến ở một số hệ NoSQL

Không nên suy từ tên **NoSQL** rằng tất cả hệ thống đều không có transaction, hay tất cả chỉ bảo đảm eventual consistency. Cơ chế khác nhau theo engine, kiểu dữ liệu, triển khai và cấu hình.

| Hệ thống | Cơ chế liên quan bất biến | Ví dụ phù hợp | Giới hạn phải đọc kỹ |
|---|---|---|---|
| **MongoDB** | Atomic write trên một document, unique index, conditional update, multi-document transaction | Không trừ tồn âm trên một SKU, chặn duplicate enrollment, nhóm order | Transaction nhiều document có chi phí; kiểm tra điều kiện xuyên dịch vụ vẫn do ứng dụng |
| **Redis** | Lệnh nguyên tử trên key, transaction/Lua script/Functions và optimistic locking | Counter, giới hạn quota hoặc giữ slot trong phạm vi key | Nhiều lệnh liên tiếp không tự là một giao dịch; Redis Cluster có hạn chế thao tác nhiều key |
| **DynamoDB** | Conditional writes, version check/optimistic locking, TransactWriteItems trong giới hạn hỗ trợ | Chặn tồn âm theo item, chống ghi trùng, ghi nhiều item có transaction | Partition hot, transaction limit, retry và consistency của các đường đọc |
| **Cassandra** | Conditional statement/LWT dùng khi cần compare-and-set theo phạm vi hỗ trợ | Một khóa trạng thái chỉ chuyển khi vẫn giữ giá trị mong đợi | LWT có thêm round trips/chi phí; batch thường không tương đương ACID transaction rộng |
| **Document/Key–value khác** | Phụ thuộc API, transaction/index/consistency của sản phẩm | Ràng buộc theo đơn vị lưu | Không suy đoán khả năng chỉ từ nhãn “document” hoặc “wide-column” |

### DynamoDB: điều kiện ngay trong UpdateItem

Ở mức biểu thức, một thao tác trừ tồn có thể dùng:

~~~text
Key:
  PK = "PRODUCT#BOOK-01"

UpdateExpression:
  SET availableStock = availableStock - :qty

ConditionExpression:
  attribute_exists(PK) AND availableStock >= :qty

ExpressionAttributeValues:
  :qty = 4
~~~

Đây là **mẫu biểu thức** cho UpdateItem; khi gọi API thật phải cung cấp kiểu thuộc tính và cấu trúc tham số theo SDK/DynamoDB API đang dùng. Nếu condition không thỏa, thao tác bị từ chối theo cơ chế conditional write và không được trừ tồn. Khi cần cùng ghi nhiều item, phải đánh giá transaction API và giới hạn của nó thay vì tự nối hai UpdateItem độc lập.

### Redis: kiểm tra và giảm số trong một script

Nếu tồn kho của một SKU nằm trong một Redis String số nguyên, một Lua script có thể kiểm tra và giảm số trong một đơn vị thực thi:

~~~lua
-- KEYS[1]: key chứa availableStock của một SKU
-- ARGV[1]: lượng cần giữ, số nguyên dương
local current = tonumber(redis.call('GET', KEYS[1]))
local quantity = tonumber(ARGV[1])

if not current or not quantity or quantity <= 0 or quantity % 1 ~= 0 then
  return {err = 'INVALID_STOCK_OR_QUANTITY'}
end

if current < quantity then
  return 0
end

redis.call('DECRBY', KEYS[1], quantity)
return 1
~~~

Script giúp tránh vòng đọc–ghi tách rời trên key đó. Cần xác định giới hạn số, khả năng chuyển đổi từ byte String sang integer, persistence, retry và cơ chế đồng bộ với order. Redis script **không tự bảo vệ một inventory record nằm ở database khác** hoặc một payment provider bên ngoài.

### Cassandra: compare-and-set bằng LWT

Với bảng chứa hàng tồn của một SKU, có thể dùng **lightweight transaction (LWT)** trên giá trị kỳ vọng:

~~~sql
-- Minh họa CQL: inventory_by_sku có primary key (sku)
-- Trước đó ứng dụng đã đọc available_stock = 10
UPDATE inventory_by_sku
SET available_stock = 6
WHERE sku = 'BOOK-01'
IF available_stock = 10;
~~~

Nếu phiên ghi khác đã đổi **available_stock** sau lần đọc, điều kiện **IF** thất bại và ứng dụng phải đọc lại/quyết định retry. Đây là mô hình **optimistic compare-and-set**, không phải phép toán tự động **available_stock = available_stock - 4** trong CQL thường. Cần đo chi phí LWT và quản lý contention khi một SKU cực kỳ nóng.

Mẫu trên minh họa cơ chế bảo vệ trạng thái của **một khóa**, không có nghĩa có thể dùng một câu IF để giao dịch nguyên tử qua hàng nghìn SKU hoặc các dịch vụ khác.

## 14. Tránh nhầm “đọc nhất quán” với “ghi bảo vệ bất biến”

Giả sử hai client cùng đọc tồn kho = 5. Ngay cả khi mỗi phép đọc trả trạng thái mới nhất tại **thời điểm đọc**, cả hai vẫn có thể đọc 5 trước khi bên nào ghi. Nếu sau đó gửi ghi không điều kiện, tình huống tranh chấp vẫn tồn tại.

Vì vậy:

- **Strongly consistent read** không thay thế **conditional update** khi dữ liệu có thể đổi giữa đọc và ghi.
- **Version check / compare-and-set** giúp phát hiện giá trị đã thay đổi trong khoảng ấy.
- **Unique constraint** giúp bảo vệ tính duy nhất ngay cả khi nhiều writer đều tin mình là người đầu tiên.
- **Transaction isolation** phải đủ để bảo vệ bất biến cụ thể; không nên suy rằng mọi giao dịch đều an toàn khỏi mọi dạng write skew.
- **Idempotency** xử lý lặp lại cùng một ý định, không thay thế kiểm tra số lượng hoặc quyền.

Một ví dụ **write skew**: hai nhân viên cùng trực; nghiệp vụ yêu cầu luôn còn ít nhất một người trực. Hai transaction cùng đọc “A và B đều đang trực”, sau đó transaction 1 tắt trạng thái A, transaction 2 tắt trạng thái B. Nếu hệ thống cho phép cả hai commit độc lập mà không phát hiện xung đột phù hợp, kết quả là **không còn ai trực**.

Ví dụ này cho thấy: khi bất biến phụ thuộc **tập dữ liệu**, dù mỗi transaction sửa một record riêng, vẫn cần chọn cách đồng bộ/khóa/ràng buộc/serializable coordination phù hợp hoặc **thiết kế lại dữ liệu để một điểm kiểm soát chung** bảo vệ điều kiện. Không thể chỉ kiểm tra mỗi record sau khi ghi.

## 15. Những điều kiện xuyên nhiều đối tượng cần được định vị

Một bất biến thường có thể chuyển thành câu hỏi về **khóa kiểm soát**:

| Bất biến | Khóa/điểm kiểm soát ứng viên | Rủi ro khi phạm vi sai |
|---|---|---|
| Không hai claim cho cùng ghế | (showId, seatId) | Tạo claim trùng ở hai document |
| Không vượt tồn một SKU | (tenantId, sku) | Nhiều order cùng trừ vượt tổng |
| Một username/email duy nhất trong tenant | (tenantId, normalizedEmail) | Trùng do viết hoa, chuẩn hóa sai hoặc cập nhật đồng thời |
| Không thanh toán trùng một provider event | (provider, providerEventId) | Một event làm tăng tiền/điểm hai lần |
| Không có hơn một membership hiện hành cho cặp | (tenantId, groupId, userId) | Một cặp xuất hiện hai record hiện hành |
| Hạn mức dùng tài nguyên theo tenant | (tenantId, quotaPeriod) | Các request ở nhiều node cùng vượt hạn mức |

Lựa chọn key cần xét cả **mức chia sẻ** và **phân bố tải**. Một counter quota tập trung theo tenant thuận tiện bảo vệ hạn mức, nhưng tenant rất lớn có thể gây **hot key**. Sharding counter có thể giảm điểm nóng, đổi lại giới hạn toàn tenant khó bảo vệ tức thì hơn. Nếu quota cứng không được vượt, phải thiết kế cơ chế cấp quota nhỏ cho shard, reservation hoặc một điểm kiểm soát phù hợp, không chỉ cộng các shard theo nền rồi hy vọng tổng không vượt.

### Vấn đề chuẩn hóa định danh

Một ràng buộc “email duy nhất” phải nói rõ email được so sánh thế nào: chuẩn hóa Unicode, khoảng trắng, chữ hoa/chữ thường, chính sách riêng của địa chỉ và tenant. Nếu cùng một người đăng ký **A@example.com** và **a@example.com**, hệ thống phải dùng quy tắc so sánh đã được phê duyệt; database unique index trên chuỗi gốc chưa chắc phản ánh định nghĩa nghiệp vụ.

Không nên tự động bỏ dấu, loại ký tự hoặc thay đổi địa chỉ email tùy tiện; chuẩn hóa phải theo yêu cầu sản phẩm và quy tắc phù hợp, để tránh gộp nhầm hai định danh thực sự khác nhau.

## 16. Quan hệ tham chiếu và bất biến toàn vẹn dữ liệu

Document database có thể lưu **order.customerId** và **enrollment.courseId** mà không tự tạo khóa ngoại. Một ID tham chiếu có thể chỉ tới bản ghi đã bị xóa hoặc thuộc tenant khác.

Các bất biến cần xác định:

- Một order hợp lệ phải thuộc khách hàng nào? Nếu khách bị xóa, order có được giữ theo chính sách lưu chứng từ hay không?
- Một enrollment phải trỏ đến khóa học và học viên thuộc cùng tenant không?
- Có được tạo enrollment khi khóa học đang **CLOSED**?
- Khi xóa một khóa học, những quan hệ còn lại phải bị chặn, xóa, chuyển trạng thái hay giữ snapshot?

Một kiểm tra “course tồn tại” trước khi insert enrollment có thể bị **race** với thao tác xóa course. Nếu bắt buộc không tạo quan hệ đến đối tượng đang bị xóa, các workflow tạo/xóa phải phối hợp trạng thái hoặc transaction đủ mạnh.

Một cách mô hình hóa thường dùng là đặt **lifecycle state** cho thực thể chia sẻ:

~~~text
OPEN -> CLOSING -> CLOSED -> DELETING
~~~

Trong giai đoạn **CLOSING/DELETING**, đường tạo quan hệ từ chối ghi mới. Tác vụ dọn quan hệ có thể chạy theo batch với checkpoint và đối soát. Đây là một lựa chọn thiết kế, không phải cơ chế khóa ngoại tự có của mọi hệ NoSQL.

**Không nên coi thiếu kết quả $lookup là lý do để im lặng bỏ một quan hệ lỗi khỏi báo cáo vận hành.** Nếu nghiệp vụ yêu cầu toàn vẹn tham chiếu, cần có cách phát hiện orphan và xử lý.

## 17. Giới hạn TTL và hết hạn: thời điểm logic khác thời điểm dọn vật lý

Một reservation giữ ghế trong 10 phút có thể có:

~~~javascript
{
  _id: "hold-901",
  showId: "show-71",
  seatId: "A12",
  status: "HELD",
  expiresAt: ISODate("2026-11-14T09:10:00Z")
}
~~~

Bất biến nghiệp vụ là **không cho phép một hold đã hết hạn được dùng để xác nhận mua**, và không được để hai claim mới cùng chiếm ghế. Đây là quy tắc **ngay tại đường đọc/ghi**, không thể phó mặc cho tác vụ TTL dọn vật lý.

Các hệ NoSQL thường dọn TTL bất đồng bộ. Do đó:

1. Khi đọc hold, so sánh **expiresAt** với thời gian đáng tin cậy theo chính sách.
2. Khi xác nhận mua, cần **ghi có điều kiện**: đúng ID, trạng thái còn hợp lệ và chưa hết hạn.
3. Khi giải phóng ghế, phải xử lý an toàn nếu khách đã gia hạn hold hoặc đã thanh toán; một job dọn trễ không được xóa claim mới do nhầm ID.
4. Nếu TTL xóa bản ghi làm mất lịch sử nghiệp vụ, cần tách bản lưu hiện hành và bản lịch sử theo chính sách.

Một tác vụ “xóa mọi hold đã quá giờ” mà không kiểm tra version/trạng thái khi ghi có thể xóa nhầm một reservation vừa được gia hạn. **Thời gian hết hạn là một phần của predicate**, không phải chỉ một thông số lưu trữ.

## 18. Bản sao, cache và read model: điều kiện nào phải đúng ở đâu?

Giả sử order chuyển sang **PAID**, sau đó phát event cập nhật:

~~~text
orders (nguồn chính)
   |
   +--> customer_recent_orders
   +--> sales_dashboard
   +--> search_index
   +--> notification_service
~~~

Các hệ dẫn xuất có thể cập nhật ở những thời điểm khác nhau. Cần định nghĩa:

**Bất biến cứng ở nguồn chính:** Không thể chuyển PAID từ trạng thái mà nghiệp vụ cấm; một payment event không được tạo hiệu ứng lặp.

**Điều kiện của read model:** Dashboard cuối cùng phản ánh trạng thái nguồn chính trong độ trễ cho phép; không đếm trùng event khi consumer retry.

**Điều kiện trên cache:** API không được lộ dữ liệu tenant khác; khi có yêu cầu xóa/thu hồi quyền, cache không được tiếp tục cho phép truy cập trái phép chỉ vì bản sao còn tồn tại.

Đối với dữ liệu dẫn xuất, nên có:

- **Version hoặc sequence** để phát hiện update đến sai thứ tự.
- **Event ID** để dedup khi consumer nhận lại cùng event.
- **Checkpoint** để tiếp tục sau lỗi.
- **Rebuild/backfill** từ nguồn chính khi cần.
- **Lag metrics** để thấy dữ liệu trễ quá hợp đồng.
- **Reconciliation** để so sánh trạng thái nguồn và bản sao.

Không nên tuyên bố “eventual consistency sẽ tự sửa sau một lúc” nếu không có đường retry/rebuild và chỉ số phát hiện lệch. **Hội tụ** phải là thuộc tính thiết kế và vận hành, không phải hy vọng.

## 19. Bất biến và phân quyền đều cần được bảo vệ ở đường ghi

Với hệ đa tenant, một request có thể truyền **orderId** hợp lệ nhưng order thuộc tổ chức khác. Nếu chỉ query theo ID:

~~~javascript
db.orders.updateOne(
  { _id: "order-101" },
  { $set: { status: "CANCELLED" } }
);
~~~

thì bộ lọc chưa ràng buộc phạm vi tenant. Một ứng dụng đúng cần xác thực người gọi, kiểm tra quyền thao tác và giới hạn điều kiện theo tenant/chủ thể theo thiết kế:

~~~javascript
db.orders.updateOne(
  {
    _id: "order-101",
    tenantId: "shop-a",
    customerId: "customer-17",
    status: "CREATED"
  },
  {
    $set: { status: "CANCELLED" }
  }
);
~~~

**tenantId** và **customerId** phải đến từ ngữ cảnh xác thực/ủy quyền hoặc được đối chiếu đáng tin cậy, không được tin nguyên văn dữ liệu do client tự nhận. Nếu backend có nhiều vai trò (khách, nhân viên, quản trị), điều kiện và quyền thay đổi theo từng thao tác.

Một unique constraint trong tenant cũng phải chọn key có phạm vi phù hợp, ví dụ **(tenantId, normalizedUsername)**; không nên vô tình áp một ràng buộc toàn cục nếu nghiệp vụ cho phép các tenant độc lập cùng dùng tên.

## 20. Bảo vệ bất biến khi dữ liệu tăng và bị phân vùng

Ban đầu, một cửa hàng nhỏ có thể cập nhật stock trên một document với độ trễ thấp. Khi hàng nghìn request mỗi giây cùng mua SKU nổi tiếng, document/key tồn kho có thể trở thành **hotspot**.

Giải pháp phân chia tồn kho thành nhiều shard có vẻ giúp tăng throughput:

~~~text
SKU BOOK-01:
  shard-1.available = 3
  shard-2.available = 2
  shard-3.available = 0

Tổng available = 5
~~~

Nhưng bất biến “tổng không âm” nay phụ thuộc nhiều shard. Nếu hai request cùng đọc tổng từ những snapshot khác nhau rồi trừ ở các shard khác nhau, hệ thống có thể vượt mức tồn nếu không có quy tắc cấp quyền, reservation hoặc kiểm soát giới hạn.

Các phương án thường cần cân nhắc:

- **Giữ một điểm điều phối theo SKU** khi tính đúng đắn quan trọng hơn throughput cực đại.
- **Phân bổ quota/stock đã được cấp trước** tới từng shard, chỉ cho phép mỗi shard bán trong phần đã cấp.
- **Reservation có thời hạn và ID** để phân biệt đã giữ, đã chốt, đã giải phóng.
- **Điều chỉnh nguồn sự thật** khi nhập/trả hàng và đối soát lượng tồn vật lý.
- **Xử lý thiếu tài nguyên** bằng backpressure/rate limit thay vì phá bất biến để tăng tốc.

Không có giải pháp scale nào được phép âm thầm đổi định nghĩa “bán thành công” nếu sản phẩm vẫn cam kết không oversell.

Trong Cassandra, việc gom nhiều hàng cùng partition có thể phục vụ truy vấn theo khóa, nhưng **không mặc nhiên chuyển mọi bất biến của tập hàng thành một atomic transaction như document MongoDB**. Trong DynamoDB, việc đặt nhiều item chung partition key cũng **không** làm mọi UpdateItem trở thành một transaction nhiều item. Ranh giới truy vấn và ranh giới bảo đảm giao dịch phải được xét riêng.

## 21. Phát hiện lỗi, đối soát và quan sát bất biến

Không phải bất biến nào cũng chỉ cần một index để bảo vệ. Các điều kiện trải qua nhiều hệ thống cần được quan sát liên tục.

| Bất biến/điều kiện | Bằng chứng tại thao tác | Kiểm tra vận hành |
|---|---|---|
| availableStock không âm | Conditional update thành công/thất bại theo lượng yêu cầu | Đếm bản ghi stock âm; đo tỷ lệ conflict hoặc thiếu tồn |
| Một active seat claim | Unique key chặn insert trùng | Truy vấn phát hiện nhiều claim trên cùng ghế nếu có dữ liệu legacy |
| Order total khớp các dòng | Lập và chốt order theo hợp đồng | Đối soát tổng/đơn vị tiền/giảm giá trên tập order |
| Một event chỉ áp dụng một lần | providerEventId hoặc idempotencyKey duy nhất | Đếm duplicate event, kiểm tra trạng thái inbox/outbox |
| Không có trạng thái bất hợp lệ | Conditional transition theo state machine | Phát hiện order bị kẹt hoặc chuyển không có event hợp lệ |
| Không có orphan reference ngoài chính sách | Kiểm tra đầu vào/ghi có phối hợp | Job tìm enrollment trỏ đến course không tồn tại |
| Read model hội tụ | Checkpoint/version của consumer | Lag, sai số đếm so với nguồn, khả năng replay |
| Không truy cập chéo tenant | Kiểm tra auth và filter theo tenant | Log truy cập bị từ chối, thử nghiệm tenant isolation |

Ví dụ một truy vấn MongoDB để tìm dữ liệu tồn kho âm trong hệ đã có dữ liệu:

~~~javascript
db.inventory.find(
  { availableStock: { $lt: 0 } },
  { _id: 1, tenantId: 1, availableStock: 1 }
);
~~~

Không tìm thấy stock âm **chưa đủ chứng minh** không có oversell: nếu hai request cùng ghi đè tồn mới = 1, số tồn vẫn không âm nhưng số order được xác nhận có thể vượt tổng có thể bán. Vì vậy, đối soát đôi khi cần so sánh **reservation, order, payment và ledger của biến động kho**.

### Kịch bản lỗi nên đưa vào kế hoạch thử nghiệm

1. Hai client cùng giảm tồn 4 khi available = 5.
2. Hai client cùng đăng ký một ghế hoặc cùng tạo quan hệ duy nhất.
3. Một request tạo order timeout sau khi đã commit; client retry cùng idempotency key.
4. Consumer nhận lại một webhook đã xử lý.
5. Event **PAID** đến sau khi order đã chuyển **CANCELLED**.
6. Inventory đã giữ thành công nhưng bước tạo order/payment thất bại.
7. Một dịch vụ dừng ngay sau khi commit database nhưng trước khi phát event.
8. Job giải phóng reservation chạy trễ khi hold đã được gia hạn.
9. Cache hoặc read model nhận sự kiện cũ sau sự kiện mới.
10. Tài khoản tenant A cố sửa ID hợp lệ của tenant B.

Các thử nghiệm này nhắm vào **trạng thái cuối, số hiệu ứng nghiệp vụ và khả năng phục hồi**, không chỉ vào HTTP status của một API.

## 22. Viết kiểm thử bất biến bằng đầu vào và trạng thái kỳ vọng

Một test concurrency có thể mô tả như sau:

~~~text
Given:
  inventory["BOOK-01"].availableStock = 5

When:
  request A và B đồng thời giữ 4 quyển

Then:
  số request giữ thành công = 1
  availableStock = 1
  không có hai reservation thành công cùng trừ quá 5
~~~

Không nên chỉ assert “mỗi API trả 200 hoặc 409 tùy điều kiện”; cần kiểm tra **số reservation/order thực tế** và lượng tồn sau khi cả hai kết thúc.

Một test idempotency:

~~~text
Given:
  checkoutRequestId = checkout-req-123

When:
  gọi tạo đơn lần 1; response bị mất
  gọi lại cùng key và cùng payload

Then:
  chỉ tồn tại một order cho key
  chỉ một lần giữ tồn có hiệu lực
  hệ thống trả lại kết quả hợp lệ của cùng ý định
~~~

Một test state machine:

~~~text
Given:
  order.status = CANCELLED

When:
  nhận webhook PAYMENT_SUCCEEDED đến muộn

Then:
  không tự chuyển thành PAID nếu không có cạnh hợp lệ
  event được ghi nhận và đi vào quy trình ngoại lệ/hoàn tiền thích hợp
  không phát hàng ngoài ý muốn
~~~

Với giao dịch nhiều hệ thống, cần test cả **fault injection**: timeout giữa hai bước, retry khi có duplicate key, worker chết khi xử lý outbox, mạng chập chờn trong lúc commit, và phục hồi từ checkpoint.

## 23. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| “Có validation ở API là đủ” | Nhiều writer, race hoặc job nền có thể bỏ qua | Bảo vệ tại điểm ghi có cạnh tranh và ở tầng dữ liệu phù hợp |
| “Đọc thấy còn tồn thì trừ luôn an toàn” | Giá trị có thể đổi giữa đọc và ghi | Dùng conditional atomic update/CAS/transaction thích hợp |
| “Một document chứa đủ field sẽ luôn hợp lệ” | Document có thể chứa giá trị sai hoặc phép tính sai | Thiết kế ranh giới và cả quy tắc kiểm tra bất biến |
| “Unique index thay thế mọi kiểm tra nghiệp vụ” | Không kiểm tra trạng thái/quan hệ/tenant khác | Kết hợp unique với quyền, điều kiện ghi và lifecycle |
| “Event cuối cùng sẽ tới nên không cần idempotency” | Event có thể trùng/lệch thứ tự | Dùng event ID, trạng thái và quy tắc retry |
| “Dùng transaction là giải quyết mọi thứ” | Transaction có phạm vi, isolation và lỗi riêng | Chọn transaction cho bất biến cụ thể, xử lý conflict/retry |
| “Tồn kho không âm nghĩa là không oversell” | Lost update có thể giữ số dương nhưng bán trùng | Đối soát reservation và order, không chỉ nhìn một field |
| “TTL đảm bảo reservation giải phóng đúng giây” | Dọn vật lý thường bất đồng bộ | Kiểm tra expiresAt khi đọc/ghi, dọn nền là bước sau |
| “Eventual consistency nghĩa là mọi thứ tự sửa” | Lỗi consumer có thể kéo dài vô hạn | Retry, replay, checkpoint, reconciliation, lag metric |
| “Cùng partition thì mọi hàng nguyên tử” | Phụ thuộc ngữ nghĩa database và thao tác | Xác định ranh giới atomic/transaction thực tế |
| “Thêm một read model không ảnh hưởng bất biến” | Ghi trùng hoặc sai thứ tự có thể làm đếm sai | Xác định nguồn sự thật và cơ chế hội tụ |
| “Bất biến cứng phải được bảo vệ bằng một document khổng lồ” | Dữ liệu có thể tăng vô hạn và tạo hotspot | Chọn điểm kiểm soát nhỏ nhất đủ mạnh, phối hợp khi cần |

## 24. Quy trình thiết kế từ bất biến đến data model

Một quy trình ngắn gọn để áp dụng với tính năng NoSQL mới:

**Bước 1 — Liệt kê thao tác nghiệp vụ.** Ai đọc/ghi dữ liệu nào? Một request có thể đến hai lần hoặc chạy cùng request khác không?

**Bước 2 — Viết bất biến thành predicate.** Cần đúng với những khóa nào? Có giới hạn, công thức hoặc state transition nào? Định nghĩa cả ngoại lệ.

**Bước 3 — Phân loại thời điểm cần đúng.** Điều kiện nào phải đúng ngay tại commit/response thành công? Điều kiện nào được phép trễ và trong bao lâu?

**Bước 4 — Xác định chủ sở hữu và khóa kiểm soát.** Một order, một SKU, một cặp ghế–suất, một tenant hay một provider event? Tránh phân tán cùng một bất biến ra các bản sao không có điểm kiểm soát.

**Bước 5 — Chọn ranh giới lưu.** Dùng document/item/key khi có thể; tránh nhúng dữ liệu chia sẻ, tăng vô hạn hoặc có vòng đời khác biệt.

**Bước 6 — Chọn cơ chế bảo vệ khi ghi.** Schema validation cho cấu trúc, unique index cho tính duy nhất, conditional update/CAS cho concurrent state, transaction khi nhiều bản ghi phải cùng thành công, saga/reservation khi nhiều dịch vụ độc lập.

**Bước 7 — Thiết kế retry và xử lý lỗi một phần.** Idempotency key, trạng thái workflow, outbox/inbox, bù, timeout và xác nhận kết quả chưa rõ.

**Bước 8 — Thiết kế dữ liệu dẫn xuất.** Điều kiện hội tụ, giới hạn độ trễ, sự kiện trùng/lệch thứ tự, rebuild và đối soát.

**Bước 9 — Kiểm chứng.** Test đồng thời, test fault injection, truy vấn đối soát và quan sát số liệu production.

~~~mermaid
flowchart TD
    A["Yêu cầu nghiệp vụ"] --> B["Predicate bất biến và ngoại lệ"]
    B --> C["Khóa/phạm vi chịu trách nhiệm"]
    C --> D{"Một đơn vị lưu trữ đủ bảo vệ?"}
    D -->|"Có"| E["Atomic conditional write / unique constraint"]
    D -->|"Không, cùng DB"| F["Transaction hoặc thiết kế lại aggregate"]
    D -->|"Không, nhiều dịch vụ"| G["Reservation + saga/outbox/idempotency"]
    E --> H["Test race + retry + trạng thái sai"]
    F --> H
    G --> H
    H --> I["Đối soát và đo vận hành"]
    I --> J{"Bất biến được giữ dưới tải?"}
    J -->|"Chưa"| C
    J -->|"Đạt"| K["Vận hành và giám sát"]
~~~

## 25. Bài tập áp dụng

### Bài tập 1 — Viết bất biến rõ ràng

Một hệ bán vé có các trạng thái **AVAILABLE**, **HELD**, **SOLD**. Hãy định nghĩa:

- Điều kiện để một ghế được HELD.
- Điều kiện để HELD chuyển sang SOLD.
- Những chuyển trạng thái không hợp lệ.
- Cách xử lý hold hết hạn và thời điểm được phép bán lại.
- Khóa dữ liệu nào phải bảo vệ chống hai người cùng đặt ghế.

Chỉ ra điều kiện nào cần đúng ngay và điều kiện nào có thể hoàn thành bất đồng bộ.

### Bài tập 2 — Hai khách mua cùng lúc

Tồn kho có **7 sản phẩm**, hai request đồng thời đặt **5 sản phẩm**. Mô phỏng lỗi của cách **read → calculate → write**. Sau đó viết filter MongoDB dùng **$gte** và **$inc** để đảm bảo chỉ request hợp lệ trừ được tồn. Nêu cách trả kết quả khi condition thất bại.

### Bài tập 3 — Tổng tiền và đơn vị tiền tệ

Một order có 3 dòng; mỗi dòng chứa **quantity**, **unitPriceAtPurchase** và thuế/phí theo quy tắc doanh nghiệp. Hãy viết công thức orderTotal, xác định cách tránh sai số thập phân, và đề xuất dữ liệu nào nên được ghi cùng order để đảm bảo hóa đơn lịch sử không đổi khi catalog cập nhật.

### Bài tập 4 — Trùng quan hệ nhiều-nhiều

Học viên có thể tham gia nhiều khóa học; mỗi cặp **(tenantId, studentId, courseId)** chỉ có một enrollment hiện hành. Hãy thiết kế unique key/index, xử lý hai request cùng đăng ký và giải thích vì sao index không tự xác nhận student/course tồn tại cùng tenant.

### Bài tập 5 — Sự kiện thanh toán gửi lại

Provider gửi cùng **paymentEventId** ba lần vì mạng chập chờn. Hãy thiết kế inbox/idempotency record, các trạng thái cần theo dõi và cách ngăn cộng điểm thưởng hoặc giữ tồn lặp. Trình bày cách xử lý nếu consumer dừng sau khi ghi “đã nhận” nhưng trước khi áp dụng hiệu ứng.

### Bài tập 6 — Ghi nhiều aggregate

Một thao tác đặt hàng cần giữ hai SKU, tạo order rồi gọi payment provider. Hãy xác định:

- Những bất biến nằm trong một inventory record.
- Những bất biến nằm trong một order document.
- Những điều kiện trải qua nhiều record và dịch vụ.
- Nơi cần transaction, nơi cần reservation/saga.
- Các bước bù khi thanh toán thất bại hoặc kết quả chưa rõ.

### Bài tập 7 — Bảo vệ bất biến ở quy mô lớn

Một SKU nổi tiếng nhận 20.000 yêu cầu đặt hàng mỗi giây, tất cả trừ trên cùng một key. Hãy phân tích hotspot, đề xuất các phương án phân bổ quyền bán/stock theo shard và giải thích vì sao chỉ cộng các shard bất đồng bộ không đủ để chứng minh không oversell.

### Bài tập 8 — Dữ liệu dẫn xuất và độ mới

Dashboard hiển thị tổng số order **PAID** theo ngày; nguồn order cập nhật đúng nhưng consumer có thể nhận event chậm hoặc trùng. Hãy định nghĩa giới hạn trễ được phép, event ID, checkpoint, cách tính số đếm không trùng và job đối soát từ nguồn chính.

### Bài tập 9 — Tenant isolation

Một API nhận **orderId**, **tenantId** từ request body và cho phép CANCELLED. Hãy phân tích vì sao chỉ dùng hai giá trị do client gửi có thể tạo lỗ hổng, cách lấy tenant từ ngữ cảnh xác thực và cách ghi điều kiện trên trạng thái hiện tại.

### Bài tập 10 — Kiểm chứng toàn diện

Chọn một bất biến trong bài và thiết kế ít nhất ba tình huống: **hai writer đồng thời**, **timeout rồi retry**, **sự kiện đến sai thứ tự**. Với mỗi tình huống, viết trạng thái ban đầu, thao tác, trạng thái cuối được phép, và bằng chứng đo được cho thấy bất biến không bị vi phạm.

Điểm cốt lõi của bài: **bất biến nghiệp vụ quyết định ranh giới cần bảo vệ, còn access patterns quyết định cách truy cập và tổ chức dữ liệu**. Một mô hình NoSQL tốt phải dung hòa cả hai: gom những dữ liệu cần nhất quán khi có thể, giữ những thực thể chia sẻ ở ranh giới phù hợp, dùng thao tác ghi có điều kiện để chống cạnh tranh và thiết kế workflow/đối soát khi bất biến kéo dài qua nhiều đơn vị hay nhiều dịch vụ. Câu hỏi quan trọng nhất không phải “dữ liệu đã được lưu chưa?”, mà là **“sau mọi thao tác thành công, kể cả khi có đồng thời và lỗi mạng, điều kiện nghiệp vụ còn đúng không?”**
