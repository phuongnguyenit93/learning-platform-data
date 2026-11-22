# Transactions, batched writes và cạnh tranh cập nhật trong Firestore

Hai khách hàng cùng bấm **Đặt hàng** khi sản phẩm chỉ còn một đơn vị. Nếu ứng dụng đọc `available=1` rồi tự ghi `available=0` bằng hai request độc lập, cả hai khách có thể được báo đặt hàng thành công. Đây là lỗi **lost update / overselling** do đọc–sửa–ghi không được bảo vệ trước truy cập đồng thời.

**Cloud Firestore** cung cấp **transactions**, **batched writes** và **atomic field transforms** để xử lý các bài toán khác nhau. Transaction đọc trạng thái rồi quyết định ghi nhất quán; batch gom nhiều lệnh ghi thành một commit nguyên tử; transform như `increment()` cập nhật trường trên server mà không cần ứng dụng đọc trước. Chọn sai công cụ có thể làm sai nghiệp vụ, phát sinh `ABORTED` khi cạnh tranh cao hoặc tăng chi phí đọc/ghi.

Bài thuộc chương **Firestore và Firebase** của mô-đun `CLOUD_PROVIDERS_GCP`, kết nối thực hành dữ liệu với IAM, VPC, Cloud Run/GKE/Compute Engine, Cloud Storage và CI/CD. Ví dụ dùng **Firestore Native mode – Core operations**, Java 21 phía server và Firebase Web SDK phía client. Không mặc định áp dụng nguyên trạng cho **Firestore in Datastore mode**, **MongoDB compatibility** hoặc **Enterprise Pipeline operations**.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt transaction, batched write, atomic transform và ghi độc lập.
2. Giải thích tính nguyên tử, nhất quán khi commit, retries và callback transaction chạy lại.
3. Dùng Java transaction để **kiểm tra tồn kho rồi ghi đơn hàng** mà không oversell.
4. Dùng Firebase Web batched write khi **không cần đọc trước** để quyết định ghi.
5. Phân biệt concurrency control **pessimistic/optimistic** và các SDK.
6. Phát hiện **hot document**, giảm contention và thiết kế idempotency key.
7. Phân biệt IAM phía server với **Firestore Security Rules** phía Web/Mobile.
8. Kiểm thử đồng thời bằng **Firebase Local Emulator Suite**, đọc metrics và ước tính chi phí.

## 1. Dữ liệu Firestore và phạm vi một lần commit

Firestore lưu dữ liệu trong **documents**, nhóm thành **collections**. Ví dụ hệ thống Commerce:

~~~text
inventory/sku-01
  available: 1
  updatedAt: timestamp

orders/request-abc
  sku: "sku-01"
  quantity: 1
  state: "RESERVED"

profiles/user-123
  displayName: "Lan"
  updatedAt: timestamp
~~~

Một document có path xác định, ví dụ `inventory/sku-01`; các lệnh ghi cùng document có thể cạnh tranh. Transactions và batched writes có thể thay đổi **nhiều documents** trong một lần commit nguyên tử: **hoặc tất cả ghi thành công, hoặc không ghi gì**.

**Giới hạn:** nguyên tử này bao phủ các thay đổi trong **Firestore database**, không tự bao phủ Cloud SQL, Pub/Sub publish, gửi email, API thanh toán hoặc upload Cloud Storage. Với workflow đa hệ thống cần idempotency, outbox hoặc cơ chế đối soát.

## 2. Lỗi lost update khi đọc rồi ghi riêng lẻ

Hai requests cùng đọc tồn kho:

~~~mermaid
sequenceDiagram
    participant A as Khách A
    participant F as Firestore
    participant B as Khách B
    A->>F: GET inventory/sku-01
    F-->>A: available = 1
    B->>F: GET inventory/sku-01
    F-->>B: available = 1
    A->>F: UPDATE available = 0
    B->>F: UPDATE available = 0
    Note over A,B: Cả hai có thể ghi đơn nếu code không bảo vệ
~~~

Kết quả đáng ngại không phải giá trị cuối bằng 0 mà là **hai đơn được tạo cho cùng một đơn vị hàng**. Khi quyết định ghi phụ thuộc dữ liệu vừa đọc, cần **transaction** để phối hợp việc đọc và commit. Không dùng hai lệnh `get()` rồi `update()` riêng và gọi đó là “đã kiểm tra tồn kho”.

Một `increment(-1)` cũng **không đủ** nếu nghiệp vụ yêu cầu `available >= 0`: transform giảm nguyên tử nhưng không tự kiểm tra điều kiện “còn hàng trước khi trừ”.

## 3. Transaction: đọc trước, ghi sau và tự retry

Firestore transaction nhóm các thao tác đọc và ghi; nó cung cấp **serializable isolation theo commit time**. Nếu dữ liệu liên quan thay đổi làm transaction không còn hợp lệ, SDK có thể thử **chạy lại toàn bộ callback** với snapshot mới.

~~~mermaid
flowchart TD
    S["Bắt đầu transaction"] --> R["Đọc orderId + inventory"]
    R --> C{"Order đã tồn tại?"}
    C -->|Có| E["Trả ALREADY_EXISTS"]
    C -->|Không| K{"available >= qty?"}
    K -->|Không| O["Trả OUT_OF_STOCK"]
    K -->|Có| W["Buffer update inventory + create order"]
    W --> COMMIT{"Commit hợp lệ?"}
    COMMIT -->|Có| OK["CREATED"]
    COMMIT -->|"Cạnh tranh / ABORTED"| RETRY["SDK retry callback (có giới hạn)"]
    RETRY --> R
~~~

**Quy tắc quan trọng:**

- **Tất cả reads phải diễn ra trước writes** trong cùng transaction; không đọc lại để “xem ghi đã có tác dụng chưa” khi đang ở callback.
- Reads trong transaction thấy snapshot nhất quán theo semantics của Firestore; **writes chỉ có hiệu lực khi commit thành công**.
- Callback có thể chạy **nhiều lần**; không gửi email, thanh toán, publish Pub/Sub hoặc sửa React state bên trong nó.
- SDK tự retry **hữu hạn** khi có contention; sau giới hạn có thể trả `ABORTED: Too much contention on these documents. Please try again.`.
- **Transactions thất bại khi client offline**; ứng dụng Web/Mobile không được giả định rằng checkout offline vẫn được đặt thành công.

### 3.1. Serializable không đồng nghĩa hai request đều thành công

Nếu chỉ còn một đơn vị, hai transactions cố mua đồng thời: một request có thể commit, request còn lại được retry rồi thấy `available=0` và nhận `OUT_OF_STOCK`. Đây là **kết quả đúng**, không phải lỗi hệ thống. Cần phân biệt hết hàng với `ABORTED`/`DEADLINE_EXCEEDED`.

## 4. Batched writes: nhiều ghi nguyên tử, không cần đọc trước

**Batched write** gom các thao tác `set()`, `update()`, `delete()`, rồi commit cùng lúc. Phù hợp khi các giá trị và điều kiện đã biết, không cần đọc tài liệu hiện tại để quyết định.

~~~mermaid
flowchart LR
    UI["Firebase Web client"] --> BATCH["Batched write"]
    BATCH --> P["profiles/user-123<br/>updatedAt"]
    BATCH --> A["profiles/user-123/activity/event-01"]
    P --> ATOMIC["Một commit: tất cả hoặc không"]
    A --> ATOMIC
~~~

| Tiêu chí | Transaction | Batched write |
| --- | --- | --- |
| Đọc document trong operation | **Có**, đọc trước ghi | **Không** |
| Ghi nhiều documents nguyên tử | Có | Có |
| Tự chạy lại callback khi cạnh tranh | Có, SDK retry hữu hạn | Không có transaction callback để retry |
| Kiểm tra tồn kho `available >= qty` | **Phù hợp** | Không làm được chỉ bằng batch |
| Thiết bị Web/Mobile offline | Transaction **thất bại** | Có thể được **xếp hàng để đồng bộ khi online** theo SDK/cấu hình |
| Phù hợp | Đọc–kiểm tra–ghi, invariant liên tài liệu | Nhiều ghi đã xác định sẵn |
| Chi phí | Reads + writes; retry có thể tăng reads/latency | Các writes được tính riêng, dù commit một lần |

**Không nhầm “batch atomic” với “batch có điều kiện”.** Nếu hai clients tự đọc `available=1` bên ngoài rồi cùng commit batches dựa trên dữ liệu cũ, hệ thống vẫn có thể oversell.

## 5. Atomic field transforms: đơn giản hơn khi chỉ đổi một trường

Firestore cung cấp phép đổi trường thực hiện trên server:

- `increment(n)`: cộng/trừ số không cần đọc–ghi giá trị trong client.
- `arrayUnion(...)` / `arrayRemove(...)`: thêm/bỏ phần tử theo semantics Firestore.
- `serverTimestamp()`: ghi thời gian phía server.

Ví dụ tăng số lượt xem từ Web SDK:

~~~javascript
import { doc, updateDoc, increment, serverTimestamp } from "firebase/firestore";

// db là Firestore instance đã khởi tạo từ Firebase app.
await updateDoc(doc(db, "products", "sku-01"), {
  viewCount: increment(1),
  lastViewedAt: serverTimestamp()
});
~~~

Đây là cập nhật **nguyên tử tại document**, không phải transaction kiểm soát workflow. `increment` có thể xử lý hai client cộng dồn mà không mất cập nhật, nhưng:

- Không giới hạn tồn kho không âm nếu dùng đơn lẻ.
- Nếu retry **hai request nghiệp vụ riêng**, có thể cộng hai lần; cần idempotency theo event/request.
- Một document vẫn có giới hạn throughput thực tế, cạnh tranh và chi phí index/write.

Nếu chỉ cần bộ đếm tăng mạnh, cân nhắc **sharded/distributed counter**; nếu cần giữ tồn kho không âm, dùng transaction hoặc thiết kế reservation/queue kiểm soát invariant.

## 6. Pessimistic và optimistic concurrency

Firestore có **concurrency mode** ở cấp database:

| Cơ chế | Hành vi | Ngữ cảnh |
| --- | --- | --- |
| **PESSIMISTIC** | Server transaction dùng locks với documents đọc để ngăn ghi cạnh tranh đến khi commit/timeout | Mặc định ở **Firestore Standard edition** |
| **OPTIMISTIC** | Không khóa documents theo kiểu trên; phát hiện xung đột và retry | Mặc định ở **Firestore Enterprise edition** |
| **Web/Mobile SDK** | Mô phỏng optimistic transactions bằng preconditions trên versions documents | **Luôn** theo cơ chế này, bất kể database mode |

Các chi tiết trên nói về **Firestore Native/Core operations**. Server SDK như Java/Go/Node.js dùng cơ chế concurrency control của database; **Web/Mobile SDK luôn dùng optimistic emulation**. Không suy ra client Web có thể giữ pessimistic lock chỉ vì database Standard đang ở chế độ PESSIMISTIC.

### 6.1. Tại sao vị trí ứng dụng ảnh hưởng?

Server SDK dùng lock trong PESSIMISTIC mode có thể khiến operations khác đợi. Nếu Cloud Run/GKE đặt **xa Firestore database region**, độ trễ mạng làm transaction giữ lock lâu hơn và tăng contention. Vì vậy đặt server workers gần database và giữ callback ngắn trước khi tăng concurrency.

### 6.2. Khi nào nhận ABORTED?

Khi nhiều transactions cố thay đổi **cùng document**, một số sẽ đợi hoặc retry. Nếu hết retries/timeout, SDK trả `ABORTED`. Không diễn giải mọi `ABORTED` là database mất dữ liệu; kiểm tra **hot document, thời gian transaction, region client và tải đồng thời**.

## 7. Thiết kế dữ liệu cho bài toán tồn kho

~~~text
inventory/sku-01
  available: 2

orders/request-100
  sku: "sku-01"
  quantity: 1
  state: "RESERVED"
~~~

**Bất biến nghiệp vụ:**

1. `available >= 0` tại mọi commit hợp lệ.
2. Cùng một `requestId` không tạo hai order documents.
3. Khi commit thành công, **trừ tồn kho và tạo đơn hàng cùng transaction**.
4. Khi API retry do mạng, **dùng lại chính requestId cũ**.

Với `orders/{requestId}`, callback đọc order trước. Nếu tồn tại và payload khớp, trả `ALREADY_EXISTS`; nếu cùng requestId nhưng payload khác, báo **idempotency conflict**, không âm thầm chấp nhận.

**Giới hạn:** một document `inventory/sku-01` có thể thành **hot document** khi flash sale. Transaction đảm bảo tính đúng, **không bảo đảm throughput vô hạn**. Khi đó cần reservation/queue, phân vùng inventory theo kho/lot hoặc phân bổ capacity có kiểm soát; không chia shard tùy ý làm phá invariant tồn kho.

## 8. Java server SDK: transaction đặt hàng có xử lý trùng

Ví dụ Java 21 dùng **Cloud Firestore Java server client** trong project lab. Thư viện Maven chính:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>libraries-bom</artifactId>
      <version>26.90.0</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
<dependencies>
  <dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-firestore</artifactId>
  </dependency>
</dependencies>
~~~

Đoạn trên đặt trong `pom.xml` Maven Java 21; BOM pin phiên bản minh họa, cần cập nhật bản được phê duyệt ở production. Java dùng **Application Default Credentials** ở môi trường thật, còn **Firestore Emulator** dùng `FIRESTORE_EMULATOR_HOST` trong lab.

### 8.1. Ví dụ class có thể chạy

~~~java
package lab.firestore;

import com.google.cloud.firestore.DocumentReference;
import com.google.cloud.firestore.DocumentSnapshot;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.FirestoreOptions;
import java.util.Map;
import java.util.Objects;

public class InventoryLab {
    public static void main(String[] args) throws Exception {
        String projectId = System.getenv("GOOGLE_CLOUD_PROJECT");
        if (projectId == null || projectId.isBlank()) {
            throw new IllegalArgumentException("Set GOOGLE_CLOUD_PROJECT");
        }
        if (args.length == 0) {
            throw new IllegalArgumentException("Use: seed | order REQUEST_ID");
        }

        try (Firestore db = FirestoreOptions.newBuilder()
                .setProjectId(projectId).build().getService()) {
            if ("seed".equals(args[0])) {
                if (System.getenv("FIRESTORE_EMULATOR_HOST") == null) {
                    throw new IllegalStateException("Seed only in emulator");
                }
                // Chỉ seed trên emulator sạch; không reset kho production.
                db.collection("inventory").document("sku-01")
                    .set(Map.of("available", 2L)).get();
                System.out.println("Seeded available=2");
                return;
            }
            if (!"order".equals(args[0]) || args.length != 2) {
                throw new IllegalArgumentException("Use: order REQUEST_ID");
            }

            String requestId = args[1];
            if (!requestId.matches("[a-zA-Z0-9_-]{1,80}")) {
                throw new IllegalArgumentException("Invalid requestId");
            }

            DocumentReference stockRef =
                db.collection("inventory").document("sku-01");
            DocumentReference orderRef =
                db.collection("orders").document(requestId);

            String result = db.runTransaction(tx -> {
                // TẤT CẢ đọc trước các thao tác ghi.
                DocumentSnapshot order = tx.get(orderRef).get();
                DocumentSnapshot stock = tx.get(stockRef).get();

                if (order.exists()) {
                    if (!Objects.equals(order.getString("sku"), "sku-01")
                        || !Objects.equals(order.getLong("quantity"), 1L)) {
                        throw new IllegalStateException("IDEMPOTENCY_CONFLICT");
                    }
                    return "ALREADY_EXISTS";
                }

                Long available = stock.exists()
                    ? stock.getLong("available") : null;
                if (available == null) {
                    throw new IllegalStateException("MISSING_INVENTORY");
                }
                if (available < 1L) {
                    return "OUT_OF_STOCK";
                }

                tx.update(stockRef, "available", available - 1L);
                tx.create(orderRef, Map.of(
                    "sku", "sku-01",
                    "quantity", 1L,
                    "state", "RESERVED"
                ));
                return "CREATED";
            }).get();

            System.out.println("requestId=" + requestId + " result=" + result);
        }
    }
}
~~~

**Ý nghĩa:** `available` và order document được commit cùng lúc. Khi hai request IDs khác nhau cùng tranh đơn vị cuối, SDK có thể retry, nhưng kết quả đúng là **một được đặt, một hết hàng**. Khi cùng requestId bị gửi lặp, lần sau thấy order tồn tại, không trừ hàng nữa.

**Không gọi Pub/Sub, gửi email hoặc thanh toán trong `runTransaction(...)`**: callback có thể chạy lại. Khi cần publish `OrderReserved`, lưu outbox document trong cùng transaction rồi dùng relay idempotent; Firestore event triggers cũng có thể giao lại và cần dedupe.

### 8.2. Điều gì còn phải bổ sung trước production?

- Xác thực requestId từ caller và gắn với **user/tenant/payload hash**; không để client khác tái sử dụng ID.
- Kiểm tra quyền mua, tồn kho theo kho/lot và logic giá không lấy nguyên từ client.
- Trả mã lỗi phân biệt `OUT_OF_STOCK`, `IDEMPOTENCY_CONFLICT`, `ABORTED`, `PERMISSION_DENIED`.
- Cấu hình deadline/backoff và concurrency trong giới hạn Cloud Run/GKE; không retry vô hạn.
- Bảo vệ side effects ngoài Firestore bằng outbox/idempotency.

## 9. Firebase Web SDK: batched write khi không cần đọc

Ví dụ client đã khởi tạo Firebase app và có `db` từ `getFirestore()`, `uid` từ Firebase Authentication, `eventId` ổn định:

~~~javascript
import {
  doc, writeBatch, serverTimestamp
} from "firebase/firestore";

// db: Firestore instance; uid: request.auth.uid ở Security Rules.
async function saveProfileAndActivity(db, uid, eventId, displayName) {
  const profileRef = doc(db, "profiles", uid);
  const activityRef = doc(db, "profiles", uid, "activity", eventId);

  const batch = writeBatch(db);
  batch.set(profileRef, {
    displayName,
    updatedAt: serverTimestamp()
  }, { merge: true });
  batch.set(activityRef, {
    type: "profile_updated",
    at: serverTimestamp()
  });
  await batch.commit();
}
~~~

**Hai documents cùng được ghi hoặc cùng thất bại**. Cách làm này phù hợp khi biết trước các writes, không cần giá trị vừa đọc. Nếu phải kiểm tra “user còn hạn mức cập nhật không?” dựa trên tài liệu khác, **chuyển sang transaction hoặc server endpoint có kiểm soát**.

Với SDK Web/Mobile, batched writes **có thể được xếp hàng khi offline và đồng bộ lại khi có mạng**; đừng hiển thị “đã commit lên server” khi mới cập nhật local UI. Với đặt hàng/giữ hàng, cần phản hồi commit từ backend.

## 10. Firestore Security Rules khác IAM server

Có hai đường truy cập:

| Đường | Cơ chế ủy quyền chính |
| --- | --- |
| **Firebase Web/Mobile SDK** | Firebase Authentication + **Firestore Security Rules**, có thể kết hợp App Check |
| **Java server SDK trên Cloud Run/GKE/VM** | **Google Cloud IAM** qua ADC/workload identity; **bỏ qua Security Rules** |
| **REST/RPC server** | IAM/token và phạm vi APIs, không dựa vào client Rules |

Mẫu Rules cho phép mỗi user sửa profile và tạo audit record của chính họ; tồn kho/đơn hàng chỉ được ghi từ backend đáng tin cậy:

~~~javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /profiles/{uid} {
      allow read: if request.auth != null && request.auth.uid == uid;
      allow create, update: if request.auth != null
        && request.auth.uid == uid
        && request.resource.data.keys().hasOnly(["displayName", "updatedAt"]);

      match /activity/{eventId} {
        allow read: if request.auth != null && request.auth.uid == uid;
        allow create: if request.auth != null
          && request.auth.uid == uid
          && request.resource.data.keys().hasOnly(["type", "at"])
          && request.resource.data.type == "profile_updated";
        allow update, delete: if false;
      }
    }
    match /inventory/{sku} {
      allow read: if request.auth != null;
      allow write: if false;
    }
    match /orders/{orderId} {
      allow read, write: if false; // Backend cấp dữ liệu cho caller phù hợp.
    }
  }
}
~~~

Đây là **mẫu Rules minh họa**, cần test trước deploy. Server SDK dùng IAM **không bị chặn bởi các allow/deny Rules** trên; backend phải tự xác thực caller, validate dữ liệu và giới hạn IAM của runtime service account.

### 10.1. getAfter() cho bất biến liên document

Trong Security Rules, `getAfter(path)` đọc trạng thái **sau tập thao tác nguyên tử nhưng trước commit**, có thể yêu cầu hai documents được cập nhật cùng nhau. Tuy nhiên có giới hạn **10 document-access calls cho từng operation** và **20 cho toàn transaction/batch**; vượt có thể trả `PERMISSION_DENIED`. Các lần đọc bằng Rules có thể **được tính phí**, kể cả request bị từ chối. Không dùng Rules làm nơi chạy toàn bộ business logic phức tạp.

## 11. Cạnh tranh cập nhật và hot document

**Hot document** được quá nhiều clients đồng thời ghi hoặc đọc trong transactions, ví dụ:

~~~text
counters/global-likes
inventory/sku-flash-sale
rooms/room-001/currentSeats
~~~

Trường hợp này gây chờ lock, retry, `ABORTED`, latency cao và throughput kém. Chọn giải pháp theo business invariant:

| Giải pháp | Phù hợp | Lưu ý |
| --- | --- | --- |
| `increment()` | Cộng/trừ không cần điều kiện, tải vừa phải | Vẫn hot ở QPS cao |
| **Distributed/sharded counter** | Likes/views/count aggregates | Tổng cần gom shards hoặc roll-up; không tự bảo vệ stock invariant |
| Phân vùng theo kho/tenant | Mỗi nhóm có tài nguyên độc lập | Bảo đảm invariant qua partitions |
| Queue/reservation service | Flash sale, cạnh tranh ghi tồn kho rất cao | Cần điều phối và expiry/compensation |
| Giảm thời gian transaction, gần region | Lock/retry lâu do network hoặc callback dài | Không chữa hotspot từ một key chung |
| Rate limit/backpressure | Tránh requests vượt capacity | Trả lỗi/thử lại có kiểm soát |

**Đừng tăng số Cloud Run instances hoặc GKE Pods mù quáng** nếu tất cả cùng sửa `inventory/sku-flash-sale`: scale-out có thể làm tranh chấp tăng.

### 11.1. Sharded counter có phải giải pháp cho tồn kho?

Ví dụ mỗi lượt xem chọn ngẫu nhiên một document trong `counters/{id}/shards/{shardId}` và `increment(1)`; tổng là tổng giá trị shards. Cách này phân tán hot writes nhưng **tăng reads và chi phí tổng hợp**. Với tồn kho hữu hạn cần bảo đảm không âm, không tự biến mỗi shard thành “tồn kho độc lập” nếu không có thuật toán phân phối/reservation an toàn.

## 12. Giới hạn transaction, batch và bulk operations

| Giới hạn/đặc tính | Điều cần nhớ |
| --- | --- |
| Kích thước API request | **10 MiB** cho transaction/commit request |
| Transaction time limit | **270 giây**, với **60 giây idle expiration** |
| Lock deadline | Có thể tự nhả lock nếu transaction kéo dài (ví dụ **20 giây** theo tài liệu) |
| Field transforms trên một document | Tối đa **500 transforms** trong một Commit/transaction |
| Security Rules access calls | **10 mỗi operation, 20 mỗi atomic batch/transaction** |
| Batched writes cỡ lớn | Index updates và payload có thể vượt giới hạn |
| Bulk operations | Server **BulkWriter** hoặc parallel writes khi không cần tất cả atomic |

**Đừng nhầm “500 field transforms trên một document” với “mọi batch đều giới hạn đúng 500 writes”.** Giới hạn thực tế còn liên quan request size, index fan-out, Security Rules và edition. Batch lớn có thể chậm; một write không hợp lệ làm toàn bộ batch thất bại.

Để import hàng trăm nghìn documents, chia thành nhiều đơn vị phù hợp. **BulkWriter/parallel writes không tạo một transaction nguyên tử xuyên toàn bộ dataset**.

## 13. Lab Firestore Emulator: transaction và cạnh tranh

Dùng **Firebase Local Emulator Suite** để tránh thay đổi database thật hoặc phát sinh phí lúc học.

### 13.1. Cấu hình Maven và emulator

Cần Java 21, Maven, Node.js, Firebase CLI và project lab riêng. Trong `pom.xml`, ngoài dependencies ở mục 8, thêm plugin:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.14.0</version>
      <configuration><release>21</release></configuration>
    </plugin>
    <plugin>
      <groupId>org.codehaus.mojo</groupId>
      <artifactId>exec-maven-plugin</artifactId>
      <version>3.6.4</version>
    </plugin>
  </plugins>
</build>
~~~

Tạo `firebase.json` trong một thư mục **lab riêng**, chọn project ID bắt đầu bằng `demo-`:

~~~json
{
  "firestore": { "rules": "firestore.rules" },
  "emulators": {
    "firestore": { "port": 8080 }
  }
}
~~~

Tạo `firestore.rules` với Rules mẫu ở mục 10, sau đó chạy:

~~~bash
firebase emulators:start \
  --only firestore \
  --project demo-firestore-tx
~~~

Trong terminal Java khác:

~~~bash
export GOOGLE_CLOUD_PROJECT=demo-firestore-tx
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8080
~~~

**Quan trọng:** `FIRESTORE_EMULATOR_HOST` chỉ chứa `host:port`, **không thêm `http://`**. Nếu chạy Java trong container, `127.0.0.1` là loopback của container; chọn host có thể truy cập emulator. Emulated data có thể mất khi tắt emulator nếu không export/import.

### 13.2. Chạy Java lab và kiểm tra idempotency

Đặt class `InventoryLab` trong `src/main/java/lab/firestore/InventoryLab.java` của Maven project; trên emulator **trống**:

~~~bash
mvn -q compile exec:java \
  -Dexec.mainClass=lab.firestore.InventoryLab \
  -Dexec.args="seed"

mvn -q compile exec:java \
  -Dexec.mainClass=lab.firestore.InventoryLab \
  -Dexec.args="order request-100"

# Gửi lại CÙNG requestId:
mvn -q compile exec:java \
  -Dexec.mainClass=lab.firestore.InventoryLab \
  -Dexec.args="order request-100"
~~~

**Kỳ vọng:** lần đầu `CREATED`, lần sau `ALREADY_EXISTS`; tồn kho từ 2 còn 1, **không trừ thêm**. Kiểm tra documents trong Emulator UI hoặc đọc qua SDK.

### 13.3. Cạnh tranh trên đơn vị cuối

Mở **hai terminals** và chạy gần đồng thời:

~~~bash
# Terminal A
mvn -q exec:java \
  -Dexec.mainClass=lab.firestore.InventoryLab \
  -Dexec.args="order request-101"

# Terminal B
mvn -q exec:java \
  -Dexec.mainClass=lab.firestore.InventoryLab \
  -Dexec.args="order request-102"
~~~

**Kỳ vọng:** chỉ một request chiếm đơn vị cuối; request kia `OUT_OF_STOCK`, tổng số đơn CREATED hợp lệ là 2 (bao gồm request-100), tồn kho 0. Nếu Emulator quá ít contention để buộc retry, điều đó **không chứng minh production sẽ không có ABORTED**.

### 13.4. Các negative tests

- Thử **cùng requestId với payload khác**: production phải báo conflict, không tái sử dụng bản ghi cũ.
- Thử Web/Mobile SDK ghi trực tiếp `inventory/sku-01`: Rules phải từ chối.
- Thử client chưa đăng nhập ghi profile: Rules phải từ chối.
- Thử batch profile/activity với quyền hợp lệ: cả hai ghi hoặc không ghi.
- Thử Web/Mobile offline: transaction thất bại; batch có thể xếp hàng theo SDK/cấu hình.
- Theo dõi `ABORTED`, retry count và latency khi load test ở test project.

**Emulator không thay thế staging** để kiểm tra throughput thực tế, độ trễ đa region, index performance hoặc mức contention production.

## 14. Phát hành thực tế: Cloud Run/GKE và idempotency

Đối với API Java backend:

1. Xác thực caller trước khi tin `requestId`, gắn với user/tenant/payload.
2. Validate `sku`, `qty`, ownership, giá, thời hạn giữ hàng.
3. Chạy transaction ngắn, không gọi external services trong callback.
4. Nếu `OUT_OF_STOCK`, trả lỗi nghiệp vụ phù hợp (ví dụ HTTP `409 Conflict`).
5. Nếu `ABORTED` hết SDK retries, trả lỗi có thể retry với backoff và **cùng requestId**.
6. Nếu commit thành công nhưng response HTTP mất, lần gọi lại cùng ID phải **ALREADY_EXISTS**.
7. Publish event bằng outbox/relay hoặc cơ chế đáng tin cậy; consumer cũng idempotent.
8. Đặt concurrency/deadline giới hạn và cảnh báo theo SLO.

Firestore transactions **không bảo đảm thanh toán đúng một lần** ở API ngoài. Dùng idempotency key ở payment provider, outbox/reconcile nếu không có transaction chung.

## 15. Quan sát, troubleshooting và chi phí

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `ABORTED: Too much contention...` | Nhiều transactions cùng document, callback dài, region xa | Tìm hot keys, giảm concurrency, đổi data model |
| `DEADLINE_EXCEEDED` | Transactions/queries chậm, network hoặc lock wait | Đo latency, index và retry policy |
| `FAILED_PRECONDITION` | Thứ tự reads/writes sai, điều kiện không thỏa | Chỉ đọc trước ghi, xem lỗi SDK |
| `PERMISSION_DENIED` từ Web | Security Rules/auth/App Check | Kiểm tra Rules/Emulator tests |
| `PERMISSION_DENIED` từ Java server | IAM/project/database/credential | Kiểm tra ADC, runtime SA, roles |
| Batch fail toàn bộ | Một write sai hoặc Rules deny, request/index limit | Chia batch, kiểm tra từng write và Rules |
| Tồn kho âm | `increment(-1)` không check invariant | Transaction stock >= qty và server endpoint |
| Đơn hàng trùng | RequestId không ổn định, side effect ngoài DB | Unique ID, idempotency và outbox |
| Ghi chậm khi scale | Hot document/index, nhiều clients xa | Key Visualizer/metrics, phân tải |
| Hóa đơn tăng | Reads do retries, writes/indexes, Rules lookups | Billing, usage dashboard, log retries |

**Chi phí Firestore** phụ thuộc edition/location, document reads/writes/deletes, storage/indexes, network và tính năng thêm. Một batch chứa 20 writes vẫn được tính phí theo **các writes**, không phải “một transaction = một write”. Rules `get()/exists()/getAfter()` và retries có thể tăng operations/latency. Cloud Billing budget alerts **không phải hard spending cap**.

Theo dõi Cloud Monitoring/Logging và Firestore usage: request count, status `ABORTED`/`RESOURCE_EXHAUSTED`, latency, reads/writes, index/storage growth; thêm application metrics **order created, out-of-stock, duplicate skipped, retry count**. Với hot key, dùng **Key Visualizer** nếu tính năng hỗ trợ.

## 16. Tình huống tổng hợp: flash sale giới hạn tồn kho

Nhóm Commerce có 200 đơn vị sản phẩm giảm giá, 50.000 người dùng Firebase Web đồng thời truy cập. Backend Java chạy trên Cloud Run, lưu orders trong Firestore.

**Thiết kế chưa phù hợp:** mọi client tự đọc `inventory/flash-01`, cập nhật `available` và tạo `orders/randomId`; khi retry lại sinh ID mới. Hệ quả là oversell, duplicate, khó bảo vệ Rules và một hot document bị quá tải.

**Thiết kế khả thi hơn:**

| Yêu cầu | Giải pháp |
| --- | --- |
| Không oversell | Backend transaction đọc stock và ghi order cùng commit |
| Không tạo hai đơn khi retry | Stable requestId, `orders/{requestId}` |
| Không để client sửa tồn kho | Security Rules deny; backend IAM tối thiểu |
| Flash sale rất lớn | Admission control/queue/reservations, kiểm thử phân phối inventory theo kho |
| Không gửi hai sự kiện | Outbox/eventId ổn định và idempotent consumer |
| Quan sát | `ABORTED`, p95, business success, cost |
| Phục hồi | Bounded retry, backpressure, reconciliation |

**Quyết định:** transaction giải quyết **tính đúng** ở mức tranh chấp chịu được. Nếu hot stock doc là nút thắt, phải **thay kiến trúc**, không chỉ tăng CPU Cloud Run.

## 17. Bài tập tự kiểm tra

**Câu 1.** Hai clients đọc tồn kho `1` rồi ghi `0` riêng lẻ. Vì sao tạo hai đơn?

*Đáp án:* Quyết định dựa trên trạng thái cũ, reads/writes không atomic.

**Câu 2.** Khi nào chọn batched write thay transaction?

*Đáp án:* Các writes đã xác định sẵn, không cần đọc hiện trạng để ra quyết định, nhưng cần all-or-nothing.

**Câu 3.** Transaction callback có thể chạy mấy lần?

*Đáp án:* Nhiều lần khi SDK retry do contention; không đặt side effects ngoài DB trong callback.

**Câu 4.** `increment(-1)` có bảo đảm tồn kho không âm?

*Đáp án:* Không. Nó cập nhật nguyên tử một field nhưng không kiểm tra `available >= 1`.

**Câu 5.** Standard dùng pessimistic mode thì Firebase Web transaction cũng giữ lock?

*Đáp án:* Không. Web/Mobile luôn dùng optimistic emulation; server SDK theo database concurrency mode.

**Câu 6.** Batch hai documents, write thứ hai bị Rules deny: điều gì xảy ra?

*Đáp án:* Cả batch không commit, không có partial success.

**Câu 7.** Vì sao `orders/{requestId}` giúp tránh duplicate request?

*Đáp án:* Cùng request dùng cùng document ID; transaction kiểm tra trước khi trừ hàng.

**Câu 8.** Transaction Firestore có atomic với Pub/Sub publish không?

*Đáp án:* Không. Dùng outbox, relay/consumer idempotent hoặc reconcile.

**Câu 9.** Client offline có tự chạy transaction kiểm tra số dư và commit sau khi online?

*Đáp án:* Không. Transaction thất bại offline; batch có thể queue.

**Câu 10.** Vì sao tăng Cloud Run instances làm `ABORTED` tăng?

*Đáp án:* Nhiều concurrent transactions cùng tranh một hot document.

**Câu 11.** Mốc 500 có nghĩa mọi batch giới hạn đúng 500 writes?

*Đáp án:* Không. Mốc trong quota là **500 field transforms trên một document** trong Commit/transaction; request size, indexes và Rules cũng áp dụng.

**Câu 12.** Java server SDK có bị deny bởi Firestore Security Rules?

*Đáp án:* Không. Server SDK dùng IAM; Rules áp dụng cho Web/Mobile.

**Câu 13.** Đã dùng transaction, vì sao vẫn cần idempotency key?

*Đáp án:* HTTP request có thể lặp lại sau commit thành công nhưng response bị mất.

**Câu 14.** Với bộ đếm likes rất nóng, có dùng sharded counter không?

*Đáp án:* Có thể; phân tán writes nhưng đọc tổng tốn hơn, không thay stock transaction.

## 18. Checklist trước production

- [ ] Phân biệt writes phụ thuộc reads (**transaction**) và writes đã biết (**batch**).
- [ ] Transaction reads trước writes; callback không có side effects ngoài DB.
- [ ] SDK retry hữu hạn; ứng dụng xử lý `ABORTED`, timeout, lỗi nghiệp vụ riêng.
- [ ] Stock/quota/order uniqueness có transaction và ID ổn định.
- [ ] Kiểm soát concurrency và hot documents; load test theo phân bố tải thật.
- [ ] Atomic transform chỉ dùng khi không cần điều kiện nghiệp vụ phức tạp.
- [ ] Web/Mobile Security Rules có tests; server SDK IAM tối thiểu.
- [ ] Transaction/batch tuân thủ request size, thời gian, transforms, Rules access calls.
- [ ] Offline rõ ràng: batch có thể queue, transaction không chạy offline.
- [ ] Không mở Rules toàn quyền để “thử nhanh” trên production.
- [ ] HTTP, Pub/Sub và event trigger retries đều idempotent.
- [ ] Theo dõi `ABORTED`, latency, duplicate skip, reads/writes, Billing.
- [ ] Data location, backup/PITR, index growth và budget được xem xét.
- [ ] Diễn tập cùng requestId, request khác nhau, last-stock và backend crash.

## 19. Kết luận

**Transaction** bảo vệ quyết định đọc–kiểm tra–ghi; **batched write** gom nhiều writes nguyên tử khi không cần đọc; **atomic transform** giải quyết thay đổi field đơn giản. Không công cụ nào tự tạo transaction xuyên Pub/Sub/Cloud SQL/payment hoặc loại bỏ giới hạn cạnh tranh trên một document.

Với Java/Firebase, mẫu đáng tin cậy là **xác thực → kiểm tra invariant trong transaction → commit với requestId ổn định → xử lý retry idempotent → quan sát contention và chi phí**. Khi một hot document trở thành nút thắt, phải **đổi data model/điều phối**, không chỉ tăng số instances.

## Tài liệu tham khảo chính thức

- [Firestore transactions and batched writes](https://firebase.google.com/docs/firestore/manage-data/transactions)
- [Transaction contention and concurrency modes](https://firebase.google.com/docs/firestore/transaction-data-contention)
- [Firestore best practices](https://firebase.google.com/docs/firestore/best-practices)
- [Firestore quotas and limits](https://firebase.google.com/docs/firestore/quotas)
- [Firestore Security Rules conditions/getAfter](https://firebase.google.com/docs/firestore/security/rules-conditions)
- [Firebase Local Emulator Suite](https://firebase.google.com/docs/emulator-suite/connect_firestore)
- [Distributed counters](https://firebase.google.com/docs/firestore/solutions/counters)
- [Firestore offline persistence](https://firebase.google.com/docs/firestore/manage-data/enable-offline)
- [Java Firestore transaction sample](https://cloud.google.com/firestore/docs/samples/firestore-transaction-document-update)
- [Firestore pricing](https://cloud.google.com/firestore/pricing)


