# Mã hóa bằng AES-GCM

Trong bài thực hành này, bạn sẽ xây dựng một thành phần Java mã hóa và giải mã dữ liệu bằng AES-GCM, lưu nonce cùng ciphertext, ràng buộc bản mã với metadata bằng Associated Data (AAD), rồi kiểm tra hệ thống từ chối dữ liệu bị sửa hoặc dùng sai ngữ cảnh. Bài tập mô phỏng việc bảo vệ một trường dữ liệu khách hàng trong ứng dụng có quản lý khóa.

AES-GCM là chế độ authenticated encryption: ngoài tính bí mật, nó còn xác minh tính toàn vẹn và xác thực của ciphertext cùng AAD. Khi tag không hợp lệ, thao tác giải mã phải thất bại và ứng dụng không được sử dụng plaintext. Trong hệ thống thực tế, an toàn của AES-GCM còn phụ thuộc vào việc quản lý nonce, bảo vệ key material, phân quyền, rotation, backup và cách tích hợp KMS/HSM.

## 1. Kết quả cần đạt

Hoàn thành bài thực hành, bạn sẽ:

- Tạo AES key bằng KeyGenerator và SecureRandom.
- Mã hóa, giải mã bằng AES/GCM/NoPadding.
- Sử dụng nonce 96 bit và authentication tag 128 bit.
- Lưu nonce, định dạng payload và ciphertext theo một cấu trúc có phiên bản.
- Ràng buộc ciphertext với tenant và record bằng AAD.
- Kiểm tra round-trip, tampering, sai AAD và payload lỗi định dạng.
- Thực hiện thử nghiệm rotation với hai key version.
- Giải thích cách chuyển từ key trong bộ nhớ của lab sang KMS/HSM và envelope encryption.

## 2. Bối cảnh bài tập

Bạn đang xây dựng chức năng lưu số định danh của khách hàng. Database không được lưu plaintext của trường này. Ứng dụng cần mã hóa trước khi ghi và giải mã khi một principal đã được phép đọc bản ghi.

Mỗi bản ghi có:

- tenantId: định danh tenant sở hữu dữ liệu.
- recordId: định danh bản ghi.
- schemaVersion: phiên bản cấu trúc dữ liệu.
- ciphertext: dữ liệu đã mã hóa cùng authentication tag.
- nonce: tham số duy nhất cho lần mã hóa với key đó.
- keyId và keyVersion: tham chiếu đến khóa dùng để mã hóa.
- algorithm: thuật toán và format payload.

Ứng dụng sẽ đưa tenantId, recordId và schemaVersion vào AAD. Nhờ đó, ciphertext được tạo cho một bản ghi không thể được chuyển sang tenant hoặc record khác rồi giải mã thành công bằng AAD khác.

## 3. Yêu cầu môi trường

- JDK 17 trở lên.
- Java Cryptography Architecture (JCA) có sẵn trong JDK.
- IDE hoặc terminal có thể chạy javac và java.
- Không cần thư viện bên ngoài.

Trong lab, key được sinh và giữ trong bộ nhớ của một tiến trình để tập trung vào API AES-GCM. Key này mất khi tiến trình kết thúc. Đây là cách làm dành riêng cho bài thực hành; không dùng cách lưu key trong bộ nhớ hoặc sinh key mới mỗi lần khởi động làm cơ chế quản lý khóa production.

## 4. Khái niệm cần nắm trước khi làm

### 4.1. AES key

AES là thuật toán mã hóa đối xứng. Cùng một secret key được dùng ở bước encrypt và decrypt. Bài lab dùng AES-256; môi trường Java hiện đại thường hỗ trợ độ dài này. Nếu provider hoặc policy của môi trường giới hạn độ dài khóa, hãy dùng cấu hình được phê duyệt và ghi rõ thay đổi.

### 4.2. GCM nonce

Nonce là giá trị đầu vào cho mỗi lần mã hóa. Với GCM, bài lab dùng nonce 96 bit (12 byte), được tạo bằng SecureRandom. Nonce không cần giữ bí mật và phải được lưu cùng ciphertext.

**Không bao giờ tái sử dụng cùng nonce với cùng một AES-GCM key.** Việc tái sử dụng có thể phá vỡ tính bí mật và cho phép giả mạo tag. Trong ứng dụng phân tán hoặc có lưu lượng lớn, cần một chiến lược bảo đảm nonce không lặp trên toàn bộ consumer dùng chung key; việc gọi SecureRandom riêng lẻ không tự chứng minh rằng thiết kế ở mọi quy mô đã an toàn.

### 4.3. Authentication tag

GCM tạo tag xác thực. Lab dùng tag 128 bit. Java provider ghép tag vào kết quả doFinal() trong payload ciphertext. Khi decrypt, provider xác minh tag trước khi trả plaintext.

### 4.4. Associated Data (AAD)

AAD là dữ liệu được xác thực nhưng không được mã hóa. AAD phù hợp với metadata cần ràng buộc vào ciphertext, chẳng hạn tenant ID, record ID hoặc schema version. Khi decrypt, phải cung cấp chính xác cùng AAD bytes đã dùng lúc encrypt.

AAD không thay thế authorization. Ứng dụng vẫn phải xác minh principal có quyền đọc record trước khi yêu cầu giải mã.

## 5. Cấu trúc payload

Để người nhận biết cách đọc dữ liệu, bài lab định nghĩa payload nhị phân như sau:

| Thành phần | Kích thước | Mô tả |
|---|---:|---|
| Magic | 4 byte | Chuỗi AGCM để nhận diện format |
| Format version | 1 byte | Phiên bản cấu trúc payload, hiện tại là 1 |
| Nonce | 12 byte | Nonce GCM |
| Ciphertext và tag | Thay đổi | Ciphertext nối với tag 128 bit do JCA tạo |

keyId, keyVersion, tenant và record ID được lưu trong metadata của record hoặc envelope bên ngoài payload. Không lưu key material trong payload. Khi đọc, ứng dụng phải lấy key reference từ metadata được kiểm soát và kiểm tra nó theo policy.

Việc có format version cho phép nâng cấp định dạng sau này mà không phải đoán cách parse từ độ dài hoặc nội dung ciphertext.

## 6. Tạo project và file Java

Tạo thư mục thực hành, sau đó tạo file:

~~~text
aes-gcm-lab/
└── AesGcmLab.java
~~~

Toàn bộ code mẫu dưới đây có thể chạy độc lập bằng JDK. Hãy nhập code vào AesGcmLab.java.

## 7. Code hoàn chỉnh: AES-GCM encrypt/decrypt

~~~java
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;

public final class AesGcmLab {
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final byte[] MAGIC = {
        (byte) 'A', (byte) 'G', (byte) 'C', (byte) 'M'
    };
    private static final byte FORMAT_VERSION = 1;
    private static final int NONCE_LENGTH_BYTES = 12;
    private static final int TAG_LENGTH_BITS = 128;
    private static final int TAG_LENGTH_BYTES = TAG_LENGTH_BITS / 8;

    private static final SecureRandom RANDOM = new SecureRandom();

    private AesGcmLab() {
    }

    public static SecretKey generateKey() throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RANDOM);
        return generator.generateKey();
    }

    public static byte[] buildAad(
            String tenantId,
            String recordId,
            int schemaVersion) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }
        if (recordId == null || recordId.isBlank()) {
            throw new IllegalArgumentException("recordId is required");
        }
        if (schemaVersion < 1) {
            throw new IllegalArgumentException("schemaVersion must be positive");
        }

        byte[] tenant = tenantId.getBytes(StandardCharsets.UTF_8);
        byte[] record = recordId.getBytes(StandardCharsets.UTF_8);

        // Length-prefix each field so different values cannot form
        // an ambiguous concatenated representation.
        ByteBuffer buffer = ByteBuffer.allocate(
            Integer.BYTES + tenant.length
                + Integer.BYTES + record.length
                + Integer.BYTES
        );
        buffer.putInt(tenant.length);
        buffer.put(tenant);
        buffer.putInt(record.length);
        buffer.put(record);
        buffer.putInt(schemaVersion);
        return buffer.array();
    }

    public static byte[] encrypt(
            SecretKey key,
            byte[] plaintext,
            byte[] aad) throws GeneralSecurityException {
        if (key == null || plaintext == null || aad == null) {
            throw new IllegalArgumentException("key, plaintext and aad are required");
        }

        byte[] nonce = new byte[NONCE_LENGTH_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(
            Cipher.ENCRYPT_MODE,
            key,
            new GCMParameterSpec(TAG_LENGTH_BITS, nonce)
        );
        cipher.updateAAD(aad);
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        ByteBuffer payload = ByteBuffer.allocate(
            MAGIC.length + 1 + NONCE_LENGTH_BYTES + ciphertextAndTag.length
        );
        payload.put(MAGIC);
        payload.put(FORMAT_VERSION);
        payload.put(nonce);
        payload.put(ciphertextAndTag);
        return payload.array();
    }

    public static byte[] decrypt(
            SecretKey key,
            byte[] payload,
            byte[] aad) throws GeneralSecurityException {
        if (key == null || payload == null || aad == null) {
            throw new IllegalArgumentException("key, payload and aad are required");
        }

        int minimumLength =
            MAGIC.length + 1 + NONCE_LENGTH_BYTES + TAG_LENGTH_BYTES;
        if (payload.length < minimumLength) {
            throw new GeneralSecurityException("Invalid encrypted payload length");
        }

        ByteBuffer input = ByteBuffer.wrap(payload);
        byte[] magic = new byte[MAGIC.length];
        input.get(magic);
        if (!Arrays.equals(MAGIC, magic)) {
            throw new GeneralSecurityException("Unsupported payload format");
        }

        byte version = input.get();
        if (version != FORMAT_VERSION) {
            throw new GeneralSecurityException("Unsupported payload version");
        }

        byte[] nonce = new byte[NONCE_LENGTH_BYTES];
        input.get(nonce);

        byte[] ciphertextAndTag = new byte[input.remaining()];
        input.get(ciphertextAndTag);

        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(
            Cipher.DECRYPT_MODE,
            key,
            new GCMParameterSpec(TAG_LENGTH_BITS, nonce)
        );
        cipher.updateAAD(aad);

        // doFinal verifies the GCM authentication tag.
        // On failure it throws AEADBadTagException and returns no plaintext.
        return cipher.doFinal(ciphertextAndTag);
    }

    public static void main(String[] args) throws Exception {
        SecretKey key = generateKey();

        String tenantId = "tenant-42";
        String recordId = "customer-1007";
        int schemaVersion = 1;

        byte[] aad = buildAad(tenantId, recordId, schemaVersion);
        byte[] plaintext =
            "Customer identifier: CUST-0001007".getBytes(StandardCharsets.UTF_8);

        byte[] encrypted = encrypt(key, plaintext, aad);
        byte[] decrypted = decrypt(key, encrypted, aad);

        System.out.println("Payload bytes: " + encrypted.length);
        System.out.println(
            "Round-trip: "
                + Arrays.equals(plaintext, decrypted)
        );

        byte[] tampered = Arrays.copyOf(encrypted, encrypted.length);
        tampered[tampered.length - 1] ^= 0x01;
        try {
            decrypt(key, tampered, aad);
            throw new AssertionError("Tampered payload was accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("Tampered payload: rejected (PASS)");
        }

        byte[] wrongAad = buildAad("tenant-99", recordId, schemaVersion);
        try {
            decrypt(key, encrypted, wrongAad);
            throw new AssertionError("Payload with wrong AAD was accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("Wrong AAD: rejected (PASS)");
        }

        byte[] truncated = Arrays.copyOf(encrypted, 8);
        try {
            decrypt(key, truncated, aad);
            throw new AssertionError("Truncated payload was accepted");
        } catch (GeneralSecurityException expected) {
            System.out.println("Truncated payload: rejected (PASS)");
        }
    }
}
~~~

## 8. Chạy chương trình

Mở terminal trong thư mục chứa file:

~~~bash
javac AesGcmLab.java
java AesGcmLab
~~~

Kết quả dự kiến có dạng:

~~~text
Payload bytes:  ...
Round-trip: true
Tampered payload: rejected (PASS)
Wrong AAD: rejected (PASS)
Truncated payload: rejected (PASS)
~~~

Độ dài payload phụ thuộc plaintext. Chương trình không in key, nonce riêng hoặc plaintext sau giải mã ra log. Round-trip: true cho biết plaintext khôi phục giống dữ liệu ban đầu; ba trường hợp tiếp theo cho thấy dữ liệu sửa đổi, AAD sai và payload bị cắt đều bị từ chối.

## 9. Đọc hiểu luồng mã hóa

Hàm generateKey() dùng KeyGenerator để tạo AES key. Ứng dụng production nên yêu cầu KMS/HSM hoặc key provider được phê duyệt tạo và quản lý key; đoạn lab chỉ tạo key trong bộ nhớ.

Trong encrypt():

1. Sinh nonce 12 byte.
2. Lấy Cipher với transformation AES/GCM/NoPadding.
3. Khởi tạo cipher ở chế độ ENCRYPT_MODE với key, nonce và tag length.
4. Gọi updateAAD() trước doFinal().
5. Nhận ciphertext nối với authentication tag.
6. Đóng gói magic, format version, nonce và ciphertext/tag.

Nonce được lưu cùng payload vì decrypt cần đúng nonce đã dùng lúc encrypt. Nonce không phải bí mật, nhưng không được thay đổi hoặc tái sử dụng với cùng key.

## 10. Đọc hiểu luồng giải mã

Trong decrypt():

1. Kiểm tra payload có đủ độ dài tối thiểu cho header, nonce và tag.
2. Kiểm tra magic và format version.
3. Tách nonce khỏi phần ciphertext/tag.
4. Khởi tạo cipher ở DECRYPT_MODE với cùng key và nonce.
5. Cung cấp đúng AAD bytes.
6. Gọi doFinal() để xác minh tag và chỉ trả plaintext khi xác minh thành công.

Nếu ciphertext, tag, nonce hoặc AAD bị thay đổi, provider sẽ ném AEADBadTagException trong trường hợp xác thực thất bại. Ứng dụng không được bắt lỗi rồi tiếp tục sử dụng dữ liệu chưa xác thực.

## 11. Vì sao AAD cần encoding không nhập nhằng?

Nếu ghép chuỗi bằng dấu phân cách mà không có quy tắc escaping, các bộ giá trị khác nhau có thể tạo cùng một chuỗi. Ví dụ ("ab", "c") và ("a", "bc") đều có thể trở thành abc khi nối trực tiếp.

Lab dùng length-prefix cho tenant và record, sau đó ghi schema version dưới dạng integer. Cách này tạo biểu diễn byte xác định. Producer và consumer phải dùng cùng encoding, cùng thứ tự trường và cùng phiên bản schema.

Trong hệ thống thực tế, hãy định nghĩa AAD schema rõ ràng và có version. Không đưa password, số tài khoản hoặc dữ liệu cá nhân vào AAD vì AAD không được mã hóa.

## 12. Bài tập 1: kiểm tra round-trip

**Nhiệm vụ:** thay plaintext trong main() bằng ba chuỗi có độ dài khác nhau, gồm chuỗi rỗng, chuỗi ngắn và chuỗi Unicode tiếng Việt.

**Yêu cầu:**

- Cả ba trường hợp encrypt/decrypt đều thành công.
- Plaintext sau decrypt phải bằng chính xác dữ liệu đầu vào.
- Không so sánh ciphertext giữa hai lần encrypt để kết luận lỗi nếu chúng khác nhau; nonce khác nhau khiến ciphertext khác nhau là bình thường.

**Câu hỏi:** Vì sao cùng một plaintext, key và AAD có thể tạo ciphertext khác nhau ở hai lần gọi?

## 13. Bài tập 2: kiểm tra tampering

**Nhiệm vụ:** tạo các bản sao payload và lần lượt sửa:

- Một byte trong nonce.
- Một byte ở phần ciphertext.
- Một byte ở authentication tag.
- Một byte trong AAD.

**Kết quả mong đợi:** decrypt thất bại ở từng trường hợp. Không có plaintext hợp lệ được trả về.

Gợi ý: với payload format của lab, nonce bắt đầu ngay sau 5 byte header; phần ciphertext/tag bắt đầu sau header và nonce. Không sửa trực tiếp payload gốc vì cần dùng lại payload hợp lệ cho các test tiếp theo.

## 14. Bài tập 3: kiểm tra metadata binding

**Nhiệm vụ:** mã hóa một record với AAD tạo từ:

~~~text
tenantId = tenant-42
recordId = customer-1007
schemaVersion = 1
~~~

Sau đó thử giải mã bằng từng biến thể:

| Thay đổi | Kết quả mong đợi |
|---|---|
| Đổi tenant thành tenant-99 | Authentication failure |
| Đổi record ID | Authentication failure |
| Đổi schema version | Authentication failure |
| Dùng đúng cả ba trường | Decrypt thành công |

**Câu hỏi:** AAD có ngăn được người dùng trái phép gọi API decrypt không? Vì sao ứng dụng vẫn cần authorization trước khi giải mã?

## 15. Bài tập 4: kiểm tra payload format

**Nhiệm vụ:** tạo các payload lỗi:

- Header magic không phải AGCM.
- Format version không được hỗ trợ.
- Payload ngắn hơn kích thước tối thiểu.
- Payload bị cắt ở phần ciphertext/tag.

**Kết quả mong đợi:** ứng dụng từ chối payload lỗi định dạng hoặc lỗi xác thực. Không tự đoán format và không thử một thuật toán khác như fallback.

**Mở rộng:** bổ sung một format version mới trong thiết kế giả định. Viết parser từ chối version chưa được hỗ trợ và nêu cách triển khai migration tương thích.

## 16. Bài tập 5: mô phỏng key rotation

Trong lab, tạo hai key độc lập keyV1 và keyV2:

1. Mã hóa record A bằng keyV1.
2. Tạo keyV2 và đánh dấu nó là current version trong metadata test.
3. Mã hóa record B bằng keyV2.
4. Đọc record A bằng keyV1.
5. Đọc record B bằng keyV2.
6. Thử đọc record A bằng keyV2; kết quả phải thất bại xác thực.

Mỗi record phải lưu keyId và keyVersion tương ứng. Không thử lần lượt mọi key để tìm key có thể giải mã. Ứng dụng phải lấy đúng key theo metadata đã được xác thực và policy cho phép.

**Câu hỏi:** Vì sao không nên xóa keyV1 ngay sau khi keyV2 trở thành current version?

## 17. Bài tập 6: kiểm tra xử lý lỗi

**Nhiệm vụ:** bọc lời gọi decrypt trong service layer và định nghĩa cách xử lý:

- AEADBadTagException: payload hoặc AAD không xác thực được.
- GeneralSecurityException: lỗi provider, key hoặc format.
- Authorization denied: principal không được phép đọc record.
- Key unavailable: key version cần thiết không còn truy cập được.

**Yêu cầu:**

- Không trả plaintext khi tag thất bại.
- Không ghi plaintext, key bytes hoặc secret vào log.
- Log request ID, record ID không nhạy cảm, key ID/version và error category nếu policy cho phép.
- Không biến mọi lỗi thành kết quả dữ liệu rỗng vì sẽ che giấu lỗi bảo mật và lỗi vận hành.
- Thông báo ra client không tiết lộ chi tiết giúp dò đoán trạng thái key hoặc dữ liệu.

## 18. Bài tập 7: thiết kế metadata record

Thiết kế record lưu ciphertext trong database với các trường:

| Field | Ví dụ | Ghi chú |
|---|---|---|
| formatVersion | 1 | Version của payload |
| algorithm | AES/GCM/NoPadding | Chọn từ allowlist |
| keyId | customer-data-key | Logical key reference |
| keyVersion | v3 | Version đã encrypt record |
| nonce | 12 byte | Có thể nằm trong payload lab |
| ciphertextAndTag | byte array | Không chứa plaintext |
| aadSchemaVersion | 1 | Cách tạo AAD |
| tenantId | tenant-42 | Dùng để tái tạo AAD và phân quyền |
| recordId | customer-1007 | Dùng để tái tạo AAD |

Xác định trường nào được phép nằm trong database, trường nào là secret và trường nào phải được xác minh từ nguồn tin cậy. keyId và keyVersion không phải key material nhưng vẫn phải được kiểm tra; không để client tùy ý chọn một key khác nhằm vượt qua phạm vi phân quyền.

## 19. Bài tập 8: mở rộng sang envelope encryption

Trong ứng dụng thực tế, thay vì lưu AES key trong tiến trình hoặc file cấu hình, bạn có thể dùng envelope encryption:

1. Workload xác thực với KMS bằng workload identity.
2. KMS tạo DEK hoặc cấp DEK theo API được hỗ trợ.
3. KMS trả plaintext DEK cho workload trong thời gian cần thiết và encrypted DEK được bọc bởi KEK.
4. Workload dùng plaintext DEK trong bộ nhớ để encrypt dữ liệu bằng AES-GCM.
5. Database lưu ciphertext, nonce, AAD metadata và encrypted DEK.
6. Khi đọc, workload yêu cầu KMS unwrap DEK theo quyền được cấp.
7. Workload xác minh GCM tag và AAD trước khi dùng plaintext.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant KMS as KMS
    participant DB as Database
    App->>KMS: GenerateDataKey (workload identity)
    KMS-->>App: Plaintext DEK + encrypted DEK
    App->>App: AES-GCM encrypt with AAD
    App->>DB: Store ciphertext, nonce, encrypted DEK, key reference
    DB-->>App: Encrypted record
    App->>KMS: Decrypt/Unwrap encrypted DEK
    KMS-->>App: Plaintext DEK
    App->>App: AES-GCM verify tag and decrypt
~~~

Plaintext DEK chỉ nên tồn tại trong bộ nhớ cần thiết, không ghi log và được giải phóng theo khả năng của runtime. Xóa byte array không bảo đảm mọi bản sao trong heap đã biến mất do garbage collection và tối ưu hóa runtime; giảm thời gian tồn tại và hạn chế dump vẫn rất quan trọng.

## 20. Bài tập 9: thiết kế quyền truy cập

Đề xuất quyền cho ba principal:

| Principal | Nhu cầu | Quyền đề xuất |
|---|---|---|
| customer-writer | Mã hóa record mới | Chỉ thao tác encrypt hoặc lấy DEK trong phạm vi customer data |
| customer-reader | Đọc record được phép | Chỉ thao tác unwrap/decrypt trong scope được giao |
| key-auditor | Kiểm tra hoạt động | Đọc metadata, policy và audit event; không decrypt hoặc export |

Kiểm tra negative case:

- customer-writer không được export key hoặc sửa policy.
- customer-reader không được tạo, rotate hoặc destroy key.
- key-auditor không được gọi encrypt/decrypt/sign.
- Workload tenant A không truy cập được key hoặc record của tenant B.

AAD giúp phát hiện việc chuyển ciphertext sang context khác, nhưng kiểm soát quyền vẫn phải được thực hiện ở tầng ứng dụng và KMS.

## 21. Bài tập 10: kiểm tra nonce strategy

Chạy thử tạo nhiều payload và thu thập nonce để quan sát cách chương trình sinh giá trị. Có thể tạm viết hàm tách nonce từ payload và đếm số giá trị khác nhau trong một tập nhỏ.

**Lưu ý:** không xuất hiện nonce trùng trong một test nhỏ không phải bằng chứng toán học rằng hệ thống production không thể trùng nonce. Với GCM, phải bảo đảm nonce uniqueness cho mỗi key trên toàn bộ các process dùng key đó. Cần đánh giá tổng số lần mã hóa, cách chia sẻ key, cơ chế cấp nonce, restart/restore và khả năng nhiều vùng cùng hoạt động.

Trong hệ thống tải lớn, cân nhắc bộ đếm duy nhất có phân vùng, nonce allocation service hoặc rotation key theo giới hạn sử dụng. Mọi chiến lược phải tránh reset counter khi restore backup hoặc khởi động lại nếu điều đó có thể làm nonce lặp.

## 22. Test matrix

| ID | Kịch bản | Kết quả mong đợi |
|---|---|---|
| GCM-01 | Encrypt rồi decrypt với key/AAD đúng | Plaintext khớp dữ liệu đầu vào |
| GCM-02 | Plaintext rỗng | Round-trip thành công |
| GCM-03 | Plaintext Unicode | Round-trip giữ nguyên UTF-8 |
| GCM-04 | Sửa ciphertext | Authentication failure |
| GCM-05 | Sửa authentication tag | Authentication failure |
| GCM-06 | Sửa nonce | Authentication failure |
| GCM-07 | Dùng AAD khác | Authentication failure |
| GCM-08 | Sai magic header | Từ chối format |
| GCM-09 | Format version không hỗ trợ | Từ chối format |
| GCM-10 | Payload quá ngắn | Từ chối payload |
| GCM-11 | Dùng key version sai | Authentication failure |
| GCM-12 | Rotation v1 sang v2 | Dữ liệu cũ và mới đọc bằng đúng version |
| GCM-13 | Principal không có quyền | Authorization denied |
| GCM-14 | Key provider timeout | Lỗi được phân loại, không fallback yếu |
| GCM-15 | Kiểm tra log | Không có plaintext hoặc key material |

## 23. Tiêu chí hoàn thành bài thực hành

- [ ] Chương trình Java compile và chạy được.
- [ ] Key được tạo bằng KeyGenerator và SecureRandom.
- [ ] Cipher transformation là AES/GCM/NoPadding.
- [ ] Nonce dài 12 byte và được lưu cùng payload.
- [ ] Tag dài 128 bit và được xác minh khi decrypt.
- [ ] AAD được tạo theo encoding ổn định và dùng giống nhau ở hai chiều.
- [ ] Tampering, sai AAD và payload lỗi đều bị từ chối.
- [ ] Không có plaintext hoặc key material trong log.
- [ ] Metadata chỉ ra đúng key ID/version.
- [ ] Rotation test vẫn đọc được dữ liệu cũ và ghi mới bằng key mới.
- [ ] Đã giải thích giới hạn của key trong bộ nhớ và hướng chuyển sang KMS/HSM.
- [ ] Đã nêu chiến lược nonce cho môi trường nhiều process hoặc tải lớn.

## 24. Câu hỏi tự đánh giá

1. AES-GCM cung cấp những thuộc tính bảo mật nào?
2. Vì sao nonce có thể lưu công khai nhưng không được tái sử dụng với cùng key?
3. Authentication tag được xác minh ở bước nào trong JCA?
4. AAD khác ciphertext như thế nào?
5. Vì sao phải ràng buộc tenant ID và record ID vào AAD?
6. Nếu tag không hợp lệ, ứng dụng phải xử lý plaintext thế nào?
7. Vì sao key ID và key version cần được lưu cùng encrypted record?
8. Khi KEK rotation trong envelope encryption, lúc nào rewrap là đủ?
9. Khi DEK bị lộ, vì sao chỉ rewrap encrypted DEK không đủ?
10. Vì sao một key được sinh trong bộ nhớ của lab không phải cơ chế lưu khóa production?

## 25. Gợi ý đáp án

1. AES-GCM cung cấp confidentiality và xác thực toàn vẹn của ciphertext cùng AAD.
2. Nonce không cần bí mật, nhưng GCM yêu cầu nonce duy nhất với cùng key; tái sử dụng có thể làm suy yếu nghiêm trọng cả confidentiality và authenticity.
3. Provider xác minh tag trong Cipher.doFinal() khi decrypt; lỗi thường được biểu diễn bằng AEADBadTagException.
4. Ciphertext được mã hóa; AAD được xác thực nhưng vẫn ở dạng đọc được.
5. AAD ràng buộc ciphertext với tenant/record cụ thể và phát hiện việc chuyển ciphertext sang context khác.
6. Không trả hoặc sử dụng plaintext; từ chối dữ liệu và ghi nhận lỗi theo cách không làm lộ secret.
7. Ứng dụng cần chọn đúng key version để giải mã dữ liệu lịch sử và tránh thử mọi khóa.
8. Rewrap đủ khi DEK vẫn được đánh giá an toàn và chỉ cần thay KEK bảo vệ DEK.
9. DEK bị lộ nghĩa là ciphertext đã mã hóa bằng DEK đó có thể bị giải mã; cần DEK mới và re-encrypt dữ liệu nếu muốn bảo vệ lại ciphertext.
10. Key trong bộ nhớ biến mất khi process kết thúc, không có lifecycle, access control, backup, rotation hay audit đầy đủ.

## 26. Mở rộng sau bài lab

Sau khi hoàn thành phần cơ bản, có thể mở rộng theo các hướng:

- Tách AesGcmLab thành AeadEncryptor, PayloadCodec và KeyProvider.
- Viết JUnit tests cho round-trip, tampering, malformed payload và AAD mismatch.
- Thêm metadata keyId, keyVersion, algorithm và aadSchemaVersion.
- Dùng test KMS project để thay generateKey() bằng thao tác lấy DEK được quản lý.
- Thêm encrypted DEK và thực hiện KEK rewrap.
- Thêm migration worker để re-encrypt dữ liệu theo batch, checkpoint và retry.
- Thêm audit event gồm principal, operation, key ID/version, request ID và outcome.
- Đo latency và throughput khi mã hóa nhiều record.

Khi mở rộng, vẫn giữ các invariant: không ghi secret vào log, không bỏ qua tag failure, không tái sử dụng nonce với cùng key và không destroy key version còn cần cho dữ liệu hoặc backup.

## Kết luận

Qua bài thực hành, bạn đã xây dựng luồng AES-GCM có nonce, authentication tag, payload format version và AAD gắn với tenant/record. Các test tampering và AAD mismatch chứng minh dữ liệu bị sửa hoặc đặt sai ngữ cảnh sẽ bị từ chối trước khi plaintext được sử dụng. Tuy nhiên, một hàm encrypt/decrypt đúng chưa tạo thành hệ thống quản lý khóa hoàn chỉnh. Ứng dụng cần lưu key ID/version, kiểm soát principal, bảo vệ key material, có chiến lược nonce duy nhất, rotation, backup, audit và phục hồi. Trong production, hãy chuyển việc tạo và bảo vệ khóa sang KMS/HSM hoặc key provider được phê duyệt, đồng thời dùng envelope encryption khi phù hợp để tách DEK khỏi KEK.
