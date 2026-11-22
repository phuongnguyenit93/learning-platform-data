# IAM, mã hóa và message storage policies trong Google Cloud Pub/Sub

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt quyền của **publisher**, **subscriber**, người quản trị Pub/Sub và **Pub/Sub service agent**; cấp IAM ở đúng topic, subscription hoặc Cloud KMS key.
2. Giải thích mã hóa mặc định, **TLS**, **customer-managed encryption key (CMEK)** và cách Pub/Sub sử dụng **envelope encryption**.
3. Cấu hình **message storage policy** theo danh sách vùng lưu trữ được phép, phân biệt với **enforceInTransit** và **regional endpoint**.
4. Hiểu tác động của policy/KMS khi đổi region, rotate key, deploy Cloud Run/GKE, phân quyền liên project và xử lý lỗi **PERMISSION_DENIED** hoặc **FAILED_PRECONDITION**.
5. Thực hành **gcloud**, ví dụ **Java Publisher** dùng Application Default Credentials (ADC), giám sát dữ liệu theo region, thiết kế rollback và bài tập.

## 1. Bài toán: hệ thống đơn hàng cần kiểm soát ai, khóa nào và dữ liệu ở đâu

Một hệ thống Java/Spring Boot chạy trên **Cloud Run** xuất bản sự kiện **order.created** tới Pub/Sub; **GKE worker** xử lý đơn hàng, sau đó lưu dữ liệu tại Cloud SQL và Cloud Storage. Bộ phận bảo mật đưa ra ba yêu cầu:

- Chỉ service account của **orders-api** được **publish** lên topic; chỉ worker chuyên trách được **consume** subscription.
- Thông điệp được mã hóa; với dữ liệu nhạy cảm, doanh nghiệp cần quản lý vòng đời khóa bằng **Cloud KMS**.
- Nội dung thông điệp phải được lưu tại **asia-southeast1**; trong môi trường quản lý nghiêm ngặt, cả request publish/pull cũng phải được xử lý tại region được phép.

~~~mermaid
flowchart LR
  API["Cloud Run orders-api<br/>Publisher identity"] -->|"Publish"| TOPIC["Pub/Sub topic<br/>orders-events"]
  TOPIC -->|"Fan-out"| SUB["Subscription<br/>orders-worker-sub"]
  SUB -->|"Pull + Ack"| WORK["GKE Java worker<br/>Subscriber identity"]
  KMS["Cloud KMS<br/>CMEK key"] -. "Service agent encrypt/decrypt" .-> TOPIC
  POLICY["Topic message storage policy<br/>allowedPersistenceRegions"] -. "Residency" .-> TOPIC
  IAM["IAM at topic/subscription"] -. "Who can publish/consume" .-> TOPIC
  IAM -. "Who can consume" .-> SUB
~~~

Trong mô-đun **CLOUD_PROVIDERS_GCP**, bài này nối project/IAM/VPC với Cloud Run, GKE, Cloud Storage, database, bảo mật phát hành và theo dõi độ tin cậy/chi phí. Ba cơ chế **IAM**, **encryption** và **message storage policy** bổ sung nhau, không thay thế nhau.

| Cơ chế | Câu hỏi được giải quyết | Không giải quyết |
|---|---|---|
| **IAM** | Principal nào được publish, consume, cấu hình topic/subscription? | Vị trí lưu message, bảo mật nội dung sau khi app đọc |
| **Encryption / CMEK** | Message được bảo vệ bằng khóa nào khi lưu? Ai kiểm soát KMS key? | Quyền publish/subscribe, giới hạn vị trí xử lý |
| **Message storage policy** | Nội dung message được lưu/xử lý ở các Google Cloud regions nào? | IAM của publisher, nhãn/tên tài nguyên, thời gian retention |
| **enforceInTransit** | Có từ chối Publish/Pull khi xử lý tại vùng không cho phép không? | Xác thực user, chống replay, mã hóa payload do ứng dụng tự thực hiện |

## 2. Nhắc lại mô hình Pub/Sub và điểm áp quyền

**Topic** là nơi producer xuất bản thông điệp. **Subscription** là đối tượng tiêu thụ message từ topic; nhiều subscription cùng topic được nhận bản sao logic riêng và có backlog/acknowledgment riêng. **Ack** xác nhận xử lý thành công để Pub/Sub không tiếp tục phân phối message đó theo cơ chế giao hàng tương ứng.

~~~text
projects/shop-dev-001/topics/orders-events
    |
    +-- projects/shop-dev-001/subscriptions/orders-worker-sub
    +-- projects/shop-dev-001/subscriptions/orders-audit-sub
~~~

Các tên là dữ liệu minh họa, chưa được tạo. Cấu hình **message storage policy và CMEK** đặt ở **topic**. **Publisher IAM** thường cấp trên **topic**; **Subscriber IAM** thường cấp trên **subscription**. **Subscription retention** và **topic message retention** là cấu hình khác với **message storage region**.

### 2.1. Những danh tính cần tách

| Principal | Vai trò đúng | Phạm vi đề xuất |
|---|---|---|
| **orders-publisher@...** | Gửi sự kiện từ Cloud Run | **roles/pubsub.publisher** tại topic orders-events |
| **orders-subscriber@...** | Pull/Ack từ GKE hoặc Cloud Run worker | **roles/pubsub.subscriber** tại subscription orders-worker-sub |
| **Platform operator** | Tạo/sửa topic, subscription và policy | Pub/Sub Editor/Admin ở phạm vi được phê duyệt |
| **Pub/Sub service agent** | Pub/Sub dùng Cloud KMS để mã hóa/giải mã | **roles/cloudkms.cryptoKeyEncrypterDecrypter** tại CryptoKey |
| **KMS administrator** | Tạo, rotate, disable, quản trị IAM của key | Vai trò Cloud KMS phù hợp; tách khỏi runtime |
| **Push subscription service agent / delivery identity** | Phát hành token cho authenticated push | Quyền token creator và gọi endpoint đúng cách |

**KSA** của GKE, **Cloud Run runtime service account**, **Pub/Sub service agent** và **node service account** là các danh tính khác nhau. Không cấp tất cả các vai trò trên cho một principal chỉ để sửa lỗi 403.

## 3. IAM của Pub/Sub: đúng vai trò, đúng resource

### 3.1. Những role cần nhớ

| Predefined role | Tác vụ chính | Quyền tiêu biểu |
|---|---|---|
| **roles/pubsub.publisher** | Publish tới topic | **pubsub.topics.publish** |
| **roles/pubsub.subscriber** | Consume/Ack subscription; cũng có quyền attach subscription theo role definition | **pubsub.subscriptions.consume**, **pubsub.topics.attachSubscription** |
| **roles/pubsub.viewer** | Xem cấu hình topic, subscription, schema | Get/List theo phạm vi |
| **roles/pubsub.editor** | Quản lý nhiều tài nguyên Pub/Sub | Rộng hơn Reader/Publisher/Subscriber |
| **roles/pubsub.admin** | Toàn quyền quản trị Pub/Sub theo phạm vi IAM | Có thể thay/xóa resources; không cấp cho app runtime |

**roles/pubsub.subscriber** có quyền rộng hơn chỉ pull một subscription vì role bao gồm **attachSubscription** tại topic theo phân quyền. Thực tế nên cấp role này trực tiếp cho **subscription**; nếu cần hạn chế sâu hơn, cân nhắc custom role với các permissions tối thiểu được Google hỗ trợ.

### 3.2. Resource-level IAM và project-level IAM

Với Pub/Sub, IAM binding ở **topic** hoặc **subscription** thường an toàn hơn role ở **project**, vì giới hạn phạm vi của một ứng dụng.

~~~bash
# Đây là thay đổi IAM, chỉ chạy trong project lab được phép.
gcloud pubsub topics add-iam-policy-binding orders-events \
  --project=shop-dev-001 \
  --member="serviceAccount:orders-publisher@shop-dev-001.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"

gcloud pubsub subscriptions add-iam-policy-binding orders-worker-sub \
  --project=shop-dev-001 \
  --member="serviceAccount:orders-subscriber@shop-dev-001.iam.gserviceaccount.com" \
  --role="roles/pubsub.subscriber"
~~~

Kiểm tra IAM policies không tiết lộ payload:

~~~bash
gcloud pubsub topics get-iam-policy orders-events \
  --project=shop-dev-001

gcloud pubsub subscriptions get-iam-policy orders-worker-sub \
  --project=shop-dev-001
~~~

**Đánh giá quyền hiệu lực**, không chỉ nhìn binding tại một tài nguyên: principal có thể được quyền thông qua group, project, folder, organization hoặc custom role. Nếu subscriber vẫn đọc được sau khi gỡ role ở subscription, kiểm tra quyền kế thừa ở các cấp cao hơn.

### 3.3. Tạo subscription và lỗi attachSubscription

Để **tạo subscription liên kết với topic**, creator có thể cần:

- **pubsub.subscriptions.create** tại project sở hữu subscription.
- **pubsub.topics.attachSubscription** trên topic nguồn.

Nếu topic và subscription thuộc **hai projects khác nhau**, phải kiểm tra IAM ở **cả hai nơi**. Cấp subscriber role để pull một subscription **không nhất thiết** đủ cho việc tạo subscription mới.

### 3.4. Runtime identity: ADC thay khóa JSON

- **Cloud Run:** cấu hình một runtime service account có role Publisher tại topic. Google Cloud Pub/Sub Java client tìm credentials qua **Application Default Credentials**.
- **GKE:** dùng **Workload Identity Federation for GKE** gắn IAM cho Kubernetes ServiceAccount hoặc impersonation khi cần; tránh service account JSON key trong Secret/ConfigMap.
- **CI/CD ngoài GCP:** ưu tiên **Workload Identity Federation**, không commit long-lived keys vào repository.
- **Compute Engine:** cần service account và scopes/IAM thích hợp; xác nhận principal thực sự dùng khi gọi Pub/Sub.

**Không nhầm ID token dành cho HTTP push endpoint với OAuth access token/ADC mà publisher hoặc pull subscriber dùng gọi Pub/Sub API.**

### 3.5. Authenticated push: hai lớp IAM

Nếu subscription **push** tới Cloud Run private endpoint:

1. Pub/Sub cấu hình **push authentication service account**.
2. Người tạo/cập nhật subscription cần quyền **iam.serviceAccounts.actAs** trên service account này.
3. **Pub/Sub service agent** cần khả năng tạo OIDC token (**roles/iam.serviceAccountTokenCreator**) cho push identity theo hướng dẫn.
4. Push identity cần quyền **roles/run.invoker** trên Cloud Run service đích.
5. Cloud Run xác minh token **audience/issuer** đúng cấu hình; không coi một HTTP 200 không xác thực là thiết kế an toàn.

Nhóm quyền **publish/consume Pub/Sub** khác nhóm quyền **gọi Cloud Run HTTP endpoint**. Trong lab Pull ở dưới, chưa cần thiết lập push authentication.

## 4. Mã hóa: Google default encryption, TLS và CMEK

### 4.1. Mặc định đã được mã hóa khi lưu

Pub/Sub mặc định mã hóa nội dung khách hàng **at rest** bằng khóa do Google quản lý. Truyền dữ liệu qua APIs dùng kênh được bảo vệ bằng **TLS**. Doanh nghiệp không cần bật CMEK chỉ để có encryption cơ bản.

**CMEK** cho phép doanh nghiệp kiểm soát **key encryption key (KEK)** trong Cloud KMS, cấu hình quyền, rotation, key location, auditing hoặc HSM/Autokey theo yêu cầu.

| Cách | Ai quản lý KEK? | Giá trị | Đánh đổi |
|---|---|---|---|
| **Google default encryption** | Google Cloud | Ít vận hành, không phải quản trị key | Ít quyền điều khiển lifecycle key |
| **Pub/Sub + Cloud KMS CMEK** | Chủ sở hữu key trong Cloud KMS | IAM/key rotation, audit và khả năng thu hồi | Thêm KMS permissions, quota/chi phí, rủi ro gián đoạn khi key không truy cập được |
| **Application-level encryption trước publish** | Ứng dụng/doanh nghiệp | Bảo vệ payload theo trust boundary riêng | Khó search/transform, cần quản lý key và decrypt ở subscriber; **khác CMEK** |

### 4.2. Envelope encryption không phải KMS mã hóa từng payload

~~~mermaid
flowchart LR
  MSG["Message data"] --> DEK["Pub/Sub dùng DEK<br/>mã hóa dữ liệu"]
  KMS["Cloud KMS CMEK (KEK)"] --> WRAP["Wrap/unwrap DEK"]
  DEK --> STORE["Lưu message encrypted"]
  WRAP --> STORE
  STORE --> READ["Pub/Sub giải mã trước khi deliver"]
  READ --> SUB["Subscriber có quyền IAM"]
~~~

Pub/Sub dùng **data encryption keys (DEKs)** cho message, còn **Cloud KMS CMEK** dùng để wrap/unwrap DEKs. Theo tài liệu, Pub/Sub tạo DEK mới cho topic khoảng **6 giờ một lần**. Vì vậy số KMS operations **không bằng số messages**; mỗi message cũng không tạo một Cloud KMS encrypt call độc lập.

**Giới hạn quan trọng:** message **attributes** không được mã hóa ở **application layer** của Pub/Sub như payload, dù vẫn được mã hóa ở các lớp hạ tầng/hardware. Không đặt API key, số thẻ, JWT hoặc PII nhạy cảm vào message attributes, topic ID, subscription ID, labels hay logs.

### 4.3. CMEK không mã hóa dữ liệu sau khi subscriber đã đọc

Khi subscriber pull/nhận push, Pub/Sub giải mã để phân phối nội dung cho client có quyền. Sau đó ứng dụng vẫn phải bảo vệ:

- Java logs/exception traces, dead-letter processing và message retries.
- Connection đến Cloud SQL/API khác, object lưu vào Cloud Storage.
- Dữ liệu trong heap, disk, snapshot, file export hoặc sao lưu.
- Những principals được IAM cấp quyền tiêu thụ nội dung.

**CMEK không thay thế IAM, TLS, kiểm soát schema/payload, data masking hoặc bảo mật trong ứng dụng.**

## 5. Thực hành A — Cấp Pub/Sub IAM đúng phạm vi

### 5.1. Tiền đề và môi trường

Tất cả tên minh họa thuộc project **shop-dev-001**, không phải tài nguyên đã tồn tại. Giả sử đã bật **Pub/Sub API**, có billing/quota và quyền quản trị theo quy trình lab. Không dùng production để thử đổi IAM hoặc thu hồi quyền.

~~~bash
gcloud auth list
gcloud config get-value project
gcloud services list --enabled --project=shop-dev-001

# Nếu project lab chưa bật API, thao tác cần quyền quản trị:
gcloud services enable pubsub.googleapis.com \
  --project=shop-dev-001

# Tạo topic và pull subscription chỉ cho bài thực hành.
gcloud pubsub topics create orders-events \
  --project=shop-dev-001

gcloud pubsub subscriptions create orders-worker-sub \
  --project=shop-dev-001 \
  --topic=orders-events
~~~

### 5.2. Tạo hai danh tính không chia sẻ role

~~~bash
gcloud iam service-accounts create orders-publisher \
  --project=shop-dev-001 \
  --display-name="Publisher for orders-events"

gcloud iam service-accounts create orders-subscriber \
  --project=shop-dev-001 \
  --display-name="Subscriber for orders-worker-sub"
~~~

Sau đó cấp **Publisher** cho topic và **Subscriber** cho subscription bằng các lệnh ở mục 3.2. Xem lại IAM policies; principal vận hành cần quyền đọc IAM policy và runtime identity cần role đúng.

### 5.3. Kiểm thử bằng CLI với principal phù hợp

~~~bash
# Người chạy phải có pubsub.topics.publish trên topic.
gcloud pubsub topics publish orders-events \
  --project=shop-dev-001 \
  --message='{"eventId":"lab-001","type":"order.created"}' \
  --attribute=event_type=order.created

# Người chạy phải có pubsub.subscriptions.consume trên subscription.
gcloud pubsub subscriptions pull orders-worker-sub \
  --project=shop-dev-001 \
  --limit=5 \
  --auto-ack
~~~

Lệnh ví dụ dùng **principal đang đăng nhập gcloud**. Nó **không tự động dùng** hai service accounts vừa tạo. Để kiểm thử quyền bằng danh tính riêng, dùng **--impersonate-service-account** khi người thao tác có quyền impersonate, hoặc chạy từ đúng Cloud Run/GKE runtime identity.

**Chỉ sử dụng --auto-ack để kiểm thử**: trong ứng dụng thật, chỉ ack **sau khi đã xử lý và lưu kết quả bền vững**; lỗi tạm thời nên nack/retry. Không dùng câu lệnh pull trên subscription production nếu việc ack có thể làm mất thông điệp chưa xử lý.

### 5.4. Test âm tính

Trong môi trường test, xác minh:

1. Publisher **không** pull được subscription khi không có Subscriber role.
2. Subscriber **không** publish được topic khi không có Publisher role.
3. Một service account thứ ba không có role **không** thực hiện được cả hai.
4. Thêm role tại resource cần thiết rồi thử lại; **không cấp Editor/Owner** để bỏ qua lỗi.

Nếu test âm tính vẫn thành công, xem quyền kế thừa hoặc danh tính gcloud/ADC thật đang được dùng.

## 6. Thực hành B — Tạo Cloud KMS CMEK cho topic

### 6.1. Chọn vị trí khóa đúng với kiến trúc

Do Pub/Sub là dịch vụ toàn cầu, Google Cloud **khuyến nghị CMEK ở location global** để tránh phụ thuộc chéo region không cần thiết. Chỉ cân nhắc **regional key** khi:

- Message storage policy chỉ cho phép **một region** và đã bật **enforceInTransit**.
- **Tất cả publisher và subscriber** sử dụng cùng **regional endpoint** tại region đó.

Không tự giả định topic giới hạn ở một region thì regional KMS key luôn tốt hơn; cần kiểm tra quyền, độ sẵn sàng, độ trễ và ràng buộc residency trước khi dùng. Ví dụ dưới chọn **global KMS key** cho môi trường lab.

### 6.2. Tạo key ring và symmetric CryptoKey

~~~bash
gcloud services enable cloudkms.googleapis.com \
  --project=shop-dev-001

gcloud kms keyrings create pubsub-ring \
  --project=shop-dev-001 \
  --location=global

gcloud kms keys create orders-messages-key \
  --project=shop-dev-001 \
  --location=global \
  --keyring=pubsub-ring \
  --purpose=encryption \
  --rotation-period=90d \
  --next-rotation-time=2027-03-01T00:00:00Z
~~~

**Ngày rotation trong lệnh chỉ để minh họa và cần phù hợp với ngày thực hiện lab**; nếu đã qua thời điểm hoặc trái policy của tổ chức, thay bằng lịch hợp lệ. Không tạo key trùng tên nếu đã tồn tại. **Key ring và CryptoKey không thể xóa trực tiếp** theo cách xóa topic; thiết kế tên/region và IAM trước khi tạo tài nguyên KMS.

### 6.3. Cấp quyền cho Pub/Sub service agent, không phải publisher

Pub/Sub service agent của project có dạng:

~~~text
service-PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com
~~~

Lấy **project number thật**:

~~~bash
gcloud projects describe shop-dev-001 \
  --format="value(projectNumber)"
~~~

Giả sử project number là **123456789012**:

~~~bash
gcloud kms keys add-iam-policy-binding orders-messages-key \
  --project=shop-dev-001 \
  --location=global \
  --keyring=pubsub-ring \
  --member="serviceAccount:service-123456789012@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/cloudkms.cryptoKeyEncrypterDecrypter"
~~~

Thay số thật trước khi chạy. **Không cấp KMS Encrypter/Decrypter cho publisher và subscriber** chỉ vì chúng dùng topic CMEK. Publisher/Subscriber chỉ cần Pub/Sub IAM; **dịch vụ Pub/Sub** thực hiện mã hóa/giải mã với key.

Nếu dùng KMS key ở project **security-kms-001** và topic ở **shop-dev-001**, phải cấp quyền KMS trên key thuộc **security-kms-001** cho **Pub/Sub service agent của project sở hữu topic**, không phải cho một service agent ngẫu nhiên ở KMS project.

### 6.4. Tạo topic CMEK

Tạo một topic lab riêng để không tác động topic đã có dữ liệu:

~~~bash
gcloud pubsub topics create orders-secure \
  --project=shop-dev-001 \
  --topic-encryption-key=projects/shop-dev-001/locations/global/keyRings/pubsub-ring/cryptoKeys/orders-messages-key

gcloud pubsub topics describe orders-secure \
  --project=shop-dev-001
~~~

Xác minh trường **kmsKeyName** trỏ đúng CryptoKey. Nếu chưa tạo Pub/Sub service agent, cần kích hoạt/tạo service identity theo hướng dẫn chính thức rồi grant IAM trước khi thử topic. Không gỡ hoặc thay IAM key khi một subscription production còn backlog.

### 6.5. Thay đổi key không mã hóa lại quá khứ

Pub/Sub cho phép cập nhật key liên kết với topic, nhưng:

- **Thay KMS key trên topic** chỉ ảnh hưởng những messages được publish sau khi cấu hình mới có hiệu lực. Pub/Sub có cache key và có thể mất khoảng **30 phút** để nhận cấu hình key mới.
- **Rotate CryptoKey version trong Cloud KMS** không làm topic dùng ngay key version mới; theo tài liệu Pub/Sub có thể cần **tới 12 giờ** để dùng version mới bảo vệ các DEKs tiếp theo.
- **Messages cũ vẫn phụ thuộc key/key version cũ** theo retention; thời gian có thể tới **31 ngày**. Không disable/destroy phiên bản khóa cũ ngay chỉ vì topic đã chuyển sang khóa mới.

**Runbook rotation:** kiểm tra sử dụng/retention → tạo/rotate key mới → quan sát publish/delivery và Cloud KMS logs → bảo đảm backlog cũ đã hết hoặc retention kết thúc → mới cân nhắc disable theo change control; đánh giá tác động tới subscription replay/snapshot.

### 6.6. KMS lỗi là rủi ro availability

Nếu key bị disable, key IAM bị thu hồi hoặc KMS không thể phục vụ, **publish/pull có thể trả FAILED_PRECONDITION** và push delivery có thể dừng. Không sửa bằng cách tắt CMEK mà chưa điều tra: có thể còn dữ liệu encrypted bằng key cũ.

Thực hành **không cần và không nên thử disable key** của hệ thống dùng chung. Thay vào đó, mô phỏng trên sơ đồ/runbook và kiểm tra KMS IAM policy, key versions, Cloud Audit Logs, backlog metrics.

## 7. Message storage policy: dữ liệu thông điệp được lưu ở đâu?

Pub/Sub topic có **messageStoragePolicy**, gồm:

~~~json
{
  "messageStoragePolicy": {
    "allowedPersistenceRegions": ["asia-southeast1"],
    "enforceInTransit": false
  }
}
~~~

**allowedPersistenceRegions** là **danh sách region IDs** (ví dụ **asia-southeast1**, **asia-east1**), không phải zones hoặc tên multi-region như **asia**. Phải có ít nhất một region và tuân thủ **Resource Location Restriction organization policy** có hiệu lực.

Khi publisher ở nơi khác nhưng **enforceInTransit=false**, Pub/Sub có thể tiếp nhận yêu cầu rồi chuyển dữ liệu vào một region được phép để lưu. Vì thế **publisher ở ngoài danh sách không tự động bị từ chối**, và có thể có độ trễ hoặc lưu lượng đi qua network regions khác trước khi lưu.

### 7.1. Giới hạn phạm vi của storage policy

Policy áp dụng với **nội dung thông điệp** được lưu/xử lý, **không áp đặt residency cho tên topic, labels hoặc IAM settings**. Nó không tạo bucket storage riêng, không biến topic thành dịch vụ chỉ hoạt động trong một region, và không tự động kiểm soát residency của dữ liệu backend khi subscriber ghi vào Cloud SQL/Cloud Storage.

### 7.2. Nếu không khai báo policy

- Topic mới sẽ nhận message storage policy dựa trên **Resource Location Restriction** của tổ chức nếu có.
- Khi không có policy tổ chức giới hạn location, **mọi regions** được phép.
- **enforceInTransit** mặc định cũng có thể chịu **organization policy** tương ứng; không giả định mặc định false trong mọi tổ chức.
- Thay đổi organization policy **không tự cập nhật tất cả topics đã tồn tại**; cần chủ động đồng bộ hoặc kiểm tra từng topic.

### 7.3. Policy thay đổi không di chuyển message cũ

Giả sử topic trước đây được lưu ở **asia-east1**, nay chỉ cho phép **asia-southeast1**. Việc đổi **allowedPersistenceRegions**:

1. Áp cho **messages mới** sau thời điểm cập nhật.
2. **Không** di chuyển/re-encrypt messages đã publish theo chính sách cũ.
3. Không bảo đảm dữ liệu cũ biến mất khỏi region cũ ngay; backlog/retention/snapshots cần được kiểm kê.

Với yêu cầu compliance bắt buộc residency chặt, **thiết kế topic/policy đúng từ đầu**, đánh giá lịch sử dữ liệu trước khi tuyên bố đã chuyển vùng hoàn tất.

## 8. enforceInTransit: thêm giới hạn xử lý request

Đặt **enforceInTransit=true** để bắt Pub/Sub không chỉ lưu nội dung ở vùng cho phép mà còn chỉ xử lý **Publish, Pull, StreamingPull và push delivery** trong các vùng đó.

| Trường hợp | false / không bật | true |
|---|---|---|
| Publisher ở region được phép | Có thể thành công nếu IAM/quota hợp lệ | Có thể thành công |
| Publisher request được xử lý ở region ngoài danh sách | Có thể tiếp nhận rồi route message để lưu ở region được phép | **FAILED_PRECONDITION** |
| Subscriber Pull/StreamingPull từ vùng không cho phép | Có thể truy cập nếu IAM và hệ thống đáp ứng | **FAILED_PRECONDITION** |
| Push subscription | Có thể xử lý theo routing thông thường | Chỉ xử lý giao hàng tại vùng cho phép; giới hạn quá chặt có thể làm **dừng giao hàng** |
| Client ngoài Google Cloud dùng global endpoint | Có thể đi qua vùng gần client rồi lưu dữ liệu ở vùng được phép | Dễ bị route vào vùng không được phép và bị từ chối; dùng **regional endpoint** |

**FAILED_PRECONDITION khác PERMISSION_DENIED:** lỗi đầu thường là trạng thái chính sách/vùng/KMS, còn lỗi sau thường liên quan IAM hoặc cơ chế truy cập khác. Chẩn đoán nguyên nhân bằng response code và logs.

### 8.1. Ba loại Pub/Sub endpoint

| Endpoint | Ví dụ | Bảo đảm |
|---|---|---|
| **Global** | pubsub.googleapis.com | Định tuyến gần nơi client đi vào Google Cloud; **không khóa cứng vùng xử lý** |
| **Regional** | pubsub.asia-southeast1.rep.googleapis.com | Yêu cầu được xử lý tại region xác định; **không tự reroute sang region khác** |
| **Locational** | Theo mẫu location cụ thể trong Pub/Sub docs | Thường vào location chỉ định nhưng **không bảo đảm mạnh bằng regional endpoint** |

Với **enforceInTransit=true** và yêu cầu dữ liệu chỉ ở **asia-southeast1**, **khuyến nghị regional endpoint** cùng region cho cả publisher và pull subscriber. Nếu service Java chạy ở US hoặc ngoài GCP nhưng vẫn dùng global endpoint, request có thể vào một region không được phép rồi thất bại.

**Ghi nhớ:** regional endpoint cũng là đánh đổi tính sẵn sàng: khi region đó gián đoạn, requests **không tự động failover sang vùng khác**. Với ứng dụng đa region cần design một danh sách allowed regions và chiến lược chuyển endpoint được phê duyệt, không chỉ bật một checkbox.

## 9. Thực hành C — Tạo topic với storage policy và in-transit enforcement

### 9.1. Một region, không enforce transit

~~~bash
gcloud pubsub topics create orders-resident \
  --project=shop-dev-001 \
  --message-storage-policy-allowed-regions=asia-southeast1

gcloud pubsub topics describe orders-resident \
  --project=shop-dev-001 \
  --format="yaml(name,messageStoragePolicy)"
~~~

**Không được kết luận tất cả request xử lý ở asia-southeast1** từ policy này: chỉ **được phép lưu nội dung message** ở region đã chọn. Để đảm bảo processing location trong Pub/Sub, cần thêm enforceInTransit và dùng endpoints phù hợp.

### 9.2. Kích hoạt enforce trong lab

~~~bash
gcloud pubsub topics update orders-resident \
  --project=shop-dev-001 \
  --message-storage-policy-allowed-regions=asia-southeast1 \
  --message-storage-policy-enforce-in-transit

gcloud pubsub topics describe orders-resident \
  --project=shop-dev-001 \
  --format="yaml(name,messageStoragePolicy)"
~~~

**Cảnh báo:** các flags của **MessageStoragePolicy** trên lệnh **update** phải được chỉ định cùng nhau. Nếu bỏ **--message-storage-policy-enforce-in-transit** khi sửa danh sách regions, thuộc tính omitted có thể trở về mặc định và **tắt enforcement ngoài ý muốn**. Không coi update chỉ thêm một flag là thao tác “sửa từng field” trừ khi CLI docs nói rõ.

### 9.3. Nhiều allowed regions và tính sẵn sàng

Ví dụ hệ thống cho phép **asia-southeast1** và **asia-east1**:

~~~bash
gcloud pubsub topics update orders-resident \
  --project=shop-dev-001 \
  --message-storage-policy-allowed-regions=asia-southeast1,asia-east1 \
  --message-storage-policy-enforce-in-transit
~~~

Khi publish request ở vùng được phép, Pub/Sub có thể lưu message tại region được phép gần publisher. **Thêm region vào policy không tự di chuyển messages đang lưu**, cũng không tự tạo multi-region synchronous replication. Với clients chỉ chạy ở một region, thêm region khác không tự làm pipeline HA nếu application không thể chuyển endpoint và workload.

### 9.4. Đồng bộ với Resource Location Restriction

~~~bash
# Dùng khi org policy đã được security/platform review.
gcloud pubsub topics update orders-resident \
  --project=shop-dev-001 \
  --recompute-message-storage-policy
~~~

**--recompute-message-storage-policy** là cách áp policy tổ chức hiện hành cho topic, **không** kết hợp với flags chỉ định vùng cụ thể trong cùng câu lệnh. Phải **readback** thuộc tính cả allowedPersistenceRegions và enforceInTransit, vì org policies có thể khác bản topic trước đó. Không tự sửa organization policy của môi trường dùng chung để chạy lab.

### 9.5. REST representation để review IaC

~~~json
{
  "name": "projects/shop-dev-001/topics/orders-resident",
  "messageStoragePolicy": {
    "allowedPersistenceRegions": [
      "asia-southeast1",
      "asia-east1"
    ],
    "enforceInTransit": true
  }
}
~~~

Đây là **phần nội dung Topic resource**; nếu dùng **topics.patch**, phải truyền **updateMask** chính xác theo API reference để chỉ sửa messageStoragePolicy, tránh thay thế/trắng các trường khác. Khi dùng Terraform/IaC, lập change plan và tránh drift giữa gcloud console và repository IaC.

## 10. Thực hành D — Java Publisher với ADC và regional endpoint

Ví dụ một ứng dụng Java 21 chạy trên Cloud Run phát sự kiện mà **không lưu JSON key**. Maven dùng thư viện **com.google.cloud:google-cloud-pubsub**, quản lý version bằng **Google Cloud libraries BOM** được tổ chức khóa/kiểm duyệt. Đoạn sau là mã lớp độc lập:

~~~java
import com.google.api.core.ApiFuture;
import com.google.cloud.pubsub.v1.Publisher;
import com.google.protobuf.ByteString;
import com.google.pubsub.v1.PubsubMessage;
import com.google.pubsub.v1.TopicName;
import java.util.concurrent.TimeUnit;

public final class OrderEventPublisher {
    private OrderEventPublisher() {}

    public static void main(String[] args) throws Exception {
        TopicName topic = TopicName.of("shop-dev-001", "orders-resident");

        // Endpoint cố định tại vùng được phép xử lý Pub/Sub.
        Publisher publisher = Publisher.newBuilder(topic)
            .setEndpoint("pubsub.asia-southeast1.rep.googleapis.com:443")
            .build();  // Sử dụng ADC của Cloud Run/GKE/workstation.

        try {
            PubsubMessage event = PubsubMessage.newBuilder()
                .setData(ByteString.copyFromUtf8(
                    "{\"eventId\":\"lab-002\",\"type\":\"order.created\"}"))
                .putAttributes("event_type", "order.created")
                .build();

            ApiFuture<String> result = publisher.publish(event);
            String messageId = result.get(30, TimeUnit.SECONDS);
            System.out.println("Published message ID: " + messageId);
        } finally {
            publisher.shutdown();
            publisher.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

**Ý nghĩa bảo mật:** Pub/Sub Java client lấy credential qua **ADC**. Cloud Run runtime identity có **roles/pubsub.publisher** tại topic, không cần quyền Cloud KMS. **setEndpoint** định tuyến RPC tới Pub/Sub **regional endpoint**; muốn subscriber có cùng bảo đảm, phải cấu hình endpoint tương ứng cho **Subscriber/Pull client** chứ không chỉ cho publisher.

### 10.1. Những thay đổi bắt buộc trước production

- Không tạo một Publisher cho **mỗi HTTP request**: tái sử dụng client để batching, retry, connection pooling hiệu quả.
- Gắn **eventId/idempotency key**, quản lý khả năng **publish retry gây duplicate** và consumers idempotent.
- Không log plaintext message nếu chứa thông tin nhạy cảm; không đặt customer ID/email/API key trong attributes.
- Chỉ ack ở consumer **sau commit xử lý**. Nếu consumer lỗi thì cho retry/dead-letter policy theo thiết kế; IAM/mã hóa không bảo đảm exactly-once end-to-end.
- Thiết kế circuit breaker/backoff, metrics và khả năng ngừng publish nếu **FAILED_PRECONDITION** là lỗi cấu hình lâu dài, không retry vô hạn.
- Dùng code path và Maven dependencies theo phiên bản đã xác thực. Nếu môi trường không được phép kết nối regional endpoint vì network policy, phải kiểm tra DNS/TLS/firewall/Private Google Access trước khi deploy.

### 10.2. Subscriber làm gì?

Pull subscriber có thể dùng **Subscriber** Java client với **MessageReceiver** callback; trong callback:

~~~java
// Đoạn mã trong callback đã được đăng ký với Subscriber:
// Chỉ ack sau khi xử lý bền vững đã thành công.
try {
    processAndCommit(message);  // Hàm nghiệp vụ do ứng dụng định nghĩa.
    consumer.ack();
} catch (Exception ex) {
    consumer.nack();
}
~~~

Đây là **pseudocode fragment**, không phải lớp Java biên dịch độc lập vì **processAndCommit, message, consumer** phải được khai báo trong callback thực tế. Với **enforceInTransit=true**, kiểm tra cả Subscriber client dùng **regional endpoint** trong danh sách cho phép.

## 11. Những cơ chế dễ nhầm với message storage policy

| Cơ chế | Tác dụng | Không đồng nghĩa |
|---|---|---|
| **Message storage policy** | Nơi lưu/xử lý message contents | **message retention** hoặc backup |
| **Subscription message retention** | Thời gian giữ messages theo subscription, có backlog | Residency, encryption, IAM |
| **Topic message retention** | Giữ bản sao messages ở topic trong cửa sổ cấu hình | Cho phép các region khác |
| **Snapshot / Seek / Replay** | Khôi phục trạng thái tiêu thụ trong giới hạn hỗ trợ | Khả năng phục hồi dữ liệu khi toàn bộ region hoặc key bị mất |
| **Ordering key** | Giữ thứ tự theo key với điều kiện cấu hình/region | Quyền và encryption |
| **Exactly-once delivery** | Tăng bảo đảm giao hàng cho **pull subscription** theo phạm vi hỗ trợ | Transactional exactly-once nghiệp vụ |
| **CMEK** | Cho phép điều khiển lớp mã hóa bằng KMS | Đảm bảo dữ liệu ở một region hoặc mã hóa trường trong payload |
| **VPC Service Controls** | Giảm rủi ro truy xuất dữ liệu ngoài security perimeter | Thay thế message storage policy hoặc Pub/Sub IAM |

**Ví dụ:** đặt subscription retention **7 ngày** không làm nội dung message chỉ được phép lưu ở Việt Nam/Châu Á. Muốn kiểm soát region cần message storage policy, muốn không xử lý ở region ngoài danh sách cần **enforceInTransit** và đúng endpoint.

Nếu topic có **ordering key** và policy loại bỏ region xử lý gần nhất, Pub/Sub có thể trả lỗi vì ràng buộc thứ tự và location. Cần kiểm thử chính sách thực tế trước khi chạy production ordering/exactly-once workload đa region.

## 12. Giám sát IAM, CMEK và vị trí message

### 12.1. Metrics cần quan sát trên Cloud Monitoring

| Mục tiêu | Metric trong Pub/Sub | Phản ứng |
|---|---|---|
| Publish bị lỗi | **topic/send_request_count**, chia theo response_code | Phân biệt 403 với FAILED_PRECONDITION |
| Pull bị lỗi | **subscription/pull_request_count** | Xem IAM, KMS, region/endpoint |
| StreamingPull bất thường | **subscription/streaming_pull_response_count** | Tìm response_code **FAILED_PRECONDITION**; không coi mọi kết thúc stream là sự cố |
| Backlog theo vùng | **subscription/num_unacked_messages_by_region** | Theo dõi tồn đọng ở mỗi region |
| Bytes backlog theo vùng | **subscription/unacked_bytes_by_region** | Xác nhận phân phối dữ liệu theo region |
| Message tồn đọng lâu | **subscription/oldest_unacked_message_age_by_region** | Cảnh báo trước khi hết retention |
| Sức khỏe giao hàng | **subscription/delivery_latency_health_score** | Tìm nguyên nhân trễ từ publish tới delivery |

Theo hướng dẫn Cloud Monitoring, **ưu tiên metrics có hậu tố _by_region** cho backlog khi giám sát hệ thống nhạy với sự cố vùng: metrics global có thể gián đoạn nếu một region không trả dữ liệu, trong khi các region khác vẫn báo bình thường.

### 12.2. Xem vị trí thực tế, không suy đoán từ topic ID

Trong **Cloud Monitoring → Metrics Explorer**:

1. Chọn Pub/Sub metric **subscription/unacked_bytes_by_region**.
2. Lọc subscription **orders-worker-sub** và project.
3. Group by **region**, xem bytes unacknowledged theo thời gian.
4. Đối chiếu regions hiển thị với **messageStoragePolicy.allowedPersistenceRegions**.
5. Kiểm tra thêm **topic/subscription retained acked bytes by region** khi sử dụng retention/replay.

**Lưu ý:** metrics backlog chỉ đo message còn tồn đọng, **không chứng minh** tất cả message đã ack trong quá khứ nằm tại đúng nơi. Số liệu sampling có độ trễ, và khi không có backlog thì biểu đồ có thể trống; cần kết hợp cấu hình policy, audit và quá trình thay đổi.

### 12.3. Audit và chi phí

- **Cloud Audit Logs** có thể ghi thay đổi IAM/topic policy; **Data Access logs** phải kiểm tra trạng thái bật, phạm vi dịch vụ và giá.
- **Cloud KMS audit logs** hỗ trợ chẩn đoán key disabled/permission; không log KMS secret material.
- **Cloud Billing** cần theo dõi Pub/Sub message throughput/storage, truyền liên vùng/outbound do storage policy, Cloud KMS cryptographic operations, logging/Monitoring.
- Gắn labels/owner vào topics/subscriptions theo chính sách, review quyền theo định kỳ và test IAM sau khi đổi service accounts.
- Budget alerts giúp cảnh báo chi phí nhưng **không tự ngừng dịch vụ**; khi hạn chế một region, đánh giá thêm tính sẵn sàng và chi phí mạng.

## 13. Troubleshooting theo triệu chứng

| Hiện tượng | Giả thuyết | Cách xác minh |
|---|---|---|
| **PERMISSION_DENIED** khi publish | Publisher SA thiếu Pub/Sub Publisher ở topic, sai identity/project | **gcloud pubsub topics get-iam-policy**, ADC/runtime SA |
| **PERMISSION_DENIED** khi pull | Subscriber thiếu quyền consume ở subscription | **get-iam-policy**, effective roles, resource name |
| Không tạo được subscription | Thiếu subscription create ở project hoặc attachSubscription tại topic | Quyền trên **cả project lẫn topic**, cross-project grants |
| Authenticated push trả 401/403 | Sai OIDC audience/Invoker, push SA hoặc token creator IAM | Push config, Cloud Run IAM, Pub/Sub service agent |
| **FAILED_PRECONDITION** ngay sau bật enforceInTransit | Publisher/subscriber được xử lý ngoài allowed regions | Topic policy, **regional endpoint**, client region |
| Push delivery dừng sau khi siết policy | Allowed regions không đáp ứng nơi xử lý push/external export | Push metrics, policy, location của endpoint/export |
| **FAILED_PRECONDITION** dù endpoint đã đúng vùng | KMS key disabled, key permissions bị thu hồi hoặc billing | KMS IAM/versions/audit, billing, Pub/Sub error details |
| Thay allowed regions nhưng dữ liệu cũ vẫn ở vùng cũ | Policy **không di chuyển messages đã publish** | Retention/backlog/snapshots, thời điểm policy update |
| Hôm qua bật enforce, hôm nay bỗng tắt | Update gcloud chỉ gửi allowed regions, bỏ flag enforce | Describe topic, review update command/IaC |
| CMEK rotate mà key version mới chưa được dùng | Key rotation Pub/Sub có độ trễ, không retroactive | Cloud KMS logs, topic key config, tối đa 12 giờ |
| Subscription backlog tăng | Subscriber không ack được do IAM/KMS/region hoặc code lỗi | Backlog **_by_region**, pull errors, GKE/Cloud Run logs |
| Không thấy dữ liệu trong metric _by_region | Không có backlog, metric sampling lag hoặc filter sai | Time window, resource/region, so metrics khác |
| Publish chạy nhưng consumer thiếu message | Subscription/filters/ack/retry vấn đề, không phải luôn IAM | Subscription settings, eventId, subscriber logs, DLQ |

### Quy trình xử lý sự cố theo lớp

~~~mermaid
flowchart TD
    E["Publish/Pull lỗi"] --> ERR{"HTTP/gRPC code?"}
    ERR -->|"PERMISSION_DENIED"| IAM["Xác nhận principal và resource IAM"]
    ERR -->|"FAILED_PRECONDITION"| PRE{"In-transit region hay CMEK?"}
    PRE --> REGION["Topic policy + endpoint + client region"]
    PRE --> KEY["KMS IAM + key version + Cloud Audit"]
    ERR -->|"INVALID_ARGUMENT"| CFG["Schema / topic / request config"]
    ERR -->|"UNAVAILABLE/DEADLINE_EXCEEDED"| RETRY["Transient outage / quota / retry policy"]
    IAM --> OBS["Readback + metrics + negative test"]
    REGION --> OBS
    KEY --> OBS
    CFG --> OBS
    RETRY --> OBS
~~~

**Không sửa mọi lỗi bằng cách tăng quyền IAM hoặc bỏ enforceInTransit.** Chọn đúng root cause; một lỗi KMS có thể biểu hiện cùng **FAILED_PRECONDITION** như lỗi vùng.

## 14. Case study: đơn hàng Java đa region và yêu cầu dữ liệu

Đội vận hành **An Bình** có hai clusters Cloud Run/GKE:

- **asia-southeast1**: đặt API và workers chính, chứa dữ liệu giao dịch.
- **asia-east1**: khu vực dự phòng có thể kích hoạt khi site chính lỗi.

Policy bảo mật cho thông điệp:

| Mục tiêu | Thiết kế |
|---|---|
| Tránh service khác publish đơn hàng | Publisher IAM chỉ trên topic **orders-resident** |
| Tránh worker đọc sự kiện ngoài phạm vi | Subscriber IAM chỉ trên subscription tương ứng |
| Nhân sự có quyền quản trị KMS nhưng không đọc message | Phân tách KMS admin, Pub/Sub service agent và subscriber |
| Lưu trong hai vùng cho phép | allowedPersistenceRegions = asia-southeast1, asia-east1 |
| Mọi request xử lý tại các vùng cho phép | enforceInTransit=true, publisher và subscriber cấu hình **regional endpoints** |
| Khả năng rotate key | CMEK có rotation và runbook giữ key cũ đến khi message cũ hết retention |
| Khả năng khôi phục | Thiết kế lại client endpoint, workloads, subscription replay và data stores; không giả định policy tự failover |

### 14.1. Chuyển vùng không chỉ là đổi flag

Khi phải chạy publisher/consumer ở **asia-east1**:

1. Kiểm tra region này đã nằm trong allowed list và đúng organization policy.
2. Chuyển Java clients sang **pubsub.asia-east1.rep.googleapis.com:443** theo configuration; không hardcode endpoint dự phòng vào một image release không có cơ chế thay đổi.
3. Xác nhận runtime service accounts/Workload Identity có IAM cần thiết và backend database/storage cũng có kế hoạch chuyển vùng.
4. Quan sát **publish success, pull, backlog by region**; nếu đã có ordering/exactly-once, kiểm tra điều kiện tương thích theo region.
5. Nếu dùng **regional Cloud KMS key**, phải đánh giá tính khả dụng của key khi chuyển sang region khác; dùng global CMEK khi được policy cho phép có thể đơn giản hơn.

**Không có cam kết:** chỉ cấu hình hai regions trong topic policy là có active-active replication của tất cả messages hoặc endpoint tự failover. Sẵn sàng vùng là thiết kế tổng thể của publishers, subscribers, APIs, KMS và dữ liệu.

### 14.2. Ma trận nghiệm thu

| Kiểm thử | Kỳ vọng |
|---|---|
| orders-publisher gửi lên topic | Thành công |
| orders-publisher Pull subscription | **PERMISSION_DENIED** nếu không có quyền khác |
| orders-subscriber Pull subscription | Thành công |
| Principal ngoài dự án publish | Bị chặn nếu không được IAM grant |
| Publish từ region bị cấm khi enforce=true | **FAILED_PRECONDITION** |
| Java publisher dùng endpoint allowed region | Thành công nếu IAM/quota/KMS hợp lệ |
| CMEK service agent thiếu CryptoKey Encrypter/Decrypter | Tạo/chạy topic có lỗi KMS; phát hiện trong lab |
| Update policy vùng | Messages mới theo policy; **messages cũ không tự migrate** |
| Rotate KMS key | Key mới áp dụng có độ trễ, không mã hóa lại message cũ |
| Region chính lỗi | Quy trình failover client/app được vận hành theo kế hoạch, có thể chịu delay |
| Backlog tăng | Metrics _by_region và alerts phát hiện |

## 15. Bài tập và đáp án gợi ý

### Bài tập A — Chọn role phù hợp

Producer Java chỉ publish vào **orders-events**; worker chỉ pull từ **orders-worker-sub**. Cấp role nào và ở đâu?

**Đáp án:** **roles/pubsub.publisher** tại topic cho producer; **roles/pubsub.subscriber** tại subscription cho worker. Không cấp Pub/Sub Admin cho ứng dụng.

### Bài tập B — Đúng principal cho CMEK

Một topic dùng KMS key, nhưng publisher có Publisher role và Pub/Sub báo lỗi thiếu quyền KMS. Có nên cấp **roles/cloudkms.cryptoKeyEncrypterDecrypter** cho publisher?

**Đáp án:** Không. Cấp cho **Pub/Sub service agent của project chứa topic** tại key cần dùng; publisher không cần trực tiếp encrypt/decrypt DEKs.

### Bài tập C — Storage policy khác transit policy

Topic chỉ cho lưu ở **asia-southeast1**, **enforceInTransit=false**. Publisher từ US vẫn gửi thành công. Có vi phạm policy không?

**Đáp án:** Không nhất thiết. Pub/Sub có thể nhận request ở một vùng khác rồi route nội dung về asia-southeast1 để lưu. Muốn từ chối request xử lý ngoài vùng cho phép, bật **enforceInTransit** và dùng regional endpoint tương ứng.

### Bài tập D — Gỡ nhầm enforcement

Lệnh cập nhật chỉ có **--message-storage-policy-allowed-regions=asia-east1** và trước đó **enforceInTransit=true**.

**Hỏi:** Rủi ro? **Đáp án:** CLI update có thể đưa thuộc tính in-transit bị bỏ qua trở lại mặc định. Phải truyền lại **--message-storage-policy-enforce-in-transit** khi còn muốn bật và đọc lại topic config.

### Bài tập E — Thay region và dữ liệu cũ

Topic lưu ở **us-central1** được sửa thành **asia-southeast1**. Toàn bộ messages đã publish có tự chuyển sang Châu Á ngay không?

**Đáp án:** Không. Policy mới áp cho **messages mới**, không di chuyển dữ liệu lịch sử. Phải xem backlog, retention/snapshots và chính sách xử lý dữ liệu cũ.

### Bài tập F — CMEK rotation

KMS rotate key version lúc 09:00, lúc 09:10 hệ thống vẫn dùng phiên bản cũ. Đây có phải lỗi tức thì?

**Đáp án:** Không nhất thiết. Pub/Sub có thể cần tới **12 giờ** để dùng key version mới; messages cũ vẫn dùng key trước khi rotate. Không disable key cũ khi dữ liệu còn cần đọc.

### Bài tập G — Đọc error code

Sau khi bật in-transit enforcement, Pub/Sub Java client dùng global endpoint và trả **FAILED_PRECONDITION**. Nên làm gì trước?

**Đáp án:** Kiểm tra **allowedPersistenceRegions**, region thực xử lý request và chuyển sang **regional endpoint được phép**. Đồng thời kiểm tra key/billing vì cùng error code có thể do KMS.

### Bài tập H — Định vị dữ liệu theo metric

Yêu cầu chứng minh backlog subscription không còn ở region bị cấm. Metric nào hỗ trợ và hạn chế?

**Đáp án:** **subscription/unacked_bytes_by_region** hoặc **num_unacked_messages_by_region**, lọc đúng subscription và group by region. Nó đo **backlog hiện tại**, không chứng minh mọi messages đã ack trong quá khứ đã bị xóa hoặc chuyển vùng.

### Bài tập I — Thiết kế production

Thiết kế Java orders-api ở Cloud Run và consumer ở GKE với yêu cầu: chỉ hai services được truy cập, CMEK riêng, allowed regions **asia-southeast1/asia-east1**, tất cả Publish/Pull phải xử lý tại vùng cho phép, có failover và monitoring.

**Đáp án định hướng:** KSA/Cloud Run IAM tách biệt, topic/subscription grants tối thiểu; service agent KMS permission; topic message storage policy + enforceInTransit; regional endpoints có config để chuyển vùng; idempotent consumer, backlog alerts theo region, retention/rollback và runbook CMEK rotation/failover.

## 16. Tổng kết và tài liệu tham khảo

**Sáu điều cần nhớ:**

1. **IAM kiểm soát ai:** Publisher tại topic, Subscriber tại subscription; phân biệt runtime identity với Pub/Sub service agent.
2. **Pub/Sub mã hóa at rest mặc định**; CMEK tăng quyền kiểm soát Cloud KMS nhưng mang thêm chi phí/rủi ro availability.
3. Với **CMEK**, Cloud KMS wrap/unwrap DEKs, không mã hóa mỗi payload riêng. **Attributes không được Pub/Sub mã hóa ở application layer** như message data.
4. **Message storage policy** giới hạn nơi lưu/xử lý **message contents**, không áp cho topic names/labels/IAM; đổi policy **không di chuyển message cũ**.
5. **enforceInTransit=true** từ chối requests xử lý ngoài allowed regions; publisher và pull subscriber nên dùng **regional endpoints** được phép.
6. **KMS rotation, IAM, backlog, regional endpoints và application failover** phải được kiểm thử cùng nhau, không coi storage policy là HA/backup/retention.

**Tài liệu Google Cloud chính thức:**

1. [Pub/Sub IAM access control](https://docs.cloud.google.com/pubsub/docs/access-control) — phân quyền topic, subscription và permissions.
2. [Pub/Sub predefined roles](https://docs.cloud.google.com/iam/docs/roles-permissions/pubsub) — Publisher, Subscriber, Admin, Viewer.
3. [Configure message encryption](https://docs.cloud.google.com/pubsub/docs/encryption) — default encryption, CMEK, service agent và key rotation.
4. [Configure message storage policies](https://docs.cloud.google.com/pubsub/docs/resource-location-restriction) — allowedPersistenceRegions, enforceInTransit, organization policy.
5. [Pub/Sub API endpoints](https://docs.cloud.google.com/pubsub/docs/reference/service_apis_overview) — global, regional, locational và cách chọn.
6. [Pub/Sub API error codes](https://docs.cloud.google.com/pubsub/docs/reference/error-codes) — PERMISSION_DENIED, FAILED_PRECONDITION và troubleshooting.
7. [Authenticate push subscriptions](https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions) — OIDC push, service agent IAM và audience.
8. [Monitor Pub/Sub](https://docs.cloud.google.com/pubsub/docs/monitoring) — backlog/latency metrics theo region.
9. [Create topics with gcloud](https://docs.cloud.google.com/sdk/gcloud/reference/pubsub/topics/create) — message storage policy và CMEK flags.
10. [Update topics with gcloud](https://docs.cloud.google.com/sdk/gcloud/reference/pubsub/topics/update) — recompute và update flags.
11. [Java Pub/Sub Publisher.Builder](https://docs.cloud.google.com/java/docs/reference/google-cloud-pubsub/latest/com.google.cloud.pubsub.v1.Publisher.Builder) — endpoint, batching, ADC options.
