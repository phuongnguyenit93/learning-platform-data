# Test key destruction

**Test key destruction** là quá trình kiểm tra một khóa mật mã đã được vô hiệu hóa, thu hồi hoặc hủy theo đúng chính sách hay chưa, đồng thời xác minh hệ thống không còn sử dụng khóa đó ngoài những trường hợp được cho phép. Kiểm thử cần bao phủ trạng thái khóa, quyền thực hiện thao tác, bản sao vật liệu khóa, replica, backup, cache, alias, dữ liệu phụ thuộc và bằng chứng audit.

Xóa một alias khỏi KeyStore hoặc đánh dấu một key resource là deleted chưa đủ để chứng minh vật liệu khóa đã bị hủy. Khóa có thể còn tồn tại trong HSM, bản sao dự phòng, snapshot, cache của provider hoặc hệ thống backup. Với crypto erasure, việc xóa khóa chỉ có ý nghĩa khi mọi bản sao của vật liệu có khả năng giải mã dữ liệu đã được xử lý đúng cách.

Kiểm thử destruction thường có tác động không thể đảo ngược. Vì vậy, chỉ sử dụng khóa thử nghiệm trong môi trường cô lập, có định danh tài nguyên rõ ràng và cleanup được kiểm soát. Không chạy test phá hủy trên khóa production hoặc khóa còn bảo vệ dữ liệu cần lưu giữ.

## 1. Mục tiêu kiểm thử key destruction

Một kế hoạch kiểm thử cần xác minh các câu hỏi:

- Hệ thống phân biệt đúng disable, revoke, schedule deletion và destroy không?
- Chỉ principal được phép mới có thể yêu cầu hoặc phê duyệt hủy khóa không?
- Quy trình có kiểm soát hai người hoặc approval độc lập khi policy yêu cầu không?
- Key material có bị loại bỏ theo cơ chế được provider/KMS/HSM cam kết không?
- Các bản sao, replica, backup và cache có được xử lý theo chính sách không?
- Sau khi hủy, thao tác mã hóa, giải mã, ký hoặc MAC bằng khóa đó có bị từ chối không?
- Alias, key ID, metadata và trạng thái có phản ánh chính xác kết quả không?
- Một request destroy lặp lại hoặc đồng thời có tạo trạng thái không nhất quán không?
- Hệ thống có ghi audit event đủ để chứng minh ai yêu cầu, ai phê duyệt và kết quả ra sao không?
- Quy trình có bảo toàn bằng chứng và không làm lộ key material trong log không?

Test cần phân biệt kiểm tra hành vi API với bằng chứng zeroization vật lý. Unit test có thể xác minh state transition và quyền; integration test có thể xác minh KMS/HSM không còn cho phép sử dụng key. Việc chứng minh mọi bit vật lý đã bị xóa khỏi thiết bị hoặc mọi media backup đã được xử lý cần dựa vào bảo đảm của nhà cung cấp, quy trình vận hành và kiểm định chuyên biệt.

## 2. Phân biệt disable, revoke, schedule deletion và destroy

Các thao tác này không đồng nghĩa và thường có semantics khác nhau giữa KMS, HSM và provider.

| Thao tác | Ý nghĩa | Điều cần kiểm thử |
|---|---|---|
| Disable | Tạm thời ngăn một số operation bằng key | Key bị từ chối sử dụng nhưng có thể được enable lại |
| Revoke access/grant | Thu hồi quyền của principal hoặc grant | Principal mất quyền; key material vẫn tồn tại |
| Schedule deletion | Đặt lịch hủy sau một khoảng chờ | Trạng thái pending deletion, thời điểm hiệu lực và khả năng hủy lịch |
| Destroy | Hủy vật liệu khóa hoặc làm khóa không thể sử dụng theo cam kết provider | Key không thể phục hồi hoặc dùng lại theo semantics đã công bố |
| Delete alias/entry | Xóa tham chiếu hoặc entry trong kho | Alias không còn trỏ tới key; không mặc nhiên chứng minh key material đã bị hủy |
| Crypto erase | Hủy khóa cần thiết để giải mã dữ liệu được mã hóa | Mọi bản sao của khóa giải mã đã bị xử lý và dữ liệu không thể khôi phục bằng các bản sao còn lại |

Một key bị disable có thể được bật lại; một key bị revoke access vẫn có thể tồn tại và được principal khác sử dụng. Một key ở trạng thái pending deletion có thể vẫn còn sử dụng được hoặc đã bị chặn tùy dịch vụ. Do đó, test phải dựa vào state model và tài liệu của backend cụ thể, không giả định tên trạng thái có cùng ý nghĩa giữa các nhà cung cấp.

Với cặp khóa bất đối xứng, hủy private key không nhất thiết đồng nghĩa xóa public key. Public key và chứng chỉ có thể cần được giữ để xác minh chữ ký đã tạo trước đó. Với khóa mã hóa, hủy vật liệu có thể khiến dữ liệu cũ không thể giải mã; phải kiểm tra dependency trước khi thực hiện.

## 3. Phạm vi vật liệu khóa và các bản sao

Trước khi kiểm thử hủy khóa, cần xác định nơi vật liệu khóa hoặc bản sao có thể tồn tại:

- HSM, KMS hoặc thiết bị bảo vệ khóa gốc.
- Replica ở region, zone, cluster hoặc partition khác.
- Backup do provider quản lý và backup do tổ chức tự quản lý.
- KeyStore, file PKCS#12, database hoặc kho cấu hình.
- Bộ nhớ tiến trình, object cache, provider session hoặc connection pool.
- Bản sao của private key đã export trước đó.
- Encrypted data key trong envelope encryption.
- Snapshot, image, archive hoặc bản sao lưu dài hạn.
- Hệ thống khôi phục thảm họa và môi trường dự phòng.

Không phải mọi bản sao đều là key material trực tiếp. Ví dụ, encrypted DEK được bọc bằng KEK vẫn có thể giải mã nếu KEK còn tồn tại. Xóa KEK ở một region nhưng còn bản sao KEK ở region khác có thể không đạt mục tiêu crypto erasure.

Inventory cần ghi nhận key ID/version, loại khóa, owner, nơi lưu, khả năng export, replica, backup, dữ liệu phụ thuộc và retention. Test fixture nên tạo metadata này ngay từ lúc tạo test key để có thể xác minh phạm vi hủy.

## 4. State machine của quá trình destruction

Một quy trình hủy có thể gồm các trạng thái:

1. **Active:** khóa đang được phép sử dụng.
2. **Disable requested:** yêu cầu ngừng sử dụng được tiếp nhận.
3. **Disabled:** các operation mới bị chặn theo policy.
4. **Pending deletion:** đã lên lịch hủy, có thể tồn tại thời gian chờ.
5. **Destroyed:** vật liệu khóa đã được hủy theo semantics của backend.
6. **Tombstoned:** metadata tối thiểu được giữ để audit, ngăn tái sử dụng định danh hoặc xác nhận trạng thái.

Tên trạng thái và thứ tự thực tế phụ thuộc hệ thống. Một số KMS yêu cầu schedule deletion và có cửa sổ chờ; một số HSM có lệnh zeroize hoặc xóa object; một số hệ thống quản lý khóa nội bộ có bước approval trước khi gửi lệnh cuối.

~~~text
Active
  |
  v
Disable requested -> Disabled
                         |
                         v
                 Pending deletion
                         |
                         v
                     Destroyed
                         |
                         v
                    Tombstoned
~~~

Test cần xác minh các chuyển trạng thái hợp lệ và từ chối chuyển trạng thái không hợp lệ. Ví dụ, key đã destroyed không được quay lại Active; key pending deletion chỉ được cancel nếu backend và policy cho phép; request destroy lặp lại phải có kết quả xác định, không tạo ra key mới hoặc nhầm sang version khác.

## 5. Chuẩn bị môi trường kiểm thử an toàn

Destruction test cần được cô lập kỹ hơn các test tạo khóa thông thường:

- Dùng project, account, tenant, namespace hoặc HSM partition thử nghiệm riêng.
- Tạo key riêng cho mỗi test run và gắn tag có owner, test ID, thời điểm tạo.
- Dùng ciphertext và dữ liệu giả lập không chứa thông tin thật.
- Xác minh key ID thuộc test fixture trước khi gọi disable hoặc destroy.
- Không dùng alias chung có thể trỏ tới key production.
- Không chạy test song song trên cùng key hoặc cùng alias nếu chưa có khóa đồng bộ.
- Đặt giới hạn quota và ngân sách cho tài nguyên KMS/HSM.
- Có teardown và quy trình xử lý khi test dừng giữa chừng.
- Giữ lại audit evidence và resource ID, không giữ key bytes trong report.

Một test phá hủy cần có guard xác nhận môi trường. Nếu test không xác định được owner hoặc tag của key, phải dừng thay vì tiếp tục hủy theo một ID nhận từ cấu hình không đáng tin cậy.

## 6. Kiểm tra quyền và approval trước khi hủy

Destroy thường là thao tác đặc quyền. Test cần xác minh:

- Principal không có quyền bị từ chối.
- Principal chỉ có quyền disable không thể destroy.
- Principal chỉ có quyền sử dụng key không thể sửa policy hoặc hủy key.
- Requester không thể tự phê duyệt nếu separation of duties yêu cầu người độc lập.
- Approval gắn đúng key ID/version, lý do, ticket và thời hạn.
- Approval cũ không thể tái sử dụng cho key khác hoặc một request đã thay đổi.
- Grant JIT hết hạn thì request destroy tiếp theo bị từ chối.
- Audit ghi cả quyết định allow và deny.

Không cấp quyền destroy chỉ vì người dùng cần dọn một alias hoặc đóng một test. Hãy tách quyền delete reference, disable, schedule deletion, cancel deletion và destroy nếu nền tảng hỗ trợ.

Với key trọng yếu, quy trình có thể yêu cầu hai người phê duyệt hoặc quorum. Test cần xác minh một approval đơn lẻ không đủ để thực hiện lệnh cuối và việc thay đổi danh tính người phê duyệt không thể bị giả mạo qua request payload.

## 7. Kiểm tra schedule deletion và cửa sổ chờ

Một số KMS có cơ chế schedule deletion với thời gian chờ trước khi vật liệu bị hủy. Cửa sổ này giúp phát hiện yêu cầu nhầm và cho phép cancel theo policy.

Test cần xác minh:

- Thời gian chờ nằm trong giới hạn được policy cho phép.
- Key chuyển sang trạng thái pending deletion đúng lúc.
- Operation mới bị chặn hoặc được cho phép đúng theo semantics của dịch vụ.
- Cancel deletion chỉ được principal có quyền thực hiện.
- Cancel sau thời điểm không còn được phép phải bị từ chối.
- Sau khi hết cửa sổ, backend thực hiện destruction và trạng thái cuối được cập nhật.
- Thay đổi trạng thái được ghi vào audit log.
- Retry schedule deletion không vô tình thay đổi thời điểm hoặc key version ngoài dự kiến.

Không giả định mọi KMS đều có cửa sổ chờ hoặc cho phép hủy lịch. Test adapter phải mô hình hóa hành vi thực tế của nhà cung cấp và phân biệt trạng thái pending với trạng thái destroyed.

## 8. Kiểm tra zeroization trong HSM và provider

HSM có thể cung cấp lệnh xóa object, zeroize token/partition hoặc cơ chế hủy vật liệu khóa được bảo vệ. Phạm vi của từng thao tác rất khác nhau:

- Xóa một key object không giống zeroize toàn bộ partition.
- Zeroize partition có thể ảnh hưởng nhiều khóa và credential khác.
- Tamper response có thể hủy vật liệu theo cấu hình thiết bị.
- Provider có thể giữ handle hoặc session cache cần đóng trước khi xác minh kết quả.

Không dùng thao tác zeroize toàn partition trong test thông thường nếu partition chứa tài nguyên khác. Chỉ kiểm thử trên partition chuyên dụng và theo quy trình của nhà cung cấp.

Bằng chứng kiểm thử có thể gồm trạng thái object không còn tồn tại, thao tác sử dụng bị từ chối, metadata provider xác nhận object đã bị xóa, audit event của HSM và chứng từ/attestation theo khả năng thiết bị. Unit test không thể đọc bộ nhớ HSM để tự chứng minh từng bit đã bị ghi đè.

Với khóa non-exportable, việc không lấy được byte từ API không tự chứng minh khóa đã bị hủy. Cần kiểm tra object state, khả năng thực hiện operation và bằng chứng destruction từ provider.

## 9. Crypto erasure và dữ liệu phụ thuộc

**Crypto erasure** là phương pháp làm dữ liệu đã mã hóa không thể giải mã bằng cách hủy vật liệu khóa cần thiết để giải mã, thay vì ghi đè từng byte dữ liệu trên mọi thiết bị lưu trữ.

Crypto erasure chỉ đạt mục tiêu khi:

- Dữ liệu được mã hóa bằng thuật toán và quy trình phù hợp.
- Khóa cần thiết để giải mã đã được xác định đầy đủ.
- Không còn bản sao key material hoặc bản sao khóa dẫn xuất có thể dùng để giải mã.
- Backup, snapshot, replica và archive không giữ bản sao khóa còn hiệu lực.
- Encrypted DEK không thể unwrap bằng một KEK hoặc bản sao KEK còn tồn tại.
- Không còn plaintext hoặc bản sao dữ liệu rõ ở hệ thống khác ngoài phạm vi đã xử lý.

Trong envelope encryption, một DEK mã hóa dữ liệu; KEK bảo vệ DEK. Hủy KEK có thể làm encrypted DEK không thể unwrap, nhưng nếu DEK từng được export và lưu ở nơi khác thì dữ liệu vẫn có thể giải mã. Nếu có nhiều KEK version hoặc nhiều bản bọc DEK, cần xử lý tất cả đường giải mã.

Test crypto erasure cần xác minh dependency graph và thử khôi phục từ các bản sao thử nghiệm theo kịch bản đã định. Không được kết luận dữ liệu đã bị xóa chỉ vì một request decrypt qua KMS trả lỗi; có thể còn bản sao khóa hoặc plaintext ở nơi khác.

## 10. Kiểm tra replica, backup và restore

Một khóa có thể được sao chép hoặc nhân bản qua nhiều vùng. Destruction test cần xác minh propagation và semantics của từng bản:

- Replica có nhận trạng thái disable/destroy trong thời gian dự kiến không?
- Nếu replica tạm mất kết nối, khi phục hồi có đồng bộ trạng thái mới nhất không?
- Backup có chứa key material hay chỉ metadata/reference?
- Backup của HSM/KMS được mã hóa và bảo vệ bởi khóa nào?
- Restore có thể làm xuất hiện lại key đã bị destroy không?
- Quy trình restore có kiểm tra tombstone hoặc trạng thái thu hồi không?
- Bản sao lưu cũ có thể khôi phục một credential hoặc key version đã bị hủy không?

Một hệ thống tốt phải tránh việc restore dữ liệu metadata cũ làm sống lại key đã bị hủy. Nếu backend có backup key material được bảo vệ, cần hiểu rõ chính sách retention và destruction của bản backup đó.

Test restore nên chạy trên môi trường thử nghiệm. Không khôi phục backup production vào môi trường không được kiểm soát chỉ để thử xem khóa có quay lại hay không.

## 11. Kiểm tra sau khi hủy

Sau khi backend báo hủy thành công, cần xác minh ở nhiều lớp:

1. **State:** metadata chuyển sang trạng thái destroyed hoặc trạng thái cuối tương đương.
2. **Lookup:** key ID/version không còn được phân giải như một khóa đang hoạt động.
3. **Operation:** Encrypt, Decrypt, Sign, Verify hoặc MAC bằng key đã hủy bị từ chối theo semantics của backend.
4. **Alias:** alias không còn trỏ tới key đã hủy; alias có thể được gắn với version mới nếu policy cho phép.
5. **Cache/session:** handle, session và cache cũ không tiếp tục thực hiện thao tác.
6. **Replica:** trạng thái cuối được đồng bộ tới các bản sao.
7. **Backup/restore:** không có đường khôi phục trái với chính sách destruction.
8. **Audit:** có request, approval, kết quả và bằng chứng xác nhận.
9. **Dependency:** dữ liệu phụ thuộc đã được xử lý hoặc có quyết định retention được phê duyệt.

Một số backend trả lỗi khác nhau khi key không tồn tại, bị disable hoặc không có quyền. Test cần xác minh kết quả cuối bằng metadata và audit, không chỉ kiểm tra exception message.

Không được tiếp tục dùng ciphertext thật để thử giải mã sau destruction. Dùng dữ liệu test được tạo riêng cho key fixture và bảo đảm dữ liệu đó không có giá trị nghiệp vụ.

## 12. Kiểm tra cache, handle và object trong Java

Trong Java, cần phân biệt hủy object key trong bộ nhớ với hủy khóa bền vững trong KeyStore, KMS hoặc HSM.

- Interface **javax.security.auth.Destroyable** cho phép một số object hỗ trợ yêu cầu destroy và kiểm tra trạng thái destroyed.
- **KeyStore.deleteEntry(alias)** xóa entry khỏi keystore theo semantics của provider; không phải bằng chứng độc lập rằng mọi bản sao vật lý của key material đã bị zeroize.
- Một object Key có thể chỉ là handle tới khóa trong HSM. Xóa object Java không nhất thiết xóa key object trong thiết bị.
- Provider session, cache hoặc connection cần được đóng hoặc làm mới theo hướng dẫn của provider.

Ví dụ kiểm tra một object hỗ trợ Destroyable:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import javax.security.auth.DestroyFailedException;
import javax.security.auth.Destroyable;
import org.junit.jupiter.api.Test;

class DestroyableKeyObjectTest {
    @Test
    void destroyableObjectReportsDestroyedState() throws Exception {
        Destroyable keyObject = new TestDestroyableKey();

        assertFalse(keyObject.isDestroyed());

        keyObject.destroy();

        assertTrue(keyObject.isDestroyed());
        assertThrows(
            DestroyFailedException.class,
            keyObject::destroy
        );
    }

    private static final class TestDestroyableKey implements Destroyable {
        private boolean destroyed;

        @Override
        public void destroy() throws DestroyFailedException {
            if (destroyed) {
                throw new DestroyFailedException("Object đã bị hủy");
            }
            destroyed = true;
        }

        @Override
        public boolean isDestroyed() {
            return destroyed;
        }
    }
}
~~~

Đây là test cho contract của một object Java minh họa. Nó không kiểm tra zeroization của HSM hoặc xóa entry trong persistent KeyStore. Implementation thật có thể xử lý lệnh destroy lặp lại khác nhau; test cần tuân theo contract của lớp/provider thay vì mặc định mọi lần gọi thứ hai đều phải ném exception.

## 13. Integration test destruction qua một adapter

Ứng dụng nên bao thao tác hủy trong một adapter để có thể kiểm thử state transition, quyền và kết quả của backend. Ví dụ dưới đây minh họa contract ở cấp ứng dụng:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class KeyDestructionServiceTest {
    enum State {
        ACTIVE,
        PENDING_DELETION,
        DESTROYED
    }

    interface KeyAdmin {
        State state(String keyId);

        void destroy(String keyId) throws Exception;
    }

    interface KeyUsage {
        byte[] decrypt(String keyId, byte[] ciphertext) throws Exception;
    }

    static class KeyUnavailableException extends Exception {
        KeyUnavailableException(String message) {
            super(message);
        }
    }

    @Test
    void destroyedKeyCannotBeUsed() throws Exception {
        String testKeyId = "test-run-42/key-001";
        KeyAdmin admin = new InMemoryKeyAdmin();
        KeyUsage usage = new InMemoryKeyUsage(admin);

        assertEquals(State.ACTIVE, admin.state(testKeyId));

        admin.destroy(testKeyId);

        assertEquals(State.DESTROYED, admin.state(testKeyId));
        assertThrows(
            KeyUnavailableException.class,
            () -> usage.decrypt(testKeyId, new byte[] {1, 2, 3})
        );
    }

    private static final class InMemoryKeyAdmin implements KeyAdmin {
        private State state = State.ACTIVE;

        @Override
        public State state(String keyId) {
            return state;
        }

        @Override
        public void destroy(String keyId) {
            state = State.DESTROYED;
        }
    }

    private static final class InMemoryKeyUsage implements KeyUsage {
        private final KeyAdmin admin;

        private InMemoryKeyUsage(KeyAdmin admin) {
            this.admin = admin;
        }

        @Override
        public byte[] decrypt(String keyId, byte[] ciphertext)
                throws Exception {
            if (admin.state(keyId) == State.DESTROYED) {
                throw new KeyUnavailableException("Key is destroyed");
            }
            return ciphertext.clone();
        }
    }
}
~~~

Ví dụ dùng in-memory fake để kiểm tra logic ứng dụng. Nó không thay thế integration test với KMS/HSM. Test backend thật cần tạo một key dùng một lần trong môi trường cô lập, mã hóa dữ liệu giả, hủy key rồi xác minh lookup và operation bị từ chối theo contract của dịch vụ.

Không dùng mock để tuyên bố vật liệu khóa đã bị xóa vật lý. Mock chỉ chứng minh ứng dụng xử lý trạng thái mà adapter trả về đúng như thiết kế.

## 14. Negative test, idempotency và concurrency

Destruction là thao tác đặc quyền và có thể bị gọi lại khi retry. Cần kiểm tra các tình huống:

| Tình huống | Kết quả mong đợi |
|---|---|
| Principal không có quyền destroy | Access denied, key giữ nguyên trạng thái |
| Chỉ có quyền disable | Không thể destroy |
| Thiếu approval bắt buộc | Request không được thực hiện |
| Approval gắn key ID khác | Từ chối request |
| Key đã destroyed | Không tạo lại key hoặc ảnh hưởng key khác |
| Gửi destroy lặp lại | Kết quả xác định theo contract, không phá trạng thái khác |
| Hai request destroy đồng thời | Chỉ một state transition hợp lệ, audit nhất quán |
| Backend timeout sau khi nhận request | Tra cứu trạng thái trước khi retry |
| Replica chưa đồng bộ | Không báo hoàn tất toàn hệ thống quá sớm |
| Backup restore chứa trạng thái cũ | Tombstone hoặc control plane ngăn key sống lại |

Khi request timeout, không thể giả định backend chưa thực hiện thao tác. Hãy truy vấn trạng thái và request ID trước khi gửi lại. Retry mù có thể gây nhầm lẫn nếu API không idempotent hoặc alias đã được trỏ sang version khác.

Concurrency test cần xác minh hai thao tác disable/destroy hoặc cancel/destroy không tạo ra trạng thái không xác định. Dùng key fixture riêng cho từng test và tránh chạy các thao tác phá hủy song song trên cùng tài nguyên.

## 15. Audit, bằng chứng và báo cáo destruction

Một destruction event nên ghi nhận:

- Key ID và version đã được xử lý.
- Loại thao tác: disable, revoke, schedule deletion, cancel hoặc destroy.
- Principal yêu cầu và principal phê duyệt.
- Lý do, ticket/change record và thời điểm.
- Policy version hoặc approval reference.
- Backend, provider, HSM partition hoặc KMS resource.
- Request ID, correlation ID và kết quả.
- Trạng thái trước/sau và thời điểm replica đồng bộ.
- Kết quả kiểm tra operation sau khi hủy.
- Kết quả cleanup, backup/replica verification và ngoại lệ còn tồn tại.

Không ghi key material, private key, secret, plaintext hoặc dữ liệu nhạy cảm vào audit event. Audit log cần được lưu ở hệ thống có quyền truy cập tách biệt và cơ chế chống sửa đổi phù hợp.

Báo cáo test nên lưu resource ID, trạng thái, thời gian, mã kết quả, bằng chứng provider và các bước xác minh. Không lưu byte khóa hoặc export key để “chứng minh” việc hủy. Nếu nhà cung cấp có destruction attestation hoặc chứng từ zeroization, liên kết tham chiếu tới bằng chứng đó theo quy trình lưu trữ.

## 16. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hệ quả | Cách phòng tránh |
|---|---|---|
| Coi xóa alias là hủy key material | Khóa có thể vẫn tồn tại và được truy cập qua ID khác | Kiểm tra trạng thái object và khả năng sử dụng |
| Coi disable là destroy | Key có thể được enable lại | Kiểm tra đúng state transition và semantics |
| Chỉ test một replica | Bản sao khác vẫn có thể dùng key | Kiểm tra propagation và trạng thái toàn hệ thống |
| Bỏ qua backup và snapshot | Khóa hoặc đường giải mã có thể được khôi phục | Kiểm kê backup, restore và retention |
| Coi lỗi decrypt là bằng chứng zeroization | Có thể chỉ là access denied hoặc key tạm thời unavailable | Đối chiếu metadata, audit và bằng chứng provider |
| Xóa KEK nhưng quên bản sao DEK | Dữ liệu vẫn có thể giải mã | Kiểm kê mọi bản sao và đường unwrap |
| Dùng zeroize toàn partition cho test nhỏ | Hủy các khóa và credential không liên quan | Dùng partition thử nghiệm riêng |
| Retry destroy sau timeout mà không tra trạng thái | Request lặp hoặc tác động nhầm tài nguyên | Tra cứu trạng thái và dùng request ID |
| Restore backup cũ làm sống lại key | Vi phạm mục tiêu destruction | Dùng tombstone và kiểm tra trạng thái control plane |
| Log key bytes trong test report | Tạo thêm bản sao bí mật | Chỉ lưu metadata và evidence reference |

## 17. Nguyên tắc triển khai an toàn

- Phân biệt rõ disable, revoke, schedule deletion, delete reference và destroy.
- Chỉ chạy destructive test trên key thử nghiệm có owner, tag và môi trường cô lập.
- Xác minh quyền, approval, separation of duties và JIT grant trước lệnh hủy.
- Kiểm tra state transition, cửa sổ chờ, cancel và trạng thái cuối theo contract của backend.
- Kiểm tra HSM zeroization bằng metadata, operation denial và evidence của provider; không tự tuyên bố đã chứng minh từng bit vật lý.
- Kiểm kê replica, backup, snapshot, cache, export và encrypted DEK trước khi kết luận crypto erasure.
- Xác minh key không thể được sử dụng lại sau destruction và backup restore không làm sống lại key.
- Giữ public key/certificate khi cần xác minh chữ ký cũ, dù private key đã bị hủy.
- Thiết kế test idempotency, timeout, concurrency, partial failure và cleanup.
- Ghi audit đầy đủ nhưng không ghi key material, secret hoặc plaintext.
- Phân biệt xóa object Java, xóa alias trong KeyStore và hủy persistent key trong KMS/HSM.
- Lưu bằng chứng destruction và retention theo chính sách; không giữ bản export khóa để làm bằng chứng.
- Không dùng unit test hoặc mock làm bằng chứng zeroization vật lý hay crypto erasure toàn hệ thống.

Test key destruction cần chứng minh hệ thống thực hiện đúng quy trình hủy theo semantics của provider và không còn đường sử dụng khóa trái phép trong phạm vi đã kiểm tra. Đánh giá đầy đủ phải bao gồm quyền, state transition, bản sao, replica, backup, cache, dữ liệu phụ thuộc và audit. Khi kết hợp test logic, integration test trên môi trường cô lập và bằng chứng từ KMS/HSM, tổ chức có thể giảm nguy cơ hủy nhầm khóa, bỏ sót bản sao hoặc tuyên bố crypto erasure khi vẫn còn đường giải mã.
