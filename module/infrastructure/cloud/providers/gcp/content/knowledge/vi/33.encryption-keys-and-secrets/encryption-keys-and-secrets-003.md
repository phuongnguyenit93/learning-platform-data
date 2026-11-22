# CMEK và tích hợp khóa do khách hàng quản lý

Khi triển khai workload trên Google Cloud, dữ liệu lưu trữ được mã hóa mặc định. Với nhiều hệ thống, cơ chế mặc định đã đáp ứng tốt yêu cầu bảo vệ dữ liệu. Tuy nhiên, một số tổ chức cần tự quyết định khóa nào bảo vệ dữ liệu, khóa nằm ở đâu, ai được phép sử dụng khóa, lịch luân chuyển khóa và thời điểm thu hồi quyền giải mã. **Customer-managed encryption keys (CMEK)** đáp ứng nhu cầu kiểm soát đó thông qua Cloud Key Management Service (Cloud KMS) và các dịch vụ Google Cloud có tích hợp CMEK.

Trong module CLOUD_PROVIDERS_GCP, CMEK liên quan trực tiếp đến cách tổ chức project, IAM, lưu trữ, cơ sở dữ liệu và vận hành workload. Một thiết kế tốt cần kết hợp vị trí tài nguyên, quyền của service agent, chính sách vòng đời khóa, khả năng phục hồi và chi phí. Chỉ bật tùy chọn CMEK trên một tài nguyên là chưa đủ để bảo đảm hệ thống có thể vận hành an toàn lâu dài.

Sau bài học này, bạn có thể:

- Phân biệt mã hóa mặc định của Google Cloud, CMEK, khóa do khách hàng cung cấp và mã hóa phía ứng dụng.
- Mô tả cách CMEK bảo vệ data encryption key (DEK) bằng key encryption key (KEK).
- Giải thích vai trò của key ring, CryptoKey, key version và service agent.
- Chọn vị trí, mức bảo vệ, phạm vi sử dụng và quyền IAM phù hợp cho khóa.
- Tích hợp CMEK vào một tài nguyên Cloud Storage bằng Google Cloud CLI.
- Lập kế hoạch luân chuyển khóa, thay khóa, giám sát và xử lý sự cố mà không làm mất khả năng truy cập dữ liệu.

## 1. CMEK giải quyết vấn đề gì?

### Mã hóa mặc định vẫn là lớp bảo vệ nền tảng

Google Cloud mã hóa dữ liệu lưu trữ theo mặc định. Dịch vụ quản lý các khóa nền tảng và thực hiện phần lớn thao tác mã hóa, giải mã thay cho khách hàng. Người dùng không cần tạo key ring hoặc cấp quyền Cloud KMS để sử dụng tính năng mã hóa mặc định.

Với mã hóa mặc định, khách hàng vẫn quản lý quyền truy cập tài nguyên bằng IAM, cấu hình mạng, chính sách tổ chức và các biện pháp bảo vệ khác. Tuy nhiên, khách hàng không trực tiếp quản lý từng khóa mã hóa nền tảng, lịch luân chuyển hoặc nhật ký sử dụng của các khóa đó.

CMEK bổ sung một lớp kiểm soát: khách hàng tạo hoặc chọn khóa trong Cloud KMS, quản lý quyền sử dụng khóa và gắn khóa đó với tài nguyên của một dịch vụ hỗ trợ CMEK. Dịch vụ vẫn xử lý mã hóa và giải mã trong luồng truy cập thông thường; Cloud KMS thực hiện thao tác cần thiết với khóa do khách hàng quản lý.

### So sánh các lựa chọn mã hóa

| Cơ chế | Ai quản lý khóa? | Cách tích hợp | Khi nào nên cân nhắc? |
|---|---|---|---|
| Mã hóa mặc định của Google Cloud | Google quản lý khóa nền tảng | Dịch vụ tự động mã hóa dữ liệu lưu trữ | Phù hợp với phần lớn workload cần mã hóa at rest mà không cần tự vận hành khóa |
| CMEK | Khách hàng quản lý khóa trong Cloud KMS | Dịch vụ tích hợp gọi Cloud KMS thông qua service agent | Khi cần kiểm soát vị trí, quyền, vòng đời, luân chuyển và khả năng thu hồi khóa |
| Customer-supplied encryption key (CSEK) | Khách hàng cung cấp khóa trong từng yêu cầu; cách hỗ trợ phụ thuộc dịch vụ | Ứng dụng gửi khóa theo yêu cầu thay vì tham chiếu CMEK đã cấu hình | Một số tình huống đặc thù, chẳng hạn Cloud Storage cần dùng khóa khách hàng cung cấp theo từng thao tác |
| Mã hóa phía ứng dụng (client-side encryption) | Khách hàng quản lý toàn bộ khóa và quy trình mã hóa | Ứng dụng mã hóa trước khi gửi dữ liệu lên Google Cloud | Khi ứng dụng cần giữ dữ liệu ở dạng ciphertext trước khi dịch vụ đám mây nhận được dữ liệu |

CMEK không thay thế IAM, VPC Service Controls, phân loại dữ liệu, quản lý bí mật ứng dụng hay mã hóa phía ứng dụng. CMEK tập trung vào quyền kiểm soát khóa mã hóa dữ liệu at rest trong những dịch vụ đã tích hợp. Cần kiểm tra chính xác loại tài nguyên và loại dữ liệu được bảo vệ; một sản phẩm có thể hỗ trợ CMEK cho một số thành phần nhưng không phải mọi dữ liệu liên quan đến sản phẩm đó.

## 2. CMEK hoạt động như thế nào?

Các dịch vụ tích hợp CMEK thường sử dụng **envelope encryption** (mã hóa bao bọc). Dữ liệu lớn được mã hóa bằng một khóa dữ liệu riêng, gọi là DEK. CMEK đóng vai trò khóa mã hóa khóa (KEK), dùng để bảo vệ DEK.

Quy trình khái quát:

1. Dịch vụ tạo hoặc sử dụng một DEK để mã hóa dữ liệu.
2. Dịch vụ yêu cầu Cloud KMS dùng CMEK để mã hóa (wrap) DEK.
3. Dịch vụ lưu dữ liệu đã mã hóa cùng DEK ở dạng đã được bảo vệ.
4. Khi cần đọc dữ liệu, service agent yêu cầu Cloud KMS giải mã (unwrap) DEK.
5. Dịch vụ dùng DEK để giải mã dữ liệu và trả kết quả theo quyền truy cập tài nguyên của người gọi.

~~~mermaid
flowchart TD
    U[Người dùng hoặc ứng dụng] --> S[Dịch vụ Google Cloud]
    S -->|Yêu cầu tạo hoặc mở dữ liệu| A[Service agent của dịch vụ]
    A -->|Quyền IAM trên khóa| K[Cloud KMS - CMEK]
    K -->|Bảo vệ hoặc mở DEK| A
    A --> S
    S -->|Dùng DEK mã hóa hoặc giải mã| D[(Dữ liệu đã mã hóa)]
~~~

Sơ đồ thể hiện quan hệ logic; thứ tự gọi nội bộ và cách lưu DEK có thể khác nhau giữa các dịch vụ.

Điểm quan trọng là người dùng đọc bucket, bảng hoặc đĩa thường không cần được cấp trực tiếp quyền Cloud KMS CryptoKey Encrypter/Decrypter. Service agent của dịch vụ thực hiện thao tác mã hóa và giải mã ở phía sau. Người dùng vẫn phải có quyền IAM phù hợp trên tài nguyên. Nếu service agent mất quyền dùng khóa, key version bị vô hiệu hóa hoặc bị phá hủy, các thao tác cần giải mã có thể thất bại dù người dùng vẫn có quyền đọc tài nguyên.

Cloud KMS không cung cấp cho người dùng quyền xem hoặc xuất raw key material của key version. Dịch vụ Cloud KMS thực hiện thao tác mật mã thay mặt principal đã được cấp quyền.

## 3. Hiểu cấu trúc tài nguyên Cloud KMS

Một khóa CMEK được tổ chức theo cấu trúc sau:

~~~text
Google Cloud project
└── Location
    └── Key ring
        └── CryptoKey
            ├── CryptoKeyVersion 1
            ├── CryptoKeyVersion 2
            └── CryptoKeyVersion 3 (primary)
~~~

| Thành phần | Ý nghĩa | Quyết định vận hành |
|---|---|---|
| Project | Ranh giới quản trị, IAM, billing và API | Có thể đặt khóa trong project riêng để tách quyền quản trị khóa khỏi quyền quản trị workload |
| Location | Khu vực lưu trữ và thực hiện thao tác với khóa | Phải tương thích với location của tài nguyên và quy tắc riêng của dịch vụ |
| Key ring | Nhóm logic chứa các khóa trong cùng location | Dùng để tổ chức theo môi trường, dịch vụ hoặc phạm vi quản trị |
| CryptoKey | Định danh logic của khóa được tài nguyên tham chiếu | Đây là tài nguyên CMEK mà dịch vụ thường nhận trong cấu hình |
| CryptoKeyVersion | Phiên bản chứa key material dùng cho thao tác mật mã | Có thể được bật, vô hiệu hóa hoặc lên lịch phá hủy theo quy trình quản trị |

Một CryptoKey có thể có nhiều phiên bản. Phiên bản primary được dùng cho thao tác mã hóa mới theo cơ chế của dịch vụ. Những phiên bản cũ thường cần được giữ lại để giải mã dữ liệu đã được bảo vệ bằng phiên bản đó. Vì vậy, tạo phiên bản mới không đồng nghĩa có thể xóa ngay phiên bản cũ.

Các khóa CMEK dùng cho mã hóa dữ liệu phải có purpose đối xứng ENCRYPT_DECRYPT và thuật toán GOOGLE_SYMMETRIC_ENCRYPTION theo yêu cầu tích hợp CMEK của Google Cloud. Khi tạo khóa bằng gcloud, giá trị purpose tương ứng là encryption.

### Chọn mức bảo vệ khóa

Cloud KMS hỗ trợ các mức bảo vệ chính:

- **Software:** thao tác mật mã được thực hiện bằng phần mềm của Cloud KMS. Đây là lựa chọn phù hợp cho nhiều workload thông thường.
- **HSM:** thao tác mật mã diễn ra trong Cloud HSM. Cân nhắc khi yêu cầu bảo vệ phần cứng hoặc chính sách tuân thủ đòi hỏi HSM.
- **External / External VPC:** khóa được giữ trong hệ thống quản lý khóa bên ngoài thông qua Cloud External Key Manager (Cloud EKM). Lựa chọn này hữu ích khi tổ chức phải giữ key material trong hệ thống của mình hoặc đối tác được hỗ trợ.

Cloud HSM và Cloud EKM có yêu cầu về quota, chi phí, kết nối và độ sẵn sàng khác với khóa software. Khi dùng Cloud EKM, khả năng mã hóa hoặc giải mã còn phụ thuộc vào hệ thống khóa bên ngoài và kết nối tới hệ thống đó.

Ngoài ra, Cloud KMS cho phép nhập key material được tạo ở bên ngoài vào một khóa Cloud KMS (BYOK). Sau khi nhập, key material được quản lý trong Cloud KMS theo cấu hình khóa. Đây là mô hình khác với Cloud EKM, nơi key material tiếp tục nằm trong hệ thống bên ngoài. Việc tự tạo và nhập key material làm tăng trách nhiệm bảo vệ bản gốc, tự động hóa nhập phiên bản mới và kiểm soát quy trình khôi phục.

### Cloud KMS Autokey

Cloud KMS Autokey tự động cấp phát key ring và CMEK khi tạo hoặc cập nhật tài nguyên thuộc dịch vụ được hỗ trợ. Autokey cũng có thể tự động cấp quyền cần thiết cho service agent. Cơ chế này giảm thao tác thủ công và giúp áp dụng chính sách tạo khóa nhất quán ở cấp folder hoặc project.

Autokey phù hợp khi các thiết lập khóa được tạo tự động đáp ứng yêu cầu về location, protection level, độ chi tiết của khóa và phân tách nhiệm vụ. Tổ chức vẫn cần quản lý ai có quyền yêu cầu cấp khóa, ai được thay đổi hoặc phá hủy key version, cũng như theo dõi các thay đổi do Autokey tạo ra.

## 4. Thiết kế tích hợp CMEK trước khi triển khai

### Xác minh dịch vụ và phạm vi dữ liệu

Không nên giả định rằng mọi tài nguyên trong một dịch vụ đều dùng được CMEK. Hãy kiểm tra danh sách dịch vụ tích hợp CMEK và tài liệu của đúng loại tài nguyên. Ví dụ:

| Dịch vụ | Ví dụ phạm vi có thể bảo vệ | Danh tính cần cấp quyền |
|---|---|---|
| Cloud Storage | Object trong bucket, thông qua khóa mặc định của bucket hoặc khóa chỉ định cho object | Cloud Storage service agent của project chứa bucket |
| BigQuery | Dataset, table hoặc kết quả truy vấn tùy cách cấu hình | BigQuery service account của project chạy BigQuery |
| Compute Engine | Persistent Disk, snapshot và machine image được hỗ trợ | Compute Engine service agent của project chứa tài nguyên |
| Google Kubernetes Engine (GKE) | Node boot disk và attached Persistent Disk; mã hóa Kubernetes Secret ở application layer là tích hợp riêng | Compute Engine service agent cho CMEK của các disk |

Danh sách trên chỉ là ví dụ. Hãy mở tài liệu CMEK của dịch vụ để xác nhận loại tài nguyên, location, giới hạn và quy trình cấp quyền hiện hành trước khi triển khai.

### Chọn project và phân tách nhiệm vụ

Một thiết kế phổ biến đặt workload trong project dữ liệu và đặt key ring trong project quản lý khóa riêng. Cách tách này giúp nhóm vận hành ứng dụng không mặc nhiên có quyền thay đổi hoặc phá hủy khóa bảo vệ dữ liệu.

Nên phân biệt ít nhất ba nhóm trách nhiệm:

- **Key administrator:** tạo key ring, tạo khóa, cấu hình rotation và quản lý trạng thái key version.
- **Resource administrator:** tạo bucket, dataset, disk hoặc tài nguyên cần bảo vệ và chọn CMEK phù hợp.
- **Service agent:** chỉ nhận quyền sử dụng khóa để mã hóa và giải mã theo tích hợp của dịch vụ.

Không cấp Owner hoặc Editor chỉ để khắc phục lỗi CMEK. Hãy cấp quyền cần thiết tại phạm vi hẹp nhất. Vai trò thường dùng cho service agent là Cloud KMS CryptoKey Encrypter/Decrypter, mã IAM là roles/cloudkms.cryptoKeyEncrypterDecrypter, được gán trực tiếp trên CryptoKey nếu mô hình vận hành cho phép.

### Chọn location và độ chi tiết của khóa

Location của key ring phải tương thích với location của tài nguyên. Với tài nguyên regional hoặc zonal, khóa thường phải ở cùng region hoặc location được dịch vụ cho phép. Với tài nguyên multi-region, location của key ring phải tương ứng với multi-region đó. Một số dịch vụ không hỗ trợ location global hoặc có quy tắc riêng cho dual-region; cần kiểm tra tài liệu của từng dịch vụ.

Google khuyến nghị thiết kế khóa với phạm vi có thể quản lý được, thường theo một project, một location, một dịch vụ và khi phù hợp là một tài nguyên. Khóa dùng chung quá rộng làm tăng ảnh hưởng khi một phiên bản bị vô hiệu hóa hoặc phá hủy. Ngược lại, tạo quá nhiều khóa làm tăng công việc quản trị. Hãy chọn mức chi tiết phù hợp với ranh giới dữ liệu, yêu cầu tuân thủ và khả năng vận hành.

## 5. Thực hành: bảo vệ Cloud Storage bucket bằng CMEK

Ví dụ này tạo một khóa trong project quản lý khóa riêng và dùng khóa đó làm khóa mã hóa mặc định cho object mới trong một bucket. Hãy thay các giá trị mẫu bằng project ID, tên bucket và location hợp lệ trong môi trường của bạn.

### Bước 1: Chuẩn bị biến và bật Cloud KMS API

~~~bash
export KEY_PROJECT_ID="security-keys-prod"
export DATA_PROJECT_ID="application-data-prod"
export LOCATION="asia-southeast1"
export KEY_RING="storage-ring"
export KEY_NAME="customer-data"
export BUCKET_NAME="example-customer-data-bucket"

gcloud services enable cloudkms.googleapis.com --project="$KEY_PROJECT_ID"
~~~

Project lưu khóa cần bật Cloud KMS API. Tài khoản triển khai phải có quyền tạo key ring, CryptoKey và cập nhật IAM policy của khóa. Tài khoản cũng cần quyền tạo bucket trong DATA_PROJECT_ID.

### Bước 2: Tạo key ring và CryptoKey

~~~bash
gcloud kms keyrings create "$KEY_RING" \
  --location="$LOCATION" \
  --project="$KEY_PROJECT_ID"

gcloud kms keys create "$KEY_NAME" \
  --location="$LOCATION" \
  --keyring="$KEY_RING" \
  --purpose=encryption \
  --protection-level=software \
  --project="$KEY_PROJECT_ID"
~~~

Tạo resource name của khóa để dùng trong cấu hình dịch vụ:

~~~bash
export KEY_RESOURCE="projects/$KEY_PROJECT_ID/locations/$LOCATION/keyRings/$KEY_RING/cryptoKeys/$KEY_NAME"
~~~

Ở ví dụ này, key material được Cloud KMS tạo và quản lý. Nếu yêu cầu sử dụng HSM hoặc khóa bên ngoài, hãy chọn protection level và quy trình tạo khóa tương ứng trước khi gắn khóa vào tài nguyên.

Có thể cấu hình lịch rotation tự động cho CryptoKey. Giá trị NEXT_ROTATION_TIME phải là thời điểm tương lai theo định dạng ISO 8601; hãy chọn mốc phù hợp với chính sách của tổ chức:

~~~bash
export NEXT_ROTATION_TIME="2026-12-01T00:00:00Z"

gcloud kms keys set-rotation-schedule "$KEY_NAME" \
  --location="$LOCATION" \
  --keyring="$KEY_RING" \
  --rotation-period=90d \
  --next-rotation-time="$NEXT_ROTATION_TIME" \
  --project="$KEY_PROJECT_ID"
~~~

### Bước 3: Cấp quyền cho Cloud Storage service agent

Cloud Storage sử dụng service agent của project chứa bucket để thực hiện mã hóa và giải mã. Dùng lệnh sau để lấy danh tính service agent và cấp quyền sử dụng CMEK:

~~~bash
gcloud storage service-agent \
  --project="$DATA_PROJECT_ID" \
  --authorize-cmek="$KEY_RESOURCE"
~~~

Lệnh này cấp quyền sử dụng khóa cho Cloud Storage service agent của DATA_PROJECT_ID. Nếu tự cấu hình IAM thay vì dùng lệnh trên, hãy xác định đúng service agent của project chứa bucket và gán roles/cloudkms.cryptoKeyEncrypterDecrypter trên đúng CryptoKey.

### Bước 4: Tạo bucket với khóa mặc định

~~~bash
gcloud storage buckets create "gs://$BUCKET_NAME" \
  --location="$LOCATION" \
  --default-encryption-key="$KEY_RESOURCE" \
  --project="$DATA_PROJECT_ID"
~~~

Bucket sử dụng CMEK làm khóa mặc định cho object được ghi sau khi cấu hình có hiệu lực. Bạn cũng có thể cập nhật bucket đã tồn tại bằng lệnh gcloud storage buckets update với cờ --default-encryption-key.

Để kiểm tra cấu hình khóa mặc định:

~~~bash
gcloud storage buckets describe "gs://$BUCKET_NAME" \
  --format="default(default_kms_key)"
~~~

Nếu cần dùng một khóa riêng cho một object, Cloud Storage cho phép chỉ định CMEK trong lệnh tải object lên bằng cờ --encryption-key. Khi bucket có khóa mặc định và yêu cầu ghi object chỉ định một khóa khác, khóa được chỉ định trong yêu cầu được ưu tiên cho object đó.

### Bước 5: Kiểm tra dữ liệu và phạm vi áp dụng

Tải thử một object, đọc lại object bằng danh tính có quyền truy cập bucket và kiểm tra metadata để xác nhận object dùng đúng key resource. Việc người dùng đọc object vẫn dựa trên IAM của Cloud Storage; người dùng không cần được cấp trực tiếp quyền giải mã Cloud KMS nếu service agent đã được cấp đúng quyền.

Thay đổi khóa mặc định của bucket không tự mã hóa lại các object đã tồn tại. Object cũ tiếp tục dùng khóa đã bảo vệ nó. Muốn chuyển dữ liệu cũ sang khóa mới, cần thực hiện rewrite object hoặc dùng Storage batch operations cho tập dữ liệu lớn.

## 6. Luân chuyển, thay thế và thu hồi khóa

### Luân chuyển key version

Khi Cloud KMS luân chuyển một CryptoKey, hệ thống tạo key version mới và đặt phiên bản đó làm primary theo lịch đã cấu hình. Những phiên bản cũ vẫn có thể cần thiết để giải mã DEK đã được bảo vệ trước đó.

Luân chuyển key version không đồng nghĩa dữ liệu cũ đã được mã hóa lại. Hành vi phụ thuộc vào dịch vụ:

- Với Cloud Storage, object được ghi mới sau khi key version mới trở thành primary sẽ dùng phiên bản mới khi bucket hoặc yêu cầu ghi sử dụng CryptoKey đó. Object cũ tiếp tục phụ thuộc vào phiên bản từng bảo vệ object.
- Với BigQuery, việc luân chuyển CryptoKey không mặc nhiên mã hóa lại các table đã tồn tại. Table có thể tiếp tục sử dụng key version gắn với table khi được tạo.
- Một số tích hợp có thể tự động re-wrap hoặc mã hóa lại DEK theo cách riêng. Cần xem tài liệu của đúng dịch vụ để biết thời gian và điều kiện hoàn tất.

Có thể cấu hình lịch rotation tự động hoặc tạo phiên bản mới theo quy trình thủ công. Lịch rotation giúp tạo key version mới đều đặn, nhưng không thay thế kế hoạch kiểm kê dữ liệu đang phụ thuộc vào các phiên bản cũ.

### Thay một CryptoKey bằng CryptoKey khác

Thay khóa là quá trình chuyển tài nguyên từ một CryptoKey sang một CryptoKey khác. Đây là thao tác khác với tạo phiên bản mới trong cùng một CryptoKey. Quy trình tổng quát:

1. Tạo khóa đích trong location phù hợp và xác nhận service agent có quyền sử dụng.
2. Cập nhật cấu hình mặc định hoặc cấu hình từng tài nguyên để dữ liệu ghi mới dùng khóa đích.
3. Liệt kê tài nguyên và dữ liệu đang dùng khóa cũ.
4. Thực hiện re-encrypt hoặc rewrite dữ liệu cũ theo hướng dẫn của dịch vụ.
5. Kiểm tra quyền đọc, tác vụ sao lưu, khôi phục và luồng xử lý dữ liệu sau khi chuyển.
6. Chỉ vô hiệu hóa phiên bản khóa cũ khi đã xác nhận không còn dữ liệu cần giải mã bằng phiên bản đó.

Không nên xóa khóa cũ chỉ vì đã thay cấu hình mặc định. Cấu hình mới có thể chỉ ảnh hưởng đến dữ liệu ghi mới, trong khi dữ liệu lịch sử vẫn phụ thuộc vào khóa cũ.

### Vô hiệu hóa hoặc phá hủy key version

Vô hiệu hóa key version chặn các thao tác mật mã cần phiên bản đó. Nếu cần, quản trị viên có thể bật lại phiên bản đã vô hiệu hóa. Phá hủy key version là hành động không thể đảo ngược sau khi quá trình phá hủy hoàn tất; dữ liệu phụ thuộc vào phiên bản đó có thể mất khả năng giải mã vĩnh viễn.

Trước khi vô hiệu hóa hoặc phá hủy, hãy kiểm kê toàn bộ tài nguyên và dữ liệu phụ thuộc vào phiên bản, bao gồm dữ liệu lưu trữ, snapshot, bản sao lưu và các workload ít được sử dụng. Với Cloud Storage, metadata object có trường kmsKeyName để hỗ trợ xác định khóa đã bảo vệ object. Chỉ thực hiện phá hủy khi chính sách lưu giữ, yêu cầu khôi phục và chủ sở hữu dữ liệu đã được kiểm tra.

Việc thu hồi quyền IAM của service agent cũng có thể làm dịch vụ không thể giải mã dữ liệu. Vì vậy, thay đổi IAM trên CryptoKey phải được xem là thay đổi có ảnh hưởng đến khả năng sẵn sàng của ứng dụng.

## 7. IAM, giám sát và độ tin cậy

### Áp dụng least privilege và separation of duties

- Chỉ cấp roles/cloudkms.cryptoKeyEncrypterDecrypter cho đúng service agent và đúng khóa cần dùng.
- Hạn chế số người có quyền tạo, thay đổi IAM, vô hiệu hóa hoặc phá hủy key version.
- Tách project chứa khóa khỏi project chứa workload khi cần phân tách trách nhiệm.
- Không cấp quyền KMS rộng cho người dùng ứng dụng nếu họ chỉ cần đọc hoặc ghi tài nguyên qua API của dịch vụ.
- Kiểm tra quyền kế thừa ở cấp project, folder và organization để tránh vô tình mở rộng phạm vi sử dụng khóa.

### Theo dõi hoạt động và tình trạng khóa

Khi vận hành CMEK, nên giám sát:

- Thay đổi IAM policy trên CryptoKey và thay đổi trạng thái key version.
- Các thao tác mã hóa, giải mã và lỗi truy cập khóa trong Cloud Audit Logs theo cấu hình audit phù hợp.
- Các tài nguyên đang sử dụng từng CryptoKey và key version.
- Key version sắp đến lịch rotation, bị vô hiệu hóa hoặc đang chờ phá hủy.
- Lỗi quota, độ trễ hoặc mất kết nối với Cloud EKM nếu dùng khóa bên ngoài.
- Khả năng đọc dữ liệu sau khi thay khóa, thay quyền hoặc triển khai lại workload.

Cloud KMS có dashboard và inventory hỗ trợ theo dõi mức độ sử dụng khóa và tài nguyên phụ thuộc. Hãy kết hợp dữ liệu này với log của dịch vụ lưu trữ, cơ sở dữ liệu và hệ thống giám sát workload.

### Đảm bảo khả năng truy cập dữ liệu

CMEK đưa trạng thái của khóa vào đường đi quan trọng của dữ liệu. Nếu khóa hoặc quyền của service agent không sẵn sàng, thao tác đọc hoặc ghi có thể thất bại. Với Cloud EKM, hệ thống khóa bên ngoài và đường kết nối tới hệ thống đó cũng trở thành một phần của độ tin cậy.

Một kế hoạch vận hành nên có:

- Người chịu trách nhiệm xử lý sự cố khóa và người có quyền khôi phục key version.
- Quy trình kiểm tra quyền của service agent sau khi tạo project hoặc bật dịch vụ mới.
- Cảnh báo trước thời điểm phá hủy và quy trình phê duyệt thay đổi vòng đời khóa.
- Kiểm thử khôi phục dữ liệu trong môi trường đại diện, bao gồm trường hợp khóa bị vô hiệu hóa rồi bật lại.
- Kế hoạch dự phòng cho kết nối, quota và phụ thuộc của Cloud EKM nếu được sử dụng.
- Danh sách tài nguyên và bản sao lưu phụ thuộc vào khóa để phục vụ kiểm toán và ứng phó sự cố.

## 8. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Tạo tài nguyên báo lỗi quyền Cloud KMS | Service agent chưa tồn tại hoặc chưa được cấp quyền trên CryptoKey | Xác định đúng service agent của project chứa tài nguyên; kiểm tra IAM policy của khóa |
| Báo location không tương thích | Key ring khác location hoặc không đáp ứng quy tắc multi-region/dual-region | Đối chiếu location của tài nguyên với quy tắc CMEK riêng của dịch vụ |
| Đọc dữ liệu thất bại dù người dùng có quyền trên bucket/table | Service agent mất quyền, key version bị vô hiệu hóa hoặc bị phá hủy | Kiểm tra quyền KMS, trạng thái key version và log của dịch vụ |
| Dữ liệu cũ vẫn hiển thị khóa trước khi rotation | Rotation chỉ tạo phiên bản mới; dữ liệu cũ chưa được re-encrypt | Kiểm tra metadata hoặc thông tin encryption của từng tài nguyên; thực hiện rewrite nếu cần |
| Cloud EKM trả lỗi hoặc thao tác chậm | Hệ thống khóa bên ngoài, kết nối, quota hoặc chính sách EKM gặp vấn đề | Kiểm tra trạng thái EKM connection, dịch vụ bên ngoài, network path và quota |
| Một phần dữ liệu của sản phẩm không dùng CMEK | CMEK chỉ hỗ trợ một số loại tài nguyên hoặc lớp dữ liệu | Kiểm tra bảng tích hợp và tài liệu cụ thể của tính năng đang sử dụng |

Khi xử lý lỗi, nên kiểm tra theo thứ tự: đúng CryptoKey resource name, đúng project và location, đúng service agent, IAM policy trên khóa, trạng thái key version, rồi mới mở rộng sang quota hoặc hệ thống EKM. Sau khi cấp quyền, có thể cần chờ thay đổi IAM lan truyền trước khi thử lại.

## 9. Chi phí và lựa chọn kiến trúc

Cloud KMS có chi phí liên quan đến số key version và thao tác mật mã. Cloud HSM và Cloud EKM còn có quota và chi phí vận hành riêng. Một thiết kế dùng khóa quá chi tiết có thể làm tăng số lượng key version cần quản lý; một thiết kế dùng khóa chung quá rộng có thể tăng phạm vi ảnh hưởng khi xảy ra sự cố.

Khi ước lượng chi phí và độ phức tạp, hãy tính đến:

- Số CryptoKey, số key version đang hoạt động và lịch rotation.
- Tần suất thao tác mã hóa, giải mã và giới hạn quota của protection level được chọn.
- Chi phí của Cloud HSM hoặc hệ thống quản lý khóa bên ngoài.
- Công việc re-encrypt dữ liệu lịch sử khi thay khóa.
- Thời gian lưu giữ key version cũ để bảo đảm khả năng đọc dữ liệu và khôi phục bản sao lưu.
- Nhân lực trực vận hành, kiểm toán IAM, theo dõi log và xử lý sự cố.

Không phải workload nào cũng cần CMEK. Nếu mục tiêu chỉ là mã hóa dữ liệu at rest, mã hóa mặc định của Google Cloud có thể đã đủ. Hãy chọn CMEK khi lợi ích kiểm soát vòng đời khóa, vị trí, quyền truy cập hoặc yêu cầu tuân thủ phù hợp với chi phí và trách nhiệm vận hành phát sinh.

## 10. Checklist trước khi đưa CMEK vào production

- [ ] Xác nhận đúng dịch vụ, loại tài nguyên và dữ liệu được CMEK bảo vệ.
- [ ] Chọn project quản lý khóa, location và mức protection level phù hợp.
- [ ] Quyết định phạm vi dùng chung hay riêng cho từng khóa.
- [ ] Tạo CryptoKey với purpose và thuật toán đối xứng được dịch vụ hỗ trợ.
- [ ] Xác định đúng service agent và cấp quyền KMS ở phạm vi nhỏ nhất.
- [ ] Cấu hình CMEK trên tài nguyên và xác minh dữ liệu ghi mới dùng đúng khóa.
- [ ] Kiểm tra dữ liệu hiện hữu có cần rewrite hoặc re-encrypt hay không.
- [ ] Thiết lập lịch rotation và xác định thời gian cần giữ các key version cũ.
- [ ] Có cảnh báo cho thay đổi IAM, trạng thái key version và lỗi sử dụng khóa.
- [ ] Thử nghiệm khôi phục dữ liệu và quy trình xử lý khi khóa không khả dụng.
- [ ] Kiểm kê các bản sao lưu, snapshot và workload phụ thuộc vào khóa trước khi phá hủy phiên bản.

## 11. Kết luận

CMEK giúp tổ chức chủ động kiểm soát khóa bảo vệ dữ liệu trên các dịch vụ Google Cloud đã tích hợp. Hiệu quả của CMEK phụ thuộc vào ba phần gắn chặt với nhau: thiết kế khóa và location phù hợp, cấp IAM chính xác cho service agent, và vận hành vòng đời khóa có kiểm soát. Khi triển khai, hãy bắt đầu từ loại dữ liệu cần bảo vệ, xác minh hỗ trợ của dịch vụ, thử nghiệm quy trình đọc/ghi và khôi phục, sau đó mới mở rộng cho workload production.

## Tài liệu tham khảo

- [Customer-managed encryption keys (CMEK) – Cloud KMS](https://docs.cloud.google.com/kms/docs/cmek)
- [Recommended practices for using CMEKs – Cloud KMS](https://docs.cloud.google.com/kms/docs/cmek-recommended-practices)
- [Use Cloud KMS keys in Google Cloud](https://docs.cloud.google.com/kms/docs/use-keys-google-cloud)
- [CMEK key rotation – Cloud KMS](https://docs.cloud.google.com/kms/docs/cmek-rotation)
- [Use customer-managed encryption keys – Cloud Storage](https://docs.cloud.google.com/storage/docs/encryption/using-customer-managed-keys)
- [Customer-managed Cloud KMS keys – BigQuery](https://docs.cloud.google.com/bigquery/docs/customer-managed-encryption)
- [Protect resources with Cloud KMS keys – Compute Engine](https://docs.cloud.google.com/compute/docs/disks/customer-managed-encryption)
- [Use customer-managed encryption keys – GKE](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/using-cmek)
