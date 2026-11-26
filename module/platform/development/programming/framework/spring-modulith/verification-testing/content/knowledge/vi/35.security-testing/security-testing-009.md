# Dọn token và credential sau test

Trong module `SPRING_MODULITH_VERIFICATION_TESTING`, một bài kiểm thử có thể tạo tài khoản tạm, OAuth client, access token, refresh token hoặc session để kiểm chứng chức năng của module `identity`, `orders` và các tích hợp. Nếu kết thúc test mà những credential này còn dùng được, bài kiểm thử sau có thể bị nhiễm trạng thái; nghiêm trọng hơn, token còn hiệu lực ở IdP, Redis hoặc cơ sở dữ liệu có thể bị tái sử dụng ngoài ý muốn.

Bài này hướng dẫn thiết kế vòng đời **tạo → sử dụng → thu hồi → xác minh → xóa dấu vết** với JUnit 5 và Spring Modulith. Trọng tâm là bảo đảm dữ liệu xác thực do test tạo ra được xử lý cả khi assertion thất bại, sự kiện chạy bất đồng bộ hoặc tiến trình CI bị gián đoạn.

## 1. Định nghĩa “dọn sạch” bằng hậu điều kiện có thể kiểm chứng

Dọn sạch token không đơn thuần là gọi `SecurityContextHolder.clearContext()` hay xóa biến Java. Cần trả lời ba câu hỏi riêng:

1. **Credential còn dùng được không?** Refresh token, opaque token hoặc client secret phải bị thu hồi hoặc vô hiệu hóa theo cơ chế thực tế của sản phẩm.
2. **Trạng thái được lưu còn tồn tại không?** Các bản ghi test trong DB, key Redis, session và tài nguyên sandbox IdP phải được xóa hoặc hết hạn theo chính sách đã xác định.
3. **Thông tin nhạy cảm có bị lộ không?** Không còn raw token/client secret trong log, báo cáo test, snapshot, artifact CI hoặc file tạm.

Ví dụ: test tạo OAuth client `it-client-a1` và refresh token `rt-a1`. Hậu điều kiện đạt khi không thể đổi `rt-a1` lấy access token mới, client đã bị vô hiệu hóa, tài nguyên của lượt chạy `a1` không còn hoạt động và hệ thống không ghi raw secret vào log. Xóa một row trong bảng token nhưng không thu hồi token phía identity provider (IdP) **chưa đủ**, vì hai bên có thể quản lý trạng thái độc lập.

Cần phân biệt:

- **Revoke (thu hồi):** thay đổi trạng thái để token hoặc client không thể tiếp tục được dùng; có thể giữ dấu vết kiểm toán.
- **Purge (xóa fixture):** dọn dữ liệu thử nghiệm sau khi đã xác minh việc thu hồi; thường chỉ làm trong môi trường test cô lập.
- **Expire (hết hạn):** cơ chế an toàn dự phòng theo TTL, đặc biệt quan trọng nếu worker CI bị kill trước khi teardown chạy.

## 2. Chọn cách dọn phù hợp với loại credential

Không phải mọi “token” trong JUnit đều tương ứng với một credential đang hoạt động trên server.

| Đối tượng được tạo trong test | Nơi giữ trạng thái | Cần dọn thế nào? |
| --- | --- | --- |
| `@WithMockUser`, `with(user(...))` hoặc `with(jwt())` trong Spring Security Test | Ngữ cảnh xác thực mô phỏng của test | Xóa security context nếu tự quản lý; **không có token thật để revoke** |
| Opaque access token, refresh token có lưu trữ | DB, Redis hoặc token store | Revoke qua application service; xóa key/row test đúng chủ sở hữu khi được phép |
| Access token dạng JWT tự chứa | Token đã ký, thường được xác minh không cần tra DB | Không thể “xóa” JWT đã phát; giới hạn TTL, kiểm tra denylist/token version nếu hệ thống hỗ trợ |
| OAuth client credential hoặc API key | IdP, secret store, bảng credential | Disable/revoke key, xóa client tạm ở sandbox và kiểm tra key không còn hiệu lực |
| Session cookie | Server session hoặc Spring Session store | Invalidate session và xóa session do test tạo; không xóa session của người khác |
| File chứa key, certificate hoặc token | Thư mục tạm, CI artifact, volume | Sử dụng tài nguyên tạm có vòng đời rõ, xóa file và hạn chế ghi dữ liệu nhạy cảm |
| Testcontainers DB/Redis dùng chung giữa các test | Container tồn tại suốt test suite | Dọn dữ liệu theo test ID; **không giả định** container bị hủy sau từng test |

JWT cần được hiểu chính xác: nếu API chỉ kiểm tra chữ ký và `exp`, thao tác xóa refresh token **không lập tức vô hiệu** access token JWT đã phát. Với yêu cầu thu hồi ngay, ứng dụng phải có cơ chế bổ sung (denylist theo `jti`, token version, introspection hoặc phiên sống ngắn phù hợp). Tài liệu test phải nói rõ bảo đảm nào thực sự tồn tại, tránh assertion khẳng định “đã revoke” khi access token vẫn hợp lệ.

## 3. Tạo fixture có chủ sở hữu và chạy trong sandbox

Mỗi test nên tạo một `runTag` duy nhất, ví dụ `cred-it-<UUID>`, gắn tag đó vào client hoặc metadata token nếu miền dữ liệu cho phép. Dùng tag để tìm đúng tài nguyên thuộc lần chạy hiện tại, nhất là khi CI chạy song song. Không sử dụng client sản xuất, tài khoản cá nhân hay cùng một credential cố định cho nhiều test.

```java
package example.shop.identity;

import java.util.UUID;

final class TestRunIds {
    private TestRunIds() {}

    static String newCredentialRunTag() {
        return "cred-it-" + UUID.randomUUID();
    }
}
```

Quy tắc sử dụng secret trong fixture:

- Chỉ đọc client secret từ kho bí mật của CI hoặc biến môi trường của **sandbox** khi test cần tích hợp thật; không commit password, refresh token hoặc private key vào repository, YAML hay Markdown.
- Nếu tạo secret tạm, dùng nguồn ngẫu nhiên bảo mật như `SecureRandom`; tránh password cố định `"test123"` trong test đánh giá chính sách credential.
- Không log giá trị trả về từ endpoint cấp token; che `Authorization`, `Cookie`, `Set-Cookie`, `client_secret` và body chứa `access_token`/`refresh_token` khi bật log HTTP.
- Dùng cấu hình allowlist cho URL/tenant sandbox và fail fast nếu trỏ tới endpoint không được phép. Không dùng tên môi trường chứa chữ “test” như bằng chứng duy nhất để xác định đây là sandbox.
- Với secret dạng `String`, Java không bảo đảm xóa sạch mọi bản sao khỏi bộ nhớ; vì vậy giảm thời gian giữ, tránh cache và tuyệt đối không ghi ra log/artifact.

Ví dụ kiểm tra biến cấu hình quan trọng mà không in secret vào thông báo lỗi:

```java
static String requiredSandboxSecret() {
    String secret = System.getenv("SANDBOX_IDP_CLIENT_SECRET");
    if (secret == null || secret.isBlank()) {
        throw new IllegalStateException(
            "Missing SANDBOX_IDP_CLIENT_SECRET for isolated integration tests"
        );
    }
    return secret;
}
```

Biến môi trường trên dùng cho test cần kết nối IdP thật. Test trong một module với fake hoặc token store riêng có thể tự tạo credential tạm; đừng bắt mọi test đơn vị phụ thuộc vào secret CI.

## 4. Đăng ký cleanup ngay khi tạo tài nguyên

Chỉ dựa vào một lệnh xóa ở cuối thân `@Test` là dễ bỏ sót: một assertion có thể ném exception trước khi chương trình tới lệnh xóa. JUnit 5 gọi `@AfterEach` sau mỗi phương thức test trong điều kiện thực thi thông thường, nhưng cleanup cần xử lý **nhiều bước**: revoke token trước, xóa client sau và vẫn tiếp tục chạy nếu một bước báo lỗi.

Một helper trong source set kiểm thử có thể thực hiện các hành động theo thứ tự ngược với thứ tự đăng ký (LIFO):

```java
package example.shop.identity;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Objects;

final class CleanupActions implements AutoCloseable {

    private final Deque<Runnable> actions = new ArrayDeque<>();

    void defer(Runnable action) {
        actions.push(Objects.requireNonNull(action));
    }

    @Override
    public void close() {
        RuntimeException firstFailure = null;

        while (!actions.isEmpty()) {
            try {
                actions.pop().run();
            } catch (RuntimeException exception) {
                if (firstFailure == null) {
                    firstFailure = exception;
                } else {
                    firstFailure.addSuppressed(exception);
                }
            }
        }

        if (firstFailure != null) {
            throw firstFailure;
        }
    }
}
```

Cách dùng quan trọng nhất là **tạo xong tài nguyên nào thì đăng ký dọn tài nguyên đó ngay**:

```java
UUID clientId = credentials.registerEphemeralClient(runTag);
cleanup.defer(() -> credentials.removeEphemeralClient(clientId));

var refreshToken = credentials.issueRefreshToken(clientId);
cleanup.defer(() -> credentials.revokeRefreshToken(refreshToken.id()));
```

Khi `close()` chạy, refresh token được revoke **trước** khi client bị xóa. Các lệnh `revoke`/`delete` của tầng ứng dụng nên có tính **idempotent**: gọi lần hai với token đã revoke hoặc client đã xóa không tạo lỗi giả. Helper cố gắng chạy mọi `Runnable` ngay cả khi một bước ném `RuntimeException`, đồng thời vẫn báo lỗi cho JUnit để CI không đánh dấu thành công sai.

`@AfterEach` không được bảo đảm chạy khi JVM bị kill, máy hết điện hoặc process bị terminate cưỡng bức; các trường hợp này cần TTL và cleanup dự phòng ở môi trường sandbox, được trình bày ở mục 8 và 10.

## 5. Kiểm thử JUnit với `@ApplicationModuleTest`

Giả sử module `identity` cung cấp một application port quản lý credential, trong đó các phương thức tạo/xóa client tạm chỉ được dùng ở môi trường test cô lập. Đây là **hợp đồng minh họa**; khi áp dụng vào dự án, dùng service/repository thật của module và giữ các quy tắc phân quyền/ghi nhận audit của sản phẩm.

```java
package example.shop.identity;

import java.util.UUID;

public interface CredentialLifecycle {
    UUID registerEphemeralClient(String runTag);

    RefreshCredential issueRefreshToken(UUID clientId);

    boolean canExchangeRefreshToken(String rawRefreshToken);

    void revokeRefreshToken(UUID tokenId);

    long activeRefreshTokensForClient(UUID clientId);

    void removeEphemeralClient(UUID clientId);

    record RefreshCredential(UUID id, String value) {}
}
```

JUnit chạy trong package module `identity` nên `@ApplicationModuleTest` bootstrap module chứa test. Test tạo credential, kiểm tra đường sử dụng trước/sau revoke và bảo đảm cleanup kể cả khi phép kiểm tra giữa chừng thất bại:

```java
package example.shop.identity;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.TestSecurityContextHolder;

@ApplicationModuleTest
class CredentialCleanupIT {

    @Autowired CredentialLifecycle credentials;

    private final CleanupActions cleanup = new CleanupActions();
    private final List<UUID> clientsCreated = new ArrayList<>();

    @Test
    void refreshTokenCannotBeUsedAfterRevocation() {
        String runTag = "cred-it-" + UUID.randomUUID();
        UUID clientId = credentials.registerEphemeralClient(runTag);
        clientsCreated.add(clientId);
        cleanup.defer(() -> credentials.removeEphemeralClient(clientId));

        var refresh = credentials.issueRefreshToken(clientId);
        cleanup.defer(() -> credentials.revokeRefreshToken(refresh.id()));

        assertThat(credentials.canExchangeRefreshToken(refresh.value()))
            .isTrue();

        credentials.revokeRefreshToken(refresh.id());

        assertThat(credentials.canExchangeRefreshToken(refresh.value()))
            .isFalse();
    }

    @AfterEach
    void revokeDeleteAndVerify() {
        try {
            cleanup.close();

            for (UUID clientId : clientsCreated) {
                assertThat(credentials.activeRefreshTokensForClient(clientId))
                    .isZero();
            }
        } finally {
            TestSecurityContextHolder.clearContext();
            SecurityContextHolder.clearContext();
        }
    }
}
```

Các điểm cần đọc đúng trong ví dụ:

- `CredentialLifecycle` cần **implementation thật** được bootstrap trong test context; việc định nghĩa interface không tự tạo bean. `canExchangeRefreshToken(...)` phải kiểm tra điều kiện sử dụng qua cơ chế xác thực/token store thực tế, không trả một kết quả giả được hardcode.
- Hàm `removeEphemeralClient` phải xóa đúng client có tag test và xử lý các row token liên quan theo chính sách test; hàm đếm token cần có thể truy vấn cả khi client đã xóa. Nếu không, tách bước xác minh trước khi purge.
- Đăng ký lệnh xóa client ngay sau khi tạo, đăng ký revoke ngay sau khi phát token. Khi assertion `isTrue()` hoặc `isFalse()` thất bại, JUnit vẫn gọi `@AfterEach` theo vòng đời bình thường.
- Lệnh revoke trong thân test chứng minh **hành vi nghiệp vụ**; lệnh revoke trong `@AfterEach` là **bảo hiểm cleanup**. Vì thế service cần xử lý việc revoke lặp lại.
- Nếu cần kiểm chứng HTTP/token thật qua gateway, dùng `@SpringBootTest` và gửi request qua filter chain. `@ApplicationModuleTest` phù hợp với vòng đời credential trong module, nhưng không mặc nhiên nạp mọi cấu hình security hay IdP của toàn ứng dụng.

Để test độc lập, dùng fixture data ở DB test và tách các credential được cấp cho từng case. Không dùng cùng một client “integration-test” cố định giữa các phương thức kiểm thử song song.

## 6. Kiểm tra chính cơ chế cleanup khi một bước thất bại

Một cleanup đáng tin phải tiếp tục xóa client ngay cả khi thao tác revoke ở token store gặp lỗi. Có thể kiểm tra helper độc lập bằng JUnit mà không tạo token thật. Đặt phép thử dưới đây trong test source set cùng package `CleanupActions`:

```java
package example.shop.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.ArrayList;
import org.junit.jupiter.api.Test;

class CleanupActionsTest {

    @Test
    void stillDeletesClientWhenRevocationThrows() {
        var actions = new CleanupActions();
        var executed = new ArrayList<String>();

        actions.defer(() -> executed.add("delete-client"));
        actions.defer(() -> {
            executed.add("revoke-token");
            throw new IllegalStateException("token store unavailable");
        });

        assertThatThrownBy(actions::close)
            .isInstanceOf(IllegalStateException.class)
            .hasMessage("token store unavailable");

        assertThat(executed)
            .containsExactly("revoke-token", "delete-client");
    }
}
```

Kết quả đúng là **cả hai hành động chạy, nhưng test vẫn báo lỗi**. Nếu lệnh thu hồi bị lỗi mà cơ chế cleanup nuốt ngoại lệ, CI sẽ báo xanh trong khi token có thể còn hoạt động.

Trong integration test, có thể xác minh thêm hậu điều kiện `activeRefreshTokensForClient(clientId) == 0` sau teardown. Nếu IdP hoặc DB cập nhật bất đồng bộ, thay assertion tức thời bằng kiểm tra chờ có thời hạn. Không thêm một test cố ý `fail()` vĩnh viễn vào CI; dùng mutation check trên nhánh tạm hoặc phép thử helper như trên để kiểm tra đường lỗi.

Một failure mode nữa là test tạo client thành công nhưng trả lỗi **trước khi nhận lại ID**. `@AfterEach` không biết tài nguyên nào phải xóa. Cần tag theo run ID ở phía server, TTL cho client test và tác vụ thu gom orphan trong sandbox để xử lý kiểu lỗi này.

## 7. Dọn đúng phạm vi ở database, Redis và session store

Với database test được quản lý riêng, xóa các row phụ thuộc trước rồi xóa client. Nếu schema hỗ trợ `client_id` và `test_run_tag`, thao tác bằng parameter binding có thể như sau:

```sql
-- Ví dụ schema fixture; tên bảng/cột cần điều chỉnh theo dự án.
DELETE FROM issued_refresh_token
WHERE client_id = :clientId
  AND test_run_tag = :runTag;

DELETE FROM oauth_client
WHERE id = :clientId
  AND test_run_tag = :runTag;
```

Các placeholder `:clientId` và `:runTag` tương ứng với `NamedParameterJdbcTemplate` hoặc cơ chế bind của driver, **không** ghép raw string tạo SQL. Cần bọc hai thao tác trong transaction phù hợp để tránh tình trạng xóa một nửa. Nếu sản phẩm yêu cầu sự kiện revoke/audit trước khi xóa, gọi application service thu hồi **trước** khi chạy bước purge test fixture. Chỉ dùng SQL trực tiếp khi DB thật sự là DB kiểm thử cô lập hoặc schema fixture do test sở hữu.

Với Redis, đặt namespace theo run tag (ví dụ `it:credential:<runTag>:<tokenId>`), dùng TTL và xóa đúng danh sách key do test tạo. Tránh `FLUSHALL`, xóa toàn bộ prefix chung hoặc thao tác quét không kiểm soát trên Redis dùng chung. Nếu hệ thống dùng Spring Session, invalidate chính session đã tạo; không vô hiệu hóa mọi session để làm test sạch.

Lưu ý về transaction:

- `@Transactional` trên một test thường cho rollback những thay đổi trong **test-managed transaction**. Nó không hủy tài nguyên ở IdP, Redis hay HTTP server độc lập.
- `@SpringBootTest(webEnvironment = RANDOM_PORT)` gửi request tới server ở thread khác; transaction của thread JUnit **không tự bao trùm** transaction do HTTP request đó tạo.
- Message listener, scheduled job hoặc event async có thể ghi DB trong transaction khác. Phải chờ công việc liên quan hoàn tất và cleanup bằng đúng owner ID.
- `@DirtiesContext` dựng lại hoặc đóng Spring context, **không đồng nghĩa** đã revoke token hay dọn dữ liệu bên ngoài context.

Nếu test đã bật rollback nhưng cần một bước cleanup xác nhận dữ liệu commit từ xử lý async, thực hiện bước này ngoài transaction kiểm thử bị rollback và chỉ nhắm tới tài nguyên thuộc run tag hiện tại.

## 8. Token phát qua event, xử lý async và IdP bên ngoài

Trong Spring Modulith, sự kiện `TokenIssued`, `ClientRotated` hoặc `RefreshTokenRevoked` có thể được listener xử lý sau giao dịch. Nếu xóa client ngay khi publisher trả về, listener còn đang chạy có thể tạo lại token hoặc ghi một row mồ côi. Trình tự kiểm thử nên là:

1. Kích hoạt thao tác trong module và chờ kết quả/sự kiện cần thiết bằng `Scenario` của `@ApplicationModuleTest` hoặc cơ chế chờ có thời hạn ở integration test.
2. Thu hồi token hoặc disable client bằng application service/IdP API.
3. Chờ trạng thái thu hồi được hệ thống xác nhận, nhất là khi cập nhật DB, cache hay IdP có độ trễ.
4. Xóa fixture và kiểm tra không còn token hoạt động thuộc client hoặc run tag.

Nếu ứng dụng dùng Awaitility (dependency test bổ sung), có thể kiểm tra kết quả bất đồng bộ bằng một assertion có timeout thay vì `Thread.sleep(...)` tùy ý:

```java
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;
import java.time.Duration;

// Sau khi đã gửi yêu cầu revoke cho clientId:
await().atMost(Duration.ofSeconds(5)).untilAsserted(() ->
    assertThat(credentials.activeRefreshTokensForClient(clientId)).isZero()
);
```

Timeout phải tương ứng SLA môi trường test và cho phép test **thất bại rõ ràng** nếu revoke không hoàn tất. Không lặp lại vô hạn, không tự đổi timeout thành một giá trị lớn chỉ để che lỗi đồng bộ.

Với sandbox IdP ngoài tiến trình, lưu ID của client/token ngay sau khi tạo, gọi endpoint revoke/delete có xác thực phù hợp, xử lý `404` do đã xóa như một kết quả idempotent nếu hợp đồng API cho phép. Khi IdP từ chối hoặc quá thời gian, lưu **ID không nhạy cảm** và mã lỗi để CI báo, tuyệt đối không ghi client secret/refresh token vào báo cáo. Việc revoke refresh token phía IdP thường **không cam kết** vô hiệu mọi access token JWT đã phát trước đó; kiểm tra riêng semantics của provider.

## 9. Dọn ngữ cảnh bảo mật, file tạm và log test

Cùng với credential phía server, một luồng kiểm thử có thể giữ principal trong `SecurityContextHolder` (ThreadLocal) hoặc `TestSecurityContextHolder`. Spring Security Test thường tự quản lý lifecycle cho `@WithMockUser`, nhưng khi test chủ động thiết lập context, nên xóa trong `finally`:

```java
import org.junit.jupiter.api.AfterEach;
import org.slf4j.MDC;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.TestSecurityContextHolder;

@AfterEach
void clearThreadLocalState() {
    try {
        TestSecurityContextHolder.clearContext();
        SecurityContextHolder.clearContext();
    } finally {
        MDC.clear(); // Chỉ cần nếu test có ghi dữ liệu vào MDC.
    }
}
```

Thao tác này chỉ dọn ngữ cảnh của **thread hiện tại**. Nếu có executor, task async hoặc thread do test tự tạo, phải dọn ngữ cảnh bên trong chính task bằng `try/finally`; xóa context ở thread JUnit không thay thế được việc đó. Không dùng `SecurityContextHolder.clearContext()` như bằng chứng rằng refresh token trên IdP đã bị thu hồi.

Các nguồn rò rỉ cần rà soát khi chạy JUnit/CI:

- Tránh `andDo(print())` hoặc request/response logging thô ở các test trao đổi token; cấu hình redaction trước khi xuất log/artifact.
- Dùng `@TempDir` cho file test dùng một lần; hạn chế ghi private key hoặc raw token xuống disk. Với tài nguyên ngoài thư mục `@TempDir`, tự xóa trong teardown và quản lý quyền truy cập file.
- Không ghi token vào assertion message, snapshot, test report hay exception log. Có thể kiểm tra việc token bị từ chối thông qua trạng thái/response mà không in giá trị token.
- Nếu test sửa system property, static cache hoặc MDC, khôi phục trạng thái cũ; những đối tượng này có thể sống qua nhiều test và gây nhiễm lẫn nhau.
- Khi JUnit chạy song song, không chia sẻ một biến mutable chứa token/client ID giữa nhiều test; dùng run tag độc lập và cleanup riêng mỗi test.

## 10. Quality gate CI và bài thực hành kiểm chứng cleanup

Chạy test vòng đời credential cùng kiểm thử module và integration trong pipeline. `ApplicationModules.of(...).verify()` vẫn cần để chặn phụ thuộc module sai, nhưng nó **không kiểm tra** việc revoke token, dọn session hay xóa client ở IdP. Quality gate cần bằng chứng ở đúng tầng trạng thái.

| Tình huống cần thử | Hậu điều kiện bắt buộc |
| --- | --- |
| Test thành công sau khi cấp refresh token | Token không đổi được credential mới; client test không còn hoạt động |
| Assertion ném exception giữa lúc test | `@AfterEach` vẫn thực hiện revoke/delete theo vòng đời JUnit |
| Revoke ném exception | Các bước cleanup tiếp theo vẫn chạy, nhưng test/job **báo lỗi** |
| Hai job CI chạy đồng thời | Cleanup job A không xóa credential của job B |
| Listener event hoàn tất muộn | Không còn token active/row mồ côi sau khi đợi sự kiện và teardown |
| JVM bị terminate trước `@AfterEach` | TTL và sandbox janitor thu gom credential orphan theo run tag/độ tuổi |
| Test ghi log và artifact | Không chứa raw token, mật khẩu, client secret hay cookie xác thực |

**Bài thực hành có tiêu chí đạt rõ ràng:**

1. Trong module `identity`, tạo port hoặc dùng application service thật để cấp client tạm, cấp refresh token, revoke và xóa client; tạo ít nhất hai test case với hai run tag khác nhau.
2. Áp dụng `CleanupActions` trong `@AfterEach`. Thêm assertion token dùng được trước revoke, không còn dùng được sau revoke; sau cleanup, truy vấn số token active của client bằng `0`.
3. Chạy `CleanupActionsTest` ở mục 6 để xác nhận khi revoke lỗi, thao tác xóa client vẫn được thử và JUnit vẫn báo fail.
4. Bổ sung một test tích hợp với DB/Redis hoặc sandbox IdP thật nếu hệ thống có thành phần đó; kiểm tra rằng tài nguyên được xóa đúng theo run tag. Không dùng database hoặc tenant production.
5. Trong CI, yêu cầu mọi cleanup exception khiến job thất bại, kiểm tra không còn fixture active theo run ID sau suite và cấu hình tác vụ dọn orphan theo TTL cho trường hợp tiến trình bị kill.

Một phép thử phản chứng hữu ích là tạm bỏ lệnh revoke trong một nhánh kiểm tra: assertion về khả năng sử dụng refresh token phải thất bại. Sau đó khôi phục revoke. Nếu test vẫn xanh, nó có thể chỉ đang kiểm tra sự hiện diện của bean hoặc đã xóa nhầm dữ liệu, chưa thực sự kiểm chứng lifecycle bảo mật.

**Tài liệu tham khảo:** [Spring Modulith – Integration Testing](https://docs.spring.io/spring-modulith/reference/testing.html), [Spring Security – Test support](https://docs.spring.io/spring-security/reference/servlet/test/index.html), [JUnit 5 – Test lifecycle](https://junit.org/junit5/docs/current/user-guide/#writing-tests-annotations).
