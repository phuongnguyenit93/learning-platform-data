# Kiểm thử điều kiện cập nhật, tạo trùng và giao dịch cạnh tranh

Trong hệ thống NoSQL, nhiều yêu cầu có thể cùng đọc và ghi một tài liệu, cùng tạo một bản ghi có khóa nghiệp vụ giống nhau hoặc cùng sửa nhiều tài liệu liên quan. Một thao tác chạy đúng khi chỉ có một người dùng chưa đủ chứng minh hệ thống đúng khi các yêu cầu chạy đồng thời.

Bài học này tập trung vào ba nhóm kiểm thử tính đúng:

1. **Cập nhật có điều kiện:** chỉ thay đổi dữ liệu khi điều kiện về phiên bản, trạng thái hoặc số lượng vẫn còn đúng tại thời điểm ghi.
2. **Tạo trùng và gửi lại yêu cầu:** xử lý nhiều lần tạo cùng một thực thể mà không sinh bản ghi hoặc tác dụng phụ ngoài ý muốn.
3. **Giao dịch cạnh tranh:** bảo toàn các bất biến khi nhiều giao dịch cùng thay đổi những dữ liệu liên quan, kể cả khi có xung đột, lỗi mạng hoặc thử lại.

Các ví dụ chính sử dụng MongoDB với Java và JUnit 5. Nguyên tắc tương tự áp dụng được cho DynamoDB và các hệ thống NoSQL khác, nhưng cần đối chiếu bảo đảm nhất quán thực tế của từng hệ quản trị.

## 1. Bắt đầu từ bất biến nghiệp vụ

Giả sử một dịch vụ nhận đơn đặt hàng và trừ tồn kho. Có hai collection:

```javascript
// products
{
  _id: "sku-01",
  available: 3,
  version: NumberLong(7)
}

// orders
{
  _id: "req-1001",    // Khóa yêu cầu, đồng thời là khóa chống tạo trùng
  sku: "sku-01",
  quantity: 2,
  state: "CONFIRMED"
}
```

Ta cần bảo đảm:

- **I1 — Không tồn kho âm:** `products.available >= 0`.
- **I2 — Không ghi đè cập nhật cũ:** với cơ chế optimistic locking, chỉ một yêu cầu được phép ghi từ cùng một `version` ban đầu.
- **I3 — Mỗi yêu cầu chỉ tạo một đơn:** mỗi `requestId` tương ứng tối đa một đơn hàng; cùng khóa nhưng nội dung khác phải được phát hiện là xung đột.
- **I4 — Đặt hàng là một chuyển trạng thái thống nhất:** đơn hàng được xác nhận khi và chỉ khi phần tồn kho tương ứng đã được giữ/chuyển đi thành công.
- **I5 — Không làm mất tác dụng hoặc cộng/trừ hai lần khi thử lại:** lỗi mạng và việc gửi lại cùng yêu cầu không được nhân đôi kết quả đã được xác nhận.

Nếu không có nhập kho, hủy đơn hoặc thay đổi tồn kho từ nơi khác trong lúc kiểm thử, có thể dùng thêm bất biến định lượng:

```text
available_ban_đầu
    = available_cuối
    + SUM(quantity của đơn CONFIRMED được tạo trong phép thử)
```

Bất biến đo trạng thái bền vững sau cùng quan trọng hơn việc chỉ đếm bao nhiêu HTTP response trả về thành công. Một response lỗi hoặc timeout đôi khi vẫn đi kèm thao tác đã commit thành công.

## 2. Phân biệt ba phạm vi bảo đảm

| Cơ chế | Điều được bảo vệ | Điều không tự bảo vệ |
|---|---|---|
| Ghi nguyên tử trên **một tài liệu** | Điều kiện và cập nhật của chính tài liệu đó | Tính nhất quán của tài liệu khác |
| **Khóa duy nhất** / conditional create | Không có hai bản ghi cùng khóa đã ràng buộc | Hai tác dụng phụ bên ngoài DB, hoặc cùng yêu cầu tạo tài liệu khác khóa |
| **Giao dịch nhiều tài liệu** | Các thao tác tham gia giao dịch commit/rollback cùng nhau theo bảo đảm của DB | Mọi bất biến nghiệp vụ nếu các giao dịch không cùng ghi vào nơi tranh chấp; tác dụng phụ ở hệ thống ngoài |

Ví dụ sai thường gặp là đọc tồn kho trước rồi cập nhật vô điều kiện:

```text
T1: đọc available = 1
T2: đọc available = 1
T1: ghi available = 0
T2: ghi available = 0
T1 và T2 cùng báo đặt hàng thành công
```

Tồn kho cuối có thể không âm, nhưng đã có **hai đơn cùng dùng một đơn vị tồn kho**. Chỉ kiểm tra `available >= 0` sẽ bỏ sót lỗi này; cần kiểm cả tổng lượng đặt và số thao tác được chấp nhận.

## 3. Kiểm thử cập nhật có điều kiện (CAS / optimistic locking)

### 3.1. Đặt điều kiện ngay trong lệnh ghi

Thay vì `find()` rồi `update()` tách rời, dùng một lệnh `updateOne()` có filter chứa điều kiện nghiệp vụ:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.conversions.Bson;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

UpdateResult reserveIfVersionMatches(
        MongoCollection<Document> products,
        String sku,
        int quantity,
        long expectedVersion) {

    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity phải > 0");
    }

    Bson filter = and(
            eq("_id", sku),
            eq("version", expectedVersion),
            gte("available", quantity)
    );

    Bson change = combine(
            inc("available", -quantity),
            inc("version", 1L)
    );

    return products.updateOne(filter, change);
}
```

MongoDB kiểm tra filter và áp dụng update nguyên tử trên **một tài liệu**. Nếu hai client cùng gửi `expectedVersion = 7`, tối đa một client có thể khớp và đổi phiên bản sang `8`. Nếu stock chỉ có một đơn vị và hai client mỗi bên muốn một đơn vị, cũng chỉ một lệnh có thể trừ thành công.

Khi diễn giải kết quả:

- `matchedCount == 1`: điều kiện khớp và cập nhật được chấp nhận.
- `matchedCount == 0`: tài liệu không tồn tại, phiên bản cũ hoặc không đủ tồn kho; muốn phân biệt lý do thì đọc lại trạng thái và xử lý theo chính sách nghiệp vụ.
- `modifiedCount` không phải tiêu chí tổng quát để biết predicate có khớp, vì một thao tác đặt lại đúng giá trị cũ có thể khớp mà không làm thay đổi dữ liệu. Ví dụ trên có tăng `version` nên thông thường số được sửa bằng số được khớp.
- Không bật `upsert` cho lệnh trừ tồn kho này: việc tạo bản ghi khi không tìm thấy sản phẩm sẽ trái với chủ đích.

**Lưu ý:** đọc lại sau khi `matchedCount == 0` chỉ giúp giải thích nguyên nhân tại *thời điểm đọc lại*. Trạng thái có thể tiếp tục đổi; không dùng phép đọc đó để thực hiện một cập nhật vô điều kiện.

### 3.2. Các trường hợp cần kiểm thử

| Tình huống | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Đủ tồn và đúng phiên bản | `available=3, version=7, quantity=2, expectedVersion=7` | Khớp 1; còn 1; phiên bản 8 |
| Không đủ tồn | `available=1, quantity=2` | Khớp 0; dữ liệu giữ nguyên |
| Phiên bản cũ | DB là 8, client gửi 7 | Khớp 0; dữ liệu giữ nguyên |
| Không tồn tại SKU | `_id` không có trong DB | Khớp 0; không tự tạo tài liệu |
| Hai cập nhật dùng cùng phiên bản | Cùng đọc phiên bản 7 | Chỉ một lệnh thắng; phiên bản cuối 8 |
| Hai cập nhật không dùng phiên bản nhưng cùng tranh một đơn vị | `available=1`, mỗi bên trừ 1 với `gte("available", 1)` | Chỉ một lệnh thắng; tồn kho cuối 0 |
| Đầu vào không hợp lệ | `quantity <= 0` | Bị chặn trước khi truy cập DB |

Nếu nghiệp vụ cho phép sửa độc lập những trường khác nhau, việc đặt `version` chung sẽ làm tăng xung đột giả; khi đó cân nhắc điều kiện trực tiếp trên trường cần bảo vệ hoặc thiết kế phân vùng cập nhật phù hợp. Phép thử phải bám đúng bất biến cần giữ, không mặc định rằng mọi thao tác đều phải tranh cùng một phiên bản.

### 3.3. Dùng hai luồng để chứng minh chỉ có một người thắng

Ví dụ JUnit 5 bên dưới giả sử biến `products` trỏ đến MongoDB dành riêng cho integration test và collection đã được làm sạch trước mỗi test. Hai luồng cùng dùng một phiên bản cũ; `CountDownLatch` bảo đảm chúng sẵn sàng rồi mới cùng bắt đầu.

```java
import static org.junit.jupiter.api.Assertions.*;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

class ConditionalUpdateIT {

    private MongoCollection<Document> products; // Gán từ fixture MongoDB test

    @Test
    void onlyOneWriterCanUseTheOldVersion() throws Exception {
        products.insertOne(new Document("_id", "sku-race")
                .append("available", 1)
                .append("version", 7L));

        int writers = 2;
        CountDownLatch ready = new CountDownLatch(writers);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(writers);

        try {
            List<Future<UpdateResult>> futures = new ArrayList<>();
            for (int i = 0; i < writers; i++) {
                futures.add(pool.submit(() -> {
                    ready.countDown();
                    if (!start.await(5, TimeUnit.SECONDS)) {
                        throw new AssertionError("Hết thời gian chờ lệnh start");
                    }
                    return products.updateOne(
                            and(eq("_id", "sku-race"),
                                eq("version", 7L),
                                gte("available", 1)),
                            combine(inc("available", -1),
                                    inc("version", 1L)));
                }));
            }

            assertTrue(ready.await(5, TimeUnit.SECONDS));
            start.countDown();

            long accepted = 0;
            for (Future<UpdateResult> f : futures) {
                accepted += f.get(10, TimeUnit.SECONDS).getMatchedCount();
            }

            Document actual = products.find(eq("_id", "sku-race")).first();
            assertNotNull(actual);
            assertEquals(1L, accepted);
            assertEquals(0, actual.getInteger("available"));
            assertEquals(8L, actual.getLong("version"));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Đây là kiểm thử tích hợp với MongoDB thật; `products` cần được khởi tạo trong fixture của dự án. Một DB nhúng giả lập hoặc mock `updateOne()` có thể không mô phỏng chính xác sự cạnh tranh trên server. Latch tạo điểm xuất phát gần nhau nhưng không ép hai lệnh bắt buộc phải chồng lấn; giá trị chính của phép thử nằm ở **bất biến sau khi cả hai thao tác kết thúc**.

## 4. Kiểm thử tạo trùng và idempotency

### 4.1. Ba khái niệm khác nhau

**Unique constraint** bảo đảm không thể có hai bản ghi với cùng khóa duy nhất. **Idempotency** bảo đảm lặp lại cùng một yêu cầu nghiệp vụ có hiệu quả tương đương thực hiện một lần. **At-most-once acceptance** nói rằng chỉ có tối đa một lần tạo được ghi nhận; nó chưa quyết định client gửi lại phải nhận response gì.

Ví dụ dùng `requestId` do client tạo và giữ ổn định khi retry:

```java
// Cách đơn giản: requestId là _id, mặc định có unique index.
Document order = new Document("_id", "req-1001")
        .append("sku", "sku-01")
        .append("quantity", 2)
        .append("state", "CONFIRMED");
orders.insertOne(order);
```

Nếu `requestId` là trường riêng, cần tạo **unique index thực sự** trước khi cho phép ghi:

```java
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;

orders.createIndex(
        Indexes.ascending("requestId"),
        new IndexOptions().unique(true)
);
```

Kiểm tra index đã tồn tại là bước chuẩn bị fixture; không được dựa vào quy trình “đọc xem có bản ghi chưa, rồi insert” để chống race. Trong hệ thống sharded cần kiểm tra giới hạn của unique index và shard key theo phiên bản MongoDB đang dùng.

### 4.2. Quy tắc phản hồi cho yêu cầu lặp

Giả sử hai request có cùng `requestId`:

| Yêu cầu tới | Ý nghĩa | Kết quả API gợi ý |
|---|---|---|
| Khóa mới, nội dung hợp lệ | Tạo lần đầu | `201 Created` |
| Khóa cũ, toàn bộ nội dung nghiệp vụ tương đương | Retry của yêu cầu cũ | Trả kết quả đơn đã tạo; có thể `200 OK` hoặc replay response đã lưu |
| Khóa cũ, nhưng `sku` hoặc `quantity` khác | Tái sử dụng khóa cho yêu cầu khác | `409 Conflict` |
| Khóa cũ, giao dịch đầu chưa rõ kết quả | Trạng thái đang cạnh tranh/không chắc chắn | Tra cứu hoặc retry có giới hạn; không tạo khóa khác để “thử lại” |

Với MongoDB, lỗi `E11000` (mã `11000`) cho biết có xung đột khóa duy nhất. Không nên kết luận ngay “idempotent thành công” chỉ từ mã lỗi; cần đọc bản ghi tương ứng và so sánh nội dung nghiệp vụ chuẩn hóa.

```java
import com.mongodb.MongoWriteException;

import static com.mongodb.client.model.Filters.eq;

String createOrReplay(
        MongoCollection<Document> orders,
        String requestId,
        String sku,
        int quantity) {

    Document intended = new Document("_id", requestId)
            .append("sku", sku)
            .append("quantity", quantity)
            .append("state", "CONFIRMED");

    try {
        orders.insertOne(intended);
        return "CREATED";
    } catch (MongoWriteException e) {
        if (e.getError().getCode() != 11000) {
            throw e;
        }

        Document existing = orders.find(eq("_id", requestId)).first();
        if (existing != null
                && sku.equals(existing.getString("sku"))
                && quantity == existing.getInteger("quantity")) {
            return "REPLAYED";
        }

        throw new IllegalStateException("IDEMPOTENCY_KEY_CONFLICT");
    }
}
```

Ví dụ trên minh họa một thao tác tạo đơn độc lập. Trong ứng dụng thực tế, phải đặt phần thay đổi tồn kho và tạo đơn trong cùng thiết kế bảo toàn bất biến (xem giao dịch ở phần sau). Ngoài ra, bản ghi của giao dịch cạnh tranh có thể chưa hiển thị khi vừa gặp duplicate-key; nếu chưa đọc được bản ghi, cần chính sách thử tra cứu lại có giới hạn và trả trạng thái chưa xác định, thay vì khẳng định hai payload khác nhau.

### 4.3. Kịch bản kiểm thử tạo trùng

1. **Lặp tuần tự:** gọi cùng `requestId`, cùng payload hai lần; assert chỉ có một bản ghi, nội dung không đổi, lần thứ hai trả kết quả replay như hợp đồng API.
2. **Lặp cạnh tranh:** cho 10–50 tác vụ đồng thời gọi tạo cùng `requestId`; assert chỉ một bản ghi tồn tại, không tác vụ nào làm thay đổi một tài liệu khác thêm lần nữa.
3. **Tái sử dụng khóa sai:** gọi cùng `requestId` với payload khác; assert conflict và bản ghi gốc vẫn nguyên vẹn.
4. **Hai khóa khác nhau:** gọi hai `requestId` khác nhau nhưng cùng nội dung; đây có thể là hai yêu cầu hợp lệ, không nên bị chặn chỉ vì payload giống nhau.
5. **Mất response sau khi commit:** mô phỏng server đã lưu đơn nhưng client timeout trước khi nhận kết quả; client gửi lại *cùng khóa*, hệ thống phải truy hồi kết quả cũ.
6. **Lỗi khác duplicate:** lỗi kết nối, quyền truy cập hoặc validation phải được phân loại đúng; không được bắt mọi exception rồi trả “đã tồn tại”.

Một cách tổ chức test cạnh tranh:

```text
given: collection rỗng; unique index hoạt động
when: N tác vụ chờ cùng start latch
      rồi INSERT _id = "req-race" với cùng payload
then: số insert thành công ở tầng database = 1
      số tài liệu có _id = "req-race" = 1
      mọi yêu cầu còn lại được service xử lý theo hợp đồng retry
      tác dụng phụ nghiệp vụ xảy ra đúng 1 lần
```

Phân biệt kết quả cấp database (một insert, các insert khác gặp duplicate) với kết quả cấp service (có thể tất cả request cùng payload đều nhận phản hồi idempotent thành công).

## 5. Kiểm thử giao dịch nhiều tài liệu cạnh tranh

### 5.1. Khi nào cần transaction?

Một đơn đặt hàng vừa tạo `orders`, vừa trừ `products`. Hai câu lệnh chạy ngoài giao dịch có thể để lại trạng thái dở dang nếu lệnh thứ hai lỗi. Với MongoDB, transaction cho phép commit/rollback các thay đổi trên nhiều tài liệu trong cùng giao dịch, khi chạy trên deployment hỗ trợ transaction (replica set hoặc sharded cluster).

```mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as Database
    Note over DB: available = 1
    A->>DB: Transaction: tạo order A; trừ 1 nếu available ≥ 1
    B->>DB: Transaction: tạo order B; trừ 1 nếu available ≥ 1
    DB-->>A: Một giao dịch có thể commit
    DB-->>B: Giao dịch còn lại xung đột hoặc không đủ tồn
    Note over DB: Cuối cùng: 1 đơn hợp lệ, available = 0
```

Trong Java, ví dụ triển khai với MongoDB synchronous driver:

```java
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.TransactionOptions;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

void placeOrderAtomically(
        MongoClient client,
        MongoCollection<Document> products,
        MongoCollection<Document> orders,
        String requestId,
        String sku,
        int quantity) {

    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity phải > 0");
    }

    TransactionOptions options = TransactionOptions.builder()
            .readConcern(ReadConcern.SNAPSHOT)
            .writeConcern(WriteConcern.MAJORITY)
            .build();

    try (ClientSession session = client.startSession()) {
        session.withTransaction(() -> {
            orders.insertOne(session, new Document("_id", requestId)
                    .append("sku", sku)
                    .append("quantity", quantity)
                    .append("state", "CONFIRMED"));

            UpdateResult result = products.updateOne(
                    session,
                    and(eq("_id", sku), gte("available", quantity)),
                    inc("available", -quantity));

            if (result.getMatchedCount() != 1) {
                throw new IllegalStateException("OUT_OF_STOCK");
            }
            return null;
        }, options);
    }
}
```

Ở đây, hai bước ghi cùng nằm trong một transaction. Nếu không đủ tồn, xảy ra lỗi khi ghi, hoặc transaction bị hủy trước khi commit, bản ghi order được tạo trong transaction cũng bị rollback. Sử dụng `_id = requestId` tránh hai order được commit cùng một khóa yêu cầu.

`withTransaction(...)` của MongoDB driver có cơ chế thử lại phù hợp với một số lỗi giao dịch/commit tạm thời. Vì callback *có thể chạy nhiều lần*, không gửi email, gọi cổng thanh toán hoặc phát message bên ngoài DB trực tiếp bên trong callback. Nếu cần phát sự kiện sau commit, cân nhắc **transactional outbox** (ghi event vào collection cùng transaction, worker độc lập phát event theo cơ chế idempotent).

### 5.2. Các trường hợp cạnh tranh cần chứng minh

| Case | Thiết lập | Điều cần assert sau cùng |
|---|---|---|
| Hai giao dịch lấy cùng đơn vị tồn | `available=1`, hai `requestId` khác nhau, mỗi bên đặt 1 | Tối đa một đơn `CONFIRMED`; tồn kho 0 nếu một bên thành công; không tồn âm |
| Hai giao dịch độc lập | Hai SKU khác nhau, tồn đủ | Cả hai có thể commit; không mất cập nhật |
| Cùng `requestId` | Hai giao dịch cùng tạo một đơn | Chỉ một đơn; trừ kho đúng một lần; retry nhận kết quả đã tồn tại hoặc trạng thái xác định |
| Lỗi sau khi tạo order nhưng trước khi trừ kho | Tiêm exception ở giữa callback | Không có order mới; tồn kho giữ nguyên |
| Lỗi sau khi trừ kho nhưng trước commit | Tiêm exception trước commit | Cả hai thao tác rollback; không có đơn và không mất tồn |
| Write conflict | Hai transaction ghi cùng tài liệu | Transaction bị xung đột được retry theo chính sách; tổng kết quả vẫn giữ bất biến |
| Kết quả commit không rõ | Làm gián đoạn phản hồi quanh thời điểm commit | Có thể truy hồi bằng `requestId`; không tạo thêm order mới với khóa khác |

Không yêu cầu “cả hai đều phải thành công” hoặc “luôn phải có đúng một write conflict”. Số lần xung đột, thứ tự thắng thua và thời điểm retry phụ thuộc lịch chạy. Điều bất biến là mỗi kết quả thành công có hiệu quả được phép, còn các thay đổi của transaction thất bại không bị commit một phần.

### 5.3. Transaction không tự thay thế điều kiện nghiệp vụ

Nhiều hệ NoSQL có transaction với snapshot isolation. Một test chỉ kiểm tra “không có ghi dở dang” vẫn chưa đủ phát hiện **write skew**: hai transaction đọc cùng một điều kiện trên nhiều tài liệu, rồi mỗi transaction thay đổi tài liệu *khác nhau* nên có thể không trực tiếp tranh một bản ghi.

Ví dụ có hai nhân viên đang trực, luật là “luôn còn ít nhất một người trực”:

```text
Ban đầu: A.onCall = true, B.onCall = true
T1 đọc A,B: thấy 2 người trực
T2 đọc A,B: thấy 2 người trực
T1 cập nhật A.onCall = false
T2 cập nhật B.onCall = false
Cuối cùng: không còn ai trực
```

Một thiết kế bảo vệ mạnh hơn là làm hai giao dịch cùng cạnh tranh một tài liệu “guard” chứa số người trực và cập nhật có điều kiện `onCallCount > 1`, hoặc chọn cơ chế transaction/isolation phù hợp với bất biến. Test phải tái hiện lịch chạy có hai lần đọc trước các lần ghi, rồi xác nhận bất biến “số người trực ≥ 1” sau commit. Với MongoDB, transaction không nên được xem là lời hứa tự động loại bỏ mọi write skew nghiệp vụ.

## 6. Kiểm thử lỗi, retry và kết quả không xác định

Mạng không bảo đảm client luôn nhìn thấy kết quả của một lần ghi. Sau khi gửi lệnh, client có thể timeout vì:

- Server chưa nhận lệnh: chưa có thay đổi.
- Server đã nhận nhưng lệnh bị hủy: chưa có thay đổi bền vững.
- Server đã commit, nhưng gói phản hồi bị mất: **đã thay đổi**, dù client báo timeout.

Do đó “exception = chưa ghi” là giả định nguy hiểm. Quy tắc cần kiểm thử:

1. Gán `requestId` ổn định **trước** lần gửi đầu tiên, lưu lại cùng payload.
2. Nếu kết quả không rõ, thử đọc theo khóa yêu cầu và đối chiếu dữ liệu đã commit. Với dữ liệu cần xác nhận bền vững, cấu hình read/write concern và read preference phù hợp; đọc từ secondary trễ có thể chưa thấy thay đổi vừa commit.
3. Nếu vẫn chưa xác định, trả trạng thái có thể tra cứu/thử lại có giới hạn thay vì tự tạo một `requestId` mới.
4. Retry lỗi xung đột có giới hạn, có backoff/jitter khi phù hợp, rồi trả kết quả nghiệp vụ rõ ràng. Một thử lại có thể chạy toàn bộ callback transaction; mọi tác dụng phụ ngoài DB phải an toàn khi bị lặp.
5. Theo dõi tỷ lệ conflict, duplicate, retry và timeout, nhưng **không** dùng số lượng exception như bằng chứng duy nhất cho tính đúng.

Ví dụ test “timeout sau commit”:

```text
given: available = 2, chưa có order(req-77)
when: lần 1 đặt 1 sản phẩm và DB commit thành công
      nhưng bỏ response của lần 1 trên tầng mô phỏng network
      lần 2 gửi lại đúng requestId = req-77
then: có đúng một order(req-77)
      available = 1
      cả quá trình chỉ giữ một đơn vị tồn
      service trả lại kết quả đơn đã tạo
```

Để tiêm lỗi một cách kiểm soát, nên đặt hook tại biên giữa service và client/DB, hoặc dùng khả năng failpoint/network proxy của môi trường thử nghiệm. Không giả lập “DB đã commit” bằng cách chỉ ném exception trước khi lệnh ghi được thực hiện: đó là một trường hợp khác.

## 7. Thiết kế bộ kiểm thử đủ mạnh và dễ lặp lại

### 7.1. Phân tầng kiểm thử

| Tầng | Mục đích | Ví dụ |
|---|---|---|
| Unit test | Kiểm tra ánh xạ lỗi thành phản hồi, validate input, retry policy, so sánh payload idempotent | Mock service/gateway theo kết quả xác định |
| Integration test với DB thật | Kiểm tra filter nguyên tử, unique index, rollback transaction và concurrency thực tế | MongoDB replica set trong môi trường test |
| Fault-injection test | Kiểm tra lỗi ở ranh giới trước/sau ghi, mất response, kết quả commit không rõ | Hook, failpoint hoặc network proxy có kiểm soát |
| Stress / property-based test | Chạy nhiều lịch xen kẽ và tổ hợp dữ liệu để tìm lỗi hiếm | Sinh nhiều `requestId`, quantity và số lượng luồng |

Transaction MongoDB cần replica set hoặc sharded cluster phù hợp; một MongoDB standalone không đáp ứng đúng đặc tính cần thử. Có thể dùng Testcontainers hoặc fixture dựng sẵn, nhưng phải khởi tạo topology hỗ trợ transaction trước khi chạy.

### 7.2. Cấu trúc Given / When / Then

**Given — trạng thái bắt đầu đã biết:**

- Sử dụng database/collection riêng cho test; reset có kiểm soát và xác nhận unique index tồn tại.
- Tạo chính xác SKU, tồn kho, phiên bản và tập đơn ban đầu.
- Mỗi test có `requestId` độc lập để tránh nhiễu từ test chạy song song.
- Nếu test yêu cầu nhiều transaction, khởi tạo session riêng cho từng luồng; không chia sẻ cùng `ClientSession` giữa các luồng.

**When — tạo cạnh tranh tại đúng điểm cần thử:**

- Dùng `CountDownLatch` / `CyclicBarrier` để điều phối lúc bắt đầu.
- Nếu cần tái hiện một lịch xen kẽ cụ thể, dùng hook tại điểm “đã đọc snapshot nhưng chưa ghi” trong test-only service; latch chỉ đồng bộ điểm xuất phát không đủ để đảm bảo write skew.
- Đặt timeout cho latch/future để test lỗi có kết thúc; tránh phụ thuộc `Thread.sleep()` như cơ chế đồng bộ.

**Then — kiểm tra cả response lẫn cơ sở dữ liệu:**

```text
assert available >= 0
assert requestId unique
assert available_initial == available_final + total_confirmed_quantity
assert quantity/time/version đúng với số thao tác thực sự thành công
assert không còn order CONFIRMED không có tồn kho tương ứng
assert retry cùng requestId không thay đổi số lượng lần nữa
```

Sau khi tất cả future hoàn tất, đọc trạng thái từ nguồn có mức nhất quán phù hợp với hợp đồng đã chọn. Đối với transaction có majority write concern, các phép đọc phục vụ test nên được cấu hình để không vô tình quan sát bản sao chậm và kết luận sai.

### 7.3. Lặp lại nhiều lịch chạy, nhưng viết assertion ổn định

Ví dụ với `available = 10`, 30 yêu cầu đặt mỗi yêu cầu một sản phẩm:

- Sau tất cả lần ghi, **số đơn được xác nhận không vượt quá 10**.
- Tồn kho cuối bằng `10 - số đơn xác nhận`.
- Mỗi request ID chỉ có một đơn; các lần retry không tăng tổng số đơn.
- Nếu service được thiết kế để tiếp tục retry đến khi có trạng thái cuối và không có lỗi hạ tầng, kỳ vọng đúng 10 đơn thành công; nếu cho phép kết thúc sớm vì xung đột hoặc timeout thì test chỉ nên yêu cầu những bất biến được cam kết.

Có thể chạy nhiều vòng với số luồng 2, 5, 20, payload phân phối ngẫu nhiên và thứ tự xen kẽ khác nhau. In seed ngẫu nhiên, `requestId`, thời điểm bắt đầu/kết thúc và trạng thái trước/sau khi gặp lỗi để tái tạo lịch gây lỗi. Không viết test chỉ yêu cầu đúng thứ tự luồng A thắng luồng B nếu nghiệp vụ không có ràng buộc thứ tự.

## 8. Quy chiếu sang các NoSQL khác

| Nhu cầu | MongoDB | DynamoDB | Redis |
|---|---|---|---|
| Cập nhật có điều kiện | `updateOne(filter, update)`, có thể kết hợp phiên bản và điều kiện tồn | `UpdateItem` với `ConditionExpression`; lỗi điều kiện không đạt | Lua script/Redis Function kiểm tra và sửa nguyên tử trên dữ liệu liên quan |
| Chặn tạo trùng | `_id` hoặc unique index | `PutItem` với `attribute_not_exists(...)` trên khóa mục tiêu | `SET key value NX` cho một khóa; cần xét TTL, tính bền vững và mất khóa |
| Ghi nhiều thực thể cùng transaction | Multi-document transaction nếu topology hỗ trợ | `TransactWriteItems` theo giới hạn dịch vụ | `MULTI/EXEC` hoặc Lua có ngữ nghĩa riêng; không thay thế transaction nhiều collection kiểu MongoDB |
| Kiểm thử tranh chấp | Kiểm filter, duplicate key, write conflict và retry | Kiểm conditional failure, transaction cancellation, idempotency | Kiểm atomic script, expiry, crash/failover và cơ chế bảo đảm dữ liệu thực tế |

Trong DynamoDB, ví dụ chống ghi đè là điều kiện `version = :expected` kèm cập nhật `version = version + :one` trong một lệnh `UpdateItem`. Tạo một item mới có thể dùng `attribute_not_exists(pk)`. Nếu cần cập nhật nhiều item như một đơn vị, cân nhắc `TransactWriteItems` và kiểm tra kết quả khi transaction bị hủy do một điều kiện không đạt.

Redis có tính nguyên tử cho từng lệnh và script theo các giới hạn của deployment, nhưng khóa `SET ... NX` có thời hạn không đồng nghĩa với bảo đảm “một yêu cầu tạo đúng một bản ghi bền vững mãi mãi”. Phép thử tạo trùng phải bao gồm thời điểm TTL hết hạn, restart/failover và việc nguồn dữ liệu chính có còn giữ lịch sử idempotency hay không.

## 9. Những lỗi thiết kế kiểm thử thường bỏ sót

| Sai sót | Hậu quả | Cách chỉnh |
|---|---|---|
| Chỉ kiểm HTTP status | Không thấy đơn trùng hoặc tồn kho bị trừ hai lần | Đọc trạng thái DB cuối và kiểm bất biến |
| Chỉ kiểm dữ liệu không âm | Hai giao dịch đều báo thành công cho cùng một đơn vị | Kiểm tổng số đơn và phương trình bảo toàn |
| Dùng `find` rồi `insert` để chặn trùng | Hai client cùng thấy “chưa tồn tại” | Unique constraint / conditional put trên DB |
| Bắt mọi lỗi thành “duplicate” | Che lỗi mạng, validation, write concern | Phân loại mã lỗi và trạng thái không xác định |
| Retry bằng `requestId` mới | Nhân đôi tác dụng nghiệp vụ sau timeout | Giữ khóa idempotency qua mọi lần gửi lại |
| Dùng MongoDB standalone để thử transaction | Không thử đúng điều kiện chạy thực tế | Replica set hoặc sharded test environment |
| Trông chờ `sleep` tạo race | Test phụ thuộc tốc độ máy, flaky | Latch/barrier và hook có kiểm soát |
| Chỉ assert số exception | Lịch chạy có thể thay đổi hợp lệ | Assert bất biến và kết quả bền vững |
| Đặt side effect ngoài DB bên trong callback retry | Email/payment/event có thể lặp | Outbox hoặc tác dụng phụ idempotent |
| Giả định transaction tự xử lý mọi write skew | Vi phạm quy tắc liên tài liệu | Guard document, điều kiện cập nhật hoặc mô hình isolation phù hợp |

## 10. Bài thực hành tổng hợp

Xây dựng API `POST /orders` nhận:

```json
{
  "requestId": "req-202",
  "sku": "sku-01",
  "quantity": 1
}
```

Yêu cầu chức năng:

1. `quantity` là số nguyên dương; SKU phải tồn tại.
2. Mỗi request ID chỉ được tạo một order, cùng khóa khác payload trả conflict.
3. Không bao giờ trừ tồn kho xuống âm.
4. Tạo order và trừ kho cùng commit hoặc cùng rollback.
5. Khi request được gửi lại sau lỗi mạng, truy hồi kết quả cũ và không trừ kho lần hai.

Xây dựng test theo thứ tự: thao tác đơn lẻ thành công; điều kiện cập nhật thất bại; replay tuần tự; tạo trùng song song; hai đơn khác khóa tranh một đơn vị tồn; lỗi ở giữa transaction; mất response sau commit; nhiều luồng với tổng lượng đặt vượt tồn kho.

Một bộ test đạt yêu cầu khi chứng minh được **tình trạng cuối sau mọi phép thử** tuân thủ các bất biến đã nêu, đồng thời phân biệt rõ xung đột nghiệp vụ, duplicate hợp lệ, lỗi hạ tầng có thể thử lại và kết quả commit chưa xác định. Đây là tiêu chuẩn kiểm thử tính đúng cho các thao tác NoSQL cạnh tranh, chứ không chỉ là việc nhìn thấy một lệnh ghi trả về thành công.
