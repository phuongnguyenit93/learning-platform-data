# Service account token

## 1. Service account token là gì?

Service account token là credential để một bên nhận xác thực chủ thể dưới danh tính Kubernetes ServiceAccount. Workload dùng token để gọi Kubernetes API hoặc một dịch vụ khác được cấu hình tin cậy token đó.

ServiceAccount là đối tượng danh tính; token là một bằng chứng để sử dụng danh tính. Hai khái niệm không đồng nhất. Một ServiceAccount có thể được nhiều Pod sử dụng và có nhiều token với vòng đời hoặc audience khác nhau.

Token được dùng như bearer credential: bên có bản sao token hợp lệ có thể trình nó để xác thực. Vì vậy, không đưa token vào log, ticket, repository hoặc công cụ giải mã trực tuyến. Tài liệu Kubernetes mô tả username dạng system:serviceaccount:<namespace>:<name>. [Kubernetes: Authenticating](https://kubernetes.io/docs/reference/access-authn-authz/authentication/).

Trong PAM, cần quản lý token theo năng lực mà danh tính có thể thực hiện. Token của một workload chỉ đọc cấu hình khác đáng kể với token của controller quản lý tài nguyên toàn cluster. Cùng một cơ chế token nhưng phạm vi tác động có thể rất khác.

Mục tiêu của bài là thiết kế danh tính workload tối thiểu, cấp token đúng mục đích, xử lý rotation và thu hồi, đồng thời tạo bằng chứng không làm lộ credential.

## 2. Phân biệt danh tính, token và quyền

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| ServiceAccount | Workload đang dùng danh tính nào? | orders-config-reader trong namespace pam-lab |
| Token | Bằng chứng xác thực được cấp theo cơ chế nào? | Token được chiếu vào Pod qua projected volume |
| Audience | Token được tạo để bên nhận nào chấp nhận? | Kubernetes API hoặc dịch vụ Reports |
| Role và binding | Danh tính được làm gì tại Kubernetes API? | Đọc một ConfigMap đã chỉ định |
| Chính sách của bên nhận ngoài cluster | Token sau xác thực được ánh xạ thành quyền nào? | Chỉ gửi báo cáo cho ứng dụng Orders |
| Pod và danh tính triển khai | Ai điều khiển mã có thể sử dụng token? | Pipeline phát hành hoặc người được sửa workload |
| Credential nhận tiếp | Token có thể đổi lấy credential khác không? | Credential truy cập một dịch vụ bên ngoài |

Token xác thực được không có nghĩa mọi hành động đều được phép. Ngược lại, token có thời hạn ngắn không có nghĩa permission của danh tính đã hẹp.

Một mô hình phân tích hữu ích:

~~~text
Ai điều khiển workload?
    -> Workload dùng ServiceAccount nào?
    -> Token được cấp cho audience nào?
    -> Bên nhận xác minh ra sao?
    -> Danh tính được ánh xạ thành quyền nào?
    -> Có thể tạo quyền hoặc credential tồn tại tiếp không?
~~~

ServiceAccount cũng không phải tài khoản Linux bên trong container. Thay UID của tiến trình không tự thay đổi ServiceAccount. Image pull credential là một loại thông tin truy cập khác; không coi mọi Secret liên quan đến Pod đều là service account token.

## 3. Token ngắn hạn và token lưu trong Secret

Kubernetes hỗ trợ TokenRequest và projected service account token để cung cấp credential có thời hạn. Cơ chế token Secret dài hạn vẫn có thể hiện diện ở hệ thống cũ hoặc cấu hình được tạo thủ công. Không suy ra loại token chỉ từ việc workload đang chạy trong Kubernetes. [Kubernetes: Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/).

Trong thiết kế PAM, hãy kiểm kê theo vòng đời thực tế:

| Câu hỏi | Token được cấp có thời hạn | Credential tĩnh dài hạn |
|---|---|---|
| Kết thúc theo thời gian? | Cần kiểm tra thời hạn thực tế được cấp | Có thể không có thời hạn phù hợp |
| Ai làm mới? | Kubelet, client hoặc hệ thống cấp phát theo cơ chế đã chọn | Cần quy trình rotation riêng |
| Có gắn với đối tượng cụ thể? | Tùy yêu cầu cấp và loại token | Không được mặc định gắn với Pod |
| Lộ token xử lý thế nào? | Chặn sử dụng và cấp mới, xử lý đối tượng ràng buộc nếu có | Thu hồi credential và đối soát nơi sao chép |
| Có thể dùng ngoài nơi cấp? | Có thể, nếu token còn hợp lệ và tới được bên nhận | Có thể, với cùng điều kiện truy cập |

Bảng là khung đánh giá. Phải xác minh cấu hình thực tế thay vì gắn nhãn “ngắn hạn” theo cảm tính.

Một token được cấp qua TokenRequest không nhất thiết là token gắn với Pod. Khi dùng quy trình cấp ngoài luồng projected volume, cần biết yêu cầu có ràng buộc đối tượng nào, audience và thời hạn thực tế là gì.

Không chuyển một token ngắn hạn thành bí mật dài hạn trong thực hành bằng cách liên tục sao chép nó sang Secret, file build hoặc máy cá nhân mà bỏ qua quản lý nguồn cấp.

## 4. Vòng đời projected token

Trong cơ chế projected token, kubelet lấy token cho Pod và làm mới file khi cần; ứng dụng phải nạp lại token sau rotation. Tắt tự động mount ở ServiceAccount hoặc Pod bằng automountServiceAccountToken; nếu cả hai cùng chỉ định, cấu hình Pod được ưu tiên. [Kubernetes: Configure Service Accounts for Pods](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/).

Từ cơ chế này, thiết kế ứng dụng cần giải quyết hai việc độc lập:

1. Credential mới xuất hiện tại đường dẫn được quản lý.
2. Client thực sự đọc và dùng credential mới.

Nếu ứng dụng chỉ đọc file lúc khởi động rồi giữ chuỗi token mãi trong bộ nhớ, việc file được cập nhật chưa chứng minh các yêu cầu tiếp theo đã dùng token mới.

### Chuỗi vận hành minh họa

~~~mermaid
sequenceDiagram
    participant P as Pod và ứng dụng
    participant K as Kubelet
    participant A as Kubernetes API
    participant D as Dịch vụ nhận token

    K->>A: Yêu cầu token cho Pod và audience
    A-->>K: Token cùng thời hạn
    K-->>P: Cập nhật file projected token
    P->>D: Gọi dịch vụ bằng token hiện tại
    D-->>P: Kết quả sau xác thực và phân quyền
    K->>A: Yêu cầu token thay thế khi cần
    A-->>K: Token mới
    K-->>P: Cập nhật file
    P->>P: Nạp lại credential theo cơ chế client
~~~

Sơ đồ mô tả luồng bình thường, không phải bảo đảm mọi lần làm mới đều thành công. Cần có quan sát lỗi và hành vi đã xác định khi control plane hoặc nguồn cấp không sẵn sàng.

### Không coi rotation là thu hồi token cũ tức thì

Ứng dụng chuyển sang token mới không tự chứng minh mọi bản sao token cũ đã mất hiệu lực. Cần xét thời hạn cũ, ràng buộc đối tượng và cách bên nhận xác minh.

Đây là lý do phải kiểm thử cả khả năng tiếp tục vận hành và giới hạn thời gian sử dụng bản sao cũ.

## 5. Audience: đúng token cho đúng bên nhận

Audience xác định bên nhận dự kiến. Token dành cho một dịch vụ nội bộ không nên được chấp nhận tại một dịch vụ khác chỉ vì cùng nguồn phát hành.

Trong thiết kế minh họa:

~~~text
Token A:
    issuer = cluster được tin cậy
    subject = ServiceAccount Orders
    audience = Reports

Token B:
    issuer = cluster được tin cậy
    subject = ServiceAccount Orders
    audience = Kubernetes API
~~~

Hai token có cùng danh tính chủ thể nhưng mục đích sử dụng khác nhau.

Bên Reports cần kiểm tra token dành cho Reports, rồi áp dụng quyền nghiệp vụ riêng. Kubernetes RBAC không tự trở thành chính sách phân quyền cho Reports.

Audience không phải biện pháp mã hóa. Token vẫn phải được bảo vệ khi lưu, truyền và xử lý. Không dùng việc đặt một audience “khó đoán” thay cho kiểm tra quyền.

### Issuer, subject và scope phải được xét cùng nhau

Chỉ kiểm tra tên ServiceAccount là chưa đủ nếu nhiều cluster hoặc nhiều namespace có thể dùng cùng tên. Bên nhận phải có cấu hình tin cậy đúng nguồn và ánh xạ chủ thể đúng phạm vi.

Ví dụ, orders-reporter tại namespace thử nghiệm không nên tự nhận quyền ghi báo cáo production chỉ vì trùng tên với một danh tính khác.

Đây là yêu cầu thiết kế phân quyền của bên nhận, không phải một thuộc tính tự phát sinh khi token được ký hợp lệ.

## 6. Tắt automount khi workload không cần token

Không phải ứng dụng nào cũng cần gọi Kubernetes API hoặc dùng ServiceAccount token cho dịch vụ khác.

Một ServiceAccount minh họa:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-web
  namespace: pam-lab
automountServiceAccountToken: false
~~~

Trong Pod hoặc Pod template của workload, cần thể hiện rõ ý định:

~~~yaml
spec:
  serviceAccountName: orders-web
  automountServiceAccountToken: false
~~~

Đoạn Pod spec chỉ là phần trích; khi dùng Deployment, nó thuộc Pod template tương ứng.

Tắt automount giảm việc phát credential không cần thiết. Nó không chứng minh container hoàn toàn không có token hoặc không gọi được API bằng credential khác.

Cần kiểm tra thêm:

- Có projected token được khai báo thủ công không?
- Có Secret hoặc file khác chứa credential không?
- Có injector hoặc cơ chế nền tảng thêm credential không?
- Người sửa workload có thể bật lại mount không?
- Có đường liên kết danh tính workload tới dịch vụ bên ngoài không?

Thay một mẫu manifest cũng chưa chứng minh mọi Pod đang chạy đã thay đổi. Kế hoạch triển khai cần xác nhận cấu hình thực tế của workload và các Pod liên quan.

## 7. Ví dụ cấp quyền tối thiểu tại Kubernetes API

Giả sử Orders cần đọc duy nhất ConfigMap orders-runtime-settings trong namespace pam-lab.

Các manifest sau là ví dụ cho môi trường thử nghiệm đã có namespace này:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-config-reader
  namespace: pam-lab
automountServiceAccountToken: false
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: orders-config-reader
  namespace: pam-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["orders-runtime-settings"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: orders-config-reader
  namespace: pam-lab
subjects:
  - kind: ServiceAccount
    name: orders-config-reader
    namespace: pam-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: orders-config-reader
~~~

Role này mô tả một phép cấp hẹp. Nó không tạo quy tắc từ chối để phủ định các role khác: Kubernetes RBAC cộng gộp các phép cho phép. [Kubernetes: Using RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Workload cần Kubernetes API có thể được cấu hình cho phép mount token phù hợp ở Pod, với client sử dụng đúng credential và xác minh TLS của API server. Không bật automount cho mọi workload chỉ để phục vụ một workload cần API.

### Những gì ví dụ chưa chứng minh

- ServiceAccount không có binding khác cấp quyền rộng hơn.
- Một nhóm của ServiceAccount không được cấp thêm quyền.
- Người sửa workload không đổi sang ServiceAccount mạnh hơn.
- Token không bị lộ qua công cụ debug hoặc log.
- Một bên nhận ngoài cluster không ánh xạ danh tính thành quyền khác.

Cần đối soát các điểm này trước khi kết luận quyền hiệu lực chỉ còn đúng một thao tác.

Quyền đọc một ConfigMap cũng phải được xem theo nội dung cấu hình. Không đặt secret vào ConfigMap rồi coi quyền này ít rủi ro chỉ vì tài nguyên không mang loại Secret.

## 8. Ví dụ projected token cho một dịch vụ riêng

Giả sử một reporter chỉ gửi báo cáo đến Reports. Workload không cần dùng Kubernetes API. Ta dùng ServiceAccount khác với reader ở phần trước.

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-reporter
  namespace: pam-lab
automountServiceAccountToken: false
---
apiVersion: v1
kind: Pod
metadata:
  name: orders-reporter-example
  namespace: pam-lab
spec:
  serviceAccountName: orders-reporter
  automountServiceAccountToken: false
  containers:
    - name: reporter
      image: registry.example.internal/pam-lab/orders-reporter:training
      env:
        - name: REPORTS_TOKEN_FILE
          value: /var/run/secrets/reports/report-token
      volumeMounts:
        - name: reports-token
          mountPath: /var/run/secrets/reports
          readOnly: true
  volumes:
    - name: reports-token
      projected:
        sources:
          - serviceAccountToken:
              path: report-token
              audience: https://reports.example.internal
              expirationSeconds: 600
~~~

Image và địa chỉ dịch vụ là giá trị minh họa; phải thay bằng artifact và cấu hình đã được duyệt. Biến REPORTS_TOKEN_FILE là giao ước của ứng dụng ví dụ, không phải biến môi trường Kubernetes tự hiểu.

Projected token hỗ trợ audience, đường dẫn và thời hạn yêu cầu; thời hạn tối thiểu của trường này là 600 giây. Mount projected volume bằng subPath không nhận cập nhật từ nguồn volume. [Kubernetes: Projected Volumes](https://kubernetes.io/docs/concepts/storage/projected-volumes/).

Trong mẫu, ứng dụng đọc token từ file thay vì đặt giá trị token vào biến môi trường. Chỉ container cần token mới được mount volume đó.

Mẫu này chưa tạo Reports, TLS, chính sách tin cậy hay quyền gửi báo cáo. Bên nhận phải được cấu hình riêng. Audience trong token cũng không tự bảo đảm quyền gọi Kubernetes API.

Mount read-only ngăn sửa file qua mount theo quyền đó; nó không ngăn tiến trình đọc rồi sao chép token. Vì vậy, vẫn phải đánh giá người điều khiển mã và quyền debug workload.

## 9. Bên nhận xác minh token như thế nào?

### 9.1. Giải mã không phải xác minh

Đọc payload của một JWT chỉ cho biết nội dung được trình bày. Nó không chứng minh chữ ký, nguồn phát hành, thời hạn hay quyền của chủ thể.

Một bên nhận cần dùng thư viện và cấu hình xác minh phù hợp. Không tự viết bộ xác minh bằng cách tách chuỗi rồi tin các trường bên trong.

Trong thiết kế Reports, những quyết định cần được thể hiện rõ là:

- Nguồn phát hành nào được tin cậy.
- Khóa và thuật toán nào được chấp nhận.
- Audience nào đại diện cho Reports.
- Danh tính nào được gửi loại báo cáo nào.
- Thời gian và trạng thái nào làm yêu cầu không còn hợp lệ.
- Lỗi nguồn xác minh được xử lý ra sao.

Những giá trị này phải đến từ cấu hình tin cậy, không lấy từ token chưa xác minh rồi tự chọn một nguồn tùy ý để tin.

### 9.2. Xác minh ngoại tuyến và trạng thái đối tượng

Bên nhận có thể xác minh JWT bằng khóa công khai. Tuy nhiên, kiểm tra ngoại tuyến không tự biết đối tượng mà token ràng buộc còn tồn tại hay không. Khi cần bảo đảm các ràng buộc vẫn hợp lệ theo control plane, tài liệu Kubernetes hướng dẫn dùng TokenReview. [Kubernetes: Managing Service Accounts](https://kubernetes.io/docs/reference/access-authn-authz/service-accounts-admin/).

Từ đó, thiết kế cần chọn rõ mức bảo đảm:

| Phương án | Đánh đổi cần quản lý |
|---|---|
| Xác minh ngoại tuyến | Ít phụ thuộc control plane khi xử lý yêu cầu, nhưng không tự có trạng thái ràng buộc hiện tại |
| TokenReview | Có đường kiểm tra qua API, cần quản lý danh tính gọi, độ sẵn sàng và cache |
| Kết hợp | Cần định nghĩa điều kiện dùng từng đường và không âm thầm giảm mức bảo đảm khi lỗi |

Không tự chuyển từ TokenReview lỗi sang “chỉ kiểm tra chữ ký rồi cho phép” nếu điều đó vượt chính sách của dịch vụ.

### 9.3. TokenReview phải kiểm tra audience và kết quả

Ví dụ cấu trúc yêu cầu, không phải file để lưu token thật:

~~~yaml
apiVersion: authentication.k8s.io/v1
kind: TokenReview
spec:
  audiences:
    - https://reports.example.internal
  token: "<token chỉ truyền qua đường xử lý bí mật>"
~~~

Client đặt audience cần xác nhận có audience tương thích trong kết quả và kiểm tra trạng thái xác thực. Nếu bỏ audience khỏi yêu cầu, API dùng audience mặc định của Kubernetes API server, không mặc nhiên là Reports. [Kubernetes: TokenReview API](https://kubernetes.io/docs/reference/kubernetes-api/definitions/token-review-v1-authentication/).

Danh tính dùng để gọi TokenReview là danh tính riêng của bên kiểm tra. Không cần cấp quyền kiểm tra token rộng cho mọi ứng dụng chỉ vì chúng trình token.

Một luồng khái niệm cho Reports:

~~~text
nhan_bao_cao(request):
    token = lay_bearer_credential_khong_ghi_log(request)
    ket_qua = kiem_tra_token_voi_nguon_tin_cay(
        token,
        audience_cua_reports
    )

    neu khong the xac minh:
        xu_ly_theo_chinh_sach_loi_da_dinh
        khong coi la da xac thuc

    neu khong xac thuc hoac audience khong phu hop:
        tu choi

    principal = lay_danh_tinh_da_xac_minh(ket_qua)
    neu principal khong duoc gui loai bao cao nay:
        tu choi

    kiem_tra_noi_dung_va_pham_vi_bao_cao()
    ghi_su_kien_khong_chua_token()
    thuc_hien_nghiep_vu()
~~~

Giả mã tách xác thực khỏi quyền nghiệp vụ. Nó chưa phải một triển khai hoàn chỉnh về TLS, cache, giới hạn kích thước, retry hay xử lý lỗi.

## 10. Những quyền có thể tạo đường tiếp cận token

Không chỉ người có quyền đọc Secret mới đáng chú ý. Cần xét ai có thể điều khiển workload và quá trình cấp credential.

Kubernetes chỉ ra quyền tạo workload có thể mở đường sử dụng ServiceAccount trong namespace; quyền create trên serviceaccounts/token cho phép yêu cầu token cho ServiceAccount hiện có. Các khả năng này phải được kiểm soát cùng RBAC và admission phù hợp. [Kubernetes: RBAC Good Practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/).

Từ đó, một bản phân tích PAM nên xem:

| Năng lực | Câu hỏi thiết kế |
|---|---|
| Sửa mã hoặc image | Người sửa có làm workload gửi token ra ngoài được không? |
| Chọn serviceAccountName | Có thể dùng một ServiceAccount mạnh ngoài nhu cầu không? |
| Tạo yêu cầu token | Được yêu cầu cho danh tính nào và audience nào? |
| Debug hoặc thực thi trong container | Ai có thể đọc file và bộ nhớ của ứng dụng? |
| Sửa RBAC | Ai có thể mở rộng quyền của danh tính đang chạy? |
| Sửa chính sách bên nhận | Ai có thể ánh xạ token ít quyền thành quyền nghiệp vụ mạnh? |
| Sửa cấu hình log | Có thể khiến token hoặc header bị ghi ra ngoài không? |
| Quản trị node hoặc runtime | Có đường tiếp cận credential của workload không? |

Đây là các câu hỏi để đánh giá tổ hợp quyền; không khẳng định mọi principal có một thao tác bất kỳ đều thực hiện được toàn bộ chuỗi.

### ServiceAccount mạnh cần một ranh giới sử dụng thực tế

Nếu một ServiceAccount có đặc quyền cao, không nên cho mọi người tạo workload trong cùng phạm vi tùy ý chọn nó.

Ranh giới có thể cần kết hợp:

- Phân tách namespace theo mức tin cậy.
- Admission kiểm soát danh tính được dùng.
- Kiểm soát nguồn image và thay đổi Pod template.
- Quản lý quyền debug.
- Phê duyệt tác vụ và nguồn triển khai.
- Giám sát các thay đổi danh tính runtime.

Cấu hình ServiceAccount hẹp nhưng quy trình triển khai cho phép đổi sang danh tính mạnh hơn thì cam kết least privilege chưa được giữ.

## 11. Thu hồi: bốn vấn đề khác nhau

Khi token bị lộ hoặc workload không còn được tin cậy, cần tách bốn việc:

1. Chặn principal thực hiện hành động nhạy cảm.
2. Làm credential đã lộ không còn được bên nhận chấp nhận.
3. Ngăn nguồn bị ảnh hưởng nhận credential mới.
4. Xử lý thay đổi hoặc credential khác đã tạo trong thời gian bị ảnh hưởng.

Một hành động đơn lẻ thường không giải quyết tất cả.

### 11.1. Đổi RBAC là đổi quyền, không tự là hủy token

Nếu gỡ một RoleBinding, cần kiểm tra permission tương ứng đã mất tại Kubernetes API. Token vẫn có thể xác thực danh tính, và bên nhận ngoài Kubernetes có thể dùng chính sách khác.

Vì vậy, không báo “token đã bị thu hồi” chỉ vì một thao tác quản trị bị từ chối sau khi sửa RBAC.

Cũng cần đối soát những phép cấp khác cho cùng danh tính. Với cơ chế cộng gộp quyền, gỡ một binding không nhất thiết loại bỏ quyền được cấp qua binding khác.

### 11.2. Token ràng buộc đối tượng

Token gắn với Pod có quan hệ vòng đời với đối tượng và UID được ràng buộc. API server kiểm tra các ràng buộc này; việc xóa đối tượng không nên được mô tả là thu hồi tức thì tại mọi bên nhận. Kiểm tra JWT ngoại tuyến vẫn có giới hạn đã nêu. [Kubernetes: Managing Service Accounts](https://kubernetes.io/docs/reference/access-authn-authz/service-accounts-admin/).

Kế hoạch xử lý cần ghi nhận thời điểm yêu cầu xóa, trạng thái đối tượng và quan sát xác thực tại đích. Không thay bằng một kết luận chung “xóa Pod là mọi nơi dừng ngay”.

Nếu controller tạo Pod thay thế, phải bảo đảm nguồn tạo mới đã được xử lý. Nếu không, một nguồn mã còn bị kiểm soát có thể tiếp tục chạy trong Pod mới và nhận credential mới.

### 11.3. Credential tĩnh và các bản sao

Với token lưu trong Secret, phải xác định đúng credential và cơ chế kiểm tra của bên nhận trước khi chọn biện pháp thu hồi.

Không coi xóa một file sao chép trên máy cá nhân là thu hồi credential gốc. Cũng không xóa hàng loạt ServiceAccount hoặc Secret mà chưa đánh giá phụ thuộc của workload.

Nếu token được đưa vào repository hoặc artifact, xử lý nơi phát tán là một phần công việc; phải đồng thời xử lý hiệu lực credential.

### 11.4. Credential được cấp tiếp

Một service account token có thể được đưa tới broker hoặc dịch vụ để nhận credential khác. Khi đó có hai vòng đời:

~~~text
Token Kubernetes
    -> Xác minh tại broker
    -> Credential của hệ thống đích
    -> Phiên hoặc tác vụ tại hệ thống đích
~~~

Làm token nguồn mất hiệu lực không tự chứng minh credential hoặc phiên tại hệ thống đích đã hết hiệu lực. Phải đối soát cơ chế cấp mới, credential đã cấp và quyền tồn dư.

## 12. Rotation và khả năng tiếp tục hoạt động

Rotation phải vừa hạn chế sử dụng credential cũ, vừa bảo đảm workload hợp lệ dùng được credential mới.

Một kế hoạch kiểm chứng nên có:

- Client đang đọc đúng đường dẫn projected volume.
- Client có cơ chế nạp lại credential đã được hiểu và kiểm thử.
- Không sao chép token sang đường dẫn cố định rồi bỏ qua cập nhật.
- Lỗi xác thực được phân biệt với lỗi mạng và lỗi quyền.
- Retry có giới hạn, không tạo vòng lặp lỗi liên tục.
- Không ghi token để debug khi rotation thất bại.
- Bên nhận xử lý khóa tin cậy và thay đổi cấu hình theo thiết kế.

### Kịch bản minh họa

Reporter chạy ổn định ngay sau khi khởi động nhưng ngừng gửi sau một thời gian. Pod không khởi động lại, file token đã được cập nhật.

Có thể ứng dụng đang giữ credential cũ trong bộ nhớ. Cũng có thể lỗi nằm ở nguồn cấp, thời gian hệ thống, audience hoặc chính sách bên nhận.

Cần dùng bằng chứng để phân biệt, chẳng hạn:

- Thời điểm file được cập nhật mà không đọc ra giá trị token.
- Kết quả nạp lại credential của client.
- Mã nguyên nhân được bên nhận trả về an toàn.
- Sự kiện cấp token và trạng thái workload.
- Thời gian của hai hệ thống.

Không sửa bằng cách tạo một token không hết hạn rồi đưa vào biến môi trường chỉ để lỗi tạm biến mất.

## 13. Kiểm thử quyền và kiểm thử token

### 13.1. Kiểm tra authorization không cần in token

Trong cluster thử nghiệm được phép, người có quyền impersonation có thể kiểm tra:

~~~shell
kubectl --context pam-lab -n pam-lab auth can-i get configmaps/orders-runtime-settings --as=system:serviceaccount:pam-lab:orders-config-reader

kubectl --context pam-lab -n pam-lab auth can-i get secrets --as=system:serviceaccount:pam-lab:orders-config-reader
~~~

Dùng --as yêu cầu quyền impersonation phù hợp. Lệnh auth can-i kiểm tra authorization, không chứng minh một token cụ thể còn hợp lệ. [Kubernetes: kubectl auth can-i](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/).

Hai câu hỏi kiểm thử khác nhau:

- Danh tính này có được thực hiện hành động không?
- Credential đang xét có được xác thực đúng với audience và trạng thái yêu cầu không?

Không dùng câu trả lời cho câu thứ nhất thay thế hoàn toàn câu thứ hai.

Nếu có quyền cấp theo nhóm, cần bảo đảm cách kiểm thử thể hiện đúng ngữ cảnh danh tính. Một kết quả dưới ngữ cảnh khác không phải bằng chứng đầy đủ cho workload thực tế.

### 13.2. Ma trận kiểm thử cho reader và reporter

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Reader đọc đúng ConfigMap | Được phép khi credential hợp lệ |
| Reader đọc ConfigMap khác | Bị từ chối nếu không có nguồn cấp bổ sung |
| Reader đọc Secret | Bị từ chối theo thiết kế |
| Reader sửa RBAC | Bị từ chối |
| Reporter gửi báo cáo đúng phạm vi | Được phép sau xác thực và phân quyền nghiệp vụ |
| Token sai audience tại Reports | Bị từ chối |
| Token từ issuer ngoài tập tin cậy | Bị từ chối |
| Token hết thời hạn | Bị từ chối theo cơ chế xác minh |
| JWT bị thay nội dung | Bị từ chối |
| Rotation xảy ra khi ứng dụng chạy | Yêu cầu mới dùng credential mới mà không lộ token |
| Automount tắt với workload không cần credential | Không có mount tự động ngoài ý định |
| Pod bị thay trong kế hoạch thu hồi | Không có nguồn không tin cậy tiếp tục nhận quyền ngoài kế hoạch |
| Gỡ quyền Kubernetes | Thao tác bị gỡ không còn được phép; không nhầm với hủy xác thực |
| Bên nhận xác minh ngoại tuyến | Giới hạn phát hiện thu hồi được đo và ghi nhận |
| Credential đã đổi qua broker | Vòng đời đích được đối soát riêng |

Một timeout hoặc lỗi kết nối không phải bằng chứng quyền đã bị chặn. Cần quan sát phản hồi xác thực, authorization và trạng thái dịch vụ theo ngữ cảnh.

## 14. Audit và bằng chứng không chứa token

Kubernetes audit có các mức thu thập khác nhau; mức Metadata không ghi body request hoặc response. Cần chọn mức phù hợp cho các API xử lý token, thay vì bật ghi body diện rộng. [Kubernetes: Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/).

Lý do thiết kế: yêu cầu TokenReview có token đầu vào và phản hồi cấp token có thể chứa credential. Bằng chứng không được biến thành một nơi phát tán bí mật.

### Chuỗi bằng chứng mong muốn

~~~text
Chủ sở hữu workload
  -> Revision triển khai đã duyệt
  -> Pod và ServiceAccount thực tế
  -> Cấu hình token và nguồn cấp
  -> Bên nhận, audience và quyết định quyền
  -> Kết quả sử dụng
  -> Rotation, thu hồi và đối soát
~~~

Một mẫu hồ sơ vận hành minh họa:

~~~yaml
workload_identity_record:
  application: orders
  environment: training
  cluster_reference: cluster-pam-lab
  namespace: pam-lab
  service_account: orders-reporter
  accountable_owner: team-orders

  purpose: submit-orders-reports
  kubernetes_api_access_required: false
  automount_expected: false

  credential_delivery:
    mechanism: projected-service-account-token
    audience: https://reports.example.internal
    mount_path: /var/run/secrets/reports/report-token
    application_reload_required: true

  receiver:
    trust_policy_reference: REPORTS-TRUST-EX-014
    authorization_policy_reference: REPORTS-AUTHZ-EX-014
    bound_state_validation: "<cơ chế thực tế được chọn>"
    cache_policy_reference: "<chính sách cache nếu có>"

  lifecycle:
    issuance_control_reference: "<điểm kiểm soát cấp token>"
    revocation_plan_reference: REVOKE-EX-014
    downstream_credentials: "<danh mục hoặc none>"

  evidence:
    deployment_reference: DEPLOY-EX-014
    verification_reference: VERIFY-EX-014
    raw_token_storage: forbidden
~~~

Đây là hồ sơ quản trị, không phải tài nguyên Kubernetes. Nó phải phản ánh cấu hình và kiểm chứng thực tế.

Các thông tin hữu ích để đối soát có thể là cluster, namespace, ServiceAccount, Pod UID, revision workload, thời điểm, thao tác và mã kết quả. Chỉ sử dụng những định danh đã xác minh và thực sự có trong nguồn audit của môi trường.

Nếu nhiều Pod dùng chung ServiceAccount, chỉ thấy username chưa đủ để xác định chắc một Pod hoặc người phát hành cụ thể. Cần thêm bằng chứng liên kết, và ghi rõ khi dữ liệu không đủ.

## 15. Tình huống thực tế: reporter làm lộ credential qua log

### Bối cảnh

Reporter của Orders gửi yêu cầu tới Reports. Khi gặp lỗi, một chế độ debug ghi toàn bộ header ra log. Đội phát hiện có bearer credential trong đầu ra.

Một phản ứng chưa đủ là tắt debug rồi kết luận đã xử lý. Credential có thể đã được thu thập, sao chép hoặc sử dụng trong khoảng trước đó.

### Phân tích phạm vi

Đội cần xác định:

1. Pod, ServiceAccount và revision mã nào ghi token.
2. Những audience và bên nhận nào liên quan.
3. Ai hoặc hệ thống nào đọc được log.
4. Token còn hiệu lực theo cơ chế nào.
5. Có nguồn tạo token mới hoặc tạo Pod mới không tin cậy không.
6. Reports có cấp credential hay phiên khác sau xác thực không.
7. Có thao tác ngoài nhu cầu báo cáo trong thời gian bị ảnh hưởng không.

### Phương án xử lý minh họa

Đội ngăn phiên bản lỗi tiếp tục phát tán credential và bảo vệ nguồn log. Họ xử lý quyền tại Reports, nguồn cấp credential và đối tượng ràng buộc theo kế hoạch đã đánh giá.

Nếu dùng broker, đội kiểm tra cả credential đích đã cấp. Họ thay mã debug, xác nhận không còn in header nhạy cảm và thử lại rotation.

Việc xóa log chứa credential phải tuân thủ quy trình bảo toàn bằng chứng và xử lý dữ liệu của tổ chức. Không tự xóa mọi bằng chứng để làm sự cố trông như đã kết thúc.

### Điều kiện đóng sự cố

- Nguồn mã không tin cậy không tiếp tục nhận hoặc phát tán credential.
- Credential bị ảnh hưởng được xử lý theo cơ chế của từng bên nhận.
- Không còn quyền hoặc phiên tồn dư ngoài kế hoạch.
- Tác động dữ liệu được điều tra theo bằng chứng có sẵn.
- Phiên bản sửa vẫn gửi báo cáo hợp lệ và dùng được token mới sau rotation.
- Hồ sơ nêu rõ phạm vi đã kiểm chứng và phần chưa thể kết luận.

## 16. Những lỗi thường gặp

### Dùng một ServiceAccount quản trị cho mọi workload

Khó giới hạn tác động và khó thu hồi riêng một ứng dụng. Cần danh tính theo ranh giới trách nhiệm phù hợp.

### Coi token ở trong Pod là không thể dùng ở nơi khác

Bearer credential bị sao chép phải được xem như một credential đã lộ, với điều kiện hiệu lực và khả năng tiếp cận bên nhận thực tế.

### Đặt giá trị token vào image hoặc manifest

Như vậy credential có thể đi theo artifact, lịch sử thay đổi và hệ thống triển khai. Hãy thiết kế cấp phát ở runtime.

### Chỉ kiểm tra chữ ký

Bên nhận còn cần audience, nguồn tin cậy, vòng đời và quyền nghiệp vụ phù hợp mục đích.

### Gắn TTL ngắn rồi bỏ qua quyền mạnh

Trong thời gian ngắn vẫn có thể tạo thay đổi lớn hoặc credential khác nếu danh tính được phép.

### Chỉ tắt automount trong ServiceAccount

Cần đọc cấu hình Pod thực tế, các mount bổ sung và quyền của người được sửa workload.

### Tin rotation của kubelet thay cho hành vi client

Ứng dụng phải dùng được file mới, không chỉ tiếp tục giữ bản cũ trong bộ nhớ.

### Gỡ RoleBinding rồi báo đã hủy token toàn hệ thống

Quyền Kubernetes, xác thực token và quyền tại bên nhận khác là các đối tượng cần xử lý riêng.

### Sao chép token ra log để phân tích lỗi

Có thể thu thập mã lỗi, thời điểm và định danh phù hợp mà không đưa credential nguyên vẹn vào hệ thống quan sát.

### Dùng token workload làm tài khoản cho con người

Điều đó làm yếu quy trách nhiệm và vòng đời nhân sự. Người quản trị cần danh tính cá nhân cùng cơ chế đặc quyền phù hợp.

## 17. Bài thực hành

Thiết kế hai workload trong namespace thử nghiệm pam-lab:

- Reader chỉ đọc ConfigMap orders-runtime-settings.
- Reporter chỉ gửi báo cáo tới một dịch vụ thử nghiệm, không cần Kubernetes API.

Yêu cầu:

1. Mỗi workload có ServiceAccount riêng và chủ sở hữu.
2. Không dùng cluster-admin để thay cho quyền tác vụ.
3. Token chỉ được mount khi cần và chỉ vào container cần dùng.
4. Reporter có audience được bên nhận xác minh.
5. Client dùng được token sau rotation.
6. Có kế hoạch xử lý khi token bị ghi ra log.
7. Có bằng chứng quyền và vòng đời mà không lưu token thật.

Sản phẩm cần tạo:

- Manifest ServiceAccount, RBAC và phần Pod spec liên quan.
- Bản mô tả ai được chọn ServiceAccount hoặc sửa mã workload.
- Chính sách tin cậy và phân quyền của Reports.
- Ma trận kiểm thử ca thành công, từ chối và sau thu hồi.
- Kết quả thử rotation không chứa credential.
- Sơ đồ credential đích nếu có broker.
- Hồ sơ sự cố giả định và điều kiện kết thúc.

Không cần in hoặc đưa token vào báo cáo học tập. Các thao tác thay workload, xóa đối tượng hoặc đổi quyền chỉ thực hiện trong môi trường và phạm vi đã được phép.

Phương án đạt phải chứng minh được tác vụ hợp lệ vẫn hoạt động, phạm vi ngoài nhu cầu bị giới hạn và kết luận thu hồi phù hợp từng bên nhận.

## 18. Câu hỏi tự kiểm tra

**Vì sao token ngắn hạn vẫn thuộc phạm vi PAM?**

Vì tác động phụ thuộc cả permission của danh tính, khả năng sử dụng credential và những thay đổi có thể tạo trong thời gian còn hiệu lực.

**Một ServiceAccount hẹp có đủ nếu người dùng được đổi workload sang danh tính mạnh hơn không?**

Chưa đủ. Quyền lựa chọn danh tính runtime cũng là một phần đường đặc quyền.

**Vì sao Reports cần chính sách riêng dù token đã được Kubernetes xác minh?**

Xác thực danh tính chưa trả lời danh tính đó được gửi loại báo cáo nào và vào phạm vi nghiệp vụ nào.

**Tại sao cần kiểm thử rotation bằng ứng dụng thật?**

Để xác nhận client nạp và sử dụng credential mới theo thiết kế, thay vì chỉ quan sát file đã thay đổi.

**Một lần auth can-i trả về yes chứng minh điều gì?**

Nó hỗ trợ đánh giá authorization trong ngữ cảnh được dùng. Nó không tự chứng minh token cụ thể, audience hoặc ràng buộc đối tượng đang hợp lệ.

**Thu hồi token nguồn có đủ nếu đã đổi sang credential khác không?**

Không. Cần đối soát credential và phiên đích cùng đường cấp mới.

**Lỗi kết nối sau thu hồi có chứng minh đã chặn truy cập không?**

Không. Cần dữ liệu cho thấy cơ chế xác thực hoặc phân quyền thực sự từ chối theo thiết kế.

**Bằng chứng nào phù hợp hơn việc lưu token thật?**

Các định danh đã xác minh, revision triển khai, cấu hình quyền, thời điểm và kết quả kiểm tra được liên kết đủ để đối soát.
