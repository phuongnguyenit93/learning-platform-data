# Touch và get-and-touch khi thao tác qua SDK

## 1. Mục tiêu và tình huống sử dụng

Trong **Spring Data Couchbase**, một document có thể có **expiry metadata** quy định thời điểm nó hết hiệu lực. Không chỉ các thao tác ghi nội dung mới thay đổi expiry: Couchbase Java SDK còn cung cấp `touch` và `getAndTouch` để **đặt lại thời hạn sống mà không phải thay JSON**.

Điều này rất hữu ích cho dữ liệu có *sliding TTL*, ví dụ một giỏ hàng chỉ còn hiệu lực 30 phút sau tương tác hợp lệ. Nhưng với mã OTP, token reset mật khẩu hoặc đặt chỗ có deadline cố định, một lần đọc không được tự động gia hạn. Việc chọn nhầm `getAndTouch` thay cho `get` có thể làm thay đổi ý nghĩa nghiệp vụ và mở rộng cửa sổ hiệu lực của dữ liệu nhạy cảm.

Bài học thuộc chương **Thời gian hết hạn** của module **SPRING_DATA_COUCHBASE**. Trong module này, tầng dữ liệu được xây dựng bằng document mapping, repository, `CouchbaseTemplate` và SQL++; bạn cũng học thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive. TOUCH và GET-AND-TOUCH nằm ngay tại ranh giới giữa **đọc**, **ghi metadata** và **quản lý nhất quán**.

Sau bài học, bạn sẽ có thể:

1. Phân biệt `get`, `touch`, `getAndTouch` và `get` theo sau `touch`.
2. Gọi API blocking/reactive với `Duration` đúng đơn vị, đúng keyspace.
3. Quyết định khi nào nên làm mới TTL, khi nào phải giữ expiry cũ hoặc deadline tuyệt đối.
4. Hiểu giới hạn tính nguyên tử của get-and-touch, đặc biệt khi phải kiểm tra content trước khi gia hạn.
5. Xử lý document-not-found, CAS conflict và mutation timeout mơ hồ.
6. Đối chiếu với Spring Data mapping, `maxTTL` server và yêu cầu hiệu năng.
7. Kiểm chứng expiry metadata và viết test để tránh gia hạn ngoài ý muốn.

Ví dụ sử dụng kiến trúc Spring Boot 3.x, Spring Data Couchbase 5.x và Couchbase Java SDK 3.x tương thích. Các option mở rộng và semantics chi tiết phải được đối chiếu theo phiên bản SDK/Server đang sử dụng.

## 2. Expiry là metadata, không phải một field JSON

Một document ví dụ:

~~~text
Cluster: commerce
Bucket: commerce
Scope: checkout
Collection: carts
Key: cart::u-42

JSON: { "userId": "u-42", "itemCount": 2 }

Metadata:
  CAS: ...
  expiry: thời điểm hết hiệu lực
~~~

Dù JSON chứa field `expiresAt`, Couchbase **không tự biến field đó thành expiry metadata**. Cần thao tác SDK hoặc mapping Spring Data có chủ đích để đặt expiry thật.

Couchbase có thể coi document đã hết hạn là không còn tồn tại hợp lệ với KV reads, dù dữ liệu vật lý chưa được thu hồi hoàn toàn ngay lúc đó. Đây là khác biệt giữa **expiry logic** và **dọn dẹp vật lý**.

### 2.1. Duration và Instant

- `Duration.ofMinutes(30)` mô tả một khoảng thời gian tương đối.
- `Instant.parse("2026-12-01T00:00:00Z")` mô tả một mốc tuyệt đối.
- `touch(key, Duration)` đặt lại expiry theo thời lượng của thao tác.
- `getAndTouch(key, Duration)` đọc document đồng thời đặt lại expiry theo thời lượng đó.
- `preserveExpiry(true)` trên mutation được hỗ trợ thể hiện ý định giữ **hạn cũ**, khác với TOUCH.

Nếu muốn deadline cố định, đừng tự động áp TTL tương đối mới mỗi lần truy cập.

## 3. Bảng so sánh thao tác SDK

| API | Trả JSON? | Sửa JSON? | Thay expiry? | Use case |
| --- | --- | --- | --- | --- |
| `get(id)` | Có | Không | Không theo mặc định | Đọc không side effect |
| `touch(id, ttl)` | Không | Không | **Có** | Gia hạn hoặc rút hạn metadata |
| `getAndTouch(id, ttl)` | Có | Không | **Có** | Đọc và làm mới hạn trong cùng thao tác |
| `get(id)` rồi `touch(id, ttl)` | Có | Không | Có tại bước touch | Kiểm tra content trước khi quyết định gia hạn |
| `replace(id, content, options)` | Không trực tiếp | Có | Tùy options | Ghi nội dung và expiry có điều kiện |
| `upsert(id, content, options)` | Không trực tiếp | Có | Tùy options | Tạo hoặc thay document |
| `getAndLock(id, ...)` | Có | Không | Không nhằm gia hạn TTL | Khóa tạm; mục đích khác |

Các lệnh này thao tác theo **document key**, không cần secondary index SQL++ để tìm key. `touch`/`getAndTouch` không phải insert hoặc upsert; nếu document đã hết hạn hoặc không tồn tại, chúng không tự tạo lại nó.

**Chọn `get` khi chỉ cần đọc.** Một thao tác đổi expiry không được ẩn sau tên method nghe như truy vấn thuần túy.

## 4. Timeline: một TOUCH thay đổi deadline ra sao?

Giả sử cart được tạo lúc 10:00 với TTL 30 phút:

~~~text
10:00  Cart được ghi; hạn ban đầu 10:30
10:10  Người dùng sửa giỏ, service gọi TOUCH 30 phút
10:20  GET cart bình thường
10:30  Mốc hết hạn ban đầu đã qua
10:40  Mốc hết hạn mới sau TOUCH
~~~

~~~mermaid
sequenceDiagram
    participant App as Cart Service
    participant CB as Couchbase KV
    App->>CB: 10:00 UPSERT TTL 30 phút
    Note over CB: Deadline ban đầu 10:30
    App->>CB: 10:10 TOUCH TTL 30 phút
    CB-->>App: MutationResult
    Note over CB: Deadline mới khoảng 10:40
    App->>CB: 10:20 GET
    CB-->>App: GetResult
    Note over CB: GET không tự gia hạn
~~~

Nếu mọi lần GET đều được thay bằng GET-AND-TOUCH, thời hạn có thể liên tục được làm mới theo tần suất đọc. Hành vi này chỉ đúng nếu sản phẩm thật sự muốn **sliding expiration theo mỗi lần truy cập**.

## 5. Lấy Collection handle từ Spring Data Couchbase

Với một ứng dụng Spring Boot, cấu hình kết nối có thể là:

~~~yaml
spring:
  couchbase:
    connection-string: "${COUCHBASE_CONNECTION_STRING:couchbase://127.0.0.1}"
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
  data:
    couchbase:
      bucket-name: "${COUCHBASE_BUCKET:commerce}"
~~~

Từ một bean Spring Data đã quản lý, có thể lấy SDK handle:

~~~java
import com.couchbase.client.java.Collection;
import org.springframework.data.couchbase.core.CouchbaseClientFactory;
import org.springframework.stereotype.Service;

@Service
public class CartAccessService {

    private final Collection carts;

    public CartAccessService(CouchbaseClientFactory factory) {
        this.carts = factory.getBucket()
                .scope("checkout")
                .collection("carts");
    }

    // Các method get, touch, getAndTouch ở đây.
}
~~~

Lưu ý:

- Bucket `commerce`, scope `checkout` và collection `carts` phải có trên server; việc lấy handle không tạo các tài nguyên này.
- Spring quản lý client/factory; không gọi `Cluster.connect()` cho mỗi request.
- Không `disconnect()` client sau khi TOUCH.
- SDK `Collection` thao tác trực tiếp, **không tự áp entity converter hoặc @Version** của Spring Data.

## 6. `touch(id, Duration)`: chỉ thay expiry

Ví dụ một service muốn làm mới hạn cart sau sự kiện người dùng thực sự chỉnh sửa giỏ:

~~~java
import java.time.Duration;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.MutationResult;

public final class CartRenewal {

    private final Collection carts;

    public CartRenewal(Collection carts) {
        this.carts = carts;
    }

    public MutationResult renewAfterEdit(String cartId) {
        return carts.touch(
                cartId,
                Duration.ofMinutes(30)
        );
    }
}
~~~

Nếu key tồn tại, operation yêu cầu đặt expiry mới, tương ứng với khoảng thời gian truyền vào; kết quả theo SDK thông dụng là `MutationResult`.

**TOUCH không cập nhật nội dung JSON.** Sau khi `renewAfterEdit` thành công, `itemCount` và danh sách sản phẩm vẫn là những giá trị trước đó. Vì vậy, không thể dùng TOUCH thay thế một lệnh cập nhật giỏ hàng.

### 6.1. Làm mới TTL bằng upsert cùng lần ghi nội dung

Khi cần sửa content và gia hạn TTL, có thể đặt expiry ngay trong mutation:

~~~java
import java.time.Duration;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

carts.upsert(
        "cart::u-42",
        JsonObject.create()
                .put("userId", "u-42")
                .put("itemCount", 3),
        UpsertOptions.upsertOptions()
                .expiry(Duration.ofMinutes(30))
);
~~~

Đoạn trên vừa ghi content vừa đặt TTL trong **một** operation. Nếu sau đó còn gọi `touch` ngay lập tức mà không có yêu cầu mới, thường chỉ làm tăng network và metadata mutations.

Lưu ý `upsert` có thể tạo document mới nếu key chưa tồn tại. Nếu use case phải từ chối cập nhật cart đã hết hạn, hãy dùng `replace` hoặc cơ chế điều kiện phù hợp thay vì mặc định upsert.

### 6.2. TOUCH có thể rút ngắn hạn

Một document còn 30 phút có thể bị đổi thành chỉ còn 2 phút:

~~~java
carts.touch(
        "cart::u-42",
        Duration.ofMinutes(2)
);
~~~

Vì vậy TOUCH nên được hiểu là **đặt expiry mới**, không phải lời hứa chỉ kéo dài hạn. Không gọi nó trong code không có quyền rút ngắn hay kéo dài vòng đời document.

## 7. `getAndTouch(id, Duration)`: đọc và làm mới cùng thao tác

Khi mỗi lần đọc được phép **gia hạn vô điều kiện**, SDK cung cấp get-and-touch:

~~~java
import java.time.Duration;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.json.JsonObject;

public JsonObject loadAndRenew(
        Collection carts, String cartId) {

    GetResult result = carts.getAndTouch(
            cartId,
            Duration.ofMinutes(30)
    );
    return result.contentAsObject();
}
~~~

`getAndTouch` thực hiện đồng thời hai tác dụng ở mức thao tác KV: lấy content và đặt expiry mới. Nó tránh gửi một lệnh GET rồi một lệnh TOUCH khi nghiệp vụ **luôn cần cả hai**.

Điều cần nhớ:

- API này **không phải read-only**.
- Nội dung JSON không được thay bởi operation.
- Key không tồn tại thì không có document mới được tạo.
- Nó không khóa document cho bước xử lý tiếp theo.
- Nó không phải một giao dịch bao gồm code Java chạy sau khi trả về.

### 7.1. Tác dụng phụ xảy ra trước khi ứng dụng xem content

Giả sử session có JSON:

~~~json
{
  "userId": "u-42",
  "revoked": true,
  "issuedAt": "2026-11-25T09:00:00Z"
}
~~~

Nếu service gọi `getAndTouch` trước, metadata expiry có thể đã được gia hạn **trước khi service đọc field `revoked` và từ chối session**.

Nếu chính sách nói chỉ được gia hạn **sau khi xác minh session chưa bị thu hồi**, một GET-AND-TOUCH đơn giản chưa đủ. Nên đọc/kiểm tra trước, rồi thực hiện mutation có điều phối phù hợp. Hai lệnh GET + TOUCH vẫn có race giữa bước kiểm tra và bước gia hạn, nên với yêu cầu nhất quán chặt phải thiết kế điều kiện cập nhật phù hợp, không tuyên bố hai lệnh là một transaction.

## 8. GET-AND-TOUCH khác GET rồi TOUCH

~~~mermaid
flowchart TD
    A["Use case cần gì?"] --> B{"Chỉ cần đọc JSON?"}
    B -- "Có" --> C["GET thuần"]
    B -- "Không" --> D{"Chỉ đổi expiry?"}
    D -- "Có" --> E["TOUCH"]
    D -- "Không" --> F{"Đọc và luôn gia hạn?"}
    F -- "Có" --> G["GET-AND-TOUCH"]
    F -- "Không" --> H["GET, kiểm tra policy, mutation phù hợp"]
~~~

| Đặc điểm | `getAndTouch` | `get` rồi `touch` |
| --- | --- | --- |
| Số lệnh KV | Một | Hai |
| Round trip | Thường thấp hơn | Thường cao hơn |
| Gia hạn có điều kiện sau khi xem content | Không làm được trước khi đổi expiry | Có thể quyết định sau GET, nhưng tồn tại race |
| Giữa đọc và gia hạn có thể hết hạn? | Không tách thành hai lệnh | Có |
| Khóa document? | Không | Không |
| Phù hợp | Sliding TTL cho mọi lần truy cập hợp lệ theo chính sách | Chính sách renewal phải kiểm tra trước |

Không gọi GET-AND-TOUCH chỉ để tiết kiệm một round trip nếu business logic **không cho phép đổi expiry**. Chi phí của một deadline sai thường lớn hơn chi phí một KV request.

## 9. Những nơi được và không được gia hạn

| Loại document | Chính sách điển hình | Dùng TOUCH/GET-AND-TOUCH? |
| --- | --- | --- |
| Cart | 30 phút từ lần sửa cuối | TOUCH sau sửa, GET khi chỉ xem |
| Session idle | 20 phút từ hoạt động được chấp nhận | Có thể gia hạn, nhưng phải xét revoked/hard deadline |
| Cache theo lần tạo | 1 giờ từ lúc tạo | GET bình thường, không làm mới |
| Cache sliding | 1 giờ từ mỗi lần truy cập | GET-AND-TOUCH có thể hợp lý |
| OTP | 5 phút từ lúc phát hành | Không TOUCH khi kiểm tra mã |
| Reset password token | Deadline cố định | Không renew khi đọc |
| Reservation | Thời điểm giữ chỗ cố định | Không gia hạn qua read |
| Audit/order | Retention theo chính sách riêng | Không TOUCH tùy tiện |

Tên method nên minh bạch: `loadAndRenewSession` thể hiện side effect, còn `findSession` thường gợi ý chỉ đọc. Không ẩn việc gia hạn trong các getter được nhiều tầng nghiệp vụ gọi lại.

## 10. Sliding TTL cần phối hợp absolute lifetime

Một phiên đăng nhập có thể có:

- Idle timeout 20 phút.
- Absolute lifetime 8 giờ kể từ thời điểm phát hành.

Nếu mỗi request cứ `touch(id, Duration.ofMinutes(20))`, một session liên tục hoạt động có thể sống vượt 8 giờ.

~~~text
issuedAt:          09:00
hardDeadline:      17:00
lastActivity:      16:50
idleDeadline:      17:10
effectiveDeadline: 17:00
~~~

Deadline cần là **min(now + idleTTL, issuedAt + absoluteLifetime)**. Có thể tính bằng Java:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class SessionExpiryPolicy {

    public static Instant effectiveDeadline(
            Instant issuedAt,
            Duration idleTimeout,
            Duration absoluteLifetime,
            Clock clock) {

        Instant now = Instant.now(clock);
        Instant idleUntil = now.plus(idleTimeout);
        Instant hardUntil = issuedAt.plus(absoluteLifetime);

        return idleUntil.isBefore(hardUntil)
                ? idleUntil
                : hardUntil;
    }
}
~~~

Nếu effective deadline đã qua, từ chối gia hạn. Không đặt lại `issuedAt` mỗi khi người dùng hoạt động.

### 10.1. Khi TOUCH chỉ nhận Duration

Bạn có thể tính thời lượng còn lại đến deadline:

~~~java
import java.time.Duration;
import java.time.Instant;

Duration remaining = Duration.between(
        Instant.now(clock),
        effectiveDeadline
);
if (remaining.isZero() || remaining.isNegative()) {
    throw new IllegalStateException("Session expired");
}
~~~

Tuy nhiên TTL protocol/server có giới hạn độ phân giải thời gian; việc chuyển từ `Instant` sang `Duration` có thể chịu rounding và độ trễ. Nếu cần không vượt hard deadline, cách bảo thủ là chỉ sử dụng số **giây nguyên không làm tròn tăng**:

~~~java
long wholeSeconds = remaining.getSeconds();
if (wholeSeconds <= 0) {
    throw new IllegalStateException("Too little lifetime remains");
}
Duration conservativeTtl = Duration.ofSeconds(wholeSeconds);
~~~

Đây không phải thay thế cho việc kiểm tra deadline ở bước xác thực/ủy quyền. Với yêu cầu deadline chính xác, một mutation hỗ trợ `expiry(Instant)` có thể thể hiện ý định rõ hơn, đi cùng kiểm soát CAS và policy. Không dựa hoàn toàn vào `maxTTL` như một hard lifetime tính từ `issuedAt`.

## 11. TOUCH là mutation metadata và có thể ảnh hưởng CAS

CAS (*Compare-And-Swap*) hỗ trợ optimistic concurrency trên document. TOUCH không thay JSON nhưng vẫn là thao tác thay expiry metadata; không nên coi nó tương đương GET trong các luồng phụ thuộc CAS.

Tình huống:

~~~text
T0  Request A GET cart và nhận CAS c1
T1  Request B TOUCH cart, expiry đổi
T2  Request A REPLACE với CAS c1
~~~

Trên các version/server phù hợp, một mutation expiry có thể tạo CAS mới khiến thao tác REPLACE của A gặp conflict. Hãy **xem TOUCH như mutation có thể tác động CAS** và kiểm chứng với server version, đặc biệt nếu repository dùng Spring Data `@Version`.

### 11.1. Khi cần thay content và expiry cùng một mutation

~~~java
import java.time.Duration;
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.kv.ReplaceOptions;

GetResult current = carts.get("cart::u-42");
var updated = current.contentAsObject();
updated.put("itemCount", 4);

carts.replace(
        "cart::u-42",
        updated,
        ReplaceOptions.replaceOptions()
                .cas(current.cas())
                .expiry(Duration.ofMinutes(30))
);
~~~

Thao tác thay nội dung dựa trên CAS và áp expiry mới cùng request. `replace` ghi **toàn bộ JSON**, không phải partial update. Nếu dữ liệu có nhiều field, `updated` phải được xây dựng đủ hoặc chọn subdocument API thích hợp.

Nếu CAS conflict, đọc lại và đánh giá retry có giới hạn; không làm mới TTL chỉ vì lỗi kỹ thuật nếu business chưa có hoạt động được phép gia hạn.

## 12. Không nên tự tạo lại document hết hạn

Nếu key không tồn tại hoặc đã hết hạn logic, `touch` và `getAndTouch` không tự tạo mới. Ví dụ xử lý lỗi:

~~~java
import java.time.Duration;
import com.couchbase.client.core.error.DocumentNotFoundException;
import com.couchbase.client.java.Collection;

public boolean renewIfPresent(
        Collection carts, String cartId) {
    try {
        carts.touch(cartId, Duration.ofMinutes(30));
        return true;
    } catch (DocumentNotFoundException ex) {
        return false;
    }
}
~~~

Với cart, kết quả false có thể dẫn người dùng tới luồng tạo giỏ mới. Với OTP hoặc session bị hết hạn, false là lý do **không** được hồi sinh khóa cũ bằng upsert mặc định.

### 12.1. Race condition GET rồi TOUCH

~~~text
10:29:59.900  GET thành công
10:30:00.000  Document hết hạn
10:30:00.100  TOUCH trả not-found
~~~

Đây không phải lỗi kỳ lạ; hai lệnh không nguyên tử. GET-AND-TOUCH tránh khoảng hở của hai lệnh nếu nghiệp vụ cho phép gia hạn đồng thời với đọc. Ngược lại, khi buộc phải kiểm tra field trước khi gia hạn, vẫn cần xử lý concurrency phù hợp.

### 12.2. Timeout không chứng minh TOUCH chưa được áp

Nếu client bị timeout, thao tác có thể đã tới server và thay expiry nhưng response bị mất. Không mặc định retry vô hạn, vì mỗi lần retry có thể tạo deadline mới. Với nghiệp vụ nhạy cảm, đọc/đối soát expiry metadata khi khả thi và thiết kế idempotency/giới hạn retry rõ ràng.

## 13. Spring Data repository và SDK TOUCH là hai đường khác nhau

Entity ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;

@Document(expiry = 1800) // TTL tĩnh ở các version hỗ trợ, đơn vị giây
public class CartDocument {

    @Id
    private String id;
    private String userId;

    protected CartDocument() { }

    public CartDocument(String id, String userId) {
        this.id = id;
        this.userId = userId;
    }

    public String getId() { return id; }
    public String getUserId() { return userId; }
}
~~~

Repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CartRepository
        extends CouchbaseRepository<CartDocument, String> {
}
~~~

Điểm phân biệt:

- `repository.findById(id)` đọc entity, **không tự được hiểu là GET-AND-TOUCH**.
- `repository.save(entity)` đi qua mapper có thể áp TTL trên `@Document` theo semantics version/operation.
- `collection.touch(...)` và `getAndTouch(...)` là SDK trực tiếp; chúng không tự đọc `@Document(expiry)`.
- `CouchbaseTemplate` có thể hỗ trợ các mutation/options khác tùy version; cần kiểm tra tác dụng expiry của đường template.
- SQL++ `SELECT` không tự gia hạn TTL như GET-AND-TOUCH; Query service/index không phải điều kiện của SDK TOUCH theo key.

Khi nhiều service dùng repository, template và SDK trên cùng document, phải xác định **ai có quyền làm mới expiry**, và kiểm thử thứ tự mutation/CAS để tránh save sau đó reset hạn ngoài ý muốn.

## 14. Server `maxTTL` có thể giới hạn expiry được đặt

Couchbase Server có thể áp maximum TTL ở bucket và/hoặc collection, tùy phiên bản.

| Thao tác client | Server policy | Hành vi cần xác minh |
| --- | --- | --- |
| TOUCH 30 phút | Collection maxTTL 10 phút | Có thể bị giới hạn khoảng 10 phút |
| GET-AND-TOUCH 20 phút | Bucket maxTTL 1 giờ | TTL 20 phút có thể hợp lệ |
| TOUCH 2 giờ | Collection maxTTL 30 phút | Có thể bị giới hạn còn khoảng 30 phút |
| TOUCH một document trước đó không TTL | Server maxTTL | Cần xem expiry metadata hiệu lực |
| TOUCH với `Duration.ZERO` | Có maxTTL | Không suy ra document được giữ vô thời hạn |

`maxTTL` là **chính sách phía server**; không tự phát sinh từ `@Document` hoặc property Spring Boot kết nối. Cần xem cấu hình của đúng bucket/collection mà handle đang sử dụng.

~~~mermaid
flowchart LR
    A["touch / getAndTouch với Duration"] --> B["Couchbase Server"]
    C["Bucket/collection maxTTL"] --> B
    B --> D["Expiry metadata thực tế"]
~~~

Đừng tự xem maxTTL như hard deadline tính từ lúc tạo session. Sliding updates có thể được xử lý theo chính sách khác; nếu muốn giới hạn 8 giờ kể từ phát hành, cần **lưu và kiểm tra hard deadline nghiệp vụ**.

## 15. Reactive API: TOUCH và GET-AND-TOUCH

Couchbase Java SDK reactive cung cấp những thao tác tương ứng:

~~~java
import java.time.Duration;
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.kv.MutationResult;
import reactor.core.publisher.Mono;

Mono<MutationResult> renewal =
        carts.reactive().touch(
                "cart::u-42",
                Duration.ofMinutes(30)
        );

Mono<GetResult> readAndRenew =
        carts.reactive().getAndTouch(
                "cart::u-42",
                Duration.ofMinutes(30)
        );
~~~

Một `Mono` là mô tả pipeline; chỉ tạo nó chưa chắc mutation đã được thực thi. Cần subscription theo ngữ nghĩa Reactor.

**Các lỗi cần tránh:**

- Retry/resubscribe có thể thực hiện TOUCH nhiều lần và kéo dài deadline hơn dự định.
- `Mono.timeout(Duration.ofSeconds(2))` là **pipeline timeout**, không phải TTL document.
- Hủy subscription không chứng minh server chưa nhận mutation.
- Không gọi `block()` trên WebFlux event-loop để “chắc chắn đã gia hạn”.
- Không nuốt mọi lỗi thành `Mono.empty()`, vì outage và document-not-found khác nhau.

Ví dụ chỉ xem cart đã hết hạn như không có dữ liệu:

~~~java
import java.time.Duration;
import com.couchbase.client.core.error.DocumentNotFoundException;
import com.couchbase.client.java.json.JsonObject;
import reactor.core.publisher.Mono;

Mono<JsonObject> cart =
        carts.reactive()
                .getAndTouch(
                        "cart::u-42",
                        Duration.ofMinutes(30)
                )
                .map(result -> result.contentAsObject())
                .onErrorResume(
                        DocumentNotFoundException.class,
                        ignored -> Mono.empty()
                );
~~~

Ví dụ trên **chỉ phù hợp khi nghiệp vụ cho phép gia hạn mọi cart được đọc**. Nếu đây chỉ là endpoint hiển thị cart, thay `getAndTouch` bằng `get` để không gia hạn.

## 16. Hiệu năng: một read có thể trở thành metadata write

Get-and-touch có thể giảm round trip so với GET + TOUCH, nhưng nó khiến mỗi lần đọc đi kèm một **metadata mutation**. Với các session được đọc hàng trăm lần/phút, điều này tạo thêm tải và có thể ảnh hưởng CAS conflict.

Ví dụ minh họa số lệnh, không phải benchmark:

~~~text
100 lượt đọc session mỗi phút:

GET thuần:              khoảng 100 KV read
GET-AND-TOUCH mỗi lần:  khoảng 100 lần có mutation expiry
GET + TOUCH mỗi lần:    khoảng 100 GET và 100 TOUCH
~~~

Vì vậy ưu tiên thiết kế theo chính sách:

1. Gia hạn khi có tương tác thật sự được phép.
2. Không renew trên các request thụ động.
3. Nếu phù hợp, chỉ renew khi remaining TTL dưới ngưỡng, chẳng hạn còn dưới 5 phút.
4. Nếu dùng GET rồi kiểm tra expiry trước TOUCH, phải xử lý race; không coi hai lệnh là atomic.
5. Đo latency p95/p99, lỗi KV, số touch, CAS conflict và tải Data service.

Không mặc định đọc expiry metadata cho mọi request production nếu chi phí không cần thiết; bật theo nhu cầu kiểm chứng hoặc nghiệp vụ cụ thể.

## 17. Đọc metadata expiry để kiểm chứng

SDK Java có thể trả thông tin expiry khi gọi `get` với option phù hợp:

~~~java
import com.couchbase.client.java.kv.GetOptions;

var result = carts.get(
        "cart::u-42",
        GetOptions.getOptions().withExpiry(true)
);

result.expiryTime().ifPresent(deadline ->
        System.out.println("Expiry: " + deadline)
);
~~~

`withExpiry(true)` yêu cầu SDK/server trả thêm expiry metadata. `expiryTime()` có kết quả tùy chọn ở những SDK hỗ trợ; cần đọc contract release đang dùng để diễn giải thiếu metadata.

**Quy trình kiểm chứng touch:**

1. Ghi một document có TTL 15 giây trong collection test có maxTTL đã biết.
2. Đọc metadata expiry và CAS ban đầu.
3. Sau 2 giây, gọi `touch(id, Duration.ofSeconds(15))`.
4. Đọc metadata sau và so sánh: hạn mới phải dịch theo ý định nếu policy cho phép.
5. Kiểm tra JSON content không đổi.
6. Với CAS, so token trước/sau để nắm semantics thực tế trong môi trường đó.

**Quy trình kiểm chứng get-and-touch:**

1. Ghi document với TTL ngắn và JSON rõ.
2. Đọc expiry metadata trước.
3. `getAndTouch(id, Duration.ofSeconds(20))`.
4. Kiểm tra JSON được trả về.
5. Đọc lại expiry và xác nhận deadline mới.
6. Gọi `get(id)` thường rồi kiểm tra không có gia hạn thêm.
7. Thử key không tồn tại/hết hạn.

Đừng assert tại đúng một mili giây; dùng độ dung sai và polling có deadline để tránh flaky tests.

## 18. Tạo dữ liệu test và kiểm tra hard deadline

Ví dụ insert một key test riêng:

~~~java
import java.time.Duration;
import java.util.UUID;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

String id = "touch-it::" + UUID.randomUUID();

testCollection.upsert(
        id,
        JsonObject.create().put("purpose", "expiry-test"),
        UpsertOptions.upsertOptions()
                .expiry(Duration.ofSeconds(15))
);
~~~

Đặt test trong collection riêng, dọn key còn lại nếu test lỗi, và kiểm tra policy maxTTL trước. Một test trong collection production có TTL hoặc RBAC khác có thể cho kết quả sai lệch.

Unit test phép tính deadline không cần Couchbase:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class SessionExpiryPolicyTest {

    @Test
    void hardDeadlineCapsIdleRenewal() {
        Instant issuedAt = Instant.parse("2026-12-01T09:00:00Z");
        Clock clock = Clock.fixed(
                Instant.parse("2026-12-01T16:50:00Z"),
                ZoneOffset.UTC
        );

        Instant deadline = SessionExpiryPolicy.effectiveDeadline(
                issuedAt,
                Duration.ofMinutes(20),
                Duration.ofHours(8),
                clock
        );

        assertThat(deadline).isEqualTo(
                Instant.parse("2026-12-01T17:00:00Z")
        );
    }
}
~~~

Unit test chứng minh chính sách, còn integration test chứng minh metadata expiry đã được Couchbase Server áp dụng. Cần cả hai.

## 19. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Cart bị gia hạn khi chỉ xem | Getter dùng getAndTouch | Chuyển read-only sang get |
| Session sống quá hard deadline | TOUCH 20 phút không xét thời điểm phát hành | Tính effective deadline và kiểm tra quyền truy cập |
| OTP sống lâu hơn dự kiến | Luồng kiểm tra OTP có TOUCH | Bỏ gia hạn, giữ hạn cố định |
| TOUCH báo not found | Document đã hết hạn hoặc keyspace sai | Kiểm tra bucket/scope/collection và xử lý nghiệp vụ |
| GET thành công nhưng TOUCH không tìm thấy | Race giữa hai lệnh | Xử lý not-found; dùng getAndTouch nếu policy cho phép |
| Repository save gặp CAS conflict | TOUCH có thể thay CAS | Kiểm chứng mutation/version, đọc lại và xử lý conflict |
| TTL yêu cầu 30m nhưng hiệu lực 10m | Server maxTTL thấp hơn | Xem cấu hình bucket/collection |
| TOUCH xong content vẫn cũ | TOUCH không sửa JSON | Dùng replace/subdocument update |
| Content mất field sau replace | Replace JSON không đầy đủ | Merge đầy đủ hoặc dùng subdocument |
| Reactive TOUCH không chạy | Publisher chưa được subscribe | Kiểm tra subscription/error |
| Retry làm deadline kéo dài | TOUCH được gọi lại sau timeout | Fixed deadline hoặc kiểm soát retry |
| Timeout nhưng không rõ hạn có đổi | Response thất lạc sau khi server áp mutation | Đối soát metadata |
| SQL++ không thấy document | Query/index/consistency hoặc document hết hạn | Kiểm tra KV theo ID trước |
| Document expired nhưng disk chưa giảm | Expiry logic không đồng thời thu hồi vật lý | Theo dõi metrics server |

## 20. Bài tập tình huống: giỏ hàng, session và OTP

Một hệ thống checkout có:

~~~text
commerce.checkout.carts
commerce.checkout.sessions
commerce.checkout.otp_codes
~~~

Chính sách:

- Cart: TTL 30 phút từ **lần sửa giỏ** hợp lệ gần nhất, không renew khi chỉ xem.
- Session: idle TTL 20 phút, hard lifetime 8 giờ, có field `revoked` phải kiểm tra.
- OTP: hết hạn đúng 5 phút từ phát hành, không renew khi kiểm tra mã.
- Server maxTTL của `carts` đang là 10 phút.
- Ứng dụng có cả repository, SDK blocking và reactive.

**Câu hỏi:**

1. Endpoint chỉ xem cart nên dùng `get` hay `getAndTouch`? Vì sao?
2. Khi sửa JSON và TTL cùng lúc, `replace` có CAS và expiry mới có lợi gì hơn `replace` rồi `touch`?
3. Khi đọc session có `revoked`, get-and-touch có thể gia hạn trước khi biết trạng thái gì?
4. Nếu chỉ còn 10 phút tới hard deadline, có nên TOUCH 20 phút không?
5. Vì sao server có thể chỉ cho cart sống 10 phút dù SDK yêu cầu 30 phút?
6. TOUCH có ảnh hưởng tới CAS và `@Version` của repository không?
7. Nếu GET thành công nhưng TOUCH bị not-found, nên xử lý thế nào?
8. Với OTP, tại sao get-and-touch làm sai thời hạn an toàn?
9. Vì sao một `Mono` mới tạo chưa chứng minh TTL được gia hạn?
10. Hãy thiết kế test đọc expiry metadata trước/sau GET, TOUCH và GET-AND-TOUCH.

**Hướng giải:** đọc thuần dùng GET; renewal chỉ ở sự kiện được phép; session phải kiểm tra revoked/hard deadline; document đã hết hạn không được hồi sinh mặc định; maxTTL có thể giới hạn, CAS cần kiểm soát và expiry metadata phải được kiểm chứng trên server.

## 21. Checklist trước production

- [ ] Mọi lời gọi `touch`/`getAndTouch` có sự kiện nghiệp vụ cho phép đổi expiry.
- [ ] Getter read-only không âm thầm gia hạn.
- [ ] OTP, token và deadline cố định không bị renew khi truy cập.
- [ ] Sliding TTL không vượt absolute lifetime.
- [ ] Không dùng get-and-touch khi phải kiểm tra nội dung **trước** khi gia hạn.
- [ ] Khi sửa content và expiry có cạnh tranh, cân nhắc một mutation với CAS.
- [ ] Đã xử lý document-not-found và race GET/TOUCH.
- [ ] Đã kiểm tra ảnh hưởng CAS của metadata mutation.
- [ ] Spring Data repository/template/SDK có chính sách expiry thống nhất.
- [ ] Biết server `maxTTL` ở đúng keyspace.
- [ ] TTL có đơn vị tường minh và validation hợp lệ.
- [ ] Không tạo metadata writes không cần thiết trên mọi read.
- [ ] Reactive operations được subscribe; retry không kéo dài hạn trái policy.
- [ ] Ambiguous timeout không bị suy thành chắc chắn chưa đổi expiry.
- [ ] Có integration test đọc `expiryTime()` trước/sau thao tác.
- [ ] Có unit test với `Clock.fixed` cho hard deadline.
- [ ] Không xem TTL là cam kết xóa vật lý ngay khỏi mọi backup/replica.

## 22. Tổng kết

`touch(id, Duration)` đặt lại expiry metadata cho một document đang tồn tại **mà không đọc hoặc thay JSON**. `getAndTouch(id, Duration)` vừa lấy nội dung vừa thay expiry trong **một thao tác Key-Value**. Chúng hữu ích cho sliding TTL, nhưng **không phải những lệnh GET thụ động** và không đồng nghĩa với preserve expiry.

Khi dùng Spring Data Couchbase, cần phân biệt SDK trực tiếp với repository/`CouchbaseTemplate`, kiểm soát CAS, `maxTTL` và concurrency, đồng thời bảo vệ deadline cố định khỏi retry hoặc gia hạn không được phép.

Bằng cách quy định rõ **khi nào một lượt truy cập được quyền làm mới thời hạn**, kiểm tra hard deadline và đọc lại metadata expiry khi test, ứng dụng có thể sử dụng TOUCH/GET-AND-TOUCH hiệu quả mà không làm sai vòng đời document.

