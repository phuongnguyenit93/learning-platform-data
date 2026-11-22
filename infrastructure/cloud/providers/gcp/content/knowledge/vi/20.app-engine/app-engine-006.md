# Kết nối dữ liệu và sử dụng service account trong App Engine

Một ứng dụng Java triển khai trên **App Engine** cần đọc ảnh trong Cloud Storage, truy vấn đơn hàng trong Firestore hoặc Cloud SQL và lấy mật khẩu từ Secret Manager. Nếu dùng credential JSON đặt trong mã nguồn, rủi ro lộ khóa rất cao; nếu gán quyền **Editor** cho toàn ứng dụng, một lỗi bảo mật có thể ảnh hưởng nhiều tài nguyên hơn cần thiết. Hướng tốt hơn là dùng **service account gắn với version App Engine**, thư viện Google Cloud với **Application Default Credentials (ADC)** và IAM theo nguyên tắc **quyền tối thiểu**.

Bài thuộc chương **App Engine** trong học phần **CLOUD_PROVIDERS_GCP**: từ project/IAM/VPC đến dịch vụ ứng dụng, lưu trữ, cơ sở dữ liệu, tự động hóa phát hành và theo dõi độ tin cậy/chi phí. Trọng tâm là **kết nối dữ liệu an toàn từ Java trên App Engine**, không phải hướng dẫn toàn bộ cách viết ứng dụng web.

Sau bài này, bạn có thể:

- Phân biệt **app-level default service account**, **per-version service account**, tài khoản người triển khai và service agent.
- Dùng **ADC** thay JSON private key để ứng dụng Java gọi Cloud Storage, Firestore, Secret Manager và Cloud SQL.
- Cấp role IAM trên đúng **bucket, secret, database/project và Cloud SQL instance** theo nhu cầu.
- Phân biệt quyền IAM với quyền database user, cùng network path tới tài nguyên private IP.
- Chọn **Direct VPC egress** hoặc **Serverless VPC Access connector** cho App Engine Standard; hiểu khác biệt với Flexible.
- Deploy một version bằng `app.yaml` và xác minh service account thực tế.
- Nhận diện lỗi `403`, timeout Cloud SQL, pool quá lớn, cấu hình sai project và chi phí phát sinh.

> **Phạm vi lab:** tên project, bucket, secret, Cloud SQL instance và service account đều là placeholder. Các lệnh IAM và deploy chỉ áp dụng cho project được phép; không chạy trên production nếu chưa kiểm tra owner, quyền hiện có và chi phí.

## 1. Kiến trúc kết nối dữ liệu của App Engine

~~~mermaid
flowchart TD
  A["Client HTTPS"] --> B["App Engine service: orders-api"]
  B --> C["Version chạy Java"]
  C --> D["ADC: danh tính service account của version"]
  D --> E["Cloud Storage API: ảnh/tài liệu"]
  D --> F["Firestore API: document"]
  D --> G["Secret Manager API: secret version"]
  D --> H["Cloud SQL Java Connector / IAM"]
  H --> I["Cloud SQL: MySQL/PostgreSQL"]
  J["VPC egress / firewall / DNS"] --> H
  K["Cloud IAM roles trên tài nguyên đích"] --> E
  K --> F
  K --> G
  K --> H
~~~

Ứng dụng cần đồng thời:

1. **Danh tính**: service account nào đang chạy version?
2. **Quyền**: service account đó có permission trên resource đúng project không?
3. **Đường truy cập**: API endpoint hoặc private IP có đi được qua network/VPC không?
4. **Quyền dữ liệu cấp ứng dụng**: Cloud SQL DB user, Firestore security logic, IAM Conditions, encryption và quy tắc nghiệp vụ đã đúng chưa?

**Có IAM không đồng nghĩa có mạng.** Ví dụ Cloud SQL connector có thể xác thực danh tính nhưng vẫn không kết nối được private IP nếu thiếu đường VPC. Ngược lại, có kết nối TCP 3306 cũng không thay thế xác thực database.

### Chọn nơi lưu dữ liệu

| Nhu cầu | Dịch vụ | Cách kết nối | Điều cần lưu ý |
|---|---|---|---|
| Ảnh/PDF, file upload, backups | **Cloud Storage** | Google Cloud Storage Java client | Bucket IAM, object lifecycle, tránh ghi vào local disk bền vững |
| Document NoSQL và truy vấn document | **Firestore Native mode** | Firestore Java server client | Index, read/write cost, quyền IAM và quy tắc ứng dụng |
| Hệ thống legacy dùng Datastore API | **Firestore in Datastore mode** | Cloud Datastore client | Khác API và mô hình truy vấn Firestore Native |
| SQL giao dịch, joins | **Cloud SQL** | JDBC + Cloud SQL Java Connector, pool | DB authentication, network, connection limits, HA/backup |
| Mật khẩu và API keys | **Secret Manager** | Secret Manager API/Java client | Secret-level IAM và caching/rotation |
| Cache dùng chung | **Memorystore** | Redis client qua private IP | VPC egress, TTL, không dùng làm nguồn dữ liệu duy nhất |

Filesystem cục bộ trên App Engine không phải kho dữ liệu nghiệp vụ bền vững và chia sẻ được giữa mọi instance/version. File upload lớn hoặc trạng thái cần tồn tại qua deployment/scale-out nên nằm ở Cloud Storage hoặc database thích hợp.

## 2. Ba lớp danh tính: deployer, runtime và service agent

App Engine có **một danh tính ứng dụng mặc định** và có thể có **danh tính riêng cho từng version**:

| Danh tính | Ví dụ | Vai trò |
|---|---|---|
| **App-level default service account** | `PROJECT_ID@appspot.gserviceaccount.com` hoặc service account tùy chọn | Runtime mặc định khi version không cấu hình riêng |
| **Per-version service account** | `orders-runtime@PROJECT_ID.iam.gserviceaccount.com` | Runtime identity của **version mới** khi deploy có chỉ định |
| **Deployer/CI/CD identity** | `ci-deploy@PROJECT_ID.iam.gserviceaccount.com` | Build/deploy code, cần `iam.serviceAccounts.actAs` trên runtime SA |
| **Service agents** | Danh tính Google quản lý theo từng API | Thực thi tác vụ hạ tầng/build/deploy; không phải identity code Java |

**Điều kiện quan trọng:**

- Per-version service account phải **được tạo trước** và thuộc **cùng project** với ứng dụng App Engine.
- Có thể chỉ định bằng `app.yaml: service_account` hoặc `gcloud app deploy --service-account`; nếu cả hai cùng có, **giá trị CLI được ưu tiên**.
- Chỉnh app-level default bằng `gcloud app update --service-account` chỉ ảnh hưởng tới **version triển khai sau khi thay đổi**. Những version hiện đang chạy giữ service account cũ cho đến khi được triển khai lại.
- Service account của runtime **khác** tài khoản mà người deploy sử dụng. Cho deployer role Storage Admin không tự cho code Java quyền đọc bucket; và cho runtime role Object Viewer không cho nó quyền deploy.

App Engine mặc định có thể tự tạo `PROJECT_ID@appspot.gserviceaccount.com`; **không giả định tài khoản này luôn có Editor**. Với tổ chức mới hoặc organization policy `iam.automaticIamGrantsForDefaultServiceAccounts`, việc tự cấp Editor có thể bị ngăn. Nếu project cũ còn Editor trên default account, cần thu hẹp bằng Policy Simulator và quy trình thay đổi có kiểm soát.

### Sơ đồ quyền cho hai version

~~~text
App Engine app (project shop-prod)
  ├── Default SA: shop-prod@appspot.gserviceaccount.com
  ├── Service: orders
  │     ├── Version v1 → default SA (đã deploy trước)
  │     └── Version v2 → orders-runtime@shop-prod.iam.gserviceaccount.com
  └── Service: report
        └── Version v1 → report-runtime@shop-prod.iam.gserviceaccount.com
~~~

Nếu traffic vẫn chia 50/50 giữa orders v1 và v2, các request **có thể chạy dưới hai IAM identities khác nhau**. Do đó khi đổi quyền phải xác minh version thực tế đang nhận traffic, không chỉ nhìn vào service name.

## 3. Thiết lập service account và IAM tối thiểu

Giả sử App Engine project là `shop-lab`, Cloud Storage bucket chứa ảnh là `shop-images-lab-unique`. Tạo service account **riêng cho Java orders**:

~~~bash
APP_PROJECT="shop-lab"
APP_SA_NAME="orders-runtime"
APP_SA="$APP_SA_NAME@$APP_PROJECT.iam.gserviceaccount.com"
BUCKET="shop-images-lab-unique"

gcloud config set project "$APP_PROJECT"
gcloud iam service-accounts create "$APP_SA_NAME" \
  --display-name="App Engine orders runtime"

# Cho runtime chỉ đọc object trong một bucket.
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$APP_SA" \
  --role="roles/storage.objectViewer"

gcloud storage buckets get-iam-policy "gs://$BUCKET"
~~~

Role `roles/storage.objectViewer` phù hợp đọc/list object; nếu ứng dụng cần upload, phải thiết kế thêm `storage.objects.create` hoặc role hẹp phù hợp. **Đừng cấp `roles/storage.admin` chỉ để đọc file.** Với bucket bật uniform bucket-level access, IAM ở bucket/managed folder thay cho object ACL.

### Cấp quyền theo thao tác

| Tác vụ | IAM role tham khảo | Phạm vi nên cấp |
|---|---|---|
| Đọc object Cloud Storage | `roles/storage.objectViewer` | Bucket cần đọc |
| Tạo object mới, không xóa file cũ | `roles/storage.objectCreator` | Bucket upload cần ghi |
| Đọc một secret version | `roles/secretmanager.secretAccessor` | **Secret cụ thể** |
| Đọc/ghi Firestore theo ứng dụng server | `roles/datastore.user` khi phù hợp | Database/project đích; xét IAM Conditions/DB scoping |
| Kết nối Cloud SQL qua connector | `roles/cloudsql.client` | Project/instance hỗ trợ; kiểm tra permission thực tế |
| Xuất sự kiện Pub/Sub | `roles/pubsub.publisher` | Topic duy nhất cần publish |

Role IAM **không thay thế authentication của database**. Cloud SQL cần user/password hoặc IAM DB authentication hợp lệ; Firestore Java server client có quyền truy cập theo IAM, vì vậy phải enforce authorization từng user/tenant trong **ứng dụng server**.

### Đọc phiên bản đang gắn identity nào?

~~~bash
gcloud app describe
gcloud app services list
gcloud app versions list --service=orders
gcloud app versions describe VERSION_ID --service=orders
~~~

Trong `gcloud app describe` tìm app-level default service account. Với version, xem service account cấu hình trong Console **App Engine → Versions** hoặc response `versions describe`. Các lệnh trên **chỉ đọc**; nên dùng trước khi thêm/thu hồi IAM role trên production.

## 4. Application Default Credentials (ADC): không nhúng JSON key

Trong App Engine, Google Cloud client libraries tự lấy **short-lived access tokens** từ runtime identity qua **Application Default Credentials (ADC)**. Java code không cần đọc `private_key` hoặc lưu service account JSON trong image/artifact.

~~~mermaid
sequenceDiagram
  participant APP as Java app (App Engine version)
  participant ADC as Google Cloud Java client / ADC
  participant META as App Engine metadata/credential provider
  participant API as Google Cloud API
  APP->>ADC: Gọi Storage/Firestore/Secret Manager
  ADC->>META: Yêu cầu credential ngắn hạn
  META-->>ADC: Access token của runtime SA
  ADC->>API: Request với token
  API-->>APP: Kết quả hoặc 403 theo IAM
~~~

Ví dụ Java khởi tạo clients:

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.FirestoreOptions;
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;

public final class GoogleClients implements AutoCloseable {
    private final Storage storage =
        StorageOptions.getDefaultInstance().getService();
    private final Firestore firestore =
        FirestoreOptions.getDefaultInstance().getService();
    private final SecretManagerServiceClient secrets;

    public GoogleClients() throws Exception {
        // Tự lấy ADC của App Engine version. Không cung cấp JSON key.
        secrets = SecretManagerServiceClient.create();
    }

    public Storage storage() { return storage; }
    public Firestore firestore() { return firestore; }
    public SecretManagerServiceClient secrets() { return secrets; }

    @Override public void close() throws Exception {
        secrets.close();
        firestore.close();
    }
}
~~~

Mã minh họa cách dùng **Java client libraries**, cần khai báo dependencies `google-cloud-storage`, `google-cloud-firestore` và `google-cloud-secretmanager` với phiên bản tương thích thông qua Google Cloud Libraries BOM (hoặc cơ chế quản lý dependency của dự án). Nên tạo client **một lần theo vòng đời ứng dụng**, dùng connection pooling và đóng khi dừng, không tạo/đóng lại mỗi HTTP request.

**Local khác production:** ở laptop có thể dùng `gcloud auth application-default login` để nhận **user ADC** cho test. Điều đó không chứng minh App Engine runtime SA đã được IAM cấp đúng. Không dùng `gcloud auth login` như một thay thế chắc chắn cho application ADC.

**Bảo mật:** không đặt `GOOGLE_APPLICATION_CREDENTIALS` trỏ tới JSON key cũ trong `app.yaml`. Biến môi trường này có thể khiến ADC ưu tiên key đó thay vì runtime identity. Không log bearer token hoặc payload secret.

## 5. Đọc và ghi Cloud Storage bằng Java

Giả sử service chỉ cần đọc ảnh từ bucket `shop-images-lab-unique`, IAM Object Viewer đã được cấp ở mục 3. Dùng client và tên bucket từ môi trường:

~~~java
import com.google.api.gax.paging.Page;
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public final class ImageRepository {
    private final Storage storage =
        StorageOptions.getDefaultInstance().getService();

    public void listImages(String bucket) {
        Page<Blob> objects = storage.list(
            bucket,
            Storage.BlobListOption.prefix("catalog/")
        );
        for (Blob object : objects.iterateAll()) {
            System.out.println(object.getName());
        }
    }

    public byte[] getImage(String bucket, String name) {
        Blob object = storage.get(BlobId.of(bucket, name));
        if (object == null) {
            throw new IllegalArgumentException("Image not found");
        }
        // Chỉ dùng getContent cho file nhỏ; file lớn phải stream.
        return object.getContent();
    }
}
~~~

Nếu chỉ cấp `roles/storage.objectViewer`, ghi file sẽ bị từ chối theo IAM. Với chức năng upload, cấp `roles/storage.objectCreator` trên bucket đích; nếu cần overwrite/delete, đánh giá thêm đúng permissions thay vì tự động nâng lên Storage Admin. **Object name là dữ liệu không tin cậy**: validate prefix, kích thước, MIME và giới hạn người dùng; không cho một tenant đoán object name để xem tài liệu tenant khác.

**Tránh lưu file vào local filesystem của App Engine để chia sẻ lâu dài.** Standard có sandbox và filesystem tạm; Flexible chạy VM nhưng các file trên instance vẫn không phải shared/durable storage được thiết kế cho ứng dụng. Dùng Cloud Storage cho ảnh, báo cáo và file upload; dùng Firestore/Cloud SQL cho metadata/giao dịch.

## 6. Firestore Native và Datastore mode

**Firestore Native mode** phù hợp document data, còn **Firestore in Datastore mode** phục vụ API Datastore/ứng dụng legacy. Hai chế độ không đồng nghĩa: chọn database mode và client library đúng từ đầu, vì khác API, indexes và mô hình truy vấn.

Ví dụ Java server client đọc document Firestore Native:

~~~java
import com.google.cloud.firestore.DocumentSnapshot;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.FirestoreOptions;
import java.util.concurrent.TimeUnit;

public final class OrderReader {
    // Với DB ở project khác, cấu hình setProjectId(DATA_PROJECT)
    // thay vì mặc định dùng project của App Engine.
    private final Firestore db =
        FirestoreOptions.getDefaultInstance().getService();

    public String readStatus(String orderId) throws Exception {
        DocumentSnapshot doc = db.collection("orders")
            .document(orderId)
            .get().get(5, TimeUnit.SECONDS);
        if (!doc.exists()) {
            return "NOT_FOUND";
        }
        return doc.getString("status");
    }
}
~~~

Quyền ví dụ: `roles/datastore.user` cho runtime SA ở resource/project chứa Firestore database theo khả năng IAM của tài nguyên. Dịch vụ server truy cập bằng **IAM**, vì thế không dựa vào Firebase client security rules để bảo vệ người dùng cuối. **Ứng dụng phải tự xác thực/ủy quyền** xem user có quyền đọc đơn hàng `orderId` hay không; đừng dùng order ID trực tiếp từ URL và bỏ qua kiểm tra tenant/owner.

Lưu ý về Firestore:

- Gọi client API có thể bị tính phí theo read/write/delete operations, storage và network.
- Với workload ghi nhiều, thiết kế indexes, document hot spots, retry transaction và query pagination.
- Đặt timeout cho async futures; không gọi `get()` không giới hạn trong HTTP request path.
- Khi dữ liệu ở **project khác**, chọn đúng database project trong `FirestoreOptions` và cấp IAM cho runtime SA từ App Engine project.

## 7. Đọc Secret Manager để lấy thông tin đăng nhập

Mật khẩu database, API token hoặc private key nghiệp vụ không nên đặt nguyên văn trong `app.yaml`, Git hoặc Java source. Tạo **Secret Manager secret** qua quy trình được phép, rồi chỉ cấp quyền đọc **một secret cụ thể**:

~~~bash
SECRET_PROJECT="security-lab"
SECRET="orders-db-password"
APP_SA="orders-runtime@shop-lab.iam.gserviceaccount.com"

# Giả định secret đã tồn tại và có version được bật.
gcloud secrets add-iam-policy-binding "$SECRET" \
  --project="$SECRET_PROJECT" \
  --member="serviceAccount:$APP_SA" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets get-iam-policy "$SECRET" \
  --project="$SECRET_PROJECT"
~~~

Java lấy secret qua ADC:

~~~java
import com.google.cloud.secretmanager.v1.AccessSecretVersionResponse;
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;
import com.google.cloud.secretmanager.v1.SecretVersionName;

public final class DbSecretProvider {
    public String getDbPassword(String projectId, String secretId)
            throws Exception {
        SecretVersionName name =
            SecretVersionName.of(projectId, secretId, "latest");

        try (SecretManagerServiceClient client =
                 SecretManagerServiceClient.create()) {
            AccessSecretVersionResponse response =
                client.accessSecretVersion(name);
            return response.getPayload().getData().toStringUtf8();
        }
    }
}
~~~

Trong code production, nên dùng client dùng chung, **cache secret ngắn hạn** có cơ chế làm mới và hỗ trợ rotation (đừng gọi Secret Manager mỗi truy vấn SQL). Java `String` không thể xóa an toàn nội dung khỏi memory theo yêu cầu, nên giới hạn thời gian/phạm vi giữ secret và tuyệt đối không ghi plaintext vào log. Khi có `403`, xác minh **đúng project/secret/version**, runtime SA và IAM policy; nếu version bị disabled thì quyền IAM đúng vẫn không đọc được.

## 8. Cloud SQL: IAM, JDBC và private IP

Cloud SQL được quản lý riêng, không phải database “tự động có” bên trong App Engine. Kết nối SQL cần:

1. **IAM**: runtime SA có quyền như `roles/cloudsql.client` trong phạm vi được cấp.
2. **Database auth**: DB user/password lấy từ Secret Manager hoặc IAM database authentication khi loại database/cấu hình hỗ trợ.
3. **Network**: đường đến Cloud SQL instance **public IP** hoặc **private IP** hợp lệ; connector không tự tạo VPC route.
4. **Connection pool**: giới hạn connections mỗi instance vì App Engine có thể autoscale.

### JDBC qua Cloud SQL Java Connector

Giả sử **Cloud SQL for MySQL**, instance connection name `DATA_PROJECT:REGION:INSTANCE`. Ví dụ dùng MySQL Connector/J, Cloud SQL Java Connector SocketFactory và HikariCP:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import javax.sql.DataSource;

public final class MySqlPool {
    public static DataSource create(
            String instanceConnectionName,
            String dbName,
            String dbUser,
            String dbPassword,
            boolean privateIp) {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl("jdbc:mysql:///" + dbName);
        config.setUsername(dbUser);
        config.setPassword(dbPassword); // Lấy từ Secret Manager, không hardcode.
        config.setMaximumPoolSize(5);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(10000);

        config.addDataSourceProperty(
            "socketFactory", "com.google.cloud.sql.mysql.SocketFactory");
        config.addDataSourceProperty(
            "cloudSqlInstance", instanceConnectionName);
        config.addDataSourceProperty(
            "ipTypes", privateIp ? "PRIVATE" : "PUBLIC");
        config.addDataSourceProperty(
            "cloudSqlRefreshStrategy", "lazy");

        // Khởi tạo pool một lần cho mỗi application instance.
        return new HikariDataSource(config);
    }
}
~~~

Ví dụ giả định Maven/Gradle đã khai báo **HikariCP**, **MySQL Connector/J** và **Cloud SQL Java Connector** đúng version tương thích. `cloudSqlRefreshStrategy=lazy` phù hợp mô hình serverless khi CPU/background processing có thể không hoạt động liên tục.

**Kết nối qua private IP:** `ipTypes=PRIVATE` khiến connector dùng địa chỉ private của Cloud SQL, **nhưng** App Engine Standard phải có **Direct VPC egress hoặc Serverless VPC Access connector**, cùng VPC route/firewall/DNS phù hợp. Với Flexible, instance VM nằm trong mạng VPC được cấu hình và có thể kết nối tài nguyên private IP qua mạng đó. Nếu dùng public IP phải đáp ứng cấu hình Cloud SQL connector và policy mạng được chấp thuận; đừng mở authorized networks `0.0.0.0/0` để sửa lỗi.

### Vì sao số kết nối có thể gây quá tải?

Giả sử App Engine có tối đa **20 application instances**, mỗi instance tạo JDBC pool với `maximumPoolSize=20`, ứng dụng có thể duy trì tới **400 connections** chỉ từ một service:

~~~text
20 App Engine instances × 20 JDBC connections/instance
  = 400 database connections (mức tối đa danh nghĩa)
~~~

Con số này chưa gồm background jobs, admin tools và service khác. Cloud SQL có giới hạn connections theo cấu hình máy; tăng App Engine autoscaling mà không kiểm soát pool dễ gây `too many connections`. **Nên bắt đầu với pool nhỏ**, giám sát Cloud SQL connection utilization và đo throughput/latency trước khi tăng.

Ngoài ra, dùng **prepared statements**, connection timeout, idle timeout, retries có backoff và transaction idempotency. HTTP request bị retry vẫn có thể ghi dữ liệu hai lần nếu SQL operation không có unique business key.

## 9. App Engine Standard và Flexible kết nối VPC khác nhau

Khi truy cập **Google Cloud APIs** như Cloud Storage, Firestore và Secret Manager qua endpoint được hỗ trợ, bạn thường không cần tạo VPC connector chỉ để gọi các API này. Nhưng kết nối **private IP** tới Cloud SQL, Memorystore hoặc VM cần đường mạng thích hợp.

| Môi trường | Đường vào private IP | Lưu ý |
|---|---|---|
| **App Engine Standard** | **Direct VPC egress** hoặc **Serverless VPC Access connector** | Direct VPC egress được tài liệu Google Cloud khuyến nghị; kiểm tra trạng thái Preview/region/điều kiện trước production |
| **App Engine Flexible** | VM instances chạy trên mạng VPC được cấu hình | Không cần Serverless VPC Access connector chỉ để gọi private IP trên VPC đã kết nối |
| **Cả hai** | IAM + firewall/routes/DNS + quyền ứng dụng | VPC không thay quyền Google Cloud IAM hay DB authentication |

### Standard: Direct VPC egress

Trong `app.yaml` của version **Standard**, có thể thêm cấu hình **Direct VPC egress**:

~~~yaml
# Phần mạng, ghép vào app.yaml Standard sau khi VPC/subnet đã có.
vpc_access:
  network_interface:
    network: app-vpc
    subnet: app-subnet
    tags:
      - appengine-orders
  vpc_egress: private-ranges-only
~~~

`private-ranges-only` chỉ định tuyến traffic tới địa chỉ nội bộ qua VPC; `all-traffic` gửi cả outbound traffic qua VPC và cần kiểm tra Cloud NAT, firewall, DNS, egress cost nếu cần gọi Internet. **Direct VPC egress cho App Engine hiện được tài liệu công bố ở giai đoạn Preview**; cần xác minh tính khả dụng, quota và điều khoản vận hành ở region/project trước khi dùng. Thay cấu hình mạng này yêu cầu **deploy version mới** và chuyển traffic, không đơn giản chỉnh tại chỗ version đang chạy.

### Standard: Serverless VPC Access connector

Nếu Direct VPC egress chưa phù hợp, dùng connector đã được platform team tạo trong cùng region:

~~~yaml
# Phương án THAY THẾ; không ghép đồng thời với vpc_access bên trên.
vpc_access_connector:
  name: projects/shop-lab/locations/asia-southeast1/connectors/app-connector
  egress_setting: private-ranges-only
~~~

Connector có **phí vận hành VM theo cấu hình kể cả khi ít traffic** và có giới hạn throughput/instances; phải giám sát utilization, subnet CIDR và firewall. Khi dùng Shared VPC, có thể cần quyền/network rules ở host project. Không gắn một connector vào version rồi giả định tất cả các version cũ cũng đã được cập nhật.

### Flexible: VPC nằm ở cấp máy ảo

App Engine Flexible dùng Compute Engine VM được quản lý, kết nối VPC theo cấu hình environment. Ví dụ **khái niệm** trong `app.yaml` Flexible:

~~~yaml
runtime: java
env: flex
network:
  name: app-vpc
~~~

Đây không phải `app.yaml` Standard: không trộn `env: flex` với `instance_class: F2` hoặc `vpc_access` Standard. Cả hai môi trường vẫn cần kiểm soát quyền IAM, firewall và chi phí; Flexible có mô hình instance billing khác Standard.

## 10. Cấu hình version qua app.yaml và triển khai có kiểm soát

Với **Java second-generation runtime** trên App Engine Standard, một mẫu `app.yaml` cho service orders:

~~~yaml
runtime: java21
service: orders
instance_class: F2

# Danh tính được gắn vào VERSION tạo bởi deployment này.
service_account: orders-runtime@shop-lab.iam.gserviceaccount.com

automatic_scaling:
  min_instances: 0
  max_instances: 10

env_variables:
  GCS_BUCKET: "shop-images-lab-unique"
  DATA_PROJECT: "data-lab"
  SECRET_PROJECT: "security-lab"
  SQL_INSTANCE_CONNECTION_NAME: "data-lab:asia-southeast1:orders-db"
  DB_NAME: "orders"
  DB_USER: "orders_app"

# Chỉ định khi artifact đã được build và file thật sự tồn tại
# trong deployment source. Web server phải nghe 0.0.0.0:8080.
entrypoint: "java -jar target/orders.jar"
~~~

**Giải thích quan trọng:**

- `runtime: java21` là ví dụ Java second-generation; chọn Java runtime còn được hỗ trợ với ứng dụng thật.
- `service_account` là **runtime SA của version**, **không** phải deployer identity. Nếu `--service-account` có ở CLI, giá trị CLI thắng.
- `max_instances` giới hạn mức mở rộng mục tiêu cho version, nhưng không phải cam kết chi phí tuyệt đối; phải tính thêm version khác, Cloud SQL và network.
- Không lưu `DB_PASSWORD` vào `env_variables`; đọc qua Secret Manager (mục 7).
- `entrypoint` ở đây giả định CI/Maven tạo **executable JAR** tại `target/orders.jar`. Nếu ứng dụng dùng WAR hoặc buildpack mặc định, phải dùng entrypoint hợp lệ theo cấu trúc thật. Web server phải bind **`0.0.0.0:8080`**.
- Chỉ thêm block `vpc_access` hoặc `vpc_access_connector` từ mục 9 khi cần **private IP connectivity** và đã xác minh network.

### Quy trình canary của một version mới

~~~bash
APP_PROJECT="shop-lab"
gcloud config set project "$APP_PROJECT"

# Kiểm tra App Engine application đã tồn tại; app location không đổi tùy tiện.
gcloud app describe

# Build Java application bằng pipeline của dự án, có target/orders.jar.
# Sau khi kiểm thử image/JAR, deploy version nhưng KHÔNG chuyển traffic.
gcloud app deploy app.yaml \
  --version=orders-wif-v2 \
  --no-promote

gcloud app versions describe orders-wif-v2 --service=orders
gcloud app versions list --service=orders
~~~

Đây là các lệnh minh họa cho người thực hành, **không thực thi trong nhiệm vụ soạn tài liệu**. Nếu đã có version trùng tên, đừng overwrite một version đang phục vụ mà chưa xem traffic/rollback. Sau khi kiểm thử phiên bản mới và identity, team vận hành có thể **chuyển traffic theo tỷ lệ** qua Console hoặc `gcloud app services set-traffic`; phải giữ khả năng rollback về version cũ.

### Một thay đổi có thể gây lỗi khó thấy

Nếu trước đó version v1 chạy với App Engine default SA có role Editor, còn v2 dùng `orders-runtime` chỉ được Object Viewer, một API ghi vào Cloud Storage **có thể chỉ lỗi khi request vào v2**. Khi canary có 10% traffic, lỗi có thể xuất hiện ngẫu nhiên. Vì vậy kiểm tra **từng thao tác và từng version**, không chỉ gọi `/healthz` trả HTTP 200.

## 11. Môi trường local, CI/CD và secrets

| Nơi thực thi | Cách lấy credential đề xuất | Không nên làm |
|---|---|---|
| Laptop dev | User ADC qua `gcloud auth application-default login` hoặc account impersonation theo chính sách | Copy service account private key vào repo |
| CI/CD | Workload Identity Federation cho pipeline hoặc danh tính ngắn hạn, quyền deploy đúng scope | Key JSON dài hạn trong pipeline variables |
| App Engine version | Runtime service account + ADC từ hạ tầng | Đặt `GOOGLE_APPLICATION_CREDENTIALS` tới key cũ |
| Cross-project data | Runtime SA của App Engine project được cấp IAM trên tài nguyên project đích | Nhầm project chứa SA với project chứa dữ liệu |

Local:

~~~bash
# Dùng local developer identity; không áp dụng lệnh này bên trong App Engine.
gcloud auth application-default login

# Java client sẽ đọc ADC từ local credential.
# Test bằng resource dev, không dùng production bucket/secret.
~~~

Để các môi trường không gọi nhầm dữ liệu, dùng **project IDs/tên bucket/secret tách biệt** qua config không chứa secret. Trong CI/CD, chạy unit tests không cần mạng bằng emulator/mocks khi khả thi; integration tests dùng tài nguyên dev và role ít quyền.

### Secret rotation

1. Tạo secret version mới và xác nhận consumer hỗ trợ credential mới.
2. Giữ khoảng chuyển tiếp với database/API khi phải xoay cả password và user.
3. App Engine clients lấy version `latest` theo caching policy; làm mới secret hoặc deploy lại nếu instance đang giữ bản cũ.
4. Kiểm tra lỗi xác thực DB và logs **không lộ secret**.
5. Vô hiệu hóa version cũ sau khi không còn consumer, có kế hoạch rollback rõ ràng.

Không giả định một bản ghi `latest` trong Secret Manager tự khiến toàn bộ connection pool đang mở được xác thực lại bằng mật khẩu mới.

## 12. Giám sát, bảo mật và chi phí

Trong production cần kiểm soát cả **truy cập dữ liệu**, **số instance** và **phụ thuộc ngoài App Engine**.

### Bảo mật vận hành

- IAM runtime service account chỉ có những role ứng dụng cần, ưu tiên cấp trên bucket/secret/topic/database thay vì cả project.
- Phân quyền **deployer** khác **runtime**; chỉ cấp `iam.serviceAccounts.actAs` cho người/pipeline được phép triển khai với service account đó.
- Dùng **Secret Manager**, encryption at rest và audit logging ở phạm vi phù hợp; không in database password, token, PII vào stdout.
- Nếu dùng Cloud SQL, tách IAM Client khỏi database user permission và giữ connection TLS/authentication qua connector.
- Tránh dùng App Engine default service account còn `Editor` cho nhiều service; dùng per-version service account riêng khi quyền khác nhau.
- Với nhiều version đang nhận traffic, kiểm tra **cả danh tính và quyền** trước khi cắt quyền version cũ.
- Thực thi authorization theo người dùng/tenant trong Java server, nhất là khi Firestore server client hoặc Cloud SQL có quyền đọc nhiều bản ghi.

### Những chỉ số nên theo dõi

| Lớp | Chỉ số/log | Phát hiện |
|---|---|---|
| App Engine | Request count, 4xx/5xx, P95 latency, instance count, version traffic | Lỗi xuất hiện sau deploy hoặc chỉ ở một version |
| IAM/Audit | PermissionDenied, principal email, role changes | SA sai, thiếu role, privilege drift |
| Cloud Storage | Read/write operations, 403/404, network egress | Sai bucket, mất quyền hoặc truy cập tăng bất thường |
| Firestore | Document reads/writes, query latency, indexes, quota | Truy vấn đắt, hot documents |
| Cloud SQL | Active connections, CPU, latency, failed connections | Pool lớn, database bottleneck |
| Secret Manager | AccessVersion calls, access failures, quota | Thừa secret reads, version disabled |
| VPC egress | Connector throughput/instances hoặc Direct VPC egress, firewall denials | Timeout private IP, egress cost |

Ví dụ chỉ đọc tình trạng/log:

~~~bash
gcloud app versions list --service=orders
gcloud app versions describe VERSION_ID --service=orders
gcloud app logs tail --service=orders

# Sử dụng Cloud Logging/Monitoring Console để lọc theo
# service, version, status 403/5xx và thời điểm deploy.
~~~

### Chi phí thực tế

App Engine Standard có instance class và automatic/basic/manual scaling; Flexible được tính theo VM/vCPU/RAM và các tài nguyên liên quan. **Không chỉ tính số request HTTP**:

~~~text
Tổng chi phí vận hành gần đúng
  = App Engine instance hours / compute
  + Cloud Storage bytes + API operations + egress
  + Firestore read/write/index/storage
  + Cloud SQL instance + storage + backup + network
  + Secret Manager operations
  + VPC connector (nếu dùng) / network / NAT
  + Cloud Logging, Monitoring và tài nguyên phụ thuộc
~~~

**Ví dụ:** App Engine scale từ 5 lên 30 instances, mỗi instance giữ pool tối đa 10 SQL connections → có thể tới **300 kết nối**. Tăng App Engine capacity có thể làm Cloud SQL quá tải và phát sinh phí backend. Điều chỉnh pool/instance limits dựa trên load test, database quota và latency, không dùng `max_instances` làm lời bảo đảm duy nhất về chi phí.

Đặt **Cloud Billing budgets/alerts**, ghi nhận owner của bucket/connector/database, xem phí từ những **version vẫn đang chạy** sau canary. Budget alert không tự tắt service; xóa một version không tự xóa bucket, Cloud SQL hoặc connector.

## 13. Bảng xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra đầu tiên |
|---|---|---|
| `403` đọc Storage | Runtime SA chưa có Object Viewer, sai bucket/project hoặc IAM Deny | `gcloud app versions describe`, bucket IAM policy |
| Local chạy được, App Engine `403` | Local dùng user ADC có quyền rộng hơn runtime SA | So sánh hai principal, không copy local key lên server |
| Sau deploy một phần request lỗi | Hai version dùng service account/permissions khác nhau | App Engine traffic splits và quyền từng version |
| `403` đọc Secret Manager | Thiếu Secret Accessor trên đúng secret, nhầm project | Secret IAM, version enabled và runtime SA |
| Cloud SQL Java Connector báo `permission denied` | Thiếu `roles/cloudsql.client`, sai instance connection name | IAM project Cloud SQL, connector logs |
| Cloud SQL `connection timeout` qua private IP | Thiếu VPC egress, firewall/router/subnet sai | `vpc_access`/connector, private IP và network path |
| Cloud SQL `Access denied` hoặc auth failed | Sai database user/password/IAM DB auth | DB user, secret version, grants bên trong DB |
| `Too many connections` | Autoscaling nhân số JDBC pools, connections rò rỉ | Cloud SQL active connections, pool per instance |
| Firestore `PERMISSION_DENIED` | Thiếu Datastore User hoặc sai database project | Runtime SA, IAM của database/project |
| Firestore lỗi index/quota | Query cần composite index, hot document hoặc vượt quota | Firestore error code, indexes và usage |
| Không thấy object trong bucket | Sai prefix/name, chưa upload, 404 hoặc access lọc | Storage list/BlobId, project/bucket |
| App deploy lỗi `actAs` | Deployer chưa được dùng runtime SA | `roles/iam.serviceAccountUser` trên đúng SA |
| Không tạo được deployment artifact | Cloud Build/Artifact Registry service agent/quyền chưa đủ | Build logs, deployer và service agent IAM |
| VPC connector còn bị tính phí | Đã bỏ cấu hình ở version mới nhưng connector vẫn tồn tại | Inventory versions và connector lifecycle |
| Hóa đơn tăng sau canary | Nhiều version active, scaling min instances, DB/network | Billing by SKU, traffic và instance counts |

**Nguyên tắc chẩn đoán:** nếu có `403` từ Storage/Firestore/Secret Manager, đọc **tên API và principal thực sự bị từ chối**, không cấp Editor để thử. Nếu `timeout` private IP, kiểm tra đường VPC trước khi đổi role. Nếu Cloud SQL báo password invalid, đừng cấp thêm `roles/cloudsql.admin`.

## 14. Tình huống: Orders API cần nhiều nguồn dữ liệu

Nhóm phát triển đưa `orders-api` lên App Engine Standard Java:

~~~text
App Engine service orders, version v2
  Runtime SA: orders-runtime@shop-prod.iam.gserviceaccount.com
     ├── Object Viewer → bucket product-images (data project)
     ├── Datastore User → Firestore orders (data project)
     ├── Secret Accessor → secret sql-password (security project)
     └── Cloud SQL Client → Cloud SQL orders-db (data project)
                                    ↑
                        Direct VPC egress → private IP
~~~

Quy trình triển khai:

1. Platform team tạo SA trong **App Engine project**, xác định App Engine Standard region và VPC/subnet hợp lệ.
2. Data/security teams cấp IAM **trên đúng resources** của project đích; Cloud SQL DB admin tạo DB user `orders_app` với quyền schema cần thiết.
3. Java code dùng ADC, Secret Manager và Cloud SQL Java Connector; không giữ password trong `app.yaml`.
4. CI/CD build JAR, deploy version v2 qua `--no-promote`, gắn SA qua `service_account`; nếu cần private IP thì bổ sung `vpc_access` cho version mới.
5. Team test **đọc object**, **đọc Firestore**, **đọc secret**, **truy vấn SQL** và xác nhận truy cập ngoài phạm vi bị từ chối.
6. Monitor P95/5xx, IAM denials, SQL connections và chi phí; chuyển traffic theo canary và có rollback.

Khi một service report cần quyền **ghi báo cáo** nhưng không cần đọc secret thanh toán, tạo `report-runtime` riêng. **Không cấp role chung “app-engine-runtime-editor” cho cả hai service.**

## 15. Checklist và bài tập

### Checklist trước production

- [ ] Đã xác định **service account thực tế của từng version** và những version còn traffic.
- [ ] Runtime SA riêng theo trách nhiệm, không dùng default Editor khi không cần.
- [ ] Deployer chỉ được `actAs` những SA đã được phê duyệt.
- [ ] Java clients dùng ADC; không có JSON private key trong image, Git hoặc `app.yaml`.
- [ ] Mỗi Cloud Storage bucket, Firestore database, secret và Cloud SQL instance được cấp quyền đúng scope.
- [ ] Cross-project IAM tham chiếu runtime SA từ App Engine project, không nhầm project ID.
- [ ] Cloud SQL có **IAM + DB auth + network path**; pool size và timeout đã kiểm thử.
- [ ] Standard private IP dùng Direct VPC egress/connector theo khả năng hỗ trợ; Flexible dùng VPC được cấu hình.
- [ ] App Engine config chứa **non-secret env vars**; password lấy từ Secret Manager và có rotation plan.
- [ ] Có monitoring theo service/version, IAM denial, database connections và chi phí.
- [ ] Version mới được kiểm tra trước khi chuyển traffic; có rollback và cleanup tài nguyên không dùng.

### Bài tập thực hành

**Bài 1 — Chọn quyền IAM.** Một service Java chỉ (a) đọc ảnh trong bucket `catalog-images`, (b) publish topic `orders-created` và (c) đọc secret `db-pass`. Chọn role và **phạm vi** cho mỗi tài nguyên; giải thích tại sao không dùng `roles/editor`.

**Bài 2 — ADC và khác biệt local/prod.** Ứng dụng đọc Cloud Storage được khi chạy máy developer, nhưng App Engine v2 trả `403`. Nêu tối thiểu bốn bước kiểm tra, bao gồm `gcloud app versions describe` và bucket IAM policy.

**Bài 3 — Cloud SQL.** App Engine Standard truy cập Cloud SQL MySQL private IP qua Java Connector. Hãy vẽ ba tầng **IAM, database user và VPC**, viết cấu hình HikariCP với `ipTypes=PRIVATE` và giải thích vì sao có role Client vẫn có thể timeout.

**Bài 4 — Tính số kết nối.** Service có `max_instances=15`, mỗi instance tạo JDBC pool `maximumPoolSize=12`. Tính số kết nối SQL tối đa danh nghĩa và đề xuất cách giới hạn khi Cloud SQL chỉ cho phép ít hơn con số đó sau khi trừ các service khác.

**Bài 5 — Version identity.** Version v1 dùng default SA; v2 dùng `orders-runtime`, traffic chia 80/20. Sau khi đổi app-level default SA, liệu v1 đã thay identity chưa? Nêu cách kiểm tra và quy trình chuyển traffic/thu hồi quyền an toàn.

**Bài 6 — Secrets và cross-project.** App Engine ở project A, Secret Manager ở B, Firestore ở C. Lập bảng project chứa **runtime SA** và project chứa **resource**, nêu IAM cần cấp ở đâu và cách tránh leak password qua logs.

**Bài 7 — Chọn VPC egress.** Một Java service cần Redis private IP và một API Internet. So sánh `private-ranges-only` với `all-traffic`, Direct VPC egress với connector, tính yếu tố Cloud NAT/firewall/chi phí và lưu ý Direct VPC egress Preview.

## Tài liệu tham khảo chính thức

- [Configure App Engine service accounts](https://cloud.google.com/appengine/docs/standard/configure-service-accounts) — app-level default, per-version, IAM và precedence giữa CLI/YAML.
- [App Engine app.yaml reference](https://cloud.google.com/appengine/docs/standard/reference/app-yaml) — runtime, `service_account`, scaling, `vpc_access`.
- [App Engine Java runtime configuration](https://cloud.google.com/appengine/docs/standard/java-gen2/configuring-your-app-with-app-yaml) — Java second-generation và file `app.yaml`.
- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials) — cách client libraries khám phá credential.
- [Use Cloud Storage with App Engine](https://cloud.google.com/appengine/docs/standard/using-cloud-storage) — object storage và Java client.
- [Use Firestore with App Engine](https://cloud.google.com/appengine/docs/standard/using-firestore) — Native/Datastore mode và kết nối database.
- [Connect App Engine Standard to Cloud SQL MySQL](https://cloud.google.com/sql/docs/mysql/connect-app-engine-standard) — Java Connector/JDBC, pool và xác thực.
- [Cloud SQL Java Connector](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory) — các thuộc tính SocketFactory, private/public IP.
- [Secret Manager access control](https://cloud.google.com/secret-manager/docs/access-control) — IAM Secret Accessor và secret versions.
- [Direct VPC egress for App Engine Standard](https://cloud.google.com/appengine/docs/standard/vpc-direct-vpc) — cấu hình mạng và giới hạn Preview.
- [Serverless VPC Access for App Engine](https://cloud.google.com/appengine/docs/standard/connecting-vpc) — connectors, firewall và egress settings.
- [App Engine Flexible environment](https://cloud.google.com/appengine/docs/flexible) — VM networking và runtime model.
- [Cloud Audit Logs overview](https://cloud.google.com/logging/docs/audit) — theo dõi thay đổi IAM và Data Access.
- [App Engine pricing](https://cloud.google.com/appengine/pricing) — instance classes, scaling và usage.
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing), [Firestore pricing](https://cloud.google.com/firestore/pricing) — chi phí lưu trữ và database operations.
