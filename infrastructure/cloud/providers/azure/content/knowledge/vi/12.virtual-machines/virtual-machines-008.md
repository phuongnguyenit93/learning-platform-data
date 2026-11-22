# Trusted Launch, confidential VM và bảo vệ máy ảo

Máy ảo Azure (Azure Virtual Machines) cho phép chạy hệ điều hành và ứng dụng trong hạ tầng điện toán đám mây. Tuy nhiên, VM vẫn có thể chịu rủi ro từ tài khoản quản trị bị xâm phạm, image thiếu tin cậy, thành phần khởi động bị chỉnh sửa, lỗ hổng hệ điều hành, cấu hình mạng sai hoặc dữ liệu nhạy cảm bị truy cập ngoài ý muốn.

Azure cung cấp hai nhóm công nghệ quan trọng nhưng có mục tiêu bảo vệ khác nhau:

- **Trusted Launch:** tăng độ tin cậy của chuỗi khởi động bằng UEFI Secure Boot, virtual Trusted Platform Module (vTPM) và khả năng đo/đánh giá trạng thái khởi động.
- **Confidential VM:** dùng công nghệ confidential computing dựa trên phần cứng để tăng khả năng bảo vệ bộ nhớ của máy ảo khi **dữ liệu đang được xử lý (data in use)**, đồng thời có thể cung cấp bằng chứng cho cơ chế attestation.

Hai lựa chọn trên không thay thế Azure RBAC, Microsoft Entra ID, tường lửa, cập nhật hệ điều hành, mã hóa dữ liệu lưu trữ, sao lưu và giám sát. Chúng là những lớp bổ sung trong một thiết kế bảo vệ theo chiều sâu (defense in depth).

Bài học nằm trong chương **Máy ảo Azure** của mô-đun CLOUD_PROVIDERS_AZURE, kết nối các kiến thức về subscription, resource group, danh tính Entra ID, mạng ảo, điện toán, lưu trữ, giám sát, bảo mật và quản trị chi phí.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt rủi ro bảo mật của VM ở giai đoạn khởi động, lúc lưu dữ liệu, lúc truyền dữ liệu và lúc dữ liệu đang được xử lý trong RAM.
2. Giải thích Secure Boot, vTPM, measured boot và vai trò của Trusted Launch.
3. Giải thích confidential VM, khả năng cách ly bộ nhớ bằng phần cứng và attestation.
4. Lựa chọn Trusted Launch hoặc confidential VM theo threat model, image/VM size, tính năng, region và ngân sách.
5. Triển khai một Trusted Launch VM, đọc cấu hình security profile bằng Azure CLI và kiểm tra trạng thái trong guest.
6. Thiết kế các lớp bảo vệ bổ sung: quản lý quyền, mạng riêng, mã hóa, cập nhật, giám sát và backup.
7. Xây dựng checklist vận hành, xử lý sự cố và xác minh các yêu cầu bảo mật.

Kiến thức nền: Azure subscription, resource group, Azure VM, Generation 2 image, VNet, NSG, managed disk, Azure CLI và Azure RBAC. Các lệnh tạo VM trong bài chỉ dùng để minh họa; nếu thực hiện trên Azure sẽ tạo tài nguyên có thể phát sinh chi phí.

## 2. Mô hình đe dọa cho máy ảo

Trước khi chọn tính năng, hãy trả lời: **đối tượng hoặc thành phần nào có thể gây rủi ro, tài sản nào cần bảo vệ, và ta tin cậy lớp nào?**

| Tài sản/giai đoạn | Mối đe dọa điển hình | Lớp bảo vệ |
|---|---|---|
| Image máy ảo | Image không được kiểm tra, gắn mã độc hoặc phụ thuộc lỗi thời | Image được phê duyệt, kiểm tra chuỗi cung ứng phần mềm |
| Firmware/bootloader | Bootkit, bootloader hoặc thành phần boot không hợp lệ | UEFI Secure Boot |
| Trạng thái boot | Chuỗi khởi động bị sửa mà không có dấu hiệu | Measured boot, vTPM, attestation/giám sát khi hỗ trợ |
| OS và ứng dụng | Lỗ hổng, credential bị đánh cắp, local privilege escalation | Bản vá, EDR, cấu hình cứng hóa, least privilege |
| Dữ liệu trên disk | Dữ liệu được lấy từ bản sao đĩa hoặc storage không đúng quyền | Storage encryption, key management, RBAC |
| Dữ liệu trên network | Nghe lén hoặc can thiệp khi truyền | TLS/mTLS, mạng riêng, VPN/ExpressRoute khi thích hợp |
| Dữ liệu trong RAM | Nguy cơ truy cập bộ nhớ guest từ lớp hạ tầng nằm ngoài VM theo mô hình đe dọa | Confidential VM, mã hóa/cách ly bộ nhớ bằng phần cứng |
| Tài khoản quản trị | Người có quyền cao thực hiện thao tác ngoài phạm vi | Entra ID, Azure RBAC, PIM, logging và phê duyệt |
| Bản sao lưu | Xóa nhầm, ransomware, key mất khả dụng | Backup, retention, kiểm tra restore, phân quyền độc lập |

Cần phân biệt ba trạng thái: **data at rest** (đã lưu trên đĩa), **data in transit** (đang truyền) và **data in use** (đang xử lý). Mã hóa một trạng thái không mặc nhiên bảo vệ hai trạng thái còn lại.

Ví dụ, một database có mã hóa đĩa vẫn đưa dữ liệu đã giải mã vào RAM khi chạy truy vấn. Secure Boot không bảo vệ toàn bộ RAM trước lớp hạ tầng; confidential computing được thiết kế để xử lý một phần mô hình rủi ro đó. Ngược lại, confidential VM không bảo đảm ứng dụng không bị khai thác qua API.

## 3. Trusted Launch hoạt động như thế nào?

### 3.1. Trusted Launch là gì?

Trusted Launch là kiểu triển khai bảo mật dành cho các Azure VM tương thích, chủ yếu dựa trên nền tảng **Generation 2/UEFI** và tập cơ chế bảo vệ chuỗi khởi động. Mục tiêu là làm khó việc đưa các thành phần độc hại vào giai đoạn trước khi hệ điều hành và phần mềm phòng vệ khởi chạy.

Các thành phần thường được nói đến cùng nhau là Secure Boot, vTPM, measured boot và giám sát tính toàn vẹn khi tích hợp giải pháp hỗ trợ.

### 3.2. UEFI Secure Boot

**Secure Boot** xác minh chữ ký và tính hợp lệ của những thành phần boot theo cơ sở tin cậy và chính sách UEFI. Nếu một bootloader hoặc thành phần boot không được chấp thuận, firmware có thể từ chối tải thành phần đó.

Secure Boot đặc biệt liên quan tới một số kiểu bootkit/rootkit thực thi sớm. Tuy nhiên, Secure Boot **không chứng minh mọi chương trình chạy sau khi khởi động đều an toàn**. Một phần mềm được ký hợp lệ vẫn có thể chứa lỗ hổng; một ứng dụng có lỗi xác thực vẫn có thể bị tấn công từ Internet.

Khi chạy Linux, cần kiểm tra bootloader, kernel, driver và kernel module tùy biến có tương thích chính sách Secure Boot không. Một bản cập nhật hoặc image tùy biến có cấu phần chưa được ký phù hợp có thể khiến VM không boot.

### 3.3. vTPM

**Virtual Trusted Platform Module (vTPM)** cung cấp chức năng TPM 2.0 cho guest VM trong mô hình được nền tảng hỗ trợ. TPM có thể hỗ trợ các phép toán liên quan khóa và lưu những giá trị đo của chuỗi khởi động trong Platform Configuration Registers (PCR).

vTPM không phải một nơi tự động cất mọi secret của ứng dụng. Khả năng bảo vệ dữ liệu phụ thuộc cách guest OS và phần mềm sử dụng TPM, quản lý khóa và chính sách cấp quyền.

### 3.4. Measured boot khác Secure Boot ra sao?

- **Secure Boot:** kiểm tra thành phần khởi động có được phép chạy hay không.
- **Measured boot:** ghi nhận phép đo của những thành phần/trạng thái trong chuỗi boot.
- **Attestation:** một dịch vụ hoặc bên xác minh có thể dựa trên bằng chứng để đánh giá trạng thái tin cậy theo policy.

~~~mermaid
flowchart LR
    F["UEFI firmware"] --> S["Secure Boot: xác minh boot chain"]
    S --> B["Bootloader"]
    B --> O["Kernel / Operating System"]
    F --> M["Measured boot: ghi nhận bằng chứng"]
    B --> M
    O --> M
    M --> T["vTPM"]
    T --> A["Attestation / integrity monitoring"]
    A --> P["Cảnh báo hoặc đánh giá chính sách"]
~~~

Đây là luồng khái niệm; tập thành phần được đo, cách xuất bằng chứng và dịch vụ kiểm tra phụ thuộc phiên bản hệ điều hành, SKU và tích hợp thực tế.

**Kết quả đo khác baseline không tự động nghĩa là mã độc.** Việc cập nhật bootloader hoặc kernel có thể thay đổi giá trị đo. Người điều tra cần đối chiếu image version, change ticket, bản vá và các nguồn tín hiệu khác.

### 3.5. Điều kiện tương thích Trusted Launch

Trước khi triển khai cần xác nhận:

1. **Image:** hỗ trợ Generation 2 và Trusted Launch.
2. **VM size:** hỗ trợ security type tại region/subscription dự kiến.
3. **OS và boot chain:** Secure Boot tương thích bootloader, driver và kernel module.
4. **Extensions/agent:** các công cụ giám sát, bảo mật, backup và quản trị cần dùng có hoạt động không?
5. **Disk:** loại OS/data disk và cách mã hóa có tương thích không?
6. **Migration:** VM hiện hữu có thuộc trường hợp nâng cấp tại chỗ được hỗ trợ hay phải dựng VM mới?
7. **Quota, availability và cost:** còn tài nguyên và mô hình dự phòng đáp ứng nhu cầu không?

Không mặc định mọi Generation 2 VM đều được bật Trusted Launch tự động và không mặc định có thể bật tính năng này cho mọi VM Generation 1.

## 4. Confidential VM và bảo vệ dữ liệu đang dùng

### 4.1. Khái niệm

**Azure Confidential VM** sử dụng tính năng confidential computing của phần cứng CPU và nền tảng VM được hỗ trợ. Những dòng phần cứng có thể dùng công nghệ như **AMD SEV-SNP** hoặc **Intel TDX**, tùy VM family và khả năng cung cấp của Azure.

Công nghệ này tăng cường bảo vệ vùng bộ nhớ guest đang được dùng trước một số kiểu truy cập từ các thành phần ngoài ranh giới VM như hypervisor hoặc hệ thống chủ, theo mô hình đe dọa của phần cứng. Điều này khác với mã hóa đĩa vì dữ liệu phải được giải mã vào RAM để CPU xử lý.

~~~text
        CONFIDENTIAL VM (guest)
  +----------------------------------+
  | Ứng dụng và hệ điều hành         |
  | Dữ liệu đang được xử lý trong RAM|
  | Cơ chế bảo vệ dựa trên phần cứng |
  +----------------------------------+
                  |
          Ranh giới cô lập
                  |
       Hypervisor / host hạ tầng
     (bị giới hạn truy cập bộ nhớ theo
      tính năng và mô hình bảo vệ)
~~~

Confidential VM **không bảo đảm bí mật tuyệt đối**. Nếu kẻ tấn công chiếm quyền root/administrator trong guest hoặc ứng dụng tự gửi dữ liệu plaintext cho sai đối tượng, mã hóa bộ nhớ khỏi host không ngăn được. Những rủi ro về side-channel, availability, thiết bị/I/O, phần mềm trong guest và cấu hình sai vẫn phải được đánh giá.

### 4.2. Attestation

Trong confidential computing, **attestation** giúp bên kiểm tra đánh giá bằng chứng về trạng thái và thuộc tính bảo mật của môi trường tính toán. Một số nền tảng có khả năng phát hành report hoặc bằng chứng phần cứng để hệ thống khác xác minh.

~~~mermaid
sequenceDiagram
    participant V as Confidential VM
    participant P as Nền tảng/phần cứng
    participant A as Attestation verifier
    participant K as Dịch vụ quản lý khóa
    V->>P: Yêu cầu bằng chứng
    P-->>V: Báo cáo/bằng chứng phần cứng
    V->>A: Gửi bằng chứng để đánh giá
    A->>A: Kiểm tra policy và thuộc tính
    A-->>V: Kết quả xác minh
    V->>K: Yêu cầu cấp khóa theo policy
    K-->>V: Chỉ cấp nếu điều kiện đạt
~~~

Sơ đồ thể hiện **một kiến trúc có thể xây dựng**, không phải luồng tự động có sẵn trong mọi CVM. Để cấp secret dựa trên attestation, phải triển khai đầy đủ cơ chế xác minh bằng chứng, chính sách tin cậy, ràng buộc danh tính và tích hợp dịch vụ quản lý khóa được hỗ trợ.

Không chấp nhận một biến môi trường hoặc một chuỗi văn bản tự khai báo “attested=true” bên trong guest làm bằng chứng đủ mạnh. Bên ra quyết định cần nhận thông tin được xác thực bằng cơ chế tin cậy đúng.

### 4.3. Confidential VM không giống enclave

Confidential VM thường bảo vệ **một VM guest** theo ranh giới phần cứng. Một số mô hình confidential computing khác sử dụng **enclave** để thu hẹp môi trường thực thi tin cậy xuống một phần ứng dụng. Hai mô hình có yêu cầu code, công cụ, attestation và threat model khác nhau.

Nếu yêu cầu là giảm mức tin cậy vào **người quản trị guest** hoặc cô lập những phần dữ liệu khỏi chính các process khác trong cùng VM, cần nghiên cứu kiến trúc enclave hoặc biện pháp cách ly ứng dụng phù hợp; CVM đơn thuần có thể không đáp ứng.

### 4.4. Giới hạn tương thích cần đánh giá

Không phải mọi VM image, GPU, driver, OS, tính năng mạng hoặc disk đều hỗ trợ CVM. Trước khi chọn, hãy đánh giá:

- Region và confidential VM family có sẵn, quota và khả năng cấp phát.
- OS/image chuyên dụng, phiên bản kernel/driver và UEFI settings.
- Phần cứng nền tảng và cơ chế attestation tương ứng.
- Lựa chọn mã hóa OS disk, guest state, key management và disk size.
- Khả năng dùng VM extension, EDR, Azure Monitor Agent, disk snapshot và Azure Backup.
- Availability Zone, mô hình HA/DR, resize và khả năng chuyển sang region khác.
- Tính tương thích của tính năng I/O, tăng tốc mạng, nested virtualization hoặc GPU nếu workload cần.
- Ảnh hưởng chi phí và hiệu năng với mẫu tải thực tế.

Hãy kiểm tra feature matrix cho **chính VM family + image + region**. Tính năng CVM phát triển theo từng thế hệ; không nên copy toàn bộ lựa chọn từ một ví dụ khác rồi giả định chạy được.

## 5. So sánh các mô hình bảo vệ

| Tiêu chí | Azure VM thông thường | Trusted Launch | Confidential VM |
|---|---|---|---|
| Mục tiêu nổi bật | Chạy ứng dụng và OS | Đảm bảo tốt hơn tính toàn vẹn chuỗi boot | Bảo vệ thêm dữ liệu đang xử lý trong RAM trước một số thành phần ngoài guest |
| UEFI Secure Boot | Theo image/cấu hình hỗ trợ | Thành phần quan trọng | Theo thiết kế/VM family được hỗ trợ |
| vTPM và measured boot | Không mặc nhiên được bật | Thành phần đặc trưng | Có thể có cơ chế trust/attestation riêng |
| Bảo vệ RAM bằng confidential computing hardware | Không mặc nhiên | Không phải mục tiêu chính | Có theo khả năng nền tảng |
| Disk encryption | Cần thiết theo dữ liệu | Vẫn cần thiết | Cần lựa chọn phù hợp cho disk/guest state |
| Mức tương thích | Rộng hơn | Giới hạn theo Gen2/image/SKU | Giới hạn chặt theo family/image/region |
| RBAC, patching, NSG, backup | Bắt buộc xem xét | Vẫn bắt buộc | Vẫn bắt buộc |

**Trusted Launch không đồng nghĩa Confidential VM.** Secure Boot và vTPM bảo vệ/đánh giá chuỗi boot; CVM bổ sung ranh giới cách ly bộ nhớ bằng phần cứng theo threat model.

Ví dụ ra quyết định:

- VM web/app thông thường có image Gen2 được hỗ trợ: **Trusted Launch** là ứng viên tốt để tăng cường boot integrity.
- Worker phân tích dữ liệu nhạy cảm, có yêu cầu bảo vệ RAM trước một số rủi ro ở host: **đánh giá confidential VM** và tích hợp attestation nếu chính sách cấp khóa yêu cầu.
- VM chạy driver/kernel tự biên dịch hoặc phần mềm chuyên dụng: xác minh compatibility và thử image trước khi lựa chọn.
- Workload chỉ yêu cầu dữ liệu at rest được mã hóa: kiểm soát disk encryption/key management và quyền, không tự coi CVM là biện pháp bắt buộc.
- Ứng dụng có thể vận hành trên dịch vụ managed: cân nhắc App Service, Container Apps hoặc dịch vụ khác trước khi tự quản lý VM.

## 6. Thiết kế bảo vệ nhiều lớp cho Azure VM

Trusted Launch/CVM chỉ là một lớp trong hệ thống.

### 6.1. Danh tính và quản trị

- Cấp Azure RBAC theo **least privilege**, ưu tiên scope resource group/VM thay vì subscription khi đủ đáp ứng.
- Áp dụng Microsoft Entra ID, MFA, Conditional Access và Privileged Identity Management (PIM) cho tài khoản quản trị phù hợp.
- Phân biệt Azure control-plane roles với quyền root/administrator trong guest.
- Sử dụng managed identity cho ứng dụng VM khi gọi Key Vault, Storage hoặc dịch vụ Azure, tránh lưu secret trong code.
- Tách người quản trị VM, người quản trị key và người phê duyệt thay đổi khi tổ chức có thể áp dụng.
- Bật Azure Activity Log, Entra sign-in/audit log và lưu bằng chứng triển khai theo yêu cầu.

Role Owner trên Azure không thay thế quản lý nhóm sudo, local admins, SSH key hoặc quyền application.

### 6.2. Bảo vệ mạng

- Ưu tiên VM trong subnet riêng và không có public IP không cần thiết.
- Dùng NSG, Azure Firewall/NVA, UDR và phân tách mạng theo ứng dụng/môi trường.
- Truy cập SSH/RDP qua Azure Bastion, VPN/ExpressRoute hoặc đường quản trị được kiểm soát thay vì mở TCP 22/3389 ra toàn Internet.
- Khi có gói dịch vụ phù hợp, cân nhắc Just-in-Time (JIT) VM access và cảnh báo thay đổi rule.
- Bảo vệ kết nối ứng dụng bằng TLS, sử dụng Private Endpoint và kiểm soát outbound khi cần.
- Theo dõi bất thường network và các thay đổi cấu hình.

Một VM bật Secure Boot vẫn có thể bị khai thác qua ứng dụng public chưa vá. Confidential VM cũng không thay thế firewall.

### 6.3. Hệ điều hành và ứng dụng

- Dùng image từ nguồn đáng tin cậy và quy trình tạo image có kiểm soát.
- Cài patch OS/kernel/driver theo quy trình được thử nghiệm; sử dụng Azure Update Manager hoặc công cụ cập nhật phù hợp.
- Cấu hình EDR/antivirus, auditing, host firewall, least privilege và bảo vệ secrets.
- Bật log cần thiết nhưng tránh ghi token, password hoặc dữ liệu nhạy cảm.
- Rà soát lỗ hổng và software dependencies trước khi xây VM image.
- Với Secure Boot, xác minh chữ ký và khả năng khởi động sau khi cập nhật kernel/module.
- Với CVM, kiểm tra agent/extension và driver của bản image đang dùng có tương thích confidential computing.

### 6.4. Bảo vệ dữ liệu và khóa

- **Data at rest:** dùng các cơ chế mã hóa Azure Storage/Managed Disks thích hợp, quản lý khóa và policy.
- **Data in transit:** dùng TLS/mTLS và mạng riêng khi cần.
- **Data in use:** xem xét confidential computing khi threat model có yêu cầu.
- Sao lưu độc lập với disk encryption, phân quyền quản trị backup và thử restore.
- Sử dụng Key Vault hoặc Managed HSM theo khả năng tích hợp và chính sách quản lý khóa.

**Azure Disk Encryption, encryption at host, SSE, CVM disk security và các cơ chế CMK không giống nhau.** Không mặc định mọi tổ hợp được sử dụng đồng thời. Phải kiểm tra hỗ trợ theo loại VM, disk security profile, OS và region.

## 7. Checklist thiết kế trước triển khai

| Hạng mục | Câu hỏi | Kết quả ví dụ |
|---|---|---|
| Threat model | Chỉ bảo vệ boot hay thêm data in use? | Trusted Launch cho app VM; CVM cho worker nhạy cảm |
| Region và quota | Family/SKU có sẵn không? | Region được tổ chức phê duyệt |
| OS/image | Gen2 hoặc CVM image được hỗ trợ? | Image tin cậy, bản phát hành đã kiểm tra |
| VM size | Có hỗ trợ security type không? | Size đạt nhu cầu CPU/RAM và quota |
| Mạng | Public IP, Bastion, NSG ra sao? | Subnet riêng, quản trị có kiểm soát |
| Identity | Admin access và managed identity nào? | Entra RBAC, SSH key, managed identity |
| Disk/key | Encryption, guest state và key ownership thế nào? | Mô hình phù hợp khả năng hỗ trợ |
| Backup | Hỗ trợ restore với security type này? | Đã kiểm tra và chạy restore test |
| Monitoring | Thu thập boot integrity và guest alerts thế nào? | Azure Monitor + Defender for Cloud nếu bật |
| Cost | VM, disk, backup, logging, network bao nhiêu? | Budget và tag CostCenter |
| Migration | VM cũ có thể chuyển đổi không? | Runbook nâng cấp/redeploy kèm rollback |

Bảo mật được đánh giá theo kiểm soát thực tế và bằng chứng, không chỉ theo giá trị “Enabled” trên Azure Portal.

## 8. Thực hành: tạo Trusted Launch VM bằng Azure CLI

Đây là ví dụ **tạo tài nguyên có phát sinh phí**. Chỉ thực hiện trong subscription lab được phép, và xác nhận tương thích của VM size/image trước khi chạy.

### 8.1. Điều kiện

Giả sử đã có:

- Resource group **rg-vmsecurity-lab**.
- VNet **vnet-security-lab** và subnet **snet-workload** trong cùng resource group của ví dụ.
- NSG/route phù hợp và đường quản trị riêng như Bastion hoặc VPN.
- SSH key hoặc cơ chế đăng nhập đã được phê duyệt.
- Quyền tạo VM, NIC, OS disk và các tài nguyên liên quan.

Kiểm tra subscription:

~~~bash
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"
~~~

Liệt kê VM sizes ở một region:

~~~bash
az vm list-skus \
  --location southeastasia \
  --resource-type virtualMachines \
  --all \
  --output table
~~~

Kết quả lệnh này không chứng minh tự động rằng mọi tổ hợp image/security type đều hỗ trợ; phải xác minh thêm điều kiện Trusted Launch theo size, image và region.

### 8.2. Tạo VM với Secure Boot và vTPM

Ví dụ Bash:

~~~bash
az vm create \
  --resource-group rg-vmsecurity-lab \
  --name vm-tl-lab01 \
  --location southeastasia \
  --image "Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest" \
  --size Standard_D2s_v5 \
  --security-type TrustedLaunch \
  --enable-secure-boot true \
  --enable-vtpm true \
  --admin-username azureadmin \
  --generate-ssh-keys \
  --vnet-name vnet-security-lab \
  --subnet snet-workload \
  --public-ip-address ""
~~~

Trong lệnh:

- **--security-type TrustedLaunch** yêu cầu security type tương ứng.
- **--enable-secure-boot true** bật UEFI Secure Boot.
- **--enable-vtpm true** bật vTPM.
- **--image** minh họa Ubuntu Generation 2; kiểm tra image URN còn khả dụng và tương thích tại region.
- **--size** là size minh họa; cần xác minh khả năng hỗ trợ ở subscription thực tế.
- **--public-ip-address ""** ngăn tạo public IP trong ví dụ Azure CLI này.
- **--vnet-name / --subnet** yêu cầu mạng đã được chuẩn bị, hoặc thêm tùy chọn network resource group nếu khác nhóm.

Nếu Azure từ chối vì image/size không hỗ trợ, hãy sửa lựa chọn theo tài liệu. **Không tắt Secure Boot để né lỗi** nếu yêu cầu bảo mật bắt buộc nó. Nếu mạng quản trị chưa sẵn sàng, VM không có public IP có thể không truy cập trực tiếp được; điều này cần được chuẩn bị từ trước.

### 8.3. Đọc security profile

~~~bash
az vm show \
  --resource-group rg-vmsecurity-lab \
  --name vm-tl-lab01 \
  --query securityProfile \
  --output json
~~~

Ví dụ cấu trúc chính của phản hồi:

~~~json
{
  "securityType": "TrustedLaunch",
  "uefiSettings": {
    "secureBootEnabled": true,
    "vTpmEnabled": true
  }
}
~~~

Đây chỉ là ví dụ các field đáng chú ý, không phải cam kết nội dung JSON đầy đủ ở mọi API version. Giá trị cấu hình không chứng minh guest đã boot thành công hoặc dịch vụ attestation đã xác nhận trạng thái.

Kiểm tra trạng thái runtime:

~~~bash
az vm get-instance-view \
  --resource-group rg-vmsecurity-lab \
  --name vm-tl-lab01 \
  --output json
~~~

### 8.4. Kiểm tra trong guest

Trong Linux guest đã đăng nhập qua mạng quản trị hợp lệ:

~~~bash
# Cần cài mokutil nếu image chưa có.
mokutil --sb-state

# Kiểm tra guest nhận diện TPM.
ls /sys/class/tpm
ls -l /dev/tpm* 2>/dev/null
~~~

Công cụ có thể cho biết trạng thái Secure Boot và sự hiện diện của TPM; nhưng **không thay thế** chứng thực trạng thái bảo mật từ nguồn bên ngoài guest.

Trong Windows guest tương thích UEFI/TPM, có thể kiểm tra bằng PowerShell:

~~~powershell
Confirm-SecureBootUEFI
Get-Tpm
~~~

Nếu hai lệnh không hoạt động, kiểm tra quyền trong OS, phiên bản Windows, firmware mode và khả năng hỗ trợ trước khi kết luận có sự cố Azure.

## 9. Quy trình triển khai confidential VM

Không sử dụng nguyên một template Trusted Launch rồi chỉ đổi chuỗi security type thành ConfidentialVM. Hãy chọn đầy đủ tổ hợp image, size, disk và guest-security profile được hỗ trợ.

### 9.1. Chốt yêu cầu bảo vệ

Ví dụ: một worker phân tích dữ liệu nội bộ cần xử lý thông tin đã giải mã trong RAM, trong khi tổ chức muốn giảm khả năng lớp host/hypervisor đọc nội dung bộ nhớ theo mô hình đe dọa.

Đây là lý do có thể đánh giá confidential VM. Nhưng nếu mục tiêu là bảo vệ dữ liệu trước một tiến trình bị chiếm quyền **bên trong cùng guest**, cần thêm cách ly ứng dụng hoặc kiến trúc khác.

### 9.2. Chọn cấu hình trên Azure Portal

Trình tự khái niệm:

1. Chọn subscription, resource group và region.
2. Chọn dòng **Confidential VM** và size phù hợp theo danh mục Azure hiện hành.
3. Chọn image/OS chuyên dụng được hỗ trợ cho confidential VM family đó.
4. Xác định security type, UEFI/vTPM/Secure Boot theo yêu cầu của tổ hợp image và platform.
5. Chọn hình thức **OS disk / guest state encryption** có hỗ trợ, đồng thời xác định khóa do platform quản lý hay phương án customer-managed nếu sản phẩm cho phép.
6. Cấu hình mạng riêng, phương thức đăng nhập, managed identity và logging.
7. Xem lại khả năng Azure Backup, extension, availability, guest agent và quota.
8. Tạo VM trong lab trước; kiểm tra guest, ứng dụng và attestation khi có yêu cầu.

Một số VM family dựa trên AMD SEV-SNP hoặc Intel TDX có điều kiện triển khai khác nhau. Không áp đặt rằng toàn bộ CVM đều có cùng cấu hình, disk encryption option hoặc attestation report.

### 9.3. Đọc trạng thái VM bằng CLI

Sau khi tạo CVM thành công:

~~~bash
az vm show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<CONFIDENTIAL_VM_NAME>" \
  --query "{name:name,size:hardwareProfile.vmSize,security:securityProfile}" \
  --output json
~~~

Đây là thao tác đọc Azure resource. Kết quả giúp kiểm tra **cấu hình khai báo**, chứ không phải bằng chứng đã hoàn tất hardware attestation. Nếu cần kiểm chứng thật, phải dùng cơ chế/SDK/dịch vụ attestation của VM family và nền tảng được hỗ trợ.

### 9.4. Cấp khóa hoặc secret theo điều kiện tin cậy

Một kiến trúc tham khảo:

~~~text
Encrypted dataset trên Azure Storage
               |
               v
       Confidential VM
               |
               +--> Hardware/platform evidence
                          |
                          v
                 Attestation verifier
                          |
                          v
                  Policy decision
                          |
                          v
             Key Vault / hệ thống cấp khóa
                          |
                          v
                  Ứng dụng giải mã
                          |
                          v
                 Xử lý trong guest
                          |
                          v
                Mã hóa kết quả đầu ra
~~~

Chỉ nên nói “khóa được giải phóng khi attestation đạt” khi hệ thống thật có policy, verifier và cơ chế key release phù hợp. Nếu khóa vẫn được phát qua một tài khoản có quyền rộng không kiểm tra attestation, cấu hình CVM không tự tạo quy tắc cấp khóa như mong muốn.

Đừng ghi plaintext key vào image, customData/userData, boot log hay Git repository. Quản lý vòng đời key và quyền xem evidence attestation theo chính sách.

## 10. Mã hóa đĩa và trạng thái guest

### 10.1. Phân biệt các công nghệ

| Cơ chế | Phạm vi điển hình | Giới hạn |
|---|---|---|
| Storage Service Encryption (SSE) | Mã hóa dữ liệu at rest tại dịch vụ storage | Không bảo vệ RAM khi guest giải mã dữ liệu |
| Encryption at host khi hỗ trợ | Bổ sung mã hóa lưu trữ qua tầng host theo tính năng Azure | Không tương đương confidential VM memory isolation |
| Guest OS disk encryption/Azure Disk Encryption trong kịch bản được hỗ trợ | Mã hóa volume theo cơ chế OS và quản lý khóa | Có ràng buộc về Gen2, security profile và tương thích CVM |
| Confidential VM disk/guest state security | Bảo vệ OS disk/trạng thái guest theo lựa chọn đặc thù của CVM | Có thể không hỗ trợ mọi mode khóa/backup |
| TLS/mTLS | Bảo vệ truyền dữ liệu | Không thay thế bảo vệ disk hoặc RAM |
| CVM hardware memory protection | Tăng bảo vệ RAM guest trước một số thành phần host | Không bảo vệ dữ liệu nếu guest/app tự làm lộ |

**Không được giả định Azure Disk Encryption, SSE với CMK, encryption at host, các chế độ bảo vệ OS disk của CVM và backup đều dùng chung được với mọi SKU.** Xác nhận theo tài liệu cụ thể trước khi đưa vào kiến trúc.

### 10.2. Key management và nguy cơ mất dữ liệu

- Xác định ai sở hữu key, ai có quyền dùng key và ai phê duyệt policy.
- Sử dụng Azure Key Vault hoặc Managed HSM khi tích hợp được hỗ trợ.
- Chặn truy cập trái phép bằng Azure RBAC, network controls và logging.
- Thiết kế rotation, recovery, soft delete và các biện pháp bảo vệ key theo hỗ trợ.
- Thử trường hợp key bị thu hồi hoặc hệ thống quản lý khóa tạm không khả dụng.

Không xóa hay vô hiệu hóa một khóa mã hóa đang phục vụ VM mà chưa hiểu tác động. Một VM có backup nhưng không còn key cần thiết vẫn có thể không khôi phục được dữ liệu.

## 11. Giám sát và kiểm toán VM được bảo vệ

### 11.1. Kiểm tra theo nhiều lớp

| Lớp kiểm tra | Nguồn | Câu hỏi |
|---|---|---|
| Azure Resource Manager | VM security profile, image, size, disk | Cấu hình khai báo có đúng policy? |
| Azure Activity Log | Tạo/sửa/xóa VM và các tài nguyên liên quan | Ai thay đổi cấu hình và khi nào? |
| Guest OS | Security logs, Secure Boot/TPM state, patch level | OS đang ở trạng thái nào? |
| Boot integrity/attestation | Dịch vụ được hỗ trợ theo image/VM type | Evidence có đáp ứng chính sách không? |
| Defender for Cloud | Recommendations và security alerts khi tính năng/gói được bật | Có rủi ro mới hoặc cấu hình yếu không? |
| Azure Monitor | CPU, disk, network, availability, log agent khi được cài | Workload có khỏe không? |
| Backup | Job history, retention và restore test | Có thể khôi phục khi sự cố không? |
| SIEM/ticket | Microsoft Sentinel hoặc hệ thống tương đương | Có điều tra và quyết định được ghi lại không? |

Trusted Launch có vTPM không có nghĩa tất cả tín hiệu guest attestation sẽ tự xuất hiện. Tùy image/OS/VM, cần agent, extension, gói bảo vệ, diagnostic settings hoặc dịch vụ attestation phù hợp. Hãy kiểm tra dữ liệu thật thay vì chỉ đánh dấu checkbox “enabled”.

### 11.2. Lệnh kiểm tra chỉ đọc

~~~bash
# Cấu hình bảo mật của VM
az vm show -g rg-vmsecurity-lab -n vm-tl-lab01 \
  --query securityProfile -o json

# Trạng thái VM và instance view
az vm get-instance-view -g rg-vmsecurity-lab -n vm-tl-lab01 \
  -o json

# Activity Log trong khoảng 24 giờ gần đây
az monitor activity-log list --offset 24h --output json
~~~

Những lệnh này hữu ích cho inventory và điều tra, nhưng không thay thế kết quả attestation hoặc bằng chứng kiểm toán từ hệ thống tin cậy. Khi lưu chứng cứ, ghi resource ID, timestamp UTC, phiên bản image, người thu thập và giới hạn dữ liệu.

### 11.3. Azure Policy và tiêu chuẩn triển khai

Trong tổ chức nhiều subscription, Azure Policy có thể hỗ trợ audit hoặc enforce các thuộc tính security profile ở những resource type/định nghĩa policy được hỗ trợ. Quy trình:

1. Kiểm kê VM Gen1/Gen2, image, security type, size và region.
2. Phân loại workload yêu cầu Trusted Launch, confidential VM hoặc ngoại lệ được phê duyệt.
3. Bắt đầu bằng policy Audit để hiểu phạm vi không tuân thủ.
4. Thêm validation vào Bicep/Terraform và CI/CD.
5. Chỉ chuyển sang Deny khi hiểu ảnh hưởng tới các image và VM family.
6. Theo dõi exemption, người sở hữu và hạn rà soát.

Không ép confidential VM lên mọi workload chỉ vì nó có bảo vệ bộ nhớ; có thể làm deployment thất bại hoặc tăng chi phí mà không phù hợp threat model.

## 12. Patch, backup và rollback

### 12.1. Cập nhật image an toàn

Một thay đổi kernel, driver hoặc bootloader có thể làm Secure Boot thất bại hoặc khiến giá trị đo thay đổi. Quy trình:

1. Xây image phiên bản mới trong pipeline có kiểm soát.
2. Tạo staging VM có security type và extension tương tự production.
3. Kiểm tra boot, Secure Boot/vTPM, quyền, network, disk và ứng dụng.
4. Kiểm tra kết quả attestation nếu được dùng làm điều kiện cấp key.
5. Ghi baseline và change ticket; triển khai rolling khi kiến trúc cho phép.
6. Giữ image/backup trước đó để rollback đúng quy trình.
7. Theo dõi sau phát hành và cập nhật baseline một cách có kiểm soát.

Nếu boot thất bại do module chưa ký, không tắt Secure Boot vô thời hạn chỉ để phục hồi nhanh. Cần đánh giá signing, compatibility hoặc chuyển về image hợp lệ.

### 12.2. Backup và DR theo khả năng thực tế

Trước khi cam kết RPO/RTO phải xác nhận:

- Azure Backup có hỗ trợ đúng **security type, VM generation, OS disk mode và VM family** không?
- Snapshot, restore new VM hoặc cross-region restore có được hỗ trợ trong cấu hình này?
- Data disk, guest state hoặc key có phụ thuộc thủ tục phục hồi đặc biệt không?
- Region đích có confidential VM family và quota tương ứng không?
- Khi khôi phục, quyền, private endpoint, network và key policy có còn phù hợp không?

**Disk encryption không thay thế backup, và backup thành công không đồng nghĩa ứng dụng khôi phục được.** Hãy thực hành restore tới môi trường tách biệt rồi kiểm tra tính toàn vẹn dữ liệu và chức năng nghiệp vụ.

### 12.3. Chuyển VM cũ lên Trusted Launch/CVM

Không mặc định VM Generation 1 hoặc image legacy có thể chuyển trực tiếp tại chỗ sang Trusted Launch hoặc CVM. Hỗ trợ chuyển đổi tùy VM, OS, image, disk và dịch vụ tại thời điểm thực hiện. Nếu không có đường nâng cấp phù hợp, dựng VM mới từ image được hỗ trợ rồi di chuyển ứng dụng/dữ liệu với kế hoạch cutover.

Các bước cần có: inventory, test ở staging, backup, xác minh compatibility, kế hoạch downtime, kiểm tra DNS/IP/managed identity, cutover có giám sát và rollback.

## 13. Kịch bản thực tế: xử lý dữ liệu tài chính

Giả sử doanh nghiệp có hệ thống phân tích dữ liệu tài chính:

- API nhận yêu cầu và xác thực người dùng bằng Entra ID.
- Worker VM xử lý dữ liệu đã được mã hóa lưu trong Azure Storage.
- Azure Key Vault quản lý khóa.
- Azure Monitor/Defender for Cloud giúp quan sát rủi ro.
- CI/CD tạo image và triển khai hạ tầng có kiểm soát.

### 13.1. Chọn biện pháp theo vai trò

| Thành phần | Nhu cầu bảo vệ | Thiết kế tham khảo |
|---|---|---|
| VM web/API | Chống can thiệp boot, bảo vệ OS và network | Trusted Launch + RBAC/NSG/EDR/TLS |
| Worker phân tích bí mật | Giảm rủi ro truy cập RAM guest từ thành phần ngoài VM | Đánh giá confidential VM và attestation |
| Azure Storage | Bảo vệ dữ liệu at rest và kiểm soát truy cập | Encryption, RBAC, private endpoint, backup |
| Azure Key Vault | Giới hạn người dùng khóa | Policy, logging và key release có điều kiện nếu được hỗ trợ |
| Pipeline | Không hard-code secret, kiểm soát image | Managed identity/WIF, approvals, artifact validation |
| Quản trị | Chống truy cập trái phép | Bastion/VPN, Entra, PIM, audit |

### 13.2. Luồng xử lý

~~~mermaid
flowchart TD
    U["Người dùng đã xác thực"] --> A["API điều phối"]
    A --> W["Worker trong Confidential VM"]
    S["Storage: dữ liệu mã hóa"] --> W
    W --> T["Attestation verifier nếu triển khai"]
    T --> K["Key Vault / policy"]
    K --> W
    W --> E["Kết quả mã hóa"]
    E --> S
    M["Monitor / Defender / log"] -.-> W
~~~

Sơ đồ mô tả ý tưởng: chỉ khi có thực thi một chính sách cấp khóa theo kết quả attestation thì tổ chức mới có thể khẳng định khóa không được cấp khi môi trường không đạt điều kiện. Việc chạy worker trên CVM đơn thuần chưa tạo bảo đảm này.

### 13.3. Tiêu chí chấp nhận

1. VM dùng đúng image, security type, size và disk configuration được hỗ trợ.
2. Quyền VM và Key Vault được giới hạn, không có secret plaintext trong image/log.
3. Network không mở cổng quản trị công khai ngoài thiết kế.
4. Attestation/policy thực sự hoạt động nếu là yêu cầu bắt buộc.
5. Guest patch/agent/EDR hoạt động, có telemetry và cảnh báo khi tính năng hỗ trợ.
6. Backup và restore được kiểm tra tương thích.
7. Benchmark độ trễ, chi phí và độ ổn định với tải đại diện.
8. Có báo cáo threat model, cấu hình, người phê duyệt và kế hoạch khôi phục.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không tạo được Trusted Launch VM | Image Gen1, size/region không hỗ trợ, thiếu quota | Kiểm tra image generation và SKU |
| Secure Boot làm VM không boot | Bootloader/module/driver không được ký phù hợp | Xem boot diagnostics, image và patch history |
| Security profile không đúng | Thiếu tham số, template cũ hoặc deployment drift | Đọc securityProfile và lịch sử deployment |
| vTPM không hiện trong guest | Chưa bật, OS không nhận hoặc tính năng không hỗ trợ | Đối chiếu Azure config, Get-Tpm hoặc /sys/class/tpm |
| Integrity signal đổi sau cập nhật | Baseline thay đổi hợp lệ hoặc dấu hiệu can thiệp | Đối chiếu change, kernel, boot log và kiểm chứng |
| Không chọn được CVM size | Region/quota/OS image/VM family không phù hợp | Kiểm tra tính sẵn có và feature matrix |
| CVM boot nhưng attestation không đạt | Policy mismatch, evidence lỗi hoặc SDK không tương thích | Kiểm tra report/policy theo hướng dẫn platform |
| VM chạy chậm | VM family, driver, I/O hoặc ứng dụng chưa tối ưu | Benchmark thực tế và đo p95 |
| Backup/restore thất bại | Security profile/disk encryption không tương thích | Kiểm tra hỗ trợ và thử restore trong lab |
| SSH/RDP thất bại | NSG, Bastion, DNS, guest firewall hoặc identity | Kiểm tra đường quản trị đã phê duyệt |
| Key Vault từ chối cấp secret | RBAC/network hoặc attestation policy không đạt | Xem policy, audit log và lỗi xác thực |

Không xử lý mọi lỗi bằng cách tắt Secure Boot, mở port 22/3389 cho toàn Internet hoặc cấp Owner toàn subscription. Hãy điều tra tuần tự: **image/SKU → Azure config → boot/guest → network/identity → app → attestation → backup**.

### 14.1. Nếu xuất hiện cảnh báo boot integrity

1. Ghi alert ID, VM resource ID, timestamp UTC và tác động ứng dụng.
2. Kiểm tra nguồn alert, tình trạng đo/attestation và phạm vi dữ liệu quan sát.
3. Đối chiếu kernel/image/driver vừa cập nhật với change ticket.
4. Bảo toàn log và bằng chứng theo chính sách, tránh thay đổi hiện trạng không cần thiết.
5. Nếu nghi xâm nhập, cô lập theo runbook đã phê duyệt, điều tra quyền và nguồn truy cập.
6. Kiểm tra image/boot/OS trước khi phục hồi lưu lượng.
7. Ghi nguyên nhân, giới hạn kết luận, biện pháp và người xác nhận đóng sự cố.

Bản cập nhật hợp lệ không tương thích Secure Boot có thể tạo lỗi giống một sự cố an ninh từ góc nhìn người dùng. Không kết luận có mã độc nếu chưa có bằng chứng.

## 15. Hiệu năng, tính sẵn sàng và chi phí

Confidential VM có thể bị giới hạn về VM family, tính năng I/O, agent và một số phương thức availability/DR; chi phí có thể khác VM thông thường. Không có một tỷ lệ overhead cố định áp dụng cho mọi ứng dụng.

Benchmark nên gồm:

- Thời gian boot và restart sau cập nhật.
- CPU/memory throughput và latency.
- Disk IOPS, throughput, fsync và tương thích data disk.
- Network RTT, TLS, kết nối tới dịch vụ phụ thuộc.
- Độ trễ attestation và cấp khóa nếu nằm trên critical path.
- p95/p99 latency và error rate của nghiệp vụ.
- Thời gian backup/restore và RTO thực tế.

**Confidential VM không tự bảo đảm đa vùng hoặc chống downtime.** Vẫn cần thiết kế HA, Availability Zone, load balancer, multi-region hoặc DR theo khả năng của family/region được chọn.

Chi phí cần tính không chỉ VM compute mà còn managed disk, backup, networking, Bastion, Azure Monitor, Log Analytics, Defender for Cloud, Key Vault và hạ tầng kiểm thử. Gắn tag Application, Owner, Environment, CostCenter; theo dõi Cost Management và budget alert nhưng không nhầm budget alert với giới hạn cứng tự ngừng chi phí.

## 16. Checklist đưa VM vào production

### Trước triển khai

- [ ] Threat model xác định rõ boot integrity hay data-in-use protection.
- [ ] Đã chọn Trusted Launch/CVM hoặc ghi rõ ngoại lệ.
- [ ] Image, OS, VM size, region, quota và extensions tương thích.
- [ ] Đã thiết kế VNet, NSG, quản trị qua Bastion/VPN và đường truy cập cần thiết.
- [ ] RBAC, Entra identity và managed identity được cấp tối thiểu.
- [ ] Có chính sách mã hóa đĩa, khóa và khả năng khôi phục.
- [ ] Đã kiểm tra backup/restore cho security type cụ thể.
- [ ] Có baseline hiệu năng, monitoring và dự toán chi phí.

### Sau triển khai

- [ ] Security profile báo đúng security type và UEFI settings.
- [ ] Guest OS thấy trạng thái Secure Boot/vTPM như kỳ vọng.
- [ ] Ứng dụng hoạt động, không có public access ngoài chủ đích.
- [ ] Attestation và conditional key release được kiểm tra nếu đã thiết kế.
- [ ] Monitoring/Defender alerts thực sự có telemetry khi được hỗ trợ.
- [ ] Backup job và restore test đạt tiêu chí đã thống nhất.
- [ ] Có owner, tag, runbook, change record và người phê duyệt.

### Vận hành định kỳ

- [ ] OS/kernel/driver được vá có kiểm thử.
- [ ] Image, extension và security profile được kiểm tra drift.
- [ ] RBAC và quyền trong guest được rà soát.
- [ ] Alert boot integrity và sự cố phần mềm được xử lý theo playbook.
- [ ] Kết quả backup/restore được kiểm tra định kỳ.
- [ ] Feature support, chi phí, quota và roadmap được rà soát khi resize/migration.

## 17. Tự kiểm tra kiến thức

1. **Trusted Launch tập trung bảo vệ điều gì?** Chuỗi khởi động bằng Secure Boot, vTPM và các khả năng đo/kiểm chứng liên quan.
2. **Secure Boot có ngăn mọi mã độc sau khi OS đã boot không?** Không. Còn cần vá lỗi, EDR, network protection và application security.
3. **Measured boot khác Secure Boot thế nào?** Measured boot ghi nhận bằng chứng; Secure Boot kiểm tra các thành phần được phép tải.
4. **vTPM dùng để làm gì?** Hỗ trợ chức năng TPM 2.0 trong guest, gồm các phép đo boot và khả năng dùng khóa theo ứng dụng.
5. **Bật vTPM có tự tạo đầy đủ cảnh báo attestation không?** Không. Cần tích hợp giám sát/dịch vụ kiểm chứng được hỗ trợ.
6. **Confidential VM tăng bảo vệ dữ liệu ở trạng thái nào?** Data in use trong RAM, theo mô hình phần cứng tương ứng.
7. **CVM có bảo vệ tuyệt đối trước root/admin bị xâm phạm trong guest không?** Không.
8. **CVM có thay thế mã hóa disk và TLS không?** Không. Các trạng thái dữ liệu cần biện pháp riêng.
9. **Attestation có tự đảm bảo Key Vault chỉ cấp secret cho VM đạt chuẩn không?** Không; phải có policy và tích hợp key release thực tế.
10. **Tại sao image Gen2 quan trọng với Trusted Launch?** Nền tảng UEFI/Secure Boot và các yêu cầu tương thích gắn với Gen2.
11. **Bật Trusted Launch có cho phép mở RDP ra toàn Internet không?** Không. Vẫn cần NSG, identity và kênh quản trị được bảo vệ.
12. **SSE có tương đương confidential memory protection không?** Không. SSE bảo vệ dữ liệu lưu trữ.
13. **Vì sao phải thử backup/restore cho CVM?** Có thể tồn tại giới hạn theo security profile, disk mode và VM family.
14. **Khi image update làm attestation thay đổi, có thể kết luận bị tấn công ngay không?** Không. Cần đối chiếu baseline, thay đổi hợp lệ và evidence khác.
15. **Có nên chọn CVM cho mọi VM?** Không. Cần căn cứ vào threat model, tương thích, hiệu năng, availability và tổng chi phí.

## 18. Tài liệu tham khảo

- [Trusted Launch for Azure virtual machines](https://learn.microsoft.com/azure/virtual-machines/trusted-launch) — các cơ chế và yêu cầu Trusted Launch.
- [Deploy Trusted Launch VMs](https://learn.microsoft.com/azure/virtual-machines/trusted-launch-portal) — quy trình triển khai với Portal.
- [Azure confidential virtual machines](https://learn.microsoft.com/azure/confidential-computing/confidential-vm-overview) — mô hình bảo vệ và khả năng CVM.
- [Azure confidential computing](https://learn.microsoft.com/azure/confidential-computing/) — bảo vệ data in use và attestation.
- [Azure security benchmark: Virtual Machines](https://learn.microsoft.com/security/benchmark/azure/baselines/virtual-machines-security-baseline) — các biện pháp bảo vệ VM.
- [Azure virtual machine disk encryption](https://learn.microsoft.com/azure/virtual-machines/disk-encryption-overview) — mã hóa đĩa và các điều kiện hỗ trợ.
- [Azure Backup for virtual machines](https://learn.microsoft.com/azure/backup/backup-azure-vms-introduction) — bảo vệ và khôi phục dữ liệu máy ảo.
- [Microsoft Defender for Cloud](https://learn.microsoft.com/azure/defender-for-cloud/) — theo dõi tư thế bảo mật và cảnh báo.
- [Azure Update Manager](https://learn.microsoft.com/azure/update-manager/overview) — quản lý bản vá hệ điều hành.
- [Azure Policy](https://learn.microsoft.com/azure/governance/policy/) — kiểm tra và áp dụng các yêu cầu quản trị.

**Kết luận:** Trusted Launch giúp củng cố sự tin cậy của quá trình boot; confidential VM bổ sung bảo vệ bộ nhớ đang xử lý bằng phần cứng theo threat model. Bảo mật VM hoàn chỉnh vẫn cần identity, network, image supply chain, patching, mã hóa, backup, giám sát và kiểm thử. Khi triển khai production, hãy đánh giá khả năng hỗ trợ của **đúng image, VM family, disk security, region và dịch vụ vận hành**, thay vì suy luận từ tên tính năng.
