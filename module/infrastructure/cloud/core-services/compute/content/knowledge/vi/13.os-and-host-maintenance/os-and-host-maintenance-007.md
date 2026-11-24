# Theo dõi vòng đời hệ điều hành, kernel và phần mềm hỗ trợ

Máy ảo có thể chạy ổn định trong nhiều năm, nhưng hệ điều hành, kernel, thư viện, driver và agent bên trong máy luôn có vòng đời riêng. Một phiên bản Linux hoặc Windows Server có thể hết hỗ trợ bảo mật; kernel mới có thể không tương thích với driver cũ; agent backup hoặc giám sát có thể ngừng hỗ trợ một bản phân phối. Nếu chỉ theo dõi trạng thái VM mà không theo dõi các thành phần này, tổ chức có thể duy trì một workload đang chạy nhưng không còn được vá lỗi hoặc không còn được nhà cung cấp hỗ trợ.

**Quản lý vòng đời hệ điều hành và phần mềm hỗ trợ** là quá trình xác định phiên bản đang sử dụng, theo dõi mốc hỗ trợ, đánh giá tương thích, lập kế hoạch cập nhật hoặc nâng cấp, kiểm thử và thay thế những thành phần đã lỗi thời. Công việc này áp dụng cho máy ảo, máy bare metal, node container và các image dùng để tạo máy mới.

Trong module **CLOUD_CORE_SERVICES_COMPUTE**, bài học tập trung vào việc theo dõi vòng đời OS, kernel và phần mềm hỗ trợ để duy trì bảo mật, khả năng tương thích và tính sẵn sàng của hạ tầng tính toán. Nội dung bao gồm các mốc EOL/EOS, LTS, kernel, driver, runtime, agent, inventory, patch management, live patching, reboot, image lifecycle và kế hoạch nâng cấp.

## 1. Vì sao phải quản lý vòng đời?

Một hệ thống cloud không chỉ gồm CPU, RAM, storage và network. Mỗi VM còn có một chuỗi phụ thuộc phần mềm:

- Hệ điều hành và phiên bản phát hành.
- Kernel và các module kernel.
- Firmware, driver và guest tools.
- Thư viện hệ thống, package và runtime ứng dụng.
- Agent giám sát, backup, bảo mật, quản trị và cập nhật.
- Ứng dụng, framework và database engine.

Các thành phần này được phát hành, vá lỗi và ngừng hỗ trợ theo lịch khác nhau. Ví dụ, một bản Windows Server vẫn còn trong thời gian hỗ trợ nhưng phiên bản .NET hoặc agent backup cài trên đó có thể đã hết hỗ trợ. Ngược lại, một ứng dụng vẫn tương thích với distro nhưng kernel đang chạy có thể thiếu bản vá bảo mật quan trọng.

Quản lý vòng đời có các mục tiêu:

1. Biết chính xác máy đang chạy OS, kernel, package và agent phiên bản nào.
2. Phát hiện phiên bản sắp hết hỗ trợ trước khi trở thành rủi ro.
3. Duy trì bản vá bảo mật và sửa lỗi theo mức độ ưu tiên.
4. Đảm bảo driver, agent và ứng dụng tương thích với OS mục tiêu.
5. Lên lịch reboot hoặc thay thế máy có kiểm soát.
6. Chuẩn hóa image để máy mới không khởi chạy từ nền tảng lỗi thời.
7. Giảm thời gian xử lý sự cố và chi phí nâng cấp khẩn cấp.

Một máy vẫn trả lời ping hoặc phục vụ request không chứng minh rằng hệ điều hành còn được hỗ trợ. Trạng thái vận hành và trạng thái vòng đời phải được theo dõi riêng.

## 2. Các mốc vòng đời cần phân biệt

Nhà cung cấp dùng nhiều thuật ngữ cho các giai đoạn hỗ trợ. Tên gọi và chính sách chính xác khác nhau theo sản phẩm, edition và kênh phát hành.

| Thuật ngữ | Ý nghĩa thường gặp | Việc cần làm |
|---|---|---|
| Release / General Availability | Phiên bản được phát hành rộng rãi | Đánh giá tương thích và thời điểm đưa vào tiêu chuẩn |
| Mainstream support | Giai đoạn hỗ trợ chính, thường gồm cập nhật bảo mật và sửa lỗi theo chính sách | Duy trì trên phiên bản được hỗ trợ và theo dõi mốc kết thúc |
| Extended support | Giai đoạn hỗ trợ mở rộng, phạm vi cập nhật có thể hẹp hơn hoặc có điều kiện | Xác nhận quyền lợi, chi phí và kế hoạch migration |
| End of maintenance / End of updates | Nhà cung cấp ngừng phát hành cập nhật bảo trì hoặc bản vá theo kênh đó | Chuyển sang kênh hỗ trợ khác hoặc nâng cấp |
| End of life (EOL) | Phiên bản kết thúc vòng đời theo định nghĩa của nhà cung cấp | Di chuyển khỏi phiên bản, trừ khi có ngoại lệ được kiểm soát |
| End of support (EOS) | Nhà cung cấp ngừng hỗ trợ theo chính sách đã công bố | Không tiếp tục coi đây là nền tảng tiêu chuẩn cho workload mới |

Không nên mặc định EOL, EOS, end of maintenance và end of standard support luôn là cùng một ngày. Hãy tra cứu vòng đời chính thức của đúng sản phẩm, edition, release và subscription đang sử dụng.

### 2.1. LTS và chu kỳ phát hành

LTS (Long-Term Support) là nhãn thường dùng cho bản phát hành có thời gian hỗ trợ dài hơn một số bản phát hành thông thường. Ubuntu có các bản LTS; một số sản phẩm doanh nghiệp như RHEL và SLES có vòng đời phát hành và hỗ trợ được công bố riêng. Windows Server cũng có mốc hỗ trợ theo từng phiên bản và edition.

LTS không có nghĩa là mọi package trong hệ thống sẽ được hỗ trợ vô thời hạn. Một package có thể có vòng đời riêng, nằm ngoài phạm vi hỗ trợ của distro hoặc cần subscription bổ sung. Cần kiểm tra:

- Thời hạn hỗ trợ tiêu chuẩn của bản phát hành.
- Điều kiện hỗ trợ mở rộng hoặc Extended Security Maintenance nếu có.
- Repository hoặc kênh cập nhật mà máy đang sử dụng.
- Package nào thuộc phạm vi hỗ trợ và package nào do bên thứ ba cung cấp.
- Phiên bản ứng dụng có được nhà cung cấp chứng nhận trên bản LTS đó không.

### 2.2. Phiên bản và nhánh hỗ trợ

Một hệ điều hành có thể có nhiều nhánh cùng tồn tại, chẳng hạn bản ổn định, bản LTS, bản cập nhật bảo trì và bản phát hành mới. Cần ghi rõ phiên bản đầy đủ và kênh phát hành, không chỉ ghi “Linux” hoặc “Windows”.

Ví dụ, thông tin “Ubuntu Server” chưa đủ để biết máy đang chạy bản LTS nào; “Windows Server” chưa cho biết release, edition và build. Khi lập kế hoạch, hãy ghi nhận product name, release, build hoặc version, kiến trúc CPU và kênh hỗ trợ.

## 3. Vòng đời của kernel

Kernel là thành phần lõi quản lý tiến trình, bộ nhớ, thiết bị, filesystem và network stack. Kernel có thể nhận bản vá bảo mật, sửa lỗi, hỗ trợ phần cứng mới và thay đổi hành vi hệ thống. Vì vậy, theo dõi phiên bản kernel là phần quan trọng trong bảo trì host.

### 3.1. Kernel version không phải toàn bộ trạng thái hỗ trợ

Trên Linux, lệnh uname -r cho biết phiên bản kernel đang chạy. Tuy nhiên, số phiên bản này không đủ để xác định máy đã nhận mọi bản vá bảo mật hay chưa. Một distro có thể backport bản sửa lỗi vào kernel package mà không thay đổi số phiên bản upstream theo cách người dùng mong đợi.

Ví dụ, kernel của distro doanh nghiệp có thể giữ nhánh version ổn định trong khi nhà cung cấp backport các bản sửa lỗi đã được kiểm thử. Do đó, cần kiểm tra package release, advisory của nhà cung cấp và trạng thái cập nhật, không chỉ so sánh số kernel với phiên bản mới nhất trên kernel.org.

Trên Windows, kernel được phát hành cùng các bản cập nhật hệ điều hành và build. Cần theo dõi OS build, cumulative update và trạng thái servicing của phiên bản Windows Server.

### 3.2. Kernel package và kernel đang chạy

Sau khi cài bản cập nhật kernel, máy có thể đã có kernel mới trên đĩa nhưng vẫn đang chạy kernel cũ cho đến khi reboot. Đây là khác biệt quan trọng:

- **Installed kernel:** package kernel đã được cài trên filesystem.
- **Running kernel:** kernel hiện đang điều khiển hệ thống.
- **Boot default:** kernel mà bootloader dự kiến nạp ở lần khởi động tiếp theo.

Nếu chỉ kiểm tra package đã cài mà không kiểm tra kernel đang chạy, đội vận hành có thể tưởng rằng bản vá đã có hiệu lực trong khi máy chưa reboot.

### 3.3. Module kernel và driver

Driver thiết bị, filesystem module, network module và security module có thể phụ thuộc vào phiên bản kernel hoặc ABI của distro. Driver ngoài cây nguồn (out-of-tree driver) như một số module GPU, storage hoặc agent bảo mật có thể cần build lại khi kernel thay đổi.

Trước khi cập nhật kernel, cần kiểm tra:

- Driver có hỗ trợ kernel mục tiêu không?
- Secure Boot có yêu cầu ký module không?
- DKMS hoặc cơ chế build module có hoạt động không?
- Agent bảo mật hoặc backup có module kernel riêng không?
- Thiết bị passthrough, GPU, NIC tăng tốc hoặc storage controller có tương thích không?
- Có kernel dự phòng để rollback nếu kernel mới không khởi động được không?

Không nên nâng kernel trên một nhóm host có GPU hoặc storage driver đặc biệt mà chưa kiểm thử trên máy đại diện.

## 4. Vòng đời của package, runtime và agent

OS có thể còn được hỗ trợ trong khi một phần mềm chạy bên trên đã cũ. Mỗi thành phần cần có phiên bản, nguồn phát hành và lịch hỗ trợ riêng.

| Thành phần | Ví dụ | Rủi ro khi lỗi thời |
|---|---|---|
| System libraries | glibc, OpenSSL, systemd | Lỗ hổng bảo mật, ứng dụng không tương thích |
| Language runtime | Java, .NET, Node.js, Python | Runtime hết hỗ trợ, thiếu bản vá, package không cài được |
| Web/database engine | NGINX, Apache, PostgreSQL, SQL Server | Lỗ hổng, lỗi dữ liệu hoặc không còn hỗ trợ |
| Container runtime | containerd, CRI-O, Docker Engine | Lỗi runtime, không tương thích kernel hoặc orchestrator |
| Guest tools | Cloud guest agent, VM tools | Mất chức năng quản trị, network hoặc storage |
| Monitoring agent | Metrics/logging agent | Không thu thập được metric hoặc log, agent gây tải |
| Backup agent | Snapshot/file backup agent | Backup thất bại hoặc không phục hồi được |
| Security agent | EDR, vulnerability scanner | Không nhận bản vá hoặc không hỗ trợ kernel mới |
| Database connector | ODBC/JDBC driver | Kết nối lỗi hoặc thay đổi hành vi |

### 4.1. Nguồn package và repository

Package manager cài phần mềm từ repository được cấu hình. Nếu máy dùng repository không còn hỗ trợ, mirror không đáng tin cậy hoặc nguồn package trộn lẫn giữa nhiều distro, quá trình cập nhật có thể thất bại hoặc cài phiên bản không tương thích.

Hãy quản lý:

- Danh sách repository được phép.
- GPG signature hoặc cơ chế xác minh package tương ứng.
- Kênh stable, LTS, security hoặc vendor-specific.
- Phiên bản package được pin và lý do pin.
- Package đến từ nhà cung cấp OS hay bên thứ ba.
- Quy trình gỡ bỏ repository cũ và khóa hết hạn.

Pin version có thể cần để giữ tương thích, nhưng không nên trở thành cách trì hoãn bản vá vô thời hạn. Mọi ngoại lệ pin cần có owner, lý do, ngày xem xét lại và phương án thoát.

### 4.2. Tương thích runtime và ứng dụng

Nâng OS có thể làm thay đổi thư viện hệ thống, TLS defaults, compiler runtime, filesystem behavior hoặc quyền mặc định. Ứng dụng cũ có thể phụ thuộc vào một thư viện đã bị loại bỏ hoặc một giao thức không còn được bật.

Trước khi nâng cấp, kiểm tra ma trận hỗ trợ của nhà cung cấp ứng dụng:

- Phiên bản OS và kiến trúc được chứng nhận.
- Phiên bản kernel và thư viện nền.
- Phiên bản Java/.NET/Node.js/Python hoặc runtime khác.
- Database engine và driver kết nối.
- Agent bảo mật, backup, giám sát và công cụ triển khai.
- Cấu hình TLS, cipher, certificate và authentication.

Không chỉ kiểm tra ứng dụng khởi động. Cần chạy test nghiệp vụ, tải đại diện, backup/restore và quy trình vận hành.

## 5. Firmware, guest tools và phần mềm hỗ trợ cloud

VM trên cloud dùng thiết bị ảo, driver paravirtualized và agent tích hợp để tương tác với nền tảng. Một số chức năng như network throughput cao, block storage, shutdown notification, time synchronization, serial console hoặc quản trị từ xa phụ thuộc vào driver và guest agent.

Các thành phần cần theo dõi:

- Guest agent hoặc cloud-init/Windows bootstrap agent.
- Driver NIC và storage.
- Agent quản lý cấu hình hoặc patch management.
- Agent giám sát và thu thập log.
- Agent backup và snapshot consistency.
- Agent bảo mật và vulnerability scanning.
- Firmware hoặc microcode được nhà cung cấp quản lý ở lớp host.

Trong mô hình cloud, nhà cung cấp thường chịu trách nhiệm firmware và hypervisor của host vật lý, nhưng khách hàng vẫn chịu trách nhiệm guest OS và phần mềm cài bên trong VM theo mô hình shared responsibility. Ranh giới cụ thể phụ thuộc dịch vụ IaaS, PaaS hoặc compute được quản lý.

Không nên cài driver từ nguồn không rõ ràng hoặc tải guest agent từ website không được nhà cung cấp chỉ định. Hãy dùng repository hoặc image chính thức và xác minh tính tương thích với OS release.

## 6. Xây dựng inventory vòng đời

Muốn quản lý vòng đời, trước hết phải biết có những máy nào và chúng đang chạy gì. Inventory cần bao gồm VM đang chạy, VM dừng, template, golden image, node container, máy bare metal và workload có OS do tổ chức quản lý.

Thông tin tối thiểu nên ghi:

| Trường | Nội dung |
|---|---|
| Asset ID | ID VM, instance, host hoặc node |
| Owner | Nhóm chịu trách nhiệm kỹ thuật |
| Application | Ứng dụng hoặc dịch vụ sử dụng máy |
| Environment | Development, staging, production |
| OS product | Tên hệ điều hành và distro |
| OS version/build | Release, edition, build và kiến trúc |
| Kernel | Kernel đang chạy và package kernel đã cài |
| Image ID | Image nguồn và phiên bản build |
| Runtime | Java/.NET/Node.js/Python hoặc runtime liên quan |
| Agents | Monitoring, backup, security, guest tools |
| Support date | Mốc hỗ trợ chính, mở rộng và EOL |
| Patch state | Ngày cập nhật gần nhất và bản vá còn thiếu |
| Maintenance window | Khung thời gian được phép bảo trì |
| Criticality | Mức độ quan trọng và SLO/RTO/RPO liên quan |

Inventory có thể lấy từ cloud API, Systems Manager, Azure Arc, OS configuration management, endpoint management hoặc công cụ CMDB. Cần đồng bộ định kỳ và phát hiện máy không còn báo cáo.

### 6.1. Không chỉ quét máy đang bật

Image cũ trong catalog, snapshot, template và autoscaling launch configuration cũng có thể tạo ra VM lỗi thời trong tương lai. Vì vậy, inventory phải bao gồm cả nguồn tạo máy, không chỉ các instance hiện hữu.

Ví dụ, fleet production đã được vá nhưng launch template vẫn trỏ tới image cũ. Khi scale-out hoặc khôi phục sau sự cố, máy mới có thể khởi chạy từ image chưa vá. Quy trình quản lý vòng đời phải cập nhật image và cấu hình triển khai cùng lúc.

### 6.2. Phát hiện máy không được quản lý

Một VM không có owner, không có agent hoặc không gửi inventory là rủi ro vì tổ chức không biết trạng thái hỗ trợ của nó. Nên tạo cảnh báo cho:

- Máy không báo cáo inventory quá thời hạn.
- OS hoặc agent không xác định được version.
- Máy không có owner hoặc application tag.
- Máy chạy OS ngoài danh sách được phê duyệt.
- Image không có build date hoặc source.
- Máy production không có maintenance window.

## 7. Theo dõi mốc hỗ trợ và ưu tiên nâng cấp

Không phải mọi máy hết hỗ trợ đều có cùng mức rủi ro. Một VM public-facing chứa dữ liệu nhạy cảm cần xử lý nhanh hơn một máy lab cô lập không có dữ liệu quan trọng. Tuy nhiên, hệ thống hết hỗ trợ vẫn cần owner và kế hoạch xử lý rõ ràng.

Có thể phân loại:

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| Supported | Đang trong thời gian hỗ trợ tiêu chuẩn | Duy trì bản vá và review định kỳ |
| Extended support | Còn hỗ trợ mở rộng hoặc kênh cập nhật có điều kiện | Xác nhận quyền lợi, chi phí và kế hoạch nâng cấp |
| Near EOL | Sắp đến mốc kết thúc hỗ trợ | Kiểm thử phiên bản thay thế và lập lịch migration |
| Unsupported | Đã hết hỗ trợ hoặc không còn bản vá tiêu chuẩn | Ưu tiên cô lập, nâng cấp hoặc thay thế |
| Exception | Chưa thể nâng cấp vì phụ thuộc kỹ thuật/nghiệp vụ | Ghi nhận owner, kiểm soát bù trừ và hạn chót |

### 7.1. Xếp hạng rủi ro

Đánh giá rủi ro nên xem xét:

- Thời gian còn lại trước EOL/EOS.
- Mức độ nghiêm trọng của lỗ hổng chưa vá.
- Khả năng khai thác từ mạng và mức phơi bày Internet.
- Độ nhạy cảm của dữ liệu.
- Mức độ quan trọng của workload.
- Khả năng tương thích của ứng dụng và agent.
- Khả năng backup, rollback và phục hồi.

Không nên chỉ xếp ưu tiên theo ngày EOL. Một lỗ hổng đang bị khai thác trên OS còn hỗ trợ có thể cần xử lý trước một máy sắp EOL nhưng đã được cô lập và không chứa dữ liệu quan trọng.

### 7.2. Ngoại lệ vòng đời

Đôi khi ứng dụng legacy không thể nâng OS ngay vì phụ thuộc driver, runtime hoặc chứng nhận nhà cung cấp. Ngoại lệ cần:

- Owner nghiệp vụ và kỹ thuật.
- Lý do cụ thể không thể nâng cấp.
- Thời hạn ngoại lệ và ngày xem xét lại.
- Phạm vi mạng được giới hạn.
- Quyền truy cập và danh tính được thu hẹp.
- Giám sát tăng cường và backup đã kiểm thử.
- Kế hoạch thay thế hoặc hiện đại hóa.

Ngoại lệ không nên trở thành trạng thái vĩnh viễn không có ngày kết thúc.

## 8. Quản lý bản vá hệ điều hành

Patch management là quy trình thu thập, đánh giá, kiểm thử, triển khai và xác minh bản cập nhật. Bản vá có thể sửa lỗ hổng bảo mật, lỗi ổn định, lỗi driver hoặc vấn đề tương thích.

Một quy trình cơ bản:

1. Thu thập advisory và danh sách bản vá.
2. Xác định máy, package và workload bị ảnh hưởng.
3. Ưu tiên theo mức độ nghiêm trọng, khả năng khai thác và mức phơi bày.
4. Kiểm thử trong môi trường đại diện.
5. Tạo backup hoặc điểm phục hồi phù hợp.
6. Triển khai theo nhóm/ring.
7. Reboot nếu cần để bản vá có hiệu lực.
8. Xác minh package, kernel, service và ứng dụng.
9. Ghi nhận máy thất bại và xử lý ngoại lệ.

### 8.1. Security patch và feature update

Security patch thường cần được ưu tiên theo rủi ro. Feature update có thể thay đổi hành vi, API hoặc cấu hình và cần quy trình kiểm thử rộng hơn. Không nên gom mọi loại cập nhật vào một đợt mà không phân biệt tác động.

Với hệ thống production, có thể dùng ring:

- Ring 0: máy thử nghiệm nội bộ.
- Ring 1: development và staging.
- Ring 2: một nhóm nhỏ production có thể phục hồi nhanh.
- Ring 3: phần còn lại của production.

Nếu phát hiện lỗi ở ring đầu, tạm dừng rollout để điều tra. Không tự động tiếp tục chỉ vì lịch bảo trì đã đến.

### 8.2. Cập nhật tự động và kiểm soát

Tự động cập nhật giúp giảm thời gian tồn tại của lỗ hổng, nhưng cập nhật không kiểm soát có thể gây reboot ngoài lịch hoặc thay đổi phiên bản ngoài dự kiến. Với máy production, nên dùng patch management có maintenance window, phê duyệt theo mức độ rủi ro và báo cáo kết quả.

Máy có thể được cập nhật theo chính sách tự động nếu:

- Mức độ quan trọng và khả năng phục hồi đã được xác định.
- Bản cập nhật được lấy từ nguồn tin cậy.
- Có maintenance window phù hợp.
- Ứng dụng hỗ trợ restart hoặc failover.
- Có giám sát sau cập nhật và quy trình xử lý lỗi.

## 9. Live kernel patching và yêu cầu reboot

Một số distro Linux và nền tảng hỗ trợ live kernel patching: áp dụng một số bản sửa lỗi kernel lên kernel đang chạy mà không cần reboot ngay. Công nghệ này hữu ích để giảm thời gian gián đoạn, nhưng không áp dụng cho mọi loại thay đổi.

Ví dụ công nghệ có thể gặp:

- Canonical Livepatch trên Ubuntu trong phạm vi phiên bản và điều kiện được hỗ trợ.
- kpatch hoặc cơ chế live patch của hệ sinh thái RHEL.
- SUSE kgraft/live patching theo phiên bản và subscription.
- Một số dịch vụ cloud hoặc nền tảng quản trị cung cấp orchestration cho kernel patch.

### 9.1. Giới hạn của live patch

Live patch chỉ xử lý các bản vá được nhà cung cấp xây dựng và hỗ trợ cho cơ chế đó. Nó không thay thế mọi kernel update, driver update, firmware update hoặc feature change. Một số thay đổi vẫn cần reboot để:

- Nạp kernel mới đầy đủ.
- Cập nhật module hoặc driver không thể thay nóng.
- Áp dụng firmware hoặc microcode cần chu kỳ khởi động.
- Hoàn tất cập nhật thư viện hệ thống hoặc thành phần user space.
- Đưa máy về trạng thái được nhà cung cấp hỗ trợ.

Do đó, cần theo dõi riêng trạng thái live patch và trạng thái reboot-required. Máy đã áp dụng live patch vẫn có thể cần reboot trong maintenance window kế tiếp.

### 9.2. Xác định reboot có cần thiết không

Trên Linux, tùy distro có thể dùng công cụ như needs-restarting -r (nếu gói hỗ trợ), kiểm tra file /var/run/reboot-required trên Ubuntu/Debian hoặc kiểm tra trạng thái từ patch management agent. Không có một lệnh duy nhất hoạt động giống nhau trên mọi distro.

Trên Windows Server, một số bản cập nhật yêu cầu restart để hoàn tất. Có thể kiểm tra trạng thái pending reboot qua công cụ quản trị endpoint/patch management hoặc các dấu hiệu hệ thống như Component Based Servicing và Windows Update. Script kiểm tra registry cần được duy trì theo tài liệu Microsoft và không nên dựa vào một khóa duy nhất như bằng chứng tuyệt đối.

### 9.3. Lập lịch reboot

Reboot cần phối hợp với:

- Load balancer và khả năng drain traffic.
- Cluster, replication và quorum.
- Database failover hoặc thứ tự dừng dịch vụ.
- Batch job và checkpoint.
- Maintenance window và thông báo cho owner.
- Backup/restore và kiểm tra sau reboot.

Nếu có nhiều node, reboot tuần tự hoặc rolling reboot để giữ đủ capacity. Với cluster stateful, phải tuân theo quy trình của database hoặc hệ thống phân tán; không tự reboot nhiều node cùng lúc nếu điều đó có thể làm mất quorum.

## 10. Nâng cấp OS: in-place hay thay thế máy?

Khi một phiên bản sắp hết hỗ trợ, có hai hướng chính.

### 10.1. In-place upgrade

In-place upgrade nâng cấp OS ngay trên máy hiện tại. Cách này có thể giữ lại cấu hình và dữ liệu cục bộ, giảm công việc tái tạo hạ tầng. Tuy nhiên, nâng cấp có thể bị chặn bởi package cũ, repository bên thứ ba, driver, bootloader hoặc ứng dụng không tương thích.

Trước khi thực hiện:

- Xác minh đường nâng cấp được nhà cung cấp hỗ trợ.
- Kiểm tra dung lượng đĩa, filesystem và package.
- Kiểm thử trên bản clone hoặc môi trường staging.
- Sao lưu dữ liệu và cấu hình.
- Kiểm tra driver, agent, runtime và ứng dụng.
- Chuẩn bị console hoặc phương án cứu hộ nếu máy không boot.
- Định nghĩa tiêu chí rollback và thời gian gián đoạn.

Không phải mọi bản phát hành đều hỗ trợ nâng cấp trực tiếp từ mọi phiên bản cũ. Có thể cần nâng qua một release trung gian hoặc triển khai máy mới.

### 10.2. Immutable image và replace instance

Với immutable infrastructure, thay vì sửa OS lâu năm tại chỗ, nhóm xây dựng image mới đã vá và kiểm thử, sau đó tạo VM mới rồi chuyển traffic hoặc workload sang máy mới. Máy cũ được loại bỏ sau khi xác nhận máy mới hoạt động.

Ưu điểm:

- Môi trường mới được tạo từ image có phiên bản rõ ràng.
- Giảm drift tích lũy qua nhiều năm sửa thủ công.
- Có thể dùng rolling replacement hoặc blue/green.
- Rollback có thể đơn giản hơn nếu image và dữ liệu được tách đúng.

Điều kiện cần:

- Dữ liệu quan trọng nằm trên storage bền vững hoặc được replication.
- Cấu hình và secret được cấp ngoài image.
- Ứng dụng có thể chạy nhiều phiên bản trong giai đoạn chuyển đổi.
- Có capacity đủ để chạy máy cũ và mới đồng thời.
- Load balancer, DNS hoặc scheduler hỗ trợ chuyển workload.

### 10.3. Chọn chiến lược

| Tiêu chí | In-place upgrade | Replace instance/image |
|---|---|---|
| Giữ máy hiện tại | Có | Không, tạo máy mới |
| Nguy cơ cấu hình cũ | Có thể tiếp tục tồn tại | Có thể loại bỏ bằng image chuẩn |
| Yêu cầu capacity tạm thời | Thường thấp hơn | Có thể cần chạy song song |
| Rollback | Có thể phức tạp nếu nâng cấp thay đổi dữ liệu | Thường dựa trên chuyển traffic về bản cũ nếu dữ liệu tương thích |
| Phù hợp | Máy stateful hoặc khó tái tạo, đường nâng cấp được hỗ trợ | Fleet stateless, autoscaling, image pipeline trưởng thành |

Không có chiến lược duy nhất phù hợp mọi máy. Cần xem dữ liệu, mức downtime, khả năng tái tạo, hỗ trợ của ứng dụng và yêu cầu vận hành.

## 11. Quản lý vòng đời machine image

Image là nguồn tạo VM. Nếu image cũ vẫn được giữ trong catalog hoặc launch template, tổ chức có thể vô tình tạo máy mới từ OS đã lỗi thời.

Một quy trình image lifecycle:

1. Chọn image nền chính thức và còn hỗ trợ.
2. Cài bản vá OS, kernel và package nền.
3. Cài phiên bản agent đã được phê duyệt.
4. Áp dụng baseline bảo mật và cấu hình logging.
5. Quét lỗ hổng và kiểm tra tương thích.
6. Gắn version/build ID và ghi nhận package manifest.
7. Phát hành image mới.
8. Cập nhật launch template, autoscaling group và pipeline.
9. Đánh dấu image cũ deprecated.
10. Xóa hoặc hạn chế sử dụng image cũ theo retention policy.

### 11.1. Golden image không được chứa bí mật

Không đưa private key, password, token hoặc credential cá nhân vào image. Mỗi instance cần danh tính riêng và nhận secret khi chạy qua secret manager hoặc cơ chế identity được hỗ trợ.

Trước khi capture image, cần làm sạch machine ID, host key, log tạm, cache package nhạy cảm và dữ liệu riêng của máy nguồn theo hướng dẫn của OS và cloud provider. Nếu nhân bản định danh máy, hệ thống quản trị có thể nhận nhầm nhiều máy là cùng một asset.

### 11.2. Image version và deprecation

Image nên có version hoặc build identifier bất biến. Ghi nhận:

- OS release và kernel package.
- Ngày build và nguồn image.
- Danh sách package/agent cùng version.
- Baseline bảo mật được áp dụng.
- Kết quả kiểm thử và scan.
- Ngày hết hạn hoặc ngày review.

Khi phát hành image mới, cần tìm mọi launch template, autoscaling policy và pipeline còn tham chiếu image cũ. Đánh dấu image deprecated không tự động bảo đảm mọi cấu hình triển khai đã ngừng dùng nó.

## 12. Theo dõi vòng đời agent và driver

Agent có thể tạo ra rủi ro tương tự OS cũ. Một agent bảo mật không còn hỗ trợ kernel mới có thể làm máy không khởi động hoặc mất bảo vệ. Agent backup lỗi thời có thể báo thành công nhưng không khôi phục được dữ liệu.

Đối với mỗi agent, cần ghi:

- Tên nhà cung cấp và sản phẩm.
- Phiên bản cài đặt.
- OS release và kernel được hỗ trợ.
- Phiên bản mới nhất được tổ chức phê duyệt.
- Mốc end of support.
- Cách cập nhật và restart service.
- Tài nguyên CPU/RAM/network agent tiêu thụ.
- Trạng thái heartbeat và lần gửi dữ liệu gần nhất.

Khi nâng OS, cần nâng cấp agent theo thứ tự tương thích. Có trường hợp phải cập nhật agent trước OS; trường hợp khác cần OS mới trước khi agent phiên bản mới có thể cài. Hãy theo ma trận tương thích của nhà cung cấp thay vì suy đoán.

### 12.1. Driver và thiết bị tăng tốc

GPU, NIC tăng tốc, storage controller và thiết bị passthrough có thể yêu cầu driver đặc biệt. Với workload compute hiệu năng cao, cần quản lý đồng bộ:

- OS image.
- Kernel.
- Driver GPU/NIC/storage.
- CUDA hoặc thư viện tăng tốc nếu dùng GPU.
- Container runtime và device plugin.
- Phiên bản ứng dụng hoặc framework.

Nâng riêng một thành phần có thể phá vỡ chuỗi tương thích. Hãy kiểm thử cả tổ hợp phiên bản trên một nhóm host đại diện.

## 13. Ví dụ kiểm kê và kiểm tra Linux

Các lệnh sau giúp thu thập một phần thông tin OS và kernel. Kết quả cần được đưa vào inventory hoặc hệ thống quản lý cấu hình thay vì chỉ xem thủ công.

~~~bash
# Xác định distro và phiên bản
cat /etc/os-release

# Xem kernel đang chạy
uname -r

# Xem kiến trúc CPU
uname -m

# Xem thời gian máy đã khởi động
uptime

# Ubuntu/Debian: xem package kernel đã cài
dpkg-query -W 'linux-image*' 2>/dev/null

# Debian/Ubuntu: kiểm tra dấu hiệu cần reboot nếu file này tồn tại
if [ -f /var/run/reboot-required ]; then
  cat /var/run/reboot-required
fi

# RHEL-like: xem package kernel đã cài
rpm -q kernel

# RHEL-like: xem advisory bảo mật khả dụng
sudo dnf updateinfo list --security
~~~

Các lệnh package phụ thuộc distro. Một hệ thống có thể dùng kernel package đã được backport; hãy đối chiếu advisory và trạng thái cập nhật của nhà cung cấp. uname -r chỉ hiển thị kernel đang chạy, không chứng minh mọi bản vá đã được cài.

### 13.1. Kiểm tra service và agent

~~~bash
# Liệt kê service đang chạy
systemctl --type=service --state=running

# Xem phiên bản một agent, nếu chương trình hỗ trợ
/opt/vendor-agent/bin/agent --version

# Xem trạng thái agent
systemctl status vendor-agent

# Xem log gần đây của agent
journalctl -u vendor-agent --since "24 hours ago"
~~~

Đường dẫn và tên service trong ví dụ cần thay bằng tên thực tế của sản phẩm đã cài. Không nên chạy lệnh restart agent hàng loạt nếu chưa biết tác động đến workload.

## 14. Ví dụ kiểm tra Windows Server

PowerShell có thể thu thập thông tin OS, build và các bản cập nhật đã cài:

~~~powershell
# Tên sản phẩm, version và build
Get-ComputerInfo |
  Select-Object WindowsProductName, WindowsVersion, OsBuildNumber, OsArchitecture

# Thông tin hệ điều hành từ CIM
Get-CimInstance Win32_OperatingSystem |
  Select-Object Caption, Version, BuildNumber, LastBootUpTime

# Các hotfix đã cài gần đây
Get-HotFix |
  Sort-Object InstalledOn -Descending |
  Select-Object -First 20 HotFixID, InstalledOn, Description

# Liệt kê service agent theo tên
Get-Service |
  Where-Object { $_.Name -match "agent|backup|monitor|security" } |
  Select-Object Name, Status, StartType
~~~

Get-HotFix không phải danh sách đầy đủ mọi thành phần đã được servicing; cần kết hợp công cụ quản lý cập nhật và báo cáo của Windows Update/endpoint management. Tên service có thể không chứa các từ khóa ví dụ, vì vậy inventory production nên dùng danh sách agent được quản lý rõ ràng.

## 15. Lập lịch bảo trì cho fleet

Fleet có thể gồm hàng trăm hoặc hàng nghìn VM. Cập nhật từng máy thủ công khó kiểm soát và dễ bỏ sót. Nên phân nhóm theo ứng dụng, môi trường, criticality, OS và maintenance window.

### 15.1. Phân nhóm theo vai trò

Ví dụ:

- Nhóm web stateless: có thể rolling replace qua load balancer.
- Nhóm worker: dừng nhận job, hoàn tất hoặc checkpoint rồi cập nhật.
- Nhóm database: tuân theo thứ tự failover, replication và quy trình của engine.
- Nhóm GPU: kiểm thử driver và framework trên image mới.
- Nhóm legacy: có maintenance window riêng và owner phê duyệt.

### 15.2. Rolling maintenance

Với cluster nhiều node, cập nhật từng node hoặc một nhóm nhỏ:

1. Kiểm tra cluster đang khỏe và đủ capacity.
2. Chọn node có thể bảo trì.
3. Drain workload và chuyển traffic.
4. Cập nhật OS/agent/driver.
5. Reboot nếu cần.
6. Kiểm tra node, ứng dụng và metric.
7. Đưa node trở lại cluster.
8. Chuyển sang node tiếp theo.

Không cập nhật đồng thời quá nhiều node đến mức làm mất quorum hoặc capacity tối thiểu. Với hệ thống stateful, tuân theo hướng dẫn của database và nền tảng cluster.

### 15.3. Maintenance window và thông báo

Maintenance window cần ghi:

- Thời gian bắt đầu/kết thúc và timezone.
- Workload và asset nằm trong phạm vi.
- Người phê duyệt và người trực.
- Dự kiến downtime hoặc tác động.
- Điều kiện dừng rollout.
- Kế hoạch rollback/restore.
- Bài kiểm tra sau bảo trì.

Không nên lên lịch reboot mà không thông báo cho owner ứng dụng. Một bản vá có thể yêu cầu restart service hoặc thay đổi network stack, ảnh hưởng tới kết nối dài hạn.

## 16. Lập kế hoạch nâng cấp trước EOL

Khi OS sắp hết hỗ trợ, hãy bắt đầu từ inventory và dependency map. Không nên chờ đến tuần cuối cùng mới tìm phiên bản thay thế.

Một lộ trình mẫu:

~~~mermaid
flowchart TD
    A["Inventory OS, kernel, runtime và agent"] --> B["Đối chiếu mốc hỗ trợ chính thức"]
    B --> C["Xác định workload sắp EOL hoặc đã unsupported"]
    C --> D["Kiểm tra ma trận tương thích"]
    D --> E["Chọn in-place upgrade hoặc replace image"]
    E --> F["Xây image / môi trường thử nghiệm"]
    F --> G["Kiểm thử ứng dụng, driver, backup và bảo mật"]
    G --> H{"Đạt tiêu chí?"}
    H -- "Không" --> I["Sửa dependency hoặc lập ngoại lệ có thời hạn"]
    I --> F
    H -- "Có" --> J["Triển khai theo ring / rolling"]
    J --> K["Xác minh và cập nhật inventory"]
    K --> L["Ngừng dùng image và OS cũ"]
~~~

### 16.1. Kiểm thử tương thích

Kiểm thử cần bao gồm:

- Khởi động và shutdown.
- Network, DNS, route và firewall.
- Storage mount, filesystem và I/O.
- Driver GPU/NIC/storage.
- Runtime, thư viện và ứng dụng.
- Danh tính workload và quyền truy cập dịch vụ cloud.
- Monitoring, logging, backup và restore.
- Hiệu năng dưới tải đại diện.
- Failover, reboot và phục hồi sau lỗi.

### 16.2. Kế hoạch rollback

Rollback không phải lúc nào cũng là hạ cấp OS về phiên bản cũ. Sau khi schema database, filesystem hoặc format dữ liệu thay đổi, máy cũ có thể không đọc được dữ liệu mới. Cần xác định:

- Có thể chuyển traffic về instance cũ không?
- Dữ liệu có tương thích giữa phiên bản cũ và mới không?
- Snapshot/backup có thể khôi phục được không?
- Có cần giữ image cũ tạm thời không?
- Khi nào phải dừng rollback và chuyển sang restore?

Với immutable deployment, có thể giữ nhóm máy cũ trong thời gian xác nhận, nhưng cần bảo đảm dữ liệu dùng chung tương thích và không để hai phiên bản ghi dữ liệu theo cách xung đột.

## 17. Trách nhiệm giữa cloud provider và khách hàng

Trong IaaS, cloud provider thường quản lý trung tâm dữ liệu, máy chủ vật lý, firmware, hypervisor và một phần mạng/lưu trữ nền. Khách hàng thường quản lý guest OS, kernel, package, ứng dụng, danh tính, cấu hình mạng khách hàng và dữ liệu.

Với PaaS hoặc dịch vụ compute được quản lý, nhà cung cấp có thể chịu trách nhiệm nhiều hơn cho OS và runtime nền. Tuy nhiên, khách hàng vẫn cần theo dõi phiên bản runtime mà dịch vụ cung cấp, thời hạn deprecation, compatibility notice và yêu cầu nâng cấp ứng dụng.

| Thành phần | IaaS VM | Managed compute/PaaS |
|---|---|---|
| Host vật lý và firmware | Thường do provider quản lý | Do provider quản lý |
| Hypervisor | Do provider quản lý | Do provider quản lý |
| Guest OS | Thường do khách hàng quản lý | Có thể do provider quản lý hoặc trừu tượng hóa |
| Kernel guest | Thường do khách hàng quản lý | Phụ thuộc dịch vụ |
| Runtime nền | Khách hàng cài và vá nếu tự quản lý | Provider có thể quản lý một phần |
| Ứng dụng và dependency | Khách hàng quản lý | Khách hàng vẫn quản lý mã và dependency thuộc phạm vi của mình |
| Dữ liệu và quyền truy cập | Khách hàng chịu trách nhiệm | Khách hàng chịu trách nhiệm |

Luôn kiểm tra mô hình trách nhiệm của dịch vụ cụ thể. Không nên cho rằng “chạy trên cloud” đồng nghĩa nhà cung cấp sẽ tự vá mọi thành phần bên trong VM.

## 18. Chỉ số và báo cáo vòng đời

Một chương trình bảo trì cần số liệu để biết mức độ tuân thủ và rủi ro. Các chỉ số có thể gồm:

| Chỉ số | Cách hiểu |
|---|---|
| OS support coverage | Tỷ lệ asset đang chạy phiên bản còn hỗ trợ |
| EOL exposure | Số lượng máy đã hoặc sắp hết hỗ trợ |
| Patch compliance | Tỷ lệ máy đáp ứng baseline bản vá |
| Reboot pending | Số máy đã cài kernel/update nhưng chưa reboot cần thiết |
| Agent coverage | Tỷ lệ máy có đủ agent bắt buộc và heartbeat hợp lệ |
| Image freshness | Tuổi image và thời gian từ lần build/patch gần nhất |
| Upgrade lead time | Thời gian từ lúc phát hiện EOL đến khi hoàn tất di chuyển |
| Exception aging | Tuổi của các ngoại lệ chưa xử lý |
| Patch failure rate | Tỷ lệ máy cập nhật thất bại |

Không nên tối ưu một metric đơn lẻ. Ví dụ, tỷ lệ patch compliance cao không có nghĩa hệ thống an toàn nếu image cũ vẫn được dùng để tạo máy mới hoặc agent bảo mật không hoạt động.

## 19. Ví dụ thực tế: fleet API sắp hết hỗ trợ OS

Một doanh nghiệp có 60 VM chạy API trên một bản Linux LTS cũ. Hệ điều hành vẫn đang phục vụ request, nhưng thời hạn hỗ trợ tiêu chuẩn sẽ kết thúc trong vài tháng. Fleet còn có agent giám sát, agent bảo mật, driver storage và một runtime Java.

Nhóm vận hành thực hiện:

1. Thu thập OS release, kernel, package và agent version từ toàn bộ 60 VM.
2. Xác nhận ngày kết thúc hỗ trợ và các lựa chọn hỗ trợ mở rộng.
3. Kiểm tra runtime Java, thư viện TLS, agent và driver có hỗ trợ distro LTS mới không.
4. Xây golden image mới với kernel và agent đã được phê duyệt.
5. Chạy integration test, vulnerability scan, backup/restore và tải đại diện.
6. Tạo nhóm canary nhỏ sau load balancer.
7. Quan sát error rate, latency, CPU, memory, disk và log agent.
8. Rolling replace các nhóm VM còn lại.
9. Cập nhật launch template và pipeline để không tạo thêm VM từ image cũ.
10. Đánh dấu image cũ deprecated, theo dõi ngoại lệ và gỡ bỏ sau thời gian retention.

Nếu chỉ nâng cấp 60 VM hiện tại mà quên launch template, lần scale-out tiếp theo có thể tạo máy từ image cũ. Nếu chỉ thay image mà không kiểm tra agent và driver, máy mới có thể khởi động nhưng mất khả năng giám sát hoặc backup. Quản lý vòng đời cần bao phủ cả máy đang chạy và nguồn tạo máy.

## 20. Những sai lầm thường gặp

- **Chỉ theo dõi OS name:** không biết release, build, edition và support channel.
- **Chỉ xem kernel version:** bỏ qua package release và bản vá được backport.
- **Cho rằng LTS được hỗ trợ vô thời hạn:** bỏ qua mốc hỗ trợ và điều kiện subscription.
- **Cài kernel mới nhưng không reboot:** máy vẫn chạy kernel cũ và chưa áp dụng bản vá cần reboot.
- **Nâng kernel không kiểm tra driver:** có thể làm mất network, storage hoặc GPU.
- **Quên agent bên thứ ba:** OS mới có thể không còn tương thích với backup, EDR hoặc monitoring.
- **Chỉ cập nhật VM đang chạy:** image hoặc launch template cũ vẫn tạo ra máy lỗi thời.
- **Reboot toàn fleet cùng lúc:** có thể làm thiếu capacity hoặc mất quorum.
- **Dựa vào live patch cho mọi bản vá:** một số thay đổi vẫn yêu cầu reboot.
- **Không kiểm thử rollback:** dữ liệu hoặc schema mới có thể không tương thích với máy cũ.
- **Không có owner cho ngoại lệ EOL:** máy unsupported tiếp tục tồn tại mà không có kế hoạch.
- **Coi patch compliance là bằng chứng duy nhất:** bỏ sót agent chết, image stale và ứng dụng không được hỗ trợ.

## 21. Quy trình vận hành vòng đời đề xuất

Có thể dùng quy trình sau cho mỗi OS family và workload:

1. **Inventory:** thu thập asset, OS, kernel, runtime, driver, agent và image.
2. **Lifecycle mapping:** đối chiếu phiên bản với lịch hỗ trợ chính thức.
3. **Risk assessment:** xếp ưu tiên theo EOL, lỗ hổng, exposure và criticality.
4. **Compatibility review:** xác nhận OS mục tiêu hỗ trợ ứng dụng, driver và agent.
5. **Patch/upgrade design:** chọn cập nhật tại chỗ, live patch, reboot hoặc replace image.
6. **Test:** kiểm thử chức năng, hiệu năng, backup/restore và phục hồi.
7. **Rollout:** triển khai theo ring hoặc rolling maintenance.
8. **Verification:** kiểm tra running kernel, build, agent heartbeat và sức khỏe ứng dụng.
9. **Inventory update:** ghi nhận phiên bản mới, ngày bảo trì và ngoại lệ.
10. **Retirement:** loại bỏ OS/image/agent cũ và thu hồi cấu hình không còn dùng.

## 22. Ghi nhớ

Vòng đời của OS, kernel, driver, runtime và agent không kết thúc cùng lúc. Muốn duy trì compute an toàn, cần inventory đầy đủ, theo dõi mốc hỗ trợ chính thức, kiểm tra tương thích, vá lỗi theo mức độ rủi ro và lên lịch reboot hoặc thay thế máy có kiểm soát.

Live patch có thể giảm gián đoạn cho một số bản vá kernel nhưng không loại bỏ mọi yêu cầu reboot. In-place upgrade phù hợp với một số máy khó tái tạo; replace instance bằng image mới giúp chuẩn hóa fleet và giảm drift khi hạ tầng hỗ trợ. Hãy cập nhật cả VM đang chạy, golden image, launch template, agent và pipeline để không tái tạo lại nền tảng lỗi thời. Quản lý vòng đời là hoạt động liên tục trong suốt thời gian workload tồn tại trên cloud.
