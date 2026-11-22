# Secrets, environment variables và gắn volume trên Cloud Run

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **environment variables**, **Secret Manager references** và **volume mounts** theo độ nhạy cảm, thời điểm đọc, tuổi thọ dữ liệu và cách triển khai.
2. Cấu hình Cloud Run service bằng **gcloud** và YAML; nhận biết khác biệt giữa cập nhật gia tăng và thay thế toàn bộ cấu hình.
3. Cấp **IAM tối thiểu** cho service identity để đọc một secret hoặc Cloud Storage bucket mà không lưu JSON service account key.
4. Chọn đúng kiểu volume: **secret**, **in-memory**, **ephemeral disk**, **Cloud Storage FUSE** hoặc **NFS/Filestore**; hiểu giới hạn concurrency, POSIX, networking và persistence.
5. Viết ứng dụng **Java/Spring Boot** đọc biến môi trường, secret file và dữ liệu tạm an toàn; thiết kế rotation, rollout và xử lý lỗi.
6. Kiểm thử các tình huống thiếu quyền, mount thất bại, hết bộ nhớ, stale secret, sai đường dẫn và chi phí ngoài dự kiến.

## 1. Bối cảnh và ba loại nhu cầu

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học đưa ứng dụng Java từ project/IAM/VPC tới Compute Engine, GKE và **Cloud Run**, tích hợp storage/database, tự động triển khai và theo dõi độ tin cậy cùng chi phí.

Giả sử dịch vụ **orders-api** chạy Spring Boot trên Cloud Run:

- Đọc **APP_ENV=production** và **LOG_LEVEL=INFO**: cấu hình thông thường, không bí mật.
- Đọc **PAYMENT_API_KEY**: thông tin nhạy cảm cần lưu ở **Secret Manager**.
- Xử lý PDF trong một thư mục tạm: cần dung lượng có giới hạn, **không cần giữ qua instance restart**.
- Đọc ảnh từ **Cloud Storage** hoặc chia sẻ tài liệu qua **Filestore NFS**: cần dữ liệu bền vững ở dịch vụ ngoài Cloud Run.

Cloud Run là nền tảng chạy container có khả năng scale out/in và tạo **revisions**. Mỗi instance có vòng đời riêng; không được coi file ghi trong một instance là file chung hay bền vững giữa các instances. Cấu hình env/secrets/volumes gắn với **revision**; cập nhật cấu hình service tạo **revision mới**, các instance đang chạy revision cũ có thể vẫn dùng cấu hình cũ trong thời gian chuyển traffic.

### Bảng quyết định nhanh

| Nhu cầu | Giải pháp ưu tiên | Lý do |
|---|---|---|
| Profile, feature flag không nhạy cảm, endpoint | **Plain environment variable** | Đơn giản, cố định theo revision |
| Password/API key đã chốt phiên bản cho lần phát hành | **Secret Manager → environment variable** | Fetch lúc khởi tạo instance, reproducible |
| Chứng chỉ, key hoặc secret cần được đọc lại sau rotation | **Secret Manager → mounted secret file** | Đọc file, dùng version latest khi phù hợp |
| Job tạo file tạm nhỏ, giới hạn bộ nhớ | **In-memory volume** | Nhanh, giới hạn dung lượng, không bền vững |
| File tạm lớn, tránh dùng toàn RAM | **Ephemeral disk** trên gen2 | Disk tạm theo instance, quota/chi phí riêng |
| Ảnh, tài liệu, model ở object storage | **Cloud Storage SDK** hoặc FUSE mount khi cần đường dẫn file | Dữ liệu ngoài instance; FUSE không phải POSIX đầy đủ |
| Chia sẻ cây thư mục NFS với nhiều clients | **Filestore/NFS volume** | Shared file namespace qua VPC, có hạn chế NFS locking |
| Dữ liệu giao dịch quan trọng | **Cloud SQL/AlloyDB/Spanner** hay dịch vụ phù hợp | Không dùng thư mục tạm hoặc object mount thay database |

## 2. Environment variables: cấu hình theo revision

### 2.1. Đặc điểm

Environment variables được cung cấp cho container khi instance bắt đầu. Ví dụ Java:

~~~java
String env = System.getenv().getOrDefault("APP_ENV", "dev");
String logLevel = System.getenv().getOrDefault("LOG_LEVEL", "INFO");
~~~

Ứng dụng có thể lấy cấu hình mà không cần đọc file riêng, nhưng:

- Biến thông thường nằm trong **revision configuration** và có thể hiện với người được phép xem cấu hình. **Không đặt secret plaintext trong --set-env-vars hoặc Dockerfile ENV**.
- Một revision giữ tập cấu hình của nó; thay đổi env trên service tạo revision mới. Không nên coi env là cơ chế thay đổi tức thời bên trong container đang chạy.
- **PORT** được Cloud Run cấp để chỉ cổng HTTP mà ingress container phải lắng nghe; **không set PORT thủ công**. Các key bắt đầu bằng **X_GOOGLE_** được dành riêng, và tên env không được rỗng hoặc chứa dấu **=**.
- Environment variables được cấu hình lúc **build** khác lúc **runtime**; đừng nhúng thông tin nhạy cảm vào image layer.

### 2.2. Các lệnh gcloud cơ bản

Giả sử project **shop-dev-001**, region **asia-southeast1**, service **orders-api** đã tồn tại. Tất cả tên là ví dụ; lệnh update có thể tạo revision mới và ảnh hưởng traffic.

~~~bash
# Chỉ đọc: xác nhận project và cấu hình
gcloud config get-value project
gcloud run services describe orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1

# Cập nhật gia tăng: giữ các biến khác
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --update-env-vars=APP_ENV=staging,LOG_LEVEL=INFO

# Chỉ xóa một key
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --remove-env-vars=OLD_FEATURE_FLAG
~~~

**Chọn flag đúng:**

| Flag | Hành vi | Cảnh báo |
|---|---|---|
| **--update-env-vars** | Thêm hoặc thay một số key, giữ các key khác | Phù hợp thay đổi nhỏ |
| **--set-env-vars** | Thay thế tập biến thông thường bằng tập được cung cấp | Có thể làm mất những key không liệt kê |
| **--remove-env-vars** | Gỡ các key được chỉ định | Kiểm tra app có còn dùng chúng |
| **--clear-env-vars** | Xóa toàn bộ biến thông thường được cấu hình | Thao tác có ảnh hưởng rộng |
| **--env-vars-file** | Đọc tập key/value từ file | Không commit file chứa secret thật |

Khi giá trị có dấu phẩy, ký tự đặc biệt hoặc nhiều dòng, dùng **env-vars-file** hoặc cú pháp delimiter tùy chỉnh được gcloud hỗ trợ. Không dán token/khóa thật vào câu lệnh vì shell history, build logs và quy trình change review có thể lưu lại.

### 2.3. Spring Boot và cổng lắng nghe

~~~properties
# application.properties
spring.profiles.active=${APP_ENV:dev}
logging.level.root=${LOG_LEVEL:INFO}
server.port=${PORT:8080}
~~~

Khi đặt cấu hình ở project thật, hãy sử dụng **Spring externalized configuration**; file này chỉ giữ **các tham chiếu**, không giữ bí mật. Cloud Run yêu cầu ingress container lắng nghe trên **0.0.0.0** tại cổng **PORT**, không chỉ loopback.

## 3. Secret Manager: nơi lưu giá trị nhạy cảm

**Secret Manager** quản lý secret và các **versions**, IAM, lifecycle, auditing và rotation. Trên Cloud Run, có hai cơ chế tích hợp được quản lý:

| Cách cấp secret | Thời điểm lấy giá trị | Khi không truy cập được | Rotation |
|---|---|---|---|
| **Environment variable reference** | Trước khi container instance khởi động | Instance **không khởi động** được nếu fetch secret thất bại | Giá trị của instance đang chạy không đổi; nên **pin version số** và rollout revision mới |
| **Secret volume mount** | Khi ứng dụng **đọc file đã mount** | Instance có thể khởi động nhưng **file read thất bại** | Mount **latest** có thể nhận phiên bản mới khi đọc lại; ứng dụng vẫn phải reload |

Cloud Run kiểm tra quyền truy cập các secret được cấu hình **tại thời điểm deploy**. Việc qua bước deploy không bảo đảm service identity có quyền mãi về sau: IAM có thể bị thu hồi, secret version bị disable/destroy hoặc backend gặp lỗi lúc runtime.

### 3.1. Vì sao không lưu secret như env plaintext?

Ví dụ thiếu an toàn:

~~~bash
# KHÔNG CHẠY: plaintext secret có thể lưu trong history/revision
gcloud run services update orders-api \
  --set-env-vars=PAYMENT_API_KEY=ACTUAL_REAL_SECRET
~~~

Thay vào đó, giữ bí mật trong Secret Manager và chỉ cấu hình **reference** tới secret. Kể cả secret được inject làm env, ứng dụng có thể vô tình log môi trường hoặc lộ qua heap dump; không in giá trị trong log/health endpoint.

### 3.2. IAM đúng loại danh tính

Phải phân biệt:

- **Deployer**: người/CI thay đổi cấu hình Cloud Run, cần quyền deploy và quyền sử dụng service account (chẳng hạn Cloud Run Developer và Service Account User trong phạm vi thích hợp).
- **Service identity**: service account mà **container chạy dưới danh tính đó**, cần **Secret Manager Secret Accessor** trên từng secret và quyền đọc/ghi bucket khi phù hợp.
- **Secret administrator/rotator**: được tạo, thay phiên bản hoặc quản lý IAM; **không nên** chính là runtime identity.

Nếu Java gọi Cloud Storage/Secret Manager API trực tiếp bằng client library, nên dùng **Application Default Credentials (ADC)** từ service identity, **không gắn file khóa JSON** hoặc tự set GOOGLE_APPLICATION_CREDENTIALS tới key dài hạn.

### 3.3. Giới hạn vùng và phạm vi

Tài liệu Cloud Run secrets dành cho services hiện nêu **không hỗ trợ regional Secret Manager secrets** trong cấu hình tích hợp; hãy sử dụng **secret được hỗ trợ theo resource path**. Với secret ở project khác, tham chiếu **projects/PROJECT_NUMBER/secrets/SECRET_NAME** và cấp IAM trên secret ở project nguồn. Không nhầm **project number** với **project ID**, cũng không tự giả định Secret Manager replication policy nào phù hợp mọi yêu cầu data residency.

## 4. Thực hành A — Secret Manager → Cloud Run env và file

### 4.1. Bối cảnh lab

| Thuộc tính | Ví dụ |
|---|---|
| Project | **shop-dev-001** |
| Region Cloud Run | **asia-southeast1** |
| Service | **orders-api** |
| Service account runtime | **orders-runtime@shop-dev-001.iam.gserviceaccount.com** |
| Secret | **orders-db-password** |
| Image | **asia-southeast1-docker.pkg.dev/shop-dev-001/apps/orders-api:1.0.0** |

Các resource chỉ là ví dụ; phải được tạo trước nếu chưa tồn tại. Nếu thực hành tạo tài nguyên thật, sẽ có chi phí. Chỉ làm trên project lab và không sao chép giá trị mật khẩu thật vào Chat, Git, terminal output hoặc mã nguồn.

### 4.2. Tạo secret và một version an toàn cho lab

~~~bash
# Thay đổi project; cần quyền và billing phù hợp.
gcloud services enable secretmanager.googleapis.com \
  --project=shop-dev-001

gcloud secrets create orders-db-password \
  --project=shop-dev-001 \
  --replication-policy=automatic

# Dùng file giả lập (không có mật khẩu thật) đã tạo bằng quy trình an toàn.
gcloud secrets versions add orders-db-password \
  --project=shop-dev-001 \
  --data-file=./lab-placeholder-secret.txt

# Xem metadata, KHÔNG in payload
gcloud secrets versions list orders-db-password \
  --project=shop-dev-001
~~~

File **lab-placeholder-secret.txt** là dữ liệu thử nghiệm do người học chuẩn bị, không phải file được tạo trong repository của bài. Trong production, secret được nhập qua kênh kiểm soát, file plaintext tạm được xử lý theo chính sách bảo mật và không lưu trong VCS.

### 4.3. Cấp quyền đọc một secret cho runtime

~~~bash
gcloud secrets add-iam-policy-binding orders-db-password \
  --project=shop-dev-001 \
  --member="serviceAccount:orders-runtime@shop-dev-001.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Xem policy (không xem secret value)
gcloud secrets get-iam-policy orders-db-password \
  --project=shop-dev-001
~~~

Không cấp **roles/secretmanager.admin** trên toàn project cho application chỉ cần đọc một secret. Nếu lệnh deploy báo thiếu quyền, phải kiểm tra **đúng service identity đang cấu hình**, không tự chuyển sang một identity giàu quyền.

### 4.4. Cấp secret qua environment variable

~~~bash
# Service và runtime SA cần đã tồn tại. VERSION=1 chỉ là minh họa.
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --update-secrets=DB_PASSWORD=orders-db-password:1
~~~

Java đọc bằng **System.getenv("DB_PASSWORD")**, nhưng tuyệt đối không log value. **Phiên bản số** giúp revision có cấu hình rõ ràng; khi tạo secret version 2, các instances của revision cũ vẫn dùng version đã gán. Nếu tham chiếu **latest** dạng env, các instances khởi động ở những thời điểm khác nhau có thể lấy phiên bản khác nhau, vì vậy Google khuyến nghị pin version.

### 4.5. Gắn secret như file

~~~bash
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --update-secrets=/etc/secrets/db/password=orders-db-password:latest
~~~

Lệnh dùng **đường dẫn file tuyệt đối** ở vế trái; thư mục **/etc/secrets/db/** là mount path, **password** là file được tạo. Khi secret rotate và tham chiếu latest, lần đọc file tiếp theo có thể nhận version mới; **Java vẫn phải chủ động đọc lại và thay connection pool**.

Không mount lên đường dẫn đang chứa file ứng dụng quan trọng: mount có thể **che các file đã có trong thư mục đích**. Cloud Run không cho mount vào **/dev, /proc, /sys** và các thư mục con, hoặc mount nhiều secret volumes trùng một path.

### 4.6. Kiểm tra kết quả mà không tiết lộ bí mật

~~~bash
gcloud run services describe orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --format export

gcloud run revisions list \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --service=orders-api
~~~

Đọc **tên secret, version, mount path và service identity**; tránh lệnh in toàn bộ env values/contents. Có thể cho ứng dụng log *secret file exists/readable?* hoặc version theo cơ chế được phê duyệt, **không log password**.

**Cảnh báo khi sửa:** **--update-secrets** thêm/sửa reference đã nêu và giữ references khác; **--set-secrets** thay thế toàn bộ cấu hình secrets, có thể vô tình gỡ secret khác. Khi deploy file YAML đầy đủ, cần review diff vì có thể thay thế nhiều cấu hình revision cùng lúc.

## 5. Rotation và thay đổi revisions

Một rotation thành công gồm: **tạo credential mới ở hệ thống đích → tạo secret version mới → chuyển ứng dụng sử dụng version mới → kiểm thử → thu hồi credential cũ**. Thay version trong Secret Manager **không** tự làm mật khẩu database hoặc API phía đối tác thay đổi.

~~~mermaid
flowchart LR
    A["Tạo credential mới"] --> B["Thêm Secret Manager version 2"]
    B --> C{"Ứng dụng nhận secret bằng?"}
    C -->|Env| D["Tạo revision mới pin version 2"]
    C -->|Mounted file latest| E["App đọc lại file + refresh clients"]
    D --> F["Canary / smoke test"]
    E --> F
    F --> G["Chuyển traffic, đo SLO"]
    G --> H["Thu hồi credential cũ"]
~~~

**Với env reference**: rollout revision mới, có thể chia traffic/canary, theo dõi lỗi startup; env của instance đang chạy không tự đổi. **Với mounted file**: nếu dùng latest, thao tác đọc có thể lấy bản mới nhưng app phải reload; khi password cũ không còn hợp lệ, connection pool giữ credential cũ sẽ gặp lỗi.

**Các rủi ro cần quản trị:**

- Nếu Secret Manager mất kết nối, env secret có thể chặn **cold start**; mounted file có thể gây lỗi lúc **read**. Thiết kế retry/backoff, timeout và SLO phù hợp.
- Nếu volume mount dùng **phiên bản cụ thể** thay vì latest, cập nhật secret version mới **không tự chuyển** file sang version khác.
- Cần kiểm tra quy tắc **disable/destroy** các versions cũ và khả năng rollback; đừng destroy version duy nhất còn được một revision phục vụ traffic sử dụng.
- Nếu credential nhạy cảm bị lộ, **revocation ở dịch vụ đích** quan trọng hơn chỉ disable Secret Manager version.
- Các revision cũ có thể còn nhận traffic, đặc biệt trong canary; không thu hồi credential cũ trước khi xác minh mọi phiên bản ứng dụng đã chuyển.

## 6. Các loại volume Cloud Run và vòng đời

Cloud Run cho phép mount dữ liệu theo path để ứng dụng đọc/ghi như file, nhưng ngữ nghĩa mỗi loại khác nhau:

| Loại | Dữ liệu ở đâu? | Tính bền vững | Hạn chế cốt lõi |
|---|---|---|---|
| **Secret volume** | Secret Manager | Secret được giữ ngoài instance; file mount là cách đọc | IAM, version, refresh và lỗi đọc runtime |
| **In-memory volume** | RAM của containers trong cùng instance | Mất khi instance dừng | Ghi file tính vào memory limit, dễ OOM |
| **Ephemeral disk** (gen2) | Disk tạm riêng instance | Mất khi instance dừng | Quota/dung lượng/chi phí riêng, không chia sẻ instances |
| **Cloud Storage volume** | Cloud Storage qua **Cloud Storage FUSE** | Object bền vững theo cấu hình bucket | Không POSIX đầy đủ, không file locking, network/API latency |
| **NFS volume** | NFS server/Filestore ngoài Cloud Run | Theo storage backend | VPC networking, no-lock mode, hiệu năng/phí NAS |

Các volume mounts dùng cho **một Cloud Run instance**. Nếu một revision scale từ 1 lên 10 instances, **mỗi instance có RAM/disk tạm riêng**. Nhiều containers (sidecars) **trong cùng instance** có thể chia sẻ một mounted volume nếu cùng được mount; không phải cơ chế dữ liệu chung giữa các instances.

## 7. In-memory volume: dữ liệu tạm cần giới hạn

In-memory volume hữu ích cho thao tác biến đổi nhỏ, file tạm, chia sẻ dữ liệu giữa sidecars của cùng một instance. Ví dụ tạo mount **/mnt/work**:

~~~bash
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --add-volume=mount-path=/mnt/work,type=in-memory,size-limit=256Mi
~~~

Ghi chú:

- **256Mi là giới hạn**, không phải Cloud Run cấp thêm 256 MiB RAM. Bytes ghi tính vào **memory của container ghi**.
- Nếu volume đầy, thao tác ghi thất bại; nếu memory container hết trước, instance có thể crash/OOM.
- Khi không đặt giới hạn, giá trị tự động có thể bằng **một nửa tổng memory** các containers, nhưng vẫn có nguy cơ một container dùng quá memory limit của chính nó.
- File mất khi instance kết thúc, scale in hoặc chuyển revision. Không lưu bản sao duy nhất của dữ liệu quan trọng.

YAML Cloud Run service (chỉ phần template; không tự chạy thay thế toàn service):

~~~yaml
spec:
  template:
    spec:
      containers:
      - image: IMAGE_URL
        volumeMounts:
        - name: scratch
          mountPath: /mnt/work
      volumes:
      - name: scratch
        emptyDir:
          medium: Memory
          sizeLimit: 256Mi
~~~

## 8. Ephemeral disk: file tạm lớn hơn RAM

Cloud Run hiện hỗ trợ **ephemeral disk** ở môi trường **second generation (gen2)**. Disk được provision, định dạng **ext4** và mã hóa riêng cho instance; dữ liệu **mất vĩnh viễn khi instance tắt**, bao gồm crash, scale-in hoặc chuyển traffic sang revision khác.

~~~bash
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --execution-environment=gen2 \
  --add-volume=name=processing-disk,type=ephemeral-disk,size=10Gi \
  --add-volume-mount=volume=processing-disk,mount-path=/mnt/processing
~~~

**Giới hạn theo tài liệu hiện hành:** mỗi disk từ **1Gi đến 100Gi**; mặc định instance có giới hạn tổng **10 GiB**, muốn nhiều hơn phải yêu cầu quota; có giới hạn số volumes và **regional project quota** tính trên nhiều instances. Khả năng triển khai, quotas và giá cần kiểm tra ở project/region thật.

Lựa chọn này hợp lý cho xử lý PDF/video/file trung gian lớn hơn khả năng RAM, nhưng **không** dùng làm persistent disk của Compute Engine. Với bài toán cần giữ output, **upload dần lên Cloud Storage** trong quá trình xử lý thay vì chờ tín hiệu SIGTERM (thời gian dọn dẹp trước SIGKILL rất ngắn).

YAML tương ứng:

~~~yaml
spec:
  template:
    spec:
      containers:
      - image: IMAGE_URL
        volumeMounts:
        - name: processing-disk
          mountPath: /mnt/processing
      volumes:
      - name: processing-disk
        emptyDir:
          medium: Disk
          sizeLimit: 10Gi
~~~

Trước khi áp dụng YAML đầy đủ qua **gcloud run services replace**, phải export cấu hình hiện có, giữ lại identity/network/secrets/traffic settings cần thiết, review diff. Kiểm tra sau thao tác UI rằng **medium: Disk** không bị chuyển nhầm thành **Memory** vì việc đó có thể dẫn tới OOM.

## 9. Cloud Storage volume: object storage dưới dạng đường dẫn file

**Cloud Storage FUSE** cho phép mount bucket như một directory trong container. Dữ liệu thật vẫn nằm trong **Cloud Storage**; mount không biến object storage thành block disk hoặc NFS POSIX.

### 9.1. Cấp quyền tối thiểu và mount read-only

Giả sử bucket **shop-product-images-UNIQUE** tồn tại, chứa ảnh do pipeline xuất bản. Cloud Run runtime chỉ được đọc:

~~~bash
# Thao tác thay đổi IAM trên bucket đã tạo; chỉ trong lab được phép.
gcloud storage buckets add-iam-policy-binding \
  gs://shop-product-images-UNIQUE \
  --member="serviceAccount:orders-runtime@shop-dev-001.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"

# Mount vào service hiện có. Mount cần Cloud Run gen2.
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --execution-environment=gen2 \
  --add-volume=mount-path=/mnt/products,type=cloud-storage,bucket=shop-product-images-UNIQUE,readonly=true
~~~

Ứng dụng đọc **/mnt/products/images/sku-1001.jpg** bằng filesystem API. Bucket phải tồn tại và service identity cần quyền phù hợp. Đối với workflow tạo/cập nhật object, cấp permissions chính xác (Object Creator/User theo nghiệp vụ), không cấp Storage Admin cho toàn project.

### 9.2. Những giới hạn phải tính trước

- Cloud Storage FUSE **không POSIX đầy đủ**; không có cơ chế **file locking** chống nhiều writers cùng ghi một object. Các writers cùng tên có thể gây **last-write-wins** và mất cập nhật.
- Đọc/liệt kê nhiều file nhỏ có độ trễ API/network, không giống disk local. **Metadata cache TTL** và lựa chọn mount options có thể làm thay đổi performance và tính mới của danh sách.
- Khi ghi, Cloud Storage FUSE sử dụng memory cho cache/buffers và đường streaming writes theo cấu hình; **đo memory/throughput thực tế** khi xử lý file lớn. Việc commit object phụ thuộc lifecycle của write/close, không suy rằng byte vừa ghi đã có trên object API.
- Mount được thực hiện **trước khi container startup**; nếu không kết nối được Cloud Storage hoặc mount vượt giới hạn thời gian, instance có thể không khởi động. Tài liệu nêu tối đa khoảng **30 giây** cho quá trình mount.
- Mounted bucket vẫn có **Cloud Storage requests, storage, retrieval/egress** theo mô hình tính phí. Cần kiểm tra bucket location, IAM, lifecycle và data residency.

**Đừng dùng GCS FUSE cho data directory của PostgreSQL/MySQL**, dù ứng dụng có thể mở path và gọi File I/O. Nếu ứng dụng Java xử lý object độc lập và không cần POSIX path, **Google Cloud Storage Java SDK** thường đơn giản và rõ semantics hơn.

### 9.3. Mount chỉ một prefix và cache options

Nếu bucket lớn, có thể dùng mount option **only-dir** để giới hạn phần directory nhìn thấy:

~~~bash
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --add-volume=mount-path=/mnt/products,type=cloud-storage,bucket=shop-product-images-UNIQUE,readonly=true,mount-options="only-dir=images"
~~~

**Chú ý:** chỉ mount một prefix **không tự thu hẹp IAM**. Nếu service account có Object Viewer trên toàn bucket, nó vẫn có thể truy cập object khác qua SDK/API. Muốn cô lập dữ liệu nhạy cảm phải phân quyền ở bucket/managed folder hoặc dùng boundaries phù hợp.

## 10. NFS/Filestore volume: chia sẻ thư mục qua VPC

Khi nhiều containers/instances cần một **cây thư mục dùng chung**, NFS là lựa chọn phù hợp hơn in-memory/ephemeral disk. Trên Google Cloud, **Filestore** cung cấp NFS server managed; Cloud Run cũng có thể dùng NFS server đủ khả năng kết nối khác.

### 10.1. Điều kiện tiên quyết

1. NFS server/Filestore instance đã hoạt động, có **IP và export path** chính xác.
2. Cloud Run service được kết nối đến **VPC** có thể route tới server; có thể dùng **Direct VPC egress** (ưu tiên hiệu năng) hoặc Serverless VPC Access theo môi trường.
3. Firewall, NFS export permissions, client UID/GID và network policy phù hợp. Không mở NFS ra Internet.
4. Cấu hình Cloud Run **gen2** khi tính năng mount yêu cầu, và service/app đã kiểm thử network/latency.

### 10.2. Ví dụ mount share

Giả sử NFS server IP **10.20.10.5** xuất share **/shared**, và VPC connectivity đã được cấu hình:

~~~bash
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --add-volume=mount-path=/mnt/shared,type=nfs,location=10.20.10.5:/shared,readonly=true
~~~

Địa chỉ IP là **ví dụ giả định**, không phải server có thật. Nếu thiếu VPC route, mount có thể timeout hoặc startup fail dù câu lệnh cấu hình Cloud Run được chấp nhận.

### 10.3. NFS có những giới hạn gì trên Cloud Run?

- **Cloud Run không hỗ trợ NFS file locking**; các volumes được mount ở chế độ **no-lock**. Không dùng ứng dụng dựa vào NFS locks để bảo đảm không có concurrent writers.
- NFS shared storage **không thay database transaction**, không tự ngăn hai workers ghi đè cùng một file. Dùng unique filenames, coordination hoặc backend quản lý đồng thời.
- Độ trễ NFS phụ thuộc network, tier Filestore, client connections, kích thước I/O và số Cloud Run instances; cần benchmark.
- Filestore tính phí theo provisioned capacity/tier và có thể có phí network/backup; khác với một thư mục local tạm.
- Nếu NFS backend mất kết nối, workload có thể **hang hoặc lỗi I/O**; thiết kế timeout, health endpoints và khả năng giảm tác động.

**Đừng nhầm kết nối VPC với IAM:** service account Cloud Run có thể cần quyền quản trị cấu hình để deploy, nhưng thao tác file NFS chịu **network access, export rules và filesystem permissions**, không giống từng request Cloud Storage IAM.

## 11. Ví dụ Java: đọc config, secret và dữ liệu tạm an toàn

Đoạn sau minh họa cách ứng dụng **không in secret ra stdout**, kiểm tra file được mount, tạo dữ liệu tạm rồi đặt output tại nơi khác.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public final class CloudRunConfiguration {
    private static final Path SECRET_PATH =
        Path.of("/etc/secrets/db/password");
    private static final Path SCRATCH_DIR =
        Path.of("/mnt/work");

    private CloudRunConfiguration() {}

    public static String profile() {
        return System.getenv().getOrDefault("APP_ENV", "dev");
    }

    // Dùng với secret volume; đọc lại khi ứng dụng thực sự muốn refresh.
    public static String readDbPassword() throws IOException {
        return Files.readString(SECRET_PATH, StandardCharsets.UTF_8);
    }

    public static Path createTempReport(byte[] contents) throws IOException {
        Objects.requireNonNull(contents, "contents");
        Files.createDirectories(SCRATCH_DIR);
        Path report = Files.createTempFile(SCRATCH_DIR, "orders-", ".csv");
        Files.write(report, contents);
        return report;
    }

    public static void main(String[] args) throws Exception {
        String env = profile();
        String password = readDbPassword();
        if (password.isEmpty()) {
            throw new IllegalStateException("Required DB secret is empty");
        }
        // Chỉ log trạng thái, tuyệt đối không log password.
        System.out.println("Config ready for " + env);
    }
}
~~~

**Ghi chú kỹ thuật:**

- Không tự gọi **trim()** trên mật khẩu/token: khoảng trắng đầu/cuối có thể là thành phần hợp lệ. Giữ nguyên dữ liệu, không log plaintext và xử lý encoding đúng hợp đồng của hệ thống đích.
- **String Java** tồn tại trong heap và không bảo đảm xóa ngay; giảm thời gian lưu và không ghi vào logs/exception messages.
- **Files.createTempFile** tạo tên ngẫu nhiên giúp giảm xung đột khi có nhiều requests đồng thời trong cùng instance. Vẫn cần cleanup theo request/job và kiểm soát giới hạn dung lượng.
- Đầu ra quan trọng phải chuyển lên **Cloud Storage hoặc database** bằng SDK/API phù hợp; không trông đợi thư mục **/mnt/work** tiếp tục tồn tại sau scale-in.
- Nếu dùng **env secret**, Java sẽ gọi **System.getenv("DB_PASSWORD")** thay cho file; không dùng cả hai cách nếu không có lý do rõ ràng.

### Rotation với connection pool Java

Nếu dùng HikariCP và secret file latest, việc file đổi **không tự thay connection pool**. Ứng dụng cần thiết kế một trong hai quy trình:

1. **Pin secret version ở env**, triển khai revision mới với version mới, kiểm tra health và chuyển traffic.
2. **Đọc lại file** có kiểm soát, cập nhật cách tạo connections/tái cấu hình pool và xử lý sessions cũ. Kiểm thử credential overlap với database/đối tác.

Với database hỗ trợ **IAM authentication** như một số cấu hình Cloud SQL, cân nhắc dùng tính năng đó để giảm mật khẩu tĩnh. Nhưng IAM của Cloud Run **không tự biến mọi JDBC connection thành kết nối được xác thực**; vẫn phải cấu hình database connector/auth tương ứng.

## 12. Cloud Run services, jobs và multi-container instances

### 12.1. Services khác Jobs

- **Cloud Run service** nhận HTTP requests, chạy nhiều instances/revisions và có traffic splitting.
- **Cloud Run job** chạy tasks đến khi hoàn thành, không phục vụ HTTP traffic và không dùng revision traffic splitting giống service.
- Cả hai có thể dùng env, Secret Manager và các volume types được hỗ trợ, nhưng **gcloud run services** và **gcloud run jobs** là **hai nhóm lệnh riêng**.

Ví dụ tạo job đọc secret qua env:

~~~bash
gcloud run jobs create nightly-report \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/shop-dev-001/jobs/report:1.0.0 \
  --service-account=orders-runtime@shop-dev-001.iam.gserviceaccount.com \
  --set-secrets=DB_PASSWORD=orders-db-password:1
~~~

Chạy job theo lịch/workflow riêng và cấp quyền caller thực thi job; không giả định việc tạo job đồng nghĩa đã chạy hay tự lập lịch.

### 12.2. Sidecar chia sẻ volume, không chia sẻ giữa các instances

~~~mermaid
flowchart TB
    LB["Cloud Run routing"] --> A["Instance A"]
    LB --> B["Instance B"]
    subgraph A1["Instance A: 2 containers"]
      APP1["Java API"] --> MEM1["in-memory volume A"]
      SC1["Sidecar"] --> MEM1
    end
    subgraph B1["Instance B: 2 containers"]
      APP2["Java API"] --> MEM2["in-memory volume B"]
      SC2["Sidecar"] --> MEM2
    end
    A --> A1
    B --> B1
    APP1 --> GCS["Cloud Storage / Filestore nếu cần state chung"]
    APP2 --> GCS
~~~

Nếu định nghĩa volume dùng chung giữa **hai containers của cùng instance**, phải khai báo volume **một lần** rồi mount volume đó trong từng container. Trong mỗi Cloud Run instance, resource limits (memory/disk/CPU) vẫn cần tính tổng và theo từng container.

## 13. An toàn, độ tin cậy và tổng chi phí

### 13.1. Bảo mật theo lớp

| Lớp | Kiểm soát cần có |
|---|---|
| **Source/image** | Không có secrets trong Dockerfile ARG/ENV, source hoặc build logs; scan image |
| **Deployer** | Cloud Run Developer và Service Account User đúng phạm vi; kiểm soát ai sửa revision |
| **Runtime identity** | Service account riêng cho orders-api; Secret Accessor trên một secret, Object Viewer trên bucket đọc |
| **Secret versions** | Pin version cho env, rotation/revocation, không in plaintext trong logs |
| **Volume** | Chỉ mount những thứ container cần; read-only với dữ liệu không cần ghi |
| **Network** | VPC route/firewall cho NFS; HTTPS/TLS cho external APIs; không mở public share |
| **Observability** | Audit IAM/config changes, metrics startup/OOM/I/O và logs đã che dữ liệu nhạy cảm |

### 13.2. Hiệu năng và chi phí

| Lựa chọn | Điều cần quan sát | Rủi ro chi phí |
|---|---|---|
| **Env plain** | Revision rollout, config drift | Không đáng kể, nhưng lỗi config gây downtime |
| **Secret Manager** | Version access errors, API latency, rotation | Active versions, access operations, logging/KMS tùy chọn |
| **In-memory** | Memory usage, OOM, requests đồng thời | Phải provision memory đủ |
| **Ephemeral disk** | GiB/instance, số instances đồng thời, throughput | Provisioned disk, regional quota và thời lượng instance |
| **Cloud Storage FUSE** | Latency p95/p99, operations, cache, egress | Object requests, storage, network và memory |
| **NFS/Filestore** | NFS latency, availability, VPC errors | File share provisioned capacity, network, backups |

**Tăng concurrency Cloud Run** có thể tiết kiệm instances nhưng làm nhiều requests cùng dùng RAM, disk tạm hoặc object mount; phải đo memory/p95 latency và thread-safety của Java. Việc đặt 1Gi disk tạm mỗi instance với **100 instances** đòi hỏi tổng quota/cost khác hẳn 1Gi cho cả service.

## 14. Troubleshooting có hệ thống

| Hiện tượng | Nguyên nhân phổ biến | Kiểm tra đầu tiên |
|---|---|---|
| Revision không khởi động, thiếu secret env | Secret version không tồn tại/disabled hoặc runtime SA thiếu quyền | Secret Manager version, **secretAccessor**, Cloud Run revision logs |
| Deploy secret reference báo 403 | Deployer hoặc **runtime identity** không đủ quyền | Service account cấu hình, secret IAM policy |
| App đã chạy nhưng đọc secret file lỗi | IAM bị thu hồi, version bị disable hoặc path sai | Mounted path, runtime access, Secret Manager audit |
| Secret rotate nhưng env không đổi | Env được resolve ở **instance startup**, không cập nhật in-place | Tạo revision mới pin version; xem traffic split |
| Secret mounted file đổi nhưng JDBC vẫn lỗi | Java không reload connection pool | App credential lifecycle và database auth |
| File ở /etc/secrets bị mất sau mount | Mount **che directory** đã tồn tại | Chọn mount path chuyên dụng |
| Cloud Run startup fail khi GCS mount | FUSE không kết nối bucket / mount timeout / IAM | Bucket, execution gen2, service identity, startup log |
| GCS FUSE ghi chậm hoặc overwrite ngoài ý muốn | Object APIs, không có file lock và write semantics khác POSIX | Dùng SDK, tên object riêng, generation preconditions |
| In-memory volume đầy | size-limit hoặc container memory thấp | Cloud Monitoring memory, quota, dung lượng tạm |
| Ephemeral disk hết quota | Regional allocation hoặc instance disk quota | Disk GiB × max instances, quota, gen2 |
| Thư mục tạm biến mất | Instance bị dừng/scale-in | Dữ liệu quan trọng phải persist ngoài instance |
| NFS mount timeout | Cloud Run chưa vào đúng VPC, route/firewall/export path sai | Direct VPC/connector, IP, NFS server, firewall |
| NFS file writes tranh chấp | NFS không có locking trong Cloud Run | Thiết kế unique filenames hoặc coordination |
| Cloud Run nhận env mới nhưng client vẫn thấy behavior cũ | Revision cũ còn nhận traffic hoặc cache app | Revisions và traffic percentages |
| ImagePull/auth lỗi | Artifact Registry image URL hoặc deploy/pull identity | Runtime error, Artifact Registry IAM, digest |

**Runbook phân loại nhanh:**

1. Xác nhận **project, region, service/job, revision, service identity**.
2. Phân biệt lỗi **deploy**, **cold start**, **runtime read**, **network mount**, **application logic**.
3. Nếu lỗi secret: xác minh **secret resource/version, Secret Accessor ở đúng principal, mount path, IAM policy**, không đọc payload.
4. Nếu lỗi volume: xác minh **type, gen2, mount path, size limit, bucket IAM, VPC route/NFS export**.
5. Nếu chỉ lỗi sau rotation: kiểm tra các **revisions còn traffic**, env cố định, file reload và đối tác đã đổi credential.
6. Rollback revision đã biết tốt nếu cần, ghi nguyên nhân và cập nhật test/alert. **Không tắt bảo mật bằng cách cấp Owner cho runtime**.

## 15. Tình huống tổng hợp: đơn hàng và báo cáo

Hệ thống Java có ba workload:

~~~mermaid
flowchart LR
    CUSTOMER["Client"] --> API["Cloud Run orders-api"]
    API --> SM["Secret Manager<br/>payment credential"]
    API --> DB["Cloud SQL"]
    API --> BUCKET["Cloud Storage<br/>product assets"]
    API --> TMP["In-memory scratch<br/>per instance"]
    JOB["Cloud Run nightly-report job"] --> DISK["Ephemeral disk<br/>temporary output"]
    JOB --> BUCKET
    LEGACY["Legacy document service"] --> NFS["Filestore NFS<br/>shared files"]
~~~

| Workload | Config/secret | Volume | Biện pháp tin cậy |
|---|---|---|---|
| **orders-api** | APP_ENV plain; payment API token từ Secret Manager, pin version | In-memory scratch nhỏ; SDK đọc bucket | Canary revision, kiểm tra secret IAM và p99 latency |
| **nightly-report job** | API config plain, credential qua service identity | Ephemeral disk 10Gi; xuất CSV ra Cloud Storage | Checkpoint incremental, không đợi shutdown mới upload |
| **legacy-documents** | Credential qua Secret Manager mounted file | Filestore NFS hoặc object storage theo semantics | NFS no-lock; tránh concurrent writes cùng file |

**Bài học kiến trúc:** Không lưu duy nhất tài liệu, session hoặc trạng thái thanh toán trong /tmp, in-memory hoặc ephemeral disk. Dữ liệu cần sống qua scale/revision phải ở **database, Cloud Storage, Filestore hoặc hệ thống bền vững phù hợp**.

### Ma trận nghiệm thu tối thiểu

| Test | Kỳ vọng |
|---|---|
| Revision mới pin secret version 2 | Instance mới đọc đúng version được cấu hình |
| Revision cũ còn traffic | Dùng version cũ và vẫn phục vụ khi credential còn hiệu lực |
| Runtime SA thiếu secretAccessor | Test phát hiện lỗi deploy/start/read tùy cơ chế |
| Anonymous principal tìm API secret | Không có quyền Secret Manager |
| In-memory chạm size-limit | App xử lý lỗi, không silently mất đơn hàng |
| Ephemeral disk bị xóa sau scale-in | Output đã được upload durable |
| Object mount với nhiều writers | Dùng unique object names/generation preconditions |
| NFS unavailable | App không treo vô hạn mà có timeout/retry/alert theo thiết kế |
| Dùng Cloud Run gen1 với disk gen2 | Cấu hình bị từ chối/không hợp lệ, test phát hiện |

## 16. Bài tập thực hành và đáp án

### Bài tập A — Chọn biến môi trường hay secret

**Yêu cầu:** Phân loại APP_ENV, LOG_LEVEL, PAYMENT_API_KEY, DB_PASSWORD, PUBLIC_ENDPOINT.

**Đáp án:** APP_ENV, LOG_LEVEL và PUBLIC_ENDPOINT là plain env; PAYMENT_API_KEY và DB_PASSWORD thuộc Secret Manager. Nếu muốn **release reproducible**, pin phiên bản secret cho env; nếu app có cơ chế đọc lại file thì cân nhắc mounted latest.

### Bài tập B — Debug secret rotation

Service đang chạy revision R1 với **DB_PASSWORD=orders-db-password:1**. Tạo secret version 2 và bỏ phiên bản 1 ngay, nhưng không đổi revision.

**Hỏi:** Tác động gì? **Đáp án:** R1 vẫn tham chiếu version 1; instances đang chạy có env cũ, còn cold starts/restarts có thể thất bại nếu version 1 bị disable. Cần tạo revision R2 pin version 2, chuyển traffic và kiểm thử trước khi thu hồi version 1.

### Bài tập C — Tính chuyện chia sẻ file

Một service có **3 Cloud Run instances**, mỗi instance có in-memory volume **256Mi**. Hai containers trong instance A mount cùng volume.

**Hỏi:** Có bao nhiêu bản volume? Container trong instance B thấy file của A không? **Đáp án:** Có **một volume tạm trên mỗi instance**, tức ba bản độc lập; sidecars trong A cùng xem volume A, B không thấy nội dung A. Chọn backend bền vững nếu cần state chung.

### Bài tập D — Chọn NFS hay GCS mount

Hai workers cần ghi cùng một file và dựa vào **file lock** để bảo đảm thứ tự. Nhóm định dùng NFS trên Cloud Run hoặc GCS FUSE.

**Hỏi:** Có an toàn không? **Đáp án:** Không mặc nhiên. Cloud Run NFS dùng **no-lock**, GCS FUSE không có file locking; phải thay giao thức phối hợp ghi, dùng unique filenames, queue/database coordination hoặc chọn môi trường/storage hỗ trợ đúng semantics.

### Bài tập E — Thiết kế 20Gi file tạm

Job xử lý video cần 20Gi scratch, dữ liệu có thể dựng lại; máy chỉ provision 2Gi memory. Chọn loại volume và giải thích.

**Đáp án:** Cân nhắc **ephemeral disk** trên gen2, nhưng phải kiểm tra default **10Gi instance limit**, regional quota và xin tăng giới hạn trước khi chọn 20Gi. Không chọn in-memory 20Gi khi không đủ RAM; upload output vào Cloud Storage trước khi task kết thúc.

### Bài tập F — Kiểm tra IAM

orders-runtime được cấp **roles/secretmanager.secretAccessor ở project**, và **roles/storage.admin** trên toàn project, trong khi app chỉ đọc một secret và một bucket.

**Yêu cầu:** Thu hẹp quyền. **Đáp án:** Chuyển secretAccessor xuống **secret cụ thể**, Object Viewer xuống **bucket cần đọc**; kiểm tra inherited roles/organization policy, không dùng static service account key.

### Bài tập G — Thực hành gcloud trên lab

Hãy chuẩn bị runbook (không cần chạy trên production):

1. Tạo Secret Manager secret và một test version không nhạy cảm.
2. Cấp secretAccessor cho runtime service account.
3. Deploy Cloud Run revision dùng **--update-secrets** với env pin version.
4. Tạo revision khác dùng secret file **latest**.
5. Gắn in-memory volume 128Mi, kiểm tra file tạm mất khi instance bị thay.
6. Mount Cloud Storage bucket **read-only** và xác minh IAM.
7. Giám sát 403, startup failures, memory và logs; thực hiện rollback.

**Tiêu chí đạt:** không in hoặc commit secret, không dùng --set-secrets làm mất các references khác, ghi lại revision và trạng thái traffic, kiểm thử identity không được phép.

## 17. Tổng kết và tài liệu tham khảo

**Sáu nguyên tắc cốt lõi:**

1. **Env** phù hợp cấu hình không bí mật, gắn với revision; **PORT** do Cloud Run cấp, không tự đặt.
2. **Secret Manager** lưu bí mật. Env secret được lấy khi instance khởi động; mounted secret được đọc khi file được truy cập. Rotation phải tính cả ứng dụng, dịch vụ đích và các revisions còn traffic.
3. **Runtime service identity** cần IAM tối thiểu trên secret/bucket; deployer, rotator và runtime là các vai trò khác nhau.
4. **In-memory và ephemeral disk** đều chỉ tồn tại trong một instance; không dùng làm nguồn dữ liệu bền vững.
5. **Cloud Storage FUSE** là object storage giả lập đường dẫn file, **không POSIX đầy đủ**; **NFS/Filestore** cung cấp file share nhưng Cloud Run NFS **không hỗ trợ locking**.
6. Luôn kiểm tra **gen2, IAM, VPC, quota, concurrency, revision traffic, startup/latency và chi phí** trước khi áp dụng cho production.

**Tài liệu Google Cloud chính thức:**

1. [Configure environment variables for Cloud Run services](https://docs.cloud.google.com/run/docs/configuring/services/environment-variables) — env flags, reserved variables, revision behavior.
2. [Configure secrets for Cloud Run services](https://docs.cloud.google.com/run/docs/configuring/services/secrets) — Secret Manager env/volume, quyền, rotation và limits.
3. [Configure secrets for Cloud Run jobs](https://docs.cloud.google.com/run/docs/configuring/jobs/secrets) — cấu hình secret cho job.
4. [Configure in-memory volume mounts](https://docs.cloud.google.com/run/docs/configuring/services/in-memory-volume-mounts) — memory limits và sharing giữa containers.
5. [Configure an ephemeral disk for Cloud Run services](https://docs.cloud.google.com/run/docs/configuring/services/ephemeral-disk) — gen2, disk quotas, temporary storage.
6. [Configure Cloud Storage volume mounts](https://docs.cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts) — FUSE, concurrency, IAM, performance và mount options.
7. [Configure NFS volume mounts](https://docs.cloud.google.com/run/docs/configuring/services/nfs-volume-mounts) — Filestore/VPC/no-lock.
8. [Cloud Run service identity](https://docs.cloud.google.com/run/docs/securing/service-identity) — ADC, IAM và runtime service account.
9. [Secret Manager best practices](https://docs.cloud.google.com/secret-manager/docs/best-practices) — version pinning, rotation và bảo vệ dữ liệu.
10. [Cloud Storage FUSE overview](https://docs.cloud.google.com/storage/docs/cloud-storage-fuse/overview) — object vs filesystem semantics.
