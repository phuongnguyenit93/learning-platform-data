# Tính nguyên tử của một lệnh, một khóa, một tài liệu hoặc một phân vùng

Khi một ứng dụng ghi dữ liệu NoSQL, câu hỏi quan trọng không chỉ là **lệnh có chạy thành công hay không** mà còn là **những thay đổi nào bắt buộc phải cùng xảy ra**. Nếu một thao tác cập nhật số lượng hàng tồn, số đã giữ và phiên bản bản ghi, có được phép nhìn thấy tình trạng chỉ một phần trong ba trường đã đổi không? Nếu một yêu cầu đồng thời sửa hai document, liệu hai document ấy có thể ở trạng thái khác nhau khi một bước thất bại? Nếu client mất kết nối sau khi database đã ghi, làm sao biết có nên gửi lại lệnh?

Những câu hỏi đó liên quan trực tiếp đến **tính nguyên tử (atomicity)** — một trong các thuộc tính quan trọng khi thiết kế giao dịch. Tuy nhiên, NoSQL không có một ranh giới nguyên tử chung cho mọi sản phẩm. Có hệ bảo đảm thao tác trên **một key**, có hệ trên **một document/item**, có hệ cung cấp **đơn vị hàng/partition** với điều kiện cụ thể, và nhiều hệ còn hỗ trợ **transaction nhiều bản ghi** khi sử dụng đúng API, cấu hình và phạm vi được phép.

Bài học trình bày cách xác định **phạm vi bảo đảm**, không suy luận từ tên lệnh hoặc hình dạng dữ liệu. Ví dụ dùng MongoDB, Redis, DynamoDB, Cassandra và Bigtable; đồng thời phân tích ghi đồng thời, batch, điều kiện ghi, nhất quán, idempotency, workflow nhiều bước và kiểm thử lỗi. Cú pháp minh họa cần được đối chiếu với phiên bản engine và driver đang dùng khi triển khai thực tế.

## 1. Nguyên tử nghĩa là “cùng xảy ra hoặc không xảy ra” trong một phạm vi

Giả sử bản ghi tồn kho:

~~~javascript
{
  _id: "BOOK-01",
  tenantId: "shop-a",
  available: 10,
  reserved: 0,
  version: 1
}
~~~

Khi giữ 3 cuốn sách, trạng thái hợp lệ tiếp theo là:

~~~javascript
{
  _id: "BOOK-01",
  tenantId: "shop-a",
  available: 7,
  reserved: 3,
  version: 2
}
~~~

Nếu nghiệp vụ yêu cầu ba trường **available**, **reserved** và **version** chuyển cùng nhau, trạng thái sau không được công nhận là một kết quả cập nhật hợp lệ:

~~~javascript
{
  _id: "BOOK-01",
  available: 7,
  reserved: 0,
  version: 1
}
~~~

**Tính nguyên tử** của thao tác trên bản ghi tồn kho nghĩa là một lần cập nhật hợp lệ có thể thay đổi các trường này như **một đơn vị logic**. Nếu thao tác không được áp dụng, không có phần thay đổi dở dang của chính thao tác ấy được công nhận.

Tuy nhiên, phải phân biệt ba vấn đề:

1. **Phạm vi:** những field, key, document, item hoặc row nào nằm trong đơn vị nguyên tử?
2. **Điều kiện:** thao tác có được phép thực hiện trên trạng thái hiện tại không? Ví dụ available phải lớn hơn hoặc bằng 3.
3. **Kết quả:** server đã áp dụng thay đổi hay chưa; client có nhận được phản hồi hay không?

Chỉ nói **“database có atomic write”** chưa trả lời đủ ba câu hỏi.

### Một biểu thức bất biến

Nếu kho không cho phép tồn khả dụng âm:

\[
\text{available} \ge 0
\]

Nếu mô hình định nghĩa tổng hàng có thể bán trong giai đoạn đó là available cộng reserved:

\[
\text{available} + \text{reserved} = \text{sellableStock}
\]

thì phép giữ hàng phải bảo vệ các điều kiện đã xác nhận **ngay trong thao tác ghi hoặc transaction phù hợp**. Công thức thứ hai chỉ đúng nếu nghiệp vụ đã định nghĩa sellableStock, chưa xét hàng hỏng, nhập mới, hoàn trả hoặc các trạng thái bổ sung. **Bất biến do nghiệp vụ xác định; atomicity là một công cụ giúp bảo vệ bất biến ấy.**

## 2. Đừng nhầm atomicity với isolation, consistency và durability

Trong ACID, bốn thuộc tính có vai trò khác nhau:

| Thuộc tính | Câu hỏi | Ví dụ |
|---|---|---|
| **Atomicity** | Những thay đổi trong một giao dịch/đơn vị có cùng thành công hoặc cùng không có hiệu lực không? | Giảm available và tăng reserved trên một document |
| **Consistency** | Giao dịch có đưa dữ liệu từ trạng thái hợp lệ sang trạng thái hợp lệ theo ràng buộc hệ thống không? | Tồn kho không âm, ID duy nhất, trạng thái hợp lệ |
| **Isolation** | Các thao tác đồng thời được nhìn nhận và tương tác với nhau như thế nào? | Hai khách cùng giữ hàng không cùng được duyệt vượt tồn |
| **Durability** | Khi hệ xác nhận thành công, dữ liệu sống sót thế nào trước lỗi và khởi động lại theo mức bảo đảm đã cấu hình? | Ghi đã được journal/replicate theo write concern thích hợp |

Một thao tác có thể **nguyên tử nhưng vẫn sai nghiệp vụ**. Ví dụ thay toàn bộ stock từ 10 thành -3 bằng một lệnh nguyên tử vẫn vi phạm bất biến stock không âm nếu không có kiểm tra.

Một thao tác có thể **nguyên tử trên một document** nhưng **không bảo đảm toàn bộ hai document cùng thay đổi**. Một transaction có thể nguyên tử trên nhiều document nhưng nếu isolation không đủ cho bất biến phức tạp, vẫn phải thiết kế điều kiện/khóa/constraint tương ứng.

Một lệnh đã thực thi nguyên tử trên node đang xử lý **không tự nói rằng đã được lưu bền vững trên mọi replica**. Durability và replication cần xem riêng.

## 3. “Một lệnh” không đồng nghĩa “một đơn vị nguyên tử”

Hình thức API có thể gây nhầm lẫn:

~~~text
Một lời gọi API:
  updateOne(...)
  updateMany(...)
  bulkWrite(...)
  ExecuteBatch(...)
  pipeline(...)
~~~

Đây đều là **một lần gọi ở phía ứng dụng**, nhưng số bản ghi bị tác động và bảo đảm nguyên tử có thể khác.

| Cách gọi | Bề ngoài | Câu hỏi phải hỏi |
|---|---|---|
| Update một document | Một command | Toàn bộ những field của document được sửa trong một atomic update không? |
| Update nhiều document | Một command | Các document có được commit cùng nhau không hay mỗi document nguyên tử riêng? |
| Ghi một batch | Một request | Batch chỉ giảm round trip hay còn có transaction/isolation? |
| Pipeline nhiều lệnh | Một lần gửi mạng | Các lệnh có thể bị chen vào hoặc thất bại một phần không? |
| Giao dịch nhiều item | Một API transaction | Phạm vi item, điều kiện, hạn mức và kết quả commit ra sao? |
| Một key chứa JSON | Một key | Ghi toàn value có nguyên tử nhưng logic đọc–sửa–ghi có bị race không? |
| Nhiều row cùng partition | Một nhóm lưu trữ | Engine bảo đảm gì với từng mutation, batch, đọc đồng thời và conditional write? |

**Đơn vị lệnh ở client**, **đơn vị lưu trữ**, **đơn vị ghi nguyên tử** và **đơn vị transaction** là bốn khái niệm có thể trùng nhưng không nhất thiết trùng.

~~~mermaid
flowchart TD
    A["Ứng dụng gửi một lời gọi"] --> B{"Lời gọi chạm bao nhiêu đơn vị lưu?"}
    B -->|"Một key/document/item"| C["Xem bảo đảm single-unit write"]
    B -->|"Nhiều key/document/item"| D["Xem có transaction/multi-item guarantee không"]
    C --> E["Kiểm tra điều kiện ghi và concurrence"]
    D --> F{"Có bảo đảm all-or-nothing phù hợp?"}
    F -->|"Có"| E
    F -->|"Không"| G["Thiết kế trạng thái trung gian / saga / bù / đối soát"]
    E --> H["Kiểm tra retry, ack, durability"]
    G --> H
~~~

## 4. Ranh giới nguyên tử phải được ghi trong thiết kế

Một cách hữu ích là mô tả mỗi thao tác bằng **bốn cột**:

| Thao tác nghiệp vụ | Đơn vị dữ liệu phải thay đổi cùng nhau | Cơ chế ứng viên | Phần nằm ngoài bảo đảm |
|---|---|---|---|
| Sửa tên và ngôn ngữ của một profile | Một profile document/item | Atomic update trên document/item | Cache profile ở dịch vụ khác |
| Giảm tồn và tăng reserved một SKU | Một inventory record | Conditional atomic update | Order record nằm ở collection khác |
| Đánh dấu một ghế đã được giữ | Một seat item/claim key | Conditional create/CAS/unique constraint | Payment bên ngoài |
| Tạo order và giữ hai SKU | Một order + hai inventory records | Transaction nhiều record hoặc reservation workflow | Cổng thanh toán ở dịch vụ khác |
| Cập nhật bảng theo khách và bảng theo trạng thái | Nhiều read models | Transaction khi hỗ trợ hoặc event/outbox | Dữ liệu dẫn xuất có thể hội tụ sau |
| Gửi email sau khi thanh toán | Database + hệ email | Durable event/outbox và consumer idempotent | Không có rollback email theo DB transaction |

**Câu hỏi thiết kế:** nếu mất điện hoặc có hai request ngay giữa quy trình, trạng thái dở dang nào được phép tồn tại? Nếu không được phép, cần đưa những thay đổi vào một đơn vị bảo đảm phù hợp hoặc đổi cách mô hình hóa.

## 5. MongoDB: atomic write trên một document

MongoDB bảo đảm tính nguyên tử của **một thao tác ghi trên một document**, ngay cả khi lệnh sửa nhiều field hoặc nhiều phần của document ấy. Vì vậy, một inventory document chứa cả available và reserved là một ví dụ tự nhiên.

~~~javascript
db.inventory.insertOne({
  _id: "BOOK-01",
  tenantId: "shop-a",
  available: 10,
  reserved: 0,
  version: 1
});
~~~

Giữ 3 cuốn chỉ khi available đủ:

~~~javascript
const requested = 3;

if (!Number.isSafeInteger(requested) || requested <= 0) {
  throw new Error("Quantity must be a positive integer");
}

const result = db.inventory.updateOne(
  {
    _id: "BOOK-01",
    tenantId: "shop-a",
    available: { $gte: requested }
  },
  {
    $inc: {
      available: -requested,
      reserved: requested,
      version: 1
    }
  }
);

if (result.matchedCount !== 1) {
  print("Không đủ tồn, sai tenant hoặc item không tồn tại");
}
~~~

Trong lần ghi này, **ba phép $inc thuộc cùng một update trên một document**. Các field không chuyển qua những trạng thái đã cập nhật dở dang theo logic của chính lệnh đó.

Quan trọng hơn, điều kiện **available >= requested** nằm trong filter của thao tác ghi. Nhờ vậy khi hai request tranh chấp, database đánh giá điều kiện trên trạng thái liên quan đến chính thao tác cập nhật, thay vì dựa vào một GET đã cũ.

Nếu kết quả **matchedCount = 0**, không có nghĩa chắc chắn “hết hàng”: có thể không tồn tại document hoặc tenant không khớp. API cần phân loại và trả phản hồi đúng theo quyền và nghiệp vụ.

### Vì sao hai lệnh $inc độc lập không tương đương?

Phản ví dụ:

~~~javascript
// Hai thao tác ghi độc lập:
db.inventory.updateOne(
  { _id: "BOOK-01" },
  { $inc: { available: -3 } }
);

db.inventory.updateOne(
  { _id: "BOOK-01" },
  { $inc: { reserved: 3 } }
);
~~~

Nếu ứng dụng chết hoặc lệnh thứ hai thất bại sau lệnh đầu, dữ liệu có thể còn available giảm nhưng reserved chưa tăng. **Hai lần updateOne không tự tạo một transaction chung** chỉ vì cùng document và chạy liền nhau.

Để bảo vệ hai field như một thay đổi, đưa cả hai vào **cùng updateOne** với điều kiện phù hợp.

## 6. Atomicity trên document không có nghĩa mọi phép tính từ client đều an toàn

Giả sử ban đầu available = 5, hai khách cùng đặt 4:

~~~text
Request A                        Request B
---------                        ---------
GET available = 5               GET available = 5
Tính 5 - 4 = 1                  Tính 5 - 4 = 1
SET available = 1               SET available = 1
~~~

Mỗi **SET** riêng có thể là một thao tác ghi nguyên tử, nhưng cả hai đều ghi **1**. Nếu cả hai API trả “giữ 4 cuốn thành công”, hệ thống đã bán vượt khả năng dù trường available không âm. Đây là **lost update và sai bất biến do đọc–tính–ghi không được bảo vệ**.

Thay bằng:

~~~javascript
db.inventory.updateOne(
  { _id: "BOOK-01", available: { $gte: 4 } },
  { $inc: { available: -4 } }
);
~~~

Khi available ban đầu bằng 5, chỉ một yêu cầu giảm được 4; yêu cầu còn lại không còn đáp ứng điều kiện.

Hai bài học:

- **Ghi một document nguyên tử** là điều kiện tốt nhưng không tự giải quyết cách client lấy giá trị dùng để ghi.
- **Atomic read–modify–write hoặc conditional update** là cơ chế cần khi quyết định phụ thuộc trạng thái đang thay đổi.

Không nên chỉ thêm khóa mutex trong một process API: nhiều instance service khác vẫn có thể ghi cùng dữ liệu. Phạm vi bảo vệ phải bao trùm **mọi writer**.

## 7. MongoDB: updateMany không biến nhiều document thành một transaction

Giả sử cần tăng ưu đãi cho hàng trăm sản phẩm:

~~~javascript
db.products.updateMany(
  { tenantId: "shop-a", categoryId: "stationery" },
  { $set: { campaignId: "campaign-2026" } }
);
~~~

Trong MongoDB, mỗi document được sửa bởi **updateMany** có tính nguyên tử ở phạm vi document, nhưng **toàn bộ nhóm document không trở thành một đơn vị nguyên tử** chỉ vì dùng một lệnh updateMany.

Ví dụ:

~~~text
Sản phẩm A: update thành công
Sản phẩm B: update thành công
Sản phẩm C: lỗi hoặc thao tác bị ngắt
Sản phẩm D: chưa được cập nhật
~~~

Nếu các request khác đọc trong quá trình thao tác, chúng có thể gặp một tập dữ liệu đã cập nhật một phần theo tiến độ của lệnh nhiều document. Việc retry phải xác định thao tác nào idempotent và kiểm tra trạng thái của các document còn lại.

Tương tự, **insertMany** hoặc **bulkWrite** có thể ghi một phần thành công trước khi gặp lỗi, tùy ordered/unordered và ngữ nghĩa cụ thể. **Một batch không tự là all-or-nothing**.

Nếu nghiệp vụ thật sự bắt buộc nhiều document cùng commit, cần xem **multi-document transaction** hoặc thiết kế lại aggregate; không nên dùng updateMany để giả lập transaction.

## 8. MongoDB: transaction nhiều document khi một record không đủ

Ví dụ nghiệp vụ **tạo order và giữ tồn một sản phẩm** phải cùng được công nhận thành công trong database. Hai bản ghi nằm ở collections khác:

~~~text
orders:
  order-1001

inventory:
  BOOK-01
~~~

Một transaction có thể nhóm hai thay đổi, trong môi trường MongoDB có hỗ trợ transaction:

~~~javascript
// Ví dụ Node.js MongoDB driver, đã có client kết nối đúng deployment.
const session = client.startSession();
const db = client.db("shop");

try {
  await session.withTransaction(async () => {
    const inventory = db.collection("inventory");
    const orders = db.collection("orders");

    const stockResult = await inventory.updateOne(
      {
        _id: "BOOK-01",
        tenantId: "shop-a",
        available: { $gte: 3 }
      },
      {
        $inc: { available: -3, reserved: 3 }
      },
      { session }
    );

    if (stockResult.modifiedCount !== 1) {
      throw new Error("INSUFFICIENT_STOCK");
    }

    await orders.insertOne(
      {
        _id: "order-1001",
        tenantId: "shop-a",
        checkoutRequestId: "checkout-req-1001",
        status: "RESERVED",
        items: [{ sku: "BOOK-01", quantity: 3 }],
        currency: "VND"
      },
      { session }
    );
  });
} finally {
  await session.endSession();
}
~~~

Trong ví dụ này, mục đích của transaction là **không công nhận một order mới nếu phần giữ tồn thuộc cùng transaction không thể commit**, và ngược lại. Deployment/driver cần được cấu hình đúng **read concern, write concern, retry, khả năng commit không rõ kết quả và điều kiện hỗ trợ transaction**.

Đoạn mã là cấu trúc minh họa, chưa phải checkout hoàn chỉnh: còn cần xác thực tenant, tính giá, kiểm tra mọi SKU, unique index trên checkoutRequestId, xử lý retry và quy tắc hủy reservation.

**Không đặt lời gọi thanh toán HTTP bên trong transaction DB rồi kỳ vọng rollback database sẽ tự hoàn tiền**. Transaction MongoDB không tự bao trùm một payment provider bên ngoài.

## 9. Redis: một lệnh trên key là một đơn vị thực thi

Redis nổi tiếng với các thao tác trên key có ngữ nghĩa nguyên tử ở cấp lệnh. Ví dụ:

~~~redis
SET inventory:BOOK-01 10
DECRBY inventory:BOOK-01 3
GET inventory:BOOK-01
~~~

Lệnh **DECRBY** thay giá trị số của một key trong một thao tác. Khi nhiều client cùng gửi các lệnh DECRBY, mỗi lệnh được xử lý theo ngữ nghĩa nguyên tử của command; không xảy ra tình trạng một lệnh DECRBY chỉ giảm nửa giá trị.

Tuy nhiên, **DECRBY không tự kiểm tra không âm**:

~~~text
available = 5

Client A: DECRBY 4  -> 1
Client B: DECRBY 4  -> -3
~~~

Hai lệnh đều có thể thành công về mặt thực thi, nhưng nghiệp vụ **không bán quá tồn** bị vi phạm.

Muốn kiểm tra **đủ tồn rồi giảm** như một thao tác không bị request khác chen giữa, cần **Lua script/Redis Function** hoặc một cơ chế compare-and-set/transaction phù hợp.

### Script kiểm tra rồi trừ

~~~lua
-- KEYS[1] là key tồn kho.
-- ARGV[1] là số lượng nguyên dương cần giữ.
local quantity = tonumber(ARGV[1])
local available = tonumber(redis.call('GET', KEYS[1]))

if not quantity or quantity <= 0 or quantity % 1 ~= 0 then
  return {err = "INVALID_QUANTITY"}
end

if not available then
  return {err = "MISSING_OR_INVALID_STOCK"}
end

if available < quantity then
  return 0
end

redis.call('DECRBY', KEYS[1], quantity)
return 1
~~~

Trong phạm vi thực thi script của Redis, các lệnh từ client khác không chen vào giữa các bước kiểm tra và giảm tồn. Vì vậy hai khách không thể cùng đọc **available = 5** bên trong hai script rồi cùng giữ 4 như cách GET/SET tách rời.

Cần kiểm tra giới hạn số nguyên, dữ liệu không hợp lệ, TTL, duplicate request, retry và durability. Script chỉ bảo vệ dữ liệu Redis mà nó thao tác, không bảo vệ một order nằm ở MongoDB hay một giao dịch thanh toán bên ngoài.

## 10. Redis: nguyên tử trong script không đồng nghĩa có rollback

Một nhầm lẫn tinh vi là cho rằng script Lua của Redis giống transaction ACID đa bước với rollback.

Ví dụ phản ví dụ về ý tưởng:

~~~lua
redis.call('INCR', 'demo:counter')
redis.call('HSET', 'demo:counter', 'field', 'value')
~~~

Nếu key **demo:counter** đang là String số nguyên, lệnh **INCR** có thể thành công, nhưng **HSET** trên cùng key có thể lỗi **WRONGTYPE**. Redis không tự hoàn tác lệnh INCR đã thực hiện chỉ vì lệnh sau trong script gặp runtime error.

Script có tính **không bị xen lệnh khác trong thời gian chạy**, nhưng không bảo đảm cơ chế **rollback toàn bộ những ghi đã thực hiện khi một lệnh nội bộ lỗi**.

Vì thế, script có nhiều ghi nên:

1. Kiểm tra trước các điều kiện và kiểu dữ liệu có thể kiểm tra.
2. Giới hạn phạm vi và thời gian thực thi để tránh chặn server lâu.
3. Định nghĩa trạng thái sau lỗi giữa các lệnh.
4. Thiết kế retry/idempotency để không nhân đôi hiệu ứng.
5. Nếu ứng dụng cần rollback nhiều hệ thống, không dựa vào một Lua script.

**Atomic execution** và **rollback semantics** là những thuộc tính phải xem riêng.

## 11. Redis MULTI/EXEC, WATCH và pipeline không giống nhau

Trong Redis có một số cơ chế dễ bị gọi chung là “transaction”:

| Cơ chế | Công dụng | Điều phải hiểu |
|---|---|---|
| **Một command** | Thực hiện một thao tác key/value | Bất biến phải khớp khả năng command |
| **Pipeline** | Gửi nhiều lệnh hiệu quả hơn qua mạng | Không tự biến nhóm lệnh thành giao dịch nguyên tử |
| **MULTI/EXEC** | Xếp nhiều lệnh rồi thực thi tuần tự theo cơ chế Redis | Không có rollback kiểu SQL nếu một lệnh gặp lỗi runtime |
| **WATCH + MULTI/EXEC** | Optimistic concurrency trên các key được theo dõi | Transaction có thể bị hủy nếu watched key đổi; ứng dụng phải retry |
| **Lua script / Redis Function** | Logic nhiều lệnh không bị chen ngang trong quá trình thực thi | Cần tránh lỗi runtime giữa các ghi và hiểu giới hạn cluster |

Một tình huống **WATCH**:

~~~text
WATCH inventory:BOOK-01
GET inventory:BOOK-01             -> 5
Tính toán: nếu >= 4, cần giảm còn 1
MULTI
SET inventory:BOOK-01 1
EXEC
~~~

Nếu một client khác thay đổi key sau WATCH, **EXEC có thể báo transaction không được thực thi**, để ứng dụng đọc lại và thử theo chính sách. Đây là optimistic concurrency; đoạn trên mô tả luồng logic, không phải code client xử lý mọi lỗi, kết nối và retry.

Trong Redis Cluster, các thao tác nhiều key chịu ràng buộc **hash slot** và lệnh cụ thể. Không được suy rằng một script/MULTI có thể cập nhật nguyên tử bất kỳ key nào nằm rải ở nhiều shard. Việc cùng dùng tiền tố **inventory:** cũng không chứng minh các key thuộc cùng hash slot.

## 12. Key chứa JSON không làm thao tác đọc–sửa–ghi thành nguyên tử

Giả sử một profile được lưu dưới một Redis String JSON:

~~~redis
SET profile:customer-07 "{\"name\":\"An\",\"points\":0}"
~~~

Hai worker:

~~~text
Worker A:
  GET -> points 0
  tính points 10

Worker B:
  GET -> points 0
  tính points 20

Worker A:
  SET toàn JSON points 10

Worker B:
  SET toàn JSON points 20
~~~

Mỗi lệnh **SET** ghi nguyên tử một value, nhưng logic tổng thể có thể **mất cập nhật** của worker A. Nếu thật sự muốn cộng điểm, dùng một counter atomic thích hợp, hoặc thiết kế WATCH/script và idempotency theo event.

Nếu dùng **Redis Hash**:

~~~redis
HSET profile:customer-07 name "An" points 0
HINCRBY profile:customer-07 points 10
~~~

HINCRBY giúp tránh thao tác GET/SET tách rời cho phép cộng integer. Nhưng nếu một event thưởng 10 điểm được xử lý hai lần, counter có thể tăng 20 điểm; **atomic increment không phải exactly-once business processing**.

## 13. DynamoDB: nguyên tử trên một item, không phải mọi item cùng partition key

Trong DynamoDB, đơn vị dữ liệu quan trọng là **item**, được định danh bởi primary key của table. **PutItem**, **UpdateItem**, **DeleteItem** và các điều kiện ghi tương ứng tác động theo ngữ nghĩa nguyên tử của thao tác trên item.

Ví dụ item:

~~~text
PK               PRODUCT#BOOK-01
availableStock   10
reservedStock     0
version           1
~~~

Một thao tác **UpdateItem** có thể giảm available, tăng reserved và tăng version trong cùng item, đồng thời kiểm tra không âm:

~~~text
Key:
  PK = "PRODUCT#BOOK-01"

UpdateExpression:
  SET availableStock = availableStock - :qty,
      reservedStock = reservedStock + :qty,
      version = version + :one

ConditionExpression:
  attribute_exists(PK) AND availableStock >= :qty

ExpressionAttributeValues:
  :qty = 3
  :one = 1
~~~

Đây là mẫu biểu thức minh họa; khi gọi SDK thực tế phải cung cấp kiểu AttributeValue đúng, kiểm tra quantity nguyên dương, bảo đảm các thuộc tính số đã tồn tại hoặc dùng biểu thức khởi tạo phù hợp, và xử lý **ConditionalCheckFailedException** theo hợp đồng.

Tất cả thay đổi thuộc cùng **một UpdateItem** được áp dụng trong đơn vị item theo bảo đảm của DynamoDB. Nếu điều kiện thất bại, không thực hiện update đó.

### Một partition key có thể chứa nhiều item

Ví dụ table có cả **PK** và **SK**:

~~~text
PK = CUSTOMER#07, SK = ORDER#1001
PK = CUSTOMER#07, SK = ORDER#1002
PK = CUSTOMER#07, SK = SUMMARY
~~~

Ba item chung partition key logic **không đồng nghĩa một UpdateItem trên ORDER#1001 sẽ nguyên tử cập nhật cả ORDER#1002 và SUMMARY**. Muốn điều phối nhiều item, cần dùng transaction API phù hợp hoặc thiết kế bản summary là dữ liệu dẫn xuất có độ trễ chấp nhận được.

Nói cách khác, **partition key giúp định tuyến và Query**, không tự tạo một transaction cho mọi item cùng partition key.

## 14. DynamoDB: điều kiện ghi và transaction nhiều item

Những bất biến thường có thể bảo vệ trên một item:

- Chỉ tạo item nếu chưa tồn tại bằng **ConditionExpression**.
- Chỉ trừ tồn nếu **availableStock >= qty**.
- Chỉ chuyển **PENDING → PAID** khi trạng thái hiện tại là PENDING.
- Chỉ ghi nếu **version** vẫn bằng giá trị client đã đọc.

Khi bất biến trải nhiều item, DynamoDB có **TransactWriteItems** trong phạm vi và giới hạn sản phẩm hỗ trợ. Ví dụ một thao tác có thể bao gồm:

~~~text
Transaction:
  1. Update inventory BOOK-01 nếu đủ số lượng
  2. Put order-1001 nếu key chưa tồn tại
  3. Put reservation record nếu reservationId chưa tồn tại
~~~

Transaction giúp các thao tác tham gia cùng được commit hoặc không được áp dụng theo bảo đảm API. Tuy nhiên:

- Phải tuân thủ giới hạn số item, kích thước và những ràng buộc transaction hiện hành.
- Không mặc nhiên có thể thao tác nhiều lần trên **cùng item** trong một transaction bằng các hành động mâu thuẫn.
- Có thể có transaction conflicts và throttling, cần retry có kiểm soát.
- Phải thiết kế idempotency khi client không biết rõ kết quả do timeout.
- Transaction không bao gồm payment provider hoặc Redis cache bên ngoài.
- Các kết quả đọc qua **GSI** có tính eventual consistency; không dùng GSI trễ để thay thế điều kiện ghi ở item nguồn.

Không nên tự đoán quota transaction theo số trong một bài cũ: cần kiểm tra giới hạn đúng phiên bản/dịch vụ đang dùng trước khi triển khai.

## 15. Cassandra: partition, row, batch và LWT là những phạm vi khác nhau

Cassandra thường tổ chức dữ liệu theo **partition key** và **clustering columns**:

~~~sql
CREATE TABLE reservations_by_show (
    show_id text,
    seat_id text,
    reservation_id text,
    status text,
    reserved_at timestamp,
    PRIMARY KEY ((show_id), seat_id)
);
~~~

Trong bảng này:

- **show_id** định danh partition.
- **seat_id** là clustering key, phân biệt row trong partition.
- Một suất chiếu có nhiều ghế, nhưng mỗi ghế tương ứng với một row theo khóa đã chọn.

Một update CQL thông thường trên một row:

~~~sql
UPDATE reservations_by_show
SET status = 'HELD',
    reservation_id = 'reservation-101'
WHERE show_id = 'show-07'
  AND seat_id = 'A12';
~~~

Đừng suy rằng việc ghi vào một row theo khóa có nghĩa **toàn bộ thao tác nghiệp vụ chọn ghế đã được bảo vệ**. Lệnh trên không kiểm tra seat đang AVAILABLE hay đã HELD; hai request có thể ghi đè reservation của nhau theo quy tắc xử lý xung đột/timestamp của Cassandra.

### LWT để compare-and-set

Với dữ liệu được khởi tạo trạng thái phù hợp, có thể dùng **lightweight transaction (LWT)**:

~~~sql
UPDATE reservations_by_show
SET status = 'HELD',
    reservation_id = 'reservation-101'
WHERE show_id = 'show-07'
  AND seat_id = 'A12'
IF status = 'AVAILABLE';
~~~

Nếu một request khác đã đổi status trước, điều kiện **IF** có thể trả **[applied] = false**; ứng dụng phải kiểm tra kết quả, không mặc nhiên coi câu lệnh đã giành được ghế. LWT có cơ chế phối hợp và chi phí khác ghi CQL thông thường; cần cân nhắc contention trên partition/khóa và phiên bản triển khai.

### BATCH không đồng nghĩa transaction SQL

Cassandra hỗ trợ **BATCH**, nhưng không nên hiểu mọi batch là một transaction có đầy đủ **atomicity + isolation + rollback + serializability** như một transaction SQL.

Đặc biệt:

- **BATCH** hữu ích cho những mutation liên quan và có ngữ nghĩa cam kết/khôi phục phụ thuộc **logged/unlogged** và phạm vi partition.
- Logged batch có cơ chế bảo đảm các mutation cuối cùng được áp dụng theo bảo đảm Cassandra, nhưng **không cung cấp isolation tổng quát cho mọi row/partition**.
- Một batch nhiều partition không phải cách mặc định để tăng throughput hoặc tạo một ACID transaction rộng.
- Khi có nhiều writer, cần xem ngữ nghĩa **timestamp/conflict resolution**, conditional writes, LWT và thứ tự quan sát.
- Cần đọc đúng tài liệu phiên bản Cassandra đang dùng để xác định phạm vi atomicity của mutation, partition và batch; không suy từ việc các row cùng partition rằng mọi business invariant được tự bảo vệ.

**Partition** vừa là ranh giới truy cập và phân phối dữ liệu, vừa ảnh hưởng một số bảo đảm của engine, nhưng **không được đồng nhất partition với một “document khổng lồ” có toàn bộ hành vi giao dịch của MongoDB**.

## 16. Bigtable và HBase: row là đơn vị atomic update quan trọng

Trong Bigtable hoặc HBase, dữ liệu được tổ chức thành **row key** và các cột/cell. Một điểm thiết kế quan trọng của những hệ này là hỗ trợ **mutation nguyên tử ở phạm vi một row** theo API tương ứng.

Ví dụ một row:

~~~text
Row key:
  inventory#BOOK-01

Columns:
  stock:available = 10
  stock:reserved  = 0
  meta:version    = 1
~~~

Nếu một row mutation cập nhật **stock:available** và **stock:reserved**, các thay đổi thuộc **row mutation** đó có thể được xem là một đơn vị nguyên tử theo bảo đảm của hệ.

Nếu available nằm ở row **inventory#BOOK-01** còn reservation ở row **reservation#R101**, đây đã là **hai row**. Không nên suy từ “Bigtable/HBase hỗ trợ atomic row operations” rằng hai row sẽ cùng rollback khi một bước thất bại.

Một số API hỗ trợ **conditional row mutation / check-and-mutate** hoặc **read-modify-write** ở phạm vi row; cú pháp và điều kiện khác nhau giữa sản phẩm. Chọn row key và cách nhóm cell phải xem cả:

- Trường nào cần đổi cùng nhau?
- Row có tăng không giới hạn không?
- Tốc độ ghi vào một row có tạo hotspot không?
- Có cần một row khác làm index theo đường truy vấn không?
- Những thay đổi nhiều row phải được đồng bộ bằng workflow nào?

## 17. So sánh ranh giới nguyên tử thường gặp

| Hệ / thao tác | Đơn vị bảo đảm đáng chú ý | Những gì không nên tự suy ra |
|---|---|---|
| **MongoDB updateOne** | Một document được sửa trong một thao tác | Hai updateOne hoặc updateMany toàn tập là một transaction |
| **MongoDB transaction** | Nhiều document thuộc phạm vi transaction hỗ trợ | Giao dịch bao trùm HTTP/payment/queue ngoài DB |
| **Redis single command** | Thực thi nguyên tử command trên dữ liệu Redis theo cơ chế engine | Nhiều GET/SET tách rời có CAS; retry không làm trùng |
| **Redis script / MULTI/EXEC** | Không bị các lệnh client khác chen giữa khi đang thực thi theo cơ chế hỗ trợ | Có SQL-style rollback khi command nội bộ lỗi |
| **DynamoDB UpdateItem** | Một item với condition/update thuộc thao tác đó | Tất cả item có chung partition key cùng nguyên tử |
| **DynamoDB TransactWriteItems** | Nhiều item trong giới hạn API transaction | GSI strong consistency hoặc giao dịch xuyên hệ ngoài |
| **Cassandra regular mutation** | Bảo đảm mutation theo row/partition và ngữ nghĩa engine | CQL BATCH là transaction SQL serializable |
| **Cassandra LWT** | Điều kiện compare-and-set trong phạm vi hỗ trợ | Transaction tùy ý xuyên mọi partition/service |
| **Bigtable/HBase row mutation** | Một row với những cell được cập nhật cùng thao tác | Nhiều row tự cập nhật all-or-nothing |
| **Ứng dụng duy trì read model** | Phụ thuộc transaction hoặc workflow do ứng dụng xây dựng | Hai bảng/Set tự đồng bộ chỉ vì cùng nguồn dữ liệu |

Bảng là **bản đồ để đặt câu hỏi**, không thay thế tài liệu giao dịch của phiên bản triển khai. Với những lời hứa quan trọng như “không bán trùng vé” hoặc “không mất tiền”, phải kiểm chứng đúng API, isolation level, write concern, topology và đường retry.

## 18. Tính nguyên tử không tự ngăn retry tạo tác dụng lặp

Giả sử một request cộng 100 điểm:

~~~text
Client gửi:
  tăng points thêm 100

Database:
  thực hiện thành công và commit

Mạng:
  mất response trước khi client nhận

Client:
  tưởng thất bại, gửi lại yêu cầu
~~~

Mỗi lệnh tăng points có thể **nguyên tử**. Nhưng nếu lệnh chạy hai lần, points tăng **200**. Atomicity không chứng minh chỉ một ý định được áp dụng đúng một lần.

Để xử lý, cần **idempotency key/event ID**:

~~~text
rewardEventId = "reward-evt-77"

Lần đầu:
  ghi nhận reward-evt-77 chưa xử lý
  cộng 100 điểm
  đánh dấu đã xử lý

Lần retry:
  phát hiện reward-evt-77 đã xử lý
  trả kết quả cũ, không cộng thêm
~~~

Nếu việc đánh dấu event và cộng điểm nằm ở **hai document**, chỉ dùng unique key của event rồi cộng điểm ngoài transaction vẫn có cửa sổ lỗi:

~~~text
Ghi event "đã xử lý" thành công
        |
        v
Ứng dụng chết trước khi cộng điểm
        |
        v
Retry thấy event đã xử lý nên bỏ qua
        |
        v
Điểm chưa được cộng
~~~

Cần phối hợp **transaction**, hoặc **trạng thái inbox với retry có điều kiện**, hoặc một mô hình gộp hiệu ứng và dấu vết event vào ranh giới đủ mạnh. **Idempotency là thiết kế trạng thái, không chỉ là một header HTTP.**

## 19. Upsert và unique key: tính nguyên tử không thay thế định danh nghiệp vụ

Một document có thể được tạo bằng **upsert**:

~~~javascript
db.customerPreferences.updateOne(
  {
    tenantId: "shop-a",
    customerId: "customer-07"
  },
  {
    $set: {
      language: "vi",
      theme: "dark"
    },
    $setOnInsert: {
      schemaVersion: 1
    }
  },
  { upsert: true }
);
~~~

Nếu hai request cùng upsert khi record chưa có, cần **unique index trên logical key** để không xuất hiện hai document cùng nghĩa:

~~~javascript
db.customerPreferences.createIndex(
  { tenantId: 1, customerId: 1 },
  { unique: true }
);
~~~

Atomicity của mỗi updateOne **không tự bảo đảm** hai lần upsert dùng filter không có unique constraint sẽ hợp nhất thành một document. Khi có race, một request có thể gặp duplicate key; ứng dụng phải đọc lại hoặc retry theo ý định cụ thể.

Đối với chuyển trạng thái **PENDING → PAID**, **không bật upsert**:

~~~javascript
db.orders.updateOne(
  {
    _id: "order-1001",
    tenantId: "shop-a",
    status: "PENDING"
  },
  {
    $set: { status: "PAID" }
  }
);
~~~

Nếu order không tồn tại hoặc đã bị hủy, **không được tự tạo một order mới** chỉ vì filter không khớp. Ranh giới nguyên tử và điều kiện cho phép tạo mới là hai quyết định khác nhau.

## 20. Write skew: một transaction nguyên tử vẫn phải bảo vệ bất biến trên tập dữ liệu

Xét quy tắc: **luôn có ít nhất một nhân viên trực ca**.

~~~text
Nhân viên A: ON_DUTY
Nhân viên B: ON_DUTY
~~~

Hai thao tác đồng thời:

~~~text
Transaction T1                      Transaction T2
--------------                      --------------
Đọc A và B đều trực                Đọc A và B đều trực
Cho A nghỉ                          Cho B nghỉ
Ghi A = OFF_DUTY                    Ghi B = OFF_DUTY
Commit                              Commit
~~~

Nếu cả hai transaction được chấp nhận dưới mức isolation không loại trừ được kiểu race này, kết quả là **không còn nhân viên trực**, mặc dù mỗi transaction có thể nguyên tử trên những ghi của nó.

Tình huống được gọi là **write skew**. Để bảo vệ bất biến liên quan nhiều record, cần **mức isolation hoặc một điểm phối hợp chung** phù hợp, ví dụ:

- Tổ chức lại trạng thái trực ca dưới một record có cập nhật có điều kiện nếu thiết kế cho phép.
- Sử dụng transaction với cơ chế khóa/serializable phù hợp.
- Dùng counter/quota có điều kiện gắn với một đối tượng quản lý ca.
- Hạn chế tính toán trên snapshot cũ mà không có cơ chế phát hiện xung đột.

**Atomicity trả lời “tất cả ghi của giao dịch có cùng thành công không?”; isolation và điều kiện ghi trả lời “hai giao dịch cùng lúc có làm hỏng bất biến không?”**.

## 21. Một partition lớn không phải phương án mặc định cho mọi bất biến

Khi nghe “cần nguyên tử trong một phạm vi”, một thiết kế dễ hấp tấp là **gom mọi dữ liệu vào một key/document/partition cực lớn**:

~~~text
customer-07:
  profile
  preferences
  all-orders
  all-payments
  all-events
  all-notifications
~~~

Cách này có thể gây:

- Value/document/partition tăng không giới hạn.
- Một key hoặc partition quá nóng vì nhiều writer cùng sửa.
- Thời gian đọc và payload lớn dù API chỉ cần vài field.
- Tranh chấp ghi và khó phân quyền theo các vòng đời khác nhau.
- Tính năng mới khó tách phần dữ liệu có chính sách retention khác nhau.

Một **ranh giới nguyên tử hợp lý** là phạm vi **nhỏ nhất nhưng đủ bảo vệ các bất biến thực sự phải giữ cùng nhau**, không phải gom toàn bộ dữ liệu có liên quan vào một chỗ.

Ví dụ, một order có thể nhúng các dòng hàng đã chốt vì chúng thuộc cùng aggregate, trong khi hồ sơ customer, tồn kho chia sẻ giữa nhiều order và giao dịch thanh toán ở những aggregate khác. Những bất biến liên aggregate phải được bảo vệ bằng transaction hoặc workflow thay vì bằng một document không giới hạn.

## 22. Khi dữ liệu nằm trên nhiều đơn vị: transaction hay saga?

Giả sử quy trình mua hàng:

~~~mermaid
flowchart TD
    A["Yêu cầu checkout có requestId"] --> B["Tạo order PENDING"]
    B --> C["Giữ stock có điều kiện"]
    C --> D["Gọi payment provider"]
    D --> E["Chuyển order PAID"]
    D --> F["Thất bại hoặc cần hoàn"]
    F --> G["Giải phóng reservation"]
~~~

Các bước không mặc nhiên thuộc cùng một transaction:

- Order ở MongoDB.
- Inventory ở DynamoDB hoặc dịch vụ kho.
- Payment ở cổng thanh toán.
- Event vào message broker.
- Dashboard ở một read model.

Một **database transaction** chỉ bao trùm những thay đổi mà hệ thống giao dịch đó hỗ trợ. Nó không thể tự rollback tiền đã thu qua HTTP.

Một **saga/workflow có trạng thái bền vững** có thể dùng:

1. **Idempotency key** cho checkout và payment intent.
2. **Reservation ID duy nhất**, có trạng thái HELD/COMMITTED/RELEASED.
3. **Conditional write** để không giữ quá tồn.
4. **Outbox** để không mất event sau commit.
5. **Inbox/dedup** để consumer không áp dụng cùng event nhiều lần.
6. **Bước bù** khi thanh toán thất bại hoặc cần hoàn.
7. **Đối soát** khi trạng thái thanh toán không rõ vì timeout.

Saga không cung cấp một transaction ACID toàn cục; nó quản lý **các trạng thái trung gian được nghiệp vụ cho phép** và cách đưa hệ thống về kết quả hợp lệ.

## 23. Ví dụ: giữ tồn và giải phóng reservation phải chống lặp

Giả sử order **order-1001** giữ 3 cuốn. Một tiến trình giải phóng reservation bị retry hai lần. Nếu mỗi lần đều:

~~~text
available += 3
reserved -= 3
~~~

thì có thể hoàn tồn **hai lần**, dù từng lần cập nhật nguyên tử.

Để tránh:

~~~text
reservation-101:
  sku = BOOK-01
  quantity = 3
  state = HELD

Release:
  chỉ cho phép HELD -> RELEASED
  thực hiện hiệu ứng hoàn tồn đúng một lần
~~~

Nếu reservation state và inventory counters cùng nằm ở một document nhỏ, có thể thiết kế một cập nhật nguyên tử theo điều kiện phù hợp. Nếu nằm ở hai document/item, phải dùng transaction hoặc workflow ghi nhận tiến độ/idempotency bảo vệ cả hai.

Không nên dùng **trạng thái cuối = RELEASED** làm bằng chứng đủ nếu không biết hiệu ứng hoàn tồn đã thực sự được áp dụng. Trường hợp crash giữa **đánh dấu RELEASED** và **cộng lại stock** phải được bao phủ bởi thiết kế.

## 24. Phân biệt kết quả được server xác nhận với kết quả client biết

Một timeline thường gặp:

~~~text
Client                   Database
   |                         |
   |------ UPDATE ---------->|
   |                         | kiểm tra điều kiện
   |                         | áp dụng atomic write
   |                         | commit/ack theo cấu hình
   |<----- RESPONSE ---X     |
   |      (mạng lỗi)         |
   |                         |
   | client không biết       |
   | ghi đã thành công chưa  |
~~~

Hai tình huống phải được phân biệt:

**Thao tác bị từ chối xác định:** server trả condition failed, duplicate key hoặc validation error. Ứng dụng có thể biết không có hiệu ứng cập nhật theo bảo đảm của thao tác đó.

**Kết quả chưa rõ:** kết nối timeout/mất sau khi request đã được gửi. Client không thể tự kết luận “server chưa ghi”. Cần query theo logical ID/idempotency key hoặc retry bằng cơ chế hỗ trợ mà không tạo tác dụng lặp.

Khi lựa chọn **write concern**, durability, consistent reads và failover, mức xác nhận của server có thể khác nhau. **Một thao tác logic nguyên tử không tự bảo đảm không mất ghi khi failover trong mọi cấu hình replication**.

## 25. Phân biệt tính nguyên tử, tính bền vững và replication

Giả sử một Redis command hoặc một MongoDB write thành công trên node đang xử lý. Các câu hỏi tiếp theo vẫn cần được trả lời:

- Dữ liệu đã được ghi vào bộ nhớ, journal, log hay ổ đĩa theo mức xác nhận nào?
- Đã có bao nhiêu replica xác nhận?
- Nếu node chính lỗi ngay sau response, ghi có thể bị mất hoặc rollback theo cơ chế failover không?
- Request sau đó đọc từ primary hay replica có thể trễ?
- Nếu dùng eventual consistency, read-your-writes được bảo đảm trong trường hợp nào?

Atomicity và durability **không đồng nghĩa**. Ví dụ một lệnh có thể hoàn tất nguyên tử trên một node, nhưng khả năng dữ liệu còn sau mất điện phụ thuộc cấu hình persistence. Một read trên replica trễ có thể thấy bản cũ mà không có nghĩa bản update nguyên tử đã được “áp dụng một nửa”.

Khi nghiệp vụ liên quan tiền, quyền truy cập hoặc giữ tồn, phải ghi rõ cả **phạm vi atomicity** và **mức xác nhận/đọc** cần thiết. Nếu không, team có thể kiểm thử chỉ trên một node local rồi hiểu sai hành vi của cluster production.

## 26. TTL và xóa dữ liệu không tạo transaction nghiệp vụ

Giả sử reservation có **expiresAt** và một TTL index/job sẽ xóa sau hạn. Việc hết hạn vật lý có thể là bất đồng bộ:

~~~text
Reservation:
  state = HELD
  expiresAt = 10:00

10:00:
  thời hạn logic đã tới

10:00:05:
  job TTL mới thực sự dọn record
~~~

Không nên kết luận **“key đã hết TTL thì các thay đổi liên quan ở inventory tự động rollback”**. Xóa key reservation không tự cộng lại availableStock ở database khác.

Nếu thời điểm hết hạn ảnh hưởng bất biến bán hàng:

1. Đường xác nhận mua phải kiểm tra trạng thái và **expiresAt** theo nguồn thời gian đáng tin.
2. Đường giải phóng cần **conditional transition** để không hoàn tồn hai lần.
3. Dọn vật lý chỉ là phần của vòng đời lưu trữ; không thay thế logic nghiệp vụ.
4. Nếu có phiên gia hạn hold, job cũ phải tránh xóa bản vừa gia hạn.

Một TTL command có thể nguyên tử trên key bị xóa, nhưng **workflow hết hạn** thường gồm nhiều trạng thái và side effects; phải thiết kế riêng.

## 27. Một command đọc cũng có phạm vi quan sát

Atomicity thường được nói trong ngữ cảnh ghi, nhưng **đọc dữ liệu** cũng cần hiểu phạm vi quan sát.

Nếu một MongoDB document được update nhiều field trong một thao tác, một lần đọc document theo bảo đảm của engine không phải tự tạo ra một trạng thái “nửa cũ nửa mới” của chính update đó.

Nhưng nếu API thực hiện:

~~~text
Read order document
Read inventory document
Read payment document
~~~

ba lần đọc ấy **không tự là một snapshot transaction**. Giữa mỗi lần đọc, writer khác có thể thay dữ liệu. Kết quả tổng hợp của API có thể kết hợp những thời điểm khác nhau.

Nếu màn hình chỉ hiển thị thông tin tổng quan, độ lệch nhỏ có thể được phép. Nếu API cần xác minh bất biến liên quan nhiều record tại cùng một điểm thời gian, cần snapshot/transaction hoặc cơ chế tính toán/điều kiện phù hợp.

**Một record đọc nhất quán không có nghĩa nhiều request đọc liên tiếp tự chia sẻ cùng snapshot.**

## 28. Đừng nhầm tính đúng của một transaction với tính đúng của read model

Giả sử transaction nguồn chuyển order sang **PAID** thành công. Hệ còn các bản đọc:

~~~text
orders (nguồn)
  status = PAID

recent_orders_by_customer
  status = PENDING  (chưa nhận event)

sales_dashboard
  paidOrderCount chưa tăng
~~~

Nếu read models cập nhật bất đồng bộ, sự lệch tạm thời có thể phù hợp hợp đồng **eventual consistency**. Nó không có nghĩa transaction đổi order tại nguồn đã thực hiện dở dang.

Nhưng muốn read models hội tụ đúng cần:

- ID của event nguồn và version/sequence.
- Retry sau lỗi, checkpoint và khả năng replay.
- Dedup khi consumer nhận lại cùng event.
- Chặn event cũ ghi đè version mới.
- Backfill hoặc rebuild khi bị mất/bỏ sót event.
- Đối soát số lượng/bất biến so với nguồn chính.

Không nên dùng dashboard hoặc secondary read model trễ làm nguồn duy nhất cho quyết định **đã thanh toán hay chưa** nếu nghiệp vụ yêu cầu xác minh tức thời ở nguồn.

## 29. Những bất biến phù hợp với một đơn vị và những bất biến cần phối hợp

| Bất biến nghiệp vụ | Điểm kiểm soát ứng viên | Cảnh báo |
|---|---|---|
| available không âm của một SKU | Một inventory item/document + conditional write | Retry trừ hai lần vẫn cần idempotency |
| Tổng tiền và dòng hàng đã chốt của một order | Một order document, nếu dữ liệu có giới hạn | Phải xác minh công thức khi tạo |
| Một user có một preferences record | Unique logical key + upsert có kiểm soát | Race upsert khi thiếu unique constraint |
| Một ghế chỉ có một claim hiện hành | Claim key/unique constraint/LWT | TTL hoặc status phải được xử lý |
| Một event thưởng chỉ cộng một lần | EventId và hiệu ứng trong cùng ranh giới phù hợp | Inbox “đã nhận” không đồng nghĩa “đã áp dụng” |
| Hai SKU cùng được giữ cho một order | Transaction nhiều inventory items hoặc reservation workflow | Giữ được một SKU nhưng thiếu SKU kia |
| Order và payment provider phải khớp | Saga, idempotency và reconciliation | Không có rollback DB qua HTTP |
| Dashboard phản ánh tổng order | Read model có replay và đối soát | Độ mới phải có SLO riêng |
| Không còn dưới một nhân viên trực | Isolation/coordination trên tập liên quan | Single-record atomicity ở hai record riêng không đủ |
| Không xuất dữ liệu khác tenant | Auth + điều kiện đọc/ghi + schema/khóa phù hợp | Atomic write không chứng minh quyền |

Mục tiêu của thiết kế là **xác định bất biến trước**, sau đó tìm **đơn vị nhỏ nhất có thể bảo vệ**. Nếu bất biến vượt qua đơn vị có sẵn, chọn transaction hoặc chấp nhận workflow trung gian có quy tắc phục hồi.

## 30. Kiểm thử tính nguyên tử dưới ghi đồng thời

Không nên chỉ kiểm tra “lệnh chạy không báo lỗi”. Cần kiểm tra trạng thái cuối và số thao tác nghiệp vụ đã thực sự có hiệu lực.

### Kịch bản 1 — Hai request giảm tồn

~~~text
Given:
  available = 5

When:
  hai client cùng đặt 4

Then:
  tối đa một client giữ thành công
  available = 1 nếu một giữ thành công
  không tạo hai reservation đều hợp lệ
~~~

Kiểm tra **kết quả API**, **trạng thái nguồn**, **số reservation**, và lặp lại nhiều lần dưới concurrency đại diện.

### Kịch bản 2 — Lệnh nhiều field thất bại

~~~text
Given:
  available = 10, reserved = 0, version = 1

When:
  thao tác nguyên tử giữ 3 bị lỗi điều kiện

Then:
  không chỉ thay một vài field trong thao tác ấy
  trạng thái không bị coi là reservation thành công
~~~

### Kịch bản 3 — Hai document, lỗi giữa chừng

~~~text
Given:
  chưa có order, còn 10 stock

When:
  giữ stock thành công nhưng tạo order thất bại

Then:
  transaction phải rollback theo bảo đảm,
  hoặc workflow phải ghi trạng thái và bù/đối soát được
~~~

### Kịch bản 4 — Response bị mất

~~~text
Given:
  checkoutRequestId = "checkout-req-101"

When:
  server commit, client timeout, client retry cùng key

Then:
  chỉ một order/hiệu ứng giữ hàng thuộc ý định đó
  client nhận lại trạng thái hợp lệ mà không nhân đôi nghiệp vụ
~~~

### Kịch bản 5 — Ghi chéo tenant

~~~text
Given:
  order thuộc shop-b

When:
  user của shop-a gửi request cập nhật orderId ấy

Then:
  không có ghi vào order ngoài quyền,
  không được tự upsert một bản ghi mới để che lỗi
~~~

**Kiểm thử trạng thái cuối quan trọng hơn việc thấy HTTP 200**, vì hai lệnh đều trả thành công vẫn có thể gây oversell hoặc ghi trùng.

## 31. Fault injection và phục hồi khi crash

Ngoài concurrency, cần cố tình tạo lỗi giữa các bước:

| Điểm gây lỗi | Điều cần xác minh |
|---|---|
| Trước khi gửi lệnh | Không có tác dụng phụ và retry được |
| Sau khi lệnh đã commit nhưng trước response | Client không lặp hiệu ứng khi retry |
| Giữa hai command độc lập | Có rollback/compensation hoặc trạng thái trung gian được theo dõi |
| Trước commit transaction | Ghi chưa commit không bị công nhận |
| Trong quá trình commit/response chưa rõ | Có cách xác định kết quả giao dịch |
| Sau commit DB nhưng trước publish event | Outbox/change feed tránh mất thay đổi |
| Consumer đã nhận event nhưng chưa áp dụng hiệu ứng | Có retry và trạng thái xử lý đúng |
| Sau hiệu ứng nhưng trước ack event | Consumer dedup, không áp dụng lại |
| Trong lúc replica failover | Durability và read consistency đáp ứng hợp đồng |
| Trong lúc TTL/cleanup chạy | Không hoàn tồn hai lần, không xóa trạng thái mới |

Một **fault injection test** phải mô tả điều kiện ban đầu, điểm lỗi, hành vi retry và trạng thái hợp lệ cuối cùng. Khi chạy trên hệ thật, chỉ thực hiện trong môi trường kiểm soát với dữ liệu thử nghiệm hoặc kịch bản được phê duyệt; không phá ngẫu nhiên dịch vụ production.

## 32. Chỉ số quan sát phù hợp với từng phạm vi nguyên tử

| Nhóm metric | Cần theo dõi | Tín hiệu bất thường |
|---|---|---|
| Conditional writes | số thành công/thất bại theo loại điều kiện | Đột biến conflict, input bất thường |
| Idempotency | duplicate request/event và lần áp dụng hiệu ứng | Một key tạo nhiều kết quả |
| Transaction | commit/abort, retries, conflicts, duration | Transaction quá lớn hoặc nghẽn |
| Redis script/MULTI | latency, errors, blocked time, WATCH abort | Script dài, WRONGTYPE giữa các lệnh |
| DynamoDB | conditional check failures, throttling, transaction cancellations | Hot item/capacity hoặc race |
| Cassandra | LWT contention/latency, unavailable/timeouts, batch warnings | Phối hợp quá nặng hoặc partition hot |
| Read models | event lag, mismatch, replay backlog | Bản dẫn xuất không hội tụ |
| Business invariant | stock âm, duplicate seat claims, tổng ledger lệch | Sai nghiệp vụ dù API thành công |
| Durability | replication lag, failover/ack errors, restore tests | Không đáp ứng mức bền vững kỳ vọng |

Không phải engine nào cũng cung cấp các metric với tên giống nhau. Một số phải được đo ở tầng ứng dụng hoặc reconciliation job. Hãy kết nối metric kỹ thuật với **điều kiện nghiệp vụ cần được bảo vệ**, tránh chỉ theo dõi CPU và số request chung.

## 33. Những hiểu nhầm phổ biến

| Hiểu nhầm | Vì sao không đúng | Cách suy luận đúng |
|---|---|---|
| “Một request API là một transaction” | API có thể gọi nhiều lệnh và dịch vụ | Xác định từng đơn vị commit |
| “Một lệnh updateMany nguyên tử trên mọi document” | Mỗi document có thể được sửa nguyên tử riêng | Dùng transaction khi cần all-or-nothing toàn tập |
| “Ghi nguyên tử là không bao giờ bán quá tồn” | Ghi SET từ snapshot cũ vẫn có lost update | Conditional read-modify-write |
| “Redis DECRBY không cho giá trị âm” | Lệnh trừ không tự kiểm tra bất biến | Script/CAS/logic điều kiện |
| “Redis Lua có rollback nếu lệnh sau lỗi” | Các ghi trước runtime error có thể còn | Kiểm tra trước, thiết kế script và retry |
| “Pipeline Redis là MULTI/EXEC” | Pipeline tối ưu truyền lệnh, không tạo transaction | Chọn cơ chế theo yêu cầu |
| “Một partition DynamoDB là một transaction” | Một partition key có nhiều item | Dùng conditional item write/TransactWriteItems |
| “Cassandra BATCH tương đương transaction SQL” | Batch không cung cấp mọi isolation/rollback SQL | Hiểu logged/unlogged/LWT và phạm vi |
| “Cùng partition là bảo vệ mọi bất biến” | Truy cập và atomicity là khái niệm khác | Kiểm tra guarantee của mutation/transaction |
| “Một row atomic thì hai row tự atomic” | Bảo đảm row không tự kéo dài qua row khác | Transaction/workflow cho nhiều row |
| “Atomic increment nghĩa là event chỉ được xử lý một lần” | Retry có thể tăng lần hai | Idempotency và dedup |
| “Timeout nghĩa là DB chưa ghi” | Response có thể mất sau commit | Xác minh theo logical key |
| “Có transaction là không cần unique constraint” | Race và key logic vẫn cần được bảo vệ | Constraint + transaction/isolation phù hợp |
| “Có snapshot read là mọi bất biến đều đúng” | Write skew vẫn có thể xảy ra | Chọn isolation/coordination phù hợp |
| “Ghi nguồn xong thì mọi cache đều đã cập nhật” | Read models có thể trễ | Độ mới, retry và đối soát |
| “TTL xóa reservation sẽ tự hoàn stock” | Cleanup key không phải nghiệp vụ bù | Reservation workflow riêng |
| “Cần nhất quán nên nhúng mọi thứ vào một document” | Giới hạn kích thước, hotspot, vòng đời khác nhau | Aggregate nhỏ nhất đủ mạnh |

## 34. Quy trình ra quyết định cho một thao tác ghi NoSQL

~~~mermaid
flowchart TD
    A["Định nghĩa thao tác nghiệp vụ"] --> B["Liệt kê field/key/document/item/row phải cùng thay đổi"]
    B --> C["Viết bất biến và trạng thái trước/sau"]
    C --> D{"Trong một đơn vị atomic được engine hỗ trợ?"}
    D -->|"Có"| E["Conditional atomic update / CAS / unique key"]
    D -->|"Không"| F{"Có transaction nhiều đơn vị đủ phạm vi?"}
    F -->|"Có"| G["Transaction + conflict/retry handling"]
    F -->|"Không hoặc nhiều dịch vụ"| H["Saga/reservation/outbox/inbox/compensation"]
    E --> I["Bổ sung idempotency theo request/event"]
    G --> I
    H --> I
    I --> J["Chốt write concern/consistency/durability"]
    J --> K["Test concurrency + crash + network ambiguity"]
    K --> L["Đối soát bất biến và đo production"]
~~~

Áp dụng từng bước:

1. **Gọi đúng tên hành động:** create-only, update-only, reserve, confirm, release hay replace.
2. **Xác định danh tính:** _id, key, PK/SK, row key, partition/clustering key, tenant scope.
3. **Viết bất biến:** stock không âm, trạng thái chuyển hợp lệ, một ghế không được giữ trùng.
4. **Xác định phạm vi nguyên tử:** một field, một document, một item, một row, hay nhiều thực thể.
5. **Đọc guarantee thực tế của engine:** một lệnh, transaction, LWT/CAS, unique constraint và giới hạn cluster.
6. **Đưa điều kiện vào ghi:** tránh GET rồi SET không bảo vệ.
7. **Thiết kế đường retry:** ID ổn định, idempotency key, xử lý kết quả chưa rõ.
8. **Tách side effect ngoài database:** outbox, inbox, saga và quy trình bù.
9. **Chọn read/write consistency và durability:** tránh suy luận từ atomicity sang replication.
10. **Kiểm chứng:** chạy song song, gây lỗi có kiểm soát, quan sát trạng thái cuối và reconciliation.

## 35. Bài tập thực hành

### Bài tập 1 — Đặt tên ranh giới nguyên tử

Với từng thao tác **MongoDB updateOne**, **MongoDB updateMany**, **Redis DECRBY**, **DynamoDB UpdateItem**, **Bigtable row mutation** và **Cassandra BATCH**, hãy nêu ranh giới nào được bảo vệ theo cơ chế tương ứng và điều gì không được phép mặc định là nguyên tử. Giải thích vì sao **một câu lệnh trên client** không phải định nghĩa đầy đủ của atomicity.

### Bài tập 2 — Giữ hàng không âm bằng MongoDB

Inventory có **available = 5**, hai khách cùng muốn giữ **4**. Viết **updateOne** dùng **$gte**, **$inc** và tenantId để chỉ request hợp lệ được trừ. Nêu kết quả trạng thái cuối và cách phân biệt trường hợp không đủ hàng với không tìm thấy item.

### Bài tập 3 — Hai updateOne trên cùng document

Một developer dùng lệnh thứ nhất giảm available 3, lệnh thứ hai tăng reserved 3. Hãy chỉ ra trạng thái dở dang nếu crash giữa hai lệnh và viết lại thành **một updateOne** với nhiều field được sửa cùng nhau.

### Bài tập 4 — updateMany có lỗi một phần

Một job gắn campaignId cho 50.000 product documents bằng **updateMany**. Job bị ngắt giữa chừng. Tại sao không được giả định mọi product đều đã được cập nhật hoặc tự rollback? Thiết kế cách query trạng thái, retry idempotent và checkpoint.

### Bài tập 5 — Redis counter

Redis key stock = 5, hai client đồng thời **DECRBY 4**. Diễn giải kết quả có thể xảy ra và viết Lua script chỉ trừ nếu còn đủ. Vì sao script giải quyết race nhưng chưa giải quyết event retry tạo hiệu ứng lặp?

### Bài tập 6 — Redis Lua lỗi giữa chừng

Script chạy **INCR** thành công rồi thực hiện **HSET** trên cùng key String và gặp WRONGTYPE. Hãy giải thích tại sao không thể coi nó có rollback kiểu SQL. Đề xuất cách kiểm tra trước và thiết kế lỗi an toàn.

### Bài tập 7 — Redis WATCH

Hai worker muốn cập nhật điểm thưởng của một profile String JSON. Hãy mô tả WATCH–GET–MULTI–EXEC với kiểm tra kết quả, cách retry khi watched key thay đổi và vì sao pipeline GET/SET không giải quyết được lost update.

### Bài tập 8 — DynamoDB một item và nhiều item

Inventory item có **availableStock** và **reservedStock**. Viết ý tưởng UpdateExpression/ConditionExpression để giữ 3 đơn vị nguyên tử trên item. Sau đó giải thích tại sao đặt **ORDER#1001**, **ORDER#1002** và **SUMMARY** dưới cùng PK không tự tạo transaction cho cả ba.

### Bài tập 9 — DynamoDB TransactWriteItems

Checkout cần tạo order và giữ một SKU. Đề xuất những hành động transaction, điều kiện ghi và logical key cần thiết. Trình bày cách xử lý transaction conflicts, timeout và retry theo idempotency key; nêu phần payment provider vẫn nằm ngoài transaction.

### Bài tập 10 — Cassandra conditional write

Bảng reservation theo **show_id + seat_id** có status AVAILABLE. Hai khách cùng muốn giữ ghế A12. So sánh **UPDATE không điều kiện** với **UPDATE ... IF status = 'AVAILABLE'** và cách đọc kết quả **[applied]**. Giải thích chi phí LWT và vì sao CQL BATCH không thay thế mọi isolation guarantee.

### Bài tập 11 — Bigtable/HBase row boundary

Một row inventory chứa available/reserved, còn reservation history ở row khác. Hãy xác định những thay đổi nào có thể nằm trong một row mutation và phần nào cần transaction/workflow riêng nếu phải cùng thỏa bất biến.

### Bài tập 12 — Retry sau timeout

Một API cộng 100 điểm đã commit nhưng response bị mất. Client retry. Thiết kế eventId, record xử lý, hiệu ứng cộng điểm và cách xử lý crash trước/sau hiệu ứng mà không đếm trùng hoặc bỏ sót.

### Bài tập 13 — Write skew

Hai nhân viên cùng được quyền nghỉ nếu thấy “vẫn còn người khác trực”. Hai transaction riêng cập nhật hai record khác nhau. Mô tả kết quả bất hợp lệ có thể xảy ra và thiết kế một điểm điều phối hoặc mức isolation phù hợp để luôn còn một nhân viên.

### Bài tập 14 — Transaction xuyên dịch vụ

Order ở MongoDB, kho ở DynamoDB, thanh toán qua HTTP và dashboard ở Redis. Liệt kê những bước có thể bảo vệ bằng transaction cục bộ, những bước cần saga/outbox/inbox, những trạng thái trung gian và cách đối soát khi payment timeout.

### Bài tập 15 — Bất biến và read model

Nguồn order đã chuyển PAID nhưng dashboard vẫn hiện PENDING trong 8 giây. Nếu hợp đồng cho phép dashboard trễ tối đa 30 giây, đây có nhất thiết là lỗi nguyên tử không? Hãy nêu các metric lag, retry, version và reconciliation để chứng minh bản đọc cuối cùng hội tụ.

### Bài tập 16 — Chọn ranh giới aggregate

Một đội muốn nhúng toàn bộ lịch sử order, payment và event vào document customer để “mọi thứ nguyên tử”. Hãy phân tích vấn đề kích thước, hot document, quyền, vòng đời; đề xuất ranh giới customer, order, inventory và payment hợp lý hơn.

### Bài tập 17 — Kế hoạch kiểm thử

Viết test plan cho tính năng giữ hàng gồm **concurrent requests**, **network timeout sau commit**, **rollback khi transaction thất bại**, **consumer nhận event trùng**, **failover replica** và **TTL cleanup trễ**. Với mỗi test, ghi trạng thái đầu, hành động, trạng thái được phép và bằng chứng quan sát.

### Bài tập 18 — Viết hợp đồng kỹ thuật

Chọn một API CreateReservation và mô tả bằng tài liệu ngắn: **identity key**, **single-unit atomicity boundary**, **conditional predicate**, **write concern/durability**, **idempotency key**, **kết quả khi conflict**, **timeout behavior**, **side effects ngoài transaction** và **metric đối soát**. Tránh mô tả mơ hồ kiểu “database tự đảm bảo”.

---

**Kết luận:** Tính nguyên tử trong NoSQL phải luôn được gắn với **một phạm vi có thể kiểm chứng**: một command, một key, một document/item, một row/partition theo ngữ nghĩa engine hoặc một transaction nhiều đơn vị được hỗ trợ. **Một lệnh không mặc nhiên nguyên tử trên mọi bản ghi nó đụng tới; một partition không mặc nhiên là một transaction; một ghi nguyên tử không tự chống được retry, lost update, write skew hay sự cố ngoài database.** Cách thiết kế đúng là viết bất biến trước, chọn đơn vị dữ liệu đủ nhỏ nhưng đủ bảo vệ, đưa điều kiện vào thao tác ghi, mở rộng bằng transaction/workflow khi cần, rồi kiểm chứng dưới đồng thời, lỗi mạng và failover. Khi ranh giới nguyên tử được nêu rõ, đội phát triển mới biết **điều gì được bảo đảm ngay**, **điều gì cần phối hợp** và **điều gì phải được đối soát về sau**.
