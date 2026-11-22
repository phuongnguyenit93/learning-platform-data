# Kiểm thử CAS Proxy với callback và chuỗi proxy không được phép

## 1. Bài toán: CAS Proxy khác đăng nhập SSO trực tiếp như thế nào?

Trong chủ đề **Spring Security - federation**, phần **Kiểm thử SSO**, **CAS Proxy** cho phép một ứng dụng đã xác thực người dùng thông qua **Central Authentication Service (CAS)** gọi **dịch vụ downstream thay mặt người dùng** mà không chuyển mật khẩu hay Ticket Granting Ticket (TGT) của người dùng cho dịch vụ đó. Đây là một cơ chế **ủy quyền giới hạn bởi vé và dịch vụ đích** trong giao thức CAS, không phải HTTP reverse proxy thông thường và cũng không phải OAuth access-token delegation.

Ví dụ một kiến trúc doanh nghiệp:

~~~text
                       CAS Server
                    https://cas.example.org/cas
                         /login
                         /serviceValidate
                         /proxy
                         /proxyValidate
                            ^
                            |
Browser ---> Portal A ------+---------> Reports API B
            (CAS client,                   (CAS client, validates PT)
             CAS proxy)                    |
                |                          |
                +-- PGT callback <---------+ (CAS Server không gọi API B
                    tại Portal A               để giao PGT của Portal A)
~~~

Một phiên điển hình: người dùng đăng nhập CAS vào Portal A; Portal A nhận **Service Ticket (ST)** và yêu cầu CAS cấp **Proxy-Granting Ticket (PGT)** thông qua **callback an toàn**; Portal A dùng PGT để lấy **Proxy Ticket (PT)** cho Reports API B; B gọi CAS **`/proxyValidate`** và phải quyết định **toàn bộ proxy chain có được phép không** trước khi tin danh tính được ủy quyền.

**Đề bài kiểm thử có hai trọng tâm riêng nhưng liên kết chặt chẽ:**

1. **Callback PGT** có thực sự được nhận từ CAS Server qua kênh phù hợp, lưu `pgtId` bí mật, ghép đúng `pgtIou` với phản hồi ticket validation, và từ chối giả mạo/ghép nhầm/race/mất callback?
2. **Proxy chain** trên phản hồi `/proxyValidate` có được xét **toàn bộ, đúng thứ tự**, chỉ chấp nhận những tuyến ủy quyền được phê duyệt; có từ chối proxy lạ, quá dài, đảo thứ tự, rỗng khi route bắt buộc proxy, và cấu hình `acceptAnyProxy=true` quá rộng?

Bài gồm: thuật ngữ và giao thức, cách thiết kế trust boundary, Spring Security/CAS Java Client setup, sơ đồ test, test matrix, mock và integration/E2E tests, Java 17 chạy độc lập để mô phỏng chính sách, cách giải quyết lỗi và checklist nghiệm thu.

> **An toàn mặc định:** một **PT hợp lệ với CAS Server** không nhất thiết hợp lệ **với quyền truy cập Reports API B**. B còn phải xác minh đúng `targetService`, **proxy chain được phép**, local user/account status và permission đối với tài nguyên. Một **PGT callback tới đúng URL** không tự chứng minh caller là CAS Server nếu không có inbound trust hoặc correlation đáng tin.

## 2. Phân biệt bốn loại ticket và hai dạng callback

| Khái niệm | Ai giữ / xuất hiện ở đâu? | Tác dụng và thời hạn |
| --- | --- | --- |
| **TGT** – Ticket Granting Ticket | CAS Server quản lý; browser giữ cookie CAS TGC để dùng phiên SSO. | Cho CAS phát nhiều ST khi SSO. **Không chuyển TGT raw cho Portal hoặc API B**. |
| **ST** – Service Ticket | Browser được redirect về Portal A kèm `ticket=ST-...`. | Vé **một lần**, ràng buộc `service` của A; A xác minh server-to-server với CAS. |
| **PGT** – Proxy-Granting Ticket | CAS Server cấp cho **Portal A** qua callback an toàn hoặc cơ chế khác được duyệt. | Credential để A xin nhiều PT theo targetService, có lifecycle riêng và bị vô hiệu theo policy/CAS logout. **Không xuất ra browser**. |
| **PGTIOU** – PGT I Owe You | Cùng giá trị xuất hiện trong CAS callback và ticket validation response. | **Khóa tương quan** để A tìm đúng PGT tương ứng với ST/PT validation. Không phải PGT và không tự dùng lấy PT. |
| **PT** – Proxy Ticket | Portal A gọi CAS `/proxy?pgt=...&targetService=...` và nhận `PT-...`. | Vé **một lần khi validate tại CAS**, chỉ dành **dịch vụ đích** như B. |
| **Proxy chain** – Chuỗi proxy | CAS trả ở `<cas:proxies>` trong phản hồi `/proxyValidate`. | Danh sách **proxy callback URLs** từng chuyển tiếp xác thực, **proxy gần đích nhất xuất hiện đầu tiên**. |

**Hai callback không được nhầm:**

- **Browser → A với ST**: người dùng quay lại URL dịch vụ đã khai báo của A, chẳng hạn `https://portal.example.org/login/cas?ticket=ST-...`; A đem ticket đi xác minh tại CAS.
- **CAS Server → PGT receptor của A**: **HTTP GET server-to-server** tới `https://portal.example.org/login/cas/proxyreceptor?pgtId=...&pgtIou=...`, nơi A phải nhận và lưu PGT vào kho bí mật.

Một HTTP reverse proxy/ingress tại `portal.example.org` có thể chuyển tiếp cả hai loại request; tuy nhiên **CAS proxy chain** là **chuỗi dịch vụ sử dụng PT**, không phải danh sách CDN/ingress/LB hops trong `X-Forwarded-For`.

### 2.1. Không phải loại vé nào cũng xác minh bằng cùng endpoint

| CAS endpoint | Dùng để làm gì? | Yêu cầu không được bỏ |
| --- | --- | --- |
| `/serviceValidate` | Validate **ST** cho đúng `service`; có thể yêu cầu `pgtUrl`. | ST đúng service, còn hiệu lực, chưa sử dụng. |
| `/proxyValidate` | Validate **ST hoặc PT**, kèm proxy chain trong trường hợp proxy. | Tất cả ST constraints cộng với **proxy policy** tại dịch vụ nhận. |
| `/proxy` | Đổi PGT lấy PT cho một `targetService` cụ thể. | PGT hợp lệ, service được CAS cho phép proxy, `targetService` được duyệt. |
| PGT receptor ở ứng dụng | Nhận `pgtId` và `pgtIou` khi CAS callback. | HTTPS, trust CAS/inbound, lưu secret và correlation đúng. |

CAS `/validate` cũ của CAS 1.0 **không hỗ trợ proxy ticket**. Không chọn validator CAS 1.0 rồi diễn giải bất kỳ response `yes` nào thành PT hợp lệ.

## 3. Luồng end-to-end: nhận PGT rồi dùng PT

Chọn tên và host chỉ để minh họa:

~~~text
CAS Server: https://cas.example.org/cas
Portal A:   https://portal.example.org/app/login/cas
PGT URL A:  https://portal.example.org/app/login/cas/proxyreceptor
Reports B:  https://reports.example.org/api/v1/summary
~~~

### 3.1. Giai đoạn A: ST validation và PGT callback

~~~text
Browser                  Portal A                     CAS Server
  |                         |                              |
  | /login/cas?ticket=ST-a  |                              |
  |------------------------>|                              |
  |                         | GET /serviceValidate          |
  |                         | ticket=ST-a                   |
  |                         | service=https://portal.../login/cas
  |                         | pgtUrl=https://portal.../proxyreceptor
  |                         |----------------------------->|
  |                         |                              | kiểm ST/service
  |                         |<-----------------------------|
  |                         |  CAS gọi PGT callback         |
  |                         |<-----------------------------|
  |                         | GET proxyreceptor?            |
  |                         |     pgtId=PGT-abc             |
  |                         |     pgtIou=PGTIOU-xyz         |
  |                         | lưu IOU -> PGT bí mật          |
  |                         | HTTP 200                      |
  |                         |----------------------------->|
  |                         |                              |
  |                         |  /serviceValidate response   |
  |                         |<-----------------------------|
  |                         |  <cas:user>alice</cas:user>   |
  |                         |  <cas:proxyGrantingTicket>    |
  |                         |       PGTIOU-xyz             |
  |                         |  </cas:proxyGrantingTicket>   |
  |                         | lấy PGT theo verified IOU     |
~~~

**Không giả định callback đến sau XML response:** theo giao thức CAS, CAS thường gọi receptor **trước khi** trả response chứa IOU; ứng dụng cần xử lý **đảo thứ tự/timing** và multi-node. Chỉ tin **IOU trùng response CAS validation đã xác minh**, không dùng “PGT mới nhất” hoặc username để ghép.

CAS 2.0 protocol quy định `pgtUrl` phải dùng **HTTPS** và CAS Server phải đánh giá trust của service callback theo PKIX/certificate policy. Nếu callback không kết nối được hoặc không có response thành công, CAS **không được cấp PGT bình thường**. Có thể ST validation vẫn trả một kết quả xác thực tùy cơ chế/thất bại proxy; ứng dụng **không được nói là PGT đã tạo thành công** khi không có verified IOU→PGT mapping.

### 3.2. Giai đoạn B: lấy PT và truy cập API

~~~text
Portal A                    CAS Server                    Reports API B
   |                            |                               |
   | GET /proxy                 |                               |
   |   pgt=PGT-abc              |                               |
   |   targetService=https://reports.../summary                 |
   |--------------------------->|                               |
   |                            | validate PGT and permission   |
   |<---------------------------|                               |
   | <cas:proxyTicket>PT-b</cas:proxyTicket>                     |
   |                            |                               |
   | GET /api/v1/summary?ticket=PT-b                              |
   |------------------------------------------------------------>|
   |                            |                               |
   |                            |  GET /proxyValidate           |
   |                            |  ticket=PT-b                  |
   |                            |  service=exact-targetService  |
   |                            |<------------------------------|
   |                            |------------------------------>|
   |                            |  success + user + proxies     |
   |                            |                               |
   |                            |                        B checks chain:
   |                            |                        all hops/order
   |                            |                        B checks local authz
   |<------------------------------------------------------------|
   | 200 response only if all checks pass                         |
~~~

**Vé PT được phát cho chính `targetService`.** Nếu A xin PT cho `https://reports.example.org/api/v1/summary` nhưng B xác minh với `https://reports.example.org/api/v1/admin`, CAS phải từ chối `INVALID_SERVICE` hoặc tương đương; B không nên “sửa” bằng cách chấp nhận mọi service URL.

### 3.3. Proxy chain trong phản hồi CAS

CAS XML minh họa:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
    <cas:proxies>
      <cas:proxy>https://gateway.example.org/pgtCallback</cas:proxy>
      <cas:proxy>https://portal.example.org/pgtCallback</cas:proxy>
    </cas:proxies>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

**Thứ tự từ trên xuống là mới nhất trước**: trong ví dụ, Portal đã proxy trước, sau đó Gateway proxy tiếp; Gateway là proxy gần Reports API B nhất. Khi B đòi chính xác chuỗi hai hop `[Gateway, Portal]`, các chuỗi `[Portal, Gateway]`, `[Gateway, Evil]`, `[Gateway, Portal, Evil]` đều phải bị loại.

**Những URL trong `<cas:proxy>` là định danh proxy callback** được CAS gắn vào lịch sử proxy, **không phải** origin URL của người dùng, email, hostname lấy từ HTTP `Host` hay ẩn danh hóa của các LB hops.

## 4. Hai ranh giới tin cậy độc lập cần kiểm thử

### 4.1. Ranh giới A: CAS Server → PGT receptor

CAS Server kiểm tra certificate/HTTPS của **PGT callback endpoint** để chứng minh CAS kết nối được tới **đúng Portal A**. Tuy nhiên việc CAS kiểm tra certificate của Portal A **không tự giúp Portal A chứng minh rằng request inbound được gửi bởi CAS Server**. A nên có bảo vệ nguồn request phù hợp: mTLS nếu tổ chức triển khai, network ACL/service mesh identity, dedicated ingress, strict trusted gateway và token/correlation controls. Không dùng `X-Forwarded-For: cas.example.org` do client tự khai.

**Lỗi nghiêm trọng:** một browser tự gọi receptor với `pgtId=PGT-attacker` và `pgtIou=PGTIOU-xyz` khiến A ghi đè mapping thật. Nếu sau đó response từ CAS dùng cùng IOU, A có thể dùng nhầm PGT của attacker. Cần chặn giả callback và **không overwrite unverified PGTIOU mapping** khi có duplicate/conflict.

### 4.2. Ranh giới B: B → CAS /proxyValidate

Reports B **không được tin PT**, `<cas:user>` hoặc `<cas:proxies>` chỉ vì chúng xuất hiện trong request của A. **B phải gọi CAS Server xác minh PT** theo exact service URL bằng TLS đúng trusted CAS host, kiểm tra proxy chain **từ kết quả validate đã xác minh**, sau đó áp dụng local admission/authorization.

**Lỗi nghiêm trọng:** B chỉ xem `cas:user=alice` hoặc chấp nhận mọi proxy bằng `acceptAnyProxy=true`. Attacker sở hữu một dịch vụ CAS-proxied khác có thể lấy PT đại diện alice cho B và đi qua một chain chưa được phê duyệt.

### 4.3. Vì sao một chặng tin cậy không đủ?

Một chuỗi có thể có proxy gần nhất đã được tin cậy nhưng bên dưới có chặng không được phép:

~~~text
CAS login -> Unknown Partner X -> Trusted Gateway -> Reports B

CAS reports:
  [Trusted Gateway, Unknown Partner X]
~~~

Nếu B chỉ so phần tử đầu tiên `Trusted Gateway` hoặc dùng “contains trusted hostname”, B có thể cho một hop không được phép xuất hiện trong lịch sử. **Đối với ứng dụng có chính sách strict chain, phải xét toàn bộ list với exact ordered match**. Một policy khác chỉ yêu cầu immediate proxy là chấp nhận được **chỉ khi business/security owners có chủ đích ủy quyền downstream trust cho proxy đó**; không mặc định như vậy trong bài kiểm thử này.

## 5. Quy tắc chấp nhận proxy chain: exact, ordered, bounded

Đặt policy cho Reports B:

~~~text
Allowed (most recent first):
  [https://gateway.example.org/pgtCallback,
   https://portal.example.org/pgtCallback]

Optional allowed direct path (nếu business phê duyệt riêng):
  [https://portal.example.org/pgtCallback]

Not allowed:
  [https://portal.example.org/pgtCallback,
   https://gateway.example.org/pgtCallback]     # đảo thứ tự

  [https://gateway.example.org/pgtCallback,
   https://untrusted.example.net/pgtCallback]   # hop độc hại

  [https://gateway.example.org/pgtCallback,
   https://portal.example.org/pgtCallback,
   https://untrusted.example.net/pgtCallback]   # hop chèn thêm
~~~

### 5.1. Các câu hỏi phải trả lời trong policy

1. B nhận **ST trực tiếp**, PT từ Portal A, PT từ chuỗi A→Gateway hay cả ba?
2. Một chuỗi rỗng `[]` có được chấp nhận không? Nếu endpoint chỉ dành cho **proxy delegation**, cần **deny empty**.
3. URL callback nào được tin **chính xác**, bao gồm scheme, host, port, path và context root?
4. Có được **ủy quyền tiếp** qua Gateway hay không? Nếu có, được bao nhiêu hops và đúng thứ tự nào?
5. Có partner/tenant riêng cần allowlist chain khác nhau? Nếu có, route/targetService policy phải phân biệt.
6. Proxy chain được đọc **từ CAS validation response**, không phải HTTP header tự khai?
7. Policy có yêu cầu max hops, không duplicate/cycle, only HTTPS và no unexpected URL encoding?
8. Nếu chain missing/invalid/unknown, có **fail closed** trước khi tạo Authentication/permissions không?
9. Có test rằng **không cấp quyền admin chỉ vì CAS principal và allowed chain hợp lệ** không?

### 5.2. So khớp URL và regex

Trong Apereo Java CAS Client, `allowedProxyChains` có thể khai báo từng chuỗi được cho phép; từng chuỗi có các URL phân cách bằng khoảng trắng. Các phiên bản có thể hỗ trợ **regex URL bắt đầu bằng `^`**. **Ưu tiên exact URL allowlist**, vì regex quá rộng như `^https://.*example.org/.*` hoặc regex unanchored có thể nhận thêm host/path ngoài ý muốn. Cần test matching implementation/version thực tế.

Không tự “chuẩn hóa” proxy URL bằng cách:
- Bỏ scheme HTTP/HTTPS.
- Chỉ so hostname và bỏ path.
- Chỉ kiểm tra `contains("portal")`.
- Bỏ port vì “proxy đang sau load balancer”.
- Sắp xếp danh sách proxy trước khi so: **thứ tự là dữ kiện an ninh**.
- Chấp nhận một prefix được phép trong khi phần đuôi chứa hop lạ.
- Coi IP/network hop `X-Forwarded-For` là CAS proxy chain.

CAS protocol nói **proxy mới đi qua gần đây nhất nằm đầu** danh sách; cho nên cấu hình allowlist phải theo thứ tự phản hồi CAS, không phải thứ tự ngược chiều từ nguồn đến đích trong sơ đồ vẽ. Test integration cần khẳng định từng hop và order đúng với CAS/Java Client version được sử dụng.

### 5.3. Cấu hình acceptAnyProxy có thể phá kiểm thử

Spring Security CAS reference có ví dụ legacy dùng:

~~~xml
<property name="acceptAnyProxy" value="true"/>
~~~

Ví dụ này **chỉ minh họa tính năng**, không phải một khuyến nghị production cho hệ thống cần giới hạn proxy chain. Với Reports B có strict policy, phải dùng **`acceptAnyProxy=false` + explicit allowedProxyChains**, đồng thời kiểm tra các policy khác trong provider/service layer.

**`allowEmptyProxyChain`** là lựa chọn riêng trên một số phiên bản `Cas20ProxyTicketValidator`; nếu B chỉ nhận PT qua proxy đã xác định, đặt/tạo test **không chấp nhận chuỗi rỗng**. Nếu B vừa nhận ST trực tiếp vừa PT, có thể cần policy tách route/matcher thay vì biến empty chain được phép cho mọi tài nguyên.

## 6. Kiểm thử PGT callback: danh sách lỗi mang tính bảo mật

### 6.1. HTTPS và certificate ở cả hai chiều

PGT URL phải là **HTTPS**; CAS Server phải verify certificate chain, hostname và thời hạn. Khi Portal A ở sau ingress, CAS nhìn thấy **public hostname** được đăng ký, không phải tên pod; certificate không khớp public hostname có thể làm PGT callback thất bại.

Ở phía A, **không suy ra caller chính là CAS chỉ vì request đến qua HTTPS**. HTTPS chứng minh A cho caller, không tự chứng minh caller cho A nếu thiếu mTLS/trusted ingress. Dùng trust boundary có thể thực thi:
- mTLS client identity của CAS Server/approved gateway, nếu có.
- Firewall/IP allowlist chỉ như một lớp phụ; không dùng HTTP forwarded IP header làm chứng cứ.
- Dedicated ingress route, WAF/rate limits, machine identity, no direct pod access.
- Ghi PGTIOU→PGT **sau khi** callback đạt chính sách source trust; duplicate không được overwrite.
- Correlate qua IOU trong CAS validation response đã xác minh trước khi PGT được phép sử dụng.

### 6.2. Đúng mã phản hồi 200

CAS protocol quy định callback GET thành công phải trả **HTTP 200 OK** để CAS nhận biết service receptor sẵn sàng. Khi callback trả status khác 200, PGT thường sẽ không được cấp qua flow thông thường; tài liệu cho phép CAS xử lý một số **3xx redirects** theo profile nên không khẳng định “mọi 302 luôn từ chối”.

**Production recommendation:** callback URL phải trỏ thẳng receptor cuối, **không phụ thuộc redirects 302**, vì có thể gây mất query, thay hostname, TLS/downgrade hoặc credentials leak. Thử:
- 200 sau khi commit IOU→PGT.
- 500/timeout khi store unavailable: **không** ack giả 200.
- 302 tới trang login: **lỗi** với server-to-server callback.
- 401 từ Spring form login filter: receptor matcher bị đặt sai.
- 403 do mTLS/network policy: test fail-closed khi CAS identity sai, success khi đúng.
- 200 được trả trước khi write store hoàn tất: phát hiện race IOU resolution.

### 6.3. Không có browser session ở PGT receptor

PGT receptor là **callback CAS Server → Portal A**, không có lý do dùng cookie `JSESSIONID` của browser để ghép PGT. Một receptor đúng:
- Không tạo local user/session chỉ vì nhận `pgtId`.
- Không phụ thuộc vào cookie người dùng.
- Không xuất `pgtId`, `pgtIou` trong HTML, JS, response body.
- Không ghi chúng vào Nginx access log/APM tracing hoặc error message.
- Chỉ lưu PGT trong secret storage có TTL, encryption/ACL, cleanup.
- Cho phép phản hồi ticket validation đang chờ đi tới đúng mapping theo IOU.

### 6.4. Rủi ro callback giả và duplicate IOU

| Case | Kỳ vọng bảo mật |
| --- | --- |
| Request từ browser có `pgtId/IOU` trông đúng format. | **Deny** nếu không đạt CAS-origin machine trust; không ghi store. |
| Hai callback cùng IOU, PGT khác nhau. | **Conflict/deny**, không overwrite PGT đầu hoặc chấp nhận ngẫu nhiên. |
| Duplicate callback giống hệt từ nguồn đã xác thực. | Có thể xử lý idempotent theo policy, không cấp thêm quyền, audit. |
| IOU rỗng hoặc PGT rỗng. | Deny input, không tạo mapping. |
| PGTIOU không có trong response CAS validation. | Không dùng PGT vừa lưu để gọi `/proxy`. |
| CAS validation trả IOU nhưng store lookup miss. | Không có PGT khả dụng; không tự ghép theo username/time. |
| Callback đến trước validation response. | Lưu có TTL ngắn rồi correlate khi response đến. |
| Callback đến sau validation response. | Correlation mechanism phải đợi/bounded retry theo flow; không lấy “latest”. |
| Callback đi vào Node A, validation đi vào Node B. | Store shared/consistent hoặc affinity được bảo đảm có failover tests. |
| Store ghi lỗi nhưng receptor trả 200. | Test FAIL: CAS tin đã giao PGT nhưng Portal không có. |
| Callback có redirect tới host lạ. | Từ chối/cấu hình lại receptor; không leak PGT qua Location. |
| Query parameters được proxy log nguyên. | Security incident/test FAIL; redaction ở tất cả hops. |

**Chú ý tính một chiều:** CAS Server tự verify callback certificate của Portal không ngăn được một attacker gọi receptor nếu receptor public. Cần kiểm tra **inbound peer** riêng; nếu không có mTLS, phải có hệ thống network trust và correlation thích hợp. **IOU bản thân không phải chữ ký số**, nên không được coi việc chỉ nhìn thấy IOU là bằng chứng caller đã được CAS xác thực.

## 7. Kiểm thử PT và từ chối proxy chain ngoài chính sách

### 7.1. Bảo vệ tại Reports API B

B phải thực thi thứ tự:

~~~text
receive PT from Portal A
 -> validate exact service URL and PT with trusted CAS /proxyValidate
 -> parse authenticated CAS response (not raw client XML)
 -> obtain complete proxy chain
 -> compare against explicit ordered allowlist
 -> check local account status/tenant and resource permission
 -> grant only approved business access
~~~

**Không được ngược:** tạo Spring `Authentication` từ raw `ticket=PT-*`, sau đó dùng proxy chain cho audit. Chain policy phải nằm trong **authentication admission** trước khi business authorization xử lý resource.

### 7.2. Bảng test chain có thể tự động hóa

Giả sử chỉ cho phép:

~~~text
APPROVED:
[https://gateway.example.org/pgtCallback,
 https://portal.example.org/pgtCallback]
~~~

| CAS trả chain | Kỳ vọng | Lý do |
| --- | --- | --- |
| `[gateway, portal]` | **ACCEPT** sau PT/service validation. | Đúng 2 hops và thứ tự. |
| `[portal, gateway]` | **DENY**. | Đảo thứ tự, không cùng ủy quyền. |
| `[gateway, unknown]` | **DENY**. | Một hop không được tin. |
| `[unknown, portal]` | **DENY**. | Hop gần B không được tin. |
| `[gateway, portal, unknown]` | **DENY**. | Extra hop/prefix-only match. |
| `[gateway]` | **DENY** trừ khi được phê duyệt riêng. | Thiếu một hop yêu cầu. |
| `[]` hoặc thiếu `cas:proxies` | **DENY** ở endpoint chỉ nhận PT. | Không có bằng chứng chuỗi proxy hợp lệ. |
| `[gateway, gateway]` | **DENY**. | Duplicate/cycle không thuộc allowlist. |
| URL thay `https` thành `http` | **DENY**. | Identity/transport đã đổi. |
| URL cùng host nhưng path khác | **DENY**. | Callback identity phải exact. |
| URL có domain suffix giả như `portal.example.org.evil.net` | **DENY**. | Không được substring match. |
| URL có port khác | **DENY** nếu không được approve. | Callback identity khác. |
| Chain đúng nhưng PT dành service khác | **DENY**. | `targetService`/service binding fail. |
| Chain đúng nhưng PT đã được CAS validate trước | **DENY** theo one-time CAS semantics, trừ app cache behavior được thiết kế/test riêng. | Replay. |
| Chain đúng nhưng CAS validation thất bại | **DENY**. | Không có chứng cứ CAS. |
| Chain đúng, CAS valid, user local DISABLED | **DENY**. | Identity không thay local admission. |
| Chain đúng, user active nhưng thiếu `reports:read` | **403**. | Local authorization riêng. |

**Cảnh báo kiểm thử:** một mock CAS endpoint **không có chữ ký** hoặc một XML fixture bị chỉnh sửa không chứng minh có thể “tấn công CAS Server”. Mục tiêu unit/integration tests là **kiểm tra ứng dụng có validate proxy list mà CAS trả**, trong khi E2E cần CAS test server thực sự phát PT đúng protocol.

### 7.3. Một “success” chưa đủ

Nếu happy-path `PT` trả HTTP 200, ít nhất phải chạy thêm:
- `acceptAnyProxy=true` mutation test: một chain lạ **phải không** biến thành ACCEPT.
- `allowedProxyChains` rỗng/missing: **fail closed**, không chấp nhận mọi proxy.
- Thử **long chain** và duplicate hop.
- Dùng đúng URL nhưng khác uppercase/path/encoding theo policy.
- Thử expired PT, replay, wrong service URL và CAS Server timeout.
- Thử user chưa được cấp quyền ở Reports B.

## 8. Spring Security: các thành phần liên quan và cấu hình mẫu

Tích hợp CAS nằm ở các lớp của Spring Security và Apereo Java CAS Client; API/package/version có thể thay đổi giữa Spring Security 5/6/7, Boot Jakarta, và CAS client releases. **Không copy cấu hình legacy XML của một bài cũ để trộn với các class mới mà chưa compile/test.**

| Thành phần | Vai trò |
| --- | --- |
| `CasAuthenticationEntryPoint` | Redirect browser đến CAS `/login` với service URL. |
| `CasAuthenticationFilter` | Nhận ST ở login callback hoặc PT trong mô hình stateless tùy matcher. |
| `ServiceProperties` | Xác định chính xác service URL, `authenticateAllArtifacts` khi cần PT. |
| `ServiceAuthenticationDetailsSource` | Tạo service URL dùng validate artifact với request, cần review sau reverse proxy. |
| `CasAuthenticationProvider` | Gọi ticket validator, dùng `CasProxyDecider` và nạp `UserDetails/GrantedAuthority`. |
| `Cas20ServiceTicketValidator` | Xác minh ST, không dùng cho PT. |
| `Cas20ProxyTicketValidator` | Xác minh PT và proxy chain; cấu hình `allowedProxyChains` và `acceptAnyProxy`. |
| `CasProxyDecider` | Một lớp kiểm soát proxy được cung cấp ở Spring Security, tùy provider/version. |
| `ProxyGrantingTicketStorage` | Store IOU→PGT, cần shared/secure storage cho cluster. |
| `Cas20ProxyReceivingTicketValidationFilter` | Filter CAS Client nhận/validate tickets và hỗ trợ PGT receptor trong mô hình phù hợp. |
| `StatelessTicketCache` | Cache xác thực PT cho stateless remoting trong Spring Security; cần TTL/scope và security review. |

### 8.1. Tránh acceptAnyProxy

**Đây là một mảnh mã cấu hình Java trong project có dependency Apereo Java CAS Client**, không phải chương trình Java SE tự chạy; dùng class/method theo release bạn đã khóa phiên bản:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.apereo.cas.client.validation.Cas20ProxyTicketValidator;
import org.apereo.cas.client.validation.ProxyList;

public class ProxyValidatorConfiguration {

    public Cas20ProxyTicketValidator strictProxyValidator() {
        Cas20ProxyTicketValidator validator =
            new Cas20ProxyTicketValidator(
                "https://cas.example.org/cas");

        // Không chấp nhận mọi proxy tùy ý.
        validator.setAcceptAnyProxy(false);
        validator.setAllowEmptyProxyChain(false);

        // CHÚ Ý: thứ tự theo <cas:proxies>, mới nhất trước.
        List<String[]> chains = new ArrayList<>();
        chains.add(new String[] {
            "https://gateway.example.org/pgtCallback",
            "https://portal.example.org/pgtCallback"
        });

        validator.setAllowedProxyChains(new ProxyList(chains));
        return validator;
    }
}
~~~

**Giới hạn:** đoạn Java trên cấu hình **validator của B**, không tự xây `SecurityFilterChain`, `CasAuthenticationProvider`, `AuthenticationManager`, PGT receiver, service URL hoặc tài khoản local. Một số phiên bản khác dùng namespace `org.jasig.cas.client` hay factory/property-style config; cần đối chiếu dependency tree, JavaDoc của release thực, và **test chain acceptance bằng CAS response**. Giữ `acceptAnyProxy=false` kể cả khi đã khai báo allowlist.

### 8.2. Cấu hình filter CAS Client không đồng nghĩa Spring Security provider

Apereo Java CAS Client có các thuộc tính cấu hình như:

~~~properties
casServerUrlPrefix=https://cas.example.org/cas
service=https://reports.example.org/api/v1/summary
proxyReceptorUrl=/login/cas/proxyreceptor
proxyCallbackUrl=https://reports.example.org/login/cas/proxyreceptor
acceptAnyProxy=false
allowedProxyChains=https://gateway.example.org/pgtCallback https://portal.example.org/pgtCallback
~~~

Đây là **ví dụ các ý nghĩa property ở Java CAS Client**; **không phải file `application.properties` drop-in** của Spring Boot. Tên prefix/namespace của starter khác nhau theo version. Với **Reports B chỉ validate PT**, thường **không cần B có `proxyReceptorUrl`** trừ khi B cũng muốn xin PGT để proxy tiếp. Đừng mở receptor không dùng; nếu dùng, B cần secret store/trust riêng.

Trong CAS Client, `proxyReceptorUrl` là **path tương đối context** mà filter lắng nghe callback, còn `proxyCallbackUrl` là **URL HTTPS đầy đủ** gửi cho CAS Server. Phải trỏ tới **cùng receptor thực**; callback public host/port/context path không đồng bộ sẽ khiến PGT bị mất.

### 8.3. CasProxyDecider là một lớp kiểm soát riêng

Spring Security CAS còn có các class `RejectProxyTickets`, `AcceptAnyCasProxy` và `NamedCasProxyDecider` theo API/version. Một hệ thống có thể có **hai cửa**:
1. **CAS client ticket validator** xác minh PT và `allowedProxyChains`.
2. **Spring provider `CasProxyDecider`** kiểm tra proxy list mà validator đưa về.

Không được dùng `AcceptAnyCasProxy` ở lớp thứ hai rồi kết luận “không sao vì lớp đầu có thể reject” nếu policy doanh nghiệp yêu cầu **defense in depth**. Hai cấu hình phải **cùng mục tiêu**, được test riêng và cùng reject unknown proxies. Đọc defaults theo version: `RejectProxyTickets` có thể từ chối toàn bộ PT dù `Cas20ProxyTicketValidator` đã accept; đừng chữa bằng cách đổi sang AcceptAny mà không review requirements.

### 8.4. Service URL và stateless remoting

Spring Security CAS docs mô tả mô hình **stateless client**: PT được gửi đến một endpoint không phụ thuộc HTTP session; `ServiceProperties.authenticateAllArtifacts=true` và `ServiceAuthenticationDetailsSource` giúp validate ticket theo request service URL. Nếu URL bên ngoài khác URL nội bộ do TLS termination/load balancer, phải cấu hình **public service identity ổn định** và trusted forwarded-header policy.

Spring Security CAS cũng có `StatelessTicketCache` để **cache CasAuthenticationToken sau lần CAS validate đầu**. Đặc điểm này quan trọng: CAS **tự nó chỉ cho validate PT một lần**, nhưng khi Spring cache kết quả, **ứng dụng vẫn có thể tiếp nhận cùng PT ở lần request khác mà không gọi CAS lần nữa**, tùy cache policy. Vì vậy:
- Thời gian/scope cache phải được chọn theo credential lifetime, endpoint và risk.
- PT không được tự trở thành một **access token tái sử dụng vô hạn**.
- Không suy rằng CAS sẽ ngăn mọi replay tới B nếu B có cache nhận lại PT.
- Nếu token được cache giữa URLs, phải có kiểm soát targetService/resource binding đủ chặt.
- Mọi quyết định authority/tenant/resource vẫn cần local checks và revocation SLA.

**Testing phải bao gồm cả cache hit và cache miss**, đặc biệt khi một PT cho `/api/v1/summary` bị thử lại ở `/api/v1/admin`.

## 9. PGT callback: các trường hợp nhiều node và race

### 9.1. Hai request login đồng thời

~~~text
User alice:
  Login browser tab A -> ST-1 -> CAS PGT callback IOU-1/PGT-1
  Login browser tab B -> ST-2 -> CAS PGT callback IOU-2/PGT-2

Không được:
  map "alice" -> PGT mới nhất và trả PGT-2 cho tab A

Bắt buộc:
  IOU-1 -> PGT-1 theo ST-1 verified validation response
  IOU-2 -> PGT-2 theo ST-2 verified validation response
~~~

**Ghép theo IOU**, không theo principal username, HTTP session ID, timestamp hoặc “current thread”, vì callback từ CAS Server có thể vào node khác/thread khác.

### 9.2. Callback trước hoặc sau verification response

Gợi ý state machine:

~~~text
CALLBACK_RECEIVED(IOU, PGT)
     |
     | verify inbound trust, validate input
     v
PENDING_PGT_IOU_STORE(IOU -> secret-PGT, short TTL)
     |
     | ST validation response from trusted CAS
     | contains matching <cas:proxyGrantingTicket>IOU
     v
CORRELATED_AND_APPROVED
     |
     | business call requests allowed targetService
     v
PGT used server-to-server at CAS /proxy
     |
     v
PT for targetService, never expose PGT to browser
~~~

Không đưa PGT vào JSP/JSON phản hồi, JavaScript, URL redirect hoặc browser storage. Nếu correlation không hoàn thành trong thời gian chờ, phải **expire pending mapping**, không dùng lại IOU vô hạn. CAS protocol không bắt buộc một thời gian cụ thể cho application storage; chọn TTL theo observed latency và risk, với upper bound.

### 9.3. Shared store và atomic semantics

Trong cluster:
- Callback Node A ghi IOU→PGT vào shared storage.
- ST validation Node B đọc theo IOU từ XML response.
- Nếu consistency yếu, Node B có thể chưa thấy mapping và báo fail dù callback 200; cần read-after-write/atomic store theo design.
- **Duplicate IOU** không được overwrite một PGT đã lưu trước đó; dùng SETNX/CAS hoặc DB unique.
- PGT là secret, cần encrypt at rest/in transit, restricted ACL/TTL và expiry cleanup.
- Nếu shared store unavailable, receptor **không trả giả 200** rồi tiếp tục SSO theo giả định PGT có sẵn.
- Test failover giữa Node A/B và xóa PGT khi CAS logout/local offboarding theo policy.

### 9.4. Trường hợp callback bị router hoặc security filter chặn

| Kết quả callback | Nghi vấn |
| --- | --- |
| 302 tới `/login` | Spring form/CAS EntryPoint intercept một server-to-server receptor không có session. |
| 401/403 | Inbound machine trust/mTLS chưa đúng hoặc filter authorization matcher sai. |
| 404 | `proxyReceptorUrl` và `proxyCallbackUrl` không cùng context/matcher. |
| 500 | PGT store unavailable, parser error, service misconfiguration. |
| 200 nhưng no PGTIOU in validation response | CAS policy không cấp PGT hoặc callback response/correlation chưa hợp lệ. |
| TLS certificate error từ CAS | Public certificate/hostname/chain/expiry của receptor sai. |
| Có PGTIOU nhưng A không tìm thấy PGT | IOU store khác node, race, TTL quá ngắn hoặc map conflict. |

**Không giải quyết bằng cách public `/proxyreceptor` không hạn chế, disable certificate checking hoặc ghi PGT vào browser cookie.** Sửa đúng nơi: receptor route, CAS trust/certificate, shared IOU store, response timing, service registration.

## 10. Một test architecture đáng tin

### 10.1. Các mức kiểm thử

| Mức | Thành phần cần chạy | Giá trị |
| --- | --- | --- |
| **Unit** | Proxy chain policy, callback correlation/state machine; mock verified CAS outcomes. | Nhanh, kiểm chứng exact/order/deny semantics. |
| **Component** | CAS client validator + mock CAS validation endpoint, PGT receptor + mock inbound caller. | Test wiring, XML parsing, `allowedProxyChains`, status handling. |
| **Integration** | Portal A, Reports B, CAS test server, TLS certificates, test IdP/users. | Kiểm chứng thật ST→PGT callback→PT→proxyValidate. |
| **E2E multi-node** | A/B ≥2 nodes, shared PGT store/session/cache, ingress/firewall. | Detect race, node failover, callback routing, TLS/source trust. |
| **Security/adversarial** | Attacker giả callback/chain, wrong service, replay, SSRF attempts. | Chứng minh fail-closed, không cần credential production. |
| **Chaos** | CAS stop, store timeout, dropped callbacks, DNS rotation, pod restart. | Test failure modes, retry bounds và cleanup. |

**Quan trọng:** đơn vị test không thể giả lập “CAS cryptographically validated response” bằng việc đặt boolean true trong request công khai. Test double chỉ là bằng chứng cho **application policy sau validation**. E2E phải xác minh thực sự với CAS Server và TLS trust.

### 10.2. Dữ liệu giả lập có kiểm soát

~~~text
CAS:     https://cas.test.example/cas
Portal:  https://portal.test.example/app
Receptor:https://portal.test.example/app/login/cas/proxyreceptor
B:       https://reports.test.example/api/v1/summary
Allowed proxy list: [Gateway, Portal] (most recent first)
Users:   alice ACTIVE reports:read; bob ACTIVE no reports:read
Tickets: opaque fresh ST/PT/PGT from test CAS (never prod)
~~~

Đối với các bài test âm, dùng **test CAS service registry** để bật/tắt proxy permission, cấp PT qua proxy lạ, dùng callback URL sai. Không chép PGT thật vào fixture, log, CI snapshot hay thư mục public.

### 10.3. Cách ghi bằng chứng QA

Mỗi test case lưu:
- Test ID, CAS/client/Spring Security versions và config policy version.
- Source service/targetService identifier (không token).
- Callback outcome: HTTP status, inbound identity verified yes/no, IOU presence boolean, store outcome.
- CAS validation result code và proxy chain **đã redact hoặc canonical partner refs**, không log secret.
- Chain decision ALLOW/DENY và local account/authority decision.
- Số lần CAS validate được gọi, cache hit/miss, replay outcome.
- Node/ingress path, correlation ID được tạo riêng (không reuse `pgtIou` trong metrics).
- Expected vs actual; lỗi xảy ra ở CAS, gateway, Spring validator hay business layer.

## 11. Integration test scenarios: PGT callback và CAS protocol

### 11.1. Happy path

1. Tạo một CAS test service registry chỉ cho Portal A nhận PGT và proxy tới B.
2. Browser test login CAS, nhận ST cho service URL chính xác của A.
3. Portal A gọi CAS `/serviceValidate` kèm `pgtUrl=https://portal.../proxyreceptor`.
4. CAS Server kiểm tra TLS certificate của receptor, gọi HTTPS GET với `pgtId, pgtIou`.
5. Receptor kiểm inbound peer, ghi IOU→PGT, trả 200 sau persist.
6. CAS trả validation success với `cas:user` và **`cas:proxyGrantingTicket=PGTIOU...`**.
7. A tìm PGT theo exact IOU; A gọi `/proxy` cho **targetService B**, nhận PT.
8. A gọi B bằng PT; B gọi `/proxyValidate`.
9. CAS trả username và **proxies list**; B kiểm exact ordered allowed chain.
10. B dùng local permissions để trả 200 cho alice/deny bob.

Đồng thời xác minh PGT không xuất hiện ở URL/response/browser, và callback server-to-server không cần browser cookie.

### 11.2. Callback từ nguồn giả

Dùng một HTTP client chưa được xác thực bởi inbound trust gửi:

~~~http
GET /app/login/cas/proxyreceptor?pgtId=PGT-fake&pgtIou=PGTIOU-fake HTTP/1.1
Host: portal.test.example
~~~

Kỳ vọng request bị firewall/mTLS/gateway **deny**, hoặc bị receptor fail-closed theo trust contract. Không có mapping được ghi, không có session/login, không tạo PT. Một response 200 nhưng mapping vẫn được tạo từ client tùy ý là **test FAIL nghiêm trọng**.

### 11.3. Callback không có/không khớp IOU

- Callback có IOU A, CAS validation trả IOU B → không chọn PGT A.
- CAS validation không có PGTIOU do proxy bị cấm → không tự gọi CAS `/proxy`.
- Callback có duplicate IOU nhưng PGT khác → conflict, không overwrite.
- Callback đến quá muộn so TTL → không dùng PGT stale.
- User A và B cùng login đồng thời → đúng mapping từng IOU.
- Callback Node 1, validation Node 2 → đọc được store chung, không lệ thuộc local memory.

### 11.4. Callback HTTP lỗi và TLS

- HTTPS certificate expired/hostname wrong tại receptor: CAS không cấp PGT qua flow thường.
- Callback route bị redirect tới login: CAS callback không thành công như thiết kế.
- Network timeout trước khi persist: retry theo CAS/client contract, không ACK 200 giả.
- Store ghi xong nhưng response 200 bị mất: duplicate callback nếu xảy ra phải idempotent, không leak/overwrite.
- Security layer chặn callback từ một CAS instance không thuộc allowlist: deny đúng.
- IdP/CAS outage: không fallback dùng PGT cũ vô hạn hoặc bỏ proxy chain validation.

## 12. Test matrix: chain không được phép và ticket binding

| Case | CAS/chain/ticket condition | Kỳ vọng tại Reports B |
| --- | --- | --- |
| PT valid, exact chain | [Gateway, Portal], target B, active alice | 200 nếu có quyền. |
| PT valid, chain đảo | [Portal, Gateway] | Deny. |
| PT valid, unknown first hop | [Evil, Portal] | Deny. |
| PT valid, unknown last hop | [Gateway, Evil] | Deny. |
| PT valid, extra proxy hop | [Gateway, Portal, Evil] | Deny. |
| PT valid, missing hop | [Gateway] | Deny nếu policy đòi cả 2. |
| PT valid, empty chain | [] | Deny nếu proxy-only endpoint. |
| PT valid, duplicated hop | [Gateway, Gateway] | Deny. |
| PT valid, wrong scheme | http://gateway... | Deny, không “normalize” sang HTTPS. |
| PT valid, same host wrong path | /otherCallback | Deny. |
| PT valid, suffix trick | portal.example.org.evil.net | Deny. |
| PT valid, wrong port | :8443 ngoài policy | Deny. |
| PT valid, targetService B2 | Validate B1 | CAS INVALID_SERVICE; không tạo auth. |
| PT already validated at CAS | Repeat to /proxyValidate | CAS reject; nếu cache active cần test cache semantics. |
| Raw fake PT | Ticket không do CAS phát | CAS reject. |
| Correct chain nhưng CAS chưa validate | XML/client claim tự khai | Deny. |
| Correct chain nhưng local account DISABLED | Legit CAS principal | Deny admission. |
| Correct chain nhưng user thiếu permission | User active, wrong role | 403 authz. |
| acceptAnyProxy misconfiguration | Unknown chain would pass | Test config FAIL. |
| No allowed proxy chains | New proxy accepted implicitly | Test FAIL. |
| Wrong CAS server host/cert | Validation không đáng tin | Fail closed, không skip TLS verify. |
| Filter chỉ dùng Cas20ServiceTicketValidator | PT từ proxy hợp lệ | Không chấp nhận PT; phải cấu hình đúng validator nếu service cần PT. |
| Wrong Spring provider proxy decider | Validator pass nhưng decider reject | Auth fail có chủ đích; sửa policy, không chuyển accept-any bừa. |
| Wrong cache scope | PT từ summary được reuse trên admin | Deny resource access theo scope, kiểm soát TTL. |

## 13. Java 17 runnable: mô phỏng callback PGT và exact proxy-chain policy

Chương trình sau **chạy độc lập bằng JDK 17**, chỉ dùng Java Standard Library. Nó kiểm thử **chính sách ứng dụng**, không phải CAS Client, không gọi CAS Server, không verify TLS/mTLS thật và không parse CAS XML.

**Giả định thử nghiệm:** các boolean `trustedCasPeer`, `casValidationSuccessful` và `exactTargetService` chỉ đại diện các kiểm tra **đã được tầng xác thực/gateway/CAS validator thực hiện**. Không bao giờ lấy chúng từ query/header/JSON của caller để quyết định authentication trong production. PGT IOU/pgt values ở đây chỉ là chuỗi giả, **không có credential thật**.

Tệp **`CasProxyPolicyDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class CasProxyPolicyDemo {

    private static final String PORTAL =
        "https://portal.example.org/pgtCallback";
    private static final String GATEWAY =
        "https://gateway.example.org/pgtCallback";
    private static final String CALLBACK =
        "https://portal.example.org/login/cas/proxyreceptor";

    // CAS reports most recently visited proxy first.
    private static final List<String> APPROVED =
        List.of(GATEWAY, PORTAL);

    record ValidatedTicket(boolean casValidationSuccessful,
                           boolean exactTargetService,
                           boolean unusedAtCas,
                           List<String> proxies) {}

    static String decide(ValidatedTicket t) {
        if (!t.casValidationSuccessful()) return "DENY_CAS_VALIDATION";
        if (!t.exactTargetService()) return "DENY_TARGET_SERVICE";
        if (!t.unusedAtCas()) return "DENY_REPLAY";
        if (t.proxies() == null || t.proxies().isEmpty())
            return "DENY_EMPTY_CHAIN";
        if (!APPROVED.equals(t.proxies()))
            return "DENY_UNTRUSTED_CHAIN";
        return "ALLOW";
    }

    static final class Receptor {
        private final Map<String, String> pending =
            new ConcurrentHashMap<>();

        String receive(boolean trustedCasPeer, String calledUrl,
                       String iou, String pgt) {
            if (!trustedCasPeer) return "DENY_CALLBACK_PEER";
            if (!CALLBACK.equals(calledUrl)) return "DENY_CALLBACK_URL";
            if (iou == null || !iou.startsWith("PGTIOU-")
                    || pgt == null || !pgt.startsWith("PGT-"))
                return "DENY_CALLBACK_FIELDS";

            String existing = pending.putIfAbsent(iou, pgt);
            if (existing == null) return "STORED";
            if (existing.equals(pgt)) return "DUPLICATE_IGNORED";
            return "DENY_IOU_CONFLICT";
        }

        String correlate(boolean validationFromCas, String verifiedIou) {
            if (!validationFromCas) return "DENY_UNVERIFIED_RESPONSE";
            if (verifiedIou == null) return "DENY_IOU_MISSING";
            String pgt = pending.remove(verifiedIou);
            return pgt == null ? "DENY_IOU_NOT_FOUND" : "MATCHED";
        }
    }

    public static void main(String[] args) {
        Receptor receptor = new Receptor();

        System.out.println("FAKE_CALLBACK=" + receptor.receive(
            false, CALLBACK, "PGTIOU-1", "PGT-1"));
        System.out.println("WRONG_CALLBACK=" + receptor.receive(
            true, "https://other.example.org/receptor",
            "PGTIOU-1", "PGT-1"));
        System.out.println("PGT_STORED=" + receptor.receive(
            true, CALLBACK, "PGTIOU-1", "PGT-1"));
        System.out.println("PGT_DUPLICATE=" + receptor.receive(
            true, CALLBACK, "PGTIOU-1", "PGT-1"));
        System.out.println("PGT_CONFLICT=" + receptor.receive(
            true, CALLBACK, "PGTIOU-1", "PGT-other"));
        System.out.println("UNVERIFIED_XML=" + receptor.correlate(
            false, "PGTIOU-1"));
        System.out.println("OTHER_IOU=" + receptor.correlate(
            true, "PGTIOU-other"));
        System.out.println("MATCH_IOU=" + receptor.correlate(
            true, "PGTIOU-1"));
        System.out.println("REUSED_IOU=" + receptor.correlate(
            true, "PGTIOU-1"));

        System.out.println("CHAIN_OK=" + decide(
            new ValidatedTicket(true, true, true,
                List.of(GATEWAY, PORTAL))));
        System.out.println("REVERSED=" + decide(
            new ValidatedTicket(true, true, true,
                List.of(PORTAL, GATEWAY))));
        System.out.println("UNKNOWN=" + decide(
            new ValidatedTicket(true, true, true,
                List.of(GATEWAY, "https://evil.example.org/pgt"))));
        System.out.println("EXTRA_HOP=" + decide(
            new ValidatedTicket(true, true, true,
                List.of(GATEWAY, PORTAL,
                    "https://evil.example.org/pgt"))));
        System.out.println("EMPTY=" + decide(
            new ValidatedTicket(true, true, true, List.of())));
        System.out.println("WRONG_SERVICE=" + decide(
            new ValidatedTicket(true, false, true,
                List.of(GATEWAY, PORTAL))));
        System.out.println("REPLAY=" + decide(
            new ValidatedTicket(true, true, false,
                List.of(GATEWAY, PORTAL))));
        System.out.println("NO_CAS_PROOF=" + decide(
            new ValidatedTicket(false, true, true,
                List.of(GATEWAY, PORTAL))));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CasProxyPolicyDemo.java
java CasProxyPolicyDemo
~~~

**Stdout xác định:**

~~~text
FAKE_CALLBACK=DENY_CALLBACK_PEER
WRONG_CALLBACK=DENY_CALLBACK_URL
PGT_STORED=STORED
PGT_DUPLICATE=DUPLICATE_IGNORED
PGT_CONFLICT=DENY_IOU_CONFLICT
UNVERIFIED_XML=DENY_UNVERIFIED_RESPONSE
OTHER_IOU=DENY_IOU_NOT_FOUND
MATCH_IOU=MATCHED
REUSED_IOU=DENY_IOU_NOT_FOUND
CHAIN_OK=ALLOW
REVERSED=DENY_UNTRUSTED_CHAIN
UNKNOWN=DENY_UNTRUSTED_CHAIN
EXTRA_HOP=DENY_UNTRUSTED_CHAIN
EMPTY=DENY_EMPTY_CHAIN
WRONG_SERVICE=DENY_TARGET_SERVICE
REPLAY=DENY_REPLAY
NO_CAS_PROOF=DENY_CAS_VALIDATION
~~~

### 13.1. Vì sao các dòng này quan trọng?

- `FAKE_CALLBACK` không ghi PGT dù caller gửi IOU và PGT có prefix trông hợp lệ.
- `PGT_CONFLICT` không overwrite cùng IOU bằng PGT khác.
- `UNVERIFIED_XML` không thể lấy PGT khi chưa có ticket validation result được tin.
- `OTHER_IOU` không lấy “PGT mới nhất” của user.
- `MATCH_IOU` đúng một lần; `REUSED_IOU` không lấy lại secret.
- `CHAIN_OK` chỉ chấp nhận đủ hai proxy URLs đúng thứ tự CAS.
- `REVERSED`, `UNKNOWN`, `EXTRA_HOP` và `EMPTY` bị deny.
- `WRONG_SERVICE`, `REPLAY` và `NO_CAS_PROOF` bị từ chối dù proxy chain đúng.

**Những điều demo cố ý không làm:** không verify CAS XML response, certificate, chain, mTLS, principal, user role, ST/PT real state, PGT TTL, encrypted storage hoặc multi-node DB transaction. `ConcurrentHashMap` chỉ atomic trong **một JVM**, không thay distributed store. `unusedAtCas` mô phỏng CAS one-time validation; khi Spring `StatelessTicketCache` được bật, phải kiểm tra cache behavior riêng thay vì tin mỗi boolean. Prefix `PGT-`/`PGTIOU-` chỉ validate **hình thức**, không phải cryptographic authentication; production không được dùng nó làm chứng cứ caller.

## 14. Những lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hành động đúng |
| --- | --- | --- |
| ST login thành công nhưng không có PGT. | CAS không gọi được receptor HTTPS, service không được phép proxy, callback không 200. | CAS logs, public callback TLS/host, service registry, response IOU. |
| Callback 302 đến CAS login. | Security chain intercept receptor như browser page. | Cho server-to-server route đi đúng filter, giữ inbound trust. |
| Callback trả 200 nhưng IOU lookup null. | Store local node khác, persist bất đồng bộ, TTL quá ngắn. | Shared store atomic/read-after-write, multi-node test. |
| Có PGT trong query logs. | Proxy log full URI hoặc APM ghi request. | Redact gateway+backend, rotate compromised secrets. |
| CAS gửi PGT tới callback nhưng app chọn sai user. | Lookup PGT theo username, không theo IOU. | Correlate exact verified PGTIOU. |
| Duplicate callback đổi mapping. | PUT/overwrite map theo IOU. | SETNX/unique constraint; reject conflicts. |
| PT tới B trả INVALID_TICKET. | PT đã validate hoặc không phải vé CAS. | One-time semantics, không retry PT vô hạn. |
| PT tới B trả INVALID_SERVICE. | targetService A xin khác service B validate. | Fix exact public service URL/ingress config. |
| B chấp nhận proxy lạ. | `acceptAnyProxy=true`, regex quá rộng, chỉ check first proxy. | Exact ordered `allowedProxyChains` + provider decider tests. |
| B từ chối mọi PT hợp lệ. | Chỉ có `Cas20ServiceTicketValidator` hoặc default `RejectProxyTickets`. | Cấu hình proxy-aware validator và decider có policy, không accept-any. |
| Chuỗi khác thứ tự do test fixture. | Đọc `cas:proxies` theo chiều ngược. | CAS protocol: most recent first, sửa expected array. |
| B có vẻ vẫn accept replay PT. | Spring `StatelessTicketCache` đã cache Authentication. | Test cache hit/miss, TTL, route/scope/tenant checks. |
| PGT callback không chạy với alias. | `proxyCallbackUrl` sai DNS/port/TLS, redirect. | Dùng public HTTPS URL đúng receptor và cert. |
| Kiểm thử callback từ Internet được 200. | Receptor thiếu inbound trust; chỉ dựa HTTPS. | mTLS/service identity/ACL, peer auth, IOU correlation. |
| CAS /proxy trả UNAUTHORIZED_SERVICE_PROXY. | CAS service registry cấm A proxy. | Admin approve đúng service proxy authorization, không mở wildcard. |
| B nhận đúng chain nhưng user không có role. | Local user status/permission denied. | Giữ 403 authz; không thay allowlist. |
| API gọi CAS qua HTTP hoặc ignore TLS cert. | Client back-channel misconfig. | HTTPS verify CA/hostname; không trust-all. |
| Node A/B nhận chain khác do config rollout. | Allowed chains/version không đồng bộ. | Versioned policy, canary/fail-closed, rollout test. |
| CAS Server upgrade thay PGT flow. | CAS3/extension khác callback profile. | Pin version, integration compatibility test, không giả định callback luôn có. |

### 14.1. Phân biệt lỗi validation và lỗi authorization

- **INVALID_TICKET / INVALID_SERVICE**: CAS không chấp nhận ticket hoặc service binding. Đây là lỗi xác thực giao thức.
- **UNAUTHORIZED_SERVICE_PROXY**: service không có quyền proxy theo CAS registry/policy.
- **UNTRUSTED_CHAIN / REJECT_PROXY**: ứng dụng B không cho phép đường ủy quyền, dù CAS có thể đã xác minh PT.
- **LOCAL_ACCOUNT_DISABLED**: danh tính đã được xác minh nhưng bị chặn bởi chính sách ứng dụng.
- **FORBIDDEN_RESOURCE**: account có thể đã authenticated nhưng thiếu permission/tenant/resource ownership.
- **PGT_IOU_NOT_FOUND**: A không thể dùng PGT, không phải bằng chứng rằng người dùng sai mật khẩu.

HTTP status có thể khác nhau tùy filter/error handler và CAS client version; trong QA cần kiểm tra **reason và Authentication state**, không chỉ kiểm tra 401/403/500.

## 15. Observability và privacy

### 15.1. Log fields nên có

~~~text
event=CAS_PROXY_VALIDATION
trace_id=casproxy-test-384
cas_server_ref=corporate-cas
service_ref=reports-summary
origin_proxy_ref=portal
chain_policy_version=proxy-allow-v3
chain_length=2
chain_decision=ALLOW
pgt_callback_status=STORED
pgt_iou_correlation_status=MATCHED
ticket_validation=SUCCESS
local_account_status=ACTIVE
resource_authz=ALLOW
~~~

Đây là schema đề xuất, không phải log mặc định Spring Security/CAS. Dùng **reference/hash** thay vì raw ticket values; không đặt `pgtId`, `pgtIou`, `ticket=PT-*`, TGT, TGC cookie, usernames hoặc attributes trong metrics labels. PGT và PT là bearer credentials.

### 15.2. Metrics và alerts

- `cas_pgt_callback_received_total{outcome}` – bao gồm peer denied, store failed, duplicate/conflict.
- `cas_pgt_iou_match_failed_total{service}` – theo dõi callback/validation race.
- `cas_proxy_chain_denied_total{reason,service}` – đặc biệt unknown hop/order/empty.
- `cas_proxy_ticket_validation_failed_total{reason}` – invalid ticket/service, TLS failure.
- `cas_proxy_ticket_cache_hit_total{service}` – phát hiện ứng dụng nhận PT lặp lại theo cache.
- `cas_proxy_unauthorized_service_total{service}` – CAS registry cấm proxy.
- `cas_pgt_store_lag_ms{bucket}` – store visibility/latency (dùng histogram thực tế).
- `cas_proxy_session_revocation_lag_ms{bucket}` – nếu tích hợp logout/revocation.

**Security alert:** một proxy chain bất ngờ được accept sau config change là dấu hiệu nguy hiểm hơn việc callback 500 đơn lẻ. Metric cardinality phải giới hạn theo partner refs, không theo full attacker-provided URL.

## 16. Các anti-pattern cần tránh

1. **Bật `acceptAnyProxy=true` ở Reports B** khi nghiệp vụ chỉ cho một chain được duyệt.
2. **Chỉ kiểm tra proxy đầu tiên** hoặc dùng `chain.contains(trustedPortal)`.
3. **Sắp xếp hoặc đảo ngược proxy chain trước khi so** vì nghĩ order không quan trọng.
4. **Cho phép prefix** của một chain hợp lệ, bỏ qua những proxy phía sau.
5. **Cho phép regex quá rộng** ở `allowedProxyChains` mà không threat-model.
6. **Dùng callback URL giống hostname là đủ** nhưng bỏ scheme/path/port.
7. **Nhận PGT callback từ browser** do endpoint public và không có inbound trust.
8. **Dùng HTTPS server cert của Portal làm bằng chứng CAS Server đã gọi vào**: hướng xác thực sai.
9. **Ghép PGT theo username/session mới nhất**, gây cross-login mix-up.
10. **Trả 200 trước khi persist** PGTIOU→PGT, gây mất PGT và race.
11. **Lưu PGT trong browser/localStorage/cookie** hoặc log query string.
12. **Cho phép dùng raw PT mà không gọi CAS** hoặc không kiểm tra targetService.
13. **Coi CAS /proxyValidate success là đủ cấp quyền admin**; bỏ local authz.
14. **Bỏ CSRF/session protections vì “đã có CAS”** ở các browser endpoints khác.
15. **Dùng Cas20ServiceTicketValidator cho PT** rồi bypass lỗi bằng mã tự viết.
16. **Tắt certificate/hostname verification ở CAS back-channel** để sửa lỗi PGT.
17. **Không kiểm thử cache hit** ở Spring stateless proxy mode; PT replay có thể được cache xử lý khác với CAS.
18. **Chỉ test một node** và quên callback tới node khác.
19. **Không tách ST browser callback và PGT server-to-server callback**.
20. **Ghi nguyên `ticket=ST-*` và `pgtId` vào access logs** để debug.
21. **Dùng cùng một proxy chain policy cho mọi tenant** dù app khác mức nhạy cảm.
22. **Cho phép chained proxy vô hạn** mà không giới hạn hops/approved exact paths.
23. **Coi HTTP 200 của /proxyreceptor là đủ proof đã ghép PGT đúng**.
24. **Sử dụng fixture XML đã sửa tay như chứng cứ CAS Server thật phát chain đó**, mà không E2E với test CAS.
25. **Thay đổi proxy allowlist production mà không version/approval/rollback**.

## 17. Checklist nghiệm thu

1. ST ban đầu được validate ở CAS cho **đúng Portal A service URL**.
2. CAS service registry cho phép A xin PGT/PT, không mở mọi service proxy.
3. `pgtUrl` là HTTPS public URL chính xác và CAS verify certificate/hostname.
4. Receptor không phụ thuộc browser cookie/session và không login khi nhận `pgtId`.
5. Inbound receptor trust được enforce bằng mTLS/ACL/gateway identity phù hợp.
6. PGT IOU được lưu và liên kết chính xác với **verified ST/PT validation response**.
7. Duplicate/conflict IOU không ghi đè PGT, TTL/cleanup và encrypted store có hiệu lực.
8. Callback failure/timeout/redirect không bị báo thành PGT success.
9. Multi-node callback và ST validation đọc cùng storage/consistency.
10. A gọi `/proxy` dùng PGT bí mật server-to-server, `targetService` đúng Reports B.
11. B dùng `/proxyValidate` và đúng `Cas20ProxyTicketValidator`/proxy-aware validator.
12. B từ chối unknown/intermediate/extra/reversed/empty chain theo policy.
13. `acceptAnyProxy=false`, `allowedProxyChains` và `CasProxyDecider` được test đồng nhất.
14. Exact chain URLs có scheme, host, port, path và **most-recent-first**.
15. PT wrong service, expired, already validated hoặc fake đều bị deny.
16. Spring `StatelessTicketCache` được giới hạn và test theo TTL/scope/replay policy.
17. User local DISABLED, tenant mismatch hoặc thiếu permission bị deny sau CAS auth.
18. ST/PT/PGT/IOU bị redact ở gateway/APM/app logs, không leak qua responses.
19. Có integration test với CAS Server thật trên môi trường test và TLS trusted cert.
20. Có failure injection: CAS down, PGT store down, callback 302/500, DNS/cert failure.
21. Có test concurrent first logins của cùng user và user khác để tìm IOU mix-up.
22. Có audit và alert cho callback spoof attempts, untrusted chain, policy changes.
23. Không có đường tắt direct service/ingress bypass policies.
24. Mọi thay đổi trust chain có reviewer, policy version, canary và rollback an toàn.

## 18. Tự kiểm tra kiến thức

1. **CAS Proxy giải quyết gì?** – Cho service A gọi service B thay người dùng bằng PT từ CAS, không chia sẻ mật khẩu/TGT.
2. **ST khác PT thế nào?** – ST dành service ban đầu, PT được lấy qua PGT cho targetService downstream.
3. **PGT dùng để làm gì?** – Cho service proxy xin nhiều PT từ CAS.
4. **PGTIOU là gì?** – Khóa tương quan giữa callback PGT và trusted ticket validation response.
5. **PGT callback diễn ra từ đâu?** – CAS Server gọi HTTPS receptor của Portal A, không phải browser user.
6. **Tại sao receptor không thể tin caller chỉ vì HTTPS?** – HTTPS đến receptor chứng minh receptor với CAS/caller, không tự chứng minh CAS với receptor.
7. **Tại sao phải kiểm tra IOU?** – Để ghép đúng PGT với đúng login/ST validation, tránh cross-session mix-up.
8. **CAS /proxy nhận gì?** – PGT và targetService; trả PT tương ứng.
9. **B validate PT bằng gì?** – CAS /proxyValidate với PT và exact service URL.
10. **`cas:proxies` có thứ tự thế nào?** – Proxy gần nhất/mới nhất đứng đầu, không phải theo thứ tự đi từ nguồn.
11. **Tại sao `acceptAnyProxy=true` nguy hiểm?** – Có thể nhận PT từ chain không được phép.
12. **Tại sao không chỉ xét first proxy?** – Các hop trước có thể không được tin, dù hop gần B hợp lệ.
13. **Có được sắp xếp proxy chain trước khi so không?** – Không; thứ tự là một phần lịch sử ủy quyền.
14. **`allowEmptyProxyChain` dùng để làm gì?** – Quyết định chấp nhận chuỗi trống; proxy-only route nên deny.
15. **Sai `targetService` sẽ thế nào?** – CAS từ chối ticket theo service binding.
16. **Một PT có thể validate hai lần tại CAS không?** – Không theo CAS one-time semantics; Spring cache cần kiểm thử riêng.
17. **Vì sao hai pods cần shared PGTIOU store?** – Callback và validation có thể được xử lý ở hai nodes khác nhau.
18. **Callback 200 có tự chứng minh PGT hợp lệ cho login không?** – Không; còn CAS validation response và IOU correlation.
19. **User được CAS xác thực có tự được reports:read không?** – Không; B còn local account status/authorization.
20. **Kiểm thử nào chứng minh chống chain spoofing?** – E2E/negative tests với unknown, reversed, extra, missing, empty proxy chain và đúng CAS validation.

## Tài liệu tham khảo

- [Apereo CAS — CAS Protocol Specification, §2.5.4 proxy callback, §2.6 proxyValidate, §2.7 proxy](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html)
- [Spring Security — CAS Authentication and Proxy Ticket Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html)
- [Apereo Java CAS Client — README: Proxy Receiving Validation Filter, allowedProxyChains, acceptAnyProxy](https://github.com/apereo/java-cas-client/blob/master/README.md)
- [Cas20ProxyTicketValidator JavaDoc: allowedProxyChains, allowEmptyProxyChain](https://javadoc.io/static/org.jasig.cas.client/cas-client-core/3.6.4/org/jasig/cas/client/validation/Cas20ProxyTicketValidator.html)
- [Apereo CAS — Proxy Authentication Configuration](https://apereo.github.io/cas/development/authentication/Configuring-Proxy-Authentication.html)
- [Spring Security CAS — StatelessTicketCache and CasProxyDecider](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html#_proxy_ticket_authentication)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html)
