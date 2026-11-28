# Bind và Unbind ở mức giao thức để quản lý phiên xác thực

Trong LDAP, **Bind** là thao tác xác lập danh tính của client trên một **kết nối LDAP**, còn **Unbind** là thông điệp thông báo kết thúc kết nối đó. Hiểu hai thao tác này giúp ứng dụng Spring Data LDAP xác thực đúng người dùng, phân biệt quyền của tài khoản dịch vụ với quyền của người dùng và quản lý tài nguyên kết nối an toàn.

## 1. Mục tiêu học tập và bối cảnh

Sau bài học, bạn có thể:

- Mô tả BindRequest, BindResponse và UnbindRequest ở mức giao thức LDAPv3.
- Phân biệt Bind ẩn danh, Simple Bind, SASL Bind và Rebind; giải thích trạng thái xác thực gắn với kết nối.
- Giải thích vì sao Unbind không có phản hồi và khác với việc thu hồi phiên đăng nhập HTTP.
- Áp dụng luồng xác thực qua `LdapTemplate` hoặc `LdapContextSource`; đóng context đúng cách và không để lộ thông tin đăng nhập.
- Nhận diện rủi ro khi dùng LDAP không mã hóa, mật khẩu rỗng, filter truy vấn ghép chuỗi và kết nối tái sử dụng không đúng danh tính.

Giả sử thư mục doanh nghiệp có cây entry (DIT) như sau:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan,ou=people,dc=example,dc=org
│   └── uid=minh,ou=people,dc=example,dc=org
└── ou=service
    └── cn=svc-reader,ou=service,dc=example,dc=org
~~~

Mỗi entry có **DN** (Distinguished Name) xác định vị trí trong cây, chẳng hạn `uid=lan,ou=people,dc=example,dc=org`. Các thuộc tính như `uid`, `cn`, `objectClass` và các ràng buộc schema giúp ứng dụng tìm entry, nhưng **tìm được entry không đồng nghĩa đã xác thực được người dùng**. Xác thực cần bước Bind phù hợp.

## 2. Bind là gì ở mức giao thức?

LDAPv3 trao đổi các thông điệp `LDAPMessage` trên một kết nối với directory server. Khi client gửi **BindRequest**, server thử xác thực theo cơ chế được khai báo rồi gửi **BindResponse**.

Các trường quan trọng:

| Thành phần | Vai trò |
| --- | --- |
| `messageID` | Mã tương quan thông điệp trong kết nối; BindResponse dùng cùng `messageID`. |
| `version` | Phiên bản giao thức; trong ví dụ hiện đại là LDAPv3 (giá trị 3). |
| `name` | DN của danh tính yêu cầu Bind; có thể rỗng trong trường hợp ẩn danh hoặc một số cơ chế SASL. |
| `authentication` | Cơ chế xác thực: `simple` (mật khẩu) hoặc `sasl` (cơ chế và dữ liệu xác thực). |
| `resultCode` của BindResponse | Cho biết kết quả, ví dụ `success` (0), `invalidCredentials` (49), `strongAuthRequired` (8). |

Minh họa nội dung logic của thông điệp; đây không phải cú pháp lệnh LDAP có thể chạy trực tiếp:

~~~text
BindRequest {
  messageID: 1,
  version: 3,
  name: "uid=lan,ou=people,dc=example,dc=org",
  authentication: simple("<mật khẩu không được ghi log>")
}

BindResponse {
  messageID: 1,
  resultCode: success (0)
}
~~~

Khi Bind thành công, các thao tác tiếp theo trên **chính kết nối này** (Search, Compare, Add, Modify, Delete, ...) được kiểm tra quyền theo danh tính đã xác thực và chính sách của server. LDAP không cấp một “mã phiên” tự động dùng được trên mọi kết nối khác: mỗi kết nối cần có ngữ cảnh xác thực riêng. Một kết nối mới không mặc nhiên thừa hưởng Bind trước đó.

### Trạng thái danh tính trên một kết nối

| Sự kiện | Trạng thái/ý nghĩa |
| --- | --- |
| Vừa kết nối, chưa xác thực | Thường ở ngữ cảnh ẩn danh; server có thể cấm thao tác không được phép. |
| Bind thành công với DN người dùng | Kết nối được xác thực theo người dùng đó. |
| Bind thành công với tài khoản dịch vụ | Kết nối thực hiện thao tác bằng quyền của tài khoản dịch vụ. |
| Bind thất bại | Trạng thái xác thực sau Bind không được giữ là danh tính đã xác thực trước đó; với LDAPv3, khi xử lý Bind, kết nối chuyển về trạng thái ẩn danh nếu xác thực không thành công. |
| Gửi Bind lần nữa (Rebind) | Client yêu cầu xác lập lại danh tính trên cùng kết nối; phải tuân thủ quy tắc xử lý thao tác đang chờ. |
| Gửi UnbindRequest và đóng kết nối | Kết thúc ngữ cảnh xác thực của kết nối đó. |

**Điểm cần nhớ:** Bind là thao tác trên **kết nối**, không phải thao tác trên từng entry. Đừng dùng một kết nối đang Bind với người A để thực hiện công việc giả định quyền người B, nhất là khi cấu hình pool kết nối.

## 3. Các cách Bind thường gặp

### 3.1. Anonymous Bind

Client có thể yêu cầu truy cập ẩn danh; trong Simple Bind, DN rỗng và mật khẩu rỗng biểu thị trường hợp ẩn danh. Directory server thường hạn chế mạnh quyền của danh tính này. Ứng dụng không nên xem phản hồi `success` của một Bind ẩn danh là bằng chứng người dùng đã đăng nhập.

### 3.2. Simple Bind

Client gửi DN và mật khẩu để server kiểm chứng. Luồng khái quát:

1. Xác định DN cần xác thực, ví dụ từ thuộc tính `uid` sau khi tìm kiếm bằng tài khoản dịch vụ.
2. Gửi BindRequest với DN và mật khẩu tương ứng **qua kênh được bảo vệ bởi TLS**.
3. Chỉ xem đăng nhập thành công khi BindResponse trả về kết quả thành công và danh tính Bind thực sự là danh tính cần xác thực.

**Cạm bẫy mật khẩu rỗng:** Theo mô hình Simple Bind LDAP, DN không rỗng nhưng mật khẩu rỗng có thể được server xử lý như **unauthenticated authentication**: server trả `success` nhưng thực chất cấp quyền ẩn danh. Vì vậy ứng dụng phải từ chối mật khẩu rỗng **trước khi gọi Bind**, và không dựa riêng vào `success` để suy ra người dùng đã xác thực. Cũng cần phân biệt trường hợp DN và mật khẩu đều rỗng (anonymous).

### 3.3. SASL Bind

SASL là khung xác thực có thể dùng các cơ chế như GSSAPI hoặc EXTERNAL, tùy server và hạ tầng. Khác Simple Bind, một số cơ chế SASL cần **nhiều vòng** trao đổi BindRequest/BindResponse; server có thể trả `saslBindInProgress` (14) và dữ liệu thách thức trước khi hoàn tất. SASL không đồng nghĩa mọi cơ chế đều tự mã hóa kết nối: yêu cầu bảo mật kênh và cấu hình cơ chế phải được kiểm tra riêng.

### 3.4. Rebind

Client có thể gửi Bind mới trên kết nối đã dùng để đổi ngữ cảnh xác thực. Khi xử lý Bind mới, LDAPv3 có quy tắc về các thao tác còn đang chạy và trạng thái xác thực tạm thời. Trong ứng dụng thông thường, **đặt một kết nối/context riêng cho mỗi lần xác thực người dùng** dễ kiểm soát hơn việc chủ động Rebind một kết nối đang được chia sẻ.

## 4. Bind và Unbind trong vòng đời kết nối

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Ứng dụng Java
    participant Server as LDAP Server
    App->>Server: Mở kết nối TCP, thiết lập TLS
    App->>Server: BindRequest (DN, cơ chế xác thực)
    Server-->>App: BindResponse (success)
    App->>Server: SearchRequest (base DN, filter)
    Server-->>App: SearchResultEntry / SearchResultDone
    App->>Server: UnbindRequest
    Note over App,Server: Không có UnbindResponse
    Note over App,Server: Kết nối được kết thúc
~~~

**UnbindRequest** là thao tác LDAPv3 có mã `[APPLICATION 2]` và phần dữ liệu `NULL`; nó **không yêu cầu xác thực lại và không có UnbindResponse**. Sau khi gửi Unbind, client không tiếp tục phát lệnh trên kết nối đó; server kết thúc xử lý kết nối. Những thao tác chưa hoàn tất có thể bị hủy hoặc không nhận phản hồi, nên ứng dụng phải hoàn tất công việc cần thiết trước khi đóng.

Cần phân biệt ba khái niệm:

| Hành vi | Ý nghĩa |
| --- | --- |
| LDAP Bind | Xác lập ngữ cảnh xác thực trên kết nối LDAP. |
| LDAP Unbind / đóng kết nối | Kết thúc kết nối và ngữ cảnh xác thực đi kèm. |
| Đăng xuất khỏi ứng dụng web | Hủy phiên HTTP, cookie hoặc token của ứng dụng; cần cơ chế riêng, không được LDAP Unbind thực hiện thay. |

Khi ứng dụng Java gọi `DirContext.close()`, nó giải phóng tài nguyên của context. Tùy thư viện JNDI, nhà cung cấp và cơ chế pooling, thao tác này **không bảo đảm** mỗi lần sẽ tạo ra đúng một gói Unbind trên mạng: kết nối vật lý có thể được đóng hoặc được trả về pool. Ở Spring LDAP, việc mượn và giải phóng context thường do framework quản lý; không cần tự phát UnbindRequest khi dùng `LdapTemplate`.

## 5. Bảo vệ thông tin đăng nhập trước khi Bind

Simple Bind có thể làm lộ mật khẩu nếu truyền qua LDAP plaintext. Vì vậy:

- Ưu tiên **LDAPS** (ví dụ `ldaps://ldap.example.org:636`) hoặc kết nối `ldap://...:389` rồi **StartTLS thành công trước khi Bind**.
- Kiểm tra chuỗi chứng chỉ và tên máy chủ; không vô hiệu hóa xác minh TLS để “chữa” lỗi kết nối.
- Quản lý mật khẩu tài khoản dịch vụ qua secret manager hoặc biến môi trường, không ghi trực tiếp trong mã nguồn hay log.
- Chặn mật khẩu rỗng và không đưa mật khẩu vào filter tìm kiếm, thông báo lỗi, metric tag hoặc trace.
- Cấp cho tài khoản dùng để tìm DN quyền đọc tối thiểu cần thiết; quyền Search của tài khoản dịch vụ khác với quyền của người dùng vừa Bind.
- Giới hạn tài nguyên kết nối và thời gian chờ; không chia sẻ một user-bound context cho các request của người dùng khác.

**Lưu ý:** LDAPS và StartTLS là hai cách bảo vệ kênh truyền. StartTLS phải được thương lượng và xác minh thành công **trước** khi gửi Simple Bind; việc chỉ mở kết nối ở cổng 389 không tự động mã hóa dữ liệu.

## 6. Thực hiện xác thực trong Spring Data LDAP

Trong ứng dụng Spring, `LdapTemplate` và Spring Data LDAP repository thường che giấu các gói LDAP thô. `LdapContextSource` quản lý việc tạo context/kết nối; `LdapTemplate.authenticate(...)` hỗ trợ tìm DN rồi xác thực bằng mật khẩu của người dùng. Ví dụ sử dụng Spring Boot với `spring-boot-starter-data-ldap`.

### 6.1. Cấu hình tài khoản dịch vụ để tìm entry

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=svc-reader,ou=service,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

Giá trị `spring.ldap.username`/`password` là danh tính **tài khoản dịch vụ** để thực hiện các truy vấn cần thiết, không phải tài khoản của người dùng đang đăng nhập. Hãy cấp quyền đọc vừa đủ để tìm DN và chạy ứng dụng với truststore/cấu hình TLS hợp lệ.

### 6.2. Tìm DN và xác thực bằng mật khẩu người dùng

~~~java
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.stereotype.Service;

@Service
public class LdapLoginService {
    private final LdapTemplate ldapTemplate;

    public LdapLoginService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public boolean verifyCredentials(String uid, String password) {
        // Ngăn trường hợp Simple Bind với mật khẩu rỗng.
        if (uid == null || uid.isBlank()
                || password == null || password.isEmpty()) {
            return false;
        }

        // ou=people được hiểu tương đối với base dc=example,dc=org.
        LdapQuery userQuery = LdapQueryBuilder.query()
                .base("ou=people")
                .where("uid").is(uid);

        return ldapTemplate.authenticate(userQuery, password);
    }
}
~~~

Luồng điển hình của cách viết trên:

1. `LdapTemplate` dùng ngữ cảnh được cấu hình để tìm entry có `uid` tương ứng trong `ou=people`.
2. Sau khi xác định DN, framework thử xác thực bằng mật khẩu người dùng (Bind thích hợp).
3. Trả kết quả xác thực cho ứng dụng và giải phóng context theo cơ chế quản lý kết nối của Spring LDAP.
4. Ứng dụng tự quyết định có tạo phiên HTTP/token hay không; các phiên ứng dụng này có vòng đời riêng với kết nối LDAP.

`LdapQueryBuilder.where("uid").is(uid)` giúp tạo filter LDAP và xử lý escaping giá trị đầu vào. Tránh nối chuỗi thủ công như `"(uid=" + uid + ")"` vì ký tự đặc biệt do người dùng nhập có thể làm thay đổi ý nghĩa filter. Cần bảo đảm thuộc tính định danh có chính sách duy nhất trong vùng tìm kiếm; khi có nhiều entry cùng khớp, ứng dụng phải xác định cách xử lý thay vì tùy tiện chọn một người.

**Giới hạn của ví dụ:** Phương thức trên minh họa xác thực LDAP, chưa thay thế toàn bộ chính sách đăng nhập của một ứng dụng (rate limit, MFA nếu yêu cầu, ánh xạ quyền, logging an toàn, phiên HTTP và xử lý lỗi hạ tầng). Trong thực tế, cần phân biệt lỗi sai thông tin đăng nhập với lỗi directory/TLS không sẵn sàng; không diễn giải tất cả ngoại lệ thành “sai mật khẩu”.

### 6.3. Khi dùng context trực tiếp, phải đóng context

Có trường hợp cần tự lấy context để thao tác với quyền của DN cụ thể:

~~~java
import javax.naming.NamingException;
import javax.naming.directory.DirContext;
import org.springframework.ldap.core.support.LdapContextSource;

public class UserContextExample {
    private final LdapContextSource contextSource;

    public UserContextExample(LdapContextSource contextSource) {
        this.contextSource = contextSource;
    }

    public void runAsUser(String userDn, String password) throws NamingException {
        if (userDn == null || userDn.isBlank()
                || password == null || password.isEmpty()) {
            throw new IllegalArgumentException("Thiếu DN hoặc mật khẩu");
        }

        DirContext context = contextSource.getContext(userDn, password);
        try {
            // Thao tác JNDI tại đây chạy trong context đã được Bind.
            // Chỉ thực hiện thao tác nằm trong quyền của userDn.
        } finally {
            context.close();
        }
    }
}
~~~

`getContext(userDn, password)` thử tạo context được xác thực bằng DN và mật khẩu đã cung cấp; nếu xác thực không thành công, thao tác có thể phát sinh ngoại lệ. Khối `finally` giúp đóng context dù phần thao tác phát sinh lỗi. Trong Spring Data LDAP thông thường, ưu tiên API của `LdapTemplate`/repository để framework xử lý vòng đời tài nguyên và các ngoại lệ nhất quán.

## 7. Những sai lầm thường gặp

| Tình huống | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Simple Bind qua `ldap://` không có StartTLS | Mật khẩu có thể đi qua mạng dưới dạng không được mã hóa. | Dùng LDAPS hoặc StartTLS đã xác minh thành công trước Bind. |
| Gửi mật khẩu rỗng rồi tin vào `success` | Có thể chỉ được xác thực ẩn danh. | Từ chối mật khẩu rỗng tại tầng ứng dụng. |
| Coi Bind tài khoản dịch vụ là xác thực người dùng | Người dùng chưa chứng minh được mật khẩu của chính họ. | Tìm DN bằng service account rồi Bind kiểm chứng thông tin người dùng. |
| Nối chuỗi trực tiếp tạo LDAP filter | Rủi ro LDAP filter injection hoặc truy vấn sai. | Dùng `LdapQueryBuilder`/API escaping an toàn. |
| Dùng chung context đã Bind người dùng A cho người B | Dễ kiểm tra ACL dưới danh tính sai. | Dùng vòng đời context riêng, cấu hình pool đúng và giải phóng tài nguyên. |
| Đồng nhất `DirContext.close()` với “đăng xuất ứng dụng” | Cookie/session HTTP vẫn có thể hoạt động. | Xử lý logout của tầng web riêng. |
| Gửi Unbind giữa thao tác chưa hoàn tất | Kết quả đang chờ có thể mất. | Hoàn thành/thu hồi thao tác có chủ đích rồi đóng kết nối. |

## 8. Kiểm thử luồng xác thực với directory

Nên dùng một LDAP test server có schema và dữ liệu giả lập, với entry thử nghiệm thuộc `ou=people`; không sử dụng mật khẩu thật trong dữ liệu kiểm thử. Ma trận xác minh tối thiểu:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| `uid` tồn tại, mật khẩu đúng, TLS hợp lệ | Bind thành công; ứng dụng xác nhận danh tính đúng. |
| `uid` tồn tại, mật khẩu sai | Bind không thành công, thường có `invalidCredentials` (49); không tạo phiên đăng nhập. |
| Mật khẩu rỗng | Ứng dụng trả `false` trước khi gửi Bind người dùng. |
| `uid` không tồn tại | Không xác thực; không lộ chi tiết giúp dò tài khoản ra bên ngoài. |
| Tài khoản dịch vụ thiếu quyền tìm DN | Lỗi truy cập/directory được ghi nhận riêng, không gắn nhãn nhầm là “mật khẩu người dùng sai”. |
| TLS hoặc chứng chỉ lỗi | Không gửi Simple Bind chứa mật khẩu trên kết nối plaintext thay thế. |
| Nhiều người đăng nhập liên tiếp | Không rò rỉ danh tính/quyền giữa các context; tài nguyên được giải phóng sau thao tác. |
| Đóng context sau thao tác | Không dùng lại context đã đóng; nếu cần, quan sát log/server trace để hiểu pool có tạo UnbindRequest hay không. |

Đối với bài lab ở mức giao thức, có thể bật trace LDAP trên **test server** để thấy thứ tự `BindRequest → BindResponse → SearchRequest → ... → UnbindRequest`. Phải che mật khẩu và dữ liệu nhạy cảm trong trace. Nếu sử dụng pooling, thay đổi một tham số cấu hình mỗi lần để nhận diện sự khác nhau giữa “đóng context” và “đóng kết nối mạng”.

## 9. Tự kiểm tra kiến thức

1. Hai request LDAP dùng cùng DN nhưng trên hai kết nối khác nhau: Bind thành công ở kết nối thứ nhất có tự xác thực kết nối thứ hai không? Vì sao?
2. Vì sao trường hợp DN không rỗng, mật khẩu rỗng cần bị từ chối ngay cả khi có server trả BindResponse thành công?
3. Trong `LdapTemplate.authenticate(...)`, tài khoản dịch vụ thực hiện vai trò gì và mật khẩu người dùng dùng ở bước nào?
4. Sau khi gửi UnbindRequest, client nên chờ loại phản hồi nào? Vì sao?
5. `DirContext.close()` có luôn phát ra một gói UnbindRequest khi bật connection pooling không?
6. Một người dùng “đăng xuất” khỏi website nhưng pool LDAP vẫn còn kết nối hoạt động. Điều này nhất thiết là lỗi không, và cần xóa trạng thái nào để đăng xuất khỏi website?

**Ghi nhớ:** Bind xác thực **kết nối LDAP**, Unbind kết thúc **kết nối LDAP**, còn trạng thái đăng nhập của ứng dụng phải được quản lý **riêng**. Với Spring Data LDAP, hãy dùng `LdapTemplate` để thực hiện các thao tác phổ biến, kiểm soát đầu vào và bảo vệ kết nối bằng TLS.

### Tài liệu tham khảo

- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511) — phần Bind Operation và Unbind Operation.
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513) — Simple Bind, unauthenticated authentication và các yêu cầu bảo mật.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/) — `LdapTemplate`, `ContextSource` và API xác thực.
