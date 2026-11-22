# Thiết lập môi trường thực hành và ngân sách ban đầu

Microsoft Azure cung cấp nhiều dịch vụ tính toán, mạng, lưu trữ, cơ sở dữ liệu và giám sát. Để học và thử nghiệm các dịch vụ này, trước hết cần có một subscription phù hợp, công cụ truy cập, một phạm vi tài nguyên dễ quản lý và cách theo dõi chi phí. Việc chuẩn bị ngân sách ngay từ đầu giúp bài thực hành có giới hạn rõ ràng và tránh để tài nguyên thử nghiệm tiếp tục phát sinh phí sau khi đã học xong.

Bài học này thuộc chương **Tài khoản và công cụ** của module **CLOUD_PROVIDERS_AZURE**. Module khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu; đồng thời hướng dẫn triển khai, giám sát, bảo vệ và kiểm soát chi phí cho một kiến trúc ứng dụng. Vì vậy, môi trường thực hành trong bài sẽ được chuẩn bị theo cách có thể mở rộng sang những bài học về sau.

Sau bài học, bạn có thể:

- Phân biệt tài khoản đăng nhập, tenant Microsoft Entra ID và Azure subscription.
- Chọn loại subscription phù hợp với mục tiêu học tập và quyền truy cập hiện có.
- Đăng nhập Azure Portal, Cloud Shell hoặc Azure CLI và xác nhận đúng subscription đang thao tác.
- Tạo resource group có quy ước tên, region và tags rõ ràng.
- Lập ngân sách, cấu hình cảnh báo và theo dõi chi phí phát sinh.
- Dọn dẹp tài nguyên sau thực hành và kiểm tra những khoản phí có thể còn tồn tại.

## 1. Hiểu các thành phần của môi trường Azure

Trước khi tạo tài nguyên, hãy phân biệt ba khái niệm thường xuất hiện cùng nhau:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Tài khoản người dùng | Danh tính dùng để đăng nhập và thực hiện thao tác | Tài khoản cơ quan, trường học hoặc tài khoản Microsoft cá nhân |
| Tenant Microsoft Entra ID | Ranh giới danh tính chứa người dùng, nhóm, ứng dụng và cấu hình xác thực | Tenant của tổ chức hoặc tenant mặc định được tạo khi đăng ký dịch vụ |
| Azure subscription | Ranh giới quản lý tài nguyên, quyền truy cập và thanh toán | Subscription dùng cho môi trường học tập hoặc phát triển |

Một tài khoản có thể truy cập nhiều tenant; một tenant có thể liên kết với nhiều subscription. Subscription xác định phạm vi mà bạn triển khai tài nguyên và theo dõi chi phí. Tenant quản lý danh tính và xác thực. Do đó, đăng nhập thành công chưa chắc đã có subscription có thể triển khai tài nguyên.

Trong subscription, **resource group** là nhóm logic để tổ chức các tài nguyên có liên quan. Ví dụ, một bài thực hành có thể đặt virtual machine, virtual network, public IP và disk trong cùng một resource group. Bạn có thể xem chi phí, áp dụng tags và xóa nhóm tài nguyên khi bài thực hành kết thúc. Resource group không phải là một hóa đơn riêng; chi phí vẫn được ghi nhận theo dịch vụ và phạm vi thanh toán tương ứng.

Hãy hình dung cấu trúc theo thứ tự:

~~~text
Tài khoản người dùng
    |
    +-- Tenant Microsoft Entra ID
            |
            +-- Azure subscription
                    |
                    +-- Resource group: rg-azure-lab-dev
                    |       +-- Virtual network
                    |       +-- Compute resource
                    |       +-- Storage account
                    |
                    +-- Resource group khác
~~~

Khi thực hành, luôn xác nhận tenant và subscription trước khi tạo hoặc xóa tài nguyên. Đây là bước đơn giản nhưng giúp tránh thao tác nhầm vào môi trường dùng chung hoặc môi trường sản xuất.

## 2. Chọn tài khoản và subscription

Azure có thể được sử dụng qua nhiều hình thức đăng ký. Tên chương trình, số tiền tín dụng, thời hạn dùng thử, danh sách dịch vụ miễn phí và điều kiện đủ tư cách có thể thay đổi theo quốc gia, thời điểm và loại tài khoản. Hãy đọc điều khoản hiển thị tại thời điểm đăng ký thay vì dựa vào một con số quảng cáo cũ.

### Subscription trả theo mức sử dụng

Subscription Pay-As-You-Go phù hợp khi bạn cần chủ động tạo tài nguyên và thanh toán theo mức sử dụng. Bạn thường cần cung cấp thông tin thanh toán và có thể chịu trách nhiệm cho chi phí phát sinh. Hãy kiểm tra phương thức thanh toán, loại tiền tệ, thuế và quyền tạo tài nguyên trước khi bắt đầu.

### Tài khoản Azure miễn phí

Chương trình Azure Free Account có thể cung cấp tín dụng dùng thử trong một khoảng thời gian và quyền sử dụng miễn phí có giới hạn đối với một số dịch vụ. Điều kiện, hạn mức và cách chuyển sang thanh toán có thể thay đổi. Trước khi triển khai, hãy kiểm tra:

- Tín dụng có thời hạn bao lâu và dịch vụ nào được áp dụng.
- Dịch vụ miễn phí có giới hạn theo tháng, theo số lượng hoặc theo thời gian hay không.
- Điều gì xảy ra khi tín dụng hết hạn hoặc khi kết thúc giai đoạn dùng thử.
- Subscription có tự chuyển sang hình thức trả phí hay yêu cầu xác nhận của người dùng.

Không coi nhãn “Free” là bảo đảm rằng mọi tài nguyên trong subscription đều miễn phí. Một dịch vụ có thể miễn phí trong một hạn mức nhưng tính phí khi vượt hạn mức; các tài nguyên phụ trợ như disk, địa chỉ IP, lưu lượng mạng hoặc log cũng có thể phát sinh chi phí.

### Azure for Students và subscription do tổ chức cấp

Người học đủ điều kiện có thể xem chương trình Azure for Students. Nếu đang học trong trường hoặc làm việc tại doanh nghiệp, hãy kiểm tra xem tổ chức đã cấp subscription, tenant và quyền truy cập hay chưa. Subscription do tổ chức quản lý thường có chính sách về region, loại dịch vụ, quota, quyền tạo tài nguyên và ngân sách.

Nếu dùng subscription của tổ chức:

1. Xác nhận đây là subscription dành cho học tập hoặc phát triển.
2. Hỏi người quản trị về giới hạn chi phí và dịch vụ được phép sử dụng.
3. Kiểm tra vai trò RBAC được cấp. Quyền đọc tài nguyên không đồng nghĩa với quyền tạo, thay đổi hoặc xóa tài nguyên.
4. Không tự tạo tenant hoặc đăng ký thanh toán mới nếu tổ chức đã có quy trình cấp quyền.

### Kiểm tra quyền trước khi bắt đầu

Bạn nên có quyền đăng nhập vào tenant và quyền triển khai các loại tài nguyên cần thiết trong subscription. Để tạo resource group, thông thường tài khoản cần quyền phù hợp ở subscription hoặc phạm vi cha. Để xem chi phí và tạo budget, tài khoản còn cần quyền Cost Management tương ứng; quyền này có thể khác với quyền triển khai tài nguyên.

Bật xác thực đa yếu tố (MFA) nếu tổ chức hoặc tài khoản hỗ trợ. Chỉ cấp quyền tối thiểu cần thiết cho từng người dùng. Không chia sẻ mật khẩu, mã xác thực, access token hoặc thông tin đăng nhập của tài khoản quản trị.

## 3. Chọn công cụ truy cập Azure

Bạn có thể quản lý Azure bằng giao diện web, shell trên trình duyệt hoặc công cụ dòng lệnh cài trên máy. Ba cách này bổ trợ cho nhau.

| Công cụ | Khi nên dùng | Điểm cần lưu ý |
|---|---|---|
| Azure Portal | Làm quen dịch vụ, cấu hình trực quan, xem biểu đồ và chi phí | Thao tác thủ công dễ nhầm subscription nếu không kiểm tra ngữ cảnh |
| Azure Cloud Shell | Chạy lệnh từ trình duyệt mà không cần tự cài toàn bộ công cụ | Cần đăng nhập; lưu trữ Cloud Shell có thể tạo hoặc sử dụng storage account |
| Azure CLI | Tự động hóa thao tác, lặp lại bài thực hành và viết script | Cần cài đặt, đăng nhập và chọn đúng subscription |

### Azure Portal

Mở [Azure Portal](https://portal.azure.com/) và đăng nhập bằng tài khoản đã được cấp quyền. Ở phần quản lý subscription, xác định subscription cần dùng và kiểm tra trạng thái. Giao diện Portal có thể thay đổi theo phiên bản, nhưng bạn thường có thể tìm dịch vụ bằng ô tìm kiếm ở đầu trang.

Trước khi tạo tài nguyên, kiểm tra tên subscription và tenant đang hoạt động. Nếu có nhiều subscription, đừng chọn theo tên gần giống nhau; hãy đối chiếu thêm subscription ID hoặc thông tin do tổ chức cung cấp.

### Azure Cloud Shell

Cloud Shell là môi trường dòng lệnh được cung cấp ngay trong Azure Portal. Bạn có thể chọn Bash hoặc PowerShell. Azure CLI và nhiều công cụ quản trị phổ biến đã có sẵn, vì vậy Cloud Shell tiện cho bài thực hành ngắn.

Ở lần sử dụng đầu tiên, Cloud Shell có thể yêu cầu thiết lập lưu trữ để giữ một số tệp và cấu hình. Storage account phục vụ Cloud Shell có thể phát sinh chi phí tùy cách cấu hình và mức sử dụng. Nếu subscription có chính sách nghiêm ngặt hoặc bạn không có quyền tạo storage, hãy hỏi người quản trị hoặc sử dụng Azure CLI cục bộ.

### Azure CLI trên máy cá nhân

Azure CLI phù hợp khi bạn muốn lưu các lệnh thực hành trong script và chạy lại nhiều lần. Cài đặt theo hướng dẫn chính thức dành cho hệ điều hành tại [Install the Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli). Sau khi cài đặt, mở terminal mới và kiểm tra phiên bản:

~~~bash
az version
~~~

Đăng nhập:

~~~bash
az login
~~~

Nếu môi trường không mở được trình duyệt, có thể dùng luồng đăng nhập bằng mã thiết bị khi chính sách của tổ chức cho phép:

~~~bash
az login --use-device-code
~~~

Nếu cần chỉ định tenant, dùng tenant ID do tổ chức cung cấp:

~~~bash
az login --tenant <TENANT_ID>
~~~

Không đưa mật khẩu, mã thiết bị hoặc token vào script, tài liệu chia sẻ hay repository.

## 4. Xác nhận tenant và subscription đang sử dụng

Sau khi đăng nhập, liệt kê các subscription mà tài khoản có thể truy cập:

~~~bash
az account list --output table
~~~

Kết quả thường có tên subscription, subscription ID, tenant ID và trạng thái. Nếu có nhiều subscription, chọn đúng subscription bằng ID:

~~~bash
az account set --subscription "<SUBSCRIPTION_ID>"
~~~

Kiểm tra lại ngữ cảnh hiện tại:

~~~bash
az account show --output table
~~~

Bạn cũng có thể lấy các giá trị cụ thể để dùng trong script:

~~~bash
az account show --query "{name:name, id:id, tenantId:tenantId, state:state}" --output json
~~~

Chỉ tiếp tục khi subscription có trạng thái hoạt động và đúng với môi trường được giao. Nếu không thấy subscription, hãy kiểm tra tài khoản đăng nhập, tenant đang chọn và quyền được cấp. Không tự tạo subscription mới để vượt qua vấn đề quyền truy cập của tổ chức.

## 5. Tạo resource group dành riêng cho thực hành

Nên tạo một resource group riêng cho từng bài thực hành hoặc nhóm bài có cùng vòng đời. Khi kết thúc, bạn có thể kiểm tra và dọn dẹp các tài nguyên của bài đó theo một phạm vi rõ ràng.

### Chọn tên và region

Tên resource group nên mô tả mục đích và môi trường. Ví dụ:

- **rg-azure-lab-dev**: bài thực hành Azure trong môi trường phát triển.
- **rg-azure-lab-network**: bài thực hành tập trung vào mạng.
- **rg-azure-lab-data**: bài thực hành tập trung vào dữ liệu.

Azure có quy tắc đặt tên khác nhau cho từng loại tài nguyên. Hãy kiểm tra quy tắc của dịch vụ cụ thể trước khi đặt tên; không phải mọi dịch vụ đều chấp nhận cùng một tập ký tự.

Region là vị trí địa lý nơi Azure triển khai tài nguyên. Chọn region dựa trên các yếu tố:

- Dịch vụ và SKU cần dùng có sẵn ở region đó hay không.
- Độ trễ kết nối từ người học hoặc hệ thống sử dụng.
- Yêu cầu lưu trú dữ liệu và chính sách của tổ chức.
- Giá dịch vụ, quota và khả năng triển khai trong subscription.

Không phải mọi dịch vụ đều có mặt ở mọi region. Có thể liệt kê các region mà subscription hỗ trợ bằng Azure CLI:

~~~bash
az account list-locations --output table
~~~

Ví dụ bên dưới sử dụng **southeastasia** làm region minh họa. Hãy thay bằng region đã được tổ chức cho phép và có dịch vụ cần thiết.

### Tạo resource group bằng Azure CLI

~~~bash
az group create --name rg-azure-lab-dev --location southeastasia --tags environment=learning owner=student purpose=azure-practice
~~~

Trong PowerShell, bạn cũng có thể chạy lệnh trên một dòng như ví dụ để tránh khác biệt về ký tự nối dòng giữa các shell.

Xem thông tin resource group vừa tạo:

~~~bash
az group show --name rg-azure-lab-dev --output table
~~~

Các tags như **environment**, **owner** và **purpose** giúp nhận diện mục đích và hỗ trợ lọc chi phí khi dịch vụ có kế thừa hoặc gắn tags phù hợp. Tags không tự tạo giới hạn chi phí và không thay thế quyền truy cập.

Bạn cũng có thể tạo resource group trong Azure Portal bằng cách tìm **Resource groups**, chọn **Create**, chọn subscription, nhập tên, region và tags, rồi xác nhận. Sau khi tạo, mở resource group để kiểm tra subscription, region và tags.

## 6. Lập ngân sách trước khi triển khai dịch vụ

Azure tính phí theo loại dịch vụ, cấu hình, thời gian chạy, dung lượng, số giao dịch, lưu lượng truyền dữ liệu và nhiều yếu tố khác. Một máy ảo không chỉ có chi phí compute: disk, địa chỉ IP, backup, băng thông và dịch vụ giám sát đi kèm cũng có thể tính phí.

Trước khi tạo tài nguyên, hãy đặt ra một ngân sách tối đa mà bạn có thể chấp nhận cho giai đoạn thực hành. Chẳng hạn, bạn có thể dùng **10 USD/tháng** làm con số minh họa trong bài tập cấu hình budget. Đây không phải dự báo giá hay khuyến nghị mức chi tiêu; hãy chọn số tiền phù hợp với subscription, tiền tệ thanh toán và khả năng tài chính của mình.

### Ước tính chi phí bằng Azure Pricing Calculator

Mở [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) và thêm những dịch vụ dự định sử dụng. Với mỗi dịch vụ, xác định:

- Region và loại dịch vụ hoặc SKU.
- Kích thước, số lượng và thời gian sử dụng.
- Dung lượng lưu trữ, loại redundancy và số giao dịch dự kiến.
- Lưu lượng mạng đi vào, đi ra và giữa các region.
- Các tùy chọn backup, bảo mật, hỗ trợ và giám sát.

Máy ảo chạy liên tục có thể tốn nhiều hơn máy ảo chỉ chạy trong vài giờ, nhưng dừng máy ảo chưa chắc loại bỏ toàn bộ chi phí. Disk được giữ lại, địa chỉ IP, snapshot hoặc tài nguyên mạng vẫn có thể tiếp tục được tính phí. Với dịch vụ được tính theo giao dịch hoặc dung lượng, hãy ước tính cả phần sử dụng ngoài giờ chạy.

Giá trên calculator là ước tính dựa trên cấu hình và giả định bạn nhập. Hóa đơn thực tế còn phụ thuộc vào mức sử dụng, chương trình ưu đãi, tiền tệ, thuế, hợp đồng và điều khoản thanh toán. Kiểm tra điều kiện của subscription trước khi dựa vào tín dụng miễn phí hoặc hạn mức free tier.

### Các nhóm chi phí thường bị bỏ sót

| Nhóm | Ví dụ khoản phí | Cách kiểm soát khi học |
|---|---|---|
| Compute | Virtual machine, container, app hosting, thời gian chạy | Chọn SKU nhỏ phù hợp, đặt lịch dừng hoặc xóa khi xong |
| Storage | Disk, blob, file share, snapshot, backup | Chỉ tạo dung lượng cần thiết, kiểm tra bản sao và dữ liệu còn lưu |
| Network | Public IP, NAT Gateway, load balancer, VPN, egress | Tránh tạo thành phần mạng cao cấp nếu bài học không yêu cầu |
| Database | Managed database, dung lượng, compute và backup | Chọn tier nhỏ, giới hạn thời gian chạy nếu dịch vụ hỗ trợ |
| Monitoring | Log Analytics ingestion, retention, metrics và alerts | Thu thập đúng loại log cần học, kiểm tra dung lượng và thời gian lưu |
| Bảo mật và quản trị | Một số dịch vụ bảo vệ, key management hoặc hỗ trợ | Kiểm tra bảng giá và phạm vi miễn phí trước khi bật |

Đặc biệt chú ý tài nguyên mạng và giám sát. Chúng có thể tồn tại độc lập với máy ảo hoặc ứng dụng mà bạn đang thử nghiệm, nên việc chỉ tắt ứng dụng không bảo đảm mọi chi phí đã dừng.

## 7. Tạo budget và cảnh báo chi phí

Trong Azure Cost Management, **budget** đặt một ngưỡng chi phí cho một phạm vi và khoảng thời gian. Khi chi phí thực tế hoặc chi phí dự báo chạm ngưỡng cảnh báo, Azure có thể gửi thông báo đến người nhận đã cấu hình.

Budget là công cụ theo dõi và cảnh báo; bản thân budget **không phải hạn mức chặn chi tiêu**. Nếu đạt 100% ngân sách, tài nguyên không tự động dừng chỉ vì đã chạm ngưỡng. Dữ liệu chi phí cũng có độ trễ, vì vậy thông báo có thể đến sau khi mức sử dụng đã tăng. Muốn tự động phản ứng, cần thiết kế quy trình riêng bằng automation hoặc action group phù hợp, đồng thời kiểm thử kỹ để tránh ảnh hưởng tài nguyên đang dùng.

### Cấu hình budget trong Azure Portal

Tên mục và vị trí điều hướng có thể thay đổi theo giao diện và quyền được cấp. Thông thường, bạn có thể thực hiện như sau:

1. Mở **Cost Management + Billing** trong Azure Portal.
2. Chọn đúng billing scope hoặc subscription cần theo dõi.
3. Mở **Cost Management** rồi chọn **Budgets**.
4. Tạo budget mới và chọn phạm vi. Nếu đang học trong resource group riêng, hãy chọn resource group khi loại scope và quyền của tài khoản hỗ trợ; nếu không, tạo budget ở subscription.
5. Đặt tên dễ nhận biết, ví dụ **budget-azure-lab-monthly**.
6. Chọn chu kỳ **Monthly**, ngày bắt đầu và ngày kết thúc phù hợp.
7. Nhập số tiền ngân sách theo đơn vị tiền tệ hiển thị cho scope đó.
8. Thêm các ngưỡng cảnh báo thực tế, ví dụ 50%, 80% và 100%.
9. Nhập địa chỉ email người nhận thông báo. Có thể cấu hình thêm action group nếu quy trình của tổ chức yêu cầu.
10. Kiểm tra lại scope, chu kỳ, số tiền và người nhận trước khi lưu.

Ví dụ, nếu budget minh họa là 10 USD/tháng, các ngưỡng 50%, 80% và 100% tương ứng với 5 USD, 8 USD và 10 USD. Hãy chọn ngưỡng cảnh báo đủ sớm để bạn còn thời gian kiểm tra và xóa tài nguyên. Nếu scope dùng đơn vị tiền tệ khác, hãy nhập số tiền theo đơn vị hiển thị tại scope đó.

### Chọn scope phù hợp

- **Subscription scope** theo dõi tổng chi phí trong subscription. Đây là lựa chọn phù hợp nếu subscription chỉ dành cho bạn hoặc một nhóm học tập nhỏ.
- **Resource group scope** theo dõi phạm vi của một bài thực hành. Lựa chọn này hữu ích khi nhiều nhóm tài nguyên khác nhau cùng tồn tại trong subscription.
- **Management group hoặc billing scope** có thể phù hợp với tổ chức quản lý nhiều subscription, nhưng quyền tạo budget ở các phạm vi này thường do bộ phận quản trị kiểm soát.

Không phải tài khoản nào cũng có quyền xem chi phí hoặc tạo budget. Nếu không thấy dữ liệu Cost Management hay nút tạo budget, hãy kiểm tra scope và quyền Cost Management với người quản trị. Không suy luận rằng không có chi phí chỉ vì bạn không nhìn thấy báo cáo.

### Theo dõi chi phí định kỳ

Sau khi tạo budget:

- Mở **Cost analysis** để xem chi phí theo thời gian và nhóm dịch vụ.
- Lọc theo subscription, resource group, service hoặc tags khi các chiều dữ liệu đó khả dụng.
- So sánh chi phí thực tế với chi phí dự báo và ngưỡng budget.
- Kiểm tra người nhận cảnh báo có thể nhận email hay không.
- Xem lại các tài nguyên đang chạy và các tài nguyên phụ trợ còn tồn tại.

Nên kiểm tra chi phí sau mỗi buổi thực hành và trước khi kết thúc tuần học. Không đợi đến khi nhận cảnh báo 100% mới xem lại tài nguyên.

## 8. Quy trình thực hành an toàn cho mỗi bài học

Áp dụng quy trình sau mỗi khi bắt đầu một bài thực hành Azure:

1. **Xác nhận danh tính và subscription:** đăng nhập đúng tài khoản, tenant và subscription.
2. **Đọc yêu cầu bài học:** xác định dịch vụ, region, quota và quyền cần thiết.
3. **Ước tính chi phí:** tra cứu các dịch vụ trong Pricing Calculator và kiểm tra điều kiện free tier nếu có.
4. **Chọn scope theo dõi:** dùng budget ở subscription hoặc resource group, tùy quyền và phạm vi học tập.
5. **Tạo resource group riêng:** gắn tags để biết ai sở hữu và dùng cho mục đích gì.
6. **Triển khai tối thiểu:** chỉ tạo các tài nguyên cần cho mục tiêu học, ưu tiên SKU nhỏ phù hợp.
7. **Quan sát và ghi nhận:** kiểm tra trạng thái, log và chi phí trong quá trình thực hành.
8. **Dọn dẹp:** xóa tài nguyên không còn cần thiết và xác nhận trạng thái sau khi xóa.
9. **Kiểm tra lại chi phí:** xem các khoản còn phát sinh và xử lý tài nguyên bị bỏ sót.

### Kiểm tra ngữ cảnh bằng CLI

Trước khi triển khai, có thể chạy lại các lệnh sau:

~~~bash
az account show --output table
az group list --output table
~~~

Nếu cần xem tags của resource group:

~~~bash
az group show --name rg-azure-lab-dev --query "{name:name, location:location, tags:tags}" --output json
~~~

Lệnh CLI chỉ xác nhận thông tin tài nguyên; nó không thay thế việc kiểm tra budget và báo cáo chi phí trong Cost Management.

## 9. Dọn dẹp tài nguyên sau thực hành

Khi bài học kết thúc, hãy xác định resource group nào chỉ phục vụ bài thực hành. Trước khi xóa, kiểm tra xem có tài nguyên hoặc dữ liệu nào cần giữ lại hay không. Không xóa resource group dùng chung hoặc resource group của môi trường sản xuất.

Nếu toàn bộ tài nguyên trong nhóm chỉ phục vụ bài thực hành và có thể xóa, chạy:

~~~bash
az group delete --name rg-azure-lab-dev --yes
~~~

Lệnh trên yêu cầu xóa resource group và các tài nguyên nằm trong nhóm. Quá trình xóa có thể mất thời gian. Bạn có thể kiểm tra nhóm còn tồn tại hay không:

~~~bash
az group exists --name rg-azure-lab-dev
~~~

Kết quả **false** cho biết resource group không còn tồn tại. Nếu lệnh trả về **true**, hãy kiểm tra tiến trình xóa hoặc lỗi được báo.

Xóa resource group không phải lúc nào cũng loại bỏ mọi khoản phí liên quan đến bài học. Hãy kiểm tra thêm:

- Tài nguyên được tạo ở resource group khác hoặc ở cấp subscription.
- Disk, snapshot, backup, image hoặc dữ liệu được giữ lại theo chính sách của dịch vụ.
- Storage account được dùng cho Cloud Shell.
- Log, dữ liệu giám sát hoặc dịch vụ có chính sách lưu giữ riêng.
- Tài nguyên có soft delete, retention hoặc lock ngăn việc xóa hoàn toàn.

Sau khi dọn dẹp, mở Cost analysis và theo dõi các kỳ cập nhật tiếp theo để phát hiện khoản phí còn lại. Một số dữ liệu chi phí được cập nhật trễ; việc resource group đã biến mất không đồng nghĩa báo cáo chi phí lập tức về 0.

## 10. Bảo vệ tài khoản và môi trường học tập

Một môi trường thực hành tốt cần an toàn ngay từ lúc đăng nhập:

- Bật MFA và sử dụng tài khoản riêng của từng người học.
- Dùng RBAC với quyền tối thiểu cần thiết; tránh sử dụng tài khoản Global Administrator cho thao tác triển khai thông thường.
- Không lưu password, secret, token hoặc khóa truy cập trong mã nguồn hay tệp cấu hình được commit.
- Không mở cổng mạng công khai hoặc cấp quyền truy cập rộng nếu bài học không yêu cầu.
- Dùng resource group và tags riêng để nhận diện tài nguyên học tập.
- Kiểm tra policy, quota và giới hạn region do tổ chức áp dụng.
- Xóa hoặc thu hồi thông tin xác thực thử nghiệm khi không còn cần thiết.

Nếu cần tự động hóa bằng service principal hoặc managed identity trong các bài học sau, hãy tạo danh tính với phạm vi và quyền tối thiểu phù hợp. Không dùng thông tin xác thực của người dùng cá nhân làm bí mật cố định trong script.

## 11. Xử lý một số vấn đề thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Đăng nhập thành công nhưng không thấy subscription | Đăng nhập nhầm tenant, tài khoản chưa được gán subscription hoặc chưa được cấp quyền | Kiểm tra tenant ID, chạy **az account list** và liên hệ quản trị viên |
| **az group create** báo không đủ quyền | Thiếu quyền tạo resource group ở subscription hoặc phạm vi cha | Xác nhận subscription và yêu cầu vai trò RBAC phù hợp |
| Không tạo được tài nguyên ở region đã chọn | Dịch vụ/SKU không khả dụng, quota không đủ hoặc policy chặn region | Kiểm tra region hỗ trợ, quota và policy; chọn region được phép |
| Không tạo được budget | Thiếu quyền Cost Management hoặc đang ở sai scope | Kiểm tra billing scope, subscription và quyền Cost Management |
| Không nhận được cảnh báo ngân sách | Ngưỡng chưa đạt, email sai, cấu hình thông báo chưa đúng hoặc dữ liệu chi phí cập nhật trễ | Kiểm tra cấu hình budget, người nhận và Cost analysis |
| Chi phí vẫn xuất hiện sau khi xóa máy ảo | Disk, IP, snapshot, backup hoặc tài nguyên phụ trợ vẫn còn | Kiểm tra resource group, các nhóm khác và báo cáo theo dịch vụ |
| Không thấy chi phí ngay sau khi tạo tài nguyên | Dữ liệu Cost Management chưa được cập nhật | Kiểm tra lại sau; không coi báo cáo chưa có dữ liệu là bằng chứng dịch vụ miễn phí |

Khi gặp lỗi, lưu lại thông báo lỗi, tên subscription, resource group và lệnh đã chạy. Không chia sẻ token hoặc thông tin đăng nhập trong báo cáo lỗi.

## 12. Bài thực hành: chuẩn bị một sandbox Azure

Mục tiêu là chuẩn bị một phạm vi thử nghiệm có thể nhận diện, theo dõi và xóa được. Bài tập này chỉ tạo resource group; chưa cần triển khai máy ảo hay dịch vụ có thể phát sinh chi phí lớn.

### Yêu cầu

- Có quyền truy cập một Azure subscription dành cho học tập hoặc phát triển.
- Có thể mở Azure Portal hoặc sử dụng Azure CLI.
- Biết region được phép sử dụng trong subscription.

### Các bước thực hiện

1. Đăng nhập Azure Portal hoặc chạy **az login**.
2. Chạy **az account list --output table**, chọn đúng subscription và xác nhận bằng **az account show**.
3. Tra cứu region được hỗ trợ bằng **az account list-locations --output table**.
4. Trong Cost Management, tạo budget ở scope phù hợp. Có thể dùng 10 USD/tháng làm giá trị minh họa nếu đơn vị tiền tệ và quyền của subscription cho phép.
5. Tạo các cảnh báo ở 50%, 80% và 100%; xác nhận người nhận email.
6. Tạo resource group với tên **rg-azure-lab-dev**, region được phép và tags **environment=learning**, **owner=student**, **purpose=azure-practice**.
7. Mở resource group trong Portal hoặc chạy **az group show** để kiểm tra tên, region và tags.
8. Xóa resource group bằng **az group delete --name rg-azure-lab-dev --yes**.
9. Chạy **az group exists --name rg-azure-lab-dev** để xác nhận kết quả.
10. Mở Cost analysis và ghi nhận thời điểm kiểm tra, scope, các dịch vụ được liệt kê và những khoản phí còn lại nếu có.

### Kết quả cần ghi lại

| Nội dung | Giá trị cần ghi |
|---|---|
| Tenant ID | Tenant đang đăng nhập |
| Subscription name và ID | Subscription dùng cho bài tập |
| Region | Region đã chọn |
| Resource group | Tên nhóm và tags |
| Budget | Scope, chu kỳ, số tiền và ngưỡng cảnh báo |
| Cleanup | Thời điểm xóa và kết quả **az group exists** |
| Cost analysis | Thời điểm xem báo cáo và các khoản chi phí quan sát được |

### Câu hỏi tự kiểm tra

1. Tenant Microsoft Entra ID và Azure subscription quản lý những khía cạnh nào khác nhau?
2. Vì sao cần chạy **az account show** trước khi tạo hoặc xóa tài nguyên?
3. Resource group giúp quản lý vòng đời của tài nguyên như thế nào?
4. Budget có tự động chặn việc triển khai hoặc dừng tài nguyên khi đạt 100% không? Vì sao?
5. Hãy nêu ba khoản phí có thể tiếp tục phát sinh sau khi dừng một virtual machine.
6. Vì sao cần kiểm tra Cost analysis sau khi xóa resource group?

## 13. Tài liệu tham khảo

- [Azure Portal](https://portal.azure.com/) — giao diện quản lý dịch vụ Azure.
- [Install the Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) — cài đặt Azure CLI.
- [Azure Cloud Shell overview](https://learn.microsoft.com/azure/cloud-shell/overview) — cách hoạt động và yêu cầu của Cloud Shell.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — ước tính chi phí theo cấu hình dịch vụ.
- [Create and manage budgets](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets) — hướng dẫn tạo và quản lý budget.

Luôn đối chiếu tài liệu và bảng giá hiện hành trước khi triển khai. Giao diện, tên chương trình ưu đãi, hạn mức miễn phí và giá dịch vụ có thể thay đổi theo thời gian, region và thỏa thuận thanh toán.
