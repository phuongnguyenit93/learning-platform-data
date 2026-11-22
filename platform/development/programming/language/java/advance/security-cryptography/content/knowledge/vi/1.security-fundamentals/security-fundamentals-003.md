# 1.3 Phân biệt tính bí mật, tính toàn vẹn, xác thực và phân quyền

Bốn khái niệm **confidentiality**, **integrity**, **authentication** và **authorization** trả lời bốn câu hỏi khác nhau của bảo mật ứng dụng Java: **ai có thể biết dữ liệu**, **dữ liệu có bị thay đổi hay không**, **chủ thể đang tương tác là ai**, và **chủ thể đó được phép làm gì**. Một hệ thống có thể làm tốt ba việc đầu nhưng vẫn rò rỉ dữ liệu nếu kiểm tra phân quyền sai.

## 1. Bốn câu hỏi phải tách bạch

| Thuộc tính | Câu hỏi cốt lõi | Rủi ro nếu thiếu | Cơ chế điển hình |
| --- | --- | --- | --- |
| **Tính bí mật (Confidentiality)** | Ai có thể **đọc/biết** nội dung? | Người không được phép thấy thông tin nhạy cảm | TLS, mã hóa khi lưu trữ, quản lý khóa, giới hạn quyền đọc |
| **Tính toàn vẹn (Integrity)** | Nội dung có bị **sửa đổi** trái phép hoặc ngoài dự kiến? | Số tiền, lệnh, file hoặc thông điệp bị thay đổi mà không bị phát hiện | HMAC, chữ ký số, mã hóa có xác thực như AES-GCM, kiểm tra dữ liệu |
| **Xác thực (Authentication)** | Chủ thể đang yêu cầu là **ai**, và bằng chứng danh tính có đáng tin? | Kẻ khác giả làm người dùng/dịch vụ hợp lệ | Mật khẩu được xác minh an toàn, MFA, passkey, session, token, chứng chỉ |
| **Phân quyền (Authorization)** | Danh tính đã xác thực được **thao tác gì trên tài nguyên nào**, trong ngữ cảnh nào? | Người dùng hợp lệ truy cập dữ liệu/quyền của người khác | Kiểm tra sở hữu tài nguyên, RBAC, ABAC, policy, least privilege |

Ghi nhớ: **xác thực danh tính đi trước quyết định phân quyền**, nhưng cả hai khác với tính bí mật và tính toàn vẹn của dữ liệu. Khi nói về bộ ba **CIA** trong bảo mật, chữ A là **Availability (tính sẵn sàng)**, không phải Authentication.

### 1.1. Tính bí mật: ngăn việc tiết lộ dữ liệu

Tính bí mật yêu cầu thông tin chỉ lộ cho chủ thể có quyền biết. Cần xét nơi dữ liệu tồn tại và di chuyển:

- **Trên đường truyền:** HTTPS/TLS che nội dung khỏi người nghe lén trên đường truyền khi kết nối được thiết lập và xác minh chứng chỉ đúng cách.
- **Khi lưu trữ:** mã hóa dữ liệu nhạy cảm ở đĩa, bản sao lưu hoặc từng trường; khóa giải mã phải được bảo vệ và phân quyền riêng.
- **Trong ứng dụng:** không để token, mật khẩu, khóa bí mật hoặc dữ liệu cá nhân lọt vào log, thông báo lỗi, cache hay phản hồi API quá rộng.
- **Ở ranh giới truy cập:** dù server có thể giải mã, server vẫn phải xác định ai được phép xem kết quả.

Ví dụ, file được mã hóa bằng AES vẫn có thể bị lộ nếu endpoint giải mã rồi trả nội dung cho bất cứ người dùng nào đã đăng nhập. **Mã hóa không tự tạo ra quy tắc ai được đọc**.

Trong Java, **AES-GCM** là lựa chọn phổ biến cho mã hóa đối xứng có xác thực: nó bảo vệ bí mật và phát hiện sửa đổi ciphertext nếu khóa, nonce và dữ liệu xác thực liên quan được dùng đúng. Việc quản lý khóa và tránh dùng lại nonce với cùng khóa là điều kiện bắt buộc.

### 1.2. Tính toàn vẹn: phát hiện hoặc ngăn sửa đổi trái phép

Tính toàn vẹn quan tâm đến việc dữ liệu còn đúng như trạng thái được tin cậy hay không. Cần phân biệt các công cụ:

- **SHA-256 không dùng khóa** tạo dấu vân tay của nội dung. Nó có ích khi giá trị hash kỳ vọng được lấy từ một nguồn đáng tin cậy. Nếu kẻ tấn công sửa được cả file lẫn hash công bố, phép so sánh hash không chứng minh nguồn gốc hoặc chống giả mạo.
- **HMAC-SHA256** dùng khóa bí mật chung để tạo mã xác thực thông điệp. Người không biết khóa khó tạo HMAC hợp lệ cho nội dung đã sửa. HMAC không mã hóa nội dung; các bên cùng giữ khóa đều có thể tạo tag.
- **Chữ ký số** dùng khóa riêng để ký và khóa công khai để kiểm tra tính toàn vẹn, nguồn ký. Để gắn khóa công khai với một danh tính cụ thể, vẫn cần cơ chế tin cậy như chứng chỉ hoặc phân phối khóa xác thực.
- **AEAD**, chẳng hạn AES-GCM, kết hợp mã hóa với kiểm tra tính toàn vẹn/xác thực của bản mã và dữ liệu AAD được ràng buộc vào tag.

**Toàn vẹn không đồng nghĩa với tính mới.** Một thông điệp HMAC đúng có thể bị phát lại (replay). Tùy giao thức, cần thêm nonce, số thứ tự, thời hạn, idempotency key hoặc bộ nhớ chống replay và kiểm tra chúng trên server.

Không dùng phép so sánh chuỗi thông thường để kiểm tra MAC theo cách có thể làm lộ thông tin thời gian; Java có **MessageDigest.isEqual(byte[], byte[])** để so sánh byte array theo cách phù hợp hơn cho trường hợp này.

### 1.3. Xác thực: kiểm chứng danh tính trước khi tin yêu cầu

Xác thực xác định **principal** (người dùng, dịch vụ, thiết bị hoặc tiến trình) qua một bằng chứng mà hệ thống có thể kiểm tra, thay vì tin tên được tự khai trong request.

- Với người dùng: password verifier được lưu bằng thuật toán băm mật khẩu có salt và chi phí phù hợp (ví dụ Argon2id, scrypt hoặc PBKDF2), kết hợp MFA/passkey khi cần. Không lưu mật khẩu thô hoặc dùng SHA-256 đơn thuần như giải pháp băm mật khẩu.
- Với phiên đăng nhập: server kiểm tra session hoặc access token; cookie phiên cần thuộc tính bảo vệ phù hợp như Secure, HttpOnly, SameSite theo ngữ cảnh.
- Với token có chữ ký: ngoài chữ ký, phải kiểm tra nhà phát hành, đối tượng nhận, hạn dùng, loại token và các ràng buộc ứng dụng áp dụng. Một token có chữ ký hợp lệ nhưng sai audience vẫn không được chấp nhận.
- Với dịch vụ: mTLS có thể xác thực danh tính dựa vào chứng chỉ client; danh tính dịch vụ đã được kiểm tra vẫn phải chịu chính sách phân quyền.

Cũng cần tách **xác thực người gọi** khỏi **xác thực nguồn gốc thông điệp bằng mật mã**. HMAC chứng minh có bên sở hữu khóa chung tạo hoặc xác nhận thông điệp, nhưng nếu nhiều bên chia sẻ khóa thì không chứng minh được chính xác cá nhân nào gửi. Chữ ký số có thể gắn với một chủ thể khi khóa và chứng chỉ được quản trị đúng. Cả hai không thay thế toàn bộ quy trình đăng nhập người dùng.

**HTTPS/TLS** thường giúp client xác thực server thông qua chứng chỉ hợp lệ, đồng thời bảo vệ đường truyền; nó không mặc nhiên cho biết người dùng của ứng dụng đã đăng nhập.

### 1.4. Phân quyền: quyết định hành động trên đúng tài nguyên

Sau khi xác thực, backend dùng danh tính tin cậy và ngữ cảnh hiện tại để quyết định có cho phép **hành động cụ thể** hay không. Quyền cần được kiểm tra ở mức chức năng **và** mức đối tượng.

Ví dụ, Alice và Bob đều có vai trò USER và đều đăng nhập thành công. Nhưng với tài liệu thuộc Alice, Bob vẫn phải bị từ chối nếu chính sách chỉ cho chủ sở hữu hoặc quản trị viên đọc. Lỗ hổng bỏ qua kiểm tra này là một dạng **Broken Object Level Authorization (BOLA/IDOR)**.

Các cách mô tả chính sách thường gặp:

| Mô hình | Quyết định dựa trên | Ví dụ |
| --- | --- | --- |
| **RBAC** (role-based) | Vai trò gắn với principal | ADMIN được quản lý tài khoản |
| **ABAC** (attribute-based) | Thuộc tính principal, tài nguyên và môi trường | Chỉ cho đọc hồ sơ cùng tenant và chưa bị khóa |
| **Kiểm tra sở hữu/quan hệ** | Quan hệ với đối tượng được yêu cầu | Chủ tài liệu được đọc tài liệu của mình |

Trong hệ thống thực tế, thường **kết hợp** các mô hình: người gọi phải có quyền READ_DOCUMENT, thuộc cùng tenant, và là chủ sở hữu hoặc thuộc nhóm được chia sẻ. Nguyên tắc là **deny by default**, **least privilege**, và kiểm tra ở backend cho mọi thao tác nhạy cảm. Việc ẩn nút trên frontend, bật CORS, hoặc có token hợp lệ không thay thế kiểm tra này.

Danh tính, role và tenant tin cậy phải được lấy từ thành phần đã xác thực và dữ liệu backend; không lấy trực tiếp role hay ownerId do client tự gửi để quyết định quyền.

## 2. Một công nghệ có thể đáp ứng nhiều mục tiêu, nhưng không thể suy diễn tất cả

| Biện pháp | Điều nó thực sự cung cấp | Điều không tự cung cấp |
| --- | --- | --- |
| **HTTPS/TLS** | Bí mật và toàn vẹn khi truyền; xác thực endpoint tùy cấu hình chứng chỉ | Đăng nhập người dùng hoặc quyền truy cập từng tài liệu |
| **AES-GCM** | Bí mật và kiểm tra sửa đổi bản mã/AAD | Danh tính người dùng, phân quyền đối tượng, chống replay ở cấp nghiệp vụ |
| **SHA-256 của file** | Dấu vân tay để so sánh với hash kỳ vọng đáng tin | Chứng minh người gửi nếu hash cũng có thể bị sửa |
| **HMAC-SHA256** | Toàn vẹn và bằng chứng sở hữu khóa chung | Che nội dung, phân biệt từng bên cùng giữ khóa, quyết định quyền |
| **Chữ ký số** | Kiểm tra sửa đổi và bằng chứng gắn với khóa ký | Che nội dung, phân quyền ứng dụng |
| **Session/token được xác minh** | Bằng chứng định danh theo quy trình xác thực | Quyền đọc mọi bản ghi |
| **RBAC/ABAC + kiểm tra tài nguyên** | Quyết định cho phép/từ chối hành động | Mã hóa dữ liệu hoặc chứng minh tính toàn vẹn trên đường truyền |

**Những trường hợp dễ nhầm:**

1. **Đã đăng nhập nhưng đọc đơn hàng người khác:** xác thực thành công, **phân quyền thất bại**.
2. **Dùng HTTPS nhưng ghi mật khẩu vào log:** đường truyền được bảo vệ, nhưng **bí mật bị phá vỡ** ở tầng ứng dụng.
3. **File có hash SHA-256 công khai đặt cạnh file và cả hai cùng bị thay:** không có căn cứ tin cậy để kết luận file nguyên vẹn.
4. **Payload đã mã hóa nhưng dùng chế độ không xác thực:** tính bí mật không bảo đảm phát hiện mọi sửa đổi; nên dùng AEAD phù hợp.
5. **HMAC hợp lệ của lệnh chuyển tiền cũ được gửi lại:** tính toàn vẹn của thông điệp có thể vẫn đúng, nhưng nghiệp vụ phải chống replay.

## 3. Đi theo một request: bốn bước kiểm tra độc lập

Xét API **GET /documents/42**, với dữ liệu có **ownerId = alice**, người gọi là **bob**:

1. **Bảo vệ truyền tải:** client kết nối HTTPS, xác minh chứng chỉ server. TLS bảo vệ nội dung trong quá trình truyền, nhưng chưa quyết định Bob có được xem tài liệu 42 hay không.
2. **Xác thực Bob:** middleware kiểm tra session hoặc token, xác định principal là bob. Thiếu/sai thông tin xác thực thường trả **401 Unauthorized** (tên HTTP hơi dễ gây nhầm: mã này liên quan đến yêu cầu xác thực).
3. **Phân quyền đối tượng:** backend đọc metadata tài liệu và kiểm tra policy: Bob có quyền READ_DOCUMENT không, có đúng tenant không, có phải chủ sở hữu hoặc người được chia sẻ không? Nếu không, thường trả **403 Forbidden**; một số hệ thống chủ động trả **404** để không tiết lộ sự tồn tại tài nguyên, nhưng phải thống nhất chính sách.
4. **Lấy và trả nội dung:** nếu được phép, server trả đúng dữ liệu; mã hóa đường truyền và cơ chế toàn vẹn tiếp tục bảo vệ dữ liệu trên kênh. Nếu dữ liệu được lưu mã hóa, giải mã chỉ diễn ra sau các kiểm tra quyền cần thiết.

Một request thực tế có thể kiểm tra quyền trước và sau khi lấy metadata, hoặc gộp điều kiện quyền trực tiếp vào truy vấn, ví dụ giới hạn theo principal/tenant. Điểm bất biến là **không trả tài liệu khi chưa xác nhận quyền đối với chính tài liệu đó**; không kiểm tra đơn thuần “đã login” hoặc “có role USER”.

Các biến thể đáng chú ý:

- **POST /documents:** cần quyền tạo trong tenant/nhóm được chọn; không cho client tự đặt ownerId/tenantId để leo quyền.
- **PUT /documents/42:** quyền đọc không mặc nhiên bao gồm quyền sửa.
- **GET /documents?tenantId=...:** phải giới hạn kết quả ở tenant thực sự được phép truy cập; lọc riêng trên frontend là không đủ.
- **Dịch vụ gọi dịch vụ:** đã xác thực bằng mTLS/token vẫn phải kiểm tra service account có quyền gọi endpoint cụ thể.

## 4. Một request, bốn quyết định độc lập

Giả sử Bob gọi `GET /documents/42`; bản ghi này có `ownerId=alice`, còn nội dung được lưu bằng AES-GCM. Việc kiểm chứng từng thuộc tính diễn ra ở những nơi khác nhau:

| Thứ tự kiểm tra | Câu hỏi | Kết quả nếu thất bại |
| --- | --- | --- |
| **Bí mật trên đường truyền** | Client có kết nối đúng HTTPS server với chứng chỉ và hostname hợp lệ không? | Không trao đổi nội dung nhạy cảm qua endpoint chưa được xác minh |
| **Xác thực người gọi** | Session/token có hợp lệ, đúng issuer/audience/hạn và ánh xạ thành Bob không? | Từ chối yêu cầu chưa xác thực (thường 401) |
| **Phân quyền đối tượng** | Bob có quyền READ_DOCUMENT trên tài liệu 42, đúng tenant và điều kiện hiện hành không? | Từ chối trước khi lấy/trả bản rõ (theo policy dùng 403 hoặc 404) |
| **Toàn vẹn bản mã** | Sau khi có quyền giải mã, khóa, nonce, ciphertext/tag và AAD có xác thực thành công không? | Bỏ kết quả, báo lỗi có kiểm soát, không sử dụng plaintext chưa được xác thực |

Thứ tự triển khai có thể khác theo query và caching, nhưng **không được trả bản rõ cho Bob nếu chưa kiểm quyền trên chính tài liệu 42**. Thành công của `Cipher.doFinal` hay HMAC trên payload không phải bằng chứng Bob được xem tài liệu. Ngược lại, quyền đọc tài liệu cũng không cho phép bỏ kiểm tra tag của dữ liệu lưu trữ.

Bài toán cấp primitive của AES-GCM có thể được kiểm qua thử thay một byte ciphertext/AAD và bắt `AEADBadTagException`; bài này đi sâu vào **cách đặt các kiểm tra bảo mật tại các lớp khác nhau** thay vì lặp lại một chương trình mã hóa độc lập.

## 5. Java 17+: minh họa toàn vẹn HMAC và phân quyền theo chủ sở hữu

Ví dụ tiếp theo cố ý tách hai việc: **verifyHmac** xác minh thông điệp có bị sửa sau khi tạo tag hay không; **canRead** kiểm tra principal đã xác thực có được đọc một tài liệu hay không. Trong ứng dụng thật, principal phải đến từ middleware/session đã xác thực đáng tin, **không được tạo từ userId tự khai trong request**.

Lưu thành **HmacAuthorizationDemo.java**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Set;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class HmacAuthorizationDemo {
    record Principal(String userId, Set<String> roles) {}
    record Document(String ownerId, String content) {}

    static byte[] hmac(String message, byte[] secret)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(message.getBytes(StandardCharsets.UTF_8));
    }

    static boolean verifyHmac(String message, byte[] expectedTag, byte[] secret)
            throws GeneralSecurityException {
        return MessageDigest.isEqual(expectedTag, hmac(message, secret));
    }

    static boolean canRead(Principal principal, Document document) {
        return principal.roles().contains("ADMIN")
                || principal.userId().equals(document.ownerId());
    }

    public static void main(String[] args) throws Exception {
        byte[] secret = "demo-secret-change-in-production"
                .getBytes(StandardCharsets.UTF_8);
        String payload = "owner=alice;amount=900";
        byte[] tag = hmac(payload, secret);

        System.out.println("Thong diep goc hop le: "
                + verifyHmac(payload, tag, secret));
        System.out.println("Thong diep bi sua hop le: "
                + verifyHmac("owner=alice;amount=990", tag, secret));

        Document doc = new Document("alice", payload);
        Principal alice = new Principal("alice", Set.of("READER"));
        Principal bob = new Principal("bob", Set.of("READER"));

        System.out.println("Alice duoc doc: " + canRead(alice, doc));
        System.out.println("Bob duoc doc: " + canRead(bob, doc));
    }
}
```

Biên dịch và chạy:

```bash
javac HmacAuthorizationDemo.java
java HmacAuthorizationDemo
```

Kết quả stdout:

```text
Thong diep goc hop le: true
Thong diep bi sua hop le: false
Alice duoc doc: true
Bob duoc doc: false
```

**Giải thích kết quả:**

- Thông điệp gốc khớp HMAC; đổi **900** thành **990** trong khi giữ tag cũ làm kiểm tra thất bại. HMAC **không che nội dung** thông điệp.
- Alice là chủ tài liệu nên được đọc; Bob có cùng vai trò READER nhưng không sở hữu tài liệu nên bị từ chối. Trong chính sách minh họa, ADMIN cũng có thể đọc. Đây là **quy tắc phân quyền riêng**, hoàn toàn không dựa vào việc HMAC của payload có hợp lệ hay không.
- Hai object Principal được tạo trực tiếp để thử chính sách. Đây **không phải ví dụ xác thực đăng nhập**. Không bao giờ coi tên người dùng do client gửi là một principal đã xác minh.
- Khóa HMAC viết sẵn trong chương trình chỉ để minh họa. Trong sản phẩm, dùng khóa bí mật đủ mạnh từ kho quản lý secret, giới hạn người có quyền sử dụng khóa, có cơ chế xoay khóa và ràng buộc ngữ cảnh/thời hạn/chống replay theo giao thức.

## 6. Các lỗi thiết kế và suy luận phổ biến

| Nhận định sai | Vì sao sai và cách sửa |
| --- | --- |
| “Đã đăng nhập thì truy cập ID bất kỳ được.” | Xác thực chỉ biết danh tính. Kiểm tra quyền trên **từng hành động và từng đối tượng**, gồm owner và tenant. |
| “Có HTTPS thì API đã an toàn.” | TLS bảo vệ kênh, không sửa được lỗi quyền truy cập, dữ liệu nhạy cảm bị log hoặc ứng dụng lộ secret. |
| “Tự băm SHA-256 là bảo đảm dữ liệu do đúng server gửi.” | Hash không có khóa không chứng minh nguồn; cần hash kỳ vọng đáng tin, HMAC hoặc chữ ký tùy mô hình tin cậy. |
| “Mã hóa đồng nghĩa chống sửa dữ liệu.” | Không phải mọi chế độ mã hóa đều xác thực; ưu tiên AEAD như AES-GCM và xử lý tag sai bằng cách từ chối dữ liệu. |
| “JWT có chữ ký hợp lệ là đủ.” | Còn phải xác thực issuer, audience, expiry, key và các policy liên quan; quyền đối tượng vẫn kiểm tra riêng. |
| “Ẩn nút sửa hoặc dùng CORS là phân quyền.” | Client và CORS không phải cổng kiểm soát quyền của backend; phải từ chối thao tác trái phép ngay trên server. |
| “HMAC chứng minh Alice đã ký.” | HMAC dùng khóa chia sẻ: mỗi bên giữ khóa đều có thể tạo MAC; muốn ràng buộc từng bên cần cơ chế danh tính/khóa phù hợp. |
| “Thông điệp có chữ ký đúng thì chắc chắn là yêu cầu mới.” | Chữ ký/MAC không tự chống phát lại; cần timestamp, nonce, sequence hoặc idempotency control. |
| “Mật khẩu nên được mã hóa để có thể giải mã khi đăng nhập.” | Mật khẩu nên được lưu dạng password hash có salt/cost; khi đăng nhập kiểm tra verifier, không cần giải mã mật khẩu cũ. |

Khi rà soát ứng dụng Java, có thể tự hỏi lần lượt:

1. **Confidentiality:** dữ liệu nào nhạy cảm, nó xuất hiện ở transport, storage, log, cache và response nào? Ai giữ khóa?
2. **Integrity:** làm sao nhận biết dữ liệu bị sửa? Ai tin cậy hash, MAC, chữ ký hoặc tag? Có chống replay không?
3. **Authentication:** principal được xác minh bằng chứng cứ nào? Session/token/chứng chỉ có được kiểm tra đầy đủ và có hết hạn không?
4. **Authorization:** cho phép **ai + hành động gì + tài nguyên nào + tenant/ngữ cảnh nào**? Có chính sách mặc định từ chối và kiểm tra phía server không?

## 7. Tự kiểm tra bằng tình huống

**Tình huống A.** Bob đăng nhập thành công. API trả hóa đơn của Alice khi Bob đổi ID trong URL. Thuộc tính thiếu là gì?  
**Đáp án:** **Authorization**, cụ thể là kiểm tra quyền ở mức đối tượng (BOLA/IDOR). Authentication có thể hoàn toàn đúng.

**Tình huống B.** Người tải file so sánh SHA-256 với giá trị lấy từ cùng một trang đã bị chiếm quyền điều khiển. Đã chứng minh toàn vẹn chưa?  
**Đáp án:** **Chưa có căn cứ tin cậy**. Kẻ tấn công có thể thay cả file lẫn hash. Cần hash/khóa xác minh đến từ nguồn đáng tin.

**Tình huống C.** Hai dịch vụ chia sẻ một khóa HMAC; tag đúng. Có thể khẳng định duy nhất dịch vụ A đã gửi không?  
**Đáp án:** **Không.** Tag chứng minh bên tạo biết khóa chung, không phân biệt các bên cùng sở hữu khóa. Cần ràng buộc danh tính và quản lý khóa riêng nếu nghiệp vụ đòi hỏi.

**Tình huống D.** Server dùng AES-GCM lưu tài liệu. Người dùng hợp lệ gọi API giải mã tài liệu của người khác. Có nên trả nội dung vì giải mã thành công?  
**Đáp án:** **Không.** AES-GCM giải quyết bảo vệ bản mã và kiểm tra sửa đổi; backend còn phải xác thực người dùng và kiểm tra quyền với tài liệu.

**Tình huống E.** Một lệnh đã ký được gửi lại y nguyên sau một giờ. Chữ ký vẫn đúng. Hệ thống cần gì thêm?  
**Đáp án:** Kiểm tra thời hạn, nonce/số thứ tự và trạng thái xử lý để chống **replay**, tùy yêu cầu giao thức.

Điểm cần mang sang các bài mật mã và bảo mật ứng dụng tiếp theo: **bí mật bảo vệ việc nhìn thấy nội dung; toàn vẹn bảo vệ việc bị sửa; xác thực thiết lập danh tính đáng tin; phân quyền áp chính sách lên hành động/tài nguyên cụ thể.** Thiết kế an toàn yêu cầu ghép các lớp bảo vệ này tại đúng ranh giới, không dùng thành công của lớp này để suy ra lớp khác.
