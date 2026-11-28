# Giới hạn dữ liệu theo key trong mật mã đối xứng

**Giới hạn dữ liệu theo key (per-key data limits)** là tập các ràng buộc về **lượng dữ liệu**, **số lần thực hiện phép toán mật mã**, **số khối**, **nonce/IV**, **thời gian sử dụng** và đôi khi **số đối tượng dữ liệu** được phép bảo vệ bằng **một khóa hoặc một phiên bản khóa**. Khi đạt ngưỡng, hệ thống phải ngừng dùng khóa cho thao tác mới, cấp khóa mới hoặc chuyển sang phiên bản khóa khác theo chính sách.

Đây là chủ đề quan trọng của chương **Mật mã đối xứng** trong module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**: một thuật toán mạnh như AES cũng không đảm bảo an toàn vô hạn nếu một key bị dùng quá lâu, tái sử dụng nonce sai cách hoặc được chia sẻ cho quá nhiều workload. Giới hạn sử dụng khóa phải gắn với vòng đời **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi, hủy**, cùng **KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán**.

> **Không có một con số dung lượng tối đa áp dụng cho mọi key AES.** Giới hạn thực tế phụ thuộc vào **mode** (GCM, CTR, CBC, XTS...), cách sinh IV/nonce, độ dài thẻ xác thực, quy mô sử dụng, giả định an toàn và chính sách vận hành. Phải phân biệt giới hạn **cho một lần mã hóa**, **cho một nonce** và **cho toàn bộ vòng đời khóa**.

## 1. Vì sao một khóa không nên mã hóa dữ liệu vô hạn?

Khi ngày càng nhiều dữ liệu được xử lý dưới cùng một khóa, một số rủi ro tăng lên:

1. **Trùng nonce/IV:** với các chế độ yêu cầu nonce duy nhất như AES-GCM, hai lần mã hóa dùng cùng **key + nonce** có thể làm phá vỡ tính bí mật và tính toàn vẹn. Nếu nonce được chọn ngẫu nhiên, xác suất va chạm tăng theo số lần phát sinh.
2. **Giới hạn toán học của chế độ:** mỗi mode có giới hạn về độ dài thông điệp, bộ đếm, tổng số khối xử lý và biên an toàn của xác thực. Vi phạm điều kiện có thể khiến bảo đảm mật mã không còn như thiết kế.
3. **Tăng phạm vi lộ dữ liệu:** nếu key bị chiếm đoạt, tất cả bản mã còn được bảo vệ bởi key đó đều có khả năng bị ảnh hưởng; cùng một key dùng quá rộng làm tăng hậu quả.
4. **Gia tăng quyền và phụ thuộc:** càng nhiều hệ thống dùng chung một key, việc phân quyền, xoay vòng, thu hồi và hủy càng khó, đồng thời dễ tác động dây chuyền.
5. **Khó chứng minh tuân thủ:** nếu không có key ID, phiên bản, số lượng thao tác và thống kê dung lượng, đội vận hành không thể biết khi nào cần chuyển khóa.

**Đổi khóa theo lịch** (ví dụ mỗi tháng) chỉ là một phần quản lý vòng đời. Một dịch vụ xử lý lưu lượng tăng đột biến có thể chạm giới hạn trước khi hết tháng. Vì vậy chính sách nên kết hợp **ngưỡng sử dụng, thời hạn và cảnh báo sự cố**, thay vì chỉ dựa vào lịch.

## 2. Phân biệt các loại giới hạn

| Phạm vi | Đơn vị ví dụ | Mục đích |
| --- | --- | --- |
| **Một lần mã hóa (per invocation)** | Byte plaintext/AAD, số khối, độ dài bản mã | Tránh vượt giới hạn của mode và định dạng thông điệp. |
| **Một nonce hoặc IV** | Số khối/byte dùng với một giá trị nonce | Không làm tràn bộ đếm hoặc sử dụng sai cách ghép nonce với key. |
| **Một key/phiên bản key** | Tổng số lần mã hóa, tổng byte/khối, thời hạn, số bản ghi | Hạn chế xác suất trùng nonce, suy giảm biên an toàn và phạm vi tác động. |
| **Một miền phân phối** | Số node/worker/tenant cùng dùng khóa | Bảo đảm các node dùng chung **một ngân sách** và quy tắc nonce thống nhất. |
| **Một dữ liệu/tenant** | Tập bản mã phụ thuộc DEK/KEK | Cho phép xoay, tái mã hóa hoặc xóa dữ liệu trong phạm vi cần thiết. |

Cần theo dõi riêng **số lần mã hóa** và **lượng dữ liệu đã mã hóa**. Một triệu thông điệp 100 byte và một triệu thông điệp 10 MB có cùng số lần gọi nhưng tổng khối xử lý rất khác nhau. Ngược lại, một thông điệp cực lớn có thể chạm giới hạn **per invocation** dù key còn mới.

**Ghi nhớ:** Một key ID trong KMS có thể có nhiều **phiên bản vật liệu khóa** do xoay vòng. Bộ đếm cần xác định chính xác nó đang quản lý **phiên bản mật mã thực sự sử dụng** nào, chứ không được nhầm alias hiện tại với tất cả phiên bản lịch sử.

## 3. Trường hợp trọng tâm: AES-GCM

**AES-GCM** là chế độ mã hóa xác thực (**AEAD**) dựa trên AES, kết hợp tính bí mật với kiểm tra tính toàn vẹn của ciphertext và **AAD (Additional Authenticated Data)**. Một phép mã hóa cần:

- **K:** khóa AES.
- **N:** nonce/IV. Giá trị này không cần bí mật nhưng phải được sử dụng đúng quy tắc; 96 bit (12 byte) là kích thước thông dụng.
- **P:** plaintext; có thể kèm **AAD** không mã hóa nhưng được xác thực.
- **T:** thẻ xác thực (authentication tag), thường dài 128 bit.

Tài liệu **NIST SP 800-38D** đặt giới hạn độ dài plaintext **cho một lần mã hóa GCM** là tối đa `2^39 - 256` bit, tương đương khoảng **64 GiB trừ 32 byte**. Đây **không phải** là quyền được dùng vô hạn số lần mã hóa 64 GiB dưới cùng một key; giới hạn tổng số phép toán và nonce là bài toán riêng.

### 3.1. Tái sử dụng key + nonce nguy hiểm như thế nào?

Trong GCM, nếu hai bản rõ khác nhau được mã hóa với **cùng key và cùng nonce**, chúng có thể làm lộ quan hệ giữa bản rõ và tạo điều kiện tấn công tính xác thực. Với hệ thống thực tế, đây là lỗi thiết kế nghiêm trọng, không được xem như một sự cố vô hại chỉ vì khóa vẫn dài 256 bit.

~~~mermaid
flowchart TD
    A["Key K đang hoạt động"] --> Q{"Còn ngân sách sử dụng key?"}
    Q -->|Không| STOP["Ngừng mã hóa và chuyển key"]
    Q -->|Có| N["Cấp nonce theo chiến lược được phê duyệt"]
    N --> E["AES-GCM encrypt: plaintext + AAD"]
    E --> C["Ciphertext + tag + nonce + key ID"]
    C --> R["Lưu/Truyền bản mã"]
~~~

Sơ đồ diễn đạt quy tắc kiểm soát: **mỗi phép mã hóa mới dùng một nonce chưa từng dùng dưới cùng key**, kể cả khi chạy ở node khác hoặc sau khi dịch vụ khởi động lại. Không cần giữ nonce bí mật, nhưng thường cần lưu nó cùng bản mã để giải mã được dữ liệu.

**Nonce ngẫu nhiên 96 bit** có không gian rất lớn nhưng vẫn có rủi ro va chạm theo hiệu ứng sinh nhật. Khi các nonce được chọn ngẫu nhiên, xác suất xuất hiện ít nhất một cặp trùng sau `q` lần mã hóa xấp xỉ:

\[
P_{collision} \approx \frac{q(q-1)}{2^{97}}
\]

Công thức trên giả định nonce độc lập và phân phối đều trên 96 bit, đồng thời xác suất va chạm còn đủ nhỏ để dùng phép xấp xỉ. Ví dụ:

| Số lần mã hóa dưới cùng key | Xác suất va chạm nonce ngẫu nhiên 96 bit, xấp xỉ |
| ---: | ---: |
| 1.000.000 | 6,3 × 10⁻¹⁸ |
| 100.000.000 | 6,3 × 10⁻¹⁴ |
| 1.000.000.000 | 6,3 × 10⁻¹² |
| 2³² | 1,16 × 10⁻¹⁰ |

Những xác suất này **chỉ phản ánh va chạm nonce do chọn ngẫu nhiên**; chúng không thể thay thế toàn bộ phân tích an toàn của GCM, vốn còn phụ thuộc độ dài thông điệp, tag, số khối được xử lý và xác suất giả mạo. Theo quy tắc trong NIST SP 800-38D, với cách xây dựng IV không chỉ sử dụng dạng xác định 96 bit, **tổng số lần gọi hàm mã hóa có xác thực dưới một key không được vượt 2³²**. Trong thực tế nên đặt giới hạn thấp hơn nhiều tùy ngân sách rủi ro và khối lượng dữ liệu.

### 3.2. Nonce theo bộ đếm có giải quyết tất cả không?

Một cách khác là dùng **nonce duy nhất có tính xác định**, chẳng hạn kết hợp trường định danh miền/thiết bị được cấp phát riêng với một bộ đếm tăng đơn điệu, theo đúng đặc tả GCM. Cách này giúp tránh va chạm ngẫu nhiên nếu bảo đảm:

1. **Mỗi node/worker có miền nonce riêng**, không trùng khi cùng dùng một key.
2. **Bộ đếm được lưu bền vững hoặc cấp phát an toàn**, không quay lại giá trị cũ sau restart, restore snapshot hoặc failover.
3. **Không tràn hoặc quay vòng bộ đếm** trong vòng đời khóa.
4. **Số phép toán và lượng dữ liệu vẫn được giới hạn**, kể cả khi chưa bao giờ trùng nonce.

Không được suy luận rằng bộ đếm giúp một key AES-GCM có thể dùng mãi. Phải tuân thủ giới hạn mode, chính sách bảo mật và thiết kế vòng đời khóa.

### 3.3. AAD và tag không thay thế chính sách giới hạn

AAD có thể gắn bản mã với tenant ID, object ID, schema version; tag xác thực ciphertext và AAD. Tuy nhiên:

- AAD **không được mã hóa**.
- Tag hợp lệ không chứng minh người gọi **có quyền** đọc dữ liệu hoặc không phát lại bản mã cũ.
- **Tag ngắn hơn** làm giảm ngân sách an toàn trước hành vi giả mạo; giới hạn sử dụng có thể khắt khe hơn.
- Kẻ tấn công có quyền decrypt/unwrap có thể gây thiệt hại dù AES-GCM và tag không bị phá.

Giữ tag chuẩn có độ dài phù hợp, kiểm tra quyền riêng biệt và từ chối bản mã bị sửa đổi trước khi cung cấp plaintext cho nghiệp vụ.

## 4. Các chế độ đối xứng khác có giới hạn khác nhau

| Chế độ/cơ chế | Mối quan tâm về giới hạn | Điều phải làm |
| --- | --- | --- |
| **AES-GCM** | Nonce duy nhất theo key; tổng lần dùng/khối; giới hạn bản rõ mỗi invocation; độ dài tag. | Quản lý nonce, quota và phiên bản key; dừng mã hóa khi vượt ngưỡng. |
| **AES-CTR** | Không được tái dùng luồng key + nonce/counter; bộ đếm có thể tràn. | Phân bổ miền counter/nonce, tránh reuse và có cơ chế xác thực riêng. |
| **AES-CBC** | Kích thước khối 128 bit, yêu cầu IV đúng cách; không tự xác thực bản mã. | Dùng giao thức an toàn có xác thực; hạn chế các thiết kế mới chỉ dùng CBC. |
| **AES-XTS** | Ràng buộc theo data unit/sector và các giới hạn chuẩn của chế độ. | Theo dõi cách đặt tweak, kích thước đơn vị dữ liệu và phương án thay khóa; không dùng XTS thay AEAD cho thông điệp. |
| **AES-KW/KWP** | Bọc key material có quy tắc định dạng/kích thước riêng; KEK có nhiều khóa phụ thuộc. | Kiểm soát usage của KEK, quyền wrap/unwrap và rủi ro khi một KEK phục vụ quá nhiều DEK. |
| **ChaCha20-Poly1305** | Nonce duy nhất theo key và giới hạn bộ đếm/độ dài thông điệp theo biến thể. | Áp dụng tài liệu chuẩn của biến thể đang dùng; không sao chép máy móc quota của AES-GCM. |

**Mọi con số trong tài liệu chuẩn đều gắn với một thuật toán/chế độ cụ thể.** Không lấy giới hạn độ dài cho một lần GCM rồi dùng làm giới hạn cho CBC, CTR hoặc XTS; cũng không lấy số byte đã mã hóa để thay thế yêu cầu duy nhất nonce.

## 5. Ba mức quota cần có trong hệ thống

Giả sử dịch vụ mã hóa bản ghi dưới một DEK AES-GCM. Có thể áp dụng ba giới hạn bổ trợ:

### 5.1. Giới hạn theo một bản ghi

Giới hạn độ dài plaintext và AAD để tránh vượt quy tắc mode hoặc quota bộ nhớ/CPU. Với tệp lớn, có thể **chia thành chunk** và mã hóa từng chunk theo giao thức có xác thực riêng.

Mỗi chunk phải có nonce hợp lệ và AAD gắn **file ID, chunk index, tổng số chunk hoặc thông tin cấu trúc cần xác thực**. Cần thiết kế phát hiện chunk bị thiếu, đảo thứ tự hoặc thay thế; chỉ xác thực tag của từng chunk mà không xác thực cấu trúc tổng thể có thể chưa đủ.

### 5.2. Giới hạn tích lũy theo một key

Theo dõi ít nhất:

- Số lượt **encrypt** được thực hiện với phiên bản key.
- Tổng **plaintext bytes** hoặc tổng số khối đã xử lý, đúng với mô hình bảo mật.
- Thời điểm tạo/key activation và hạn dùng.
- Quy tắc sinh nonce, số phiên/node đang chia sẻ key và ngưỡng cảnh báo.

Các giá trị do đội an toàn đặt phải dựa trên thuật toán, tài liệu tiêu chuẩn, đặc điểm lưu lượng và mục tiêu rủi ro. Ví dụ chính sách nội bộ có thể đặt **tối đa 1 triệu lần mã hóa, 8 GiB plaintext hoặc 30 ngày**, lấy điều kiện chạm ngưỡng nào trước. **Các số này chỉ minh họa một chính sách thận trọng, không phải giới hạn tiêu chuẩn bắt buộc của AES-GCM.**

### 5.3. Giới hạn phạm vi chia sẻ key

Hạn chế một DEK trên một tập bản ghi, phiên/đơn vị dữ liệu hoặc tenant thích hợp. Dùng **KEK** trong KMS để bảo vệ nhiều DEK qua **envelope encryption**; qua đó mỗi DEK có ngân sách sử dụng độc lập.

Nếu một tenant có DEK riêng, việc xoay hoặc hủy DEK đó ít ảnh hưởng tenant khác hơn so với dùng một DEK chung toàn hệ thống. Tuy nhiên, nếu một **KEK chung** bọc mọi DEK, KEK vẫn là một thành phần tập trung cần phân quyền và kiểm toán chặt.

## 6. Ví dụ tính toán ngân sách sử dụng key

Xét dịch vụ mã hóa mỗi bản ghi 4 KiB, trung bình 20.000 bản ghi/ngày, dùng một DEK AES-GCM và nonce ngẫu nhiên 96 bit. Với mức sử dụng ổn định trong 30 ngày:

| Chỉ số | Cách tính | Kết quả |
| --- | --- | ---: |
| Tổng lần mã hóa | 20.000 × 30 | 600.000 |
| Tổng dữ liệu | 600.000 × 4 KiB | 2.343,75 MiB (~2,29 GiB) |
| Mức so với quota minh họa 1 triệu lần | 600.000 / 1.000.000 | 60% |
| Mức so với quota minh họa 8 GiB | 2,29 / 8 | ~28,6% |

Trong trường hợp này, số lượt mã hóa tiến sát quota nhanh hơn dung lượng. Nhưng nếu một đợt nhập dữ liệu tạo những bản ghi rất lớn, **quota byte** có thể chạm trước số lượt mã hóa. Vì vậy cả hai chỉ số đều có ý nghĩa.

**Số liệu trên chưa bao gồm lượt mã hóa khi retry, tác vụ batch, hệ thống dự phòng, worker khác hoặc bản dữ liệu tạm.** Để tính chính xác ngân sách của key, phải gộp **mọi lần mã hóa thực tế cùng key**, kể cả những lần mà kết quả không được ghi thành công nhưng phép toán đã thực hiện.

## 7. Ví dụ Java 17+: chặn mã hóa khi vượt quota key

Đoạn code dưới đây minh họa cách tổ chức **giới hạn số lần encrypt và tổng byte plaintext**. Ví dụ dùng JCA với AES-GCM, nonce ngẫu nhiên 96 bit và các biến đếm thread-safe trong **một tiến trình**.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.concurrent.atomic.AtomicLong;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class PerKeyBudgetDemo {
    static final long MAX_ENCRYPTIONS = 1_000_000L;  // Chính sách ví dụ
    static final long MAX_PLAINTEXT_BYTES = 8L * 1024 * 1024 * 1024;
    static final int MAX_RECORD_BYTES = 4 * 1024 * 1024;

    static final class GuardedKey {
        private final String keyId;
        private final SecretKey key;
        private final AtomicLong encryptions = new AtomicLong();
        private final AtomicLong usedBytes = new AtomicLong();
        private final SecureRandom random = new SecureRandom();

        GuardedKey(String keyId, SecretKey key) {
            this.keyId = keyId;
            this.key = key;
        }

        // Chỉ là quota cục bộ một JVM; khi có nhiều node,
        // cần ngân sách dùng chung, bền vững và đồng bộ.
        Result encrypt(byte[] plaintext, byte[] aad) throws Exception {
            if (plaintext.length > MAX_RECORD_BYTES) {
                throw new IllegalArgumentException("Record too large");
            }

            // Đặt trước ngân sách; nếu lỗi sau bước này thì vẫn tính quota,
            // để tránh thao tác lặp đi lặp lại mà không bị ghi nhận.
            long n = encryptions.incrementAndGet();
            long total = usedBytes.addAndGet(plaintext.length);
            if (n > MAX_ENCRYPTIONS || total > MAX_PLAINTEXT_BYTES) {
                throw new IllegalStateException("Rotate the key first");
            }

            byte[] nonce = new byte[12];
            random.nextBytes(nonce);

            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key,
                    new GCMParameterSpec(128, nonce));
            cipher.updateAAD(aad);
            byte[] ciphertextAndTag = cipher.doFinal(plaintext);

            return new Result(keyId, nonce, ciphertextAndTag);
        }
    }

    record Result(String keyId, byte[] nonce, byte[] ciphertextAndTag) {}

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey dek = generator.generateKey();

        GuardedKey guarded = new GuardedKey("orders-dek-v1", dek);
        byte[] aad = "tenant=A;record=123".getBytes(StandardCharsets.UTF_8);
        Result result = guarded.encrypt(
                "Du lieu can bao ve".getBytes(StandardCharsets.UTF_8), aad);

        System.out.println("Key ID: " + result.keyId());
        System.out.println("Ciphertext length: " +
                result.ciphertextAndTag().length);
    }
}
~~~

**Giới hạn của ví dụ:** Đây là mã **minh họa ý tưởng quota**, không phải bộ cấp nonce phân tán hoặc cơ chế bảo đảm ngân sách an toàn ở sản xuất. Một node khác có thể dùng cùng DEK mà không chia sẻ `AtomicLong`; counters mất khi restart; còn nonce ngẫu nhiên chỉ mang tính xác suất duy nhất. Dưới tải phân tán, nên dùng **dịch vụ quản lý key usage bền vững**, phân phối khóa/miền nonce được kiểm soát, kiểm tra quyền và cơ chế khóa/phiên bản phù hợp.

Mã cố tình **trừ ngân sách trước khi mã hóa** để tránh vượt ngưỡng do hai luồng cùng chạy. Việc cộng số lần và số byte trong hai biến riêng có thể tạo tình huống quota **bảo thủ hơn cần thiết** nếu một phép bị chặn sau khi đặt chỗ; không dùng cấu trúc hai bộ đếm này làm bằng chứng giao dịch chính xác. Trong hệ thống sản xuất, cần giải quyết atomic reservation, idempotency, retry, lỗi giao dịch và ghi nhận mọi thao tác đã thực hiện.

Thực tế nên tránh xuất DEK thô vào ứng dụng nếu có thể dùng **KMS/HSM hoặc dịch vụ mã hóa** phù hợp. Cần lưu key ID/phiên bản, nonce, tag và metadata đã xác thực cùng bản mã; không ghi nội dung khóa vào log.

## 8. Vòng đời khi một key chạm giới hạn

~~~mermaid
flowchart TD
    A["DEK v1 đang ACTIVE"] --> B["Theo dõi encrypt count, byte count, age, nonce budget"]
    B --> C{"Chạm ngưỡng cảnh báo?"}
    C -->|Chưa| A
    C -->|Có| D["Chuẩn bị và cấp phát DEK v2"]
    D --> E["Cập nhật phiên bản cho thao tác ghi mới"]
    E --> F{"DEK v1 còn nhận encrypt mới?"}
    F -->|Có| G["Ngừng encrypt mới bằng v1"]
    F -->|Không| H["Giữ v1 cho decrypt hợp lệ nếu còn dữ liệu cần đọc"]
    G --> H
    H --> I["Re-encrypt/di chuyển dữ liệu cũ khi cần"]
    I --> J["Kiểm tra backup, retention và khả năng khôi phục"]
    J --> K["Thu hồi/hủy v1 theo chính sách khi đủ điều kiện"]
~~~

Một kế hoạch vận hành hợp lý bao gồm:

1. **Tạo và cấp phát:** tạo DEK bằng CSPRNG/KMS, gắn key ID, phiên bản, thuật toán, mode, usage và chủ sở hữu.
2. **Thiết lập policy:** khai báo giới hạn cho **mỗi message, mỗi key, thời gian và phạm vi tenant**, cùng mức cảnh báo (ví dụ 70%, 90%, 100%). Đây là ngưỡng vận hành ví dụ, cần hiệu chỉnh.
3. **Đo lường:** đếm số lần mã hóa và byte ở điểm kiểm soát tập trung hoặc cơ chế dùng chung giữa các node; theo dõi nonce strategy, restart, retry và replica.
4. **Chuyển key trước hạn:** tạo DEK mới, đưa vào KMS/envelope encryption; cập nhật nơi ghi mới và quy tắc key version.
5. **Ngừng encrypt bằng key cũ:** chặn các lệnh mã hóa mới với phiên bản chạm ngưỡng. Việc **giải mã dữ liệu lịch sử** có thể còn được cho phép, miễn key chưa bị thu hồi/hủy và caller có quyền.
6. **Di chuyển dữ liệu nếu cần:** thay DEK và mã hóa lại bản mã cũ khi chính sách hoặc sự cố yêu cầu. Chỉ **rewrap DEK dưới KEK mới** không làm giảm dữ liệu đã mã hóa bằng DEK cũ.
7. **Thu hồi và hủy:** sau khi kiểm kê tất cả ciphertext, backup, replica và điều kiện lưu giữ, mới tiến hành hủy key material theo chính sách. Tránh hủy DEK quá sớm gây mất dữ liệu vĩnh viễn.

Chạm giới hạn toán học hoặc nonce phải được xử lý theo hướng **fail closed**: không cho encrypt mới với key đã vượt ngưỡng. Nếu một khóa bị **lộ**, chỉ rotate cho dữ liệu mới có thể chưa đủ: cần đánh giá bản mã lịch sử, quyền decrypt, khả năng tái mã hóa và xử lý sự cố.

## 9. Tổ chức quota trong KMS/HSM và envelope encryption

Một hệ thống quản lý khóa thường phân tầng:

~~~text
KMS / HSM: KEK-2026
    |
    +-- wrapped DEK-TenantA-v1 -> AES-GCM records A (quota riêng)
    |                |
    |                +-- DEK-TenantA-v2 -> bản mã A mới
    |
    +-- wrapped DEK-TenantB-v1 -> AES-GCM records B (quota riêng)
    |
    +-- wrapped DEK-TenantC-v1 -> AES-GCM records C (quota riêng)
~~~

**DEK** có nhiệm vụ mã hóa/giải mã dữ liệu, vì vậy ngân sách nonce/số lượt AES-GCM áp dụng trực tiếp cho **từng DEK**. **KEK** có nhiệm vụ wrap/unwrap DEK; nó cũng có giới hạn, usage và chính sách riêng của thuật toán bọc khóa hoặc KMS, nhưng không thể đơn giản cộng số byte ciphertext của DEK rồi suy ra giới hạn toán học của KEK.

Chủ sở hữu khóa nên định nghĩa các policy:

| Đối tượng | Chỉ số nên theo dõi | Hành động khi chạm ngưỡng |
| --- | --- | --- |
| **DEK AES-GCM** | Encrypt count, tổng byte/khối, tuổi, nonce uniqueness, key version | Không encrypt mới; cấp DEK mới; đánh giá re-encrypt. |
| **KEK** | Số lần wrap/unwrap theo chính sách, tenant/workload được phép, tuổi, bản sao, số DEK phụ thuộc | Rotate/rewrap khi cần; kiểm tra phạm vi trước revoke/destroy. |
| **KMS/HSM API** | Lượt gọi, lỗi, độ trễ, throttling, quyền sử dụng, nhật ký nhạy cảm | Rate limit, cảnh báo, xử lý lỗi; không xem quota API như giới hạn mật mã của DEK. |
| **Dữ liệu/tenant** | Số bản mã, phiên bản DEK, trạng thái backup, retention | Lập kế hoạch di chuyển và xóa theo ranh giới dữ liệu. |

**Quota dịch vụ KMS** (số request mỗi giây) khác **quota mật mã của key** (số lần/byte dùng key). Nếu KMS chỉ thực hiện thao tác unwrap và ứng dụng AES-GCM cục bộ, KMS có thể không thấy số lượt encrypt thực tế. Cần bổ sung đo lường ở phía ứng dụng hoặc dịch vụ mã hóa.

**HSM/KMS non-exportable** giúp hạn chế lộ key material nhưng không thay thế least privilege. Một danh tính có quyền gọi unwrap hoặc decrypt quá rộng vẫn có thể đọc dữ liệu mà không cần xuất KEK.

## 10. Giám sát và kiểm toán giới hạn dữ liệu

Hồ sơ quản lý một key nên có:

- **Định danh:** key ID, phiên bản, thuật toán/mode, key usage, owner, môi trường, tenant và thời điểm kích hoạt.
- **Ngưỡng:** max invocations, max plaintext bytes/blocks, giới hạn mỗi message, tuổi, nonce strategy, mức cảnh báo và chính sách khi hết quota.
- **Thực tế sử dụng:** encrypt/decrypt count tách biệt, byte đã mã hóa, số lỗi quota, luồng retry, các node dùng key, thời điểm dùng cuối.
- **Bằng chứng chuyển đổi:** key version mới, thời điểm cắt lưu lượng ghi, số ciphertext đã di chuyển, kết quả thử khôi phục, tình trạng backup.
- **Dấu vết kiểm toán:** ai/phần mềm nào tạo, cấp phát, truy cập, rotate, vô hiệu hóa hoặc hủy key; phê duyệt, kết quả và lý do nghiệp vụ.

Không ghi **DEK/KEK dạng rõ, private key hay nội dung plaintext** vào audit log. Theo dõi số lượng phép mã hóa theo key ID giúp cảnh báo sớm khi một ứng dụng đột ngột phát sinh nhiều lượt sử dụng bất thường hoặc một key được dùng từ nhiều môi trường ngoài dự kiến.

### Cảnh báo vận hành cần có

- Mức sử dụng key đạt **ngưỡng cảnh báo** hoặc ngày hết hạn sắp đến.
- Xuất hiện **nonce/counter trùng lặp** hoặc sự cố đồng bộ nonce.
- Worker mới được cấu hình sử dụng **key version cũ** hoặc phát sinh encrypt sau thời điểm chặn.
- Nhiều lỗi **unwrap/decrypt** hoặc quyền sử dụng key thay đổi bất thường.
- Quá trình chuyển key bị kẹt do backup, dữ liệu lịch sử hoặc chưa đủ quyền rewrap.

## 11. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng AES-256 cho phép mã hóa vô hạn | Dùng sai mode/nonce hoặc vượt ngân sách an toàn. | Áp dụng giới hạn theo thuật toán và chính sách per-key. |
| Đếm byte nhưng không đếm số lần encrypt | Không kiểm soát được số nonce đã sử dụng. | Theo dõi cả count và byte/blocks. |
| Đếm số lần ở từng node nhưng dùng chung key | Tổng sử dụng thực tế lớn hơn mọi dashboard đơn lẻ. | Ngân sách tổng hợp qua tất cả node và phiên bản key. |
| Reset nonce counter sau restart | Có thể tái sử dụng key + nonce, phá vỡ GCM. | Lưu bền vững counter/miền nonce hoặc thiết kế phân phối an toàn. |
| Dùng nonce ngẫu nhiên mà không giới hạn số lần mã hóa | Xác suất va chạm ngày càng tăng. | Đặt quota theo mô hình rủi ro và xoay DEK trước hạn. |
| Chỉ rotate theo ngày cố định | Lưu lượng tăng có thể chạm ngưỡng trước lịch. | Kết hợp quota, tuổi và cảnh báo. |
| Coi thay KEK là đã thay DEK | Dữ liệu cũ vẫn mã hóa dưới DEK cũ. | Phân biệt rewrap với re-encrypt. |
| Dùng lại DEK cho mọi tenant | Lộ/hủy một key ảnh hưởng nhiều bên. | Phân đoạn DEK theo tenant, tập dữ liệu hoặc mục tiêu hủy. |
| Hủy key ngay khi đạt ngưỡng encrypt | Dữ liệu lịch sử mất khả năng giải mã. | Chặn encrypt mới nhưng duy trì decrypt hợp lệ đến khi di chuyển/retention xong. |
| Coi KMS API rate limit là per-key crypto limit | Không quan sát được encrypt thực tế ở ứng dụng. | Theo dõi hoạt động mật mã tại điểm thực thi. |
| Tự rút ngắn GCM tag mà giữ nguyên ngân sách | Biên an toàn xác thực giảm. | Đánh giá lại theo chuẩn; ưu tiên tag đầy đủ khi có thể. |

## 12. Câu hỏi tự kiểm tra

1. Vì sao không thể áp dụng một giới hạn “10 TB/key” cho mọi chế độ AES?
2. Giới hạn **mỗi lần mã hóa** khác gì với giới hạn **tích lũy của một key**?
3. Nếu hai worker cùng dùng DEK AES-GCM, vì sao mỗi worker tự đếm nonce không nhất thiết đủ an toàn?
4. Một hệ thống xử lý tệp lớn nên giới hạn/chia chunk như thế nào để không làm mất kiểm tra tính toàn vẹn?
5. Nếu một DEK chạm quota encrypt, có phải hủy ngay DEK đó hay không?
6. Sự khác biệt giữa rotate KEK và rotate DEK ảnh hưởng thế nào đến ngân sách AES-GCM?
7. Vì sao API rate limit của KMS không chứng minh số lần ứng dụng đã mã hóa dưới một DEK?
8. Khi tăng kích thước tag hoặc đổi cách sinh nonce, chính sách hạn mức có cần đánh giá lại không?

**Ghi nhớ:** Giới hạn dữ liệu theo key là một phần của **thiết kế an toàn mật mã và vận hành vòng đời khóa**, không phải chỉ là tham số dung lượng. Muốn dùng AES-GCM an toàn cần bảo đảm **key + nonce không lặp**, kiểm soát **số lần mã hóa và tổng dữ liệu**, phân tách DEK/KEK, quan sát việc sử dụng ở mọi node và xoay khóa có kiểm chứng. KMS/HSM, quyền truy cập và kiểm toán giúp thực thi chính sách đó trên toàn hệ thống.
