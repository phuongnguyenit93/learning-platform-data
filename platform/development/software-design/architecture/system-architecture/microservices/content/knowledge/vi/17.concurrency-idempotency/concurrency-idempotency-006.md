# Cạnh tranh tài nguyên trong đặt hàng, tồn kho và thanh toán

## Mục tiêu bài học

Trong hệ thống thương mại điện tử và Microservices, nhiều yêu cầu thường cùng thao tác lên một tập dữ liệu hữu hạn: hai khách mua sản phẩm cuối cùng, người dùng nhấn thanh toán hai lần, hai worker cùng xử lý một sự kiện, hoặc yêu cầu hủy đơn chạy đồng thời với xác nhận thanh toán. Những request riêng lẻ có thể đều hợp lệ, nhưng **thứ tự xen kẽ giữa chúng** lại làm phát sinh lỗi nghiệp vụ.

Đây là nhóm vấn đề về **concurrency, race condition, atomicity và idempotency**. Để hệ thống đáng tin cậy, không đủ chỉ kiểm tra các endpoint khi chạy tuần tự. Cần bảo vệ những bất biến nghiệp vụ quan trọng ngay tại nơi sở hữu dữ liệu, đồng thời chuẩn bị cho retry, timeout, trùng thông điệp và phản hồi đến muộn giữa các dịch vụ.

Bài này tập trung vào ba tài nguyên liên quan chặt chẽ:

- **Đơn hàng (Order):** một ý định đặt hàng không tạo hai đơn; trạng thái không bị chuyển ngược ngoài quy tắc.
- **Tồn kho (Inventory):** không oversell do hai người cùng giữ số lượng cuối; không trừ hoặc hoàn tồn hai lần.
- **Thanh toán (Payment):** một payment intent không authorize/capture/refund nhiều lần ngoài quy tắc; kết quả UNKNOWN phải được xác minh.

Sau bài học, bạn có thể:
1. Nhận diện race condition bằng timeline và business invariant.
2. Phân biệt read-modify-write không an toàn với conditional atomic update.
3. Chọn optimistic locking, pessimistic locking, unique constraint và serialization phù hợp.
4. Thiết kế reservation, expiration, release và payment state machine idempotent.
5. Kết hợp local transaction với Saga, outbox, inbox và reconciliation trong Microservices.
6. Xây test concurrency có kiểm soát, fault injection và observability cho các luồng quan trọng.

## 1. Race condition là gì?

Race condition xảy ra khi kết quả phụ thuộc vào thứ tự/timing của các thao tác đồng thời, trong khi hệ thống không kiểm soát được thứ tự đó theo các invariant cần bảo vệ.

Ví dụ stock còn 1:

~~~text
Thời điểm        Khách A                     Khách B
-------------------------------------------------------------
t0               Đọc stock = 1
t1                                           Đọc stock = 1
t2               Kiểm tra 1 >= 1: OK
t3                                           Kiểm tra 1 >= 1: OK
t4               Tạo reservation A
t5                                           Tạo reservation B
t6               Ghi stock = 0
t7                                           Ghi stock = 0
-------------------------------------------------------------
Kết quả: hai người được hứa cùng một đơn vị hàng cuối.
~~~

Vấn đề không nằm ở việc đọc giá trị 1 là sai; mỗi request có thể đọc đúng tại thời điểm đó. Vấn đề là phép **kiểm tra điều kiện rồi thay đổi trạng thái** không được thực hiện thành một hành động nguyên tử.

Mã giả có lỗi:

~~~java
Stock stock = repository.findBySku(sku);
if (stock.available() >= quantity) {
    stock.setAvailable(stock.available() - quantity);
    repository.save(stock);
    return RESERVED;
}
return OUT_OF_STOCK;
~~~

Nếu hai request cùng đọc một phiên bản, cả hai có thể vượt qua điều kiện. Tùy ORM/isolation, lỗi có thể là mất cập nhật (lost update), cấp phát quá số lượng thực hoặc reservation trùng.

### 1.1. Những kiểu lỗi thường gặp

| Lỗi | Mô tả | Ví dụ |
| --- | --- | --- |
| Lost update | Ghi của request sau đè lên ghi của request trước | Hai lệnh cập nhật số lượng từ cùng stock cũ |
| Check-then-act race | Kiểm tra và hành động bị chen ngang | Hai checkout cùng thấy còn hàng |
| Duplicate side effect | Cùng ý định bị thực hiện nhiều lần | Hai payment captures |
| Write skew | Hai giao dịch cập nhật các hàng khác nhau dựa trên cùng điều kiện tổng thể | Mỗi worker giữ một phần capacity làm vượt constraint chung |
| TOCTOU | Điều kiện đúng lúc kiểm tra, không còn đúng lúc sử dụng | Giá, quota hoặc trạng thái đơn đã đổi |
| Stale event | Thông điệp cũ tác động lên trạng thái mới | Cancel event đến sau Confirm |
| Double release | Compensation/release được áp dụng hai lần | Cộng lại stock hai lần |
| Concurrent transition | Hai state changes cạnh tranh | CancelOrder và ConfirmOrder |
| Deadlock | Nhiều transaction khóa tài nguyên theo thứ tự trái nhau | Checkout giỏ nhiều SKU |
| Hot row contention | Nhiều request cùng tranh một dòng | SKU bán chạy, bộ đếm tồn kho |

Các lỗi trên có thể xảy ra ngay trong một service với một DB, và cũng có thể xuất hiện xuyên nhiều services khi message/network không bảo đảm chỉ gửi một lần.

## 2. Bắt đầu bằng business invariant

Không nên chọn công nghệ lock trước khi xác định điều gì **không được phép sai**.

Ví dụ:

**Đặt hàng**
- Một checkout intent chỉ tạo tối đa một Order.
- Order CONFIRMED phải có bằng chứng đủ điều kiện nghiệp vụ.
- Order CANCELLED không được tự động chuyển thành CONFIRMED bởi callback cũ.

**Tồn kho**
- Available quantity không âm đối với hàng có kiểm soát stock.
- Tổng reservations hiệu lực không vượt nguồn inventory có thể cấp phát theo mô hình đã định.
- Một reservation business key không được giữ cùng stock hai lần.
- Release một reservation chỉ tăng lại available tối đa một lần.

**Thanh toán**
- Một business payment intent không capture tiền hai lần do retry.
- Amount/currency/merchant reference của cùng idempotency key phải giữ nguyên.
- Refund không được vượt phần tiền đã capture trừ khi có quy tắc tài chính xác định.
- Chỉ có trạng thái final khi có bằng chứng từ nguồn có thẩm quyền.

Từ invariant, xác định nơi thực thi:
- Có thể kiểm tra/ghi atomically trong một local DB transaction không?
- Có cần unique constraint, row lock hoặc state transition guard?
- Invariant có trải nhiều service không và có thể tạm thời chưa đồng bộ không?
- Có thể dùng reservation, compensation và reconciliation để hội tụ không?
- Nếu không cho phép trạng thái trung gian, có cần giữ khả năng nghiệp vụ trong cùng bounded context không?

### 2.1. Không tin phép kiểm tra tại client

Mobile/Web có thể hiển thị “còn 1 sản phẩm” lúc 10:00:00, nhưng đến lúc nhấn Đặt hàng ở 10:00:05 stock đã thay đổi. Client UI chỉ là thông tin tham khảo; xác nhận stock phải thực hiện ở Inventory owner bằng thao tác concurrency-safe.

Tương tự, việc ẩn nút Thanh toán sau một lần click giúp UX nhưng **không phải** biện pháp chống double charge ở backend. Người dùng có thể refresh, mở hai tab, mạng tự retry, proxy phát lại hoặc callback tới nhiều lần.

## 3. Các lớp cần bảo vệ đồng thời

~~~text
Client / UI
   |   Disable duplicate click, stable checkout ID
   v
API Gateway / BFF
   |   Auth, quotas, deadline, correlation ID
   v
Order Service
   |   Unique checkout key, guarded Order state
   v
Inventory Service
   |   Atomic stock update + unique reservation
   v
Payment Service
   |   Unique payment intent + PSP idempotency
   v
External Payment Provider
       Merchant reference, status inquiry, webhook
~~~

Từng lớp giải quyết phần khác nhau:

- UI giảm các hành động trùng do người dùng.
- Gateway hạn chế tải, nhưng không thể biết mọi side effect đã commit hay chưa.
- Order chịu trách nhiệm identity và lifecycle của đơn.
- Inventory là nguồn có thẩm quyền về số lượng có thể cấp.
- Payment chịu trách nhiệm tiền, reference và đối soát PSP.
- Database bảo vệ transaction/unique constraints cục bộ.
- Workflow coordinator/Saga kết nối trạng thái giữa các owner.

Không đẩy toàn bộ concurrency protection lên gateway hoặc client. **Nguồn sở hữu invariant** phải có cách bảo vệ nó ngay cả khi request đi tới bằng đường khác.

## 4. Overselling: hai người cùng mua đơn vị hàng cuối

Xét SKU-100 có available=1. Hai request A/B đồng thời đặt quantity=1. Code sau không an toàn:

~~~sql
SELECT available
FROM inventory
WHERE sku = 'SKU-100';

-- Cả A và B đều đọc available = 1.

UPDATE inventory
SET available = 0
WHERE sku = 'SKU-100';
~~~

Điều kiện stock không được gắn vào UPDATE, nên hai request có thể cùng được ứng dụng ghi nhận thành công.

### 4.1. Atomic conditional update

Một cách đơn giản là để database kiểm tra điều kiện và thay đổi trong **một câu UPDATE nguyên tử**:

~~~sql
UPDATE inventory
SET available = available - :quantity,
    reserved = reserved + :quantity,
    version = version + 1
WHERE sku = :sku
  AND available >= :quantity;
~~~

Sau đó kiểm tra affected rows:
- 1 row: update đã thỏa điều kiện, có thể tiếp tục ghi reservation trong cùng transaction.
- 0 rows: không còn đủ hàng hoặc SKU không tồn tại; phân loại bằng truy vấn/contract phù hợp.
- Không coi request đã reserve thành công nếu transaction chứa UPDATE sau đó rollback.

Phương pháp này dùng atomic write và ràng buộc điều kiện tại database, nên hai request tranh stock=1 không thể **đều** giảm available xuống -1 bằng câu UPDATE này khi database thực thi row updates theo semantics thông thường.

### 4.2. Không tách stock update và reservation insert thành hai transaction

Sai:

~~~text
Transaction 1:
  UPDATE inventory stock -= quantity
  COMMIT

Transaction 2:
  INSERT reservation
  (lỗi unique constraint)
  ROLLBACK
~~~

Khi reservation insert thất bại, stock đã bị trừ và không có record theo dõi để release.

Đúng về nguyên tắc:

~~~text
BEGIN local transaction
  Atomic conditional stock decrement
  INSERT unique Reservation(orderId, sku, purpose)
  INSERT Outbox(InventoryReserved), nếu cần
COMMIT
~~~

Nếu insert reservation lỗi và transaction rollback, stock decrement cũng rollback. Đây là ví dụ local ACID xử lý đúng một invariant thuộc Inventory service.

### 4.3. SQL constraint làm tuyến phòng thủ cuối

Có thể bổ sung:

~~~sql
ALTER TABLE inventory
ADD CONSTRAINT chk_inventory_available_nonnegative
CHECK (available >= 0);
~~~

CHECK constraint giúp ngăn available âm ngay cả nếu một code path có lỗi. Nhưng nó không ngăn **hai reservation trùng** nếu stock vẫn không âm do lost update. Cần cả unique business key và atomic transition.

Cũng cần xác định đơn vị của số lượng: item, gram, package hay serial number; không dùng kiểu số thực thiếu kiểm soát cho quantity đòi độ chính xác.

## 5. Reservation model thay vì trừ stock không dấu vết

Một mô hình tồn kho thường có:
- on_hand: số lượng vật lý theo nguồn có thẩm quyền.
- reserved: số lượng đã giữ cho các intent còn hiệu lực.
- available: số lượng có thể hứa cho yêu cầu mới.
- allocated/shipped: số lượng đã cấp phát/giao theo workflow.

Quan hệ cụ thể tùy domain. Ví dụ nếu dùng available = on_hand - reserved - other_holds, mọi thay đổi phải giữ invariant theo schema đã chọn. Không vừa ghi available thủ công vừa tái tính sai từ reserved.

Bảng minh họa:

~~~sql
CREATE TABLE inventory (
    sku VARCHAR(100) PRIMARY KEY,
    available BIGINT NOT NULL CHECK (available >= 0),
    reserved BIGINT NOT NULL CHECK (reserved >= 0),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE reservations (
    reservation_id VARCHAR(120) PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    order_id VARCHAR(120) NOT NULL,
    sku VARCHAR(100) NOT NULL,
    purpose VARCHAR(50) NOT NULL,
    quantity BIGINT NOT NULL CHECK (quantity > 0),
    status VARCHAR(30) NOT NULL,
    expires_at TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,
    UNIQUE (tenant_id, order_id, sku, purpose)
);
~~~

Unique constraint minh họa: nếu một order được phép có nhiều line items cùng SKU hoặc nhiều fulfillment attempts, phải chọn business key phù hợp thay vì máy móc dùng orderId+sku.

### 5.1. Trạng thái reservation

~~~text
REQUESTED
    |
    +--> RESERVED ------> CONFIRMED/ALLOCATED
    |        |
    |        +----------> RELEASED
    |        |
    |        +----------> EXPIRED
    |
    +--> REJECTED
~~~

Không phải mọi business đều cần REQUESTED; nhiều trường hợp có thể quyết định RESERVED/REJECTED trong cùng local transaction. Quan trọng là transition có guard và chỉ một đường được phép đổi reserved quantity.

### 5.2. Release phải idempotent

Một release unsafe:

~~~java
inventory.setAvailable(
    inventory.available() + reservation.quantity());
reservation.setStatus(RELEASED);
~~~

Nếu hai release requests cùng đọc status=RESERVED và đều thực hiện phép cộng, available có thể tăng hai lần.

Cần một transaction với **chuyển trạng thái điều kiện**:

~~~sql
UPDATE reservations
SET status = 'RELEASED',
    version = version + 1
WHERE reservation_id = :id
  AND status = 'RESERVED';
~~~

Chỉ khi affected rows=1 mới cập nhật available/reserved tương ứng trong **cùng local transaction**:

~~~sql
UPDATE inventory
SET available = available + :quantity,
    reserved = reserved - :quantity,
    version = version + 1
WHERE sku = :sku
  AND reserved >= :quantity;
~~~

Nếu status đã RELEASED, trả kết quả idempotent/no-op. Nếu status là CONFIRMED, EXPIRED hay không tồn tại, không được tự cộng stock; xử lý đúng state machine.

### 5.3. Release và confirm cạnh tranh

Một worker hết hạn reservation gọi EXPIRE, trong khi Order vừa nhận PaymentAuthorized và muốn CONFIRM.

~~~text
Worker A: EXPIRE Reservation R
Worker B: CONFIRM Reservation R
~~~

Nếu cả hai chỉ đọc status=RESERVED rồi ghi không có guard, có thể vừa hoàn stock vừa ghi Order CONFIRMED.

Cần mô hình chuyển trạng thái quyết định duy nhất, ví dụ:

~~~sql
UPDATE reservations
SET status = 'CONFIRMED',
    version = version + 1
WHERE reservation_id = :id
  AND status = 'RESERVED'
  AND expires_at > CURRENT_TIMESTAMP;
~~~

hoặc EXPIRE từ RESERVED theo điều kiện thời gian. Thao tác thắng là thao tác thực hiện state transition hợp lệ trước theo transaction isolation đã chọn. Thao tác thua phải đọc trạng thái thật và thực hiện nhánh bù trừ/reconciliation nếu cần.

Không dùng clock của hai application nodes làm nguồn quyết định duy nhất cho một timeout cạnh tranh; xác định time authority và semantics expiration rõ.

## 6. Giỏ nhiều SKU và deadlock

Một order có SKU-A và SKU-B; hai transaction có thứ tự khóa trái nhau:

~~~text
Transaction A:
  Lock SKU-A
  Wait SKU-B

Transaction B:
  Lock SKU-B
  Wait SKU-A

=> Deadlock
~~~

Các hướng giảm rủi ro:
- Sắp xếp SKUs theo thứ tự xác định trước khi cập nhật.
- Giữ transaction ngắn, không gọi PSP khi đang giữ row locks.
- Có giới hạn thời gian chờ khóa.
- Bắt và retry **toàn bộ local transaction** khi DB trả deadlock/serialization failure, với budget phù hợp.
- Tránh khóa nhiều records không cần thiết.
- Nếu reservation trải nhiều warehouses/owners, đánh giá transaction boundary và compensation.

### 6.1. Đơn nhiều SKU phải all-or-nothing hay partial?

Đây là business decision:
- Nếu Order yêu cầu đủ tất cả items mới được accept, có thể reserve nhiều dòng trong cùng Inventory DB transaction nếu chúng ở cùng ownership boundary.
- Nếu chia nhiều kho độc lập, toàn bộ reservation có thể cần Saga/compensation.
- Nếu cho partial fulfillment, từng line cần state riêng và API phải phản ánh partial outcome.

Không “cố rollback bằng HTTP” một reservation ở service khác và coi đó là local ACID. Compensation có thể thất bại và phải theo dõi.

## 7. Optimistic locking: phiên bản dữ liệu chống lost update

Optimistic locking phù hợp khi xung đột tương đối hiếm và chi phí retry chấp nhận được.

Ví dụ một bảng orders có version. Hai request cùng đọc version=5:

~~~text
Request A reads status=PENDING, version=5
Request B reads status=PENDING, version=5

A updates status=CONFIRMED if version=5
A succeeds, version becomes 6

B updates status=CANCELLED if version=5
B affects 0 rows (conflict)
~~~

SQL:

~~~sql
UPDATE orders
SET status = :new_status,
    version = version + 1
WHERE id = :order_id
  AND version = :expected_version
  AND status = :expected_status;
~~~

Affected rows=0 nghĩa là precondition không còn đúng hoặc row không tồn tại; service phải đọc lại state và quyết định, không tự retry mù mọi transition.

Trong JPA:

~~~java
@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private String id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @Version
    private long version;
}
~~~

Nếu entity được load/updated trong một transaction theo cách JPA hỗ trợ optimistic locking, @Version giúp phát hiện conflict khi flush/commit. Nhưng cần phân biệt exception này với business rejection và retry đúng cả transaction nếu phù hợp.

### 7.1. Optimistic locking không tự chống double charge

Nếu hai threads có cùng Payment, mỗi thread gọi PSP trước rồi mới lưu version, cả hai có thể đã tạo side effect. Một version conflict ở database sau PSP call không rollback được PSP.

**Thứ tự đúng:** claim/payment intent có identity ổn định và bảo vệ bằng local transaction trước khi gửi PSP, sau đó query/reconcile provider nếu kết quả mơ hồ.

## 8. Pessimistic locking: khóa trước khi thay đổi

Pessimistic locking phù hợp khi cần bảo vệ nhiều thao tác cục bộ dưới contention hoặc conflict rất đắt.

~~~sql
BEGIN;

SELECT available
FROM inventory
WHERE sku = :sku
FOR UPDATE;

-- Kiểm tra điều kiện và ghi reservation/stock trong cùng transaction.

COMMIT;
~~~

FOR UPDATE thường khóa row cho đến commit/rollback trong nhiều relational DB, nhưng syntax, lock scope, isolation và timeout phụ thuộc engine.

Ưu điểm:
- Serialize các thao tác cạnh tranh trên cùng row theo cơ chế DB.
- Dễ bảo vệ một chuỗi local checks/updates nếu thiết kế đúng.

Nhược điểm:
- Wait/lock contention tăng khi một SKU hot.
- Deadlock khi khóa nhiều rows sai thứ tự.
- Giữ transaction dài ảnh hưởng throughput.
- Không thể kéo khóa database qua PSP/network để tạo distributed ACID.

### 8.1. Chọn optimistic, pessimistic hay atomic SQL?

| Tình huống | Lựa chọn thường hợp lý |
| --- | --- |
| Một bộ đếm available giảm có điều kiện | Atomic conditional UPDATE |
| Entity có nhiều thay đổi, xung đột ít | Optimistic locking/version |
| Nhiều local rows cần kiểm tra cùng transaction | Row locks theo thứ tự hoặc isolation phù hợp |
| SKU rất hot | Cân nhắc contention, partition/bucket, queue/serialization |
| Command có side effect ngoài DB | Durable intent + idempotency + reconciliation |
| Unique business intent | Unique constraint/atomic claim |
| State transition | Conditional UPDATE + version/status guard |

Không có một kiểu lock tối ưu cho mọi endpoint. Ưu tiên invariant đơn giản được diễn đạt trực tiếp trong database; đo contention và deadlock trước khi thêm cơ chế phức tạp.

## 9. Transaction isolation không phải “cứ SERIALIZABLE là xong”

Các isolation levels có thể cho phép những anomaly khác nhau, tùy database engine. READ COMMITTED có thể phù hợp với conditional atomic update; REPEATABLE READ không nhất thiết loại bỏ mọi write skew; SERIALIZABLE thường cung cấp mức isolation mạnh nhất trong phạm vi DB nhưng có thể abort/retry transactions.

Một ví dụ write skew: hai nhân viên trực tổng đài; quy tắc luôn phải có ít nhất một người trực. Hai transaction cùng thấy có hai người trực rồi mỗi người tự tắt trạng thái của mình ở hai rows khác nhau. Nếu không bảo vệ predicate invariant bằng isolation/constraint/locking phù hợp, kết quả có thể không còn ai trực.

Trong thương mại điện tử, những invariant tổng thể như “tổng reserved across buckets không vượt toàn bộ capacity” cũng cần thiết kế concurrency đúng; chỉ atomic UPDATE một bucket chưa chắc bảo vệ tổng nếu có nhiều buckets.

Dù dùng SERIALIZABLE trong Inventory DB, nó **không bao phủ Payments DB, broker hoặc PSP**. Isolation của local transaction không thay Saga/reconciliation cho giao dịch phân tán.

## 10. Đặt hàng: một checkout intent không tạo hai Order

Trường hợp thường gặp:
1. User nhấn nút Đặt hàng.
2. Request gửi tới Order Service.
3. Order đã commit nhưng response mất.
4. User nhấn lần nữa.
5. Client tạo request mới.

Nếu Order Service tạo ID ngẫu nhiên ở mọi POST mà không nhận diện checkout intent, có thể tạo hai Order cho cùng một giỏ.

Giải pháp là **stable checkout/idempotency key**:

~~~http
POST /orders
Idempotency-Key: checkout-cart-471-submit-v1
Content-Type: application/json

{
  "cartId": "cart-471",
  "shippingAddressId": "addr-91"
}
~~~

Server scope key theo tenant/user hoặc account ownership và operation type, so fingerprint của payload, rồi atomically claim.

### 10.1. Bảng operation idempotency

~~~sql
CREATE TABLE api_operations (
    tenant_id VARCHAR(80) NOT NULL,
    operation_type VARCHAR(80) NOT NULL,
    idempotency_key VARCHAR(180) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(30) NOT NULL,
    resource_id VARCHAR(120),
    result_json TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation_type, idempotency_key)
);
~~~

Luồng local:
- Claim key bằng INSERT có unique constraint.
- Kiểm tra fingerprint khi key tồn tại.
- Nếu operation đã SUCCEEDED, trả lại Order ID cũ.
- Nếu PENDING, trả operation status; không tạo Order mới.
- Nếu cùng key nhưng payload khác, trả conflict.
- Khi tạo Order, record operation và Order có thể được ghi cùng transaction nếu cùng DB.

### 10.2. Không chỉ check existence

Sai:

~~~java
if (!operationRepository.existsByKey(key)) {
    createNewOrder();
    operationRepository.save(key);
}
~~~

Hai threads có thể cùng kiểm tra và đều thấy chưa có key. Phải có constraint/atomic insert ở DB và xử lý conflict đúng.

### 10.3. Một key dùng cho một ý định, không phải mọi lần gửi

Nếu checkout intent giống nhau và cần retry, dùng cùng key. Nếu người dùng chủ động tạo một đơn hàng mới khác, dùng operation identity khác. Đừng tái sử dụng cùng key với payload khác hoặc scope không rõ.

Idempotency key không phải mật khẩu và không thay authorization. Biết một key của người khác không được cho phép truy vấn/nhận Order của tenant khác.

## 11. Đơn hàng có state machine, không chỉ cột status tùy ý

Một state machine minh họa:

~~~text
CREATED
   |
   v
PENDING_INVENTORY
   |
   +------------------------> CANCELLED
   |
   v
PENDING_PAYMENT
   |
   +----------> CANCELLING ---> CANCELLED
   |
   v
CONFIRMED
   |
   v
FULFILLING ---> SHIPPED

PENDING_PAYMENT --timeout--> NEEDS_RECONCILIATION
~~~

Các điều kiện:
- CONFIRMED chỉ sau khi có bằng chứng inventory và payment theo business contract.
- CANCELLED không tự trở về PENDING_PAYMENT chỉ do một event cũ.
- Nếu PaymentAuthorized đến sau Cancel, cần policy void/refund/reconcile.
- SHIPPED không được hủy như một đơn chưa đóng gói; có thể tạo return workflow.
- Trạng thái UNKNOWN/RECONCILING phải được theo dõi và có owner.

### 11.1. Cancel vs confirm race

~~~text
Thread A: PaymentAuthorized → ConfirmOrder
Thread B: User cancels      → CancelOrder
~~~

Cả hai đọc Order=PENDING_PAYMENT. Nếu code chỉ set status rồi save, transition cuối cùng có thể thắng một cách không kiểm soát.

SQL guarded transitions:

~~~sql
UPDATE orders
SET status = 'CONFIRMED', version = version + 1
WHERE id = :id
  AND status = 'PENDING_PAYMENT'
  AND version = :expected_version;
~~~

~~~sql
UPDATE orders
SET status = 'CANCELLING', version = version + 1
WHERE id = :id
  AND status IN ('PENDING_INVENTORY','PENDING_PAYMENT')
  AND version = :expected_version;
~~~

Chỉ transition có affected rows=1 được xem là đã xảy ra. Thao tác còn lại đọc state mới và quyết định bù trừ phù hợp. Đây là business ordering ở Order owner, không phải suy đoán bằng timestamp của hai HTTP requests.

## 12. Thanh toán: phân biệt intent, authorization, capture và refund

Không nên coi “thanh toán” là một boolean paid=true. Một PSP thường có các bước/khái niệm:
- Payment intent/request.
- Authorization: giữ/cho phép một khoản tiền theo provider contract.
- Capture: thực hiện ghi nhận thu tiền theo policy.
- Void/cancel authorization.
- Refund một phần/toàn bộ khoản đã capture.
- Settlement/reconciliation ngoài phạm vi một HTTP request.

Các service cần có state model phù hợp provider và domain:

~~~text
NEW
  |
  v
AUTHORIZING
  |           \
  v            v
AUTHORIZED    REJECTED
  |
  v
CAPTURING
  |          \
  v           v
CAPTURED      UNKNOWN
  |
  v
REFUNDING -> PARTIALLY_REFUNDED / REFUNDED
~~~

Đây là ví dụ; nhiều PSP có semantics và trạng thái khác. Không áp một mô hình cố định nếu provider chỉ hỗ trợ sale, split capture hoặc các nghiệp vụ khác.

### 12.1. Double authorize/capture do hai request đồng thời

Hai requests với cùng orderId cùng gọi PSP authorize. Nếu không có payment intent identity, PSP có thể hiểu đó là hai yêu cầu độc lập.

Cần:
1. Stable payment operation ID.
2. Unique constraint theo tenant/merchant/order/operation role phù hợp.
3. Atomic claim trong Payments DB.
4. Gửi cùng provider idempotency key/merchant reference nếu PSP hỗ trợ.
5. Nếu request duplicate, trả PENDING hoặc kết quả cũ.
6. Tra cứu PSP bằng reference cũ khi timeout.
7. Không tạo operation ID mới để “thử lại cho chắc”.

### 12.2. Local DB transaction không rollback PSP

~~~text
Payment Service                    PSP
   |
   | Commit Payment(PENDING)
   |
   | -- authorize(key=K) --------->|
   |                               | AUTHORIZED
   | <------ response lost -- X    |
   |
   ? Local Payment vẫn UNKNOWN.
~~~

Không thể rollback database local để làm PSP quên authorization đã xảy ra. Nếu call timeout, outcome là UNKNOWN cho đến khi có nguồn sự thật xác nhận.

Đừng dùng “bắt exception rồi retry với UUID mới” cho tiền. Phải dùng stable reference và reconciliation.

## 13. Thiết kế payment operation storage

Một schema minh họa:

~~~sql
CREATE TABLE payment_operations (
    operation_id VARCHAR(140) PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    order_id VARCHAR(120) NOT NULL,
    action_type VARCHAR(40) NOT NULL,
    amount_minor BIGINT NOT NULL,
    currency VARCHAR(3) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    provider_reference VARCHAR(180),
    status VARCHAR(40) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    UNIQUE (tenant_id, order_id, action_type, operation_id)
);
~~~

Unique constraint cần phản ánh business semantics: ví dụ nếu cho partial captures, có thể có nhiều capture operations khác nhau với amount và reference riêng; không đặt UNIQUE(orderId, CAPTURE) một cách máy móc nếu nghiệp vụ cho phép nhiều captures.

### 13.1. Claim trước side effect

Một use case nên:
- Nhận stable operationId do coordinator tạo hoặc được xác định bền vững.
- Validate amount/currency và quyền.
- Claim operation atomically trong local DB transaction.
- Commit intent trước lời gọi PSP.
- Gọi PSP bằng provider reference ổn định.
- Lưu kết quả có thẩm quyền trong transaction mới.
- Nếu response mất, giữ UNKNOWN và tra cứu lại bằng reference cũ.

### 13.2. Concurrent webhook và synchronous response

PSP có thể gửi webhook AUTHORIZED trước khi synchronous HTTP response đến Payment Service. Hai handler có thể cùng cập nhật Payment.

Cần:
- Verify signature/provenance và chống replay cho webhook.
- Dùng provider eventId và state version/final-state guards.
- Có unique constraint trên provider reference ở scope phù hợp.
- Chấp nhận cùng kết quả từ hai nguồn như một transition idempotent.
- Không cho event PENDING đến muộn ghi đè AUTHORIZED/CAPTURED.
- Nếu hai nguồn xung đột, đưa vào reconciliation thay vì chọn last write wins tùy tiện.

## 14. Refund: cạnh tranh giữa nhiều yêu cầu hoàn tiền

Giả sử đã capture 100.000 đơn vị tiền nhỏ nhất; hai support agents cùng gửi refund 70.000, hoặc client retry refund do timeout.

Nếu mỗi request chỉ đọc refundable=100.000 rồi tạo refund 70.000, có thể yêu cầu tổng 140.000 trước khi một trong các trạng thái được đồng bộ.

Cần mô hình hạn mức hoàn tiền có thẩm quyền:
- Tổng captured, refunded và outstanding refund intents.
- Atomic claim/decrement remaining refundable hoặc lock ledger row.
- Refund operation IDs duy nhất.
- PSP idempotency/reference và reconciliation.
- Chỉ giải phóng quota reservation khi refund thật sự thất bại có thẩm quyền.
- Không báo refund succeeded khi provider còn PENDING/UNKNOWN.

Ví dụ guard tổng mức refund, trong cùng local DB:

~~~sql
UPDATE payment_balances
SET refundable_reserved =
      refundable_reserved + :refund_amount,
    version = version + 1
WHERE payment_id = :payment_id
  AND captured_minor - refunded_minor
      - refundable_reserved >= :refund_amount;
~~~

Kiểm tra affected rows=1 trước khi tạo RefundOperation trong **cùng transaction**. Sau khi PSP xác nhận, cập nhật refunded_minor và giảm refundable_reserved theo state machine. Nếu PSP timeout, quota có thể phải tiếp tục được giữ tới khi reconciliation; không lập tức trả lại rồi phát refund mới.

## 15. Order, Inventory, Payment là ba transaction boundaries

Một checkout có thể có các local commits:

~~~text
Order DB:
  Create Order(PENDING) + Outbox(OrderCreated)
  COMMIT

Inventory DB:
  ReserveStock + Reservation + Outbox(InventoryReserved)
  COMMIT

Payment DB:
  Save PaymentIntent(PENDING)
  COMMIT
  Call PSP (side effect outside local transaction)
  Save PaymentResult + Outbox(PaymentAuthorized)
  COMMIT

Order DB:
  Confirm Order + Outbox(OrderConfirmed)
  COMMIT
~~~

Không có một @Transactional chung bao phủ tất cả. Mỗi service bảo vệ invariant riêng bằng local transaction. Liên kết toàn cục thông qua Saga/workflow và events/commands có identity.

### 15.1. Vì sao không giữ SQL transaction mở xuyên PSP?

Nếu Inventory transaction giữ khóa stock trong lúc chờ PSP 10 giây, các checkout khác cùng SKU có thể bị block. PSP timeout cũng không có nghĩa side effect đã rollback. Giữ transaction dài tăng lock wait, connection pressure và deadlock.

Nên giữ local transaction ngắn:
- Reserve inventory rồi commit.
- Payment authorization có intent bền và reference riêng.
- Workflow quyết định CONFIRMED, RELEASE hoặc NEEDS_RECONCILIATION sau đó.

### 15.2. Nếu cần atomicity mạnh tức thời?

Có những invariants không thể chấp nhận bất cứ trạng thái trung gian nào và không có compensation hợp lệ. Khi đó cần xem lại bounded context: có thể gộp các quyết định gắn chặt vào một service/database transaction thay vì buộc qua ba services. Microservices không phải mục tiêu tự thân; mô hình consistency phải xuất phát từ nghiệp vụ.

## 16. Saga và compensation khi cạnh tranh

Saga tổ chức các local transactions thành workflow dài:

~~~text
Create Order
    |
    v
Reserve Inventory
    |
    v
Authorize Payment
    |
    +---- AUTHORIZED ----> Confirm Order
    |
    +---- REJECTED ------> Release Inventory
                                   |
                                   v
                               Cancel Order
    |
    +---- UNKNOWN -------> Reconcile Payment
~~~

Compensation **không phải rollback ACID**. Release reservation hoặc void payment là một nghiệp vụ mới, có thể thất bại và có operation identity riêng.

### 16.1. Race giữa hủy đơn và thanh toán đến muộn

Order đã chuyển sang CANCELLING, nhưng PaymentAuthorized event tới sau đó.

Một cách xử lý:
- Order không chuyển thẳng thành CONFIRMED nếu state guard không cho phép.
- Coordinator phát yêu cầu void authorization nếu provider cho phép và nghiệp vụ yêu cầu.
- Theo dõi kết quả void; nếu void timeout thì giữ UNKNOWN/RECONCILING.
- Chỉ chuyển CANCELLED hoàn tất khi điều kiện bù trừ đã thỏa theo contract.
- Nếu đã capture thì có thể cần refund, không dùng void sai loại nghiệp vụ.

### 16.2. Compensation có thể được yêu cầu hai lần

Một command ReleaseReservation có thể được gửi hai lần do broker redelivery. Inventory phải xử lý bằng state guard; status RELEASED không được làm available tăng lần nữa. Payment refund cũng vậy: một refund ID không được tạo hai provider refunds do retry.

## 17. Transactional Outbox và consumer inbox

Nếu Order DB commit nhưng event chưa publish, Inventory không biết cần giữ hàng. Transactional outbox giải quyết khoảng lỗi giữa **business DB commit** và **message intent**:

~~~text
BEGIN
  INSERT Order(PENDING)
  INSERT Outbox(OrderCreated, stable eventId)
COMMIT

Outbox relay -> Broker -> Inventory consumer
~~~

Broker/relay có thể phát event trùng. Inventory consumer cần idempotency ở hai mức:
1. Message dedup theo eventId/inbox record.
2. Business dedup theo reservation key của Order/SKU/purpose.

### 17.1. Inbox xử lý trùng trong cùng local transaction

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(140) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Một local transaction có thể claim inbox, reserve stock và ghi event output cùng nhau. Nếu crash trước commit, broker redelivery sẽ làm lại; nếu crash sau commit trước ACK, consumer sẽ thấy inbox record và không reserve lại.

Không ghi inbox trong transaction A rồi reserve stock trong transaction B mà không có recovery protocol: crash giữa chúng có thể khiến lần retry tưởng đã xử lý dù chưa reserve.

### 17.2. Event ordering

OrderCreated v1 và OrderCancelled v2 có thể đến sai thứ tự. State transitions nên mang aggregate version/sequence và guard cục bộ. Kafka ordering theo partition key có thể giúp trong phạm vi partition, nhưng không loại bỏ duplicate, retry hoặc side effect ngoài broker.

## 18. Unknown outcome khi mạng lỗi

Một timeout không tự chứng minh thất bại:

~~~text
Client/Order                      Inventory/Payment
    |                                   |
    | --- POST operation K -----------> |
    |                                   | COMMIT / PSP side effect
    | <----- response lost ------ X     |
    |                                   |
    | Timeout                           |
    ? K đã thực hiện hay chưa?           |
~~~

Một API đáng tin nên hỗ trợ:
- Stable idempotency key hoặc client operation ID.
- Response PENDING/UNKNOWN khi chưa có kết luận final.
- Status lookup theo operation ID/key.
- Retention key đủ dài cho retry/recovery.
- Reconciliation từ authoritative owner/provider.

Nếu GET status trả 404 từ read replica đang lag, không thể tự kết luận operation không tồn tại. Cần hiểu consistency semantics của status endpoint.

### 18.1. Retry không có idempotency là nguy hiểm

Sai:

~~~java
for (int i = 0; i < 3; i++) {
    paymentClient.capture(UUID.randomUUID().toString(), cmd);
}
~~~

Mỗi lần gửi có một identity khác, nên PSP có thể xử lý chúng như các captures độc lập.

Đúng về nguyên tắc:

~~~java
String stableOperationId = checkout.captureOperationId();
paymentClient.capture(stableOperationId, cmd);
~~~

Nhưng chỉ giữ key thôi chưa đủ: provider/service phải **thực sự bảo vệ idempotency**, có retry budget và cách xác minh kết quả mơ hồ.

## 19. Spring Boot: reserve tồn kho bằng atomic SQL

Repository với Spring Data JDBC/JPA có thể thực hiện conditional update. Ví dụ:

~~~java
public interface InventoryRepository
        extends JpaRepository<InventoryEntity, String> {

    @Modifying
    @Query(value = """
        UPDATE inventory
        SET available = available - :quantity,
            reserved = reserved + :quantity,
            version = version + 1
        WHERE sku = :sku
          AND available >= :quantity
        """, nativeQuery = true)
    int tryReserve(
        @Param("sku") String sku,
        @Param("quantity") long quantity);
}
~~~

Use case:

~~~java
@Service
public class ReserveStockUseCase {
    private final InventoryRepository inventory;
    private final ReservationRepository reservations;
    private final OutboxRepository outbox;

    public ReserveStockUseCase(
            InventoryRepository inventory,
            ReservationRepository reservations,
            OutboxRepository outbox) {
        this.inventory = inventory;
        this.reservations = reservations;
        this.outbox = outbox;
    }

    @Transactional
    public ReservationResult reserve(ReserveCommand cmd) {
        Reservation existing =
            reservations.findByBusinessKey(cmd.operationId());

        if (existing != null) {
            return ReservationResult.from(existing);
        }

        int updated = inventory.tryReserve(
            cmd.sku(), cmd.quantity());

        if (updated != 1) {
            return ReservationResult.rejected("OUT_OF_STOCK");
        }

        Reservation reservation =
            reservations.save(Reservation.reserved(cmd));

        outbox.save(OutboxEvent.inventoryReserved(reservation));
        return ReservationResult.reserved(reservation.id());
    }
}
~~~

**Đây là đoạn minh họa, không phải ứng dụng compile-ready**: Command, repositories, entities, outbox factory và error handling cần được hiện thực. Trong production phải:
- Kiểm tra quantity > 0, tenant/SKU và quyền.
- Dùng unique constraint business key trên reservations; read-then-insert chưa đủ chặn race.
- Nếu insert fail vì duplicate, rollback cả transaction rồi đọc lại kết quả đã commit ở một transaction thích hợp.
- Phân biệt SKU không tồn tại với out of stock nếu API contract yêu cầu.
- Giữ stock update, reservation insert và outbox insert trong **cùng local DB transaction**.
- Không catch exception rồi trả success khi transaction có thể bị đánh dấu rollback-only.
- Kiểm tra ảnh hưởng của native update đến persistence context/cache; tránh đọc lại entity stale trong cùng session.
- Không gọi PSP hoặc network lâu trong transaction này.

### 19.1. Concurrent duplicate requests

Hai threads có cùng operationId:
- Cả hai có thể đọc existing=null.
- Một thread reserve và insert thành công.
- Thread kia có thể chờ row lock, sau đó update stock nếu còn.
- Khi insert cùng unique business key, một thread sẽ bị constraint conflict.

Nếu mọi bước trong **cùng transaction**, transaction bị conflict phải rollback stock update của nó. Sau rollback, service trả kết quả operation đã tồn tại, chứ không coi constraint violation là lỗi hệ thống vĩnh viễn.

Tối ưu hơn có thể atomic claim operation/reservation key trước khi động đến stock, tránh cập nhật không cần thiết. Nhưng phải đảm bảo claim và stock effect có semantics transaction/recovery rõ.

## 20. Spring Boot: guarded Order transition

Order service chỉ chuyển state khi điều kiện thỏa:

~~~java
public interface OrderRepository
        extends JpaRepository<OrderEntity, String> {

    @Modifying
    @Query(value = """
        UPDATE orders
        SET status = 'CONFIRMED',
            version = version + 1
        WHERE id = :orderId
          AND status = 'PENDING_PAYMENT'
          AND version = :expectedVersion
        """, nativeQuery = true)
    int confirmIfPending(
        @Param("orderId") String orderId,
        @Param("expectedVersion") long expectedVersion);
}
~~~

Application layer:

~~~java
@Transactional
public ConfirmResult confirm(
        String orderId, long expectedVersion,
        PaymentEvidence payment, ReservationEvidence stock) {

    if (!payment.isAuthorized()
            || !stock.isReserved()) {
        return ConfirmResult.notReady();
    }

    int count = orders.confirmIfPending(orderId, expectedVersion);

    if (count == 1) {
        outbox.save(OutboxEvent.orderConfirmed(orderId));
        return ConfirmResult.confirmed();
    }

    return ConfirmResult.conflictOrAlreadyProcessed();
}
~~~

Code này chỉ mô tả một phần workflow. PaymentEvidence và ReservationEvidence phải đến từ nguồn có thẩm quyền hoặc state mà Order service đã xử lý tin cậy; không lấy thông tin người dùng tự khai. Nếu count=0, phải đọc trạng thái thật để phân biệt:
- Đã CONFIRMED theo cùng intent → trả idempotent success.
- Đã CANCELLED → từ chối transition và xử lý late effects.
- Version stale nhưng status vẫn PENDING → quyết định retry/refresh.
- Order không tồn tại → 404/business error.

Không phát OrderConfirmed khi SQL update không thực sự chuyển state.

## 21. Payment adapter và durable intent

Mẫu các ranh giới:

~~~java
public record CaptureCommand(
    String paymentId,
    String captureOperationId,
    long amountMinor,
    String currency
) {}

public enum CaptureStatus {
    NEW, SUBMITTED, CAPTURED, REJECTED, UNKNOWN
}

public interface PaymentProviderPort {
    ProviderCaptureResult capture(CaptureCommand command);
    ProviderCaptureResult findCapture(String operationId);
}
~~~

Một use case có thể:
1. Claim CaptureOperation trong DB với unique key, amount và currency.
2. Commit durable intent.
3. Gọi PSP với captureOperationId làm stable provider idempotency key nếu hợp đồng hỗ trợ.
4. Khi có kết quả cuối, ghi state và outbox event trong local transaction.
5. Khi timeout, lưu UNKNOWN và đặt lịch status inquiry.
6. Nếu có webhook đến đồng thời, update state với version/status guard.
7. Chỉ retry command khi contract idempotent và retry budget cho phép.

Không giữ một transaction SQL mở trong thời gian chờ PSP chỉ để “kéo ACID qua mạng”. Nó không làm PSP tham gia local transaction và còn tăng lock/connection contention.

## 22. Business uniqueness khác message uniqueness

Một eventId có thể được phát lại, nhưng một business intent cũng có thể bị phát hai lần với hai eventIds nếu upstream bug hoặc người dùng retry sai.

Ví dụ:
- evt-101: ReserveInventory(order-471, SKU-A).
- evt-102: ReserveInventory(order-471, SKU-A).

Inbox theo eventId coi đây là hai messages mới. Nếu không có unique reservation business key, stock có thể bị giữ hai lần.

Nên bảo vệ cả:
- eventId unique cho một message được relay/replay.
- operationId unique cho một nghiệp vụ được yêu cầu.
- resource/transaction constraints giữ invariant cuối.
- request fingerprint để cùng key không đại diện hai payload khác nhau.

Đây là lý do **exactly-once business effect** nên được chứng minh bằng business identity và database constraints, không chỉ bằng nhãn “exactly-once” của broker.

## 23. Hot SKU và lựa chọn mô hình tải cao

Một sản phẩm flash sale có hàng nghìn request/giây cho cùng một row inventory. Atomic UPDATE đúng về tính nhất quán nhưng có thể gây contention ở row hot.

Các chiến lược:
- Queue/serialize reservations theo SKU để điều tiết tải, với durable queue.
- Phân vùng stock theo warehouse/location khi nghiệp vụ cho phép.
- Bounded reservation tokens hoặc escrow-like allocation với reconciliation.
- Pre-allocate capacity theo buckets/partitions có invariant tổng rõ.
- Admission control/rate limiting để giảm burst vượt khả năng xử lý.
- Cache thông tin hiển thị, nhưng xác nhận stock tại owner có thẩm quyền.
- Đo lock wait/deadlocks và kết hợp retry có giới hạn.

### 23.1. Sharding stock không tự an toàn

Nếu chia 100 đơn vị stock thành 10 buckets, cần bảo đảm tổng available trên buckets không tự vượt on_hand hoặc bị cấp phát hai lần khi rebalance. Chuyển stock giữa buckets cũng là một operation cần atomicity/lock/idempotency phù hợp.

Không nên tăng throughput bằng cách sao chép stock=100 vào mọi bucket rồi coi mỗi bucket có quyền bán 100. Đó chỉ là nhân overselling lên quy mô lớn hơn.

### 23.2. Queue không tự loại bỏ duplicate

Queue có thể tuần tự hóa requests theo key trong một số cấu hình, nhưng broker có thể redeliver; consumer crash sau commit trước ACK; partition key thay đổi; nhiều workers được scale. Dù có queue, Inventory vẫn cần atomic business constraints.

## 24. Race trong voucher, quota và giới hạn thanh toán

Cùng kiểu lỗi check-then-act xuất hiện ngoài stock:

**Voucher giới hạn 100 lượt:** hai transactions cùng thấy used=99 rồi đều phát voucher. Dùng atomic conditional update trên remaining hoặc một unique entitlement/claim table phù hợp.

**Giới hạn mua mỗi khách:** hai requests cùng thấy customerBought=0 rồi mỗi request đặt quantity=1; nếu business rule tối đa 1, cần unique/conditional claim theo (customerId, promotionId).

**Ngân sách khuyến mại:** nhiều orders cùng tiêu spend budget. Không chỉ cache giá trị ngân sách trên client; dùng owner có authoritative atomic allocation.

**Refund quota:** hai agents cùng thấy còn hoàn 100 nhưng mỗi người yêu cầu 70. Phải reserve/validate remaining refundable trong cùng local transaction.

Bài học chung: **quy tắc dựa trên dữ liệu chia sẻ phải được bảo vệ ở điểm phân bổ có thẩm quyền**, không chỉ bằng một truy vấn đọc trước khi ghi.

## 25. HTTP semantics và phản hồi cho client

Các kết quả cần phân biệt:
- 201 Created: resource đã được tạo theo contract, có ID.
- 200 OK: một thao tác idempotent đã được xử lý và có kết quả tương ứng.
- 202 Accepted: hệ thống nhận intent, việc cuối cùng có thể còn PENDING.
- 409 Conflict: state conflict, key reuse conflict hoặc một business precondition không phù hợp tùy API design.
- 422 Unprocessable Content: một số hệ thống dùng cho từ chối business validation.
- 429 Too Many Requests: hạn chế tải, thường kèm Retry-After khi phù hợp.
- 500/502/503/504 hoặc timeout: kết quả side effect có thể UNKNOWN, không tự chứng minh rollback.

Ví dụ trả operation status:

~~~http
POST /checkout
Idempotency-Key: checkout-471-v1

{"cartId":"cart-471"}
~~~

~~~http
HTTP/1.1 202 Accepted
Location: /checkout-operations/op-471

{"operationId":"op-471","status":"PENDING_PAYMENT"}
~~~

Khi client không nhận được cả response 202, phải có cách query operation theo idempotency key hoặc một client-generated operationId. Nếu chỉ biết một ID được sinh trong response bị mất, client có thể không tìm lại được.

### 25.1. UI phải phản ánh trạng thái mơ hồ

Nếu thanh toán timeout, UI không nên hiển thị “Thất bại, hãy thanh toán lại ngay” một cách chắc chắn. Có thể hiển thị “Đang xác minh” và cung cấp đường kiểm tra trạng thái có thẩm quyền. Thao tác retry phải sử dụng cùng identity, không tạo payment mới.

## 26. Những hiểu lầm phổ biến

**“Chỉ một server nên không có race.”** Sai; nhiều threads/requests trên cùng instance vẫn có thể chạy đồng thời.

**“Có @Transactional thì check-then-update luôn an toàn.”** Không đủ; isolation, locking và query shape quyết định có race hay không.

**“Đặt synchronized trong Java là xong.”** Chỉ khóa trong một JVM/process; nhiều pods/instances vẫn có thể chạy song song. Restart và distributed events cũng vượt phạm vi lock này.

**“Redis lock bảo đảm tuyệt đối không oversell.”** Không tự bảo đảm nếu lock lease hết hạn, worker cũ vẫn chạy, hệ thống có failover hoặc chưa có fencing. DB invariant/atomic update vẫn quan trọng.

**“Dùng SELECT trước UPDATE để chắc còn hàng.”** SELECT không giữ giá trị ổn định khi transaction khác cập nhật; dùng atomic guard hoặc locking phù hợp.

**“SERIALIZABLE làm HTTP Payment cũng rollback.”** Isolation level chỉ thuộc local database; PSP không tham gia transaction đó.

**“Idempotency key mới cho mỗi retry sẽ an toàn hơn.”** Sai với cùng một business intent: key mới có thể tạo duplicate side effect.

**“Một eventId unique đủ chống mọi duplicate.”** Chưa đủ nếu cùng intent bị phát thành nhiều eventIds khác nhau.

**“Message broker exactly-once nghĩa là PSP capture đúng một lần.”** Không phải cùng phạm vi bảo đảm. Phải bảo vệ provider operation identity và reconciliation.

**“Timeout là business failure.”** Không đúng; server/PSP có thể đã commit mà response bị mất.

**“Release tồn kho thì chỉ cần cộng lại quantity.”** Không đủ; release phải dựa vào reservation state và thực hiện tối đa một lần.

**“Thêm replica database/gateway tự giải quyết race.”** Replica chỉ thay đổi topology; nếu thiếu correctness constraints thì race có thể xảy ra nhiều hơn.

**“Optimistic locking conflict thì retry vô hạn.”** Có thể gây starvation/retry storm; phải có budget, backoff và phân loại business state.

**“Đơn đã CANCELLED thì PaymentAuthorized đến muộn có thể bỏ qua luôn.”** Có thể PSP đã giữ tiền; cần void/refund/reconciliation theo policy.

## 27. Quan sát và dấu hiệu cạnh tranh

Những metrics nên theo dõi:

| Nhóm | Ví dụ |
| --- | --- |
| Stock correctness | Oversell incidents, negative available, inventory discrepancies |
| DB contention | Lock wait, deadlocks, serialization failures, hot row updates |
| Conditional update | Affected-row=0 rate, insufficient stock vs stale version |
| Idempotency | Duplicate requests blocked, key fingerprint conflicts |
| Reservation lifecycle | RESERVED age, EXPIRED/RELEASED transitions, stuck holds |
| Payment | UNKNOWN captures, duplicated provider references, reconciliation age |
| Retry | Attempts per intent, retry amplification, conflict retry rate |
| Saga | PENDING/CANCELLING/RECONCILING age, compensation failures |
| Broker | Redelivery rate, consumer inbox dedup count, DLQ, lag |
| Performance | p95/p99 checkout latency, stock lock time, DB connection wait |
| Business invariants | Confirmed order without reserved stock/payment evidence |

Logs/traces cần liên kết:
- checkoutOperationId.
- orderId và tenantId.
- reservationId, SKU, quantity.
- paymentOperationId, provider reference.
- eventId/correlationId.
- status/version trước và sau transition.
- lỗi, retry count và nextReconcileAt.

Không dùng orderId hoặc userId làm metric label có cardinality vô hạn. Không log thông tin thẻ, token hoặc PII không cần thiết. Logs nên hỗ trợ điều tra một intent, không trở thành nguồn dữ liệu nhạy cảm mở rộng.

## 28. Kiểm thử race condition có kiểm soát

Một test chạy tuần tự không đủ. Cần phát nhiều requests có chủ đích cùng thời điểm và kiểm tra invariant trong database thật.

### Case 1 — Hai người mua item cuối

Stock available=1. Hai threads cùng reserve quantity=1 với operationIds khác nhau.

Kỳ vọng:
- Tối đa một reservation RESERVED.
- available=0, reserved tăng đúng 1.
- Một request nhận kết quả OUT_OF_STOCK/conflict theo contract.
- Không có stock âm.

### Case 2 — Hai requests cùng business key

Hai threads dùng cùng reservationKey cho cùng Order/SKU.

Kỳ vọng:
- Chỉ một reservation.
- Một lần trừ stock.
- Request còn lại trả kết quả idempotent hoặc chờ result cũ.
- Không để constraint exception làm stock đã trừ bị commit.

### Case 3 — Request trùng với payload khác

Hai requests chung idempotency key nhưng quantity 1 và quantity 2.

Kỳ vọng: fingerprint conflict, không silently đổi quantity của operation đã claim.

### Case 4 — Confirm và release đồng thời

Reservation đang RESERVED; một thread CONFIRM, một thread RELEASE.

Kỳ vọng: chỉ một transition thành công; nếu RELEASE thắng thì Order không được CONFIRMED với reservation đó.

### Case 5 — Cancel và payment authorized đồng thời

Order PENDING_PAYMENT, CancelOrder và PaymentAuthorized event tới cùng lúc.

Kỳ vọng: state machine chọn transition hợp lệ; không có Order CANCELLED nhưng PSP authorization bị bỏ quên.

### Case 6 — Double capture

Hai capture commands cùng operationId tới Payments trên hai pods.

Kỳ vọng: chỉ một provider capture effect, còn lại trả PENDING/result cũ; cần môi trường giả lập PSP có idempotency semantics.

### Case 7 — PSP response mất

Provider đã capture, response bị mất.

Kỳ vọng: Payment UNKNOWN rồi reconcile theo stable reference, không tạo capture mới.

### Case 8 — Refund đồng thời

Captured=100, hai refund requests với hai operations hợp lệ, mỗi request 70.

Kỳ vọng: tổng reserved+refunded không vượt 100; ít nhất một request bị từ chối/đợi theo policy.

### Case 9 — Broker redelivery

Inventory xử lý OrderCreated, commit rồi crash trước ACK; broker gửi lại.

Kỳ vọng: inbox/business constraints chặn trừ stock hai lần.

### Case 10 — Reservation expiry race

Expiry worker và Order confirmation cùng cập nhật reservation gần deadline.

Kỳ vọng: transition có guard, available không sai; Order xử lý trường hợp reservation không còn hiệu lực.

### Case 11 — Deadlock nhiều SKU

Hai orders reserve các SKUs A và B theo thứ tự ngược.

Kỳ vọng: hệ thống phát hiện deadlock và retry local transaction có giới hạn, không giữ stock nửa chừng.

### Case 12 — Rollout nhiều phiên bản

App v1 và v2 cùng chạy, event v1 đến muộn.

Kỳ vọng: mọi instance xử lý state guards, operation identity và schema compatibility đồng nhất trong compatibility window.

### 28.1. Dùng barrier để tạo contention thực

Trong Java, có thể dùng CountDownLatch hoặc CyclicBarrier để nhiều threads bắt đầu cùng lúc; test nên dùng database thật (ví dụ Testcontainers) thay vì chỉ mock repository.

~~~java
int workers = 2;
CountDownLatch start = new CountDownLatch(1);

ExecutorService pool = Executors.newFixedThreadPool(workers);

Future<ReservationResult> first =
    pool.submit(() -> {
        start.await();
        return api.reserve("op-A", "SKU-100", 1);
    });

Future<ReservationResult> second =
    pool.submit(() -> {
        start.await();
        return api.reserve("op-B", "SKU-100", 1);
    });

start.countDown();

ReservationResult r1 = first.get();
ReservationResult r2 = second.get();
~~~

Đoạn test chỉ minh họa orchestration concurrent calls; cần setup/teardown, timeout, exception handling, database reset và assertions sau khi cả hai hoàn tất.

**Assert cuối nên nằm trên database invariants**, không chỉ kiểm tra hai HTTP responses. Một request timeout có thể đã commit, nên test cần tra cứu đúng resource/operation sau đó.

### 28.2. Property-based và stress testing

Có thể tạo chuỗi ngẫu nhiên có kiểm soát:
- Reserve, confirm, release, expire.
- Create order, cancel, confirm.
- Authorize, capture, refund và webhook duplicate.
- Network reset, delayed events, service restart.

Sau mỗi chuỗi, kiểm tra invariants như available>=0, không double capture, state transitions hợp lệ, không có reservation bị release hai lần. Stress tests tìm race hiếm, còn deterministic fault-injection giúp tái hiện lỗi cụ thể.

## 29. Tình huống điển hình từ đầu đến cuối

Giả sử stock SKU-X còn 1, khách A và B cùng checkout; trong khi đó mạng tới PSP chập chờn.

~~~text
A: CreateOrder(op-A) -> Order A PENDING
B: CreateOrder(op-B) -> Order B PENDING

A: Reserve(SKU-X,1) -> atomic update succeeds
B: Reserve(SKU-X,1) -> atomic update affects 0 rows

A: PaymentAuthorize(pay-A) -> PSP approves but response lost
A: Payment remains UNKNOWN; reconcile using pay-A
B: Order cancelled/rejected due to no stock

A: PSP status returns AUTHORIZED
A: Order confirms after authoritative inventory/payment evidence
~~~

Ở đây hệ thống đạt tính đúng nhờ **nhiều lớp bảo vệ có trách nhiệm rõ**:
- A và B có checkout identity khác nhau.
- Inventory atomic update chỉ cho một request giữ hàng.
- Payment giữ provider identity, không authorize lần hai khi timeout.
- Order transition chỉ CONFIRMED khi bằng chứng đủ.
- Events và retries có idempotency/ordering.
- UI thể hiện PENDING/UNKNOWN thay vì báo sai.

Nếu A payment bị REJECTED thay vì AUTHORIZED, Saga cần release reservation của A. Release có identity và guarded transition để available tăng đúng một lần, sau đó một checkout khác có thể mua hàng nếu điều kiện vẫn hợp lệ.

## 30. Checklist triển khai production

- [ ] Đã định nghĩa invariants cho order, stock và money?
- [ ] Mỗi invariant có service/database owner rõ?
- [ ] Không dựa vào client/UI để chặn duplicate hoặc oversell?
- [ ] Stock decrement dùng atomic conditional UPDATE hoặc locking đúng?
- [ ] Affected row count được kiểm tra và transaction rollback đúng khi insert lỗi?
- [ ] Reservation có business unique key phù hợp domain?
- [ ] Reserve/confirm/release/expire có guarded state transitions?
- [ ] Có bảo vệ double release và expiration race?
- [ ] Multi-SKU transaction khóa theo thứ tự xác định khi cần?
- [ ] Có giới hạn contention và retry khi deadlock/serialization failure?
- [ ] Order create dùng stable checkout/idempotency key?
- [ ] Same key + different payload trả conflict?
- [ ] Order cancel/confirm có version/status guards?
- [ ] Payment authorize/capture/refund có operation identity riêng?
- [ ] PSP idempotency và status inquiry đã được kiểm chứng theo provider contract?
- [ ] Timeout không bị coi ngay là business failure?
- [ ] Payment UNKNOWN có reconciliation timer/owner?
- [ ] Refund quota và partial refund được bảo vệ atomically?
- [ ] Local DB transaction không giữ qua external PSP call dài?
- [ ] Saga có compensation và state machine cho late events?
- [ ] Domain state + outbox cùng commit cục bộ?
- [ ] Inbox và business idempotency bảo vệ event redelivery?
- [ ] Có metrics lock wait, duplicate, UNKNOWN, oversell và compensation failures?
- [ ] Đã test concurrent requests, retries, rollback, network reset và crash?
- [ ] Authorization/tenant scope được áp dụng cho mọi operation ID?

## 31. Bài tập tình huống

### Bài 1 — Lost update khi còn một sản phẩm

Hai requests cùng đọc available=1 rồi cùng ghi available=0 và tạo hai reservations.

**Câu hỏi:** Tại sao transaction đơn giản chưa đủ? Cách sửa?

*Gợi ý:* Check-then-act race; dùng atomic UPDATE với WHERE available>=quantity và ghi reservation cùng transaction, kiểm tra affected rows.

### Bài 2 — Hai request cùng idempotency key

Hai pods đồng thời xử lý POST /orders key=K, cả hai thấy key chưa có.

**Câu hỏi:** Vì sao if (!exists) không đủ? Cần cấu trúc DB nào?

*Gợi ý:* Unique constraint/atomic claim trong local transaction và xử lý conflict để trả cùng order ID.

### Bài 3 — Release hai lần

Hai compensation workers cùng nhận ReleaseReservation(R) sau khi payment bị từ chối.

**Câu hỏi:** Làm sao không cộng stock hai lần?

*Gợi ý:* Conditional transition RESERVED → RELEASED, chỉ cộng lại khi transition thắng và trong cùng transaction.

### Bài 4 — Cancel và confirm cạnh tranh

Người dùng bấm Cancel khi PaymentAuthorized webhook được xử lý.

**Câu hỏi:** Trạng thái nào đúng? Ai quyết định?

*Gợi ý:* Order owner và state machine có version guard quyết định transition; nếu Cancel thắng nhưng PSP đã authorize, cần void/reconcile.

### Bài 5 — Double charge do timeout

PSP authorize thành công, response mất; backend tạo UUID mới rồi authorize lần nữa.

**Câu hỏi:** Nguyên nhân gốc và phương án sửa?

*Gợi ý:* Mất stable provider reference; lưu durable intent, retry/query cùng operation ID theo contract, giữ UNKNOWN tới khi xác minh.

### Bài 6 — Một SKU quá nóng

Atomic UPDATE đúng nhưng 20.000 requests/s cùng khóa một stock row làm p99 tăng.

**Câu hỏi:** Làm sao tăng throughput mà vẫn không oversell?

*Gợi ý:* Admission control, queue/serialize theo SKU, phân allocation buckets có invariant tổng, đo lock wait và recovery.

### Bài 7 — Refund đồng thời

Payment capture 100. Hai refund operations hợp lệ đồng thời yêu cầu 70.

**Câu hỏi:** Vì sao kiểm tra refundable bằng SELECT không an toàn?

*Gợi ý:* Cần atomic reservation/guard trên số tiền còn hoàn, các payment operations có identity riêng.

### Bài 8 — @Version nhưng PSP gọi trước

Hai payment threads cùng gọi PSP capture, sau đó một thread bị OptimisticLockException khi lưu DB.

**Câu hỏi:** @Version có ngăn double capture không?

*Gợi ý:* Không, PSP side effect đã xảy ra. Claim operation trước PSP và dùng provider idempotency/status lookup.

### Bài 9 — Kafka gửi OrderCreated trùng

Inventory consumer commit reservation rồi crash trước broker ACK, message được phát lại.

**Câu hỏi:** Những lớp nào phải chống trùng?

*Gợi ý:* Consumer inbox theo eventId + reservation unique business key, cùng local transaction.

### Bài 10 — Hết hạn reservation và thanh toán tới sau

Reservation vừa EXPIRED; PSP trả AUTHORIZED sau timeout.

**Câu hỏi:** Order có thể CONFIRMED không?

*Gợi ý:* Chỉ nếu có stock evidence hợp lệ theo domain. Nếu không, cần void/refund/reconcile, không tự xác nhận đơn thiếu hàng.

## 32. Kết luận

Cạnh tranh tài nguyên trong đặt hàng, tồn kho và thanh toán không phải lỗi hiếm chỉ xảy ra khi traffic cực lớn. Một nút được bấm hai lần, một callback đến muộn, một broker redelivery hoặc hai worker chạy gần như đồng thời đã đủ làm lộ race condition.

Giải pháp bắt đầu bằng **business invariants** và **data ownership**. Tồn kho cần atomic conditional update và reservation có unique key; đơn hàng cần stable checkout identity và guarded state machine; thanh toán cần durable operation intent, idempotency tại provider và reconciliation cho kết quả chưa xác định. Optimistic/pessimistic locking, unique constraints, local ACID transactions, outbox/inbox, Saga và retry budgets giải quyết các lớp vấn đề khác nhau, không thể thay thế tùy tiện.

Nguyên tắc quan trọng nhất: **đừng tách bước “kiểm tra điều kiện” khỏi bước “thay đổi tài nguyên” nếu giữa chúng một request khác có thể can thiệp; đừng coi timeout là thất bại; và đừng tạo side effect mới khi ý định nghiệp vụ cũ còn chưa có kết luận có thẩm quyền.**
