# Quản lý bí mật và cấp quyền đọc theo dịch vụ

Trong kiến trúc microservices, mỗi dịch vụ có những thông tin nhạy cảm riêng: mật khẩu kết nối cơ sở dữ liệu, khóa gọi nhà cung cấp thanh toán, token truy cập dịch vụ bên ngoài, khóa ký JWT hoặc private key của chứng thư. Nếu tất cả dịch vụ cùng đọc một kho bí mật bằng một tài khoản có quyền rộng, việc một dịch vụ bị xâm nhập có thể làm lộ thông tin của nhiều dịch vụ khác.

**Quản lý bí mật và cấp quyền đọc theo dịch vụ** là thiết kế vòng đời của secret và chính sách truy cập sao cho mỗi workload chỉ lấy được đúng bí mật cần cho chức năng của nó, đúng môi trường, đúng thời điểm và thông qua danh tính đã xác thực. Quyền phải được thực thi ở kho bí mật và tầng hạ tầng, không chỉ dựa vào quy ước đặt tên trong mã nguồn.

Ví dụ: Payment Worker có thể đọc API key của cổng thanh toán và thông tin truy cập database chuyên dụng của Payment; Notification Worker chỉ được đọc token gửi email. Việc hai service cùng chạy trong một Kubernetes cluster không có nghĩa chúng được đọc secret của nhau.

## 1. Kết quả cần đạt

Sau bài này, người học có thể:

- Phân biệt secret với cấu hình thông thường và chỉ ra ranh giới bảo vệ của từng loại.
- Thiết kế **service identity** và quyền đọc theo nguyên tắc **least privilege** và **default deny**.
- Mô tả luồng workload lấy bí mật từ secret manager bằng danh tính ngắn hạn, không cần mật khẩu dùng chung để “mở khóa” kho secret.
- Chọn cách đưa secret vào ứng dụng ở runtime, hiểu rủi ro của biến môi trường, file mount, API và cache.
- Thiết kế cấp phát, kiểm kê, xoay vòng, thu hồi và xử lý sự cố secret bị lộ.
- Kiểm tra quyền được cấp, hoạt động audit và hành vi của dịch vụ khi secret hết hạn hoặc không thể lấy được.

## 2. Secret khác cấu hình thông thường ở đâu?

Không phải mọi giá trị cấu hình đều là bí mật. Cần phân loại theo hệ quả nếu người không có quyền đọc được giá trị.

| Loại | Ví dụ | Cách quản lý mong muốn |
|---|---|---|
| Cấu hình công khai hoặc không nhạy cảm | Tên service, timeout, tên topic, cổng HTTP | Version control, config repository hoặc cấu hình triển khai |
| Cấu hình nội bộ cần hạn chế | Internal hostname, feature flag quản trị, định tuyến riêng | Giới hạn khả năng đọc theo môi trường và vai trò |
| Secret dạng thông tin xác thực | Database password, API key, OAuth client secret, token dịch vụ | Secret manager, quyền tối thiểu, audit, rotation |
| Secret dạng vật liệu mã hóa | Private key, khóa đối xứng, khóa ký | KMS/HSM hoặc kho secret có kiểm soát, tránh xuất khóa nếu hỗ trợ ký/giải mã tại chỗ |
| Chứng thư và vật liệu công khai | Public certificate, public key | Có thể phân phối công khai trong nhiều trường hợp; tính toàn vẹn và nguồn cấp vẫn cần được xác minh |

**Nguyên tắc quan trọng:** Một chuỗi được mã hóa Base64 vẫn chỉ là dữ liệu đã được biểu diễn lại, không phải dữ liệu được mã hóa bảo mật. Kubernetes Secret lưu trường data theo Base64 trong manifest/API và cần kiểm soát RBAC, quyền tạo pod, mã hóa dữ liệu lưu trữ cũng như đường truyền. Không coi việc đổi từ file plaintext sang Base64 là đã giải quyết bài toán bảo mật.

Đừng lưu secret trong repository, commit history, Docker image, Java resource đóng gói trong JAR, template triển khai, ticket, log hoặc ảnh chụp màn hình. Việc xóa secret ở commit mới không bảo đảm nó biến mất khỏi lịch sử Git; secret đã bị commit cần được xem xét thu hồi và thay giá trị.

## 3. Rủi ro khi mọi dịch vụ dùng chung một bộ bí mật

Giả sử ba dịch vụ Order, Payment và Notification dùng chung tài khoản “microservices-admin” để đọc toàn bộ secret production:

~~~text
Order Service ---------|
Payment Service -------|----> shared-admin credential ----> Secret Store
Notification Service --|             quyền đọc: prod/*
~~~

Thiết kế này có những rủi ro:

1. **Mở rộng phạm vi sự cố:** lộ credential trong Notification có thể làm lộ cả khóa thanh toán của Payment.
2. **Không quy trách nhiệm được:** audit chỉ ghi nhận “microservices-admin”, khó xác định service thực sự đã đọc.
3. **Thu hồi gây gián đoạn rộng:** đổi một credential dùng chung có thể làm cả ba dịch vụ ngừng hoạt động.
4. **Vi phạm ranh giới môi trường:** một quy tắc rộng như prod/* có thể bị dùng sai cho staging hoặc môi trường khác.
5. **Khó vận hành rotation:** nhiều service phải triển khai và cập nhật cùng lúc, dễ phát sinh trạng thái không đồng bộ.
6. **Tăng khả năng di chuyển ngang:** một service có thể lấy bí mật của service khác để kết nối thay mặt service đó.

Thiết kế phù hợp hơn:

~~~text
Order Service        -- identity/order-prod --> chỉ secret của Order
Payment Service      -- identity/payment-prod -> chỉ secret của Payment
Notification Service -- identity/notify-prod --> chỉ secret của Notification
                                                  |
                                                  v
                                     Secret Manager + Policy Engine
                                                  |
                                                  v
                                          Audit / Rotation
~~~

Ranh giới danh tính và quyền phải tồn tại ngay cả khi các workload dùng cùng node, cluster hoặc network. Tên endpoint hay tên service trong request không tự chứng minh danh tính của workload.

## 4. Service identity: Ai đang xin đọc bí mật?

**Danh tính dịch vụ** là chứng cứ có thể xác minh về workload đang chạy. Tùy nền tảng, nó có thể dựa trên:

- Kubernetes ServiceAccount kết hợp projected service account token có issuer, audience và thời hạn cụ thể.
- Workload identity của nhà cung cấp cloud, trong đó pod/VM/workload đổi chứng cứ runtime lấy token truy cập có thời hạn.
- Identity do service mesh hoặc hệ thống định danh máy cấp, chẳng hạn chứng thư mTLS với danh tính workload.
- Danh tính cấp cho job CI/CD, batch job hoặc rotation controller riêng, không dùng chung với danh tính runtime của service.

Ví dụ, các workload của cùng một ứng dụng có thể cần danh tính khác nhau:

| Workload | Danh tính logic | Lý do cần tách |
|---|---|---|
| order-api | prod/order-api | Chỉ đọc credential phục vụ tạo/tra cứu đơn |
| payment-worker | prod/payment-worker | Đọc khóa cổng thanh toán |
| notification-worker | prod/notification-worker | Đọc token của nhà cung cấp email |
| payment-rotator | prod/payment-rotator | Có quyền tạo phiên bản khóa mới, kiểm tra và chuyển phiên bản |
| payment-deployer | ci/payment-deployer | Triển khai ứng dụng; không tự động có quyền đọc giá trị khóa thanh toán |

Tên ở bảng là **nhãn minh họa**, không phải định dạng bắt buộc của một sản phẩm secret manager.

Khi nhận yêu cầu đọc, kho secret cần kiểm tra nhiều thuộc tính tin cậy thay vì chỉ một tên chuỗi tự khai:

- **Ai cấp danh tính?** Token có issuer hợp lệ, chữ ký hợp lệ, audience đúng và chưa hết hạn không?
- **Workload nào?** ServiceAccount, namespace, cluster, project, workload type và môi trường có khớp policy không?
- **Muốn làm gì?** Chỉ đọc giá trị hay có quyền tạo, sửa, xóa, xem metadata, liệt kê?
- **Với tài nguyên nào?** Đường dẫn hoặc ID của đúng secret và đúng phiên bản được cho phép?
- **Trong hoàn cảnh nào?** Điều kiện thời gian, nguồn chạy, tag môi trường hoặc chính sách bổ sung có phù hợp không?

Không nên dùng API key tĩnh có phạm vi toàn kho làm credential bootstrap nếu nền tảng hỗ trợ liên kết danh tính workload. Token ngắn hạn và cơ chế xác thực dựa trên môi trường chạy làm giảm tác động của một token bị lấy cắp, nhưng vẫn cần chính sách cấp quyền chặt và khả năng thu hồi.

## 5. Least privilege, default deny và phân quyền theo secret

**Least privilege:** mỗi service chỉ có quyền thực sự cần thiết để hoàn thành nghiệp vụ.

**Default deny:** không có policy cho phép rõ ràng thì yêu cầu đọc bị từ chối. Service mới không tự nhận quyền chỉ vì được deploy vào cùng namespace.

**Separation of duties:** service runtime thường chỉ đọc; việc tạo phiên bản, thay secret hoặc xóa secret do một vai trò vận hành riêng thực hiện.

Ví dụ ma trận phân quyền cho hệ thống thương mại điện tử:

| Principal | prod/order/db-credential | prod/payment/gateway-key | prod/notify/email-token | Quyền quản trị secret |
|---|---|---|---|---|
| order-api | Read | Deny | Deny | Deny |
| payment-worker | Deny | Read | Deny | Deny |
| notification-worker | Deny | Deny | Read | Deny |
| payment-rotator | Deny | Write/rotate theo phạm vi Payment | Deny | Quyền giới hạn trên secret của Payment |
| security-auditor | Metadata/audit tùy chính sách | Metadata/audit tùy chính sách | Metadata/audit tùy chính sách | Không mặc định được xem payload |

Nếu Order và Payment cùng truy cập một cơ sở dữ liệu, nên ưu tiên tài khoản và credential khác nhau với quyền SQL phù hợp, thay vì chia sẻ mật khẩu quản trị database. Khi buộc phải chia sẻ một secret, cần ghi rõ danh sách service phụ thuộc, chủ sở hữu, kế hoạch rotation và nguyên nhân kiến trúc. Việc chia sẻ không nên là mặc định.

Chú ý rằng quyền **list** có thể tiết lộ tên và cấu trúc secret; quyền **get/read** cho phép xem nội dung; quyền **write/update** có thể làm thay đổi hành vi ứng dụng; quyền **delete** có thể gây mất khả năng truy cập. Không gộp tất cả thành “access”.

Một ví dụ chính sách **mang tính khái niệm, không phải cú pháp của sản phẩm cụ thể**:

~~~yaml
principal:
  environment: production
  service: payment-worker
  workload_identity: verified-runtime-identity

allow:
  - operation: read_secret_value
    resources:
      - prod/payment/gateway-api-key
      - prod/payment/processor-db-credential

deny_by_default: true
conditions:
  token_audience: secret-manager
  token_not_expired: true

audit:
  record_principal: true
  record_resource: true
  record_decision: true
  record_secret_value: false
~~~

Policy này cần được **thực thi tại hệ thống quản lý secret**. Một đoạn code chỉ kiểm tra chuỗi đầu vào trước khi gọi secret manager bằng tài khoản admin không tạo ra ranh giới quyền đáng tin cậy: service vẫn có credential có thể đọc dữ liệu ngoài phạm vi.

## 6. Tổ chức namespace, đường dẫn và ownership

Một quy tắc đặt tên nhất quán giúp viết policy chính xác và làm rõ trách nhiệm:

~~~text
<environment>/<domain>/<service>/<purpose>

dev/payment/payment-worker/gateway-token
staging/payment/payment-worker/gateway-token
prod/payment/payment-worker/gateway-token
prod/order/order-api/database-credential
prod/notify/notification-worker/email-token
~~~

Đường dẫn ở trên chỉ là ví dụ logic. Sản phẩm thực tế có thể dùng resource name, project, folder, key vault, secret version hoặc ARN/URI theo chuẩn riêng.

Với mỗi secret, nên có metadata quản trị độc lập với giá trị bí mật:

| Metadata | Ví dụ | Mục đích |
|---|---|---|
| Owner | Payment Platform Team | Biết ai chịu trách nhiệm vòng đời |
| Environment | prod | Chặn đọc nhầm môi trường |
| Consumer identities | payment-worker | Quyết định danh tính được phép đọc |
| Purpose | Gateway authentication | Tránh tái sử dụng bí mật sai mục đích |
| Rotation policy | Theo cơ chế nhà cung cấp hỗ trợ | Biết cách và khi nào thay |
| Version / state | active, previous, revoked | Chuyển phiên bản an toàn |
| Expiration | Nếu credential có thời hạn | Cảnh báo và xử lý trước khi hết hạn |
| Incident contact | Nhóm trực vận hành | Thu hồi kịp thời khi nghi ngờ lộ |

Không đưa giá trị secret vào metadata, label hoặc annotation dễ được nhiều người đọc.

Cần tránh quy tắc wildcard rộng kiểu “prod/*” cho service runtime. Một policy chính xác trên một hoặc vài secret cụ thể dễ kiểm tra hơn và giảm thiểu thay đổi ngoài ý muốn khi hệ thống thêm dịch vụ mới.

## 7. Luồng truy cập secret từ service tới secret manager

Một thiết kế thông dụng:

~~~text
(1) Workload khởi động trên nền tảng tin cậy
             |
             v
(2) Nhận chứng cứ workload identity có hạn dùng
             |
             v
(3) Trao đổi chứng cứ với hệ thống xác thực
             |
             v
(4) Nhận token ngắn hạn, quyền gắn với service
             |
             v
(5) Gửi yêu cầu đọc secret được khai báo
             |
             v
(6) Secret Manager xác thực và áp dụng policy
             |
       +-----+-----+
       |           |
       v           v
    ALLOW         DENY
    trả giá trị   không trả giá trị
       |           |
       +-----+-----+
             v
(7) Ghi audit metadata (không ghi payload)
             |
             v
(8) Service sử dụng secret trong phạm vi cần thiết
~~~

Các mốc quan trọng:

1. **Không tự khai danh tính:** API client không được tự gửi “service=payment” rồi được tin ngay. Danh tính phải được xác minh bằng token/chứng thư và ràng buộc nền tảng.
2. **Tách quyền lấy token và quyền đọc secret:** việc có token hợp lệ không đồng nghĩa được đọc mọi tài nguyên; secret manager vẫn kiểm tra policy tại mỗi yêu cầu.
3. **TLS cho đường truyền:** kết nối đến secret manager phải được bảo vệ; kiểm tra chứng thư server và giới hạn endpoint tin cậy.
4. **Không ghi nội dung secret:** chỉ log mã lỗi, tài nguyên được yêu cầu theo mức cho phép, danh tính và mã định danh truy vết.
5. **Giới hạn thời gian sống:** token và credential được cấp theo thời gian ngắn khi phù hợp; có cơ chế gia hạn và thu hồi.
6. **Lỗi quyền phải là lỗi thật:** nếu service nhận 403/permission denied, không tự chuyển sang tài khoản admin hoặc bản secret sao chép trong file cấu hình.

## 8. Chọn cách cung cấp bí mật cho ứng dụng

Cùng một secret manager có thể phân phối bí mật qua nhiều hình thức. Mỗi lựa chọn tạo ra ranh giới và chi phí vận hành khác nhau.

| Hình thức | Ưu điểm | Hạn chế / điều kiện cần chú ý |
|---|---|---|
| Ứng dụng gọi Secret Manager API/SDK | Xác thực theo workload; truy vết hoạt động đọc; có thể hỗ trợ version và refresh | Phải xử lý cache, timeout, lỗi tạm thời và số lượng API call |
| Secret được mount dưới dạng file chỉ đọc | Ứng dụng đọc từ đường dẫn ổn định; dễ tích hợp với thư viện dùng certificate/keystore | Quyền file, cập nhật nội dung, snapshot trong container và cơ chế refresh phải được thiết kế |
| Truyền qua biến môi trường | Đơn giản cho cấu hình lúc startup | Giá trị có thể bị lộ qua debug, crash dump, công cụ có quyền xem process/runtime; thay đổi thường đòi hỏi restart |
| Agent/sidecar đồng bộ secret | Giảm logic truy cập trong ứng dụng; có thể tự làm mới file | Sidecar/agent cũng cần identity và policy; thêm thành phần vận hành, cần xử lý đồng bộ và lỗi |
| Cấp credential động theo phiên | Có thể đặt TTL ngắn và quyền database tách biệt | Cần hệ thống hỗ trợ tạo/thu hồi phiên và ứng dụng xử lý gia hạn |

**Không tồn tại một cơ chế “tự động an toàn” chỉ nhờ chọn API, mount hay env.** Cần xét ai có thể truy cập process, pod, host, deployment manifest, log, telemetry và secret store; đồng thời bảo đảm runtime thực sự dùng danh tính đúng.

Với một ứng dụng Spring Boot, cấu hình không nhạy cảm như timeout, endpoint logical name và feature flag có thể đi qua cấu hình thông thường. Secret nên lấy bằng một adapter chuyên trách, ví dụ interface:

~~~java
public interface SecretResolver {
    SecretValue read(String logicalSecretName);
}
~~~

Ứng dụng gọi bằng **tên logic đã cấu hình cố định** như “payment-gateway-api-token”; adapter gắn danh tính runtime và ánh xạ tới đúng tài nguyên của môi trường hiện tại. Kiểu SecretValue ở đây là lớp minh họa; triển khai thực tế phụ thuộc SDK và cách giữ/xóa dữ liệu nhạy cảm trong bộ nhớ.

Tránh cho caller tùy ý truyền đường dẫn secret từ request của người dùng. Nếu một endpoint nhận đường dẫn bất kỳ rồi dùng quyền service để đọc, ứng dụng có thể trở thành cầu nối làm lộ dữ liệu (confused deputy), ngay cả khi secret manager đã hạn chế service ở một phạm vi nào đó.

## 9. Kubernetes: ServiceAccount, Secret và ranh giới quyền

Trong Kubernetes, cần phân biệt ba lớp:

1. **Danh tính workload:** ServiceAccount được pod sử dụng; có thể liên kết tới secret manager bên ngoài bằng cơ chế workload identity phù hợp.
2. **Secret object của Kubernetes:** đối tượng chứa dữ liệu để pod dùng theo cấu hình mount/env; nó có cơ chế RBAC và bảo vệ dữ liệu riêng.
3. **Quyền gọi Kubernetes API:** Role/ClusterRole và RoleBinding/ClusterRoleBinding quyết định ai được thao tác với Secret object qua API.

Đây là ba khái niệm liên quan nhưng không đồng nhất. Ví dụ, một pod được cấu hình mount Secret không nhất thiết cần service account có quyền gọi Kubernetes API để get Secret. Kubelet thực hiện phần lấy dữ liệu cho pod; trao thêm quyền API get/list Secret cho ứng dụng có thể mở rộng bề mặt tấn công không cần thiết.

Manifest minh họa **chỉ tập trung vào cách gắn ServiceAccount và mount một secret cụ thể**:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-worker
  namespace: payment-prod
spec:
  replicas: 2
  selector:
    matchLabels:
      app: payment-worker
  template:
    metadata:
      labels:
        app: payment-worker
    spec:
      serviceAccountName: payment-worker-sa
      containers:
        - name: payment-worker
          image: example.invalid/payment-worker:1.0
          volumeMounts:
            - name: payment-credentials
              mountPath: /run/secrets/payment
              readOnly: true
      volumes:
        - name: payment-credentials
          secret:
            secretName: payment-worker-credentials
~~~

Ví dụ này giả định namespace, ServiceAccount và Secret object đã tồn tại. Đường dẫn image là minh họa, không phải image có thể pull để chạy thật. **Không đặt giá trị secret trong manifest Deployment.**

Một số lưu ý khi dùng Kubernetes Secret:

- Dùng namespace và chính sách cấp quyền riêng cho workload và môi trường. Namespace là một ranh giới quản trị hữu ích, nhưng không đủ nếu người dùng có quyền tạo/sửa pod để mount secret trong namespace đó.
- Áp dụng encryption at rest cho secret trong datastore của control plane và RBAC tối thiểu cho người dùng, controller và service account.
- Không mặc định cấp get/list/watch Secrets qua Kubernetes API cho mọi service account.
- Kiểm soát người có thể xem pod spec, exec vào container, đọc file mount và truy cập node; quyền đọc gián tiếp vẫn có thể tiết lộ secret.
- Khi cập nhật Secret được mount, ứng dụng có thể cần cơ chế theo dõi file và nạp lại client. Secret đi qua environment variable thường không tự cập nhật trong process đã chạy.
- Nếu dùng Secrets Store CSI Driver hoặc integration tương đương, xác thực cơ chế đồng bộ, phân quyền identity và tần suất cập nhật theo tài liệu của hệ thống đang triển khai.

**Câu hỏi kiến trúc cần trả lời:** bí mật được lưu gốc trong Kubernetes, trong kho secret chuyên dụng, hay được đồng bộ từ nơi khác? Cần có một nguồn quản lý vòng đời rõ ràng để tránh bản sao lệch phiên bản.

## 10. Quyền đọc nên gắn với service, môi trường và thao tác

Một policy dễ sai nếu chỉ dựa vào tên service và bỏ qua bối cảnh chạy. Ví dụ “payment-worker được đọc payment-key” chưa nói rõ payment-worker của **dev** có thể đọc key **prod** hay không.

Nên ràng buộc ít nhất các chiều sau khi có thể:

- **Service:** danh tính logic của workload; có cơ chế chứng thực thay vì tin vào header tự gửi.
- **Environment:** dev/staging/prod phải có quyền và tài nguyên tách biệt.
- **Deployment boundary:** namespace, cluster, cloud account/project hoặc trust domain.
- **Operation:** đọc giá trị, đọc metadata, liệt kê, tạo phiên bản, chuyển phiên bản, xóa.
- **Resource:** ID của secret cụ thể hoặc prefix nhỏ có chủ đích, tránh wildcard quá rộng.
- **Time/lifetime:** token và credential chỉ còn hiệu lực trong thời gian cần thiết.

Một ma trận kiểm thử quyền minh họa:

| Yêu cầu | Kết quả mong đợi | Vì sao |
|---|---|---|
| payment-worker/prod đọc prod/payment/gateway-api-key | Allow | Đúng identity, môi trường và tài nguyên |
| notification-worker/prod đọc prod/payment/gateway-api-key | Deny | Không có quyền sang service khác |
| payment-worker/staging đọc prod/payment/gateway-api-key | Deny | Sai môi trường |
| payment-worker/prod xóa prod/payment/gateway-api-key | Deny | Runtime chỉ cần đọc |
| payment-worker/prod list toàn bộ prod/* | Deny | Không cần khám phá toàn bộ kho |
| payment-rotator/prod thêm version của secret Payment | Allow theo phạm vi hẹp | Nhiệm vụ rotation riêng |
| Token sai audience hoặc hết hạn đọc bất kỳ secret | Deny | Danh tính không đạt điều kiện xác thực |

Đừng chỉ kiểm tra đường đi thành công. Những ca **bị từ chối** cho thấy ranh giới quyền có thực sự đang được thực thi hay không.

## 11. Quản lý vòng đời: tạo, đọc, xoay vòng và thu hồi

Một secret có vòng đời, không phải giá trị cố định được tạo một lần.

### 11.1. Tạo mới và cấp phát

Xác định chủ sở hữu, mục đích, môi trường, danh tính tiêu thụ, thời hạn, nguồn cấp và quyền thao tác. Secret nên được tạo trong kho phù hợp bởi quy trình có quyền riêng, sau đó service được cấp quyền đọc. Tránh gửi giá trị qua chat hoặc chép vào ticket để “truyền tay”.

### 11.2. Sử dụng và quan sát

Service xác thực bằng workload identity rồi đọc đúng secret. Hệ thống ghi nhận request metadata và quyết định allow/deny; ứng dụng sử dụng giá trị trong thời gian cần thiết. Tránh log payload hoặc đưa secret vào trace attribute, metric label, exception message.

### 11.3. Rotation không gây gián đoạn

Một mẫu quy trình cho secret có hỗ trợ hai credential/phiên bản song song:

1. Tạo phiên bản mới, giữ phiên bản cũ còn hiệu lực trong giai đoạn chuyển tiếp có kiểm soát.
2. Kiểm tra phiên bản mới bằng môi trường hoặc canary phù hợp.
3. Cho service nạp phiên bản mới, cập nhật connection pool/client nếu cần.
4. Theo dõi tỷ lệ xác thực thành công, số kết nối lỗi và audit việc đọc phiên bản cũ.
5. Sau khi tất cả consumer đã chuyển và cửa sổ an toàn kết thúc, thu hồi phiên bản cũ.
6. Xác minh không còn consumer phụ thuộc phiên bản cũ; cập nhật metadata và lịch rotation.

Không phải backend nào cũng hỗ trợ hai phiên bản cùng hợp lệ. Với hệ thống chỉ cho một password active, rotation cần chiến lược riêng: ví dụ dùng hai tài khoản luân phiên, credential động, hoặc khoảng dừng đã lên kế hoạch. Đừng mặc định luôn có thể thay giá trị mà không cần phối hợp với ứng dụng.

### 11.4. Thu hồi và xóa

Khi service bị ngừng hoặc credential có nguy cơ bị lộ, phải thu hồi quyền tại nguồn, vô hiệu hóa token/secret ở nơi phát hành, chuyển ứng dụng sang credential mới và kiểm tra các bản sao còn tồn tại. Chỉ xóa một entry trong secret manager chưa chắc làm credential hết hiệu lực với hệ thống đích, ví dụ một API key bên nhà cung cấp vẫn có thể dùng cho tới khi bị revoke tại nhà cung cấp.

### 11.5. Rà soát định kỳ

Đối chiếu danh sách secret đang tồn tại với danh sách workload còn chạy, owner và quyền đang cấp. Xóa quyền của service đã bỏ; xác minh service mới không thừa hưởng policy rộng. Tự động hóa việc phát hiện secret không có owner, sắp hết hạn hoặc không còn được đọc trong thời gian dài.

## 12. Chi tiết khó: cache, TTL và đồng bộ phiên bản

Đọc secret trên mỗi request làm tăng độ trễ và tạo phụ thuộc vận hành mạnh vào secret manager. Vì vậy nhiều hệ thống cache secret tại process hoặc thông qua agent. Cache cần được thiết kế rõ:

- **Cache scope:** chỉ trong process/service được phép dùng; không đặt secret vào cache dùng chung để mọi service đọc.
- **TTL:** thời gian sống phù hợp với khả năng rotation và giới hạn sử dụng credential.
- **Refresh:** có cơ chế làm mới chủ động hoặc khi nhận tín hiệu version thay đổi, tránh tất cả instance refresh đồng thời.
- **Failure policy:** khi secret manager tạm thời không khả dụng, chỉ dùng bản cache còn hiệu lực và được policy cho phép; không kéo dài vô hạn credential đã bị thu hồi.
- **Atomic replacement:** khi nạp secret mới, client hoặc connection pool phải chuyển trạng thái an toàn; không để một transaction dùng lẫn key/version cũ và mới mà không kiểm soát.
- **Rollback:** xác định khi nào có thể quay lại credential trước đó; nếu credential cũ đã bị revoke thì rollback binary phải vẫn dùng được credential mới.

Với token ngắn hạn, lưu ý phân biệt **hạn của token dùng để đọc secret** với **hạn của chính secret** và **hạn của kết nối đang sử dụng secret**. Ba thời gian này có thể khác nhau. Credential database bị thu hồi có thể không lập tức ngắt phiên kết nối đang mở; cần xem semantics của database và connection pool.

Không hứa hẹn “rotate ngay lập tức” nếu hệ thống còn cache, file mount chưa cập nhật hoặc process chỉ nạp secret một lần lúc khởi động. Thời gian lan truyền của thay đổi phải được đo và đưa vào kế hoạch.

## 13. Xử lý sự cố khi kho secret hoặc identity provider không hoạt động

Quản lý secret đúng tạo thêm một phụ thuộc hạ tầng. Cần thiết kế cách service hành xử khi phụ thuộc này gặp lỗi.

**Khởi động service mà không lấy được secret bắt buộc:** tốt nhất là báo lỗi khởi động hoặc readiness không đạt, kèm mã lỗi đã được che nội dung, thay vì khởi động “thành công” rồi thất bại mơ hồ ở request đầu tiên.

**Ứng dụng đang chạy, secret manager tạm thời timeout:** có thể tiếp tục dùng bản cache hợp lệ trong khoảng cho phép, giới hạn retry có backoff và jitter, phát cảnh báo và giữ đường nghiệp vụ ổn định nếu hợp đồng bảo mật cho phép. Nếu bản cache hết hạn hoặc có tín hiệu đã bị thu hồi, phải ưu tiên từ chối thao tác cần secret thay vì dùng bản đã bị cấm.

**Token identity hết hạn:** ứng dụng hoặc agent phải có cơ chế đổi token đúng cách. Không chuyển sang một service account rộng quyền hơn khi refresh thất bại.

**Nhận 403/Access Denied:** kiểm tra policy, workload identity, môi trường và tên resource; không retry liên tục vì đây thường là lỗi quyền hoặc cấu hình, không phải lỗi tạm thời.

**Phiên bản secret mới bị sai:** có thể khôi phục qua quá trình rotation đã thiết kế nếu hệ thống vẫn chấp nhận phiên bản cũ. Nếu cần rollback, quyết định dựa trên khả năng thực tế và không chấp nhận mở rộng quyền đọc để vượt qua lỗi.

**Secret bị lộ:** xem như sự cố bảo mật có ưu tiên; ghi nhận thời gian và phạm vi, vô hiệu hóa credential tại nơi phát hành, thay phiên bản, tìm dấu vết truy cập và thu hẹp quyền nếu phát hiện policy quá rộng. Không đưa chính giá trị bị lộ vào log điều tra.

## 14. Audit: chứng minh ai đã đọc, khi nào và được phép hay không

Audit của secret manager cần trả lời được:

- Danh tính nào đã yêu cầu?
- Yêu cầu cho resource nào, từ workload/môi trường nào?
- Thao tác là read, list, write, rotate hay delete?
- Quyết định allow hoặc deny là gì?
- Khi nào yêu cầu xảy ra, request ID nào liên quan?
- Có hành vi bất thường so với hoạt động thông thường không?

Ví dụ bản ghi audit **chỉ chứa metadata**:

~~~json
{
  "timestamp": "2026-11-12T02:00:00Z",
  "principal": "prod/payment-worker",
  "operation": "read_secret_value",
  "resource": "prod/payment/gateway-api-key",
  "decision": "allow",
  "requestId": "example-request-001"
}
~~~

Không thêm trường secretValue, Authorization header hoặc token truy cập vào bản ghi.

Các tín hiệu đáng cảnh báo:

1. Một service đột nhiên đọc nhiều secret không thuộc nhu cầu thường ngày.
2. Deny tăng ở các đường dẫn ngoài phạm vi của danh tính.
3. Service staging cố đọc secret production.
4. Token không hợp lệ hoặc hết hạn được thử liên tục.
5. Secret sắp hết hạn nhưng không có dấu hiệu consumer đã chuyển phiên bản.
6. Một danh tính runtime yêu cầu thao tác quản trị mà không được phân quyền.

Audit log cũng là dữ liệu nhạy cảm vì thể hiện cấu trúc dịch vụ và tài nguyên. Chỉ người có nhiệm vụ phù hợp được xem, với chính sách lưu giữ và bảo vệ tính toàn vẹn log.

## 15. So sánh các lựa chọn kiến trúc

| Lựa chọn | Dùng khi nào | Điểm cần bảo vệ |
|---|---|---|
| Secret manager tập trung + workload identity | Nhiều service, nhiều môi trường, cần audit/rotation nhất quán | Policy cấp theo service, ranh giới môi trường, phụ thuộc khả dụng |
| Kubernetes Secret trực tiếp | Nhu cầu nhỏ hoặc môi trường đã có governance phù hợp | RBAC, quyền tạo pod, encryption at rest, quyền trên node |
| Secret manager + CSI/agent mount | Ứng dụng cần file và không tiện tích hợp SDK | Identity của agent, quyền file, refresh, đồng bộ phiên bản |
| Credential động, thời hạn ngắn | Database và backend hỗ trợ cấp quyền theo phiên | Lease, renew/revoke, kết nối đang mở, xử lý token hết hạn |
| KMS/HSM thao tác trên khóa tại chỗ | Khóa ký/giải mã cần giảm nguy cơ xuất private key | Quyền gọi cryptographic operation, rate limit, audit |

Sự lựa chọn nên dựa trên threat model, cách triển khai, nền tảng danh tính và nhu cầu rotation; không đưa thêm hệ thống mới chỉ vì nó “được gọi là secret manager”. Dù lựa chọn khác nhau, mục tiêu vẫn là mỗi service có danh tính riêng, quyền nhỏ và vòng đời có thể quan sát.

## 16. Một tình huống thiết kế từ đầu đến cuối

Hệ thống có ba luồng:

~~~text
Client -> Order API -> Order Database
                  |
                  +--> Payment Worker -> Payment Provider
                  |
                  +--> Notification Worker -> Email Provider
~~~

### 16.1. Kiểm kê nhu cầu bí mật

| Service | Secret cần | Không cần |
|---|---|---|
| Order API | order-db-credential | payment-gateway-key, email-token |
| Payment Worker | payment-gateway-key và credential database của Payment nếu có | order-db-credential, email-token |
| Notification Worker | email-provider-token | order-db-credential, payment-gateway-key |

Mỗi đường kết nối được đánh giá theo quyền nghiệp vụ: Order API chỉ cần thao tác trên schema/table của Order; Payment Worker chỉ cần các quyền phù hợp để thực hiện thanh toán và lưu trạng thái của nó.

### 16.2. Phân quyền

Tạo ba runtime principal tách biệt. Policy allow đọc một danh sách resource cố định theo từng service. Không cấp list trên toàn kho, không cấp write/rotate cho runtime. Tài khoản vận hành rotation của Payment có quyền trên secret Payment nhưng không tự đọc secret Notification.

### 16.3. Phân phối tại runtime

Mỗi workload nhận identity của chính nó. Khi cần, client đọc secret qua adapter. API/agent trả giá trị chỉ khi identity và quyền khớp. Khai báo đường dẫn logic theo môi trường mà không đóng gói payload secret trong JAR.

### 16.4. Rotation cổng thanh toán

Nhóm vận hành cấp key mới từ nhà cung cấp, lưu một phiên bản mới, chuyển Payment Worker sang version mới và xác minh giao dịch thử nghiệm. Sau khi mọi instance dùng key mới, thu hồi key cũ ở cả secret manager lẫn phía nhà cung cấp. Không cần restart Order API hoặc Notification Worker vì hai service không phụ thuộc secret đó.

### 16.5. Giả lập trường hợp bị từ chối

Cho Notification Worker thử đọc key Payment bằng chính identity Notification. Kỳ vọng: secret manager từ chối, không trả payload và audit ghi nhận deny. Đây là bằng chứng trực tiếp cho khả năng cô lập quyền giữa các service.

### 16.6. Xử lý phiên bản hết hạn

Cho Payment Worker thử khởi động khi credential gateway đã hết hiệu lực. Kỳ vọng: workload không xử lý payment với token không hợp lệ, phát tín hiệu vận hành rõ ràng, không tự lấy token service khác, và chỉ phục vụ trở lại sau khi nhận credential đúng.

## 17. Những lỗi thiết kế thường gặp

**Một role cho mọi microservice.** Dễ cấu hình lúc đầu nhưng biến một sự cố nhỏ thành nguy cơ lộ toàn bộ bí mật. Tách identity và danh sách secret theo service.

**Để service runtime có quyền tạo và xóa secret.** Service thường chỉ cần đọc; quyền quản trị rộng làm tăng hậu quả khi mã hoặc token bị xâm nhập. Phân quyền provisioning/rotation riêng.

**Chỉ phân quyền bằng đường dẫn trong code.** Một ứng dụng bị khai thác có thể gọi trực tiếp secret store bằng credential của nó. Kho secret phải kiểm tra policy theo danh tính thực.

**Dùng cùng secret giữa dev, staging và production.** Kẻ tấn công có thể đi từ môi trường ít được bảo vệ đến hệ thống thật. Tách credential và trust boundary theo môi trường.

**Coi Kubernetes Secret là mã hóa đầy đủ.** Base64 không phải encryption; ngoài encryption at rest, cần RBAC, quyền tạo pod, bảo vệ node, transport và quy trình rotation.

**Đưa secret vào environment rồi mặc định không ai đọc được.** Cần đánh giá quyền debug, process inspection, crash dump, log và quản trị runtime. Một số trường hợp file mount hoặc API có thể dễ kiểm soát hơn.

**Rotation nhưng không quản lý consumer.** Key mới tồn tại trong kho nhưng process vẫn giữ bản cũ. Cần biết cách refresh, đo thời gian chuyển đổi và chỉ revoke khi đã xử lý phụ thuộc.

**Cấp wildcard cho tiện mở rộng.** Khi tạo thêm secret mới, quyền của các service cũ bất ngờ mở rộng. Dùng resource scope hẹp và rà soát thay đổi policy như thay đổi code.

**Không có audit và thử nghiệm phủ định.** Chỉ kiểm tra rằng Payment đọc được key Payment là chưa đủ; còn phải kiểm tra Notification không đọc được nó và staging không đọc được prod.

**Ghi payload vào log khi truy lỗi.** Lỗi 403 hoặc timeout có thể được điều tra bằng request ID, metadata và tình trạng policy, không cần chụp giá trị bí mật.

## 18. Bài thực hành: thiết kế chính sách đọc theo service

Một hệ thống demo có bốn workload:

- catalog-api: phục vụ danh sách sản phẩm, không gọi hệ thống ngoài cần secret.
- order-api: đọc credential truy cập Order Database.
- payment-worker: đọc API key của Payment Provider.
- notification-worker: đọc SMTP token.

Hệ thống có hai môi trường staging và production.

**Yêu cầu thực hành:**

1. Vẽ ma trận principal × secret × operation; chỉ cấp quyền read tối thiểu. Catalog API không được cấp quyền secret nếu không có nhu cầu.
2. Đặt tên tài nguyên để staging và production tách rời. Mô tả cách kho secret xác minh environment thay vì tin vào tên do caller khai báo.
3. Viết chính sách ở dạng khái niệm với default deny. Xác định riêng principal tạo/rotate secret.
4. Mô tả đường đi từ workload identity đến secret manager và cách service nhận secret tại runtime.
5. Đề xuất ít nhất bốn tình huống cho phép/từ chối: service đọc secret của chính mình, service khác đọc nhầm, staging đọc prod, runtime cố xóa secret.
6. Định nghĩa quy trình rotation gateway key khi nhà cung cấp cho hai key cùng tồn tại trong giai đoạn chuyển tiếp.
7. Mô tả khi nào ứng dụng tiếp tục dùng cache đang hợp lệ và khi nào phải ngừng thao tác cần secret.

Một lời giải hợp lý phải bảo đảm Payment Worker không có đường đọc SMTP token hay Order credential; quyền write/rotate được cấp cho vai trò khác; quyết định deny được thực thi bởi secret manager và có audit metadata. Các con số TTL, thời gian refresh và cách triển khai cụ thể phụ thuộc nền tảng được chọn.

## 19. Kết luận

Quản lý secret trong microservices là bài toán **danh tính, cấp quyền và vòng đời**, không chỉ là giấu một chuỗi cấu hình ở nơi khác. Mỗi service cần danh tính runtime có thể kiểm chứng, quyền đọc nhỏ nhất trên đúng secret và môi trường, cách nhận secret không làm lộ payload, cùng quy trình rotation và thu hồi đo được.

Khi Order, Payment và Notification có ranh giới quyền riêng, một lỗi hoặc sự cố ở Notification khó trở thành con đường đọc khóa thanh toán của Payment. Khả năng cô lập này cần được chứng minh bằng chính sách tại nguồn, thử nghiệm truy cập bị từ chối và bản ghi audit — đồng thời được duy trì khi service, môi trường và credential thay đổi.
