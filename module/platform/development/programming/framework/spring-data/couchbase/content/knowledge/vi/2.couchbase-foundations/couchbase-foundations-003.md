# Khóa tài liệu, nội dung JSON và metadata trong Couchbase

> **Chương:** Nền tảng Couchbase  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase với document mapping, repository, `CouchbaseTemplate` và SQL++; làm nền cho thiết kế collection, chỉ mục, TTL, CAS, giao dịch, API reactive và vận hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **document ID (khóa tài liệu)**, phạm vi duy nhất của khóa và sự khác biệt giữa khóa với trường `id` trong JSON.
2. Thiết kế khóa ổn định cho thao tác key-value (KV), idempotency và dữ liệu nhiều tenant; tránh khóa dễ trùng hoặc tiết lộ dữ liệu nhạy cảm.
3. Biểu diễn dữ liệu JSON có object, array, kiểu nguyên thủy, trường tùy chọn và phiên bản schema; phân biệt `MISSING` với `NULL`.
4. Đọc và dùng **metadata** do Couchbase quản lý như ID, CAS, expiry; phân biệt chúng với trường nghiệp vụ và audit được lưu trong JSON.
5. Thực hành Java SDK, SQL++ và Spring Data Couchbase để đọc/ghi theo khóa, truy vấn trường JSON, kiểm soát cập nhật cạnh tranh và TTL.
6. Nhận biết hệ quả của khóa, JSON và metadata đối với index, consistency, transaction và lựa chọn API reactive.

## 2. Document gồm những gì?

Couchbase tổ chức dữ liệu theo **bucket → scope → collection → document**. Mỗi document có một **document ID**, phần nội dung và metadata của hệ thống. Với tài liệu JSON, nội dung là một JSON value, phổ biến nhất là JSON object.

Ví dụ document trong collection `commerce.sales.orders`:

**Document ID:** `tenant::42::order::1001`

**JSON content:**

~~~json
{
  "type": "order",
  "schemaVersion": 2,
  "tenantId": "42",
  "customerId": "customer::87",
  "status": "PAID",
  "total": 1490000,
  "currency": "VND",
  "createdAt": "2026-11-25T02:15:00Z",
  "items": [
    {
      "productId": "sku::A1",
      "quantity": 2,
      "unitPrice": 745000
    }
  ]
}
~~~

**Metadata minh họa:** document ID `tenant::42::order::1001`, CAS và expiry (nếu đặt). Metadata được Couchbase quản lý **bên ngoài** object JSON ở trên. CAS/expiry không tự biến thành các trường `cas`/`expiry` của nội dung.

~~~mermaid
flowchart TD
    K["Keyspace: commerce.sales.orders"]
    ID["Document ID: tenant::42::order::1001"]
    J["JSON content: status, total, items..."]
    M["System metadata: CAS, expiry..."]
    K --> ID
    ID --> J
    ID --> M
~~~

Điểm cần nhớ: **định danh đầy đủ** cho một document là *collection* cùng *document ID*. Một ID giống nhau có thể xuất hiện ở hai collection khác nhau mà không xung đột.

## 3. Khóa tài liệu: phạm vi và vai trò

### 3.1. Khóa là định danh riêng của document trong collection

Document ID (còn gọi là *key*) là chuỗi dùng để đọc và ghi KV. Trong một collection, không thể có hai document hiện hữu mang cùng ID. Các thao tác có ý nghĩa khác nhau:

| Thao tác KV | Ý nghĩa khi dùng cùng document ID | Nếu ID chưa tồn tại/đã tồn tại |
|---|---|---|
| `insert(id, value)` | Tạo document mới | Lỗi nếu document đã tồn tại |
| `get(id)` | Đọc document | Lỗi nếu document không tồn tại |
| `upsert(id, value)` | Tạo mới hoặc thay toàn bộ nội dung | Có thể tạo nếu ID chưa tồn tại |
| `replace(id, value)` | Thay nội dung document hiện có | Lỗi nếu ID không tồn tại |
| `remove(id)` | Xóa document | Lỗi nếu ID không tồn tại |

`upsert` thuận tiện nhưng có nguy cơ **ghi đè ngoài ý muốn**. Nếu nghiệp vụ yêu cầu “chỉ tạo một lần”, `insert` giúp phát hiện khóa trùng. Nếu yêu cầu “cập nhật khi đúng phiên bản đã đọc”, dùng **CAS** với `replace`.

Các thao tác KV tới ID đã biết thường đi thẳng đến **Data Service**; không cần Query/Index Service hoặc tạo GSI. Nếu cần tìm nhiều document theo trường `status`, `tenantId` thì dùng SQL++ và chỉ mục phù hợp.

### 3.2. Khóa không phải trường `id` trong JSON

Document ID:

~~~text
tenant::42::order::1001
~~~

JSON có thể không chứa `id`:

~~~json
{
  "tenantId": "42",
  "status": "PAID",
  "total": 1490000
}
~~~

Một trường JSON như `orderId` hoặc `id` do ứng dụng lưu là **dữ liệu bình thường**, không tự đồng bộ với khóa. Nếu chọn lưu trùng ID trong JSON để thuận tiện trao đổi với hệ thống ngoài, phải có quy tắc đồng bộ tránh lệch dữ liệu.

Trong SQL++:

~~~sql
SELECT
    META(o).id AS documentId,
    o.status,
    o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.status = "PAID";
~~~

`META(o).id` lấy **khóa hệ thống**; `o.id` (nếu có) lấy **trường JSON** mang tên `id`. Hai biểu thức không tương đương.

### 3.3. Khóa không đồng nghĩa khóa chính quan hệ

Document ID cho phép định vị một document qua KV. Tuy nhiên:

- Nó không tự tạo **foreign key** đến document ở collection khác.
- Nó không áp đặt mọi document cùng schema hay kiểu trường.
- Nó không khiến document có tiền tố khóa giống nhau bắt buộc nằm cùng Data node.
- Nó không tự cấp quyền đọc document; ứng dụng phải kiểm tra xác thực và phân quyền.

Có thể xem document ID là định danh ổn định, nhưng tránh suy rộng thành toàn bộ đặc tính **PRIMARY KEY + FOREIGN KEY + ràng buộc bảng** của RDBMS.

## 4. Thiết kế document ID phù hợp với bài toán

Một khóa tốt thường cần các tính chất:

1. **Duy nhất trong collection:** hạn chế va chạm giữa hai thực thể.
2. **Ổn định:** không đổi theo các thuộc tính nghiệp vụ thường xuyên thay đổi, chẳng hạn trạng thái đơn hoặc tên khách hàng.
3. **Có quy ước rõ ràng:** dễ tạo và phân tích khi debug, migration hoặc import.
4. **Không lộ dữ liệu nhạy cảm:** không đặt token bí mật, mật khẩu hoặc PII không cần thiết vào ID.
5. **Dễ tái sử dụng trong idempotency:** cùng một yêu cầu tạo đơn có thể tra cứu khóa xác định thay vì tạo đơn trùng.

### 4.1. Khóa từ ID nghiệp vụ

~~~text
order::1001
customer::87
product::sku-A1
~~~

Ưu điểm là dễ tra cứu khi hệ thống đã có mã nghiệp vụ duy nhất và ổn định. Rủi ro là dữ liệu có thể đến từ nhiều nguồn cùng dùng mã `1001`. Cần thêm **namespace**/nguồn hoặc tenant nếu có khả năng trùng.

### 4.2. Khóa được tạo ngẫu nhiên

~~~text
order::d2490e1c-5a09-491e-9e0f-8f693cd80853
~~~

UUID phù hợp khi không có mã nghiệp vụ duy nhất. Muốn hỗ trợ idempotency khi client retry việc tạo mới, nên có **idempotency key** và cách lưu/kiểm tra tương ứng; tạo UUID mới ở mỗi lần retry có thể tạo nhiều document.

### 4.3. Khóa nhiều tenant

~~~text
tenant::42::order::1001
tenant::99::order::1001
~~~

Cách này giảm trùng khóa khi nhiều tenant dùng chung collection. Tuy nhiên **khóa có tenant không thay thế quyền truy cập**: endpoint nhận ID bất kỳ vẫn phải kiểm tra người gọi có quyền truy cập tenant/document đó. Nếu truy vấn theo thuộc tính, đặt thêm `tenantId` trong JSON và thiết kế index phù hợp.

### 4.4. Có cần prefix?

Prefix `order::` hoặc `product::` có ích cho vận hành và đặt tên, đặc biệt ở collection trộn nhiều loại document. Nhưng nếu đã tách `orders`/`products` thành collection riêng, prefix là quy ước tùy chọn.

Couchbase phân phối document theo hàm băm định danh; các document có prefix giống nhau **không mặc nhiên ở gần nhau về lưu trữ**. Muốn truy vấn theo thời gian, tenant hoặc trạng thái, thường cần trường JSON và secondary index; không kỳ vọng danh sách khóa có thể quét hiệu quả theo thứ tự từ vựng.

**Cẩn trọng với giới hạn độ dài/ký tự khóa:** các giới hạn cụ thể phụ thuộc phiên bản/server SDK. Dùng ID ngắn, ổn định, được chuẩn hóa và kiểm tra quy tắc mã hóa ngay tại biên ứng dụng. Tránh nhúng JSON lớn hoặc dữ liệu bí mật vào ID.

## 5. Nội dung JSON: schema linh hoạt nhưng phải có hợp đồng dữ liệu

JSON cho phép các kiểu chính:

| Kiểu JSON | Ví dụ | Trường hợp sử dụng |
|---|---|---|
| Object | `{"shipping":{"city":"Hanoi"}}` | Dữ liệu lồng nhau có tên trường |
| Array | `[{"sku":"A1","qty":2}]` | Danh sách item hoặc giá trị |
| String | `"PAID"` | Trạng thái, mã, ISO-8601 timestamp |
| Number | `1490000` hoặc `0.15` | Số lượng, giá trị tiền/tỷ lệ với chính sách độ chính xác thích hợp |
| Boolean | `true` | Cờ nghiệp vụ |
| Null | `null` | Giá trị được khai báo rõ là rỗng |

JSON không có kiểu ngày giờ gốc. Một quy ước thường dùng là lưu `createdAt`/`updatedAt` dưới dạng **chuỗi ISO-8601 UTC**; khi so sánh/sắp xếp phải kiểm chứng định dạng đồng nhất hoặc dùng biểu diễn thời gian phù hợp.

### 5.1. Tách thông tin phụ thuộc nghiệp vụ

Đơn hàng có thể chứa các line item vì thường được đọc cùng đơn:

~~~json
{
  "status": "PAID",
  "items": [
    {"sku": "A1", "quantity": 2, "unitPrice": 745000},
    {"sku": "B2", "quantity": 1, "unitPrice": 99000}
  ]
}
~~~

Ngược lại, hồ sơ khách hàng và danh mục sản phẩm thường là các thực thể lớn, thay đổi theo vòng đời riêng. Có thể lưu tham chiếu dạng `customerId` và `productId`, rồi đọc riêng hoặc dùng SQL++ JOIN khi cần.

Cân nhắc:

- **Embed** khi dữ liệu có cùng vòng đời, kích thước hợp lý và thường được đọc/ghi cùng nhau.
- **Reference** khi thực thể được nhiều document sử dụng hoặc có vòng đời/quyền riêng.
- Tránh mảng không giới hạn kích thước bên trong một document: ghi/đọc toàn bộ tài liệu lớn có thể tăng chi phí mạng, CAS conflict và vận hành.

### 5.2. Trường không tồn tại khác trường có giá trị null

Hai document:

~~~json
{"status": "PAID"}
~~~

~~~json
{"status": "PAID", "shippedAt": null}
~~~

Khác nhau ở chỗ document đầu **thiếu trường** `shippedAt` (MISSING), document sau **có trường với giá trị NULL**. Trong SQL++:

~~~sql
SELECT META(o).id AS id
FROM `commerce`.`sales`.`orders` AS o
WHERE o.shippedAt IS MISSING;
~~~

~~~sql
SELECT META(o).id AS id
FROM `commerce`.`sales`.`orders` AS o
WHERE o.shippedAt IS NULL;
~~~

Việc xử lý MISSING và NULL ảnh hưởng điều kiện lọc, biểu thức, thống kê và khả năng sử dụng index. Hãy chuẩn hóa quy ước, ví dụ “chưa giao hàng” dùng `status = "PAID"` và không có `shippedAt`, thay vì trộn bừa `""`, `null` và thiếu trường.

### 5.3. Trường dạng số và tiền

JSON Number không mang định nghĩa kiểu `long`, `double` hay `BigDecimal` cố định. Cách SDK/serializer diễn giải số và độ chính xác phụ thuộc API/language.

Với tiền VND, lưu giá trị **đơn vị nguyên** (ví dụ `1490000` đồng) thường dễ kiểm soát hơn kiểu dấu phẩy động. Với tiền có phần thập phân, cần quy ước integer minor unit hoặc decimal/chuỗi cùng cơ chế chuyển đổi được kiểm thử. Không dựa vào số thực nhị phân cho tính toán tiền thiếu kiểm soát.

### 5.4. Schema version để phát triển hệ thống

JSON linh hoạt không có nghĩa ứng dụng được phép bỏ qua tính tương thích:

~~~json
{
  "schemaVersion": 2,
  "status": "PAID",
  "total": 1490000
}
~~~

Khi chuyển từ `totalAmount` sang `total`:

- Reader có thể tạm hỗ trợ cả version cũ và mới trong giai đoạn migration.
- Writer mới ghi đúng schema version đã công bố.
- Index và truy vấn SQL++ cần được cập nhật trước khi xóa trường cũ.
- Test phải bao gồm document cũ, document mới, NULL và MISSING.

Document JSON cũng có giới hạn kích thước theo Couchbase/version. Không gom toàn bộ lịch sử sự kiện hoặc log không giới hạn vào một document để “tiết kiệm collection”.

## 6. Metadata do Couchbase quản lý

**System metadata** là dữ liệu Couchbase dùng để quản lý document hoặc đi kèm kết quả KV. Một số thuộc tính thường gặp:

| Metadata | Công dụng | Lưu ý |
|---|---|---|
| **Document ID** | Định danh document trong collection | Đọc qua API KV và `META(alias).id` trong SQL++ |
| **CAS** | Token thay đổi phiên bản phục vụ optimistic concurrency | Được server cấp; không dùng như timestamp hoặc bộ đếm nghiệp vụ |
| **Expiry/TTL** | Thời điểm/chính sách document hết hạn | Không tự có trường JSON `expiresAt` |
| **Flags/type thông tin nội bộ** | Thông tin biểu diễn nội dung theo API/server | Không nhầm với trường JSON `type` do ứng dụng tự đặt |
| **Mutation token** (khi API trả về) | Mô tả sự thay đổi để hỗ trợ một số chiến lược nhất quán | Không phải khóa document hoặc business version |

Không phải mọi API đều trả về tất cả metadata. Một số metadata chỉ được hiển thị khi yêu cầu thêm tùy chọn; các trường trong kết quả `META()` cũng cần kiểm tra theo phiên bản Couchbase và loại document.

### 6.1. Metadata khác audit fields

Các trường sau là **application data**:

~~~json
{
  "createdAt": "2026-11-25T02:15:00Z",
  "updatedAt": "2026-11-25T03:00:00Z",
  "createdBy": "service-order",
  "schemaVersion": 2
}
~~~

Chúng giúp kiểm toán, phân tích và migration, nhưng không phải CAS/expiry của Couchbase. Một document có thể được sửa mà `updatedAt` không đổi nếu ứng dụng quên ghi; CAS sẽ thay đổi theo mutation được server thực hiện.

Không suy ra chính xác “ai sửa, sửa lúc nào” chỉ từ CAS. Muốn audit đáng tin cậy, cần thiết kế audit riêng và xem xét transaction/event log.

### 6.2. Extended attributes (XATTR)

Couchbase có **extended attributes**, thường gọi là XATTR: dữ liệu phụ gắn với document nhưng không nằm trong body JSON thông thường. XATTR có thể phục vụ metadata của ứng dụng hoặc tính năng hệ thống, với API và quyền truy cập riêng.

Không nên giả định XATTR và metadata hệ thống là một. XATTR do ứng dụng tạo vẫn cần thiết kế, phân quyền và giới hạn kích thước; không dùng để lưu bí mật hoặc dữ liệu nhạy cảm không được bảo vệ.

## 7. Đọc/ghi JSON và metadata bằng Java SDK

Giả sử bucket `commerce`, scope `sales` và collection `orders` đã được tạo; tài khoản có quyền KV phù hợp. Đoạn Java SDK sau minh họa **đường truy cập theo ID**:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Bucket;
import com.couchbase.client.java.Scope;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.kv.MutationResult;
import java.time.Duration;

// Trong ứng dụng thực, dùng secret manager và TLS đúng môi trường.
Cluster cluster = Cluster.connect(
        "couchbase://localhost", "app-user", "example-password");
try {
    Bucket bucket = cluster.bucket("commerce");
    bucket.waitUntilReady(Duration.ofSeconds(10));
    Scope scope = bucket.scope("sales");
    Collection orders = scope.collection("orders");

    String id = "tenant::42::order::1001";
    JsonObject body = JsonObject.create()
            .put("tenantId", "42")
            .put("status", "NEW")
            .put("total", 1490000);

    MutationResult inserted = orders.insert(id, body);
    System.out.println("CAS sau insert: " + inserted.cas());

    GetResult result = orders.get(id);
    System.out.println("JSON: " + result.contentAsObject());
    System.out.println("CAS sau get: " + result.cas());
} finally {
    cluster.disconnect();
}
~~~

Đây là ví dụ giảng dạy nên khai báo trực tiếp trong khối mã. Trong ứng dụng Spring Boot, SDK connection thường do cấu hình và lifecycle quản lý; không tạo/disconnect `Cluster` trên mỗi HTTP request. Không đưa mật khẩu thật vào source code.

**Ghi nhớ:** `orders.get(id)` trả về body và metadata kết quả; body `JsonObject` không tự chứa CAS. Nếu gọi `orders.get(id)` lần nữa sau một thao tác cập nhật, giá trị CAS có thể khác.

### Khi nào nên dùng insert, upsert, replace?

| Yêu cầu nghiệp vụ | Phương thức phù hợp | Rủi ro cần xử lý |
|---|---|---|
| Tạo đơn đúng một lần | `insert` | Trùng khóa → xử lý conflict/idempotency |
| Đồng bộ cache/snapshot có thể tạo mới | `upsert` | Có thể ghi đè nội dung hiện có |
| Chỉ sửa đơn đã tồn tại | `replace` | Document đã bị xóa → xử lý not found |
| Sửa khi document chưa đổi từ lần đọc | `replace` + CAS | CAS mismatch → xử lý cập nhật cạnh tranh |
| Xóa đơn theo ID | `remove` | Kiểm tra nghiệp vụ, quyền, idempotency và transaction khi cần |

Một lệnh KV thường tác động lên **một document**. Khi cần bảo đảm nhiều document cùng cập nhật nhất quán, cân nhắc transaction với phạm vi và yêu cầu được phiên bản Couchbase hỗ trợ.

## 8. CAS: metadata giúp tránh ghi đè khi có cạnh tranh

Xét hai request cùng cập nhật trạng thái đơn hàng:

~~~text
T0: Request A đọc status=NEW, CAS=V1
T1: Request B đọc status=NEW, CAS=V1
T2: Request A ghi status=PAID với CAS=V1  -> thành công, CAS=V2
T3: Request B ghi status=CANCELLED với CAS=V1 -> bị từ chối
~~~

Nếu không kiểm soát CAS, Request B có thể ghi đè thay đổi của A (**lost update**).

Ví dụ với Java SDK:

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.json.JsonObject;

// orders là Collection được khởi tạo từ bucket.scope.collection.
String id = "tenant::42::order::1001";

GetResult current = orders.get(id);
JsonObject changed = current.contentAsObject()
        .put("status", "PAID");

orders.replace(
        id,
        changed,
        replaceOptions().cas(current.cas())
);
~~~

Nếu có thay đổi đồng thời, thao tác có thể ném lỗi CAS mismatch. Cách xử lý đúng phụ thuộc nghiệp vụ:

- Đọc lại document mới nhất.
- Kiểm tra trạng thái chuyển tiếp còn hợp lệ không.
- Hợp nhất dữ liệu nếu an toàn, hoặc từ chối yêu cầu và yêu cầu người dùng xử lý xung đột.

**Không retry vô hạn và không lấy CAS mới chỉ để ép ghi đè** khi thao tác có điều kiện nghiệp vụ. CAS là token opaque của hệ thống: không cộng 1, không dùng làm timestamp, không tự lưu một giá trị CAS cũ vào JSON với kỳ vọng server đồng bộ.

## 9. TTL/expiry: thời gian sống là metadata

**TTL** quy định khi nào document được xem là hết hạn. Ví dụ collection `sessions` lưu phiên đăng nhập ngắn hạn, còn `orders` cần được giữ theo chính sách nghiệp vụ.

Dùng SDK để đặt expiry trong một thao tác ghi:

~~~java
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;
import java.time.Duration;
import com.couchbase.client.java.json.JsonObject;

JsonObject session = JsonObject.create()
        .put("userId", "customer::87")
        .put("device", "mobile");

sessions.upsert(
        "session::abc123",
        session,
        upsertOptions().expiry(Duration.ofMinutes(30))
);
~~~

`sessions` ở đây là biến `Collection` trỏ tới collection chứa session. Đoạn ví dụ chỉ đặt TTL, không minh họa quy tắc xác thực hoặc vòng đời toàn bộ phiên.

Phân biệt:

| Giá trị | Nằm ở đâu? | Công dụng |
|---|---|---|
| `createdAt` | Trường JSON do ứng dụng ghi | Thời gian tạo theo nghiệp vụ |
| `expiresAt` | Trường JSON nếu ứng dụng tự thiết kế | Có thể dùng hiển thị/tra cứu, nhưng **không tự kích hoạt TTL** |
| **Expiry metadata** | Quản lý bởi Couchbase | Quyết định document hết hạn |
| **Bucket/collection maxTTL** (khi hỗ trợ) | Cấu hình quản trị | Chính sách thời gian sống mặc định/giới hạn cho document |

Sau expiry, document không còn được phục vụ như document đang tồn tại. Việc dọn dữ liệu vật lý và cập nhật index có thể diễn ra sau đó; vì vậy không lấy trạng thái index như đồng hồ chính xác cho thời điểm xóa vật lý.

**Cần kiểm tra expiry khi cập nhật:** thao tác replace/upsert có thể thay đổi hoặc reset expiry tùy API, tham số và cấu hình. Nếu nghiệp vụ yêu cầu giữ thời gian hết hạn cũ, dùng cơ chế preserve-expiry hoặc đặt lại expiry được SDK/version hỗ trợ, và kiểm thử hành vi thực tế.

TTL không thay thế backup, retention compliance, transaction hay sự kiện nghiệp vụ “hủy đơn”.

## 10. Truy vấn JSON và metadata bằng SQL++

### 10.1. Lấy document theo ID

Tốt nhất, khi đã có ID và collection, dùng KV `get`. Nếu cần biểu diễn tương đương trong SQL++, có thể dùng `USE KEYS`:

~~~sql
SELECT
    META(o).id AS id,
    o.status,
    o.total
FROM `commerce`.`sales`.`orders` AS o
USE KEYS "tenant::42::order::1001";
~~~

Cú pháp `USE KEYS` hướng truy vấn đến khóa được chỉ rõ, không giống truy vấn lọc toàn bộ collection theo một trường JSON. Với Java SDK, `collection.get(id)` vẫn là lựa chọn trực tiếp và gọn hơn.

### 10.2. Tìm theo trường JSON

~~~sql
SELECT
    META(o).id AS id,
    o.tenantId,
    o.status,
    o.total,
    o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.status = $status
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Đây là truy vấn theo thuộc tính, nên thiết kế GSI theo mẫu truy vấn:

~~~sql
CREATE INDEX ix_orders_tenant_status_created
ON `commerce`.`sales`.`orders`(
    tenantId, status, createdAt DESC
);
~~~

Sau đó kiểm tra kế hoạch:

~~~sql
EXPLAIN
SELECT META(o).id AS id, o.status, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "42"
  AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Cần quan sát index scan, fetch, sort và độ lớn tập dữ liệu. Trường JSON `total` chưa có trong ví dụ index nên query có thể cần **Fetch** để đọc body. Không tự động tạo primary index chỉ để giải quyết mọi truy vấn.

### 10.3. Metadata trong SQL++

`META(o).id` thường dùng để trả document ID. SQL++ cũng có thể cung cấp các thuộc tính metadata khác (như CAS/expiry) qua `META(o)` tùy phiên bản và ngữ cảnh. Chỉ dựa vào thuộc tính đã được server/API của dự án hỗ trợ; không coi mọi trường metadata đều là field JSON có thể lọc/index giống dữ liệu nghiệp vụ.

Nếu muốn tìm các document “sắp hết TTL”, hãy xác định rõ yêu cầu và API được hỗ trợ. Đối với luồng giao dịch quan trọng, việc ứng dụng lưu `expiresAt` vào JSON **chỉ là dữ liệu phục vụ truy vấn**, còn expiry thực tế vẫn phải được cấu hình trên document.

## 11. Spring Data Couchbase: ánh xạ ID, JSON và CAS

Spring Data Couchbase kết nối Java object với document và cho phép dùng `CouchbaseRepository`, `CouchbaseTemplate`. Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;

    @Version
    private Long version;

    @Field
    private String tenantId;

    @Field
    private String status;

    @Field
    private Long total;

    // Constructor, getter/setter được lược bớt để tập trung vào mapping.
}
~~~

| Annotation | Ý nghĩa | Ghi chú |
|---|---|---|
| `@Document` | Đánh dấu entity lưu dạng document | Áp dụng quy tắc mapping của Spring Data |
| `@Scope("sales")` | Chọn scope cho entity | Cần đúng phiên bản Spring Data hỗ trợ |
| `@Collection("orders")` | Chọn collection cho entity | Đảm bảo keyspace thực tồn tại |
| `@Id` | Ánh xạ thuộc tính Java thành document ID | Không mặc định thêm field JSON `id` |
| `@Field` | Ánh xạ property thành field dữ liệu | Có thể tùy chỉnh tên trường theo API annotation |
| `@Version` | Liên hệ CAS để optimistic locking | Không coi là business version/số đếm cần lưu trong body |

Repository:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByTenantIdAndStatus(
            String tenantId, String status);
}
~~~

Dùng repository:

~~~java
// Cần entity có id được gán hoặc cơ chế sinh ID đã cấu hình.
OrderDocument order = new OrderDocument();
// order.setId("tenant::42::order::1001");
// order.setTenantId("42");
// order.setStatus("NEW");
// order.setTotal(1490000L);

OrderDocument result = orderRepository
        .findById("tenant::42::order::1001")
        .orElseThrow();
~~~

Đoạn trên minh họa ý nghĩa của `findById`; trong code thật phải có constructor/setter hoặc builder tương ứng. `findById` thường dùng KV theo ID và collection mapping, trong khi `findByTenantIdAndStatus` là truy vấn theo trường và cần chỉ mục phù hợp.

**Lưu ý về `_class`:** Spring Data Couchbase có thể ghi trường phân biệt kiểu entity (ví dụ `_class`) trong JSON hoặc thêm điều kiện loại entity khi sinh SQL++. Vì vậy, câu lệnh SQL++ do repository sinh có thể khác câu SQL++ thủ công. Khi tối ưu index, hãy kiểm tra query thực tế, không chỉ nhìn tên phương thức repository.

### 11.1. Optimistic locking với `@Version`

Với entity có `@Version`, Spring Data dùng cơ chế phiên bản/CAS của Couchbase để phát hiện cập nhật đồng thời theo hành vi của phiên bản framework. Luồng đọc → sửa → save có thể gặp lỗi optimistic locking nếu document đã bị thay đổi kể từ lần đọc.

Thiết kế xử lý lỗi cần nêu rõ chiến lược:

- Từ chối thay đổi và trả thông báo xung đột (chẳng hạn HTTP 409) khi dữ liệu đã đổi.
- Đọc lại rồi kiểm tra business rule trước khi thử cập nhật.
- Dùng transaction khi nghiệp vụ phải cập nhật nhiều document nguyên tử.

**`@Version` và `schemaVersion` là hai khái niệm khác nhau**: một bên dùng kiểm soát cạnh tranh qua CAS; bên còn lại mô tả định dạng JSON để phục vụ migration.

### 11.2. Khi nào dùng CouchbaseTemplate?

`CouchbaseTemplate` phù hợp khi cần thao tác với entity nhưng muốn kiểm soát nhiều hơn so với derived repository method, ví dụ lựa chọn query, thao tác đọc/ghi hay xử lý lỗi theo API của phiên bản đang dùng. Dù chọn repository hay template, vẫn cần nắm rõ:

- Đường dẫn bucket/scope/collection và document ID.
- API dùng KV hay SQL++; index nào cần thiết.
- Metadata/expiry/CAS có được đọc, truyền lại và bảo toàn đúng ý định không.
- Cách framework ánh xạ trường JSON, `_class` và schema version.

Các API reactive của Spring Data Couchbase thay đổi cách thực hiện bất đồng bộ và ghép pipeline, **không đổi** khái niệm document ID, CAS hay TTL. Reactive không tự giải quyết lost update hoặc index consistency.

## 12. Dữ liệu và metadata trong một vòng đời đơn hàng

Xét luồng tạo và thanh toán đơn hàng:

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant KV as Data Service (KV)
    participant IDX as Index Service
    participant Q as Query Service
    API->>KV: insert(orderId, JSON status=NEW)
    KV-->>API: success + CAS V1
    API->>KV: get(orderId)
    KV-->>API: JSON + CAS V1
    API->>KV: replace(orderId, status=PAID, CAS V1)
    KV-->>API: success + CAS V2
    KV-->>IDX: Ghi thay đổi để cập nhật GSI
    API->>Q: SQL++ WHERE status=PAID
    Q->>IDX: Index scan
    IDX-->>Q: Kết quả có thể chưa bắt kịp ghi
    Q-->>API: Dòng kết quả theo scan consistency
~~~

Từ sơ đồ:

- **Khóa** xác định chính xác document khi tạo/đọc/sửa.
- **JSON** chứa trạng thái nghiệp vụ, số tiền và item.
- **CAS** phát hiện cập nhật đồng thời.
- **GSI** giúp tìm theo field nhưng quá trình cập nhật có thể trễ so với thao tác KV.
- **TTL** (nếu áp dụng) là metadata quyết định document hết hạn, độc lập với trường `createdAt` trong JSON.

Khi đọc ngay sau ghi, nếu có ID thì `get(id)` là đường phù hợp. Nếu bắt buộc truy vấn SQL++, hãy chọn scan consistency thích hợp: `not_bounded` tối ưu phản hồi nhưng có thể chưa bắt kịp ghi; `request_plus` chờ index cập nhật và có thể tăng độ trễ. Các API có hỗ trợ mutation state cho phép chiến lược có mục tiêu hơn.

## 13. Những lỗi thường gặp khi làm việc với ID, JSON và metadata

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `DocumentNotFound` dù thấy ID trong console | Sai bucket/scope/collection; ID khác ký tự hoặc encoding | Log keyspace và ID chuẩn hóa, kiểm tra collection đích |
| `DocumentExists` khi tạo đơn | Khóa đã có hoặc retry lặp lại tạo | Đặt idempotency rule; dùng insert có xử lý trùng |
| Ghi mất thay đổi của request khác | Upsert/replace thiếu kiểm soát concurrency | Dùng CAS và business rule; xử lý conflict rõ ràng |
| SQL++ trả ID nhưng entity bị lỗi mapping | Java field khác JSON, thiếu field, kiểu số không khớp | Kiểm tra JSON thật, mapping, schema version |
| `o.id` rỗng nhưng `META(o).id` có giá trị | ID không được lưu dưới dạng field JSON | Dùng metadata đúng API hoặc ánh xạ `@Id` |
| Query thấy bản cũ ngay sau ghi | Index chưa cập nhật hoặc consistency mặc định | Dùng KV theo ID hoặc scan consistency cần thiết |
| Document đột nhiên hết hạn | TTL được đặt khi ghi hoặc cấu hình bucket/collection | Kiểm tra expiry, preserve-expiry, cấu hình môi trường |
| `@Version` báo conflict khi save | CAS thay đổi từ lần đọc | Đọc lại, xác thực trạng thái và retry có điều kiện |
| Tìm theo tiền sai | Biểu diễn số thiếu nhất quán giữa các serializer | Chuẩn hóa integer minor unit/decimal handling |
| Tìm document sau migration thất bại | Chưa chuyển document hoặc ID/keyspace thay đổi | Lập mapping chuyển dữ liệu và kiểm chứng trước chuyển API |

Thứ tự kiểm tra thường hữu ích: **keyspace → document ID → thao tác KV/SQL++ → JSON mapping → CAS/TTL → index/consistency → quyền và tài nguyên**.

## 14. Bài tập thực hành

### Bài tập A — phân biệt khóa và body

Cho document ID `tenant::42::order::1001` trong `commerce.sales.orders` với JSON:

~~~json
{"status":"PAID","total":1490000}
~~~

1. Document có field JSON `id` không?
2. Truy vấn SQL++ nào lấy document ID?
3. Nếu collection `commerce.sales.payments` cũng có document ID giống hệt thì có xung đột không?

**Gợi ý:** document không có `id` ở body; lấy `META(o).id`; khóa chỉ cần duy nhất trong phạm vi collection.

### Bài tập B — thiết kế ID cho nhiều tenant

Một ứng dụng nhận `orderNumber=1001` từ mỗi tenant. Hãy chọn quy ước khóa để tenant `42` và `99` không trùng nhau; giải thích vì sao vẫn cần xác minh quyền tenant khi `GET /orders/{id}`.

**Gợi ý:** có thể dùng `tenant::<tenantId>::order::<orderNumber>`; ID không phải cơ chế phân quyền.

### Bài tập C — NULL và MISSING

Tạo hai document: một không có `shippedAt`, một có `"shippedAt": null`. Viết SQL++ lọc hai trường hợp riêng. Giải thích tác động lên schema version và logic hiển thị.

### Bài tập D — tránh lost update

Hai request cùng đọc CAS ban đầu V1. Request A cập nhật `status = "PAID"` thành công. Request B thử `status = "CANCELLED"` với CAS V1. Dự đoán kết quả, đề xuất cách xử lý nghiệp vụ khi hủy đơn đã thanh toán.

### Bài tập E — TTL và audit

Một document session có `createdAt` trong JSON nhưng không đặt expiry. Document có tự hết hạn sau 30 phút không? Ngược lại, khi expiry metadata được đặt 30 phút, vì sao trường `expiresAt` trong JSON không phải điều kiện bắt buộc?

### Bài tập F — Spring Data và query plan

Một repository có `@Id`, `@Version` và phương thức `findByTenantIdAndStatus`. Cho biết cách lấy theo ID đi qua service nào, khi nào phải tạo GSI và vì sao phải kiểm tra SQL++ được Spring Data sinh trước khi thiết kế index.

## 15. Checklist khi triển khai

- [ ] Xác định chính xác **bucket.scope.collection** cho entity và repository.
- [ ] Quy định format ID duy nhất, ổn định, xử lý va chạm/idempotency.
- [ ] Không nhầm document ID hoặc CAS/TTL với field JSON.
- [ ] Chuẩn hóa tên field, timestamp, kiểu tiền, null/missing và schemaVersion.
- [ ] Chọn `insert`, `upsert` hoặc `replace` đúng semantics nghiệp vụ.
- [ ] Dùng CAS/optimistic locking cho cập nhật có cạnh tranh.
- [ ] Quy định TTL theo vòng đời dữ liệu, kiểm tra khi update và migration.
- [ ] Tạo GSI theo truy vấn thực tế; kiểm tra `EXPLAIN` và scan consistency.
- [ ] Xác thực quyền tenant/document trong cả đường KV và SQL++.
- [ ] Kiểm tra code mapping và đặc tính API trên đúng phiên bản Spring Data Couchbase/Couchbase SDK triển khai.

## 16. Kết luận

Một document Couchbase có ba lớp cần nhìn đồng thời: **document ID** dùng để định vị bản ghi, **JSON content** mô tả dữ liệu nghiệp vụ, và **metadata** phục vụ các cơ chế hệ thống như CAS và TTL. Phân biệt ba lớp giúp sử dụng chính xác KV, SQL++, repository và `CouchbaseTemplate`, đồng thời phòng tránh lỗi phổ biến như ghi đè dữ liệu, đọc sai collection, sai schema hoặc nhầm TTL với trường ngày giờ trong JSON.

Trong Spring Data Couchbase, cấu trúc này vẫn giữ nguyên dù ứng dụng dùng repository đồng bộ, template hay reactive API. Khả năng mở rộng và tính nhất quán bắt đầu từ lựa chọn document ID và hợp đồng JSON rõ ràng, sau đó được hoàn thiện bằng index, CAS, TTL, transaction và cấu hình vận hành phù hợp.
