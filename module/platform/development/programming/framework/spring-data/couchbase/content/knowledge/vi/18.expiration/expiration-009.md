# Thiết kế phiên đăng nhập, mã xác thực và dữ liệu tạm

## 1. Bài toán: không phải mọi document ngắn hạn đều có cùng vòng đời

Trong **Spring Data Couchbase**, TTL (time to live) cho phép một document không còn hiệu lực sau một thời điểm nhất định. Điều này phù hợp với phiên đăng nhập, mã OTP, token xác minh, giỏ hàng nháp, khóa giữ chỗ và dữ liệu xử lý trung gian. Tuy nhiên, chỉ thêm `@Document(expiry = 900)` hoặc `UpsertOptions.expiry(Duration.ofMinutes(15))` chưa đủ để thiết kế đúng vòng đời và bảo mật.

Ba tình huống thể hiện sự khác nhau:

- **Phiên đăng nhập:** có thể cần gia hạn sau hoạt động hợp lệ, nhưng không được vượt quá tuổi thọ tối đa tính từ lúc phát hành; phải có cách thu hồi.
- **Mã xác thực:** có deadline cố định, số lần thử giới hạn và chỉ được sử dụng thành công một lần; việc kiểm tra hoặc nhập sai không được gia hạn.
- **Dữ liệu tạm:** có thể được xóa khi không còn cần thiết, nhưng TTL không phải scheduler đáng tin cậy để kích hoạt nghiệp vụ đúng giờ; dữ liệu đang xử lý cũng không nên tự biến mất giữa chừng nếu quy trình chưa được bảo vệ.

Bài thuộc chương **Thời gian hết hạn** của module **SPRING_DATA_COUCHBASE**. Phạm vi module là xây dựng tầng truy cập Couchbase bằng document mapping, repository, `CouchbaseTemplate` và SQL++; thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và lựa chọn API reactive để bảo đảm hiệu năng, nhất quán và khả năng vận hành.

**Mục tiêu học tập:**

1. Lựa chọn đúng TTL tương đối và deadline tuyệt đối cho từng loại dữ liệu.
2. Thiết kế session với idle expiry, absolute lifetime, rotation, logout/revocation và concurrency.
3. Thiết kế OTP một lần, deadline không gia hạn, giới hạn số lần thử và cập nhật bằng CAS.
4. Phân biệt TTL dùng dọn dữ liệu với deadline nghiệp vụ cần kiểm tra trước khi chấp nhận hành động.
5. Tách keyspace và `maxTTL` theo retention, đồng thời thống nhất đường ghi Spring Data/SDK/SQL++.
6. Thiết kế retry, idempotency, reactive pipeline, kiểm thử và observability phù hợp.

Ví dụ theo phong cách **Java 17, Spring Boot 3.x, Spring Data Couchbase 5.x và Couchbase Java SDK 3.x** tương thích. API nâng cao hoặc ngữ nghĩa expire/update có thể khác giữa các phiên bản, vì thế cần xác minh artifact cùng Couchbase Server thực tế trước khi triển khai.

## 2. Bắt đầu bằng bảng chính sách dữ liệu

Trước khi chọn annotation hoặc SDK method, viết chính sách nghiệp vụ:

| Loại dữ liệu | Thời gian sống | Được gia hạn? | Được tái sử dụng? | Điều kiện kết thúc |
| --- | --- | --- | --- | --- |
| Session đăng nhập | Idle 20 phút, tối đa 8 giờ từ lúc tạo | Có, sau hoạt động hợp lệ | Chỉ phiên chưa bị thu hồi | Idle timeout, hard deadline, logout, revoke |
| OTP xác minh | 5 phút từ lúc phát hành | **Không** | **Không** sau khi dùng thành công | Hết hạn, dùng thành công, hết lượt thử, revoke |
| Token reset mật khẩu | Ví dụ 15 phút từ lúc tạo | **Không** | **Không** | Sử dụng, thu hồi hoặc hết hạn |
| Giỏ hàng nháp | 30 phút từ lần sửa gần nhất | Có, sau thao tác sửa | Có thể tiếp tục sửa | TTL hoặc người dùng chốt/xóa |
| Reservation giữ chỗ | Deadline cố định đã thông báo | Chỉ theo thao tác gia hạn được phê duyệt | Không sau xác nhận/hủy | Xác nhận, hủy, hết hạn |
| Kết quả xuất báo cáo tạm | Ví dụ 1 ngày từ lúc tạo xong | Thường không | Có thể tải trong hạn | Hết hạn hoặc xóa chủ động |
| Job trung gian | Theo giai đoạn xử lý | Theo checkpoint/lease được thiết kế | Có thể retry có kiểm soát | Hoàn thành, thất bại, cleanup |
| Khóa idempotency | Bằng hoặc dài hơn cửa sổ retry đã cam kết | Theo contract rõ ràng | Ngăn tác động lặp | Hết cửa sổ chống trùng |

**TTL không thay thế state machine.** Một OTP hết hạn không đồng nghĩa mọi bước xác minh được rollback; một reservation hết hạn không tự hoàn tiền; một job document mất đi không làm scheduler biết công việc đã xử lý thành công.

## 3. Mô hình bucket/scope/collection theo vòng đời

Ví dụ hệ thống thương mại:

~~~text
Bucket: commerce
├── Scope: auth
│   ├── Collection: sessions
│   ├── Collection: otp_challenges
│   └── Collection: reset_tokens
├── Scope: checkout
│   ├── Collection: carts
│   ├── Collection: reservations
│   └── Collection: idempotency_keys
└── Scope: processing
    ├── Collection: export_jobs
    └── Collection: temporary_results
~~~

Lợi ích của phân nhóm:

1. Dễ áp quyền RBAC khác nhau cho session, mã xác thực và dữ liệu tạm.
2. Có thể đặt và quan sát policy `maxTTL` phù hợp theo khả năng của server.
3. Dễ xây index SQL++ theo nhu cầu từng loại, tránh query/index chung quá rộng.
4. Dễ đặt cảnh báo document-not-found, số document sống và lưu lượng mutation theo collection.
5. Hạn chế việc thay TTL của dữ liệu tạm vô tình ảnh hưởng order hoặc audit.

**Cảnh báo:** `maxTTL` của bucket/collection là cấu hình phía Couchbase Server. Nó có thể áp expiry mặc định hoặc giới hạn thời gian mà client yêu cầu; cơ chế kế thừa/ưu tiên cần kiểm tra theo server version. Không có annotation Java nào tự tạo collection hay tự chỉnh maxTTL.

### 3.1. Đặt key có ngữ nghĩa và khó đoán khi cần

Ví dụ:

~~~text
session::[opaque-random-token]
otp::[opaque-challenge-id]
cart::[user-id]
reservation::[reservation-id]
job::[job-id]
idempotency::[caller-scope]::[operation-id]
~~~

Với session, key hoặc token được sử dụng để xác thực **phải khó đoán và có entropy cao**; không dùng `session::user-42` như một bearer token. Nếu session key được lộ ra log hoặc URL, TTL không bảo vệ khỏi việc chiếm phiên trong thời gian còn hạn.

Đối với OTP, key nên là challenge ID riêng, tránh vô tình ghi đè một challenge còn hiệu lực khi người dùng yêu cầu mã mới. Tách **định danh challenge** khỏi **giá trị OTP**.

## 4. Relative TTL và absolute deadline khác nhau ra sao?

`Duration` diễn đạt “sống thêm bao lâu kể từ khi áp expiry”; `Instant` diễn đạt “hết hạn lúc nào”.

~~~java
import java.time.Duration;
import java.time.Instant;

Duration cartIdle = Duration.ofMinutes(30);

Instant issuedAt = Instant.parse("2026-12-01T10:00:00Z");
Instant otpDeadline = issuedAt.plus(Duration.ofMinutes(5));
~~~

Nếu cùng một mutation dùng `expiry(Duration.ofMinutes(5))` lúc 10:03 thay vì 10:00, deadline mới có thể dịch từ 10:05 thành 10:08. Đây là lỗi với OTP, nhưng có thể đúng với một giỏ hàng sliding.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant CB as Couchbase KV
    App->>CB: 10:00 tạo OTP, deadline 10:05
    alt Cập nhật bằng TTL tương đối mới
        App->>CB: 10:03 update, TTL 5 phút
        Note over CB: Deadline có thể thành 10:08
    else Preserve hoặc cùng Instant cũ
        App->>CB: 10:03 update, giữ hạn 10:05
        Note over CB: Deadline vẫn là 10:05
    end
~~~

Để kiểm soát vòng đời an toàn, lưu một deadline nghiệp vụ đáng tin cậy và chọn API expiry phù hợp cho **từng đường ghi**.

## 5. TTL không tự thực thi một hành động nghiệp vụ

Couchbase có thể khiến document hết hạn và không còn đọc được như dữ liệu hợp lệ. Tuy nhiên, không nên dựa vào mốc expire để cam kết:

- Gửi email “phiên đã hết hạn” chính xác đúng giây.
- Hủy giữ chỗ và hoàn tồn kho tức thời.
- Đánh dấu đơn hàng thành trạng thái `CANCELLED`.
- Gọi webhook hoặc phát event đúng deadline.
- Xóa vật lý mọi byte khỏi replica, backup hoặc hệ thống downstream cùng lúc.

Expiry logic, quét dọn nền, cập nhật index và compaction có thể diễn ra theo nhịp riêng. Với nhiệm vụ cần diễn ra vào giờ cụ thể, phải thiết kế **scheduler/event processor** hoặc state transition có kiểm tra deadline/idempotency, dùng TTL như cơ chế dọn dữ liệu bổ sung.

Một tình huống dễ sai: reservation document hết hạn và biến mất trước khi job giải phóng inventory đọc nó. Nếu toàn bộ thông tin giải phóng chỉ nằm trong document đã bị TTL, job có thể **mất ngữ cảnh**. Khi nghiệp vụ phải thực thi hậu quả, lưu state/event bền vững ở nơi phù hợp, không chỉ chờ document biến mất.

## 6. Cấu hình TTL có kiểu và validation

Giữ thời hạn ở một nguồn cấu hình của ứng dụng:

~~~yaml
app:
  expiration:
    session-idle: 20m
    session-absolute: 8h
    otp: 5m
    reset-token: 15m
    cart-idle: 30m
    temporary-result: 1d
~~~

Các property `app.expiration.*` là **tự định nghĩa**. Spring Boot không tự biến chúng thành expiry của Couchbase; service phải bind rồi truyền vào SDK hoặc một cơ chế mapping được version hỗ trợ.

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.expiration")
public record ExpirationProperties(
        Duration sessionIdle,
        Duration sessionAbsolute,
        Duration otp,
        Duration resetToken,
        Duration cartIdle,
        Duration temporaryResult
) {
    public ExpirationProperties {
        positive("sessionIdle", sessionIdle);
        positive("sessionAbsolute", sessionAbsolute);
        positive("otp", otp);
        positive("resetToken", resetToken);
        positive("cartIdle", cartIdle);
        positive("temporaryResult", temporaryResult);

        if (sessionIdle.compareTo(sessionAbsolute) > 0) {
            throw new IllegalArgumentException(
                    "sessionIdle must not exceed sessionAbsolute"
            );
        }
    }

    private static void positive(String name, Duration value) {
        if (value == null || value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException("Invalid TTL: " + name);
        }
    }
}
~~~

Đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Việc parse `20m` thành `Duration` giúp tránh lỗi số `1200` bị hiểu là 1200 mili giây khi bind Duration không có suffix. `@Document(expiry = 1200)` lại thường diễn đạt **giây** trên Spring Data Couchbase release hỗ trợ API đó.

Không để một bản config production vô tình bật các TTL ngắn phục vụ integration test. Khi thay config, document cũ **không tự động đổi expiry metadata** nếu không có mutation/migration.

## 7. Kết nối Spring Data và lấy SDK collection đúng vòng đời

Cấu hình Spring Boot:

~~~yaml
spring:
  couchbase:
    connection-string: "couchbases://cb.example.internal"
    username: "app-user"
    password: "supply-through-secret-manager"
  data:
    couchbase:
      bucket-name: commerce
~~~

Đây là ví dụ cấu hình, không dùng mật khẩu minh họa trong production. Kết nối thật cần TLS/trust và secret injection phù hợp.

Dùng `CouchbaseClientFactory` do Spring Data quản lý:

~~~java
import com.couchbase.client.java.Collection;
import org.springframework.data.couchbase.core.CouchbaseClientFactory;

public final class AuthCollections {

    private final Collection sessions;
    private final Collection otpChallenges;

    public AuthCollections(CouchbaseClientFactory factory) {
        this.sessions = factory.getBucket()
                .scope("auth")
                .collection("sessions");
        this.otpChallenges = factory.getBucket()
                .scope("auth")
                .collection("otp_challenges");
    }

    public Collection sessions() { return sessions; }
    public Collection otpChallenges() { return otpChallenges; }
}
~~~

Đây là một class helper; muốn inject nó như bean cần đăng ký ở Spring configuration phù hợp. Bucket/scope/collection phải được tạo trên server trước. Không tạo/đóng `Cluster` ở mỗi request và không gọi `disconnect()` cho SDK handle riêng lẻ sau `get` hoặc `upsert`.

**Trộn SDK với repository cần kiểm soát mapping.** Các lệnh `Collection` SDK trực tiếp không tự chạy `@Document` converter, `@Version` hoặc expiry annotation của entity.

## 8. Thiết kế session: state tối thiểu

Một session có thể lưu các trường:

~~~json
{
  "userId": "u-42",
  "issuedAt": "2026-12-01T09:00:00Z",
  "lastActivityAt": "2026-12-01T09:25:00Z",
  "absoluteDeadline": "2026-12-01T17:00:00Z",
  "revoked": false,
  "deviceLabel": "browser"
}
~~~

Thời hạn metadata nên được đặt theo **deadline hiệu lực**, ví dụ sớm hơn giữa idle deadline và absolute deadline. Không coi JSON field `absoluteDeadline` là TTL metadata tự động: SDK cần đặt expiry thực.

Session identifier phải được sinh từ bộ tạo số ngẫu nhiên an toàn, đủ dài và không được đưa nguyên vào logs. Với ứng dụng trình duyệt, thiết kế cookie bảo mật (Secure, HttpOnly, SameSite phù hợp), rotation/session fixation defense, CSRF và yêu cầu logout là những phần cần kết hợp với TTL.

**Quan trọng:** Spring Security hoặc Spring Session **không tự động sử dụng Couchbase làm session store** chỉ vì đã thêm `spring-boot-starter-data-couchbase`. Nếu dự án xây custom session repository, phải triển khai rõ cơ chế xác thực, lưu trữ và cập nhật, hoặc dùng một integration được hỗ trợ/kiểm chứng riêng.

## 9. Session idle TTL và absolute lifetime

Giả sử:

~~~text
issuedAt:           09:00
idle timeout:       20 phút
absolute lifetime:  8 giờ
last activity:      16:50
idle deadline:      17:10
absolute deadline:  17:00
effective deadline: 17:00
~~~

Một hàm thuần Java:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class SessionExpiryPolicy {

    private SessionExpiryPolicy() { }

    public static Instant nextDeadline(
            Instant issuedAt,
            Duration idleTtl,
            Duration absoluteLifetime,
            Clock clock) {

        Instant now = Instant.now(clock);
        Instant idleDeadline = now.plus(idleTtl);
        Instant hardDeadline = issuedAt.plus(absoluteLifetime);

        return idleDeadline.isBefore(hardDeadline)
                ? idleDeadline
                : hardDeadline;
    }
}
~~~

Hàm tính deadline, **không tự ghi Couchbase**. Phải kiểm tra session vẫn còn hợp lệ và chưa bị thu hồi tại lúc quyết định renew.

### 9.1. Không để idle renewal vượt hard deadline

Nếu service chỉ gọi:

~~~java
sessions.touch(
        sessionKey,
        Duration.ofMinutes(20)
);
~~~

sau mỗi request, phiên có thể được kéo dài vượt 8 giờ. Với hard deadline, phải chọn một mutation thích hợp để đặt **`Instant effectiveDeadline`** hoặc thời lượng không vượt hạn cứng; đồng thời xác thực deadline trong logic nghiệp vụ.

### 9.2. Không gia hạn ở mọi GET

GET phiên để hiển thị tên người dùng và một hành động đã xác thực có thể là hai use case khác nhau. Không âm thầm dùng `getAndTouch` trong mọi truy vấn:

~~~java
var session = sessions.getAndTouch(
        sessionKey,
        Duration.ofMinutes(20)
);
~~~

`getAndTouch` đặt expiry **trong lúc đọc, trước khi code Java có cơ hội kiểm tra field `revoked` hoặc hard deadline**. Vì vậy không phù hợp nếu việc gia hạn phụ thuộc các kiểm tra đó. Cần tách đọc, xác minh và cập nhật có kiểm soát; lưu ý hai thao tác độc lập vẫn có race nếu không dùng điều phối/CAS phù hợp.

## 10. Tạo session: insert một key không thể đoán

Mẫu minh họa:

~~~java
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.util.Base64;

import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.InsertOptions;

public final class SessionIssuer {

    private final Collection sessions;
    private final ExpirationProperties policy;
    private final Clock clock;
    private final SecureRandom random = new SecureRandom();

    public SessionIssuer(
            Collection sessions,
            ExpirationProperties policy,
            Clock clock) {
        this.sessions = sessions;
        this.policy = policy;
        this.clock = clock;
    }

    public String issue(String userId) {
        byte[] tokenBytes = new byte[32];
        random.nextBytes(tokenBytes);

        String token = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(tokenBytes);

        Instant now = Instant.now(clock);
        Instant absolute = now.plus(policy.sessionAbsolute());
        Instant idle = now.plus(policy.sessionIdle());
        Instant effective = idle.isBefore(absolute) ? idle : absolute;

        JsonObject content = JsonObject.create()
                .put("userId", userId)
                .put("issuedAt", now.toString())
                .put("lastActivityAt", now.toString())
                .put("absoluteDeadline", absolute.toString())
                .put("revoked", false);

        sessions.insert(
                "session::" + token,
                content,
                InsertOptions.insertOptions().expiry(effective)
        );

        return token;
    }
}
~~~

**Giới hạn của ví dụ:** token trả về là bearer credential và chỉ được gửi qua kênh/cookie bảo mật; không log hoặc lưu plaintext tùy tiện. Với hệ thống yêu cầu giảm tác động khi key store bị lộ, có thể dùng **hash/HMAC của token làm document key** thay vì nguyên token, với secret/rotation được quản lý riêng. Cần xử lý xác thực user trước khi phát hành, rủi ro token bị đánh cắp, logout và giới hạn session đồng thời.

`insert` tránh thay một document có cùng key nếu xảy ra trùng (rất hiếm với random đủ mạnh). Không tự chuyển sang upsert khi trùng mà chưa xác định semantics.

## 11. Gia hạn session: validate rồi ghi theo CAS

Luồng mong muốn:

~~~mermaid
flowchart TD
    A["Request mang session token"] --> B["KV GET theo session key"]
    B --> C{"Document tồn tại?"}
    C -- "Không" --> D["Từ chối: không tồn tại/hết hạn"]
    C -- "Có" --> E{"Revoked hoặc quá hard deadline?"}
    E -- "Có" --> F["Từ chối và không renew"]
    E -- "Không" --> G["Tính min(now+idle, hardDeadline)"]
    G --> H["REPLACE theo CAS + expiry(Instant)"]
    H --> I{"Mutation thành công?"}
    I -- "Có" --> J["Trả session hợp lệ theo policy"]
    I -- "CAS/not-found/timeout" --> K["Phân loại lỗi, đối soát và retry hữu hạn"]
~~~

Ví dụ phần cốt lõi:

~~~java
import java.time.Clock;
import java.time.Instant;
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.kv.ReplaceOptions;

GetResult current = sessions.get(sessionKey);
var value = current.contentAsObject();

Instant now = Instant.now(clock);
Instant hardDeadline =
        Instant.parse(value.getString("absoluteDeadline"));

if (Boolean.TRUE.equals(value.getBoolean("revoked"))
        || !now.isBefore(hardDeadline)) {
    throw new IllegalStateException("Session not active");
}

Instant idleDeadline = now.plus(policy.sessionIdle());
Instant next = idleDeadline.isBefore(hardDeadline)
        ? idleDeadline : hardDeadline;

value.put("lastActivityAt", now.toString());

sessions.replace(
        sessionKey,
        value,
        ReplaceOptions.replaceOptions()
                .cas(current.cas())
                .expiry(next)
);
~~~

Đây là đoạn mã dịch vụ minh họa với các biến `sessions`, `sessionKey`, `clock` và `policy` đã được khai báo ở lớp bao quanh. `replace` ghi lại **toàn bộ JSON**; phải giữ các trường cần thiết. CAS phát hiện thay đổi cạnh tranh nhưng không tự bảo đảm tính nguyên tử với hành động kinh doanh khác.

**Race:** phiên có thể hết hạn ngay giữa GET và REPLACE; lúc đó nhận not-found. Nếu có request revoke đồng thời, CAS có thể conflict. Không chữa bằng upsert tạo lại session cũ.

### 11.1. Đồng bộ lần gia hạn

Với lượng request cao, không nhất thiết gia hạn session trên mỗi request. Có thể chỉ renew khi còn dưới một ngưỡng (ví dụ năm phút), nhưng cần bảo đảm hard deadline, concurrency và bảo mật. Thao tác metadata write quá thường xuyên có thể gây CAS contention và tải Data service.

## 12. Logout và thu hồi session

TTL chỉ đợi thời gian trôi qua; logout cần **vô hiệu hóa trước hạn**.

Các cách phổ biến:

- **Remove session document** theo key: các KV reads tiếp theo không tìm thấy, khi mutation xóa đã được xử lý.
- **Mark revoked** theo CAS: giữ một bản ghi ngắn phục vụ audit/đối soát nếu policy cần, đồng thời không cho xác thực.
- **Revoke all sessions**: cần index/cơ chế quản lý danh sách session của user hoặc một version/fencing token trên user profile; không thể chỉ dựa vào việc chờ TTL.
- **Session rotation** sau đăng nhập/nâng quyền: phát token mới, vô hiệu token cũ; tránh session fixation.

Nếu dùng cache ở service/gateway, logout phải xét **invalidation**: xóa document Couchbase mà cache vẫn trả session cũ là lỗi kiến trúc. Với thao tác nhạy cảm, kiểm tra trạng thái phiên tại điểm quyết định, không chỉ dựa vào một lần cache hit trước đó.

### 12.1. Không dùng TTL như cơ chế logout duy nhất

Một phiên có TTL 20 phút và người dùng logout lúc phút thứ hai phải bị vô hiệu hóa ngay theo contract dịch vụ. `@Document(expiry = 1200)` hoặc touch không thay điều kiện này.

## 13. OTP là một challenge có deadline cố định

Thiết kế OTP cần tối thiểu:

- `challengeId` ngẫu nhiên, xác định đúng một lần cấp mã.
- `subject/userId` và `purpose` để tránh dùng mã của nghiệp vụ này cho nghiệp vụ khác.
- Hash/HMAC của mã; **không lưu hoặc log OTP thô**.
- `issuedAt` và `expiresAt` cố định.
- `attemptsRemaining` hoặc counter dùng CAS để chống cập nhật mất.
- `used` hoặc trạng thái tiêu thụ.
- Rate limit ở nhiều lớp: user/account, IP/device, challenge và kênh gửi.

Ví dụ document JSON:

~~~json
{
  "subject": "u-42",
  "purpose": "LOGIN_STEP_UP",
  "codeMac": "[base64-hmac-value]",
  "issuedAt": "2026-12-01T10:00:00Z",
  "expiresAt": "2026-12-01T10:05:00Z",
  "attemptsRemaining": 5,
  "used": false
}
~~~

**Vì sao HMAC/secret pepper?** OTP 6 chữ số chỉ có khoảng một triệu khả năng; một hash nhanh không có secret, nếu bị lộ, có thể bị dò offline dễ dàng. HMAC với secret phía server hoặc chiến lược bảo vệ credential chuyên dụng làm giảm rủi ro này. Vẫn phải giới hạn số lần thử và bảo vệ secret; HMAC không tự làm OTP thành token entropy cao.

## 14. Cấp OTP với absolute expiry

Ví dụ tạo document challenge:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.InsertOptions;

Instant issuedAt = Instant.now(clock);
Instant deadline = issuedAt.plus(policy.otp());

// codeMac được tạo bởi thành phần bảo mật và secret được quản lý an toàn.
JsonObject challenge = JsonObject.create()
        .put("subject", userId)
        .put("purpose", "LOGIN_STEP_UP")
        .put("codeMac", codeMac)
        .put("issuedAt", issuedAt.toString())
        .put("expiresAt", deadline.toString())
        .put("attemptsRemaining", 5)
        .put("used", false);

otpChallenges.insert(
        "otp::" + challengeId,
        challenge,
        InsertOptions.insertOptions().expiry(deadline)
);
~~~

Đoạn mã giả định `clock`, `policy`, `userId`, `codeMac`, `challengeId` và `otpChallenges` đã có trong service. Phát mã ngẫu nhiên bằng CSPRNG, gửi qua kênh đã định và **không tái sử dụng cùng mã/challenge** khi phát hành mới.

Lợi thế của `expiry(Instant)`: nếu mutation timeout và có một lần retry được phép, deadline giữ nguyên. Nếu dùng TTL tương đối `expiry(Duration.ofMinutes(5))` tính lại lúc retry, hạn có thể bị kéo dài.

### 14.1. Đơn vị và thời gian cấp phát

Một số API expiry dạng raw numeric có quy tắc legacy phân biệt thời lượng tương đối với Unix timestamp ở ngưỡng 30 ngày. Với SDK Java hiện đại, ưu tiên overload `Duration`/`Instant` và kiểm tra API tương ứng thay vì truyền số epoch mili giây không rõ nghĩa.

Không tin clock client thiết bị người dùng làm nguồn sự thật cho deadline. Dùng đồng hồ backend đồng bộ và một `Clock` có thể inject để test. Với OTP nhạy cảm, cần điều chỉnh skew/latency theo policy bảo mật được phê duyệt chứ không tự gia hạn âm thầm.

## 15. Xác minh OTP: kiểm tra deadline và tiêu thụ một lần

Một thuật toán hợp lý:

1. Load document bằng **KV GET theo challenge ID**, không dựa vào query theo user.
2. Kiểm tra purpose/subject, `used == false`, số lượt thử còn lại và `now < expiresAt`.
3. Tính MAC của mã người dùng gửi bằng secret phía server và so sánh theo cách hạn chế timing leak.
4. Với mã sai: giảm lượt thử bằng **CAS replace + preserve expiry**.
5. Với mã đúng: đánh dấu `used = true` bằng **CAS replace + preserve expiry** hoặc thao tác state transition tương đương.
6. Chỉ công nhận xác minh thành công nếu mutation tiêu thụ thành công; nếu CAS conflict hoặc document hết hạn, phải đọc lại/đánh giá theo policy.
7. Nếu thành công dẫn tới hiệu ứng ngoài (thanh toán, thay mật khẩu), kết hợp idempotency/transaction/outbox thích hợp; một CAS trên OTP **không** nguyên tử với API ngoài hệ thống.

~~~mermaid
flowchart TD
    A["Nhận challengeId + mã OTP"] --> B["GET challenge từ KV"]
    B --> C{"Tồn tại và chưa hết hạn?"}
    C -- "Không" --> X["Từ chối"]
    C -- "Có" --> D{"Đúng subject, purpose, chưa used, còn attempts?"}
    D -- "Không" --> X
    D -- "Có" --> E{"MAC của mã khớp?"}
    E -- "Không" --> F["CAS: giảm lượt thử, preserve expiry"]
    F --> G["Trả kết quả sai"]
    E -- "Có" --> H["CAS: used=true, preserve expiry"]
    H --> I{"CAS thành công?"}
    I -- "Có" --> J["Chấp nhận một lần / tiếp tục idempotent flow"]
    I -- "Không" --> K["Đối soát, không tự coi là thành công"]
~~~

### 15.1. Vì sao dùng CAS?

Hai request có thể cùng đọc `used=false`. Nếu cả hai lập tức trả thành công mà không có update điều kiện, OTP có thể được sử dụng hai lần.

CAS cho phép chỉ một request ghi thành công dựa trên **phiên bản document đã đọc**. Tuy nhiên, CAS mismatch không tự chứng minh request khác đã dùng đúng OTP; service phải đọc lại, kiểm tra trạng thái và từ chối hoặc xử lý theo protocol.

### 15.2. Pseudocode cập nhật trạng thái

~~~java
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.kv.ReplaceOptions;

// Gọi sau khi kiểm tra deadline, purpose và mã đúng.
GetResult current = otpChallenges.get(otpKey);
var state = current.contentAsObject();

// Trong thực tế, phải kiểm tra lại fields của phiên bản current.
if (Boolean.TRUE.equals(state.getBoolean("used"))) {
    throw new IllegalStateException("OTP already consumed");
}

state.put("used", true);
otpChallenges.replace(
        otpKey,
        state,
        ReplaceOptions.replaceOptions()
                .cas(current.cas())
                .preserveExpiry(true)
);
~~~

**Đoạn trên minh họa mechanics CAS/preserve, không phải implementation OTP hoàn chỉnh.** Luồng thật phải kiểm tra lại `expiresAt`, `attemptsRemaining`, user/purpose và MAC từ chính phiên bản `current` trước khi replace; nếu không, có thể chấp nhận mã đã đổi hoặc đã hết hạn. Bảo đảm an toàn dựa trên **kiểm tra lại + CAS + chỉ trả success sau replace**, không chỉ mỗi cờ `used`.

Nếu muốn xóa ngay challenge khi dùng thành công, phải xác minh API remove/CAS và hậu quả đối với idempotency; một bản ghi `used=true` sống tới expiry có thể giúp nhận diện và từ chối replay rõ hơn.

## 16. Mã sai không được gia hạn OTP

Ví dụ cập nhật bộ đếm bằng CAS:

~~~java
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.kv.ReplaceOptions;

GetResult current = otpChallenges.get(otpKey);
var challenge = current.contentAsObject();

Integer left = challenge.getInt("attemptsRemaining");
int remaining = left == null ? 0 : Math.max(0, left - 1);

challenge.put("attemptsRemaining", remaining);

otpChallenges.replace(
        otpKey,
        challenge,
        ReplaceOptions.replaceOptions()
                .cas(current.cas())
                .preserveExpiry(true)
);
~~~

Đoạn code chỉ minh họa mutation: trước khi cập nhật, service thật cần kiểm tra deadline, trạng thái used, user/purpose, mức rate limit và xử lý CAS/not-found rõ ràng. Nếu TTL reset 5 phút mỗi lần nhập sai, attacker có thể giữ mã lâu hơn deadline bằng cách liên tục thử; **preserve expiry** loại bỏ hình thức gia hạn đó.

**Đừng dùng `getAndTouch(id, Duration.ofMinutes(5))`** để đọc OTP. Đây là lệnh vừa đọc vừa gia hạn, trái với chính sách “5 phút từ lúc phát hành”.

## 17. Giới hạn số lần thử và rate limit không phải TTL

TTL ngắn không tự chặn online brute force. Một challenge OTP 6 chữ số có số khả năng hữu hạn; nếu được thử không giới hạn, rủi ro vẫn cao dù chỉ sống 5 phút.

Cần ít nhất:

- Counter cho challenge, cập nhật atomically bằng CAS hoặc cơ chế phù hợp.
- Rate limit theo account/địa chỉ mạng/thiết bị và kênh gửi mã.
- Cooldown phát mã mới.
- Chính sách khóa tạm khi vượt ngưỡng, không phát mã trùng không kiểm soát.
- Quan sát lỗi và phát hiện tấn công nhưng không log mã/thông tin nhạy cảm.
- Kiểm soát chi phí các request gửi SMS/email để tránh lạm dụng.

Nếu lưu counter rate limit ở một document Couchbase ngắn hạn, expiry metadata của counter cũng cần được thiết kế đúng. Dùng `touch` liên tục có thể khiến cửa sổ rate limit kéo dài khác với mô hình fixed-window; dùng CAS/subdocument counter và deadline theo policy.

## 18. Idempotency và retry khi phát mã/tiêu thụ mã

Các thao tác Couchbase có thể timeout sau khi server đã áp mutation. Với `AmbiguousTimeoutException`, client không chắc trạng thái server.

Không nên:

~~~text
Timeout phát OTP
→ tạo challenge mới và mã mới vô điều kiện
→ gửi hai mã hoặc đẩy deadline xa hơn
~~~

Thay vào đó, cần:

1. Sinh **operation/challenge ID ổn định** cho một yêu cầu phát hành.
2. Tính `issuedAt` và `expiresAt` **một lần**.
3. Nếu retry được phép, dùng lại deadline và identity hoặc đọc/đối soát kết quả trước.
4. Đảm bảo gửi thông báo ra ngoài được điều phối để tránh gửi hai lần theo ý định (outbox/idempotency).
5. Khi một OTP đã consumed, lần xác minh lặp phải bị từ chối hoặc trả kết quả idempotent chỉ trong phạm vi đã thiết kế, tuyệt đối không tạo quyền mới.

Việc idempotency của Couchbase KV operation và idempotency **nghiệp vụ** là hai khái niệm khác nhau. Một `upsert` lặp có thể tạo nội dung giống nhau nhưng lại reset expiry, trong khi side effect bên ngoài vẫn bị lặp.

## 19. Token reset mật khẩu và mã xác minh email

Token reset mật khẩu thường cần:

| Thuộc tính | Thiết kế |
| --- | --- |
| Định danh | Opaque, entropy cao, không suy từ user ID |
| Expiry | Fixed `Instant` từ lúc cấp |
| Lưu trên Couchbase | Hash/HMAC token; tránh lưu bearer secret thô |
| State | One-time consumed, revoked hoặc active |
| Verification | Deadline + purpose + subject + CAS/state |
| Side effect | Thay mật khẩu và tiêu thụ token phải được điều phối nhất quán |
| Logging | Không log token/raw secret |

Với token entropy cao, hashing có tính chất và threat model khác OTP entropy thấp, nhưng nguyên tắc bảo vệ secret và chống replay vẫn giống nhau.

**Không dùng TTL làm phép phân quyền duy nhất.** Token còn đọc được không đồng nghĩa hợp lệ: nó có thể đã dùng, bị revoke, sai purpose hoặc tài khoản đã bị khóa.

## 20. Dữ liệu tạm: phân loại theo mục đích trước khi đặt TTL

Không phải dữ liệu tạm nào cũng có thể đơn giản “TTL 10 phút”.

### 20.1. Cache kết quả tính toán

Ví dụ document kết quả gợi ý sản phẩm:

~~~json
{
  "queryKey": "recommendation::segment-A",
  "generatedAt": "2026-12-01T10:00:00Z",
  "items": ["SKU-1", "SKU-2"]
}
~~~

Có thể dùng `expiry(Duration.ofMinutes(30))` nếu chấp nhận cache miss sau TTL và có thể tính lại. Không cần scheduler để “hoàn tất” việc hết hạn cache.

### 20.2. Export/report tạm

Một kết quả xuất CSV có thể sống 24 giờ sau khi **tạo xong**; nếu document job được tạo lúc bắt đầu và chạy 3 giờ mới hoàn tất, TTL tính từ lúc bắt đầu có thể khiến metadata biến mất trước khi người dùng được tải.

Chọn lifecycle:

~~~text
CREATED → RUNNING → SUCCEEDED → DOWNLOADABLE → EXPIRED
                    ↘ FAILED
~~~

Có thể đặt TTL ngắn cho kết quả tạm **tại thời điểm hoàn tất**. Nhưng metadata job cần tồn tại đủ lâu để quản lý retry, hiển thị lỗi, theo dõi và cleanup object storage. Nếu cần callback “expired”, dùng job riêng hoặc event state, không phụ thuộc TTL.

### 20.3. Reservation giữ chỗ

Reservation có deadline, nhưng nếu TTL xóa document ngay, hệ thống có thể mất dữ liệu để trả hàng về kho. Giữ trạng thái bền vững hoặc event timeout ở cơ chế riêng; TTL chỉ dành cho record tạm sau khi hậu quả nghiệp vụ đã được xử lý.

### 20.4. Khóa idempotency

Ví dụ API thanh toán có operation ID. Nếu idempotency record hết hạn quá sớm nhưng client còn quyền retry, cùng operation có thể được xử lý lại, gây double charge hoặc tạo đơn trùng.

Vì vậy TTL của khóa idempotency phải tối thiểu đáp ứng **cửa sổ retry và yêu cầu chống trùng đã cam kết**, không đặt bằng “TTL cache thông thường” chỉ để tiết kiệm storage.

## 21. Dùng SDK ghi dữ liệu tạm với TTL

Ví dụ kết quả tạm sau khi tính xong:

~~~java
import java.time.Duration;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

// temporaryResults trỏ đúng scope/collection processing.
temporaryResults.upsert(
        "result::job-123",
        JsonObject.create()
                .put("jobId", "job-123")
                .put("status", "SUCCEEDED")
                .put("generatedAt", "2026-12-01T10:00:00Z"),
        UpsertOptions.upsertOptions()
                .expiry(Duration.ofDays(1))
);
~~~

TTL được áp **khi mutation hoàn thành**, nếu maxTTL server không giới hạn ngắn hơn. Nếu update lại kết quả sau một giờ với Duration 1 ngày, deadline có thể được làm mới; đó có thể đúng hoặc sai tùy retention contract.

Một số đường API/legacy xử lý raw numeric expiry có ranh giới 30 ngày; ưu tiên `Duration`/`Instant` theo SDK version thay vì một số giây thiếu ý nghĩa.

## 22. `@Document(expiry)` trong Spring Data Couchbase

Một entity dữ liệu tạm có TTL tĩnh:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document(expiry = 3600) // Thông thường: 3600 giây.
@Scope("processing")
@Collection("temporary_results")
public class TemporaryResultDocument {

    @Id
    private String id;
    private String jobId;

    protected TemporaryResultDocument() { }

    public TemporaryResultDocument(String id, String jobId) {
        this.id = id;
        this.jobId = jobId;
    }

    public String getId() { return id; }
    public String getJobId() { return jobId; }
}
~~~

Repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface TemporaryResultRepository
        extends CouchbaseRepository<TemporaryResultDocument, String> {
}
~~~

`@Document(expiry = 3600)` mô tả TTL tĩnh khi đi qua mapper được hỗ trợ, **không tạo collection và không set maxTTL**. Một số release có expiry expression hoặc annotation expiry động, nhưng cú pháp, kiểu giá trị và precedence cần kiểm tra đúng version.

Nếu một entity cần deadline cố định tùy từng instance hoặc update phải preserve chính xác, không mặc định repository `save` đáp ứng chỉ nhờ annotation tĩnh. Kiểm tra behavior insert/update bằng metadata expiry trên server.

### 22.1. Spring Data và SDK là hai đường khác nhau

| Đường ghi | Điều phải kiểm soát |
| --- | --- |
| `repository.save(entity)` | Mapping expiry, update behavior, CAS/`@Version` |
| `CouchbaseTemplate` entity operation | Mapper và operation options của version |
| SDK `insert/upsert` | `expiry(Duration/Instant)` rõ ràng, schema JSON |
| SDK `replace` | `preserveExpiry` hoặc expiry mới, CAS |
| SDK `touch/getAndTouch` | Renewal có chủ đích, không thay JSON |
| SQL++ `UPDATE/UPSERT` | Semantics server statement; không tự đọc `@Document` |
| Reactive repository/template | Subscription, mapping và retry |

Khi refactor từ repository sang SDK vì tối ưu hiệu năng, phải xem lại TTL, schema serialization, CAS và converter; không coi đó là thay đổi thuần túy về cú pháp.

## 23. Preserve expiry khi cập nhật mà không gia hạn

Một lần sửa trạng thái tạm hoặc ghi audit metadata không nhất thiết được phép kéo dài hạn.

Ví dụ SDK `replace`:

~~~java
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.kv.ReplaceOptions;

GetResult current = temporaryResults.get(resultKey);
var updated = current.contentAsObject();
updated.put("downloadCount", 1);

temporaryResults.replace(
        resultKey,
        updated,
        ReplaceOptions.replaceOptions()
                .cas(current.cas())
                .preserveExpiry(true)
);
~~~

`preserveExpiry(true)` yêu cầu giữ expiry metadata đã có trong các mutation được hỗ trợ. CAS giúp tránh ghi đè content cạnh tranh; chúng giải quyết hai vấn đề khác nhau. `replace` ghi toàn bộ JSON sau khi đã cập nhật object, không phải partial update.

Nếu document hết hạn giữa GET và REPLACE, mutation có thể trả not-found; không dùng upsert để hồi sinh dữ liệu đã quá hạn, trừ khi đó là một nghiệp vụ tạo mới độc lập được cho phép.

## 24. MaxTTL của server và chính sách không thể vượt qua

Giả sử:

~~~text
commerce.auth.sessions          maxTTL 15 phút
commerce.auth.otp_challenges    maxTTL 5 phút
commerce.checkout.carts         maxTTL 10 phút
commerce.processing.results     maxTTL 1 ngày
~~~

Nếu session cần idle 20 phút và server policy giới hạn 15 phút, document có thể hết hạn **sớm hơn policy ứng dụng**. Nếu cart muốn 30 phút nhưng maxTTL 10 phút, giỏ có thể biến mất trước mong đợi.

| Nhu cầu | TTL ứng dụng | Server maxTTL | Vấn đề |
| --- | --- | --- | --- |
| Session idle 20m | 20m | 15m | Phiên có thể hết sớm |
| OTP cố định 5m | 5m | 5m | Thường tương thích nếu mutation đúng |
| Cart sau sửa 30m | 30m | 10m | Chính sách mâu thuẫn |
| Reset token 15m | 15m | 24h | TTL ngắn hợp lệ, vẫn cần hard deadline |
| Export tạm 1d | 1d | 2h | File/job metadata có thể mất sớm |

Bảng minh họa hướng chẩn đoán; quy tắc áp dụng, kế thừa bucket/collection và preserve expiry phải đối chiếu theo server version thực tế.

**Không xem maxTTL là một session hard lifetime tính từ issuedAt.** Một TTL tương đối được áp lại có thể dịch deadline; session cần lưu **absoluteDeadline** riêng.

## 25. Dữ liệu tạm và index SQL++

Các truy vấn phổ biến:

- Tìm các export job của user theo trạng thái.
- Liệt kê reservation sắp hết hạn để scheduler xử lý.
- Tìm session còn hiệu lực trong một nghiệp vụ quản trị.
- Phân tích số lượt OTP bị khóa (thường nên tổng hợp vào hệ thống telemetry thay vì query raw secret).

SQL++ phù hợp với truy vấn theo predicate nhưng cần index/scan consistency hợp lý. Ví dụ:

~~~sql
SELECT META(j).id AS documentId, j.status, j.generatedAt
FROM `commerce`.`processing`.`export_jobs` AS j
WHERE j.status = "SUCCEEDED";
~~~

Một document không xuất hiện qua SQL++ có thể do query plan/index, keyspace hoặc expiry. Với một challenge/session đã biết key, KV GET là phép kiểm tra trực tiếp hơn.

**Không xem SQL++ index như một scheduler “tìm đúng tất cả record vào mili giây hết hạn”.** Index được duy trì theo cơ chế riêng; nếu cần xử lý timeout reservation, dùng scheduler có idempotency và kiểm tra deadline/status trước khi thay đổi.

## 26. Thời điểm read và deadline nghiệp vụ

Ví dụ:

~~~text
10:04:59.900  GET OTP thành công
10:05:00.000  OTP đến hạn
10:05:00.200  Service chuẩn bị chấp nhận OTP
~~~

Nếu chính sách yêu cầu “chưa hết hạn tại thời điểm chấp nhận”, một GET thành công trước hạn **chưa đủ**. Phải kiểm tra deadline trong cùng luồng quyết định và xử lý concurrency. Đây là tình huống *time-of-check/time-of-use*.

Không thể đảm bảo một thao tác Couchbase tự tạo snapshot nguyên tử với mọi xử lý Java hoặc external API. Nếu cần xác minh trước side effect có giá trị cao, dùng CAS/transaction/idempotency và định nghĩa điểm quyết định rõ ràng.

**Chú ý:** `DocumentNotFoundException` chỉ nói key không còn tồn tại hợp lệ ở thời điểm thao tác; không khẳng định nó đã hết hạn thay vì bị xóa, chưa từng tồn tại hoặc request đang trỏ sai collection. Timeout cũng không đồng nghĩa expired.

## 27. Reactive API: subscription và retries

SDK reactive dùng expiry tương tự blocking:

~~~java
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.InsertOptions;
import java.time.Instant;
import reactor.core.publisher.Mono;

Instant fixedDeadline = issuedAt.plusSeconds(300);

Mono<?> write = otpChallenges.reactive().insert(
        challengeKey,
        JsonObject.create()
                .put("subject", userId)
                .put("purpose", "LOGIN_STEP_UP"),
        InsertOptions.insertOptions().expiry(fixedDeadline)
);
~~~

Đây là ví dụ về **fixed deadline**, chưa đủ trường thông tin cho một OTP production.

- Chỉ tạo `Mono` chưa chắc mutation đã chạy; cần subscription.
- `retryWhen` hoặc resubscribe có thể lặp mutation; `insert` trên key đã tồn tại có thể báo trùng, cần đối soát thay vì tạo key mới.
- Dùng `Instant` đã tính trước publisher giúp không gia hạn deadline khi retry.
- `Mono.timeout(Duration.ofSeconds(2))` là pipeline timeout, không phải document TTL.
- Cancellation không đảm bảo mutation đã gửi tới server được rollback.
- Không nuốt mọi lỗi thành `Mono.empty()`: outage, auth error và not-found khác nhau.

Với xác minh OTP, mọi nhánh reactive phải giữ nguyên điều kiện kiểm tra, CAS và idempotency như đường blocking.

## 28. Cache ứng dụng không được sống lâu hơn quyền sử dụng

Một service có thể cache session/OTP result trong Caffeine/Redis hoặc Reactor `Mono.cache(...)`. TTL của cache là một **đồng hồ khác** với expiry metadata Couchbase.

Ví dụ Couchbase session hết hạn sau 20 phút nhưng cache application giữ 1 giờ. Một cache hit có thể tiếp tục trả dữ liệu đã hết hạn trên server nếu ứng dụng không kiểm tra deadline.

Giải pháp:

1. Không cache raw OTP/secret.
2. Với session, cache TTL không vượt deadline hiệu lực, nhưng còn cần invalidation khi revoke/logout.
3. Ở điểm có yêu cầu bảo mật cao, kiểm tra trạng thái mới thay vì tin một cached value cũ.
4. Không coi `REQUEST_PLUS` của SQL++ là cách invalidate cache.
5. Thiết kế nhất quán khi nhiều service cùng xác thực một session.

Cũng không dùng `getAndTouch` chỉ để “đọc lại cache” vì lệnh này gia hạn expiry và có thể thay CAS.

## 29. Giao dịch, CAS và side effect bên ngoài

Một OTP được dùng để phê duyệt nghiệp vụ có giá trị cao:

~~~text
GET OTP → xác minh → CAS used=true → gọi thanh toán
~~~

CAS giúp chỉ một lần cập nhật trạng thái OTP thành công, nhưng **không tự thực hiện giao dịch phân tán với hệ thống thanh toán ngoài Couchbase**. Nếu payment call thất bại sau khi OTP đã consumed, cần quy tắc retry/reconciliation/idempotency để không trừ tiền hai lần hoặc dùng mã nhiều lần.

Một số lựa chọn kiến trúc:

- State machine bền vững cho operation được phê duyệt.
- Outbox hoặc job có idempotency key.
- Transaction Couchbase nếu các document liên quan ở phạm vi khả năng hỗ trợ và đáp ứng giới hạn hệ thống.
- Đối soát kết quả external side effect sau ambiguous timeout.

**Transaction timeout khác TTL**. Một document bị expiry không tự commit/rollback thanh toán; một transaction commit không bảo đảm OTP còn trong hạn nếu code không kiểm tra deadline khi ra quyết định.

## 30. Tối ưu hiệu năng mà vẫn đúng chính sách

Các thao tác auth thường nhạy latency nhưng không nên đánh đổi tính đúng đắn:

| Thao tác | Đường thường phù hợp | Lưu ý |
| --- | --- | --- |
| Lookup session theo token | SDK KV GET hoặc repository theo ID | Tránh query SQL++ không cần thiết |
| Renew session | Replace theo CAS + expiry effective deadline | Không renew session revoked/expired |
| Verify OTP theo challenge ID | KV GET + CAS mutation | Một lần dùng, giới hạn attempts, fixed deadline |
| Liệt kê export jobs theo status | SQL++ có index | Chấp nhận semantics index, không làm clock TTL |
| Cart read-only | KV GET | Không getAndTouch nếu không được gia hạn |
| Cart sau sửa | Replace/upsert có expiry rõ | CAS nếu có concurrency |
| Cleanup dữ liệu không cần workflow | TTL | Đừng tạo job xóa vô ích nếu policy chỉ yêu cầu expiry |
| Deadline có side effect | Scheduler/job + state transition | TTL chỉ hỗ trợ cleanup |

Khi throughput cao, gia hạn session mỗi request làm tăng metadata mutation, ảnh hưởng CAS contention và chi phí. Có thể **coalesce renewal** khi remaining idle TTL xuống một ngưỡng, nhưng phải giữ hard deadline và không thay policy bảo mật.

## 31. Đọc expiry metadata để kiểm chứng

Java SDK 3.x có API yêu cầu metadata expiry:

~~~java
import com.couchbase.client.java.kv.GetOptions;

var result = sessions.get(
        sessionKey,
        GetOptions.getOptions().withExpiry(true)
);

result.expiryTime().ifPresent(deadline ->
        System.out.println("Effective expiry: " + deadline)
);
~~~

`withExpiry(true)` yêu cầu thông tin expiry ở phiên bản hỗ trợ; `expiryTime()` thường trả giá trị tùy chọn. Không mặc định một giá trị trống luôn có cùng nghĩa ở mọi phiên bản. Khi đã expired, GET thông thường có thể không trả document để bạn đọc metadata; vì vậy test phải ghi nhận expiry **ngay sau insert/update**.

So sánh:

1. Mốc `issuedAt` và deadline nghiệp vụ.
2. Expiry metadata quan sát từ server.
3. Server `maxTTL` hiệu lực ở đúng collection.
4. Thời điểm mutation được áp, rounding/time resolution.
5. Các mutation `touch`, `replace` hoặc save khác có thể thay đổi expiry.

Không assert chính xác tới từng nano giây; dùng dung sai hợp lý.

## 32. Kiểm thử unit: chính sách session

Dùng `Clock.fixed` để chắc chắn kết quả không phụ thuộc thời gian test thật:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class SessionExpiryPolicyTest {

    @Test
    void idleRenewalNeverExceedsAbsoluteDeadline() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-12-01T16:50:00Z"),
                ZoneOffset.UTC
        );

        Instant deadline = SessionExpiryPolicy.nextDeadline(
                Instant.parse("2026-12-01T09:00:00Z"),
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

Bổ sung:

- `issuedAt` sau hiện tại: từ chối hoặc xử lý clock skew theo policy.
- `now` sau hard deadline: không gia hạn.
- Idle TTL bằng 0/âm: validation fail.
- TTL không được vượt cấu hình server nếu cần đủ thời gian cho user flow.
- Session `revoked=true`: không được renew.

Test này chỉ chứng minh phép tính; cần integration test để chứng minh metadata Couchbase.

## 33. Kiểm thử integration: session và OTP

Chạy với bucket/scope/collection **dành riêng cho test**, quyền tối thiểu và `maxTTL` được biết rõ. Không thay maxTTL production để thử.

| Kịch bản | Điều cần khẳng định |
| --- | --- |
| Tạo session | Expiry metadata tương ứng min(idle, absolute) |
| Renew session còn hợp lệ | Deadline mới không vượt hard limit |
| Renew session bị revoke | Từ chối, không làm mới TTL |
| Logout/remove session | KV lookup sau mutation không còn hiệu lực |
| Tạo OTP | Expiry metadata trùng deadline cố định trong dung sai |
| Nhập sai OTP | Attempts giảm, expiry không được gia hạn |
| Hai request dùng OTP đồng thời | Chỉ một CAS state transition tiêu thụ thành công |
| OTP hết hạn giữa GET/REPLACE | Không tự upsert tạo lại |
| Retry phát OTP | Cùng operation identity và fixed deadline |
| maxTTL server thấp hơn policy | Test phát hiện mâu thuẫn trước deployment |
| Cache/session invalidation | Sau logout, không còn xác thực qua cache cũ |

### 33.1. Tạo test document có TTL ngắn

~~~java
import java.time.Duration;
import java.util.UUID;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

String key = "ttl-it::" + UUID.randomUUID();

testCollection.upsert(
        key,
        JsonObject.create().put("kind", "test"),
        UpsertOptions.upsertOptions()
                .expiry(Duration.ofSeconds(5))
);
~~~

Ngay sau ghi, GET nội dung và expiry metadata. Sau deadline, poll có giới hạn thay vì cố sleep đúng 5.000 mili giây rồi assert một lần.

### 33.2. Polling xác minh dữ liệu hết hạn

Với Awaitility (dependency test của dự án):

~~~java
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;
import java.time.Duration;

await()
        .atMost(Duration.ofSeconds(15))
        .pollInterval(Duration.ofMillis(200))
        .untilAsserted(() -> {
            assertThat(testCollection.exists(key).exists()).isFalse();
        });
~~~

Đây là phác thảo test: cần fixture kết nối Couchbase, setup/cleanup và độ dung sai cho môi trường. Phải chứng minh document đã được tạo **trước khi** chờ hết hạn, nếu không test có thể “thành công” vì key chưa từng tồn tại.

## 34. Kiểm thử concurrency và kết quả ghi mơ hồ

Các test dễ bị bỏ qua:

1. Hai request xác minh OTP cùng mã đúng từ cùng CAS → không được cùng được công nhận thành công.
2. Tăng bộ đếm OTP sai và xác minh đúng chạy đồng thời → cập nhật không bị mất, deadline không bị reset.
3. Session revoke xảy ra giữa GET và REPLACE renew → CAS/not-found được xử lý, không hồi sinh.
4. TTL chạm hạn giữa GET và mutation → trả expired/not-found thay vì upsert.
5. Timeout mutation tạo OTP → client đối soát, không phát hành lại mã mới vô điều kiện.
6. Reactive retry/resubscribe → không tạo deadline mới.
7. Update qua repository rồi SDK → expiry không bị thay đổi trái policy.
8. Cache cũ sau revoke → hệ thống không chấp nhận hành động nhạy cảm chỉ dựa vào cache.

Trong test cạnh tranh, không dựa trên `Thread.sleep` để tạo race theo may rủi. Có thể dùng barrier, executor hoặc test harness điều phối request rồi kiểm tra kết quả CAS/state; quan sát expiry metadata riêng.

## 35. Vận hành: log và metrics đúng tầng

| Tín hiệu | Mục đích |
| --- | --- |
| Tỷ lệ session-not-found/expired | Phát hiện chính sách hết hạn bất thường |
| Số lượt revoke/logout | Đo hành vi và xác minh invalidation |
| Rate limit/OTP attempts | Phát hiện brute-force và lỗi kênh gửi |
| CAS conflict | Quan sát cập nhật cạnh tranh trên session/OTP |
| KV timeout/ambiguous mutation | Phân biệt outage với expired |
| Lưu lượng TOUCH/GET-AND-TOUCH | Tránh renew quá thường xuyên |
| Expiry metadata mẫu trong test/staging | Xác minh `maxTTL` và mapping |
| Query/index latency | Đo danh sách dữ liệu tạm theo SQL++ |
| Số export jobs đang RUNNING quá hạn | Phát hiện workflow cần recovery, không chỉ cleanup |
| Idempotency duplicate prevented | Bảo đảm retry không tạo side effect lặp |

Không log raw session token, OTP, reset token, secret HMAC, mật khẩu hoặc toàn bộ document auth. Có thể log correlation ID đã ẩn danh, collection, loại thao tác và trạng thái lỗi theo chính sách bảo mật.

## 36. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân khả dĩ | Cách khắc phục |
| --- | --- | --- |
| Session kéo dài vượt 8 giờ | Renew idle TTL không xét hard deadline | Tính `min(idleDeadline, hardDeadline)` |
| Session bị revoke vẫn được chấp nhận | Cache cũ hoặc getAndTouch trước khi validate | Kiểm tra revoked và invalidation |
| OTP sống lâu hơn 5 phút | Update/retry áp lại relative TTL | Fixed `Instant` hoặc preserve expiry |
| OTP được dùng hai lần | Check-then-use không có CAS | State transition có CAS, success sau mutation |
| Nhập sai không giảm counter đáng tin cậy | Concurrent updates lost | CAS/retry giới hạn |
| OTP bị brute force | Không giới hạn attempts/rate | Rate limiting và challenge lifecycle |
| Mã OTP lộ qua logs | Log/raw storage thiếu bảo vệ | HMAC/pepper, không log secret |
| Cart mất sớm | Server maxTTL ngắn hơn app TTL | Kiểm tra policy collection |
| Export job biến mất khi đang chạy | TTL bắt đầu quá sớm | Tách job state và result TTL |
| Idempotency mất trước cửa sổ retry | TTL quá ngắn | Chọn retention theo contract |
| Reservation hết hạn nhưng inventory chưa giải phóng | Dùng TTL như scheduler | Job/event transition riêng |
| SDK path làm sai expiry entity | SDK không đọc `@Document` | Truyền expiry/preserve rõ ràng |
| SQL++ không thấy nhưng KV có | Index/consistency/keyspace | Kiểm tra KV theo key và query plan |
| Timeout bị báo thành expired | Phân loại exception sai | Tách not-found, timeout và CAS |
| Reactive write không chạy | Publisher chưa subscribe | Kiểm tra signal/subscription |
| Expired nhưng disk chưa giảm | Expiry logic khác purge vật lý | Dùng metrics server đúng tầng |

## 37. Bài tập tình huống tổng hợp

Một hệ thống checkout có:

~~~text
commerce.auth.sessions
commerce.auth.otp_challenges
commerce.checkout.carts
commerce.checkout.reservations
commerce.processing.export_jobs
commerce.processing.temporary_results
~~~

Yêu cầu:

- Session: idle 20 phút; tối đa 8 giờ; có logout và revoke-all.
- OTP login step-up: 5 phút từ phát hành; tối đa năm lượt thử; chỉ thành công một lần.
- Cart: 30 phút từ lần sửa cuối, không renew khi chỉ xem.
- Reservation: giữ hàng đến deadline 10 phút; phải giải phóng giữ chỗ nếu timeout.
- Export result: có thể tải trong 24 giờ sau khi job thành công.
- Idempotency key: phải bao phủ ít nhất thời gian gateway/client được phép retry.
- Collection sessions đang có `maxTTL` 10 phút; collection exports có `maxTTL` 2 giờ.
- Ứng dụng có repository, SDK trực tiếp và reactive endpoint.

**Câu hỏi thực hành:**

1. Vì sao cấu hình `maxTTL` của session và export mâu thuẫn yêu cầu?
2. Viết công thức tính deadline session khi thời gian phát hành 09:00 và hoạt động cuối lúc 16:50.
3. Vì sao không dùng `getAndTouch` để đọc OTP hoặc session revoked?
4. Thiết kế một lệnh cấp OTP với `expiry(Instant)` và challenge ID ổn định.
5. Khi tăng lượt thử sai, phải preserve expiry hay refresh TTL? Vì sao?
6. Hai yêu cầu dùng cùng OTP đồng thời cần CAS/state transition thế nào?
7. Vì sao một OTP được lưu dưới dạng hash đơn giản không secret vẫn có thể bị dò offline?
8. Tại sao không cho export job RUNNING và result DOWNLOADABLE cùng TTL từ lúc tạo job?
9. Vì sao TTL của idempotency key phải căn cứ vào cửa sổ retry?
10. Nếu reservation document hết hạn trước khi scheduler chạy, lấy dữ liệu nào để giải phóng tồn kho?
11. Xử lý `AmbiguousTimeoutException` khi phát mã để tránh tạo hai challenge như thế nào?
12. Viết ma trận integration test so sánh repository, SDK và reactive expiry behavior.

**Định hướng lời giải:** session cần idle + absolute deadline và thu hồi; OTP cần fixed deadline, giới hạn lượt thử, MAC được bảo vệ và CAS tiêu thụ một lần; dữ liệu tạm phải phân loại theo workflow; TTL là cleanup, còn side effect phải do state machine/scheduler idempotent xử lý. Server maxTTL và đường ghi thực tế quyết định expiry metadata.

## 38. Checklist trước production

- [ ] Đã phân loại session, OTP, token, cart, reservation, job và idempotency theo retention thực.
- [ ] Session ID/token có entropy cao và được truyền/lưu an toàn.
- [ ] Session có idle TTL, absolute deadline và cơ chế logout/revoke.
- [ ] Không renew session revoked hoặc đã qua hard deadline.
- [ ] Không tự dùng GET-AND-TOUCH cho mọi thao tác xác thực.
- [ ] OTP có challenge ID riêng, subject/purpose, deadline cố định và one-time state.
- [ ] Không lưu/log OTP thô; cơ chế MAC/hash và secret phù hợp threat model.
- [ ] Rate limit, giới hạn lượt thử, chống phát mã trùng được thiết kế riêng.
- [ ] OTP update dùng preserve expiry và CAS khi cần.
- [ ] Retry không gia hạn deadline hoặc tạo tác động ngoài nhiều lần.
- [ ] Có idempotency và xử lý ambiguous timeout.
- [ ] Không dùng TTL để thực thi scheduler/hủy reservation tức thời.
- [ ] Export job state và temporary result có policy TTL khác nếu cần.
- [ ] Idempotency retention đủ dài so với cửa sổ retry.
- [ ] `maxTTL` bucket/collection tương thích với yêu cầu nghiệp vụ.
- [ ] Entity mapping, repository, template, SDK và SQL++ tuân cùng chính sách.
- [ ] CAS/`@Version` kiểm soát concurrency, không bị hiểu nhầm là TTL.
- [ ] Cache session không bỏ qua revoke/hard deadline.
- [ ] Reactive publisher được subscribe và retry đúng ngữ nghĩa.
- [ ] Có unit test `Clock.fixed` và integration test metadata expiry.
- [ ] Đã test document expired giữa GET/REPLACE và concurrent one-time use.
- [ ] Monitoring phân biệt not-found, timeout, CAS mismatch và query lag.
- [ ] Không coi TTL là cam kết xóa vật lý tức thì khỏi backup/replica.

## 39. Tổng kết

Thiết kế session, mã xác thực và dữ liệu tạm với Couchbase đòi hỏi **chính sách vòng đời khác nhau**. Session cần sliding idle TTL nhưng phải chịu hard deadline và revocation; OTP phải có thời hạn cố định, bảo vệ bí mật, giới hạn lượt thử và trạng thái tiêu thụ một lần được cập nhật có điều kiện; dữ liệu tạm cần TTL gắn với đúng **giai đoạn công việc**, không thay thế scheduler và idempotency.

Spring Data Couchbase cung cấp document mapping, repository và `CouchbaseTemplate`; Couchbase Java SDK cho phép chỉ định `Duration`, `Instant`, `preserveExpiry` và CAS phù hợp. Các đường ghi này không tự có semantics đồng nhất nếu ứng dụng không thống nhất policy, và tất cả còn chịu `maxTTL` server.

Khi giữ rõ nguồn sự thật của deadline, kiểm tra trạng thái ở điểm quyết định, đọc expiry metadata sau mutation và kiểm thử concurrency/retry, hệ thống có thể sử dụng TTL để dọn dữ liệu hiệu quả mà vẫn bảo vệ tính đúng đắn và an toàn của phiên đăng nhập, mã xác thực và dữ liệu tạm.

