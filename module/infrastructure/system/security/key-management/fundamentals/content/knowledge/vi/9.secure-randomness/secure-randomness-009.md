# Predictable randomness — Khi số ngẫu nhiên mật mã có thể dự đoán

## 1. Predictable randomness là gì?

**Predictable randomness** là tình huống các giá trị được một hệ thống coi là “ngẫu nhiên” nhưng đối thủ có thể **dự đoán, suy ra hoặc tái tạo** chúng với chi phí khả thi. Đây là rủi ro đặc biệt nghiêm trọng trong mật mã vì nhiều bí mật được tạo ra từ các byte ngẫu nhiên: **khóa AES, khóa riêng RSA/ECC, số bí mật dùng trong thỏa thuận khóa, khóa phiên, token khôi phục tài khoản và nonce của một số giao thức**.

Một giá trị trông “rối”, không có quy luật rõ ràng với mắt người, **không đồng nghĩa với khó dự đoán về mặt mật mã**. Một bộ sinh số giả ngẫu nhiên thông thường có thể sinh chuỗi dài, phân bố có vẻ đều nhưng toàn bộ chuỗi lại được quyết định bởi một **seed** có ít khả năng hoặc đã bị lộ.

Ví dụ, ứng dụng tạo reset token từ thời gian hiện tại rồi dùng bộ sinh số giả ngẫu nhiên thông thường. Người ngoài có thể ước lượng khoảng thời gian tạo token, thu hẹp tập seed cần xét và dự đoán token. Tương tự, nếu khóa riêng được tạo từ một nguồn thiếu entropy, đối thủ có thể thử lại các trạng thái đầu vào khả dĩ để tìm khóa phù hợp với public key.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chủ đề thuộc chương **Secure randomness** và gắn trực tiếp với vòng đời khóa: **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy**. Một private key bị sinh ra yếu **không thể trở thành mạnh chỉ bằng việc cất trong KMS/HSM sau đó**; sự bảo vệ phải bắt đầu từ nguồn ngẫu nhiên ở thời điểm sinh khóa.

> **Nguyên tắc cốt lõi:** Để sinh **bí mật mật mã**, phải dùng **CSPRNG/DRBG phù hợp** được khởi tạo từ nguồn entropy đáng tin, qua API mật mã chuẩn. Không thay thế bằng `Random`, timestamp, PID, counter, UUID tự chế hay hash của một đầu vào dễ đoán.

### Hai câu hỏi quan trọng

1. **Đối thủ có thể dự đoán đầu ra tiếp theo hoặc tái tạo đầu ra trước đó không?** Đây là vấn đề về độ an toàn của bộ sinh và trạng thái nội bộ.
2. **Các giá trị cần độc lập/không trùng có thực sự đáp ứng quy tắc của giao thức không?** Đây là vấn đề riêng, đặc biệt đối với nonce của AES-GCM/CTR và số ngẫu nhiên ký số.

Một CSPRNG mạnh không tự bảo đảm mọi yêu cầu “không trùng” khi số lần lấy mẫu rất lớn, và một counter không trùng cũng chưa chắc là lựa chọn phù hợp để **tạo bí mật**.

## 2. Thuật ngữ: random, entropy, seed, PRNG, CSPRNG và DRBG

| Thuật ngữ | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| **Entropy** | Mức bất định của nguồn hoặc phân bố đầu vào theo mô hình phù hợp | Độ dài byte **không bằng** số bit entropy |
| **Entropy source** | Nguồn tạo dữ liệu vật lý/hệ thống mang tính bất định, được thu thập và xử lý | Cần đánh giá chất lượng và lỗi nguồn, không chỉ nhìn chuỗi đầu ra |
| **Seed** | Vật liệu khởi tạo hoặc bổ sung trạng thái bộ sinh | Seed bị đoán/lộ có thể phá an toàn của RNG tùy cấu trúc |
| **PRNG** | Bộ sinh giả ngẫu nhiên xác định bởi trạng thái/seed | Phù hợp mô phỏng, game, thử nghiệm; không mặc định an toàn mật mã |
| **CSPRNG** | PRNG được thiết kế chống dự đoán theo mô hình an toàn mật mã | Thích hợp sinh key/token khi khởi tạo đúng |
| **DRBG** | Deterministic Random Bit Generator: dạng bộ sinh bit xác định có yêu cầu an toàn/seed/reseed rõ | Các cơ chế chuẩn có thể dùng block cipher, hash hoặc HMAC |
| **TRNG** | True/Hardware Random Number Generator, lấy bất định từ hiện tượng vật lý hoặc thiết bị | Có thể có lỗi/bias; cần xử lý và kiểm tra nguồn |
| **Reseed** | Cập nhật trạng thái bộ sinh từ entropy mới | Tuân theo thiết kế bộ sinh, không tự thêm timestamp vào seed |
| **Forward/backtracking resistance** | Các thuộc tính chống suy diễn đầu ra sau/trước khi một phần trạng thái lộ theo thiết kế cụ thể | Không coi mọi API RNG đều bảo đảm như nhau |
| **Nonce** | Giá trị dùng một lần trong phạm vi khóa/giao thức khi yêu cầu | Thường yêu cầu **duy nhất**, không nhất thiết bí mật |
| **Salt** | Giá trị phụ công khai cho KDF/password hashing | Thường cần riêng biệt/không trùng theo mục đích, không phải secret |
| **Key material** | Vật liệu bí mật dùng trong khóa mật mã | Cần entropy và độ dài/định dạng theo thuật toán |

### Seed 256 bit có luôn là 256 bit entropy?

**Không.** Nếu ứng dụng lấy một số nguyên timestamp có khoảng 1 triệu khả năng rồi hash thành 32 byte SHA-256, đầu ra dài 256 bit nhưng entropy thực vẫn không tự tăng lên 256 bit. Đối thủ có thể băm lại một triệu timestamp ứng viên.

~~~text
weakSeed = currentTimeMillis()
seedBytes = SHA-256(encode(weakSeed))   # dài 32 byte
~~~

`seedBytes` có vẻ đủ dài để làm khóa AES-256, nhưng số khả năng thực tế chỉ bằng số giá trị `weakSeed` mà đối thủ chưa biết. **Hash không tạo entropy mới từ một nguồn dự đoán được.**

## 3. Vì sao PRNG thông thường không phù hợp với mật mã?

**Pseudo-Random Number Generator (PRNG)** có thể tạo ra phân bố nhìn tương tự ngẫu nhiên trong thử nghiệm thống kê. Nhưng với nhiều PRNG phổ thông, biết một phần trạng thái hoặc một số đầu ra có thể giúp suy ra trạng thái hay dự đoán chuỗi tiếp theo.

### 3.1. Java `java.util.Random` là bộ sinh có mục đích khác

`java.util.Random` sử dụng bộ sinh xác định với trạng thái hạn chế (trong các triển khai Java thông dụng, thuật toán LCG với trạng thái nội bộ 48 bit). Nó hữu ích cho **mô phỏng, lựa chọn dữ liệu thử nghiệm và hành vi tái lập**, nhưng **không phải bộ sinh bí mật mật mã**. `ThreadLocalRandom` và `SplittableRandom` cũng không nên được chọn để sinh private key, reset token, OTP bí mật hoặc session secret.

Ví dụ hai đối tượng `Random` được khởi tạo bằng cùng seed cho cùng chuỗi:

~~~java
import java.util.Arrays;
import java.util.Random;

public final class PredictableRandomDemo {
    public static void main(String[] args) {
        Random a = new Random(12345L);
        Random b = new Random(12345L);

        byte[] first = new byte[16];
        byte[] second = new byte[16];

        a.nextBytes(first);
        b.nextBytes(second);
        System.out.println(Arrays.equals(first, second)); // true

        // Đây là tính tái lập hữu ích trong test, không phải bí mật.
    }
}
~~~

Kẻ tấn công không nhất thiết phải biết seed chính xác ngay từ đầu. Nếu seed lấy từ thời gian, PID hoặc trạng thái dễ quan sát, đối thủ có thể có số lượng ứng viên nhỏ. Nếu thuật toán RNG không được thiết kế để chống suy diễn trạng thái, các giá trị công khai cùng sinh từ RNG cũng có thể hỗ trợ dự đoán giá trị bí mật khác.

### 3.2. CSPRNG khác PRNG thường ở mục tiêu bảo mật

Một **CSPRNG** được thiết kế sao cho người quan sát đầu ra và biết thuật toán vẫn khó dự đoán các bit bí mật tiếp theo nếu **trạng thái nội bộ và nguồn entropy đủ an toàn**. Bộ sinh cũng cần có cơ chế cập nhật trạng thái và phục hồi sau những sự cố được mô hình hóa.

Tuy nhiên, “dùng API tên SecureRandom” không phải phép màu nếu môi trường có lỗi: runtime lỗi thời, entropy source trục trặc, trạng thái RNG bị snapshot/copy sai, seed bị can thiệp hoặc phần cứng bị lỗi có thể làm suy yếu kết quả. Cần chọn API chuẩn, cập nhật nền tảng và kiểm soát kiến trúc sinh khóa.

## 4. Các nguồn predictable randomness thường gặp

| Sai lầm | Tại sao nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| **Seed bằng timestamp** | Đối thủ thường đoán được khoảng thời gian tạo | Dùng RNG mật mã của nền tảng; không tự seed bằng thời gian |
| **Seed bằng PID, hostname hoặc username** | Không gian giá trị nhỏ/có thể công khai | Không coi metadata hệ thống là entropy bí mật |
| **Seed bằng hash của chuỗi cố định** | Hash của hằng số vẫn xác định, tái tạo được | Lấy entropy từ nguồn tin cậy |
| **Dùng `Random` cho khóa/token** | Trạng thái/thuật toán không đáp ứng yêu cầu CSPRNG | `SecureRandom`, API key generation chuẩn hoặc KMS/HSM |
| **Dùng hằng số hoặc seed cố định ở production** | Các lần chạy có thể sinh cùng chuỗi | Seed cố định chỉ dùng trong test không liên quan bí mật |
| **Seed suy ra từ mật khẩu yếu** | Đối thủ thử từ điển/password dự đoán được | Password KDF phù hợp cho mật khẩu; secret generation phải có entropy phù hợp |
| **Clone VM/container với trạng thái RNG tùy biến** | Các bản sao có thể tiếp tục từ trạng thái giống nhau | Để OS/runtime quản lý CSPRNG, đánh giá snapshot/fork và cơ chế refresh/reseed |
| **Nguồn entropy phần cứng lỗi hoặc bị can thiệp** | DRBG có thể nhận ít entropy hơn giả định | Thu thập theo cơ chế được đánh giá, health checks và phản ứng lỗi |
| **Tự ghép vài nguồn có vẻ ngẫu nhiên** | Kết quả có thể vẫn dự đoán hoặc có bias | Dùng entropy collector/DRBG đã được thẩm định |
| **RNG bị lộ trạng thái nội bộ** | Có thể suy diễn đầu ra tùy cơ chế | Bảo vệ process/host, chọn DRBG có thuộc tính và reseed phù hợp |

### 4.1. Timestamp hoặc UUID có được dùng làm secret không?

Một timestamp có thể hữu ích cho **log, sort order và identifier**; điều đó không biến timestamp thành bí mật. UUID là **định dạng định danh**, và các phiên bản/cách tạo UUID có thuộc tính khác nhau. Không được suy ra mọi UUID đều khó đoán chỉ vì chúng trông dài và chứa ký tự hex.

Nếu cần **token có entropy bảo mật**, hãy yêu cầu **32 byte từ CSPRNG** rồi biểu diễn bằng Base64url hoặc hex. Nếu cần định danh công khai, UUID theo chính sách có thể phù hợp; nhưng **định danh công khai không thay thế quyền truy cập và bằng chứng xác thực**.

### 4.2. Một nguồn “nhiễu” có bảo đảm an toàn không?

Độ biến thiên của nhiệt độ, thời gian phản hồi hoặc dữ liệu sensor có thể được dùng trong một số thiết kế entropy source, nhưng không nên tự lấy vài phép đo rồi XOR/hash để xem như RNG mật mã. Độ ngẫu nhiên phải được **ước lượng trong mô hình của nguồn**, kiểm soát bias/correlation và lỗi sức khỏe nguồn.

Việc quan sát một dãy byte “không thấy quy luật” hoặc kiểm tra histogram đẹp **không chứng minh** nguồn có đủ entropy để sinh private key.

## 5. Entropy thật, DRBG và quy trình khởi tạo

Một kiến trúc RNG mật mã thường có các bước:

~~~mermaid
flowchart TD
    E[Nguồn entropy được hệ thống đánh giá] --> C[Thu thập, đánh giá và xử lý theo thiết kế]
    C --> S[Seed/instantiation cho CSPRNG-DRBG]
    S --> G[Sinh byte giả ngẫu nhiên mật mã]
    G --> K[Key material, secret, token, nonce thích hợp]
    S --> R[Reseed khi cần theo chính sách/thiết kế]
    E --> R
    R --> S
    H[Health checks và giám sát lỗi RNG] --> C
    H --> R
~~~

### 5.1. Seed không phải “cứ càng nhiều byte càng tốt”

Một DRBG có trạng thái dài không tự chứng minh đầu vào seed có đủ entropy. Phải đánh giá **nguồn** và quy trình thu thập. Nguồn entropy tin cậy có thể do hệ điều hành, phần cứng mật mã hoặc module được đánh giá cung cấp; cơ chế cụ thể tùy nền tảng.

Ví dụ, DRBG phục vụ mức an toàn tương ứng 128 bit cần được khởi tạo với lượng entropy đạt yêu cầu của thiết kế. Không lấy **128 bit đầu ra từ RNG yếu** rồi tuyên bố đó là 128 bit entropy.

### 5.2. Reseed là gì?

**Reseed** cập nhật trạng thái DRBG bằng entropy mới theo quy tắc của thuật toán. Một số hệ thống thực hiện reseed định kỳ hoặc theo hạn mức sinh, một số dựa trên API/hạ tầng hệ điều hành. Không nên tự bắt buộc reseed ở mỗi request với timestamp; như vậy có thể thêm độ phức tạp, giảm hiệu năng hoặc tạo rủi ro nếu can thiệp sai trạng thái.

Nếu cần mức bảo đảm cao, xem xét đặc tính reseed, khả năng **prediction resistance**, phương thức khôi phục sau compromise và chứng nhận của nhà cung cấp. Cần nhận thức rằng **thuộc tính cryptographic prediction resistance của một DRBG** là khái niệm kỹ thuật cụ thể, khác với cách nói chung “chuỗi có vẻ khó đoán”.

### 5.3. Health checks không đồng nghĩa chứng minh RNG an toàn

Hệ thống cần phát hiện sự cố của entropy source như nguồn bị kẹt, lặp, sai phân bố bất thường. Những bài kiểm tra sức khỏe nguồn và kiểm tra startup/continuous có thể hỗ trợ phát hiện lỗi; chi tiết phụ thuộc phần cứng/tiêu chuẩn.

**Nhưng:** vượt qua kiểm tra thống kê hoặc kiểm tra một lần trên dãy byte ngắn **không chứng minh** bộ sinh là CSPRNG. Việc chọn thuật toán, đánh giá entropy và triển khai đúng vẫn là trọng tâm.

### 5.4. Tiêu chuẩn và hướng đánh giá

Trong những hệ thống có yêu cầu tuân thủ, các khung kỹ thuật như **NIST SP 800-90A** (DRBG), **SP 800-90B** (entropy source) và **SP 800-90C** (cấu trúc kết hợp) có thể hữu ích để xác định thành phần và bằng chứng cần kiểm tra. Không tự nhận tuân thủ chỉ vì dùng một hàm hash hoặc gọi API `SecureRandom`; phải xem chứng nhận/configuration và phạm vi thực tế.

## 6. Predictable randomness phá vỡ khóa mật mã như thế nào?

### 6.1. Khóa đối xứng AES

Một khóa AES-256 dài **32 byte** nhưng nếu toàn bộ byte được sinh bằng PRNG với seed chỉ có vài nghìn hoặc vài triệu khả năng, đối thủ có thể thử các seed có thể xảy ra thay vì tìm trong không gian khóa lý tưởng 2^256.

Ví dụ khái niệm:

~~~text
weakSeed = encode(serverStartTime)
AES256Key = first32Bytes(PRNG(weakSeed))

Độ dài khóa biểu diễn: 256 bit
Không gian seed mà đối thủ có thể tìm: có thể rất nhỏ
=> Độ an toàn thực tế bị giới hạn bởi khả năng đoán seed/PRNG.
~~~

Cất khóa này trong một keystore mã hóa hoặc KMS sau khi tạo **không thay đổi cách nó được sinh ra**. Nếu đối thủ đã có khả năng tái tạo khóa, kiểm soát lưu trữ không khôi phục tính bí mật.

### 6.2. RSA/ECC private key

Khóa riêng RSA, ECDSA/Ed25519, ECDH/X25519 và các cơ chế khóa công khai đều phụ thuộc vào quá trình sinh vật liệu bí mật đúng cách. Nguồn entropy yếu có thể dẫn đến private key dự đoán được, các cặp khóa lặp lại hoặc các mối liên hệ không mong muốn.

Với RSA, việc sinh số nguyên tố bằng RNG yếu có thể gây rủi ro nghiêm trọng; trong một số lớp lỗi triển khai, nhiều mô-đun RSA chia sẻ thừa số nguyên tố, khiến khóa riêng có thể bị suy ra khi đối chiếu các public modulus. Với khóa đường cong elliptic, nếu private scalar được lấy từ nguồn có không gian nhỏ, kẻ tấn công có thể thử ứng viên và so với public key.

**Không tự viết code sinh prime RSA hoặc scalar ECC** để “kiểm soát entropy”. Dùng `KeyPairGenerator`, nhà cung cấp mật mã đáng tin hoặc KMS/HSM hỗ trợ thuật toán, với yêu cầu nguồn ngẫu nhiên được đánh giá.

### 6.3. Khóa thỏa thuận phiên và forward secrecy

Trong (EC)DHE, các private agreement key tạm thời có vai trò tạo shared secret cho phiên. Nếu những private key tạm bị dự đoán hoặc lặp giữa các phiên do RNG lỗi, đối thủ có thể suy ra shared secret và các khóa phiên dẫn xuất, làm suy yếu hoặc phá vỡ kỳ vọng **forward secrecy**.

Không nên coi việc giao thức sử dụng “ephemeral key” là đủ; **ephemeral phải được tạo bằng nguồn mật mã phù hợp, quản lý vòng đời và hủy sau khi dùng**.

## 7. Rủi ro trong chữ ký số: ECDSA, RSA-PSS và EdDSA

### 7.1. ECDSA cần bảo vệ nonce ký

ECDSA sử dụng một giá trị bí mật **k** cho mỗi lần ký. Nếu k bị lặp trong những điều kiện nhất định, hoặc bị dự đoán/tiết lộ, **private signing key có thể bị suy ra**. Đây là một trong những hậu quả nguy hiểm nhất của predictable randomness.

Cách bảo vệ:

- Dùng thư viện ký số chuẩn được đánh giá, không tự tạo k bằng `Random`, timestamp hoặc counter.
- Một số cơ chế **deterministic ECDSA** như cách tiếp cận RFC 6979 dẫn xuất k bằng cơ chế mật mã từ private key và thông điệp, tránh phụ thuộc trực tiếp vào nguồn ngẫu nhiên cho mỗi lần ký. Tuy nhiên **private key ban đầu vẫn phải được sinh an toàn**.
- Không tự kết hợp một bộ sinh k tùy biến với API ECDSA hoặc vô hiệu hóa kiểm tra của provider.

### 7.2. RSA-PSS cũng có sử dụng randomness

RSA-PSS thường sử dụng một salt khi tạo chữ ký, theo thông số và thuật toán chữ ký. Việc chọn salt phải theo quy tắc và provider phù hợp. **Không tự thay salt bằng hằng số hoặc giá trị dễ đoán** chỉ để kết quả ký lặp lại, trừ khi một biến thể/giao thức tiêu chuẩn cụ thể quy định khác và được đánh giá.

Dù dùng thuật toán chữ ký mạnh, private key RSA sinh bằng nguồn entropy yếu vẫn là rủi ro độc lập.

### 7.3. Ed25519 và tính xác định

Ed25519 theo cách triển khai tiêu chuẩn sử dụng cơ chế ký xác định từ private key và thông điệp, không cần một nonce ngoài do ứng dụng cấp cho từng chữ ký theo cách ECDSA ngẫu nhiên. **Điều này không loại bỏ yêu cầu tạo seed/private key đủ entropy**, bảo vệ private key, xác minh đúng giao thức và tránh lỗi triển khai.

### Bảng so sánh

| Hoạt động | Randomness liên quan | Nếu randomness yếu |
| --- | --- | --- |
| **Sinh private key ECDSA/Ed25519/RSA** | Vật liệu bí mật ban đầu | Có thể đoán/lặp private key |
| **Ký ECDSA với k ngẫu nhiên** | Nonce bí mật của mỗi chữ ký | Có nguy cơ lộ private key nếu k lặp, lệch hoặc bị biết |
| **Ký ECDSA xác định đúng chuẩn** | K được dẫn xuất an toàn từ private key và thông điệp | Vẫn lệ thuộc an toàn của private key và triển khai |
| **Ký RSA-PSS** | Salt/padding theo thuật toán | Không tuân thủ scheme có thể giảm bảo đảm và tính tương thích |
| **Ký Ed25519 chuẩn** | Seed khóa ban đầu, phép tính nội bộ chuẩn | Lộ seed/private key hoặc triển khai lỗi làm mất an toàn |
| **Thỏa thuận khóa ECDHE** | Private agreement key tạm | Có thể mất bí mật phiên/forward secrecy |

## 8. Nonce, IV, salt và token: không phải mọi thứ đều cần “bí mật”

Một nhầm lẫn thường gặp là cho rằng vì `SecureRandom` dùng cho sinh khóa thì **mọi IV, salt và nonce phải giữ bí mật**. Trong thực tế, nhiều giá trị **công khai** nhưng cần đáp ứng điều kiện khác nhau.

| Giá trị | Có cần bí mật? | Điều kiện quan trọng |
| --- | --- | --- |
| **AES key / HMAC key / private key** | **Có** | Sinh bằng CSPRNG và bảo vệ vật liệu/quyền sử dụng |
| **Reset token / bearer token / API secret** | **Có** | Không thể đoán, đủ entropy, TTL/quyền phù hợp |
| **IV cho AES-CBC** | Thường không | Mới và **khó dự đoán trước khi plaintext được chọn/chốt** theo yêu cầu CBC |
| **Nonce cho AES-GCM** | Không | **Không lặp dưới cùng một khóa**; 96 bit thường được ưu tiên |
| **Counter block trong AES-CTR** | Không | Không lặp counter block dưới cùng khóa; tránh overflow |
| **Salt cho password hashing** | Không | Riêng biệt theo verifier/ngữ cảnh, đủ độ dài và được lưu cùng tham số |
| **Salt cho HKDF** | Thường không | Theo quy tắc giao thức/KDF; không coi là khóa bí mật |
| **Session ID công khai không dùng làm bearer secret** | Không | Tính duy nhất và ràng buộc ngữ cảnh, không thay xác thực |

### 8.1. Khi nào dùng nonce ngẫu nhiên, khi nào dùng counter?

Đối với AES-GCM, có thể có hai chiến lược phù hợp với thiết kế:

- **Nonce ngẫu nhiên 96 bit từ CSPRNG:** đơn giản và phổ biến, nhưng vẫn có **xác suất va chạm**; cần theo dõi giới hạn số lần mã hóa trên mỗi khóa theo đặc tả/chính sách.
- **Nonce xác định/counter được điều phối:** có thể bảo đảm không lặp nếu quy tắc cấp phát thật sự duy nhất, bền vững qua restart, không trùng node/region và không tràn bộ đếm.

**Dự đoán được nonce GCM không tự động là vấn đề**, nếu giao thức chỉ yêu cầu nó duy nhất; nhưng **lặp nonce với cùng khóa là lỗi nghiêm trọng**. Ngược lại, nonce/IV của CBC không thể mặc nhiên dùng bộ đếm công khai bởi CBC cần thuộc tính khó dự đoán trong mô hình bảo mật thông dụng.

Đặc biệt, **không lấy output của `Random` để sinh nonce** chỉ vì nó trông ngẫu nhiên, rồi bỏ qua đánh giá va chạm và tương quan giữa các node. Với hệ thống nhiều instance, phải làm rõ phạm vi và cách cấp phát.

### 8.2. Reset token và mật khẩu không cùng mô hình entropy

Mật khẩu do người dùng tự đặt thường có entropy hạn chế và cần **password KDF** (Argon2id/scrypt/PBKDF2 theo chính sách) để bảo vệ password verifier khỏi dò đoán offline. Một reset token sinh ra từ **32 byte CSPRNG** đã có entropy cao; thường có thể lưu **hash của token** trên server và yêu cầu TTL + one-time-use. Không lấy hash của một timestamp rồi coi là reset token đủ entropy.

**HMAC key** cũng phải sinh bí mật từ CSPRNG phù hợp; việc HMAC dựa trên hash không có nghĩa có thể dùng một mật khẩu yếu làm HMAC key mà không đánh giá thiết kế.

## 9. Java: sử dụng `SecureRandom` đúng cách

Trong Java, nên dùng **`java.security.SecureRandom`** hoặc các API tạo khóa mật mã sử dụng nguồn an toàn đã cấu hình. Đối với khóa AES, **`KeyGenerator`** là API phù hợp; với cặp khóa bất đối xứng, dùng **`KeyPairGenerator`**. Trong hệ thống yêu cầu cao, có thể chuyển thao tác tạo khóa vào KMS/HSM hỗ trợ loại khóa.

### 9.1. Ví dụ tốt: tạo reset token, AES key và EC key pair

Đoạn mã sau dùng Java 11+ và các API JCA/JCE phổ biến. Mục đích minh họa **nguồn ngẫu nhiên và sự phân biệt giữa secret/token với key object**. Không có endpoint gửi token hoặc lưu key material ra file.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.spec.ECGenParameterSpec;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class SecureRandomExamples {
    private static final SecureRandom RNG = new SecureRandom();

    static byte[] newRandomTokenBytes() {
        byte[] tokenBytes = new byte[32]; // 256 bit độ dài
        RNG.nextBytes(tokenBytes);
        return tokenBytes;
    }

    static SecretKey newAes256Key() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        return generator.generateKey();
    }

    static KeyPair newEcKeyPair() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(new ECGenParameterSpec("secp256r1"), RNG);
        return generator.generateKeyPair();
    }

    public static void main(String[] args) throws Exception {
        byte[] rawToken = newRandomTokenBytes();
        String token = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(rawToken);

        // Bên server lưu digest token, tài khoản, mục đích,
        // expiresAt và consumedAt; không lưu token dạng rõ.
        byte[] tokenDigest = MessageDigest.getInstance("SHA-256")
                .digest(token.getBytes(StandardCharsets.US_ASCII));

        SecretKey aesKey = newAes256Key();
        KeyPair ecKeyPair = newEcKeyPair();

        System.out.println("Token digest length: " + tokenDigest.length);
        System.out.println("AES algorithm: " + aesKey.getAlgorithm());
        System.out.println("EC public key algorithm: "
                + ecKeyPair.getPublic().getAlgorithm());

        // Không log token, AES key, EC private key hoặc getEncoded().
        Arrays.fill(rawToken, (byte) 0);
        Arrays.fill(tokenDigest, (byte) 0);
        // String token có thể còn tồn tại trong bộ nhớ: best effort.
    }
}
~~~

**Giải thích:**

1. `new SecureRandom()` yêu cầu bộ sinh mật mã theo cấu hình/provider của JVM và hệ điều hành; **thuật toán/provider cụ thể phụ thuộc runtime**. Đây là API phù hợp hơn `Random` cho secret. Cần dùng runtime được cập nhật và cấu hình đúng.
2. `nextBytes` lấy 32 byte cho token. **Độ dài 256 bit không tự chứng minh đủ 256 bit entropy** nếu nguồn/runtime có sự cố; đó là lý do phải kiểm soát môi trường.
3. `KeyGenerator` và `KeyPairGenerator` để nhà cung cấp mật mã thực hiện sinh khóa theo thuật toán, tránh tự xây các byte private key.
4. `Base64url` chỉ là **mã hóa biểu diễn**, không bảo vệ bí mật token. Tránh ghi token vào log, URL analytics, crash dump; kiểm soát TTL, phạm vi và one-time-use.
5. Ví dụ tạo EC key pair không tự thiết kế thuật toán ký. Với ứng dụng thật, cần quản lý private key trong keystore/KMS/HSM và hạn chế xuất.

### 9.2. Có nên gọi `SecureRandom.setSeed(System.currentTimeMillis())`?

**Không.** Không dùng timestamp, PID hay password yếu như một cách tự khởi tạo bộ sinh mật mã. `SecureRandom` có quy tắc seed riêng tùy provider; một lời gọi `setSeed` có thể bổ sung dữ liệu vào trạng thái đã khởi tạo chứ không nhất thiết thay thế toàn bộ seed, nhưng **không nên dựa vào việc thêm dữ liệu dễ đoán để tăng an toàn**.

Không gọi `new SecureRandom(new byte[]{...})` với mảng seed cố định hoặc giá trị dễ đoán trong production. Hãy để runtime và hệ điều hành cung cấp entropy theo cơ chế được đánh giá, hoặc cấu hình DRBG/provider chuẩn theo chính sách.

### 9.3. Có nên dùng `SecureRandom.getInstanceStrong()` cho mọi request?

Không nhất thiết. `SecureRandom.getInstanceStrong()` chọn một thuật toán theo cấu hình JVM cho trường hợp cần nguồn mạnh theo cấu hình đó, nhưng **có thể khác nhau giữa các nền tảng** và trong một số môi trường có thể chờ nguồn entropy. Không nên thay mọi lời gọi `SecureRandom` trong luồng request nóng bằng `getInstanceStrong()` mà không đánh giá API, throughput, latency và cấu hình provider.

Nên dùng provider/runtime đáng tin, lựa chọn DRBG theo yêu cầu sản phẩm/tuân thủ và theo dõi khi gặp lỗi. **Không tự hạ cấp sang `java.util.Random`** nếu `SecureRandom` không khả dụng hoặc phát sinh lỗi.

### 9.4. DRBG Java và các môi trường tuân thủ

Một số JVM hỗ trợ API `SecureRandom` với thuật toán **`DRBG`** theo provider. Khả năng cấu hình, mức an toàn và prediction-resistance/reseed phụ thuộc provider và nền tảng. Không nên tự viết DRBG trong application khi một API mật mã chuẩn đáp ứng mục tiêu; nếu có yêu cầu FIPS hoặc HSM, cần xét cụ thể **mô-đun, phiên bản, chế độ vận hành và chứng nhận**.

## 10. RNG trong container, serverless, VM, snapshot và hệ phân tán

### 10.1. Rủi ro khi sao chép trạng thái

Nếu một hệ thống tự quản lý PRNG/DRBG rồi **clone/snapshot trạng thái sau khi khởi tạo**, hai bản sao có thể tiếp tục từ cùng trạng thái và sinh trùng chuỗi bí mật. Điều này đặc biệt nguy hiểm với:

- Cặp khóa tạm của phiên TLS/ECDH;
- Token reset/password-recovery, session secret;
- AES-GCM nonce nếu cấu trúc nonce hoặc state bị sao chép;
- Khóa người dùng sinh tại thời điểm khởi động.

Các OS/runtime hiện đại có thể có cơ chế bảo vệ khi **fork, snapshot hoặc clone**, nhưng không nên mặc định mọi phiên bản JVM, thư viện native, driver HSM và bộ sinh tự viết đều xử lý đúng. Đối với sản phẩm có khởi tạo từ snapshot hoặc checkpoint/restore, cần **kiểm tra tài liệu của môi trường** và thử nghiệm hệ thống theo thiết kế.

### 10.2. Khởi động rất sớm

Một số môi trường nhúng, thiết bị IoT hoặc hệ điều hành mới khởi động có thể chưa có đủ entropy nếu nguồn được thiết kế yếu. Trong hệ thống hiện đại, API hệ điều hành thường có cơ chế kiểm soát trạng thái sẵn sàng của RNG; nhưng nếu firmware hoặc ứng dụng bỏ qua trạng thái đó để “tránh chờ”, có thể tạo khóa dự đoán được.

**Phản ứng đúng:** chờ nguồn được phép, báo lỗi hoặc từ chối cấp secret khi RNG không đáp ứng điều kiện. **Không fallback** sang timestamp, counter hay dữ liệu dễ đoán.

### 10.3. Nhiều node có cần dùng chung seed để đồng bộ không?

**Không.** Việc cố định seed “để mọi node sinh cùng khóa” là một lỗi kiến trúc nghiêm trọng. Nếu nhiều node phải sử dụng chung **một DEK**, khóa đó phải được **phát hành và phân phối qua KMS/HSM/secret-management** với quyền, phiên bản và audit; không đồng bộ bằng cách tái tạo private key từ một seed chung dễ lộ.

Nếu cần **mỗi node có secret riêng**, hãy tạo khóa riêng ở nơi phù hợp hoặc nhận key material từ dịch vụ quản lý khóa. Đối với nonce GCM, các node phải phối hợp **tính duy nhất theo cùng DEK**, không giả định ngẫu nhiên hoặc bộ đếm cục bộ đơn giản là bảo đảm tuyệt đối.

## 11. KMS/HSM và vòng đời khóa: bảo vệ từ điểm sinh khóa

**Key Management Service (KMS)** và **Hardware Security Module (HSM)** có thể giúp tập trung việc sinh, bảo vệ, sử dụng và kiểm toán khóa. Nhưng cần phân biệt:

- **Sinh khóa trong KMS/HSM:** Nhà cung cấp kiểm soát nguồn RNG/DRBG và các yêu cầu bảo vệ trong phạm vi dịch vụ/mô-đun.
- **Nhập khóa từ ứng dụng:** Nếu khóa đã được tạo bằng RNG yếu bên ngoài, việc nhập vào KMS/HSM **không khắc phục entropy ban đầu**.
- **Gọi API sinh DEK:** Một số KMS có thể trả DEK rõ kèm bản bọc; ứng dụng vẫn phải bảo vệ DEK khi sử dụng và giảm thời gian tồn tại trong RAM.
- **Khóa không xuất được:** KMS/HSM có thể hạn chế xuất private key và chỉ cho phép thao tác `Sign`, `Decrypt`, `Derive` theo loại khóa. Phải kiểm tra khả năng hỗ trợ thuật toán và chính sách sản phẩm.
- **Audit:** Ghi key ID, caller, mục đích, thời gian, trạng thái và kết quả; không log seed, key material, nonce bí mật khi giao thức yêu cầu bí mật hoặc token.

### Vòng đời và trách nhiệm

| Giai đoạn | Kiểm soát randomness | Kiểm soát quản lý khóa |
| --- | --- | --- |
| **Thiết kế** | Xác định mức an toàn, loại RNG, yêu cầu entropy, nonce | Owner, custodian, key usage, thuật toán và cryptoperiod |
| **Tạo khóa** | CSPRNG/DRBG đúng chuẩn, nguồn entropy đã đánh giá | KMS/HSM/keystore, key ID/version, hạn chế export |
| **Cấp phát** | Không sinh lại từ seed dùng chung/dễ đoán | Phân phối khóa đã tạo theo kênh được bảo vệ, cấp quyền tối thiểu |
| **Sử dụng** | Random nonce/IV hoặc counter đáp ứng mode; private ephemeral key không dự đoán | Chỉ đúng dịch vụ được `Sign`/`Decrypt`/`GenerateMac` |
| **Xoay vòng** | Sinh khóa mới thực sự độc lập, không tái dùng seed yếu | Thay key version, chuyển lưu lượng, giữ khả năng đọc dữ liệu cũ |
| **Thu hồi** | Đánh giá khóa nào bị ảnh hưởng bởi lỗi RNG | Chặn sử dụng, thu hồi chứng thư/grant, thông báo bên liên quan |
| **Hủy** | Không giữ seed/bản sao ngoài ý muốn | Xóa key material theo quy trình, kiểm soát backup và audit |

### Key owner, custodian và người dùng

**Key owner** xác định mức độ nhạy cảm, thuật toán, yêu cầu nguồn ngẫu nhiên và phương án xử lý khóa yếu. **Key custodian** vận hành KMS/HSM, thiết lập key policy, kiểm tra vùng bảo vệ, rotation và log. **Key user (ứng dụng)** sử dụng API tạo khóa/token đúng và không tự hạ cấp. **Security reviewer/auditor** đánh giá chứng cứ cấu hình RNG, sự cố entropy và việc xử lý các khóa được sinh trong thời gian lỗi.

**Separation of duties** vẫn cần thiết: người quản lý key policy không mặc nhiên được phép ký số hoặc xuất DEK. RNG mạnh không sửa được lỗi phân quyền, và IAM đúng không thể biến khóa đã tạo dự đoán được thành an toàn.

## 12. Hậu quả với envelope encryption, KDF và password hashing

### 12.1. Envelope encryption

Trong **envelope encryption**, một **DEK ngẫu nhiên** mã hóa dữ liệu bằng AES-GCM, còn **KEK** trong KMS/HSM bọc DEK. Có hai vấn đề ngẫu nhiên riêng:

1. **DEK phải được sinh bằng CSPRNG phù hợp.** Nếu DEK dễ đoán, dù được bọc bởi KEK mạnh, kẻ tấn công vẫn có thể tự thử DEK ứng viên đối với ciphertext.
2. **Nonce GCM của từng lần mã hóa** phải được quản lý không lặp dưới cùng DEK. Một DEK mạnh không ngăn lỗi reuse nonce.

Nếu KEK là khóa đối xứng được tạo ngẫu nhiên, bản thân KEK cũng cần nguồn an toàn. **Xoay KEK** có thể chỉ yêu cầu rewrap DEK; nếu **DEK bị nghi yếu hoặc đã lộ**, chỉ rewrap DEK không khắc phục được rủi ro — cần đánh giá **thay DEK và mã hóa lại dữ liệu**.

### 12.2. KDF không “sửa” được entropy bị thiếu

**HKDF** là công cụ dẫn xuất khóa từ secret thích hợp và giúp phân tách mục đích, nhưng **không tự tạo entropy mới** từ seed ít khả năng. Nếu một shared secret ECDH bị đối thủ đoán được do private key tạm được sinh yếu, HKDF trên shared secret đó không khôi phục tính bí mật phiên.

Với **mật khẩu do con người chọn**, dùng password KDF như Argon2id, scrypt hoặc PBKDF2 theo chính sách để làm chậm đoán offline. Nhưng các KDF này cũng **không biến một mật khẩu yếu thành entropy tương đương key random 256 bit**. Muốn sinh khóa AES độc lập, nên dùng CSPRNG hoặc dịch vụ tạo khóa được chấp thuận.

### 12.3. Salt không phải secret

Salt cho password hashing thường **không cần khó dự đoán**, nhưng nên **độc lập/riêng biệt theo bản ghi và mục đích** theo thiết kế. CSPRNG là cách phổ biến tạo salt mới tránh trùng; salt có thể lưu cùng hash và KDF parameters.

**Không dùng duy nhất salt làm bằng chứng xác thực**, và không nhầm salt với **pepper** — bí mật cấp hệ thống nếu thiết kế sử dụng.

## 13. Phát hiện, ứng cứu và khắc phục sự cố RNG

Giả sử nhóm bảo mật phát hiện một bản firmware từng sinh private key tại thời điểm boot bằng PRNG khởi tạo từ timestamp. Số thiết bị bị ảnh hưởng có thể lên tới hàng nghìn; public key tương ứng đã được đăng ký với hệ thống.

**Không đủ** để sửa firmware trên các thiết bị mới. Các khóa đã sinh trước khi sửa **vẫn có thể yếu**.

### Runbook khái niệm

1. **Xác định phạm vi:** Phiên bản ứng dụng/firmware/JVM, thời điểm triển khai, vùng, tenant và loại key/token được sinh bởi RNG liên quan.
2. **Cô lập nguồn lỗi:** Ngừng cấp khóa/token mới qua đường RNG yếu, nâng cấp nguồn/thư viện, chặn fallback và xác minh hệ thống ổn định.
3. **Đánh giá dữ liệu đã phát hành:** Phân loại DEK/KEK, private signing key, ECDH key, session token, reset token, IV/nonce và các bản backup trong giai đoạn lỗi.
4. **Thu hồi/thay thế:** Tạo key material mới **độc lập từ CSPRNG đã sửa**; cập nhật public key/chứng thư, grant và key version; vô hiệu hóa token cũ theo mức độ rủi ro.
5. **Bảo vệ dữ liệu lịch sử:** Nếu DEK yếu, đánh giá giải mã trái phép đã có thể xảy ra và mã hóa lại dữ liệu; nếu chỉ KEK bị nghi yếu, xem xét cả các DEK được bọc và dữ liệu liên quan.
6. **Ảnh hưởng chữ ký:** Nếu private signing key yếu hoặc nonce ECDSA bị ảnh hưởng, lập danh mục chữ ký/chứng thư, đánh giá nguy cơ giả mạo và yêu cầu xác minh lại/thu hồi theo chính sách.
7. **Audit và thông báo:** Bảo toàn log an toàn, mốc thời gian, key inventory và quyết định xử lý; thông báo bên phụ thuộc và chủ sở hữu dữ liệu khi cần.
8. **Kiểm thử ngăn tái diễn:** Bổ sung yêu cầu review RNG trong security checklist, kiểm tra cấu hình provider, xử lý lỗi entropy và kiểm thử môi trường snapshot/clone nếu liên quan.

### Rủi ro không thể “xoay khóa là xong”

Nếu đối thủ đã lưu ciphertext khi DEK yếu, việc thay DEK hôm nay không thể bảo đảm đối thủ chưa giải mã bản mã cũ. Nếu private signing key bị tái tạo được, chữ ký tạo trong giai đoạn đó có thể cần phân tích nguồn gốc và niềm tin. Nếu lỗi RNG gây **nonce GCM trùng**, việc thay khóa cho bản mã mới **không sửa được các bản mã đã bị mã hóa sai**.

Kế hoạch ứng cứu phải đánh giá **tác động quá khứ**, không chỉ ngăn tái phát.

## 14. Rủi ro thực tế và cách phòng ngừa

| Lỗi thiết kế/triển khai | Hậu quả có thể xảy ra | Cách phòng ngừa |
| --- | --- | --- |
| Dùng `java.util.Random` sinh private key hoặc bearer token | Token/khóa dự đoán được | `SecureRandom`, JCA KeyGenerator/KeyPairGenerator, KMS/HSM |
| Seed PRNG từ timestamp hoặc PID | Không gian seed hẹp | Dùng entropy source được đánh giá; không tự seed yếu |
| Hash seed yếu thành 32 byte rồi coi là 256 bit entropy | Đánh giá sai độ an toàn | Phân tích entropy của đầu vào, không chỉ độ dài đầu ra |
| Seed cố định để nhiều node “dùng cùng secret” | Các node có thể lộ/giống key và token | Phân phối key qua KMS/secret manager có kiểm soát |
| Dùng PRNG tùy biến trong VM snapshot | Sao chép trạng thái, trùng đầu ra | Dựa vào OS CSPRNG và quy tắc snapshot/fork đã đánh giá |
| Tự chọn private scalar ECC hoặc prime RSA | Khóa không đạt bảo đảm thuật toán | Provider/hardware key generation chuẩn |
| Tự sinh k ECDSA bằng RNG yếu | Nguy cơ lộ private signing key | Thư viện ký chuẩn, deterministic nonce đúng chuẩn khi phù hợp |
| Dùng nonce GCM trùng dưới cùng DEK | Rò rỉ plaintext và suy yếu tag | Cấp nonce duy nhất, giám sát giới hạn mỗi key |
| Dùng IV CBC dễ dự đoán | Mất yêu cầu bảo mật của CBC | IV khó dự đoán từ CSPRNG, kèm xác thực |
| Cho rằng salt phải giữ bí mật, bỏ qua chất lượng key | Nhầm ưu tiên bảo mật | Salt riêng, key material bí mật và đủ entropy |
| Fallback từ CSPRNG sang Random khi RNG lỗi | Tạo hàng loạt secret yếu | Fail closed, cảnh báo và khắc phục môi trường |
| Dùng số ngẫu nhiên trong unit test rồi bê seed cố định vào production | Secret trùng/lộ giữa các phiên bản | Tách test RNG khỏi production, review cấu hình |
| Tin rằng KMS có thể chữa DEK được nhập từ RNG yếu | Đối thủ vẫn có thể tái tạo DEK | Tạo khóa mới từ nguồn an toàn và đánh giá mã hóa lại |
| Kiểm tra histogram rồi công bố RNG “an toàn” | Bỏ sót khả năng suy luận trạng thái/seed | Đánh giá thuật toán, entropy source, kiểm soát vận hành |
| Log seed, private key, token hoặc DRBG state khi debug | Mất tính bí mật của nguồn/đầu ra | Không ghi bí mật, lọc logs và hạn chế dump |

## 15. Checklist chọn RNG và quản lý khóa cho production

1. **Mục đích:** Giá trị cần sinh là **key/private scalar/token bí mật**, **IV CBC**, **nonce GCM**, **salt** hay **ID công khai**? Đã xác định yêu cầu riêng cho từng loại chưa?
2. **API:** Có dùng CSPRNG/DRBG đáng tin và API tạo khóa chuẩn? Không có `Random`, `ThreadLocalRandom`, `SplittableRandom` hoặc seed cố định trong luồng sinh secret?
3. **Nguồn entropy:** Nền tảng/JVM/provider được cập nhật, có cơ chế khởi tạo an toàn; các yêu cầu từ entropy source được nhà cung cấp công bố và đánh giá?
4. **Seed/reseed:** Không tự seed bằng timestamp/PID; không trông chờ một lần hash hay KDF tạo entropy; hiểu cơ chế reseed theo provider?
5. **Môi trường:** VM/container/serverless, snapshot, fork, clone, thiết bị khởi động sớm hoặc môi trường air-gapped có rủi ro sao chép trạng thái/thiếu entropy?
6. **Khóa AES/DEK/KEK:** Được sinh đủ độ dài và entropy, bảo vệ bằng KMS/HSM/keystore; có key ID/version và cơ chế rotation/backup?
7. **Khóa RSA/ECC:** Tạo bằng `KeyPairGenerator`/HSM/KMS theo thuật toán chuẩn; private key không cần xuất và public key được phân phối tin cậy?
8. **Chữ ký số:** ECDSA nonce được provider xử lý đúng, private signing key và quyền `Sign` được bảo vệ; không tự thiết kế nonce?
9. **Thỏa thuận khóa:** Private ephemeral key được tạo độc lập và xóa khi hết dùng; các kỳ vọng forward secrecy có cơ sở?
10. **Nonce và IV:** Với GCM/CTR có cơ chế không lặp dưới cùng key và không tràn counter; CBC có IV khó dự đoán? Có xử lý retry và đa node?
11. **Token:** Reset token/bearer secret đủ entropy, TTL, hạn mức, one-time-use theo mục đích, không xuất hiện trong URL log, analytics hay crash dump?
12. **Mật khẩu/KDF:** Password hash dùng password KDF với salt; không dùng HKDF hoặc SHA-256 đơn lẻ để “làm mạnh” password; không dùng password verifier làm DEK?
13. **KMS/HSM và quyền:** Key owner/custodian, IAM least privilege, duyệt tạo/nhập/xuất/rotation và audit có được áp dụng? Có đánh giá nguồn của **imported key material**?
14. **Giám sát:** Có cảnh báo lỗi RNG, entropy source/DRBG theo cơ chế nhà cung cấp, key creation bất thường và cấu hình RNG thay đổi?
15. **Ứng cứu:** Nếu phát hiện RNG yếu, có inventory để xác định key/token/nonce đã sinh trong thời gian lỗi, thay thế và đánh giá bản mã/chữ ký lịch sử?
16. **Kiểm thử:** Test có thể dùng seed cố định để tái lập, nhưng môi trường production có guardrails để không tái sử dụng các seed đó? Có code review ngăn fallback yếu?

### Ghi nhớ

**Predictable randomness** làm vô hiệu nhiều bảo đảm mật mã từ điểm khởi đầu: **khóa AES/RSA/ECC có thể đoán được, ECDHE mất bí mật phiên, nonce ECDSA yếu có thể làm lộ private signing key, reset token trở nên dễ đoán**. Để sinh secret, dùng **CSPRNG/DRBG và entropy source đáng tin** qua API chuẩn như Java `SecureRandom`, `KeyGenerator`, `KeyPairGenerator` hoặc KMS/HSM; không dùng `Random`, seed timestamp hay nguồn ít entropy. Đồng thời phải phân biệt **bí mật và tính không lặp**: key/token cần khó đoán, GCM nonce cần không lặp, CBC IV cần khó dự đoán, còn salt thường không cần bí mật. Một thiết kế quản lý khóa đúng phải gắn chất lượng randomness với **KMS/HSM, AEAD/envelope encryption, chữ ký số, quyền sử dụng, rotation, thu hồi, hủy và kiểm toán**; lưu khóa yếu trong phần cứng an toàn về sau không tự khắc phục được lỗi sinh khóa.
