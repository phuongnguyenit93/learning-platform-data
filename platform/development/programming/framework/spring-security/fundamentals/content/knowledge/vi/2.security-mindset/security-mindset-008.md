# Phân biệt tính bí mật, tính toàn vẹn và tính sẵn sàng (CIA Triad)

## 1. Ba mục tiêu bảo mật cơ bản

Để thiết kế bảo mật cho một ứng dụng Spring Boot, trước tiên cần xác định **điều gì cần được bảo vệ**. Ba mục tiêu nền tảng là:

- **Confidentiality — Tính bí mật (C):** Chỉ những chủ thể được phép mới có thể biết hoặc đọc thông tin.
- **Integrity — Tính toàn vẹn (I):** Dữ liệu và hành động phải giữ đúng trạng thái, nguồn gốc và quy tắc được phép; thay đổi trái phép hoặc ngoài ý muốn cần được ngăn chặn hoặc phát hiện.
- **Availability — Tính sẵn sàng (A):** Người dùng và hệ thống được phép có thể truy cập chức năng, dữ liệu và dịch vụ khi cần với chất lượng chấp nhận được.

Bộ ba này được gọi là **CIA Triad**. Đây là **mục tiêu của bảo mật**, không phải tên ba công nghệ cụ thể. Authentication, authorization, mã hóa, transaction, backup hay rate limiting là **những phương tiện** góp phần đạt một hoặc nhiều mục tiêu ấy.

Hãy hình dung ứng dụng ngân hàng: nếu thông tin số dư bị lộ cho người ngoài, lỗi chính là **bí mật**. Nếu số dư bị sửa mà không có giao dịch hợp lệ, lỗi chính là **toàn vẹn**. Nếu khách hàng không thể chuyển tiền vì hệ thống bị tê liệt, lỗi chính là **sẵn sàng**. Hệ thống có thể bảo vệ rất tốt hai mục tiêu nhưng vẫn thất bại ở mục tiêu còn lại.

| Khía cạnh | Confidentiality | Integrity | Availability |
| --- | --- | --- | --- |
| Câu hỏi cần trả lời | **Ai được đọc hoặc biết?** | **Ai được thay đổi và kết quả có đúng?** | **Người có quyền có dùng được lúc cần?** |
| Vi phạm điển hình | Rò rỉ dữ liệu | Sửa hoặc giả mạo dữ liệu | Mất khả năng phục vụ |
| Ví dụ trong API | USER A đọc đơn hàng USER B | USER A duyệt đơn hoặc sửa giá trái quyền | Checkout liên tục timeout |
| Kiểm soát thường gặp | Quyền truy cập, TLS, mã hóa, masking | Quyền ghi, validation, transaction, CSRF protection, HMAC/chữ ký | Giới hạn tải, dự phòng, timeout, backup, khôi phục |
| Cách kiểm chứng | Test đọc trái quyền | Test sửa trái quyền và trạng thái DB | Load test, failover test, đo latency/uptime |

**Lưu ý:** C, I và A không loại trừ nhau. Một vụ tấn công có thể làm lộ dữ liệu, sửa dữ liệu và khiến dịch vụ ngừng hoạt động cùng lúc. Bảng trên cho thấy **tác động trực tiếp nổi bật** của từng mục tiêu.

## 2. Confidentiality — Tính bí mật

### 2.1. Bí mật nghĩa là gì?

Một dữ liệu có tính bí mật khi **chỉ được tiết lộ cho những danh tính, vai trò, dịch vụ hoặc tiến trình có quyền**. Cần bảo vệ cả dữ liệu **đang truyền**, **đang lưu** và **đang được xử lý hoặc xuất ra**.

“Không tiết lộ” không chỉ có nghĩa là không trả dữ liệu ở API chính. Dữ liệu vẫn có thể lộ qua:

- Response có thêm trường nhạy cảm mà client không cần.
- URL, query string, log, stack trace, access log, debug trace.
- File cấu hình chứa mật khẩu, API key, token hoặc private key.
- Cache công khai, file export, bản backup chưa kiểm soát quyền.
- Mạng không có TLS, cho phép người nghe lén quan sát nội dung.
- API cho phép người đăng nhập đọc tài nguyên không thuộc về mình.

### 2.2. Ví dụ: đăng nhập đúng nhưng đọc sai dữ liệu

API có **GET /orders/42**. Người dùng A đăng nhập thành công với role USER, rồi thay số 42 trong URL thành ID đơn hàng của B. Nếu server chỉ kiểm tra authenticated() mà không xác minh **chủ sở hữu đơn**, response có thể trả địa chỉ giao hàng, số điện thoại và tổng tiền của B.

Đây là lỗi **Broken Object Level Authorization (BOLA/IDOR)** và trực tiếp vi phạm C. **Authentication** trả lời A là ai. **Authorization theo dữ liệu** phải trả lời A có quyền đọc **đơn cụ thể** hay không. Có authentication không có nghĩa mọi dữ liệu đều bí mật.

### 2.3. Biện pháp bảo vệ C

1. **Kiểm soát truy cập:** Xác thực, role/authority, permission và kiểm tra quyền sở hữu từng bản ghi trước khi trả dữ liệu.
2. **Least privilege:** User, service account, database role và API key chỉ được cấp quyền tối thiểu cần để làm việc.
3. **Bảo vệ kênh truyền:** Dùng HTTPS/TLS; không gửi mật khẩu và dữ liệu nhạy cảm qua HTTP thuần trên mạng thật.
4. **Bảo vệ nơi lưu:** Mã hóa phù hợp với loại dữ liệu, quản lý khóa, bảo vệ backup và hạn chế truy cập database.
5. **Giảm tiết lộ ngoài ý muốn:** Chỉ trả các trường cần thiết qua DTO, che dấu secret trong log, không phản hồi stack trace nhạy cảm.
6. **Quản lý vòng đời:** Hết hạn và thu hồi session/token, xoay vòng secret, xử lý tài khoản bị vô hiệu hóa.

**Điểm cần phân biệt:** Mã hóa không tự giải quyết authorization. Một response được gửi qua HTTPS vẫn có thể làm lộ dữ liệu khi server trả thông tin của B cho A. Ẩn một nút hoặc một trang ở frontend cũng không thay cho server-side authorization.

### 2.4. Kiểm thử C như thế nào?

Tạo hai user A và B với đơn hàng riêng. Đăng nhập bằng A rồi thử đọc đơn của B bằng URL và API client trực tiếp. Kỳ vọng là response **không chứa dữ liệu trái quyền**, bất kể hệ thống trả 403 hoặc 404 theo chính sách chống tiết lộ sự tồn tại của tài nguyên. Kiểm tra thêm log và response có lộ token, passwordHash hoặc trường nhạy cảm không.

## 3. Integrity — Tính toàn vẹn

### 3.1. Toàn vẹn nghĩa là gì?

Tính toàn vẹn nghĩa là dữ liệu và thao tác **không bị sửa trái phép, giả mạo, mất mát hoặc biến đổi sai quy tắc**. Dữ liệu vẫn được phép thay đổi bình thường: khách hàng cập nhật địa chỉ, quản trị viên duyệt đơn, kế toán ghi nhận giao dịch. Mục tiêu không phải là “không bao giờ được đổi”, mà là **đổi đúng quyền, đúng điều kiện và đúng kết quả**.

Có thể nhìn I ở ba cấp:

- **Quyền thao tác:** Người gọi có được tạo, sửa, xóa hoặc duyệt dữ liệu này không?
- **Độ tin cậy của nội dung:** Request/payload có bị thay đổi, giả mạo hoặc không đạt quy tắc nghiệp vụ không?
- **Tính nhất quán kết quả:** Sau giao dịch, trạng thái dữ liệu có đúng hay bị ghi đè đồng thời hoặc cập nhật một phần?

### 3.2. Ví dụ trực tiếp

- USER thường gọi **POST /admin/orders/42/approve** và đơn bị duyệt dù user không có quyền ADMIN: **I bị vi phạm bởi thao tác trái quyền**.
- Client gửi totalPrice=100 cho đơn hàng thực tế có giá 900; server tin giá từ client và lưu vào database: **I bị vi phạm do tin dữ liệu không đáng tin**.
- Hai request cùng trừ tiền ở một tài khoản, dẫn đến số dư sai vì thiếu transaction/locking thích hợp: **I bị vi phạm bởi lỗi xử lý đồng thời**.
- Kẻ tấn công sửa nội dung gói tin hoặc dữ liệu cấu hình đã ký: cần cơ chế xác minh tính toàn vẹn và nguồn dữ liệu.

Tất cả các tình huống này có thể xảy ra **mà không cần rò rỉ dữ liệu bí mật**. Vì vậy việc bảo vệ C không đồng nghĩa đã bảo vệ I.

### 3.3. Biện pháp bảo vệ I

1. **Authorization cho thao tác ghi:** Phân biệt quyền đọc và quyền thay đổi; kiểm tra chủ sở hữu, quyền thực hiện hành động và trạng thái nghiệp vụ.
2. **Validation:** Kiểm tra kiểu dữ liệu, độ dài, số tiền, giá trị enum, trạng thái chuyển đổi, các ràng buộc liên trường.
3. **Business invariants:** Không tin các trường nhạy cảm do client tự đặt như ownerId, role hoặc totalPrice; tính lại hoặc tra nguồn đáng tin.
4. **Database integrity:** Dùng transaction, unique/foreign-key constraints, optimistic locking hoặc cơ chế đồng bộ thích hợp.
5. **Chống giả mạo trên đường truyền:** Dùng TLS; khi giao thức yêu cầu xác thực độc lập cho dữ liệu, dùng HMAC hoặc chữ ký số với khóa được quản lý đúng.
6. **CSRF protection khi phù hợp:** Chặn một số yêu cầu thay đổi trạng thái bị website khác kích hoạt trong trình duyệt đang đăng nhập.
7. **Audit và khôi phục:** Ghi dấu thao tác quan trọng để truy vết, phát hiện bất thường, phục hồi khi dữ liệu bị sửa hoặc xóa sai.

Không nên coi “đã kiểm tra ROLE_USER” là đủ nếu API cho phép USER A sửa bản ghi của USER B. Quy tắc ở tầng Service cần đối chiếu **principal đã xác thực** với **dữ liệu sở hữu thật**.

### 3.4. Hash, HMAC và chữ ký số có liên quan gì?

- **Hash mật mã** như SHA-256 cho fingerprint của nội dung. Muốn dùng để kiểm tra toàn vẹn, giá trị hash chuẩn phải lấy từ **nguồn đáng tin**. Hash đơn thuần không xác thực ai tạo ra nội dung.
- **HMAC** dùng khóa bí mật chung để tạo mã xác thực. Nếu khóa được giữ an toàn, người kiểm tra có thể phát hiện nội dung bị đổi và xác minh người tạo có biết khóa chung. HMAC **không mã hóa** nội dung.
- **Chữ ký số** dùng private key để ký và public key tương ứng để xác minh. Chữ ký không che giấu plaintext, và bên xác minh phải tin cậy public key.
- **Mã hóa có xác thực (AEAD)** có thể cung cấp cả bí mật và xác thực/toàn vẹn cho dữ liệu được mã hóa, nhưng vẫn không tự chứng minh quyền nghiệp vụ.

Ví dụ một file và mã hash cùng được lưu ở nơi kẻ tấn công có quyền sửa cả hai: kẻ đó có thể thay file rồi tính hash mới. Việc hai giá trị khớp không chứng minh dữ liệu đến từ nguồn đáng tin.

### 3.5. Kiểm thử I như thế nào?

Thử gọi hành động ghi bằng user sai quyền, sửa ownerId hoặc totalPrice trong payload, gửi request lặp, tạo hai yêu cầu đồng thời và kiểm tra **trạng thái database cuối cùng**. Với endpoint duyệt đơn, kiểm thử quan trọng không chỉ là response 403 mà còn phải khẳng định **đơn không bị chuyển trạng thái** sau yêu cầu bị từ chối.

## 4. Availability — Tính sẵn sàng

### 4.1. Sẵn sàng nghĩa là gì?

Hệ thống có tính sẵn sàng khi **người dùng có quyền** có thể sử dụng dịch vụ **khi họ cần**, với thời gian đáp ứng và chất lượng phù hợp. Một service có tiến trình còn chạy nhưng tất cả request đều timeout vẫn không có availability tốt. Cũng vậy, một API liên tục trả 503 hoặc phụ thuộc database ngừng hoạt động là sự cố A.

**403 cho người không đủ quyền không phải là vi phạm A.** Đó có thể là kết quả bảo mật đúng. Ta đánh giá A dựa trên **người có quyền và yêu cầu hợp lệ**, không phải yêu cầu tùy ý của người không được phép.

### 4.2. Những nguyên nhân điển hình

- Lưu lượng tăng đột biến hoặc tấn công DoS/DDoS làm CPU, RAM, thread pool, connection pool cạn kiệt.
- Database, identity provider, DNS, message broker hoặc hạ tầng mạng bị lỗi.
- Deploy sai cấu hình khiến ứng dụng không khởi động hoặc không thể xử lý nghiệp vụ.
- Retry vô hạn hoặc tác vụ nặng làm nghẽn tài nguyên dùng chung.
- Bản ghi/hệ thống lưu trữ hỏng mà không có backup/restore khả dụng.
- Chính sách khóa tài khoản quá cứng bị lợi dụng để khóa người dùng hợp lệ.

### 4.3. Biện pháp bảo vệ A

1. **Kiểm soát tải:** Rate limiting phù hợp với người dùng/IP, quota, giới hạn kích thước request, request timeout, queue và concurrency limits.
2. **Tránh điểm lỗi đơn:** Nhiều instance, load balancer, health checks, failover và kiến trúc hạ tầng phù hợp.
3. **Hạn chế lỗi dây chuyền:** Timeout, circuit breaker, bulkhead, retry giới hạn và backoff để không làm dependency sụp đổ nặng hơn.
4. **Sao lưu và khôi phục:** Thử restore định kỳ; xác định mục tiêu thời gian khôi phục **RTO** và mức mất dữ liệu chấp nhận **RPO**.
5. **Theo dõi khả năng phục vụ:** Error rate, latency, saturation, availability SLI/SLO và hành trình nghiệp vụ quan trọng.
6. **Triển khai có kiểm soát:** Rollback, rolling deployment, capacity planning và diễn tập xử lý sự cố.

Rate limiting không phải thuốc chữa mọi dạng DDoS; hạ tầng mạng, CDN/WAF, cấu hình tài nguyên và khả năng mở rộng vẫn quan trọng. Ngược lại, một cơ chế khóa tài khoản thiếu cân nhắc có thể khiến kẻ tấn công liên tục nhập sai mật khẩu để **làm mất quyền truy cập hợp lệ** của nạn nhân.

### 4.4. Availability và trách nhiệm của Spring Security

Spring Security cung cấp kiểm soát xác thực, phân quyền và một số cơ chế web, nhưng **không tự tạo** hệ thống load balancing, multi-region failover, backup, restore, circuit breaker hay distributed rate limiting hoàn chỉnh. Chúng thường thuộc thiết kế ứng dụng, hạ tầng, API gateway và vận hành.

## 5. Cùng một API: nhìn đủ ba góc độ

Xét hệ thống đặt hàng có các chức năng xem đơn, sửa đơn và thanh toán:

| Hoạt động | Câu hỏi cho C | Câu hỏi cho I | Câu hỏi cho A |
| --- | --- | --- | --- |
| GET /orders/42 | Người gọi có quyền **đọc** đơn 42? | Dữ liệu trả có đúng bản ghi, không bị làm giả? | Người hợp lệ có nhận response đúng hạn? |
| PATCH /orders/42 | Có lộ dữ liệu riêng trong response/log? | Người gọi có quyền sửa; giá trị mới có hợp lệ? | Khi database chậm, API có timeout và phục hồi hợp lý? |
| POST /payments | Có lộ tài khoản, token, dữ liệu cá nhân? | Có xác thực giao dịch, chống lặp, đảm bảo transaction? | Có chịu được tải, lỗi dependency và khôi phục? |

Ba tình huống mẫu:

**Tình huống A — Lộ đơn hàng:** User A đọc được địa chỉ của B. Kiểm soát thiếu là quyền truy cập bản ghi: **C**.

**Tình huống B — Giá bị đổi trái phép:** User A không có quyền nhưng gửi một request khiến tổng tiền trên server bị thay đổi. Kiểm soát thiếu là quyền ghi và ràng buộc nghiệp vụ: **I**.

**Tình huống C — Hệ thống checkout nghẽn:** Khách đã xác thực có quyền thanh toán nhưng liên tục timeout vì hết connection database. Kiểm soát thiếu là tài nguyên, backpressure hoặc phục hồi: **A**.

Các lỗi có thể kết hợp. Ví dụ một token bị đánh cắp làm mất bí mật của credentials, từ đó kẻ tấn công đọc hoặc sửa dữ liệu; một vụ xóa dữ liệu vừa phá toàn vẹn vừa làm gián đoạn dịch vụ.

## 6. Spring Security hỗ trợ từng mục tiêu đến đâu?

Spring Security **trực tiếp nhất** hỗ trợ xác thực, phân quyền và một số lớp bảo vệ request, session và browser. Các chức năng ấy tác động rõ tới C/I nhưng không thay thế thiết kế availability.

| Cơ chế | Giá trị với CIA | Điều framework chưa tự giải quyết |
| --- | --- | --- |
| Authentication | Xác minh principal để áp dụng quyền đọc/ghi | Đã đăng nhập không có nghĩa được đọc/sửa mọi bản ghi |
| HTTP authorization | Chặn request ngoài quyền; bảo vệ C và I | Matcher URL không thay thế điều kiện ownerId trong DB |
| Method security | Áp kiểm tra quyền ở phương thức nghiệp vụ | Cần cấu hình đúng và xử lý trường hợp gọi nội bộ/proxy |
| CSRF protection | Hỗ trợ I trước request thay đổi trạng thái bị giả mạo | Không thay thế transaction, permission hoặc validation |
| Session/security context | Duy trì ngữ cảnh principal để áp dụng chính sách | Cần thiết kế cookie, timeout, logout, kiến trúc session |
| Security headers | Giảm một số nguy cơ liên quan browser | Không tự tạo CSP chính xác cho mọi app, không thay TLS |
| HTTPS/TLS | Có thể bảo vệ C và I trên đường truyền | Phải được cấu hình ở server, ingress/proxy và client |
| Rate limit, HA, backup, failover | Chủ yếu phục vụ A | Không tự có đầy đủ khi cài starter-security |

**Ví dụ:** endpoint GET /profile yêu cầu authenticated() là bước đầu cho C. Tuy nhiên, Controller phải trả hồ sơ của người gọi hoặc kiểm tra quyền đọc hồ sơ mục tiêu. Endpoint POST /payments yêu cầu authenticated() chỉ mới biết người gọi; để đạt I còn cần owner check, số dư/hạn mức, validation, transaction, chống request lặp và CSRF khi mô hình trình duyệt có rủi ro tương ứng.

### 6.1. Cấu hình minh họa trong Spring MVC

Đây là **đoạn cấu hình SecurityFilterChain** dùng trong một class Spring được quản lý, với import @Bean, SecurityFilterChain, HttpSecurity, HttpMethod và Customizer tương ứng. Nó là **mã minh họa phụ thuộc Spring Boot/Spring Security**, không phải file Java thuần có thể biên dịch độc lập:

~~~java
@Bean
SecurityFilterChain appSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/catalog").permitAll()
            .requestMatchers(HttpMethod.GET, "/profile").authenticated()
            .requestMatchers(HttpMethod.POST, "/payments").authenticated()
            .requestMatchers(HttpMethod.POST, "/admin/**").hasRole("ADMIN")
            .anyRequest().denyAll()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Cấu hình cho phép mọi người đọc catalog, người đã xác thực truy cập profile/payment, chỉ ADMIN gọi POST thuộc /admin/** và từ chối các request chưa được phân loại. **Các matcher không tự bảo đảm** rằng thông tin profile thuộc đúng người, payment đủ tiền hoặc có đủ khả năng chịu tải.

Lưu ý với POST: Spring Security thường bật CSRF protection trong Servlet theo mặc định. Ví dụ dùng HTTP Basic trong trình duyệt có thể cần **CSRF token hợp lệ** để gửi request thay đổi trạng thái; nếu thiếu, request có thể bị 403 ngay cả khi role hợp lệ. Đừng tắt CSRF theo thói quen mà phải đánh giá cách client gửi credentials.

### 6.2. Một lỗi thường gặp khi đánh giá bảo mật

Nhận định “API đã có SecurityFilterChain nên bảo đảm CIA” là không đúng. Filter chain có thể chặn người thiếu quyền tại ranh giới HTTP, nhưng:

- C vẫn thất bại nếu Service trả dữ liệu user B cho A.
- I vẫn thất bại nếu một giao dịch hợp lệ được xử lý sai, cập nhật nửa chừng hoặc ghi giá từ client mà không kiểm tra.
- A vẫn thất bại nếu database, mạng hoặc service tê liệt.

Chọn giải pháp bảo mật phải dựa vào **tài sản, mối đe dọa và hậu quả**, không chỉ dựa vào số annotation.

## 7. Thực hành Java 17: Integrity khác Confidentiality thế nào?

Ta có thể dùng **HMAC-SHA256** để thấy nội dung thay đổi sẽ bị phát hiện khi người kiểm tra giữ đúng khóa bí mật. Chương trình này chạy bằng **JDK 17+**, không phụ thuộc Spring.

Tạo file **IntegrityDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class IntegrityDemo {

    private static byte[] tag(String message, byte[] secret)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(message.getBytes(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        byte[] secret = "demo-only-secret".getBytes(StandardCharsets.UTF_8);
        String original = "order=42&amount=100";
        String tampered = "order=42&amount=900";

        byte[] expectedTag = tag(original, secret);

        System.out.println("Original valid: "
                + MessageDigest.isEqual(expectedTag, tag(original, secret)));
        System.out.println("Tampered valid: "
                + MessageDigest.isEqual(expectedTag, tag(tampered, secret)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac IntegrityDemo.java
java IntegrityDemo
~~~

Stdout xác định từ chương trình:

~~~text
Original valid: true
Tampered valid: false
~~~

**Giải thích:** HMAC tạo tag cho thông điệp gốc từ nội dung và khóa chung. Khi amount đổi từ 100 sang 900 nhưng tag gốc giữ nguyên, phép kiểm tra thất bại. Đây là **phát hiện sửa nội dung và xác thực nguồn biết khóa**, một phần của **Integrity**.

Chương trình **không mã hóa** chuỗi order/amount; người đọc được thông điệp vẫn thấy số tiền, vì vậy **Confidentiality chưa được bảo vệ**. Chương trình cũng không cam kết luôn hoạt động khi máy hỏng hay bị quá tải, vì vậy **Availability chưa được giải quyết**. HMAC đơn độc không kiểm tra role, quyền sở hữu, logic chuyển tiền và không ngăn phát lại một thông điệp hợp lệ trước đó (replay). Khóa hard-code chỉ để học; trong ứng dụng thật phải lưu khóa an toàn và thiết kế giao thức đầy đủ.

## 8. Từ CIA đến phân tích rủi ro và kiểm thử

Một quy trình nhỏ để áp dụng ngay trong dự án:

1. **Liệt kê tài sản:** Hồ sơ, credential, số dư, đơn hàng, dữ liệu backup, chức năng duyệt, API thanh toán.
2. **Xác định chủ thể có quyền:** User nào được đọc, sửa, xóa, duyệt; service nào được dùng dữ liệu?
3. **Viết rủi ro C:** Ai có thể xem dữ liệu trái quyền qua endpoint, log, backup hoặc kết nối?
4. **Viết rủi ro I:** Ai có thể sửa trái quyền, giả mạo payload, gửi lặp hoặc tạo trạng thái sai?
5. **Viết rủi ro A:** Người có quyền có thể bị từ chối phục vụ, timeout hay mất dữ liệu trong bao lâu?
6. **Chọn biện pháp ở đúng tầng:** Spring Security ở authn/authz và CSRF, Service/DB ở quy tắc dữ liệu, TLS ở kết nối, hạ tầng ở capacity và phục hồi.
7. **Thiết kế negative tests:** Trường hợp bị từ chối phải không rò rỉ dữ liệu và không làm thay đổi DB.
8. **Kiểm chứng vận hành:** Theo dõi latency, error rate, capacity; diễn tập restore và xác định RTO/RPO.

Bảng kiểm thử mẫu:

| Mục tiêu | Ca kiểm thử | Tiêu chí đạt |
| --- | --- | --- |
| C | User A gọi GET /orders/42 khi đơn thuộc B | Không nhận được dữ liệu B |
| C | Log phát sinh lỗi đăng nhập | Không ghi mật khẩu hoặc token |
| I | USER gọi endpoint duyệt chỉ ADMIN được dùng | Không thay đổi trạng thái bản ghi |
| I | Client cố sửa totalPrice không hợp lệ | Server từ chối hoặc tự tính lại theo quy tắc |
| I | Hai request cùng cập nhật số dư | Kết quả DB nhất quán theo giao dịch |
| A | Dependency database tạm ngừng | Có timeout/cảnh báo, giới hạn lỗi dây chuyền và phục hồi được |
| A | Lưu lượng tăng mạnh | Dịch vụ ưu tiên vẫn phục vụ trong giới hạn thiết kế |
| A + I | Phục hồi bản backup sau sự cố | Hệ thống hoạt động, dữ liệu khôi phục đúng mục tiêu RPO |

### Khi nào ghi nhiều thuộc tính cho cùng một rủi ro?

Hãy nêu hậu quả **trực tiếp** trước, sau đó nêu các tác động liên quan:

- Lấy cắp token: C đối với credential, có thể dẫn tới C/I ở dữ liệu tùy quyền token.
- Ransomware làm dữ liệu không thể truy cập: A; nếu dữ liệu bị phá hoặc sửa trái phép thì còn I.
- Mất database và bản backup: A vì hệ thống không phục vụ; I vì dữ liệu đúng không được giữ/khôi phục.
- Dịch vụ rơi vào deadlock: chủ yếu A; nếu transaction vẫn atomic, không nhất thiết ảnh hưởng I.

Cách nhìn này tốt hơn việc ép mỗi sự cố vào một và chỉ một nhãn.

## 9. Các ngộ nhận cần tránh

**“Đã đăng nhập thì dữ liệu được giữ bí mật.”** Sai. Phải kiểm tra quyền đọc đối với từng tài nguyên và các đường lộ khác như log, backup, export.

**“Mã hóa xong thì chắc chắn dữ liệu không bị sửa.”** Sai. Không phải mọi cách mã hóa đều cung cấp xác thực/toàn vẹn. Cần chọn cơ chế phù hợp, ví dụ AEAD khi cần cả bí mật và toàn vẹn.

**“Có SHA-256 là biết người gửi đáng tin.”** Sai. Hash thông thường không xác thực nguồn; hash chuẩn phải lấy từ nguồn tin cậy, hoặc dùng HMAC/chữ ký số với khóa được quản lý đúng.

**“Có ROLE_ADMIN rồi thì mọi giao dịch đúng.”** Sai. Quyền thao tác không thay thế validation, điều kiện nghiệp vụ, transaction và xử lý đồng thời.

**“CORS thay CSRF.”** Sai. CORS là chính sách trình duyệt về truy cập cross-origin, không thay thế xác thực, phân quyền hoặc CSRF protection khi cần.

**“Rate limiting giải quyết mọi DDoS.”** Sai. Nó chỉ là một lớp kiểm soát tải; vẫn phải quan tâm mạng, hạ tầng, dependency và capacity.

**“403 nghĩa là API mất tính sẵn sàng.”** Không nhất thiết. Từ chối đúng người thiếu quyền là bảo mật hoạt động đúng; tính sẵn sàng xét với **người có quyền**.

**“Tính toàn vẹn chỉ bị phá bởi hacker.”** Sai. Lỗi lập trình, race condition, thao tác nhầm và deploy lỗi cũng có thể gây I hoặc A.

## 10. Tự kiểm tra kiến thức

**Câu 1.** A đã đăng nhập nhưng xem được địa chỉ giao hàng của B. Thuộc tính bị vi phạm?  
**Đáp:** **C**. Authentication chưa đủ; thiếu authorization theo bản ghi.

**Câu 2.** Một user chỉ có quyền xem nhưng sửa được trạng thái đơn. Thuộc tính bị vi phạm?  
**Đáp:** **I** vì hệ thống chấp nhận thao tác ghi trái quyền.

**Câu 3.** Người dùng hợp lệ không thanh toán được trong 40 phút vì database pool hết connection. Thuộc tính bị ảnh hưởng?  
**Đáp:** **A**. Đồng thời phải kiểm tra I nếu có giao dịch cập nhật dở hoặc mất dữ liệu.

**Câu 4.** SHA-256 của file khớp với hash nằm cạnh file trên server đã bị chiếm quyền. Có chứng minh file đáng tin?  
**Đáp:** **Không**. Kẻ tấn công có thể đổi cả file và hash; cần nguồn hash tin cậy hoặc xác thực bằng khóa.

**Câu 5.** HTTPS bảo đảm CIA đầy đủ cho API không?  
**Đáp:** **Không**. TLS bảo vệ kênh truyền nhưng không tự kiểm tra quyền trên dữ liệu, quy tắc giao dịch hay availability của dịch vụ.

**Câu 6.** Backup liên quan A hay I?  
**Đáp:** **Cả A và I**: giúp khôi phục khả năng phục vụ và trạng thái dữ liệu đúng theo mục tiêu khôi phục. Backup chứa dữ liệu nhạy cảm cũng cần bảo vệ C.

**Câu 7.** Tại sao CSRF có thể liên quan I dù người dùng đã đăng nhập đúng?  
**Đáp:** Trình duyệt có thể tự gửi credentials khi trang độc hại kích hoạt request thay đổi trạng thái, khiến server chấp nhận hành động người dùng không chủ ý. CSRF token là một lớp phòng vệ phù hợp cho các luồng có nguy cơ đó.

## 11. Tài liệu đọc tiếp

- NIST — Confidentiality: https://csrc.nist.gov/glossary/term/confidentiality
- NIST — Integrity: https://csrc.nist.gov/glossary/term/integrity
- NIST — Availability: https://csrc.nist.gov/glossary/term/availability
- Spring Security — Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/index.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
