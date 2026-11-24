# Quản lý giấy phép hệ điều hành, phần mềm và mô hình BYOL

Máy ảo, máy chủ vật lý, container và dịch vụ cloud đều có thể kéo theo nghĩa vụ giấy phép cho hệ điều hành hoặc phần mềm bên trong. Chi phí compute nhìn thấy trên hóa đơn chưa chắc đã bao gồm quyền sử dụng Windows Server, SQL Server, hệ điều hành thương mại, database, middleware hoặc phần mềm chuyên dụng. Nếu không xác định rõ giấy phép đã nằm trong giá dịch vụ hay phải cung cấp riêng, tổ chức có thể trả tiền hai lần, thiếu quyền sử dụng hoặc không đáp ứng điều kiện kiểm toán.

BYOL (Bring Your Own License) là mô hình khách hàng sử dụng giấy phép phần mềm đã sở hữu hoặc đã mua theo hợp đồng của nhà cung cấp phần mềm, thay vì mua giấy phép đi kèm với tài nguyên cloud. BYOL có thể giảm chi phí khi tổ chức có quyền sử dụng phù hợp, nhưng quyền đó phụ thuộc phiên bản, loại giấy phép, ngày mua, Software Assurance hoặc subscription, cách cấp phép theo core/user/device, vị trí chạy và điều khoản của cả nhà cung cấp phần mềm lẫn cloud.

Sau bài học, bạn có thể:

- Phân biệt license-included, BYOL và các mô hình trả phí theo mức sử dụng.
- Xác định đơn vị cấp phép và quyền sử dụng của hệ điều hành, database và phần mềm thương mại.
- Đối chiếu các lựa chọn giấy phép trên Amazon EC2, Azure Virtual Machines và Google Compute Engine.
- Thiết kế inventory, tag, kiểm soát triển khai và bằng chứng kiểm toán cho tài nguyên có giấy phép.
- Đánh giá tác động của scale, resize, host placement, DR và container đến nghĩa vụ cấp phép.

## 1. Ba mô hình giấy phép thường gặp

### License-included

Nhà cung cấp cloud bán kèm quyền sử dụng phần mềm trong giá VM hoặc dịch vụ. Ví dụ, một số image Windows Server hoặc SQL Server được cung cấp theo mô hình license-included. Khách hàng trả phí theo đơn giá của image hoặc loại VM, và nhà cung cấp xử lý phần giấy phép theo thỏa thuận dịch vụ.

Ưu điểm là triển khai nhanh, dễ dự toán theo giờ hoặc theo đơn vị sử dụng và không cần tự mang quyền sử dụng sẵn có vào môi trường cloud. Cần kiểm tra phần mềm, edition, phiên bản, vùng và loại máy có nằm trong danh mục license-included hay không. Giá license-included có thể khác nhau đáng kể giữa image tiêu chuẩn và image có phần mềm thương mại.

### BYOL (Bring Your Own License)

Khách hàng cung cấp giấy phép đã có theo hợp đồng của nhà cung cấp phần mềm. Tổ chức phải chứng minh quyền sử dụng còn hiệu lực và đáp ứng các điều kiện triển khai, chẳng hạn số core được cấp phép, phiên bản, thời hạn, quyền di chuyển workload, yêu cầu Software Assurance/subscription hoặc yêu cầu chạy trên phần cứng chuyên dụng.

BYOL không đồng nghĩa với việc có một product key là được phép cài phần mềm ở bất kỳ VM nào. Product key, bộ cài và quyền sử dụng là những thứ khác nhau. Một khóa kích hoạt có thể hoạt động về mặt kỹ thuật nhưng không chứng minh tổ chức có đủ quyền theo hợp đồng.

### Pay-as-you-go hoặc subscription theo mức dùng

Một số phần mềm hoặc hệ điều hành thương mại có thể được tính theo thời gian chạy, số core, người dùng, thiết bị, request hoặc gói subscription. Mô hình này có thể được bán trực tiếp qua cloud marketplace hoặc qua nhà cung cấp phần mềm. Cần xác định khoản phí đã nằm trong giá VM, được tính riêng trên hóa đơn cloud hay được nhà cung cấp phần mềm xuất hóa đơn độc lập.

| Mô hình | Ai cung cấp quyền sử dụng? | Cách tính chi phí thường gặp | Trách nhiệm cần kiểm tra |
|---|---|---|---|
| License-included | Nhà cung cấp cloud hoặc marketplace theo offer | Giá VM/image theo giờ hoặc đơn vị dùng | Chọn đúng image/edition, vùng và loại máy; xác minh phạm vi đã bao gồm |
| BYOL | Tổ chức đã có hợp đồng với vendor | Chi phí license đã mua hoặc subscription riêng | Chứng minh entitlement, tính số lượng cần có, tuân thủ điều kiện cloud/host |
| Pay-as-you-go | Cloud marketplace hoặc vendor | Theo giờ, core, user, thiết bị hoặc mức sử dụng | Theo dõi usage, subscription, hóa đơn và điều kiện kết thúc |

## 2. Xác định đơn vị cấp phép

Trước khi chọn VM, hãy đọc hợp đồng hoặc Product Terms để biết phần mềm được cấp phép theo đơn vị nào. Các mô hình phổ biến gồm:

- **Theo core hoặc vCPU:** số lõi xử lý được cấp phép có thể phụ thuộc số core vật lý trên host, số vCPU của VM, hệ số quy đổi hoặc mức tối thiểu cho mỗi VM. Không tự giả định một vCPU luôn tương đương một core được cấp phép.
- **Theo processor/socket:** giấy phép dựa trên số CPU vật lý, socket hoặc cách định nghĩa processor của vendor. Điều kiện này có thể yêu cầu biết máy vật lý đang chạy VM.
- **Theo server/VM:** một giấy phép áp dụng cho một máy chủ hoặc một VM trong phạm vi được hợp đồng cho phép. Cần xác định việc clone, scale-out hoặc tạo máy thay thế có làm phát sinh thêm đơn vị cấp phép không.
- **Theo user hoặc device:** số người dùng hoặc thiết bị truy cập phần mềm quyết định số license. Cần tính cả người dùng gián tiếp, tài khoản dịch vụ và thiết bị dùng chung nếu hợp đồng quy định.
- **Theo concurrent user/session:** số phiên hoặc người dùng đồng thời. Cần có dữ liệu đo và cơ chế kiểm soát số phiên.
- **Theo subscription hoặc mức sử dụng:** tính theo thời gian, request, transaction, dung lượng, node hoặc một gói quyền sử dụng định kỳ.

Một sản phẩm có thể cung cấp nhiều lựa chọn, ví dụ theo core hoặc theo server cộng Client Access License (CAL). Edition và phiên bản khác nhau cũng có thể có điều kiện khác nhau. Không suy ra đơn vị cấp phép từ tên sản phẩm hoặc từ cách cloud tính tiền VM.

### Ví dụ tính sơ bộ theo core

Giả sử hợp đồng của một phần mềm quy định phải cấp phép 8 core cho mỗi VM, bất kể VM có ít core hơn. Nếu triển khai 6 VM, số lượng cần dự trù là:

\[
6 \times 8 = 48 \text{ core license}
\]

Đây chỉ là phép tính minh họa cho điều kiện giả định “tối thiểu 8 core mỗi VM”. Trong thực tế, hợp đồng có thể dùng số core vật lý của host, số core ảo, hệ số khác hoặc điều kiện tối thiểu khác. Phải dùng đúng định nghĩa trong hợp đồng trước khi lập dự toán.

Nếu autoscaling có thể tăng từ 6 lên 12 VM, phải tính cả số VM tối đa có thể chạy đồng thời, môi trường staging, node dự phòng và máy được tạo trong quá trình rolling update nếu chúng cùng chạy phần mềm được cấp phép. Một nhóm có 6 VM mong muốn không đồng nghĩa số VM tối đa luôn là 6.

## 3. Giấy phép hệ điều hành và phần mềm ứng dụng

### Hệ điều hành

Linux có thể dùng bản phân phối và subscription khác nhau. Một image Linux miễn phí không đồng nghĩa mọi gói hỗ trợ, cập nhật bảo mật hoặc repository thương mại đều miễn phí. Với Red Hat Enterprise Linux (RHEL) hoặc SUSE Linux Enterprise Server (SLES), cần xác định image là PAYG do cloud tính phí hay BYOS (Bring Your Own Subscription) dùng subscription đã có. Kiểm tra quyền đăng ký, cập nhật, hỗ trợ và cách chuyển subscription giữa môi trường.

Windows Server thường có lựa chọn license-included và trong một số trường hợp có thể dùng quyền hiện có theo điều kiện của Microsoft. Cần xác minh edition, phiên bản, số core, loại host, ngày mua license và quyền đi kèm Software Assurance hoặc subscription. Không nên cài một bản Windows từ ISO riêng lên VM rồi cho rằng chi phí license đã được tính trong giá compute.

### Database, middleware và ứng dụng

SQL Server, Oracle Database, SAP, middleware thương mại, phần mềm bảo mật, backup agent và công cụ quản trị có thể có điều kiện riêng. Một VM có thể đồng thời cần license cho hệ điều hành, database và ứng dụng. Ví dụ, giá một VM Windows license-included không tự động bao gồm SQL Server; cần chọn image SQL Server license-included hoặc cung cấp quyền SQL Server hợp lệ theo hợp đồng.

Với phần mềm có yêu cầu theo core hoặc socket, cần ghi nhận loại VM, host placement, số core và quy tắc tính của vendor. Với phần mềm theo user/device, cần quản lý danh sách người dùng và quyền truy cập. Với phần mềm theo subscription, cần theo dõi ngày bắt đầu, ngày hết hạn, gia hạn và số lượng seat.

### Container và image ứng dụng

Đóng gói phần mềm vào container không tự động loại bỏ nghĩa vụ giấy phép. Cần xác định license gắn với host, node, core, container instance, user hay workload. Nếu một container được scale thành 20 bản sao, hợp đồng có thể tính theo cách khác so với một bản sao chạy trên một VM.

Image container có thể chứa thư viện, runtime, database client hoặc phần mềm thương mại. Hãy kiểm tra điều khoản phân phối image, quyền sử dụng thư viện và việc image được sao chép sang registry hoặc cloud khác. License scanner có thể phát hiện package và phiên bản, nhưng kết quả scan không thay thế việc đọc hợp đồng.

## 4. License-included và BYOL trên các cloud

Ba cloud có các cơ chế giúp lựa chọn image có license kèm theo hoặc triển khai phần mềm với quyền hiện có. Tên dịch vụ và điều kiện hỗ trợ thay đổi theo sản phẩm, region, thời điểm mua license và hợp đồng vendor.

| Nền tảng | Lựa chọn license-included | Cơ chế hỗ trợ BYOL hoặc quản lý quyền |
|---|---|---|
| AWS | AMI/instance có Windows Server hoặc phần mềm thương mại đã bao gồm license theo offer | AWS License Manager để quản lý inventory và quy tắc; EC2 Dedicated Hosts có thể cần thiết cho một số license gắn với server vật lý |
| Azure | Một số image Windows Server, SQL Server và marketplace có giá đã bao gồm license | Azure Hybrid Benefit cho license đủ điều kiện; Azure Dedicated Host cung cấp host vật lý riêng cho các kịch bản cần kiểm soát host |
| Google Cloud | Một số public image/marketplace image có phí phần mềm tính theo mức dùng | Sole-tenant nodes có thể đáp ứng một số kịch bản BYOL yêu cầu phần cứng chuyên dụng; cần kiểm tra điều kiện license của sản phẩm cụ thể |

### AWS

Amazon EC2 cung cấp các image và lựa chọn giá có thể bao gồm license cho một số hệ điều hành hoặc phần mềm. Nếu dùng BYOL, tổ chức phải xác định license có quyền chạy trên cloud và trên loại host dự kiến hay không.

AWS License Manager hỗ trợ tạo license configuration, theo dõi việc sử dụng và áp dụng quy tắc cho tài nguyên được tích hợp. Công cụ này hữu ích để quản lý inventory, nhưng không tự xác nhận mọi điều khoản hợp đồng của vendor. Với license gắn với server vật lý hoặc yêu cầu kiểm soát vị trí phần cứng, EC2 Dedicated Hosts có thể là một phần của thiết kế. Dedicated Host cung cấp host vật lý dành riêng cho tài khoản; cần xem loại instance, host allocation, affinity và điều kiện license liên quan.

Phân biệt EC2 Dedicated Hosts với Dedicated Instances. Dedicated Instances chạy trên phần cứng dành riêng theo mô hình dịch vụ nhưng không cung cấp cùng mức hiển thị và kiểm soát host như Dedicated Hosts. Không chọn Dedicated Instances chỉ vì nghĩ rằng chúng tự động đáp ứng mọi điều kiện BYOL.

### Microsoft Azure

Azure có thể cung cấp VM image với license hệ điều hành hoặc phần mềm đã bao gồm trong giá. Với license đủ điều kiện, Azure Hybrid Benefit cho phép áp dụng quyền hiện có để giảm hoặc loại bỏ phần phí license đủ điều kiện trong giá dịch vụ Azure. Quyền này có thể yêu cầu Windows Server hoặc SQL Server license phù hợp cùng Software Assurance hoặc subscription đủ điều kiện.

Azure Hybrid Benefit không phải quyền BYOL chung cho mọi sản phẩm. Phải xác định đúng sản phẩm, phiên bản, edition, số core, loại subscription, quyền chạy song song trong giai đoạn chuyển đổi và thời hạn sử dụng. Azure Dedicated Host cung cấp máy chủ vật lý riêng cho khách hàng; nó có thể liên quan đến các kịch bản cấp phép theo host, nhưng việc có host riêng không tự tạo ra entitlement.

### Google Cloud

Google Cloud cung cấp public image và marketplace image có thể tính phí license theo thời gian sử dụng. Với một số phần mềm yêu cầu chạy trên phần cứng chuyên dụng hoặc cần biết host vật lý, sole-tenant nodes cho phép đặt VM trên node phần cứng dành riêng cho một khách hàng trong phạm vi dịch vụ. Điều kiện BYOL vẫn phải được xác nhận theo license agreement và hướng dẫn của Google Cloud cho đúng sản phẩm.

Không suy luận rằng mọi Windows, database hoặc phần mềm thương mại đều có thể BYOL lên sole-tenant nodes. Kiểm tra sản phẩm, ngày mua license, quyền cloud mobility, loại máy, host maintenance và cách tính core theo điều khoản vendor.

## 5. BYOL, Software Assurance và License Mobility

Một số hợp đồng cho phép chuyển license từ máy chủ tại chỗ sang cloud hoặc giữa các môi trường, nhưng quyền này có điều kiện. Các thuật ngữ như Software Assurance, subscription, License Mobility, Flexible Virtualization Benefit hoặc quyền sử dụng trên dedicated host có ý nghĩa riêng theo sản phẩm và thời điểm ký hợp đồng.

Trước khi áp dụng BYOL, hãy xác minh:

1. License có đúng sản phẩm, edition, version và metric cần chạy không?
2. Hợp đồng có cho phép triển khai trên public cloud không?
3. Có yêu cầu Software Assurance, subscription đang hoạt động hoặc License Mobility không?
4. Có giới hạn theo region, quốc gia, loại host, shared tenancy hoặc dedicated tenancy không?
5. Có yêu cầu thời gian gán license cho một server trước khi chuyển sang server khác không?
6. Có được chạy đồng thời bản cũ và bản mới trong giai đoạn migration, DR hoặc rolling upgrade không?
7. Có cần đăng ký license với cloud provider hoặc duy trì hồ sơ host vật lý không?

Không coi điều khoản của một vendor áp dụng cho vendor khác. Ví dụ, quyền License Mobility của một sản phẩm Microsoft không tự động áp dụng cho Oracle Database, RHEL, phần mềm backup hoặc ứng dụng do bên thứ ba phát hành. Khi điều khoản không rõ, cần có xác nhận bằng văn bản từ nhà cung cấp phần mềm hoặc bộ phận quản lý hợp đồng trước khi triển khai.

## 6. Quản lý inventory và bằng chứng cấp phép

Một inventory tốt phải nối được ba nhóm dữ liệu: quyền đã mua, tài nguyên đang chạy và quy tắc tính license. Nếu chỉ lưu product key hoặc tên image, tổ chức sẽ khó chứng minh số lượng quyền sử dụng và khó phát hiện tài nguyên vượt entitlement.

### Trường dữ liệu nên quản lý

| Nhóm | Trường thông tin gợi ý | Mục đích |
|---|---|---|
| Sản phẩm | Vendor, product, edition, version | Xác định chính xác phần mềm |
| Quyền sử dụng | License model, metric, entitlement quantity, agreement reference | Biết có bao nhiêu quyền và tính theo cách nào |
| Điều kiện | Purchase date, SA/subscription status, mobility rights, territory, host requirement | Xác định quyền còn hợp lệ và nơi được phép chạy |
| Tài nguyên | Cloud, account/subscription/project, region, zone, VM ID, instance type, host ID | Nối license với workload thực tế |
| Quy mô | vCPU, physical core nếu có, VM count, maximum scale, user/device count | Tính số lượng cần cấp phép |
| Trách nhiệm | Service owner, license owner, cost center, review date | Xác định người chịu trách nhiệm |
| Bằng chứng | Contract reference, invoice reference, vendor confirmation, audit report | Hỗ trợ kiểm toán mà không đưa key bí mật vào tag |

Có thể gắn tag/label quản trị cho VM hoặc nhóm tài nguyên, ví dụ:

| Tag | Ví dụ giá trị |
|---|---|
| license-model | BYOL |
| license-product | SQL-Server-Standard |
| license-owner | data-platform-team |
| license-metric | core |
| license-contract-ref | AGR-2026-014 |
| license-review-date | 2027-03-31 |

Các giá trị trên chỉ minh họa. Không lưu product key, mật khẩu, file license hoặc thông tin hợp đồng nhạy cảm trực tiếp trong tag vì tag thường hiển thị cho nhiều người và có thể xuất hiện trong log, báo cáo hoặc API. Chỉ lưu mã tham chiếu đến kho hồ sơ được kiểm soát quyền truy cập.

### Quy trình đối soát định kỳ

1. Thu thập danh sách license đã mua từ hợp đồng, hóa đơn và hệ thống quản lý tài sản.
2. Lấy inventory VM, image, disk, host, container node và ứng dụng đang triển khai từ các cloud account.
3. Xác định mô hình license của từng image và phần mềm cài trên máy.
4. Tính nhu cầu theo đúng metric: core, VM, host, user, device, subscription hoặc mức sử dụng.
5. So sánh nhu cầu với entitlement còn hiệu lực; đánh dấu thiếu, thừa, sắp hết hạn hoặc không rõ quyền.
6. Giao owner xử lý sai lệch và lưu bằng chứng quyết định.
7. Lặp lại khi tạo VM, resize, scale, clone image, thay host hoặc chuyển region/cloud; không chỉ đợi đến kỳ kiểm toán.

## 7. Kiểm soát giấy phép trong vòng đời compute

### Trước khi tạo VM

- Chỉ cho phép image đã được phê duyệt trong catalog hoặc pipeline.
- Ghi rõ license-included hay BYOL trong cấu hình triển khai.
- Kiểm tra entitlement và điều kiện host trước khi cấp quota hoặc tạo máy.
- Chọn đúng loại máy, region, zone và tenancy theo điều khoản vendor.
- Tính cả số lượng tối đa do autoscaling hoặc rolling deployment tạo ra.

### Khi resize, clone hoặc autoscale

Resize VM có thể thay đổi số vCPU hoặc vị trí host và do đó ảnh hưởng đến metric cấp phép. Clone image hoặc tạo VM mới có thể làm tăng số máy đang chạy phần mềm. Auto Scaling có thể tạo nhiều bản sao hơn số lượng dự kiến nếu chỉ nhìn desired capacity mà bỏ qua max capacity.

Đối với license theo core, cần tính lại khi đổi size. Đối với license theo VM, cần kiểm soát số instance đồng thời. Đối với license theo host vật lý, cần biết VM được đặt trên host nào và điều kiện gán license. Với license theo user/device, cần cập nhật danh sách truy cập khi thêm người dùng hoặc thiết bị.

### Khi stop, terminate hoặc chuyển môi trường

Stop VM không nhất thiết kết thúc nghĩa vụ license. Subscription có thể tiếp tục tính phí theo kỳ; quyền license có thể vẫn được gán cho máy hoặc host trong thời gian nhất định. Terminate VM cũng không tự động giải phóng entitlement nếu hợp đồng yêu cầu thời gian chờ hoặc quy trình reassign.

Khi migration, hãy xác định ngày chuyển quyền, số ngày chạy song song được phép, phương án đồng bộ dữ liệu, thời điểm tắt máy cũ và bằng chứng chấm dứt hoặc tái gán license. Với DR, cần biết standby có được chạy đồng thời không, có yêu cầu active/passive hay không và cách tính license trong thời gian failover.

## 8. Kiểm soát phần mềm trong image và container

Image VM và container nên được build từ pipeline có kiểm soát. Pipeline có thể lưu SBOM (Software Bill of Materials), kết quả quét package, phiên bản base image và nguồn license. Khi cập nhật image, cần phát hiện package thương mại mới hoặc thay đổi edition.

Một quy trình cơ bản:

1. Chọn base image từ nguồn đã phê duyệt.
2. Quét package và tạo SBOM.
3. Đối chiếu package với danh mục phần mềm được phép và license inventory.
4. Gắn metadata về product/version/license model vào artifact hoặc registry record.
5. Chỉ phát hành image sau khi owner xác nhận quyền sử dụng.
6. Quét lại định kỳ và khi có CVE hoặc thay đổi điều khoản vendor.

Với Kubernetes hoặc nền tảng container, inventory phải tính cả node host, số replica và cơ chế autoscaling. Nếu vendor cấp phép theo core của node, cần tính tổng core của node pool có thể chạy phần mềm. Nếu cấp phép theo container hoặc instance, phải theo dõi số bản sao đồng thời và cách tính trong hợp đồng. Không lấy số pod đang chạy tại một thời điểm làm bằng chứng duy nhất nếu workload có thể scale nhanh hoặc di chuyển giữa node.

## 9. Ví dụ thực hành: chọn license cho VM Windows và SQL Server

Một nhóm cần chạy ứng dụng nội bộ trên 4 VM Windows và một database SQL Server. Nhóm có hai lựa chọn:

**Phương án A — license-included:** chọn image Windows/SQL Server có giá license kèm theo nếu sản phẩm và edition cần dùng được cung cấp. Hóa đơn cloud phản ánh phần phí theo image hoặc cấu hình. Cách này đơn giản cho thử nghiệm hoặc workload chưa có entitlement BYOL phù hợp.

**Phương án B — BYOL/Hybrid Benefit:** kiểm tra hợp đồng Windows Server và SQL Server, phiên bản/edition, số core, quyền Software Assurance hoặc subscription, quyền di chuyển lên cloud và điều kiện tenancy. Nếu đáp ứng, chọn loại VM và mô hình triển khai được phép, đăng ký quyền theo hướng dẫn nhà cung cấp, gắn metadata inventory và lưu bằng chứng.

Để so sánh, không chỉ nhân giá license-included của 4 VM với một mức giá license mua trước. Cần tính:

- Entitlement hiện có còn bao nhiêu và đã được gán cho workload nào.
- Có cần mua thêm license hoặc duy trì Software Assurance/subscription không.
- SQL Server được cấp phép theo core hay mô hình server/CAL.
- VM có thể tăng số lượng lên bao nhiêu khi autoscale hoặc DR kích hoạt.
- Có yêu cầu dedicated host, giới hạn reassign hoặc thời gian chạy song song khi migration không.
- Chi phí compute, disk, backup, network và hỗ trợ có khác nhau giữa các phương án không.

Kết quả có thể là license-included rẻ và đơn giản hơn cho workload ngắn hạn, trong khi BYOL có lợi hơn khi tổ chức đã có đủ quyền và workload ổn định. Phải dùng entitlement và giá hiện hành của môi trường thực tế để ra quyết định.

## 10. Kiểm tra inventory bằng CLI

Các lệnh dưới đây giúp thu thập một phần thông tin hạ tầng để đối soát với hồ sơ license. Chúng không xác định đầy đủ quyền sử dụng phần mềm; cần kết hợp image offer, hợp đồng, Software Assurance/subscription, host placement và inventory ứng dụng.

**AWS CLI — xem instance, image, loại máy và tenancy:**

```bash
aws ec2 describe-instances --query 'Reservations[].Instances[].{ID:InstanceId,Type:InstanceType,Image:ImageId,Platform:PlatformDetails,Tenancy:Placement.Tenancy,State:State.Name}' --output table
```

**Azure CLI — liệt kê VM và một số thuộc tính triển khai:**

```bash
az vm list --show-details --query '[].{Name:name,ResourceGroup:resourceGroup,Location:location,Size:hardwareProfile.vmSize,OS:storageProfile.osDisk.osType,LicenseType:licenseType}' --output table
```

**Google Cloud CLI — liệt kê VM, machine type, zone và labels:**

```bash
gcloud compute instances list --format='table(name,zone,machineType,status,labels)'
```

Sau khi thu thập, đối chiếu từng VM với image ID/offer, package inventory, ứng dụng đang chạy và hồ sơ quyền sử dụng. Trường license hoặc platform detail trong API có thể không thể hiện toàn bộ license của phần mềm được cài sau khi tạo máy.

## 11. Kiểm toán và xử lý sai lệch

Một cuộc kiểm toán license thường cần chứng minh cả quyền đã mua lẫn cách quyền đó được sử dụng. Hồ sơ nên bao gồm:

- Hợp đồng, order, invoice và điều khoản sản phẩm/phiên bản áp dụng.
- Số lượng entitlement, metric tính license và thời hạn.
- Bằng chứng Software Assurance, subscription hoặc quyền License Mobility nếu điều kiện yêu cầu.
- Inventory VM, host, core, user/device, container và phần mềm được cài.
- Image/marketplace offer, license model và cấu hình dedicated tenancy nếu liên quan.
- Lịch sử tạo, resize, clone, scale, stop, terminate và chuyển workload.
- Kết quả đối soát, ngoại lệ được phê duyệt và kế hoạch khắc phục.

Khi phát hiện tài nguyên chưa rõ quyền, trước tiên xác định owner, phần mềm, phiên bản và cách tính license. Tạm dừng việc mở rộng hoặc triển khai thêm bản sao nếu có nguy cơ vượt entitlement. Sau đó xác minh hợp đồng, hỏi vendor hoặc bộ phận quản lý license, chuyển sang image license-included nếu phù hợp hoặc mua bổ sung quyền sử dụng. Ghi lại quyết định và thời điểm xử lý.

Không xóa VM hoặc thay image chỉ để làm mất dấu vết kiểm toán. Cần giữ log, inventory snapshot và bằng chứng cấu hình theo chính sách lưu trữ của tổ chức. Không chia sẻ product key hoặc file license trong ticket, log hoặc báo cáo rộng quyền truy cập.

## Checklist quản lý giấy phép

- [ ] Đã xác định sản phẩm, edition, version và vendor của hệ điều hành/phần mềm.
- [ ] Đã phân loại license-included, BYOL hay pay-as-you-go/subscription.
- [ ] Đã đọc metric cấp phép: core, processor, VM, host, user, device hoặc mức sử dụng.
- [ ] Đã xác minh quyền cloud mobility, Software Assurance/subscription và điều kiện dedicated host nếu có.
- [ ] Đã chọn đúng image/offer và loại tenancy cho workload.
- [ ] Đã tính số lượng tối đa khi autoscaling, rolling update, DR và migration chạy song song.
- [ ] Đã có inventory nối entitlement với VM, host, ứng dụng và owner.
- [ ] Đã gắn tag quản trị và lưu tham chiếu hồ sơ an toàn; không đưa product key vào tag.
- [ ] Đã quét image/container, lưu SBOM và đối chiếu phần mềm thương mại.
- [ ] Đã kiểm tra định kỳ ngày hết hạn, quyền còn lại, chi phí và sai lệch.
- [ ] Đã lưu bằng chứng kiểm toán và quy trình xử lý ngoại lệ.

Quản lý giấy phép là một phần của quản trị tài nguyên compute. Hãy quyết định mô hình license trước khi triển khai, gắn quyền sử dụng với inventory thực tế và kiểm tra lại khi VM thay đổi kích thước, số lượng, host hoặc môi trường. BYOL chỉ có lợi khi entitlement phù hợp và tổ chức chứng minh được việc sử dụng đúng điều khoản.
