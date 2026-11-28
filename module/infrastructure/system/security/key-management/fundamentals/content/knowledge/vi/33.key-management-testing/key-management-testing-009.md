# Test key recovery: Kiểm thử khả năng khôi phục khóa mật mã

**Test key recovery** là hoạt động kiểm tra xem tổ chức có thể khôi phục và sử dụng lại khóa mật mã hợp lệ sau sự cố mất thiết bị, lỗi KMS/HSM, xóa nhầm, hỏng backup hoặc gián đoạn khu vực hay không. Một bài kiểm thử đạt yêu cầu phải chứng minh được quy trình phục hồi, quyền truy cập, metadata và các phụ thuộc đều hoạt động; chỉ nhìn thấy file backup hoặc nhận được phản hồi restore thành công chưa đủ để kết luận dữ liệu có thể giải mã.

Khóa mật mã thường bảo vệ dữ liệu trong thời gian dài hơn vòng đời của một máy chủ hoặc ứng dụng. Khi khóa bị mất, bản mã có thể trở nên không thể đọc. Khi khóa bị khôi phục sai phiên bản, ứng dụng có thể hoạt động nhưng không giải mã được dữ liệu cũ. Vì vậy, recovery test cần kiểm tra cả key material, key version, thuật toán, policy, wrapping hierarchy, quyền sử dụng và dữ liệu đã được mã hóa.

Trong quản lý khóa mật mã, khôi phục phải được thực hiện theo cơ chế được phê duyệt của KMS/HSM, backup system hoặc key escrow. Khóa nhạy cảm không nên được xuất ra môi trường kiểm thử chỉ để so sánh byte. Hãy xác minh bằng thao tác mật mã phù hợp, chẳng hạn giải mã một fixture đã biết, xác minh chữ ký hoặc mở gói một DEK thử nghiệm.

## 1. Mục tiêu của Test key recovery

Một recovery test cần trả lời được các câu hỏi:

- Backup có tồn tại, còn nguyên vẹn và thuộc đúng key ID/version không?
- Backup được tạo từ nguồn tin cậy và được bảo vệ khỏi sửa đổi, xóa hoặc truy cập trái phép không?
- Có đủ metadata, thuật toán, provider, wrapping key, policy và thông tin phụ thuộc để phục hồi không?
- Người vận hành có thể thực hiện restore bằng đúng danh tính và quy trình phê duyệt không?
- HSM/KMS hoặc hệ thống đích có khôi phục được khóa trong trạng thái và mục đích mong muốn không?
- Ứng dụng có thể thực hiện thao tác mật mã cần thiết bằng khóa đã khôi phục không?
- Dữ liệu cũ, DEK đã wrap, chữ ký hoặc chứng thư có tiếp tục hoạt động theo yêu cầu không?
- Thời gian phục hồi có đáp ứng RTO và mức mất dữ liệu có đáp ứng RPO không?
- Audit log có ghi nhận ai đã yêu cầu, phê duyệt, thực hiện và xác minh quá trình không?

Recovery test còn giúp phát hiện các giả định sai: bản sao chỉ có metadata mà thiếu key material, backup phụ thuộc một KEK khác đã bị hủy, HSM backup không thể restore sang security domain đích, hoặc quyền decrypt đã bị thu hồi sau khi đổi role.

## 2. Phân biệt recovery, restore, rotation, rekey và regeneration

Các thao tác này có mục tiêu khác nhau:

| Thuật ngữ | Ý nghĩa | Có giữ nguyên khả năng xử lý dữ liệu cũ không? |
|---|---|---|
| Backup | Tạo bản sao được bảo vệ của key material hoặc trạng thái cần thiết để phục hồi. | Chưa tự chứng minh; cần kiểm tra backup và dependency. |
| Restore | Đưa khóa hoặc bản sao khóa từ backup vào môi trường đích. | Có thể, nếu đúng key material/version và còn đủ wrapping dependency. |
| Recovery | Quy trình đầu-cuối để khôi phục khả năng sử dụng khóa và dịch vụ. | Có, nếu recovery thành công và policy cho phép. |
| Rotation | Chuyển sang phiên bản khóa mới theo cryptoperiod hoặc policy. | Thường vẫn cần giữ khóa cũ để xử lý dữ liệu cũ. |
| Rekey | Tạo cặp khóa hoặc key material mới, thường do thay đổi chính sách hoặc nghi ngờ compromise. | Không tự khôi phục dữ liệu cũ; cần re-encrypt/rewrap hoặc giữ khóa cũ hợp lệ. |
| Regeneration | Tạo lại khóa bằng quy trình sinh khóa. | Chỉ tương đương khóa cũ nếu thiết kế dẫn xuất xác định và giữ đúng secret gốc/tham số; khóa ngẫu nhiên mới không thay thế khóa cũ. |

Tạo một khóa AES mới cùng thuật toán và kích thước không giúp giải mã ciphertext được mã hóa bằng khóa AES cũ. Tương tự, tạo một cặp RSA mới không thể tạo ra chữ ký hợp lệ tương ứng với private key đã mất. Nếu key material gốc không thể phục hồi và không có bản sao hợp lệ, dữ liệu có thể mất khả năng truy cập vĩnh viễn.

## 3. Phạm vi kiểm thử theo loại khóa

Mỗi loại khóa cần một tiêu chí khôi phục phù hợp:

| Loại khóa | Cách backup thường gặp | Kiểm tra recovery |
|---|---|---|
| KEK trong KMS | KMS-managed backup, replication hoặc cơ chế export/backup được hỗ trợ. | Xác minh quyền wrap/unwrap và mở gói DEK thử nghiệm đã lưu. |
| HSM key object | Secure backup theo vendor, cluster replication hoặc backup domain. | Restore vào HSM/partition đích rồi thực hiện sign, verify, unwrap hoặc thao tác được phép. |
| DEK | Wrapped DEK được lưu cùng ciphertext và metadata. | Dùng KEK đã phục hồi để unwrap DEK rồi giải mã fixture hoặc dữ liệu thử. |
| Signing private key | HSM secure backup hoặc key escrow được phê duyệt nếu policy cho phép. | Ký challenge mới bằng khóa khôi phục và xác minh bằng public key đã lưu. |
| HMAC key | KMS/HSM backup hoặc backup package được bảo vệ. | Tạo/verify MAC cho fixture đã biết bằng API được phép. |
| TLS private key | HSM backup hoặc keystore backup được mã hóa và kiểm soát. | Chứng minh private key khớp certificate, sau đó kiểm thử TLS handshake trong môi trường cô lập. |
| CA key | HSM backup với quorum, split knowledge và thủ tục khôi phục nghiêm ngặt. | Kiểm thử trong môi trường PKI riêng, xác minh chữ ký CA và quy trình kiểm soát quyền. |

Không phải mọi khóa đều nên được backup hoặc export. Một số khóa dùng cho phiên ngắn hoặc dữ liệu tạm có thể được thiết kế để không phục hồi; khi mất, dữ liệu tương ứng được loại bỏ theo policy. Quyết định này cần được ghi rõ trong key policy và data retention policy.

## 4. Các mô hình backup và recovery

### KMS-managed backup và replication

KMS có thể quản lý tính bền vững, replication, multi-region key hoặc backup nội bộ. Cần hiểu semantics của dịch vụ:

- Replication có tự động lan truyền thao tác disable/delete không?
- Bản sao có cùng key material hay chỉ có cấu hình tương đương?
- Key ID, alias, version và policy có giữ nguyên ở region đích không?
- Có thể restore sau khi xóa nhầm hay replication cũng đã đồng bộ thao tác xóa?
- Recovery phụ thuộc account, project, region, tenant hoặc external key store nào?

Replication giúp tăng khả năng sẵn sàng, nhưng không nhất thiết thay thế backup độc lập. Nếu thao tác xóa hoặc thay đổi policy được đồng bộ sang mọi replica, một bản backup độc lập hoặc cơ chế recovery khác có thể vẫn cần thiết.

### HSM secure backup

HSM thường cung cấp cơ chế backup/restore riêng, có thể gắn với backup key, security domain, cloning domain hoặc thiết bị backup chuyên dụng. Chỉ dùng cơ chế được vendor hỗ trợ. Không tự trích xuất bộ nhớ thiết bị hoặc sao chép file nội bộ của HSM để tạo backup.

Các điểm phải kiểm tra:

- Backup được mã hóa và xác thực bằng cơ chế của HSM/vendor.
- Backup chỉ restore được trong security domain hoặc cluster được phép.
- Backup key và các thành phần quorum được bảo vệ độc lập.
- Có đủ operator, smart card hoặc thành phần phần cứng cần thiết.
- Firmware, model, partition và policy tương thích với thiết bị đích.
- Quy trình khôi phục có log và kiểm soát dual control.

### Encrypted key backup và key escrow

Một số hệ thống cho phép backup key package đã mã hóa bằng một khóa bảo vệ khác. Key escrow là cơ chế lưu giữ có kiểm soát để khôi phục trong tình huống được phê duyệt. Escrow làm tăng khả năng phục hồi nhưng cũng tạo thêm mục tiêu có giá trị cao cho kẻ tấn công.

Backup package, wrapping key, recovery credential và bản ghi escrow phải được bảo vệ tách biệt. Không đặt bản backup cùng khóa dùng để mở nó ở cùng một nơi hoặc cùng một quyền truy cập nếu điều đó làm mất ý nghĩa phân tách.

### Split knowledge và M-of-N

Với khóa quan trọng, có thể chia quyền khôi phục cho nhiều người hoặc nhiều thành phần, yêu cầu tối thiểu M trong N phần tham gia. Ví dụ, 2 trong 3 custodian phải hiện diện để hoàn tất thao tác recovery.

Split knowledge là cơ chế kiểm soát tổ chức và kỹ thuật. Không tự chia chuỗi khóa bằng cách cắt chuỗi hoặc viết script tự chế. Dùng cơ chế backup/quorum được HSM hoặc giải pháp escrow hỗ trợ, kiểm tra việc tạo và phục hồi shares trong môi trường thử nghiệm, và bảo đảm mỗi share không đủ để khôi phục khóa một mình.

## 5. Thiết kế chiến lược backup trước khi kiểm thử

Recovery test chỉ có ý nghĩa nếu chiến lược backup được định nghĩa rõ. Với từng key class, hãy xác định:

- Khóa nào cần backup, khóa nào không được export và khóa nào có thể tái tạo an toàn.
- Backup frequency và sự kiện phải tạo backup, ví dụ sau khi tạo khóa, import, rotate hoặc thay đổi wrapping hierarchy.
- Số phiên bản cần giữ và thời gian retention.
- Vị trí lưu: offline, immutable storage, vùng địa lý khác hoặc hệ thống backup riêng.
- Cơ chế mã hóa, integrity check và xác thực nguồn.
- Principal được phép tạo, đọc, restore và hủy backup.
- Số custodian, quorum và quy trình phê duyệt.
- Dependency: KEK, backup key, HSM domain, KMS account, metadata, certificate chain và policy.
- RPO/RTO, người chịu trách nhiệm và thứ tự phục hồi.

Backup phải tương thích với dữ liệu đã mã hóa. Nếu tổ chức giữ ciphertext trong 10 năm nhưng chỉ giữ DEK/KEK trong 2 năm, dữ liệu sau thời hạn khóa có thể không giải mã được. Retention của key version cần được xem xét cùng retention của dữ liệu và yêu cầu pháp lý.

## 6. Metadata và dependency cần phục hồi cùng khóa

Chỉ backup key material có thể chưa đủ. Một bản ghi recovery nên lưu các thông tin không bí mật cần thiết để nhận diện và sử dụng khóa:

| Metadata | Tại sao cần |
|---|---|
| Key ID, alias, version | Xác định chính xác tài sản và phiên bản. |
| Algorithm, key size, curve | Chọn provider và thao tác tương thích. |
| Purpose/key usage | Ngăn dùng khóa sai mục đích sau restore. |
| Owner, tenant, environment | Khôi phục quyền và phạm vi sở hữu. |
| Provider, HSM partition, KMS region/account | Xác định backend và nơi restore hợp lệ. |
| Exportability và protection level | Giữ nguyên yêu cầu bảo vệ key material. |
| Wrapping hierarchy | Xác định KEK hoặc backup key cần có trước. |
| Key version và rotation history | Hỗ trợ dữ liệu cũ, ciphertext và signature lịch sử. |
| Certificate, public key fingerprint | Xác minh danh tính và cặp khóa. |
| Policy, grants và principal mapping | Phục hồi quyền truy cập đúng phạm vi. |
| Nonce/IV, tag, AAD/encryption context metadata | Cung cấp tham số cần thiết để giải mã dữ liệu đúng. |
| Backup ID, created_at, integrity result | Truy vết bản backup và kiểm tra tính toàn vẹn. |

Không lưu plaintext key material, password hoặc recovery share trong metadata registry. Nếu metadata chứa thông tin nhạy cảm về cấu trúc hệ thống, áp dụng quyền truy cập và audit tương ứng.

### Dependency graph

Với envelope encryption, thứ tự phục hồi có thể là:

~~~text
Backup key / HSM security domain
             |
             v
          KEK
             |
             v
     Wrapped DEK / key version
             |
             v
        Plaintext DEK
             |
             v
       Ciphertext data
~~~

Nếu KEK được wrap hoặc backup bằng một khóa cấp cao hơn, phải phục hồi chuỗi từ gốc xuống. Không thể unwrap DEK nếu KEK hoặc backup domain cần thiết vẫn chưa khả dụng.

## 7. Chuẩn bị môi trường recovery test

Ưu tiên môi trường DR hoặc sandbox tách biệt với production. Môi trường thử nghiệm cần:

- KMS/HSM test account, partition hoặc cluster được chỉ định.
- Quyền restore tách khỏi quyền sử dụng dữ liệu production.
- Backup fixture hoặc bản sao đã được phê duyệt.
- Dữ liệu thử nghiệm không nhạy cảm, có ciphertext và expected result đã biết.
- Kết nối mạng, DNS, time synchronization và provider tương thích.
- Audit log độc lập và đồng hồ đồng bộ.
- Người vận hành, người phê duyệt và người xác minh được phân công.
- Cách cô lập và hủy tài nguyên sau test.

Không restore khóa production vào môi trường ít kiểm soát chỉ để kiểm tra. Nếu cần xác minh backup production, dùng bản sao backup được phê duyệt, thiết bị hoặc account recovery chuyên biệt và giới hạn quyền thao tác. Không đưa plaintext key ra ngoài ranh giới bảo vệ.

Trước test, ghi nhận trạng thái ban đầu: key ID/version, trạng thái backend, fingerprint public key nếu có, backup ID, policy version, dependency và thời gian bắt đầu. Đặt correlation ID để liên kết toàn bộ audit event.

## 8. Quy trình kiểm thử khôi phục đầu-cuối

Một recovery test có thể chia thành các bước:

1. **Chọn kịch bản:** xác định loại sự cố, key class, phạm vi và tiêu chí thành công.
2. **Xác minh backup:** kiểm tra nguồn, thời điểm tạo, version, integrity và retention.
3. **Phê duyệt:** xác minh người yêu cầu, custodian, quorum và quyền restore.
4. **Chuẩn bị backend:** kiểm tra HSM/KMS đích, security domain, provider, network và capacity.
5. **Khôi phục dependency:** phục hồi backup key, KEK hoặc domain cần thiết theo đúng thứ tự.
6. **Restore key:** dùng API hoặc quy trình chính thức của KMS/HSM/escrow.
7. **Khôi phục metadata và policy:** đăng ký key ID/version, purpose, owner, grants và các thuộc tính cần thiết.
8. **Kiểm tra trạng thái:** xác minh key usable/enabled và không bị revoke hoặc pending deletion ngoài dự kiến.
9. **Thực hiện cryptographic test:** sign/verify, decrypt fixture, unwrap DEK hoặc verify MAC.
10. **Kiểm tra authorization:** principal hợp lệ dùng được thao tác cần thiết; principal ngoài phạm vi bị từ chối.
11. **Đo RTO/RPO:** ghi thời gian và điểm backup phục hồi được.
12. **Đóng test:** lưu evidence, thu hồi quyền tạm thời và xử lý tài nguyên thử nghiệm theo policy.

Không chuyển khóa sang trạng thái production-active chỉ vì test restore thành công. Quyết định phục hồi production cần qua change/incident process, kiểm tra dependency thực tế và phê duyệt của owner.

## 9. Xác minh khóa khôi phục bằng thao tác mật mã

Không cần và không nên export khóa chỉ để so sánh bytes. Chọn phép thử theo loại khóa:

| Loại khóa | Phép kiểm tra |
|---|---|
| Symmetric DEK | Giải mã một ciphertext fixture đã tạo trước đó; kiểm tra plaintext và authentication tag. |
| KEK | Unwrap một DEK thử đã wrap bằng KEK; dùng DEK để giải mã fixture. |
| RSA/EC signing key | Ký challenge ngẫu nhiên sau restore và xác minh bằng public key/certificate đã lưu. |
| HMAC key | Verify MAC của fixture đã biết hoặc tạo MAC mới rồi đối chiếu ở phía verifier. |
| TLS private key | Kiểm tra public key trong certificate khớp key handle và thực hiện handshake trong môi trường test. |
| CA key | Ký certificate thử trong PKI test hierarchy và xác minh chain bằng trust anchor test. |

Với khóa đối xứng, ciphertext fixture cần lưu đủ nonce/IV, authentication tag, AAD/encryption context, thuật toán và version. Chỉ so sánh plaintext sau khi AEAD xác thực thành công; không bỏ qua lỗi tag hoặc tắt xác thực để test “cho qua”.

Với khóa bất đối xứng, public key fingerprint là bằng chứng nhận diện hữu ích. Tuy nhiên, thao tác ký challenge và verify là phép kiểm tra thực tế rằng private key được restore đúng và provider có thể sử dụng nó.

## 10. Test recovery cho envelope encryption

Envelope encryption tạo nhiều lớp phụ thuộc nên cần kiểm tra toàn bộ đường đi:

~~~text
Ciphertext + Wrapped DEK + Metadata
                 |
                 v
          KMS/HSM đã restore
                 |
                 v
          Unwrap DEK bằng KEK
                 |
                 v
          Plaintext DEK trong RAM
                 |
                 v
        AEAD decrypt + verify tag
                 |
                 v
          Expected plaintext
~~~

Các bước kiểm tra:

1. Chọn một fixture được mã hóa bằng DEK thuộc key version đang kiểm tra.
2. Xác nhận ciphertext, wrapped DEK, nonce, tag, AAD và metadata không bị thay đổi.
3. Khôi phục KEK hoặc KMS/HSM resource có thể unwrap DEK.
4. Gọi unwrap bằng principal được phép và encryption context chính xác.
5. Giải mã ciphertext bằng DEK trong bộ nhớ.
6. So sánh kết quả với expected plaintext hoặc hash của fixture.
7. Xóa buffer DEK theo khả năng kiểm soát của runtime và đóng session.
8. Thử negative case: sai context, sai principal, sai key version hoặc ciphertext bị sửa phải thất bại.

Nếu wrapped DEK được tạo với encryption context, context phải khớp chính xác theo semantics của KMS. Việc thiếu hoặc đổi context có thể khiến unwrap bị từ chối ngay cả khi KEK đã restore đúng.

## 11. Test recovery cho HSM và khóa ký

Với HSM, recovery test phải xác minh cả thiết bị, domain, quorum và key object:

- HSM đích thuộc security domain phù hợp.
- Firmware, partition, backup format và cơ chế restore tương thích.
- Custodian hoặc quorum cần thiết có mặt theo quy trình.
- Backup package hợp lệ và được xác thực.
- Key attributes như sign, decrypt, wrap, unwrap và extractability được giữ đúng.
- Key label/ID được liên kết đúng với metadata registry.
- Audit log của thiết bị ghi nhận operator, thao tác và kết quả.

Đối với khóa ký:

1. Lấy public key/certificate đã lưu trước sự cố.
2. Restore private key bằng cơ chế HSM/vendor.
3. Tạo challenge mới ngẫu nhiên trong test harness.
4. Yêu cầu HSM ký challenge bằng key handle đã restore.
5. Xác minh chữ ký bằng public key đã lưu.
6. Xác minh policy từ chối export private key và các thao tác không được phép.

Không dùng chữ ký cũ làm phép thử duy nhất: chữ ký cũ có thể được xác minh bằng public key mà không cần private key. Cần tạo chữ ký mới bằng private key sau restore để chứng minh thao tác ký hoạt động.

## 12. Test recovery cho Java KeyStore và ứng dụng

Với khóa phần mềm được lưu trong JKS hoặc PKCS#12, cần kiểm tra:

- Backup file và checksum/integrity metadata khớp bản đã lưu.
- File được bảo vệ bằng cơ chế mã hóa và quyền truy cập phù hợp.
- Keystore type, provider, alias và certificate chain được nhận diện đúng.
- Ứng dụng có thể nạp keystore bằng credential được quản lý an toàn.
- Private key entry có certificate chain phù hợp.
- Key pair có thể thực hiện thao tác sign hoặc decrypt thử nghiệm.
- Ứng dụng dùng đúng alias/key version và không fallback sang khóa khác ngoài ý muốn.

Ví dụ Java dưới đây minh họa việc kiểm tra một certificate entry và thực hiện kiểm tra thời hạn. Nó không đọc hoặc xuất private key:

~~~java
import java.security.KeyStore;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;
import java.time.Instant;
import java.util.Date;

public static X509Certificate loadAndCheckCertificate(
        KeyStore keyStore,
        String alias) throws Exception {

    Certificate certificate = keyStore.getCertificate(alias);
    if (!(certificate instanceof X509Certificate x509)) {
        throw new IllegalStateException(
                "Không tìm thấy X.509 certificate cho alias");
    }

    x509.checkValidity(Date.from(Instant.now()));
    return x509;
}
~~~

Kiểm tra certificate không chứng minh private key có thể ký. Trong test tích hợp, hãy thực hiện challenge sign/verify qua provider hoặc HSM handle. Mật khẩu keystore nên được lấy từ secret manager hoặc cơ chế credential được phê duyệt, không hard-code trong source code hoặc log.

Ví dụ sau minh họa phép thử cho khóa ký đã restore. Backend trả về một PrivateKey handle từ provider; với HSM provider, handle có thể đại diện cho khóa không exportable và thao tác ký được thực hiện bên trong thiết bị:

~~~java
import java.security.GeneralSecurityException;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;

public static void verifyRestoredSigningKey(
        PrivateKey restoredKeyHandle,
        PublicKey archivedPublicKey,
        String signatureAlgorithm) throws GeneralSecurityException {

    byte[] challenge = new byte[32];
    new SecureRandom().nextBytes(challenge);

    Signature signer = Signature.getInstance(signatureAlgorithm);
    signer.initSign(restoredKeyHandle);
    signer.update(challenge);
    byte[] signatureBytes = signer.sign();

    Signature verifier = Signature.getInstance(signatureAlgorithm);
    verifier.initVerify(archivedPublicKey);
    verifier.update(challenge);
    if (!verifier.verify(signatureBytes)) {
        throw new GeneralSecurityException(
                "Khóa sau restore không khớp public key đã lưu");
    }
}
~~~

signatureAlgorithm phải lấy từ profile đã phê duyệt và tương thích với cặp khóa, ví dụ SHA256withRSA hoặc SHA256withECDSA. Không lấy thuật toán tùy ý từ request chưa được xác thực. Ví dụ chỉ kiểm tra khả năng ký và tính khớp với public key; backend restore, policy, quyền truy cập và audit vẫn phải được kiểm tra riêng.

## 13. Kiểm tra quyền và separation of duties

Recovery là thao tác nhạy cảm vì người thực hiện có thể đưa một khóa có giá trị cao trở lại trạng thái sử dụng. Kiểm thử cần bao gồm:

- Principal không có quyền restore phải bị từ chối.
- Một custodian đơn lẻ không thể vượt quorum M-of-N.
- Người yêu cầu không thể tự phê duyệt nếu policy yêu cầu độc lập.
- Operator chỉ được restore vào backend/partition được phép.
- Workload sau restore chỉ có operation cần thiết.
- Quyền export, grant, change policy và destroy vẫn bị giới hạn.
- Quyền tạm thời được thu hồi sau test.
- Audit event ghi nhận actor, approval, backup ID, key ID, version và kết quả.

Không dùng tài khoản quản trị toàn quyền để đơn giản hóa recovery test. Nếu test bằng quyền quá rộng, kết quả không chứng minh được quy trình production có thể vận hành an toàn theo least privilege.

## 14. Test các tình huống lỗi và negative cases

Một bài test đầy đủ cần cố ý kiểm tra trường hợp thất bại:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Backup bị sửa hoặc checksum không khớp | Từ chối restore và tạo audit event/cảnh báo. |
| Backup thuộc sai key ID hoặc version | Dừng quy trình, không ghi đè tài sản khác. |
| Thiếu một recovery share trong quorum | Không thể hoàn tất restore. |
| Sai wrapping key hoặc backup domain | Restore/unwrap thất bại có kiểm soát. |
| HSM đích không tương thích | Dừng trước khi làm thay đổi trạng thái không thể đảo ngược. |
| Principal không có quyền | Request bị deny và được audit. |
| Approval hết hạn hoặc sai phạm vi | Không thực hiện restore. |
| Metadata thiếu algorithm hoặc purpose | Đưa workflow vào trạng thái chờ xử lý, không kích hoạt khóa. |
| Key version đã bị revoke | Không tự động bật lại; cần policy/incident decision. |
| Ciphertext hoặc AEAD tag bị sửa | Decrypt phải thất bại xác thực. |
| Encryption context không khớp | Unwrap/decrypt bị từ chối. |
| Backup cũ hơn RPO cho phép | Báo không đạt RPO và yêu cầu quyết định phục hồi. |
| Audit sink không khả dụng | Lưu event bền vững hoặc giữ workflow chưa hoàn tất theo policy. |
| Restore thành công nhưng ứng dụng không dùng được key | Không đánh dấu recovery hoàn tất; điều tra provider, policy và dependency. |

Không thử phá hủy hoặc làm hỏng backup production để kiểm tra negative case. Dùng bản sao fixture và môi trường được phê duyệt.

## 15. RPO, RTO và tiêu chí thành công

**RPO (Recovery Point Objective)** xác định mức dữ liệu hoặc thay đổi tối đa có thể mất khi phục hồi. Với key management, cần xác định backup gần nhất có bao gồm key version, metadata, policy và wrapping dependency cần thiết hay không.

**RTO (Recovery Time Objective)** xác định thời gian mục tiêu để khôi phục khả năng sử dụng dịch vụ. Thời gian này gồm phát hiện, phê duyệt, chuẩn bị HSM/KMS, restore, đăng ký metadata, cấp quyền, kiểm thử và chuyển ứng dụng.

Ví dụ tiêu chí cho một recovery exercise:

| Chỉ tiêu | Ví dụ mục tiêu |
|---|---|
| Backup integrity | 100% bản backup được chọn xác minh hợp lệ. |
| Key identity | Đúng key ID/version hoặc có mapping được phê duyệt nếu backend tạo resource ID mới. |
| Cryptographic validation | 100% fixture được xác minh đúng; negative cases bị từ chối. |
| Authorization | Chỉ principal và operation được phê duyệt hoạt động. |
| RTO | Hoàn tất trong thời gian đã thống nhất cho key class. |
| RPO | Không vượt quá thời điểm backup/version được policy cho phép. |
| Audit | Đủ request, approval, actor, backup reference, result và evidence. |
| Cleanup | Thu hồi quyền tạm thời và xử lý môi trường test theo policy. |

Các mục tiêu thời gian và tỷ lệ phải được tổ chức xác định theo mức quan trọng. Không lấy ví dụ trong bảng làm SLA chung cho mọi KMS/HSM hoặc mọi loại khóa.

## 16. Khôi phục theo các kịch bản sự cố

### Mất hoặc hỏng một HSM

1. Xác định thiết bị, partition, cluster và key class bị ảnh hưởng.
2. Kiểm tra trạng thái replica và khả năng tiếp tục dịch vụ.
3. Kích hoạt quy trình HSM backup/restore theo vendor.
4. Xác minh quorum, security domain và thiết bị đích.
5. Restore key object và metadata cần thiết.
6. Thực hiện cryptographic test và kiểm tra policy.
7. Chuyển traffic hoặc ứng dụng sang thiết bị đã khôi phục.
8. Theo dõi audit, latency, lỗi và trạng thái đồng bộ.

### Xóa nhầm khóa hoặc lên lịch deletion

Nếu khóa đang ở trạng thái pending deletion và nền tảng cho phép hủy lịch, thực hiện quy trình cancel/restore có phê duyệt. Sau đó xác minh backend đã trả khóa về trạng thái phù hợp và kiểm tra thao tác mật mã. Nếu key material đã bị hủy vĩnh viễn, chỉ có thể phục hồi từ backup hợp lệ nếu backup còn đủ dependency và được phép sử dụng.

### Mất KEK hoặc wrapping dependency

Khôi phục backup key hoặc KEK cấp trên trước, sau đó mới restore KEK và unwrap DEK. Kiểm tra đầy đủ version, encryption context, wrapping algorithm và metadata. Không tạo một KEK mới rồi giả định nó có thể unwrap các DEK cũ.

### Khôi phục sau thảm họa khu vực

1. Xác định region/account/project đích và quyền truy cập DR.
2. Kiểm tra KMS/HSM, network, identity provider và audit pipeline.
3. Restore wrapping hierarchy theo thứ tự.
4. Khôi phục key metadata, policy, grants và alias mapping.
5. Kiểm tra ứng dụng có thể decrypt/sign trong region DR.
6. Chuyển traffic theo DR plan và ghi nhận RTO/RPO.
7. Khi primary region trở lại, đối soát version và tránh split-brain hoặc ghi đè trạng thái mới hơn.

## 17. Xử lý khi khóa bị compromise

Không phải mọi sự cố đều nên khôi phục khóa cũ. Nếu key material bị nghi ngờ lộ, restore khóa đó vào production có thể đưa rủi ro trở lại.

Trong tình huống compromise:

- Cô lập principal, thiết bị hoặc đường truy cập nghi ngờ bị xâm nhập.
- Giữ audit evidence và xác định phạm vi key version/bản sao bị ảnh hưởng.
- Không đưa bản backup nghi ngờ bị xâm phạm trở lại môi trường production nếu chưa đánh giá.
- Tạo key pair hoặc key version mới theo policy.
- Rewrap DEK hoặc re-encrypt dữ liệu khi phù hợp.
- Thu hồi chứng thư, grant và credential liên quan.
- Kiểm tra bản backup, escrow và recovery share có bị truy cập trái phép không.
- Ghi rõ quyết định không restore khóa cũ và lý do.

Recovery test cần có ít nhất một kịch bản phân biệt **mất khóa** với **khóa bị compromise**. Mất khóa có thể yêu cầu restore key material gốc; compromise thường yêu cầu thay khóa và chuyển dữ liệu sang khóa mới, đồng thời giữ bằng chứng điều tra.

## 18. Audit, evidence và báo cáo recovery test

Một báo cáo kiểm thử nên ghi:

- Test ID, thời gian, môi trường và người tham gia.
- Key class, key ID/version hoặc mapping sau restore.
- Backup ID, timestamp, source, integrity result và retention.
- KMS/HSM/partition/region nguồn và đích.
- Approval, quorum/custodian và principal thực hiện.
- Trạng thái từng bước và lỗi phát sinh.
- Cryptographic test đã chạy, fixture ID và kết quả; không ghi key material hoặc plaintext nhạy cảm.
- Authorization positive/negative test.
- RTO, RPO thực tế và chênh lệch so với mục tiêu.
- Dependency còn thiếu, ngoại lệ và hành động khắc phục.
- Evidence reference từ KMS/HSM, audit system và test harness.

Audit log phải được bảo vệ khỏi sửa đổi, lưu độc lập với key resource và không chứa password, recovery share, private key, DEK hoặc plaintext dữ liệu. Fixture test nên dùng dữ liệu tổng hợp và được quản lý theo retention phù hợp.

## 19. Những sai lầm thường gặp

**Chỉ kiểm tra backup file tồn tại.** File có thể hỏng, sai version hoặc thiếu dependency. Cần restore thử và thực hiện thao tác mật mã.

**Coi restore API thành công là recovery hoàn tất.** Khóa có thể chưa có metadata, policy, grant hoặc quyền sử dụng đúng. Kiểm tra ứng dụng và authorization.

**Tạo khóa mới thay cho khóa đã mất.** Khóa ngẫu nhiên mới không giải mã được ciphertext cũ. Cần phục hồi key material gốc hoặc chấp nhận dữ liệu không thể giải mã theo policy.

**Không backup wrapping hierarchy.** Backup DEK hoặc KEK có thể vô dụng nếu khóa dùng để unwrap chúng không còn.

**Để backup và recovery key cùng một nơi.** Một sự cố hoặc tài khoản bị chiếm quyền có thể làm mất cả bản sao và phương tiện mở bản sao. Tách vùng lưu trữ và quyền.

**Không kiểm tra quorum.** Recovery có thể chỉ hoạt động khi một cá nhân giữ toàn bộ thành phần. Thử quy trình M-of-N và kiểm tra mỗi share riêng lẻ không đủ khôi phục.

**Restore khóa bị compromise vào production.** Khôi phục tính sẵn sàng nhưng tái tạo rủi ro. Phân biệt mất khóa với lộ khóa và có quyết định rekey.

**Không kiểm tra version cũ.** Dữ liệu lưu trữ có thể cần key version cũ nhiều năm sau khi version mới đã active. Giữ mapping và backup theo retention.

**Không kiểm thử quyền từ chối.** Một principal có thể restore nhưng cũng có thể export hoặc destroy ngoài ý muốn. Kiểm tra cả allow và deny.

**Không đo RTO/RPO.** Quy trình có thể hoạt động nhưng quá chậm hoặc dùng backup quá cũ so với yêu cầu nghiệp vụ.

## 20. Checklist Test key recovery

**Trước kiểm thử**

- [ ] Xác định key class, key ID/version, owner, purpose và phạm vi dữ liệu.
- [ ] Chọn kịch bản mất khóa, lỗi backend, xóa nhầm hoặc DR.
- [ ] Xác định backup ID, thời điểm, retention và dependency.
- [ ] Xác nhận backup integrity và nguồn tin cậy.
- [ ] Chuẩn bị môi trường cô lập, fixture và tiêu chí thành công.
- [ ] Có approval, custodian/quorum và người xác minh độc lập.

**Trong quá trình restore**

- [ ] Dùng cơ chế KMS/HSM/vendor được hỗ trợ.
- [ ] Khôi phục wrapping hierarchy theo đúng thứ tự.
- [ ] Restore metadata, version, policy và grant cần thiết.
- [ ] Không export hoặc log key material.
- [ ] Ghi audit event cho từng bước quan trọng.
- [ ] Kiểm tra trạng thái backend và mapping key ID.

**Sau khi restore**

- [ ] Thực hiện cryptographic test phù hợp loại khóa.
- [ ] Kiểm tra dữ liệu fixture và authentication tag.
- [ ] Kiểm tra sign/verify hoặc MAC theo loại khóa.
- [ ] Kiểm tra principal hợp lệ được phép và principal ngoài phạm vi bị từ chối.
- [ ] Đo RTO/RPO và đối chiếu mục tiêu.
- [ ] Thu hồi quyền tạm thời, đóng session và dọn môi trường test.
- [ ] Lưu báo cáo, evidence và hành động khắc phục.

## 21. Tần suất và chương trình recovery exercise

Tần suất phụ thuộc mức độ quan trọng của khóa, tốc độ thay đổi, retention và yêu cầu phục hồi. Một chương trình có thể gồm:

- Kiểm tra tự động integrity và khả năng đọc metadata sau mỗi lần backup.
- Thử restore định kỳ cho từng key class quan trọng.
- Thực hiện recovery exercise sau khi thay đổi KMS/HSM, firmware, backup format hoặc wrapping hierarchy.
- Kiểm thử sau khi thay đổi quorum, custodian, IAM policy hoặc DR region.
- Diễn tập khôi phục sau xóa nhầm và mất thiết bị.
- Kiểm thử định kỳ việc phục hồi dữ liệu cũ bằng key version cũ.

Không chỉ test khóa mới nhất. Cần chọn mẫu từ các key version cũ còn được yêu cầu để giải mã dữ liệu lưu trữ. Nếu có nhiều region, account, HSM partition hoặc CA, chọn mẫu đủ đại diện cho từng failure domain.

Sau mỗi lần test, cập nhật runbook, inventory, dependency graph, RTO/RPO và danh sách người có quyền recovery. Các lỗi lặp lại cần có owner, deadline và kiểm tra lại sau khi khắc phục.

Test key recovery chứng minh tổ chức có thể khôi phục khả năng sử dụng khóa theo đúng chính sách và thời gian yêu cầu. Bằng chứng mạnh nhất là thao tác mật mã thực tế thành công trên khóa đã restore, kết hợp kiểm tra quyền, metadata, dependency và negative case. Khi recovery exercise được thực hiện định kỳ trong môi trường cô lập, tổ chức giảm nguy cơ phát hiện quá muộn rằng backup không thể phục hồi hoặc khóa cũ không còn mở được dữ liệu.
