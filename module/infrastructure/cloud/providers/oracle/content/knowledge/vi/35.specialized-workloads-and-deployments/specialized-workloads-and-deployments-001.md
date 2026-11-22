# Oracle Cloud VMware Solution và tổ chức SDDC

Oracle Cloud VMware Solution (OCVS) cho phép triển khai trung tâm dữ liệu định nghĩa bằng phần mềm, hay **Software-Defined Data Center (SDDC)**, trên hạ tầng bare metal chuyên dụng của Oracle Cloud Infrastructure (OCI). Đây là một hướng đưa môi trường VMware lên OCI trong khi tiếp tục sử dụng nhiều kỹ năng và công cụ quản trị hiện có. [Oracle: giới thiệu OCVS](https://docs.oracle.com/en-us/iaas/Content/VMware/Concepts/ocvsoverview.htm).

Trong chương **Workload và triển khai chuyên biệt** của module **CLOUD_PROVIDERS_ORACLE**, bài này tập trung vào cách tổ chức SDDC trong bức tranh tenancy, compartment, IAM, VCN, Compute và lưu trữ của OCI. Một SDDC vận hành được cần cả thiết kế VMware, kết nối tới dịch vụ Oracle, phân quyền, quan sát hệ thống, dự phòng và quản lý chi phí.

Sau bài học, người học có thể:

- Phân biệt tài nguyên OCI với đối tượng quản trị bên trong VMware.
- Chọn ranh giới SDDC, cluster, resource pool và mạng cho từng nhóm workload.
- Lập kế hoạch địa chỉ, lưu trữ và dung lượng khi phải chịu lỗi hoặc bảo trì host.
- Mô tả luồng triển khai, di chuyển máy ảo, vận hành và khôi phục có tiêu chí kiểm chứng.

## 1. OCVS giải quyết bài toán nào?

Một doanh nghiệp đang chạy ứng dụng ERP, dịch vụ tích hợp và các máy chủ nghiệp vụ trên VMware tại trung tâm dữ liệu riêng. Ứng dụng vẫn đáp ứng nghiệp vụ, nhưng hạ tầng sắp phải thay mới. Doanh nghiệp muốn đưa workload lên OCI, tận dụng kết nối tới cơ sở dữ liệu và dịch vụ lưu trữ Oracle, đồng thời giữ thời gian thay đổi ứng dụng trong giới hạn cho phép.

OCVS là một lựa chọn cho giai đoạn chuyển hạ tầng đó. Tuy nhiên, quyết định cần dựa trên phụ thuộc thực tế của từng ứng dụng:

| Hướng triển khai | Đặc điểm phù hợp | Công việc cần đánh giá |
| --- | --- | --- |
| Chạy máy ảo trên OCVS | Cần tiếp tục dùng hệ sinh thái VMware, công cụ backup hoặc cách quản trị hiện tại | Dung lượng cluster, tương thích phần mềm, mạng và trách nhiệm vận hành VMware |
| Chuyển sang OCI Compute | Có thể chuẩn hóa lại máy chủ và quy trình quản trị theo OCI | Chuyển đổi image, driver, bootstrap, backup và tự động hóa |
| Chuyển thành container hoặc dịch vụ được quản lý | Ứng dụng cho phép thay đổi kiến trúc và cách phát hành | Dữ liệu, trạng thái, giao tiếp dịch vụ, quan sát hệ thống và kỹ năng đội ngũ |

Đây là bảng gợi ý đánh giá kiến trúc, không phải khẳng định mọi workload đều di chuyển được theo một hướng. Ví dụ, việc chuyển máy ảo ứng dụng sang OCVS và chuyển cơ sở dữ liệu sang một dịch vụ Oracle riêng là hai thay đổi khác nhau. Mỗi thay đổi cần kiểm tra khả năng tương thích và có kế hoạch quay lui riêng.

Không mặc định “giữ máy ảo” đồng nghĩa với “giữ nguyên toàn bộ môi trường”. Địa chỉ mạng, đường tới DNS, chứng thư, thời gian phản hồi giữa các tầng và các hệ thống cấp phép vẫn có thể thay đổi.

## 2. Các thành phần và hai phạm vi quản trị

### 2.1. Thành phần bên trong SDDC

Một môi trường VMware kết hợp các thành phần phục vụ tính toán, quản trị, mạng, lưu trữ và di chuyển workload:

| Thành phần | Vai trò | Điều cần nhận diện khi vận hành |
| --- | --- | --- |
| ESXi | Hypervisor chạy trên từng host bare metal | Host nào đang chạy VM nào; host nào còn đủ tài nguyên |
| vCenter Server | Điểm quản trị tập trung của môi trường vSphere | Inventory, cluster, quyền quản trị, tác vụ và cảnh báo |
| NSX | Mạng ảo và các chức năng bảo mật mạng của SDDC | Segment, gateway, Edge, tuyến và chính sách lưu lượng |
| vSAN | Lưu trữ phân tán khi sử dụng cấu hình có vSAN | Storage policy, dung lượng, tình trạng object và đồng bộ lại |
| HCX, khi được triển khai | Hỗ trợ di chuyển workload giữa các môi trường | Kết nối giữa các site và điều kiện của phương thức migration |

Không suy ra mọi shape đều dùng cùng một mô hình lưu trữ. Thiết kế datastore được trình bày riêng ở phần sau. Thành phần phần mềm và khả năng được hỗ trợ phải đối chiếu theo cấu hình OCVS được chọn. [Oracle: thành phần phần mềm VMware](https://docs.oracle.com/en-us/iaas/Content/VMware/Concepts/ocvsoverview.htm).

### 2.2. OCI và VMware có quyền quản trị khác nhau

**Phạm vi OCI** gồm tài nguyên dịch vụ SDDC, host do OCVS cấp phát, mạng VCN, VLAN, Block Volume, IAM và các dịch vụ liên quan. Console, API, CLI và công cụ hạ tầng dưới dạng mã làm việc với phạm vi này.

**Phạm vi VMware** gồm inventory của vCenter, VM, resource pool, datastore và cấu hình NSX. Người dùng cần tài khoản, vai trò và kết nối tới công cụ VMware để thao tác tại đây.

Một người có quyền xem SDDC trên OCI chưa chắc có quyền đăng nhập vCenter. Ngược lại, người quản trị VM trong vCenter chưa chắc được phép tạo thêm host trên OCI. Tích hợp danh tính có thể giúp quản lý tài khoản tập trung, nhưng vẫn phải thiết kế quyền cho từng hệ thống.

Cũng cần tách trách nhiệm của nhà cung cấp và khách hàng. Oracle bảo vệ hạ tầng vật lý, còn khách hàng chịu trách nhiệm cấu hình an toàn và cập nhật các thành phần VMware của mình. [Oracle: trách nhiệm bảo mật của OCVS](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/vmware_security.htm).

Hệ quả thực tế là đội vận hành phải có lịch bảo trì, kiểm tra tương thích, backup cấu hình và quy trình xử lý sự cố VMware. Việc SDDC được cấp phát bằng một dịch vụ cloud không tự thay thế những công việc đó.

## 3. Tổ chức SDDC, cluster và workload

### 3.1. Phân cấp cần hiểu

Có thể nhìn mô hình tổ chức theo hai nhánh song song:

~~~text
OCI
Tenancy
└── Compartment dành cho nền tảng VMware
    ├── Tài nguyên SDDC và các cluster/host liên quan
    ├── VCN, VLAN, route table và NSG
    └── Tài nguyên lưu trữ và tích hợp vận hành

VMware
vCenter của SDDC
└── Datacenter trong inventory
    ├── Unified management cluster
    │   ├── Các appliance quản trị
    │   └── Workload được cho phép theo thiết kế
    └── Workload cluster
        ├── Resource pool
        └── Máy ảo ứng dụng
~~~

Sơ đồ thể hiện cách nhìn quản trị, không khẳng định mọi tài nguyên liên quan bắt buộc nằm trong cùng một compartment. Ví dụ, đội mạng có thể quản lý VCN dùng chung trong compartment riêng và cấp quyền cần thiết cho đội nền tảng.

**Compartment OCI không tương đương folder hoặc resource pool của vCenter.** Đặt hai VM vào hai folder không làm chúng có hai phạm vi IAM OCI khác nhau. Ngược lại, đặt SDDC trong compartment riêng không tự tạo chính sách phân tách giữa các VM.

### 3.2. Unified management cluster và workload cluster

Cluster được tạo đầu tiên là **unified management cluster**, chứa những thành phần quản trị dùng chung của SDDC, bao gồm vCenter, NSX Manager và NSX Edge. Cluster này cũng có thể chứa workload. Các cluster bổ sung là **workload cluster**, không nhận một bộ thành phần quản trị SDDC riêng chỉ vì được tạo thêm. [Oracle: các loại cluster trong SDDC](https://docs.oracle.com/en-us/iaas/Content/VMware/Tasks/clusters.htm).

Điều này tạo ra một đánh đổi:

- Dùng management cluster cho cả ứng dụng giúp tận dụng tài nguyên, nhưng phải bảo vệ phần tài nguyên dành cho quản trị.
- Dành workload cluster riêng cho ứng dụng giúp quy hoạch tài nguyên và bảo trì rõ hơn.
- Dù workload nằm ở cluster khác, sự phụ thuộc vào dịch vụ quản trị dùng chung của SDDC vẫn tồn tại.

Khi vCenter gặp sự cố, nhiều VM đang chạy có thể tiếp tục hoạt động, nhưng các thao tác quản trị tập trung bị ảnh hưởng. Khi thành phần mạng gặp sự cố, mức ảnh hưởng lại phụ thuộc vai trò và cấu hình dự phòng của thành phần đó. Không dùng trạng thái “VM còn bật” làm bằng chứng rằng toàn bộ nền tảng vẫn khỏe.

### 3.3. Chọn ranh giới phù hợp

Bảng dưới là hướng dẫn thiết kế, cần điều chỉnh theo yêu cầu tổ chức:

| Ranh giới | Khi nên cân nhắc | Giới hạn của ranh giới |
| --- | --- | --- |
| Folder và tag trong vCenter | Phân loại ứng dụng, chủ sở hữu, vòng đời và phạm vi gán quyền | Không tự dành riêng CPU, RAM hoặc tạo cách ly mạng |
| Resource pool | Phân bổ shares, reservation và limit cho nhóm workload | Không thay thế chính sách mạng hoặc ranh giới quản trị SDDC |
| Cluster riêng | Khác nhu cầu phần cứng, lịch bảo trì, mức dự phòng hoặc yêu cầu bố trí workload | Vẫn dùng các thành phần quản trị chung của SDDC |
| SDDC riêng | Cần tách miền quản trị, giảm phạm vi ảnh hưởng hoặc tổ chức vòng đời độc lập | Tăng chi phí nền tảng, vận hành và kết nối |
| Compartment riêng | Phân quyền OCI, quản trị tài nguyên và theo dõi chi phí | Không tự chia quyền bên trong VMware |

Một yêu cầu như “đội thử nghiệm không được can thiệp production” phải được chuyển thành các biện pháp cụ thể: quyền vCenter, quyền NSX, quyền OCI, mạng truy cập quản trị và cách bảo vệ bí mật. Chỉ đặt tên folder là `prod` và `test` chưa đáp ứng yêu cầu.

Không cố định số cluster hoặc số host tối đa trong tài liệu thiết kế dài hạn. Các giới hạn phụ thuộc loại cluster, shape, phiên bản và hạn mức tenancy; cần tra lại trước khi triển khai. [Oracle: quản lý SDDC và giới hạn cấu hình](https://docs.oracle.com/en-us/iaas/Content/VMware/Tasks/ocvsmanagingsddc.htm).

### 3.4. Ví dụ tổ chức một môi trường production

Giả sử cần đưa 40 VM nghiệp vụ lên OCI, chia thành 24 VM ERP, 10 VM tích hợp và 6 VM dịch vụ hỗ trợ. Cơ sở dữ liệu được đánh giá riêng để đặt trên dịch vụ cơ sở dữ liệu Oracle có kết nối private.

Một phương án ban đầu:

| Đối tượng | Tên minh họa | Mục đích |
| --- | --- | --- |
| Compartment | `cmp-vmware-prod` | Quản lý tài nguyên nền tảng production |
| SDDC | `sddc-prod01` | Miền quản trị VMware production |
| Unified management cluster | `prod-unified01` | Các appliance quản trị và phần tài nguyên dự phòng của chúng |
| Workload cluster | `prod-erp01` | Chạy workload ERP, tích hợp và dịch vụ hỗ trợ |
| Resource pool | `rp-erp`, `rp-integration`, `rp-shared` | Phân bổ tài nguyên theo mức ưu tiên đã xác định |
| Nhóm bảo mật NSX | Theo vai trò web, app và dịch vụ | Áp dụng chính sách giao tiếp giữa các tầng |

Số host chỉ được chốt sau khi tính tải, phần dự phòng và kiểm tra cấu hình được OCVS hỗ trợ. Trong ví dụ này, management cluster dự kiến có ba host; workload cluster sẽ được tính ở phần dung lượng. Đây là dữ liệu giả định để học thiết kế, không phải cấu hình chuẩn cho mọi hệ thống.

## 4. Thiết kế mạng: VCN, VLAN và NSX overlay

### 4.1. Tách mạng nền và mạng của máy ảo

Ở lớp OCI, SDDC cần các tài nguyên mạng phục vụ cấp phát và hoạt động của nền tảng. Ở lớp VMware, NSX tạo các segment để kết nối VM và kiểm soát luồng ứng dụng.

Một số nhóm chức năng VLAN cần nhận diện:

| Nhóm chức năng | Loại lưu lượng |
| --- | --- |
| vSphere | Quản trị các thành phần SDDC |
| vMotion | Di chuyển trạng thái VM giữa các host |
| vSAN | Lưu lượng lưu trữ vSAN khi sử dụng |
| NSX VTEP và NSX Edge VTEP | Lưu lượng data plane của mạng overlay |
| NSX Edge Uplink | Kết nối giữa SDDC và mạng OCI |
| Provisioning và các VLAN liên quan phiên bản | Một số hoạt động cấp phát, clone hoặc migration |
| HCX, nếu bật | Lưu lượng phục vụ HCX |

Danh sách cụ thể phải theo phiên bản và workflow triển khai. Không tự suy ra công dụng của uplink hoặc xóa VLAN được dịch vụ tạo ra chỉ từ tên gọi. [Oracle: chức năng các VLAN của SDDC](https://docs.oracle.com/en-us/iaas/Content/VMware/Tasks/vlan-create.htm).

Một segment NSX chứa VM ứng dụng **không tự trở thành subnet của VCN**. VM cũng không tự xuất hiện như một OCI Compute instance để áp NSG trực tiếp theo cách của máy ảo OCI thông thường.

### 4.2. Lập kế hoạch địa chỉ trước khi tạo SDDC

Ví dụ dưới đây sử dụng các dải private không trùng nhau:

| Phạm vi | Dải minh họa | Ý nghĩa |
| --- | --- | --- |
| Trung tâm dữ liệu hiện có | `10.10.0.0/16` | Mạng tại chỗ |
| VCN dành cho OCVS | `10.60.0.0/16` | Không gian địa chỉ mạng nền OCI |
| Vùng địa chỉ dự trữ cho cluster quản trị | `10.60.0.0/21` | Để workflow phân chia subnet/VLAN theo thiết kế |
| Vùng địa chỉ dự trữ cho workload cluster | `10.60.8.0/21` | Dự kiến cho tài nguyên mạng của cluster bổ sung |
| VCN dịch vụ cơ sở dữ liệu | `10.80.0.0/16` | Chứa các subnet dịch vụ phù hợp |
| Segment NSX cho web | `172.20.10.0/24` | Mạng VM tầng web |
| Segment NSX cho app | `172.20.20.0/24` | Mạng VM tầng ứng dụng |

Hai vùng `/21` là **phần địa chỉ được dành trước**, không phải yêu cầu tạo nguyên mỗi vùng thành một subnet duy nhất. Sizing và cách chia thực tế phải khớp số host dự kiến, tài nguyên mạng mà workflow yêu cầu và kế hoạch mở rộng. Oracle cho phép workflow tạo mạng hoặc sử dụng các tài nguyên mạng đã chuẩn bị. [Oracle: chuẩn bị và tạo SDDC](https://docs.oracle.com/en-us/iaas/Content/VMware/Tasks/ocvssettingupsddc.htm).

Khi lập kế hoạch, cần đối chiếu thêm mạng VPN của người dùng, mạng đối tác, site DR và các vùng NSX đang dùng tại chỗ. Hai mạng không trùng ở thời điểm tạo SDDC vẫn có thể xung đột khi kết nối thêm đối tác sau này.

Không chữa xung đột CIDR bằng cách thêm route tùy ý. Cần chọn phương án địa chỉ hoặc NAT có chủ đích, ghi rõ tác động tới DNS, nhật ký, bảo mật và migration.

### 4.3. Hiểu đường đi và đường về

Ví dụ VM ứng dụng cần kết nối database trong VCN khác:

~~~mermaid
flowchart LR
    VM["VM ứng dụng"]
    SEG["NSX segment"]
    GW["Gateway NSX T1 / T0"]
    EDGE["NSX Edge Uplink"]
    OCI["Mạng OCI và DRG"]
    DB["Subnet dịch vụ database"]

    VM --> SEG --> GW --> EDGE --> OCI --> DB
    DB -. "Đường về phải tới được CIDR overlay" .-> OCI
    OCI -.-> EDGE
    EDGE -.-> GW
    GW -.-> VM
~~~

Đây là sơ đồ luồng logic; T1/T0 và Edge không nhất thiết tương ứng với từng thiết bị vật lý tách biệt.

Khi kết nối tới VCN khác, cần kiểm tra route của subnet đích, route của DRG và cấu hình phía OCVS để tới được CIDR overlay. Hướng dẫn của Oracle minh họa việc khai báo route tới mạng NSX qua DRG và workflow kết nối SDDC. [Oracle: kết nối NSX overlay tới VCN khác](https://docs.oracle.com/en/learn/oci-connect-ocvs-nsxt-overlay/index.html).

Với mạng tại chỗ, DRG kết hợp FastConnect hoặc Site-to-Site VPN tạo đường kết nối private. Workflow OCVS có thể hỗ trợ các tài nguyên định tuyến và bảo mật giữa DRG với NSX Edge Uplink. Vẫn cần kiểm tra cấu hình và đường về ở phía trung tâm dữ liệu. [Oracle: kết nối SDDC với mạng tại chỗ](https://docs.oracle.com/en-us/iaas/Content/VMware/Tasks/ocvsconfigconnectivity_topic-Configuring_Connectivity_to_Your_Onpremises_Network.htm).

Một kết nối thành công cần đồng thời có:

1. Địa chỉ nguồn và đích không gây xung đột.
2. DNS trả về địa chỉ đúng với đường truy cập dự kiến.
3. Route cho cả hai chiều.
4. Chính sách bảo mật cho phép đúng giao thức và cổng.
5. Dịch vụ đích đang lắng nghe.
6. MTU và đường truyền phù hợp với kiểu lưu lượng.

Ví dụ, ping thành công không chứng minh kết nối database đã hoạt động. Cần thử tới listener thực tế, rồi kiểm tra xác thực và một giao dịch nghiệp vụ đơn giản.

### 4.4. Phân đoạn bảo mật theo luồng nghiệp vụ

Không mở toàn bộ mạng chỉ để hoàn thành migration. Hãy mô tả luồng cần thiết:

| Nguồn | Đích | Luồng minh họa | Mục đích |
| --- | --- | --- | --- |
| Mạng quản trị được kiểm soát | Endpoint quản trị VMware | HTTPS và các cổng quản trị thực sự cần | Vận hành nền tảng |
| Điểm vào ứng dụng | Nhóm web | TCP 443 | Truy cập web |
| Nhóm web | Nhóm app | TCP 8443, nếu ứng dụng dùng | Xử lý nghiệp vụ |
| Nhóm app | Database listener | Cổng được cấu hình, ví dụ TCP 1521 | Kết nối dữ liệu |
| VM và appliance | DNS/NTP đã chọn | Giao thức phục vụ DNS/NTP | Phân giải tên và đồng bộ thời gian |
| Thành phần backup | Đối tượng được bảo vệ | Theo sản phẩm backup | Sao lưu và khôi phục |

Cổng trong bảng là ví dụ thiết kế; phải thay bằng giao thức của hệ thống thực. Đặc biệt, cổng listener không tự chứng minh đường truyền database đã được mã hóa.

Phân công nơi thực thi rõ ràng: NSG và cấu hình mạng OCI bảo vệ các ranh giới OCI thích hợp; chính sách NSX kiểm soát luồng trong SDDC; firewall của hệ điều hành bảo vệ máy đích. Muốn chứng minh VM test không tới được VM production, phải thử đúng luồng giữa hai VM đó, kể cả khi lưu lượng không đi ra khỏi SDDC.

## 5. Tổ chức lưu trữ và tính dung lượng chịu lỗi

### 5.1. Chọn mô hình datastore theo shape

Dense shape có lưu trữ NVMe cục bộ phục vụ vSAN; Standard shape không cung cấp loại NVMe cục bộ đó và sử dụng OCI Block Volume cho nhu cầu lưu trữ phù hợp. Vì vậy, cần chọn shape cùng với mô hình datastore, không chỉ nhìn CPU và RAM. [Oracle: câu hỏi thường gặp về shape và lưu trữ OCVS](https://www.oracle.com/cloud/compute/vmware/faq/).

| Khía cạnh | vSAN với lưu trữ cục bộ | Datastore VMFS trên OCI Block Volume |
| --- | --- | --- |
| Nguồn dung lượng | Thiết bị lưu trữ của các host tham gia | Block Volume được chuẩn bị và gắn theo cấu hình được hỗ trợ |
| Quan hệ với mở rộng host | Thêm host có thể bổ sung cả tính toán và lưu trữ | Có thể lập kế hoạch dung lượng lưu trữ riêng với tính toán |
| Nội dung phải theo dõi | Policy, object health, dung lượng trống và resync | Datastore, đường truy cập, dung lượng và hiệu năng volume |
| Rủi ro thiết kế | Nhầm raw capacity với dung lượng dùng được | Nhầm việc tạo volume trên OCI với hoàn tất cấu hình VMware |

OCVS có **Datastore Management** để quản lý phía OCI của datastore và datastore cluster dựa trên Block Volume. Chức năng này không quản lý toàn bộ cấu hình block storage bên trong vCenter; đội vận hành vẫn phải kiểm tra phía VMware. [Oracle: Datastore Management và giới hạn trách nhiệm](https://docs.oracle.com/en-us/iaas/Content/VMware/Tasks/datastores.htm).

### 5.2. Dung lượng raw khác dung lượng khả dụng

Với vSAN, storage policy quyết định cách bảo vệ dữ liệu và lượng dung lượng tiêu thụ. Một phép tính sơ bộ có thể viết:

~~~text
Dung lượng cho dữ liệu ứng dụng
≈ (Dung lượng raw / hệ số bảo vệ dữ liệu)
  × (1 - tỷ lệ dung lượng dự phòng)
  - các phần tiêu thụ khác
~~~

Ví dụ giả định độc lập với cấu hình ERP: bốn host cung cấp tổng cộng 60 TB raw. Nếu dùng mô hình mirroring hai bản sao, hệ số sơ bộ là 2:

~~~text
60 TB / 2 = 30 TB

Nếu tiếp tục dành 20% phần này làm khoảng trống:
30 TB × 0,8 = 24 TB
~~~

24 TB chỉ là ước lượng giảng giải. Metadata, policy cụ thể, snapshot, dữ liệu quản trị và khả năng rebuild còn làm thay đổi kết quả. Cũng không dùng hệ số mirroring này cho mọi cấu hình RAID hoặc mọi thế hệ vSAN.

Kế hoạch lưu trữ phải trả lời được: sau một lỗi host, hệ thống còn phục vụ dữ liệu được không, còn đủ chỗ để tái lập mức bảo vệ không, và quá trình tái lập đó ảnh hưởng độ trễ thế nào.

### 5.3. Sizing theo trạng thái có lỗi

Mức sử dụng bình thường thấp chưa đủ chứng minh khả năng chịu lỗi. Một kiểm tra RAM sơ bộ:

~~~text
(N - F) × R × U ≥ D + M
~~~

Trong đó:

- N: số host trong cluster.
- F: số host dự kiến không khả dụng cùng lúc do lỗi hoặc bảo trì.
- R: RAM của mỗi host trong mô hình đồng nhất.
- U: tỷ lệ sử dụng tối đa mục tiêu trên các host còn lại.
- D: nhu cầu RAM workload.
- M: phần dự toán cho hệ thống và các thành phần liên quan chưa tính trong D.

Giả sử workload ERP cần 620 GiB, phần dự toán hệ thống là 64 GiB, mỗi host có 256 GiB và mục tiêu sử dụng tối đa là 80%. Muốn chịu mất một host:

~~~text
N = 4:
(4 - 1) × 256 × 0,8 = 614,4 GiB
D + M = 620 + 64 = 684 GiB
=> Không đạt.

N = 5:
(5 - 1) × 256 × 0,8 = 819,2 GiB
=> Đạt kiểm tra RAM sơ bộ.
~~~

Như vậy, phương án minh họa chọn ít nhất năm host cho workload cluster theo giả định này. Kết quả chưa xác nhận cấu hình cuối cùng: còn phải kiểm tra CPU, phân bố VM lớn, reservation, độ trễ lưu trữ, băng thông, giới hạn shape và tăng trưởng.

Không chuyển trực tiếp số vCPU thành OCPU bằng một tỷ lệ cố định rồi kết luận đủ tài nguyên. CPU ready, tải đồng thời, kiến trúc bộ xử lý và yêu cầu của VM lớn đều có thể làm thay đổi kết quả.

Nếu yêu cầu là “một host bảo trì trong lúc một host khác hỏng”, phải tính F = 2 và kiểm tra lại cả compute lẫn storage. N+1 không tự đáp ứng N+2.

### 5.4. Bảo vệ tài nguyên quản trị

Với unified management cluster, cần chừa đủ tài nguyên cho các appliance khi host lỗi, khi nâng cấp và khi phát sinh thao tác quản trị nặng. Khi cho ứng dụng dùng chung cluster này, phải có chính sách ưu tiên và giới hạn phù hợp.

Tránh đặt limit quá thấp khiến appliance quản trị thiếu tài nguyên dù cluster vẫn còn RAM hoặc CPU rảnh. Cũng tránh reservation thiếu cơ sở làm giảm khả năng bố trí lại VM trong tình huống có lỗi.

## 6. Danh tính, quyền và thông tin vận hành

### 6.1. Ma trận trách nhiệm đề xuất

| Nhóm | Quyền OCI theo nhiệm vụ | Quyền VMware theo nhiệm vụ |
| --- | --- | --- |
| Đội nền tảng | Quản lý tài nguyên OCVS được giao | Quản trị cluster, host và vòng đời nền tảng |
| Đội mạng | Quản lý VCN, VLAN, route, NSG hoặc DRG trong phạm vi được giao | Quản trị mạng NSX nếu được phân công |
| Đội ứng dụng | Xem tài nguyên OCI cần thiết | Quản trị VM của ứng dụng trong phạm vi được cấp |
| Đội giám sát | Đọc trạng thái, metric và log được cho phép | Đọc inventory, alarm và dữ liệu vận hành cần thiết |
| Đội kiểm toán | Đọc bằng chứng và nhật ký thích hợp | Xem cấu hình và sự kiện theo phạm vi kiểm toán |

Đây là ma trận thiết kế, không phải một tập policy hoàn chỉnh có thể sao chép áp dụng. Policy thực phải xét tên nhóm, identity domain, compartment chứa tài nguyên phụ thuộc và quyền của từng API.

Ưu tiên tài khoản định danh cho công việc hằng ngày. Tài khoản quyền cao phục vụ khôi phục khẩn cấp cần được kiểm soát, lưu bí mật và ghi nhận việc sử dụng. Không đưa mật khẩu appliance, khóa SSH hoặc token vào tài liệu thiết kế, repository hay log pipeline.

Quyền xem metadata tài nguyên cũng cần được cân nhắc: thông tin endpoint, tên máy và cấu trúc hạ tầng có thể nhạy cảm dù không trực tiếp chứa mật khẩu.

### 6.2. Gắn nhãn và theo dõi chủ sở hữu

Ví dụ nhãn thiết kế:

~~~yaml
environment: prod
owner: platform-team
cost-center: erp
application: shared-vmware-platform
recovery-tier: critical
data-classification: internal
~~~

Đây là quy ước minh họa, không phải cú pháp nhập trực tiếp cho API OCVS. Khi triển khai, chuyển thành defined tags hoặc free-form tags phù hợp trên OCI và nhãn tương ứng ở VMware.

Tag ở SDDC không tự phân bổ chính xác chi phí cho từng VM. Muốn phân bổ nội bộ, cần dữ liệu inventory và quy tắc như tài nguyên được cấp, tài nguyên thực dùng hoặc dung lượng dự trữ. Phải ghi rõ cách chia phần chi phí nền tảng dùng chung.

## 7. Quy trình triển khai SDDC có thể kiểm chứng

### 7.1. Chuẩn bị đầu vào

Trước khi tạo tài nguyên, hoàn thành các quyết định sau:

1. **Vị trí và capacity:** region, availability domain, shape, phiên bản được hỗ trợ, hạn mức và khả năng cấp phát host.
2. **Tổ chức:** compartment, chủ sở hữu, cách chia SDDC và cluster.
3. **Mạng:** CIDR, DNS, NTP, đường quản trị, đường tới mạng tại chỗ và các dịch vụ phụ thuộc.
4. **Lưu trữ:** datastore, policy bảo vệ, dung lượng khả dụng và hiệu năng mục tiêu.
5. **Vận hành:** quyền truy cập, nơi giữ bí mật, giám sát, backup và đầu mối xử lý sự cố.
6. **Chi phí:** shape, kỳ cam kết, chi phí mạng, lưu trữ và kế hoạch kết thúc môi trường thử nghiệm.

Với cấu hình dùng Standard shape, cần chuẩn bị datastore cluster theo yêu cầu workflow tạo SDDC hiện hành. Không mặc định quy trình tạo volume của một hướng dẫn cũ vẫn áp dụng. [Oracle: điều kiện trước khi tạo SDDC](https://docs.oracle.com/en-us/iaas/Content/VMware/Tasks/ocvssettingupsddc.htm).

### 7.2. Trình tự thực hiện và bằng chứng

| Giai đoạn | Việc thực hiện | Bằng chứng cần có |
| --- | --- | --- |
| Chuẩn bị OCI | Thiết lập compartment, policy, mạng, địa chỉ và lưu trữ cần thiết | Danh sách tài nguyên, kết quả kiểm tra trùng CIDR và quyền |
| Cấp phát SDDC | Chọn cluster đầu tiên, shape, host, mạng và phần mềm | Work request hoàn tất, tài nguyên đạt trạng thái phù hợp |
| Kiểm tra quản trị | Truy cập vCenter, NSX và host qua đường quản trị | Đăng nhập thành công bằng tài khoản được phân quyền |
| Kiểm tra nền tảng | Xem tình trạng cluster, datastore, mạng và các appliance | Không còn lỗi nền tảng chặn nghiệm thu |
| Chuẩn bị workload | Tạo resource pool, segment, policy và VM mẫu | VM nhận đúng mạng, DNS và cấu hình mong muốn |
| Kiểm thử dịch vụ | Kiểm tra ứng dụng, giám sát, backup và restore | Bằng chứng kết nối, cảnh báo và khôi phục dữ liệu |

Trạng thái tài nguyên OCI sẵn sàng chỉ là một điều kiện. Nghiệm thu nền tảng còn cần các bài thử ở phía VMware và ứng dụng.

### 7.3. Quan sát bằng OCI CLI

Đoạn PowerShell sau chỉ minh họa thao tác đọc metadata. Cần cài OCI CLI, cấu hình profile và có quyền phù hợp; thay các giá trị mẫu bằng môi trường của mình:

~~~powershell
$ociRegion = "REGION_NAME"
$sddcId = "ocid1.sddc.REPLACE_WITH_REAL_OCID"

oci ocvs sddc get --sddc-id $sddcId --profile TRAINING --region $ociRegion --query 'data.{Name:"display-name",State:"lifecycle-state",Id:id}' --output table

oci ocvs cluster list --sddc-id $sddcId --all --profile TRAINING --region $ociRegion --query 'data[].{Name:"display-name",State:"lifecycle-state",Id:id}' --output table
~~~

Lệnh đầu đọc SDDC đã chọn; lệnh sau liệt kê các cluster thuộc SDDC đó. Bộ lọc chỉ xuất một số trường phục vụ kiểm kê. Đây là thông tin từ API OCI, không phải danh sách tất cả VM trong vCenter. Tham khảo [lệnh lấy thông tin SDDC](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/ocvs/sddc/get.html) và [lệnh liệt kê cluster](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/ocvs/cluster/list.html).

Nếu kết quả rỗng hoặc truy cập bị từ chối, kiểm tra profile, region, OCID và policy trước khi kết luận rằng tài nguyên đã mất. Không xử lý lỗi đọc bằng cách cấp quyền quản trị toàn tenancy một cách mặc định.

### 7.4. Tự động hóa với phạm vi rõ ràng

Có thể tách luồng tự động hóa thành ba phần:

- **Hạ tầng OCI:** compartment, mạng, SDDC, cluster và tài nguyên lưu trữ được công cụ hỗ trợ.
- **Cấu hình VMware:** inventory, resource pool, segment, policy và VM thông qua công cụ phù hợp.
- **Cấu hình ứng dụng:** hệ điều hành, agent, cấu hình dịch vụ và phát hành phần mềm.

Định nghĩa rõ phần nào là nguồn cấu hình chuẩn, phần nào do dịch vụ OCVS tạo và quản lý. Nếu hai pipeline cùng sửa một route hoặc một cấu hình NSX, trạng thái có thể bị thay đổi qua lại ngoài dự kiến.

Với pipeline tạo hạ tầng, lưu plan để review, kiểm soát state có dữ liệu nhạy cảm, theo dõi work request và thiết kế khả năng tiếp tục sau khi một giai đoạn thất bại. Một API trả về thành công khi nhận yêu cầu chưa chứng minh thao tác bất đồng bộ đã hoàn tất.

## 8. Di chuyển workload bằng HCX và tổ chức đợt chuyển đổi

HCX hỗ trợ các hoạt động di chuyển ứng dụng và workload giữa môi trường nguồn và OCVS. Khả năng cụ thể phụ thuộc phiên bản, loại license và phương thức migration. HCX cũng cần các kết nối phục vụ hoạt động, kích hoạt và cập nhật theo yêu cầu của giải pháp. [Oracle: HCX trong OCVS](https://docs.oracle.com/en-us/iaas/Content/VMware/Concepts/ocvsoverview.htm).

### 8.1. Chuẩn bị theo nhóm phụ thuộc ứng dụng

Không nên gom VM thành đợt chỉ theo số lượng. Ví dụ, một đợt ERP có thể gồm máy xử lý đơn hàng, máy tích hợp kho và dịch vụ xác thực mà chúng phụ thuộc.

Với mỗi nhóm, ghi lại:

| Thông tin | Nội dung cần biết |
| --- | --- |
| Chủ sở hữu | Người quyết định ứng dụng đạt hoặc không đạt |
| Phụ thuộc | DNS, thời gian, danh tính, file share, queue, database và đối tác |
| Dữ liệu | Nơi ghi dữ liệu chính, cách đồng bộ và điểm nhất quán |
| Giới hạn gián đoạn | Khoảng dừng tối đa và thời điểm chuyển đổi |
| Kiểm thử | Giao dịch đại diện, tiêu chí hiệu năng và kiểm tra tích hợp |
| Quay lui | Điều kiện kích hoạt, người quyết định và cách xử lý dữ liệu đã phát sinh |

### 8.2. Ước lượng thời gian truyền

Có thể ước lượng tối thiểu:

~~~text
Thời gian truyền
≈ Dung lượng phải truyền / Băng thông hữu dụng
~~~

Ví dụ dữ liệu cần truyền là 2 TiB, đường truyền danh nghĩa 500 Mbit/s và giả định chỉ đạt 65% hiệu suất hữu dụng:

~~~text
Băng thông hữu dụng = 500 × 0,65 = 325 Mbit/s

Thời gian ≈ (2 × 1024^4 × 8) / (325 × 10^6)
          ≈ 54.130 giây
          ≈ 15 giờ
~~~

Đây là phép tính cho dữ liệu truyền ban đầu, chưa phải thời gian ngừng ứng dụng. Tốc độ ghi mới ở nguồn, phần đồng bộ cuối, số luồng song song và giới hạn lưu trữ có thể kéo dài quá trình.

Nếu dữ liệu thay đổi nhanh hơn tốc độ sao chép hữu dụng, hệ thống có thể không hội tụ trước giờ cắt chuyển. Phải đo trong thử nghiệm bằng workload đại diện.

### 8.3. Thực hiện cắt chuyển có kiểm soát

Một đợt chuyển đổi nên đi qua các mốc:

1. Kiểm tra backup và khả năng phục hồi nguồn.
2. Xác nhận kết nối, tài nguyên đích và quyền thao tác.
3. Đồng bộ hoặc truyền dữ liệu theo phương thức được chọn.
4. Dừng ghi hoặc điều phối ghi theo kế hoạch nhất quán.
5. Hoàn tất phần đồng bộ cuối và chuyển luồng truy cập.
6. Chạy giao dịch nghiệm thu, theo dõi lỗi và hiệu năng.
7. Chỉ kết thúc thời hạn quay lui sau khi chủ ứng dụng chấp thuận.

Nếu workload cần kéo dài mạng Layer 2 trong giai đoạn chuyển tiếp, phải ghi rõ mục đích và thời điểm kết thúc. Việc VM giữ được IP không chứng minh đường truy cập tới database, DNS hoặc hệ thống ngoài cloud đã tối ưu.

Kế hoạch quay lui cần xử lý dữ liệu phát sinh trên đích. Sau khi ứng dụng đã ghi dữ liệu mới, bật lại VM nguồn từ trạng thái cũ có thể tạo hai bản dữ liệu mâu thuẫn. Phải biết bản nào được coi là nguồn dữ liệu có thẩm quyền và cách đồng bộ ngược nếu cần.

## 9. Tính sẵn sàng, backup và khôi phục thảm họa

### 9.1. Phân biệt các lớp bảo vệ

| Cơ chế | Sự cố muốn xử lý | Điều vẫn cần giải quyết |
| --- | --- | --- |
| vSphere HA | Host lỗi và VM cần được khởi động lại trên host còn lại | Thời gian khởi động lại và phục hồi ứng dụng |
| Dự phòng mạng | Một thành phần hoặc đường mạng lỗi | Hội tụ, đường về và trạng thái phiên |
| Chính sách bảo vệ dữ liệu lưu trữ | Mất một số thành phần theo policy được hỗ trợ | Xóa nhầm, hỏng logic hoặc dữ liệu bị mã hóa độc hại |
| Backup | Khôi phục về bản dữ liệu trước đó | Thời gian restore, tính nhất quán và phạm vi dữ liệu mất |
| DR sang địa điểm khác | Sự cố vượt phạm vi bảo vệ của site chính | Capacity đích, replication, DNS, trình tự phục hồi và failback |

HA thường khởi động lại VM; điều này khác với ứng dụng hoạt động liên tục không mất phiên. Một ứng dụng chịu lỗi tốt còn cần thiết kế nhiều instance, quản lý trạng thái và xử lý retry phù hợp.

### 9.2. Fault domain, availability domain và region

Trong thiết kế single-AD, việc phân bố host qua các fault domain giúp giảm tác động của một số lỗi hạ tầng cục bộ. Nó không tự cung cấp phương án khi cả availability domain hoặc region bị gián đoạn.

OCVS cũng có khả năng Multi-AD với điều kiện áp dụng riêng; không giả định mọi shape, region và tenancy đều sử dụng được theo cùng một cách. Thiết kế trải rộng phải đánh giá thêm độ trễ, lưu lượng lưu trữ và yêu cầu được Oracle hỗ trợ. [Oracle: phân bố host và khả năng Multi-AD](https://docs.oracle.com/en-us/iaas/Content/VMware/Concepts/ocvsoverview.htm).

Với yêu cầu DR khác region, cần một thiết kế độc lập về vị trí phục hồi, dữ liệu, kết nối và tài nguyên. Chỉ sao chép file của VM chưa đủ nếu còn thiếu DNS, dịch vụ danh tính, khóa giải mã hoặc kết nối database.

### 9.3. RPO, RTO và bằng chứng phục hồi

- **RPO** mô tả mức dữ liệu có thể mất, thường diễn đạt bằng khoảng thời gian.
- **RTO** mô tả thời gian mục tiêu để khôi phục dịch vụ sau gián đoạn.

Ví dụ, RPO 15 phút và RTO 2 giờ là mục tiêu nghiệp vụ. Muốn chứng minh đạt, phải ghi nhận thời điểm dữ liệu cuối cùng có thể phục hồi và thời điểm giao dịch ứng dụng chạy lại thành công.

Backup cần bao phủ cả dữ liệu ứng dụng và thông tin tái lập nền tảng: cấu hình vCenter/NSX theo phương thức được hỗ trợ, inventory, chính sách mạng, bí mật và các bước khôi phục. Snapshot của VM thường phụ thuộc vào chuỗi dữ liệu của VM, nên không dùng riêng snapshot làm phương án bảo vệ dài hạn.

Khi thử restore, chọn dữ liệu hoặc VM đại diện và môi trường cách ly phù hợp. Kiểm tra tính toàn vẹn, quyền truy cập và giao dịch nghiệp vụ, thay vì chỉ kiểm tra máy ảo bật được.

### 9.4. Single-host SDDC có phạm vi riêng

Single-host SDDC phục vụ thử nghiệm hoặc phát triển ngắn hạn; Oracle không hỗ trợ production workload trên loại cấu hình này. Nó không có khả năng chịu lỗi host như một cluster nhiều host và không thể nâng cấp trực tiếp thành SDDC nhiều cluster. Khi cần production, phải lập phương án di chuyển workload sang môi trường phù hợp. [Oracle: giới hạn single-host SDDC](https://docs.oracle.com/en-us/iaas/Content/VMware/Tasks/ocvsmanagingsddc.htm).

Không dùng kết quả “ứng dụng chạy được trên một host” làm bằng chứng về tính sẵn sàng hoặc dung lượng chịu lỗi của production.

## 10. Giám sát và bảo trì trong suốt vòng đời

### 10.1. Quan sát nhiều lớp

Một bộ chỉ số vận hành nên trả lời được cả tình trạng nền tảng lẫn chất lượng dịch vụ:

| Lớp | Tín hiệu nên theo dõi | Hành động gắn với cảnh báo |
| --- | --- | --- |
| OCI | Work request lỗi, trạng thái tài nguyên, kết nối mạng | Xác định thao tác hoặc thành phần OCI bị ảnh hưởng |
| Host và cluster | CPU contention, memory pressure, mất host, capacity còn lại | Đánh giá nguy cơ vi phạm mức dự phòng |
| Lưu trữ | Dung lượng trống, độ trễ, lỗi đường truy cập, tình trạng bảo vệ | Ngăn hết chỗ, xác định phạm vi VM ảnh hưởng |
| NSX và kết nối | Trạng thái Edge, tunnel, drop và thay đổi tuyến | Kiểm tra đúng đoạn mạng đang gây lỗi |
| VM và ứng dụng | Lỗi dịch vụ, thời gian phản hồi, tỷ lệ giao dịch thành công | Đo tác động thực tế tới nghiệp vụ |
| Backup | Job lỗi, tuổi bản backup, kết quả restore gần nhất | Đảm bảo dữ liệu còn khả năng phục hồi |

Không đặt ngưỡng chỉ dựa trên phần trăm sử dụng trung bình. Với cluster năm host, cần biết tải sau khi mất một host và mức tăng trưởng trước lần mở rộng tiếp theo.

Nếu triển khai VMware Solution Management Appliance, có thể cấu hình các metric ESXi được gửi tới OCI Monitoring qua phần tích hợp trong vSphere. Phải thiết lập appliance, kết nối và lựa chọn metric; không mặc định mọi dữ liệu đã tự động được thu thập. [Oracle: cấu hình xuất metric](https://docs.oracle.com/en-us/iaas/Content/VMware/Tasks/ocvs-management-app-metrics.htm).

Oracle Log Analytics có giải pháp thu thập và phân tích sự kiện, log và tín hiệu vận hành VMware khi được cấu hình. Đây là một lựa chọn tập trung dữ liệu, cần dự toán cả lượng dữ liệu thu thập và thời gian lưu. [Oracle: VMware Monitoring Solution](https://docs.oracle.com/en-us/iaas/log-analytics/doc/vmware-monitoring-solution.html).

OCI Audit và log của VMware phục vụ các phạm vi khác nhau. Muốn điều tra ai đổi cấu hình VM hoặc policy NSX, phải có dữ liệu từ công cụ VMware tương ứng; không chỉ tìm trong lịch sử API OCI.

### 10.2. Bảo trì một host theo trình tự

Một quy trình bảo trì điển hình:

1. Kiểm tra sức khỏe cluster, backup và khả năng tiếp tục phục vụ khi thiếu host đó.
2. Kiểm tra tương thích giữa ESXi, vCenter, NSX, lưu trữ, HCX và các công cụ bổ sung.
3. Bảo đảm có đủ tài nguyên để di chuyển hoặc dừng workload theo kế hoạch.
4. Đưa host vào trạng thái bảo trì bằng workflow được hỗ trợ; xử lý dữ liệu vSAN phù hợp với tình huống.
5. Áp dụng thay đổi, xác nhận host và các thành phần liên quan hoạt động đúng.
6. Chờ quá trình đồng bộ lại cần thiết hoàn thành rồi kiểm tra ứng dụng.
7. Chuyển sang host tiếp theo sau khi tiêu chí sức khỏe đạt.

Nếu dùng công cụ tự động thêm host, thay host hoặc nâng cấp của OCVS, vẫn phải kiểm tra bước nào đã được công cụ thực hiện. Không mặc định mọi thao tác phía OCI đều đã hoàn tất các bước bên trong VMware.

Không xóa trực tiếp tài nguyên Compute hoặc storage nền của SDDC để thay thế thao tác lifecycle được OCVS hỗ trợ. Việc cấp phát host mới cũng cần kiểm tra capacity thực tế, không chỉ hạn mức cho phép.

## 11. Kiểm soát chi phí của một SDDC

### 11.1. Tính chi phí theo nền tảng

Mô hình chi phí sơ bộ:

~~~text
Tổng chi phí
= host và các quyền sử dụng liên quan theo mô hình hợp đồng
+ lưu trữ bổ sung
+ kết nối và truyền dữ liệu
+ backup và vị trí phục hồi
+ giám sát, log và lưu giữ dữ liệu
+ công cụ bổ sung
+ công sức vận hành
~~~

Dừng một VM không có nghĩa là ngừng chi phí bare metal host đang được cấp phát. Vì thế, cần phân biệt tiết kiệm bằng tối ưu VM với tiết kiệm thực sự bằng thay đổi số host, shape hoặc mô hình lưu trữ.

Kỳ tính phí có thể gắn với cam kết sử dụng. Xóa host trước khi kết thúc cam kết không mặc nhiên chấm dứt nghĩa vụ thanh toán của kỳ đó. Trước khi tạo hoặc thay đổi host, đọc điều khoản kỳ cam kết áp dụng cho cấu hình cụ thể. [Oracle: các lựa chọn tính phí OCVS](https://docs.oracle.com/en-us/iaas/Content/VMware/Concepts/billing-options.htm).

Không lấy một cấu hình tối thiểu làm dự toán đầy đủ cho production. Ví dụ ERP còn cần phần dư chịu lỗi, dự phòng tăng trưởng, backup và khả năng phục hồi.

### 11.2. Biện pháp thực tế

- Đo tải trước migration và sau từng đợt để hiệu chỉnh sizing.
- Gom workload theo yêu cầu tài nguyên và chính sách được phép, đồng thời giữ mức dự phòng.
- So sánh phương án bổ sung host với bổ sung storage khi storage là nút thắt.
- Theo dõi tài nguyên dùng cho migration, backup tạm và thử nghiệm để kết thúc đúng hạn.
- Gắn chủ sở hữu, mục đích và ngày đánh giá lại cho từng môi trường.
- Lập budget và cảnh báo để đội chịu trách nhiệm xử lý; cảnh báo không thay cho quy trình kiểm soát cấp phát.
- Kiểm tra lại dung lượng sau khi loại bỏ tài nguyên để tránh làm mất mức bảo vệ cần thiết.

Cần xác minh quyền sử dụng phần mềm VMware, công cụ bổ sung và phần mềm Oracle chạy trong môi trường theo hợp đồng áp dụng. Đặc biệt, việc kết nối tới một dịch vụ database hoặc đặt database trong VM là các mô hình khác nhau về vận hành và quyền sử dụng. Không suy ra entitlement chỉ từ tên dịch vụ cloud.

## 12. Thực hành lập phương án và nghiệm thu

Phần thực hành sử dụng ví dụ ERP ở trên. Có thể làm phần thiết kế mà chưa cần cấp phát SDDC. Phần thao tác thực hiện trên môi trường đào tạo hoặc môi trường đã được tổ chức cho phép.

### Bước 1: Hoàn thành bản thiết kế

Ghi rõ:

- Ranh giới compartment, SDDC, management cluster và workload cluster.
- Nhóm tài khoản OCI, vCenter và NSX cùng phạm vi nhiệm vụ.
- Không gian địa chỉ VCN, phần dành cho mạng cluster và các segment ứng dụng.
- Luồng quản trị, luồng tới mạng tại chỗ và luồng tới dịch vụ database.
- Giả định CPU, RAM, storage, mức dự phòng và tăng trưởng.
- Phương án backup, RPO/RTO và cách chứng minh kết quả.

Với giả định RAM trong bài, phải nhận diện rằng bốn host workload không đạt kiểm tra chịu mất một host, còn năm host đạt kiểm tra RAM sơ bộ. Nếu thay nhu cầu ứng dụng hoặc shape, tính lại thay vì giữ số host theo thói quen.

### Bước 2: Kiểm kê môi trường hiện có

Dùng Console hoặc hai lệnh CLI ở phần triển khai để đối chiếu đúng SDDC và các cluster. Sau đó dùng vCenter để kiểm tra host, datastore, network và VM mẫu.

Kết quả mong đợi là giải thích được mỗi đối tượng đang xem thuộc phạm vi OCI hay VMware, do ai quản lý và phụ thuộc vào tài nguyên nào.

### Bước 3: Kiểm tra luồng được phép và bị cấm

Trên VM mẫu và endpoint được phép thử:

1. Kiểm tra phân giải DNS tới dịch vụ mục tiêu.
2. Thử kết nối tới đúng cổng dịch vụ đã khai báo.
3. Chạy một giao dịch đơn giản để xác nhận đường ứng dụng.
4. Thử một luồng được thiết kế là bị cấm và ghi nhận bằng chứng phù hợp.
5. Kiểm tra log hoặc công cụ chẩn đoán để xác định lớp thực thi chính sách.

Nếu luồng tới database thất bại, lần theo thứ tự: địa chỉ đích, gateway của VM, policy NSX, Edge, route OCI/DRG, chính sách phía database và dịch vụ đích. Chỉ thay đổi một nguyên nhân đã xác định trong mỗi lần kiểm tra.

### Bước 4: Kiểm chứng quan sát và khôi phục

Xác nhận một sự kiện thử có kiểm soát được ghi nhận đúng nơi và có đầu mối nhận cảnh báo. Thực hiện restore một đối tượng đại diện theo quy trình của môi trường, rồi kiểm tra dữ liệu và ứng dụng.

Bài thử lỗi host hoặc ngắt kết nối chỉ thực hiện trong cửa sổ và phạm vi đã được tổ chức cho phép. Với bài tập thiết kế, có thể mô phỏng bằng dữ liệu capacity và mô tả trình tự phục hồi.

### Bước 5: Ghi kết quả nghiệm thu

Một bản nghiệm thu nên có:

| Bằng chứng | Tiêu chí |
| --- | --- |
| Sơ đồ và inventory | Khớp tài nguyên thực tế hoặc giả định đã công bố |
| Ma trận quyền | Người dùng chỉ thực hiện được nhiệm vụ được giao |
| Bảng tuyến và luồng mạng | Luồng cần thiết hoạt động, luồng cấm bị chặn |
| Sizing | Có phần dự phòng và chỉ rõ giới hạn của phép tính |
| Giám sát | Có dữ liệu, cảnh báo và người xử lý |
| Restore | Dữ liệu dùng được, có thời gian phục hồi đo được |
| Chi phí | Có chủ sở hữu, mô hình dự toán và kỳ cam kết đã kiểm tra |

Nếu đã tạo tài nguyên tạm, kết thúc bài thực hành bằng việc rà soát chúng theo quy trình lifecycle được hỗ trợ. Trước khi xóa, xác nhận dữ liệu cần giữ, phụ thuộc mạng/lưu trữ và điều khoản cam kết; sau đó kiểm tra tài nguyên còn tồn tại và chi phí còn phát sinh.

## 13. Những lỗi thiết kế cần nhận diện

| Nhầm lẫn | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Cấp quyền OCI rồi coi như đã cấp quyền vCenter | Người dùng không thực hiện được tác vụ, hoặc được cấp quá nhiều quyền để chữa lỗi | Thiết kế và thử quyền riêng cho từng phạm vi |
| Tạo workload cluster rồi coi là độc lập hoàn toàn | Đánh giá thấp phụ thuộc quản trị dùng chung | Ghi rõ thành phần chung và phạm vi ảnh hưởng |
| Dùng NSG thay cho mọi chính sách giữa VM | Một số luồng nội bộ không được kiểm soát như dự kiến | Thiết kế chính sách NSX và kiểm thử đúng luồng |
| Chỉ kiểm tra route đi | Kết nối thất bại hoặc hoạt động không ổn định | Theo dõi đường về của CIDR overlay |
| Dùng raw capacity để chốt dung lượng ứng dụng | Thiếu chỗ cho bảo vệ dữ liệu và phục hồi | Tính policy, khoảng trống và kịch bản lỗi |
| Chỉ tính tải lúc đủ host | Không đủ tài nguyên khi bảo trì hoặc có lỗi | Tính trạng thái thiếu host và kiểm tra admission control |
| Coi snapshot, HA và backup là tương đương | Thiếu khả năng khôi phục dữ liệu khi cần | Chọn cơ chế theo loại sự cố và thử restore |
| Coi tắt VM hoặc xóa host là kết thúc mọi chi phí | Dự toán sai chi phí nền tảng và cam kết | Kiểm tra tài nguyên được tính phí và điều khoản kỳ sử dụng |

Một phương án OCVS có thể triển khai được cần thể hiện rõ nơi workload chạy, cách dữ liệu đi qua các lớp mạng, người có quyền thay đổi hệ thống và bằng chứng cho khả năng phục hồi. Các quyết định đó phải được duy trì khi thêm cluster, mở rộng host, thay storage hoặc di chuyển thêm ứng dụng.
