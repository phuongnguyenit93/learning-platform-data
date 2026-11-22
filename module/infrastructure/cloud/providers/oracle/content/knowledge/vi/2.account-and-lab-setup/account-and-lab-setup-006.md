# Cài đặt OCI CLI và cấu hình profile kết nối

## 1. Mục tiêu và phạm vi

OCI Command Line Interface (OCI CLI) là công cụ dòng lệnh để gọi API của Oracle Cloud Infrastructure. Bạn có thể dùng CLI để kiểm tra tài nguyên, thu thập thông tin vận hành và xây dựng những bước tự động hóa có thể lặp lại.

Bài học thuộc chương **Tài khoản và môi trường thực hành** của module **CLOUD_PROVIDERS_ORACLE**. Một kết nối CLI đúng là nền tảng để thực hành tenancy, compartment, IAM, VCN, Compute, lưu trữ và dịch vụ cơ sở dữ liệu Oracle theo đúng quyền, đúng môi trường, có khả năng giám sát và kiểm soát chi phí.

Sau bài học, bạn có thể:

- Cài OCI CLI theo hệ điều hành và xác minh chương trình đang được gọi.
- Phân biệt API signing key với SSH key, mật khẩu Console và session token.
- Tạo profile kết nối với đúng user, tenancy, private key và region.
- Chọn profile rõ ràng và nhận diện cấu hình bị biến môi trường ghi đè.
- Kiểm tra kết nối bằng lệnh chỉ đọc, rồi tách lỗi cài đặt, xác thực và phân quyền.
- Quản lý credential trên máy thực hành và thu hồi khi không còn sử dụng.

Bài này không yêu cầu tạo instance, VCN, bucket hoặc database để kiểm tra kết nối. Các ví dụ gọi dịch vụ bên dưới chỉ lấy thông tin; không dùng việc triển khai tài nguyên tính phí làm phép thử đầu tiên.

## 2. Hiểu đường đi của một lệnh OCI CLI

Một lệnh CLI có cấu trúc phổ biến:

~~~text
oci <service> <resource> <action> <options>
~~~

Ví dụ:

~~~text
oci compute instance list --compartment-id <COMPARTMENT_OCID>
~~~

Trong ví dụ, `compute` chọn dịch vụ, `instance` chọn loại tài nguyên và `list` chọn thao tác. Thông tin xác thực và region được lấy từ cấu hình hiệu lực của lệnh. [Oracle: Using the CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliusing.htm)

~~~mermaid
flowchart LR
    S["Shell và tham số lệnh"] --> C["Cấu hình hiệu lực"]
    P["Profile trong config"] --> C
    E["Biến môi trường"] --> C
    C --> A["Xác thực theo phương thức đã chọn"]
    A --> O["Endpoint OCI của dịch vụ"]
    O --> I["Kiểm tra quyền IAM"]
    I --> R["Kết quả hoặc lỗi"]
~~~

Cài được chương trình và xác thực được là hai mốc khác nhau. Xác thực thành công cũng chưa chứng minh user có quyền quản lý mọi tài nguyên.

## 3. Chuẩn bị thông tin trước khi cấu hình

Bạn cần một tài khoản OCI được phép thực hành và biết người quản trị nào phụ trách quyền truy cập. Không dùng tài khoản quản trị toàn tenancy chỉ để tránh phải xử lý lỗi thiếu quyền.

| Thông tin | Ý nghĩa và nơi đối chiếu |
| --- | --- |
| Tenancy OCID | Định danh tenancy; lấy từ thông tin tenancy trong Console |
| User OCID | Định danh user thực hiện yêu cầu; lấy từ trang chi tiết đúng user |
| Domain và user đang sử dụng | Giúp chọn đúng tài khoản khi tenancy có nhiều Identity Domain |
| Region thực hành | Mã region dự kiến gọi; đối chiếu region đã đăng ký và được phép sử dụng |
| Compartment OCID | Phạm vi tài nguyên cho phép kiểm tra ở những bước sau |
| Phương thức xác thực | API key hoặc phiên đăng nhập tạm thời theo quy định môi trường |
| Quyền IAM | Những thao tác đọc hoặc thực hành đã được cấp |

OCID không phải tên hiển thị. Không thay `user` trong config bằng địa chỉ email, tên đăng nhập hoặc tên domain. Tương tự, `tenancy` phải là OCID tenancy, không phải OCID của compartment thực hành.

Một region trong config chỉ định đích gọi dịch vụ; nó không tự đăng ký region, sao chép tài nguyên hoặc mở thêm quyền truy cập.

### 3.1. Các loại credential cần phân biệt

| Thành phần | Dùng để làm gì? | Không thay thế cho |
| --- | --- | --- |
| Mật khẩu Console và MFA | Đăng nhập tương tác theo cấu hình tài khoản | API signing key cho phương thức xác thực API key |
| API signing key | Ký yêu cầu API; public key đăng ký cho user, private key giữ ở máy khách | SSH key đăng nhập hệ điều hành |
| SSH key | Xác thực vào máy chủ theo cấu hình SSH | API signing key của OCI |
| Session token | Xác thực CLI trong một phiên tạm thời | Credential dài hạn để dùng vô thời hạn |
| Auth token của dịch vụ | Phục vụ các trường hợp tích hợp được hỗ trợ | Private key trong profile API key |

API signing key OCI sử dụng cặp khóa RSA dạng PEM, tối thiểu 2048 bit; không tải public key dạng `ssh-rsa` lên mục API Keys như thể đó là cùng định dạng. [Oracle: Required Keys and OCIDs](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm)

## 4. Cài đặt OCI CLI

Chọn một phương thức cài đặt chính cho máy. Trộn nhiều bản cài mà không kiểm soát PATH có thể làm terminal gọi một phiên bản khác với phiên bản bạn vừa nâng cấp.

Oracle cung cấp hướng dẫn cài cho Windows, macOS và Linux/UNIX. Dùng tài liệu và bộ cài chính thức, đồng thời đối chiếu yêu cầu của phiên bản đang cài thay vì sao chép một số phiên bản cố định từ bài học. [Oracle: OCI CLI Quickstart](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm)

### 4.1. Windows: dùng MSI

Với người mới trên Windows, có thể dùng bộ cài MSI được dẫn từ trang Quickstart:

1. Mở mục cài đặt Windows trong tài liệu Oracle.
2. Theo liên kết tới bộ cài MSI chính thức và tải bản phù hợp.
3. Chạy bộ cài, xác nhận thư mục cài và hoàn tất các bước được yêu cầu.
4. Đóng rồi mở lại PowerShell để nhận thay đổi PATH.
5. Kiểm tra lệnh và phiên bản:

~~~powershell
Get-Command oci
oci --version
oci --help
~~~

`Get-Command oci` cho biết PowerShell đang tìm thấy lệnh ở đâu. Nếu máy đã có nhiều bản cài, xem tất cả kết quả:

~~~powershell
Get-Command oci -All
~~~

Chọn và duy trì một bản cài theo quy trình của máy; không xóa thư mục hệ thống chỉ vì một kết quả PATH chưa đúng.

Nếu chọn cách cài bằng script PowerShell thay cho MSI, làm theo nhánh PowerShell trong tài liệu chính thức và chính sách thiết bị. Không cần áp dụng cả hai cách cho cùng bài thực hành.

### 4.2. macOS: dùng Homebrew

Nếu máy đã có Homebrew theo quy trình được chấp nhận:

~~~bash
brew update
brew install oci-cli
oci --version
command -v oci
~~~

Khi nâng cấp một bản cài bằng Homebrew, tiếp tục dùng Homebrew để quản lý bản đó thay vì cài đè bằng một phương thức khác.

### 4.3. Linux/UNIX: dùng installer chính thức

Có thể tải installer về để xem trước rồi chạy:

~~~bash
curl --fail --location https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh --output /tmp/oci-cli-install.sh
less /tmp/oci-cli-install.sh
bash /tmp/oci-cli-install.sh
~~~

Làm theo các câu hỏi của installer, ghi nhớ thư mục cài và thư mục chương trình. Mở shell mới nếu installer cập nhật PATH, sau đó kiểm tra:

~~~bash
command -v oci
oci --version
oci --help
~~~

Nếu tổ chức phân phối sẵn OCI CLI qua package hoặc image được quản lý, dùng phương thức đó. Không mặc định cần cài lại chỉ vì đã thấy một hướng dẫn installer khác.

### 4.4. Môi trường phụ thuộc và máy bị hạn chế mạng

OCI CLI có các dependency riêng. Với cài đặt thủ công hoặc offline, dùng hướng dẫn Oracle tương ứng; tránh cài vào môi trường phần mềm dùng chung khi có nguy cơ xung đột dependency. Oracle khuyến nghị dùng installer hoặc môi trường tách biệt thay vì cài CLI vào Python hệ thống. [Oracle: Manual and Offline Installations](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/climanualinst.htm)

Nếu terminal không nhận `oci`, xử lý cài đặt hoặc PATH trước. Chưa cần tạo API key mới, thay policy hoặc tạo tài nguyên cloud ở bước này.

## 5. Chọn phương thức xác thực

Hai lựa chọn thực hành phổ biến là API key và session token:

| Lựa chọn | Đặc điểm | Trường hợp phù hợp |
| --- | --- | --- |
| API key | Máy giữ private key; public key đăng ký với user | Máy thực hành được bảo vệ, cần profile dùng lại theo quy trình |
| Session token | Đăng nhập để có phiên tạm thời, cần xử lý khi hết hạn | Thao tác tương tác và môi trường ưu tiên đăng nhập qua trình duyệt |

OCI còn có instance principal và resource principal cho những workload được hỗ trợ. Không sao chép credential cá nhân lên Compute hoặc pipeline như lựa chọn mặc định khi có thể sử dụng danh tính workload phù hợp. [Oracle: OCI SDK Authentication Methods](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdk_authentication_methods.htm)

Trong bài này, phần API key tạo profile `LAB_API`; phần session token dùng profile riêng `LAB_SESSION`. Chọn phương thức được môi trường cho phép, không cần tạo cả hai để chứng minh đã cài CLI thành công.

## 6. Tạo profile API key

### 6.1. Chuẩn bị nơi lưu ngoài mã nguồn

Thư mục cấu hình thường dùng là `.oci` trong thư mục người dùng. Trên Windows PowerShell:

~~~powershell
$ociDirectory = Join-Path $env:USERPROFILE '.oci'
$ociConfigPath = Join-Path $ociDirectory 'config'
New-Item -ItemType Directory -Path $ociDirectory -Force
~~~

Trên Linux/macOS:

~~~bash
mkdir -p "$HOME/.oci"
chmod 700 "$HOME/.oci"
~~~

Không đặt private key vào repository, thư mục chia sẻ hoặc image ứng dụng. File config không nên chứa secret dạng rõ, nhưng vẫn cần được quản lý vì nó mô tả danh tính và nơi lưu credential.

### 6.2. Đăng ký public key cho đúng user

Một luồng thuận tiện là dùng Console:

1. Chọn đúng user trong đúng Identity Domain.
2. Mở mục API Keys của user đó.
3. Thêm API key theo khả năng được cho phép của tài khoản.
4. Nếu để Console tạo cặp khóa, tải private key về và chuyển tới thư mục bảo vệ đã chọn.
5. Nếu đã có cặp khóa phù hợp, chỉ tải **public key** lên Console.
6. Lấy configuration snippet được cung cấp để đối chiếu user, tenancy và fingerprint.

Đường dẫn `key_file` trong snippet phải được sửa thành vị trí private key thực tế trên máy. Không tải private key lên nơi yêu cầu public key. [Oracle: Required Keys and OCIDs](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm)

Một lựa chọn khác là chạy trình hướng dẫn tương tác:

~~~text
oci setup config
~~~

Lệnh này hỗ trợ tạo config cục bộ. Nếu tạo khóa mới bằng trình hướng dẫn, vẫn phải hoàn tất việc đăng ký public key tương ứng cho đúng user trên OCI. Việc có file PEM trên máy không chứng minh key đã được đăng ký. Kiểm tra các câu hỏi trước khi ghi vào một config đã có profile quan trọng. [Oracle: oci setup config](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/setup/config.html)

### 6.3. Các field trong profile

| Field | Nội dung |
| --- | --- |
| `user` | OCID user ký yêu cầu |
| `tenancy` | OCID tenancy của cấu hình |
| `fingerprint` | Fingerprint public key đã đăng ký cho user |
| `key_file` | Đường dẫn tới private key tương ứng trên máy |
| `region` | Region mặc định khi lệnh không chỉ định giá trị khác |

Config dùng cú pháp kiểu INI với tên profile trong dấu ngoặc vuông. File kết nối mặc định là `~/.oci/config`; với PowerShell Windows, thường là thư mục `.oci` dưới `%USERPROFILE%`. [Oracle: SDK and CLI Configuration File](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm)

Ví dụ cho Windows:

~~~ini
[LAB_API]
user=<USER_OCID>
fingerprint=<PUBLIC_KEY_FINGERPRINT>
tenancy=<TENANCY_OCID>
region=<LAB_REGION>
key_file=C:/Users/YourName/.oci/lab_api_key.pem
~~~

Ví dụ tương đương cho Linux/macOS:

~~~ini
[LAB_API]
user=<USER_OCID>
fingerprint=<PUBLIC_KEY_FINGERPRINT>
tenancy=<TENANCY_OCID>
region=<LAB_REGION>
key_file=~/.oci/lab_api_key.pem
~~~

Các giá trị trong dấu `<...>` đều là placeholder, phải thay bằng dữ liệu thật. `YourName` cũng phải thay bằng thư mục người dùng thực tế. Không đặt dấu ngoặc kép quanh toàn bộ đường dẫn `key_file` như khi truyền một đối số shell; đó là giá trị trong file INI.

Tên `LAB_API` là tên cục bộ do bạn đặt. Nó không tạo user, group hoặc policy trên OCI và không tự làm quyền của tài khoản hẹp hơn.

### 6.4. Bảo vệ private key

Trên Linux/macOS, sau khi xác nhận đúng vị trí file:

~~~bash
chmod 600 "$HOME/.oci/config"
chmod 600 "$HOME/.oci/lab_api_key.pem"
~~~

Trên Windows, kiểm tra quyền tại Properties → Security của thư mục và private key; giới hạn quyền đọc cho tài khoản và những chủ thể quản trị được tổ chức cho phép. Không dùng lệnh `chmod` như cách thay thế máy móc cho ACL Windows.

Nếu private key được mã hóa bằng passphrase, cần cung cấp passphrase bằng cơ chế runtime được hỗ trợ và phù hợp quy trình của máy. Không ghi passphrase vào bài nộp, lịch sử lệnh hoặc repository. Field `pass_phrase` trong config đã bị đánh dấu deprecated; Oracle khuyến cáo tránh lưu thông tin bí mật trong config. [Oracle: SDK and CLI Configuration File](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm)

Mật khẩu Console và MFA của trình duyệt không được dùng để thay cho passphrase giải mã private key. Đây là các cơ chế khác nhau.

## 7. Cấu hình session token

Với máy có trình duyệt và môi trường cho phép đăng nhập tương tác:

~~~text
oci session authenticate
~~~

Theo các câu hỏi để chọn region, đăng nhập vào đúng tenancy/domain và đặt tên profile phiên, ví dụ `LAB_SESSION`. Giữ thông tin file được CLI tạo theo hướng dẫn của công cụ; không sao chép cấu hình API key rồi tự điền một chuỗi token bất kỳ.

Kiểm tra phiên:

~~~text
oci session validate --profile LAB_SESSION --auth security_token
~~~

Gọi một lệnh chỉ đọc bằng phiên:

~~~text
oci os ns get --profile LAB_SESSION --auth security_token
~~~

Đối với session token, cần chỉ rõ `--auth security_token` hoặc đặt `OCI_CLI_AUTH` tương ứng. Chỉ chọn profile mang tên `LAB_SESSION` không tự bảo đảm CLI sử dụng đúng loại xác thực. [Oracle: Token-based Authentication for the CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/clitoken.htm)

Phiên có thời hạn. Khi phiên không còn hợp lệ, xử lý việc làm mới hoặc đăng nhập lại theo khả năng của phiên và hướng dẫn Oracle. Không sửa thủ công nội dung token hoặc coi phiên tương tác là credential vô thời hạn cho tác vụ chạy nền.

Máy không có trình duyệt cần quy trình xác thực khác đã được cấu hình. Không hiểu tùy chọn `--no-browser` là bỏ qua yêu cầu xác thực.

## 8. Chọn profile và tránh nhầm môi trường

### 8.1. Truyền profile rõ ràng

Với API key:

~~~text
oci os ns get --profile LAB_API --auth api_key
~~~

Nếu config nằm ngoài đường dẫn mặc định, chỉ rõ file. Ví dụ PowerShell:

~~~powershell
$ociConfigPath = Join-Path $env:USERPROFILE '.oci/config'
oci os ns get --config-file $ociConfigPath --profile LAB_API --auth api_key
~~~

Đây là file config kết nối. Nó khác `oci_cli_rc`, file tùy chọn riêng của CLI dùng cho mặc định tham số, alias và các cấu hình tiện ích. Thông thường không cần sửa `oci_cli_rc` để hoàn thành kết nối đầu tiên. [Oracle: Configuring the CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliconfigure.htm)

### 8.2. Nhiều profile không đồng nghĩa nhiều bộ quyền

Có thể có nhiều profile cho những user, tenancy hoặc region khác nhau. Khi tạo profile bổ sung, nên điền đầy đủ các field cần thiết để dễ đối chiếu và tránh nhầm những giá trị mặc định được dùng lại.

| Tên profile minh họa | Ý định sử dụng | Điều phải xác minh |
| --- | --- | --- |
| `LAB_API` | User thực hành với API key | User, tenancy, key và quyền lab |
| `LAB_SESSION` | Phiên tương tác tạm thời | User đăng nhập, thời hạn và loại auth |
| `LAB_OTHER_REGION` | Thực hành tại region khác được cho phép | Region đích và tài nguyên tại đó |

Đặt tên `READONLY` không biến một user nhiều quyền thành user chỉ đọc. Hai profile cùng trỏ tới một user vẫn sử dụng quyền hiệu lực của user đó, trừ khi phương thức và ngữ cảnh xác thực thực tế dẫn tới một chủ thể khác.

### 8.3. Thứ tự ưu tiên cấu hình

Với những giá trị có cơ chế tương ứng, OCI CLI ưu tiên:

1. Tùy chọn truyền trực tiếp trên lệnh.
2. Biến môi trường.
3. Giá trị trong config.

Các biến thường gặp là `OCI_CLI_PROFILE`, `OCI_CLI_CONFIG_FILE`, `OCI_CLI_REGION`, `OCI_CLI_AUTH`, `OCI_CLI_USER`, `OCI_CLI_TENANCY` và `OCI_CLI_KEY_FILE`. Một số biến khác có thể mang nội dung private key hoặc passphrase. [Oracle: CLI Environment Variables](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/clienvironmentvariables.htm)

Ví dụ, profile ghi một region nhưng `OCI_CLI_REGION` trong shell đã chọn region khác thì lệnh không truyền `--region` có thể đi tới đích ngoài dự kiến.

Trên PowerShell, chỉ liệt kê **tên** những biến OCI hiện có khi kiểm tra ban đầu:

~~~powershell
Get-ChildItem Env:OCI_CLI_* | Select-Object -ExpandProperty Name
~~~

Không in toàn bộ giá trị môi trường để gửi cho người hỗ trợ: biến môi trường có thể chứa private key hoặc passphrase. Sau đó đối chiếu riêng những biến liên quan trong môi trường bạn kiểm soát.

Để đặt mặc định cho shell PowerShell hiện tại:

~~~powershell
$env:OCI_CLI_PROFILE = 'LAB_API'
$env:OCI_CLI_AUTH = 'api_key'
~~~

Trên Bash:

~~~bash
export OCI_CLI_PROFILE=LAB_API
export OCI_CLI_AUTH=api_key
~~~

Các biến trên giúp rút ngắn lệnh, nhưng khi ghi hướng dẫn hoặc làm thao tác nhạy cảm vẫn nên truyền profile, auth và region rõ ràng. Nếu đổi phương thức xác thực, kiểm tra các biến cũ thay vì chỉ sửa tên profile.

## 9. Kiểm tra kết nối theo từng tầng

### 9.1. Tầng 1: chương trình cục bộ

~~~text
oci --version
oci --help
~~~

Hai lệnh này xác nhận chương trình có thể chạy và cung cấp trợ giúp. Chúng không xác nhận key đúng, user tồn tại hoặc API endpoint truy cập được.

### 9.2. Tầng 2: một yêu cầu dịch vụ đơn giản

Với API key:

~~~text
oci os ns get --profile LAB_API --auth api_key
~~~

Kết quả có dạng minh họa:

~~~json
{
  "data": "namespace-cua-tenancy"
}
~~~

Giá trị thật do tenancy cung cấp. Lệnh lấy namespace không tạo bucket và không tải dữ liệu mẫu lên Object Storage.

Khi lệnh thành công, đối chiếu namespace hoặc thông tin tenancy đã biết để tránh kiểm tra nhầm môi trường. Kết quả này chỉ chứng minh yêu cầu đó thành công; không chứng minh user có mọi quyền trên Compute, VCN hoặc Database.

### 9.3. Tầng 3: quyền tại compartment và region thực hành

Giả sử user đã được cấp quyền đọc instance trong compartment lab. Ví dụ PowerShell:

~~~powershell
$labCompartmentId = '<COMPARTMENT_OCID>'
$labRegion = '<LAB_REGION>'
oci compute instance list --compartment-id $labCompartmentId --region $labRegion --profile LAB_API --auth api_key --limit 5
~~~

Thay placeholder trước khi chạy. Với session token, dùng profile `LAB_SESSION` và `--auth security_token`.

Các kết quả cần phân biệt:

- Có danh sách instance: phép đọc đã trả dữ liệu trong phạm vi vừa chọn.
- Danh sách trống: có thể compartment/region đó chưa có instance; không phải lỗi kết nối chỉ vì không có tài nguyên.
- Lỗi xác thực: kiểm tra credential và phương thức auth.
- Lỗi quyền hoặc không tìm thấy: kiểm tra policy, OCID và phạm vi tài nguyên.

`--limit 5` chỉ lấy một phần dữ liệu phục vụ phép thử; không xem nó là kiểm kê đầy đủ tenancy. Không mở rộng quyền quản trị toàn tenancy chỉ để làm phép đọc này thành công.

### 9.4. Lưu bằng chứng tối thiểu

Có thể ghi nhận phiên bản CLI, tên profile, phương thức auth, region, compartment thực hành, thời điểm và loại lệnh đã thành công. Không đưa private key, passphrase hoặc session token vào báo cáo.

Đối với yêu cầu thất bại, request ID có thể hữu ích khi phối hợp hỗ trợ. Chỉ chia sẻ đầu ra đã loại bỏ dữ liệu không cần thiết và credential.

## 10. Xử lý lỗi thường gặp

| Hiện tượng | Nhóm nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy `oci` | Cài đặt hoặc PATH | Mở terminal mới, kiểm tra đường dẫn lệnh và phương thức cài |
| Phiên bản không như dự kiến | Nhiều bản CLI | Kiểm tra chương trình thực tế đang được shell gọi |
| Không có profile được yêu cầu | Sai file config hoặc tên section | Đối chiếu `--config-file`, biến môi trường và tên profile |
| Thiếu field cấu hình | Profile chưa đủ dữ liệu | Kiểm tra user, tenancy, fingerprint, key file và region theo loại auth |
| Không đọc được private key | Sai đường dẫn, định dạng hoặc quyền file | Xác nhận file PEM đúng và quyền đọc của tài khoản chạy CLI |
| `NotAuthenticated` hoặc lỗi chữ ký | Key/user/fingerprint không khớp, key bị thu hồi, thời gian máy sai hoặc auth sai | Đối chiếu bộ credential, trạng thái key, đồng hồ và loại auth |
| Session hết hạn | Token không còn hợp lệ | Validate phiên rồi làm mới hoặc đăng nhập lại theo quy trình |
| `NotAuthorizedOrNotFound` | Thiếu quyền, sai OCID hoặc phạm vi không đúng | Đối chiếu quyền và tài nguyên; không mặc định tài nguyên đã bị xóa |
| Không thấy tài nguyên mong đợi | Sai compartment, region, tenancy hoặc phân trang | Đối chiếu toàn bộ phạm vi của lệnh |
| Timeout, lỗi DNS hoặc proxy | Kết nối từ máy tới endpoint | Kiểm tra mạng, DNS, proxy và cấu hình endpoint |
| Lỗi xác minh chứng chỉ | Trust store hoặc proxy kiểm tra TLS | Dùng CA bundle được tổ chức chấp nhận, không vô hiệu hóa kiểm tra TLS |

### 10.1. Không nhầm xác thực với phân quyền

Đăng ký public key không cấp thêm IAM policy. Nếu một yêu cầu đã được xác thực nhưng bị từ chối quyền, tạo thêm nhiều API key thường không giải quyết được vấn đề.

Ngược lại, cấp policy rộng không sửa được cặp khóa không khớp. Hãy kiểm tra theo thứ tự: chương trình → cấu hình → credential → kết nối → quyền → tài nguyên đích.

### 10.2. Proxy và CA của tổ chức

CLI hỗ trợ cấu hình proxy và certificate bundle. Ví dụ, khi đã có địa chỉ proxy và file CA được bộ phận phụ trách cung cấp:

~~~powershell
$env:HTTPS_PROXY = 'http://proxy.example.internal:8080'
$env:OCI_CLI_CERT_BUNDLE = 'C:/Certificates/company-ca-bundle.pem'
~~~

Đây là giá trị minh họa, không phải cấu hình chung cho mọi mạng. Không thêm mật khẩu proxy vào tài liệu chia sẻ hoặc lịch sử lệnh. Không thay endpoint sang một host không rõ nguồn để thử sửa lỗi. [Oracle: Configuring the CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliconfigure.htm), [Oracle: CLI Environment Variables](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/clienvironmentvariables.htm)

### 10.3. Dùng debug có kiểm soát

Khi cần điều tra sâu hơn, có thể tham khảo `oci --help` về tùy chọn debug của bản đang dùng. Đầu ra debug có thể chứa metadata, nội dung yêu cầu và thông tin môi trường; phải rà soát trước khi chia sẻ. Không đăng toàn bộ log debug vào kho mã công khai.

## 11. Quản lý profile và credential sau khi kết nối

### 11.1. Giữ phạm vi thực hành rõ ràng

Trước các lệnh thay đổi tài nguyên ở bài sau, xác nhận bốn yếu tố: **profile, auth, region và compartment**. Profile đúng nhưng compartment sai vẫn có thể làm thao tác ngoài phạm vi dự kiến nếu user có quyền ở đó.

Một cấu hình kết nối thành công cũng không phải phương án kiểm soát chi phí. Cần quyền phù hợp và quy trình quản lý tài nguyên khi bắt đầu triển khai Compute hoặc Database. Ở bài cài đặt này, dừng tại các phép đọc đã nêu là đủ.

### 11.2. Thay và thu hồi API key

Khi cần thay khóa theo quy trình:

1. Tạo và đăng ký public key mới cho đúng user.
2. Đặt private key mới ở vị trí được bảo vệ.
3. Cập nhật một profile mới hoặc thay bộ fingerprint/key tương ứng.
4. Xác minh bằng lệnh chỉ đọc và kiểm tra những công cụ phụ thuộc.
5. Thu hồi public key cũ trên OCI khi đã hoàn tất chuyển đổi.
6. Loại bỏ bản private key cũ theo quy trình lưu giữ của tổ chức.

Khi nghi key đã lộ, ưu tiên quy trình ứng phó và thu hồi phù hợp mức rủi ro; không tiếp tục giữ key cũ chỉ để thuận tiện chuyển đổi.

Xóa file config trên laptop không thu hồi public key đã đăng ký trong OCI. Ngược lại, thu hồi key trên OCI không xóa những bản private key đã sao chép sang máy khác. Cần quản lý cả hai phía.

### 11.3. Dọn môi trường lab

Nếu profile không còn cần thiết, kiểm tra xem có tác vụ nào còn sử dụng nó trước khi bỏ cấu hình và credential liên quan. Với shell đã đặt biến mặc định, có thể bỏ các biến của bài tập trong phiên hiện tại:

~~~powershell
Remove-Item Env:OCI_CLI_PROFILE -ErrorAction SilentlyContinue
Remove-Item Env:OCI_CLI_AUTH -ErrorAction SilentlyContinue
~~~

Trên Bash:

~~~bash
unset OCI_CLI_PROFILE
unset OCI_CLI_AUTH
~~~

Chỉ xóa những cấu hình thuộc bài tập hoặc đã được cho phép. Không xóa toàn bộ `.oci` nếu thư mục còn chứa profile đang dùng cho công việc khác.

## 12. Bài thực hành tổng hợp và tiêu chí hoàn thành

Thực hiện theo trình tự sau:

1. Cài CLI bằng một phương thức phù hợp với máy và ghi nhận đường dẫn lệnh.
2. Xác minh `oci --version` và mở được trợ giúp.
3. Chọn API key hoặc session token theo yêu cầu môi trường.
4. Tạo profile riêng cho lab; đối chiếu đúng danh tính và tenancy.
5. Kiểm tra file credential được lưu ngoài repository và có quyền truy cập phù hợp.
6. Kiểm tra những biến môi trường có thể thay đổi cấu hình hiệu lực.
7. Chạy phép lấy Object Storage namespace bằng profile và auth rõ ràng.
8. Nếu đã có quyền lab, liệt kê instance trong đúng compartment/region mà không tạo tài nguyên.
9. Ghi kết quả từng phép thử và nguyên nhân nếu bước nào chưa thể xác minh.
10. Xác định cách thu hồi credential khi kết thúc việc thực hành.

| Mốc kiểm tra | Bằng chứng đạt |
| --- | --- |
| CLI chạy được | Có phiên bản và vị trí chương trình thực tế |
| Profile được chọn đúng | Lệnh chỉ rõ profile/config và phương thức auth phù hợp |
| Credential khớp | Với API key: user, fingerprint và private key tương ứng; với token: phiên hợp lệ |
| Kết nối dịch vụ hoạt động | Một yêu cầu chỉ đọc trả kết quả hợp lệ ở tenancy dự kiến |
| Phạm vi lab đúng | Đã đối chiếu region và compartment; kết quả phép đọc được giải thích đúng |
| Credential được bảo vệ | Không nằm trong mã nguồn hoặc báo cáo, có kiểm soát quyền đọc |
| Có phương án kết thúc | Biết cách thu hồi key hoặc kết thúc sử dụng phiên và dọn cấu hình lab |

Nếu thiếu quyền cho phép đọc tài nguyên, ghi rõ mốc đó chưa đạt và làm việc với người quản trị theo phạm vi lab. Không xem cài đặt thành công là đã hoàn tất mọi mốc, và không giải quyết bằng cách dùng credential quản trị của người khác.

Kết quả cần đạt là một OCI CLI có thể gọi đúng dịch vụ bằng **đúng danh tính, đúng phương thức xác thực và đúng phạm vi thực hành**. Từ cấu hình này, các bài tiếp theo mới có cơ sở triển khai hạ tầng và tự động hóa mà vẫn kiểm soát được quyền, chi phí và dấu vết thao tác.
