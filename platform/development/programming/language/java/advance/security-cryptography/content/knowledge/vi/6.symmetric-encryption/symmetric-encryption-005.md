# 6.5. Phân biệt ECB, CBC, CTR và yêu cầu bảo vệ tính toàn vẹn của bản mã

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc đúng tên transformation trong Java như `AES/ECB/NoPadding`, `AES/CBC/PKCS5Padding` và `AES/CTR/NoPadding`; hiểu **AES** là thuật toán mã khối còn **ECB, CBC, CTR** là các *mode of operation*.
2. Giải thích cách ba mode biến plaintext thành ciphertext; phân biệt yêu cầu về **IV, nonce, counter**, padding và độ dài dữ liệu.
3. Nhận diện các vấn đề của **ECB lộ mẫu**, **CBC với IV/padding oracle**, **CTR khi tái sử dụng keystream**, và vì sao cả ba mode tự thân **không xác thực tính toàn vẹn** của ciphertext.
4. Thử nghiệm Java 17+ cho thấy việc sửa ciphertext/IV có thể làm plaintext thay đổi mà giải mã không phát hiện; triển khai đúng nguyên tắc **Encrypt-then-MAC** nếu buộc phải dùng CBC/CTR cũ, và ưu tiên **AEAD** như AES-GCM trong thiết kế mới.
5. Biết lưu/truyền IV và tag, xử lý lỗi xác thực, thiết kế uniqueness của nonce và tránh đánh đồng tính bí mật, toàn vẹn, xác thực và chống replay.

**Phạm vi:** bài tập trung vào mã hóa đối xứng với AES trong Java. Các ví dụ CBC/CTR *chưa có xác thực* chỉ dùng để quan sát vấn đề; không sử dụng chúng làm mẫu bảo mật hoàn chỉnh cho production.

## 1. AES là mã khối; ECB, CBC, CTR quyết định cách dùng mã khối

**AES (Advanced Encryption Standard)** là thuật toán mã hóa đối xứng hoạt động trên **khối 128 bit = 16 byte**, với khóa 128, 192 hoặc 256 bit. **Kích thước khối vẫn là 16 byte kể cả khi dùng khóa AES-256**. AES tự nó cho phép mã hóa hoặc giải mã *một khối*; để xử lý thông điệp dài, cần mode of operation, cách xử lý IV/counter và đôi khi padding.

Trong Java Cryptography Architecture/Extension, `javax.crypto.Cipher` có dạng tên:

```text
<algorithm>/<mode>/<padding>

AES/ECB/NoPadding
AES/CBC/PKCS5Padding
AES/CTR/NoPadding
AES/GCM/NoPadding
```

Trong bảng trên, `NoPadding` là chỉ dẫn không thêm padding, **không có nghĩa thông điệp không cần kiểm tra tính hợp lệ**; và `PKCS5Padding` trong cách đặt tên JCE cho AES hoạt động theo quy tắc padding tương thích PKCS#7 trên khối 16 byte.

Không viết `Cipher.getInstance("AES")` trong ứng dụng bảo mật: chế độ/padding mặc định phụ thuộc provider, có thể dẫn đến ECB ngoài ý muốn. Hãy chỉ định transformation **đầy đủ** và theo thiết kế giao thức.

### 1.1. Bốn tính chất thường bị nhầm lẫn

| Tính chất | Câu hỏi thực tế | Mã hóa ECB/CBC/CTR tự cung cấp? |
| --- | --- | --- |
| **Confidentiality – tính bí mật** | Người không có khóa có đọc được plaintext không? | Có thể cung cấp ở mức độ khác nhau **chỉ khi mode/IV/counter dùng đúng**; ECB thường không phù hợp dữ liệu có cấu trúc |
| **Integrity – tính toàn vẹn** | Dữ liệu có bị sửa kể từ lúc gửi/lưu không? | **Không**; plaintext có thể thay đổi khi ciphertext/IV bị sửa |
| **Authentication – xác thực nguồn gốc** | Dữ liệu có do bên sở hữu khóa xác thực tạo ra không? | **Không**; encryption không thay cho MAC/chữ ký |
| **Replay protection – chống phát lại** | Một bản tin cũ hợp lệ bị gửi lại có bị từ chối không? | **Không**, kể cả với MAC hoặc AEAD nếu không có sequence number/nonce/cơ chế state |

Đây là nguyên tắc của toàn bài: **“decrypt được” không có nghĩa “ciphertext chưa bị sửa”**. Một ứng dụng kiểm tra padding thành công vẫn có thể nhận plaintext do đối thủ tác động.

## 2. ECB – Electronic Codebook: các khối độc lập và lộ mẫu lặp

Với plaintext được chia thành các khối `P1, P2, ...` đủ 16 byte và khóa `K`, ECB áp dụng AES cho **từng khối độc lập**:

```text
P1 ── AES-Encrypt(K) ──> C1
P2 ── AES-Encrypt(K) ──> C2
P3 ── AES-Encrypt(K) ──> C3

C_i = E_K(P_i)
```

Nếu `P1 = P2`, thì **chắc chắn `C1 = C2` dưới cùng khóa**. Kẻ quan sát có thể không giải mã được nội dung nhưng thấy rõ khối nào lặp, từ đó suy luận cấu trúc, định dạng và mẫu dữ liệu. Với hình ảnh, bản ghi có trường lặp hoặc dữ liệu có tính khuôn mẫu, đây là rò rỉ đáng kể.

- **IV:** ECB không dùng IV; không có cơ chế phá mẫu khối bằng nonce.
- **Padding:** `AES/ECB/NoPadding` chỉ nhận đầu vào có độ dài bội số 16; `AES/ECB/PKCS5Padding` thêm padding cho message không đủ khối.
- **Tính toàn vẹn:** không có. Kẻ tấn công còn có thể hoán đổi hoặc thay thế các khối ciphertext mà không cần khóa; giải mã có thể ra các khối plaintext được sao chép/di chuyển.
- **Phù hợp:** hiếm khi dùng trực tiếp cho message thực tế. ECB có thể là primitive bên trong cấu trúc khác đã được chứng minh, nhưng không chọn ECB để “mã hóa file/JSON/database record”.

Ví dụ cùng một khối 16 byte ký tự `A` lặp hai lần: hai khối ciphertext ECB đầu tiên giống nhau hoàn toàn. Đây là biểu hiện của **deterministic per-block mapping**, không phụ thuộc vào việc khóa AES có dài 128 hay 256 bit.

**Không sửa ECB chỉ bằng cách đổi padding:** thêm PKCS5 padding không loại bỏ mẫu lặp ở các khối plaintext đầy đủ đã trùng nhau.

## 3. CBC – Cipher Block Chaining: liên kết khối và IV

CBC sử dụng ciphertext khối trước để tác động đến mã hóa khối hiện tại. Gọi `IV` là giá trị khởi đầu 16 byte, `P_i` là plaintext khối thứ `i`, `C_i` là ciphertext khối thứ `i`:

```text
C_0 = IV

P1 ─ XOR(IV) ─ AES-Encrypt(K) ─> C1
P2 ─ XOR(C1) ─ AES-Encrypt(K) ─> C2
P3 ─ XOR(C2) ─ AES-Encrypt(K) ─> C3

C_i = E_K(P_i XOR C_(i-1))
P_i = D_K(C_i) XOR C_(i-1)
```

Đây là mode có tính *chaining*: khối trước tác động lên khối sau. Với IV tạo ngẫu nhiên và khó dự đoán đúng cách, hai thông điệp giống nhau khi mã hóa ở hai lần khác nhau thường tạo ciphertext khác nhau, ngay từ khối đầu.

### 3.1. IV của CBC phải như thế nào?

- IV CBC/AES có **16 byte** tương ứng kích thước block AES, khác với GCM thường dùng nonce 12 byte.
- Đối với CBC encryption an toàn, IV cần **khó dự đoán khi plaintext được chọn**; trong thực tế tạo IV mới bằng `SecureRandom.nextBytes(new byte[16])` cho mỗi message là lựa chọn thông dụng.
- IV **không cần giữ bí mật**, có thể đặt trước ciphertext; nhưng phải được **ràng buộc toàn vẹn** với thông điệp trong sơ đồ có MAC/AEAD.
- **Không** dùng IV cố định là 16 byte zero, IV lấy từ timestamp/`Random` hoặc luôn dùng lại IV cho mọi message cùng khóa.
- Không nhầm “lưu IV cạnh ciphertext” với “IV được xác thực”: nếu đối thủ sửa IV mà không có MAC, plaintext block đầu có thể bị tác động trực tiếp.

### 3.2. CBC thường cần padding

`AES/CBC/PKCS5Padding` trong Java tự thêm padding; kể cả plaintext có độ dài đúng bội số 16, nó vẫn thêm **một khối padding đầy đủ**, nên ciphertext CBC có thể dài hơn plaintext. Với `NoPadding`, ứng dụng phải cung cấp dữ liệu bội số 16 và không tự chế padding mơ hồ.

Với `AES/CBC/PKCS5Padding`, phép giải mã có thể trả lỗi `BadPaddingException` nếu padding không hợp lệ. **Lỗi padding không phải là cơ chế xác thực.** Kẻ tấn công có thể thay đổi ciphertext và quan sát hành vi ứng dụng để suy luận plaintext nếu hệ thống phân biệt lỗi padding hợp lệ/không hợp lệ hoặc thời gian xử lý.

### 3.3. CBC có thể bị sửa có chủ đích

Công thức giải mã khối đầu:

```text
P1 = D_K(C1) XOR IV
```

Nếu đối thủ sửa bit ở **IV**, bit tương ứng của `P1` sẽ bị lật mà không cần biết khóa. Tương tự, sửa `C_i` có thể làm hỏng khối `P_i` và lật một số bit có chủ đích trong `P_(i+1)`. Điều này gọi là **malleability**.

Ví dụ cấu trúc dữ liệu chứa cờ quyền hạn hoặc số tiền sẽ đặc biệt nguy hiểm nếu backend giải mã CBC rồi tin vào plaintext mà không xác thực trước. Việc chỉnh bit không phải lúc nào cũng cho ra plaintext hợp lệ, nhưng **không được coi giải mã thành công là bằng chứng dữ liệu nguyên vẹn**.

### 3.4. Padding oracle: tại sao phải xác thực trước giải mã?

Giả sử API nhận `IV || ciphertext`, gọi `Cipher.doFinal` rồi trả:

- `400 Padding error` khi `BadPaddingException`;
- `401 Invalid message` khi plaintext giải mã thành công nhưng dữ liệu ứng dụng không hợp lệ.

Sự khác biệt có thể tạo **oracle**: đối thủ thử sửa ciphertext, quan sát kết quả để học thông tin về plaintext mà không biết khóa. Ngay cả khi dùng một thông báo lỗi chung, sự khác biệt timing có thể là tín hiệu.

Nếu buộc phải dùng CBC, cần một thiết kế có xác thực được kiểm chứng, ví dụ **Encrypt-then-MAC** với khóa độc lập; bên nhận **kiểm MAC trước khi giải mã CBC**. Cũng phải kiểm chính sách về IV, format, padding, key rotation và thông báo lỗi đồng nhất. Trong thiết kế mới, AEAD chuẩn như AES-GCM thường đơn giản và an toàn hơn để sử dụng đúng.

## 4. CTR – Counter: biến AES thành luồng khóa (keystream)

CTR không mã hóa trực tiếp plaintext block bằng AES. Nó mã hóa một **counter block** riêng, rồi XOR kết quả với plaintext. Các counter block phải **không trùng dưới cùng khóa**.

```text
T1 = nonce || counter1  ─ AES-Encrypt(K) ─> S1
T2 = nonce || counter2  ─ AES-Encrypt(K) ─> S2
T3 = nonce || counter3  ─ AES-Encrypt(K) ─> S3

C1 = P1 XOR S1
C2 = P2 XOR S2
C3 = P3 XOR S3

P_i = C_i XOR S_i
```

`T_i` là giá trị counter block đầu vào AES; `S_i` là keystream. Ký hiệu `nonce || counter` chỉ là **một cách bố trí counter block theo giao thức**: số bit nonce/counter, cách tăng counter và endian phải được thống nhất chính xác. Trong Java với AES, counter block khởi tạo được truyền qua `IvParameterSpec` dài 16 byte. Các provider có thể có cách quản lý counter khác nhau, vì thế hệ thống liên thông phải xác định format cụ thể.

### 4.1. Đặc tính hữu ích của CTR

- Không cần padding: `AES/CTR/NoPadding` mã hóa cả plaintext không đủ 16 byte; ciphertext có **cùng số byte** với plaintext.
- Các khối keystream có thể được tính độc lập khi biết các counter block, thuận lợi cho song song hóa và truy cập theo vị trí.
- Mã hóa/giải mã cùng nguyên lý XOR; `Cipher` phân biệt `ENCRYPT_MODE`/`DECRYPT_MODE` nhưng đều dùng keystream tương ứng.
- Không có chaining kiểu CBC, nên lỗi một byte ciphertext có thể chỉ làm sai byte tương ứng plaintext nếu counter chính xác.

**Đánh đổi quan trọng:** CTR không xác thực dữ liệu. Nếu đối thủ đổi một bit ciphertext, bit tương ứng plaintext đổi theo **một cách có thể dự đoán**. Ứng dụng có thể giải mã bình thường mà không có exception.

### 4.2. Quy tắc cực kỳ quan trọng: không tái sử dụng keystream

Nếu dùng cùng khóa `K` và cùng counter block `T_i` để mã hóa hai plaintext khác nhau, keystream `S_i` giống nhau:

```text
C1 = P1 XOR S
C2 = P2 XOR S

C1 XOR C2 = P1 XOR P2
```

Kẻ quan sát thấy quan hệ XOR của hai plaintext. Nếu biết/đoán được một plaintext, có thể suy ra plaintext còn lại ở các vị trí tương ứng. Đây là một dạng **two-time pad** rất nguy hiểm.

- Với CTR, điều kiện chính xác là **không bao giờ dùng lại cùng counter block đầu vào AES với cùng khóa**, kể cả giữa các message.
- Mỗi message phải có vùng counter/nonce riêng, không trùng chéo; phải chống counter overflow/wrap, tính cả số block của từng message.
- Không dùng IV/counter block cố định, bộ đếm bị reset sau restart/snapshot hoặc chỉ dựa vào random mà không hiểu xác suất va chạm/giới hạn.
- Không suy ra “CTR không cần padding nên chắc an toàn hơn CBC”: CTR có yêu cầu nonce/counter nghiêm ngặt và vẫn thiếu integrity.

Trong demo sẽ dùng IV 16 byte ngẫu nhiên chỉ cho **một lần mã hóa**. Với hệ thống sản xuất lớn, thiết kế counter/nonce duy nhất theo khóa và giới hạn số lượng block theo tài liệu/chuẩn triển khai quan trọng hơn một ví dụ ngắn.

## 5. Đối chiếu ECB, CBC, CTR từ góc nhìn bảo mật

| Tiêu chí | ECB | CBC | CTR |
| --- | --- | --- | --- |
| Cách vận hành | Mỗi khối plaintext mã hóa độc lập | XOR plaintext với ciphertext khối trước, rồi mã hóa | Mã hóa counter block thành keystream, XOR plaintext |
| Lộ mẫu lặp trong message | **Có**, khối plaintext bằng nhau → ciphertext bằng nhau | Không lộ cùng mẫu kiểu ECB khi IV/khóa dùng đúng; chaining làm các khối phụ thuộc nhau | Không lộ mẫu kiểu ECB khi counter block không trùng |
| IV/nonce/counter | Không có IV | IV 16 byte, cần mới và khó dự đoán cho encryption | Counter block 16 byte, phải bảo đảm không trùng dưới cùng khóa |
| Padding với AES | Cần nếu dữ liệu không đủ bội 16 | Cần nếu dữ liệu không đủ bội 16 | **Không cần** |
| Kích thước ciphertext | Bội số 16 | Bội số 16; thêm padding nếu dùng PKCS5Padding | Bằng kích thước plaintext |
| Mã hóa song song các khối | Có | Phụ thuộc ciphertext khối trước | Có thể tính keystream các block độc lập |
| Tác động khi ciphertext bị sửa | Thay/xáo trộn khối dẫn đến thay/xáo trộn plaintext | Lỗi hoặc sửa có cấu trúc ở khối kế tiếp; IV sửa có thể sửa block đầu | Bit ciphertext sửa → bit plaintext tương ứng sửa |
| Có MAC/tag? | **Không** | **Không** | **Không** |
| Có nên dùng nguyên bản cho dữ liệu nhạy cảm mới? | **Không** | Không, cần xác thực chuẩn; thường ưu tiên AEAD | Không, cần xác thực chuẩn; thường ưu tiên AEAD |

**Đừng đánh đồng “có IV” với “có kiểm tra integrity”.** IV CBC và nonce CTR hỗ trợ mục tiêu confidentiality; muốn biết dữ liệu có bị thay đổi phải có cơ chế xác thực riêng.

### 5.1. Nhìn nhanh hành vi sửa dữ liệu

```text
ECB:
  P_block → E_K → C_block
  Reorder/copy C_block ⇒ reorder/copy P_block (không phát hiện)

CBC (chưa có MAC):
  P1 = D_K(C1) XOR IV
  IV[0] ^= 1 ⇒ P1[0] ^= 1 (không cần biết K)

CTR (chưa có MAC):
  P = C XOR keystream
  C[0] ^= 1 ⇒ P[0] ^= 1 (không cần biết K)

GCM (có xác thực):
  C hoặc tag bị sửa ⇒ kiểm tag thất bại ⇒ từ chối plaintext
```

Sơ đồ trên là mô hình quan hệ, không phải cam kết rằng mọi sửa đổi CBC luôn cho plaintext hợp lệ hoặc GCM giải quyết được replay.

## 6. Java 17+ – demo chạy độc lập cho thấy khác biệt

Tạo file **`ModeComparisonDemo.java`** như sau. Đây là chương trình **giáo dục**: phần ECB/CBC/CTR cố ý không có MAC để quan sát điều có thể xảy ra khi chỉ dùng encryption. Khóa, IV/nonce đều tạo mới bằng các API mật mã; chương trình không in bí mật, nên stdout ổn định.

```java
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.IvParameterSpec;

public class ModeComparisonDemo {
    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128, random);
        SecretKey key = generator.generateKey();

        // Hai khối 16-byte giống hệt nhau.
        byte[] plain = new byte[32];
        Arrays.fill(plain, (byte) 'A');

        // ECB: cùng plaintext block -> cùng ciphertext block.
        Cipher ecb = Cipher.getInstance("AES/ECB/NoPadding");
        ecb.init(Cipher.ENCRYPT_MODE, key);
        byte[] ecbCipher = ecb.doFinal(plain);
        boolean ecbRepeats = Arrays.equals(
                Arrays.copyOfRange(ecbCipher, 0, 16),
                Arrays.copyOfRange(ecbCipher, 16, 32));

        // CBC: IV phải là 16 byte và được bảo vệ toàn vẹn.
        byte[] cbcIv = new byte[16];
        random.nextBytes(cbcIv);
        Cipher cbc = Cipher.getInstance("AES/CBC/PKCS5Padding");
        cbc.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(cbcIv));
        byte[] cbcCipher = cbc.doFinal(plain);

        cbc.init(Cipher.DECRYPT_MODE, key, new IvParameterSpec(cbcIv));
        boolean cbcRoundTrip = Arrays.equals(plain, cbc.doFinal(cbcCipher));

        // Nếu IV không được xác thực, sửa bit IV làm sửa bit P1.
        byte[] changedCbcIv = cbcIv.clone();
        changedCbcIv[0] ^= 1;
        cbc.init(Cipher.DECRYPT_MODE, key,
                new IvParameterSpec(changedCbcIv));
        byte[] cbcModifiedPlain = cbc.doFinal(cbcCipher);
        byte[] expectedCbcPlain = plain.clone();
        expectedCbcPlain[0] ^= 1;
        boolean cbcIvMalleable =
                Arrays.equals(expectedCbcPlain, cbcModifiedPlain);

        // CTR: không padding, độ dài ciphertext = plaintext.
        byte[] ctrIv = new byte[16];
        random.nextBytes(ctrIv);
        Cipher ctr = Cipher.getInstance("AES/CTR/NoPadding");
        ctr.init(Cipher.ENCRYPT_MODE, key, new IvParameterSpec(ctrIv));
        byte[] ctrCipher = ctr.doFinal(plain);

        ctr.init(Cipher.DECRYPT_MODE, key, new IvParameterSpec(ctrIv));
        boolean ctrRoundTrip = Arrays.equals(plain, ctr.doFinal(ctrCipher));

        // Sửa một bit ciphertext CTR sẽ sửa bit plaintext tương ứng.
        byte[] changedCtrCipher = ctrCipher.clone();
        changedCtrCipher[0] ^= 1;
        ctr.init(Cipher.DECRYPT_MODE, key, new IvParameterSpec(ctrIv));
        byte[] ctrModifiedPlain = ctr.doFinal(changedCtrCipher);
        byte[] expectedCtrPlain = plain.clone();
        expectedCtrPlain[0] ^= 1;
        boolean ctrMalleable =
                Arrays.equals(expectedCtrPlain, ctrModifiedPlain);

        // GCM: cùng AES, nhưng được bảo vệ bằng authentication tag.
        byte[] gcmNonce = new byte[12];
        random.nextBytes(gcmNonce);
        GCMParameterSpec gcmParams =
                new GCMParameterSpec(128, gcmNonce);
        Cipher gcm = Cipher.getInstance("AES/GCM/NoPadding");
        gcm.init(Cipher.ENCRYPT_MODE, key, gcmParams);
        byte[] gcmCipherAndTag = gcm.doFinal(plain);

        gcm.init(Cipher.DECRYPT_MODE, key, gcmParams);
        boolean gcmRoundTrip =
                Arrays.equals(plain, gcm.doFinal(gcmCipherAndTag));

        // Đổi một bit cuối tag: decryption phải bị từ chối.
        byte[] changedGcm = gcmCipherAndTag.clone();
        changedGcm[changedGcm.length - 1] ^= 1;
        gcm.init(Cipher.DECRYPT_MODE, key, gcmParams);
        boolean gcmRejected = false;
        try {
            gcm.doFinal(changedGcm);
        } catch (AEADBadTagException expected) {
            gcmRejected = true;
        }

        System.out.println("ecbRepeatedBlocks=" + ecbRepeats);
        System.out.println("cbcRoundTrip=" + cbcRoundTrip);
        System.out.println("cbcIvMalleable=" + cbcIvMalleable);
        System.out.println("ctrSameLength=" +
                (ctrCipher.length == plain.length));
        System.out.println("ctrRoundTrip=" + ctrRoundTrip);
        System.out.println("ctrMalleable=" + ctrMalleable);
        System.out.println("gcmRoundTrip=" + gcmRoundTrip);
        System.out.println("gcmTamperRejected=" + gcmRejected);
    }
}
```

Chạy tại thư mục chứa file:

```shell
javac ModeComparisonDemo.java
java ModeComparisonDemo
```

**Stdout kỳ vọng trên JDK 17+ chuẩn hỗ trợ các transformation trên:**

```text
ecbRepeatedBlocks=true
cbcRoundTrip=true
cbcIvMalleable=true
ctrSameLength=true
ctrRoundTrip=true
ctrMalleable=true
gcmRoundTrip=true
gcmTamperRejected=true
```

**Phân tích đúng kết quả:**

- `ecbRepeatedBlocks=true` là tính chất toán học của ECB với hai khối plaintext giống nhau; nó không phụ thuộc vào giá trị ngẫu nhiên của khóa.
- `cbcRoundTrip=true`, `ctrRoundTrip=true` nói rằng giải mã đúng khi key và IV đúng. Chúng **không chứng minh toàn vẹn**.
- `cbcIvMalleable=true` cho thấy **sửa IV chưa được xác thực** làm plaintext block đầu thay đổi tương ứng mà `Cipher` không phát hiện. Các byte padding ở cuối message không bị ảnh hưởng trong demo.
- `ctrMalleable=true` cho thấy sửa bit ciphertext CTR đổi bit plaintext tương ứng, không có exception khi chỉ giải mã CTR.
- `gcmTamperRejected=true` chứng minh tag trong ví dụ phát hiện thay đổi; bên nhận phải từ chối không sử dụng plaintext chưa xác thực.
- Đoạn code **không trình bày cách lưu nonce hoặc quản lý số lần mã hóa dài hạn**. Khi triển khai thật, phải bảo đảm không tái dùng cặp khóa–nonce GCM/CTR.

### 6.1. Có thể suy ra từ ví dụ những gì?

**Có thể kết luận:** ECB lộ khối lặp; CBC và CTR chỉ cung cấp confidentiality khi dùng đúng mode/IV/counter, vẫn cho phép can thiệp ciphertext; AEAD có xác thực được kiểm tra khi giải mã.

**Không thể kết luận:** chỉ từ việc `gcmTamperRejected=true`, ứng dụng đã có toàn bộ security controls. Vẫn cần quản lý khóa, nonce, AAD, quyền truy cập, chống replay và xử lý lỗi an toàn. CBC/CTR demo cố ý chưa có MAC, **không sao chép nguyên vào production**.

## 7. Tại sao phải xác thực ciphertext trước khi tin plaintext?

Giả sử backend lưu:

```text
IV || ciphertext
```

và chỉ gọi `Cipher.doFinal(ciphertext)`. Khi bị sửa byte:

- ECB có thể chấp nhận khối ciphertext bị copy/reorder.
- CBC có thể trả dữ liệu bị sửa, hoặc ném lỗi padding; phản hồi khác biệt dễ tạo oracle.
- CTR luôn có phép XOR cho mọi byte ciphertext (nếu độ dài/counter hợp lệ), không tự phát hiện bit bị sửa.

**Mã hóa không có chứng thực tạo ra ranh giới tin cậy sai:** ứng dụng nhìn thấy bytes “đã giải mã” và tưởng chúng là dữ liệu do một bên hợp lệ tạo ra.

Khi cần chống sửa đổi, dùng một trong hai hướng đã được chuẩn hóa:

1. **AEAD** (*Authenticated Encryption with Associated Data*): thuật toán cung cấp confidentiality + integrity/authentication trong một cơ chế, ví dụ `AES/GCM/NoPadding`. Tag xác thực ciphertext, nonce và AAD theo cách đặc tả thuật toán. Đây là **lựa chọn ưu tiên cho hệ thống mới** nếu thỏa điều kiện nonce/key lifecycle.
2. **Encrypt-then-MAC (EtM)**: dùng encryption mode phù hợp cộng thêm MAC mật mã (ví dụ HMAC-SHA256 với **khóa khác** khóa AES); xác thực định dạng/IV/ciphertext và dữ liệu ngữ cảnh trước khi decrypt. Chỉ chọn khi cần tương thích legacy/giao thức đã được thiết kế, review và thử nghiệm cẩn thận.

**Không** thay MAC bằng checksum, CRC32, SHA-256 không khóa hoặc “thử decrypt xem có lỗi”. Hash công khai có thể bị đối thủ tính lại sau khi sửa dữ liệu. MAC phải dùng khóa bí mật/thuật toán chuẩn. Chữ ký số cũng có thể cung cấp xác thực theo mô hình khóa khác, nhưng không cần biến mọi message đối xứng thành bài toán chữ ký số.

### 7.1. Quy tắc Encrypt-then-MAC

Ví dụ định dạng tự mô tả rõ phiên bản:

```text
message = version || IV || ciphertext
tag     = HMAC_SHA256(macKey, message)
packet  = message || tag
```

Bên gửi:

1. Có **AES key** và **HMAC key** độc lập, được quản lý an toàn.
2. Tạo IV CBC mới bằng `SecureRandom`.
3. Encrypt plaintext bằng AES/CBC/PKCS5Padding.
4. Tính HMAC trên **version + IV + ciphertext** (cũng xác thực metadata/AAD ngoài nếu giao thức có).
5. Gửi `packet`; không cần giấu IV, nhưng phải giữ key bí mật.

Bên nhận:

1. Phân tích khung dữ liệu và kiểm độ dài với giới hạn tài nguyên phù hợp.
2. Tính lại HMAC cho đúng **toàn bộ dữ liệu cần xác thực**.
3. So sánh tag với cơ chế tránh rò timing, ví dụ `MessageDigest.isEqual`.
4. **Chỉ nếu tag hợp lệ**, kiểm phiên bản/format và giải mã CBC; xử lý ngoại lệ theo chính sách thống nhất.

Nếu decrypt CBC **trước** khi verify HMAC, cơ chế có thể vẫn để lộ padding oracle. Nếu MAC chỉ phủ ciphertext mà bỏ IV/version/metadata, đối thủ có thể sửa các phần bỏ sót. Nếu tái sử dụng cùng key làm AES và HMAC mà không có key separation rõ ràng, thiết kế thiếu ràng buộc mật mã cần thiết.

### 7.2. Vì sao xác thực không tự chống replay?

Giả sử packet hợp lệ đã được ký MAC. Đối thủ **không sửa** packet, chỉ gửi lại y nguyên. MAC vẫn hợp lệ vì nội dung thực sự không thay đổi. Hệ thống cần chống replay bằng **sequence number, transaction ID, timestamp có cửa sổ chấp nhận, token một lần, state chống trùng** hoặc cơ chế đã được giao thức chuẩn quy định. Các trường nhận dạng chống replay cũng phải được bảo vệ toàn vẹn.

## 8. Java 17+ – ví dụ Encrypt-then-MAC cho CBC legacy

Bài toán này dùng hai khóa độc lập: AES-128 để mã hóa và HMAC-SHA256 (32 byte secret) để xác thực. Format của ví dụ: `1 byte version || 16 byte IV || ciphertext || 32 byte HMAC`. Chỉ giải mã khi MAC hợp lệ.

Đây là **ví dụ giáo dục cho giao thức legacy**. Trong hệ thống mới, ưu tiên dùng AEAD chuẩn; tự định nghĩa packet format cần thêm versioning, key IDs, giới hạn kích thước, rotation, quản lý metadata và review bảo mật.

Tạo file **`AuthenticatedCbcDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public class AuthenticatedCbcDemo {
    private static final int IV_SIZE = 16;
    private static final int TAG_SIZE = 32;
    private static final int HEADER_SIZE = 1 + IV_SIZE;
    private static final byte VERSION = 1;

    private static byte[] hmac(SecretKey macKey, byte[] message)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(macKey);
        return mac.doFinal(message);
    }

    private static byte[] seal(byte[] plaintext, SecretKey aesKey,
            SecretKey macKey, SecureRandom random)
            throws GeneralSecurityException {
        byte[] iv = new byte[IV_SIZE];
        random.nextBytes(iv);

        Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
        cipher.init(Cipher.ENCRYPT_MODE, aesKey, new IvParameterSpec(iv));
        byte[] encrypted = cipher.doFinal(plaintext);

        byte[] body = new byte[HEADER_SIZE + encrypted.length];
        body[0] = VERSION;
        System.arraycopy(iv, 0, body, 1, IV_SIZE);
        System.arraycopy(encrypted, 0, body, HEADER_SIZE, encrypted.length);

        byte[] tag = hmac(macKey, body);
        byte[] packet = Arrays.copyOf(body, body.length + tag.length);
        System.arraycopy(tag, 0, packet, body.length, tag.length);
        return packet;
    }

    private static byte[] open(byte[] packet, SecretKey aesKey,
            SecretKey macKey) throws GeneralSecurityException {
        // Ít nhất 1 header + 16 IV + 16 ciphertext + 32 tag.
        if (packet.length < HEADER_SIZE + 16 + TAG_SIZE) {
            throw new GeneralSecurityException("Invalid message");
        }
        int bodyEnd = packet.length - TAG_SIZE;
        byte[] body = Arrays.copyOf(packet, bodyEnd);
        byte[] suppliedTag = Arrays.copyOfRange(
                packet, bodyEnd, packet.length);
        byte[] computedTag = hmac(macKey, body);

        // Quan trọng: verify MAC trước khi decrypt CBC.
        if (!MessageDigest.isEqual(computedTag, suppliedTag)) {
            throw new GeneralSecurityException("Invalid message");
        }

        int encryptedLength = body.length - HEADER_SIZE;
        if (body[0] != VERSION || encryptedLength % 16 != 0) {
            throw new GeneralSecurityException("Invalid message");
        }

        byte[] iv = Arrays.copyOfRange(body, 1, HEADER_SIZE);
        byte[] encrypted = Arrays.copyOfRange(
                body, HEADER_SIZE, body.length);
        Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
        cipher.init(Cipher.DECRYPT_MODE, aesKey, new IvParameterSpec(iv));
        return cipher.doFinal(encrypted);
    }

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();

        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128, random);
        SecretKey aesKey = generator.generateKey();

        byte[] macBytes = new byte[32];
        random.nextBytes(macBytes);
        SecretKey macKey =
                new SecretKeySpec(macBytes, "HmacSHA256");

        byte[] plain = "CBC needs integrity"
                .getBytes(StandardCharsets.UTF_8);
        byte[] sealed = seal(plain, aesKey, macKey, random);
        boolean valid = Arrays.equals(
                plain, open(sealed, aesKey, macKey));

        byte[] changed = sealed.clone();
        changed[changed.length - 1] ^= 1;
        boolean rejected = false;
        try {
            open(changed, aesKey, macKey);
        } catch (GeneralSecurityException expected) {
            rejected = true;
        }

        System.out.println("authenticatedRoundTrip=" + valid);
        System.out.println("tamperRejected=" + rejected);
    }
}
```

Biên dịch/chạy:

```shell
javac AuthenticatedCbcDemo.java
java AuthenticatedCbcDemo
```

Stdout kỳ vọng:

```text
authenticatedRoundTrip=true
tamperRejected=true
```

**Diễn giải:** ciphertext bị sửa sau bước encrypt không còn MAC hợp lệ, vì thế `open()` từ chối **trước khi gọi CBC decrypt**. HMAC xác thực cả header version, IV và ciphertext. `MessageDigest.isEqual` giảm rò timing từ so sánh tag; điều này không tự giải quyết mọi side channel của toàn hệ thống.

**Giới hạn cố ý của demo:** không có cơ chế chống replay, key ID, giới hạn packet tối đa, quản lý khóa dài hạn, ràng buộc user/request/AAD, bảo vệ lỗi qua HTTP hoặc rotate key. Ứng dụng production phải giải quyết những việc đó; đừng thay packet format chuẩn bằng ví dụ học thuật này khi có lựa chọn giao thức/AEAD đã chuẩn hóa.

### 8.1. Nếu phải dùng CTR + MAC?

Các nguyên tắc tương tự: MAC phải bao phủ **đầy đủ nonce/counter + ciphertext + version + context** bằng khóa riêng; verify MAC **trước khi xuất plaintext**; counter không bao giờ trùng dưới cùng khóa. Vì CTR không dùng padding, không có lỗi `BadPaddingException`, nhưng **bit-flipping và keystream reuse** vẫn cực kỳ nguy hiểm nếu bỏ xác thực/nonce discipline.

## 9. AEAD và AES-GCM: lựa chọn mặc định tốt hơn cho thiết kế mới

**AEAD** kết hợp mã hóa và kiểm tính xác thực trong một sơ đồ; có thể xác thực thêm **AAD – Additional Authenticated Data** mà không mã hóa AAD. Ví dụ metadata AAD: loại message, phiên bản protocol, tenant ID hoặc transaction context. Dữ liệu AAD phải được cung cấp **giống hệt** ở cả encryption và decryption.

Java:

```java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
GCMParameterSpec params = new GCMParameterSpec(128, nonce);
cipher.init(Cipher.ENCRYPT_MODE, aesKey, params);
cipher.updateAAD(aad);
byte[] ciphertextAndTag = cipher.doFinal(plaintext);
```

Đoạn này **không độc lập**: cần `aesKey`, `nonce` (thông thường 12 byte, **không lặp với cùng AES key**), `aad`, `plaintext` và xử lý exception. Trong JCE, `doFinal()` với GCM encryption thường trả **ciphertext nối với authentication tag**; khi decrypt dùng cùng key/nonce/AAD và truyền đúng dữ liệu có tag để xác minh.

### 9.1. GCM không tự động giải quyết mọi lỗi

- **Nonce reuse:** dùng lại cặp **key + nonce** với GCM là lỗi bảo mật nghiêm trọng, có thể phá confidentiality và authentication. Đặt chính sách sinh nonce duy nhất, giới hạn số message và quản lý trạng thái qua restart.
- **Tag:** thường dùng 128 bit, đừng tự rút ngắn theo cảm tính. Xử lý `AEADBadTagException` bằng cách từ chối toàn bộ message; không cho business logic nhận plaintext trước khi xác thực xong.
- **AAD:** AAD được xác thực nhưng **không được mã hóa**. Không đặt secret vào AAD với kỳ vọng dữ liệu được giấu. Cùng AAD ở cả hai phía là bắt buộc.
- **Replay:** người khác gửi lại đúng ciphertext+tag cũ vẫn có tag hợp lệ. Chống replay cần thiết kế state/protocol.
- **Key storage và authorization:** AEAD không tự quản lý khóa, quyền truy cập hay việc rò key ở log.
- **Streaming:** tránh phát dữ liệu chưa kiểm tag thành plaintext đã được tin cậy cho downstream; API/framework cần đảm bảo xử lý dữ liệu theo ranh giới xác thực.

**Đừng chỉ thay `AES/CBC/PKCS5Padding` bằng `AES/GCM/NoPadding` rồi giữ nguyên định dạng IV 16 byte, tập quán reuse IV hoặc bỏ quản lý tag.** Thay mode đòi hỏi cập nhật cả giao thức, định dạng, giới hạn sử dụng và cách xử lý lỗi.

### 9.2. Khi nào không “tự đổi mode” trong hệ thống đang chạy?

Một hệ thống đã lưu hàng triệu bản mã CBC không thể giải mã chúng như GCM bằng cách thay transformation. Muốn migrate cần định danh version, đọc dữ liệu cũ theo quy trình an toàn, xác thực trước khi dùng dữ liệu, mã hóa lại bằng AEAD với nonce mới và cập nhật format. Nếu giao thức CBC cũ thiếu MAC, nên xem việc giải mã dữ liệu từ nguồn không đáng tin cậy là rủi ro cần thiết kế riêng, không mở endpoint legacy rộng rãi.

## 10. Key, IV, nonce, MAC, tag và format vận hành

Thiết kế một record đã mã hóa nên trả lời được:

- **Algorithm/mode/version:** sử dụng AES-GCM hay CBC+HMAC? Cần có marker/metadata rõ ràng để giải mã đúng và migrate.
- **Key identity:** khóa nào, phiên bản nào? Khóa AES và khóa MAC phải độc lập nếu dùng EtM; quản lý trong keystore/KMS/HSM phù hợp.
- **IV/nonce:** cần bao nhiêu byte, được tạo như thế nào, có thể lặp sau crash/retry/concurrent writers không? IV/nonce có thể lưu cạnh ciphertext.
- **Ciphertext:** dài bao nhiêu, encoding/định dạng được giới hạn ra sao? Khi lưu Base64, encoding không tăng tính bí mật.
- **Authentication:** tag/MAC có bao phủ tất cả trường ảnh hưởng đến cách hiểu bản mã (version, IV, ciphertext, metadata hoặc AAD) không?
- **Associated context:** record này gắn với user/tenant/object/route nào? Có cần xác thực context để chống hoán đổi ciphertext hợp lệ giữa các đối tượng?
- **Replay/order:** có cần sequence number, request ID, token chỉ dùng một lần hoặc counter được giám sát không?
- **Failure behavior:** xác thực sai thì từ chối, không dùng plaintext và không lộ lý do chi tiết qua API, log hay timing.

Ví dụ format AEAD khái niệm:

```text
version || key-id || nonce || ciphertext || tag
                   \_____ authenticated ______/
AAD: version, key-id, tenant/context (định nghĩa giao thức quyết định)
```

Sơ đồ chỉ để học: tính chất “được xác thực” phụ thuộc **chính xác những bytes nào đưa vào AAD và MAC/tag**. Không mặc nhiên mọi header trong định dạng file đều tự được xác thực. Việc lập trình đúng schema, thứ tự, encoding, độ dài, phân tách trường là một phần của an toàn.

## 11. Xử lý lỗi trong Java và các dấu hiệu chẩn đoán

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `InvalidKeyException` | Key AES sai loại/độ dài, provider/policy không phù hợp | Xác minh algorithm, số bit key, provider; không log secret key |
| `InvalidAlgorithmParameterException` | IV/nonce sai kích thước/kiểu, provider không hỗ trợ tham số | Kiểm transformation và `IvParameterSpec`/`GCMParameterSpec` |
| `IllegalBlockSizeException` | ECB/CBC `NoPadding` nhưng plaintext/ciphertext không phải bội số block | Chọn format/padding chuẩn đúng giao thức, không thêm byte tùy ý |
| `BadPaddingException` khi CBC decrypt | Padding hỏng, key/IV/ciphertext sai, dữ liệu bị sửa | Nếu dùng EtM, **verify MAC trước decrypt**; không expose padding oracle |
| `AEADBadTagException` khi GCM decrypt | Sai key/nonce/AAD/tag hoặc dữ liệu thay đổi | Từ chối message; kiểm metadata và lifecycle, không bỏ qua tag |
| Plaintext CTR thay đổi một vài byte nhưng không exception | CTR không xác thực, ciphertext bị sửa hoặc counter sai | Dùng AEAD/MAC và nonce đúng |
| Hai ciphertext ECB có nhiều block giống nhau | Mode lộ khối lặp | Không dùng ECB cho message thực tế; thay bằng AEAD |
| CTR cho ra thông tin về hai plaintext | Keystream/counter bị tái sử dụng cùng khóa | Sửa quy trình nonce/counter, đánh giá dữ liệu đã lộ và rotation khóa |
| Giải mã thành công nhưng API business data sai | Có thể do thiếu authentication/validity checks, record bị tráo hoặc replay | Ràng buộc integrity, AAD/context và authorization/replay controls |
| GCM báo sai tag sau migration | Sai nonce/tag layout, AAD hoặc format/version | Thiết kế format rõ ràng; test vector và kiểm liệu đúng phiên bản |

Một lỗi thiết kế thường gặp: trả HTTP 400 với text `invalid padding` còn HTTP 401 với `bad MAC`, làm đối thủ có một oracle mạnh. Trên giao diện bên ngoài, xử lý message không xác thực bằng lỗi đồng nhất và quan sát log nội bộ có kiểm soát. Đừng tin vào text exception từ provider làm thông báo public.

### 11.1. Cẩn thận với thứ tự xử lý

**Sai:**

```text
Nhận IV+ciphertext
→ Giải mã CBC
→ Parse JSON
→ Kiểm role trong JSON
→ Cuối cùng mới kiểm HMAC (hoặc không kiểm)
```

**Đúng với Encrypt-then-MAC:**

```text
Nhận packet, kiểm framing/size
→ Kiểm HMAC xác thực version+IV+ciphertext+context
→ Nếu sai, từ chối; không decrypt
→ Nếu đúng, mới giải mã CBC
→ Parse dữ liệu
→ Kiểm schema và phân quyền nghiệp vụ
```

**Đúng với GCM:**

```text
Nhận packet, giải mã metadata và giới hạn size
→ Cung cấp key+nonce+AAD đúng cho Cipher GCM
→ doFinal xác minh tag
→ Nếu tag sai, từ chối toàn bộ plaintext
→ Nếu tag đúng, parse/check schema và phân quyền nghiệp vụ
```

MAC/AEAD tạo ranh giới xác thực cho bytes; **schema validation và authorization** vẫn là các bước riêng.

## 12. Câu hỏi tự kiểm tra có đáp án

**1. Tại sao ECB bị coi là không phù hợp để mã hóa một ảnh?** Vì các block plaintext giống nhau sinh ra các block ciphertext giống nhau dưới cùng khóa, làm lộ mẫu/đường nét/cấu trúc dù pixel gốc đã mã hóa.

**2. Dùng AES-256 có giải quyết mẫu lặp ECB không?** Không. Key dài hơn không thay đổi phép ánh xạ khối deterministic của ECB.

**3. CBC có IV ngẫu nhiên 16 byte nhưng không có HMAC. Dữ liệu có toàn vẹn không?** Không. IV hoặc ciphertext có thể bị sửa; padding oracle cũng có thể xuất hiện nếu ứng dụng phản hồi theo lỗi giải mã.

**4. IV CBC có phải là secret không?** Không, thông thường có thể công khai. Nhưng phải được tạo mới/khó dự đoán khi cần và **xác thực toàn vẹn** cùng message nếu dùng EtM.

**5. Tại sao `AES/CTR/NoPadding` mã hóa dữ liệu 17 byte không cần padding?** CTR biến đầu ra AES của counter block thành keystream XOR với plaintext; block cuối dùng phần keystream cần thiết, ciphertext dài đúng 17 byte.

**6. Nếu CTR dùng cùng key và counter block cho hai message, đối thủ học gì?** Khi thấy `C1 XOR C2`, đối thủ tính được `P1 XOR P2`; plaintext có cấu trúc/biết trước có thể bị lộ đáng kể.

**7. Vì sao CTR decrypt thành công không chứng minh ciphertext nguyên vẹn?** Giải mã CTR là XOR với keystream; đổi bit ciphertext sẽ đổi bit plaintext tương ứng mà không yêu cầu kiểm tag.

**8. Vì sao CBC+HMAC phải xác minh MAC trước decrypt?** Để dữ liệu không xác thực không đi vào phép giải mã padding và tạo kênh quan sát dẫn tới padding oracle.

**9. Có thể thay HMAC bằng SHA-256(ciphertext) không?** Không. Hash công khai không có secret key; đối thủ sửa ciphertext rồi tính lại hash.

**10. GCM có chống replay không?** Không. GCM xác thực nội dung của một packet, nhưng packet cũ có tag hợp lệ vẫn có thể được phát lại; cần sequence/state hoặc cơ chế một lần.

**11. GCM nonce cần giữ bí mật không?** Không, nhưng **phải không lặp dưới cùng key**; không để cơ chế khởi động/retry/đồng bộ khiến nonce tái sử dụng.

**12. Khi nào nên chọn CBC+HMAC thay vì GCM?** Chủ yếu khi phải tương thích định dạng/giao thức legacy đã được kiểm chứng, có thiết kế MAC trước decrypt, khóa tách biệt và versioning. Hệ thống mới thường ưu tiên AEAD được cung cấp và quản lý đúng cách.

## 13. Checklist trước khi đưa mã hóa đối xứng vào production

1. **Không dùng ECB** để mã hóa thông điệp có cấu trúc hoặc dữ liệu người dùng.
2. Chọn transformation đầy đủ; không gọi `Cipher.getInstance("AES")` một cách mơ hồ.
3. **Ưu tiên AEAD** như AES-GCM; nếu dùng CBC/CTR, bổ sung sơ đồ xác thực đúng với khóa riêng và verify trước decrypt.
4. Tạo **key** bằng nguồn mật mã phù hợp, lưu trong cơ chế quản lý khóa; không hard-code vào source, log hoặc URL.
5. Xác định kích thước/format IV hoặc nonce; **CBC IV mới, khó dự đoán**; CTR/GCM **không trùng counter/nonce với cùng key**, có giới hạn usage và xử lý restart/retry.
6. Xác thực **version, IV/nonce, ciphertext và metadata/AAD ảnh hưởng đến ngữ nghĩa**; không bỏ trường quan trọng khỏi MAC/tag.
7. Không phát plaintext hay xử lý business logic nếu xác thực thất bại; lỗi bên ngoài đồng nhất, không leak padding/timing.
8. Có cơ chế chống **replay**, phân quyền và kiểm tra schema theo threat model; MAC/AEAD không tự cung cấp chúng.
9. Định dạng lưu trữ có version/key ID và quy trình migration; không thay mode mà bỏ qua dữ liệu cũ.
10. Viết test cho **round-trip**, sửa một byte ciphertext/tag/IV/AAD phải bị từ chối trong đường có xác thực, ràng buộc context và failure behavior.

## Tài liệu chính thống

- [NIST SP 800-38A – Recommendation for Block Cipher Modes of Operation: Methods and Techniques](https://csrc.nist.gov/pubs/sp/800/38/a/final): định nghĩa ECB, CBC, CTR; yêu cầu IV/counter và tính chất vận hành.
- [NIST SP 800-38D – Galois/Counter Mode (GCM) and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): xác thực AES-GCM và yêu cầu quản lý IV/nonce.
- [Java Cryptography Architecture (JCA) Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): engine `Cipher`, provider và API mật mã Java.
- [Java SE 17 – Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html): transformation, padding, AEAD/GCM, `updateAAD` và hành vi encryption/decryption.
- [Java SE 17 – GCMParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): tag length và nonce/IV trong Java.
- [Java SE 17 – Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html) và [MessageDigest.isEqual](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): HMAC và đối chiếu tag trong một thiết kế có xác thực.