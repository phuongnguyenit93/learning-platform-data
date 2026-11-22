# Application Default Credentials trong môi trường phát triển

Khi viết một ứng dụng Java truy cập Google Cloud Storage, Cloud SQL, Pub/Sub hoặc gọi API Google Cloud, lập trình viên cần cung cấp **danh tính** cho client library. Nếu phải tự chèn access token hay tải khóa bí mật vào mã nguồn cho mỗi môi trường, ứng dụng vừa khó triển khai vừa khó bảo vệ. Google Cloud giải quyết vấn đề này bằng **Application Default Credentials (ADC)**: một cơ chế thống nhất để thư viện tìm thông tin xác thực từ môi trường đang chạy.

Bài học thuộc chương **Công cụ và môi trường GCP** của mô-đun `CLOUD_PROVIDERS_GCP`. Đây là kỹ năng chuẩn bị trước khi xây dựng ứng dụng dùng IAM, VPC, Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua một tình huống phát triển ứng dụng, bạn sẽ thiết lập ADC cục bộ, kiểm tra quyền và hiểu vì sao cùng một đoạn mã có thể chạy trên máy cá nhân lẫn môi trường Google Cloud.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích ADC là gì, nó làm gì và điều gì vẫn phải cấu hình ngoài ADC.
2. Trình bày chính xác thứ tự tìm thông tin xác thực của ADC.
3. Thiết lập ADC cho máy phát triển bằng Google Cloud CLI mà không cần tải service account key.
4. Phân biệt danh tính của lệnh `gcloud` với danh tính mà ứng dụng sử dụng qua ADC.
5. Viết ứng dụng Java sử dụng client library và ADC để truy cập dịch vụ Google Cloud.
6. Chọn giữa user credentials, service account impersonation và federation theo tình huống.
7. Chẩn đoán những lỗi xác thực, phân quyền, project và quota thường gặp.

## 1. ADC là gì và giải quyết việc gì?

**Application Default Credentials** là cách các thư viện xác thực của Google Cloud **tự tìm một nguồn credential thích hợp** theo thứ tự đã định. Client library lấy credential tìm được, xin hoặc làm mới access token khi cần, rồi đính kèm thông tin xác thực vào yêu cầu gửi đến dịch vụ.

Ví dụ, thay vì ứng dụng Java có đoạn cấu hình chứa private key:

~~~java
// Không nên viết hoặc tải private key vào mã nguồn ứng dụng.
// String privateKey = "...";
~~~

ta sử dụng SDK hỗ trợ ADC:

~~~java
Storage storage = StorageOptions.getDefaultInstance().getService();
~~~

Khi chạy trên máy lập trình, ứng dụng có thể sử dụng thông tin xác thực của developer đã đăng nhập bằng `gcloud auth application-default login`. Khi triển khai lên Cloud Run, Compute Engine hoặc GKE đã cấu hình danh tính workload, thư viện thường lấy credential từ môi trường Google Cloud.

**ADC không phải là một loại tài khoản hay một vai trò IAM.** Nó là cơ chế **tìm nguồn credential**. Danh tính cuối cùng có thể là người dùng, service account hoặc danh tính được liên kết qua federation, tùy nguồn credential và cách cấu hình.

Để lời gọi API thành công, cần phân biệt bốn yếu tố:

| Yếu tố | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Authentication** (xác thực) | Ứng dụng đang đại diện cho ai? | Developer hoặc service account |
| **Authorization** (phân quyền) | Danh tính đó được phép làm gì? | `roles/storage.objectViewer` trên bucket |
| **Resource project** | Tài nguyên được truy cập thuộc project nào? | Project chứa bucket cần đọc |
| **Quota/billing project** | Project nào được dùng để ghi nhận quota hoặc yêu cầu tính phí theo cơ chế API? | Project phát triển đã cấu hình cho user ADC |

**Có ADC hợp lệ không bảo đảm ứng dụng có quyền.** Một tài khoản có thể xác thực thành công nhưng vẫn nhận `403 PERMISSION_DENIED` nếu IAM không cho phép truy cập tài nguyên.

## 2. ADC tìm credential theo thứ tự nào?

Khi client library cần credential mặc định, ADC sử dụng trình tự ưu tiên sau:

1. **Biến môi trường `GOOGLE_APPLICATION_CREDENTIALS`**: nếu được đặt, thư viện đọc tệp credential/configuration mà biến này trỏ đến.
2. **Tệp ADC trong thư mục cấu hình người dùng**: thường được tạo bằng `gcloud auth application-default login`.
3. **Danh tính gắn với môi trường chạy Google Cloud**: ví dụ service account được gắn với Compute Engine hoặc Cloud Run, lấy token qua metadata server; GKE còn có cơ chế cung cấp danh tính workload tương ứng.

~~~mermaid
flowchart TD
    A["Ứng dụng gọi Google Cloud client library"] --> B{"Có GOOGLE_APPLICATION_CREDENTIALS?"}
    B -->|Có| C["Đọc tệp credential/config đã chỉ định"]
    B -->|Không| D{"Có tệp ADC cục bộ?"}
    D -->|Có| E["Đọc ADC do gcloud application-default login tạo"]
    D -->|Không| F{"Có nguồn credential từ môi trường Google Cloud?"}
    F -->|Có| G["Sử dụng danh tính workload qua metadata server"]
    F -->|Không| H["Không tìm được ADC: báo lỗi xác thực"]
    C --> I["Lấy hoặc làm mới token"]
    E --> I
    G --> I
    I --> J["Gọi API; IAM và chính sách xác định quyền hiệu lực"]
~~~

**Thứ tự này là thứ tự ưu tiên, không phải xếp hạng độ an toàn.** Nếu `GOOGLE_APPLICATION_CREDENTIALS` trỏ đến một tệp không tồn tại hoặc không hợp lệ, ứng dụng có thể báo lỗi ngay; đừng trông chờ hệ thống tự bỏ qua và thử nguồn tiếp theo.

### 2.1. Nguồn thứ nhất: `GOOGLE_APPLICATION_CREDENTIALS`

Biến môi trường này chứa **đường dẫn tới tệp**, không chứa access token và cũng không chứa nguyên chuỗi JSON. Tệp được hỗ trợ có thể là:

- **Credential configuration file** cho Workload Identity Federation hoặc Workforce Identity Federation.
- **Service account key file** dạng JSON, nếu hệ thống buộc phải dùng khóa. Đây là lựa chọn cần hạn chế vì khóa có tuổi thọ dài và có nguy cơ bị lộ.
- Những định dạng credential khác mà thư viện xác thực hỗ trợ; không nên tự giả định mọi tệp JSON đều là credential ADC hợp lệ.

Ví dụ đường dẫn trên Linux/macOS:

~~~bash
export GOOGLE_APPLICATION_CREDENTIALS="/home/dev/.config/gcp/dev-credential-config.json"
~~~

Trong PowerShell:

~~~powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\gcp\dev-credential-config.json"
~~~

Cả hai lệnh chỉ đặt biến cho phiên shell tương ứng. File trong ví dụ là credential configuration đã được cấp hợp lệ, **không phải file cần tự tạo bằng cách điền khóa vào JSON**.

### 2.2. Nguồn thứ hai: tệp ADC cục bộ

Sau khi chạy:

~~~bash
gcloud auth application-default login
~~~

Google Cloud CLI tạo tệp credential tại vị trí mặc định của người dùng, thường là:

| Hệ điều hành | Vị trí tệp ADC cục bộ |
| --- | --- |
| Linux, macOS | `$HOME/.config/gcloud/application_default_credentials.json` |
| Windows | `%APPDATA%\gcloud\application_default_credentials.json` |

Đây là tệp nhạy cảm vì có thể chứa thông tin cho phép làm mới access token. **Không đưa tệp này vào Git, Docker image, bản build, tài liệu chia sẻ hoặc log.**

Chú ý: Nếu máy có đặt `GOOGLE_APPLICATION_CREDENTIALS`, ADC sẽ ưu tiên đường dẫn biến môi trường thay vì tệp ADC mặc định này.

### 2.3. Nguồn thứ ba: danh tính từ môi trường Google Cloud

Trong môi trường triển khai, có thể gắn một service account với workload. Client library truy cập hạ tầng cung cấp credential của Google Cloud để nhận token ngắn hạn. Cách ánh xạ cụ thể khác nhau giữa Compute Engine, Cloud Run và GKE Workload Identity Federation.

Khi triển khai đúng, mã Java sử dụng ADC **không cần đổi** chỉ vì chuyển từ máy developer lên Cloud Run. Thay đổi quan trọng là cấu hình danh tính và IAM của workload, không phải chép tệp credential cục bộ lên server.

## 3. Thiết lập ADC trên máy phát triển

Tình huống: nhóm Commerce viết một ứng dụng Java chạy trên laptop để đọc metadata của một object trong Cloud Storage. Môi trường phát triển dùng project `atlas-shop-dev`; bucket được tạo sẵn. Developer đã được quản trị viên cấp quyền đọc object phù hợp.

### Bước 1: Chuẩn bị CLI, project và API

Cài Google Cloud CLI rồi kiểm tra:

~~~bash
gcloud version
~~~

Đăng nhập CLI với tài khoản phù hợp:

~~~bash
gcloud auth login
gcloud auth list
~~~

Chọn project cho các lệnh CLI:

~~~bash
gcloud config set project atlas-shop-dev
gcloud config get-value project
~~~

Project ID chỉ là ví dụ; thay bằng ID thật. Nếu yêu cầu của ứng dụng là đọc Cloud Storage, hãy xác minh dịch vụ/API có sẵn và quyền tài khoản đáp ứng. Việc bật API, liên kết billing hoặc cấp IAM là các bước riêng; ADC không tự thực hiện.

### Bước 2: Tạo ADC của người dùng để phát triển cục bộ

~~~bash
gcloud auth application-default login
~~~

Lệnh thường mở luồng đăng nhập bằng trình duyệt để xin user credentials cho ADC. Khi hoàn tất, thư viện Google Cloud có thể dùng tệp ADC vừa tạo.

**Điểm rất dễ nhầm:** `gcloud auth login` và `gcloud auth application-default login` tạo hoặc sử dụng **hai nguồn credential khác nhau**. Đăng nhập thành công vào CLI không đồng nghĩa một chương trình Java đã có ADC đúng danh tính mong muốn.

Nếu trong lúc chạy lệnh thấy trình duyệt yêu cầu chọn tài khoản, hãy chọn tài khoản được phép sử dụng môi trường dev.

### Bước 3: Cấu hình quota project nếu cần

Với user credentials, một số API và client library yêu cầu chỉ định **quota project**. Có thể thiết lập bằng:

~~~bash
gcloud auth application-default set-quota-project atlas-shop-dev
~~~

Tài khoản có thể cần quyền `serviceusage.services.use` trên project được chọn; một vai trò thường dùng để cấp quyền này là `roles/serviceusage.serviceUsageConsumer`. Nếu lệnh bị từ chối, cần yêu cầu quản trị viên cấp quyền phù hợp hoặc chọn project quota hợp lệ.

Không nhầm ba giá trị sau:

- `gcloud config set project`: chọn project mặc định cho nhiều lệnh CLI.
- `gcloud auth application-default set-quota-project`: ghi quota project cho ADC cục bộ đang sử dụng khi áp dụng.
- Project ID trong mã ứng dụng: xác định project của tài nguyên hoặc request tùy API.

Ba giá trị có thể trùng nhau trong bài thực hành nhưng **không mặc nhiên là một**.

### Bước 4: Kiểm tra ADC

Có thể kiểm tra khả năng lấy token bằng lệnh:

~~~bash
gcloud auth application-default print-access-token
~~~

**Đầu ra là access token nhạy cảm.** Không gửi token vào chat, issue, ảnh chụp màn hình, log hoặc hệ thống giám sát. Để kiểm tra thực tế đầy đủ hơn, nên chạy một lời gọi API nhỏ tới tài nguyên dev bằng SDK như ở phần Java bên dưới.

Nếu trước đó đã đặt `GOOGLE_APPLICATION_CREDENTIALS`, hãy xác nhận file mà biến môi trường trỏ tới; nó có thể đang được ưu tiên hơn ADC cục bộ bạn vừa tạo.

### Bước 5: Kiểm tra danh tính và quyền thực tế

Phân tách việc kiểm tra:

1. **Xác thực:** SDK có tìm được ADC và lấy được token không?
2. **Danh tính:** Credential lấy từ developer, service account được impersonate hay nguồn khác?
3. **IAM:** Danh tính đó có permission thích hợp với bucket/object cụ thể không?
4. **Project:** Bạn đang gọi đúng tài nguyên trong project dev không?
5. **Quota/API:** API đã bật và quota project hợp lệ nếu được yêu cầu chưa?

Các lỗi `401`, `403` hoặc `404` có thể xuất phát từ những nguyên nhân khác nhau; không nên giải quyết bằng cách cấp `roles/owner` cho tài khoản phát triển.

## 4. Vì sao ứng dụng chạy được bằng gcloud nhưng Java lại báo lỗi?

Hai hệ thống credential có mục đích khác nhau:

| Thao tác | Credential thường sử dụng | Lệnh kiểm tra |
| --- | --- | --- |
| `gcloud storage ls`, `gcloud projects list` và lệnh CLI tương tự | Tài khoản CLI đã được đăng nhập hoặc cấu hình impersonation riêng của CLI | `gcloud auth list` |
| Ứng dụng Java qua Google Cloud client library | **ADC** theo thứ tự tìm kiếm | Chạy lệnh API từ ứng dụng; kiểm tra cấu hình ADC |
| `gcloud auth application-default login` | Tạo/cập nhật tệp ADC cục bộ | `gcloud auth application-default print-access-token` |
| Workload Cloud Run/GCE/GKE đã cấu hình danh tính | Credential dành cho workload tại môi trường chạy | Kiểm tra service account/workload identity và IAM gắn với workload |

Ví dụ, bạn đăng nhập `gcloud auth login` bằng `dev-a@example.com` nhưng `GOOGLE_APPLICATION_CREDENTIALS` vẫn trỏ đến một tệp của service account `old-test@example.iam.gserviceaccount.com`. Khi đó:

- CLI có thể gọi tài nguyên bằng danh tính `dev-a@example.com`.
- Ứng dụng Java lại có thể gọi bằng danh tính của tệp cấu hình cũ.

Vì vậy, “CLI chạy được” là bằng chứng hữu ích, **không phải bằng chứng rằng Java đang xác thực bằng cùng danh tính**.

Lưu ý thêm: Lệnh CLI có thể mang cấu hình project, impersonation và quota riêng. Đừng suy đoán credential thực tế của chương trình chỉ dựa trên tài khoản hiển thị trong `gcloud auth list`.

## 5. Ví dụ Java: đọc metadata của object trên Cloud Storage bằng ADC

Giả sử bạn đã cấu hình ADC và có quyền đọc một object trong bucket dev. Trong Maven/Gradle, thêm thư viện `com.google.cloud:google-cloud-storage` phiên bản tương thích với BOM/thư viện của dự án; SDK sẽ tự tìm ADC khi tạo service client.

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public class ReadObjectMetadata {
    public static void main(String[] args) {
        if (args.length != 3) {
            System.err.println(
                "Usage: ReadObjectMetadata <PROJECT_ID> <BUCKET_NAME> <OBJECT_NAME>"
            );
            System.exit(1);
        }

        String projectId = args[0];
        String bucketName = args[1];
        String objectName = args[2];

        // Storage client library tu tim Application Default Credentials.
        Storage storage = StorageOptions.newBuilder()
            .setProjectId(projectId)
            .build()
            .getService();

        Blob blob = storage.get(BlobId.of(bucketName, objectName));

        if (blob == null) {
            System.out.println("Object khong ton tai hoac khong tim thay.");
            return;
        }

        // In metadata; khong in token, private key hay credential JSON.
        System.out.println("Name: " + blob.getName());
        System.out.println("Size: " + blob.getSize());
        System.out.println("Content type: " + blob.getContentType());
    }
}
~~~

**Cách hoạt động:**

1. `StorageOptions.newBuilder()` tạo client cho Cloud Storage.
2. Không gọi `setCredentials(...)`: client library dùng cơ chế ADC mặc định.
3. `setProjectId(projectId)` giúp xác định project một cách tường minh cho ngữ cảnh client; bucket vẫn được chỉ định qua tên bucket.
4. `storage.get(...)` gửi lời gọi đến Cloud Storage bằng credential mà ADC tìm được.
5. IAM và cấu hình dịch vụ quyết định thao tác có được phép hay không.

**Điều kiện:** object phải tồn tại trong bucket, credential phải có quyền `storage.objects.get` thích hợp (chẳng hạn qua `roles/storage.objectViewer` ở phạm vi cần thiết), và môi trường phải có kết nối mạng/API phù hợp. Nếu thiếu quyền, SDK có thể ném exception với mã `403` thay vì trả về `null`.

Không có private key, access token hay email người dùng được hard-code trong ví dụ. Khi đưa cùng mã lên Cloud Run và cấu hình service account runtime đúng cách, SDK vẫn tìm credential thông qua ADC.

### Khi nào cần gọi GoogleCredentials trực tiếp?

Một số tình huống đòi hỏi dựng HTTP client hoặc SDK không tự tích hợp ADC. Với thư viện Java Auth, có thể lấy credential:

~~~java
import com.google.auth.oauth2.GoogleCredentials;

GoogleCredentials credentials = GoogleCredentials.getApplicationDefault();
~~~

Thư viện/API có thể cần thêm scope hoặc thiết lập tương ứng trước khi phát hành request. Việc lấy được đối tượng `GoogleCredentials` chưa chứng minh danh tính đó có quyền truy cập từng tài nguyên. Khi dùng Google Cloud client library chính thức như Storage, Pub/Sub hoặc Cloud SQL connector, hãy ưu tiên cơ chế tích hợp ADC có sẵn và tránh tự quản lý vòng đời token.

## 6. User ADC hay service account impersonation?

Đăng nhập ADC với tài khoản developer là con đường nhanh để chạy thử trên laptop, nhưng ứng dụng thực tế thường chạy bằng service account. Nếu muốn **thử nghiệm cục bộ gần với danh tính runtime** mà không tải service account key, có thể dùng **service account impersonation**.

### 6.1. Nguyên lý impersonation

- Developer đăng nhập bằng tài khoản riêng.
- Developer được cấp quyền tạo token thay mặt service account, thường qua `roles/iam.serviceAccountTokenCreator` trên service account đích.
- Google Cloud cấp token ngắn hạn đại diện cho service account đó.
- API kiểm tra quyền trên tài nguyên theo danh tính service account, đồng thời việc cấp token phụ thuộc quyền impersonation của developer.

~~~mermaid
sequenceDiagram
    participant D as Developer
    participant A as ADC / Auth library
    participant I as IAM Credentials API
    participant S as Google Cloud service
    D->>A: Chạy ứng dụng Java
    A->>I: Xin token đại diện service account
    I-->>A: Token ngắn hạn khi được phép
    A->>S: Gửi request với token service account
    S-->>A: Kết quả theo quyền IAM của service account
~~~

Lệnh dùng cho môi trường phát triển với Google Cloud CLI:

~~~bash
gcloud auth application-default login \
  --impersonate-service-account=app-dev@atlas-shop-dev.iam.gserviceaccount.com
~~~

Java là một trong các ngôn ngữ được Google Cloud hỗ trợ cho cách tạo ADC bằng CLI với service account impersonation; với ngôn ngữ hay thư viện khác cần xác minh khả năng hỗ trợ.

Để cách này hoạt động, bạn cần:

1. Có quyền impersonate service account đích, không tự cấp quyền này nếu không có thẩm quyền.
2. Service account đích có những vai trò IAM cần để gọi API dự kiến.
3. IAM Credentials API cùng quota và quyền dịch vụ liên quan được cấu hình phù hợp.
4. Phiên đăng nhập gốc của developer còn hợp lệ để xin token ngắn hạn.

Impersonation hữu ích để kiểm tra quyền của ứng dụng trong quá trình phát triển; nó vẫn cần đánh giá riêng các khác biệt về mạng, cấu hình runtime, vị trí triển khai và những policy áp dụng trong môi trường thật.

### 6.2. Khi nào dùng Workload Identity Federation?

Nếu công cụ phát triển hoặc hệ thống CI/CD chạy ngoài Google Cloud và có nhà cung cấp danh tính (IdP) phù hợp, **Workload Identity Federation (WIF)** cho phép dùng danh tính bên ngoài để nhận credential ngắn hạn thay vì lưu khóa service account lâu dài. ADC có thể đọc một **credential configuration file** cho WIF qua `GOOGLE_APPLICATION_CREDENTIALS`.

Để triển khai WIF phải có cấu hình trust/federation từ phía quản trị, nguồn token của IdP và các vai trò cần thiết. Việc chỉ đặt biến môi trường tới một file JSON không tự tạo quyền truy cập.

| Cách xác thực | Thích hợp nhất | Điểm cần chú ý |
| --- | --- | --- |
| **User ADC** (`application-default login`) | Laptop developer, bài thực hành và thử nghiệm ngắn | Danh tính người dùng; phải quản lý quota project và quyền phù hợp |
| **Service account impersonation** | Phát triển local cần mô phỏng quyền service account runtime | Cần quyền tạo token và hỗ trợ từ SDK |
| **Workload Identity Federation** | Workload/công cụ ngoài Google Cloud với IdP sẵn có | Cần cấu hình federation, nguồn identity và trust |
| **Service account được gắn trực tiếp vào workload** | Compute Engine, Cloud Run và nhiều môi trường Google Cloud | Ưu tiên cho runtime; cấu hình IAM cho workload |
| **Service account key file** | Trường hợp đặc biệt không có phương án an toàn hơn | Rủi ro khóa dài hạn; tránh nếu có thể |

## 7. Quy tắc với GOOGLE_APPLICATION_CREDENTIALS

### Dùng trong một phiên shell

Nếu bài thực hành trước tạo credential configuration hợp lệ cho federation, có thể đặt đường dẫn:

~~~bash
# Linux/macOS
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/credential-config.json"

# Xem giá trị biến môi trường
printenv GOOGLE_APPLICATION_CREDENTIALS

# Bỏ override để ứng dụng quay lại tra cứu ADC mặc định
unset GOOGLE_APPLICATION_CREDENTIALS
~~~

Tương đương trong PowerShell:

~~~powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\path\to\credential-config.json"
$env:GOOGLE_APPLICATION_CREDENTIALS

# Xóa override trong phiên PowerShell hiện tại
Remove-Item Env:GOOGLE_APPLICATION_CREDENTIALS
~~~

Hãy giữ cấu hình theo môi trường: cấu hình cho dev không được vô tình áp dụng cho production.

### Những lỗi cấu hình thường gặp

- Đặt biến tới **thư mục** thay vì đường dẫn một **file** credential/config hợp lệ.
- Đặt biến tới file của project cũ và quên xóa, làm ứng dụng dùng sai danh tính.
- Đặt biến trong shell A nhưng IDE mở từ môi trường B nên tiến trình Java không nhận được biến.
- Cho rằng `GOOGLE_APPLICATION_CREDENTIALS` là nơi nhập **project ID**; trên thực tế đây là đường dẫn tới credential.
- Copy tệp `application_default_credentials.json` hoặc service account key vào source code repo hay container image.
- Đưa token, refresh token hoặc nội dung file credential vào log khi debug.

**Với phát triển local thông thường, bạn không cần tự đặt `GOOGLE_APPLICATION_CREDENTIALS` chỉ để ADC hoạt động.** Lệnh `gcloud auth application-default login` đã tạo tệp ở vị trí mặc định.

## 8. ADC giữa laptop, IDE, container và môi trường GCP

Một codebase có thể chạy trong các môi trường sau:

| Nơi chạy | Nguồn credential nên dùng | Cách áp dụng |
| --- | --- | --- |
| Terminal laptop | User ADC hoặc impersonation | `gcloud auth application-default login` |
| IDE (IntelliJ IDEA, VS Code) | Cùng ADC local nếu tiến trình có quyền truy cập file | Kiểm tra user/hệ điều hành, biến môi trường và cấu hình chạy |
| Container Docker trên laptop | Credential/config được truyền vào container theo phương án được phê duyệt | Lưu ý filesystem container **không tự có** thư mục ADC của host |
| Cloud Run | Service account gắn với service/revision | Để thư viện tự lấy token từ môi trường runtime |
| Compute Engine | Service account gắn với VM, cùng IAM và access scopes phù hợp | Dùng metadata server, tránh chép khóa vào VM |
| GKE | Cấu hình Workload Identity Federation for GKE và quyền của Kubernetes workload | Không mặc định đồng nhất danh tính pod với node |
| CI/CD ngoài Google Cloud | WIF/impersonation khi có thể | Dùng token ngắn hạn; không commit khóa dài hạn |

### Docker: vì sao “chạy trên host được, trong container lại lỗi”?

ADC có thể tìm được tệp ở `$HOME/.config/gcloud/application_default_credentials.json` trên laptop, nhưng container có filesystem riêng. Cùng một tệp không tự xuất hiện trong container.

Trong môi trường phát triển được phép sử dụng user ADC, một cách thử nghiệm là **mount chỉ đọc** tệp ADC vào nơi mà thư viện trong container có thể tìm thấy, và dùng biến môi trường để chỉ đúng đường dẫn bên trong container:

~~~bash
docker run --rm \
  -v "$HOME/.config/gcloud/application_default_credentials.json:/var/run/gcp/adc.json:ro" \
  -e GOOGLE_APPLICATION_CREDENTIALS=/var/run/gcp/adc.json \
  my-java-dev-image
~~~

Ví dụ này dành cho host Linux/macOS, với image và file ADC đã tồn tại. Trên Windows cần điều chỉnh đường dẫn và cách mount cho Docker Desktop. File mount chứa thông tin xác thực nhạy cảm; chỉ dùng với container dev đáng tin cậy. Không bake credential vào image hoặc đưa sang môi trường production theo cách này.

Nếu tổ chức đã có federation hoặc công cụ chạy container tự cấp identity, hãy ưu tiên cơ chế đó thay vì chia sẻ credential cá nhân.

## 9. Lỗi thường gặp và quy trình chẩn đoán

| Triệu chứng | Khả năng thường gặp | Bước kiểm tra |
| --- | --- | --- |
| `Could not load the default credentials` / `DefaultCredentialsError` | Không có tệp/nguồn ADC hoặc biến trỏ tới đường dẫn sai | Kiểm tra `GOOGLE_APPLICATION_CREDENTIALS`; thiết lập ADC local nếu cần |
| `401 UNAUTHENTICATED`, `invalid_grant` | Credential hết hiệu lực, bị thu hồi, không thể refresh | Đăng nhập lại ADC; kiểm tra thời gian hệ thống và trạng thái tài khoản |
| `403 PERMISSION_DENIED` | Có token nhưng thiếu quyền IAM hoặc bị deny/policy chặn | Kiểm tra danh tính thực tế, permission, phạm vi project/bucket, policy |
| `403` liên quan quota project hoặc `serviceusage.services.use` | User ADC không có quyền sử dụng quota project | Kiểm tra `set-quota-project` và IAM trên quota project |
| `API has not been used / is disabled` | Dịch vụ/API cần thiết chưa bật trên project tương ứng | Kiểm tra Service Usage và quyền bật API |
| CLI gọi được nhưng Java thất bại | CLI và ADC dùng credential hoặc project khác nhau | So sánh `gcloud auth list` với nguồn ADC, env var và project trong code |
| Lỗi tìm metadata server trên laptop | Không có nguồn ADC local; thư viện thử nguồn runtime rồi thất bại | Tạo ADC local hoặc cấu hình credential hợp lệ |
| IDE chạy được, Docker không chạy | File ADC chưa có trong container hoặc path khác | Kiểm tra filesystem, biến môi trường và cách cung cấp credential |
| `404 NOT_FOUND` | Sai tên bucket/object/project hoặc không tồn tại; một số API có thể che giấu quyền bằng 404 | Kiểm tra chính xác resource ID, location và quyền |
| `429 RESOURCE_EXHAUSTED` | Vượt quota/rate limit | Kiểm tra quota project, giới hạn API và tốc độ yêu cầu |

### Trình tự debug thực tế

~~~mermaid
flowchart TD
    A["Lời gọi API thất bại"] --> B{"SDK tìm được ADC?"}
    B -->|Không| C["Kiểm tra biến môi trường, file ADC và môi trường chạy"]
    B -->|Có| D{"Lấy token được?"}
    D -->|Không| E["Đăng nhập lại / kiểm tra impersonation, WIF, refresh"]
    D -->|Có| F{"API trả 403?"}
    F -->|Có| G["Kiểm tra principal, IAM, policy, API và quota project"]
    F -->|Không| H["Đọc mã lỗi: 404, 429, network, dữ liệu request..."]
~~~

Điều quan trọng khi debug là **không dùng access token làm vật chứng trong log hoặc issue**. Thay vào đó, ghi lại thời điểm, project ID, tài nguyên đích, mã lỗi, request ID nếu có và nguồn credential *theo loại* (user ADC/impersonation/federation/runtime). Tránh ghi giá trị token, refresh token hoặc private key.

## 10. Bảo vệ credential trong môi trường phát triển

### Các nguyên tắc nên áp dụng

1. **Không commit credential**: thêm quy tắc ignore thích hợp, rà soát thay đổi trước khi commit, dùng cơ chế quản lý secret nếu ứng dụng cần secret riêng.
2. **Ưu tiên credential ngắn hạn**: user ADC cho local; impersonation hoặc federation khi cần đóng vai service account; môi trường GCP dùng identity gắn trực tiếp cho workload.
3. **Cấp quyền IAM tối thiểu**: thử đọc bucket thì chỉ cấp permission đọc tương ứng, không dùng vai trò Owner/Editor làm mặc định.
4. **Tách môi trường dev/prod**: dùng project và danh tính riêng, không sử dụng credential của production cho các bài thực hành.
5. **Không xuất credential vào log, màn hình chia sẻ hoặc hình ảnh**: cả access token lẫn file ADC đều nhạy cảm.
6. **Đặt hạn chế trên tệp local**: quyền đọc file phù hợp với tài khoản phát triển, không để thư mục chia sẻ tự động sao lưu hoặc công khai.
7. **Thu hồi credential không còn dùng**: với ADC do lệnh login cục bộ tạo, có thể dùng `gcloud auth application-default revoke`; điều này ảnh hưởng đến phiên ADC local liên quan và có thể buộc ứng dụng đăng nhập lại.

### Quy trình kết thúc một bài lab

~~~bash
# Kiểm tra credential local khi cần (không chia sẻ token)
gcloud auth application-default print-access-token

# Thu hồi credential ADC local do gcloud tạo nếu không cần dùng nữa
gcloud auth application-default revoke
~~~

Việc thu hồi credential không tự xóa bucket, VM hay các tài nguyên Google Cloud đã tạo. Những tài nguyên tính phí và quyền IAM vẫn cần được quản lý, thu hồi hoặc dọn dẹp qua quy trình riêng.

## 11. Tình huống triển khai: từ máy developer lên Cloud Run

Nhóm Commerce có ứng dụng Java cần đọc metadata file ảnh trong Cloud Storage. Quy trình phát triển:

**Trên laptop:**

1. Developer có quyền đọc bucket dev trong project `atlas-shop-dev`.
2. Dùng `gcloud auth application-default login` hoặc impersonate service account phát triển.
3. Chạy `ReadObjectMetadata` bằng project ID, bucket và object của dev.
4. Nếu nhận `403`, kiểm tra quyền của **danh tính ADC**, không thay đổi code để nhúng khóa.

**Khi triển khai Cloud Run:**

1. Tạo hoặc lựa chọn service account runtime với quyền đọc tài nguyên được phép.
2. Cấu hình service Cloud Run sử dụng service account đó.
3. Triển khai cùng đoạn code sử dụng client library và ADC.
4. Cấu hình project, bucket, location, kết nối mạng và quan sát vận hành phù hợp.
5. Theo dõi lỗi `401/403`, request latency, quota và chi phí theo project.

Kết quả mong muốn là **mã nguồn không phụ thuộc vào nơi cấp credential**. Tuy nhiên, người triển khai vẫn chịu trách nhiệm chọn danh tính runtime chính xác và cấp IAM trong phạm vi tối thiểu.

~~~mermaid
flowchart LR
    A["Java source code"] --> B["Google Cloud client library"]
    B --> C{"Môi trường chạy"}
    C --> D["Laptop: user ADC / impersonation"]
    C --> E["Cloud Run: runtime service account"]
    D --> F["Cloud Storage API"]
    E --> F
    F --> G["IAM và cấu hình tài nguyên quyết định kết quả"]
~~~

Cùng nguyên tắc này áp dụng khi học các phần khác của mô-đun GCP: chương trình kết nối Pub/Sub, Cloud SQL connector, API quản lý GKE hay dịch vụ lưu trữ có thể sử dụng ADC thông qua SDK phù hợp. Nhưng quyền truy cập, endpoint, kết nối VPC, region/zone, API và chi phí luôn phải cấu hình theo nhu cầu dịch vụ cụ thể.

## 12. Bài tập tự kiểm tra

**Câu 1.** Bạn chạy `gcloud auth login` thành công nhưng ứng dụng Java báo không tìm thấy default credentials. Nguyên nhân có thể là gì?

*Đáp án gợi ý:* CLI credential và ADC là hai nguồn riêng. Cần cấu hình ADC bằng `gcloud auth application-default login` hoặc nguồn credential hợp lệ khác; kiểm tra biến `GOOGLE_APPLICATION_CREDENTIALS` nếu có.

**Câu 2.** Máy có tệp ADC local hợp lệ nhưng biến `GOOGLE_APPLICATION_CREDENTIALS` trỏ tới file đã bị xóa. ADC có chắc sẽ bỏ qua lỗi và dùng tệp local không?

*Đáp án gợi ý:* Không. Biến môi trường có ưu tiên cao; đường dẫn sai có thể làm ứng dụng lỗi. Cần sửa hoặc xóa biến đó.

**Câu 3.** Một lập trình viên đã lấy được access token nhưng API trả `403 PERMISSION_DENIED`. Có phải ADC thất bại?

*Đáp án gợi ý:* Chưa chắc. ADC có thể đã xác thực thành công, nhưng IAM, deny policy, quota project hoặc chính sách dịch vụ không cho phép yêu cầu. Phải đọc thông điệp lỗi và kiểm tra quyền hiệu lực.

**Câu 4.** Bạn muốn kiểm tra code Java với quyền của service account chạy Cloud Run mà không tải service account key xuống laptop. Chọn phương án nào?

*Đáp án gợi ý:* Dùng service account impersonation khi tài khoản được cấp quyền và thư viện hỗ trợ. Dùng tệp khóa dài hạn chỉ khi đã đánh giá và không có phương án an toàn hơn.

**Câu 5.** Bạn đưa Java app từ laptop lên Cloud Run và giữ nguyên code `StorageOptions...getService()`. Cần làm gì để app lấy được credential?

*Đáp án gợi ý:* Cấu hình service account của Cloud Run và cấp IAM thích hợp; client library tìm credential của runtime qua ADC. Đồng thời kiểm tra project, bucket, billing/API, networking và cấu hình vận hành.

**Câu 6.** Vì sao việc đặt `gcloud config set project atlas-shop-dev` không luôn xử lý được lỗi quota project của user ADC?

*Đáp án gợi ý:* Đó là cấu hình project của CLI, còn quota project gắn với ADC có thể cần thiết lập và kiểm tra riêng bằng `gcloud auth application-default set-quota-project`.

## 13. Những điểm cần nhớ

- ADC là **cơ chế tìm credential**, không tự cấp quyền IAM.
- Thứ tự tìm nguồn: **`GOOGLE_APPLICATION_CREDENTIALS` → tệp ADC local → credential từ môi trường Google Cloud**.
- `gcloud auth login` dùng cho CLI; `gcloud auth application-default login` tạo credential mà ứng dụng local có thể dùng.
- Trong phát triển, ưu tiên user ADC hoặc service account impersonation; tránh service account key dài hạn.
- Khi chạy trên Google Cloud, ưu tiên service account hoặc identity gắn với workload, không sao chép ADC của laptop.
- Phân biệt **danh tính**, **IAM**, **resource project** và **quota project** khi chẩn đoán lỗi.
- SDK Java có thể dùng ADC tự động; hãy cấu hình quyền ở Google Cloud thay vì nhúng token vào mã.

## Tài liệu tham khảo

- [How Application Default Credentials works — Google Cloud](https://cloud.google.com/docs/authentication/application-default-credentials)
- [Set up Application Default Credentials for local development](https://cloud.google.com/docs/authentication/set-up-adc-local-dev-environment)
- [gcloud auth application-default login](https://cloud.google.com/sdk/gcloud/reference/auth/application-default/login)
- [gcloud auth application-default set-quota-project](https://cloud.google.com/sdk/gcloud/reference/auth/application-default/set-quota-project)
- [Service account impersonation](https://cloud.google.com/iam/docs/service-account-impersonation)
- [Authenticate for using client libraries](https://cloud.google.com/docs/authentication/client-libraries)

