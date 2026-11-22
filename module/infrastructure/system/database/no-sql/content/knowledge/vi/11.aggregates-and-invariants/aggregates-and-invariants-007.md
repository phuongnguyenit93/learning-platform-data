# Đánh giá ảnh hưởng khi tách một bất biến qua nhiều bản ghi/phân vùng

Trong thiết kế cơ sở dữ liệu NoSQL, chia dữ liệu thành nhiều **bản ghi (record/document/item)** hoặc **phân vùng (partition)** thường giúp mỗi phần nhỏ hơn, phân phối lưu lượng tốt hơn và mở rộng linh hoạt hơn. Nhưng khi một quy tắc nghiệp vụ cần nhìn và thay đổi **nhiều phần dữ liệu cùng lúc**, việc tách dữ liệu có thể làm thay đổi căn bản khả năng giữ đúng quy tắc đó.

Quy tắc như “không bán quá lượng tồn”, “không thể chuyển tiền khi số dư không đủ”, “mỗi mã giảm giá chỉ được sử dụng một lần” hoặc “mỗi ca trực luôn có ít nhất một nhân viên” được gọi là **bất biến nghiệp vụ (business invariant)**. Bất biến phải còn đúng sau mọi thao tác được chấp nhận, kể cả khi nhiều client chạy đồng thời, request bị gửi lại, một node bị lỗi hoặc sự kiện đến sai thứ tự.

Câu hỏi quan trọng là: **Bất biến có còn nằm trọn trong đơn vị dữ liệu mà database có thể cập nhật nguyên tử không?** Nếu không, ứng dụng phải chọn một cơ chế phối hợp phù hợp, hoặc thay đổi cách tổ chức dữ liệu/luồng nghiệp vụ.

Bài học hướng dẫn phân tích tác động khi một bất biến bị trải qua nhiều bản ghi, nhiều partition, nhiều node hoặc nhiều dịch vụ, rồi so sánh các phương án: **gom dữ liệu theo aggregate**, **conditional update**, **transaction đa bản ghi**, **khóa/phiên bản điều phối**, **reservation và saga**, **ledger/outbox**, cùng các phương pháp kiểm thử cạnh tranh và sự cố.

> Điểm cốt lõi: **Đặt hai giá trị cạnh nhau về mặt nghiệp vụ không đồng nghĩa database có thể bảo vệ chúng trong cùng một transaction.** Ngược lại, hai giá trị nằm cùng partition cũng chưa đủ để kết luận các thao tác trên chúng có tính nguyên tử hoặc isolation: phải xem chính xác primitive và bảo đảm của sản phẩm đang dùng.

## 1. Bất biến nghiệp vụ là gì?

Một bất biến là điều kiện không được vi phạm bởi các trạng thái đã được hệ thống chấp nhận. Có thể mô tả bằng câu chữ hoặc điều kiện toán học.

| Bối cảnh | Bất biến | Dữ liệu tham gia |
| --- | --- | --- |
| Kho hàng | Số lượng có thể bán không âm | available theo SKU |
| Đặt vé | Một ghế không có hai reservation hiệu lực | seatId, reservationId, trạng thái và thời hạn |
| Giỏ hàng | Tổng tiền bằng tổng các dòng hàng và quy tắc tính giá đã chốt | cart, items, discount, tax |
| Ví điện tử | Không tự tạo/mất giá trị khi chuyển giữa hai ví | debit, credit, ledger, transactionId |
| Mã khuyến mãi | Một coupon dùng tối đa một lần cho cùng điều kiện | coupon, redemption, user |
| Phân quyền | Luôn còn ít nhất một quản trị viên hợp lệ | danh sách thành viên, role |
| Đăng ký tên người dùng | Username duy nhất trong phạm vi tenant | tenantId, username, owner |

Một số cách phát biểu cụ thể:

~~~text
Bất biến tồn kho:
    available(sku) >= 0

Bất biến đặt ghế:
    count(activeReservations(eventId, seatId)) <= 1

Bất biến duy nhất:
    count(users where tenantId = T and username = U) <= 1

Bất biến chuyển tiền:
    sum(balances after) + externalSettlements
      = sum(balances before)
      + externalDeposits - externalWithdrawals
~~~

Những công thức này cần được làm rõ theo thực tế: tiền có phí, thuế, giữ tạm, hoàn tiền và nguồn giao dịch ngoài; tồn kho có hàng đang giữ, hàng đã xuất và hàng hỏng. Một bất biến mơ hồ có thể dẫn tới “thiết kế đúng kỹ thuật” nhưng sai ngữ nghĩa nghiệp vụ.

### Phân biệt bất biến tức thời và điều kiện được phép hội tụ

Không phải mọi khác biệt giữa các bản ghi đều là lỗi nghiêm trọng.

- **Phải đúng ngay khi xác nhận thành công:** không oversell; một ghế không được giữ cho hai đơn; không ghi debit mà không có cơ chế bảo đảm giá trị được ghi nhận/hoàn trả.
- **Có thể hội tụ sau khoảng thời gian:** số lượt xem trên dashboard; danh sách đơn mới nhất trong search index; số lượng sản phẩm theo category ở cache.
- **Phải đúng khi kết thúc quy trình:** một đơn ở trạng thái CONFIRMED phải có thanh toán và giữ hàng hợp lệ, nhưng có thể trải qua PENDING hoặc RESERVED trong lúc xử lý.

Nếu nghiệp vụ cho phép một giai đoạn trung gian, cần **mô hình trạng thái hợp lệ** và **giới hạn thời gian phục hồi**, thay vì gọi mọi trạng thái tạm là “nhất quán” một cách chung chung.

## 2. Ranh giới bản ghi và ranh giới bất biến

Hãy phân biệt hai hình dung:

~~~text
Trường hợp A — Bất biến nằm trong một document/item:

inventory:SKU-7
+--------------------------------+
| available: 2                   |
| reserved: 3                    |
| version: 14                    |
+--------------------------------+
   Atomic conditional update trên một đơn vị.

Trường hợp B — Bất biến nằm trên nhiều đơn vị:

inventory:SKU-7       reservation:order-937
+---------------+      +------------------+
| available: 2  |      | status: PENDING  |
| version: 14   |      | sku: SKU-7       |
+---------------+      +------------------+
     Bước 1                    Bước 2
    hai thay đổi phải được phối hợp nếu nghiệp vụ yêu cầu.
~~~

Ở trường hợp A, một conditional update có thể kiểm tra **available >= requested** rồi giảm số lượng trong cùng thao tác nguyên tử, nếu database thực sự hỗ trợ điều kiện ấy.

Ở trường hợp B, **giảm tồn kho** và **tạo reservation** nằm ở hai đơn vị. Thậm chí nếu từng bước đều atomic riêng lẻ, hệ vẫn có thể dừng giữa hai bước. Khi đó cần giải thích điều gì xảy ra với lượng hàng đã giảm nhưng không có reservation, hoặc reservation đã tạo mà tồn kho chưa giảm.

### Các lớp ranh giới cần kiểm tra

| Ranh giới | Ví dụ | Phải xác minh |
| --- | --- | --- |
| Một field | Tăng lượt xem | Primitive tăng có atomic không? |
| Một item/document | Giảm tồn và tăng version trong một đối tượng | Conditional write có bảo vệ cả điều kiện và thay đổi không? |
| Nhiều item/document | Tạo đơn và giữ tồn kho | Có transaction đa bản ghi; isolation nào? |
| Nhiều partition | Chuyển hàng giữa hai kho, chuyển tiền giữa hai ví | Phạm vi transaction có bao phủ các partition không? |
| Nhiều shard/node | Các bản ghi ở các nơi vật lý khác nhau | Có phối hợp phân tán, timeout và failover nào? |
| Nhiều Region | Ghi từ các trung tâm dữ liệu khác nhau | Replication, conflict resolution và phạm vi commit là gì? |
| Nhiều database/dịch vụ | Kho, đơn hàng, thanh toán | Có giao dịch chung thực sự hay cần saga/outbox/ledger? |

**Partition key trùng nhau không tự biến hai lệnh thành một transaction.** Ngược lại, một database có transaction đa item có thể bảo vệ dữ liệu nằm trên nhiều phân vùng *trong phạm vi được nhà cung cấp hỗ trợ*. Vì vậy không thể dùng một quy tắc chung cho tất cả NoSQL.

## 3. Hệ quả thứ nhất: mất tính nguyên tử toàn cục

Xét yêu cầu chuyển 30 đơn vị từ ví A sang ví B:

~~~text
Ban đầu:
    wallet:A.balance = 100
    wallet:B.balance = 0

Quy trình chia thành hai lệnh:
    UPDATE wallet:A.balance -= 30
    UPDATE wallet:B.balance += 30

Kỳ vọng:
    wallet:A = 70
    wallet:B = 30
    tổng = 100
~~~

Nếu ứng dụng chết sau lệnh trừ A:

~~~text
T0  A = 100, B = 0
T1  Trừ A thành công: A = 70
T2  Process chết hoặc mất mạng
T3  Chưa cộng B: B = 0
    Tổng hiện tại = 70
~~~

Hai phép ghi nguyên tử riêng không giải quyết được bất biến **tổng giá trị**. Nếu retry toàn bộ chuỗi mà không xác định kết quả cũ, A còn có thể bị trừ lần nữa.

Có nhiều cách giải quyết tùy phạm vi và nghiệp vụ:

1. **Transaction đa bản ghi:** commit cả debit và credit hoặc cùng rollback, dưới isolation đủ mạnh.
2. **Ledger với trạng thái chuyển tiền:** ghi một transferId duy nhất, lưu hai bút toán liên quan và tính số dư theo các quy tắc nhất quán đã thiết kế.
3. **Quy trình nhiều bước có thể phục hồi:** dùng RESERVED/IN_TRANSIT/COMPLETED, bù trừ nếu có lỗi và reconciliation.
4. **Đổi ranh giới dữ liệu:** nếu hai số dư luôn thuộc cùng một aggregate nhỏ và không gây hot spot, có thể gom vào một đơn vị atomic. Thường khó áp dụng cho ví bất kỳ trên toàn hệ.

Một giao thức nhiều bước có trạng thái trung gian **không đồng nghĩa mọi lúc đọc hai số dư sẽ thấy trạng thái giống một transaction atomic**. Phải định nghĩa rõ số dư khả dụng, số dư đang giữ, quyền rút tiền và điều gì được công bố cho người dùng trong lúc xử lý.

## 4. Hệ quả thứ hai: race condition và lost update

Giả sử tồn kho có 1 sản phẩm. Hai client đặt hàng đồng thời:

~~~text
Client A                  Client B
READ stock = 1            READ stock = 1
Thấy đủ                   Thấy đủ
WRITE stock = 0           WRITE stock = 0
CREATE order A            CREATE order B

Kết quả:
    Hai đơn được nhận, nhưng chỉ có một sản phẩm.
~~~

Vấn đề là **check rồi write không nguyên tử**. Ngay cả khi phần tạo order được tách sang bảng khác, điều kiện giữ hàng phải được bảo vệ ở một nơi có thể phân xử cạnh tranh.

### Giải pháp nguyên tử trên một bản ghi

Ví dụ MongoDB (một document tồn kho):

~~~javascript
const result = await db.collection("inventory").updateOne(
  {
    _id: sku,
    available: { $gte: quantity }
  },
  {
    $inc: { available: -quantity }
  }
);

if (result.modifiedCount !== 1) {
  throw new Error("Không đủ tồn hoặc SKU không tồn tại");
}
~~~

Điều kiện available >= quantity và phép giảm được đánh giá trong **một update document atomic**. Trong cùng một document và cùng điều kiện, hai request tranh sản phẩm cuối không thể cùng giảm thành công.

Nhưng đây **chỉ** bảo vệ bất biến tồn kho của document đó. Nó không tự bảo đảm tạo order ở document khác, không bảo vệ tác động của request retry và không biến việc gọi cổng thanh toán thành một phần transaction.

Với DynamoDB, cùng ý tưởng có thể dùng **UpdateItem** với **ConditionExpression** kiểm tra available >= quantity và **UpdateExpression** trừ quantity trên một item. Phải xác định đủ primary key, kiểu thuộc tính, phạm vi transaction và xử lý lỗi **ConditionalCheckFailedException**.

## 5. Hệ quả thứ ba: write skew dù có transaction

Một lỗi tinh vi xảy ra khi nhiều giao dịch cùng đọc một điều kiện tổng hợp rồi ghi vào **những bản ghi khác nhau**.

Ví dụ: luôn phải có ít nhất một nhân viên trực hệ thống.

~~~text
Ban đầu:
    Doctor A: onCall = true
    Doctor B: onCall = true

Transaction T1:
    Đọc cả A và B -> thấy đủ hai người trực.
    Chuyển A.onCall = false.

Transaction T2:
    Đọc cả A và B -> cũng thấy đủ hai người trực.
    Chuyển B.onCall = false.

Nếu isolation cho phép cả hai commit:
    A.onCall = false
    B.onCall = false
    -> Vi phạm bất biến.
~~~

Hai giao dịch ghi trên **hai bản ghi khác nhau**, nên một số cơ chế **snapshot isolation** có thể không phát hiện write conflict trực tiếp. Đây là **write skew**.

Không nên suy luận “database có transaction đa document” là “mọi bất biến qua nhiều document đều được bảo vệ”. Phải xác minh **mức isolation thực tế**:

- **Atomic commit:** cùng commit hoặc cùng hủy các ghi thuộc transaction.
- **Snapshot isolation:** giao dịch quan sát một snapshot và thường tránh một số xung đột, nhưng có thể vẫn xảy ra write skew.
- **Serializability:** lịch thực thi tương đương một thứ tự giao dịch tuần tự, phù hợp hơn để bảo vệ loại bất biến này khi các điều kiện/đường đọc được biểu diễn đầy đủ.
- **Strict serializability:** ngoài tính tương đương tuần tự còn bảo toàn thứ tự thời gian thực của các thao tác hoàn tất không chồng lấn.

Các lựa chọn kỹ thuật có thể là **serializable transaction**, **khóa/điều kiện trên một bản ghi chung** (ví dụ remainingOnCallCount > 1), hoặc **gom trạng thái trực ca vào aggregate phù hợp**. Cần chú ý bản ghi chung có thể thành hot spot khi số người dùng lớn.

## 6. Hệ quả thứ tư: chi phí phối hợp tăng khi vượt partition

Khi tất cả dữ liệu quyết định bất biến nằm trong một đơn vị atomic, database thường có thể xử lý tại một phạm vi khóa hẹp. Khi tách qua nhiều partition hoặc nhiều node, việc cam kết thay đổi có thể cần:

- Xác định các partition/shard tham gia.
- Đọc hoặc khóa các bản ghi liên quan dưới isolation được yêu cầu.
- Phát hiện thay đổi đồng thời, xung đột và retry.
- Phối hợp commit, ghi log phục hồi và xử lý timeout.
- Giữ trạng thái trung gian trong lúc một node chậm hoặc mất liên lạc.

Chi phí cụ thể phụ thuộc sản phẩm, engine, topology và transaction API. Không phải mọi hệ đều dùng cùng giao thức phối hợp, và không phải mọi transaction qua hai key đều chậm như nhau.

### So sánh định tính

| Phương án | Ưu điểm | Chi phí hoặc hạn chế |
| --- | --- | --- |
| Một document/item atomic | Ranh giới rõ, ít phối hợp | Có thể tạo document lớn, hot key, xung đột cao |
| Hai item cùng partition | Tổ chức dữ liệu gần nhau, có thể thuận tiện cho query | Không tự có atomic commit; phải xác minh transaction của engine |
| Nhiều partition trong một DB | Phân phối lưu lượng và kích thước | Transaction/locking/phối hợp có thể tốn thêm độ trễ |
| Nhiều Region | Có thể phục vụ người dùng phân tán địa lý | Replication, độ trễ liên vùng, xung đột và phạm vi nhất quán |
| Nhiều service/database | Mở rộng và triển khai độc lập | Không tự có transaction chung; cần workflow/compensation |
| Bản chiếu bất đồng bộ | Đọc theo query nhanh, giảm tranh chấp nguồn | Độ trễ hội tụ, replay, idempotency, reconciliation |

Phải đo **p95/p99, throughput, contention, retry, số node tham gia và thời gian giữ transaction**, đặc biệt khi có một partition nóng. Không chỉ đo trung bình của một lệnh trong môi trường thử ít cạnh tranh.

## 7. Tách dữ liệu cũng thay đổi hình ảnh mà người đọc quan sát

Giả sử thao tác chuyển 20 từ tồn kho tổng sang lượng đã giữ:

~~~text
inventory.available = 10
inventory.reserved  = 0

Bất biến:
    available + reserved = 10
~~~

Nếu hai field nằm cùng một document/item và database thực hiện một atomic update cập nhật cả hai, một đường đọc đúng phạm vi có thể nhận được trạng thái đầy đủ theo bảo đảm của hệ.

Nếu tách:

~~~text
Key A: inventory:SKU-7:available
Key B: inventory:SKU-7:reserved
~~~

và cập nhật riêng:

~~~text
T0: available = 10, reserved = 0
T1: available = 9,  reserved = 0
T2: available = 9,  reserved = 1
~~~

Một client đọc giữa T1 và T2 sẽ thấy tổng 9. Đó là **inconsistent observation** so với bất biến tổng 10 nếu ứng dụng coi hai key là một ảnh chụp tức thời. Cũng có thể đọc available ở thời điểm mới rồi reserved ở replica chậm và ghép thành ảnh chụp không tồn tại trong thực tế.

Cần phân biệt:

1. **Atomicity của ghi:** cả hai thay đổi có cùng commit không?
2. **Isolation của giao dịch đọc:** client có thể quan sát trạng thái xen giữa không?
3. **Read consistency của replica:** các đường đọc có thấy phiên bản đủ mới và tương ứng không?
4. **Consistency của bản chiếu:** search/cache/read model được cập nhật muộn bao lâu?
5. **Durability:** sau ACK và failover, những thay đổi nào còn lại?

Một hệ có atomic commit đa item nhưng cho phép đọc từ một replica chưa bắt kịp vẫn có thể khiến người dùng thấy dữ liệu cũ theo chính sách đọc. Vì vậy cần xác định **đường đọc từ đâu và hợp đồng nhất quán ra sao**, không chỉ cấu hình transaction ghi.

## 8. Phân tích ảnh hưởng khi một bất biến bị tách

Có thể dùng mẫu sau cho từng bất biến:

~~~text
Bất biến:
    [Diễn đạt bằng điều kiện có thể xác minh]

Trước khi tách:
    Các field/item tham gia:
    Đơn vị atomic:
    Tải ghi/đọc:
    Cơ chế bảo vệ:

Sau khi tách:
    Các key, item, document và partition:
    Những transaction/workflow chạm nhiều phần:
    Đường đọc dùng dữ liệu nguồn hay bản chiếu:
    Loại xung đột có thể xảy ra:
    Trạng thái trung gian có thể lộ:
    Timeout/retry có thể tạo trùng:
    Failover có thể làm mất kết quả xác nhận:
    Cơ chế sửa sai/khôi phục/đối soát:

Tiêu chí nghiệm thu:
    Correctness:
    Isolation/consistency:
    Latency p95/p99:
    Throughput:
    Recovery:
~~~

### Ma trận kiểm tra tác động

| Câu hỏi | Nếu câu trả lời là “Có” | Hành động cần phân tích |
| --- | --- | --- |
| Phải sửa nhiều item để hoàn tất một yêu cầu? | Có nguy cơ partial update | Transaction hoặc state machine |
| Hai client cùng kiểm tra rồi ghi vào nhiều phần? | Có nguy cơ race/write skew | Serializable/conditional write/khóa điều phối |
| Dữ liệu bị sao chép theo nhóm truy vấn? | Có nguy cơ read model stale | Freshness, version, idempotency, rebuild |
| Có nhiều partition/shard tham gia? | Có chi phí phối hợp | Benchmark contention và timeout |
| Có client retry khi chưa biết kết quả? | Có nguy cơ tác dụng phụ trùng | OperationId và trạng thái xử lý |
| Có nhiều Region cùng chấp nhận ghi? | Có nguy cơ conflict giữa bản sao | Xác định replication mode và cách giải quyết |
| Trạng thái trung gian ảnh hưởng trải nghiệm? | Người dùng thấy dữ liệu không khớp | Định nghĩa PENDING/RESERVED/CONFIRMED |
| Có dữ liệu giữ tạm hoặc TTL? | Hết hạn/lỗi có thể làm rò rỉ reservation | Cleanup, lease/fencing, reconciliation |
| Một key chung đang quá nóng? | Gom dữ liệu có thể hạn chế mở rộng | Chia tải có kiểm soát, escrow hoặc kiến trúc khác |

## 9. Phương án A: giữ bất biến trong một aggregate

**Aggregate** là nhóm dữ liệu có một ranh giới nhất quán được lựa chọn theo nghiệp vụ. Nếu các field thường phải thay đổi cùng nhau và kích thước có giới hạn, có thể gom chúng vào một document/item.

Ví dụ cart:

~~~json
{
  "cartId": "cart-42",
  "customerId": "customer-42",
  "version": 7,
  "items": [
    {"sku": "P-100", "qty": 2, "unitPrice": 100000},
    {"sku": "P-200", "qty": 1, "unitPrice": 50000}
  ],
  "totalAmount": 250000
}
~~~

Nếu giỏ thường được đọc và cập nhật như một đơn vị, lưu items và totalAmount trong một document có thể giúp cập nhật chúng atomically trên database hỗ trợ. Nhưng phải tính lại totalAmount đúng theo các item và xử lý hai tab sửa giỏ cùng lúc bằng version/conditional update phù hợp.

### Khi nào không nên gom?

- Aggregate tăng không giới hạn, có nguy cơ vượt giới hạn kích thước document/item.
- Nhiều request cùng cập nhật một đối tượng nóng, tạo write contention.
- Dữ liệu có vòng đời độc lập hoặc được dùng chung bởi nhiều aggregate.
- Một thay đổi nhỏ bắt buộc ghi lại cấu trúc rất lớn gây write amplification.
- Nghiệp vụ cần phân vùng hàng triệu bản ghi để phân phối tải.
- Đường đọc chỉ thường xuyên lấy một phần nhỏ nhưng aggregate lớn gây I/O không cần thiết.

Ví dụ **tồn kho tổng của SKU** không nên được copy vào mọi cart như bản ghi nguồn: hàng nghìn giỏ đều chia sẻ cùng một số tồn. Có thể cache số tồn để hiển thị, nhưng phép quyết định giữ hàng phải dựa trên nguồn có điều kiện atomic phù hợp.

**Thiết kế aggregate tốt đặt những field quyết định cùng một bất biến vào ranh giới có thể bảo vệ, đồng thời tránh biến aggregate thành điểm nghẽn khi tải tăng.**

## 10. Phương án B: conditional write trên nguồn quyết định

Không phải mọi thao tác liên quan nhiều bản ghi đều cần transaction nếu có thể **thu hẹp quyết định cạnh tranh** vào một điểm cập nhật nguyên tử.

Ví dụ giữ một vé:

~~~text
Nguồn quyết định:
    seat(eventId, seatId)
       state = AVAILABLE
       reservationId = null

Atomic conditional operation:
    IF state == AVAILABLE
       SET state = RESERVED,
           reservationId = requestId
    ELSE
       RETURN ALREADY_RESERVED
~~~

Sau khi claim seat thành công, ứng dụng có thể phát sự kiện để tạo read model cho lịch sử đơn. Cơ chế này giữ bất biến **một ghế có tối đa một claim hiệu lực** nếu điều kiện và cập nhật đúng trong một item/transaction, đồng thời định nghĩa chính xác trạng thái reservation.

Nhưng có hai vấn đề riêng:

1. **Tính toàn vẹn của claim:** requestId phải được dùng để retry có idempotency; TTL/hết hạn không được làm cấp ghế trùng khi holder cũ tiếp tục xử lý.
2. **Quan hệ với order/payment:** claim seat thành công không đồng nghĩa order và thanh toán đã xác nhận. Cần một quy trình trạng thái với bù trừ/khôi phục nếu các bước tiếp theo thất bại.

Conditional write là một **điểm phân xử cạnh tranh** hiệu quả, nhưng không thay cho transaction của mọi thay đổi khác.

## 11. Phương án C: transaction nhiều bản ghi với isolation phù hợp

Nếu những thay đổi bắt buộc phải cùng commit và cùng thuộc một database có API transaction đáp ứng phạm vi cần thiết, dùng transaction thường là lựa chọn trực tiếp.

Mã giả:

~~~text
TRANSACTION:
    IF orderId đã tồn tại:
        RETURN kết quả cũ

    UPDATE inventory
      WHERE sku = :sku AND available >= :qty
      SET available = available - :qty

    ASSERT số bản ghi đã cập nhật = 1

    INSERT reservation(
      orderId, sku, qty, status = RESERVED
    )

COMMIT
~~~

Điều kiện để diễn giải đúng:

- Transaction bao phủ **inventory và reservation** theo API cụ thể.
- Điều kiện giảm tồn được kiểm tra atomically tại lúc ghi.
- Có unique key/điều kiện tương ứng chống **orderId trùng**.
- Isolation ngăn các xung đột có thể làm sai bất biến.
- Client xử lý write conflict, timeout và retry an toàn.
- Không gọi payment gateway hoặc phát email trực tiếp trong callback transaction có thể chạy lại mà không có idempotency.

### Khác biệt tiêu biểu giữa sản phẩm

| Sản phẩm | Cần xác minh khi bảo vệ nhiều bản ghi |
| --- | --- |
| **MongoDB** | Có transaction đa document trên môi trường phù hợp; phạm vi shard, readConcern/writeConcern, session, isolation và retry. Transaction snapshot không tự biến mọi quy tắc tổng hợp thành serializable. |
| **Amazon DynamoDB** | Có TransactWriteItems/TransactGetItems trong giới hạn API và phạm vi hỗ trợ; điều kiện ghi trên item, conflict, timeout và vùng địa lý cần phân tích riêng. |
| **Cassandra** | Conditional update/LWT và batch có phạm vi/ngữ nghĩa riêng; batch nhiều partition không được mặc nhiên coi như transaction có isolation và rollback kiểu RDBMS. |
| **Redis** | Lệnh/script có atomicity theo server; MULTI/EXEC có ngữ nghĩa riêng, không rollback mọi lỗi runtime; Redis Cluster giới hạn multi-key theo hash slot, replica/failover và persistence cần xét. |
| **Elasticsearch/OpenSearch** | Bulk có thể thành công một phần; không dùng nó như transaction atomic nhiều document để bảo vệ bất biến thanh toán/tồn kho. |

Một số hệ có thể cung cấp tính năng mới trong từng bản phát hành hoặc chế độ triển khai. Đừng suy ra phạm vi transaction từ tên “NoSQL” hoặc từ câu “hỗ trợ ACID” mà thiếu **API, deployment, vùng và isolation cụ thể**.

## 12. Phương án D: điều phối qua một bản ghi chung hoặc version

Khi bất biến trải nhiều đối tượng nhưng có một **quyết định tổng** cần được kiểm soát, có thể đưa điểm phân xử vào một bản ghi chung.

Ví dụ “luôn còn ít nhất một quản trị viên”:

~~~text
organization:
    adminCount = 2
    version = 15

RemoveAdmin(user):
    atomic conditional update:
        IF adminCount > 1
           decrement adminCount
           increment version
    ghi thay đổi membership tương ứng
~~~

Nếu **giảm count** và **xóa membership** nằm ở hai đơn vị và không có transaction chung, chỉ có điều kiện ở count **chưa đủ** để bảo đảm chúng luôn khớp. Cần transaction, hoặc thiết kế workflow với reservation/compensation và trạng thái thực được diễn giải nhất quán.

Một biến thể là lưu cả **membership decision** trong cùng aggregate nhỏ, nhưng tổ chức có hàng trăm nghìn thành viên thì aggregate sẽ rất lớn. Ngoài ra, bản ghi điều phối có thể trở thành **hot key** vì mọi thay đổi admin đều tranh một version/đếm.

### Version và optimistic concurrency

Khi ứng dụng đọc nhiều field rồi quyết định thay đổi, dùng **expectedVersion** có thể phát hiện trạng thái đã bị sửa:

~~~text
READ aggregate:
    currentVersion = 15
    ...

CAS:
    chỉ ghi khi version = 15
    nếu thành công -> version = 16
    nếu xung đột -> đọc lại và tính lại
~~~

CAS giúp ngăn lost update trên **một aggregate/version token được kiểm tra nguyên tử**. Nếu hai giao dịch đọc A và B nhưng mỗi bên chỉ kiểm tra version riêng của record mà nó ghi, vẫn có thể xảy ra write skew. Phải đảm bảo **mọi thay đổi ảnh hưởng bất biến đều xung đột tại cùng điểm điều phối**, hoặc dùng isolation đủ mạnh.

## 13. Phương án E: workflow trạng thái và saga khi vượt dịch vụ

Giả sử tạo đơn gồm ba dịch vụ: **Order**, **Inventory**, **Payment**. Mỗi dịch vụ có database riêng; transaction của Order DB không tự bao phủ tồn kho hoặc thanh toán.

Một quy trình hợp lý:

~~~mermaid
flowchart TD
    A[Nhận yêu cầu tạo đơn] --> B[Order PENDING + ghi outbox]
    B --> C[Gửi ReserveRequested]
    C --> D{Inventory giữ hàng được?}
    D -->|Không| E[Order REJECTED]
    D -->|Có| F[Order RESERVED]
    F --> G[Gửi PaymentRequested]
    G --> H{Payment thành công?}
    H -->|Có| I[Order CONFIRMED]
    H -->|Không| J[Release reservation]
    J --> K[Order CANCELLED]
~~~

Bất biến được diễn giải **theo trạng thái**:

- **PENDING:** chưa xác nhận hàng và tiền.
- **RESERVED:** Inventory đã giữ hàng theo reservationId; chưa được hứa thanh toán thành công.
- **CONFIRMED:** các điều kiện bắt buộc đã được ghi nhận theo hợp đồng.
- **CANCELLED:** quy trình hủy; có thể còn hành động bù trừ đang cần retry, nên phải thể hiện trạng thái phù hợp như CANCELLING khi cần.

Đây là một kiểu **saga**: chuỗi giao dịch cục bộ với các bước tiếp theo và hành động bù trừ khi thất bại. Saga **không tạo atomic commit tức thời cho cả ba database**. Trong lúc chạy, các dịch vụ có thể ở các trạng thái khác nhau; thiết kế phải giới hạn những gì được công bố cho client và cách phục hồi khi tiến trình chết.

### Compensation khác rollback

**Rollback** của transaction cục bộ làm giao dịch chưa commit không xuất hiện như một thay đổi đã chấp nhận. **Compensation** của saga là một **thao tác nghiệp vụ mới** để đảo tác động đã ghi nhận, ví dụ thả lượng hàng đã giữ, hoàn tiền hoặc hủy đơn.

Compensation có thể gặp lỗi, đến trễ hoặc được thực hiện lại; nó phải có idempotency, cơ chế retry, giám sát và đôi khi cần xử lý thủ công. Một thanh toán đã capture cũng không phải lúc nào có thể đảo ngay bằng “xóa bản ghi”; refund có nghĩa vụ và quy trình riêng.

## 14. Outbox, event replay và đồng bộ các bản chiếu

Khi tách bất biến hoặc tạo read model sang dịch vụ khác, ứng dụng thường cần phát sự kiện. Cách viết sau có khoảng trống lỗi:

~~~text
UPDATE order status = RESERVED
PUBLISH OrderReserved to broker
~~~

Nếu database đã commit nhưng tiến trình chết trước khi publish, sự kiện bị mất. Nếu publish trước rồi database ghi thất bại, consumer có thể thấy sự kiện không tương ứng trạng thái đã commit.

**Transactional outbox** là một phương pháp để ghi thay đổi dữ liệu nguồn và bản ghi sự kiện chờ phát trong **cùng một transaction cục bộ**, khi database hỗ trợ:

~~~text
TRANSACTION tại Order DB:
    UPDATE order
    INSERT outbox(eventId, orderId, version, payload)
COMMIT

Worker:
    đọc outbox
    publish lên broker
    đánh dấu đã chuyển (hoặc dùng CDC phù hợp)
~~~

Worker có thể phát lại event nếu ACK của broker bị mất. Vì vậy consumer cần:

- **eventId** để nhận diện lặp.
- **aggregateId + version** để xử lý sự kiện đến trễ/đảo thứ tự.
- **Idempotent application** để không cập nhật hai lần.
- **Retry và dead-letter/reconciliation** cho các lỗi kéo dài.
- **Backfill/replay** để dựng lại read model khi bị mất hoặc lỗi.

Outbox giúp giảm khoảng trống giữa ghi nguồn và phát sự kiện, **không tự bảo đảm exactly-once delivery trên toàn hạ tầng**. Mục tiêu thực tế là **một hiệu ứng nghiệp vụ có thể khôi phục và chống lặp**, thường dựa vào idempotency và ràng buộc tại nơi nhận.

## 15. Timeout và idempotency khi kết quả chưa rõ

Một lỗi phân tán khó nhất là **client mất phản hồi nhưng database đã commit**:

~~~text
Client                   Database
  | Reserve(order-937)      |
  |------------------------>|
  |                  COMMIT |
  |        phản hồi mất  X  |
  |<------------------------X
  | timeout                |
  | gửi lại order-937      |
~~~

Nếu lần gửi lại thực hiện giảm stock lần nữa, hệ có thể giữ hàng hai lần cho một đơn.

Cần một **operationId/orderId** bền vững, có ý nghĩa cho cùng ý định nghiệp vụ. Có thể thiết kế:

~~~text
Reserve(orderId, sku, quantity):
    Nếu đã có kết quả của orderId:
        trả kết quả cũ.

    Nếu chưa có:
        thực hiện thay đổi có điều kiện
        ghi kết quả gắn với orderId
        commit atomically theo phạm vi được hỗ trợ.
~~~

Phần “đã có?” và “ghi kết quả” không nên là hai bước rời rạc không được bảo vệ nếu chúng quyết định bất biến. Khi không thể atomically thay đổi toàn bộ dữ liệu, dùng ledger/trạng thái processing, unique condition, workflow có thể phục hồi và reconciliation.

**Retry policy** cũng phải khác giữa các trường hợp:

| Kết quả | Diễn giải | Hướng xử lý |
| --- | --- | --- |
| Condition failed | Server xác định điều kiện không còn đúng | Trả từ chối hợp lệ hoặc đọc lại theo chính sách |
| Transaction conflict | Có xung đột đồng thời | Retry giới hạn với backoff nếu thao tác idempotent |
| Timeout sau khi gửi | Kết quả không rõ | Tra cứu theo operationId, không tự trừ/cộng lần nữa |
| Lỗi trước khi gửi | Chưa thực thi thao tác | Có thể retry có giới hạn |
| Compensation failed | Hành động bù trừ chưa hoàn tất | Giữ trạng thái pending, retry, cảnh báo và đối soát |
| Event nhận trùng | Cùng eventId đã xử lý | Bỏ qua hoặc trả trạng thái đã hoàn tất theo hợp đồng |

## 16. Tránh điểm nghẽn khi gom dữ liệu để giữ bất biến

Đưa mọi thao tác vào một item hoặc một bản ghi chung giúp dễ kiểm soát concurrency nhưng có thể tạo **hot aggregate**.

Ví dụ một nền tảng có hàng triệu request cùng giảm quota toàn hệ. Nếu toàn bộ cùng update một key **global:quota:remaining**, hệ có thể bị giới hạn bởi thông lượng cập nhật một key/node. Chia quota thành nhiều partition có thể tăng tải, nhưng khi đó bất biến **tổng quota không âm** trở nên khó bảo vệ.

Một số phương án chuyên biệt:

- **Escrow allocation:** phân bổ trước quota/tồn kho cho từng partition; mỗi partition chỉ cấp phát trong phần hạn mức đã được giao. Chuyển hạn mức giữa các partition cần giao thức bảo đảm và đối soát.
- **Reservation token:** cấp trước các token hữu hạn đại diện quyền sử dụng tài nguyên; mỗi token được claim đúng một lần. Cần xử lý token hết hạn, mất phản hồi và tái cấp phát.
- **Ledger + batch settlement:** ghi các thay đổi có định danh duy nhất và xử lý đối soát/tổng hợp theo workflow có kiểm chứng.
- **Shard theo phạm vi nghiệp vụ tự nhiên:** nếu tồn kho theo kho hàng độc lập, bảo vệ từng kho riêng và xác định quy tắc phân phối hàng giữa kho.
- **Đổi hợp đồng nghiệp vụ:** cho phép waitlist hoặc trạng thái PENDING thay vì hứa chắc “thành công ngay” khi không thể phân xử nhanh dưới tải cực lớn.

Escrow và token không phải một phép cộng counter tùy ý. Nếu tổng quyền được cấp cho các shard vượt tài nguyên thực, mô hình vẫn oversell. Phải duy trì bất biến **tổng hạn mức đã phân bổ và chưa phân bổ không vượt nguồn thực**, đặc biệt khi retry, partition fail và recovery.

## 17. Kịch bản nhiều Region và xung đột ghi

Giả sử hệ đặt hàng phục vụ đồng thời ở Region A và Region B. Mỗi Region có bản sao tồn kho = 1 và đều chấp nhận một đơn trong lúc mất liên lạc. Sau khi kết nối lại, một cơ chế replication dùng chính sách “last writer wins” có thể chọn một giá trị cuối cùng cho stock, nhưng **không tự hủy đơn đã xác nhận ở Region còn lại**. Bất biến không oversell bị vi phạm ở tầng nghiệp vụ dù dữ liệu cuối cùng hội tụ.

~~~text
Region A: stock = 1 -> reserve A -> stock = 0
Region B: stock = 1 -> reserve B -> stock = 0

Cả A và B đều phản hồi thành công.

Replication hội tụ về stock = 0,
nhưng thực tế đã xác nhận hai reservation.
~~~

Các lựa chọn:

- Chỉ chấp nhận ghi quyết định tồn kho từ **một vùng chủ** hoặc một dịch vụ điều phối có thể chịu được yêu cầu consistency tương ứng.
- Dùng cơ chế **global transaction/consensus** thực sự có trong sản phẩm và deployment, với độ trễ/availability được chấp nhận.
- **Phân bổ quota/tồn kho theo Region** sao cho mỗi Region chỉ claim từ hạn mức riêng đã được cấp không trùng.
- Giữ yêu cầu ở **PENDING** khi mất liên lạc thay vì xác nhận ngay, rồi đối soát theo chính sách.

Không thể kết luận “database có global replication nên transaction cũng global” hoặc “strong read tại Region A nghĩa là mọi lần đọc ở Region B cùng thời điểm đều mạnh”. Phải đọc đúng chế độ replication và phạm vi bảo đảm của sản phẩm.

## 18. Đừng nhầm ACID consistency, CAP consistency và dữ liệu hội tụ

Có ít nhất ba ngữ cảnh của chữ “consistency”:

1. **ACID consistency:** các ràng buộc/bất biến được giao dịch bảo toàn theo luật của hệ thống.
2. **CAP consistency:** consistency theo nghĩa linearizability khi xét các hệ phân tán dưới phân hoạch mạng.
3. **Replica/read consistency:** các bảo đảm như strong read, read-your-writes, causal consistency hoặc eventual consistency tùy API.

Không thể lấy chữ “C” trong ACID để khẳng định hệ có linearizable read xuyên Region. Cũng không thể lấy tính cuối cùng hội tụ của replica để đảm bảo bất biến “không hai người cùng lấy vé cuối”.

Ví dụ:

- Một giao dịch đa item có thể commit nguyên tử nhưng một read model/search index bất đồng bộ vẫn trễ.
- Một single-key conditional update có thể linearizable trong phạm vi key nhưng một workflow nhiều key vẫn thiếu atomic commit.
- Một hệ eventual consistency có thể phù hợp cho dashboard; nhưng quyết định thanh toán cần bảo đảm mạnh hơn tại nguồn.

Khi viết tài liệu kiến trúc, hãy gọi đúng **atomic boundary**, **isolation level**, **read guarantee**, **write acknowledgement** và **replication scope** thay vì dùng một chữ “nhất quán” chung.

## 19. Ví dụ tổng hợp: tách tồn kho và đơn hàng ra hai partition

### 19.1. Yêu cầu ban đầu

~~~text
Khách đặt SKU-X, quantity = 1.

Bất biến:
    available(SKU-X) >= 0
    Một orderId chỉ giữ hàng đúng một lần.
    Khi trả CONFIRMED, phải có reservation hiệu lực.
~~~

### 19.2. Phương án chưa an toàn

~~~text
1. READ inventory(SKU-X)
2. Nếu available > 0: WRITE inventory.available -= 1
3. INSERT order(orderId, status=CONFIRMED)
~~~

Lỗi có thể xảy ra:

- Hai request cùng đọc số tồn cũ, gây oversell.
- Ghi inventory thành công, tạo order thất bại.
- Tạo order thành công nhưng client timeout rồi retry giảm tồn lần nữa.
- Một phần replica thấy status CONFIRMED trước khi inventory mới hội tụ.
- Mất sự kiện cập nhật đọc theo customer sau khi order đã commit.

### 19.3. Phương án dùng transaction nếu được hỗ trợ

~~~text
TRANSACTION:
    Kiểm tra orderId chưa tồn tại.
    Conditional decrement inventory nếu đủ.
    Tạo reservation gắn orderId.
COMMIT

Chỉ sau commit:
    trả RESERVED.
~~~

Nếu thanh toán cũng nằm ngoài database này, không được trả **CONFIRMED** chỉ vì đã giữ hàng; cần workflow tiếp theo.

### 19.4. Phương án dùng reservation workflow

~~~mermaid
flowchart LR
    A[Request orderId] --> B[Order PENDING]
    B --> C[Reserve stock có điều kiện]
    C --> D{Reservation hợp lệ?}
    D -->|Không| E[Order REJECTED]
    D -->|Có| F[Order RESERVED]
    F --> G[Thanh toán]
    G --> H{Thành công?}
    H -->|Có| I[Order CONFIRMED]
    H -->|Không| J[Release reservation]
    J --> K[Order CANCELLED]
~~~

Khi tách dịch vụ, phải có operationId, trạng thái trung gian, outbox/event retry, idempotent consumer và quá trình giải quyết reservation treo. Với bước release, cần đảm bảo **chỉ trả lại lượng đã giữ một lần**, không cộng kho nhiều lần nếu message release đến trùng.

### 19.5. Quy định câu trả lời API

| Trạng thái | Điều client được quyền kết luận |
| --- | --- |
| PENDING | Đã nhận yêu cầu, chưa xác nhận giữ hàng |
| RESERVED | Giữ hàng đã được nguồn tồn kho chấp nhận |
| PAYMENT_PENDING | Chưa xác định hoàn thành thanh toán |
| CONFIRMED | Đã đạt các điều kiện xác nhận nghiệp vụ |
| REJECTED | Không thể đáp ứng yêu cầu, không có reservation hiệu lực |
| CANCELLING | Đang hoàn tất các bước bù trừ |
| CANCELLED | Đã đạt điều kiện hủy theo hợp đồng |

Tên trạng thái có thể khác nhau theo dự án, nhưng ý nghĩa phải được định nghĩa để client **không nhầm việc gửi message thành hoàn tất giao dịch**.

## 20. Đánh giá ảnh hưởng tới hiệu năng và khả năng mở rộng

Tách dữ liệu có thể cải thiện khả năng phân tán tải nhưng cũng làm mỗi thao tác chạm nhiều node. Cần đo **tải thực tế** và đúng loại thao tác:

| Chỉ số | Khi bất biến nằm trong một aggregate | Khi tách nhiều partition/bản ghi |
| --- | --- | --- |
| Số đơn vị phải cập nhật | Thường ít | Thường nhiều hơn |
| Khả năng phân tán ghi | Có thể bị hot aggregate | Có thể tăng nhờ chia partition |
| Phối hợp để giữ bất biến | Có thể dùng conditional atomic update | Có thể cần transaction/saga/điều phối |
| Chi phí network | Có thể ít round trip | Tăng nếu nhiều node/dịch vụ |
| Khả năng đọc nhất quán | Dễ xác định ranh giới đọc hơn | Có thể cần snapshot/phiên/đường nguồn |
| Failure modes | Lỗi ở một thao tác | Có thể partial update, outbox lag, compensation |
| Retry/idempotency | Vẫn cần khi hiệu ứng không idempotent | Càng quan trọng khi nhiều bước |
| Vận hành | Ít dữ liệu lặp | Cần reconciliation, dashboard workflow và backfill |
| Storage/read models | Ít bản sao | Có thể nhiều projection, index và ledger |

Không phải mọi transaction đa partition đều chậm hơn mọi single-item update trong mọi điều kiện. So sánh có ý nghĩa khi giữ nguyên **số request, phân bố khóa, kích thước dữ liệu, consistency và độ đúng kết quả**.

### Những workload cần tách riêng khi đo

- Nhiều request tranh **cùng một SKU** chỉ còn một đơn vị.
- Nhiều request đọc/ghi các SKU độc lập.
- Một customer/store/tenant lớn tạo hot partition.
- Retry khi client mất ACK ngay sau commit.
- Failover trong lúc có transaction hoặc saga ở trạng thái trung gian.
- Cập nhật read model theo event đến trễ/đến trùng.
- Tăng số partition/shard/Region và thay đổi latency mạng.
- Quá trình restore/backfill tạo lại bảng phụ/ledger.
- Tải dài hạn có TTL, tombstone, compaction và backlog.

Một benchmark chỉ chạy **đọc theo ID** không chứng minh một thiết kế giữ bất biến xuyên nhiều partition hoạt động đúng dưới tranh chấp.

## 21. Các bài kiểm thử correctness bắt buộc

### 21.1. Oversell

Cho stock ban đầu = 1, gửi 200 request giữ hàng đồng thời với **orderId riêng**.

Kỳ vọng:
- Có tối đa một reservation hiệu lực.
- Không có available âm.
- Không có order CONFIRMED thiếu reservation.
- Các request từ chối được phân loại đúng, không bị xem là lỗi hệ thống nếu nghiệp vụ từ chối hợp lệ.

### 21.2. Timeout sau khi commit

Cho database xử lý xong, nhưng cố ý làm mất phản hồi tới client. Client gửi lại **cùng orderId**.

Kỳ vọng:
- Cùng một ý định chỉ tạo một hiệu ứng nghiệp vụ.
- Client có thể tra cứu kết quả.
- Không bị trừ tồn hoặc ghi tiền lần hai.

### 21.3. Lỗi giữa hai bản ghi

Cố ý cho bước ghi đầu thành công, bước thứ hai lỗi.

Kỳ vọng:
- Với transaction atomic, không thấy một phần đã commit trái hợp đồng.
- Với saga, hệ phản ánh trạng thái trung gian, có retry/compensation và cuối cùng đạt một trạng thái hợp lệ hoặc phát cảnh báo rõ ràng.

### 21.4. Write skew

Khởi tạo hai người quản trị đều đang hoạt động, cho hai request đồng thời gỡ mỗi người.

Kỳ vọng:
- Nếu bất biến là **phải còn ít nhất một admin**, ít nhất một thao tác phải bị từ chối hoặc chuyển sang trạng thái chờ.
- Không thể kết luận an toàn chỉ vì mỗi transaction ghi một record khác nhau.

### 21.5. Event đảo thứ tự và trùng lặp

Phát version v5 trước v4 rồi phát lại v5.

Kỳ vọng:
- Read model không lùi về phiên bản cũ.
- Không đếm trùng tiền, tồn kho hoặc reservation.
- Có cơ chế replay khi mất kết nối.

### 21.6. Mất node và Region

Tiêm hỏng node/leader hoặc mất liên lạc theo kịch bản được hỗ trợ.

Kỳ vọng:
- Hệ có hành vi xác định khi không thể phân xử cập nhật.
- Không hứa thành công nếu chưa đạt điều kiện business.
- Ghi đã xác nhận được duy trì theo chính sách durability đã chọn; những trạng thái chưa rõ có cách tra cứu/đối soát.

## 22. Bộ chỉ số đo và điều kiện nghiệm thu

Một bản thiết kế cần nêu **mục tiêu về tính đúng và vận hành**, tránh khẳng định không có lỗi chỉ từ một kết quả load test.

Ví dụ với hệ đặt hàng giả lập:

| Mã | Tiêu chí | Phép đo |
| --- | --- | --- |
| AC-01 | Không có trường hợp stock âm | Đối soát toàn bộ SKU sau kiểm thử cạnh tranh |
| AC-02 | Một orderId tạo tối đa một reservation hiệu lực | Đối soát unique operationId khi retry |
| AC-03 | Không có CONFIRMED thiếu điều kiện nghiệp vụ | Kiểm tra trạng thái order, stock và payment |
| AC-04 | Transaction/conditional update có p99 trong ngưỡng đã duyệt | Load test đúng phân bố hot key |
| AC-05 | Saga treo vượt thời hạn được phát hiện và khôi phục | Fault injection, metric pending age, alert |
| AC-06 | Read model hội tụ trong freshness SLO | Version/time lag đo trên các đường đọc |
| AC-07 | Có thể khôi phục sau lỗi node theo RTO/RPO đã chọn | Failure drill và đối soát dữ liệu |
| AC-08 | Dư địa tài nguyên khi tăng tải hoặc thêm partition | CPU, memory, I/O, network, conflict/retry |

Ví dụ ngưỡng p99 **≤ 250 ms** hay độ trễ bản chiếu **≤ 5 giây** chỉ là **giả định để minh họa**. Dự án phải chọn ngưỡng theo trải nghiệm và ngân sách của mình, rồi chạy trên dataset và topology đại diện.

Cần phân biệt:

- **Correctness violation:** vi phạm bất biến. Không được “bù” bằng p95 nhanh.
- **Infrastructure error:** timeout, mất kết nối, retry quá mức, transaction abort vì lỗi hạ tầng.
- **Business rejection:** hết hàng hoặc thiếu điều kiện hợp lệ; có thể là kết quả đúng.
- **Incomplete result:** saga chưa hoàn tất, bản chiếu chưa bắt kịp, timeout không rõ kết quả.

### Quan sát và đối soát

Những metric hữu ích:

~~~text
reservation_conflicts_total
duplicate_operation_ids_total
stock_invariant_violations_total
transaction_aborts_total
transaction_retry_count
pending_sagas_by_age
compensation_failures_total
outbox_backlog
projection_freshness_seconds
replica_lag
hot_partition_latency_p99
reconciliation_mismatches
~~~

Tên metric chỉ mang tính minh họa. Có thể dùng dashboard để nhận biết bất biến đã bị phá vỡ, các workflow bị treo, độ trễ đọc và điểm nghẽn contention. Đối soát định kỳ từ **nguồn dữ liệu chuẩn** giúp tìm lỗi hiếm không lộ qua status API.

## 23. Bài tập thiết kế: chuyển quyền quản trị giữa hai người

Một tổ chức có hai admin **A và B**. Yêu cầu: **không có thời điểm nào tổ chức ở trạng thái đã xác nhận mà không còn admin**, đồng thời có thể chuyển quyền admin từ A sang C.

### Thiết kế 1 — Mỗi người một record

~~~text
member:A { role: ADMIN }
member:B { role: ADMIN }
member:C { role: MEMBER }
~~~

Hai request đồng thời:
- Request X hạ A khỏi ADMIN vì còn B.
- Request Y hạ B khỏi ADMIN vì còn A.

Nếu hai request cùng đọc trạng thái cũ và ghi vào hai record khác nhau, có thể tạo write skew. Học viên cần đề xuất:
- Transaction serializable nếu sản phẩm hỗ trợ phù hợp.
- Một điểm điều phối có CAS/version, với toàn bộ thay đổi ảnh hưởng invariant đều phải đi qua điểm này.
- Một aggregate membership có giới hạn; đánh giá tranh chấp và kích thước.

### Thiết kế 2 — Một document nhóm admin

~~~json
{
  "organizationId": "org-1",
  "adminIds": ["A", "B"],
  "version": 12
}
~~~

Khi bỏ A, conditional update kiểm tra adminIds còn ít nhất một người và thay đổi trong một document atomic phù hợp. Nhưng với tổ chức cực lớn, document có thể tăng vượt giới hạn và trở thành hot aggregate. Nếu membership còn được lưu độc lập để truy vấn theo user, cần cách đồng bộ không làm sai quyền trong thời gian chờ.

### Những câu hỏi phải trả lời

1. Bất biến áp dụng trên **trạng thái đã commit** hay cả những trạng thái workflow chưa hoàn tất?
2. Có bao nhiêu người có thể sửa quyền cùng lúc?
3. Nơi nào là nguồn sự thật để kiểm tra quyền truy cập tức thời?
4. Nếu cập nhật nguồn thành công nhưng read model chưa theo kịp, điều gì phải được kiểm tra lại trước khi cấp quyền?
5. Khi một transaction timeout, làm sao xác minh request có thành công?
6. Nếu dùng version, mọi đường thay đổi membership có buộc phải đi qua cùng version token không?
7. Có thể phát hiện/xử lý quyền bị lệch sau restore hoặc event replay không?

Bài tập cho thấy **giữ bất biến** và **tối ưu đọc theo user/organization** là hai mục tiêu cần kết nối bằng một thiết kế cụ thể.

## 24. Quy trình ra quyết định thực tế

~~~mermaid
flowchart TD
    A[Viết bất biến có thể kiểm chứng] --> B[Xác định tất cả record/partition tham gia]
    B --> C{Có thể gom quyết định vào một đơn vị atomic?}
    C -->|Có| D[Atomic conditional update / aggregate]
    C -->|Không| E{Database có transaction phù hợp?}
    E -->|Có| F[Transaction + isolation + retry]
    E -->|Không| G[Workflow / saga / ledger / escrow]
    D --> H[Thiết kế idempotency, read guarantee và durability]
    F --> H
    G --> H
    H --> I[Thử cạnh tranh, timeout, partial failure, failover]
    I --> J[Đo hiệu năng, reconciliation và chi phí]
    J --> K[Ghi hợp đồng theo sản phẩm/API/topology]
~~~

Thứ tự nên áp dụng:

1. **Viết bất biến chính xác:** điều kiện nào không thể sai, điều kiện nào được hội tụ và khoảng thời gian tối đa?
2. **Vẽ ranh giới dữ liệu:** những bản ghi/partition/dịch vụ nào tham gia một quyết định?
3. **Chọn điểm bảo vệ:** một item/document, conditional update, transaction, token, ledger hoặc workflow?
4. **Xác định isolation:** tránh lost update, write skew và quan sát trạng thái xen giữa bằng bảo đảm cụ thể.
5. **Thiết kế đường lỗi trước:** timeout, retry, gửi trùng, event lộn thứ tự, mất node và bù trừ thất bại.
6. **Quy định phản hồi client:** PENDING, RESERVED, CONFIRMED có ý nghĩa gì; khi nào có thể tuyên bố thành công?
7. **Đo dưới workload thật:** hot key, phân vùng lớn, p95/p99, số transaction abort, backlog và số read model.
8. **Dựng cơ chế đối soát:** có thể phát hiện và khôi phục dữ liệu lệch sau sự cố hoặc replay.
9. **Ghi rõ hợp đồng từng hệ:** API, phiên bản, partition/transaction scope, read/write concern, replication và durability.

## Kết luận

**Tách một bất biến qua nhiều bản ghi hoặc phân vùng làm thay đổi ranh giới bảo vệ tính đúng đắn.** Các thao tác atomic riêng lẻ có thể không ngăn partial update, lost update, write skew, quan sát trạng thái trung gian hay tác dụng phụ bị lặp khi retry. Nhiều partition và dịch vụ còn làm tăng chi phí phối hợp, nguy cơ timeout, độ trễ hội tụ và công việc phục hồi.

Cách xử lý phụ thuộc vào **bất biến cụ thể và bảo đảm thực tế của database**: giữ quyết định trong một aggregate hợp lý, dùng conditional write, transaction đa bản ghi với isolation phù hợp, hoặc thiết kế ledger/reservation/saga có idempotency và đối soát khi vượt ranh giới giao dịch. Một mô hình chỉ thật sự an toàn khi có bằng chứng rằng **dưới cạnh tranh và sự cố, hệ vẫn giữ đúng điều được hứa với người dùng**.
