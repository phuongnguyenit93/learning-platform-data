# Cloud KMS key rings, keys và key versions

Cloud Key Management Service (Cloud KMS) quản lý vòng đời của khóa mật mã trong Google Cloud. Khi làm việc với Cloud KMS, cần phân biệt ba cấp tài nguyên: **key ring** dùng để nhóm các khóa, **CryptoKey** đại diện cho một khóa logic và các chính sách liên quan, còn **CryptoKeyVersion** chứa vật liệu khóa thực tế dùng cho thao tác mã hóa, giải mã hoặc ký.

Hiểu đúng ba cấp này giúp thiết kế quyền IAM, chọn vị trí lưu khóa, xoay vòng khóa và giữ dữ liệu cũ có thể giải mã được sau khi tạo phiên bản mới.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích quan hệ giữa project, location, key ring, CryptoKey và CryptoKeyVersion.
- Đọc resource ID đầy đủ của một key ring, key và key version.
- Phân biệt purpose, protection level và trạng thái của key version.
- Tạo key ring và khóa đối xứng bằng Google Cloud CLI.
- Giải thích primary version, rotation và lý do phải giữ phiên bản cũ khi dữ liệu vẫn cần giải mã.
- Chọn phạm vi IAM phù hợp cho quản trị viên và ứng dụng.

## 1. Mô hình tài nguyên của Cloud KMS

Các tài nguyên Cloud KMS nằm trong một Google Cloud project và được đặt tại một location. Có thể hình dung cấu trúc như sau:

~~~text
Organization
└── Folder
    └── Project
        └── Location
            └── Key ring
                └── CryptoKey
                    ├── CryptoKeyVersion 1
                    ├── CryptoKeyVersion 2
                    └── CryptoKeyVersion 3
~~~

Organization và folder là các cấp quản trị Google Cloud bao quanh project. Bên trong project, location xác định khu vực địa lý của tài nguyên Cloud KMS. Key ring, CryptoKey và CryptoKeyVersion là các cấp tài nguyên mật mã.

### Key ring: nhóm các khóa theo phạm vi quản trị

Key ring là một nhóm logic chứa các CryptoKey trong cùng một location. Key ring giúp tổ chức khóa theo môi trường, ứng dụng, nhóm dữ liệu hoặc yêu cầu phân quyền. Ví dụ, một project có thể có các key ring riêng cho **production**, **staging** và **analytics**.

Key ring không chứa vật liệu khóa và không trực tiếp thực hiện mã hóa. Nó tạo một cấp để quản lý nhóm khóa và cấp quyền IAM cho tất cả khóa trong nhóm. Tên key ring phải duy nhất trong một location; cùng tên có thể xuất hiện ở location khác. Bản thân key ring không phát sinh chi phí Cloud KMS.

### CryptoKey: định nghĩa khóa logic

CryptoKey là tài nguyên có tên, chứa metadata và một hoặc nhiều phiên bản khóa. Khi tạo CryptoKey, bạn xác định các thuộc tính quan trọng như:

- **Purpose:** loại thao tác mật mã mà khóa được phép thực hiện, chẳng hạn mã hóa/giải mã đối xứng, mã hóa bất đối xứng, ký bất đối xứng hoặc MAC.
- **Protection level:** môi trường bảo vệ vật liệu khóa, chẳng hạn phần mềm, HSM hoặc hệ thống quản lý khóa bên ngoài.
- **Rotation schedule:** lịch tạo phiên bản mới tự động, nếu loại khóa hỗ trợ.
- **IAM policy:** các principal được phép quản trị khóa hoặc sử dụng khóa cho thao tác mật mã.

Purpose và protection level không thể thay đổi sau khi CryptoKey được tạo. Các phiên bản thuộc cùng một CryptoKey dùng chung purpose.

CryptoKey là định danh ổn định mà ứng dụng và chính sách IAM thường tham chiếu. Vật liệu khóa thực tế nằm trong các CryptoKeyVersion bên dưới nó.

### CryptoKeyVersion: vật liệu khóa thực tế

Mỗi CryptoKeyVersion chứa một bộ vật liệu khóa dùng cho thao tác mật mã. Phiên bản được đánh số bắt đầu từ **1**; khi xoay vòng khóa, Cloud KMS tạo một phiên bản mới thay vì ghi đè vật liệu của phiên bản cũ.

Khi giải mã dữ liệu hoặc xác minh chữ ký, hệ thống phải dùng đúng phiên bản đã được dùng để mã hóa dữ liệu hoặc tạo chữ ký đó. Vì vậy, phiên bản cũ có thể vẫn cần thiết ngay cả khi phiên bản mới đã trở thành phiên bản chính.

Cloud KMS không cho principal xem hoặc xuất vật liệu khóa thô. Ứng dụng gửi yêu cầu đến Cloud KMS; dịch vụ thực hiện thao tác bằng vật liệu khóa thay cho ứng dụng.

## 2. Đọc resource ID đầy đủ

Resource ID thể hiện project, location và các cấp tài nguyên cha. Ví dụ:

~~~text
projects/PROJECT_ID/locations/LOCATION/keyRings/KEY_RING
projects/PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY_NAME
projects/PROJECT_ID/locations/LOCATION/keyRings/KEY_RING/cryptoKeys/KEY_NAME/cryptoKeyVersions/VERSION
~~~

| Tài nguyên | Phần cuối của resource ID | Ý nghĩa |
|---|---|---|
| Key ring | keyRings/KEY_RING | Nhóm khóa trong một location |
| CryptoKey | cryptoKeys/KEY_NAME | Khóa logic và metadata |
| CryptoKeyVersion | cryptoKeyVersions/VERSION | Một phiên bản vật liệu khóa cụ thể |

Ví dụ, phần **cryptoKeyVersions/3** chỉ rõ phiên bản số 3 của một CryptoKey. Khi xử lý sự cố hoặc kiểm tra log, hãy đối chiếu cả project, location, key ring, key và version; chỉ nhìn tên key có thể chưa đủ để xác định đúng tài nguyên.

## 3. Chọn location trước khi tạo key ring

Location là quyết định kiến trúc quan trọng. Cloud KMS hỗ trợ location theo vùng (regional), đa vùng (multi-regional) và location **global**. Location ảnh hưởng đến nơi vật liệu khóa được lưu trữ, yêu cầu lưu trú dữ liệu và độ trễ khi ứng dụng gọi Cloud KMS.

- **Regional:** phù hợp khi ứng dụng và dữ liệu tập trung ở một khu vực, hoặc khi có yêu cầu lưu trú dữ liệu theo vùng.
- **Multi-regional:** phù hợp khi yêu cầu dữ liệu được lưu trữ trên nhiều khu vực thuộc một multi-region được Google định nghĩa.
- **Global:** là một multi-region đặc biệt, có phạm vi trung tâm dữ liệu trên toàn cầu; không cho phép tự chọn từng trung tâm dữ liệu bên trong.

Hãy chọn location gần các tài nguyên sử dụng khóa và kiểm tra location đó có hỗ trợ protection level mong muốn hay không. Với CMEK, location của key thường cần tương thích với location của tài nguyên được bảo vệ. Với Cloud EKM, cần cân nhắc vị trí của hệ thống quản lý khóa bên ngoài.

**Không thể chuyển key ring hoặc key sang location khác sau khi tạo.** Nếu chọn sai location, phương án thường là tạo tài nguyên mới ở location phù hợp, chuyển ứng dụng và dữ liệu sang khóa mới theo một kế hoạch di trú có kiểm soát.

Các thao tác tạo hoặc cập nhật tài nguyên và metadata ở multi-region có thể chậm hơn single-region do yêu cầu đồng thuận giữa các trung tâm dữ liệu. Hãy đánh giá độ trễ, khả năng sẵn sàng và yêu cầu lưu trú dữ liệu thay vì mặc định rằng multi-region luôn tốt hơn.

## 4. Purpose và protection level

Hai thuộc tính này trả lời hai câu hỏi khác nhau: **khóa được dùng làm gì** và **vật liệu khóa được bảo vệ ở đâu**.

### Purpose

| Purpose thường gặp | Công dụng |
|---|---|
| Symmetric encrypt/decrypt | Cùng một khóa dùng để mã hóa và giải mã |
| Asymmetric encrypt/decrypt | Dùng public key để mã hóa và private key để giải mã |
| Asymmetric signing | Dùng private key để ký và public key để xác minh |
| MAC signing/verification | Tạo và xác minh mã xác thực thông điệp |

Chọn purpose theo giao thức và nhu cầu của ứng dụng. Không thể đổi purpose của CryptoKey sau khi tạo; nếu chọn sai, cần tạo key khác và chuyển ứng dụng sang key mới.

### Protection level

| Giá trị | Mô tả |
|---|---|
| SOFTWARE | Vật liệu khóa được bảo vệ bằng cơ chế phần mềm của Cloud KMS |
| HSM | Vật liệu khóa được bảo vệ bằng Cloud HSM dùng chung nhiều khách hàng |
| HSM_SINGLE_TENANT | Vật liệu khóa được bảo vệ bằng hạ tầng HSM dành riêng cho một khách hàng |
| EXTERNAL | Cloud KMS phối hợp với hệ thống External Key Manager (EKM) qua internet |
| EXTERNAL_VPC | Cloud KMS kết nối tới EKM qua VPC |

Khả năng hỗ trợ HSM và EKM khác nhau theo location. Protection level không thể thay đổi sau khi tạo key. Do đó, cần kiểm tra yêu cầu tuân thủ, mô hình vận hành và location trước khi tạo khóa.

## 5. Primary version và cách sử dụng phiên bản

Một CryptoKey có thể có nhiều phiên bản đang ở trạng thái enabled.

- Với **khóa mã hóa đối xứng**, một phiên bản được chọn làm **primary version**. Nếu yêu cầu mã hóa không chỉ rõ version, Cloud KMS dùng phiên bản primary.
- Với **khóa bất đối xứng**, không có primary version. Ứng dụng phải chỉ rõ version cần dùng trong thao tác.
- Các phiên bản enabled vẫn có thể được chỉ định trực tiếp khi thao tác phù hợp với purpose của khóa.

Ví dụ, khóa **payments-data-key** có hai phiên bản:

| Phiên bản | Vai trò | Trạng thái |
|---|---|---|
| 1 | Đã mã hóa dữ liệu trước đợt rotation | Enabled |
| 2 | Phiên bản primary cho dữ liệu mới | Enabled |

Ứng dụng có thể tiếp tục giải mã dữ liệu cũ bằng version **1**, trong khi yêu cầu mã hóa mới mặc định dùng version **2**. Việc đổi primary không tự động chuyển dữ liệu cũ sang version mới.

## 6. Vòng đời và trạng thái của key version

Cloud KMS quản lý trạng thái ở cấp CryptoKeyVersion. Key ring và CryptoKey không có trường state theo mô hình trạng thái của key version.

| State | Ý nghĩa | Có thể dùng cho thao tác mật mã? |
|---|---|---|
| PENDING_GENERATION | Phiên bản bất đối xứng đang được tạo | Không |
| PENDING_IMPORT | Phiên bản đang được nhập từ vật liệu khóa bên ngoài | Không |
| ENABLED | Phiên bản sẵn sàng sử dụng | Có |
| DISABLED | Vật liệu khóa vẫn tồn tại nhưng tạm thời không được sử dụng | Không |
| DESTROY_SCHEDULED | Đang chờ đến thời điểm hủy vật liệu khóa | Không |
| DESTROYED | Vật liệu khóa đã bị hủy | Không |
| IMPORT_FAILED | Quá trình nhập khóa thất bại | Không |

Một số điểm cần nhớ:

- Phiên bản đối xứng mới thường bắt đầu ở trạng thái **ENABLED**; phiên bản bất đối xứng bắt đầu ở **PENDING_GENERATION** và chuyển sang **ENABLED** khi tạo xong.
- Phiên bản bị **DISABLED** có thể được bật lại nếu vật liệu khóa vẫn còn.
- Phiên bản ở **DESTROY_SCHEDULED** không dùng được. Trong thời gian chờ hủy, có thể khôi phục phiên bản về trạng thái disabled theo quy trình của Cloud KMS.
- Khi đã ở **DESTROYED**, vật liệu khóa không còn được lưu trong Cloud KMS. Dữ liệu đã mã hóa bằng phiên bản đó sẽ không thể giải mã nếu không có bản sao vật liệu khóa hợp lệ ở nơi khác. Với khóa ký, không thể tạo chữ ký mới bằng private key đã hủy; việc xác minh chữ ký cũ phụ thuộc vào public key đã được lưu lại.

**Cảnh báo:** hủy một version vẫn đang được ứng dụng hoặc dịch vụ sử dụng có thể gây mất dữ liệu vĩnh viễn hoặc gián đoạn dịch vụ. Trước khi hủy, cần xác định mọi dữ liệu, bản sao lưu, ứng dụng và quy trình khôi phục còn phụ thuộc vào version đó.

## 7. IAM: cấp quyền đúng cấp tài nguyên

Bạn có thể quản lý quyền trên project, key ring hoặc CryptoKey. Không thể cấp IAM policy riêng cho từng CryptoKeyVersion.

| Cấp cấp quyền | Phạm vi ảnh hưởng |
|---|---|
| Project | Các key trong project |
| Key ring | Các key thuộc key ring |
| CryptoKey | Chỉ key được chọn và các version enabled của key đó |
| CryptoKeyVersion | Không hỗ trợ cấp quyền IAM độc lập |

Ví dụ, cấp quyền trên key ring **payments-prod** cho phép principal sử dụng các key trong key ring đó theo các permission được cấp. Nếu ứng dụng chỉ cần mã hóa/giải mã bằng một key, hãy cân nhắc cấp quyền ở cấp CryptoKey để giới hạn phạm vi.

Một số role thường gặp:

- **roles/cloudkms.admin:** quản trị tài nguyên Cloud KMS, bao gồm các quyền bảo trì và quản lý version nhạy cảm như hủy version. Chỉ cấp cho nhóm chịu trách nhiệm quản trị khóa.
- **roles/cloudkms.cryptoKeyEncrypter:** cho phép mã hóa bằng key trong phạm vi được cấp quyền.
- **roles/cloudkms.cryptoKeyDecrypter:** cho phép giải mã bằng key trong phạm vi được cấp quyền.
- **roles/cloudkms.cryptoKeyEncrypterDecrypter:** cho phép cả mã hóa và giải mã.

Nên tách vai trò quản trị khóa khỏi danh tính chạy ứng dụng. Ứng dụng chỉ nhận quyền mật mã cần thiết; nhóm quản trị khóa mới nhận quyền tạo, thay đổi cấu hình hoặc hủy version. Khi cần kiểm soát quyền khác nhau giữa hai ứng dụng, hãy cân nhắc tạo hai CryptoKey riêng thay vì dùng chung một key ring rồi cố phân quyền theo version.

## 8. Tạo key ring và khóa đối xứng bằng gcloud

Ví dụ sau tạo key ring và CryptoKey dùng cho mã hóa/giải mã đối xứng. Thay các giá trị placeholder bằng project, location và tên tài nguyên của môi trường thực tế.

### Bước 1: chọn project

~~~bash
gcloud config set project PROJECT_ID
~~~

### Bước 2: tạo key ring

~~~bash
gcloud kms keyrings create payments-prod \
  --location LOCATION
~~~

### Bước 3: tạo CryptoKey

~~~bash
gcloud kms keys create payments-data-key \
  --keyring payments-prod \
  --location LOCATION \
  --purpose encryption \
  --protection-level software
~~~

Lệnh trên tạo khóa phần mềm có purpose mã hóa. Nếu cần HSM hoặc EKM, hãy chọn protection level tương ứng và xác nhận location hỗ trợ loại khóa đó.

### Bước 4: xem thông tin key và các version

~~~bash
gcloud kms keys describe payments-data-key \
  --keyring payments-prod \
  --location LOCATION

gcloud kms keys versions list \
  --key payments-data-key \
  --keyring payments-prod \
  --location LOCATION
~~~

Kiểm tra version đầu tiên, trạng thái và primary state trước khi cấu hình ứng dụng. Để xem toàn bộ resource ID, có thể dùng định dạng đầu ra phù hợp của gcloud hoặc Cloud KMS API.

### Bước 5: tạo version mới và đặt làm primary

Với khóa mã hóa đối xứng, có thể tạo version mới và đặt nó làm primary trong cùng lệnh:

~~~bash
gcloud kms keys versions create \
  --key payments-data-key \
  --keyring payments-prod \
  --location LOCATION \
  --primary
~~~

Chỉ dùng cờ **--primary** cho key purpose **encryption**. Với khóa bất đối xứng, hãy tạo version rồi cập nhật ứng dụng để chỉ rõ version mới theo quy trình phát hành khóa của ứng dụng.

### Bước 6: cấu hình rotation tự động

Ví dụ đặt chu kỳ rotation là 90 ngày:

~~~bash
gcloud kms keys update payments-data-key \
  --keyring payments-prod \
  --location LOCATION \
  --rotation-period 90d
~~~

Chu kỳ 90 ngày chỉ là giá trị minh họa. Hãy chọn chu kỳ theo chính sách bảo mật, yêu cầu tuân thủ, mức độ nhạy cảm của dữ liệu và khả năng xử lý version cũ của ứng dụng. Cloud KMS không hỗ trợ automatic rotation cho khóa ký bất đối xứng hoặc khóa mã hóa bất đối xứng.

## 9. Rotation không đồng nghĩa với mã hóa lại dữ liệu

Rotation tạo version mới để bảo vệ dữ liệu mới. Với dữ liệu mà ứng dụng trực tiếp mã hóa bằng Cloud KMS, thao tác rotation **không tự giải mã rồi mã hóa lại ciphertext cũ**. Các version cũ vẫn cần tồn tại để giải mã dữ liệu đã được tạo bằng chúng.

Một quy trình rotation an toàn thường gồm:

1. Tạo version mới và xác nhận version ở trạng thái **ENABLED**.
2. Với khóa đối xứng, chuyển primary sang version mới hoặc để lịch automatic rotation thực hiện việc này.
3. Theo dõi ứng dụng và xác nhận các thao tác mã hóa mới sử dụng version mới.
4. Tiếp tục giữ các version cũ để giải mã dữ liệu hiện có.
5. Nếu cần loại bỏ phụ thuộc vào version cũ, thực hiện quy trình giải mã và mã hóa lại dữ liệu, sau đó xác minh dữ liệu, bản sao lưu và quy trình khôi phục.
6. Chỉ vô hiệu hóa hoặc lên lịch hủy version cũ sau khi đã xác nhận không còn phụ thuộc.

Đối với CMEK, dịch vụ Google Cloud tích hợp có thể xử lý rotation theo những cách khác nhau. Có dịch vụ tự mã hóa lại data encryption key (DEK), có dịch vụ chỉ dùng version mới cho dữ liệu mới. Hãy kiểm tra tài liệu của dịch vụ đang dùng trước khi lên lịch hủy version cũ.

Với khóa bất đối xứng dùng để ký, cần phân phối public key của version mới và cập nhật bên xác minh. Với khóa bất đối xứng dùng để mã hóa, bên gửi cần dùng public key mới; bên nhận vẫn cần private key của các version cũ để giải mã dữ liệu cũ.

## 10. Tình huống thực tế: quản lý khóa cho dữ liệu thanh toán

Một hệ thống thanh toán lưu dữ liệu nhạy cảm trong một dịch vụ Google Cloud hỗ trợ CMEK. Nhóm nền tảng tạo key ring **payments-prod** và CryptoKey **payments-data-key** trong location tương thích với dịch vụ lưu trữ.

Ban đầu, version **1** là primary. Sau một chu kỳ rotation, Cloud KMS tạo version **2** và version **2** trở thành primary. Dữ liệu mới được bảo vệ bằng version mới, trong khi dữ liệu cũ vẫn có thể phụ thuộc vào version **1**.

Nhóm vận hành cần xác minh cách dịch vụ lưu trữ xử lý DEK sau rotation. Nếu dịch vụ chưa mã hóa lại DEK cũ, version **1** vẫn phải được giữ enabled để đọc dữ liệu. Nhóm chỉ xem xét hủy version **1** sau khi có bằng chứng rằng dữ liệu, backup và quy trình phục hồi không còn cần version này.

Phân quyền cũng được chia theo trách nhiệm: service account của ứng dụng chỉ có quyền sử dụng CryptoKey cho thao tác cần thiết; nhóm quản trị khóa có quyền quản lý rotation và version. Nhờ vậy, một lỗi trong workload không tự động trao cho workload quyền thay đổi cấu hình hoặc hủy vật liệu khóa.

## 11. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chọn location mà không kiểm tra residency hoặc hỗ trợ HSM/EKM | Không đáp ứng yêu cầu dữ liệu hoặc không tạo được loại khóa cần thiết | Kiểm tra location và protection level trước khi tạo |
| Nghĩ rằng key ring chứa vật liệu khóa | Nhầm lẫn trách nhiệm của từng tài nguyên | Xem key ring là nhóm; vật liệu khóa nằm trong CryptoKeyVersion |
| Cố cấp IAM cho một version | Không thể biểu diễn quyền theo cách đó trong Cloud KMS | Tách thành các CryptoKey khác nhau nếu cần ranh giới quyền riêng |
| Rotation xong xóa version cũ ngay | Dữ liệu cũ có thể không giải mã được | Giữ version cũ cho đến khi hoàn tất di trú và kiểm chứng |
| Dùng automatic rotation cho khóa bất đối xứng | Cấu hình không được hỗ trợ | Thiết kế quy trình tạo version và phân phối public key thủ công |
| Cấp Cloud KMS Admin cho service account ứng dụng | Workload có thể nhận quyền quản trị quá rộng | Cấp role mã hóa/giải mã ở cấp key theo least privilege |

## 12. Checklist trước khi đưa key vào production

- [ ] Project và location đáp ứng yêu cầu tổ chức, lưu trú dữ liệu và độ trễ.
- [ ] Location hỗ trợ protection level đã chọn.
- [ ] Purpose và thuật toán phù hợp với thao tác của ứng dụng.
- [ ] Đã xác định CryptoKey nào được dùng chung và CryptoKey nào cần tách riêng.
- [ ] IAM được cấp ở cấp hẹp nhất có thể; service account không có quyền quản trị khóa nếu không cần.
- [ ] Có lịch rotation và người chịu trách nhiệm xử lý version mới.
- [ ] Ứng dụng có thể xác định version cần dùng khi giải mã hoặc xác minh chữ ký.
- [ ] Backup và quy trình khôi phục vẫn hoạt động khi version cũ bị vô hiệu hóa.
- [ ] Có bước xác minh trước khi đưa version vào trạng thái scheduled for destruction.

## Kết luận

Key ring giúp tổ chức và phân quyền theo nhóm; CryptoKey đại diện cho khóa logic và chính sách; CryptoKeyVersion chứa vật liệu khóa thực tế. Location, purpose và protection level là các quyết định cần chốt trước khi tạo key. Khi rotation, hãy nhớ rằng version mới phục vụ dữ liệu mới, còn version cũ có thể vẫn cần thiết để đọc dữ liệu đã tồn tại. Quy trình chỉ hoàn tất khi ứng dụng, dữ liệu, backup và IAM đều đã được kiểm chứng.

## Tài liệu tham khảo

- [Cloud KMS resources và resource hierarchy](https://docs.cloud.google.com/kms/docs/resource-hierarchy)
- [Cloud KMS locations](https://docs.cloud.google.com/kms/docs/locations)
- [Key version states](https://docs.cloud.google.com/kms/docs/key-states)
- [Cloud KMS permissions and roles](https://docs.cloud.google.com/kms/docs/reference/permissions-and-roles)
- [Create a key ring](https://docs.cloud.google.com/kms/docs/create-key-ring)
- [Create a key](https://docs.cloud.google.com/kms/docs/create-key)
- [Key rotation](https://docs.cloud.google.com/kms/docs/key-rotation)
- [CMEK key rotation](https://docs.cloud.google.com/kms/docs/cmek-rotation)

