# Dọn token và key sau test

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao token, signing key, encryption key và test credential còn sót lại sau integration test tạo ra rủi ro bảo mật.
- Thiết kế vòng đời tài nguyên test theo nguyên tắc tạo riêng, giới hạn phạm vi, thu hồi và xác minh đã dọn.
- Phân biệt cách dọn JWT, opaque token, refresh token, JWK/JWKS, khóa trong KMS/HSM, chứng thư và dữ liệu test.
- Viết teardown an toàn, có thể chạy lặp lại khi test thành công hoặc thất bại.
- Kiểm thử rằng token cũ không còn dùng được, khóa test không còn được công bố và artifact nhạy cảm không bị lưu lại.

## 1. Vì sao cleanup là một phần của kiểm thử bảo mật?

Integration test thường cần một authorization server, resource server, database, cache, message broker và bộ khóa ký token. Test có thể tạo access token, refresh token, opaque token, client secret, private key, certificate hoặc dữ liệu chứa thông tin xác thực. Nếu chỉ kiểm tra assertion mà không dọn những tài nguyên này, môi trường test có thể giữ lại credential còn hiệu lực sau khi pipeline kết thúc.

Các tình huống có thể xảy ra:

- Một refresh token test còn hiệu lực trong token store và có thể tiếp tục xin access token.
- Một opaque access token chưa bị thu hồi vẫn được introspection trả về trạng thái active.
- Một JWT đã phát hành vẫn xác minh được vì resource server tiếp tục tin signing key test.
- Private key, client secret hoặc file keystore bị lưu trong thư mục build, log, test report hay artifact CI.
- JWKS cache còn giữ public key cũ, khiến test không phản ánh trạng thái key rotation hoặc key removal.
- Dữ liệu tenant, session, revocation record hoặc message test bị dùng nhầm trong lượt chạy kế tiếp.

Cleanup không chỉ là xóa file. Nó phải kết thúc khả năng sử dụng credential, loại bỏ trạng thái tin cậy liên quan, thu hồi hoặc xóa tài nguyên test và xác minh kết quả. **Một test chỉ được xem là hoàn tất khi cả kiểm tra nghiệp vụ lẫn teardown bắt buộc đều thành công.**

## 2. Phân loại tài nguyên cần dọn

| Tài nguyên | Ví dụ | Hành động cleanup |
| --- | --- | --- |
| Access token | JWT hoặc opaque token | Thu hồi, xóa token record hoặc làm token không còn được chấp nhận theo cơ chế của hệ thống |
| Refresh token | Token trong token family | Thu hồi token và toàn bộ family/session liên quan nếu policy yêu cầu |
| Authorization code | Code dùng một lần | Đánh dấu đã dùng/hết hiệu lực và xóa record test |
| Client credential | Client secret, test password | Vô hiệu hóa/xóa client test, không ghi secret vào log |
| Signing key | RSA, EC, HMAC key dùng ký JWT | Xóa key test hoặc key version trong KMS/HSM; gỡ khỏi cấu hình/JWKS test |
| Encryption key | DEK/KEK hoặc wrapping key test | Xóa key test theo policy; xử lý ciphertext và wrapped key liên quan |
| Certificate | Test certificate và private key | Xóa file/key, thu hồi hoặc gỡ trust entry theo mô hình PKI test |
| Cache/session | Access decision, session, JWKS cache | Xóa theo namespace của lượt chạy; xác minh không còn entry |
| Dữ liệu test | User, tenant, order, audit record | Xóa theo test run ID hoặc reset database test |
| Artifact | Keystore, token dump, report, temp file | Xóa hoặc bảo đảm không upload/publish artifact nhạy cảm |

Không phải tài nguyên nào cũng có cùng cách dọn. Ví dụ, xóa một JWT khỏi bộ nhớ test không làm chữ ký của nó mất hiệu lực. Nếu resource server vẫn tin issuer và signing key, JWT có thể tiếp tục được chấp nhận cho đến khi hết hạn hoặc có một cơ chế kiểm tra trạng thái/revocation bổ sung.

## 3. Nguyên tắc thiết kế cleanup an toàn

### 3.1 Mỗi lượt test sở hữu tài nguyên riêng

Tạo namespace duy nhất cho mỗi lượt chạy, chẳng hạn ID có tiền tố it- và run ID, rồi gắn namespace đó vào:

- Client ID và test subject.
- Token family, session, authorization grant.
- KMS key alias hoặc key label.
- Database schema/tenant test.
- Cache prefix, queue/topic và object storage prefix.
- Thư mục tạm và tên artifact.

Cleanup chỉ được xóa tài nguyên thuộc namespace mà test tạo ra. Không dùng chung signing key production, client thật, tenant thật hoặc key test dùng chung với các test đang chạy song song.

### 3.2 Dọn theo thứ tự phụ thuộc

Một thứ tự tham khảo:

1. Ngừng phát sinh request/job mới từ test client.
2. Thu hồi refresh token, access token opaque, session và grant liên quan.
3. Vô hiệu hóa client test hoặc credential đã tạo.
4. Xóa key test khỏi KMS/HSM hoặc key registry và gỡ key khỏi JWKS/configuration test.
5. Xóa JWKS/introspection/authorization cache và các cache entry theo namespace.
6. Xóa dữ liệu, file, message và artifact test.
7. Đọc lại trạng thái để xác minh token không còn active, key không còn được tin cậy và dữ liệu đã được dọn.

Thứ tự thực tế phụ thuộc hệ thống. Ví dụ, có thể cần giữ public key trong một khoảng thời gian ngắn để test cache/rotation hoàn tất trước khi xóa key version. Điều quan trọng là xác định rõ trạng thái cuối cùng và không để pipeline kết thúc khi credential ngoài ý muốn vẫn hoạt động.

### 3.3 Cleanup phải idempotent

Teardown có thể được gọi sau khi một bước đã xóa tài nguyên, sau khi test fail hoặc sau khi CI retry. Gọi cleanup nhiều lần không được gây lỗi giả hoặc xóa nhầm tài nguyên khác.

Một thao tác cleanup nên:

- Nhận chính xác ID/namespace do test tạo.
- Chấp nhận tài nguyên đã không còn tồn tại.
- Không dùng wildcard rộng có thể chạm dữ liệu test khác.
- Ghi nhận trạng thái thành công/thất bại mà không ghi secret.
- Có thể xác minh bằng truy vấn trạng thái độc lập sau khi xóa.

### 3.4 Có TTL dự phòng nhưng không dựa vào TTL làm cleanup duy nhất

Token test nên có lifetime ngắn và key test có vòng đời giới hạn. TTL giúp giảm tác động nếu teardown bị bỏ lỡ. Tuy nhiên, chờ token tự hết hạn không thay thế thu hồi token, xóa key hoặc dọn dữ liệu. Với opaque token và refresh token, cần cập nhật trạng thái phía authorization server/token store.

## 4. Dọn từng loại token

### 4.1 JWT access token

JWT thường là token tự chứa. Resource server xác minh chữ ký và claims như iss, aud, exp; nó không nhất thiết hỏi authorization server mỗi lần dùng. Vì vậy:

- Xóa chuỗi JWT khỏi biến test không thu hồi token đã phát hành.
- Xóa private key không nhất thiết làm token mất hiệu lực nếu verifier vẫn có public key tương ứng.
- Gỡ public key khỏi JWKS không có tác dụng ngay nếu resource server đang cache JWKS.
- Nếu hệ thống có denylist/revocation check theo jti, cần xóa hoặc cập nhật record theo policy và xác minh verifier thật sự kiểm tra nó.

Các lựa chọn cleanup:

1. Dùng signing key riêng cho từng test run; sau test, gỡ key khỏi trust set và làm mới JWKS cache trong môi trường test.
2. Dùng token TTL rất ngắn như một lớp giảm thiểu rủi ro.
3. Nếu ứng dụng hỗ trợ revocation/introspection cho JWT, thu hồi theo cơ chế đó và xác minh resource server từ chối token.

Không dùng chung key giữa test suite song song nếu teardown một test có thể khiến test khác mất khả năng xác minh token.

### 4.2 Opaque access token

Opaque token thường có record hoặc trạng thái phía authorization server. Cleanup nên gọi revoke endpoint/API quản trị được hệ thống hỗ trợ hoặc xóa record test qua fixture quản lý. Sau đó:

- Gọi introspection và xác minh token không còn active.
- Xác minh resource server từ chối token.
- Xóa cache introspection theo token hoặc namespace.

Chỉ xóa bản sao token trong test client không đủ vì token store vẫn có thể giữ token active.

### 4.3 Refresh token và token family

Refresh token có thể cấp access token mới. Nếu test tạo refresh token rotation, phải dọn toàn bộ token family và session/grant được tạo trong lượt chạy. Kiểm tra refresh token cũ và token hiện tại đều không thể tiếp tục cấp access token sau cleanup.

Nếu hệ thống có phát hiện reuse, không dùng lại family test đã bị thu hồi cho test khác. Mỗi scenario cần family riêng để kết quả không phụ thuộc thứ tự chạy.

### 4.4 Authorization code và session

Authorization code là credential ngắn hạn và dùng một lần. Test cần xác minh code đã dùng không thể dùng lại; sau scenario, xóa authorization transaction, browser session, consent/grant và cookie test theo namespace. Không lưu cookie hoặc session ID trong artifact CI.

## 5. Dọn signing key, encryption key và JWKS

### 5.1 Signing key dùng trong test

Ưu tiên sinh key pair tạm thời bằng API mật mã hoặc KMS test. Public key có thể được công bố trong JWKS của test issuer; private key chỉ được giữ trong phạm vi test. Sau test:

- Xóa private key/key version trong provider test nếu có API hỗ trợ.
- Gỡ JWK khỏi JWKS test endpoint và cấu hình issuer.
- Xóa cache JWKS ở resource server hoặc chờ cơ chế refresh được kiểm soát.
- Xác minh token được ký bằng key đã loại bỏ bị từ chối sau khi verifier cập nhật trust set.

Nếu nhiều test cùng dùng một issuer/key, không được xóa key ở teardown của một test khi test khác còn phụ thuộc. Dùng key theo run hoặc quản lý lifecycle ở cấp suite.

### 5.2 HMAC secret

HMAC secret là bí mật dùng chung để ký và xác minh. Không đưa secret vào source code, fixture commit, command line hoặc log. Dùng secret riêng cho test, lấy từ secret store của môi trường test hoặc sinh ngẫu nhiên khi chạy. Sau test, xóa secret khỏi store và cấu hình test theo cơ chế của provider.

### 5.3 Encryption key và dữ liệu đã mã hóa

Nếu test tạo DEK/KEK hoặc wrapped key, cần dọn cả key reference, wrapping metadata và ciphertext test theo policy. Xóa ciphertext nhưng để lại key có thể không tạo rủi ro tương tự việc để lại key có thể giải mã dữ liệu nhạy cảm; ngược lại, xóa key quá sớm có thể khiến teardown hoặc kiểm thử phục hồi thất bại. Xác định rõ thứ tự theo mục tiêu test.

### 5.4 Không hứa hẹn xóa sạch byte trong JVM

Trong Java, một đối tượng PrivateKey có thể được quản lý bởi provider và runtime. Gọi clear() trên biến tham chiếu hoặc đặt biến thành null không chứng minh byte bí mật đã bị ghi đè trong bộ nhớ. Một số provider hỗ trợ javax.security.auth.Destroyable, nhưng khả năng và hiệu quả phụ thuộc implementation.

Vì vậy:

- Giảm thời gian và phạm vi tồn tại của secret trong bộ nhớ.
- Ưu tiên KMS/HSM để private key không phải xuất ra ứng dụng.
- Nếu cần nạp key bytes vào test, giữ trong buffer có thể kiểm soát và xóa buffer sau khi import.
- Không ghi key, token hoặc password vào exception, dump hay log.
- Xem xóa key tại KMS/HSM và loại bỏ quyền truy cập là kiểm soát chính; không tuyên bố đã zeroize hoàn toàn mọi bản sao trong heap nếu runtime/provider không bảo đảm điều đó.

## 6. Ví dụ Java: quản lý fixture và teardown

Ví dụ dưới đây mô tả cấu trúc fixture. Các interface là adapter do ứng dụng/test harness cung cấp; tên method không phải API chuẩn của OAuth hoặc JCA.

~~~java
import java.util.UUID;

interface TestTokenAdmin {
    void revokeToken(String tokenId);
    boolean isActive(String tokenId);
    void revokeTokenFamily(String familyId);
    boolean isFamilyActive(String familyId);
}

interface TestKeyAdmin {
    void deleteKeyVersion(String keyVersionId);
    boolean keyVersionExists(String keyVersionId);
    void removeFromJwks(String keyId);
    boolean isPublishedInJwks(String keyId);
    void refreshVerifierJwksCache();
}

final class TokenSecurityFixture implements AutoCloseable {
    private final String runId = "it-" + UUID.randomUUID();
    private final TestTokenAdmin tokenAdmin;
    private final TestKeyAdmin keyAdmin;
    private String accessTokenId;
    private String refreshFamilyId;
    private String keyVersionId;
    private String keyId;

    TokenSecurityFixture(
            TestTokenAdmin tokenAdmin,
            TestKeyAdmin keyAdmin) {
        this.tokenAdmin = tokenAdmin;
        this.keyAdmin = keyAdmin;
    }

    String runId() {
        return runId;
    }

    void registerAccessToken(String tokenId) {
        this.accessTokenId = tokenId;
    }

    void registerRefreshFamily(String familyId) {
        this.refreshFamilyId = familyId;
    }

    void registerSigningKey(String keyVersionId, String keyId) {
        this.keyVersionId = keyVersionId;
        this.keyId = keyId;
    }

    @Override
    public void close() {
        RuntimeException cleanupFailure = null;

        if (refreshFamilyId != null) {
            cleanupFailure = runCleanupStep(cleanupFailure,
                    () -> tokenAdmin.revokeTokenFamily(refreshFamilyId));
        }
        if (accessTokenId != null) {
            cleanupFailure = runCleanupStep(cleanupFailure,
                    () -> tokenAdmin.revokeToken(accessTokenId));
        }
        if (keyId != null) {
            cleanupFailure = runCleanupStep(cleanupFailure,
                    () -> keyAdmin.removeFromJwks(keyId));
            cleanupFailure = runCleanupStep(cleanupFailure,
                    keyAdmin::refreshVerifierJwksCache);
        }
        if (keyVersionId != null) {
            cleanupFailure = runCleanupStep(cleanupFailure,
                    () -> keyAdmin.deleteKeyVersion(keyVersionId));
        }

        if (refreshFamilyId != null) {
            cleanupFailure = runCleanupStep(cleanupFailure, () -> {
                if (tokenAdmin.isFamilyActive(refreshFamilyId)) {
                    throw new IllegalStateException("refresh family remains active");
                }
            });
        }
        if (accessTokenId != null) {
            cleanupFailure = runCleanupStep(cleanupFailure, () -> {
                if (tokenAdmin.isActive(accessTokenId)) {
                    throw new IllegalStateException("access token remains active");
                }
            });
        }
        if (keyId != null) {
            cleanupFailure = runCleanupStep(cleanupFailure, () -> {
                if (keyAdmin.isPublishedInJwks(keyId)) {
                    throw new IllegalStateException("test key remains in JWKS");
                }
            });
        }
        if (keyVersionId != null) {
            cleanupFailure = runCleanupStep(cleanupFailure, () -> {
                if (keyAdmin.keyVersionExists(keyVersionId)) {
                    throw new IllegalStateException("test key version still exists");
                }
            });
        }

        if (cleanupFailure != null) {
            throw new IllegalStateException(
                    "Test security fixture cleanup failed for " + runId,
                    cleanupFailure);
        }
    }

    private static RuntimeException runCleanupStep(
            RuntimeException previousFailure, Runnable action) {
        try {
            action.run();
        } catch (RuntimeException ex) {
            if (previousFailure == null) {
                return ex;
            }
            previousFailure.addSuppressed(ex);
        }
        return previousFailure;
    }
}
~~~

Fixture thực tế cần bổ sung adapter cho session, client, opaque token, cache và dữ liệu. Ví dụ trên cho thấy ba nguyên tắc: chỉ dọn tài nguyên đã đăng ký thuộc run hiện tại, tiếp tục thử các bước cleanup độc lập ngay cả khi một bước lỗi, và xác minh trạng thái sau xóa. Các adapter phải coi kết quả "đã không tồn tại" là thành công để thao tác có thể chạy lặp lại; lỗi quyền hoặc lỗi kết nối vẫn phải được báo.

### Sử dụng với JUnit 5

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class TokenExchangeIntegrationTest {
    private TokenSecurityFixture fixture;

    @BeforeEach
    void setUp() {
        fixture = createIsolatedFixture();
    }

    @AfterEach
    void tearDown() {
        if (fixture != null) {
            fixture.close();
        }
    }

    // Test methods tạo token/key và đăng ký ID vào fixture.
}
~~~

Trong test thật, hàm tạo fixture phải tạo tài nguyên trong namespace riêng và trả về adapter đã kết nối tới test authorization server/KMS. Không tạo fixture dùng chung giữa các test song song nếu lifecycle của chúng không được điều phối an toàn.

Với resource có thể tạo từng phần rồi lỗi giữa chừng, đăng ký cleanup ngay sau khi tạo thành công. Không đợi đến cuối setup mới đăng ký tất cả, vì setup fail giữa chừng sẽ để lại tài nguyên chưa được teardown quản lý.

## 7. Xác minh cleanup đã thực sự hoàn tất

Đừng chỉ kiểm tra rằng hàm delete trả về không lỗi. Cần đọc lại trạng thái bằng API hoặc kho dữ liệu phù hợp:

| Đối tượng | Xác minh sau cleanup |
| --- | --- |
| Opaque access token | Introspection trả active=false hoặc token không còn tồn tại |
| Refresh token | Refresh thất bại; family/session test không còn active |
| JWT test | Verifier từ chối sau khi key test bị gỡ khỏi trust set/cache theo thiết kế |
| Signing key | Key version không còn tồn tại/không còn quyền sử dụng trong KMS test |
| JWKS | kid test không còn được công bố; verifier đã làm mới cache |
| Client secret | Client test bị disable/xóa và credential không còn xác thực được |
| Cache/session | Không còn entry mang run ID |
| Database | Không còn fixture record thuộc run ID |
| File/artifact | Không còn keystore, token dump hoặc file nhạy cảm trong output được giữ lại |

JWT cần được kiểm tra cẩn thận: nếu key test đã bị gỡ khỏi issuer nhưng verifier vẫn giữ public key trong cache, token có thể vẫn hợp lệ trong khoảng cache. Bài test cleanup nên chờ/ép refresh cache theo contract rồi xác minh token bị từ chối. Nếu hệ thống chủ ý cho phép overlap key khi rotation, kết quả kỳ vọng phải tính đến khoảng overlap đó.

### Test chính cleanup

Một integration test cleanup có thể thực hiện:

1. Tạo issuer/key pair test và công bố public key.
2. Phát hành JWT và opaque token; tạo refresh token family.
3. Xác minh các token được chấp nhận trước cleanup.
4. Chạy teardown.
5. Xác minh opaque token inactive, refresh token không cấp được access token, key không còn trong KMS/JWKS và JWT bị verifier từ chối sau cache refresh.
6. Xác minh namespace database/cache/storage của run không còn dữ liệu.
7. Chạy teardown lần thứ hai và xác minh thao tác vẫn thành công.

Test này kiểm tra cả khả năng cleanup và tính idempotent. Có thể bổ sung scenario teardown khi test assertion fail hoặc khi một trong các thao tác xóa trả lỗi.

## 8. Xử lý cleanup khi test thất bại

### Cleanup lỗi phải được nhìn thấy

Nếu assertion chính fail và teardown cũng fail, báo cáo test cần giữ được cả hai nguyên nhân. Không bắt exception cleanup rồi chỉ log ở mức debug; như vậy pipeline có thể báo xanh trong khi token hoặc key còn sống. Teardown failure phải làm job thất bại hoặc tạo trạng thái failure riêng được CI gate xử lý.

### Dùng try/finally cho tài nguyên ngoài lifecycle của framework

Với file, server, process hoặc client được tạo thủ công, dùng try/finally hoặc AutoCloseable/try-with-resources. JUnit AfterEach và AfterAll là hook hữu ích nhưng không thay thế quản lý tài nguyên đã tạo một phần trong setup.

### Có cơ chế dọn rác cho test run bị kill

CI runner có thể bị hủy đột ngột, mất kết nối hoặc bị terminate trước khi teardown chạy. Một sweeper riêng trong môi trường test có thể tìm tài nguyên theo prefix và thời gian tạo, rồi xóa sau TTL an toàn. Sweeper chỉ được phép tác động namespace test; cần audit và dry-run khi triển khai lần đầu.

### Không dùng production cleanup API tùy tiện

Test nên chạy trên issuer, database, KMS project/account và tenant riêng. Không để fixture có quyền xóa signing key hoặc token của môi trường dùng chung. Nếu cần test tích hợp với dịch vụ dùng chung, cấp credential giới hạn namespace và quyền cleanup đúng tài nguyên đã tạo.

## 9. Artifact, log và secret hygiene

Kiểm tra các vị trí thường vô tình lưu credential:

- target/, build/, thư mục test report và thư mục tạm.
- Log của authorization server, resource server, mock server và CI runner.
- Screenshot, HTTP trace, HAR, heap dump và crash dump.
- Environment variable capture, debug output và command history.
- Test fixture JSON/YAML, keystore, PEM, PKCS#12 và file cấu hình tạm.
- Artifact được upload để debug hoặc lưu giữa các pipeline stage.

Không ghi raw access token, refresh token, private key, HMAC secret, password hoặc authorization header vào test report. Nếu cần đối chiếu, dùng ID giả lập hoặc fingerprint không thể dùng để xác thực. Việc mask log là lớp hỗ trợ; tốt nhất là không phát sinh log chứa secret ngay từ đầu.

Đối với file keystore tạm, tạo trong thư mục riêng có quyền truy cập giới hạn, dùng tên gắn với run ID và xóa trong teardown. Kiểm tra pipeline không upload thư mục đó như artifact chung. Nếu test cần giữ bằng chứng, chỉ giữ report đã loại bỏ secret và dữ liệu nhạy cảm.

## 10. Ma trận kiểm thử cleanup

| Tình huống | Hành động | Kỳ vọng |
| --- | --- | --- |
| Test thành công | Chạy teardown bình thường | Mọi token/key/data test được dọn và xác minh |
| Assertion fail | Cố ý làm test fail | Teardown vẫn chạy và cleanup failure vẫn được báo |
| Setup fail giữa chừng | Tạo một phần tài nguyên rồi ném lỗi | Tài nguyên đã tạo được dọn |
| Cleanup chạy hai lần | Gọi close/teardown lần nữa | Thành công, không xóa tài nguyên ngoài namespace |
| Token opaque | Thu hồi rồi introspect | active là false |
| Refresh token | Thu hồi family rồi refresh | Không cấp access token mới |
| JWT với key riêng | Gỡ key, refresh JWKS cache | Verifier từ chối JWT test |
| JWKS cache cũ | Gỡ key nhưng giữ cache mô phỏng | Test phát hiện token còn được chấp nhận cho đến khi cache refresh |
| Test chạy song song | Cleanup run A khi run B đang hoạt động | Tài nguyên B không bị ảnh hưởng |
| CI bị terminate | Bỏ qua teardown mô phỏng | Sweeper tìm và dọn đúng run đã quá TTL |
| Secret trong report | Quét report/artifact | Không có raw token, key hoặc credential |

## 11. Checklist trước khi phát hành test suite

- [ ] Test dùng issuer, client, tenant và key riêng trong môi trường test.
- [ ] Mỗi lượt chạy có namespace/ID riêng để cleanup chính xác.
- [ ] Access token, opaque token, refresh family, session và authorization grant đều có kế hoạch thu hồi.
- [ ] JWT test dùng key riêng; đã kiểm tra JWKS và verifier cache sau khi gỡ key.
- [ ] KMS/HSM key version, certificate và client credential test được xóa hoặc vô hiệu hóa theo policy.
- [ ] Cleanup được đăng ký ngay sau khi từng tài nguyên tạo thành công.
- [ ] Teardown chạy khi assertion fail và khi setup fail giữa chừng.
- [ ] Cleanup idempotent, có readback và báo lỗi rõ ràng.
- [ ] Teardown failure làm CI job thất bại hoặc kích hoạt gate tương đương.
- [ ] Cache, database, queue, object storage và file tạm không còn dữ liệu thuộc run.
- [ ] Test report, log và artifact không chứa raw token hoặc key.
- [ ] Có sweeper giới hạn namespace để xử lý run bị terminate đột ngột.

## Ghi nhớ

**Dọn token và key là một phần của kết quả integration test.** Xóa biến chứa JWT không thu hồi JWT; xóa private key không tự động khiến verifier quên public key; xóa bản sao refresh token không làm token store vô hiệu hóa nó. Hãy thu hồi token ở nơi quản lý trạng thái, gỡ key khỏi trust set/KMS, làm mới cache, xóa artifact và đọc lại trạng thái. Mỗi test run cần sở hữu tài nguyên riêng, teardown phải idempotent và mọi lỗi cleanup phải được phản ánh trong kết quả CI.

### Tài liệu tham khảo

- IETF RFC 7517 — JSON Web Key (JWK), định dạng khóa và JWKS: https://www.rfc-editor.org/rfc/rfc7517
- IETF RFC 7519 — JSON Web Token (JWT), claims và expiration: https://www.rfc-editor.org/rfc/rfc7519
- IETF RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009
- IETF RFC 7662 — OAuth 2.0 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
- NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management: https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final
- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
