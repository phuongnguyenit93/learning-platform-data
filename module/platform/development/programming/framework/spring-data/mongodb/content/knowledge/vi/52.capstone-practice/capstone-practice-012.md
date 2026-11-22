# Rà soát tính đúng dữ liệu, bảo mật và tiêu chí sẵn sàng triển khai

Một ứng dụng sử dụng **Spring Data MongoDB** có thể chạy tốt trên máy phát triển nhưng vẫn gặp lỗi nghiêm trọng khi triển khai: dữ liệu bị ghi trùng sau một lần retry, đơn hàng bị truy cập chéo tenant, index không có trong môi trường thật, hoặc dữ liệu cũ không đọc được sau khi đổi schema. Kiểm thử endpoint trả HTTP 200 mới chỉ chứng minh được một phần nhỏ của hệ thống.

Bài **thực hành tổng hợp** này xây dựng một quy trình rà soát trước phát hành (*release readiness review*) cho dịch vụ đặt hàng sử dụng `MongoTemplate`, repository, transaction và có thể mở rộng sang truy cập reactive. Trọng tâm là ba câu hỏi:

1. **Dữ liệu có đúng không?** Các quy tắc nghiệp vụ có được bảo vệ khi ghi đồng thời, retry, lỗi một phần và thay đổi schema hay không?
2. **Dữ liệu có an toàn không?** Ứng dụng có xác thực, phân quyền theo tenant, giữ kín thông tin nhạy cảm và giới hạn quyền truy cập MongoDB hay không?
3. **Hệ thống đã đủ điều kiện triển khai chưa?** Có bằng chứng từ kiểm thử, đo hiệu năng, sao lưu/khôi phục, giám sát, migration và phương án xử lý sự cố hay chưa?

Mục tiêu cuối cùng là tạo được một **hồ sơ quyết định GO/NO-GO** dựa trên kết quả kiểm chứng thực tế, không chỉ dựa trên cảm giác rằng mã nguồn đã hoàn thành.

## 1. Bối cảnh capstone và phạm vi rà soát

Giả sử ứng dụng phục vụ nhiều cửa hàng (*tenant*), có bốn collection:

| Collection | Dữ liệu chính | Thao tác quan trọng |
| --- | --- | --- |
| `customers` | Khách hàng theo `tenantId`, email chuẩn hóa, trạng thái | Đăng ký, đọc và cập nhật thông tin khách |
| `products` | Sản phẩm, SKU và giá hiện tại | Tra cứu catalog, đổi giá, ẩn sản phẩm |
| `inventory` | Tồn kho theo cặp `(tenantId, productId)` | Giữ/chuyển/hoàn tồn kho cạnh tranh |
| `orders` | Đơn hàng, dòng hàng và snapshot giá mua | Tạo đơn, chuyển trạng thái, xem lịch sử |

Một đơn hàng minh họa:

~~~javascript
{
  _id: "ord_1001",
  tenantId: "shop_a",
  idempotencyKey: "create-order-req-78",
  requestFingerprint: "sha256:...",
  customerId: "cus_100",
  status: "CREATED",
  currency: "VND",
  totalMinor: NumberLong("250000"),
  lines: [
    {
      productId: "prd_10",
      nameAtPurchase: "Bình giữ nhiệt",
      unitPriceMinor: NumberLong("125000"),
      quantity: 2,
      lineTotalMinor: NumberLong("250000")
    }
  ],
  createdAt: ISODate("2026-11-20T03:00:00Z"),
  version: NumberLong("0")
}
~~~

Mẫu trên là **hợp đồng dữ liệu dùng trong bài tập**, không phải cấu trúc bắt buộc của Spring Data MongoDB. Tiền được lưu theo đơn vị nhỏ nhất đã quy ước; với nghiệp vụ có số thập phân cần xác định cách làm tròn, cách lưu `long`/`Decimal128` và giới hạn số học. Địa chỉ, thông tin thanh toán hoặc dữ liệu cá nhân có thể cần snapshot riêng, nhưng chỉ giữ trường thực sự cần thiết.

Phạm vi kiểm chứng phải bao gồm **API → service → Spring Data → MongoDB → hệ thống ngoài**. Nếu có gửi sự kiện hoặc gọi cổng thanh toán, việc thành công ở MongoDB chưa đủ chứng minh toàn bộ quy trình đã thành công.

## 2. Xác định invariant trước khi kiểm thử

*Invariant* là điều kiện phải luôn đúng ở ranh giới nghiệp vụ đã định, kể cả khi hai request cùng chạy hoặc một thành phần bị lỗi. Mỗi invariant cần có **nơi cưỡng chế** và **phép kiểm chứng**.

| Mã | Invariant | Nơi bảo vệ chính | Cách chứng minh |
| --- | --- | --- | --- |
| D1 | Không có hai đơn cùng `idempotencyKey` trong một tenant | Unique index, logic xử lý request lặp | Hai request đồng thời cùng khóa chỉ tạo một kết quả nghiệp vụ |
| D2 | Đơn hàng không chứa sản phẩm của tenant khác | Kiểm tra dữ liệu theo tenant trong service/query | Thử tạo đơn với `productId` thuộc tenant khác bị từ chối |
| D3 | Không bán vượt số tồn khả dụng | Atomic conditional update hoặc transaction | Nhiều request cạnh tranh, tổng lượng giữ không vượt lượng có sẵn |
| D4 | `totalMinor` bằng tổng các dòng theo quy tắc giá/chiết khấu | Domain service và kiểm tra dữ liệu | Trường hợp giá âm, quantity 0, overflow và tính lại tổng đều bị phát hiện |
| D5 | Đơn đã chốt giữ nguyên giá/tên tại thời điểm mua | Snapshot trong `orders.lines` | Đổi catalog không làm thay đổi lịch sử đơn |
| D6 | Chuyển trạng thái đơn tuân thủ state machine | Update có điều kiện trạng thái/version | Không thể chuyển `CANCELLED → PAID` khi quy tắc không cho phép |
| D7 | Người dùng chỉ đọc/ghi dữ liệu tenant được ủy quyền | Authorization, mọi query mang tenant scope | Cross-tenant test cho từng endpoint và tác vụ nội bộ |
| D8 | Một business event không gây side effect hai lần | Event ID, idempotent consumer, outbox nếu cần | Gửi lại event không phát sinh thanh toán/thông báo/điểm thưởng trùng |

Đây là ví dụ. Trong dự án thật, cần bổ sung invariant từ đặc tả nghiệp vụ: thuế, hoàn tiền, giao hàng, quyền xóa dữ liệu, thời gian lưu trữ và đối soát tài chính.

### Biến invariant thành tiêu chí kiểm tra

Không viết tiêu chí mơ hồ kiểu “đơn hàng phải đúng”. Hãy nêu điều kiện đầu vào, hành động cạnh tranh và hậu điều kiện. Ví dụ với D3: “Cho một document tồn kho `available = 3`, hai request độc lập cùng giữ `quantity = 2`; tối đa một request thành công, kết quả còn lại không âm, và không tồn tại đơn đã xác nhận mà chưa được giữ hàng theo thiết kế”.

Lưu ý nhiều invariant **không thể cưỡng chế chỉ bằng annotation Java**. `@NotNull`, `@Valid` giúp kiểm tra đầu vào nhưng không thay cho unique index, truy vấn có điều kiện hoặc transaction tại database.

## 3. Rà soát schema, mapping và index

Trong MongoDB, nhiều document có thể cùng tồn tại với cấu trúc và kiểu BSON khác nhau. Sau migration hoặc refactor Java, một trường có thể là `String` ở document cũ nhưng là BSON Date trong document mới; repository vẫn chạy, nhưng filter/sort có thể cho kết quả sai.

Kiểm tra tối thiểu:

- Những trường bắt buộc có tồn tại ở dữ liệu cũ, dữ liệu mới và dữ liệu nhập từ tác vụ batch không?
- Các trường tiền, số lượng, ngày giờ và ID có đúng kiểu BSON không? Giá trị `null`, thiếu field và chuỗi rỗng có được xử lý khác nhau đúng không?
- `@Id`, `@MongoId`, `@Field`, `@Version`, converter và enum có cùng hợp đồng với dữ liệu vật lý không? Chuỗi có hình dạng ObjectId có bị chuyển kiểu ngoài ý muốn không?
- Các mảng nhúng có bị tăng không giới hạn, làm document tiến tới giới hạn **16 MiB** không? Sản phẩm/lịch sử đơn có bị nhúng sai vòng đời không?
- Các reference (`customerId`, `productId`) có kiểm tra tồn tại và `tenantId` không? MongoDB không tự cung cấp tính toàn vẹn khóa ngoại cho các trường tham chiếu tùy ý.
- Validator tại database, nếu dùng, có tương thích với dữ liệu lịch sử và mọi luồng ghi (web, job, CLI, import) không?

### Các ràng buộc duy nhất phải được đặt ở MongoDB

Trong `mongosh`, kiểm tra danh sách index thực tế rồi xác nhận các unique index phù hợp:

~~~javascript
db.orders.getIndexes();

// Chạy trong migration/index deployment có kiểm soát sau khi xử lý trùng dữ liệu.
db.orders.createIndex(
  { tenantId: 1, idempotencyKey: 1 },
  { unique: true, name: "uq_orders_tenant_idempotency" }
);

db.products.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true, name: "uq_products_tenant_sku" }
);

db.inventory.createIndex(
  { tenantId: 1, productId: 1 },
  { unique: true, name: "uq_inventory_tenant_product" }
);
~~~

Với ví dụ này, mọi đơn đều **bắt buộc có** `idempotencyKey`. Nếu field là tùy chọn, phải thiết kế lại unique index (chẳng hạn partial index với điều kiện được xác định rõ) và chính sách đối với dữ liệu thiếu/null. Trước khi tạo index, kiểm tra dữ liệu đã trùng vì MongoDB sẽ từ chối tạo unique index không hợp lệ. Trên **sharded collection**, quy tắc về shard key và unique index cần được xác nhận riêng; không được suy rằng unique compound index bất kỳ đều bảo đảm tính duy nhất toàn cục.

Annotation như `@Indexed(unique = true)` thể hiện ý định mapping, nhưng không bảo đảm index đã xuất hiện trên production. Spring Data MongoDB hiện đại không mặc định bật tự động tạo index; việc triển khai index nên thuộc quy trình migration có kiểm soát, với kết quả được xác minh sau khi chạy.

### Kiểm tra validation ở hai tầng

Ở API, dùng Bean Validation để loại đầu vào sai hình dạng. Ở database, cân nhắc JSON Schema validator để ngăn các đường ghi khác bỏ qua ràng buộc cơ bản:

~~~javascript
// Chỉ là ví dụ cho collection đã tồn tại; triển khai sau khi rà soát dữ liệu cũ.
db.runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["tenantId", "status", "totalMinor", "lines"],
      properties: {
        tenantId: { bsonType: "string" },
        status: { enum: ["CREATED", "PAID", "CANCELLED"] },
        totalMinor: { bsonType: ["long", "int"] },
        lines: { bsonType: "array" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Validator minh họa mới chỉ kiểm tra **cấu trúc căn bản**; nó không chứng minh `totalMinor` bằng tổng các dòng, không bảo đảm tham chiếu tồn tại và không thay thế state machine. `validationLevel: "strict"` cùng `validationAction: "error"` có thể khiến ghi/cập nhật vào dữ liệu lịch sử không tương thích bị từ chối, vì vậy phải kiểm tra tác động trước khi bật trên môi trường thật.

## 4. Rà soát ghi đồng thời, idempotency và transaction

### Một lệnh cập nhật nguyên tử trên một document

Mẫu cập nhật tồn kho nên đưa điều kiện “còn đủ” vào **chính lệnh update**. Ví dụ sau dùng `MongoTemplate` và BSON `Document` để minh họa ranh giới kỹ thuật:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public final class InventoryReservation {
    private final MongoTemplate mongo;

    public InventoryReservation(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public boolean reserve(String tenantId, String productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        Query filter = Query.query(Criteria.where("tenantId").is(tenantId)
            .and("productId").is(productId)
            .and("available").gte(quantity));

        Update update = new Update()
            .inc("available", -quantity)
            .inc("reserved", quantity);

        Document updated = mongo.findAndModify(
            filter,
            update,
            FindAndModifyOptions.options().returnNew(true),
            Document.class,
            "inventory"
        );

        return updated != null;
    }
}
~~~

Vì filter và update được xử lý nguyên tử **trên một document**, hai request cạnh tranh không thể cùng trừ số lượng dựa trên một trạng thái tồn kho cũ. Tuy nhiên `false` có thể có nhiều nghĩa: không tồn tại document phù hợp, sai tenant hoặc không đủ hàng. Service cần diễn giải theo hợp đồng nghiệp vụ, không trả thông tin về tài nguyên tenant khác.

**Giới hạn quan trọng:** nếu đơn hàng gồm nhiều sản phẩm, cập nhật nhiều document `inventory` và tạo một `order`, các lệnh riêng lẻ không tự trở thành một giao dịch. Khi nghiệp vụ yêu cầu tất cả cùng commit hoặc rollback, cần `MongoTransactionManager`, `@Transactional` ở đúng service boundary và MongoDB chạy trên replica set/sharded cluster hỗ trợ transaction; đồng thời kiểm thử cả thất bại/commit không chắc chắn. Không dùng transaction dài để chạy backfill hàng triệu document.

### State machine và optimistic locking

Trong một hệ thống đặt hàng, `CREATED → PAID` và `CREATED → CANCELLED` có thể hợp lệ, nhưng `CANCELLED → PAID` phải bị chặn. Một câu `save` bất kỳ cập nhật toàn bộ document theo dữ liệu cũ có thể tạo *lost update*.

- Nếu dùng `@Version` với Spring Data, kiểm tra rằng đường ghi thực sự đi qua API hỗ trợ optimistic locking và dùng acknowledged write concern. Driver trực tiếp hoặc update tùy chỉnh bỏ qua version có thể phá vỡ bảo vệ.
- Với thay đổi trạng thái cụ thể, dùng query có **trạng thái nguồn** trong filter (`tenantId`, `_id`, `status = CREATED`), cập nhật sang đích và kiểm tra số bản ghi được sửa. Không giả định chỉ đọc trạng thái trước rồi ghi sau là đủ.
- Khi phát hiện xung đột, service phải quyết định đọc lại, trả `409 Conflict` hoặc áp dụng lại lệnh theo quy tắc; không retry mù với bản sao cũ.

### Request lặp và kết quả commit chưa rõ

Một client gửi `POST /orders` rồi bị timeout không chứng minh server chưa tạo đơn. Nếu retry sinh ID mới và trừ tồn kho lại, có thể tạo tác dụng phụ trùng. Thiết kế nên có **idempotency key** gắn với người dùng/tenant và request fingerprint:

1. Lấy `idempotencyKey` từ request, kiểm tra định dạng và phạm vi sử dụng; lưu cùng `tenantId` vào record có unique index phù hợp.
2. Chỉ một lần tạo nghiệp vụ được phép chiếm khóa. Nếu cùng khóa xuất hiện lần nữa, đối chiếu fingerprint: cùng nội dung thì trả lại kết quả đã ghi; khác nội dung thì trả lỗi xung đột.
3. Ghi đơn hàng, giữ tồn kho và outbox event trong cùng transaction **nếu** nghiệp vụ cần nhất quán nguyên tử và hạ tầng đáp ứng.
4. Khi client mất phản hồi, truy vấn đối soát theo khóa ổn định trước khi quyết định chạy lại; xử lý `DuplicateKeyException` từ unique index thay vì chỉ `find` kiểm tra rồi `insert`.

Đối với transaction, driver có thể gắn nhãn `TransientTransactionError` hoặc `UnknownTransactionCommitResult`. Hai nhãn dẫn đến cách phục hồi khác nhau: lỗi giao dịch thoáng qua có thể cần chạy lại **toàn bộ transaction**; kết quả commit chưa rõ cần xử lý **retry commit** theo hợp đồng driver/framework. Không tự động lặp lại mọi side effect bên ngoài, chẳng hạn thanh toán, email hoặc gửi webhook.

### Outbox và sự kiện bên ngoài

Nếu tạo đơn cần phát `OrderPlaced` cho hệ thống khác, nên cân nhắc **transactional outbox**: trong transaction, lưu `orders` và một record `outbox_events` có `eventId` duy nhất; publisher gửi event sau commit. Dù vậy, publisher có thể gửi lặp khi broker đã nhận nhưng checkpoint chưa lưu. Consumer phải xử lý idempotent theo `eventId` và logic nghiệp vụ. MongoDB change stream có thể dùng để đánh thức publisher, nhưng change stream chỉ thông báo thay đổi dữ liệu; record outbox mới biểu diễn hợp đồng sự kiện nghiệp vụ.

## 5. Phân quyền theo tenant: phải kiểm tra ngay tại truy vấn

Trong kiến trúc đa tenant, `tenantId` phải được lấy từ **ngữ cảnh xác thực/ủy quyền đáng tin cậy**, không mặc định tin giá trị trong request body hoặc query string. Một endpoint `GET /orders/{id}` chỉ lọc theo `_id` có thể trả dữ liệu thuộc tenant khác, dù `_id` rất khó đoán.

Ví dụ một truy vấn đọc giới hạn tenant:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public final class TenantOrderReader {
    private final MongoTemplate mongo;

    public TenantOrderReader(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    // tenantId phải đến từ security context đã kiểm tra quyền.
    public Document findById(String tenantId, String orderId) {
        Query filter = Query.query(Criteria.where("_id").is(orderId)
            .and("tenantId").is(tenantId));
        return mongo.findOne(filter, Document.class, "orders");
    }
}
~~~

Câu truy vấn trả `null` nếu không tìm thấy document trong tenant được phép. Biên API có thể trả `404 Not Found` theo hợp đồng để tránh tiết lộ sự tồn tại của tài nguyên tenant khác. Ví dụ giả định `_id` lưu dạng BSON string, khớp với `orderId` Java; nếu collection dùng `ObjectId`, phải dùng mapping/kiểu đúng.

Những con đường dễ bị bỏ sót khi rà soát tenant isolation:

| Bề mặt | Kiểm tra bắt buộc |
| --- | --- |
| `findById`, `updateFirst`, `remove` | Mọi thao tác cần xác thực tenant đều lọc theo tenant hoặc qua lớp truy cập đã chứng minh cách ly |
| Query từ repository/`@Query` | Tên method, annotation và custom fragment có chứa tenant predicate phù hợp không? |
| Aggregation `$lookup` | Collection nguồn và các join có thể kết nối dữ liệu khác tenant không? |
| Pagination, export, báo cáo | Filter tenant vẫn được giữ qua sort, `$facet`, `$group` và export batch không? |
| Batch job, message consumer | Mỗi message có ngữ cảnh tenant được xác minh; không tin tenant từ payload thiếu xác thực |
| `@DBRef` / `@DocumentReference` | Reference được nạp có được giới hạn tenant/ủy quyền không? Không dùng lazy load như một biện pháp bảo mật |
| Admin/support endpoint | Quyền xem chéo tenant được cấp rõ, có ghi audit và giới hạn phạm vi |

**Thử nghiệm bắt buộc:** dùng hai tenant có document hợp lệ và cùng các kiểu ID. Người dùng của tenant A phải bị từ chối ở mọi tuyến đọc/ghi/export dữ liệu B, kể cả khi chủ động thay path ID, filter và pagination cursor. Không chỉ kiểm thử trường hợp ID không tồn tại.

## 6. Bảo mật kết nối MongoDB và dữ liệu nhạy cảm

### Xác thực, quyền hạn và kết nối

- Bật cơ chế xác thực phù hợp với môi trường; tài khoản ứng dụng chỉ có quyền cần thiết trên database/collection. Migration, backup và admin nên sử dụng danh tính/role riêng nếu nhiệm vụ cần quyền rộng hơn.
- Sử dụng TLS được xác minh chứng chỉ và tên máy, cấu hình mạng hạn chế truy cập MongoDB chỉ từ thành phần được phép. Không vô hiệu hóa kiểm tra chứng chỉ để “sửa nhanh” lỗi kết nối production.
- Đọc credential từ secret manager/secret injection; không ghi mật khẩu trong repository, file cấu hình commit lên Git, command line hay log. Có quy trình xoay vòng khóa, xử lý secret bị lộ và kiểm tra quyền truy cập.
- Đánh giá lựa chọn lưu trữ mã hóa at-rest, backup encryption và quản lý khóa; với trường dữ liệu cực kỳ nhạy cảm có thể cần client-side field-level encryption hoặc cơ chế bổ sung được thiết kế trước.
- Phân quyền tại API/domain **khác** phân quyền tài khoản MongoDB. Một ứng dụng có quyền đọc collection vẫn phải tự giới hạn tenant, đối tượng và hành động của từng người dùng.

Ví dụ cấu hình Spring Boot qua biến môi trường, tránh chèn credential thật vào tài liệu:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

Giá trị `MONGODB_URI` thực tế phải được secret manager cấp và cấu hình theo topology, TLS, cơ chế xác thực và database phù hợp. Không ghi toàn bộ URI có username/password vào log khi debug startup.

### Bảo vệ trước thao tác truy vấn không mong muốn

Với `MongoTemplate`, `Criteria` và repository, ưu tiên tạo query từ trường hợp lệ và tham số có kiểu. Tránh ghép chuỗi JSON query từ dữ liệu người dùng hay cho client gửi trực tiếp một `Document` chứa toán tử như `$where`, `$ne`, `$regex` hoặc pipeline `$lookup` tùy ý.

Phân trang phải có `limit` tối đa. Filter và sort được lấy từ **allowlist** field cho phép, có timeout phù hợp và giới hạn kích thước request. `maxTimeMS` hay timeout phía client giúp kiểm soát một phần chi phí, nhưng không thay cho giới hạn truy vấn, index và kiểm soát tần suất API.

### Giảm thiểu dữ liệu lộ ra ngoài

- Response chỉ trả các field cần thiết, tránh đưa nguyên document lên API. Dùng DTO/projection và kiểm tra mapping giữa entity, JSON và BSON.
- Log chứa `traceId`, operation, collection, mã lỗi, độ trễ và tenant ID đã được xử lý theo chính sách; không in nguyên document, token, địa chỉ, email hoặc chuỗi kết nối.
- MongoDB profiler/slow query log và monitoring có thể chứa filter/field nhạy cảm; giới hạn quyền truy cập, retention và cách xuất log.
- Tạo bản dữ liệu kiểm thử đã ẩn danh khi sao chép production sang staging; kiểm soát backup, dump và quyền truy cập môi trường thấp hơn.
- TTL và chính sách xóa phải bám theo yêu cầu lưu giữ của từng loại dữ liệu; không áp dụng TTL lên đơn hàng/chứng từ bắt buộc lưu lâu chỉ vì muốn giảm dung lượng.

## 7. Kiểm tra các điều kiện vận hành của MongoDB

Tính đúng dữ liệu còn phụ thuộc vào topology, cấu hình đọc/ghi và trạng thái cluster:

| Hạng mục | Điều cần xác minh trước triển khai |
| --- | --- |
| Topology | Replica set/sharded cluster đúng cấu hình; transaction/change stream được hỗ trợ nếu ứng dụng dùng |
| Read/write concern | Mức xác nhận ghi/đọc tương thích với yêu cầu nhất quán và bền vững; kiểm tra hành vi failover |
| Connection pool | Kích thước pool, thời gian chờ, timeout, số kết nối và cơ chế backpressure hợp lý với tải dự kiến |
| Index | Unique/compound/TTL/partial index tồn tại thực, không bị trùng hoặc lệch collation; không gây tải ghi không chấp nhận được |
| Truy vấn | Truy vấn quan trọng được kiểm tra bằng `explain("executionStats")` trên dữ liệu đủ đại diện |
| Transaction | Phạm vi transaction nhỏ, không có external side effect trước commit, có xử lý lỗi/retry và write concern thích hợp |
| Change stream (nếu dùng) | Resume token/checkpoint, khả năng khôi phục khi token quá cũ, quy tắc xử lý duplicate và thời gian giữ oplog |
| Dung lượng | Có headroom cho dữ liệu, index, tăng trưởng và các thao tác vận hành; theo dõi sức khỏe disk/CPU/memory |
| Backup | Bản sao lưu tự động, mã hóa, quyền truy cập hợp lý và **đã thử restore** |

### `writeConcern` và `readConcern` không phải khẩu hiệu

Một ghi đã được ứng dụng nhận kết quả *acknowledged* chưa chắc có cùng đặc tính bền vững qua mọi kiểu failover. Với dữ liệu quan trọng, cần cân nhắc mức xác nhận như `majority`, chính sách journaling và khả năng chấp nhận độ trễ. `readConcern` và read preference ảnh hưởng dữ liệu đọc được từ node nào và tính nhất quán mà ứng dụng có thể dựa vào; không mặc định mọi read từ secondary đều thấy ngay ghi vừa commit.

Không thể chọn cấu hình tối ưu chỉ bằng một bảng chung. Hãy viết rõ yêu cầu nghiệp vụ: sau khi tạo đơn thành công, client có cần đọc ngay thấy đơn? Dữ liệu có được phép trễ trong báo cáo không? Một lần mất primary có thể chấp nhận mất xác nhận cuối cùng hay không? Sau đó mới đối chiếu với semantics MongoDB thực tế và thử nghiệm failover.

## 8. Kiểm tra hiệu năng, quy mô và reactive access

Các câu lệnh thường phải có bằng chứng đo:

| Query/workload | Ví dụ | Dấu hiệu cần theo dõi |
| --- | --- | --- |
| Đọc đơn theo tenant + ID | `findOne({ tenantId, _id })` | Đúng scope tenant, độ trễ và số document đọc |
| Danh sách đơn theo tenant/status | Filter + sort `createdAt` + limit | Có dùng compound index, không sort/quét quá rộng |
| Lịch sử khách hàng | Filter `tenantId`, `customerId`, sort | Phân trang có index và khóa thứ tự ổn định |
| Giữ tồn kho | Conditional update trên một document | Tỷ lệ xung đột, latency p95/p99, nóng trên một SKU |
| Báo cáo aggregation | `$match`, `$group`, `$lookup` | Memory, spill, số document qua stage, tải đồng thời |
| Bulk import/migration | Update theo batch | Tốc độ ghi, replication lag, kết quả từng batch |

Ví dụ kiểm tra danh sách đơn trong `mongosh`:

~~~javascript
db.orders.find({ tenantId: "shop_a", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(30)
  .explain("executionStats");
~~~

Ghi lại `winningPlan`, `indexName`, `nReturned`, `totalKeysExamined`, `totalDocsExamined`, `executionTimeMillis` và hiện tượng `COLLSCAN`/`SORT`. Không kết luận một kế hoạch có `IXSCAN` là tốt nếu vẫn quét hàng trăm nghìn key để trả 30 kết quả; ngược lại, `COLLSCAN` không phải lúc nào cũng sai ở một collection rất nhỏ.

Đối với **reactive access** (`ReactiveMongoTemplate`, `ReactiveMongoRepository`), cần thêm các kiểm tra: có subscribe đúng vòng đời, có áp dụng backpressure ở consumer, có giới hạn concurrency và buffer, và có xử lý `onError`/timeout phù hợp không? Lặp lại luồng ghi sau `retryWhen` có thể tạo side effect lặp; không dùng retry vô hạn. Với `MongoTemplate` đồng bộ, tránh gọi blocking database operations trực tiếp trên reactive event-loop vì có thể gây nghẽn luồng xử lý.

Khi dùng `@DocumentReference` hoặc `@DBRef`, đếm số truy vấn thực tế cho màn hình danh sách để phát hiện **N+1 query**. Với aggregation, kiểm tra `$lookup` có join đúng tenant, các bước `$match`/`$sort` có tận dụng index và lượng dữ liệu trung gian có giới hạn không.

## 9. Migration, thay đổi schema và đường lui

Một release có thể chứa mã ứng dụng mới, index mới, data migration và thay đổi cách phát event. Chúng không nhất thiết nên chạy cùng một thời điểm. Với thay đổi `customers.name` sang `customers.displayName`, nên đi qua các giai đoạn **expand → backfill → verify → switch → contract**:

1. Triển khai mã mới có thể đọc schema cũ và mới, đồng thời xác định cách mọi writer vẫn tạo dữ liệu tương thích.
2. Chạy migration có phiên bản bằng job/công cụ được kiểm soát; cập nhật theo batch với checkpoint, lock, checksum và khả năng chạy lại an toàn.
3. Kiểm chứng bằng truy vấn độc lập: số document thiếu field mới, document có giá trị xung đột, dữ liệu mẫu và hoạt động của các consumer.
4. Chuyển reader/writer sang schema mới, tiếp tục quan sát độ trễ và lỗi ứng dụng.
5. Chỉ xóa trường hoặc index cũ trong release sau khi mọi consumer đã ngừng phụ thuộc.

Đối với migration phá hủy dữ liệu, **rollback code không đồng nghĩa rollback data**. Một bước xóa field có thể không đảo ngược được nếu không giữ backup/snapshot hoặc dữ liệu gốc. Phải có phương án *roll forward* (migration sửa lỗi), khôi phục đã thử nghiệm hoặc giữ hai schema trong giai đoạn chuyển tiếp.

Sổ migration nên ghi `migrationId`, checksum, trạng thái, thời điểm, số bản ghi ảnh hưởng, checkpoint và thông tin lỗi. Không đánh dấu `APPLIED` trước khi xác minh hậu điều kiện. Nếu các worker tranh nhau chạy, lock phải có cách kiểm soát lease hết hạn và worker cũ tiếp tục ghi.

## 10. Kiểm thử chấp nhận: đi từ lỗi thực tế đến bằng chứng

Môi trường kiểm thử nên dùng MongoDB thực và dữ liệu đại diện. Testcontainers có thể phù hợp cho integration test; transaction/change stream cần cấu hình replica set hoặc sharded cluster hỗ trợ tương ứng. Mock repository đơn thuần không chứng minh được semantics unique index, transaction hoặc hành vi failover.

| Mã test | Cách tạo tình huống | Điều kiện PASS |
| --- | --- | --- |
| T01 | Hai request cùng `(tenantId, idempotencyKey)` với payload giống nhau | Chỉ có một đơn và một reservation; request lặp nhận kết quả tương đương |
| T02 | Cùng idempotency key nhưng payload khác | Trả xung đột, không tạo đơn/giữ hàng mới |
| T03 | Hai tenant có cùng SKU | Unique index cho phép ở tenant khác, từ chối trùng trong cùng tenant |
| T04 | Người dùng tenant A truy vấn ID của tenant B | Không trả/sửa/xóa/export dữ liệu tenant B |
| T05 | Hai luồng giữ 2 sản phẩm khi tồn khả dụng là 3 | Chỉ một lần thành công; tồn kho không âm |
| T06 | Giả lập lỗi giữa bước tạo đơn và cập nhật tồn kho | Transaction rollback hoặc cơ chế bù trừ đã thiết kế giữ invariant |
| T07 | Hai request cập nhật cùng một order version | Phát hiện stale update hoặc từ chối chuyển trạng thái không hợp lệ |
| T08 | Timeout sau khi DB đã commit nhưng trước khi client nhận kết quả | Retry/đối soát không tạo tác dụng phụ trùng |
| T09 | Bulk migration bị dừng giữa chừng rồi khởi động lại | Không bỏ sót/ghi đè, checkpoint và history phản ánh trạng thái thật |
| T10 | Document cũ thiếu field mới, hoặc field có kiểu BSON khác | Converter/reader xử lý đúng hoặc migration phát hiện và chặn release |
| T11 | API nhận filter/operator MongoDB ngoài allowlist | Yêu cầu bị từ chối; không mở rộng query ngoài quyền đã cấp |
| T12 | Secret sai, user DB thiếu quyền hoặc TLS không hợp lệ | Kết nối fail rõ ràng; không log secret, không tự bỏ kiểm tra TLS |
| T13 | Query list/aggregation với nhiều tenant và dữ liệu lớn | Sử dụng index phù hợp, dữ liệu không lẫn tenant, latency trong ngưỡng dự án |
| T14 | Khôi phục một backup vào môi trường tách biệt | Dữ liệu nhất quán, ứng dụng đọc được và thời gian phục hồi đáp ứng mục tiêu |

Với test concurrency, nên đồng bộ thời điểm bắt đầu hai request để tạo tranh chấp thực; chỉ gọi tuần tự hai request không chứng minh được tính an toàn khi chạy đồng thời. Với timeout/failover, cần fault injection hoặc môi trường thử nghiệm phù hợp; chỉ mock một `MongoTimeoutException` chưa chứng minh được dữ liệu đã commit hay chưa.

### Các phép đối soát dữ liệu

Ngoài integration test, chạy các truy vấn kiểm tra dữ liệu được thiết kế theo invariant:

~~~javascript
// Kiểm tra khả năng có nhiều đơn trùng idempotency key trong tenant.
db.orders.aggregate([
  { $group: {
      _id: { tenantId: "$tenantId", key: "$idempotencyKey" },
      n: { $sum: 1 }
  }},
  { $match: { n: { $gt: 1 } } },
  { $limit: 20 }
]);

// Tồn kho âm (trong thiết kế bài tập, phải bằng 0 kết quả).
db.inventory.find({
  $or: [
    { available: { $lt: 0 } },
    { reserved: { $lt: 0 } }
  ]
}).limit(20);
~~~

Nếu collection lớn, truy vấn đối soát phải có kế hoạch thời điểm, index, batch và giới hạn tải. Một truy vấn tổng hợp quét toàn bộ collection chỉ phù hợp để chạy theo kế hoạch trong môi trường có kiểm soát. Điều kiện “không có kết quả sai” cần được kiểm tra trên **toàn phạm vi thực sự yêu cầu**, không chỉ trên 20 document đầu tiên sau khi cắt kết quả lỗi.

## 11. Đo lường, cảnh báo và sổ tay vận hành

Khi triển khai, cần quan sát từ **cả ứng dụng và MongoDB**, có liên hệ qua trace ID hoặc operation context:

| Chỉ số / tín hiệu | Mục đích |
| --- | --- |
| API latency p50/p95/p99, error rate | Phát hiện trải nghiệm suy giảm ngay cả khi DB không báo lỗi |
| MongoDB query duration, slow queries, `docsExamined`/`keysExamined` | Phát hiện truy vấn dùng index kém hoặc thay đổi plan |
| Connection pool wait, active connections, server selection timeout | Phát hiện nghẽn pool hoặc sự cố topology/mạng |
| Duplicate key, optimistic lock, transaction retry | Phân biệt xung đột nghiệp vụ với lỗi hệ thống và retry quá mức |
| Số reservation thành công/thất bại, đơn hàng thiếu liên kết | Phát hiện invariant nghiệp vụ bị đe dọa |
| Replication lag, disk headroom, index size, CPU/I/O | Nhìn thấy nguy cơ về năng lực và độ bền dữ liệu |
| Outbox backlog, publish lag, duplicate handling | Theo dõi sự kiện tích hợp và khả năng phục hồi |
| Backup age, restore drill, migration state | Bảo đảm có khả năng khôi phục và biết release đang ở bước nào |

Mỗi cảnh báo phải có **người phụ trách**, ngưỡng dựa trên SLO thực tế, nơi xem dashboard và runbook xử lý. Ví dụ khi outbox backlog tăng, runbook cần hướng dẫn kiểm tra publisher/broker, checkpoint, retention và cách chạy lại idempotent; không chỉ yêu cầu “restart service”.

### Xác định mục tiêu phục hồi

- **RPO (*Recovery Point Objective*)**: giới hạn lượng dữ liệu tối đa có thể mất khi cần khôi phục theo yêu cầu nghiệp vụ.
- **RTO (*Recovery Time Objective*)**: khoảng thời gian tối đa để khôi phục dịch vụ về trạng thái chấp nhận được.

RPO và RTO phải được chủ sở hữu hệ thống xác nhận và **kiểm chứng bằng restore drill**. Có backup nhưng chưa từng restore thành công không đủ làm bằng chứng sẵn sàng triển khai. Sau restore, cần đối soát dữ liệu và cân nhắc lại thứ tự phục hồi đối với broker, outbox hoặc các hệ thống ngoài MongoDB.

## 12. Đặt tiêu chí GO/NO-GO có thể kiểm chứng

Không có ngưỡng p95, số kết nối hay kích thước index “chuẩn cho mọi hệ thống”. Trong một capstone, nhóm có thể đề xuất ngưỡng **minh họa** (ví dụ p95 API đọc đơn dưới 200 ms ở tải mục tiêu đã nêu) rồi thay bằng SLO do dự án phê duyệt. Điều quan trọng là biết đã đo ở tải nào, dùng dữ liệu nào và cần đáp ứng mục tiêu gì.

### Cổng phát hành đề xuất

| Cổng | Bằng chứng tối thiểu | GO khi | NO-GO khi |
| --- | --- | --- | --- |
| **G1 – Correctness** | Test D1–D8, kiểm thử cạnh tranh và đối soát dữ liệu | Tất cả invariant trọng yếu PASS | Có khả năng tạo đơn trùng, bán vượt tồn hoặc mất dữ liệu chưa xử lý |
| **G2 – Security** | Kiểm thử cross-tenant, kiểm soát role/secret/TLS và log | Không còn đường truy cập trái quyền trọng yếu | Có lộ dữ liệu tenant khác, secret hoặc quyền ghi không kiểm soát |
| **G3 – Migration** | Dry run, số liệu dữ liệu cũ, history/checksum, thử rollback/roll-forward | Migration tái chạy an toàn và dữ liệu tương thích | Migration phá hủy chưa có đường khôi phục hoặc chưa xác minh |
| **G4 – Performance** | Load test và `explain` cho query trọng yếu | Đạt SLO được duyệt ở tải mục tiêu, đủ headroom | Timeout, scan/sort hoặc chi phí ghi vượt ngân sách đã đặt |
| **G5 – Recovery** | Backup hiện hành, restore drill, RPO/RTO đã đo | Khôi phục thành công theo mục tiêu | Không thể khôi phục hoặc thiếu dữ liệu bắt buộc |
| **G6 – Operations** | Dashboard, alert, log an toàn, on-call/runbook | Có người chịu trách nhiệm và quy trình xử lý sự cố | Không phát hiện/ứng phó được sự cố nghiêm trọng |

**Quy tắc quyết định:** Nếu một cổng trọng yếu chưa đạt và không có ngoại lệ rủi ro được chủ sở hữu có thẩm quyền chấp nhận rõ ràng, kết quả là **NO-GO**. Việc đánh dấu “chưa kiểm thử” phải được phân biệt với “PASS”; không suy diễn rằng thiếu bằng chứng đồng nghĩa đã an toàn. Ngoại lệ đã được chấp nhận cần có thời hạn, người chịu trách nhiệm và biện pháp hạn chế rủi ro.

### Mẫu biên bản readiness

~~~text
Release: orders-service <version>
MongoDB deployment: <cluster/topology>, driver/Spring Data: <versions>
Phạm vi: <API, collections, migrations, indexes, integrations>
Thời điểm đánh giá: <UTC time>

G1 Correctness: PASS | FAIL | NOT TESTED  Evidence: <link/test id>
G2 Security:    PASS | FAIL | NOT TESTED  Evidence: <link/test id>
G3 Migration:   PASS | FAIL | NOT TESTED  Evidence: <link/job id>
G4 Performance: PASS | FAIL | NOT TESTED  Evidence: <dashboard/report>
G5 Recovery:    PASS | FAIL | NOT TESTED  Evidence: <restore drill>
G6 Operations:  PASS | FAIL | NOT TESTED  Evidence: <runbook/alert>

Open risks: <issue, severity, owner, deadline>
Decision: GO | NO-GO
Approved by: <responsible owner>
Rollback/roll-forward plan: <documented procedure>
~~~

Không ghi thông tin bí mật, credential hoặc dữ liệu người dùng thật vào biên bản. Nên dùng đường dẫn tới bằng chứng kiểm thử/giám sát được phân quyền phù hợp.

## 13. Runbook triển khai và khôi phục

Một kịch bản phát hành có thể theo trình tự:

1. **Trước deploy:** xác nhận bản sao lưu gần nhất và restore drill, đánh giá rủi ro migration, kiểm tra index/validator đang tồn tại, đo baseline truy vấn và cảnh báo.
2. **Expand:** triển khai mã tương thích schema cũ/mới, chuẩn bị index theo kế hoạch, bảo đảm mọi writer tuân thủ hợp đồng dữ liệu.
3. **Migration:** chạy job có version/lock/checkpoint, quan sát tiến độ, xác minh số bản ghi và invariant trước khi chuyển tiếp.
4. **Triển khai theo đợt:** rollout một phần traffic/canary nếu nền tảng hỗ trợ; giám sát p95/p99, error rate, pool wait, conflict và backlog tích hợp.
5. **Xác minh hậu deploy:** chạy smoke test theo tenant, API tạo/đọc đơn, cạnh tranh tối thiểu, kiểm tra schema/index và số liệu nghiệp vụ trọng yếu.
6. **Kích hoạt hoặc dừng:** tiếp tục rollout khi cổng đáp ứng; nếu vi phạm cổng, dừng mở rộng, giảm traffic và áp dụng phương án khôi phục thích hợp.
7. **Contract sau ổn định:** chỉ dọn field/index cũ ở release riêng sau khi xác minh không còn consumer phụ thuộc.

Phương án “rollback” cần nêu **cái gì có thể đảo ngược và cái gì không**. Triển khai lại phiên bản ứng dụng cũ chỉ an toàn khi nó còn đọc được schema đã thay đổi; một transaction đã commit, sự kiện đã gửi hoặc thanh toán đã xử lý ở hệ thống ngoài có thể cần thao tác bù/đối soát chứ không thể đảo ngược bằng deploy code cũ. Chỉ khôi phục backup production khi đã đánh giá tác động tới các ghi mới hơn bản backup và hệ thống phụ thuộc.

## 14. Bài tập nộp cuối capstone

Người học chuẩn bị một **gói bằng chứng triển khai** cho dịch vụ đặt hàng gồm:

1. Sơ đồ luồng request và collection, bảng D1–D8 cùng nơi cưỡng chế và test ID tương ứng.
2. Mẫu BSON, mapping Spring Data, danh sách index thực tế và kết quả `explain("executionStats")` cho các query quan trọng.
3. Kết quả concurrency/idempotency/transaction test, bao gồm ít nhất một trường hợp request lặp và một lỗi giữa quy trình nhiều document.
4. Báo cáo bảo mật về tenant isolation, tài khoản MongoDB, TLS, secrets, dữ liệu nhạy cảm và kiểm tra log.
5. Kế hoạch migration có version, điều kiện rollback/roll-forward và bằng chứng đối soát dữ liệu cũ.
6. Báo cáo tải, SLO, cảnh báo, RPO/RTO và thử restore, kèm quyết định GO/NO-GO có chữ ký người chịu trách nhiệm.

### Thang đánh giá gợi ý

| Nhóm | Tỷ trọng | Tiêu chí |
| --- | ---: | --- |
| Tính đúng dữ liệu | 35% | Invariant rõ, cưỡng chế ở đúng tầng, kiểm thử concurrency và idempotency đáng tin cậy |
| Bảo mật | 25% | Chặn cross-tenant, quyền tối thiểu, TLS/secret an toàn, không lộ dữ liệu trong API/log |
| Sẵn sàng triển khai | 25% | Migration, backup/restore, quan sát, cổng GO/NO-GO và runbook có thể vận hành |
| Bằng chứng và khả năng giải thích | 15% | Có số liệu, query thực tế, test và giải thích đánh đổi phù hợp với hệ thống |

Một bản thiết kế đạt yêu cầu phải chỉ ra được **lỗi nào được chặn bằng ràng buộc MongoDB, lỗi nào cần quy tắc ở Spring Data/domain service và lỗi nào cần quy trình vận hành**. `MongoTemplate`, repository, transaction, index và reactive API đều hữu ích trong phạm vi của chúng; tính sẵn sàng triển khai chỉ được chứng minh khi các quyết định ấy được kiểm tra đồng bộ với dữ liệu, bảo mật và điều kiện phục hồi thực tế.
