# SSH key vaulting

## Mục tiêu bài học

SSH key vaulting là việc đưa khóa SSH, đặc biệt là private key có thể mở quyền quản trị, vào một cơ chế quản lý bí mật tập trung với quyền sở hữu, chính sách sử dụng, quy trình luân chuyển và bằng chứng kiểm toán rõ ràng.

Trong phạm vi Privileged Access Management, mục tiêu không chỉ là cất khóa trong một kho mã hóa. Hệ thống phải trả lời được: ai được dùng khóa, dùng vào máy nào, bằng tài khoản nào, trong khoảng thời gian nào, có được lấy private key ra ngoài hay không và thu hồi quyền bằng cách nào.

Sau bài học, bạn có thể:

- Phân biệt quản lý secret trong vault với kiểm soát quyền đăng nhập tại máy Linux.
- Chọn cách cấp quyền phù hợp cho người quản trị và workload tự động.
- Thiết kế inventory, policy và bằng chứng cho một SSH key đặc quyền.
- Thực hiện rotation có kiểm thử, tránh tự khóa đường quản trị.
- Giải thích vì sao checkout hết hạn hoặc xóa secret chưa đủ để vô hiệu hóa một khóa đã bị sao chép.

Tên chương Linux PAM ở đây nằm trong module quản lý truy cập đặc quyền. Bài học không hướng dẫn cấu hình thư viện Linux-PAM, tức Pluggable Authentication Modules; đó là một lớp tích hợp xác thực khác.

## 1. Vấn đề cần giải quyết

Một nhóm vận hành dùng khóa `prod-admin` để đăng nhập nhiều máy Linux. Private key nằm trên laptop của vài quản trị viên, trong biến bí mật CI và trong một thư mục sao lưu. Public key được thêm vào nhiều tài khoản trên nhiều máy nhưng không có danh sách đầy đủ.

Khi một thành viên chuyển công việc, nhóm xóa quyền của người đó trong hệ thống quản lý danh tính. Tuy nhiên, bản private key họ đã tải về vẫn có thể xác thực ở những máy tiếp tục chấp nhận public key tương ứng.

Có ba vấn đề độc lập:

1. Không biết private key đang tồn tại ở đâu.
2. Không biết chính xác máy và tài khoản nào tin cậy public key.
3. Không có đường nối đáng tin cậy giữa người yêu cầu, lần sử dụng và hành động trên máy đích.

Đưa private key vào vault giải quyết được một phần của vấn đề thứ nhất. Muốn quản trị truy cập đặc quyền đầy đủ, tổ chức còn phải kiểm soát phân phối, điểm xác thực SSH, quyền sau đăng nhập và khả năng quan sát phiên.

Một bản ghi vault không tự biến một khóa dùng chung thành danh tính cá nhân. Nếu năm người cùng lấy một private key và đăng nhập tài khoản `ops`, máy đích chủ yếu nhìn thấy tài khoản `ops` cùng khóa xác thực. Muốn quy trách nhiệm, cần bổ sung danh tính người yêu cầu, giao dịch cấp quyền và phiên liên quan; việc hạn chế người dùng tiếp xúc private key thường giúp giảm khoảng trống này.

## 2. Những đối tượng phải phân biệt

| Đối tượng | Vai trò | Ý nghĩa với PAM |
|---|---|---|
| Private key của người dùng hoặc workload | Chứng minh bên kết nối có quyền dùng danh tính SSH | Là secret cần bảo vệ, hạn chế xuất và có kế hoạch thay thế |
| Public key tương ứng | Được phía máy đích chấp nhận theo cấu hình xác thực | Không phải secret, nhưng thay đổi trái phép có thể tạo cửa vào |
| Fingerprint | Dấu định danh rút gọn của khóa | Dùng để đối chiếu inventory và bằng chứng; không thay thế việc quản lý khóa |
| Host key của máy chủ | Giúp client xác thực máy chủ SSH | Cần một luồng quản lý tin cậy riêng, không nhầm với khóa đăng nhập |
| Passphrase của private key | Bảo vệ file private key khi lưu trữ | Không vô hiệu hóa quyền của khóa trên máy đích |
| SSH certificate | Liên kết public key với thuộc tính được CA ký | Có thể hỗ trợ quyền ngắn hạn, nhưng cần quản trị CA và chính sách phía đích |
| Tài khoản Linux và quyền sudo | Quyết định quyền thực thi sau xác thực | Vaulting không tự áp dụng least privilege cho tài khoản |

Không đăng private key, passphrase hoặc token vault vào ticket để “lưu bằng chứng”. Bằng chứng phù hợp là secret ID, phiên bản, fingerprint, request ID và kết quả kiểm tra đã loại bỏ dữ liệu bí mật.

Public key có thể được phân phối rộng hơn private key, nhưng không được coi mọi thao tác trên public key là vô hại. Một thay đổi trong nguồn cấp public key có thể cấp thêm quyền truy cập, vì vậy vẫn cần kiểm soát thay đổi và xác nhận trạng thái thực tế.

## 3. Ranh giới bảo vệ của vault

### 3.1 Vault bảo vệ việc giữ và cấp secret

Một thiết kế vault hợp lý có thể cung cấp:

- Mã hóa secret khi lưu trữ và bảo vệ kênh truy cập.
- Xác thực người dùng hoặc workload trước khi truy xuất.
- Policy giới hạn đọc secret, quản lý phiên bản và sửa metadata.
- Nhật ký về thao tác truy cập, phê duyệt, rotation và thay đổi policy.
- Tích hợp với broker hoặc connector để sử dụng khóa mà không phát file cho người dùng.

Những khả năng này phụ thuộc sản phẩm, cấu hình và cách triển khai. Không nên mặc định rằng một hệ thống mang tên vault đã có đầy đủ checkout, dual approval, session recording hay rotation cho mọi nền tảng.

### 3.2 Vault không thay thế máy đích

Máy đích vẫn là nơi quyết định có chấp nhận việc xác thực bằng khóa hay không. Sau đó, tài khoản, nhóm, sudo và các cơ chế kiểm soát khác quyết định người dùng thực hiện được điều gì.

Nếu private key đã bị sao chép ra ngoài, các thao tác sau không tự thay đổi quyết định xác thực tại máy đích:

- Thu hồi token đọc vault của người dùng.
- Xóa mục secret trong vault.
- Đổi passphrase của bản private key đang lưu trong vault.
- Đặt thời gian checkout về 0.
- Đổi tên secret hoặc gắn nhãn “revoked” trong inventory.

Để vô hiệu hóa khóa bị lộ, phải cập nhật những nơi thực sự chấp nhận khóa đó, hoặc áp dụng cơ chế thu hồi tương ứng đã được triển khai. Phải xác minh kết quả ở các máy và tài khoản liên quan.

### 3.3 Khóa đăng nhập và quyền sau đăng nhập

Khóa dùng để vào tài khoản `deploy` không nên đồng thời mở tài khoản `root` trên toàn bộ production. Tách khóa theo môi trường và mục đích giúp giới hạn phạm vi ảnh hưởng.

Tuy nhiên, tách khóa chưa đủ nếu `deploy` được phép chạy mọi lệnh bằng sudo mà không có giới hạn. Thiết kế cần nối được chuỗi:

```text
Danh tính yêu cầu
  → quyền dùng secret
  → đường kết nối được phép
  → tài khoản trên máy đích
  → quyền thực thi của tài khoản
  → bằng chứng sử dụng
```

Một mắt xích được quản lý tốt không bù được cho việc các mắt xích khác để mở.

## 4. Chọn mô hình sử dụng khóa

### 4.1 Checkout private key

Vault phát private key cho client hoặc runner được phép. Cách này thường dễ tích hợp với hệ thống cũ nhưng người hoặc tiến trình nhận khóa có khả năng giữ lại bản sao.

Nếu lựa chọn checkout, cần ghi rõ:

- Ai được tải private key và lý do cần chức năng này.
- Khóa được lưu tạm ở đâu và tiến trình nào được đọc.
- Checkout kết thúc thì dọn file, thu hồi quyền hay rotation theo cơ chế nào.
- Bản sao ngoài vault được phát hiện và xử lý thế nào.
- Tài khoản hoặc máy nào vẫn chấp nhận khóa sau khi thời gian checkout hết hạn.

Thời gian checkout là một chính sách trong hệ thống cấp secret. Với một public key tĩnh vẫn còn được chấp nhận, thời gian này không tự trở thành hạn dùng của khóa SSH.

### 4.2 Kết nối qua broker hoặc proxy

Người quản trị xác thực với hệ thống PAM. Broker lấy hoặc sử dụng khóa để mở kết nối tới máy đích, sau đó gắn hoạt động với người yêu cầu.

Mô hình này có thể giảm việc phát private key ra máy trạm. Tuy nhiên, cần kiểm tra kiến trúc thật: broker có kết thúc kết nối SSH hay chỉ chuyển tiếp lưu lượng, khóa nằm ở thành phần nào và sự kiện nào được ghi nhận.

Một SSH jump host thông thường không tự trở thành hệ thống PAM có ghi hình phiên. Không nên suy ra khả năng theo dõi lệnh chỉ từ việc lưu lượng đi qua một máy trung gian.

Broker cũng trở thành thành phần nhạy cảm: quản trị viên của broker, tài khoản dịch vụ, bản sao lưu và cơ chế phục hồi của nó đều phải nằm trong phạm vi kiểm soát.

### 4.3 Agent hoặc dịch vụ ký

Một số thiết kế cho phép client yêu cầu thao tác ký mà không nhận file private key. Lợi ích là giảm việc phân phối vật liệu khóa, nhưng khả năng yêu cầu ký vẫn là một quyền nhạy cảm.

Cần xác định tiến trình nào được sử dụng giao diện ký, yêu cầu nào cần phê duyệt và quyền được chấm dứt ra sao. “Không đọc được file private key” không đồng nghĩa “không thể sử dụng danh tính SSH”.

### 4.4 SSH certificate ngắn hạn

Một lựa chọn khác là dùng khóa của người dùng hoặc workload và cấp certificate ngắn hạn theo policy. Đây là một thiết kế cấp danh tính khác với việc cho thuê bản sao của private key tĩnh.

Phải bảo vệ khóa CA, kiểm soát danh tính được ký, phạm vi đích và thời hạn. Việc certificate hết hạn chủ yếu liên quan tới xác thực mới; không nên coi đó là thao tác tự ngắt mọi phiên đã tồn tại.

| Nhu cầu | Lựa chọn có thể xem xét | Điểm phải kiểm chứng |
|---|---|---|
| Hệ thống cũ chỉ nhận khóa tĩnh | Vault cùng quy trình rotation | Kiểm kê đầy đủ nơi chấp nhận public key |
| Quản trị tương tác cần quy trách nhiệm | Broker có tích hợp danh tính | Liên kết người dùng, tài khoản đích và phiên |
| Tự động hóa không cần con người tải khóa | Workload identity cùng connector hoặc cơ chế cấp ngắn hạn | Tránh bootstrap bằng một secret dùng chung lâu dài |
| Nhiều máy đích cần quyền ngắn hạn | SSH certificate | Chính sách CA, trust phía đích và xử lý thu hồi |

Không có một mô hình tối ưu cho mọi môi trường. Quyết định cần dựa vào khả năng máy đích, yêu cầu kiểm toán, mức chấp nhận bản sao private key và năng lực vận hành.

## 5. Inventory: biết khóa nào đang mở quyền gì

Trước khi import hàng loạt private key vào vault, lập inventory theo quan hệ nhiều-nhiều giữa khóa, tài khoản và tài nguyên.

Một bản ghi tối thiểu nên có:

| Thuộc tính | Ví dụ minh họa |
|---|---|
| Key ID nội bộ | `ssh-prod-app-deploy-01` |
| Fingerprint public key | Giá trị SHA-256 thu được từ công cụ kiểm tra |
| Owner nghiệp vụ | Nhóm vận hành ứng dụng |
| Owner kỹ thuật | Nhóm platform |
| Loại chủ thể sử dụng | Workload triển khai |
| Môi trường | Production |
| Tài khoản đích | `deploy` |
| Danh sách đích hoặc nhóm đích | Nhóm máy ứng dụng đã được kiểm chứng |
| Nguồn cấp public key | Công cụ cấu hình và vị trí quản lý tương ứng |
| Đường dùng khóa | Connector của pipeline |
| Secret ID và phiên bản | Tham chiếu vault, không chứa private key |
| Ngày kiểm chứng gần nhất | Thời điểm đối chiếu trạng thái thật |
| Phương án thu hồi | Gỡ khóa và xác minh trên toàn bộ đích |

Không dùng trường comment trong public key làm bằng chứng duy nhất về chủ sở hữu. Comment là thông tin mô tả, có thể thay đổi hoặc sao chép. Inventory phải nối fingerprint với owner đã được xác nhận.

Phải tìm cả những nơi cấp quyền ngoài file `authorized_keys` thông thường nếu hệ thống có sử dụng: vị trí được cấu hình khác, dịch vụ tra cứu khóa, công cụ cấu hình hoặc cơ chế certificate. Một lần tìm trong một thư mục không chứng minh đã kiểm kê hết.

Một khóa có nhiều owner không rõ trách nhiệm thường là dấu hiệu cần tách khóa. Nếu chưa thể tách ngay, chỉ định một owner chịu trách nhiệm rotation, thêm danh sách consumer và thời hạn xử lý.

## 6. Onboarding khóa vào vault

### Bước 1: Xác nhận mục đích và phạm vi

Ghi lại khóa phục vụ người quản trị hay workload, tài khoản đích nào cần dùng và quyền thực thi nào thật sự cần thiết. Không import một khóa quá rộng rồi mặc định rằng đặt nó trong vault đã làm giảm quyền.

Với khóa không rõ nguồn gốc hoặc không kiểm soát được các bản sao, ưu tiên lập kế hoạch thay thế. Không coi việc import là bằng chứng khóa chưa từng bị lộ.

### Bước 2: Đối chiếu cặp khóa

Xác nhận public key tương ứng với private key và đối chiếu fingerprint với inventory. Việc kiểm tra nên diễn ra trên môi trường được kiểm soát, không gửi private key tới công cụ kiểm tra trực tuyến.

Không đưa nội dung private key vào command line, log debug hoặc một script được commit. Nếu công cụ import cần secret đầu vào, chọn kênh mà hệ thống hỗ trợ cho dữ liệu nhạy cảm và kiểm tra chính sách log của kênh đó.

### Bước 3: Lưu secret và metadata

Lưu private key vào vùng phù hợp với môi trường và độ nhạy. Tách quyền sử dụng khóa với quyền sửa policy, sửa owner hoặc quản lý kho.

Nếu private key có passphrase, xác định thành phần nào được cấp quyền mở khóa. Khi cùng một chủ thể có thể lấy cả private key và passphrase qua cùng một policy, không nên tính đó là hai lớp kiểm soát độc lập đối với chính chủ thể ấy.

### Bước 4: Thiết lập đường sử dụng

Chọn checkout, broker, connector hoặc cơ chế ký. Cấu hình đường mạng và quyền tại máy đích để phản ánh lựa chọn đó.

Nếu bắt buộc đi qua broker nhưng máy đích vẫn cho phép dùng cùng khóa trực tiếp từ mạng người dùng, người giữ bản sao có thể bỏ qua đường quan sát dự kiến. Chính sách phải được thực thi ở các lớp liên quan, không chỉ mô tả trong tài liệu.

### Bước 5: Kiểm thử tích cực và tiêu cực

Kiểm thử một yêu cầu hợp lệ thành công, một danh tính không được phép bị từ chối, một tài nguyên ngoài phạm vi bị từ chối và việc thay đổi policy được ghi nhận.

Sau onboarding, phải biết chính xác cơ chế thu hồi khi khóa bị lộ. Nếu chưa mô tả được hành động ở máy đích, việc onboarding mới hoàn thành phần lưu trữ.

## 7. Policy truy cập: người dùng và workload

Ví dụ dưới đây là mô hình policy để thảo luận thiết kế, không phải cú pháp của một sản phẩm vault cụ thể.

```yaml
policy_id: ssh-production-app-maintenance
subjects:
  group: app-operations
targets:
  environment: production
  host_group: app-linux
  account: pamops
access:
  mode: broker
  export_private_key: false
  request_duration_minutes: 30
approval:
  ticket_required: true
  independent_approver: true
authentication:
  mfa_required_for_human: true
evidence:
  request_id: required
  session_id: required
  key_version: required
```

Phải phân biệt mong muốn trong policy với khả năng của hệ thống. Chẳng hạn, `export_private_key: false` chỉ có ý nghĩa khi giao diện, API và quyền quản trị đều được thiết kế để thực thi yêu cầu đó.

Với người dùng tương tác:

- Xác thực bằng danh tính cá nhân.
- Gắn lý do và phạm vi công việc với yêu cầu.
- Dùng phê duyệt độc lập khi mức rủi ro yêu cầu.
- Giới hạn cửa sổ sử dụng và đường kết nối.
- Liên kết phiên với người dùng ngay cả khi tài khoản Linux đích dùng chung.

Với workload:

- Nhận diện workload bằng cơ chế phù hợp môi trường chạy.
- Giới hạn job, môi trường, tài nguyên và hành động.
- Tránh dùng tài khoản người để giải quyết nhu cầu của dịch vụ.
- Chặn việc đưa secret vào artifact, cache và log của pipeline.
- Có owner và quy trình rotation không phụ thuộc một cá nhân.

Không nên thêm MFA tương tác vào mỗi lần chạy tự động rồi để nhóm vận hành dùng chung tài khoản nhằm vượt qua nó. Chính sách cho workload phải được thiết kế riêng, đồng thời vẫn có kiểm soát thay đổi và truy vết.

## 8. Thực hành trong môi trường lab

Phần này chỉ dùng khóa và tài khoản lab. Không chạy với khóa production hoặc tự thêm public key vào hệ thống nằm ngoài phạm vi được giao.

### 8.1 Tạo cặp khóa lab và nhận diện fingerprint

Ví dụ tạo thư mục riêng, sinh khóa Ed25519 và đọc fingerprint public key:

```bash
umask 077
lab_dir="$(mktemp -d)"

ssh-keygen   -t ed25519   -a 100   -f "$lab_dir/id_pam_lab"   -C "pam-training-ssh-vault"

ssh-keygen -lf "$lab_dir/id_pam_lab.pub" -E sha256
```

Công cụ sẽ hỏi passphrase; không đặt passphrase thật trực tiếp trong tham số lệnh. Tùy chọn `-a` điều chỉnh chi phí dẫn xuất khi lưu private key được bảo vệ bằng passphrase. Cần chọn loại khóa theo khả năng tương thích và chính sách mật mã của môi trường. Xem [tài liệu ssh-keygen của OpenSSH](https://man.openbsd.org/ssh-keygen).

Kết quả cần ghi vào hồ sơ lab là fingerprint và vị trí tham chiếu secret. Không ghi nội dung file private key vào báo cáo.

### 8.2 Import và cấp quyền

Dùng luồng import đã được phê duyệt của vault trong lab. Tạo metadata owner, tài khoản đích và secret version. Nếu lab dùng checkout, đặt quyền đọc cho đúng danh tính thử nghiệm; nếu dùng broker, cấp quyền kết nối thay vì mặc định cấp quyền đọc secret.

Đưa public key vào nguồn cấp quyền của tài khoản lab theo cơ chế quản lý cấu hình đang sử dụng. Tài khoản này chỉ nên có quyền cần cho bài thử.

Đồng thời chuẩn bị dữ liệu host key đã được xác minh. Việc tin một user key không thay thế việc xác thực máy chủ.

### 8.3 Kiểm thử với đúng khóa được cấp

Giả sử connector đã cung cấp đường dẫn private key lab qua `PAM_KEY_FILE`, và `PAM_KNOWN_HOSTS_FILE` chỉ tới dữ liệu host key đã kiểm chứng:

```bash
ssh -F /dev/null   -i "$PAM_KEY_FILE"   -o IdentitiesOnly=yes   -o IdentityAgent=none   -o ForwardAgent=no   -o StrictHostKeyChecking=yes   -o UserKnownHostsFile="$PAM_KNOWN_HOSTS_FILE"   -o ControlMaster=no   -o ControlPath=none   pamops@app-01.lab.example
```

Đây là lệnh kiểm thử theo mô hình checkout, không phải hướng dẫn kết nối của mọi broker. Các tùy chọn giúp chọn identity rõ ràng, không dùng agent và tránh tái sử dụng kết nối multiplex trong bài thử. Kiểm tra phiên bản client và cấu hình thích hợp trước khi áp dụng. Xem [tài liệu ssh_config của OpenSSH](https://man.openbsd.org/ssh_config).

Không xử lý lỗi host key bằng cách tắt kiểm tra máy chủ. Xác minh tên đích, hồ sơ tin cậy và thay đổi host key qua kênh quản trị phù hợp.

### 8.4 Kiểm thử từ chối và kết thúc

Thử dùng danh tính không được cấp quyền để xin cùng secret hoặc cùng phiên; yêu cầu phải bị từ chối và có sự kiện tương ứng.

Khi kết thúc checkout, thực hiện dọn file tạm theo quy trình của môi trường, thu hồi phiên cấp secret và kiểm tra kết quả. Việc xóa file tạm không chứng minh không còn bản sao hoặc không thể phục hồi dữ liệu từ môi trường lưu trữ.

Nếu bài lab yêu cầu chứng minh khóa hết quyền, phải gỡ quyền ở điểm xác thực và thử một kết nối mới bằng khóa cũ. Không chỉ kiểm tra giao diện vault hiển thị “expired”.

## 9. Rotation có kiểm soát

Rotation là thay cặp khóa cùng các điểm chấp nhận khóa và consumer liên quan. Đổi passphrase hoặc đổi tên secret không phải thay cặp khóa.

Một quy trình thực tế gồm các trạng thái sau:

```text
A: Khóa cũ đang hoạt động
  → B: Sinh khóa mới và lưu phiên bản mới
  → C: Thêm public key mới vào các đích đã kiểm kê
  → D: Kiểm thử kết nối mới bằng đúng khóa mới
  → E: Chuyển consumer sang phiên bản mới
  → F: Gỡ public key cũ ở toàn bộ điểm chấp nhận
  → G: Kiểm thử khóa cũ bị từ chối, đóng giao dịch
```

### 9.1 Chuẩn bị trước khi đổi

Xác nhận danh sách máy đích, tài khoản, workload và lịch chạy. Đối với một job mỗi tháng mới chạy, một lần triển khai thành công hôm nay chưa chứng minh job đó đã chuyển khóa.

Chuẩn bị đường phục hồi được quản lý độc lập, có kiểm thử và có giới hạn. Không tạo thêm một private key bí mật nằm ngoài inventory để phòng sự cố.

Xác định rõ tiêu chí thành công, thời hạn tồn tại đồng thời hai khóa và người quyết định xử lý máy chưa cập nhật.

### 9.2 Kiểm thử khóa mới

Đảm bảo kết nối thử thật sự sử dụng khóa mới. Một kết nối đã mở trước đó, một identity khác trong agent hoặc cơ chế dự phòng có thể khiến bài thử thành công dù khóa mới chưa dùng được.

Đối chiếu danh tính, tài khoản, máy đích và fingerprint hoặc version liên quan trong bằng chứng. Chạy một thao tác đọc ít rủi ro để xác nhận tài khoản có quyền cần thiết, không mặc định đăng nhập thành công nghĩa là tác vụ nghiệp vụ sẽ thành công.

### 9.3 Cắt bỏ khóa cũ

Sau khi consumer đã chuyển, gỡ khóa cũ khỏi các nơi cấp quyền. Kiểm tra xem công cụ cấu hình có tự đưa khóa cũ trở lại ở lần đồng bộ tiếp theo hay không.

Nếu một máy offline chưa xác minh được, ghi nhận máy đó là ngoại lệ còn mở. Không báo rotation hoàn tất chỉ vì phần lớn máy đã đổi.

Với rotation định kỳ, có thể cho phép thời gian chuyển tiếp đã kiểm soát. Với khóa nghi bị lộ, cần cân bằng yêu cầu ngắt quyền nhanh và khả năng duy trì dịch vụ; không áp dụng máy móc một khoảng overlap dài.

### 9.4 Rollback không làm sống lại bí mật bị lộ

Nếu khóa mới lỗi vì sai tài khoản đích hoặc permission, sửa nguyên nhân và dùng đường phục hồi đã chuẩn bị. Không tự động bật lại khóa cũ khi khóa đó đang bị nghi ngờ lộ.

Versioning trong vault giúp quản lý lịch sử và khôi phục theo chính sách, nhưng đồng thời có thể giữ lại vật liệu khóa cũ. Quyền truy cập lịch sử phải được giới hạn; khôi phục metadata không được làm khôi phục quyền xác thực ngoài ý muốn.

## 10. Thu hồi: phải nói rõ đang thu hồi điều gì

| Hành động | Điều được thay đổi | Điều chưa được chứng minh |
|---|---|---|
| Thu hồi quyền đọc vault | Chủ thể không thể xin secret qua quyền đó | Bản sao đã tải không còn dùng được |
| Kết thúc checkout | Giao dịch cấp secret kết thúc theo hệ thống | Khóa tĩnh đã mất quyền tại máy đích |
| Đổi passphrase | Cách mở bản private key được cập nhật | Bản private key cũ đã sao chép bị vô hiệu |
| Gỡ public key ở một tài khoản | Điểm chấp nhận tại tài khoản đó thay đổi | Mọi tài khoản hoặc nguồn cấp quyền khác đã được xử lý |
| Thu hồi theo cơ chế certificate hoặc danh sách thu hồi | Quy tắc xác thực mới tại nơi đã áp dụng thay đổi | Tất cả máy đích đã nhận và thực thi thay đổi |
| Đóng phiên đang chạy | Phiên cụ thể chấm dứt | Khả năng mở phiên mới đã bị chặn |

Quy trình thu hồi hoàn chỉnh phải kiểm tra hai câu hỏi riêng:

1. Chủ thể có còn mở được kết nối mới không?
2. Các phiên đã tồn tại có còn tiếp tục hoạt động không?

Với một khóa tĩnh có nhiều bản sao, thường không thể vô hiệu riêng bản sao của một người mà vẫn giữ nguyên cùng cặp khóa cho mọi người khác. Đây là lý do cần hạn chế chia sẻ khóa, ưu tiên quy trách nhiệm theo danh tính và có kế hoạch thay thế khi xảy ra lộ lọt.

Nếu chủ thể còn quyền sudo rộng hoặc đã tạo cơ chế truy cập bổ sung, việc gỡ một public key chưa đủ để kết luận hệ thống sạch. Phạm vi ứng phó phải dựa vào quyền đã có và dấu hiệu hoạt động.

## 11. Bằng chứng và giám sát

Một chuỗi bằng chứng hữu ích nối được yêu cầu với việc sử dụng:

```text
Người hoặc workload
  ↔ yêu cầu và phê duyệt
  ↔ secret ID + version + fingerprint
  ↔ phiên hoặc lần kết nối
  ↔ host + tài khoản đích
  ↔ kết quả thực hiện và kết thúc
```

Ví dụ sự kiện đã loại bỏ bí mật:

```json
{
  "event_type": "ssh_access_started",
  "request_id": "REQ-LAB-204",
  "actor_id": "user-ops-17",
  "approval_ref": "APPROVAL-LAB-51",
  "secret_id": "ssh-prod-app-deploy-01",
  "secret_version": "v12",
  "key_fingerprint_ref": "inventory-fingerprint-v12",
  "target_host": "app-01.lab.example",
  "target_account": "pamops",
  "session_id": "SESSION-LAB-902",
  "access_mode": "broker",
  "result": "allowed"
}
```

Đây là schema minh họa. Không phải mọi hệ thống sẽ cung cấp toàn bộ trường, và giá trị do client tự khai chưa chắc là bằng chứng đáng tin. Cần xác định hệ thống nào phát sự kiện, đồng bộ thời gian và cách bảo vệ log khỏi bị sửa bởi người đang được kiểm toán.

Sự kiện đọc secret chỉ chứng minh secret đã được truy xuất theo ghi nhận của vault. Nó không chứng minh khóa đã được dùng, không cho biết toàn bộ lệnh đã chạy và không loại trừ việc dùng bản sao trước đó.

Các tình huống đáng theo dõi gồm:

- Tăng mạnh số lần đọc private key hoặc tải nhiều phiên bản cũ.
- Khóa được dùng ngoài máy, tài khoản hoặc thời gian dự kiến.
- Truy cập trực tiếp trong khi policy yêu cầu broker.
- Khóa cũ vẫn được chấp nhận sau thời điểm rotation đã tuyên bố hoàn tất.
- Thay đổi owner, policy hoặc nguồn cấp public key không có giao dịch hợp lệ.
- Dùng khóa đặc quyền từ workload không thuộc inventory.

Cần gắn ngưỡng cảnh báo với cách vận hành thật. Một job triển khai có nhiều kết nối ngắn là mẫu bình thường khác với quản trị tương tác.

Bằng chứng phiên có thể chứa dữ liệu nhạy cảm. Quyền xem, xuất và thời gian giữ phải phù hợp mục đích kiểm toán; không biến kho log thành nơi phát tán secret thứ hai.

## 12. Ứng phó khi nghi private key bị lộ

Giả sử một pipeline ghi private key vào artifact. Các bước cần phối hợp:

1. Xác định fingerprint, phiên bản, môi trường và phạm vi tài khoản đích của khóa.
2. Giữ bằng chứng cần thiết bằng kênh xử lý sự cố, tránh sao chép secret vào nhiều ticket.
3. Ngăn tiếp tục cấp khóa từ vault và hạn chế actor hoặc workload liên quan.
4. Cập nhật các điểm chấp nhận khóa để chặn xác thực mới, theo mức khẩn cấp của sự cố.
5. Rà soát và xử lý các phiên đang chạy theo quy trình ứng phó.
6. Cấp khóa thay thế qua đường tin cậy và chuyển consumer.
7. Kiểm chứng khóa cũ bị từ chối ở toàn bộ phạm vi, kể cả nguồn cấu hình có thể tái cấp khóa.
8. Đánh giá hoạt động đã thực hiện, quyền leo thang và secret khác có khả năng bị truy cập.
9. Xử lý artifact, cache và chính sách retention phù hợp, đồng thời giữ bằng chứng được phê duyệt.

Không chỉ xóa artifact rồi đóng sự cố. Secret có thể đã được tải xuống; việc không còn tìm thấy file không chứng minh chưa ai sao chép.

Cũng không nên chỉ đổi token vault. Token bảo vệ lần truy xuất tiếp theo, còn private key đã lộ là một thông tin xác thực có vòng đời riêng.

## 13. Vận hành khi thành phần gặp sự cố

### Vault không khả dụng

Định nghĩa trước hành vi khi vault không truy cập được: yêu cầu mới có bị từ chối, broker có phiên đang chạy, workload nào chịu ảnh hưởng và đường phục hồi được kiểm soát ở đâu.

Không xử lý sự cố bằng cách phát một private key quản trị chung qua chat. Nếu cần break-glass, cơ chế đó phải có owner, điều kiện kích hoạt, bằng chứng sử dụng và hành động xử lý credential sau đó.

### Rotation chỉ thành công một phần

Duy trì trạng thái theo từng đích và consumer. Một kết quả “success” ở connector không thay thế xác minh trên tất cả tài nguyên.

Dùng các trạng thái rõ ràng như `new-key-installed`, `new-key-tested`, `consumer-switched`, `old-key-removed` và `old-key-rejected`. Các tên này mô tả bằng chứng đạt được, không chỉ diễn tả ý định.

### Quyền của máy lưu key hoặc runner quá rộng

Quyền file chặt giúp giảm truy cập cục bộ ngoài ý muốn, nhưng không bảo vệ khóa khỏi mọi tiến trình chạy cùng danh tính hoặc người có đặc quyền trên máy đó.

Vì vậy, một runner dùng chung cho mã không tin cậy không nên nhận khóa production chỉ vì file đã đặt mode hạn chế. Cần kiểm soát nơi chạy, nguồn mã, danh tính workload và khả năng phát tán đầu ra.

### Sao lưu và phục hồi

Sao lưu của vault, broker và hệ thống cấu hình có thể chứa secret hoặc làm sống lại trạng thái cấp quyền cũ. Phục hồi cần đối chiếu với danh sách khóa đã thu hồi và kế hoạch rotation.

Bài thử khôi phục phải xác nhận không tái kích hoạt một khóa đã bị loại bỏ. Khả năng phục hồi dữ liệu và tính đúng của quyền truy cập là hai tiêu chí cần kiểm tra riêng.

## 14. Bài tập thiết kế và tiêu chí nghiệm thu

Một nhóm có 12 máy ứng dụng, hai pipeline và sáu quản trị viên. Hiện tại mọi bên dùng cùng một private key để vào tài khoản `ops`. Yêu cầu mới là quản trị viên phải có phê duyệt, pipeline chỉ truy cập nhóm máy ứng dụng, và khóa bị lộ phải có quy trình thu hồi kiểm chứng được.

Hãy đề xuất:

- Cách tách khóa hoặc mô hình cấp danh tính cho người và workload.
- Inventory thể hiện đầy đủ máy đích, tài khoản, owner và consumer.
- Cách tránh phát private key cho người nếu hạ tầng hỗ trợ.
- Một quy trình chuyển đổi không làm gián đoạn cả hai pipeline.
- Bằng chứng xác nhận khóa dùng chung cũ đã hết quyền.

Một phương án tốt không nhất thiết dùng cùng công nghệ cho mọi chủ thể. Có thể dùng broker cho người và một đường cấp credential phù hợp cho workload, miễn cả hai được giới hạn quyền và truy vết.

Tiêu chí nghiệm thu nên thể hiện kết quả có thể quan sát:

| Kiểm tra | Kết quả mong đợi |
|---|---|
| Người không có quyền xin truy cập | Bị từ chối; có actor và lý do trong log |
| Người đã được phê duyệt dùng đúng đích | Kết nối được; liên kết được yêu cầu với phiên |
| Pipeline xin quyền tới môi trường ngoài phạm vi | Bị từ chối |
| Rotation hoàn tất | Consumer dùng phiên bản mới; khóa cũ bị từ chối ở các đích |
| Một máy chưa nhận thay đổi | Được ghi rõ là ngoại lệ; chưa đóng giao dịch rotation |
| Khóa bị lộ bị thu hồi | Chặn được kết nối mới; xử lý phiên hiện hữu theo quyết định ứng phó |
| Thu thập log và artifact | Không chứa private key, passphrase hoặc token vault |

Không nghiệm thu chỉ bằng ảnh chụp secret đã nằm trong vault. Mục tiêu là kiểm soát việc dùng credential và chứng minh việc thu hồi.

## 15. Câu hỏi tự kiểm tra

1. Vì sao hết thời gian checkout không có nghĩa một private key tĩnh đã hết hạn?
2. Nếu public key dùng chung nằm trên 30 máy, cần những bằng chứng nào để tuyên bố rotation hoàn tất?
3. Một broker chỉ chuyển tiếp kết nối có tự cung cấp nhật ký lệnh không?
4. Vì sao đổi passphrase không xử lý được bản private key đã sao chép trước đó?
5. Làm thế nào phát hiện kết nối thử đang dùng identity khác hoặc phiên multiplex cũ?
6. Cần tách quyền nào giữa người sử dụng khóa và người quản trị vault?
7. Khi một workload cần secret để lấy secret khác, phải xem xét vấn đề bootstrap nào?
8. Tại sao kiểm tra host key vẫn cần thiết dù user private key được vault quản lý?
9. Quy trình phục hồi phải làm gì để không tái cấp quyền cho khóa đã thu hồi?
10. Điều gì còn thiếu nếu hệ thống chỉ có log đọc secret mà không nối được với tài khoản và phiên ở máy đích?

Điểm cốt lõi là quản lý đồng thời vật liệu khóa, quyền tại máy đích và danh tính sử dụng. Một vault có giá trị khi nó nằm trong một vòng đời truy cập có thể kiểm soát, luân chuyển và kiểm chứng.

