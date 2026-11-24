# Thông tin xác thực ngắn hạn và luân chuyển quyền truy cập

Máy ảo, container và workload chạy trên đám mây thường cần gọi API để đọc object, ghi log, truy cập database, lấy cấu hình hoặc quản lý tài nguyên. Để thực hiện các thao tác đó, workload phải chứng minh danh tính và được cấp quyền phù hợp. Nếu lưu access key hoặc mật khẩu dài hạn trực tiếp trên máy, trong image hay trong mã nguồn, thông tin xác thực có thể bị sao chép và tiếp tục được sử dụng ngay cả sau khi máy hoặc ứng dụng đã thay đổi.

**Thông tin xác thực ngắn hạn (short-lived credentials)** giúp giảm khoảng thời gian một credential bị lộ có thể bị khai thác. Workload nhận token hoặc credential có thời hạn từ một hệ thống cấp quyền tin cậy, sử dụng chúng trong phạm vi cần thiết rồi lấy bộ mới khi gần hết hạn. **Luân chuyển quyền truy cập (credential and access rotation)** là quy trình thay thế, làm mới hoặc thu hồi thông tin xác thực và quyền đã cấp để duy trì truy cập hợp lệ, đồng thời giới hạn quyền cũ.

Trong **CLOUD_CORE_SERVICES_COMPUTE**, danh tính workload là một phần của cấu hình bảo mật cho VM, container và serverless. Cần thiết kế đồng thời danh tính, cơ chế cấp token, thời hạn, phạm vi quyền, cách làm mới, xử lý lỗi và audit. Mục tiêu là để workload có thể hoạt động liên tục mà không phải nhúng bí mật dài hạn vào image hoặc cấu hình máy.

## 1. Danh tính, xác thực và phân quyền

Ba khái niệm cần được tách biệt:

- **Danh tính (identity):** đại diện cho một người, máy ảo, ứng dụng, service account hoặc workload.
- **Xác thực (authentication):** kiểm tra chủ thể có thực sự sở hữu danh tính đã khai báo hay không.
- **Phân quyền (authorization):** quyết định danh tính đã xác thực được phép thực hiện hành động nào trên tài nguyên nào.

Ví dụ, một VM có thể xác thực với nền tảng bằng managed identity. Sau khi xác thực, VM nhận token dành cho dịch vụ lưu trữ. Quyền đọc một bucket hoặc container cụ thể được quyết định bởi IAM/RBAC policy gắn với danh tính đó.

Không nên xem token hợp lệ là đồng nghĩa với quyền truy cập không giới hạn. Token chỉ chứng minh hoặc mang theo thông tin về danh tính và phạm vi quyền theo cơ chế của hệ thống. Dịch vụ đích vẫn cần kiểm tra audience, issuer, expiry, scope/role và policy.

### 1.1. Danh tính người dùng và danh tính workload

Danh tính người dùng đại diện cho con người đăng nhập bằng mật khẩu, MFA, khóa bảo mật hoặc phương thức xác thực tương ứng. Danh tính workload đại diện cho phần mềm đang chạy và thường cần xác thực tự động, không có người nhập mật khẩu mỗi lần gọi API.

Ví dụ về danh tính workload:

- Instance role hoặc instance profile gắn với VM.
- Managed identity gắn với máy ảo hoặc dịch vụ ứng dụng.
- Service account được workload sử dụng trong nền tảng cloud.
- Kubernetes ServiceAccount gắn với Pod.
- Danh tính liên kết qua OIDC federation cho pipeline CI/CD.

Mỗi workload nên có danh tính riêng theo ứng dụng, môi trường hoặc ranh giới tin cậy. Dùng chung một service account quyền rộng cho nhiều ứng dụng làm giảm khả năng cô lập và khiến việc điều tra credential bị lộ khó hơn.

### 1.2. Phân biệt secret dài hạn và credential ngắn hạn

| Đặc điểm | Secret/credential dài hạn | Credential ngắn hạn |
| --- | --- | --- |
| Thời hạn | Có thể tồn tại nhiều tháng hoặc đến khi bị thu hồi | Có thời điểm hết hạn rõ ràng |
| Cách cấp | Tạo thủ công hoặc từ hệ thống quản lý secret | Cấp động từ identity provider hoặc security token service |
| Rủi ro khi bị lộ | Có thể bị dùng lâu nếu không phát hiện và thu hồi | Cửa sổ sử dụng bị giới hạn bởi expiry và policy |
| Vận hành | Cần lưu trữ, phân phối và luân chuyển định kỳ | Cần cơ chế lấy mới và xử lý token hết hạn |
| Ví dụ | API key tĩnh, access key, mật khẩu service account | STS session, OAuth access token, managed identity token |

Credential ngắn hạn vẫn là bí mật trong thời gian còn hiệu lực. Kẻ tấn công có thể sử dụng token bị đánh cắp cho đến khi token hết hạn hoặc bị thu hồi theo cơ chế hỗ trợ. Vì vậy vẫn cần bảo vệ token trong bộ nhớ, log, file tạm, process environment và đường truyền.

## 2. Vì sao nên ưu tiên credential ngắn hạn?

Credential dài hạn thường khó quản lý khi có nhiều VM, image, container và pipeline. Một khóa được đưa vào image có thể xuất hiện trên mọi máy tạo từ image đó. Nếu khóa bị lộ, đội vận hành phải xác định phạm vi phân phối, thay khóa và cập nhật mọi nơi đang dùng khóa cũ.

Credential ngắn hạn giảm rủi ro theo một số cách:

- **Giới hạn thời gian:** token tự hết hạn sau khoảng thời gian được cấp.
- **Cấp theo nhu cầu:** workload chỉ lấy credential khi cần và cho dịch vụ đích cụ thể.
- **Giảm phân phối bí mật:** không cần lưu access key dài hạn trong image hoặc repository.
- **Ràng buộc ngữ cảnh:** token có thể gắn với audience, scope, role, session tag hoặc danh tính workload.
- **Dễ kiểm toán:** hệ thống có thể ghi nhận danh tính, thời điểm cấp và hành động được thực hiện.
- **Thu hồi quyền:** thay đổi policy hoặc vô hiệu hóa danh tính giúp ngăn các lần cấp token mới; mức độ ảnh hưởng đến token đang tồn tại phụ thuộc cơ chế kiểm tra và thu hồi của provider.

Short-lived credential không thay thế least privilege, network control, encryption hay monitoring. Nó là một lớp trong thiết kế bảo mật tổng thể.

## 3. Các cơ chế cấp credential ngắn hạn

### 3.1. Instance role hoặc managed identity

Với VM, nền tảng có thể gắn một danh tính vào máy. Workload yêu cầu credential từ dịch vụ metadata hoặc identity endpoint do nền tảng cung cấp. Endpoint xác định VM dựa trên môi trường thực thi và trả token hoặc credential tạm thời.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng trên VM
    participant IMDS as Metadata / Identity endpoint
    participant STS as Identity service
    participant API as Dịch vụ đích
    App->>IMDS: Yêu cầu token cho audience/resource
    IMDS->>STS: Xác minh danh tính VM và policy
    STS-->>IMDS: Token ngắn hạn
    IMDS-->>App: Trả token và expiry
    App->>API: Gọi API kèm token
    API->>API: Kiểm tra token và quyền
    API-->>App: Kết quả
    Note over App,API: SDK làm mới token trước khi hết hạn
~~~

Ví dụ mô hình của các nền tảng:

- AWS EC2 dùng IAM role gắn với instance profile; ứng dụng lấy temporary security credentials qua instance metadata service. Nên yêu cầu IMDSv2 và giới hạn quyền truy cập metadata theo chính sách.
- Azure cung cấp Managed Identity cho VM và một số dịch vụ compute. Ứng dụng lấy access token từ endpoint do nền tảng quản lý, sau đó gọi dịch vụ có quyền được cấp.
- Google Cloud cung cấp service account gắn với VM. Workload có thể lấy access token từ metadata server để gọi Google APIs theo IAM roles được cấp.

Tên API, endpoint và thời hạn token khác nhau giữa nhà cung cấp. Nên dùng SDK chính thức hoặc thư viện identity được hỗ trợ để xử lý metadata, cache và refresh token.

### 3.2. Security Token Service (STS)

STS là dịch vụ cấp credential tạm thời sau khi xác minh một danh tính hoặc một yêu cầu assume role. Thay vì phân phối access key dài hạn đến từng workload, hệ thống cấp một phiên credential có thời hạn, thường bao gồm access key tạm, secret key tạm và session token hoặc một access token tùy giao thức.

Một phiên STS thường có:

- Danh tính hoặc role mà workload đang đảm nhận.
- Thời điểm bắt đầu và hết hạn.
- Phạm vi quyền kế thừa từ role/policy.
- Thông tin phiên hoặc điều kiện bổ sung nếu provider hỗ trợ.

Thời hạn phiên nên đủ dài để workload hoạt động ổn định nhưng không quá dài so với nhu cầu. Thời hạn tối đa và tối thiểu do provider quy định. Không nên tự chọn một con số rồi giả định mọi dịch vụ đều hỗ trợ.

### 3.3. OAuth 2.0 và OpenID Connect

OAuth 2.0 thường được dùng để cấp quyền truy cập API bằng access token. OpenID Connect (OIDC) bổ sung lớp xác thực danh tính dựa trên OAuth 2.0 và ID token.

Một số điểm cần phân biệt:

- **ID token:** thường dùng để chứng minh thông tin xác thực của người dùng hoặc workload với client tin cậy; không mặc nhiên là token để gọi mọi API.
- **Access token:** dùng để truy cập resource server theo audience và scope/permission được cấp.
- **Refresh token:** có thể dùng để xin access token mới mà không yêu cầu xác thực lại; nó thường có vòng đời và mức nhạy cảm cao hơn access token.
- **Client secret:** bí mật dài hạn của một confidential client; cần bảo vệ và luân chuyển nếu được sử dụng.

Workload nên dùng flow phù hợp với môi trường thực thi. Với ứng dụng chạy trên server, authorization code flow có PKCE hoặc client credentials flow có thể phù hợp tùy loại client và identity provider. Với workload cloud, workload identity federation thường tránh được việc lưu client secret dài hạn.

Không gửi ID token đến API chỉ vì nó là JWT. Resource server phải xác minh đúng loại token, issuer, audience, chữ ký, thời hạn và claim cần thiết.

### 3.4. Workload identity federation qua OIDC

CI/CD runner hoặc workload bên ngoài cloud có thể chứng minh danh tính bằng OIDC token được nền tảng CI/CD cấp. Cloud identity provider xác minh issuer, chữ ký và claim như repository, branch, environment hoặc subject; nếu điều kiện tin cậy đạt, workload được cấp credential tạm thời.

Ví dụ, pipeline triển khai chỉ được assume role khi:

- Token đến từ issuer OIDC đã đăng ký.
- Subject khớp repository và workflow được phép.
- Branch hoặc deployment environment thuộc danh sách tin cậy.
- Audience đúng với dịch vụ cấp credential.

Điều kiện trust quá rộng như chấp nhận mọi repository hoặc mọi branch có thể cho phép workload không mong muốn lấy quyền. Hãy ràng buộc trust policy với tổ chức, repository, branch/tag, environment và audience cần thiết.

## 4. Metadata service và bảo vệ danh tính VM

Metadata service cung cấp thông tin về VM và thường là đường để lấy credential. Vì vậy, quyền truy cập metadata endpoint cần được kiểm soát.

### 4.1. Rủi ro từ SSRF

Server-Side Request Forgery (SSRF) xảy ra khi ứng dụng bị lừa gửi request đến địa chỉ do kẻ tấn công kiểm soát. Nếu metadata endpoint có thể truy cập từ workload và không có biện pháp bảo vệ phù hợp, lỗ hổng SSRF có thể bị lợi dụng để lấy metadata hoặc token của VM.

Biện pháp giảm thiểu:

- Bật cơ chế metadata bảo vệ theo khuyến nghị của provider, chẳng hạn yêu cầu token phiên IMDSv2 trên EC2.
- Giới hạn hop hoặc đường truy cập metadata nếu nền tảng hỗ trợ.
- Chặn ứng dụng không cần thiết truy cập metadata endpoint.
- Không cho phép người dùng kiểm soát URL mà backend fetch mà thiếu allowlist và kiểm tra đích.
- Cập nhật framework, thư viện HTTP và xử lý redirect an toàn.
- Giới hạn quyền của instance role để token bị lộ cũng không có quyền rộng.

IMDSv2 giảm một số kiểu khai thác SSRF bằng yêu cầu phiên có token và request phù hợp, nhưng không thay thế việc sửa lỗi SSRF hoặc least privilege.

### 4.2. Không đưa credential vào image

Không bake access key, client secret, refresh token, private key hoặc mật khẩu vào:

- Machine image hoặc container image.
- User data, cloud-init hoặc startup script lưu lâu dài.
- Git repository, file cấu hình mẫu hoặc artifact build.
- Shell history, command line và log pipeline.
- File backup hoặc snapshot được chia sẻ rộng.

Image nên chứa ứng dụng và cấu hình không nhạy cảm. Khi máy khởi động, workload dùng identity gắn với VM hoặc lấy credential qua federation. Nếu phải dùng secret dài hạn vì hệ thống đích chưa hỗ trợ federation, hãy lấy secret từ secret manager qua một danh tính bootstrap có quyền tối thiểu.

## 5. Thiết kế quyền tối thiểu cho workload

Credential ngắn hạn chỉ giảm thời gian khai thác; quyền quá rộng vẫn gây thiệt hại lớn trong thời gian token còn hiệu lực.

### 5.1. Tách role theo trách nhiệm

Ví dụ một ứng dụng có thể cần:

- Đọc cấu hình từ một path cụ thể.
- Đọc/ghi một bucket hoặc prefix.
- Ghi log và metric.
- Lấy secret của một database.

Thay vì cấp quyền quản trị toàn bộ tài khoản, tạo role chỉ cho phép những thao tác đó trên tài nguyên xác định. Nếu ứng dụng có nhiều thành phần với trách nhiệm khác nhau, cấp identity riêng cho từng thành phần.

### 5.2. Scope, audience và resource restriction

Khi hệ thống hỗ trợ, token nên giới hạn:

- **Audience (aud):** dịch vụ hoặc resource server được phép nhận token.
- **Scope/role:** nhóm hành động được phép thực hiện.
- **Resource:** bucket, database, queue hoặc API cụ thể.
- **Subject:** danh tính workload hoặc người dùng cụ thể.
- **Session duration:** thời hạn phiên.
- **Network/context conditions:** điều kiện mạng, thiết bị hoặc môi trường nếu provider hỗ trợ.

Audience không thay thế authorization policy. Một token đúng audience vẫn có thể không có quyền đọc một resource cụ thể. Tương tự, scope rộng không nên được dùng nếu ứng dụng chỉ cần một hành động hẹp.

### 5.3. Tách môi trường

Development, staging và production nên dùng identity, role và secret riêng. Không dùng credential production trong môi trường thử nghiệm. Nếu staging bị xâm nhập, phạm vi quyền không nên cho phép truy cập dữ liệu hoặc tài nguyên production.

## 6. Làm mới credential trước khi hết hạn

Ứng dụng dùng credential ngắn hạn phải có cơ chế refresh. Nếu chỉ lấy token một lần khi khởi động, ứng dụng có thể chạy tốt trong vài phút hoặc vài giờ rồi bắt đầu nhận lỗi unauthorized khi token hết hạn.

### 6.1. Dùng SDK và credential provider chain

SDK cloud thường có credential provider chain để tìm danh tính theo thứ tự cấu hình. Trong môi trường VM, SDK có thể dùng instance role; trong container, SDK có thể dùng workload identity hoặc credential provider của orchestrator.

Ưu tiên SDK chính thức vì nó thường xử lý:

- Lấy token từ metadata hoặc identity endpoint.
- Cache credential trong bộ nhớ.
- Làm mới trước thời điểm hết hạn.
- Retry có giới hạn khi endpoint tạm thời lỗi.
- Chọn credential provider phù hợp môi trường.

Không tự viết cơ chế refresh nếu SDK đã hỗ trợ. Nếu phải tự quản lý, cần hiểu thời hạn token, clock skew, giới hạn API và cách xử lý lỗi.

### 6.2. Làm mới chủ động và tránh refresh đồng loạt

Không nên chờ token hết hạn mới lấy token mới. Có thể bắt đầu refresh trước expiry một khoảng an toàn để chịu được độ trễ mạng và sai lệch đồng hồ.

Với nhiều worker chạy cùng lúc, nếu tất cả cùng refresh tại một thời điểm, identity service có thể nhận một đợt request đột biến. Dùng cache chia sẻ phù hợp, single-flight hoặc jitter để phân tán thời điểm refresh. Không chia sẻ token giữa các workload khác trust boundary.

### 6.3. Xử lý lỗi refresh

Nếu identity endpoint tạm thời không sẵn sàng:

1. Tiếp tục dùng credential hiện tại khi nó còn hiệu lực và policy cho phép.
2. Retry với exponential backoff và jitter, có giới hạn.
3. Không ghi token hoặc secret vào log khi báo lỗi.
4. Phát metric về refresh failure, remaining lifetime và số lần retry.
5. Nếu token sắp hết hạn mà không thể refresh, ngừng nhận công việc mới hoặc chuyển workload sang trạng thái suy giảm an toàn.
6. Sau khi identity service phục hồi, refresh và kiểm tra lại quyền truy cập.

Không retry vô hạn với credential đã hết hạn hoặc bị thu hồi. Cần phân biệt lỗi mạng tạm thời, throttling, trust policy sai, audience không đúng và danh tính đã bị vô hiệu hóa.

## 7. Luân chuyển credential dài hạn khi chưa thể loại bỏ

Một số hệ thống cũ, dịch vụ bên thứ ba hoặc thiết bị ngoài cloud chưa hỗ trợ workload identity. Khi đó có thể vẫn cần API key, mật khẩu hoặc client secret dài hạn. Cần quản lý chúng trong secret manager và có quy trình rotation rõ ràng.

### 7.1. Quy trình rotation có thời gian chồng lấn

Thay credential đang dùng ngay lập tức có thể làm gián đoạn ứng dụng. Quy trình phổ biến là tạo credential mới, chuyển workload, xác minh rồi mới thu hồi credential cũ.

~~~mermaid
flowchart TD
    A["Đánh giá credential và consumer"] --> B["Tạo credential mới"]
    B --> C["Lưu vào secret manager"]
    C --> D["Cập nhật consumer theo từng nhóm"]
    D --> E["Kiểm tra xác thực và hành động nghiệp vụ"]
    E --> F{"Tất cả consumer đã dùng credential mới?"}
    F -- "Chưa" --> D
    F -- "Rồi" --> G["Thu hồi credential cũ"]
    G --> H["Theo dõi lỗi và audit"]
    H --> I["Đóng rotation và cập nhật inventory"]
~~~

Các bước nên thực hiện:

1. Xác định chủ sở hữu, mục đích, quyền, thời điểm hết hạn và mọi consumer đang dùng credential.
2. Kiểm tra hệ thống đích hỗ trợ hai credential đồng thời hay không.
3. Tạo credential mới với quyền tương đương hoặc hẹp hơn.
4. Lưu credential mới trong secret manager; không truyền qua chat hoặc log.
5. Cập nhật một nhóm consumer thử nghiệm.
6. Xác minh kết nối, thao tác đọc/ghi và metric lỗi.
7. Cập nhật các consumer còn lại theo từng đợt.
8. Xác nhận không còn request dùng credential cũ.
9. Thu hồi credential cũ và kiểm tra nó không còn hoạt động.
10. Ghi nhận kết quả rotation, thời điểm và người/hệ thống thực hiện.

Thời gian overlap cần ngắn và có giới hạn. Nếu credential cũ bị nghi ngờ đã lộ, cần cân nhắc thu hồi khẩn cấp thay vì duy trì overlap dài; khi đó có thể phải chấp nhận gián đoạn có kiểm soát.

### 7.2. Hệ thống chỉ cho phép một credential

Một số dịch vụ chỉ cho phép một API key hoặc một password tại một thời điểm. Khi không thể overlap:

- Kiểm tra có thể tạo thêm principal hoặc client phụ để chuyển đổi hay không.
- Dùng cửa sổ bảo trì và chuẩn bị consumer cập nhật đồng bộ.
- Cập nhật secret ở nơi tập trung trước, sau đó restart/reload consumer theo kế hoạch.
- Chuẩn bị phương án rollback credential nếu hệ thống đích hỗ trợ.
- Xác minh các consumer quan trọng trước khi đóng cửa sổ thay đổi.

Không nên xóa credential cũ trước khi biết credential mới đã được phân phối và consumer đã nạp thành công.

### 7.3. Rotation không chỉ là đổi chuỗi bí mật

Credential có thể gắn với principal, role hoặc policy. Khi luân chuyển, cần xem xét:

- Quyền cũ có còn cần thiết không.
- Có cần thay role hoặc tách identity không.
- Credential mới có quyền rộng hơn ngoài dự kiến không.
- Secret có xuất hiện trong log, dump hoặc backup cũ không.
- Consumer nào chưa cập nhật hoặc đang dùng cache.
- Credential cũ đã bị thu hồi ở tất cả nơi liên quan chưa.

Nếu chỉ tạo key mới nhưng để key cũ tồn tại vô thời hạn, rủi ro chưa được loại bỏ.

## 8. Luân chuyển quyền truy cập và thu hồi quyền

Rotation có thể liên quan đến credential, nhưng quyền truy cập cũng cần được rà soát và điều chỉnh định kỳ.

### 8.1. Thay đổi policy an toàn

Khi thu hẹp quyền:

1. Thu thập audit log để xác định các hành động workload thực sự sử dụng.
2. So sánh quyền đang cấp với nhiệm vụ hiện tại.
3. Tạo policy mới hẹp hơn hoặc role mới.
4. Gắn policy mới cho một nhóm workload thử nghiệm.
5. Kiểm tra hành vi ứng dụng và các luồng ít dùng như backup, restore, failover.
6. Chuyển toàn bộ workload sang policy mới.
7. Gỡ policy cũ và xác minh không còn quyền thừa.

Thay policy có thể tác động ngay đến request tiếp theo, nhưng một số hệ thống cache authorization hoặc token claims đến hết thời hạn token. Cần hiểu cơ chế thực tế để xác định thời gian quyền cũ còn hiệu lực.

### 8.2. Thu hồi khẩn cấp

Khi credential bị lộ hoặc workload bị xâm nhập:

- Disable hoặc revoke credential/principal theo khả năng của provider.
- Gỡ role hoặc policy nhạy cảm và chặn đường truy cập không cần thiết.
- Thu hồi session hoặc token nếu dịch vụ hỗ trợ; nếu không, giới hạn tác động bằng cách thay đổi policy và chờ token hết hạn theo cơ chế.
- Xoay vòng secret, key hoặc certificate có liên quan.
- Kiểm tra audit log, source IP, user agent, resource và hành động bất thường.
- Cô lập VM/container bị ảnh hưởng và giữ bằng chứng điều tra.
- Khởi tạo workload mới từ image đáng tin cậy sau khi xử lý nguyên nhân.

Xóa file credential khỏi VM không thu hồi bản sao đã bị lấy đi. Thu hồi phải diễn ra ở identity provider hoặc hệ thống đích.

## 9. Lưu trữ và phân phối secret

Secret manager tập trung giúp lưu trữ, kiểm soát quyền, ghi audit và luân chuyển secret. Workload nên xác thực với secret manager bằng danh tính ngắn hạn, sau đó chỉ đọc đúng secret cần dùng.

Các nguyên tắc:

- Mỗi ứng dụng hoặc workload có secret path riêng.
- Chỉ cấp quyền đọc secret cần thiết, không cấp quyền liệt kê hoặc quản trị toàn bộ kho nếu không cần.
- Hạn chế thời gian secret nằm trong bộ nhớ và tránh ghi ra disk.
- Không đưa secret vào environment variable nếu runtime hoặc hệ điều hành có cách phân phối an toàn hơn; nếu phải dùng, cần kiểm soát quyền đọc process và dump.
- Không truyền secret qua command-line argument vì có thể xuất hiện trong process listing hoặc audit log.
- Che giá trị nhạy cảm trong log, trace, crash dump và error report.
- Bật audit cho thao tác đọc, ghi, rotate và delete secret.
- Có kế hoạch phục hồi khi secret manager hoặc KMS không sẵn sàng.

Nếu workload cache secret trong bộ nhớ, cần có TTL và cơ chế reload. Không giữ secret vô thời hạn chỉ vì ứng dụng không có cơ chế refresh.

## 10. Credential ngắn hạn trong VM, container và serverless

### 10.1. Máy ảo

VM thường dùng instance role hoặc managed identity. Khi tạo VM, gắn role đúng với nhiệm vụ. SDK lấy credential từ metadata/identity endpoint và làm mới khi cần.

Kiểm soát quan trọng:

- Không dùng access key chung cho cả fleet.
- Hạn chế truy cập metadata endpoint từ ứng dụng có nguy cơ SSRF.
- Tách role theo môi trường và vai trò máy.
- Không để user-data chứa secret lâu dài.
- Kiểm tra role khi tạo image hoặc thay instance type để tránh mất identity attachment.

### 10.2. Container và Kubernetes

Container có thể nhận danh tính từ orchestrator thay vì dùng credential gắn cố định trong image. Trên Kubernetes, ServiceAccount gắn với Pod có thể được sử dụng để cấp token; token projected có thời hạn và audience theo cấu hình. Trên các nền tảng cloud, workload identity integration có thể ánh xạ Kubernetes ServiceAccount sang cloud identity.

Các nguyên tắc:

- Tắt tự động mount ServiceAccount token nếu Pod không cần gọi Kubernetes API.
- Chỉ cấp Role/RoleBinding trong namespace và resource cần thiết.
- Dùng projected service account token với audience và thời hạn phù hợp khi nền tảng hỗ trợ.
- Với cloud API, dùng workload identity federation hoặc cơ chế tích hợp chính thức.
- Không lưu cloud access key trong Kubernetes Secret nếu có thể dùng identity federation.
- Giới hạn quyền node identity; Pod không nên thừa hưởng quyền quản trị rộng của node.

Kubernetes Secret mặc định không tự động tương đương một secret manager có mã hóa và kiểm soát đầy đủ. Cần cấu hình encryption at rest, RBAC, audit và tích hợp secret store theo yêu cầu.

### 10.3. Serverless

Function hoặc serverless container thường có execution identity do nền tảng cấp. Gắn role/service account với function và giới hạn quyền theo nhiệm vụ. Runtime lấy token ngắn hạn từ identity service.

Không lưu trạng thái token trong filesystem tạm với giả định instance sẽ tồn tại giữa các lần gọi. Serverless runtime có thể bị tái tạo hoặc scale về zero. Dùng SDK provider chain và lưu trạng thái nghiệp vụ ở dịch vụ bền vững.

### 10.4. CI/CD và workload ngoài cloud

Pipeline chạy trên GitHub Actions, GitLab CI hoặc hệ thống tương tự có thể dùng OIDC federation để đổi identity token lấy credential tạm. Điều này giúp tránh lưu cloud access key lâu dài trong CI secret.

Trust policy cần giới hạn:

- Issuer URL được tin cậy.
- Audience được phép.
- Organization/repository/project.
- Branch, tag hoặc protected environment.
- Workflow hoặc subject cụ thể nếu nền tảng cung cấp claim.

Pipeline chỉ nên nhận quyền deploy trong thời gian job chạy. Quyền quản trị IAM hoặc xóa tài nguyên production cần tách khỏi role triển khai thông thường.

## 11. Ví dụ cấu hình quyền theo nhiệm vụ

Ví dụ policy khái niệm dưới đây minh họa nguyên tắc chỉ cho phép workload đọc một prefix object và ghi log. Đây không phải policy có thể dùng nguyên trạng cho một provider cụ thể.

~~~yaml
workload_identity:
  name: invoice-worker
  environment: production
  credential:
    source: workload-identity
    max_session_duration: provider-defined
    audience:
      - object-storage-api
  permissions:
    - action:
        - object:Get
      resource:
        - bucket:invoice-archive/pending/*
    - action:
        - logs:Write
      resource:
        - log-group:/services/invoice-worker
  denied_actions:
    - iam:*
    - storage:Delete
~~~

Khi triển khai thực tế, cần chuyển sang cú pháp IAM/RBAC của nhà cung cấp, xác định chính xác resource ARN/ID và action name. Một số dịch vụ yêu cầu quyền bổ sung để liệt kê prefix hoặc đọc metadata; chỉ thêm sau khi xác minh ứng dụng thực sự cần.

## 12. Ví dụ luồng lấy và làm mới token

Pseudocode sau mô tả cách ứng dụng sử dụng SDK credential provider. Các hàm cụ thể phụ thuộc SDK và ngôn ngữ:

~~~text
credentialProvider = createWorkloadCredentialProvider()
client = createCloudApiClient(credentialProvider)

while applicationIsRunning:
    request = receiveWork()
    try:
        result = client.performAllowedAction(request)
        acknowledge(request)
    catch AuthenticationExpired:
        credentialProvider.refresh()
        retryOnceIfOperationIsIdempotent(request)
    catch AuthorizationDenied:
        recordPermissionFailureWithoutSecrets()
        sendToFailureQueueOrStopSafely(request)
~~~

Phân biệt lỗi xác thực và lỗi phân quyền:

- **401/Unauthenticated:** token thiếu, sai chữ ký, sai issuer/audience hoặc hết hạn.
- **403/Forbidden:** danh tính được nhận diện nhưng policy không cho phép hành động.

Mã HTTP và tên lỗi cụ thể tùy API. Không nên tự động retry 403 liên tục vì refresh token thường không làm quyền được cấp rộng hơn. Với thao tác ghi hoặc thanh toán, chỉ retry khi có idempotency key hoặc cơ chế xác nhận kết quả để tránh thực hiện lặp.

## 13. Giám sát và kiểm toán danh tính

Credential ngắn hạn cần được theo dõi để phát hiện refresh lỗi, quyền quá rộng và hành vi bất thường.

| Nhóm quan sát | Chỉ số hoặc sự kiện | Mục đích |
| --- | --- | --- |
| Cấp token | Số lần cấp, lỗi, latency, issuer, audience | Phát hiện lỗi trust hoặc identity service |
| Vòng đời token | Remaining lifetime, refresh success/failure | Phát hiện token sắp hết hạn hoặc refresh bất ổn |
| Sử dụng API | Principal, action, resource, source, result | Phát hiện hành vi bất thường và quyền không cần thiết |
| Policy | Thay đổi role, trust policy, scope và binding | Theo dõi thay đổi quyền truy cập |
| Secret | Read, create, rotate, revoke, delete | Xác định consumer và lịch sử sử dụng |
| Credential dài hạn | Tuổi credential, owner, lần dùng gần nhất, expiry | Tìm khóa cũ hoặc không còn sử dụng |

Không ghi raw access token, refresh token, secret key hoặc mật khẩu vào log. Có thể ghi token ID, key ID, principal, expiry hoặc correlation ID nếu không làm lộ credential.

Các cảnh báo nên bao gồm:

- Token refresh thất bại liên tục hoặc identity endpoint bị throttling.
- Một workload yêu cầu audience hoặc scope bất thường.
- Credential dài hạn vượt thời hạn rotation.
- API key cũ vẫn được sử dụng sau khi credential mới đã triển khai.
- Một principal thực hiện hành động quản trị ngoài lịch triển khai.
- Một workload gọi API từ nguồn hoặc vùng không mong đợi.

## 14. Kế hoạch rotation định kỳ

Một lịch rotation cần phản ánh loại credential, khả năng tự động hóa và mức độ quan trọng của workload.

| Loại thông tin | Cách ưu tiên | Điểm cần lưu ý |
| --- | --- | --- |
| Instance role/managed identity | Dùng credential ngắn hạn do provider cấp | Rà soát role và trust policy định kỳ |
| STS/session credential | SDK tự refresh theo expiry | Kiểm tra thời hạn, cache và lỗi identity endpoint |
| OIDC federation | Cấp token theo từng job/workload | Giới hạn issuer, audience, subject và environment |
| API key bên thứ ba | Secret manager và rotation theo chu kỳ | Xác minh overlap và consumer trước khi revoke |
| Database password | Ưu tiên IAM/database auth hoặc secret rotation tích hợp | Cập nhật connection pool và phiên kết nối |
| TLS certificate | Tự động gia hạn và triển khai certificate mới | Theo dõi chain, SAN, expiry và reload dịch vụ |
| SSH key quản trị | Ưu tiên short-lived SSH certificate hoặc identity-aware access | Thu hồi principal và kiểm soát authorized key cũ |

Không có một chu kỳ rotation phù hợp cho mọi loại secret. Tuân theo chính sách tổ chức, yêu cầu tuân thủ, khả năng provider và thời gian phản ứng khi credential bị lộ. Tự động hóa rotation có thể giảm lỗi thao tác nhưng vẫn cần kiểm tra consumer và kết quả sau khi đổi.

### 14.1. Inventory credential

Tổ chức nên duy trì danh mục credential gồm:

- Tên và loại credential.
- Chủ sở hữu và ứng dụng sử dụng.
- Nơi lưu trữ hoặc identity provider.
- Quyền và resource được phép truy cập.
- Ngày tạo, ngày hết hạn hoặc lịch rotation.
- Danh sách consumer và môi trường.
- Cách revoke và phương án khôi phục.
- Trạng thái cuối cùng sau lần rotation.

Credential không có owner hoặc consumer rõ ràng cần được điều tra trước khi xóa. Không nên thu hồi hàng loạt chỉ dựa trên tuổi mà chưa xác định phụ thuộc.

## 15. Xử lý sự cố credential bị lộ hoặc hết hạn

### 15.1. Credential bị lộ

1. Xác định loại credential, principal, quyền và phạm vi tài nguyên.
2. Thu hồi hoặc vô hiệu hóa credential ở identity provider/dịch vụ đích.
3. Chặn hoặc thu hẹp policy để giới hạn token/session còn hiệu lực.
4. Xoay vòng secret, key, certificate hoặc trust binding liên quan.
5. Kiểm tra audit log trước và sau thời điểm nghi lộ.
6. Cô lập workload nếu nghi bị chiếm quyền.
7. Tạo lại workload từ image đáng tin cậy và cấp identity mới nếu cần.
8. Xác minh credential cũ không còn được chấp nhận.
9. Ghi lại nguyên nhân, phạm vi và biện pháp phòng ngừa.

### 15.2. Token hết hạn trong lúc xử lý

Nếu một tác vụ dài chạy lâu hơn thời hạn token, SDK cần làm mới credential trước request tiếp theo. Với tác vụ có thể kéo dài nhiều giờ, tránh giữ một token duy nhất trong biến cấu hình lúc khởi động. Dùng provider tự refresh hoặc chia công việc thành bước có checkpoint.

Nếu API stream hoặc kết nối dài không tự cập nhật token, cần kiểm tra cơ chế reauthentication của giao thức. Một số kết nối đã xác thực có thể tiếp tục đến khi đóng, trong khi kết nối mới sẽ bị từ chối sau expiry. Hành vi phụ thuộc dịch vụ.

### 15.3. Rotation làm workload mất quyền

Khi đổi role hoặc policy, lỗi 403 có thể xuất hiện nếu quyền mới thiếu một action phụ trợ. Kiểm tra audit log và policy evaluation để xác định action/resource bị từ chối. Không giải quyết bằng cách cấp Administrator hoặc wildcard rộng. Thêm quyền tối thiểu đã được chứng minh cần thiết, kiểm thử lại và ghi nhận lý do.

## 16. Những sai lầm thường gặp

- Đưa access key hoặc client secret vào machine image/container image.
- Dùng chung một identity quyền rộng cho nhiều VM hoặc ứng dụng.
- Lấy token một lần lúc khởi động rồi không làm mới.
- Dùng ID token để gọi resource API mà không kiểm tra audience và loại token.
- Trust mọi repository/branch trong OIDC federation.
- Cho rằng token hết hạn đồng nghĩa token bị lộ đã bị thu hồi ngay lập tức.
- Thu hồi credential cũ trước khi mọi consumer đã dùng credential mới.
- Giữ credential cũ quá lâu sau khi rotation thành công.
- Retry 403 liên tục hoặc retry thao tác ghi không có idempotency.
- Ghi raw token, secret hoặc authorization header vào log.
- Chỉ xoay key mà không rà soát role và quyền gắn với key.
- Xóa secret mà không xác định backup, cache hoặc consumer còn sử dụng.
- Cho phép mọi container truy cập metadata hoặc node identity.

## 17. Quy trình triển khai danh tính workload an toàn

1. **Phân loại workload:** xác định VM, container, serverless hay pipeline ngoài cloud.
2. **Chọn identity native:** instance role, managed identity, service account hoặc OIDC federation.
3. **Thiết kế trust:** giới hạn issuer, audience, subject, environment và nguồn workload.
4. **Cấp quyền tối thiểu:** giới hạn action, resource, thời hạn và điều kiện truy cập.
5. **Tích hợp SDK:** dùng provider chain, cache và refresh tự động.
6. **Bảo vệ metadata và secret:** giảm SSRF, không bake credential vào image, dùng secret manager khi cần.
7. **Kiểm thử vòng đời:** xác minh token được cấp, refresh trước expiry, lỗi được xử lý và workload reconnect.
8. **Thiết lập audit:** ghi principal, action, resource và kết quả mà không log credential.
9. **Lập inventory và rotation:** xác định owner, consumer, thời hạn và quy trình revoke.
10. **Diễn tập sự cố:** thử thu hồi identity, thay secret, khôi phục workload và xác minh quyền cũ bị vô hiệu hóa.

## 18. Nguyên tắc vận hành

1. **Ưu tiên danh tính workload:** dùng instance role, managed identity, service account hoặc federation thay cho key tĩnh.
2. **Giới hạn quyền:** tách identity theo ứng dụng và môi trường, cấp đúng action trên đúng resource.
3. **Giới hạn thời gian:** dùng token có expiry phù hợp và làm mới trước khi hết hạn.
4. **Ràng buộc token:** kiểm tra issuer, audience, subject, scope và policy ở đúng lớp.
5. **Bảo vệ metadata:** giảm nguy cơ SSRF và hạn chế quyền của instance identity.
6. **Rotation có overlap:** phân phối credential mới, xác minh consumer rồi mới thu hồi credential cũ khi hệ thống cho phép.
7. **Thu hồi ở nguồn:** xóa bản sao trong máy không thay thế việc revoke tại identity provider.
8. **Không log bí mật:** chỉ ghi metadata đủ để điều tra, không ghi token hoặc secret thô.
9. **Theo dõi cả quyền:** rà soát role, trust policy và policy binding cùng với việc xoay credential.
10. **Kiểm thử phục hồi:** xác minh refresh, revoke, reconnect và phương án xử lý khi identity service không sẵn sàng.

Thông tin xác thực ngắn hạn giúp workload truy cập dịch vụ cloud mà không cần mang theo bí mật dài hạn trong image hoặc mã nguồn. Khi kết hợp workload identity, quyền tối thiểu, refresh tự động, rotation có kiểm soát và audit, đội kỹ thuật có thể giảm cửa sổ rủi ro của credential bị lộ mà vẫn duy trì khả năng vận hành liên tục cho VM, container và serverless.
