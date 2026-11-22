# Thực hành loại bỏ khóa và mật khẩu khỏi mã nguồn Java

Trong một ứng dụng Java chạy trên Google Cloud, mật khẩu cơ sở dữ liệu, API key, access token và khóa mã hóa đều có thể bị lộ nếu được viết trực tiếp trong mã nguồn hoặc tệp cấu hình rồi commit lên Git. Khi một bí mật đã đi vào lịch sử Git, việc xóa dòng mã đó không làm bí mật trở nên an toàn trở lại: bản sao cũ, nhánh khác, log CI/CD và artifact vẫn có thể chứa giá trị đã lộ.

Bài thực hành này thuộc module **CLOUD_PROVIDERS_GCP**. Module giúp người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu; đồng thời lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Trong phạm vi bài học, chúng ta tập trung đưa mật khẩu và thông tin xác thực ra khỏi mã nguồn Java, lưu chúng trong **Secret Manager**, cấp quyền truy cập bằng **IAM**, và sử dụng danh tính của workload để ứng dụng lấy bí mật khi chạy.

## Mục tiêu

Sau bài học, bạn có thể:

- Nhận diện thông tin nào là bí mật và thông tin nào chỉ là cấu hình thông thường.
- Phân biệt vai trò của Secret Manager và Cloud Key Management Service (Cloud KMS).
- Tạo secret và phiên bản secret trên Google Cloud.
- Cấp quyền đọc đúng secret cho service account chạy ứng dụng.
- Dùng Google Cloud Java client library và Application Default Credentials (ADC) để đọc secret.
- Lập kế hoạch xoay vòng, thu hồi và kiểm tra bí mật đã bị lộ.

## 1. Nhận diện dữ liệu cần đưa ra khỏi mã nguồn

Một giá trị cần được bảo vệ nếu người khác có thể dùng nó để đăng nhập, gọi API, truy cập dữ liệu hoặc thực hiện thao tác thay mặt ứng dụng. Những ví dụ thường gặp gồm:

| Dữ liệu | Ví dụ | Cách quản lý phù hợp |
|---|---|---|
| Mật khẩu | Mật khẩu cơ sở dữ liệu | Secret Manager |
| API key hoặc access token | Khóa gọi dịch vụ bên thứ ba | Secret Manager |
| Client secret | Bí mật của OAuth client | Secret Manager |
| Khóa riêng hoặc chứng thư có khóa riêng | Private key dùng để xác thực | Secret Manager hoặc dịch vụ quản lý danh tính/chứng thư phù hợp |
| Khóa mã hóa dữ liệu | Khóa dùng để mã hóa hoặc giải mã dữ liệu ứng dụng | Cloud KMS |
| Tên project, region, tên secret | my-project, asia-southeast1, orders-db-password | Cấu hình ứng dụng; các giá trị này thường không phải bí mật |

Không phải chuỗi nào trông khó đọc cũng là bí mật. Ngược lại, một chuỗi ngắn như mật khẩu hoặc token vẫn có thể cấp quyền truy cập rất lớn. Hãy phân loại theo khả năng cấp quyền, không theo độ dài hay hình thức của chuỗi.

### Ví dụ mã nguồn không an toàn

~~~java
public final class DatabaseConfig {
    private static final String DB_URL =
            "jdbc:postgresql://10.20.0.5:5432/orders";
    private static final String DB_USERNAME = "orders_app";
    private static final String DB_PASSWORD = "change-me-in-production";
}
~~~

Mật khẩu trong ví dụ trên có thể bị lưu trong Git, bản build, ảnh container, log debug hoặc bản sao mã nguồn của nhà phát triển. Đổi tên biến, mã hóa Base64 hay chuyển chuỗi sang một lớp Java khác không giải quyết được vấn đề nếu giá trị bí mật vẫn nằm trong artifact hoặc kho mã.

Một tệp cấu hình được commit cũng có rủi ro tương tự:

~~~yaml
database:
  username: orders_app
  password: change-me-in-production
~~~

Tệp cấu hình chỉ an toàn khi nó không chứa giá trị bí mật thực tế. Có thể commit tên secret, tên project hoặc tên biến cấu hình; không commit nội dung mật khẩu hay token.

## 2. Chọn đúng dịch vụ: Secret Manager hay Cloud KMS?

Hai dịch vụ thường được nhắc cùng nhau nhưng giải quyết hai nhu cầu khác nhau.

**Secret Manager** lưu trữ và phân phối dữ liệu bí mật như mật khẩu, token, API key và nội dung chứng thư. Secret có thể có nhiều phiên bản; quyền truy cập được kiểm soát bằng IAM và hoạt động truy cập có thể được ghi nhận trong Cloud Audit Logs. Ứng dụng cần lấy lại giá trị bí mật để kết nối cơ sở dữ liệu hoặc gọi API thường dùng Secret Manager.

**Cloud KMS** quản lý khóa mật mã và cung cấp thao tác mật mã như mã hóa, giải mã, ký hoặc xác minh chữ ký. Ứng dụng thường gọi Cloud KMS để thực hiện thao tác bằng khóa được quản lý trong dịch vụ, thay vì tự nhúng khóa mã hóa dài hạn vào mã nguồn. Cloud KMS cũng có thể cung cấp khóa do khách hàng quản lý (CMEK) cho các dịch vụ Google Cloud hỗ trợ.

Ví dụ lựa chọn:

- Ứng dụng cần mật khẩu để mở kết nối PostgreSQL: lưu mật khẩu trong Secret Manager.
- Ứng dụng cần gọi API thanh toán bằng token: lưu token trong Secret Manager.
- Ứng dụng cần mã hóa dữ liệu nghiệp vụ bằng khóa được kiểm soát tập trung: dùng Cloud KMS; với dữ liệu lớn, cân nhắc mô hình envelope encryption.
- Secret Manager cần được mã hóa bằng khóa do tổ chức kiểm soát: cấu hình CMEK bằng Cloud KMS nếu yêu cầu bảo mật và dịch vụ hỗ trợ phù hợp.

Không nên dùng Cloud KMS như một kho lưu mật khẩu mà ứng dụng phải đọc lại thường xuyên. Cũng không nên lưu một khóa mã hóa dài hạn trong Secret Manager rồi coi như đã có đầy đủ quản lý vòng đời khóa. Hãy chọn dịch vụ theo mục đích của dữ liệu.

## 3. Luồng truy cập bí mật trên Google Cloud

Ứng dụng không cần chứa khóa service account để gọi Secret Manager. Khi triển khai trên Cloud Run, Compute Engine hoặc GKE, hãy gắn danh tính runtime phù hợp cho workload. Java client library dùng ADC để lấy thông tin xác thực từ môi trường chạy.

~~~mermaid
flowchart LR
    A["Ứng dụng Java<br/>Cloud Run / GKE / Compute Engine"]
    B["Service account của workload"]
    C["IAM<br/>secretAccessor trên secret cần dùng"]
    D["Secret Manager API"]
    E["Phiên bản secret"]
    A -->|"ADC"| B
    B -->|"được cấp quyền"| C
    A -->|"đọc secret qua API"| D
    D --> E
~~~

Luồng này có ba thành phần quan trọng:

1. **Danh tính workload** xác định ứng dụng nào đang yêu cầu truy cập.
2. **IAM** quyết định danh tính đó được đọc secret nào.
3. **Secret Manager** trả về phiên bản secret được yêu cầu sau khi kiểm tra quyền.

Hãy tạo service account riêng cho từng ứng dụng hoặc workload có ranh giới quyền khác nhau. Tránh dùng một service account có quyền đọc tất cả secret trong project cho mọi dịch vụ.

## 4. Tạo secret và cấp quyền tối thiểu

Các lệnh dưới đây dùng Google Cloud CLI. Thay các giá trị định danh bằng project, secret và service account của môi trường triển khai. Không đưa mật khẩu thật trực tiếp vào câu lệnh có thể được lưu trong shell history.

### Bước 1: Chọn project và bật Secret Manager API

~~~bash
export PROJECT_ID="your-project-id"
export SECRET_ID="orders-db-password"
export RUNTIME_SA="orders-api@your-project-id.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud services enable secretmanager.googleapis.com \
  --project="$PROJECT_ID"
~~~

Project ID và tên secret là thông tin định danh, không phải nội dung bí mật. Hãy xác nhận đang thao tác đúng project trước khi tạo tài nguyên hoặc cấp quyền.

### Bước 2: Tạo secret và thêm phiên bản

~~~bash
gcloud secrets create "$SECRET_ID" \
  --project="$PROJECT_ID" \
  --replication-policy="automatic"

gcloud secrets versions add "$SECRET_ID" \
  --project="$PROJECT_ID" \
  --data-file="/secure/path/orders-db-password.txt"
~~~

Tệp đầu vào phải được tạo và bảo vệ bằng quy trình phù hợp với tổ chức; không đặt tệp trong repository, thư mục build hoặc thư mục được đồng bộ công khai. Nếu quy trình cấp phát secret dùng pipeline, hãy lấy giá trị từ kho bí mật của pipeline và tránh in giá trị ra log.

Một secret có thể có nhiều phiên bản. Khi thay mật khẩu, thêm phiên bản mới thay vì sửa mã nguồn để chứa mật khẩu mới. Sau khi ứng dụng đã chuyển sang phiên bản mới và được xác minh, vô hiệu hóa hoặc hủy phiên bản cũ theo chính sách lưu giữ của tổ chức.

### Bước 3: Chỉ cấp quyền đọc cho service account cần thiết

~~~bash
gcloud secrets add-iam-policy-binding "$SECRET_ID" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/secretmanager.secretAccessor"
~~~

Vai trò **roles/secretmanager.secretAccessor** cho phép đọc payload của secret. Cấp vai trò ở cấp secret giúp giới hạn phạm vi quyền tốt hơn việc cấp cùng vai trò trên toàn project. Người vận hành tạo secret và quản lý IAM có thể cần quyền quản trị riêng; không cấp các quyền đó cho service account chạy ứng dụng nếu ứng dụng chỉ cần đọc secret.

Nếu dùng Cloud Run, hãy cấu hình service account này làm runtime service account của service. Với Compute Engine, gắn service account phù hợp vào VM. Với GKE, cấu hình Workload Identity Federation for GKE để Kubernetes workload sử dụng danh tính Google Cloud được chỉ định. Tên và cách gắn danh tính khác nhau theo nền tảng, nhưng nguyên tắc vẫn là workload nhận đúng danh tính và chỉ có quyền cần thiết.

## 5. Đọc secret từ ứng dụng Java

### Thêm thư viện

Với Maven, thêm Google Cloud Secret Manager client library. Dự án nên quản lý phiên bản thư viện thông qua Google Cloud Libraries BOM trong **dependencyManagement** để các thư viện Google Cloud dùng các phiên bản tương thích.

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-secretmanager</artifactId>
</dependency>
~~~

### Tạo lớp đọc secret

Ví dụ sau tạo client một lần và tái sử dụng trong vòng đời ứng dụng. Tham số project, secret ID và version là cấu hình định danh; payload trả về mới là nội dung bí mật.

~~~java
import com.google.cloud.secretmanager.v1.AccessSecretVersionResponse;
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import com.google.cloud.secretmanager.v1.SecretVersionName;

import java.io.IOException;

public final class SecretReader implements AutoCloseable {
    private final SecretManagerServiceClient client;

    public SecretReader() throws IOException {
        // Client tự sử dụng Application Default Credentials.
        this.client = SecretManagerServiceClient.create();
    }

    public String read(
            String projectId,
            String secretId,
            String versionId) {
        SecretVersionName versionName =
                SecretVersionName.of(projectId, secretId, versionId);

        AccessSecretVersionResponse response =
                client.accessSecretVersion(versionName);

        return response.getPayload().getData().toStringUtf8();
    }

    @Override
    public void close() {
        client.close();
    }
}
~~~

**SecretManagerServiceClient.create()** dùng ADC. Khi chạy trên Google Cloud, ADC có thể lấy danh tính từ service account được gắn vào workload. Khi phát triển cục bộ, nhà phát triển có thể thiết lập ADC bằng tài khoản được phép truy cập secret trong môi trường phát triển:

~~~bash
gcloud auth application-default login
gcloud config set project "$PROJECT_ID"
~~~

Không tải khóa JSON của service account về máy chỉ để làm cho ví dụ chạy được. Khóa service account dạng tệp là thông tin xác thực dài hạn; nếu bị sao chép hoặc commit, người khác có thể sử dụng nó cho đến khi khóa bị thu hồi. Ưu tiên ADC dựa trên danh tính được quản lý, hoặc Workload Identity Federation khi workload chạy ngoài Google Cloud.

### Gọi lớp đọc secret khi khởi tạo ứng dụng

~~~java
public final class Application {
    public static void main(String[] args) throws Exception {
        String projectId = requiredEnvironmentVariable(
                "GOOGLE_CLOUD_PROJECT");

        // Secret ID và version không chứa payload bí mật.
        String secretId = "orders-db-password";
        String versionId = System.getenv()
                .getOrDefault("DB_PASSWORD_SECRET_VERSION", "latest");

        try (SecretReader secrets = new SecretReader()) {
            String databasePassword =
                    secrets.read(projectId, secretId, versionId);

            // Truyền password trực tiếp cho cấu hình connection pool.
            // Không log password và không đưa nó vào exception message.
            startApplication(databasePassword);
        }
    }

    private static String requiredEnvironmentVariable(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Thiếu biến cấu hình bắt buộc: " + name);
        }
        return value;
    }

    private static void startApplication(String databasePassword) {
        // Khởi tạo DataSource/connection pool bằng cấu hình an toàn.
        // Ví dụ được rút gọn; không in databasePassword ra log.
    }
}
~~~

Trong ứng dụng thực tế, hãy đưa secret vào nơi khởi tạo **DataSource**, connection pool hoặc API client. Không truyền secret qua URL, query string, tên metric, trace attribute hay thông báo lỗi. Các hệ thống quan sát thường thu thập những dữ liệu này và có thể làm lộ bí mật.

**latest** giúp ứng dụng đọc phiên bản mới nhất đang được bật. Đây là lựa chọn thuận tiện khi thiết kế cơ chế tự nhận phiên bản mới, nhưng hành vi có thể thay đổi giữa các lần khởi động. Với phát hành cần tính tái lập, cấu hình version ID cụ thể rồi cập nhật cấu hình triển khai cùng quy trình xoay vòng. Dù dùng cách nào, không ghi payload secret vào cấu hình.

## 6. Xử lý lỗi, bộ nhớ đệm và xoay vòng

Không nên gọi Secret Manager cho mỗi truy vấn cơ sở dữ liệu hoặc mỗi request HTTP. Việc đọc secret thường phù hợp ở giai đoạn khởi động hoặc khi làm mới cấu hình theo một khoảng thời gian có kiểm soát. Hãy cân nhắc:

- Tái sử dụng client thay vì tạo client cho từng request.
- Chỉ giữ secret trong bộ nhớ trong phạm vi cần thiết; không lưu vào tệp tạm hoặc cache dùng chung không được bảo vệ.
- Đặt thời hạn làm mới cache phù hợp với yêu cầu xoay vòng và tải của hệ thống.
- Khi secret bắt buộc không đọc được, dừng khởi tạo hoặc từ chối thao tác phụ thuộc vào secret. Không âm thầm quay về mật khẩu mặc định hoặc giá trị hard-code.
- Ghi log mã lỗi, tên tài nguyên hoặc correlation ID cần thiết; tuyệt đối không ghi payload secret.

Một quy trình xoay vòng an toàn có thể thực hiện theo thứ tự sau:

1. Tạo thông tin xác thực mới tại hệ thống đích, chẳng hạn tạo mật khẩu mới cho tài khoản ứng dụng trong cơ sở dữ liệu.
2. Thêm payload mới thành một phiên bản của secret.
3. Triển khai hoặc làm mới ứng dụng để đọc phiên bản mới.
4. Kiểm tra kết nối và hành vi nghiệp vụ bằng phiên bản mới.
5. Thu hồi thông tin xác thực cũ ở hệ thống đích.
6. Vô hiệu hóa hoặc hủy phiên bản secret cũ theo chính sách lưu giữ.

Thứ tự có thể cần điều chỉnh theo khả năng hỗ trợ nhiều mật khẩu đồng thời của hệ thống đích. Nếu cơ sở dữ liệu chỉ cho phép một mật khẩu tại một thời điểm, hãy thiết kế cửa sổ chuyển đổi và khả năng khôi phục trước khi thực hiện. Không xóa phiên bản cũ trước khi xác minh ứng dụng đã chuyển đổi thành công.

## 7. Khi ứng dụng cần khóa mã hóa: dùng Cloud KMS

Secret Manager phù hợp với mật khẩu và token mà ứng dụng cần lấy lại. Nếu mục tiêu là mã hóa dữ liệu nghiệp vụ bằng một khóa được quản lý tập trung, hãy dùng Cloud KMS để thực hiện thao tác mật mã. Ví dụ sau minh họa việc mã hóa một payload nhỏ bằng khóa đối xứng trong Cloud KMS:

~~~java
import com.google.cloud.kms.v1.CryptoKeyName;
import com.google.cloud.kms.v1.EncryptResponse;
import com.google.cloud.kms.v1.KeyManagementServiceClient;
import com.google.protobuf.ByteString;

import java.io.IOException;

public final class KmsEncryption {
    public byte[] encrypt(
            String projectId,
            String locationId,
            String keyRingId,
            String keyId,
            byte[] plaintext) throws IOException {

        CryptoKeyName keyName = CryptoKeyName.of(
                projectId, locationId, keyRingId, keyId);

        try (KeyManagementServiceClient kms =
                     KeyManagementServiceClient.create()) {
            EncryptResponse response = kms.encrypt(
                    keyName, ByteString.copyFrom(plaintext));
            return response.getCiphertext().toByteArray();
        }
    }
}
~~~

Đây là ví dụ tối giản để thể hiện ứng dụng gửi dữ liệu đến Cloud KMS và nhận ciphertext. Trong ứng dụng production, cần quản lý vòng đời client, quyền IAM như quyền mã hóa trên CryptoKey, định dạng lưu ciphertext, xử lý lỗi và quy trình giải mã. Không gửi dữ liệu lớn trực tiếp qua thao tác mã hóa của KMS; với dữ liệu lớn, dùng envelope encryption: tạo khóa dữ liệu (DEK), mã hóa dữ liệu bằng DEK tại ứng dụng, sau đó dùng Cloud KMS bảo vệ DEK. Chỉ lưu ciphertext và DEK đã được bọc; không lưu DEK dạng rõ trong repository.

Service account của workload nên có quyền đúng trên CryptoKey cần dùng, chẳng hạn vai trò mã hóa/giải mã phù hợp với thao tác thực tế. Quyền truy cập secret trong Secret Manager và quyền sử dụng khóa trong Cloud KMS là hai quyền riêng biệt; cấp quyền ở đúng tài nguyên và đúng vai trò.

## 8. Tích hợp với CI/CD và các môi trường triển khai

Quy trình build và phát hành cũng có thể làm lộ bí mật. Hãy kiểm tra các điểm sau:

- Không truyền payload secret bằng tham số dòng lệnh có thể xuất hiện trong lịch sử hoặc danh sách tiến trình.
- Không bật chế độ debug làm in toàn bộ biến môi trường hoặc cấu hình nhạy cảm.
- Dùng danh tính ngắn hạn hoặc Workload Identity Federation để pipeline truy cập Google Cloud; hạn chế khóa service account dạng JSON.
- Chỉ cấp quyền đọc secret cho bước pipeline thật sự cần nó. Tách quyền build, deploy và runtime nếu chúng có trách nhiệm khác nhau.
- Không đóng gói secret vào JAR, WAR, Docker image, source map, file .env hoặc artifact phát hành.
- Với Cloud Run hoặc nền tảng hỗ trợ tích hợp Secret Manager, có thể cấu hình secret được cung cấp qua biến môi trường hoặc volume theo yêu cầu ứng dụng. Đánh giá rủi ro lộ qua dump, process inspection và log; chỉ cấp secret cho revision cần sử dụng.
- Với GKE, cân nhắc tích hợp Secret Manager theo mô hình được tổ chức phê duyệt và kiểm soát quyền ở cấp workload.

Biến môi trường có thể dùng để truyền các giá trị cấu hình không bí mật như project ID, secret ID hoặc version ID. Nếu nền tảng cung cấp secret trực tiếp qua biến môi trường, hãy hiểu rằng tiến trình và công cụ chẩn đoán có thể truy cập môi trường đó; tránh in toàn bộ môi trường và cân nhắc volume hoặc truy cập API trực tiếp khi phù hợp.

## 9. Kiểm tra sau khi di chuyển bí mật

Sau khi sửa ứng dụng, kiểm tra cả mã nguồn lẫn quy trình vận hành:

1. Tìm các tên trường thường chứa bí mật như password, apiKey, clientSecret, accessToken, privateKey trong mã Java và tệp cấu hình. Kết quả tìm kiếm là đầu mối rà soát; cần đọc ngữ cảnh để phân biệt tên biến với giá trị bí mật.
2. Chạy công cụ secret scanning trên repository và pipeline. Xử lý cảnh báo thật, đồng thời cấu hình quét các nhánh và lịch sử phù hợp.
3. Xác nhận repository chỉ còn tên secret hoặc tham chiếu cấu hình, không còn payload.
4. Xác nhận runtime service account đọc được đúng secret cần thiết và không đọc được secret ngoài phạm vi được cấp.
5. Kiểm tra log ứng dụng, log build, crash dump và trace để chắc chắn payload không xuất hiện.
6. Thử xoay vòng trong môi trường thử nghiệm để xác minh ứng dụng nhận phiên bản mới và xử lý lỗi khi không có quyền.
7. Kiểm tra Cloud Audit Logs để rà soát hoạt động truy cập secret theo quy trình giám sát của tổ chức.

Nếu một bí mật đã được commit hoặc gửi vào nơi không đáng tin cậy, hãy xem nó là đã bị lộ. Thu hồi hoặc xoay vòng bí mật tại hệ thống đích ngay cả khi commit đã bị xóa. Viết lại lịch sử Git có thể giảm khả năng vô tình phân phối lại giá trị, nhưng không thể thu hồi các bản clone, fork, cache, log hay artifact đã tồn tại. Hãy phối hợp xử lý các bản sao liên quan theo quy trình ứng phó sự cố của tổ chức.

## 10. Những cách làm sai thường gặp

| Cách làm | Vì sao không an toàn | Cách xử lý |
|---|---|---|
| Đưa mật khẩu vào biến static final | Giá trị nằm trong source hoặc bytecode | Đọc từ Secret Manager khi chạy |
| Chỉ thêm .env vào .gitignore sau khi đã commit | Tệp đã được theo dõi vẫn nằm trong lịch sử Git | Gỡ khỏi repository và xoay vòng bí mật |
| Mã hóa Base64 hoặc đảo chuỗi | Có thể khôi phục dễ dàng; không phải kiểm soát truy cập | Dùng kho bí mật và IAM |
| Lưu khóa service account JSON trong repository | Người có tệp có thể dùng danh tính đó | Dùng ADC, service account gắn với workload hoặc Workload Identity Federation |
| Cấp secretAccessor ở toàn project cho mọi ứng dụng | Mở rộng phạm vi đọc secret quá mức | Cấp quyền ở từng secret và tách service account |
| Log giá trị secret để gỡ lỗi | Log có thể được nhiều người và hệ thống truy cập | Log mã lỗi, resource name hoặc correlation ID |
| Chỉ xóa secret khỏi mã nguồn mà không xoay vòng | Giá trị cũ có thể vẫn được sử dụng từ bản sao khác | Thu hồi hoặc thay secret tại hệ thống đích |
| Đọc latest mà không có kế hoạch triển khai | Các lần khởi động có thể dùng phiên bản khác nhau | Thiết kế chính sách version, cache và rollout |

## 11. Bài tập thực hành

Giả sử một ứng dụng Java tên orders-api kết nối PostgreSQL. Hiện tại, mật khẩu cơ sở dữ liệu nằm trong lớp cấu hình và repository đã có lịch sử commit chứa giá trị đó.

Hãy thực hiện các nhiệm vụ sau trong một project Google Cloud thử nghiệm:

1. Xác định service account mà orders-api sẽ sử dụng khi chạy.
2. Tạo secret có tên orders-db-password, thêm phiên bản chứa mật khẩu thử nghiệm và cấp roles/secretmanager.secretAccessor ở cấp secret cho service account của ứng dụng.
3. Thêm Secret Manager Java client library và triển khai lớp đọc secret dựa trên ADC.
4. Thay cấu hình mật khẩu hard-code bằng giá trị đọc từ Secret Manager. Giữ project ID, secret ID và version ID trong cấu hình không bí mật.
5. Chạy ứng dụng bằng danh tính có quyền và xác nhận kết nối thành công.
6. Thu hồi quyền đọc secret trong môi trường thử nghiệm, khởi động lại ứng dụng và xác nhận lỗi được xử lý rõ ràng, không dùng mật khẩu mặc định.
7. Cấp lại quyền, thêm phiên bản secret mới và kiểm tra quy trình chuyển đổi.
8. Rà soát repository, log và artifact để xác nhận không còn payload bí mật.

### Câu hỏi tự kiểm tra

**1. Vì sao xóa mật khẩu khỏi commit mới nhất chưa đủ khi mật khẩu từng xuất hiện trong Git?**

Vì lịch sử commit, nhánh khác, fork, clone, cache và artifact có thể vẫn giữ giá trị cũ. Cần xoay vòng hoặc thu hồi bí mật tại hệ thống đích.

**2. Ứng dụng Java trên Cloud Run nên lấy thông tin xác thực để gọi Secret Manager từ đâu?**

Từ ADC dựa trên service account được gắn làm runtime identity cho Cloud Run service. Ứng dụng không cần nhúng khóa JSON của service account.

**3. Vai trò nào cho phép workload đọc payload của secret?**

roles/secretmanager.secretAccessor. Nên cấp ở cấp secret nếu workload chỉ cần đọc một số secret cụ thể.

**4. Khi nào nên dùng Cloud KMS thay vì Secret Manager?**

Khi cần quản lý khóa mật mã và thực hiện thao tác như mã hóa, giải mã hoặc ký. Mật khẩu và token mà ứng dụng cần lấy lại thường phù hợp với Secret Manager.

**5. Có nên ghi nội dung secret vào log khi gặp lỗi kết nối?**

Không. Hãy ghi thông tin chẩn đoán không nhạy cảm như mã lỗi, tên tài nguyên và correlation ID.

## Kết luận

Loại bỏ khóa và mật khẩu khỏi mã nguồn Java cần một quy trình hoàn chỉnh: nhận diện và phân loại dữ liệu, lưu bí mật trong Secret Manager, cấp quyền tối thiểu bằng IAM, dùng danh tính workload và ADC để truy cập, sau đó xoay vòng và giám sát. Với khóa mã hóa, hãy dùng Cloud KMS cho vòng đời khóa và thao tác mật mã. Khi một bí mật đã bị lộ, phải thu hồi hoặc thay nó tại hệ thống đích; sửa repository chỉ là một phần của quá trình khắc phục.
