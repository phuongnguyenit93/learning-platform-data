# 18.6. Kerberos, KDC, service principal, ticket, keytab và quan hệ với Krb5LoginModule

## 1. Mục tiêu và bối cảnh

Sau bài này, bạn cần giải thích được:

- Kerberos V5 xác thực **ai đang yêu cầu dịch vụ nào** bằng vé (ticket) và khóa đối xứng, thay vì gửi mật khẩu của người dùng tới từng dịch vụ.
- KDC, realm, client principal, service principal, TGT, service ticket, session key và keytab có trách nhiệm khác nhau.
- Luồng AS → TGS → application service, bao gồm bước chứng minh client sở hữu session key.
- Khi nào ứng dụng Java dùng ticket cache, khi nào service cần keytab, và cách JAAS Krb5LoginModule đưa thông tin vào Subject.
- Vì sao đăng nhập JAAS thành công chưa đồng nghĩa HTTP/SASL/GSS-API đã xác thực với dịch vụ đích.

Phạm vi là **Kerberos trong Java**, tập trung vào quan hệ giữa hạ tầng Kerberos và Krb5LoginModule. Ví dụ hostname, realm và đường dẫn dưới đây chỉ minh họa; chúng không đại diện cho một KDC thực sự.

## 2. Bức tranh tổng thể: danh tính, realm và KDC

**Principal** là tên danh tính trong hệ Kerberos. Các dạng điển hình:

~~~text
alice@EXAMPLE.COM                         # người dùng (client principal)
HTTP/api.example.com@EXAMPLE.COM          # dịch vụ HTTP (service principal)
host/server.example.com@EXAMPLE.COM       # dịch vụ host
krbtgt/EXAMPLE.COM@EXAMPLE.COM            # dịch vụ cấp vé của realm
~~~

- **Realm**: miền quản lý danh tính và khóa Kerberos; thường viết hoa theo quy ước, ví dụ EXAMPLE.COM. Realm không tự động đồng nghĩa DNS domain, dù nhiều hệ thống cố tình đặt tên giống nhau.
- **Client principal**: danh tính muốn sử dụng dịch vụ, ví dụ alice@EXAMPLE.COM.
- **Service principal**: danh tính server được client yêu cầu xác thực, thường có dạng service/hostname@REALM. Với HTTP Negotiate thường gặp HTTP/hostname@REALM.
- **KDC (Key Distribution Center)**: dịch vụ tin cậy phát hành vé, gồm logic Authentication Service (AS) và Ticket-Granting Service (TGS). KDC biết các principal và khóa thích hợp; với Active Directory, domain controller thường đảm nhiệm vai trò KDC.
- **Application server/acceptor**: dịch vụ nhận vé do client gửi, kiểm tra vé bằng khóa riêng của service principal.

Không phải mỗi bước đều gửi yêu cầu tới KDC. Khi client đã có TGT và service ticket còn hiệu lực, có thể tái sử dụng vé; server không cần liên hệ KDC cho từng request xác thực thông thường.

## 3. Luồng Kerberos V5 từ đăng nhập tới gọi dịch vụ

Giả sử Alice muốn gọi HTTP/api.example.com@EXAMPLE.COM:

~~~text
Alice / Java client                    KDC (AS + TGS)              HTTP service
       |                                      |                          |
       |--- AS-REQ (xin TGT) ---------------->|                          |
       |<-- AS-REP (TGT + khóa phiên) --------|                          |
       |                                      |                          |
       |--- TGS-REQ (TGT, xin vé cho HTTP) -->|                          |
       |<-- TGS-REP (service ticket + key) ---|                          |
       |                                      |                          |
       |--- AP-REQ (service ticket + authenticator) ------------------->|
       |<-- AP-REP (nếu yêu cầu xác thực hai chiều) --------------------|
       |<================= giao thức ứng dụng được bảo vệ =============>|
~~~

**Bước 1 — AS exchange:** client chứng minh danh tính với AS, thường bằng cơ chế pre-authentication liên quan tới khóa của principal hoặc một phương thức được KDC hỗ trợ. KDC trả về **TGT** (Ticket-Granting Ticket) cùng thông tin khóa phiên dành cho client. TGT chứa phần được mã hóa cho TGS, nên client không thể tự ý sửa nó.

**Bước 2 — TGS exchange:** client dùng TGT để xin một **service ticket** đúng cho HTTP/api.example.com@EXAMPLE.COM. TGS cấp service ticket có phần được mã hóa bằng khóa dài hạn của service principal và cung cấp session key tương ứng cho client theo cách được bảo vệ.

**Bước 3 — AP exchange:** client gửi service ticket **cùng authenticator mới** tới HTTP server. Server dùng khóa của chính service principal (thường lấy từ keytab) để giải mã phần ticket liên quan; sau đó dùng session key để kiểm tra authenticator, thời gian và các điều kiện khác. Một ticket đứng riêng chưa chứng minh người gửi sở hữu session key.

**Bước 4 — xác thực hai chiều (tùy chọn):** service có thể phản hồi AP-REP để client xác thực phía server. Sau khi cơ chế xác thực thiết lập xong, giao thức ứng dụng quyết định cách bảo vệ tính toàn vẹn/bảo mật của thông điệp: GSS-API có khả năng wrap/unwrap, còn HTTP có thể sử dụng TLS. Kerberos không mặc nhiên mã hóa mọi byte của HTTP payload.

**Lưu ý:** tên thông điệp trên mô tả giao thức. Ứng dụng dùng GSS-API/SASL thường không tự đóng gói thủ công AS-REQ, TGS-REQ hay AP-REQ.

## 4. Phân biệt TGT, service ticket, session key và keytab

| Thành phần | Nơi sử dụng chính | Ý nghĩa | Điều không nên nhầm |
| --- | --- | --- | --- |
| TGT | Client ↔ TGS | Cho phép xin vé tới những dịch vụ khác trong thời hạn chính sách | Không phải vé để trình trực tiếp cho HTTP service thông thường |
| Service ticket | Client → đúng service | Bằng chứng do KDC cấp cho service principal cụ thể | Không phải mật khẩu và không dùng tùy ý cho service khác |
| Session key | Client và bên kiểm tra ticket | Dùng chứng minh sở hữu vé, xác thực thông điệp và có thể bảo vệ phiên | Không phải khóa dài hạn trong keytab |
| Keytab | Thường tại server, đôi khi client không tương tác | Tệp chứa khóa dài hạn và metadata principal/KVNO/enctype để Kerberos dùng | Không chứa TGT hoặc danh sách service ticket |
| Ticket cache | Môi trường client/tiến trình | Lưu credential như TGT, service ticket để tái sử dụng | Không phải keytab; xóa cache không xoay khóa service |

Một **ticket** có thời hạn và thuộc tính như client, service, thời điểm hiệu lực và các cờ theo chính sách KDC. Đối với service ticket, phần ticket dành cho server được mã hóa để **service** kiểm tra. Client nhận được session key phù hợp nhưng không nhận khóa dài hạn của service.

**KVNO (Key Version Number)** giúp chọn phiên bản khóa đúng khi khóa của principal được đổi; **enctype** chỉ thuật toán mã hóa/kiểu khóa. Khi KDC cấp ticket theo một phiên bản khóa nhưng server chỉ có keytab cũ hoặc không hỗ trợ enctype tương thích, xác thực có thể thất bại. Không nên kết luận “có principal trong keytab là đủ” mà bỏ qua KVNO và enctype.

## 5. Service principal, hostname và ánh xạ tới keytab

Với dịch vụ ví dụ, ba phía phải thống nhất danh tính:

~~~text
Tên client yêu cầu:  HTTP/api.example.com@EXAMPLE.COM
Principal KDC biết:  HTTP/api.example.com@EXAMPLE.COM
Khóa server có:      keytab chứa khóa của HTTP/api.example.com@EXAMPLE.COM
~~~

Nếu client yêu cầu HTTP/alias.example.com nhưng KDC không có SPN đó, có thể không cấp được service ticket. Nếu KDC có principal nhưng server đọc keytab của principal hoặc phiên bản khóa khác, server không giải mã được ticket. DNS alias, reverse DNS, hostname canonicalization, load balancer và ánh xạ SPN của Active Directory cần được thiết kế nhất quán.

Một service principal có thể được đăng ký với tài khoản dịch vụ hoặc service account trong KDC/AD. Nó là **định danh Kerberos**; tên service principal không phải chính nó là user/password, URL đầy đủ hay chứng chỉ TLS.

**Nhiều instance:** các instance thực sự cùng phục vụ một SPN có thể cần quyền truy cập cùng tập khóa thích hợp, nhưng việc sao chép keytab phải được quản lý như phân phối bí mật. Đừng cho nhiều dịch vụ độc lập dùng chung principal chỉ vì tiện cấu hình.

## 6. Keytab hoạt động như thế nào?

Keytab chứa khóa bí mật của một hoặc nhiều principal, thường kèm KVNO và enctype. Server không cần nhúng mật khẩu vào mã Java; khi nhận AP-REQ, GSS/Kerberos có thể dùng khóa từ keytab để chấp nhận ticket.

Ví dụ quy trình quản trị ở môi trường có MIT Kerberos hoặc công cụ tương đương:

~~~bash
# Chạy trên host đã cấu hình Kerberos; tên file chỉ minh họa.
klist -k -e /etc/security/keytabs/http-api.keytab

# Kiểm tra vé hiện có của tài khoản client:
klist

# Client có quyền và TGT hợp lệ có thể xin service ticket:
kvno HTTP/api.example.com@EXAMPLE.COM
~~~

- Lệnh klist -k -e hiển thị danh tính, KVNO, enctype trong keytab; nó **không** kiểm tra rằng KDC hiện tại đã có đúng khóa.
- Lệnh kvno cần môi trường Kerberos thực, phân giải realm/KDC đúng và quyền lấy vé.
- Công cụ/tùy chọn cụ thể phụ thuộc MIT Kerberos, Heimdal, Windows hoặc hệ quản trị KDC.

Trong triển khai, chỉ tài khoản hệ điều hành chạy service cần đọc keytab; áp dụng permission tối thiểu (ví dụ 0600 trên Unix khi phù hợp), lưu bằng secret management và không commit vào Git, log hoặc gửi qua chat. Khi rotate key, đồng bộ KDC, KVNO và các instance; lập kế hoạch chồng lấp khóa trong thời gian ticket cũ còn hiệu lực theo khả năng KDC/keytab. Nếu keytab lộ, kẻ tấn công có thể giả danh service trong phạm vi khóa bị lộ.

## 7. Krb5LoginModule nằm ở đâu trong kiến trúc Java?

Trong Java, có ba lớp trách nhiệm cần tách bạch:

1. **JAAS LoginContext** kích hoạt các LoginModule theo tên cấu hình; javax.security.auth.login.LoginContext thực hiện login/commit/logout.
2. **com.sun.security.auth.module.Krb5LoginModule** làm việc với Kerberos (ticket cache, keytab, KDC hoặc callback tùy cấu hình), rồi đưa principal/credential vào javax.security.auth.Subject.
3. **GSS-API (org.ietf.jgss) hoặc SASL** dùng credential phù hợp để thiết lập phiên xác thực với dịch vụ thực tế. Ví dụ HTTP Negotiate/SPNEGO dùng GSS ở lớp giao thức HTTP; SASL GSSAPI dùng trong những giao thức có hỗ trợ SASL.

Krb5LoginModule **không phải KDC, không phát hành vé và không tự cài đặt HTTP Negotiate**. Nó là cầu nối giữa cơ chế Kerberos và môi trường JAAS của Java.

Khi login/commit thành công, Subject có thể có:

- **KerberosPrincipal** trong tập principals.
- **KerberosTicket** trong private credentials khi đăng nhập với vai trò initiator và có TGT.
- **KeyTab hoặc KerberosKey** trong private credentials nếu tùy chọn storeKey và nguồn khóa thích hợp được dùng.
- Những credential khác tùy cấu hình login và provider.

Chú ý private credentials là dữ liệu nhạy cảm. Không in ra nội dung Subject một cách tùy tiện, không serialize credential vào log hoặc API response.

## 8. Client (initiator) và server (acceptor) cần gì?

| Vai trò | Nguồn thông dụng | isInitiator | Mục tiêu |
| --- | --- | --- | --- |
| Người dùng/client đã kinit | Ticket cache có TGT | true (mặc định) | Có credential để xin service ticket và khởi tạo GSS context |
| Client daemon xác thực không tương tác | Keytab riêng và principal của daemon | true | Dùng khóa để lấy TGT từ KDC rồi gọi service |
| Server chỉ nhận Kerberos | Keytab của service principal, storeKey=true | false | Nạp khóa cho GSS acceptor; không cần lấy TGT chỉ để chấp nhận AP-REQ |

**TGT không thay thế keytab** trên server. Một HTTP acceptor thường cần service key để mở service ticket; việc server cũng chạy kinit không tự giải quyết được thiếu keytab hoặc SPN sai.

## 9. Tùy chọn quan trọng của Krb5LoginModule

| Tùy chọn | Ý nghĩa và điều kiện |
| --- | --- |
| principal | Danh tính muốn dùng; với acceptor nên chọn SPN cụ thể. Dấu * chỉ hợp lệ cho isInitiator=false và mở phạm vi chấp nhận theo các khóa trong keytab, cần cân nhắc kỹ |
| isInitiator | true để lấy credential khởi tạo giao tiếp; false cho acceptor-only, không thực hiện AS exchange để lấy TGT |
| useTicketCache | true để thử lấy TGT từ ticket cache (phù hợp client đã kinit) |
| ticketCache | Đường dẫn cache tùy chọn; chỉ dùng khi useTicketCache=true |
| useKeyTab | true để dùng khóa trong keytab; nếu chỉ khai báo keyTab mà thiếu useKeyTab=true là cấu hình không hợp lệ |
| keyTab | Đường dẫn keytab; nên nêu rõ và quản lý quyền file |
| storeKey | true để lưu keytab/khóa vào Subject private credentials, quan trọng cho acceptor |
| doNotPrompt | true để không hỏi mật khẩu tương tác; thất bại rõ ràng nếu không lấy được credential |
| renewTGT | Chính sách thử gia hạn TGT; chỉ hợp lệ cùng useTicketCache=true, không thay thế quy trình quản lý hạn vé |
| refreshKrb5Config | Cho phép nạp lại cấu hình Kerberos khi login (tùy yêu cầu vận hành) |
| debug | Thông tin chẩn đoán LoginModule; chỉ bật có kiểm soát và tắt sau khi xử lý |

Các ràng buộc dễ sai: **doNotPrompt=true** nhưng không có cache/keytab/nguồn credential hợp lệ; **storeKey=true** với chỉ ticket cache và không có nguồn khóa; **keyTab** nhưng thiếu **useKeyTab=true**; **renewTGT=true** nhưng thiếu **useTicketCache=true**. Cơ chế có thể thử cache rồi keytab rồi các nguồn khác tùy cấu hình; không nên cho phép nhắc password trong daemon production.

## 10. Cấu hình Kerberos và JAAS mẫu

Ví dụ krb5.conf: host KDC và realm phải được thay bằng thông tin do quản trị viên cung cấp.

~~~ini
[libdefaults]
    default_realm = EXAMPLE.COM
    dns_lookup_kdc = false

[realms]
    EXAMPLE.COM = {
        kdc = kdc.example.com
    }
~~~

Ví dụ jaas.conf gồm **hai entry riêng**, dùng tùy theo process:

~~~text
KrbClient {
    com.sun.security.auth.module.Krb5LoginModule required
    useTicketCache=true
    doNotPrompt=true
    isInitiator=true
    debug=false;
};

KrbAcceptor {
    com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/etc/security/keytabs/http-api.keytab"
    principal="HTTP/api.example.com@EXAMPLE.COM"
    storeKey=true
    doNotPrompt=true
    isInitiator=false
    debug=false;
};
~~~

**KrbClient**: kỳ vọng trước đó đã có TGT hợp lệ trong cache mà JVM đọc được. Login thất bại nếu không có credential phù hợp; sample cố ý không hỏi password.

**KrbAcceptor**: nạp khóa của HTTP/api.example.com để ứng dụng có thể chấp nhận GSS token tới principal đó. Nó không tự tạo HTTP endpoint hoặc tự xử lý header Authorization; vẫn cần framework/handler hỗ trợ Negotiate hay giao thức tích hợp GSS.

Tùy runtime, đường dẫn ticket cache từ công cụ hệ điều hành và đường dẫn Java sử dụng có thể khác nhau. Trên Windows/AD, việc lấy credential có thể theo cơ chế hệ điều hành và JDK; hãy kiểm tra thực tế thay vì mặc định KRB5CCNAME hoạt động như mọi hệ Unix.

**Không đặt mật khẩu vào jaas.conf**, không lưu keytab trong source tree, không dùng account domain administrator để chạy service.

## 11. Ví dụ Java 17+: phân tích service principal mà không cần KDC

Tệp độc lập **PrincipalDemo.java**:

~~~java
import javax.security.auth.kerberos.KerberosPrincipal;

public class PrincipalDemo {
    public static void main(String[] args) {
        KerberosPrincipal principal = new KerberosPrincipal(
                "HTTP/api.example.com@EXAMPLE.COM",
                KerberosPrincipal.KRB_NT_SRV_HST);

        System.out.println(principal.getName());
        System.out.println(principal.getRealm());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PrincipalDemo.java
java PrincipalDemo
~~~

Stdout:

~~~text
HTTP/api.example.com@EXAMPLE.COM
EXAMPLE.COM
~~~

Constructor trên biểu diễn **tên danh tính và name type**, chưa xác thực với KDC, chưa mở keytab và chưa tạo ticket. Khởi tạo KerberosPrincipal thành công **không chứng minh** SPN đã được đăng ký trong KDC.

## 12. Ví dụ Java 17+: đăng nhập bằng JAAS và kiểm tra Subject

Tệp **JaasLoginDemo.java** (cần krb5.conf, jaas.conf và ticket cache thực mới login thành công):

~~~java
import javax.security.auth.Subject;
import javax.security.auth.login.LoginContext;
import java.security.PrivilegedAction;

public class JaasLoginDemo {
    public static void main(String[] args) throws Exception {
        LoginContext context = new LoginContext("KrbClient");
        context.login();

        try {
            Subject subject = context.getSubject();

            subject.getPrincipals().forEach(principal ->
                    System.out.println("Principal: " + principal.getName()));

            Subject.doAs(subject, (PrivilegedAction<Void>) () -> {
                System.out.println("Run using authenticated Subject");
                return null;
            });
        } finally {
            context.logout();
        }
    }
}
~~~

Biên dịch:

~~~bash
javac JaasLoginDemo.java
~~~

Cách chạy tham khảo (trong máy đã cấu hình Kerberos):

~~~bash
java -Djava.security.auth.login.config=jaas.conf -Djava.security.krb5.conf=krb5.conf JaasLoginDemo
~~~

Nếu LoginContext.login() thất bại sẽ phát sinh LoginException (được khai báo qua throws Exception trong ví dụ); thường do thiếu TGT, cache không đọc được, lệch realm hoặc lỗi cấu hình. **Không có một stdout cố định cho ví dụ này**: principal phụ thuộc credential của môi trường, và thiếu KDC/cache hợp lệ sẽ không đi tới các lệnh in.

Subject.doAs chạy đoạn code dưới danh tính Subject; API tích hợp GSS có thể tra cứu credential liên quan. Mẫu chỉ in tên principal để minh họa, **chưa giao tiếp hoặc chứng thực với service HTTP**. Với môi trường Java đời mới hơn, cần kiểm tra hướng dẫn tương thích của phiên bản JDK cho API Subject và cơ chế gắn Subject vào ngữ cảnh thực thi.

## 13. Từ Subject tới GSS-API, HTTP Negotiate và SASL GSSAPI

Để thực sự dùng service ticket, ứng dụng cần cơ chế trao đổi token với server:

~~~text
LoginContext("KrbClient") → Subject có credential
        ↓
GSSManager / GSSContext (initiator)
        ↓ tạo GSS token cho service "HTTP@api.example.com"
HTTP client gửi Authorization: Negotiate <base64-token>
        ↓
HTTP server / GSSContext (acceptor) dùng keytab service
        ↓
Server xác thực principal; framework ánh xạ sang user/quyền ứng dụng
~~~

Tên host-based dạng **HTTP@api.example.com** trong GSS-API là một biểu diễn khác với service principal Kerberos **HTTP/api.example.com@EXAMPLE.COM**. GSS/Kerberos provider giải quyết ánh xạ thích hợp theo realm và cấu hình; không nên tự ghép chuỗi tùy tiện, nhất là khi có alias.

Một GSS security context có thể cần **nhiều vòng token** giữa client và server; đừng giả định đúng một AP-REQ/token cho mọi cơ chế (đặc biệt khi dùng SPNEGO). Sau context establishment, GSS có API bảo vệ thông điệp, còn việc ứng dụng có dùng chúng hay chỉ dựa trên TLS là quyết định của giao thức/triển khai.

Với **SASL GSSAPI**, một giao thức như LDAP hoặc messaging có thể đưa việc xác thực vào quá trình SASL negotiation. Thư viện/protocol driver điều khiển token; Krb5LoginModule vẫn phục vụ chuẩn bị credential. Không suy từ việc cấu hình JAAS thành công rằng LDAP/HTTP server đã cho phép thao tác: **authentication** và **authorization** là hai giai đoạn riêng.

## 14. Quy trình triển khai và kiểm tra theo thứ tự

1. **Xác định principal và realm**: chính xác client principal, service principal, hostname/SPN mà client yêu cầu, realm và đường đi tới KDC.
2. **Chuẩn bị KDC**: tài khoản/principal phải tồn tại; cấp khóa hoặc keytab bằng quy trình quản trị, theo chính sách enctype và KVNO.
3. **Chuẩn bị máy service**: đặt keytab dưới đường dẫn riêng, hạn chế quyền; xác minh nó có đúng SPN và các khóa hiện hành.
4. **Chuẩn bị máy client**: lấy TGT qua cơ chế tổ chức cho phép (ví dụ kinit) và kiểm tra bằng klist; không cần copy keytab của server sang client.
5. **Nạp cấu hình vào JVM**: realm, KDC, JAAS login entry đúng vai trò; xử lý môi trường ticket cache đúng với user chạy JVM.
6. **Login bằng JAAS**: kiểm tra principal trong Subject, không log private credentials.
7. **Thực hiện GSS/SASL/HTTP exchange**: client xin service ticket rồi gửi token; server dùng service key để nhận token.
8. **Xác thực quyền**: từ principal đã xác thực, ứng dụng ánh xạ sang role/ACL theo chính sách riêng.
9. **Kiểm tra gia hạn/rotation**: ticket hết hạn cần cơ chế tái lấy credential; keytab và KVNO phải phối hợp khi xoay khóa.

Các lệnh chẩn đoán tham khảo, chỉ chạy trong môi trường Kerberos được cấp quyền:

~~~bash
kinit alice@EXAMPLE.COM
klist
kvno HTTP/api.example.com@EXAMPLE.COM
klist -k -e /etc/security/keytabs/http-api.keytab
~~~

Trước khi debug Java, hãy xác định bước lỗi: **AS không cấp TGT**, **TGS không cấp service ticket**, hay **acceptor không giải mã/xác nhận AP-REQ**. Ba lỗi này cần ba hướng sửa khác nhau.

## 15. Các lỗi thường gặp và cách suy luận

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra trước |
| --- | --- | --- |
| Không tìm thấy KDC / realm | krb5.conf hoặc DNS/KDC routing sai | Realm, host, cổng, khả năng kết nối |
| Client không có credential hợp lệ | Cache trống/hết hạn hoặc JVM đọc sai cache | klist dưới đúng user chạy ứng dụng; useTicketCache |
| Server not found in Kerberos database | SPN/realm client yêu cầu không được KDC nhận diện | Exact service principal, alias, realm, đăng ký SPN |
| KRB_AP_ERR_MODIFIED hoặc lỗi integrity khi accept | Server không có đúng service key, KVNO/enctype lệch, SPN trỏ sai instance | Ticket service principal, keytab, KVNO/enctype, hostname |
| Clock skew too great / ticket expired | Lệch giờ hoặc hạn vé | Đồng bộ NTP, thời gian KDC/client/server, ticket lifetime |
| Cannot find key of appropriate type | Thiếu khóa/enctype tương thích | Enctype keytab và chính sách KDC/JDK |
| JAAS LoginException doNotPrompt | Không có nguồn credential cho login mode đã chọn | Cấu hình useTicketCache/useKeyTab, principal, quyền file |
| JAAS login OK nhưng HTTP 401 / SASL fail | GSS negotiation, SPN, server key, proxy hoặc authorization chưa đúng | Token exchange, service principal, acceptor, user mapping |

Thông báo lỗi là dấu hiệu để khoanh vùng, không phải kết luận nguyên nhân duy nhất. Ví dụ KRB_AP_ERR_MODIFIED có thể xuất hiện khi keytab cũ **hoặc** client lấy ticket cho SPN của instance khác.

Để bật chẩn đoán JVM khi thật sự cần:

~~~bash
java -Dsun.security.krb5.debug=true -Djava.security.auth.login.config=jaas.conf -Djava.security.krb5.conf=krb5.conf JaasLoginDemo
~~~

Có thể bật debug=true cho Krb5LoginModule ở môi trường kiểm thử. **Không để debug Kerberos thường trực ở production**; bảo vệ log vì có thể lộ tên principal, hostname, cấu hình và thông tin nhạy cảm vận hành.

## 16. Những hiểu lầm nguy hiểm

- **“TGT và service ticket giống nhau.”** Sai. TGT dùng xin ticket ở TGS; service ticket dành cho một service cụ thể.
- **“Có keytab là chắc chắn Kerberos login sẽ thành công.”** Sai. Principal, KVNO, enctype, realm, quyền file và mode của LoginModule phải phù hợp. Client initiator cần một quá trình lấy credential, có thể liên quan KDC.
- **“Krb5LoginModule tự xác thực mọi HTTP request.”** Sai. Cần GSS/SPNEGO/HTTP integration cùng trao đổi token và kiểm tra server.
- **“Service có TGT thì không cần keytab.”** Sai với mô hình acceptor dựa trên khóa service để mở ticket được KDC cấp.
- **“Kerberos thành công nghĩa là user có mọi quyền.”** Sai. Kerberos xác thực identity, còn tài nguyên/quyền do ứng dụng hay hệ thống ủy quyền quyết định.
- **“Đã có Kerberos thì không cần TLS.”** Sai. HTTPS/TLS và Kerberos xử lý các khía cạnh an ninh khác nhau; cần xét bảo vệ transport, channel binding và threat model của giao thức cụ thể.
- **“Ticket cache và keytab đều là nơi lưu mật khẩu.”** Sai. Cache chứa ticket/credential phiên; keytab chứa khóa dài hạn, cả hai đều phải được bảo vệ.

## 17. Bài tập tự kiểm tra

**Tình huống A:** client có TGT hợp lệ nhưng khi gọi API nhận “Server not found in Kerberos database”. Bạn kiểm tra service principal client yêu cầu và bản ghi SPN/realm tại KDC trước; thay keytab ở server chưa giải quyết việc TGS không cấp được ticket.

**Tình huống B:** client lấy service ticket thành công, server trả KRB_AP_ERR_MODIFIED sau lần rotate key. Kiểm tra KVNO/enctype và liệu mọi instance đã nhận keytab mới, đồng thời xác minh client gửi ticket cho đúng SPN.

**Tình huống C:** một Java service chỉ cần nhận HTTP Negotiate token. Entry JAAS nên là acceptor-only (isInitiator=false), useKeyTab=true, storeKey=true, principal chính xác; không cấu hình kinit/TGT như điều kiện bắt buộc chỉ để nhận vé.

**Tình huống D:** LoginContext.login() trả thành công nhưng endpoint vẫn 403. Phân biệt hai câu hỏi: token GSS đã được xác thực và ánh xạ ra principal chưa? Principal đó có quyền gọi endpoint theo authorization policy không?

Bạn hoàn thành bài khi tự vẽ lại đường đi **AS → TGS → AP**, chỉ ra khóa nào dùng ở mỗi bước, giải thích credential nào được lưu trong **Subject** cho initiator/acceptor và xác định được nơi cần kiểm tra khi client có TGT nhưng vẫn không gọi được service.

## 18. Tài liệu kỹ thuật để đối chiếu

- Kerberos V5, RFC 4120: https://www.rfc-editor.org/rfc/rfc4120
- Java SE 21 Krb5LoginModule API (tùy chọn, ràng buộc và ví dụ): https://docs.oracle.com/en/java/javase/21/docs/api/jdk.security.auth/com/sun/security/auth/module/Krb5LoginModule.html
- Oracle Java SE 17 JAAS Login và Java GSS-API: https://docs.oracle.com/en/java/javase/17/security/use-jaas-login-utility-and-java-gss-api-secure-message-exchanges.html

Các đường dẫn trên mô tả chuẩn và JDK; ví dụ EXAMPLE.COM cần được thay bằng môi trường Kerberos hợp lệ để kiểm thử tương tác thật.
