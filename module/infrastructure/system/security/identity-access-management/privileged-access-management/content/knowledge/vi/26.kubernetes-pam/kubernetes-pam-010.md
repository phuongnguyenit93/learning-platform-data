# Rotate cluster credential

## 1. Rotation credential của cluster là thay đổi gì?

Rotate cluster credential là quy trình thay credential hoặc vật liệu mật mã liên quan đến Kubernetes cluster, chuyển các bên sử dụng sang phiên bản mới, rồi xử lý hiệu lực của phiên bản cũ theo mục tiêu đã định.

“Cluster credential” không phải một mật khẩu duy nhất. Nó có thể là:

- Token truy cập của workload.
- Chứng chỉ client của người quản trị hoặc thành phần hệ thống.
- Chứng chỉ máy chủ cho một endpoint.
- Khóa ký service account token.
- CA và các trust bundle.
- Credential trong kubeconfig của công cụ tự động.
- Credential tới registry, cloud hoặc dịch vụ phụ thuộc.

Không thể chọn cùng một lệnh cho tất cả các loại trên. Chúng có nguồn cấp, bên sử dụng, điểm xác minh và khả năng thu hồi khác nhau.

Trong PAM, rotation phải giảm rủi ro credential bị lộ hoặc tồn tại quá lâu, đồng thời giữ khả năng quản trị và vận hành hợp lệ. Một file mới được tạo thành công chưa đủ để kết luận rotation hoàn tất.

Bài học tập trung vào cách phân loại, lập kế hoạch, thực hiện theo từng giai đoạn và kiểm chứng. Các runbook minh họa phải được ánh xạ vào phiên bản, bản phân phối, topology và cơ chế quản lý thực tế của cluster.

## 2. Phân biệt renewal, key rotation, revocation và trust rotation

| Khái niệm | Điều thay đổi | Điều không tự được chứng minh |
|---|---|---|
| Certificate renewal | Cấp một chứng chỉ mới theo quy trình gia hạn | Private key cũ đã được thay hoặc chứng chỉ cũ mất hiệu lực |
| Key rotation | Thay khóa mật mã đang dùng | Mọi consumer đã chuyển hoặc mọi verifier đã ngừng tin khóa cũ |
| Token refresh | Lấy token mới | Bản sao token trước đó lập tức bị vô hiệu |
| Credential revocation | Làm credential không còn được chấp nhận theo cơ chế xác minh | Thao tác đã thực hiện được hoàn tác |
| Trust rotation | Thay khóa công khai, CA hoặc cấu hình mà verifier tin cậy | Tất cả issuer, client và endpoint đã chuyển cùng lúc |
| Permission change | Thay tập thao tác danh tính được phép làm | Credential không còn xác thực được ở mọi bên nhận |

Ví dụ, tạo một client certificate mới cho cùng người dùng không tự vô hiệu hóa certificate đã bị sao chép trước đó.

Ngược lại, bỏ quyền của người dùng có thể ngăn một số thao tác mà chưa làm credential mất khả năng xác thực. Nếu cùng danh tính được ánh xạ thành quyền tại một hệ thống khác, hệ thống đó còn cần xử lý riêng.

Trước mỗi job, phải viết mục tiêu đủ cụ thể:

> Thay khóa và chứng chỉ client của tác vụ triển khai A, xác nhận tác vụ dùng phiên bản mới, xử lý khả năng dùng phiên bản cũ theo cơ chế xác thực hiện tại và kiểm tra không còn bản sao hoạt động ngoài inventory.

Mục tiêu này có thể kiểm chứng hơn câu “rotate kubeconfig”.

## 3. Lập inventory theo quan hệ cấp, dùng và xác minh

Một credential cần có ít nhất ba quan hệ:

1. Ai hoặc hệ thống nào cấp và quản lý?
2. Thành phần nào sử dụng?
3. Bên nào xác minh hoặc tin cậy?

Kubernetes có nhiều quan hệ TLS: API server phục vụ client, kubelet xác thực tới API server, API server kết nối tới etcd, và các thành phần control plane dùng credential riêng. Không coi toàn bộ PKI là một cặp certificate dùng chung. [Kubernetes: PKI certificates and requirements](https://kubernetes.io/docs/setup/best-practices/certificates/).

### Bảng kiểm kê minh họa

| Credential | Bên sử dụng | Bên xác minh | Phạm vi tác động cần xem |
|---|---|---|---|
| Client certificate quản trị | Công cụ của con người hoặc automation | API server | Quyền của chủ thể và nhóm được nhận diện |
| Kubelet client certificate | Kubelet | API server | Quan hệ node với control plane |
| API server serving certificate | API server | Client và thành phần gọi API | Khả năng xác minh endpoint và thiết lập TLS |
| Credential API server tới etcd | API server | etcd | Đọc, ghi trạng thái cluster |
| ServiceAccount token | Workload hoặc client | API server hoặc dịch vụ tin cậy | Quyền Kubernetes và quyền tại bên nhận khác |
| Khóa ký token | Thành phần phát hành token | Các bên kiểm tra chữ ký | Phạm vi tất cả token và relying party liên quan |
| CA hoặc trust bundle | Thành phần xác minh TLS | Chính thành phần dùng trust | Nhiều chứng chỉ và đường kết nối phụ thuộc |
| Credential registry | Thành phần kéo image | Registry | Khả năng triển khai và tải artifact |

Bảng là khung phân tích. Một bản phân phối hoặc managed cluster có thể giao một phần trách nhiệm cho nhà cung cấp.

### Dữ liệu nên có trong inventory

- Định danh cluster và môi trường.
- Loại credential và chủ thể.
- Chủ sở hữu nghiệp vụ cùng đội kỹ thuật.
- Nguồn cấp hoặc signer.
- Bên sử dụng, nơi phân phối và bản sao.
- Bên xác minh, trust store và cơ chế cập nhật.
- Thời hạn thực tế, không chỉ thời hạn yêu cầu.
- Mã phiên bản, fingerprint hoặc định danh công khai phù hợp.
- Cách rotate, thu hồi và kiểm chứng.
- Credential nhận tiếp hoặc quan hệ phụ thuộc.
- Cơ chế khôi phục khi mất đường quản trị.

Không đưa private key, token hoặc mật khẩu vào inventory. Chỉ lưu tham chiếu tới kho bí mật có kiểm soát và metadata cần thiết.

## 4. Phân biệt cluster tự quản lý và managed cluster

### Cluster tự quản lý

Đội nền tảng có thể trực tiếp quản lý PKI, cấu hình thành phần và quy trình reload hoặc restart. Khi đó cần runbook phù hợp cách cluster được dựng.

Cluster dùng kubeadm không đồng nghĩa mọi credential đều do kubeadm quản lý. Có thể có external CA, automation riêng hoặc thành phần được cài thêm.

### Managed cluster

Một phần control plane, CA hoặc cơ chế rotation có thể thuộc trách nhiệm nhà cung cấp. Người dùng cần xác định thao tác quản trị được hỗ trợ thay vì sửa file PKI theo hướng dẫn của cluster tự quản lý.

Kế hoạch vẫn cần kiểm kê những thứ thuộc phía tổ chức:

- Kubeconfig của người và automation.
- Workload identity.
- Token tĩnh còn tồn tại.
- Credential registry hoặc dịch vụ ngoài.
- Trust cấu hình ở webhook, hệ thống giám sát và broker.
- Đường break-glass và quyền cloud quản lý cluster.

### Hợp đồng trách nhiệm

Với từng credential, ghi ai chịu trách nhiệm tạo, phân phối, kích hoạt, ngừng dùng cũ và kiểm chứng.

Không để hai bên cùng nghĩ bên còn lại đã thu hồi credential cũ. Một tác vụ nhà cung cấp báo thành công có thể chưa bao gồm mọi client hoặc bên nhận ngoài cluster của tổ chức.

## 5. Rotation định kỳ khác xử lý credential bị lộ

### Rotation định kỳ

Mục tiêu là thay trước khi hết hạn, giảm tuổi credential và thử khả năng vận hành vòng đời.

Có thể dùng một khoảng chuyển tiếp có kiểm soát để consumer dùng được phiên bản mới trước khi ngừng chấp nhận phiên bản cũ.

### Rotation khi nghi ngờ bị lộ

Mục tiêu còn gồm chặn bên không tin cậy. Một khoảng chuyển tiếp tiếp tục tin credential cũ có thể giữ nguyên đường truy cập bị ảnh hưởng.

Cần đánh giá:

- Credential nào bị lộ: token, private key của client hay khóa ký?
- Có khả năng cấp credential mới bằng nguồn bị xâm nhập không?
- Bên bị ảnh hưởng còn điều khiển workload hoặc signer không?
- Có thể giảm quyền hoặc chặn truy cập tại đích trong lúc chuyển đổi không?
- Mức gián đoạn nào được chấp nhận để chặn sự cố?
- Có credential hoặc phiên đích đã được cấp tiếp không?

Không áp dụng máy móc runbook “tin cả khóa cũ và mới” cho một khóa ký đã bị lộ. Quyết định giữ thời gian chuyển tiếp phải phản ánh nguy cơ tiếp tục giả mạo credential.

### Rotation không thay điều tra tác động

Credential mới không hoàn tác dữ liệu đã bị đọc hoặc thay đổi. Cần đối soát quyền, tài nguyên, danh tính và hiện vật đã tạo trong khoảng bị ảnh hưởng.

Nếu nguồn workload vẫn bị điều khiển, nó có thể lấy credential mới sau rotation. Phải xử lý nguồn tin cậy trước khi coi thay bí mật là biện pháp đầy đủ.

## 6. Thiết kế chuỗi chuyển đổi và điều kiện dừng

Một mô hình thường dùng cho thay đổi định kỳ:

~~~mermaid
flowchart LR
    A[Kiểm kê và phê duyệt] --> B[Chuẩn bị phiên bản mới]
    B --> C[Chuẩn bị bên xác minh nếu cần]
    C --> D[Chuyển bên sử dụng theo từng nhóm]
    D --> E[Kiểm chứng thực tế]
    E --> F[Ngừng sử dụng hoặc tin phiên bản cũ]
    F --> G[Kiểm tra từ chối và đóng hồ sơ]
~~~

Không phải loại credential nào cũng hỗ trợ hai phiên bản đồng thời. Với từng giai đoạn, cần ghi rõ khả năng kỹ thuật.

### Điều kiện trước khi bắt đầu

- Đã xác định đúng cluster, scope và loại credential.
- Có inventory đủ cho những bên phụ thuộc quan trọng.
- Có quyền thực hiện theo tác vụ và thời hạn phù hợp.
- Đã xác nhận baseline sức khỏe và truy cập.
- Có cách lấy credential mới mà không phát tán bí mật.
- Có đường khôi phục đã kiểm chứng.
- Biết thành phần nào reload và thành phần nào cần restart.
- Có tiêu chí dừng nếu hệ thống suy giảm.
- Kế hoạch không dựa vào credential sắp hết hạn để hoàn tất mọi bước còn lại.

### Điểm kiểm soát sau mỗi nhóm

Sau khi đổi một thành phần, cần xác nhận kết nối mới hoạt động và không làm mất năng lực bắt buộc trước khi chuyển tiếp.

Một cluster nhiều control-plane node không tự bảo đảm không gián đoạn. Còn cần tình trạng các node còn lại, load balancer, kết nối client và quorum của những hệ thống phụ thuộc.

Không thay đồng thời mọi credential chỉ để rút ngắn số bước nếu điều đó làm mất khả năng xác định lỗi và khôi phục.

## 7. ServiceAccount token: thay token khác thay khóa ký

### 7.1. Rotation token của workload

Projected token được cấp có thời hạn và kubelet làm mới; ứng dụng cần dùng được file token mới. Cơ chế này khác token lưu tĩnh trong Secret và không thay cho quản lý quyền của ServiceAccount. [Kubernetes: Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/).

Runbook cho một workload nên chỉ ra:

1. Danh tính và audience được dùng.
2. Cách credential tới container.
3. Cách ứng dụng nạp lại token.
4. Bên nhận xác minh theo cơ chế nào.
5. Đường ngăn nhận token mới khi workload không còn tin cậy.
6. Những credential đích có thể được cấp từ token nguồn.

Không sao chép token ra ticket để so sánh trước và sau. Dùng metadata hoặc kết quả kiểm tra đã được làm sạch bí mật.

### 7.2. Rotation khóa ký service account token

Thay khóa ký là thay nguồn tạo chữ ký cho nhiều token, không chỉ thay một credential của một Pod.

Kubernetes phân biệt khóa dùng ký và khóa dùng xác minh; cấu hình xác minh có thể chấp nhận nhiều khóa. Vì thế, có thể thiết kế giai đoạn chuyển tiếp phù hợp, nhưng phải xét cả các bên xác minh ngoài API server. [Kubernetes: Configure Service Accounts for Pods](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/).

Một kế hoạch định kỳ minh họa:

- Chuẩn bị khóa ký mới trong hệ thống quản lý khóa được phép.
- Bảo đảm verifier liên quan có thể xác minh token mới.
- Chuyển các issuer theo kế hoạch đã kiểm thử.
- Xác nhận token mới thật sự được phát hành bằng khóa mới.
- Xác định thời điểm cuối còn phát hành token bằng khóa cũ.
- Theo dõi consumer và thời hạn token cũ.
- Ngừng chấp nhận khóa cũ tại mọi verifier trong phạm vi.
- Kiểm tra token thuộc thế hệ cũ bị từ chối theo tiêu chí.

Không giả định cập nhật một API server đã chuyển toàn bộ signer trong một control plane nhiều instance.

### 7.3. Tính thời gian chuyển tiếp theo dữ kiện

Trong trường hợp định kỳ, nếu tất cả token cũ có thời hạn hữu hạn và các verifier kiểm tra thời hạn đúng, có thể dùng một giới hạn lập kế hoạch:

~~~text
Mốc cân nhắc ngừng tin khóa cũ
    >= thời điểm cuối phát hành bằng khóa cũ
       + thời gian hiệu lực tối đa thực tế của token cũ
       + phần dung sai thời gian đã được đánh giá
~~~

Đây không phải công thức đủ cho mọi hệ thống. Còn phải xét cache, token tĩnh, issuer chưa chuyển và relying party chưa cập nhật.

Nếu khóa cũ bị lộ, bên không tin cậy có thể tạo thêm token trong lúc khóa vẫn được chấp nhận. Không dùng thời điểm phát hành hợp lệ cuối cùng để suy ra mọi credential giả mạo đã hết hạn.

### 7.4. Bên xác minh ngoại tuyến và credential đích

Một dịch vụ dùng cache khóa công khai có thể không cập nhật cùng thời điểm với control plane. Cần kiểm tra chính sách làm mới, xử lý khóa mới và ngừng chấp nhận khóa cũ.

Nếu token dùng để đổi credential tại hệ thống khác, phải theo dõi vòng đời credential đích. Loại bỏ khóa ở nguồn không tự kết thúc mọi phiên đã được cấp tại đích.

## 8. Client certificate và kubeconfig

Kubeconfig là cấu hình truy cập, có thể chứa credential hoặc tham chiếu tới cơ chế lấy credential. Đổi tên context hoặc thay endpoint không tự rotate credential.

Khi xử lý một kubeconfig, cần biết:

- Đang dùng client certificate, token hay cơ chế lấy credential khác?
- Có private key hoặc certificate được nhúng không?
- Có bản sao trong máy cá nhân, runner hoặc kho bí mật không?
- Ai có quyền đọc và sửa file?
- Client đang dùng file nào, profile nào?
- Bản cũ có còn xác thực và được cấp quyền không?

### Renewal không có nghĩa certificate cũ bị thu hồi

Tài liệu xác thực Kubernetes nêu cơ chế client certificate không hỗ trợ thu hồi từng chứng chỉ như một thao tác revocation riêng. Vì vậy, cấp certificate mới không tự hủy certificate cũ vẫn còn được nguồn tin cậy chấp nhận. [Kubernetes: Authenticating](https://kubernetes.io/docs/reference/access-authn-authz/authentication/).

Runbook phải phân biệt:

- Xác nhận certificate mới dùng được.
- Xác nhận quyền của chủ thể đúng.
- Xử lý certificate cũ theo cơ chế thực tế.
- Xử lý bản sao private key và file kubeconfig.
- Xử lý các kết nối hoặc phiên đích liên quan.

Nếu chứng chỉ cũ bị lộ, có thể cần kiểm soát quyền hoặc điểm truy cập, thay mô hình danh tính, hoặc một thay đổi trust có phạm vi lớn hơn. Phương án phải xét quyền thực tế của chủ thể; không mặc định gỡ một binding là đủ cho mọi danh tính quản trị.

### Quy trách nhiệm và least privilege

Không cấp một kubeconfig quản trị chung rồi phát cho nhiều người chỉ để việc rotation dễ hơn. Khi mọi người dùng cùng danh tính, log khó gắn hành động với từng cá nhân.

Danh tính con người nên theo vòng đời cá nhân và luồng đặc quyền có thời hạn phù hợp. Automation cần danh tính riêng với quyền tác vụ, chủ sở hữu và cơ chế rotation có thể thực hiện được.

## 9. Renewal chứng chỉ trong cluster dùng kubeadm

Với cluster thực sự do kubeadm quản lý, lệnh đọc thông tin sau có thể hỗ trợ kiểm kê thời hạn:

~~~shell
kubeadm certs check-expiration
~~~

Chỉ dùng trong môi trường và trên host được phép; đây không phải kiểm tra đầy đủ mọi credential của cluster.

Kubeadm có các thao tác renewal cho chứng chỉ nó quản lý. Runbook cần tính việc nhiều control-plane node phải được xử lý và thành phần có thể cần restart để dùng certificate mới. Kubeadm không tự cung cấp một quy trình rotation hoặc thay CA hoàn chỉnh chỉ bằng thao tác renewal. [Kubernetes: Certificate Management with kubeadm](https://kubernetes.io/docs/tasks/administer-cluster/kubeadm/kubeadm-certs/).

### Runbook phải kiểm chứng những gì?

Trước renewal:

- Xác định certificate cụ thể cùng bên sử dụng.
- Xác định CA và signer đang chịu trách nhiệm.
- Kiểm tra subject, mục đích sử dụng và tên endpoint cần phục vụ.
- Biết công cụ có tạo private key mới hay tái sử dụng key.
- Xác định file nào được thay và cấu hình nào tham chiếu.
- Có bản phục hồi được bảo vệ phù hợp mức độ nhạy cảm.

Sau renewal:

- Certificate mới có thuộc tính và thời hạn đúng.
- Private key mới đúng với certificate nếu mục tiêu là thay key.
- Thành phần thực sự đã nạp phiên bản mới.
- Endpoint hoặc client đang dùng đúng certificate.
- Những bản kubeconfig phân phối cho consumer đã được cập nhật khi cần.
- Các kết nối quan trọng vẫn xác thực đúng.

Không dùng một lệnh thành công làm bằng chứng cho mọi bước này.

### Quan sát certificate mà không đọc private key

Trong một cluster kubeadm có đúng đường dẫn này, có thể đọc metadata certificate công khai:

~~~shell
openssl x509 -in /etc/kubernetes/pki/apiserver.crt -noout -dates -issuer -subject -fingerprint -sha256
~~~

Đường dẫn chỉ minh họa cho cấu hình tương ứng. Kết quả là metadata của file trên đĩa, không chứng minh API server đang phục vụ đúng file đó.

Nếu endpoint qua load balancer, cần kiểm tra từng backend hoặc nguồn bằng chứng tương đương. Một lần kết nối có thể chỉ chạm một instance đã đổi trong khi instance khác còn dùng bản cũ.

Không dùng việc tắt kiểm tra TLS để làm bước xác nhận thành công.

## 10. Kubelet: client certificate và serving certificate khác nhau

Kubelet client certificate dùng khi kubelet gọi API server. Kubernetes có cơ chế tạo key và yêu cầu certificate thay thế khi được cấu hình rotation và luồng cấp hoạt động đúng. [Kubernetes: Configure Certificate Rotation for the Kubelet](https://kubernetes.io/docs/tasks/tls/certificate-rotation/).

Serving certificate bảo vệ endpoint của kubelet là một quan hệ khác. Luồng bootstrap và phê duyệt serving certificate không nên bị coi là tự động giống client certificate; tài liệu nêu cần cơ chế phê duyệt phù hợp cho serving CSR. [Kubernetes: TLS Bootstrapping](https://kubernetes.io/docs/reference/access-authn-authz/kubelet-tls-bootstrapping/).

### Kiểm tra luồng, không chỉ kiểm tra cờ

Một trường cấu hình bật rotation chưa chứng minh rotation đã diễn ra.

Cần quan sát:

1. Có yêu cầu certificate mới đúng chủ thể không?
2. Yêu cầu có đúng signer, mục đích và thuộc tính không?
3. Phê duyệt có hợp lệ và độc lập theo chính sách không?
4. Certificate đã được cấp chưa?
5. Kubelet có nhận và dùng nó không?
6. Kết nối mới tới đích có hoạt động không?
7. Có node nào còn chờ hoặc dùng credential sắp hết hạn không?

Có thể xem danh sách CSR trong môi trường được phép:

~~~shell
kubectl --context pam-lab get csr
~~~

Lệnh này chỉ hỗ trợ quan sát. Không tự duyệt hàng loạt CSR đang Pending để làm cảnh báo biến mất.

### Phê duyệt CSR cũng là đặc quyền

Một bên có khả năng cấp hoặc phê duyệt certificate có thể tác động tới danh tính được tin cậy.

Quy trình phải xác minh nguồn yêu cầu, danh tính, mục đích và scope. Đừng dựa vào tên CSR hoặc tên node do một phía không tin cậy tự khai làm bằng chứng duy nhất.

Nếu node hoặc nguồn bootstrap đã bị xâm nhập, cấp certificate mới cho cùng nguồn đó có thể tiếp tục giữ đường truy cập không mong muốn.

## 11. Rotation CA và trust bundle

Thay CA là thay một gốc tin cậy có thể ảnh hưởng nhiều certificate, client và endpoint. Nó có phạm vi lớn hơn renewal một leaf certificate.

Tài liệu rotation CA thủ công của Kubernetes dùng mô hình chuyển đổi từng bước và nêu giả định về HA; cluster một API server có thể gián đoạn khi restart. Các điểm cấu hình cũng không mặc nhiên đều chấp nhận CA bundle theo cùng cách. [Kubernetes: Manual Rotation of CA Certificates](https://kubernetes.io/docs/tasks/tls/manual-rotation-of-ca-certificates/).

### Mô hình chuyển đổi định kỳ

Với những thành phần hỗ trợ cơ chế phù hợp, kế hoạch khái niệm có thể gồm:

1. Chuẩn bị CA mới và nguồn ký được bảo vệ.
2. Chuẩn bị verifier tin certificate mới, giữ khả năng kết nối cần thiết trong chuyển tiếp.
3. Cấp certificate mới cho các bên sử dụng.
4. Chuyển endpoint và client theo thứ tự phụ thuộc.
5. Kiểm tra các kết nối mới cùng chức năng điều khiển.
6. Xử lý những consumer còn dùng trust hoặc certificate cũ.
7. Loại bỏ trust cũ khi đủ điều kiện.
8. Kiểm tra đường cũ không còn được chấp nhận trong phạm vi mục tiêu.

Không sao chép CA bundle vào mọi file có tên ca.crt mà chưa biết file đó dùng để xác minh hay ký và thành phần có hỗ trợ bundle không.

Private key của CA cũng không cần được phân phối đến mọi verifier. Bên kiểm tra trust thường cần dữ liệu công khai phù hợp; việc tạo thêm bản sao khóa ký làm tăng phạm vi phải bảo vệ.

### Vẽ đồ thị phụ thuộc trước khi thay

~~~text
CA hoặc nguồn tin cậy
  -> Certificate của endpoint
  -> Trust store của client gọi endpoint

CA hoặc nguồn tin cậy
  -> Certificate client
  -> Trust store của server nhận client

Nguồn ký token
  -> Token
  -> Khóa xác minh và cache của bên nhận
~~~

Ba quan hệ này có thể cùng tồn tại nhưng không thay thế nhau.

Ví dụ, thay serving certificate API server có thể yêu cầu client tin CA phù hợp. Nó không tự thay khóa ký token workload. Ngược lại, thay khóa ký token không tự sửa lỗi TLS tới endpoint API server.

### Phạm vi thường bị bỏ sót

- Công cụ quản trị ở ngoài cluster.
- Runner và pipeline triển khai.
- Controller hoặc operator do tổ chức cài thêm.
- Admission webhook và API mở rộng.
- Hệ thống giám sát, backup và khôi phục.
- Cấu hình in-cluster cùng những client nạp trust một lần.
- Dữ liệu bootstrap hoặc discovery.
- etcd và proxy có miền tin cậy riêng.

Mỗi mục cần được xác định theo kiến trúc thực tế, không dựa trên một danh sách mặc định rồi coi là đầy đủ.

## 12. Credential registry, cloud và dịch vụ ngoài

Rotate cluster credential đôi khi bắt đầu từ một Secret dùng cho registry hoặc API dịch vụ ngoài. Khi đó cần tách:

- Credential nguồn tại nhà cung cấp.
- Bản phân phối trong cluster.
- Cách ứng dụng hoặc thành phần tải credential.
- Phiên hoặc credential nhận tiếp.

Chỉ cập nhật Secret trong cluster chưa chứng minh credential cũ đã bị thu hồi ở dịch vụ nguồn. Chỉ rotate ở dịch vụ nguồn mà không chuyển consumer có thể làm tác vụ hợp lệ ngừng hoạt động.

### Runbook minh họa cho credential ngoài

1. Xác định workload, chủ sở hữu và quyền cần thiết.
2. Tạo phiên bản mới bằng cơ chế nhà cung cấp hỗ trợ.
3. Phân phối qua kho bí mật hoặc luồng được phép.
4. Chuyển một nhóm consumer thử nghiệm.
5. Kiểm tra thao tác nghiệp vụ và phạm vi từ chối.
6. Chuyển các consumer còn lại.
7. Ngừng chấp nhận phiên bản cũ tại nguồn.
8. Đối soát lỗi, bản sao và credential đích.

Nếu nhà cung cấp không cho hai credential đồng thời, phải thiết kế cửa sổ chuyển đổi và phương án phục hồi theo hạn chế đó.

Rotation cũng là cơ hội rà soát quyền. Không mặc nhiên giữ nguyên role quản trị rộng nếu tác vụ chỉ cần kéo image hoặc đọc một tập dữ liệu.

## 13. Hồ sơ job rotation và phân tách trách nhiệm

Một job có thể cần quyền mạnh, nhưng không phải ai tham gia cũng cần giữ toàn bộ quyền.

Có thể phân tách:

| Trách nhiệm | Năng lực cần thiết |
|---|---|
| Chủ sở hữu dịch vụ | Xác nhận nhu cầu, phạm vi và tiêu chí nghiệp vụ |
| Người phê duyệt | Chấp thuận thay đổi cùng mức ảnh hưởng |
| Người thực thi | Thực hiện tác vụ được ủy quyền trong thời hạn |
| Người quản lý signer hoặc vault | Cấp và bảo vệ vật liệu mật mã theo nhiệm vụ |
| Người kiểm chứng | Đối chiếu phiên bản, kết quả và giới hạn quyền |
| Người xử lý sự cố | Điều phối khi có tín hiệu dừng hoặc nghi ngờ bị lộ |

Đội nhỏ có thể gộp một số trách nhiệm, nhưng xung đột và điểm kiểm tra độc lập phải được nhận diện.

### Hồ sơ minh họa

~~~yaml
credential_rotation_job:
  job_reference: ROTATE-EX-028
  cluster_reference: cluster-orders-training
  environment: training
  accountable_owner: platform-team
  objective: replace-deployment-client-credential

  credential:
    kind: client-certificate-and-private-key
    principal_reference: orders-deployer
    issuer_reference: "<nguồn cấp đã xác minh>"
    previous_public_fingerprint: "<fingerprint công khai>"
    replacement_public_fingerprint: "<fingerprint công khai mới>"
    private_material_reference: "<tham chiếu kho bí mật>"

  scope:
    consumers:
      - runner-orders-training
    verifiers:
      - api-endpoint-training
    downstream_credentials: none

  execution:
    request_reference: CHANGE-EX-028
    approval_reference: APPROVAL-EX-028
    operator_reference: "<danh tính cá nhân>"
    privileged_activation_reference: "<phiên tác vụ>"
    planned_start: "<thời điểm có múi giờ>"
    planned_end: "<thời điểm có múi giờ>"

  verification:
    new_credential_test_reference: TEST-NEW-EX-028
    old_credential_handling_reference: TEST-OLD-EX-028
    permission_regression_reference: TEST-SCOPE-EX-028
    runtime_evidence_reference: EVID-EX-028

  recovery:
    procedure_reference: RECOVER-EX-028
    compromised_material_allowed_for_reuse: false
~~~

Mẫu là hồ sơ quản trị, không phải cấu hình nhập vào Kubernetes.

Trường xử lý credential cũ phải mô tả cơ chế thật. Với client certificate không có đường thu hồi riêng phù hợp, không điền “đã revoke” chỉ vì tạo được certificate thay thế.

## 14. Kiểm thử sau rotation

### 14.1. Chứng minh sử dụng phiên bản mới

Cần bằng chứng từ điểm sử dụng hoặc bên xác minh, không chỉ từ hệ thống tạo credential.

Ví dụ:

- Endpoint phục vụ certificate có fingerprint mới.
- Client dùng đúng danh tính và phiên bản credential.
- Token mới được verifier chấp nhận với audience đúng.
- Kubelet đã thiết lập lại kết nối bằng credential thay thế.
- Pipeline hoàn thành tác vụ được duyệt.
- Dịch vụ ngoài không ghi nhận lỗi xác thực của consumer chưa chuyển.

Không để client âm thầm fallback sang credential cũ rồi báo kiểm thử thành công. Cần biết đường nào thực sự được dùng.

### 14.2. Chứng minh giới hạn quyền vẫn đúng

Rotation không nên vô tình mở quyền hoặc đổi danh tính.

Kiểm thử cần bao gồm:

| Nhóm | Ví dụ kỳ vọng |
|---|---|
| Tác vụ hợp lệ | Danh tính mới đọc hoặc cập nhật đúng tài nguyên được phép |
| Vượt ứng dụng | Không thao tác được tài nguyên của đội khác |
| Vượt môi trường | Không nhận quyền production từ credential thử nghiệm |
| Quản trị IAM/RBAC | Không tự cấp thêm quyền ngoài nhiệm vụ |
| Nguồn không tin cậy | Không tiếp tục nhận credential mới |
| Bên nhận sai | Không chấp nhận token dành cho audience khác |
| Metadata không đúng | Certificate hoặc token có thuộc tính sai bị xử lý đúng cơ chế |

Một credential mới có hiệu lực nhưng mang nhóm quyền mạnh hơn ban đầu là một sự cố phân quyền, không phải kết quả rotation tốt.

### 14.3. Chứng minh xử lý phiên bản cũ

Đối với một credential cần mất hiệu lực, cần thử theo cơ chế được phép mà không phát tán bí mật.

Kết luận nên đủ cụ thể:

> Credential cũ không còn được chấp nhận tại tập verifier đã kiểm tra sau mốc chuyển đổi; các verifier ngoài phạm vi chưa được kết luận.

Hoặc:

> Certificate cũ còn được CA hiện tại xác thực đến thời điểm hết hạn; quyền tại API đã được xử lý theo kế hoạch, và phần giới hạn còn lại được ghi nhận.

Không dùng timeout, endpoint hỏng hoặc lỗi mạng làm bằng chứng thu hồi. Phải phân biệt xác thực thất bại, permission bị từ chối và dịch vụ không sẵn sàng.

### 14.4. Kiểm tra khả năng điều khiển thực tế

Cluster có thể còn chạy Pod cũ nhưng mất một phần control plane. Vì vậy, không chỉ nhìn ứng dụng đang trả lời HTTP.

Kế hoạch có thể cần thử trong scope an toàn:

- Client đọc tài nguyên được phép.
- Controller tiếp tục reconcile.
- Scheduler và node cập nhật trạng thái theo thiết kế.
- Workload thử nghiệm được tạo và vận hành bình thường.
- Hệ thống giám sát nhận được dữ liệu cần thiết.
- Cơ chế cấp credential tiếp theo vẫn hoạt động.

Các bước thử phải phù hợp quyền và mức ảnh hưởng của môi trường.

## 15. Khôi phục, rollback và break-glass

### 15.1. Chuẩn bị trước khi mất truy cập

Một bản backup chỉ hữu ích nếu được bảo vệ, đúng revision và có phương án dùng khi đường quản trị bình thường không hoạt động.

Cần xác định:

- Ai được mở bản phục hồi.
- Bản nào chứa private key hoặc credential còn hiệu lực.
- Cấu hình nào phải đồng bộ với credential.
- Khôi phục một node có tương thích với các node khác không.
- Đường out-of-band hoặc hỗ trợ nhà cung cấp nào còn dùng được.
- Điều kiện nào cho phép dùng break-glass.
- Sau khôi phục phải thu hồi quyền tạm và đối soát gì.

Không phân phối CA private key rộng chỉ để “dễ khôi phục”.

### 15.2. Rollback không luôn là quay về credential cũ

Trong rotation định kỳ, quay về cấu hình trước có thể là phương án đã đánh giá.

Trong sự cố credential bị lộ, dùng lại khóa cũ có thể mở lại đường truy cập đang muốn chặn. Phương án khôi phục có thể phải tiếp tục bằng một credential mới khác hoặc sửa trust theo hướng tiến, thay vì khôi phục vật liệu đã không còn tin cậy.

Quyết định phải dựa trên loại lỗi, phạm vi xâm nhập và mục tiêu ứng phó.

### 15.3. Tiêu chí dừng

Ví dụ các tín hiệu cần dừng chuyển nhóm tiếp theo:

- Không chứng minh được thành phần đang dùng credential nào.
- Một nhóm control plane không phục hồi sức khỏe.
- Có lỗi TLS hoặc xác thực tăng mà chưa xác định nguyên nhân.
- Consumer quan trọng chưa có trust mới.
- Không còn đường khôi phục đã chuẩn bị.
- Phát hiện nguồn cấp hoặc kho bí mật có dấu hiệu bị can thiệp.
- Credential mới mang quyền ngoài phạm vi.

Dừng chuyển bước không có nghĩa bỏ mặc job. Cần giữ trạng thái có thể hiểu, điều tra và theo phương án phục hồi đã định.

## 16. Audit và bảo vệ vật liệu mật mã

Bằng chứng cần cho biết ai thay gì, trên cluster nào, vì sao, khi nào và kết quả ra sao.

Chuỗi mong muốn:

~~~text
Inventory
  -> Yêu cầu và phê duyệt
  -> Cấp hoặc tạo phiên bản mới
  -> Phân phối có kiểm soát
  -> Consumer nạp và sử dụng
  -> Verifier kiểm chứng
  -> Xử lý phiên bản cũ
  -> Kết thúc quyền tác vụ và đóng hồ sơ
~~~

### Dữ liệu phù hợp

- Mã job và mã thay đổi.
- Danh tính cá nhân cùng phiên đặc quyền.
- Định danh credential, signer và consumer.
- Fingerprint hoặc phiên bản công khai.
- Thời hạn và mốc kích hoạt.
- Những thành phần đã chuyển và chưa chuyển.
- Kết quả tác vụ được phép và ca từ chối.
- Ngoại lệ cùng chủ sở hữu, thời hạn xử lý.
- Bản ghi sử dụng break-glass nếu có.

### Dữ liệu không đưa vào bằng chứng thông thường

- Private key.
- Token nguyên vẹn.
- Kubeconfig có credential nhúng.
- Mật khẩu hoặc khóa truy cập dịch vụ ngoài.
- Bản dump Secret.
- Header xác thực trong trace.

Cần thiết kế mức thu thập audit phù hợp để việc theo dõi cấp token không làm lộ token trong body. Kubernetes phân biệt các mức Metadata, Request và RequestResponse; không nên bật ghi body diện rộng cho mọi API chứa bí mật. [Kubernetes: Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/).

Bản backup chứa credential phải có quyền truy cập và vòng đời phù hợp. Hết job không đồng nghĩa cứ giữ mọi private key cũ vô thời hạn trong một thư mục chia sẻ.

## 17. Tình huống thực tế: pipeline đã đổi credential nhưng máy cũ vẫn truy cập được

### Bối cảnh

Đội Orders thay client certificate của pipeline triển khai. Runner mới dùng certificate mới và hoàn thành một lần triển khai thử nghiệm.

Một máy cũ vẫn có kubeconfig chứa certificate trước đó. Khi thử một thao tác đọc được phép, máy vẫn truy cập được API.

### Điều này nói lên gì?

Nó không chứng minh renewal đã thất bại. Nó chứng minh mục tiêu “certificate cũ không còn dùng được” chưa được đáp ứng bằng việc cấp certificate mới.

Cần phân tích riêng:

- Certificate mới có thực sự được runner dùng không?
- Certificate cũ còn thời hạn và được trust không?
- Hai certificate ánh xạ thành cùng danh tính và nhóm nào?
- Có cách xử lý quyền ở đích trong phạm vi chủ thể đó không?
- Có cần thay mô hình credential để đáp ứng yêu cầu vòng đời không?
- Máy cũ có giữ credential khác không?

### Cách xử lý phù hợp hơn

Đội sửa tiêu chí job, phân biệt thay credential đang dùng với kết thúc hiệu lực bản cũ. Họ kiểm kê bản sao, xử lý quyền và nguồn trust theo một phương án đã đánh giá.

Nếu mục tiêu cần quyền tạm thời, đội đánh giá một luồng truy cập có thời hạn và cơ chế kết thúc phù hợp, thay vì lặp lại việc phát certificate dài hạn cho cùng tài khoản dùng chung.

Đội cũng kiểm tra những credential hoặc quyền có thể đã được tạo bởi phiên quản trị trước đó.

### Bằng chứng cần có trước khi đóng

- Runner dùng được credential mới với đúng scope.
- Có kết luận rõ về hiệu lực và permission của certificate cũ.
- Các bản sao và nguồn cấp ngoài inventory đã được xử lý hoặc ghi ngoại lệ.
- Không phát sinh quyền rộng hơn.
- Có chủ sở hữu cho phần chưa thể thu hồi theo cơ chế hiện tại.
- Quyền đặc quyền dùng để thực hiện job đã kết thúc.

## 18. Những lỗi thường gặp

### Chạy renewal rồi báo đã rotate toàn cluster

Một loại certificate không đại diện cho token, khóa ký, CA và credential ngoài cluster.

### Quên consumer ngoài cluster

Runner, backup, dashboard và máy quản trị có thể giữ credential hoặc trust riêng.

### Chỉ nhìn file mới trên đĩa

Thành phần có thể chưa reload hoặc client có thể đang dùng một đường cấu hình khác.

### Giữ cả khóa cũ và mới vô thời hạn

Khoảng chuyển tiếp cần tiêu chí kết thúc. Nếu không, mục tiêu loại bỏ phiên bản cũ có thể không đạt.

### Xóa trust cũ trước khi consumer chuyển

Có thể làm mất đường quản trị hoặc khả năng hoạt động của thành phần phụ thuộc.

### Tin mọi file CA đều dùng cùng cách

Cần phân biệt nguồn ký, dữ liệu xác minh và giới hạn hỗ trợ bundle của từng thành phần.

### Coi tự động rotation là không cần theo dõi

Luồng cấp, phê duyệt, phân phối hoặc nạp credential vẫn có thể lỗi.

### Duyệt CSR hàng loạt

Có thể cấp danh tính không đúng. Phê duyệt certificate là một thao tác đặc quyền cần xác minh yêu cầu.

### Thu hồi ở nguồn nhưng bỏ phiên đích

Credential được cấp tiếp hoặc phiên tại hệ thống khác có thể vẫn hoạt động.

### Dùng lại khóa đã lộ để khôi phục nhanh

Có thể phục hồi cả đường truy cập không tin cậy. Cần phương án khôi phục phù hợp sự cố.

### Thêm quyền quản trị để vượt lỗi rotation

Lỗi có thể do trust, thời gian, audience hoặc reload. Mở permission không giải quyết đúng nguyên nhân.

## 19. Bài thực hành

Thiết kế một job rotation trên cluster thử nghiệm cho ba loại đối tượng:

- Credential của pipeline triển khai Orders.
- Token của workload gửi báo cáo.
- Một serving certificate do đội nền tảng quản lý trong môi trường lab.

Không yêu cầu thay CA hoặc tác động production để hoàn thành bài học.

### Sản phẩm cần tạo

1. Inventory có issuer, consumer, verifier và chủ sở hữu.
2. Mục tiêu riêng cho từng loại credential.
3. Sơ đồ phụ thuộc và các bản sao.
4. Kế hoạch chuyển đổi, thời hạn và quyền tác vụ.
5. Cơ chế quan sát phiên bản được sử dụng mà không lưu bí mật.
6. Ca kiểm thử tác vụ hợp lệ, vượt scope và xử lý credential cũ.
7. Phương án reload hoặc restart cho từng thành phần.
8. Tiêu chí dừng và khôi phục.
9. Hồ sơ ngoại lệ nếu cơ chế không hỗ trợ thu hồi như mong muốn.
10. Bằng chứng kết thúc quyền đặc quyền của người thực hiện.

### Bảng tự đánh giá

| Câu hỏi | Kết quả cần đạt |
|---|---|
| Đã thay loại credential nào? | Mô tả chính xác, không gọi chung “mọi credential” |
| Private key có thay không? | Có bằng chứng phù hợp mục tiêu |
| Ai đang dùng bản mới? | Liệt kê consumer đã kiểm chứng |
| Ai còn dùng bản cũ? | Có danh mục hoặc bằng chứng không còn trong scope |
| Credential cũ có bị từ chối không? | Kết luận theo cơ chế, không suy từ việc tạo bản mới |
| Có quyền mới ngoài nhu cầu không? | Ca kiểm thử cho thấy scope được giữ |
| Có thể khôi phục khi lỗi không? | Phương án được kiểm chứng trong lab |
| Có làm lộ bí mật trong báo cáo không? | Không có token hoặc private key nguyên vẹn |

Nếu không đáp ứng một điều kiện, ghi rõ thay vì đánh dấu hoàn tất dựa trên một lệnh thành công.

## 20. Câu hỏi tự kiểm tra

**Vì sao “rotate kubeconfig” là mô tả chưa đủ?**

Vì kubeconfig có thể chứa hoặc tham chiếu nhiều loại credential. Phải biết đang thay cơ chế nào, consumer nào dùng và bản cũ được xử lý ra sao.

**Cấp certificate mới có tự thu hồi certificate cũ không?**

Không. Hiệu lực cũ phụ thuộc nguồn trust và cơ chế xác thực, không chỉ sự tồn tại của một certificate thay thế.

**Token rotation và signing-key rotation khác nhau thế nào về phạm vi?**

Một bên thay credential sử dụng; bên kia thay nguồn ký có thể ảnh hưởng nhiều token và nhiều verifier.

**Vì sao cần kiểm tra kết nối mới sau chuyển đổi?**

Kết nối hoặc cache trước đó có thể che việc thành phần chưa thực sự sử dụng credential hay trust mới.

**HA có bảo đảm job không gián đoạn không?**

Không. Còn phải kiểm tra các instance còn lại, đường kết nối, trạng thái phụ thuộc và thứ tự thao tác.

**Khi nào không nên rollback về credential cũ?**

Khi nó đã không còn tin cậy hoặc việc dùng lại sẽ mở lại đường truy cập cần chặn.

**Một lỗi mạng có chứng minh credential cũ bị thu hồi không?**

Không. Cần xác định rõ phản hồi của cơ chế xác thực hoặc phân quyền tại đích.

**Điều kiện quan trọng nhất để đóng job là gì?**

Mục tiêu về credential mới, quyền đúng phạm vi và xử lý phiên bản cũ đều có bằng chứng trong scope đã xác định, cùng các ngoại lệ được ghi rõ.
