# Xác thực giữa dịch vụ bằng danh tính dịch vụ (workload identity) hoặc mTLS

Trong microservices, một API thường gọi nhiều API nội bộ trước khi trả kết quả. Nếu hệ thống chỉ dựa vào địa chỉ IP, tên DNS, mạng nội bộ hoặc một API key dùng chung, service nhận yêu cầu khó trả lời câu hỏi: **“Đúng workload được cấp quyền có đang gọi tôi không?”**. Một container bị chiếm quyền có thể giả làm service khác, lấy secret được chia sẻ và di chuyển ngang giữa các hệ thống.

**Workload identity** cung cấp danh tính có thể xác minh cho tiến trình, container, pod hoặc service đang chạy. **Mutual TLS (mTLS)** là cơ chế TLS xác thực hai phía bằng chứng chỉ, đồng thời mã hóa lưu lượng. Hai khái niệm liên quan chặt chẽ nhưng không đồng nghĩa: workload identity trả lời **ai đang gọi**, mTLS cung cấp một cách **chứng minh danh tính trên kênh truyền**. Sau xác thực, hệ thống vẫn phải quyết định **danh tính đó được phép làm gì**.

Bài học đặt trong ngữ cảnh bảo mật giữa các microservices: từ mô hình đe dọa, lựa chọn danh tính, luồng cấp phát/chuyển vòng credential, xác minh ở điểm nhận, chính sách ủy quyền, đến vận hành và xử lý lỗi.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

- Phân biệt authentication, authorization, encryption, workload identity, service account, mTLS và token.
- Giải thích cách xác thực hai chiều trong TLS handshake và giới hạn của việc “đã bật mTLS”.
- Mô tả danh tính workload được cấp phát, chứng minh, luân phiên và thu hồi như thế nào.
- So sánh X.509 certificate, SPIFFE X.509-SVID, JWT-SVID và OAuth/OIDC workload tokens theo tình huống.
- Thiết kế service-to-service authentication và authorization theo nguyên tắc **zero trust** và **least privilege**.
- Áp dụng mô hình cho Kubernetes, service mesh, ứng dụng Java/Spring và hệ thống gọi dịch vụ bên ngoài.
- Kiểm chứng hệ thống từ log, trace, kiểm thử bảo mật và sự cố chứng chỉ/token.

## 2. Bài toán và mô hình đe dọa

Giả sử hệ thống đặt hàng gồm:

~~~text
Client
  |
  v
API Gateway
  |
  v
Order Service
  |         \
  |          \----> Inventory Service
  v
Payment Service ----> Payment Provider
  |
  v
Order Database
~~~

Giả sử API nội bộ `POST /internal/payments/charge` chỉ dành cho Order Service. Nếu Payment Service chấp nhận mọi request đến từ dải IP private hoặc chỉ kiểm tra một header `X-Service-Name: order`, đối tượng kiểm soát được container khác trong cluster có thể gửi request giả danh Order.

Những rủi ro cần xét:

1. **Giả mạo service:** một tiến trình tự tuyên bố là Order Service mà không có bằng chứng mật mã.
2. **Di chuyển ngang:** workload bị xâm nhập gọi những API nội bộ vốn không dành cho nó.
3. **Lộ credential:** API key dùng chung bị ghi vào log, image, environment, ticket hoặc bản sao cấu hình.
4. **Nghe lén hoặc sửa lưu lượng:** traffic giữa node/cluster/VPC đi qua hạ tầng không được tin tưởng tuyệt đối.
5. **Nhầm quyền giữa người dùng và service:** service có credential hợp lệ nhưng dùng nó để thực hiện hành động thay người dùng ngoài phạm vi cho phép.
6. **Chiếm quyền tại nơi cấp danh tính:** kẻ tấn công có thể yêu cầu credential cho workload khác nếu khâu workload attestation yếu.
7. **Trust mở rộng quá mức:** một CA được tin cậy cấp certificate cho nhiều service, nhưng hệ thống nhận lại mặc nhiên chấp nhận mọi certificate từ CA đó.

Một thiết kế đúng phải xét cả **bảo vệ trên đường truyền**, **chứng minh danh tính** và **kiểm soát hành động ở service nhận**. Tường lửa, network policy và phân đoạn mạng vẫn hữu ích để giảm bề mặt tấn công, nhưng không thay thế xác thực danh tính workload.

## 3. Phân biệt các khái niệm cốt lõi

| Khái niệm | Câu hỏi giải quyết | Ví dụ |
|---|---|---|
| **Workload** | Thực thể đang thực thi là gì? | Pod `orders-api`, process Java `payment-service`. |
| **Workload identity** | Thực thể đang chạy được nhận diện bằng tên đã được xác minh nào? | `spiffe://prod.example/ns/orders/sa/orders-api`. |
| **Authentication (AuthN)** | Bên gọi có chứng minh được danh tính đó không? | Xác minh client certificate hoặc chữ ký JWT. |
| **Authorization (AuthZ)** | Danh tính đã xác thực được thao tác gì với tài nguyên nào? | Chỉ `orders-api` được gọi `POST /internal/charge`. |
| **TLS** | Kênh có được bảo vệ và server có được xác thực không? | Client xác minh certificate của server. |
| **mTLS** | Cả client và server có được xác thực trong TLS handshake không? | Payment kiểm tra cert của Order, Order kiểm tra cert của Payment. |
| **Service account** | Danh tính vận hành do nền tảng quản lý là gì? | Kubernetes `ServiceAccount` gắn với một Deployment. |
| **Credential** | Bằng chứng nào giúp workload chứng minh danh tính? | Private key + X.509 cert, signed JWT. |
| **Trust anchor** | Gốc tin cậy để xác minh bằng chứng là gì? | CA được chấp nhận, issuer/JWKS đáng tin cậy. |
| **Principal** | Danh tính đã được hệ thống xác thực và dùng để đánh giá policy là gì? | URI SAN trong chứng chỉ hoặc subject đã xác minh trong token. |

**Không nên dùng tên DNS làm bằng chứng danh tính client.** DNS hỗ trợ định tuyến; danh tính phải được gắn với bằng chứng mật mã và quy trình cấp phát đáng tin cậy. Tương tự, “request đi qua mạng private” chỉ là thông tin đường đi, không phải xác thực.

Một bên có thể mang hai danh tính khác nhau: **workload identity** của Order Service và **end-user identity** của người đặt hàng. Không được trộn lẫn chúng. Khi Order Service đại diện người dùng gọi Payment, cần kiểm tra cả quyền service gọi Payment lẫn quyền người dùng thực hiện nghiệp vụ tương ứng, tùy contract.

## 4. mTLS hoạt động như thế nào?

Trong TLS thông thường, client xác minh server certificate để giảm nguy cơ kết nối đến server giả. Trong **mTLS**, server còn yêu cầu client certificate và xác minh nó. Ở TLS 1.3, chi tiết các message handshake khác TLS 1.2, nhưng trách nhiệm xác minh hai chiều vẫn giống nhau.

~~~text
Order Service (client)                        Payment Service (server)
        |                                                |
        | -- ClientHello -------------------------------> |
        | <--------------- TLS handshake / server cert -- |
        | -- Xác minh chain, SAN, hiệu lực của server --> |
        | <--- Yêu cầu chứng chỉ client (mTLS) ---------- |
        | -- Client cert + chứng minh có private key ---> |
        |                                                |
        |     Hai bên xác minh trust chain, identity,     |
        |     thuật toán và điều kiện chấp nhận           |
        | <======== Kênh mã hóa đã thiết lập ============> |
        | -- POST /internal/charge ---------------------> |
        | <---- Policy kiểm tra principal + action ------ |
        | <---------------- HTTP response --------------- |
~~~

Trong thực tế handshake có thể được TLS library xử lý hoàn toàn; ứng dụng chỉ nhận connection sau khi thành công. Việc có TLS session **không đồng nghĩa** ứng dụng đã cấp quyền cho mọi API.

Có ba kiểm tra khác nhau thường bị gộp nhầm:

1. **Chứng chỉ hợp lệ:** chain được ký bởi trust anchor được cho phép, chưa hết hạn và đáp ứng ràng buộc kỹ thuật phù hợp.
2. **Danh tính đúng:** certificate thuộc đúng service dự kiến, ví dụ URI SAN có SPIFFE ID phù hợp, chứ không chỉ “một cert bất kỳ được CA này ký”.
3. **Quyền đúng:** service đó được phép gọi route và operation cụ thể trong hoàn cảnh hiện tại.

Một trust store chấp nhận CA của toàn cluster mà không áp policy nguồn gọi có thể biến mọi workload có cert hợp lệ thành “người dùng được tin cậy” của API.

## 5. Thiết kế danh tính service

Danh tính có tính ổn định theo **vai trò/khối lượng công việc** nên thường hữu ích hơn danh tính dựa vào IP hoặc tên Pod ngẫu nhiên. Ví dụ:

~~~text
spiffe://prod.example/ns/orders/sa/orders-api
spiffe://prod.example/ns/payment/sa/payment-api
spiffe://prod.example/ns/inventory/sa/inventory-api
~~~

Với SPIFFE, cấu trúc tổng quát là `spiffe://<trust-domain>/<workload-path>`; phần path do tổ chức và hệ thống cấp danh tính quản lý theo quy tắc nhất quán. URI ví dụ ở trên minh họa ánh xạ namespace và service account, không tự động được Kubernetes cấp chỉ vì đặt tên service account như vậy.

Thiết kế danh tính phải trả lời:

- **Cái gì là một workload?** Mỗi deployment, mỗi service account, mỗi môi trường hay mỗi bản triển khai?
- **Trust domain nào cấp danh tính?** Tách production khỏi development để tránh credential của môi trường thử nghiệm được dùng tại production.
- **Ai được nhận identity nào?** Phải có workload attestation dựa trên thông tin nền tảng tin cậy, không cho ứng dụng tự khai nhận tên tùy ý.
- **Identity được thay đổi khi nào?** Đổi tên workload, chuyển namespace, đổi service account, tách team hoặc chuyển cluster.
- **Policy tham chiếu danh tính cụ thể nào?** Dùng principal có thể xác minh; tránh wildcard quá rộng.
- **Có cần federation giữa trust domain không?** Cross-cluster, multi-cloud và external partner cần thêm cơ chế xác lập niềm tin liên miền.

Không nên trao cùng một identity cho mọi service chỉ để triển khai nhanh. Nếu Order, Payment và Reporting đều dùng `default` ServiceAccount với một quyền chung, việc audit và hạn chế di chuyển ngang trở nên khó khăn.

## 6. Các hình thức cung cấp workload identity

### 6.1. X.509 certificate gắn với workload

Workload có một private key và certificate chứa identity, được ký bởi CA đáng tin cậy. Khi kết nối mTLS, private key được dùng để chứng minh bên kết nối thực sự sở hữu credential; phía nhận xác minh chain, SAN và policy.

**Ưu điểm:** xác thực kênh hai chiều, có thể dùng cho HTTP/gRPC và protocol dựa trên TLS; private key không nhất thiết rời khỏi môi trường runtime. **Hạn chế:** cần quản lý cấp cert, hạn sử dụng, phân phối trust bundle, cấu hình TLS và rotation.

Certificate chỉ hữu ích khi identity trong SAN và chain được ánh xạ đúng sang principal. Tên Common Name (CN) không nên được xem là cơ chế thay thế cho SAN trong thiết kế hiện đại.

### 6.2. SPIFFE X.509-SVID

SPIFFE định nghĩa định dạng danh tính workload. X.509-SVID là một certificate có SPIFFE ID dưới dạng URI SAN, đi kèm private key và trust bundle. Một hệ thống như SPIRE có thể cấp các SVID ngắn hạn dựa trên xác minh node và workload.

~~~text
Node / Agent attestation
         |
         v
Workload identity issuer (ví dụ SPIRE Server)
         |
         v
Workload Agent hoặc local Workload API
         |
         v
Workload nhận X.509-SVID + private key + trust bundle
         |
         v
Kết nối mTLS và xác minh SPIFFE ID
~~~

Điểm cần nhớ: **SPIFFE là đặc tả danh tính; SPIRE là một triển khai phổ biến**. Không nhất thiết dùng SPIRE để sử dụng tư duy identity cho workload. Nhiều service mesh tích hợp cơ chế cấp certificate theo cách riêng hoặc dựa trên các chuẩn tương thích.

Một certificate có SPIFFE ID hợp lệ vẫn cần đối tác kiểm tra **đúng identity được phép**, không chỉ đúng trust domain.

### 6.3. JWT-SVID hoặc service-to-service JWT

Một workload có thể dùng signed JWT thể hiện danh tính để gọi API. Bên nhận xác minh chữ ký và claims, rồi ánh xạ thành principal.

Các thông tin quan trọng thường gồm:

- `iss`: issuer mà hệ thống nhận chủ động tin tưởng.
- `sub`: danh tính workload, định danh ổn định theo hợp đồng.
- `aud`: đối tượng nhận token, phải khớp API được gọi.
- `exp` và `nbf`: thời điểm hết hạn và bắt đầu hiệu lực.
- `iat`: thời điểm cấp, hữu ích cho kiểm tra tuổi token.
- `kid` trong header: hỗ trợ chọn khóa xác minh từ một issuer đáng tin cậy; không biến một URL do client tự đưa thành nguồn khóa đáng tin.

**JWT-SVID** là một loại token tuân theo hồ sơ SPIFFE, không đồng nhất với mọi JWT do nền tảng tùy ý phát hành. Token ký đúng nhưng sai issuer hoặc sai audience phải bị từ chối. JWT thường là **bearer credential**: ai sở hữu token trong hạn dùng có thể sử dụng nó nếu không áp thêm cơ chế proof-of-possession hoặc binding phù hợp. Vì vậy, cần bảo vệ token khỏi bị ghi log và tái sử dụng ngoài ý muốn.

### 6.4. Kubernetes ServiceAccount token

Kubernetes có thể cung cấp token ràng buộc với ServiceAccount thông qua TokenRequest/projected volume. Token kiểu mới thường có thời hạn, audience và metadata ràng buộc khác với secret token lâu dài theo cách cũ. Một API bên ngoài Kubernetes chỉ nên chấp nhận token khi đã thiết lập tin cậy với issuer, xác minh claims và hiểu rõ vòng đời token.

Ví dụ Pod gắn với một service account riêng và dùng projected token có audience hẹp:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders
---
apiVersion: v1
kind: Pod
metadata:
  name: orders-example
  namespace: orders
spec:
  serviceAccountName: orders-api
  automountServiceAccountToken: false
  containers:
    - name: app
      image: example.invalid/orders:1.0
      volumeMounts:
        - name: workload-token
          mountPath: /var/run/workload
          readOnly: true
  volumes:
    - name: workload-token
      projected:
        sources:
          - serviceAccountToken:
              path: token
              audience: payments.internal
              expirationSeconds: 3600
~~~

Đây là cấu hình minh họa cho token được chiếu vào volume. `audience: payments.internal` **chỉ phù hợp** nếu verifier của Payment được cấu hình chấp nhận chính xác audience đó. Khi runtime xoay vòng token, ứng dụng phải đọc token mới theo cơ chế file phù hợp, không cache vĩnh viễn giá trị lúc startup. Deployment thực tế cần namespace, image và security policy riêng.

**ServiceAccount token không tự tạo mTLS.** Nó có thể được dùng làm bằng chứng để đổi lấy credential ngắn hạn khác qua token exchange/workload identity federation, hoặc để gọi API có chính sách xác thực JWT tương ứng.

### 6.5. Workload identity federation với cloud IAM

Workload chạy trên Kubernetes hoặc một nền tảng khác có thể dùng credential do nền tảng phát hành để đổi lấy access token ngắn hạn của cloud provider, tránh lưu cloud access key dài hạn. Mô hình khái quát:

~~~text
Pod/VM workload
  -> token hoặc assertion từ issuer tin cậy
  -> Security Token Service / IAM federation
  -> token ngắn hạn có phạm vi, audience và role phù hợp
  -> API cloud
~~~

Quy tắc quan trọng là ràng buộc chặt **issuer + subject + audience + điều kiện role**. Không coi tất cả token cùng issuer là có cùng quyền. Tài khoản cloud có thể được gán cho workload cụ thể; identity của Pod chưa chắc chính là principal trong cloud, vì còn bước trao đổi và ánh xạ.

## 7. Workload identity và mTLS bổ sung cho nhau thế nào?

| Phương án | Xác minh bên gọi | Bảo mật kênh | Điểm cần lưu ý |
|---|---|---|---|
| Chỉ IP allowlist | Phụ thuộc địa chỉ mạng | Không có nếu không bật TLS | IP không chứng minh workload, dễ sai trong cluster động. |
| TLS một chiều + shared API key | Server qua TLS; client qua key dùng chung | Có | Key bị lộ có thể mạo danh nhiều caller; khó phân quyền và rotation. |
| TLS một chiều + JWT workload | Client qua token, server qua cert | Có | Phải kiểm tra issuer, signature, audience, hạn dùng, policy; bearer token có thể bị đánh cắp. |
| mTLS với identity trong client cert | Cả hai qua TLS certificate | Có | Cần validate SAN/principal, cấp quyền, rotation và trust bundle. |
| mTLS + JWT/user token | Cả kênh và danh tính token theo hợp đồng | Có | Hai bằng chứng phục vụ lớp mục tiêu khác nhau; tránh giả định chúng luôn cùng principal. |
| Service mesh tự quản mTLS | Proxy hai phía xác thực workload | Có giữa các proxy | Ứng dụng cần tin tưởng đúng proxy và identity context; phải bảo vệ khoảng giữa proxy và app. |

Không có lựa chọn “mTLS hoặc workload identity” theo nghĩa loại trừ lẫn nhau. mTLS thường **sử dụng workload identity được biểu diễn bằng certificate**. Ngược lại, workload identity cũng có thể được chứng minh bằng token trên kênh TLS một chiều.

Chọn cách triển khai theo yêu cầu hệ thống: giao thức, việc kiểm soát client/server, độ nhạy dữ liệu, số service, hạ tầng cấp credential và khả năng vận hành.

## 8. Vòng đời của credential: từ cấp phát đến thu hồi

Một hệ thống xác thực phải vận hành được cả khi workload được tạo mới, đổi Pod, đổi node, lỗi mạng hoặc bị xâm nhập.

### 8.1. Bootstrap: workload ban đầu chứng minh mình là ai?

Đây là điểm bắt đầu của chuỗi tin cậy. Một workload chưa có certificate không thể tự tuyên bố “tôi là Payment Service” rồi xin CA cấp cert cho tên đó.

Cơ chế cấp phát thường dựa trên **workload attestation**:

1. Nền tảng tạo workload với metadata được quản trị, ví dụ cluster, namespace, service account, node.
2. Agent/issuer xác minh bằng chứng được tạo từ nền tảng, không chỉ một chuỗi text do ứng dụng gửi.
3. Policy ánh xạ bằng chứng hợp lệ sang một workload identity xác định.
4. Issuer cấp certificate/token thời hạn ngắn và phân phối tới workload qua kênh được kiểm soát.
5. Workload dùng credential để xác thực với peer; peer kiểm tra trust bundle và identity.

Rủi ro nằm ở việc **cấp nhầm identity ngay từ đầu**. Nếu bất kỳ Pod nào cũng có thể gắn service account đặc quyền hoặc giả mạo chứng cứ node, TLS handshake có đúng chuẩn vẫn không bảo đảm người gọi là workload được mong đợi.

### 8.2. Lưu giữ private key và token

- Hạn chế secret tồn tại trên image, Git, CI log, crash dump hoặc đường dẫn world-readable.
- Cấp credential riêng theo workload; không dùng một private key chung cho toàn cluster.
- Dùng volume/secret manager/agent có quyền truy cập tối thiểu, ưu tiên credential được xoay vòng tự động.
- Với private key, bảo vệ file permission và tiến trình có thể đọc; với HSM/KMS/TPM, cân nhắc cơ chế ký mà khóa không xuất ra nếu nền tảng hỗ trợ.
- Không xuất token, Authorization header, private key hay full certificate chain nhạy cảm vào application log.
- Kiểm soát quyền debug/exec vào Pod và quyền đọc mounted credential; một container bị xâm nhập thường có thể sử dụng credential mà nó đang được cấp.

### 8.3. Rotation và hết hạn

Credential ngắn hạn giảm thời gian khai thác nếu bị lộ, nhưng tăng yêu cầu độ tin cậy của issuer và rotation. Cần bảo đảm:

- Certificate/token mới xuất hiện **trước** khi phiên bản cũ hết hạn.
- TLS client/server và pool kết nối dùng credential mới theo đúng cách thư viện hỗ trợ. Không mặc định cập nhật file sẽ tự làm mọi connection nhận cert mới.
- Trust bundle có khoảng chồng lấn khi thay CA, sau đó loại bỏ gốc cũ có kiểm soát.
- Monitoring có metric/cảnh báo cho `certificate_expiry_seconds`, token refresh error, issuer availability và handshake failure.
- Kịch bản issuer tạm thời không hoạt động có chính sách rõ: dùng credential còn hiệu lực trong khoảng cho phép, **không bỏ qua xác minh**.

### 8.4. Thu hồi

Với cert ngắn hạn, thời gian sống ngắn là biện pháp giới hạn phơi nhiễm nhưng **không phải thu hồi tức thì**. Có thể cần thu hồi trust, điều chỉnh authorization policy, cô lập workload bị xâm nhập hoặc ngừng issuer cấp credential mới. Các cơ chế CRL/OCSP có thể hỗ trợ ở một số PKI, song phải biết thực tế client/proxy có kiểm tra hay không. Với JWT, token đã phát hành thường vẫn dùng được tới khi hết hạn nếu verifier chỉ kiểm tra chữ ký; yêu cầu vô hiệu hóa ngay cần chiến lược riêng như revocation, denylist, short TTL hoặc kiểm tra trạng thái bổ sung.

## 9. Luồng xác thực một lời gọi Order → Payment

Thiết kế ví dụ:

~~~text
[1] Order Pod/sidecar có identity:
    spiffe://prod.example/ns/orders/sa/orders-api

[2] Payment Pod/sidecar có identity:
    spiffe://prod.example/ns/payment/sa/payment-api

[3] Order gọi payments.internal qua TLS/mTLS.

[4] Order xác minh server certificate:
    chain + validity + tên/identity Payment mong đợi.

[5] Payment xác minh client certificate:
    chain + validity + identity Order.

[6] Payment chuyển identity đã xác minh thành principal.

[7] Policy:
    principal = orders-api
    method    = POST
    path      = /internal/charge
    action    = allow

[8] Service thực hiện kiểm tra nghiệp vụ: order hợp lệ,
    quyền của user/tenant, idempotency, hạn mức...
~~~

**Authentication không cấp quyền tự động cho hành động nghiệp vụ.** Một Order Service được phép tạo yêu cầu thu tiền không có nghĩa nó được phép truy cập báo cáo tài chính, đọc toàn bộ thông tin thẻ hay thực hiện hoàn tiền.

Ở bước [4], tùy giao thức, xác minh server có thể dựa trên DNS SAN của service hoặc SPIFFE ID với trust bundle phù hợp. Cần định nghĩa chính xác expected identity; chấp nhận mọi cert từ một CA thường không đủ.

Ở bước [7], policy phải dùng principal do mTLS/JWT verifier tạo, **không đọc trực tiếp tên do caller tự gửi trong header tùy ý**.

## 10. Đặt authorization policy sau khi đã xác thực

Một policy có thể viết theo tư duy “chỉ cho phép quan hệ giao tiếp được khai báo”:

| Caller identity | Resource/operation | Quyết định |
|---|---|---|
| `spiffe://prod.example/ns/orders/sa/orders-api` | `POST /internal/charge` | Cho phép khi nghiệp vụ hợp lệ |
| `spiffe://prod.example/ns/orders/sa/orders-api` | `GET /internal/payments/export` | Từ chối |
| `spiffe://prod.example/ns/reporting/sa/reporting-api` | `GET /internal/payments/summary` | Cho phép nếu thuộc vai trò báo cáo |
| `spiffe://prod.example/ns/inventory/sa/inventory-api` | `POST /internal/charge` | Từ chối |
| Không xác thực | Mọi API nội bộ bảo vệ | Từ chối |

Cần tách ba lớp chính sách:

1. **Transport authentication:** kết nối được chấp nhận nếu chứng minh danh tính hợp lệ.
2. **Service-to-service authorization:** danh tính caller nào được gọi API/phương thức nào.
3. **Business authorization:** user, tenant, order, tài khoản, số tiền và trạng thái nghiệp vụ có cho phép hành động không.

Ví dụ Order Service có quyền gọi Payment Service, nhưng một user chỉ có quyền trên đơn hàng thuộc tenant của họ. Nếu chỉ dựa vào quyền workload, kẻ tấn công lợi dụng endpoint của Order có thể yêu cầu Order làm “người đại diện có đặc quyền”, tạo lỗi **confused deputy**.

Chính sách tốt mặc định từ chối, được version-control và được kiểm thử như logic nghiệp vụ. Tránh whitelist tên service theo regex rộng hoặc suy ra quyền chỉ vì service nằm cùng namespace.

## 11. Triển khai mTLS qua service mesh

Service mesh có thể cung cấp certificate, TLS handshake, identity propagation, policy và telemetry ở data plane. Ứng dụng tập trung vào nghiệp vụ, proxy chịu trách nhiệm nhiều thao tác bảo mật transport.

~~~text
Order App
    |
    v
Order Proxy -- mTLS [X.509 workload cert] --> Payment Proxy
                                                   |
                                                   v
                                             Payment App
~~~

Ví dụ minh họa với Istio: ràng buộc traffic vào Payment namespace dùng STRICT mTLS và cho phép đúng workload gọi API charge. Phiên bản API/resource cần đối chiếu với mesh đang vận hành trước khi áp dụng.

~~~yaml
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: payment-strict-mtls
  namespace: payment
spec:
  mtls:
    mode: STRICT
---
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: payment-allow-orders-charge
  namespace: payment
spec:
  selector:
    matchLabels:
      app: payment-api
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - cluster.local/ns/orders/sa/orders-api
      to:
        - operation:
            methods: ["POST"]
            paths: ["/internal/charge"]
~~~

**Hiểu giới hạn của ví dụ:**

- `STRICT` yêu cầu traffic mesh phù hợp mTLS tại phạm vi policy. Chuyển từ plaintext sang STRICT mà chưa di chuyển mọi caller có thể làm gián đoạn dịch vụ.
- Principal ví dụ theo dạng SPIFFE-like identity dùng trong Istio; giá trị trust domain và service account phải đúng với cluster thực tế.
- Policy `ALLOW` giới hạn theo selector, principal và route đã khai báo; workload/route khác trong selector không tự có quyền nếu không được match. Chính sách khác đồng thời tồn tại có thể ảnh hưởng kết quả và phải được xét cùng.
- Những policy method/path yêu cầu proxy nhìn thấy HTTP L7; với TCP thô hoặc traffic không phân tích HTTP, phải chọn khả năng và policy phù hợp.
- Proxy có thể kết thúc TLS trước khi giao tiếp qua loopback với app; cần bảo vệ ranh giới app ↔ proxy, không giả định toàn bộ byte từ mạng tới logic app đều được mã hóa cùng một session TLS.
- Ingress, egress, job, health probe và third-party client có thể có đường đi khác; phải đưa chúng vào kế hoạch migration.

Khi mesh báo `source.principal`, ứng dụng chỉ nên tin giá trị nếu nó đến từ proxy đã được bảo vệ và không thể bị client tự gán, ví dụ qua kết nối nội bộ an toàn và header đã được proxy loại bỏ/ghi đè có kiểm soát. Nếu ứng dụng có đường truy cập bypass proxy, cơ chế tin tưởng header có thể bị phá.

## 12. Ứng dụng tự xử lý mTLS không qua mesh

Khi không dùng service mesh, chính HTTP/gRPC server và client cần quản lý TLS.

Ví dụ Spring Boot Servlet server bật client-certificate authentication (chỉ minh họa cơ chế, certificate và truststore phải được cấp ngoài ứng dụng):

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: "file:/run/secrets/payment-server.p12"
    key-store-type: "PKCS12"
    key-store-password: "change-by-secret-management"
    trust-store: "file:/run/secrets/payment-trust.p12"
    trust-store-type: "PKCS12"
    trust-store-password: "change-by-secret-management"
    client-auth: need
~~~

**Không đặt mật khẩu thật trong file cấu hình hoặc repository.** Các giá trị ở đây chỉ là placeholder minh họa; triển khai thật cần secret injection/secret manager và cơ chế xoay vòng phù hợp. `client-auth: need` yêu cầu certificate phía client ở TLS layer, nhưng không thay thế policy kiểm tra **danh tính trong SAN** và **quyền gọi API**.

Trong một ứng dụng Servlet, nơi đã được TLS connector xác minh certificate client, có thể có certificate chain trong request attribute `jakarta.servlet.request.X509Certificate`. Không nên tự viết một “certificate verifier” dựa trên các header tên cert do HTTP client gửi; dùng trust manager và certificate path validation của nền tảng. Sau khi TLS thành công, đọc SAN đã được xác minh để ánh xạ sang principal và áp authorization policy.

Ví dụ phác thảo cách tách vai trò của các component:

~~~java
// Khung logic, không phải trình xác minh X.509 tự viết.
void authorizeCharge(VerifiedPeer peer, HttpRequestView request) {
    // VerifiedPeer chỉ được tạo bởi TLS/identity middleware đã
    // xác minh chain, hạn hiệu lực và URI SAN theo trust policy.
    if (!peer.spiffeId().equals(
            "spiffe://prod.example/ns/orders/sa/orders-api")) {
        throw new AccessDeniedException("caller is not orders-api");
    }

    if (!request.method().equals("POST")
            || !request.path().equals("/internal/charge")) {
        throw new AccessDeniedException("operation not allowed");
    }

    // Sau AuthZ của service vẫn phải kiểm tra user/tenant/order.
}
~~~

Ở phía client, cần **cả key material và trust material**:

- KeyManager chứng minh client identity bằng private key + client certificate.
- TrustManager xác minh server chain.
- Kiểm tra expected server name/identity theo contract và không tắt hostname verification.
- Cấu hình connection pool và TLS session resumption sao cho rotation không khiến credential cũ tồn tại ngoài chính sách.
- Hạn chế thư viện hoặc code custom TLS; không dùng “trust all certificates” khi gặp lỗi handshake.

Nếu triển khai mTLS tại API gateway, cần xác định rõ phía backend có tin danh tính đã xác minh của client/gateway hay vẫn yêu cầu mTLS thêm một hop. **TLS kết thúc ở gateway không tự chứng minh danh tính của caller ở đoạn kết nối sau gateway**.

## 13. Xác thực bằng JWT workload trên TLS một chiều

Đôi khi service-to-service API chỉ hỗ trợ OAuth/JWT và TLS một chiều. Cách này vẫn có thể dùng workload identity nếu token được cấp và xác minh đúng.

~~~text
Order workload
  -> nhận/đổi token có aud=payment-api
  -> HTTPS Authorization: Bearer <token>
  -> Payment:
       kiểm tra TLS server identity ở client
       xác minh issuer + chữ ký token + thời gian + audience
       ánh xạ subject thành service principal
       kiểm tra quyền gọi endpoint
~~~

Bên nhận phải xác minh ít nhất:

1. Chữ ký hợp lệ từ khóa được cấu hình cho issuer đáng tin cậy.
2. `iss` chính xác; không chấp nhận issuer ngoài danh sách cho phép.
3. `aud` khớp tài nguyên nhận, ngăn token dùng cho Inventory bị chuyển sang Payment.
4. `exp`, `nbf`, clock skew hợp lý và thuật toán ký được phép.
5. `sub`/claim identity đáng tin theo issuer và contract, không suy từ token chưa xác minh.
6. Scope/role/permission phù hợp với method và resource sau khi đã xác thực.

Ví dụ các claim minh họa:

~~~json
{
  "iss": "https://identity.prod.example",
  "sub": "spiffe://prod.example/ns/orders/sa/orders-api",
  "aud": "payment-api",
  "iat": 1794441600,
  "nbf": 1794441600,
  "exp": 1794441900
}
~~~

Thời gian epoch trong ví dụ chỉ là dữ liệu minh họa; client phải dùng token issuer cấp thực sự. Cần tránh “decode JWT rồi tin claims” khi chưa xác minh chữ ký; thư viện chỉ parse payload không đồng nghĩa đã authenticate.

Trên Spring Security Resource Server, cấu hình issuer hỗ trợ xác thực JWT theo issuer đã tin; nhưng **audience và service-specific authorization** thường phải được cấu hình/kiểm tra tường minh theo policy API. Không coi việc JWT có chữ ký hợp lệ là đủ quyền gọi mọi endpoint.

Với API có rủi ro cao, cân nhắc token ngắn hạn, token exchange với audience hẹp và các cơ chế chống tái sử dụng phù hợp. mTLS và JWT có thể được dùng cùng nhau: mTLS chứng minh identity của peer trong kênh, JWT thể hiện delegated identity hoặc scope theo contract. Khi phối hợp, cần chỉ rõ mối quan hệ được phép giữa peer identity và token subject.

## 14. Identity của service khác identity của người dùng

Một request có thể có hai tầng:

~~~text
User A
  -- access token của User A --> API Gateway
  -- request context --> Order Service (identity Order)
  -- mTLS/JWT workload --> Payment Service
~~~

Bốn câu hỏi độc lập cần được trả lời:

1. Gateway đã xác thực user A bằng cách nào?
2. Order có được phép gọi Payment không?
3. Payment có nhận đúng và có thể tin user context hoặc delegated token không?
4. User A có quyền trả tiền cho order, tenant và phương thức thanh toán này không?

Đừng mặc định forward raw user access token tới mọi service; token có thể có audience sai và phạm vi quá rộng. Có thể dùng token exchange hoặc delegated token chỉ dành cho Payment, với phạm vi, audience và lifetime phù hợp. Nếu truyền user claims trong internal headers, chỉ tin headers được set bởi một gateway/proxy đáng tin, đã xóa giá trị do client tự gửi và bảo vệ hop tiếp theo.

Sai lầm thường gặp là nghĩ: “Payment đã xác thực Order bằng mTLS, vậy mọi payment do Order gửi đều hợp lệ”. Workload authentication chỉ xác định caller; nó không thay thế kiểm soát quyền của người dùng và các invariant nghiệp vụ.

## 15. Thiết kế trust domain và giao tiếp đa cluster

Trong một cluster đơn, nhiều hệ thống chọn một trust domain cho workloads. Khi có nhiều cluster, nhiều vùng hoặc nhiều cloud, cần phân biệt:

- **Cùng trust domain:** có thể chia sẻ cơ sở tin cậy/issuer đã được quản trị; vẫn phải xác minh principal cụ thể.
- **Trust domain riêng biệt:** cần federation hoặc cơ chế tin cậy liên miền rõ ràng, kèm policy ánh xạ danh tính được phép.
- **Production và staging:** nên giảm khả năng credential staging được tin như production.
- **Partner/external service:** thường cần boundary riêng, gateway, mutual auth hoặc token federation với điều kiện cụ thể; không tự đưa trust root của partner vào toàn bộ mesh.

Ví dụ:

~~~text
prod.example               partner.example
Order Service ------------> Partner Gateway
     |                            |
  prod CA                  partner trust root
     +---- federation / gateway trust policy ----+
~~~

Federation không có nghĩa mọi principal của bên kia có quyền. Hệ thống cần quy tắc “chỉ identity X từ trust domain Y được gọi operation Z”. Nếu chấp nhận trust bundle mới quá rộng, vùng bị xâm nhập ở một domain có thể trở thành đường truy cập trái phép vào domain còn lại.

## 16. Quan hệ giữa mTLS, NetworkPolicy, RBAC và Zero Trust

**mTLS không thay thế mọi lớp phòng vệ:**

- **NetworkPolicy/firewall:** giảm phạm vi kết nối khả dĩ; một workload không cần gọi database thì nên bị chặn cả đường mạng.
- **Workload identity + AuthN:** xác minh danh tính thật của peer.
- **Service authorization:** cho phép đúng cặp service/route/method, default deny.
- **Business authorization:** kiểm tra user/tenant/object/action cụ thể.
- **Secrets/IAM:** giới hạn quyền đọc token, cert, data và cloud resource.
- **Audit/telemetry:** phát hiện giả mạo, policy deny, certificate anomalies và hành vi bất thường.

“Zero trust” không có nghĩa mọi request luôn bị từ chối; nghĩa là **không cấp quyền chỉ vì ở trong một mạng được gọi là nội bộ**. Danh tính, trạng thái tin cậy và quyền phải được chứng minh ở đúng boundary.

Ví dụ, Kubernetes RBAC quyết định Pod/ServiceAccount nào được thao tác với Kubernetes API. Nó **không mặc định** là policy cho endpoint `POST /internal/charge` của Payment Service. Muốn enforce quyền đó cần AuthorizationPolicy của mesh, gateway policy hoặc authorization tại ứng dụng.

## 17. Cơ chế phát hiện và kiểm tra identity thực sự

Đừng chỉ kiểm tra “có certificate file” hoặc “mesh dashboard hiện mTLS enabled”. Cần biết **peer identity đã được xác minh** ở nơi ra quyết định.

Thứ tự logic cho mTLS:

~~~text
TLS library / proxy:
  1. Verify certificate chain + validity + acceptable CA
  2. Verify key usage / certificate purpose as appropriate
  3. Verify expected server identity / peer identity
  4. Extract verified principal

Policy engine:
  5. Match principal against caller allowlist
  6. Match route, method, scope and resource context
  7. Allow or reject

Application:
  8. Check user, tenant and business invariants
  9. Process request or return safe error
~~~

Các kiểm tra ở tầng TLS thường xử lý bằng thư viện/mesh chuẩn; ứng dụng không nên tự viết lại chain validation. Nếu proxy xác thực client certificate rồi chuyển danh tính qua header, điểm nhận phải bảo đảm client ngoài không thể truy cập trực tiếp để tự đặt header. Cách đáng tin cậy hơn là lấy principal từ API/context do middleware xác thực quản lý, có ranh giới trust rõ ràng.

Với HTTP/2/gRPC, connection có thể được tái sử dụng nhiều request. Principal của kênh mTLS vẫn cần được gắn đúng với request; token ứng dụng có thể thay đổi trên từng request nên không thể suy user identity chỉ từ connection.

## 18. Observability: theo dõi danh tính và lỗi xác thực

Đo cả bảo mật và vận hành:

| Tín hiệu | Câu hỏi trả lời |
|---|---|
| TLS handshake failures | Có cert hết hạn, sai CA, mismatch SAN hoặc protocol không tương thích không? |
| Peer identity / principal | Service nào đang thực sự gọi service nào? |
| Authorization denied | API bị từ chối theo policy nào, trên operation nào? |
| Token validation error | Sai issuer, audience, signature, exp/nbf hay JWKS refresh? |
| Cert rotation / issuance | Credential được xoay vòng đúng hạn không? |
| Certificate expiry margin | Bao lâu nữa cert hoặc trust bundle quan trọng hết hạn? |
| mTLS coverage | Bao nhiêu traffic giữa các workload bảo vệ bằng mTLS? |
| Sidecar/issuer availability | Việc cấp danh tính hoặc xác thực có trở thành điểm lỗi tập trung không? |

Trong distributed tracing, có thể ghi **service principal đã xác minh** tại boundary cần audit, nhưng cần giới hạn dữ liệu và cardinality. Không đưa access token, private key, session ticket, nội dung certificate nhạy cảm hoặc Authorization header vào log/traces. Có thể tham chiếu service, namespace, policy ID, route và kết quả allow/deny.

Một mTLS handshake thất bại có thể kết thúc **trước khi HTTP request vào ứng dụng**, nên cần thu thập log/metric từ proxy, ingress và TLS library; chỉ nhìn ứng dụng sẽ không đủ.

Phân biệt các lỗi:

- **Authentication failure:** không chứng minh được danh tính (invalid cert/token), thường bị chặn ở TLS/proxy hoặc phản hồi 401 ở HTTP auth layer.
- **Authorization failure:** identity hợp lệ nhưng thiếu quyền, thường là 403 ở HTTP layer.
- **Business failure:** identity và quyền gọi API hợp lệ nhưng đơn hàng/trạng thái nghiệp vụ không cho phép; ánh xạ lỗi theo contract.
- **Infrastructure failure:** issuer/JWKS/agent không khả dụng, lỗi rotation hoặc handshake, cần theo dõi nguyên nhân riêng thay vì gom toàn bộ vào “403”.

## 19. Chiến lược triển khai dần trên hệ thống đang chạy

Đổi toàn bộ traffic thành STRICT mTLS trong một bước có thể làm hỏng health probes, legacy service, batch job hoặc client ngoài mesh. Một lộ trình thực tế:

**Bước 1 — Kiểm kê lời gọi:** lập bảng caller → callee, protocol, environment, route, method, nguồn credential và nơi TLS bị terminate.

**Bước 2 — Chọn identity model:** quyết định identity gắn với service account/workload nào, trust domain, CA/issuer, lifecycle và boundary.

**Bước 3 — Thiết lập cấp credential:** triển khai workload attestation, cert/token issuance, refresh, rotation và giám sát hết hạn.

**Bước 4 — Bật xác thực trong vùng thử nghiệm:** kiểm tra client/server identity, handshake, chain, SAN và latency/CPU overhead; không tắt verification để vượt lỗi.

**Bước 5 — Ghi nhận quan hệ thực:** đo principal nào gọi API nào; chuyển thành allowlist cụ thể, review với owner của mỗi service.

**Bước 6 — Áp authorization theo vùng:** ưu tiên endpoint nhạy cảm, default deny có chủ đích, kiểm thử rollout và có cơ chế rollback policy được kiểm soát.

**Bước 7 — Tắt plaintext/credential cũ:** sau khi mọi caller hợp lệ đã di chuyển và được quan sát, khóa đường bypass; loại bỏ shared key không còn cần thiết.

**Bước 8 — Vận hành lâu dài:** diễn tập rotation, trust-root change, issuer outage, compromised workload, cert expiration và failover.

Trong giai đoạn chuyển đổi có thể dùng chế độ permissive để đo coverage trước khi áp STRICT, nhưng phải có thời điểm kết thúc rõ ràng. Không xem chế độ cho phép cả plaintext là trạng thái bảo mật cuối.

## 20. Những sai lầm thường gặp

1. **Tin private network là đủ:** nội bộ vẫn có workload bị xâm nhập. Cần identity xác minh được.
2. **Cho mọi service cùng một credential:** rò rỉ một key mở quyền nhiều service. Dùng credential và principal riêng.
3. **Chỉ kiểm tra CA hợp lệ:** mọi service được CA cấp cert có thể gọi nhau. Cần identity matching và authorization.
4. **Tin header X-Service-Name từ client:** header dễ giả mạo. Chỉ tin principal do verifier/proxy đáng tin cung cấp.
5. **Tắt hostname/SAN validation vì khó cấu hình:** tạo đường MITM dù TLS có mã hóa. Sửa identity và trust configuration.
6. **Dùng token sai audience:** token cấp cho một API bị dùng ở API khác. Verifier phải kiểm tra `aud`.
7. **Dùng token/cert dài hạn không rotation:** tăng thiệt hại khi lộ. Dùng credential ngắn hạn, rotation chủ động.
8. **Cho rằng Kubernetes RBAC bảo vệ mọi API service:** RBAC Kubernetes không thay cho application/mesh AuthZ.
9. **Bật mesh mTLS nhưng để đường bypass:** app vẫn có thể bị gọi qua port khác hoặc tin header giả. Khóa đường bypass.
10. **Đưa user token xuống tất cả service:** sai audience và tăng phạm vi phơi nhiễm. Dùng delegated token đúng mục tiêu.
11. **Coi timeout handshake là lỗi nghiệp vụ:** cần quan sát lỗi TLS, certificate, issuer riêng để xử lý đúng.
12. **Khi issuer lỗi thì fail open:** bỏ xác thực đúng lúc hệ thống mất tín hiệu tin cậy. Thiết kế fallback chỉ dùng credential còn hiệu lực và policy rõ ràng.
13. **Tin mTLS giải quyết mọi quyền:** kết nối mTLS hợp lệ vẫn có thể truy cập sai endpoint nếu AuthZ quá rộng.
14. **Không kiểm chứng rotation:** hệ thống chạy tốt tới ngày cert hết hạn, sau đó đồng loạt gián đoạn. Thử nghiệm rotation và cảnh báo sớm.

## 21. Kiểm thử xác thực và ủy quyền

Các tình huống kiểm thử cần bao phủ cả đường thành công và những điều kiện bị từ chối.

| Tình huống | Kết quả mong đợi |
|---|---|
| Order có cert hợp lệ và được phép gọi Payment | Kết nối thành công, route đúng được cho phép. |
| Không có client certificate trong mTLS bắt buộc | TLS handshake/connection bị từ chối. |
| Client cert tự ký, CA không nằm trong trust bundle | Từ chối kết nối. |
| Cert được CA tin cậy ký nhưng principal là Inventory | AuthN có thể thành công; AuthZ Payment charge phải từ chối. |
| Cert hết hạn/chưa đến thời điểm hiệu lực | TLS validation thất bại. |
| Server cert có identity không phải Payment mong đợi | Client phải từ chối server, không bypass validation. |
| JWT có chữ ký hợp lệ nhưng `aud` sai | Từ chối token. |
| JWT hết hạn hoặc issuer không được tin cậy | Từ chối token. |
| Caller tự gửi `X-Verified-Service` nhưng không có chứng cứ | Không được cấp quyền. |
| User có token hợp lệ nhưng không sở hữu order | Từ chối ở business authorization. |
| Rotating cert giữa lúc có traffic | Kết nối mới xác thực bằng credential mới, hạn chế gián đoạn theo thiết kế. |
| CA/issuer tạm unavailable | Không phát credential không được kiểm chứng; sự cố được quan sát và xử lý theo chính sách. |
| Client ngoài mesh cố gọi port app trực tiếp | Bị chặn bằng topology/network enforcement hoặc app authentication. |
| Cross-cluster principal ngoài allowlist | Dù liên miền được trust, operation vẫn bị từ chối. |

Kiểm thử end-to-end phải dùng workload chạy trong môi trường giống production vì phần lớn lỗi xảy ra ở sidecar, certificate lifecycle, routing và network boundary. Unit test policy hữu ích, nhưng không chứng minh được traffic thực sự được mTLS bảo vệ.

## 22. Ví dụ tình huống: service mới muốn gọi Payment

Nhóm Reporting cần truy vấn trạng thái giao dịch từ Payment để tạo báo cáo. Payment đang cho Order gọi `POST /internal/charge` qua mTLS. Nhóm Reporting đề nghị “cho chúng tôi dùng chung certificate của Order để triển khai nhanh”.

**Cách xử lý:**

1. Không cấp lại credential của Order cho Reporting. Xác lập identity riêng, ví dụ `spiffe://prod.example/ns/reporting/sa/reporting-api`.
2. Làm rõ API cần thiết: `GET /internal/payments/summary` hay `GET /internal/payments/{id}`, bộ lọc tenant và quyền đọc dữ liệu nhạy cảm.
3. Đảm bảo Reporting được issuer cấp cert riêng dựa trên service account của chính nó; bật rotation.
4. Thêm policy chỉ cho identity Reporting được gọi các endpoint đọc được duyệt. Không cấp quyền charge/refund.
5. Nếu request chứa ngữ cảnh người dùng hoặc tenant, áp business authorization tương ứng; không coi workload identity là toàn quyền xem dữ liệu.
6. Viết thử nghiệm: Reporting đọc được summary hợp lệ; Reporting gọi charge bị từ chối; client giả danh Reporting không có cert hợp lệ bị chặn.

**Kết quả kiến trúc mong muốn:** credential bị lộ từ Reporting không trực tiếp mở quyền tạo thanh toán như Order; Payment có audit cho từng principal và operation.

## 23. Bài tập thực hành

Một cluster có bốn workload:

~~~text
orders/orders-api
payment/payment-api
inventory/inventory-api
analytics/reporting-api
~~~

Payment cần quy tắc:

- Chỉ `orders/orders-api` gọi được `POST /internal/charge`.
- Chỉ `analytics/reporting-api` gọi được `GET /internal/summary`.
- `inventory/inventory-api` không được gọi bất kỳ endpoint Payment nào.
- Mọi kết nối giữa service nội bộ phải có mTLS.
- Không được chấp nhận request chỉ vì đi từ địa chỉ private.

**Câu hỏi:**

1. Đặt workload identity rõ ràng cho cả bốn service trong một trust domain production.
2. Nếu tất cả đều có cert hợp lệ từ cùng CA, Payment có thể chỉ kiểm tra CA rồi cho mọi request đi qua không?
3. Request từ Reporting có mTLS hợp lệ nhưng gọi `POST /internal/charge` phải được xử lý ở bước nào?
4. Một JWT có `sub=orders-api` nhưng `aud=inventory-api` có hợp lệ để gọi Payment không?
5. Khi Payment thay CA hoặc certificate hết hạn, cần những kiểm tra vận hành nào để tránh downtime?

**Gợi ý đối chiếu:**

- Mỗi service cần principal riêng được issuer gắn với workload attestation, ví dụ `spiffe://prod.example/ns/orders/sa/orders-api` và `spiffe://prod.example/ns/analytics/sa/reporting-api`.
- Xác thực chứng chỉ hợp lệ mới chứng minh peer thuộc một identity tin cậy, chưa cấp quyền gọi operation.
- Reporting gọi charge phải bị từ chối ở service authorization kể cả mTLS handshake thành công.
- Audience của token không khớp Payment nên verifier phải từ chối.
- Cần thử nghiệm trust bundle overlap, rotation client/server, certificate expiry alert và xác thực kết nối mới trong quá trình thay đổi.

## 24. Nguyên tắc mang vào thiết kế thực tế

Khi thảo luận security architecture, hãy yêu cầu sơ đồ có đủ năm dữ kiện:

~~~text
Caller identity  -> Credential được cấp bằng cách nào?
Trust anchor     -> Ai được quyền cấp và xác minh identity?
Transport        -> Kết nối được xác thực/mã hóa ở hop nào?
Authorization    -> Principal nào được gọi API/action nào?
Lifecycle        -> Credential được xoay vòng/thu hồi/quan sát ra sao?
~~~

Nếu thiếu một trong các dữ kiện, thiết kế rất dễ biến thành “bật TLS cho xong” hoặc “service nào trong cluster cũng đáng tin”. Khi đầy đủ, nhóm phát triển có thể vận hành quyền truy cập service-to-service theo nguyên tắc có thể kiểm chứng, thu hẹp quyền khi có sự cố và bảo vệ cả dữ liệu trên đường truyền lẫn hành động nghiệp vụ.

**Thông điệp chính:** Xác thực giữa microservices phải dựa trên danh tính workload có bằng chứng mật mã, không dựa vào sự hiện diện trong mạng nội bộ. mTLS là một cơ chế mạnh để xác thực hai phía và bảo vệ kênh; token workload là lựa chọn phù hợp cho nhiều API/identity federation. Dù chọn cơ chế nào, vẫn cần **xác minh đúng principal, áp authorization tối thiểu, bảo vệ credential và vận hành rotation/cancellation of trust một cách có kiểm soát**.
