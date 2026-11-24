# Signed URL và quyền của danh tính thực hiện ký

## 1. Bài toán chia sẻ object có thời hạn

Một ứng dụng Spring Boot có thể lưu tài liệu, ảnh, bản xuất báo cáo hoặc tệp người dùng trong Google Cloud Storage (GCS). Khi người dùng cần tải một file, backend thường không muốn tải toàn bộ bytes qua chính mình rồi truyền tiếp. Tương tự, khi người dùng upload, backend không nhất thiết phải nhận file rồi chuyển tiếp lên bucket. **Signed URL** cho phép backend cấp một URL có chữ ký, giới hạn theo object, HTTP method và thời gian; client có thể trao đổi dữ liệu trực tiếp với Cloud Storage mà không cần Google account hoặc IAM credentials riêng.

Signed URL không biến bucket thành public. Nó tạo một quyền truy cập tạm thời cho người nắm URL. Bất kỳ ai có URL đều có thể dùng nó trong thời hạn còn hiệu lực, miễn là request khớp method, resource, query parameter và header đã ký. Vì vậy, signed URL phải được xem như một bearer credential.

Bài học thuộc chương **Google Cloud Storage** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Bài này tập trung vào signed URL, quy trình ký V4 và quyền IAM của danh tính thực hiện ký.

Sau bài học, bạn có thể:

- Giải thích signed URL, V4 signature và mô hình bearer access.
- Phân biệt người tạo chữ ký, service account ký URL và người sử dụng URL.
- Cấp đúng quyền `iam.serviceAccounts.signBlob` và quyền object cho signer.
- Tạo signed URL GET/PUT bằng Java Cloud Storage client.
- Dùng service account impersonation để ký mà không phát hành private key dài hạn.
- Ràng buộc HTTP method, Content-Type, query parameter, generation và thời hạn.
- Tích hợp signed URL vào Spring Boot flow có kiểm tra quyền nghiệp vụ.
- Bảo vệ URL, cấu hình CORS và xử lý lỗi chữ ký/permission/expiration.

> **Phạm vi phiên bản:** Ví dụ dùng Google Cloud Storage Java client, V4 signing và Google Auth Library. Các overload, package và dependency version cần đồng bộ qua BOM của dự án; hãy đối chiếu Javadoc của đúng version đã resolve. Bài ưu tiên service account impersonation và IAM Credentials API, không yêu cầu lưu service account private key trong source hoặc container image.

## 2. Signed URL là gì?

Signed URL là URL chứa thông tin xác thực trong query string. Chữ ký cho phép Cloud Storage xác định request được thực hiện dưới quyền của một tài khoản cụ thể, dù người gửi request không có credentials Google Cloud.

Một signed URL thường ràng buộc:

- **Resource:** một bucket/object cụ thể.
- **HTTP method:** ví dụ `GET` để đọc hoặc `PUT` để upload.
- **Expiration:** thời điểm URL hết hạn.
- **Signed headers:** các header bắt buộc phải khớp, ví dụ `Content-Type`.
- **Query parameters:** các tham số được đưa vào canonical request và bảo vệ bởi chữ ký.

Ví dụ URL V4 có các query parameter như `X-Goog-Algorithm`, `X-Goog-Credential`, `X-Goog-Date`, `X-Goog-Expires`, `X-Goog-SignedHeaders` và `X-Goog-Signature`. Java client tạo các trường này tự động; ứng dụng không nên tự nối hoặc chỉnh sửa URL sau khi ký.

~~~mermaid
sequenceDiagram
    participant User as Người dùng
    participant API as Spring Boot API
    participant IAM as IAM Credentials API
    participant GCS as Cloud Storage

    User->>API: Yêu cầu URL tải tài liệu
    API->>API: Xác thực user và kiểm tra quyền tài liệu
    API->>IAM: Ký request bằng service account
    IAM-->>API: Chữ ký
    API-->>User: Signed URL có thời hạn
    User->>GCS: GET object bằng signed URL
    GCS->>GCS: Kiểm tra chữ ký, method, header, expiry
    GCS-->>User: Object bytes
~~~

Người dùng không cần quyền IAM trực tiếp trên bucket. Cloud Storage xác thực request bằng chữ ký và thực thi quyền của danh tính đã ký URL.

### 2.1. Signed URL không phải public object

| Cách truy cập | Ai có thể truy cập? | Điều kiện |
| --- | --- | --- |
| Object public | Mọi người theo policy public | Bucket/object được cấp quyền public |
| IAM authenticated access | Principal có IAM permission | Request có credentials hợp lệ |
| Signed URL | Bất kỳ ai có URL | URL còn hạn và request khớp chữ ký |
| `gs://bucket/object` | Không tự cấp quyền | Caller vẫn cần credentials và IAM |

Signed URL là quyền truy cập tạm thời vào resource đã ký. Khi hết hạn, URL không còn dùng được; object vẫn giữ policy IAM bình thường của bucket.

### 2.2. Signed URL phù hợp với trường hợp nào?

- Backend xác minh quyền người dùng rồi cấp URL tải một file.
- Người dùng upload trực tiếp file lên một object đã được backend xác định.
- Ứng dụng cần chuyển dữ liệu lớn trực tiếp giữa client và Cloud Storage.
- Dịch vụ bên ngoài cần truy cập một object cụ thể trong khoảng thời gian ngắn mà không cấp Google credentials cho dịch vụ đó.

Signed URL thường không cần thiết cho thao tác copy, compose, list bucket, sửa metadata hoặc xóa do backend thực hiện. Trong các trường hợp đó, backend có thể gọi Storage API trực tiếp dưới workload identity của nó.

## 3. V4 signing và những gì được bảo vệ

### 3.1. Vì sao ưu tiên V4?

Cloud Storage hỗ trợ nhiều thế hệ signing. Với ứng dụng mới, nên dùng **V4 signing** và chỉ định rõ option `withV4Signature()` để tránh phụ thuộc default của phiên bản thư viện.

V4 dùng thuật toán `GOOG4-RSA-SHA256` khi ký bằng service account RSA key. Quy trình chuẩn hóa request và ký bao gồm:

1. Xác định HTTP method và canonical resource path.
2. Chuẩn hóa các header được ký.
3. Chuẩn hóa query parameter.
4. Tạo canonical request.
5. Tạo string-to-sign chứa timestamp, credential scope và hash của canonical request.
6. Ký string-to-sign bằng danh tính signer.
7. Đưa chữ ký vào query parameter `X-Goog-Signature`.

Thư viện Google Cloud thực hiện các bước này. Chỉ tự triển khai canonical request khi có yêu cầu đặc biệt và đã kiểm thử kỹ; một khác biệt nhỏ về encoding, dấu cách, header hoặc thứ tự query parameter cũng có thể làm chữ ký không hợp lệ.

### 3.2. Method, header và query phải khớp

Nếu URL được ký cho `GET`, client không thể đổi thành `PUT`. Nếu chữ ký yêu cầu header `Content-Type: application/pdf`, request upload phải gửi đúng giá trị đã ký. Nếu thêm query parameter không có trong chữ ký, request V4 có thể bị từ chối.

| Thành phần | Ví dụ | Hành vi |
| --- | --- | --- |
| HTTP method | `GET`, `PUT` | Phải dùng đúng method đã ký |
| Object path | `/bucket/reports/a.pdf` | Không đổi object name |
| Content-Type | `application/pdf` | Phải khớp signed header |
| Query parameter | `ifGenerationMatch=0` | Phải được đưa vào chữ ký |
| Expiration | 15 phút | Request phải đến trong thời hạn |
| Host | `storage.googleapis.com` | Là header bắt buộc trong signed headers |

Không sửa URL bằng cách nối thêm query parameter, thay host tùy ý hoặc encode lại path sau khi ký.

### 3.3. Giới hạn endpoint

Signed URL của Cloud Storage chỉ dùng để truy cập resource qua **XML API endpoints**. Không dùng URL đó như `gs://` URI, JSON API URL hoặc URL console. Client thường gửi request tới host được tạo trong signed URL, ví dụ `storage.googleapis.com`.

## 4. Ba danh tính cần phân biệt

Trong quy trình signed URL có ba vai trò riêng:

1. **Signing principal:** user hoặc workload identity đang chạy Spring Boot và gọi IAM Credentials API để yêu cầu ký.
2. **Signer service account:** service account được chọn làm danh tính thực hiện request GCS sau này; URL được ký dưới quyền tài khoản này.
3. **URL consumer:** trình duyệt, mobile app hoặc đối tác nhận URL và gửi request tới Cloud Storage.

~~~mermaid
flowchart TD
    SOURCE["Signing principal<br/>API runtime identity"] -->|"iam.serviceAccounts.signBlob"| SIGNER["Signer service account"]
    SIGNER -->|"storage.objects.get / create / delete"| OBJECT["Bucket / object"]
    CONSUMER["URL consumer<br/>Browser / mobile / partner"] -->|"URL + signed method"| GCS["Cloud Storage"]
    SIGNER -. "Danh tính trong chữ ký" .-> GCS
~~~

**Signing principal không tự động là signer.** Ví dụ, Cloud Run service chạy bằng `document-api-runtime@...` có thể impersonate `document-download-signer@...`. Runtime identity chỉ cần quyền ký thay service account đó; signer service account mới là principal cần quyền đọc object.

URL consumer không cần Google IAM role. Quyền của consumer bị giới hạn bởi method, object, header, query và expiration đã ký.

### 4.1. Quyền object của signer

| Signed request | Permission của signer | Role thường dùng |
| --- | --- | --- |
| GET object | `storage.objects.get` | `roles/storage.objectViewer` |
| HEAD/đọc metadata | `storage.objects.get` | `roles/storage.objectViewer` |
| PUT tạo object mới | `storage.objects.create` | `roles/storage.objectCreator` |
| PUT có thể ghi đè object | `storage.objects.create` và `storage.objects.delete` | `roles/storage.objectUser` hoặc custom role phù hợp |
| DELETE object | `storage.objects.delete` | Role có quyền delete phù hợp |

Các role trên nên được cấp ở bucket scope nếu signer chỉ phục vụ một bucket. Không cấp `roles/storage.admin` ở project scope cho một service chỉ phát hành URL tải tài liệu.

`roles/storage.objectCreator` không mặc nhiên cho phép đọc, xóa hoặc ghi đè object hiện có. Nếu signed PUT có thể thay thế object cũ, signer cần thêm quyền xóa object cũ theo semantics của Cloud Storage. Nếu chỉ tạo object mới, hãy dùng object name duy nhất và precondition `ifGenerationMatch=0`.

### 4.2. Quyền để ký thay service account

Signing principal cần permission:

`iam.serviceAccounts.signBlob`

Permission này nằm trong role:

`roles/iam.serviceAccountTokenCreator`

Cấp role này trên **service account mục tiêu** cho đúng runtime principal thay vì cấp rộng toàn project nếu không cần. Role Token Creator còn có các khả năng tạo token/credential khác; tổ chức có thể dùng custom role chỉ chứa permission cần thiết nếu chính sách cho phép.

Ngoài ra, project cần bật **IAM Service Account Credentials API** (`iamcredentials.googleapis.com`). Việc bật API cần quyền `serviceusage.services.enable`.

### 4.3. Ma trận quyền tổng hợp

| Thành phần | Quyền cần có | Không nên nhầm với |
| --- | --- | --- |
| Signing principal | `iam.serviceAccounts.signBlob` trên signer SA | Quyền đọc object |
| Signer service account | `storage.objects.get/create/delete` theo signed method | Quyền impersonate chính nó |
| URL consumer | Không cần Google IAM credentials | Không có quyền truy cập mọi object |
| Admin cấu hình IAM | Bật API và gán role phù hợp | Runtime permission |

Nếu signing principal là một service account chạy trên Cloud Run/GKE/Compute Engine, nó cần được cấp Token Creator trên signer SA. Nếu dùng user ADC trong local development, user đó cũng cần role này trên signer SA.

## 5. Thiết lập IAM bằng gcloud

Ví dụ có hai service account:

- `document-api-runtime@training-platform-dev.iam.gserviceaccount.com`: danh tính chạy Spring Boot.
- `document-download-signer@training-platform-dev.iam.gserviceaccount.com`: danh tính ký URL tải tài liệu.

Bật IAM Credentials API:

~~~bash
gcloud services enable iamcredentials.googleapis.com \
  --project=training-platform-dev
~~~

Cho runtime identity quyền ký thay signer service account:

~~~bash
gcloud iam service-accounts add-iam-policy-binding \
  document-download-signer@training-platform-dev.iam.gserviceaccount.com \
  --member="serviceAccount:document-api-runtime@training-platform-dev.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
~~~

Cấp quyền đọc object cho signer tại bucket:

~~~bash
gcloud storage buckets add-iam-policy-binding \
  gs://training-documents-prod \
  --member="serviceAccount:document-download-signer@training-platform-dev.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
~~~

Với signed upload chỉ tạo object mới, có thể cấp `roles/storage.objectCreator` ở bucket scope. Nếu URL cho phép overwrite, đánh giá `roles/storage.objectUser` hoặc custom role có cả create/delete.

Các lệnh chỉ minh họa cách cấu hình. Thay project, bucket, service account bằng tài nguyên thực tế và kiểm tra IAM policy trước khi áp dụng. Không cấp quyền signer trên nhiều bucket khi ứng dụng chỉ cần một bucket.

## 6. Dùng ADC và impersonation để ký không cần private key

### 6.1. Vì sao ADC thông thường có thể không ký được?

Java `Storage.signUrl(...)` cần một credential triển khai `ServiceAccountSigner`. Một số loại ADC thường gặp như user credentials tạo từ `gcloud auth application-default login` hoặc credentials từ metadata server không nhất thiết triển khai interface này trực tiếp.

Vì vậy, chỉ gọi `StorageOptions.getDefaultInstance().getService()` rồi `signUrl()` có thể ném `IllegalStateException` nếu credential không có khả năng ký. Cần cung cấp signer tường minh hoặc dùng một credential phù hợp.

Không giải quyết lỗi này bằng cách mặc định tạo service account key JSON rồi đóng gói vào container. Có thể dùng **ImpersonatedCredentials** để yêu cầu IAM Credentials API ký thay service account đích.

### 6.2. ImpersonatedCredentials

`ImpersonatedCredentials` cho phép credentials nguồn đại diện cho một service account khác. Trong Java Auth Library, lớp này triển khai `ServiceAccountSigner`, nên có thể truyền vào `Storage.SignUrlOption.signWith(...)`.

Luồng quyền:

- ADC của runtime xác thực với Google Cloud.
- Runtime principal có `roles/iam.serviceAccountTokenCreator` trên signer service account.
- IAM Credentials API thực hiện thao tác ký `signBlob`.
- Signed URL mang danh tính signer service account.
- Khi consumer dùng URL, Cloud Storage kiểm tra request theo quyền signer.

~~~java
import com.google.auth.oauth2.GoogleCredentials;
import com.google.auth.oauth2.ImpersonatedCredentials;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import java.io.IOException;
import java.util.Collections;

public class SignedUrlCredentialsFactory {

    public ImpersonatedCredentials createDownloadSigner(
            String signerServiceAccountEmail) throws IOException {

        GoogleCredentials source =
                GoogleCredentials.getApplicationDefault()
                        .createScoped(Collections.singletonList(
                                "https://www.googleapis.com/auth/iam"));

        return ImpersonatedCredentials.create(
                source,
                signerServiceAccountEmail,
                null,
                Collections.singletonList(
                        "https://www.googleapis.com/auth/devstorage.read_only"),
                300);
    }

    public Storage createStorageClient() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Ví dụ trên dùng ADC làm source credentials và tạo impersonated signer có scope đọc Cloud Storage. IAM scope cho source credentials phục vụ IAM Credentials API. OAuth scope không thay thế IAM role: signer service account vẫn phải có `storage.objects.get` trên bucket.

Đối với upload, tạo signer credential với scope phù hợp cho read/write và cấp IAM role object creator/user tương ứng. Không dùng một signer có quyền rộng nếu có thể tách download signer và upload signer.

### 6.3. Bảo vệ và vận hành impersonation

- Không lưu access token hoặc impersonated credentials vào database.
- Không log chữ ký, session token hoặc signed URL đầy đủ.
- Dùng thời hạn token ngắn; ví dụ `300` giây trong factory.
- Cấp Token Creator cho runtime principal đúng service account đích.
- Bật IAM Credentials API ở project phù hợp.
- Theo dõi lỗi `iam.serviceAccounts.signBlob` và quota của IAM Credentials API.
- Khi chạy local, dùng user ADC đã được admin cấp quyền impersonate signer; production dùng workload identity/service account runtime.

Impersonation không làm giảm quyền của signer. Nếu signer có thể đọc toàn bucket, bất kỳ signed URL GET nào do signer tạo đều dùng authority đó trên object đã ký. Vì vậy, quyền của signer phải được giới hạn ở mức thấp nhất cần thiết.

## 7. Tạo signed URL GET bằng Java

### 7.1. Cấu hình signer và Storage bean

Có thể tạo signer một lần trong Spring ApplicationContext rồi inject vào service:

~~~java
import com.google.auth.oauth2.GoogleCredentials;
import com.google.auth.oauth2.ImpersonatedCredentials;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import java.io.IOException;
import java.util.Collections;

@Configuration(proxyBeanMethods = false)
public class SignedUrlConfiguration {

    @Bean
    ImpersonatedCredentials downloadSigner(
            @Value("${app.gcs.download-signer}") String signerEmail)
            throws IOException {

        GoogleCredentials source = GoogleCredentials.getApplicationDefault()
                .createScoped(Collections.singletonList(
                        "https://www.googleapis.com/auth/iam"));

        return ImpersonatedCredentials.create(
                source,
                signerEmail,
                null,
                Collections.singletonList(
                        "https://www.googleapis.com/auth/devstorage.read_only"),
                300);
    }

    @Bean
    Storage storage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Property:

~~~yaml
app:
  gcs:
    download-signer: document-download-signer@training-platform-dev.iam.gserviceaccount.com
~~~

Nếu Spring Framework on Google Cloud starter đã tạo `Storage` bean, inject bean hiện có thay vì tạo bean thứ hai. Ví dụ chỉ minh họa một cách cấu hình; tránh duplicate bean khi đã bật auto-configuration.

### 7.2. Sinh URL GET

~~~java
import com.google.auth.oauth2.ImpersonatedCredentials;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.net.URL;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class DocumentSignedUrlService {

    private final Storage storage;
    private final ImpersonatedCredentials downloadSigner;

    public DocumentSignedUrlService(
            Storage storage,
            ImpersonatedCredentials downloadSigner) {
        this.storage = storage;
        this.downloadSigner = downloadSigner;
    }

    public URL createDownloadUrl(
            String bucket,
            String objectName) {

        BlobInfo object = BlobInfo.newBuilder(
                BlobId.of(bucket, objectName))
                .build();

        return storage.signUrl(
                object,
                15,
                TimeUnit.MINUTES,
                Storage.SignUrlOption.withV4Signature(),
                Storage.SignUrlOption.signWith(downloadSigner));
    }
}
~~~

`15 MINUTES` là ví dụ thời hạn ngắn. Chọn thời hạn dựa trên kích thước file, tốc độ mạng và trải nghiệm người dùng. Không mặc định cấp URL trong nhiều ngày nếu một lần tải thường chỉ cần vài phút.

### 7.3. Tải file bằng signed URL

Consumer không cần gửi OAuth token hoặc service account key:

~~~bash
curl --fail --show-error \
  --output report.pdf \
  "SIGNED_URL_FROM_API"
~~~

Không gửi URL này qua log, analytics hoặc ticket công khai. Nếu API trả URL trong JSON, frontend cần giữ URL trong thời gian sử dụng và tránh lưu vào local storage nếu không cần.

## 8. Tạo signed URL PUT để upload

### 8.1. Ràng buộc Content-Type

Với signed PUT, backend nên quyết định trước object name và Content-Type. Header `Content-Type` có thể được đưa vào chữ ký để client không thể thay đổi tùy ý sau khi URL được phát hành.

~~~java
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.HttpMethod;
import com.google.cloud.storage.Storage;
import java.net.URL;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public URL createUploadUrl(
        Storage storage,
        com.google.auth.oauth2.ImpersonatedCredentials signer,
        String bucket,
        String objectName) {

    BlobInfo object = BlobInfo.newBuilder(bucket, objectName)
            .setContentType("application/pdf")
            .build();

    Map<String, String> signedHeaders =
            Map.of("Content-Type", "application/pdf");

    return storage.signUrl(
            object,
            15,
            TimeUnit.MINUTES,
            Storage.SignUrlOption.httpMethod(HttpMethod.PUT),
            Storage.SignUrlOption.withExtHeaders(signedHeaders),
            Storage.SignUrlOption.withV4Signature(),
            Storage.SignUrlOption.signWith(signer));
}
~~~

Consumer phải gửi đúng header đã ký:

~~~bash
curl --fail --show-error \
  --request PUT \
  --header "Content-Type: application/pdf" \
  --upload-file ./report.pdf \
  "SIGNED_URL_FROM_API"
~~~

Nếu Content-Type khác giá trị đã ký, Cloud Storage có thể trả lỗi chữ ký không hợp lệ. Không chỉ dựa vào phần mở rộng PDF; backend vẫn cần xác minh nội dung file sau upload.

### 8.2. Ngăn ghi đè object ngoài ý muốn

Signed PUT có thể ghi đè object hiện tại nếu request được ký cho phép và signer có quyền cần thiết. Với upload tạo object mới, nên dùng object name duy nhất và ký thêm query precondition `ifGenerationMatch=0`.

~~~java
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.HttpMethod;
import com.google.cloud.storage.Storage;
import java.net.URL;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public URL createNewObjectOnlyUrl(
        Storage storage,
        com.google.auth.oauth2.ImpersonatedCredentials signer,
        String bucket,
        String objectName) {

    BlobInfo object = BlobInfo.newBuilder(bucket, objectName)
            .setContentType("application/pdf")
            .build();

    return storage.signUrl(
            object,
            15,
            TimeUnit.MINUTES,
            Storage.SignUrlOption.httpMethod(HttpMethod.PUT),
            Storage.SignUrlOption.withExtHeaders(
                    Map.of("Content-Type", "application/pdf")),
            Storage.SignUrlOption.withQueryParams(
                    Map.of("ifGenerationMatch", "0")),
            Storage.SignUrlOption.withV4Signature(),
            Storage.SignUrlOption.signWith(signer));
}
~~~

Precondition `ifGenerationMatch=0` yêu cầu object chưa tồn tại tại thời điểm upload. Nếu object đã có live generation, request thất bại thay vì ghi đè. Query parameter phải được ký; consumer không được tự thêm hoặc bỏ tham số.

### 8.3. Kiểm tra object sau upload

Backend không nên đánh dấu tài liệu hoàn tất chỉ vì browser nhận HTTP 200. Sau upload:

1. Tra object theo bucket/object name đã cấp.
2. Đọc generation, size, content type và checksum.
3. So sánh kích thước tối đa và loại file được phép.
4. Kiểm tra tenant/document ownership và trạng thái upload.
5. Ghi metadata nghiệp vụ vào database.
6. Chỉ sau khi xác minh mới chuyển tài liệu sang trạng thái sẵn sàng.

Signed URL kiểm soát quyền truy cập storage; nó không thay thế validation file hoặc authorization trong domain.

## 9. Signed URL với generation và query parameter

Nếu muốn URL GET trỏ tới một generation cụ thể, cần đưa generation vào resource và query parameter đã ký:

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.net.URL;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public URL createVersionDownloadUrl(
        Storage storage,
        com.google.auth.oauth2.ImpersonatedCredentials signer,
        String bucket,
        String objectName,
        long generation) {

    BlobInfo object = BlobInfo.newBuilder(
            BlobId.of(bucket, objectName, generation))
            .build();

    return storage.signUrl(
            object,
            15,
            TimeUnit.MINUTES,
            Storage.SignUrlOption.withQueryParams(
                    Map.of("generation", Long.toString(generation))),
            Storage.SignUrlOption.withV4Signature(),
            Storage.SignUrlOption.signWith(signer));
}
~~~

Điều này hữu ích khi object có versioning và ứng dụng cần bảo đảm người dùng tải đúng phiên bản đã duyệt. Nếu chỉ ký object name live, URL thường đọc phiên bản live tại thời điểm request.

Có thể ký query parameter như `response-content-disposition` để trình duyệt tải file với tên mong muốn. Mọi query parameter cần được đưa vào quá trình ký; không thêm chúng sau khi đã tạo URL.

## 10. Thời hạn, key rotation và thu hồi URL

### 10.1. Giới hạn V4

V4 `X-Goog-Expires` chấp nhận thời hạn từ 1 giây đến tối đa **604800 giây (7 ngày)**. Đây là giới hạn protocol, không phải khuyến nghị thời hạn mặc định.

Thời hạn ngắn giảm khoảng thời gian URL bị lạm dụng nếu bị lộ. Chọn thời hạn thực tế theo loại dữ liệu và hành vi client:

| Use case | Ví dụ thời hạn khởi đầu |
| --- | --- |
| Preview ảnh hoặc PDF nhỏ | 5–15 phút |
| Download file dung lượng lớn | 15–60 phút tùy tốc độ và retry |
| Upload file lớn | 15–60 phút hoặc quy trình resumable riêng |
| Link chia sẻ với đối tác | Ngắn nhất có thể theo quy trình nghiệp vụ |

Các giá trị này là gợi ý thiết kế; cần kiểm thử với kích thước file và mạng thực tế.

### 10.2. Chữ ký dùng IAM signBlob

Khi ký bằng IAM Credentials API `signBlob`, Google sử dụng service account key được quản lý và luân chuyển định kỳ. Với chữ ký có expiration dài hơn 12 giờ, URL có thể ngừng hoạt động sớm hơn thời điểm hết hạn khai báo do key rotation. Vì vậy, chữ ký qua `signBlob` phù hợp với URL ngắn hạn.

Mặc dù V4 cho phép tối đa 7 ngày, không nên phát hành URL 7 ngày qua IAM `signBlob` mà giả định nó chắc chắn hoạt động đủ 7 ngày. Nếu cần chia sẻ dài hơn, cân nhắc kiến trúc khác và đánh giá kỹ vòng đời khóa, nhưng không chuyển sang phát hành key dài hạn thiếu kiểm soát.

### 10.3. Thu hồi và vòng đời

Signed URL không có cơ chế thu hồi riêng từng URL như một session record trong ứng dụng. Thời hạn là giới hạn chính. Việc thay đổi quyền của signer, vô hiệu hóa/luân chuyển khóa hoặc thay đổi trạng thái object có thể ảnh hưởng các URL đang phát hành; tác động phụ thuộc cơ chế ký và policy.

Do đó:

- Dùng URL ngắn hạn.
- Không dùng signed URL làm token đăng nhập lâu dài.
- Nếu cần thu hồi tức thời theo từng người dùng, kiểm tra quyền tại backend trước khi cấp URL và giới hạn thời hạn đủ ngắn.
- Nếu cần kiểm soát từng phiên tải, cân nhắc proxy download qua backend hoặc một gateway có session state.
- Không giả định có thể thu hồi một URL riêng lẻ mà không ảnh hưởng credential hoặc resource liên quan.

## 11. Bảo vệ signed URL

### 11.1. Xem URL như secret

Signed URL chứa chữ ký và thông tin xác thực trong query string. Người nắm URL có thể sử dụng nó trong thời hạn còn hiệu lực. Không:

- Ghi toàn bộ URL vào application log, access log hoặc distributed trace.
- Đưa URL vào analytics event, crash report hoặc hệ thống ticket.
- Gắn URL vào HTML/metadata công khai.
- Lưu URL trong database lâu dài nếu không có lý do nghiệp vụ.
- Gửi URL qua kênh không mã hóa.
- Dùng URL của một tenant cho tenant khác.

Nếu cần log, chỉ ghi object ID nội bộ, method, expiration, signer identity, request ID và kết quả phát hành; che query string và chữ ký.

### 11.2. Chỉ cấp object đã được backend xác minh

Không tạo signed URL từ bucket/object name tùy ý do client gửi. Backend phải:

1. Xác thực người dùng.
2. Tải metadata document từ database.
3. Kiểm tra tenant ownership và quyền xem/sửa.
4. Lấy bucket/object name từ bản ghi đã tin cậy.
5. Chọn signer phù hợp với thao tác.
6. Tạo URL với method, header, query và expiry cố định.
7. Ghi audit event không chứa URL.

Nếu client được quyền chọn object name, hãy ánh xạ qua ID nghiệp vụ và allowlist prefix; không nối trực tiếp path tùy ý.

### 11.3. Signed URL có thể được dùng nhiều lần

Signed URL không mặc nhiên là one-time token. Một URL GET có thể được dùng nhiều lần trong thời hạn. Signed PUT cũng có thể được gửi lại, và nếu không có precondition thì có thể ghi đè object theo quyền signer.

Dùng object name duy nhất, `ifGenerationMatch=0`, giới hạn thời gian và kiểm tra trạng thái nghiệp vụ để giảm replay hoặc overwrite ngoài ý muốn.

### 11.4. Dữ liệu nhạy cảm và cache

Với tài liệu nhạy cảm, đặt cache policy phù hợp cho object và response; cân nhắc `Cache-Control: private, no-store`. Không mặc định mọi proxy/CDN đều xử lý signed URL theo cách bạn mong đợi. Kiểm tra cache key, query string handling và log redaction của hạ tầng phân phối nội dung.

## 12. CORS khi browser sử dụng signed URL

Nếu browser gọi trực tiếp Cloud Storage từ một website khác origin, trình duyệt áp dụng CORS. Bucket cần CORS rule cho origin, method và request header phù hợp:

- Origin: domain frontend cụ thể, ví dụ `https://app.example.com`.
- Method: `GET` và/hoặc `PUT`.
- Request headers: `Content-Type` và các header đã ký mà browser gửi.
- Response headers: các header mà frontend cần đọc, ví dụ `ETag` hoặc `Content-Range`.
- Max age: thời gian cache preflight theo chính sách.

CORS là cơ chế của trình duyệt để kiểm soát cross-origin response. Nó không cấp quyền IAM và không thay thế chữ ký. Signed URL có thể chạy bằng `curl` mà không cần CORS; browser có thể bị chặn nếu CORS chưa được cấu hình.

Không dùng wildcard origin cho production nếu frontend có domain cố định và dữ liệu nhạy cảm. Kiểm tra preflight `OPTIONS` và header thực tế mà browser gửi.

## 13. Signed URL và resumable upload

Signed URL thường phù hợp với một request GET hoặc PUT cho object. Với upload lớn cần tiếp tục sau gián đoạn, **resumable upload** có cơ chế session URI riêng:

1. Backend hoặc client khởi tạo resumable upload.
2. Cloud Storage trả session URI.
3. Client gửi các chunk tiếp theo tới session URI.
4. Session URI hoạt động như bearer credential trong vòng đời phiên.

Thông thường backend nên khởi tạo resumable upload rồi gửi session URI cho client. Việc tạo signed URL cho request khởi tạo có thể hữu ích khi server và client ở xa nhau về địa lý, nhưng các PUT tiếp theo dùng session URI chứ không tiếp tục dùng signed URL ban đầu.

Session URI cũng phải được bảo vệ như secret: chỉ gửi qua HTTPS, không log và không cấp cho tenant khác. Phân biệt session URI với signed URL vì chúng có semantics, vòng đời và request flow khác nhau.

## 14. Tích hợp Spring Boot theo mô hình backend cấp quyền

### 14.1. Luồng download

~~~mermaid
sequenceDiagram
    participant Browser
    participant API as Spring Boot
    participant DB as Document DB
    participant GCS as Cloud Storage

    Browser->>API: GET /documents/{id}/download-url
    API->>API: Xác thực user
    API->>DB: Tìm document và tenant
    DB-->>API: bucket/object/generation
    API->>API: Kiểm tra quyền xem
    API->>API: Ký URL bằng download signer
    API-->>Browser: URL + expiresAt
    Browser->>GCS: GET signed URL
    GCS-->>Browser: File bytes
~~~

Backend không cần đọc bytes rồi proxy về browser. Nó chỉ cấp quyền sau khi kiểm tra domain authorization. URL nên có expiration ngắn và object/generation rõ ràng.

### 14.2. Luồng upload

~~~mermaid
sequenceDiagram
    participant Browser
    participant API as Spring Boot
    participant DB as Document DB
    participant GCS as Cloud Storage

    Browser->>API: POST /documents/upload-url
    API->>API: Xác thực user và quota
    API->>DB: Tạo document PENDING
    API->>API: Chọn object name và signer
    API-->>Browser: PUT signed URL + required headers
    Browser->>GCS: PUT file
    GCS-->>Browser: Upload result
    Browser->>API: POST /documents/{id}/complete
    API->>GCS: Đọc metadata và checksum
    GCS-->>API: generation, size, contentType
    API->>DB: Đánh dấu READY nếu hợp lệ
~~~

Nếu người dùng bỏ dở upload, document vẫn ở trạng thái `PENDING`; job cleanup có thể xử lý theo TTL. Không đánh dấu `READY` chỉ dựa vào callback từ browser.

### 14.3. API response nên trả gì?

Có thể trả:

~~~json
{
  "documentId": "doc-123",
  "method": "PUT",
  "url": "SIGNED_URL",
  "requiredHeaders": {
    "Content-Type": "application/pdf"
  },
  "expiresAt": "2026-11-24T10:30:00Z"
}
~~~

Đây là response minh họa. Không lưu URL vào bảng document như một thuộc tính lâu dài. `expiresAt` giúp frontend biết khi nào cần xin URL mới; URL vẫn là secret.

## 15. Kiểm thử signed URL

### 15.1. Unit test

Kiểm thử service phát hành URL bằng cách mock Storage hoặc signer boundary:

- User không có quyền xem không nhận được URL.
- Tenant A không thể xin URL cho document của tenant B.
- GET service chỉ phát hành method GET.
- PUT service chỉ ký Content-Type được cho phép.
- Expiration nằm trong giới hạn cấu hình.
- Object name lấy từ metadata tin cậy, không từ path tùy ý.
- URL không xuất hiện trong log hoặc exception message.
- Upload mới dùng `ifGenerationMatch=0` nếu không cho phép overwrite.

Không cần kiểm tra giá trị chữ ký cryptographic trong unit test; kiểm tra option và authorization boundary.

### 15.2. Integration test trên GCP test project

1. Tạo signer service account riêng cho test.
2. Cấp quyền object tối thiểu ở bucket test.
3. Cấp Token Creator cho test runtime principal trên signer service account.
4. Bật IAM Credentials API.
5. Tạo signed GET URL và tải object bằng HTTP client không có Google credentials.
6. Tạo signed PUT URL, gửi đúng Content-Type và xác minh object được tạo.
7. Gửi sai method hoặc sai Content-Type; xác nhận request bị từ chối.
8. Thử URL hết hạn hoặc dùng query parameter không nằm trong chữ ký.
9. Thử signer thiếu `storage.objects.get` hoặc runtime thiếu `iam.serviceAccounts.signBlob`.
10. Kiểm tra CORS trong browser test nếu frontend gọi trực tiếp.
11. Xác minh generation, size, content type và checksum sau upload.
12. Dọn object và test identity theo quy trình.

Không chạy test destructive trên bucket production. Không in URL thật vào test report; che query string trong assertion failure.

### 15.3. Kiểm tra IAM theo vai trò

| Test principal | Kỳ vọng |
| --- | --- |
| Runtime có Token Creator trên signer | Có thể yêu cầu ký thay signer |
| Runtime không có `iam.serviceAccounts.signBlob` | Không thể tạo chữ ký bằng signer đó |
| Signer có Object Viewer | URL GET hoạt động; URL PUT không được phép |
| Signer có Object Creator | URL PUT tạo object mới; không overwrite object cũ |
| Signer có Object User | Có thể đọc/ghi/xóa object trong phạm vi role |
| Consumer không có Google credentials | Dùng signed URL hợp lệ được |
| Consumer dùng sai method/header | Request bị từ chối |

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `IllegalStateException` khi `signUrl` | Credential không triển khai `ServiceAccountSigner` | Dùng `ImpersonatedCredentials` hoặc signer tường minh |
| `iam.serviceAccounts.signBlob` denied | Runtime principal thiếu Token Creator trên signer SA | Kiểm tra IAM binding trên đúng service account |
| `403` khi consumer dùng URL | Signer thiếu object permission, URL hết hạn hoặc policy từ chối | Kiểm tra signer role, expiration và bucket policy |
| `SignatureDoesNotMatch` | Method/header/query/path khác request đã ký | So sánh chính xác method, Content-Type, host và query |
| `AccessDenied` khi PUT overwrite | Signer thiếu quyền xóa object hiện tại | Dùng objectCreator cho create-only hoặc role có create/delete |
| URL GET chạy bằng curl nhưng browser lỗi | CORS chưa cho phép origin/method/header | Kiểm tra preflight và bucket CORS |
| URL hết hạn sớm | Thời hạn quá dài khi ký bằng IAM signBlob và key rotation | Dùng URL ngắn hơn, thường dưới 12 giờ |
| URL không còn dùng được sau thay đổi object | Generation/resource không còn phù hợp hoặc object đã bị xóa | Kiểm tra generation và object lifecycle |
| URL hoạt động sau khi chia sẻ ngoài dự kiến | URL bị lộ và chưa hết hạn | Rút ngắn expiry, xử lý signer/resource và redaction |
| PUT upload thành công nhưng document không READY | Backend chưa xác minh object hoặc callback không hoàn tất | Chạy bước complete/verification và cleanup PENDING |

### 16.1. Phân biệt lỗi tạo URL và lỗi dùng URL

- Lỗi tạo URL thường liên quan `ServiceAccountSigner`, `iam.serviceAccounts.signBlob`, API chưa bật hoặc credential scope.
- Lỗi dùng URL thường liên quan quyền object của signer, thời hạn, method, header, query parameter, object path hoặc bucket policy.
- Lỗi browser có thể liên quan CORS dù cùng URL chạy được bằng `curl`.

Không cấp `roles/storage.admin` để xử lý lỗi ký. Hãy xác định principal nào thiếu permission nào.

## 17. So sánh với AWS S3 presigned URL và Azure SAS

| Khía cạnh | Google Cloud Storage Signed URL | Amazon S3 Presigned URL | Azure Blob SAS |
| --- | --- | --- | --- |
| Danh tính ký | Thường là service account | IAM principal/credential của AWS | Storage account key hoặc user delegation key |
| Cơ chế ký | V4 RSA hoặc HMAC theo loại credential | AWS Signature Version 4 | Shared Access Signature |
| Quyền truy cập | IAM permission của signer | IAM policy của signer và bucket/object policy | Quyền và resource scope ghi trong SAS |
| Thời hạn | V4 tối đa 7 ngày; IAM signBlob có lưu ý key rotation | Phụ thuộc cách ký và credential/session lifetime | Phụ thuộc signed start/expiry và loại SAS |
| Giới hạn request | Method, resource, signed headers/query | Method, resource, signed headers/query | Resource, permission, protocol, IP/time và signed fields |
| Java SDK | `Storage.signUrl` | `S3Presigner` | `BlobServiceSasSignatureValues` / user delegation SAS |

Cả ba cơ chế đều tạo URL có quyền tạm thời và cần được bảo vệ như bearer secret. Khác biệt nằm ở cách xác định signer, permission model, token lifetime và chi tiết canonical signing. Không chuyển nguyên cấu hình IAM role, expiration hoặc header từ provider này sang provider khác mà không kiểm tra semantics.

## 18. Bài tập thực hành tổng hợp

**Bối cảnh:** Ứng dụng Spring Boot `document-api` lưu tài liệu của nhiều tenant trong bucket `training-documents-dev`. Người dùng có quyền xem tài liệu muốn tải file trực tiếp từ GCS; người dùng có quyền upload muốn tải file trực tiếp lên bucket.

### Nhiệm vụ A — Danh tính và IAM

1. Tạo runtime service account và signer service account riêng.
2. Bật IAM Service Account Credentials API.
3. Cấp Token Creator cho runtime trên signer service account.
4. Cấp Object Viewer cho download signer.
5. Cấp Object Creator cho upload signer.
6. Giải thích vì sao consumer không cần Google IAM role.

### Nhiệm vụ B — Signed GET

1. Dùng `ImpersonatedCredentials` làm `ServiceAccountSigner`.
2. Sinh signed URL V4 với thời hạn 15 phút.
3. Xác thực document ownership trước khi ký.
4. Tải file bằng `curl` không có OAuth token.
5. Tạo URL cho generation cụ thể.

### Nhiệm vụ C — Signed PUT

1. Chọn object name do backend sinh.
2. Ký method PUT và Content-Type `application/pdf`.
3. Dùng `ifGenerationMatch=0` để tránh overwrite.
4. Upload bằng `curl` với header đã ký.
5. Gọi API complete để backend xác minh metadata/generation/checksum.

### Nhiệm vụ D — Bảo mật và kiểm thử

- Kiểm tra signer thiếu objectViewer thì GET thất bại.
- Kiểm tra runtime thiếu Token Creator thì không tạo được URL.
- Thử sai method, Content-Type, query và expiration.
- Kiểm tra CORS trên browser.
- Đảm bảo URL không xuất hiện trong log.
- Kiểm tra upload chưa hoàn tất được cleanup.
- So sánh signed URL với S3 presigned URL và Azure SAS.

**Tiêu chí đạt:** Người học phân biệt được signing principal, signer service account và URL consumer; cấp đúng quyền `signBlob` và object permissions; tạo GET/PUT URL V4 bằng Java; kiểm soát method/header/expiry; và tích hợp quy trình upload/download trực tiếp có xác minh nghiệp vụ.

## 19. Ghi nhớ

- Signed URL cấp quyền tạm thời cho người nắm URL; xem URL như bearer credential.
- Signed URL Cloud Storage dùng XML API endpoint và chỉ cho phép request khớp method, resource, signed headers, query và expiration.
- Signing principal cần `iam.serviceAccounts.signBlob` trên signer service account; signer cần object permission tương ứng với GET/PUT/overwrite.
- Dùng `ImpersonatedCredentials` để ký qua IAM Credentials API mà không cần phát hành service account private key dài hạn.
- V4 expiration tối đa 604800 giây (7 ngày); khi ký bằng IAM `signBlob`, nên dùng thời hạn ngắn do service account signing keys được luân chuyển.
- Dùng object name do backend kiểm soát, signed headers, `ifGenerationMatch=0` và kiểm tra metadata sau upload.
- CORS chỉ giải quyết cross-origin browser access, không cấp quyền và không thay thế chữ ký.
- Không log URL; nếu cần kiểm soát theo từng phiên hoặc thu hồi ngay, cân nhắc proxy/gateway có session state.

### Tài liệu tham khảo

- [Signed URLs — Cloud Storage](https://docs.cloud.google.com/storage/docs/access-control/signed-urls)
- [V4 signing process with Cloud Storage tools](https://docs.cloud.google.com/storage/docs/access-control/signing-urls-with-helpers)
- [Create signatures with signBlob](https://docs.cloud.google.com/storage/docs/authentication/creating-signatures)
- [V4 signing process with your own program](https://docs.cloud.google.com/storage/docs/access-control/signing-urls-manually)
- [XML API query parameters and headers](https://docs.cloud.google.com/storage/docs/xml-api/reference-headers)
- [Cloud Storage Java Storage interface](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
- [ImpersonatedCredentials Java API](https://docs.cloud.google.com/java/docs/reference/google-auth-library/latest/com.google.auth.oauth2.ImpersonatedCredentials)
- [Cloud Storage CORS](https://docs.cloud.google.com/storage/docs/cross-origin)
