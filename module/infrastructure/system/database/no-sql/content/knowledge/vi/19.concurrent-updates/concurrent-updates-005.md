# Phép tăng/giảm nguyên tử và giới hạn phạm vi bảo đảm

Một hệ thống NoSQL lưu số lượng hàng còn bán:

~~~~json
{
  "sku": "BOOK-42",
  "available": 10
}
~~~~

Trong giờ cao điểm, 100 yêu cầu đặt hàng có thể đồng thời muốn giảm số lượng. Nếu mỗi ứng dụng Java **đọc available, tự trừ rồi ghi lại**, nhiều thao tác có thể dựa trên cùng một giá trị cũ, dẫn đến **lost update**: số lượng trong database không phản ánh đúng số lần đã bán.

Nhiều NoSQL cung cấp **phép tăng/giảm nguyên tử** như increment, decrement, add, atomic update hoặc counter. Những phép toán này giúp tránh đọc–sửa–ghi ở client cho một giá trị trong phạm vi được engine bảo đảm. Nhưng “nguyên tử” **không tự đồng nghĩa** không âm, không bán quá tồn kho, không ghi trùng khi retry, không mất dữ liệu sau failover, không có sai lệch giữa các bản sao, hoặc giao dịch đã bảo vệ nhiều document và dịch vụ.

Trong chương **Cập nhật đồng thời** của **Database No SQL**, bài học này giải thích chính xác phép tăng/giảm nguyên tử giải quyết vấn đề nào, đâu là **ranh giới atomicity**, cách kết hợp **điều kiện, version, idempotency và transaction**, và cách kiểm chứng chúng bằng ví dụ MongoDB, DynamoDB, Redis, Cassandra, HBase cùng Java.

> **Phạm vi:** API, bảo đảm nhất quán và độ bền thay đổi theo sản phẩm/phiên bản/cấu hình. Các câu lệnh là ví dụ mô hình hoặc API phổ biến; không thay thế kiểm tra tài liệu của database đang dùng. Các giá trị workload và kết quả hiệu năng là giả định để luyện tư duy.

## 1. Vì sao đọc–sửa–ghi dễ bị lost update?

Giả sử counter ban đầu bằng 10. Hai request muốn bán mỗi request một sản phẩm.

~~~~text
Thời gian         Request A                Request B
----------------------------------------------------------------
T0                Read stock = 10
T1                                         Read stock = 10
T2                Tính 10 - 1 = 9
T3                                         Tính 10 - 1 = 9
T4                Write stock = 9
T5                                         Write stock = 9
----------------------------------------------------------------
Kết quả DB = 9, dù đã xử lý hai lượt giảm.
Giá trị đúng nếu hai lượt giảm đều thành công = 8.
~~~~

Đây là **lost update**: hai writer tính toán từ cùng snapshot, writer sau ghi đè kết quả của writer trước.

Một triển khai Java không an toàn:

~~~~java
long current = inventoryRepository.getAvailable("BOOK-42");
long updated = current - 1;
inventoryRepository.setAvailable("BOOK-42", updated);
~~~~

Ba dòng code **không phải một thao tác nguyên tử** chỉ vì chúng nằm trong cùng một method hoặc vì biến Java là long. Nếu chạy nhiều instance của ứng dụng, dùng **synchronized** trong một JVM cũng không bảo vệ toàn hệ.

### 1.1. Phép giảm nguyên tử chuyển bước tính vào database

Thay vì đọc–tính–ghi:

~~~~text
Client A -> AtomicDecrement(stock, 1)
Client B -> AtomicDecrement(stock, 1)

Database áp dụng mỗi phép giảm như một thao tác nguyên tử
trên đối tượng được bảo vệ theo hợp đồng engine.
~~~~

Một lịch sử hợp lệ có thể là:

~~~~text
Ban đầu: 10
A: -1 -> 9
B: -1 -> 8
Cuối: 8
~~~~

Nếu cả hai operation thực sự được áp dụng đúng một lần, không có writer khác, kiểu số không overflow và counter không bị khởi tạo lại, kết quả là 8.

### 1.2. Atomic increment khác phép gán giá trị tuyệt đối

Hai kiểu cập nhật:

- **SET stock = 9:** đặt giá trị thành 9, không nói nó được suy ra từ trạng thái nào.
- **DECREMENT stock BY 1:** yêu cầu database lấy trạng thái hiện hành và áp dụng thay đổi -1 trong phạm vi atomicity của engine.

Một thao tác kiểu **SET** có thể vẫn an toàn nếu dùng **conditional write/version check hoặc transaction**. Vấn đề không phải cú pháp SET sai, mà là việc ứng dụng viết giá trị đã tính từ một bản đọc cũ mà không có hàng rào cạnh tranh.

## 2. “Nguyên tử” là một bảo đảm có phạm vi

**Atomicity** là một thuộc tính của **một tập thay đổi trong một ranh giới xác định**: theo hợp đồng engine, nó không bị nhìn thấy/thực thi như nhiều phần độc lập trái với ngữ nghĩa đã công bố.

Nhưng ranh giới ấy có thể là:

- **Một trường của một document**.
- **Nhiều trường trong cùng một document/item/row**.
- **Một lệnh trên một khóa**.
- **Nhiều item trong cùng transaction được database hỗ trợ**.
- **Một transaction có tính nhất quán theo phạm vi partition**.
- **Một script chạy trên một Redis node**, với hạn chế riêng về runtime errors và persistence.

Không có quy luật chung rằng “NoSQL chỉ atomic trên một hàng”, cũng không có quy luật chung rằng “mọi NoSQL hỗ trợ transaction tùy ý”. Phải đọc hợp đồng của **đúng thao tác, đúng engine, đúng cấu hình**.

### 2.1. Sáu câu hỏi phải hỏi trước khi tin một atomic counter

| Câu hỏi | Ví dụ |
| --- | --- |
| **Atomic với đối tượng nào?** | Một document BOOK-42 hay mọi item của cửa hàng? |
| **Tăng/giảm và điều kiện có nằm cùng thao tác không?** | Chỉ giảm khi available >= quantity |
| **Giá trị có được bảo vệ khỏi writer khác không?** | Writer dùng absolute SET có thể ghi đè không? |
| **Client nhận ACK ở mức durability nào?** | Một replica, quorum, majority, WAL flush? |
| **Sau mất ACK, retry có áp dụng lần nữa không?** | Trừ 1 hai lần dù chỉ một ý định? |
| **Đường đọc sau ghi có nhìn thấy kết quả mới không?** | Primary hay replica/GSI/cache trễ? |

Chỉ khi trả lời được những câu này mới có thể nói **counter đáp ứng nghiệp vụ nào**.

### 2.2. Atomicity khác isolation, durability, consistency và idempotency

| Thuộc tính | Mối quan tâm | Atomic increment tự bảo đảm? |
| --- | --- | --- |
| **Atomicity** | Không bị xé nhỏ trong phạm vi thao tác | Có, theo phạm vi được công bố |
| **Isolation** | Các thao tác đồng thời ảnh hưởng/nhìn nhau thế nào | Không suy ra isolation cho toàn bộ workflow |
| **Durability** | Giá trị đã ACK tồn tại sau crash/failover nào | Tùy cơ chế ghi và cấu hình |
| **Read consistency** | Reader thấy giá trị mới ngay không | Tùy replica/read mode |
| **Idempotency** | Retry cùng ý định có tạo thêm hiệu ứng không | **Không**, phép +1 thường không idempotent |
| **Business invariant** | Không âm, không vượt quota, không trừ tiền trùng | Cần điều kiện/giao dịch/ledger phù hợp |
| **Cross-item atomicity** | Hai key/document cùng cập nhật hoặc không | Chỉ khi có transaction được hỗ trợ bao trùm chúng |

Phép tăng **+1** có thể atomic nhưng nếu chạy hai lần thì giá trị vẫn tăng **+2**. Atomicity bảo vệ **một lần thực thi**, còn idempotency bảo vệ **nhiều lần gửi lại cùng một ý định**.

## 3. Atomic increment và conditional decrement là hai nhu cầu khác nhau

Với **page views**, có thể chấp nhận counter tăng sau mỗi lượt xem được nhận diện.

Với **tồn kho**, ta thường cần bất biến:

\[
\text{available} \ge 0
\]

Một lệnh atomic decrement đơn thuần không có nghĩa tự cấm số âm:

~~~~text
available = 0
AtomicDecrement(1)
available = -1
~~~~

Tính nguyên tử vẫn hoàn toàn đúng: thao tác giảm được áp dụng trọn vẹn, nhưng **bất biến nghiệp vụ đã bị vi phạm**.

### 3.1. Điều kiện và phép giảm phải thuộc cùng một ranh giới nguyên tử

Giả sử hai người cùng muốn mua món hàng cuối cùng:

~~~~text
available = 1

A: Read available=1
B: Read available=1
A: Decrement(1)
B: Decrement(1)

available = -1
~~~~

Cả hai phép giảm có thể **đều nguyên tử**, nhưng bước **kiểm tra trước đó** không được bảo vệ chung. Cách đúng về mặt nguyên lý:

~~~~text
ConditionalDecrement(key, qty):
    nếu available >= qty
        available := available - qty
        trả SUCCESS
    ngược lại
        không thay đổi
        trả INSUFFICIENT_STOCK
~~~~

**So sánh điều kiện và ghi phải được engine thực hiện như một đơn vị atomic**. Đừng biến nó thành hai request độc lập GET rồi DECR.

### 3.2. Ba bất biến khác nhau

Cần phân biệt:

1. **Không mất lượt tăng/giảm:** mỗi operation được áp dụng đúng theo khả năng atomic của engine.
2. **Không âm:** chỉ chấp nhận giảm khi giá trị hiện hành đủ lớn.
3. **Không trừ lặp cùng ý định:** retry một operationId không trừ thêm lần thứ hai.

Một conditional decrement có thể giải quyết (1) và (2) nhưng **chưa giải quyết (3)** nếu client gửi lại một request mới sau timeout.

### 3.3. Số lượng giảm không phải lúc nào bằng 1

Với quantity có thể lớn hơn 1, điều kiện phải được tính theo quantity hợp lệ:

~~~~text
available = 5

Request A: reserve 3
Request B: reserve 3

Chỉ một request được phép thành công.
Request còn lại phải nhận conflict/insufficient stock.
~~~~

Trước khi gửi lệnh:

- Kiểm tra **quantity > 0**.
- Kiểm tra giới hạn quantity theo nghiệp vụ.
- Kiểm tra đơn vị đo là **chiếc, kg, cent, lượt** hay thứ khác.
- Đảm bảo phép trừ không overflow kiểu số.
- Gắn operationId nếu cần chống retry.

Không cho client gửi quantity = -3 vào lệnh **decrement by quantity** vì như vậy nó có thể thành phép tăng kho.

## 4. MongoDB: $inc trên một document

MongoDB có toán tử **$inc** để thay đổi trường số, không cần client tự đọc rồi gán giá trị tuyệt đối.

Ví dụ:

~~~~javascript
db.inventory.updateOne(
  { _id: "BOOK-42" },
  { $inc: { available: -1 } }
);
~~~~

Nếu nhiều writer cùng gọi thao tác cập nhật trường trong **cùng document**, MongoDB duy trì tính nguyên tử của từng thao tác update trên document theo hợp đồng của engine. Một writer không cần biết trước số lượng hiện tại để yêu cầu giảm 1.

### 4.1. Không được âm thầm cho stock về âm

Cập nhật có điều kiện:

~~~~javascript
const qty = 3;

const result = db.inventory.updateOne(
  {
    _id: "BOOK-42",
    available: { $gte: qty }
  },
  {
    $inc: {
      available: -qty,
      version: 1
    }
  }
);

if (result.matchedCount === 0) {
  // Không thấy document phù hợp điều kiện.
  // Có thể SKU không tồn tại hoặc không đủ hàng.
}
~~~~

**Predicate available >= qty và $inc nằm trong cùng một updateOne**, nên các writer cạnh tranh trên cùng document không thể cùng vượt qua điều kiện dựa trên một trạng thái đã bị writer khác thay đổi.

Điều kiện này có ý nghĩa khi:

- available có kiểu số hợp lệ.
- quantity dương và được validate.
- Mọi đường thay đổi available đều tuân thủ invariant tương thích.
- Không có bug hoặc job maintenance chủ động đặt stock âm.
- Kết quả update được đọc/diễn giải theo write concern phù hợp.

Không suy ra **matchedCount = 0** chỉ mang nghĩa “hết hàng”: document có thể không tồn tại, field có kiểu không đúng hoặc điều kiện khác không thỏa.

### 4.2. $inc có hành vi riêng khi trường thiếu/null

Trong MongoDB, **$inc** có thể tạo trường số khi trường chưa tồn tại theo quy tắc của operator, nhưng một trường **null** hoặc dữ liệu không tương thích có thể gây lỗi. Nếu available là field bắt buộc, hãy validate schema và không dựa vào việc field thiếu được mặc định theo mong muốn.

Một kho hàng mới chưa có available không nên tự “tăng thành 1” trừ khi nghiệp vụ đã định nghĩa rõ.

### 4.3. Cập nhật nhiều field trong cùng document

Ví dụ cùng document lưu:

~~~~json
{
  "_id": "BOOK-42",
  "available": 5,
  "reserved": 2,
  "sold": 10,
  "version": 18
}
~~~~

Một thao tác:

~~~~javascript
db.inventory.updateOne(
  {
    _id: "BOOK-42",
    available: { $gte: 2 }
  },
  {
    $inc: {
      available: -2,
      reserved: 2,
      version: 1
    }
  }
);
~~~~

Trong phạm vi **một document update**, các trường liên quan được cập nhật cùng nhau theo atomicity của update. Nhưng nếu một service khác lưu **order** ở document khác, thao tác này không tự tạo order trong cùng transaction.

### 4.4. Java driver: giảm tồn kho có điều kiện

Ví dụ với MongoDB Java driver:

~~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.inc;

public final class InventoryRepository {
    private final MongoCollection<Document> inventory;

    public InventoryRepository(MongoCollection<Document> inventory) {
        this.inventory = inventory;
    }

    public boolean reserve(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        UpdateResult result = inventory.updateOne(
                and(eq("_id", sku), gte("available", quantity)),
                combine(
                        inc("available", -quantity),
                        inc("reserved", quantity),
                        inc("version", 1)
                )
        );

        return result.getMatchedCount() == 1;
    }
}
~~~~

Đoạn code minh họa **một lần cập nhật có điều kiện**. Nó chưa giải quyết:

- Retry sau khi mất ACK.
- Ghi booking/order ở document khác.
- Audit và operation ledger.
- Chọn write concern và cơ chế phục hồi sau failover.
- Cách trả kết quả khi update không match.

**Không tự động gọi reserve lần nữa với một operationId mới khi gặp network timeout.**

### 4.5. Transaction đa document khi cần

Nếu yêu cầu “giảm stock và tạo order” phải được commit cùng nhau, có thể dùng **multi-document transaction** trên MongoDB khi đáp ứng điều kiện/giới hạn của sản phẩm.

~~~~text
BEGIN TRANSACTION
  Conditional decrement Inventory BOOK-42
  Insert Order O-901
  Insert OperationResult OP-101
  Insert Outbox OrderCreated
COMMIT
~~~~

Cần thực hiện các thao tác dưới **cùng session/transaction** và xử lý xung đột, retry/unknown commit result đúng theo driver. Không nên cho rằng chỉ cần gọi nhiều updateOne liên tiếp trong một method Java là chúng tự trở thành transaction.

## 5. DynamoDB: atomic update theo item và condition

DynamoDB có **UpdateItem** cho phép cập nhật một item và biểu thức điều kiện.

Ví dụ mô hình dữ liệu:

~~~~text
Table Inventory
  PK: SKU#BOOK-42
  available: N(5)
  reserved: N(2)
  version: N(18)
~~~~

Một lệnh UpdateItem có điều kiện:

~~~~text
ConditionExpression:
  attribute_exists(PK) AND available >= :qty

UpdateExpression:
  SET available = available - :qty,
      reserved = reserved + :qty,
      version = version + :one
~~~~

Trong thực tế, phải dùng **ExpressionAttributeNames/Values** để ánh xạ tên thuộc tính và tham số, nhất là tên trùng từ khóa hoặc thuộc tính tùy biến.

### 5.1. Ví dụ SDK Java v2

~~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.ReturnValue;
import software.amazon.awssdk.services.dynamodb.model.UpdateItemRequest;
import software.amazon.awssdk.services.dynamodb.model.UpdateItemResponse;

public final class DynamoInventory {
    private final DynamoDbClient client;

    public DynamoInventory(DynamoDbClient client) {
        this.client = client;
    }

    public UpdateItemResponse reserve(String sku, long quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        return client.updateItem(UpdateItemRequest.builder()
                .tableName("Inventory")
                .key(Map.of(
                        "PK", AttributeValue.builder()
                                .s("SKU#" + sku).build()
                ))
                .conditionExpression(
                        "attribute_exists(#pk) AND #available >= :qty"
                )
                .updateExpression(
                        "SET #available = #available - :qty, " +
                        "#reserved = #reserved + :qty, " +
                        "#version = #version + :one"
                )
                .expressionAttributeNames(Map.of(
                        "#pk", "PK",
                        "#available", "available",
                        "#reserved", "reserved",
                        "#version", "version"
                ))
                .expressionAttributeValues(Map.of(
                        ":qty", AttributeValue.builder()
                                .n(Long.toString(quantity)).build(),
                        ":one", AttributeValue.builder().n("1").build()
                ))
                .returnValues(ReturnValue.ALL_NEW)
                .build());
    }
}
~~~~

Ví dụ giả định các field **available, reserved, version đã tồn tại với kiểu N hợp lệ**. Một số tình huống thiếu field cần dùng cách khởi tạo có kiểm soát, chẳng hạn if_not_exists trong biểu thức phù hợp, nhưng không nên tự cho số lượng tồn kho thiếu bằng 0 nếu đó là dấu hiệu record sai schema.

Một **ConditionalCheckFailedException** xác định điều kiện không thỏa cho attempt đó, còn **network timeout sau khi gửi request** không tự chứng minh UpdateItem chưa được áp dụng. Khi dùng cho booking quan trọng, vẫn cần idempotency.

### 5.2. ADD và SET arithmetic

DynamoDB hỗ trợ những biểu thức cập nhật số, trong đó có **ADD** và **SET arithmetic**. Chọn hình thức theo field và semantics.

Ví dụ cập nhật số lượt:
 
~~~~text
ADD viewCount :one
~~~~

Với stock, nên dùng **condition và update** trong cùng thao tác để chặn vượt hạn. **ADD -1** không tự cấm âm nếu không có condition thích hợp.

### 5.3. Multi-item TransactWriteItems

Nếu cần ghi:

~~~~text
Inventory item
Order item
OperationResult item
Outbox item
~~~~

như một giao dịch, **TransactWriteItems** có thể là một lựa chọn trong giới hạn được dịch vụ hỗ trợ. Cần ghi rõ các điều kiện, key và số item, và lưu ý không thể tùy tiện thao tác nhiều hành động trên cùng item trong một transaction theo các ràng buộc của API.

**ClientRequestToken** của TransactWriteItems hỗ trợ idempotency trong một **cửa sổ giới hạn** theo hợp đồng dịch vụ. Đối với retry sau nhiều ngày hoặc workflow payment, cần thêm **operation ledger/business key bền vững**.

### 5.4. Replica và GSI là vấn đề khác

Một UpdateItem đã commit ở bảng nguồn không đồng nghĩa một query trên **Global Secondary Index** đã thấy số lượng mới. GSI được cập nhật bất đồng bộ; nếu dùng GSI để quyết định còn hàng rồi decrement ở nguồn, decision phải được xác minh bằng condition tại bảng chính.

**Không dùng một con số stock trên search index hoặc GSI eventual làm điều kiện cuối cùng để bán.**

## 6. Redis: INCRBY, DECRBY và giới hạn của chúng

Redis hỗ trợ những lệnh như:

~~~~redis
SET counter:views:post-42 100
INCR counter:views:post-42
INCRBY counter:views:post-42 10
DECRBY counter:views:post-42 3
GET counter:views:post-42
~~~~

Các lệnh increment/decrement trên một key được thực thi nguyên tử theo mô hình xử lý lệnh của Redis instance. Hai client đồng thời gọi INCR không cần tự GET rồi SET lại.

### 6.1. Atomic command không bảo đảm không âm

~~~~redis
SET stock:BOOK-42 0
DECRBY stock:BOOK-42 1
GET stock:BOOK-42
~~~~

Giá trị có thể thành **-1**. Không có điều kiện “chỉ trừ nếu đủ hàng” trong DECRBY mặc định.

### 6.2. Lua script để kết hợp điều kiện và giảm

Một script thực thi trên Redis có thể kiểm tra trạng thái và giảm trong cùng lần gọi:

~~~~lua
-- KEYS[1]: stock key
-- ARGV[1]: positive quantity (validated by caller)
local raw = redis.call('GET', KEYS[1])
if not raw then
    return redis.error_reply('STOCK_NOT_FOUND')
end

local qty = tonumber(ARGV[1])
if not qty or qty <= 0 or qty ~= math.floor(qty) then
    return redis.error_reply('INVALID_QUANTITY')
end

local stock = tonumber(raw)
if not stock then
    return redis.error_reply('INVALID_STOCK_VALUE')
end

if stock < qty then
    return 0
end

local remaining = redis.call('DECRBY', KEYS[1], qty)
return remaining
~~~~

Ý tưởng: **kiểm tra điều kiện và thay đổi nằm trong một script chạy không bị lệnh khác xen giữa trên cùng Redis execution context**.

Nhưng:
- Không được hiểu **atomic execution** là commit bền qua mọi crash.
- Nếu script thực hiện nhiều write rồi gặp runtime error, Redis không cung cấp rollback kiểu relational cho những write đã thực thi.
- Script cần kiểm tra input và trường hợp lỗi **trước khi thay đổi** nếu có thể.
- Redis Cluster yêu cầu các key liên quan trong một multi-key operation/script phải phù hợp quy tắc hash slot và các hạn chế cluster.
- Script trên stock key không tự tạo một order ở một database khác.
- Timeout sau EVAL vẫn có thể dẫn tới kết quả UNKNOWN cho client.

Đối với giá trị số nguyên lớn, phải chú ý **phạm vi integer của Redis** và cách Lua xử lý number; cần kiểm tra miền số/precision ở cả client, script và câu lệnh, không giả định mọi số nguyên Java long có thể diễn giải không mất mát trong mọi phép toán Lua.

### 6.3. WATCH/MULTI/EXEC

Một workflow có thể dùng **WATCH** để giám sát key, đọc trước, rồi **MULTI/EXEC** để commit nếu key chưa thay đổi:

~~~~text
WATCH stock:BOOK-42
GET stock:BOOK-42
# client kiểm tra stock >= quantity
MULTI
DECRBY stock:BOOK-42 quantity
EXEC
~~~~

Nếu key được thay đổi trước EXEC theo ngữ nghĩa WATCH, transaction có thể không được thực thi và client cần retry từ đầu. **Không dùng GET rồi DECRBY mà thiếu WATCH/script/guard**.

Lưu ý **MULTI/EXEC không cung cấp rollback kiểu relational khi một lệnh bên trong EXEC lỗi ở runtime**. Lua script và Redis transaction cũng không mở rộng atomicity sang payment provider hoặc NoSQL store khác.

### 6.4. Persistence và failover

Redis có cơ chế persistence/replication tùy cấu hình. Một command thực thi nguyên tử ở instance không nhất thiết **bền qua mất điện hoặc đã được nhân bản tới node sẽ trở thành leader**. Cần đọc hợp đồng durability/replication trước khi dùng một Redis counter làm **sổ cái tài chính** hoặc nguồn duy nhất cho số lượng đặt chỗ đã xác nhận.

Dùng Redis cho cache, rate-limiting hoặc approximate counters có thể phù hợp; dùng nó cho strict inventory cần thiết kế chặt hơn về persistence, recovery và idempotency.

## 7. Cassandra: counter column khác LWT trên cột thường

Cassandra cung cấp kiểu **counter** với ngữ nghĩa cập nhật tăng/giảm. Ví dụ:

~~~~sql
CREATE TABLE page_views_by_day (
    page_id text,
    day_bucket date,
    views counter,
    PRIMARY KEY ((page_id), day_bucket)
);
~~~~

Một lần tăng:

~~~~sql
UPDATE page_views_by_day
SET views = views + 1
WHERE page_id = 'post-42'
  AND day_bucket = '2026-11-14';
~~~~

Counter hỗ trợ workload đếm phân tán theo mô hình Cassandra, nhưng **không nên coi nó là primitive phù hợp cho mọi bất biến giao dịch**.

### 7.1. Counter update không idempotent dưới retry

Nếu client gửi tăng 1, server xử lý rồi ACK mất, client gửi lại tăng 1:

~~~~text
Lần 1: +1 đã áp dụng, ACK mất
Lần 2: +1 được gửi lại
Kết quả có thể tăng tổng cộng 2.
~~~~

Một counter increment **không phải phép SET idempotent**. Retry không kiểm soát có thể khiến đếm trùng. Với Cassandra, còn phải xem consistency, replication, cơ chế counter và timeout cụ thể để xác định khả năng đọc/hội tụ của counter.

### 7.2. Counter table có giới hạn schema và thao tác

Cassandra có những quy tắc riêng cho bảng chứa counter, không được tùy tiện kết hợp counter columns và các cột thường trong cùng một bảng như một bảng nghiệp vụ thông thường. Counter updates cũng không phải lời giải thay thế trực tiếp cho **lightweight transaction (LWT) với điều kiện stock >= qty**.

Nếu bài toán cần **không âm tuyệt đối**, có thể dùng cột thường với compare-and-set LWT trong một phạm vi phù hợp.

Ví dụ khái niệm trên bảng inventory có cột thường:

~~~~sql
-- Sau khi đọc và thấy available=10:
UPDATE inventory
SET available = 9
WHERE sku = 'BOOK-42'
IF available = 10;
~~~~

Hai writer cùng dựa trên available=10 chỉ có thể nhận kết quả áp dụng điều kiện phù hợp với LWT; writer còn lại phải đọc lại và tính lại.

**Điểm cần hiểu:** Cassandra không cung cấp phép **available = available - 1** tổng quát như một biểu thức cập nhật cột số thường để vừa tính vừa kiểm tra stock. Với cột thường, ví dụ dùng **CAS với giá trị cũ** và lặp lại có kiểm soát; với counter column, ngữ nghĩa và giới hạn khác.

### 7.3. CAS cũng cần idempotency cho nghiệp vụ

Nếu LWT cập nhật stock từ 10 xuống 9 và response mất, client không nên tạo một ý định giảm mới không có ID. Một lần đọc có thể thấy available=9, nhưng không chứng minh **ai đã giảm** nếu có writer khác.

Nếu cần xác nhận “OP-101 đã reserve”, lưu operationId hoặc ledger theo ranh giới atomic hỗ trợ. Trường hợp nhiều partition hoặc nhiều bước yêu cầu thiết kế khác; **LWT một hàng không tự bao trùm toàn bộ order workflow**.

## 8. HBase: increment theo row và ranh giới khác

HBase hỗ trợ atomic operations trong phạm vi row theo contract của HBase, trong đó có **Increment**. Ứng dụng Java có thể cộng số lượt xem vào một cell của một row.

Ví dụ ý tưởng với HBase Java API:

~~~~java
import org.apache.hadoop.hbase.client.Increment;
import org.apache.hadoop.hbase.client.Result;
import org.apache.hadoop.hbase.client.Table;
import org.apache.hadoop.hbase.util.Bytes;

public class ViewCounter {
    public long incrementView(Table table, String pageId)
            throws java.io.IOException {
        byte[] rowKey = Bytes.toBytes(pageId);

        Increment increment = new Increment(rowKey);
        increment.addColumn(
                Bytes.toBytes("stats"),
                Bytes.toBytes("views"),
                1L
        );

        Result result = table.increment(increment);
        return Bytes.toLong(
                result.getValue(
                        Bytes.toBytes("stats"),
                        Bytes.toBytes("views")
                )
        );
    }
}
~~~~

Code giả định column family **stats** tồn tại và cell được lưu theo kiểu số tương thích. Một row-level atomic increment không biến hai row khác nhau hoặc hai bảng khác nhau thành transaction chung.

Với yêu cầu **kiểm tra stock trước khi giảm**, cần cơ chế compare-and-mutate/check-and-mutate hoặc phương án transaction tương ứng được HBase/version hỗ trợ, thay vì đoán rằng increment tự chặn âm.

Ngoài ra, sau network timeout, việc đọc counter cuối cùng không luôn xác định được phép tăng nào của một client đã được áp dụng: cần **operation identity** nếu ngữ nghĩa không cho phép lặp.

## 9. Counter nguyên tử và giới hạn đa document

Giả sử đơn hàng chứa hai SKU:

~~~~text
Order O-901:
  2 x SKU-A
  1 x SKU-B
~~~~

Cần giảm:

~~~~text
Inventory SKU-A: -2
Inventory SKU-B: -1
Create Order O-901
~~~~

Nếu dùng ba atomic write riêng:

~~~~text
1. SKU-A giảm thành công.
2. SKU-B giảm thất bại do hết hàng.
3. Order chưa được tạo.
~~~~

Kết quả là một **phần** của tác vụ nghiệp vụ đã thành công. Tính nguyên tử ở **mỗi item** không làm toàn bộ workflow trở nên nguyên tử.

### 9.1. Những lựa chọn kiến trúc

**A. Multi-item transaction nếu hệ hỗ trợ:**

~~~~text
BEGIN
  Conditional reserve SKU-A
  Conditional reserve SKU-B
  Insert Order O-901
  Insert OperationResult OP-101
COMMIT
~~~~

Phải kiểm tra giới hạn transaction, phân vùng, chi phí, isolation, và cách retry khi commit outcome unknown.

**B. Thiết kế lại aggregate để bất biến nằm cùng một đơn vị:**

Nếu số lượng nhỏ và phù hợp với access pattern, có thể lưu các counter có liên quan trong cùng document/row; không lạm dụng document lớn đến mức vượt giới hạn kích thước/hot key.

**C. Saga/reservation workflow:**

~~~~text
Reserve SKU-A
Reserve SKU-B
Nếu thất bại ở bất kỳ bước:
  Release những reservation đã thành công
Nếu thành công:
  Confirm Order
~~~~

Tất cả các bước cần **idempotency, trạng thái pending, timeout và compensation**. Compensation là một hành động mới, không phải rollback tự động qua các service.

### 9.2. Không thể dùng nhiều atomic counters độc lập để bảo đảm tổng bất biến

Giả sử quota toàn công ty:

\[
\text{usedA} + \text{usedB} \le \text{limit}
\]

Mỗi team cập nhật một counter riêng:

~~~~text
Team A: usedA += 5
Team B: usedB += 5
~~~~

Dù từng phép tăng nguyên tử, **tổng** có thể vượt limit nếu kiểm tra tổng ở những read cũ. Cần ranh giới ghi chung, transaction, phân bổ hạn mức trước hoặc một cơ chế **escrow/rights allocation** phù hợp.

## 10. Đếm và đặt chỗ: tại sao hai bài toán nên tách?

Không phải mọi counter đều cần bảo đảm giống nhau.

| Tình huống | Hậu quả khi đếm trùng/trễ | Mô hình có thể phù hợp |
| --- | --- | --- |
| Số lượt xem bài viết | Sai số nhỏ có thể chấp nhận trong ngắn hạn | Counter phân tán, tổng hợp eventual |
| Lượt click quảng cáo dùng để thanh toán | Đếm trùng ảnh hưởng hóa đơn | Event dedup theo ID, ledger, reconciliation |
| Rate limiter | Vượt giới hạn ngắn hạn có thể nguy hiểm | Atomic limit check trong kho phù hợp |
| Số email đã gửi | Retry có thể gửi lại thư | Idempotency/provider key và delivery ledger |
| Tồn kho | Âm hoặc oversell vi phạm bán hàng | Conditional decrement, reservation, transaction |
| Số dư ví | Trừ trùng gây thiệt hại tài chính | Ledger giao dịch và invariant bền vững |
| Quota API | Cần phân biệt quota cứng và mềm | Conditional counter hoặc token bucket |
| Thống kê theo phút | Có thể hiển thị trễ vài giây | Sharded/aggregated counters |
| Số lượng người đang online | Chịu ảnh hưởng TTL/heartbeat | Approximate presence với hạn dùng |
| Hạn mức đặt phòng | Phải chặn giữ slot trùng | Slot-level conditional guard, không chỉ counter |

Nếu dùng một thiết kế cho cả **page views** và **debit ví tiền**, hoặc rất đắt hoặc không đủ đúng.

### 10.1. Counter cho tiền: đơn vị số phải chính xác

Không dùng double cho tiền cần tính chính xác. Một ví có thể lưu:

~~~~text
balanceMinor = 100000    // ví dụ đơn vị nhỏ nhất theo currency contract
~~~~

Lệnh trừ cần:
- Kiểm tra số tiền dương, giới hạn giá trị.
- Kiểm tra balance >= amount.
- Thực hiện guard và decrement nguyên tử.
- Gắn paymentOperationId/ledger để chống retry.
- Ghi audit transaction với trạng thái final.
- Bảo vệ tính đúng qua failover/restore.

**Một counter balance** có thể là projection giúp đọc nhanh, nhưng **ledger bất biến các bút toán** thường cần thiết trong các nghiệp vụ tài chính có yêu cầu kiểm toán và đối soát.

## 11. Retry sau timeout: atomicity không chống double increment

Giả sử metric event count ban đầu là 100. Client gửi INCREMENT +1.

~~~~text
T0: Client send +1
T1: Database áp dụng -> 101
T2: ACK bị mất
T3: Client timeout
T4: Client retry +1 như một operation mới
T5: Database áp dụng -> 102
~~~~

Mỗi lần +1 đều atomic. Nhưng về mặt nghiệp vụ, chỉ có **một event gốc** và kết quả mong muốn là 101.

### 11.1. Điểm khác nhau giữa atomic và idempotent

Một hàm **idempotent** thỏa ý nghĩa:

\[
f(f(x)) = f(x)
\]

Ví dụ gán một trạng thái cụ thể (khi không có xung đột và điều kiện khác) có thể có tính idempotent:

~~~~text
set active = true
set active = true
~~~~

Trong khi:

~~~~text
increment 1
increment 1
~~~~

không idempotent.

**Điều này không có nghĩa SET luôn an toàn:** việc gán từ một lần đọc cũ có thể gây lost update hoặc xóa field mới. Idempotency và concurrency correctness là hai vấn đề độc lập.

### 11.2. Operation ledger hoặc dedup marker

Một ý định có ID riêng:

~~~~json
{
  "operationId": "OP-101",
  "sku": "BOOK-42",
  "quantity": 2,
  "status": "COMMITTED",
  "reservationId": "RES-901"
}
~~~~

Một transaction hợp lý:

~~~~text
IF operationId OP-101 đã COMMITTED:
  Trả lại reservationId cũ.

ELSE atomically:
  Kiểm tra available >= 2.
  available -= 2.
  reserved += 2.
  Tạo reservation RES-901.
  Ghi OperationResult OP-101 -> RES-901, COMMITTED.
~~~~

Nếu mất ACK, client **retry cùng OP-101**. Ledger giúp phân biệt cùng ý định với một lượt mua mới.

### 11.3. Không đặt dedup record ở bên ngoài transaction mà không có cơ chế phục hồi

Flow sai:

~~~~text
1. Decrement stock.
2. Save processedOperationId.
~~~~

Nếu process chết sau 1 nhưng trước 2, retry không tìm thấy dedup ID và giảm thêm. Đảo thứ tự cũng có vấn đề:

~~~~text
1. Save processedOperationId.
2. Decrement stock.
~~~~

Nếu chết sau 1, hệ có thể tưởng operation đã thành công dù stock chưa giảm.

Nếu không thể ghi hai phần nguyên tử, phải dùng mô hình **state machine + reconciliation/saga có hàng rào** hoặc thay đổi cách đặt dữ liệu để đảm bảo tính đúng.

### 11.4. Không tin read model eventual để kiểm tra retry

Một event đã commit nhưng **search index/GSI/cache** chưa bắt kịp có thể trả “không thấy OP-101”. Điều này không chứng minh decrement chưa xảy ra. Tra **nguồn có thẩm quyền theo consistency phù hợp** và retry dưới cùng operationId.

## 12. Unknown commit result và không suy diễn từ lỗi mạng

Khi client không nhận được ACK của phép tăng/giảm, có thể xảy ra:

~~~~text
Case A: Request chưa tới database.
Case B: Database reject điều kiện.
Case C: Database áp dụng decrement, ACK bị mất.
Case D: Server đang tiếp tục xử lý khi client đã timeout.
~~~~

Tất cả có thể biểu hiện bằng network timeout ở client. Do đó client phải dùng trạng thái **UNKNOWN**, không lập tức retry như một hành động mới.

Mẫu xử lý:

~~~~text
submit(operationId, sku, qty):
  response = sendConditionalReservation(operationId, sku, qty)

  if response == committed:
      return success(existingReservationId)

  if response == knownConflict:
      return insufficientStockOrConflict

  if response == timeout:
      return unknownAndReconcile(operationId)
~~~~

**Hết deadline của HTTP client không tự cancel thao tác đã gửi.** Chỉ khi cơ chế server cung cấp một bằng chứng terminal mới có thể kết luận không commit.

### 12.1. Retryable write ở driver có phạm vi giới hạn

Một số driver/database cung cấp **retryable writes** và cơ chế nhận diện cùng logical write request. Điều này có thể giúp tránh áp dụng lại một write trong **phạm vi hợp đồng cụ thể** của driver.

Nhưng điều đó **không đồng nghĩa** mọi request API có thể retry mãi với một payload mới và operationId mới. SDK retry, ứng dụng retry, gateway retry và worker retry là các lớp khác nhau.

Hãy biết:
- Driver tự retry những loại thao tác nào?
- Transaction commit unknown được xử lý ra sao?
- Retry identity tồn tại trong bao lâu và qua failover nào?
- Có cần application-level idempotency cho booking/payment không?

### 12.2. Một read “không thấy operation” chưa đủ

Ngay cả khi truy vấn source mạnh, request cũ có thể đang in-flight và **commit sau lần đọc**. Muốn chống lặp, cần **unique/conditional guard** bảo vệ operationId hoặc một transaction identity phù hợp.

Đừng thay “không thấy trong cache” bằng “không thấy ở primary” rồi tưởng đã giải quyết hoàn toàn vấn đề nếu hai request cùng operationId vẫn có thể vượt qua điều kiện tạo mới.

## 13. Counter sharding: giảm hot key, đánh đổi đọc và tính đúng

Một counter được tất cả writer cập nhật có thể trở thành **hot key/hot partition**:

~~~~text
viewCount:popular-post
  Writer 1 -> +1
  Writer 2 -> +1
  ...
  Writer 50.000 -> +1
~~~~

Dù mỗi phép tăng atomic, một key có thể phải phục vụ lượng update vượt khả năng của storage partition/node. Dấu hiệu:
- p99 tăng khi traffic tập trung.
- Throttling/queuing/lock contention.
- Throughput không tăng tuyến tính khi thêm app instances.
- Một shard nóng hơn hẳn phần còn lại.
- Retry storm khi client timeout.

### 13.1. Sharded counters

Thay vì một key:

~~~~text
views:post-42:shard-00
views:post-42:shard-01
views:post-42:shard-02
...
views:post-42:shard-31
~~~~

Mỗi event được phân vào một shard. Tổng:

\[
\text{views} = \sum_{i=0}^{31}\text{shard}_i
\]

Điều này có thể phân tán write load. Nhưng:
- Đọc tổng phải lấy nhiều shard hoặc một projection tổng hợp.
- Tổng có thể stale nếu dùng read eventual.
- Một shard bị mất/dedup lỗi làm tổng sai.
- Thay số shard cần kế hoạch migration/aggregation.
- Một event retry có thể được chuyển sang shard khác nếu không có **mapping deterministic theo eventId**, gây đếm trùng.

### 13.2. Có nên dùng sharded counter để giữ inventory không âm?

Không mặc định.

Giả sử tổng available từ 10 shard bằng 5. Hai request ở hai vùng cùng đọc tổng 5 và giảm trên **hai shard khác nhau**. Mỗi shard giảm nguyên tử, nhưng hệ **không có điểm bảo vệ tổng invariant**; tổng có thể âm.

Với inventory có giới hạn cứng, dùng:
- Một điểm atomic guard có khả năng chịu tải phù hợp.
- Transaction hỗ trợ invariant.
- Hoặc phân bổ quyền giữ hàng trước bằng **escrow/bounded counter** với quy tắc chuyển quyền chặt chẽ.

Đừng dùng sharding chỉ để giải quyết hot partition rồi phá bất biến nghiệp vụ.

## 14. CRDT counters và phạm vi hội tụ

Trong một số hệ phân tán, **CRDT counter** hỗ trợ nhiều replica tăng/giảm độc lập rồi merge trạng thái mà vẫn hội tụ về một kết quả theo thiết kế.

Ví dụ **PN-counter** về mặt khái niệm giữ hai thành phần:

~~~~text
P: số lần tăng
N: số lần giảm
Giá trị = P - N
~~~~

Các thành phần có thể được tách theo replica và hợp nhất bằng phép toán phù hợp.

Ưu điểm:
- Có thể tiếp nhận update tại nhiều replica khi mạng phân vùng.
- Merge có thể hội tụ mà không cần đồng bộ từng increment.
- Hữu ích cho thống kê chịu được eventual consistency.

Giới hạn:
- Đọc giữa các replica có thể khác nhau trong khi chưa đồng bộ.
- Counter có thể **âm**, trừ khi có cơ chế bổ sung.
- CRDT không tự hiểu event nào là duplicate do retry cùng ý định.
- Không tự bảo đảm invariant liên quan tới **hai counter** hoặc một giao dịch payment.
- Cần biết đúng CRDT implementation để xử lý identity, merge và retention.

### 14.1. Escrow/bounded counter cho quota cứng

Một ý tưởng khác là phân bổ trước **quyền giảm** cho các vùng:

~~~~text
Global stock = 100

Region A được quyền reserve tối đa 40
Region B được quyền reserve tối đa 35
Region C được quyền reserve tối đa 25
Tổng quyền = 100
~~~~

Mỗi region có thể giảm **trong phạm vi quyền đã được cấp** mà không phải đồng bộ tới mọi region cho từng request, nếu quy tắc cấp/chuyển quyền được bảo vệ đúng.

Nhưng:
- Chuyển quyền giữa region phải tránh double spend.
- Khi region mất kết nối, phần quyền của nó có thể tạm không dùng được.
- Thêm stock hoặc hủy reservation phải cập nhật quyền hợp lệ.
- Recovery, duplicate messages và failover cần kiểm chứng.

Escrow là một **thiết kế phân tán chuyên biệt**, không phải một cờ bật trong mọi NoSQL counter API.

## 15. Atomicity và read consistency: vì sao reader có thể thấy giá trị cũ?

Giả sử UpdateItem của inventory vừa trả success, nhưng trang listing đọc từ **search index hoặc replica**.

~~~~text
T0  Source available: 5 -> 4 (committed)
T1  Listing read model còn available: 5
T2  Pipeline cập nhật read model thành 4
~~~~

Phép giảm tại source vẫn atomic. Vấn đề nằm ở **độ mới của đường đọc khác**.

Một số quyết định:
- UI listing có thể hiển thị số lượng **ước lượng**.
- Trang chi tiết nên đọc số lượng mới hơn khi cần.
- Checkout phải **condition tại nguồn có thẩm quyền**, không tin index stale.
- Admin cần **read-your-writes** có thể mang version token và đọc nguồn nếu projection chưa bắt kịp.

**Atomic write không tự làm mọi replica, cache và projection đồng bộ ngay**.

### 15.1. Đọc kết quả trả về từ phép tăng

Một số API trả **giá trị mới** sau update, ví dụ trả UPDATED_NEW/ALL_NEW hoặc kết quả INCRBY. Điều này giúp client không phải GET thêm.

Nhưng cần phân biệt:
- Giá trị trả về có phải giá trị **sau thao tác** không?
- Nó có phản ánh state được chấp nhận theo write concern nào?
- Nếu response mất, client biết gì?
- Nếu nhiều writer tiếp tục ghi sau đó, giá trị trả về có thể không còn là state hiện tại.

Một số hệ có thể trả giá trị cũ hoặc mới tùy cấu hình; đừng suy ra từ tên gọi “update” mà không xem ReturnValues.

### 15.2. Snapshot reads và số liệu tổng hợp

Một request tính tổng nhiều shard tại các thời điểm khác nhau có thể nhìn thấy **snapshot không đồng nhất** nếu engine không cung cấp snapshot read cho toàn bộ các shard. Ngay cả khi từng GET atomic, tổng có thể không tương ứng với một thời điểm duy nhất.

Nếu báo cáo yêu cầu đối soát tài chính tại thời điểm đóng sổ, có thể cần snapshot/checkpoint hoặc ledger với cutoff rõ ràng.

## 16. Số nguyên, overflow, kiểu dữ liệu và đơn vị

Phép tăng/giảm nguyên tử chỉ có thể đúng khi **kiểu dữ liệu và miền giá trị** được kiểm soát.

### 16.1. Không để số nguyên tràn

Java long có giới hạn. Với thao tác tính số lượng ở tầng Java:

~~~~java
long newValue = Math.addExact(current, delta);
~~~~

**Math.addExact** ném ArithmeticException khi phép cộng vượt phạm vi long. Nhưng với phép tăng do database tính, ứng dụng còn phải kiểm tra:
- Kiểu số storage engine hỗ trợ.
- Hành vi overflow/truncation/error của engine.
- Kiểu trả về của driver có thể là int/long/decimal hay không.
- Phạm vi quantity/limit được phép.
- Quy tắc khởi tạo khi field missing hoặc null.

Không giả định mọi NoSQL lưu số nguyên 64-bit giống Java long.

### 16.2. Decimal và tiền tệ

Không dùng double để đếm **số tiền nguyên đơn vị nhỏ nhất** khi phải giữ chính xác. Có thể chọn:
- long theo đơn vị nhỏ nhất và xử lý overflow.
- BigDecimal/Decimal128/decimal với scale và rounding policy rõ.
- Ledger append-only cho khoản nợ/số dư.

Cần phân biệt **1000 đồng**, **1000 cent** và **1000 đơn vị game credit**: cùng một số 1000 nhưng ý nghĩa khác.

### 16.3. Negative increment không phải lúc nào hợp lệ

Một API cho phép delta tùy ý:

~~~~json
{
  "counter": "stock",
  "delta": -1000000000
}
~~~~

nếu không kiểm soát có thể phá quota. Nên có **endpoint riêng cho hành động nghiệp vụ** (reserve, release, adjust) với rule và quyền, thay vì expose primitive atomicAdd(delta) cho mọi client không tin cậy.

## 17. Giải phóng reservation: phép cộng cũng có thể bị trùng

Giảm stock khi giữ hàng và tăng lại khi hủy:

~~~~text
Reserve OP-101:
  available -= 2
  reserved += 2

Cancel OP-101:
  reserved -= 2
  available += 2
~~~~

Nếu cancellation được xử lý hai lần, available có thể tăng **+4** dù ban đầu chỉ reserve 2.

Vì vậy phải bảo vệ cả **reserve** và **release** bằng state machine:

~~~~text
PENDING -> RESERVED -> CONFIRMED
                  \-> CANCELLED
~~~~

Một transition hợp lệ có thể là:

~~~~text
IF reservation.status == RESERVED
THEN
  reservation.status = CANCELLED
  available += quantity
  reserved -= quantity
~~~~

Tốt nhất, **điều kiện trạng thái và cập nhật số lượng nằm trong một transaction/atomic boundary** hoặc một workflow có thể reconcile. Một command Cancel bị retry khi trạng thái đã CANCELLED phải **không tăng available lần nữa**.

### 17.1. TTL của reservation không tự hoàn tiền hàng

Nếu một reservation hết hạn sau 15 phút, việc Redis key chứa reservation tự biến mất **không đảm bảo** inventory ở nguồn đã được cộng lại đúng một lần.

Cần một expiration workflow:
- Phát hiện reservation đã hết hạn.
- Conditional transition RESERVED -> EXPIRED.
- Cập nhật slot/available theo transaction hoặc compensation có guard.
- Ghi operation result và outbox.
- Retry an toàn khi scheduler hoặc worker crash.

TTL là cơ chế hết hạn/lưu trữ, không mặc nhiên là một transaction giải phóng tài nguyên xuyên nhiều key.

## 18. Atomic counter và optimistic concurrency control

Khi update chỉ là cộng/trừ, toán tử atomic có thể đơn giản hơn CAS ở client. Nhưng nếu nghiệp vụ cần tính **dựa trên nhiều trường**, version check có ích.

Ví dụ tính giá trị mới bằng Java:

~~~~java
record InventorySnapshot(long available, long version) {}

InventorySnapshot current = repository.read("BOOK-42");

if (current.available() < quantity) {
    return Result.insufficientStock();
}

boolean updated = repository.compareAndSet(
        "BOOK-42",
        current.version(),
        current.available() - quantity
);

if (!updated) {
    // Có người cập nhật đồng thời: đọc lại và retry có giới hạn.
}
~~~~

**Compare-and-set (CAS)** cần được engine thực thi nguyên tử theo điều kiện version. Nếu kiểm tra version tại client rồi ghi SET không điều kiện, nó lại trở thành lost update.

### 18.1. CAS làm gì khi có tranh chấp?

~~~~text
available=10, version=7

Writer A đọc v7, muốn available=8.
Writer B đọc v7, muốn available=7.

A ghi IF version=7 -> thành công, version=8.
B ghi IF version=7 -> thất bại.
B đọc lại và tính trên state mới.
~~~~

CAS bảo vệ không ghi đè bản cũ **nhưng không tự ngăn B retry cùng ý định hai lần** nếu response của A hoặc B bị mất. Vẫn cần operationId cho những nghiệp vụ không được áp dụng lặp.

### 18.2. CAS có thể nhiều retry ở hot key

Khi 5.000 writer tranh một version, nhiều CAS sẽ fail rồi phải đọc lại, tăng CPU/I/O và latency. Atomic increment có thể hiệu quả hơn cho phép cộng thuần túy, còn **conditional arithmetic** thường phù hợp hơn cho một số bất biến đơn giản.

Chọn giữa **atomic operator, conditional write, version CAS và transaction** theo **invariant cần bảo vệ**, không chỉ theo cú pháp gọn.

## 19. Hot counter và thiết kế throughput

### 19.1. Công suất một key là hữu hạn

Atomic increment trên một key không có nghĩa **vô hạn RPS**. Counter nóng có thể phải serialize/coordinate những thay đổi trong một partition/leader hoặc theo mô hình engine, nên:
- p99 tăng khi nhiều writer tranh.
- Throttling xảy ra trước khi cluster dùng hết CPU trung bình.
- Retry làm tăng tải và phá độ chính xác nếu thiếu idempotency.
- Replica/consistency mạnh có thể làm write latency lớn hơn.
- Dữ liệu không phân tán đồng đều khi mọi request dùng một key.

### 19.2. Thực hiện batching ở phía ứng dụng có đánh đổi

Gom 100 lượt xem thành +100 giúp giảm số ghi, nhưng:

~~~~text
100 events -> aggregate delta=+100 -> một update
~~~~

Nếu process crash trước flush batch, có thể mất lượt; nếu gửi batch rồi timeout, retry có thể +100 lần nữa.

Giải pháp thường cần:
- Durable event log hoặc checkpoint/batchId.
- Idempotency theo batch.
- Chính sách max delay/loss chấp nhận được.
- Reconciliation từ event gốc nếu cần.
- Tránh batch quá lớn làm tăng tail latency.

Batched counters có thể phù hợp analytics; không dùng gom thao tác bán hàng theo đợt mà bỏ mất tính đúng của từng reservation.

### 19.3. Client throttling và retry storm

Nếu storage bắt đầu timeout, 1.000 request/giây có 2% timeout và mọi client lập tức retry, có thêm khoảng **20 request/giây** trên baseline nếu mỗi timeout retry đúng một lần. Nếu cả các lần retry cũng timeout và tiếp tục retry không giới hạn, tải có thể tiếp tục tăng.

Quan trọng hơn: với increment không idempotent, **20 timeout có thể tương ứng 20 increment đã commit**, và retry tạo thêm **20 increment sai** trong kịch bản xấu đó.

Cần **bounded retry, backoff+jitter, rate limiting, idempotency và deadline**. Backoff đơn độc chỉ giảm tải, không bảo vệ số đếm.

## 20. Bảo đảm nguyên tử không vượt ranh giới database

Một lần giảm thành công có thể cần kéo theo:
- Tạo order.
- Ghi bút toán.
- Phát sự kiện.
- Cập nhật search index.
- Gửi email.
- Gọi payment provider.

Nếu chúng ở những dịch vụ khác nhau:

~~~~mermaid
flowchart LR
    API["Checkout API"] --> INV[("Inventory DB")]
    API --> ORD[("Orders DB")]
    API --> PAY["Payment provider"]
    INV --> OUT[("Outbox")]
    OUT --> IDX[("Search / read model")]
~~~~

Một atomic decrement ở Inventory DB không tự làm **order, payment và search** cùng commit.

### 20.1. Transactional outbox

Trong một database có transaction đủ phạm vi:

~~~~text
BEGIN
  Conditional reserve stock
  Create Order
  Record OperationResult
  Insert OutboxEvent
COMMIT
~~~~

Relay phát outbox event sau commit. Consumer phải idempotent vì event có thể được giao nhiều lần. Nếu các thực thể nằm ở **hai database độc lập**, outbox ở một database không tự tạo distributed transaction qua database kia.

### 20.2. Saga và compensation

Với nhiều nguồn độc lập:

~~~~text
Reserve Inventory
  -> Authorize Payment
  -> Confirm Order
  -> Release Inventory nếu payment thất bại
~~~~

Các bước cần operation ID, state machine, retry và compensation. **Release** phải idempotent như **Reserve**; nếu xử lý trùng, counter có thể bị hoàn hàng hai lần.

### 20.3. Counter projection không phải nguồn duy nhất của ledger

Một số hệ tính available từ những bản ghi chi tiết:

~~~~text
initialStock
+ replenishments
- confirmedSales
- activeReservations
+ releasedReservations
~~~~

Counter materialized giúp đọc nhanh, nhưng khi sai lệch cần **tái dựng từ nguồn sự kiện/bút toán** có định danh duy nhất. Nếu chỉ còn một mutable counter mà không có audit, rất khó xác định vì sao giá trị sai sau nhiều retry hoặc failover.

## 21. Đo tính đúng và hiệu năng của atomic increment/decrement

### 21.1. Số liệu phải thu

| Nhóm | Metric | Mục đích |
| --- | --- | --- |
| **Correctness** | Expected vs actual count | Phát hiện lost/duplicate update |
| **Invariant** | Negative stock / over-limit count | Chứng minh hàng rào nghiệp vụ |
| **Idempotency** | Replayed operations, same-key conflicts | Bảo vệ retry |
| **Concurrency** | Conditional failures, CAS conflicts | Đánh giá tranh chấp |
| **Latency** | p50/p95/p99 write và read | Nhận ra hot counter |
| **Throughput** | Offered/achieved increment/s | Xác định công suất |
| **Error** | Timeout, throttling, retry rate | Không đánh đồng unknown với failure |
| **Distribution** | Per-key/partition hotspot | Xem tải có tập trung không |
| **Consistency** | Replica lag, read-your-writes misses | Đánh giá đường đọc |
| **Durability** | Failover/restart recovery | Bảo đảm ACK theo cấu hình |
| **Workflow** | Pending reservation age, outbox lag | Phát hiện trạng thái kẹt |
| **Storage** | IO/CPU/network, write amplification | Tính giá của counter mạnh |

### 21.2. Counter phải có expected result độc lập

Nếu 10.000 event ID **khác nhau** được chấp nhận thành công, một counter được thiết kế chính xác nên đối soát được với **10.000 effect duy nhất**, không phải với số request HTTP đã gửi.

Số request có thể lớn hơn số event vì retry. Do đó cần giữ dữ liệu kiểm chứng:

~~~~text
eventId / operationId
expected delta
accepted/rejected final state
observed effects
~~~~

Với quota và inventory, cần kiểm tra cả **tập operation được chấp nhận**, không chỉ counter cuối cùng: hai đường lỗi khác nhau có thể triệt tiêu khiến số cuối trông đúng nhưng booking/ledger vẫn sai.

### 21.3. Không chỉ benchmark increment trên một key ít tải

Một benchmark nên gồm:
- 1 writer, 10 writer, 100 writer, nhiều instance/máy.
- Một hot key, 100 key, hàng triệu key.
- Cùng một counter và những counter ở các partition khác nhau.
- Increment-only; decrement có condition; mixed reserve/release.
- Payload/quantity khác nhau.
- Timeout và retry.
- Replica đọc chậm.
- Failover giữa commit và ACK.
- Dữ liệu thật có indexes, TTL, background load.

**Throughput tăng khi thêm client không chứng minh correctness** nếu bài test không kiểm tra mỗi operationId được áp dụng tối đa một lần và các invariant.

## 22. Kịch bản fault injection cho phép tăng/giảm

| Kịch bản | Cách thử | Kỳ vọng |
| --- | --- | --- |
| Lost update | Nhiều writer đọc và SET từ cùng snapshot | Minh họa lost update ở mẫu sai |
| Atomic increment | N writer tăng cùng key, không lỗi, mỗi operation một lần | Giá trị cuối đúng tổng delta |
| Conditional decrement | available=1, hai request giảm 1 | Chỉ một request được commit |
| Same-key retry | Một op gửi hai lần | Tối đa một effect theo ledger |
| ACK loss | Database commit, chặn response | Client UNKNOWN; retry cùng ID không trùng |
| In-flight commit | Client GET không thấy trước khi write đầu hoàn tất | Không kết luận rollback |
| Different-key contention | Hai op khác nhau giữ cùng slot | Guard tài nguyên chặn duplicate |
| Release replay | Hủy reservation hai lần | Available chỉ hoàn đúng một lần |
| Overflow | Giá trị sát giới hạn kiểu số | Không âm thầm tràn |
| Missing/null counter | Counter chưa khởi tạo hoặc sai kiểu | Xử lý theo schema, không đoán |
| Replica lag | Đọc sau ghi qua read model trễ | Không dùng stale read làm quyết định |
| Hot partition | Hàng nghìn writer cùng key | Đo p99, throttle, backlog |
| Failover | Kill leader trong/ sau write ở môi trường test | Bảo đảm durability theo cấu hình |
| Multi-item partial workflow | Giảm SKU-A rồi lỗi SKU-B | Có transaction/compensation rõ |
| Expired reservation | Scheduler xử lý cùng reservation nhiều lần | Không hoàn hàng trùng |
| Sharded sum | Nhiều shard và đọc không snapshot | Xác định giới hạn tổng eventual |

### 22.1. Không chỉ kiểm tra HTTP response

Một test phải kiểm tra:
- Giá trị counter ở nguồn theo consistency phù hợp.
- Tập operationId và final status.
- Không có hai reservation cho cùng slot.
- Không có stock âm.
- Số lần payment capture/refund nếu có.
- Bản ghi ledger/outbox đúng.
- Khả năng phục hồi sau crash/restore.
- Mỗi retry cùng key trả đúng result, không ghi thêm delta.
- Tỷ lệ UNKNOWN và thời gian resolve.

Một test chỉ assert **HTTP 200** chưa chứng minh counter đúng khi có nhiều writer.

## 23. Ví dụ kiểm thử đồng thời bằng Java

Giả sử interface repository cung cấp thao tác có điều kiện:

~~~~java
public interface StockRepository {
    boolean reserveIfAvailable(String sku, long quantity);
    long getAvailable(String sku);
}
~~~~

Một test tải có thể phát nhiều request song song:

~~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class StockConcurrencyExample {
    public static void runTest(StockRepository repo) throws Exception {
        // Fixture: BOOK-42 có available=1 trước khi test.
        try (ExecutorService pool = Executors.newFixedThreadPool(20)) {
            List<Callable<Boolean>> tasks = new ArrayList<>();
            for (int i = 0; i < 20; i++) {
                tasks.add(() -> repo.reserveIfAvailable("BOOK-42", 1));
            }

            List<Future<Boolean>> futures = pool.invokeAll(tasks);
            int successful = 0;
            for (Future<Boolean> result : futures) {
                if (result.get()) {
                    successful++;
                }
            }

            if (successful != 1 || repo.getAvailable("BOOK-42") != 0) {
                throw new AssertionError(
                        "Expected exactly one reservation"
                );
            }
        }
    }
}
~~~~

Ví dụ sử dụng cú pháp Java hiện đại với ExecutorService trong try-with-resources khi phiên bản hỗ trợ (Java 21). Repository phải được hiện thực bằng atomic conditional update thật, không phải GET/SET ngây thơ.

**Giới hạn của ví dụ:**
- Không tạo lỗi mạng.
- Không kiểm tra operationId/idempotency.
- Không kiểm tra write concern/replica.
- Không tạo retry sau ACK loss.
- Không kiểm tra hiệu năng/p99.
- Một lần chạy không chứng minh hệ không bao giờ có race.

Cần bổ sung test tích hợp với database thật, barrier đồng bộ điểm bắt đầu và fault injection để kiểm chứng những trường hợp khó.

## 24. Runbook khi counter sai hoặc stock âm

### Bước 1 — Tách lỗi logic, lỗi retry và lỗi đọc

- Giá trị âm thực sự tồn tại tại source hay chỉ ở cache/search?
- Có đường GET-SET tự viết nào cạnh tranh với atomic operator không?
- Có lệnh decrement mà thiếu condition không?
- Có worker retry increment không idempotent khi timeout?
- Có release reservation chạy hai lần?
- Có batch import/adjustment thủ công ghi sai giá trị không?

### Bước 2 — Xác định ranh giới bảo đảm

- Atomicity của lệnh đang dùng là key, item, document hay transaction?
- Điều kiện và cập nhật có ở **cùng lệnh** không?
- Các bản ghi khác nhau có thuộc một transaction không?
- Write concern/consistency và durability cấu hình thế nào?
- Có replica/GSI/read model lag không?
- Có operation ledger để tra ID thao tác đã commit không?

### Bước 3 — Đối soát từ nguồn sự kiện

- Lấy số lượng ban đầu và những operation hợp lệ.
- Dedup theo operationId.
- Cộng tổng delta được **chấp nhận**.
- So với counter materialized hiện tại.
- Tách phần sai do duplicate, missing effect hoặc compensation.
- Không sửa counter bằng một số tùy ý nếu đang có writer cạnh tranh.

### Bước 4 — Sửa có hàng rào và kiểm soát tải

- Nếu đang vi phạm invariant, hạn chế nghiệp vụ nhạy cảm theo quy trình sự cố.
- Chặn đường ghi không có conditional guard.
- Giữ operationId qua retry và thêm ledger/transaction.
- Khắc phục worker xử lý duplicate/release.
- Chọn cách rebuild counter hoặc correction event có audit.
- Dùng version/conditional write khi áp dụng correction để không ghi đè thay đổi mới.

### Bước 5 — Chứng minh đã ổn định

- Counter khớp ledger sau khi reconcile.
- Không có negative/over-limit dưới tải cạnh tranh.
- Không có duplicate effect với retry và lost ACK.
- p99, conditional conflict rate và throttle trong ngưỡng.
- Replica/read model được cập nhật đúng freshness contract.
- Đã có test lỗi tương ứng để ngăn tái diễn.

## 25. Những sai lầm thường gặp

1. **“Biến Java là atomic nên cập nhật NoSQL cũng atomic.”** AtomicInteger trong một JVM không bảo vệ nhiều instance.
2. **“Cứ dùng $inc/INCR là không oversell.”** Không; cần condition hoặc tài nguyên quyền phù hợp.
3. **“Đọc stock > 0 rồi DECRBY là đủ.”** Hai request có thể cùng qua bước đọc.
4. **“Atomic increment cũng idempotent.”** Retry +1 có thể thành +2.
5. **“Timeout nghĩa là decrement chưa chạy.”** ACK có thể mất sau commit.
6. **“Một strongly consistent GET không thấy thì request cũ chắc chắn không thể commit.”** Có thể còn in-flight.
7. **“MongoDB $inc trên một document cập nhật được toàn bộ các document khác.”** Không, ngoài transaction thích hợp.
8. **“DynamoDB GSI mới ngay khi UpdateItem success.”** GSI thường được cập nhật bất đồng bộ.
9. **“Redis EVAL có rollback nếu script lỗi giữa chừng.”** Không có rollback kiểu relational cho mọi write đã thực thi.
10. **“Redis INCR là ledger tài chính bền vững mặc định.”** Durability/replication tùy cấu hình.
11. **“Cassandra counter hỗ trợ sẵn CAS stock >= qty.”** Counter khác LWT trên cột thường.
12. **“Cassandra counter update có thể retry vô hạn không đếm trùng.”** Không idempotent.
13. **“Mỗi HBase row increment làm transaction đa row.”** Row boundary có giới hạn.
14. **“Dùng nhiều shard sẽ giữ được global quota cứng.”** Cần phân bổ quyền/transaction.
15. **“CRDT hội tụ nên không thể âm.”** PN-counter không tự có giới hạn dưới.
16. **“Biết counter cuối đúng là chắc chắn không có lỗi.”** Duplicate và missing effect có thể triệt tiêu.
17. **“Có TTL reservation thì tự hoàn inventory.”** Cần workflow release có guard.
18. **“Chỉ guard reserve, release không cần idempotency.”** Release trùng có thể tăng stock sai.
19. **“Số nguyên lớn luôn không overflow trong database.”** Phải kiểm tra kiểu/miền/hành vi engine.
20. **“Một lần HTTP 200 là đủ chứng minh durability qua failover.”** Phụ thuộc write concern/replication.
21. **“Cache hiển thị số mới chứng minh source đã commit.”** Cache không phải nguồn có thẩm quyền.
22. **“Thêm synchronized vào service giải quyết đa node.”** Không bảo vệ các process khác.
23. **“Thêm nhiều app instance là counter hotspot tự hết.”** Có thể tăng tranh chấp cùng partition.
24. **“Tăng/giảm nguyên tử đồng nghĩa mọi nghiệp vụ liên quan đều atomic.”** External payment/order/search nằm ngoài phạm vi primitive.
25. **“Retry với idempotency key nhưng không lưu kết quả bền vững đã đủ.”** Crash có thể làm mất dấu và gây duplicate.

## 26. Bài tập tình huống: đặt hàng, tồn kho và báo cáo

Một nền tảng thương mại điện tử dùng Java 21 và NoSQL:

- SKU BOOK-42 có **available = 5**.
- Hai request đồng thời, mỗi request muốn mua **3 đơn vị**.
- API dùng MongoDB cho Inventory, DynamoDB cho Order read model và Redis cho cache số lượng.
- API có timeout 3 giây; client có thể tự retry khi mạng chậm.
- Mỗi booking/order có **operationId** ổn định.
- Index tìm kiếm và read model có thể trễ vài giây.
- Có worker hủy đơn và hoàn trả inventory.
- Số lượt xem sản phẩm được ghi riêng bằng counter có lưu lượng rất lớn.

### Phần A — Minh họa lost update

Viết timeline hai writer cùng đọc available=5 rồi ghi available=2 bằng SET. Nêu kết quả sai và vì sao **mỗi lệnh SET riêng lẻ có thể atomic** nhưng cả workflow vẫn gây lost update.

### Phần B — Conditional decrement

Viết một lệnh cập nhật MongoDB **chỉ giảm khi available >= quantity**, đồng thời tăng reserved và version. Với hai request qty=3, xác định có bao nhiêu request được phép thành công và available cuối đúng là bao nhiêu khi không có lỗi khác.

**Gợi ý:** Chỉ một request được commit; available từ 5 xuống **2**. Request còn lại không được tự trừ vì stock=2 < 3.

### Phần C — Timeout và idempotency

Giả sử OP-101 đã giảm 3, nhưng ACK bị mất. Client retry cùng OP-101. Thiết kế:
- OperationResult ledger.
- Unique constraint/conditional guard theo OP-101.
- Cách lưu ledger nguyên tử cùng reserve.
- Cách trả lại cùng reservationId.
- Hành vi khi cùng key có payload khác.

Giải thích vì sao **$inc -3** lặp lại lần hai vẫn là một thao tác atomic nhưng sai nghiệp vụ.

### Phần D — Đọc từ Redis/GSI

MongoDB đã commit available=2, nhưng Redis cache còn 5 và DynamoDB read model vẫn ghi “còn hàng”. API checkout có được lấy 5 làm căn cứ cấp phát không? Phải đặt condition ở đâu, và làm sao hiển thị dữ liệu stale mà không làm sai quyết định?

### Phần E — Cancel và hoàn tồn kho

Một đơn đã RESERVED quantity=3 được hủy, worker nhận CancelOrder hai lần. Thiết kế state transition và atomic/transactional guard để available chỉ tăng lại đúng **3 một lần**, không tăng 6.

### Phần F — Hot views counter

Một bài viết có 50.000 lượt xem/giây. So sánh:
1. Một atomic counter duy nhất.
2. 64 sharded counters.
3. Event log + batch aggregation.

Đánh giá throughput, độ mới khi đọc, khả năng mất/trùng khi retry và chi phí đọc. Vì sao mô hình sharded này có thể phù hợp **lượt xem** nhưng không mặc nhiên phù hợp **strict stock**?

### Phần G — Fault injection

Thiết kế test:
- 100 writer giảm có điều kiện trên 10 sản phẩm.
- Mất ACK sau commit.
- Thay đổi leader/failover.
- Retry cùng opId nhiều lần.
- Hủy đơn lặp.
- Tăng giá trị sát giới hạn long.
- Đọc cache/GSI trễ.
- Một hot key chịu 10.000 write/s.

Mỗi test cần nêu **invariant, kết quả cuối cần kiểm tra, metric và điều kiện kết luận pass/fail**.

### Phần H — Sổ cái tín dụng

Một ví có balanceMinor=100000 và hai request debit 70000 cùng thời điểm. Có thể dùng atomic decrement đơn thuần không? Hãy đề xuất **conditional debit, operation ledger, transaction record, write concern và reconciliation**. Nếu debit lần đầu commit nhưng ACK mất, phải làm gì trước khi thử một debit mới?

### Gợi ý hướng giải

Không chỉ thay GET-SET bằng increment/decrement. Chỉ dùng primitive atomic đúng **phạm vi**: với inventory phải kết hợp **điều kiện available >= qty**; với retry phải có **operationId và ledger**; với nhiều item phải dùng **transaction được hỗ trợ hoặc state machine/compensation**. Dữ liệu trên Redis/GSI/search có thể giúp UI nhưng không làm điểm quyết định cuối. Với lượt xem khối lượng lớn, counter sharding/batch có thể giảm hotspot khi chấp nhận độ mới hoặc cần dedup event riêng. Mọi thiết kế phải chứng minh được **không lost update, không âm, không xử lý trùng cùng ý định và phục hồi được sau mất kết nối**.

**Kết luận:** Phép tăng/giảm nguyên tử là công cụ mạnh để bảo vệ thao tác thay đổi số tại **một ranh giới dữ liệu cụ thể**, tránh kiểu đọc–sửa–ghi gây lost update. Nhưng atomicity của phép toán **không tự bảo đảm** điều kiện số không âm, idempotency khi retry, độ bền sau failover, độ mới ở replica, hay sự nguyên tử giữa nhiều document và dịch vụ. Muốn xử lý cập nhật đồng thời đúng đắn trong NoSQL, cần kết hợp **atomic operator, conditional guard, operation ledger, transaction hoặc saga theo phạm vi, giám sát hotspot và kiểm thử lỗi mạng** — luôn xác định rõ bảo đảm đang áp dụng **cho thao tác nào, trên dữ liệu nào và tại thời điểm nào**.
