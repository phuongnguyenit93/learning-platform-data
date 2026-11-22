# Cài đặt Azure CLI và quản lý phiên đăng nhập

Azure CLI là công cụ dòng lệnh để làm việc với các dịch vụ Microsoft Azure. Sau khi cài đặt và đăng nhập, bạn có thể dùng lệnh `az` để xem subscription, chọn môi trường làm việc, quản lý resource group và triển khai hạ tầng. Bài học này tập trung vào hai việc nền tảng: chuẩn bị Azure CLI trên máy và kiểm soát chính xác danh tính cùng subscription đang hoạt động.

Trong hệ sinh thái **CLOUD_PROVIDERS_AZURE**, Azure CLI là một công cụ quản trị quan trọng bên cạnh Azure Portal, Azure Cloud Shell và các công cụ triển khai tự động. Nó giúp bạn thực hiện các thao tác lặp lại bằng câu lệnh, lưu chúng thành script và đưa vào quy trình CI/CD.

## 1. Hiểu ngữ cảnh trước khi đăng nhập

Azure có một số khái niệm cần phân biệt:

| Khái niệm | Vai trò |
|---|---|
| Microsoft Entra tenant | Thư mục danh tính chứa người dùng, nhóm, ứng dụng và chính sách truy cập |
| Azure subscription | Phạm vi quản lý tài nguyên, quyền truy cập và thanh toán |
| Resource group | Nhóm logic chứa các tài nguyên Azure có liên quan |
| Azure CLI | Công cụ gửi yêu cầu quản trị tới Azure bằng lệnh `az` |

Một người dùng có thể được cấp quyền trên nhiều subscription, kể cả subscription thuộc các tenant khác nhau. Vì vậy, đăng nhập thành công chưa đủ để bảo đảm lệnh tiếp theo chạy đúng môi trường. Bạn cần kiểm tra tenant và subscription đang được chọn trước khi tạo, sửa hoặc xóa tài nguyên.

Azure CLI cũng không tự cấp quyền. Quyền thực hiện một thao tác vẫn được kiểm soát bởi Azure role-based access control (Azure RBAC), chính sách của tổ chức và các cơ chế bảo vệ danh tính trong Microsoft Entra ID.

## 2. Chuẩn bị trước khi cài đặt

Bạn cần:

- Một máy tính có quyền cài đặt phần mềm hoặc quyền sử dụng trình quản lý gói của hệ điều hành.
- Kết nối Internet để tải Azure CLI và xác thực với Azure.
- Một tài khoản Microsoft Entra được phép truy cập tenant hoặc subscription cần làm việc.
- Quyền Azure phù hợp với thao tác dự định thực hiện. Ví dụ, quyền đọc subscription đủ để xem thông tin; thao tác tạo resource group cần quyền ghi tương ứng.

Nếu tổ chức yêu cầu xác thực đa yếu tố (MFA), hãy chuẩn bị phương thức xác thực đã đăng ký. Một số tổ chức còn áp dụng Conditional Access, giới hạn thiết bị hoặc vị trí đăng nhập; các chính sách này vẫn có hiệu lực khi bạn dùng Azure CLI.

## 3. Cài đặt Azure CLI

Chọn cách cài phù hợp với hệ điều hành. Hãy sử dụng nguồn cài đặt chính thức hoặc trình quản lý gói đáng tin cậy của hệ thống.

### Windows

Trên Windows 10 hoặc Windows 11 có Windows Package Manager (winget), mở PowerShell hoặc Windows Terminal và chạy:

```powershell
winget install --exact --id Microsoft.AzureCLI
```

Bạn cũng có thể dùng bộ cài MSI của Microsoft nếu môi trường máy tính không sử dụng winget. Sau khi cài xong, đóng và mở lại terminal để hệ điều hành nạp lại đường dẫn chương trình.

### macOS

Nếu máy đã cài Homebrew, chạy:

```bash
brew update
brew install azure-cli
```

Nếu Azure CLI đã được cài qua Homebrew, có thể cập nhật bằng:

```bash
brew update
brew upgrade azure-cli
```

### Ubuntu và Debian

Với Ubuntu hoặc Debian, Microsoft cung cấp script cài đặt Azure CLI để cấu hình nguồn gói và cài đặt CLI:

```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

Lệnh này cần kết nối Internet và quyền `sudo`. Với bản phân phối Linux khác, hãy chọn hướng dẫn cài đặt tương ứng trên tài liệu Azure CLI chính thức; không nên mặc định rằng gói dành cho Debian sẽ phù hợp với mọi bản phân phối.

### Kiểm tra cài đặt

Mở một terminal mới và chạy:

```bash
az version
```

Lệnh trả về thông tin phiên bản Azure CLI và các thành phần liên quan. Nếu terminal báo không tìm thấy `az`, hãy kiểm tra quá trình cài đặt, mở terminal mới và xác nhận thư mục cài đặt đã nằm trong biến môi trường `PATH`.

Bạn có thể cập nhật Azure CLI bằng:

```bash
az upgrade
```

Nếu hệ điều hành hoặc chính sách doanh nghiệp quản lý phiên bản thông qua trình quản lý gói, hãy tuân theo cơ chế cập nhật đó.

## 4. Đăng nhập Azure bằng tài khoản người dùng

Trên máy tính có trình duyệt, cách đăng nhập thông thường là:

```bash
az login
```

Azure CLI mở trình duyệt để bạn chọn tài khoản và hoàn tất quy trình xác thực của Microsoft Entra ID. Nếu tổ chức yêu cầu MFA hoặc bước xác minh bổ sung, hãy hoàn thành các bước đó trong trình duyệt.

Sau khi đăng nhập, CLI hiển thị thông tin các subscription mà tài khoản có thể truy cập. Kết quả này giúp bạn nhận biết những môi trường có sẵn, nhưng không nên dựa vào thứ tự hiển thị để suy đoán subscription mặc định.

### Đăng nhập khi không mở được trình duyệt

Trong máy chủ từ xa, terminal không có giao diện đồ họa hoặc môi trường không thể tự mở trình duyệt, sử dụng device code:

```bash
az login --use-device-code
```

CLI sẽ hiển thị địa chỉ trang xác thực và mã dùng một lần. Mở trang được hướng dẫn trên một trình duyệt có thể truy cập, nhập mã và xác nhận đăng nhập. Không chia sẻ mã xác thực với người khác; mã này là một phần của quy trình đăng nhập.

### Chỉ định tenant khi đăng nhập

Nếu tài khoản thuộc nhiều tenant hoặc bạn cần truy cập một tenant cụ thể, truyền tenant ID:

```bash
az login --tenant "<TENANT_ID>"
```

Thay `<TENANT_ID>` bằng ID tenant Microsoft Entra mà tổ chức cung cấp. Bạn cũng có thể dùng tên miền tenant nếu phù hợp với cấu hình tổ chức, nhưng tenant ID thường rõ ràng hơn khi viết script hoặc tài liệu vận hành.

Đăng nhập vào tenant chỉ xác lập ngữ cảnh danh tính. Bạn vẫn cần chọn subscription có quyền truy cập trước khi thực hiện thao tác trên tài nguyên.

## 5. Xem và chọn subscription đang hoạt động

Đây là bước quan trọng nhất để tránh thao tác nhầm môi trường.

Liệt kê các subscription CLI đang nhận diện:

```bash
az account list --output table
```

Bảng kết quả thường có tên subscription, subscription ID, tenant ID, trạng thái và thông tin subscription mặc định. Dùng subscription ID khi cần lựa chọn chính xác, đặc biệt khi nhiều subscription có tên gần giống nhau.

Xem ngữ cảnh hiện tại:

```bash
az account show --output json
```

Đặt subscription cần làm việc:

```bash
az account set --subscription "<SUBSCRIPTION_ID_OR_NAME>"
```

Sau đó kiểm tra lại:

```bash
az account show --query "{subscription:name, subscriptionId:id, tenant:tenantId, state:state}" --output json
```

Lệnh `az account set` thay đổi subscription mặc định mà Azure CLI sử dụng cho các lệnh tiếp theo. Nó không tạo subscription, không cấp thêm quyền và không thay đổi quyền của người dùng.

**Thói quen an toàn:** trước khi chạy lệnh có thể tạo, sửa hoặc xóa tài nguyên, hãy chạy `az account show` và xác nhận subscription ID cùng tenant ID. Trong script quan trọng, có thể truyền tham số `--subscription` trực tiếp vào lệnh hỗ trợ tham số này để thể hiện rõ phạm vi thực thi.

## 6. Xác nhận quyền truy cập

Sau khi chọn subscription, bạn có thể kiểm tra một thao tác đọc đơn giản:

```bash
az group list --output table
```

Nếu lệnh trả về danh sách resource group, danh tính hiện tại có thể đọc danh sách đó trong subscription đang chọn. Nếu danh sách rỗng, subscription có thể chưa có resource group hoặc phạm vi truy cập của bạn không hiển thị tài nguyên nào.

Nếu nhận lỗi authorization, hãy kiểm tra lần lượt:

1. Subscription đang chọn có đúng không?
2. Tenant đăng nhập có phải tenant chứa subscription đó không?
3. Tài khoản đã được cấp Azure RBAC role phù hợp tại subscription hoặc resource group chưa?
4. Chính sách Conditional Access hoặc chính sách của tổ chức có chặn thao tác không?

Đăng nhập thành công chỉ chứng minh CLI đã xác thực được danh tính. Nó không chứng minh danh tính đó có quyền đọc hoặc thay đổi mọi tài nguyên.

## 7. Làm việc với nhiều loại danh tính

### Tài khoản người dùng

Đăng nhập tương tác bằng `az login` phù hợp cho thao tác trực tiếp của kỹ sư. Người dùng có thể hoàn tất MFA và các bước xác thực mà tổ chức yêu cầu. Không nên dùng tài khoản cá nhân làm danh tính chạy tác vụ tự động dài hạn.

### Service principal

Service principal đại diện cho một ứng dụng hoặc workload trong Microsoft Entra ID. Nó thường được dùng trong pipeline hoặc tác vụ tự động khi workload cần một danh tính ứng dụng.

Dạng lệnh đăng nhập bằng client secret:

```bash
az login --service-principal \
  --username "<APPLICATION_CLIENT_ID>" \
  --password "<CLIENT_SECRET>" \
  --tenant "<TENANT_ID>"
```

Các giá trị trong dấu ngoặc nhọn là placeholder, không phải thông tin đăng nhập có thể sử dụng. Không ghi client secret thật vào mã nguồn, file cấu hình được commit, log hoặc lịch sử lệnh dùng chung. Khi thiết kế hệ thống tự động, ưu tiên workload identity federation hoặc chứng chỉ nếu nền tảng hỗ trợ; nếu buộc phải dùng secret, hãy lưu trong kho bí mật được bảo vệ, giới hạn quyền và xoay vòng theo chính sách.

Service principal chỉ có thể thực hiện các thao tác được cấp quyền. Hãy cấp role tối thiểu theo phạm vi cần thiết thay vì mặc định cấp Owner trên toàn subscription.

### Managed identity

Khi ứng dụng chạy trên tài nguyên Azure có managed identity được bật và cấp quyền phù hợp, có thể đăng nhập mà không cần lưu client secret:

```bash
az login --identity
```

Với user-assigned managed identity, có thể chỉ định client ID:

```bash
az login --identity --client-id "<MANAGED_IDENTITY_CLIENT_ID>"
```

Các lệnh này chỉ hoạt động trong môi trường Azure có managed identity tương ứng. Chạy chúng trên máy tính cá nhân không có managed identity sẽ không tự tạo ra danh tính Azure.

**Chọn phương thức phù hợp:** dùng tài khoản người dùng cho thao tác tương tác; dùng service principal hoặc workload identity federation cho pipeline; dùng managed identity cho workload chạy trên Azure khi kiến trúc hỗ trợ.

## 8. Đăng xuất và làm mới ngữ cảnh cục bộ

Khi hoàn tất phiên làm việc trên máy dùng chung hoặc cần chuyển tài khoản, chạy:

```bash
az logout
```

Lệnh không có đối số đăng xuất tất cả tài khoản đã đăng nhập trong cache của Azure CLI. Nếu chỉ muốn đăng xuất một tài khoản, truyền tùy chọn `--username` cùng tên đăng nhập của tài khoản đó.

Khi danh sách subscription trong cache cục bộ không còn đúng hoặc cần làm mới dữ liệu subscription, dùng:

```bash
az account clear
```

Lệnh này xóa dữ liệu subscription khỏi cache cục bộ của Azure CLI. Sau đó, đăng nhập lại để CLI tải lại thông tin tài khoản và subscription:

```bash
az login
az account list --output table
```

Hai lệnh có mục đích khác nhau: `az logout` xử lý trạng thái đăng nhập; `az account clear` làm sạch cache subscription cục bộ. Chúng không xóa tài nguyên Azure và không hủy subscription trên nền tảng Azure.

## 9. Một số tùy chọn hữu ích khi sử dụng CLI

### Chọn định dạng đầu ra

Azure CLI hỗ trợ nhiều định dạng đầu ra. Ví dụ:

```bash
az account list --output table
az account list --output json
az account list --output yaml
```

- `table` dễ đọc khi thao tác thủ công.
- `json` thuận tiện cho chương trình hoặc công cụ xử lý dữ liệu.
- `yaml` hữu ích khi cần định dạng dễ đọc trong một số quy trình cấu hình.
- `tsv` phù hợp với một số script cần các trường phân tách bằng tab.
- `none` bỏ qua nội dung đầu ra khi không cần hiển thị kết quả.

Có thể cấu hình định dạng mặc định cho CLI:

```bash
az config set core.output=table
```

Bạn vẫn có thể ghi đè định dạng cho từng lệnh bằng `--output`.

### Lọc dữ liệu bằng --query

Tùy chọn `--query` sử dụng JMESPath để chọn trường hoặc lọc kết quả. Ví dụ, lấy tên và ID của các subscription:

```bash
az account list --query "[].{name:name, id:id, tenant:tenantId}" --output table
```

Khi viết script, hãy lọc đúng trường cần dùng và kiểm tra kết quả thực tế. Không đưa access token, client secret hoặc dữ liệu xác thực vào đầu ra chỉ để thuận tiện gỡ lỗi.

## 10. Xử lý các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy lệnh `az` | CLI chưa cài, terminal chưa nạp lại PATH hoặc cài đặt lỗi | Mở terminal mới, kiểm tra cài đặt và PATH, sau đó chạy lại `az version` |
| Trình duyệt không mở khi đăng nhập | Máy chủ không có giao diện đồ họa hoặc terminal từ xa | Dùng `az login --use-device-code` |
| Không thấy subscription mong muốn | Đăng nhập sai tenant, tài khoản chưa được cấp quyền hoặc subscription không khả dụng | Dùng `az login --tenant "<TENANT_ID>"`, kiểm tra `az account list` và xác nhận quyền với quản trị viên |
| Lệnh báo AuthorizationFailed | Danh tính đã xác thực nhưng thiếu quyền cho thao tác hoặc phạm vi tài nguyên | Kiểm tra subscription, tenant và Azure RBAC role cần thiết |
| Đang thao tác nhầm subscription | CLI đang giữ subscription mặc định khác với dự định | Dừng thao tác, chạy `az account show`, rồi chọn lại bằng `az account set` |
| Phiên đăng nhập không còn hợp lệ | Token hết hạn, chính sách xác thực thay đổi hoặc phiên cần xác minh lại | Thực hiện lại `az login` và hoàn tất các bước xác thực được yêu cầu |

Khi gặp lỗi, hãy đọc thông báo đầy đủ và xác định lỗi thuộc nhóm cài đặt, xác thực, lựa chọn subscription hay phân quyền. Không nên lặp lại một lệnh ghi hoặc xóa tài nguyên khi chưa xác nhận nguyên nhân.

## 11. Nguyên tắc bảo mật và vận hành

- Xác minh tenant và subscription trước mọi thao tác có ảnh hưởng tới hạ tầng.
- Tuân thủ MFA và chính sách Conditional Access của tổ chức.
- Dùng Azure RBAC với quyền tối thiểu cần thiết; tách quyền đọc, triển khai và quản trị khi phù hợp.
- Không chia sẻ phiên terminal đang đăng nhập hoặc thư mục cache xác thực của Azure CLI.
- Không đưa access token, client secret hay mã device login vào Git, ticket công khai, ảnh chụp màn hình hoặc log.
- Dùng managed identity hoặc workload identity federation cho workload khi có thể; quản lý vòng đời secret và chứng chỉ theo quy trình bảo mật nếu cần dùng chúng.
- Với script có thao tác phá hủy, yêu cầu xác nhận môi trường và phạm vi tài nguyên trước khi chạy.

Các nguyên tắc này đặc biệt quan trọng khi một máy phát triển được dùng để truy cập nhiều subscription hoặc khi lệnh Azure CLI được đưa vào pipeline tự động.

## 12. Bài thực hành

Thực hiện các bước sau trên subscription thử nghiệm mà bạn được phép truy cập:

1. Cài Azure CLI và xác nhận phiên bản bằng `az version`.
2. Đăng nhập bằng `az login`; nếu đang dùng máy không có trình duyệt, chuyển sang `az login --use-device-code`.
3. Chạy `az account list --output table` và xác định subscription cần dùng.
4. Chọn subscription bằng `az account set --subscription "<SUBSCRIPTION_ID>"`.
5. Chạy `az account show` để kiểm tra subscription ID và tenant ID.
6. Chạy `az group list --output table` để xác nhận quyền đọc resource group.
7. Đăng xuất bằng `az logout` khi hoàn thành.

**Tiêu chí hoàn thành:** bạn giải thích được tenant và subscription khác nhau thế nào, cài được Azure CLI, đăng nhập được bằng phương thức phù hợp, chọn đúng subscription và xác minh được ngữ cảnh trước khi thao tác với tài nguyên.

## Kết luận

Azure CLI cung cấp giao diện dòng lệnh thống nhất để quản lý Azure. Quy trình làm việc an toàn bắt đầu bằng cài đặt đúng phiên bản, xác thực bằng danh tính phù hợp, kiểm tra tenant và subscription, rồi mới thực hiện thao tác trên tài nguyên. Khi nắm vững `az login`, `az account list`, `az account show`, `az account set` và `az logout`, bạn đã có nền tảng cần thiết để tiếp tục học cách quản lý resource group, mạng, dịch vụ tính toán, lưu trữ và dữ liệu trên Microsoft Azure.

