# Giới hạn proxy được tin cậy và tránh chấp nhận mọi proxy trong Spring Security CAS

## 1. Mục tiêu và tình huống

**CAS Proxy Authentication** cho phép một service đã xác thực người dùng tại CAS thay mặt người dùng gọi một service phía sau mà không truyền mật khẩu người dùng. Đây là khả năng hữu ích với portal, gateway, ứng dụng nghiệp vụ gọi backend, nhưng cũng mở thêm một **ranh giới ủy quyền**: backend phải quyết định **đối tác trung gian nào được phép hành động nhân danh người dùng**, chứ không chỉ biết “CAS đã xác thực username”.

Xét hệ thống:

- **Portal**: ứng dụng web tiếp nhận Service Ticket (ST) từ trình duyệt, cần gọi backend thay người dùng.
- **Gateway**: service trung gian có thể tiếp tục ủy nhiệm yêu cầu đến backend.
- **Reports API**: backend nhận **Proxy Ticket (PT)** do CAS phát cho service API của chính nó.
- **CAS Server**: cấp ST, Proxy-Granting Ticket (PGT), PT và xác minh ticket với service URL đích.

Một lỗi cấu hình nguy hiểm là để backend dùng `Cas20ProxyTicketValidator` với **`acceptAnyProxy=true`** hoặc thiết lập `allowedProxyChains` quá rộng. Khi đó, một service lạ trong cùng CAS federation có khả năng sở hữu PGT có thể trở thành nguồn ủy nhiệm được backend chấp nhận, nếu các điều kiện khác cho phép. CAS xác minh ticket **không tự thay backend quyết định tin mọi proxy**.

Sau bài học, bạn cần:

1. Phân biệt **ST, PT, PGT, PGTIOU** và **CAS proxy chain**.
2. Hiểu chuỗi `<cas:proxies>` trong response `/proxyValidate`: **proxy gần nhất đứng trước**, các hop đi trước đứng sau.
3. Biết áp dụng **deny by default**, **allowlist proxy callback URL chính xác**, **toàn bộ chuỗi và thứ tự**, cùng **service target**.
4. Biết vì sao **`acceptAnyProxy=true`** chỉ xuất hiện như ví dụ chức năng trong một số tài liệu cũ, **không phù hợp là mặc định production**.
5. Biết cấu hình `Cas20ProxyTicketValidator`/`allowedProxyChains` và phân biệt cấu hình ở **Spring Security provider**, **Apereo Java CAS Client filter** và **CAS Server service registry**.
6. Biết giới hạn phía CAS Server về **dịch vụ nào được cấp PGT**, **callback HTTPS nào được phép**, và **target service nào PT được cấp cho**.
7. Hiểu rủi ro **StatelessTicketCache**, replay ở cấp ứng dụng, vòng đời PGT và quản lý secret.
8. Có mã Java 17 độc lập minh họa chính sách chain chặt, test các chuỗi hợp lệ và các kiểu tấn công/sai cấu hình.
9. Có checklist, ma trận kiểm thử và phương pháp chẩn đoán không làm lộ ticket.

**Nguyên tắc xuyên suốt:** **CAS Server xác minh tính hợp lệ ticket và cung cấp lịch sử proxy; dịch vụ đích quyết định lịch sử đó có thuộc danh sách được tin và được phép thực hiện thao tác nghiệp vụ hay không.** Hai bước này là **hai điều kiện cùng phải đạt**, không thay thế nhau.

## 2. Ranh giới tin cậy của CAS Proxy

### 2.1. Một luồng ST trực tiếp không có proxy

~~~text
Browser -> CAS /login?service=https://portal.example.test/login/cas
CAS -> Browser: redirect + ST-...
Browser -> Portal /login/cas?ticket=ST-...
Portal -> CAS /serviceValidate?ticket=ST-...&service=<Portal service>
CAS -> Portal: authenticationSuccess(username)
Portal: tạo local Authentication nếu user policy cho phép
~~~

Trong trường hợp này, không cần Proxy Ticket. Portal xác minh ST qua CAS rồi có thể dùng session local. Nếu service không hề cần ủy nhiệm sang backend khác, **không bật chức năng proxy chỉ để đăng nhập CAS**.

### 2.2. Portal được cấp PGT để gọi backend

~~~text
Browser -- ST --> Portal
                   |
                   | /serviceValidate:
                   |   ticket = ST
                   |   service = https://portal.example.test/login/cas
                   |   pgtUrl  = https://portal.example.test/login/cas/proxyreceptor
                   v
                CAS Server
                   |
                   | HTTPS callback đến pgtUrl
                   | ?pgtIou=PGTIOU-...&pgtId=PGT-...
                   v
                Portal proxy receptor / PGT storage
                   |
                   | /serviceValidate response chứa PGTIOU
                   | Portal ghép PGTIOU với PGT đã nhận
                   |
                   | /proxy?pgt=PGT-...&
                   |        targetService=https://reports.example.test/api/cas
                   v
                CAS Server
                   |
                   | cấp PT chỉ cho Reports API target service
                   v
Portal --- PT ---> Reports API
                   |
                   | /proxyValidate:
                   |  service=https://reports.example.test/api/cas
                   |  ticket=PT-...
                   v
                CAS Server
                   |
                   | authenticationSuccess
                   | proxies=[https://portal.example.test/.../proxyreceptor]
                   v
                Reports API
                   |
                   | ĐỐI CHIẾU đầy đủ danh sách proxy được tin
                   | + identity + authorization policy
                   v
                Xử lý nghiệp vụ
~~~

Có **hai bộ lọc quyền khác nhau**:

- CAS Server cho biết Portal có được **cấp PGT/PT** theo **CAS registered-service proxy policy** và tính hợp lệ của callback hay không.
- Reports API quyết định **Portal có phải proxy đáng tin cho API này** không, bằng **proxy chain allowlist**.

Chỉ một trong hai bộ lọc thành công **chưa đủ**. Không nên dùng CAS “đã cấp PT” làm lý do mặc nhiên cho phép bất kỳ proxy nào tại Reports.

### 2.3. Hai hop: Portal → Gateway → Reports

Nếu Portal ủy nhiệm cho Gateway, rồi Gateway lại ủy nhiệm đến Reports:

~~~text
Người dùng
   |
   v
Portal  (proxy hop được dùng trước)
   |
   v
Gateway (proxy hop được dùng gần nhất)
   |
   v
Reports API (service đích)
~~~

Với CAS 2.0/3.0, nếu callback proxy URL của Portal là `P` và Gateway là `G`, response từ `/proxyValidate` ở Reports biểu diễn:

~~~text
cas:proxies = [G, P]
              ^  ^
           gần nhất  đã đi qua trước đó
~~~

**Thứ tự là một phần chính sách**. `[G, P]` không giống `[P, G]`. Đừng đảo thứ tự vì sơ đồ nghiệp vụ được vẽ từ trái sang phải. CAS Protocol quy định proxy **gần nhất đứng đầu**.

## 3. Phân biệt các loại ticket và phạm vi ủy nhiệm

| Artifact | Được cấp cho ai? | Dùng ở đâu? | Giới hạn |
| --- | --- | --- | --- |
| **Service Ticket (ST)** | Người dùng qua CAS cho một service | Browser callback và `/serviceValidate` hoặc validation profile thích hợp | Dành cho **một service**, **một lần validation attempt**, TTL ngắn |
| **Proxy-Granting Ticket (PGT)** | Service đã được CAS chấp thuận proxy | `/proxy` để xin PT | Credential mạnh hơn, có thể cấp **nhiều PT**; cần bảo vệ như secret |
| **PGT IOU (PGTIOU)** | Kênh phản hồi xác minh ticket | Ghép response validation với callback đã mang PGT | Mã correlation, **không phải PGT** |
| **Proxy Ticket (PT)** | Một backend target service cụ thể | Backend chuyển về CAS `/proxyValidate` | Dành cho **một target service**, **một lần validation attempt**, TTL ngắn |
| **TGT/TGC** | Phiên SSO tại CAS/Browser | CAS dùng duy trì login SSO và phát ST | Không được coi là PGT hoặc gửi xuống backend |

Một PT có thể mang prefix `PT-`, nhưng **không được parse tiền tố để quyết định đã có ủy nhiệm đáng tin**. CAS quyết định ticket hợp lệ hay không. **Lịch sử proxy phải đến từ assertion do TicketValidator tạo sau khi gọi CAS Server tin cậy**, không đến từ HTTP header như `X-Proxy-Chain` do client gửi.

### 3.1. Tính one-time vẫn tồn tại ở PT

CAS Protocol quy định **ST và PT chỉ hợp lệ cho một ticket validation attempt**. Dù validation thất bại, CAS phải vô hiệu hóa ticket. Do đó:

- Backend không được gửi lại PT y nguyên sau response `INVALID_TICKET` rồi kỳ vọng CAS cấp lại quyền.
- Nếu service được gọi hai lần, caller thường phải có **PT mới** từ PGT theo luồng đã được cấp phép.
- **PGT khác PT**: PGT có thể dùng để xin nhiều PT, nên PGT cần storage, TTL, audit và khóa quyền rất chặt.
- Nếu Spring cache kết quả PT cho **stateless client**, việc client có thể gửi lại cùng chuỗi cho ứng dụng là **hành vi cache phía Spring**, không phải CAS cấp phép PT sử dụng nhiều lần.

## 4. Proxy chain nằm ở đâu và phải hiểu đúng ra sao?

Một response hợp lệ từ `/proxyValidate` có thể chứa:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>employee-42</cas:user>
    <cas:proxies>
      <cas:proxy>https://gateway.example.test/login/cas/proxyreceptor</cas:proxy>
      <cas:proxy>https://portal.example.test/login/cas/proxyreceptor</cas:proxy>
    </cas:proxies>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

Đây là **mẫu minh họa**. Việc XML chứa `authenticationSuccess` phải được xác nhận bằng **TicketValidator đã gọi đúng CAS Server qua TLS và kiểm service ticket**. Không nhận một XML như thế qua browser rồi tự gán authenticated.

**`cas:proxy` là URL của proxy callback/`pgtUrl` được CAS dùng để nhận diện service trung gian**, không phải tên con người, địa chỉ HTTP forward proxy, IP ingress hay hostname mà backend thấy qua `X-Forwarded-For`.

### 4.1. CAS liệt kê proxy theo thứ tự ngược với hành trình ban đầu

Ví dụ business flow:

~~~text
Portal -> Gateway -> Reports API
~~~

Thứ tự `<cas:proxy>`:

~~~text
1. https://gateway.example.test/login/cas/proxyreceptor
2. https://portal.example.test/login/cas/proxyreceptor
~~~

Nếu backend được phép **chỉ** Portal gọi trực tiếp, allowlist là **[Portal]**, không tự chấp nhận **[Gateway, Portal]**. Nếu backend cho phép Gateway chuyển tiếp từ Portal, khai một **chain riêng** là **[Gateway, Portal]**.

### 4.2. Chuỗi đầy đủ mới là điều cần tin

| Chain CAS đã xác minh | Chính sách của Reports | Quyết định |
| --- | --- | --- |
| `[Portal]` | Chỉ chấp nhận Portal | PASS |
| `[Gateway, Portal]` | Cho phép Gateway sau Portal | PASS |
| `[Gateway]` | Chỉ Gateway trực tiếp được phép | PASS nếu được liệt kê riêng |
| `[Unknown]` | Không có Unknown | FAIL |
| `[Portal, Gateway]` | Chỉ có [Gateway, Portal] | FAIL do sai **thứ tự** |
| `[Gateway, Portal, Unknown]` | Chỉ có hai hop | FAIL do **hop lạ** |
| `[]` | Backend **chỉ nhận PT có proxy** | FAIL |
| `[Portal]` | Backend **chỉ chấp nhận hai hop** | FAIL |
| `[Portal]` với service sai | Chain đúng nhưng ticket phát cho service khác | FAIL |

**Không chỉ hỏi “chuỗi có chứa Portal không?”** Một chain `[attacker, Portal]` vẫn “chứa Portal” nhưng thêm một hop không được duyệt. Tương tự, chỉ so proxy cuối hoặc proxy đầu cũng có thể bỏ qua các hop nguy hiểm nằm giữa.

## 5. Rủi ro của `acceptAnyProxy=true`

Trong một số ví dụ hướng dẫn Spring Security CAS, đoạn cấu hình mở để minh họa **proxy ticket authentication** có:

~~~xml
<!-- CHỈ MINH HỌA CẤU HÌNH RỘNG - KHÔNG DÙNG PROD -->
<bean class="org.apereo.cas.client.validation.Cas20ProxyTicketValidator">
  <constructor-arg value="https://sso.example.test/cas"/>
  <property name="acceptAnyProxy" value="true"/>
</bean>
~~~

**Đây là ví dụ anti-pattern trong sản xuất**, không phải cấu hình khuyến nghị. Tài liệu Apereo Java CAS Client xác nhận `acceptAnyProxy` mặc định **false**, và hỗ trợ `allowedProxyChains` để chỉ định các chain được chấp nhận.

Vì sao nguy hiểm?

1. Một service khác trong CAS federation có thể được CAS cho phép nhận PGT.
2. Service đó có thể xin PT cho backend target service nếu CAS policy cho phép.
3. Backend dùng `acceptAnyProxy=true` có thể bỏ qua việc **ủy nhiệm qua đối tác lạ**.
4. Backend có thể lấy username đã xác minh rồi cấp quyền nghiệp vụ, dù **nguồn ủy nhiệm không thuộc danh sách tin cậy**.
5. Nếu PGT của service trung gian bị lộ, khả năng giả lập ủy nhiệm có thể rộng hơn dự kiến.

**Không có nghĩa `acceptAnyProxy=true` tự tạo ra ticket CAS hợp lệ hoặc vượt qua TLS/target-service validation.** Nó chủ yếu xóa một **lớp kiểm soát quan trọng tại service đích**: kiểm danh tính/lịch sử proxy. Các điều kiện còn lại vẫn có thể chặn, nhưng **security posture đã yếu hơn rõ rệt**.

### 5.1. Không chỉ có boolean đáng sợ

Các cấu hình khác cũng có thể tạo “accept any” trên thực tế:

- `allowedProxyChains` chứa regex `^https://.*`.
- Regex chỉ kiểm `gateway` xuất hiện trong URL bất kể host/phần cuối.
- Chấp nhận `chain.contains(trustedProxy)` thay vì exact full chain.
- Chỉ kiểm hop đầu, bỏ qua các hop còn lại.
- Dùng `startsWith("https://gateway.example.test")` khiến hostname như `gateway.example.test.evil.test` lọt qua nếu không parse đúng URI.
- Tự động thêm mọi proxy vừa xuất hiện trong CAS response vào allowlist.
- Dùng `acceptAnyProxy=false` nhưng code khác tạo một validator/proxy decider mở hoặc cache kết quả từ phiên bản cấu hình cũ.
- CAS server registry cấp PGT cho mọi service hoặc mọi `pgtUrl`, làm tăng nguồn tạo PT.

Một policy an toàn phải được kiểm tra **ở cả backend và CAS Server**.

## 6. Đầu tiên chọn đúng chế độ: không hỗ trợ proxy nếu không cần

Nếu ứng dụng chỉ nhận người dùng bằng browser CAS ST:

~~~text
Browser -> /login/cas?ticket=ST-...
App -> CAS /serviceValidate
App -> SecurityContext/HttpSession
~~~

Hãy ưu tiên:

- Dùng `Cas20ServiceTicketValidator` hoặc validator Service Ticket không chấp nhận Proxy Ticket theo protocol.
- Chỉ xử lý artifact tại `CasAuthenticationFilter.filterProcessesUrl`, thường là `/login/cas`.
- Giữ `ServiceProperties.authenticateAllArtifacts=false` nếu không cần CAS PT trên mọi URL.
- Không cấu hình `pgtUrl`/proxy receptor/PGT store khi không có downstream CAS use case.
- CAS Server **không cấp PGT** cho service này theo registered-service proxy policy.
- Không dùng `/proxyValidate` thay `/serviceValidate` chỉ vì tài liệu mẫu có nhiều tính năng hơn.

Theo CAS Protocol, `/serviceValidate` **không được chấp nhận PT thành công**. Việc backend **không nhận PT** thường an toàn và đơn giản hơn việc nhận PT nhưng “hy vọng proxy sẽ hợp lệ”.

### 6.1. Chế độ nào thực sự cần PT?

Một backend không có browser, cần biết service trung gian nào đã ủy nhiệm người dùng, có thể dùng PT:

~~~text
Portal (đã có CAS Authentication) -> CAS /proxy -> PT cho Reports
Portal -> Reports (PT)
Reports -> CAS /proxyValidate -> assertion + proxy chain
Reports -> kiểm chain + quyền -> trả dữ liệu
~~~

Đây là **delegated authentication**, không có nghĩa Portal tự động được quyền truy cập mọi dữ liệu người dùng. Backend vẫn cần giới hạn người dùng, scopes nghiệp vụ, resource ownership và thao tác được phép.

## 7. Chính sách deny-by-default cho backend nhận PT

Một chính sách rõ ràng gồm **năm câu hỏi độc lập**:

1. **CAS Server nào** được backend tin, URL và TLS certificate/host có được xác thực?
2. **Target service** có đúng service identity mà PT được cấp cho không?
3. **Proxy chain** có đúng từng URL, số hop và thứ tự trong allowlist không?
4. **Người dùng** từ CAS assertion có được backend nhận biết và cho phép không?
5. **Thao tác/ngữ cảnh nghiệp vụ** có được cho phép cho user qua proxy đó không?

### 7.1. Ví dụ allowlist đầy đủ

~~~yaml
# Cấu hình miền nghiệp vụ minh họa; không phải Spring Boot property tự động.
cas-proxy-policy:
  reports-api:
    cas-server: "https://sso.example.test/cas"
    target-service: "https://reports.example.test/api/cas"
    allow-direct-service-ticket: false
    accept-any-proxy: false
    allowed-chains:
      - - "https://gateway.example.test/login/cas/proxyreceptor"
      - - "https://gateway.example.test/login/cas/proxyreceptor"
        - "https://portal.example.test/login/cas/proxyreceptor"
    require-https-proxy-callback: true
    reject-unlisted-hops: true
    max-proxy-hops: 2
~~~

**Đây là policy DSL riêng của ứng dụng để giải thích ý tưởng, không phải schema Spring Security/Apereo built-in.** Nếu dự án sử dụng nó, cần code để chuyển các dòng vào chính sách kiểm chain và cấu hình validator phù hợp. Không thả YAML này vào `application.yml` rồi cho rằng framework đã thực thi.

Các thuộc tính quan trọng:

- `allowed-chains` là **danh sách các chuỗi**, không phải một danh sách gộp “mọi URL được tin”.
- Một chain dài hai phần tử **chỉ** chấp nhận [Gateway, Portal].
- `max-proxy-hops` là lớp kiểm tra chiều sâu bổ sung; **không được** thay allowlist.
- Không tin `require-https-proxy-callback=true` nếu không thật sự kiểm endpoint CAS đã xác minh danh tính callback.
- `allow-direct-service-ticket=false` phù hợp backend chỉ cho phép delegated PT; một backend cũng nhận ST trực tiếp phải có policy rõ cho chain rỗng.

### 7.2. Exact URL và regular expression

Apereo CAS Java Client cho phép mô tả `allowedProxyChains` bằng từng URL chính xác hoặc một số cú pháp **regular expression** theo client/version. Khi có thể, ưu tiên **exact URL**.

Nếu buộc phải dùng regex cho migration nhiều callback URLs, cần:

- Bắt đầu bằng `^` và kết thúc bằng `$`, giới hạn hostname/path/port chính xác.
- Escape dấu chấm trong domain, ví dụ `\.` thay vì `.`.
- Không mở pattern rộng `.*` hoặc optional scheme `https?` nếu HTTPS là yêu cầu.
- Giới hạn độ dài input, số proxy hops và tránh regex backtracking nặng.
- Viết negative tests cho các hostname như `gateway.example.test.evil.test` và path `/proxyreceptor/extra`.
- Kiểm tra cú pháp tạo `ProxyList` thực tế của **phiên bản Apereo client đã dùng**; không đoán Java regex rules tự động áp như nhau với mọi binder.

Ví dụ pattern dùng trong **hệ thống policy của chính bạn**:

~~~regex
^https://gateway\.example\.test/login/cas/proxyreceptor$
~~~

Nếu chỉ có một URL được chấp nhận, **exact string match rõ ràng hơn regex**. Không dùng cách normalize bỏ tùy ý scheme, host, port, slash, query hoặc case; mọi thay đổi URL phải được đối chiếu với cách CAS registry/callback thực tế xác định service.

## 8. Cas20ProxyTicketValidator: cấu hình chain cụ thể

Trong Apereo Java CAS Client, `Cas20ProxyTicketValidator` được tạo với **CAS server URL prefix**, có các phương thức:

~~~java
Cas20ProxyTicketValidator validator =
    new Cas20ProxyTicketValidator("https://sso.example.test/cas");

validator.setAcceptAnyProxy(false);
validator.setAllowEmptyProxyChain(false);
validator.setAllowedProxyChains(approvedProxyList);
~~~

**Đây là snippet API không chạy độc lập**:

- `approvedProxyList` là biến đối tượng **`ProxyList` đã được tạo từ các chain đã được phê duyệt** bằng API/parser của phiên bản CAS Java Client cụ thể, **không phải `List<String>` thông thường**. Trong các Javadoc về `Cas20ProxyTicketValidator`, signature của setter là **`setAllowedProxyChains(ProxyList)`**.
- Import/package của `ProxyList`, cú pháp tạo object và regex parsing cần được xác nhận trên **phiên bản Apereo Java CAS Client thật**.
- `setAllowEmptyProxyChain(false)` phù hợp với **backend chỉ được nhận PT có proxy hợp lệ**. Nếu business cho phép cả ST trực tiếp, cần thiết kế policy riêng cho chain rỗng và kiểm thử rõ.
- `setAcceptAnyProxy(false)` **không tự sinh allowlist**. Phải cấp `approvedProxyList` thực sự, và test cả trường hợp không có match.
- `Cas20ProxyTicketValidator` là **CAS 2.x proxy validation**; CAS 3 attributes có thể cần `Cas30ProxyTicketValidator` tương ứng. Tránh trộn endpoint/format.

Cách viết còn an toàn hơn là **không tạo `Cas20ProxyTicketValidator`** tại các service hoàn toàn không nhận proxy, như đã nêu ở phần 6.

### 8.1. Spring Security CasAuthenticationProvider

Trong Spring Security, `CasAuthenticationProvider` nhận `TicketValidator` mà chính bạn cấu hình. Trích đoạn wiring (các biến khác do bean configuration cấp):

~~~java
Cas20ProxyTicketValidator validator =
    new Cas20ProxyTicketValidator("https://sso.example.test/cas");
validator.setAcceptAnyProxy(false);
validator.setAllowEmptyProxyChain(false);
validator.setAllowedProxyChains(approvedProxyList);

CasAuthenticationProvider provider = new CasAuthenticationProvider();
provider.setKey("reports-cas-provider-v1");
provider.setServiceProperties(serviceProperties);
provider.setTicketValidator(validator);
provider.setUserDetailsService(userDetailsService);
~~~

**Đây là code sketch trong Spring Boot app, không phải Java 17 runnable program.** Cần import Apereo/Spring Security, bean `serviceProperties`, `userDetailsService` và đối tượng `approvedProxyList`. `provider.setKey` là định danh provider nội bộ, **không phải CAS cryptographic key**. Cấu hình cuối cùng phải được kiểm bằng integration tests với CAS Server.

Điều cần tránh:

~~~java
// Khong dung trong production:
validator.setAcceptAnyProxy(true);
~~~

Một số tài liệu Spring Security có ví dụ sử dụng giá trị này để **biểu diễn cách mở tính năng proxy**. Nó không phải khuyến nghị trust policy cho ứng dụng xử lý dữ liệu thật.

### 8.2. CAS Java Client Servlet filters và Spring Security là hai đường cấu hình

Một service có thể dùng **Apereo Java CAS Client filters trực tiếp** hoặc dùng **Spring Security CAS provider/filter**. Với Java Client filters thuần, `Cas20ProxyReceivingTicketValidationFilter` có thể nhận init parameters:

~~~xml
<!-- Fragment web.xml cho APEREO CAS CLIENT FILTER, không tự động
     áp dụng lên Spring Security CasAuthenticationProvider. -->
<filter>
  <filter-name>CAS Validation Filter</filter-name>
  <filter-class>
    org.apereo.cas.client.validation.Cas20ProxyReceivingTicketValidationFilter
  </filter-class>
  <init-param>
    <param-name>casServerUrlPrefix</param-name>
    <param-value>https://sso.example.test/cas</param-value>
  </init-param>
  <init-param>
    <param-name>acceptAnyProxy</param-name>
    <param-value>false</param-value>
  </init-param>
  <init-param>
    <param-name>allowedProxyChains</param-name>
    <param-value>https://gateway.example.test/login/cas/proxyreceptor</param-value>
  </init-param>
</filter>
~~~

Đây **chỉ là fragment cấu hình minh họa**, không phải web.xml hoàn chỉnh. Cần `filter-mapping`, service URL hoặc serverName chính xác, auth filters và test với version CAS Client thật. Theo Apereo Java CAS Client docs, `allowedProxyChains` khi dùng dạng init-param có thể khai **mỗi chain trên một dòng, URLs trong mỗi chain cách nhau bằng khoảng trắng**. Một cấu hình có nhiều chain cần đảm bảo không bị YAML/XML whitespace normalization làm thay đổi parser input.

**Không copy nguyên một Apereo Filter vào Spring Security nếu đã có CasAuthenticationFilter xử lý cùng URL**: có thể dẫn đến hai lớp cùng đọc/validate một PT, làm ticket **one-time** bị tiêu thụ trước khi lớp sau xử lý. Dùng một integration path có owner rõ ràng.

### 8.3. Ví dụ cấu hình nhiều chain trong file quản trị

~~~text
https://gateway.example.test/login/cas/proxyreceptor
https://gateway.example.test/login/cas/proxyreceptor https://portal.example.test/login/cas/proxyreceptor
~~~

**Dòng thứ nhất** cho phép [Gateway]. **Dòng thứ hai** cho phép [Gateway, Portal] theo thứ tự CAS trả về. Không coi hai dòng trên là “chỉ cần một proxy khớp”. Người vận hành phải xác nhận syntax `allowedProxyChains` của đúng Apereo client version và viết integration test đọc config thật, vì Binder XML, Servlet init-param và Java setter **không cùng kiểu dữ liệu**.

## 9. CAS Server service registry: chặn từ nguồn cấp PGT

Chỉ kiểm tra chain ở Reports là chưa đủ. CAS Server cần có chính sách **ai được phép làm proxy**.

Apereo CAS có **registered service proxy policy**. Tài liệu CAS mô tả mặc định **không cho service proxy**, có cấu hình như `RefuseRegisteredServiceProxyPolicy` và các chính sách cho phép callback URL dựa trên pattern hạn chế.

Ví dụ định hướng policy:

~~~text
CAS registered service Portal:
  serviceId = https://portal.example.test/login/cas
  proxyPolicy = allow PGT only for
    https://portal.example.test/login/cas/proxyreceptor

CAS registered service Gateway:
  serviceId = https://gateway.example.test/login/cas
  proxyPolicy = allow PGT only for
    https://gateway.example.test/login/cas/proxyreceptor

CAS registered service Unknown:
  proxyPolicy = refuse / no PGT issuance

CAS target Reports:
  targetService = https://reports.example.test/api/cas
  service registry entry approved
  allow PT only from registered actors per applicable policy
~~~

Đây là **mô hình quản trị**, không phải format JSON/YAML CAS Server hoàn chỉnh. Mỗi CAS version có schema service registry khác nhau. Khi cấu hình thật:

1. Xác nhận **service ID** và callback URL được phép.
2. Chỉ bật proxy cho **service có use case đã được phê duyệt**.
3. Không cấp quyền PGT nếu chỉ cần xác thực bằng ST.
4. Nếu dùng regex callback, giới hạn scheme, host, path và escaping chặt.
5. Bảo vệ thay đổi service registry bằng RBAC, code review/audit và versioning.
6. Không cho bất kỳ service tự yêu cầu `pgtUrl` là một URL nội bộ tùy ý (SSRF risk).
7. Có chủ sở hữu/tài liệu cho **mỗi chain được backend cho phép** và mục đích nghiệp vụ của nó.

### 9.1. Vì sao “CAS cấp PT” vẫn cần backend kiểm proxy chain?

Trong CAS proxy, CAS có thể cho một service hợp lệ lấy PGT và xin PT cho một backend. Tuy nhiên backend mới biết **các service trung gian nào được phép gửi tác vụ này**. Một CAS federation có nhiều ứng dụng không nên tự xem mọi ứng dụng là **đồng cấp về trust và quyền nghiệp vụ**.

Tài liệu **CAS Security Guide** cảnh báo rằng proxy tickets có trách nhiệm kiểm proxy chain tại **service nhận PT**, và cấu hình `/proxyValidate` nhưng không kiểm chain sẽ tạo lỗ hổng tin cậy. Đây là vấn đề **delegation** chứ không phải chỉ token validity.

## 10. PGT callback, TLS và việc định danh proxy

### 10.1. pgtUrl là định danh của proxy

Khi Portal muốn nhận PGT, nó gửi `pgtUrl` qua `/serviceValidate` hoặc `/proxyValidate`. CAS Server tạo HTTPS callback đến URL đó để đưa:

~~~text
pgtIou = PGTIOU-...
pgtId  = PGT-...
~~~

CAS chỉ trả `<cas:proxyGrantingTicket>PGTIOU-...</...>` khi cơ chế callback tương ứng thành công theo protocol/policy. Portal ghép PGTIOU của validation response với PGT do callback nhận được.

**Trường hợp lỗi:**

- `pgtUrl` HTTP thay vì HTTPS.
- Certificate callback hết hạn hoặc hostname không khớp.
- CAS không tin CA/certificate chain của callback.
- CAS service registry từ chối proxy policy.
- Endpoint callback không trả trạng thái phù hợp.
- Proxy receptor và validator dùng **hai PGT storage khác nhau**, không ghép được IOU.
- Callback đến replica A, validation response xử lý ở replica B khi storage không chia sẻ.

Không giải quyết bằng **tắt TLS peer verification** hoặc mở `acceptAnyProxy`. Đây là lỗi ở **PGT issuance/callback**, không phải lý do để hạ trust của Reports.

### 10.2. Không biến pgtUrl thành SSRF

CAS Server có thể phải chủ động gọi `pgtUrl`. Nếu cho phép một service lạ gửi callback URL bất kỳ, đó có thể là nguồn **server-side request forgery** hoặc khiến CAS liên hệ địa chỉ nội bộ không mong muốn.

Giảm rủi ro bằng:

- CAS service registry + proxy policy gắn **registered service → callback URL cụ thể**.
- Chỉ HTTPS, hostname được duyệt và kiểm chứng certificate/chain/validity.
- Giới hạn redirects và địa chỉ nội bộ/private IP theo chính sách.
- Dùng DNS/egress policy và network segmentation.
- Không chấp nhận `pgtUrl` do end-user query/tenant claim tự chọn.
- Theo dõi callback errors và lưu audit chỉ metadata cần thiết.

### 10.3. PGT là secret mạnh

PGT có thể dùng **nhiều lần để xin PT**, khác ST/PT one-time. Vì vậy:

- Không đưa PGT vào URL log, telemetry, exception, CI artifact hoặc client-side JavaScript.
- Đặt PGT storage chỉ service identity có quyền đọc, có encryption at rest và TTL/cancel policy.
- Vô hiệu hóa PGT theo CAS logout policy; nếu service dùng cache PGT riêng, phải có cleanup.
- Phân tách PGT theo user/session và CAS issuer/service.
- Không dùng một PGT cho nhiều tenant nếu contract không cho phép.
- Nếu nghi lộ PGT, xử lý như sự cố credential compromise, không chỉ xóa một PT đã dùng.

## 11. Target service: một lớp ràng buộc độc lập với chain

CAS cấp PT **cho targetService chỉ định** tại `/proxy`:

~~~text
GET /cas/proxy?pgt=PGT-opaque
    &targetService=https%3A%2F%2Freports.example.test%2Fapi%2Fcas
~~~

Khi Reports xác minh:

~~~text
GET /cas/proxyValidate?ticket=PT-opaque
    &service=https%3A%2F%2Freports.example.test%2Fapi%2Fcas
~~~

`targetService` lúc xin PT và `service` lúc validate phải khớp theo CAS Protocol/service matching policy. Một PT dành cho `https://inventory.example.test/api/cas` **không trở thành PT dành cho Reports** chỉ vì cùng user và cùng proxy chain.

**Chú ý:** một proxy chain hợp lệ **không tự làm PT hợp lệ với mọi backend**. Người vận hành cần tách:

- CAS Server URL tin cậy.
- CAS registered target service ID.
- Proxy chain allowlist của backend đó.
- Authorization policy với resource/action cụ thể.
- Đường dẫn service thực tại reverse proxy, không để `Host` hoặc `X-Forwarded-*` từ nguồn không tin cậy quyết định service identity.

Nếu backend kiểm một URL service chung cho nhiều API endpoints, vẫn phải kiểm **quyền theo endpoint/resource** sau khi xác thực; không vì một PT hợp lệ cho gateway root mà cho phép mọi thao tác quản trị.

## 12. CAS Proxy trong Spring Security: stateless và nguy cơ cache

Theo hướng dẫn Spring Security, khi service nhận proxy tickets ngoài callback `filterProcessesUrl`, có thể cần:

- `ServiceProperties.authenticateAllArtifacts=true` nếu chủ ý xử lý artifact trên nhiều URL.
- `ServiceAuthenticationDetailsSource` để xây **service URL từ HTTP request** đúng với PT target.
- `CasAuthenticationFilter` nhận ticket, tạo authentication request thích hợp (Spring Security bản hiện đại dùng `CasServiceTicketAuthenticationToken`).
- `CasAuthenticationProvider` dùng `Cas20ProxyTicketValidator` hoặc validator tương ứng với CAS 3 và chain allowlist.
- `StatelessTicketCache` (nếu dùng theo kiến trúc này) cho phép truy xuất Authentication đã xác minh theo ticket ở lần yêu cầu trước.

**Không bật authenticateAllArtifacts khi chỉ cần đăng nhập browser ST.** Việc bật trên toàn bộ filter chain có thể khiến rất nhiều endpoint chấp nhận tham số `ticket` và tạo bề mặt tấn công không cần thiết.

### 12.1. Dùng cache cần chủ ý về security semantics

CAS Protocol nói **PT dùng cho một validation attempt**, nhưng Spring Security mô tả `StatelessTicketCache` trong đó Authentication có thể được cache theo chuỗi PT để remoting client **gửi lại cùng PT** mà không gọi CAS xác minh thêm. Đây là **trust mở rộng ở tầng ứng dụng**, có tác động đến vòng đời credential.

Cần chính sách:

- Chỉ cache Authentication **đã qua cả CAS validation và proxy-chain allowlist**.
- Cache phải có **TTL ngắn, size limit, eviction**, không lâu hơn security requirement.
- Nếu allowlist/tenant authorization thay đổi, phải **invalidate hoặc version cache**; không để result cũ vượt policy mới.
- Nếu CAS logout/PGT bị thu hồi, cần tính đến **session invalidation/cached token lifetime**, không mặc nhiên cache biết CAS logout ngay.
- Cache key phải scope đúng CAS server/service/tenant nếu nhiều issuer; không gộp các ticket có cùng chuỗi từ namespace khác.
- Không cho phép bearer-style PT lâu dài ở URL, log hoặc access traces.
- Cân nhắc **không dùng cache** nếu yêu cầu giao thức/security policy không cho phép tái sử dụng token ở application layer.

Nếu hệ thống cần một API token có khả năng dùng nhiều lần, hãy đánh giá **một cơ chế token riêng phù hợp** thay vì để ticket CAS ngắn hạn trở thành API credential lâu dài.

### 12.2. Phân biệt cache và ticket registry

- **CAS Server ticket registry** biết ST/PT còn hợp lệ hay đã được tiêu thụ.
- **Spring StatelessTicketCache** lưu Authentication sau lần validate đầu ở service nhận PT.
- **PGT storage** giữ PGT để service xin PT mới.
- **HttpSession/SecurityContextRepository** giữ Authentication local của browser.

Đó là **bốn loại state khác nhau**. Không xử lý lỗi `INVALID_TICKET` bằng cách mở một cache vô hạn hoặc dùng PGT làm password.

## 13. Multi-tenant, nhiều CAS server và ranh giới trust

Một backend có thể phục vụ đối tác A và B; mỗi bên có một CAS Server riêng hoặc cùng CAS Server nhưng proxy services khác nhau.

Mô hình đề xuất:

~~~text
Partner A:
  CAS issuer/base: https://cas-a.example.test/cas
  backend service: https://api.example.test/a/cas
  chains:
    [https://gateway-a.example.test/cas/pgtCallback]

Partner B:
  CAS issuer/base: https://cas-b.example.test/cas
  backend service: https://api.example.test/b/cas
  chains:
    [https://gateway-b.example.test/cas/pgtCallback]
~~~

**Không xác minh PT của Partner B bằng CAS Server A**, không dùng allowlist chain A cho B và không dùng username/email để đoán CAS provider được tin. Việc chọn provider và service identity phải đến từ cấu hình/route đã được quản trị, được kiểm tra lại sau validation.

Khi backend có một CAS issuer nhưng nhiều tenants:

- Proxy callback URL có thể được chia sẻ nếu tổ chức chấp thuận, nhưng **tenant context** và **quyền nghiệp vụ** vẫn phải được kiểm riêng.
- Không lấy tenant từ query parameter hoặc CAS attribute chưa có hợp đồng quyền.
- Tách cache theo service/tenant/policy version nếu dùng stateful caching.
- Những thay đổi ở shared proxy có thể ảnh hưởng nhiều tenants; quản lý blast radius và rotation.

### 13.1. Proxy chain hợp lệ chưa đủ để cấp quyền

Ví dụ Gateway được phép gọi Reports nhưng chỉ trong tư cách người dùng thuộc nhóm Reports Reader. Một PT đã validate và chain [Gateway, Portal] được tin vẫn có thể cần từ chối `DELETE /reports/finance` nếu local authorization không cho.

Bảo vệ:

1. Kết quả ticket từ **CAS Server tin cậy**.
2. Service target đúng.
3. Full proxy chain được phê duyệt.
4. Local principal tồn tại, enabled, scoped theo CAS provider/tenant.
5. User quyền truy cập đúng resource/action.
6. Nếu cần, phân biệt **mức ủy nhiệm**: một proxy chỉ được đọc, proxy khác được ghi.
7. Audit user + proxy chain + action + decision, **không ghi raw ticket**.

## 14. Java 17 độc lập: kiểm tra toàn bộ proxy chain theo allowlist

Chương trình sau **biên dịch/chạy với JDK 17+, không cần Spring Security hay CAS Server**. Mô hình này có hai chain được phép:

- **[Gateway]** — một proxy hop.
- **[Gateway, Portal]** — hai proxy hops, gần nhất là Gateway như CAS response quy định.

Chương trình minh họa:

- Không chấp nhận **chain rỗng** cho một backend chỉ được dùng delegated PT.
- Không chấp nhận **proxy lạ**, thứ tự đảo, hop bổ sung.
- Không chấp nhận service đích khác, HTTPS bị hạ thành HTTP, URL có hậu tố bất ngờ hoặc thiếu username.
- Chỉ chấp nhận dữ liệu đã được **CAS TicketValidator thực sự xác minh**.

**Giới hạn nghiêm ngặt:** `VerifiedCasAssertion` là **mô hình dữ liệu mô phỏng đầu ra tin cậy**. Boolean `validatedByTrustedCas` **không được nhận từ JSON/header/query hay client**. Trong sản phẩm thật, chỉ có kết quả của `TicketValidator` sau khi kết nối CAS Server qua **HTTPS có TLS validation**, parse CAS protocol, kiểm ticket, service và proxy chain mới có thể được đưa vào bước business policy. Mã Java này **không xác minh ticket thật, không gọi CAS, không parse XML, không có HTTP security hoặc PGT storage**.

Tệp `CasProxyChainPolicyDemo.java`:

~~~java
import java.util.List;
import java.util.Set;

public class CasProxyChainPolicyDemo {
    static final String TARGET = "https://reports.example.test/api/cas";
    static final String GATEWAY =
        "https://gateway.example.test/login/cas/proxyreceptor";
    static final String PORTAL =
        "https://portal.example.test/login/cas/proxyreceptor";
    static final String ATTACKER =
        "https://evil.example.test/login/cas/proxyreceptor";

    // Represents a result already checked by the real CAS TicketValidator.
    record VerifiedCasAssertion(boolean validatedByTrustedCas,
                                String service, String username,
                                List<String> proxies) {}

    static final class StrictPolicy {
        // CAS lists the most recently traversed proxy first.
        private final Set<List<String>> approvedChains = Set.of(
            List.of(GATEWAY), List.of(GATEWAY, PORTAL));

        boolean accept(VerifiedCasAssertion result) {
            if (result == null || !result.validatedByTrustedCas())
                return false;
            if (!TARGET.equals(result.service()))
                return false;
            if (result.username() == null || result.username().isBlank())
                return false;
            return approvedChains.contains(result.proxies());
        }
    }

    static VerifiedCasAssertion result(boolean verified,
                                       String service, List<String> chain) {
        return new VerifiedCasAssertion(verified, service, "u-42", chain);
    }

    public static void main(String[] args) {
        StrictPolicy p = new StrictPolicy();
        System.out.println("approvedOneHop=" +
            p.accept(result(true, TARGET, List.of(GATEWAY))));
        System.out.println("approvedTwoHops=" +
            p.accept(result(true, TARGET, List.of(GATEWAY, PORTAL))));
        System.out.println("directTicketDenied=" +
            !p.accept(result(true, TARGET, List.of())));
        System.out.println("unknownProxyDenied=" +
            !p.accept(result(true, TARGET, List.of(ATTACKER))));
        System.out.println("reorderedChainDenied=" +
            !p.accept(result(true, TARGET, List.of(PORTAL, GATEWAY))));
        System.out.println("extraHopDenied=" +
            !p.accept(result(true, TARGET,
                List.of(GATEWAY, PORTAL, ATTACKER))));
        System.out.println("untrustedResultDenied=" +
            !p.accept(result(false, TARGET, List.of(GATEWAY))));
        System.out.println("wrongServiceDenied=" +
            !p.accept(result(true, "https://other.example.test/api/cas",
                List.of(GATEWAY))));
        System.out.println("prefixTrickDenied=" +
            !p.accept(result(true, TARGET,
                List.of(GATEWAY + ".evil.example.test"))));
        System.out.println("httpDowngradeDenied=" +
            !p.accept(result(true, TARGET,
                List.of(GATEWAY.replace("https:", "http:")))));
        System.out.println("trailingSlashDenied=" +
            !p.accept(result(true, TARGET, List.of(GATEWAY + "/"))));
        System.out.println("missingUserDenied=" +
            !p.accept(new VerifiedCasAssertion(true, TARGET, "",
                List.of(GATEWAY))));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 CasProxyChainPolicyDemo.java
java CasProxyChainPolicyDemo
~~~

**Stdout chính xác:**

~~~text
approvedOneHop=true
approvedTwoHops=true
directTicketDenied=true
unknownProxyDenied=true
reorderedChainDenied=true
extraHopDenied=true
untrustedResultDenied=true
wrongServiceDenied=true
prefixTrickDenied=true
httpDowngradeDenied=true
trailingSlashDenied=true
missingUserDenied=true
~~~

Ở các dòng `...Denied=true`, nghĩa là điều kiện phủ định báo **policy đã từ chối như mong đợi**. `approvedOneHop=true` và `approvedTwoHops=true` chứng minh hai chain nguyên vẹn được phép.

**Hạn chế cố ý của bài học:** phép `Set<List<String>>.contains` thực hiện full-chain exact match, **không giải quyết** CAS proxy trust bootstrap, canonicalization URI, certificate trust, service registry, revocation hay authorization. Trong thực tế, nên dùng **CAS Java Client validated assertion** và cấu hình allowlist của validator; nếu tự viết business layer check bổ sung, không dùng nó thay `Cas20ProxyTicketValidator`.

## 15. Tấn công/sai cấu hình cần chủ động kiểm thử

| Tình huống | Input hoặc thay đổi | Kết quả yêu cầu |
| --- | --- | --- |
| Một hop đúng | [Gateway] với PT cho Reports | PASS nếu identity và authorization đúng |
| Hai hop đúng | [Gateway, Portal] | PASS nếu policy liệt kê đủ |
| Direct ST tới backend PT-only | `cas:proxies=[]` | FAIL, trừ khi có policy direct riêng |
| Proxy chưa đăng ký | [Unknown] | FAIL |
| Hoán đổi thứ tự | [Portal, Gateway] | FAIL |
| Thêm hop ở đầu | [Attacker, Gateway, Portal] | FAIL |
| Thêm hop ở cuối | [Gateway, Portal, Attacker] | FAIL |
| Chain chỉ chứa một proxy trong allowlist | [Gateway, Unknown] | FAIL |
| So khớp substring nguy hiểm | URL lạ chứa text `gateway.example.test` | FAIL |
| Hostname prefix giả | `gateway.example.test.evil.test` | FAIL |
| HTTP downgrade | `http://gateway...` thay vì HTTPS | FAIL |
| Trailing slash khác | `.../proxyreceptor/` | FAIL theo exact policy |
| Path gần giống | `.../proxyreceptor-admin` | FAIL |
| Port khác | `https://gateway...:8443/...` | FAIL nếu không được đăng ký |
| Regex quá rộng | `^https://.*` | Config QA FAIL, không đưa production |
| URL regex thiếu end anchor | Pattern match đầu chuỗi và cho thêm hậu tố | FAIL negative tests |
| CAS validation endpoint giả | MITM/DNS/hostname mismatch | FAIL TLS, không tạo Authentication |
| Browser giả `X-Proxy-Chain` | Header tự khai chain hợp lệ | Không coi là CAS assertion |
| CAS response XML giả | HTTP client gửi `cas:proxies` | Không parse làm trusted nếu chưa qua TicketValidator |
| PT cho service khác | targetService=Inventory, backend=Reports | FAIL từ CAS validation |
| PT đã dùng | Cùng PT gửi lần hai | CAS từ chối nếu không có application cache; kiểm policy cache |
| PT hết hạn | Validation sau TTL | FAIL |
| PGT lộ | Một actor cố xin PT khác từ PGT | Incident response, thu hồi/bảo vệ PGT |
| PGT callback HTTP | `pgtUrl=http://...` | CAS từ chối theo protocol/policy |
| PGT callback cert hết hạn | TLS trust fail | Không cấp PGT |
| PGT callback tới nội bộ lạ | `pgtUrl` chỉ IP/host chưa approved | CAS chặn policy/SSRF |
| PGTIOU không match | Callback và validation response không liên kết | Không dùng PGT |
| Một cluster mất PGT | Callback node A, app node B không thấy IOU | Fail closed; shared storage/affinity |
| CAS service policy bị mở rộng | Unknown service được cấp PGT | Phát hiện qua config review/test |
| `acceptAnyProxy=true` | Bật ở backend Reports | Deployment gate FAIL |
| `authenticateAllArtifacts=true` không cần | PT được thử trên mọi endpoint | Giới hạn filter processing/URL |
| Cache giữ auth sau đổi policy | PT hợp lệ cũ được reuse từ cache | Evict/version cache; không vượt policy mới |
| Cache cross-tenant | Ticket cache trùng namespace | Tách issuer/service/tenant |
| Tenant A proxy sang B | Valid CAS issuer nhưng chain thuộc A | FAIL nếu B không allowlist |
| User disabled local | CAS success, app user khóa | FAIL authorization |
| Quyền không đủ | Proxy chain đúng, user không có quyền ghi | HTTP 403, không cấp quyền |
| CAS logout | PGT/TGT bị vô hiệu hóa, cache vẫn còn | Test revocation/TTL của app cache |

**Không cần ticket production thật để kiểm các chuỗi sai.** Dùng CAS test server/service registry riêng, dummy users và integration mocks có xác minh API. Với test có mã ticket, chỉ ghi correlation IDs đã hash hoặc redact.

## 16. Threat model: điều gì xảy ra nếu tin mọi proxy?

### 16.1. Service khác làm proxy ngoài dự kiến

Nếu Reports cho phép bất kỳ proxy nào, một service nội bộ thứ ba được CAS cấp PGT có thể xin PT thay user (trong phạm vi CAS service/target policy). Reports kiểm CAS ticket hợp lệ rồi **nhầm rằng nguồn ủy nhiệm cũng được phép**.

Hậu quả có thể là:
- Bypass các hạn chế chỉ Portal/Gateway được dùng chức năng delegated access.
- Lạm dụng quyền user trên backend không thuộc luồng đã được xét duyệt.
- Audit chỉ thấy username, không biết hop trung gian nào chịu trách nhiệm.
- Khó thu hồi riêng một proxy sau khi phát hiện lỗi.

### 16.2. Host spoof và cấu hình “wildcard để sửa lỗi”

Nếu service URL hoặc callback URL được lấy tùy ý từ `Host`/`X-Forwarded-Host`, kẻ tấn công có thể tạo URL nhận diện sai service. Nếu cùng lúc allowlist regex quá rộng, khả năng PT đi qua tuyến không được duyệt tăng lên.

Khắc phục bằng **public URL cố định**, trusted reverse proxy, exact service registration và negative tests host/path/port. Không dùng `acceptAnyProxy=true` làm cách “fix nhanh” lỗi hostname.

### 16.3. Proxy chain giả qua HTTP header

Một app có thể nhận:

~~~text
X-Proxy-Chain: https://gateway.example.test/login/cas/proxyreceptor
~~~

**Không được dùng header ấy làm proxy chain CAS**. Chỉ sử dụng `<cas:proxies>` do CAS TicketValidator trả sau khi xác minh ticket. HTTP proxy headers ở mạng hạ tầng không có cùng semantics với CAS delegation path.

### 16.4. Bị lợi dụng làm proxy đến backend nhạy cảm

Portal có thể có PGT hợp lệ nhưng không được tùy chọn bất cứ `targetService` nào từ tham số `targetUrl` do browser đưa vào. Portal nên dùng **allowlist backends**, không cho người dùng chuyển PGT thành PT dành cho ứng dụng nhạy cảm khác.

Bộ kiểm soát nên có cả:

- CAS registered proxy policy (ai có thể lấy PGT).
- Proxy app targetService allowlist (backend nào được gọi).
- Reports backend chain allowlist (proxy nào được tin).
- API authorization (user nào được làm gì).
- Network egress/SSRF protection và secrets policy.

## 17. Troubleshooting đúng theo lỗi

| Triệu chứng | Nguyên nhân khả dĩ | Cách điều tra an toàn |
| --- | --- | --- |
| Browser ST login chạy nhưng không xin được PGT | CAS service proxyPolicy từ chối | Kiểm registry service/callback, không bật mọi proxy |
| `pgtIou` không có | Callback TLS/HTTP status lỗi hoặc CAS không cấp PGT | Kiểm CAS callback logs/truststore |
| PGTIOU có nhưng không tìm ra PGT | Receptor/validator storage khác, cache TTL, load balancer | Kiểm shared ProxyGrantingTicketStorage, correlation |
| Xin PT trả lỗi | PGT hết hạn/revoked hoặc targetService không được phép | Kiểm CAS /proxy response và proxy policy |
| `INVALID_SERVICE` khi PT validate | targetService khác service URL backend gửi | So đúng scheme/host/path/port, proxy config |
| `INVALID_TICKET` | PT hết hạn/đã dùng/malformed hoặc sai CAS server | Xin PT mới, kiểm ticket registry |
| Validation pass nhưng proxy chain bị từ chối | URL hop không nằm allowlist, thứ tự khác | Đọc danh sách `cas:proxies` đã được validate, redacted |
| Chain rỗng bị từ chối | Backend PT-only policy không cho direct ST | Xem profile ST vs PT; không mở vô điều kiện |
| Trật thứ tự hop | Người vận hành ghi [Portal, Gateway] nhưng CAS trả [Gateway, Portal] | Đối chiếu protocol, sửa allowlist có review |
| Một proxy mới được thêm vào giữa | Service delegation architecture thay đổi | Xem phê duyệt onboarding, thêm chain chính xác |
| Chỉ lỗi khi HTTPS ở proxy callback | Certificate trust/hostname/CA chain | Sửa certificate/truststore, không tắt TLS |
| Chỉ lỗi production sau ingress | URL public và callback path/host khác | Kiểm trusted Forwarded headers và CAS registry |
| CAS 2 validator không nhận attributes CAS3 | Dùng sai endpoint/profile | Chọn CAS 3 validator theo version |
| `ClassCastException`/API mismatch | Apereo client/Spring Security version không tương thích | Kiểm dependency graph, Javadoc thật |
| Reload allowlist mà vẫn accept chain cũ | Validator/cache không reload hoặc cached auth còn | Rolling restart, version/evict cache |
| ST stateful hoạt động, PT stateless fail | `authenticateAllArtifacts`/details source/provider không nối đúng | Kiểm filter chain và service URL |
| PT được phép nhưng API trả 403 | Local user bị khóa hoặc role policy không đủ | Kiểm application authorization, không mở proxy |
| PT xuất hiện trong access log | Logger/proxy ghi full query | Redact `ticket`, xử lý secret exposure |
| CAS Service PGT được cấp ngoài ý muốn | CAS registry regex quá rộng | Thu hẹp proxy policy, kiểm lại mọi service |
| Lỗi chỉ trên cluster | PGT/PGTIOU/session/cached auth không đồng bộ | Shared storage hoặc partition-aware design |

### 17.1. Log an toàn

~~~text
event=CAS_PROXY_CHAIN_REJECTED
casServer=https://sso.example.test/cas
targetService=https://reports.example.test/api/cas
chain=[gateway,unknown]            # đã chuẩn hóa label nội bộ
reason=UNAPPROVED_PROXY_CHAIN
policyVersion=reports-proxy-v8
requestId=trace-7f4e
~~~

**Không log raw `PT-...`, `PGT-...`, `PGTIOU-...`, full CAS XML, browser cookies hoặc user attributes nhạy cảm.** CAS proxy callback URLs bản thân không phải bí mật như PGT, nhưng vẫn nên quản trị log theo chính sách.

## 18. Quy trình triển khai an toàn từng bước

1. **Inventory use cases:** backend nào thực sự cần PT? Nếu không có, giữ ST-only và không cấp PGT.
2. **Inventory CAS services:** Portal/Gateway/Reports có service IDs và callback URLs nào?
3. **Thiết kế trust chains:** xác định **đúng danh sách proxy hop theo thứ tự CAS trả**, mỗi chain gắn owner/change ticket.
4. **Khóa CAS service registry:** service nào được cấp PGT, callback URL nào cho phép, target service nào được phép.
5. **Khóa network/TLS:** CAS validation endpoint và PGT callbacks phải HTTPS, certificate/hostname được xác minh.
6. **Cấu hình backend:** `acceptAnyProxy=false`, `allowedProxyChains` rõ ràng, không allowEmptyProxyChain nếu PT-only.
7. **Cấu hình đúng validator:** `Cas20ProxyTicketValidator`/CAS 3 variant theo server; không dùng `Cas20ServiceTicketValidator` cho PT hoặc bật proxy validator ở ST-only service.
8. **Cấu hình Spring filter chain:** nếu stateless PT, giới hạn endpoint, `ServiceAuthenticationDetailsSource` và `authenticateAllArtifacts` chỉ nơi cần.
9. **Cấu hình PGT storage:** secure, TTL, cleanup, shared giữa receptor và validator, hoạt động khi load balance.
10. **Áp local authorization:** user/tenant/role/target operation; chain pass không tự cấp business permission.
11. **Test happy paths:** direct ST-only; một hop; hai hop được duyệt; callback/target service đúng.
12. **Test negative matrix:** unknown/reordered/extra/empty chain, service mismatch, proxy callback TLS fail, PGTIOU mismatch, ticket replay.
13. **Load test/cache policy:** kiểm TTL, size, revocation, user khóa, config reload và tình huống CAS logout.
14. **Quan sát production:** số lượng proxy-chain reject, registry changes, PT/PGT issuance, callback errors và anomaly.
15. **Rollback:** khi chuỗi được duyệt mới gây lỗi, khôi phục cấu hình/route; **không rollback bằng cách mở acceptAnyProxy**.

## 19. Checklist cho code review và QA

- [ ] Chỉ bật CAS Proxy cho backend thật sự cần ủy nhiệm; ST-only không dùng `/proxyValidate`.
- [ ] `Cas20ProxyTicketValidator.setAcceptAnyProxy(false)` rõ ràng; không có `acceptAnyProxy=true` ở bất cứ env production nào.
- [ ] `allowedProxyChains` là danh sách **full chains** chính xác, không phải list “đủ chứa một proxy được tin”.
- [ ] Kiểm **thứ tự gần nhất trước**, như CAS `<cas:proxies>` trả.
- [ ] Không cho proxy lạ ở đầu/giữa/cuối; không mở chain vượt số hop phê duyệt.
- [ ] Exact URL matching cho callback URL; nếu regex, bắt `^...$` và kiểm các trường hợp giả host/path/port.
- [ ] Nếu PT-only, chain rỗng không được chấp nhận; nếu có ST direct, có chính sách tách biệt.
- [ ] CAS validation endpoint phải là server cố định/trusted, TLS/hostname verification bật.
- [ ] CAS response proxy list phải đến từ **TicketValidator** đã xác minh, không từ header/query/client XML.
- [ ] targetService ở `/proxy` khớp `service` lúc `/proxyValidate` và CAS registered target.
- [ ] CAS registered service chỉ cấp PGT cho Portal/Gateway được phép; proxy policy default deny.
- [ ] `pgtUrl` là HTTPS callback được CAS cấp phép và xác minh peer certificate.
- [ ] CAS Server hạn chế SSRF/redirect đối với pgtUrl; không liên hệ arbitrary host do user chọn.
- [ ] PGT, PGTIOU, PT không bị log; PGT storage có quyền truy cập tối thiểu và cleanup.
- [ ] CAS 2 vs CAS 3 validation endpoint/validator được kiểm với version thật.
- [ ] Apereo Java CAS Client và Spring Security dùng phiên bản tương thích; hiểu setter `ProxyList`.
- [ ] Không đăng ký hai CAS filters trùng cùng endpoint; tránh ST/PT bị consume trước.
- [ ] Với stateless PT, `authenticateAllArtifacts` chỉ bật khi thực sự có service URL details đúng.
- [ ] `StatelessTicketCache` nếu dùng có TTL/size/policy invalidation và không kéo dài credential tùy tiện.
- [ ] Không coi PT dùng một lần ở CAS như API token tái sử dụng vô hạn trong Spring.
- [ ] Multi-tenant tách CAS issuer, service, proxy chains, cache và user scope.
- [ ] CAS ticket hợp lệ + proxy hợp lệ vẫn phải qua local roles/resource authorization.
- [ ] Test chain order, unknown hop, extra hop, direct ST, wrong target, ticket replay, PGT callback TLS, proxy policy.
- [ ] Khi có proxy mới, yêu cầu approval và rollout/version allowlist; không thay bằng wildcard.
- [ ] Log có policyVersion, service, reject reason nhưng không ghi raw ticket.

## 20. Câu hỏi tự kiểm tra

**1. Tại sao CAS Proxy Ticket hợp lệ vẫn có thể bị backend từ chối?**

Vì CAS xác minh ticket đúng nhưng backend cần **kiểm proxy chain** có nằm trong danh sách được ủy nhiệm không. Ticket hợp lệ **không chứng minh mọi proxy đều được phép gọi backend**.

**2. `acceptAnyProxy=true` làm thay đổi điều gì?**

Nó cho phép validator chấp nhận proxy chain rộng hơn, bỏ kiểm soát nguồn ủy nhiệm theo allowlist. Nó **không tự tạo CAS ticket hợp lệ hoặc bỏ qua target-service validation**, nhưng làm mất một tầng bảo vệ quan trọng.

**3. CAS trả proxy chain theo thứ tự nào?**

**Proxy vừa đi qua gần nhất đứng đầu**. Portal → Gateway → Reports thì backend nhận **[Gateway, Portal]**, không phải [Portal, Gateway].

**4. Có thể chỉ kiểm `chain.contains("Portal")` không?**

Không. [Attacker, Portal] cũng chứa Portal nhưng có hop chưa được duyệt. Cần kiểm **toàn bộ chain và thứ tự**.

**5. `allowedProxyChains` trong Apereo Java CAS Client là một `List<String>` Java tùy ý?**

Không nên giả định. API `Cas20ProxyTicketValidator.setAllowedProxyChains` có kiểu **ProxyList** trong Javadoc; init-param filter lại là string theo cú pháp mỗi chain một dòng. Cần dùng binder/parser đúng thư viện.

**6. Nếu backend không cần nhận proxy tickets, cấu hình an toàn nhất là gì?**

Dùng **service ticket validation** và không bật proxy, không nhận PT, không cấp PGT và không bật authenticateAllArtifacts không cần thiết.

**7. `pgtUrl` dùng để làm gì và có liên quan tới proxy chain không?**

Nó là **HTTPS callback để CAS xác minh danh tính service muốn nhận PGT**, và URL này giúp CAS biểu diễn service trung gian trong proxy chain. Không phải header mạng hay endpoint bất kỳ người dùng chọn.

**8. `PGTIOU` có phải PGT để gọi `/proxy` không?**

Không. PGTIOU dùng **correlate PGT** đến từ callback với kết quả ticket validation; `/proxy` cần **PGT thực** đã được cấp.

**9. Proxy Ticket có dùng nhiều lần ở CAS không?**

Không. CAS Protocol nêu PT chỉ cho một validation attempt. Spring `StatelessTicketCache` có thể dùng lại authenticated result tại app, nên đó là **quyết định cache riêng có rủi ro**, không phải CAS cho PT dùng nhiều lần.

**10. `/serviceValidate` có nhận Proxy Ticket không?**

Theo CAS Protocol, **không**. `/proxyValidate` dùng để xác minh ST và PT, nhưng backend dùng nó phải **kiểm proxy chain**.

**11. Vì sao phải chặn arbitrary pgtUrl tại CAS Server?**

CAS có thể thực hiện HTTPS callback tới pgtUrl. Cho service tùy ý chọn nó có thể dẫn đến **SSRF** hoặc cấp PGT cho endpoint không được ủy quyền.

**12. Nếu proxy chain đúng, có tự cấp quyền đọc mọi báo cáo không?**

Không. Backend còn phải kiểm **subject, tenant, local authorities và resource permissions**. Ủy nhiệm xác thực không tự đồng nghĩa ủy quyền nghiệp vụ.

**13. Khi đổi URL callback từ /pgtCallback sang /proxyreceptor, cần làm gì?**

Cập nhật CAS proxy policy/registry, allowed proxy chains tại backend, TLS/certificate/callback config, integration tests và rollout có overlap nếu protocol/policy cho phép. Không nên mở wildcard để tránh lỗi migration.

**14. Vì sao không dùng một CAS issuer và allowlist chung cho mọi tenant?**

Một tenant có thể có proxy/callback và quyền nghiệp vụ khác; trust chung không có scope có thể cho phép A được nhận ở B. Cần map issuer/service/chain/tenant rõ.

**15. Việc dùng HTTPS ở PGT callback đã đủ để tin proxy chưa?**

Chưa. CAS phải xác minh peer certificate và registry proxy policy; backend vẫn phải **kiểm CAS-provided chain** xem service trung gian ấy được phép ủy nhiệm hay không.

## 21. Nguồn tham khảo chính thức

- Spring Security, **CAS Authentication** — `Cas20ServiceTicketValidator`, `Cas20ProxyTicketValidator`, proxy ticket authentication, `ServiceAuthenticationDetailsSource`, `StatelessTicketCache` và ví dụ cấu hình rộng: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
- Spring Security Javadoc, **CasAuthenticationFilter**, xử lý service/proxy tickets, `authenticateAllArtifacts` và token stateless: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html
- Spring Security Javadoc, **CasAuthenticationProvider**, ticket validator/service integration: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html
- Apereo CAS, **CAS Protocol Specification**, `/serviceValidate`, `/proxyValidate`, `/proxy`, callback PGT, `<cas:proxies>`, thứ tự chain và one-time tickets: https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html
- Apereo CAS, **CAS Security Guide**, trách nhiệm kiểm proxy chain và cảnh báo nhận PT không kiểm chain: https://apereo.github.io/cas/development/planning/Security-Guide.html
- Apereo CAS, **Configuring Service Proxy Policy**, mặc định từ chối proxy và cho phép callback theo chính sách: https://apereo.github.io/cas/8.0.x/services/Configuring-Service-Proxy-Policy.html
- Apereo CAS, **Proxy Authentication**, luồng ST → PGT → PT → backend và TLS callback: https://apereo.github.io/cas/7.3.x/authentication/Configuring-Proxy-Authentication.html
- Apereo Java CAS Client, **README**, `acceptAnyProxy=false` mặc định, `allowedProxyChains` theo URL/regex và init-param filters: https://github.com/apereo/java-cas-client/blob/master/README.md
- Javadoc CAS Client, **Cas20ProxyTicketValidator**, setter `setAllowedProxyChains(ProxyList)` và `setAllowEmptyProxyChain(boolean)` (đối chiếu với version đã cài): https://javadoc.io/static/org.jasig.cas.client/cas-client-core/3.6.4/org/jasig/cas/client/validation/Cas20ProxyTicketValidator.html

**Ghi nhớ:** **Không mở `acceptAnyProxy=true` chỉ để proxy login chạy được**. Nếu chỉ cần browser CAS login, hãy **không nhận Proxy Ticket**. Nếu phải nhận PT, hãy xác minh nó với **CAS Server tin cậy** và **targetService đúng**, rồi yêu cầu **full proxy chain khớp allowlist theo đúng thứ tự CAS**; chỉ cấp PGT tại CAS cho các proxy service/callback được duyệt, bảo vệ PGT và vẫn kiểm **authorization nghiệp vụ**. Đó là cách giới hạn proxy được tin cậy mà không làm mất các lợi ích của CAS federation.