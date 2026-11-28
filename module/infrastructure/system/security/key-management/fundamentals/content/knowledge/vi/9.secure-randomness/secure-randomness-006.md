# Random IV — Vector khởi tạo ngẫu nhiên trong mật mã

## 1. Random IV là gì?

**Initialization Vector (IV)** là một giá trị đầu vào bổ sung cho **thuật toán và chế độ mã hóa (mode of operation)**. IV giúp các lần mã hóa được tách biệt với nhau ngay cả khi sử dụng cùng một khóa bí mật. **Random IV** là IV được sinh bằng nguồn ngẫu nhiên phù hợp với yêu cầu mật mã, thường là **Cryptographically Secure Pseudorandom Number Generator (CSPRNG)**.

Ví dụ, hệ thống Java mã hóa hai hồ sơ có cùng nội dung bằng **AES-GCM** và cùng một **Data Encryption Key (DEK)**. Khi sử dụng hai IV/nonce hợp lệ khác nhau, hệ thống tạo ra hai bản mã khác nhau và tránh việc sử dụng lại cùng một trạng thái mã hóa.

Tuy nhiên, **“IV ngẫu nhiên” không có nghĩa “IV chắc chắn duy nhất”**. Hai lần sinh ngẫu nhiên độc lập vẫn có một xác suất trùng. Tùy mode, yêu cầu có thể là **không đoán trước được**, **duy nhất dưới cùng khóa**, hoặc cả hai. Do đó, không thể áp dụng một quy tắc IV chung cho mọi thuật toán.

Trong chương **Secure randomness** của học phần **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, việc chọn, tạo và quản lý IV là phần không thể tách rời của việc bảo vệ khóa trong suốt vòng đời: **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy**. Một khóa AES dài 256 bit vẫn có thể bị sử dụng không an toàn nếu IV/nonce được tạo sai, bất kể khóa được giữ trong **KMS/HSM** hay được bọc bằng **envelope encryption**.

> **Ý chính:** IV thường không phải bí mật. Điều cần bảo đảm là **đúng kích thước, đúng quy tắc ngẫu nhiên/duy nhất của mode và không lặp lại trạng thái mã hóa nguy hiểm dưới cùng khóa**.

## 2. Phân biệt IV, nonce, khóa, salt và authentication tag

Các thuật ngữ này thường xuất hiện cạnh nhau nhưng đảm nhận vai trò khác nhau.

| Thành phần | Vai trò | Có cần bí mật không? | Yêu cầu điển hình |
| --- | --- | --- | --- |
| **Encryption key / DEK** | Bí mật quyết định mã hóa và giải mã | **Có** | Sinh đủ entropy, bảo vệ bằng KMS/HSM hoặc cơ chế tương ứng |
| **IV** | Khởi tạo trạng thái của một chế độ mã hóa | Thường **không** | Phụ thuộc mode: ngẫu nhiên khó đoán hoặc duy nhất |
| **Nonce** | Giá trị dùng một lần theo phạm vi khóa/giao thức | Thường **không** | Không tái sử dụng khi thuật toán yêu cầu uniqueness |
| **Salt** | Giá trị phân biệt các đầu vào KDF/password hashing | **Không** trong trường hợp thông thường | Sinh ngẫu nhiên hoặc theo yêu cầu KDF; khác IV |
| **Authentication tag** | Kiểm tra ciphertext và AAD trong AEAD | **Không** | Phải được xác minh trước khi chấp nhận bản rõ |
| **AAD** | Ngữ cảnh được xác thực nhưng không mã hóa bởi AEAD | **Không được che giấu** | Ràng buộc bản mã với đúng tenant, record hoặc purpose |

**IV và nonce có thể được dùng gần như thay thế nhau trong tài liệu một số mode**, nhưng không phải mọi IV đều có cùng quy tắc. Cần đọc định nghĩa của chế độ và API cụ thể.

Trong **AES-GCM**:

- **AES-256** cho biết khóa dài **256 bit = 32 byte**.
- **IV/nonce 96 bit = 12 byte** là kích thước được dùng phổ biến và có xử lý thuận lợi trong GCM.
- **Tag 128 bit = 16 byte** là lựa chọn xác thực phổ biến.
- **Block size của AES** luôn là **128 bit = 16 byte**, không phụ thuộc AES-128 hay AES-256.

Ba con số **256 / 96 / 128 bit** trong cùng một cấu hình AES-256-GCM không thay thế được cho nhau. Tăng key size không sửa được lỗi lặp nonce.

### 2.1. IV có phải một secret không?

Đối với AES-CBC, AES-GCM và nhiều cơ chế thông dụng, **IV không cần giữ bí mật**. Nó có thể nằm cạnh ciphertext trong cơ sở dữ liệu hoặc thông điệp truyền đi. Nhưng IV phải được **ràng buộc đúng với ciphertext, key ID và ngữ cảnh** theo thiết kế.

Nếu một ứng dụng lưu IV trong file cấu hình và dùng mãi cho mọi bản ghi, việc “giữ kín IV” không biến cách sử dụng đó thành an toàn. Ngược lại, công khai IV được tạo đúng cách thường hoàn toàn phù hợp.

### 2.2. Randomness khác uniqueness

**Randomness** nói đến cách lấy giá trị từ một phân phối khó dự đoán. **Uniqueness** nói đến việc hai lần sử dụng không nhận cùng một giá trị trong phạm vi phải phân biệt.

- Sinh 12 byte bằng **SecureRandom** tạo ra IV có tính ngẫu nhiên mật mã phù hợp, nhưng **không bảo đảm tuyệt đối không trùng**.
- Dùng một bộ đếm được cấp phát đúng cách có thể tạo các nonce **duy nhất** nhưng **dự đoán trước được**.
- Một mode như **CBC** có yêu cầu IV **không đoán trước được** khi mã hóa trong mô hình liên quan; không nên thay IV ngẫu nhiên bằng bộ đếm đơn giản chỉ vì bộ đếm không trùng.
- Một mode như **GCM** cần **IV không được lặp dưới cùng khóa**; IV có thể được tạo theo cơ chế ngẫu nhiên hoặc cơ chế xác định duy nhất, với các điều kiện khác nhau.

**Không đồng nhất** thuật ngữ “random IV” với “unique IV” trong tài liệu thiết kế.

## 3. Quy tắc IV phụ thuộc chế độ mã hóa

| Mode / thuật toán | Kích thước thường gặp | Quy tắc IV/nonce quan trọng | Ghi chú |
| --- | --- | --- | --- |
| **AES-CBC** | IV bằng block size AES: **16 byte** | IV phải **không đoán trước được** khi mã hóa; thông thường sinh ngẫu nhiên mới cho mỗi bản mã | CBC không tự xác thực; cần giải pháp MAC phù hợp hoặc chuyển sang AEAD |
| **AES-CTR** | Counter block tổng cộng bằng block size AES: **16 byte** | **Không được lặp counter block dưới cùng khóa**, kể cả giữa các thông điệp | Tránh tràn bộ đếm, lặp tiền tố hoặc trùng vùng đếm |
| **AES-GCM** | Thường **12 byte** | **Không được tái sử dụng IV/nonce dưới cùng khóa**; nếu sinh ngẫu nhiên, phải quản lý xác suất trùng và giới hạn lượt sử dụng | AEAD; luôn xác minh tag và AAD |
| **ChaCha20-Poly1305** | Thường nonce **12 byte** với biến thể IETF | Nonce **duy nhất dưới cùng khóa** | Không phải mode của AES; vẫn phải quản lý nonce |
| **AES-ECB** | Không có IV | **Không nên dùng cho mã hóa dữ liệu ứng dụng** | Bộc lộ mẫu khối lặp; không được “vá” bằng cách tự thêm IV |
| **AES-XTS** | Tweak theo đơn vị dữ liệu lưu trữ | Quy tắc tweak khác mô hình nonce ngẫu nhiên của GCM | Dành cho mã hóa thiết bị lưu trữ, không thay AEAD cho thông điệp |

**Kết luận:** Không đặt mặc định hệ thống “IV luôn là 12 byte ngẫu nhiên” nếu giao thức có cả CBC, CTR hoặc cơ chế khác. Kích thước và quy tắc phải được chọn từ **mode và đặc tả được sử dụng**, không chỉ từ độ dài khóa.

### 3.1. AES-CBC: IV cần khó đoán trước

Với CBC, khối đầu tiên của plaintext được kết hợp với IV trước phép mã hóa. Nếu đối thủ dự đoán hoặc tác động được IV trong một số mô hình tấn công, tính bí mật có thể bị ảnh hưởng.

Một cách làm thông dụng là sinh **IV ngẫu nhiên 16 byte mới cho mỗi lần mã hóa**. Không dùng IV toàn số 0, timestamp hoặc một bộ đếm đơn giản thay IV ngẫu nhiên khi thiết kế yêu cầu unpredictability.

CBC **không tự phát hiện việc sửa bản mã**. Khi thiếu xác thực, sửa IV có thể khiến khối plaintext đầu tiên sau giải mã bị thay đổi có kiểm soát. Vì thế, nếu phải dùng CBC trong hệ thống cũ, cần một cơ chế xác thực phù hợp để bảo vệ **IV cùng ciphertext và metadata cần thiết**, đồng thời xử lý lỗi giải mã tránh padding-oracle. Với thiết kế mới, ưu tiên **AEAD** khi có thể.

### 3.2. AES-CTR: không bao giờ lặp lại dòng khóa

CTR tạo dòng khóa từ **khóa bí mật và các counter block**. Nếu hai thông điệp dùng trùng cùng một counter block dưới cùng khóa, chúng có thể dùng lại phần dòng khóa và làm lộ quan hệ giữa plaintext.

Vì vậy, câu hỏi không chỉ là “IV có ngẫu nhiên không?” mà còn là **toàn bộ chuỗi counter block có duy nhất trên mọi thông điệp và mọi block dưới cùng khóa hay không**. Cần quản lý vùng bộ đếm, giới hạn kích thước, restart, phân vùng giữa các tiến trình và overflow.

CTR cũng không tự cung cấp tính toàn vẹn. Thay đổi ciphertext có thể dẫn đến thay đổi plaintext khi giải mã. Không dùng CTR đơn lẻ thay AEAD trong hệ thống cần xác thực.

### 3.3. AES-GCM: tính duy nhất là điều kiện sống còn

GCM là **Authenticated Encryption with Associated Data (AEAD)**: mã hóa plaintext và tạo authentication tag kiểm tra ciphertext cùng AAD. Với GCM, **sử dụng lại cùng IV dưới cùng khóa** là một sự cố mật mã nghiêm trọng, có thể phá hủy tính bí mật và khả năng xác thực.

**Hai IV khác nhau có thể dùng cùng DEK theo chính sách và giới hạn của GCM**; **một IV dùng với hai DEK độc lập khác nhau không phải sự lặp trong cùng phạm vi khóa**. Tuy nhiên, quy trình gán key ID phải bảo đảm thực sự không có trường hợp hai dịch vụ âm thầm dùng cùng vật liệu khóa rồi tưởng là hai khóa độc lập.

IV 96 bit được hỗ trợ rất phổ biến trong AES-GCM. Một số provider có thể nhận IV độ dài khác theo đặc tả, nhưng **không tự chọn kích thước khác** để né việc quản lý tính duy nhất hoặc vì tưởng IV dài hơn luôn an toàn hơn.

### 3.4. Không nhầm tag hợp lệ với chống replay

Kẻ tấn công có thể gửi lại **nguyên ciphertext, IV, tag và AAD** của một thông điệp cũ. AEAD có thể xác minh thành công vì bản mã chưa bị sửa. Đó là một **replay**, không phải lỗi tính toán tag.

Nếu ứng dụng cần ngăn lặp giao dịch, hãy ràng buộc **request ID, sequence number, phiên bản, thời gian hoặc trạng thái nghiệp vụ** với dữ liệu đã được xác thực và kiểm tra chúng ở tầng giao thức/ứng dụng. IV dùng cho mã hóa **không tự động trở thành cơ chế chống replay**.

## 4. Random IV phải được sinh từ đâu?

Nguồn sinh IV cần đáp ứng yêu cầu của mode. Với IV ngẫu nhiên dùng trong mật mã, hãy dùng **CSPRNG** của nền tảng, ví dụ **java.security.SecureRandom** trên Java, hoặc cơ chế sinh số ngẫu nhiên được KMS/HSM cung cấp khi phù hợp.

### 4.1. Những lựa chọn nên và không nên dùng

| Cách tạo | Đánh giá | Lý do |
| --- | --- | --- |
| **SecureRandom.nextBytes(byte[])** | Phù hợp cho ví dụ và nhiều hệ thống Java | Sử dụng bộ sinh số giả ngẫu nhiên được thiết kế cho mật mã |
| **KMS/HSM tạo IV hoặc nonce** | Có thể phù hợp nếu API hỗ trợ và tài liệu quy định rõ | Tích hợp với ranh giới bảo vệ và chính sách của nhà cung cấp |
| **Bộ đếm độc nhất có phân vùng bền vững** | Phù hợp với các mode cho phép nonce xác định duy nhất | Phải bảo đảm không trùng dưới khóa khi restart, nhân bản và failover |
| **java.util.Random / Math.random()** | **Không dùng để tạo random IV mật mã** | Không được thiết kế như nguồn ngẫu nhiên mật mã |
| **System.currentTimeMillis()** | **Không phù hợp** | Dễ dự đoán, có thể trùng trên nhiều request/instance |
| **Hằng số, all-zero IV, IV cố định trong config** | **Không dùng lặp dưới cùng khóa** trong các mode cần IV mới | Làm mất tính duy nhất/khó đoán cần thiết |
| **UUID tùy ý rồi cắt/đệm thành IV** | **Không nên chọn chỉ vì tiện** | Định dạng UUID có bit cố định và kích thước/ngữ nghĩa khác yêu cầu mode |

**SecureRandom không phải Math.random.** Trong Java, tên lớp không chỉ khác nhau về API mà còn khác mục tiêu bảo mật. Không dùng RNG dễ dự đoán chỉ vì dữ liệu sau đó đã được mã hóa bởi AES.

### 4.2. Không tự seed bằng thời gian hoặc giá trị dễ đoán

Một anti-pattern là khởi tạo generator mật mã bằng **timestamp, user ID hoặc request ID** được xem như nguồn ngẫu nhiên chính. Đây không phải cách cung cấp entropy đáng tin cậy.

Trong môi trường Java hiện đại, nên để **SecureRandom** sử dụng cơ chế của provider/hệ điều hành theo thiết kế đã được hỗ trợ. Nếu hệ thống có yêu cầu đặc biệt về FIPS, HSM hoặc DRBG, lựa chọn provider và cơ chế khởi tạo phải theo chính sách/đặc tả, không tự thay bằng một hàm sinh ngẫu nhiên tự chế.

### 4.3. Random IV không giải quyết vấn đề quản lý khóa

Nếu DEK được hardcode hoặc xuất hiện trong log, kẻ tấn công có DEK vẫn có thể giải mã dữ liệu dù mỗi bản mã có IV ngẫu nhiên đúng. Tương tự, nếu mọi workload có quyền Decrypt với mọi tenant, IV tốt không bù cho quyền truy cập sai.

Phải kết hợp **CSPRNG, AEAD, bảo vệ key, least privilege, giám sát và vòng đời khóa**.

## 5. Xác suất trùng IV khi sinh ngẫu nhiên

Một IV có **n bit ngẫu nhiên đồng đều** cho khoảng \(2^n\) giá trị khả dĩ. Khi sinh **q giá trị độc lập** cùng độ dài, xác suất xuất hiện ít nhất một cặp trùng có thể được ước lượng bằng công thức birthday bound khi xác suất còn nhỏ:

\[
P(\text{collision}) \approx \frac{q(q-1)}{2^{n+1}}
\]

Với **IV ngẫu nhiên 96 bit** trong AES-GCM:

| Số lần sinh IV dưới cùng một khóa | Xác suất trùng xấp xỉ (mô hình lý tưởng) |
| ---: | ---: |
| **1 triệu** | \(6{,}3 \times 10^{-18}\) |
| **1 tỷ** | \(6{,}3 \times 10^{-12}\) |
| **2³²** (khoảng 4,3 tỷ) | \(1{,}2 \times 10^{-10}\) |

Những con số này **không phải mức sử dụng được khuyến nghị**. Chúng chỉ minh họa rằng xác suất không bằng 0 và tăng xấp xỉ theo bình phương số lượt sinh. Giả định của bảng là **các IV thật sự ngẫu nhiên, độc lập và phân bố đều**; một RNG lỗi, snapshot sai, bộ đếm trùng hoặc thiết kế phân vùng không đúng có thể tạo rủi ro cao hơn.

**Các chuẩn và cấu hình GCM có giới hạn riêng về số lượt mã hóa trên mỗi khóa, kích thước dữ liệu và cách tạo IV.** Đặc biệt, với cấu trúc IV dùng RNG, cần tuân thủ ngân sách invocation của chuẩn áp dụng; không coi công thức birthday là quyền mã hóa vô hạn. Khi hệ thống sinh rất nhiều bản ghi dưới một DEK, hãy **đặt ngưỡng sử dụng an toàn thấp hơn giới hạn** và chuyển sang DEK mới có kiểm soát.

### 5.1. Random không có nghĩa bảo đảm duy nhất trên nhiều máy

Giả sử 20 instance cùng mã hóa bằng **cùng DEK**. Xác suất trùng cần tính theo **tổng số lần mã hóa của cả 20 instance dưới DEK đó**, không phải mỗi instance riêng lẻ.

Hai máy dùng cùng khóa có thể cùng sinh một nonce dù RNG của mỗi máy đều hoạt động đúng. Vì thế, thiết kế phải quản lý **ngân sách lượt mã hóa toàn cục theo key ID**, hoặc dùng chiến lược nonce xác định duy nhất cho toàn miền sử dụng khóa.

## 6. Hai chiến lược quản lý IV cho hệ thống phân tán

### 6.1. Chiến lược A — IV ngẫu nhiên bằng CSPRNG

Phù hợp cho nhiều hệ thống có số lần mã hóa trên mỗi khóa được giới hạn tốt:

1. Chọn thuật toán/mode, ví dụ **AES-256-GCM với IV 96 bit**.
2. Sinh 12 byte mới bằng SecureRandom **cho từng lần mã hóa**.
3. Lưu IV cùng ciphertext, tag và key ID/version.
4. **Đếm, dự trù hoặc giới hạn** tổng lượt sử dụng dưới cùng DEK trên mọi instance; xoay vòng trước ngưỡng được phê duyệt.
5. Theo dõi lỗi mã hóa, lỗi KMS, cấu hình provider và khả năng sinh ngẫu nhiên của môi trường.

Ưu điểm: dễ tích hợp vào các ứng dụng stateless, không phải lưu bộ đếm riêng cho mỗi message. Hạn chế: **không bảo đảm tuyệt đối uniqueness**, nên phải chấp nhận và quản lý xác suất trùng cùng giới hạn sử dụng.

### 6.2. Chiến lược B — Nonce xác định nhưng duy nhất

Một số mode, trong đó có cấu trúc IV xác định của GCM khi thực hiện đúng đặc tả, có thể dùng nonce dựa trên **prefix được cấp phát duy nhất + counter tăng dần**. Lúc đó không nhất thiết cần ngẫu nhiên cho từng nonce.

~~~text
Ví dụ khái niệm dành riêng cho mode cho phép nonce xác định:

nonce = uniqueInstancePrefix || monotonicallyIncreasingCounter

uniqueInstancePrefix:
    được cấp phát duy nhất cho từng luồng/instance dùng cùng DEK
monotonicallyIncreasingCounter:
    không được lặp, kể cả sau restart hoặc failover

Nếu đổi DEK: không gian nonce được quản lý theo DEK mới.
Nếu counter gần tràn: dừng hoặc rotate trước khi tràn.
~~~

**Rủi ro vận hành:**

- Hai instance được cấp trùng prefix hoặc cùng một vùng counter.
- Process bị khôi phục từ snapshot cũ làm counter quay về giá trị đã dùng.
- Bộ đếm được reset sau khi deploy, failover hoặc restore backup.
- Một tiến trình sử dụng lại DEK nhưng registry lại tưởng đó là khóa khác.

Nếu chọn cách này, phải thiết kế **cấp phát prefix/counter độc nhất, lưu trạng thái bền vững hoặc phân vùng an toàn** và tương thích đúng quy tắc IV của mode. **Không được thay IV ngẫu nhiên CBC bằng bộ đếm dự đoán được** chỉ vì chiến lược đó hợp lệ cho một biến thể GCM.

### 6.3. Có thể dùng khóa mới cho mỗi bản ghi không?

**Envelope encryption** có thể sinh một **DEK mới** cho mỗi đối tượng/tệp hoặc nhóm dữ liệu. Việc đó giúp giảm số lần dùng mỗi DEK, phân vùng phạm vi sự cố và quản lý key rotation.

Tuy nhiên, sinh DEK mới không loại bỏ mọi nghĩa vụ quản lý IV: **mỗi lần mã hóa vẫn phải tuân thủ điều kiện của mode**. Nếu cùng DEK được dùng để mã hóa lại bản ghi, nonce phải được tạo đúng theo chính sách. Không nên giả định luôn có một DEK mới nếu caching hoặc pooling có thể tái sử dụng khóa.

## 7. Java: tạo random IV và mã hóa bằng AES-GCM

Ví dụ sau minh họa một API rõ ràng cho mã hóa đối xứng:

- Sinh **DEK AES-256** bằng KeyGenerator và SecureRandom.
- Sinh **IV 12 byte mới** ngay trong mỗi lần mã hóa.
- Mã hóa và giải mã bằng **AES/GCM/NoPadding**, với **tag 128 bit**.
- Dùng **AAD** để ràng buộc dữ liệu với đúng bản ghi.
- Từ chối ciphertext đã bị sửa nhờ xác minh authentication tag.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class RandomIvDemo {
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();
    private static final int IV_BYTES = 12;    // GCM nonce 96 bit
    private static final int TAG_BITS = 128;   // Authentication tag 128 bit

    private RandomIvDemo() {}

    static final class Envelope {
        final String keyId;
        final byte[] iv;
        final byte[] ciphertextWithTag;

        Envelope(String keyId, byte[] iv, byte[] ciphertextWithTag) {
            this.keyId = keyId;
            this.iv = iv.clone();
            this.ciphertextWithTag = ciphertextWithTag.clone();
        }
    }

    static SecretKey newAes256Key() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, SECURE_RANDOM);
        return generator.generateKey();
    }

    static Envelope encrypt(
            SecretKey dek, String keyId, byte[] plaintext, byte[] aad
    ) throws Exception {
        byte[] iv = new byte[IV_BYTES];
        SECURE_RANDOM.nextBytes(iv); // IV ngẫu nhiên mới cho lần mã hóa này

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, iv));
        cipher.updateAAD(aad);
        byte[] ciphertextWithTag = cipher.doFinal(plaintext);

        return new Envelope(keyId, iv, ciphertextWithTag);
    }

    static byte[] decrypt(
            SecretKey dek, String expectedKeyId, Envelope envelope, byte[] aad
    ) throws Exception {
        if (!expectedKeyId.equals(envelope.keyId)) {
            throw new SecurityException("Wrong key version");
        }
        if (envelope.iv.length != IV_BYTES) {
            throw new SecurityException("Invalid IV length");
        }

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, envelope.iv));
        cipher.updateAAD(aad);

        // doFinal xác minh tag trước khi trả plaintext cho ứng dụng.
        return cipher.doFinal(envelope.ciphertextWithTag);
    }

    public static void main(String[] args) throws Exception {
        SecretKey dek = newAes256Key();
        String keyId = "dek-prod-v1"; // Ví dụ; thực tế từ key registry/KMS
        byte[] aad = "tenant=42|record=invoice-100|schema=v1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "Du lieu can duoc bao ve"
                .getBytes(StandardCharsets.UTF_8);

        Envelope envelope = encrypt(dek, keyId, plaintext, aad);
        byte[] restored = decrypt(dek, keyId, envelope, aad);
        System.out.println("Decryption valid: "
                + Arrays.equals(plaintext, restored));

        byte[] modified = envelope.ciphertextWithTag.clone();
        modified[0] ^= 1;
        Envelope tampered = new Envelope(keyId, envelope.iv, modified);

        try {
            decrypt(dek, keyId, tampered, aad);
            throw new AssertionError("Tampering must be rejected");
        } catch (AEADBadTagException expected) {
            System.out.println("Tampering rejected");
        }
    }
}
~~~

**Kết quả mong đợi:**

~~~text
Decryption valid: true
Tampering rejected
~~~

### 7.1. Giải thích các thành phần quan trọng

1. **SecureRandom.nextBytes(iv)** tạo IV mới cho lần mã hóa hiện tại. Trong ví dụ, IV dài 12 byte theo cấu hình AES-GCM.
2. **KeyGenerator.init(256, ...)** đặt kích thước khóa AES-256, **không đặt kích thước IV**.
3. **GCMParameterSpec(128, iv)** dùng tag 128 bit, **không phải** tạo khóa AES-128.
4. **updateAAD(aad)** ràng buộc ciphertext với ngữ cảnh được xác thực. Khi đọc, AAD phải khớp chính xác; ứng dụng nên dựng AAD từ dữ liệu nghiệp vụ tin cậy, không chỉ tin trường do client tùy ý gửi.
5. **doFinal** ở phía giải mã kiểm tra tag. Nếu ciphertext/tag/AAD bị sửa, phải từ chối kết quả thay vì tiếp tục xử lý bản rõ.
6. **Envelope** mang key ID và IV/ciphertext; code sản xuất cần thêm phiên bản định dạng, giới hạn kích thước và serialization rõ ràng.

**Giới hạn ví dụ:** Một lời gọi SecureRandom không có nghĩa nonce chắc chắn không trùng trên mọi bản ghi. Hệ thống production phải quản lý số lần dùng khóa và chính sách nonce trên toàn bộ instance. Ví dụ cũng tạo khóa trong bộ nhớ để minh họa; chưa có KMS/HSM, persistence, IAM, audit, quản lý key version hoặc khôi phục.

### 7.2. Những đoạn code không an toàn

~~~java
// KHÔNG DÙNG: IV cố định và lặp dưới cùng DEK cho nhiều bản ghi GCM.
byte[] iv = new byte[12];

// KHÔNG DÙNG: nguồn ngẫu nhiên thông thường.
new java.util.Random().nextBytes(iv);

// KHÔNG DÙNG: biến timestamp thành IV rồi nghĩ rằng nó là ngẫu nhiên.
// Việc lặp hoặc dự đoán vẫn có thể xảy ra.
~~~

Với CBC, việc dùng một counter tự tăng có thể tạo IV khác nhau nhưng vẫn **không đáp ứng yêu cầu khó đoán trước**. Với CTR/GCM, chỉ kiểm tra “IV khác bản ghi ngay trước đó” cũng chưa đủ; cần bảo đảm không lặp trên **toàn bộ lịch sử cùng khóa**.

## 8. Lưu IV cùng ciphertext và metadata như thế nào?

IV thường được lưu ngay bên cạnh bản mã. Một định dạng envelope rõ ràng giúp dịch vụ đọc đúng thuật toán, phiên bản, khóa và ngữ cảnh:

~~~json
{
  "formatVersion": 1,
  "algorithm": "AES-256-GCM",
  "keyId": "dek-prod-v1",
  "ivBase64": "<12-byte-IV-encoded-as-Base64>",
  "ciphertextAndTagBase64": "<ciphertext-and-tag>",
  "wrappedDekBase64": "<DEK-protected-by-KEK>",
  "context": {
    "tenantId": "tenant-42",
    "recordId": "invoice-100"
  }
}
~~~

Đây là **mẫu minh họa, không phải cấu trúc chuẩn bắt buộc**. Trong thực tế:

- **IV thường không cần mã hóa riêng**. Base64 chỉ là encoding, không làm IV hay dữ liệu bí mật hơn.
- **Ciphertext và tag** có thể lưu chung hoặc tách trường tùy thư viện; giải mã phải biết đúng format.
- **Key ID và version** giúp chọn DEK/KEK đúng và hỗ trợ dữ liệu cũ sau rotation.
- **Algorithm/mode** phải được kiểm tra với chính sách được phép; không để metadata bị thay đổi thành một thuật toán yếu rồi tự động chấp nhận.
- **AAD** nên ràng buộc tenant ID, record ID, format version hoặc mục đích cần thiết theo quy tắc canonical rõ ràng. Những trường này không được giữ bí mật bởi riêng AAD.
- **Wrapped DEK** phải được bảo vệ bằng cơ chế wrapping phù hợp; không lưu plaintext DEK cạnh ciphertext.
- Nếu kẻ tấn công thay nguyên một envelope cũ hợp lệ vào vị trí một bản ghi mới, **AEAD không tự nhận biết replay/rollback** nếu ứng dụng không kiểm tra record ID/version/trạng thái đáng tin cậy.

Với GCM, IV tham gia trực tiếp vào quá trình tính toán xác thực của thuật toán. Không cần giả định phải đưa nguyên IV vào AAD một lần nữa mới có tính xác thực; điều quan trọng là **kiểm tra tag đúng cách, ràng buộc đúng metadata và bảo vệ ngữ cảnh nghiệp vụ**.

## 9. KMS/HSM và envelope encryption: ai sinh IV?

Trong **envelope encryption**, một **DEK** dùng để mã hóa dữ liệu bằng AES-GCM; **KEK** nằm trong KMS/HSM hoặc ranh giới bảo vệ tương ứng để wrap/unwrap DEK.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng Java
    participant KMS as KMS/HSM
    participant Store as Data store
    App->>KMS: GenerateDataKey hoặc yêu cầu khóa theo policy
    KMS-->>App: Plaintext DEK tạm thời + wrapped DEK
    Note over App: Sinh random IV mới bằng CSPRNG
    Note over App: AES-GCM với DEK, IV và AAD
    App->>Store: Lưu IV, ciphertext, tag, wrapped DEK, key ID
    App->>Store: Đọc envelope
    Store-->>App: IV, ciphertext, tag, wrapped DEK
    App->>KMS: Unwrap DEK theo quyền và ngữ cảnh
    KMS-->>App: Plaintext DEK nếu được phép
    Note over App: Kiểm tra tag/AAD và giải mã
~~~

Trong luồng trên, **ứng dụng sinh IV** vì nó thực hiện AES-GCM ở phía ứng dụng. Nếu dùng **API Encrypt trực tiếp của KMS/HSM**, provider có thể tự chọn IV/nonce và định dạng ciphertext; cần đọc tài liệu API, không tự giả định có thể cung cấp IV hoặc lấy IV từ đầu ra theo cấu trúc tùy ý.

**Cấp phát DEK và cấp phát IV là hai bước khác nhau.** KMS giữ KEK an toàn không có nghĩa nó tự bảo đảm tính duy nhất của các IV khi mã hóa bằng DEK tại ứng dụng.

### 9.1. Quyền truy cập và phạm vi khóa

Đối với nhiều tenant:

- Tách DEK/KEK theo miền dữ liệu khi phù hợp để giới hạn phạm vi ảnh hưởng.
- Workload chỉ được GenerateDataKey/Encrypt/Decrypt/Unwrap theo quyền tối thiểu.
- Kiểm tra **quyền đọc bản ghi** trước khi giải mã, không coi việc có quyền KMS đồng nghĩa được đọc mọi dữ liệu.
- Theo dõi tổng số lượt dùng của **mỗi DEK**, kể cả khi nhiều instance cùng dùng một khóa.
- Ghi audit theo **key ID, workload, thao tác, thời điểm, kết quả và sự kiện rotation** mà không ghi raw DEK hoặc plaintext.

Đối với **random IV**, log có thể ghi các chỉ số vận hành như số lần mã hóa, vi phạm chính sách/giới hạn, lỗi provider và định danh khóa. Không nên ghi plaintext hoặc bí mật chỉ để điều tra sự cố IV.

## 10. Vòng đời khóa gắn với IV như thế nào?

| Giai đoạn | Điều cần kiểm soát về khóa và IV | Lỗi thường gặp |
| --- | --- | --- |
| **Tạo DEK** | Sinh bằng CSPRNG/KMS/HSM, định danh khóa, thuật toán và nonce strategy | Dùng lại key material cũ nhưng khai báo key ID mới |
| **Cấp phát** | Truyền/gán DEK đúng workload, biết phạm vi cùng chia sẻ khóa | Hai hệ độc lập dùng chung DEK và quản lý IV tách rời |
| **Lưu trữ** | Giữ key đã wrap và metadata; IV lưu cùng ciphertext theo format rõ ràng | Làm mất IV, cắt ngắn hoặc nhầm IV của bản ghi khác |
| **Sử dụng** | Sinh IV theo mode, không trùng dưới cùng key khi bắt buộc; kiểm tra tag/AAD | Hardcode IV, dùng RNG yếu, dùng lại counter sau restart |
| **Xoay vòng** | Tạo DEK mới, đặt ngân sách nonce mới; giữ phiên bản cũ để đọc dữ liệu hợp lệ | Đổi key alias nhưng vẫn dùng key cũ và bộ đếm bị reset |
| **Thu hồi** | Ngăn sử dụng key bị lộ hoặc nghi bị khai thác; điều tra các bản mã liên quan | Chỉ chặn một instance trong khi instance khác tiếp tục mã hóa |
| **Hủy** | Đảm bảo không còn dữ liệu cần giải mã bằng key cũ; xử lý bản sao/bản backup | Hủy khóa trước khi dữ liệu lịch sử đã được chuyển đổi |

### 10.1. Xoay vòng DEK và IV mới

Khi hệ thống thay **DEK v1** bằng **DEK v2**, không gian IV được quản lý theo khóa mới. Các bản ghi mã hóa bằng v1 vẫn cần **key ID v1 và IV đã dùng** để giải mã nếu chính sách cho phép.

**Đổi KEK** bằng cách rewrap DEK không làm thay đổi chính DEK đang mã hóa dữ liệu. Vì vậy, **ngân sách sử dụng IV dưới DEK đó không tự đặt lại** khi chỉ rotate KEK. Nếu cần chuyển hoàn toàn sang DEK mới, phải mã hóa lại dữ liệu phụ thuộc theo kế hoạch được bảo vệ.

### 10.2. Nghi ngờ IV/nonce bị trùng thì xử lý ra sao?

Tái sử dụng nonce GCM dưới cùng khóa có thể gây hậu quả nghiêm trọng. Không thể “sửa” hoàn toàn bằng cách thay IV lưu trong database sau khi ciphertext đã được tạo: bản mã và tag cũ được tính từ IV trước đó.

Quy trình xử lý nên:

1. **Tạm dừng** các thao tác mã hóa mới dùng DEK bị nghi ảnh hưởng; cô lập cấu hình tạo nonce sai.
2. Xác định **key ID**, các lần mã hóa, IV liên quan, số instance, khoảng thời gian, dữ liệu và tenant bị ảnh hưởng.
3. Đánh giá mức độ lộ thông tin hoặc giả mạo theo loại mode, điều kiện tấn công và phạm vi ciphertext đã bị truy cập.
4. **Sinh DEK mới** và triển khai nonce strategy đúng; mã hóa lại dữ liệu cần thiết theo ưu tiên và chính sách.
5. Nếu cần, điều tra các bản ghi có nguy cơ bị sửa và kích hoạt phương án thu hồi/khôi phục.
6. Sửa nguồn lỗi như RNG yếu, bộ đếm reset, clone/snapshot hoặc quyền dùng chung khóa; thêm giám sát để ngăn tái diễn.

**Không kết luận mọi dữ liệu đều đã bị đọc chỉ từ phát hiện trùng nonce**, nhưng cũng không xem đó là cảnh báo nhỏ. Cần đánh giá hậu quả dựa trên thuật toán, dữ liệu và quyền truy cập của đối thủ.

## 11. Tình huống thực tế: hệ thống Java nhiều instance

Một nền tảng có 12 instance Java cùng mã hóa hồ sơ khách hàng bằng **DEK AES-256-GCM** lấy từ cache, và mỗi bản ghi có IV do instance sinh. Hệ thống chạy nhiều vùng, hỗ trợ autoscaling và có thể khôi phục snapshot khi xảy ra sự cố.

### 11.1. Những rủi ro cần phát hiện

- **Mỗi instance đếm riêng:** Nếu giới hạn dùng khóa chỉ tính trên một instance, tổng số lần mã hóa theo DEK bị đánh giá thiếu.
- **Reset bộ đếm:** Nếu dùng counter nonce và instance restart, bộ đếm có thể quay về điểm xuất phát gây lặp.
- **Clone cấu hình:** Một snapshot có thể chứa cùng key material và trạng thái nonce/counter, làm nhiều instance vô tình dùng lại cùng miền giá trị.
- **Key alias không đổi:** Sau rotation, key alias trỏ tới DEK mới nhưng metadata bản mã không lưu version, khiến không chọn được DEK cũ để giải mã.
- **Kiểm tra quyền thiếu tenant:** Workload có khả năng Unwrap DEK của tenant khác dù nonce và tag đều đúng.

### 11.2. Phương án triển khai

**Nếu chọn IV ngẫu nhiên:**

1. Mỗi thao tác mã hóa sinh 12 byte mới bằng SecureRandom.
2. Tập trung hoặc phân bổ **ngân sách lượt mã hóa theo key ID** trên toàn bộ instance.
3. Xác định ngưỡng rotate an toàn và có thể buộc cấp DEK mới trước khi vượt ngưỡng.
4. Duy trì định dạng envelope chứa key ID/version, nonce, ciphertext/tag và metadata để xác minh AAD.
5. Theo dõi phân phối deployment, key cache, lỗi mã hóa/giải mã và khả năng khôi phục.

**Nếu chọn IV dạng counter duy nhất:**

1. Cấp mỗi instance một miền counter/prefix **độc nhất theo DEK** bằng cơ chế phân phối đáng tin cậy.
2. Bảo đảm counter tiếp tục đúng sau crash/restart/restore, không dùng lại giá trị đã phát.
3. Kiểm soát điều kiện tràn counter và cấp phát lại miền; dừng mã hóa khi không thể chứng minh tính duy nhất.
4. Xác minh cấu trúc IV tuân thủ chuẩn của mode được dùng, không đưa cùng cơ chế sang CBC một cách máy móc.

### 11.3. Các test case nên chạy

| Test | Kết quả mong đợi |
| --- | --- |
| Mã hóa hai lần cùng plaintext dưới cùng DEK với IV mới | IV khác nhau trong các lần thử thông thường; **không dùng test này làm bằng chứng duy nhất tuyệt đối** |
| Sửa một byte ciphertext hoặc tag | AES-GCM Verify thất bại, không trả plaintext |
| Sửa AAD/record ID | Giải mã thất bại hoặc kiểm tra quyền/ngữ cảnh từ chối |
| Giải mã bằng sai DEK version | Tag không hợp lệ hoặc quy tắc chọn key ID ngăn xử lý |
| Restart nhiều instance dùng counter nonce | Không có counter block/nonce lặp dưới cùng DEK |
| Key rotation trong khi có request đang chạy | Ghi/đọc nhất quán, version cũ và mới không bị nhầm |
| Một tenant xin decrypt dữ liệu tenant khác | Bị từ chối bởi authorization và/hoặc KMS policy |
| KMS hoặc nguồn RNG gặp lỗi | Fail closed, không dùng IV cố định làm fallback |

**Lưu ý:** Với random IV, việc test một vài nghìn lần không thấy trùng là kiểm thử chức năng chứ không chứng minh tính duy nhất trong mọi tương lai. Cần kết hợp phân tích thiết kế, giới hạn usage và chính sách cryptography.

## 12. Những lỗi phổ biến khi dùng random IV

| Sai lầm | Hậu quả | Hướng khắc phục |
| --- | --- | --- |
| Dùng IV toàn số 0 cho mọi lần AES-GCM | Tái sử dụng nonce dưới cùng khóa, rủi ro nghiêm trọng | Sinh IV mới đúng mode hoặc dùng bộ cấp nonce duy nhất |
| Dùng Math.random hoặc timestamp làm IV | Dễ đoán hoặc trùng, không phải randomness mật mã | SecureRandom/CSPRNG và đúng kích thước |
| Nhầm key size với IV size | Provider có thể lỗi hoặc cấu hình không đúng chuẩn | Tách key, IV, block và tag sizes |
| Coi IV ngẫu nhiên luôn duy nhất | Bỏ qua birthday collision và ngân sách lượt mã hóa | Giới hạn sử dụng theo DEK, rotation và chiến lược nonce |
| Đếm IV ở mỗi instance riêng lẻ | Đánh giá thiếu rủi ro toàn hệ thống dùng chung DEK | Theo dõi theo key ID trên mọi instance/vùng |
| Reset counter nonce sau restart/restore | Phát lại nonce đã dùng dưới cùng khóa | Lưu hoặc cấp phát trạng thái bền vững, phân vùng an toàn |
| Dùng counter IV dễ đoán cho AES-CBC | Không đáp ứng yêu cầu unpredictability | Sinh random IV đúng yêu cầu của CBC |
| Dùng CBC/CTR không có cơ chế xác thực | Ciphertext/IV có thể bị chỉnh sửa không được phát hiện | Ưu tiên AEAD hoặc thiết kế xác thực đúng chuẩn |
| Giữ IV bí mật nhưng dùng lại dưới cùng DEK | Không khắc phục lỗi nonce reuse | Tập trung vào uniqueness/unpredictability, không dựa vào bí mật IV |
| Bỏ IV khỏi bản ghi khi lưu | Không đủ tham số để giải mã chính xác | Lưu IV và version cùng envelope |
| Đổi KEK rồi reset bộ đếm IV của DEK cũ | Có thể lặp nonce nếu DEK chưa đổi | Gắn trạng thái nonce với chính DEK, không chỉ KEK |
| Cho phép mọi workload dùng chung một DEK | Tăng phạm vi lộ khóa và khó điều phối IV | Phân vùng key theo tenant/mục đích và least privilege |
| Tin rằng AEAD tự chống replay | Bản mã cũ hợp lệ vẫn có thể được gửi lại | Gắn request ID/version/trạng thái và kiểm tra nghiệp vụ |
| Khi RNG/KMS lỗi thì quay về IV mặc định | Lặp trạng thái mã hóa đúng lúc hệ thống gặp sự cố | Fail closed, cảnh báo và xử lý lỗi |

## 13. Checklist đánh giá thiết kế Random IV

Trước khi đưa mã hóa vào production, hãy trả lời:

1. **Mode:** Đang dùng AES-CBC, CTR, GCM, ChaCha20-Poly1305 hay một chế độ khác? Yêu cầu nonce/IV của mode đó là gì?
2. **Kích thước:** Độ dài IV đã đúng theo mode và provider chưa? Có phân biệt khóa, block size, IV và tag không?
3. **Nguồn tạo:** Random IV có đến từ CSPRNG/SecureRandom phù hợp thay vì timestamp, Random thông thường hay giá trị hardcode?
4. **Duy nhất/khó đoán:** Với CBC, IV có khó đoán trước? Với GCM/CTR, có kiểm soát tính không lặp dưới cùng khóa?
5. **Phân tán:** Nếu nhiều instance dùng cùng DEK, ai quản lý tổng số lượt mã hóa, vùng counter và rủi ro trùng nonce?
6. **Giới hạn:** Có ngân sách nonce theo key, giới hạn độ dài dữ liệu, chính sách rotate và cảnh báo trước ngưỡng không?
7. **Lưu trữ:** IV, ciphertext, tag, algorithm, key ID/version và wrapped DEK có được lưu theo format rõ ràng?
8. **Ngữ cảnh:** AAD/metadata có ràng buộc đúng tenant, record, version hoặc mục đích khi cần không?
9. **Giải mã:** Có kiểm tra tag trước khi sử dụng plaintext và từ chối mọi ciphertext không hợp lệ không?
10. **Quyền:** Ai được Encrypt/Decrypt, GenerateDataKey, Unwrap hoặc Rotate? KMS/HSM và ứng dụng đã dùng least privilege chưa?
11. **Sự cố:** Nếu nghi trùng IV, có cách xác định DEK và bản mã ảnh hưởng, ngừng sử dụng, thay khóa và điều tra không?
12. **Kiểm toán:** Có thể truy vết key ID, thao tác, version và lỗi nonce mà không ghi raw key/DEK hoặc plaintext không?

## 14. Ghi nhớ

- **Random IV** là vector khởi tạo được sinh bằng nguồn ngẫu nhiên mật mã, nhưng **random không đồng nghĩa chắc chắn duy nhất**.
- Với **AES-CBC**, IV thường cần **ngẫu nhiên khó đoán trước, dài 16 byte**; với **AES-GCM**, IV **12 byte** là lựa chọn phổ biến và **không được tái sử dụng dưới cùng khóa**.
- Với **AES-CTR**, phải tránh lặp **counter block**; với **ChaCha20-Poly1305**, phải quản lý nonce duy nhất theo khóa. Quy tắc IV **phụ thuộc mode**.
- **SecureRandom** phù hợp để sinh random IV trong nhiều ứng dụng Java. Không dùng **Math.random, java.util.Random, timestamp hoặc IV cố định** cho mục tiêu này.
- **IV không phải khóa và thường không cần bí mật**. Nên lưu IV cùng bản mã/tag/key ID; bảo đảm xác thực AEAD và ràng buộc ngữ cảnh theo chính sách.
- **KMS/HSM, envelope encryption, phân quyền và vòng đời DEK/KEK** giúp bảo vệ key; chúng **không tự sửa lỗi tái sử dụng nonce** nếu ứng dụng tự thực hiện mã hóa.
- Với hệ thống nhiều instance, phải quản lý ngân sách nonce, rotation và khả năng phục hồi **trên toàn bộ phạm vi dùng chung một DEK**.

Thiết kế Random IV an toàn bắt đầu bằng ba câu hỏi: **Mode này yêu cầu IV ngẫu nhiên hay duy nhất? Làm thế nào bảo đảm quy tắc đó dưới cùng một khóa, kể cả sau restart và trên nhiều máy? Khi quy tắc bị vi phạm, hệ thống sẽ phát hiện, ngừng sử dụng và xử lý sự cố ra sao?**
