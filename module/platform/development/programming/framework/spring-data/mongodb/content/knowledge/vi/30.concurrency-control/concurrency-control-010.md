# Giới hạn version khi cập nhật trực tiếp hoặc ghi hàng loạt

## 1. Bài toán: một document, hai luồng cập nhật đồng thời

Trong hệ thống quản lý đơn hàng dùng **Spring Data MongoDB**, một document đơn hàng có thể được cập nhật bởi nhiều luồng: nhân viên xác nhận đơn, tác vụ giữ hàng, webhook thanh toán và một job đồng bộ chạy theo lô.

Giả sử hai worker đọc cùng một trạng thái:

```javascript
{
  _id: "ord-101",
  tenant_id: "tenant-A",
  status: "PENDING",
  reserved_units: NumberLong("2"),
  version: NumberLong("7")
}
```

Sau khi đọc:

```text
T1: Worker A đọc order ord-101, version=7.
T2: Worker B đọc order ord-101, version=7.
T3: A xác nhận đơn và ghi status=CONFIRMED.
T4: B ghi trạng thái cũ/giá trị mới theo dữ liệu đã đọc.
```

Nếu hai luồng chỉ cập nhật theo `_id`, một thao tác có thể **ghi đè kết quả của thao tác kia** (*lost update*) hoặc áp dụng quyết định kinh doanh dựa trên trạng thái không còn đúng.

Spring Data MongoDB hỗ trợ **optimistic locking** bằng `@Version` khi lưu entity qua những API phù hợp. Nhưng khi dùng **`MongoTemplate.updateFirst(...)`**, `findAndModify(...)`, **`BulkOperations.updateOne(...)`** hoặc raw MongoDB Driver, ta phải hiểu chính xác việc kiểm tra version nào được thực hiện tự động và việc nào phải làm **tường minh**.

**Chủ đề thuộc chương Kiểm soát đồng thời** của module **SPRING_DATA_MONGODB**: kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository; áp dụng query, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng.

Mục tiêu của bài:

- Dùng `expectedVersion` để ngăn cập nhật dựa trên bản ghi cũ.
- Hiểu khác biệt giữa **tăng số version** và **kiểm tra version trước khi ghi**.
- Thiết kế **compare-and-set (CAS)** với `Query` + `Update` trong một lệnh nguyên tử.
- Đưa CAS vào từng operation của một **bulk write** mà không nhầm tổng số thành công với kết quả từng dòng.
- Phân biệt **version conflict**, **document không tồn tại**, **bị từ chối do điều kiện nghiệp vụ** và **kết quả chưa rõ do lỗi mạng**.
- Biết khi nào dùng repository `save`, `findAndModify`, transaction, idempotency key và retry.

**Nguyên tắc chính:** với cập nhật trực tiếp, filter phải chứa **ID + version kỳ vọng** (và tenant/quy tắc nghiệp vụ phù hợp), trong khi update phải **tăng version ngay trong cùng thao tác nguyên tử**. Chỉ tăng version mà không so sánh version cũ **không ngăn lost update**.

## 2. Công thức compare-and-set trên MongoDB

Giả sử document đang có `version = 7`. Worker đưa ra yêu cầu “đổi trạng thái nếu bản ghi vẫn ở version 7”:

```javascript
db.orders.updateOne(
  {
    _id: "ord-101",
    tenant_id: "tenant-A",
    version: NumberLong("7"),
    status: "PENDING"
  },
  {
    $set: {
      status: "CONFIRMED",
      last_operation_id: "confirm:ord-101:v7"
    },
    $inc: {
      version: NumberLong("1")
    },
    $currentDate: {
      updated_at: true
    }
  }
);
```

Nếu query khớp một document, MongoDB thực thi cập nhật trên document đó **nguyên tử**; trạng thái trở thành `CONFIRMED` và version tăng thành 8 trong cùng một thao tác.

Nếu một worker khác đã tăng version lên 8 trước đó, filter `version:7` không còn khớp và lệnh **không** ghi đè trạng thái mới.

### 2.1. Bất biến cần duy trì

```text
Precondition:
    document.id      == orderId
    document.tenant   == trustedTenantId
    document.version  == expectedVersion
    document.status   == PENDING

Atomic effect nếu khớp:
    status    := CONFIRMED
    version   := version + 1
    updatedAt := serverTime
    marker    := operationId
```

Đây là CAS về mặt nghiệp vụ: chỉ thay đổi khi dữ liệu còn ở trạng thái kỳ vọng.

### 2.2. Không dùng read-check-write bằng ba bước không nguyên tử

Một triển khai nguy hiểm:

```java
OrderDocument current =
    template.findById(id, OrderDocument.class);

// Kiểm tra version trong Java.
if (current.version().equals(expectedVersion)) {
    // Có thể bị worker khác ghi xen vào trước lệnh này.
    template.updateFirst(
        Query.query(Criteria.where("id").is(id)),
        new Update().set("status", "CONFIRMED"),
        OrderDocument.class
    );
}
```

Khoảng thời gian giữa lần đọc và lần update là **race window**. Thay vì kiểm tra version chỉ ở Java, phải đưa điều kiện version vào **filter của lệnh ghi**.

### 2.3. Một document nguyên tử không có nghĩa cả bulk là transaction

Mỗi `updateOne` trên một document bảo vệ tính nguyên tử của chính lệnh đó. Một bulk gồm 100 `updateOne` trên 100 document **không tự bảo đảm** tất cả cùng thành công hoặc cùng rollback. Phạm vi atomicity và quy trình retry phải được chọn riêng.

## 3. Mô hình entity với `@Version` và mapping BSON

Ta dùng entity immutable kiểu Java record:

```java
import java.time.Instant;

import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record OrderDocument(
    @MongoId(FieldType.STRING)
    String id,

    @Field("tenant_id")
    String tenantId,

    String status,

    @Field("reserved_units")
    long reservedUnits,

    @Version
    Long version,

    @Field("updated_at")
    Instant updatedAt,

    @Field("last_operation_id")
    String lastOperationId,

    @Field("last_operation_hash")
    String lastOperationHash
) {}
```

Các điểm quan trọng:

| Java property | BSON field | Ý nghĩa |
| --- | --- | --- |
| `id` | `_id` | Khóa document ổn định |
| `tenantId` | `tenant_id` | Điều kiện phân vùng và phân quyền |
| `reservedUnits` | `reserved_units` | Số lượng đã giữ; cập nhật có điều kiện |
| `version` | `version` | Version dùng cho optimistic locking |
| `updatedAt` | `updated_at` | Thời điểm ghi, không thay thế version |
| `lastOperationId` | `last_operation_id` | Marker phục vụ đối soát retry |
| `lastOperationHash` | `last_operation_hash` | Fingerprint payload cho cùng operationId |

Chọn `@Version Long` (wrapper) để có trạng thái `null` trước lần insert. Với Spring Data, giá trị version ban đầu cho wrapper số thường bắt đầu từ **0**; primitive version thường dùng giá trị khởi tạo khác, chẳng hạn **1**. Các quy tắc version initialization phải được kiểm tra bằng test với phiên bản thực tế.

Không gán `Instant.now()` làm “version thay thế”: timestamp có thể trùng độ phân giải, chịu clock skew hoặc được tính trước khi lệnh ghi. Version số nguyên và điều kiện CAS thể hiện rõ thứ tự thay đổi trên một document.

### 3.1. Mapping theo tên property Java

Khi dùng `MongoTemplate` với `OrderDocument.class`:

```java
Criteria.where("tenantId").is("tenant-A")
    .and("version").is(7L);
```

Spring Data chuyển tên Java `tenantId` sang BSON `tenant_id`. Khi dùng raw driver hay `mongosh` phải viết tên BSON thật.

Không dùng `Criteria.where("tenantId")` trong raw MongoDB shell rồi mong `@Field` của Java tự tác động lên command đó.

## 4. `@Version` bảo vệ `save(...)` như thế nào?

Khi dùng repository hoặc `MongoTemplate.save(...)` với entity có `@Version`, Spring Data MongoDB thực hiện optimistic locking cho đường lưu phù hợp: truy vấn cập nhật dựa trên **ID và version hiện tại**, thay đổi version khi ghi và phát hiện trường hợp không còn document khớp.

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {}
```

Ví dụ hai luồng lưu entity đã đọc:

```java
OrderDocument a = repository.findById("ord-101")
    .orElseThrow();
OrderDocument b = repository.findById("ord-101")
    .orElseThrow();

// Ở đây minh họa tạo bản ghi mới với cùng ID và version.
OrderDocument changedA = new OrderDocument(
    a.id(), a.tenantId(), "CONFIRMED",
    a.reservedUnits(), a.version(),
    a.updatedAt(), a.lastOperationId(), a.lastOperationHash()
);

OrderDocument changedB = new OrderDocument(
    b.id(), b.tenantId(), "CANCELLED",
    b.reservedUnits(), b.version(),
    b.updatedAt(), b.lastOperationId(), b.lastOperationHash()
);

OrderDocument savedA = repository.save(changedA);

// Nếu cả hai ban đầu đọc version 7,
// save(changedB) phải gặp optimistic locking conflict.
repository.save(changedB);
```

Khi version đã bị thay đổi, đường `save` phù hợp sẽ ném **`OptimisticLockingFailureException`** thay vì âm thầm ghi đè entity cũ.

**Điều kiện bắt buộc:** dùng **acknowledged write concern** để client nhận được kết quả ghi cần thiết cho kiểm tra optimistic locking. Với `w:0`/unacknowledged writes, ứng dụng không có bằng chứng đáng tin để phát hiện “matched=0”; tránh cấu hình đó cho dữ liệu cần CAS.

### 4.1. `@Version` không phải khóa database

Optimistic locking:

- Không giữ một mutex bên ngoài document trước khi sửa.
- Không ngăn worker khác **đọc** cùng version.
- Không tự bảo đảm mọi quy tắc nghiệp vụ đa document.
- Không biến `saveAll(...)` trên nhiều document thành một transaction.
- Không bảo vệ lệnh raw driver/`BulkOperations` chỉ vì entity có annotation.

Nó thực sự hữu ích khi **mọi đường ghi có liên quan** tuân thủ cùng quy tắc version.

### 4.2. Vì sao `save(...)` phù hợp với trường hợp nhất định?

`save` thích hợp khi ứng dụng đã đọc và sửa **cả aggregate/entity**, cần mapping/callbacks/versioning theo contract của Spring Data. Khi chỉ cần thay một field hoặc thực hiện `$inc` nguyên tử, dùng direct update với CAS thường rõ ràng và tránh truyền cả entity qua mạng.

Lựa chọn đúng phụ thuộc tính chất dữ liệu, không phải cố ép tất cả vào `save` hay tất cả vào raw update.

## 5. Cập nhật trực tiếp: version có thể tăng nhưng chưa chắc được so khớp

Một điểm rất dễ nhầm trong Spring Data MongoDB: các thao tác `updateFirst(...)`/`updateMulti(...)` dùng `Update` không nhận một **entity snapshot** hoàn chỉnh để Spring Data tự biết version mà caller đã đọc.

Ở một số dòng Spring Data MongoDB hiện đại, property có `@Version` được **tự tăng sau update nếu nó chưa xuất hiện trong định nghĩa `Update`**. Nhưng cơ chế tăng version này **không tự bổ sung điều kiện so sánh `expectedVersion` vào query của bạn**.

Ví dụ nguy hiểm:

```java
Query query = Query.query(
    Criteria.where("id").is("ord-101")
);

Update update = new Update()
    .set("status", "CONFIRMED");

template.updateFirst(
    query, update, OrderDocument.class
);
```

Ngay cả khi mapping infrastructure tăng field `version` khi thực thi, filter chỉ dựa vào ID. Hai worker đọc cùng dữ liệu cũ vẫn có thể ghi quyết định xung đột theo ID, vì **không có so sánh version kỳ vọng**.

**Phân biệt hai chức năng:**

| Chức năng | Nó giải quyết điều gì? |
| --- | --- |
| `$inc: {version:1}` | Đánh dấu document đã đổi sang revision mới |
| Filter `version == expectedVersion` | Ngăn một request cũ ghi lên revision đã thay đổi |
| Cả hai trong **cùng một updateOne** | Tạo cơ chế CAS có thể kiểm tra |
| `@Version` khi `save(...)` | Spring Data thực hiện optimistic locking của entity theo đường API phù hợp |

Để code cập nhật trực tiếp dễ kiểm chứng và độc lập với việc Spring Data có tự thêm bước increment hay không, bài sẽ **tăng version tường minh bằng `Update.inc("version",1L)`** và luôn đặt `expectedVersion` trong filter. Khi đã tự cập nhật version trong `Update`, không nên cộng lại lần nữa.

## 6. `MongoTemplate.updateFirst(...)`: CAS thực sự trong một lệnh

### 6.1. Command và kết quả

```java
public record ConfirmOrderCommand(
    String orderId,
    String tenantId,
    long expectedVersion,
    String operationId,
    String payloadHash
) {}
```

Ví dụ service cập nhật trực tiếp:

```java
import com.mongodb.client.result.UpdateResult;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class OrderCasService {

    private final MongoTemplate template;

    public OrderCasService(MongoTemplate template) {
        this.template = template;
    }

    public boolean confirm(ConfirmOrderCommand command) {
        if (command.orderId() == null
                || command.orderId().isBlank()
                || command.tenantId() == null
                || command.tenantId().isBlank()
                || command.expectedVersion() < 0
                || command.operationId() == null
                || command.operationId().isBlank()
                || command.payloadHash() == null
                || command.payloadHash().isBlank()) {
            throw new IllegalArgumentException(
                "Thông tin CAS không hợp lệ"
            );
        }

        Query filter = Query.query(
            Criteria.where("id").is(command.orderId())
                .and("tenantId").is(command.tenantId())
                .and("version").is(command.expectedVersion())
                .and("status").is("PENDING")
        );

        Update update = new Update()
            .set("status", "CONFIRMED")
            .set("lastOperationId", command.operationId())
            .set("lastOperationHash", command.payloadHash())
            .inc("version", 1L)
            .currentDate("updatedAt");

        UpdateResult result = template.updateFirst(
            filter, update, OrderDocument.class
        );

        if (!result.wasAcknowledged()) {
            throw new IllegalStateException(
                "Không có acknowledgement cho cập nhật CAS"
            );
        }

        return result.getMatchedCount() == 1L;
    }
}
```

Tại sao query dùng `and("status").is("PENDING")`? Version bảo vệ khỏi stale writes, còn state predicate bảo vệ **quy tắc nghiệp vụ** “chỉ xác nhận đơn đang chờ”. Một lệnh khác với `expectedVersion` đúng nhưng status `CANCELLED` không được xác nhận.

Tại sao `Update.inc("version",1L)` phải nằm trong cùng update? Nếu chỉ `$set` trạng thái rồi gửi riêng lệnh tăng version, sẽ có khoảng giữa hai lệnh; một writer khác có thể đọc/ghi trong lúc version chưa phản ánh thay đổi.

### 6.2. Không kết luận `matchedCount=0` chính xác là lỗi nào

Khi `getMatchedCount()==0`, có nhiều khả năng:

- `orderId` chưa tồn tại hoặc đã bị xóa.
- `tenantId` không đúng hoặc người gọi không được phép xem.
- `status` không còn `PENDING`.
- `version` đã thay đổi bởi writer khác.
- Lệnh trước **đã thực hiện** và client gửi lại với expectedVersion cũ.

Vì vậy, `false` trong ví dụ là “không có document nào khớp toàn bộ precondition”, **không phải bằng chứng chắc chắn về một version conflict**. Service/application layer phải phân loại phù hợp sau một lần đọc đối soát, đồng thời không để thông báo lỗi lộ trạng thái đơn của tenant khác.

### 6.3. Phân biệt `matchedCount` và `modifiedCount`

`getMatchedCount()` cho biết có document khớp filter. `getModifiedCount()` phản ánh số document có thay đổi được server báo. Trong ví dụ, nếu khớp thì `$inc(version,1)` làm document thay đổi nên modified thường là 1; tuy nhiên hợp đồng CAS nên ưu tiên kiểm tra **matchedCount** và trạng thái thật khi cần.

Nếu update chỉ `$set` cùng giá trị cũ mà không tăng version, matched có thể 1 còn modified 0. Không dùng `modifiedCount==0` như bằng chứng mặc định rằng version đã xung đột.

## 7. `findAndModify(...)`: CAS và nhận document sau cập nhật

Nếu caller cần biết **newVersion** ngay sau khi ghi, có thể dùng `findAndModify` với `returnNew(true)`:

```java
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public OrderDocument confirmAndReturn(
    MongoTemplate template,
    ConfirmOrderCommand command
) {
    Query filter = Query.query(
        Criteria.where("id").is(command.orderId())
            .and("tenantId").is(command.tenantId())
            .and("version").is(command.expectedVersion())
            .and("status").is("PENDING")
    );

    Update update = new Update()
        .set("status", "CONFIRMED")
        .set("lastOperationId", command.operationId())
        .set("lastOperationHash", command.payloadHash())
        .inc("version", 1L)
        .currentDate("updatedAt");

    return template.findAndModify(
        filter,
        update,
        FindAndModifyOptions.options().returnNew(true),
        OrderDocument.class
    );
}
```

Nếu khớp, method trả entity sau cập nhật (ví dụ version 8). Nếu không khớp, kết quả có thể là `null`. Hãy xử lý `null` như **không thỏa toàn bộ điều kiện**, không tự đồng nhất với version conflict.

Cơ chế này hữu ích khi cần:

- Biết version mới cho ETag/optimistic concurrency token.
- Trả về document đã cập nhật mà không gọi `findById` lần thứ hai.
- Gắn marker operation và nhận trạng thái sau ghi.

Tuy nhiên, `findAndModify` cũng có thể gặp **ambiguous outcome** khi mất kết nối sau khi server đã ghi. Việc caller không nhận entity **không chứng minh** server chưa cập nhật. Cần idempotency/đối soát theo yêu cầu nghiệp vụ.

## 8. Tại sao phải giữ điều kiện nghiệp vụ trong CAS?

Version là cách phát hiện thay đổi, không phải nguồn chân lý duy nhất của logic.

Ví dụ giữ thêm 3 sản phẩm nếu vẫn còn số lượng khả dụng:

```javascript
db.inventory.updateOne(
  {
    _id: "sku-101",
    version: NumberLong("7"),
    available: { $gte: 3 }
  },
  {
    $inc: {
      available: NumberLong("-3"),
      reserved: NumberLong("3"),
      version: NumberLong("1")
    }
  }
);
```

Ở đây update có ba mục tiêu:

1. Không chấp nhận một request dựa trên version cũ.
2. Không giữ hàng vượt số lượng hiện có.
3. Thực hiện cộng/trừ số lượng **trong một atomic update**.

Nếu chỉ kiểm tra `available>=3` **trong Java** rồi update theo version, vẫn nên đưa điều kiện số lượng vào filter: nghiệp vụ phải được bảo vệ tại thời điểm server thực hiện lệnh.

### 8.1. `$inc` nguyên tử nhưng không tự bảo vệ khỏi retry trùng

`$inc` trên một document là nguyên tử, song nếu client timeout sau khi MongoDB đã tăng `reserved` rồi job gửi lại yêu cầu với **version mới** mà không có operationId cố định, cùng hiệu ứng có thể được áp dụng hai lần.

Version giải quyết **cạnh tranh giữa các phiên bản**; operationId/ledger giải quyết **định danh một hiệu ứng nghiệp vụ khi retry**. Hai cơ chế bổ sung cho nhau, không thay thế nhau.

## 9. `@Version` và `BulkOperations`: chỗ nào không tự động?

Spring Data MongoDB có:

```java
template.bulkOps(
    BulkOperations.BulkMode.UNORDERED,
    OrderDocument.class
);
```

`BulkOperations` ghép nhiều lệnh ghi thành một bulk. Các đường bulk **không được kỳ vọng cung cấp optimistic locking tự động giống `repository.save(entity)`**: Spring Data không có một entity snapshot/version riêng cho từng `Update` để tự suy ra version người dùng đã đọc, và một bulk cũng không trả đủ kết quả per-operation cho tất cả update không khớp.

Vì vậy, **không** viết bulk theo ID đơn thuần rồi cho rằng `@Version` trên entity bảo vệ tất cả update.

Ví dụ **nguy hiểm**:

```java
BulkOperations bulk = template.bulkOps(
    BulkOperations.BulkMode.UNORDERED,
    OrderDocument.class
);

for (ConfirmOrderCommand command : commands) {
    bulk.updateOne(
        Query.query(
            Criteria.where("id").is(command.orderId())
        ),
        new Update().set("status", "CONFIRMED")
    );
}

bulk.execute();
```

Đoạn trên thiếu tenant, expectedVersion và precondition status; mỗi lệnh có thể ghi dựa trên trạng thái cũ. Việc entity có `@Version` **không đủ** để biến query trên ID thành CAS.

### 9.1. Cách đúng: CAS bên trong từng `updateOne`

```java
Query filter = Query.query(
    Criteria.where("id").is(command.orderId())
        .and("tenantId").is(command.tenantId())
        .and("version").is(command.expectedVersion())
        .and("status").is("PENDING")
);

Update update = new Update()
    .set("status", "CONFIRMED")
    .set("lastOperationId", command.operationId())
    .set("lastOperationHash", command.payloadHash())
    .inc("version", 1L)
    .currentDate("updatedAt");

bulk.updateOne(filter, update);
```

Mỗi operation là một **atomic conditional update** có precondition và version increment riêng. Cách này dùng được trong bulk vì nó dựa trên semantics MongoDB `updateOne`, không dựa vào việc Spring Data tự thêm optimistic lock.

## 10. Dịch vụ bulk với manifest và validation rõ ràng

Giả sử một job xác nhận nhiều đơn. Dùng `List<ConfirmOrderCommand>` từ một manifest có ID, expectedVersion và operationId ổn định:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import com.mongodb.bulk.BulkWriteResult;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public final class OrderBulkCasWriter {

    private final MongoTemplate template;

    public OrderBulkCasWriter(MongoTemplate template) {
        this.template = template;
    }

    public BulkWriteResult confirmMany(
        List<ConfirmOrderCommand> commands
    ) {
        if (commands == null || commands.isEmpty()) {
            throw new IllegalArgumentException(
                "Danh sách command rỗng"
            );
        }

        Set<String> touchedOrders = new HashSet<>();
        Set<String> operationIds = new HashSet<>();

        BulkOperations bulk = template.bulkOps(
            BulkOperations.BulkMode.UNORDERED,
            OrderDocument.class
        );

        for (ConfirmOrderCommand c : commands) {
            if (c.orderId() == null || c.orderId().isBlank()
                    || c.tenantId() == null
                    || c.tenantId().isBlank()
                    || c.expectedVersion() < 0
                    || c.operationId() == null
                    || c.operationId().isBlank()
                    || c.payloadHash() == null
                    || c.payloadHash().isBlank()) {
                throw new IllegalArgumentException(
                    "Command không hợp lệ"
                );
            }

            // Không gửi hai bản cập nhật cho cùng một order
            // trong một unordered bulk.
            String orderKey = c.tenantId() + ":" + c.orderId();
            if (!touchedOrders.add(orderKey)
                    || !operationIds.add(c.operationId())) {
                throw new IllegalArgumentException(
                    "Order/operationId trùng trong một bulk"
                );
            }

            Query filter = Query.query(
                Criteria.where("id").is(c.orderId())
                    .and("tenantId").is(c.tenantId())
                    .and("version").is(c.expectedVersion())
                    .and("status").is("PENDING")
            );

            Update update = new Update()
                .set("status", "CONFIRMED")
                .set("lastOperationId", c.operationId())
                .set("lastOperationHash", c.payloadHash())
                .inc("version", 1L)
                .currentDate("updatedAt");

            bulk.updateOne(filter, update);
        }

        return bulk.execute();
    }
}
```

Tại sao từ chối hai command cùng order trong một **unordered bulk**? Vì thứ tự thực thi không được bảo đảm. Dù có CAS, nếu hai command cùng expectedVersion, **chỉ một** có thể khớp, nhưng business không thể dựa vào vị trí trong input để xác định command nào thắng. Hãy dedupe, hợp nhất, tuần tự hóa theo aggregate ID hoặc xử lý theo một chính sách tường minh trước khi tạo bulk.

**Vẫn còn giới hạn:** mã ở trên chỉ gửi CAS và trả `BulkWriteResult`. Nó **chưa** xây hệ thống đối soát từng operation, bền vững hóa manifest hay đưa dữ liệu vào dead-letter queue. Những việc đó là trách nhiệm tầng orchestration.

## 11. `ORDERED` và `UNORDERED`: không đổi bản chất CAS

| Tiêu chí | `ORDERED` | `UNORDERED` |
| --- | --- | --- |
| Thứ tự logic của lệnh | Theo thứ tự đầu vào | Không bảo đảm thứ tự |
| Khi có **write error** | Thường dừng tại lỗi đầu | Có thể tiếp tục những operation khác |
| Khi CAS **matchedCount=0** | Không nhất thiết là write error; có thể tiếp tục | Tương tự |
| Các cập nhật đã thành công | Không tự rollback ngoài transaction | Không tự rollback ngoài transaction |
| Mất phản hồi giữa chừng | Có thể không biết lệnh nào đã ghi | Có thể không biết lệnh nào đã ghi |
| Phù hợp | Các operation phụ thuộc trật tự hoặc cần dừng sớm | Các operation độc lập sau khi dedupe |

**Version mismatch thông thường không làm MongoDB ném duplicate key hoặc optimistic locking exception trong một lệnh `updateOne`.** Nó tạo kết quả **không khớp document**, tức matched count của operation đó bằng 0. Trong bulk, đây thường không được liệt kê như một `writeError` theo operation index.

Đừng mong một bulk `ORDERED` sẽ dừng ngay ở version conflict nếu chỉ dùng filter `version`: update không khớp filter là một lệnh hợp lệ theo MongoDB, không phải lỗi ghi buộc bulk dừng.

### 11.1. Bulk có thể bị chia thành nhiều lệnh vật lý

Driver/server có giới hạn số thao tác và kích thước BSON cho mỗi batch, nên một bulk lớn có thể được chia thành các command nhỏ hơn. Điều này càng làm việc suy luận “mọi update đã chạy liền một lúc như một transaction” trở nên sai.

Thiết kế manifest/checkpoint và idempotency phải hoạt động cả khi job bị ngắt giữa những phần bulk thực tế.

## 12. `BulkWriteResult`: tổng số không phải kết quả của từng order

Sau một bulk acknowledged:

```java
BulkWriteResult result = writer.confirmMany(commands);

if (!result.wasAcknowledged()) {
    throw new IllegalStateException(
        "Không có acknowledgement cho bulk CAS"
    );
}

int matched = result.getMatchedCount();
int modified = result.getModifiedCount();
int inserted = result.getInsertedCount();

System.out.printf(
    "matched=%d modified=%d inserted=%d%n",
    matched, modified, inserted
);
```

Giả sử gửi ba update với ba order khác nhau:

```text
Index 0: ord-A expectedVersion=7
Index 1: ord-B expectedVersion=4
Index 2: ord-C expectedVersion=9

BulkWriteResult:
  matchedCount = 2
  modifiedCount = 2
```

Không thể kết luận từ hai count đó rằng **ord-B** bị conflict hay **ord-C** bị conflict. `BulkWriteResult` chứa **các số đếm tổng hợp**, không có danh sách ID cho mọi `updateOne` thành công và thất bại do không khớp.

`getUpserts()` có thể mang index/ID của những operation upsert tạo document mới, nhưng **không** là một bảng trạng thái đầy đủ cho mọi conditional update.

### 12.1. Server write errors khác CAS không khớp

Một `MongoBulkWriteException` (hoặc exception đã được Spring Data dịch) có thể cung cấp danh sách `writeErrors` với **index** của những lệnh gặp write error, chẳng hạn vi phạm schema, duplicate key hoặc lỗi dữ liệu.

Nhưng `matchedCount=0` của một `updateOne` có filter version **không nhất thiết tạo một writeError**. Đừng chỉ xử lý `catch` rồi kết luận những lệnh không vào `catch` đều CAS thành công.

### 12.2. Không suy kết quả theo “matchedCount đầu tiên” của ordered bulk

Kể cả ở mode `ORDERED`, con số matched là **tổng**. Nếu operation index 0 không khớp version nhưng operation index 1 khớp, result tổng matched=1 không nói rằng operation 0 thành công. Chỉ khi API trả dữ liệu chi tiết theo ID hoặc có đối soát mới biết được.

## 13. Đối soát kết quả từng operation sau bulk

Với nghiệp vụ cần biết **mỗi order đã được xác nhận chưa**, một lớp orchestrator có thể duy trì manifest:

```json
{
  "batchId": "confirm-orders-2026-11-20",
  "operations": [
    {
      "operationId": "confirm:ord-A:v7",
      "orderId": "ord-A",
      "expectedVersion": 7,
      "desiredStatus": "CONFIRMED",
      "payloadHash": "hash-A"
    },
    {
      "operationId": "confirm:ord-B:v4",
      "orderId": "ord-B",
      "expectedVersion": 4,
      "desiredStatus": "CONFIRMED",
      "payloadHash": "hash-B"
    }
  ]
}
```

Các giá trị hash ở đây chỉ là nhãn minh họa. Trong hệ thống thật, phải dùng hash từ **payload canonical** (các field có ý nghĩa nghiệp vụ và cùng quy tắc chuyển đổi).

Một thuật toán đối soát:

1. **Ghi manifest bền vững** trước khi gửi bulk, có `operationId` ổn định qua retry.
2. Gửi các conditional `updateOne` với `expectedVersion` và marker.
3. Nếu kết quả acknowledged, kiểm tra matched count có đúng số operation dự kiến không; nếu không, đánh dấu batch cần đối soát.
4. Nếu có lỗi mạng/timeout, đánh dấu **UNKNOWN**, không tự suy rằng tất cả chưa ghi.
5. Đọc lại document theo `orderId` trong phạm vi tenant và so sánh version, status, marker/hash.
6. Phân loại `APPLIED`, `CONFLICT`, `MISSING_OR_DENIED`, `BUSINESS_REJECTED` hoặc `UNKNOWN` theo bằng chứng.
7. Chỉ retry phần phù hợp sau khi xác nhận và tính lại expectedVersion/quy tắc nghiệp vụ.

### 13.1. Bảng quyết định sau readback

| Dữ liệu quan sát | Diễn giải thận trọng |
| --- | --- |
| `lastOperationId` và hash đúng, status mong muốn | Có bằng chứng operation này đã áp dụng, **nếu marker và effect ghi nguyên tử** |
| Version tăng, marker thuộc operation khác | Có writer khác đã thay đổi; cần quyết định conflict/merge |
| Version vẫn bằng expected, status vẫn PENDING | Có thể chưa áp dụng; vẫn phải xét tính nhất quán của lần đọc |
| Document không thấy qua truy vấn tenant | Có thể thiếu, bị xóa hoặc không có quyền; không tiết lộ tùy tiện |
| Marker ID đúng nhưng hash khác | **CONFLICT**: cùng key nhưng payload khác |
| Không có marker và version đã tăng nhiều lần | Không đủ bằng chứng; cần ledger/audit bền vững |
| Lỗi mạng trước khi nhận response | **UNKNOWN**, không mặc định rollback |

Một lần đọc đơn thuần không phải luôn đủ để nhận biết request có từng áp dụng khi dữ liệu đã đổi thêm bởi nhiều writer. Marker `lastOperationId` có thể bị ghi đè bởi operation sau. Nếu đòi lịch sử lâu dài, cần ledger/idempotency store có transaction hoặc embedded bounded history với hợp đồng retention.

### 13.2. Bulk không có per-item matched map: lựa chọn thiết kế

Nếu số lượng operation nhỏ nhưng **cần kết quả chi tiết ngay**, có thể dùng nhiều lệnh `findAndModify` riêng (mỗi lệnh trả document hoặc null), với concurrency/backpressure được giới hạn. Nếu throughput quan trọng, dùng bulk + **readback theo ID**, lưu manifest và chấp nhận độ phức tạp đối soát.

Không có lựa chọn nào mặc nhiên tối ưu mọi hệ thống; phải cân đối round trips, tính đúng và UX báo lỗi.

## 14. Idempotency: version guard không đủ để xác nhận retry là an toàn

Giả sử:

```text
Worker gửi CAS expectedVersion=7, operationId=op-1.
Server thực hiện: status=CONFIRMED, version=8, marker=op-1.
Phản hồi bị mất.
Worker gửi lại CAS expectedVersion=7, operationId=op-1.
Server trả matchedCount=0.
```

Điều này là **hành vi CAS đúng**: lần thứ hai không áp dụng thêm. Nhưng phía client không biết đây là:

- Lần đầu đã thành công và retry bị chặn.
- Writer khác đã dùng version 7 trước.
- Status đã chuyển theo một luồng khác.

**Không tự biến `matchedCount=0` thành exception “không có gì được ghi” rồi gửi lại với version=8.** Nếu worker tính lại version mới và gửi lại cùng business effect thiếu idempotency, có thể gây tác động lần thứ hai.

### 14.1. Marker cùng document

```javascript
db.orders.updateOne(
  {
    _id: "ord-101",
    version: NumberLong("7"),
    last_operation_id: { $ne: "op-1" }
  },
  {
    $set: {
      status: "CONFIRMED",
      last_operation_id: "op-1",
      last_operation_hash: "hash-1"
    },
    $inc: { version: NumberLong("1") }
  }
);
```

Vì filter marker và update marker/version nằm trong **một updateOne nguyên tử**, cùng operation không thể được áp dụng hai lần **nếu marker vẫn còn và lệnh được thiết kế phù hợp**.

Nhưng chỉ giữ **lastOperationId** không đủ để chống replay vô hạn nếu một lệnh khác ghi đè marker sau đó. Với yêu cầu at-most-once trong thời gian dài, cần ledger bền vững, unique operationId và phối hợp marker/effect nguyên tử hoặc transaction thích hợp.

### 14.2. Fingerprint phải được so khớp

Nếu `op-1` được gửi lần đầu với `status=CONFIRMED`, lần sau cùng `op-1` lại yêu cầu `status=CANCELLED` thì đây là **payload conflict**, không phải retry hợp lệ.

Bản ghi marker hoặc ledger phải lưu `payloadHash`/canonical payload. Không coi “đã có operationId” là thành công nếu không kiểm tra cùng nội dung nghiệp vụ.

## 15. Vì sao không nên dùng upsert với query chứa version?

Một lỗi thiết kế thường gặp:

```javascript
db.orders.updateOne(
  {
    _id: "ord-101",
    version: NumberLong("7")
  },
  {
    $set: { status: "CONFIRMED" },
    $inc: { version: NumberLong("1") }
  },
  { upsert: true }
);
```

Nếu document `ord-101` tồn tại nhưng version đã là 8, filter không khớp. Do có `upsert:true`, server có thể thử **insert document mới** từ điều kiện/update thay vì đơn giản báo 0 matched. Nếu insert mới mang cùng `_id`, bạn có thể gặp **duplicate key**; nếu điều kiện ID không được ràng buộc đúng, có thể tạo document không mong muốn.

Cách đúng khi cập nhật một entity đã phải tồn tại:

```javascript
db.orders.updateOne(
  { _id: "ord-101", version: NumberLong("7") },
  {
    $set: { status: "CONFIRMED" },
    $inc: { version: NumberLong("1") }
  },
  { upsert: false }
);
```

Khi cần **create-if-absent**, hãy thiết kế luồng insert riêng với ID/unique index ổn định, version initialization và xử lý duplicate/conflict rõ ràng. Đừng biến version mismatch thành insert nhờ một `upsert` không được phân tích.

### 15.1. Insert ban đầu và version không tồn tại

Một document legacy thiếu `version` không tự có version 0 theo nghĩa ứng dụng. Dùng filter `version:0` sẽ không khớp nó. Dùng `version:null` lại có semantics có thể khớp giá trị null/missing, dễ tạo đường cập nhật không nhất quán.

Trước khi bật version guard cho collection cũ, cần audit kiểu BSON và nâng cấp dữ liệu/version theo một migration có kiểm soát.

## 16. `replaceOne`, `updateMulti` và `saveAll`: không thay thế CAS per-document

### 16.1. `replaceOne`

Replacement thay **nội dung document** (trừ các ràng buộc như `_id`), nên dễ làm mất field nếu object replacement thiếu dữ liệu. Muốn dùng replacement trong bulk, vẫn cần filter theo `_id + expectedVersion` và replacement có **version mới** cùng các field cần giữ.

Đừng nghĩ việc truyền entity có `@Version` vào mọi overload `bulk.replaceOne` sẽ cung cấp optimistic locking tự động giống `save`. Phải đọc contract API đang dùng và test BSON/query thực tế.

### 16.2. `updateMulti`

```java
template.updateMulti(
    Query.query(Criteria.where("status").is("PENDING")),
    new Update().set("status", "EXPIRED"),
    OrderDocument.class
);
```

Đây là một lệnh cập nhật **nhiều document**, phù hợp cho một chính sách batch rộng **nếu không cần CAS riêng của từng document**. Nhưng nếu mỗi order có `expectedVersion` khác nhau, một filter chung trên status không thể bảo đảm từng expectedVersion đã được đối chiếu.

Một câu lệnh `updateMulti` không thể trả trạng thái per-order đầy đủ; dùng các `updateOne` có precondition riêng, theo batch khi cần.

### 16.3. `saveAll`

Repository `saveAll(...)` có thể thuận tiện với nhiều entity nhưng **không** có nghĩa “tất cả lưu thành công hoặc không lưu cái nào”. Tùy ID/version và đường thực thi, hoạt động lưu nhiều entity có thể có lỗi một phần khi không ở trong transaction.

Nếu cần atomicity đa document, phải chọn transaction trên deployment được hỗ trợ; không suy từ chữ “All” trong tên method.

## 17. Nhiều command trên cùng document: thứ tự và version

Ví dụ hai yêu cầu cùng order:

```text
A: version=7, PENDING → CONFIRMED
B: version=7, PENDING → CANCELLED
```

Nếu cả hai đều có CAS theo version và status, **tối đa một** được áp dụng trước, giả sử không có luồng khác đưa document trở về version 7. Đây là cơ chế **first successful compare-and-set wins**, không phải “request xuất hiện trước trong list sẽ thắng”.

Trong `UNORDERED`, MongoDB có thể thực hiện các update không theo thứ tự đầu vào; vì vậy **không dựa vào thứ tự list** để quyết định business precedence.

Nếu nghiệp vụ yêu cầu `CANCELLED` luôn ưu tiên hơn `CONFIRMED`, cần một **chính sách trạng thái** cụ thể, có thể là state machine, queue tuần tự theo ID, ưu tiên dựa trên event timestamp đáng tin và version guard — không chỉ đổi sang bulk ordered.

### 17.1. Version không phải timestamp của sự kiện nguồn

Event từ hệ thống ngoài có thể đến **không theo thứ tự**. Ví dụ event version 10 tới trước version 9. Nếu MongoDB entity version tăng mỗi lần cập nhật theo thứ tự nhận, nó không tự hiểu **sourceVersion** của upstream.

Có thể cần **hai field khác nhau**:

- `version`: optimistic lock revision của document MongoDB.
- `sourceVersion` hoặc `eventSequence`: thứ tự/số phiên bản của sự kiện nguồn.

Lúc đó filter phải kiểm tra cả policy về source ordering và optimistic revision, thay vì trộn hai mục đích vào một biến.

## 18. Retry version conflict: đọc lại, đánh giá lại, rồi mới ghi

Một retry hợp lệ trong optimistic locking thường là:

1. Nhận kết quả cho biết precondition không còn khớp.
2. Đọc lại bản ghi từ nơi có mức nhất quán phù hợp.
3. Xác định **quy tắc nghiệp vụ còn cho phép thay đổi hay không**.
4. Tính lại cập nhật dựa trên trạng thái mới, không dùng snapshot cũ.
5. Lấy version hiện tại làm `expectedVersion` mới.
6. Thử lại với backoff/giới hạn số lần; nếu conflict tiếp, kết thúc bằng mã lỗi phù hợp.

Ví dụ:

```text
Lần 1:
  read version=7, status=PENDING
  CAS confirm expectedVersion=7 → matched=0

Readback:
  version=8, status=CANCELLED

Quy tắc:
  Không cho phép CONFIRMED sau CANCELLED

Kết quả:
  BUSINESS_REJECTED, KHÔNG retry xác nhận theo version=8.
```

**Không retry tự động chỉ bằng cách tăng `expectedVersion`.** Làm như vậy có thể biến optimistic locking từ cơ chế bảo vệ thành vòng lặp ghi đè dữ liệu mới.

### 18.1. Vòng retry có giới hạn

```java
public enum CasDecision {
    APPLIED,
    ALREADY_APPLIED,
    CONFLICT,
    BUSINESS_REJECTED,
    UNKNOWN
}
```

Đặt kết quả domain rõ giúp service phân biệt điều kiện:

- `ALREADY_APPLIED`: marker/hash chứng minh cùng effect đã ghi.
- `CONFLICT`: document đổi và cần caller giải quyết.
- `BUSINESS_REJECTED`: trạng thái không cho phép thao tác nữa.
- `UNKNOWN`: chưa biết outcome do lỗi mạng, thiếu bằng chứng.
- `APPLIED`: nhận được acknowledgement và có bằng chứng update thành công.

Nếu cần retry thực tế, orchestration phải lưu operationId, theo dõi số lần retry, backoff, deadline và eventual dead-letter/inspection. Không nuốt lỗi mạng rồi trả `CONFLICT` vì một lệnh có thể đã hoàn tất trước khi phản hồi bị mất.

## 19. Transaction đa document: CAS vẫn phải tôn trọng bất biến

Một workflow có thể cần:

- Xác nhận order.
- Trừ tồn kho của sản phẩm.
- Ghi ledger/audit.

Nếu ba thao tác nằm trên **nhiều document/collection**, chỉ CAS một order chưa làm cả workflow nguyên tử.

MongoDB hỗ trợ transaction đa document trên deployment phù hợp (replica set/sharded cluster theo cấu hình). Spring Data MongoDB có `MongoTransactionManager`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
class MongoTransactionConfig {

    @Bean
    MongoTransactionManager mongoTransactionManager(
        MongoDatabaseFactory factory
    ) {
        return new MongoTransactionManager(factory);
    }
}
```

Service điều phối:

```java
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderWorkflowService {

    private final OrderCasService orders;

    public OrderWorkflowService(OrderCasService orders) {
        this.orders = orders;
    }

    @Transactional(
        transactionManager = "mongoTransactionManager"
    )
    public void confirmWithRelatedWrites(
        ConfirmOrderCommand command
    ) {
        boolean applied = orders.confirm(command);

        if (!applied) {
            throw new OptimisticLockingFailureException(
                "Không thỏa precondition cập nhật order"
            );
        }

        // Thêm các thao tác MongoDB khác qua repository/template
        // cùng transaction context, ví dụ giữ hàng và ghi ledger.
        // Không thực hiện HTTP/email bên ngoài với giả định rollback được.
    }
}
```

Đoạn code là **khung ranh giới transaction**; các bước dữ liệu liên quan chưa được triển khai. Nó chỉ cho thấy rằng khi CAS không khớp, service phải **throw** để transaction rollback phần thao tác đã làm, thay vì trả thành công khi có một lệnh thất bại về nghiệp vụ.

### 19.1. Bulk và transaction

Bulk có thể được thực hiện trong transaction nếu các thao tác tham gia đúng session/transaction context và đáp ứng ràng buộc deployment. Nhưng transaction:

- Có overhead và giới hạn tài nguyên/thời gian.
- Có thể gặp write conflict cần quyết định retry **toàn transaction** theo semantics.
- Không biến `matchedCount=0` thành exception tự động: application vẫn phải kiểm tra invariant.
- Có thể có **unknown commit result** nếu kết nối mất sau khi commit; không mặc định rollback.
- Không bao trùm email, HTTP, cổng thanh toán hoặc broker khác.

Không mở transaction hàng giờ chỉ để batch hàng triệu document. Chia theo bất biến nghiệp vụ và dùng checkpoint/idempotency phù hợp.

## 20. Reactive MongoDB: CAS vẫn là một lệnh update có điều kiện

Với WebFlux, dùng `ReactiveMongoTemplate` thay vì gọi imperative `MongoTemplate` rồi bọc trong `Mono.just(...)`.

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

public Mono<Boolean> confirmReactive(
    ReactiveMongoTemplate template,
    ConfirmOrderCommand c
) {
    if (c.expectedVersion() < 0) {
        return Mono.error(
            new IllegalArgumentException("Version âm")
        );
    }

    Query filter = Query.query(
        Criteria.where("id").is(c.orderId())
            .and("tenantId").is(c.tenantId())
            .and("version").is(c.expectedVersion())
            .and("status").is("PENDING")
    );

    Update update = new Update()
        .set("status", "CONFIRMED")
        .set("lastOperationId", c.operationId())
        .set("lastOperationHash", c.payloadHash())
        .inc("version", 1L)
        .currentDate("updatedAt");

    return template.updateFirst(
        filter, update, OrderDocument.class
    ).map(result -> {
        if (!result.wasAcknowledged()) {
            throw new IllegalStateException(
                "Unacknowledged CAS write"
            );
        }
        return result.getMatchedCount() == 1L;
    });
}
```

Reactive CAS có cùng semantics:

- Filter theo version là điều kiện bắt buộc.
- Version increment nằm trong atomic update.
- Kết quả `false` không tự chỉ ra version conflict.
- Retry/resubscribe publisher có thể **gửi lại cùng lệnh**.
- Lỗi mạng có thể là ambiguous outcome.
- `Flux`/`Mono` không thay thế index, read concern hoặc transaction.

Không gọi `block()` trong event loop. Với transaction reactive, dùng `ReactiveMongoTransactionManager`/`TransactionalOperator` và reactive context phù hợp, không dùng manager imperative.

## 21. Write concern, read concern và bảo đảm về kết quả

### 21.1. Acknowledged writes cho CAS

Một update theo version cần phân biệt:

- Có server acknowledgement và `matchedCount=1`.
- Có acknowledgement nhưng `matchedCount=0`.
- Có lỗi/timeout khiến outcome chưa rõ.

Nếu write concern là unacknowledged (`w:0`), ứng dụng không thể dựa vào count hoặc optimistic locking exception đáng tin cậy. Với dữ liệu quan trọng, dùng acknowledged write concern; khi cần độ bền mạnh hơn theo chính sách triển khai, cân nhắc `majority`.

`w:"majority"` làm tăng yêu cầu xác nhận ghi bền vững theo cơ chế MongoDB, nhưng **không** làm biến mất trường hợp phản hồi bị mất sau khi server đã ghi. Version + idempotency/đối soát vẫn cần thiết.

### 21.2. Đọc đối soát cần đúng nguồn

Nếu vừa ghi vào primary nhưng đọc một secondary chưa bắt kịp, client có thể thấy version cũ và kết luận sai “chưa thực hiện”. Với những bước xác minh outcome, dùng read preference/read concern thích hợp và cân nhắc session/causal consistency theo yêu cầu.

Dù đọc từ primary, không có marker hoặc ledger đủ bền vững thì trạng thái cuối có thể không chứng minh một operation cụ thể đã từng áp dụng nếu các writer khác đã thay đổi sau đó.

### 21.3. CAS không loại bỏ khả năng ghi thay nhau hợp lệ

Hai request tuần tự với expectedVersion **7 rồi 8** đều có thể thành công. Version ngăn **stale request**; nó không ngăn một request hoàn toàn mới ở revision 8 thực hiện một thay đổi nghiệp vụ có thể không mong muốn. Cần state machine, ACL và validation trong filter/service.

## 22. Index và hiệu năng cho conditional update

Với filter:

```javascript
{
  _id: "ord-101",
  tenant_id: "tenant-A",
  version: NumberLong("7"),
  status: "PENDING"
}
```

MongoDB mặc định có index `_id` duy nhất. Vì query có equality trên `_id`, server thường có thể định vị document rất chọn lọc rồi kiểm tra tenant/version/status.

**Không mặc định cần tạo index `{_id:1,version:1}`** chỉ vì có version CAS. Trên collection mặc định, `_id` đã là khóa định vị duy nhất; thêm một index chứa version có thể tăng write amplification mà không cải thiện nhiều.

Nếu use case có query theo `tenantId + status` **không biết ID**, index khác có thể cần:

```javascript
db.orders.createIndex(
  { tenant_id: 1, status: 1, updated_at: -1 },
  { name: "idx_orders_tenant_status_updated" }
);
```

Index này phục vụ tìm danh sách đơn theo trạng thái/thời gian, không biến một câu `updateMulti` thành CAS từng version.

### 22.1. `explain("executionStats")` cho đường đọc tương đương

```javascript
db.orders.find({
  _id: "ord-101",
  tenant_id: "tenant-A",
  version: NumberLong("7"),
  status: "PENDING"
}).explain("executionStats");
```

Quan sát:

| Tín hiệu | Câu hỏi |
| --- | --- |
| `IXSCAN` / `IDHACK` / kế hoạch tương đương | Có dùng index để định vị theo ID? |
| `totalKeysExamined` | Đọc bao nhiêu index key? |
| `totalDocsExamined` | Có phải quét nhiều document? |
| `nReturned` | Đúng số document kỳ vọng? |
| p95/p99 update latency | Có write conflict/hotspot trên cùng order? |
| Retry rate | CAS có bị cạnh tranh thường xuyên? |
| Version conflict rate | Business đang tạo nhiều stale writes? |
| Write concern timeouts | Có nhiều ambiguous outcomes cần đối soát? |

`explain` cho **query đọc** giúp hiểu khả năng tìm document; không chứng minh toàn bộ chi phí của update, journal, replication, callback hoặc lock contention. Dùng metrics/profiler/driver monitoring và benchmark riêng cho write path.

### 22.2. Hot document và contention

Nếu một đơn hàng bị hàng trăm worker cập nhật liên tục, nhiều CAS sẽ thất bại vì version thay đổi nhanh. Chỉ thêm index không giải quyết được contention tại một document.

Các lựa chọn:

- Gom thay đổi theo aggregate ID.
- Điều phối queue theo key để giảm tranh chấp.
- Chuyển mô hình sang atomic counter/conditional update nếu business cho phép.
- Giảm trường hợp read-modify-write không cần thiết.
- Kiểm soát retry/backoff và độ lớn batch.

## 23. Kiểm thử tích hợp CAS trên MongoDB thật

Unit test mock `MongoTemplate.updateFirst` trả matched=1 chỉ xác minh code có nhánh xử lý; nó không chứng minh MongoDB thực thi filter/version một cách nguyên tử. Cần integration test với MongoDB thật, ví dụ Testcontainers.

### 23.1. Test cập nhật version và chặn stale writer

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;

import com.mongodb.client.result.UpdateResult;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

@DataMongoTest
class OrderVersionCasIntegrationTest {

    @Autowired
    MongoTemplate template;

    @Test
    void onlyOneWriterCanUseExpectedVersion() {
        String id = "cas-order-001";

        template.insert(new OrderDocument(
            id, "test-tenant", "PENDING",
            0L, null, Instant.EPOCH, null, null
        ));

        OrderDocument saved =
            template.findById(id, OrderDocument.class);

        assertThat(saved).isNotNull();
        long v0 = saved.version();

        UpdateResult first = casConfirm(
            id, "test-tenant", v0, "op-first"
        );

        UpdateResult stale = casConfirm(
            id, "test-tenant", v0, "op-second"
        );

        assertThat(first.getMatchedCount()).isEqualTo(1L);
        assertThat(stale.getMatchedCount()).isEqualTo(0L);

        OrderDocument after =
            template.findById(id, OrderDocument.class);

        assertThat(after.status()).isEqualTo("CONFIRMED");
        assertThat(after.version()).isEqualTo(v0 + 1L);
        assertThat(after.lastOperationId())
            .isEqualTo("op-first");
    }

    private UpdateResult casConfirm(
        String id,
        String tenant,
        long expected,
        String opId
    ) {
        Query filter = Query.query(
            Criteria.where("id").is(id)
                .and("tenantId").is(tenant)
                .and("version").is(expected)
                .and("status").is("PENDING")
        );

        Update update = new Update()
            .set("status", "CONFIRMED")
            .set("lastOperationId", opId)
            .inc("version", 1L);

        return template.updateFirst(
            filter, update, OrderDocument.class
        );
    }
}
```

Test chạy hai lệnh **tuần tự** với cùng expectedVersion để xác nhận stale update bị từ chối; đây chưa phải stress test hai thread thực sự đồng thời. Nếu muốn thử concurrency, dùng barrier/latch để hai worker cùng đọc version ban đầu, sau đó đồng thời gửi CAS, rồi assert tổng số thành công đúng 1.

Với ID cố định, test phải dùng database/collection cô lập hoặc cleanup an toàn. Không xóa toàn collection dùng chung chỉ để khởi tạo fixture.

### 23.2. Test bulk có một expectedVersion cũ

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;

import com.mongodb.bulk.BulkWriteResult;
import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

@Test
void bulkOnlyMatchesCurrentVersion() {
    template.insertAll(List.of(
        new OrderDocument(
            "bulk-cas-01", "test-tenant", "PENDING",
            0L, null, Instant.EPOCH, null, null
        ),
        new OrderDocument(
            "bulk-cas-02", "test-tenant", "PENDING",
            0L, null, Instant.EPOCH, null, null
        )
    ));

    OrderDocument one = template.findById(
        "bulk-cas-01", OrderDocument.class
    );

    OrderDocument two = template.findById(
        "bulk-cas-02", OrderDocument.class
    );

    BulkOperations bulk = template.bulkOps(
        BulkOperations.BulkMode.UNORDERED,
        OrderDocument.class
    );

    bulk.updateOne(
        Query.query(
            Criteria.where("id").is(one.id())
                .and("version").is(one.version())
                .and("tenantId").is("test-tenant")
        ),
        new Update().set("status", "CONFIRMED")
            .inc("version", 1L)
    );

    // Dùng expectedVersion cũ không khớp order thứ hai.
    bulk.updateOne(
        Query.query(
            Criteria.where("id").is(two.id())
                .and("version").is(two.version() + 1L)
                .and("tenantId").is("test-tenant")
        ),
        new Update().set("status", "CONFIRMED")
            .inc("version", 1L)
    );

    BulkWriteResult result = bulk.execute();

    assertThat(result.wasAcknowledged()).isTrue();
    assertThat(result.getMatchedCount()).isEqualTo(1);
    assertThat(result.getModifiedCount()).isEqualTo(1);

    assertThat(
        template.findById(one.id(), OrderDocument.class)
            .version()
    ).isEqualTo(one.version() + 1L);

    assertThat(
        template.findById(two.id(), OrderDocument.class)
            .status()
    ).isEqualTo("PENDING");
}
```

Đây là **method test minh họa đặt trong test class ở mục 23.1**, dùng cùng field `template` và các imports cần thiết; không phải file Java độc lập. Test chứng minh một lệnh unmatched không làm toàn bộ bulk ném optimistic locking exception.

### 23.3. Test `@Version` với repository `save`

Nên có thêm test:

1. Insert entity có `@Version Long version`.
2. Đọc hai bản snapshot A/B.
3. `repository.save(A)` thành công và tăng version.
4. `repository.save(B)` với version cũ ném `OptimisticLockingFailureException`.
5. Kiểm tra dữ liệu cuối thuộc A.

Trường hợp này đối chiếu rõ optimistic locking **tự động của `save`** với CAS **tường minh** của direct update/bulk.

### 23.4. Những test còn cần làm

| Case | Kỳ vọng |
| --- | --- |
| `@Version` khi `save` | Version mới được tăng; stale save bị chặn |
| Direct update chỉ theo ID | Cho thấy nguy cơ khi không check expectedVersion |
| Direct update ID+version | Chỉ một writer dùng version đó được |
| Version đúng, status sai | CAS không khớp vì business precondition |
| Tenant khác | Không thể cập nhật order ngoài phạm vi |
| Bulk một current, một stale | matched tổng 1; version chỉ một order tăng |
| Bulk ordered gặp CAS no match | Không mặc nhiên dừng nếu không có write error |
| Một bulk có hai command cùng ID | Phát hiện/dedupe trước, không tin thứ tự unordered |
| Upsert chứa version | Không tạo document ngoài ý muốn khi version mismatch |
| Mất phản hồi sau update | Đối soát marker trước retry |
| Cùng operationId, payload khác | Phát hiện conflict |
| Document legacy thiếu version | Có chính sách migration/không âm thầm áp dụng |
| Write concern không acknowledged | Không dùng làm cơ sở optimistic locking |
| Transaction multi-document | Rollback khi CAS fail, có xử lý commit unknown |
| Reactive CAS | Publisher phát kết quả đúng, không block |
| Index/hot document | Kiểm tra latency, version conflict rate, explain |

## 24. Các lỗi thường gặp

**Lỗi 1 — “Chỉ cần `@Version` thì mọi `MongoTemplate.updateFirst` tự thành optimistic locking.”** Không. Phải có precondition expectedVersion trong query hoặc đường API có cơ chế CAS cụ thể.

**Lỗi 2 — “Tăng version là đủ.”** Không. Nếu filter chỉ theo `_id`, hai writer vẫn có thể ghi giá trị tính từ snapshot cũ.

**Lỗi 3 — “`matchedCount=0` luôn là version conflict.”** Không. Còn có missing ID, tenant, status và retry đã áp dụng trước đó.

**Lỗi 4 — “Bulk ném exception khi một update không khớp version.”** Không mặc định; updateOne không khớp filter thường không phải write error.

**Lỗi 5 — “`BulkWriteResult.matchedCount=5` chỉ rõ 5 order đầu tiên thành công.”** Không. Đây là tổng số, không có mapping kết quả từng lệnh.

**Lỗi 6 — “ORDERED bulk rollback các update thành công trước lỗi.”** Không ngoài transaction.

**Lỗi 7 — “Có hai command cùng order trong UNORDERED bulk thì command sau sẽ thắng.”** Không có bảo đảm thứ tự đầu vào.

**Lỗi 8 — “Upsert filter theo version là cách retry conflict an toàn.”** Không. Khi version khác, upsert có thể thử insert và gặp duplicate key hoặc tạo document sai.

**Lỗi 9 — “Sau timeout phải gửi lại cùng yêu cầu với version mới.”** Nguy hiểm. Phải đối soát effect/idempotency trước.

**Lỗi 10 — “`modifiedCount=0` có nghĩa version không khớp.”** Không nếu update là no-op hoặc có semantics khác; trong CAS thường đọc matchedCount.

**Lỗi 11 — “Transaction tự phát hiện unmatched CAS và rollback.”** Không nếu application bỏ qua result rồi commit.

**Lỗi 12 — “Version là số thứ tự event upstream.”** Không nhất thiết. Cần tách revision của document và source sequence.

**Lỗi 13 — “Thêm compound index `{_id:1,version:1}` luôn nhanh hơn.”** Không; `_id` đã unique/indexed, phải đo hiệu năng thực tế.

**Lỗi 14 — “Có acknowledged write concern thì không bao giờ có UNKNOWN.”** Không. Kết nối có thể đứt sau khi server đã ghi.

**Lỗi 15 — “Reactive retryWhen có thể chạy lại `$inc`/CAS mà không cần xét kết quả.”** Không. Phải xét effect, marker và policy.

## 25. Bài thực hành theo từng cấp độ

1. Tạo order `ord-101` với `status=PENDING` và `version=7` trên MongoDB test.
2. Viết raw `updateOne` dùng filter chỉ `_id`; mô phỏng hai writer ghi trạng thái khác nhau.
3. Thêm `version:7` vào filter và `$inc: {version:1}` vào update.
4. Chạy hai update cùng expectedVersion=7; xác minh chỉ một matched.
5. Đổi sang `MongoTemplate.updateFirst` với entity có `@Version Long version`, giữ version trong query.
6. Bỏ version khỏi query và quan sát vì sao tự tăng version (nếu framework hỗ trợ) không đủ ngăn stale writes.
7. Dùng `findAndModify(...returnNew(true))` để đọc version mới sau ghi.
8. Thêm precondition `status=PENDING`, thử xác nhận đơn đã CANCELLED.
9. Tạo bulk gồm nhiều `updateOne` với expectedVersion khác nhau.
10. Tạo một lệnh có expectedVersion cũ, đọc `BulkWriteResult.getMatchedCount()`, xác minh không có per-ID match map.
11. Thử `ORDERED` và `UNORDERED`, phân biệt unmatched query với write error.
12. Thử hai command cùng order trong unordered bulk; thiết kế bước dedupe.
13. Dùng operationId/marker/hash; mô phỏng mất phản hồi và đọc lại trước retry.
14. Thử `upsert:true` trong filter có version trên database test; quan sát rủi ro duplicate.
15. Viết test `repository.save(...)` cho optimistic locking exception.
16. Thử transaction cho order + ledger trên replica set test; rollback khi một CAS không khớp.
17. Viết `ReactiveMongoTemplate.updateFirst` với version filter và kiểm thử resubscription.
18. Đo index/explain và p95/p99 của update trên một “hot order”.
19. Thiết kế phân loại outcome `APPLIED/ALREADY_APPLIED/CONFLICT/UNKNOWN` cho job retry.
20. Chạy integration test bảo đảm tất cả write paths trong module không vô tình bypass version policy.

## 26. Checklist khi triển khai production

| Câu hỏi | Điều kiện cần xác minh |
| --- | --- |
| Entity có `@Version` đúng kiểu? | Long wrapper/primitive và BSON type khớp dữ liệu |
| Đường ghi nào sử dụng `save`? | Biết lúc nào optimistic locking được framework áp dụng |
| Đường ghi nào dùng update/bulk/raw? | **Tự đặt expectedVersion vào filter** |
| Version có tăng nguyên tử với business update? | `$inc(version,1)` hoặc cơ chế rõ tương đương |
| Có double increment version? | Không tự tăng hai lần trong Update và logic khác |
| Query có tenant/ACL? | Filter từ nguồn đáng tin, không lộ dữ liệu chéo tenant |
| Có business precondition? | Status/số lượng/điều kiện hợp lệ nằm trong filter |
| CAS 0 matched được xử lý? | Phân biệt missing/conflict/retry/permission khi có bằng chứng |
| Bulk có independent operations? | Dedupe cùng ID; không tin thứ tự unordered |
| Bulk result chỉ aggregate? | Có manifest/readback cho per-ID outcome |
| Retry sau timeout? | Có UNKNOWN, marker/ledger và payloadHash |
| Upsert với expectedVersion? | Tránh insert ngoài ý muốn khi version mismatch |
| Document legacy thiếu version? | Có migration, không coi missing là version=0 |
| Acknowledged write concern? | Không dùng w:0 cho optimistic locking |
| Readback nhất quán? | Có read preference/concern phù hợp |
| Transaction multi-document? | Có manager/context đúng, throw khi CAS fail |
| Có operation tới không theo thứ tự? | Phân biệt doc revision với sourceVersion |
| Index có cần thêm? | `_id` thường đủ cho single-order CAS; đo thực tế |
| Có test concurrency? | Stale save, stale update, bulk partial match, retry ambiguity |
| Có monitoring? | Conflict rate, UNKNOWN rate, retry count, latency, hotspot |

## 27. Tài liệu tham khảo

Các API và hành vi phụ thuộc phiên bản **MongoDB Server**, **MongoDB Java Driver** và **Spring Data MongoDB** mà ứng dụng thực tế đang dùng. Đặc biệt, kiểm tra `@Version` của `save(...)`, tăng version tự động ở template update, ghi hàng loạt, transaction và cách driver chuyển exception trong đúng dòng dependency.

- [Spring Data MongoDB — Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking)
- [Spring Data MongoDB — Bulk Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
- [Spring Data MongoDB — BulkOperations Javadoc](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/BulkOperations.html)
- [Spring Data MongoDB — MongoTemplate CRUD](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
- [Spring Data MongoDB — Update API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/query/Update.html)
- [Spring Data MongoDB — FindAndModifyOptions API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/FindAndModifyOptions.html)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)

**Kết luận:** `@Version` hỗ trợ optimistic locking khi lưu entity qua những đường API phù hợp, nhưng **cập nhật trực tiếp hoặc ghi hàng loạt không được mặc định tự kiểm tra version mà caller đã đọc**. Muốn giới hạn thay đổi theo version, hãy kết hợp **ID + tenant + expectedVersion + điều kiện nghiệp vụ trong filter**, đồng thời **tăng version trong cùng atomic update**. Trong bulk, mỗi `updateOne` phải có CAS riêng; `BulkWriteResult` chỉ cung cấp tổng số và không tự ném lỗi cho mọi lệnh unmatched. Cuối cùng, version giúp chống ghi đè từ snapshot cũ nhưng **không thay idempotency, đối soát sau timeout, transaction đa document hoặc kiểm soát thứ tự sự kiện nguồn**. Kiểm chứng bằng integration test trên MongoDB thật và theo dõi conflict rate/latency trước khi đưa vào production.

