# Cryptographic key lifecycle

## 1. Quản lý khóa là quản lý cả vòng đời

Một thuật toán mật mã đúng chỉ phát huy tác dụng khi khóa được tạo, cấp quyền, sử dụng, thay thế và hủy đúng cách.

Một hệ thống có thể mã hóa dữ liệu bằng thuật toán phù hợp nhưng vẫn mất an toàn nếu:

- Khóa nằm trong source code hoặc log.
- Mọi workload đều có quyền giải mã mọi tenant.
- Khóa cũ vẫn tiếp tục tạo dữ liệu mới sau thời hạn.
- Backup không có khóa cần thiết để phục hồi.
- Rotation chỉ đổi tên tham chiếu mà không đổi key material.
- Khóa bị xóa khi dữ liệu hoặc bản sao lưu vẫn còn phụ thuộc.
- Khóa đã nghi bị lộ được tiếp tục dùng như một khóa bình thường.

Cryptographic key lifecycle là tập trạng thái, thao tác và kiểm soát áp dụng từ khi khóa được hoạch định cho tới khi key material không còn được sử dụng hoặc có thể khôi phục theo phạm vi đã xác định.

[NIST SP 800-57 Part 1 Revision 5](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-57pt1r5.pdf) cung cấp khung hướng dẫn về trạng thái, chức năng và bảo vệ keying material xuyên vòng đời.

Trong thiết kế yêu cầu bảo mật, mục tiêu là trả lời:

> Khóa nào được phép thực hiện thao tác nào, cho ai, trong khoảng thời gian nào, và bằng chứng nào cho thấy chuyển trạng thái đã có hiệu lực?

### 1.1. Ba mục tiêu cần cân bằng

| Mục tiêu | Câu hỏi |
|---|---|
| Bí mật và toàn vẹn khóa | Ai có thể đọc, thay hoặc dùng key material? |
| Sử dụng đúng mục đích | Khóa có bị dùng sai thuật toán, tenant hoặc hành động không? |
| Khả năng phục hồi dữ liệu | Khi sự cố hoặc rotation xảy ra, dữ liệu cần giữ có còn dùng được không? |

Bảo vệ khóa không chỉ là ngăn lộ. Xóa một khóa quá sớm có thể làm dữ liệu hợp lệ không thể phục hồi. Giữ khóa không cần thiết quá lâu lại làm tăng phạm vi tác động khi bị lộ.

### 1.2. Không có một vòng đời giống nhau cho mọi loại khóa

Khóa mã hóa dữ liệu lâu dài, khóa ký, khóa HMAC và khóa phiên có nhu cầu khác nhau.

Ví dụ:

- Khóa mã hóa có thể ngừng encrypt mới nhưng còn cần decrypt dữ liệu cũ.
- Private signing key có thể ngừng ký, trong khi public key và bằng chứng xác minh cũ vẫn cần được giữ.
- HMAC verify thông thường vẫn cần secret hoặc quyền gọi dịch vụ verify phù hợp.
- Khóa phiên ngắn hạn thường không có cùng nhu cầu lưu trữ dài hạn như khóa dữ liệu.

Không sao chép một lịch rotate/delete chung cho mọi key chỉ vì chúng đều được gọi là secret.

## 2. Những khái niệm phải phân biệt

### 2.1. Logical key, version và key material

| Khái niệm | Ý nghĩa |
|---|---|
| Logical key | Đối tượng quản lý đại diện cho một mục đích hoặc nhóm khóa |
| Key version | Một phiên bản có danh tính, metadata và vòng đời cụ thể |
| Key material | Những giá trị mật mã thực tế dùng trong thuật toán |
| Alias hoặc primary pointer | Tham chiếu có thể trỏ sang version khác |
| Key handle/reference | Cách yêu cầu thao tác mà không nhất thiết lấy raw key |

Tên và mức tách biệt phụ thuộc nền tảng. Ví dụ, [Cloud KMS mô tả trạng thái ở mức key version](https://docs.cloud.google.com/kms/docs/key-states), trong khi những dịch vụ khác có mô hình logical resource và material khác.

Điều cần đặc tả là hệ thống thực sự theo dõi trạng thái ở mức nào.

### 2.2. Đổi alias không đồng nghĩa đổi khóa

Nếu alias document-key chuyển tên nhưng vẫn tham chiếu cùng material, các bảo đảm gắn với tuổi, lượng sử dụng hoặc miền nonce của khóa không tự được làm mới.

Ngược lại, một logical key giữ nguyên ID có thể được nền tảng thay material bên dưới theo cơ chế rotation của nó.

Vì vậy, audit cần phân biệt thay tên, thay pointer, tạo version và thay material. Không kết luận rotation thành công chỉ từ việc một chuỗi cấu hình thay đổi.

### 2.3. Public key không phải bí mật nhưng vẫn cần được bảo vệ

Nếu public key dùng để xác minh bị thay bởi key của bên khác, hệ thống có thể chấp nhận bằng chứng giả theo quan hệ tin cậy sai.

Các yêu cầu cho public key tập trung vào nguồn, tính toàn vẹn, liên kết danh tính và policy xác minh. Không bỏ quản lý vòng đời chỉ vì key không cần giữ bí mật.

### 2.4. Key metadata cũng quan trọng

Metadata có thể gồm:

- Loại khóa và profile mật mã.
- Mục đích sử dụng.
- Owner và workload được cấp quyền.
- Tenant hoặc miền dữ liệu.
- State và thời điểm hiệu lực.
- Nguồn tạo hoặc import.
- Key version và quan hệ wrapping.
- Ngân sách sử dụng.
- Chính sách backup, archive và hủy.

Không cần đặt key material vào inventory. Inventory quản lý tham chiếu và thuộc tính cần thiết, không trở thành một kho raw key thứ hai.

## 3. Bắt đầu từ tài sản, mục đích và dependency

### 3.1. Một khóa cần có lý do tồn tại

Trước khi tạo khóa, cần xác định:

```text
Tài sản: nội dung tài liệu nội bộ
Mục đích: encryption ở lớp ứng dụng
Chủ sở hữu: nhóm phụ trách tài liệu
Workload: document-service
Phạm vi: môi trường production và miền dữ liệu đã chỉ định
Thao tác: encrypt mới, decrypt dữ liệu được phép
Phụ thuộc: ciphertext, wrapped DEK, backup và cấu hình version
```

Nếu không xác định được tài sản hoặc owner, việc rotate, thu hồi và hủy về sau sẽ dựa trên phỏng đoán.

### 3.2. Dependency có thể nhiều tầng

Trong envelope encryption:

```text
KEK bảo vệ DEK
DEK bảo vệ dữ liệu
Metadata liên kết ciphertext với đúng khóa và profile
```

Một KEK có thể bảo vệ nhiều DEK; một DEK có thể bảo vệ dữ liệu theo profile đã định nghĩa. Hủy KEK có thể ảnh hưởng nhiều hơn một bản ghi.

Inventory cần ghi nhận đủ quan hệ để trả lời:

- Dữ liệu nào còn phụ thuộc version này?
- Wrapped key nào cần được rewrap?
- Backup nào vẫn cần key cũ?
- Có bản export hoặc replica nào dùng material tương ứng không?
- Những workload nào còn gọi version đó?

Không phải KMS luôn tự biết toàn bộ ciphertext trong ứng dụng. Ứng dụng phải có cách quản lý dependency ở mức cần thiết.

### 3.3. Tách môi trường và mục đích

Production, thử nghiệm và phát triển không nên dùng chung key material theo mặc định.

Tương tự, một khóa ký không tự được phép dùng cho encryption; một khóa của tenant A không tự mở quyền dữ liệu tenant B.

Cần thể hiện việc tách qua cấu trúc khóa, policy quyền và kiểm tra context, thay vì chỉ bằng tên đặt theo quy ước.

## 4. Mô hình trạng thái có thể kiểm chứng

Bảng dưới là mô hình chính sách ứng dụng minh họa. Nó không phải bản sao tên trạng thái hoặc API của mọi KMS.

| Trạng thái | Ý nghĩa trong mô hình ví dụ | Sử dụng bình thường |
|---|---|---|
| PREPARED | Đã tạo nhưng chưa được kích hoạt cho nghiệp vụ | Không tạo bảo vệ dữ liệu thật |
| ACTIVE | Được phép theo mục đích, quyền và hạn sử dụng | Thao tác trong policy |
| RETIRED | Ngừng tạo dữ liệu bảo vệ mới | Chỉ xử lý dữ liệu cũ theo phạm vi |
| DISABLED | Tạm dừng các thao tác do hệ thống quản lý | Từ chối theo policy |
| COMPROMISED | Đã lộ hoặc nghi bị lộ | Không dùng như key tin cậy bình thường |
| DESTROY_PENDING | Đang chờ hoàn tất điều kiện hủy | Không hoạt động như key ACTIVE |
| DESTROYED | Material đã bị loại theo phạm vi và cơ chế hủy | Không sử dụng material đã hủy |

### 4.1. State không phải điều kiện duy nhất

Một key ở ACTIVE vẫn phải chịu:

- Quyền của workload.
- Mục đích và thuật toán được phép.
- Phạm vi tenant hoặc dữ liệu.
- Thời hạn hiệu lực.
- Giới hạn số lần dùng hoặc lượng dữ liệu.
- Ngữ cảnh encryption/decryption cần thiết.
- Quyết định về sự cố và các ràng buộc hạ tầng.

Không để một boolean enabled thay cho toàn bộ chính sách.

### 4.2. Chuyển trạng thái cần có điều kiện

Ví dụ:

```text
PREPARED → ACTIVE:
    material sẵn sàng
    profile đúng
    quyền đã được kiểm tra
    workload và metadata tương thích
    owner đã phê duyệt theo quy trình

ACTIVE → RETIRED:
    version mới sẵn sàng cho việc tạo mới
    không tiếp tục phát hành dữ liệu mới bằng version cũ
    quyền xử lý dữ liệu cũ được giới hạn

RETIRED → DESTROY_PENDING:
    đã kiểm kê dependency
    dữ liệu và backup đã được xử lý theo retention
    có phê duyệt và phương án kiểm chứng

DESTROY_PENDING → DESTROYED:
    cơ chế hủy hoàn tất
    có readback hoặc bằng chứng tương ứng
    các bản sao trong phạm vi được xử lý
```

Không chuyển trực tiếp từ “đang dùng” sang “đã hủy” chỉ vì một tác vụ housekeeping thấy khóa lâu không có log.

### 4.3. Disabled không đồng nghĩa destroyed

Một key bị disable thường còn material và có thể có khả năng bật lại theo nền tảng. Hủy là một thao tác khác, có hệ quả phục hồi khác.

Tài liệu [trạng thái key version của Cloud KMS](https://docs.cloud.google.com/kms/docs/key-states) minh họa sự phân biệt enabled, disabled, chờ hủy và destroyed. Khi triển khai, cần ánh xạ mô hình policy của ứng dụng sang trạng thái thực của dịch vụ đã chọn, kể cả những giới hạn và cơ chế khôi phục của nó.

### 4.4. Compromised không phải một lần hết hạn thông thường

Một key hết hạn tạo mới có thể còn phù hợp để xử lý dữ liệu cũ theo policy.

Một key bị lộ đặt ra câu hỏi khác: bên không được phép có thể đã đọc dữ liệu, tạo ciphertext, tag hoặc chữ ký hợp lệ trong khoảng ảnh hưởng.

Không chỉ rotate rồi khẳng định mọi dữ liệu cũ còn nguyên độ tin cậy. Cần quy trình đánh giá phạm vi, thời điểm và bằng chứng độc lập phù hợp.

## 5. Hoạch định và tạo khóa

### 5.1. Profile phải có trước hoặc cùng thời điểm tạo

Cần xác định:

- Thuật toán và key size theo baseline.
- Mục đích sử dụng.
- Nguồn entropy hoặc cơ chế generate được quản lý.
- Material có được export hay không.
- Module, provider hoặc dịch vụ thực hiện thao tác.
- Các quyền quản trị và sử dụng.
- Thời điểm kích hoạt và hạn dùng.
- Yêu cầu về lưu trữ, backup và vùng triển khai.

Không để người gọi tạo một key với thuật toán tùy ý rồi yêu cầu ứng dụng chấp nhận vì key đã tồn tại.

### 5.2. Sinh khóa trong ranh giới phù hợp

Có thể tạo khóa trong module mật mã hoặc dịch vụ quản lý khóa, hoặc bằng một cơ chế được thiết kế theo yêu cầu triển khai.

Điều cần đạt là:

- Key material được tạo đúng profile.
- Không xuất hiện ở nơi không cần thiết.
- Không được ghi vào log hoặc artifact build.
- Việc cấp quyền gắn với workload thực tế.
- Có thông tin nguồn và người/tác vụ tạo.

Chỉ dùng một hàm sinh số ngẫu nhiên không tự giải quyết phân phối, lưu trữ và quyền sử dụng khóa.

### 5.3. Import là một luồng riêng cần kiểm soát

Khóa import có thể đã có những bản sao bên ngoài KMS. Những bản sao đó ảnh hưởng tới nhận định “đã hủy” hoặc “không export”.

Yêu cầu import cần xác định:

- Nguồn và quyền sở hữu material.
- Cách bảo vệ trong quá trình nhập.
- Xác minh profile và metadata.
- Bản sao gốc được giữ ở đâu hoặc bị hủy thế nào.
- Ai có thể import lại.
- Hành vi khi material import hết hạn hoặc không còn khả dụng.

Không coi việc đã nhập vào HSM là bằng chứng raw key chưa từng tồn tại ngoài HSM.

## 6. Phân phối, lưu trữ và kích hoạt

### 6.1. Ưu tiên quyền gọi thay vì phát raw key rộng rãi

Một workload có thể được cấp quyền encrypt/decrypt hoặc sign/verify thông qua handle hoặc API mà không được đọc raw key.

Điều này giảm số nơi giữ material, nhưng cần tiếp tục giới hạn:

- Workload identity.
- Key reference.
- Operation.
- Context và miền dữ liệu.
- Môi trường và đường truy cập.
- Thời hạn quyền.

Có quyền gọi decrypt vẫn là quyền nhạy cảm dù không thể export key. API ứng dụng phải kiểm tra quyền dữ liệu, không chỉ dựa vào việc KMS cho phép workload sử dụng khóa.

### 6.2. Phân phối khóa có bảo vệ

Nếu kiến trúc bắt buộc chuyển material hoặc wrapped key, cần xác thực bên nhận và bảo vệ bí mật, toàn vẹn cùng metadata liên kết.

Không gửi raw key qua email, issue, clipboard dùng chung hoặc file tạm không có quản lý vòng đời.

Mỗi bản sao mới tạo thêm một nơi cần kiểm soát quyền, backup, log và hủy. Điều đó phải nằm trong inventory và threat model.

### 6.3. Bootstrap identity

Ứng dụng cần có cách xác thực với hệ thống khóa. Nếu credential bootstrap được hardcode cùng source, rủi ro có thể chỉ bị chuyển từ key dữ liệu sang một secret khác.

Yêu cầu nên chỉ rõ cơ chế identity của workload, phạm vi quyền và cách thay thế. Không tạo một vòng phụ thuộc không phục hồi được, trong đó mọi credential cần giải mã đều cần chính dịch vụ chưa thể truy cập.

### 6.4. Kích hoạt phải nhất quán với envelope

Một request mã hóa cần dùng material và key reference tương ứng.

Không nên:

```text
Đọc alias đang trỏ version A
    → mã hóa bằng A
    → alias đổi sang B
    → lưu envelope ghi version B
```

Thiết kế phải snapshot hoặc nhận metadata có thẩm quyền cho đúng thao tác, để ciphertext và thông tin giải mã được lưu cùng nhau một cách nhất quán.

Trong một số dịch vụ, ciphertext đã mang đủ thông tin để nền tảng chọn material. Trong mô hình khác, ứng dụng phải lưu version reference. Hợp đồng phải theo cơ chế thật, không tự giả định mọi KMS giống nhau.

## 7. Sử dụng khóa và cryptoperiod

### 7.1. Tạo bảo vệ mới và xử lý dữ liệu cũ

Cần tách hai khoảng:

- Khoảng được dùng key để tạo dữ liệu bảo vệ mới.
- Khoảng còn được xử lý dữ liệu đã bảo vệ trước đó.

NIST SP 800-57 phân biệt những mục đích sử dụng theo phía tạo và phía xử lý, giúp giải thích vì sao ngừng tạo mới không nhất thiết đồng nghĩa hủy ngay material.

Trong thiết kế sản phẩm, nên diễn đạt bằng operation cụ thể: encrypt/decrypt, sign/verify hoặc wrap/unwrap. Không chỉ dùng một trường expiresAt cho mọi thao tác nếu chúng có thời hạn khác nhau.

### 7.2. Chọn cryptoperiod theo rủi ro và sử dụng

Các yếu tố cần xem xét:

- Mức nhạy cảm và thời gian cần bảo vệ dữ liệu.
- Thuật toán và profile.
- Lượng dữ liệu hoặc số thao tác dưới một key.
- Số bên có quyền sử dụng material.
- Khả năng bảo vệ môi trường.
- Giới hạn nonce, counter hoặc các tham số khác.
- Chi phí thay key và migration.
- Khả năng phát hiện, thu hồi và khôi phục.

Không có một con số số ngày duy nhất phù hợp mọi loại key. Một policy cần giá trị và căn cứ cụ thể cho từng nhóm, không chỉ câu “rotate định kỳ”.

### 7.3. Thời hạn không thay thế ngân sách sử dụng

Một key còn trong thời hạn vẫn có thể đạt giới hạn theo số lần dùng hoặc lượng dữ liệu. Một key ít được dùng vẫn có thể cần thay vì một sự cố hoặc thay đổi baseline.

Hệ thống nên có trigger theo thời gian, mức sử dụng và sự kiện, tùy profile.

Đối với AEAD có yêu cầu nonce, trạng thái cấp nonce cũng thuộc miền vòng đời key. Restore hoặc đổi alias không được làm mất bảo đảm gắn với cùng material.

### 7.4. Key cache và độ trễ thu hồi

Nếu ứng dụng giữ material hoặc kết quả unwrap trong bộ nhớ, disable key ở KMS không nhất thiết làm mọi bản sao cache lập tức mất khả năng sử dụng.

Yêu cầu phải xác định:

- Có cache gì và tại đâu.
- TTL hoặc giới hạn sử dụng.
- Cách truyền tín hiệu thu hồi.
- Thời gian tối đa để quyền ngừng có hiệu lực.
- Hành vi khi mất liên lạc với key service.
- Cách hạn chế dump và quyền đọc bộ nhớ theo threat model.

Không hứa “thu hồi ngay lập tức” nếu kiến trúc chưa có cách kiểm soát các bản sao đang hoạt động.

## 8. Ví dụ Java: policy thời gian cho khóa mã hóa

Ví dụ Java 17 trở lên sau chỉ mô tả một phần policy cho khóa mã hóa đối xứng của ứng dụng giả định. Nó không ánh xạ nguyên vẹn mọi trạng thái của một nhà cung cấp KMS.

```java
import java.time.Instant;
import java.util.Objects;

public final class EncryptionKeyLifecycle {
    public enum State {
        PREPARED,
        ACTIVE,
        RETIRED,
        DISABLED,
        COMPROMISED,
        DESTROY_PENDING,
        DESTROYED
    }

    public record Policy(
            String versionReference,
            State state,
            Instant validFrom,
            Instant encryptUntil,
            Instant decryptUntil
    ) {
        public Policy {
            Objects.requireNonNull(versionReference);
            Objects.requireNonNull(state);
            Objects.requireNonNull(validFrom);
            Objects.requireNonNull(encryptUntil);
            Objects.requireNonNull(decryptUntil);

            if (versionReference.isBlank()) {
                throw new IllegalArgumentException(
                        "Missing key version reference"
                );
            }

            if (!validFrom.isBefore(encryptUntil)
                    || decryptUntil.isBefore(encryptUntil)) {
                throw new IllegalArgumentException(
                        "Invalid key usage periods"
                );
            }
        }
    }

    private EncryptionKeyLifecycle() {
    }

    public static boolean mayEncrypt(Policy policy, Instant now) {
        Objects.requireNonNull(policy);
        Objects.requireNonNull(now);

        return policy.state() == State.ACTIVE
                && !now.isBefore(policy.validFrom())
                && now.isBefore(policy.encryptUntil());
    }

    public static boolean mayDecrypt(Policy policy, Instant now) {
        Objects.requireNonNull(policy);
        Objects.requireNonNull(now);

        boolean allowedState =
                policy.state() == State.ACTIVE
                || policy.state() == State.RETIRED;

        return allowedState
                && !now.isBefore(policy.validFrom())
                && now.isBefore(policy.decryptUntil());
    }
}
```

Các điểm của hợp đồng ví dụ:

- validFrom bao gồm thời điểm bắt đầu.
- encryptUntil và decryptUntil là cận không bao gồm.
- RETIRED không cho encrypt mới.
- DISABLED, COMPROMISED và các state hủy không cho sử dụng bình thường.
- Metadata và thời gian phải đến từ nguồn có thẩm quyền.
- Không tìm thấy policy hoặc không đánh giá được không trở thành quyền cho phép.

### 8.1. Code chưa phải toàn bộ authorization

Một kết quả mayDecrypt=true vẫn cần:

- Workload có quyền gọi operation.
- Tenant và object nằm trong phạm vi.
- Key reference được resolver cho phép.
- Provider thực tế còn cho phép dùng material.
- Ngân sách sử dụng và profile còn hợp lệ.
- Các ràng buộc dữ liệu được xác minh.

Ứng dụng không được tự lấy Policy từ JSON của người dùng rồi xem đó là sự thật về trạng thái key.

### 8.2. Trạng thái phải đúng ở điểm sử dụng

Nếu policy được cache quá lâu, code có thể cho phép theo một snapshot đã lỗi thời.

Thiết kế cần xác định hiệu lực của việc đổi state và cách phối hợp với thao tác đang chạy. Không giả định một hàm pure tự cung cấp tính nguyên tử giữa database policy, KMS và storage.

Trong hệ thống thật, enforcement tại dịch vụ khóa và các giới hạn cache phải phối hợp với kiểm tra của ứng dụng.

## 9. Rotation, rewrap và re-encryption

### 9.1. Rotation có nhiều nghĩa

Cần phân biệt:

| Thao tác | Điều thay đổi | Dữ liệu cũ có tự đổi không? |
|---|---|---|
| Chuyển alias/primary | Điểm chọn khóa cho thao tác mới | Không mặc định |
| Rotate material | Material dùng theo cơ chế nền tảng | Theo hợp đồng nền tảng |
| Rewrap DEK | Lớp bảo vệ của key dữ liệu | Ciphertext dữ liệu có thể giữ nguyên |
| Re-encrypt dữ liệu | Dữ liệu được mã hóa lại | Có theo quá trình migration |
| Đổi profile | Thuật toán hoặc định dạng áp dụng | Cần thiết kế tương thích/migration |

Ví dụ, tài liệu [rotation của AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html) nêu việc rotate KMS material không tự rotate data key hay mã hóa lại dữ liệu đã được chúng bảo vệ.

Đây là một ví dụ về lý do phải đọc đúng hợp đồng dịch vụ, không suy ra “bật auto-rotation” đồng nghĩa mọi dữ liệu đã chuyển sang key mới.

### 9.2. Luồng rotation có kiểm soát

Một kế hoạch có thể gồm:

1. Tạo hoặc chuẩn bị version mới.
2. Kiểm tra profile, quyền và khả năng phục hồi cần thiết.
3. Xác minh operation bằng dữ liệu tổng hợp phù hợp.
4. Cho thao tác mới chọn version mới.
5. Giữ đường xử lý dữ liệu cũ trong phạm vi.
6. Rewrap hoặc re-encrypt khi mục tiêu yêu cầu.
7. Kiểm kê dependency còn lại.
8. Ngừng quyền cũ theo từng giai đoạn.
9. Hủy chỉ khi đạt điều kiện riêng.

Danh sách này không đồng nghĩa mọi loại key đều phải đi qua cùng một migration. Điều cần có là mỗi bước liên quan được xác định hoặc giải thích không áp dụng.

### 9.3. Migration cần khả năng tiếp tục và đọc lại

Một tác vụ chuyển dữ liệu có thể bị dừng giữa chừng. Yêu cầu nên xác định:

- Cách nhận biết bản ghi đã chuyển.
- Cách tránh ghi metadata key mới với ciphertext cũ.
- Tính idempotent.
- Kiểm chứng dữ liệu sau khi ghi.
- Cách xử lý lỗi một phần.
- Cách quay lại hoặc tiếp tục mà không vi phạm nonce/profile.
- Những bản sao nằm ngoài database chính.

Không dùng số lượng record “đã quét” làm bằng chứng dữ liệu đã chuyển đúng.

### 9.4. Rotation khi compromised

Rotation theo lịch và ứng phó lộ key là hai tình huống khác nhau.

Nếu key cũ bị lộ, chuyển dữ liệu hiện tại sang key mới không làm những bản ciphertext cũ mà bên khác đã lấy trở nên bí mật trở lại.

Nếu key dùng cho MAC hoặc chữ ký bị lộ, dữ liệu được chấp nhận trong khoảng ảnh hưởng cần đánh giá lại. Một tag hoặc chữ ký hợp lệ không tự giải quyết câu hỏi ai đã tạo nó khi key không còn đáng tin.

## 10. Backup, archive và phục hồi

### 10.1. Backup dữ liệu chưa đủ

Một bản sao lưu ciphertext cần đồng thời có khả năng phục hồi:

- Material hoặc quyền truy cập key cần thiết.
- Metadata version và profile.
- Wrapped DEK và KEK tương ứng.
- Context như AAD nếu nó cần cho giải mã.
- Policy và identity cho workload phục hồi.

Không nên chỉ kiểm tra rằng file backup tồn tại hoặc checksum đúng.

### 10.2. Không backup mọi loại key theo cùng một cách

Key encryption lâu dài có thể cần chiến lược phục hồi để không mất dữ liệu.

Đối với private signing key hoặc key ngắn hạn, quyết định giữ bản sao phải xét mục đích và nguy cơ tạo bằng chứng giả. Public verification material, certificate chain và dữ liệu hỗ trợ xác minh cũng có nhu cầu giữ riêng.

Một quy tắc “backup tất cả secret” có thể làm tăng phạm vi lộ hoặc trái mục tiêu của một số loại key.

### 10.3. Recovery có quyền riêng

Quyền khôi phục key có thể làm vô hiệu hóa những giới hạn đang áp dụng trong môi trường bình thường.

Cần xác định:

- Ai được khởi tạo recovery.
- Điều kiện phê duyệt.
- Nơi material được khôi phục.
- Identity nào được phép sử dụng.
- Có được export raw key không.
- Thời hạn và cleanup sau recovery.
- Audit và readback.

Quy trình khôi phục không được trở thành một API lấy secret dễ hơn đường sử dụng thông thường.

### 10.4. Thử phục hồi có kiểm soát

Bằng chứng cần cho thấy dữ liệu tổng hợp được khôi phục trong thời gian và phạm vi đã cam kết, bằng chính cơ chế key/metadata dự kiến.

Không tạo một bản key plaintext để “chắc chắn có thể restore” rồi quên quản lý nó. Những bản sao thử cũng cần vòng đời và hủy theo policy.

## 11. Thu hồi, ngừng sử dụng và hủy khóa

### 11.1. Ba hành động khác nhau

- Ngừng tạo mới: chặn encrypt, sign hoặc generate-MAC mới theo mục đích.
- Thu hồi hoặc disable: ngăn những quyền sử dụng đã xác định.
- Hủy material: loại bỏ khả năng dùng hoặc khôi phục material theo phạm vi.

Không dùng ba thuật ngữ thay thế nhau trong ticket vận hành.

Đối với khóa công khai đã phân phối, việc disable một dịch vụ trung tâm không tự xóa bản sao public key ở client. Cần cơ chế cập nhật hoặc thu hồi quan hệ tin cậy phù hợp.

### 11.2. Điều kiện trước hủy

Một gate hủy có thể yêu cầu:

- Không còn dữ liệu phải giữ phụ thuộc key.
- Backup và replica đã được xem xét.
- Không còn migration dở.
- Public verification material cần giữ đã có phương án.
- Bản export/import và cache được đánh giá.
- Có owner và phê duyệt theo mức rủi ro.
- Đã quan sát giai đoạn ngừng sử dụng theo policy.
- Có thời điểm và cơ chế kiểm chứng hoàn tất.

Không có log sử dụng gần đây không chứng minh không có backup lạnh hoặc dữ liệu ít truy cập còn cần key.

### 11.3. Disable để thử tác động không thay mọi kiểm kê

Một giai đoạn disable có thể giúp phát hiện phụ thuộc đang hoạt động. Nhưng dữ liệu archive chỉ được đọc khi có sự cố có thể không tạo lỗi trong giai đoạn đó.

Vì vậy, quan sát là một nguồn bằng chứng, không thay thế inventory và kiểm tra phục hồi.

Tài liệu [xóa key của AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/deleting-keys.html) nhấn mạnh hệ quả mất khả năng giải mã và việc dịch vụ không giữ inventory của mọi ciphertext ứng dụng. Chính ứng dụng phải hiểu phạm vi phụ thuộc trước hành động hủy.

### 11.4. Hủy và cryptographic erasure

Cryptographic erasure chỉ đạt mục tiêu theo threat model nếu những key cần để khôi phục dữ liệu thực sự không còn khả dụng qua các bản sao trong phạm vi.

Cần xem xét:

- Material trong dịch vụ chính.
- Replica và hệ thống dự phòng.
- Bản import hoặc export bên ngoài.
- Backup của module khóa.
- Cache hoặc material đã unwrap.
- Key wrapping cấp cao hơn và bản sao thay thế.
- Metadata còn cho phép phục hồi qua một đường khác.

Xóa một hàng keyId trong database không tự là hủy mật mã. Một trạng thái API hiển thị destroyed cũng cần được hiểu theo hợp đồng của nhà cung cấp về hệ thống đang hoạt động, backup và khả năng import lại.

Không đưa ra lời hứa tuyệt đối về mọi bản sao vật lý nếu cơ chế và bằng chứng thực tế không hỗ trợ kết luận đó.

### 11.5. Metadata sau hủy

Có thể cần giữ bằng chứng không chứa material:

- Key reference hoặc định danh nội bộ.
- Loại và mục đích.
- Owner.
- Lịch sử chuyển trạng thái.
- Phê duyệt hủy.
- Thời điểm và kết quả xác minh.
- Dependency đã được xử lý.

Việc giữ audit không có nghĩa giữ lại secret. Quyền đọc metadata cũng cần theo phân loại hệ thống.

## 12. Phân quyền, trách nhiệm và audit

### 12.1. Tách quản trị key và sử dụng key

Một vai trò có quyền tạo hoặc đổi policy không nhất thiết cần quyền decrypt dữ liệu. Một workload cần encrypt không nhất thiết cần quyền hủy key.

Có thể tách:

| Vai trò | Trách nhiệm minh họa |
|---|---|
| Data owner | Xác định tài sản, retention và nhu cầu truy cập |
| Key owner | Sở hữu policy và vòng đời key |
| Key administrator | Thực hiện quản trị theo quyền được cấp |
| Workload | Gọi operation trong phạm vi |
| Security/approver | Đánh giá ngoại lệ hoặc thao tác rủi ro cao |
| Recovery operator | Khôi phục trong quy trình có kiểm soát |
| Auditor | Đọc bằng chứng theo quyền riêng |

Mức tách phải phù hợp quy mô và rủi ro; không bắt buộc mọi tác vụ thường ngày đều cần nhiều người. Những thao tác có hậu quả lớn cần cơ chế phê duyệt hoặc kiểm soát phù hợp.

### 12.2. Audit cần mô tả quyết định và kết quả

Một sự kiện có thể gồm:

```text
actor
workload
operation
key reference/version
purpose
environment
decision
previous state
new state
approval reference
request/correlation ID
result
```

Không ghi raw key, private key, plaintext dữ liệu hoặc credential gọi key service.

Key reference có thể là metadata nhạy cảm; log vẫn cần quyền truy cập và retention phù hợp.

### 12.3. API thành công chưa đủ cho mọi chuyển trạng thái

Cần readback state và kiểm chứng hiệu lực liên quan:

- Version mới có thật sự được dùng cho thao tác mới?
- Key disabled còn bị cache dùng tiếp ngoài cửa sổ cho phép không?
- Tác vụ hủy đã hoàn tất hay chỉ được lên lịch?
- Những node khác đã nhận policy mới chưa?

Bằng chứng phải phân biệt “đã gửi lệnh”, “nền tảng báo state” và “hành vi hệ thống đạt yêu cầu”.

## 13. Đặc tả yêu cầu có thể kiểm chứng

### 13.1. Yêu cầu mơ hồ

> Tất cả khóa phải được quản lý và rotate thường xuyên.

Phát biểu này thiếu phạm vi, mục đích, thời hạn và điều kiện hoàn thành.

### 13.2. Yêu cầu về inventory

> Mọi version khóa dùng để bảo vệ dữ liệu production phải có owner, purpose, profile, nguồn material, operation được phép, thời điểm sử dụng và tham chiếu dependency cần phục hồi. Inventory không chứa raw material và được đối chiếu với những key thực tế đang sử dụng.

### 13.3. Yêu cầu về sử dụng

> Chỉ workload đã xác minh được gọi operation trên key trong phạm vi đã cấp. State ACTIVE không tự cấp quyền. Ngừng tạo mới và tiếp tục xử lý dữ liệu cũ có policy riêng; cache không được vượt thời gian thu hồi đã công bố.

### 13.4. Yêu cầu về rotation

> Rotation phải xác định rõ material hoặc version thay đổi, điểm chọn cho thao tác mới và cách giữ khả năng xử lý dữ liệu cũ. Nếu mục tiêu yêu cầu rewrap hoặc re-encrypt, có inventory, readback và xử lý lỗi một phần. Bật một cấu hình tự động không tự là bằng chứng dữ liệu đã migration.

### 13.5. Yêu cầu về hủy

> Key chỉ được hủy sau khi dependency của dữ liệu, backup, replica và các bản sao material trong phạm vi được đánh giá theo policy. Thao tác có phê duyệt, thời hạn theo cơ chế nền tảng và bằng chứng hoàn tất. Không có raw material được giữ lại ngoài inventory để tránh mất khả năng khôi phục một cách không kiểm soát.

### 13.6. Yêu cầu về sự cố

> Khi nghi key bị lộ, hệ thống có khả năng ngừng những thao tác liên quan trong thời gian đã xác định, chuyển sang key phù hợp và đánh giá dữ liệu trong phạm vi ảnh hưởng. Không khôi phục trạng thái tin cậy chỉ bằng việc đổi alias hoặc hết cảnh báo.

### 13.7. Mẫu truy vết

```text
ID: KEY-LIFE-01
Tài sản:
    key material và dữ liệu phụ thuộc
Phạm vi:
    các version khóa production trong inventory
Quy tắc:
    owner + purpose + state + operation + thời hạn
Điểm thực thi:
    key service, policy workload và adapter ứng dụng
Rotation:
    version mới cho thao tác mới, dữ liệu cũ có lộ trình
Recovery:
    backup kèm key/context cần thiết
Destruction:
    gate dependency và phê duyệt
Bằng chứng:
    readback state, hành vi và phục hồi dữ liệu tổng hợp
```

## 14. Ma trận bằng chứng và tình huống chấp nhận

Những tình huống dưới đây là tiêu chí cho việc triển khai, không phải kết quả kiểm thử đã chạy cho một hệ thống cụ thể.

| Rủi ro | Kiểm soát | Bằng chứng chấp nhận |
|---|---|---|
| Key không có chủ sở hữu | Inventory bắt buộc | Không có version production không xác định purpose/owner |
| Material xuất hiện ngoài phạm vi | Giới hạn export và quản lý bản sao | Không có secret trong source, log hoặc artifact ngoài policy |
| Workload dùng sai key | Scope theo operation và dữ liệu | Request ngoài phạm vi bị từ chối |
| Key hết hạn vẫn tạo dữ liệu mới | Policy operation/time | Sau cận thời gian không có encryption mới bằng key cũ |
| Rotation chỉ đổi tên | Theo dõi version/material | Bằng chứng thao tác mới dùng đúng material theo hợp đồng |
| Mất dữ liệu cũ sau rotation | Giữ khả năng recipient use | Dữ liệu mẫu cũ còn xử lý được trong thời hạn |
| Restore làm lặp nonce | Quản lý trạng thái và key recovery | Không tiếp tục cấp nonce trong miền đã sử dụng |
| Disable không thu hồi cache | Giới hạn TTL và invalidation | Hiệu lực đạt trong thời hạn cam kết |
| Hủy khi backup còn cần key | Gate dependency | Phục hồi hoặc retention được giải quyết trước hủy |
| Key compromise bị xử lý như hết hạn | Runbook riêng | Thao tác bị chặn và dữ liệu ảnh hưởng được đánh giá |

### 14.1. Kiểm tra operation và thời gian

Bao phủ:

- PREPARED không thực hiện nghiệp vụ thật.
- ACTIVE chỉ cho operation được cấp.
- RETIRED không encrypt mới nhưng xử lý dữ liệu cũ theo policy.
- DISABLED bị từ chối trong cửa sổ hiệu lực đã cam kết.
- Hành vi tại đúng thời điểm bắt đầu và kết thúc.
- State không nhận diện được không rơi vào nhánh cho phép.
- Metadata bị thiếu hoặc không tải được không tạo quyền mặc định.

Không chỉ kiểm tra state trên console. Cần dùng identity và đường gọi đại diện cho workload thật.

### 14.2. Kiểm tra rotation và concurrency

Cần quan sát:

- Request đang chạy khi primary đổi.
- Ciphertext và key reference luôn phù hợp.
- Node còn cache cấu hình cũ.
- Tác vụ migration chạy lại sau lỗi.
- Version cũ không được chọn cho thao tác mới ngoài cửa sổ đã định nghĩa.
- Không có fallback tự động sang material không đúng profile.

Không được thử giải mã bằng mọi key để che lỗi envelope/version.

### 14.3. Kiểm tra recovery

Dùng dữ liệu tổng hợp để xác nhận:

- Backup dữ liệu cùng những dependency key cần thiết.
- Identity phục hồi chỉ có quyền theo quy trình.
- Key và context được khôi phục đúng.
- Dữ liệu được đọc lại trong mục tiêu phục hồi đã công bố.
- Bản sao tạm được quản lý sau khi thử.
- Restore không quay lùi những trạng thái an toàn như allocator nonce.

Một thông báo “backup success” chưa đủ làm bằng chứng.

### 14.4. Kiểm tra hủy trong môi trường phù hợp

Tình huống hủy cần dùng tài nguyên thử đúng phạm vi, không tác động key đang bảo vệ dữ liệu thật.

Bằng chứng có thể gồm:

- Lệnh được tiếp nhận.
- Trạng thái chờ hủy.
- Khả năng khôi phục trong giai đoạn cho phép, nếu có.
- Trạng thái hoàn tất.
- Operation không còn khả dụng theo cơ chế.
- Metadata audit còn đủ nhưng không có material.
- Những bản sao trong phạm vi được xử lý đúng.

Không suy ra thời gian xóa backup hoặc mọi bản sao vật lý chỉ từ một trạng thái API nếu nhà cung cấp có hợp đồng khác.

### 14.5. Kiểm tra lỗi phụ thuộc

Bao phủ mất key service, sai quyền, mất vùng, policy mới chưa đồng bộ và key không khả dụng.

Kết quả cần bảo đảm:

- Không ghi plaintext thay cho ciphertext để tiếp tục.
- Không dùng key test hoặc key mặc định.
- Không bỏ tag hoặc chữ ký verification.
- Retry có giới hạn và không tạo tác dụng phụ ngoài ý muốn.
- Lỗi đủ để vận hành chẩn đoán mà không lộ bí mật.

## 15. Vận hành và những sai lầm cần tránh

### 15.1. Những chỉ số hữu ích

- Key/version không có owner hoặc purpose.
- Version sắp hết thời hạn tạo mới.
- Key gần đạt ngân sách sử dụng.
- Khóa cũ còn nhận thao tác mới.
- Dependency migration chưa hoàn tất.
- Thời gian có hiệu lực của disable hoặc revoke.
- Lỗi decrypt/verify theo version.
- Backup/recovery chưa được kiểm chứng.
- Hủy đang chờ hoặc quá thời hạn dự kiến.
- Quyền quản trị hoặc sử dụng mở rộng bất thường.

Không biến dashboard thành một kho material. Các chỉ số nên dựa trên metadata được phân loại và tổng hợp phù hợp.

### 15.2. Những sai lầm phổ biến

- Coi tên alias là key material.
- Dùng một state enabled cho mọi operation và thời hạn.
- Bật auto-rotation rồi cho rằng dữ liệu đã mã hóa lại.
- Tách key theo tên nhưng dùng chung material.
- Backup mọi key không xét mục đích.
- Xóa key chỉ vì không có request gần đây.
- Hứa thu hồi ngay dù cache vẫn dùng tiếp.
- Chỉ bảo vệ raw key mà bỏ quyền gọi decrypt.
- Restore dữ liệu mà quên key reference hoặc AAD.
- Hủy key trong KMS nhưng bỏ các bản import/export.
- Dùng key bị nghi lộ như key nghỉ bình thường.
- Tạo một bản plaintext dự phòng không nằm trong quản lý.

### 15.3. Những thay đổi cần đánh giá lại

- Thêm workload hoặc tenant mới.
- Đổi provider hay module mật mã.
- Cho phép export hoặc import.
- Thêm vùng hoặc replica.
- Thay cache key.
- Đổi profile, key size hoặc nonce allocator.
- Thay chính sách retention và backup.
- Thay quyền recovery hoặc destruction.
- Tích hợp một nguồn dữ liệu archive mới.

Vòng đời khóa phải đi cùng vòng đời dữ liệu và kiến trúc, không phải một tác vụ được làm một lần lúc tạo ứng dụng.

## 16. Điểm cần ghi nhớ

Cryptographic key lifecycle bao phủ nhiều hơn generate và rotate. Nó liên kết material, version, purpose, quyền sử dụng, thời gian, dữ liệu phụ thuộc và bằng chứng chuyển trạng thái.

Thiết kế cần tách ngừng tạo mới khỏi xử lý dữ liệu cũ, phân biệt rotation với rewrap/re-encryption, đồng thời giữ khả năng phục hồi trong phạm vi cần thiết. Hủy khóa chỉ được xem là đạt khi điều kiện dữ liệu và bản sao đã được giải quyết theo policy.

Yêu cầu có thể kiểm chứng phải nói rõ ai được làm gì, ở state nào, tới khi nào và bằng chứng nào được quan sát. Một key được lưu trong KMS vẫn cần những quyết định đó để trở thành một phần của hệ thống bảo mật đúng.
