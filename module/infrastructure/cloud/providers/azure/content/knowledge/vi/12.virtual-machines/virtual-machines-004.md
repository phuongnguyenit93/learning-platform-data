# Khởi tạo cấu hình bằng cloud-init và VM extension

Một máy ảo Azure vừa được tạo từ image Ubuntu thường chỉ mới có hệ điều hành, tài khoản quản trị và cấu hình mạng cơ bản. Ứng dụng sản xuất còn cần gói phần mềm, tệp cấu hình, dịch vụ chạy nền, agent giám sát và các chính sách vận hành. Nếu cấu hình thủ công qua SSH cho từng máy, nhóm triển khai dễ quên bước, tạo khác biệt giữa môi trường dev/prod và khó phục hồi khi phải thay máy.

Trên Microsoft Azure, có hai cách quan trọng để tự động hóa công việc này:

- **cloud-init**: khởi tạo máy Linux từ dữ liệu cấu hình được cung cấp trong giai đoạn provision, thường ở lần boot đầu tiên.
- **Azure VM extensions**: cài agent hoặc thực thi tác vụ cấu hình trên một VM đã được Azure quản lý thông qua **Azure VM Agent**, kể cả sau khi VM được tạo.

Hai cơ chế bổ sung cho nhau, nhưng khác nhau về vòng đời, trách nhiệm, cách kiểm tra kết quả và rủi ro bảo mật. Bài học thuộc chương **Máy ảo Azure**, gắn với việc triển khai, giám sát và bảo vệ ứng dụng trên Azure từ subscription, resource group, Microsoft Entra ID, mạng ảo, compute đến lưu trữ và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích provisioning VM, bootstrapping và configuration management khác nhau ra sao.
2. Viết tệp **cloud-config** để cài gói, tạo tệp cấu hình và khởi động dịch vụ trên Linux VM.
3. Sử dụng tùy chọn **custom data** của Azure CLI và đọc log cloud-init sau khi tạo VM.
4. Phân biệt **Azure VM Agent** với cloud-init và nhận diện vai trò của các VM extension.
5. Cấu hình minh họa **Custom Script Extension** trên Linux và kiểm tra trạng thái extension.
6. Thiết kế các bước chạy lặp an toàn, xử lý phụ thuộc, bí mật, mạng và nguồn phần mềm.
7. Chẩn đoán lỗi cloud-init, extension, quyền truy cập và khởi động ứng dụng.
8. Chọn cơ chế phù hợp với kiến trúc VM, VM Scale Sets và quy trình Infrastructure as Code.

## 1. Provisioning và bootstrap trong vòng đời VM

**Provisioning** là quá trình Azure cấp phát tài nguyên VM: chọn image, tạo đĩa hệ điều hành, NIC, phân bổ tài nguyên tính toán và chuẩn bị hệ điều hành. **Bootstrapping** là các bước biến máy vừa tạo thành một máy sẵn sàng chạy workload, ví dụ cài Nginx, cấu hình thời gian, tạo thư mục dữ liệu và bật một dịch vụ.

**Configuration management** có phạm vi dài hơn bootstrapping: đảm bảo cấu hình tiếp tục đúng khi ứng dụng thay đổi, máy được cập nhật và chính sách vận hành được điều chỉnh. Những hệ thống như Ansible, Chef, Puppet, DSC, hoặc quy trình triển khai riêng có thể bổ sung cho cloud-init và VM extensions.

~~~text
ARM / Bicep / Terraform / Azure CLI
             |
             v
       Azure tạo VM
             |
             v
   Image + OS disk + NIC + compute
             |
             v
 Linux boot, cloud-init nhận custom data
             |
             v
 Cài gói / ghi cấu hình / bật dịch vụ
             |
             +--------> Ứng dụng sẵn sàng?
             |
             v
 VM Agent quản lý VM extensions
             |
             v
 Agent monitoring / Custom Script / cấu hình bổ sung
             |
             v
 Health check + logs + giám sát + vận hành
~~~

Sơ đồ trên minh họa các trách nhiệm, **không cam kết thứ tự tuyệt đối giữa tất cả tác vụ cloud-init và extension**. Trong một triển khai thực tế, extension có thể được khai báo và chạy trong thời gian VM vẫn đang hoàn tất bootstrap. Nếu extension phụ thuộc kết quả cloud-init, phải có cơ chế đồng bộ/kiểm tra điều kiện sẵn sàng thay vì dựa vào giả định “khởi tạo VM thành công là mọi script đã xong”.

## 2. So sánh cloud-init và VM extension

| Tiêu chí | cloud-init | Azure VM extension |
|---|---|---|
| Vị trí chạy | Bên trong guest OS, khi cloud-init xử lý các giai đoạn khởi tạo | Bên trong guest OS, do VM Agent phối hợp với extension handler |
| Hệ điều hành điển hình | Linux image có cloud-init được hỗ trợ | Linux hoặc Windows theo extension tương ứng |
| Thời điểm | Chủ yếu khi tạo và boot một instance OS mới; tần suất từng module phụ thuộc cloud-init | Khi extension được triển khai/cập nhật và khi cơ chế extension yêu cầu |
| Cách cung cấp cấu hình | Custom data cloud-config, user-data, script hoặc cấu hình datasource phù hợp | Extension resource với public settings/protected settings |
| Dùng tốt cho | Cài gói, tạo file, user, cấu hình nền, bước first boot | Cài agent, chạy script quản trị, tích hợp tính năng Azure |
| Chạy lại | Không nên coi việc reboot là cách chạy lại toàn bộ cloud-config | Có thể cập nhật settings/force-update theo cơ chế của extension |
| Phụ thuộc chính | Image hỗ trợ cloud-init, DNS/route/repository, script | Azure VM Agent, extension handler, đường tới artifact/dịch vụ cần thiết |
| Giám sát | cloud-init status, log và trạng thái ứng dụng | Azure extension status/substatus, log extension và trạng thái ứng dụng |
| Quản lý bí mật | Không đặt mật khẩu/token trong custom data | Dùng protected settings/identity theo hỗ trợ, vẫn phải bảo vệ log và máy |

**Chọn nhanh:** cấu hình nền của Linux VM ngay lần đầu khởi động thường hợp với cloud-init; cần bật Azure Monitor Agent, triển khai Custom Script sau khi máy đã có hoặc quản lý tác vụ bằng ARM thì cân nhắc VM extension. Với một ứng dụng sản xuất, có thể cần **cả hai**.

### Cloud-init không phải dịch vụ Azure VM Agent

Trên nhiều image Linux Azure, **cloud-init** nhận dữ liệu khởi tạo từ nguồn dữ liệu Azure. **Azure Linux Agent (waagent)** vẫn có thể hiện diện để hỗ trợ chức năng Azure VM Agent và extension. Không nên tắt hoặc gỡ VM Agent chỉ vì cloud-init đang xử lý provisioning; việc đó có thể làm hỏng tính năng mở rộng hoặc thao tác quản lý VM.

Đối với **Windows VM**, Azure không dùng cloud-init Linux theo ví dụ của bài này. Các lựa chọn thường liên quan tới image customization, unattend, PowerShell, Custom Script Extension dành cho Windows hoặc công cụ quản lý cấu hình tương ứng.

## 3. Cloud-init là gì và cấu hình cloud-config

**cloud-init** là công cụ khởi tạo instance Linux, có thể thực hiện các tác vụ như tạo người dùng, cấu hình khóa SSH, cài package, ghi tệp hoặc chạy lệnh. Trên Azure, image Linux phải có phiên bản cloud-init và các thành phần tích hợp nền tảng được hỗ trợ.

Tệp **cloud-config** thường bắt đầu bằng dòng:

~~~yaml
#cloud-config
~~~

Sau đó là nội dung YAML gồm các khóa được cloud-init hỗ trợ. Những khóa thông dụng:

| Khóa | Vai trò |
|---|---|
| **package_update** | Làm mới metadata package trước khi cài theo điều kiện của distro |
| **packages** | Danh sách package cần cài bằng package manager của hệ điều hành |
| **write_files** | Tạo nội dung tệp và đặt owner/permissions |
| **users** | Khai báo hoặc điều chỉnh người dùng theo schema được hỗ trợ |
| **runcmd** | Khai báo lệnh cần chạy ở giai đoạn thích hợp của cloud-init |
| **bootcmd** | Tác vụ sớm trong boot; có thể chạy nhiều lần theo tần suất module |
| **final_message** | Thông báo khi cloud-init hoàn tất |

Cloud-init có nhiều stage và module với **frequency** khác nhau: per-instance, per-boot, per-once. Không nên kết luận mọi khóa đều chạy lại ở mỗi lần reboot. Đặc biệt, **runcmd** thường được thực thi ở giai đoạn final của lần khởi tạo instance, không phải công cụ bảo trì cấu hình mỗi khi VM khởi động.

### Ví dụ cloud-config cài Nginx

Ví dụ này dành cho một **Ubuntu VM có image cloud-init được hỗ trợ**. Tệp được đặt tên **cloud-init.yaml** trên máy dùng Azure CLI:

~~~yaml
#cloud-config
package_update: true

packages:
  - nginx

write_files:
  - path: /opt/bootstrap/site-index.html
    owner: root:root
    permissions: '0644'
    content: |
      <!doctype html>
      <html lang="vi">
        <head><meta charset="utf-8"></head>
        <body><h1>Azure VM duoc khoi tao bang cloud-init</h1></body>
      </html>

runcmd:
  - [install, -m, '0644', /opt/bootstrap/site-index.html, /var/www/html/index.html]
  - [systemctl, enable, --now, nginx]

final_message: "cloud-init da hoan tat bootstrap co ban."
~~~

Ý nghĩa:

1. **package_update** cập nhật danh mục package.
2. **packages** yêu cầu cài Nginx bằng package manager phù hợp.
3. **write_files** tạo một file nguồn nằm ngoài document root; tránh phụ thuộc file HTML mặc định của package.
4. **runcmd** sao chép nội dung sang thư mục web sau khi package được cài, rồi cho Nginx khởi động.
5. **final_message** hỗ trợ nhận biết mốc hoàn tất trong log.

Nếu repository không truy cập được, package không tồn tại trong image hoặc service không thể khởi động, cloud-init có thể báo lỗi dù VM đã xuất hiện trong Azure portal. Cần kiểm tra kết quả từ **bên trong VM**, không chỉ nhìn trạng thái ARM của tài nguyên.

### Vì sao chọn định dạng YAML và file riêng?

Cloud-config dễ đưa vào phiên bản nguồn và code review, nhưng YAML nhạy với thụt lề, kiểu dữ liệu và dấu nháy. Tệp chỉ cần sai một mức indentation là khóa hoặc danh sách có thể không còn đúng schema.

Không nhúng vào cloud-config password, connection string, SAS token hoặc private key. **Custom data không được thiết kế để giữ bí mật.** Nội dung cấu hình và đầu ra có thể được lưu trong hệ thống provision, trên đĩa guest hoặc log tùy cơ chế; mọi thành viên có quyền quản lý VM/guest phù hợp cần được xem là có khả năng tiếp cận những dữ liệu này.

## 4. Cloud-init được chuyển vào Azure VM thế nào?

Khi tạo Linux VM, Azure cung cấp cơ chế **custom data**. Azure CLI có tùy chọn **--custom-data** nhận đường dẫn tệp; CLI xử lý encoding khi gửi yêu cầu tạo VM. Đừng tự base64 tệp rồi lại truyền qua cơ chế CLI thông thường vì có thể tạo dữ liệu bị mã hóa hai lần.

Lưu ý:

- Custom data có **giới hạn dung lượng** do Azure áp dụng; thường được nêu là tối đa **64 KiB nội dung chưa mã hóa** trong tài liệu của dịch vụ. Đừng dùng nó để nhúng bộ cài hoặc artifact lớn.
- Image Linux phải hỗ trợ cloud-init theo cách phù hợp. Một số image tùy biến hoặc image cũ không tự hiểu cloud-config.
- Cloud-init nhận dữ liệu khởi tạo và chạy các module theo tần suất của nó; sửa nội dung custom data trong cấu hình quản lý sau khi VM đã được provision **không có nghĩa cloud-init sẽ tự chạy lại** như lúc tạo VM.
- Giai đoạn reboot hoặc reimage có các đặc điểm khác nhau; nếu OS disk được tạo mới, hành vi khởi tạo lại phải được kiểm chứng theo image và quy trình của bạn.
- Các tác vụ cài package phải có mạng, DNS, proxy và nguồn repository phù hợp.

### Những lớp cấu hình có liên quan

| Lớp | Ví dụ |
|---|---|
| Azure control plane | Subscription, resource group, VM size, image, NIC, NSG, managed identity |
| Dữ liệu khởi tạo guest | cloud-config thông qua custom data |
| Mạng của guest | IP/DNS/route, proxy, repository apt, endpoint nội bộ |
| Workload | Nginx, ứng dụng API, cấu hình dịch vụ |
| Quản trị sau khởi tạo | VM extension, Azure Monitor Agent, cập nhật và thay đổi cấu hình |

Chẳng hạn, cloud-init có thể cài Nginx nhưng **không tự cấp Public IP cho VM hoặc tự mở NSG**. Muốn người dùng bên ngoài truy cập website, phải thiết kế điểm vào (Load Balancer/Application Gateway), DNS, NSG và bảo mật mạng tương ứng.

## 5. Thực hành tạo Linux VM bằng cloud-init

Đây là **lab có tạo tài nguyên và có thể phát sinh chi phí**. Chỉ thực hiện trong subscription được cấp quyền, với quota và ngân sách đã xác nhận. Lệnh là ví dụ để học; trước khi chạy, hãy kiểm tra image alias, VM size, mạng và chính sách của môi trường.

### Bước 1: chuẩn bị CLI và khóa SSH

Đăng nhập, chọn đúng subscription:

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --query "{name:name,id:id}" --output table
~~~

Chuẩn bị một cặp khóa SSH của bạn. Không sao chép private key vào repository. Ví dụ dòng lệnh bên dưới giả định public key đã nằm ở **~/.ssh/id_ed25519.pub**; thay bằng đường dẫn thật nếu khác.

### Bước 2: lưu cloud-config

Tạo file **cloud-init.yaml** với toàn bộ nội dung ví dụ ở mục 3. Kiểm tra nó là UTF-8, dòng đầu tiên chính xác **#cloud-config**, thụt lề YAML và các khóa như **packages**, **write_files**, **runcmd**.

### Bước 3: tạo resource group

~~~bash
az group create \
  --name rg-vm-init-lab \
  --location southeastasia
~~~

### Bước 4: tạo VM từ image có cloud-init

~~~bash
az vm create \
  --resource-group rg-vm-init-lab \
  --name vm-init-lab \
  --location southeastasia \
  --image Ubuntu2204 \
  --size Standard_B2s \
  --admin-username azureuser \
  --ssh-key-values ~/.ssh/id_ed25519.pub \
  --custom-data ./cloud-init.yaml \
  --public-ip-address ""
~~~

**Các lưu ý vận hành:**

- Alias image **Ubuntu2204** và VM size **Standard_B2s** chỉ minh họa; phải xác minh SKU/image khả dụng trong region và subscription.
- Tùy chọn **--public-ip-address ""** thể hiện chủ đích không cấp Public IP trực tiếp cho máy, nên cần kênh quản trị riêng như Azure Bastion, VPN hoặc kết nối quản trị qua VNet. Một số môi trường có chính sách buộc dùng subnet/VNet có sẵn; hãy dùng đúng tham số mạng theo kiến trúc.
- Azure CLI có thể tạo một số tài nguyên mạng phụ trợ khi bạn chưa chỉ rõ VNet/NIC. Trong production nên khai báo rõ VNet, subnet, NSG và chọn mô hình mạng được kiểm soát bằng IaC.
- Việc command **az vm create** trả thành công không chứng minh trang HTML/Nginx đã hoạt động; cần kiểm tra guest OS và service.

### Bước 5: xác minh bên trong VM

Khi đã kết nối tới VM bằng phương pháp quản trị được cấp quyền, chạy:

~~~bash
cloud-init status --wait
cloud-init status --long

sudo tail -n 100 /var/log/cloud-init.log
sudo tail -n 100 /var/log/cloud-init-output.log

systemctl is-active nginx
curl -fsS http://127.0.0.1/
~~~

Kết quả mong đợi:

- Cloud-init hoàn thành mà không có lỗi chặn bootstrap.
- Nginx ở trạng thái **active**.
- HTTP request nội bộ tới **127.0.0.1** trả nội dung trang do cloud-config tạo.

**Nếu VM không có Public IP**, đừng cố SSH trực tiếp từ Internet. Bài lab cố ý tách bootstrap của guest khỏi việc công khai cổng ứng dụng.

### Bước 6: xác minh từ Azure control plane

~~~bash
az vm show \
  --resource-group rg-vm-init-lab \
  --name vm-init-lab \
  --query "{name:name,state:provisioningState,location:location}" \
  --output json

az vm get-instance-view \
  --resource-group rg-vm-init-lab \
  --name vm-init-lab \
  --output json
~~~

Những lệnh này giúp xem thông tin trạng thái VM từ Azure. Chúng không thay thế **cloud-init status**, log hoặc health check của ứng dụng ở bên trong máy.

## 6. Azure VM Agent và cơ chế extension

**Azure VM Agent** là thành phần guest hỗ trợ Azure quản lý các extension trong VM. Trên Linux, Azure Linux Agent thường được gọi là **waagent**. Azure điều phối yêu cầu cài extension từ control plane; VM Agent nhận cấu hình, gọi **extension handler** tương ứng trong hệ điều hành, theo dõi trạng thái và báo kết quả.

Các thành phần liên quan:

~~~text
Azure Resource Manager
        |
        v
VM extension resource
  publisher / type / version
  settings / protectedSettings
        |
        v
Azure VM Agent bên trong guest
        |
        v
Extension handler
        |
        v
Script / agent cài đặt / tác vụ cấu hình
        |
        v
Status + substatus + log + output ứng dụng
~~~

Một VM extension là **tài nguyên con** của VM theo cấu trúc Azure Resource Manager. Vì thế, extension có thể được khai báo bằng Azure portal, Azure CLI, ARM/Bicep hoặc Terraform theo cách tổ chức triển khai.

### Các loại extension thường gặp

| Loại | Mục đích minh họa |
|---|---|
| **Custom Script Extension (Linux)** | Tải/thi hành script tùy chỉnh khi cần cấu hình hoặc thao tác quản trị |
| **Custom Script Extension (Windows)** | Thực thi script tương ứng trên Windows VM; publisher/type khác Linux |
| **Azure Monitor Agent extension** | Cài agent thu thập telemetry theo cơ chế Azure Monitor, kết hợp Data Collection Rule khi cần |
| Extension dành cho quản lý và bảo mật | Cài cấu phần phục vụ giám sát, xác thực hoặc các tính năng Azure được hỗ trợ |

Tên publisher, extension type, version và hỗ trợ hệ điều hành **không thể hoán đổi tùy ý**. Ví dụ, Custom Script dành cho Linux thường có publisher **Microsoft.Azure.Extensions** và type **CustomScript**, trong khi Custom Script dành cho Windows có thể có publisher/type khác.

### Public settings và protected settings

Một extension có cấu hình **settings** và có thể có **protectedSettings**. Public settings được xem như dữ liệu cấu hình có thể được đọc từ ARM theo quyền tương ứng; **không đặt bí mật trong public settings**. Protected settings được bảo vệ theo cơ chế extension, nhưng điều đó không có nghĩa log của script, tiến trình guest hoặc tệp tạm đã an toàn. Hãy sử dụng managed identity, Azure Key Vault và quyền truy cập tối thiểu khi có thể, đồng thời tránh in secret vào stdout/stderr.

Không dùng Custom Script Extension làm nơi lưu giữ password lâu dài. Nếu script cần artifact hoặc gói nội bộ, nên thiết kế cơ chế tải xuống có xác thực, kiểm tra integrity và quyền tới nguồn dữ liệu.

## 7. Custom Script Extension: cấu hình ví dụ trên Linux

**Custom Script Extension** (CSE) cho phép chạy script/lệnh trên VM thông qua VM Agent. Có thể dùng để cài ứng dụng, tạo cấu trúc thư mục hoặc thực hiện một bước cấu hình sau khi VM đã được tạo. Đây không phải công cụ quản lý trạng thái liên tục theo kiểu “máy luôn đúng cấu hình” nếu bạn không xây thêm quy trình triển khai/kiểm chứng.

### Ví dụ một extension không cần tải script từ Internet

Giả sử VM **vm-init-lab** đã tồn tại và bạn muốn tạo một **marker** cho biết tác vụ extension đã chạy. Tạo file tên **cse-settings.json** với nội dung:

~~~json
{
  "commandToExecute": "/bin/sh -c 'mkdir -p /opt/bootstrap && touch /opt/bootstrap/extension-ready'"
}
~~~

Lệnh minh họa này không tải artifact hay dùng bí mật. Nó tạo marker ở **/opt/bootstrap/extension-ready**; việc chạy lại không tạo dữ liệu trùng gây hại. Sau khi đã xác nhận VM Agent, quyền và chi phí môi trường, triển khai extension:

~~~bash
az vm extension set \
  --resource-group rg-vm-init-lab \
  --vm-name vm-init-lab \
  --name CustomScript \
  --publisher Microsoft.Azure.Extensions \
  --settings @cse-settings.json
~~~

CLI ở đây sử dụng cú pháp **@cse-settings.json** để đọc nội dung JSON từ file tại máy chạy lệnh. Tên extension, publisher và cấu trúc settings cần phù hợp với handler Linux đã được hỗ trợ trên image/region. Lệnh này **thay đổi tài nguyên VM thật**, chỉ chạy trong lab được cho phép.

### Kiểm tra trạng thái extension

~~~bash
az vm extension show \
  --resource-group rg-vm-init-lab \
  --vm-name vm-init-lab \
  --name CustomScript \
  --output json

az vm get-instance-view \
  --resource-group rg-vm-init-lab \
  --name vm-init-lab \
  --output json
~~~

Trong guest, xác nhận marker:

~~~bash
test -f /opt/bootstrap/extension-ready \
  && echo "Extension task completed"
~~~

Kiểm tra log handler hoặc trạng thái theo phiên bản extension đang cài, ví dụ khu vực log Linux thường ở **/var/log/azure/**. Đường dẫn cụ thể và tên thư mục có thể thay đổi theo publisher/type/version; không suy đoán extension đã thành công chỉ vì lệnh triển khai kết thúc.

### Khi cần thực thi script tải từ Storage

Một kịch bản thực tế khác là CSE lấy script đã được quản lý phiên bản từ Azure Blob Storage rồi chạy nó. Thiết kế:

1. Lưu **setup.sh** tại nguồn artifact tin cậy, đã được kiểm tra và gắn version.
2. Cấu hình quyền truy cập bằng cơ chế được extension hỗ trợ, tránh lưu SAS dài hạn trong public settings.
3. Kiểm tra checksum/chữ ký artifact trước khi chạy khi có thể.
4. Script phải idempotent, có mã thoát rõ ràng và giới hạn thời gian.
5. Không để script ghi bí mật ra log.

Không dùng mô hình tải một script bất kỳ từ Internet và thực thi ngay khi chưa xác minh nguồn, nhất là trên VM production có quyền cao. CSE thường chạy các thao tác với đặc quyền hệ thống; phạm vi rủi ro lớn hơn một lệnh người dùng bình thường.

### Extension không phải công tắc “chạy lại” tự động

Custom Script Extension không nhất thiết thực thi lại khi bạn reboot VM hoặc chạy lại cùng một khai báo y hệt. Các bản cập nhật settings, phiên bản handler hoặc **force update** có cơ chế kích hoạt lại theo quy định của extension và Azure. Muốn chạy lại có chủ đích, hãy dùng cách cập nhật cấu hình được hỗ trợ và thiết kế script để lần chạy lại không gây lỗi.

Nếu một extension báo provisioning thành công nhưng ứng dụng chưa sẵn sàng, bạn vẫn phải kiểm tra tác động thật: file đã được tạo, process có đang chạy, endpoint có trả đúng nội dung, dependency có kết nối được không.

## 8. Cloud-init và extension phối hợp với nhau

Một cách phân chia trách nhiệm dễ vận hành:

| Bước | Cơ chế | Kết quả mong đợi |
|---|---|---|
| Tạo VM/NIC/managed identity | ARM/Bicep/Terraform/Azure CLI | Máy và nền tảng truy cập được cấp phát |
| Tạo user, cập nhật packages, cài Nginx | cloud-init | Nền tảng guest được bootstrap |
| Cài Azure Monitor Agent | VM extension | Có agent theo cấu hình và quyền được cấp |
| Cấu hình Data Collection Rule | Azure Monitor + ARM/IaC | Telemetry đi tới workspace/đích đã định |
| Triển khai phiên bản ứng dụng | Pipeline triển khai/extension phù hợp | Artifact có phiên bản và health check |
| Theo dõi trạng thái và rollback | Azure Monitor, logs, release process | Phát hiện lỗi và khôi phục đúng quy trình |

Trong ví dụ:

- Cloud-init chịu trách nhiệm **đưa hệ điều hành đến cấu hình nền ban đầu**.
- Custom Script Extension tạo một marker hoặc thực hiện bước cấu hình bổ sung.
- Azure Monitor Agent (nếu được triển khai) giúp thu thập telemetry theo DCR.
- Application Gateway/Load Balancer (nếu có) chỉ phân phối traffic khi workload đáp ứng health check.

### Quản lý phụ thuộc giữa các bước

Đừng giả định extension luôn chạy **sau khi toàn bộ runcmd hoàn tất** chỉ vì các resource được khai báo trong cùng template. Nếu extension cần Nginx hoặc file do cloud-init tạo, nên:

1. Tách trách nhiệm rõ ràng; ưu tiên cùng một cơ chế cho các bước phụ thuộc chặt.
2. Cho script extension kiểm tra điều kiện sẵn sàng trước khi thực thi tác vụ phụ thuộc.
3. Dùng timeout và thông báo lỗi khi điều kiện không xuất hiện.
4. Điều phối thứ tự ở pipeline/IaC theo khả năng hỗ trợ, đồng thời vẫn kiểm tra trạng thái bên trong guest.
5. Kiểm thử lại khi rebuild/reimage hoặc cập nhật image.

Một ví dụ điều kiện trong script:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

for attempt in $(seq 1 30); do
  if systemctl is-active --quiet nginx; then
    echo "Nginx is ready"
    exit 0
  fi
  sleep 10
done

echo "Nginx was not ready before timeout" >&2
exit 1
~~~

Đây là đoạn script minh họa; yêu cầu thực tế có thể là chờ file cấu hình, kiểm tra HTTP health endpoint hoặc điều kiện từ database. Không dùng vòng lặp vô hạn vì extension có giới hạn thời gian thực thi và có thể bị kẹt deployment.

## 9. Viết script idempotent và có thể khôi phục

**Idempotency** nghĩa là việc chạy một tác vụ nhiều lần không làm hệ thống rơi vào trạng thái không mong muốn. Đây là yêu cầu quan trọng vì VM có thể được tạo lại từ image, deployment được retry hoặc extension được cập nhật.

Ví dụ không nên:

~~~bash
echo "10.10.10.10 db.internal" >> /etc/hosts
~~~

Lệnh trên có thể thêm dòng lặp mỗi lần chạy. Một phương án tốt hơn là quản lý cấu hình qua file riêng hoặc dùng thao tác thay thế có kiểm tra trạng thái.

Ví dụ tạo file cấu hình an toàn hơn:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

install -d -m 0755 /etc/myapp

cat > /etc/myapp/app.conf.tmp <<'EOF'
[app]
environment=lab
listen_port=8080
EOF

install -m 0644 /etc/myapp/app.conf.tmp /etc/myapp/app.conf
rm -f /etc/myapp/app.conf.tmp
~~~

Với production, có thể dùng file tạm ở cùng filesystem, kiểm tra cú pháp cấu hình và **atomic rename** trước khi reload service. Script minh họa trên đủ để giải thích tính lặp lại, nhưng chưa có toàn bộ kiểm tra và rollback ở production.

### Checklist của một bootstrap script tốt

- Có **shebang**, exit code rõ ràng và dừng khi bước quan trọng thất bại.
- Không phụ thuộc vào thứ tự thực thi ngầm giữa các cơ chế.
- Có idempotency với file, package, database migration và tài nguyên cloud.
- Ghi log đủ để chẩn đoán nhưng **không ghi bí mật**.
- Có timeout/backoff phù hợp khi chờ mạng hoặc dịch vụ.
- Có cơ chế kiểm tra phiên bản artifact, checksum/chữ ký nếu dùng nguồn ngoài.
- Có health check sau cấu hình, tách biệt với thông báo script đã thoát.
- Không reboot VM một cách bất ngờ trong lúc extension đang thực thi.
- Có kế hoạch xử lý bước thất bại một phần và cơ chế rollback/redeploy.

### Bootstrap không phải migration dữ liệu

Không chạy migration database có tác dụng không đảo ngược ở mỗi VM vừa tạo nếu chưa có cơ chế điều phối và khóa riêng. Khi VM Scale Sets tạo thêm ba instance, cùng một cloud-init sẽ chạy trên ba máy; nếu cả ba cùng sửa schema dữ liệu, hệ thống có thể gặp race condition. Những thao tác toàn cục như migration thường phải nằm trong pipeline triển khai hoặc một job được kiểm soát độc lập.

## 10. Bảo mật khi dùng cloud-init và extension

### Không đưa secrets vào custom data

Ví dụ không an toàn:

~~~yaml
#cloud-config
write_files:
  - path: /etc/myapp/secrets.env
    content: |
      DB_PASSWORD=plaintext-example
~~~

Đây là **phản ví dụ**, không phải cấu hình nên dùng. Nội dung custom data không được xem là kho bí mật. Azure VM có thể lưu lại một phần cấu hình/đầu ra trong guest; bản sao template, pipeline log hoặc quyền quản trị có thể làm lộ dữ liệu.

Một kiến trúc bảo mật hơn:

1. Tạo **managed identity** cho VM bằng Azure control plane.
2. Cấp role/policy phù hợp để identity chỉ đọc bí mật cần thiết trong **Azure Key Vault**.
3. Sau khi máy khởi tạo, workload hoặc agent truy cập Key Vault qua danh tính được quản lý.
4. Dùng TLS và private networking khi yêu cầu; không ghi token/secret ra log.
5. Đặt rotation, expiration và theo dõi truy cập secrets theo chính sách.

Với extension, **protectedSettings** giúp bảo vệ một phần cấu hình nhạy cảm trong Azure, nhưng không thay thế managed identity hoặc quản lý bí mật sau khi script chạy. Trong môi trường cần kiểm soát cao, tránh thiết kế yêu cầu người vận hành đưa password trực tiếp vào dòng lệnh.

### Quyền triển khai extension

Người được phép tạo VM extension có thể chạy mã bên trong guest với quyền rất cao tùy handler. Vì vậy, cần hạn chế role ở subscription/resource group/VM, kiểm soát pipeline IaC, phê duyệt script và xem thay đổi extension như một thay đổi bảo mật quan trọng.

### Network và đường ra Internet

VM không có Public IP vẫn có thể cần truy cập apt repository, Azure control plane, endpoint giám sát hoặc nơi chứa artifact. Cần thiết kế đường **outbound** được phép qua NAT Gateway, firewall hoặc phương án hỗ trợ, đồng thời bảo đảm DNS phân giải đúng.

Một mô hình bảo mật tốt là nguồn package/artifact được chọn lọc, egress giới hạn, mirror/private repository phù hợp, checksum đáng tin cậy và log thay đổi rõ ràng. Không mở toàn bộ Internet hoặc tắt firewall chỉ vì cloud-init cài package không thành công.

### Vùng lưu trữ cấu hình và log

- Không đưa khóa bí mật trong các câu lệnh được ghi vào **cloud-init-output.log**.
- Kiểm soát quyền đọc file cấu hình do **write_files** tạo.
- Extension có thể ghi log/tham số trên guest; bảo vệ máy và log theo mức độ nhạy cảm.
- Với script tải xuống, kiểm tra nguồn và integrity trước khi thực thi.
- Giữ image/agent/extension được cập nhật bằng quy trình vá lỗi phù hợp.

## 11. Kiểm tra và chẩn đoán cloud-init

### Nơi xem trạng thái

Trong Linux VM:

~~~bash
cloud-init status
cloud-init status --long

sudo less /var/log/cloud-init.log
sudo less /var/log/cloud-init-output.log
~~~

**cloud-init.log** thường ghi hoạt động của các module và chi tiết lỗi. **cloud-init-output.log** thường chứa stdout/stderr của những tác vụ đã chạy. Những file này phải được xem là nguồn dữ liệu nhạy cảm nếu script lỡ in token hoặc dữ liệu ứng dụng.

### Cách phân biệt lỗi

| Triệu chứng | Nguyên nhân thường gặp | Bước kiểm tra |
|---|---|---|
| cloud-init không nhận nội dung | Image không hỗ trợ, thiếu header, custom data sai/encoding | Xem image, dòng #cloud-config, log datasource và thông số tạo VM |
| Không cài được package | Không có DNS/egress, repository lỗi, apt lock | Kiểm tra mạng/DNS, apt logs và cloud-init-output.log |
| write_files không tạo tệp | YAML sai indentation/schema, quyền hoặc đường dẫn không hợp lệ | Xem cloud-init.log, kiểm tra quyền và nội dung file |
| runcmd không chạy như mong đợi | Lỗi cú pháp, phụ thuộc chưa tồn tại, command exit non-zero | Xem cloud-init-output.log và trạng thái các module |
| Reboot nhưng không chạy lại script | Module per-instance đã chạy | Kiểm tra frequency; dùng công cụ quản lý cấu hình nếu cần thay đổi lâu dài |
| VM hiển thị Succeeded nhưng web lỗi | Azure đã provision tài nguyên, guest bootstrap/app thất bại | Xem systemctl, curl localhost, cloud-init status và log |
| VM dùng custom image không có cloud-init | Image chưa cấu hình datasource/agent thích hợp | Kiểm tra bước chuẩn bị image và khả năng hỗ trợ cloud-init |

### Cần làm gì khi cloud-init thất bại?

1. Ghi nhận VM name, image, thời gian tạo, nội dung cloud-config **đã được loại bỏ secrets** và mã lỗi.
2. Kiểm tra stage bị lỗi qua status/log.
3. Phân loại lỗi YAML, network, package, permission hoặc dependency.
4. Sửa cấu hình nguồn trong repository/IaC; tạo một VM lab mới để kiểm thử quy trình first boot.
5. Chỉ cân nhắc chạy lại module/clean cloud-init khi hiểu cơ chế và tác động của nó. Dùng lệnh **cloud-init clean** trên VM đang phục vụ workload có thể gây thực thi lại các bước không mong đợi; không xem đó là nút “retry an toàn”.

## 12. Kiểm tra và chẩn đoán VM extension

Các lệnh Azure CLI:

~~~bash
az vm extension list \
  --resource-group rg-vm-init-lab \
  --vm-name vm-init-lab \
  --output table

az vm extension show \
  --resource-group rg-vm-init-lab \
  --vm-name vm-init-lab \
  --name CustomScript \
  --output json
~~~

Trong guest Linux, có thể xem:

~~~bash
systemctl status walinuxagent --no-pager
sudo ls /var/log/azure/
~~~

Tên systemd unit của VM Agent **có thể khác theo distro/image**, nên nếu không tìm thấy **walinuxagent**, cần tra dịch vụ thực tế của image. Log extension thường nằm trong thư mục tương ứng dưới **/var/log/azure/**; cũng có dữ liệu trạng thái extension trong các thư mục do VM Agent quản lý.

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| Không thể cài extension | VM Agent thiếu/hỏng, type không hỗ trợ OS/region | Kiểm tra Agent, publisher/type/version và instance view |
| Handler không tải được script | DNS/route/firewall, URL sai, SAS hết hạn | Kiểm tra endpoint, quyền artifact và log extension |
| Extension báo failed | Lệnh trả exit code khác 0 hoặc timeout | Xem status/substatus, handler log và stderr có kiểm soát |
| Extension thành công nhưng ứng dụng chưa hoạt động | Script chưa có app health check hoặc bước chạy chưa đủ | Xem marker, systemctl, TCP/HTTP và file cấu hình |
| Chạy lại cùng cấu hình không tác động | Không có thay đổi kích hoạt handler | Kiểm tra update/force-update theo tài liệu extension |
| Extension phụ thuộc cloud-init nhưng chạy sớm | Chưa có ràng buộc sẵn sàng đúng | Đặt condition/timeout, điều phối thứ tự và kiểm thử nhiều lần |
| Tác vụ bị treo trong lúc reboot | Script tự restart VM hoặc phụ thuộc sai thời điểm | Xem lịch sử reboot, VM Agent log và thiết kế script |

Không tự xóa cài đặt extension hoặc thư mục của VM Agent chỉ để “reset” khi chưa hiểu tác động. Các extension có thể đang cung cấp giám sát hoặc kiểm soát bảo mật cho VM.

## 13. VM Scale Sets và triển khai nhiều máy

Với **Virtual Machine Scale Sets (VMSS)**, image, custom data, VM extensions và những cấu hình khác có thể được khai báo trong model của scale set theo tính năng/orchestration mode hỗ trợ. Khi VMSS tăng từ 2 lên 10 instance, những instance mới phải tự cấu hình mà không đòi hỏi người vận hành SSH vào từng máy.

Một thiết kế có tính mở rộng nên:

- Dùng image chuẩn hoặc cloud-init để chuẩn bị cấu hình nền.
- Dùng extension/agent cho telemetry, security và bước triển khai hỗ trợ.
- Giữ script **idempotent** để mỗi instance có thể tự chạy độc lập.
- Tránh nhiệm vụ toàn cục (ví dụ database migration) thực thi trùng từ nhiều instance.
- Dùng managed identity/Key Vault để truy cập cấu hình nhạy cảm thay vì sao chép secrets tới mỗi VM.
- Kiểm tra load balancer/application gateway probe để chỉ gửi traffic tới instance sẵn sàng.
- Có rolling upgrade, health checks và rollback khi cập nhật VMSS model/instances.

**Thay model của VMSS không nhất thiết ngay lập tức thay đổi mọi instance hiện có**: còn phụ thuộc upgrade policy và cơ chế áp dụng model. Cần kiểm tra trạng thái instance và chính sách triển khai trước khi kết luận một thay đổi cloud-init/extension đã có mặt trên toàn bộ fleet.

### Cloud-init, extension hay golden image?

Với nhiều VM có cấu hình nặng, việc cài hàng trăm package mỗi lần VM start có thể làm bootstrap chậm và tăng rủi ro do repository. Một **golden image** được xây dựng và kiểm thử trước có thể chứa phần mềm nền, còn cloud-init chỉ cấu hình vài giá trị theo môi trường. Extension dùng cho agent tích hợp Azure hoặc tác vụ thay đổi cần điều phối từ control plane.

Đánh đổi là image phải được bảo trì và vá lỗi. Không nhúng bí mật vào image và không để image cũ trở thành nguồn lỗ hổng lâu dài.

## 14. Giám sát, vận hành và chi phí

Khởi tạo VM không kết thúc tại dòng lệnh create thành công. Trên production, nên định nghĩa các mốc:

| Mốc | Bằng chứng |
|---|---|
| VM provisioned | Azure resource tồn tại, cấu hình VNet/OS disk đúng |
| Guest bootstrap completed | cloud-init status và các log không có lỗi chặn |
| Baseline configured | Package/service/file được kiểm tra |
| Extension healthy | VM Agent và extension status/substatus đáp ứng yêu cầu |
| Application ready | HTTP/TCP/business health check thành công |
| Observability active | Telemetry, logs và alert được xác minh |
| Security controls active | RBAC, NSG, identity, Key Vault và chính sách được áp dụng |

### Theo dõi thời gian bootstrap

Đo thời gian từ lúc tạo VM đến lúc ứng dụng thực sự healthy. Nếu thời gian quá dài:

- Kiểm tra tốc độ tải package, network/proxy và repository.
- Xác định script nào đang đợi dịch vụ bên ngoài.
- Rút những tác vụ nặng vào image build hoặc pipeline phù hợp.
- Tránh chạy nhiều bước phụ thuộc phức tạp mà không có timeout/log.
- Kiểm tra VM SKU có đủ CPU/RAM/IO cho quá trình cài đặt.

### Chi phí

Cloud-init là cơ chế khởi tạo bên trong guest, nhưng các tài nguyên nó triển khai/tải về có thể phát sinh chi phí. **VM extensions** cũng có thể cài các thành phần dẫn đến phí bổ sung, chẳng hạn dịch vụ monitoring, lưu log, bảo mật hoặc truyền dữ liệu. Phần chi phí cần xem:

- Giờ hoạt động VM, kích thước VM và OS/data disks.
- Public IP, NAT Gateway, firewall, truyền dữ liệu và dịch vụ mạng liên quan.
- Kho lưu trữ artifact, container registry, proxy hoặc image gallery.
- Azure Monitor/Log Analytics, Application Insights, retention.
- Chi phí phần mềm có license hoặc agent bên thứ ba.
- Thời gian VM không phục vụ người dùng do bootstrap kéo dài.

Đặt budget/tag chủ sở hữu trong subscription/resource group và theo dõi Azure Cost Management. Không ghi cứng một mức giá VM hay extension vì giá phụ thuộc region, SKU, plan và thời điểm.

## 15. Bài tập tình huống: triển khai API trên Linux VM

Một công ty triển khai API đơn hàng trên ba Ubuntu VM chạy sau Azure Application Gateway. Họ muốn mỗi VM được tạo cùng cấu hình:

- Cài Nginx làm reverse proxy.
- Tạo thư mục **/opt/orders-api** và file cấu hình không chứa bí mật.
- Dùng managed identity để truy cập Azure Key Vault.
- Cài Azure Monitor Agent và giám sát log.
- Chỉ nhận lưu lượng từ subnet Application Gateway; không cấp Public IP cho backend.
- Tự thay VM khi VM không healthy mà không phải cấu hình bằng tay.

Hãy thiết kế:

1. Những cấu hình nào đặt trong image, cloud-init và VM extensions?
2. Tạo mẫu cloud-config để cài Nginx, tạo file cấu hình và khởi động dịch vụ.
3. Mô tả cách cấp managed identity và quyền đọc secret trong Key Vault.
4. Xác định extension cần dùng cho telemetry và cách ghép Data Collection Rule.
5. Giải thích điều gì xảy ra nếu extension phụ thuộc Nginx nhưng cloud-init đang cài package.
6. Đề xuất health check và cách kiểm tra VM đã sẵn sàng nhận traffic.
7. Thiết kế idempotency, retry và rollback khi bước bootstrap gặp lỗi.
8. Nêu log/metric, chính sách mạng và chi phí cần theo dõi.

**Gợi ý lời giải:** image được kiểm soát có OS và package nền; cloud-init ghi cấu hình first boot, bật Nginx và khai báo ứng dụng; extension cài Azure Monitor Agent theo model IaC; managed identity truy cập Key Vault ở runtime; Application Gateway chỉ chọn VM vượt qua probe. Toàn bộ instance chạy cùng cấu hình, và database migration thực hiện từ pipeline riêng chứ không chạy ở mỗi VM.

## 16. Checklist production

| Nhóm | Điều cần xác nhận |
|---|---|
| Phạm vi | Subscription, resource group, region và owner đúng |
| Image | Image được hỗ trợ, có cloud-init/VM Agent theo yêu cầu |
| Cloud-config | YAML hợp lệ, có header, không chứa bí mật |
| Custom data | Kích thước trong giới hạn, encoding đúng, nguồn được review |
| Mạng | DNS, apt repo, artifact, Key Vault, route/egress và NSG được thiết kế |
| IAM | Managed identity/RBAC tối thiểu, không dùng token cố định |
| Bootstrap | Package/file/service hoàn tất và app health check PASS |
| Extension | Publisher/type/version đúng OS, VM Agent hoạt động, status PASS |
| Phụ thuộc | Không dựa vào thứ tự chạy ngầm, có timeout/điều phối |
| Lặp lại | Script idempotent, không ghi trùng, không migration dữ liệu theo từng VM |
| Khôi phục | Có quy trình tạo lại VM, rollback, xử lý lỗi một phần |
| Giám sát | cloud-init log, VM extension status, Azure Monitor và alerts |
| Chi phí | VM/disk/network/log/agent có ngân sách, tài nguyên lab được dọn |

## 17. Câu hỏi tự kiểm tra

1. Khác nhau giữa provisioning VM, bootstrapping và configuration management là gì?
2. Khi nào dùng cloud-init, khi nào dùng VM extension?
3. Dòng đầu tiên của một tệp cloud-config hợp lệ là gì? Vì sao YAML indentation quan trọng?
4. **write_files**, **packages** và **runcmd** đảm nhiệm những nhiệm vụ nào?
5. Việc **az vm create** báo thành công có chứng minh Nginx đã chạy không? Cần kiểm tra bằng gì?
6. Vì sao custom data không nên chứa password hoặc token dù VM nằm trong subnet riêng?
7. Azure Linux Agent có vai trò gì đối với extensions?
8. Vì sao không dùng extension publisher/type của Windows cho Linux?
9. Public settings và protected settings khác nhau ra sao? Protected settings có thay thế Key Vault không?
10. Vì sao reboot VM không phải cách đáng tin cậy để yêu cầu cloud-init chạy lại toàn bộ?
11. Khi extension phụ thuộc file do cloud-init tạo, cần xử lý ràng buộc thời điểm thế nào?
12. Vì sao lệnh append vào cấu hình có thể không idempotent?
13. Trong VMSS, vì sao không đặt bước database migration toàn cục vào cloud-init của mỗi instance?
14. Những trường hợp nào khiến cloud-init cài package thất bại dù VM không có lỗi Azure control plane?
15. Một VM có extension báo Succeeded nhưng endpoint /health trả lỗi: việc xác minh nên tiếp tục ở đâu?
16. Tại sao cần kiểm thử cả bootstrap, agent và health check sau khi thay image hoặc VMSS model?

## Tài liệu tham khảo

- Microsoft Learn — *Use cloud-init to customize a Linux VM in Azure*: https://learn.microsoft.com/azure/virtual-machines/linux/using-cloud-init
- Microsoft Learn — *Cloud-init support for Azure VMs*: https://learn.microsoft.com/azure/virtual-machines/linux/cloudinit-prepare-custom-image
- Microsoft Learn — *Virtual machine extensions and features for Linux*: https://learn.microsoft.com/azure/virtual-machines/extensions/features-linux
- Microsoft Learn — *Custom Script Extension for Linux*: https://learn.microsoft.com/azure/virtual-machines/extensions/custom-script-linux
- Microsoft Learn — *Azure Linux VM Agent overview*: https://learn.microsoft.com/azure/virtual-machines/extensions/agent-linux
- Microsoft Learn — *Custom Script Extension for Windows*: https://learn.microsoft.com/azure/virtual-machines/extensions/custom-script-windows
- cloud-init documentation — *Examples and reference*: https://docs.cloud-init.io/en/latest/reference/examples.html
