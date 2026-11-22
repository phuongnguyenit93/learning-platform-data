# API signing keys, auth tokens và customer secret keys

Trong chương **Danh tính và phân quyền IAM** của module **CLOUD_PROVIDERS_ORACLE**, người học cần chọn đúng thông tin xác thực cho từng công cụ trước khi triển khai hoặc tự động hóa hạ tầng. OCI CLI gọi API quản trị, Docker truy cập Container Registry và công cụ sao lưu dùng giao thức S3 có thể cùng đại diện cho một IAM user nhưng sử dụng các loại credential khác nhau.

Bài này tập trung vào ba loại credential đó và cách vận hành chúng trong một môi trường OCI có giới hạn quyền. Những nguyên tắc bảo vệ, thay thế và thu hồi credential cũng cần được áp dụng cho pipeline triển khai Compute, VCN, lưu trữ và quy trình sao lưu cơ sở dữ liệu Oracle.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Chọn API signing key, auth token hoặc customer secret key theo API mà client sử dụng.
- Giải thích sự khác nhau giữa xác thực danh tính và quyền truy cập tài nguyên.
- Cấu hình một phép thử đọc dữ liệu với mỗi loại credential.
- Thiết kế quy trình thay khóa, thu hồi khi lộ bí mật và kiểm tra phạm vi ảnh hưởng.

## 1. Chọn credential từ giao thức của client

Trước khi tạo khóa, hãy xác định client gọi endpoint nào và hỗ trợ cơ chế xác thực nào. Không chọn credential chỉ vì giao diện ứng dụng có một ô mang tên `API key` hoặc `Password`.

| Loại credential | Client hoặc giao thức thường gặp | Thành phần bí mật cần bảo vệ | Cách sử dụng chính |
| --- | --- | --- | --- |
| API signing key | OCI CLI, OCI SDK, API OCI sử dụng request signing | Private key RSA | Ký yêu cầu; public key tương ứng được đăng ký với IAM user |
| Auth token | Docker truy cập OCI Container Registry; client Swift phù hợp | Chuỗi token do Oracle sinh | Cung cấp token theo cơ chế đăng nhập mà dịch vụ hỗ trợ |
| Customer secret key | Công cụ gọi Amazon S3 Compatibility API của Object Storage | Secret Key trong cặp Access Key/Secret Key | Dùng cặp khóa để tạo chữ ký theo giao thức S3 |

Oracle phân biệt các credential trên với mật khẩu Console, OAuth 2.0 client credentials và thông tin đăng nhập cơ sở dữ liệu. API signing key cũng khác khóa SSH dùng để đăng nhập Compute. Vì vậy, việc đổi credential phải dựa trên API đích và danh tính thực sự được sử dụng. Xem [Working with User Credentials](https://docs.oracle.com/en-us/iaas/Content/Identity/usercred/usercredentials.htm).

Ví dụ lựa chọn cho một nhóm vận hành:

| Nhu cầu | Lựa chọn cho tình huống này | Điểm phải làm rõ trước khi cấp |
| --- | --- | --- |
| Kỹ sư dùng OCI CLI từ máy quản trị | API signing key của user được phép thao tác | Compartment, môi trường và các thao tác cần thiết |
| Máy build cần tải một image riêng từ OCIR | Auth token của danh tính dành cho tác vụ đó | Repository và quyền pull |
| Phần mềm sao lưu chỉ hỗ trợ S3 | Customer secret key | Bucket, endpoint, region và thao tác đọc/ghi |

Nếu workload có cơ chế xác thực do nền tảng cung cấp phù hợp với dịch vụ đang gọi, cần đánh giá cơ chế đó trước khi phân phối bí mật lâu dài. Phần thực hành dưới đây giả định yêu cầu tích hợp thực sự cần một trong ba loại credential của user.

## 2. Credential chứng minh danh tính; IAM quyết định quyền

Một yêu cầu thành công cần nhiều điều kiện cùng đúng:

```text
Client gửi đúng endpoint và giao thức
        ↓
Credential hợp lệ xác thực được danh tính
        ↓
IAM cho phép thao tác trên tài nguyên đích
        ↓
Dịch vụ xử lý yêu cầu
```

Tạo credential không phải là cấp quyền vào mọi tài nguyên. User vẫn cần quyền phù hợp với dịch vụ. Với các credential gắn cùng một user, hãy đánh giá toàn bộ quyền mà user nhận được, thay vì coi tên mô tả của từng khóa là một ranh giới phân quyền. Tham khảo [User Credentials](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/usercredentials.htm).

Ví dụ, tạo hai API key với mô tả `dev` và `prod` dưới cùng một user không tự tách quyền hai môi trường. Nếu mục tiêu là giới hạn sự cố của môi trường thử nghiệm, thiết kế nên dùng danh tính và policy phù hợp với phạm vi đó.

Trong ví dụ của bài, quản trị viên chuẩn bị trước bucket `iam-credentials-lab`, một object không nhạy cảm và một nhóm chỉ đọc. Policy minh họa dùng OCID để tránh nhầm các nhóm trùng tên giữa identity domain:

```text
Allow group id ocid1.group.oc1..REPLACE_GROUP_OCID to read objects in compartment id ocid1.compartment.oc1..REPLACE_COMPARTMENT_OCID where target.bucket.name = 'iam-credentials-lab'
```

Thay hai OCID bằng giá trị thật và bảo đảm user thuộc đúng nhóm. Policy này minh họa quyền đọc object trong bucket đã biết; nó không cấp quyền tạo bucket hay quản lý Compute. Nếu một công cụ còn cần liệt kê bucket, phải đánh giá thêm quyền tương ứng thay vì mở toàn bộ `object-family`. Xem [các mẫu policy Object Storage](https://docs.oracle.com/en-us/iaas/Content/Identity/policiescommon/commonpolicies.htm).

## 3. API signing keys: ký yêu cầu OCI bằng khóa bất đối xứng

### 3.1. Public key, private key và fingerprint

Đối với API signing, OCI yêu cầu cặp khóa RSA dạng PEM với độ dài tối thiểu 2048 bit. Public key được thêm vào hồ sơ IAM user; private key được client giữ để ký. Fingerprint giúp nhận diện public key đã đăng ký. Cặp khóa dùng cho API phải được quản lý riêng với khóa SSH vào máy ảo. Xem [Required Keys and OCIDs](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm).

Phân biệt các giá trị khi bàn giao cấu hình:

| Giá trị | Vai trò | Cách xử lý |
| --- | --- | --- |
| User OCID | Xác định user gọi API | Kiểm tra đúng user và identity domain |
| Tenancy OCID | Xác định tenancy | Tránh sao chép nhầm cấu hình môi trường |
| Fingerprint | Nhận diện public key | Đối chiếu với khóa trên hồ sơ user |
| Public key | Phần đăng ký tại OCI | Có thể cung cấp cho người quản trị đăng ký |
| Private key | Tạo chữ ký | Chỉ cấp cho tiến trình hoặc người được phép sử dụng |

OCID và fingerprint không thay thế được private key. Tuy nhiên, vẫn nên chia sẻ chúng theo nhu cầu công việc vì cấu hình còn thể hiện cấu trúc và danh tính của hệ thống.

### 3.2. Chữ ký gắn với nội dung yêu cầu

OCI request signing sử dụng RSA-SHA256. Client tạo signing string từ các thành phần yêu cầu, rồi đưa chữ ký vào header `Authorization` theo cơ chế `Signature`. Với GET không có body, những thành phần tối thiểu gồm `(request-target)`, `host` và `date` hoặc `x-date`.

Đổi đường dẫn, thứ tự query sau khi ký, hoặc để đồng hồ client lệch quá năm phút có thể làm xác thực thất bại. Các phương thức có body còn có yêu cầu header bổ sung và ngoại lệ theo API, vì vậy thực hành thông thường nên để OCI SDK/CLI thực hiện việc ký. Xem [Request Signatures](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/signingrequests.htm).

### 3.3. Chuẩn bị và cấu hình profile

Quy trình cho người học:

1. Mở hồ sơ đúng user trong Console và tìm phần API keys hoặc Tokens and keys tương ứng.
2. Tạo cặp khóa hoặc đăng ký public key của cặp đã tạo.
3. Lưu private key tại vị trí chỉ tài khoản chạy client được đọc.
4. Lấy cấu hình gợi ý, kiểm tra lại user, tenancy và fingerprint.
5. Dùng một profile riêng cho bài thực hành để giảm nhầm lẫn môi trường.

Ví dụ trong file cấu hình OCI của người dùng:

```ini
[ORACLE_LAB]
user=ocid1.user.oc1..REPLACE_USER_OCID
fingerprint=REPLACE_PUBLIC_KEY_FINGERPRINT
tenancy=ocid1.tenancy.oc1..REPLACE_TENANCY_OCID
region=ap-singapore-1
key_file=C:/Users/REPLACE_LOCAL_USER/.oci/oracle_lab_api_key.pem
```

Trên Windows PowerShell, vị trí mặc định của file config là `$Env:UserProfile\.oci\config`; trên Linux và macOS thường là `~/.oci/config`. Sửa `key_file` theo đường dẫn thật của máy chạy client. Nếu private key có passphrase, cung cấp qua cơ chế runtime được client hỗ trợ; tránh lưu passphrase cạnh private key trong cấu hình. Các trường và cơ chế profile được mô tả tại [SDK and CLI Configuration File](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm).

Không đưa private key vào source code, image container, thư mục đồng bộ chia sẻ hoặc nội dung ticket. Trên Windows, kiểm tra ACL của file; trên hệ điều hành kiểu Unix, giới hạn quyền đọc file cho tài khoản cần dùng. Kiểm tra cả bản sao trong thư mục tải xuống sau khi tạo khóa bằng trình duyệt.

### 3.4. Thử bằng thao tác chỉ đọc

Giả định OCI CLI đã được cài, profile đã đúng và bucket mẫu nằm tại Singapore. Lệnh sau dành cho terminal của người học; thay namespace bằng giá trị của tenancy:

```powershell
oci os object list --profile ORACLE_LAB --namespace-name 'REPLACE_NAMESPACE' --bucket-name 'iam-credentials-lab' --limit 5
```

Kết quả mong đợi là phản hồi liệt kê object, có thể là danh sách rỗng nếu bucket chưa có dữ liệu. Bằng chứng nên giữ lại gồm thời điểm, profile, bucket và mã yêu cầu nếu có. Không dùng việc tạo tài nguyên mới làm phép thử đầu tiên cho credential đọc dữ liệu.

Nếu kết quả thất bại, kiểm tra user OCID, fingerprint, private key và endpoint trước. Sau khi xác thực hoạt động, mới đối chiếu policy với thao tác cụ thể. Không mở quyền quản trị tenancy để che một lỗi đường dẫn file khóa.

## 4. Auth tokens: bí mật cho cơ chế đăng nhập mà dịch vụ hỗ trợ

### 4.1. Hiểu đúng từ “token”

Auth token là chuỗi Oracle tạo cho những tích hợp được hỗ trợ, chẳng hạn Swift. Nó có cách quản lý riêng với API signing key. Khi lập hồ sơ tích hợp, nên ghi rõ tên loại credential thay vì chỉ ghi “token”, vì nhóm vận hành có thể đang nói về các cơ chế hoàn toàn khác nhau. Xem [Security Credentials](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/credentials.htm).

Ví dụ một thông tin bàn giao đủ rõ:

```text
Tác vụ: tải image phiên bản đã được duyệt
Dịch vụ: OCI Container Registry
Danh tính: user dành cho tác vụ pull
Credential: OCI auth token
Phạm vi: repository của ứng dụng trong compartment thử nghiệm
Nơi cấp bí mật cho runtime: kho bí mật được nhóm quản trị phê duyệt
```

Không chép giá trị token vào tài liệu bàn giao này. Người nhận cần biết cách lấy bí mật qua kênh được kiểm soát và biết ai chịu trách nhiệm thay token.

### 4.2. Ví dụ đăng nhập Container Registry

Trong phần Auth Tokens của hồ sơ user, tạo token và lưu ngay vào nơi bảo vệ bí mật. Giá trị token chỉ hiển thị khi tạo. Với OCIR, tên đăng nhập thường có dạng `<namespace>/<username>`; một số cấu hình liên kết danh tính dùng `<namespace>/<domain-name>/<username>`. Lấy đúng dạng cho tenancy và user của bạn theo [Pushing Images Using the Docker CLI](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrypushingimagesusingthedockercli.htm).

Ví dụ dùng region Singapore:

```powershell
docker login ocir.ap-singapore-1.oci.oraclecloud.com
```

Tại prompt, nhập username theo cấu hình ở trên và dùng auth token ở ô password. Sau đó thử pull một image riêng đã có sẵn và được phép truy cập:

```powershell
docker pull ocir.ap-singapore-1.oci.oraclecloud.com/REPLACE_NAMESPACE/team/demo:lab
```

Đăng nhập thành công chưa chứng minh user có quyền pull mọi repository. Đối với tác vụ chỉ pull, quản trị viên có thể thiết kế policy `read repos` trong compartment phù hợp. Quyền push cần tập quyền khác, vì vậy không nên mặc định cấp `manage repos` chỉ để tải image. Xem [Policies to Control Repository Access](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registrypolicyrepoaccess.htm).

Với CI, chuyển token từ kho bí mật vào client bằng cơ chế tránh ghi bí mật vào tham số dòng lệnh và log; Docker hỗ trợ nhận password qua standard input. Máy runner cũng phải kiểm soát nơi Docker lưu thông tin đăng nhập. Không coi việc che một biến trong giao diện CI là đủ nếu script vẫn in toàn bộ môi trường.

Khi kết thúc buổi thực hành, có thể xóa thông tin đăng nhập của Docker trên máy:

```powershell
docker logout ocir.ap-singapore-1.oci.oraclecloud.com
```

Lệnh này dọn trạng thái client. Nếu token phải ngừng có hiệu lực, thực hiện thu hồi token tại OCI và kiểm tra lại bằng một lần đăng nhập mới.

## 5. Customer secret keys: cặp khóa cho S3 Compatibility API

### 5.1. Access Key và Secret Key

Customer secret key phục vụ Amazon S3 Compatibility API của OCI Object Storage. Cần cung cấp cả Access Key lẫn Secret Key cho client S3. Access Key nhận diện credential, còn Secret Key là phần bí mật để tạo chữ ký; không nhầm chúng với khóa mã hóa dữ liệu của Vault.

Trong một hồ sơ kết nối, hãy đặt tên rõ ràng:

| Trường của client S3 | Giá trị cần lấy từ OCI |
| --- | --- |
| Access key ID | Access Key của customer secret key |
| Secret access key | Secret Key tương ứng |
| Endpoint | Endpoint S3 compatibility của Object Storage |
| Region | Region của bucket đích |
| Bucket | Tên bucket cần truy cập |

Secret Key không thể được đọc lại sau khi tạo. Nếu mất giá trị này, lập kế hoạch thay credential và cập nhật client, thay vì tìm cách suy ra nó từ Access Key. Xem [Object Storage Amazon S3 Compatibility API](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/s3compatibleapi.htm).

### 5.2. Thử bằng AWS CLI với endpoint OCI

Ví dụ này giả định bạn đã có AWS CLI, bucket mẫu và cặp customer secret key của đúng user. AWS CLI là client dùng giao thức S3 trong tình huống này; dữ liệu đích vẫn nằm ở OCI.

Tạo profile riêng bằng cơ chế nhập tương tác:

```powershell
aws configure --profile OCI_S3_LAB
```

Khi được hỏi, nhập Access Key và Secret Key vừa tạo; chọn region `ap-singapore-1`, output `json`. Việc cấu hình này lưu credential cục bộ, nên giới hạn quyền đọc file credentials và không đưa file vào repository.

Chọn cách đặt bucket trong đường dẫn cho ví dụ:

```powershell
aws configure set s3.addressing_style path --profile OCI_S3_LAB
```

Sau đó liệt kê tối đa năm object:

```powershell
aws --profile OCI_S3_LAB --region ap-singapore-1 --endpoint-url 'https://REPLACE_NAMESPACE.compat.objectstorage.ap-singapore-1.oci.customer-oci.com' s3api list-objects-v2 --bucket 'iam-credentials-lab' --max-keys 5
```

Đây là mẫu endpoint path-style công khai được Oracle mô tả. Với realm hoặc cấu hình endpoint khác, dùng endpoint chính thức tương ứng. Giữ region dùng để ký nhất quán với region đích; Amazon S3 Compatibility API không hỗ trợ Signature Version 2. Tham khảo [cấu hình ứng dụng S3 compatibility](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/s3compatibleapi.htm).

Chỉ kiểm tra một bucket đã biết trong bài thực hành. Nếu đưa cùng cấu hình vào công cụ sao lưu thật, phải bổ sung thử nghiệm theo chức năng cần dùng: ghi object mới, đọc phục hồi, xử lý multipart và các yêu cầu tương thích của sản phẩm. Không suy ra toàn bộ quy trình sao lưu hoạt động chỉ từ một lần liệt kê thành công.

## 6. Vận hành vòng đời credential

### 6.1. Ghi nhận chủ sở hữu và nơi sử dụng

Nên có một bản kiểm kê không chứa bí mật cho từng credential:

| Thuộc tính | Ví dụ dữ liệu kiểm kê |
| --- | --- |
| Danh tính | User của tác vụ sao lưu thử nghiệm |
| Loại credential | Customer secret key |
| Dấu nhận diện | Access Key hoặc fingerprint theo loại |
| Người phụ trách | Nhóm quản trị sao lưu |
| Client đang dùng | Runner dự phòng và runner chính |
| Phạm vi dự kiến | Bucket thử nghiệm trong compartment đã duyệt |
| Mốc vận hành | Ngày tạo, ngày thay dự kiến, lần kiểm tra gần nhất |
| Kịch bản thu hồi | Người thực hiện, nơi cập nhật cấu hình và phép thử sau thu hồi |

Danh sách client phải bao gồm tác vụ ít chạy: phục hồi dữ liệu, job cuối tháng và máy dự phòng. Các client này dễ bị bỏ sót khi thay khóa vì hệ thống chính vẫn hoạt động bình thường.

Oracle nêu giới hạn tối đa đồng thời là ba API keys, hai auth tokens và hai customer secret keys cho mỗi user. Auth tokens và customer secret keys không tự hết hạn; nhóm vận hành cần chủ động lập lịch thay và thu hồi chúng. Các thao tác quản lý credential cho user khác cũng yêu cầu quyền thích hợp, không chỉ quyền trên compartment dữ liệu. Xem [Managing User Credentials](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingcredentials.htm).

### 6.2. Thay khóa có thời gian chuyển tiếp

Tình huống minh họa: một phần mềm sao lưu chạy trên hai runner và cần đổi customer secret key. Mục tiêu vận hành là cả hai runner tiếp tục hoàn thành job trong quá trình chuyển đổi.

1. **Lập danh sách nơi đang dùng khóa cũ.** Kiểm tra cả runner chính, runner dự phòng và tác vụ khôi phục thử.
2. **Chuẩn bị một vị trí credential còn trống.** Nếu đã dùng hết giới hạn, phải xác định credential nào thật sự có thể bỏ trước khi tạo thêm.
3. **Tạo credential mới.** Lưu bí mật qua kênh được kiểm soát và ghi dấu nhận diện vào bản kiểm kê.
4. **Cập nhật một client thử nghiệm.** Kiểm tra đọc/ghi trong phạm vi mà job cần, không mở thêm quyền để làm phép thử thành công.
5. **Chuyển các client còn lại.** Theo dõi một chu kỳ vận hành phù hợp với tần suất job và mục tiêu sẵn sàng.
6. **Thu hồi credential cũ tại OCI.** Không chỉ xóa biến khỏi giao diện CI.
7. **Chạy yêu cầu mới với credential cũ.** Kết quả mong đợi là bị từ chối; dùng kết nối mới để tránh hiểu sai trạng thái cache hoặc phiên cũ.
8. **Xác minh credential mới và dọn bản sao.** Kiểm tra job, tài liệu vận hành, runner dự phòng và nơi lưu tạm.

Đây là phương án chuyển đổi đề xuất cho tình huống trên. Độ dài giai đoạn theo dõi phải dựa trên lịch chạy thực tế. Một khoảng quan sát vài phút không đủ đại diện cho job chỉ chạy mỗi tuần.

Nếu credential đã bị lộ, ưu tiên thu hồi nhanh để hạn chế truy cập trái phép; có thể phải chấp nhận gián đoạn thay vì giữ khóa cũ hoạt động trong giai đoạn chuyển tiếp. Chuẩn bị trước phương án thay khẩn cấp giúp giảm thời gian gián đoạn này.

### 6.3. Xử lý bí mật bị đưa vào repository hoặc log

Không chờ việc xóa đoạn log hoặc sửa commit để coi sự cố đã xong. Thực hiện theo thứ tự vận hành phù hợp:

1. Xác định đúng loại credential, user liên quan và phạm vi quyền hiện có.
2. Thu hồi credential bị lộ và đưa credential thay thế vào các client cần duy trì.
3. Kiểm tra hoạt động bất thường bằng Audit cho sự kiện được hỗ trợ, log dịch vụ và log của pipeline liên quan.
4. Đối chiếu tài nguyên hoặc dữ liệu có thể bị tác động, bao gồm chi phí phát sinh và thay đổi ảnh hưởng tính sẵn sàng.
5. Loại bỏ các bản sao khỏi nơi lưu không phù hợp, xử lý lịch sử theo quy trình của nhóm và bổ sung biện pháp phòng ngừa.

Bằng chứng sự cố nên chứa thời gian, danh tính, fingerprint hoặc Access Key cần nhận diện, tài nguyên đích và request ID. Không đính kèm private key, Secret Key, auth token hay toàn bộ header xác thực. Những khuyến nghị bảo vệ credential của OCI được trình bày trong [IAM Credentials](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-IAM_Credentials.htm).

## 7. Chẩn đoán lỗi theo lớp

Bảng sau dùng để định hướng kiểm tra. Một thông báo lỗi chưa đủ để kết luận nguyên nhân duy nhất.

| Biểu hiện | Kiểm tra trước | Bước tiếp theo |
| --- | --- | --- |
| Không đọc được private key hoặc lỗi passphrase cục bộ | Đường dẫn, định dạng, quyền đọc và cơ chế nhập passphrase | Sửa cấu hình client trước khi kiểm tra IAM |
| API OCI trả `NotAuthenticated` | User OCID, fingerprint, cặp khóa, đồng hồ và nội dung request được ký | Đối chiếu yêu cầu mới với cấu hình đã biết hoạt động |
| Docker login thất bại | Registry domain, namespace, dạng username và auth token | Tạo phép thử đăng nhập mới, tránh dùng trạng thái đăng nhập cũ |
| Docker login được nhưng pull image thất bại | Image/tag có tồn tại, repository đích và quyền pull | Kiểm tra policy trên compartment chứa repository |
| Client S3 báo `SignatureDoesNotMatch` | Access Key/Secret Key có cùng cặp; endpoint, region và cấu hình ký | Kiểm tra thay đổi request qua proxy hoặc cấu hình client |
| Truy cập object bị từ chối | Đúng bucket, đúng region, user, nhóm và policy | Đối chiếu quyền với API đang gọi; tài nguyên đích cũng có thể bị chỉ sai |
| Sau thay khóa chỉ một số job lỗi | Runner, secret version và lịch chạy thực tế | Tìm client còn dùng khóa cũ hoặc cấu hình chưa được nạp lại |

Khi hỗ trợ từ xa, yêu cầu thông tin nhận diện đã loại bỏ bí mật. Nếu phải bật log chi tiết của client, kiểm soát quyền đọc log và xem lại nội dung trước khi chia sẻ. Không dùng việc in credential ra màn hình làm phép thử xác thực.

## 8. Bài thực hành tổng hợp

### Điều kiện chuẩn bị

Quản trị viên chuẩn bị một môi trường thử nghiệm gồm:

- Bucket `iam-credentials-lab` tại một region đã chọn, chứa object mẫu không nhạy cảm.
- Repository riêng đã có image thử nghiệm để kiểm tra auth token.
- Danh tính và policy chỉ đủ quyền cho từng phép thử.
- OCI CLI, Docker và một client S3 phù hợp trên máy người học.

Các lệnh trong bài minh họa Singapore. Nếu dùng region khác, cập nhật đồng bộ profile, endpoint và tên registry. Mỗi credential chỉ được lưu trong vị trí bảo vệ bí mật đã chọn.

### Trình tự thực hiện

1. Với API signing key, dùng profile riêng để liệt kê object trong bucket mẫu.
2. Với auth token, đăng nhập OCIR rồi pull image đã được cấp quyền.
3. Với customer secret key, dùng client S3 liệt kê chính bucket mẫu qua endpoint compatibility.
4. Ghi kết quả theo mẫu dưới đây và giữ bí mật ở ngoài báo cáo.
5. Thực hiện thay một credential theo quy trình chuyển tiếp, rồi kiểm tra credential cũ bằng yêu cầu mới sau khi thu hồi.
6. Dọn profile và thông tin đăng nhập cục bộ không còn cần, đồng thời thu hồi credential chỉ tạo cho bài thực hành.

| Phép thử | Bằng chứng cần ghi | Tiêu chí đạt |
| --- | --- | --- |
| OCI API đọc object | Profile, bucket, thời điểm và kết quả | Đọc được phạm vi đã cấp |
| OCIR pull image | Registry, repository, tag và kết quả | Pull được image mẫu |
| S3 compatibility | Endpoint, region, bucket và kết quả | Client S3 nhận phản hồi hợp lệ |
| Thu hồi credential cũ | Dấu nhận diện và thời điểm thử mới | Credential cũ không xác thực được |
| Duy trì sau thay khóa | Client đã cập nhật và chu kỳ job đã kiểm tra | Credential mới phục vụ đúng tác vụ |

Không đánh dấu bài thực hành đạt chỉ vì đã tạo đủ ba loại credential. Kết quả cần thể hiện client sử dụng đúng loại, truy cập đúng tài nguyên, và credential có thể được thay hoặc thu hồi mà nhóm vận hành biết rõ ảnh hưởng.

## 9. Những điểm cần ghi nhớ

- Bắt đầu từ API và cơ chế xác thực của client trước khi cấp credential.
- Giữ private key, auth token và Secret Key trong kênh bảo vệ bí mật; cấu hình nhận diện phải trỏ đúng môi trường.
- Thiết kế danh tính và IAM policy theo tác vụ để giới hạn phạm vi ảnh hưởng.
- Quản lý đầy đủ nơi dùng credential, kể cả job dự phòng và khôi phục ít chạy.
- Kiểm tra thay thế và thu hồi bằng yêu cầu mới, đồng thời xác minh tác vụ cần duy trì vẫn hoạt động.
