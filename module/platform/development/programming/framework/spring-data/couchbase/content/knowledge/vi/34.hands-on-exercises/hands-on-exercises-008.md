# Lưu phiên đăng nhập có TTL và kiểm tra làm mới thời hạn trong Spring Data Couchbase

> **Chương:** Bài thực hành  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase bằng Spring Data với document mapping, repository, `CouchbaseTemplate` và truy vấn SQL++; thực hành bucket/scope/collection, TTL, CAS, durability và lựa chọn API reactive theo nhu cầu hiệu năng và tính đúng đắn.

## 1. Bối cảnh: một phiên đăng nhập nên sống được bao lâu?

Sau khi xác thực thành công, ứng dụng cần một **session có thời hạn**, để mỗi request không phải kiểm tra lại mật khẩu. Một mô hình thông dụng lưu session ở Couchbase và cho hết hạn khi không còn hoạt động trong một khoảng thời gian.

Giả sử lab dùng:

~~~text
Idle timeout (trượt): 6 giây
Absolute session lifetime: 20 giây
Cookie/token: giá trị ngẫu nhiên có entropy cao
Couchbase key: session::<SHA-256 của token>
Keyspace: security_lab.auth.sessions
~~~

Đây là **thời gian rất ngắn để kiểm thử**, không phải khuyến nghị TTL cho ứng dụng thật. Giả sử một session được tạo lúc `12:00:00`:

| Thời điểm | Hành động | Kết quả mong đợi theo sliding TTL 6 giây |
|---|---|---|
| 12:00:00 | Đăng nhập, tạo document | Hạn idle khoảng 12:00:06 |
| 12:00:03 | Request hợp lệ và làm mới TTL | Hạn idle chuyển gần 12:00:09 |
| 12:00:07 | Đọc expiry metadata bằng SDK `get` không touch (để kiểm tra trong lab) | Còn sống nhờ lần làm mới trước, nhưng lần kiểm tra không gia hạn |
| 12:00:10 | Không hoạt động từ 12:00:03 | Đã vượt hạn idle 12:00:09, từ chối |
| 12:00:20 | Dù liên tục hoạt động | Hết hạn tuyệt đối, không được làm mới thêm |

Hai loại hạn không được trộn:

- **Sliding/idle expiration:** hạn tương đối tính lại sau một lần hoạt động hợp lệ.
- **Absolute expiration:** giới hạn cố định từ lúc tạo, dù người dùng liên tục hoạt động.

Bài hướng dẫn hai chế độ: cơ chế `@Document(touchOnRead = true)` giúp hiểu TTL trượt tự động; và cơ chế **kiểm tra phiên rồi `touch` theo hạn bị chặn bởi absolute deadline** để có điều kiện xác thực rõ ràng hơn.

## 2. Mục tiêu và tiêu chí nghiệm thu

Sau thực hành, bạn có thể:

1. Cấu hình Couchbase bucket/scope/collection dành cho sessions.
2. Giải thích TTL là metadata trên document, không phải cột `expiresAt` tự động của JSON.
3. Mapping entity bằng `@Document(expiry, expiryUnit, touchOnRead)`, `@Id` và `@Version`.
4. Lưu session bằng Spring Data `CouchbaseRepository.save` và đọc bằng `findById`.
5. So sánh đọc **không làm mới** với `touchOnRead=true` trên Spring Data.
6. Dùng Java SDK `getOptions().withExpiry(true)` và `GetResult.expiryTime()` để kiểm tra hạn thực tế.
7. Dùng `Collection.touch(id, Duration/Instant)` hoặc `getAndTouch` để làm mới expiry tại server.
8. Thiết kế kiểm tra quyền, idle timeout và **hard cap** trước khi làm mới.
9. Phân biệt `replace` làm mất TTL, `preserveExpiry(true)` và touch-only mutation.
10. Viết integration tests theo thời gian thực, với sai số đồng hồ/độ phân giải và thao tác bất đồng bộ.
11. Xử lý session not found/expired/revoked, logout, timeout ambiguous, multi-node và TTL policy.
12. Giải thích vì sao session TTL không thay thế authentication, CSRF defense, token rotation, backup/DR hoặc revocation policy.

### 2.1. Hợp đồng lab

| Trường hợp | Expected behavior |
|---|---|
| Tạo session ở môi trường lab | Lưu document và nhận opaque token một lần |
| Đọc không làm mới | TTL tiếp tục đếm xuống |
| Đọc hợp lệ và refresh | Expiry metadata chuyển tới gần `now + idleTimeout` nhưng không vượt hard deadline |
| Truy cập sau idle TTL | Không thể xác thực bằng session đã hết hạn |
| Truy cập sau absolute deadline | Từ chối dù document còn hoặc có request đồng thời |
| Logout | Remove document, token cũ không còn hợp lệ |
| Read/refresh timeout | Không mặc định hợp lệ hoặc mặc định logout; phân loại kết quả |
| Truy vấn SQL++ không thấy session | Không dùng làm bằng chứng xác thực vì index có thể trễ |

**Giới hạn bảo mật:** endpoint khởi tạo session trong lab sẽ mô phỏng bước *đã xác thực*; không có controller nào được coi là hệ thống login production nếu chưa có authentication/authorization thật.

## 3. Hiểu TTL của Couchbase trước khi viết code

Couchbase lưu **expiration metadata** gắn với mỗi KV document. Client có thể đặt thời hạn qua insert/upsert/replace options, hoặc cấu hình mặc định ở bucket/collection.

~~~mermaid
flowchart LR
    Client["HTTP request"]
    App["Spring Boot<br/>Spring Data + Java SDK"]
    KV["Couchbase Data Service"]
    Doc["Session JSON body"]
    Exp["Expiry metadata"]
    Index["Query / GSI<br/>async via DCP"]
    Client --> App --> KV
    KV --> Doc
    KV --> Exp
    KV -.-> Index
~~~

Khi document vượt thời hạn, các thao tác KV sẽ coi nó là expired/not found theo semantics của server. Việc dọn vật lý/tombstone trên disk hoặc việc GSI bắt kịp có thể không đồng bộ; **không** coi document chỉ hết hạn khi job dọn dẹp đã quét xong.

### 3.1. TTL không phải field `expiresAt` của JSON

~~~json
{
  "userId": "user-42",
  "issuedAt": "2026-11-25T03:00:00Z",
  "absoluteExpiresAt": "2026-11-25T03:00:20Z",
  "status": "ACTIVE"
}
~~~

Trong body ở trên, `absoluteExpiresAt` là **ràng buộc nghiệp vụ do ứng dụng tự lưu và kiểm tra**. Hạn idle TTL thực sự nằm ở metadata Couchbase, **không tự xuất hiện** trong JSON. Cập nhật `absoluteExpiresAt` trong body **không tự cập nhật** TTL metadata.

### 3.2. TTL=0, TTL tương đối và hạn tuyệt đối

- Nếu không đặt expiration và không có cấu hình bucket/collection áp đặt TTL, document mặc định **không tự hết hạn**.
- Với `Duration.ofSeconds(6)`, SDK đặt hạn tương đối kể từ mutation ở server.
- Với `Instant`, SDK đặt một thời điểm hết hạn cụ thể theo thời gian UTC.
- Với expiry `0`, không mặc định hiểu là "xóa ngay": ý nghĩa trong một số KV options là **không hết hạn**, nhưng bucket/collection `maxTTL` có thể vẫn áp default.
- SDK hiện đại phân biệt `Duration`/`Instant` để tránh tự chuyển thủ công một Unix timestamp thành số giây TTL.

Đối với lab dưới một phút, dùng `Duration` ngắn để nhìn rõ. Trong production, luôn kiểm tra SDK/server version và **đơn vị**; không đưa giá trị epoch milliseconds vào API đòi seconds.

### 3.3. Bucket/collection `maxTTL` có thể ghi đè thời hạn mong muốn

Một bucket hoặc collection có `maxTTL > 0` có thể vừa áp TTL mặc định, vừa **giới hạn trên** các expiry được đặt tường minh. Ví dụ collection có `maxTTL=4s`, trong khi Java code xin `6s`, server có thể đưa hạn về mức tối đa 4s.

| Layer | Ví dụ | Hiệu ứng cần kiểm tra |
|---|---|---|
| Bucket `maxTTL` | 0 (không áp default) | Chưa giới hạn bởi bucket |
| Collection `maxTTL` | 4 giây | Giới hạn explicit session TTL ở 4 giây |
| Entity `@Document(expiry=6)` | 6 giây | Chỉ hiệu lực trong giới hạn maxTTL |
| SDK `touch(Duration.ofSeconds(6))` | Tính lại 6 giây | Vẫn có thể bị collection/bucket cap |
| Body `absoluteExpiresAt` | 20 giây | **Ứng dụng phải kiểm tra**, Couchbase không hiểu business field |

Collection `maxTTL=0` thông thường thừa hưởng nonzero bucket maxTTL, không nên tự suy đây là override vô hạn. Khi muốn một collection dùng thời hạn khác, DBA phải kiểm tra semantics phiên bản Server đang chạy.

### 3.4. TTL không tương đương durability

Một mutation được xác nhận theo `MAJORITY` hay `PERSIST_TO_MAJORITY` liên quan replication/persistence; đó không phải idle timeout. Couchbase expiry processing có semantics riêng và không phải một ứng dụng của synchronous durable write cho từng lần xóa. Đừng dùng mức durability để thay một chính sách phiên.

## 4. Fixed TTL, sliding TTL và absolute lifetime

~~~mermaid
flowchart TD
    Start["Đăng nhập hợp lệ"]
    Fixed["Fixed TTL:<br/>expireAt = issuedAt + TTL"]
    Sliding["Sliding TTL:<br/>expireAt = last approved activity + idle TTL"]
    Hard["Absolute limit:<br/>hardExpiresAt = issuedAt + max lifetime"]
    Effective["Effective next expiry:<br/>min(now + idle TTL, hardExpiresAt)"]
    Start --> Fixed
    Start --> Sliding --> Effective
    Hard --> Effective
~~~

| Chiến lược | Ưu điểm | Rủi ro/chú ý |
|---|---|---|
| **Fixed** | Dễ hiểu, không bị kéo dài vô hạn | Người dùng đang thao tác vẫn có thể bị hết hạn |
| **Sliding** | Trải nghiệm tốt khi hoạt động | Nếu refresh vô điều kiện, phiên có thể sống mãi |
| **Sliding + absolute cap** | Cân bằng hoạt động và vòng đời tối đa | Cần lưu, kiểm tra hard deadline khi refresh |
| **Refresh theo ngưỡng** | Giảm số KV writes | Đổi lấy idle expiry độ chính xác theo policy |
| **Logout/revoke** | Kết thúc ngay theo yêu cầu | Cần xóa/đánh dấu session và bảo vệ race |

**Không phải mọi request HTTP đều là hoạt động hợp lệ.** Asset request, health probe, request chưa xác thực, polling nền và crawler không nên tự động làm sống một phiên nhạy cảm, trừ khi chính sách được thiết kế như vậy.

## 5. Lab architecture và ranh giới trách nhiệm

~~~mermaid
flowchart LR
    Browser["HTTP Client<br/>X-Lab-Session-Token"]
    Api["LabSessionController"]
    Service["SessionService<br/>validate + refresh"]
    Repo["SessionRepository<br/>Spring Data Couchbase"]
    SDK["Couchbase Java SDK Collection<br/>touch + expiry metadata"]
    Data["Data Service<br/>security_lab.auth.sessions"]
    Browser --> Api --> Service
    Service --> Repo --> Data
    Service --> SDK --> Data
~~~

Lab dùng hai đường API có mục đích:

- **Spring Data Repository** lưu entity và lấy document theo ID mà **không** tự refresh.
- **Java SDK KV** cập nhật expiry metadata bằng `touch(id, Instant)` và kiểm tra bằng `get(... withExpiry(true))`.

Không lẫn hai đường bằng cách kỳ vọng annotation Spring Data áp dụng cho lời gọi SDK trực tiếp. Ngược lại, SDK `touch` không tự chạy logic xác thực đang nằm trong service.

### 5.1. Vì sao không dùng SQL++ cho lookup session?

Vì session được tra theo opaque token → deterministic KV ID, `findById`/SDK `get` trực tiếp định tuyến tới Data Service. SQL++ qua GSI có độ trễ cập nhật, cần index và không phù hợp làm nguồn quyết định một bearer token có hợp lệ ngay lúc này.

## 6. Chuẩn bị môi trường

### 6.1. Yêu cầu

- JDK tương thích Spring Boot, ví dụ Java 21.
- Maven/Gradle do Spring Initializr tạo.
- Spring Boot + Spring Web + Spring Data Couchbase + Validation + Spring Boot Test.
- Couchbase Server/Capella có bucket, scope, collection và KV permissions.
- Một lab **cách ly production**, dùng user giả và token thử nghiệm.
- Đồng hồ môi trường đủ đồng bộ cho test hard deadline.
- HTTP client và khả năng xem metadata expiration qua Java SDK.

### 6.2. Tạo keyspace

~~~text
Bucket: security_lab
Scope: auth
Collection: sessions

Document ID: session::<64 hex characters SHA-256>
~~~

Tạo keyspace bằng công cụ quản trị được phép. Chọn Couchbase bucket hoặc Ephemeral theo nhu cầu durability/persistence, nhưng **TTL được hỗ trợ ở các kiểu bucket thích hợp**; nếu cần persistence hãy dùng Couchbase bucket, không suy từ Ephemeral rằng session đã persist lên disk.

Với bài lab, nên tránh bucket/collection có `maxTTL` ngắn hơn 6 giây hoặc cấu hình default trái với thí nghiệm. Ghi lại maxTTL hiện tại và replica configuration trước khi chạy.

### 6.3. Phần dependency Maven

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-couchbase</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây là **fragment** trong project đã được Spring Initializr tạo. Parent/BOM chọn phiên bản tương thích; tránh tự ghép nhiều major versions Spring Data/Couchbase SDK không đồng bộ.

### 6.4. Cấu trúc source đề xuất

~~~text
src/main/java/com/example/session/
  SessionLabApplication.java
  SessionDocument.java
  SessionRepository.java
  SessionTokenFactory.java
  SessionService.java
  LabSessionController.java
  LabSessionErrorHandler.java
src/main/resources/application.yml
src/test/java/com/example/session/
  SessionTtlIntegrationTest.java
~~~

Package Java chung là `com.example.session`. Các classes/records được minh họa dưới đây theo đúng phân chia tệp; hãy thêm các imports như ví dụ khi tạo project.

## 7. Cấu hình Spring Boot và môi trường

~~~yaml
spring:
  couchbase:
    connection-string: "${CB_CONNECTION_STRING}"
    username: "${CB_USERNAME}"
    password: "${CB_PASSWORD}"
  data:
    couchbase:
      bucket-name: security_lab

# Endpoint thử nghiệm chỉ active khi profile ttl-lab được bật.
# Không sử dụng profile này trong production.
server:
  port: 8080
~~~

Ví dụ environment lab:

~~~text
CB_CONNECTION_STRING=couchbase://127.0.0.1
CB_USERNAME=session-lab-runtime
CB_PASSWORD=<secret do môi trường cấp>
SPRING_PROFILES_ACTIVE=ttl-lab
~~~

Với Capella, dùng `couchbases://...`, TLS và certificate trust hợp lệ. Không commit credential vào Git hoặc tắt TLS để “sửa” lỗi cấu hình.

Application và UTC clock:

~~~java
package com.example.session;

import java.time.Clock;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SessionLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionLabApplication.class, args);
    }

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

`Clock` có thể thay bằng test fixture để kiểm tra business hard deadline; tuy nhiên **TTL thật vẫn tính theo server clock**, không theo fake Clock trong JUnit. Đừng cho rằng `Clock.fixed` có thể làm Couchbase tự expire nhanh hơn.

## 8. Entity Spring Data: expiry cố định, chưa bật touch-on-read

Ví dụ entity theo Spring Data Couchbase có metadata expiry:

~~~java
package com.example.session;

import java.util.concurrent.TimeUnit;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document(
    expiry = 6,
    expiryUnit = TimeUnit.SECONDS,
    touchOnRead = false
)
@Scope("auth")
@Collection("sessions")
public class SessionDocument {
    @Id
    private String id;

    @Version
    private Long version;

    private String userId;
    private String issuedAt;
    private String absoluteExpiresAt;
    private String status;

    public SessionDocument() {}

    public SessionDocument(
            String id, String userId,
            String issuedAt,
            String absoluteExpiresAt,
            String status) {
        this.id = id;
        this.userId = userId;
        this.issuedAt = issuedAt;
        this.absoluteExpiresAt = absoluteExpiresAt;
        this.status = status;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public Long getVersion() { return version; }
    public void setVersion(Long version) {
        this.version = version;
    }

    public String getUserId() { return userId; }
    public void setUserId(String userId) {
        this.userId = userId;
    }

    public String getIssuedAt() { return issuedAt; }
    public void setIssuedAt(String issuedAt) {
        this.issuedAt = issuedAt;
    }

    public String getAbsoluteExpiresAt() {
        return absoluteExpiresAt;
    }
    public void setAbsoluteExpiresAt(String absoluteExpiresAt) {
        this.absoluteExpiresAt = absoluteExpiresAt;
    }

    public String getStatus() { return status; }
    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

### 8.1. Ý nghĩa annotation

- `@Document(expiry=6, expiryUnit=SECONDS)`: Spring Data ghi document với thời hạn 6 giây theo mapping khi mutation đi qua API hỗ trợ.
- `touchOnRead=false`: các direct reads qua Spring Data **không tự reset TTL**, thuận tiện để service kiểm tra phiên trước khi refresh.
- `@Id`: document key KV.
- `@Version`: CAS token trong metadata, giúp chống ghi đè update đồng thời; **không phải** TTL hoặc timestamp.
- `@Scope`, `@Collection`: chọn đúng `auth.sessions`.
- `absoluteExpiresAt`: ràng buộc do ứng dụng lưu trong JSON; server không tự hiểu đây là hard cap.

**Quan trọng:** `@Document` annotation này **không tự áp dụng** cho SDK direct `collection.insert/replace`. Những lời gọi SDK phải đặt `expiry(...)` hoặc `preserveExpiry(...)` theo ý định.

### 8.2. Vì sao không lưu bearer token trực tiếp vào document?

Nếu body hoặc logs bị đọc trái phép, token thô có thể bị dùng để chiếm session. Bài sinh token ngẫu nhiên và dùng **SHA-256 của token** làm phần ID. Không lưu token thô trong body, không đưa username/password vào key, không log session token. Hash của token ngẫu nhiên đủ entropy khác với hash của password ít entropy; **không dùng cách này để lưu mật khẩu**.

## 9. Repository cho session theo KV key

~~~java
package com.example.session;

import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface SessionRepository
        extends CouchbaseRepository<SessionDocument, String> {
}
~~~

Các thao tác quan trọng:

~~~text
repository.save(sessionDocument)          -> mutation KV, theo metadata entity
repository.findById(sessionDocumentId)    -> KV get theo key
repository.deleteById(sessionDocumentId)  -> KV delete theo key
~~~

Không cần GSI/primary index để `save`/`findById` một document theo ID. `findAll` hoặc query theo `userId` là bài toán khác cần SQL++/Index Service và không nên dùng cho xác thực.

### 9.1. Thử trạng thái TTL không làm mới

Giả sử tạo session bằng repository `save` và không gọi `touch`:

~~~text
T0: save -> có expiry gần T0+6s
T0+2s: repository.findById -> còn thấy, TTL không reset
T0+7s: repository.findById -> expected empty sau khi hết hạn
~~~

Đây là fixed expiry nếu chỉ có các lần đọc. Sau đó bài sẽ thêm `touch` để trở thành sliding expiry. Khi kiểm thử cần chấp nhận jitter về wall clock và request scheduling, không assert TTL chính xác từng millisecond.

## 10. Sinh token bảo mật và document ID ổn định

Trong lab, **token** do server tạo một lần sau khi user đã được xác thực, không lấy token từ trường `userId` hay một timestamp dễ đoán.

~~~java
package com.example.session;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;
import java.util.regex.Pattern;

public final class SessionTokenFactory {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Pattern TOKEN =
        Pattern.compile("[A-Za-z0-9_-]{43}");

    private SessionTokenFactory() {}

    public static String newToken() {
        byte[] raw = new byte[32];  // 256-bit secret
        RANDOM.nextBytes(raw);
        return Base64.getUrlEncoder()
            .withoutPadding().encodeToString(raw);
    }

    public static String keyFor(String rawToken) {
        if (rawToken == null ||
                !TOKEN.matcher(rawToken).matches()) {
            throw new IllegalArgumentException(
                "Session token không hợp lệ");
        }

        try {
            byte[] digest = MessageDigest
                .getInstance("SHA-256")
                .digest(rawToken.getBytes(StandardCharsets.UTF_8));
            return "session::" +
                HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }
}
~~~

256-bit cryptographically secure random token khiến việc đoán/duyệt key không thực tế trong điều kiện bình thường. Tuy vậy, **token là bearer credential**: ai sở hữu token có thể giả danh user nếu endpoint không có lớp bảo vệ khác.

### 10.1. Không tạo token mới ở mỗi lần refresh

~~~text
Đăng nhập thành công -> phát token T.
Request hoạt động -> dùng lại token T, refresh expiry của key hash(T).
Logout -> xóa key hash(T).

Đổi token (rotation) là workflow bảo mật RIÊNG,
không phải side effect bắt buộc của từng touch.
~~~

Sau login/đổi quyền nhạy cảm, sản phẩm có thể cần rotate token và quản lý overlap. Không tự tạo token khác trong một phương thức `refresh` rồi quên chuyển cookie; như vậy request tiếp theo sẽ đọc nhầm key.

## 11. Spring Data có cơ chế touch-on-read tự động

Nếu mục tiêu chỉ là một demo sliding TTL đơn giản, Spring Data Couchbase hỗ trợ cấu hình:

~~~java
// PHƯƠNG ÁN THAY THẾ của entity ở mục 8,
// không khai báo class trùng tên trong cùng project.
@Document(
    expiry = 6,
    expiryUnit = java.util.concurrent.TimeUnit.SECONDS,
    touchOnRead = true
)
@Scope("auth")
@Collection("sessions")
public class SessionDocument {
    // Các fields như mục 8.
}
~~~

Trong phiên bản Spring Data hỗ trợ, direct reads như `repository.findById(id)` và `CouchbaseTemplate.findById(...).one(id)` có thể dùng get-and-touch, khiến expiry được đặt lại theo giá trị annotation.

### 11.1. Ưu điểm của automatic touch

- Ít code.
- Hợp session đơn giản “có đọc là hoạt động”.
- Dễ chứng minh TTL trượt trong lab với các lần `findById`.
- Không cần tự gọi SDK `touch` chỉ để refresh idle time.

### 11.2. Giới hạn bảo mật và nghiệp vụ

- Lần đọc **trước khi service kiểm tra quyền** có thể đã refresh TTL.
- `touchOnRead` không tự enforce một `absoluteExpiresAt` trong body.
- Không phải mọi query/read path đều được touch; annotation nói đến **direct reads**, không đảm bảo query SQL++ trả session cũng làm mới.
- Một service khác dùng SDK trực tiếp `collection.get` sẽ **không** tự áp Spring annotation.
- Nếu muốn “chỉ hoạt động được xác thực mới gia hạn”, nên dùng **manual refresh sau validation** như phần tiếp.
- Nếu test hết hạn mà gọi `repository.findById` để “kiểm tra” trong chế độ touch-on-read, chính phép kiểm tra **có thể làm session sống lâu hơn**.

**Kết luận của hai chế độ:** `touchOnRead=true` thích hợp demo/lựa chọn rõ ràng; `touchOnRead=false` + thao tác SDK touch minh bạch giúp kiểm soát trước điều kiện gia hạn và hard lifetime.

## 12. SessionService: đọc, kiểm tra và gia hạn trước hard deadline

Bài sử dụng entity `@Document(touchOnRead=false)` ở mục 8. Repository đọc session bằng KV, service kiểm tra trạng thái và hạn tuyệt đối, sau đó Java SDK `touch(id, Instant)` cập nhật TTL metadata. Hạn mới được tính:

~~~text
nextExpiry = min(now + idleTimeout, absoluteExpiresAt)
~~~

Toàn bộ service:

~~~java
package com.example.session;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;

import com.couchbase.client.core.error.DocumentNotFoundException;
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.GetResult;
import org.springframework.stereotype.Service;

import static com.couchbase.client.java.kv.GetOptions.getOptions;

@Service
public class SessionService {
    public static final Duration IDLE = Duration.ofSeconds(6);
    public static final Duration HARD = Duration.ofSeconds(20);

    private final SessionRepository repository;
    private final Collection sessions;
    private final Clock clock;

    public SessionService(
            SessionRepository repository,
            Cluster cluster, Clock clock) {
        this.repository = repository;
        this.sessions = cluster.bucket("security_lab")
            .scope("auth").collection("sessions");
        this.clock = clock;
    }

    public record Issued(
        String token, String userId,
        Instant initialExpiresAt, Instant hardExpiresAt
    ) {}

    public record Active(
        String userId, Instant renewedExpiresAt,
        Instant hardExpiresAt
    ) {}

    public Issued issueAfterSuccessfulAuthentication(
            String authenticatedUserId) {
        // Chỉ gọi khi user đã được auth thực sự.
        // Controller profile ttl-lab mô phỏng bước này.
        if (authenticatedUserId == null ||
                authenticatedUserId.isBlank()) {
            throw new IllegalArgumentException("Invalid user");
        }

        String token = SessionTokenFactory.newToken();
        Instant now = clock.instant();
        Instant hardDeadline = now.plus(HARD);
        String id = SessionTokenFactory.keyFor(token);

        var doc = new SessionDocument(
            id, authenticatedUserId, now.toString(),
            hardDeadline.toString(), "ACTIVE"
        );

        // Spring Data @Document(expiry=6,...) áp TTL ban đầu.
        repository.save(doc);

        return new Issued(token, authenticatedUserId,
            now.plus(IDLE), hardDeadline);
    }

    public Active authenticateAndRenew(String rawToken) {
        final String id;
        try {
            id = SessionTokenFactory.keyFor(rawToken);
        } catch (IllegalArgumentException invalid) {
            throw new SessionRejected("Invalid session");
        }

        final SessionDocument doc;
        try {
            doc = repository.findById(id)
                .orElseThrow(() ->
                    new SessionRejected("Session expired"));
        } catch (SessionRejected expected) {
            throw expected;
        } catch (RuntimeException dbFailure) {
            throw new StorageUnavailable(
                "Session lookup failed", dbFailure);
        }

        Instant now = clock.instant();
        final Instant hardDeadline;
        try {
            hardDeadline =
                Instant.parse(doc.getAbsoluteExpiresAt());
        } catch (RuntimeException invalidBody) {
            // Dữ liệu hỏng -> fail closed.
            throw new SessionRejected("Session invalid");
        }

        if (!"ACTIVE".equals(doc.getStatus()) ||
                !now.isBefore(hardDeadline)) {
            throw new SessionRejected("Session no longer valid");
        }

        // Production còn cần user disabled, tenant,
        // role/MFA/revocation checks từ hệ thống authoritative.
        Instant idleDeadline = now.plus(IDLE);
        Instant nextExpiry =
            idleDeadline.isBefore(hardDeadline)
                ? idleDeadline : hardDeadline;

        if (!nextExpiry.isAfter(now)) {
            throw new SessionRejected("Hard deadline reached");
        }

        try {
            // Chỉ cập nhật expiry metadata, không sửa JSON.
            sessions.touch(id, nextExpiry);
        } catch (DocumentNotFoundException gone) {
            throw new SessionRejected(
                "Session expired during refresh");
        } catch (RuntimeException touchFailure) {
            throw new StorageUnavailable(
                "Could not confirm TTL refresh", touchFailure);
        }

        return new Active(
            doc.getUserId(), nextExpiry, hardDeadline);
    }

    public void logout(String rawToken) {
        final String id;
        try {
            id = SessionTokenFactory.keyFor(rawToken);
        } catch (IllegalArgumentException invalid) {
            // Logout idempotent: không tiết lộ token tồn tại.
            return;
        }

        try {
            sessions.remove(id);
        } catch (DocumentNotFoundException alreadyGone) {
            // Trạng thái cuối đã là không còn session.
        } catch (RuntimeException error) {
            throw new StorageUnavailable(
                "Could not confirm logout", error);
        }
    }

    // Chỉ phục vụ lab diagnostics và integration tests.
    public Optional<Instant> expiryForLab(String rawToken) {
        String id = SessionTokenFactory.keyFor(rawToken);
        try {
            GetResult result = sessions.get(
                id, getOptions().withExpiry(true));
            return result.expiryTime();
        } catch (DocumentNotFoundException notFound) {
            return Optional.empty();
        }
    }

    public static class SessionRejected
            extends RuntimeException {
        public SessionRejected(String message) {
            super(message);
        }
    }

    public static class StorageUnavailable
            extends RuntimeException {
        public StorageUnavailable(
                String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

### 12.1. Hai loại clock không giống nhau

`clock.instant()` lấy giờ ứng dụng, còn Couchbase xử lý expiry dựa trên server time và metadata. Nếu lệch NTP hoặc độ phân giải thời gian khác nhau, kết quả gần ranh giới có thể không chính xác tới từng millisecond. Test kiểm tra **xu hướng deadline** với sai số cho phép, không assert nanosecond.

### 12.2. Tại sao refresh lỗi thì không chấp nhận request?

`touch` có thể timeout sau khi server đã thực hiện. Với phiên đăng nhập, ví dụ chọn **fail closed**: không coi request hợp lệ khi việc kiểm tra/gia hạn chưa được xác nhận; trả lỗi availability để client retry có giới hạn. Không tự sinh session khác khi timeout.

`StorageUnavailable` là lỗi **chưa kiểm tra được**, khác `SessionRejected` là session thực sự không tồn tại, không hợp lệ hoặc đã hết hạn.

### 12.3. Race giữa read và touch

`findById` và `touch` là **hai KV operations**, không phải transaction. Nếu logout xóa key giữa hai bước, touch có thể trả `DocumentNotFoundException` và request phải bị từ chối. Nếu quản trị đổi `status=REVOKED` giữa hai bước mà không xóa key, một request đang chạy vẫn có thể touch; do đó revocation policy nghiêm ngặt cần kiểm tra authoritative source hoặc giao thức conditional mutation riêng.

### 12.4. `touch` không viết `lastActivityAt` vào JSON

Metadata expiry thay đổi không đồng nghĩa body có trường thời gian truy cập mới. Nếu cần audit từng request, dùng telemetry riêng hoặc cập nhật body có CAS và hiểu chi phí contention. Không suy TTL thực từ một JSON field không được cập nhật.

## 13. Controller thử nghiệm: chỉ được bật với profile `ttl-lab`

Controller sau **không kiểm tra mật khẩu** và không được triển khai như endpoint login thật. Nó chỉ mô phỏng trạng thái “đã xác thực” để tập trung học TTL. Ứng dụng production phải gọi `issueAfterSuccessfulAuthentication` sau xác thực qua Spring Security/IdP.

~~~java
package com.example.session;

import java.time.Instant;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@Profile("ttl-lab")
@RequestMapping("/lab/sessions")
public class LabSessionController {
    private final SessionService service;

    public LabSessionController(SessionService service) {
        this.service = service;
    }

    public record StartRequest(
        @NotBlank String userId
    ) {}
    public record StartResponse(
        String token,
        String userId,
        Instant expiresAt,
        Instant absoluteExpiresAt
    ) {}
    public record MeResponse(
        String userId,
        Instant expiresAt,
        Instant absoluteExpiresAt
    ) {}

    @PostMapping("/start")
    @ResponseStatus(HttpStatus.CREATED)
    public StartResponse start(
            @Valid @RequestBody StartRequest request) {
        var issued = service
            .issueAfterSuccessfulAuthentication(
                request.userId());
        return new StartResponse(
            issued.token(), issued.userId(),
            issued.initialExpiresAt(),
            issued.hardExpiresAt());
    }

    @GetMapping("/me")
    public MeResponse me(
            @RequestHeader("X-Lab-Session-Token")
            String rawToken) {
        var active = service.authenticateAndRenew(rawToken);
        return new MeResponse(
            active.userId(), active.renewedExpiresAt(),
            active.hardExpiresAt());
    }

    @PostMapping("/logout")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void logout(
            @RequestHeader("X-Lab-Session-Token")
            String rawToken) {
        service.logout(rawToken);
    }
}
~~~

### 13.1. Vì sao không dùng cookie ngay trong demo?

Header `X-Lab-Session-Token` giúp curl/Postman gửi token minh bạch khi học mà không phải dựng Spring Security/CSRF/cookie đầy đủ. **Không suy ra nên dùng header tùy ý trong production.**

Với browser thật, một lựa chọn thường gặp là opaque token trong cookie:

~~~http
Set-Cookie: SESSION=<opaque-token>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Cần cấu hình domain/path, CSRF, SameSite, absolute expiry, token rotation, session fixation prevention và authentication toàn diện. Không đặt token vào URL query, access log hoặc local storage tùy tiện.

### 13.2. Không cho người dùng tự nhận một `userId` khác

Lab giả định bất cứ `userId` nào cũng tạo được session để thử TTL. Production **tuyệt đối không** cho phép phát token chỉ dựa vào `userId` trong request body. Tài khoản phải đến từ principal đã xác thực; kiểm tra role, disable state, tenant và MFA tùy hệ thống.

## 14. Error handler: session hết hạn khác mất Data Service

~~~java
package com.example.session;

import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
@Profile("ttl-lab")
public class LabSessionErrorHandler {
    @ExceptionHandler(SessionService.SessionRejected.class)
    public ResponseEntity<ProblemDetail> rejected(
            SessionService.SessionRejected e) {
        return response(HttpStatus.UNAUTHORIZED,
            "SESSION_INVALID_OR_EXPIRED",
            "Phiên không hợp lệ hoặc đã hết hạn.");
    }

    @ExceptionHandler(SessionService.StorageUnavailable.class)
    public ResponseEntity<ProblemDetail> unavailable(
            SessionService.StorageUnavailable e) {
        return response(HttpStatus.SERVICE_UNAVAILABLE,
            "SESSION_BACKEND_UNAVAILABLE",
            "Chưa xác minh được phiên; hãy thử lại.");
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ProblemDetail> badInput(
            IllegalArgumentException e) {
        return response(HttpStatus.BAD_REQUEST,
            "SESSION_INPUT_INVALID", "Input không hợp lệ.");
    }

    private ResponseEntity<ProblemDetail> response(
            HttpStatus status, String code, String detail) {
        ProblemDetail body =
            ProblemDetail.forStatusAndDetail(status, detail);
        body.setProperty("code", code);
        return ResponseEntity.status(status).body(body);
    }
}
~~~

| Status | Khi nào? | Hướng xử lý |
|---|---|---|
| 201 | Khởi tạo session trong lab | Giữ token thử nghiệm an toàn |
| 200 | Valid session được gia hạn theo policy | Tiếp tục thao tác |
| 204 | Logout thành công hoặc token đã hết | Xóa token phía client |
| 400 | Input giả lập tạo session sai | Sửa request |
| 401 | Token sai/hết idle/hard deadline | Đăng nhập lại |
| 503 | Không xác minh/refresh được do lỗi cluster | Retry có giới hạn; không giả làm logout |

Không biến mọi `RuntimeException` của database thành 401. Couchbase timeout hoặc thiếu quyền đọc là một lỗi availability/configuration, không phải chứng minh user bị logout.

## 15. HTTP walkthrough với phiên 6 giây

### 15.1. Tạo session

~~~http
POST /lab/sessions/start HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{"userId":"user-lab-42"}
~~~

Trên profile `ttl-lab`, response mẫu:

~~~json
{
  "token": "<43 ký tự base64url ngẫu nhiên>",
  "userId": "user-lab-42",
  "expiresAt": "2026-11-25T03:00:06Z",
  "absoluteExpiresAt": "2026-11-25T03:00:20Z"
}
~~~

`expiresAt` được tính ở ứng dụng để minh họa, **không phải metadata readback từ server**. Nếu bucket/collection `maxTTL` cap nhỏ hơn 6 giây, thời hạn thực tế sẽ ngắn hơn.

### 15.2. Hoạt động và refresh

~~~http
GET /lab/sessions/me HTTP/1.1
Host: localhost:8080
X-Lab-Session-Token: <token thử nghiệm>
~~~

Kỳ vọng `200`, đúng `userId`, `expiresAt` gần `now+6s`. Sau khoảng 3 giây, gọi lại `/me` để gia hạn; đọc expiry metadata để xác nhận hạn **sau refresh tiến về phía tương lai**.

### 15.3. Không hoạt động quá idle timeout

Sau lần refresh cuối, không gọi `/me` trong hơn 6 giây cộng khoảng đệm. Tiếp theo gọi `/me`: kỳ vọng `401` vì document đã hết hạn. Không gọi `/me` trong lúc “chờ session expire”, bởi chính nó có thể gia hạn.

### 15.4. Logout

~~~http
POST /lab/sessions/logout HTTP/1.1
Host: localhost:8080
X-Lab-Session-Token: <token>
~~~

Kỳ vọng `204`. Một request `/me` với token đã logout sẽ nhận `401` sau khi remove thành công. Nếu remove timeout, service trả `503` thay vì tuyên bố token đã bị thu hồi chắc chắn.

## 16. Kiểm tra expiration metadata thực tế với `withExpiry`

Spring Data Repository chủ yếu trả body entity; expiry không tự hiện thành một field JSON. Java SDK hỗ trợ yêu cầu lấy metadata:

~~~java
import static com.couchbase.client.java.kv.GetOptions.getOptions;

import java.time.Instant;
import java.util.Optional;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.GetResult;

Collection collection = cluster
    .bucket("security_lab")
    .scope("auth")
    .collection("sessions");

String id = SessionTokenFactory.keyFor(rawSessionToken);
GetResult result = collection.get(
    id, getOptions().withExpiry(true));

Optional<Instant> metadataExpiry = result.expiryTime();
metadataExpiry.ifPresent(expiry ->
    System.out.println("Lab expiry: " + expiry));
~~~

`cluster` và `rawSessionToken` là biến giả định đã cấu hình trong test code; không log token thật.

### 16.1. Phân biệt hai tình huống Optional

- `expiryTime()` không có value không đồng nghĩa document đã expired; có thể document không có expiry hoặc metadata không được yêu cầu.
- Khi document đã expire, `collection.get(id)` thường trả `DocumentNotFoundException`. Không lấy `Optional.empty()` làm dấu hiệu logout.

### 16.2. Kiểm tra trong khoảng, không dùng nanosecond equality

Một assertion hợp lý so thời điểm expiry với khoảng gần `now+6s`, có tolerance cho scheduling/rounding. Không assert `expiry.equals(Instant.now().plusSeconds(6))` vì hai lần đọc đồng hồ khác thời điểm.

## 17. Java SDK: `touch` và `getAndTouch`

### 17.1. Làm mới TTL tương đối

~~~java
import java.time.Duration;
import com.couchbase.client.java.kv.MutationResult;

MutationResult mutation =
    collection.touch(id, Duration.ofSeconds(6));
~~~

`touch` chỉ cập nhật expiry của document đã tồn tại; **không hồi sinh** session đã bị xóa/expire.

### 17.2. Làm mới đến deadline tuyệt đối

~~~java
import java.time.Instant;

Instant nextExpiry = Instant.now().plusSeconds(6);
Instant hard = Instant.parse(
    sessionDocument.getAbsoluteExpiresAt());

if (nextExpiry.isAfter(hard)) {
    nextExpiry = hard;
}
collection.touch(id, nextExpiry);
~~~

Giả định `sessionDocument` đã được kiểm tra active/hard deadline trước đó. SDK overload với `Instant` tránh việc tự đổi epoch milliseconds sang giây và phù hợp giới hạn cố định.

### 17.3. Đọc và gia hạn cùng một KV operation

~~~java
import java.time.Duration;
import com.couchbase.client.java.kv.GetResult;

GetResult result =
    collection.getAndTouch(id, Duration.ofSeconds(6));

String userId =
    result.contentAsObject().getString("userId");
~~~

`getAndTouch` hữu ích khi mọi successful read đều **được phép** gia hạn. Nhưng nếu quyền/revocation/hard deadline cần được kiểm tra **trước refresh**, operation này có thể gia hạn trước khi code xem body. Main lab chọn hai bước read→validate→touch minh bạch.

### 17.4. Atomic get-and-touch không phải atomic authorization

`getAndTouch` gộp read/expiry update ở server, **không** gộp kiểm tra user disabled/role/tenant của ứng dụng. Bảo đảm revocation nghiêm ngặt vẫn cần thiết kế riêng.

## 18. `expiryExpression` đọc từ Spring property

Thay hardcode số giây, Spring Data hỗ trợ:

~~~yaml
app:
  session:
    idle-seconds: 6
~~~

~~~java
// Đây là PHƯƠNG ÁN THAY THẾ annotation ở mục 8.
@Document(
    expiryExpression = "${app.session.idle-seconds}",
    expiryUnit = java.util.concurrent.TimeUnit.SECONDS,
    touchOnRead = false
)
@Scope("auth")
@Collection("sessions")
public class SessionDocument {
    // Các fields như mục 8.
}
~~~

`expiryExpression` dùng Spring property placeholders, không phải chỗ để đặt mọi SpEL expression. Không khai báo đồng thời `expiry` và `expiryExpression`.

**Đổi config không sửa toàn bộ documents cũ**: TTL metadata của các session đã ghi trước đó chỉ thay khi có operation phù hợp. Cần kiểm thử migration giữa các policy, không suy “đổi YAML xong tất cả session có hạn mới”.

## 19. Replace/upsert có thể reset TTL nếu không cẩn thận

Một `replace` không đặt expiry hoặc preserve-expiry có thể khiến session mất expiry cũ/nhận default không mong muốn:

~~~java
// PHẢN VÍ DỤ nếu muốn giữ nguyên TTL:
collection.replace(id, updatedJson);
~~~

Để thay body nhưng giữ hạn metadata (Couchbase Server 7.0+ theo SDK docs):

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;

collection.replace(
    id, updatedJson,
    replaceOptions().preserveExpiry(true));
~~~

Kết hợp CAS khi có nhiều writers:

~~~java
var before = collection.get(
    id, getOptions().withExpiry(true));

collection.replace(
    id, updatedJson,
    replaceOptions()
        .cas(before.cas())
        .preserveExpiry(true)
);
~~~

### 19.1. Khi muốn refresh bằng replace

~~~java
collection.replace(
    id, updatedJson,
    replaceOptions()
        .cas(before.cas())
        .expiry(Duration.ofSeconds(6))
);
~~~

Đây là chính sách **refresh upon write**, khác giữ TTL. Nếu cần hard cap, đặt expiry theo `Instant` được giới hạn tương tự service. Không trộn `preserveExpiry(true)` với `expiry(...)` trong cùng operation rồi tự suy thứ tự ưu tiên.

### 19.2. CAS và annotation Spring Data

`@Version` đại diện CAS của document. Vì SDK `touch` là mutation metadata, CAS có thể thay so với entity Spring Data đã đọc; update tiếp theo cần CAS hiện hành. Không tự tăng version; hãy đọc lại hoặc thiết kế cùng một protocol mutation.

### 19.3. Tương tác giữa hai policy

Nếu entity `@Document(expiry=6)` nhưng SDK gọi `touch(id, Duration.ofSeconds(12))`, một lần `repository.save` sau đó có thể lại áp expiry 6 giây của mapping. Phải quy định **một chủ sở hữu policy TTL** để tránh lúc gia hạn, lúc rút ngắn khó đoán.

## 20. Khi nào có thể coi sliding TTL đã được kiểm chứng?

| Quan sát | Kết luận hợp lý | Không nên kết luận |
|---|---|---|
| `repository.save` success | Entity đã được ghi theo metadata hiệu lực | User đã được auth thật |
| `repository.findById` với touchOnRead=false | Đọc KV mà không cố ý refresh | Session không có request khác đang touch |
| `touch(id, Instant)` success | Metadata expiry được set theo server rules | Cookie/JWT tự thay |
| `getAndTouch` success | Read + refresh thành công ở KV | Đã validate authorization trước refresh |
| `findById` empty sau TTL | Session không còn truy cập được bằng key | Physical disk cleanup đã hoàn tất |
| `maxTTL` 4s, client xin 6s | Server có thể cap ở 4s | Tất cả session sống đủ 6s |
| `logout remove` success | Session document đã bị xóa | In-flight requests đã bị hủy |
| `findByQuery` không thấy row | GSI chưa có hoặc record không match | Auth session chắc chắn hết hạn |

## 21. Race và concurrency khi nhiều request cùng token

Hai tabs hoặc hai API instances có thể cùng đọc `ACTIVE` và tính hai deadlines khác nhau:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant KV as Couchbase KV
    A->>KV: FIND id
    B->>KV: FIND id
    KV-->>A: ACTIVE
    KV-->>B: ACTIVE
    A->>KV: TOUCH expiry=T+6
    B->>KV: TOUCH expiry=T+5
    Note over KV: Lệnh đến sau có thể rút ngắn TTL
~~~

`touch` không điều kiện có thể **rút ngắn expiry** nếu request chậm hơn tính deadline cũ nhưng chạm KV sau. Khi cần invariant “expiry không bao giờ giảm”:

- Dùng protocol conditional update/CAS có kiểm tra expiry hiện hành và retry bounded.
- Hoặc chấp nhận sai số nhỏ được định nghĩa rõ trong SLO của session phổ thông.
- Có thể giảm số touches bằng cách chỉ refresh gần ngưỡng.
- Vẫn enforce hard cap bất kể request concurrency.

### 21.1. Race với logout/revocation

Nếu logout xóa document trước touch, touch trả not-found. Nếu logout xóa sau touch, document lại bị xóa. Nhưng nếu revocation chỉ là một update body và một request đọc trạng thái cũ trước update, việc authorize/touch có thể chấp nhận quyền quá cũ trong cửa sổ race. Session nhạy cảm cần một policy revocation mạnh hơn, không suy rằng TTL đã giải quyết race.

## 22. Phân loại lỗi trong bài thực hành

| Tình huống | Dấu hiệu | Cách xử lý |
|---|---|---|
| Token sai hình thức | Không match regex 43 ký tự | 401, không query Couchbase |
| Session hết idle | KV missing/expired | 401, đăng nhập lại |
| Qua hard deadline | Body `absoluteExpiresAt` trong quá khứ | 401, không touch |
| Đã logout | Key bị remove | 401 |
| Read Data Service timeout | Không xác minh body | 503, không coi đã logout |
| Touch timeout | Không biết mutation metadata đã hoàn tất | Fail closed request, retry có hạn |
| Bucket/collection maxTTL ngắn | Hạn thực tế thấp hơn code | Kiểm tra config/metadata |
| App clock lệch | Hard cap lệch với server | Đồng bộ NTP, tăng test margin |
| SQL++ query stale | Index chưa bắt kịp | Dùng KV ID cho auth |
| Replace quên preserve expiry | TTL bị reset | Dùng explicit expiry/preserve |
| Two requests touch gần nhau | Hạn cuối có thể lùi | Đánh giá monotonic protocol |
| User bị disable nhưng session còn ACTIVE | Business authorization khác | Kiểm tra authoritative user state |

## 23. Chiến lược kiểm thử: phải dùng TTL thật của server

Một test thuần Java có `Clock.fixed` chỉ kiểm tra logic so sánh thời gian trong service; **nó không khiến Couchbase expiration chạy nhanh hơn**. Để chứng minh TTL, cần integration test trên collection thật.

| Nhóm test | Cần Couchbase? | Điều kiểm tra |
|---|---|---|
| Sinh token và hash ID | Không | Token 43 ký tự base64url, deterministic SHA-256 ID |
| Hàm `min(idle, hard)` | Không | Hạn không vượt absolute cap |
| Mapping `@Document(expiry=6)` | Có | Document được tạo với expiry metadata |
| `findById` touchOnRead=false | Có | Không gia hạn chỉ vì đọc |
| SDK `touch(id, Instant)` | Có | Expiry metadata tiến tới tương lai theo policy |
| SDK `getAndTouch` | Có | Read + refresh ở cùng KV operation |
| Logout | Có | Remove và không tái sử dụng token |
| `maxTTL` thấp hơn code | Có, cấu hình lab được phép | Server cap expiry |
| Data node timeout | Lab có orchestrator/fault proxy | Phân biệt 401 với 503 |
| Spring Security/login thật | Cần môi trường auth riêng | Không thuộc demo phát token giả |

### 23.1. Những lưu ý trước integration test

1. Dùng bucket `security_lab`, scope `auth`, collection `sessions` **riêng và dữ liệu giả**.
2. Tài khoản runtime có quyền KV phù hợp.
3. Ghi chú bucket/collection `maxTTL` và clock drift.
4. Bật test chỉ khi `RUN_CB_TTL_IT=true`; không chạy vô tình với production.
5. Không query SQL++ để xác nhận document đã expire; dùng KV theo ID.
6. Chạy test timing với khoảng đệm, không assert chính xác milliseconds.
7. Tránh cho những health probes/test helpers gọi `authenticateAndRenew` trong pha chờ expiration; chính chúng sẽ refresh TTL.
8. Không log token dùng trong test report; chỉ lưu ID hash đã che bớt khi cần.

## 24. Integration test: TTL hết hạn nếu không có hoạt động

~~~java
package com.example.session;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@EnabledIfEnvironmentVariable(
    named = "RUN_CB_TTL_IT",
    matches = "true"
)
class SessionTtlIntegrationTest {

    @Autowired SessionService service;
    @Autowired SessionRepository repository;

    @Test
    void sessionExpiresAfterIdleWithoutRenewal()
            throws InterruptedException {
        var issued = service
            .issueAfterSuccessfulAuthentication("lab-user-001");

        String key = SessionTokenFactory.keyFor(issued.token());

        try {
            assertTrue(repository.findById(key).isPresent());
            assertTrue(
                service.expiryForLab(issued.token()).isPresent());

            // @Document(expiry=6), không có touch.
            // 8 giây có buffer cho các độ trễ lab.
            Thread.sleep(8_000);

            assertTrue(repository.findById(key).isEmpty());
            assertThrows(
                SessionService.SessionRejected.class,
                () -> service.authenticateAndRenew(
                    issued.token())
            );
        } finally {
            service.logout(issued.token());
        }
    }
}
~~~

Kết quả kỳ vọng: document có TTL khi mới insert, nhưng sau khoảng thời gian lớn hơn idle timeout, KV không còn trả document theo key. Lệnh `repository.findById` không reset TTL vì `touchOnRead=false`.

### 24.1. Không dùng sleep ngắn ngay sát 6 giây

Một test kiểu `Thread.sleep(6_001)` rồi assert may rơi vào ranh giới do latency, scheduling, clock granularity. Trong môi trường CI dùng thời gian thật, chọn khoảng đệm hoặc poll bounded tới khi hết hạn. **Không sửa timeout sản phẩm chỉ để che flaky test**.

### 24.2. Cleanup sau khi đã expired

`logout` trong khối `finally` idempotent khi document đã expire. Nó tránh để lại session giả nếu một assertion thất bại sớm. Chạy test trên bucket thử nghiệm riêng để cleanup không xóa dữ liệu của người khác.

## 25. Integration test: refresh phải kéo dài session qua hạn cũ

Cần so hai mốc **expiry metadata trước/sau**; kiểm tra theo body `issuedAt` là chưa đủ.

~~~java
package com.example.session;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@EnabledIfEnvironmentVariable(
    named = "RUN_CB_TTL_IT", matches = "true"
)
class SessionRefreshIntegrationTest {

    @Autowired SessionService service;
    @Autowired SessionRepository repository;

    @Test
    void activityRenewsExpiryBeyondOriginalDeadline()
            throws InterruptedException {
        var issued = service
            .issueAfterSuccessfulAuthentication("lab-user-002");
        String id = SessionTokenFactory.keyFor(issued.token());

        try {
            Instant original =
                service.expiryForLab(issued.token())
                    .orElseThrow();

            Thread.sleep(2_500);

            // Service: findById + validate + touch(Instant).
            var active = service.authenticateAndRenew(
                issued.token());
            assertEquals("lab-user-002", active.userId());

            Instant renewed =
                service.expiryForLab(issued.token())
                    .orElseThrow();

            assertTrue(renewed.isAfter(original));
            assertFalse(
                renewed.isAfter(active.hardExpiresAt()));

            // Đợi tới sau hạn CŨ, nhưng vẫn trước
            // hạn MỚI. KHÔNG gọi /me lúc đang đợi.
            sleepUntil(original.plusMillis(600));
            assertTrue(repository.findById(id).isPresent());

            // Đợi qua hạn MỚI, không tiếp tục touch.
            sleepUntil(renewed.plusSeconds(2));
            assertTrue(repository.findById(id).isEmpty());
        } finally {
            service.logout(issued.token());
        }
    }

    private static void sleepUntil(Instant target)
            throws InterruptedException {
        long delay = Math.max(
            0L, Duration.between(
                Instant.now(), target).toMillis()
        );
        Thread.sleep(delay);
    }
}
~~~

**Đây là test timing cần môi trường ổn định**. Nếu load/clock skew lớn, `original.plusMillis(600)` có thể vượt hạn mới; khi đó test nên skip/retry test case trên môi trường phù hợp hoặc thiết kế poll theo các khoảng guard lớn hơn, **không** khẳng định implementation sai chỉ từ một lần timing jitter. Trên lab chuyên biệt có thể tăng TTL thực hành lên 10–15 giây để có cửa sổ an toàn hơn.

### 25.1. Tránh test phá hiệu lực của chính mình

Nếu entity bật `touchOnRead=true` thì `repository.findById(id)` ở cuối test có thể refresh khi kiểm tra. Bài này cố ý dùng `touchOnRead=false`; đối với automatic mode, cần dùng SDK `get(... withExpiry(true))` để quan sát **nhưng nó cũng không tự touch**, hoặc tách test đọc cuối sau khi đã chắc chắn hết hạn.

### 25.2. Dữ liệu trong test không có GSI

`findById(id)` truy vấn theo key KV, không cần Query Service. Nếu bạn chạy `findByUserId` thay cho KV get, index lag có thể khiến kết luận sai. Dùng document ID từ token hash cho mọi TTL assertions.

## 26. Kiểm tra hard deadline mà không phải chờ đủ 20 giây

Trong lab, có thể tạo session rồi **đổi field nghiệp vụ `absoluteExpiresAt`** bằng một replace hợp lệ để giả lập phiên có hard cap gần. Sau đó kiểm tra service từ chối dù KV vẫn còn document theo TTL.

~~~java
// Ví dụ bên trong @SpringBootTest có
// @Autowired SessionService service;
// @Autowired SessionRepository repository;

var issued = service.issueAfterSuccessfulAuthentication(
    "lab-user-hard");

String id = SessionTokenFactory.keyFor(issued.token());

var document = repository.findById(id).orElseThrow();
document.setAbsoluteExpiresAt(
    java.time.Instant.now()
        .plusSeconds(2).toString());

// Entity đã có @Version -> update qua CAS; có thể
// reset TTL về 6 giây theo @Document metadata.
repository.save(document);

Thread.sleep(2_500);

assertThrows(
    SessionService.SessionRejected.class,
    () -> service.authenticateAndRenew(issued.token())
);

// Cleanup riêng sau assertions.
service.logout(issued.token());
~~~

Bài test mô phỏng trạng thái đã sát hard cap; nó **không chứng minh** server tự hiểu `absoluteExpiresAt`. Chính service phải so thời gian và từ chối. Một lần `get(id)` vẫn có thể thấy body trong cửa sổ TTL, nhưng đó không phải quyền truy cập còn hợp lệ.

### 26.1. Hard deadline không được di chuyển theo refresh

`absoluteExpiresAt` được set từ `issuedAt + HARD`. Chỉ idle deadline trượt; không cập nhật hard deadline theo `lastRequestAt`. Nếu mỗi touch lại tăng hard deadline, bạn đã đánh mất absolute lifetime.

## 27. Test `touchOnRead=true` tách biệt

Để kiểm thử auto refresh của Spring Data:

1. Dùng **một bản entity alternative** có `@Document(expiry=6, touchOnRead=true)`.
2. Tạo session và đọc expiry metadata bằng SDK `getOptions().withExpiry(true)`.
3. Chờ khoảng 2–3 giây.
4. Gọi `repository.findById(id)`.
5. Đọc expiry metadata lần nữa và xác minh hạn đã tiến về phía tương lai.
6. Chờ qua hạn cũ nhưng chưa qua hạn mới và xác minh document còn.
7. Không tự gọi `repository.findById` nhiều lần trong giai đoạn chờ không hoạt động vì sẽ vô tình gia hạn.

**Chỉ dùng một phiên bản `SessionDocument` trong cùng project.** Không khai báo hai classes cùng package/cùng tên hoặc dựa vào việc annotation có thể đổi runtime bằng biến tùy ý.

### 27.1. Vì sao không dùng automatic mode cho hard cap?

`touchOnRead=true` không tự đọc `absoluteExpiresAt` rồi so `now` trước khi touch. Do đó một request direct read có thể kéo dài expiry metadata ngay cả khi service sau đó xác định session cần bị từ chối. Nếu hard cap là invariant bắt buộc, dùng explicit policy hoặc một thiết kế bảo vệ tương đương.

## 28. Thực hành kiểm tra `maxTTL` ở collection

Đây là một thí nghiệm cấu hình **chỉ do DBA/SRE thực hiện trên lab**:

~~~text
Case A:
  Bucket maxTTL: 0
  Collection maxTTL: 0 hoặc không set
  Entity expiry: 6 giây
  Kỳ vọng: metadata khoảng 6 giây

Case B:
  Collection maxTTL: 4 giây
  Entity expiry: 6 giây
  Kỳ vọng: server không cho expiry vượt 4 giây

Case C:
  SDK touch xin 10 giây trên collection maxTTL 4
  Kỳ vọng: hạn hiệu lực vẫn bị giới hạn bởi policy
~~~

Đừng thay `maxTTL` trong production để minh họa. Trên Server hiện hành, collection `maxTTL=0` thường thừa hưởng bucket maxTTL không zero; ngoại lệ/disable inheritance cần theo đúng config semantics. Test report ghi **bucket, collection, actual server version và metadata sau write**.

### 28.1. Kiểm tra cả create và update

Couchbase có quy tắc về default/maxTTL khi create hoặc mutate document. Một `replace` không dùng preserveExpiry có thể nhận lại default TTL. Nếu test chỉ kiểm tra insert lần đầu mà không kiểm tra update, có thể bỏ sót việc phiên bị kéo dài hoặc vô tình thành non-expiring.

### 28.2. Đừng dùng TTL âm tùy tiện

Các giá trị đặc biệt ở bucket/collection không phải TTL seconds thông thường; phải xem docs deployment. Với document level, hãy dùng `Duration`/`Instant` hợp lệ và tránh âm/zero khi mục tiêu là phiên có thời hạn.

## 29. Logout và session revocation: test riêng

| Thao tác | Điều kiện | Kỳ vọng |
|---|---|---|
| Logout token hợp lệ | KV có session | 204, key bị xóa |
| Logout hai lần | Lần hai key không còn | Có thể tiếp tục 204 |
| `GET /me` sau logout | Token cũ | 401 |
| Logout khi Data Service timeout | Không rõ remove hoàn tất | 503, không tự hứa đã revoke |
| User bị disabled nhưng session còn | Cần kiểm tra user authority | Từ chối theo policy sản phẩm |
| Đổi mật khẩu/MFA | Có thể buộc revoke toàn bộ sessions | Thiết kế index/ledger theo user hoặc version token |

### 29.1. Session revocation theo người dùng

Bài thực hành có document ID theo token, không có index `userId` cho “logout tất cả thiết bị”. Để revoke mọi phiên của một user, có thể cân nhắc:

- Duy trì bảng session registry/index theo user với consistency phù hợp.
- Gắn `sessionVersion`/`tokenGeneration` với user authority và kiểm tra tại request.
- Hủy các token được biết, nhưng đừng dựa vào SQL++ index lag để tin đã revoke tất cả.
- Xác định behavior khi revocation diễn ra đồng thời với refresh.

Đây là **bài toán authorization**, không được giải quyết chỉ bằng cách đổi expiry 6 giây thành 5 giây.

## 30. Bảo mật phiên và cookie ngoài phạm vi demo

Một mô hình session stateful ở production cần thêm:

1. **Auth thật**: password hashing an toàn, MFA/IdP, rate limiting, lockout phù hợp.
2. **Token bảo mật**: random secret đủ entropy; không đặt username/email trong token.
3. **Transport**: HTTPS, `Secure` cookie, `HttpOnly`, `SameSite` + CSRF defense theo threat model.
4. **Session fixation**: phát/rotate token sau login và thay đổi đặc quyền.
5. **Authorization**: role/tenant/user status được kiểm tra đáng tin tại mỗi request cần thiết.
6. **Logout/revocation**: remove hoặc cơ chế không chấp nhận token cũ, giải quyết concurrent requests.
7. **Absolute limit**: phiên hoạt động liên tục không sống mãi.
8. **Cookie lifetime**: tránh cookie sống lâu hơn session authority mà caller không xử lý 401.
9. **Telemetry**: không log raw token; quan sát hashed identifier có kiểm soát.
10. **Data protection**: session body ít PII, RBAC keyspace, encryption và backup policy.
11. **Deployment safeguards**: endpoint `/lab/sessions/start` không được đi vào production artifact hoặc phải bị vô hiệu hóa hoàn toàn ngoài profile test; một profile bị bật nhầm vẫn là rủi ro cần kiểm soát qua CI/deployment.
12. **User-visible UX**: idle warning, reauthentication, thông báo khi session hết hạn; không lặng lẽ tạo token mới từ token đã expire.

### 30.1. Phân biệt JWT và stateful opaque session

- **Opaque session**: token chỉ là reference, server tra Couchbase state ở mỗi request cần auth, TTL/remove có tác dụng trực tiếp.
- **Self-contained JWT**: JWT đã ký có claim `exp` và được validate stateless. Xóa một Couchbase session document **không tự làm JWT đã phát vô hiệu**, trừ khi resource server cũng kiểm tra revocation/session state.

Bài học sử dụng opaque token để Couchbase expiry là một phần của access decision.

## 31. Observability và production operations

| Metric/Log | Mục đích |
|---|---|
| Session issued count | Tốc độ tạo sessions, dấu hiệu login spam |
| Session validation success/rejected | Session acceptance và 401 bất thường |
| Idle timeout count | UX/chính sách quá ngắn? |
| Hard cap rejection count | Phiên đạt lifetime tối đa |
| KV touch latency p95/p99 | Chi phí refresh trong request path |
| `DocumentNotFound` after touch | Race expiry/logout |
| Storage unavailable 503 | Phân biệt cụm lỗi với user logout |
| Actual expiry metadata sample | TTL bị `maxTTL` cap hoặc code reset? |
| Retry/cancellation rate | Có request chưa rõ kết quả không? |
| Per-user/session request rate | Detect abuse/token theft |
| Clock skew/NTP status | Giải thích lỗi sát ranh giới |
| Replica/Data Service health | Availability cho session reads |

Tên metric tùy ứng dụng; **không** khẳng định chúng được Couchbase Server xuất mặc định. Chỉ dùng aggregate metrics/redacted session ID, không đẩy bearer token vào telemetry.

### 31.1. Kết quả đúng sau incident không chỉ là HTTP 200

Sau node failover, cần kiểm tra session KV read/touch, replica health, SDK timeout classification và policy revocation. Nếu read timeout, không tự ghi hàng loạt users thành logged out; nếu write timeout, cũng không mở quyền mà không xác minh.

## 32. Case study A — `findById` “vô tình” giữ session sống mãi

**Bối cảnh:** entity bật `touchOnRead=true`, health/debug endpoint mỗi 3 giây gọi `repository.findById` để “kiểm tra session còn không”.

**Kết quả:** mỗi lần đọc lại gia hạn TTL 6 giây. Phiên không idle-expire theo mong muốn dù người dùng không thao tác.

**Cách sửa:** không dùng refresh-on-read cho endpoint quan sát. Tách raw SDK `get(...withExpiry(true))` trong công cụ lab được ủy quyền; ở production chỉ refresh trên hoạt động hợp lệ. Nếu yêu cầu hard cap, enforce trước touch hoặc thiết kế theo chính sách phù hợp.

## 33. Case study B — Update profile làm session mất TTL

**Bối cảnh:** session ban đầu có TTL, nhưng background job `replace(id, newJson)` mà không preserve expiry.

**Kết quả:** tùy policy bucket/collection, expiry có thể về zero hoặc default ngoài ý định, khiến session sống quá lâu/ngắn hơn dự kiến.

**Cách sửa:** với Server hỗ trợ, dùng `replaceOptions().preserveExpiry(true)` nếu không muốn thay hạn. Nếu muốn refresh, đặt `expiry(Instant)` theo hard cap và kiểm chứng metadata. Không trộn các code paths có TTL policy khác nhau.

## 34. Case study C — App xin 30 phút nhưng session chết sau 5 phút

**Bối cảnh:** Java code dùng `touch(Duration.ofMinutes(30))`, nhưng collection `maxTTL` được đặt 300 giây.

**Kết quả:** Couchbase cap expiration theo collection policy, session hết sớm hơn client dự tính.

**Cách sửa:** ghi lại bucket/collection `maxTTL`, so với business idle policy, dùng `getOptions().withExpiry(true)` để xác minh server metadata. Không vội tăng timeout HTTP hoặc thêm retry; đó không phải nguyên nhân.

## 35. Case study D — Logout đồng thời với một request gia hạn

**Bối cảnh:** tab A gọi logout, tab B đồng thời gửi `/me` với cùng token. Tab B đã đọc ACTIVE trước khi A xóa document.

**Kết quả:** nếu remove xảy ra trước touch, touch trả not-found; nếu touch hoàn tất trước remove, logout vẫn xóa key. Nhưng một request đã được service cho phép **trước** logout có thể đang xử lý tiếp; không có cơ chế hủy tự động mọi in-flight request.

**Cách sửa:** định nghĩa revocation semantics, dùng authoritative user state/transaction hoặc request-level checks cho thao tác nhạy cảm, không suy từ `touch` success rằng logout đã bị vô hiệu hóa.

## 36. Ma trận kiểm thử chấp nhận

| ID | Tình huống | Assertion chính |
|---|---|---|
| T01 | Token mới | Random 256 bit, base64url không padding |
| T02 | Hash token | Cùng token -> cùng document ID, khác token -> ID khác |
| T03 | Tạo session | Repository save, KV key tồn tại |
| T04 | Expiry metadata ban đầu | Có hạn gần `now+6s` khi không có cap |
| T05 | Read không touch | TTL tiếp tục giảm |
| T06 | Read auto `touchOnRead=true` | Hạn tăng sau direct read |
| T07 | Explicit renew | Hạn tăng sau validate + SDK touch |
| T08 | Không hoạt động | KV missing/401 sau idle TTL |
| T09 | Hard deadline | Bị từ chối dù có hoạt động liên tục |
| T10 | Logout | Token cũ không được chấp nhận |
| T11 | Logout lần hai | Idempotent behavior theo API contract |
| T12 | Expiry metadata | `getOptions().withExpiry(true)` có dữ liệu |
| T13 | Missing metadata | Không coi `Optional.empty()` là document expired |
| T14 | Bucket/collection maxTTL thấp | Hạn server bị cap |
| T15 | Replace không preserve | Nhận diện nguy cơ reset expiry |
| T16 | Replace preserveExpiry | Giữ hạn cũ theo server support |
| T17 | Concurrent touch | Đánh giá race rút ngắn TTL |
| T18 | Read timeout | 503, không ép 401 |
| T19 | Touch timeout | Fail closed, không giả logout |
| T20 | Session revoked/disabled | Từ chối theo authoritative policy |
| T21 | SQL++ index lag | Dùng KV, không dùng GSI làm auth |
| T22 | Browser cookie security | Secure/HttpOnly/SameSite/CSRF theo threat model |
| T23 | Lab controller off ngoài profile | Không thể phát token giả trên production |
| T24 | Reactive cancellation | Không tự kết luận touch/server đã rollback |

## 37. Bài tập mở rộng

### Bài A — fixed versus sliding

Viết lại lab để `touchOnRead=false` và **không** gọi SDK touch. Hãy giải thích vì sao người dùng hoạt động ở giây 3 vẫn hết phiên ở giây 6.

### Bài B — metadata expiry

Tạo session, dùng `getOptions().withExpiry(true)`, ghi lại expiry. Vì sao `SessionDocument` không có field TTL metadata mặc định?

### Bài C — hard cap

Với idle timeout 10 phút và absolute lifetime 8 giờ, một user hoạt động liên tục 9 giờ có còn session hợp lệ không? Tính `min(now+idle, issuedAt+8h)` và nơi kiểm tra.

### Bài D — touch và cookie

Gọi `collection.touch(id, Duration.ofMinutes(10))` có tự thay `Set-Cookie` ở browser không? Khi nào cần cấp cookie mới?

### Bài E — read that refreshes

Bật `@Document(touchOnRead=true)` và tạo debug endpoint đọc session mỗi 30 giây. Nguy cơ gì nếu idle timeout 1 phút?

### Bài F — maxTTL

Entity đặt 30 phút, collection maxTTL 5 phút. Hạn thực tế là bao nhiêu và đọc metadata bằng API nào để xác minh?

### Bài G — replace mutation

Update `status` trong body bằng SDK `replace`. Nếu không đặt preserveExpiry, chuyện gì có thể xảy ra? Viết mã có CAS và `preserveExpiry(true)`.

### Bài H — logout race

A logout, B đồng thời refresh token. Chỉ dùng `touch` có tạo key lại sau remove được không? Có hủy được mọi request in-flight không?

### Bài I — app clock versus server clock

Một instance lệch NTP +20 giây so với server. Hard deadline sẽ bị tác động thế nào? Nêu cách giới hạn rủi ro.

### Bài J — security

Vì sao endpoint POST `/lab/sessions/start` không được triển khai trong production dù có `@Profile`? Cần authentication, authorization và deployment controls nào?

### Bài K — TTL và Query

SQL++ không thấy một session mới nhưng KV get thấy. Có thể từ chối token dựa trên câu SQL++ `NOT_BOUNDED` không? Vì sao?

### Bài L — reactive

Thay `Collection.touch` bằng reactive `collection.reactive().touch(id, expiry)` trả `Mono`. Đảm bảo không gọi `block()` trong event loop và kiểm soát timeout/cancellation như thế nào?

### Bài M — refresh threshold

Thiết kế chính sách chỉ refresh khi remaining TTL dưới 50% idle window. Đo lợi ích giảm writes và giải thích race/absolute cap.

### Bài N — durability và failover

Một bucket không replica vẫn tạo và expire sessions được. Vì sao điều đó không bảo đảm session sống sót khi Data node duy nhất bị mất vĩnh viễn? Khi nào cần replica/durability?

## 38. Checklist nghiệm thu production-oriented

- [ ] Có bucket/scope/collection riêng và RBAC tối thiểu cho session data.
- [ ] Code lab chỉ chạy ở profile/môi trường được cấp phép, không có login giả ở production.
- [ ] Token ngẫu nhiên đủ entropy, không có PII/password/secret trong document key.
- [ ] Session token không nằm trong URL/access logs, có policy cookie/TLS rõ ràng.
- [ ] Session JSON có user ID, issuedAt và absoluteExpiresAt để kiểm tra hạn cứng.
- [ ] Entity được mapping đúng `@Id`, `@Scope`, `@Collection` và expiry.
- [ ] Biết rõ `touchOnRead` đang bật hay tắt và những direct reads có refresh.
- [ ] TTL metadata được kiểm tra qua `getOptions().withExpiry(true)`.
- [ ] Idle refresh chỉ xảy ra sau validation/authorization phù hợp.
- [ ] Không gia hạn sau hard deadline.
- [ ] Không cho request qua khi không thể xác minh touch/auth state.
- [ ] Phân biệt 401 expired với 503 backend unavailable.
- [ ] Logout thu hồi token và được kiểm thử nhiều lần.
- [ ] Biết race giữa read/touch, touch/touch và touch/logout.
- [ ] Có policy với user disabled, role change, session fixation và token rotation.
- [ ] Không dùng SQL++/GSI để quyết định token session theo ID.
- [ ] Kiểm tra bucket/collection `maxTTL` và trường hợp hạn bị cap.
- [ ] Update body không vô tình xóa/đặt lại TTL; dùng preserveExpiry khi phù hợp.
- [ ] Có CAS cho những cập nhật nội dung cạnh tranh.
- [ ] Integration tests có timing buffer, chạy chỉ trên lab và có cleanup.
- [ ] Có metrics p95/p99 KV read/touch, 401/503, expiry drift và anomaly.
- [ ] Không coi TTL là backup, durability hay JWT revocation.
- [ ] NTP/clock drift được giám sát và có hard cap.
- [ ] Có SLO/idle policy rõ, chấp nhận hoặc xử lý race TTL monotonic.
- [ ] Có quy trình rollback khi policy expiry thay đổi.

## 39. Tổng kết

**TTL của Couchbase là expiration metadata của một KV document**, không phải một trường JSON chỉ cần đặt `expiresAt` là xong. Spring Data Couchbase hỗ trợ `@Document(expiry, expiryUnit, touchOnRead)` để đặt TTL và có thể làm mới khi đọc trực tiếp. Java SDK cung cấp `getOptions().withExpiry(true)` để quan sát hạn server cùng `touch`/`getAndTouch` để gia hạn.

Trong bài thực hành, **Repository lưu và đọc session**, còn **SDK touch** được gọi **sau khi kiểm tra ACTIVE và absolute deadline**, với hạn mới bằng `min(now+idleTimeout, hardExpiresAt)`. Cách này cho thấy khác biệt giữa read, authorized activity và refresh policy. `@Document(touchOnRead=true)` là lựa chọn ngắn gọn nhưng có thể gia hạn cả trên những direct reads chưa được service đánh giá quyền, và không tự giới hạn absolute lifetime.

Một triển khai session thực tế cần thêm token bảo mật, login thật, authorization, revocation, CSRF/cookie policy, lưu ý `maxTTL`, `preserveExpiry`, CAS, clock skew, concurrency và observability. **Một lần touch thành công không đồng nghĩa user có quyền mãi mãi; một lần timeout không đồng nghĩa session đã hết hạn.**

## Tài liệu tham khảo chính thức

1. [Couchbase Server — Expiration](https://docs.couchbase.com/server/current/learn/data/expiration.html): cơ chế TTL, bucket/collection `maxTTL`, giới hạn và expiry behavior.
2. [Couchbase Server — Manage Expiration](https://docs.couchbase.com/server/current/manage/manage-expiration.html): cấu hình expiration và quản lý time-to-live.
3. [Spring Data Couchbase — @Document API](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/core/mapping/Document.html): `expiry`, `expiryUnit`, `expiryExpression`, `touchOnRead`.
4. [Spring Data Couchbase — @Expiry API](https://docs.spring.io/spring-data/couchbase/docs/current/api/org/springframework/data/couchbase/core/mapping/Expiry.html): giá trị expiry và cấu hình property placeholder.
5. [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): `expiry(Duration/Instant)`, `getAndTouch`, `withExpiry` và `preserveExpiry`.
6. [Couchbase Java SDK — Collection API](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/Collection.html): `touch`, `getAndTouch` và `get`.
7. [Couchbase Java SDK — GetOptions API](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/kv/GetOptions.html): `withExpiry(true)` và đọc expiry metadata.
8. [Spring Data Couchbase — Repository](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): CRUD theo key ID qua Repository.
9. [Spring Boot — NoSQL Couchbase Support](https://docs.spring.io/spring-boot/reference/data/nosql.html): cấu hình `spring.couchbase` và bucket.
10. [Couchbase Java SDK — Error Handling](https://docs.couchbase.com/java-sdk/current/howtos/error-handling.html): timeout/retry classification cần thiết cho session refresh.

**Giới hạn STEP 4:** Bài cung cấp mã hướng dẫn và kịch bản để người học triển khai trên cluster lab. Chưa build project Java, chạy integration tests hoặc tiến hành lỗi node thật trong bước soạn. Hãy khóa phiên bản Spring Boot/Spring Data/SDK/Server phù hợp và chạy Content QA chuyên môn của STEP 6 trước khi đưa mã vào sản phẩm.



