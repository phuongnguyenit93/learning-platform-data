# Liên hệ ranh giới aggregate với phạm vi nguyên tử của hệ lưu trữ

Một hệ thống bán hàng phải bảo đảm **không bán quá số lượng tồn kho**, **một đơn hàng không có tổng tiền sai**, và **một lần thanh toán không bị ghi nhận hai lần**. Những quy tắc đó được gọi là **bất biến nghiệp vụ (business invariants)**: các điều kiện phải tiếp tục đúng khi hệ thống thay đổi trạng thái.

Trong Domain-Driven Design (DDD), **aggregate** là một nhóm thực thể và value object được xem như một **ranh giới nhất quán**. Mọi thay đổi ảnh hưởng đến các bất biến bên trong nhóm được điều phối qua một **aggregate root**. Trong NoSQL, lựa chọn này liên quan chặt chẽ đến câu hỏi kỹ thuật: *cơ sở dữ liệu có thể cập nhật nguyên tử những phần dữ liệu nào?*

Ví dụ:

- Một document MongoDB có thể chứa trạng thái tồn kho của một SKU và được cập nhật có điều kiện trong **một thao tác nguyên tử**.
- Nếu đơn hàng và tồn kho thuộc **hai document**, cần cơ chế bổ sung nếu muốn cả hai thay đổi cùng thành công hoặc cùng thất bại.
- Nếu đơn hàng, kho và thanh toán thuộc **nhiều hệ thống độc lập**, một transaction ở một database không đủ để bảo đảm toàn bộ quy trình.
- Nếu cố nhét mọi thứ vào **một aggregate/document rất lớn** để có tính nguyên tử, hệ thống lại gặp tranh chấp cập nhật, tăng kích thước và khó mở rộng.

Điểm cốt lõi là phải thiết kế đồng thời **ranh giới bất biến nghiệp vụ** và **phạm vi nguyên tử thực tế của công nghệ lưu trữ**, thay vì cho rằng chúng tự nhiên trùng nhau.

## 1. Aggregate trong DDD nghĩa là gì?

Một **aggregate** bao gồm một hoặc nhiều domain object được quản lý như một đơn vị nhất quán. Nó có một **aggregate root**, là đầu mối mà ứng dụng dùng để thực hiện các thay đổi có ảnh hưởng đến bất biến của aggregate.

Ví dụ một đơn hàng:

~~~text
Order aggregate
└── Order (aggregate root)
    ├── orderId
    ├── tenantId
    ├── status
    ├── OrderLine[]
    │   ├── productId
    │   ├── quantity
    │   └── unitPriceMinor
    ├── currency
    └── totalMinor
~~~

Bất biến có thể gồm:

1. Mỗi `OrderLine.quantity` phải lớn hơn 0.
2. Mọi dòng hàng trong đơn phải dùng đơn vị tiền tương thích với quy tắc tính tổng.
3. `totalMinor` phải bằng tổng `quantity × unitPriceMinor` của các dòng, có xét giảm giá và thuế theo hợp đồng nghiệp vụ.
4. Không được sửa danh sách dòng hàng nếu đơn đã chuyển sang trạng thái không cho phép chỉnh sửa.
5. Chuyển trạng thái phải đi theo quy trình hợp lệ, ví dụ `DRAFT → CONFIRMED → SHIPPED`.

Những bất biến này có thể được thực thi bằng các phương thức của aggregate root:

~~~java
public final class Order {
    private OrderStatus status;
    private final List<OrderLine> lines;
    private long totalMinor;

    public void addLine(OrderLine line) {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Only draft orders can change");
        }
        if (line.quantity() <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        lines.add(line);
        totalMinor = calculateTotal(lines);
    }

    // Những phương thức khác quản lý chuyển trạng thái...
}
~~~

Đoạn code chỉ minh họa **đặt quy tắc tại aggregate root**, chưa phải class Java hoàn chỉnh. Trong ứng dụng thật, cần xử lý phép tính tiền an toàn tràn số, immutable/value objects, thuế/giảm giá và persistence mapping.

### Ranh giới aggregate có ba ý nghĩa

| Ý nghĩa | Câu hỏi cần trả lời |
|---|---|
| **Ranh giới nghiệp vụ** | Những trạng thái nào phải cùng đúng ngay khi một thao tác kết thúc? |
| **Ranh giới truy cập** | Ứng dụng thay đổi các entity bên trong thông qua root nào? |
| **Ranh giới nhất quán** | Khi một lệnh ghi thành công, các bất biến nào phải được bảo vệ đồng thời? |

DDD thường khuyến khích **aggregate đủ nhỏ để bảo vệ một tập bất biến rõ ràng**, đồng thời dùng phối hợp qua sự kiện hoặc quy trình cho những ràng buộc giữa các aggregate. Đây là hướng thiết kế, không phải định luật yêu cầu mọi aggregate chỉ chứa đúng một entity hay một document.

## 2. Phạm vi nguyên tử của cơ sở dữ liệu là gì?

**Atomicity** là tính chất *all-or-nothing* của một đơn vị thao tác: nếu thao tác được xem là nguyên tử, các thay đổi thuộc đơn vị đó không xuất hiện như một trạng thái hoàn tất một phần theo bảo đảm của hệ lưu trữ.

Cần phân biệt atomicity với:

- **Isolation:** mức độ các thao tác đồng thời nhìn thấy hoặc ảnh hưởng lẫn nhau.
- **Durability:** một thao tác đã xác nhận thành công sống sót qua lỗi đến mức nào theo cấu hình ghi và replication.
- **Consistency của dữ liệu nghiệp vụ:** bất biến như “tồn kho không âm” còn đúng không.
- **Read consistency:** dữ liệu đọc từ replica hoặc nhiều nguồn có thể mới đến đâu.
- **Idempotency:** gửi cùng một ý định nhiều lần có tạo thêm hiệu ứng không.

Một database có thao tác ghi nguyên tử **không tự biết** các quy tắc nghiệp vụ. Chẳng hạn nó có thể cập nhật `available` từ 3 thành -2 một cách hoàn toàn nguyên tử nếu lệnh ghi không kèm điều kiện chống âm. Atomicity bảo đảm thao tác không bị chia đôi, nhưng **logic điều kiện đúng vẫn do ứng dụng thiết kế**.

### Phạm vi khác nhau giữa các hệ NoSQL

| Hệ lưu trữ/cơ chế | Đơn vị thường được bảo vệ | Giới hạn cần nhớ |
|---|---|---|
| **MongoDB single-document write** | Thao tác ghi nguyên tử ở cấp một document | Không tự bảo đảm quy tắc liên document hay idempotency khi retry |
| **MongoDB multi-document transaction** | Các thao tác nằm trong transaction được hỗ trợ | Có chi phí, hạn chế vận hành và cần xử lý lỗi/retry/commit không rõ kết quả |
| **DynamoDB conditional item write** | Thay đổi có điều kiện trên một item | Điều kiện ở một item không tự bảo vệ bất biến trải trên nhiều item |
| **DynamoDB TransactWriteItems** | Nhóm thao tác trên nhiều item trong phạm vi transaction được dịch vụ hỗ trợ | Có giới hạn về số item, dung lượng và hành vi conflict; không phải transaction xuyên mọi dịch vụ AWS |
| **Cassandra LWT/CAS** | Thao tác điều kiện với semantics Paxos theo phạm vi được hỗ trợ | Không tương đương một transaction ACID tùy ý bao trùm nhiều partition |
| **Redis command/Lua/transaction** | Tính nguyên tử trong phạm vi thực thi và topology được hỗ trợ | Cluster, key slot, persistence và external side effect có giới hạn riêng |
| **Event broker + nhiều database** | Thường là giao nhận message theo hợp đồng broker | Không tự biến nhiều database và dịch vụ thành một transaction chung |

Bảng chỉ nêu hướng tư duy. Khi triển khai cần đối chiếu **phiên bản, chế độ standalone/cluster/sharded, consistency level, transaction API và cấu hình** của sản phẩm cụ thể.

## 3. Aggregate không đồng nghĩa với document

Đây là sự phân biệt quan trọng nhất của bài học.

- **Aggregate** là khái niệm mô hình nghiệp vụ, chọn theo **bất biến và cách thay đổi trạng thái**.
- **Document/item** là đơn vị lưu trữ, chọn theo **truy cập, kích thước, partition và khả năng ghi**.
- **Transaction** là cơ chế hỗ trợ thực thi thay đổi theo một phạm vi nguyên tử nhất định.

Có thể gặp nhiều cách ánh xạ:

| Cách ánh xạ | Khi có thể phù hợp | Rủi ro |
|---|---|---|
| Một aggregate → một document | Aggregate nhỏ, các thay đổi cần nguyên tử cùng lúc, thường đọc cùng nhau | Document lớn/hot, giới hạn kích thước, tranh chấp |
| Một aggregate → nhiều document trong transaction | Có những thành phần cần lưu riêng nhưng chung bất biến mạnh | Transaction phức tạp/đắt, xuyên shard khó hơn |
| Một aggregate → một item và các projection phụ | Dữ liệu nguồn gọn, nhu cầu đọc khác nhau | Projection phải đồng bộ, có thể tạm thời trễ |
| Nhiều aggregate → nhiều document/item | Mỗi aggregate có vòng đời và bất biến riêng | Quy trình liên aggregate cần phối hợp |
| Nhiều aggregate → một document | Hợp lý trong vài trường hợp thật sự rất nhỏ và gắn chặt | Dễ nhầm ownership, tăng contention và coupling |

**Nhúng dữ liệu (embedding) có thể đưa các trạng thái cần đổi cùng nhau vào một document**, giúp tận dụng atomicity cấp document. Nhưng nhúng hai đối tượng vào cùng một document **không tự động** chứng minh chúng thuộc cùng aggregate; vẫn phải xem mỗi đối tượng có vòng đời và bất biến độc lập hay không.

### Một dấu hiệu chọn aggregate quá rộng

Nếu một “aggregate” bao trùm mọi sản phẩm của một cửa hàng chỉ vì muốn kiểm tra tổng tồn kho, mỗi lần cập nhật một SKU có thể phải tranh chấp với tất cả SKU còn lại. Aggregate này có thể quá lớn, trong khi quy tắc toàn cửa hàng nên được thiết kế bằng một cơ chế quản lý hạn mức riêng hoặc transaction/điều phối phù hợp.

### Một dấu hiệu chọn aggregate quá hẹp

Nếu tổng tiền đơn hàng nằm ở một document, các dòng hàng ở nhiều document khác, và ứng dụng ghi chúng bằng nhiều lệnh độc lập không có bảo vệ, một lỗi giữa chừng có thể khiến `totalMinor` không khớp danh sách dòng hàng. Nếu bất biến này cần đúng ngay sau mỗi lệnh, cách chia dữ liệu đang làm việc bảo vệ bất biến khó hơn đáng kể.

## 4. Bắt đầu từ bất biến, rồi mới chọn ranh giới lưu trữ

Có thể thực hiện một bài tập thiết kế theo từng bước.

Ví dụ với hệ thống bán hàng:

| Quy tắc | Loại bất biến | Cần đúng ở thời điểm nào? | Ứng viên ranh giới |
|---|---|---|---|
| Tổng đơn bằng tổng các dòng | Bên trong đơn hàng | Ngay khi cập nhật đơn hoàn tất | Order aggregate |
| Tồn khả dụng của một SKU không âm | Bên trong trạng thái kho của SKU | Ngay khi đặt chỗ/trừ tồn thành công | Stock aggregate |
| Không tạo hai booking cho cùng một slot còn hiệu lực | Liên yêu cầu, có cạnh tranh | Ngay tại thao tác giữ slot | Slot/Reservation aggregate hoặc unique/conditional constraint |
| Đơn được gửi email xác nhận | Liên hệ thống | Có thể sau khi đơn được xác nhận | Event + consumer |
| Tổng số đơn trong báo cáo ngày | Derived data | Chấp nhận trễ theo SLA | Projection/analytics |
| Không ghi thanh toán thành công hai lần cho cùng giao dịch | Liên dịch vụ/nguồn thanh toán | Phải có rào chắn trước khi ghi nhận | Payment identity, idempotency, quy trình đối soát |

Cách chọn tốt không bắt đầu bằng “MongoDB hỗ trợ atomic một document nên gom hết vào một document”. Nó bắt đầu bằng **điều gì không được sai dù có hai lệnh đồng thời hoặc một tiến trình chết ở giữa**, rồi tìm khả năng nguyên tử đủ để thực thi.

## 5. Ví dụ 1: aggregate tồn kho nằm trong một document

Giả sử mỗi SKU tại một kho có một document:

~~~javascript
{
  _id: "tenant-a:warehouse-HCM:sku-101",
  tenantId: "tenant-a",
  warehouseId: "warehouse-HCM",
  sku: "sku-101",
  available: 8,
  reserved: 2,
  version: NumberLong("7"),
  updatedAt: ISODate("2026-11-14T08:00:00Z")
}
~~~

**Bất biến nội bộ** có thể là:

\[
available \ge 0,\quad reserved \ge 0
\]

Nếu có `onHand` đại diện tổng tồn vật lý, cần định nghĩa quan hệ với `available`, `reserved` và các trạng thái khác. Chẳng hạn `onHand = available + reserved` chỉ đúng nếu mô hình không có hàng hỏng, hàng đang vận chuyển hay các loại tồn khác.

### Phép trừ tồn có điều kiện

Một request muốn giữ 3 sản phẩm. Lệnh MongoDB:

~~~javascript
const quantity = 3; // Đã được service kiểm tra là số nguyên dương.

const result = db.inventory.updateOne(
  {
    _id: "tenant-a:warehouse-HCM:sku-101",
    available: { $gte: quantity }
  },
  {
    $inc: {
      available: -quantity,
      reserved: quantity,
      version: NumberLong("1")
    },
    $currentDate: { updatedAt: true }
  }
);
~~~

Ở đây:

1. **Điều kiện** `available >= quantity` là một phần của thao tác update.
2. Nếu document khớp, các field được tăng/giảm trong **cùng một phép ghi nguyên tử cấp document**.
3. Nếu không đủ hàng, document không khớp và không bị trừ.
4. Hai lệnh đồng thời cùng tranh document phải tuân theo điều kiện cập nhật thực tế ở thời điểm thực thi; không thể cả hai cùng tùy ý trừ vượt số tồn theo cách đọc cũ ở ứng dụng.

Kiểm tra kết quả:

~~~javascript
if (result.matchedCount === 0) {
  // Không có item phù hợp hoặc tồn không đủ.
  // Phân biệt nguyên nhân bằng chính sách xử lý nghiệp vụ.
}
~~~

**Không đủ hàng** và **không tồn tại SKU** đều có thể dẫn đến `matchedCount = 0`. Nếu API cần phân biệt, có thể đọc thêm để chẩn đoán, nhưng việc đọc đó không thay thế điều kiện nguyên tử ở phép update.

### Vì sao đọc trước rồi ghi sau có thể sai?

Cách dễ mắc lỗi:

~~~javascript
const stock = db.inventory.findOne({ _id: stockId });

if (stock.available >= quantity) {
  db.inventory.updateOne(
    { _id: stockId },
    { $set: { available: stock.available - quantity } }
  );
}
~~~

Hai request đồng thời đều có thể đọc `available = 8` rồi cùng ghi `available = 5`. Khi đó hệ thống **đã nhận hai yêu cầu giữ 3 sản phẩm** nhưng chỉ ghi nhận giảm 3. Đây là **lost update** và sai về nghiệp vụ, dù từng lệnh update riêng vẫn nguyên tử.

Biện pháp là đưa điều kiện vào phép ghi, hoặc dùng optimistic concurrency với version và kiểm tra kết quả. Atomicity của document không tự sửa cách triển khai read-modify-write ở ứng dụng.

### Nhưng retry có thể trừ hai lần

Giả sử phép cập nhật đã thành công, nhưng client timeout trước khi nhận response và gửi lại request. Vì `available` vẫn đủ, lệnh có thể trừ thêm lần nữa. **Conditional update bảo vệ giới hạn tồn kho nhưng không bảo đảm mỗi ý định chỉ được xử lý một lần**.

Cần idempotency theo request/reservation:

- Một `reservationId` duy nhất cho ý định giữ hàng.
- Bảo vệ việc tạo reservation khỏi trùng.
- Gắn thay đổi tồn kho với việc ghi nhận reservation trong cùng phạm vi nguyên tử phù hợp.
- Nếu cần nhiều document, cân nhắc transaction; nếu reservation có thể nhúng trong một document kích thước nhỏ và có giới hạn, có thể thiết kế điều kiện cập nhật cùng record.
- Khi retry, trả lại kết quả đã có thay vì giữ hàng lần nữa.

Ví dụ này cho thấy **một invariant mạnh còn có thể cần nhiều cơ chế**: atomic conditional update + idempotency + quản lý vòng đời reservation.

## 6. Version và optimistic concurrency ở ranh giới aggregate

Một aggregate có thể được lưu bằng một document chứa field `version`. Khi đọc, ứng dụng biết phiên bản hiện tại, sau đó chỉ ghi nếu phiên bản chưa đổi.

~~~javascript
const expectedVersion = NumberLong("7");

const result = db.orders.updateOne(
  {
    _id: "order-101",
    version: expectedVersion,
    status: "DRAFT"
  },
  {
    $set: {
      deliveryNote: "Giao trong giờ hành chính"
    },
    $inc: {
      version: NumberLong("1")
    }
  }
);
~~~

Nếu `matchedCount = 0`, có thể là aggregate đã bị sửa hoặc không còn ở trạng thái `DRAFT`. Ứng dụng cần nạp lại dữ liệu, xử lý xung đột theo nghiệp vụ, hoặc trả lỗi phù hợp cho client.

### Optimistic concurrency giải quyết vấn đề gì?

Giả sử hai người cùng mở một đơn hàng:

~~~mermaid
sequenceDiagram
    participant A as User A
    participant B as User B
    participant DB as Order document
    A->>DB: Đọc order, version 7
    B->>DB: Đọc order, version 7
    A->>DB: Update WHERE version = 7
    DB-->>A: Thành công, version 8
    B->>DB: Update WHERE version = 7
    DB-->>B: Không khớp, xung đột
~~~

Version giúp tránh **ghi đè âm thầm thay đổi của người khác**. Nhưng không nên retry tự động bằng cách áp nguyên bản update cũ lên dữ liệu mới nếu điều đó làm mất ý định hoặc phá quy tắc nghiệp vụ. Cần định nghĩa cơ chế merge, báo người dùng hoặc tính lại lệnh với state mới.

**Version của aggregate** là một công cụ điều phối thay đổi trạng thái. Nó không cần đồng nhất với `schemaVersion`, là version của định dạng lưu trữ; hai loại version giải quyết hai vấn đề khác nhau.

## 7. Đặt OrderLine trong Order aggregate: khi nào embedding hữu ích?

Giả sử đơn hàng thường có 1–20 dòng hàng và các dòng chỉ thay đổi qua thao tác trên đơn:

~~~javascript
{
  _id: "order-101",
  tenantId: "tenant-a",
  status: "DRAFT",
  currency: "VND",
  lines: [
    { lineId: "L1", sku: "sku-101", quantity: 2, unitPriceMinor: 100000 },
    { lineId: "L2", sku: "sku-205", quantity: 1, unitPriceMinor: 250000 }
  ],
  totalMinor: 450000,
  version: NumberLong("3")
}
~~~

Nếu các dòng và tổng tiền cùng nằm trong một document, một update có thể thay đổi cả hai nguyên tử. Nhưng cần bảo đảm logic tính tổng không phụ thuộc state đã lỗi thời.

Các cách thiết kế:

- Đọc aggregate, gọi domain method tính lại tổng, ghi bằng version check để tránh lost update.
- Dùng update pipeline của MongoDB nếu phép tính có thể biểu diễn hợp lệ, bảo đảm cập nhật cùng document.
- Chặn writer bypass domain bằng API/service boundary và validation.
- Áp dụng giới hạn số dòng, kích thước document và chính sách archive.

Đây là trường hợp **ranh giới aggregate và document có thể khớp tương đối tự nhiên** vì những bất biến như tổng tiền và trạng thái đơn liên quan trực tiếp đến các dòng.

### Không nên lưu mọi thứ liên quan đến đơn trong một document

Một đơn hàng có thể liên quan hàng nghìn sự kiện tracking, nhiều lần retry thanh toán, webhook log và bình luận hỗ trợ. Những dữ liệu này có vòng đời, tần suất ghi và kích thước khác nhau.

Nhúng tất cả vào `Order` có thể dẫn đến:

- Document lớn, mảng không giới hạn.
- Tranh chấp cập nhật giữa những tiến trình độc lập.
- Khó giữ lịch sử và phân trang.
- Tăng chi phí serialize/deserialize.
- Dễ đưa các trạng thái không cần nguyên tử vào cùng một đơn vị ghi.

Có thể giữ **trạng thái cốt lõi của Order** trong một aggregate nhỏ và lưu sự kiện/lịch sử dưới dạng document riêng, kết hợp idempotency, projection hoặc transaction khi cần.

## 8. Khi hai bất biến thuộc hai aggregate khác nhau

Một lần đặt hàng có thể liên quan:

- `Order`: dòng hàng, giá, trạng thái.
- `Stock`: số lượng khả dụng và đã giữ.
- `Payment`: trạng thái thanh toán và idempotency.
- `Shipment`: tiến trình giao hàng.

Không nên gom chúng vào một aggregate khổng lồ chỉ để có vẻ “nhất quán”.

### Phân loại nhất quán

**Bất biến cục bộ**:

- Order total phải khớp dòng hàng.
- Stock.available không âm.
- Một Payment không ghi nhận hai lần cùng một giao dịch.

**Quy tắc phối hợp liên aggregate**:

- Order chỉ chuyển CONFIRMED nếu đã giữ đủ stock.
- Thanh toán đã thu nhưng đặt hàng thất bại phải được hoàn/đối soát.
- Shipment chỉ được tạo khi đơn đủ điều kiện.

Quy tắc liên aggregate có thể cần transaction nếu dữ liệu cùng nằm trong một database và yêu cầu nguyên tử ngay, hoặc cần **quy trình trạng thái + event** nếu hệ thống phân tán hoặc chấp nhận nhất quán sau một khoảng thời gian.

### Cần phân biệt atomicity và hoàn tất quy trình

Giả sử Order được tạo trạng thái `PENDING_STOCK`, sau đó hệ thống giữ hàng rồi chuyển `CONFIRMED`. Trong khoảng thời gian ngắn, Order đã tồn tại nhưng chưa được xác nhận. **Đó không nhất thiết là lỗi** nếu mô hình nghiệp vụ cho phép trạng thái trung gian và quy định cách xử lý timeout, từ chối, retry và hoàn tác.

Một thiết kế đúng nên **diễn đạt trạng thái trung gian công khai và kiểm soát chúng**, thay vì tuyên bố cả quy trình sẽ xảy ra tức thời khi thực tế có nhiều dịch vụ tham gia.

## 9. Transaction nhiều document: khi nào cần?

Giả sử muốn chuyển tiền giữa hai tài khoản trong cùng một database:

- Tài khoản A giảm 50.000.
- Tài khoản B tăng 50.000.
- Tổng số tiền của cả hai không đổi nếu phép chuyển thành công.

Đây là ví dụ **bất biến trải qua nhiều document**. Nếu thực hiện hai update độc lập, tiến trình có thể dừng sau khi trừ A nhưng trước khi cộng B. Transaction nhiều document có thể là cơ chế phù hợp khi engine hỗ trợ và yêu cầu nghiệp vụ cần kết quả nguyên tử.

### Ví dụ MongoDB transaction bằng mongosh

Giả định có collection `accounts` với document:

~~~javascript
{ _id: "account-A", balanceMinor: NumberLong("200000") }
{ _id: "account-B", balanceMinor: NumberLong("100000") }
~~~

Một ví dụ minh họa:

~~~javascript
const amount = NumberLong("50000");
const session = db.getMongo().startSession();

try {
  const accounts = session.getDatabase(db.getName()).accounts;

  session.withTransaction(() => {
    const debit = accounts.updateOne(
      {
        _id: "account-A",
        balanceMinor: { $gte: amount }
      },
      { $inc: { balanceMinor: -amount } }
    );

    if (debit.matchedCount !== 1) {
      throw new Error("Tài khoản nguồn không đủ tiền hoặc không tồn tại");
    }

    const credit = accounts.updateOne(
      { _id: "account-B" },
      { $inc: { balanceMinor: amount } }
    );

    if (credit.matchedCount !== 1) {
      throw new Error("Tài khoản đích không tồn tại");
    }
  });
} finally {
  session.endSession();
}
~~~

**Các giả định và giới hạn:**

- Ví dụ dùng MongoDB trong môi trường hỗ trợ transaction theo cấu hình triển khai; không phải mọi standalone topology đều hỗ trợ giống nhau.
- Mục đích là minh họa thay đổi hai document trong cùng transaction, **chưa phải thiết kế hệ thống kế toán đầy đủ**.
- Giá trị tiền phải được lưu và thao tác bằng kiểu số phù hợp. Trong code JavaScript/mongosh, cách tạo toán hạng BSON và số âm cần khớp API thực tế.
- Callback transaction có thể được chạy lại khi driver xử lý lỗi giao dịch theo chính sách retry; **không gửi email, gọi cổng thanh toán hoặc tạo external side effect bên trong callback** mà không có bảo đảm idempotency.
- Tình huống commit có kết quả chưa rõ, lỗi conflict và timeout vẫn cần chính sách retry và kiểm tra trạng thái.
- Đối với hệ tài chính thật, cần thiết kế sổ cái, idempotency, đối soát và kiểm toán riêng; số dư hiện tại không thay thế lịch sử bút toán.

Ví dụ cho thấy transaction cung cấp **phạm vi nguyên tử kỹ thuật** để bảo vệ một thay đổi liên document. Nhưng DDD không yêu cầu phải biến hai tài khoản thành cùng một aggregate chỉ vì một transaction chuyển tiền đụng vào cả hai.

### Không nên dùng transaction để che giấu aggregate quá rộng

Nếu mọi lệnh trong hệ thống cần transaction bao trùm hàng chục collection và nhiều shard, đó có thể là dấu hiệu:

- Các bất biến chưa được phân loại theo phạm vi.
- Workflow đang cố hoàn tất đồng bộ quá nhiều bước.
- Dữ liệu được chia một cách không phù hợp với thao tác cốt lõi.
- Có cơ hội thiết kế lại aggregate, dùng reservation, counter hoặc state machine.
- Mô hình phải cân nhắc trade-off giữa nhất quán mạnh và độ sẵn sàng/hiệu năng.

Transaction rất hữu ích khi thật sự cần, nhưng việc mở rộng transaction có thể tăng xung đột và chi phí tài nguyên. **Nhu cầu nghiệp vụ quyết định độ mạnh nhất quán; độ mạnh nhất quán không tự quyết định ranh giới nghiệp vụ**.

## 10. Bài toán giới hạn sức chứa: chọn aggregate theo điểm tranh chấp

Giả sử dịch vụ đặt vé chỉ có **một ghế A12 cho một suất chiếu**. Bất biến:

\[
\text{Số booking hiệu lực cho }(showtimeId, seatId) \le 1
\]

Nếu hai request cùng đặt ghế:

~~~mermaid
sequenceDiagram
    participant C1 as Khách 1
    participant C2 as Khách 2
    participant DB as Storage
    C1->>DB: Kiểm tra A12 còn trống
    C2->>DB: Kiểm tra A12 còn trống
    DB-->>C1: Còn trống
    DB-->>C2: Còn trống
    C1->>DB: Tạo booking
    C2->>DB: Tạo booking
~~~

Chỉ đọc trước rồi insert là chưa đủ. Có thể áp đặt uniqueness qua khóa `(showtimeId, seatId)` của reservation hiệu lực, hoặc thiết kế conditional write lên **một item đại diện cho slot**:

~~~text
Key: SHOWTIME#S1 / SEAT#A12
status: AVAILABLE | HELD | SOLD
reservationId: ...
expiresAt: ...
version: ...
~~~

Mọi thao tác tranh A12 cùng đi qua slot item, và conditional update chỉ cho một thao tác chuyển `AVAILABLE → HELD` khi phù hợp. **Slot/SeatReservation** có thể là aggregate nhỏ đại diện cho bất biến “mỗi ghế chỉ được giữ bởi một bên tại một thời điểm”.

Nhưng cần quyết định:

- Hết hạn giữ chỗ sẽ làm gì với trạng thái?
- Người dùng giữ rồi thanh toán trễ thì sao?
- Nếu callback thanh toán đến hai lần thì sao?
- Nếu vé được bán rồi nhưng thao tác phát hành vé lỗi thì sao?
- Có cần nhiều ghế được giữ **cùng lúc hoặc không giữ ghế nào** không?

Khi một booking gồm nhiều ghế và yêu cầu giữ toàn bộ đồng thời, bất biến chuyển sang **nhiều slot/item**; có thể cần transaction nhiều item hoặc một cơ chế đặt chỗ nguyên tử khác. Ranh giới theo một ghế vừa đẹp cho tranh chấp một ghế nhưng chưa tự giải quyết booking nhiều ghế.

## 11. Unique constraint cũng là một công cụ bảo vệ invariant

Một số bất biến không phải số học mà là **tính duy nhất**:

- Mã SKU chỉ xuất hiện một lần trong một tenant.
- Một đơn hàng ngoài đối tác không được nhập thành hai đơn nội bộ.
- Một ghế không có hai reservation hiệu lực.
- Một idempotency key không tạo hai giao dịch đã chấp nhận.

Nếu hệ DB hỗ trợ unique index trong phạm vi cần thiết, index đó có thể bảo vệ một bất biến mà service chỉ kiểm tra bằng query sẽ không bảo vệ được trước cạnh tranh ghi.

Ví dụ MongoDB trên collection không sharded:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true }
);
~~~

Chỉ tạo index này nếu mọi order trong phạm vi đó có mã external hợp lệ, và business key thật sự duy nhất theo tenant. Nếu mã từ nhiều đối tác có thể trùng, cần thêm `providerId` hoặc namespace thích hợp.

Trong collection sharded, unique index bị ràng buộc bởi lựa chọn shard key và cấu hình; không nên suy ra uniqueness toàn cục tùy ý.

### Khi trạng thái hiệu lực quyết định tính duy nhất

Một chỗ đặt có thể được `CANCELLED` hoặc `EXPIRED`. Có thể cân nhắc partial unique index trên trạng thái đang giữ/đã bán nếu engine và topology hỗ trợ. Nhưng phải định nghĩa rõ:

- Trạng thái nào tính là còn hiệu lực?
- Một reservation hết hạn nhưng chưa được job cập nhật trạng thái có chặn booking mới không?
- `expiresAt` có thể dùng trực tiếp như điều kiện partial index động theo thời gian không?

**Thời gian hiện tại không tự biến thành điều kiện index tự cập nhật.** Nếu muốn điều kiện “giữ ghế nếu hạn giữ đã qua”, cần thao tác có điều kiện xét timestamp và trạng thái trong đường ghi, hoặc quy trình dọn dẹp/giải phóng slot rõ ràng. TTL xóa bản ghi là cơ chế vòng đời dữ liệu, không phải lời giải hoàn chỉnh cho đặt ghế nguyên tử.

## 12. Cross-aggregate workflow: Saga và trạng thái trung gian

Khi nhiều aggregate thuộc các dịch vụ/database độc lập, một transaction ACID trong một database thường không bao phủ toàn bộ quy trình. **Saga** là một mẫu phối hợp nhiều bước, trong đó mỗi bước cập nhật cục bộ và khi cần có hành động bù trừ (compensation).

Ví dụ đặt hàng:

~~~mermaid
flowchart TD
    A["Create Order: PENDING"] --> B["Reserve Stock"]
    B --> C{"Giữ đủ hàng?"}
    C -->|Không| D["Order: REJECTED"]
    C -->|Có| E["Authorize Payment"]
    E --> F{"Thanh toán được chấp nhận?"}
    F -->|Không| G["Release Stock"]
    G --> H["Order: CANCELLED"]
    F -->|Có| I["Order: CONFIRMED"]
    I --> J["Phát sự kiện giao hàng"]
~~~

Các bước có thể chạy trong những transaction cục bộ khác nhau, nhưng phải thiết kế **định danh yêu cầu, thời hạn, retry, idempotency và xử lý lỗi**.

### Compensation không phải rollback của DB

Nếu đã giữ hàng rồi thanh toán lỗi, `Release Stock` là **một thao tác nghiệp vụ mới**. Nó có thể thất bại, bị gửi lặp hoặc đến chậm. Nó không xóa quá khứ như rollback của transaction chưa commit.

Bởi vậy:

- Mỗi bước cần có trạng thái bền vững và idempotency key.
- Trả lời timeout phải phân biệt **chưa thực hiện**, **đã thực hiện**, và **không rõ kết quả**.
- Saga cần cơ chế phục hồi khi worker chết giữa các bước.
- Có thể cần dead-letter queue, đối soát hoặc công cụ can thiệp vận hành.
- Khi bù trừ không thể hoàn toàn (ví dụ email đã gửi), phải định nghĩa hành vi hợp lý thay vì giả định rollback được mọi tác động.

### Orchestration và choreography

- **Orchestration:** một thành phần điều phối theo dõi trạng thái saga và ra lệnh cho từng bước.
- **Choreography:** mỗi dịch vụ phản ứng với sự kiện rồi phát sự kiện tiếp, không nhất thiết có bộ điều phối tập trung.

Cách nào cũng cần quan sát được tiến độ. Với quy trình dài, orchestration thường giúp thấy trạng thái và timeout rõ hơn; choreography có thể giảm coupling ở một số hệ nhưng dễ khó theo dõi khi số bước tăng.

## 13. Transactional outbox: gắn thay đổi aggregate với việc phát sự kiện

Một lỗi điển hình:

~~~text
1. Lưu Order thành CONFIRMED.
2. Gửi "OrderConfirmed" lên message broker.
~~~

Nếu process chết **sau bước 1 trước bước 2**, database đã ghi đơn thành công nhưng các consumer không bao giờ nhận event.

Nếu đảo thứ tự:

~~~text
1. Gửi event.
2. Lưu Order.
~~~

Broker có thể đã nhận event nhưng thay đổi Order thất bại, khiến consumer xử lý một trạng thái chưa thật sự tồn tại.

**Transactional outbox** giải quyết khoảng hở này trong trường hợp có transaction phù hợp:

~~~text
BEGIN TRANSACTION
  update Order aggregate
  insert OutboxEvent(OrderConfirmed)
COMMIT

Background publisher:
  đọc OutboxEvent chưa gửi
  publish lên broker
  ghi nhận kết quả gửi / retry
~~~

Transaction bảo đảm **Order và outbox record** cùng được lưu hoặc cùng bị hủy trong phạm vi được hỗ trợ. Việc **đưa event lên broker** vẫn là một bước khác và thường có khả năng gửi lặp.

### Vì sao consumer phải idempotent?

Publisher có thể gửi event thành công, nhưng chết trước khi đánh dấu `published`. Khi chạy lại, nó gửi sự kiện lần nữa. Vì thế:

- Mỗi event có `eventId` ổn định.
- Consumer ghi nhận event đã xử lý hoặc bảo vệ effect bằng business key.
- Thao tác downstream phải chịu được duplicate.
- Có retry/backoff, giám sát event tồn quá lâu và cơ chế phục hồi.

**Outbox không tạo exactly-once end-to-end tự động**. Nó chủ yếu giúp tránh mất event do lỗi “đã commit DB nhưng chưa gửi broker”, kết hợp với at-least-once delivery và idempotency phía nhận.

### Nếu NoSQL chỉ hỗ trợ atomicity một item?

Có thể cân nhắc:

- Nhúng một marker/event chưa publish trong cùng aggregate item nếu kích thước và vòng đời cho phép.
- Dùng change stream/CDC để theo dõi thay đổi đã commit.
- Dùng transaction nhiều item nếu hệ DB có và giới hạn cho phép.
- Thiết kế state machine cùng cơ chế quét/đối soát để phát hiện việc chưa hoàn tất.

Mỗi phương án phải chứng minh không tạo **khoảng hở giữa thay đổi nghiệp vụ và tín hiệu cho bước tiếp theo**. Chỉ viết hai thao tác độc lập bằng code liên tiếp không đủ bảo đảm.

## 14. Read model và projection có thể tách khỏi aggregate

Một aggregate bảo vệ bất biến trong lúc ghi, còn API đọc có thể cần dữ liệu được tổng hợp từ nhiều aggregate. DDD/CQRS thường tách **write model** và **read model** theo nhu cầu.

Ví dụ trang chi tiết đơn hàng cần:

- Đơn hàng và dòng hàng.
- Tên/ảnh sản phẩm hiện tại.
- Trạng thái thanh toán.
- Vị trí vận chuyển mới nhất.
- Dòng thời gian sự kiện.

Nếu luôn đòi đọc tất cả như một snapshot nguyên tử xuyên mọi nguồn, hệ thống sẽ phức tạp và đắt. Một lựa chọn là **OrderDetailsProjection** được cập nhật theo event, kèm chính sách độ mới.

~~~text
Order aggregate ─── OrderUpdated ─┐
Payment aggregate ─ PaymentUpdated ├──> OrderDetails read model
Shipment aggregate ─ ShipmentMoved ┘
~~~

Projection có thể trễ ngắn sau lệnh ghi. Điều đó có thể chấp nhận với trang theo dõi nếu có timestamp và trạng thái cập nhật rõ ràng. Nhưng **không dùng read model trễ làm nguồn kiểm tra bất biến quan trọng** như “đã thu đủ tiền để xuất hàng” nếu yêu cầu cần xác nhận trạng thái hiện hành.

### Một câu hỏi về aggregate xuyên nhiều document

“Trang OrderDetails chứa payment và shipment, vậy có phải tất cả cùng một aggregate?” Không nhất thiết. **Read model gom nhiều nguồn để hiển thị** không thay đổi ranh giới nhất quán của các aggregate nguồn.

## 15. Phân biệt một số loại nhất quán dễ nhầm

### 15.1. Invariant nhất quán ≠ replica đọc mới nhất

Một update có điều kiện trên primary có thể bảo vệ `available >= 0`, nhưng API đọc từ replica có độ trễ có thể thấy giá trị cũ. Đó là vấn đề **read consistency/replication lag**, khác với atomicity của phép ghi.

Nếu người dùng đặt hàng xong và lập tức xem trạng thái, hệ thống cần chính sách read-after-write thích hợp; không nên dùng việc replica còn cũ làm lý do để kết luận điều kiện cập nhật trên primary thất bại.

### 15.2. Atomicity ≠ isolation cấp serializable

Một nhóm lệnh commit cùng nhau không bảo đảm mọi transaction đồng thời được sắp xếp như thực hiện từng cái một trừ khi mức isolation/semantics của hệ DB hỗ trợ và code sử dụng đúng. Cần hiểu write conflict, snapshot isolation, predicate checks và các anomaly có thể xảy ra.

Ví dụ hai bác sĩ thay ca và chỉ được phép tối đa một người rời trực: nếu hai transaction đọc cùng một snapshot rồi cập nhật **hai document khác nhau**, có thể phát sinh loại vấn đề **write skew** trong một số mức isolation. Bất biến trải trên nhiều document cần biện pháp như một điểm ghi chung/conditional guard, khóa hoặc isolation phù hợp với engine, chứ không chỉ “có transaction” là đủ trong mọi trường hợp.

### 15.3. Atomicity ≠ durability mạnh nhất

Một phép ghi có thể nguyên tử nhưng mức độ bền vững sau mất node phụ thuộc write concern/replication configuration. Ví dụ MongoDB có lựa chọn write concern; đọc/ghi theo cấu hình phù hợp là phần của thiết kế bảo đảm dữ liệu.

Trong nghiệp vụ quan trọng, nên ghi rõ:

- Lúc nào ứng dụng được trả “thành công”?
- Điều gì đã được commit, và được xác nhận ở mức nào?
- Khi client timeout nhưng lệnh có thể đã commit, sẽ kiểm tra bằng ID nào?
- Khi failover, yêu cầu độ mới và độ bền được đảm bảo ra sao?

## 16. Các dạng bất biến và cách chọn nơi thực thi

Có thể phân nhóm để thấy mối liên hệ với aggregate boundary:

| Loại bất biến | Ví dụ | Cơ chế thường cân nhắc |
|---|---|---|
| **Trong một giá trị** | Số lượng phải dương | Constructor/value object, validation |
| **Trong một aggregate** | Tổng Order bằng tổng các dòng | Domain root + atomic write/version |
| **Trong một item/document** | Stock.available không âm | Conditional atomic update |
| **Uniqueness** | Một SKU trong một tenant | Unique index/conditional claim, đúng phạm vi |
| **Qua nhiều document cùng DB** | Chuyển tiền giữa hai account | Multi-document transaction/guard phù hợp |
| **Qua nhiều aggregate** | Order chỉ CONFIRMED khi giữ được hàng | Transaction hoặc saga + trạng thái rõ ràng |
| **Qua nhiều dịch vụ** | Thanh toán và giao hàng | Saga, idempotency, outbox và đối soát |
| **Dữ liệu dẫn xuất** | Dashboard số đơn theo ngày | Projection/eventual consistency có SLA |
| **Bất biến theo thời gian** | Reservation hết hạn và được giải phóng | State machine, timeout, conditional update |

Cùng một quy tắc có thể được thực thi bằng nhiều cơ chế. Điều quan trọng là **tính đúng đắn khi có đồng thời và lỗi**, không phải gọi tên được một mẫu thiết kế.

## 17. Aggregate boundary ảnh hưởng throughput và contention

Giả sử mọi sản phẩm của một cửa hàng được lưu trong **một document lớn**:

~~~javascript
{
  _id: "inventory:tenant-a",
  items: [
    { sku: "sku-101", available: 100 },
    { sku: "sku-102", available: 250 },
    // Hàng nghìn SKU khác...
  ]
}
~~~

Lợi thế là có thể cập nhật nhiều trường của document nguyên tử. Nhưng:

- Document có thể tăng đến giới hạn kích thước.
- Các writer cập nhật nhiều SKU khác nhau vẫn có thể cùng tranh document lớn.
- Mỗi thay đổi cần quản lý phiên bản của cùng một aggregate.
- Truy vấn/tải từng SKU có thể phức tạp và tốn chi phí.
- Một tenant lớn có thể trở thành hotspot không được giải quyết chỉ bằng thêm shard.

Nếu tách thành **một document cho mỗi SKU tại mỗi kho**:

~~~javascript
{
  _id: "tenant-a:warehouse-HCM:sku-101",
  available: 100,
  reserved: 0
}
~~~

Các SKU độc lập có thể được ghi song song tốt hơn. Tuy nhiên, một lệnh giữ **nhiều SKU nguyên tử cùng lúc** giờ phải dùng transaction hoặc một quy trình đặt chỗ có trạng thái và bù trừ, tùy yêu cầu.

Đó là trade-off cốt lõi:

\[
\text{Aggregate rộng} \Rightarrow
\text{dễ giữ bất biến chung nhưng dễ tranh chấp}
\]

\[
\text{Aggregate hẹp} \Rightarrow
\text{dễ phân tán nhưng cần phối hợp nhiều aggregate}
\]

Không có kích thước aggregate tối ưu cho mọi hệ thống. Cần đo **workload ghi, xung đột, kích thước document, số key nóng và nhu cầu cập nhật đồng thời**.

## 18. Hot aggregate và giới hạn mở rộng ngang

Một SKU rất phổ biến có thể nhận hàng nghìn request giữ hàng mỗi giây. Nếu mọi thao tác phải thay đổi cùng một document có bất biến mạnh, có thể phát sinh **hot aggregate/hot item**.

Thêm node hoặc shard có thể tăng throughput toàn cụm, nhưng **không tự nhân bản khả năng ghi cạnh tranh của một item duy nhất**. Hash shard key có thể phân phối nhiều item khác nhau nhưng một item vẫn nằm ở một điểm ghi logic.

Các hướng xử lý có thể gồm:

1. **Giới hạn tốc độ nhận đặt hàng** cho SKU nóng; bảo vệ DB và giữ tính công bằng.
2. **Hàng đợi theo SKU**, xử lý tuần tự có kiểm soát, với idempotency và thời hạn chờ.
3. **Reservation pool/bucket** nếu có thể chia nguồn hàng mà vẫn bảo đảm tổng tồn và quy tắc đối soát.
4. **Preallocation** phân phối số vé/suất mua vào các bucket theo chiến lược được chứng minh.
5. **Tách lệnh đọc khỏi lệnh ghi** bằng cache đối với dữ liệu có thể cũ, trong khi update vẫn đi qua nguồn chính.
6. **Giảm write amplification**, index không cần thiết và thao tác phụ trong đường giữ hàng.

Việc chia stock thành bucket chỉ đúng nếu chứng minh được **không oversell** trên tổng bucket, xử lý cấp phát/chuyển bucket và retry. Một bộ đếm phân tán eventual consistency thông thường không tự bảo đảm bất biến tồn kho mạnh.

## 19. Aggregate root trong code: bảo vệ lệnh thay đổi trạng thái

Một ứng dụng Java có thể tổ chức lớp miền:

~~~java
public final class StockAggregate {
    private final String sku;
    private int available;
    private int reserved;

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (available < quantity) {
            throw new IllegalStateException("insufficient stock");
        }

        available -= quantity;
        reserved += quantity;
    }
}
~~~

Đây là **quy tắc nghiệp vụ trong bộ nhớ**. Nó rất có giá trị để diễn đạt bất biến, nhưng **không tự bảo vệ cạnh tranh giữa hai instance ứng dụng** cùng nạp aggregate từ database.

Nếu repository triển khai bằng cách:

~~~text
load Stock(available = 5)
reserve(4)
save Stock(available = 1)
~~~

hai tiến trình cùng làm vậy vẫn có thể tạo tình trạng đã chấp nhận hai reservation nhưng database chỉ giảm stock một lần.

Repository cần duy trì một **hợp đồng lưu aggregate an toàn đồng thời**, chẳng hạn:

- Atomic conditional update theo điều kiện tồn.
- Version check (compare-and-swap) khi ghi toàn aggregate.
- Transaction phù hợp nếu cần cập nhật thêm dữ liệu liên quan.
- Unique/index constraint để ngăn trùng danh tính/reservation.
- Idempotency khi có retry.

DDD là cách tổ chức quy tắc; **persistence adapter** phải chuyển những quy tắc đó thành bảo đảm thực tế ở storage.

## 20. Ví dụ Spring Data MongoDB: cập nhật điều kiện từ service

Một cách thực hiện trừ tồn không âm qua `MongoTemplate`:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

public final class StockRepository {
    private final MongoTemplate mongoTemplate;

    public StockRepository(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public boolean reserve(String stockId, long quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        Query query = Query.query(
            Criteria.where("_id").is(stockId)
                .and("available").gte(quantity)
        );

        Update update = new Update()
            .inc("available", -quantity)
            .inc("reserved", quantity)
            .inc("version", 1)
            .currentDate("updatedAt");

        UpdateResult result = mongoTemplate.updateFirst(
            query, update, "inventory"
        );

        return result.getMatchedCount() == 1;
    }
}
~~~

Ở đây repository cung cấp một thao tác **gắn điều kiện và update trong cùng lệnh**. Nó không phải full aggregate persistence cho mọi ứng dụng; chỉ là một operation có ràng buộc cục bộ rõ ràng.

Những điều còn cần thiết trong hệ thống thực:

- Khoanh đúng `tenantId`, SKU và warehouse; không chỉ dựa vào ID do client gửi.
- Định nghĩa xử lý document không tồn tại, trùng request và lỗi DB.
- Chọn kiểu số tương thích với BSON và xử lý tràn số.
- Nếu reservation là một thực thể có `reservationId`, bảo vệ việc tạo reservation cùng update stock theo phạm vi nguyên tử thích hợp.
- Phân biệt lỗi xung đột/không đủ hàng với lỗi hạ tầng.
- Chọn write concern và chính sách retry phù hợp với yêu cầu bền vững.

## 21. Với DynamoDB, một aggregate thường được ánh xạ như thế nào?

DynamoDB dùng **item** và primary key, gồm partition key, có thể kèm sort key. Một aggregate nhỏ có thể nằm trong một item và được bảo vệ bằng **ConditionExpression** khi `UpdateItem` hoặc `PutItem`.

Ví dụ pseudo-code:

~~~text
UpdateItem(
  Key = { PK: "STOCK#tenant-a#sku-101" },
  ConditionExpression = "available >= :quantity",
  UpdateExpression =
    "SET available = available - :quantity,
         reserved = reserved + :quantity"
)
~~~

Trong thực tế cần đảm bảo biểu thức update, giá trị tham số và việc field tồn tại theo cú pháp API được dùng. Ý tưởng chính là **check-and-update trong một item**.

Nếu một aggregate phải lưu nhiều item cùng partition key, cần xem **TransactWriteItems** nếu muốn nguyên tử giữa các item trong phạm vi dịch vụ hỗ trợ. Không thể kết luận “cùng partition nên mọi PutItem đều nguyên tử với nhau” nếu chỉ gọi nhiều API đơn lẻ.

Để tạo reservation không trùng, có thể dùng item có key duy nhất cho `reservationId` và conditional put; nếu đồng thời phải cập nhật stock item, thiết kế transaction giữa hai item hoặc cơ chế workflow có trạng thái tương ứng.

**Điểm phải nhớ:** DynamoDB không có unique index tùy ý trên mọi thuộc tính. Nếu một business key cần duy nhất khác primary key, thường phải thiết kế item claim/guard và thao tác điều kiện hoặc transaction.

## 22. Với Cassandra và Redis, đừng suy diễn từ cú pháp transaction

### Cassandra

Cassandra hỗ trợ conditional operation như `IF NOT EXISTS`/`IF` thông qua lightweight transaction (LWT) theo cơ chế và phạm vi được hỗ trợ. Nó hữu ích khi một thao tác cần compare-and-set, nhưng chi phí khác write thông thường và **không tương đương transaction ACID tùy ý xuyên nhiều partition**.

“BATCH” trong Cassandra không có cùng ý nghĩa như một SQL transaction tổng quát với isolation và rollback mọi loại thao tác. Khi dùng batch để phối hợp các hàng, cần đọc chính xác atomicity, logging và performance guarantees của kiểu batch và topology đang chạy.

### Redis

Một số thao tác Redis có thể được thực thi nguyên tử đối với key trong cùng phạm vi hỗ trợ, ví dụ script Lua trên một instance hoặc command điều kiện. Nhưng:

- Redis Cluster có các giới hạn key/slot cho thao tác nhiều key.
- Tính nguyên tử thao tác không giải quyết sự kiện gửi sang broker hoặc thay đổi trong database khác.
- Durability và failover phụ thuộc persistence/replication configuration.
- Dùng Redis làm **lock phân tán** không tự chứng minh bất biến của dữ liệu ở một storage khác sẽ không bị phá.

Không nên thiết kế aggregate dựa trên nhãn “NoSQL có atomic command” mà thiếu phân tích **phạm vi key, topology, retry và nguồn dữ liệu thực sự có thẩm quyền**.

## 23. Ranh giới aggregate với sharding và partition key

Trong NoSQL phân tán, partition/shard key có thể quyết định **dữ liệu nào được colocate** và thao tác nào cần fan-out hoặc transaction phân tán.

Ví dụ:

~~~text
PK = TENANT#tenant-a#ORDER#order-101
SK = METADATA

PK = TENANT#tenant-a#ORDER#order-101
SK = LINE#L1

PK = TENANT#tenant-a#ORDER#order-101
SK = LINE#L2
~~~

Cách này gom item của một order theo cùng partition key trong một mô hình key-value/document nhất định, thuận tiện đọc các item liên quan. Nhưng:

- **Colocation** không đồng nghĩa mặc định mọi update trên các item đều nguyên tử.
- Một aggregate quá lớn có thể tạo hot partition.
- Query nhiều aggregate có thể cần nhiều partition.
- Transaction và uniqueness có thể có giới hạn gắn với shard key.

Một lựa chọn thiết kế thường hữu ích là **định nghĩa aggregate ID và tenant ID rõ ràng**, rồi chọn partition key để phục vụ những thao tác hay xảy ra trên aggregate. Nhưng nếu một tenant có hàng triệu lệnh/giây, lấy `tenantId` làm partition key duy nhất dễ gây lệch tải.

### Chuyển aggregate giữa partition không phải việc nhỏ

Nếu shard key chứa thuộc tính có thể thay đổi, việc chuyển dữ liệu có thể phức tạp. Cần cân nhắc khóa ổn định và quy tắc migrate/rehash.

Đừng dùng một business key dễ đổi làm partition key hoặc primary key dài hạn nếu không có lý do cụ thể và kế hoạch thay đổi.

## 24. Ghi nhận lỗi và retry theo đúng ranh giới

Một thao tác trên aggregate có thể gặp:

| Tình huống | Ý nghĩa có thể xảy ra | Hướng xử lý |
|---|---|---|
| Không khớp điều kiện | Không đủ tồn hoặc version đã đổi | Trả lỗi nghiệp vụ, đọc lại khi cần |
| Duplicate key | Một định danh/reservation đã được tạo | Phân biệt retry cùng ý định với xung đột thật |
| Write conflict | Hai giao dịch/trạng thái cạnh tranh | Retry có giới hạn theo hợp đồng và xem lại state |
| Timeout trước response | Lệnh có thể chưa hoặc đã commit | Tra theo operationId/idempotency key |
| Node failover | Read/write và độ mới có thể thay đổi | Chính sách driver retry, write concern và đối soát |
| Event gửi lặp | Consumer nhận cùng event nhiều lần | Dedupe/idempotent apply |
| Saga chạy dở | Một số bước cục bộ đã hoàn thành | Resume/compensation từ trạng thái bền vững |
| Projection chậm | Read model chưa phản ánh write mới | Quan sát lag, hiển thị trạng thái phù hợp |

Tính đúng đắn cần được định nghĩa cho **từng trường hợp lỗi**, không chỉ khi happy path chạy tuần tự một lần.

### Operation ID phải sống qua retry

Nếu client gửi lại một lệnh giữ hàng sau timeout, nó phải dùng **cùng reservation/operation ID** cho ý định cũ. Nếu mỗi retry tạo ID khác, server không thể biết đó là yêu cầu lặp hay đơn đặt mới.

Ở phía server, cần bảo vệ uniqueness của operation ID và lưu kết quả/tham chiếu đã được tạo. Với request dùng cùng ID nhưng payload khác, phải có chính sách từ chối xung đột.

## 25. Các phản ví dụ thường gặp

**“Mọi dữ liệu được đọc cùng nhau đều là một aggregate.”** Một trang đọc tổng hợp có thể chứa nhiều aggregate; read model không quyết định transaction boundary.

**“Một aggregate phải luôn đúng một document.”** Đó là một cách ánh xạ tiện khi phù hợp. Aggregate là quyết định nghiệp vụ; storage có thể yêu cầu transaction nhiều document hoặc thiết kế khác.

**“Nếu transaction hỗ trợ nhiều document thì có thể bỏ aggregate.”** Transaction bảo đảm một phần tính nguyên tử kỹ thuật, không diễn đạt quy tắc trạng thái, ownership và invariant của domain.

**“Atomic update nghĩa là tồn kho luôn không âm.”** Nếu không có điều kiện `available >= quantity`, atomic update vẫn có thể ghi số âm.

**“Version ở Java đủ để tránh concurrent update.”** Version chỉ hữu ích khi được dùng trong **điều kiện ghi** và kết quả ghi được kiểm tra.

**“Unique index tự làm thao tác tạo đơn idempotent.”** Index có thể chặn trùng business key; request lặp còn cần định nghĩa trả lại kết quả, so sánh payload và vòng đời operation ID.

**“Dùng saga thì mọi bước có thể rollback như transaction.”** Compensation là hành động nghiệp vụ mới, có thể thất bại và cần retry/đối soát.

**“Một transaction lưu DB xong rồi gửi event là nguyên tử cả hai.”** External broker call nằm ngoài DB transaction trừ khi có cơ chế coordination đặc biệt. Transactional outbox thường được dùng để tránh khoảng hở này.

**“Nhúng mọi thứ vào một document sẽ nhanh nhất.”** Document lớn và nhiều writer tranh chấp có thể giảm throughput, gây hotspot hoặc chạm giới hạn kích thước.

**“Tách thành nhiều aggregate thì bắt buộc eventual consistency.”** Không tuyệt đối. Có thể dùng transaction đa item/document khi cần và được engine hỗ trợ, nhưng phải cân nhắc chi phí và ranh giới.

**“Same partition nghĩa là same transaction.”** Colocation thường giúp một số thao tác nhưng không tự biến chuỗi ghi độc lập thành một thao tác nguyên tử.

**“Đã nhận event thành công thì downstream chỉ xử lý đúng một lần.”** Broker và consumer có thể retry; cần idempotency để hiệu ứng nghiệp vụ không bị nhân đôi.

## 26. Tình huống tổng hợp: một đơn hàng chứa ba SKU

Giả sử khách đặt 2 sản phẩm A, 1 sản phẩm B, 3 sản phẩm C. Hệ thống có:

- `Order` là aggregate quản lý dòng hàng, tổng tiền và trạng thái.
- `Stock(A)`, `Stock(B)`, `Stock(C)` là ba aggregate quản lý tồn riêng.
- `Payment` là aggregate khác hoặc một dịch vụ ngoài.

Yêu cầu: **không xác nhận đơn nếu không giữ đủ cả ba SKU**.

### Phương án A — Transaction bao trùm dữ liệu cùng hệ lưu trữ

Nếu ba stock document và order cùng nằm trong phạm vi transaction được DB hỗ trợ, có thể:

~~~text
BEGIN TRANSACTION
  Giữ 2 A bằng conditional update
  Giữ 1 B bằng conditional update
  Giữ 3 C bằng conditional update
  Cập nhật Order thành CONFIRMED
COMMIT
~~~

Nếu một SKU không đủ, hủy transaction. Các stock update và order update không commit một phần.

Ưu điểm là quy tắc được bảo vệ chặt trong một transaction; đánh đổi là transaction tranh tài nguyên nhiều aggregate, thời gian commit, conflict và chi phí tăng. Nếu có gọi cổng thanh toán ngoài, transaction DB **không bao phủ** cổng thanh toán đó.

### Phương án B — Reservation workflow

~~~text
Order: PENDING_STOCK
   |
   +--> Reserve A (reservationId = order-101:A)
   +--> Reserve B (reservationId = order-101:B)
   +--> Reserve C (reservationId = order-101:C)
   |
   +--> Nếu tất cả thành công:
   |      Order: STOCK_RESERVED
   |
   +--> Nếu bất kỳ bước nào thất bại:
          Release các reservation đã tạo
          Order: REJECTED
~~~

Ưu điểm: mỗi stock aggregate độc lập, các bước có thể điều phối giữa nhiều hệ. Đánh đổi: hệ thống tồn tại trạng thái trung gian và cần logic bù trừ khi một bước thất bại.

Nếu áp dụng phương án B, không được hiển thị `CONFIRMED` cho khách trước khi đạt điều kiện nghiệp vụ xác nhận. Phải định nghĩa khi nào một reservation hết hạn, xử lý lỗi bù trừ và phục hồi saga sau khi worker restart.

### Phương án C — Một aggregate sản phẩm/kho cực rộng

Nhúng mọi tồn kho vào một document lớn để trừ cùng lúc có thể đơn giản về atomicity, nhưng tạo hotspot và khó scale. Phương án này chỉ hợp lý khi quy mô và nhu cầu truy cập thực sự phù hợp, không nên xem là giải pháp mặc định.

## 27. Bài tập tự suy luận

### Bài tập 1 — Tổng tiền đơn hàng

`Order` có mảng `lines[]` và `totalMinor`. Hai request đồng thời: một request thêm dòng hàng, request kia áp giảm giá.

**Câu hỏi:** nếu cả hai request đọc version 7 rồi ghi toàn bộ document mà không kiểm tra version, có thể xảy ra gì? Cách bảo vệ nào phù hợp?

**Hướng suy luận:** một request có thể ghi đè thay đổi của request khác, làm tổng và giảm giá không khớp. Domain root kiểm tra invariant khi tính toán, còn storage cần optimistic version check, conditional update hoặc thao tác nguyên tử thích hợp.

### Bài tập 2 — Một ghế, hai khách

Hai khách cùng đặt ghế A12 trong một suất chiếu. Mỗi request query “còn ghế không?” rồi insert booking.

**Câu hỏi:** chỉ dùng transaction cho riêng thao tác insert booking đã đủ chưa nếu không có unique/conditional guard?

**Hướng suy luận:** chưa chắc. Cần ngăn hai booking hiệu lực cho cùng slot bằng khóa/constraint hoặc một item trạng thái được cập nhật có điều kiện trong phạm vi atomicity phù hợp. Đọc “còn trống” trước không bảo vệ race condition.

### Bài tập 3 — Chuyển khoản

Chuyển 50.000 từ A sang B, nhưng A và B nằm ở hai document. Sau khi trừ A, ứng dụng crash.

**Câu hỏi:** lỗi gì xảy ra nếu không có transaction hoặc quy trình bù trừ/đối soát? Làm sao giải?

**Hướng suy luận:** có trạng thái chuyển tiền hoàn tất một phần. Nếu cùng DB có transaction thích hợp, dùng transaction; nếu qua hệ độc lập, cần mô hình sổ cái/quy trình chuyển tiền với trạng thái bền vững, idempotency và đối soát, không tự giả định hai thao tác độc lập tương đương atomic.

### Bài tập 4 — Email xác nhận

Order đã CONFIRMED, nhưng không có email xác nhận do worker chết giữa ghi DB và gửi message.

**Câu hỏi:** outbox giúp chặn khoảng hở nào? Vì sao consumer còn phải idempotent?

**Hướng suy luận:** ghi Order và bản ghi event trong cùng transaction giúp có dấu vết cần publish sau commit. Publisher có thể gửi lặp khi retry, nên consumer phải chống xử lý hai lần.

### Bài tập 5 — Mở rộng kho

Một tenant có 100.000 SKU. Mọi SKU được nhúng trong một document `inventory:tenant-a` để cập nhật nguyên tử.

**Câu hỏi:** thiết kế này có phù hợp khi 1.000 yêu cầu/giây cập nhật nhiều SKU độc lập không?

**Hướng suy luận:** có nguy cơ document vượt giới hạn và contention lớn. Có thể tách aggregate theo SKU/kho rồi dùng transaction hoặc reservation workflow cho lệnh nhiều SKU.

### Bài tập 6 — Idempotency

Client gửi `reserve(2, id=req-55)`. Server đã giữ thành công nhưng client timeout và gửi lại cùng ID.

**Câu hỏi:** chỉ có điều kiện `available >= 2` có ngăn giữ hai lần không?

**Hướng suy luận:** không. Cần cơ chế ghi nhận rằng `req-55` đã được áp dụng, cùng kết quả hoặc trạng thái đã xác định; thao tác retry không được tạo thêm effect. Điều kiện chống âm và idempotency là hai lớp khác nhau.

## 28. Quy trình lựa chọn aggregate boundary theo bất biến và storage

Khi thiết kế một thực thể NoSQL, nên đi theo thứ tự sau:

1. **Viết bất biến bằng câu rõ ràng.** “Không được có hai booking hiệu lực cho cùng ghế”, “available không âm”, “total bằng tổng dòng hàng”.
2. **Xác định trạng thái mà bất biến liên quan.** Một field, nhiều field trong một entity, nhiều entity, nhiều aggregate hay nhiều hệ thống?
3. **Xác định thời điểm phải đúng.** Ngay sau mỗi lệnh ghi hay có thể trong một khoảng chấp nhận được?
4. **Chọn aggregate root và các lệnh nghiệp vụ.** Lệnh nào được phép tạo/chuyển trạng thái? Ai sở hữu bất biến?
5. **Đối chiếu với phạm vi atomicity của DB.** Một document/item, conditional write, unique constraint, multi-document transaction hay chỉ eventual workflow?
6. **Chọn cách lưu dữ liệu.** Embed khi dữ liệu nhỏ và cùng vòng đời; reference/tách item khi cần phân tán hoặc truy cập độc lập.
7. **Thiết kế concurrency control.** Atomic predicate, version, transaction conflict, uniqueness, idempotency.
8. **Thiết kế liên aggregate.** Transaction nếu cần và khả thi; saga/outbox/event nếu quy trình cần nhiều bước hoặc nhiều hệ.
9. **Thiết kế failure handling.** Timeout, unknown commit, retry, duplicate, compensation, data repair.
10. **Đo giới hạn thực tế.** Throughput, hot aggregate, contention, latency, transaction cost, document size và khả năng recovery.

Một bản ghi quyết định thiết kế có thể như sau:

~~~yaml
aggregate: Stock
root: StockItem
identity: [tenantId, warehouseId, sku]
invariants:
  - "available >= 0"
  - "reserved >= 0"
commands:
  - reserve(quantity, reservationId)
  - release(reservationId)
storage:
  unit: "one document per tenant + warehouse + SKU"
  atomicity: "conditional single-document write"
concurrency:
  guard: "available >= quantity"
  versionField: version
idempotency:
  key: reservationId
  policy: "duplicate request returns existing reservation result"
crossAggregate:
  orderIntegration: "reservation workflow"
  completion: "Order confirmed only after all stock holds succeed"
observability:
  - insufficientStockRate
  - duplicateReservationCount
  - pendingReservationAge
~~~

Đây là **hợp đồng thiết kế minh họa**, không phải cấu hình mà MongoDB hoặc một framework tự động thực thi. Đặc biệt, mục `idempotency` chỉ trở thành bảo đảm khi được triển khai bằng dữ liệu và thao tác nguyên tử phù hợp.

## 29. Kết nối tư duy DDD và NoSQL

Có thể ghi nhớ mối quan hệ bằng sơ đồ:

~~~mermaid
flowchart TD
    A["Bất biến nghiệp vụ cần bảo vệ"] --> B["Ranh giới aggregate"]
    B --> C["Lệnh thông qua aggregate root"]
    C --> D{"Bất biến thuộc phạm vi nào?"}
    D -->|"Một document/item"| E["Atomic/conditional update + version"]
    D -->|"Nhiều document cùng DB"| F["Transaction/guard theo engine"]
    D -->|"Nhiều aggregate hoặc dịch vụ"| G["Workflow/saga + outbox + idempotency"]
    E --> H["Xử lý concurrent requests và retry"]
    F --> H
    G --> H
    H --> I["Kiểm chứng invariant dưới lỗi và tải đồng thời"]
~~~

**Aggregate trả lời “điều gì phải nhất quán cùng nhau theo nghiệp vụ?”; storage atomicity trả lời “cơ sở dữ liệu có thể thực thi thay đổi nguyên tử ở phạm vi nào?”.** Khi hai ranh giới phù hợp, một cập nhật có thể vừa đơn giản vừa an toàn. Khi chúng không khớp, kiến trúc phải chọn transaction, thay đổi mô hình lưu trữ hoặc thiết kế một quy trình có trạng thái và bù trừ. Sự lựa chọn đúng dựa trên bất biến, khả năng đồng thời và hành vi khi có lỗi; đó là nền tảng để dùng NoSQL linh hoạt mà vẫn giữ dữ liệu đáng tin cậy.
