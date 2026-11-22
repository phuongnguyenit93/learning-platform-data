# BCrypt, PBKDF2, SCrypt và Argon2: tiêu chí lựa chọn trong Spring Security

Khi lưu mật khẩu cho tài khoản ứng dụng Spring Security Servlet, câu hỏi không chỉ là “nên dùng thuật toán mạnh nhất nào?”. Cần lựa chọn một **password hashing/KDF dành cho mật khẩu**, cân bằng khả năng chống tấn công đoán mật khẩu ngoại tuyến, mức tiêu thụ CPU/RAM của máy chủ, yêu cầu tương thích hệ thống, chi phí vận hành và lộ trình nâng cấp hash đã tồn tại. Bốn cái tên thường gặp là **BCrypt, PBKDF2, SCrypt và Argon2**. Không có một giá trị cost/iterations/memory cố định tối ưu cho mọi sản phẩm.

Bài này tập trung vào tiêu chí lựa chọn và cách dùng các thuật toán qua `PasswordEncoder` trong **Spring Security 6.x trên Servlet stack**, với ví dụ Java 17+ và Spring Boot 3.x. Các tham số và phiên bản API trong ví dụ mang tính minh họa: trước khi triển khai thật phải benchmark trên phần cứng hiện tại, tính đến lưu lượng đăng nhập và kiểm thử toàn bộ migration.

## 1. Hiểu đúng mục tiêu: lưu mật khẩu để kiểm tra, không phải để khôi phục

Tại thời điểm đăng ký hoặc đổi mật khẩu, ứng dụng nhận một **raw password** qua kênh được bảo vệ (HTTPS), dùng thuật toán băm mật khẩu có salt/cost để sinh một **encoded password**, rồi lưu encoded value vào database. Khi đăng nhập, ứng dụng không giải mã giá trị này; nó kiểm tra password được nhập với giá trị đã lưu.

~~~text
Đăng ký/đổi mật khẩu:
raw password ---- password KDF + random salt + work factors ---> encoded hash
                                                               |
                                                               v
                                                             database

Đăng nhập:
raw password + encoded hash ---- PasswordEncoder.matches(...) ---> true/false
~~~

Spring Security biểu diễn thao tác đó qua `org.springframework.security.crypto.password.PasswordEncoder`:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword, String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

Đây là **hình dạng contract để học**, không phải khai báo interface cần sao chép vào dự án. `encode` tạo giá trị lưu; `matches` trả kết quả kiểm tra; `upgradeEncoding` giúp quyết định hash lưu có cần được nâng cấp, nhưng **không tự cập nhật database**.

Các nguyên tắc bắt buộc:

- **Không lưu plaintext**, không dùng reversible encryption để “có thể lấy lại mật khẩu” khi người dùng quên. Luồng quên mật khẩu nên cấp token đặt lại mật khẩu, không gửi lại mật khẩu cũ.
- **Không dùng hash nhanh** như MD5, SHA-1 hoặc SHA-256 đơn thuần (kể cả có salt) để lưu mật khẩu. Những hàm này tối ưu tốc độ, nên kẻ tấn công có thể thử mật khẩu rất nhanh trên GPU/ASIC.
- **Salt khác nhau cho mỗi mật khẩu** làm cùng một password thường sinh ra các encoded hash khác nhau; salt không phải bí mật và thường được đóng gói trong hash lưu. Không cần một cột salt riêng nếu định dạng encoder đã tự mang salt.
- **Work factor** (iterations/cost/memory/parallelism) khiến mỗi lần thử mật khẩu có chi phí đủ lớn để làm khó việc thử hàng loạt. Vì vậy nó cũng làm tăng tài nguyên khi user đăng nhập hợp lệ.
- **Pepper** là bí mật ứng dụng dùng ngoài database (tùy hệ thống), không thay thế salt hoặc thuật toán tốt. Nếu dùng pepper, cần thiết kế HSM/secret manager, vòng đời và rotation; không tự thêm một chuỗi hardcoded vào password rồi gọi là đã an toàn.
- **Không so sánh** `encoder.encode(password).equals(storedHash)`: nhiều thuật toán tạo salt mới ở mỗi lần encode nên hash khác nhau dù raw password giống nhau. Luôn dùng `matches`.

Mô hình tấn công quan trọng nhất ở đây là **đối thủ đã lấy được database chứa password hashes** và thử các password candidate ngoại tuyến. Khi đó rate limiting ở endpoint login **không** làm giảm trực tiếp tốc độ thử offline của họ; chính chi phí của thuật toán, entropy mật khẩu và các yếu tố bảo mật khác mới quyết định sức chống chịu. Ngược lại, trong tấn công online, rate limiting/MFA/cảnh báo đăng nhập vẫn cực kỳ quan trọng.

## 2. So sánh nhanh bốn thuật toán

| Tiêu chí | BCrypt | PBKDF2 | SCrypt | Argon2 (ưu tiên Argon2id trong sử dụng phổ biến) |
| --- | --- | --- | --- | --- |
| Ý tưởng | Hash mật khẩu lặp lại, có cost theo cấp số mũ | Dẫn xuất khóa bằng PRF/HMAC lặp nhiều lần | Password KDF đòi cả CPU và bộ nhớ | Password KDF được thiết kế với chi phí RAM/thời gian/lanes có cấu hình |
| Chủ yếu ràng buộc | CPU/time | CPU/time | CPU + RAM | CPU + RAM, có tham số song song |
| Tham số thường gặp | Cost/work factor | Iterations, PRF, salt/key length | N, r, p (cost, block size, parallelization) | m, t, p (memory, iterations, parallelism) |
| Salt | Thường nhúng vào encoded hash | Cần salt ngẫu nhiên; encoder thường lưu kèm | Salt ngẫu nhiên, encoder lưu kèm | Salt ngẫu nhiên, encoder lưu kèm |
| Điểm mạnh | Phổ biến, lâu đời, dễ tương thích | Có nhiều triển khai, dễ đáp ứng ràng buộc hệ sinh thái/chuẩn | Memory-hard, gây bất lợi cho việc thử song song quy mô lớn | Memory-hard, điều chỉnh chi phí rõ và phù hợp nhiều threat model hiện đại |
| Điểm cần lưu ý | Đầu vào BCrypt có giới hạn hiệu dụng khoảng 72 byte; không memory-hard theo nghĩa của SCrypt/Argon2 | Không memory-hard; cần iterations đủ lớn và hiểu lựa chọn PRF | Tải RAM và CPU cần tính đến concurrency; phụ thuộc thư viện triển khai | Cần memory budget, hỗ trợ thư viện và benchmark; chọn **biến thể Argon2id** khi phù hợp |
| Trong Spring Security | `BCryptPasswordEncoder` | `Pbkdf2PasswordEncoder` | `SCryptPasswordEncoder` | `Argon2PasswordEncoder` |
| Một tình huống hợp lý | Hệ thống Java cần password hash thông dụng, vận hành đơn giản | Môi trường cần tương thích PBKDF2 hoặc ràng buộc tuân thủ riêng | Muốn memory-hard, stack hỗ trợ tốt SCrypt | Hệ thống mới ưu tiên memory-hard và có đủ ngân sách RAM |
| Có “mạnh nhất tuyệt đối”? | Không | Không | Không | Không |

**Điểm mấu chốt:** “Argon2 mạnh hơn” không phải một tuyên bố đủ để chọn production, vì cấu hình Argon2 quá nhẹ vẫn có thể kém một cấu hình khác được benchmark đúng. Tương tự, một BCrypt có cost quá thấp hoặc PBKDF2 quá ít iterations đều có thể bảo vệ kém. Hãy so sánh **tham số, phần cứng, threat model và triển khai thực**, không chỉ tên thuật toán.

Nếu tổ chức có yêu cầu tuân thủ như FIPS, cần xác minh **chính xác thư viện/provider, chế độ hoạt động và phạm vi chứng nhận**. PBKDF2 là lựa chọn thường được xem xét trong môi trường có ràng buộc đó, nhưng tên thuật toán PBKDF2 tự nó không chứng minh toàn bộ triển khai đạt FIPS.

## 3. BCrypt: lựa chọn ổn định khi cần đơn giản và tương thích

BCrypt áp dụng cơ chế hash dành cho password với salt và cost. Trong Spring Security:

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder(12);

String stored = encoder.encode("example-password");
boolean correct = encoder.matches("example-password", stored);
boolean wrong = encoder.matches("wrong-password", stored);
~~~

Đây là **mảnh code minh họa** cần import `PasswordEncoder` và `BCryptPasswordEncoder`; nó không phải file Java độc lập. `12` là cost ví dụ, **không** phải khuyến nghị cố định. Kết quả `correct` là `true` và `wrong` là `false` nếu bộ mã hóa hoạt động bình thường; chuỗi `stored` thay đổi theo salt, không đưa hash cố định vào assertion.

### 3.1. Cost trong BCrypt

Work factor của BCrypt thường biểu diễn bằng một số nguyên; chi phí xử lý tăng rất nhanh khi tăng cost, gần theo cấp số mũ. Chuyển từ cost 10 sang 12 không có nghĩa “thêm 20% công sức”; về trực giác, nó làm số vòng làm việc tăng theo hệ số nhiều lần, dù latency thực phải đo.

Điều cần đo không chỉ là thời gian `encode` trên laptop:

- Thời gian `matches` ở các percentile quan trọng (p50, p95, p99) trên **máy production**.
- Số request xác thực đồng thời, burst traffic và thời gian hàng đợi.
- Tải CPU giới hạn trong container, noisy neighbors và thời gian cold start.
- Khả năng tăng cost trong 1–2 năm tới và cách nâng cấp hash cũ.

Tham số BCrypt lưu trong định dạng hash, giúp encoder xác định cost khi kiểm tra; không cần một bảng riêng ghi lại cost cho mỗi user nếu đã dùng định dạng chuẩn của thư viện.

### 3.2. Giới hạn đầu vào khoảng 72 byte

BCrypt có giới hạn đầu vào hiệu dụng khoảng **72 byte**, không phải 72 ký tự Unicode. Với UTF-8, một ký tự có thể chiếm nhiều byte. Nhiều triển khai BCrypt chỉ xét phần đầu của đầu vào khi vượt giới hạn; hai chuỗi có tiền tố byte giống nhau có thể dẫn tới những vấn đề tương thích và bảo mật nếu sản phẩm xử lý không nhất quán.

Khi chọn BCrypt:

1. Quy định cách chuyển đổi password thành byte và giới hạn hợp lý, nhất quán giữa đăng ký, login, đổi password, migration.
2. Kiểm thử password dài và các chuỗi Unicode có nhiều byte.
3. Không âm thầm cắt chuỗi password theo ký tự mà không giải thích policy cho người dùng.
4. Không tự đưa một thuật toán pre-hash vào trước BCrypt nếu chưa thiết kế giao thức và versioning nghiêm túc: thay đổi đó sẽ thay đổi định nghĩa password và có thể gây incompatibility.

### 3.3. Khi nào phù hợp?

BCrypt thường hợp lý nếu đội ngũ muốn một giải pháp phổ biến, có hỗ trợ lâu dài và vận hành chủ yếu theo CPU. Với hệ thống mới có thể dành RAM đáng kể cho mỗi attempt, nên đánh giá thêm Argon2id. Với hệ thống cũ đã lưu BCrypt, không cần buộc toàn bộ tài khoản đổi password chỉ để chuyển ngay thuật toán; lộ trình migrate khi đăng nhập thành công thường phù hợp hơn.

## 4. PBKDF2: ưu tiên tính tương thích và yêu cầu hệ sinh thái

PBKDF2 lặp một pseudorandom function (thường HMAC với hash được chọn) nhiều lần trên password và salt để tạo khóa/hash dẫn xuất. Nó chủ yếu tiêu thụ CPU và được hỗ trợ rộng rãi bởi nhiều thư viện mật mã.

Spring Security có `Pbkdf2PasswordEncoder`. Trên Spring Security 6.x, một factory theo version được cung cấp để lựa chọn bộ tham số tương thích một profile cụ thể:

~~~java
PasswordEncoder encoder =
    Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8();

String stored = encoder.encode("example-password");
boolean correct = encoder.matches("example-password", stored);
~~~

Đoạn trên là **mảnh code**, không phải chương trình chạy một mình; cần import `Pbkdf2PasswordEncoder` và `PasswordEncoder`. Factory theo version là cách tránh việc code tùy ý sao chép nhiều con số iterations/salt length. Tuy nhiên, **đừng coi mặc định của một release là thông số bắt buộc cho mọi hệ thống hay luôn cập nhật theo tiêu chuẩn mới nhất**: khi áp dụng production, vẫn cần đánh giá chính sách và benchmark.

### 4.1. Các tham số quan trọng

- **PRF**: ví dụ HMAC-SHA256. Cần ghi rõ khi trao đổi hash giữa các hệ thống.
- **Iterations**: càng nhiều thì CPU cost thường càng tăng; một cấu hình nhỏ có thể trở nên không phù hợp theo thời gian.
- **Salt**: ngẫu nhiên, riêng cho mỗi password, độ dài đủ theo chính sách.
- **Derived key length**: kích thước đầu ra; không phải cứ tăng gấp đôi chiều dài là tăng gấp đôi khả năng chống đoán password.
- **Secret/pepper tùy chọn**: nếu dùng tính năng trộn secret của implementation, phải quản lý và version secret riêng.

### 4.2. Lợi thế và giới hạn

PBKDF2 có lợi thế khi dự án cần tương tác với một hệ thống đã chuẩn hóa PBKDF2 hoặc chịu các ràng buộc mật mã/compliance. Nó có thể dễ chạy trong các runtime không có thư viện memory-hard phù hợp.

Giới hạn quan trọng là PBKDF2 **không memory-hard** như SCrypt/Argon2id. Đối thủ có phần cứng song song mạnh có thể thử nhiều candidate một cách hiệu quả hơn so với một KDF đòi nhiều RAM, tùy tham số và môi trường. Vì vậy, “số iterations rất cao” không phải giải pháp miễn phí: máy chủ cũng phải thực hiện công việc đó cho từng lần xác thực hợp lệ.

### 4.3. Những lỗi thường gặp

- Dùng PBKDF2 nhưng iterations bị đóng băng nhiều năm.
- Không lưu hoặc không nhận diện cấu hình PRF, iterations, salt length khi thay phiên bản encoder.
- Đổi implementation/secret/PRF mà không giữ cơ chế xác minh hash cũ.
- Gọi tên PBKDF2 như bằng chứng FIPS mà chưa kiểm tra provider/môi trường chứng nhận.
- Dùng PBKDF2 một lần nhanh với mật khẩu yếu rồi kỳ vọng giải quyết được rủi ro credential stuffing; online attacks vẫn cần nhiều lớp phòng vệ.

## 5. SCrypt: tăng chi phí RAM để chống thử song song

SCrypt là password KDF memory-hard. Ngoài CPU, người thử mật khẩu còn phải dùng bộ nhớ cho các bước tính toán; điều này làm tấn công song song quy mô lớn có chi phí RAM lớn hơn.

Trong Spring Security, class là `SCryptPasswordEncoder` (chú ý chữ hoa `SCrypt`):

~~~java
PasswordEncoder encoder =
    SCryptPasswordEncoder.defaultsForSpringSecurity_v5_8();

String hash = encoder.encode("example-password");
boolean valid = encoder.matches("example-password", hash);
~~~

Cần import `org.springframework.security.crypto.scrypt.SCryptPasswordEncoder` và `PasswordEncoder`. Tùy phiên bản và cách đóng gói, triển khai SCrypt của Spring Security cần dependency crypto bổ sung như Bouncy Castle; kiểm tra classpath runtime, không chỉ compile.

### 5.1. N, r, p tác động thế nào?

Tham số SCrypt thường được mô tả bằng:

- **N** (cost/work factor): số lượng công việc, thường bị ràng buộc ở dạng lũy thừa của 2.
- **r** (block size): ảnh hưởng đến mức RAM và tính toán.
- **p** (parallelization): mức khối công việc độc lập có thể làm tăng effort.

Một công thức ước lượng nổi tiếng cho phần bộ nhớ lõi là khoảng **128 × N × r byte**, nhưng tổng RAM thực tế của thư viện/JVM, các buffer, thread stack, GC và concurrent requests còn nhiều yếu tố khác. Không dùng công thức làm thay thế cho đo **RSS/heap/native memory** dưới tải thực.

### 5.2. Khi chọn SCrypt

SCrypt phù hợp khi hệ thống muốn memory-hard, triển khai đã được hỗ trợ và đáp ứng ngân sách RAM. Không tăng `N, r, p` theo cảm tính. Nếu máy chạy 1.000 requests login đồng thời và mỗi attempt đòi lượng RAM đáng kể, application có thể bị memory pressure hoặc OutOfMemoryError ngay cả khi từng request riêng lẻ chạy được.

Hãy có concurrency limits và bảo vệ endpoint authentication khỏi resource exhaustion. Memory-hard khiến việc đo cost ở môi trường container và dưới load quan trọng hơn, không kém.

## 6. Argon2: ưu tiên Argon2id khi phù hợp threat model

Argon2 là họ password hashing/KDF với các biến thể. Trong đa số thiết kế password storage hiện đại, **Argon2id** là biến thể thường được ưu tiên vì kết hợp đặc tính chống một số kiểu tấn công side-channel và chống tính toán chuyên dụng. Không đồng nhất mọi cấu hình “Argon2” mà không biết biến thể và tham số.

Trong Spring Security 6.x:

~~~java
PasswordEncoder encoder =
    Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();

String hash = encoder.encode("example-password");
boolean valid = encoder.matches("example-password", hash);
~~~

Cần import `org.springframework.security.crypto.argon2.Argon2PasswordEncoder` và `PasswordEncoder`. Implementation của Spring Security sử dụng crypto backend tương ứng, thường cần Bouncy Castle trên classpath. Hãy bảo đảm dependency phù hợp; thiếu library có thể gây lỗi runtime dù code biên dịch.

### 6.1. Memory, iterations và parallelism

Ba nhóm tham số mà bạn phải hiểu:

- **m / memory cost**: dung lượng bộ nhớ được thuật toán dùng. Đây là đặc tính khác biệt quan trọng so với các KDF chỉ dùng CPU.
- **t / iterations hoặc passes**: số lượt tính toán; tăng thường tăng thời gian.
- **p / parallelism**: số lanes/độ song song theo thuật toán; ảnh hưởng cách triển khai dùng tài nguyên.

Ngoài ra còn salt length, hash length, biến thể Argon2, version format. Các thông số này nên được gắn với **phiên bản chính sách mã hóa**, để tương lai xác minh hash đã lưu và nâng cấp theo kế hoạch.

Không áp dụng tham số từ bảng benchmark của một CPU/RAM khác mà không đo. Đặc biệt khi chạy trên Kubernetes, serverless hoặc máy có RAM thấp, memory cost trên mỗi concurrent request có thể làm giảm throughput hoặc khiến pod bị OOM kill.

### 6.2. Điều gì làm Argon2id là một lựa chọn tốt?

Khả năng “đòi RAM” làm chi phí thử song song tăng lên trên nhiều cấu hình GPU/ASIC; trong khi đó phía server có thể chủ động phân bổ ngân sách RAM cho mỗi lần hash. Với ứng dụng mới, Argon2id thường là một ứng viên hàng đầu **nếu** runtime và vận hành hỗ trợ được memory cost hợp lý.

Không vì thế mà mặc định “một API Argon2id với cấu hình bất kỳ là đủ”. Cần kiểm tra:

1. Biến thể Argon2id và tham số thực tế.
2. Mức RAM/CPU/latency dưới p95/p99 traffic login.
3. Phần mềm crypto, phiên bản thư viện và hành vi khi nâng cấp.
4. Mô hình deploy, giới hạn memory, giới hạn concurrent hashing.
5. Khả năng tương thích với hệ thống khác và quá trình migrate hash cũ.

## 7. Quyết định chọn thuật toán theo bối cảnh

Không nên xếp hạng một cách tuyệt đối. Một quy trình quyết định thực tế:

| Điều kiện dự án | Lựa chọn cần đánh giá trước | Vì sao | Rủi ro còn phải xử lý |
| --- | --- | --- | --- |
| Ứng dụng mới, chủ động được RAM/cost, không bị khóa bởi giao thức cũ | Argon2id | Memory-hard; tham số linh hoạt | Thư viện, RAM cho concurrency, benchmark |
| Dự án đang có BCrypt, nhiều user và ưu tiên migration ít gián đoạn | Tiếp tục xác minh BCrypt, cân nhắc chuyển dần sang Argon2id/SCrypt | Không ép reset toàn bộ password, giảm rủi ro migration | Cost BCrypt, giới hạn 72 byte, versioning |
| Có yêu cầu interoperability hoặc provider/compliance liên quan PBKDF2 | PBKDF2 với PRF và iterations được phê duyệt | Hỗ trợ rộng, dễ kiểm toán trong một số hệ sinh thái | Không memory-hard, phải calibrate iterations và xác minh compliance thực |
| Muốn memory-hard nhưng dự án đã vận hành SCrypt tốt | SCrypt | Có chi phí RAM và CPU | Cost N/r/p, Bouncy Castle, memory pressure |
| Server thiếu RAM và traffic xác thực cao | Benchmark BCrypt/PBKDF2 và đánh giá nâng cấp hạ tầng | Giới hạn vận hành thực tế | Không chọn work factor quá thấp chỉ để đạt latency |
| Hash store pha trộn nhiều thuật toán/version | DelegatingPasswordEncoder và rehash dần | Cho phép hỗ trợ hash cũ, thay encoder mặc định có kiểm soát | Prefix, unknown ids, migration state |

**Cây quyết định gợi ý:**

~~~text
Có yêu cầu compliance/provider cụ thể?
   |-- Có --> Xác minh thuật toán + triển khai được phê duyệt
   |           (PBKDF2 thường là một ứng viên, không tự suy ra đạt FIPS)
   |
   |-- Không --> Có thể cấp RAM cho mỗi attempt + giới hạn concurrency?
                 |-- Có --> Benchmark Argon2id và SCrypt
                 |-- Không --> Benchmark BCrypt/PBKDF2 ở cost phù hợp
                               + đánh giá lại hạ tầng/threat model

Đã có hash cũ trong database?
   |-- Có --> Giữ verifier cho legacy, phiên bản hóa hash,
   |          chỉ rehash sau matches thành công hoặc quy trình an toàn khác
   |-- Không --> Chọn id/version policy ngay khi hệ thống bắt đầu
~~~

Một password dài, ngẫu nhiên, không tái sử dụng vẫn quan trọng. Không thuật toán nào cứu được toàn bộ rủi ro nếu user dùng mật khẩu bị lộ, endpoint login không có rate limiting hoặc ứng dụng đã bị chiếm quyền truy cập.

## 8. Benchmark đúng: cân bằng độ khó tấn công và khả năng phục vụ

Một chính sách hashing tốt không nằm ở một con số “mặc định trên blog”. Nên đặt một mục tiêu latency **có ngân sách riêng** cho encode/verify, dựa trên SLA và tính toán lưu lượng thực. Đo ít nhất:

- **Thời gian đơn request:** median/p95/p99 của `matches` và `encode` với dữ liệu đại diện.
- **Môi trường chạy:** instance CPU, kiến trúc x86/ARM, container CPU quota, JVM, GC, provider version.
- **Bộ nhớ:** heap/native, mức cấp phát và high-watermark, số attempt đồng thời.
- **Throughput:** requests/second, burst, timeout, queueing, khả năng bị DoS ở endpoint login.
- **Khả năng scale:** số replica, chi phí cloud và tác động đến thread pool của Servlet container.

Ví dụ: nếu mỗi attempt dùng 32 MiB riêng và 100 attempt thực sự chạy đồng thời, chỉ riêng phần ngân sách lý tưởng đó đã là khoảng 3.200 MiB, **chưa gồm** heap, threads và overhead của thuật toán. Đây là phép tính minh họa, không phải số RAM cố định cho Argon2/SCrypt. Với password hashing memory-hard, đặt **giới hạn concurrent attempts** và kiểm tra áp lực tài nguyên dưới load xấu.

### 8.1. Đo chi phí mà không làm benchmark sai

Bản đo đơn giản cho một encoder:

~~~java
long start = System.nanoTime();
boolean matched = encoder.matches(rawPassword, storedHash);
long elapsedNanos = System.nanoTime() - start;

System.out.println("verified=" + matched);
System.out.println("elapsedMillis=" + elapsedNanos / 1_000_000);
~~~

Đây là **mảnh code minh họa**, không phải chương trình độc lập. Giá trị `elapsedMillis` không cố định, không thể đưa một stdout chính xác chung cho mọi máy. Để làm benchmark nghiêm túc cần warm-up, lặp nhiều lần, ngăn compiler/JIT bóp méo kết quả, kiểm soát CPU quotas, đo nhiều percentile và mô phỏng concurrency. Có thể dùng JMH cho microbenchmark cùng load test ngoài hệ thống thực tế.

Không benchmark bằng cách gọi `encode` một lần trên laptop rồi áp cost cho production. Không tắt cost cao khi phát hành chỉ vì test chạy chậm; thay vào đó dùng test strategy hợp lý cho các đơn vị không cần chạy crypto thật, nhưng vẫn có integration tests đủ chứng minh encoder đã cấu hình và kiểm chứng được password thực.

### 8.2. Ứng phó online attacks mà không hạ cấp password hash

Hashing chậm cũng có thể bị lợi dụng để gây quá tải. Ngoài việc calibrate, triển khai:

- Rate limiting phân tầng theo account/IP/device và cơ chế chống credential stuffing.
- Resource pool/queue với giới hạn số lần verify đồng thời.
- MFA/passkeys khi phù hợp, phát hiện đăng nhập bất thường.
- Giám sát latency, CPU, memory, authentication failures, retry storm.
- Chính sách thông báo lỗi tránh lộ user enumeration, không trả timing/status quá khác biệt giữa user có/không tồn tại khi có thể ngăn.
- Dự phòng capacity cho thời điểm đổi password hàng loạt hoặc rehash dần.
- HTTPS và bảo vệ secret trong logs/traces/snapshot.

## 9. Spring Security: cấu hình PasswordEncoder như thế nào?

Trong Spring Security, `PasswordEncoder` được các provider xử lý username/password sử dụng để xác minh credentials. Với Spring Boot Servlet, ứng dụng thường khai báo một bean:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder(12);
}
~~~

Đoạn này đặt trong class `@Configuration`, thêm `@Bean` và các import; **không** có nghĩa mọi luồng authentication tự động dùng bean đó nếu bạn đã cấu hình custom manager/provider khác. Hãy kiểm tra bean wiring và luồng authentication thực tế.

### 9.1. DelegatingPasswordEncoder và prefix định danh

`DelegatingPasswordEncoder` dùng một mã định danh thuật toán trong encoded password:

~~~text
{id}encodedPassword
~~~

Ví dụ về **hình dạng**, không phải chuỗi hash có thể dùng để xác thực:

~~~text
{bcrypt-v1}<BCrypt hash>
{pbkdf2-v1}<PBKDF2 encoded hash>
{argon2id-v1}<Argon2 encoded hash>
~~~

`idForEncode` chỉ định thuật toán dùng khi **tạo hash mới**, còn phần tiền tố của **hash đã lưu** giúp chọn verifier đúng cho dữ liệu cũ. Nhờ đó có thể migrate dần thay vì đổi thuật toán và làm toàn bộ user mất khả năng đăng nhập.

### 9.2. Chính sách có phiên bản: không phụ thuộc vào tên ngắn chung chung

Ví dụ tự tạo một policy với id tùy chỉnh:

~~~java
Map<String, PasswordEncoder> encoders = new HashMap<>();

encoders.put("bcrypt-v1", new BCryptPasswordEncoder(12));
encoders.put("pbkdf2-v1",
    Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8());
encoders.put("scrypt-v1",
    SCryptPasswordEncoder.defaultsForSpringSecurity_v5_8());
encoders.put("argon2id-v1",
    Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8());

PasswordEncoder selected =
    new DelegatingPasswordEncoder("argon2id-v1", encoders);
~~~

Đây là **mảnh code**, cần import `Map, HashMap`, `PasswordEncoder`, `DelegatingPasswordEncoder` và các encoder cụ thể. Việc đặt tên version giúp đổi cost/PRF/Argon2 settings trong tương lai mà vẫn giữ verifier cũ. Phải đảm bảo id được lưu trên DB chính xác và có một chính sách clear cho legacy hashes.

Lưu ý `argon2id-v1` ở đây là **id ứng dụng tự đặt**, không phải tên id chuẩn mặc định của `PasswordEncoderFactories`. Verifier nhận được hash chỉ khi map chứa id đó. Đừng gửi hash chứa id tùy chỉnh cho một dịch vụ khác rồi mặc định dịch vụ đó hiểu.

### 9.3. Sử dụng factory có sẵn

Spring Security cũng có:

~~~java
PasswordEncoder selected =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();
~~~

Factory chọn một cấu hình mặc định của framework (thường dùng BCrypt làm encoder để tạo hash mới) và đăng ký một số verifier tương ứng. **Luôn kiểm tra bản Spring Security đang dùng**: id/parameter mappings có thể thay đổi theo release, và default không đồng nghĩa với policy đã được tổ chức của bạn phê duyệt.

Đừng trộn hai cách: id ứng dụng `argon2id-v1` không tự tồn tại trong map tạo bởi factory trừ khi ứng dụng đã đăng ký theo cách phù hợp.

### 9.4. Thiếu prefix khi nâng cấp từ legacy

Một hash BCrypt cũ có thể lưu dạng `$2a$...` mà không có `{bcrypt}` prefix. `DelegatingPasswordEncoder` không thể mặc định suy luận chắc chắn thuật toán cho mọi giá trị như vậy; có thể báo lỗi không có id/unmapped id.

Hướng xử lý an toàn:

1. Kiểm kê các định dạng hash đã tồn tại (regex/nguồn hệ thống), không dựa vào phỏng đoán.
2. Xác định verifier chỉ cho đúng loại legacy đã biết, không chấp nhận plaintext hoặc `NoOpPasswordEncoder` làm fallback chung.
3. Nếu tiền tố có thể bổ sung bằng migration dữ liệu **không đổi nội dung hash**, hãy kiểm thử trước trên bản sao dữ liệu và có rollback.
4. Nếu cần fallback runtime, chỉ áp dụng cho bản ghi legacy được định danh rõ, kiểm soát và giám sát số lượng; không cho mọi unknown id đi qua một verifier dễ dãi.
5. Sau khi user login thành công, tạo hash mới theo policy và cập nhật an toàn với concurrency control.
6. Theo dõi số lượng legacy hashes còn lại; đặt kế hoạch loại bỏ verifier cũ sau khi đủ điều kiện, không xóa khi dữ liệu cũ chưa được chuyển.

### 9.5. upgradeEncoding không tự nâng cấp mật khẩu

`PasswordEncoder.upgradeEncoding(stored)` là một tín hiệu rằng encoded value nên được cập nhật theo policy, ví dụ algorithm id không còn là idForEncode hoặc tham số đã thấp. Nó **không** có raw password và không thể tự tạo hash mới từ hash cũ.

Một lộ trình rehash-at-login:

~~~text
1. User nhập raw password qua HTTPS
2. matches(raw, storedHash) == true
3. Nếu cần upgrade theo policy:
       newHash = currentEncoder.encode(raw)
       UPDATE users SET password_hash = newHash
       WHERE id = userId AND password_hash = oldHash
4. Tiếp tục luồng login bình thường
~~~

Điều kiện `WHERE password_hash = oldHash` minh họa **compare-and-swap/optimistic concurrency**: tránh ghi đè thay đổi mật khẩu vừa được request khác cập nhật. Một số flow dùng version column. Việc rehash và lưu nằm ở ứng dụng/dịch vụ persistence hoặc tích hợp như `UserDetailsPasswordService` trong luồng DAO authentication phù hợp; cần kiểm tra provider có bật đường nâng cấp thực sự.

Không rehash khi password sai. Không lấy encoded hash cũ làm raw password để hash lần hai (double-hash) vì nó tạo giao thức mới và không có giá trị tương đương với rehash đúng từ raw password.

## 10. Ví dụ Java 17+ chạy được: thử cả bốn encoder

Ví dụ dự án Spring Boot 3.3.5 dưới đây là **ứng dụng console** để học password hashing. Nó không mở HTTP port và không chứa auth endpoint; điều này giúp tách việc chọn encoder khỏi cấu hình Servlet security filter chain. Sau khi hiểu cơ chế, bạn có thể dùng các encoder tương tự trong bean `PasswordEncoder` của ứng dụng Spring MVC.

### 10.1. Cấu trúc dự án

~~~text
password-hash-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/hash/
    │   └── PasswordHashLabApplication.java
    └── test/java/demo/hash/
        └── PasswordHashLabApplicationTests.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'password-hash-lab'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.security:spring-security-crypto'

    // Spring Security SCrypt và Argon2 encoder cần crypto backend.
    implementation 'org.bouncycastle:bcprov-jdk18on:1.78.1'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter` đem tới cơ chế khởi động ứng dụng console. `spring-security-crypto` cung cấp các `PasswordEncoder` cần học; chương trình không yêu cầu `spring-boot-starter-web` hay đăng ký `SecurityFilterChain`. Bouncy Castle cung cấp các primitive cần cho SCrypt/Argon2 trong triển khai sử dụng. Dự án thực nên để BOM/version catalog quản lý phiên bản thư viện đã được kiểm thử và kiểm tra cảnh báo bảo mật dependency; version minh họa ở đây nhằm làm ví dụ có cấu hình đầy đủ.

### 10.2. Chương trình

Tệp `src/main/java/demo/hash/PasswordHashLabApplication.java`:

~~~java
package demo.hash;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.crypto.argon2.Argon2PasswordEncoder;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;
import org.springframework.security.crypto.scrypt.SCryptPasswordEncoder;

@SpringBootApplication
public class PasswordHashLabApplication implements CommandLineRunner {

    public static void main(String[] args) {
        SpringApplication.run(PasswordHashLabApplication.class, args);
    }

    static Map<String, PasswordEncoder> encoders() {
        Map<String, PasswordEncoder> result = new LinkedHashMap<>();

        result.put("BCrypt", new BCryptPasswordEncoder(12));
        result.put("PBKDF2",
            Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8());
        result.put("SCrypt",
            SCryptPasswordEncoder.defaultsForSpringSecurity_v5_8());
        result.put("Argon2",
            Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8());

        return result;
    }

    @Override
    public void run(String... args) {
        String raw = "correct-horse-battery-staple";

        encoders().forEach((name, encoder) -> {
            String hash = encoder.encode(raw);
            boolean valid = encoder.matches(raw, hash);
            boolean invalid = encoder.matches("definitely-wrong", hash);

            System.out.println(name + ": correct=" + valid
                + ", wrong=" + invalid);
        });
    }
}
~~~

Với class và project như trên, phần **stdout do chính code `System.out.println` tạo ra** theo thứ tự `LinkedHashMap` là:

~~~text
BCrypt: correct=true, wrong=false
PBKDF2: correct=true, wrong=false
SCrypt: correct=true, wrong=false
Argon2: correct=true, wrong=false
~~~

Spring Boot có thể in thêm banner/log khởi động; vì vậy bảng stdout này **không** khẳng định toàn bộ console chỉ có bốn dòng. Hash thực tế không được in vì salt ngẫu nhiên sẽ làm chuỗi thay đổi mỗi lần chạy, và không nên log encoded password ở production.

### 10.3. Test để kiểm tra từng encoder

Tệp `src/test/java/demo/hash/PasswordHashLabApplicationTests.java`:

~~~java
package demo.hash;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PasswordHashLabApplicationTests {

    @Test
    void allEncodersAcceptCorrectAndRejectIncorrectPasswords() {
        PasswordHashLabApplication.encoders().forEach((name, encoder) -> {
            String hash = encoder.encode("demo-password");

            assertNotNull(hash, name);
            assertTrue(encoder.matches("demo-password", hash), name);
            assertFalse(encoder.matches("wrong-password", hash), name);
        });
    }

    @Test
    void encodedValueIsNotPlaintext() {
        PasswordEncoder encoder =
            PasswordHashLabApplication.encoders().get("BCrypt");

        String hash = encoder.encode("demo-password");

        assertFalse("demo-password".equals(hash));
        assertTrue(encoder.matches("demo-password", hash));
    }
}
~~~

Hai test này kiểm tra contract `encode/matches` và không so sánh hash với một giá trị cố định. Nếu đã thay tham số thuật toán, những test cơ bản vẫn có giá trị. Để kiểm chứng migration, cần bổ sung test nhiều id/version theo §DelegatingPasswordEncoder§ và dữ liệu hash cũ đã biết.

### 10.4. Chạy

Trong thư mục dự án, nếu có Gradle phù hợp được cài:

~~~bash
gradle test
gradle bootRun
~~~

Nếu có Gradle wrapper, ưu tiên:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Trên Windows dùng `gradlew.bat test` và `gradlew.bat bootRun`. Chương trình Spring Boot cần classpath dependency; lệnh `javac`/`java` trần không chạy được khi thiếu JAR. Các phép hash có thể tốn thời gian đáng kể tùy tham số/phần cứng; không dùng thời gian chạy cục bộ để kết luận thuật toán nào tốt nhất.

## 11. Ví dụ chính sách triển khai: bean DelegatingPasswordEncoder

Trong ứng dụng Servlet thực tế, bạn có thể khai báo một bean duy nhất để provider username/password sử dụng:

~~~java
package demo.security;

import java.util.HashMap;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.argon2.Argon2PasswordEncoder;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.password.Pbkdf2PasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;
import org.springframework.security.crypto.scrypt.SCryptPasswordEncoder;

@Configuration
public class PasswordPolicyConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        Map<String, PasswordEncoder> verifiers = new HashMap<>();

        verifiers.put("bcrypt-2026",
            new BCryptPasswordEncoder(12));
        verifiers.put("pbkdf2-2026",
            Pbkdf2PasswordEncoder.defaultsForSpringSecurity_v5_8());
        verifiers.put("scrypt-2026",
            SCryptPasswordEncoder.defaultsForSpringSecurity_v5_8());
        verifiers.put("argon2id-2026",
            Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8());

        return new DelegatingPasswordEncoder(
            "argon2id-2026", verifiers);
    }
}
~~~

Đây là **class Spring cấu hình dùng trong một ứng dụng đã có các dependencies phù hợp**, không phải một ứng dụng chạy độc lập. Khi dùng trong production, thay id theo policy và cấu hình tham số **đã benchmark**; code này chỉ minh họa cơ chế hỗ trợ nhiều thuật toán/version và dùng Argon2id cho hash mới.

### 11.1. Đường đi khi đăng ký

~~~java
String rawPassword = registrationRequest.password();
String encoded = passwordEncoder.encode(rawPassword);
// Chỉ lưu encoded trong database.
~~~

Đây là mảnh code minh họa; `registrationRequest`, `passwordEncoder` và lớp persistence được ứng dụng cung cấp. Encoded password có prefix của policy mới. Không lưu plaintext vào event log, request trace, telemetry hoặc một cột phụ dùng “debug”.

### 11.2. Đường đi khi đăng nhập

~~~java
boolean valid =
    passwordEncoder.matches(rawPasswordFromLogin, storedHash);
~~~

Đây là mảnh code; mã xác thực thực trong Spring Security thường nằm tại provider thích hợp, không cần tự gọi `matches` trong controller nếu đã dùng provider đúng. Với DelegatingPasswordEncoder, verifier được chọn theo id trong stored hash; kết quả đúng mới có thể dẫn đến Authentication thành công.

### 11.3. Lộ trình chuyển thuật toán qua các phiên bản

Giả sử database lưu:

~~~text
{bcrypt-2026}$2a$...             -> vẫn được kiểm tra bằng bcrypt-2026
{pbkdf2-2026}<PBKDF2 data>     -> vẫn được kiểm tra bằng pbkdf2-2026
{argon2id-2026}<Argon2 data>  -> hash mới theo policy hiện tại
~~~

Các chuỗi trên là **ký hiệu format**, không phải hash có thể đem vào `matches`. Một ứng dụng có thể trong tương lai giới thiệu `argon2id-2028` với thông số cost khác, giữ `argon2id-2026` làm verifier cho dữ liệu cũ, rồi rehash dần lúc user login thành công.

Versioning này giải quyết hai vấn đề:

1. **Đổi thuật toán** từ BCrypt/PBKDF2/SCrypt sang Argon2id mà không khóa user cũ.
2. **Đổi tham số** của cùng một thuật toán sau benchmark mà vẫn nhận diện rõ verifier phù hợp.

Không bỏ verifier cũ sớm; một người dùng ít đăng nhập có thể giữ hash legacy trong nhiều năm. Cân nhắc chính sách đặt lại password cho những account không thể migrate thụ động và có rủi ro cao, nhưng cần đánh giá tác động trải nghiệm.

## 12. Tình huống thực tế và sai lầm thường gặp

### 12.1. Đã có BCrypt, có cần chuyển toàn bộ sang Argon2 ngay?

Không nhất thiết. Trước tiên xác nhận cost hiện tại, danh sách hash còn sống, những account mật khẩu yếu/leaked, khả năng bảo vệ online và ngân sách production. Một kế hoạch có thể là:

- Giữ verifier BCrypt an toàn cho hash cũ.
- Benchmark Argon2id với memory/time có chủ đích.
- Cài policy `DelegatingPasswordEncoder` với id mới.
- Chuyển hash sau login thành công bằng raw password hiện có trong phiên xác thực.
- Quan sát latency, error rate và số lượng legacy còn lại.
- Dọn verifier legacy khi không còn dữ liệu phải hỗ trợ hoặc có chính sách reset hợp lệ.

### 12.2. Đặt tất cả encoder theo tham số mặc định rồi benchmark thời gian

Không đủ để tuyên bố “thuật toán A mạnh hơn B” nếu các tham số mặc định đại diện cho chi phí rất khác nhau. Hãy đặt một **ngân sách latency/RAM**, chọn và đo nhiều cấu hình ứng viên trong ngân sách đó, rồi so sánh chi phí tấn công theo các đặc tính của thuật toán. Nếu tổ chức yêu cầu mức chống chịu khác, điều chỉnh cả ngân sách hạ tầng.

### 12.3. Dùng cùng một salt cho mọi tài khoản để tiện kiểm thử

Đây là anti-pattern. Salt phải được sinh ngẫu nhiên và riêng cho từng mật khẩu; không cố định salt để hash có output “đẹp”. Test nên kiểm tra `matches` và định dạng hợp lệ, không cần giá trị encoded luôn bằng một chuỗi cố định.

### 12.4. Gắn pepper nhưng lưu ngay trong cùng database với hash

Như vậy gần như không đạt mục tiêu phân tách bí mật. Pepper nếu dùng phải được bảo vệ độc lập, version hóa, có kế hoạch rotation và phục hồi; mất pepper có thể khiến các hash phụ thuộc pepper không còn xác minh được. Không bắt đầu thêm pepper khi chưa có thiết kế vận hành.

### 12.5. Dùng NoOpPasswordEncoder để chữa lỗi legacy prefix

`NoOpPasswordEncoder` không mã hóa mật khẩu; đưa nó làm fallback mặc định cho hash thiếu prefix có thể tạo lỗ hổng nghiêm trọng. Dữ liệu legacy không có id phải được xử lý theo **format đã biết, migration được kiểm chứng**, không bằng cách hạ cấp chuẩn bảo mật.

### 12.6. Dùng BCrypt với password Unicode rất dài mà không xác minh byte length

Giới hạn khoảng 72 byte của BCrypt là dễ bị bỏ qua. Nếu ứng dụng cho phép password dài, phải có chính sách rõ ràng về byte encoding, test đầu vào vượt giới hạn và migration. Một thay đổi normalize Unicode thiếu nhất quán có thể làm password cũ không đăng nhập được. Không áp dụng trim/lowercase password như username.

### 12.7. Đổi PBKDF2 PRF/iterations nhưng không nhận diện version

Hash cũ có thể trở nên không thể kiểm tra hoặc bị dùng sai tham số. Hãy đóng gói version/mapping rõ và giữ profile cũ cho tới khi không còn giá trị cần xác minh.

### 12.8. Memory-hard làm tăng bảo mật nhưng làm hệ thống sập khi traffic tăng

Argon2id/SCrypt bảo vệ tốt hơn ở một số threat model bằng cách đòi RAM, nhưng cần đặt giới hạn concurrent hashing, đo memory cao điểm và bảo vệ endpoint trước traffic không tin cậy. Không để request login vô hạn chiếm memory độc lập chỉ vì mỗi password được bảo vệ bằng thuật toán mạnh.

### 12.9. Cho rằng PasswordEncoder thay thế được toàn bộ auth architecture

Không. PasswordEncoder chỉ kiểm tra password; authorization, account status, khóa user, MFA, token/session, CSRF, HTTPS và rate limiting là các lớp khác. Với Spring Security Servlet, tích hợp đúng `AuthenticationProvider`, `UserDetailsService`, `AuthenticationManager` và `SecurityFilterChain` vẫn phải được đảm bảo.

### 12.10. Tưởng BCrypt/Argon2 giống mã hóa đối xứng có thể decrypt

Password KDF là chức năng một chiều. Không lưu khóa AES bên cạnh password hashes để “giải mã khi user quên”; thiết kế đúng là reset mật khẩu bằng quy trình an toàn và hash mới.

## 13. Bài tập thực hành

1. Giải thích vì sao không được thay `PasswordEncoder.matches(raw, encoded)` bằng `encode(raw).equals(encoded)`.
2. Với một hệ thống đã lưu 500.000 bcrypt hashes, lập kế hoạch migrate sang Argon2id mà không yêu cầu user đăng nhập đồng thời và không làm mất tài khoản ít hoạt động.
3. Phân biệt **CPU-hard** và **memory-hard**. Vì sao SCrypt/Argon2id đòi RAM có thể làm tấn công offline ở quy mô lớn tốn kém hơn, nhưng cũng khiến endpoint login chịu áp lực DoS?
4. Chọn BCrypt/PBKDF2/SCrypt/Argon2id cho ba bối cảnh: (a) Java backend cần tương thích rộng, (b) tổ chức bị ràng buộc compliance/provider cụ thể, (c) dịch vụ mới có ngân sách RAM và khả năng benchmark. Giải thích các điều kiện bổ sung thay vì chỉ ghi tên thuật toán.
5. Thiết kế benchmark có warm-up, p50/p95/p99, throughput, concurrency, memory budget; nêu lý do không lấy một lần `System.nanoTime` làm quyết định cuối cùng.
6. Viết test kiểm tra `PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo hash có id đúng theo phiên bản framework đang dùng; không hardcode output hash.
7. Với hash legacy BCrypt không có prefix, đề xuất migration an toàn. Tại sao fallback “mọi hash thiếu prefix dùng NoOp” là nguy hiểm?
8. Giải thích sự khác nhau giữa `upgradeEncoding(storedHash)` và việc thực sự cập nhật DB. Thiết kế SQL update có kiểm soát cạnh tranh.
9. Với BCrypt, giải thích vì sao giới hạn khoảng 72 **byte** khiến chuỗi Unicode nhiều ký tự đa byte dễ gặp tình huống khó phát hiện.
10. Nếu policy hiện tại là `argon2id-2026` nhưng database còn `pbkdf2-2026`, sau matches thành công nên cập nhật ra sao? Điều gì xảy ra nếu user đổi mật khẩu cùng lúc?
11. Nếu ứng dụng bị lộ password hash database nhưng API login có rate limiting rất mạnh, tại sao tấn công offline vẫn cần được xem xét?
12. Khi dùng SCrypt hoặc Argon2, chọn giới hạn số hash attempt đồng thời như thế nào theo RAM limit/CPU quota thực tế?
13. Mô tả cách cất và rotate pepper nếu tổ chức yêu cầu, phân biệt nó với salt được đóng gói trong hash.

## 14. Checklist chọn và vận hành password hashing

- [ ] Threat model bao gồm cả database breach/offline cracking và online credential stuffing.
- [ ] Chỉ dùng password hashing/KDF thích hợp, không dùng MD5/SHA-256 đơn thuần hoặc plaintext.
- [ ] Mỗi password có salt ngẫu nhiên do encoder tạo; không reuse salt cố định.
- [ ] Thuật toán và tham số được **benchmark trên hạ tầng thật** và có lịch rà soát.
- [ ] Với memory-hard, tính RAM/concurrency và đặt giới hạn tài nguyên.
- [ ] Nếu có yêu cầu compliance, kiểm tra provider/chứng nhận, không chỉ tên thuật toán.
- [ ] Password policy xử lý Unicode/độ dài nhất quán; lưu ý giới hạn byte của BCrypt.
- [ ] Dùng `PasswordEncoder.matches`, không tái encode rồi so hash string.
- [ ] Hash được lưu với **algorithm/version id** nếu hỗ trợ nhiều profile.
- [ ] Legacy format có verifier giới hạn; unknown id/malformed hash được xử lý fail-closed.
- [ ] Có kế hoạch rehash sau login thành công, cập nhật DB an toàn và theo dõi migration.
- [ ] Không log raw passwords, token, pepper hoặc encoded hashes bừa bãi.
- [ ] Login có rate limiting, monitoring, HTTPS, MFA khi phù hợp và error handling không lộ user enumeration.
- [ ] Code Spring Security Servlet có `PasswordEncoder` được inject đúng vào provider/manager đang sử dụng.
- [ ] Có unit tests `encode/matches`, integration tests authentication và test migration.
- [ ] Có phương án rollback/version compatibility khi đổi thuật toán hoặc cost.

**Kết luận:** BCrypt là lựa chọn thực dụng và phổ biến; PBKDF2 có lợi thế tương thích và có thể phù hợp yêu cầu chuẩn/provider; SCrypt và Argon2id là những lựa chọn memory-hard đáng đánh giá để tăng chi phí tấn công offline. **Thuật toán tốt nhất trong sản phẩm là thuật toán được cấu hình, benchmark, version hóa, giám sát và nâng cấp đúng với threat model của sản phẩm đó.** Trong Spring Security, `PasswordEncoder` và `DelegatingPasswordEncoder` giúp biến quyết định này thành một chính sách triển khai có thể tiến hóa theo thời gian.
