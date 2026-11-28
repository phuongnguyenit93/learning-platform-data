# Work factor – Chi phí tính toán trong KDF và bảo vệ mật khẩu

**Work factor** (hệ số công việc hoặc tham số chi phí) mô tả lượng tài nguyên mà một thuật toán cần dùng để **dẫn xuất khóa từ mật khẩu** hoặc **tạo/xác minh giá trị băm mật khẩu**. Tùy thuật toán, chi phí có thể được điều chỉnh bằng **số vòng lặp, thời gian tính toán, lượng bộ nhớ và mức song song**. Work factor càng lớn thường khiến mỗi lần thử đoán mật khẩu tốn kém hơn, nhưng cũng tiêu tốn thêm CPU/RAM của hệ thống phục vụ người dùng hợp lệ.

Đây là khái niệm nền tảng của chương **KDF và mật khẩu** trong module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**. Quản lý work factor đúng giúp giảm rủi ro dò mật khẩu ngoại tuyến và hỗ trợ thiết kế vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy**. Nội dung liên hệ đến mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán, nhất là khi mật khẩu được dùng để bảo vệ vật liệu khóa.

> **Điểm chính:** Không có một work factor tối ưu cho mọi hệ thống. Nó phải đủ tốn kém để làm chậm kẻ tấn công, đồng thời không khiến đăng nhập hợp lệ quá chậm hoặc hệ thống cạn tài nguyên khi có nhiều yêu cầu. Cần đo thực tế trên hạ tầng triển khai và cập nhật định kỳ.

## 1. Tại sao cần work factor?

Mật khẩu do con người chọn thường có entropy thấp hơn khóa mật mã được sinh ngẫu nhiên. Khi dữ liệu đăng nhập bị lộ, kẻ tấn công có thể thực hiện **offline password guessing**: thử nhiều mật khẩu trên bản ghi đã lấy mà không phải gửi yêu cầu đến máy chủ.

So sánh hai cách lưu mật khẩu:

- **Băm nhanh thông thường**, như SHA-256(password), cho phép thử rất nhiều ứng viên trên CPU/GPU chuyên dụng. SHA-256 là hàm băm mật mã tốt cho các mục đích thích hợp, nhưng **không phải phương án lưu mật khẩu an toàn nếu dùng trực tiếp**.
- **Password hashing / password-based KDF có điều chỉnh chi phí**, như Argon2id, scrypt, bcrypt hoặc PBKDF2, khiến mỗi lần kiểm tra một mật khẩu dự đoán tốn nhiều công hơn.

~~~mermaid
flowchart TD
    A["Bản ghi mật khẩu bị lộ"] --> G["Kẻ tấn công chọn mật khẩu đoán"]
    G --> FAST["Băm nhanh: chi phí thấp mỗi lần thử"]
    G --> SLOW["Password KDF: chi phí CPU và/hoặc RAM đã cấu hình"]
    FAST --> F["Có thể thử nhiều ứng viên hơn trong cùng ngân sách"]
    SLOW --> L["Ít lần thử hơn trong cùng ngân sách"]
    L --> NEXT["Vẫn cần mật khẩu mạnh và kiểm soát khác"]
~~~

**Work factor không làm mật khẩu yếu trở thành bí mật mạnh tuyệt đối.** Nếu người dùng chọn mật khẩu nằm trong danh sách cực phổ biến, kẻ tấn công vẫn có thể đoán được. Cần kết hợp với cơ chế kiểm tra mật khẩu yếu/rò rỉ, bảo vệ dữ liệu đăng nhập, MFA khi phù hợp và quản trị phiên.

### 1.1. Phân biệt tấn công ngoại tuyến và trực tuyến

| Mô hình | Kẻ tấn công làm gì? | Work factor có tác dụng gì? | Biện pháp bổ sung |
| --- | --- | --- | --- |
| **Ngoại tuyến** | Có salt, tham số và giá trị hash từ cơ sở dữ liệu; tự thử ứng viên ở nơi khác. | Buộc mỗi lần thử phải tốn CPU/RAM; giúp tăng chi phí dò. | Mật khẩu mạnh, salt riêng, pepper khi thích hợp, bảo vệ kho lưu trữ. |
| **Trực tuyến** | Gửi nhiều lần đăng nhập qua API thật. | Có làm mỗi lượt xác minh tốn công, nhưng **cũng tăng tải của máy chủ**. | Rate limit, kiểm soát lạm dụng, MFA, giám sát, khóa phiên theo chính sách. |
| **Lộ khóa hoặc pepper** | Chiếm được secret dùng bổ sung trong quy trình xác thực. | Work factor vẫn là một lớp bảo vệ nhưng không bù đắp được việc mất secret. | KMS/HSM, tách quyền, xoay khóa và ứng phó sự cố. |

Không đánh đồng **rate limiting** với **work factor**: giới hạn tần suất chỉ khống chế đường gọi dịch vụ mà hệ thống điều khiển được; nó không ngăn kẻ tấn công thử offline trên bản sao dữ liệu đã bị lấy.

## 2. Work factor là những tham số nào?

Các họ thuật toán biểu diễn chi phí theo cách khác nhau.

| Thuật toán | Tham số chính | Tài nguyên tăng lên | Điểm cần nhớ |
| --- | --- | --- | --- |
| **Argon2id** | **m** (memory cost), **t** (time cost), **p** (parallelism) | Bộ nhớ và thời gian tính toán; p điều khiển số lane/luồng theo thư viện. | Thiết kế memory-hard, thường là lựa chọn tốt cho password hashing mới khi thư viện và môi trường hỗ trợ. |
| **scrypt** | **N** (CPU/memory cost), **r** (block size), **p** (parallelization) | CPU, bộ nhớ và mức song song. | N có ràng buộc theo triển khai, thường là lũy thừa của 2; phải hiệu chỉnh cả N, r, p. |
| **bcrypt** | **cost** hay log rounds | Số phép tính tăng xấp xỉ theo **2^cost**. | Cần lưu ý giới hạn đầu vào thường là **72 byte** ở nhiều triển khai bcrypt; đừng cắt mật khẩu không có chủ đích. |
| **PBKDF2-HMAC-SHA-256** | **iteration count** | Chủ yếu tăng công CPU theo số vòng lặp. | Hữu ích khi bị ràng buộc tương thích hoặc chính sách/provider; không có đặc tính memory-hard như Argon2id/scrypt. |

**Không thể đối chiếu các con số khác loại chỉ bằng phép so sánh trực tiếp.** Ví dụ, Argon2id t=3 không có nghĩa tương đương bcrypt cost=12 hay PBKDF2 300.000 iterations. Cần so thời gian, RAM, đặc tính phòng thủ và mức chi phí tấn công trên phần cứng có liên quan.

### 2.1. Time cost và memory cost

**Time cost** tăng công xử lý phải thực hiện. Nếu tăng số vòng của một KDF dựa trên CPU, tốc độ thử đoán thường giảm trong cùng điều kiện phần cứng. Tuy nhiên, hệ thống phục vụ đăng nhập cũng cần thêm CPU cho mỗi lần kiểm tra.

**Memory cost** yêu cầu một lượng RAM đáng kể cho mỗi công việc. Thuộc tính **memory-hard** của Argon2id và scrypt nhằm khiến việc chạy hàng loạt ứng viên song song trên phần cứng chuyên dụng trở nên tốn kém hơn. Khả năng chống tấn công còn phụ thuộc vào thuật toán, tham số và đặc điểm phần cứng của kẻ tấn công.

Ví dụ minh họa: nếu một cấu hình Argon2id dùng khoảng **64 MiB cho mỗi phép xác minh**, thì 20 phép đồng thời có thể yêu cầu khoảng **1.280 MiB (1,25 GiB)** chỉ tính bộ nhớ của các công việc KDF, chưa kể JVM, database và dịch vụ khác. Vì vậy cần kiểm soát **concurrency**, không chỉ latency một request riêng lẻ.

**Parallelism** không đơn giản là “càng cao càng an toàn”. Tham số p của Argon2id mô tả số lane, còn mức sử dụng thread thực tế phụ thuộc implementation. Tăng p có thể giúp tận dụng CPU trong một phép tính, nhưng cũng cạnh tranh tài nguyên khi có hàng trăm yêu cầu đăng nhập.

### 2.2. Hiểu đúng bcrypt cost

Ở nhiều triển khai bcrypt, tăng cost từ 10 lên 11 làm số vòng xử lý tăng xấp xỉ gấp đôi; từ 10 lên 12 làm công việc xấp xỉ gấp bốn, trong các điều kiện tương tự. Tuy nhiên **thời gian tuyệt đối** vẫn phụ thuộc máy, thư viện và tải.

Bcrypt truyền thống có giới hạn xử lý mật khẩu theo **byte**, thường là 72 byte. Một mật khẩu dài nhiều ký tự Unicode có thể vượt ngưỡng byte sớm hơn dự kiến. Ứng dụng cần chọn thư viện và chính sách xử lý đầu vào rõ ràng; không âm thầm cắt bớt nội dung. Không tự thêm bước pre-hash tùy tiện trước bcrypt khi chưa có thiết kế định dạng và migration được kiểm chứng.

### 2.3. Vì sao PBKDF2 vẫn có chỗ đứng?

PBKDF2 dùng một **PRF**, thường HMAC, lặp nhiều lần để tạo đầu ra dẫn xuất từ mật khẩu và salt. Các hệ thống có yêu cầu tiêu chuẩn/khả năng tương thích nhất định có thể sử dụng PBKDF2 với một provider được phê duyệt.

Dù tăng iterations giúp chống dò tốt hơn so với hash nhanh, PBKDF2 **không được thiết kế memory-hard**. Khi xây mới, nên đánh giá Argon2id nếu môi trường hỗ trợ; khi bị ràng buộc về thư viện, phần cứng hoặc quy định, cần hiệu chỉnh PBKDF2 theo yêu cầu thực tế và lên kế hoạch nâng cấp.

## 3. Salt, pepper và work factor khác nhau thế nào?

Ba cơ chế cùng hỗ trợ bảo vệ mật khẩu nhưng giải quyết các rủi ro khác nhau:

| Thành phần | Là gì? | Có giữ bí mật không? | Tác dụng |
| --- | --- | --- | --- |
| **Salt** | Giá trị ngẫu nhiên riêng cho mỗi mật khẩu/bản ghi. | **Không.** Thường lưu cùng password hash. | Khiến các mật khẩu giống nhau có đầu ra khác nhau; chống bảng tính sẵn và chia sẻ công dò giữa nhiều bản ghi. |
| **Work factor** | Tham số thời gian, bộ nhớ, vòng lặp hoặc song song. | **Không.** Cần lưu để xác minh và nâng cấp. | Làm mỗi lần thử đoán tốn thêm tài nguyên. |
| **Pepper** | Secret dùng bổ sung theo một thiết kế bảo vệ mật khẩu được xác định rõ. | **Có.** Phải lưu tách khỏi cơ sở dữ liệu hash. | Thêm bí mật ngoài bản ghi DB; giúp hạn chế tấn công khi chỉ có DB bị lộ. |

**Salt phải đủ ngẫu nhiên và độc lập** cho mỗi bản ghi, sinh bằng CSPRNG. Salt **không cần được mã hóa** và việc nó nằm cùng password hash là thiết kế bình thường. Một salt cố định cho toàn bộ người dùng làm mất đi nhiều lợi ích của cơ chế này.

**Pepper không thay thế salt hoặc work factor.** Pepper cần được bảo vệ bằng kho bí mật hoặc KMS/HSM phù hợp, có phân quyền và cơ chế kiểm toán. Khi pepper bị lộ hoặc cần xoay, quá trình thay đổi phức tạp vì hệ thống thông thường **không thể suy ngược lại mật khẩu gốc từ password hash cũ**. Cần một chiến lược rehash khi người dùng đăng nhập lại hoặc đặt lại mật khẩu cho tài khoản chưa được di chuyển.

Không tự ghép password + pepper bằng phép nối chuỗi tùy tiện rồi giả định giao thức an toàn. Sử dụng thiết kế pepper có phương thức rõ ràng, chẳng hạn một bước **HMAC ở vị trí phù hợp của quy trình** đã được đánh giá, đồng thời quản lý key ID/phiên bản pepper.

## 4. Dữ liệu nào cần lưu để xác minh và nâng cấp?

Một bản ghi password hash cần đủ thông tin để verifier biết **đã dùng thuật toán nào và work factor nào**.

Đối với Argon2id, nhiều thư viện dùng một chuỗi mã hóa kiểu **PHC string**, ví dụ mô tả cấu trúc:

~~~text
$argon2id$v=19$m=65536,t=3,p=1$<base64-salt>$<base64-hash>
~~~

Ý nghĩa:

- **argon2id:** định danh thuật toán.
- **v=19:** version thuật toán Argon2 được thể hiện theo quy ước thông dụng.
- **m=65536:** chi phí bộ nhớ (KiB), tương đương 64 MiB trong ví dụ.
- **t=3:** time cost.
- **p=1:** parallelism.
- **salt/hash:** dữ liệu nhị phân đã mã hóa theo quy ước của thư viện.

**Đây là ví dụ minh họa cách lưu tham số, không phải mức tối thiểu bảo mật bắt buộc cho mọi hệ thống.** Giá trị phù hợp phải được cân chỉnh bằng benchmark và chính sách cập nhật. Không sử dụng chuỗi placeholder này như một bản ghi người dùng thật.

Với bcrypt, định dạng lưu thường chứa version/biến thể và cost; với PBKDF2, hệ thống cần lưu **PRF, iterations, salt và độ dài đầu ra** cùng hash. Không nên chỉ lưu một cột digest ẩn đi thuật toán và tham số, vì việc nâng cấp sau này dễ trở nên thiếu an toàn hoặc không thể thực hiện.

### 4.1. Bảo vệ metadata do record cung cấp

Bản ghi hash có thể đến từ database, nhưng **không được dùng tham số chưa kiểm soát để cấp phát tài nguyên vô hạn**. Verifier cần kiểm tra:

- Thuật toán có nằm trong danh sách được phép hay không.
- Phiên bản và tham số có nằm trong khoảng hỗ trợ, giới hạn an toàn và ngân sách tài nguyên hay không.
- Độ dài salt/hash có hợp lệ theo định dạng và chính sách không.
- Record có đúng account/tenant cần xác minh không; truy cập DB phải được phân quyền.
- Khi đọc một bản ghi cũ, có quy trình nâng cấp hợp lệ, thay vì âm thầm hạ độ khó cho bản ghi mới.

Ví dụ nếu một record giả mạo khai Argon2id với memory cost khổng lồ, verifier không được cấp phát RAM chỉ vì tin vào tham số đó. Giới hạn parser và tài nguyên là một phần phòng vệ DoS.

## 5. Hiệu chỉnh work factor trên môi trường triển khai

Không nên chọn work factor chỉ bằng một con số tìm thấy trong bài viết rồi áp dụng cho mọi workload. Cần **đo và lặp lại** trên hạ tầng phù hợp, gồm CPU, bộ nhớ, container limit, JDK/provider, cách scale và lưu lượng thực.

Quy trình đề xuất:

1. **Xác định threat model và mục tiêu trải nghiệm:** số người dùng, đỉnh đăng nhập, p95/p99 latency cho xác minh, mức RAM/CPU được phân bổ và yêu cầu bảo mật.
2. **Chọn thuật toán được phép:** ưu tiên thuật toán password hashing phù hợp với thư viện và chính sách, chẳng hạn Argon2id; ghi nhận lý do nếu chọn scrypt, bcrypt hay PBKDF2.
3. **Đo một phép xác minh ở nhiều cấu hình:** ghi thời gian, bộ nhớ cực đại, CPU và ảnh hưởng đến GC/runtime.
4. **Đo khi tải đồng thời:** mô phỏng các đợt đăng nhập thực tế cùng các yêu cầu khác. Đặc biệt kiểm tra tổng RAM khi Argon2id/scrypt chạy đồng thời.
5. **Đặt giới hạn tài nguyên:** bounded concurrency, queue/timeout theo chính sách, rate limit và giám sát. Không vô tình tạo khả năng từ chối dịch vụ khi bị spam login.
6. **Chọn cấu hình có biên an toàn:** giữ dư địa cho peak traffic, tình huống failover, phần cứng yếu nhất và các tác vụ khác.
7. **Lưu version cấu hình vào bản ghi:** ghi rõ algorithm và work factor để lần sau có thể verify và nâng cấp.
8. **Đánh giá lại theo chu kỳ:** khi CPU mới, thư viện mới, tốc độ tấn công thay đổi hoặc chỉ số tải thay đổi, cần benchmark và điều chỉnh.

### 5.1. Ví dụ bảng hiệu chỉnh

Các con số dưới đây **hoàn toàn minh họa cách ghi benchmark**, không đại diện cho một loại CPU hoặc gợi ý cấu hình sản xuất:

| Cấu hình thử nghiệm | Thời gian một phép xác minh (minh họa) | Bộ nhớ cho KDF (minh họa) | Nhận xét |
| --- | ---: | ---: | --- |
| Argon2id: m=32 MiB, t=2, p=1 | 45 ms | ~32 MiB | Có thể còn dư ngân sách ở tải nhẹ. |
| Argon2id: m=64 MiB, t=3, p=1 | 120 ms | ~64 MiB | Cần kiểm tra RAM khi nhiều request đồng thời. |
| Argon2id: m=128 MiB, t=3, p=1 | 220 ms | ~128 MiB | Chi phí bộ nhớ cho mỗi request tăng rõ rệt. |
| PBKDF2-HMAC-SHA-256: 300.000 vòng | 100 ms | Thấp hơn nhiều | Không có khả năng memory-hard như Argon2id. |

Ví dụ nếu một phiên đăng nhập mất khoảng 120 ms và cần phục vụ hàng trăm lần xác minh đồng thời, tổng yêu cầu CPU/RAM có thể vượt tài nguyên của một node. Không được lấy phép tính **1 / 0,12 giây ≈ 8 lần/giây** làm năng lực tuyệt đối của cả hệ thống vì thread, core CPU, memory bandwidth, scheduler và các request khác làm thay đổi throughput.

**Đo trực tiếp điều kiện tải là bước bắt buộc trước khi quyết định tham số vận hành.**

## 6. Ví dụ Java 17: work factor của PBKDF2-HMAC-SHA-256

Java 17 cung cấp **SecretKeyFactory** và **PBEKeySpec** cho PBKDF2 qua Java Cryptography Architecture (JCA). Ví dụ này minh họa việc **lưu iterations + salt + derived hash**, kiểm tra bằng cách dẫn xuất lại và so sánh byte.

> **Phạm vi demo:** PBKDF2 được dùng để minh họa work factor bằng API sẵn có trong JDK. Nếu muốn dùng Argon2id trong Java 17, thường cần thư viện/provider tương thích và kiểm tra cấu hình bảo mật riêng. Con số 300.000 iterations dưới đây **chỉ là tham số minh họa**, phải hiệu chỉnh theo hạ tầng và chính sách trước khi dùng thực tế.

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public class PasswordWorkFactorDemo {
    private static final String ALGORITHM = "PBKDF2WithHmacSHA256";
    private static final int ITERATIONS = 300_000;  // Ví dụ cần benchmark
    private static final int KEY_BITS = 256;
    private static final int SALT_BYTES = 16;
    private static final SecureRandom RNG = new SecureRandom();

    record PasswordRecord(String algorithm, int iterations,
                          byte[] salt, byte[] derivedHash) {}

    private static byte[] derive(char[] password, byte[] salt, int iterations)
            throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(password, salt, iterations, KEY_BITS);
        try {
            return SecretKeyFactory.getInstance(ALGORITHM)
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    static PasswordRecord register(char[] password)
            throws GeneralSecurityException {
        byte[] salt = new byte[SALT_BYTES];
        RNG.nextBytes(salt); // Salt mới cho từng bản ghi.
        byte[] hash = derive(password, salt, ITERATIONS);
        return new PasswordRecord(ALGORITHM, ITERATIONS, salt, hash);
    }

    static boolean verify(char[] candidate, PasswordRecord record)
            throws GeneralSecurityException {
        // Giới hạn định dạng và work factor trước khi xử lý.
        if (record == null || !ALGORITHM.equals(record.algorithm())
                || record.iterations() < 100_000
                || record.iterations() > 1_000_000
                || record.salt() == null || record.salt().length != SALT_BYTES
                || record.derivedHash() == null
                || record.derivedHash().length != KEY_BITS / 8) {
            return false;
        }

        byte[] candidateHash = derive(
                candidate, record.salt(), record.iterations());
        try {
            return MessageDigest.isEqual(candidateHash, record.derivedHash());
        } finally {
            Arrays.fill(candidateHash, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        // Mật khẩu giả cho bài học; ứng dụng thật không hard-code.
        char[] password = "DemoOnly-LongPassphrase-123!".toCharArray();
        char[] wrongPassword = "WrongPassphrase!".toCharArray();
        try {
            PasswordRecord record = register(password);

            System.out.println("Work factor: " + record.iterations());
            System.out.println("Correct password: "
                    + verify(password, record));     // true
            System.out.println("Wrong password: "
                    + verify(wrongPassword, record)); // false
        } finally {
            Arrays.fill(password, '\0');
            Arrays.fill(wrongPassword, '\0');
        }
    }
}
~~~

Giải thích:

- **SecureRandom** sinh salt ngẫu nhiên; lưu salt cùng derived hash là bình thường.
- **iterations** quyết định số vòng PBKDF2, là work factor của bản ghi. Cần lưu để xác minh và so sánh với chính sách mới.
- **PBEKeySpec** nhận mật khẩu dạng mảng ký tự; gọi clearPassword() để dọn bản sao nội bộ của đối tượng này.
- **MessageDigest.isEqual** dùng để so sánh byte, phù hợp hơn một vòng lặp tự viết dừng ở byte sai đầu tiên. Cần kiểm tra độ dài và metadata trước khi xác minh như demo.
- **Arrays.fill** chỉ xóa các mảng được chỉ định. Java String và các bản sao khác của mật khẩu hoặc derived key trong JVM có thể còn tồn tại; ở production cần giảm thời gian giữ bí mật và tránh log, dump nhạy cảm.
- **PasswordRecord** chỉ là kiểu dữ liệu demo trong RAM; lưu thật cần định dạng versioned, mã hóa bytes đúng quy ước, giới hạn parser, quản lý tenant/identity và cơ chế nâng cấp.
- **Đoạn mã không triển khai pepper**, chưa có rate limiting, MFA, xử lý tài khoản, session, kiểm soát lạm dụng hoặc cơ chế dịch chuyển thuật toán. Không dùng nguyên xi làm hệ thống xác thực sản xuất.

### 6.1. Khi cần Argon2id trong Java

Java 17 không bảo đảm có Argon2id trực tiếp trong các provider tiêu chuẩn. Nếu chọn thư viện Argon2id, thiết kế API nên tách phần chính sách:

~~~text
policy = {
    algorithm: "Argon2id",
    memoryKiB: 65536,
    timeCost: 3,
    parallelism: 1
}

registration:
    salt = secureRandomBytes()
    encodedHash = argon2id.hash(password, salt, policy)
    store(encodedHash)  // Bao gồm thuật toán, phiên bản và tham số.

verification:
    record = readPasswordRecord(accountId)
    validateSupportedAlgorithmAndParameterBounds(record)
    valid = argon2id.verify(record, candidatePassword)
    if valid and parametersAreOutdated(record):
        newHash = argon2id.hash(candidatePassword, freshSalt(), currentPolicy)
        updatePasswordRecordAtomically(accountId, record.version, newHash)
~~~

Đây là **giả mã độc lập thư viện**, không phải API Java thực tế; các hàm cần được thay bằng thư viện được đánh giá, dùng tham số và định dạng theo tài liệu của thư viện. Việc **rehash** phải xử lý đồng thời các thay đổi mật khẩu, tránh ghi đè một bản ghi mới hơn.

## 7. Nâng cấp work factor và chuyển thuật toán an toàn

Work factor không được đặt một lần rồi giữ mãi. Khi máy chủ mạnh hơn hoặc chính sách thay đổi, có thể cần nâng iterations, memory cost hoặc chuyển từ thuật toán cũ sang thuật toán mới.

### 7.1. Rehash khi đăng nhập thành công

Đây là phương án phổ biến:

1. Lấy bản ghi hash cùng algorithm và work factor đã lưu.
2. Kiểm tra định dạng và giới hạn tham số; xác minh mật khẩu bằng cấu hình **đúng của bản ghi cũ**.
3. Khi mật khẩu hợp lệ, đối chiếu với **current password-hash policy**.
4. Nếu cấu hình cũ, tạo **salt mới** và hash lại **mật khẩu vừa được xác thực** với thuật toán/tham số mới.
5. Cập nhật bản ghi theo cơ chế **compare-and-swap/version check** để tránh ghi đè kết quả đổi mật khẩu đồng thời.
6. Ghi audit về việc nâng cấp policy (không ghi mật khẩu, salt bí mật giả định hoặc secret trong log); tiếp tục đăng nhập theo quy trình bình thường.

Không thể chỉ tăng trường iterations trong database từ 100.000 lên 300.000 mà giữ nguyên giá trị hash: đầu ra sẽ **không còn khớp**. Cần có mật khẩu gốc lúc người dùng đăng nhập hoặc một quy trình thay mật khẩu riêng, rồi dẫn xuất lại từ đầu.

### 7.2. Người dùng không đăng nhập trong thời gian dài

Nếu một tài khoản cũ không có lần đăng nhập thành công mới, hệ thống không có mật khẩu rõ để rehash. Có thể áp dụng chính sách buộc đặt lại mật khẩu khi tài khoản hoạt động trở lại, hoặc chấp nhận legacy verifier trong một khoảng chuyển tiếp có giới hạn và có giám sát.

**Không được giữ thuật toán yếu vô thời hạn chỉ để tránh phiền người dùng.** Tuy nhiên, cũng không tự ý thay bản ghi bằng giá trị không thể xác minh khiến mọi người bị khóa tài khoản mà không có quy trình khôi phục.

### 7.3. Thay pepper và thuật toán có hệ quả riêng

- **Tăng work factor:** rehash trên mật khẩu hợp lệ với tham số mới.
- **Thay algorithm:** cần verifier đa phiên bản trong giai đoạn chuyển đổi, sau đó loại bỏ hỗ trợ cũ có kế hoạch.
- **Xoay pepper:** cần quy trình riêng, vì pepper bí mật không thể thay bằng cách sửa metadata thông thường. Nếu giữ nhiều phiên bản pepper, kiểm soát thời gian chấp nhận, key ID và quyền dùng secret cũ.
- **Khi nghi lộ database/pepper:** cần đánh giá phạm vi, thu hồi phiên, yêu cầu đổi mật khẩu khi thích hợp, giảm quyền truy cập và theo dõi hoạt động bất thường; rehash không tự sửa được việc mật khẩu đã bị đoán hoặc dùng lại ở nơi khác.

## 8. Work factor trong hệ thống có nhiều node và tenant

Một ứng dụng có thể có nhiều nhóm truy cập: người dùng đăng nhập, tài khoản quản trị, dịch vụ nội bộ, khách hàng API hoặc nhiều tenant. Không nên áp dụng giải pháp mật khẩu cho mọi loại danh tính:

- **Người dùng:** password hashing có salt và work factor, rate limiting/MFA theo rủi ro.
- **Dịch vụ nội bộ:** ưu tiên workload identity, khóa bất đối xứng, chứng chỉ, token ngắn hạn hoặc secret ngẫu nhiên thích hợp; không cần KDF mật khẩu chậm nếu không có mật khẩu con người.
- **API key ngẫu nhiên có entropy cao:** có thể cần cách lưu và xác minh riêng, phù hợp để tra cứu và thu hồi; không tự xem giống mật khẩu do người dùng chọn.
- **Dữ liệu mã hóa bằng AES:** dùng khóa đối xứng sinh ngẫu nhiên và được quản lý với DEK/KEK, không tái sử dụng password hash làm khóa AES.

Nếu mỗi lần login Argon2id dùng khoảng 64 MiB, **100 lượt xác minh đồng thời** có thể tạo nhu cầu RAM lớn ngay trên một node. Để tránh DoS, có thể đặt giới hạn số công việc KDF chạy song song, queue có thời hạn, chính sách rate limit và khả năng scale dựa trên đo tải. Không mở rộng queue vô hạn khiến request tồn đọng quá lâu.

Với môi trường đa tenant, lưu policy được phê duyệt theo phiên bản thay vì để tenant tự chọn work factor tùy ý ở đầu vào. Không cho request không tin cậy quyết định thẳng memory cost, iterations hoặc số luồng mà máy chủ phải cấp phát.

## 9. KDF mật khẩu khác HKDF và dẫn xuất khóa phiên thế nào?

**Password-based KDF** cố ý tốn tài nguyên để bù cho độ khó đoán thấp của mật khẩu. **HKDF** được thiết kế để trích xuất và mở rộng vật liệu khóa từ một bí mật đầu vào có tính chất thích hợp, chẳng hạn bí mật ECDH, với **salt và info** để ràng buộc ngữ cảnh. HKDF **không được thiết kế để làm chậm việc dò mật khẩu yếu** như Argon2id/scrypt/PBKDF2.

| Nguồn đầu vào | Mục đích | Cơ chế phù hợp theo thiết kế |
| --- | --- | --- |
| **Mật khẩu người dùng** | Lưu thông tin để xác minh đăng nhập. | Password hashing chuyên dụng với salt và work factor. |
| **Mật khẩu / passphrase để mở kho dữ liệu** | Dẫn xuất khóa bảo vệ dữ liệu có giới hạn rủi ro theo mật khẩu. | Password-based KDF phù hợp với salt, work factor và giao thức mã hóa xác thực. |
| **Bí mật ECDH / X25519 trong giao thức bắt tay** | Tạo khóa phiên dùng cho mã hóa đối xứng. | KDF chuẩn trong giao thức, thường là HKDF hoặc cơ chế tương đương. |
| **Khóa gốc ngẫu nhiên của hệ thống** | Dẫn xuất các khóa theo mục đích. | KDF chuẩn với domain separation và kiểm soát quyền. |

Không lưu **password verifier** rồi lấy bytes hash đó làm DEK cho dữ liệu ứng dụng. Nếu một mật khẩu phải phục vụ cả xác thực và mở dữ liệu, cần có thiết kế phân tách mục đích, cách dẫn xuất độc lập và kế hoạch khôi phục/đổi mật khẩu rõ ràng. Khi mật khẩu bị quên, dữ liệu được mã hóa bằng khóa chỉ có thể suy ra từ mật khẩu có thể không khôi phục được nếu không tồn tại đường khôi phục hợp lệ khác.

### 9.1. Liên hệ với envelope encryption

Trong mô hình **envelope encryption**, một **DEK** thường được sinh ngẫu nhiên để mã hóa dữ liệu bằng AES-GCM, sau đó được bọc bởi **KEK** do KMS/HSM quản lý. Work factor của password KDF **không thay thế** cơ chế wrap DEK.

Ở mô hình kho dữ liệu có passphrase, password-based KDF có thể tạo ra một khóa để bảo vệ DEK theo giao thức được thiết kế riêng. Cần xem xét rủi ro dò mật khẩu ngoại tuyến, cách lưu salt/work factor, khả năng nâng tham số và việc **mã hóa lại hoặc rewrap** sau khi đổi passphrase. Không đồng nhất work factor của lớp password với vòng đời và quyền truy cập của KEK trong KMS.

## 10. Vòng đời, phân quyền và kiểm toán

Trong module quản lý khóa mật mã, work factor không được tách rời vòng đời secret:

| Giai đoạn | Hoạt động với password KDF / khóa liên quan | Rủi ro |
| --- | --- | --- |
| **Tạo** | Chọn thuật toán, work factor đã benchmark; sinh salt bằng CSPRNG; nếu có pepper, tạo secret qua nguồn tin cậy. | Tham số quá thấp, salt lặp hoặc secret yếu. |
| **Cấp phát** | Gắn algorithm ID, policy version, tham số, account/tenant và quyền truy cập bản ghi. | Dùng nhầm policy hoặc truy cập hash ngoài quyền. |
| **Lưu trữ** | Lưu hash, salt và work factor với ACL; bảo vệ pepper riêng trong KMS/HSM/kho bí mật nếu có. | Lộ DB hoặc lộ cả pepper khiến tấn công dễ hơn. |
| **Sử dụng** | Verifier kiểm tra tham số trước khi chạy, giới hạn đồng thời, so khớp an toàn và xác minh tài khoản. | CPU/RAM bị DoS, time-based leak, nhận sai record. |
| **Xoay/nâng cấp** | Tăng work factor hoặc đổi thuật toán qua rehash khi đăng nhập, theo dõi phiên bản. | Legacy hash tồn tại quá lâu hoặc migration làm khóa tài khoản. |
| **Thu hồi** | Thu hồi phiên/token, đổi mật khẩu hoặc vô hiệu hóa phương thức xác thực khi phát hiện sự cố. | Kẻ tấn công tiếp tục truy cập bằng thông tin đã lộ. |
| **Hủy** | Xóa bản ghi/secret/bản sao theo retention, xử lý pepper cũ và khóa được dẫn xuất nếu có. | Dữ liệu nhạy cảm tồn dư trong backup hoặc mất khả năng mở dữ liệu mã hóa phụ thuộc. |

**KMS/HSM** giúp bảo vệ pepper hoặc khóa dùng trong một cơ chế xác thực được nhà cung cấp hỗ trợ, nhưng quyền gọi API HMAC hoặc giải bọc secret cũng phải được phân quyền chặt. Không mặc định mọi KMS hỗ trợ trực tiếp Argon2id hay lưu password hash như một dịch vụ riêng.

Một hồ sơ kiểm toán phù hợp nên ghi **policy version, loại thuật toán, việc nâng cấp hash, thay đổi cấu hình, số lần xác minh và lỗi tài nguyên**, với danh tính actor và kết quả khi thích hợp. **Không ghi plaintext password, giá trị pepper, khóa bí mật hoặc toàn bộ credential record vào log**. Các phép đo latency/CPU/RAM nên được tổng hợp mà không tạo ra kênh lộ dữ liệu người dùng.

## 11. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Lưu SHA-256(password) không qua password KDF | Tấn công offline có thể thử rất nhanh. | Dùng Argon2id/scrypt/bcrypt/PBKDF2 phù hợp và hiệu chỉnh work factor. |
| Một salt cố định dùng cho mọi tài khoản | Mật khẩu giống nhau dễ liên hệ; giảm hiệu quả chống tính sẵn. | Sinh salt ngẫu nhiên riêng cho mỗi bản ghi. |
| Giữ pepper ngay cạnh password hash trong DB | Mất lợi ích tách bí mật khi DB bị lộ. | Pepper ở kho độc lập, ACL/KMS/HSM và chính sách xoay. |
| Work factor thấp vì muốn login nhanh | Chi phí dò offline thấp hơn cần thiết. | Benchmark để tăng công an toàn trong ngân sách tài nguyên. |
| Work factor quá cao không xét peak traffic | Đăng nhập chậm, cạn RAM/CPU, dễ DoS. | Giới hạn concurrency, đo p95/p99 và có biên tài nguyên. |
| Tự cho client chọn Argon2 m/t/p | Có thể bị ép cấp phát quá nhiều RAM/CPU. | Validate algorithm/params và áp policy server-side. |
| So sánh trực tiếp bcrypt cost với PBKDF2 iterations | Chọn tham số sai vì hai thang đo khác nhau. | So benchmark và đặc tính thuật toán. |
| Không biết giới hạn đầu vào bcrypt | Mật khẩu dài có thể bị cắt/diễn giải không như người dùng kỳ vọng. | Kiểm tra hành vi library và định nghĩa chính sách byte/encoding. |
| Chỉ thay trường iterations trong DB | Hash cũ không khớp lần xác minh tiếp theo. | Rehash mật khẩu hợp lệ và lưu salt/hash mới. |
| Rehash thất bại nhưng ghi đè bản ghi cũ | Người dùng mất khả năng đăng nhập. | Cập nhật nguyên tử, version check và đường rollback kỹ thuật phù hợp. |
| Dùng HKDF thuần để băm mật khẩu yếu | Không có work factor chống thử offline như password KDF. | Dùng thuật toán chuyên cho password hashing. |
| Dùng password hash làm khóa AES lâu dài | Trộn mục đích, khó đổi mật khẩu/khôi phục dữ liệu. | Tách verifier khỏi DEK/KEK và thiết kế dẫn xuất khóa riêng. |
| Chỉ nâng tham số mà bỏ qua lộ mật khẩu | Mật khẩu đã biết vẫn có thể bị dùng ở nơi khác. | Ứng phó sự cố, đổi mật khẩu, thu hồi phiên và bảo vệ tài khoản. |

## 12. Câu hỏi tự kiểm tra

1. Work factor khác **salt** và **pepper** như thế nào?
2. Vì sao SHA-256 trực tiếp không phù hợp để lưu mật khẩu người dùng?
3. Các tham số **m, t, p** của Argon2id đại diện cho những tài nguyên gì?
4. Bcrypt cost tăng từ 11 lên 12 có xu hướng làm chi phí thay đổi thế nào?
5. Vì sao một cấu hình KDF chạy nhanh với một người đăng nhập chưa chắc đủ an toàn ở thời điểm peak traffic?
6. PBKDF2 có tính memory-hard như Argon2id hoặc scrypt không?
7. Muốn tăng iterations cho bản ghi PBKDF2 cũ thì có thể chỉ sửa metadata không?
8. Vì sao cần kiểm tra giới hạn work factor lấy từ database trước khi thực hiện phép xác minh?
9. Khi đổi pepper, vì sao nhiều hệ thống phải chờ người dùng đăng nhập lại hoặc yêu cầu đặt lại mật khẩu?
10. Work factor của mật khẩu có thay thế rate limiting hoặc MFA được không?
11. Vì sao không nên dùng một password hash để vừa xác minh đăng nhập vừa làm khóa mã hóa dữ liệu?
12. Nếu một hệ thống dùng Argon2id memory cost cao, làm thế nào ngăn 100 đăng nhập đồng thời làm cạn RAM?

**Ghi nhớ:** Work factor là tham số biến **mỗi lần đoán mật khẩu** thành một công việc tốn thời gian và/hoặc bộ nhớ, giảm tốc độ dò offline trong một ngân sách tấn công nhất định. Để bảo vệ thực tế cần **thuật toán password KDF phù hợp, salt riêng, work factor được đo trên hạ tầng, kiểm soát tài nguyên khi đăng nhập, phiên bản hóa bản ghi, quy trình rehash và giám sát**. Khi có pepper hoặc khóa dẫn xuất phục vụ mã hóa, phải kết hợp **KMS/HSM, phân quyền, kiểm toán và quản lý vòng đời khóa** để tránh rò rỉ hay mất dữ liệu.
