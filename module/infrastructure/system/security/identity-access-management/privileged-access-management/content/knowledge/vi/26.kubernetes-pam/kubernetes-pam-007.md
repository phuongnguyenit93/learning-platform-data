# Break-glass cluster access

Một cụm Kubernetes có thể vẫn chạy ứng dụng nhưng đội vận hành không còn đăng nhập được để quản trị. Nguyên nhân có thể là IdP ngừng hoạt động, cổng PAM không cấp phiên, một ClusterRoleBinding bị thay đổi hoặc đường mạng tới API server gặp sự cố.

Trong những tình huống đó, việc có sẵn một kubeconfig quyền cao chưa đủ. Người trực còn phải lấy được credential, tới đúng endpoint, xác minh máy chủ, được xác thực, có quyền sửa lỗi và giữ được bằng chứng về những gì đã làm.

Break-glass cluster access là năng lực truy cập khẩn cấp được chuẩn bị để phục hồi quyền kiểm soát cụm khi đường quản trị thông thường không hoạt động hoặc không còn đáng tin. Trong Privileged Access Management (PAM), năng lực này cần có điều kiện kích hoạt, người chịu trách nhiệm, phương tiện truy cập được bảo quản, quyền phù hợp với nhiệm vụ và quy trình kết thúc có kiểm chứng.

Bài học sử dụng mô hình trung lập về nền tảng. Một số chi tiết áp dụng riêng cho cụm dùng kubeadm được đánh dấu rõ; không coi chúng là cấu hình mặc định của mọi dịch vụ Kubernetes.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt mất đường truy cập với hỏng control plane hoặc hỏng ứng dụng.
- Thiết kế đường khẩn cấp đủ độc lập với SSO, PAM, vault và mạng đang được dự phòng.
- Chọn danh tính và phạm vi quyền phục hồi theo đúng loại sự cố.
- Hiểu giới hạn thu hồi của credential, binding và nhóm đặc biệt.
- Thực hiện một phiên khẩn cấp có kiểm soát từ kích hoạt đến đóng quyền.
- Diễn tập cả việc vào được cụm, sửa được lỗi và khôi phục trạng thái bảo quản.

## 2. Phân biệt các loại sự cố

Không nên bắt đầu mọi sự cố bằng cách tìm một credential mạnh hơn. Trước hết cần xác định lớp đang gặp vấn đề.

| Lớp gặp sự cố | Ví dụ | Credential khác có thể giúp gì? |
| --- | --- | --- |
| Kết nối | Không tới được endpoint riêng của API server | Chỉ có ích nếu có đường mạng thay thế được phép |
| Tin cậy TLS | Chứng thư máy chủ không được xác minh hoặc endpoint sai | Cần sửa đúng thông tin tin cậy; không chỉ đổi user |
| Xác thực | SSO không cấp được token hoặc token không được chấp nhận | Có thể dùng cơ chế xác thực dự phòng đã được cấu hình |
| Phân quyền | Principal hợp lệ nhưng thiếu quyền phục hồi | Cần đường quyền hiệu lực ở đúng phạm vi |
| Admission | Thay đổi bị policy hoặc webhook từ chối | Cần quy trình phục hồi đúng kiểm soát đang chặn |
| Control plane | API server hoặc thành phần lưu trạng thái không phục vụ được | Có thể cần phục hồi hạ tầng hoặc hỗ trợ nền tảng |
| Ứng dụng | Một workload lỗi trong khi API vẫn hoạt động | Thường dùng quyền vận hành phù hợp, chưa chắc cần break-glass |

Một lỗi thường biểu hiện qua nhiều thành phần. Ví dụ, gateway xác thực ngừng hoạt động có thể khiến request không tới API server, dù API server vẫn khỏe.

Mã lỗi là manh mối, không phải kết luận đầy đủ. Một phản hồi Forbidden có thể cần phân tích sâu hơn về authorization hoặc admission. Timeout có thể do mạng, endpoint hoặc dịch vụ phía sau.

### 2.1. Giới hạn của break-glass

Credential khẩn cấp không làm API server đang ngừng hoạt động trở lại. Nó cũng không tự khôi phục dữ liệu ứng dụng đã mất.

Nếu quy trình cần truy cập host control plane, backup hoặc hạ tầng cloud, đó là các đặc quyền riêng phải được thiết kế và cấp rõ ràng. Không suy ra quyền truy cập những hệ thống đó chỉ từ việc có nhiệm vụ quản trị Kubernetes.

## 3. Định nghĩa điều kiện kích hoạt

Điều kiện kích hoạt cần gắn với một nhiệm vụ phục hồi cụ thể:

> Đường đăng nhập quản trị thông thường không dùng được hoặc bị nghi không đáng tin; cần thay đổi khẩn cấp trong phạm vi được giao để phục hồi quyền kiểm soát cụm.

Một quyết định kích hoạt nên ghi được:

- Cụm và môi trường bị ảnh hưởng.
- Đường truy cập nào thất bại hoặc không còn đáng tin.
- Mục tiêu phục hồi.
- Người cho phép, người thực hiện và người giám sát theo chính sách.
- Phạm vi thay đổi và thời điểm cần đánh giá lại.
- Kênh ghi nhận nếu hệ thống ticket hoặc phê duyệt chính đang mất.

Break-glass không phải lựa chọn mặc định khi một kỹ sư quên xin quyền, một pipeline gặp lỗi Forbidden hoặc một nhóm muốn triển khai nhanh hơn.

Nếu IdP bị nghi xâm nhập, email hoặc phê duyệt qua chính IdP đó có thể chưa đủ tin cậy. Cần kênh xác minh thay thế đã được chuẩn bị, không tự chọn một tài khoản chat bất kỳ làm căn cứ cấp quyền.

### 3.1. Không dùng quyền khẩn cấp để mở rộng nhiệm vụ

Một phiên được cho phép sửa đường phân quyền không mặc nhiên được đọc Secret của mọi ứng dụng hay thực hiện thay đổi khác đang chờ.

Khi mục tiêu thay đổi, phải đánh giá lại phạm vi và ghi lý do. Giữ rõ ranh giới này giúp người thực hiện tập trung phục hồi và giúp hậu kiểm phân biệt hành động cần thiết với hoạt động ngoài nhiệm vụ.

## 4. Vẽ chuỗi phụ thuộc của đường truy cập

Một đường quản trị bình thường có thể là:

```text
Người quản trị
     |
     v
SSO / IdP
     |
     v
PAM và phê duyệt
     |
     v
Proxy hoặc mạng truy cập quản trị
     |
     v
API server: xác thực → phân quyền → admission
     |
     v
Tài nguyên cần phục hồi
```

Đường khẩn cấp cần được đánh giá theo những thành phần dự kiến có thể hỏng. Không nhất thiết phải độc lập với mọi thứ, nhưng phải độc lập đủ cho từng kịch bản đã công bố.

### 4.1. Những vòng phụ thuộc thường gặp

| Thiết kế dự kiến | Vòng phụ thuộc cần phát hiện |
| --- | --- |
| Credential dự phòng nằm trong vault | Vault chỉ đăng nhập được bằng SSO đang lỗi |
| Dùng bastion thay cho gateway chính | Bastion vẫn cần cùng IdP hoặc cùng đường mạng bị mất |
| Cấp chứng thư ngắn hạn khi khẩn cấp | Dịch vụ ký cần quyền vào chính cluster đang bị khóa |
| Khôi phục bằng GitOps | Controller hoặc repository phụ thuộc vào hệ thống đang lỗi |
| Đọc runbook trong wiki | Wiki yêu cầu SSO không còn hoạt động |
| Nhận mã xác thực qua một thiết bị | Chỉ một người giữ thiết bị và người đó không liên hệ được |
| Gửi cảnh báo sử dụng tài khoản khẩn cấp | Cảnh báo chỉ tới tenant hoặc hệ thống liên lạc đang mất |

Ví dụ một chuỗi không đạt mục tiêu:

```text
Muốn sửa RBAC
  → cần lấy credential khẩn cấp
    → cần truy cập vault
      → cần Pod vault đang chạy trong cluster
        → cần sửa cấu hình truy cập cluster
```

Vấn đề nằm ở khả năng phục hồi, không phải ở việc vault có đủ an toàn trong vận hành bình thường hay không.

### 4.2. Độc lập về endpoint và tin cậy

Nếu đường khẩn cấp đi thẳng tới API server thay vì qua proxy, cần chuẩn bị:

- Endpoint chính xác và đường mạng được phép.
- Cơ chế xác minh chứng thư máy chủ.
- Firewall hoặc quy tắc truy cập tương ứng.
- Khả năng xác thực trực tiếp được API server hỗ trợ.
- Thiết bị quản trị và công cụ cần thiết.

Không để endpoint khẩn cấp mở rộng không kiểm soát chỉ để giảm phụ thuộc. Tính khả dụng và giới hạn nguồn truy cập cần được thiết kế cùng nhau.

Không thêm tùy chọn bỏ kiểm tra TLS vào runbook như cách chữa mọi lỗi kết nối. Làm vậy có thể khiến người trực gửi credential cho một endpoint không được xác minh.

## 5. Chọn danh tính phục hồi

### 5.1. Danh tính dự phòng vẫn đi qua RBAC

Một principal có thể được xác thực độc lập với đường SSO chính nhưng nhận quyền bằng binding thông thường.

Ưu điểm của thiết kế này là có thể quản lý quyền theo phạm vi và gỡ đường cấp quyền phù hợp. Tuy nhiên, nếu chính binding hoặc role phục hồi đã bị xóa, principal có thể xác thực thành công mà vẫn không sửa được lỗi.

Cần kiểm tra đúng tình huống. “Đăng nhập được khi IdP mất” khác với “khôi phục được khi toàn bộ binding quản trị liên quan bị thay đổi”.

### 5.2. Nhóm đặc biệt không tương đương một binding thông thường

Kubernetes cảnh báo rằng `system:masters` vượt kiểm tra RBAC; gỡ RoleBinding hoặc ClusterRoleBinding không thu hồi được đặc quyền của thành viên nhóm này. Vì vậy, không coi đây là một nhóm quản trị thông thường có thể kết thúc chỉ bằng xóa grant. [Thực hành RBAC Kubernetes](https://kubernetes.io/docs/concepts/security/rbac-good-practices/).

Nếu sử dụng khả năng này cho phục hồi cuối cùng, phải hiểu mức độ nhạy cảm của credential và kế hoạch xử lý khi lộ. Một người có thể truy cập credential đó có thể vượt qua đường cấp quyền mà PAM đang quản lý thông thường.

Khả năng vượt authorization không có nghĩa mọi lớp khác cũng tự bị bỏ qua. Vẫn phải đánh giá kết nối, xác thực, admission và khả năng hoạt động của control plane.

### 5.3. Ví dụ riêng cho kubeadm

Tài liệu kubeadm phân biệt `admin.conf` dùng nhóm `kubeadm:cluster-admins` được gắn quyền quản trị với `super-admin.conf` dùng nhóm `system:masters` cho khả năng phục hồi đặc biệt. Những file này cần được bảo vệ và không chia sẻ như cấu hình vận hành thông thường. [Tài liệu tạo cụm bằng kubeadm](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/create-cluster-kubeadm/).

Đây là ví dụ về một phương thức bootstrap cụ thể. Cụm được tạo bằng phiên bản, công cụ hoặc dịch vụ khác có thể có cấu trúc khác. Phải kiểm tra principal và cơ chế thực tế, không suy quyền chỉ từ tên file.

Không phân phát file quản trị bootstrap cho toàn bộ đội để làm phương án dự phòng. Việc tạo nhiều bản sao làm tăng nơi cần bảo vệ và khó biết ai có thể sử dụng credential.

### 5.4. Cụm được quản lý bởi nhà cung cấp

Một dịch vụ managed Kubernetes có thể cung cấp đường quản lý truy cập, khôi phục mapping hoặc hỗ trợ riêng qua control plane cloud.

Cần xác định quyền Kubernetes nào tổ chức tự kiểm soát và quyền nào thuộc nhà cung cấp. Không mặc định có thể đăng nhập host control plane hoặc lấy file kubeadm trên một dịch vụ managed.

Quyền cloud cho phép thay đường truy cập cluster cũng là đặc quyền. Nó cần danh tính, bảo quản credential, điều kiện kích hoạt và audit riêng; không để nó trở thành đường vòng ngoài PAM.

## 6. Credential và vòng đời phục hồi

### 6.1. Credential được chuẩn bị sẵn

Một credential dự phòng có sẵn giảm phụ thuộc vào hệ thống cấp phát lúc sự cố, nhưng tạo khả năng truy cập tồn tại trước khi cần dùng.

Cần quản lý:

- Thời hạn và trạng thái sử dụng được.
- Bên giữ và bên được nhận.
- Số lượng bản sao.
- Nơi lưu, phương tiện giải mã và nhật ký mở.
- Kế hoạch cập nhật khi đổi CA, endpoint hoặc cơ chế xác thực.
- Phương án khi credential hoặc phương tiện bảo quản bị nghi lộ.

Không để credential hết hạn mà không có cảnh báo. Đồng thời, không kéo dài mọi credential vô hạn chỉ để giảm công việc gia hạn.

### 6.2. Credential được cấp khi kích hoạt

Một dịch vụ cấp credential ngắn hạn có thể giảm thời gian credential tồn tại. Nhưng dịch vụ đó phải còn khả dụng trong mô hình lỗi đang dự phòng.

Cần phân tích danh tính người yêu cầu, quyền ký hoặc cấp credential, nguồn phê duyệt và nơi lưu khóa. Nếu thành phần cấp phát cần chính đường IAM hoặc API đang hỏng, nó có thể không cung cấp được khả năng phục hồi mong muốn.

Không chuyển khóa riêng CA xuống máy người trực để họ tự cấp credential tùy ý. Khả năng phát hành danh tính có thể có tác động lớn hơn một credential phục hồi được giới hạn từ trước.

### 6.3. Giới hạn thu hồi chứng thư client

Tài liệu Kubernetes nêu cơ chế xác thực bằng chứng thư client X.509 không hỗ trợ thu hồi riêng lẻ chứng thư theo cách một số hệ thống kỳ vọng; chứng thư đã cấp còn hiệu lực tới khi hết hạn trong cơ chế được mô tả. Phải thiết kế vòng đời và ứng phó theo đặc tính đó. [Xác thực Kubernetes](https://kubernetes.io/docs/reference/access-authn-authz/authentication/#x509-client-certificates).

Gỡ quyền của một principal đi qua RBAC và làm credential không còn xác thực được là hai việc khác nhau. Với credential dùng nhóm đặc biệt vượt RBAC, giới hạn này càng cần được tính từ lúc thiết kế.

Cấp một chứng thư mới không tự làm chứng thư cũ mất tác dụng. Nếu cần thay đổi miền tin cậy để xử lý credential bị lộ, phải đánh giá tác động tới các client hợp lệ và thực hiện theo quy trình phục hồi PKI phù hợp; không xoay CA một cách tùy tiện.

### 6.4. Kubeconfig không phải bản thân quyền

Kubeconfig có thể chứa dữ liệu credential, tham chiếu file hoặc gọi plugin lấy credential.

Một file được gọi là “offline emergency config” nhưng còn dùng plugin cần SSO vẫn phụ thuộc vào SSO. Một file không chứa token thô cũng có thể cho phép truy cập nếu nó tham chiếu private key có sẵn.

Kiểm kê cơ chế đằng sau file và những phụ thuộc liên quan. Không in toàn bộ kubeconfig có secret vào ticket để chứng minh đã chuẩn bị.

### 6.5. MFA và sự thật của đường xác thực

Một cơ chế xác thực client trực tiếp không nhất thiết có bước MFA tương tác cho từng request.

Nếu tổ chức yêu cầu kiểm soát nhiều yếu tố hoặc hai người tham gia, phải xác định chúng được thực thi ở đâu: lúc lấy credential, mở thiết bị, qua cổng độc lập hay qua cơ chế mà nền tảng hỗ trợ. Không ghi rằng API server đã thực thi MFA chỉ vì file được cất trong vault có MFA.

Cơ chế checkout giảm rủi ro lấy credential, nhưng cần đánh giá khả năng credential được sao chép và dùng ngoài cổng sau khi đã nhận.

## 7. Bảo quản và bàn giao

Một phương án bảo quản có thể dùng kho độc lập, vật mang được mã hóa hoặc cơ chế niêm phong phù hợp. Mục tiêu là vừa bảo mật vừa sử dụng được trong điều kiện đã dự kiến.

Các câu hỏi cần trả lời gồm:

- Ai có thể mở và ai có thể biết việc mở?
- Khi người giữ chính vắng mặt, ai có thể thay thế?
- Bản dự phòng có cùng rủi ro địa điểm hoặc thiết bị với bản chính không?
- Phương tiện giải mã có bị lưu cùng dữ liệu theo cách mất kiểm soát không?
- Làm sao kiểm kê mà không làm lộ nội dung?
- Sau sử dụng, credential được đưa về trạng thái bảo quản nào?

### 7.1. Dual control phải có hiệu lực tại lúc sử dụng

Nếu cần hai bên phối hợp, cơ chế phải thực sự ngăn một người tự lấy toàn bộ khả năng truy cập theo thiết kế.

Hai chữ ký được bổ sung sau sự cố không chứng minh có dual control lúc mở credential. Hai phần thông tin nằm trong cùng một kho mà một người mở được cũng không tạo ra sự tách biệt mong muốn.

Cần định nghĩa trước tình huống không liên hệ được người thứ hai. Nếu có đường khẩn cấp đặc biệt, nó phải có thẩm quyền, phạm vi và hậu kiểm rõ ràng, không được tạo ngẫu hứng trong lúc áp lực cao.

### 7.2. Truy vết người cầm credential chung

Nếu phương án cuối cùng dùng một principal được bảo quản chung, ghi rõ người checkout, người sử dụng, thời điểm và hồ sơ sự cố.

Hạn chế sử dụng đồng thời nếu điều đó làm mất khả năng phân biệt thao tác. Khi bàn giao ca trực, ghi trạng thái phiên và người tiếp nhận.

Audit chỉ có một username chung không tự chứng minh người nào đã thao tác. Cần chuỗi bằng chứng bổ sung đáng tin từ nhận credential tới phiên sử dụng.

## 8. Runbook kích hoạt và xác minh

Một runbook hữu ích cần truy cập được khi những hệ thống dự kiến gặp lỗi không hoạt động. Không đặt bản duy nhất trong wiki chỉ mở được qua SSO đang được dự phòng.

### 8.1. Nội dung chuẩn bị từ trước

| Nhóm thông tin | Nội dung cần có |
| --- | --- |
| Đích | Định danh cluster, môi trường, endpoint và chủ sở hữu |
| Mô hình lỗi | Tình huống nào phương án chịu được và phụ thuộc nào vẫn còn |
| Danh tính | Principal phục hồi, cơ chế xác thực và đường nhận quyền |
| Credential | Vị trí bảo quản theo mã kiểm kê, thời hạn và người giữ |
| Thiết bị | Máy quản trị, công cụ, cấu hình mạng và yêu cầu tin cậy |
| Phê duyệt | Người có thẩm quyền, kênh chính và kênh thay thế |
| Nhiệm vụ | Những thao tác phục hồi được phép và giới hạn |
| Bằng chứng | Cách ghi bàn giao, phiên, thay đổi và kết quả |
| Kết thúc | Xử lý quyền, credential, kết nối và cấu hình tồn dư |
| Nhánh thất bại | Khi không tới API hoặc không đủ quyền thì chuyển sang đâu |

Runbook không chứa secret thô chỉ để dễ sử dụng. Nó cần hướng dẫn tới phương tiện bảo quản đúng mà người được ủy quyền có thể nhận trong điều kiện sự cố.

### 8.2. Bước 1: ghi tình huống và giao người

Xác nhận mục tiêu, đích và lý do dùng break-glass. Chỉ định người thực hiện cùng vai trò giám sát hoặc phê duyệt theo mức tác động.

Nếu chưa biết đầy đủ nguyên nhân, ghi giả thuyết hiện tại và giới hạn hành động. Tránh quyết định mơ hồ như “vào bằng tài khoản mạnh nhất rồi kiểm tra sau”.

### 8.3. Bước 2: chuẩn bị thiết bị và nhận credential

Dùng thiết bị đủ tin cậy. Nếu nghi máy trạm hoặc IdP bị xâm nhập, không tự động tái sử dụng cùng môi trường đó để cầm credential phục hồi.

Kiểm tra tình trạng phương tiện bảo quản, thời hạn credential và thông tin cluster. Nếu niêm phong có dấu hiệu bất thường hoặc có bản sao không được kiểm kê, chuyển sang nhánh nghi lộ credential.

Ghi việc bàn giao bằng mã nhận diện phương tiện, không ghi password, token hoặc private key.

### 8.4. Bước 3: xác minh đúng đích

Trước thao tác có tác động:

- Xác nhận kubeconfig và context đang dùng.
- Xác minh endpoint và tin cậy máy chủ theo cấu hình đã chuẩn bị.
- Xác nhận danh tính được API nhận diện bằng cơ chế hỗ trợ.
- Xác nhận cluster và phạm vi tài nguyên.
- Kiểm tra khả năng audit và ghi nhận trạng thái hiện tại.
- Đối chiếu quyền cần cho thay đổi dự kiến.

Tên context phía client không tự là định danh đáng tin của cluster. Một context mang tên production vẫn có thể trỏ sai endpoint nếu file bị sửa.

### 8.5. Ví dụ kiểm tra trên môi trường học tập

Các lệnh dưới đây chỉ mô tả kiểm tra, không phải quy trình cấp hoặc phá bỏ quyền:

```bash
kubectl --kubeconfig=./emergency-lab.config --context=lab-recovery config current-context
kubectl --kubeconfig=./emergency-lab.config --context=lab-recovery auth can-i get clusterrolebindings.rbac.authorization.k8s.io
kubectl --kubeconfig=./emergency-lab.config --context=lab-recovery auth can-i patch clusterrolebindings.rbac.authorization.k8s.io
kubectl --kubeconfig=./emergency-lab.config --context=lab-recovery get clusterrolebinding lab-recovery-target -o yaml
```

Đối tượng `lab-recovery-target` phải là đối tượng thử nghiệm đã được chuẩn bị; không suy ra một binding có tên tương tự tồn tại trên cụm thật.

`can-i` kiểm tra khả năng authorization theo request. Kết quả cho phép chưa chứng minh admission sẽ chấp nhận một bản sửa cụ thể hoặc mọi bước của tác vụ sẽ thành công. [Tham chiếu kiểm tra quyền](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/).

Không in nội dung credential thô để xác nhận danh tính. Đọc nhãn user trong kubeconfig cũng không thay thế xác minh principal mà API thực sự nhận diện.

## 9. Thực hiện thay đổi phục hồi

### 9.1. Đọc trạng thái trước, sửa phần cần thiết

Thu thập cấu hình và bằng chứng liên quan trong phạm vi được giao. Đối chiếu với nguồn cấu hình được quản trị và đáng tin trong tình huống hiện tại.

Một manifest nhận qua kênh không xác thực không trở thành bản phục hồi an toàn chỉ vì có người gọi nó là “bản cuối cùng còn chạy”.

Ví dụ, nếu một binding của nhóm trực bị xóa, có thể cần khôi phục đúng binding đó. Không nhất thiết phải cấp quyền quản trị cho mọi thành viên hoặc mọi ServiceAccount để vượt lỗi.

### 9.2. Phân biệt thay đổi khẩn cấp và nguồn khai báo

Trong cụm quản lý bằng GitOps, thay đổi trực tiếp có thể bị hoàn nguyên. Ngược lại, một cấu hình sai trong repository có thể liên tục được áp dụng lại.

Runbook cần xác định cách phối hợp với controller và người quản lý nguồn cấu hình:

1. Xác định đối tượng có được reconcile từ nguồn ngoài không.
2. Ghi thay đổi khẩn cấp và lý do.
3. Thực hiện biện pháp kiểm soát reconcile phù hợp nếu cần và đã được phép.
4. Sửa nguồn mong muốn để trạng thái đúng được duy trì.
5. Khôi phục hoạt động tự động và kiểm tra chênh lệch.

Không tắt toàn bộ tự động hóa của cluster chỉ vì một đối tượng đang được reconcile. Mọi tạm dừng cần phạm vi và điều kiện kết thúc.

### 9.3. Khi admission chặn thao tác

Authorization là một bước trong chuỗi xử lý request, còn admission áp dụng sau đó. Một credential có quyền authorization rất cao không bảo đảm mọi thay đổi đều vượt qua policy hoặc webhook. [Mô hình authorization](https://kubernetes.io/docs/reference/access-authn-authz/authorization/).

Nếu sự cố nằm ở admission, cần nhánh phục hồi được thiết kế cho chính lớp đó. Xác định policy hay webhook nào đang chặn, hành động nào cần sửa và quyền nào thực sự đủ.

Không mặc định xóa mọi webhook, nới toàn bộ Pod security hoặc tắt audit để “mở đường”. Những thay đổi đó có thể tạo thêm rủi ro và ảnh hưởng nhiều workload không liên quan.

### 9.4. Khi API server không phục vụ

Nếu lỗi nằm ở control plane hoặc nơi lưu trạng thái, việc gửi lại cùng request bằng credential khác có thể không có ích.

Với cụm tự quản lý, cần chuyển sang runbook hạ tầng, host hoặc phục hồi trạng thái tương ứng, có thẩm quyền riêng. Với dịch vụ managed, có thể cần thao tác control plane cloud hoặc hỗ trợ của nhà cung cấp theo thiết kế.

Bài học này không cung cấp một lệnh chung để sửa trực tiếp dữ liệu điều khiển. Can thiệp vào trạng thái nền tảng cần quy trình riêng, vì sai thao tác có thể làm hỏng tính nhất quán hoặc mất dữ liệu.

### 9.5. Xác nhận phục hồi bằng đường bình thường

Sau thay đổi, kiểm tra một lần đăng nhập mới qua đường vận hành thông thường và thực hiện một nhiệm vụ đại diện được phép.

Một phiên cũ còn tồn tại không chứng minh lần đăng nhập mới đã hoạt động. Ngược lại, đăng nhập thành công nhưng không có quyền cần thiết vẫn chưa đạt mục tiêu.

Nếu nền tảng có độ trễ đồng bộ hoặc áp dụng cấu hình, ghi nhận và kiểm tra theo hành vi thực tế. Không liên tục mở rộng quyền chỉ vì chưa chờ đúng thời điểm kiểm tra.

## 10. Bằng chứng và giám sát

Mục tiêu là nối được toàn bộ chuỗi:

```text
Sự cố và thẩm quyền
        |
        v
Người nhận credential
        |
        v
Danh tính / phiên tới API
        |
        v
Đối tượng và thay đổi thực tế
        |
        v
Kết quả phục hồi
        |
        v
Thu hồi, bàn giao và hậu kiểm
```

### 10.1. Những gì cần ghi

| Nhóm | Ví dụ bằng chứng |
| --- | --- |
| Kích hoạt | Lý do, cluster, phạm vi, người cho phép |
| Bàn giao | Người nhận, thời điểm, mã phương tiện |
| Xác thực | Principal, kết quả, nguồn truy cập phù hợp |
| Hoạt động | Verb, loại tài nguyên, namespace, tên đối tượng, kết quả |
| Thay đổi | Tham chiếu cấu hình trước và sau được bảo vệ |
| Quyền phát sinh | Binding, principal, credential hoặc trust được tạo |
| Kết thúc | Thời điểm dừng, quyền bị gỡ, credential được xử lý |
| Hậu kiểm | Hành động ngoài dự kiến, khoảng trống bằng chứng, việc cần sửa |

Không sao chép nguyên Secret, token hoặc private key vào hồ sơ. Khi nội dung thay đổi chứa dữ liệu nhạy cảm, lưu theo phạm vi truy cập phù hợp và dùng tham chiếu thay cho phát tán rộng.

### 10.2. Audit API có phạm vi cụ thể

Audit API không mặc định ghi mọi lệnh bên trong container hoặc mọi thao tác ở host. Mức ghi metadata cũng khác với mức ghi nội dung request hay response. Cần chọn policy phù hợp và biết dữ liệu nhạy cảm nào có thể xuất hiện trong bản ghi. [Audit Kubernetes](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/).

Nếu phiên khẩn cấp có bước vào host hoặc hệ thống cloud, cần bằng chứng tại những lớp đó. Một audit event tạo Pod không tự cho biết toàn bộ hoạt động xảy ra sau đó trong Pod.

### 10.3. Đừng để người quản trị tự xóa toàn bộ bằng chứng

Đánh giá quyền của principal khẩn cấp đối với collector, cấu hình audit, kho lưu, khóa mã hóa và hệ thống quản trị đích.

Một nơi lưu ngoài cluster có thể giúp giảm phụ thuộc, nhưng không tự độc lập nếu cùng principal còn có quyền cloud để xóa nó. Cần mô tả mức tách biệt thực tế thay vì chỉ vẽ hai hộp khác nhau.

Theo dõi việc sử dụng credential khẩn cấp, thay đổi credential, phương tiện xác thực mới và các thay đổi làm giảm audit. Cảnh báo cần đến được người có trách nhiệm trong chính tình huống đường chính đang lỗi.

### 10.4. Khi mất audit

Runbook cần có hành vi được định nghĩa trước: thao tác nào phải chờ, thao tác nào có thể tiếp tục trong phạm vi được phép và cách ghi bằng chứng tạm thời.

Có thể cần người giám sát hoặc bản ghi bổ sung được bảo vệ. Nhưng bản ghi bổ sung không tự thay thế hoàn toàn bằng chứng tại nền tảng.

Khi đường audit được phục hồi, đối chiếu khoảng thời gian bị thiếu và những thay đổi đã thực hiện. Không đánh dấu bằng chứng đầy đủ nếu chỉ có ghi chép một phía mà chưa xác minh được.

## 11. Kết thúc phiên khẩn cấp

Kết thúc không chỉ là đóng terminal. Cần khôi phục cả quyền và trạng thái bảo quản.

### 11.1. Kiểm kê mọi khả năng đã phát sinh

Trong phiên có thể đã tạo hoặc thay đổi:

- Role, binding và nhóm nhận quyền.
- ServiceAccount hoặc credential liên quan.
- Chứng thư hay trust xác thực.
- Workload dùng danh tính khác.
- Job hoặc controller tiếp tục chạy.
- Kết nối tương tác và luồng theo dõi.
- File credential, cache hoặc bản sao cấu hình trên thiết bị.
- Bản sao dữ liệu được lấy phục vụ điều tra.

Việc thu hồi principal ban đầu không tự thu hồi mọi khả năng mới đã được tạo.

### 11.2. Thu hồi theo đúng đường quyền

Nếu principal được cấp qua RBAC, xử lý grant ở nguồn quản lý đúng và kiểm tra các đường còn lại. Quyền từ nhóm hoặc binding khác có thể vẫn tồn tại.

Nếu credential có khả năng vượt RBAC, không báo cáo đã thu hồi chỉ vì xóa ClusterRoleBinding. Phải thực hiện kế hoạch xử lý credential và miền tin cậy phù hợp với thiết kế.

Ghi rõ những giới hạn kỹ thuật còn tồn tại, chẳng hạn credential cũ vẫn có thể xác thực tới khi hết hạn. Giới hạn cần được quản lý và theo dõi, không che bằng một trạng thái “đã đóng”.

### 11.3. Phiên dài hạn và tác vụ đã chạy

Một request mới bị từ chối không chứng minh kết nối đã mở hoặc job đã được tạo cũng chấm dứt.

Cần xử lý phiên tương tác, luồng đang theo dõi và tiến trình còn hoạt động theo cơ chế nền tảng hỗ trợ. Đánh giá tác động trước khi dừng những tác vụ có thể đang phục hồi hệ thống.

### 11.4. Luân chuyển và bàn giao

Password hoặc token tĩnh đã được tiết lộ có thể cần thay theo quy trình. Với chứng thư client, cấp bản mới không làm bản cũ tự mất hiệu lực. Phương tiện xác thực phần cứng cũng không nhất thiết phải thay sau mỗi lần dùng hợp lệ; cần xử lý theo việc mất, nghi lộ hoặc thay người giữ.

Sau xử lý:

1. Cập nhật bản bảo quản và kiểm kê.
2. Hạn chế hoặc dọn bản sao cục bộ theo chính sách.
3. Kiểm tra đường khẩn cấp vẫn sử dụng được bằng phương thức phù hợp.
4. Đưa phương tiện về trạng thái bảo quản.
5. Xác nhận người chịu trách nhiệm cho những giới hạn hoặc việc còn lại.

Không kết thúc sự cố với một bản niêm phong chứa credential đã hết tác dụng.

### 11.5. Quyền tồn dư và cấu hình cuối cùng

Đối chiếu trạng thái cuối với thay đổi được phép. Đặc biệt tìm principal mới, binding rộng, key ngoài kiểm kê, ngoại lệ policy hoặc cấu hình GitOps có thể tái tạo đường truy cập.

Khôi phục trạng thái audit và tự động hóa đã tạm thay đổi. Chứng minh đường bình thường hoạt động và đường khẩn cấp đã quay lại mục đích dự phòng.

## 12. Hai tình huống minh họa

### 12.1. IdP mất nhưng API server còn hoạt động

Một cluster sử dụng SSO qua IdP doanh nghiệp. IdP ngừng cấp token mới; đội trực không đăng nhập được qua PAM.

Đường dự phòng đã chuẩn bị có cơ chế xác thực độc lập, binding phục hồi còn nguyên, endpoint và mạng truy cập khả dụng. Credential được bảo quản ngoài vòng phụ thuộc IdP.

Người trực thực hiện:

1. Xác nhận đây là lỗi đường danh tính, không phải API ngừng hoạt động.
2. Kích hoạt và nhận credential theo thẩm quyền.
3. Vào đúng cluster, kiểm tra principal và quyền.
4. Thực hiện nhiệm vụ vận hành khẩn cấp được duyệt hoặc hỗ trợ phục hồi đường truy cập.
5. Xác nhận đăng nhập mới qua đường bình thường khi IdP được phục hồi.
6. Đóng quyền, xử lý credential và đối chiếu audit.

Không cần mặc định sửa RBAC nếu RBAC không có vấn đề. Cũng không tạo tài khoản quản trị thường trực mới cho cả đội chỉ để chờ IdP hoạt động lại.

### 12.2. Binding quản trị bị thay đổi sai

Trong một cluster tự quản lý, thay đổi cấu hình làm nhóm quản trị mất quyền sửa RBAC. Xác thực vẫn thành công nhưng thao tác cần thiết bị từ chối.

Một principal dự phòng dùng cùng binding đã bị xóa không giải quyết được tình huống. Phương án phải có khả năng phục hồi quyền ở lớp thích hợp đã được chuẩn bị từ trước.

Đội trực:

1. Xác định binding hoặc nguồn cấu hình gây mất quyền.
2. Dùng đường phục hồi được phép cho tình huống RBAC.
3. Khôi phục cấu hình cụ thể từ nguồn đáng tin.
4. Đồng bộ nguồn GitOps nếu có.
5. Kiểm tra người quản trị đăng nhập mới và có đúng quyền.
6. Kết thúc đường phục hồi theo đặc tính credential đã dùng.
7. Điều tra vì sao thay đổi có thể làm mất đường quản trị.

Điểm khác biệt giữa hai tình huống là lớp lỗi và khả năng phục hồi cần thiết. Một credential độc lập với IdP chưa chắc độc lập với lỗi RBAC.

## 13. Diễn tập theo mô hình lỗi

Một bài diễn tập cần nêu giả định: thành phần nào không dùng được, thành phần nào còn hoạt động và nhiệm vụ nào phải hoàn thành.

### 13.1. Các lớp kiểm chứng

| Lớp | Kết quả cần chứng minh |
| --- | --- |
| Con người | Liên hệ được người có thẩm quyền và người giữ dự phòng |
| Tài liệu | Runbook còn đúng và truy cập được khi hệ thống chính mất |
| Phương tiện | Mở đúng bản bảo quản mà không làm lộ credential |
| Mạng và TLS | Tới đúng API endpoint, xác minh máy chủ đúng cách |
| Xác thực | Principal dự phòng được chấp nhận theo cơ chế thiết kế |
| Quyền | Thực hiện được hành động phục hồi đại diện |
| Bằng chứng | Có cảnh báo và audit nối được với người thực hiện |
| Kết thúc | Xử lý quyền, credential và trạng thái bảo quản đầy đủ |

### 13.2. Bộ tình huống cần cân nhắc

- IdP không dùng được nhưng control plane khỏe.
- PAM hoặc vault chính không truy cập được.
- Người giữ chính vắng mặt hoặc phương tiện xác thực chính mất.
- Endpoint, CA hoặc thời hạn credential đã thay đổi.
- Binding quản trị bị xóa trong môi trường thử nghiệm.
- Admission chặn thay đổi cần thiết.
- API server không phục vụ để kiểm tra nhánh chuyển cấp.
- Kênh audit hoặc cảnh báo chính không hoạt động.
- GitOps tạo lại cấu hình sai.
- Một credential cũ bị thử dùng sau khi đóng sự cố.

Mỗi tình huống có thể cần cách thử khác nhau. Không nhất thiết phải gây lỗi thật cho toàn bộ production để kiểm tra khả năng chịu đựng.

### 13.3. Đo cả khả năng phục hồi và chất lượng kiểm soát

Ghi thời gian nhận phương tiện, tới API, xác minh quyền, thực hiện hành động thử và đóng quyền.

Đồng thời ghi thao tác ngoài runbook, secret xuất hiện nhầm trong bản ghi, phụ thuộc bất ngờ và quyền tồn dư. Truy cập nhanh nhưng sai cluster hoặc không đóng được quyền không phải một bài diễn tập đạt mục tiêu.

Lịch diễn tập cần phù hợp rủi ro và mức thay đổi. Kiểm tra lại sau những thay đổi ảnh hưởng IdP, PAM, endpoint, CA, phiên bản, người giữ, mạng hoặc hệ thống quản trị cấu hình.

## 14. Những sai lầm cần tránh

### 14.1. Dùng một file admin cho mọi người

Nhiều bản sao làm tăng khả năng lộ credential và giảm khả năng quy trách nhiệm. Người dùng thường ngày cần danh tính riêng; file phục hồi được quản trị theo mục đích riêng.

### 14.2. Cấp quyền khi cần nhưng thành phần cấp quyền đang hỏng

Một phương án JIT phải có điểm khởi đầu khả dụng. Nếu mọi thao tác cấp credential đều cần chính API hoặc IdP đang mất, chưa có đường phục hồi cho mô hình lỗi đó.

### 14.3. Chỉ diễn tập đăng nhập

Đăng nhập được nhưng không sửa được quyền hoặc cấu hình mục tiêu vẫn chưa đủ. Phải thử một hành động phục hồi đại diện trong phạm vi được phép.

### 14.4. Bỏ TLS, admission hoặc audit để đơn giản hóa

Đó là những thay đổi có phạm vi và rủi ro riêng. Chỉ xử lý lớp thực sự gặp lỗi bằng nhánh được thiết kế, không coi khẩn cấp là quyền tắt mọi kiểm soát.

### 14.5. Xóa binding rồi kết luận credential đã bị vô hiệu

Binding, cơ chế xác thực và nhóm đặc biệt có hành vi khác nhau. Cần chứng minh những khả năng nào đã mất và những khả năng nào còn tồn tại.

### 14.6. Tạo chứng thư mới rồi quên bản cũ

Cần hiểu hiệu lực của credential cũ và các bản sao. Luân chuyển chỉ đạt mục tiêu khi trạng thái sau thay đổi được xác minh theo cơ chế thực tế.

### 14.7. Bản bảo quản lỗi thời

Runbook đúng nhưng endpoint cũ, credential hết hạn hoặc người giữ đã nghỉ vẫn có thể làm phương án thất bại. Kiểm kê và cập nhật là hoạt động thường xuyên của năng lực phục hồi.

## 15. Bài tập áp dụng

Bạn quản lý hai cluster: một cụm tự quản lý và một cụm managed. Cả hai dùng cùng IdP, cùng PAM và một vault nằm trong cụm tự quản lý.

Hãy thiết kế cho hai tình huống:

- IdP không cấp được token mới.
- Một thay đổi RBAC làm đội platform mất quyền sửa binding trên cụm tự quản lý.

Với từng tình huống, trả lời:

1. Những thành phần nào được giả định còn hoạt động?
2. Đường dự phòng có vòng phụ thuộc nào?
3. Principal nào được dùng và nhận quyền qua cơ chế nào?
4. Credential được cấp trước hay khi kích hoạt, và vì sao?
5. Có giới hạn thu hồi nào cần quản lý?
6. Người trực nhận phương tiện, xác minh đích và thực hiện thay đổi thế nào?
7. Bằng chứng nào liên kết được toàn bộ phiên?
8. Đóng quyền và khôi phục phương tiện bảo quản ra sao?
9. Diễn tập an toàn nào chứng minh phương án?

Một đáp án tốt phân biệt rõ cụm managed với cụm tự quản lý và không giả định cùng một file kubeconfig giải quyết mọi lớp lỗi.

## 16. Tiêu chí hoàn thành

Break-glass cluster access đạt mục tiêu khi tổ chức chứng minh được:

- Điều kiện kích hoạt, mục tiêu và thẩm quyền rõ ràng.
- Đường truy cập chịu được những lỗi mà nó được thiết kế để dự phòng.
- Endpoint, tin cậy máy chủ, mạng và thiết bị đã được chuẩn bị.
- Principal có quyền thực tế để thực hiện nhiệm vụ phục hồi.
- Credential, khóa cấp phát và phương tiện xác thực được bảo quản theo vòng đời.
- Những giới hạn của binding, nhóm đặc biệt và thu hồi credential được hiểu đúng.
- Hoạt động có bằng chứng từ kích hoạt đến kết thúc.
- Quyền, phiên, credential và thay đổi tồn dư được kiểm tra sau sử dụng.
- Runbook và bản bảo quản được cập nhật, diễn tập theo rủi ro.

Truy cập khẩn cấp vào cluster là một đường phục hồi có quản trị. Nó cần đủ mạnh để sửa lỗi đã dự kiến, đủ độc lập để không thất bại cùng đường chính và đủ rõ ràng để người dùng không giữ đặc quyền ngoài nhiệm vụ sau khi hệ thống đã hoạt động trở lại.

