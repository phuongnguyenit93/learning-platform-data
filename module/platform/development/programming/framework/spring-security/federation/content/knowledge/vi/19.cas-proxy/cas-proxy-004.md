# Liên kết PGT IOU với Proxy Granting Ticket tại ứng dụng

## 1. Vấn đề trong CAS Proxy

Trong **Spring Security - federation**, nhóm **CAS Proxy**, một ứng dụng web đã đăng nhập người dùng qua Central Authentication Service (CAS) có thể cần gọi một API phía sau **thay mặt** người dùng đó. Khi ấy, service ticket (ST) dùng cho đăng nhập vào ứng dụng không thể được tái sử dụng để xác thực với API: ST được cấp cho đúng service và chỉ có hiệu lực trong một lần validation. CAS hỗ trợ **proxy-granting ticket (PGT)** để ứng dụng trung gian xin **proxy ticket (PT)** mới dành riêng cho backend.

Theo cơ chế callback chuẩn, CAS Server **không gửi PGT thật trực tiếp trong kết quả xác minh ST**. Thay vào đó:

- CAS Server gửi **PGT thật** (`pgtId=PGT-...`) và **PGT IOU** (`pgtIou=PGTIOU-...`) đến endpoint HTTPS `pgtUrl` của ứng dụng.
- Trong response từ `/serviceValidate` hoặc `/proxyValidate`, CAS Server chỉ trả **`<cas:proxyGrantingTicket>PGTIOU-...</cas:proxyGrantingTicket>`**.
- Ứng dụng lấy **PGT IOU từ kết quả validation đã xác minh**, tra **đúng PGT thật** đã được callback lưu, rồi ràng buộc PGT với CAS Assertion/principal tương ứng.

**PGT IOU là khóa tương quan, không phải credential dùng với CAS `/proxy`. PGT là bearer credential nhạy cảm và có thể được dùng để xin nhiều PT trong vòng đời cho phép.** Không nhầm việc tiêu thụ mapping IOU một lần với việc PGT chỉ được dùng một lần.

Nếu ứng dụng chỉ lưu một biến `latestPgt` hoặc tìm PGT theo username, hai luồng CAS đồng thời có thể ghép nhầm người dùng. Nếu callback đi vào pod A nhưng validator ở pod B, kho in-memory cục bộ có thể khiến IOU tra không thấy PGT. Nếu để lộ `pgtId` qua logs hoặc browser, kẻ có credential có thể xin PT tới các target services được phép.

**Mục tiêu bài:** hiểu hai kênh dữ liệu, lựa chọn và nối `ProxyGrantingTicketStorage`, kiểm tra ranh giới trust ở callback, xử lý race/TTL/multi-node và triển khai tích hợp CAS Proxy an toàn trong Spring Security.

## 2. Phân biệt các ticket và phiên

| Đối tượng | Chủ thể giữ | Chức năng | Hiệu lực và điểm cần nhớ |
| --- | --- | --- | --- |
| **TGT** – Ticket Granting Ticket | CAS Server, có liên hệ cookie SSO của CAS | Duy trì SSO, là cơ sở cấp ticket. | Không truyền TGT cho một service backend. |
| **ST** – Service Ticket | Browser mang tới ứng dụng A; A validate với CAS | Xác thực một login cho **service A**. | Có service binding và chỉ một lần validation. |
| **PGT** – Proxy-Granting Ticket | Ứng dụng A proxy | Xin một hay nhiều **PT** tại CAS `/proxy`. | Bí mật nhiều quyền hơn PT; phải có lifecycle/revocation. |
| **PGT IOU** | CAS callback và validation response | Ghép đúng PGT với kết quả xác minh ST/PT. | Không tự chứng minh danh tính, không dùng để gọi `/proxy`. |
| **PT** – Proxy Ticket | A gửi cho backend B | Chứng minh một lời gọi backend B theo CAS Proxy. | Dành đúng `targetService=B`; một lần validation. |
| **TGC** | Browser và CAS Server | Cookie phiên đăng nhập CAS. | Không phải PGT hoặc Spring session. |
| **`HttpSession`** | Ứng dụng Java/Spring và browser | Duy trì `SecurityContext` của web app. | CAS Server callback không mang cookie browser này. |

**Một luồng đăng nhập có thể có cả ST, PGT IOU, PGT và các PT về sau, nhưng chúng không thay thế nhau.** Tiền tố `PGT-`, `PGTIOU-` chỉ là quy ước định dạng, không phải bằng chứng chữ ký hoặc nguồn tin cậy.

## 3. Hai luồng CAS cần kết hợp

### 3.1. Luồng tổng thể

~~~text
Browser                 Portal A / CAS Client                 CAS Server
   |                             |                                 |
   | GET /login/cas?ticket=ST-1 |                                 |
   |---------------------------->|                                 |
   |                             | HTTPS /serviceValidate           |
   |                             | ticket=ST-1                       |
   |                             | service=https://portal.../login/cas
   |                             | pgtUrl=https://portal.../proxyreceptor
   |                             |-------------------------------->|
   |                             |                                 | validate ST
   |                             |                                 | tạo PGT-1 và PGTIOU-1
   |                             |<------ HTTPS GET pgtUrl --------|
   |                             |        pgtId=PGT-1              |
   |                             |        pgtIou=PGTIOU-1           |
   |                             |                                 |
   |                             | storage.save(PGTIOU-1, PGT-1)    |
   |                             |-------- HTTP 200 -------------->|
   |                             |                                 |
   |                             |<----- validation response ------|
   |                             |    cas:user=alice                |
   |                             |    proxyGrantingTicket=PGTIOU-1 |
   |                             |                                 |
   |                             | storage.retrieve(PGTIOU-1)       |
   |                             |   -> PGT-1                       |
   |                             | CAS Assertion alice + PGT-1     |
   |<--- app session ------------|                                 |
   |                             |                                 |
   |     Khi app cần API B:       |                                 |
   |                             | GET /proxy?pgt=PGT-1             |
   |                             |     &targetService=API-B         |
   |                             |-------------------------------->|
   |                             |<---------- PT-for-B ------------|
   |                             |                                 |
   |                             | --- PT-for-B ---> API B           |
   |                             |          API B validates PT with CAS
~~~

**Thứ tự quan trọng:** theo **CAS Protocol §2.5.4**, CAS Server gọi callback và chờ HTTP 200 trước khi trả validation response **có chứa PGT IOU**. Vì vậy trong luồng đồng bộ chuẩn, callback không “đến sau” validation response theo quy tắc giao thức. Tuy nhiên, trong phần mềm nhiều node, **ghi Redis chưa nhất quán, xử lý bất đồng bộ, timeout hoặc retry** có thể làm thành phần đọc IOU không thấy PGT vừa được callback ACK. Thiết kế cần bảo đảm read-after-write, không dựa vào delay tùy ý.

### 3.2. CAS Server xin PGT thế nào?

Trong yêu cầu validation, client gửi đúng các tham số:

~~~http
GET /cas/serviceValidate?service=https%3A%2F%2Fportal.example.org%2Flogin%2Fcas&ticket=ST-1-example&pgtUrl=https%3A%2F%2Fportal.example.org%2Flogin%2Fcas%2Fproxyreceptor HTTP/1.1
Host: sso.example.org
Accept: application/xml
~~~

Đây là minh họa: CAS Server xác minh ticket một lần, `service` chính xác và `pgtUrl` là callback **HTTPS** mà server cho phép. Nếu chạy giao thức CAS 3.0 có attributes, endpoint có thể là `/p3/serviceValidate`. Nếu cần nhận PT và validation proxy chain, dùng `/proxyValidate` hoặc `/p3/proxyValidate` tương ứng CAS client/server.

`pgtUrl` là **URL server-side cấu hình**, không phải giá trị browser có thể gửi tùy ý. CAS Server kiểm tra chứng thư của callback endpoint (ít nhất PKIX/hostname/certificate trust) và khả năng kết nối trước khi trao PGT.

### 3.3. Callback nhận PGT thật

CAS Server gửi một HTTPS GET về callback:

~~~http
GET /login/cas/proxyreceptor?pgtId=PGT-1-example&pgtIou=PGTIOU-1-example HTTP/1.1
Host: portal.example.org
~~~

Ứng dụng nhận hai tham số phân biệt:

- **`pgtId`**: PGT thật, là credential bí mật.
- **`pgtIou`**: khóa tương quan khó đoán do CAS phát, không cho phép suy ra PGT.

Chỉ sau khi đã bảo vệ nguồn kết nối theo security architecture và **lưu cặp IOU → PGT thành công**, callback mới trả **HTTP 200**. Không trả giá trị PGT trong response body hoặc redirect đến browser. Nếu ghi storage lỗi, không được ACK 200 trước rồi “để background ghi sau” — CAS có thể tưởng rằng callback đã thành công.

**Phân biệt hai chiều TLS:** CAS Server xác minh HTTPS certificate của callback để biết giao PGT cho đúng ứng dụng, nhưng **server certificate của ứng dụng không tự xác thực danh tính của phía gọi vào receptor**. Để chống callback injection, endpoint cần biện pháp inbound trust tương ứng, ví dụ mTLS (khi phù hợp) hoặc kiểm soát nguồn kết nối/gateway nghiêm ngặt, cùng rate limiting và xử lý input an toàn. Không tin một header `X-CAS-Server` do client tùy ý đặt.

### 3.4. Validation response chỉ đưa PGT IOU

CAS có thể trả:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
    <cas:proxyGrantingTicket>PGTIOU-1-example</cas:proxyGrantingTicket>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

Ứng dụng lấy **IOU trong XML response từ CAS Server đáng tin**, tra `storage.retrieve("PGTIOU-1-example")` và nhận `PGT-1-example`. **Không gửi PGT IOU đến CAS `/proxy` thay cho PGT thật**. Không lấy `cas:user` từ callback vì callback chỉ mang PGT và IOU.

Nếu CAS không phát `proxyGrantingTicket`, không có cơ sở xác nhận PGT cho lần validation đó. Nguyên nhân có thể là callback unreachable, certificate fail, receptor không trả 200, server không cho proxy, cấu hình sai hoặc CAS Server đang dùng một profile khác. **Không fallback lấy PGT của phiên trước**.

## 4. Vì sao PGT IOU là mấu chốt bảo mật?

Giả sử hai request ST được xác minh gần cùng lúc:

~~~text
Ticket ST-A -> CAS user alice -> CAS tạo PGT-A / PGTIOU-A
Ticket ST-B -> CAS user bob   -> CAS tạo PGT-B / PGTIOU-B

CAS callbacks:
  (PGTIOU-B, PGT-B) tới trước
  (PGTIOU-A, PGT-A) tới sau

CAS validation responses:
  ST-A -> user alice + PGTIOU-A
  ST-B -> user bob   + PGTIOU-B

Kết quả đúng:
  Alice chỉ được gắn PGT-A
  Bob   chỉ được gắn PGT-B
~~~

Một thuật toán sai:

~~~text
latestPgt = PGT-B
login(alice) -> attach latestPgt
~~~

sẽ dẫn đến **ủy quyền thay mặt Bob nhưng phiên ứng dụng mang danh Alice**. Thậm chí hai trình duyệt đăng nhập cùng username vẫn không đảm bảo PGT có thể dùng thay nhau, vì có thể khác CAS session, quyền và service context.

**Bất biến ghép nối:**
1. Không ghép bằng username, email, session ID hoặc timestamp gần nhất.
2. Chỉ nhận IOU từ **trusted CAS ticket validation response**.
3. Chỉ dùng PGT được receptor lưu với **chính IOU đó**, trong namespace CAS/environment/service tương ứng.
4. Ghép một lần và gắn vào **đúng CAS Assertion**.
5. Khi IOU không thấy, expired, bị trùng/conflict hoặc storage outage, **không cấp proxy capability**.
6. Không đồng nhất “CAS login success” với “PGT acquisition success”; application policy có thể tách hai outcome.

## 5. ProxyGrantingTicketStorage của Apereo Java CAS Client

Trong Java CAS Client, interface **`org.apereo.cas.client.proxy.ProxyGrantingTicketStorage`** cung cấp hợp đồng lưu PGT tạm theo IOU. Những thao tác được dùng là:

~~~java
void save(String proxyGrantingTicketIou,
          String proxyGrantingTicket);

String retrieve(String proxyGrantingTicketIou);

void cleanUp();
~~~

Đây là **chữ ký API minh họa từ thư viện**, không phải một class độc lập chạy bằng JDK. Khi sử dụng Spring Security CAS, phần nhận callback của `CasAuthenticationFilter` lưu PGT, còn `Cas20ProxyTicketValidator` hoặc `Cas30ProxyTicketValidator` truy xuất PGT khi đọc kết quả CAS validation.

| API | Mục đích | Điều phải giữ |
| --- | --- | --- |
| `save(iou,pgt)` | Ghi cặp khi receptor nhận callback. | Một IOU không được ghi đè bởi PGT khác. |
| `retrieve(iou)` | Tra PGT mà CAS Server đã liên kết với IOU trong response. | Lấy đúng một lần theo chính sách storage. |
| `cleanUp()` | Dọn các record orphan/hết hạn. | Không để PGT chưa tiêu thụ trong RAM/Redis vô hạn. |

**Implementation `ProxyGrantingTicketStorageImpl` lịch sử có tính chất retrieve-and-remove:** gọi `retrieve` **xóa mapping tạm** sau khi trả PGT. Đây là single-use của **lookup IOU**, **không** phải single-use của bản thân PGT. Theo CAS Protocol, một PGT có thể xin nhiều PT đến khi bị CAS Server thu hồi/hết hạn.

### 5.1. Storage tạm khác storage của PGT đã gắn vào phiên

Tại callback:

~~~text
Temporary:
  PGTIOU-1 -> PGT-1
~~~

Sau trusted validation:

~~~text
CAS Assertion:
  principal = alice
  verified ST/service = ST-A / Portal
  proxy capability uses PGT-1

Temporary IOU mapping:
  removed
~~~

PGT sau khi ghép cần được bảo vệ theo lifecycle của **đúng principal/CAS Assertion**. Với API Spring/Apereo CAS Client được cấu hình đúng, lớp principal/assertion có thể hỗ trợ `getProxyTicketFor(targetService)` để xin PT, thay vì ứng dụng tự chuyển PGT sang frontend.

Không lưu PGT trong `localStorage`, không đưa vào JSON trả browser, không serialise raw secret vào audit hoặc cho mọi service đọc shared Redis PGT. Khi dùng persistence, mã hóa at rest và giới hạn quyền đọc.

### 5.2. Callback có thể tới khi chưa có local session

CAS Server gọi backend receptor, không mang **browser `JSESSIONID`**. Vì vậy không được viết:

~~~text
GET /proxyreceptor?pgtId=PGT-1&pgtIou=PGTIOU-1
  -> request.getSession().getAttribute("currentUser")
  -> lưu PGT theo currentUser
~~~

Cách này thiếu session hoặc dùng session sai, vì không có browser request context. **IOU giải quyết chính vấn đề ghép hai đường server-side độc lập.** Receptor chỉ lưu cặp tạm; không tạo `Authentication`, `SecurityContext`, cookie hay đăng nhập người dùng.

## 6. Cấu hình Spring Security: dùng cùng một kho

Các thành phần cần được nối đúng:

- `CasAuthenticationEntryPoint`: chuyển browser tới CAS login cùng service URL.
- `ServiceProperties`: định nghĩa **service callback URL** (thường `https://portal.example.org/login/cas`).
- `CasAuthenticationFilter`: nhận ST từ browser và callback PGT từ CAS Server tại `proxyReceptorUrl`.
- `CasAuthenticationProvider`: xác minh ST qua `TicketValidator`, ánh xạ CAS user sang local account.
- `Cas20ProxyTicketValidator` hoặc `Cas30ProxyTicketValidator`: cấu hình **`proxyCallbackUrl`** và **`proxyGrantingTicketStorage`**.
- `ProxyGrantingTicketStorage`: **cùng một logical store** cho filter và validator.

### 6.1. Ba URL không được lẫn nhau

| Tên | URL minh họa | Vai trò |
| --- | --- | --- |
| CAS Server base URL | `https://sso.example.org/cas` | Validator gọi `/serviceValidate` hoặc `/proxyValidate`. |
| `ServiceProperties.service` | `https://portal.example.org/login/cas` | Callback browser mang ST; URL được CAS ràng buộc với ST. |
| `proxyCallbackUrl` | `https://portal.example.org/login/cas/proxyreceptor` | **CAS Server** gửi PGT + IOU qua HTTPS. |

**`proxyReceptorUrl`** ở filter thường là path nội bộ như `/login/cas/proxyreceptor`, còn **`proxyCallbackUrl`** là URL HTTPS hoàn chỉnh mà CAS Server truy cập được. Khi ứng dụng có context path `/portal`, callback full URL cần bao gồm context path đúng, trong khi filter receptor path còn phụ thuộc cấu hình mapping. Kiểm tra ingress/reverse proxy và service registry theo môi trường.

### 6.2. Cấu hình Java Configuration minh họa

Trong một **dự án Spring Boot Servlet** có `spring-security-cas` và `cas-client-core` phù hợp phiên bản, các bean tập trung vào PGT storage có thể được tổ chức như sau:

~~~java
package example.cas;

import org.apereo.cas.client.proxy.ProxyGrantingTicketStorage;
import org.apereo.cas.client.proxy.ProxyGrantingTicketStorageImpl;
import org.apereo.cas.client.validation.Cas20ProxyTicketValidator;
import org.apereo.cas.client.validation.TicketValidator;
import org.springframework.authentication.AuthenticationManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.cas.web.CasAuthenticationFilter;

@Configuration
public class CasPgtConfiguration {

    @Bean
    ProxyGrantingTicketStorage pgtStorage() {
        return new ProxyGrantingTicketStorageImpl();
    }

    @Bean
    TicketValidator ticketValidator(
            ProxyGrantingTicketStorage pgtStorage) {

        Cas20ProxyTicketValidator validator =
            new Cas20ProxyTicketValidator(
                "https://sso.example.org/cas");
        validator.setProxyCallbackUrl(
            "https://portal.example.org/login/cas/proxyreceptor");
        validator.setProxyGrantingTicketStorage(pgtStorage);
        return validator;
    }

    @Bean
    CasAuthenticationFilter casAuthenticationFilter(
            AuthenticationManager manager,
            ProxyGrantingTicketStorage pgtStorage) {

        CasAuthenticationFilter filter = new CasAuthenticationFilter();
        filter.setAuthenticationManager(manager);
        filter.setProxyReceptorUrl("/login/cas/proxyreceptor");
        filter.setProxyGrantingTicketStorage(pgtStorage);
        return filter;
    }
}
~~~

Đây là **một phần cấu hình Spring** chứ **không phải ứng dụng hoàn chỉnh có thể `javac`**. Cần bổ sung `CasAuthenticationProvider`, `ServiceProperties`, `CasAuthenticationEntryPoint`, `AuthenticationManager`, đăng ký filter trong đúng `SecurityFilterChain`, local `UserDetailsService`, CAS service registry và TLS. Ví dụ in-memory storage chỉ phù hợp thử nghiệm một node; production có nhiều node nên cung cấp implementation dùng shared storage.

**Lưu ý import:** Trong các release hiện hành, `AuthenticationManager` của Spring Security nằm ở package **`org.springframework.security.authentication.AuthenticationManager`**, không phải `org.springframework.authentication`. Khi đưa đoạn ví dụ vào dự án, phải dùng import chuẩn của dependency thực tế, và xác minh các setter của module CAS theo phiên bản. Vì đây là mảnh cấu hình minh họa, cần chạy compilation/integration tests trong dự án thật.

Tất cả đường nhận callback và đường xác minh ticket phải dùng **cùng bean `pgtStorage`**. Nếu hai bean tạo hai instance khác nhau, `save` và `retrieve` không gặp nhau, dù cả hai đều chạy trong một JVM.

### 6.3. Provider và service URL vẫn cần thiết

Mô hình:

~~~text
CasAuthenticationProvider:
  ticketValidator -> proxy-aware validator
  serviceProperties.service -> https://portal.example.org/login/cas
  userDetailsService / account mapper -> local user
  key -> stable provider identity

CasAuthenticationFilter:
  browser ST callback -> /login/cas
  CAS PGT receptor -> /login/cas/proxyreceptor
  proxyGrantingTicketStorage -> shared store

CAS TicketValidator:
  CAS base URL -> https://sso.example.org/cas
  proxyCallbackUrl -> HTTPS callback full URL
  proxyGrantingTicketStorage -> same shared store
~~~

`CasAuthenticationProvider#setKey` không phải bí mật ký ticket. Bảo mật vẫn phụ thuộc CAS Server ticket validation, TLS, service binding, PGT storage và local authorization.

### 6.4. Service validator hay proxy validator?

Nếu ứng dụng **chỉ đăng nhập web**, không cần PGT, `Cas20ServiceTicketValidator` hoặc `Cas30ServiceTicketValidator` thường đủ. Nếu cần được CAS cấp PGT để proxy, tài liệu Spring Security hướng dẫn dùng `Cas20ProxyTicketValidator` với `proxyCallbackUrl` và shared storage; với CAS3 attributes và proxy protocol có thể xét `Cas30ProxyTicketValidator` khi được hỗ trợ.

**Cần phân biệt:** ứng dụng A **nhận PGT để đi gọi B** với việc ứng dụng B **nhận proxy ticket và xét proxy chain**. Backend B phải dùng đúng CAS `/proxyValidate`/`/p3/proxyValidate` và **chỉ chấp nhận proxy chain cho phép**, không bật `acceptAnyProxy=true` chỉ để “cho qua lỗi”.

## 7. Từ PGT đã ghép tới proxy ticket của backend B

Sau khi provider xác thực và gắn PGT vào CAS Assertion, ứng dụng A có thể xin PT cho service B. Tài liệu Spring Security minh họa mô hình:

~~~java
// Mảnh code trong handler có CAS Authentication đã xác thực.
CasAuthenticationToken authentication =
    (CasAuthenticationToken)
        SecurityContextHolder.getContext().getAuthentication();

String targetService = "https://reports.example.org/api/report";
String pt = authentication.getAssertion()
        .getPrincipal()
        .getProxyTicketFor(targetService);
~~~

Đây là **mảnh Java trong dự án Spring**, không phải Java SE độc lập. Phải có CAS principal/Assertion được tích hợp proxy capability đúng; khi IOU bị thiếu hoặc PGT không còn hợp lệ, lời gọi xin PT không thể được xem là thành công mặc định.

Giao dịch CAS proxy:

~~~http
GET /cas/proxy?pgt=PGT-1-example&targetService=https%3A%2F%2Freports.example.org%2Fapi%2Freport HTTP/1.1
Host: sso.example.org
~~~

CAS trả PT dành đúng service B; A gửi PT đến B, B gọi CAS proxy validation để kiểm tra PT/service/proxy chain trước khi cho vào API. **Không đưa trực tiếp PGT vào API B**, không sử dụng ST cũ dành cho A, và không dùng PT đã validate lặp lại: PT là một validation attempt. Vì protocol CAS có thể đặt PGT vào query của `/proxy`, bắt buộc redaction ticket ở reverse proxy, server access logs và APM.

Ngay cả khi backend nhận PT hợp lệ, backend vẫn phải kiểm tra tenant, resource ownership, action permission và tài khoản bị khóa. **Proxy authentication không thay authorization**.

## 8. Race condition và multi-node

### 8.1. Những lỗi hiếm có thể gây sự cố lớn

| Tình huống | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Receptor Node A trả 200, validator Node B lookup IOU không thấy. | Shared store chưa có, dùng HashMap cục bộ, replication lag. | Một storage dùng chung, read-after-write, ACK sau commit. |
| Hai callback cùng IOU nhưng khác PGT. | Retry bất thường, lỗi cấu hình, injection. | Reject conflict, không ghi đè mapping. |
| Validation response đến rồi retry ST validation. | ST đã tiêu thụ, retry không đúng giao thức. | Bắt đầu login/validation mới theo policy, không tái dùng ST. |
| Callback PGT orphan (không bao giờ được retrieve). | Validation timeout/crash, restart, drop response. | TTL và cleanup, audit/số lượng orphan. |
| Receptor yêu cầu browser session. | CAS backend không có cookie browser. | Lưu tạm theo IOU, gắn principal sau ticket validation. |
| Multi-user cùng username nhưng khác ticket. | Lưu PGT theo username. | Chỉ ghép bằng IOU, không dùng “PGT mới nhất”. |
| Callback bị scanner gọi với dữ liệu giả. | Endpoint không bảo vệ inbound trust. | mTLS/gateway policy, chống injection, rate limit và kiểm tra input. |
| Kho Redis/SQL timeout. | Không thể chứng minh IOU có PGT. | **Fail closed** cho proxy capability, không lấy PGT cũ. |
| Phiên local bị khóa sau khi PGT đã cấp. | PGT có lifetime khác local session. | Revocation/check status và CAS logout integration. |

### 8.2. Vì sao ACK chỉ sau khi lưu thành công?

~~~text
CAS Server -> GET receptor tới Node A
Node A -> enqueue write Redis rồi trả 200 ngay
CAS Server -> validation XML có PGTIOU gửi về Node B
Node B -> Redis GET PGTIOU -> MISS
~~~

Đó là “ACK trước, durability sau”. Không sửa bằng `Thread.sleep` cố định. Receptor phải trả 200 **sau khi** storage đáp ứng độ bền và tính nhất quán cần thiết, hoặc trả lỗi khi không bảo đảm. CAS Server có thể từ chối PGT issuance nếu callback không đáp ứng; đây là hành vi an toàn hơn phát credential không gắn được chủ thể.

### 8.3. Kho tạm và kho PGT đã gắn có vòng đời khác

| Kho | Key | TTL | Trách nhiệm |
| --- | --- | --- | --- |
| Callback mapping tạm | Namespace + **PGT IOU** | Ngắn, phục vụ giao dịch validation | `save`, `retrieve-and-remove`, cleanup orphan. |
| PGT gắn CAS Assertion | Principal/session/account ref có chứng cứ | Theo CAS session/PGT lifetime và ứng dụng | Chỉ cấp PT cho targets được phép, revoke khi cần. |
| PT gọi Backend B | Target service B | Rất ngắn, single validation | Backend validate với CAS và kiểm tra proxy chain. |

Một PGT có thể tồn tại lâu hơn mapping IOU sau khi `retrieve` thành công, nhưng không được vượt qua chính sách CAS Server/ứng dụng. Đặc biệt, **CAS logout hoặc hủy TGT thường kéo theo hết hiệu lực PGT** theo giao thức; ứng dụng nên chủ động thu hồi/không sử dụng proxy capability khi local account bị disabled.

## 9. Java 17 runnable: ghép hai nửa bằng IOU, chặn trùng và TTL

Chương trình tự biên dịch bằng **Java 17**, không phụ thuộc Spring/Apereo. Nó chỉ mô phỏng hai luồng đến **sau khi** dữ liệu callback và CAS validation đã được kiểm tra ở các tầng tin cậy. Demo **không xác minh chữ ký, ticket, TLS hoặc danh tính caller**, không triển khai Redis và không được dùng trực tiếp làm controller public.

Tệp `PgtIouJoinDemo.java`:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class PgtIouJoinDemo {
    record Callback(String pgt, Instant when) {}
    record Validation(String principal, String service, Instant when) {}
    record Bound(String principal, String service, String pgt) {}

    static final class Store {
        private final Map<String, Callback> callbacks = new HashMap<>();
        private final Map<String, Validation> validations = new HashMap<>();
        private final Set<String> consumed = new HashSet<>();
        private final Set<String> blocked = new HashSet<>();
        private final Duration ttl = Duration.ofSeconds(60);

        // Caller phải xác minh nguồn CAS callback trước phương thức này.
        synchronized String callback(String iou, String pgt, Instant now) {
            if (iou == null || !iou.startsWith("PGTIOU-")
                    || pgt == null || !pgt.startsWith("PGT-")) {
                return "BAD_CALLBACK";
            }
            if (consumed.contains(iou) || blocked.contains(iou)) {
                return "CLOSED";
            }
            Callback old = callbacks.putIfAbsent(iou, new Callback(pgt, now));
            if (old != null) {
                if (!Objects.equals(old.pgt(), pgt)) {
                    blocked.add(iou);
                    callbacks.remove(iou);
                    validations.remove(iou);
                    return "CALLBACK_CONFLICT";
                }
                return "DUPLICATE_CALLBACK";
            }
            return "CALLBACK_STORED";
        }

        // Caller phải xác minh ticket + CAS validation response trước.
        synchronized String validated(String iou, String principal,
                                      String service, Instant now) {
            if (iou == null || !iou.startsWith("PGTIOU-")
                    || principal == null || principal.isBlank()
                    || service == null || service.isBlank()) {
                return "BAD_VALIDATION";
            }
            if (consumed.contains(iou) || blocked.contains(iou)) {
                return "CLOSED";
            }
            Validation old = validations.putIfAbsent(
                    iou, new Validation(principal, service, now));
            if (old != null) {
                if (!old.principal().equals(principal)
                        || !old.service().equals(service)) {
                    blocked.add(iou);
                    callbacks.remove(iou);
                    validations.remove(iou);
                }
                return "DUPLICATE_VALIDATION";
            }
            return "VALIDATION_STORED";
        }

        synchronized Bound take(String iou, Instant now) {
            if (consumed.contains(iou) || blocked.contains(iou)) {
                return null;
            }
            Callback callback = callbacks.get(iou);
            Validation validation = validations.get(iou);
            if (callback == null || validation == null) {
                return null;
            }
            boolean expired = now.isBefore(callback.when())
                    || now.isBefore(validation.when())
                    || now.isAfter(callback.when().plus(ttl))
                    || now.isAfter(validation.when().plus(ttl));
            consumed.add(iou);
            callbacks.remove(iou);
            validations.remove(iou);
            if (expired) {
                return null;
            }
            return new Bound(validation.principal(), validation.service(),
                             callback.pgt());
        }
    }

    static String display(Bound bound) {
        // Không in PGT ra log/stdout.
        return bound == null ? "NOT_LINKED" : "LINKED:" + bound.principal();
    }

    public static void main(String[] args) {
        Store store = new Store();
        Instant t = Instant.parse("2026-11-07T03:00:00Z");

        // CAS callback trước validation response (luồng chuẩn).
        System.out.println(store.callback("PGTIOU-A", "PGT-A", t));
        System.out.println(store.validated("PGTIOU-A", "alice",
                "https://portal.example.org/login/cas", t.plusSeconds(1)));
        System.out.println(display(store.take("PGTIOU-A", t.plusSeconds(2))));
        System.out.println(display(store.take("PGTIOU-A", t.plusSeconds(3))));

        // Thành phần xử lý nhìn thấy validation trước callback.
        System.out.println(store.validated("PGTIOU-B", "bob",
                "https://portal.example.org/login/cas", t));
        System.out.println(store.callback(
                "PGTIOU-B", "PGT-B", t.plusSeconds(1)));
        System.out.println(display(store.take("PGTIOU-B", t.plusSeconds(2))));

        // Không có đủ hai nửa hoặc callback quá hạn.
        System.out.println(display(store.take("PGTIOU-UNKNOWN", t)));
        store.callback("PGTIOU-C", "PGT-C", t);
        store.validated("PGTIOU-C", "carol",
                "https://portal.example.org/login/cas", t);
        System.out.println(display(store.take("PGTIOU-C", t.plusSeconds(61))));

        // Hai PGT khác nhau cho cùng IOU: conflict, không ghi đè.
        store.callback("PGTIOU-D", "PGT-D1", t);
        System.out.println(store.callback(
                "PGTIOU-D", "PGT-D2", t.plusSeconds(1)));
        System.out.println(store.validated("PGTIOU-D", "dave",
                "https://portal.example.org/login/cas", t.plusSeconds(2)));
        System.out.println(display(store.take("PGTIOU-D", t.plusSeconds(3))));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac PgtIouJoinDemo.java
java PgtIouJoinDemo
~~~

**Stdout chính xác:**

~~~text
CALLBACK_STORED
VALIDATION_STORED
LINKED:alice
NOT_LINKED
VALIDATION_STORED
CALLBACK_STORED
LINKED:bob
NOT_LINKED
NOT_LINKED
CALLBACK_CONFLICT
CLOSED
NOT_LINKED
~~~

Giải thích: A được ghép đúng PGT của nó và không thể consume IOU lần hai; B mô phỏng hai nguồn xử lý đến ngược thứ tự; IOU lạ/quá hạn không ghép; callback trùng với PGT khác đánh dấu conflict, không gắn PGT tùy tiện cho dave.

**Giới hạn:** `synchronized` chỉ nguyên tử trong một JVM. Production cần `save-if-absent`, TTL và **atomic take** ở Redis/SQL hoặc adapter phù hợp, có namespace theo CAS Server/environment/service, mã hóa PGT at rest, giới hạn cardinality, và kiểm tra nguồn cả hai nửa trước khi join. Demo lưu `consumed/blocked` không dọn định kỳ, nên chỉ phù hợp bài học. Dữ liệu `PGT-` trong code là giá trị giả, không phải credential thật.

## 10. Thiết kế storage dùng chung an toàn

Sơ đồ logical:

~~~text
CAS Server
    |
    +-- callback HTTPS --> Ingress --> Node A
    |                                    |
    |                                    v
    |                              PGT shared store
    |                          IOU -> encrypted PGT + TTL
    |                                    ^
    |                                    |
    +-- validation XML --> Node B -------+
                                         |
                                  atomic retrieve
                                         |
                               CAS Assertion đúng principal
                                         |
                              request PT cho backend được phép
~~~

Các yêu cầu:

1. **Một logical storage cho tất cả pod**: callback trên A và validator trên B vẫn tìm đúng IOU.
2. **ACK 200 sau write bền/đọc được**: tránh Redis replica lag hoặc async write.
3. **Atomic consume**: ví dụ primitive tương đương `GETDEL` của Redis hoặc transaction SQL; không tách `GET` rồi `DEL` không đồng bộ nếu có hai tiến trình tiêu thụ.
4. **Không overwrite duplicate**: IOU có PGT khác là security conflict, ghi audit và refuse.
5. **TTL ngắn của mapping**: callback không được retrieve phải được cleanup; không để orphan vô hạn.
6. **Mã hóa PGT**: AES-GCM/KMS hoặc vault được phân quyền; không đưa raw PGT vào cache key, logs hay queue thông thường.
7. **Namespace**: theo môi trường, CAS issuer/server và service identity; không trộn staging/prod hoặc hai CAS Servers.
8. **Rate limit, input validation**: receptor có thể bị request lạ/DoS; không dựa duy nhất vào tiền tố PGT.
9. **Fail closed** khi store timeout hoặc không chứng minh được IOU match.
10. **Lifecycle**: PGT đã ghép cần được thu hồi/không dùng khi CAS TGT hết hạn/logout, local account disabled hoặc ứng dụng thu hồi proxy permission.
11. **Quan sát**: metrics thời gian callback, count IOU missing/orphan/conflict, tỷ lệ successful association, không ghi secret.
12. **Bảo vệ backup/snapshot**: không để Redis dump hoặc SQL backup trở thành nguồn rò PGT.

Nếu callback bị chặn do Spring authorization hoặc CSRF matcher, cần cấu hình ngoại lệ **đúng endpoint CAS receptor**, đồng thời bảo vệ inbound trust qua gateway/mTLS và tuyệt đối không tắt CSRF toàn ứng dụng web. Callback là request server-to-server; không đưa nó vào luồng form login cần browser session.

## 11. Direct/encrypted PGT là cơ chế khác callback IOU

Một số cấu hình **Apereo CAS Server** hỗ trợ phát **PGT trực tiếp ở validation response** dưới dạng thuộc tính mã hóa theo khóa công khai của service. Khi kích hoạt biến thể đó, có thể **không có PGT IOU hoặc callback `pgtUrl`**. Đây không phải “callback CAS chuẩn tự đổi sang trả PGT” khi storage lỗi.

| Mô hình | Validation response | Callback receptor | Ứng dụng cần gì? |
| --- | --- | --- | --- |
| **CAS Proxy callback chuẩn** | `proxyGrantingTicket=PGTIOU` | GET `pgtId=PGT` + `pgtIou=PGTIOU` | Shared `ProxyGrantingTicketStorage`, lookup theo IOU. |
| **CAS extension direct encrypted PGT** | PGT theo profile/thuộc tính riêng, có thể mã hóa | Không dùng callback IOU | Đúng cấu hình public/private key, decrypt/validation policy hỗ trợ. |

**Không trộn hai profile.** Khi PGTIOU missing, kiểm tra server/client mode trước khi kết luận lỗi. Không tự coi một chuỗi `proxyGrantingTicket` là bearer PGT khi chưa biết profile nào được dùng.

## 12. Lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| CAS login xong nhưng API proxy thất bại. | Không lấy được PGT dù ST hợp lệ; hoặc PT/authorization backend bị từ chối. | Tách login success khỏi proxy capability success. |
| Validation response không có PGTIOU. | `pgtUrl` không gửi, HTTPS/cert lỗi, service registry không cho proxy, callback không trả 200. | Xem kết quả callback và cấu hình CAS không lộ ticket. |
| CAS callback 404. | URL public `proxyCallbackUrl` không tương ứng `proxyReceptorUrl`/context path. | So ingress route và filter mapping. |
| CAS callback 401/403. | Receptor bị yêu cầu browser login/CSRF, hoặc gateway policy sai. | Ngoại lệ đúng path + inbound trust, không mở toàn ứng dụng. |
| Receptor trả 200 nhưng validator không có PGT. | Hai instance storage, multi-node local memory, replication delay, TTL. | Shared store và read-after-write; ACK sau commit. |
| Duplicate IOU thành công với PGT khác. | Overwrite không an toàn. | Reject conflict, atomically preserve/invalidate. |
| ST `INVALID_TICKET`. | ST đã validate, expired hoặc sai CAS Server. | Không retry cùng ST vô hạn. |
| ST `INVALID_SERVICE`. | Service URL khác lúc CAS phát ticket, reverse proxy HTTPS sai. | So `ServiceProperties.service` và CAS registry. |
| Backend PT `INVALID_SERVICE`. | `targetService` khi xin PT không khớp service lúc backend validate. | Chuẩn hóa service ID và kiểm thử end-to-end. |
| Backend PT bị từ chối proxy chain. | Proxy từ service không được phê duyệt. | Xác minh allowlisted proxy chain, không bật acceptAnyProxy bừa bãi. |
| PGT hết hiệu lực khi gọi `/proxy`. | CAS TGT/logout, PGT expiration/revocation hoặc sai server. | Xin lại qua luồng đúng; không dùng PGT khác. |
| PGTIOU missing chỉ ở một node. | Registry local hoặc shared cache consistency. | Multi-node integration test, common storage. |
| HTTP access logs chứa `pgtId` hoặc `pgt`. | Gateway/APM log raw query string. | Redact và kiểm soát secrets. |
| Receptor bị callback giả. | Không bảo vệ nguồn gọi, only-IOU check. | mTLS/gateway controls, audit, rate limit. |
| Direct encrypted PGT bật nhưng IOU lookup luôn miss. | Đang dùng mode khác. | Kiểm tra profile và CAS Client support. |

### 12.1. Audit và metrics an toàn

Gợi ý:

~~~text
event=CAS_PGT_IOU_CORRELATION
timestamp=2026-11-07T03:00:00Z
cas_server_ref=cas-primary
service_ref=portal
iou_ref=HMAC(PGTIOU)
callback_persisted=true
validation_received=true
result=MATCHED
consumed_once=true
proxy_target_ref=reports-api
~~~

Đây là audit schema minh họa, không phải log chuẩn của Spring Security. **Không ghi raw PGT, IOU, ST/PT, browser cookie, CAS validation response đầy đủ, hoặc tên người dùng nhạy cảm** vào log có nhiều người truy cập. Do CAS truyền PGT trong query của callback/`/proxy`, kiểm soát logs ở reverse proxy, WAF, APM, tracing và backend.

## 13. Bộ test trước production

| Kiểm thử | Expected outcome |
| --- | --- |
| ST hợp lệ + callback URL HTTPS có cert đúng. | CAS callback lưu IOU→PGT và validation response có cùng IOU. |
| Callback A và validation A có cùng IOU. | Lấy đúng PGT-A, gắn vào Assertion A. |
| Callback A nhưng response B có IOU khác. | Không ghép A vào B. |
| Hai người dùng login đồng thời, callbacks đảo thứ tự. | Ghép theo IOU độc lập, không dựa username. |
| Callback đến Node A, validation đến Node B. | Shared store đọc thấy cùng mapping. |
| Callback ACK 200 trước Redis persist thất bại. | Test phát hiện sai contract; không báo success khi chưa lưu. |
| Callback hai PGT khác nhau cùng IOU. | Reject conflict; không overwrite. |
| Callback giống hệt được gửi lại. | Idempotency/replay policy không ghép hai lần. |
| Validator retrieve IOU hai lần. | Chỉ một lần lấy được mapping. |
| IOU quá hạn hoặc không có trong store. | Không cấp PGT, dọn state. |
| CAS Server không tới receptor. | Không có proxy capability, xử lý failure đúng. |
| Certificate callback sai/không HTTPS. | CAS Server không gửi PGT. |
| Gửi callback từ browser/attacker. | Không ghi PGT trái phép hay tạo authenticated session. |
| Gửi ST đã dùng hai lần. | CAS Server từ chối replay. |
| ST dành service A gửi service B. | Wrong-service validation fail. |
| PGT đã bị thu hồi. | CAS `/proxy` không cấp PT. |
| PT cho B dùng tại service C. | CAS proxy validation từ chối target mismatch. |
| PT đi qua proxy chain lạ. | Backend từ chối. |
| Local account locked dù CAS ticket hợp lệ. | Không sử dụng proxy capability để vượt khóa. |
| Storage unavailable. | Fail closed, không fallback PGT “latest”. |
| Server bật direct PGT extension. | Theo đúng variant, không đòi callback IOU. |
| Backend B nhận PT hợp lệ. | Vẫn kiểm tra role, tenant và resource permission. |

**Kiểm thử đơn vị** Java demo chỉ kiểm tra mapping IOU/TTL/replay, không chứng minh HTTPS, CAS Protocol, CAS Server service registration, callback trust, local account mapping hoặc proxy authorization. Phải có integration test với CAS Server test (ST/PGT/PT thật trong test), ứng dụng Spring chạy qua reverse proxy và ít nhất hai node nếu deployment đa node.

## 14. Những lỗi khái niệm cần tránh

1. **PGTIOU chính là PGT** — sai, IOU chỉ tra PGT.
2. **Callback chứa username** — sai, principal từ trusted ticket validation.
3. **Validation response chứa PGT thật trong callback flow chuẩn** — sai, response chứa IOU.
4. **Một IOU chỉ lấy một lần nên PGT cũng không xin PT được lần hai** — sai, PGT có vòng đời khác.
5. **Dùng `JSESSIONID` để ghép callback** — sai, CAS backend không có browser session.
6. **Ghép theo user/email hoặc latest timestamp** — sai, dễ nối sai giao dịch.
7. **Callback đến sau validation response theo CAS spec** — sai với callback flow đồng bộ chuẩn; cần hiểu callback 200 trước IOU response.
8. **Receptor trả 200 trước khi lưu cũng được** — sai, tạo false success.
9. **Bật `acceptAnyProxy=true` là sửa lỗi storage** — sai, mở rộng proxy trust.
10. **Một HashMap mỗi node là shared storage** — sai, multi-node cần backend chung.
11. **PGT có thể gửi vào frontend để lưu session** — sai, PGT là bearer credential.
12. **CAS Server tin chứng thư receptor thì receptor tự tin người gọi** — sai, inbound caller trust là việc riêng.
13. **Thấy tên `PGT-` là credential thật** — sai, phải từ kênh CAS trusted.
14. **Có PGT thì mọi API đều cho phép** — sai, PT target service và backend authorization.
15. **PGT lỗi thì dùng ST cũ validate lại** — sai, ST one-time.
16. **Không có IOU chắc chắn callback lỗi** — chưa chắc, có thể server dùng direct PGT extension.
17. **Local logout chắc chắn CAS TGT/PGT và API session đều đã hủy** — sai, cần lifecycle/revocation được thiết kế rõ.

## 15. Checklist triển khai

1. Có nhu cầu thật để Portal xin PT cho backend và chính sách backend proxy chain không?
2. `ServiceProperties.service` chính xác, cùng URL public HTTPS mà CAS dùng cấp ST không?
3. CAS Server được cấu hình cho proxy, tin HTTPS `pgtUrl`/certificate/hostname không?
4. `proxyReceptorUrl` path và `proxyCallbackUrl` full URL khớp qua ingress/context path không?
5. Validator và filter dùng cùng `ProxyGrantingTicketStorage` logical ở mọi node không?
6. Receptor chỉ ACK 200 sau khi persist IOU→PGT và bảo vệ nguồn gọi chưa?
7. IOU được lấy từ trusted validation result chứ không từ browser query/username không?
8. Lấy PGT bằng IOU một lần, không overwrite duplicate/conflict, có TTL và cleanup không?
9. Shared storage có atomic take/read-after-write và khả năng fail-safe khi lỗi không?
10. PGT thật được giữ bí mật, mã hóa at rest, không ghi logs hoặc trả browser không?
11. PGT sau lookup được gắn vào đúng CAS Assertion/principal, không vào phiên khác không?
12. Có kiểm soát CAS session/PGT lifetime và local account revocation không?
13. Có kiểm tra backend targetService, PT one-time và proxy chain allowlist không?
14. Có integration tests cho callback network/certificate, multi-node, concurrent users, replay và outage không?
15. Nếu CAS dùng direct encrypted PGT, có chọn đúng profile và không trộn với IOU callback không?

## Tài liệu tham khảo

- [Apereo CAS Protocol Specification — §2.5.4 Proxy Callback, §3.3 PGT, §3.4 PGT IOU và §2.7 Proxy Ticket](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html)
- [Spring Security — CAS Authentication, Configuring CAS to Obtain Proxy Granting Tickets](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html)
- [Apereo Java CAS Client — Proxy Receptor và Proxy Granting Ticket Storage](https://github.com/apereo/java-cas-client/blob/master/README.md)
- [Apereo CAS — Proxy Authentication and Direct PGT Variant](https://apereo.github.io/cas/development/authentication/Configuring-Proxy-Authentication.html)
- [Apereo CAS Protocol Overview](https://apereo.github.io/cas/development/protocol/CAS-Protocol.html)
- [Spring Security API — CasAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html)
- [Spring Security API — CasAuthenticationFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html)
