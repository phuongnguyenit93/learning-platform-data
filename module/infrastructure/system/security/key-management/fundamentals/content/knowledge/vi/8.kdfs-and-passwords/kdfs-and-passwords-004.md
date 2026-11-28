# scrypt (Hàm dẫn xuất khóa dựa trên mật khẩu có chi phí bộ nhớ)

## 1. scrypt là gì?

**scrypt** là một **hàm dẫn xuất khóa từ mật khẩu** (*password-based key derivation function – password KDF*) được thiết kế để làm cho việc thử đoán mật khẩu hàng loạt trở nên tốn **thời gian tính toán và bộ nhớ**. Đầu vào phổ biến của scrypt là mật khẩu, **salt**, các tham số chi phí **N, r, p** và độ dài đầu ra; kết quả là một chuỗi byte được dẫn xuất.

Hai ứng dụng quan trọng:

1. **Lưu bộ kiểm tra mật khẩu (password verifier):** hệ thống lưu kết quả scrypt cùng salt và các tham số, rồi tính lại khi người dùng đăng nhập. Không lưu mật khẩu rõ.
2. **Dẫn xuất khóa từ passphrase:** hệ thống có thể dùng scrypt để tạo bí mật dùng bảo vệ một khóa dữ liệu khác, ví dụ **password-derived KEK** bọc **DEK** trong envelope encryption.

~~~text
Mật khẩu / passphrase
          |
          |    salt (công khai), N, r, p
          v
        scrypt
          |
          v
   Derived key bytes (dkLen)
          |
          +--> Password verifier để đối chiếu khi đăng nhập
          |
          +--> Bí mật đầu vào cho cơ chế bảo vệ khóa dữ liệu
               (cần thiết kế giao thức, thuật toán và metadata phù hợp)
~~~

**scrypt không tự mã hóa dữ liệu, không tạo chữ ký số và không xác thực nguồn gốc một thông điệp.** Nó tạo ra vật liệu khóa hoặc giá trị dùng kiểm tra mật khẩu. Muốn mã hóa nội dung cần thuật toán như AES-GCM với khóa được quản lý đúng; muốn ký số cần private signing key của thuật toán như ECDSA hoặc Ed25519.

Trong chương **KDF và mật khẩu** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, scrypt giúp hiểu cách bảo vệ khóa được dẫn xuất từ bí mật có entropy thấp và kết nối vấn đề này với **vòng đời khóa, KMS/HSM, envelope encryption, phân quyền và kiểm toán**.

## 2. Vì sao mật khẩu không thể dùng trực tiếp làm khóa AES?

Mật khẩu do con người chọn thường chứa **ít entropy thực tế** hơn một khóa ngẫu nhiên 128/256 bit. Độ dài ký tự không tự nói lên tính khó đoán: một chuỗi dài nhưng có mẫu phổ biến vẫn có thể bị đoán bằng từ điển hoặc quy tắc sinh ứng viên.

Nếu dùng trực tiếp cách làm sau:

~~~text
AES_key = SHA256(password)
~~~

thì SHA-256 chạy rất nhanh. Kẻ tấn công lấy được bản mã hoặc verifier có thể thử nhiều mật khẩu ứng viên một cách hiệu quả. Dù SHA-256 tạo 256 bit đầu ra, phép băm **không thể tự bổ sung entropy mà mật khẩu ban đầu không có**.

Một password KDF như scrypt giải quyết vấn đề khác: mỗi lần thử một ứng viên cần tiêu tốn tài nguyên đáng kể. Nó **không biến mật khẩu yếu thành bí mật có entropy bằng khóa được sinh bằng CSPRNG**, nhưng tăng chi phí cho kẻ tấn công có dữ liệu để thử đoán ngoại tuyến.

| Đầu vào | Mục đích | Công cụ tiêu biểu |
|---|---|---|
| Mật khẩu người dùng, entropy thường thấp | Lưu mật khẩu an toàn trước tấn công offline | Argon2id, scrypt hoặc PBKDF2 trong bối cảnh phù hợp |
| Passphrase cần tạo khóa để bảo vệ tệp | Kéo giãn mật khẩu thành vật liệu khóa với chi phí chống đoán | scrypt/Argon2id và một giao thức mã hóa được thiết kế rõ ràng |
| Bí mật mật mã đã có entropy cao | Dẫn xuất nhiều khóa phục vụ các mục đích độc lập | HKDF với ngữ cảnh phân tách |
| Hạt giống ngẫu nhiên cần khóa AES | Sinh hoặc dẫn xuất khóa từ nguồn ngẫu nhiên được tin cậy | CSPRNG/KMS/HSM/KDF chuẩn theo giao thức |

**Không dùng HKDF thay cho password hashing** khi đầu vào là mật khẩu yếu; HKDF được thiết kế chủ yếu để xử lý vật liệu khóa thích hợp, không nhằm làm mỗi lần đoán mật khẩu tốn bộ nhớ như scrypt.

## 3. Memory-hard là gì?

Một thuật toán được mô tả là **memory-hard** khi việc tính toán hiệu quả cần một lượng bộ nhớ đáng kể; cố tiết kiệm bộ nhớ thường phải đổi lấy thêm công việc tính toán. scrypt khai thác đặc điểm này để làm tăng chi phí thực hiện nhiều phép đoán mật khẩu song song trên phần cứng chuyên dụng.

~~~mermaid
flowchart TD
    A["Kẻ tấn công có salt + verifier"] --> B["Tạo các ứng viên mật khẩu"]
    B --> C["Mỗi ứng viên phải chạy scrypt"]
    C --> D["Tiêu tốn CPU và bộ nhớ theo N, r, p"]
    D --> E{"Kết quả khớp verifier?"}
    E -->|Không| B
    E -->|Có| F["Tìm được một ứng viên khớp"]
~~~

Điểm khác so với một phép SHA-256 đơn lẻ:

- **Chi phí CPU:** phép thử mật khẩu mất nhiều thao tác hơn.
- **Chi phí bộ nhớ:** nhiều phép thử đồng thời cần thêm bộ nhớ, tạo áp lực cho GPU/ASIC và cả máy chủ hợp pháp.
- **Chi phí cấu hình được:** người triển khai điều chỉnh tham số trong giới hạn của thuật toán và hạ tầng.

Memory-hard **không đồng nghĩa bất khả xâm phạm**. Nếu người dùng chọn mật khẩu cực kỳ phổ biến, kẻ tấn công vẫn có thể thử thành công; nếu cấu hình quá yếu, chi phí thử đoán thấp; nếu cấu hình quá cao, chính dịch vụ có thể cạn CPU/RAM khi có nhiều yêu cầu đăng nhập.

## 4. Đầu vào và đầu ra của scrypt

scrypt thường được biểu diễn bằng ký hiệu:

\[
\operatorname{scrypt}(P,S,N,r,p,\mathrm{dkLen}) \longrightarrow DK
\]

| Thành phần | Ý nghĩa | Có bí mật không? |
|---|---|---|
| **P** | Password/passphrase được quy đổi thành byte theo quy tắc thống nhất | **Có** |
| **S (salt)** | Giá trị ngẫu nhiên, thông thường duy nhất theo mỗi bản ghi | **Không** |
| **N** | Cost parameter, chi phối số bước/chi phí bộ nhớ, là lũy thừa của 2 hợp lệ | Không |
| **r** | Block-size parameter | Không |
| **p** | Parallelization parameter; góp phần điều chỉnh công việc | Không |
| **dkLen** | Độ dài khóa đầu ra tính bằng byte | Không |
| **DK** | Derived key bytes, hoặc giá trị verifier lưu lại tùy mục đích | Cần bảo vệ theo vai trò cụ thể |

**Salt khác mật khẩu**: salt được tạo bằng nguồn ngẫu nhiên phù hợp, lưu cùng tham số và đầu ra. Salt không thay thế cho mật khẩu bí mật và cũng không nhất thiết phải đưa vào KMS.

**N, r, p không phải bí mật.** Chúng phải được lưu để biết cách tính lại scrypt cho dữ liệu cũ. Với password verifier, thường lưu cùng bản ghi một định dạng mô tả thuật toán, phiên bản, tham số, salt và derived bytes.

Ví dụ metadata khái niệm:

~~~yaml
# Ví dụ mô tả, không phải format chuẩn dùng chung của mọi thư viện.
algorithm: scrypt
profileVersion: 1
N: 32768
r: 8
p: 1
dkLen: 32
saltBase64: "<salt ngau nhien, da ma hoa Base64>"
derivedBase64: "<ket qua scrypt, da ma hoa Base64>"
~~~

Không lưu plaintext password. **Không dùng một chuỗi secret đặt trong file cấu hình làm salt chung cho toàn bộ người dùng.** Salt nên khác nhau cho các bản ghi mật khẩu mới, kể cả khi hai người dùng chọn cùng mật khẩu.

## 5. Vai trò của N, r, p và dkLen

Ba tham số chính cần hiểu đúng vì chúng quyết định chi phí vận hành:

| Tham số | Tác động khái quát | Lưu ý thiết kế |
|---|---|---|
| **N** | Tăng chi phí CPU/bộ nhớ của phép trộn | Phải thuộc miền giá trị hợp lệ, thường là lũy thừa 2 lớn hơn 1 |
| **r** | Điều chỉnh kích cỡ khối và lượng bộ nhớ | Kết hợp với N tác động mạnh đến RAM mỗi phép tính |
| **p** | Điều chỉnh số nhánh công việc, thường tăng tổng công việc gần tỉ lệ p | Tăng p không đồng nghĩa mọi thư viện bắt buộc cấp p lần RAM theo công thức đơn giản |
| **dkLen** | Chọn chiều dài byte kết quả | Chiều dài đầu ra không làm tăng entropy mật khẩu |

Với triển khai scrypt thường gặp, **bộ nhớ trọng tâm** cho pha trộn khoảng:

\[
M_{\mathrm{ROMix}} \approx 128 \times N \times r\ \text{byte}.
\]

Đây là **ước lượng** cho phần bộ nhớ chính của một công việc ROMix, không phải đo chính xác peak RSS của mọi thư viện. Các mảng trung gian, cấu trúc runtime, giá trị p và số lời gọi song song có thể làm mức sử dụng thực tế cao hơn.

Một số ví dụ khi **r = 8, p = 1**:

| N | Bộ nhớ ROMix xấp xỉ | Cách hiểu |
|---|---:|---|
| 2¹⁴ = 16.384 | 16 MiB | Minh họa mức tài nguyên nhỏ hơn |
| 2¹⁵ = 32.768 | 32 MiB | Cấu hình minh họa trong mã Java bên dưới |
| 2¹⁷ = 131.072 | 128 MiB | Bộ nhớ tăng gấp 4 lần so với N = 2¹⁵ |

Công việc tính toán thường tăng theo bậc gần **N × r × p** trong phạm vi các cấu hình và cách triển khai thông thường. Nếu tăng N gấp đôi thì phần bộ nhớ ROMix và phần công việc tương ứng cũng tăng đáng kể; nhưng không thể suy trực tiếp **độ trễ chính xác** nếu chưa đo trên hạ tầng thật.

**Không có một bộ N/r/p tối ưu cho mọi hệ thống.** Hãy chọn theo mục đích (đăng nhập hay giải mã tệp), khả năng CPU/RAM, số lần gọi đồng thời, yêu cầu an toàn và chính sách được phê duyệt. Ví dụ 32 MiB trong tài liệu này dùng để hiểu cơ chế, **không phải khuyến nghị mặc định cho mọi ứng dụng sản xuất**.

### 5.1. Chi phí nhiều đăng nhập đồng thời

Nếu một phép scrypt dùng khoảng 32 MiB RAM ROMix, **100 phép kiểm tra chạy thực sự đồng thời** có thể đòi hỏi khoảng **3,1 GiB chỉ cho phần bộ nhớ chính**, chưa tính JVM, request buffers và phần mềm khác. Cần giới hạn concurrency hoặc cấp tài nguyên phù hợp để tránh làm dịch vụ tự cạn RAM.

Ngược lại, giảm tham số quá mức để tăng thông lượng khiến kẻ tấn công có cơ sở dữ liệu verifier thực hiện nhiều phép thử offline rẻ hơn. Đây là đánh đổi phải được đo đạc và quyết định rõ ràng.

## 6. scrypt hoạt động bên trong ra sao?

Ở mức thuật toán, scrypt được chuẩn hóa trong **RFC 7914**. Trong cấu trúc điển hình, nó kết hợp **PBKDF2-HMAC-SHA-256** với pha **ROMix**, trong đó **BlockMix** sử dụng **Salsa20/8**.

~~~mermaid
flowchart TD
    P["Password bytes P"] --> K1["PBKDF2-HMAC-SHA256 ban đầu"]
    S["Salt S"] --> K1
    K1 --> B["Tạo các khối B"]
    B --> R["ROMix / BlockMix(Salsa20/8)"]
    R --> K2["PBKDF2-HMAC-SHA256 cuối"]
    P --> K2
    K2 --> DK["DK: derived bytes có chiều dài dkLen"]
~~~

Mục tiêu của pha ROMix là buộc thuật toán thực hiện một chuỗi thao tác dựa vào bộ nhớ tương đối lớn. Vì vậy, **scrypt không thể mô tả đúng bằng cách lặp SHA-256 N lần**.

Điều cần nhớ:

- Không cần tự cài đặt Salsa20/8, PBKDF2 hoặc ROMix để sử dụng scrypt; chọn **thư viện mật mã được kiểm chứng**.
- Thuật toán được xác định bởi **cả bộ tham số**. Cùng mật khẩu và salt nhưng N/r/p/dkLen khác nhau thường cho kết quả khác.
- Chuỗi byte đầu vào của mật khẩu rất quan trọng. Hai hình thức Unicode được hiển thị giống nhau nhưng mã hóa khác có thể cho DK khác.
- Dùng **UTF-8 và chính sách chuẩn hóa** rõ ràng giữa đăng ký, đăng nhập và khôi phục. Không tự ý đổi chính sách chuẩn hóa sau khi đã lưu verifier mà không có kế hoạch tương thích.

## 7. Salt, pepper và nonce: ba khái niệm khác nhau

| Thuật ngữ | Dùng ở đâu | Có giữ bí mật? | Quy tắc chính |
|---|---|---|---|
| **Salt của scrypt** | Bảo vệ password verifier/khóa dẫn xuất | Không | Ngẫu nhiên, thường duy nhất cho từng bản ghi mật khẩu |
| **Pepper** | Bí mật bổ sung do server quản lý trong một số kiến trúc lưu mật khẩu | Có | Lưu ngoài DB verifier, ví dụ secret store/KMS/HSM, quản lý quyền và rotation |
| **Nonce/IV của AES-GCM** | Chọn phép mã hóa AEAD cho từng message dưới DEK | Không nhất thiết | **Không tái sử dụng với cùng khóa AES-GCM** |
| **Nonce k của ECDSA** | Tham số bí mật riêng cho lần ký | **Có** | Không lộ hoặc tái sử dụng sai cách giữa các thông điệp |

### 7.1. Salt giải quyết vấn đề gì?

Giả sử hai tài khoản cùng chọn một mật khẩu. Nếu không có salt, chúng có thể tạo cùng verifier; kẻ tấn công có thể tận dụng phép tính băm/derivation đã làm cho nhiều tài khoản.

Với **salt ngẫu nhiên độc lập**, hai lần tính scrypt thường cho hai DK khác nhau. Salt cũng làm giảm khả năng dùng bảng kết quả tính sẵn để tấn công nhiều cơ sở dữ liệu.

**Salt không có nhiệm vụ làm tăng độ khó bí mật của mật khẩu bằng cách giấu giá trị salt**. Salt được lưu cùng kết quả và có thể công khai. Kẻ tấn công vẫn có thể thử mật khẩu cho từng bản ghi; điểm bảo vệ là phép thử phải trả chi phí scrypt với salt đó.

Thông thường nên sinh salt bằng **CSPRNG**, ví dụ 16 byte (128 bit) cho một bản ghi mới. Cần đánh giá chính sách và định dạng của thư viện cụ thể nếu chúng có yêu cầu khác.

### 7.2. Pepper có bắt buộc không?

**Pepper** là một bí mật bổ sung được giữ riêng với cơ sở dữ liệu password verifier nhằm bổ sung một lớp kiểm soát. Nó **không thay thế scrypt, salt ngẫu nhiên hoặc mật khẩu mạnh**. Dùng pepper đòi hỏi thiết kế chính xác: ví dụ một bước HMAC được xác định rõ trước/sau password hashing theo chính sách, bảo vệ khóa pepper trong KMS/HSM và có kế hoạch xoay vòng.

Nếu mất pepper nhưng không thể tính lại verifier, hệ thống có thể phải yêu cầu người dùng đổi mật khẩu hoặc thực hiện migration phức tạp. Không tự đưa một chuỗi "pepper" vào công thức tùy tiện mà không đánh giá giao thức.

## 8. Lưu mật khẩu đăng nhập bằng scrypt

Quy trình điển hình khi **đăng ký**:

1. Nhận mật khẩu qua kênh truyền bảo mật và xử lý theo chính sách encoding.
2. Sinh **salt mới độc lập** bằng CSPRNG cho mật khẩu đó.
3. Chọn một **profile N/r/p/dkLen** đã được benchmark và cho phép.
4. Chạy scrypt để tạo verifier.
5. Lưu **algorithm/version, N, r, p, salt và verifier**. Không lưu plaintext password.

Quy trình **đăng nhập**:

1. Đọc profile và salt của tài khoản.
2. Kiểm tra profile thuộc **danh sách cấu hình được phép**, không chấp nhận N/r/p tùy ý không giới hạn từ dữ liệu bị sửa.
3. Chạy scrypt trên mật khẩu người dùng nhập với salt và tham số đã lưu.
4. So sánh kết quả với verifier đã lưu bằng API so sánh phù hợp, tránh rò rỉ timing không cần thiết.
5. Thực hiện kiểm tra tài khoản, **rate limiting, kiểm soát đăng nhập bất thường và MFA nếu áp dụng**.
6. Nếu verifier đang dùng profile cũ, cân nhắc **rehash với tham số mới và salt mới sau khi đăng nhập thành công** theo kế hoạch nâng cấp.

~~~mermaid
flowchart LR
    P["Password nhập"] --> S["scrypt với salt + profile đã lưu"]
    DB["Verifier + salt + N/r/p/version trong DB"] --> S
    S --> V["So sánh derived bytes"]
    V --> D{"Khớp?"}
    D -->|Không| X["Từ chối, ghi log an toàn"]
    D -->|Có| A["Kiểm tra tài khoản và policy"]
    A --> R["Đăng nhập / rehash nếu cần"]
~~~

**Lưu ý bảo mật:** Không nên coi password verification thành công là đủ để bỏ qua **khóa tài khoản, kiểm soát phiên, MFA, phòng chống credential stuffing, giám sát và audit**. scrypt chủ yếu nâng chi phí của **tấn công offline khi dữ liệu verifier bị lấy**, không tự bảo vệ trước hàng triệu yêu cầu login trực tiếp.

## 9. Java: dùng scrypt với Bouncy Castle

**Java Standard Edition không bảo đảm có thuật toán scrypt như một dịch vụ JCA bắt buộc.** Muốn dùng scrypt trong Java, cần thư viện/provider thích hợp. Ví dụ dưới đây dùng **Bouncy Castle** với lớp **org.bouncycastle.crypto.generators.SCrypt**. Thêm dependency **org.bouncycastle:bcprov-jdk18on** bằng phiên bản được dự án kiểm tra và phê duyệt trước khi chạy.

**Ví dụ Java 17+** sau minh họa tạo verifier và kiểm tra mật khẩu với một profile cố định:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import org.bouncycastle.crypto.generators.SCrypt;

public final class ScryptPasswordExample {
    private static final SecureRandom RANDOM = new SecureRandom();

    // Giá trị minh họa; cần benchmark và chọn profile phù hợp.
    private static final int N = 1 << 15;  // 32768
    private static final int R = 8;
    private static final int P = 1;
    private static final int DK_LEN = 32;
    private static final int SALT_LEN = 16;

    public record StoredVerifier(
            int n, int r, int p, String saltB64, String derivedB64) {}

    public static StoredVerifier register(byte[] passwordUtf8) {
        byte[] salt = new byte[SALT_LEN];
        RANDOM.nextBytes(salt);

        byte[] derived = SCrypt.generate(
            passwordUtf8, salt, N, R, P, DK_LEN
        );
        try {
            return new StoredVerifier(
                N, R, P,
                Base64.getEncoder().encodeToString(salt),
                Base64.getEncoder().encodeToString(derived)
            );
        } finally {
            Arrays.fill(derived, (byte) 0);
        }
    }

    public static boolean verify(
            byte[] passwordUtf8, StoredVerifier stored) {
        // Ví dụ chỉ hỗ trợ một profile. Không nhận tham số tùy ý
        // từ bản ghi không đáng tin để tránh DoS CPU/RAM.
        if (stored.n() != N || stored.r() != R || stored.p() != P) {
            throw new IllegalArgumentException("Unsupported scrypt profile");
        }

        byte[] salt = Base64.getDecoder().decode(stored.saltB64());
        byte[] expected =
            Base64.getDecoder().decode(stored.derivedB64());
        if (salt.length != SALT_LEN || expected.length != DK_LEN) {
            throw new IllegalArgumentException("Invalid stored verifier");
        }

        byte[] actual = SCrypt.generate(
            passwordUtf8, salt, N, R, P, DK_LEN
        );
        try {
            return MessageDigest.isEqual(expected, actual);
        } finally {
            Arrays.fill(actual, (byte) 0);
            Arrays.fill(expected, (byte) 0);
        }
    }

    public static void main(String[] args) {
        byte[] password = "demo-only-not-a-real-secret"
            .getBytes(StandardCharsets.UTF_8);
        try {
            StoredVerifier record = register(password);
            if (!verify(password, record)) {
                throw new IllegalStateException("Verification failed");
            }

            byte[] incorrect = "wrong-demo-password"
                .getBytes(StandardCharsets.UTF_8);
            try {
                if (verify(incorrect, record)) {
                    throw new IllegalStateException("Wrong password accepted");
                }
            } finally {
                Arrays.fill(incorrect, (byte) 0);
            }
            System.out.println("scrypt verifier OK");
        } finally {
            Arrays.fill(password, (byte) 0);
        }
    }
}
~~~

### 9.1. Phân tích ví dụ

- **SCrypt.generate** nhận **password bytes, salt, N, r, p, dkLen** và trả derived bytes. Đây là API của Bouncy Castle, không phải method chuẩn sẵn có trong **MessageDigest**.
- Định dạng **StoredVerifier** chỉ là mô hình lưu dữ liệu minh họa. Dự án thật cần format/serializer có phiên bản, kiểm tra schema và giới hạn kích thước.
- **Salt được sinh bằng SecureRandom** và lưu dưới dạng Base64. Base64 là phép **mã hóa biểu diễn**, không phải mã hóa giữ bí mật.
- **MessageDigest.isEqual** dùng để so sánh derived bytes; cần kiểm tra độ dài và chính sách algorithm trước đó.
- **Ví dụ chỉ hỗ trợ một profile cố định** nhằm tránh việc nhận một record có N rất lớn từ đầu vào không tin cậy. Triển khai production cần **profile registry có phiên bản**, giới hạn tài nguyên và con đường nâng cấp verifier cũ.
- Mã dùng **byte[] passwordUtf8** để làm rõ đầu vào mật mã là byte. Tầng thu nhận mật khẩu cần xử lý Unicode, thời gian tồn tại dữ liệu nhạy cảm và sự khác biệt giữa char[]/byte[] một cách nhất quán.
- **Arrays.fill** chỉ giảm thời gian tồn tại của những mảng do ứng dụng quản lý; không bảo đảm xóa mọi bản sao bí mật trong JVM/nhà cung cấp.
- Đoạn **main** dùng mật khẩu giả phục vụ demo; tuyệt đối không nhúng mật khẩu thật vào mã nguồn.

### 9.2. Chọn profile và kiểm soát đầu vào

Trước khi đưa vào production, nên:

1. Benchmark thời gian scrypt trên hạ tầng thật, bao gồm **p95/p99 khi nhiều login đồng thời**.
2. Xác định giới hạn CPU/RAM cho endpoint login và quy tắc rate limiting.
3. Lưu profile version trong DB; giới hạn các tham số mà hệ thống thực sự hỗ trợ.
4. Thiết kế migration khi tăng chi phí; không tự thay tham số của verifier cũ rồi mong phép kiểm tra vẫn khớp.
5. Áp dụng logging an toàn: **không log password, derived bytes hay bí mật pepper**.
6. Kiểm thử cả mật khẩu Unicode, byte encoding, mật khẩu rất dài, dữ liệu lưu sai định dạng và yêu cầu đồng thời.

**Cảnh báo:** Đối với mật khẩu người dùng, **Argon2id** là lựa chọn hiện đại rất đáng cân nhắc khi có thư viện được đánh giá và chính sách cho phép. **scrypt** vẫn là phương án memory-hard phù hợp trong nhiều hệ thống; **PBKDF2** có thể cần thiết ở môi trường có yêu cầu tương thích/tuân thủ riêng. Chọn theo threat model và tiêu chuẩn hệ thống, không theo tên thuật toán đơn lẻ.

## 10. Dẫn xuất khóa để mã hóa tệp bằng passphrase

scrypt cũng có thể được dùng khi một người cần mở tệp mã hóa bằng **passphrase**. Thiết kế nên tách rõ:

- **Passphrase:** bí mật do con người ghi nhớ, entropy hạn chế.
- **Salt + tham số scrypt:** metadata công khai, giúp dẫn xuất password-derived key.
- **Password-derived KEK:** khóa bí mật dùng để bảo vệ **DEK**.
- **DEK:** khóa ngẫu nhiên sinh bằng CSPRNG để mã hóa dữ liệu bằng AES-GCM.
- **Nonce AES-GCM:** giá trị không được tái sử dụng cho cùng khóa khi mã hóa; không phải salt scrypt.

~~~mermaid
flowchart TD
    P["Passphrase"] --> KDF["scrypt(salt, N, r, p)"]
    S["Salt & profile công khai"] --> KDF
    KDF --> KEK["KEK dẫn xuất từ passphrase"]
    C["CSPRNG"] --> DEK["DEK ngẫu nhiên"]
    DEK --> ENC["AES-GCM mã hóa file"]
    F["File plaintext"] --> ENC
    ENC --> CT["Ciphertext + nonce + tag"]
    KEK --> WR["AEAD/key wrap theo thiết kế"]
    DEK --> WR
    WR --> ED["Encrypted DEK"]
    CT --> STORE["Lưu metadata + ciphertext"]
    ED --> STORE
    S --> STORE
~~~

**Luồng tạo tệp:**

1. Sinh **DEK ngẫu nhiên** để mã hóa nội dung bằng thuật toán AEAD được hỗ trợ.
2. Sinh **salt ngẫu nhiên** cho lần dẫn xuất từ passphrase.
3. Chạy scrypt với profile đã kiểm soát để tạo **KEK** hoặc keying material cần thiết cho bước bảo vệ DEK.
4. Dùng KEK với một cơ chế **wrap/AEAD đúng chuẩn** để bảo vệ DEK. Nếu dùng AEAD, phải xử lý nonce, tag và AAD đúng; không tự mã hóa bằng XOR hoặc phép nối chuỗi.
5. Lưu ciphertext, encrypted DEK, salt, N/r/p/dkLen, định dạng, phiên bản thuật toán, nonce và AAD metadata theo schema được xác thực.

**Luồng mở tệp:** nhận passphrase, lấy salt/profile từ metadata đã được kiểm tra giới hạn, dẫn xuất lại KEK, thử unwrap DEK và giải mã file. Nếu passphrase sai hoặc metadata/bản mã bị sửa, phép xác thực của cơ chế bảo vệ DEK/dữ liệu phải thất bại; không tiếp tục xuất plaintext chưa xác thực.

### 10.1. Tại sao nên dùng DEK ngẫu nhiên thay vì mã hóa toàn file trực tiếp bằng một khóa từ mật khẩu?

Có hai lý do vận hành quan trọng:

- **Đổi mật khẩu:** nếu DEK vẫn an toàn và cơ chế cho phép, có thể unwrap DEK bằng KEK từ passphrase cũ rồi **rewrap bằng KEK từ passphrase mới**, không nhất thiết mã hóa lại toàn bộ file. Phải cấp **salt mới**, profile phù hợp và xử lý metadata đúng.
- **Phân quyền/rotation:** nhiều file hoặc nhiều đối tượng có thể dùng các DEK độc lập; lộ một DEK có phạm vi ảnh hưởng nhỏ hơn dùng một password-derived key chung cho toàn bộ dữ liệu.

Tuy nhiên, **nếu DEK đã lộ**, chỉ rewrap không làm DEK cũ an toàn trở lại; có thể phải tạo DEK mới và mã hóa lại dữ liệu. Nếu passphrase bị đoán và kẻ tấn công đã sao chép encrypted DEK/ciphertext, đổi passphrase sau đó cũng **không xóa được bản sao đã bị đọc hoặc giải mã**.

### 10.2. Mất passphrase thì sao?

Nếu **chỉ** có passphrase mới suy ra được KEK để giải bọc DEK, việc mất passphrase có thể làm dữ liệu **không thể phục hồi**. Một hệ thống production cần quyết định trước có cho phép:

- Mã hóa thêm bản sao DEK dưới một **recovery key** độc lập.
- Phục hồi qua tổ chức với **KMS/HSM** và quy trình xác thực/ủy quyền nhiều bước.
- Khôi phục từ backup được mã hóa và quản lý khóa riêng.

Mỗi đường phục hồi cũng mở ra một ranh giới tin cậy mới: ai được sử dụng recovery key, audit ra sao và cách thu hồi khi có sự cố.

## 11. scrypt với KMS/HSM và envelope encryption

**KMS (Key Management Service/System)** quản lý vòng đời và quyền sử dụng khóa; **HSM (Hardware Security Module)** bảo vệ vật liệu khóa và hỗ trợ phép toán mật mã trong miền phần cứng chuyên dụng. scrypt là thuật toán tính toán từ passphrase; không phải mọi KMS/HSM đều cung cấp API scrypt trực tiếp.

Một kiến trúc có thể phân vai:

| Thành phần | Trách nhiệm |
|---|---|
| **Ứng dụng** | Thu nhận mật khẩu an toàn, chọn profile được phép, thực hiện scrypt qua thư viện hoặc API phù hợp |
| **Database verifier** | Lưu salt, N/r/p, algorithm/version và kết quả password hashing |
| **KMS/HSM** | Bảo vệ pepper/recovery key/KEK cấp cao hoặc thực hiện wrap/sign/decrypt theo API được hỗ trợ |
| **DEK** | Mã hóa dữ liệu bằng AES-GCM hay AEAD thích hợp |
| **KEK** | Bọc DEK; có thể được dẫn xuất từ passphrase hoặc quản lý trong KMS tùy mô hình |
| **Audit/IAM** | Giới hạn ai được sử dụng khóa, phát hiện đăng nhập bất thường và theo dõi rotation/recovery |

**Ví dụ:** hệ thống doanh nghiệp quản lý tài liệu có thể dùng **KMS KEK** để bảo vệ DEK và **scrypt** để lưu verifier mật khẩu tài khoản. Hai cơ chế này có nhiệm vụ riêng. Không bắt buộc mọi DEK phải được dẫn xuất từ mật khẩu người dùng.

Nếu hệ thống có **passphrase-derived KEK**, phải hiểu rằng kẻ tấn công lấy được encrypted DEK có thể thực hiện **offline password guessing** nếu có đủ metadata và ciphertext để kiểm tra ứng viên. scrypt làm mỗi phép đoán đắt hơn nhưng không thay thế mật khẩu đủ mạnh, cơ chế phục hồi và chính sách quản lý quyền.

### 11.1. Khi nào không nên dùng scrypt?

Không nên dùng scrypt để thay thế những công cụ được thiết kế cho nhiệm vụ khác:

- **Sinh DEK ngẫu nhiên:** dùng CSPRNG/KMS/HSM thay vì lấy password KDF làm máy phát số ngẫu nhiên tổng quát.
- **Dẫn xuất nhiều khóa từ secret có entropy cao:** HKDF và domain separation thường thích hợp hơn.
- **Mã hóa dữ liệu:** dùng AES-GCM hoặc AEAD phù hợp; scrypt chỉ tạo keying material.
- **Ký số:** dùng ECDSA/Ed25519/RSA-PSS với private signing key.
- **Xác thực MAC:** dùng HMAC hoặc API MAC thích hợp.
- **Bảo vệ mật khẩu khỏi credential stuffing trực tuyến:** cần rate limiting/MFA/giám sát; scrypt không xử lý trọn bài toán này.

## 12. Vòng đời của thông tin scrypt và khóa dẫn xuất

Trong quản lý khóa, cần tách **vòng đời password verifier** và **vòng đời password-derived encryption key**:

~~~mermaid
flowchart LR
    A["Chọn mật khẩu/nhận passphrase"] --> B["Sinh salt và profile"]
    B --> C["scrypt dẫn xuất bytes"]
    C --> D{"Mục đích?"}
    D -->|Verifier| E["Lưu verifier + metadata"]
    D -->|Bảo vệ DEK| F["Wrap DEK bằng derived KEK"]
    E --> G["Kiểm tra mật khẩu & giám sát"]
    F --> H["Giải bọc DEK có kiểm soát"]
    G --> I["Nâng cấp profile / thay mật khẩu"]
    H --> I
    I --> J["Thu hồi credential/rewrap hoặc migrate"]
~~~

| Sự kiện | Với password verifier | Với password-derived KEK |
|---|---|---|
| **Tạo** | Sinh salt và tính scrypt; lưu các tham số | Dẫn xuất KEK và wrap DEK có ngữ cảnh |
| **Sử dụng** | Tính lại rồi so sánh kết quả | Unwrap DEK rồi giải mã dữ liệu được phép |
| **Nâng tham số** | Rehash khi có mật khẩu đúng, thay salt/profile mới | Cần rewrap DEK tương ứng bằng KEK mới nếu thay profile dẫn xuất |
| **Đổi mật khẩu** | Tạo verifier mới với salt mới | Cần có DEK/KEK cũ hợp lệ để rewrap, hoặc cơ chế phục hồi |
| **Thu hồi credential** | Ngừng cho login và làm mất hiệu lực session phù hợp | Thu hồi quyền unwrap, thay KEK/DEK theo phạm vi sự cố |
| **Hủy** | Xóa dữ liệu verifier theo chính sách lưu giữ | Xóa dữ liệu/khóa có kiểm soát; tránh mất bản mã hợp lệ |

**Chỉ đổi N/r/p đã lưu mà không tính lại giá trị dẫn xuất là sai.** Cùng một password và salt nhưng profile khác dẫn đến DK khác; việc thay các tham số đòi hỏi quá trình migration có đủ bí mật đầu vào.

### 12.1. Không có "rotation" định kỳ giống nhau cho mọi trường hợp

Với **verifier đăng nhập**, không nên ép người dùng đổi mật khẩu theo một lịch tùy tiện nếu không có lý do rủi ro hoặc chính sách đặc thù; ưu tiên mật khẩu đủ mạnh, phát hiện lộ lọt, MFA và nâng work factor khi phù hợp.

Với **DEK/KEK**, lịch rotation phụ thuộc cryptoperiod, mục đích bảo vệ dữ liệu, giới hạn thuật toán và khả năng chuyển đổi. Với **pepper**, phải có cơ chế đổi khóa và xác định hệ quả đối với verifier cũ.

Nếu passphrase bị lộ, không thể chỉ đổi salt rồi tuyên bố bản mã trước đó đã an toàn: kẻ tấn công có thể đã sở hữu mật khẩu, encrypted DEK và ciphertext. Cần xác định những khóa và dữ liệu bị ảnh hưởng rồi triển khai phương án bảo vệ mới.

## 13. Rủi ro vận hành và cách phòng tránh

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Lưu **SHA256(password)** thay vì password KDF | Tấn công từ điển offline rẻ | Dùng Argon2id/scrypt/PBKDF2 phù hợp, với salt và work factor |
| Dùng **một salt cố định** cho mọi tài khoản | Các tài khoản cùng mật khẩu cho cùng verifier; hỗ trợ tấn công hàng loạt | Sinh salt CSPRNG mới cho mỗi bản ghi |
| Giấu salt và bỏ qua bảo vệ mật khẩu | Coi sai salt là bí mật | Giữ secret ở password/pepper, quản lý đúng thuật toán |
| N/r/p quá thấp | Kẻ tấn công thử ứng viên nhanh | Benchmark và chọn profile phù hợp với hệ thống |
| N/r/p quá cao ở endpoint công khai | Cạn RAM/CPU khi login đồng thời | Rate limit, concurrency cap, bounded profiles, capacity planning |
| Cho phép client gửi N/r/p tùy ý | Resource exhaustion và denial of service | Đọc profile có xác thực từ cấu hình/DB, áp giới hạn nghiêm ngặt |
| Không lưu salt/params/algorithm version | Không thể xác minh hoặc migrate verifier | Lưu metadata đủ, cấu trúc có phiên bản |
| So sánh verifier bằng phép so sánh chuỗi tùy tiện | Có thể rò thời gian hoặc lỗi encoding | So sánh bytes theo API phù hợp, kiểm tra độ dài |
| Lưu password trong log, exception hoặc tracing | Lộ trực tiếp credential | Không log bí mật; che/redact và giới hạn quyền log |
| Ghi mật khẩu vào String lâu dài trong Java | Khó kiểm soát thời gian tồn tại bản sao bộ nhớ | Chọn API/đường xử lý byte hoặc char[] thích hợp và giảm bản sao |
| Dùng derived key từ cùng password cho mọi mục đích không tách biệt | Gia tăng liên kết và nguy cơ lạm dụng chéo | Dùng phân tách mục đích theo giao thức, KDF/HKDF phù hợp |
| Đổi tham số mà không rehash/rewrap | Không xác minh được mật khẩu hoặc mất quyền đọc dữ liệu | Quy trình migration có phiên bản và kiểm thử |
| Đánh đồng salt scrypt với nonce AES-GCM | Tái sử dụng nonce dẫn đến phá AEAD | Quản lý nonce riêng cho từng khóa/ lần mã hóa |
| Coi scrypt tự ngăn tấn công online | Credential stuffing và brute force trực tuyến vẫn có thể xảy ra | MFA, rate limit, chống abuse, audit |
| Hủy passphrase-derived key khi chưa xử lý DEK | Dữ liệu mã hóa có thể không phục hồi | Kiểm kê bản mã, backup và recovery trước khi hủy |

## 14. Tình huống thiết kế: dịch vụ lưu hồ sơ được bảo vệ bằng mật khẩu

Một dịch vụ cung cấp kho hồ sơ cho mỗi khách hàng. Dữ liệu nhạy cảm được mã hóa bằng **AES-GCM**, còn người dùng đăng nhập bằng mật khẩu.

**Thiết kế ban đầu có ba vấn đề:**

1. Hệ thống lấy **SHA256(password)** làm AES key dùng cho mọi hồ sơ của tài khoản.
2. Mọi tài khoản dùng cùng salt bằng chuỗi cố định, gây lặp giá trị verifier khi mật khẩu giống nhau.
3. Khi người dùng đổi mật khẩu, hệ thống chỉ sửa trường hash ở bảng user và không có cách giải mã dữ liệu cũ.

**Thiết kế cải tiến:**

1. Dùng **scrypt hoặc password hashing được chọn** cho verifier đăng nhập, với salt ngẫu nhiên và profile được lưu riêng theo tài khoản.
2. Sinh **DEK độc lập bằng CSPRNG** để mã hóa dữ liệu theo phạm vi phù hợp. Nếu dùng envelope encryption, bảo vệ DEK bằng **KEK trong KMS** hoặc mô hình password-derived KEK được đánh giá kỹ.
3. Nếu password chỉ dùng để đăng nhập, **KMS-backed KEK** có thể tách việc thay password khỏi thao tác đọc/ghi DEK. Ứng dụng chỉ được gọi KMS khi IAM và quyền nghiệp vụ cho phép.
4. Nếu passphrase thực sự dùng để bảo vệ DEK, phải có cơ chế **unwrap bằng bí mật cũ rồi rewrap bằng bí mật mới**; thiết kế recovery và kiểm toán trước khi phát hành.
5. Dữ liệu AES-GCM phải được lưu cùng **nonce duy nhất theo DEK, authentication tag, key version và metadata AAD**.
6. Thao tác đổi mật khẩu, reset credential, revoke session, unwrap DEK và khôi phục dữ liệu phải được phân quyền và ghi audit đúng mức; không đưa password hoặc key material dạng rõ vào log.

~~~text
Đăng nhập:
 password -> scrypt + salt -> so sánh verifier -> xác thực tài khoản
                                             |
                                             v
                                 IAM/authorization/session
                                             |
                                             v
                                   KMS quyền unwrap DEK

Bảo vệ dữ liệu:
 CSPRNG -> DEK -> AES-GCM -> ciphertext + nonce + tag
              |
              +-> KEK trong KMS -> encrypted DEK
~~~

**Điểm cần phân biệt:** Bảo vệ password verifier bằng scrypt là một mục tiêu; kiểm soát ai được KMS giải bọc DEK là mục tiêu khác. Khi thiết kế đúng, việc mật khẩu bị lộ không mặc nhiên tiết lộ DEK chỉ từ dữ liệu DB, nhưng tài khoản bị chiếm vẫn có thể bị lạm dụng quyền truy cập ứng dụng. Phải có xác thực nhiều yếu tố và phân quyền theo ngữ cảnh phù hợp.

## 15. Kiểm thử và kiểm toán

| Tình huống | Kết quả mong đợi |
|---|---|
| Mật khẩu đúng, salt/profile và verifier không đổi | Verify thành công |
| Mật khẩu sai | Verify thất bại |
| Cùng mật khẩu, hai salt mới độc lập | Verifier thường khác nhau |
| Đổi một tham số N/r/p | Derived bytes không thể xem là tương đương với profile cũ |
| Dữ liệu verifier có N bất thường | Bị từ chối trước khi cấp phát lượng RAM nguy hiểm |
| Base64/salt/derived bytes sai định dạng | Lỗi được xử lý an toàn, không rò bí mật |
| Nhiều login đồng thời vượt giới hạn | Bị throttle hoặc xếp hàng; không làm cạn toàn bộ RAM |
| Password chứa Unicode và ký tự đặc biệt | Encoding nhất quán giữa đăng ký và đăng nhập |
| Đổi password và tạo verifier mới | Dùng salt mới, profile hiện hành, hủy credential cũ theo chính sách |
| Nâng tham số sau login thành công | Verifier mới vẫn xác minh đúng, dữ liệu cũ không mất |
| Passphrase-derived KEK thay đổi | DEK được rewrap đúng; dữ liệu giải mã và xác thực AEAD thành công |
| Thu hồi tài khoản hoặc quyền KMS | Yêu cầu login/unwrap không còn được phép bị từ chối |
| Sai AES-GCM nonce/tag/AAD | Không chấp nhận dữ liệu chưa xác thực |
| Password, pepper hoặc derived key xuất hiện trong log | Kiểm thử thất bại; phải loại bỏ nguồn rò rỉ |

Một phép kiểm thử có 1000 salt không trùng **không chứng minh không bao giờ va chạm**; mục tiêu là kiểm tra RNG và code dùng salt đúng. Chọn tham số scrypt vẫn cần đánh giá chi phí trên phần cứng thật và threat model.

**Audit hợp lý** gồm: tài khoản/dịch vụ thực hiện hành động, thời điểm, kết quả đăng nhập/đổi mật khẩu, phiên bản profile, key reference liên quan, quyền gọi KMS và kết quả. Không ghi password, pepper, derived KEK, plaintext nhạy cảm hoặc access token còn hiệu lực.

## 16. Câu hỏi tự kiểm tra

**Câu 1. scrypt có phải thuật toán mã hóa dữ liệu không?**

**Trả lời:** Không. scrypt là password-based KDF. Nó tạo derived bytes; muốn mã hóa phải dùng thuật toán mã hóa như AES-GCM với khóa và nonce phù hợp.

**Câu 2. Mục đích của memory-hardness là gì?**

**Trả lời:** Làm việc thử nhiều mật khẩu ứng viên tốn tài nguyên bộ nhớ cùng với CPU, đặc biệt trong tấn công offline có nhiều phép thử song song.

**Câu 3. Salt scrypt có cần giữ bí mật không?**

**Trả lời:** Không. Salt thường được lưu công khai cùng verifier. Nên sinh ngẫu nhiên và dùng salt mới cho mỗi bản ghi/mật khẩu mới.

**Câu 4. Chỉ dùng SHA-256 một lần cho password có đủ không?**

**Trả lời:** Không. SHA-256 quá nhanh đối với mật khẩu có entropy thấp; cần password hashing/KDF được thiết kế cho việc chống thử đoán.

**Câu 5. Vì sao N, r, p phải được lưu cùng verifier?**

**Trả lời:** Kết quả scrypt phụ thuộc các tham số đó. Khi kiểm tra lại phải dùng đúng profile đã tạo giá trị, trừ khi thực hiện migration có chủ đích.

**Câu 6. Tăng N lên gấp đôi có luôn làm ứng dụng an toàn hơn không?**

**Trả lời:** Không đơn giản. Tăng N nâng chi phí thử đoán nhưng cũng tăng CPU/RAM cho dịch vụ thật và có thể gây DoS nếu không giới hạn concurrency. Cần benchmark và thiết kế toàn hệ thống.

**Câu 7. scrypt và HKDF có thể hoán đổi nhau không?**

**Trả lời:** Không. scrypt tạo chi phí để chống đoán bí mật do người chọn; HKDF dẫn xuất khóa theo ngữ cảnh từ vật liệu khóa phù hợp, không thay thế password hashing.

**Câu 8. Khi dùng scrypt để bảo vệ một DEK, có cần AES-GCM nữa không?**

**Trả lời:** Có nếu cần mã hóa dữ liệu. scrypt chỉ dẫn xuất KEK/keying material; DEK có thể mã hóa dữ liệu bằng AEAD và được bọc bằng cơ chế phù hợp.

**Câu 9. Đổi passphrase có bắt buộc mã hóa lại toàn bộ file không?**

**Trả lời:** Không nhất thiết nếu thiết kế dùng DEK ngẫu nhiên và chỉ rewrap DEK bằng KEK mới. Nếu DEK đã bị lộ, thường phải đánh giá thay DEK và mã hóa lại.

**Câu 10. Pepper có giống salt không?**

**Trả lời:** Không. Salt được lưu cùng verifier, không cần bí mật; pepper là secret bổ sung cần bảo vệ ngoài DB, với vòng đời và rotation riêng.

**Câu 11. Java MessageDigest có cung cấp scrypt trong mọi bản JDK không?**

**Trả lời:** Không. Cần thư viện/provider hỗ trợ, ví dụ Bouncy Castle; MessageDigest.getInstance("SHA-256") không thay thế scrypt.

**Câu 12. Nếu database password verifier đã bị đánh cắp, scrypt có bảo đảm kẻ tấn công không đoán được password?**

**Trả lời:** Không. scrypt làm tăng chi phí mỗi lần đoán; mật khẩu yếu vẫn có thể bị đoán, nên cần mật khẩu đủ mạnh và các kiểm soát khác.

**Câu 13. Nonce của AES-GCM và salt của scrypt khác nhau ở đâu?**

**Trả lời:** Salt tham gia password KDF và nên riêng cho mỗi bản ghi; nonce AES-GCM tham gia mã hóa và bắt buộc không trùng dưới cùng khóa mã hóa. Không thể dùng hai cơ chế tùy tiện thay nhau.

**Câu 14. Khi nâng tham số scrypt, có thể chỉ sửa N trong DB không?**

**Trả lời:** Không. Phải tính lại derived bytes với cấu hình mới từ mật khẩu đúng, đồng thời giữ khả năng xử lý verifier cũ trong giai đoạn chuyển đổi.

## 17. Checklist thiết kế và ghi nhớ

Trước khi dùng scrypt trong hệ thống thực tế, hãy trả lời:

- **Mục đích:** scrypt dùng để lưu password verifier, bảo vệ DEK hay mục đích khác? Có lẫn với mã hóa hoặc chữ ký số không?
- **Input:** có xử lý nhất quán UTF-8/Unicode và xóa giảm thiểu bản sao mật khẩu trong bộ nhớ không?
- **Salt:** có sinh salt mới bằng CSPRNG cho mỗi bản ghi/ lần thay mật khẩu và lưu salt không?
- **Tham số:** N/r/p/dkLen đã được benchmark trên hạ tầng thật và có giới hạn chống DoS chưa?
- **Metadata:** có lưu algorithm/version, salt, profile và định dạng đủ để verify/migrate không?
- **Library:** dùng thư viện/provider được đánh giá, không tự viết ROMix hay kết hợp SHA-256 sai cách chứ?
- **Online defense:** có rate limiting, MFA, bảo vệ phiên, giám sát credential stuffing và audit không?
- **Key lifecycle:** nếu scrypt dẫn xuất KEK, khi đổi password hoặc thu hồi có thể rewrap DEK, bảo vệ backup và phục hồi dữ liệu không?
- **KMS/HSM:** có tách quyền sử dụng key, vị trí lưu pepper/recovery key và chính sách audit không?
- **Incident response:** nếu verifier, password, pepper hoặc DEK bị lộ, hệ thống biết phạm vi và phương án chuyển đổi không?

**Ghi nhớ:** **scrypt là password-based KDF có chi phí bộ nhớ**, giúp tăng giá của mỗi lần đoán mật khẩu ngoại tuyến bằng tham số **N, r, p** và salt phù hợp. Nó **không tự tạo thêm entropy cho một mật khẩu yếu**, không thay cơ chế xác thực online, không mã hóa dữ liệu và không thay chữ ký số. Khi kết hợp đúng với **CSPRNG, KMS/HSM, DEK/KEK, envelope encryption, phân quyền, kiểm toán và vòng đời khóa**, scrypt là một thành phần hữu ích trong hệ thống bảo vệ khóa an toàn.
