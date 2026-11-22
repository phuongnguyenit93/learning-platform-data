# Secret Manager secrets, versions và access policies

Secret Manager là dịch vụ của Google Cloud dùng để lưu trữ và kiểm soát thông tin nhạy cảm mà ứng dụng cần khi chạy, chẳng hạn mật khẩu cơ sở dữ liệu, API key, token, chứng chỉ và thông tin xác thực của dịch vụ bên ngoài. Dịch vụ giúp tách dữ liệu bí mật khỏi mã nguồn, image container và tệp cấu hình được phát hành cùng ứng dụng.

Để dùng Secret Manager an toàn, cần hiểu ba phần gắn chặt với nhau: **secret** là tài nguyên quản lý và chứa metadata; **secret version** lưu giá trị bí mật thực tế; **IAM policy** quyết định danh tính nào được xem metadata, thêm phiên bản hoặc đọc payload. Quy trình triển khai tốt còn phải quản lý vòng đời phiên bản, phát hành thay đổi có kiểm soát và ghi nhận hoạt động truy cập.

Sau bài học, bạn có thể:

- Phân biệt secret với secret version và giải thích vì sao giá trị của một version không thể sửa tại chỗ.
- Tạo secret, thêm version, đọc một version cụ thể và dùng version alias.
- Thiết kế IAM policy theo nguyên tắc quyền tối thiểu cho người dùng và service account.
- Tổ chức rotation, rollback, disable và destroy version an toàn.
- Kết nối ứng dụng Java trên Google Cloud với Secret Manager bằng Application Default Credentials.

## 1. Secret Manager giải quyết vấn đề gì?

Một ứng dụng thường cần các giá trị như:

- Mật khẩu để kết nối PostgreSQL hoặc MySQL.
- API key của cổng thanh toán, dịch vụ gửi email hoặc hệ thống đối tác.
- Access token và refresh token của một dịch vụ bên ngoài.
- Private key hoặc nội dung chứng chỉ mà ứng dụng cần đọc khi khởi động.
- Chuỗi kết nối chứa thông tin xác thực.

Nếu đặt các giá trị này trực tiếp trong source code, file .env, image Docker hoặc biến cấu hình được chia sẻ rộng rãi, chúng có thể bị lộ qua Git, log build, artifact, bản sao lưu hoặc quyền truy cập không phù hợp. Khi credential bị lộ, việc thay đổi giá trị cũng thường đòi hỏi sửa cấu hình và phát hành lại ứng dụng.

Secret Manager cung cấp một nơi lưu trữ tập trung với mã hóa, IAM, versioning và audit log. Ứng dụng xác thực bằng danh tính Google Cloud của workload rồi gọi API để lấy đúng secret cần dùng. Người vận hành có thể cấp quyền cho từng secret và thay đổi giá trị bằng cách thêm version mới.

### Secret Manager và Cloud KMS khác nhau thế nào?

Hai dịch vụ thường được dùng cùng nhau nhưng giải quyết hai bài toán khác nhau:

| Dịch vụ | Vai trò chính | Ví dụ |
|---|---|---|
| Secret Manager | Lưu trữ và phân phối dữ liệu bí mật cho ứng dụng | Mật khẩu database, API token, private key dưới dạng dữ liệu |
| Cloud Key Management Service (Cloud KMS) | Quản lý khóa mã hóa và thực hiện thao tác mật mã | Tạo, xoay vòng, phân quyền và dùng khóa để mã hóa/giải mã dữ liệu |

Secret Manager mã hóa dữ liệu bí mật khi truyền và khi lưu trữ. Nếu tổ chức cần kiểm soát khóa mã hóa do khách hàng quản lý, secret có thể dùng Customer-Managed Encryption Keys (CMEK) từ Cloud KMS. Việc dùng CMEK không biến Secret Manager thành dịch vụ quản lý khóa ứng dụng: payload vẫn được lưu và truy cập qua Secret Manager.

## 2. Mô hình tài nguyên: secret và secret version

Một secret là tài nguyên chứa metadata và một tập hợp các version. Metadata có thể gồm tên, labels, annotations, cấu hình replication, thông tin rotation và IAM policy. Payload thực tế nằm trong từng version.

~~~mermaid
flowchart TB
    P["Google Cloud project"] --> S["Secret: orders-db-password"]
    S --> M["Metadata, labels, replication, IAM"]
    S --> V1["Version 1: payload bất biến"]
    S --> V2["Version 2: payload bất biến"]
    S --> V3["Version 3: payload bất biến"]
    W["Ứng dụng / service account"] -->|IAM cho phép| S
    W -->|AccessSecretVersion(version 3)| V3
~~~

Ví dụ, secret có tên orders-db-password có thể chứa:

- Version 1: mật khẩu ban đầu.
- Version 2: mật khẩu đã được thay đổi trong lần rotation thứ nhất.
- Version 3: mật khẩu đang được workload production sử dụng.

Khi mật khẩu thay đổi, Secret Manager tạo version mới. Version cũ vẫn tồn tại cho đến khi bị disable hoặc destroy theo chính sách vòng đời. Vì payload của version là bất biến, bạn có thể xác định chính xác workload đã đọc giá trị nào và quay lại version trước nếu cần.

Tên tài nguyên của một secret version thuộc dịch vụ global có dạng:

~~~text
projects/PROJECT_ID/secrets/SECRET_ID/versions/VERSION_ID
~~~

Ví dụ:

~~~text
projects/acme-prod-123/secrets/orders-db-password/versions/3
~~~

Secret Manager cũng có dịch vụ regional với đường dẫn chứa locations/LOCATION. Hãy chọn loại tài nguyên theo yêu cầu về vị trí dữ liệu và phạm vi triển khai; phần lớn ví dụ trong bài này dùng dịch vụ global mặc định.

## 3. Tạo secret và thêm version

### 3.1. Chuẩn bị project và API

Trước tiên, chọn đúng project và bật Secret Manager API:

~~~bash
gcloud config set project acme-prod-123
gcloud services enable secretmanager.googleapis.com
~~~

Người tạo secret cần quyền quản trị phù hợp, thường là roles/secretmanager.admin hoặc một custom role chứa các permission cần thiết.

Nên tách project theo môi trường, ví dụ acme-dev, acme-staging và acme-prod. Cách tổ chức này giảm nguy cơ một binding ở cấp project vô tình cho ứng dụng thử nghiệm đọc được secret production.

### 3.2. Tạo secret

Tạo secret với replication tự động:

~~~bash
gcloud secrets create orders-db-password --replication-policy="automatic" --labels="app=orders,environment=production"
~~~

Lệnh trên tạo tài nguyên secret và metadata. Nếu chưa cung cấp payload ban đầu, secret chưa có version để ứng dụng truy cập. Bạn có thể thêm version sau đó.

Secret Manager hỗ trợ hai chính sách replication phổ biến cho dịch vụ global:

- **Automatic replication**: Google Cloud chọn vị trí replica phù hợp. Đây thường là lựa chọn đơn giản khi workload không có ràng buộc vị trí cụ thể.
- **User-managed replication**: bạn chỉ định các region cần lưu replica. Cách này cho phép kiểm soát vị trí nhưng cần tính đến chi phí theo từng location.

Nếu yêu cầu tuân thủ quy định về data residency, hãy đánh giá regional secrets và chính sách vị trí dữ liệu của tổ chức thay vì chỉ dựa vào tên region của workload.

### 3.3. Thêm version từ file

Đặt payload vào một file được bảo vệ quyền truy cập trên máy quản trị hoặc trong quy trình phát hành bảo mật. Sau đó thêm version:

~~~bash
gcloud secrets versions add orders-db-password --data-file="./db-password.txt"
~~~

Secret Manager trả về version ID mới. Ghi nhận ID này trong cấu hình phát hành hoặc hệ thống quản lý deployment.

Tránh truyền giá trị bí mật trực tiếp trong câu lệnh như sau:

~~~bash
echo -n "my-real-password" | gcloud secrets versions add orders-db-password --data-file=-
~~~

Cách truyền trực tiếp có thể làm lộ giá trị trong shell history hoặc danh sách process. File đầu vào cũng cần được bảo vệ, xóa theo quy trình phù hợp và không đưa vào Git hay artifact build.

**Nguyên tắc quan trọng:** mỗi lần thay đổi giá trị, hãy thêm một version mới. Không thiết kế quy trình dựa trên việc sửa payload của version cũ.

## 4. Vòng đời và cách tham chiếu secret version

### 4.1. Ba trạng thái của version

Một secret version có một trong ba trạng thái sau:

| Trạng thái | Có thể đọc payload? | Payload còn tồn tại? | Có thể khôi phục? |
|---|---:|---:|---:|
| Enabled | Có, nếu IAM cho phép | Có | Không cần khôi phục |
| Disabled | Không | Có | Có thể enable lại |
| Destroyed | Không | Không, dữ liệu đã bị loại bỏ | Không |

Version mới được tạo ở trạng thái Enabled. Khi disable một version, ứng dụng không thể đọc payload của version đó nhưng dữ liệu vẫn còn và có thể được enable lại. Khi destroy, payload bị loại bỏ vĩnh viễn; thao tác này không thể đảo ngược sau khi hoàn tất.

Enabled và Disabled versions vẫn được tính phí lưu trữ theo quy định dịch vụ; Destroyed versions không còn payload để tính phí lưu trữ. Vì vậy, cần có chính sách giữ lại và dọn dẹp version rõ ràng.

### 4.2. Truy cập bằng version ID

Để đọc version 3:

~~~bash
gcloud secrets versions access 3 --secret="orders-db-password"
~~~

Có thể dùng latest để đọc version mới nhất:

~~~bash
gcloud secrets versions access latest --secret="orders-db-password"
~~~

latest thuận tiện trong thử nghiệm, nhưng cần thận trọng ở production. Khi một version mới được thêm, workload dùng latest có thể nhận giá trị mới ngay ở lần đọc tiếp theo. Nếu giá trị mới sai hoặc chưa được hệ thống bên ngoài chấp nhận, nhiều instance có thể gặp lỗi cùng lúc.

Với deployment production, nên ghim cấu hình vào version ID cụ thể, ví dụ version 3. Khi phát hành version 4, kiểm tra giá trị mới rồi cập nhật cấu hình deployment theo quy trình release hiện có. Cách này giúp mỗi lần triển khai có thể tái lập và rollback rõ ràng.

### 4.3. Dùng version alias

Secret Manager cho phép gán alias do người dùng đặt cho một version. Ví dụ, gán alias stable cho version 3:

~~~bash
gcloud secrets update orders-db-password --update-version-aliases=stable=3
~~~

Đọc payload thông qua alias:

~~~bash
gcloud secrets versions access stable --secret="orders-db-password"
~~~

Alias giúp cấu hình dễ hiểu hơn, nhưng alias là ánh xạ có thể thay đổi. Nếu chuyển stable từ version 3 sang version 4, ứng dụng đọc alias ở lần tiếp theo sẽ nhận version 4. Vì vậy, cần kiểm soát ai được phép sửa alias và thời điểm thay đổi.

Tên alias tùy chỉnh phải bắt đầu bằng chữ cái, dài tối đa 63 ký tự và có thể chứa chữ cái, số, dấu gạch ngang hoặc gạch dưới. Không dùng latest hoặc new làm tên alias tùy chỉnh vì đây là các tên dành riêng. Một secret có thể có nhiều alias, nhưng nên đặt tên phản ánh mục đích rõ ràng.

Một quy trình phát hành an toàn có thể dùng alias cho bước kiểm thử hoặc promotion, sau đó ghi version ID cụ thể vào cấu hình production. Đừng để việc đổi alias trở thành thao tác không được review nhưng lại ảnh hưởng đến toàn bộ workload.

## 5. Thiết kế IAM access policies

Secret Manager dùng Identity and Access Management (IAM) để quyết định principal nào được thực hiện thao tác nào. Principal có thể là user, Google Group hoặc service account. IAM role là tập hợp permission; khi gán role cho principal trên một tài nguyên, principal nhận các quyền tương ứng trên phạm vi đó.

### 5.1. Các role thường gặp

| IAM role | Mục đích | Đọc được payload? |
|---|---|---:|
| roles/secretmanager.secretAccessor | Đọc payload của secret version | Có |
| roles/secretmanager.viewer | Xem metadata và danh sách/version metadata | Không |
| roles/secretmanager.secretVersionAdder | Thêm version vào secret hiện có | Không |
| roles/secretmanager.secretVersionManager | Thêm, enable, disable và destroy version | Không |
| roles/secretmanager.admin | Quản trị Secret Manager, gồm quản lý policy và version | Có |

Hãy chú ý sự khác biệt giữa quyền xem metadata và quyền đọc payload. Một nhân viên vận hành có thể cần biết secret tồn tại, trạng thái version và thời điểm cập nhật mà không cần biết mật khẩu thực tế. Trong trường hợp đó, Viewer có thể đáp ứng nhu cầu tốt hơn Accessor.

Tương tự, một quy trình CI/CD chỉ cần thêm version có thể dùng Secret Version Adder. Nếu quy trình còn phải disable hoặc destroy version, hãy đánh giá Secret Version Manager. Tránh cấp Admin cho mọi workload chỉ vì muốn đơn giản hóa cấu hình.

### 5.2. Gán quyền ở phạm vi nhỏ nhất

IAM role có thể được gán ở secret, project, folder hoặc organization. Phạm vi càng cao thì quyền càng bao phủ nhiều tài nguyên:

| Nơi gán roles/secretmanager.secretAccessor | Phạm vi payload mà principal có thể đọc |
|---|---|
| Một secret | Chỉ secret đó |
| Project | Tất cả secret trong project |
| Folder | Các secret trong những project thuộc folder |
| Organization | Các secret trong những project thuộc organization |

Nếu service account chỉ cần mật khẩu của dịch vụ Orders, hãy cấp Accessor trực tiếp trên secret orders-db-password. Đừng cấp quyền đọc toàn bộ project khi workload chỉ cần một giá trị.

Ví dụ, cấp quyền cho service account chạy ứng dụng Orders:

~~~bash
gcloud secrets add-iam-policy-binding orders-db-password --member="serviceAccount:orders-runtime@acme-prod-123.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
~~~

IAM role được gán trên secret, không gán riêng trên từng secret version. Khi principal có quyền Accessor trên secret, quyền đó áp dụng cho payload của các version thuộc secret theo policy hiện hành.

### 5.3. IAM Conditions và kiểm soát danh tính

IAM Conditions cho phép giới hạn quyền theo thuộc tính tài nguyên hoặc thời gian. Một số tình huống phù hợp:

- Cấp quyền truy cập tạm thời đến một thời điểm xác định.
- Chỉ cho phép principal thao tác trên secret có tên theo một prefix nhất định.
- Giới hạn một nhóm quyền theo tài nguyên hoặc phạm vi cần thiết.

Với môi trường có nhiều nhóm ứng dụng, hãy kết hợp project tách biệt, secret-level bindings và IAM Conditions để giảm phạm vi ảnh hưởng khi một service account hoặc tài khoản con người bị xâm nhập.

Ngoài IAM, tổ chức có thể dùng VPC Service Controls để tạo perimeter bảo vệ API và dùng organization policy để giới hạn domain của principal được phép thêm vào IAM policy. Đây là các lớp kiểm soát bổ sung, không thay thế việc thiết kế role tối thiểu.

### 5.4. Dùng service account của workload

Ứng dụng chạy trên Google Cloud nên xác thực bằng danh tính runtime của chính workload thông qua Application Default Credentials (ADC). Ví dụ:

- Cloud Run dùng service account được gắn vào service.
- Compute Engine dùng service account của VM.
- GKE có thể dùng Workload Identity để ánh xạ Kubernetes workload tới Google service account.

Cách này tránh phải tạo và phân phối service account key file. Nếu ứng dụng chạy ngoài Google Cloud, cân nhắc Workload Identity Federation để dùng danh tính từ nhà cung cấp hiện tại.

Đối với workload trên Compute Engine hoặc GKE, kiểm tra OAuth access scope của VM/node; Secret Manager API cần scope cloud-platform. Có IAM role phù hợp mà thiếu scope cần thiết vẫn có thể khiến lệnh gọi API thất bại.

## 6. Đọc secret trong ứng dụng Java

Ứng dụng Java có thể dùng Google Cloud Secret Manager client library. Client library sử dụng ADC để tìm thông tin xác thực; trong production, hãy gắn service account có quyền Accessor trên đúng secret.

Dependency của thư viện có artifact google-cloud-secretmanager. Nên quản lý phiên bản thư viện bằng Google Cloud Libraries BOM trong dự án Gradle hoặc Maven.

Ví dụ đọc version cụ thể:

~~~java
import com.google.cloud.secretmanager.v1.AccessSecretVersionResponse;
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import com.google.cloud.secretmanager.v1.SecretVersionName;

public final class DatabaseSecretLoader {
    public String loadPassword(
            String projectId,
            String secretId,
            String versionId) throws Exception {

        SecretVersionName versionName =
                SecretVersionName.of(projectId, secretId, versionId);

        try (SecretManagerServiceClient client =
                     SecretManagerServiceClient.create()) {
            AccessSecretVersionResponse response =
                    client.accessSecretVersion(versionName);

            return response.getPayload().getData().toStringUtf8();
        }
    }
}
~~~

Ở đây, versionId là version ID cụ thể như 3. Nếu muốn thử nghiệm với version mới nhất, có thể dùng chuỗi latest, nhưng production nên nhận version ID từ cấu hình phát hành đã được kiểm tra.

Trong ứng dụng thật, hãy xử lý các tình huống như API chưa được bật, principal thiếu permission, version không tồn tại hoặc version đã Disabled/Destroyed. Không ghi payload vào log, exception message, tracing attribute hoặc metric label. Giới hạn thời gian giữ giá trị trong bộ nhớ và chỉ truyền nó đến thành phần thực sự cần sử dụng.

Ưu tiên gọi Secret Manager API trực tiếp từ ứng dụng. Nếu một tích hợp sản phẩm yêu cầu mount secret thành file hoặc đưa vào environment variable, hãy đánh giá kỹ quyền đọc filesystem, khả năng lộ qua debug endpoint, crash dump và log của process.

## 7. Rotation: thay secret mà không làm gián đoạn dịch vụ

Rotation là quá trình thay credential định kỳ hoặc khi có dấu hiệu bị lộ. Secret Manager hỗ trợ lịch rotation và phát thông báo qua Pub/Sub. **Thông báo rotation không tự thay mật khẩu ở database hoặc API bên ngoài.** Một subscriber hoặc rotation worker phải thực hiện các bước thay đổi ở hệ thống đích, thêm version mới vào Secret Manager và phối hợp phát hành ứng dụng.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant SM as Secret Manager
    participant PS as Pub/Sub
    participant RW as Cloud Run rotation worker
    participant DB as Database hoặc API bên ngoài
    participant APP as Ứng dụng

    SM->>PS: SECRET_ROTATE notification
    PS->>RW: Gửi sự kiện rotation
    RW->>DB: Tạo hoặc kích hoạt credential mới
    DB-->>RW: Trả credential mới
    RW->>SM: Thêm secret version mới
    RW-->>APP: Kích hoạt quy trình release/deploy
    APP->>SM: Đọc version ID đã được phê duyệt
    APP->>DB: Kết nối bằng credential mới
    RW->>DB: Thu hồi credential cũ sau khi xác nhận
~~~

Một rotation workflow nên có các bước:

1. Nhận thông báo từ Pub/Sub và xác định secret cần rotation.
2. Tạo credential mới ở hệ thống bên ngoài. Nếu có thể, giữ credential cũ còn hiệu lực trong giai đoạn chuyển tiếp.
3. Thêm credential mới thành secret version. Ghi lại version ID được tạo.
4. Kiểm tra credential mới bằng một health check hoặc thao tác xác thực an toàn.
5. Phát hành cấu hình để workload dùng version ID mới. Có thể triển khai dần theo từng nhóm instance.
6. Theo dõi lỗi kết nối và khả năng phục hồi. Nếu có lỗi, rollback cấu hình về version đã biết là hoạt động tốt.
7. Chỉ thu hồi credential cũ sau khi workload đã chuyển đổi và không còn phụ thuộc vào giá trị cũ.

Có ba cách phổ biến để workload lấy version:

- **Resolve trong release process**: pipeline xác định version mới, lưu version ID vào cấu hình deployment và phát hành ứng dụng. Đây là cách dễ kiểm soát rollout và rollback.
- **Resolve lúc ứng dụng khởi động**: mỗi instance đọc version mới nhất khi start. Cách này đơn giản hơn cho pipeline nhưng instance khởi động sau có thể nhận một version lỗi.
- **Resolve liên tục**: ứng dụng liên tục kiểm tra version mới. Cách này có thể khiến toàn bộ instance đổi credential gần như đồng thời, vì vậy cần kiểm soát rất cẩn thận.

Với production, lựa chọn version ID cụ thể trong release process thường tạo ra hành vi dễ dự đoán nhất. Hãy thiết kế khả năng tương thích chuyển tiếp: hệ thống đích có thể chấp nhận cả credential cũ và mới trong khoảng thời gian rollout.

## 8. Mã hóa, replication và audit

### 8.1. Mã hóa dữ liệu

Secret Manager mã hóa dữ liệu khi truyền bằng TLS và mã hóa dữ liệu khi lưu trữ theo mặc định. Nếu cần kiểm soát khóa do khách hàng quản lý, có thể cấu hình CMEK từ Cloud KMS cho secret phù hợp.

Khi dùng CMEK, cần quản lý cả vòng đời khóa Cloud KMS. Việc disable hoặc xóa key version đang cần để giải mã có thể khiến secret không thể truy cập. Key location cũng phải phù hợp với location của replica được mã hóa. Hãy kiểm tra yêu cầu này trước khi thay đổi key rotation hoặc key state.

### 8.2. Replication và data residency

Với global Secret Manager, automatic replication là lựa chọn mặc định phù hợp cho nhiều workload. User-managed replication hữu ích khi cần chỉ định các location. Nếu tổ chức phải lưu dữ liệu trong một khu vực địa lý cụ thể, hãy đánh giá regional Secret Manager cùng các ràng buộc tổ chức về location.

Replication tăng khả năng sẵn sàng của dữ liệu bí mật, nhưng không thay thế backup, quy trình khôi phục credential ở hệ thống đích hoặc việc kiểm soát ai được phép đọc secret.

### 8.3. Audit log

Bật Data Access audit logs để ghi nhận các thao tác truy cập payload, đặc biệt là AccessSecretVersion. Có thể cấu hình ở folder hoặc organization để chính sách logging được áp dụng nhất quán cho nhiều project.

Khi điều tra sự cố, hãy xác định:

- Principal nào đã gọi API.
- Secret/version nào được truy cập.
- Thời điểm và nguồn gọi.
- Hoạt động đó có khớp với lịch deployment hoặc rotation không.

Không đưa payload bí mật vào log ứng dụng. Audit log giúp truy vết danh tính và hành động, còn log ứng dụng nên chỉ ghi metadata cần thiết như tên secret, version ID, kết quả thành công/thất bại và correlation ID.

## 9. Disable, destroy và bảo vệ trước thao tác nhầm

Trước khi destroy một version, hãy cân nhắc disable trước. Disabled version không thể được đọc nhưng vẫn có thể được enable lại. Giữ version ở trạng thái Disabled trong một khoảng thời gian giúp phát hiện workload hoặc job cũ vẫn còn phụ thuộc vào nó.

Destroy là thao tác loại bỏ payload vĩnh viễn. Khi cần thêm lớp bảo vệ, Secret Manager hỗ trợ **delayed destruction**: quản trị viên cấu hình khoảng chờ từ 1 đến 1000 ngày; khi yêu cầu destroy, version bị disable ngay và được lên lịch xóa vĩnh viễn sau thời gian chờ. Trong thời gian chờ, quản trị viên có thể khôi phục version bằng cách enable hoặc disable lại version đó. Khi thời gian chờ kết thúc, payload bị hủy không thể khôi phục.

Ví dụ disable version 2:

~~~bash
gcloud secrets versions disable 2 --secret="orders-db-password"
~~~

Nếu cần khôi phục quyền đọc:

~~~bash
gcloud secrets versions enable 2 --secret="orders-db-password"
~~~

Chỉ destroy sau khi đã xác nhận không còn dependency:

~~~bash
gcloud secrets versions destroy 2 --secret="orders-db-password"
~~~

Quy trình vận hành nên phân tách quyền thêm version, quyền disable/enable/destroy và quyền đọc payload. Cấu hình delayed destruction giúp giảm rủi ro do thao tác nhầm hoặc phá hoại, nhưng không thay thế việc review thay đổi và giám sát notification.

## 10. Tình huống thực tế: quản lý mật khẩu database cho Orders

Giả sử dịch vụ Orders chạy trên Cloud Run và kết nối tới database production. Thiết kế có thể như sau:

1. Project production chứa secret orders-db-password.
2. Service account orders-runtime được gắn vào Cloud Run service.
3. IAM policy của riêng secret cấp roles/secretmanager.secretAccessor cho orders-runtime.
4. Pipeline phát hành có quyền thêm version bằng role phù hợp, nhưng không cần đọc payload cũ.
5. Ứng dụng Java đọc version ID được truyền từ cấu hình release.
6. Rotation worker nhận Pub/Sub notification, tạo credential mới ở database, thêm version mới và yêu cầu triển khai theo quy trình release.
7. Sau khi xác nhận các instance đã chuyển sang version mới, nhóm vận hành disable version cũ; destroy sau thời gian giữ lại theo chính sách.

Ví dụ trạng thái trong một lần rotation:

| Giai đoạn | Version đang dùng | Hành động |
|---|---:|---|
| Trước rotation | 3 | Workload production đọc version 3 |
| Tạo credential mới | 3 và 4 | Thêm version 4, kiểm tra kết nối |
| Rollout | 4 cho nhóm instance mới | Cập nhật cấu hình theo từng đợt |
| Hoàn tất | 4 | Theo dõi lỗi và xác nhận không còn workload dùng version 3 |
| Thu hồi | 4 | Disable version 3; destroy sau thời gian chờ nếu không còn phụ thuộc |

Nếu version 4 gây lỗi, pipeline có thể triển khai lại cấu hình dùng version 3 trong khi credential cũ vẫn còn hiệu lực. Đây là lý do cần phối hợp rotation ở database với rollout ở ứng dụng; chỉ thêm version mới vào Secret Manager chưa đủ để hoàn tất rotation.

## 11. Lỗi thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| PERMISSION_DENIED khi đọc secret | Service account thiếu secretmanager.versions.access hoặc IAM binding đặt sai phạm vi | Kiểm tra principal thực tế của workload và cấp Accessor trên đúng secret |
| Đã cấp IAM nhưng workload vẫn lỗi | Workload dùng service account khác, OAuth scope thiếu hoặc đang chạy cấu hình cũ | Xác minh ADC, service account gắn vào workload và scope cloud-platform nếu dùng Compute Engine/GKE |
| NOT_FOUND | Sai project ID, secret ID hoặc version ID | Kiểm tra resource name và project mà ứng dụng đang truy cập |
| Version không đọc được | Version Disabled hoặc Destroyed | Kiểm tra trạng thái; chỉ enable lại nếu payload còn tồn tại và được phép |
| Sau rotation ứng dụng kết nối thất bại | Credential ở hệ thống đích chưa đồng bộ, version mới sai hoặc rollout quá nhanh | Kiểm tra rotation worker, kiểm thử credential mới và rollback về version đã xác nhận |
| Tăng số lần gọi API đột ngột | Nhiều instance cùng đọc secret khi autoscaling hoặc restart | Đánh giá quota, thời điểm khởi động, chiến lược cache có kiểm soát và giới hạn tải |

Khi xử lý lỗi, không in secret payload ra terminal hoặc log để “kiểm tra nhanh”. Hãy kiểm tra version ID, trạng thái, IAM principal, audit log và kết quả xác thực với hệ thống đích.

## 12. Checklist thiết kế production

- [ ] Tách secret production khỏi môi trường dev/test bằng project hoặc ranh giới IAM phù hợp.
- [ ] Mỗi workload dùng service account riêng và ADC/Workload Identity.
- [ ] Chỉ cấp roles/secretmanager.secretAccessor trên những secret workload thực sự cần.
- [ ] Tách quyền đọc payload khỏi quyền tạo, disable và destroy version.
- [ ] Dùng version ID cụ thể trong cấu hình release production.
- [ ] Có quy trình kiểm tra credential mới trước khi rollout và giữ credential cũ trong giai đoạn chuyển tiếp.
- [ ] Bật Data Access audit logs cho thao tác đọc payload.
- [ ] Có lịch rotation và subscriber xử lý Pub/Sub notification.
- [ ] Disable version cũ trước khi destroy; cân nhắc delayed destruction.
- [ ] Đánh giá replication, regional secrets, CMEK và VPC Service Controls theo yêu cầu bảo mật/tuân thủ.
- [ ] Kiểm tra quota và hành vi khi nhiều instance khởi động cùng lúc.
- [ ] Không commit, in log hoặc truyền secret plaintext qua command line.

## 13. Câu hỏi tự kiểm tra

**1. Secret và secret version khác nhau ở điểm nào?**

Secret là tài nguyên quản lý metadata, policy và tập hợp version. Secret version chứa payload bí mật thực tế cùng trạng thái của version. Khi giá trị thay đổi, thêm version mới thay vì sửa payload cũ.

**2. Vì sao nên cấp Accessor trên một secret thay vì ở cấp project?**

Binding ở cấp secret chỉ cho phép principal đọc payload của secret đó. Binding ở cấp project có thể mở quyền đọc tất cả secret trong project, làm tăng phạm vi ảnh hưởng nếu service account bị xâm nhập.

**3. Disabled và Destroyed khác nhau thế nào?**

Disabled chặn truy cập nhưng payload vẫn tồn tại và có thể enable lại. Destroyed loại bỏ payload vĩnh viễn; sau khi thao tác hoàn tất thì không thể khôi phục.

**4. Lịch rotation của Secret Manager có tự thay mật khẩu trong database không?**

Không. Lịch rotation phát notification qua Pub/Sub. Một subscriber hoặc rotation worker phải cập nhật credential ở hệ thống đích, thêm version mới, triển khai ứng dụng và thu hồi credential cũ sau khi xác nhận.

**5. Vì sao production nên ghim version ID cụ thể?**

Version ID giúp mỗi lần phát hành dùng một giá trị xác định, có thể kiểm thử, theo dõi và rollback. Dùng latest có thể khiến workload nhận giá trị mới chưa được kiểm tra.

## 14. Tài liệu tham khảo

- [Secret Manager overview](https://cloud.google.com/secret-manager/docs/overview)
- [Secret Manager best practices](https://cloud.google.com/secret-manager/docs/best-practices)
- [Access control with IAM](https://cloud.google.com/secret-manager/docs/access-control)
- [Add a secret version](https://cloud.google.com/secret-manager/docs/add-secret-version)
- [Access a secret version](https://cloud.google.com/secret-manager/docs/access-secret-version)
- [Assign an alias to a secret version](https://cloud.google.com/secret-manager/docs/assign-alias-to-secret-version)
- [About rotation schedules](https://cloud.google.com/secret-manager/docs/rotation-recommendations)
- [Delay destruction of secret versions](https://cloud.google.com/secret-manager/docs/delay-destruction-of-secret-versions)
- [Enable customer-managed encryption keys](https://cloud.google.com/secret-manager/docs/cmek)

