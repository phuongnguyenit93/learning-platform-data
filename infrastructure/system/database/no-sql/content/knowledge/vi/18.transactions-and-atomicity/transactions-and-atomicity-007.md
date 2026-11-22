# Cập nhật có điều kiện và tính nguyên tử của phép so sánh rồi ghi

## 1. Bài toán: kiểm tra đúng nhưng vẫn ghi sai

Trong hệ thống NoSQL, nhiều client có thể đồng thời truy cập và sửa cùng một bản ghi. Một yêu cầu nghiệp vụ rất phổ biến là:

> “Chỉ cập nhật dữ liệu **nếu** một điều kiện đang còn đúng **tại thời điểm ghi**.”

Ví dụ:

- Chỉ trừ tồn kho nếu số lượng còn đủ.
- Chỉ tạo username nếu username chưa tồn tại.
- Chỉ cập nhật hồ sơ nếu người khác chưa sửa phiên bản đang đọc.
- Chỉ chuyển đơn hàng từ `PAID` sang `SHIPPED`, không chuyển từ `CANCELLED`.
- Chỉ gia hạn lease nếu caller vẫn là chủ sở hữu hợp lệ.
- Chỉ xác nhận một mã giảm giá nếu lượt sử dụng chưa vượt hạn mức.
- Chỉ ghi kết quả của worker nếu tiến trình này vẫn giữ fencing token mới nhất.

Nếu ứng dụng đọc dữ liệu, kiểm tra điều kiện trong bộ nhớ rồi gửi một lệnh ghi **riêng biệt**, điều kiện có thể bị thay đổi bởi client khác trong khoảng giữa hai bước.

Đây là **race condition** thuộc nhóm *time-of-check to time-of-use (TOCTOU)*.

### 1.1. Ví dụ tồn kho: chỉ còn một sản phẩm

Trạng thái ban đầu:

```json
{
  "productId": "P100",
  "available": 1
}
```

Hai khách A và B cùng muốn mua một sản phẩm. Code ngây thơ:

```java
Inventory inventory = repository.findByProductId("P100");

if (inventory.getAvailable() >= 1) {
    inventory.setAvailable(inventory.getAvailable() - 1);
    repository.save(inventory);
    return "RESERVED";
}

return "OUT_OF_STOCK";
```

Timeline có thể là:

```text
                      Tồn kho P100 = 1

Khách A                                  Khách B
-------                                  -------
READ available=1
                                         READ available=1
Kiểm tra 1 >= 1: đúng
                                         Kiểm tra 1 >= 1: đúng
WRITE available=0
                                         WRITE available=0
Trả "đặt thành công"
                                         Trả "đặt thành công"

Kết quả: Hai khách đều được xác nhận, dù chỉ còn 1 sản phẩm.
```

Ngay cả khi giá trị cuối cùng trong database là `available=0` chứ không phải `-1`, **bất biến nghiệp vụ vẫn bị vi phạm**: hệ thống đã xác nhận hai lượt đặt chỗ cho cùng một đơn vị hàng.

Thêm một lần đọc lại trước khi ghi không giải quyết triệt để, vì client khác vẫn có thể ghi vào khe thời gian tiếp theo.

### 1.2. Điều kiện phải đi cùng thao tác ghi

Thay vì:

```text
READ
  |
  v
CHECK ở ứng dụng
  |
  v
WRITE
```

ta cần một thao tác được database bảo vệ:

```text
ATOMIC {
    CHECK available >= 1
    IF true:
        available = available - 1
}
```

Nếu cả A và B cùng yêu cầu, chỉ một thao tác có thể thành công đối với trạng thái `available=1` theo ngữ nghĩa nguyên tử thích hợp của bản ghi.

Đó là nền tảng của **cập nhật có điều kiện (conditional update)**, **compare-and-set (CAS)** và **optimistic concurrency control (OCC)**.

## 2. Cập nhật có điều kiện là gì?

Một cập nhật có điều kiện có hình thức khái niệm:

\[
\operatorname{UpdateIf}(key,\ predicate,\ mutation)
\]

Trong đó:

- `key`: đối tượng hoặc tập đối tượng được thao tác có phạm vi nguyên tử phù hợp;
- `predicate`: điều kiện phải đúng dựa trên trạng thái hiện hành;
- `mutation`: thay đổi cần áp dụng nếu điều kiện đúng.

Ví dụ:

```text
key       = Inventory(P100)
predicate = available >= 1
mutation  = available := available - 1
```

Kết quả có thể là:

| Kết quả | Ý nghĩa |
|---|---|
| `APPLIED` / matched | Điều kiện đúng và mutation được chấp nhận theo bảo đảm của database |
| `NOT_APPLIED` / conflict | Điều kiện sai hoặc phiên bản đã thay đổi |
| `TIMEOUT` / unknown | Client chưa biết chắc thao tác có được commit hay không |
| Lỗi validation/permission | Request không hợp lệ hoặc không có quyền; không mặc định là conflict |

**Không được gộp timeout và điều kiện không thỏa thành một kết quả “chưa cập nhật”.** Timeout có thể xảy ra sau khi database đã commit nhưng phản hồi bị mất.

### 2.1. CAS: compare-and-swap / compare-and-set

Một phép CAS kinh điển:

\[
CAS(x, expected, newValue)
\]

có ý nghĩa:

> Nếu giá trị hiện tại của `x` vẫn bằng `expected` thì thay bằng `newValue`; nếu không, giữ nguyên và báo không thành công.

Ví dụ:

```text
CAS(status, "PENDING", "PAID")
```

Nếu trạng thái đã thành `CANCELLED`, CAS không được biến nó thành `PAID`.

Trong database, CAS có thể là:

- So sánh giá trị của một trường;
- So sánh `version` hoặc `etag`;
- So sánh sự tồn tại/chưa tồn tại;
- So sánh một biểu thức phức hợp;
- So sánh token/generation của quyền sở hữu.

API cụ thể của mỗi sản phẩm rất khác nhau. Một số hệ gọi nó là **conditional write**; một số gọi **lightweight transaction** hoặc **precondition**.

### 2.2. Phạm vi nguyên tử

Câu hỏi quan trọng không chỉ là “database có CAS không?” mà là:

> **CAS nguyên tử trong phạm vi nào, và bất biến cần bảo vệ nằm ở đâu?**

Ví dụ:

- MongoDB bảo đảm thao tác ghi trên **một document** là nguyên tử theo ngữ nghĩa tương ứng.
- DynamoDB conditional write áp dụng cho **một item**; TransactWriteItems có phạm vi giao dịch đa item trong giới hạn sản phẩm.
- Redis có thể dùng một lệnh nguyên tử hoặc Lua script theo ngữ nghĩa server, nhưng phải xét cluster và durability.
- Cassandra LWT tạo bảo đảm so sánh–ghi cho điều kiện trong phạm vi được hỗ trợ, với giao thức đồng thuận và chi phí riêng.
- Firestore có precondition/transaction theo mô hình tài liệu và giao dịch.
- Cosmos DB for NoSQL có cơ chế `_etag`/If-Match và transactional batch trong phạm vi partition key được hỗ trợ.

Một CAS nguyên tử trên item A **không tự làm cập nhật item B cũng nguyên tử**.

## 3. Tính nguyên tử của phép so sánh rồi ghi

### 3.1. “Check then write” và “check-and-write” không giống nhau

Phương án không an toàn:

```text
GET K
if K.version == 7:
    PUT K with version 8
```

Hai worker có thể cùng đọc v7 rồi cùng ghi v8 với dữ liệu khác nhau. Điều kiện được kiểm tra **bên ngoài** thao tác ghi.

Phương án có bảo vệ:

```text
UPDATE K
SET value = newValue, version = 8
WHERE version = 7
```

Database phải đảm bảo việc kiểm tra `version = 7` và ghi diễn ra như **một thao tác nguyên tử trong phạm vi nó cam kết**. Nếu worker đầu tiên chuyển sang v8, worker thứ hai với `expected=7` phải không được ghi theo điều kiện đó.

### 3.2. Điểm tuyến tính hóa (linearization point)

Ta có thể hình dung một conditional write thành công như xảy ra tại một thời điểm logic duy nhất giữa lúc database nhận request và trả response:

```text
Client A: |----- request CAS A ------|
                        ^
                  Điểm áp dụng

Client B:      |----- request CAS B ------|
                              ^
                    Áp dụng hoặc từ chối theo
                    trạng thái đã có tại thời điểm đó
```

Đây là mô hình tư duy của **linearizability** đối với một đối tượng khi hệ thực sự cung cấp bảo đảm tương ứng. Không phải tất cả NoSQL hoặc cấu hình nhất quán đều cung cấp tính tuyến tính hóa cho mọi thao tác, mọi key và mọi vùng địa lý.

Cần phân biệt:

- **Atomicity**: thao tác không được quan sát như một chuỗi cập nhật nửa chừng trong phạm vi cam kết.
- **Isolation**: các thao tác/giao dịch đồng thời được quan sát và tương tác theo quy tắc nào.
- **Linearizability**: kết quả có thể sắp thành thứ tự tôn trọng thời gian thực của các thao tác đã hoàn tất.
- **Serializability**: các giao dịch có kết quả tương đương một thứ tự tuần tự nào đó, không nhất thiết theo thời gian thực.
- **Durability**: sau commit, dữ liệu sống sót thế nào trước lỗi máy/đĩa.

**Một conditional update nguyên tử không tự chứng minh toàn hệ có serializable transactions hoặc linearizable reads.**

### 3.3. Đúng điều kiện ở đâu?

Nếu một API đọc từ replica có thể trễ, rồi yêu cầu ghi CAS ở leader, kết quả kiểm tra tại leader có thể khác dữ liệu client vừa đọc. Đó là điều bình thường:

```text
Read replica: version=7
Write authority: version=8

Client gửi IF version=7
=> Conflict
```

Ứng dụng phải coi **kết quả conditional write ở nơi thực thi** là quyết định, không coi giá trị từ lần đọc trước là cam kết.

## 4. Mô hình Optimistic Concurrency Control bằng version

**Optimistic concurrency control (OCC)** cho phép các client đọc và chuẩn bị thay đổi song song, nhưng chỉ commit nếu trạng thái nguồn chưa thay đổi ngoài dự kiến.

### 4.1. Lưu trường version

Một document:

```json
{
  "orderId": "O100",
  "status": "PENDING",
  "shippingAddress": "Địa chỉ A",
  "version": 7
}
```

Client A và B cùng đọc v7.

Client A sửa địa chỉ; client B sửa trạng thái. Nếu cả hai thay nguyên document và không bảo vệ version, một client có thể làm mất thay đổi của client kia.

### 4.2. Quy trình OCC

1. Đọc object cùng `version`.
2. Tính thay đổi mong muốn ở ứng dụng.
3. Gửi **conditional update** với `expectedVersion`.
4. Nếu thành công, tăng version.
5. Nếu conflict, đọc lại trạng thái và quyết định merge/retry hoặc trả lỗi cho người dùng.

```text
                      Order v7
                    /          \
                   /            \
              Client A         Client B
              đọc v7           đọc v7
                 |                |
        UPDATE IF version=7   UPDATE IF version=7
                 |                |
             thành công         conflict
             Order v8           không ghi
```

### 4.3. Bất biến version

Với quy ước version tăng một mỗi lần cập nhật:

\[
newVersion = expectedVersion + 1
\]

Điều kiện cần được gắn với lệnh ghi:

\[
currentVersion = expectedVersion
\]

Không nên tách:

```text
if current.version == expected:
    update(value)
    update(version)
```

thành nhiều thao tác rời không có bảo vệ nguyên tử. Nếu chỉ tăng version sau khi ghi nội dung, một client khác có thể chen vào và nhìn trạng thái không đồng nhất.

### 4.4. Version số hay ETag?

Có thể dùng:

- `version` nguyên tăng dần;
- `_etag` hoặc revision token do database cấp;
- `_seq_no` + `_primary_term` trong một số search engine;
- CAS token của document store.

Version số dễ quan sát nhưng ứng dụng phải duy trì đúng, kể cả khi xóa/tái tạo. ETag/CAS token do storage quản lý giảm việc ứng dụng tự tăng số nhưng vẫn phải hiểu phạm vi và thời hạn hiệu lực.

**Timestamp không luôn là version tốt.** Hai ghi có thể cùng timestamp theo độ phân giải đang dùng, đồng hồ lệch hoặc không mang thứ tự transaction. Dùng `updatedAt` làm CAS token chỉ khi database và mô hình dữ liệu bảo đảm cách so sánh phù hợp.

## 5. Những kiểu điều kiện thường gặp

### 5.1. Create-if-absent

Chỉ tạo bản ghi nếu chưa tồn tại:

```text
IF key does not exist:
    INSERT new item
ELSE:
    conflict
```

Ứng dụng phù hợp:

- Đăng ký username duy nhất;
- Tạo idempotency record;
- Chiếm một slot có ID ổn định;
- Tạo job chỉ một lần theo business key.

Không thể thay bằng **GET rồi PUT** vì hai request cùng thấy key chưa tồn tại.

### 5.2. Update-if-version

```text
IF current.version == 7:
    UPDATE content, version := 8
```

Phù hợp với form chỉnh sửa, workflow có nhiều người thao tác và chống lost update.

### 5.3. Update-if-state

```text
IF status == "PAID":
    status := "SHIPPED"
```

Phù hợp với state machine nghiệp vụ. Việc chuyển từ `CANCELLED` sang `SHIPPED` có thể bị từ chối ngay tại thao tác ghi.

### 5.4. Update-if-capacity

```text
IF available >= quantity:
    available := available - quantity
```

Phù hợp cho tồn kho, hạn mức theo một counter và điểm thưởng còn đủ.

### 5.5. Delete-if-owner

```text
IF lockOwner == callerId:
    DELETE lease
```

Tránh worker cũ xóa khóa/lease đã được worker khác nhận lại. Tuy vậy cần xem thêm **fencing token** khi tài nguyên ngoài database đã bị tác động.

### 5.6. Conditional upsert

Một số API cho phép “nếu đã tồn tại thì cập nhật, nếu chưa thì tạo”, đi kèm điều kiện. Nhưng logic của điều kiện khi record chưa tồn tại phải được định nghĩa rõ; việc dùng `upsert=true` mà không có unique index hay khóa ổn định có thể tạo bản ghi trùng khi cạnh tranh.

## 6. Lost update: lỗi CAS giải quyết rất tốt

Một hồ sơ lưu:

```json
{
  "userId": "U42",
  "displayName": "An",
  "language": "vi",
  "version": 3
}
```

Client A muốn đổi `displayName`; client B muốn đổi `language`. Nếu cả hai tải toàn document v3 rồi gửi thay toàn bộ document, có thể xảy ra:

```text
A đọc {name: An, language: vi}
B đọc {name: An, language: vi}

A ghi {name: Anh, language: vi}
B ghi {name: An,  language: en}

Kết quả: B vô tình khôi phục name=An; thay đổi của A mất.
```

**Lost update** là một dạng race phổ biến.

### 6.1. Bảo vệ bằng version

Cả hai gửi `IF version=3`, chỉ một request thành công. Client còn lại được báo conflict và có thể:

- Tải lại dữ liệu;
- Chỉ gửi trường nó thật sự sửa;
- Merge một cách có quy tắc;
- Yêu cầu người dùng xác nhận thay đổi mới.

### 6.2. Không phải lúc nào cũng cần OCC cho các trường độc lập

Nếu database hỗ trợ **atomic partial updates** trên từng field, hai client sửa hai trường độc lập có thể không làm mất nhau. Ví dụ các thao tác chỉ `$set` đúng field tương ứng trong MongoDB.

Tuy nhiên, nếu bất biến liên quan đồng thời hai trường, hoặc UI đang gửi trạng thái toàn form, OCC vẫn có thể hữu ích để phát hiện thay đổi bất ngờ.

**Tối ưu song song không được bỏ qua yêu cầu nghiệp vụ.** Có hệ cho phép hai thay đổi độc lập chạy chung, có hệ cần người dùng xem lại toàn bộ object vì các trường có liên hệ.

## 7. Cập nhật số đếm: atomic increment khác read-modify-write

### 7.1. Race khi cộng bằng ứng dụng

Giả sử `views=100`, hai client cùng tăng một:

```text
A GET views=100
B GET views=100
A SET views=101
B SET views=101
```

Giá trị mong muốn là 102, nhưng kết quả cuối là 101.

### 7.2. Atomic increment

Một lệnh nguyên tử ở database:

```text
INCREMENT views BY 1
```

có thể giúp cả hai lượt tăng được cộng mà không bị lost update:

```text
100 -> 101 -> 102
```

Ví dụ MongoDB:

```javascript
db.articles.updateOne(
  { articleId: "A100" },
  { $inc: { views: 1 } }
);
```

Ví dụ Redis:

```redis
INCR views:A100
```

Những thao tác này có semantics nguyên tử trong phạm vi key/document được engine hỗ trợ.

### 7.3. Nhưng increment không tự bảo vệ giới hạn

Một lệnh `INCR` liên tục có thể tăng số lượt sử dụng vượt hạn mức. Nếu yêu cầu:

> “Chỉ tăng `used` nếu `used < quota`.”

thì cần điều kiện và cập nhật trong một thao tác bảo vệ:

```text
ATOMIC {
    IF used < quota:
        used := used + 1
    ELSE:
        reject
}
```

Nếu quota và used nằm ở **hai item khác nhau**, single-item CAS không tự tạo ra một giao dịch nguyên tử cho cả hai; phải xét lại mô hình hoặc dùng transaction phù hợp.

## 8. DynamoDB: ConditionExpression và conditional writes

Amazon DynamoDB có cơ chế **conditional write** qua `ConditionExpression` trong các thao tác như `PutItem`, `UpdateItem` và `DeleteItem`.

Một câu hỏi cần được thiết kế ngay từ đầu: **bất biến được bảo vệ có nằm trong cùng item với điều kiện không?**

### 8.1. Tạo item nếu chưa tồn tại

Giả sử bảng có partition key `PK`, lưu username đã chuẩn hóa làm khóa:

```json
{
  "PK": "USERNAME#an.nguyen",
  "userId": "U42",
  "createdAt": "2026-11-14T08:00:00Z"
}
```

Muốn ngăn hai request cùng chiếm username:

```json
{
  "TableName": "UsernameClaims",
  "Item": {
    "PK": {"S": "USERNAME#an.nguyen"},
    "userId": {"S": "U42"}
  },
  "ConditionExpression": "attribute_not_exists(PK)"
}
```

Đây là hình dạng request ở API cấp thấp, minh họa ý nghĩa **PutItem chỉ khi item mang khóa đó chưa tồn tại**.

Hai request với cùng `PK` có điều kiện loại trừ nhau theo semantics của conditional write. Một request có thể thành công; request khác nhận lỗi điều kiện không thỏa.

**Không nên thay bằng**:

```text
GetItem PK
if not found:
    PutItem PK
```

vì hai caller có thể cùng đọc “không thấy”.

### 8.2. Tồn kho: trừ khi còn đủ

Giả sử item:

```json
{
  "PK": "PRODUCT#P100",
  "available": 5,
  "version": 7
}
```

Yêu cầu đặt trước 2 sản phẩm khi có ít nhất 2:

```json
{
  "TableName": "Inventory",
  "Key": {
    "PK": {"S": "PRODUCT#P100"}
  },
  "UpdateExpression": "SET #a = #a - :q, #v = #v + :one",
  "ConditionExpression": "attribute_exists(PK) AND #a >= :q",
  "ExpressionAttributeNames": {
    "#a": "available",
    "#v": "version"
  },
  "ExpressionAttributeValues": {
    ":q": {"N": "2"},
    ":one": {"N": "1"}
  },
  "ReturnValues": "ALL_NEW"
}
```

Ở đây kiểm tra `available >= 2` và trừ `2` thuộc **một conditional UpdateItem**. Phép cập nhật `version + 1` cũng nằm trong mutation của item đó.

Tùy yêu cầu, có thể thêm `#v = :expectedVersion` vào `ConditionExpression` để vừa bảo vệ tồn kho vừa chặn thay đổi khác:

```text
attribute_exists(PK)
AND #a >= :q
AND #v = :expected
```

Cách thêm OCC khiến request dễ bị conflict hơn; chỉ thêm version condition khi cần bảo vệ toàn bộ những thay đổi phụ thuộc vào bản snapshot mà caller đã đọc.

### 8.3. Phân biệt lỗi điều kiện với lỗi khác

Khi điều kiện sai, DynamoDB trả lỗi `ConditionalCheckFailedException` theo SDK tương ứng. Đó thường là tín hiệu request không được áp dụng do predicate không thỏa.

Các lỗi mạng, timeout và internal errors **không nên bị chuyển thành cùng loại “hết hàng”**. Có thể request đã commit trước khi client mất kết nối.

### 8.4. Java với AWS SDK for Java v2

Ví dụ minh họa một conditional update trừ tồn kho:

```java
import java.util.Map;

import software.amazon.awssdk.core.exception.SdkException;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.ConditionalCheckFailedException;
import software.amazon.awssdk.services.dynamodb.model.UpdateItemRequest;

public final class InventoryRepository {
    private final DynamoDbClient dynamoDb;

    public InventoryRepository(DynamoDbClient dynamoDb) {
        this.dynamoDb = dynamoDb;
    }

    public boolean reserve(String productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        UpdateItemRequest request = UpdateItemRequest.builder()
                .tableName("Inventory")
                .key(Map.of(
                        "PK", AttributeValue.fromS("PRODUCT#" + productId)
                ))
                .updateExpression("SET #a = #a - :q")
                .conditionExpression(
                        "attribute_exists(PK) AND #a >= :q")
                .expressionAttributeNames(Map.of(
                        "#a", "available"
                ))
                .expressionAttributeValues(Map.of(
                        ":q", AttributeValue.fromN(
                                Integer.toString(quantity))
                ))
                .build();

        try {
            dynamoDb.updateItem(request);
            return true;
        } catch (ConditionalCheckFailedException conflict) {
            return false; // Không đủ hàng hoặc item không tồn tại.
        }
        // Các SdkException khác được truyền ra:
        // không được tự kết luận thao tác chưa commit.
    }
}
```

Đây là ví dụ **phần cập nhật tồn kho**. Một workflow đặt hàng hoàn chỉnh còn cần idempotency, ghi trạng thái reservation/order, rollback/compensation hoặc transaction theo thiết kế.

### 8.5. Conditional write không phải giao dịch order + inventory tự động

Nếu hệ cập nhật inventory thành công rồi tạo order thất bại:

```text
Inventory(P100): available 5 -> 3    OK
Order(O100): CREATE                  FAIL
```

thì inventory và order bị lệch. Conditional update trên inventory chỉ bảo vệ **một item**. Nếu hai thao tác phải commit cùng nhau, cần xem `TransactWriteItems` với những giới hạn về item/kích thước/phạm vi của DynamoDB hoặc một workflow reservation/compensation đáng tin cậy.

### 8.6. Global tables và nhiều vùng ghi

Conditional write được đánh giá tại nơi xử lý request theo mô hình của DynamoDB. Khi dùng kiến trúc đa vùng với những cơ chế sao chép và xử lý xung đột riêng, **không nên mặc định hai ghi điều kiện ở hai region độc lập cùng áp dụng một invariant toàn cục duy nhất**.

Tùy thế hệ/cấu hình global tables và nhất quán được chọn, cần kiểm tra semantics multi-region và chiến lược ownership. Nếu username hoặc slot phải duy nhất toàn cầu, có thể cần tuyến ghi về một authority hoặc cơ chế giao dịch/toàn cục phù hợp, không chỉ dựa vào hai phép `attribute_not_exists` chạy tại hai nơi.

## 9. MongoDB: cập nhật một document với filter nguyên tử

MongoDB hỗ trợ update document bằng `updateOne()` hoặc `findOneAndUpdate()`. Việc tìm document phù hợp với filter và áp dụng mutation cho **document đó** được engine thực hiện nguyên tử theo phạm vi một document.

### 9.1. Chuyển trạng thái có điều kiện

Document ban đầu:

```json
{
  "_id": "O100",
  "status": "PAID",
  "version": 7
}
```

Chỉ chuyển sang `SHIPPED` nếu trạng thái vẫn là `PAID`:

```javascript
const result = db.orders.updateOne(
  {
    _id: "O100",
    status: "PAID"
  },
  {
    $set: {
      status: "SHIPPED"
    },
    $inc: {
      version: 1
    }
  }
);

if (result.matchedCount === 0) {
  // Không tìm thấy document thỏa điều kiện:
  // có thể đã đổi trạng thái hoặc không tồn tại.
}
```

Nếu client khác đã đổi trạng thái trước, filter `status: "PAID"` không còn khớp và thao tác không được áp dụng cho document đó.

Không nên coi `matchedCount=0` luôn có nghĩa đơn đã hủy; muốn phân biệt không tồn tại, đã giao hay đã hủy thì phải đọc trạng thái hiện tại theo yêu cầu API.

### 9.2. OCC theo version

```javascript
const expectedVersion = 7;

const result = db.orders.updateOne(
  {
    _id: "O100",
    version: expectedVersion
  },
  {
    $set: {
      shippingAddress: "Địa chỉ B"
    },
    $inc: {
      version: 1
    }
  }
);

if (result.matchedCount === 0) {
  throw new Error("VERSION_CONFLICT");
}
```

Nội dung và version thay đổi cùng một mutation trên document. Nếu hai caller cùng dùng expectedVersion 7, chỉ caller áp dụng trước sẽ nhìn thấy điều kiện đúng, theo semantics của một document được database quản lý.

### 9.3. Atomic decrement với điều kiện

```javascript
const result = db.inventory.updateOne(
  {
    _id: "P100",
    available: { $gte: 2 }
  },
  {
    $inc: {
      available: -2
    }
  }
);

if (result.matchedCount === 0) {
  // Không đủ số lượng hoặc không có item.
}
```

Đây thường là thiết kế trực tiếp hơn việc gọi `findOne`, tính giá trị ở JavaScript rồi `$set`.

### 9.4. Return old/new document với findOneAndUpdate

Một API có thể cần trạng thái sau khi áp dụng:

```javascript
const updated = db.orders.findOneAndUpdate(
  {
    _id: "O100",
    version: 7
  },
  {
    $set: { status: "SHIPPED" },
    $inc: { version: 1 }
  },
  {
    returnDocument: "after"
  }
);
```

Cú pháp return value có thể khác giữa MongoDB shell/driver/version. Tư duy chính: database áp dụng filter và update trên document rồi trả trạng thái theo lựa chọn phù hợp. Không cần tách một lượt đọc chỉ để lấy số version mới nếu API cung cấp kết quả.

### 9.5. Unique index vẫn cần cho tạo bản ghi

Giả sử ứng dụng kiểm tra email chưa tồn tại:

```javascript
const existing = db.users.findOne({
  normalizedEmail: "an@example.com"
});

if (!existing) {
  db.users.insertOne({
    normalizedEmail: "an@example.com"
  });
}
```

Hai request có thể cùng nhìn “không có”. Nếu cần uniqueness toàn collection, tạo **unique index** theo quy tắc dữ liệu:

```javascript
db.users.createIndex(
  { normalizedEmail: 1 },
  { unique: true }
);
```

Unique index ngăn hai document sở hữu cùng giá trị khóa index theo semantics của nó, và thao tác insert bị từ chối khi trùng.

Điểm cần xét:

- Email phải được chuẩn hóa một cách nhất quán.
- Collation/case sensitivity phải khớp hợp đồng.
- Null/missing field, partial unique index và compound key có semantics riêng.
- Trong sharded collection, ràng buộc unique index có những giới hạn liên quan shard key và sản phẩm/phiên bản.

Không nên coi `upsert: true` tự tạo uniqueness cho một trường nếu điều kiện và index không bảo đảm điều đó.

### 9.6. Giao dịch nhiều document khi bất biến trải rộng

MongoDB có multi-document transactions trong những topology/phiên bản hỗ trợ. Nhưng không cần transaction nhiều document nếu invariant có thể nằm gọn trong một document với atomic conditional update.

Khi một workflow cập nhật nhiều document, cần đánh giá transaction, retry semantics, hiệu năng và những giới hạn của hệ. Một conditional update một document không kéo theo atomicity cho hai collection khác.

## 10. Cassandra: Lightweight Transactions và cú pháp IF

Cassandra thông thường có thiết kế ghi dựa trên replicated mutations và timestamp. Khi cần **compare-and-set**, Cassandra cung cấp **Lightweight Transaction (LWT)** dùng điều kiện như `IF NOT EXISTS` hoặc `IF column = value` trong những trường hợp được CQL hỗ trợ.

### 10.1. Tạo bản ghi nếu chưa tồn tại

Ví dụ bảng claim username:

```sql
CREATE TABLE usernames (
    normalized_username text PRIMARY KEY,
    user_id text,
    created_at timestamp
);
```

Chỉ tạo nếu key chưa được chiếm:

```sql
INSERT INTO usernames (
    normalized_username, user_id, created_at
)
VALUES (
    'an.nguyen', 'U42', toTimestamp(now())
)
IF NOT EXISTS;
```

Cassandra trả một kết quả có cột `[applied]`:

```text
[applied] | ...
----------+----
true      | ...
```

Nếu đã có row với khóa đó, `[applied] = false`; Cassandra có thể trả thêm thông tin trạng thái hiện tại theo ngữ nghĩa của câu lệnh và driver.

### 10.2. Cập nhật có điều kiện theo version

```sql
CREATE TABLE orders_by_id (
    order_id text PRIMARY KEY,
    status text,
    version bigint
);
```

Giả sử O100 đang có `status='PAID', version=7`:

```sql
UPDATE orders_by_id
SET status = 'SHIPPED',
    version = 8
WHERE order_id = 'O100'
IF version = 7 AND status = 'PAID';
```

Nếu điều kiện không thỏa, mutation không được áp dụng. Với LWT, ta không giả định có thể viết nhiều statement thông thường rồi tự gọi đó là một CAS.

### 10.3. LWT sử dụng cơ chế đồng thuận

LWT trong Cassandra có chi phí cao hơn nhiều thao tác ghi thông thường vì cần phối hợp theo một giao thức đồng thuận kiểu Paxos trong phạm vi tương ứng. Cần xem cả:

- Latency và số vòng trao đổi giữa replica;
- `SERIAL` / `LOCAL_SERIAL` cho serial consistency theo topology;
- Regular consistency của phần mutation;
- Contention trên cùng partition;
- Timeout và không biết kết quả commit;
- Các hạn chế khi dùng cùng statement/batch.

Cú pháp `IF` không nên dùng tràn lan cho mọi row chỉ để “an toàn hơn” nếu workload không cần CAS.

### 10.4. Ví dụ tranh chấp trên cùng partition

Hai client:

```text
A: UPDATE order O100 IF version=7 -> v8, status=SHIPPED
B: UPDATE order O100 IF version=7 -> v8, status=CANCELLED
```

Chỉ một transition nên được áp dụng khi cả hai yêu cầu cạnh tranh đúng cùng expected version, theo bảo đảm LWT và lựa chọn consistency phù hợp.

Nhưng điều đó **không** tự tạo transaction cho các bảng phi chuẩn hóa khác:

```text
orders_by_id(O100)              -> SHIPPED
orders_by_customer_month(O100)  -> PAID
orders_by_seller_status(O100)   -> PAID
```

Nếu cập nhật các bảng còn lại qua fan-out/event, đó là một quy trình đồng bộ **đa bảng** có thể có khoảng lệch. LWT trên bảng nguồn chỉ bảo vệ invariant tại nơi được áp dụng.

### 10.5. IF NOT EXISTS không có nghĩa batch nhiều bảng là ACID

Một lỗi thường gặp là cho rằng `BEGIN BATCH ... APPLY BATCH` với nhiều write sẽ biến toàn bộ workflow thành một transaction ACID tương đương database quan hệ. Cassandra batch có semantics và giới hạn riêng; không nên coi nó là giải pháp chung để ràng buộc cập nhật nhiều partition hoặc nhiều bảng.

Khi cần một invariant xuyên nhiều đối tượng, cân nhắc đổi aggregate/schema, một authority riêng hoặc cơ chế transaction phù hợp với hệ.

### 10.6. CAS trong Cassandra có thể đắt vì hot partition

Nếu hàng nghìn worker cùng cập nhật một counter/claim trong một partition qua LWT, throughput có thể giảm mạnh vì mọi request tranh chấp trên cùng trạng thái.

Có thể cần:

- Chia workload theo business key;
- Giảm số lần CAS;
- Hàng đợi tuần tự theo key;
- Reservation/counter sharding với invariant bổ sung;
- Batch xử lý ở tầng ứng dụng khi phù hợp;
- Tránh dùng LWT cho những cập nhật không cần điều kiện.

Đừng dùng throughput của write thường để dự đoán throughput LWT.

## 11. Redis: một lệnh nguyên tử, Lua và WATCH/MULTI/EXEC

Redis xử lý các command với semantics nguyên tử của từng thao tác trong ngữ cảnh server. Nhưng một chuỗi:

```text
GET inventory:P100
if >= 2:
    DECRBY inventory:P100 2
```

**không phải** một check-and-write nguyên tử vì client có thể bị chen giữa hai lệnh.

### 11.1. SET NX cho tạo-if-absent

```redis
SET username:an.nguyen U42 NX
```

`NX` chỉ cho ghi nếu key chưa tồn tại. Có thể dùng thêm expiry cho một claim tạm thời:

```redis
SET claim:P100:slot1 worker-A NX PX 30000
```

Đây là một thao tác tạo claim có TTL trong Redis. Nhưng một Redis claim **không tự bảo đảm quyền sở hữu vĩnh viễn hoặc durable uniqueness** trên mọi tình huống failover và replication. Khi dùng để điều phối tài nguyên quan trọng, phải xét kiến trúc triển khai.

### 11.2. Trừ tồn kho nguyên tử bằng Lua

Trong Redis, Lua script có thể kiểm tra số lượng và trừ trong một thao tác thực thi nguyên tử theo semantics của server:

```lua
-- KEYS[1] = "inventory:P100"
-- ARGV[1] = quantity cần trừ

local current = tonumber(redis.call("GET", KEYS[1]))
local requested = tonumber(ARGV[1])

if not current or not requested or requested <= 0 then
    return -1
end

if current < requested then
    return 0
end

redis.call("DECRBY", KEYS[1], requested)
return 1
```

Quy ước kết quả minh họa:

- `1`: đã trừ thành công;
- `0`: không đủ tồn kho;
- `-1`: input hoặc trạng thái không hợp lệ.

Nhờ check và `DECRBY` được thực hiện trong cùng script trên server, hai client không thể chen lệnh Redis khác vào giữa các bước này theo mô hình thực thi script hỗ trợ.

**Cần chú ý:**

- Không nên viết script dài/chặn server; chạy script quá lâu gây ảnh hưởng tất cả client.
- Trong Redis Cluster, truy cập nhiều key trong script có những ràng buộc về key slots; cần định nghĩa key qua `KEYS` phù hợp.
- Atomic execution không đồng nghĩa transaction rollback đầy đủ nếu script đã thực hiện ghi rồi gặp lỗi về sau.
- Redis durability/replication/failover có bảo đảm riêng; script nguyên tử trên một node không tự trở thành transaction nhiều region.

### 11.3. WATCH/MULTI/EXEC cho optimistic transaction

Một hướng khác:

```text
WATCH inventory:P100
GET inventory:P100
Nếu đủ số lượng:
    MULTI
    DECRBY inventory:P100 2
    EXEC
```

Nếu key được theo dõi bị thay đổi giữa `WATCH` và `EXEC` theo semantics của Redis, transaction có thể bị abort (ví dụ `EXEC` trả kết quả nil/null theo client).

Ứng dụng phải:

1. Nhận biết `EXEC` thành công hay abort.
2. Khi abort, đọc lại trạng thái và tính lại điều kiện.
3. Giới hạn retry/backoff khi nhiều client tranh chấp.
4. Không thực hiện side effect ngoài Redis trước khi biết transaction đã thành công.

`WATCH` là optimistic concurrency ở tầng Redis, khác việc một client đọc rồi ghi vô điều kiện.

### 11.4. Release lock phải so sánh owner

Một đoạn không an toàn:

```redis
DEL lock:resource:R1
```

Nếu worker A giữ lock, hết TTL, worker B lấy lock mới, rồi worker A chạy `DEL` muộn, A có thể xóa lock của B.

Cần release theo điều kiện “giá trị owner vẫn là token của tôi”. Một Lua script có thể so rồi xóa:

```lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
```

Giải pháp này bảo vệ **việc xóa nhầm lock** trên key Redis, nhưng không tự ngăn worker A vẫn tiếp tục ghi vào một hệ khác sau khi lock của A hết hạn. Đó là lý do cần hiểu **fencing token** khi khóa bảo vệ tài nguyên ngoài Redis.

## 12. Azure Cosmos DB for NoSQL: ETag và If-Match

Trong Azure Cosmos DB for NoSQL, item có metadata như `_etag` để hỗ trợ **optimistic concurrency**. Client đọc item, lấy ETag, rồi ghi với điều kiện ETag vẫn khớp.

### 12.1. Mẫu dữ liệu

```json
{
  "id": "O100",
  "tenantId": "T1",
  "status": "PAID",
  "_etag": "\"some-etag-token\""
}
```

ETag là token do dịch vụ cung cấp, không phải trường ứng dụng nên tự tự tăng. Giá trị trên chỉ minh họa.

### 12.2. Quy trình If-Match

```text
Client A                           Cosmos DB
--------                           ---------
READ O100 ------------------------>
        <------------------------- item + ETag e7
Tính thay đổi
REPLACE O100 If-Match=e7 -------->
        <------------------------- success, ETag e8
```

Nếu client B sửa O100 và ETag đã đổi trước A gửi request, thao tác If-Match với e7 có thể bị từ chối bằng **HTTP 412 Precondition Failed** theo API tương ứng.

### 12.3. Vì sao không nên chỉ gửi replace vô điều kiện?

Nếu đọc document v7 rồi gửi một bản sao đầy đủ mà không có ETag precondition, ứng dụng có thể ghi đè thay đổi của người khác, nhất là khi nó chỉ định sửa một trường nhưng SDK replace toàn item.

OCC bằng ETag giúp phát hiện **lost update**.

### 12.4. Transactional batch trong partition

Cosmos DB for NoSQL có khả năng transactional batch trong phạm vi **cùng logical partition key** theo giới hạn dịch vụ, giúp nhóm nhiều thao tác mà cần atomicity.

Nhưng một update có ETag trên item A và một write riêng trên item B không tự bảo đảm cả hai commit cùng nhau. Cần dùng batch/giao dịch khi các item thuộc phạm vi được hỗ trợ, hoặc một workflow khác khi chúng nằm ở partition khác.

### 12.5. Multi-region và conflict resolution

Khi bật cấu hình đa vùng ghi, cần xét quy tắc conflict resolution và mô hình consistency của container. Một ETag precondition tại một vùng **không tự chứng minh invariant đã được bảo vệ toàn cục giữa các vùng độc lập**.

Với yêu cầu duy nhất nghiêm ngặt, nên kiểm tra khả năng và phạm vi bảo đảm của đúng cấu hình, không suy từ một demo single-region.

## 13. Cloud Firestore: precondition và transaction

Cloud Firestore hỗ trợ transaction và một số precondition dựa trên trạng thái document, như tồn tại hay update time, tùy SDK/API.

### 13.1. Transaction đọc rồi cập nhật

Một mẫu giao dịch tại SDK server-side:

```javascript
// Ví dụ minh họa với Firestore Admin SDK đã tạo biến db.
const inventoryRef = db.collection("inventory").doc("P100");

const reserved = await db.runTransaction(async (tx) => {
  const snapshot = await tx.get(inventoryRef);

  if (!snapshot.exists) {
    return false;
  }

  const available = snapshot.get("available");

  if (typeof available !== "number" || available < 2) {
    return false;
  }

  tx.update(inventoryRef, {
    available: available - 2
  });

  return true;
});
```

Transaction API có thể **chạy lại callback** khi gặp xung đột, tùy SDK và cấu hình. Vì thế callback nên thuần túy về nghiệp vụ, không gửi email, thu tiền hay gọi API bên ngoài mỗi lần nó chạy.

### 13.2. Vì sao transaction khác đọc ngoài rồi update?

Đọc và quyết định nằm trong transaction của Firestore. Database/SDK phối hợp để phát hiện thay đổi concurrent và commit theo bảo đảm transaction, thay vì application tự kiểm tra ở một request rồi ghi vô điều kiện ở request khác.

Những điều kiện về thứ tự đọc trước ghi, giới hạn thời gian/kích thước, retry và contention phụ thuộc API/sản phẩm.

### 13.3. Precondition theo update time

Nếu chỉ cần xác nhận document chưa thay đổi kể từ lúc đọc, có thể sử dụng precondition theo `updateTime` trong những API hỗ trợ.

Ý tưởng:

```text
read DOC -> updateTime=t1
update DOC IF updateTime=t1
=> success hoặc precondition failure
```

Một precondition dựa trên tồn tại `exists=false` cũng hữu ích cho create-if-absent theo API tương ứng.

### 13.4. Đừng tách side effect khỏi transaction mà vẫn đòi exactly-once

Ví dụ code sai:

```javascript
await db.runTransaction(async (tx) => {
  const snapshot = await tx.get(orderRef);

  // Sai thiết kế: gửi email trong callback có thể được retry!
  await sendConfirmationEmail();

  tx.update(orderRef, {
    status: "PAID"
  });
});
```

Vì callback có thể chạy lại hoặc transaction abort, email có thể được gửi dù ghi database chưa commit, thậm chí gửi nhiều lần.

Một hướng phù hợp là commit trạng thái và outbox/event trong cơ chế nguyên tử được hỗ trợ, rồi xử lý side effect bất đồng bộ, idempotent.

## 14. Couchbase CAS và Elasticsearch concurrency tokens

Không phải hệ nào cũng dùng trường `version` do ứng dụng tự quản lý.

### 14.1. Couchbase CAS

Couchbase có thể trả một **CAS value** khi đọc document. Khi cập nhật, client gửi CAS đã nhận để nói “chỉ replace nếu document vẫn là phiên bản tôi đọc”.

Giả mã:

```text
result = collection.get("product::P100")
currentDocument = result.content
casToken = result.cas

newDocument = modify(currentDocument)

collection.replace(
    "product::P100",
    newDocument,
    cas = casToken
)
```

Nếu document đã bị writer khác thay đổi, replace có thể thất bại do CAS mismatch. Cú pháp và loại exception phụ thuộc SDK; đây là giả mã.

### 14.2. Elasticsearch/OpenSearch

Với Elasticsearch, một document có metadata như `_seq_no` và `_primary_term` để hỗ trợ optimistic concurrency. Client có thể dùng precondition tương ứng với các tham số `if_seq_no` và `if_primary_term` khi ghi trong API hỗ trợ.

Ý tưởng:

```text
GET document:
    _seq_no = 42
    _primary_term = 3

UPDATE with:
    if_seq_no = 42
    if_primary_term = 3
```

Nếu tài liệu đã thay đổi hoặc primary term không còn khớp, write sẽ bị conflict thay vì ghi đè vô điều kiện.

Đây là concurrency control của document/index tương ứng. Nó không biến search engine thành cơ chế transaction nhiều document phục vụ ledger tài chính.

### 14.3. ETag/CAS token có thể là opaque

Đừng parse một CAS/ETag như số version nghiệp vụ nếu sản phẩm không hứa cấu trúc đó. Phần mềm nên lưu và gửi lại **token nguyên vẹn**, trong phạm vi thời hạn/context hợp lệ.

## 15. So sánh các hệ NoSQL theo phạm vi và chi phí

| Hệ | Cơ chế điển hình | Phạm vi cần hiểu | Chi phí/cảnh báo |
|---|---|---|---|
| DynamoDB | `ConditionExpression` trên Put/Update/Delete | Item; transaction đa item qua API riêng | Conflict, capacity, global table semantics |
| MongoDB | Filter và update nguyên tử | Một document; multi-document transaction riêng | Unique index, upsert race, transaction retries |
| Cassandra | `IF NOT EXISTS`, `IF ...` (LWT) | Điều kiện trong phạm vi CQL/LWT hỗ trợ | Paxos coordination, hot partition, serial consistency |
| Redis | `SET NX`, Lua, `WATCH/MULTI/EXEC` | Key(s) theo semantics server/cluster | Atomic execution ≠ durability, side effects ngoài Redis |
| Cosmos DB for NoSQL | `_etag` + If-Match, transactional batch | Item; batch trong logical partition | ETag conflict, RU, multi-region configuration |
| Firestore | Transaction và document precondition | Document(s) trong transaction theo giới hạn | Callback retry, contention, cost |
| Couchbase | CAS token khi replace/update | Document | CAS mismatch, SDK/version semantics |
| Elasticsearch | `if_seq_no` + `if_primary_term` | Một document/index write | Không thay transaction nguồn, visibility/indexing |

Không nên kết luận “hệ nào mạnh nhất” chỉ từ việc có CAS. Cần hỏi **bất biến thực tế**, latency, tải ghi, dữ liệu phân vùng và yêu cầu multi-region.

## 16. Atomicity một bản ghi khác transaction nhiều bản ghi

### 16.1. Một invariant nằm gọn một item

Giả sử:

```json
{
  "productId": "P100",
  "available": 5,
  "reserved": 2
}
```

Nếu invariant chỉ là `available >= 0`, một conditional decrement trên item có thể đủ bảo vệ bước trừ tồn kho.

### 16.2. Một invariant trải qua hai item

Giả sử:

```text
Account A: balance = 100
Account B: balance = 100
```

Chuyển 30 đơn vị từ A sang B cần:

1. Trừ A 30;
2. Cộng B 30;
3. Không được mất tiền, nhân đôi tiền, hoặc hiển thị trạng thái commit nửa chừng ngoài hợp đồng.

Một CAS trên A thành công **không đảm bảo** B đã được cộng. Nếu cần tính nguyên tử xuyên cả hai item, phải có transaction phù hợp hoặc một quy trình ledger/reservation/saga với mô hình bất biến khác.

### 16.3. “Gộp aggregate để tận dụng atomicity” có giới hạn

Một cách thiết kế NoSQL là đặt những trường cần sửa nguyên tử trong **cùng document/item**.

Ví dụ trạng thái đơn và tổng tiền có thể nằm trong document order. Nhưng không phải mọi thứ nên nhét vào một document khổng lồ:

- Giới hạn kích thước item/document;
- Hot key khi nhiều request cùng cập nhật;
- Write amplification;
- Xung đột OCC không cần thiết;
- Chi phí tải toàn bộ aggregate;
- Khó phân vùng mở rộng.

Hãy chọn ranh giới aggregate theo **bất biến cần bảo vệ**, không chỉ để né mọi transaction.

### 16.4. Write skew: hai CAS đều thành công nhưng invariant tổng thể sai

Giả sử quy định:

> “Trong ca trực luôn phải có ít nhất một bác sĩ trực.”

Hai document:

```json
{"doctorId": "D1", "onCall": true, "version": 5}
{"doctorId": "D2", "onCall": true, "version": 8}
```

D1 đọc thấy D2 trực, quyết định tự nghỉ. D2 đọc thấy D1 trực, quyết định tự nghỉ. Mỗi người CAS **document riêng**:

```text
D1 CAS D1.onCall true -> false: thành công
D2 CAS D2.onCall true -> false: thành công
```

Mỗi CAS đều đúng, nhưng cuối cùng **không còn bác sĩ nào trực**. Đây là ví dụ **write skew**: invariant tồn tại trên **tập nhiều bản ghi**, không được bảo vệ bởi CAS cục bộ.

Cách giải có thể là:

- Đưa trạng thái ca trực vào một aggregate chung có CAS;
- Transaction/isolation đủ mạnh kiểm tra và ghi tập bản ghi;
- Một token/slot ownership authoritative;
- Mô hình reservation/phân quyền quyết định tập trung.

Điều quan trọng là **xác định đúng phạm vi của invariant trước khi chọn kỹ thuật**.

## 17. Conditional create và tính duy nhất của business key

### 17.1. Kiểm tra tên/email duy nhất phải có authority

Một hệ có thể lưu:

```text
users_by_id[U42] = { email: "an@example.com" }
users_by_email["an@example.com"] = U42
```

Nếu email phải duy nhất, `users_by_email` có thể đóng vai trò **bảng claim duy nhất** theo email đã chuẩn hóa, dùng conditional create.

Quy trình:

~~~text
Normalize email
       |
       v
Conditional create claim(email -> userId)
       |
       +--> conflict -> email đã được chiếm
       |
       v
Create user document
       |
       v
Mark claim committed / complete workflow
~~~

Vấn đề: claim thành công nhưng tạo user thất bại. Một bảng claim + user nằm ở hai object, nên cần transaction nếu có, hoặc trạng thái workflow và cơ chế recovery/timeout/compensation phù hợp.

### 17.2. Chuẩn hóa khóa trước khi CAS

Các chuỗi:

```text
An@Example.com
an@example.com
an@example.com␠
```

có thể được ứng dụng coi là cùng email theo policy cụ thể hoặc không; cần quy định chuẩn hóa rõ ràng. CAS của ba key khác nhau không ngăn duplicate về nghĩa nghiệp vụ nếu normalization thiếu thống nhất.

Tương tự:

- Tên đăng nhập có Unicode normalization.
- Số điện thoại cần chuẩn hóa định dạng quốc tế theo policy.
- Mã voucher có quy tắc case sensitivity.
- Slug có thể xung đột khi chuyển chữ có dấu sang không dấu.

Database chỉ bảo vệ **khóa được cung cấp**, không tự hiểu ngữ nghĩa business key.

### 17.3. Tính duy nhất toàn cầu và sharding

Một unique index hoặc conditional put theo partition key có thể bảo vệ một phạm vi cụ thể. Nếu dữ liệu được sharded/multi-region, phải xác định:

- Key uniqueness thuộc tenant hay toàn hệ?
- Có authority cho một normalized key không?
- Shard key có phù hợp unique constraint không?
- Có nhiều region ghi độc lập không?
- Conflict được hòa giải sau replication hay từ chối ngay?

Chỉ thêm một điều kiện “chưa thấy username” tại mỗi region **không tự tạo global uniqueness**.

## 18. ABA problem: giá trị quay lại trạng thái cũ

Giả sử một client đọc:

```text
status = FREE
```

Trong lúc client chuẩn bị CAS, hai thao tác khác diễn ra:

```text
FREE -> HELD -> FREE
```

Client chỉ so sánh `status == FREE` và thấy điều kiện vẫn đúng, dù record đã trải qua một chu kỳ thay đổi. Đây là **ABA problem**.

### 18.1. Vì sao ABA quan trọng?

Trong một số bài toán, nếu trạng thái trở về `FREE` thì việc tiếp tục thao tác là hợp lệ. Nhưng với lease/ownership hoặc workflow, việc giá trị quay lại như cũ **không có nghĩa mọi thông tin bên ngoài vẫn như lần đầu**.

Ví dụ:

- Slot từng được giữ bởi booking B1 rồi được giải phóng.
- Worker cũ mang kết quả tính toán từ trước B1.
- Slot lại thành FREE, worker cũ CAS theo trạng thái FREE và ghi dữ liệu stale.

### 18.2. Chặn ABA bằng version/generation

Thay vì chỉ so:

```text
status = FREE
```

so cả:

```text
status = FREE
AND version = 12
```

Chu trình:

```text
FREE v12 -> HELD v13 -> FREE v14
```

Worker cũ mang expected version 12 sẽ bị từ chối ở trạng thái `FREE v14`.

Một **generation** riêng có thể hữu ích nếu business key được tái sử dụng sau delete/recreate. Khi đó không cho thao tác của generation cũ cập nhật entity mới dù tên khóa trùng nhau.

### 18.3. Version cần tăng bền vững và có phạm vi rõ

Nếu xóa hoàn toàn bản ghi rồi tạo lại với `version=0`, một token cũ `expectedVersion=0` có thể trở nên hợp lệ sai ngữ cảnh. Có thể cần:

- Generation ID không tái sử dụng;
- Tombstone/version marker;
- ID thực thể mới;
- Fencing token từ authority;
- Dữ liệu history/ledger phù hợp.

Đây là vấn đề đặc biệt quan trọng với lock, reservation và tài nguyên có thể được “giải phóng rồi cấp lại”.

## 19. Leases và distributed locks: CAS chưa đủ ngăn worker cũ

Giả sử worker A chiếm quyền xử lý job bằng lock TTL 30 giây:

```text
T0: A lấy lock, bắt đầu xử lý.
T1: A bị pause 60 giây.
T2: Lock A hết hạn.
T3: B lấy lock mới.
T4: A hoạt động lại và ghi kết quả cũ.
```

Ngay cả nếu Redis `SET NX PX` làm việc đúng, **A vẫn có thể tiếp tục sau khi quyền sở hữu đã hết**.

### 19.1. So sánh owner khi release

Release lock bằng điều kiện owner giúp A không xóa lock của B. Nhưng nó không ngăn A gọi một database khác để ghi.

### 19.2. Fencing token

Một giải pháp mạnh hơn cho những tài nguyên có thể kiểm tra token là cấp token tăng đơn điệu:

```text
A nhận fencing token 41
A bị pause
B nhận fencing token 42
Resource tiếp nhận write của B (42)
A thức dậy, gửi write token 41
Resource từ chối vì 41 < 42
```

Tài nguyên đích phải lưu và kiểm tra **last accepted fencing token** trong một thao tác có bảo đảm phù hợp. Chỉ gắn số token vào request nhưng đích không kiểm tra thì không có tác dụng.

### 19.3. Không phải mọi lock đều cần fencing

Với cache recomputation có thể làm lại, một lock best-effort có thể đủ giảm số request trùng. Với thay đổi tiền, quyền truy cập hoặc thiết bị vật lý, cần kỹ thuật và bảo đảm mạnh hơn.

Thiết kế nên xuất phát từ **hậu quả nếu worker cũ ghi sau lease hết hạn**, không chỉ từ việc có lệnh `SET NX`.

## 20. Retry: khi điều kiện không thỏa và khi không biết kết quả

### 20.1. Conditional conflict là một kết quả bình thường

Nếu client A đọc version 7, còn B đã ghi version 8, thì request CAS của A bị conflict. Không nhất thiết là lỗi hệ thống.

Ứng dụng có thể:

1. Đọc lại dữ liệu hiện tại.
2. Quyết định liệu ý định ban đầu vẫn hợp lệ.
3. Tính mutation mới.
4. Thử CAS lại với version mới.
5. Giới hạn số lần thử và thời gian.
6. Trả conflict cho người dùng khi không thể merge an toàn.

**Không được retry nguyên payload cũ với expected version mới mà không kiểm tra ý nghĩa nghiệp vụ.** Ví dụ form A thay toàn document v7, sau khi conflict nếu đơn giản chuyển `expected=8` rồi ghi lại document cũ, thay đổi của B vẫn bị mất.

### 20.2. Timeout tạo kết quả không chắc chắn

Giả sử client gửi conditional decrement:

```text
Client -> DB: IF available>=1 DECREMENT 1
DB áp dụng thành công
DB -> Client: response bị mất
Client nhìn thấy TIMEOUT
```

Nếu client gửi lại **một request trừ một đơn vị nữa** mà không có idempotency, nó có thể giữ hai sản phẩm thay vì một.

Vì vậy các trạng thái cần phân biệt:

| Tình huống | Cách nhìn |
|---|---|
| Điều kiện không thỏa rõ ràng | Không áp dụng mutation đó |
| Response thành công | Mutation được xác nhận theo guarantee |
| Timeout/network error | Có thể đã áp dụng hoặc chưa |
| Process crash | Cần phục hồi từ nguồn bền vững |
| Retry trùng | Cần idempotency để không nhân đôi business action |

### 20.3. Idempotency key

Một request đặt trước có ID:

```json
{
  "requestId": "RESERVE-1001",
  "productId": "P100",
  "quantity": 2
}
```

Backend có thể lưu trạng thái:

```json
{
  "requestId": "RESERVE-1001",
  "state": "COMMITTED",
  "productId": "P100",
  "quantity": 2,
  "reservationId": "R1001"
}
```

Nếu client retry cùng requestId, backend tra/nhận lại kết quả ban đầu, không tạo reservation mới.

Nhưng **idempotency record và việc trừ inventory cũng cần được phối hợp nguyên tử hoặc bằng workflow phục hồi đáng tin cậy**. Viết request record rồi trừ hàng bằng hai thao tác rời không tự giải quyết mọi crash window.

### 20.4. Idempotency không giống CAS

- **CAS:** ngăn ghi khi trạng thái không như dự kiến.
- **Idempotency:** đảm bảo gửi lại cùng một ý định nghiệp vụ không thực hiện tác động nhiều lần.

Một workflow quan trọng thường cần **cả hai**. CAS tồn kho đảm bảo không âm; idempotency đảm bảo một yêu cầu reservation không trừ tồn kho hai lần do retry.

## 21. Retry có backoff và giới hạn tranh chấp

Khi 100 worker cùng muốn sửa một item nóng, tất cả có thể:

```text
READ version=7
CAS expected=7
99 worker nhận conflict
99 worker đọc lại version=8
CAS expected=8
...
```

Nếu retry ngay không giới hạn, hệ có thể rơi vào **contention storm**:

- Tăng latency;
- Tăng read/write capacity;
- Tăng số request thất bại;
- Làm nóng một partition/shard;
- Tạo áp lực đồng thuận đối với LWT;
- Làm tăng chi phí và độ bất ổn.

### 21.1. Exponential backoff với jitter

Một chính sách minh họa:

\[
delay_n = \min(maxDelay,\ baseDelay \times 2^n) + jitter
\]

Trong đó jitter là một phần ngẫu nhiên có giới hạn. Không có giá trị chung cho mọi workload; nên dùng backoff theo thư viện/SDK, thời hạn request và SLO.

### 21.2. Khi nào không nên retry tự động?

- Người dùng sửa form có xung đột ý nghĩa; cần yêu cầu xem lại.
- State machine đã chuyển sang trạng thái không còn hợp lệ.
- Reservation đã hết hạn.
- Retry có thể gây side effect ngoài database chưa được idempotent.
- Deadline của request đã qua.
- Cùng một key bị tranh chấp quá cao; cần queue/đổi kiến trúc.

### 21.3. Giảm contention bằng mô hình khác

Một số cách:

- **Single writer per key:** tuần tự hóa tác vụ qua partitioned queue.
- **Sharded counters:** chia tải cộng dồn rồi tổng hợp, nếu invariant cho phép.
- **Reservation tokens:** tách yêu cầu khỏi bước commit cuối.
- **Append-only facts/ledger:** ghi event duy nhất theo request ID rồi tổng hợp, tránh sửa một counter nóng trong mọi request.
- **Aggregate redesign:** gom bất biến cần bảo vệ, nhưng không làm item quá lớn.
- **Smoothing/batching:** gộp nhiều cập nhật nhỏ theo chu kỳ nếu độ trễ cho phép.

Điều kiện chọn tùy mức nhất quán cần đạt. Sharded counter không tự bảo vệ một quota toàn cục nghiêm ngặt nếu các shard được tăng độc lập mà không có cơ chế cấp hạn mức.

## 22. Đường cập nhật trạng thái theo finite state machine

Một trạng thái đơn hàng:

```text
CREATED -> PAID -> PACKED -> SHIPPED -> DELIVERED
    \         \
     \         -> REFUNDED (theo quy tắc cụ thể)
      -> CANCELLED
```

Nếu API chỉ gửi:

```text
SET status = "SHIPPED"
```

thì một client cũ có thể chuyển đơn đã `CANCELLED` sang `SHIPPED`.

### 22.1. Gắn trạng thái nguồn vào điều kiện

Ví dụ:

```text
UPDATE order O100
IF status == "PACKED" AND version == 8
SET status = "SHIPPED", version = 9
```

Điều này bảo vệ một transition cụ thể.

### 22.2. Version và trạng thái bổ trợ nhau

Nếu chỉ so version:

```text
IF version = 8
```

mà ứng dụng có bug đặt trạng thái sai từ snapshot, CAS vẫn có thể ghi một transition không hợp lệ.

Nếu chỉ so state:

```text
IF status = "PACKED"
```

mà các field khác thay đổi quan trọng giữa lúc đọc và lúc ghi, client có thể dựa vào dữ liệu cũ.

Có thể cần cả **source state** và **expected version**, hoặc một predicate bao trùm những trường liên quan đến bất biến.

### 22.3. Kiểm soát side effect

Chuyển sang `SHIPPED` có thể cần:

- Cập nhật order;
- Tạo vận đơn;
- Phát event;
- Gửi thông báo;
- Cập nhật bảng theo status.

Nếu conditional update nguồn đã commit nhưng gửi thông báo thất bại, workflow cần outbox/retry. **CAS không tự phát event chính xác một lần**, cũng không biến tất cả side effect ngoài database thành một giao dịch.

## 23. Điều kiện một bản ghi và một ràng buộc tập hợp

### 23.1. Quota theo một item

```json
{
  "tenantId": "T1",
  "used": 80,
  "quota": 100
}
```

Nếu cả `used` và `quota` nằm trong một item, một conditional update có thể kiểm tra:

```text
used + requested <= quota
```

rồi tăng `used` nguyên tử.

### 23.2. Quota được chia nhiều shard

Nếu mỗi shard có `usedShard` và cùng quota tổng 100, kiểm tra riêng từng shard:

```text
usedShard < 100
```

không bảo vệ tổng usage toàn tenant. Có thể mỗi shard đều tăng hợp lệ nhưng tổng vượt quota.

Một mô hình khác có thể cấp trước token/hạn mức cho shard, dùng một authority quản lý quota tổng, hoặc transaction/allocator có semantics phù hợp.

### 23.3. Điều kiện “không tồn tại record nào như X”

Nếu yêu cầu:

> “Mỗi khách hàng chỉ được có tối đa một subscription ACTIVE.”

Đây là **ràng buộc tập hợp**. Chỉ condition update một record không đủ nếu có thể tạo hai record subscription mới đồng thời.

Các cách:

- Đưa unique active subscription claim về một key xác định theo customer;
- Unique partial index (nếu DB hỗ trợ và semantics đúng);
- Transaction kiểm tra và tạo theo ranh giới phù hợp;
- Một aggregate customer-subscription trạng thái duy nhất.

Thiết kế đúng phải đưa invariant vào phạm vi mà hệ có thể **kiểm tra và ghi nguyên tử**.

## 24. CAS với delete và recreate: dữ liệu cũ xuất hiện lại

Giả sử một record bị xóa:

```text
v7: K = ACTIVE
v8: K = DELETED
```

Nếu hệ xóa vật lý ngay và quên version 8, một worker cũ có thể thực hiện:

```text
PUT K = ACTIVE IF key absent
```

và tạo lại K. Điều kiện “key absent” đúng nhưng **ý định nghiệp vụ không đúng**.

### 24.1. Khi nào create-if-absent là đủ?

Nếu tạo lại cùng key là hành vi hợp lệ và không có worker cũ có thể replay, create-if-absent có thể đủ.

Nếu key biểu diễn một identity không được tái tạo sau delete, cần:

- Tombstone/negative record;
- Generation ID;
- Operation ledger;
- Retention phù hợp với replay window;
- Kiểm tra quyền tái tạo;
- Quy trình xóa có xác nhận.

### 24.2. CAS không thay retention của tombstone

Một tombstone bị dọn trước khi mọi event/replica cũ được xử lý có thể mở đường cho dữ liệu hồi sinh. Điều này liên quan tới semantics của hệ lưu trữ, backup/replay và chính sách giữ trạng thái xóa.

Đừng tự đặt TTL ngắn cho delete marker chỉ để tiết kiệm storage mà không biết tuổi tối đa của request/event có thể quay lại.

### 24.3. Conditional delete cũng cần version

Thay vì:

```text
DELETE K
```

một worker muốn xóa đúng instance mà nó sở hữu nên kiểm tra:

```text
DELETE K IF generation = 5 AND owner = workerA
```

Nếu K đã được tái cấp cho thế hệ 6, xóa của worker A phải bị từ chối.

## 25. Multi-region: bảo đảm tại một điểm ghi có thể không phải toàn cục

NoSQL phân tán qua nhiều region có những mô hình:

- Một region leader nhận ghi;
- Multi-region writes với conflict resolution;
- Replication bất đồng bộ;
- Quorum/dẫn xuất theo topology;
- Strong consistency trong phạm vi hỗ trợ;
- Eventual consistency giữa các bản sao.

### 25.1. Hai vùng cùng thấy “chưa tồn tại”

Giả sử Region A và B nhận đăng ký username `an.nguyen` đồng thời:

```text
Region A: key absent -> conditional create succeeds
Region B: key absent -> conditional create succeeds
         |                         |
         +---- asynchronous replication ----+
                           |
                    Resolve conflict
```

Trong một số mô hình multi-master eventual replication, cả hai request **có thể được xác nhận cục bộ** trước khi conflict được giải quyết. Điều đó không đáp ứng hợp đồng “chỉ một đăng ký được xác nhận thành công trên toàn cầu”.

### 25.2. Các phương án thiết kế

- Route mọi claim của một business key về **một authority region/partition**.
- Dùng dịch vụ cung cấp uniqueness/transaction toàn cục với bảo đảm rõ ràng.
- Phân bổ dải tên/ID không trùng theo region nếu yêu cầu cho phép.
- Chấp nhận conflict resolution bất đồng bộ chỉ khi sản phẩm chấp nhận việc hai request từng thành công rồi một bị bù/hủy.
- Phân biệt global uniqueness với uniqueness theo tenant/region.

### 25.3. Không đồng nhất consistency level với isolation

Việc một request dùng “strong read” hoặc “quorum write” không tự bảo đảm một workflow nhiều item có serializable isolation. Cần tìm hiểu **từng thao tác**, scope và giao thức mà engine thực hiện.

Một mô tả kiến trúc nên viết:

> “Conditional update nguyên tử trên item X tại authority Y; không có transaction toàn cục cho X và Z.”

thay vì:

> “Database hỗ trợ strong consistency nên mọi check-and-write trong hệ đều an toàn.”

## 26. Lỗi thiết kế API: trả kết quả rõ ràng

Một API cập nhật có điều kiện nên biểu diễn được ba lớp kết quả:

1. **Đã áp dụng**;
2. **Không áp dụng do điều kiện sai**;
3. **Chưa biết chắc, cần reconcile/idempotent retry**.

### 26.1. REST và optimistic concurrency

Một API có thể dùng:

```http
GET /api/orders/O100
```

Response:

```http
HTTP/1.1 200 OK
ETag: "order-v7"
Content-Type: application/json

{
  "orderId": "O100",
  "status": "PACKED",
  "version": 7
}
```

Client gửi:

```http
PATCH /api/orders/O100
If-Match: "order-v7"
Content-Type: application/json

{
  "status": "SHIPPED"
}
```

Server ánh xạ precondition sang **conditional update thật** ở database. Nếu phiên bản thay đổi, có thể trả:

```http
HTTP/1.1 412 Precondition Failed
Content-Type: application/json

{
  "code": "VERSION_CONFLICT",
  "message": "Đơn hàng đã được thay đổi. Hãy tải lại."
}
```

Đây là một hợp đồng API minh họa. ETag ở ví dụ là token ứng dụng tạo và phải được kiểm tra/đối chiếu đúng. Không chỉ so header trong memory rồi ghi vô điều kiện.

### 26.2. 409 và 412

- **412 Precondition Failed:** thường phù hợp khi điều kiện HTTP `If-Match` hoặc precondition được chỉ định không còn đúng.
- **409 Conflict:** có thể dùng khi xung đột trạng thái nghiệp vụ, như đơn đã hủy không được giao.
- **400/422:** payload không hợp lệ.
- **503/504 hoặc lỗi tạm thời:** không tự khẳng định mutation đã rollback.

Cách chọn status cần nhất quán trong API contract. Client cần hiểu retry hay không retry, và có nên đọc lại dữ liệu.

### 26.3. ETag không được dùng làm quyền truy cập

Biết ETag của document không chứng minh caller được phép sửa document đó. Authorization/tenant scope phải được kiểm tra độc lập với CAS.

### 26.4. Idempotency-Key cho nghiệp vụ có side effect

Một API tạo reservation có thể nhận:

```http
POST /api/reservations
Idempotency-Key: RESERVE-1001
Content-Type: application/json

{
  "productId": "P100",
  "quantity": 2
}
```

Backend phải định nghĩa:

- RequestId có phạm vi user/tenant nào;
- Cùng key nhưng payload khác sẽ được xử lý sao;
- Kết quả được lưu bao lâu;
- Khi request ban đầu chưa hoàn tất thì retry nhận trạng thái gì;
- Cách đối soát khi server đã commit nhưng phản hồi mất.

CAS và idempotency là hai lớp bổ trợ trong workflow này.

## 27. Kiến trúc reservation có CAS và event

Một trường hợp thực tế là đặt trước hàng tồn kho.

### 27.1. Thành phần

```text
                 Reservation API
                        |
                        v
                 Validate request
                        |
                        v
             Idempotency / request state
                        |
                        v
          Conditional decrement Inventory
                        |
              +---------+----------+
              |                    |
            Applied             Not applied
              |                    |
              v                    v
      Create reservation       OUT_OF_STOCK /
      / record result          retry if conflict
              |
              v
        Emit event via
       reliable workflow
              |
              v
         Orders / Views
```

Đây là sơ đồ ý tưởng về các bước. **Không nên triển khai tất cả các mũi tên như những lệnh rời không có cơ chế phục hồi** rồi gọi đó là transaction.

### 27.2. Trạng thái reservation

Có thể lưu:

```text
REQUESTED
   |
   v
RESERVED
   |
   +--> CONFIRMED
   |
   +--> EXPIRED / CANCELLED
```

Mỗi transition cần điều kiện:

```text
CONFIRM only if state == RESERVED
EXPIRE  only if state == RESERVED AND expiresAt <= now
```

Một transition chạy muộn không được biến `CONFIRMED` thành `EXPIRED` nếu chính sách không cho phép.

### 27.3. Hết hạn reservation và hoàn tồn kho

Nếu reservation hết hạn, cần cộng lại tồn kho **đúng một lần**. Chỉ dùng job:

```text
if now > expiresAt:
    inventory = inventory + quantity
```

có thể cộng nhiều lần khi job retry.

Một hướng tốt hơn:

1. Conditional transition `RESERVED -> EXPIRED` chỉ được một caller áp dụng.
2. Phát một event có request/reservation ID ổn định.
3. Workflow hoàn tồn kho idempotent theo reservation ID.
4. Đối soát reservation, inventory và order.

Tuy nhiên, transition reservation và inventory ở hai item vẫn cần transaction hoặc thiết kế workflow phù hợp để xử lý crash ở giữa.

### 27.4. Đừng coi TTL xóa reservation là đủ

Nếu reservation tự biến mất vì TTL, việc kiểm tra “đã hoàn tồn kho chưa?” có thể khó nếu không có ledger/tombstone/event. TTL giúp dọn dữ liệu, nhưng **không tự hoàn tác những thay đổi nghiệp vụ đã commit**.

## 28. Testing concurrency: phải tạo được cạnh tranh thật

Một test tuần tự:

```text
reserve(1) -> thành công
reserve(1) -> hết hàng
```

không chứng minh implementation chống race khi có hai request đồng thời.

### 28.1. Test hai client tranh chấp

Khởi tạo:

```text
Inventory P100 = 1
```

Cho 20 worker đồng thời yêu cầu `reserve(1)` và chờ hoàn tất. Với invariant cần bảo vệ:

- Chỉ một reservation nghiệp vụ thành công;
- Tồn kho cuối cùng không âm;
- Không có hai ownership claims cho cùng slot;
- Các request bị từ chối không làm side effect;
- Retry cùng request ID không thêm reservation thứ hai.

### 28.2. Barrier để tạo race

Ví dụ Java minh họa cấu trúc test song song:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ConcurrencyScenario {
    public void run(InventoryService service) throws Exception {
        int workers = 20;
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);

        ExecutorService executor = Executors.newFixedThreadPool(workers);
        List<Future<Boolean>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < workers; i++) {
                final int requestIndex = i;
                futures.add(executor.submit(() -> {
                    ready.countDown();
                    start.await();
                    return service.reserve(
                            "P100",
                            1,
                            "request-" + requestIndex
                    );
                }));
            }

            ready.await();
            start.countDown();

            int successCount = 0;
            for (Future<Boolean> future : futures) {
                if (future.get()) {
                    successCount++;
                }
            }

            System.out.println("successful reservations = " + successCount);
        } finally {
            executor.shutdownNow();
        }
    }

    public interface InventoryService {
        boolean reserve(
                String productId,
                int quantity,
                String requestId
        );
    }
}
```

Đây là **khung mô phỏng đồng thời**, không phải bài test hoàn chỉnh: còn cần khởi tạo database thật, đưa `available=1`, kiểm tra bất biến, cleanup dữ liệu và xử lý timeout.

### 28.3. Test timeout sau commit

Một kịch bản quan trọng:

1. Request đến database và commit thành công.
2. Chặn/mất phản hồi cho client.
3. Client retry cùng idempotency key.
4. Xác nhận số reservation và số lần trừ tồn kho vẫn chỉ là một.

Đây thường là kịch bản mà code “CAS đúng” nhưng **business workflow vẫn bị trùng tác động** nếu không có idempotency.

### 28.4. Test thay đổi version và retry

- Hai client đọc v7, một ghi trước.
- Client còn lại nhận conflict.
- Nó phải đọc lại v8 và merge có quy tắc, không đơn giản đè snapshot cũ.
- Kiểm tra thay đổi của caller thứ nhất vẫn còn.

### 28.5. Test ABA và lease expiration

- Worker A có token 41 rồi bị pause.
- B có token 42 và ghi thành công.
- A resume, gửi token 41.
- Sink phải từ chối stale writer.

### 28.6. Test nhiều region khi thực sự chạy multi-write

Nếu sản phẩm cho phép hai region ghi đồng thời, phải thử với phân vùng mạng, độ trễ replication và conflict. Test một region khỏe mạnh không đủ để chứng minh uniqueness toàn cầu.

## 29. Quan sát và metrics của conditional writes

### 29.1. Nhóm metric

| Nhóm | Metric | Ý nghĩa |
|---|---|---|
| Kết quả | Applied/s, condition-failed/s | Tỷ lệ ghi thành công/xung đột |
| Độ trễ | p50/p95/p99 CAS latency | Xem chi phí phối hợp |
| Tranh chấp | Conflicts per key/partition | Phát hiện hot keys |
| Retry | Attempts per operation, retry delay | Phát hiện retry storm |
| Timeout | Unknown-outcome operations | Theo dõi rủi ro commit không rõ |
| Idempotency | Replayed request IDs, duplicate prevented | Xem bảo vệ side effect |
| Chất lượng dữ liệu | Oversell, negative inventory, duplicate usernames | Kiểm tra invariant thực |
| Hệ thống | CPU, RU/RCU/WCU, network, Paxos/LWT metrics | Đánh giá chi phí database |
| Multi-region | Replication lag, resolved conflicts | Quan sát nguy cơ xung đột vùng |
| Workflow | Pending reservations, compensation backlog | Biết giao dịch nhiều bước có hội tụ không |

Không phải metric nào cũng được database xuất sẵn; một số cần instrumentation ở ứng dụng.

### 29.2. Conflict rate cao không luôn là lỗi

Nếu một item rất hot và nhiều client cạnh tranh hợp lệ, conflict tăng có thể phản ánh cơ chế CAS đang **ngăn vi phạm invariant thành công**.

Nhưng conflict rate cao cũng có thể nghĩa là:

- Thiết kế hot key chưa tốt;
- Client retry quá nhanh;
- Cache đang phát phiên bản stale;
- Có writer cũ chạy lại;
- Workflow thiếu idempotency;
- UI gửi lại form nhiều lần.

Cần đánh giá tỷ lệ conflict cùng latency và hiệu quả nghiệp vụ.

### 29.3. SLO phải đo điều đúng cần bảo vệ

Ví dụ:

> Không có reservation nào được xác nhận thành công khi số đơn vị khả dụng đã được cấp hết; cùng request ID không được tạo hơn một reservation.

Đây là invariant nghiệp vụ. Một SLO phụ về latency:

> p95 conditional reservation dưới ngưỡng được sản phẩm xác định ở mức tải đại diện.

Nếu CAS rất nhanh nhưng cho hai reservation thành công, hệ vẫn sai. Nếu CAS đúng nhưng p95 quá cao do hot key, cần tối ưu kiến trúc nhưng không bỏ điều kiện bảo vệ.

## 30. Những sai lầm thường gặp

**“Đọc rồi kiểm tra rồi ghi là CAS.”** Không. Nếu điều kiện và ghi không diễn ra nguyên tử tại nơi lưu trữ/authority, vẫn có TOCTOU.

**“Database hỗ trợ atomic write thì code read-modify-write của tôi cũng atomic.”** Không. Atomicity của một lệnh không kéo dài qua nhiều round-trip tự do.

**“Dùng version là đủ dù ghi không kiểm tra version.”** Không. Lưu `version` chỉ có ích khi nó tham gia điều kiện bảo vệ.

**“Chỉ cần check stock trước lệnh DECREMENT.”** Không. Cần conditional decrement hoặc transaction phù hợp.

**“Tăng counter nguyên tử cũng bảo vệ quota.”** Không nếu không có điều kiện kiểm tra hạn mức cùng thao tác.

**“CAS trên document A bảo vệ bất biến giữa A và B.”** Không. Write skew vẫn có thể xảy ra.

**“LWT và write thường trong Cassandra có cùng chi phí.”** Không. LWT cần phối hợp đồng thuận theo semantics riêng và có thể tốn latency hơn.

**“Cassandra BATCH là ACID transaction trên mọi partition.”** Không. Phải hiểu phạm vi và semantics của batch/conditional batch thực tế.

**“MongoDB upsert tự chặn duplicate business key.”** Không nếu thiếu unique index hoặc khóa điều kiện đúng.

**“Unique index thay cho chuẩn hóa business key.”** Không. Index không tự đoán hai email dạng khác nhau là cùng giá trị theo policy ứng dụng.

**“Redis SET NX tạo lock nên worker cũ chắc chắn không thể ghi.”** Không. TTL hết và worker pause có thể đòi fencing/validation tại tài nguyên.

**“Lua script nguyên tử nghĩa là rollback mọi ghi nếu script lỗi.”** Không. Atomic execution của Redis không tự là ACID rollback của nhiều hệ.

**“ETag/CAS token là bằng chứng authorization.”** Không. Client vẫn phải có quyền thao tác.

**“Timeout nghĩa là điều kiện chưa được áp dụng.”** Không. Có thể database đã commit nhưng phản hồi mất.

**“CAS thành công nghĩa là side effect như email/thu tiền chắc chắn chỉ một lần.”** Không. Side effect bên ngoài cần idempotency/outbox/workflow.

**“Conflict thì đổi expectedVersion thành số mới và retry cùng object cũ.”** Có thể gây lost update nếu không merge theo ý nghĩa nghiệp vụ.

**“Condition ở hai region cùng bảo vệ uniqueness toàn cục.”** Không mặc định với hệ multi-master eventual replication.

**“Status trở về FREE giống hệt như chưa từng đổi.”** Có thể có ABA; cần version/generation khi ý nghĩa lịch sử quan trọng.

**“Xóa record là đã xóa marker version nên sự kiện cũ không thể quay lại.”** Không. Có thể cần tombstone/deletion ledger để chặn replay.

## 31. Quy trình chọn cơ chế conditional write

### Bước 1 — Viết invariant thành biểu thức cụ thể

Ví dụ:

```text
available >= requested
status in allowedPredecessors
version == expectedVersion
owner == callerOwner
usernameClaim == absent
```

Nếu không thể viết điều kiện rõ ràng, rất khó xác định đâu là phạm vi nguyên tử cần bảo vệ.

### Bước 2 — Xác định nơi lưu dữ liệu có quyền quyết định

- Item/document nào là authoritative?
- Có read model cập nhật bất đồng bộ không?
- Có nhiều region cùng ghi không?
- Có cache/replica stale không?

Không thực thi một business CAS quan trọng trên bản sao có thể trễ mà thiếu cơ chế kiểm tra authoritative.

### Bước 3 — Xác định phạm vi của invariant

- Một field?
- Một document/item?
- Một partition?
- Nhiều item cùng partition?
- Nhiều partition?
- Nhiều hệ thống?

Nếu invariant vượt phạm vi mà database có thể check-and-write nguyên tử, cần transaction hoặc thiết kế lại.

### Bước 4 — Chọn predicate và token

- Điều kiện trạng thái?
- Version tăng dần?
- ETag/CAS token?
- Presence/absence?
- Fencing generation?
- Điều kiện trên số đếm?

Chỉ so những trường cần thiết để tránh conflict thừa, nhưng không bỏ sót trường liên quan bất biến.

### Bước 5 — Gắn check với mutation

Dùng API native hỗ trợ:

- `ConditionExpression`;
- `updateOne(filter, update)`;
- CQL `IF`/LWT;
- Lua/WATCH;
- If-Match/ETag;
- Transaction/precondition.

Không chỉ kiểm tra bằng code rồi gọi `save()`.

### Bước 6 — Thiết kế kết quả và retry

Phân biệt:

- Applied;
- Conflict;
- Timeout/unknown;
- Validation/permission error.

Giới hạn retry và kết hợp idempotency khi request có side effect nghiệp vụ.

### Bước 7 — Giải quyết phần còn lại của workflow

Nếu còn nhiều bước:

- Transaction nếu có thể;
- Outbox/event;
- Reservation/compensation;
- Reconciliation;
- Audit/metrics;
- Fencing khi có worker cũ.

### Bước 8 — Kiểm thử đồng thời và sự cố

Kiểm thử nhiều client, timeout sau commit, retry cùng request ID, ABA, delete/recreate, node failover và multi-region khi phù hợp.

## 32. Bài tập thực hành

### Bài tập 1 — Phát hiện TOCTOU

Ứng dụng thực hiện:

```text
stock = read("P100")
if stock.available >= 1:
    write("P100", stock.available - 1)
```

Hai client cùng thấy `available=1`.

**Câu hỏi:** Vì sao cả hai có thể báo thành công?

**Gợi ý:** Check và write là hai thao tác tách biệt; cả hai có thể dùng cùng snapshot cũ. Cần conditional decrement nguyên tử.

### Bài tập 2 — OCC theo version

Order O100 đang `version=9`. Client A và B đều đọc v9 và muốn cập nhật.

**Câu hỏi:** Với `IF version=9 SET version=10`, bao nhiêu client có thể thành công cho cùng phiên bản ban đầu?

**Gợi ý:** Trong semantics CAS phù hợp, chỉ một mutation chuyển v9 sang v10; caller còn lại bị conflict.

### Bài tập 3 — Conditional update MongoDB

Viết `updateOne()` chỉ giảm `available` 3 đơn vị khi `available >= 3` trên document `_id="P100"`.

**Gợi ý:**

```javascript
db.inventory.updateOne(
  { _id: "P100", available: { $gte: 3 } },
  { $inc: { available: -3 } }
);
```

### Bài tập 4 — DynamoDB create-if-absent

Hai client cùng muốn tạo username `an.nguyen`.

**Câu hỏi:** `GetItem` rồi `PutItem` có an toàn không? Cần điều kiện gì?

**Gợi ý:** Không. Dùng `PutItem` với `ConditionExpression: attribute_not_exists(PK)` trên key username chuẩn hóa.

### Bài tập 5 — Cassandra LWT

Bảng `orders_by_id` chứa `status="PAID", version=5`.

**Yêu cầu:** Viết CQL chuyển trạng thái sang `SHIPPED`, version 6, chỉ khi version 5 và status PAID.

**Gợi ý:**

```sql
UPDATE orders_by_id
SET status='SHIPPED', version=6
WHERE order_id='O100'
IF version=5 AND status='PAID';
```

### Bài tập 6 — Redis WATCH

Worker A `WATCH` một key tồn kho, đọc 2 và chuẩn bị trừ 2. Worker B sửa key trước khi A gọi `EXEC`.

**Câu hỏi:** A phải xử lý thế nào?

**Gợi ý:** Nhận biết transaction bị abort theo semantics Redis, đọc lại, tính lại và retry có giới hạn. Không tự coi đã trừ thành công.

### Bài tập 7 — Redis Lua và side effect

Một Lua script trừ stock xong; ứng dụng gọi API thanh toán nhưng API timeout.

**Câu hỏi:** Lua script có đảm bảo toàn bộ stock + thanh toán là một giao dịch không?

**Gợi ý:** Không. Nó chỉ bảo vệ thao tác ở Redis. Cần workflow idempotent/transaction hoặc compensation giữa hai hệ.

### Bài tập 8 — ETag

Client đọc item Cosmos DB có ETag `e7`; client khác đã ghi và ETag thành `e8`.

**Câu hỏi:** Request `If-Match: e7` sẽ dẫn tới điều gì?

**Gợi ý:** Precondition có thể thất bại, thường HTTP 412 theo API; client cần đọc lại hoặc trả conflict.

### Bài tập 9 — Firestore transaction callback

Một transaction callback gửi email trước khi commit. SDK retry callback ba lần vì contention.

**Câu hỏi:** Điều gì sai?

**Gợi ý:** Side effect ngoài database có thể bị lặp. Không gửi email trực tiếp trong callback có thể retry; dùng event/outbox có xử lý idempotent.

### Bài tập 10 — Write skew

Hai bác sĩ D1/D2 đều đang trực; mỗi người check người kia còn trực rồi dùng CAS trên document riêng để nghỉ.

**Câu hỏi:** Vì sao cả hai CAS có thể thành công nhưng invariant thất bại?

**Gợi ý:** Invariant “ít nhất một người trực” nằm trên hai documents. Cần transaction/aggregate/authority bảo vệ tập trạng thái.

### Bài tập 11 — ABA

Một slot chuyển `FREE v10 -> HELD v11 -> FREE v12`. Worker cũ chỉ giữ `expectedStatus=FREE`.

**Câu hỏi:** Vì sao so status chưa đủ?

**Gợi ý:** Trạng thái đã quay lại cùng chữ nhưng generation/version khác. So version/generation nếu cần phát hiện thay đổi trung gian.

### Bài tập 12 — Unknown commit

Client gửi conditional decrement 1 và bị timeout. Có khả năng DB đã commit.

**Câu hỏi:** Có được retry một decrement mới với request ID khác không?

**Gợi ý:** Không nếu muốn bảo đảm một ý định chỉ trừ một lần. Dùng idempotency key, tra trạng thái request/reconcile và retry theo giao thức an toàn.

### Bài tập 13 — Version conflict của form

Hai người cùng sửa hồ sơ. A đổi tên và commit v8; B sửa ngôn ngữ dựa trên v7 nên bị conflict.

**Câu hỏi:** Có nên tăng `expectedVersion=8` rồi gửi nguyên snapshot v7 của B?

**Gợi ý:** Không, có thể ghi đè tên mới của A. Cần đọc v8 và merge đúng field B chỉnh hoặc hỏi người dùng.

### Bài tập 14 — Quota nhiều shard

Quota tenant là 100. `used` bị chia thành 4 shard, mỗi shard tự kiểm tra `usedShard < 100`.

**Câu hỏi:** Điều kiện này có giữ tổng usage dưới 100 không?

**Gợi ý:** Không. Cần allocation hoặc một authority bảo vệ quota tổng, hoặc transaction phù hợp.

### Bài tập 15 — Multi-region username

Hai region độc lập cùng có quyền ghi username. Cả hai conditional create một key khi chưa thấy replication của nhau.

**Câu hỏi:** Điều gì có thể xảy ra?

**Gợi ý:** Có thể hai lần xác nhận cục bộ rồi conflict resolution. Để đảm bảo uniqueness toàn cục, cần authority/consistency hoặc cơ chế được sản phẩm xác nhận.

### Bài tập 16 — Lock hết hạn

Worker A lấy lock 30 giây rồi pause 60 giây; B lấy lock mới. A chạy lại và ghi file.

**Câu hỏi:** Chỉ release-if-owner có chặn A ghi file không?

**Gợi ý:** Không. Nếu file/resource hỗ trợ kiểm tra, cần fencing token hoặc xác nhận quyền sở hữu mới nhất tại nơi ghi.

### Bài tập 17 — Kiểm thử concurrent reservation

Tồn kho chỉ còn 1. Có 100 request đồng thời, mỗi request có idempotency key riêng.

**Câu hỏi:** Những invariant nào cần assert?

**Gợi ý:** Chỉ 1 reservation nghiệp vụ thành công, tồn kho không âm, không trùng idempotency, không side effect từ request bị từ chối và hệ không mất trạng thái khi retry.

### Bài tập 18 — Chọn phạm vi nguyên tử

Ba thiết kế:

1. Một document order chứa `status` và `version`.
2. Hai item `accountA` và `accountB` cần chuyển tiền.
3. Một key Redis lưu counter cache không quan trọng.

**Câu hỏi:** Cơ chế nào phù hợp cho từng trường hợp?

**Gợi ý:** (1) conditional document update/OCC; (2) transaction hoặc ledger/workflow bảo đảm toàn bộ invariant; (3) atomic `INCR` hoặc Lua nếu có điều kiện, không cần LWT đa hệ.

### Bài tập 19 — Xóa rồi tạo lại

Worker nhận `DELETE Product P100 version=12`; một event cũ `UPSERT P100 version=10` đến sau, trong khi record đã bị xóa khỏi sink.

**Câu hỏi:** Làm sao chặn hồi sinh?

**Gợi ý:** Giữ tombstone/version marker hoặc identity generation, so version nguyên tử, thiết kế retention đủ dài cho replay.

### Bài tập 20 — So sánh lựa chọn vận hành

Một ứng dụng dùng Cassandra LWT trên cùng một partition cho 5.000 yêu cầu/giây, p99 tăng và conflict rất cao.

**Câu hỏi:** Có nên chỉ giảm timeout hoặc retry liên tục không?

**Gợi ý:** Không. Đánh giá hot partition, contention, single-writer queue, giảm số CAS, chia mô hình công việc và cân nhắc authority khác với invariant phù hợp.

## 33. Checklist trước khi đưa conditional write vào production

- [ ] Đã viết rõ bất biến cần bảo vệ bằng điều kiện có thể thực thi.
- [ ] Đã xác định authoritative record và phạm vi nguyên tử thực tế.
- [ ] Điều kiện được đánh giá **trong cùng thao tác** với mutation, không phải đọc trước rồi ghi vô điều kiện.
- [ ] Đã chọn CAS theo status/version/ETag/owner/absence phù hợp.
- [ ] Có quy tắc chống ABA, delete/recreate và stale worker nếu cần.
- [ ] Đã xem index/partition key, uniqueness và normalization.
- [ ] Đã xác định side effects ngoài phạm vi transaction.
- [ ] Có idempotency key nếu retry có thể nhân đôi nghiệp vụ.
- [ ] Phân biệt condition failed với timeout/unknown commit.
- [ ] Có retry giới hạn, backoff và phương án conflict cho người dùng.
- [ ] Đã xét multi-region/replication semantics.
- [ ] Đã kiểm thử nhiều writer cùng lúc và lỗi sau commit.
- [ ] Có metric applied/conflict/latency/hot key.
- [ ] Có kế hoạch phục hồi/reconciliation khi workflow nhiều bước thất bại.
- [ ] Không dùng CAS như lời bảo đảm chung cho transaction nhiều bản ghi.

## 34. Tổng kết

**Cập nhật có điều kiện** bảo vệ một nguyên tắc rất quan trọng: *chỉ ghi khi điều kiện về trạng thái hiện hành còn đúng*, và việc **so sánh với ghi phải nằm trong cùng ranh giới nguyên tử mà database cam kết**. Vì vậy, “đọc → kiểm tra trong code → ghi” không tương đương với CAS.

NoSQL cung cấp nhiều cơ chế thể hiện cùng ý tưởng ở phạm vi khác nhau: DynamoDB `ConditionExpression`, MongoDB filter trong atomic update một document, Cassandra LWT `IF`, Redis `SET NX`/Lua/`WATCH`, Cosmos DB ETag, Firestore transaction/preconditions, Couchbase CAS và các concurrency token của search engine. Cú pháp khác nhau, nhưng câu hỏi cần đặt ra luôn giống nhau: **điều kiện được bảo vệ trên key/document/partition nào, bởi authority nào, trong mô hình nhất quán nào?**

CAS đặc biệt hữu ích để chống **lost update, overselling, chuyển trạng thái sai và tạo trùng business key** khi bất biến nằm trong phạm vi phù hợp. Tuy nhiên, nó không tự bảo vệ invariant xuyên nhiều object, không biến side effect ngoài database thành giao dịch, không làm request timeout trở thành “chưa commit”, và không tự ngăn worker cũ ghi sau khi lease hết hạn.

Một thiết kế production cần kết hợp **version/generation, idempotency, error classification, retry có giới hạn, multi-item transaction hoặc workflow bù khi cần, và kiểm thử tranh chấp thật**. Khi bất biến vượt phạm vi một item, hãy thay đổi ranh giới aggregate hoặc chọn cơ chế giao dịch phù hợp, thay vì kỳ vọng nhiều CAS rời rạc sẽ tự hợp thành một transaction.

**Nguyên tắc cuối cùng:** điều kiện có giá trị bảo vệ chỉ khi nó được kiểm tra và ghi **nguyên tử tại nơi chịu trách nhiệm quyết định trạng thái**. Mọi bước ngoài ranh giới đó phải được thiết kế và phục hồi như một phần riêng của workflow.

