# Thao tác nguyên tử trên một khóa, tăng bộ đếm và cập nhật có điều kiện

Trong mô hình cơ sở dữ liệu **khóa–giá trị** (*key–value*), ứng dụng truy cập dữ liệu chủ yếu bằng một khóa để đọc, tạo, thay thế hoặc cập nhật giá trị đi kèm. Nhiều hệ NoSQL cung cấp các thao tác **nguyên tử** (*atomic operation*) trên một đơn vị dữ liệu như key, item hoặc document: tăng số đếm, chỉ tạo nếu chưa tồn tại, hoặc cập nhật nếu giá trị/phiên bản vẫn thỏa điều kiện. Các primitive này giải quyết một nhóm lỗi cạnh tranh mà cách **đọc → tính ở ứng dụng → ghi lại** thường gặp phải.

Nhưng “atomic trên một khóa” không có nghĩa toàn bộ quy trình nghiệp vụ nhiều khóa là transaction, cũng không tự bảo đảm mọi replica đọc được dữ liệu mới tức thì hay ghi đã bền vững sau failover. Bài học này làm rõ ranh giới nguyên tử, các lệnh số học, **compare-and-set (CAS)**, cập nhật có điều kiện, cách chống ghi trùng khi retry và những đánh đổi về hiệu năng, nhất quán trong các hệ NoSQL.

## 1. Vì sao một lần đọc rồi ghi lại có thể sai?

Giả sử key **views:article:42** đang lưu số lượt xem là 100. Hai người xem bài gần như đồng thời, và mỗi request sử dụng logic:

~~~text
value = GET(key)
SET(key, value + 1)
~~~

Một lịch thực thi hợp lệ:

~~~text
Giá trị ban đầu: 100

Client A: GET -> 100
Client B: GET -> 100
Client A: tính 100 + 1; SET 101
Client B: tính 100 + 1; SET 101

Kết quả thực tế: 101
Kết quả mong muốn: 102
~~~

Đây là lỗi **lost update**: lần ghi của B đã ghi đè hiệu quả của A. Lệnh GET và lệnh SET có thể được thực thi nguyên tử *riêng từng lệnh*, nhưng chuỗi GET → phép tính → SET chưa phải một đơn vị nguyên tử.

Nếu database hỗ trợ thao tác **INCREMENT(key, 1)** nguyên tử:

~~~text
Giá trị ban đầu: 100

Client A: INCREMENT(key, 1) -> 101
Client B: INCREMENT(key, 1) -> 102

Kết quả: 102
~~~

Với primitive phù hợp, server tự đọc giá trị hiện hành và áp dụng thay đổi dưới bảo đảm atomic của nó. Client không cần tự dựng chuỗi đọc/ghi có thể bị chen ngang.

### Atomicity thực sự bảo đảm điều gì?

| Đặc tính | Câu hỏi phải trả lời | Không được suy diễn |
| --- | --- | --- |
| **Atomicity** | Thao tác nào trên đơn vị dữ liệu nào được xem như một lần thay đổi không bị chia nhỏ? | Một lệnh atomic sẽ bảo vệ toàn bộ quy trình gồm nhiều lệnh. |
| **Isolation** | Hai giao dịch đồng thời có thể quan sát, gây xung đột hoặc sắp xếp với nhau ra sao? | Có atomic update tức là mọi transaction đều serializable. |
| **Read consistency** | Lần đọc kế tiếp qua primary/replica/index có thể thấy phiên bản nào? | Ghi thành công nghĩa là mọi replica thấy ngay giá trị mới. |
| **Durability** | Khi được xác nhận, dữ liệu đã ở đâu và có thể tồn tại qua loại sự cố nào? | Thao tác trên primary hoàn tất nghĩa là không bao giờ mất dữ liệu. |
| **Idempotency** | Một ý định nghiệp vụ được gửi lại có tạo tác dụng phụ lần nữa không? | Lệnh atomic được retry sẽ có đúng một tác động. |

Trong Redis, đơn vị thao tác thường là key/cấu trúc dữ liệu trên primary. Trong DynamoDB, thao tác cập nhật một **item** được xác định bởi primary key. MongoDB cho atomic update trên một **document**. Cassandra có cơ chế counter và lightweight transaction riêng. Vì vậy, trước khi dùng từ “một khóa” trong thiết kế, cần xác định **đơn vị nguyên tử chính xác theo sản phẩm và API**.

## 2. Nhóm thao tác nguyên tử thông dụng

| Primitive | Ý nghĩa | Tình huống sử dụng |
| --- | --- | --- |
| **Atomic SET** | Ghi/ghi đè giá trị trong một lệnh. | Lưu trạng thái, thay giá trị. |
| **Create-if-absent** | Chỉ tạo nếu key/item chưa tồn tại. | Chống trùng username, claim một tài nguyên. |
| **Update-if-present** | Chỉ cập nhật khi key/item đã có. | Không tự tạo dữ liệu vắng mặt. |
| **Increment/Decrement** | Tăng/giảm số hiện có ngay trong database. | Counter, lượt xem, số thứ tự. |
| **Compare-and-set (CAS)** | So sánh giá trị hoặc version kỳ vọng trước khi ghi. | Optimistic locking, tránh ghi đè thay đổi. |
| **Conditional update** | Kiểm tra điều kiện trên giá trị hiện tại rồi cập nhật cùng một thao tác nguyên tử. | Trừ tồn kho nếu đủ, chuyển trạng thái có điều kiện. |
| **Script/transaction có phạm vi xác định** | Ghép nhiều phép đọc/ghi trong khả năng atomic của hệ. | Ràng buộc phức tạp hơn một phép toán. |

Điểm chung của các primitive là **database kiểm tra điều kiện ở đúng thời điểm thay đổi**. Không được thay conditional update bằng một lần đọc điều kiện ở client rồi gửi một lệnh ghi vô điều kiện.

## 3. Tăng bộ đếm: đơn giản nhưng có nhiều loại yêu cầu

### 3.1. Redis INCR, DECR, INCRBY

Redis cung cấp các lệnh số học trên giá trị số nguyên của key:

~~~redis
SET page:42:views 100
INCR page:42:views
# 101

INCRBY page:42:views 5
# 106

DECR page:42:views
# 105

GET page:42:views
# "105"
~~~

Mỗi lệnh tăng/giảm được thực thi nguyên tử theo ngữ nghĩa của lệnh trên Redis primary. Với INCR, key chưa tồn tại được xử lý như giá trị ban đầu 0. Nếu nội dung hiện tại không phải số nguyên hợp lệ, lệnh trả lỗi; không tự sửa một giá trị tùy ý thành số.

Trong Spring Data Redis, mã Java có thể ngắn gọn:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;

public final class ArticleViewCounter {
    private final StringRedisTemplate redis;

    public ArticleViewCounter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long recordView(String articleId) {
        String key = "page:" + articleId + ":views";
        Long updated = redis.opsForValue().increment(key);
        if (updated == null) {
            throw new IllegalStateException("No value returned by Redis");
        }
        return updated;
    }
}
~~~

Ở đây **increment** giải quyết lost update khi nhiều client cùng tăng counter. Nó chưa giải quyết chuyện người dùng bấm refresh nhiều lần, message đến trùng, client retry hoặc Redis failover. Những yêu cầu ấy cần hợp đồng riêng.

### 3.2. Bộ đếm “chính xác” có nhiều cách hiểu

| Loại counter | Ví dụ | Điều cần quyết định |
| --- | --- | --- |
| Hiển thị số liệu | Lượt xem bài, số lần tải trang | Chấp nhận sai số nhỏ hoặc độ trễ hội tụ không? |
| Thống kê theo thời gian | Số request từng phút | Khóa hết hạn/reset thế nào, burst tại ranh giới được tính ra sao? |
| Theo dõi trạng thái | Số người online | Khi client mất kết nối, ai giảm counter và khi nào? |
| Giới hạn nghiệp vụ | Số suất còn lại, số lượt dùng quota | Có cần chặn xuống âm, xử lý request trùng và tranh chấp không? |
| Đánh số | Cấp số thứ tự từ một sequence | Có cho phép lỗ hổng số, reset hoặc số đã cấp nhưng chưa dùng không? |
| Thanh toán/ledger | Tổng tiền đã thu | Cần idempotency, audit, durability và ràng buộc mạnh hơn một increment. |

Nếu một client tăng thành công hai lần, counter có thể đúng theo số **lệnh thực thi** nhưng sai theo số **sự kiện nghiệp vụ duy nhất**. Phải nêu rõ “đếm cái gì”, không chỉ chọn lệnh INCR.

### 3.3. Một counter atomic khác với nhiều counter atomic

Giả sử xử lý một đơn hàng phải tăng cả **orders:total** và **orders:day:2026-11-14**:

~~~text
INCR orders:total                  -> thành công
[Ứng dụng mất kết nối]
INCR orders:day:2026-11-14         -> chưa thực thi
~~~

Hai lệnh tăng riêng có thể đều atomic, nhưng **không bảo đảm cả hai cùng commit**. Nếu bắt buộc giữ bất biến giữa hai counter, cần transaction/script trong phạm vi hệ hỗ trợ, hoặc lưu sự kiện chuẩn rồi tổng hợp có đối soát. Nếu chỉ phục vụ dashboard, việc chậm hội tụ có thể được chấp nhận với điều kiện có cách tái dựng số liệu.

## 4. Cập nhật có điều kiện để không bán vượt tồn

Giả sử SKU chỉ còn 1 sản phẩm. Hai client cùng thực hiện:

~~~text
stock = GET(stock:sku-7)
if stock >= 1:
    DECR(stock:sku-7)
~~~

Cả hai có thể cùng đọc 1 rồi cùng giảm, tạo giá trị -1. Ngay cả khi DECR riêng lẻ atomic, điều kiện **stock ≥ 1** đang ở bên ngoài database.

Thiết kế cần một thao tác logic:

~~~text
CONDITIONAL_DECREMENT(key, amount):
    nguyên tử kiểm tra current >= amount
    nếu thỏa: ghi current - amount; trả SUCCESS
    nếu không: giữ nguyên; trả INSUFFICIENT_STOCK
~~~

Điều kiện và cập nhật phải được đánh giá **cùng một ranh giới nguyên tử**. Có thể thực hiện bằng **conditional update** của database hoặc script/transaction với ngữ nghĩa tương đương.

### 4.1. Redis Lua: kiểm tra và trừ cùng một lần thực thi

~~~lua
-- KEYS[1]: key tồn kho
-- ARGV[1]: số lượng muốn giữ
local raw = redis.call('GET', KEYS[1])
if not raw then
    return -2 -- không có key
end

local stock = tonumber(raw)
local quantity = tonumber(ARGV[1])

if not stock or not quantity
   or quantity < 1
   or quantity ~= math.floor(quantity) then
    return -3 -- dữ liệu không hợp lệ
end

if stock < quantity then
    return -1 -- không đủ tồn
end

return redis.call('DECRBY', KEYS[1], quantity)
~~~

Redis thực thi script theo cơ chế không cho các lệnh khác chen vào giữa các thao tác của script trên server, giúp loại race **GET → kiểm tra → DECR**. Các mã kết quả trong ví dụ:

| Giá trị trả về | Ý nghĩa |
| --- | --- |
| Số không âm | Trừ thành công; giá trị còn lại. |
| **-1** | Thiếu tồn kho. |
| **-2** | Không có key. |
| **-3** | Giá trị hiện có/đầu vào không hợp lệ. |

Ví dụ giả định dữ liệu tồn kho là số nguyên không âm nằm trong miền hỗ trợ và ứng dụng chặn số lượng quá lớn/không hợp lệ. Trong sản phẩm thực phải kiểm soát giá trị số, độ lớn phép toán và chính sách retry; script có thể gây lỗi khi dữ liệu vượt giới hạn hoặc có client khác ghi sai định dạng. Redis Lua có tính nguyên tử về việc **không bị xen lệnh**, nhưng **không có rollback tổng quát** cho những ghi đã xảy ra trước một lỗi runtime trong script.

Ví dụ chỉ sửa **một key**. Nếu script dùng nhiều key trong Redis Cluster, các key phải thỏa yêu cầu định tuyến cùng hash slot theo quy tắc của hệ.

### 4.2. DynamoDB: điều kiện gắn trực tiếp vào UpdateItem

DynamoDB hỗ trợ **ConditionExpression** và **UpdateExpression** trong một **UpdateItem**. Với bảng chỉ có partition key **pk** và item:

~~~json
{
  "pk": "SKU#sku-7",
  "available": 1
}
~~~

Có thể gửi request tương đương:

~~~text
Key:
    pk = "SKU#sku-7"

UpdateExpression:
    SET #stock = #stock - :qty

ConditionExpression:
    attribute_exists(pk) AND #stock >= :qty

ExpressionAttributeNames:
    #stock = "available"

ExpressionAttributeValues:
    :qty = 1
~~~

DynamoDB kiểm tra điều kiện trên item và thực hiện cập nhật atomic nếu điều kiện đúng. Khi hai request cùng tranh một sản phẩm và cùng yêu cầu **available ≥ 1**, tối đa một request sẽ cập nhật thành công trong tình huống này. Request còn lại nhận lỗi không thỏa điều kiện theo API, thay vì tự động trừ xuống -1.

Ví dụ Java dùng AWS SDK for Java v2 với kiểu giá trị low-level **AttributeValue**:

~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.ConditionalCheckFailedException;
import software.amazon.awssdk.services.dynamodb.model.ReturnValue;
import software.amazon.awssdk.services.dynamodb.model.UpdateItemRequest;
import software.amazon.awssdk.services.dynamodb.model.UpdateItemResponse;

public final class DynamoStock {
    private final DynamoDbClient client;
    private final String tableName;

    public DynamoStock(DynamoDbClient client, String tableName) {
        this.client = client;
        this.tableName = tableName;
    }

    public long reserve(String sku, long quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        UpdateItemRequest request = UpdateItemRequest.builder()
            .tableName(tableName)
            .key(Map.of(
                "pk", AttributeValue.builder().s("SKU#" + sku).build()
            ))
            .updateExpression("SET #stock = #stock - :qty")
            .conditionExpression(
                "attribute_exists(pk) AND #stock >= :qty"
            )
            .expressionAttributeNames(Map.of(
                "#stock", "available"
            ))
            .expressionAttributeValues(Map.of(
                ":qty", AttributeValue.builder()
                    .n(Long.toString(quantity)).build()
            ))
            .returnValues(ReturnValue.ALL_NEW)
            .build();

        try {
            UpdateItemResponse response = client.updateItem(request);
            return Long.parseLong(
                response.attributes().get("available").n()
            );
        } catch (ConditionalCheckFailedException ex) {
            throw new IllegalStateException(
                "SKU not found or insufficient stock", ex
            );
        }
    }
}
~~~

Mẫu này giả định bảng chỉ có **pk**. Nếu schema có sort key, request phải truyền đủ khóa chính; nếu tên thuộc tính, kiểu số hoặc trạng thái ban đầu khác thì điều kiện phải điều chỉnh tương ứng. Trường hợp không đủ hàng và không có item đều dẫn tới conditional failure trong ví dụ; ứng dụng có thể đọc bổ sung để phân loại, nhưng lần đọc đó không thay thế phép kiểm tra điều kiện atomic.

**Lưu ý quan trọng:** lệnh này chỉ trừ tồn kho trong một item. Nó chưa tạo đơn hàng ở item khác cùng transaction, chưa có idempotency theo **orderId**, và timeout vẫn có thể khiến client không biết phép trừ đã được thực hiện chưa.

## 5. Compare-and-set (CAS) và optimistic locking

**Compare-and-set** diễn đạt một cập nhật chỉ được chấp nhận nếu trạng thái chưa bị thay đổi kể từ khi client quan sát nó:

~~~text
CAS(key, expectedValue, newValue):
    nếu currentValue == expectedValue:
        ghi newValue và trả SUCCESS
    ngược lại:
        không ghi và trả CONFLICT
~~~

Nhiều hệ triển khai ý tưởng này bằng **version**, **ETag**, điều kiện so sánh field hoặc token do server cấp. Dùng CAS phù hợp khi cập nhật phụ thuộc vào dữ liệu đã đọc, nhưng không muốn khóa bi quan mọi thao tác.

### 5.1. Ví dụ: hai tab cùng sửa hồ sơ

~~~json
{
  "pk": "USER#42",
  "displayName": "An",
  "city": "Hà Nội",
  "version": 7
}
~~~

Tab A và B cùng đọc version 7. A đổi tên, B đổi thành phố. Nếu mỗi tab ghi lại toàn bộ item vô điều kiện, B có thể vô tình đưa tên cũ trở lại.

Dùng version trong điều kiện cập nhật:

~~~text
SET displayName = "Bình",
    version = version + 1
WHERE pk = "USER#42" AND version = 7
~~~

Trong DynamoDB có thể diễn đạt bằng:

~~~text
UpdateExpression:
    SET #name = :newName, #version = #version + :one

ConditionExpression:
    attribute_exists(pk) AND #version = :expected

Giá trị:
    :newName = "Bình"
    :one = 1
    :expected = 7
~~~

Lần ghi thành công nâng version lên 8. Client còn kỳ vọng version 7 sẽ nhận **conflict**. Ứng dụng có thể hiển thị xung đột cho người dùng, hoặc đọc lại trạng thái mới và merge theo **field có chủ ý sửa** nếu nghiệp vụ cho phép. Không nên âm thầm đọc lại và ghi đè toàn bộ item, vì điều đó có thể gây lost update ở vòng retry.

### 5.2. ABA problem

Một CAS chỉ so sánh payload hiện tại có thể bỏ sót chuỗi:

~~~text
A -> B -> A
~~~

Client thứ nhất đọc **A**. Client khác sửa **A → B → A**. Khi client thứ nhất so sánh với **A**, nó không thấy đã có hai thay đổi xen giữa. Đây là vấn đề **ABA**.

Thêm version tăng theo mỗi thay đổi:

~~~text
(A, version 10) -> (B, version 11) -> (A, version 12)
~~~

Client vẫn giữ **expectedVersion = 10** sẽ nhận conflict dù giá trị trở lại A. Version cần được quản lý sao cho không tự quay vòng hoặc tái sử dụng trong phạm vi cần bảo vệ.

### 5.3. Redis WATCH và MULTI/EXEC

Khi client cần đọc, tính toán rồi ghi, Redis hỗ trợ optimistic locking bằng **WATCH**:

~~~text
Client A: WATCH stock:sku-7
Client A: GET stock:sku-7       -> 2
Client A: tính newStock = 1
Client A: MULTI
Client A: SET stock:sku-7 1
Client A: EXEC
~~~

Nếu key bị sửa giữa WATCH và EXEC, EXEC hủy nhóm lệnh đang chờ thực thi theo cơ chế WATCH; client có thể đọc lại và retry có giới hạn. Lưu ý WATCH gắn với connection và transaction lifecycle; phải thực hiện đúng qua driver, nhất là khi dùng connection pool. TTL/expire, Redis Cluster và phiên bản Redis cũng ảnh hưởng hành vi cần xác minh.

**MULTI/EXEC** thực thi các lệnh theo thứ tự trên server nhưng không cung cấp rollback tất cả thay đổi đã thực thi nếu một lệnh gặp lỗi runtime. Do đó không nên đồng nhất nó với transaction ACID đa bản ghi của hệ quan hệ.

## 6. Chỉ tạo nếu chưa có: giải quyết tranh chấp đăng ký

Một ví dụ sai:

~~~text
if GET username:mai == null:
    SET username:mai user-101
~~~

Hai request có thể cùng thấy chưa tồn tại rồi cùng SET. Khi đó người đến sau ghi đè kết quả người trước.

Thay bằng **create-if-absent** nguyên tử:

~~~redis
SET username:mai "user-101" NX
# OK khi key chưa có; không ghi nếu key đã tồn tại

SET claim:worker:abc "worker-7" NX EX 60
# Claim key nếu chưa tồn tại, đồng thời đặt TTL 60 giây
~~~

DynamoDB có thể dùng **PutItem** với **ConditionExpression = attribute_not_exists(pk)** để chỉ tạo item khi khóa chưa có; MongoDB có thể dựa trên unique index và thao tác insert/upsert phù hợp, xử lý duplicate-key khi có tranh chấp.

Một **SET NX EX** thường được dùng để lấy lease/lock tạm. Nhưng lease có TTL không bảo vệ tuyệt đối mọi thao tác bên ngoài Redis: nếu một worker bị pause lâu, lease hết hạn, worker khác lấy lease, worker cũ có thể thức dậy và tiếp tục ghi xuống hệ khác. Với tài nguyên quan trọng, cần kiểm tra token/phiên bản ở nơi cập nhật, sử dụng **fencing token** hoặc một giao thức bảo vệ được chứng minh theo ranh giới thực tế.

## 7. Retry: nguyên tử không đồng nghĩa idempotent

Một client tăng counter và bị timeout:

~~~text
Client                  Database
   |  INCR views         |
   |-------------------->|
   |             5 -> 6  |
   |     phản hồi bị mất X
   |<--------------------X
   | timeout             |
   |  INCR views lần nữa |
   |-------------------->|
   |             6 -> 7  |
~~~

Cả hai lệnh đều atomic, nhưng **một ý định nghiệp vụ** đã tăng hai lần. Timeout không chứng minh lệnh đầu thất bại; có thể database đã commit nhưng client không nhận ACK.

| Tính chất | Nghĩa trong ví dụ |
| --- | --- |
| **Atomic** | Mỗi INCR không bị xen bởi lệnh khác trong phạm vi primitive. |
| **Idempotent** | Gọi lại cùng ý định không làm thay đổi kết quả thêm lần nữa. INCR **không** có tính chất này. |
| **At-most-once effect** | Một operationId có tối đa một tác động nghiệp vụ. Cần cơ chế lưu nhận dạng và kiểm tra trùng an toàn. |
| **At-least-once delivery** | Message/request có thể đến nhiều lần, consumer cần tránh tác động lặp khi cần. |

### 7.1. Idempotency key cho yêu cầu giữ hàng

~~~text
POST /reservations
Idempotency-Key: order-937

Lần đầu:
  nếu order-937 chưa xử lý:
    kiểm tra và trừ tồn kho
    tạo/lưu reservation của order-937
    ghi nhận kết quả
  trả reservationId

Lần sau với cùng order-937:
  trả lại kết quả đã ghi nhận
  không trừ thêm tồn kho
~~~

Điều kiện “operationId đã xử lý hay chưa” và hiệu ứng giữ hàng cần nằm trong **cùng ranh giới nguyên tử** hoặc dùng một giao thức giao dịch/đối soát đủ an toàn. Đoạn logic sau **chưa an toàn** nếu mỗi dòng là một thao tác riêng:

~~~text
IF NOT EXISTS processed:order-937:
    DECR stock:sku-7
    SET processed:order-937 true
~~~

Hai request có thể cùng vượt qua kiểm tra, hoặc tiến trình sập giữa DECR và SET rồi retry trừ thêm lần nữa. Nếu cần ghi nhiều key/item, phải xem có transaction đa item/document phù hợp, hoặc thiết kế ledger, reservation state và cơ chế khôi phục. Idempotency token cũng cần vòng đời lưu giữ phù hợp; token hết hạn trước khi request cũ được gửi lại sẽ tạo cửa sổ đếm trùng.

### 7.2. Xử lý kết quả không rõ ràng

Đối với cập nhật có điều kiện, hãy phân biệt:

- **Condition failed:** server xác định điều kiện không thỏa; thường là xung đột hoặc từ chối hợp lệ, không retry vô hạn.
- **Timeout/connection lost:** kết quả chưa biết. Cần tra cứu qua operationId hoặc cơ chế idempotency trước khi gửi lại thay đổi không idempotent.
- **Lỗi trước khi gửi request:** có thể retry với backoff/jitter và số lần giới hạn nếu operation cho phép.
- **Conflict trong CAS:** đọc lại trạng thái rồi retry có kiểm soát, hoặc trả conflict để người dùng quyết định. Đừng retry lập tức vô hạn trên key nóng.

Nếu vòng CAS retry có gọi API ngoài như thanh toán hoặc gửi email, side effect có thể thực hiện nhiều lần. Cần tách side effect ra khỏi vòng retry hoặc bảo vệ nó bằng idempotency và luồng trạng thái riêng.

## 8. TTL và bộ đếm theo cửa sổ thời gian

Một cách đếm request theo phút:

~~~text
INCR rate:user-42
if count == 1:
    EXPIRE rate:user-42 60
~~~

Nếu ứng dụng chết giữa INCR và EXPIRE, key có thể **không có TTL**, tiếp tục tồn tại qua nhiều cửa sổ. Việc kiểm tra và đặt TTL bị chia thành hai lượt gọi nên không có bảo đảm atomic cho cả quy trình.

Dùng script trên Redis để gộp:

~~~lua
-- KEYS[1]: counter của cửa sổ
-- ARGV[1]: TTL tính bằng giây
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
return count
~~~

Điều này giải quyết khoảng trống client chết giữa INCR và EXPIRE đối với key do script quản lý. Nhưng nếu key đã tồn tại với giá trị lớn hơn 1 mà **không có TTL** do dữ liệu cũ hoặc công cụ khác tạo, script sẽ không tự chữa. Một hệ production có thể kiểm tra TTL và xử lý key lỗi theo policy đã định.

Nếu giới hạn tốc độ cần quyết định **cho phép/từ chối trước khi tăng**, gộp kiểm tra và tăng trong một thao tác:

~~~lua
-- KEYS[1]: bucket của user trong một fixed window
-- ARGV[1]: giới hạn; ARGV[2]: TTL cửa sổ (giây)
local limit = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
if not limit or not ttl or limit < 1 or ttl < 1 then
    return redis.error_reply('invalid config')
end

local count = tonumber(redis.call('GET', KEYS[1]) or '0')
if not count then
    return redis.error_reply('counter not numeric')
end
if count >= limit then
    return 0 -- từ chối, không tăng
end

if count == 0 then
    redis.call('SET', KEYS[1], 1, 'EX', ttl)
else
    redis.call('INCR', KEYS[1])
end
return 1 -- chấp nhận
~~~

Đây là một biến thể **fixed-window limiter** trên một key, giả định không có tác nhân khác sửa key. Nó có thể cho burst tại ranh giới cửa sổ: request cuối của phút trước và đầu phút sau có thể đến sát nhau. Sliding window/token bucket có thuật toán và yêu cầu khác. Nếu dùng Redis làm bộ giới hạn quan trọng, cần xác định thêm ảnh hưởng của replica, failover, mất kết nối và độ trễ expiration.

## 9. So sánh các hệ NoSQL và phạm vi thao tác

| Hệ | Primitive thường dùng | Ranh giới và lưu ý |
| --- | --- | --- |
| **Redis** | INCR, DECR, SET NX/XX, HINCRBY, WATCH/MULTI/EXEC, Lua | Thực thi lệnh/script trên server theo bảo đảm của Redis; replica thường đồng bộ bất đồng bộ; cluster có quy tắc hash slot cho multi-key. |
| **DynamoDB** | UpdateItem với SET/ADD và ConditionExpression; PutItem điều kiện; transaction API riêng | Cập nhật và điều kiện trên cùng item là atomic; item được định danh bằng đủ primary key. Strong/eventual read và GSI là vấn đề khác. |
| **MongoDB** | $inc, $set, findOneAndUpdate, filter theo _id/version | Một document được cập nhật atomic; thao tác trên nhiều document cần xem transaction và write concern phù hợp. |
| **Cassandra** | Counter columns, UPDATE … IF dùng LWT | Counter và LWT có ngữ nghĩa khác nhau; LWT có chi phí phối hợp và phạm vi partition cụ thể. |
| **Couchbase** | Counter operation, CAS token của document | CAS ngăn ghi dựa trên phiên bản cũ; durability và việc đọc qua replica cần cấu hình/kiểm chứng riêng. |

### 9.1. MongoDB: $inc và điều kiện trong một document

~~~javascript
// Tăng lượt xem trên một document.
db.pageViews.updateOne(
  { _id: "article-42" },
  { $inc: { views: 1 } },
  { upsert: true }
);

// Giữ hai sản phẩm nếu còn đủ trong cùng document.
const result = db.inventory.updateOne(
  { _id: "sku-7", available: { $gte: 2 } },
  { $inc: { available: -2 } }
);

if (result.modifiedCount !== 1) {
  // Không thỏa điều kiện hoặc không tồn tại SKU.
}
~~~

MongoDB kiểm tra filter cập nhật và áp dụng phép tăng/trừ trên document một cách atomic theo ngữ nghĩa ghi đơn document. Nếu hai client tranh sản phẩm cuối trên **cùng document**, không thể cả hai cùng thành công khi mỗi update yêu cầu available ≥ 1. Nhưng nếu còn phải tạo order trên document khác, **updateOne** chưa phải transaction đa document.

### 9.2. Cassandra: counter không giống LWT

Cassandra có kiểu **counter** với cách cập nhật riêng:

~~~sql
UPDATE article_views
SET views = views + 1
WHERE article_id = 42;
~~~

Lệnh trên giả định schema hợp lệ đã định nghĩa views là counter. Counter có ràng buộc dữ liệu và ngữ nghĩa retry cần nghiên cứu theo phiên bản Cassandra. Nếu lần cập nhật được thực thi nhưng ACK bị mất, gửi lại có thể tăng thêm; không nên coi counter này là ledger thanh toán duy nhất.

Với điều kiện theo trạng thái, **Lightweight Transaction (LWT)** dùng cơ chế đồng thuận và có thể diễn đạt:

~~~sql
UPDATE orders
SET status = 'RESERVED'
WHERE order_id = 937
IF status = 'PENDING';
~~~

Ứng dụng phải xem kết quả **applied** có thành công không, rồi xử lý xung đột. LWT có chi phí khác ghi thường và không biến mọi batch/cập nhật xuyên nhiều partition thành một transaction ACID tùy ý.

## 10. Hot key và sharded counter

Một counter được mọi request cập nhật là **hot key**:

~~~text
pageviews:total  <-  mọi INCR tập trung vào một điểm
~~~

Dù tổng số key trong database rất lớn, chỉ một key nhận phần lớn traffic có thể làm node/shard chứa key đó bị nghẽn. Biểu hiện là latency p99 tăng, queue tăng, CPU của một node cao trong khi phần khác của cụm còn rảnh.

Một chiến lược cho chỉ số thống kê có thể chấp nhận hội tụ là **sharded counter**:

~~~text
pageviews:42:shard:0 = 100
pageviews:42:shard:1 = 96
pageviews:42:shard:2 = 121
pageviews:42:shard:3 = 83

Tổng đọc được bằng SUM = 400
~~~

Phân phối increment theo shard làm giảm tranh chấp tập trung, nhưng đổi lấy:

- Phải đọc/tổng hợp nhiều key để lấy tổng; không tự có snapshot nhất quán cùng thời điểm.
- Tổng có thể chậm hội tụ nếu giữ bản tổng định kỳ.
- Khi thay đổi số shard, retry, khôi phục hoặc phát sinh sự kiện trùng, cần quy tắc đếm rõ ràng.
- **Không phù hợp nếu phải chặn quota/tồn kho toàn cục một cách chính xác** mà không có cơ chế phối hợp bổ sung, vì mỗi shard chỉ biết tổng cục bộ.

Có thể lựa chọn buffer/batch, queue, aggregate theo thời gian hoặc kiến trúc phân tán khác tùy yêu cầu. Nguyên tắc là phải phân biệt **counter thống kê** và **counter thực thi bất biến nghiệp vụ**.

## 11. Một khóa atomic không tạo ra transaction xuyên khóa

Giả sử:

~~~text
account:A.balance = 100
account:B.balance = 0
~~~

Chuyển 30 từ A sang B bằng hai lệnh:

~~~text
DECRBY account:A.balance 30
INCRBY account:B.balance 30
~~~

Từng lệnh có thể atomic, nhưng khi tiến trình chết sau lệnh đầu thì tổng số dư thiếu 30. Gửi lại cả chuỗi có thể làm trừ hai lần. Với dữ liệu nằm ở các shard/dịch vụ khác nhau, không thể suy ra một script hay transaction trên một primary sẽ bao phủ tất cả.

Chuyển tiền cần **ledger**, idempotency, transaction hoặc giao thức chuyển trạng thái có thể khôi phục và đối soát. Tương tự, một lệnh trừ **stock:sku-7** không bảo đảm key **order:937** đã tạo thành công. Nếu bất biến nằm trên hai item, hãy xác định transaction đa item/document có được hỗ trợ không; nếu không, dùng thiết kế reservation/state machine/saga với hành động bù trừ phù hợp.

## 12. Replica, xác nhận ghi và failover

Một phép INCR atomic trên primary có thể được phản hồi thành công trong khi replica vẫn chưa nhận bản mới:

~~~text
T0  INCR trên primary được thực thi.
T1  Client nhận ACK theo chính sách write acknowledgement.
T2  Client khác đọc replica chưa bắt kịp -> thấy giá trị cũ.
T3  Replica nhận cập nhật -> giá trị đọc có thể mới hơn.
~~~

Nếu primary hỏng gần T1–T2, khả năng mất dữ liệu đã được xác nhận phụ thuộc cấu hình persistence, replication, failover và chính sách ACK. Không thể kết luận độ bền chỉ từ tính nguyên tử của lệnh.

Khi đưa primitive vào ứng dụng, phải làm rõ:

- **Đường đọc:** đọc primary hay replica, có cần read-your-writes/strong read không?
- **Điều kiện xác nhận:** ACK có nghĩa lệnh đã chạy, đã vào journal hay đã được số replica cần thiết xác nhận?
- **Phạm vi key:** Một key, một item, một document, một partition hay nhiều shard?
- **Timeout:** Làm sao tìm được kết quả thực khi client không nhận phản hồi?
- **Failover:** Sau chuyển leader, counter, version và idempotency record có còn nhất quán không?
- **TTL:** Khi key tự hết hạn rồi được tạo lại, liệu phiên bản/khóa định danh có tái sử dụng gây sai nghiệp vụ?

Các câu hỏi này thuộc hợp đồng của hệ cụ thể, không được trả lời chỉ bằng nhãn “key–value”.

## 13. Kịch bản xác minh trước khi đưa vào vận hành

### 13.1. Counter không mất cập nhật

Khởi tạo counter 0, phát đồng thời nhiều request INCR, chờ các request có kết quả xác định, rồi đọc lại với mức nhất quán phù hợp. Nếu **10.000** increment thật sự thành công đúng một lần, kỳ vọng counter 10.000. Với request timeout chưa rõ kết quả, phải phân loại và đối soát riêng trước khi suy ra chính xác số lần thực thi.

### 13.2. Cạnh tranh giữ sản phẩm cuối

Khởi tạo available = 1, cho **200** client cùng reserve 1. Kỳ vọng có tối đa một reservation thành công và tồn kho không âm. Đối soát dữ liệu sau cùng, đừng chỉ kiểm tra HTTP status.

### 13.3. CAS tránh ghi đè

Hai client cùng đọc version 7 rồi cập nhật khác nhau. Một cập nhật thành công, cập nhật còn lại nhận conflict hoặc retry có kiểm soát. Không có bản cập nhật nào bị ghi đè âm thầm.

### 13.4. Timeout và request trùng

Cho server thực hiện thay đổi nhưng làm mất phản hồi. Client retry với cùng operationId. Với số dư/tồn kho, kỳ vọng chỉ một tác động nghiệp vụ. Nếu increment không được bảo vệ bằng idempotency, phép thử phải nhận diện nguy cơ đếm thêm lần nữa.

### 13.5. TTL và key tái tạo

Tạo key mới, xác minh TTL được thiết lập trong thao tác mong muốn; kiểm tra lúc hết hạn và lúc key được tạo lại. Thử cả trường hợp key tồn tại nhưng thiếu TTL để xác định cơ chế phát hiện và khôi phục.

### 13.6. Hot key và failover

Tăng riêng traffic vào một khóa, đo p95/p99, throughput, conflict, queue và tải node/shard. Tiêm lỗi primary hoặc mất kết nối trong phạm vi triển khai, sau đó đối soát những ghi đã được ACK theo chính sách durability chọn trước.

## 14. Bảng chọn giải pháp theo nhu cầu

| Nhu cầu | Primitive khởi đầu | Cần thêm |
| --- | --- | --- |
| Đếm lượt xem có thể sai số nhỏ | Atomic increment | Quy tắc retry, TTL, tổng hợp, hot key. |
| Đếm sự kiện tính phí đúng một lần | Increment gắn operationId/ledger idempotent | Audit, xử lý timeout và durability. |
| Đăng ký username duy nhất | Create-if-absent | Chuẩn hóa key, uniqueness và vòng đời tên. |
| Cập nhật hồ sơ tránh lost update | CAS/version | Xử lý conflict, merge field, ABA. |
| Không bán quá tồn | Conditional decrement | Idempotency, trạng thái order, quan hệ giữa nhiều item. |
| Rate limit theo thời gian | Atomic check-and-increment + TTL | Định nghĩa window, xử lý ranh giới, retry và failover. |
| Worker claim có thời hạn | Set-if-absent + TTL/token | Lease expiry và fencing ở tài nguyên được bảo vệ. |
| Tổng lượt xem rất lớn | Sharded/aggregated counter | Độ trễ hội tụ và cơ chế tái dựng. |
| Chuyển giá trị giữa hai key | Transaction/ledger hoặc giao thức bảo đảm phù hợp | Bất biến xuyên key, bù trừ, recovery và đối soát. |

## 15. Quy trình chọn primitive

~~~mermaid
flowchart TD
    A[Viết bất biến nghiệp vụ] --> B{Bất biến nằm trong một key/item?}
    B -->|Có| C{Chỉ cần tăng hoặc ghi đơn giản?}
    C -->|Có| D[Atomic increment / single-key write]
    C -->|Không| E[Conditional update / CAS / server-side script]
    B -->|Không| F[Transaction đa key hoặc ledger/state machine]
    D --> G[Idempotency và cách retry]
    E --> G
    F --> G
    G --> H[TTL, consistency, ACK và durability]
    H --> I[Thử cạnh tranh, timeout, hot key, failover]
~~~

Hợp đồng triển khai tối thiểu nên trả lời:

1. **Bất biến:** Đếm một lần theo lệnh hay theo sự kiện nghiệp vụ? Không âm hay chỉ là thống kê?
2. **Khóa:** Một hay nhiều key/item, các key có nằm cùng shard/partition theo yêu cầu API?
3. **Primitive:** Increment, create-if-absent, CAS, conditional update hay transaction/script?
4. **Conflict:** Điều kiện không thỏa trả kết quả gì và client xử lý như thế nào?
5. **Retry:** Lệnh có idempotent không, operationId được lưu trong phạm vi nào?
6. **TTL:** Key có hết hạn, reset hoặc được tạo lại không? Ai quản lý vòng đời?
7. **Replica/durability:** Chính sách đọc, ACK và failover nào thực sự đáp ứng yêu cầu?
8. **Hiệu năng:** Có hot key, retry storm, xung đột CAS hoặc chi phí đồng thuận cao không?
9. **Bằng chứng:** Đã đo tranh chấp, retry, timeout, đọc stale và khả năng đối soát chưa?

## Kết luận

**Atomic increment** tránh lost update khi nhiều client cùng tăng một giá trị; **conditional update** bảo vệ bất biến được kiểm tra trên cùng đơn vị atomic; **CAS/optimistic locking** ngăn ghi đè dựa vào phiên bản cũ. Đây là các primitive căn bản khi thiết kế dữ liệu khóa–giá trị.

Mỗi primitive có **phạm vi, điều kiện và giới hạn riêng**. Một lệnh atomic không tự trở thành transaction nhiều key; một lần ACK không tự bảo đảm mọi replica thấy dữ liệu mới; và một phép tăng nguyên tử có thể bị thực hiện thêm lần nữa khi request retry. Muốn đúng nghiệp vụ, cần ghép ranh giới khóa, điều kiện ghi, idempotency, TTL, mức nhất quán và cơ chế phục hồi thành một hợp đồng có thể kiểm chứng.
