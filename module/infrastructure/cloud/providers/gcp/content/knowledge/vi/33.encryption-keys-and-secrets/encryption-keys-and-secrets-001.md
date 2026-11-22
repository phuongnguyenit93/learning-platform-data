# Mã hóa mặc định và lựa chọn quản lý khóa trên GCP

Google Cloud tự động mã hóa dữ liệu khách hàng khi lưu trữ. Vì vậy, một workload mới thường đã có lớp bảo vệ at-rest mà không cần tạo khóa hay cấu hình thêm. Khi yêu cầu kiểm soát khóa, phân tách trách nhiệm, kiểm toán hoặc tuân thủ tăng lên, tổ chức có thể chuyển sang Customer-Managed Encryption Keys (CMEK) với Cloud Key Management Service (Cloud KMS), dùng Autokey để tự động cấp phát khóa hoặc kết nối một hệ thống quản lý khóa bên ngoài.

Bài học này giải thích cơ chế mã hóa mặc định, vai trò của các loại khóa và cách chọn mô hình quản lý khóa cho workload GCP. Ví dụ thực hành sử dụng Cloud Storage; các dịch vụ khác có quy trình tích hợp CMEK riêng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt mã hóa khi lưu trữ (encryption at rest) với mã hóa khi truyền (encryption in transit).
- Mô tả cách Google Cloud sử dụng DEK, KEK và envelope encryption.
- So sánh khóa do Google quản lý, CMEK, CMEK với Autokey, Cloud EKM và CSEK.
- Xác định khi nào cần CMEK và những điều kiện phải kiểm tra trước khi bật.
- Cấu hình một khóa Cloud KMS làm khóa mặc định cho bucket Cloud Storage.
- Đánh giá tác động của xoay vòng, vô hiệu hóa và hủy phiên bản khóa.

## 1. Mã hóa at-rest bảo vệ điều gì?

Encryption at rest bảo vệ dữ liệu đã được ghi lên thiết bị lưu trữ hoặc phương tiện sao lưu. Ví dụ trên GCP gồm object trong Cloud Storage, volume của Compute Engine, snapshot, dữ liệu lưu trong cơ sở dữ liệu và các nội dung khách hàng được lưu bởi những dịch vụ khác.

Mã hóa giúp dữ liệu khó bị đọc nếu một người không có quyền lấy được bản sao vật lý hoặc bản sao lưu. Tuy nhiên, mã hóa at-rest chỉ là một lớp trong mô hình bảo vệ dữ liệu:

| Lớp bảo vệ | Thời điểm áp dụng | Ví dụ trên GCP |
|---|---|---|
| Encryption at rest | Khi dữ liệu được lưu trên storage | Mã hóa object trong Cloud Storage hoặc Persistent Disk |
| Encryption in transit | Khi dữ liệu đi qua mạng | TLS giữa client và API, hoặc giữa các dịch vụ |
| Encryption in use | Khi dữ liệu đang được xử lý trong bộ nhớ | Confidential Computing, Confidential VM và các cơ chế bảo vệ bộ nhớ phù hợp |
| Application-level encryption | Trước khi ứng dụng gửi dữ liệu tới dịch vụ lưu trữ | Ứng dụng tự mã hóa trường nhạy cảm bằng thư viện mật mã |

Mã hóa mặc định at-rest không thay thế IAM, phân quyền ở tầng ứng dụng, kiểm soát mạng, quản lý bí mật hay mã hóa đầu cuối do ứng dụng thực hiện. Ví dụ, một người dùng có quyền đọc object hợp lệ vẫn có thể tải nội dung xuống; việc object được mã hóa at-rest không tự động từ chối yêu cầu đó.

Cũng cần phân biệt customer content với customer metadata. Nội dung như byte của object hoặc dữ liệu trên disk là trọng tâm của mã hóa at-rest. Một số metadata như tên object, nhãn, kích thước hoặc thông tin phục vụ vận hành có cách bảo vệ riêng. Không nên đưa bí mật vào tên resource, tên object hoặc metadata với giả định rằng CMEK sẽ mã hóa toàn bộ các trường đó.

## 2. Cơ chế mã hóa mặc định của Google Cloud

Google Cloud mã hóa customer content khi lưu trữ theo mặc định. Người dùng không phải tạo khóa, bật một cờ cấu hình hoặc quản lý lịch xoay vòng để nhận được lớp bảo vệ cơ bản này. Google sở hữu và vận hành hệ thống khóa dùng cho mô hình mặc định.

Tài liệu Google Cloud mô tả AES-256 là chuẩn mã hóa ở tầng lưu trữ. Một số tài nguyên Persistent Disk rất cũ có thể thuộc ngoại lệ lịch sử, vì vậy khi đánh giá một tài nguyên legacy cần kiểm tra tài liệu của đúng dịch vụ và thời điểm tạo tài nguyên.

### Envelope encryption

Ở quy mô lớn, hệ thống thường không dùng một khóa gốc duy nhất để mã hóa trực tiếp mọi byte dữ liệu. Thay vào đó, hệ thống dùng mô hình mã hóa bao (envelope encryption):

- Data Encryption Key (DEK) là khóa dữ liệu, dùng để mã hóa nội dung.
- Key Encryption Key (KEK) là khóa bảo vệ khóa, dùng để mã hóa hoặc bọc DEK.
- Ciphertext là nội dung đã được mã hóa.
- Wrapped DEK là DEK đã được mã hóa bằng KEK và được lưu cùng thông tin cần thiết để giải mã dữ liệu.

Sơ đồ khái quát:

~~~mermaid
flowchart LR
    A[Customer content] --> B[DEK]
    B --> C[Encrypt content]
    C --> D[Ciphertext at rest]
    B --> E[Wrap DEK with KEK]
    F[KEK] --> E
    E --> G[Wrapped DEK]
    D --> H[Storage]
    G --> H
~~~

Khi cần đọc dữ liệu, dịch vụ lấy wrapped DEK, yêu cầu cơ chế quản lý khóa giải bọc DEK, rồi dùng DEK để giải mã nội dung. Việc tách DEK và KEK giúp thay đổi hoặc kiểm soát khóa bảo vệ khóa mà không phải thiết kế lại toàn bộ cách lưu dữ liệu.

Trong mô hình mặc định, Google quản lý KEK và quy trình vận hành liên quan. Khách hàng không thể xem hoặc tự đặt lịch xoay vòng các khóa mặc định đó, cũng không có log sử dụng khóa ở mức quản trị khóa như khi dùng CMEK. Nhiều khách hàng có thể dùng chung một số KEK của hạ tầng Google; do đó, mô hình mặc định không tạo ranh giới khóa riêng cho từng khách hàng.

Điều này không có nghĩa dữ liệu mặc định được lưu dưới dạng plaintext. Dữ liệu vẫn được mã hóa và bảo vệ bởi hệ thống quản lý khóa, kiểm soát truy cập và kiểm toán nội bộ của Google. Khác biệt chính nằm ở quyền sở hữu, khả năng quan sát và quyền kiểm soát khóa của khách hàng.

## 3. Các thành phần trong Cloud KMS

Cloud KMS là dịch vụ quản lý khóa mật mã của Google Cloud. Khi một dịch vụ hỗ trợ CMEK, khóa Cloud KMS do khách hàng quản lý có thể đóng vai trò KEK bảo vệ DEK của tài nguyên.

Các khái niệm thường gặp:

| Thành phần | Ý nghĩa |
|---|---|
| Project | Phạm vi quản lý IAM, API, quota và tài nguyên |
| Location | Vị trí địa lý của key ring và khóa; phải phù hợp yêu cầu vị trí của dịch vụ sử dụng khóa |
| Key ring | Nhóm logic chứa các CryptoKey trong một location |
| CryptoKey | Tài nguyên đại diện cho khóa logic, chứa cấu hình và các phiên bản khóa |
| CryptoKeyVersion | Phiên bản chứa vật liệu khóa mật mã thực tế |
| Key rotation | Tạo phiên bản khóa mới và chuyển phiên bản chính sang phiên bản mới |
| Service agent | Danh tính dịch vụ Google Cloud dùng để thực hiện thao tác mã hóa/giải mã thay mặt dịch vụ |

Cấu trúc tài nguyên có dạng:

~~~text
projects/PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY_NAME/cryptoKeyVersions/VERSION
~~~

Một CryptoKey có thể có nhiều phiên bản. Phiên bản mới được tạo khi xoay vòng khóa; các phiên bản cũ thường phải được giữ lại để giải mã dữ liệu đã được bảo vệ bằng chúng. Quyền IAM được cấp trên CryptoKey áp dụng cho các phiên bản của khóa đó.

### Protection level

Khi tạo khóa, bạn chọn mức bảo vệ phù hợp:

- **SOFTWARE:** Cloud KMS bảo vệ và sử dụng vật liệu khóa bằng cơ chế phần mềm của dịch vụ. Đây là lựa chọn phổ biến cho nhiều workload.
- **HSM:** vật liệu khóa được tạo và sử dụng trong phần cứng bảo mật Cloud HSM. Chọn mức này khi yêu cầu kiểm soát phần cứng hoặc tiêu chuẩn tuân thủ đòi hỏi HSM.
- **EXTERNAL** hoặc **EXTERNAL_VPC:** Cloud KMS sử dụng khóa nằm trong hệ thống External Key Manager (EKM) được hỗ trợ. Khóa nằm ngoài ranh giới lưu trữ khóa thông thường của Cloud KMS; kết nối và khả năng sẵn sàng của hệ thống ngoài trở thành một phần của đường truy cập dữ liệu.

Không phải mọi dịch vụ GCP đều hỗ trợ mọi protection level. Cần kiểm tra ma trận tương thích của dịch vụ trước khi thiết kế.

## 4. Những lựa chọn quản lý khóa trên GCP

### 4.1. Google-owned and Google-managed keys

Đây là lựa chọn mặc định:

- Google sở hữu và quản lý khóa.
- Tự động áp dụng cho customer content được lưu trong các dịch vụ Google Cloud.
- Không cần cấu hình hoặc vận hành vòng đời khóa.
- Mã hóa mặc định được tính trong dịch vụ lưu trữ.
- Khách hàng không trực tiếp quản lý phiên bản khóa, lịch xoay vòng hoặc quyền sử dụng KEK mặc định.

Nên dùng khi yêu cầu bảo vệ dữ liệu thông thường đã được đáp ứng bởi mã hóa mặc định và tổ chức không cần quyền kiểm soát khóa riêng.

### 4.2. Customer-Managed Encryption Keys (CMEK)

CMEK là khóa khách hàng tạo và quản lý trong Cloud KMS, được một dịch vụ GCP tích hợp sử dụng để bảo vệ dữ liệu. CMEK thường đóng vai trò KEK trong envelope encryption; dịch vụ vẫn xử lý việc mã hóa dữ liệu và người dùng truy cập tài nguyên theo cách gần giống mô hình mặc định.

CMEK bổ sung các khả năng:

- Khách hàng kiểm soát việc tạo khóa, location, protection level và quyền IAM.
- Có thể đặt lịch xoay vòng, tạo phiên bản, vô hiệu hóa hoặc lên lịch hủy phiên bản.
- Có thể xem metadata khóa, theo dõi tài nguyên sử dụng khóa ở những dịch vụ hỗ trợ key tracking và xem audit log liên quan.
- Có thể tạo ranh giới mật mã riêng cho khách hàng hoặc workload.
- Có thể dùng việc hủy khóa có chủ đích để làm dữ liệu được bảo vệ bởi khóa đó không thể giải mã (crypto-shredding), sau khi đã đánh giá toàn bộ tác động.

CMEK chỉ hoạt động với các dịch vụ có tích hợp hoặc tuân thủ CMEK. Danh sách dịch vụ và phạm vi dữ liệu được bảo vệ có thể khác nhau. Một sản phẩm có thể có nhiều tích hợp CMEK riêng cho các loại dữ liệu khác nhau, vì vậy không nên suy luận rằng bật CMEK cho một tài nguyên sẽ bảo vệ mọi dữ liệu liên quan đến sản phẩm đó.

CMEK cũng không có nghĩa người dùng cuối phải được cấp quyền trực tiếp lên khóa. Thông thường, service agent của dịch vụ nhận quyền Cloud KMS CryptoKey Encrypter/Decrypter; dịch vụ dùng danh tính này để mã hóa hoặc giải mã trong quá trình xử lý yêu cầu.

### 4.3. CMEK với Cloud KMS Autokey

Autokey tự động tạo key ring và CryptoKey theo nhu cầu khi người dùng tạo tài nguyên tích hợp. Autokey cũng hỗ trợ tạo service agent và gán các quyền IAM cần thiết theo quy trình được hỗ trợ.

Autokey hữu ích khi tổ chức muốn:

- Chuẩn hóa cấu hình khóa cho nhiều project hoặc workload.
- Giảm thao tác cấp phát và gán khóa thủ công.
- Áp dụng các thực hành được khuyến nghị về location, mức bảo vệ HSM, phân tách trách nhiệm và lịch xoay vòng.
- Vẫn giữ quyền quản lý và khả năng quan sát đối với CMEK đã tạo.

Autokey không biến mọi dịch vụ thành dịch vụ hỗ trợ CMEK. Chỉ dùng cho resource type và dịch vụ có tích hợp Autokey. Nếu cần protection level hoặc lịch xoay vòng tùy chỉnh ngoài cấu hình Autokey, hãy đánh giá việc tạo CMEK thủ công.

### 4.4. Cloud External Key Manager (Cloud EKM)

Cloud EKM cho phép Cloud KMS sử dụng khóa được lưu trong một hệ thống quản lý khóa bên ngoài Google Cloud. Mô hình này phù hợp khi tổ chức cần giữ vật liệu khóa trong hệ thống do mình hoặc nhà cung cấp chuyên biệt vận hành.

Đổi lại, đường truy cập dữ liệu phụ thuộc vào kết nối tới EKM, quota, độ trễ và khả năng sẵn sàng của hệ thống bên ngoài. Nếu dịch vụ không thể sử dụng khóa ngoài, thao tác cần giải mã dữ liệu có thể thất bại. Cần thiết kế dự phòng, giám sát và quy trình xử lý sự cố cho cả hai phía. Không phải dịch vụ hỗ trợ Cloud KMS key nào cũng hỗ trợ Cloud EKM key.

### 4.5. Customer-Supplied Encryption Keys (CSEK)

CSEK là mô hình một số dịch vụ cho phép khách hàng gửi khóa cùng yêu cầu API để dịch vụ dùng khóa đó bảo vệ dữ liệu. CSEK khác với CMEK: khóa được cung cấp theo yêu cầu và khách hàng chịu trách nhiệm lưu giữ, cung cấp lại đúng khóa khi cần truy cập dữ liệu.

Cloud Storage vẫn có tài liệu hướng dẫn CSEK theo phạm vi hỗ trợ của dịch vụ. Với Compute Engine, CSEK đã bị ngừng cho tài nguyên Persistent Disk, image, machine image và snapshot kể từ ngày 20-07-2026, đồng thời dự kiến bị loại bỏ hoàn toàn ngày 20-07-2027. Đối với tài nguyên Compute Engine mới, hãy đánh giá CMEK làm phương án thay thế. Không áp dụng một kết luận về CSEK cho mọi dịch vụ; phải kiểm tra trạng thái hỗ trợ của từng dịch vụ.

### So sánh nhanh

| Lựa chọn | Ai kiểm soát khóa? | Khả năng kiểm soát của khách hàng | Khi nên cân nhắc |
|---|---|---|---|
| Google default encryption | Google | Thấp ở cấp KEK; tự động và không cần vận hành | Workload thông thường |
| CMEK thủ công | Khách hàng qua Cloud KMS | Cao: IAM, location, protection level, rotation, trạng thái khóa và audit | Cần kiểm soát khóa hoặc ranh giới mật mã riêng |
| CMEK với Autokey | Khách hàng; Autokey tự động cấp phát | Cao, giảm thao tác tạo và gán khóa | Cần chuẩn hóa CMEK ở quy mô nhiều workload |
| Cloud EKM | Tổ chức/nhà cung cấp EKM bên ngoài | Khóa được giữ ngoài Google Cloud | Yêu cầu kiểm soát vật liệu khóa bên ngoài |
| CSEK | Khách hàng | Khách hàng tự cung cấp và giữ khóa | Chỉ khi dịch vụ cụ thể còn hỗ trợ và mô hình này đáp ứng yêu cầu |

## 5. Quy trình chọn mô hình khóa

Có thể dùng các câu hỏi sau để chọn phương án:

1. **Dịch vụ có hỗ trợ CMEK không?** Nếu không, phải dùng mã hóa mặc định hoặc phương án mã hóa ở tầng ứng dụng mà dịch vụ cho phép.
2. **Có yêu cầu sở hữu hoặc kiểm soát khóa riêng không?** Nếu không, mã hóa mặc định thường là điểm bắt đầu phù hợp.
3. **Có cần audit việc sử dụng khóa hoặc tách người quản trị khóa khỏi người vận hành workload không?** Nếu có, đánh giá CMEK.
4. **Có cần tự động hóa việc tạo và gán khóa trên nhiều project không?** Nếu có, kiểm tra Autokey.
5. **Vật liệu khóa có bắt buộc nằm ngoài Google Cloud không?** Nếu có, đánh giá Cloud EKM và khả năng tương thích của dịch vụ.
6. **Có yêu cầu vị trí dữ liệu hoặc mức bảo vệ HSM cụ thể không?** Kiểm tra location, protection level và chính sách tổ chức trước khi tạo khóa.
7. **Đội vận hành có thể duy trì quyền truy cập khóa trong toàn bộ vòng đời dữ liệu không?** Nếu không, CMEK có thể tạo ra rủi ro gián đoạn hoặc mất dữ liệu khi khóa bị vô hiệu hóa hay hủy.

Ví dụ: một ứng dụng lưu ảnh công khai, không có yêu cầu riêng về quyền kiểm soát khóa, có thể dùng mã hóa mặc định. Một kho dữ liệu chứa hồ sơ khách hàng cần tách quyền quản trị khóa, kiểm toán việc sử dụng khóa và kiểm soát vòng đời có thể chọn CMEK. Nếu quy định yêu cầu vật liệu khóa ở hệ thống HSM ngoài Google Cloud, cần đánh giá Cloud EKM và kiểm tra dịch vụ có hỗ trợ hay không.

## 6. Thực hành: bảo vệ bucket Cloud Storage bằng CMEK

Ví dụ này tạo một khóa Cloud KMS trong project quản lý khóa, cấp quyền cho Cloud Storage service agent của project dữ liệu và đặt khóa làm khóa mã hóa mặc định cho bucket.

Giả sử:

- **KMS_PROJECT_ID:** project quản lý khóa.
- **DATA_PROJECT_ID:** project chứa bucket.
- **LOCATION:** location của bucket và key ring, ví dụ **asia-southeast1** nếu đó là location workload đã chọn.
- **KEY_RING:** tên key ring.
- **KEY_NAME:** tên CryptoKey.
- **BUCKET_NAME:** tên bucket duy nhất toàn cục.

### Bước 1: Bật API và tạo key ring

Bật Cloud KMS API trong project quản lý khóa:

~~~bash
gcloud services enable cloudkms.googleapis.com \
  --project=KMS_PROJECT_ID
~~~

Tạo key ring trong location phù hợp với bucket:

~~~bash
gcloud kms keyrings create KEY_RING \
  --location=LOCATION \
  --project=KMS_PROJECT_ID
~~~

Key ring được gắn với location khi tạo. Với Cloud Storage, key ring dùng cho bucket phải ở location tương thích với bucket. Với dịch vụ khác, hãy đọc yêu cầu location riêng của dịch vụ đó.

### Bước 2: Tạo CryptoKey

Tạo khóa đối xứng có purpose là encryption:

~~~bash
gcloud kms keys create KEY_NAME \
  --keyring=KEY_RING \
  --location=LOCATION \
  --purpose=encryption \
  --protection-level=software \
  --project=KMS_PROJECT_ID
~~~

Resource name đầy đủ của khóa có dạng:

~~~text
projects/KMS_PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY_NAME
~~~

Trong môi trường yêu cầu HSM, đánh giá **--protection-level=hsm** và xác nhận location hỗ trợ Cloud HSM. Chọn protection level theo yêu cầu bảo mật và khả năng tương thích, không chỉ theo mức độ cao nhất có thể chọn.

### Bước 3: Cấp quyền cho Cloud Storage service agent

Cloud Storage dùng service agent của project chứa bucket để gọi Cloud KMS. Cấp quyền CryptoKey Encrypter/Decrypter cho đúng service agent trên đúng khóa:

~~~bash
gcloud storage service-agent \
  --project=DATA_PROJECT_ID \
  --authorize-cmek=projects/KMS_PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY_NAME
~~~

Lệnh trên lấy hoặc tạo service agent cần thiết và cấp quyền sử dụng CMEK. Nếu tổ chức thực hiện phân quyền thủ công, role cần thiết là **roles/cloudkms.cryptoKeyEncrypterDecrypter**. Khi khóa nằm trong project riêng, cần cấp quyền trên khóa cho service agent của project dữ liệu.

Người dùng hoặc workload truy cập object không cần được cấp quyền Cloud KMS trực tiếp chỉ để đọc object. Cloud Storage service agent thực hiện thao tác với khóa thay mặt dịch vụ; IAM trên bucket vẫn quyết định người gọi có được đọc object hay không.

### Bước 4: Tạo bucket với CMEK

~~~bash
gcloud storage buckets create gs://BUCKET_NAME \
  --location=LOCATION \
  --default-encryption-key=projects/KMS_PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY_NAME \
  --project=DATA_PROJECT_ID
~~~

Đối với bucket đã tồn tại, có thể đặt hoặc thay đổi khóa mặc định:

~~~bash
gcloud storage buckets update gs://BUCKET_NAME \
  --default-encryption-key=projects/KMS_PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY_NAME \
  --project=DATA_PROJECT_ID
~~~

Khóa mặc định của bucket được dùng cho object được ghi mới sau khi cấu hình. Việc thay đổi khóa mặc định không tự động mã hóa lại các object đã tồn tại trước đó.

### Bước 5: Xác minh cấu hình

Xem khóa mặc định của bucket:

~~~bash
gcloud storage buckets describe gs://BUCKET_NAME \
  --format="default(default_kms_key)" \
  --project=DATA_PROJECT_ID
~~~

Khi cần xác minh một object cụ thể, kiểm tra metadata của object, bao gồm trường **kmsKeyName** nếu có. Với Cloud Storage, CMEK bảo vệ nội dung object và một số giá trị kiểm tra như CRC32C, MD5; nhiều metadata khác vẫn được bảo vệ bằng khóa phía máy chủ của Google. Vì vậy, không dùng CMEK làm lý do để đưa thông tin nhạy cảm vào tên object hoặc metadata.

## 7. Vòng đời khóa: xoay vòng, vô hiệu hóa và hủy

Quản lý khóa không kết thúc khi tạo CryptoKey. Mỗi phiên bản khóa có thể đang bảo vệ dữ liệu tồn tại trong thời gian dài, vì vậy thao tác vòng đời phải gắn với inventory tài nguyên và quy trình khôi phục.

### Xoay vòng không đồng nghĩa mã hóa lại dữ liệu

Khi xoay vòng một symmetric key trong Cloud KMS, hệ thống tạo CryptoKeyVersion mới và đặt phiên bản đó làm phiên bản chính. Dịch vụ có thể dùng phiên bản mới để bảo vệ DEK mới. Phiên bản cũ vẫn cần tồn tại để giải mã dữ liệu đã được mã hóa trước đó.

Cách một dịch vụ áp dụng phiên bản mới phụ thuộc vào tích hợp của dịch vụ:

- Một số dịch vụ tự động bảo vệ lại DEK bằng phiên bản mới.
- Một số dịch vụ chỉ dùng phiên bản mới cho dữ liệu hoặc object được tạo sau thời điểm xoay vòng.
- Một số dịch vụ yêu cầu thao tác di chuyển, rewrite hoặc tạo lại tài nguyên.

Với Cloud Storage, object đã ghi trước khi thay đổi phiên bản vẫn có thể phụ thuộc vào phiên bản khóa cũ. Nếu cần chuyển dữ liệu sang khóa hoặc phiên bản mới, phải thực hiện rewrite object theo hướng dẫn của Cloud Storage và xác minh kết quả. Không được xóa phiên bản cũ ngay sau khi xoay vòng.

### Vô hiệu hóa phiên bản khóa

Khi một phiên bản khóa bị disable, dịch vụ không thể dùng phiên bản đó để thực hiện thao tác mật mã sau khi trạng thái đã có hiệu lực. Dữ liệu phụ thuộc vào phiên bản đó có thể không đọc được. Vô hiệu hóa có thể đảo ngược bằng cách enable lại nếu phiên bản chưa bị hủy.

Đây là một biện pháp phản ứng sự cố hữu ích khi nghi ngờ khóa bị lộ, nhưng cũng có thể gây outage. Trước khi thực hiện, cần biết tài nguyên nào đang phụ thuộc vào khóa và xác định người có quyền khôi phục.

### Hủy phiên bản khóa

Destroy là thao tác có hậu quả nghiêm trọng. Khi vật liệu khóa của phiên bản bị hủy, dữ liệu chỉ có thể được giải mã bằng phiên bản đó sẽ không thể khôi phục bằng cách bật lại khóa. Hủy khóa có thể được dùng cho crypto-shredding hoặc xử lý vòng đời dữ liệu, nhưng chỉ sau khi đã xác nhận:

- Không còn tài nguyên cần phiên bản đó để đọc hoặc phục hồi.
- Dữ liệu cần giữ lại đã được di chuyển hoặc mã hóa lại bằng khóa còn hiệu lực.
- Snapshot, bản sao lưu, object cũ và môi trường khôi phục thảm họa đã được kiểm kê.
- Chính sách lưu giữ, legal hold và yêu cầu tuân thủ cho phép hủy.
- Quy trình phê duyệt và thời gian chờ hủy đã được thực hiện.

Không dùng thao tác destroy như một bước dọn dẹp định kỳ mà không kiểm tra mức độ sử dụng của từng phiên bản.

## 8. IAM, kiểm toán và vận hành an toàn

CMEK tạo thêm quyền kiểm soát nhưng cũng thêm một phụ thuộc vận hành. Nếu service agent mất quyền sử dụng khóa, khóa bị disable hoặc key project gặp sự cố, dịch vụ lưu trữ có thể không giải mã được dữ liệu.

Các thực hành nên áp dụng:

1. **Tách trách nhiệm:** người quản trị Cloud KMS không nhất thiết phải là người quản trị workload. Cấp role quản lý khóa cho nhóm bảo mật và quyền sử dụng khóa cho service agent cần thiết.
2. **Least privilege:** cấp **roles/cloudkms.cryptoKeyEncrypterDecrypter** trên CryptoKey cụ thể khi có thể; tránh cấp quyền rộng ở project hoặc organization nếu không cần.
3. **Quản lý location:** đặt key ring ở location tương thích với tài nguyên và yêu cầu residency. Với dịch vụ có yêu cầu location đặc biệt, làm theo tài liệu tích hợp của dịch vụ.
4. **Theo dõi audit log:** giám sát thao tác quản trị khóa và hoạt động mật mã. Xác định log cần bật, nơi lưu log, thời gian lưu và cảnh báo cho các thao tác nhạy cảm.
5. **Kiểm tra khôi phục:** thử quy trình enable lại khóa, chuyển phiên bản và phục hồi dữ liệu trong môi trường kiểm thử.
6. **Quản lý phụ thuộc:** duy trì inventory ánh xạ giữa key, key version, project, service agent và tài nguyên được bảo vệ.
7. **Lập kế hoạch chi phí và quota:** Cloud KMS có chi phí theo phiên bản khóa và hoạt động; HSM và EKM có quota, giới hạn và cấu trúc chi phí riêng. Kiểm tra bảng giá và quota hiện hành trước khi triển khai ở quy mô lớn.
8. **Đặt chính sách tổ chức:** với môi trường nhiều project, cân nhắc Organization Policy để giới hạn project được dùng làm nguồn CMEK, dịch vụ bắt buộc CMEK hoặc protection level được phép.

## 9. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Nghĩ rằng mọi dịch vụ đều hỗ trợ CMEK | Tài nguyên không thể dùng khóa theo thiết kế mong muốn | Kiểm tra CMEK integrations và phạm vi dữ liệu được bảo vệ |
| Tạo key ring sai location | Dịch vụ từ chối cấu hình khóa hoặc không đáp ứng yêu cầu vị trí | Đối chiếu location của resource với yêu cầu của dịch vụ |
| Quên cấp quyền cho service agent | Tạo hoặc đọc tài nguyên bằng CMEK thất bại | Cấp đúng role trên đúng CryptoKey cho service agent |
| Cấp quyền KMS cho mọi developer | Mở rộng quyền quản lý hoặc sử dụng khóa quá mức | Phân biệt quyền quản trị khóa, quyền dùng khóa và quyền truy cập dữ liệu |
| Xoay vòng rồi hủy ngay phiên bản cũ | Dữ liệu cũ có thể không giải mã được | Kiểm tra cách dịch vụ xoay vòng và inventory trước khi hủy |
| Cho rằng đổi default key sẽ mã hóa lại dữ liệu cũ | Object hoặc tài nguyên cũ vẫn dùng khóa trước đó | Thực hiện rewrite/migration theo hướng dẫn của dịch vụ |
| Không có quy trình dự phòng cho Cloud EKM | Sự cố EKM có thể làm gián đoạn truy cập dữ liệu | Kiểm tra SLA, kết nối, quota, monitoring và runbook |
| Dùng CSEK Compute Engine cho tài nguyên mới | Không thể tạo tài nguyên bằng tính năng đã ngừng nhận sử dụng mới | Chọn CMEK và lập kế hoạch di chuyển tài nguyên legacy |

## 10. Checklist trước khi đưa CMEK vào production

- [ ] Đã xác định chính xác loại dữ liệu và tài nguyên cần bảo vệ.
- [ ] Đã xác nhận dịch vụ và loại resource hỗ trợ CMEK.
- [ ] Đã chọn mô hình Google default, CMEK thủ công, Autokey hoặc Cloud EKM theo yêu cầu.
- [ ] Đã chọn project, location và protection level phù hợp.
- [ ] Đã phân tách vai trò quản trị khóa và vận hành workload.
- [ ] Service agent đã có quyền tối thiểu trên CryptoKey.
- [ ] Đã kiểm tra chi phí, quota và giới hạn tích hợp.
- [ ] Đã cấu hình audit log, giám sát và cảnh báo thao tác nhạy cảm.
- [ ] Đã xác định cách xoay vòng và di chuyển dữ liệu cũ.
- [ ] Đã thử nghiệm disable/enable, khôi phục và xử lý sự cố khóa.
- [ ] Đã có inventory tài nguyên phụ thuộc vào từng CryptoKeyVersion.
- [ ] Đã có quy trình phê duyệt trước khi destroy phiên bản khóa.

## Kết luận

Google Cloud default encryption cung cấp mã hóa at-rest tự động cho customer content và là nền tảng phù hợp cho nhiều workload. CMEK bổ sung quyền kiểm soát khóa, audit và ranh giới mật mã cho các dịch vụ hỗ trợ. Autokey giảm công sức cấp phát CMEK; Cloud EKM đáp ứng nhu cầu giữ khóa ở hệ thống bên ngoài nhưng thêm phụ thuộc về kết nối và độ sẵn sàng.

Quyết định quan trọng nhất là chọn mức kiểm soát phù hợp với yêu cầu dữ liệu và khả năng vận hành khóa trong suốt vòng đời tài nguyên. Một khóa CMEK chỉ tăng cường bảo vệ khi IAM được cấu hình đúng, service agent luôn có quyền hợp lệ, phiên bản cũ được giữ đủ lâu và quy trình khôi phục đã được kiểm chứng.

## Tài liệu tham khảo

- [Default encryption at rest](https://cloud.google.com/docs/security/encryption/default-encryption)
- [Customer-managed encryption keys (CMEK)](https://cloud.google.com/kms/docs/cmek)
- [Cloud KMS with Autokey](https://cloud.google.com/kms/docs/kms-autokey)
- [Cloud KMS key rotation](https://cloud.google.com/kms/docs/key-rotation)
- [Use customer-managed encryption keys with Cloud Storage](https://cloud.google.com/storage/docs/encryption/using-customer-managed-keys)
- [Cloud Storage customer-managed encryption keys](https://cloud.google.com/storage/docs/encryption/customer-managed-keys)
- [Deprecation of CSEK in Compute Engine](https://cloud.google.com/compute/docs/deprecations/csek-deprecation-in-compute-engine)

