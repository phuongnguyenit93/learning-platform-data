# AES – Advanced Encryption Standard trong mật mã đối xứng

**AES (Advanced Encryption Standard)** là chuẩn thuật toán **mã hóa khối đối xứng**: cùng một khóa bí mật được dùng trong quá trình mã hóa và giải mã. AES là nền tảng phổ biến để bảo vệ dữ liệu lưu trữ, dữ liệu truyền qua giao thức an toàn, khóa dữ liệu trong hệ thống phân tán và nhiều giải pháp **envelope encryption**.

Trong chương **Mật mã đối xứng** thuộc module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài này tập trung vào cách AES hoạt động ở mức cần thiết cho người thiết kế hệ thống; cách chọn chế độ mã hóa, quản lý khóa, nonce/IV; mối quan hệ với mật mã bất đối xứng, chữ ký số, KMS/HSM; và rủi ro trong vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng đến thu hồi và hủy**.

> **Nguyên tắc quan trọng:** AES là thuật toán mã hóa khối, **không tự tạo thành cơ chế mã hóa dữ liệu an toàn hoàn chỉnh**. Cần kết hợp AES với một chế độ hoạt động, quy tắc nonce/IV và kiểm tra tính toàn vẹn phù hợp. Với dữ liệu ứng dụng mới, **AES-GCM** là một lựa chọn thông dụng khi hệ thống bảo đảm các điều kiện sử dụng của nó.

## 1. AES là gì và giải quyết bài toán nào?

AES là thuật toán đối xứng được chuẩn hóa trong **FIPS 197**. Thuật toán biến một khối dữ liệu 128 bit thành một khối bản mã 128 bit dưới tác động của khóa bí mật. Quá trình giải mã dùng cùng khóa bí mật để khôi phục khối ban đầu.

AES có ba kích thước khóa được chuẩn hóa:

| Biến thể | Độ dài khóa | Độ dài khối cố định | Số vòng biến đổi |
| --- | ---: | ---: | ---: |
| **AES-128** | 128 bit (16 byte) | 128 bit (16 byte) | 10 |
| **AES-192** | 192 bit (24 byte) | 128 bit (16 byte) | 12 |
| **AES-256** | 256 bit (32 byte) | 128 bit (16 byte) | 14 |

**AES-256 không có kích thước khối 256 bit**: kích thước khối AES luôn là 128 bit. Số bit trong tên gọi chỉ **độ dài khóa**. AES-128 vẫn cung cấp mức bảo mật rất cao khi triển khai đúng; lựa chọn AES-256 thường gắn với yêu cầu chính sách hoặc biên an toàn dài hạn, đồng thời có thể ảnh hưởng hiệu năng theo phần cứng.

AES phù hợp khi hai đầu giao tiếp đã chia sẻ được một khóa bí mật hoặc khi ứng dụng có dịch vụ quản lý khóa bảo đảm việc cấp phát khóa. So với mã hóa bất đối xứng, AES thường có hiệu năng rất tốt khi xử lý lượng dữ liệu lớn.

**AES không phải hàm băm, thuật toán ký số hoặc cơ chế trao đổi khóa.** AES-GCM xác thực tính toàn vẹn của bản mã dựa trên một khóa bí mật chia sẻ, nhưng không cung cấp bằng chứng chữ ký số công khai có thể kiểm chứng như Ed25519 hoặc RSA-PSS. Mật mã bất đối xứng có thể được dùng để thiết lập/bảo vệ khóa AES; chữ ký số có thể bổ sung tính xác thực của người ký theo yêu cầu nghiệp vụ.

## 2. Bên trong AES: hiểu đủ để chọn đúng giải pháp

AES là một **mạng thay thế và hoán vị (substitution–permutation network)** hoạt động trên trạng thái 128 bit, thường biểu diễn thành ma trận 4 × 4 byte. Theo cấu trúc vòng của AES, các phép biến đổi chính gồm:

- **SubBytes:** thay thế từng byte bằng bảng ánh xạ phi tuyến (S-box).
- **ShiftRows:** dịch vòng các hàng của trạng thái.
- **MixColumns:** trộn các byte trong từng cột để khuếch tán ảnh hưởng của dữ liệu.
- **AddRoundKey:** kết hợp trạng thái với khóa vòng được dẫn xuất từ khóa gốc.

Vòng cuối bỏ bước MixColumns theo đặc tả. Các bước tạo **độ hỗn loạn và khuếch tán**, khiến quan hệ giữa bản rõ, bản mã và khóa khó bị khai thác bằng các kỹ thuật phân tích mật mã đã biết khi dùng đúng tham số.

Trong ứng dụng Java, **không tự viết SubBytes/MixColumns hay tự triển khai AES**. Hãy dùng thư viện và provider đã được kiểm chứng; vấn đề vận hành khó nhất thường nằm ở **chế độ mã hóa, nonce, quản lý khóa, quyền giải mã và metadata**.

## 3. Vì sao cần chế độ hoạt động của AES?

Một phép biến đổi AES chỉ xử lý **một khối 16 byte**. File, bản ghi và thông điệp thường dài tùy ý, nên phải sử dụng **mode of operation** để mã hóa nhiều byte và, khi cần, cung cấp xác thực tính toàn vẹn.

| Chế độ/cơ chế | Thuộc tính chính | Lựa chọn triển khai |
| --- | --- | --- |
| **AES-GCM** | Mã hóa có xác thực (**AEAD**), cung cấp tính bí mật và kiểm tra toàn vẹn bản mã/AAD. | Thường ưu tiên cho dữ liệu ứng dụng mới khi quản lý nonce duy nhất và giới hạn sử dụng khóa đúng. |
| **AES-CTR** | Tạo luồng khóa từ AES; **không tự xác thực** bản mã. | Chỉ dùng trong thiết kế có cơ chế xác thực riêng, được kiểm chứng. |
| **AES-CBC** | Mã hóa khối có chaining và padding thích hợp; **không tự xác thực**. | Chủ yếu gặp ở hệ thống cũ; nếu phải dùng, cần giao thức xác thực đúng và xử lý lỗi an toàn. |
| **AES-ECB** | Mã hóa độc lập từng khối giống nhau. | **Không dùng để mã hóa dữ liệu thông thường** vì làm lộ mẫu lặp của bản rõ. |
| **AES-XTS** | Chế độ mã hóa hướng đến sector/khối lưu trữ có vị trí; không cung cấp tính xác thực tổng quát. | Thích hợp cho một số hệ thống mã hóa ổ đĩa, không thay thế AEAD ở tầng bản ghi/thông điệp. |
| **AES-KW / AES-KWP** | Cơ chế chuyên dụng bọc (**wrap**) vật liệu khóa khác. | Dùng cho bảo vệ DEK/khóa khác theo chuẩn và phạm vi được hỗ trợ. |

Ví dụ, nếu cùng một khối bản rõ xuất hiện nhiều lần, AES-ECB với cùng khóa sẽ tạo cùng một khối bản mã tương ứng; điều này có thể để lộ cấu trúc dữ liệu. Tương tự, AES-CBC hay AES-CTR nếu dùng thiếu cơ chế xác thực sẽ không phát hiện đầy đủ các thay đổi ác ý của bản mã.

**Không chọn thuật toán bằng cách chỉ kiểm tra chuỗi AES.** Cần đọc trọn tổ hợp **thuật toán + chế độ + padding + nonce/IV + tag + quy tắc sử dụng khóa**.

## 4. AES-GCM: mã hóa và xác thực trong một cơ chế

**GCM (Galois/Counter Mode)** là chế độ mã hóa có xác thực dùng AES để bảo vệ dữ liệu. Đây là một dạng **AEAD (Authenticated Encryption with Associated Data)**.

Đầu vào cơ bản của một phép mã hóa AES-GCM gồm:

1. **Key (K):** khóa AES bí mật, thường dài 128 hoặc 256 bit.
2. **Nonce/IV (N):** giá trị không cần giữ bí mật nhưng phải **không trùng lặp với cùng khóa** theo quy tắc của chế độ; kích thước 96 bit (12 byte) là lựa chọn điển hình.
3. **Plaintext (P):** dữ liệu cần mã hóa.
4. **AAD:** dữ liệu bổ sung được **xác thực nhưng không mã hóa**, chẳng hạn tenant ID, object ID hoặc phiên bản schema đã được kiểm tra.

Đầu ra là **ciphertext (C)** và **authentication tag (T)**. Khi giải mã, hệ thống phải cung cấp cùng khóa, nonce và AAD; bản mã/tag bị sửa đổi hoặc AAD sai phải khiến việc kiểm tra xác thực thất bại.

~~~mermaid
flowchart LR
    K["Khóa AES bí mật"] --> E["AES-GCM encrypt"]
    N["Nonce duy nhất theo khóa"] --> E
    A["AAD: metadata được xác thực"] --> E
    P["Plaintext"] --> E
    E --> C["Ciphertext + Tag"]
    C --> D["AES-GCM decrypt + verify"]
    K --> D
    N --> D
    A --> D
    D --> R{"Tag hợp lệ?"}
    R -->|Có| O["Trả plaintext"]
    R -->|Không| X["Từ chối dữ liệu"]
~~~

**AAD không được mã hóa**: ai nhìn thấy payload vẫn có thể đọc AAD nếu giao thức lưu nó ở dạng rõ. AAD bảo đảm sự gắn kết của dữ liệu với ngữ cảnh **nếu bên giải mã cũng xác thực ngữ cảnh đó từ nguồn đáng tin cậy**. Không được tin tenant ID do client tự khai báo rồi coi việc kiểm tra tag là đã chứng minh quyền truy cập của client.

### 4.1. Nonce quan trọng như thế nào?

Với AES-GCM, **tái sử dụng cùng nonce dưới cùng một khóa là lỗi bảo mật nghiêm trọng**: có thể làm lộ mối quan hệ giữa các bản rõ và phá vỡ tính toàn vẹn. Nonce có thể công khai và thường được lưu ngay cạnh bản mã, nhưng không được trùng theo khóa.

- Với số lượng bản mã vừa phải, hệ thống có thể tạo nonce 96 bit bằng bộ sinh số ngẫu nhiên mật mã (**CSPRNG**) và theo dõi giới hạn số lần mã hóa để duy trì xác suất va chạm đủ nhỏ.
- Với hệ thống phát hành rất nhiều bản mã hoặc nhiều worker cùng dùng một khóa, nên thiết kế **nonce duy nhất có kiểm soát**, chẳng hạn bộ đếm được phân bổ an toàn theo phiên/worker, cùng chính sách giới hạn sử dụng khóa.
- Không tự đặt nonce cố định như toàn byte 0, không lấy trực tiếp timestamp làm bảo đảm duy nhất, và không dùng lại nonce sau restart nếu sơ đồ cấp phát chưa xử lý tính bền vững.
- Khi có nhiều phiên bản khóa, lưu **key ID/phiên bản** cùng bản mã để tìm đúng khóa giải mã. Đặt chính sách khóa riêng cho mỗi mục đích và môi trường.

Trong AES-GCM, tag thường dài 128 bit. Không tự rút ngắn tag để tiết kiệm dung lượng khi chưa có đánh giá cụ thể về mức bảo mật, giới hạn sử dụng và giao thức.

### 4.2. GCM kiểm tra điều gì, không kiểm tra điều gì?

AES-GCM cung cấp **tính bí mật và xác thực tính toàn vẹn** của bản mã và AAD trong mô hình hai phía biết cùng khóa. Nó **không tự giải quyết** phân quyền người dùng, nhận dạng người ký, chống phát lại hoặc quản lý thời hạn dữ liệu.

Ví dụ: kẻ tấn công sao chép nguyên một bản mã/tag/nonce cũ và gửi lại. Nếu hệ thống chỉ kiểm tra tag, bản mã cũ có thể vẫn xác thực thành công. Để chống **replay**, ứng dụng cần sequence number, timestamp được kiểm chứng, nonce nghiệp vụ hoặc trạng thái đã xử lý tùy giao thức.

## 5. Ví dụ Java 17+: mã hóa/giải mã AES-256-GCM

Ví dụ sau minh họa JCA (**Java Cryptography Architecture**) với khóa AES-256 sinh bằng **KeyGenerator**, nonce mới 12 byte, AAD và kiểm tra tag khi giải mã. Khóa chỉ được giữ trong bộ nhớ để đơn giản hóa bài học; trong hệ thống sản xuất, nên sử dụng KMS/HSM hoặc cơ chế bảo vệ khóa phù hợp.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class AesGcmDemo {
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey dek = generator.generateKey();

        byte[] nonce = new byte[NONCE_BYTES];
        new SecureRandom().nextBytes(nonce);

        byte[] aad = "tenant=shop-a;record=order-123;v=1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Thong tin don hang nhay cam"
                .getBytes(StandardCharsets.UTF_8);

        // Mã hóa với một nonce mới cho lần mã hóa này.
        Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
        encryptor.init(Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, nonce));
        encryptor.updateAAD(aad);
        byte[] ciphertextAndTag = encryptor.doFinal(plaintext);

        // Có thể lưu nonce + ciphertextAndTag + AAD/metadata + key ID.
        // Không ghi hoặc in byte khóa bí mật.
        System.out.println("Nonce (Base64): " +
                Base64.getEncoder().encodeToString(nonce));
        System.out.println("Ciphertext + tag (Base64): " +
                Base64.getEncoder().encodeToString(ciphertextAndTag));

        Cipher decryptor = Cipher.getInstance("AES/GCM/NoPadding");
        decryptor.init(Cipher.DECRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, nonce));
        decryptor.updateAAD(aad);
        byte[] recovered = decryptor.doFinal(ciphertextAndTag);
        System.out.println(new String(recovered, StandardCharsets.UTF_8));

        // Thay đổi một byte bản mã làm kiểm tra tag thất bại.
        byte[] tampered = ciphertextAndTag.clone();
        tampered[0] ^= 1;
        try {
            Cipher check = Cipher.getInstance("AES/GCM/NoPadding");
            check.init(Cipher.DECRYPT_MODE, dek,
                    new GCMParameterSpec(TAG_BITS, nonce));
            check.updateAAD(aad);
            check.doFinal(tampered);
            throw new IllegalStateException("Tampering was not rejected");
        } catch (AEADBadTagException expected) {
            System.out.println("Rejected modified ciphertext");
        }

        Arrays.fill(plaintext, (byte) 0);
        Arrays.fill(recovered, (byte) 0);
    }
}
~~~

Khi triển khai thực tế, cần chú ý:

- Trong JCA, chuỗi **AES/GCM/NoPadding** là biến thể AES với chế độ GCM; GCM không dùng padding kiểu PKCS#5 như CBC.
- **doFinal** của Java thường trả bản mã kèm tag và sẽ kiểm tra tag khi giải mã. Không tin tưởng hoặc xử lý plaintext trước khi xác thực hoàn tất; đặc biệt thận trọng với thiết kế streaming.
- Nonce phải được tạo **mới cho mỗi lần mã hóa bằng cùng DEK**. Ví dụ tạo nonce ngẫu nhiên, phù hợp để minh họa nhưng **chưa phải bộ quản lý nonce quy mô lớn**.
- **AES-GCM không mã hóa AAD**. Khi khôi phục bản mã phải dùng đúng giá trị AAD và kiểm tra quyền truy cập dựa trên danh tính thật của caller.
- Lệnh xóa mảng chỉ xóa chính các mảng được chỉ định, **không bảo đảm mọi bản sao khóa hoặc plaintext trong JVM đã bị xóa**.
- Khi giải mã thật, xử lý lỗi xác thực bằng việc **từ chối dữ liệu**, đồng thời không làm lộ thông tin nhạy cảm qua thông điệp lỗi, log hoặc phản hồi API.
- Ví dụ giữ khóa ở RAM để dạy cú pháp JCA; bản mã được lưu bền vững cần **key ID, phiên bản, nonce, tag và metadata** để giải mã về sau.

## 6. AES và quản lý khóa: DEK, KEK, KMS/HSM

Trong thiết kế an toàn, cần phân biệt **DEK (Data Encryption Key)** dùng trực tiếp với dữ liệu và **KEK (Key Encryption Key)** dùng bảo vệ DEK. KEK có thể là khóa đối xứng AES được quản lý bởi **KMS**; cách bọc khóa dùng AES-KW/KWP hoặc API wrap/encrypt được nhà cung cấp hỗ trợ.

~~~mermaid
flowchart TB
    APP["Ứng dụng"] --> DEK["Sinh DEK AES cho dữ liệu"]
    DEK --> ENC["AES-GCM: mã hóa dữ liệu"]
    ENC --> C["Ciphertext + nonce + tag"]
    DEK --> WRAP["Wrap DEK"]
    KMS["KMS/HSM giữ KEK"] --> WRAP
    WRAP --> W["Wrapped DEK + key ID"]
    C --> STORE["Lưu bản mã và wrapped DEK"]
    W --> STORE
    STORE --> READ["Yêu cầu đọc có xác thực và phân quyền"]
    READ --> UNWRAP["KMS: unwrap DEK"]
    KMS --> UNWRAP
    UNWRAP --> DEC["AES-GCM: giải mã + kiểm tra tag"]
    STORE --> DEC
~~~

Đây là **envelope encryption**: mã hóa đối xứng xử lý dữ liệu lớn hiệu quả, còn KMS/HSM tập trung bảo vệ KEK, phân quyền và ghi nhật ký sử dụng khóa. Một số hệ thống dùng cơ chế bất đối xứng (ví dụ trao đổi khóa qua ECDH hay mã hóa khóa bằng public key) để cấp phát hoặc bảo vệ khóa AES; điều đó không thay đổi vai trò đối xứng của AES khi mã hóa dữ liệu.

**KMS (Key Management Service)** quản lý vòng đời và API sử dụng khóa. **HSM (Hardware Security Module)** là thiết bị chuyên dụng có cơ chế bảo vệ vật liệu khóa, có thể là thành phần bên trong nền tảng KMS. Một số KEK được đánh dấu **non-exportable** để không xuất key material thô ra ngoài.

Tuy nhiên, **không xuất được KEK không đồng nghĩa an toàn nếu quyền gọi decrypt/unwrap bị cấp quá rộng**. Kẻ tấn công có quyền gọi API unwrap có thể lấy DEK dạng rõ trong một số thiết kế. Vì vậy cần kiểm soát truy cập theo workload/tenant/môi trường, phân tách quyền quản trị với quyền sử dụng khóa và giám sát các lần gọi bất thường.

### 6.1. Dùng AES trực tiếp với mật khẩu có được không?

**Mật khẩu người dùng không phải là khóa AES ngẫu nhiên đủ entropy.** Không lấy UTF-8 của mật khẩu rồi chèn/cắt đủ 16 hoặc 32 byte làm khóa AES. Khi thực sự cần dẫn xuất khóa mã hóa từ mật khẩu, sử dụng **KDF dành cho mật khẩu** được cấu hình phù hợp (ví dụ Argon2id, scrypt hoặc PBKDF2 tùy môi trường và yêu cầu), salt riêng và tham số chi phí được đánh giá.

Với **xác thực đăng nhập**, thông thường cần **lưu giá trị băm mật khẩu chuyên dụng** qua thuật toán xử lý mật khẩu phù hợp, không mã hóa mật khẩu bằng AES để có thể giải mã về sau. Đây là bài toán khác với mã hóa dữ liệu ứng dụng.

## 7. Vòng đời khóa AES

| Giai đoạn | Công việc cần thực hiện | Rủi ro nếu làm sai |
| --- | --- | --- |
| **Tạo khóa** | Sinh bằng **CSPRNG** hoặc KMS/HSM; chọn AES-128/256 theo yêu cầu. | Khóa dự đoán được, dùng cùng một khóa ở nhiều nơi ngoài ý muốn. |
| **Cấp phát** | Đặt key ID, phiên bản, owner, tenant, purpose, môi trường và giới hạn sử dụng. | Dùng nhầm khóa hoặc giải mã chéo tenant. |
| **Lưu trữ** | Bảo vệ DEK bằng KEK/envelope encryption; hạn chế xuất và log; kiểm soát backup. | Lộ DEK/KEK từ repository, cache, dump hoặc kho lưu trữ. |
| **Sử dụng** | AES-GCM với nonce duy nhất theo khóa; xác thực AAD/tag; phân quyền decrypt. | Trùng nonce, bản mã bị sửa đổi hoặc người không có quyền đọc dữ liệu. |
| **Xoay vòng** | Sinh khóa phiên bản mới, chuyển ghi mới, di chuyển dữ liệu cũ khi cần. | Không giải mã được dữ liệu lịch sử hoặc giữ quá lâu khóa bị lộ. |
| **Thu hồi/vô hiệu hóa** | Ngừng dùng khóa cho dữ liệu mới, chặn các API theo chính sách, xử lý DEK trong cache. | Ứng dụng vẫn dùng khóa cũ hoặc tiếp tục giải mã trái phép. |
| **Hủy** | Kiểm kê dữ liệu, backups, replica và mọi bản sao khóa; xác minh điều kiện lưu giữ. | Mất dữ liệu vĩnh viễn hoặc khóa còn có thể khôi phục trái ý định. |

**Xoay KEK** có thể chỉ cần **rewrap DEK** mà không mã hóa lại toàn bộ dữ liệu. Ngược lại, khi **DEK AES thực sự bị lộ**, chỉ thay KEK không bảo vệ được bản mã đã mã hóa bằng DEK đó: cần đánh giá việc thay DEK và mã hóa lại dữ liệu bị ảnh hưởng.

**Crypto-shredding** là chiến lược xóa bằng mật mã thông qua hủy các khóa cần thiết để giải mã. Nó chỉ có hiệu lực khi mọi bản sao DEK/KEK hoặc đường khôi phục khác đều được xử lý và không còn bản rõ ngoài ý muốn. Hủy một KEK dùng chung có thể khiến nhiều nhóm dữ liệu không thể đọc, nên thiết kế phạm vi khóa phù hợp với yêu cầu xóa dữ liệu.

## 8. Thiết kế ví dụ: mã hóa hóa đơn trong hệ thống nhiều tenant

Giả sử hệ thống bán hàng lưu hóa đơn của tenant A và tenant B. Thiết kế đề xuất:

1. Mỗi hóa đơn hoặc nhóm hóa đơn theo chính sách có **DEK AES riêng**, được sinh bằng CSPRNG/KMS.
2. Dữ liệu hóa đơn được mã hóa bằng **AES-256-GCM** và nonce không trùng cho cùng DEK. AAD gồm tenant ID và object ID đã được lấy từ ngữ cảnh có xác thực của ứng dụng.
3. DEK được **wrap dưới KEK phù hợp**, có key ID và phiên bản; bản mã, nonce, tag, wrapped DEK và metadata xác thực được lưu nhất quán.
4. Khi tenant A yêu cầu đọc hóa đơn, API kiểm tra quyền truy cập đúng tenant/object, sau đó chỉ gọi unwrap/decrypt với dữ liệu được phép.
5. KMS ghi log hoạt động wrap/unwrap theo chính sách; ứng dụng ghi nhận truy cập hóa đơn nhưng không ghi DEK/KEK dạng rõ.
6. Khi luân chuyển khóa, ứng dụng hỗ trợ đọc dữ liệu phiên bản cũ trong thời gian chuyển tiếp có kiểm soát. Trước khi hủy khóa cũ, kiểm tra backup và khả năng khôi phục.

**Tình huống lỗi:** Nếu API nhận tùy ý tenant ID từ request và dùng giá trị đó làm AAD mà không xác minh quyền sở hữu, một người dùng có quyền gọi unwrap hoặc có thể chuyển đổi bản ghi có thể tiếp cận dữ liệu tenant khác. Tag AES-GCM vẫn xác thực với AAD phù hợp nhưng **không thay cho phân quyền nghiệp vụ**.

**Tình huống khác:** Nếu hai worker phát hành nonce bằng cùng một bộ đếm được reset về 0 sau mỗi lần restart nhưng vẫn dùng cùng DEK, nguy cơ trùng nonce có thể phá vỡ bảo mật AES-GCM. Cần thiết kế cấp phát nonce hoặc khóa theo worker để tránh trùng lặp, đồng thời bảo đảm tính bền vững qua restart.

## 9. Kiểm soát và kiểm toán khi vận hành AES

Một hệ thống dùng AES an toàn cần kiểm soát không chỉ cách mã hóa mà còn quyền truy cập và khả năng phát hiện sự cố:

- **Phân loại dữ liệu và khóa:** xác định mục đích, độ nhạy cảm, ranh giới tenant, thời hạn lưu và phạm vi chia sẻ DEK/KEK.
- **Quản lý định danh:** cấp quyền encrypt/decrypt/unwrap theo danh tính workload thay vì dùng chung một secret cho mọi dịch vụ.
- **Chính sách sử dụng:** cố định thuật toán/chế độ an toàn, hạn chế số lượt mã hóa theo khóa và tránh trùng nonce.
- **Quản lý metadata:** lưu thuật toán, key ID, phiên bản, nonce, tag và AAD cần thiết; kiểm tra tính toàn vẹn và nguồn gốc metadata.
- **Nhật ký kiểm toán:** lưu actor, thời điểm, key ID, hành động, kết quả và ngữ cảnh phù hợp; không ghi khóa thô, plaintext hay bí mật vào log.
- **Phòng vệ vận hành:** kiểm soát bản sao lưu, phân quyền KMS/HSM, giảm thời gian giữ DEK trong RAM và cảnh báo hành vi unwrap bất thường.
- **Khôi phục và ứng phó sự cố:** duy trì kế hoạch restore, rewrap/re-encrypt, thu hồi/xoay khóa, điều tra ảnh hưởng và chứng minh đã hủy khi cần.

Không nên chỉ kiểm tra việc gọi phương thức mã hóa có thành công hay không. Thiết kế cần chứng minh ứng dụng đang dùng đúng khóa, đúng quyền, đúng ngữ cảnh và không khiến dữ liệu cần giữ mất khả năng khôi phục.

## 10. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Dùng **AES/ECB** cho dữ liệu có cấu trúc | Rò rỉ các mẫu lặp và quan hệ giữa các khối. | Dùng AEAD phù hợp như AES-GCM. |
| Dùng CTR/CBC nhưng không xác thực bản mã | Đầu vào có thể bị thay đổi hoặc khai thác sai cách xử lý lỗi. | Dùng AEAD hoặc giao thức encrypt-then-MAC đúng chuẩn khi có lý do tương thích. |
| Tái sử dụng **nonce GCM với cùng khóa** | Có thể phá vỡ tính bí mật/toàn vẹn. | Thiết kế cấp phát nonce duy nhất, giám sát giới hạn sử dụng khóa. |
| Chọn AES-256 rồi xem như hệ thống đã an toàn | Rủi ro ở khóa, nonce, AAD, phân quyền và vận hành vẫn tồn tại. | Đánh giá giải pháp tổng thể và vòng đời khóa. |
| Hard-code khóa AES trong source/biến môi trường truy cập rộng | Lộ khóa qua Git, image, log hoặc quyền đọc cấu hình. | Dùng KMS/HSM hoặc kho bí mật, phân quyền và xoay khóa khi có sự cố. |
| Tự cắt/đệm mật khẩu thành khóa AES | Khóa yếu, dễ bị đoán hoặc brute force. | Dùng khóa ngẫu nhiên hoặc KDF chuyên dụng đúng mục đích. |
| Không lưu key ID, nonce, tag, AAD cần thiết | Dữ liệu không giải mã được hoặc bị gắn sai ngữ cảnh. | Định nghĩa envelope/định dạng bản ghi có phiên bản. |
| Chỉ rotate KEK khi DEK đã bị lộ | Bản mã cũ vẫn mở được bằng DEK lộ. | Đánh giá re-encrypt dữ liệu bằng DEK mới. |
| Tin rằng có GCM tag là đủ chống phát lại | Bản mã hợp lệ cũ có thể được chấp nhận nhiều lần. | Thêm sequence number, thời hạn và kiểm tra replay theo nghiệp vụ. |
| Xóa KEK trước khi di chuyển wrapped DEK/backup | Dữ liệu trở nên không thể khôi phục. | Kiểm kê phụ thuộc, thử restore và chỉ hủy sau khi đáp ứng điều kiện lưu giữ. |

## 11. Câu hỏi tự kiểm tra

1. AES-128 và AES-256 khác nhau về điều gì? Kích thước khối AES có thay đổi không?
2. Vì sao sử dụng AES-ECB để mã hóa một ảnh hoặc nhiều bản ghi giống nhau là không an toàn?
3. AES-GCM cần lưu những thành phần nào cùng bản mã để giải mã và kiểm tra xác thực?
4. Khi một hệ thống có nhiều worker cùng mã hóa bằng một DEK, có những cách nào để bảo đảm nonce không trùng?
5. AAD có được mã hóa không? Có thể xem AAD/tag là cơ chế phân quyền tenant thay thế cho ACL hay không?
6. Khác biệt thực tế giữa xoay KEK, rewrap DEK và thay DEK là gì?
7. Khi DEK AES bị lộ, những dữ liệu nào có khả năng bị ảnh hưởng và việc thay KEK đã đủ chưa?

**Ghi nhớ:** AES là primitive đối xứng mạnh và hiệu quả, nhưng bảo mật ứng dụng phụ thuộc vào **chế độ đúng, nonce đúng, xác thực bản mã, khóa bí mật được bảo vệ, phân quyền và kiểm toán**. Dùng AES-GCM để bảo vệ dữ liệu, kết hợp DEK/KEK và KMS/HSM khi phù hợp, đồng thời thiết kế ngay từ đầu đường xoay vòng, thu hồi, khôi phục và hủy khóa.
