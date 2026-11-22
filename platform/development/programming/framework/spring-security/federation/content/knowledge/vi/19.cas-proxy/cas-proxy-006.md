# Xác minh Proxy Ticket và kiểm tra toàn bộ chuỗi proxy trong CAS

## 1. Vì sao phải xác minh cả Proxy Ticket lẫn proxy chain?

Trong **Central Authentication Service (CAS)**, một ứng dụng giao diện (proxy A) có thể cần gọi ứng dụng backend (service B) **thay mặt người dùng**. CAS hỗ trợ tình huống này bằng **Proxy-Granting Ticket (PGT)** và **Proxy Ticket (PT)**.

Đối với backend B, câu hỏi bảo mật không chỉ là “ticket có được CAS phát và còn hợp lệ không?” mà còn:

- Ticket được phát cho **đúng service B** hay cho service khác?
- CAS server tin cậy đã **thực sự xác minh ticket qua /proxyValidate** chưa?
- Người dùng được xác định là ai, có tài khoản/quyền ứng dụng tương ứng không?
- Ticket đã đi qua **những proxy nào, theo thứ tự nào**?
- **Mỗi proxy trong toàn bộ chuỗi** có được B chấp thuận cho tác vụ này không?
- Chuỗi có bị thêm proxy lạ, bỏ một bước, đổi thứ tự hoặc thay thế bằng service không có thẩm quyền không?
- Có bảo vệ kênh HTTPS, một-lần-sử-dụng ticket, cache và credential **PGT** không?

**Nguyên tắc trung tâm:** **CAS protocol validation** và **proxy-chain authorization** là hai kiểm tra liên tiếp. B phải để **CAS server đã được cấu hình tin cậy xác minh PT** với đúng target service, sau đó **từ chối chuỗi proxy không nằm trong chính sách B đã phê duyệt**. Chỉ nhìn thấy tiền tố PT-, một username hoặc một phần tử proxy hợp lệ **không đủ**.

Bài này tập trung **CAS native proxy authentication** trong module **Spring Security - federation / CAS Proxy**. Nó **khác** SAML2 Assertion, OAuth2 delegation và OIDC ID Token. Ví dụ ưu tiên **Java 17**, Spring Boot **3.3.5** và Spring Security **6.x** khi minh họa cấu hình Spring. Tên miền example.org, ticket, user và proxy đều là dữ liệu giả.

### Kết quả học tập

1. Phân biệt **ST, PGT, PGTIOU, PT** và mục đích của **/serviceValidate, /proxy, /proxyValidate**.
2. Giải thích **HTTPS proxy callback (pgtUrl)**, xác minh endpoint và tương quan PGTIOU với PGT.
3. Biết **cas:proxies** thể hiện lịch sử proxy và vì sao **proxy gần backend nhất xuất hiện đầu tiên**.
4. Thiết kế **allowlist nguyên chuỗi** theo exact callback URLs, đúng thứ tự, không chấp nhận proxy lạ.
5. Cấu hình **Cas20ProxyTicketValidator** theo hướng hạn chế thay vì **acceptAnyProxy=true** vô điều kiện.
6. Phân biệt cơ chế **Spring Security CAS stateless ticket cache** với CAS ticket một-lần-sử-dụng tại server.
7. Chạy ví dụ Java 17 xác định ALLOW/DENY chính xác với chuỗi đúng, đảo thứ tự, thiếu/extra hop và service không đúng.
8. Kiểm thử PT thật từ CAS sandbox mà không lấy raw PT/PGT vào logs.

## 2. Các thành phần của CAS proxying

| Thuật ngữ | Ai phát/giữ? | Mục đích | Có được đưa thẳng ra browser hoặc log không? |
| --- | --- | --- | --- |
| **TGC/TGT** | CAS server và browser cookie CAS | Giữ phiên SSO của browser với CAS. | Không lộ TGC/TGT; không phải PT. |
| **ST — Service Ticket** | CAS phát cho ứng dụng khi browser đăng nhập | Chứng minh một lần với **service** được cấp; thường trả qua callback. | Có thể đi qua browser theo protocol, nhưng vẫn là credential nhạy cảm. |
| **PGT — Proxy-Granting Ticket** | CAS phát qua back-channel tới ứng dụng có quyền proxy | Cho ứng dụng xin **nhiều PT** thay mặt một authentication. | **Không**; phải bảo vệ như bí mật server-side. |
| **PGTIOU — Proxy-Granting Ticket IOU** | CAS đưa vào response ticket validation | Khóa tương quan để ghép với PGT đến ở callback. | Không xem PGTIOU là PGT hay credential xin PT. |
| **PT — Proxy Ticket** | CAS phát qua **/proxy** khi ứng dụng có PGT hợp lệ | Cho phép gọi một **targetService** cụ thể; backend phải validate. | Tránh logs, query tracking, Referrer; ngắn hạn và một lần dùng. |
| **pgtUrl** | URL HTTPS của ứng dụng trung gian | CAS gọi callback để kiểm/nhận diện proxy và gửi PGT. | Public endpoint nhưng cần TLS, trust, không lộ nội dung PGT. |
| **cas:proxies** | CAS trả về trong proxy validation response | Danh sách proxy identities, thường là **pgtUrl**, theo thứ tự quy định. | Dùng cho kiểm policy sau khi CAS xác minh thành công. |

**Không được nhầm:** **PGTIOU** chỉ giúp nhận ra PGT nào thuộc ticket validation nào. **PGT** là credential cho proxy xin PT. **PT** không phải PGT và không phải CAS TGT/TGC. Không đưa PGT vào query string khi gọi backend; PGT chỉ được gửi tới **CAS /proxy** từ proxy server.

## 3. Luồng đầy đủ: Browser → Proxy A → Proxy B → Backend C

Giả sử người dùng **alice** truy cập portal A, portal A cần qua proxy B để gọi API C. C chỉ tin luồng được CAS xác minh với **đúng thứ tự A → B → C**.

~~~text
Browser alice               CAS server            Proxy A         Proxy B         Backend C
     |                          |                     |               |                |
     |---- GET A/protected -------------------------->|               |                |
     |<--- redirect CAS /login?service=A ------------|               |                |
     |---- đăng nhập CAS -------->|                   |               |                |
     |<--- ST-A + browser redirect|                   |               |                |
     |---------------------------- ST-A ------------>|               |                |
     |                          |<-- /serviceValidate(ST-A,service=A,pgtUrl=A/pgt)
     |                          |-- HTTPS GET A/pgt?pgtId=PGT-A&pgtIou=IOU-A ------> A
     |                          |------ validated alice + PGTIOU-A -----> A
     |                          |                     |               |                |
     |                          |<-- /proxy?pgt=PGT-A&targetService=B --- A
     |                          |-------- PT-B ------>|               |                |
     |                          |                     |---- PT-B ---->|                |
     |                          |<----- /proxyValidate(PT-B,service=B,pgtUrl=B/pgt) -- B
     |                          |-- HTTPS callback PGT-B/PGTIOU-B ---> B
     |                          |----- alice, proxies=[A], PGTIOU-B --> B
     |                          |                     |               |                |
     |                          |<---- /proxy?pgt=PGT-B&targetService=C ----- B
     |                          |---------------- PT-C --------------------> B
     |                          |                     |               |--- PT-C ------> C
     |                          |<------------------- /proxyValidate(PT-C,service=C) -- C
     |                          |----- alice, proxies=[B,A] --------------> C
     |                          |                     |               |                |
     |                          |                     |               |         C kiểm [B,A]
     |                          |                     |               |         và quyền alice
~~~

*Sơ đồ chỉ mô tả các bước giao thức; các đường kết nối được viết gọn để dễ theo dõi, không phải HTTP trace nguyên văn.*

**Điểm quyết định của C:**

1. **PT-C** do B mang tới đã được phát bởi **CAS server tin cậy** cho **service C**.
2. C gọi **/proxyValidate** với đúng **ticket=PT-C** và **service=C**.
3. CAS trả validation success, **cas:user=alice** và **cas:proxies=[B,A]**.
4. C đối chiếu **cả chuỗi [B,A]** với allowlist: **B phải là proxy gần C nhất; A là proxy đi trước B**.
5. C kiểm thêm **alice có quyền đối với API/resource/tenant** hay không.
6. Nếu có bất kỳ mismatch nào, **không tạo Authentication được ủy quyền, không thực hiện truy xuất nhạy cảm**.

### A/B/C có bắt buộc mỗi bên là một Spring app?

Không. Chúng có thể là Spring MVC, service Java, cổng API hoặc ứng dụng khác hỗ trợ CAS. Điều CAS quan tâm là **service identifiers**, **pgtUrl** và **ticket validation**. Nếu A và B cùng nằm trong một ứng dụng logic, vẫn phải làm rõ các role, quyền proxy và callback IDs.

## 4. Nhận PGT đúng: /serviceValidate + pgtUrl + PGTIOU

Để proxy A có thể xin PT, nó phải nhận được **PGT** qua một cơ chế được CAS chấp nhận. Ví dụ A đang validate ST:

~~~text
GET https://cas.example.org/cas/serviceValidate
    ?service=https%3A%2F%2Fproxy-a.example.org%2Flogin%2Fcas
    &ticket=ST-EXAMPLE
    &pgtUrl=https%3A%2F%2Fproxy-a.example.org%2Fcas%2FpgtCallback
~~~

URL này được xuống dòng **để đọc**, không phải raw URL hợp lệ cho shell. Các tham số **service, ticket, pgtUrl** phân biệt chữ hoa/chữ thường theo CAS protocol.

CAS làm:

1. Kiểm ST còn hiệu lực và **service** khớp giá trị ban đầu CAS phát ticket.
2. Kiểm **pgtUrl là HTTPS**, có thể kết nối và có **TLS certificate/endpoint trust** đúng tiêu chuẩn CAS server; không tin host tùy ý do caller khai.
3. CAS gọi **pgtUrl** của A, gửi query params **pgtId=PGT-A** và **pgtIou=PGTIOU-A**.
4. A lưu cặp PGTIOU→PGT **server-side**, không đưa PGT vào browser.
5. Nếu callback và ticket validation thành công, response XML chứa **cas:proxyGrantingTicket** với **PGTIOU-A**.
6. A đối chiếu IOU ở response với cặp đã lưu trước khi dùng PGT-A.
7. A có thể xin PT-B từ CAS **/proxy** bằng PGT-A.

**CAS phải xác thực pgtUrl**, không chỉ kiểm nó trả HTTP 200. Tài liệu CAS protocol xác định HTTPS callback với PKIX/container trust tối thiểu. Một URL nhái callback hoặc TLS không tin cậy phải không được nhận PGT. Cấu hình exact callbacks/registered services và private key/certificates cần được quản trị.

**Lưu ý race:** CAS có thể gọi callback và trả validation response theo thứ tự mà hệ thống cần đồng bộ. Storage PGTIOU→PGT phải hỗ trợ tương quan, TTL, hạn chế trùng và behavior khi callback bị trễ; nếu IOU không ghép được thì **không phát PT từ “PGT gần nhất”**.

### Ví dụ response khi có PGTIOU

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
    <cas:proxyGrantingTicket>PGTIOU-EXAMPLE</cas:proxyGrantingTicket>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

**PGTIOU-EXAMPLE không phải PGT.** PGT thật chỉ đến backend callback được CAS xác minh. Đây là XML mẫu, không tự có giá trị xác thực khi copy vào ứng dụng.

### Nhận thêm PGT khi B cần tiếp tục proxy

B nhận PT-B và gọi **/proxyValidate** với **pgtUrl=B/pgtCallback**, CAS có thể tiếp tục cấp PGT-B để B xin PT-C. Nhờ vậy hình thành **CAS proxy chain**. CAS server/service registry cần cho phép B **được proxy** đến C; không mặc định mọi backend được proxy tiếp.

## 5. Xin PT bằng /proxy và kiểm bằng /proxyValidate

A hoặc B gửi CAS:

~~~text
GET https://cas.example.org/cas/proxy
    ?pgt=PGT-EXAMPLE
    &targetService=https%3A%2F%2Fapi.example.org%2Fcas%2Freceiver
~~~

CAS kiểm PGT, proxy authorization và **targetService**. Nếu thành công:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:proxySuccess>
    <cas:proxyTicket>PT-EXAMPLE-ONE-TIME</cas:proxyTicket>
  </cas:proxySuccess>
</cas:serviceResponse>
~~~

Ứng dụng proxy chuyển **PT** (không phải PGT) cho backend C. C xác minh:

~~~text
GET https://cas.example.org/cas/proxyValidate
    ?ticket=PT-EXAMPLE-ONE-TIME
    &service=https%3A%2F%2Fapi.example.org%2Fcas%2Freceiver
~~~

Ở đây **service** phải khớp **targetService** mà CAS dùng khi phát PT. **Không dùng URL do attacker kiểm soát** làm targetService/validation service; nếu backend có nhiều endpoints cần CAS ticket, xác định từng service rõ và kiểm request target/service registration.

| Endpoint CAS | Nhiệm vụ | Chấp nhận PT? |
| --- | --- | --- |
| **/login** | Xác thực browser, phát ST. | Không phải ticket validator. |
| **/serviceValidate** | Xác minh **Service Ticket**; có thể phát PGT nếu pgtUrl hợp lệ. | **Không** chấp nhận PT thành công theo CAS 2.0 protocol. |
| **/proxy** | Dùng PGT để xin PT cho targetService. | Không validate PT, không phải browser login. |
| **/proxyValidate** | Xác minh **PT hoặc ST** với service, có thể cung cấp proxy chain và PGTIOU. | **Có**. |
| **/p3/proxyValidate** | Biến thể CAS 3.0, có thể có thêm attributes. | Tùy CAS server/client configuration. |

**Không gọi /serviceValidate khi endpoint được phép nhận PT rồi bỏ qua lỗi**, và không mở **acceptAnyProxy** chỉ để một PT sai chain pass. CAS 2.0 quy định PT/ST đều dùng một lần tại server validation. Phần **StatelessTicketCache** trong Spring có thể cache **kết quả validation** ở ứng dụng, nhưng đó là một quyết định session/cache khác, không làm CAS server ticket thành nhiều-lần-sử-dụng.

### Từ chối khi ticket invalid

CAS trả **authenticationFailure** với các mã như **INVALID_TICKET**, **INVALID_SERVICE**, **INVALID_REQUEST**, **INVALID_TICKET_SPEC**, **UNAUTHORIZED_SERVICE_PROXY**, **INVALID_PROXY_CALLBACK** hoặc lỗi nội bộ tùy nơi. Backend phải:

- Không cho quyền từ username/client-supplied claims khi validation fail.
- Không thử lại cùng PT như thể nó còn hiệu lực: ticket có thể đã bị CAS tiêu thụ.
- Không đổi service sang một URL khác để khiến ticket “khớp”.
- Không tin một response XML được caller tự gửi; response phải đến từ CAS endpoint qua TLS trust và HTTP client hợp lệ.

## 6. Cách đọc đúng chuỗi cas:proxies

Ví dụ CAS trả thành công cho backend C:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
    <cas:proxies>
      <cas:proxy>https://proxy-b.example.org/cas/pgtCallback</cas:proxy>
      <cas:proxy>https://proxy-a.example.org/cas/pgtCallback</cas:proxy>
    </cas:proxies>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

Theo **CAS Protocol 2.0**, khi qua nhiều proxy, phần tử **cas:proxy đầu tiên là proxy được đi qua gần đây nhất**. Với hành trình A → B → C, C nhận danh sách **[B, A]**, không phải [A, B]. Bản danh sách thường biểu diễn **pgtUrl (proxy callback identity)**, **không phải URL backend resource**, tên hiển thị hay service ticket.

| Vị trí | Giá trị | Diễn giải |
| --- | --- | --- |
| **[0]** | https://proxy-b.example.org/cas/pgtCallback | Proxy gần nhất **trước C**. |
| **[1]** | https://proxy-a.example.org/cas/pgtCallback | Proxy đi trước B, gần browser/user hơn. |
| **Không có** | Không có phần tử proxy | Có thể là ST trực tiếp hoặc validation không qua proxy, tùy profile. |

**Không suy luận rằng danh sách không có proxy luôn là lỗi ở mọi endpoint.** Một endpoint nhận **ST trực tiếp** có thể hợp lệ với empty chain. Nhưng endpoint **chỉ dành cho delegated PT** phải **chủ động từ chối empty chain**. Tách policy theo endpoint và use case.

### Vì sao kiểm cả chuỗi, không chỉ phần tử cuối?

C có thể tin B như API gateway, nhưng B lại nhận request từ proxy X chưa được phê duyệt:

~~~text
Expected: Alice -> A -> B -> C
Observed: Alice -> X -> B -> C

Expected cas:proxies = [B, A]
Observed cas:proxies = [B, X]
~~~

Kiểm **chỉ “có B”** sẽ chấp nhận sai. Kiểm **toàn bộ danh sách [B,A] theo thứ tự** sẽ từ chối, kể cả B hợp lệ. Tương tự, **[B,A,X]** phải fail nếu policy chỉ cho **[B,A]**, không bỏ qua hop bổ sung.

### Không dùng prefix/substring wildcard bừa bãi

Nếu allowlist có **https://proxy-a.example.org/cas/pgtCallback**, đừng match các chuỗi:

- https://proxy-a.example.org.evil.test/cas/pgtCallback
- http://proxy-a.example.org/cas/pgtCallback
- https://proxy-a.example.org/cas/pgtCallback-extra
- https://proxy-a.example.org/anotherPath
- https://evil.test/?next=https://proxy-a.example.org/cas/pgtCallback

Dùng exact IDs chuẩn hóa theo **hợp đồng CAS** và config quản trị; nếu cần regex trong CAS Java Client, phải **anchor**, escape và test các trường hợp tương tự. **Không tự normalize host/path/query một cách rộng** nếu làm mất phân biệt identity mà CAS đã xác minh.

## 7. Thiết kế allowlist nguyên chuỗi

Một chính sách dành riêng backend C:

~~~yaml
cas:
  backend-c:
    service: "https://api.example.org/cas/receiver"
    require-delegation: true
    allowed-chains:
      - ["https://proxy-b.example.org/cas/pgtCallback",
         "https://proxy-a.example.org/cas/pgtCallback"]
~~~

Đây là **mẫu policy của ứng dụng**, không phải thuộc tính auto-configuration sẵn có của Spring Boot. Quy trình triển khai phải map policy vào **Cas20ProxyTicketValidator** và/hoặc authorization service theo phiên bản client.

**Quy tắc khớp:**

1. Kiểm CAS ticket validation success trước; nếu fail thì **DENY**.
2. Kiểm service ID trả về/được xác minh khớp service C đã đăng ký.
3. Chuỗi CAS đã xác minh phải có **đúng số lượng phần tử**, đúng URL từng vị trí và đúng thứ tự.
4. Nếu endpoint yêu cầu proxy, không chấp nhận chain rỗng, null hoặc giá trị thiếu.
5. Dùng **allowlist cả chuỗi** chứ không phải kiểm “mỗi hop nằm trong một set”: tập hợp {A,B} vẫn có thể cho nhầm [A,B] và [B,A].
6. Không tự cho phép thêm gateway/CDN/ingress vào chain nếu nó không phải CAS proxy identity được công bố.
7. Nếu cho nhiều chuỗi, liệt kê **từng chuỗi hợp lệ** và lý do nghiệp vụ; tránh một regex rộng có thể nhận bất kỳ depth/path.
8. Sau khi chain pass, **kiểm user và quyền đối với operation/tenant**; trusted proxy không tự trao quyền mọi người dùng.

### Chain order trong config thư viện

CAS Java Client có thuộc tính **allowedProxyChains**; mỗi entry có thể là chuỗi URL proxy, hoặc regex theo cú pháp tài liệu client. **Cách thư viện lưu/chuyển chuỗi và việc match được quyết định bởi phiên bản client**, nên hãy **test trường hợp [B,A]** từ CAS server thực; không tự đảo danh sách dựa trên trực giác về “đường đi” khi cấu hình. Trong bảng policy của bài này, **[B,A] là thứ tự XML nhận tại C**.

### Một điểm kiểm policy ngoài chain

Nếu backend C chỉ tin **proxy B** và không quan tâm ai đứng trước B, phải ghi rõ đó là **policy chấp nhận mọi upstream của B**, khác hẳn yêu cầu **xác minh toàn bộ chuỗi proxy**. Với dữ liệu nhạy cảm, nên dùng **strict full-chain allowlist** để hạn chế delegation bất ngờ. Nếu business thật sự cho phép chain mở rộng, cần threat model, maximum hop count, danh sách cấm/vòng lặp, identity uniqueness và audit; không đặt acceptAnyProxy=true ngầm.

## 8. Java 17 độc lập: kiểm cả chuỗi theo đúng thứ tự

**ProxyChainPolicyDemo.java** chạy với **JDK 17**, không cần Spring/CAS server. Đầu vào **VerifiedTicket** chỉ là mô phỏng **kết quả đã được CAS TicketValidator xác thực qua HTTPS**. Trong production, tuyệt đối không dựng nó trực tiếp từ HTTP header, JSON body, query, XML do client gửi hoặc chuỗi PT- chưa validate.

~~~java
import java.util.List;
import java.util.Set;

public class ProxyChainPolicyDemo {
    private static final String TARGET =
            "https://api.example.org/cas/receiver";
    private static final String A =
            "https://proxy-a.example.org/cas/pgtCallback";
    private static final String B =
            "https://proxy-b.example.org/cas/pgtCallback";

    // CAS XML ở backend C: proxy gần nhất đứng ĐẦU.
    private static final List<String> EXPECTED = List.of(B, A);
    private static final Set<String> ACTIVE_USERS = Set.of("alice");

    record VerifiedTicket(String user, String service, List<String> proxies) {}

    static String decide(VerifiedTicket ticket) {
        if (ticket == null) {
            return "DENY INVALID_TICKET";
        }
        if (!TARGET.equals(ticket.service())) {
            return "DENY WRONG_SERVICE";
        }
        if (ticket.user() == null || !ACTIVE_USERS.contains(ticket.user())) {
            return "DENY USER_NOT_ALLOWED";
        }
        if (ticket.proxies() == null || ticket.proxies().isEmpty()) {
            return "DENY EMPTY_CHAIN";
        }
        if (!EXPECTED.equals(ticket.proxies())) {
            return "DENY UNAPPROVED_CHAIN";
        }
        return "ALLOW";
    }

    static void check(String label, VerifiedTicket ticket) {
        System.out.println(label + ": " + decide(ticket));
    }

    public static void main(String[] args) {
        check("valid A-B", new VerifiedTicket(
            "alice", TARGET, List.of(B, A)));

        check("reversed B-A", new VerifiedTicket(
            "alice", TARGET, List.of(A, B)));

        check("extra hop", new VerifiedTicket(
            "alice", TARGET, List.of(B, A,
                "https://unknown.example.org/cas/pgtCallback")));

        check("unapproved upstream", new VerifiedTicket(
            "alice", TARGET, List.of(B,
                "https://evil.example.org/cas/pgtCallback")));

        check("direct", new VerifiedTicket(
            "alice", TARGET, List.of()));

        check("wrong service", new VerifiedTicket(
            "alice", "https://other.example.org/cas/receiver",
            List.of(B, A)));

        check("unknown user", new VerifiedTicket(
            "mallory", TARGET, List.of(B, A)));

        check("missing validation", null);
    }
}
~~~

Chạy:

~~~bash
javac ProxyChainPolicyDemo.java
java ProxyChainPolicyDemo
~~~

**stdout chính xác:**

~~~text
valid A-B: ALLOW
reversed B-A: DENY UNAPPROVED_CHAIN
extra hop: DENY UNAPPROVED_CHAIN
unapproved upstream: DENY UNAPPROVED_CHAIN
direct: DENY EMPTY_CHAIN
wrong service: DENY WRONG_SERVICE
unknown user: DENY USER_NOT_ALLOWED
missing validation: DENY INVALID_TICKET
~~~

**Giải thích từng trường hợp:**

- **valid A-B:** đường đi thực A→B→C sinh danh sách **[B,A]**, khớp exact policy nên ALLOW.
- **reversed B-A:** CAS XML [A,B] không phải [B,A]; nếu chỉ so set sẽ mắc lỗi.
- **extra hop:** danh sách có B,A và thêm X **không** được coi là đúng; fail exact-chain.
- **unapproved upstream:** B hợp lệ nhưng upstream X không được phép; fail.
- **direct:** không có proxy không hợp lệ với endpoint **chỉ nhận delegated PT**.
- **wrong service:** ticket service khác policy C; fail kể cả chain đúng.
- **unknown user:** service/chain đúng cũng không tự cấp quyền cho mọi tài khoản.
- **missing validation:** không có kết quả từ CAS TicketValidator, không phát quyền.

**Ranh giới demo:** class VerifiedTicket được tạo từ các giá trị tĩnh trong main; chương trình **không xác minh CAS ticket, không kiểm HTTPS, XML, PGT, TTL, cache hoặc identity CAS thực**. Trong hệ thống thật chỉ chạy **decide** trên kết quả đã được CAS server tin cậy xác nhận và nhận metadata từ library validation, không từ browser.

## 9. Spring Security CAS: các lớp liên quan đến PT

Trong **Spring Security 6.x**, CAS native integration có các vai trò:

| Lớp | Vai trò |
| --- | --- |
| **CasAuthenticationEntryPoint** | Redirect browser đến CAS /login khi cần đăng nhập; không kiểm PT. |
| **CasAuthenticationFilter** | Nhận CAS ticket từ HTTP request; nếu cấu hình hỗ trợ stateless, có thể nhận ticket ngoài callback /login/cas. |
| **ServiceProperties** | Định nghĩa service URL, có thể bật **authenticateAllArtifacts** nếu muốn xử lý CAS artifacts từ nhiều paths. |
| **ServiceAuthenticationDetailsSource** | Xây ServiceAuthenticationDetails chứa service URL cụ thể của request cho stateless proxy authentication. |
| **CasAuthenticationProvider** | Dùng TicketValidator để xác thực CAS ST/PT, lấy user details/authorities, trả CasAuthenticationToken. |
| **Cas20ServiceTicketValidator** | Dùng /serviceValidate cho ST, không thích hợp nếu cần chấp nhận PT. |
| **Cas20ProxyTicketValidator** | Dùng /proxyValidate, kiểm CAS validation response và **proxy-chain policy** theo cài đặt. |
| **StatelessTicketCache** | Tùy chọn lưu kết quả xác thực cho remoting/stateless client, phải có giới hạn TTL và ràng buộc an ninh. |

### 9.1. Đổi validator khi backend nhận PT

Trong một ứng dụng vốn đã có CAS login integration, đổi **Cas20ServiceTicketValidator** sang **Cas20ProxyTicketValidator** là bước cần nhưng chưa đủ. Cần cấu hình allowed proxy chains và đúng service, ticket cache/endpoint.

**Mảnh mã cấu hình minh họa với Apereo CAS Java Client; không tự biên dịch độc lập nếu thiếu project và dependencies:**

~~~java
import org.apereo.cas.client.util.CommonUtils;
import org.apereo.cas.client.validation.Cas20ProxyTicketValidator;

String casPrefix = "https://cas.example.org/cas";
Cas20ProxyTicketValidator validator =
        new Cas20ProxyTicketValidator(casPrefix);

validator.setAcceptAnyProxy(false);
validator.setAllowEmptyProxyChain(false);
validator.setAllowedProxyChains(CommonUtils.createProxyList(
        "https://proxy-b.example.org/cas/pgtCallback "
      + "https://proxy-a.example.org/cas/pgtCallback"));
~~~

**Ý nghĩa:**

- **casPrefix:** base CAS server đã phê duyệt; validator gọi **/proxyValidate** qua HTTPS.
- **setAcceptAnyProxy(false):** không bỏ qua quy tắc chuỗi proxy.
- **setAllowEmptyProxyChain(false):** endpoint chỉ dành cho delegated PT thì **không** nhận direct ST/empty chain.
- **setAllowedProxyChains:** danh sách chuỗi được cho phép, ở đây chỉ một chuỗi gồm B và A theo policy; **xác nhận thứ tự/cú pháp match bằng test đúng phiên bản CAS client**.
- **CommonUtils.createProxyList:** helper của CAS Java Client chuyển policy string thành ProxyList; thay đổi package/API cần đối chiếu dependency đang dùng.

**Nếu version client dùng ProxyList API khác**, không tự thay bằng **acceptAnyProxy=true** để đi qua lỗi compile/config. Tra Javadoc đúng phiên bản và triển khai equivalent strict allowed list.

### 9.2. Mảnh mã Spring bean: TicketValidator trong CasAuthenticationProvider

Trong project Spring Boot 3.3.5 đã có **spring-security-cas**, **CasAuthenticationProvider** cần nhận TicketValidator đã cài ở trên:

~~~java
// Mảnh mã phải đặt trong @Configuration và dùng các bean/import thật.
// Đây KHÔNG phải toàn bộ ứng dụng Spring Security runnable.

@Bean
CasAuthenticationProvider casProvider(
        ServiceProperties serviceProperties,
        UserDetailsService localUsers,
        Cas20ProxyTicketValidator proxyValidator) {

    CasAuthenticationProvider provider = new CasAuthenticationProvider();
    provider.setServiceProperties(serviceProperties);
    provider.setUserDetailsService(localUsers);
    provider.setTicketValidator(proxyValidator);
    provider.setKey("cas-backend-provider");
    return provider;
}
~~~

Các kiểu cần import tương ứng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.apereo.cas.client.validation.Cas20ProxyTicketValidator;
~~~

**provider key là identifier nội bộ**, không phải private signing key. **UserDetailsService** là nơi map user CAS đã xác minh thành account/authorities của ứng dụng; không tự cho mọi username ROLE_ADMIN.

Để dùng trong **Spring SecurityFilterChain** cần thêm **CasAuthenticationFilter**, **AuthenticationManager/ProviderManager**, filter order, đúng SecurityContextRepository/session policy và endpoint match. Chỉ tạo provider bean **không tự bật CAS ticket authentication**. Nếu cấu hình CAS filter thủ công với Spring Security 6.x, phải đảm bảo **SecurityContextRepository được dùng để lưu Authentication cho stateful login** và **SessionAuthenticationStrategy** (session fixation) phù hợp; nếu không, request sau login có thể bị coi là anonymous.

### 9.3. Khi nhận PT ở URL không phải /login/cas

Theo tài liệu Spring Security CAS proxy integration, với stateless remoting nhận ticket trên những URL khác callback thường cần:

~~~java
// Mảnh mã minh họa, filter, serviceProperties đã được tạo:
serviceProperties.setAuthenticateAllArtifacts(true);
filter.setServiceProperties(serviceProperties);
filter.setAuthenticationDetailsSource(
        new ServiceAuthenticationDetailsSource(serviceProperties));
~~~

**ServiceAuthenticationDetailsSource** giúp validator dùng **service URL của request** làm giá trị service trong tình huống stateless. Tuy nhiên, bật **authenticateAllArtifacts=true** trên toàn ứng dụng có thể khiến bất kỳ URL nào chứa query **ticket** bị CAS filter bắt, nếu không có matchers/endpoint policy phù hợp.

Hạn chế:

- Dành **filter chain hoặc request matcher riêng** cho endpoints nhận PT.
- Kiểm CAS ticket cho **đúng service ID** đã đăng ký; tránh xây service theo Host/X-Forwarded-* do client trực tiếp điều khiển.
- Cấu hình **acceptAnyProxy=false** và full-chain allowlist trước khi mở endpoint.
- Quyết định **có hỗ trợ direct ST (empty chain)** hay PT-only và test rõ.
- Bảo vệ authentication success/failure handler, SecurityContext/session behavior và authorization cho route tương ứng.
- Không cho một PT hợp lệ ở resource này trở thành quyền truy cập mọi URL/tenant khác chỉ vì backend dùng chung CasAuthenticationToken.

**Mảnh này không là một mẫu production hoàn chỉnh.** Khi xây filter chain đầy đủ, cần kiểm API của Spring Security/CAS client version và test tích hợp thực; cấu hình sai có thể chấp nhận PT ngoài phạm vi dự kiến.

## 10. Ticket cache: tính một lần của CAS và kết quả đã cache của Spring

Theo CAS protocol, **ST/PT** là artifact ngắn hạn và **một lần sử dụng** khi gọi CAS server để validate. Sau khi /proxyValidate thành công, CAS thường không chấp nhận validate lại **cùng PT**.

Spring Security CAS có **StatelessTicketCache**, dùng trong mô hình remoting không có HttpSession để cache **CasAuthenticationToken sau khi validate thành công**. Nếu client tiếp tục trình **cùng một chuỗi PT** tới backend, Spring có thể lấy Authentication từ cache mà không gọi CAS server lần nữa.

**Điều này không biến PT thành nhiều-lần-sử-dụng tại CAS.** Nó tạo ra một **quyết định chấp nhận lại bearer ticket tại backend dựa trên cache local**, vì vậy có rủi ro nếu ticket bị lộ.

### Hai lựa chọn chính sách

| Chính sách | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| **Không cache kết quả PT / cache rỗng** | Gần với one-time CAS validation; PT dùng lại sẽ fail nếu validation lại. | Mỗi request stateless cần **PT mới** hoặc cơ chế session/token khác. |
| **StatelessTicketCache có TTL rất ngắn và bound scope** | Giảm round trips tới CAS; hỗ trợ client gọi lại trong thời gian cho phép. | Trong TTL, ai có cùng PT có thể lấy Authentication nếu endpoint không thêm binding/authorization; cần tính toán cẩn thận. |
| **SP HttpSession stateful** | Browser chỉ cần validate ST/PT một lần rồi lưu SecurityContext. | Cần cookie/session security, invalidation, multi-node shared sessions/affinity. |

Nếu cho phép cache, phải xem xét:

1. TTL ngắn theo threat model và chính sách logout/revocation.
2. Không cache negative validation như user hợp lệ.
3. Cache key không được trộn **khác CAS server, service, tenant, role/proxy policy**.
4. Tránh tái sử dụng một PT để truy cập các endpoints có service/authorization khác.
5. Có giải pháp clear cache khi proxy/PGT bị thu hồi hoặc chính sách trust thay đổi.
6. Giới hạn bộ nhớ/size, mã hóa và kiểm soát truy cập đối với cache.
7. Test replay có/không cache để nêu rõ khác biệt, không hứa một-lần-sử-dụng nếu backend intentionally cache kết quả.

**Không dùng acceptAnyProxy=true + cache nhiều giờ** để tránh invalid ticket. Đó là mở rộng trust và credential lifetime; nếu caller cần liên tục gọi backend, thiết kế delegation/token lifecycle phù hợp thay vì dựa vào ticket cache vô hạn.

## 11. Bảo vệ proxy callbacks, TLS và secret PGT

### pgtUrl không phải URL tùy ý

Theo CAS protocol, CAS gọi **pgtUrl bằng HTTPS** và cần xác minh peer trust. Vận hành phải kiểm:

- URL public đầy đủ, có **scheme=https**.
- CAS server kết nối được đến endpoint, TLS certificate hợp lệ và hostname khớp.
- Endpoint thuộc proxy hợp lệ/registered service, không phải địa chỉ callback do attacker gửi.
- Không dùng rộng **allow-all hostname verifier** hoặc tắt TLS cert validation để “lấy PGT cho được”.
- CAS callback trả response phù hợp; các request lỗi không được trả PGT.
- Đường callback **không yêu cầu browser authentication/redirect CAS vô hạn**.
- Không log **pgtId**, **pgtIou**, ST, PT ở reverse proxy, access log, APM hay browser analytics.

### PGT storage

- Lưu PGT server-side trong storage bảo vệ quyền, có TTL/cleanup, không truyền PGT ra client/browser.
- Nếu chạy nhiều instance, callback CAS có thể vào node A còn ticket validation response xử lý ở node B; **PGT storage phải chia sẻ hoặc định tuyến đúng**, không tự cho giá trị IOU lạ khớp PGT của phiên khác.
- Dùng **IOU correlation** thay vì chọn latest PGT.
- Chỉ dùng PGT đã gắn với đúng authenticated principal/service và policy.
- Không giữ PGT bị compromise/expired; cần incident response/rotation và CAS logout lifecycle.
- Kiểm lỗi callback, TLS, proxy, race và storage availability. Không bỏ TLS hoặc cho phép PGT null mà vẫn phát PT.

### PT transport

PT là **bearer credential** nên yêu cầu HTTPS trong proxy→backend; nếu truyền qua query param, thiết lập URL redaction ở load balancer, logs, tracing, error reports và tránh referrer leakage. Backend validate PT với CAS server tin cậy qua HTTPS và không ghi raw PT vào SecurityContext/audit output khi không cần.

### CAS server-side service registry

CAS server cần giới hạn:

- Proxy nào được cấp PGT/proxy permission.
- Proxy được xin PT cho những targetService nào.
- Callback pgtUrl và TLS policy.
- Những service IDs mà backend yêu cầu validate; tránh wildcard rộng.
- Việc ủy quyền nhiều hop có được cho phép và theo chính sách nào.

Backend C **vẫn kiểm lại full chain** vì CAS cho phép proxy không đồng nghĩa C đã phê duyệt proxy chain cho mọi chức năng.

## 12. Điều kiện validation thành công nhưng vẫn phải từ chối truy cập

Một ví dụ CAS server trả user **alice** và chain đúng **[B,A]**:

~~~text
cas:authenticationSuccess
  cas:user = alice
  cas:proxies = [B,A]
  validated service = https://api.example.org/cas/receiver
~~~

C vẫn có thể cần:

1. Map **alice** thành local account đúng tenant/organization/cas realm.
2. Kiểm account đang active, chưa bị khóa/deprovisioned.
3. Kiểm authority/role cho **operation** cụ thể.
4. Kiểm resource/owner/tenant của dữ liệu được yêu cầu, không chỉ authenticated().
5. Kiểm caller ứng dụng B được cấp scope proxy sang service C theo policy.
6. Kiểm request không gây cross-tenant BOLA/IDOR dù chain hoàn toàn hợp lệ.
7. Có rate limit, observability và audit, không phát raw ticket/proxy identities nhạy cảm ra ngoài.

**CAS username không phải global unique identity trong môi trường có nhiều CAS servers.** Tài khoản cùng tên từ hai CAS realms có thể là hai người khác nhau; cần namespace issuer/CAS trust domain và account binding. Với một CAS server có nhiều tenant, vẫn phải kiểm local membership.

### Chính sách theo endpoint thay vì mọi backend chung một policy

Ví dụ:

| Backend endpoint | Chain được phép | Yêu cầu thêm |
| --- | --- | --- |
| /api/reports/read | [B,A] | alice có quyền REPORT_READ ở tenant X. |
| /api/payroll/export | [TrustedPayrollGateway] | Payroll role; không cho portal A ủy quyền tùy ý. |
| /api/self-service | direct ST hoặc [A] tùy design | Chỉ bản ghi của chính user. |
| /api/admin | Không chấp nhận PT công cộng | Service principal/đặc quyền riêng, audit. |

**Một ticket identity hợp lệ ở một endpoint không được dùng làm global admin identity.** Policy chain, service URL, roles và resource scope phải đi cùng nhau.

## 13. Bảo vệ XML response và ranh giới parse

CAS /proxyValidate trả về XML/JSON tùy CAS version/config. **Không parse tự chế từ XML do browser gửi**. Validator cần:

1. Gọi CAS endpoint tin cậy qua HTTPS, hostname/certificate validation.
2. Gửi ticket và **service** chính xác.
3. Kiểm **authenticationSuccess** không phải authenticationFailure.
4. Parse username/attributes và **cas:proxies** từ **response của CAS server**, không từ client.
5. Có phòng vệ XXE, entity expansion, unexpected namespaces/DTD, kích thước response và XML parser configurations; ưu tiên CAS Java Client đã được bảo trì.
6. Kiểm full-chain allowlist/empty policy và user/service authorization.
7. Chỉ tạo Authentication khi các bước cùng pass.

**Không tự tin cas:proxies nếu được copy từ user input.** Một chuỗi XML mà attacker viết có thể chứa [B,A] đẹp, nhưng chỉ **CAS validator** biết PT được CAS phát và proxy history thực. Việc đối chiếu text thôi không phải cryptographic/protocol validation.

### Phân biệt CAS XML và SAML Assertion

CAS XML serviceResponse không phải **SAMLResponse** với XML Signature của SAML2. Không dùng **Saml2WebSsoAuthenticationFilter** để xác minh CAS native PT, cũng không coi một SAML2 issuer là CAS proxy callback. Nếu CAS server tích hợp thêm SAML/OIDC, phải chọn đúng protocol và trust boundaries.

## 14. Kịch bản kiểm thử tích hợp

Dùng **CAS sandbox đã cấu hình service registry, PGT callbacks và PT issuance**, có ít nhất Proxy A, Proxy B, Backend C. Quan sát được **/serviceValidate, /proxy, /proxyValidate** nhưng **che ST/PT/PGT trong logs**. Negative tests phải kiểm riêng **CAS rejection** và **full-chain policy rejection**.

| # | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| 1 | A nhận ST hợp lệ và pgtUrl A qua HTTPS đáng tin | A có thể lấy PGT sau callback + IOU match. |
| 2 | CAS callback PGT tới URL HTTP | **Từ chối** theo yêu cầu HTTPS. |
| 3 | CAS callback TLS cert/hostname sai | Không cấp PGT; không tắt TLS validation. |
| 4 | pgtUrl A không reachable hoặc không trả phản hồi chấp nhận | PGT acquisition fail, không phát PT. |
| 5 | IOU response không khớp PGT callback | **Từ chối** sử dụng PGT. |
| 6 | A dùng PGT hợp lệ xin PT-B cho targetService=B | CAS có thể phát PT-B nếu service registry cho phép. |
| 7 | PGT hết hạn/bị thu hồi | CAS từ chối /proxy, không có PT. |
| 8 | PT-B được validate tại B bằng đúng service | Có thể thành công nếu policy và ticket hợp lệ. |
| 9 | PT-B mang đến backend C thay vì B | **INVALID_SERVICE**, vì targetService mismatch. |
| 10 | Gửi PT tới /serviceValidate thay /proxyValidate | **Không thành công** theo CAS 2.0. |
| 11 | Gửi lại cùng PT tới CAS lần hai | CAS từ chối reuse ticket. |
| 12 | CAS /proxyValidate trả authenticationFailure | Backend không tạo Authentication/quyền. |
| 13 | Valid PT-C, cas:proxies=[B,A] | **ALLOW** nếu C cho phép đúng chain và user/action đạt. |
| 14 | cas:proxies=[A,B] bị đảo | **DENY**, dù A/B đều là trusted hop. |
| 15 | cas:proxies=[B,X] | **DENY**, B hợp lệ không cứu upstream X. |
| 16 | cas:proxies=[B,A,X] | **DENY**, có hop dư ngoài allowlist. |
| 17 | cas:proxies=[B] thay vì [B,A] | **DENY** nếu C yêu cầu hai-hop chain. |
| 18 | cas:proxies=[] trên endpoint PT-only | **DENY EMPTY_CHAIN**. |
| 19 | Chain chứa http://proxy-b thay cho https://proxy-b | **DENY**, exact callback identity sai. |
| 20 | Chain chứa tên miền proxy-b.example.org.evil.test | **DENY**, không match substring host. |
| 21 | Chain đúng nhưng user không có local role/resource ACL | **DENY authorization**. |
| 22 | Chain đúng nhưng CAS ticket service là endpoint khác | **DENY WRONG_SERVICE**. |
| 23 | Gửi XML chứa <cas:proxies>[B,A] do attacker tự tạo | Không tin nếu chưa qua CAS server validation. |
| 24 | StatelessTicketCache bật và PT cũ được dùng lại trong TTL | Kiểm behavior cache, không tuyên bố CAS đã revalidate. |
| 25 | Cache quá TTL hoặc policy proxy thay đổi | Không giữ quyền cũ, phải lấy PT mới/reauth theo policy. |
| 26 | CAS server HTTPS chứng chỉ hết hạn | Validation lỗi; không tắt TLS để ép accept. |
| 27 | App có nhiều CAS servers, cùng username alice | Không tự gộp identity/account giữa CAS realms. |
| 28 | Backend C thuộc tenant khác dù chain [B,A] đúng | **DENY cross-tenant access**. |
| 29 | B xin PT cho service chưa đăng ký/không được phép | CAS /proxy từ chối. |
| 30 | App nhiều node, callback PGT và validator ở hai nodes | Cần storage/session routing đúng, IOU phải match. |

**Bài test nên tách kết quả:**

- **CAS_VALIDATION=PASS/FAIL**: CAS server xác minh ticket.
- **PROXY_CHAIN=PASS/FAIL**: ứng dụng chấp nhận **toàn bộ** danh sách proxy.
- **SERVICE_BINDING=PASS/FAIL**: targetService đúng.
- **LOCAL_AUTHZ=PASS/FAIL**: quyền user, tenant và resource.

Bốn lớp đều pass mới thực hiện operation. Test chỉ chứng minh **valid ticket** chưa chứng minh full-chain policy đúng.

## 15. Troubleshooting theo từng tầng

| Triệu chứng | Nguyên nhân thường gặp | Hướng điều tra |
| --- | --- | --- |
| **INVALID_TICKET** | PT hết hạn/đã validate một lần/ticket không tồn tại. | Xin PT mới; không replay hoặc bypass validator. |
| **INVALID_SERVICE** | CAS targetService khi phát PT khác service lúc validate. | So exact scheme/host/path/port, proxy rewriting và service registry. |
| **UNAUTHORIZED_SERVICE_PROXY** | Service không được phép xin PGT/proxy. | Kiểm CAS registered service policy, đừng mở wildcard. |
| **INVALID_PROXY_CALLBACK** | pgtUrl TLS/hostname/endpoint trust sai. | Kiểm callback HTTPS, certificate chain, DNS, firewall. |
| **Không có PGTIOU** | Callback không thành công/không được CAS cấp PGT. | Kiểm response và proxy receptor, không dùng PGT mặc định. |
| **Có IOU nhưng không tìm thấy PGT** | Storage/race/cluster mapping lỗi. | Kiểm distributed PGT storage, callback và expiry. |
| **PT được CAS validate nhưng backend vẫn 403** | Proxy-chain allowlist hoặc local user/tenant role từ chối. | Phân biệt CAS auth success và application authorization. |
| **Cas20ServiceTicketValidator không chấp nhận PT** | Dùng /serviceValidate thay /proxyValidate. | Chọn Cas20ProxyTicketValidator đúng endpoint. |
| **[B,A] bị reject trong khi kỳ vọng A→B** | Lẫn thứ tự đường đi với XML order. | CAS XML **most recent proxy first**, kiểm rule theo version. |
| **[B,X] vẫn được chấp nhận** | acceptAnyProxy=true hoặc chỉ xét B. | Dùng full-chain policy và test unknown upstream. |
| **Direct ST được nhận tại PT-only endpoint** | Empty proxy chain được cho phép. | setAllowEmptyProxyChain(false) hoặc policy tương đương. |
| **Một PT dùng được nhiều lần** | Spring stateless validation-result cache. | Kiểm cache TTL, scope và quyết định chính sách reuse. |
| **HTTP 200 từ CAS nhưng chưa authentication success** | Body có authenticationFailure hoặc lỗi parse. | Parse bằng CAS validator, không chỉ kiểm status code. |
| **Ticket lộ qua access logs** | Log URL query nguyên văn. | Redact ticket/pgtId/pgtIou ở proxy/APM/logs. |
| **Đổi reverse proxy làm service khác** | Host/scheme/path thay đổi. | Dùng public service ID cố định hoặc trusted forwarded headers. |
| **PGT lưu ở A, request PT tại B không thấy** | Multi-node storage không đồng bộ. | Shared PGT store có TTL/ACL, kiểm IOU correlation. |
| **CAS user hợp lệ được vào dữ liệu tenant khác** | Local authorization thiếu tenant scope. | Kiểm membership, role và data-layer tenant predicates. |

**Logging gợi ý** (không phải log framework tự sinh):

~~~text
event=cas_proxy_validation result=success service=backend-c trace=t-102
event=cas_proxy_chain_policy result=deny reason=UNAPPROVED_CHAIN trace=t-102
event=cas_local_authorization result=deny action=payroll-export trace=t-102
~~~

Không log raw **ST, PT, PGT, PGTIOU, TGC**, full proxy callback URL có secret, username nhạy cảm hoặc XML validation response đầy đủ. Với audit chỉ cần mã đối tác, chain policy ID, reason và trace ID đã được quản trị.

## 16. Sai lầm thường gặp

1. **Thấy PT- là chấp nhận**: prefix chỉ là quy ước, không phải chứng minh ticket hợp lệ.
2. **Gọi /serviceValidate để kiểm PT**: CAS 2.0 không chấp nhận PT tại đây.
3. **Chỉ so một trusted proxy**: một upstream proxy lạ có thể lọt qua.
4. **Không kiểm thứ tự cas:proxies**: CAS trả most-recent-first.
5. **So set thay vì list**: [A,B] và [B,A] là hai chain khác nhau.
6. **Dùng contains/startsWith cho callback URLs**: có thể nhận host hoặc path giả mạo.
7. **Bật acceptAnyProxy=true trong production** để tránh lỗi allowlist.
8. **Cho phép chain rỗng ở endpoint yêu cầu PT**: nhận nhầm direct ST.
9. **Tin cas:proxies do HTTP client khai báo** thay vì response từ CAS đã validate.
10. **Đưa PGT/PGTIOU/PT vào log/browser**: lộ credential/correlation info.
11. **Dùng PGTIOU làm PGT**: IOU không thể xin PT.
12. **Cho mọi pgtUrl/ticket URL tùy ý** mà không kiểm TLS và registry.
13. **Giữ PGT vô hạn, không cleanup/rotate** khi session hoặc proxy bị thu hồi.
14. **Không test race giữa PGT callback và validation response**.
15. **Không xét service binding**: PT cho B không hợp lệ tại C.
16. **Không xét tenant/role sau proxy chain pass**: delegation hợp lệ không đồng nghĩa business permission.
17. **Tin cache Spring là CAS đã validate PT lại**: cache chỉ tái sử dụng kết quả.
18. **Dùng Java/Spring client API khác phiên bản mà không kiểm Javadoc**.
19. **Gộp CAS Proxy với OAuth2 delegated token hoặc SAML2 Assertion**.
20. **Quên reverse proxy/HTTPS public service URL**, dẫn đến INVALID_SERVICE khó hiểu.
21. **Chỉ kiểm HTTP 200 của /proxyValidate**: body có thể chứa authenticationFailure.
22. **Gắn CAS filter vào mọi endpoint** khi không kiểm authenticateAllArtifacts và chain-specific policy.
23. **Chấp nhận mọi username CAS là ROLE_ADMIN** khi chưa có local account management.
24. **Gộp username giữa các CAS realms** khi hỗ trợ nhiều đối tác.
25. **Cho ticket cache vượt quá revocation window**.
26. **Không bảo vệ proxy reception endpoint khỏi đăng ký/điều khiển ngoài dự kiến**.

## 17. Checklist triển khai production

**CAS server và giao thức**

- [ ] CAS serverPrefix và endpoints **/serviceValidate, /proxy, /proxyValidate** đúng CAS protocol/version.
- [ ] CAS registered services chỉ cho phép những proxy/targetService đã phê duyệt.
- [ ] pgtUrl dùng HTTPS/TLS trust, callback reachable nhưng không bị caller tự chọn.
- [ ] PGTIOU được đối chiếu đúng PGT lưu server-side, có TTL và chống race.
- [ ] ST/PT được CAS server validate với service ID khớp; không trust prefix/username từ request.
- [ ] PGT chỉ server-side; ST/PT/PGT/IOU không lộ trong logs hay browser ngoài quy trình bắt buộc.

**Proxy chain policy**

- [ ] Chọn PT-only hay cho phép direct ST rõ ràng cho từng backend endpoint.
- [ ] Kiểm **mọi hop, đúng số lượng, thứ tự most-recent-first và exact callback identity**.
- [ ] Không bật acceptAnyProxy=true; nếu buộc có ngoại lệ, dokument hóa threat model và expiration.
- [ ] allowedProxyChains được test bằng response thật của CAS, bao gồm reversed/extra/unknown/empty chains.
- [ ] CAS server HTTPS validation response được parse bằng client an toàn, không dùng XML client-supplied.
- [ ] Kiểm user account, role, tenant/resource ACL ngay cả khi chain hợp lệ.

**Spring Security và vận hành**

- [ ] Cas20ProxyTicketValidator tương thích phiên bản CAS Java Client đang dùng; setAllowedProxyChains có policy.
- [ ] CasAuthenticationProvider được nối với AuthenticationManager và CAS filter đúng request scope.
- [ ] Nếu filter custom, có SecurityContextRepository/session fixation protection cho flow stateful.
- [ ] Nếu stateless, ServiceAuthenticationDetailsSource, authenticateAllArtifacts và cache được kiểm chặt.
- [ ] StatelessTicketCache TTL và service/tenant scope có chủ đích; test replay/cache expiry.
- [ ] Multi-node proxy PGT storage và CAS callback có HA/TTL/ACL.
- [ ] TLS, proxy, hostname, service IDs và clock được theo dõi.
- [ ] Negative tests CAS validation, chain, service binding và local authorization đều có.

## 18. Câu hỏi ôn tập

**Câu 1.** Backend C nhận PT-C và một danh sách [B,A]. Có được tin ngay vì thấy cả hai proxy trong allowlist?  
**Đáp án:** Chưa. C phải gọi CAS /proxyValidate đúng **service C** rồi so **toàn bộ chuỗi đúng thứ tự** với policy, sau đó kiểm quyền user/resource.

**Câu 2.** CAS trả [B,A]. Người dùng đã đi qua A trước B, vậy CAS có đảo sai không?  
**Đáp án:** Không. CAS Protocol quy định **proxy mới nhất xuất hiện đầu tiên**; với A→B→C, danh sách tại C là [B,A].

**Câu 3.** PGTIOU trong cas:proxyGrantingTicket có thể dùng làm tham số pgt cho CAS /proxy không?  
**Đáp án:** Không. PGTIOU chỉ là IOU tương quan. **PGT thật** được gửi qua HTTPS proxy callback và phải đối chiếu IOU.

**Câu 4.** PT đã được CAS phát cho Backend B, có thể dùng lại ở Backend C nếu C cùng company không?  
**Đáp án:** Không. PT ràng buộc **targetService**. C phải từ chối **INVALID_SERVICE**, trừ khi CAS phát ticket mới đúng service C.

**Câu 5.** Vì sao /serviceValidate không thay /proxyValidate khi dùng PT?  
**Đáp án:** CAS 2.0 yêu cầu /serviceValidate **không xác minh PT thành công**, còn /proxyValidate hỗ trợ cả ST/PT và proxy history.

**Câu 6.** [B,X] có thể pass vì B là proxy tin cậy và X không trực tiếp gọi C?  
**Đáp án:** Không nếu policy yêu cầu [B,A]. **Toàn bộ delegation chain** phải đúng.

**Câu 7.** Khi nào empty cas:proxies có thể hợp lệ?  
**Đáp án:** Có thể với direct ST ở endpoint cho phép direct login. Nhưng PT-only delegated endpoint cần deny empty chain.

**Câu 8.** Bật acceptAnyProxy=true có an toàn nếu CAS ticket thật không?  
**Đáp án:** CAS xác thực PT thật nhưng backend vẫn cần policy **proxy nào được phép đại diện user**. acceptAnyProxy=true bỏ bảo vệ chuỗi, không phù hợp mặc định với hệ thống nhạy cảm.

**Câu 9.** StatelesTicketCache cho phép cùng PT đăng nhập lần nữa là CAS server tái xác minh PT?  
**Đáp án:** Không. Cache Spring tái sử dụng kết quả thành công của lần validation trước; ticket ở CAS vẫn one-time.

**Câu 10.** CAS xác minh PT và full chain đúng, tại sao backend vẫn phải kiểm role/tenant?  
**Đáp án:** Ticket và proxy chain là **delegated authentication**, không phải authorization trên mọi API/tổ chức/tài nguyên.

## 19. Tài liệu chuẩn và API

1. [Apereo CAS — CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html), đặc biệt **2.5.4 proxy callback**, **2.6 /proxyValidate**, **2.7 /proxy**, **3.3 PGT** và **3.4 PGTIOU**. Đối chiếu CAS version của tổ chức vì tài liệu nhánh development có thể đổi.
2. [Apereo CAS — CAS 2.0 Protocol tại tài liệu Jasig](https://jasigcas.readthedocs.io/en/latest/cas-server-documentation/protocol/CAS-Protocol-V2-Specification.html): yêu cầu service, validate ST/PT, XML <cas:proxies> và quy tắc thứ tự proxy.
3. [Spring Security — CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): proxy grant, CasAuthenticationFilter, CasAuthenticationProvider, ServiceAuthenticationDetailsSource và StatelessTicketCache. Tài liệu current có thể thuộc Spring Security 7; dùng API Javadoc 6.x cho ví dụ 6.x.
4. [Spring Security 6.3 — CasAuthenticationFilter Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.0-RC1/api/org/springframework/security/cas/web/CasAuthenticationFilter.html): process ST/PT, proxy receptor, serviceDetails, authenticateAllArtifacts.
5. [Spring Security 6.5 — CAS authentication package](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/cas/authentication/package-summary.html): CasAuthenticationProvider và StatelessTicketCache.
6. [Apereo Java CAS Client](https://github.com/apereo/java-cas-client): Cas20ProxyTicketValidator, Cas20ProxyReceivingTicketValidationFilter, acceptAnyProxy, allowedProxyChains, pgtUrl và storage.
7. [CAS Java Client Javadoc (nhánh Jasig 3.6.4) — Cas20ProxyTicketValidator](https://javadoc.io/static/org.jasig.cas.client/cas-client-core/3.6.4/org/jasig/cas/client/validation/Cas20ProxyTicketValidator.html): setAcceptAnyProxy, setAllowedProxyChains, setAllowEmptyProxyChain; package khác so với Apereo mới, phải kiểm API project thực.
8. [Spring Security — ServiceProperties Javadoc](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/cas/ServiceProperties.html): authenticateAllArtifacts, service và sendRenew.

**Tóm tắt:** Backend nhận **CAS Proxy Ticket** phải **validate ticket với CAS /proxyValidate cho đúng service**, rồi **đối chiếu toàn bộ cas:proxies theo đúng thứ tự most-recent-first** với **allowlist nguyên chuỗi**; sau cùng vẫn phải kiểm **local user/role/tenant/resource authorization**. **PGT được gửi riêng qua callback HTTPS và ghép bằng PGTIOU**, còn **StatelessTicketCache không biến PT ở CAS thành ticket tái sử dụng**.
