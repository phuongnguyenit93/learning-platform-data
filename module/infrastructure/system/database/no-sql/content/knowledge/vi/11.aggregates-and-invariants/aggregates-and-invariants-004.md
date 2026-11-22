# Đặt ràng buộc trong database, dịch vụ ứng dụng hoặc cả hai

Trong cơ sở dữ liệu NoSQL, việc **nhóm dữ liệu** thường được quyết định bởi các đường đọc và ghi quan trọng: một đơn hàng có thể chứa tất cả dòng hàng trong một document, còn tồn kho được lưu trong một document khác; trạng thái phiên đăng nhập có thể ở key–value store, trong khi kết quả thanh toán nằm ở một dịch vụ độc lập. Cách nhóm dữ liệu ảnh hưởng trực tiếp đến câu hỏi: **bất biến nào có thể được bảo vệ bằng một thao tác nguyên tử, và bất biến nào cần phối hợp nhiều thành phần?**

Ví dụ, một hệ thống bán hàng có các yêu cầu:

- Số lượng từng dòng hàng phải dương.
- Tổng tiền đơn hàng phải khớp các khoản đã chốt.
- Một yêu cầu thanh toán không được tạo ra hai giao dịch logic.
- Lượng tồn kho được cấp phát không được vượt số lượng có sẵn.
- Đơn hàng đã hủy không được tự chuyển trở lại trạng thái đã thanh toán.
- Nếu việc giữ hàng thành công nhưng hệ thống thanh toán lỗi, dữ liệu phải đi tới trạng thái được xác định và có thể phục hồi.

Đó là những **bất biến (invariants)** khác nhau. Một schema validator có thể từ chối số lượng âm; một unique index có thể bảo vệ tính duy nhất; một conditional update có thể ngăn cạnh tranh tồn kho; còn một workflow xuyên dịch vụ cần idempotency, sự kiện đáng tin cậy, trạng thái trung gian và bù trừ. Không có một loại constraint duy nhất giải quyết tất cả.

**Mục tiêu của bài:** phân loại bất biến, xác định ranh giới cập nhật của một nhóm dữ liệu, chọn đặt ràng buộc trong database, domain/application service hoặc kết hợp cả hai, rồi kiểm chứng tính đúng dưới tải đồng thời và sự cố.

> Các ví dụ MongoDB, DynamoDB, Cassandra, HBase và Redis nhằm làm rõ phạm vi bảo đảm. Phiên bản, cấu hình, consistency và giới hạn transaction khác nhau giữa sản phẩm; các đoạn code minh họa không phải một ứng dụng production hoàn chỉnh.

## 1. Bất biến là gì và vì sao cần chỉ rõ phạm vi?

**Bất biến dữ liệu** là một mệnh đề phải đúng ở mọi trạng thái mà hệ thống chấp nhận là hợp lệ. Ví dụ:

~~~text
OrderLine.quantity > 0
Inventory.available >= 0
Inventory.reserved >= 0
Promotion.startsAt < Promotion.endsAt
Order.status == CONFIRMED => Order.confirmedAt != null
(tenantId, externalOrderId) xác định tối đa một order logic
~~~

Nhưng các phát biểu ngắn vẫn có thể thiếu điều kiện. Ví dụ “tồn kho không âm” chưa cho biết tồn kho ở **kho nào**, **SKU nào**, hàng đã giữ chỗ tính ra sao, và việc kiểm tra phải đúng **sau thao tác nào**.

Phát biểu chi tiết hơn:

> Với mỗi cặp (warehouseId, sku), sau mỗi lệnh reserve thành công được xác nhận, số available phải không âm. Hai lệnh reserve cạnh tranh trên cùng trạng thái phải được quyết định nguyên tử, và retry của cùng operationId không được trừ available thêm lần nữa.

Khi diễn đạt như vậy, ta nhận ra **ba ràng buộc riêng**: giới hạn không âm, cập nhật nguyên tử khi cạnh tranh và idempotency khi retry.

### 1.1. Các nhóm bất biến

| Loại | Ví dụ | Nơi thường thực thi |
| --- | --- | --- |
| Hình dạng và kiểu | Một booking phải có checkIn và checkOut dạng thời điểm | DTO/domain, document validator |
| Giá trị đơn lẻ | Quantity là số nguyên từ 1 đến 10 | API/domain và validator nếu có |
| Quan hệ giữa trường | checkIn trước checkOut, CONFIRMED cần confirmedAt | Domain và biểu thức validation trong DB khi hỗ trợ |
| Duy nhất giữa bản ghi | Mã đơn theo tenant không được trùng | Unique index hoặc conditional create nguyên tử |
| Cập nhật dựa trên trạng thái cũ | Không reserve quá available | Atomic conditional update |
| Chuyển trạng thái | Chỉ PENDING mới được confirm | State machine và update có điều kiện trên state/version |
| Nhiều đối tượng | Order và inventory phải tiến triển nhất quán | Transaction hoặc protocol phối hợp |
| Nhiều dịch vụ | Thanh toán và đơn hàng phải được đối soát | Saga, idempotency, outbox, reconciliation |
| Ủy quyền | Chỉ người có quyền quản lý tenant mới được sửa | Application/auth; database có thể hỗ trợ giới hạn đường truy cập |

Cần phân biệt **kiểm tra một trạng thái cuối có hợp lệ không** với **bảo vệ sự chuyển đổi từ trạng thái cũ sang mới**. Một order có status CONFIRMED và confirmedAt hợp lệ vẫn có thể là kết quả của một chuyển trạng thái trái phép từ CANCELLED. Schema nhìn thấy trạng thái cuối, nhưng không nhất thiết biết lịch sử và quyền người thực hiện.

## 2. Vì sao chỉ validation trong ứng dụng chưa đủ?

Giả sử tồn kho còn đúng một đơn vị và hai request đặt mua cùng lúc:

~~~text
Thời điểm     Request A                  Request B
------------------------------------------------------------
T1            Đọc available = 1
T2                                       Đọc available = 1
T3            Kiểm tra >= 1: đúng
T4                                       Kiểm tra >= 1: đúng
T5            Ghi available = 0
T6                                       Ghi available = 0
T7            Trả đặt thành công         Trả đặt thành công
~~~

Trạng thái cuối cùng của trường available là 0, không âm, nhưng **hai đơn hàng đã cùng được báo thành công cho một đơn vị**. Đây là lỗi **time-of-check to time-of-use (TOCTOU)**: đọc và kiểm tra không nguyên tử với lệnh ghi.

Để bảo vệ quyết định cấp phát, cần kết hợp điều kiện và cập nhật tại nơi có thẩm quyền trong **cùng một thao tác nguyên tử**.

Ví dụ trên MongoDB:

~~~javascript
const result = db.inventory.updateOne(
  {
    warehouseId: "WH-A",
    sku: "BOOK-01",
    available: { $gte: 1 }
  },
  { $inc: { available: -1, reserved: 1 } }
);

if (result.matchedCount === 1) {
  // Đã reserve một đơn vị trên trạng thái hiện hành.
} else {
  // Không tồn tại bản ghi phù hợp hoặc không đủ hàng.
}
~~~

MongoDB bảo đảm tính nguyên tử của thao tác cập nhật **một document**. Hai yêu cầu đồng thời sẽ không cùng vượt qua điều kiện available >= 1 trên cùng document sau khi một thao tác đã giảm available thành công.

Tuy nhiên, đoạn code **chưa bảo đảm toàn bộ checkout**:

- Chưa tạo đơn hàng.
- Chưa ghi dấu một operationId đã được xử lý, nên retry có thể trừ thêm lần nữa.
- Chưa xử lý thanh toán.
- Chưa xử lý trường hợp database đã commit nhưng API không nhận ACK.

Đây là ví dụ quan trọng về **ranh giới bất biến**: đúng ở một document không đồng nghĩa đúng ở tất cả dịch vụ.

### 2.1. Race trong kiểm tra duy nhất

Một cách làm sai thường gặp:

~~~text
if (!orderExists(tenantId, externalOrderId)) {
    createOrder(...);
}
~~~

Hai worker có thể đều thấy chưa có order, rồi cùng insert. Nếu nghiệp vụ yêu cầu duy nhất, cần một ràng buộc được database thực thi dưới concurrency, chẳng hạn **unique index** hoặc **conditional put/insert-if-not-exists**, tùy engine.

Kiểm tra trước ở application vẫn hữu ích để phản hồi sớm, nhưng không thể thay thế hàng rào nguyên tử tại điểm ghi.

## 3. Đặt constraint tại database

Database là lớp cuối cùng có thể chặn trạng thái sai khi có nhiều đường ghi: API, background worker, batch import, consumer hoặc thao tác quản trị. Nhưng **NoSQL không có một hệ constraint chung**; nhiều engine không cung cấp đầy đủ CHECK, FOREIGN KEY và transaction kiểu SQL quan hệ.

### 3.1. Schema/document validation

Một document order có thể được yêu cầu:

- Có orderId, tenantId, status, items và totalMinor.
- Status thuộc PENDING, CONFIRMED, CANCELLED.
- Items là mảng không rỗng.
- Mỗi item có sku và quantity dương.
- totalMinor là số nguyên không âm.

Ví dụ MongoDB:

~~~javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["orderId", "tenantId", "status", "items", "totalMinor"],
      properties: {
        orderId: { bsonType: "string", minLength: 1 },
        tenantId: { bsonType: "string", minLength: 1 },
        status: { enum: ["PENDING", "CONFIRMED", "CANCELLED"] },
        items: {
          bsonType: "array",
          minItems: 1,
          items: {
            bsonType: "object",
            required: ["sku", "quantity"],
            properties: {
              sku: { bsonType: "string", minLength: 1 },
              quantity: { bsonType: "int", minimum: 1 }
            }
          }
        },
        totalMinor: { bsonType: "long", minimum: 0 },
        confirmedAt: { bsonType: "date" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

MongoDB sử dụng các kiểu **BSON**. Giá trị Int32, Int64, Decimal128 và string không phải cùng kiểu. Phải thống nhất cách serialize ở driver với validator; một API JSON nhận số 1 không tự chứng minh driver sẽ ghi kiểu BSON int thay vì long.

Một số engine hỗ trợ biểu thức so sánh giữa các trường cùng document, ví dụ startsAt trước endsAt hoặc status CONFIRMED yêu cầu confirmedAt. Tuy nhiên, **schema validator không tự nhìn thấy các document khác**, quyền của người gọi hoặc kết quả một cuộc gọi payment provider.

Hình dạng hợp lệ cũng **không bảo đảm số tiền đã được tính đúng** nếu tổng cần tham chiếu giá và chính sách ở một dịch vụ khác.

### 3.2. Unique index hoặc tạo có điều kiện

Giả sử mã đơn do đối tác cung cấp phải duy nhất **trong mỗi tenant**:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true }
);
~~~

Constraint này bảo vệ tổ hợp hai trường. Khi áp dụng phải hiểu:

- Có cho phép externalOrderId bị thiếu hoặc null không?
- Mã có phân biệt chữ hoa, chữ thường không?
- Tính duy nhất chỉ áp dụng cho các order active hay toàn bộ lịch sử?
- Nếu collection sharded, cấu hình shard key có đáp ứng điều kiện hỗ trợ index duy nhất toàn phạm vi mong muốn không?
- Dữ liệu cũ có duplicate khiến không thể tạo index không?

Nếu một yêu cầu insert bị từ chối vì duplicate, application không nên chỉ trả lỗi kỹ thuật. Với **idempotency key cùng payload**, có thể trả lại kết quả đã tồn tại; với **cùng key nhưng payload khác**, thường phải thông báo xung đột.

### 3.3. Conditional update và compare-and-swap

Khi một thao tác chỉ hợp lệ từ phiên bản hoặc trạng thái cũ nhất định, dùng điều kiện trên **giá trị hiện hành tại database**.

~~~javascript
const result = db.orders.updateOne(
  {
    orderId: "O-101",
    status: "PENDING",
    version: 7
  },
  {
    $set: { status: "CONFIRMED", confirmedAt: new Date() },
    $inc: { version: 1 }
  }
);

if (result.matchedCount === 1) {
  // Chuyển trạng thái thành công.
} else {
  // Không tồn tại hoặc trạng thái/phiên bản đã đổi.
}
~~~

**Domain layer** quyết định quy tắc PENDING -> CONFIRMED. **Database** chặn một worker cũ cập nhật khi trạng thái đã đổi. Đó là một ví dụ dùng **cả hai** lớp đúng trách nhiệm.

### 3.4. Transaction khi phải thay đổi nhiều item

Đôi khi cùng một nghiệp vụ đòi:

~~~text
Transaction:
  1. Tạo order trạng thái RESERVED.
  2. Trừ available, tăng reserved của inventory.
  3. Ghi record idempotency đã áp dụng.
  Commit tất cả hoặc không commit.
~~~

Nếu các item ở phạm vi mà database có **transaction đa tài liệu/item** hỗ trợ, có thể dùng giao dịch phù hợp. Nhưng phải xác nhận:

- Giới hạn số item, kích thước, thời gian hoặc số vùng dữ liệu.
- Kiểu consistency và isolation được bảo đảm.
- Chi phí latency/throughput khi có tranh chấp.
- Cách ứng dụng xử lý conflict, abort, retry và unknown commit.
- Có được chạy với cấu hình replication, sharding và phiên bản đang dùng hay không.

Không thể đưa một cuộc gọi bên ngoài tới **payment provider** vào transaction MongoDB hoặc DynamoDB rồi suy ra ACID xuyên tất cả hệ thống.

### 3.5. Không đồng nhất batch với transaction

Một thao tác batch có thể là cơ chế gửi nhiều lệnh để giảm round trip hoặc bảo đảm một số đặc tính ở phạm vi hẹp. Trong Cassandra, **BATCH không phải một giao dịch SQL tổng quát bảo đảm isolation cho mọi partition**. HBase có bảo đảm theo row với các thao tác thích hợp nhưng không mặc nhiên có transaction đa row như SQL. Phải đọc chính xác hợp đồng của engine trước khi đặt bất biến lên batch.

## 4. Đặt validation ở application/domain service

Tầng ứng dụng hiểu những khái niệm mà validator database khó diễn đạt:

- Ai được quyền hủy đơn?
- Giá nào là giá đã chốt để tính tiền?
- Một yêu cầu thay đổi trạng thái có hợp lệ trong quy trình?
- Khách có được dùng mã khuyến mãi này không?
- Khi service bên ngoài lỗi, kết quả API cần là gì?

Application validation thường giúp **phát hiện lỗi sớm, trả lỗi rõ và diễn đạt nghiệp vụ tập trung**. Tính đúng dưới cạnh tranh vẫn cần cơ chế bảo vệ tại điểm ghi.

### 4.1. Ví dụ Java: bất biến của một aggregate

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Objects;

enum OrderStatus { PENDING, CONFIRMED, CANCELLED }

record OrderLine(String sku, int quantity, long unitPriceMinor) {
    OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (quantity <= 0 || unitPriceMinor < 0) {
            throw new IllegalArgumentException("invalid quantity or price");
        }
    }

    long subtotalMinor() {
        return Math.multiplyExact(quantity, unitPriceMinor);
    }
}

final class Order {
    private OrderStatus status = OrderStatus.PENDING;
    private Instant confirmedAt;
    private final List<OrderLine> lines;
    private final long totalMinor;

    Order(List<OrderLine> lines, long totalMinor) {
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("order is empty");
        }
        this.lines = List.copyOf(lines);
        long computed = 0;
        for (OrderLine line : this.lines) {
            computed = Math.addExact(computed, line.subtotalMinor());
        }
        if (computed != totalMinor) {
            throw new IllegalArgumentException("total mismatch");
        }
        this.totalMinor = totalMinor;
    }

    void confirm(Instant now) {
        Objects.requireNonNull(now, "now");
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException("invalid transition");
        }
        status = OrderStatus.CONFIRMED;
        confirmedAt = now;
    }
}
~~~

Đây là ví dụ đơn hàng đơn giản, chưa gồm thuế, shipping, discount hoặc currency. Trong sản phẩm thực, cần định nghĩa đơn vị tiền, cách làm tròn, snapshot giá đã chốt và quy tắc thay đổi đơn. **Đừng tự tính lại số tiền lịch sử theo giá catalog hiện tại**.

Lớp Order có thể bảo đảm trạng thái object trong một tiến trình. Nhưng nếu hai service tải cùng một order PENDING rồi đều gọi confirm, **version/status conditional update** vẫn cần thiết để không có hai thao tác đồng thời được xác nhận.

### 4.2. Kiểm tra quyền là trách nhiệm khác schema

Ứng dụng có thể kiểm tra:

~~~text
principal = authenticate(request)
assert principal.canManage(tenantId)
order = orderRepository.load(orderId, tenantId)
order.confirm(serverTime)
orderRepository.saveWhenVersionMatches(order)
~~~

Trong thiết kế multi-tenant, nên đưa tenantId vào bộ lọc truy vấn/ghi nơi phù hợp, nhưng **partition key chứa tenantId không tự thực hiện authorization**. Token, vai trò, chủ sở hữu và các chính sách truy cập vẫn phải có nguồn quyết định có thẩm quyền.

### 4.3. Cập nhật PATCH phải kiểm tra dữ liệu sau khi hợp nhất

Document hiện tại:

~~~json
{
  "startsAt": "2026-11-14T09:00:00Z",
  "endsAt": "2026-11-14T10:00:00Z"
}
~~~

PATCH:

~~~json
{ "startsAt": "2026-11-14T11:00:00Z" }
~~~

Chỉ kiểm tra PATCH riêng lẻ sẽ không biết endsAt đã nhỏ hơn startsAt. Cần:

1. Áp dụng PATCH vào mô hình hiện tại.
2. Kiểm tra trạng thái cuối theo các quy tắc giữa trường.
3. Ghi có điều kiện theo version nếu trạng thái có thể bị thay đổi đồng thời.
4. Dùng validator DB nếu hỗ trợ để chặn trạng thái sai từ đường ghi khác.

Khi các trường phụ thuộc nhau, nên cập nhật chúng **trong cùng thao tác nguyên tử** thay vì set status rồi đợi lệnh khác set thời điểm.

## 5. Đặt ở cả hai: một hợp đồng, hai loại trách nhiệm

Không nên lựa chọn một cách cực đoan là “mọi luật nằm ở database” hoặc “mọi luật nằm trong service”. Có thể phân chia:

| Ràng buộc | Application/domain làm gì? | Database làm gì? |
| --- | --- | --- |
| Quantity hợp lệ | Trả lỗi đầu vào dễ hiểu | Nếu có validator, từ chối dữ liệu cuối sai |
| startsAt trước endsAt | Kiểm tra ngữ nghĩa khoảng thời gian | Nếu engine hỗ trợ, chặn document sai |
| Order không trùng theo tenant | Quản lý idempotency, lỗi conflict | Unique index/conditional create |
| Inventory đủ hàng | Quyết định nghiệp vụ reserve | Conditional update nguyên tử |
| Chuyển PENDING -> CONFIRMED | State machine, quyền, thông báo lỗi | Filter theo trạng thái/version hiện hành |
| Payment thành công | Phối hợp workflow, reconcile | Bảo vệ trạng thái cục bộ từng dịch vụ |
| Search/read model đồng bộ | Quản lý pipeline, duplicate và lag | Conditional/versioned writes tại projection nếu cần |

~~~mermaid
flowchart TD
    A["Request / consumer / batch"] --> B["Application\nXác thực, domain validation, idempotency"]
    B --> C["Database command\nUnique / conditional update / transaction nếu cần"]
    C --> D[("NoSQL store\nBảo vệ trạng thái trong phạm vi nguyên tử")]
    D -->|Ghi thành công| E["Trả kết quả và tiếp tục workflow"]
    D -->|Conflict / validation failure| F["Phân loại lỗi, đọc lại, trả business conflict hoặc retry an toàn"]
~~~

Hai lớp không nhất thiết chứa **toàn bộ quy tắc y hệt nhau**. Định nghĩa hợp đồng nghiệp vụ nhất quán, để tầng ứng dụng diễn giải/điều phối và database là hàng rào khi có concurrency trong phạm vi nó hỗ trợ.

## 6. Nhóm dữ liệu theo ranh giới bất biến

Một câu hỏi quan trọng trong thiết kế NoSQL là: **các field cần giữ nhất quán tức thì có thể nằm trong cùng đơn vị cập nhật nguyên tử không?**

### 6.1. Gộp khi thay đổi cùng nhau

Ví dụ giỏ hàng:

~~~json
{
  "cartId": "C-42",
  "customerId": "U-7",
  "version": 4,
  "status": "OPEN",
  "items": [
    { "sku": "BOOK-01", "quantity": 2 },
    { "sku": "PEN-02", "quantity": 1 }
  ]
}
~~~

Nếu một document chứa tất cả các dòng giỏ, thao tác tăng quantity hoặc đổi status có thể được bảo vệ trong phạm vi document. Tuy nhiên, đừng gom vô hạn:

- Document có thể vượt giới hạn kích thước của engine.
- Nhiều writer cùng sửa sẽ tranh chấp một record.
- Truy vấn chỉ cần một dòng nhưng phải xử lý object lớn.
- Các thành phần có vòng đời khác nhau làm migration và TTL phức tạp.

**Aggregate** nên là ranh giới mà các quy tắc cần được quyết định cùng nhau, đồng thời phù hợp kích thước và access patterns.

### 6.2. Tách khi trách nhiệm và nhịp thay đổi khác nhau

Một checkout có thể dùng:

~~~text
Order aggregate:
  orderId, lines, total, status, version

Inventory aggregate:
  warehouseId, sku, available, reserved, version

Payment aggregate:
  paymentId, providerRef, attempts, status
~~~

Đơn hàng có luật về giá và trạng thái, tồn kho có luật về cấp phát cạnh tranh, payment có luật riêng về giao dịch và provider callback. Dồn cả ba vào một document thường không phản ánh đúng ranh giới truy cập và sở hữu.

Tuy vậy, tách aggregate buộc hệ thống phải **thiết kế giao thức phối hợp**, không thể hy vọng một schema validator sẽ giữ atomicity toàn workflow.

## 7. Idempotency: duy nhất của thao tác không phải duy nhất của ID

Client gọi tạo order:

~~~text
POST /orders
Idempotency-Key: req-abc-123
Payload: ...
~~~

Server commit order, nhưng mạng đứt trước khi client nhận phản hồi. Client retry. Nếu mỗi lần retry tạo orderId mới và gọi insert mới, database có thể có hai order với **hai ID đều duy nhất**. Không có duplicate ID nhưng đã vi phạm bất biến **một yêu cầu logic tạo một đơn**.

Một thiết kế idempotency cần:

- **Operation key ổn định**, có phạm vi như (tenantId, idempotencyKey).
- Một cách ghi nhận nguyên tử rằng operation đã được bắt đầu/hoàn thành.
- So sánh fingerprint payload để phân biệt retry hợp lệ với reuse key khác nội dung.
- Lưu kết quả để trả lại khi retry.
- Trạng thái IN_PROGRESS, SUCCEEDED hoặc FAILED phù hợp với thời gian xử lý.
- Xử lý trường hợp **đã commit nhưng phản hồi không đến** bằng truy vấn theo operation key.

Nếu trạng thái idempotency và order ở hai document khác nhau, cần transaction phù hợp hoặc thiết kế biến **cùng một record** thành điểm quyết định. Ghi key chống trùng trước rồi ghi order ở một bước độc lập có lỗ hổng crash ở giữa.

TTL của dedup key chỉ xác định **cửa sổ ghi nhớ**, không bảo đảm một hành động sẽ không bao giờ được xử lý trùng sau khi key hết hạn hoặc bị evict. Với thanh toán cần hàng rào bền vững hoặc giao thức provider có idempotency tương ứng.

## 8. Bất biến chuyển trạng thái: domain và điều kiện ghi

Giả sử order:

~~~json
{
  "orderId": "O-101",
  "status": "PENDING",
  "version": 7,
  "confirmedAt": null
}
~~~

Hai worker cùng nhận ConfirmOrder:

~~~text
Worker A: Đọc PENDING, version 7.
Worker B: Đọc PENDING, version 7.
Worker A: Domain cho phép confirm.
Worker B: Domain cho phép confirm.
~~~

Nếu ghi vô điều kiện, cả hai có thể coi mình thành công và phát hai OrderConfirmed event. Cần **ghi một lần theo trạng thái/version hiện hành**:

~~~javascript
const r = db.orders.updateOne(
  { orderId: "O-101", status: "PENDING", version: 7 },
  {
    $set: { status: "CONFIRMED", confirmedAt: new Date() },
    $inc: { version: 1 }
  }
);

if (r.matchedCount === 0) {
  // Đã có cập nhật cạnh tranh, trạng thái không còn hợp lệ,
  // hoặc order không tồn tại: đọc lại và phân loại.
}
~~~

Khi matchedCount = 1, worker có bằng chứng nó đã thực hiện chuyển trạng thái. Nhưng **publish event** sau đó cũng phải có tính tin cậy. Nếu database commit rồi process chết trước khi gửi message, downstream có thể không nhận OrderConfirmed.

Một thiết kế **transactional outbox** có thể ghi trạng thái order và outbox record trong cùng transaction được database hỗ trợ. Publisher đọc outbox và gửi sự kiện, consumer xử lý idempotent vì gửi lại có thể xảy ra. Với những engine không hỗ trợ phạm vi cần thiết, phải dùng một phương án ghi sự kiện đáng tin cậy khác và chứng minh rủi ro lỗi từng phần.

## 9. Bất biến xuyên nhiều dịch vụ: saga và phục hồi

Đặt hàng có thể gồm:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as Order Service
    participant I as Inventory Service
    participant P as Payment Service
    C->>O: Checkout(operationId)
    O->>O: Tạo order PENDING idempotent
    O->>I: Reserve(sku, qty, operationId)
    I->>I: Conditional write, ghi nhận operationId
    I-->>O: Reserved / Rejected
    O->>P: Authorize/charge có idempotency
    P-->>O: Success / Failed / Unknown
    O->>O: Chuyển trạng thái, hoặc bù trừ/đối soát
    O-->>C: Result / Processing
~~~

Không có một giao dịch ACID chung chỉ vì sơ đồ trông tuần tự. Phải xử lý cả trường hợp:

- Reserve thành công nhưng response bị mất, request được gửi lại.
- Payment thành công nhưng Order Service chết trước khi ghi trạng thái.
- Client ngắt kết nối nhưng workflow vẫn đang chạy.
- Cancel đến trong lúc Reserve hoặc Payment đang xử lý.
- Release stock được gửi trùng.
- Callback payment đến muộn sau timeout.

### 9.1. Saga không phải transaction toàn cục

**Saga** là chuỗi các bước cục bộ với trạng thái rõ, có thể có **compensation** khi bước sau thất bại:

~~~text
Tạo order PENDING
    ↓
Reserve inventory
    ↓
Authorize payment
    ↓
Confirm order

Nếu payment thất bại:
  Release inventory reservation (idempotent)
  Mark order FAILED / CANCELLED
~~~

Cần có:

1. OperationId/idempotency cho mỗi lệnh.
2. Trạng thái workflow bền vững và có thể phục hồi sau crash.
3. Outbox/inbox hoặc cách giao message đủ tin cậy.
4. Retry có giới hạn, backoff, xử lý poison message.
5. Bù trừ idempotent, có điều kiện version/state.
6. Đối soát với nguồn có thẩm quyền khi kết quả payment không xác định.

**Bù trừ không phải luôn là rollback thật.** Một email đã gửi, khoản thanh toán đã capture hoặc hàng đã giao có thể cần một nghiệp vụ hoàn tiền/trả hàng, không thể đơn giản đảo ngược write cũ.

### 9.2. TTL/lock không đủ bảo đảm sự đúng đắn

Một reservation giữ hàng 10 phút có thể dùng expiresAt và một job dọn. Nhưng TTL hết hạn không chứng minh worker cũ đã ngừng hành động:

~~~text
T0 Worker A nhận lease 10 phút.
T1 Worker A bị dừng lâu nhưng vẫn giữ context cũ.
T2 Lease hết hạn, Worker B tiếp quản.
T3 Worker A tiếp tục chạy và ghi kết quả muộn.
~~~

Để ngăn lệnh cũ, cần kiểm tra **reservationId, state/version, deadline**, hoặc cơ chế **fencing token** tại tài nguyên đích theo yêu cầu. Chỉ xóa một key Redis sau thời gian định trước không tự giữ đúng bất biến tồn kho khi có cạnh tranh và lỗi.

## 10. Đối chiếu với các hệ NoSQL phổ biến

### 10.1. MongoDB

- Atomic update một document hỗ trợ điều kiện trong filter, kết hợp toán tử tăng/giảm và set.
- Unique index bảo vệ tính duy nhất trong phạm vi hợp đồng chỉ mục.
- Document validation bảo vệ hình dạng và một số quan hệ giữa trường.
- Multi-document transaction có thể dùng khi triển khai hỗ trợ, với chi phí và giới hạn nhất định.

~~~javascript
db.inventory.updateOne(
  { _id: "WH-A#BOOK-01", available: { $gte: 2 } },
  { $inc: { available: -2, reserved: 2 } }
);
~~~

**Lưu ý:** nếu retry cùng lệnh sau unknown commit, lệnh này có thể trừ thêm. Muốn xử lý một lần phải ghép với idempotency/operation record nguyên tử phù hợp.

### 10.2. DynamoDB

DynamoDB hỗ trợ **ConditionExpression** để Put/Update chỉ thành công khi điều kiện trên item được đáp ứng. Một ví dụ biểu thức minh họa:

~~~text
UpdateExpression:
  SET available = available - :qty,
      reserved  = reserved + :qty

ConditionExpression:
  attribute_exists(PK) AND available >= :qty
~~~

Đây không phải request SDK hoàn chỉnh: còn cần Key, ExpressionAttributeValues, kiểu dữ liệu và xử lý ConditionalCheckFailedException. Với nhiều item, **TransactWriteItems** có phạm vi và giới hạn riêng. Global secondary index/read replica có độ mới và cơ chế truy cập riêng; không dùng một bản đọc có thể stale làm hàng rào cuối của cấp phát.

### 10.3. Cassandra

Cassandra CQL có conditional write như:

~~~sql
INSERT INTO processed_operations (operation_id, outcome)
VALUES (550e8400-e29b-41d4-a716-446655440000, 'RESERVED')
IF NOT EXISTS;
~~~

Điều kiện trên dùng cơ chế **lightweight transaction (LWT)** trong trường hợp thích hợp, với chi phí phối hợp cao hơn ghi thông thường. Chống trùng bản ghi operation **không tự làm thao tác giảm tồn kho ở partition khác trở nên nguyên tử cùng lệnh đó**. Phải đánh giá phạm vi và thiết kế mô hình dữ liệu.

Cassandra BATCH có semantics riêng; không xem nó như transaction SQL tổng quát có isolation xuyên nhiều partition.

### 10.4. HBase

HBase có các thao tác kiểm tra–cập nhật theo row như **CheckAndMutate**. Với một aggregate được biểu diễn trong cùng row, có thể tận dụng bảo đảm nguyên tử trong phạm vi row. **Hai row khác nhau không tự thuộc một transaction chung** vì ứng dụng gọi hai lệnh kiểm tra lần lượt.

### 10.5. Redis

~~~redis
SET lock:order:O-101 owner-token NX PX 30000
~~~

Một lệnh như trên có thể hỗ trợ lấy lease, nhưng không phải hàng rào duy nhất để bảo vệ tiền hoặc tồn kho: lease có thể hết hạn, owner cũ tiếp tục chạy, và tính bền vững/failover/eviction phụ thuộc triển khai. Với lệnh quan trọng, cần điều kiện/version hoặc **fencing** tại tài nguyên có thẩm quyền.

**Không có khuyến nghị mặc định “NoSQL X tốt hơn Y”**; chỉ có cơ chế phù hợp với loại bất biến và workload cụ thể.

## 11. Validation, atomicity, consistency, isolation và durability

Các khái niệm này thường bị nhầm:

| Khái niệm | Câu hỏi cần trả lời |
| --- | --- |
| Validation | Trạng thái cuối có hợp lệ theo schema/domain không? |
| Atomicity | Một nhóm thay đổi trong phạm vi được hỗ trợ có cùng thành công hoặc thất bại không? |
| Consistency/visibility | Sau ghi, đường đọc nào nhìn thấy phiên bản nào, trong điều kiện gì? |
| Isolation | Hai thao tác đồng thời có thể thấy nhau và tranh chấp như thế nào? |
| Durability | Sau khi hệ thống xác nhận thành công, dữ liệu sống sót qua các lỗi nào? |

Một document có quantity dương vẫn có thể bị hai yêu cầu cấp phát sai. Một lệnh điều kiện nguyên tử vẫn có thể được **gửi lại** do timeout. Một write được ack ở một consistency level chưa chắc lập tức hiển thị ở mọi replica. Một state machine đúng không cứu được thao tác thanh toán bên ngoài bị nhân đôi.

Vì thế câu “database đã bảo đảm constraint” chỉ có nghĩa khi ghi rõ **phạm vi nguyên tử, điểm đọc, consistency, độ bền và hành vi khi lỗi**.

### 11.1. Cache và search index không phải điểm quyết định tồn kho

Ví dụ:

~~~text
Cache/search: available = 1 (bản cũ)
Primary:      available = 0 (bản mới)
~~~

Cache có thể dùng để **hiển thị** thông tin gần đúng theo SLO độ mới đã chấp nhận. Khi checkout, application phải gọi **reserve có điều kiện** tới Inventory Store có thẩm quyền. Chỉ đọc cache rồi chấp nhận giao dịch không bảo vệ bất biến.

## 12. Chọn ranh giới giữa document, aggregate và dịch vụ

Khi bất biến trải qua nhiều tài liệu, có một số cách tiếp cận:

1. **Gộp những field thực sự cần thay đổi atomically** vào một document/row nếu kích thước và tranh chấp cho phép.
2. **Dùng conditional update hoặc unique index** để biến cuộc đua thành một điểm quyết định.
3. **Dùng transaction đa item** khi engine hỗ trợ đúng phạm vi và hiệu năng chấp nhận.
4. **Giao quyền quyết định cho một service sở hữu aggregate**, các nơi khác gửi command và chấp nhận read model có thể trễ.
5. **Dùng saga, outbox, idempotency và reconciliation** khi phải thực hiện nhiều bước ở những kho không thể transaction chung.

### 12.1. Trạng thái có thể trễ khác với bất biến bắt buộc tức thì

Một dashboard doanh thu trễ 60 giây có thể chấp nhận theo yêu cầu. Nhưng “không bán vượt tồn kho” thường không thể tạm phá rồi hy vọng dữ liệu hội tụ sau một phút.

Thiết kế eventual consistency phải ghi rõ **điều gì được phép tạm khác nhau**, và **điều gì luôn cần được quyết định nguyên tử**.

### 12.2. Ví dụ đặt phòng: unique index không ngăn khoảng chồng lấn

Giả sử có hai booking:

~~~text
A: room R-08, [01/12 14:00, 03/12 10:00)
B: room R-08, [02/12 14:00, 04/12 10:00)
~~~

Unique index trên **(roomId, checkIn)** không ngăn hai khoảng trên vì checkIn khác nhau, dù khoảng giao nhau. Schema của từng booking cũng không biết booking khác.

Muốn cấm overlap, có thể cần:

- Một aggregate availability theo room/time slot được cập nhật nguyên tử.
- Rời rạc hóa slot với khóa duy nhất và transaction đủ phạm vi.
- Một coordinator/command serialization có điểm ghi cuối bảo vệ bằng điều kiện.
- Một cơ chế transaction/lock thích hợp, với bài test tranh chấp và xử lý retry.

Chọn cách nào phụ thuộc độ phân giải thời gian, số phòng, phân bố yêu cầu và giới hạn của database. Không giải quyết bằng một unique index trên bookingId.

## 13. Giữ hợp đồng giữa các lớp khi phát hành phiên bản mới

Nếu luật được diễn đạt ở nhiều lớp, chúng có thể lệch khi triển khai:

~~~text
API mới:    quantity >= 1
Worker cũ:  quantity >= 0
DB schema:  quantity >= 0
~~~

Worker cũ vẫn có thể ghi quantity = 0. Để tránh **constraint drift**:

- Xác định một chủ sở hữu và tài liệu hợp đồng nghiệp vụ có version.
- Duy trì test vectors cho các trường hợp hợp lệ/không hợp lệ ở cả domain và DB.
- Đưa bất biến dữ liệu cốt lõi xuống database nếu engine hỗ trợ, nhất là khi có nhiều writer.
- Triển khai reader/writer tương thích rồi mới siết schema.
- Quản lý các script import, backfill, worker cũ và quyền bypass validator.
- Theo dõi constraint violations theo service và version ứng dụng.

Không cần copy-paste mọi chi tiết ở tất cả lớp. Tốt hơn là để **application trả lỗi giàu ngữ cảnh**, còn **database bảo vệ các ràng buộc cần nguyên tử và chống dữ liệu sai từ mọi đường ghi**.

### 13.1. Thêm ràng buộc trên dữ liệu cũ

Ví dụ trước đây contactEmail được phép thiếu, nay mọi order mới phải có. Không nên bật validator bắt buộc ngay nếu dữ liệu cũ và writer cũ chưa sẵn sàng.

Một quy trình **Expand → Migrate → Enforce**:

1. Khảo sát dữ liệu cũ: bao nhiêu bản ghi thiếu, sai kiểu, trùng mã?
2. Phát hành reader đọc được cả dạng cũ và mới.
3. Writer mới bắt đầu ghi đúng cấu trúc mới.
4. Backfill theo batch có checkpoint, giám sát lỗi và đối soát.
5. Khi mọi writer phù hợp, bật validator/unique constraint chặt hơn.
6. Bỏ nhánh tương thích cũ khi an toàn.

MongoDB có chế độ warn/moderate phù hợp một số giai đoạn quan sát theo ngữ nghĩa của sản phẩm, nhưng **chúng không tự làm sạch dữ liệu cũ**. Unique index có thể không tạo được nếu dữ liệu hiện tại đã trùng.

Nếu không có nguồn chứng minh tiền tệ của order cũ là gì, **đừng gán bừa giá trị mặc định** chỉ để qua validator. Dữ liệu đúng cấu trúc nhưng sai ngữ nghĩa còn nguy hiểm hơn một record được đánh dấu cần đối soát.

## 14. Lỗi kỹ thuật và lỗi nghiệp vụ cần phản hồi khác nhau

| Lỗi | Tình huống | Hành động ứng dụng |
| --- | --- | --- |
| Input invalid | Quantity âm, thiếu field | Trả validation error, không retry |
| Duplicate key | External order đã tồn tại | Trả kết quả idempotent nếu cùng request, hoặc conflict |
| Conditional check failed | Hết stock, order không còn PENDING | Đọc lại và quyết định theo nghiệp vụ |
| Version conflict | Có writer khác sửa trước | Retry có giới hạn khi an toàn hoặc trả conflict |
| Unknown commit | Database commit nhưng ACK mất | Tra cứu theo operationId trước khi làm lại |
| Database unavailable | Không quyết định được trạng thái nguồn | Trả processing/unavailable, không báo thành công giả |
| Duplicate event | Consumer nhận lại event | Bỏ qua hoặc áp dụng idempotent theo ID/version |
| Compensation failed | Chưa giải phóng reserve | Giữ trạng thái phục hồi, retry và cảnh báo |

Đặc biệt, **retry không có idempotency** có thể tạo hai đơn, hai lần trừ kho hoặc hai lần thanh toán. Retry vô hạn cũng làm tăng tải khi hệ thống đang gặp lỗi.

## 15. Kiểm thử bất biến dưới cạnh tranh và sự cố

Unit test của domain là cần thiết, nhưng không chứng minh đầy đủ tính đúng của hệ thống phân tán.

### 15.1. Test matrix

| Kiểm tra | Kịch bản | Điều phải đúng |
| --- | --- | --- |
| Domain | Quantity = 0 hoặc total sai | Từ chối trước ghi |
| Database integration | Ghi document sai kiểu/required | Validator DB từ chối |
| Duplicate insert | 100 request cùng externalOrderId | Tối đa một order logic được chấp nhận |
| Inventory contention | 100 request tranh 10 đơn vị | Không cấp phát hơn 10 |
| Optimistic version | Hai writer từ version 7 | Chỉ update có điều kiện hợp lệ thành công |
| Unknown commit | Mất ACK sau commit | Retry không tạo tác dụng phụ trùng |
| Event replay | Giao sự kiện hai lần hoặc sai thứ tự | Không double-count, projection hội tụ đúng |
| Saga failure | Payment thành công, ghi Order thất bại | Có trạng thái đối soát và xử lý tiếp |
| Tenant isolation | Tenant A sửa tài nguyên B | Bị từ chối |
| Schema rollout | Writer V1 và V2 cùng chạy | Không chấp nhận trạng thái ngoài hợp đồng |

### 15.2. Một phép kiểm tra tồn kho cụ thể

Ban đầu:

~~~text
available = 10
reserved  = 0
~~~

Gửi 100 lệnh reserve 1 đơn vị đồng thời, mỗi lệnh có **operationId riêng**; gửi lại 20% lệnh với **cùng operationId**. Kết quả phải chứng minh:

~~~text
Số reserve thành công duy nhất <= 10
available >= 0
reserved >= 0
available + reserved = 10  (khi chưa có release/fulfill)
Một operationId không trừ tồn kho hai lần
Không có request bị từ chối lại báo thành công giả
~~~

Điều cần quan sát không chỉ là **available cuối không âm**, mà còn là **số lệnh thực sự được chấp nhận** và số đơn vị đã cấp phát. Khi có fulfill/release, tổng bất biến cần được thay đổi cho đúng trạng thái vận hành.

### 15.3. Fault injection

Trong môi trường thử nghiệm có kiểm soát:

- Dừng service sau database commit nhưng trước khi phát event.
- Cắt mạng sau khi server ghi, trước khi client nhận phản hồi.
- Gửi duplicate event và payment callback nhiều lần.
- Cho worker giữ lease chạy tiếp sau hạn.
- Tạo conflict khi hai worker chuyển trạng thái.
- Mô phỏng consumer restart, outbox backlog và payment unknown.

Mỗi test cần có **kỳ vọng về bất biến và cách đối soát**. Không cần phá production để chứng minh một giả thuyết thiết kế.

## 16. Quan sát ràng buộc trong vận hành

Các chỉ số nên theo dõi:

- Số lần schema/unique/conditional constraint từ chối ghi, theo nguyên nhân và phiên bản writer.
- Số operationId được phát hiện retry và trả kết quả cũ.
- Unknown commits, timeout, transaction conflict và số lần retry.
- Outbox backlog, consumer lag, duplicate message và idempotency rejection.
- Saga quá hạn, compensation chưa hoàn thành, payment chưa được đối soát.
- Số bất biến vi phạm do job reconciliation phát hiện.
- p95/p99 latency của transaction, LWT hoặc conditional write vì tính đúng cũng có chi phí.

Ví dụ job đối soát có thể tìm:

~~~text
Orders CONFIRMED nhưng không có reservation cuối hợp lệ.
Payments SUCCEEDED nhưng order vẫn PENDING quá ngưỡng.
Hai logical orders cùng một idempotency key.
Inventory có available hoặc reserved âm.
Consumer projection ghi nhiều lần cùng event ID.
~~~

Đối soát giúp phát hiện và phục hồi trạng thái sai hoặc chưa hoàn tất, **không thay thế việc bảo vệ bất biến khi ghi**. Thông tin nhạy cảm trong payment hoặc hồ sơ cá nhân không nên ghi nguyên vào log để điều tra constraint failure.

## 17. Khung quyết định thực hành

Khi nhận một quy tắc nghiệp vụ mới, nên đi theo trình tự:

1. **Viết rõ bất biến và phạm vi:** một field, một document, nhiều item, hay nhiều service?
2. **Xác định nơi có thẩm quyền:** ai được quyền quyết định cuối?
3. **Xác định đường ghi:** API, worker, batch, import, admin, event consumer.
4. **Đánh giá cơ chế nguyên tử có thật:** schema validation, unique index, conditional update, transaction, consensus/coordination.
5. **Đặt hàng rào cuối ở điểm ghi phù hợp:** không tin vào precheck khi có concurrency.
6. **Thêm domain/API validation:** diễn đạt luật, quyền, thông báo lỗi.
7. **Thiết kế retry/idempotency/unknown commit:** đặc biệt khi có tác dụng phụ.
8. **Xây test đồng thời, fault injection và reconciliation.**
9. **Lập kế hoạch triển khai schema/contract và chỉ số giám sát.**

### 17.1. Các sai lầm thường gặp

1. Chỉ kiểm tra ở controller, bỏ quên worker và import.
2. Tưởng schema validator tự ngăn duplicate giữa nhiều document.
3. Đọc rồi ghi vô điều kiện, không chặn race.
4. Coi một batch lệnh là transaction đa partition đầy đủ.
5. Dùng Redis lease như khóa bảo đảm vĩnh viễn khi worker cũ vẫn có thể ghi.
6. Quyết định giao dịch dựa trên cache hoặc search index có thể stale.
7. Retry với ID mới làm xử lý trùng nhưng vẫn có các ID duy nhất.
8. Đưa payment provider vào sơ đồ transaction rồi cho rằng có ACID toàn hệ.
9. Nhét mọi thứ vào một document vì muốn atomicity, dẫn tới hot document hoặc vượt giới hạn.
10. Bật validator mới trước khi xử lý dữ liệu cũ và writer phiên bản trước.
11. Chỉ kiểm tra trạng thái cuối không âm, không đối chiếu số thao tác đã báo thành công.
12. Chặn dữ liệu sai nhưng không có cách phục hồi khi workflow bị kẹt giữa các bước.

## 18. Bài tập: đặt vé cho sự kiện có 100 chỗ

Ứng dụng bán tối đa **100 vé** cho một suất diễn. Mỗi khách đặt **1 đến 4 vé**, request có idempotencyKey. Booking có trạng thái:

~~~text
PENDING -> RESERVED -> PAID
                    -> EXPIRED / CANCELLED
~~~

Yêu cầu:

- Quantity là số nguyên từ 1 đến 4.
- Số vé đã giữ và đã bán không được vượt sức chứa 100.
- Cùng (tenantId, idempotencyKey) không tạo hai booking logic.
- Booking EXPIRED không được chuyển sang PAID nếu nghiệp vụ cấm.
- Reservation có thời hạn 10 phút, nhưng callback payment có thể đến muộn.
- Nếu payment provider xác nhận đã thu tiền, hệ thống không được mất dấu nghĩa vụ hoàn tất/hoàn tiền.

### Phần A — Phân loại bất biến

Hãy phân loại từng yêu cầu: field/schema, quan hệ giữa trường, uniqueness, cập nhật theo trạng thái cũ, nhiều item hoặc workflow xuyên dịch vụ. Chỉ ra nơi có thẩm quyền cho từng quy tắc.

### Phần B — Chọn aggregate

Đề xuất:

~~~text
EventCapacity:
  eventId, totalSeats=100, available, reserved, sold, version

Booking:
  bookingId, eventId, customerId, quantity,
  status, reservationId, expiresAt, version,
  paymentReference, idempotencyKey
~~~

Quy tắc nào thuộc một aggregate? Quy tắc nào liên quan cả Booking và EventCapacity? Nếu dùng hai document, cần transaction hoặc cách phối hợp nào?

### Phần C — Tranh chấp

Ban đầu available = 1. Hai khách gửi reserve một vé cùng lúc. Thiết kế một lệnh **conditional update** sao cho chỉ một yêu cầu được xác nhận. Vì sao chỉ kiểm tra available > 0 tại application không đủ?

### Phần D — Retry và thanh toán đến muộn

Reserve đã thành công nhưng Order Service timeout. Client retry. Làm sao tránh giảm available lần hai? Nếu reservation đã EXPIRED nhưng payment báo SUCCESS, hệ thống cần trạng thái đối soát và xử lý hoàn tiền/hoàn tất thế nào để không vừa cấp vé sai vừa giữ khoản tiền chưa giải quyết?

### Phần E — Thử nghiệm

Tạo **1.000 request đồng thời** tranh 100 vé, trong đó 20% được gửi lại với cùng operationId. Kiểm tra:

~~~text
Không quá 100 vé được giữ/bán hợp lệ.
Không có số lượng âm.
Một operationId chỉ có một kết quả logic.
Không chuyển EXPIRED -> PAID trái luật.
Mỗi payment success có booking hợp lệ
hoặc quy trình đối soát/hoàn tiền rõ ràng.
~~~

Tiếp tục thử crash sau reserve, mất ACK, callback trùng và phục hồi outbox/consumer. Kết quả đúng phải được chứng minh **cả ở trạng thái dữ liệu và lịch sử các thao tác được báo thành công**.

### Hướng giải

Quantity 1–4 được kiểm tra ở application/domain và ở schema database nếu có. **Sức chứa 100 vé** cần một điểm cấp phát nguyên tử có điều kiện tại EventCapacity, kết hợp idempotency để retry không giảm số vé nhiều lần. **Booking duy nhất theo idempotencyKey** cần unique/conditional create đúng phạm vi. **Chuyển trạng thái** cần state machine và ghi có điều kiện. **Thanh toán** cần workflow bền vững, idempotency, compensation và reconciliation; TTL của reservation không phải bảo đảm cuối.

**Kết luận:** Với NoSQL, hãy đặt ràng buộc theo **phạm vi bất biến**. Quy tắc đầu vào, quyền và ngữ nghĩa thuộc **domain/application**; quy tắc phải đứng vững dưới cạnh tranh cần một **hàng rào tại database hoặc điểm ghi nguyên tử**; quy trình nhiều aggregate và dịch vụ cần **giao thức phối hợp, idempotency và khả năng phục hồi**. Thiết kế đúng không phải chọn một lớp duy nhất để chứa mọi luật, mà là chỉ rõ **ai sở hữu quyết định, trạng thái nào phải luôn đúng và hệ thống chứng minh điều đó ra sao khi gặp lỗi**.
