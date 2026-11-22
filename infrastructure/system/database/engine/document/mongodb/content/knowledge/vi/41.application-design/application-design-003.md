# Tồn kho: cập nhật có điều kiện và chống trừ số lượng nhiều lần trong MongoDB

## Mục tiêu bài học

Trong hệ thống bán hàng, đặt vé, giữ chỗ và phân bổ tài nguyên, “trừ tồn kho” tưởng chừng chỉ là một lệnh giảm số. Tuy nhiên có hai lỗi **khác nhau** phải phòng ngừa:

- **Overselling:** hai yêu cầu khác nhau đều được xác nhận khi kho chỉ còn một sản phẩm. Cách xử lý là đặt điều kiện đủ hàng ngay trong một **atomic update**.
- **Double decrement:** một yêu cầu đã trừ hàng thành công, nhưng response bị mất; client hoặc queue gửi lại chính yêu cầu đó và kho bị trừ lần hai. Cách xử lý là **idempotency key ổn định** cùng bằng chứng đã commit hiệu ứng.

MongoDB hỗ trợ update nguyên tử trên một document, toán tử `$inc`, filter `$gte`, unique indexes, retryable writes và multi-document transactions. Nhưng **conditional update chống bán vượt tồn không tự chống request bị gửi lại**. Ngược lại, unique marker ở document khác với stock cũng không tự atomic.

Bài thuộc **Database Engine Document MongoDB → Thiết kế ứng dụng → Tồn kho: cập nhật có điều kiện và chống trừ số lượng nhiều lần**.

Mục tiêu:

1. Phân biệt `on_hand`, `available`, `reserved` và stock movement.
2. Định nghĩa invariant của mỗi inventory bucket theo tenant, kho và SKU.
3. Dùng `updateOne` với `available >= quantity` và `$inc` để chống oversell.
4. Đọc `matchedCount` và `modifiedCount` đúng cách.
5. Giải thích vì sao read–modify–save và retry `$inc` không an toàn.
6. Thiết kế stable reservation ID, request fingerprint và unique business key.
7. Dùng reservation ledger + transaction để commit marker cùng decrement.
8. Xử lý duplicate requests, duplicate key và unknown transaction commit result.
9. Thiết kế reserve, release, expire, fulfill đúng một lần.
10. Giải quyết nhiều SKU/kho, payment callback, outbox và event retries.
11. Viết Java Sync Driver và Spring Data MongoTemplate examples.
12. Xây concurrency tests, reconciliation, metrics và runbook.

> Hai hàng rào phải tồn tại cùng nhau: **điều kiện số lượng ở thời điểm ghi** và **bằng chứng chống lặp theo ID nghiệp vụ**.

---

## 1. Xác định đúng ý nghĩa của từng con số

Ví dụ inventory document:

    {
      _id: "tenant-a|wh-hcm|SKU-01",
      tenant_id: "tenant-a",
      warehouse_id: "wh-hcm",
      sku: "SKU-01",
      on_hand: NumberLong("10"),
      reserved: NumberLong("3"),
      available: NumberLong("7"),
      version: NumberLong("12"),
      updated_at: ISODate("2026-11-14T02:00:00Z")
    }

Trong mô hình mẫu:

| Field | Diễn giải |
|---|---|
| `on_hand` | Số đơn vị vật lý còn tại kho, bao gồm hàng đã được giữ |
| `reserved` | Số đơn vị đã giữ cho những reservations hiệu lực |
| `available` | Số đơn vị còn được phép giữ/bán |
| `tenant_id` | Bên sở hữu dữ liệu |
| `warehouse_id` | Kho thực tế |
| `sku` | Chủng loại sản phẩm |
| `version` | Thế hệ cập nhật cho optimistic concurrency |
| `updated_at` | Timestamp của thay đổi |

Công thức trong mô hình đơn giản:

    on_hand = available + reserved
    available >= 0
    reserved  >= 0
    on_hand   >= 0

Đây là **quy ước của mô hình này**, không phải công thức bắt buộc trong mọi hệ thống WMS. Nếu tồn có hàng lỗi, cách ly, in-transit, safety stock hay backorder, cần thêm fields và invariants đúng nghiệp vụ.

### 1.1. Reserve hai sản phẩm

    Trước: on_hand=10, reserved=3, available=7
    Sau:   on_hand=10, reserved=5, available=5

Sản phẩm chưa rời kho; chỉ không còn được hứa bán cho request khác.

### 1.2. Release reservation hai sản phẩm

    Trước: on_hand=10, reserved=5, available=5
    Sau:   on_hand=10, reserved=3, available=7

### 1.3. Fulfill và xuất kho hai sản phẩm

    Trước: on_hand=10, reserved=5, available=5
    Sau:   on_hand=8,  reserved=3, available=5

Không tăng available lúc ship: nó đã giảm khi reserve.

### 1.4. Nhập kho

Một lần receive 5 sản phẩm còn bán được sẽ tăng `on_hand` và `available` thêm 5, `reserved` giữ nguyên. Nếu inbound event bị gửi lại, vẫn cần chống cộng hai lần bằng movement ID.

---

## 2. Một document đại diện một inventory bucket

Một cách chia:

    tenant-a / wh-hcm / SKU-01 -> document A
    tenant-a / wh-hn  / SKU-01 -> document B
    tenant-a / wh-hcm / SKU-02 -> document C

Mỗi bucket có một ID ổn định. Không nhúng hàng triệu SKU và reservations vào một array trong một document khổng lồ.

Có thể tạo compound unique index:

    db.inventory.createIndex(
      {
        tenant_id: 1,
        warehouse_id: 1,
        sku: 1
      },
      {
        unique: true,
        name: "uq_inventory_bucket"
      }
    );

Nếu `_id` đã là composite key có encoding chặt chẽ, unique `_id` có thể đủ cho định danh, còn compound index thêm hay không phụ thuộc truy vấn. Không nối delimiter tùy tiện nếu tenant/SKU có thể chứa ký tự phân cách.

### 2.1. Vì sao atomic cấp document có ích?

`available` và `reserved` nằm trong **cùng document**, nên MongoDB có thể thay cả hai fields trong một write nguyên tử. Nếu nằm trong hai documents, cần transaction hoặc protocol đảm bảo consistency.

### 2.2. Hot SKU

Một sản phẩm rất hot có thể khiến nhiều requests cùng cập nhật một document; tăng shards không tự phân tán một document nóng. Vẫn cần benchmark contention, retry rate và cơ chế quota/escrow nếu thật sự cần scale sâu hơn.

---

## 3. Read–modify–save gây race condition

Cách viết không an toàn:

    Inventory inv = repository.findById(stockId)
        .orElseThrow();

    if (inv.getAvailable() >= quantity) {
        inv.setAvailable(
            inv.getAvailable() - quantity
        );
        repository.save(inv);
        return "RESERVED";
    }

    return "OUT_OF_STOCK";

Nếu available=1:

    T1 Request A đọc available=1
    T2 Request B đọc available=1
    T3 Request A check qty=1 -> OK
    T4 Request B check qty=1 -> OK
    T5 Request A save available=0
    T6 Request B save available=0
    T7 Cả hai báo RESERVED dù chỉ có 1 món hàng

Số available cuối vẫn là 0, nên chỉ kiểm tra “không âm” trong database chưa đủ để phát hiện business oversell.

### 3.1. Java lock không đủ

`synchronized` chỉ bảo vệ một JVM. Nhiều pods, services, job scripts và queue consumers vẫn có thể cùng ghi một MongoDB document. Cần bảo vệ predicate tại database write.

### 3.2. Nguyên tắc

Không đọc rồi quyết định một write vô điều kiện. Đưa **available >= quantity** vào filter của chính `updateOne`.

---

## 4. Atomic conditional decrement bằng mongosh

Chỉ chạy các lệnh sau trên lab:

    use inventory_lab

    db.inventory.insertOne({
      _id: "tenant-a|wh-hcm|SKU-01",
      tenant_id: "tenant-a",
      warehouse_id: "wh-hcm",
      sku: "SKU-01",
      on_hand: NumberLong("10"),
      reserved: NumberLong("3"),
      available: NumberLong("7"),
      version: NumberLong("12"),
      updated_at: new Date()
    });

Giữ hai đơn vị:

    const qty = NumberLong("2");

    const result = db.inventory.updateOne(
      {
        _id: "tenant-a|wh-hcm|SKU-01",
        tenant_id: "tenant-a",
        available: { $gte: qty }
      },
      {
        $inc: {
          available: NumberLong("-2"),
          reserved: NumberLong("2"),
          version: NumberLong("1")
        },
        $currentDate: {
          updated_at: true
        }
      }
    );

    printjson(result);

### 4.1. Vì sao đúng khi concurrent?

Hai clients cùng q=2, available ban đầu 2: một update giảm về 0; update kia không còn match predicate `available >= 2`. MongoDB đánh giá predicate trong write atomic trên document.

### 4.2. Vì sao giảm available và tăng reserved cùng lệnh?

Nếu gọi hai `updateOne` riêng, crash giữa chúng có thể phá phương trình `on_hand=available+reserved`. Một update kết hợp giữ được invariant tại cấp document.

### 4.3. Không dùng upsert

Không thêm `upsert:true` cho reserve. Khi available không đủ hoặc bucket không tồn tại, upsert có thể tìm cách insert record mới trái nghiệp vụ và gây duplicate key.

### 4.4. Validate quantity

Từ chối qty<=0, quá max domain, sai loại số và overflow. Nếu qty=-2, biểu thức giảm âm sẽ thành tăng kho.

---

## 5. Hiểu kết quả matched và modified

Với acknowledged updateOne:

    {
      acknowledged: true,
      matchedCount: 1,
      modifiedCount: 1,
      upsertedId: null
    }

| Matched | Modified | Nghĩa |
|---:|---:|---|
| 1 | 1 | Một bucket được thay đổi |
| 0 | 0 | Không có bucket phù hợp: có thể không đủ tồn, sai tenant hoặc ID thiếu |
| 1 | 0 | Match nhưng không thay đổi; hiếm với `$inc` q>0 |
| Chưa ACK | Không chắc | Xử lý write concern/network/unknown outcome |

`matchedCount=0` không tự chứng minh là hết hàng. Có thể cần lookup được authorize để phân loại missing/closed/insufficient; không tiết lộ sự tồn tại của bucket thuộc tenant khác.

Khi UI hiển thị “còn 1 sản phẩm”, số đó có thể stale. Chỉ một **write commit thỏa predicate** mới xác nhận reservation thành công.

---

## 6. Bẫy: conditional decrement vẫn trừ hai lần

Giả sử available=10:

    Client gửi R100, qty=2
       |
    MongoDB cập nhật available 10 -> 8
       |
    Server commit nhưng response bị mất
       |
    Client timeout và gửi lại R100
       |
    MongoDB cập nhật available 8 -> 6

Cả hai lần `available>=2` đều đúng. Kết quả là double decrement.

### 6.1. Những nguồn retry

- API gateway/client timeout.
- Người dùng bấm nút hai lần.
- Queue redelivery at-least-once.
- Worker restart sau DB commit nhưng trước message ACK.
- Payment/shipping callback gửi lặp.
- Batch/job replay.
- Application retry policy tự gọi lại method.

### 6.2. Retryable writes không thay business idempotency

MongoDB Driver có retryable writes cho một số operation với protocol identity. Nhưng một HTTP request mới hoặc consumer xử lý lại message thường tạo MongoDB operation mới. Tầng nghiệp vụ vẫn phải nhận ra cùng reservation ID.

### 6.3. Hai câu hỏi khác nhau

- **Condition:** “Kho hiện đủ cho q không?”
- **Idempotency:** “Nghiệp vụ R100 đã được áp dụng chưa?”

Cần trả lời **cả hai** trước khi coi reserve đúng.

---

## 7. Thiết kế stable idempotency key

Ví dụ request:

    {
      "reservationId": "resv-2026-000123",
      "orderId": "ORD-101",
      "lineId": "LINE-1",
      "warehouseId": "wh-hcm",
      "sku": "SKU-01",
      "quantity": 2
    }

### 7.1. Giữ nguyên ID qua retry

Nếu request R100 bị timeout và gửi lại, vẫn dùng `reservationId=R100`. Không tạo UUID mới theo từng retry attempt.

### 7.2. ID đúng phạm vi nghiệp vụ

Có thể dùng stable identity dựa trên:

    tenant_id + order_id + line_id + generation

Nếu cùng line có thể tạo reservation mới sau khi release/expire, dùng một generation mới. Đừng dùng lại terminal ID để “đặt lại”.

### 7.3. Key reuse sai tham số

R100 lần đầu SKU-01 qty=2, lần sau SKU-02 qty=5 phải trả **idempotency conflict**, không thay đổi inventory. So sánh các immutable fields hoặc canonical request fingerprint (tenant, stock ID, SKU, order, line, qty, type).

### 7.4. Retention

Marker phải được giữ đủ dài cho replay/queue retention, late callbacks, dispute hoặc legal policy. Nếu TTL xóa proof quá sớm, delayed retry có thể được coi là request mới và trừ lại.

### 7.5. Duplicate checkout trước reservation

Nếu cùng hành động bấm mua sinh **hai order IDs mới**, mỗi order tạo reservation khác thì ledger không nhận là duplicate. Cần idempotency ở cả API checkout/order creation, không chỉ inventory.

---

## 8. Reservation ledger

Một collection `inventory_reservations`:

    {
      _id: "resv-2026-000123",
      tenant_id: "tenant-a",
      order_id: "ORD-101",
      line_id: "LINE-1",
      stock_id: "tenant-a|wh-hcm|SKU-01",
      warehouse_id: "wh-hcm",
      sku: "SKU-01",
      quantity: NumberLong("2"),
      request_fingerprint: "sha256-canonical-params",
      state: "ACTIVE",
      created_at: ISODate("2026-11-14T03:00:00Z"),
      expires_at: ISODate("2026-11-14T03:15:00Z")
    }

Ledger giữ:

- Stable ID và unique business key.
- Tham số immutable để kiểm tra reuse.
- State `ACTIVE`, `RELEASED`, `EXPIRED`, `FULFILLED`.
- Chứng cứ request đã commit.
- Thông tin reconcile stock counter.
- Thời gian/nguồn yêu cầu phục vụ audit.

`_id` đã có unique index. Có thể thêm compound unique index cho tenant/order/line/generation khi schema thực sự dùng đủ các fields đó:

    db.inventory_reservations.createIndex(
      {
        tenant_id: 1,
        order_id: 1,
        line_id: 1,
        generation: 1
      },
      {
        unique: true,
        name: "uq_reservation_business"
      }
    );

Nếu không dùng generation, bỏ field đó khỏi index và định nghĩa một reservation duy nhất trên mỗi order line. Schema validation phải thống nhất với key design.

---

## 9. Vì sao chỉ thêm marker unique vẫn chưa đủ?

Sai lầm thứ nhất:

    1. insert reservation marker R100
    2. decrement inventory

Crash giữa hai bước: marker có nhưng stock chưa giảm. Retry thấy marker và trả ALREADY_RESERVED **sai**.

Sai lầm thứ hai:

    1. decrement inventory
    2. insert reservation marker R100

Crash giữa hai bước: stock đã giảm nhưng marker không tồn tại. Retry lại decrement lần thứ hai.

### 9.1. Unique index chỉ bảo vệ marker

Nó không tự đảm bảo hai writes trên **hai documents** commit cùng nhau.

### 9.2. Phương án phổ biến

Dùng multi-document transaction chứa cả insert reservation và conditional update inventory. Khi không đủ hàng, throw/abort toàn transaction, không lưu marker ACTIVE.

### 9.3. Các lựa chọn khác

Single-document atomic protocol có marker bounded hoặc một saga có state/recovery được chứng minh cũng có thể đúng. Nhưng đừng dùng hai writes không transaction rồi giả định “thực tế hiếm khi crash”.

---

## 10. Transaction reserve: trình tự

    BEGIN TRANSACTION
        |
        +-- Tìm reservation R100
        |      +-- có, cùng fingerprint, ACTIVE: ALREADY_RESERVED
        |      +-- có, terminal: trả terminal outcome
        |      +-- có, khác fingerprint: CONFLICT
        |
        +-- Insert R100 với state ACTIVE
        |
        +-- updateOne inventory:
        |      filter stock_id + tenant + available >= q
        |      $inc available -q, reserved +q
        |      matched=0: abort
        |
    COMMIT: cả marker và inventory cùng thành công

### 10.1. Requirements

Multi-document transactions yêu cầu replica set/sharded cluster với MongoDB version phù hợp. Local standalone `mongod` không đủ cho bài lab transaction; single-member replica set có thể sử dụng.

### 10.2. Ngắn và giới hạn

Không thực hiện HTTP call, email hoặc payment charge trong transaction. Chỉ đụng các MongoDB documents cần thiết. Transaction quá dài làm tăng write conflict, latency và resource consumption.

### 10.3. Không đổi ID khi retry

Nếu order request cùng nghiệp vụ sinh marker mới, transaction vẫn có thể giảm stock hai lần. Identity chính xác quan trọng không kém transaction.

---

## 11. Java Sync Driver: conditional update

Đây là phương thức chống **overselling**, chưa chống duplicate business request.

    import com.mongodb.client.MongoCollection;
    import com.mongodb.client.result.UpdateResult;
    import org.bson.Document;

    import static com.mongodb.client.model.Filters.and;
    import static com.mongodb.client.model.Filters.eq;
    import static com.mongodb.client.model.Filters.gte;
    import static com.mongodb.client.model.Updates.combine;
    import static com.mongodb.client.model.Updates.currentDate;
    import static com.mongodb.client.model.Updates.inc;

    public final class StockUpdate {

        public static boolean reserveConditional(
                MongoCollection<Document> inventory,
                String stockId,
                String tenantId,
                long quantity) {

            if (quantity <= 0) {
                throw new IllegalArgumentException(
                    "Quantity must be positive"
                );
            }

            UpdateResult result = inventory.updateOne(
                and(
                    eq("_id", stockId),
                    eq("tenant_id", tenantId),
                    gte("available", quantity)
                ),
                combine(
                    inc("available", -quantity),
                    inc("reserved", quantity),
                    inc("version", 1L),
                    currentDate("updated_at")
                )
            );

            if (!result.wasAcknowledged()) {
                throw new IllegalStateException(
                    "Unacknowledged stock write"
                );
            }

            return result.getMatchedCount() == 1;
        }
    }

### 11.1. Chỉ trả success theo committed result

Nếu client không nhận được response, đừng kết luận update thất bại; trạng thái có thể chưa rõ. Nếu không có ledger, application không thể xác định request này đã được áp dụng chỉ bằng cách nhìn available hiện tại.

### 11.2. Kiểu số

Thống nhất BSON Int64/Java long. Không cho qty âm, không dùng floating point cho số lượng nguyên, kiểm soát upper bounds/overflow và tránh field null/string trong stock counter.

---

## 12. Java Sync Driver: transaction giữ chỗ idempotent

Ví dụ Java 17+ dùng `record` để biểu diễn request. Các collections đã được tạo, index và deployment hỗ trợ transaction.

    import com.mongodb.ReadConcern;
    import com.mongodb.ReadPreference;
    import com.mongodb.TransactionOptions;
    import com.mongodb.WriteConcern;

    import com.mongodb.client.ClientSession;
    import com.mongodb.client.MongoClient;
    import com.mongodb.client.MongoCollection;
    import com.mongodb.client.result.UpdateResult;

    import org.bson.Document;
    import java.util.Objects;

    import static com.mongodb.client.model.Filters.and;
    import static com.mongodb.client.model.Filters.eq;
    import static com.mongodb.client.model.Filters.gte;
    import static com.mongodb.client.model.Updates.combine;
    import static com.mongodb.client.model.Updates.inc;

    public class ReservationService {

        public enum Outcome {
            RESERVED, ALREADY_RESERVED
        }

        public record Request(
            String reservationId,
            String tenantId,
            String stockId,
            String sku,
            long quantity,
            String fingerprint
        ) {}

        private final MongoClient client;
        private final MongoCollection<Document> inventory;
        private final MongoCollection<Document> reservations;

        public ReservationService(
            MongoClient client,
            MongoCollection<Document> inventory,
            MongoCollection<Document> reservations
        ) {
            this.client = client;
            this.inventory = inventory;
            this.reservations = reservations;
        }

        public Outcome reserve(Request req) {
            if (req.quantity() <= 0) {
                throw new IllegalArgumentException("quantity");
            }

            TransactionOptions options =
                TransactionOptions.builder()
                    .readConcern(ReadConcern.SNAPSHOT)
                    .writeConcern(WriteConcern.MAJORITY)
                    .readPreference(ReadPreference.primary())
                    .build();

            try (ClientSession session = client.startSession()) {
                return session.withTransaction(() -> {

                    Document old = reservations.find(
                        session,
                        eq("_id", req.reservationId())
                    ).first();

                    if (old != null) {
                        checkSame(old, req);

                        if ("ACTIVE".equals(
                                old.getString("state"))) {
                            return Outcome.ALREADY_RESERVED;
                        }

                        throw new IllegalStateException(
                            "Reservation already terminal"
                        );
                    }

                    Document marker = new Document()
                        .append("_id", req.reservationId())
                        .append("tenant_id", req.tenantId())
                        .append("stock_id", req.stockId())
                        .append("sku", req.sku())
                        .append("quantity", req.quantity())
                        .append(
                            "request_fingerprint",
                            req.fingerprint()
                        )
                        .append("state", "ACTIVE")
                        .append(
                            "created_at",
                            new java.util.Date()
                        );

                    reservations.insertOne(session, marker);

                    UpdateResult r = inventory.updateOne(
                        session,
                        and(
                            eq("_id", req.stockId()),
                            eq("tenant_id", req.tenantId()),
                            gte("available", req.quantity())
                        ),
                        combine(
                            inc("available", -req.quantity()),
                            inc("reserved", req.quantity()),
                            inc("version", 1L)
                        )
                    );

                    if (r.getMatchedCount() != 1) {
                        throw new InsufficientStock();
                    }

                    return Outcome.RESERVED;
                }, options);
            }
        }

        private static void checkSame(
            Document marker,
            Request req
        ) {
            boolean same =
                Objects.equals(
                    marker.getString("tenant_id"),
                    req.tenantId()
                )
                && Objects.equals(
                    marker.getString("stock_id"),
                    req.stockId()
                )
                && Objects.equals(
                    marker.getString("sku"),
                    req.sku()
                )
                && marker.getLong("quantity")
                    == req.quantity()
                && Objects.equals(
                    marker.getString("request_fingerprint"),
                    req.fingerprint()
                );

            if (!same) {
                throw new IllegalArgumentException(
                    "Idempotency key reused with changed input"
                );
            }
        }

        public static class InsufficientStock
                extends RuntimeException {
            public InsufficientStock() {
                super("Inventory insufficient");
            }
        }
    }

### 12.1. Marker và stock commit cùng nhau

Nếu marker insert được thực hiện nhưng stock không match, throw làm transaction abort, tránh marker ACTIVE giả.

### 12.2. Driver có thể chạy callback hơn một lần

`withTransaction` có retry semantics cho transient transaction errors. Không gọi payment provider, gửi email hoặc publish message trực tiếp trong callback.

### 12.3. Cạnh tranh cùng ID

Hai transactions cùng R100 có thể cùng đọc “chưa có”, sau đó một bên nhận duplicate key/write conflict. Handler ngoài transaction cần read/reconcile marker đã commit, kiểm tra fingerprint và state. Không coi mọi duplicate key là successful duplicate.

### 12.4. Terminal state

Nếu R100 đã RELEASED/EXPIRED/FULFILLED, retry reserve không được giảm kho. Ví dụ ném domain exception; production có thể trả typed terminal outcome.

---

## 13. Unknown commit result và retry đúng

Timeline:

    T1 Transaction insert reservation R100
    T2 Transaction decrement available 10 -> 8
    T3 MongoDB commit thành công
    T4 ACK commit mất trên mạng
    T5 Client thấy timeout / unknown commit
    T6 Client retry R100

Cách xử lý:

1. Giữ nguyên R100 và canonical request fingerprint.
2. Driver retry commit theo supported API khi thích hợp.
3. Nếu outcome vẫn unknown, **không trả chắc chắn thất bại**.
4. Query reservation ledger để xác nhận committed state với primary/read consistency phù hợp.
5. Nếu ACTIVE và fingerprint đúng, kết luận đã reserve; không trừ lại.
6. Nếu chưa phân giải được, dùng bounded backoff/reconciliation/PENDING response.
7. Không tự tạo reservation ID mới để né lỗi.

### 13.1. Phân biệt error labels

`TransientTransactionError` thường cho phép retry toàn transaction theo contract. `UnknownTransactionCommitResult` liên quan outcome của commit, nên cần retry commit/reconcile thay vì tự chạy một business operation mới.

### 13.2. Một lần đọc “không thấy” chưa chắc là thất bại

Một competing transaction có thể vẫn đang commit hoặc một secondary có lag. Không suy từ absence trong một lần đọc thành “kho chưa bị trừ”.

### 13.3. Đừng gọi `$inc` mù từ HTTP retry

Retry một method mới không nhất thiết giữ MongoDB protocol operation identity của retryable writes. **Business ID** mới là hàng rào xuyên HTTP, queue và process restarts.

---

## 14. Spring Data MongoTemplate

Một update có điều kiện tương đương:

    import com.mongodb.client.result.UpdateResult;
    import org.springframework.data.mongodb.core.MongoTemplate;
    import org.springframework.data.mongodb.core.query.Criteria;
    import org.springframework.data.mongodb.core.query.Query;
    import org.springframework.data.mongodb.core.query.Update;

    public final class InventoryTemplateService {

        private final MongoTemplate template;

        public InventoryTemplateService(
            MongoTemplate template
        ) {
            this.template = template;
        }

        public boolean reserveConditional(
            String stockId,
            String trustedTenantId,
            long qty
        ) {
            if (qty <= 0) {
                throw new IllegalArgumentException("qty");
            }

            Query query = Query.query(
                Criteria.where("_id").is(stockId)
                    .and("tenant_id").is(trustedTenantId)
                    .and("available").gte(qty)
            );

            Update update = new Update()
                .inc("available", -qty)
                .inc("reserved", qty)
                .inc("version", 1L)
                .currentDate("updated_at");

            UpdateResult result = template.updateFirst(
                query,
                update,
                "inventory"
            );

            if (!result.wasAcknowledged()) {
                throw new IllegalStateException(
                    "Write unacknowledged"
                );
            }

            return result.getMatchedCount() == 1;
        }
    }

### 14.1. Tên trường

Ví dụ dùng overload theo collection name nên tên paths là BSON keys. Với typed entity có `@Field`, Spring Data mapping có thể chuyển Java property sang BSON. Kiểm tra đúng mapping và tenant filter.

### 14.2. Spring transaction manager

    import org.springframework.context.annotation.Bean;
    import org.springframework.context.annotation.Configuration;
    import org.springframework.data.mongodb.MongoDatabaseFactory;
    import org.springframework.data.mongodb.MongoTransactionManager;

    @Configuration
    class MongoTxConfig {

        @Bean
        MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory
        ) {
            return new MongoTransactionManager(factory);
        }
    }

Sau đó dùng service method `@Transactional(transactionManager="mongoTransactionManager")` để insert marker và update stock cùng transaction. Cần gọi qua Spring-managed proxy; self-invocation có thể bypass transaction advice. Quan trọng: đoạn `reserveConditional` riêng lẻ ở trên **chưa** chống double decrement, phải tích hợp ledger như mô hình transaction đã giải thích.

### 14.3. `@Version` khác idempotency

Spring Data `@Version` có thể hỗ trợ optimistic locking với `save` ở các đường API phù hợp, nhưng template update không tự thêm expected version filter cho mọi lệnh; và version không xác định request R100 đã xử lý hay chưa.

---

## 15. Reservation state machine

    NEW
     |
     v
    ACTIVE
      | \
      |  +----- FULFILLED
      |
      +-------- RELEASED
      |
      +-------- EXPIRED

Các trạng thái terminal không tự quay lại ACTIVE bằng cùng ID.

| Transition | Thay đổi inventory |
|---|---|
| NEW → ACTIVE | available−q, reserved+q |
| ACTIVE → RELEASED | available+q, reserved−q |
| ACTIVE → EXPIRED | available+q, reserved−q |
| ACTIVE → FULFILLED | on_hand−q, reserved−q |
| RELEASED/EXPIRED → ACTIVE cùng ID | Không cho phép |
| Terminal → terminal do duplicate request | Trả outcome đã ghi, không thay stock |

### 15.1. Release đúng một lần

Cùng transaction:

- Đọc reservation R100.
- Nếu đã RELEASED, trả ALREADY_RELEASED.
- Nếu FULFILLED, không được release lại.
- Chỉ khi ACTIVE, CAS ACTIVE→RELEASED.
- Update inventory `reserved>=q`, `$inc available:+q` và `reserved:-q`.
- Nếu stock update không match, abort để không lưu state sai.

### 15.2. Vì sao `reserved>=q` chưa đủ?

Reserved tổng còn có thể lớn vì có những reservations khác. Nếu callback cancel R100 chạy hai lần, lần thứ hai có thể vẫn match và cộng available sai. **CAS trên reservation state** mới ngăn double release.

### 15.3. Fulfillment

Khi hàng thực sự rời kho, CAS ACTIVE→FULFILLED cùng transaction giảm `on_hand` và `reserved`, giữ `available` không đổi. Retry ship callback không được trừ thêm.

### 15.4. Refund và return

Refund tài chính không đồng nghĩa hàng đã quay lại kho. Return có thể cần kiểm định, damaged/quarantine và stock movement riêng trước khi tăng available.

---

## 16. Hết hạn giữ chỗ và TTL trap

Worker cần tìm:

    db.inventory_reservations.find({
      state: "ACTIVE",
      expires_at: { $lte: new Date() }
    }).sort({
      expires_at: 1,
      _id: 1
    }).limit(100);

Trong transaction, worker kiểm tra còn ACTIVE và quá hạn, chuyển ACTIVE→EXPIRED, rồi tăng available/giảm reserved trong cùng commit.

### 16.1. TTL không tự giải phóng hàng

TTL index chỉ xóa reservation document, **không tự cập nhật inventory**. Nếu xóa ACTIVE marker, vừa không trả hàng vừa mất idempotency proof.

### 16.2. TTL dọn terminal records

Có thể dùng field `delete_after_at` cho các records đã terminal sau retention đủ dài, nhưng delayed retries có thể đến sau TTL. Phải chứng minh retention không khiến nghiệp vụ cũ được xử lý lại.

### 16.3. TTL không đúng tuyệt đối theo deadline

TTL deletion là background process và có thể trễ. Expiration worker phải dựa vào `expires_at` và state condition, không dựa vào việc marker đã bị xóa.

### 16.4. Race expire vs payment

Payment callback và expiry worker cùng tranh ACTIVE. Chỉ một transition terminal được commit. Order/payment state machine cần xử lý trường hợp tiền đến sau expiry, không được tự giữ lại một reservation đã terminal.

---

## 17. Nhiều SKU, nhiều kho và transaction

Một order:

    {
      "orderId": "ORD-101",
      "lines": [
        { "sku": "SKU-01", "warehouse": "HCM", "qty": 2 },
        { "sku": "SKU-02", "warehouse": "HCM", "qty": 1 }
      ]
    }

Hai SKU là hai inventory documents.

### 17.1. All-or-nothing

Nếu SKU-01 đủ nhưng SKU-02 thiếu, một luồng reserve hai updates riêng lẻ có thể giữ một phần. Nếu business yêu cầu toàn đơn được giữ hoặc không giữ gì, dùng transaction cho tất cả stock updates + reservation markers + order state.

### 17.2. Partial reservation

Nếu business cho phép backorder/partial fulfillment, phải ghi rõ line-level state và compensation. Không trả “đã giữ toàn bộ” trong khi chỉ một phần thành công.

### 17.3. Gom line items trùng bucket

Hai lines cùng tenant+warehouse+SKU phải được cộng quantity có kiểm tra overflow, tránh khó đối soát và giảm số lần chạm cùng document.

### 17.4. Multi-warehouse

Ví dụ HCM có 3 và HN có 4, order cần 5 có thể lấy 3+2 nếu policy cho phép. Đây là nhiều stock documents; cần transaction hoặc saga có state và recovery, không chỉ đọc tổng available rồi giảm một kho tùy ý.

### 17.5. Độ dài transaction

Giữ transaction ngắn, có stable order/reservation identity, sắp bucket IDs theo thứ tự nhất quán khi hữu ích và retry bounded khi write conflict.

## 18. Single-document idempotency: có thể đúng nhưng khó mở rộng

Một phương án không cần transaction là lưu các operation IDs đã áp dụng ngay trong stock document:

    db.inventory.updateOne(
      {
        _id: "tenant-a|wh-hcm|SKU-01",
        available: { $gte: NumberLong("2") },
        applied_ids: { $ne: "R100" }
      },
      {
        $inc: {
          available: NumberLong("-2"),
          reserved: NumberLong("2")
        },
        $addToSet: {
          applied_ids: "R100"
        }
      }
    );

### 18.1. Điều gì đúng?

Filter không có ID R100 và effect decrement/add marker cùng trong một atomic document update. Hai cùng ID requests sẽ không cùng match nếu marker được lưu đúng.

### 18.2. Vì sao không dùng rộng rãi?

`applied_ids` tăng vô hạn qua các năm. MongoDB document có giới hạn BSON 16 MiB; array càng lớn gây hot document, write amplification và khó quản lý.

### 18.3. Vì sao không cắt ID cũ?

Nếu xóa R100 khỏi array quá sớm, một delayed retry R100 có thể trừ tiếp. Không thể xóa markers chỉ vì “đã qua 5 phút” nếu queue có thể replay sau một ngày.

### 18.4. `$addToSet` đơn lẻ không chống double decrement

Nếu không có filter `applied_ids:{$ne:"R100"}`, update chứa `$inc` vẫn chạy lần hai dù `$addToSet` không thêm duplicate.

### 18.5. Kết luận

Chỉ dùng approach này nếu operation markers được **bounded** với generation/retention rõ và bảo đảm late retries không vượt retention. Với tồn kho hoạt động lâu dài, reservation ledger riêng + transaction thường dễ vận hành hơn.

---

## 19. Optimistic version không thay idempotency key

Có thể dùng expected version:

    db.inventory.updateOne(
      {
        _id: "tenant-a|wh-hcm|SKU-01",
        version: NumberLong("12"),
        available: { $gte: NumberLong("2") }
      },
      {
        $inc: {
          available: NumberLong("-2"),
          reserved: NumberLong("2"),
          version: NumberLong("1")
        }
      }
    );

### 19.1. Version bảo vệ cái gì?

Hai writers đọc cùng version=12 thì chỉ một CAS update thành công. Điều đó giúp tránh lost update trên snapshot cũ.

### 19.2. Vì sao chưa đủ chống double decrement?

Một HTTP retry có thể đọc version=13 và thực hiện cùng nghiệp vụ R100 thêm lần nữa. Version chỉ nói “document đã đổi” chứ không nói “R100 đã áp dụng”.

### 19.3. Phân biệt

| Cơ chế | Câu hỏi trả lời |
|---|---|
| `available >= q` | Hiện còn đủ hàng không? |
| `version == expected` | State đã bị writer khác thay từ lúc đọc chưa? |
| `reservation_id` unique | Nghiệp vụ này đã được xử lý chưa? |
| Multi-document transaction | Marker và counter thay cùng commit chưa? |
| Reconciliation | Các dữ liệu hiện có có còn thỏa invariant không? |

### 19.4. Version khác schema version

`schema_version` đánh dấu cấu trúc document, không phải optimistic update counter. Đừng dùng một field cho cả hai mục đích.

---

## 20. Stock movement ledger: mọi biến động đều có identity

Không chỉ reserve cần idempotency. Nhận hàng, giao hàng, trả hàng và điều chỉnh tồn cũng có thể lặp.

Một `inventory_movements` document:

    {
      _id: "MOVE-1001",
      tenant_id: "tenant-a",
      stock_id: "tenant-a|wh-hcm|SKU-01",
      type: "RECEIVE",
      quantity: NumberLong("5"),
      external_reference: "PO-987",
      created_at: new Date()
    }

### 20.1. Nhập kho

    db.inventory.updateOne(
      { _id: "tenant-a|wh-hcm|SKU-01" },
      {
        $inc: {
          on_hand: NumberLong("5"),
          available: NumberLong("5")
        }
      }
    );

Nếu event MOVE-1001 được phát hai lần, lệnh trên cộng 10 thay vì 5. Unique movement ID và movement marker phải commit atomic với inventory update hoặc có event-sourced protocol tương đương.

### 20.2. Xuất kho

`SHIP` không chỉ đơn giản là giảm `on_hand`. Nếu hàng đã reserve, cần chuyển reservation ACTIVE→FULFILLED và giảm `reserved` đồng transaction.

### 20.3. Kiểm kê/điều chỉnh

Một `set available=100` từ snapshot cũ có thể ghi đè các reservations mới. Dùng adjustment movement có lý do, before/after audit, version CAS và quy trình quản lý quyền.

### 20.4. Transfer giữa kho

Chuyển 5 món từ HCM sang HN phải có source/destination movement IDs và in-transit policy; cập nhật hai stock buckets cần transaction hoặc saga có reconciliation.

### 20.5. Trả hàng

Return sau refund chưa chắc được cộng available. Cần nhận hàng, kiểm tra chất lượng và phân loại hàng bán lại được/không được.

---

## 21. Schema, indexes và guards ở database

### 21.1. Unique inventory bucket

    db.inventory.createIndex(
      {
        tenant_id: 1,
        warehouse_id: 1,
        sku: 1
      },
      {
        unique: true
      }
    );

### 21.2. Unique reservation business key

    db.inventory_reservations.createIndex(
      {
        tenant_id: 1,
        order_id: 1,
        line_id: 1
      },
      {
        unique: true
      }
    );

Chỉ dùng key này nếu mỗi order line có đúng một reservation trong toàn vòng đời. Nếu có attempts/generations mới sau cancel, thêm generation và bảo đảm schema lưu giá trị.

### 21.3. Index cho expiration worker

    db.inventory_reservations.createIndex({
      state: 1,
      expires_at: 1,
      _id: 1
    });

### 21.4. Index cho reconciliation

    db.inventory_reservations.createIndex({
      tenant_id: 1,
      state: 1,
      stock_id: 1
    });

Đo workload thực. Có quá nhiều indexes sẽ làm writes chậm, nhất là khi state thay đổi thường xuyên.

### 21.5. Validation cho số không âm

Trên một collection **mới dùng trong lab**, ví dụ:

    db.createCollection("inventory_guarded", {
      validator: {
        $jsonSchema: {
          bsonType: "object",
          required: [
            "tenant_id",
            "warehouse_id",
            "sku",
            "on_hand",
            "available",
            "reserved"
          ],
          properties: {
            on_hand: {
              bsonType: "long",
              minimum: 0
            },
            available: {
              bsonType: "long",
              minimum: 0
            },
            reserved: {
              bsonType: "long",
              minimum: 0
            }
          }
        }
      }
    });

Validator chỉ là một lớp bảo vệ shape/nonnegative. Nó **không** tự bảo đảm `on_hand=available+reserved`, uniqueness theo business effect hay stock/reservation atomic consistency. Nếu data legacy có Int32 thay Int64, cần migration/validator rollout trước khi áp strict.

### 21.6. Điều kiện quyền tenant

Tất cả writes phải scope theo trusted tenant. Không dựa trên tenant ID do user tự đặt trong body chưa xác thực.

---

## 22. API contract idempotent

Ví dụ REST request (biểu diễn text, không phải cú pháp Java):

    POST /api/inventory/reservations
    Idempotency-Key: R100
    Content-Type: application/json

    {
      "orderId": "ORD-101",
      "lineId": "LINE-1",
      "warehouseId": "wh-hcm",
      "sku": "SKU-01",
      "quantity": 2
    }

### 22.1. Lần đầu commit

    {
      "reservationId": "R100",
      "state": "ACTIVE",
      "quantity": 2,
      "result": "RESERVED"
    }

### 22.2. Retry cùng ID và cùng payload

    {
      "reservationId": "R100",
      "state": "ACTIVE",
      "quantity": 2,
      "result": "ALREADY_RESERVED"
    }

Không trừ tồn thêm lần nào.

### 22.3. Hết hàng

    {
      "reservationId": "R101",
      "result": "OUT_OF_STOCK"
    }

Nếu transaction abort khi hết hàng, marker có thể không được tạo. Retry R101 **sau khi kho đã được nhập thêm** có thể thành công. Nếu API cần giữ nguyên kết quả rejected cho mọi retry, phải lưu cả rejection result theo protocol phù hợp; hãy định nghĩa rõ requirement.

### 22.4. Outcome chưa rõ

Nếu commit result unknown, trả trạng thái `PENDING/UNKNOWN` hoặc response retryable có reservation ID và cơ chế lookup. Đừng nói “chưa giữ hàng” khi MongoDB có thể đã commit.

### 22.5. Key reuse với payload khác

Trả conflict, không ghi đè dữ liệu của marker cũ, không âm thầm trừ theo quantity mới.

### 22.6. Scope thời gian

Một idempotency ID phải còn hiệu lực ít nhất suốt thời gian clients/queues có thể replay. Với inventory ở hệ thống tài chính hoặc fulfillment, retention còn phải xét audit/compliance.

---

## 23. Tách order state khỏi stock state

Một order có thể:

- `PENDING_PAYMENT` sau reserve.
- `PAID` sau thanh toán thành công.
- `CANCELLED` trước fulfillment.
- `SHIPPED` khi giao kho.
- `REFUNDED` sau hoàn tiền.

Reservation có vòng đời riêng `ACTIVE/EXPIRED/RELEASED/FULFILLED`. Không suy:

- Paid == shipped.
- Refunded == returned to available stock.
- Cancelled callback == chắc chắn stock chưa trừ.
- Order creation == stock reserve đã commit.

### 23.1. Những transition nhiều documents

Nếu đặt hàng phải tạo order, reserve nhiều SKU và outbox event all-or-nothing, các documents đó phải ở cùng transaction hoặc một saga có compensation. Không chỉ update inventory rồi gọi order service và giả định hai hệ thống tự atomic.

### 23.2. Outbox event

Ví dụ:

    {
      _id: "EVT-R100-RESERVED",
      reservation_id: "R100",
      type: "InventoryReserved",
      payload: {
        order_id: "ORD-101",
        quantity: NumberLong("2")
      },
      published_at: null
    }

Outbox insert trong **cùng MongoDB transaction**; relay publish sau commit. Nếu relay crash sau khi publish nhưng trước khi đánh dấu đã publish, consumer vẫn có thể nhận duplicate và cần dedup event ID.

### 23.3. Không charge payment trong transaction callback

MongoDB không rollback được charge đã gửi tới provider bên ngoài. Callback transaction có thể chạy lại; external effect cần idempotency key của provider và state machine tương ứng.

---

## 24. Multi-tenant và security

### 24.1. Trusted tenant

Trong HTTP service, `tenantId` phải lấy từ authenticated principal/session, không chỉ từ JSON client. Các queries và writes chứa tenant condition.

### 24.2. SKU và warehouse ownership

Stock ID do backend xây có thể chứa tenant; nhưng vẫn phải xác nhận SKU/kho thuộc tenant, user có quyền đặt hàng và stock bucket được active.

### 24.3. Tránh mass assignment

Không chấp nhận request body tùy ý có `available`, `reserved`, `on_hand`, `tenant_id` hoặc `state` rồi map thẳng sang `$set`. Chỉ service có quyền cao mới điều khiển movement.

### 24.4. Không log secrets/PII

Khi debug, log reservation ID, stock bucket ID, request fingerprint, matched/modified, transaction status và retry count; redact customer/payment data.

### 24.5. Không dùng exception detail để lộ data cross-tenant

Nếu request chọn stock ID thuộc tenant khác, có thể trả error chung theo API policy. Nội bộ audit chi tiết với restricted access.

---

## 25. Không đọc secondary stale để xác nhận reserve

MongoDB replica set có primary và secondary; secondary reads có thể lag. Một UI đọc available từ secondary rồi hiển thị “còn 5” không phải bằng chứng còn hàng khi một request reserve đến server.

### 25.1. Source of truth là conditional write

Predicate `available>=quantity` phải nằm trong write. Nếu client dùng cached value để quyết định bán, có thể oversell dù cache nhanh.

### 25.2. Write concern

`WriteConcern.MAJORITY` cho transaction commit giúp durability theo replicated deployment semantics. Nó không loại bỏ unknown commit outcome trên network.

### 25.3. Read concern và outcome lookup

Sau timeout, tra reservation ledger bằng primary/read concern phù hợp và xét lag/transaction in-flight. Một lần đọc không thấy marker chưa chắc operation đã thất bại.

### 25.4. Retryable writes vs at-least-once delivery

Retry protocol driver không đảm bảo exactly-once effect trên toàn HTTP/event architecture. Business ID và ledger vẫn cần.

---

## 26. Reconciliation: tìm stock counter lệch ledger

Nếu mô hình coi `reserved` là tổng quantity của những reservations còn ACTIVE, ta có thể tính theo ledger:

    db.inventory_reservations.aggregate([
      {
        $match: {
          tenant_id: "tenant-a",
          state: "ACTIVE"
        }
      },
      {
        $group: {
          _id: "$stock_id",
          ledger_reserved: { $sum: "$quantity" },
          reservation_count: { $sum: 1 }
        }
      },
      {
        $lookup: {
          from: "inventory",
          localField: "_id",
          foreignField: "_id",
          as: "bucket"
        }
      },
      {
        $unwind: {
          path: "$bucket",
          preserveNullAndEmptyArrays: true
        }
      },
      {
        $project: {
          _id: 1,
          ledger_reserved: 1,
          inventory_reserved: "$bucket.reserved",
          difference: {
            $subtract: [
              { $ifNull: ["$bucket.reserved", 0] },
              "$ledger_reserved"
            ]
          }
        }
      },
      {
        $match: {
          difference: { $ne: 0 }
        }
      }
    ]);

### 26.1. Giới hạn của truy vấn

Pipeline xuất phát từ ACTIVE reservations nên không liệt kê buckets **không có ACTIVE reservations** nhưng reserved counter khác 0. Cần query riêng cho trường hợp đó.

### 26.2. Concurrent changes

Nếu đang có writes, một truy vấn dài có thể quan sát trạng thái khác thời điểm theo read concern và execution semantics. Dùng snapshot thích hợp hoặc lặp reconciliation và ghi nhận consistency window; không sửa ngay một mismatch thoáng qua.

### 26.3. Ledger phải đúng contract

Nếu state `CONFIRMED` cũng giữ stock hoặc nếu reserved đại diện cả backorders, phải điều chỉnh predicate/group. Không được thay invariant bằng script đơn giản sai domain.

### 26.4. Không tự overwrite counter

Khi thấy difference, phải xác minh reservation events, order state, movement ledger, physical stock và concurrency. Sửa bằng adjustment có operation ID và audit, không chỉ set số cho bằng.

---

## 27. Tìm counters âm và bất nhất

Counter âm:

    db.inventory.find({
      tenant_id: "tenant-a",
      $or: [
        { available: { $lt: 0 } },
        { reserved: { $lt: 0 } },
        { on_hand: { $lt: 0 } }
      ]
    });

Kiểm tra phương trình trong mô hình đơn giản:

    db.inventory.find({
      tenant_id: "tenant-a",
      $expr: {
        $ne: [
          "$on_hand",
          {
            $add: [
              "$available",
              "$reserved"
            ]
          }
        ]
      }
    });

### 27.1. Khi có null/missing

`$add` và BSON type comparison cần dữ liệu số hợp lệ. Nếu collection legacy có field null/string/missing, phân loại invalid type trước để không hiểu sai kết quả.

### 27.2. Không đồng nhất physical audit với ledger

`on_hand = available + reserved` chỉ là nhất quán nội bộ; số physical có thể sai do thất thoát, damaged stock hoặc receipt chưa ghi. Cycle count là quy trình riêng.

### 27.3. Khi drift được phát hiện

Lưu incident ID, tenant/SKU/warehouse, danh sách reservation/movement IDs, timestamps, versions và writers có liên quan; chọn correction theo source of truth đã được quyết định.

---

## 28. Metrics và alerting

| Metric gợi ý | Điều phát hiện |
|---|---|
| `inventory_negative_count` | Stock bucket có số âm |
| `inventory_invariant_mismatch_count` | on_hand khác available+reserved |
| `inventory_ledger_drift_count` | Reserved counter lệch ACTIVE ledger |
| `reserve_new_success_total` | Business reservations mới thực sự commit |
| `reserve_duplicate_total` | Retry được dedup hợp lệ |
| `idempotency_conflict_total` | Cùng key khác payload |
| `reserve_insufficient_total` | Không đủ hàng |
| `transaction_write_conflict_total` | Contention |
| `transaction_unknown_commit_total` | Outcome chưa được phân giải |
| `reservation_expired_active_backlog` | Giữ chỗ quá hạn chưa giải phóng |
| `release_duplicate_total` | Cancel/expiry callback trùng |
| `fulfillment_duplicate_total` | Ship callback trùng |
| `queue_redelivery_total` | At-least-once replay |
| `reserve_latency_p95/p99` | SLO và hot SKU pressure |
| `reconciliation_lag_seconds` | Độ chậm sửa/đối soát |

Các tên chỉ là ví dụ application metrics, không phải metrics sẵn có mặc định trong mongod.

### 28.1. Đếm business effect, không đếm retries

Một retry R100 trả ALREADY_RESERVED không phải reservation mới. Nếu tính nó như sale mới, báo cáo sẽ sai dù kho chưa bị trừ thêm.

### 28.2. Cảnh báo quan trọng

Số âm >0, drift kéo dài, unknown commits chưa resolve, expiration backlog tăng liên tục, duplicate spikes hoặc hot SKU latency quá cao cần được điều tra.

---

## 29. Test concurrency: hai đơn, một sản phẩm

Thiết lập:

    available=1
    reserved=0
    on_hand=1

Hai requests **khác ID** A và B, cùng qty=1, chạy đồng thời.

Kết quả đúng:

    A RESERVED, B OUT_OF_STOCK
    hoặc B RESERVED, A OUT_OF_STOCK

    available=0
    reserved=1
    on_hand=1
    ACTIVE reservations count=1

Không được có cả hai requests success.

### 29.1. Barrier/parallel execution

Dùng hai threads hoặc hai service instances, chờ barrier rồi cùng gửi requests. Lặp test nhiều lần để tăng khả năng race, nhưng không thay việc chứng minh atomic query semantics.

### 29.2. Kiểm tra raw BSON

Đọc cuối test từ MongoDB và kiểm tra counters + ledger, không chỉ dựa vào HTTP response.

### 29.3. Không dùng lock trong test để che race

Nếu các requests thực sự không chạy song song do một local lock, test có thể pass dù service phân tán vẫn sai.

---

## 30. Test double decrement: cùng ID khi còn nhiều hàng

Thiết lập:

    available=10
    reserved=0
    on_hand=10
    request R100 qty=2

Gửi R100 hai lần, cả tuần tự và đồng thời.

Kết quả đúng:

    First R100 -> RESERVED
    Retry R100 -> ALREADY_RESERVED

    available=8
    reserved=2
    on_hand=10
    ACTIVE marker R100 count=1

Nếu available=6, bạn mới chống overselling mà **chưa chống double decrement**.

### 30.1. Payload mismatch

R100 lần đầu q=2, lần sau q=5 phải trả conflict và không đổi stock.

### 30.2. Unknown outcome

Mô phỏng disconnect/timeout sau commit rồi retry cùng key. Không để request mới sinh key khác.

### 30.3. Concurrent duplicate key

Hai transaction cùng insert R100; một bên có thể nhận duplicate key hoặc write conflict. Handler phải reconcile marker, không trả false failure hoặc giảm thêm.

### 30.4. Retention

Replay R100 sau longest queue retention. Nếu marker bị xóa, chứng minh architecture còn cách chống old duplicate.

---

## 31. Test state machine và failures

Những kịch bản bắt buộc:

1. Double cancel R100: available chỉ tăng một lần.
2. Double ship R100: on_hand chỉ giảm một lần.
3. Cancel vs ship: chỉ một terminal transition commit.
4. Expire vs payment: state không vừa EXPIRED vừa FULFILLED.
5. Crash giữa marker insert và stock decrement: transaction rollback cả hai.
6. Crash sau transaction commit nhưng trước HTTP response: retry idempotent.
7. Một SKU đủ, SKU khác thiếu: all-or-nothing order transaction rollback.
8. Hai SKUs trùng stock bucket: tổng quantity đúng, không double count.
9. Warehouse wrong tenant: update không match hoặc bị chặn quyền.
10. Inventory thiếu record: không tạo stock âm qua upsert.
11. Qty=0/âm/quá max: không ghi.
12. Mixed BSON int32/int64/null: validation/decoding không bị bỏ qua.
13. Replica primary stepdown: retry/reconciliation xử lý uncertainty.
14. Consumer redelivery: cùng movement ID không cộng/trừ lại.
15. Expiry worker restart: không release cùng reservation hai lần.

### 31.1. Test trên replica set

Transaction behavior không được kiểm chứng đầy đủ bằng standalone mongod. Dùng replica set test (có thể single-member) và JUnit/Testcontainers/hệ thống tương đương.

### 31.2. Inject faults

Ngắt kết nối ngay quanh commit, dừng worker giữa các bước, duplicate message và thay đổi thứ tự callback. Kiểm tra **data cuối**, không chỉ exception type.

---

## 32. Hot SKU, sharding và hiệu năng

### 32.1. Một hot document vẫn là điểm tranh chấp

Dù sharded cluster có nhiều shards, một inventory bucket của SKU rất hot vẫn cập nhật một document. Sharding không cho phép nhiều writers tự do giảm cùng một counter mà không coordination.

### 32.2. Conditional update rất rẻ để tìm theo ID

`_id` có index mặc định. Nếu query dùng unique stock ID và tenant check, thường không cần index trên `available` chỉ để reserve; index trên field đổi liên tục có thể tăng write cost.

### 32.3. Escrow/quota buckets

Một kiến trúc nâng cao chia quota bán được thành nhiều buckets, mỗi bucket có conditional decrement riêng. Tuy nhiên tổng quota cấp ban đầu không được vượt physical stock; chuyển quota giữa buckets phải có transaction/fencing và reconciliation. Không tự chia counters rồi lấy tổng không kiểm soát.

### 32.4. Cache

Có thể cache số available để hiển thị nhưng success của reservation phải đến từ database write. Cached/stale data hoặc Redis lock hết lease không đủ bảo vệ invariant nếu database là source of truth.

### 32.5. Benchmark đúng

Đo throughput, p95/p99 latency, write conflict rate, transaction retries, primary CPU, replication lag và reconciliation backlog trên hot SKUs. Không tuyên bố một throughput cố định áp cho mọi deployment.

---

## 33. Runbook khi phát hiện double decrement

### Bước 1 — Ổn định

- Giảm retry storm/redelivery.
- Tạm ngưng writer sai nếu có feature flag.
- Không xóa reservation/movement proofs.
- Không chạy script cộng tồn toàn collection khi chưa biết effect.

### Bước 2 — Khoanh vùng

Xác định tenant, warehouse, SKU, reservation ID, order line, request ID, timestamps, số lần retry, application version và worker.

### Bước 3 — So nguồn

Inventory counters, reservation ledger, movement IDs, order state, payment/shipping events và transaction/driver errors. Kiểm tra có hai distinct IDs cho cùng checkout hay cùng ID đã chạy hai lần.

### Bước 4 — Xác định nguyên nhân

- Thiếu key?
- Key bị tái tạo?
- Marker không atomic với decrement?
- Retry `$inc` mới sau unknown outcome?
- Callback release/ship chạy lặp?
- TTL xóa proof quá sớm?
- Old writer không áp protocol?

### Bước 5 — Correction

Dùng audited adjustment với unique movement ID, authorized scope, CAS/transaction và đối soát. Không âm thầm set available theo ước tính.

### Bước 6 — Ngăn tái phát

Thêm stable ID/unique index/transaction/state CAS, sửa retry policy, tăng retention, test multi-instance/fault injection.

---

## 34. Runbook khi oversell hoặc available âm

### Bước 1 — Dừng hứa bán không chính xác

Có thể tạm khóa reserve theo hot SKU/bucket trong phạm vi incident policy, nhưng không tùy tiện dừng toàn bộ payment/fulfillment hệ thống.

### Bước 2 — Kiểm tra write path

- Có read–modify–save?
- Có thiếu `available>=qty` trong update filter?
- Có `upsert:true`?
- Có qty âm?
- Có job/script set available trực tiếp?
- Có warehouse/tenant ID sai?
- Có duplicate stock bucket?

### Bước 3 — Kiểm tra orders bị ảnh hưởng

Nếu hai orders cùng được xác nhận cho một sản phẩm, cần business workflow xử lý oversold orders/backorders/refunds; chỉ sửa counter không đủ.

### Bước 4 — Reconcile

Đối chiếu reservations, movements, physical stock, queue events và audit records.

### Bước 5 — Repair có kiểm soát

Dùng unique adjustment movement + transaction và confirmation; không chỉnh sửa nhiều stock buckets bừa khi concurrent traffic còn chạy.

### Bước 6 — Theo dõi

Alerts negative counters, idempotency conflicts, unknown commits và drift giảm về mức chấp nhận được.

---

## 35. Anti-patterns cần tránh

| Anti-pattern | Vì sao sai | Thay bằng |
|---|---|---|
| `find` rồi `save` không CAS | Race, lost update | Atomic conditional `updateOne` |
| Chỉ check available trong Java | Check và write tách thời gian | `available >= q` trong filter |
| Retry `$inc` bất kỳ | Double decrement | Stable operation ID + ledger |
| Tạo UUID mới mỗi retry | Dedup mất ý nghĩa | Giữ request ID |
| Marker insert riêng rồi decrement | Crash tạo false success | Transaction |
| Decrement rồi insert marker | Crash gây duplicate effect | Transaction |
| Coi duplicate key luôn success | Có thể key reuse khác payload | Compare fingerprint/state |
| Coi timeout là rollback | Commit có thể đã thành công | Reconcile unknown outcome |
| `upsert:true` khi reserve | Có thể tạo record ngoài ý muốn | update-only |
| `$addToSet` marker không kèm filter | `$inc` vẫn có thể chạy | Dedupe filter + atomic write |
| Array IDs tăng vô hạn | BSON 16 MiB/hotspot | Separate reservation collection |
| TTL xóa ACTIVE marker | Không release stock, mất proof | Expiration worker transaction |
| Hủy hai lần đều `$inc +q` | Double release | State CAS |
| Ship hai lần đều `$inc -q` | Double decrement on_hand | State CAS |
| Chỉ lock trong JVM | Không bảo vệ nhiều instances | Database atomicity |
| Secondary read để quyết định reserve | Stale available | Predicate tại write |
| Refund trực tiếp cộng available | Hàng có thể chưa trở lại | Return/inspection workflow |
| Chỉ đếm API success | Retries bị tính thành business events | Metrics theo unique IDs |
| Validator minimum=0 là đủ | Không chống duplicate effect | Ledger/transaction |
| Thấy drift là set counter | Che lỗi gốc | Audited reconciliation |

---

## 36. Checklist trước khi triển khai

### 36.1. Data model

- [ ] `on_hand`, `available`, `reserved` có contract rõ.
- [ ] Một bucket duy nhất theo tenant/kho/SKU.
- [ ] Cùng kiểu số và giới hạn hợp lệ.
- [ ] Reservation có stable ID và immutable request fields.
- [ ] Terminal state không được quay lại ACTIVE với cùng ID.
- [ ] Movement IDs cho receive/ship/return/adjust/transfer.
- [ ] Idempotency retention lớn hơn replay window.

### 36.2. Concurrency

- [ ] Filter `available>=q` ở chính write.
- [ ] `$inc` available/reserved chung document update.
- [ ] Qty>0, checked bounds/overflow.
- [ ] Không upsert khi reserve.
- [ ] Ledger marker + stock effect cùng transaction.
- [ ] Release/expire/ship có state CAS.
- [ ] Multi-SKU all-or-nothing có transaction.
- [ ] Retry transient/write-conflict bounded, không gọi external side effects trong callback.

### 36.3. Tính đúng hệ thống

- [ ] Unique business keys và fingerprints.
- [ ] Duplicate requests trả result cũ.
- [ ] Unknown commit có lookup/reconciliation.
- [ ] Outbox publish và consumer dedup.
- [ ] Tenant authorization cho mọi operation.
- [ ] Schema validation và index phù hợp.
- [ ] Không xóa ACTIVE markers bằng TTL.
- [ ] Monitoring negative/drift/duplicate/unknown.
- [ ] Test concurrency + crash + message replay trên replica set.

---

## 37. Bài tập thực hành

1. **Invariant:** Với on_hand=20 và reserved=5, tính available. Nếu reserved=23, chẩn đoán.
2. **Stock bucket:** Tạo document `inventory` Int64 theo tenant+warehouse+SKU.
3. **Index:** Tạo compound unique index cho bucket. Thử insert trùng.
4. **Atomic decrement:** Viết `updateOne` có available≥q, giảm available và tăng reserved.
5. **Race:** Stock=1, hai requests khác ID qty=1. Chứng minh chỉ một thành công.
6. **Input:** Test qty=0, âm, cực lớn, null và string.
7. **Result:** Phân biệt matched=0 do không đủ hàng hay missing bucket.
8. **Double decrement:** Stock=10, gửi cùng request hai lần không ledger; quan sát lỗi.
9. **Stable key:** Tạo deterministic reservation ID cho order line/attempt.
10. **Fingerprint:** Gửi lại cùng ID nhưng quantity khác; phải conflict.
11. **Unique ledger:** Tạo `inventory_reservations` và unique index phù hợp.
12. **Marker-first crash:** Insert marker rồi crash trước stock decrement; mô tả sai lệch.
13. **Effect-first crash:** Decrement trước marker rồi crash; giải thích retry sai.
14. **Transaction:** Insert marker + conditional decrement trong transaction.
15. **Duplicate concurrency:** Hai transactions cùng R100; xử lý duplicate key bằng reconcile.
16. **Unknown commit:** Mô phỏng mất ACK commit, retry R100 không trừ lần hai.
17. **Spring Data:** Viết MongoTemplate conditional update và tích hợp MongoTransactionManager.
18. **Version:** So sánh expected version CAS với idempotency ID.
19. **Double cancel:** Hai CANCEL callbacks chỉ release stock một lần.
20. **Expire worker:** ACTIVE quá hạn chuyển EXPIRED và release trong transaction.
21. **TTL:** Giải thích vì sao TTL trên ACTIVE marker làm sai stock.
22. **Ship:** ACTIVE→FULFILLED giảm reserved/on_hand và không đổi available.
23. **Expire vs ship:** Chạy đồng thời, chỉ một terminal transition commit.
24. **Multi-SKU:** Một line đủ, một line thiếu; all-or-nothing không giữ partial.
25. **Multi-warehouse:** Phân 5 sản phẩm HCM=3 và HN=4 theo policy.
26. **Receive:** Inbound event duplicate, dùng unique movement ID tránh cộng hai lần.
27. **Reconciliation:** Tính tổng ACTIVE reservations, so với inventory.reserved.
28. **Monitoring:** Thiết kế dashboard negative, drift, retries, expiration backlog.
29. **Security:** Không cho client đặt tenant_id hay ghi counters trực tiếp.
30. **Production design:** Xây sơ đồ order/reserve/payment/ship/cancel/expire/outbox với retry, transaction, tests và runbook.

---

## 38. Câu hỏi ôn tập

1. `on_hand` khác `available` và `reserved` thế nào?
2. Khi nào công thức on_hand=available+reserved không còn đúng?
3. Tại sao cần một inventory bucket duy nhất cho tenant–warehouse–SKU?
4. Atomicity single-document của MongoDB bảo vệ điều gì?
5. Vì sao read–modify–save có thể oversell mà available không âm?
6. `$gte` trong update filter làm gì?
7. Vì sao `$inc` available và reserved cần ở cùng lệnh?
8. Tại sao phải reject quantity âm?
9. Vì sao `upsert:true` không phù hợp khi reserve?
10. Matched=0 có đồng nghĩa không đủ hàng không?
11. Hai requests khác ID cùng qty=1 khi available=1 phải có kết quả gì?
12. Vì sao conditional decrement không tự chống duplicate request?
13. Retryable writes của driver có bảo vệ HTTP replay mới không?
14. Stable idempotency key nên được tạo ra ở cấp nghiệp vụ nào?
15. Vì sao tạo UUID mới mỗi retry phá dedup?
16. Cùng ID khác quantity có thể xem là retry hợp lệ không?
17. Reservation marker unique giải quyết vấn đề gì?
18. Vì sao marker và stock effect cần cùng transaction?
19. Crash giữa hai writes riêng lẻ gây hai loại lỗi gì?
20. Khi duplicate key xuất hiện, khi nào trả already reserved?
21. Khi nào duplicate key phải trả conflict?
22. `TransientTransactionError` và `UnknownTransactionCommitResult` khác nhau thế nào?
23. Tại sao timeout không chứng minh rollback?
24. Vì sao sau timeout tra reservation marker thay vì chỉ đọc available?
25. ReadConcern.SNAPSHOT và WriteConcern.MAJORITY phục vụ mục đích gì?
26. Vì sao transaction callback không được charge payment?
27. ACTIVE→RELEASED tác động counters thế nào?
28. Vì sao check reserved>=q chưa ngăn double release?
29. Làm sao CAS ACTIVE→RELEASED giúp tránh cập nhật hai lần?
30. ACTIVE→FULFILLED khác RELEASED ở on_hand thế nào?
31. Vì sao refund không đồng nghĩa nhập kho?
32. TTL index có tự release stock không?
33. Expiration worker phải thực hiện điều gì cùng transaction?
34. Expire và payment callback cạnh tranh giải quyết ra sao?
35. Khi nào cần transaction cho order nhiều SKU?
36. Khi nào partial reservation là hợp lệ?
37. Vì sao phải gộp quantities trùng stock bucket?
38. Một hot SKU có được phân tán chỉ bằng sharding không?
39. Vì sao cache available không đủ quyết định reserve?
40. Single-document applied IDs array gặp giới hạn gì?
41. `$addToSet` đơn lẻ có ngăn `$inc` khi ID trùng không?
42. Optimistic version có thay thế idempotency key không?
43. Receive/adjust/transfer cần movement ID vì sao?
44. Outbox giải quyết khoảng crash nào?
45. Outbox có bảo đảm message chỉ được phát đúng một lần không?
46. Vì sao consumer downstream cần dedup?
47. Các chỉ số nào phát hiện negative stock và ledger drift?
48. Reconciliation có thể thấy mismatch tạm khi concurrent writes không?
49. Vì sao không tự set available theo số mới đo được mà thiếu audit?
50. Test nào chứng minh ngăn cả overselling lẫn double decrement?

---

## 39. Tổng kết

Một hệ thống inventory đáng tin cậy trong MongoDB phải đồng thời bảo vệ **số lượng, định danh nghiệp vụ, trạng thái và khả năng khôi phục**:

1. **Chống overselling:** dùng `updateOne` với `available>=quantity` ngay tại write, cập nhật available−q và reserved+q trong cùng document.
2. **Chống double decrement:** dùng stable reservation ID, unique marker, fingerprint và kết quả bền vững; không retry `$inc` như một operation mới.
3. **Atomic giữa ledger và stock:** nếu marker và inventory thuộc hai documents, dùng multi-document transaction hoặc protocol khác có chứng minh correctness; không chấp nhận marker-first/effect-first có cửa sổ crash.
4. **State machine:** reserve, release, expire và fulfill phải dùng CAS/transaction để ngăn double release, double ship và tranh chấp callback.
5. **Đa SKU/kho:** all-or-nothing cần transaction; partial fulfillment phải có state tường minh.
6. **External integrations:** payment/shipping/broker/outbox có retries và idempotency độc lập; không lẫn payment success với stock shipped.
7. **Vận hành:** unique indexes, schema validation, tenant isolation, monitoring, reconciliation, retention và concurrency fault tests quan trọng như câu lệnh update.

**Bài kiểm tra cuối cùng:** Nếu MongoDB đã commit giảm 2 sản phẩm, HTTP response bị mất và cùng request được gửi lại khi kho vẫn còn đủ hàng, hệ thống có thể **chứng minh** rằng lần thứ hai không làm thay đổi tồn kho không? Nếu chưa, hệ thống mới chỉ có atomic decrement, chưa có idempotent inventory operation.

## Tài liệu tham khảo

- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Transactions in Applications](https://www.mongodb.com/docs/manual/core/transactions-in-applications/)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Manual — Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/)
- [MongoDB Manual — `$inc`](https://www.mongodb.com/docs/manual/reference/operator/update/inc/)
- [MongoDB Manual — `$gte`](https://www.mongodb.com/docs/manual/reference/operator/query/gte/)
- [MongoDB Manual — `$setOnInsert`](https://www.mongodb.com/docs/manual/reference/operator/update/setOnInsert/)
- [MongoDB Manual — `$addToSet`](https://www.mongodb.com/docs/manual/reference/operator/update/addToSet/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Java Sync Driver — Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [Spring Data MongoDB — Template CRUD Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
- [Spring Data MongoDB — Client Sessions and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
- [Spring Data MongoDB — Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking)
