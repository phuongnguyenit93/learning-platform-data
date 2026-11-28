# Key revocation

## 1. Thu hồi khóa là thu hồi một sự cho phép

Key revocation là việc tuyên bố một khóa, phiên bản khóa hoặc quan hệ tin cậy liên quan không còn được phép sử dụng trong phạm vi đã xác định.

Nguyên nhân có thể là:

- Key material đã lộ hoặc nghi bị lộ.
- Workload giữ quyền sử dụng không còn đáng tin.
- Quan hệ với đối tác hoặc chủ thể đã chấm dứt.
- Khóa được cấp sai mục đích hoặc sai danh tính.
- Một profile không còn được phép.
- Chính sách yêu cầu chấm dứt một quyền trước thời hạn dự kiến.

Điểm quan trọng là revocation không chỉ là ghi một trạng thái REVOKED trong database. Quyết định phải có hiệu lực tại những nơi sử dụng hoặc tin khóa đó.

Trong thiết kế yêu cầu bảo mật, cần trả lời:

> Thu hồi cái gì, cấm thao tác nào, tại những điểm nào, và trong bao lâu kể từ quyết định có thẩm quyền?

### 1.1. Hai mục tiêu khác nhau

Có thể cần:

1. Ngăn các hệ thống do tổ chức kiểm soát tiếp tục dùng một key.
2. Ngăn relying party tiếp tục chấp nhận dữ liệu được xác thực bằng một key hoặc chứng thư.

Ví dụ, disable signing key trong KMS có thể chặn workload gọi dịch vụ ký. Nhưng nếu raw private key đã lộ ra ngoài, bên đang giữ bản sao vẫn có thể tính chữ ký.

Do đó, ứng phó cần cả việc chặn sử dụng trong hạ tầng và cập nhật quyết định tin cậy ở phía xác minh. Không có một API nội bộ nào xóa được kiến thức về key mà bên khác đã lấy.

### 1.2. Phạm vi cần cụ thể

Một yêu cầu “thu hồi toàn bộ khóa của đối tác” có thể bao gồm nhiều đối tượng:

- Quyền của một principal gọi key service.
- Một key version trong KMS.
- Shared secret HMAC.
- Chứng thư X.509.
- Public key trong một danh sách tin cậy.
- Một alias đang trỏ tới version bị ảnh hưởng.
- Các credential hoặc session đã được tạo nhờ key đó.

Cần xác định từng loại và quan hệ phụ thuộc. Thu hồi một mục không tự đồng nghĩa những mục khác đã bị vô hiệu hóa.

## 2. Phân biệt revocation với các thao tác liên quan

| Thao tác | Mục đích | Điều không tự xảy ra |
|---|---|---|
| Expiration | Kết thúc thời hạn đã định trước | Không phản ứng sớm với một sự cố |
| Retirement | Ngừng tạo bảo vệ mới theo vòng đời bình thường | Không nhất thiết cấm xử lý dữ liệu cũ |
| Rotation | Chuyển thao tác mới sang key/material khác | Không tự làm key cũ hết được tin |
| Disable | Chặn thao tác tại một hệ thống quản lý | Không xóa mọi bản sao material |
| Revocation | Thu hồi quyền sử dụng hoặc quan hệ tin cậy theo phạm vi | Không tự hủy dữ liệu hoặc mọi key copy |
| Destruction | Loại bỏ material theo cơ chế và phạm vi | Không thu hồi dữ liệu đã bị đọc trước đó |

### 2.1. Thu hồi grant và thu hồi key

Nếu một workload bị xâm nhập nhưng key chưa bị export và vẫn phục vụ những workload khác, quyết định có thể là thu hồi quyền của workload đó.

Nếu material bị lộ, chỉ xóa grant của một principal có thể không đủ. Cần đánh giá mọi bên có thể dùng material hoặc tin các kết quả do nó tạo.

Thiết kế phải gắn biện pháp với tình huống. Không mặc định mọi sự cố đều cần xóa ngay key đang bảo vệ dữ liệu lưu lâu dài.

### 2.2. Key bị nghi lộ khác key nghỉ bình thường

Một key retired có thể còn được decrypt dữ liệu cũ trong điều kiện đã định nghĩa.

Với key compromised, dữ liệu được mã hóa hoặc xác thực dưới key đó cần đánh giá thêm về phạm vi ảnh hưởng. Không giữ đường chấp nhận bình thường chỉ vì “cần tương thích dữ liệu cũ”.

Có thể có luồng phục hồi hoặc điều tra đặc biệt, nhưng đó phải là quyền riêng có kiểm soát, không phải một fallback tự động cho mọi request.

### 2.3. Certificate revocation khác xóa private key

Thu hồi chứng thư thông báo rằng một liên kết danh tính–public key không còn được chấp nhận theo chính sách PKI.

Xóa private key ở một máy không tự thông báo cho mọi relying party. Ngược lại, chứng thư bị thu hồi không làm bản sao private key biến mất.

Khi sự cố liên quan tới chứng thư, cần thiết kế cả thay key/certificate, cập nhật endpoint và phân phối trạng thái thu hồi.

## 3. Mô hình đe dọa và điểm thực thi

### 3.1. Những đường có thể tiếp tục dùng key

Một hệ thống có thể có:

```text
Control plane quản lý key
    → KMS/HSM
    → workload có cache
    → tác vụ nền
    → verifier ở dịch vụ khác
    → client hoặc đối tác bên ngoài
```

Từng điểm có thể giữ:

- Key material.
- Wrapped data key.
- Public key.
- Chứng thư.
- Kết quả xác minh trước đó.
- Quyền hoặc trạng thái ACTIVE đã cache.
- Session được thiết lập trước khi thu hồi.

Yêu cầu chỉ cập nhật một database trung tâm sẽ không bao phủ đầy đủ nếu các điểm này có thể tiếp tục hoạt động độc lập.

### 3.2. Kiểm kê theo khả năng, không chỉ theo tên dịch vụ

Cần phân biệt:

| Thành phần | Nó có thể làm gì sau sự cố? |
|---|---|
| Workload chỉ gọi KMS | Phụ thuộc quyền và trạng thái dịch vụ khóa |
| Workload đã giữ plaintext DEK | Có thể còn dùng local material theo khả năng kiểm soát |
| Verifier giữ public key | Có thể tiếp tục xác minh nếu policy tin cậy chưa đổi |
| Đối tác giữ shared secret | Có thể tạo MAC ngoài hạ tầng của tổ chức |
| Session đã thiết lập | Có thể không tự kiểm tra lại trạng thái key ở mỗi thao tác |
| Backup có material | Có thể phục hồi lại trạng thái cũ nếu không có kiểm soát |

Những khả năng này quyết định vị trí và độ trễ của revocation.

### 3.3. Ví dụ về disable key quản lý

Tài liệu [enable/disable key của AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/enabling-keys.html) nêu rằng key bị disable không còn được dùng cho operation qua dịch vụ theo trạng thái và tính nhất quán của nó; nhưng dữ liệu được bảo vệ bằng data key không tự bị ảnh hưởng cho tới khi cần dùng KMS lại.

Hệ quả thiết kế là phải xét cả data key đã được giữ ở nơi khác. Disable KEK không đồng nghĩa mọi bản DEK trong bộ nhớ đã hết khả năng sử dụng.

Đây là ví dụ theo một nền tảng, không phải lời khẳng định mọi KMS có cùng mô hình trạng thái hoặc thời gian có hiệu lực.

## 4. Định danh mục tiêu thu hồi

### 4.1. Dùng tham chiếu ổn định

Một alias có thể đổi đích. Nếu lệnh thu hồi chỉ ghi alias, kết quả có thể khác tùy thời điểm resolver đọc nó.

Nên xác định một mục tiêu bất biến phù hợp:

- Key version reference.
- Key material identity theo cơ chế nền tảng.
- Certificate issuer và serial hoặc định danh tương ứng.
- Trust binding cụ thể.
- Grant/principal/operation cần thu hồi.

Có thể lưu alias để hỗ trợ điều tra, nhưng alias không nên là căn cứ duy nhất nếu phạm vi cần gắn với version thực tế.

### 4.2. Cùng material dưới nhiều tên

Nếu raw material được import ở nhiều nơi hoặc có nhiều bản sao, thu hồi một key object không tự bao phủ những bản khác.

Inventory cần giúp xác định:

- Bản copy hoặc import liên quan.
- Replica.
- Môi trường hoặc workload cùng sử dụng.
- Chứng thư chứa cùng public key.
- Những trust store hoặc key set đã phân phối.
- Những hệ thống phục hồi có thể đưa material trở lại.

Đổi tên keyId không làm material bị lộ trở nên đáng tin trở lại.

### 4.3. Phạm vi operation

Một quyết định nên ghi rõ:

```text
Đối tượng: version khóa xác định
Thao tác bị cấm: mọi sử dụng bình thường
Lý do: nghi lộ material
Phạm vi: production và các replica liên quan
Ngoại lệ: không có trong đường nghiệp vụ thông thường
Luồng phục hồi: một quyền riêng được phê duyệt nếu cần
```

Với một tình huống khác, phạm vi có thể chỉ là generate-MAC cho một integration hoặc quyền decrypt của một workload.

Không dùng một từ revoked mà không định nghĩa hệ quả cho những thao tác liên quan.

## 5. Nguồn có thẩm quyền và lịch sử quyết định

### 5.1. Ai được thu hồi?

Revocation có thể làm ngừng dịch vụ hoặc mất khả năng truy cập dữ liệu. Một request bất kỳ không được quyền thay trạng thái key.

Cần xác định:

- Danh tính có quyền khởi tạo.
- Mức phê duyệt cho từng loại thu hồi.
- Cơ chế khẩn cấp nếu có.
- Điều kiện dùng cơ chế khẩn cấp.
- Audit và kiểm tra sau thao tác.
- Ai có quyền khôi phục hoặc thay thế.

Không nhất thiết mọi sự kiện đều chờ một quy trình dài. Nhưng đường khẩn cấp vẫn cần có thẩm quyền và bằng chứng.

### 5.2. Hồ sơ quyết định

Một sự kiện logic có thể gồm:

```json
{
  "revocationId": "revocation-example-007",
  "targetType": "KEY_VERSION",
  "targetReference": "immutable-version-reference",
  "policyEpoch": 18,
  "reason": "SUSPECTED_COMPROMISE",
  "scope": "NORMAL_OPERATIONS",
  "decisionReference": "incident-reference"
}
```

Đây là minh họa metadata, không phải một lệnh API hoàn chỉnh.

Có thể cần thêm thời điểm quyết định, hiệu lực dự kiến, actor và approval reference theo policy. Không đưa material vào sự kiện thu hồi.

### 5.3. Chống thông điệp cũ khôi phục trạng thái ACTIVE

Một consumer có thể nhận sự kiện theo thứ tự khác nhau:

```text
Epoch 18: REVOKED
Epoch 17: ACTIVE đến muộn
```

Nó không được áp dụng bản cũ để bật lại key.

Cần cơ chế version/epoch hoặc trạng thái có thẩm quyền để phát hiện rollback. Một timestamp tự khai không đủ nếu không có xác thực nguồn và quy tắc thứ tự.

Khi phát hiện mất sự kiện hoặc khoảng trống, consumer phải đồng bộ lại theo thiết kế. Không mặc định “chưa thấy revoke” nghĩa “chắc chắn còn active”.

### 5.4. Bảo vệ kênh phân phối

Sự kiện thu hồi có thể đi qua broker hoặc API. Kênh đó cần bảo vệ nguồn, toàn vẹn và quyền xử lý.

Một sự kiện giả có thể gây từ chối dịch vụ. Một sự kiện bị bỏ qua có thể giữ quyền trái phép. Vì vậy, revocation plane cũng là một tài sản bảo mật, không chỉ một topic vận hành.

## 6. Độ trễ thu hồi và giới hạn cache

### 6.1. Định nghĩa thời điểm bắt đầu và kết thúc

Một mục tiêu minh họa:

```text
Trong tối đa 60 giây kể từ khi quyết định thu hồi có thẩm quyền
được ghi nhận, các operation mới thuộc phạm vi bị cấm phải bị từ chối.
```

Con số chỉ là ví dụ. Hệ thống cần chọn thời hạn theo rủi ro và kiến trúc thật.

Cần làm rõ:

- Thời điểm quyết định, không nhầm với thời điểm bắt đầu nghi ngờ.
- Những operation được đo.
- Các node và vùng trong phạm vi.
- Cách xác định một request mới.
- Hành vi với request đang chạy.
- Đường nào không thể đáp ứng thời hạn, chẳng hạn client offline.

Nếu không nêu phạm vi, một SLO “thu hồi trong 60 giây” có thể được báo đạt trong khi một vùng vẫn chấp nhận key.

### 6.2. Tách detection, decision và propagation

Có thể đánh giá:

```text
Khoảng phát hiện sự cố
    + khoảng đưa ra quyết định
    + khoảng phân phối và thực thi
```

Tối ưu propagation không bù được cho việc key đã lộ nhiều ngày trước khi được nhận diện.

Vận hành cần biết mỗi khoảng để xác định exposure và cải thiện đúng chỗ. Không lấy thời gian gọi API thành công làm toàn bộ thời gian thu hồi.

### 6.3. TTL đặt trần cho độ cũ được phép

Nếu verifier giữ trạng thái ACTIVE trong cache 5 phút và không có invalidation, nó không thể cam kết ngừng chấp nhận trong 60 giây kể từ một quyết định mới.

Có thể cần:

- TTL ngắn hơn.
- Push invalidation có cơ chế dự phòng.
- Lease có thời hạn.
- Tra trạng thái online cho operation nhạy cảm.
- Policy riêng cho hoạt động khi mất kết nối.

Những cơ chế này có chi phí khả dụng và hiệu năng. Yêu cầu phải chọn rõ thay vì hứa thu hồi tức thời.

### 6.4. Không có phản hồi không có nghĩa trạng thái tốt

Nếu status service lỗi, kết quả là không xác định hoặc chỉ còn cache trong độ mới đã cho phép.

Đối với đường nhạy cảm trong mô hình ví dụ, policy có thể là:

```text
Có trạng thái ACTIVE còn hạn → tiếp tục các kiểm tra khác
Có trạng thái REVOKED → từ chối
Không có hoặc quá cũ → từ chối/gián đoạn có kiểm soát
```

Một sản phẩm khác có thể có chế độ degraded được đánh giá riêng. Nhưng không nên có fail-open âm thầm biến lỗi mạng thành quyền vô thời hạn.

### 6.5. Cache material khác cache trạng thái

Một cache status hết hạn có thể dễ làm mới. Một bản raw key hoặc DEK đã unwrap nằm trong process còn có thể được dùng mà không gọi status service.

Cần biết ai giữ material và ràng buộc lớp sử dụng của nó. Chỉ xóa key khỏi một map metadata không chứng minh những bản copy khác đã được thu hồi.

## 7. Ví dụ Java: gate từ chối trạng thái cũ hoặc revoked

Ví dụ Java 17 trở lên dưới đây mô tả một bước chặn sử dụng bình thường. Snapshot được lấy từ nguồn policy đáng tin, không phải JSON do client tự khai.

```java
import java.time.Instant;
import java.util.Objects;

public final class RevocationGate {
    public enum Status {
        ACTIVE,
        REVOKED,
        UNKNOWN
    }

    public enum Decision {
        PASS_THIS_GATE,
        REJECTED_STATUS,
        STALE_SNAPSHOT,
        REFERENCE_MISMATCH,
        POLICY_ROLLBACK
    }

    public record Snapshot(
            String immutableVersionReference,
            Status status,
            long policyEpoch,
            Instant freshUntil
    ) {
        public Snapshot {
            Objects.requireNonNull(immutableVersionReference);
            Objects.requireNonNull(status);
            Objects.requireNonNull(freshUntil);

            if (immutableVersionReference.isBlank() || policyEpoch < 0) {
                throw new IllegalArgumentException(
                        "Invalid status snapshot"
                );
            }
        }
    }

    private RevocationGate() {
    }

    public static Decision evaluate(
            String expectedVersionReference,
            long minimumKnownEpoch,
            Snapshot snapshot,
            Instant now
    ) {
        Objects.requireNonNull(expectedVersionReference);
        Objects.requireNonNull(now);

        if (minimumKnownEpoch < 0) {
            throw new IllegalArgumentException(
                    "Invalid policy epoch"
            );
        }

        if (snapshot == null) {
            return Decision.STALE_SNAPSHOT;
        }

        if (!expectedVersionReference.equals(
                snapshot.immutableVersionReference()
        )) {
            return Decision.REFERENCE_MISMATCH;
        }

        if (snapshot.policyEpoch() < minimumKnownEpoch) {
            return Decision.POLICY_ROLLBACK;
        }

        if (snapshot.status() != Status.ACTIVE) {
            return Decision.REJECTED_STATUS;
        }

        if (!now.isBefore(snapshot.freshUntil())) {
            return Decision.STALE_SNAPSHOT;
        }

        return Decision.PASS_THIS_GATE;
    }
}
```

### 7.1. Ý nghĩa của ví dụ

- Tham chiếu phải khớp đúng version dự kiến.
- Trạng thái UNKNOWN không được coi là ACTIVE.
- Snapshot ACTIVE quá cũ không được tiếp tục dùng.
- Một epoch cũ hơn mốc đã biết không được áp dụng.
- REVOKED không được bật lại chỉ vì status service không trả lời.
- Cận freshUntil không bao gồm thời điểm kết thúc.

### 7.2. Những điều code không tự bảo đảm

minimumKnownEpoch chỉ có ý nghĩa nếu đến từ cơ chế tin cậy. Một mốc “đã biết gần nhất” không chứng minh toàn hệ thống chưa có quyết định mới hơn.

freshUntil cần được cấp theo policy cache và thời gian được quản lý; caller không được tự chọn một hạn xa trong tương lai.

PASS_THIS_GATE không phải ALLOW toàn bộ operation. Hệ thống còn cần kiểm tra workload, operation, tenant, key purpose, profile và provider thực tế.

Đoạn code không cung cấp tính nguyên tử giữa kiểm tra snapshot và thao tác mật mã. Request có thể chạy cùng lúc với thu hồi; policy in-flight cần được giải quyết ở kiến trúc thực thi.

### 7.3. Không sửa logic thành fallback

Không thêm nhánh:

```text
Nếu snapshot lỗi thì dùng cached key vô hạn
Nếu bị revoke thì thử alias cũ
Nếu verify bị từ chối thì bỏ kiểm tra trạng thái
```

Những đường đó làm mất ý nghĩa của revocation dù hàm evaluate vẫn tồn tại trong codebase.

## 8. Thu hồi chứng thư và public-key trust

### 8.1. Chứng thư có thể bị thu hồi trước khi hết hạn

Một chứng thư còn trong khoảng validity không có nghĩa luôn được chấp nhận tới ngày cuối.

[RFC 5280](https://www.rfc-editor.org/rfc/rfc5280.html#section-3.3) mô tả certificate revocation và CRL: một cấu trúc trạng thái có chữ ký, được kiểm tra trong phạm vi chứng thư và issuer phù hợp.

Không chỉ lấy serial number rồi so với một danh sách không rõ nguồn. Issuer, phạm vi, chữ ký và độ mới là những yếu tố quan trọng.

### 8.2. CRL và độ mới

CRL là cơ chế phân phối trạng thái theo những lần công bố. Vì vậy, hiệu lực tới relying party còn phụ thuộc chu kỳ phát hành, tải lại và cache.

Yêu cầu PKI cần xác định:

- Những chứng thư nào được kiểm tra.
- Nguồn trạng thái được chấp nhận.
- Độ mới tối đa.
- Cách xác minh chữ ký và phạm vi.
- Hành vi khi thiếu dữ liệu hoặc dữ liệu quá cũ.
- Giới hạn tải, parse và cache.

Không tuyên bố “đã có CRL nên thu hồi tức thời”.

### 8.3. OCSP và những trạng thái khác nhau

OCSP cung cấp trạng thái good, revoked hoặc unknown theo giao thức. good không thay thế toàn bộ kiểm tra chứng thư; unknown không đồng nghĩa good.

Bên nhận phải kiểm tra response phù hợp chứng thư, người ký có thẩm quyền và thông tin thời gian theo policy. Những yêu cầu này được mô tả trong [RFC 6960](https://www.rfc-editor.org/rfc/rfc6960.html), đặc biệt phần 2 và 3.2.

Không chấp nhận một response chỉ vì nó có chuỗi good. Chữ ký, binding và freshness phải được xác minh bằng implementation phù hợp.

### 8.4. Mất kết nối tới dịch vụ trạng thái

Cần tách:

| Tình huống | Ý nghĩa |
|---|---|
| Trạng thái đã xác minh là revoked | Quan hệ tin cậy bị từ chối theo policy |
| Trạng thái đã xác minh và còn độ mới | Có thể tiếp tục các kiểm tra khác |
| Response unknown | Nguồn này không xác định được trạng thái |
| Timeout hoặc lỗi mạng | Chưa lấy được kết quả mới |
| Response sai chữ ký hoặc quá cũ | Không dùng như trạng thái đáng tin |

Việc có thể dùng cache hay cần từ chối phụ thuộc policy đã công bố và rủi ro. Không được ghi mọi trường hợp vào một boolean notRevoked=true.

### 8.5. Trust anchor và key pinning

Một root/trust anchor được tin theo cấu hình không nên được xử lý như một leaf certificate thông thường trong mọi tình huống.

Khi một trust anchor hoặc pin bị ảnh hưởng, có thể cần cập nhật cấu hình tin cậy hoặc phần mềm phía client. Không mặc định một CRL cho leaf sẽ tự làm mất mọi niềm tin vào root đã được cài.

Ứng dụng pin key cũng phải có kế hoạch thay và thu hồi pin. Nếu client không có kênh cập nhật, cam kết thời gian revocation sẽ bị giới hạn bởi điều đó.

## 9. Verifier, token và kết nối đã thiết lập

### 9.1. Public key đã được phân phối

Một verifier có thể giữ một public key đã tải từ trước. Xóa key khỏi nguồn phân phối không tự làm mọi cache biết thay đổi.

Yêu cầu cần xác định:

- Cache key và TTL.
- Cách cập nhật trust set.
- Cách báo key bị thu hồi.
- Hành vi với key không còn trong tập được phép.
- Cách xử lý metadata cũ khi mất mạng.

Một key còn có thể xác minh chữ ký đúng về toán học nhưng không còn được policy chấp nhận.

### 9.2. Credential hoặc token được tạo trước đó

Thu hồi signing key có thể ảnh hưởng nhiều credential đã được ký, nhưng không tự tương đương với thu hồi một token hoặc session riêng.

Cần xác định mục tiêu:

- Từ chối mọi thông điệp dưới key.
- Từ chối những token cụ thể.
- Chặn chủ thể hoặc session.
- Giữ một số bằng chứng lịch sử theo policy riêng.

Không dùng một trường issuedAt được ký bằng chính key đã lộ như bằng chứng độc lập chắc chắn rằng thông điệp được tạo trước sự cố. Bên có private key có thể tự tạo giá trị thời gian.

### 9.3. Kết nối đang tồn tại

Một kết nối TLS/mTLS hoặc session ứng dụng có thể đã được thiết lập trước quyết định thu hồi.

Không được mặc định cập nhật trạng thái chứng thư hoặc key sẽ tự đóng mọi kết nối đang chạy.

Nếu cần giới hạn tiếp tục hoạt động, policy có thể yêu cầu:

- Thời gian sống kết nối hữu hạn.
- Kiểm tra lại quyền ở operation nhạy cảm.
- Cơ chế hủy session theo danh tính.
- Hành vi rõ cho reconnect hoặc resumption.
- Phân biệt session transport và session ứng dụng.

Các cơ chế phải được đối chiếu với stack thực tế. Bằng chứng cần quan sát kết nối đã có, không chỉ handshake mới.

### 9.4. Request đang chạy và ranh giới commit

Cần quyết định có cho phép request bắt đầu trước khi revoke hoàn tất hay không.

Ví dụ:

- Một thao tác đọc ngắn có thể được phép kết thúc theo policy.
- Một lệnh ký hoặc phát hành quyền nhạy cảm có thể cần kiểm tra mới tại ranh giới phát hành.
- Một job chờ queue cần đánh giá lại khi thực thi.
- Một artifact tạo xong có thể còn cần kiểm tra quyền lúc tải.

Không hứa kiểm tra trước commit nếu không có cơ chế phối hợp chống race phù hợp. Hãy định nghĩa mô hình nhất quán và độ trễ có thể thực thi.

## 10. Phục hồi sau thu hồi mà không mất dữ liệu

### 10.1. Key mới cho hoạt động mới

Một kế hoạch có thể:

1. Ngừng sử dụng bình thường key bị ảnh hưởng.
2. Chuẩn bị key mới từ nguồn tin cậy.
3. Cấp quyền và cập nhật workload.
4. Kiểm chứng thao tác mới dùng key mới.
5. Xử lý dữ liệu và bằng chứng cũ theo đánh giá rủi ro.
6. Duy trì trạng thái thu hồi cho mục tiêu cũ.

Không chuyển alias rồi xóa dấu vết key cũ khỏi inventory; vẫn cần biết dữ liệu nào và bên nào có liên quan.

### 10.2. Dữ liệu mã hóa dưới key cũ

Thu hồi quyền sử dụng không luôn đồng nghĩa phải hủy ngay material.

Nếu còn dữ liệu cần phục hồi, có thể cần một luồng hạn chế để decrypt và re-encrypt theo kiểm soát. Luồng đó phải có quyền riêng, log, giới hạn và validation phù hợp.

Nếu material đã lộ, tái mã hóa dữ liệu hiện tại không làm các ciphertext cũ mà bên khác đã sao chép trở nên bí mật trở lại.

Với cơ chế có xác thực đối xứng, key bị lộ cũng có thể làm dữ liệu giả mang tag hợp lệ. Kế hoạch phục hồi không được coi mọi dữ liệu giải mã thành công là chắc chắn nguyên bản.

### 10.3. Chữ ký hoặc MAC lịch sử

Đánh giá bằng chứng cũ cần dựa vào policy, thời điểm tin cậy và nguồn bằng chứng phù hợp.

Không áp một quy tắc chung:

```text
Mọi chữ ký trước ngày thu hồi đều hợp lệ
```

nếu thời điểm đó chỉ là lời khai có thể được tạo bởi key đã lộ.

Cũng không mặc định xóa public key cần thiết cho điều tra. Có thể cần giữ material công khai và metadata để phân tích lịch sử trong khi không còn chấp nhận nó cho hoạt động mới.

### 10.4. Chống khôi phục lại quyền đã thu hồi

Backup cấu hình hoặc database policy có thể chứa trạng thái ACTIVE cũ.

Khi restore, hệ thống phải đối chiếu trạng thái thu hồi có thẩm quyền hoặc policy epoch hiện hành trước khi phục vụ.

Không để một quy trình disaster recovery âm thầm làm key bị lộ được chấp nhận lại chỉ vì snapshot được tạo trước sự cố.

### 10.5. Có được un-revoke không?

Cần phân biệt tạm dừng do vận hành với thu hồi vĩnh viễn vì compromise.

Nếu nền tảng cho bật lại một key disabled, hành động đó không tự khôi phục niềm tin vào material đã lộ. Có thể chỉ phù hợp trong một luồng phục hồi hạn chế.

Việc phục hồi quyền phải là quyết định mới có thẩm quyền, không là tác dụng phụ của một retry hoặc startup script.

## 11. Chuyển quyết định thành yêu cầu bảo mật

### 11.1. Yêu cầu mơ hồ

> Hệ thống phải hỗ trợ thu hồi khóa nhanh chóng.

Phát biểu này thiếu mục tiêu, operation, thời gian và những điểm thực thi.

### 11.2. Yêu cầu về phạm vi

> Mỗi quyết định thu hồi phải xác định target bất biến, operation bị cấm, lý do, thời điểm có thẩm quyền và phạm vi workload/verifier. Alias không được là căn cứ duy nhất nếu quyết định liên quan tới một version hoặc material cụ thể.

### 11.3. Yêu cầu về hiệu lực

> Trong thời hạn đã công bố, các operation mới thuộc phạm vi phải bị từ chối tại mọi điểm thực thi được kiểm kê. Cơ chế cache, key material local và session tồn tại phải có policy tương ứng; không tuyên bố đạt chỉ từ readback control plane.

### 11.4. Yêu cầu về trạng thái không xác định

> Khi không có trạng thái đủ mới, đường nhạy cảm không tự cho phép sử dụng bình thường. Nếu sản phẩm có chế độ degraded, phạm vi và thời hạn phải được định nghĩa và kiểm chứng riêng, không có fallback vô hạn.

### 11.5. Yêu cầu về bằng chứng và audit

> Mỗi thao tác thu hồi có actor, target, policy version, quyết định và kết quả. Hệ thống lưu bằng chứng trạng thái cùng kiểm chứng hành vi từ những vùng/workload đại diện. Log không chứa raw key, plaintext hoặc credential không cần thiết.

### 11.6. Yêu cầu về phục hồi

> Key bị thu hồi không được tự trở lại hoạt động do restore, sự kiện cũ hoặc alias thay đổi. Luồng phục hồi dữ liệu dùng key cũ, nếu cần, là quyền riêng có kiểm soát và không mở lại đường nghiệp vụ thông thường.

### 11.7. Mẫu truy vết

```text
ID: KEY-REVOKE-01
Tài sản:
    key material, quyền mật mã và quan hệ tin cậy
Target:
    version/binding/grant bất biến
Trigger:
    quyết định có thẩm quyền theo sự cố hoặc policy
Hiệu lực:
    operation và thời hạn cụ thể
Điểm thực thi:
    key service, workload, verifier và cache liên quan
In-flight:
    quy tắc cho request/job đang chạy
Recovery:
    không tự khôi phục niềm tin
Bằng chứng:
    control-plane state + data-plane rejection
```

## 12. Ma trận rủi ro và bằng chứng chấp nhận

| Rủi ro | Kiểm soát | Bằng chứng |
|---|---|---|
| Chỉ revoke alias nhưng material còn dùng | Target bất biến và inventory bản sao | Các tham chiếu liên quan không tạo bypass |
| Control plane đổi nhưng cache vẫn ACTIVE | Độ mới, invalidation và SLO | Operation mới bị chặn trong thời hạn |
| DEK đã unwrap tiếp tục được dùng | Quản lý material cache | Hành vi local nằm trong cam kết thu hồi |
| Sự kiện ACTIVE cũ đến sau | Policy version/epoch | Không hạ trạng thái về bản cũ |
| Lỗi mạng bị hiểu là good | Xử lý UNKNOWN rõ | Không có fail-open ngoài policy |
| Cert còn hạn nhưng đã revoked | Kiểm tra trạng thái theo PKI policy | Chứng thư bị thu hồi không được chấp nhận mới |
| Public key cache chưa cập nhật | Trust set có vòng đời | Verifier ngừng chấp nhận theo hạn |
| Session cũ giữ quyền | Policy in-flight/session | Không hoạt động ngoài phạm vi đã công bố |
| Restore bật lại key | Đối chiếu revocation authority | Snapshot cũ không tái cấp quyền |
| Hủy ngay gây mất dữ liệu | Tách revoke và destroy | Phục hồi/retention được xử lý có kiểm soát |
| Thu hồi giả gây ngừng dịch vụ | Xác thực và phân quyền control plane | Actor/sự kiện không có quyền bị từ chối |

## 13. Thiết kế kiểm chứng

Các tình huống dưới đây là tiêu chí cho việc triển khai, không phải kết quả kiểm thử đã chạy cho một hệ thống cụ thể.

### 13.1. Đo hiệu lực trên đường thật

Dùng key và dữ liệu tổng hợp trong môi trường kiểm soát:

```text
T0: ghi nhận quyết định thu hồi
T1: control plane báo state tương ứng
T2...Tn: các workload/verifier bắt đầu từ chối operation mới
```

Đối chiếu thời điểm cuối trong phạm vi với SLO. Không chỉ đo một node gần control plane.

Cần ghi rõ:

- Identity và operation thử.
- Version hoặc binding.
- Vùng và loại workload.
- Snapshot/cache state liên quan.
- Request bắt đầu trước hay sau mốc.
- Kết quả và tác dụng phụ.

### 13.2. Cache và mạng phân vùng

Bao phủ:

- Cache ACTIVE còn hạn lúc revoke.
- Push event đến bình thường.
- Push event bị bỏ lỡ.
- Cache hết hạn và status service lỗi.
- Node offline rồi quay lại.
- Sự kiện cũ hoặc lặp.
- Clock không phù hợp trong giới hạn policy.
- Material đã unwrap hoặc giữ local.

Kết quả phải khớp mô hình hiệu lực đã công bố. Nếu có một cửa sổ dùng cache, hãy nêu đúng cửa sổ đó thay vì báo đạt “ngay lập tức”.

### 13.3. Kiểm tra PKI theo trạng thái

| Tình huống | Điều cần xác minh |
|---|---|
| Certificate chưa bị thu hồi, hợp lệ theo policy | Đường bình thường vẫn hoạt động |
| Certificate đã bị thu hồi | Không chấp nhận mới theo phạm vi |
| CRL quá cũ hoặc sai chữ ký | Không dùng như dữ liệu trạng thái đáng tin |
| OCSP response không khớp certificate | Từ chối response đó |
| OCSP signer không có thẩm quyền | Không tin trạng thái |
| OCSP unknown hoặc timeout | Hành vi theo policy, không tự đổi thành good |
| Trust anchor bị thay đổi | Trust store/client cập nhật theo kế hoạch |
| Kết nối cũ đã thiết lập | Hành vi đúng chính sách session |

Không tắt validation chứng thư để làm bài thử “vượt qua lỗi”. Điều đó làm mất chính kiểm soát cần đánh giá.

### 13.4. In-flight, job và side effect

Kiểm tra:

- Một operation đang chạy khi quyết định được ghi.
- Một job tạo trước nhưng chạy sau revoke.
- Retry của một request bị từ chối.
- Tác vụ migration dùng key cũ.
- Một artifact đã tạo nhưng chưa được tải.
- Hai thay đổi policy diễn ra gần nhau.

Quan sát trạng thái nghiệp vụ và side effect, không chỉ response code. Một lời gọi bị báo lỗi nhưng đã phát hành chữ ký, plaintext hoặc quyền mới có thể không đạt yêu cầu.

### 13.5. Restore và khôi phục quyền

Trong môi trường thử:

- Restore một snapshot có trạng thái ACTIVE cũ.
- Khởi động workload với trust set cũ.
- Khôi phục một replica chưa nhận revoke.
- Đổi alias sau quyết định.
- Gửi lại sự kiện cũ.
- Thực hiện một quy trình bật lại có thẩm quyền nếu policy cho phép.

Điều kiện đạt là không có đường nào tự biến quyết định thu hồi thành ACTIVE. Những hành động phục hồi được phép phải tạo một quyết định mới, có scope và audit tương ứng.

### 13.6. Thử lỗi quyền quản trị

Cần xác nhận:

- Workload chỉ có quyền dùng key không tự revoke được key khác.
- Actor không có thẩm quyền không tạo quyết định.
- Thông điệp giả không được consumer tin.
- Thay target hoặc epoch ngoài policy bị phát hiện.
- Quyền khẩn cấp có giới hạn và được ghi nhận.

Revocation bảo vệ hệ thống nhưng cũng có thể là công cụ làm gián đoạn nếu control plane không được bảo vệ.

## 14. Vận hành và xử lý sự cố

### 14.1. Runbook theo loại key

Một runbook cần có:

- Cách xác định target và owner.
- Cách ngừng operation liên quan.
- Cách phân phối trạng thái.
- Cách kiểm chứng theo vùng/workload.
- Cách thay key hoặc trust binding.
- Cách xử lý dữ liệu cũ.
- Cách giữ bằng chứng và tránh lộ secret.
- Cách đánh giá khả năng phục hồi và hủy về sau.

Không chỉ ghi một lệnh disable rồi coi sự cố đã đóng.

### 14.2. Chỉ số có ý nghĩa

Có thể theo dõi:

- Thời gian từ quyết định đến từng điểm thực thi.
- Node chưa xác nhận hoặc snapshot quá cũ.
- Operation dùng target bị thu hồi.
- Key service/status service không khả dụng.
- Số verifier vẫn dùng trust set cũ.
- Session/job ngoài cửa sổ policy.
- Sự kiện epoch lùi hoặc mất khoảng.
- Luồng phục hồi dùng key cũ.

Không ghi raw key hoặc plaintext vào log chẩn đoán. Tham chiếu key và thông tin sự cố cũng cần quyền truy cập phù hợp.

### 14.3. Không đồng nhất xác nhận với hiệu lực

Consumer ACK một sự kiện chỉ chứng minh một bước giao tiếp đã diễn ra. Nó không tự chứng minh mọi thread, cache, provider hoặc process liên quan đã chặn operation.

Có thể cần kết hợp ACK, readback và phép thử hành vi tổng hợp. Cách kiểm chứng phải phù hợp mức rủi ro và chi phí, không chỉ chọn một tín hiệu dễ thu.

### 14.4. Diễn tập định kỳ

Một cơ chế thu hồi ít được dùng có thể hỏng khi thực sự cần. Diễn tập bằng key thử giúp phát hiện:

- Inventory thiếu.
- Quá nhiều bản copy.
- Cache dài hơn SLO.
- Quyền khẩn cấp không hoạt động.
- Client không có kênh cập nhật.
- Restore tái tạo state cũ.
- Runbook chưa có owner đúng.

Kết quả cần dẫn tới điều chỉnh yêu cầu hoặc kiến trúc, không chỉ đánh dấu đã chạy một thao tác.

## 15. Những sai lầm thường gặp

### 15.1. Rotation được coi là revocation

Key mới không làm verifier tự ngừng tin key cũ. Cần quyết định và phân phối trạng thái chấp nhận rõ.

### 15.2. Disable KMS được coi là xóa mọi copy

Material hoặc DEK đã có ở nơi khác có thể còn khả dụng. Phạm vi hứa hẹn phải theo inventory và cơ chế thật.

### 15.3. Còn hạn chứng thư nghĩa là còn đáng tin

Expiry và revocation là hai điều kiện khác nhau. Validation phải đáp ứng policy cho cả hai.

### 15.4. Unknown hoặc timeout được coi là good

Không lấy sự thiếu thông tin làm bằng chứng chưa bị thu hồi. Nếu có degraded mode, phải định nghĩa và giới hạn.

### 15.5. Một timestamp tự khai chứng minh lịch sử

Thời điểm được tạo bởi key đã lộ không luôn là bằng chứng độc lập. Cần xem xét nguồn thời gian và bằng chứng tin cậy phù hợp.

### 15.6. Chỉ đo control plane

State mới trên console không chứng minh mọi verifier hoặc cache đã dừng chấp nhận. Cần bằng chứng ở đường thực thi.

### 15.7. Xóa key ngay để kết thúc sự cố

Hủy không có inventory có thể làm mất dữ liệu cần phục hồi. Revoke và destroy cần gate khác nhau.

### 15.8. Restore đưa key bị lộ hoạt động lại

Backup không được là đường bypass trạng thái thu hồi. Quy trình phục hồi phải đối chiếu policy hiện hành trước khi phục vụ.

## 16. Điểm cần ghi nhớ

Key revocation là một quyết định có phạm vi về việc tiếp tục dùng hoặc tin một khóa, version hay binding. Nó khác rotation, hết hạn và hủy material.

Thiết kế phải xác định target bất biến, operation, thẩm quyền, độ trễ hiệu lực và những nơi giữ trạng thái hoặc material. Cache, verifier offline, session và job đang chạy là những phần của hợp đồng thu hồi.

Bằng chứng chấp nhận cần cho thấy quyền bị chặn ở đường thực thi trong thời hạn đã công bố, không chỉ có một state trong control plane. Phục hồi dữ liệu và thay key phải giữ quyết định thu hồi, không âm thầm đưa material không còn đáng tin trở lại luồng bình thường.
