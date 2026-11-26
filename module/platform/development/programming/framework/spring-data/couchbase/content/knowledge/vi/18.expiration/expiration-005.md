# Giữ lại, thay thế hoặc làm mới thời hạn khi ghi

## 1. Bài toán: cập nhật nội dung nhưng không được đổi hạn sai ý định

Trong **Spring Data Couchbase**, document có metadata thời điểm hết hạn (expiry) độc lập với JSON content. Khi ứng dụng sửa một field, tăng số lần thử OTP, thay giỏ hàng hay cập nhật session, thao tác ghi có thể đồng thời **giữ nguyên, đặt lại hoặc gia hạn expiry**. Đây là lựa chọn về tính đúng đắn nghiệp vụ, không chỉ là một tham số của SDK.

Ví dụ, mã OTP phát hành lúc 10:00 và hết hạn 10:05. Người dùng nhập sai lúc 10:03. Nếu service ghi bộ đếm lỗi bằng một mutation áp TTL mới 5 phút, mã có thể tồn tại tới 10:08 — không còn đúng chính sách ban đầu. Ngược lại, với giỏ hàng “30 phút sau lần sửa cuối”, việc làm mới TTL sau sửa giỏ lại là hành vi mong muốn.

Bài học thuộc chương **Thời gian hết hạn** của module **SPRING_DATA_COUCHBASE**. Module bao gồm document mapping, repository, `CouchbaseTemplate`, SQL++, bucket/scope/collection, index, TTL, CAS, giao dịch và API reactive để bảo đảm hiệu năng, tính nhất quán và khả năng vận hành.

**Mục tiêu:**

1. Phân biệt ba chiến lược **preserve, override, refresh** của expiry khi ghi.
2. Dùng các option Couchbase Java SDK như `ReplaceOptions`, `UpsertOptions`, `preserveExpiry` và các API `touch`.
3. Hiểu sự khác nhau giữa thao tác qua Spring Data mapper và mutation SDK/SQL++ trực tiếp.
4. Giữ deadline cố định khi có retry, đồng thời xử lý CAS conflict và document hết hạn giữa lúc đọc và ghi.
5. Đọc metadata expiry để xác nhận hành vi thật, xét cả `maxTTL` ở server.
6. Thiết kế kiểm thử, monitoring và chiến lược nâng cấp/migration TTL.

Các ví dụ theo hướng **Spring Boot 3.x, Spring Data Couchbase 5.x, Couchbase Java SDK 3.x** tương thích. Chữ ký API và các trường hợp bảo toàn expiry cần đối chiếu phiên bản SDK/server thực tế.

## 2. Ba chính sách cần đặt tên tường minh

Cùng một document OTP hết hạn lúc 10:05, service ghi lại nội dung lúc 10:03:

| Chính sách | Hành động về thời hạn | Hạn sau ghi | Ví dụ nghiệp vụ |
| --- | --- | --- | --- |
| **Giữ lại (preserve)** | Không đổi expiry metadata đã có | Vẫn 10:05 | OTP, token reset mật khẩu, reservation có hạn cố định |
| **Thay thế (override)** | Đặt một thời điểm mới cụ thể | Ví dụ 10:04 hoặc 10:10 | Rút ngắn/hợp lệ gia hạn theo quyết định nghiệp vụ |
| **Làm mới (refresh)** | Đặt một TTL tương đối mới từ lúc thao tác | Nếu 5 phút, khoảng 10:08 | Cart/session dạng sliding TTL |

~~~mermaid
sequenceDiagram
    participant App as Service
    participant CB as Couchbase
    App->>CB: 10:00 tạo OTP với expiry 10:05
    Note over CB: Hạn ban đầu = 10:05
    alt Preserve
      App->>CB: 10:03 ghi failedAttempts và giữ expiry
      Note over CB: Hạn = 10:05
    else Override với Instant
      App->>CB: 10:03 ghi deadline mới 10:04
      Note over CB: Hạn = 10:04
    else Refresh với Duration 5 phút
      App->>CB: 10:03 ghi lại TTL tương đối
      Note over CB: Hạn = khoảng 10:08
    end
~~~

Thay thế là khái niệm rộng: đặt một mốc mới có thể là rút ngắn hoặc kéo dài hạn. Refresh là trường hợp riêng của thay thế khi hạn mới được **tính lại từ một sự kiện**. API có thể tương tự nhau, nhưng **quyền nghiệp vụ** được gia hạn khác quyền chỉ được sửa nội dung.

## 3. Phân biệt metadata expiry với JSON content

Ví dụ:

~~~json
{
  "userId": "u-42",
  "failedAttempts": 2,
  "issuedAt": "2026-11-25T10:00:00Z",
  "expiresAt": "2026-11-25T10:05:00Z"
}
~~~

Đây là nội dung JSON của `otp::u-42` trong `commerce.checkout.otp_codes`. Field `expiresAt` phục vụ nghiệp vụ hoặc hiển thị, **không tự trở thành** metadata expiration trên server. Nếu hệ thống lưu cả field JSON và metadata expiry, phải bảo đảm:

- `issuedAt`/`expiresAt` không bị tính lại ngoài ý muốn khi retry hoặc save.
- Mutation đặt expiry thực qua SDK options hoặc mapper Spring Data.
- Khi server `maxTTL` rút ngắn hiệu lực, ứng dụng không tiếp tục quảng cáo deadline xa hơn thực tế nếu điều đó gây hại.
- Dữ liệu đã hết hạn logic không bị coi là còn hợp lệ chỉ vì hệ thống chưa thu hồi toàn bộ storage.

Ví dụ keyspace:

~~~text
Cluster commerce-cluster
└── Bucket commerce
    └── Scope checkout
        ├── Collection otp_codes
        ├── Collection carts
        └── Collection reservations
~~~

Bucket, scope và collection phải tồn tại trước khi thao tác. Chọn sai keyspace có thể trông giống lỗi expiry vì `get(id)` báo không thấy document.

## 4. Mặc định mutation không phải lời hứa preserve

Một trong những sai lầm phổ biến nhất là nghĩ rằng `replace(id, json)` hoặc `upsert(id, json)` **không truyền expiry** có nghĩa “giữ nguyên expiry cũ”. Trong các mutation Couchbase, nếu không chủ động dùng cơ chế preserve, expiry có thể được đặt lại về 0 ở cấp document hoặc chịu policy mặc định/`maxTTL` của server.

| Thao tác | Điều phải hiểu |
| --- | --- |
| `insert` mới | Chưa có hạn cũ để preserve; chọn TTL khi tạo |
| `upsert` không expiry | Có thể tạo mới hoặc thay content; không mặc định xem là preserve |
| `replace` không expiry | Có thể reset hạn cũ theo semantics của thao tác/server |
| `replace` với `preserveExpiry(true)` | Nêu rõ ý định bảo toàn metadata expiry |
| `replace` với `expiry(Duration/Instant)` | Nêu rõ ý định đặt một expiry mới |
| `touch` | Thay metadata expiry, không cần thay JSON |
| `getAndTouch` | Đọc đồng thời đổi expiry; không phải read-only |
| `repository.save(entity)` | Mapping/version có thể áp TTL của entity |
| SQL++ `UPDATE` | Không tự đọc annotation Java, phải xác minh SQL++ semantics |

Cần phân biệt **không expiry** (thường giá trị 0 ở cấp document) với **preserve expiry** (giữ mốc đang có). Chúng khác nhau ngay cả khi document hiện tại chỉ còn vài giây trước khi hết hạn.

## 5. Giữ nguyên hạn bằng `preserveExpiry(true)`

Couchbase Java SDK 3.x có `ReplaceOptions` hỗ trợ preserve expiry ở các phiên bản tương ứng:

~~~java
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.ReplaceOptions;

// otpCodes trỏ tới commerce.checkout.otp_codes.
// updatedContent phải là TOÀN BỘ nội dung document.
otpCodes.replace(
        "otp::u-42",
        updatedContent,
        ReplaceOptions.replaceOptions().preserveExpiry(true)
);
~~~

Ý định: thay content nhưng **giữ nguyên deadline metadata** đã có trên document.

**Các giới hạn:**

1. `replace` thay toàn bộ content, không phải partial update. Dùng JSON hoàn chỉnh hoặc subdocument API phù hợp nếu chỉ sửa một field.
2. `replace` cần document đang tồn tại; nếu document hết hạn giữa lúc đọc và ghi, thao tác có thể thất bại. Không tự dùng `upsert` để hồi sinh OTP.
3. Preserve không xử lý xung đột ghi. Dùng CAS nếu nhiều request cạnh tranh.
4. Tránh cấu hình đồng thời `preserveExpiry(true)` và expiry mới trong một mutation: hai ý định đối nghịch; SDK có thể từ chối tổ hợp.
5. Tác động của `maxTTL` và khả năng bảo toàn metadata cần kiểm thử trên server version đang chạy.

### 5.1. Ví dụ tăng số lần thử OTP mà không gia hạn

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.kv.ReplaceOptions;

public final class OtpAttemptService {

    private final Collection otpCodes;

    public OtpAttemptService(Collection otpCodes) {
        this.otpCodes = otpCodes;
    }

    public void recordFailedAttempt(String key) {
        GetResult current = otpCodes.get(key);
        JsonObject next = current.contentAsObject();

        Integer old = next.getInt("failedAttempts");
        next.put("failedAttempts", (old == null ? 0 : old) + 1);

        otpCodes.replace(
                key,
                next,
                ReplaceOptions.replaceOptions()
                        .cas(current.cas())
                        .preserveExpiry(true)
        );
    }
}
~~~

Nếu có lỗi CAS mismatch, một writer khác đã thay đổi document; service cần đọc lại và đánh giá retry hữu hạn. Nếu document hết hạn hoặc không tồn tại, phải trả trạng thái mã đã hết hiệu lực. Nếu mutation timeout mơ hồ, **không chắc** bộ đếm chưa tăng; cần đối soát.

Code tập trung vào metadata expiry/CAS, chưa phải một hệ thống OTP đầy đủ. Sản phẩm thật còn cần hạn chế số lần thử, đánh dấu mã đã dùng, rate limit, xử lý hash và các biện pháp bảo mật riêng.

## 6. Thay thế hạn bằng `Instant`

Khi muốn đặt một deadline cố định mới, dùng `Instant` biểu diễn mốc UTC thay vì tính lại thời lượng mỗi lần ghi.

~~~java
import java.time.Instant;
import com.couchbase.client.java.kv.ReplaceOptions;

Instant newDeadline =
        Instant.parse("2026-12-01T16:00:00Z");

reservations.replace(
        "reservation::R-100",
        completeUpdatedJson,
        ReplaceOptions.replaceOptions().expiry(newDeadline)
);
~~~

Nếu reservation trước đó hết hạn 17:00, thao tác trên rút hạn về 16:00. Nếu quyết định gia hạn được phê duyệt đến 19:00, service có thể đặt `Instant` 19:00. Cả hai đều là **override**, nhưng quyền và audit của chúng có thể rất khác nhau.

### 6.1. Không dùng duration để diễn đạt deadline không đổi

Nếu deadline phải luôn là 16:00, việc mỗi lần retry lấy `Duration.between(Instant.now(), deadline)` có thể bị ảnh hưởng bởi độ trễ, làm tròn và chuyển đổi raw numeric ở các API cấp thấp. Nên dùng thẳng cùng `Instant`, nếu API hỗ trợ.

Nếu deadline đã ở quá khứ, kiểm tra nghiệp vụ nên từ chối thao tác hoặc xác nhận hết hạn trước khi mutation, thay vì kỳ vọng một expiry quá khứ sẽ điều phối toàn bộ logic.

### 6.2. Thời điểm theo múi giờ nghiệp vụ

Ví dụ kết thúc lúc đầu ngày 1 tháng 12 năm 2026 theo giờ Việt Nam:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

Instant endExclusive = LocalDate.of(2026, 12, 1)
        .atStartOfDay(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toInstant();
~~~

Mốc này là `2026-11-30T17:00:00Z`, khác đầu ngày 1/12 theo UTC. Khi lưu và gửi expiry, ưu tiên `Instant`; khi hiển thị, chuyển qua timezone người dùng.

## 7. Làm mới TTL khi mutation được phép gia hạn

Giả sử giỏ hàng phải hết hạn **30 phút sau lần sửa giỏ gần nhất**. Một thao tác sửa item count có thể đặt TTL tương đối mới.

~~~java
import java.time.Duration;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

JsonObject content = JsonObject.create()
        .put("userId", "u-42")
        .put("itemCount", 3);

carts.upsert(
        "cart::u-42",
        content,
        UpsertOptions.upsertOptions()
                .expiry(Duration.ofMinutes(30))
);
~~~

Nếu ghi thành công lúc 10:20, hạn mới thường gần 10:50, khi không bị `maxTTL` giới hạn. Đây là hành vi refresh, **khác** preserve.

**Cẩn thận với `upsert`:** nếu giỏ hàng đã hết hạn, upsert có thể tạo lại key. Nếu nghiệp vụ chỉ muốn “sửa cart đang còn tồn tại”, nên dùng replace hoặc một cơ chế điều kiện phù hợp để không hồi sinh dữ liệu đã hết hạn ngoài ý muốn.

### 7.1. Refresh cùng với CAS

~~~java
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.kv.ReplaceOptions;
import java.time.Duration;

GetResult read = carts.get("cart::u-42");
var updated = read.contentAsObject();
updated.put("itemCount", 3);

carts.replace(
        "cart::u-42",
        updated,
        ReplaceOptions.replaceOptions()
                .cas(read.cas())
                .expiry(Duration.ofMinutes(30))
);
~~~

Thao tác này vừa ghi content dựa trên phiên bản đã đọc, vừa đặt lại TTL. CAS tránh lost update khi có writer khác; **CAS không tự quyết định việc gia hạn có hợp lệ**. Nếu CAS conflict, ứng dụng phải đọc lại và xử lý theo business rule.

## 8. Làm mới expiry không cần ghi lại JSON: `touch`

Nếu mục tiêu chỉ là thay đổi deadline, dùng `touch`:

~~~java
import java.time.Duration;

carts.touch(
        "cart::u-42",
        Duration.ofMinutes(30)
);
~~~

Một thao tác đọc và gia hạn đồng thời:

~~~java
var result = carts.getAndTouch(
        "cart::u-42",
        Duration.ofMinutes(30)
);
~~~

`getAndTouch` không phải phiên bản thay thế vô hại của `get`. Nó **thay expiry metadata**, vì thế không nên dùng trong mọi lần đọc OTP hay reservation có hard deadline.

| Nhu cầu | Thao tác thường phù hợp |
| --- | --- |
| Chỉ đọc thông tin, không gia hạn | `get` |
| Có sự kiện gia hạn và không cần sửa JSON | `touch` |
| Vừa đọc vừa gia hạn theo đúng nghiệp vụ | `getAndTouch` |
| Sửa JSON và làm mới TTL có điều kiện | `replace` với expiry mới, có CAS khi cần |
| Sửa JSON nhưng giữ nguyên hạn | `replace` với preserveExpiry |

Khi cập nhật content và expiry cần tính nguyên tử theo cùng một phiên bản document, hãy ưu tiên một mutation phù hợp thay vì `replace` rồi `touch` thành hai bước không có điều phối.

## 9. Document có thể hết hạn giữa lúc đọc và ghi

Ví dụ timeline:

~~~text
10:04:58  GET otp::u-42, nhận content + CAS
10:05:00  Document đến hạn hết hiệu lực
10:05:01  REPLACE preserveExpiry=true
~~~

Trong trường hợp này, `replace` có thể trả document-not-found. Không phải vì preserveExpiry không đúng, mà vì document **không còn tồn tại hợp lệ** để thay.

Ứng dụng nên:

1. Nhận diện document-not-found/expired theo ngữ nghĩa nghiệp vụ.
2. Không fallback sang `upsert` để tạo lại OTP/reservation cũ.
3. Nếu CAS conflict, chỉ retry khi document còn hợp lệ và có ý nghĩa.
4. Nếu business cần cấp mới, thực hiện luồng phát hành mới với identity, authorization và idempotency riêng.

TTL không phải transaction lock. Với các thao tác có cạnh tranh, cần kết hợp CAS/transaction và kiểm tra deadline nghiệp vụ.

## 10. Server `maxTTL` quyết định giới hạn hiệu lực

Couchbase có thể đặt maximum TTL cho bucket hoặc collection theo server version. Khi request expiry và maxTTL xung đột, thời hạn metadata cuối cùng do server xác định.

| Yêu cầu ứng dụng | Cấu hình server | Cần hiểu |
| --- | --- | --- |
| Cart refresh 30 phút | maxTTL collection 10 phút | Hạn thực có thể còn 10 phút |
| Reservation override đến cuối tháng | maxTTL 7 ngày | Có thể bị giới hạn trước deadline mong muốn |
| Product không expiry | maxTTL bucket 24 giờ | Có thể vẫn hết hạn |
| OTP preserve hạn cũ còn 2 phút | maxTTL 5 phút | Kiểm tra server metadata; không suy luận bị tự kéo dài |
| Replace không gửi expiry | Collection có maxTTL | Phải kiểm tra default/reset behavior cụ thể |

~~~mermaid
flowchart TD
    A["Ý định client: preserve / override / refresh"] --> B["SDK / Mapper mutation"]
    C["Bucket hoặc collection maxTTL"] --> D["Couchbase Server"]
    B --> D
    D --> E["Expiry metadata hiệu lực"]
    E --> F["KV / SQL++ nhìn nhận document"]
~~~

Không tự thêm property `spring.data.couchbase.maxTTL` vào YAML và cho rằng Spring Boot sẽ cấu hình server. Đây là chính sách phía cluster, phải xác minh ở đúng bucket/collection.

## 11. `@Document(expiry)` và `repository.save(...)`

Một entity Spring Data Couchbase có thể khai báo TTL tĩnh:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;

@Document(expiry = 900) // Thông thường 900 giây ở version hỗ trợ
public class LoginSessionDocument {

    @Id
    private String id;
    private String userId;

    protected LoginSessionDocument() {
    }

    public LoginSessionDocument(String id, String userId) {
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

public interface LoginSessionRepository
        extends CouchbaseRepository<LoginSessionDocument, String> {
}
~~~

Khi gọi `repository.save(entity)`, mapper có thể áp dụng expiry theo metadata annotation. Tuy vậy, **không mặc định lần save lại sẽ giữ hạn cũ hoặc luôn refresh**. Phải xác minh behavior create/update ở đúng release và bằng metadata thực tế.

~~~text
10:00  repository.save(session)  => dự kiến hạn 10:15
10:10  repository.save(session đã sửa)
       => giữ 10:15, gia hạn 10:25, hay policy khác?
~~~

Câu trả lời phụ thuộc Spring Data mapper, SDK operation và maxTTL server. Đây là lý do **annotation mô tả TTL không thay thế test hành vi của đường ghi**.

### 11.1. TTL động theo entity

Một số phiên bản Spring Data Couchbase có cơ chế expiry expression hoặc `@Expiry`. Cách cấu hình, kiểu dữ liệu, precedence và behavior update phải kiểm tra trong Javadoc của bản đã resolve. Không khẳng định mọi phiên bản đều có cùng method hoặc có thể preserve tự động.

Nếu mapper không đáp ứng policy như OTP cần hạn cố định, chọn `CouchbaseTemplate`/SDK API thích hợp và ghi rõ trách nhiệm expiry ở service.

## 12. Khi trộn repository, template và SDK

Hệ thống đôi khi tạo session bằng repository nhưng cập nhật bằng SDK trực tiếp. Đường SDK **không tự biết annotation `@Document`**:

~~~java
// Tạo qua Spring Data mapping.
sessionRepository.save(session);

// Cập nhật trực tiếp bằng SDK: phải chọn expiry rõ ràng.
sessions.replace(
        id,
        completeUpdatedJson,
        ReplaceOptions.replaceOptions()
                .preserveExpiry(true)
);
~~~

Nếu SDK ghi `JsonObject`, nó cũng không tự áp converter hoặc `@Version` của Spring Data. Cần thống nhất schema JSON, CAS và expiration.

### 12.1. `CouchbaseTemplate`

Template có các API entity và operation options theo phiên bản; mỗi đường insert/upsert/replace có thể áp mapping expiry theo cách khác. Khi đổi repository sang template vì hiệu năng hoặc thao tác đặc biệt:

- Kiểm tra mutation nào được gọi thực tế.
- Kiểm tra có sử dụng entity expiry metadata không.
- Xác định reset/preserve/override trong update.
- Xem xét CAS/`@Version` nếu tài liệu có cạnh tranh.
- Viết integration test trước/sau refactor.

### 12.2. SQL++ không tự đọc annotation Java

Ví dụ:

~~~sql
UPDATE `commerce`.`checkout`.`carts` AS c
SET c.itemCount = 3
WHERE META(c).id = "cart::u-42";
~~~

Câu SQL++ không biết `@Document(expiry = 900)` của Java entity. Semantics expiration của SQL++ phải kiểm tra theo server version và API của statement; không giả định nó giống `Collection.replace`. Sau update, đọc metadata expiry nếu nghiệp vụ yêu cầu bảo toàn chính xác.

Index SQL++ phục vụ việc tìm document theo điều kiện; index không quyết định TTL. Với key đã biết, KV `get` là phép kiểm tra sự tồn tại đơn giản hơn Query service.

## 13. Retry và `AmbiguousTimeoutException`

Khi mutation timeout mà client không biết server đã thực hiện hay chưa, retry có thể **đặt lại relative TTL**:

~~~text
10:00:00  Gửi OTP TTL 5 phút
10:00:01  Client timeout, kết quả chưa rõ
10:00:04  Retry TTL 5 phút mới
10:05:04  Hạn có thể bị dịch 4 giây
~~~

Để tránh dịch deadline ngoài ý muốn, tính một mốc tuyệt đối **một lần** rồi tái sử dụng:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

Clock clock = Clock.systemUTC();

Instant issuedAt = Instant.now(clock);
Instant deadline = issuedAt.plus(Duration.ofMinutes(5));

JsonObject otp = JsonObject.create()
        .put("hash", otpHash)
        .put("issuedAt", issuedAt.toString())
        .put("expiresAt", deadline.toString());

otpCodes.upsert(
        otpKey,
        otp,
        UpsertOptions.upsertOptions().expiry(deadline)
);
~~~

Ví dụ chỉ minh họa **deadline cố định**; không khuyến nghị upsert hoặc retry OTP vô điều kiện. Sản phẩm thật cần key ổn định, idempotency, kiểm soát trường hợp phát hành trùng, kết quả ghi mơ hồ và trạng thái mã đã dùng.

**Quy tắc:** retry kỹ thuật không phải một sự kiện nghiệp vụ mới được quyền gia hạn tài liệu. Với cart, có thể làm mới từ hoạt động sửa cuối hợp lệ; với OTP, deadline phải gắn với lúc phát hành.

## 14. Session: idle TTL và absolute lifetime

Một session có thể dùng idle TTL 20 phút và hard deadline 8 giờ tính từ lúc cấp. Nếu chỉ gọi `touch(Duration.ofMinutes(20))` cho mọi hoạt động, session có thể sống dài hơn 8 giờ.

~~~text
issuedAt:          09:00
absoluteDeadline:  17:00
lastActivity:      16:50
idleDeadline:      17:10
effectiveDeadline: 17:00
~~~

Hàm tính mốc:

~~~java
import java.time.Duration;
import java.time.Instant;

static Instant effectiveExpiry(
        Instant issuedAt,
        Instant now,
        Duration idleTtl,
        Duration absoluteLifetime) {

    Instant idleUntil = now.plus(idleTtl);
    Instant hardUntil = issuedAt.plus(absoluteLifetime);

    return idleUntil.isBefore(hardUntil)
            ? idleUntil
            : hardUntil;
}
~~~

Nếu kết quả đã qua, service phải từ chối gia hạn. Nếu còn hiệu lực và cần cập nhật session content, `replace` với CAS và `expiry(effectiveInstant)` có thể phù hợp hơn `touch(Duration)`. Không reset `issuedAt` mỗi lần hoạt động.

## 15. CAS, `@Version` và thời hạn là các điều kiện độc lập

CAS giúp ngăn lost update, không đặt expiry; expiry quyết định vòng đời document, không ngăn lost update.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant CB as Couchbase
    A->>CB: GET cart => CAS c1
    B->>CB: GET cart => CAS c1
    B->>CB: REPLACE CAS c1 + refresh TTL
    CB-->>B: Success, CAS c2
    A->>CB: REPLACE CAS c1 + preserve expiry
    CB-->>A: CAS mismatch
~~~

Khi CAS conflict, retry có điều kiện phải đọc lại content; khi document hết hạn trong lúc thực hiện, báo not-found/expired thay vì tạo mới vô điều kiện. Spring Data `@Version` cho optimistic locking khi API mapping hỗ trợ, nhưng không thay chính sách preserve/refresh.

Giao dịch Couchbase có thời gian chờ và commit/rollback riêng. TTL không phải transaction scheduler hoặc distributed lock có fencing. Nếu business yêu cầu “reservation còn hạn mới được xác nhận”, cần kiểm tra deadline trong logic nghiệp vụ cùng CAS/transaction phù hợp.

## 16. Reactive và resubscription

Couchbase Java SDK reactive dùng options expiry tương ứng:

~~~java
import java.time.Duration;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;
import reactor.core.publisher.Mono;

Mono<?> write = carts.reactive().upsert(
        "cart::u-42",
        JsonObject.create().put("itemCount", 3),
        UpsertOptions.upsertOptions()
                .expiry(Duration.ofMinutes(30))
);
~~~

Những điểm cần lưu ý:

- Chỉ tạo `Mono` chưa chạy mutation; cần subscription.
- Retry/resubscription có thể lặp write và làm mới TTL tương đối.
- `Mono.timeout(...)` là timeout của pipeline, không phải TTL document.
- Cancellation không bảo đảm mutation đã gửi tới server bị rollback.
- Reactive repository vẫn cần đánh giá mapper expiry và đường write thực.

Với deadline cố định, nên tính `Instant` một lần trước khi xây request có thể retry, đồng thời có idempotency và budget cho retry. Không retry mù mutation chỉ vì timeout.

## 17. Đọc metadata expiry để xác minh

SDK Java có thể trả expiry metadata khi yêu cầu qua `GetOptions` ở phiên bản hỗ trợ:

~~~java
import com.couchbase.client.java.kv.GetOptions;

var result = otpCodes.get(
        "otp::u-42",
        GetOptions.getOptions().withExpiry(true)
);

result.expiryTime().ifPresent(deadline ->
        System.out.println("Expiry: " + deadline)
);
~~~

Điều này giúp kiểm tra **thời điểm đã được server áp dụng**, không chỉ giá trị ở source. `expiryTime()` có dạng tùy chọn theo SDK API; cần hiểu trường hợp không có expiry và các giới hạn API qua Javadoc đúng version.

| Trước ghi | Thao tác | Kiểm tra sau ghi |
| --- | --- | --- |
| Hạn 10:05 | Replace preserve | Vẫn gần 10:05 |
| Hạn 10:05 | Replace `expiry(Instant 10:04)` | Hạn gần 10:04 |
| Hạn 10:05 | Refresh lúc 10:03 bằng `Duration 5m` | Hạn gần 10:08 |
| Không TTL | Replace preserve | Không tự được thêm TTL ngoài policy server |
| TTL 30m | maxTTL collection 10m | Kiểm tra giới hạn hiệu lực |

Không ghi metadata expiry của mọi request vào log production nếu không thực sự cần; dùng test, chẩn đoán hoặc nghiệp vụ cụ thể.

## 18. Integration test ba chính sách

Một bộ test TTL nên chạy trong collection test với `maxTTL` đã biết, dùng key riêng cho mỗi kịch bản.

### 18.1. Preserve

1. Tạo document với TTL khoảng 20 giây.
2. Đọc expiry metadata và CAS.
3. Replace JSON với `preserveExpiry(true)` và CAS nếu cần.
4. Đọc lại metadata.
5. Kiểm tra deadline hầu như không đổi theo độ phân giải SDK/server và JSON đã cập nhật.

### 18.2. Override

1. Tạo document với `Instant` đủ xa trong tương lai.
2. Replace với `expiry(newInstant)` là một mốc sớm hơn vẫn trong tương lai.
3. Đọc metadata và so sánh với mốc mới, có dung sai.
4. Xác minh không có lần update khác đã can thiệp.

### 18.3. Refresh

1. Tạo cart với TTL 15 giây.
2. Đợi một khoảng ngắn, sau đó `touch(Duration.ofSeconds(15))`.
3. Đọc expiry metadata; hạn mới phải dịch theo ý định.
4. Poll có deadline nếu cần kiểm tra khi document thực sự không còn đọc được.

### 18.4. Các race test cần có

- Document hết hạn giữa `get` và `replace`: không được tự tái tạo mã cũ.
- Hai writer thay đổi cùng CAS: một thao tác bị conflict.
- Mutation timeout mơ hồ: không khởi tạo deadline mới khi nghiệp vụ yêu cầu cố định.
- Collection có `maxTTL` thấp hơn TTL client: hành vi cần được xác minh.

**Đừng assert tại đúng từng mili giây.** Độ phân giải expiry, clock và scheduling có sai số; nên dùng khoảng dung sai và polling hữu hạn.

## 19. Kiểm thử phép tính với đồng hồ cố định

Trước khi dùng server thật, test logic hard deadline bằng `Clock.fixed`:

~~~java
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class SessionDeadlineTest {

    @Test
    void refreshDoesNotExceedHardDeadline() {
        Instant issuedAt = Instant.parse("2026-12-01T09:00:00Z");
        Instant now = Instant.parse("2026-12-01T16:50:00Z");

        Instant expiry = effectiveExpiry(
                issuedAt,
                now,
                Duration.ofMinutes(20),
                Duration.ofHours(8)
        );

        assertThat(expiry)
                .isEqualTo(Instant.parse("2026-12-01T17:00:00Z"));
    }
}
~~~

Test thuần chỉ chứng minh tính deadline, không chứng minh mutation đã áp metadata server. Dùng cả unit test lẫn integration test.

## 20. Thay cấu hình TTL không tự cập nhật document cũ

Giả sử TTL cart trong YAML đổi từ `30m` xuống `15m`. Các document đã lưu có expiry metadata riêng; đổi property, đổi hằng số `@Document(expiry)` hoặc restart service **không tự viết lại mọi document cũ**.

Nếu cần migration, hãy:

1. Quy định document nào giữ deadline cũ và document nào cần cập nhật.
2. Chọn chiến lược touch/replace/batch có giới hạn tải.
3. Kiểm tra keyspace, `maxTTL`, thời gian và quyền truy cập.
4. Dùng CAS/idempotency để tránh ghi đè đồng thời.
5. Theo dõi tiến độ và lỗi, có kế hoạch resume/rollback thích hợp.
6. Đừng áp TTL ngắn nhầm lên order/audit chỉ vì dùng chung một cấu hình.

## 21. Bảng chẩn đoán

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| OTP được gia hạn sau khi nhập sai | Save/upsert/replace reset hoặc áp TTL mới | Preserve expiry hoặc dùng lại fixed `Instant` |
| OTP biến mất trước khi cập nhật bộ đếm | Document hết hạn giữa read/write | Xử lý not-found đúng nghiệp vụ |
| Cart hết sớm hơn 30 phút | `maxTTL` ngắn hơn | Kiểm tra policy server |
| Cart cứ được gia hạn khi xem | Dùng touch/getAndTouch thay cho get | Tách read khỏi renewal |
| Replace làm document không còn deadline cũ | Không gửi expiry, không preserve | Dùng option tường minh |
| Override không có hiệu lực như dự kiến | Mapper ghi đè hoặc server maxTTL | Đọc expiry metadata |
| SDK và repository không giống nhau | SDK không đọc annotation | Chuẩn hóa policy từng đường ghi |
| CAS mismatch | Writer khác đã sửa | Đọc lại, retry hữu hạn |
| SQL++ update khiến expiry khác mong muốn | Semantics API khác | Kiểm tra Server version và metadata |
| Reactive retry kéo dài hạn | Re-subscribe mutation relative TTL | Fixed deadline hoặc kiểm soát retry |
| Test expiry không ổn định | Clock/độ phân giải sát ngưỡng | Tolerance và polling |
| Data hết hạn nhưng disk chưa giảm | Expiry logic khác dọn vật lý | Quan sát server metrics phù hợp |

## 22. Bài tập tình huống

Một `checkout-service` quản lý:

~~~text
commerce.checkout.otp_codes
commerce.checkout.carts
commerce.checkout.reservations
~~~

Yêu cầu:

- OTP hết hạn 5 phút sau lúc cấp, không gia hạn khi người dùng nhập sai.
- Cart hết hạn 30 phút sau lần sửa cuối, không gia hạn khi chỉ xem.
- Reservation hết hạn chính xác `2026-12-01T16:00:00Z`. Nhân viên có thể rút hạn đến 15:00 khi được phép.
- Collection `carts` bị cấu hình `maxTTL` 10 phút.
- Có thể xảy ra CAS conflict, ambiguous mutation timeout và retry.

**Câu hỏi thực hành:**

1. Tăng bộ đếm OTP cần preserve, override hay refresh? Tại sao?
2. Khi sửa cart, `replace` với CAS và `expiry(Duration)` phù hợp ở đâu?
3. Khi xem cart, có nên dùng `getAndTouch` không?
4. Vì sao TTL cart thực tế có thể chỉ 10 phút?
5. Đổi reservation từ 16:00 sang 15:00 dùng `Duration` hay `Instant`?
6. Vì sao retry OTP với relative TTL mới có thể vi phạm deadline?
7. Preserve expiry có tự ngăn lost update không?
8. Nếu OTP hết hạn giữa đọc và ghi, có được fallback sang upsert không?
9. Khi đổi repository sang SDK, annotation `@Document(expiry)` có còn được áp tự động không?
10. Hãy thiết kế integration test so sánh metadata expiry trước/sau mỗi chính sách.

**Hướng trả lời:** OTP cần giữ deadline, cart refresh sau sự kiện sửa hợp lệ nhưng chịu maxTTL, reservation thay bằng absolute `Instant`; CAS giải quyết cạnh tranh chứ không đặt hạn; retry phải có idempotency; SDK và SQL++ không tự áp entity mapping.

## 23. Checklist trước production

- [ ] Mỗi mutation ghi rõ ý định preserve, override hoặc refresh.
- [ ] Không coi thiếu expiry option đồng nghĩa preserve.
- [ ] Không reset TTL OTP/token bởi ghi metadata hoặc retry.
- [ ] Cart/session chỉ refresh theo sự kiện được phép.
- [ ] Có hard deadline nếu sliding session yêu cầu.
- [ ] `replace` dùng content đầy đủ và CAS khi cần.
- [ ] Không kết hợp preserve với expiry mới gây mâu thuẫn.
- [ ] Kiểm tra API/operation options của SDK version đang chạy.
- [ ] Repo/template/SDK/SQL++ tuân cùng expiry policy.
- [ ] Đã xác minh server `maxTTL` ở đúng bucket/collection.
- [ ] Có test đọc metadata trước/sau update.
- [ ] Xử lý document hết hạn giữa GET và REPLACE.
- [ ] Retry ambiguous mutation có idempotency và không tự tạo deadline mới.
- [ ] Reactive resubscribe không gia hạn trái nghiệp vụ.
- [ ] Migration TTL có kế hoạch cho document đã tồn tại.
- [ ] Không xem TTL là cam kết xóa vật lý khỏi mọi bản sao tức thời.

## 24. Tổng kết

**Giữ lại, thay thế và làm mới expiry** là ba quyết định khác nhau khi ghi document. `preserveExpiry(true)` giúp giữ metadata hạn cũ khi mutation hỗ trợ; `expiry(Instant)` đặt một mốc mới cố định; `expiry(Duration)` và `touch(Duration)` làm mới thời lượng tương đối theo sự kiện.

Trong Spring Data Couchbase, `@Document(expiry)`, repository, `CouchbaseTemplate`, SDK và SQL++ có thể đi qua các cơ chế ghi khác nhau. Vì thế phải xác định rõ **đường ghi nào sở hữu chính sách expiry**, kiểm soát CAS/retry và xét `maxTTL` server.

Cách chắc chắn nhất là thiết kế policy tại tầng nghiệp vụ, sau đó **đọc lại expiry metadata từ server** để chứng minh thao tác preserve/override/refresh thực hiện đúng. Nhờ vậy hệ thống có thể dùng TTL cùng index, CAS, giao dịch và reactive API mà không làm sai vòng đời dữ liệu.

