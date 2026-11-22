# Dọn authorization hết hạn, backup và khôi phục dữ liệu

Spring Authorization Server lưu authorization, token và consent trong cơ sở dữ liệu khi ứng dụng dùng JDBC persistence. Theo thời gian, bảng oauth2_authorization có thể tích lũy các bản ghi chứa authorization code, access token, refresh token, ID Token, device code hoặc user code đã hết hạn. Nếu không có retention policy, dữ liệu tăng liên tục, backup lớn hơn và truy vấn vận hành khó dự đoán hơn.

Dọn dữ liệu phải hiểu đúng cấu trúc lưu trữ: **một hàng oauth2_authorization có thể chứa nhiều token thuộc cùng một authorization**. Access token hết hạn không có nghĩa refresh token cũng hết hạn; authorization code hết hạn không có nghĩa access token được phát sau đó đã hết hạn. Xóa hàng chỉ dựa vào một cột expires_at có thể làm mất token còn hiệu lực hoặc làm hỏng khả năng refresh.

Bên cạnh cleanup, Authorization Server cần backup nhất quán cả dữ liệu JDBC, cấu hình và khóa ký. Khôi phục một database cũ mà thiếu signing keys, client registrations hoặc thông tin revocation có thể khiến issuer không xác minh được token, client không hoạt động, hoặc làm token đã bị thu hồi xuất hiện trở lại.

Bài học thuộc chương **Lưu trữ JDBC** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, tập trung vào thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.

Sau bài học, bạn có thể:

- Mô tả các bảng JDBC quan trọng và quan hệ giữa authorization, consent và registered client.
- Phân biệt thời hạn của từng token được lưu trong một authorization.
- Thiết kế cleanup an toàn theo từng token và theo toàn bộ authorization.
- Dùng retention grace period, batch delete, transaction và SKIP LOCKED.
- Tránh xóa authorization còn refresh token hoặc token khác đang hoạt động.
- Lập chính sách lưu trữ consent, registered client và audit độc lập với token cleanup.
- Backup database nhất quán, WAL/PITR, signing keys, secrets và cấu hình issuer.
- Khôi phục vào môi trường cô lập, xác minh dữ liệu và kiểm soát rủi ro rollback revocation.
- Thực hành kiểm thử cleanup, backup/restore và disaster recovery.

## 1. JDBC persistence lưu những dữ liệu nào?

Spring Authorization Server cung cấp các JDBC service chính để lưu trữ:

| Service | Bảng mặc định | Dữ liệu |
| --- | --- | --- |
| JdbcRegisteredClientRepository | oauth2_registered_client | Client ID, secret đã encode, redirect URI, grant types, scopes, authentication methods và client settings. |
| JdbcOAuth2AuthorizationService | oauth2_authorization | Authorization, principal, attributes và các token liên quan. |
| JdbcOAuth2AuthorizationConsentService | oauth2_authorization_consent | Consent/authorities mà người dùng đã chấp thuận cho client. |

Các service này làm việc trên schema JDBC được Spring Authorization Server cung cấp. Trong production, schema thường được quản lý bằng Flyway, Liquibase hoặc migration tool tương đương. Dùng schema đúng phiên bản dependency; không tự ý bỏ cột hoặc đổi kiểu dữ liệu mà row mapper/converter đang cần.

### 1.1. Bảng oauth2_authorization

Bảng oauth2_authorization có một hàng cho một authorization. Tùy grant type và trạng thái flow, hàng đó có thể lưu:

- authorization code;
- access token;
- OIDC ID Token;
- refresh token;
- user code;
- device code;
- thời điểm phát hành, hết hạn và metadata của từng token;
- principal name, client registration ID, grant type, authorized scopes và attributes.

Các cột token thường có cặp thời gian riêng, ví dụ access_token_issued_at, access_token_expires_at, refresh_token_issued_at và refresh_token_expires_at. Token không được dùng trong flow có thể có các cột tương ứng là NULL.

### 1.2. Một authorization không đồng nghĩa một token

Ví dụ Authorization Code flow:

~~~mermaid
flowchart TD
    A["oauth2_authorization row"] --> C["Authorization Code"]
    A --> AT["Access Token"]
    A --> RT["Refresh Token"]
    A --> IDT["OIDC ID Token"]
    C --> CE["Code hết hạn sau vài phút"]
    AT --> AE["Access Token hết hạn"]
    RT --> RE["Refresh Token có thể còn hiệu lực"]
    IDT --> IE["ID Token có thời hạn riêng"]
~~~

Một hàng có thể chứa authorization code đã hết hạn, access token đã hết hạn nhưng refresh token vẫn còn hiệu lực. Nếu cleanup xóa cả hàng theo authorization_code_expires_at hoặc access_token_expires_at, client sẽ mất refresh token còn dùng được.

**Quy tắc:** thời hạn phải được đánh giá theo từng token; chỉ xóa toàn bộ authorization khi mọi token có thể được dùng trong hàng đó đã hết hạn hoặc đã được dọn theo retention policy.

### 1.3. Consent và registered client có vòng đời khác

oauth2_authorization_consent không phải token cache và không có cùng semantics expiry với access/refresh token. Consent có thể tồn tại lâu hơn nhiều authorization. Xóa authorization hết hạn không tự động có nghĩa phải xóa consent.

oauth2_registered_client chứa cấu hình client. Một client có thể có nhiều authorization và consent. Xóa client registration trong khi token/authorization của client còn hiệu lực có thể làm server không còn tra được cấu hình client cần thiết để xử lý các authorization đó.

Không chạy một câu DELETE chung cho cả ba bảng dựa trên ngày hết hạn token.

## 2. Xác định điều kiện hết hạn chính xác

### 2.1. Dùng thời điểm hết hạn của từng token

| Token | Cột thời gian hết hạn | Hệ quả khi hết hạn |
| --- | --- | --- |
| Authorization Code | authorization_code_expires_at | Không thể đổi code đã hết hạn lấy token. |
| Access Token | access_token_expires_at | Resource Server phải từ chối token hết hạn theo validation. |
| OIDC ID Token | oidc_id_token_expires_at | Client không được dùng ID Token hết hạn như assertion authentication mới. |
| Refresh Token | refresh_token_expires_at | Không thể dùng refresh token đã hết hạn để xin access token mới. |
| User Code | user_code_expires_at | Không thể dùng user code đã hết hạn để hoàn tất device authorization. |
| Device Code | device_code_expires_at | Không thể dùng device code đã hết hạn để lấy token. |

Tên cột chính xác phải được đối chiếu với schema SQL đi kèm đúng phiên bản Spring Authorization Server đang chạy. Nếu ứng dụng có token type hoặc cột tùy chỉnh, cleanup cũng phải hiểu các cột đó.

### 2.2. NULL không phải lúc nào cũng có nghĩa là đã hết hạn

Trong schema chuẩn, token không được tạo thường có *_value IS NULL. Khi token value có mặt nhưng *_expires_at IS NULL, cleanup không nên tự suy luận rằng token đã hết hạn. Hãy giữ bản ghi cho tới khi có quy tắc rõ ràng cho loại token đó.

Một điều kiện an toàn có dạng:

~~~sql
(token_value IS NULL
 OR (token_expires_at IS NOT NULL AND token_expires_at < :cutoff))
~~~

Điều kiện này có nghĩa:

- không có token value: thành phần đó không ngăn cleanup;
- có token value và expiry đã qua cutoff: token có thể được xem là hết hạn theo retention policy;
- có token value nhưng không có expiry: giữ lại để tránh xóa nhầm.

### 2.3. Dùng grace period

Không nhất thiết xóa ngay khi đồng hồ vừa qua expires_at. Một khoảng giữ thêm, ví dụ 24 giờ hoặc 7 ngày tùy policy, có thể hữu ích cho:

- điều tra sự cố và audit;
- xử lý request đang chạy;
- retry từ client có clock skew;
- đối chiếu dữ liệu và hỗ trợ vận hành;
- bảo đảm các node có cùng cách diễn giải thời gian.

Gọi thời điểm cleanup là cutoff = current_time - retention_grace_period. Chỉ coi token đủ điều kiện dọn khi expires_at < cutoff.

Grace period là quyết định vận hành, không thay thế kiểm tra token expiry tại endpoint. Access token hết hạn vẫn phải bị từ chối dù hàng còn nằm trong database.

## 3. Hai chiến lược cleanup

| Chiến lược | Hành vi | Khi phù hợp |
| --- | --- | --- |
| Xóa toàn bộ authorization khi mọi token đã hết hạn | Xóa hàng chỉ khi mọi token value đều vắng mặt hoặc đã hết hạn quá cutoff. | Đơn giản, giữ lại các token cùng authorization tới khi tất cả không còn dùng được. |
| Dọn từng token đã hết hạn, sau đó xóa hàng rỗng | Đặt các cột token đã hết hạn về NULL, giữ token còn hiệu lực; xóa hàng khi không còn token value. | Giảm thời gian lưu token cũ khi authorization vẫn có refresh token hoạt động. |

Không có một lịch cleanup phù hợp cho mọi hệ thống. Chọn chiến lược theo yêu cầu retention, khả năng điều tra và hành vi của phiên bản JdbcOAuth2AuthorizationService đang dùng.

### 3.1. Khi nào nên dọn từng token?

Ví dụ authorization có access token hết hạn từ hôm qua, ID Token hết hạn từ hôm qua và refresh token còn hạn 20 ngày. Nếu chỉ xóa toàn bộ hàng khi tất cả token hết hạn, access token và ID Token cũ vẫn nằm trong database thêm 20 ngày. Nếu chính sách yêu cầu giảm thời gian lưu token bearer đã hết hạn, có thể xóa riêng token fields đã hết hạn, giữ refresh token và phần authorization cần thiết cho refresh flow.

Khi dọn từng token, phải cập nhật đồng bộ các cột value, issued-at, expires-at, metadata và các cột mô tả token liên quan. Không chỉ xóa *_value rồi để metadata cũ khiến row mapper hoặc truy vấn vận hành hiểu sai.

## 4. SQL cleanup an toàn trên PostgreSQL

Các ví dụ dưới đây dùng PostgreSQL và tên cột của schema JDBC chuẩn. Với MySQL, SQL Server hoặc database khác, điều chỉnh cú pháp batch/locking và kiểm tra execution plan. Luôn đối chiếu schema migration thực tế trước khi chạy.

### 4.1. Dọn authorization code đã hết hạn

~~~sql
UPDATE oauth2_authorization
SET authorization_code_value = NULL,
    authorization_code_issued_at = NULL,
    authorization_code_expires_at = NULL,
    authorization_code_metadata = NULL
WHERE authorization_code_value IS NOT NULL
  AND authorization_code_expires_at IS NOT NULL
  AND authorization_code_expires_at < :cutoff;
~~~

Câu lệnh chỉ xóa dữ liệu của authorization code đã hết hạn quá cutoff. Access token, refresh token và các token khác trong cùng hàng được giữ nguyên.

Authorization code đã hết hạn không thể đổi lấy token mới, nhưng giữ metadata trong grace period có thể hỗ trợ điều tra code replay hoặc client retry. Chọn thời điểm cleanup phù hợp với yêu cầu vận hành.

### 4.2. Dọn access token đã hết hạn

~~~sql
UPDATE oauth2_authorization
SET access_token_value = NULL,
    access_token_issued_at = NULL,
    access_token_expires_at = NULL,
    access_token_metadata = NULL,
    access_token_type = NULL,
    access_token_scopes = NULL
WHERE access_token_value IS NOT NULL
  AND access_token_expires_at IS NOT NULL
  AND access_token_expires_at < :cutoff;
~~~

Không xóa refresh token trong câu lệnh này. Khi refresh token vẫn còn hiệu lực, authorization row vẫn cần được giữ để refresh flow tải authorization và kiểm tra refresh token.

### 4.3. Dọn refresh token đã hết hạn

~~~sql
UPDATE oauth2_authorization
SET refresh_token_value = NULL,
    refresh_token_issued_at = NULL,
    refresh_token_expires_at = NULL,
    refresh_token_metadata = NULL
WHERE refresh_token_value IS NOT NULL
  AND refresh_token_expires_at IS NOT NULL
  AND refresh_token_expires_at < :cutoff;
~~~

Khi refresh token đã hết hạn, client không thể tiếp tục refresh bằng token đó. Access token cùng authorization có thể vẫn còn hiệu lực; do đó không xóa cả hàng chỉ vì refresh token hết hạn.

### 4.4. Dọn OIDC ID Token

Không dùng một câu UPDATE chung chỉ dựa trên oidc_id_token_expires_at. Schema authorization mặc định không có một cột session-end phổ quát để biết RP-Initiated Logout còn được phép dùng ID Token hint hay không. Nếu cần dọn ID Token riêng trong khi các token khác vẫn còn, hãy bổ sung retention/session eligibility state do ứng dụng quản lý và chỉ xóa sau khi UserInfo window, access-token dependency và logout eligibility window đã kết thúc.

ID Token là token riêng với access token. Client thường lưu ID Token ở phía mình cho session OIDC; Authorization Server không cần giữ ID Token vô thời hạn sau khi token đã hết hạn và hết retention window. Tuy nhiên, **không xóa ID Token chỉ dựa trên exp** nếu OP còn hỗ trợ RP-Initiated Logout hoặc UserInfo dựa trên authorization đó. OIDC cho phép OP xử lý ID Token hint đã hết hạn khi phiên RP còn hiện tại/gần đây; UserInfo mapper mặc định của Spring Authorization Server cũng có thể lấy claims từ ID Token được lưu trong authorization. Hãy giữ ID Token tới khi access-token/UserInfo window và session/logout eligibility window liên quan đã kết thúc, rồi mới dọn theo retention policy.

### 4.5. Dọn user code và device code

~~~sql
UPDATE oauth2_authorization
SET user_code_value = NULL,
    user_code_issued_at = NULL,
    user_code_expires_at = NULL,
    user_code_metadata = NULL
WHERE user_code_value IS NOT NULL
  AND user_code_expires_at IS NOT NULL
  AND user_code_expires_at < :cutoff;
~~~

~~~sql
UPDATE oauth2_authorization
SET device_code_value = NULL,
    device_code_issued_at = NULL,
    device_code_expires_at = NULL,
    device_code_metadata = NULL
WHERE device_code_value IS NOT NULL
  AND device_code_expires_at IS NOT NULL
  AND device_code_expires_at < :cutoff;
~~~

Hai loại token này liên quan Device Authorization Grant. Khi dọn chúng, vẫn phải giữ access/refresh token nếu authorization đã hoàn tất và token tương ứng còn hiệu lực.

### 4.6. Xóa authorization không còn token

Sau khi đã dọn các token hết hạn theo từng loại, có thể xóa các authorization không còn token value nào:

~~~sql
DELETE FROM oauth2_authorization
WHERE authorization_code_value IS NULL
  AND access_token_value IS NULL
  AND oidc_id_token_value IS NULL
  AND refresh_token_value IS NULL
  AND user_code_value IS NULL
  AND device_code_value IS NULL;
~~~

Câu lệnh này là bước cuối của chiến lược dọn từng token. Chỉ dùng khi mọi loại token có thể xuất hiện trong schema và custom extension đã được xử lý. Nếu ứng dụng có loại token bổ sung, thêm điều kiện tương ứng. Không xóa hàng có token value chưa xác định được expiry.

Nếu không muốn dọn từng token, có thể xóa hàng theo predicate kiểm tra tất cả token:

~~~sql
DELETE FROM oauth2_authorization
WHERE (authorization_code_value IS NULL
       OR (authorization_code_expires_at IS NOT NULL
           AND authorization_code_expires_at < :cutoff))
  AND (access_token_value IS NULL
       OR (access_token_expires_at IS NOT NULL
           AND access_token_expires_at < :cutoff))
  AND oidc_id_token_value IS NULL
  AND (refresh_token_value IS NULL
       OR (refresh_token_expires_at IS NOT NULL
           AND refresh_token_expires_at < :cutoff))
  AND (user_code_value IS NULL
       OR (user_code_expires_at IS NOT NULL
           AND user_code_expires_at < :cutoff))
  AND (device_code_value IS NULL
       OR (device_code_expires_at IS NOT NULL
           AND device_code_expires_at < :cutoff));
~~~

Predicate này bảo đảm mọi token value có mặt đều đã được dọn theo policy. Các token có expiry độc lập được so với cutoff; riêng ID Token chỉ được dọn sau khi ứng dụng xác nhận không còn UserInfo hoặc logout dependency. Một token còn hạn, ID Token chưa hết retention window hoặc token không có expiry sẽ ngăn xóa toàn bộ hàng.

## 5. Batch cleanup và transaction

Không nên xóa hàng triệu authorization trong một transaction duy nhất. Transaction quá lớn có thể giữ row locks lâu, tăng WAL, làm replica lag, tăng bloat và ảnh hưởng request token đang chạy.

### 5.1. Dùng batch với SKIP LOCKED

PostgreSQL hỗ trợ FOR UPDATE SKIP LOCKED, cho phép nhiều worker chọn các hàng khác nhau mà không chờ nhau. Ví dụ xóa authorization đã hết hạn toàn bộ token:

~~~sql
WITH candidates AS (
    SELECT id
    FROM oauth2_authorization
    WHERE (authorization_code_value IS NULL
           OR (authorization_code_expires_at IS NOT NULL
               AND authorization_code_expires_at < :cutoff))
      AND (access_token_value IS NULL
           OR (access_token_expires_at IS NOT NULL
               AND access_token_expires_at < :cutoff))
      AND oidc_id_token_value IS NULL
      AND (refresh_token_value IS NULL
           OR (refresh_token_expires_at IS NOT NULL
               AND refresh_token_expires_at < :cutoff))
      AND (user_code_value IS NULL
           OR (user_code_expires_at IS NOT NULL
               AND user_code_expires_at < :cutoff))
      AND (device_code_value IS NULL
           OR (device_code_expires_at IS NOT NULL
               AND device_code_expires_at < :cutoff))
    ORDER BY id
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
DELETE FROM oauth2_authorization authorization
USING candidates
WHERE authorization.id = candidates.id;
~~~

Mỗi lần chỉ xử lý tối đa batch_size hàng. Gọi lặp lại trong các transaction ngắn cho tới khi số hàng xóa bằng 0 hoặc đạt giới hạn thời gian của maintenance window.

SKIP LOCKED giúp nhiều cleanup workers không khóa chờ cùng một hàng. Nó không thay thế predicate expiry chính xác và không làm cho việc xóa hàng còn token hiệu lực trở nên an toàn.

### 5.2. Dọn từng token theo batch

Các câu UPDATE ở mục trước có thể được giới hạn theo batch bằng CTE chọn ID:

~~~sql
WITH candidates AS (
    SELECT id
    FROM oauth2_authorization
    WHERE access_token_value IS NOT NULL
      AND access_token_expires_at IS NOT NULL
      AND access_token_expires_at < :cutoff
    ORDER BY id
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
UPDATE oauth2_authorization authorization
SET access_token_value = NULL,
    access_token_issued_at = NULL,
    access_token_expires_at = NULL,
    access_token_metadata = NULL,
    access_token_type = NULL,
    access_token_scopes = NULL
FROM candidates
WHERE authorization.id = candidates.id;
~~~

Dùng cùng mẫu cho authorization code, refresh token, user code và device code. Với ID Token, áp dụng retention/session eligibility policy riêng; không dùng expires_at đơn độc vì token còn có thể phục vụ UserInfo hoặc RP-Initiated Logout.

Các câu SQL này thao tác trực tiếp trên bảng và bỏ qua logic của OAuth2AuthorizationService. Nếu ứng dụng có cache hoặc wrapper tùy chỉnh quanh JDBC service, phải invalidate cache tương ứng sau cleanup. Chạy SQL bằng cùng database/schema mà Authorization Server đang dùng; không sửa object authorization trong bộ nhớ rồi quên persist trạng thái mới.

### 5.3. Transaction ngắn và retry

Một batch nên là một transaction độc lập:

1. Tính cutoff một lần cho lần chạy hoặc truyền cutoff cố định vào từng batch.
2. Chọn và khóa candidate rows.
3. Update/delete.
4. Commit.
5. Ghi metrics số hàng được xử lý.
6. Tiếp tục batch kế tiếp nếu còn dữ liệu.

Nếu transaction thất bại, rollback batch đó và retry có giới hạn với backoff. Không lặp vô hạn khi có lỗi schema, deadlock hoặc permission. Log error code và batch ID, không log token values.

### 5.4. Job chạy trên nhiều instance

Nếu mỗi Authorization Server instance chạy cùng một scheduled cleanup:

- Dùng SKIP LOCKED để tránh xử lý trùng các hàng trong cùng batch.
- Hoặc dùng distributed scheduler/leader election nếu chỉ muốn một instance điều phối.
- Tránh một transaction dài bao trùm toàn bộ vòng lặp.
- Đặt timeout, giới hạn batch và maintenance window.
- Đảm bảo job không chạy đồng thời với schema migration.

Nếu cleanup chạy song song với refresh/revoke, row-level locking và transaction isolation giúp các thao tác trên cùng authorization được tuần tự hóa. Predicate vẫn phải kiểm tra lại expiry trong transaction; không chọn ID ở một thời điểm rồi xóa sau đó mà không kiểm tra lại điều kiện.

## 6. Triển khai cleanup job trong Spring

Spring Authorization Server cung cấp JDBC persistence services, nhưng ứng dụng vẫn cần quyết định retention và lịch dọn dữ liệu. Không giả định việc dùng JdbcOAuth2AuthorizationService tự động tạo một retention job phù hợp cho production.

Có thể tách thành hai thành phần:

- AuthorizationCleanupScheduler: điều phối lịch chạy và batch loop.
- AuthorizationCleanupRepository: thực thi các câu SQL cleanup bằng NamedParameterJdbcTemplate.

Ví dụ cấu trúc scheduler:

~~~java
@Component
@RequiredArgsConstructor
public class AuthorizationCleanupScheduler {

    private final AuthorizationCleanupService cleanupService;
    private final Clock clock;

    private final Duration gracePeriod = Duration.ofDays(7);
    private final int batchSize = 500;

    @Scheduled(cron = "0 30 2 * * *")
    public void cleanupExpiredAuthorizations() {
        Instant cutoff = clock.instant().minus(gracePeriod);

        int deleted;
        do {
            deleted = cleanupService.deleteExpiredBatch(cutoff, batchSize);
        } while (deleted == batchSize);
    }
}
~~~

Service thực thi một batch trong transaction riêng:

~~~java
@Service
@RequiredArgsConstructor
public class AuthorizationCleanupService {

    private final AuthorizationCleanupRepository repository;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public int deleteExpiredBatch(Instant cutoff, int batchSize) {
        return repository.deleteExpiredBatch(cutoff, batchSize);
    }
}
~~~

Đây là skeleton để thể hiện ranh giới transaction; AuthorizationCleanupRepository phải dùng SQL phù hợp với database và schema đã triển khai. Cần bật scheduling bằng @EnableScheduling, cấu hình Clock, validate batchSize > 0 và giới hạn tổng thời gian một lần chạy. Nếu dùng nhiều instance, bổ sung distributed scheduling hoặc batch locking phù hợp.

Phương thức transactional nên được gọi qua Spring proxy từ bean khác; self-invocation trong cùng bean có thể không kích hoạt transaction interceptor. Với job chạy lâu, giữ mỗi batch trong một transaction ngắn và không đặt toàn bộ vòng lặp trong một transaction bên ngoài.

### 6.1. Tránh cleanup khi schema chưa sẵn sàng

Không chạy cleanup trước khi migration schema hoàn tất. Khi deploy:

1. Apply database migrations.
2. Kiểm tra schema version.
3. Khởi động Authorization Server.
4. Xác minh JDBC services hoạt động.
5. Mới cho phép scheduled cleanup chạy.

Dùng feature flag để tạm dừng cleanup trong lúc restore, migration hoặc incident response. Không để một instance cũ chạy SQL cleanup trên schema của phiên bản mới chưa tương thích.

## 7. Index, query plan và database maintenance

Cleanup có thể trở thành full table scan nếu bảng lớn và không có index phù hợp.

### 7.1. Đánh giá index theo truy vấn thực tế

Các cột thường dùng trong điều kiện expiry:

- authorization_code_expires_at;
- access_token_expires_at;
- oidc_id_token_expires_at;
- refresh_token_expires_at;
- user_code_expires_at;
- device_code_expires_at.

PostgreSQL có thể dùng partial indexes, ví dụ:

~~~sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    idx_oauth2_authorization_access_expiry
ON oauth2_authorization (access_token_expires_at)
WHERE access_token_value IS NOT NULL;
~~~

Tạo index tương tự chỉ khi query plan chứng minh có ích. Trong PostgreSQL, CREATE INDEX CONCURRENTLY không chạy bên trong transaction block; hãy đưa migration này vào bước triển khai riêng phù hợp với công cụ migration. Predicate nhiều cột kết hợp AND/OR có thể khiến optimizer chọn bitmap scan hoặc sequential scan; không có một bộ index tối ưu cho mọi workload.

### 7.2. Kiểm tra query plan

Dùng EXPLAIN để xem truy vấn cleanup có quét toàn bảng hay không. Khi dùng EXPLAIN ANALYZE, nhớ rằng câu UPDATE/DELETE thực sự chạy; thử trong staging hoặc transaction rollback có kiểm soát.

Theo dõi:

- số hàng được scan và số hàng được xóa;
- thời gian batch;
- lock waits và deadlocks;
- WAL generation;
- replication lag;
- table/index size và dead tuples.

### 7.3. VACUUM và bloat

PostgreSQL không nhất thiết thu nhỏ file database ngay sau DELETE. Dead tuples được xử lý bởi VACUUM; disk space thường được tái sử dụng trong table thay vì trả ngay cho filesystem. Theo dõi autovacuum và table bloat, tránh chạy VACUUM FULL tùy tiện trên production vì thao tác này có thể cần lock mạnh và rewrite bảng.

Cleanup ổn định theo batch thường tốt hơn một đợt delete rất lớn theo tháng.

## 8. Retention cho consent, client và audit

### 8.1. Authorization consent

oauth2_authorization_consent lưu consent đã cấp giữa principal và registered client. Bảng này không có expiry của access/refresh token. Chính sách xóa consent nên dựa trên:

- người dùng yêu cầu thu hồi consent;
- client bị gỡ bỏ hoặc không còn được sử dụng;
- yêu cầu privacy/data retention;
- tenant/account bị đóng;
- thời hạn lưu trữ theo quy định của tổ chức.

Không xóa consent chỉ vì một authorization token đã hết hạn. Consent có thể được dùng lại ở lần authorization sau; xóa nó sẽ khiến người dùng phải consent lại.

### 8.2. Registered client

oauth2_registered_client chứa cấu hình và credential của client. Xóa registration cần quy trình quản lý vòng đời riêng:

1. Ngừng cấp token mới cho client.
2. Thu hồi hoặc chờ hết hạn các authorization/token hiện có.
3. Xử lý refresh token và consent theo policy.
4. Giữ audit/tombstone đủ lâu để điều tra và tránh tái sử dụng client ID.
5. Chỉ xóa registration khi không còn authorization cần nó và đã hết retention window.

Không xóa client chỉ vì client_name cũ hoặc client không hoạt động trong vài ngày.

### 8.3. Audit và lịch sử bảo mật

Audit records thường có retention riêng với token data. Có thể cần giữ sự kiện tạo client, thay đổi redirect URI, token revocation, consent withdrawal và administrative action lâu hơn authorization rows.

Không giữ raw access token, refresh token, client secret hoặc private key trong audit. Nếu cần liên kết một token với sự kiện, dùng token identifier/hash phù hợp và giới hạn quyền truy cập.

## 9. Backup phải bao gồm những gì?

Một backup có thể khôi phục Authorization Server phải bao gồm mọi thành phần cần thiết để server tiếp tục xác thực client, đọc authorization và ký/xác minh token.

| Thành phần | Lý do cần backup |
| --- | --- |
| oauth2_registered_client | Khôi phục client IDs, credentials đã encode, redirect URIs, grant types, scopes và settings. |
| oauth2_authorization | Khôi phục authorization, access/refresh tokens, ID Token và trạng thái revocation/invalidated metadata. |
| oauth2_authorization_consent | Khôi phục consent để trải nghiệm authorization nhất quán. |
| Signing keys/JWK material hoặc KMS/HSM references | Ký token mới và duy trì khả năng xác minh token cũ. |
| Issuer và endpoint configuration | Giữ iss, endpoint URLs, key selection và client discovery nhất quán. |
| Database schema/migration version | Đảm bảo row mappers và SQL tương thích với dữ liệu. |
| Encryption keys/secret references | Giải mã dữ liệu hoặc truy cập secret store sau restore. |
| Session store và security state bên ngoài | Khôi phục hoặc chủ động invalidation OP sessions khi cần. |
| Audit và administrative records | Điều tra thay đổi, revocation và hoạt động quản trị. |

### 9.1. Database backup không tự chứa signing keys

JWKSource có thể lấy key từ database, filesystem, secret manager, KMS hoặc HSM. Không giả định private signing key luôn nằm trong ba bảng JDBC.

Nếu key nằm ngoài database:

- backup key theo quy trình của KMS/HSM hoặc secret manager;
- lưu key ID/version và quyền truy cập;
- bảo đảm ứng dụng restore có thể truy cập key cần thiết;
- giữ public keys cũ đủ lâu để Resource Server xác minh token đã phát hành;
- không export private key ra file backup thông thường nếu nền tảng hỗ trợ backup an toàn hơn.

Database snapshot không thể khôi phục khả năng ký token nếu private key đã bị mất hoặc quyền truy cập KMS không còn.

### 9.2. Backup là dữ liệu nhạy cảm

oauth2_authorization có thể chứa bearer token values, claims và PII. Backup cần:

- mã hóa khi truyền và khi lưu;
- quyền truy cập tối thiểu và audit mọi lần restore;
- lưu bản backup ở tài khoản/storage tách biệt;
- immutable retention hoặc object lock nếu cần chống ransomware;
- quản lý encryption keys tách khỏi backup;
- chính sách xóa backup hết hạn;
- kiểm soát việc sao chép production data sang staging/development.

Không gửi backup hoặc dump database qua email/chat và không đưa token values vào log.

## 10. PostgreSQL backup và Point-in-Time Recovery

Chiến lược backup nên kết hợp logical backup, physical/base backup và WAL archiving tùy RPO/RTO.

### 10.1. Logical backup với pg_dump

Ví dụ tạo custom-format backup:

~~~bash
pg_dump \
  --format=custom \
  --no-owner \
  --file=authorization-server.dump \
  --dbname=authorization_server
~~~

Xem danh sách object trong archive:

~~~bash
pg_restore --list authorization-server.dump
~~~

Logical backup phù hợp cho migration, kiểm tra dữ liệu, restore một database hoặc chuyển môi trường. Nó tạo snapshot nhất quán của database tại thời điểm dump, nhưng không thay thế WAL archiving nếu cần khôi phục tới một thời điểm bất kỳ sau base backup.

Dùng .pgpass, service file hoặc secret manager để cấp credentials; tránh ghi password trực tiếp vào command line hoặc script lưu trong repository.

pg_dump chỉ backup một database; các global objects như database roles và tablespaces cần được quản lý/backup riêng theo quy trình PostgreSQL của tổ chức (ví dụ pg_dumpall --globals-only). Đảm bảo role và grants được khôi phục phù hợp trước khi ứng dụng kết nối.

### 10.2. Physical backup và WAL archiving

Với yêu cầu RPO thấp, PostgreSQL có thể dùng base backup kết hợp WAL archiving để hỗ trợ PITR:

- tạo base backup định kỳ;
- bật WAL archiving và lưu WAL liên tục tới storage độc lập;
- giám sát archive failures và khoảng trống WAL;
- giữ base backup/WAL theo retention;
- định kỳ thực hiện restore drill tới một timestamp được chọn.

PITR cần đầy đủ base backup và chuỗi WAL liên tục. Có WAL file nhưng thiếu base backup tương thích thì không đủ để khôi phục.

### 10.3. Backup consistency

Ba bảng oauth2_registered_client, oauth2_authorization và oauth2_authorization_consent nên được backup trong một snapshot database nhất quán. Nếu chúng nằm ở các database khác nhau, phải thiết kế snapshot/coordination để tránh trạng thái lệch giữa client và authorization.

Cấu hình issuer, key IDs, key material và session store ngoài database cần có checkpoint/version tương thích với snapshot. Ghi lại timestamp và schema migration version của mỗi backup.

## 11. Restore vào môi trường cô lập

Không restore đè production ngay trong lần diễn tập đầu tiên. Hãy khôi phục vào một database và môi trường cô lập để xác minh.

### 11.1. Restore logical backup vào database mới

~~~bash
createdb authorization_server_restore

pg_restore \
  --exit-on-error \
  --no-owner \
  --dbname=authorization_server_restore \
  authorization-server.dump
~~~

Sau khi restore:

1. Kiểm tra ownership, grants và database extensions.
2. Xác minh schema/migration version.
3. Cấu hình ứng dụng trỏ tới database mới.
4. Kết nối signing keys/KMS đúng môi trường.
5. Kiểm tra issuer và public JWKS.
6. Chạy smoke tests với client thử nghiệm.
7. Chỉ sau khi xác minh mới xem xét cutover.

Không dùng --clean hoặc restore đè database production mà chưa có change plan, snapshot trước thao tác và phương án rollback.

### 11.2. Kiểm tra số lượng và tính nhất quán

Một số truy vấn đối chiếu:

~~~sql
SELECT COUNT(*) AS registered_clients
FROM oauth2_registered_client;

SELECT COUNT(*) AS authorizations
FROM oauth2_authorization;

SELECT COUNT(*) AS consents
FROM oauth2_authorization_consent;

SELECT COUNT(*) AS authorizations_with_active_access_token
FROM oauth2_authorization
WHERE access_token_value IS NOT NULL
  AND access_token_expires_at > CURRENT_TIMESTAMP;
~~~

Các con số chỉ giúp phát hiện restore thiếu bảng hoặc dữ liệu bất thường. Chúng không chứng minh token có thể được xác minh, client có thể đăng nhập hoặc refresh flow hoạt động.

### 11.3. Smoke test sau restore

Thực hiện một bộ kiểm tra qua application service/API:

- RegisteredClientRepository.findByClientId(...) tìm được client dự kiến.
- OAuth2AuthorizationService.findById(...) đọc được authorization test.
- OAuth2AuthorizationService.findByToken(...) tìm được token test còn hạn theo token type.
- Token còn hạn được xác minh bằng key hiện tại/cũ phù hợp.
- Refresh token còn hạn có thể đi qua refresh flow trong môi trường test.
- Revoked/invalidated token vẫn bị từ chối.
- Consent được đọc đúng.
- Metadata discovery công bố đúng issuer và JWKS URI.

Không dùng token production thật trong smoke test ở staging nếu có thể tạo client và authorization test riêng.

## 12. Rủi ro đặc biệt khi restore một backup cũ: revocation có thể bị rollback

Đây là rủi ro bảo mật cần được xử lý riêng.

Giả sử:

1. Lúc 10:00, database ghi nhận refresh token R1 còn hiệu lực.
2. Lúc 11:00, người dùng thu hồi R1; database lưu trạng thái invalidated.
3. Lúc 12:00, hệ thống restore snapshot được tạo lúc 10:30.

Sau restore, database có thể không còn biết R1 đã bị thu hồi. Nếu authorization/token state được đọc trực tiếp từ database, trạng thái cũ có thể làm token xuất hiện như chưa bị revoke.

~~~mermaid
sequenceDiagram
    participant DB as Authorization DB
    participant AS as Authorization Server
    participant RS as Resource Server

    AS->>DB: 10:00: Lưu refresh token R1 active
    AS->>DB: 11:00: Đánh dấu R1 revoked
    Note over DB: Snapshot backup lúc 10:30
    AS->>DB: 12:00: Restore snapshot 10:30
    AS->>DB: Đọc lại authorization của R1
    DB-->>AS: Trạng thái trước khi revoke
    AS->>AS: Phải áp dụng recovery security policy
    AS-->>RS: Chỉ tiếp tục phục vụ sau khi xử lý token state
~~~

Tác động phụ thuộc token format và Resource Server:

- Opaque token/introspection có thể trở lại active nếu trạng thái cũ được phục hồi.
- JWT được xác minh offline vốn không phụ thuộc trực tiếp vào row revocation hiện tại; restore database không tự làm JWT hết hiệu lực.
- Refresh token có thể được chấp nhận lại nếu trạng thái invalidation đã bị rollback.
- Client registration hoặc secret rotation mới hơn snapshot cũng có thể bị mất.

### 12.1. Recovery controls

Sau khi restore từ snapshot cũ hơn các thay đổi bảo mật quan trọng:

- tạm dừng cấp token/refresh trong khi đánh giá;
- so sánh thời điểm snapshot với revocation, credential rotation và incident logs;
- thu hồi hoặc xoay các credentials có thể bị rollback;
- invalidate sessions theo policy;
- áp dụng denylist/epoch/monotonic security state ở kho độc lập nếu hệ thống cần bảo đảm không resurrect token;
- yêu cầu re-authentication hoặc re-consent khi cần;
- chỉ mở lại traffic khi đã xác minh trạng thái token và keys.

Nếu yêu cầu bảo mật nghiêm ngặt, lưu revocation/security events trong một hệ thống append-only hoặc replicated độc lập với database snapshot có thể bị rollback. Một restore database thành công về kỹ thuật chưa chắc là trạng thái an toàn để mở traffic.

## 13. Disaster recovery: RPO, RTO và runbook

Đặt mục tiêu trước khi có sự cố:

| Chỉ số | Ý nghĩa | Ví dụ cần quyết định |
| --- | --- | --- |
| RPO (Recovery Point Objective) | Mức mất dữ liệu tối đa chấp nhận được. | Mất tối đa 5 phút authorization/revocation updates hay 1 giờ? |
| RTO (Recovery Time Objective) | Thời gian tối đa để khôi phục dịch vụ. | Khôi phục issuer trong 30 phút hay 4 giờ? |
| Backup retention | Thời gian lưu backup. | Daily snapshots, weekly/monthly archive và legal retention. |
| PITR window | Khoảng thời gian có thể khôi phục tới. | 7, 14 hoặc 35 ngày tùy WAL retention và chi phí. |
| Key recovery objective | Thời gian khôi phục signing/verification keys. | KMS/HSM failover và quyền truy cập emergency. |

### 13.1. Runbook khôi phục

Một runbook thực tế:

1. Xác nhận incident, phạm vi hỏng dữ liệu và thời điểm cuối cùng database còn nhất quán.
2. Chặn hoặc giới hạn traffic tới Authorization Server nếu tiếp tục cấp token có thể gây rủi ro.
3. Chọn base backup/snapshot và PITR target.
4. Khôi phục vào database cô lập.
5. Khôi phục key access, issuer config, secret references và session dependencies.
6. Kiểm tra schema, row counts, client registrations, authorization và consent.
7. Đánh giá revocations, client secret rotations và security events sau thời điểm snapshot.
8. Chạy smoke/integration tests.
9. Quyết định invalidation/rotation cần thiết trước cutover.
10. Chuyển traffic, theo dõi lỗi token/refresh/login và replication.
11. Ghi lại thời gian thực tế, dữ liệu mất và các bước cần cải thiện.

### 13.2. Restore drill

Backup chỉ đáng tin khi đã restore thành công. Lên lịch diễn tập:

- restore một bản backup gần nhất vào staging;
- restore một mốc PITR được chọn;
- xác minh signing keys/JWKS và token validation;
- xác minh client credentials và consent;
- chạy refresh/revocation tests;
- đo thời gian thực tế so với RTO;
- kiểm tra backup encryption keys và quyền truy cập;
- ghi lại lỗi và cập nhật runbook.

Không chờ tới ngày production database hỏng mới thử pg_restore hoặc truy cập KMS bằng tài khoản khẩn cấp.

## 14. Các lỗi vận hành thường gặp

### 14.1. Xóa authorization theo access_token_expires_at

Một hàng có thể còn refresh token hợp lệ. Chỉ xóa toàn bộ row sau khi mọi token đã hết hạn hoặc được dọn theo policy.

### 14.2. Xóa refresh token nhưng quên metadata

Các cột token value, issued-at, expires-at và metadata cần được xử lý đồng bộ. Kiểm tra schema row mapper trước khi tự viết SQL.

### 14.3. Cleanup chạy quá lâu và khóa request token

Giảm batch size, dùng transaction ngắn, index theo truy vấn thật, giới hạn số batch mỗi lần và theo dõi lock wait/replication lag.

### 14.4. Consent bị xóa cùng token

Consent không có cùng expiry với authorization. Quản lý consent bằng retention policy riêng.

### 14.5. Restore database nhưng thiếu signing keys

Authorization Server có thể khởi động nhưng không ký được token hoặc Resource Server không xác minh được token cũ. Kiểm tra JWK/KMS/HSM trước cutover.

### 14.6. Restore snapshot làm mất revocation mới hơn

Đây là rollback trạng thái bảo mật. So sánh snapshot với security events độc lập, xử lý token/session/credentials trước khi mở traffic.

### 14.7. Backup có dữ liệu production được dùng ở staging

Backup chứa token, claims, client data và PII. Cô lập môi trường, hạn chế egress, bảo vệ keys và sanitize dữ liệu nếu mục tiêu chỉ là kiểm thử.

### 14.8. Dùng schema SQL khác phiên bản

Migration có thể thêm hoặc đổi cột. Cleanup SQL phải tương thích schema đang chạy; kiểm tra migration và thử trong staging trước production.

### 14.9. Bảng lớn nhưng thiếu index expiry

Cleanup quét toàn bảng, gây I/O và ảnh hưởng workload. Đo query plan trước khi thêm index; cân nhắc partial index theo token value hiện diện.

### 14.10. Chạy cleanup cùng lúc migration hoặc restore

Job có thể ghi lên schema chưa sẵn sàng hoặc xóa dữ liệu trong lúc restore validation. Dùng maintenance flag và chỉ bật lại sau khi xác minh.

## 15. Ma trận kiểm thử cleanup, backup và restore

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Authorization chỉ có code đã hết hạn quá cutoff | Có thể được dọn theo policy. |
| Code hết hạn nhưng access token còn hạn | Hàng được giữ; nếu dọn từng token thì chỉ code fields bị xóa. |
| Access token hết hạn nhưng refresh token còn hạn | Giữ refresh token và authorization. |
| Refresh token hết hạn nhưng access token còn hạn | Giữ access token; chỉ refresh fields được dọn. |
| ID Token hết hạn nhưng access token còn hạn | Không xóa access token; giữ ID Token nếu UserInfo hoặc logout còn cần. |
| ID Token hết hạn nhưng phiên OP còn trong logout eligibility window | Giữ ID Token hint tới khi cửa sổ logout và UserInfo kết thúc. |
| ID Token đã hết UserInfo/logout retention window và được policy đánh dấu đủ điều kiện | Chỉ dọn ID Token theo policy riêng; không ảnh hưởng token khác còn hiệu lực. |
| Device code/user code hết hạn nhưng access token còn hạn | Chỉ dọn device/user code fields. |
| Token value có nhưng expiry là NULL | Không tự động xóa token hoặc hàng. |
| Tất cả token value NULL sau cleanup | Hàng có thể được xóa theo retention policy. |
| Batch size nhỏ | Mỗi transaction chỉ xử lý tối đa batch size. |
| Hai cleanup workers chạy đồng thời | Không xóa trùng/khóa chờ kéo dài; SKIP LOCKED hoạt động như thiết kế. |
| Refresh request chạy đồng thời cleanup | Authorization còn token hoạt động không bị xóa. |
| Consent có tuổi đời lớn nhưng còn cần thiết | Không bị token cleanup xóa. |
| Client có authorization còn hiệu lực | Không xóa registered client. |
| Backup trong lúc token issuance | Snapshot nhất quán theo cơ chế database. |
| Restore logical backup vào database mới | Bảng và row được phục hồi. |
| Restore PITR | Dữ liệu khớp mốc thời gian đã chọn và WAL liên tục. |
| Restore thiếu signing key | Smoke test phát hiện trước cutover. |
| Restore snapshot cũ hơn một revocation | Recovery procedure phát hiện và xử lý rollback. |
| Restore sang staging | Secrets/keys được cô lập; dữ liệu nhạy cảm được kiểm soát. |
| Cleanup SQL sau schema migration | SQL vẫn tương thích với schema thực tế. |
| Backup encryption key không truy cập được | Restore drill thất bại và được ghi nhận trước incident. |
| Restore test chạy hết RTO | Đạt mục tiêu khôi phục đã đặt. |

### 15.1. Integration test với dữ liệu token hỗn hợp

Tạo một số authorization fixture:

- A: authorization code hết hạn, access token còn hạn, refresh token còn hạn.
- B: access token hết hạn, refresh token còn hạn.
- C: refresh token hết hạn, access token còn hạn.
- D: mọi token đã hết hạn quá grace period.
- E: token value có expiry NULL.
- F: device code/user code hết hạn, access token còn hạn.

Chạy cleanup trong transaction test và xác minh:

1. A, B, C, E, F vẫn còn authorization row.
2. Token fields hết hạn bị xóa đúng theo chiến lược.
3. Token còn hạn vẫn được OAuth2AuthorizationService.findByToken(...) tìm thấy.
4. D bị xóa sau khi thỏa điều kiện mọi token.
5. Consent và registered client không bị thay đổi ngoài policy.

### 15.2. Backup/restore integration drill

- Tạo registered client, consent và authorization test.
- Backup database.
- Thay đổi một registration, revoke một token và tạo authorization mới.
- Restore backup vào database cô lập.
- Xác minh dữ liệu khớp snapshot, nhận diện các thay đổi sau snapshot bị mất.
- Kiểm tra signing key, issuer và token validation.
- Chạy recovery controls để không phục hồi nhầm token đã bị revoke sau snapshot.
- Ghi thời gian restore và kết quả so với RPO/RTO.

## 16. Checklist triển khai

- [ ] Cleanup SQL khớp schema JDBC đúng phiên bản Spring Authorization Server.
- [ ] Hiểu một authorization row có thể chứa nhiều loại token.
- [ ] Predicate cleanup kiểm tra từng token expiry, không dựa vào một cột đơn lẻ.
- [ ] Token value có expiry NULL được giữ cho tới khi có policy rõ ràng.
- [ ] Có grace period và thời gian dùng chung theo UTC.
- [ ] Có chiến lược dọn từng token hoặc xóa row khi tất cả token đã hết hạn.
- [ ] Token fields và metadata được xóa đồng bộ.
- [ ] Không xóa authorization còn refresh/access/device token hoạt động.
- [ ] Batch size, transaction timeout và retry được giới hạn.
- [ ] Job chạy nhiều instance có SKIP LOCKED, scheduler lock hoặc leader election phù hợp.
- [ ] Consent và registered client có retention policy độc lập.
- [ ] Audit không lưu raw token, secret hoặc private key.
- [ ] Query plan và expiry indexes được đo trước khi triển khai.
- [ ] Theo dõi WAL, replica lag, lock waits, dead tuples và cleanup metrics.
- [ ] Backup snapshot nhất quán các bảng JDBC quan trọng.
- [ ] Có WAL archiving/PITR nếu yêu cầu RPO thấp.
- [ ] Backup bao gồm hoặc tham chiếu được signing keys, KMS/HSM và issuer configuration.
- [ ] Backup được mã hóa, phân quyền tối thiểu và lưu tách biệt.
- [ ] Có schema version, migration state và restore runbook.
- [ ] Restore drill được thực hiện định kỳ và đo theo RTO.
- [ ] Có quy trình xử lý revocation/credential rotation bị rollback sau restore cũ.
- [ ] Production backup không được mở trực tiếp ở staging không cô lập.
- [ ] Cleanup bị tạm dừng trong migration, restore và incident response.
- [ ] Có integration tests cho token hỗn hợp, concurrency, backup và restore.

**Ghi nhớ:** Hãy xem oauth2_authorization như một aggregate chứa nhiều token có expiry độc lập. Dọn từng token hoặc chỉ xóa cả hàng khi mọi token đã hết hạn quá retention cutoff. Backup phải giữ được tính nhất quán của client, authorization, consent và signing keys. Sau khi restore snapshot cũ, luôn kiểm tra khả năng rollback revocation trước khi mở lại traffic.

## 17. Tài liệu tham khảo

- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): JdbcOAuth2AuthorizationService, JdbcOAuth2AuthorizationConsentService, JdbcRegisteredClientRepository và các thành phần persistence.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): cấu hình Authorization Server và các service cần thiết.
- [Spring Authorization Server — How-to: Implement core services with JPA](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-jpa.html): tham khảo mô hình persistence và ranh giới service khi tùy chỉnh storage.
- [Spring Authorization Server — Source repository](https://github.com/spring-projects/spring-authorization-server): schema SQL chính thức đi kèm đúng phiên bản dependency.
- [PostgreSQL — pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html): logical backup nhất quán.
- [PostgreSQL — pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html): khôi phục archive.
- [PostgreSQL — Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): base backup, WAL archiving và PITR.
- [PostgreSQL — SELECT locking clause](https://www.postgresql.org/docs/current/sql-select.html): FOR UPDATE SKIP LOCKED.
- [PostgreSQL — VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html): thu hồi và tái sử dụng không gian sau DELETE/UPDATE.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): semantics thu hồi token và tác động đến token liên quan.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): refresh token protection, rotation và bảo mật OAuth hiện hành.

