# mTLS giữa các workload: xác thực kết nối và xây dựng ranh giới tin cậy trong service mesh

Giả sử một nền tảng thương mại điện tử có dịch vụ **checkout** gọi **inventory**, **payment** và **identity** trong cùng Kubernetes cluster. Tất cả đều ở mạng private, nhưng một Pod đã bị xâm nhập hoặc một workload cấu hình sai vẫn có thể thử kết nối tới địa chỉ của các service khác. Mạng private và việc gọi đúng Service DNS không tự chứng minh **bên đang gọi là ai**, **bên được gọi có đúng danh tính dự kiến không**, cũng không đảm bảo **dữ liệu trên đường đi được bảo vệ**.

**Mutual Transport Layer Security (mTLS)** sử dụng TLS để **cả hai phía xác thực lẫn nhau**, thường thông qua chứng thư X.509 và bằng chứng sở hữu khóa riêng, đồng thời bảo vệ tính bí mật và toàn vẹn của dữ liệu trên đoạn kết nối được mã hóa. Trong **service mesh**, những chức năng như cấp chứng thư ngắn hạn, phân phối trust bundle, thiết lập kết nối mTLS và quan sát lưu lượng có thể được điều phối tự động bởi **control plane** và thực thi bởi **data plane** (sidecar, proxy chia sẻ hoặc mô hình khác). Tuy nhiên, **mTLS không tự thay thế authorization theo service, phương thức hay tài nguyên nghiệp vụ**.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, bài học thuộc chương **Service mesh và mTLS**; chủ đề kết nối với phân đoạn mạng, firewall, VPN, PKI, TLS, DNS, Kubernetes, IDS/IPS, giám sát và thiết kế mạng Zero Trust. Mục tiêu là hiểu **workload identity, trust boundary, vòng đời chứng thư, chế độ bắt buộc mTLS, kiểm soát đường bypass và quy trình xác minh ALLOW/DENY** trên những đường mạng cụ thể.

> **Nguyên tắc cốt lõi:** Có TLS không nhất thiết có mTLS; có mTLS không đồng nghĩa caller được phép thực hiện mọi RPC; thấy biểu tượng “mesh enabled” không chứng minh mọi đường đi đều đã được bảo vệ. Hãy kiểm tra **đúng hai danh tính, đúng điểm kết thúc TLS, đúng policy, đúng route và đúng kết quả nghiệp vụ**.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **plaintext TCP/HTTP, server-authenticated TLS và mTLS**.
2. Giải thích **handshake, certificate chain, SAN, trust anchor, khóa riêng, CertificateVerify, TLS session** và vai trò xác thực hai chiều.
3. Mô tả **workload identity, SPIFFE ID, X.509-SVID, trust domain, trust bundle và service account** mà không nhầm chúng với IP/hostname.
4. Hiểu cách **control plane cấp/luân chuyển identity**, data plane thiết lập mTLS trong **sidecar** hoặc mô hình không dùng sidecar.
5. Phân biệt **peer authentication** với **authorization**, đặc biệt khi triển khai chế độ **STRICT/PERMISSIVE** trong hệ thống hỗ trợ.
6. Thiết kế **least-privilege service-to-service access** kết hợp NetworkPolicy, service identity, L4/L7 policy và application authorization.
7. Nhận ra những đường **plaintext bypass, policy gaps, port exclusions, hostNetwork, ingress/egress gateway, external dependencies** và rủi ro multi-cluster.
8. Thiết kế quy trình **bootstrap identity, certificate rotation, CA rollover, điều tra expired/untrusted certificates** và xử lý khi control plane gián đoạn.
9. Xác định dữ liệu quan sát cần có: **TLS/mesh telemetry, principal, workload, route, authorization decision, HTTP/gRPC status** mà không lộ secret.
10. Áp dụng **lab an toàn, runbook và ma trận positive/negative tests** trước khi tuyên bố kết nối workload đã được bảo vệ.

## 2. TLS một chiều và mTLS khác nhau như thế nào?

Với **TLS thông thường**, client thường xác thực danh tính của server qua chứng thư. Server chưa nhất thiết xác thực danh tính client bằng chứng thư TLS; ứng dụng có thể dùng token, session, OAuth hoặc cách khác để xác thực người gọi ở lớp cao hơn.

**mTLS** bổ sung bước server yêu cầu và xác thực chứng thư của client (hoặc cơ chế tương ứng trong TLS), sao cho **cả hai phía** đều có bằng chứng xác thực ở tầng vận chuyển. Cả TLS và mTLS đều cần cấu hình đúng CA/trust policy, verification, cipher/protocol và private-key protection.

| Mô hình | Server được client xác thực? | Client được server xác thực bằng TLS certificate? | Dữ liệu trên hop được mã hóa? |
|---|---|---|---|
| **Plaintext TCP/HTTP** | Không bằng TLS | Không | Không bằng TLS |
| **Server-authenticated TLS** | Có, nếu kiểm tra danh tính/trust đúng | Thường không | Có trên TLS hop |
| **mTLS** | Có | Có | Có trên TLS hop |
| **mTLS + application authorization** | Có | Có | Có, và thêm quyết định quyền nghiệp vụ |

**Mã hóa không đồng nghĩa xác thực đầy đủ.** Một kết nối TLS với chế độ bỏ kiểm tra chứng thư hoặc chấp nhận CA quá rộng có thể bị sai đích. Tương tự, mTLS với một CA tin cậy nhưng **không ràng buộc SAN/identity mong đợi** có thể xác thực “một workload nào đó” mà không xác thực đúng service đích.

### mTLS bảo vệ những điều gì?

- **Bí mật trên đường truyền (confidentiality)** của TLS application data giữa các điểm kết thúc được xác định.
- **Toàn vẹn (integrity)**: phát hiện sửa đổi dữ liệu được TLS bảo vệ trên hop.
- **Xác thực peer** dựa vào chứng thư/khóa và trust policy đúng.
- **Nền tảng cho policy dựa trên workload identity** và audit attribution.

### mTLS không tự bảo vệ những điều gì?

- **Phân quyền tới object/tenant** hoặc hành động nghiệp vụ.
- **Đoạn sau TLS termination** nếu proxy gửi plaintext tiếp.
- **Endpoint bị chiếm quyền**, nơi dữ liệu sau giải mã và private key có thể bị lạm dụng.
- **Giao thức không đi qua data plane mTLS** hoặc các cổng bị loại khỏi proxy.
- **DDoS/resource exhaustion** từ workload đã có danh tính hợp lệ.
- **Sự đúng đắn của policy routing/identity mapping** khi cấu hình sai.

## 3. Phân biệt IP/network identity và workload identity

Trong môi trường cloud/Kubernetes, một workload có thể liên tục đổi **Pod IP, node, vùng triển khai** hoặc replica. Một NetworkPolicy cho phép nguồn theo Pod/namespace labels, còn mTLS xác minh **danh tính mật mã** gắn với workload theo chính sách.

~~~text
Workload checkout
  namespace: shop
  serviceAccount: checkout-sa
  Pod IP hôm nay: 10.244.1.20
  Pod IP sau rollout: 10.244.3.18
  Mesh workload identity (minh họa):
    spiffe://cluster.local/ns/shop/sa/checkout-sa

Workload inventory
  namespace: catalog
  serviceAccount: inventory-sa
  Mesh workload identity:
    spiffe://cluster.local/ns/catalog/sa/inventory-sa
~~~

Đây là **ví dụ mô hình danh tính**, không bảo đảm mọi mesh/cluster đều cấp identity có định dạng và trust domain giống vậy. Giá trị **cluster.local** trong chuỗi SPIFFE minh họa là tên trust domain; không được nhầm với tên DNS Service **.svc.cluster.local** dù chúng có thể trùng phần chữ.

### Mỗi thuộc tính trả lời một câu hỏi khác nhau

| Thuộc tính | Ý nghĩa | Hạn chế |
|---|---|---|
| **Pod IP** | Nơi có thể định tuyến gói tới trong một thời điểm | Biến động, có thể NAT/proxy |
| **Namespace label** | Nhóm Pod/resource theo Kubernetes API | Có thể bị thay nếu RBAC quá rộng |
| **ServiceAccount** | Principal Kubernetes gắn cho Pod | Cần bảo vệ quyền gán, token và bootstrap identity |
| **SPIFFE ID / workload identity** | Tên danh tính dùng cho xác thực giữa workload theo trust domain | Cần issuance, validation và policy chính xác |
| **TLS certificate SAN** | Tên/danh tính được chứng thư xác nhận | Phải match identity mong đợi, không chỉ chain valid |
| **Application user ID** | Người dùng cuối trong request | Không tự bằng workload identity của gateway |

**Có network path tới một IP không đồng nghĩa caller có service identity được phép; một service identity được xác thực cũng không thay user authentication trong ứng dụng.**

## 4. Mô hình hóa mối đe dọa east–west traffic

**East–west traffic** là các luồng giữa service/workload bên trong trung tâm dữ liệu hoặc cloud, như API→DB, gateway→backend, service→broker. Tên gọi “internal” không có nghĩa các peer đều đáng tin.

~~~text
                 Internet / User
                        |
                    Edge Gateway
                        |
              Shop namespace
                 Checkout
                   /   \
           inventory   payment
            (catalog)  (finance)
                |           |
           Catalog DB   Ledger DB

          Untrusted workload / compromised Pod
                      |
                 tries lateral access
~~~

| Mối đe dọa | Nếu chỉ dùng IP/“mạng private” | mTLS hỗ trợ thế nào? | Vẫn cần gì? |
|---|---|---|---|
| **Giả mạo dịch vụ** | DNS/route/proxy sai hoặc đích giả | Server identity validation | Discovery policy, SAN match, DNS safeguards |
| **Giả mạo caller** | Workload khác ở cùng subnet gọi API | Client identity validation | AuthorizationPolicy, application auth |
| **Nghe lén trên hop** | Traffic cleartext trong overlay/VPC | TLS encryption | Bảo vệ proxy endpoints, logs và keys |
| **Lateral movement** | Pod bị chiếm quyền gọi các Pod khác | Policy theo danh tính mTLS | NetworkPolicy, least privilege, segmentation |
| **Workload compromised** | Service hợp lệ bị điều khiển | Identity vẫn nhận diện service đó | Runtime isolation, EDR, behavior/rate limits |
| **Cross-tenant data access** | Một RPC hợp lệ yêu cầu object tenant khác | Không tự chặn | Object-level authorization |
| **Availability attack** | Nhiều kết nối/stream gây quá tải | Không tự giải quyết | Rate/concurrency limit, circuit breaker, DDoS defense |
| **Rogue certificate issuance** | Danh tính sai được cấp chứng thư | mTLS có thể bị đánh lừa bởi CA bị xâm phạm | CA security, attestation, trust governance |

**Kết luận threat model:** mTLS là một **kiểm soát xác thực/mã hóa hop**, không phải bằng chứng một workload không thể gây hại khi chính nó đã bị chiếm quyền.

## 5. TLS handshake và xác thực hai chiều ở mức khái niệm

Quy trình cụ thể khác nhau theo **TLS 1.2/TLS 1.3**, session resumption và thư viện. Ở trường hợp TLS 1.3 full handshake có xác thực client bằng certificate:

~~~text
Client workload                        Server workload
       |                                       |
       | ---- ClientHello / supported TLS ---> |
       | <--- ServerHello / handshake keys --- |
       | <--- server CertificateRequest* ----- |
       | <--- server Certificate + proof ----- |
       | <--- server Finished ---------------- |
       |                                       |
       |   Verify server certificate and ID   |
       |                                       |
       | ---- client Certificate* -----------> |
       | ---- client CertificateVerify* -----> |
       | ---- client Finished ---------------> |
       |                                       |
       | ===== authenticated TLS data ======= |

* Tóm tắt về client certificate authentication;
  thứ tự/định dạng đầy đủ phải theo phiên bản TLS đang dùng.
~~~

**Trong TLS 1.3, nhiều handshake messages sau ServerHello được bảo vệ bằng khóa handshake; sơ đồ trên không mô tả mọi byte/frame.** Thông điệp **CertificateVerify** chứng minh phía tương ứng sở hữu khóa riêng phù hợp với certificate; chỉ thấy một tập certificate trong log không đủ chứng minh xác thực đã hoàn thành.

### Hai phía thực sự kiểm tra những gì?

1. **Certificate chain** tới trust anchor được phép, với các điều kiện path validation.
2. **Validity interval** (notBefore/notAfter) và đồng hồ đủ chính xác.
3. **Certificate signature, key usage, Extended Key Usage**, thuật toán và các ràng buộc liên quan.
4. **SAN/identity** được phép cho server hoặc client theo cơ chế mesh/SPIFFE.
5. **Possession of private key** được chứng minh trong handshake khi dùng certificate auth.
6. **Trust domain, issuer và policy** phù hợp, không chỉ “được ký bởi bất kỳ CA có trong máy”.
7. **Trạng thái kết nối và handshake result** ở TLS endpoint đã kiểm chứng.

### Trust là quan hệ có điều kiện

Một certificate được ký bởi CA hợp lệ chỉ cho biết **CA đó xác nhận một tập thuộc tính danh tính**; nó **không tự tạo quyền gọi method DeletePayment**. Hệ thống tiếp tục phải xác định **principal này được gọi service/method nào và trên dữ liệu nào**.

## 6. X.509, SAN và chứng thư workload

Service mesh có thể cấp chứng thư X.509 ngắn hạn cho workload. Các trường quan trọng bao gồm:

| Thuộc tính | Ý nghĩa an ninh |
|---|---|
| **Subject / Issuer** | Chủ thể và tổ chức/chứng thư phát hành; với SPIFFE chủ yếu phải đọc SAN |
| **Serial number** | Định danh chứng thư từ CA; dùng trong inventory/revocation |
| **Not Before / Not After** | Khoảng hiệu lực; liên quan rotation và clock |
| **Subject Alternative Name (SAN)** | Chứa danh tính, ví dụ **URI SAN** cho SPIFFE ID |
| **Key Usage / EKU** | Mục đích khóa: xác thực TLS server/client theo policy |
| **Public key / signature algorithm** | Cơ sở xác minh certificate và handshake |
| **Certificate chain** | Chuỗi tin cậy qua intermediate đến root/trust anchor |

Trong mô hình SPIFFE X.509-SVID, **SPIFFE ID được biểu diễn qua URI SAN**, không phải chỉ trong Common Name. Một implementation có thể dùng URI SAN phù hợp thay cho DNS hostname; **kiểm tra hostname bằng tiêu chí DNS SAN không tương đương kiểm tra SPIFFE ID**.

### Chứng thư không phải private key

- **Certificate/public key** có thể được phân phối để phía khác xác minh.
- **Private key** phải giữ bí mật, giới hạn quyền đọc và vòng đời.
- **Trust bundle** chứa trust anchors/CA certificates để xác minh peer, không được coi như private key.
- **SVID** là chứng thực danh tính workload; **X.509-SVID** gồm certificate chain và private key tương ứng, còn trust bundle dùng để xác minh các SVID được phân phối/quản lý riêng theo cơ chế identity.

**Không ghi private key, token bootstrap hoặc SVID material vào log, tracing hay artefact công khai.** Nếu workload bị chiếm quyền và có quyền dùng private key hiện hành, mTLS vẫn có thể xác thực workload đó theo danh tính đã được cấp; cần bổ sung host/runtime security và quy trình incident response.

## 7. SPIFFE ID, SVID và trust domain

**SPIFFE** đưa ra mô hình định danh workload thống nhất. Một SPIFFE ID thường có dạng URI:

~~~text
spiffe://<trust-domain>/<workload-identity-path>

Ví dụ:
spiffe://cluster.local/ns/shop/sa/checkout-sa
spiffe://cluster.local/ns/catalog/sa/inventory-sa
~~~

Trong ví dụ, **trust domain = cluster.local**. Phần đường dẫn là quy ước ánh xạ danh tính workload của một hệ thống cụ thể; SPIFFE không bắt buộc mọi tổ chức phải dùng **/ns/.../sa/...**. Một hệ thống dùng SPIRE hoặc mesh khác có thể xây workload selectors/path theo quy ước được phê duyệt.

### SPIFFE và SVID

| Thuật ngữ | Ý nghĩa |
|---|---|
| **SPIFFE ID** | Định danh workload dạng URI theo trust domain |
| **SVID** | Tài liệu/credential chứng minh danh tính SPIFFE |
| **X.509-SVID** | Certificate chain chứa SPIFFE ID trong URI SAN và private key tương ứng; trust bundle là dữ liệu tin cậy đi kèm qua cơ chế phân phối riêng |
| **JWT-SVID** | Chứng thực SPIFFE dạng JWT, có ngữ nghĩa xác minh khác TLS certificate |
| **Trust domain** | Phạm vi quản trị danh tính và trust anchors được xác định |
| **Trust bundle** | Tập chứng thư CA/trust anchor để xác minh SVID tương ứng |
| **Workload attestation** | Cơ chế xác định workload nào được cấp một danh tính |

**Không đồng nhất JWT-SVID với mTLS.** JWT-SVID thường được dùng như token xác thực theo audience/verification phù hợp; mTLS sử dụng cơ chế TLS certificate auth. Có thể dùng hai cơ chế phối hợp trong kiến trúc, nhưng không thay thế nguyên tắc xác minh từng loại.

### Trust domain không nhất thiết trùng Kubernetes cluster

Một mesh có thể có một trust domain cho nhiều cluster, hoặc nhiều trust domain cho nhiều vùng/đối tác. Quyết định này có tác động lớn tới **policy namespace/ServiceAccount**, trust sharing và blast radius nếu CA hoặc bootstrap identity bị xâm phạm.

## 8. Identity bootstrap: workload được cấp chứng thư bằng cách nào?

**Bootstrap** là khâu khó của mọi hệ thống danh tính: một workload mới chưa có chứng thư mTLS được tin cậy, vậy CA/identity service dựa vào đâu để cấp đúng identity?

~~~text
      Kubernetes Pod starts
               |
       Workload/node attestation
       ServiceAccount / runtime evidence
               |
               v
        Mesh identity agent
          or sidecar proxy
               |
       CSR / identity issuance
               |
               v
         Mesh CA / issuer
               |
        X.509 certificate
        + chain/trust bundle
               |
               v
        Data plane mTLS
~~~

### Yêu cầu thiết kế

1. **Xác thực nguồn bootstrap**: token/attestation phải được kiểm tra issuer, audience, expiry và identity phù hợp.
2. **Không để Pod tự chọn service identity bất kỳ** bằng cách tự gửi tên trong CSR mà CA không ràng buộc với bằng chứng workload.
3. **Giới hạn quyền gán ServiceAccount**: không phải mọi tenant được tạo Pod với ServiceAccount đặc quyền.
4. **Giới hạn quyền CA/issuer**: workload không được cấp certificate thay service khác.
5. **Bảo vệ kênh phân phối** chứng thư/khóa qua agent, SDS hoặc cơ chế tương ứng.
6. **Ràng buộc trust domain và namespace** với chính sách cấp phát, tránh giả mạo cross-cluster.
7. **Audit issuance** và theo dõi các identity mới, certificate lifetime/rotation errors.

**Cấp chứng thư tự động không bảo đảm danh tính đúng** nếu khâu bootstrap hoặc quyền tạo workload bị cấu hình quá rộng.

## 9. Control plane và data plane của service mesh

Service mesh thường phân tách:

- **Control plane**: điều phối cấu hình routing, policy, trust, workload discovery và phân phối chứng thư/secret theo sản phẩm.
- **Data plane**: các proxy/agent thực sự nhận kết nối, xác thực/mã hóa, định tuyến và thu telemetry.

~~~text
                  Mesh Control Plane
           Configuration + identity + CA
                /               \
               v                 v
         Data plane A        Data plane B
         [Checkout] ======= [Inventory]
             |        mTLS       |
             |                   |
         Application         Application
             |                   |
         Network/CNI/Cloud routing
~~~

Không phải mesh nào cũng **vận chuyển mọi gói dữ liệu qua control plane**. Thông thường control plane cung cấp điều phối và chứng thư, còn **data plane thực hiện các kết nối trực tiếp qua mạng**. Nếu control plane mất tạm thời, những kết nối và cấu hình đã được phân phối **có thể** tiếp tục hoạt động tùy TTL, proxy state và kiến trúc, nhưng **rotation/reconfiguration/scale-out** có thể bị ảnh hưởng.

### Câu hỏi phải xác minh

| Lớp | Điều cần kiểm tra |
|---|---|
| **CA / issuer** | Ai được phép cấp identity? Root/intermediate/trust domain ở đâu? |
| **Config distribution** | Proxy nào nhận policy, thời điểm và phiên bản nào? |
| **Certificate distribution** | Cơ chế SDS/agent/mount có bảo vệ khóa riêng không? |
| **Data plane** | Kết nối nào thật sự dùng mTLS, phiên bản TLS nào? |
| **Sidecar injection/enrollment** | Pod nào được đưa vào mesh, Pod nào bị loại trừ? |
| **Telemetry** | Có thấy cả successful và denied peer identities không? |
| **Failure handling** | Khi CA/control plane lỗi, proxy có fail-open plaintext không? |

## 10. Sidecar, shared proxy và ambient data plane

Trong **sidecar architecture**, một proxy (ví dụ Envoy trong một số mesh) chạy cùng Pod hoặc gần workload, điều khiển traffic theo cơ chế redirect/proxy configuration. Ứng dụng có thể vẫn giao tiếp plaintext với **local proxy trong cùng network namespace**, còn proxy thiết lập **mTLS trên hop tới proxy của peer**.

~~~text
Pod A                            Pod B
+-------------------+            +-------------------+
| Application       |            | Application       |
|   | local hop     |            |    ^ local hop    |
|   v               |            |    |              |
| Sidecar proxy A   |============| Sidecar proxy B   |
+-------------------+   mTLS     +-------------------+
                encrypted/authenticated mesh hop
~~~

**Điểm kết thúc mTLS nằm ở proxy**, không nhất thiết ở chính process ứng dụng. Với threat model cần mã hóa end-to-end tới ứng dụng, phải phân tích tiếp **local plaintext hop**, host trust và có thể cân nhắc TLS/mTLS ở ứng dụng.

### Không phải mọi mesh đều dùng sidecar cho từng Pod

Một số kiến trúc có **shared per-node proxy hoặc ambient data plane**:

~~~text
Pod A app
   |
Node-level secure tunnel proxy
   |========= mTLS ========|
                     Node-level proxy
                            |
                         Pod B app
~~~

Trong những mô hình này, **tính năng L4 mTLS và khả năng L7 routing/authorization** có thể do những thành phần khác nhau cung cấp. Ví dụ, mô hình ambient của Istio phân biệt thành phần tunnel L4 với **waypoint proxy** phục vụ một số nhu cầu L7. Không suy rằng mọi policy về HTTP method được thi hành ở cùng điểm với L4 identity khi chưa xác minh data path.

### So sánh mô hình

| Mô hình | Ưu điểm thường gặp | Rủi ro hoặc điều kiện cần xét |
|---|---|---|
| **Sidecar per Pod** | Policy/telemetry gần workload, hỗ trợ L7 khi cấu hình | Sidecar injection/port exclusions, resource overhead, app→proxy local hop |
| **Shared/ambient L4 proxy** | Có thể giảm sidecar footprint và bật mTLS cấp node/workload | Host/data-plane boundary, waypoint cho L7, coverage của namespace/node |
| **Application-native mTLS** | Endpoint TLS nằm trong ứng dụng, kiểm soát identity trực tiếp | Quản lý cert/rotation trong app, SDK và vận hành phức tạp |
| **Gateway-mediated TLS** | Kiểm soát tập trung trên ingress/egress | Các hop phía sau gateway có thể không cùng policy |

**Không có một mô hình mặc nhiên an toàn hơn trong mọi hệ thống.** Cần hiểu điểm kết thúc mTLS, quyền của proxy và nơi application authorization được áp dụng.

## 11. Service mesh khác firewall, VPN và NetworkPolicy

| Công cụ | Giải quyết tốt | Không tự giải quyết |
|---|---|---|
| **Firewall / SG / NACL** | Kiểm soát địa chỉ, port, direction, zone | Workload identity hay quyền nghiệp vụ chi tiết |
| **Kubernetes NetworkPolicy** | L3/L4 access dựa Pod/namespace/CIDR theo CNI | Certificate identity và HTTP method |
| **VPN/IPsec** | Bảo vệ tunnel/đường giữa mạng/điểm kết nối | Xác thực từng workload trong tunnel nếu không có lớp khác |
| **Server-authenticated TLS** | Client xác minh server và mã hóa trên hop | Peer client certificate identity |
| **Service mesh mTLS** | Peer workload identity, mã hóa và telemetry trên mesh path | Quyền user/object nếu không có policy khác |
| **AuthorizationPolicy/API gateway** | Cho phép caller/service/method theo identity và điều kiện | Không tự đảm bảo mọi đường traffic đi qua enforcement point |
| **Application authorization** | Quyền tới object/tenant/transaction | Không thay L3/L4 segmentation và bảo vệ tunnel |

**Defense-in-depth:** một request hợp lệ thường phải đồng thời **có route**, **được firewall/NetworkPolicy cho phép**, **được mTLS xác thực peer**, **được service policy cho phép** và **được ứng dụng phân quyền dữ liệu**.

## 12. Peer authentication: bắt buộc mTLS hay chấp nhận plaintext?

Các mesh có thể có chế độ điều khiển **cách server chấp nhận kết nối**. Trong Istio, những chế độ thường gặp của **PeerAuthentication** gồm:

- **STRICT:** chỉ chấp nhận traffic với mTLS phù hợp theo policy áp dụng.
- **PERMISSIVE:** hỗ trợ chuyển đổi khi có cả caller mTLS và caller plaintext trên đường được phép; cần kiểm tra enforcement và nguy cơ downgrade.
- **DISABLE:** vô hiệu mTLS ở phạm vi được chọn theo cách triển khai.
- **UNSET:** không thiết lập mode trực tiếp ở cấp đó; hiệu lực phụ thuộc chính sách kế thừa và cấu hình/phiên bản.

Đây là **thuật ngữ của Istio**, không phải danh sách chuẩn mTLS chung cho mọi sản phẩm. Một số dataplane modes có hạn chế đối với DISABLE hoặc các loại policy; cần xác minh **API version, mode, scope và hiệu lực thực tế** trên cluster.

### STRICT không có nghĩa chỉ một caller được phép

Giả sử catalog server đặt **STRICT mTLS**. Một workload khác có certificate hợp lệ thuộc trust domain mesh vẫn có thể **hoàn tất mTLS handshake**, dù nó không được phép gọi catalog theo logic nghiệp vụ, nếu không có authorization policy phù hợp.

~~~text
Pod X in trust domain
        |
        | valid mTLS identity
        v
Catalog proxy: peer authenticated
        |
        | AuthorizationPolicy?
        |
     Allowed or Denied
        |
     Catalog application
~~~

**Peer authentication trả lời “ai đang nói chuyện và qua kênh nào?”; authorization trả lời “peer đó được làm gì?”**. Chỉ bật STRICT không phải cách triển khai least privilege giữa các workload.

## 13. Ví dụ Istio PeerAuthentication STRICT tại namespace

Trong một mesh **Istio được cấu hình theo cơ chế hỗ trợ CRD này**, ví dụ minh họa:

~~~yaml
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: require-mtls
  namespace: catalog
spec:
  mtls:
    mode: STRICT
~~~

Trong mô hình Istio sidecar phù hợp, policy này có ý định **yêu cầu mTLS cho inbound traffic tới các workload thuộc phạm vi áp dụng** ở namespace catalog. Đây là **ví dụ học tập, không phải file triển khai cho mọi version/mode**.

### Điều phải kiểm tra trước khi áp dụng

1. Cluster đã cài **Istio CRDs/control plane**, đúng API version và namespace chưa?
2. Các workload đích thực sự **tham gia mesh** và data plane đang thực thi policy chưa?
3. Có **PeerAuthentication cấp mesh/workload hoặc port-level** với độ ưu tiên/ghi đè liên quan không?
4. Những client hợp lệ đã có **mTLS-compatible data plane** chưa?
5. Có luồng từ **Ingress Gateway, legacy VM, health checker hoặc external service** cần đường chuyển đổi rõ ràng không?
6. Có **port exclusions/hostNetwork/direct service routes** khiến một đường không qua enforcement point không?
7. Sẽ kiểm chứng **plaintext DENY** và **mTLS caller được phép ALLOW** bằng phép thử nào?

**Không chuyển cả namespace từ PERMISSIVE sang STRICT trong production mà chưa xác minh mọi caller.** Những hệ thống legacy dùng HTTP cleartext tới Pod có thể mất kết nối; cần kế hoạch onboarding, canary, metrics và rollback.

### Namespace-wide khác workload-specific

Một policy namespace có thể tác động nhiều service trong cùng namespace. Khi một service đặc thù cần mode khác, phải có quyết định rủi ro và kế hoạch chuyển đổi riêng; **không bật ngoại lệ plaintext trên toàn namespace chỉ vì một dependency chưa được nâng cấp**.

## 14. Authorization theo workload principal

Sau khi xác thực peer bằng mTLS, proxy hoặc application có thể ràng buộc principal với policy. Trong Istio, **AuthorizationPolicy** có thể mô tả caller identities, method/path/port và các điều kiện khác tùy mode, protocol và enforcement point.

### Ví dụ chỉ cho checkout gọi inventory TCP/8080

~~~yaml
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: allow-checkout-to-inventory
  namespace: catalog
spec:
  selector:
    matchLabels:
      app: inventory
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - "cluster.local/ns/shop/sa/checkout-sa"
      to:
        - operation:
            ports:
              - "8080"
~~~

**Phạm vi ví dụ:** cú pháp minh họa một workload **Istio sidecar** trong **catalog** với nhãn **app=inventory**, sử dụng trust domain **cluster.local**. Một số kiểu Istio principal thể hiện identity không có tiền tố **spiffe://** trong field authorization; không được tự chèn/loại bỏ tiền tố khi chưa kiểm tra tài liệu API.

### Tại sao policy này chưa đủ?

- Nó cho phép principal trên **port 8080**, chưa giới hạn một RPC **GetInventory** cụ thể.
- Nếu application nhận request từ gateway đại diện người dùng, principal **checkout-sa** vẫn không cho biết **end-user ID**.
- Policy có thể không được thực thi với traffic không đi qua proxy/waypoint thích hợp.
- Nếu có **các policy khác** hoặc policy cấp mesh cùng áp dụng, hiệu lực thực tế cần tính theo semantics của Istio.
- Với **ambient mesh**, vị trí gắn L4/L7 authorization policy và cấu hình **targetRefs/waypoint** có thể khác kiểu sidecar selector ở trên.

**Không copy nguyên manifest vào production nếu chưa xác định mode của dataplane.** Trong một số mô hình chỉ có L4 proxy, không có đủ thông tin HTTP để áp chính sách method/path; cần waypoint/gateway hoặc application-layer controls.

### Lựa chọn cho dịch vụ gRPC

Với gRPC, một method thông dụng có đường dẫn HTTP/2 dạng:

~~~text
/inventory.v1.InventoryService/GetItem
~~~

L7 authorization có thể dùng identity + gRPC method/path nếu proxy thực sự hiểu HTTP/2 và gRPC trên đoạn đó. Nhưng ứng dụng vẫn phải kiểm tra **quyền đối với item_id hoặc tenant**. Không suy role admin từ việc một service caller có chứng thư hợp lệ.

## 15. Mô hình ma trận IAM/workload authorization

Thiết kế chính sách nên bắt đầu từ **luồng nghiệp vụ cần thiết**:

| Caller | Target | Network | mTLS | Service authorization | Business authorization |
|---|---|---|---|---|---|
| **shop/checkout-sa** | **catalog/inventory-sa** | TCP/8080 | Bắt buộc | ALLOW GetItem/Reserve | Chỉ item/tenant theo caller context |
| **shop/checkout-sa** | **finance/payment-sa** | TCP/8443 | Bắt buộc | ALLOW CreatePayment theo policy | Idempotency, user/transaction rights |
| **catalog/inventory-sa** | **data/catalog-db** | TCP/5432 | Theo ứng dụng/mesh/proxy | Chỉ workload inventory | DB roles và quyền schema |
| **sandbox/test-sa** | **finance/payment-sa** | TCP/8443 | Nếu có kết nối thì vẫn xác thực | **DENY** | Không đến business logic |
| **monitoring/collector-sa** | **catalog/inventory metrics** | TCP/9090 | Theo thiết kế | ALLOW metrics only | Che dữ liệu nhạy cảm |
| **unknown client** | **catalog/inventory-sa** | TCP/8080 | Không có trusted identity | **DENY** | Không đến business logic |

### Phân biệt ALLOW ở các lớp

Một flow được **NetworkPolicy cho qua** nhưng **mTLS handshake bị từ chối** là kết quả bảo mật có ý nghĩa khi caller không có certificate. Một flow **mTLS thành công** nhưng **AuthorizationPolicy DENY** cũng có thể là kết quả đúng khi principal không có quyền. Một flow đạt cả hai mà **application trả PERMISSION_DENIED** vẫn có thể đúng do object-level authorization.

**Không dùng một trường “success=true” duy nhất trong dashboard để tổng hợp tất cả các tầng.** Cần ghi **đang thất bại ở lớp nào** và identity nào đã được kiểm tra.

## 16. Danh tính ServiceAccount và quyền tạo workload

Trong Kubernetes, ServiceAccount là một phần quan trọng của workload identity trong nhiều hệ thống mesh. Nhưng quyền **tạo Pod sử dụng ServiceAccount nào** và quyền **sửa labels/namespace** có ảnh hưởng trực tiếp tới an toàn của PKI bootstrap.

### Rủi ro phổ biến

1. Mọi Deployment đều dùng **default ServiceAccount**, gây chia sẻ identity quá rộng.
2. Team dev có quyền triển khai Pod sử dụng **ServiceAccount đặc quyền của service production** trong cùng namespace.
3. Có quyền sửa label để khiến workload được chọn vào một nhóm traffic/policy không mong muốn.
4. Mesh issuer **không ràng buộc CSR với identity thực** từ workload attestation.
5. Sidecar injection bị bỏ qua ở Pod mới nhưng các route cũ vẫn cho phép plaintext.
6. Một số workloads có **hostNetwork/privileged** tạo đường điều khiển khó bao phủ bằng NetworkPolicy thường.

### Các biện pháp

- Mỗi service nhạy cảm có **ServiceAccount riêng**; không dùng chung identity không có lý do.
- RBAC/admission giới hạn ai được **create/update Pod/Deployment/ServiceAccount** và nhãn bảo mật.
- Tắt auto-mount ServiceAccount token khi ứng dụng không cần gọi Kubernetes API, theo nhu cầu bootstrap mesh.
- Không đồng nhất **Kubernetes API RBAC** với **quyền gọi HTTP giữa services**.
- Xác minh **token audience, issuer, lifecycle** khi dùng token để bootstrap danh tính.
- Theo dõi các certificate được cấp **cho principal mới** và thay đổi policy liên quan.

**Gắn label checkout lên một Pod không phải bằng chứng mật mã nó là checkout.** Nếu policy mạng tin labels, cần bảo vệ quyền chỉnh labels; nếu authorization dựa vào mTLS identity, cần bảo vệ issuance và private key.

## 17. Bảo vệ khóa riêng và phân phối chứng thư

Trong một số mesh, proxy nhận chứng thư/khóa riêng qua **Secret Discovery Service (SDS)** hoặc agent cục bộ, thay vì ứng dụng tự tải chứng thư từ file cố định.

~~~text
Identity issuer / CA
         |
    certificate/key material
         |
    authorized agent / SDS
         |
    proxy memory / secured storage
         |
    TLS connection handshake
~~~

### Các ràng buộc cần xác minh

| Rủi ro | Biện pháp |
|---|---|
| **Private key bị lộ qua filesystem/secret** | Hạn chế mount/permissions, tránh log/debug dump |
| **Unauthorized agent connection** | Bảo vệ Unix socket/API và xác thực workload |
| **Key reuse giữa services** | Cấp danh tính và khóa theo workload theo yêu cầu |
| **Old certificate tồn tại quá lâu** | Short-lived SVID, rotation và expiry alert |
| **CA signing key bị xâm phạm** | Issuer isolation, key management, audit, incident response |
| **Clock drift** | Đồng bộ thời gian và theo dõi notBefore/notAfter |
| **Trust bundle sai** | Cấu hình đúng trust domain/roots, kiểm thử cross-cluster |

**Không yêu cầu pod operator tải private key ra terminal để “kiểm chứng mTLS”.** Có thể dùng read-only metadata, certificate subject/SAN/expiry ở điểm được phép hoặc các mesh metrics mà không tiết lộ private key.

## 18. Certificate issuance, rotation và CA rollover

Một service mesh thường sử dụng chứng thư workload **ngắn hạn** và tự động **renew/rotate** trước khi hết hạn, giảm thời gian một credential bị lộ còn dùng được và hạn chế thao tác thủ công.

### Vòng đời tiêu biểu

~~~text
Workload scheduled / starts
           |
    Identity attested
           |
    Short-lived SVID issued
           |
    Proxy establishes mTLS
           |
    Periodic renewal
           |
    New certificate/key loaded
           |
    New connections use current identity
           |
    Old material expires / is discarded
~~~

### Rotation cần chú ý

- **NotAfter:** cảnh báo trước hết hạn với thời gian đủ cho nhân sự/đợt rollback.
- **Renewal errors:** issuer unavailable, CSR bị từ chối, permission drift.
- **Trust bundle synchronization:** bên xác minh phải tin đúng root/intermediate trong giai đoạn chuyển đổi.
- **Existing connections:** khi chứng thư thay đổi, session đang hoạt động có thể tiếp tục theo ngữ nghĩa TLS/proxy; không đồng nghĩa mọi kết nối cũ lập tức bị hủy.
- **Canary/new Pods:** Pod mới có thể gặp lỗi bootstrap khi Pod cũ vẫn chạy bình thường.
- **Key protection:** rotation không được làm lộ private key qua debug/log/CI artifacts.

### Root/intermediate CA rollover

~~~text
Phase 1: All verifying peers trust CA-old
Phase 2: Distribute trust: CA-old + CA-new
Phase 3: Start issuing identities under CA-new
Phase 4: Verify all workloads have migrated
Phase 5: Remove CA-old from trust bundle safely
~~~

Trình tự là **mô hình giải thích**; quy trình thực có thể phức tạp hơn với intermediate rotation, trust domain federation và certificate chain. **Không gỡ CA-old trước khi những client/server còn dùng chain cũ chuyển xong**, và không duy trì hai trust anchors vô thời hạn nếu một anchor đã không còn được kiểm soát.

### Revocation và chứng thư ngắn hạn

Mesh sử dụng chứng thư sống ngắn đôi khi dựa vào **expiry/rotation và policy changes** hơn là kiểm tra CRL/OCSP cho từng kết nối. Khả năng revocation thực tế **phụ thuộc sản phẩm, kiểu credential và proxy**. Nếu khóa bị nghi lộ, cần **incident response và thu hẹp quyền/cách ly workload ngay**, không chỉ chờ certificate tự hết hạn.

## 19. Control plane/CA outage: hệ thống phản ứng thế nào?

Nếu mesh CA hoặc control plane gián đoạn, **những mTLS connection đã thiết lập có thể tiếp tục**; nhưng Pod mới cần chứng thư, kết nối mới, rotation, policy pushes và thay đổi endpoints có thể gặp lỗi.

### Những tình huống cần thử trong lab

| Tình huống | Khả năng ảnh hưởng |
|---|---|
| Proxy đang phục vụ, control plane mất vài phút | Có thể dùng cấu hình/cache hiện có |
| Pod mới start khi CA không cấp certificate | Không bootstrap mTLS identity được |
| Certificate gần hết hạn khi renewal bị lỗi | New handshakes có thể thất bại sau expiry |
| Trust bundle rollout nửa chừng | Peer tin CA khác nhau, connection failure |
| Policy change không tới một nhóm proxy | Quyền thực thi không đồng nhất giữa replicas |
| Recovery đồng thời nhiều Pod | Issuer/load burst, cần capacity/rate limiting |

**Không bật plaintext fallback tự động để “giữ availability” nếu hệ thống phải bắt buộc mTLS.** Với bảo vệ dữ liệu nhạy cảm, kết nối **không xác thực được peer** phải từ chối theo chính sách. Những phương án degraded mode cần được phê duyệt từ threat model, không phát sinh từ thao tác chữa cháy tùy ý.

### Tiêu chí chọn giải pháp HA

- Control plane/CA có **replicas**, health, backup và cơ chế failover được thiết kế?
- Trust/key issuance có **rate/availability SLO**?
- New workloads được dự trù certificate bootstrap trong rolling upgrade?
- Proxy có **observability** khi policy/secret quá cũ?
- Đồng hồ node/VM có đủ tin cậy cho TLS validation?
- Recovery có kiểm thử **không downgrade plaintext**?

## 20. Ingress Gateway và nơi TLS được kết thúc

Traffic từ Internet hoặc đối tác có thể dùng **server-authenticated TLS, client mTLS hoặc protocol khác** tới edge gateway; gateway sau đó tạo một kết nối khác tới workload trong mesh.

~~~text
Browser / Partner
       |
       | TLS or external mTLS policy (Hop A)
       v
Ingress Gateway
       |
       | Mesh mTLS (Hop B)
       v
Workload inventory
       |
       | app-level authorization
       v
Business data
~~~

**TLS Hop A không phải TLS Hop B.** Certificate và identity của user/partner phía ngoài khác **workload identity của gateway** khi gateway gọi backend. Backend không nên suy **gateway-sa** là người dùng cuối cùng và cấp mọi quyền cho tất cả request.

### Những kiểm soát cần có

1. Edge xác thực **server name, TLS policy và client token/mTLS** nếu hợp đồng yêu cầu.
2. Gateway xác minh/truyền **end-user identity** bằng cơ chế đáng tin (token có audience, signature, TTL).
3. Backend mesh xác minh **gateway workload identity** và **AuthorizationPolicy**.
4. Backend ứng dụng xác minh **user/tenant/resource authorization**.
5. Traffic giữa gateway và backend bảo vệ đúng hop, không phụ thuộc “mạng internal là an toàn”.
6. Không tin **X-Forwarded-User hoặc custom headers** từ client bên ngoài nếu gateway không xóa/ghi đè và bảo vệ nguồn.

## 21. Egress Gateway, external services và chỗ mTLS dừng lại

Khi workload gọi một API bên ngoài mesh, remote service có thể không có **mesh SPIFFE identity** và không tham gia cùng CA/trust domain. Không thể giả định **mTLS xuyên suốt tới mọi Internet host** chỉ vì app đã bật sidecar.

~~~text
Mesh workload
     |
  mTLS to egress gateway (internal hop)
     |
  Egress gateway
     |
  TLS/mTLS per external provider contract
     |
  Third-party API
~~~

### Những điểm phải phân tích

| Đoạn kết nối | Identity/trust cần kiểm tra |
|---|---|
| Workload → egress proxy | Mesh workload identity, policy caller → gateway |
| Egress proxy → external API | DNS/SNI, public/private CA, hostname/SAN hoặc external client cert |
| Response external → proxy → workload | Correct origin, content validation, authorization |
| External private link/VPN | Route/firewall và TLS; VPN identity không thay workload identity |

Nếu proxy **passthrough TLS** thay vì terminate, data-plane có thể không có đủ metadata L7 để ra quyết định theo URL/method. Nếu proxy **terminate và tái mã hóa**, cần kiểm tra **cả hai TLS hops**. Cấu hình **ServiceEntry/egress policies** của từng mesh có thể ảnh hưởng discovery nhưng không tự chứng minh external API đã xác thực caller.

**Không coi egress gateway là biện pháp duy nhất chống exfiltration.** Cần network segmentation, policy theo đích, DNS governance, monitoring và quyền app/secret tối thiểu.

## 22. HTTP/2, gRPC, TCP và cách mTLS được áp dụng

mTLS bảo vệ **kênh truyền**; các tính năng authorization và telemetry phía trên phụ thuộc proxy hiểu được **giao thức ứng dụng** tới mức nào.

| Traffic | Data plane có thể biết | Điều cần kiểm tra |
|---|---|---|
| **TCP opaque** | Source/destination workload, port, bytes, connection status | Không tự biết business operation trong payload |
| **HTTP/1.1** | Method, path, headers khi proxy có quyền giải mã/parse | L7 policies và header trust boundaries |
| **HTTP/2** | Stream và HTTP semantics khi proxy hỗ trợ | Per-stream identity/request context, gRPC status |
| **gRPC** | Service/method, status/trailers khi proxy gRPC-aware | Authz theo method và resource trong message |
| **Database protocol** | TCP identity/port; có thể hỗ trợ protocol filters tùy product | DB authentication/roles vẫn bắt buộc |
| **Message broker** | Peer connection, một số metadata theo filter | ACL/topic/consumer group authorization |
| **UDP/QUIC** | Phụ thuộc proxy/mesh/CNI và chế độ kết nối | Không giả định TCP mTLS policy tự bao phủ UDP |

### TLS origination và protocol detection

Nếu ứng dụng **đã dùng TLS riêng** bên trong, sidecar có thể chỉ thấy **TCP/TLS encrypted payload**, không thể tự đọc HTTP method trừ khi phù hợp với kiến trúc TLS termination. Ngược lại, application plaintext tới sidecar có thể cho proxy đọc/kiểm soát L7 trước khi thiết lập mesh mTLS. Phải phân biệt:

- **Application TLS**: TLS kết thúc trong application hoặc trước đó.
- **Mesh mTLS**: TLS kết thúc ở mesh data plane giữa proxies/agents.
- **End-to-end TLS**: thuật ngữ phải định nghĩa **endpoint cụ thể**, không chỉ nhìn hình khóa trên dashboard.

Không nên bật transparent proxy hoặc L7 filters mà chưa biết **HTTP/2, gRPC streaming, websocket, TCP database, TLS passthrough** có được hỗ trợ đúng không.

## 23. Truy cập trực tiếp, excluded ports và bypass quanh data plane

Một mối nguy lớn là traffic đi qua một con đường **không được proxy/mTLS policy kiểm soát**.

~~~text
Authorized intended path:
  Checkout App -> Proxy A == mTLS ==> Proxy B -> Inventory App

Possible unintended path:
  Untrusted Pod ------------ direct TCP ------------> Inventory App
                      (only if routing/listener/policy permits)
~~~

### Nguyên nhân có thể tạo bypass

1. Một Pod **không được inject/enroll** vào mesh trong khi vẫn có route tới backend.
2. **Inbound/outbound port exclusions** loại service port hoặc management port khỏi redirect.
3. **hostNetwork hoặc node-originated traffic** có đường thực thi khác mạng Pod thường.
4. Một container **privileged/NET_ADMIN** có quyền hoặc cấu hình làm thay đổi traffic redirection.
5. Một load balancer/Service route tới **listener thứ hai** không nằm trong policy mTLS.
6. Mạng cho phép **direct Pod IP** và ứng dụng không có chính sách bảo vệ khi proxy không intercept.
7. Sidecar/agent không sẵn sàng, nhưng **app vẫn khởi động phục vụ** ở chế độ fallback không được phê duyệt.
8. Một endpoint debug/metrics không được catalog hóa, dùng plaintext không có authorization.

### Những phép kiểm chứng nên có

| Đường | Kỳ vọng nếu có policy bắt buộc mTLS/least privilege |
|---|---|
| Workload được cấp quyền → Service DNS | mTLS PASS và business request ALLOW |
| Workload được cấp quyền → Pod IP | Không bỏ qua authz/mTLS theo kiến trúc |
| Workload không có mesh identity → service port | DENY ở lớp thích hợp |
| Workload trong mesh nhưng principal không được phép | mTLS có thể PASS; authorization phải DENY |
| hostNetwork/legacy client → service | DENY hoặc qua gateway/bridge có mTLS đã duyệt |
| Untrusted workload → admin/metrics/debug | DENY; không mở chỉ vì dùng port khác |

**Không kiểm thử bằng cách tắt sidecar/mTLS trên production**. Sử dụng staging và **workload test được phê duyệt**, giới hạn số yêu cầu, audit và dừng khi thấy ảnh hưởng.

## 24. Namespace và NetworkPolicy vẫn cần thiết khi đã có mTLS

Mạng Kubernetes **không tự ngăn Pod khác namespace gọi nhau**. Nếu chỉ bật STRICT mTLS, một workload thuộc trust domain vẫn có thể sở hữu chứng thư hợp lệ và tiếp cận một service mà nó không có quyền nghiệp vụ, trừ khi có policy bổ sung.

### Kết hợp hai trục kiểm soát

~~~text
        Source Pod in shop namespace
                     |
           K8s NetworkPolicy egress
                     |
              Mesh mTLS connection
                     |
         Destination NetworkPolicy ingress
                     |
           Mesh workload authorization
                     |
             Application authorization
~~~

| Policy | Dùng để giới hạn |
|---|---|
| **Kubernetes NetworkPolicy** | Source/destination Pod/namespace/IP/port theo CNI |
| **Mesh PeerAuthentication** | Kênh đến có đòi mTLS/identity hay không |
| **Mesh AuthorizationPolicy** | Workload principal được gọi service/port/method nào |
| **Application policy** | Dữ liệu/hành động user hoặc tenant được phép |
| **RBAC/admission** | Ai được đổi cấu hình trust/policy/Pod/labels |

**NetworkPolicy là lớp chặn bổ trợ**, nhưng không phải mọi CNI đều thực thi cùng một path. Trong một số mesh, proxy traffic, gateway NAT hoặc ambient routing có thể ảnh hưởng **điểm áp policy**; test trong cluster thật là bước bắt buộc.

## 25. Multi-cluster, multi-network và trust domain federation

Khi hai cluster ở hai region hoặc hai nhà cung cấp cloud cần gọi nhau, mTLS có thể mở rộng theo mô hình **shared trust domain**, **trust-domain alias** hoặc **federation** được quản trị. Mỗi lựa chọn thay đổi phạm vi danh tính được tin.

~~~text
Cluster A / Region A                  Cluster B / Region B
Trust domain: corp-a.test             Trust domain: corp-b.test
       |                                       |
  Checkout identity                         Inventory identity
       |                                       ^
       |           VPN / private link          |
       +---- gateway == authorized mTLS ======+
                   trust federation
~~~

**corp-a.test/corp-b.test là tên mô tả**, không phải hệ thống đã cấu hình. Xác thực giữa hai trust domains phải có **trust bundles, certificate path validation, SPIFFE ID mapping và authorization** được phê duyệt.

### Những quyết định quan trọng

1. **Trust boundary:** cluster khác có được cấp danh tính **cùng quyền** với cluster hiện tại không?
2. **Root/CA trust:** có tin toàn bộ root của cluster kia hay chỉ một tập issuer/identity nhất định?
3. **Alias/canonicalization:** principal có thể được đổi tên giữa trust domains không và ở đâu?
4. **Namespace collision:** hai cluster đều có namespace shop/serviceaccount checkout-sa, liệu chúng có bị nhận nhầm là cùng workload?
5. **Routing và gateways:** đâu là điểm termination, source identity nào được backend thấy?
6. **Revocation/incident response:** khi CA của đối tác bị nghi xâm phạm, ai có quyền ngắt trust?
7. **Network controls:** peering/VPN/Transit Gateway/firewall có giới hạn đúng nguồn/đích không?
8. **Telemetry:** logs có giữ **trust domain/cluster identity** đủ để điều tra không?

**Cùng chuỗi /ns/shop/sa/checkout-sa ở hai cluster không tự là cùng danh tính đáng tin.** Chính sách authorization cần tính cả trust domain/issuer và federation contract.

## 26. Dùng mTLS với VM, bare metal và legacy workloads

Không phải tất cả workload đều là Kubernetes Pod có ServiceAccount. Một VM, batch worker, service on-prem hoặc thiết bị network cũng có thể cần tham gia trust domain hoặc đi qua gateway.

### Các phương án kiến trúc

| Phương án | Cách bảo vệ | Cần xem |
|---|---|---|
| **Identity agent trên VM** | Attestation/issuance SVID cho workload VM | Node identity, agent permissions, key storage |
| **Mesh gateway bridge** | Kết thúc TLS/mTLS rồi gọi mesh service | Gateway identity có đại diện đúng caller không? |
| **Application-native mTLS** | Ứng dụng tự xác minh cert/workload identity | Library support, rotation, SAN validation |
| **VPN + TLS/mTLS** | Bảo vệ đường WAN và danh tính workload | Tunnel không thay client identity |
| **Temporary legacy exception** | Cho phép hẹp theo IP/port trong giai đoạn chuyển đổi | Owner, expiry, risk acceptance, rollback |

**Không để một “legacy exception” tồn tại vô thời hạn** rồi trở thành đường plaintext quanh các service nhạy cảm. Đặt ngày kết thúc, thống kê traffic, kế hoạch chuyển sang mTLS và kiểm thử trước khi gỡ.

## 27. Hiệu năng, resource limits và availability

mTLS có chi phí **handshake, CPU mã hóa, bộ nhớ proxy, certificate verification và telemetry**. Thường có thể giảm overhead bằng connection reuse, TLS session mechanisms và tối ưu proxy, nhưng **không nên tắt xác thực để tăng hiệu năng** khi chính sách an ninh yêu cầu.

### Điểm cần benchmark

- Handshake latency và new connections/s theo các loại client.
- In-flight connections/HTTP/2 streams, proxy CPU/memory, connection pools.
- p50/p95/p99 API latency trước/sau bật mTLS.
- Certificate renewal, config push và concurrent rollouts.
- Retry amplification nếu TLS handshake lỗi hoặc endpoint flapping.
- Proxy buffer/queue saturation và ảnh hưởng tới app SLO.
- Streaming/long-lived connection khi cert rotation hoặc pod drain.

### Failure classification

| Kết quả | Có thể do | Không được làm |
|---|---|---|
| **TLS handshake failure** | Untrusted CA, identity mismatch, expired cert, TLS protocol issue | Tự tắt verify để gọi cho chạy |
| **mTLS PASS, HTTP 403** | Mesh/app authorization từ chối | Mở service to all để chữa quyền |
| **mTLS PASS, HTTP 503/gRPC UNAVAILABLE** | Backend unhealthy, routing/proxy/circuit breaker | Quy kết luôn cho PKI |
| **Proxy timeout** | Network path, overload, response queue, policy | Tăng timeout vô hạn |
| **Client certificate renewal fail** | CA/control plane outage, bootstrap/RBAC | Chuyển plaintext ngoài change control |
| **Certificate valid, principal denied** | Identity không được cấp quyền method/service | Đổi certificate tùy tiện |

**Availability và security phải cùng được kiểm thử.** Một thay đổi làm tăng tỷ lệ ALLOW bằng cách bỏ yêu cầu mTLS có thể làm cải thiện uptime số học nhưng phá vỡ tiêu chí bảo mật.

## 28. Đo mTLS coverage và policy enforcement

“mTLS enabled” trong cấu hình hoặc dashboard chỉ là **một tín hiệu**. Để kết luận coverage, cần định nghĩa rõ **tập lưu lượng kỳ vọng**, phạm vi quan sát và tỷ lệ kết nối thực sự mã hóa/xác thực.

### Tầng đo quan trọng

| Tầng | Quan sát cần có |
|---|---|
| **Workload inventory** | Pod/VM/service nào nằm trong mesh, identity, owner và env |
| **Certificate inventory** | SPIFFE IDs/SANs, issuer, trust domain, expiry, rotation success |
| **Data plane connections** | TLS/mTLS mode, peer identities, handshake result |
| **Policy distribution** | Proxy nào có bản policy/trust bundle hiện tại |
| **Authorization** | Allowed/denied principals by service/method, reason |
| **Network** | Route/path, Pod IP/gateway/NAT, NetworkPolicy drops |
| **Application** | HTTP/gRPC status, tenant authorization, resource outcome |
| **Exceptions** | Out-of-mesh services, excluded ports, legacy HTTP exceptions |

### Những KPI có thể thiết kế

- **Expected-mTLS coverage:** phần trăm luồng **được yêu cầu mTLS** có bằng chứng mTLS tại đúng hop.
- **Unknown/unclassified rate:** tỷ lệ traffic không xác định được peer identity hoặc TLS mode.
- **Unauthenticated attempts:** số lượng/nguồn kết nối bị chặn vì thiếu chứng thư theo baseline.
- **Unauthorized principal attempts:** số request có mTLS identity hợp lệ nhưng không được phép truy cập service.
- **Certificate health:** tỷ lệ chứng thư gần hết hạn, renewal failed, CA/trust drift.
- **Policy convergence lag:** thời gian cấu hình mới được data planes nhận và thực thi.
- **User-facing SLO:** tỷ lệ request đúng nghiệp vụ thành công, latency sau rotation/rollout.

### Giới hạn của phép đo

Một NIDS ngoài mesh có thể chỉ thấy **TCP/IP flow hoặc TLS metadata**, không đọc service identity/SPIFFE SAN sau khi TLS bắt đầu hoặc không thấy HTTP/gRPC payload. Phải phối hợp **proxy telemetry, CNI flow records, cert inventory và app logs**; không kết luận traffic không tồn tại chỉ vì sensor không nhìn thấy plaintext.

## 29. Logging, tracing và cảnh báo không làm lộ dữ liệu

### Mẫu sự kiện đã che dữ liệu

~~~text
timestamp=2026-11-28T13:30:00+07:00
environment=staging
cluster=shop-cluster-a
source_service=checkout
source_identity=spiffe://cluster.local/ns/shop/sa/checkout-sa
destination_service=inventory
destination_identity=spiffe://cluster.local/ns/catalog/sa/inventory-sa
transport_security=mutual_tls
tls_version=TLSv1.3
trust_domain=cluster.local
policy=allow-checkout-to-inventory
policy_decision=ALLOW
http_method=POST
rpc=/inventory.v1.InventoryService/GetItem
grpc_status=OK
trace_id=example-trace-001
client_private_key=[NOT_COLLECTED]
authorization_token=[REDACTED]
~~~

Đây là **log giả lập**, không phải output cố định của một mesh. Một số proxies chỉ log **peer principal** hoặc TLS security level mà không tự log destination identity; ứng dụng/mesh exporter cần được cấu hình đúng. Không tự thêm dữ liệu nhạy cảm vào log vì muốn forensic chi tiết.

### Những sự kiện cần cảnh báo

| Tín hiệu | Vì sao quan trọng |
|---|---|
| **Handshake failures tăng đột ngột** | CA/trust drift, cert expiry, policy migration hoặc client lỗi |
| **Unknown principal trên service nhạy cảm** | Workload không enrolled, proxy bypass hoặc attribution gap |
| **Plaintext traffic vào mesh-required listener** | Đường chưa tuân thủ mTLS policy |
| **Policy DENY từ service bất thường** | Lateral access attempt hoặc rollout sai |
| **Certificate nearing expiry / rotation failure** | Nguy cơ hết hạn đồng loạt gây outage |
| **Issuer/trust bundle unexpected change** | Rủi ro supply chain/CA governance |
| **New service account identity** | Workload mới có thể thay đổi quyền mặc định |
| **Unexpected port exclusions** | Có thể tạo đường không đi qua data plane |
| **Policy version skew** | Một số proxies có thể thực thi quyền không nhất quán |
| **L7 authz errors sau mesh change** | Thay trust/route có thể ảnh hưởng identity propagation |

### Nguyên tắc bảo vệ telemetry

- Không lưu **private key, full certificate key material, bootstrap token, Authorization header hoặc cookies**.
- Giới hạn danh sách principal và trace theo **RBAC/retention**; identity có thể tiết lộ cấu trúc hệ thống.
- Tách **policy decision** khỏi **transport handshake result** để điều tra chính xác.
- Với tracing, **trace ID không phải danh tính**, có thể do client gửi trong một số tình huống.
- Theo dõi **logs thiếu dữ liệu** như một coverage gap, không coi “không thấy DENY” là đã an toàn.

## 30. Runbook phân loại sự cố mTLS giữa workload

### Bước 1 — Xác định phạm vi và trust boundary

1. Lấy **thời gian, source/destination workload, namespace, cluster, ServiceAccount, Pod/VM, node/region, port**.
2. Xác định client kết nối **Pod IP, Service DNS, mesh gateway, external address** hay một path khác.
3. Kiểm tra **ngữ nghĩa lỗi**: DNS failure, TCP timeout/refused, TLS alert/handshake failure, policy DENY, HTTP/gRPC status.
4. Kiểm tra **thay đổi gần đây**: cert rotation, CA rollover, injection, deployment, mesh upgrade, trust domain, NetworkPolicy, route/VPN.
5. Gắn owner cho **PKI, mesh control plane, app và network** theo điểm lỗi.

### Bước 2 — Định vị tầng

~~~text
Cross-workload RPC failed
             |
        DNS resolves?
         /        \
        No        Yes
        |          |
    DNS egress   TCP path reachable?
                 /           \
                No            Yes
                |              |
          Route/CNI/SG       TLS handshake passes?
                             /             \
                            No             Yes
                            |               |
                   CA/SAN/EKU/clock     Authz policy allows?
                   cert/mesh mode         /           \
                                        No            Yes
                                        |              |
                                    Principal/       App business
                                    policy           result/timeout
~~~

### Bước 3 — Xem chứng thư mà không lộ private key

- Validity **notBefore/notAfter**, issuer, SAN URI và trust domain.
- Client có certificate material phù hợp và server **thật sự yêu cầu/kiểm tra client cert** không?
- Peer identities có đúng với ServiceAccount/cluster/trust domain được cấp quyền không?
- Data plane có **policy/trust bundle phiên bản mới** chưa?
- Có chứng thư bị cấp sai identity, trùng không mong muốn hoặc hết hạn đồng loạt không?

### Bước 4 — Containment có kiểm soát

1. Nếu principal trái quyền xuất hiện, áp **AuthorizationPolicy/NetworkPolicy deny-by-default** tương ứng theo change đã duyệt.
2. Nếu cert sắp hết hạn, khôi phục **issuer/rotation** thay vì tắt xác thực.
3. Nếu CA rollover không đồng bộ, sửa trust bundle/issuance theo quy trình có khả năng rollback, không thêm CA lạ tùy tiện.
4. Nếu sidecar injection/bypass sai, sửa **admission/redirect/excluded ports** và kiểm tra đường thực.
5. Nếu gateway truyền user identity không an toàn, sửa **token validation, header sanitization** trước khi phục hồi route.
6. Nếu nghi CA/khóa riêng bị xâm phạm, thực hiện **incident response, identity isolation và key rotation**, lưu bằng chứng theo quy định.

### Bước 5 — Hậu kiểm

Chỉ kết luận xử lý thành công khi đồng thời thấy:

- **Caller hợp lệ → service đúng**: mTLS PASS, identity match, service authz ALLOW, business result đúng.
- **Caller không có chứng thư/không enrolled**: không dùng plaintext để bypass.
- **Caller mTLS hợp lệ nhưng không có quyền**: service authz DENY.
- **Caller được gọi method nhưng không có quyền object/tenant**: app DENY.
- **Đường direct Pod IP/hostNetwork/legacy** không tạo bypass ngoài ý định.
- **Certificate rotation và trust** hoạt động tiếp sau deploy/failover.
- **Telemetry và audit** đủ chứng minh các lớp đã được thực thi.

## 31. Case study 1: chuyển PERMISSIVE sang STRICT làm gián đoạn dịch vụ

**Bối cảnh giả định:** Nhóm vận hành đã bật service mesh cho phần lớn Pod thuộc namespace **catalog**. Một batch worker cũ chạy trên VM kết nối thẳng tới **inventory:8080** qua VPN bằng HTTP cleartext. Sau khi bật **PeerAuthentication STRICT** tại catalog, batch worker bắt đầu timeout hoặc nhận lỗi kết nối; các Pod mesh-native vẫn gọi thành công.

### Timeline giả lập

~~~text
09:00  Mesh control plane healthy, inventory available.
09:05  Apply STRICT policy to namespace catalog.
09:06  Mesh-native checkout -> inventory: mTLS OK.
09:07  Legacy VM -> inventory: connection/handshake fails.
09:10  App dashboard: inventory health PASS, batch import FAIL.

Changes:
  PeerAuthentication: PERMISSIVE -> STRICT
  VM client: not onboarded to mesh identity
~~~

### Giả thuyết cần kiểm tra

1. VM không có **client identity** được chấp thuận để thiết lập mesh mTLS.
2. Route/VPN tới inventory thay đổi đúng lúc, không liên quan policy.
3. VM có TLS nhưng **trust domain/client cert không đúng**.
4. Strict policy được áp quá rộng cho namespace gồm nhiều loại callers.
5. Gateway chuyển tiếp VM traffic nhưng **không origination mTLS** tới backend.

### Cách xác minh

- Đối chiếu **peer identity và handshake errors** ở data plane, không chỉ HTTP logs.
- Kiểm tra **policy scope, version/config convergence** của các proxy inventory.
- Thực hiện một phép thử **từ VM test được cho phép** trên staging, không thay đổi production firewall tùy ý.
- Xác nhận mesh-native caller dùng đúng mTLS và vẫn được authorization.

### Phương án khắc phục

1. Ưu tiên **onboard VM bằng identity agent** hoặc cho VM đi qua gateway có **client/peer authentication** rõ ràng.
2. Nếu cần giai đoạn chuyển đổi, dùng **ngoại lệ nhỏ nhất**, cô lập port/workload, có owner, expiry, telemetry và phê duyệt rủi ro.
3. Không bật PERMISSIVE cho mọi workload nhạy cảm chỉ để cứu một batch job.
4. Kiểm tra lại **plaintext DENY** trên các service không có ngoại lệ, **mTLS ALLOW** với caller hợp lệ, và user-level authorization.

**Bài học:** Migration mTLS phải lập danh mục caller và trust boundary trước khi chuyển STRICT; một kết nối legacy mất dịch vụ không chứng minh STRICT sai, mà có thể cho thấy một dependency chưa được đưa vào mô hình identity.

## 32. Case study 2: CA rollover làm workload mới không bắt tay được

**Bối cảnh giả định:** Một mesh chuẩn bị chuyển intermediate CA. Một nhóm proxies/agents nhận certificate chain mới nhưng không nhận đủ **trust bundle** mới do lỗi phân phối config trên một node. Pod cũ còn các session hiện hành nên hệ thống trông tương đối khỏe; khi autoscaling tạo Pod mới, các gRPC calls tới một số backends thất bại.

### Dấu hiệu

~~~text
Region A:
  Existing proxy connections: mostly healthy
  New pod handshakes: failing for subset of destinations

Proxy certificate:
  SAN: spiffe://cluster.local/ns/catalog/sa/inventory-sa
  Issuer: intermediate-new
  Validity: within NotBefore/NotAfter

Some verifying peers:
  Trust bundle: old CA chain only

Observed:
  TLS trust/path validation errors
~~~

### Nguyên nhân không nằm ở port 8443

TCP route và firewall đều cho gói đến; **xác thực certificate chain thất bại** ở bước TLS, trước khi service policy xử lý request. Mở NACL/SG hoặc tắt hostname/identity validation không sửa nguyên nhân gốc và có thể tạo lỗ hổng.

### Hướng xử lý

1. Kiểm tra issuer/chain/trust bundle từ **nguồn chứng thư công khai đã được cấp quyền**, không tải private keys.
2. Đối chiếu chính xác **proxy config version/secret distribution**, các node/cluster và thời điểm rollover.
3. Khôi phục trình tự **trust-new-before-issue-new**, tuân theo quy trình CA rollover được phê duyệt.
4. Duy trì khả năng phục hồi cho Pod mới và xác minh certificate renewals tự động.
5. Không giữ một CA đã bị nghi xâm phạm chỉ để tăng tỷ lệ handshake thành công; nếu có compromise, dùng incident response riêng.
6. Test trên **new pods, existing sessions, rolling restart và regional failover**, không chỉ một connection lâu đời.

**Bài học:** Certificate hợp lệ theo thời gian chưa đủ; peer còn phải tin đúng **issuer/trust chain** và xác minh đúng **SPIFFE identity/trust domain**.

## 33. Case study 3: mTLS hoàn toàn hợp lệ nhưng vẫn có lateral access

**Bối cảnh giả định:** Các microservice trong namespace **shop** sử dụng chung ServiceAccount **default** nên có cùng workload identity theo quy ước mesh. Inventory đặt STRICT mTLS nhưng không có AuthorizationPolicy giới hạn callers. Một test processor bị xâm nhập có thể gọi method inventory thay checkout.

### Kết quả dễ gây hiểu nhầm

~~~text
Caller:
  shop/test-processor
  ServiceAccount: default
  Mesh principal: cluster.local/ns/shop/sa/default

Target:
  catalog/inventory
  PeerAuthentication: STRICT
  AuthorizationPolicy: no restrictive policy on target

Transport:
  mTLS handshake succeeds

Business:
  potentially unintended API operation reached
~~~

### Điểm thất bại ở đâu?

**mTLS đang làm đúng chức năng xác thực**, nhưng **identity quá rộng** và **authorization không giới hạn phương thức/nguồn**. Nếu inventory còn tin một tenant_id do client gửi, lỗi có thể lan sang **object-level authorization**.

### Sửa theo thứ tự

1. Cấp **ServiceAccount riêng** cho checkout và test-processor; bảo vệ quyền tạo Pod/gán ServiceAccount.
2. Yêu cầu inventory chỉ nhận principal **checkout-sa** trên các route/port được phê duyệt.
3. Dùng NetworkPolicy ngăn Pod không được duyệt tới inventory ở L3/L4.
4. Ở ứng dụng, kiểm tra **user/token/tenant/resource** độc lập với mesh identity.
5. Xác nhận **unapproved workload có chứng thư hợp lệ** vẫn bị **AuthorizationPolicy DENY**.
6. Test một caller hợp lệ nhưng truy cập object ngoài quyền để chứng minh **app DENY**.

**Bài học:** mTLS không giải quyết phân quyền thay ứng dụng. Identity phân biệt kém (cùng một ServiceAccount cho nhiều service) làm giảm giá trị audit và chính sách least privilege.

## 34. Case study 4: trust-domain alias làm phạm vi tin cậy rộng hơn thiết kế

**Bối cảnh giả định:** Cluster A và B có cùng tên namespace/service account. Để hợp nhất nhanh, nhóm cấu hình một cơ chế alias/federation rộng, sau đó policy ở cluster A chỉ so khớp phần identity **/ns/shop/sa/checkout-sa** mà không phân biệt trust domain hoặc issuer.

~~~text
Cluster A:
  spiffe://corp-a.test/ns/shop/sa/checkout-sa

Cluster B:
  spiffe://corp-b.test/ns/shop/sa/checkout-sa

Risky interpretation:
  treating both as "same checkout" without formal federation scope.
~~~

### Hướng kiểm soát

- Ràng buộc **trust domain/issuer/cluster identity** đúng theo federation contract.
- Chỉ alias những identity/nhóm cần thiết; không tin toàn bộ cluster đối tác mặc nhiên.
- Định nghĩa ai có thể cấp ServiceAccount tên trùng và ai có thể sửa policy.
- Đo **principal nhận thực** ở backend, không suy từ Kubernetes namespace name.
- Diễn tập **thu hồi trust của cluster đối tác** nếu CA hoặc admin boundary bị xâm phạm.
- Kiểm tra NetworkPolicy/cloud gateway ở mỗi phía; federation chỉ là một lớp.

**Bài học:** Đổi cấu hình trust domain có thể ảnh hưởng **toàn bộ tập principal được tin**, không phải chỉ sửa một URL.

## 35. Lab an toàn: quan sát mTLS và policy ở môi trường được cấp quyền

Mục tiêu bài lab là chứng minh **mTLS peer identity và authorization** bằng phép thử ít tác động trong **staging/isolated cluster**. Không tắt TLS, không gỡ sidecar, không trích xuất private key, không thay default mesh policy trên production chỉ để minh họa.

### 35.1. Chuẩn bị ma trận caller

~~~text
Namespace: shop
  Checkout test Pod:
    ServiceAccount checkout-sa
    Intended call: inventory GetItem

Namespace: catalog
  Inventory test Pod:
    ServiceAccount inventory-sa
    Allowed caller: checkout-sa

Namespace: sandbox
  Unapproved test Pod:
    ServiceAccount sandbox-sa
    Intended outcome: DENY inventory

Policy target:
  Require mTLS
  Allow only approved workload identity
  Preserve application object-level auth
~~~

Với các service HTTP/gRPC thật, cần **health/test method read-only có phép** và tài khoản/token lab. Không dùng dữ liệu thanh toán hoặc customer secrets.

### 35.2. Đọc trạng thái các resource Kubernetes

~~~bash
# Chọn context đã được cấp quyền; những lệnh sau chỉ đọc API.
kubectl config current-context
kubectl get namespaces --show-labels
kubectl get pods -n shop -o wide
kubectl get pods -n catalog -o wide
kubectl get serviceaccounts -n shop
kubectl get serviceaccounts -n catalog
kubectl get networkpolicies -n shop
kubectl get networkpolicies -n catalog
~~~

Các lệnh này giúp nắm workload/labels/SA/network policy nhưng **không tự chứng minh có mTLS**. Không in ServiceAccount tokens hoặc Kubernetes Secrets vào báo cáo.

### 35.3. Đọc chính sách Istio nếu cluster hỗ trợ

~~~bash
# Chỉ sử dụng nếu đúng cluster có Istio CRDs này.
kubectl get peerauthentications.security.istio.io -A
kubectl get authorizationpolicies.security.istio.io -A

# Xem policy đích và kiểm tra principal/selector.
kubectl get peerauthentications.security.istio.io -n catalog -o yaml
kubectl get authorizationpolicies.security.istio.io -n catalog -o yaml
~~~

**Không có CRD này không đồng nghĩa cluster không có mTLS**: mesh khác, application-native mTLS hoặc mode khác có thể được sử dụng. Ngược lại, resource tồn tại không chứng minh data plane đã nhận và đang thực thi đúng policy.

### 35.4. Xem chứng thư X.509 công khai đã được cấp cho lab

Nếu service owner cung cấp **bản certificate công khai** và **trust bundle công khai** dùng trong lab:

~~~bash
# Không dùng private key trong phép đọc này.
openssl x509 -in workload-public.crt \
  -noout -subject -issuer -dates \
  -ext subjectAltName

# Kiểm tra chuỗi với CA/intermediate được phê duyệt.
openssl verify \
  -CAfile trust-bundle.pem \
  -untrusted intermediates.pem \
  workload-public.crt
~~~

**openssl verify PASS chỉ chứng minh một khía cạnh path validation theo option đang dùng**, không đủ kết luận workload đã hoàn tất **mTLS client/server authentication**, peer đã match **SPIFFE URI SAN**, identity đã được cấp đúng hay L7 authorization đang thực thi. Nếu certificate chứa URI SAN, so khớp URI bằng cơ chế identity-aware phù hợp thay vì cho rằng **-verify_hostname** kiểu DNS là kiểm tra SPIFFE.

**Chỉ dùng file được cung cấp cho lab; không chạy lệnh đọc Secret/private-key của workload thật**. Nếu không có certificate public hoặc intermediate chain, ghi **NOT_TESTED** thay vì tự tìm credential ngoài phạm vi.

### 35.5. Kiểm chứng từ một caller đã được phép

Nếu Pod kiểm thử đã có sẵn và có **curl**, có thể gọi một endpoint read-only:

~~~bash
# Hostname và pod chỉ là ví dụ; phải thay bằng tài sản lab đã được phép.
kubectl exec -n shop checkout-test -- \
  curl --connect-timeout 2 --max-time 5 \
  --silent --show-error \
  http://inventory.catalog.svc.cluster.local:8080/health
~~~

Trong một **sidecar mesh**, URL HTTP từ application tới sidecar có thể là plaintext ở local hop, trong khi proxy dùng **mTLS trên network hop** đến backend. **Curl thành công không chứng minh mesh mTLS thành công** nếu chưa đối chiếu proxy identity/transport telemetry trên đường; cần giám sát đúng data plane và route.

### 35.6. Phép thử âm tính có phép

Từ một **sandbox-test Pod** (nếu đã được cấp quyền để thực hiện thử), kiểm tra một request read-only tương tự tới inventory. Kỳ vọng:

- Nếu sandbox thiếu mesh identity và đường buộc mTLS: **transport authentication fails** hoặc bị ngăn ở lớp network.
- Nếu sandbox có mTLS identity hợp lệ nhưng **không có authorization**: **policy DENY**.
- Nếu API yêu cầu user identity: **ứng dụng từ chối** khi thiếu quyền, dù mTLS peer được xác thực.

Lỗi cụ thể (timeout, reset, 403, gRPC PERMISSION_DENIED, v.v.) **tùy proxy, network path và ứng dụng**. Không coi một HTTP status duy nhất là chữ ký chuẩn của mọi loại DENY.

### 35.7. Phiếu kết quả

~~~text
Lab ID:                MESH-MTLS-001
Environment:           authorized staging / isolated lab
Cluster/trust domain:  [cluster and expected domain]
Source namespace/SA:   [verified]
Destination ns/SA:     [verified]
Source IP/route:       [observed]
Destination IP/port:   [observed]
Mesh data plane:       [sidecar/ambient/native/other]
Enforced policy:       [PeerAuthentication equivalent]
Client identity:       [expected and observed]
Server identity:       [expected and observed]
Certificate issuer:    [public metadata only]
Certificate validity:  [metadata; no secret]
Trust bundle version:  [approved version]
Transport outcome:     [mTLS PASS/FAIL/NOT_OBSERVED]
Authorization result:  [ALLOW/DENY/NOT_OBSERVED]
Business result:       [correct/denied/not tested]
Bypass path checked:   [PodIP/legacy/gateway/other]
Negative test:         [method and expected result]
Telemetry evidence:    [trace/proxy logs, redacted]
Verdict:               [PASS/FAIL/INCONCLUSIVE]
Owner/change record:   [responsible team/ticket]
~~~

**INCONCLUSIVE** là kết quả đúng nếu chỉ có manifest mà không biết enforcement point, thiếu telemetry handshake/peer identity hoặc không xác minh được route thật. Không kết luận “mTLS phủ 100%” từ một test service duy nhất.

## 36. Ma trận kiểm thử mTLS và authorization giữa workload

Bảng dưới đây mô tả **mục tiêu và kết quả kỳ vọng**; không phải lệnh khai thác hay thử tải. Thực hiện ở **lab/staging với service owners và stop conditions**. Trường hợp gây ngắt CA, proxy, VPN hoặc thay đổi trust ở production cần change/diễn tập được phê duyệt riêng.

| Test ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| **MTLS-01** | Checkout với đúng identity gọi inventory hợp lệ | mTLS PASS, authz ALLOW, API trả kết quả đúng |
| **MTLS-02** | Client thiếu certificate ở listener bắt buộc mTLS | Transport DENY theo policy |
| **MTLS-03** | Client dùng certificate do CA không được tin | Handshake/peer validation FAIL |
| **MTLS-04** | Server certificate có identity không phải inventory | Client từ chối identity mismatch |
| **MTLS-05** | Certificate hợp lệ về chain nhưng NotAfter đã qua | Validation FAIL; alert expiry |
| **MTLS-06** | Certificate chưa đến NotBefore vì clock sai | Validation FAIL, xử lý clock/time |
| **MTLS-07** | Cert có issuer đúng nhưng URI SAN không khớp | Identity validation FAIL |
| **MTLS-08** | Workload gửi chứng thư không được cấp đúng client EKU/policy | TLS verification đúng mục đích |
| **MTLS-09** | Workload thuộc mesh nhưng principal không được phép tới inventory | mTLS có thể PASS; authz DENY |
| **MTLS-10** | Checkout có quyền GetItem nhưng không có quyền DeleteItem | L7 method policy/app DENY |
| **MTLS-11** | Checkout có method ALLOW nhưng request item của tenant khác | Object-level authorization DENY |
| **MTLS-12** | Namespace catalog chuyển sang STRICT trong staging | Caller hợp lệ hoạt động, plaintext client bị từ chối |
| **MTLS-13** | Một workload legacy chưa enrolled | Không có fallback plaintext ngoài ngoại lệ có phép |
| **MTLS-14** | Có PeerAuthentication cùng scope với config khác | Xác định effective mode và rule precedence theo sản phẩm |
| **MTLS-15** | Có AuthorizationPolicy không chọn đúng labels/targetRefs | Phát hiện policy gap và sửa |
| **MTLS-16** | Pod không được sidecar inject/enroll | Không có đường bypass tới backend nhạy cảm |
| **MTLS-17** | Service port nằm trong danh sách excluded ports | Phát hiện plaintext/unprotected path |
| **MTLS-18** | Client gọi trực tiếp Pod IP thay vì Service DNS | Không bypass mesh authn/authz |
| **MTLS-19** | hostNetwork hoặc node-originated client | Node/host exception được kiểm soát, không vượt trust boundary |
| **MTLS-20** | App→sidecar local hop là plaintext | Threat model ghi rõ điểm TLS termination |
| **MTLS-21** | Mô hình ambient chỉ L4 nhưng cần authz gRPC method | Có waypoint/app L7 enforcement đã xác minh |
| **MTLS-22** | Client dùng HTTP/2/gRPC streaming dài | mTLS ổn định, deadline/rotation/drain phù hợp |
| **MTLS-23** | Opaque TCP database qua mesh | Peer identity đúng, DB auth/role vẫn được kiểm tra |
| **MTLS-24** | UDP hoặc protocol không thuộc khả năng mesh | Coverage gap được nhận diện và bảo vệ riêng |
| **MTLS-25** | Sidecar/proxy restart trong staging | Không tự downgrade plaintext; phục hồi SLO |
| **MTLS-26** | Proxy chưa nhận policy/secret mới | Phát hiện config version skew và remediation |
| **MTLS-27** | CA tạm gián đoạn trong lab | Existing vs new workloads được đánh giá riêng |
| **MTLS-28** | Cert renew trước khi hết hạn | Rotation thành công, không gián đoạn ngoài SLO |
| **MTLS-29** | CA rollover với dual trust bundle | Trust distribution/issuance đúng trình tự |
| **MTLS-30** | Gỡ CA-old sau khi mọi workload đã chuyển | Không còn handshake failures do CA-old |
| **MTLS-31** | Incident nghi lộ certificate private key | Có identity isolation/rotation/audit, không chờ expiry đơn thuần |
| **MTLS-32** | Ingress Gateway nhận user, gọi backend | Backend thấy gateway identity và user identity được xác minh riêng |
| **MTLS-33** | External API qua egress gateway | Kiểm tra cả mesh hop và external TLS/SAN/trust |
| **MTLS-34** | Multi-cluster shared trust domain | Identity không bị đánh đồng chỉ vì cùng tên namespace |
| **MTLS-35** | Multi-domain federation | Chỉ những issuers/principals được duyệt được tin |
| **MTLS-36** | Mất VPN/transit route trong hybrid | Phân loại network outage, không tắt mTLS |
| **MTLS-37** | IPv4/IPv6 trong cluster dual-stack | Không có đường v6 bypass policy |
| **MTLS-38** | Untrusted namespace có certificate mesh hợp lệ | Không được dùng identity hợp lệ để gọi mọi service |
| **MTLS-39** | ServiceAccount chung cho nhiều workloads | Phát hiện identity collision/sprawl và tách quyền |
| **MTLS-40** | Nhãn Pod/namespace bị thay ngoài quyền | Admission/RBAC bảo vệ membership và policy |
| **MTLS-41** | Mesh policy cấu hình ALLOW nhưng CNI deny | Triage phân biệt mạng, handshake, authz |
| **MTLS-42** | HTTP 403/gRPC PERMISSION_DENIED sau mTLS PASS | Dashboard phân loại đúng authorization failure |
| **MTLS-43** | Telemetry bị thiếu trên một đường traffic | Đánh dấu coverage UNKNOWN, không tuyên bố encrypted |
| **MTLS-44** | Log/trace có credentials giả | Key/token bị redacted, principal metadata có kiểm soát |
| **MTLS-45** | Load test hợp lệ ở staging theo budget | TLS overhead, CPU, p95/p99, resource limits đáp ứng SLO |
| **MTLS-46** | Sau rollout policy trong production theo canary | Positive và negative tests đúng, có rollback xác định |

### Quy tắc đánh giá

- **PASS**: có bằng chứng từ đúng endpoints và data plane rằng authentication, authorization và business outcome đáp ứng kỳ vọng.
- **FAIL**: chứng minh được một đường plaintext/bypass ngoài quyền, một caller trái quyền được cho phép, hoặc caller hợp lệ bị từ chối ngoài chính sách.
- **INCONCLUSIVE**: thiếu TLS identity telemetry, sai điểm quan sát, chưa xác định trust domain/CA, thiếu CNI coverage hoặc không có quyền thử đường liên quan.
- **NOT_APPLICABLE**: kiến trúc không có hạng mục đó (ví dụ cluster không dùng ambient hoặc không có IPv6), có ghi rõ phạm vi.

**Một phép thử âm tính thất bại không tự chứng minh mTLS đang chặn**: DNS sai hoặc service tắt cũng có thể gây timeout. Phải xác nhận **đúng loại denial và enforcement point**.

## 37. Những hiểu nhầm và sai sót phổ biến

| Nhận định sai | Vì sao sai | Cách hiểu phù hợp |
|---|---|---|
| “Mạng nội bộ nên không cần TLS” | Workload có thể bị chiếm, cloud/VPN có ranh giới phức tạp | Xác thực/mã hóa theo threat model |
| “TLS và mTLS là một” | TLS thông thường có thể chỉ xác thực server | mTLS yêu cầu xác thực hai phía |
| “HTTPS ở gateway nghĩa backend có mTLS” | TLS có thể terminate và chuyển plaintext | Kiểm tra từng hop |
| “Cert chain valid nghĩa đúng service” | Cần SAN/URI identity và trust domain đúng | Xác thực peer identity được kỳ vọng |
| “Common Name luôn là danh tính SPIFFE” | X.509-SVID dùng URI SAN | Kiểm tra đúng SAN/identity |
| “SPIFFE ID là Pod IP” | SPIFFE ID tách khỏi network address | Xác thực identity bất biến theo vai trò |
| “ServiceAccount name là bằng chứng mật mã” | Cần issuance/attestation/handshake | Kiểm tra SVID và CA |
| “JWT-SVID tự là mTLS” | Token JWT không phải TLS client certificate | Phân biệt cơ chế credential |
| “Có sidecar là tự tất cả traffic mTLS” | Injection, exclusions, host path, mesh mode ảnh hưởng | Inventory/route coverage tests |
| “STRICT cho phép chỉ service có quyền gọi” | STRICT yêu cầu mTLS, không tự làm authorization | AuthorizationPolicy/least privilege |
| “PERMISSIVE chắc chắn an toàn như STRICT” | Có thể cho plaintext trong giai đoạn chuyển đổi | Onboard caller và chuyển sang STRICT có phép |
| “Có AuthorizationPolicy nghĩa mọi đường đều được bảo vệ” | Enforcement point có thể bị bypass | Test direct PodIP, port/host paths |
| “mTLS peer hợp lệ được đọc mọi tenant” | Identity service khác identity người dùng | Object-level authorization |
| “Cùng ServiceAccount cho mọi Pod thuận tiện mà vẫn an toàn” | Mất phân biệt principal và tăng blast radius | Tách ServiceAccount/rights |
| “Mọi proxy trong mesh có cùng policy ngay khi apply YAML” | Config propagation có thể chậm/lỗi | Monitor version convergence |
| “CA mới được tin ở một node là đủ cho rollover” | Peer còn dùng trust bundle cũ | Phân phối trust trước issuance |
| “Short-lived cert giải quyết revocation ngay lập tức” | Cert bị lộ còn dùng được tới khi bị chặn/hết hạn | Isolation/incident response |
| “Có cert mới thì mọi session cũ tự bị ngắt” | TLS sessions/connection lifecycle khác renewal | Xem session lifetime và drain |
| “Control plane hỏng là data plane lập tức ngừng” | Cấu hình/kết nối cũ có thể tiếp tục | Phân biệt existing/new/rotation |
| “Control plane hỏng thì nên tự bật plaintext” | Làm mất bảo mật khi sự cố availability | Fail closed theo policy |
| “TLS passthrough vẫn cho proxy đọc mọi HTTP method” | Payload L7 có thể vẫn mã hóa trong app TLS | Xem termination và parsing |
| “NetworkPolicy không còn cần khi có mTLS” | mTLS không loại mọi nguồn có identity hoặc DoS | L3/L4 segmentation |
| “VPN bảo vệ WAN thì xác thực service không cần thiết” | VPN xác thực tunnel, không mọi workload | mTLS/service identity bổ trợ |
| “Trust domain = Kubernetes namespace” | Trust domain là phạm vi identity riêng | Phân biệt cluster, namespace, SA |
| “Hai cluster có same SA path là cùng principal” | Còn issuer/trust domain/cluster boundary | Federation có kiểm soát |
| “Gateway identity bằng user cuối” | Gateway đang gọi thay người dùng | End-user token/context riêng |
| “Mesh mTLS tự bảo vệ tới external Internet service” | External hop có TLS/trust khác | Kiểm tra egress boundary |
| “mTLS bảo vệ luôn private key trong app memory” | Endpoint bị chiếm có thể dùng key | Runtime security và key protection |
| “Một gRPC 200 chứng minh quyền API đúng” | grpc-status và resource authorization riêng | Đo đủ transport/status/business |
| “IDS không thấy HTTP là không có traffic” | TLS làm payload ẩn trước TLS termination | Proxy/app telemetry |
| “Tất cả mesh có cùng API PeerAuthentication” | CRDs, defaults, modes khác nhau | Theo tài liệu sản phẩm/version |
| “Certificate hết hạn chỉ ảnh hưởng Pod mới” | New handshakes hoặc renewals có thể lỗi nhiều nơi | Theo dõi vòng đời và connection state |
| “Chỉ test happy path là đủ” | Plaintext và unauthorized peer có thể vẫn được phép | Positive + negative tests |

## 38. Câu hỏi tự kiểm tra

1. TLS server-authenticated khác mTLS ở bước xác thực nào?
2. mTLS bảo vệ tính bí mật và toàn vẹn trên đoạn kết nối nào? Vì sao cần nêu **TLS termination points**?
3. Certificate chain validation khác việc so khớp **SAN/identity mong đợi** thế nào?
4. CertificateVerify có vai trò gì trong xác thực dựa trên chứng thư?
5. SPIFFE ID là gì? Nó khác Pod IP và Kubernetes Service DNS ra sao?
6. X.509-SVID chứa SPIFFE ID ở đâu? Vì sao không chỉ xem Common Name?
7. Trust domain khác namespace thế nào? Vì sao cùng namespace/SA path ở hai cluster chưa tự là cùng identity?
8. Workload attestation dùng làm gì trong certificate issuance?
9. Vì sao việc cho Pod tự khai báo danh tính bất kỳ trong CSR là nguy hiểm?
10. Mesh control plane và data plane có trách nhiệm khác nhau gì?
11. Sidecar architecture đặt điểm kết thúc mTLS ở đâu? Có nhất thiết app process dùng TLS trên local hop không?
12. Ambient L4 proxy và waypoint L7 khác nhau về loại thông tin/policy có thể xử lý như thế nào?
13. STRICT mTLS trong Istio nhằm bảo đảm điều gì và **không** tự bảo đảm điều gì?
14. Một client có mTLS hợp lệ nhưng không được phép gọi DeletePayment thì bị chặn ở đâu?
15. Vì sao dùng default ServiceAccount cho nhiều ứng dụng làm identity policy kém chính xác?
16. RBAC/admission có vai trò gì với quyền gắn ServiceAccount/labels và phát hành certificate?
17. Vì sao một Pod sidecar không được inject có thể trở thành security gap?
18. Bạn sẽ kiểm tra port exclusions và direct Pod IP path ra sao mà không ảnh hưởng production?
19. Certificate rotation cần theo dõi những yếu tố gì ngoài thời gian NotAfter?
20. CA rollover nên phối hợp giai đoạn trust bundle và issuance như thế nào?
21. Nếu một private key bị lộ, vì sao không thể chỉ chờ chứng thư ngắn hạn tự hết hạn?
22. Điều gì có thể xảy ra khi control plane không phản hồi nhưng các proxy đã có cấu hình cũ?
23. Ingress gateway identity khác end-user identity thế nào?
24. Khi gateway kết thúc TLS rồi gọi backend, cần xác minh những hop nào?
25. Vì sao mTLS trong mesh không tự cấp client certificate tin cậy cho external API?
26. Một HTTP/gRPC policy có hoạt động đúng với opaque TCP hoặc app-native TLS không?
27. NetworkPolicy và mTLS kết hợp ra sao để giới hạn lateral movement?
28. Vì sao proxy metrics báo authenticated peer nhưng database vẫn có thể bị truy cập trái quyền?
29. Khi mTLS handshake lỗi, làm sao phân biệt CA trust, URI SAN, expiry, routing và authorization?
30. Trong case study chuyển STRICT, nên khôi phục legacy VM theo phương án nào mà không mở plaintext toàn namespace?
31. Trong case study CA rollover, vì sao những session cũ có thể khỏe nhưng Pod mới thất bại?
32. Trong case study dùng chung ServiceAccount, cần chỉnh những chính sách nào để ngăn lateral access?
33. Các giả định trust-domain federation nào có thể làm sai một policy principal?
34. Vì sao một phép thử từ Pod không có quyền bị timeout chưa chứng minh NetworkPolicy hay mTLS DENY đúng?
35. Cần những trường telemetry nào để chứng minh **đúng client identity, đúng server identity, đúng mTLS và đúng AuthorizationPolicy**?
36. Nêu ít nhất bốn loại traffic cần test để phát hiện đường bypass quanh mesh.
37. Bạn sẽ xử lý thế nào nếu CA/control plane bị lỗi trong lúc rollout mà vẫn giữ nguyên chính sách bảo mật?
38. Hãy thiết kế ma trận test cho **checkout → inventory ALLOW**, **sandbox → inventory DENY** và **checkout → tenant B object DENY**.

## 39. Ghi nhớ trọng tâm

**mTLS giữa các workload** là cơ chế TLS xác thực **cả hai phía** và mã hóa dữ liệu trên các đoạn kết nối được triển khai đúng. Trong service mesh, danh tính thường được quản lý qua **PKI, X.509/SPIFFE/SVID, trust domain, issuance, rotation** và được **data plane proxy/agent** thực thi theo cấu hình từ **control plane**. Một certificate hợp lệ chỉ có giá trị khi **chain, thời gian, SAN/identity, trust domain và possession of private key** được xác minh phù hợp.

**Peer authentication không phải authorization.** Chế độ **STRICT** có thể từ chối client không dùng mTLS nhưng không tự giới hạn những workload có chứng thư hợp lệ. Cần kết hợp **NetworkPolicy/firewall phân đoạn L3/L4, mesh AuthorizationPolicy theo principal/service/method, application-level authorization theo user/tenant/object và RBAC/admission bảo vệ danh tính**. Chú ý các đường **sidecar không được inject, excluded ports, direct Pod IP, hostNetwork, ingress/egress gateway, VM legacy, multi-cluster, IPv6 và TLS termination tại proxy**.

Để vận hành an toàn, hãy xác định **tập workload được yêu cầu mTLS, nơi bắt đầu/kết thúc TLS từng hop, policy ở đúng data plane, certificate inventory và trust bundle**, cùng khả năng **rotation/CA rollover, resilience khi control plane lỗi và telemetry được redacted**. Nghiệm thu phải có **positive/negative tests**: caller có quyền hoạt động, caller thiếu certificate không vượt qua xác thực, caller có certificate nhưng thiếu quyền bị chặn, và quyền object/tenant vẫn được ứng dụng kiểm tra. **Không tuyên bố bảo vệ hoàn chỉnh chỉ vì cấu hình mTLS đã được bật; cần bằng chứng trên đường truyền thực tế và cả các đường có thể bypass.**
