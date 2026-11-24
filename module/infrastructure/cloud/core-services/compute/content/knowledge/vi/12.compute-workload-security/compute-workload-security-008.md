# Quét lỗ hổng hệ điều hành và phần mềm phụ thuộc

Máy ảo, container và ứng dụng chạy trên đám mây đều dựa vào nhiều thành phần phần mềm: hệ điều hành, kernel, thư viện hệ thống, runtime, package của ứng dụng và các dependency trực tiếp hoặc gián tiếp. Một thành phần có lỗ hổng có thể mở đường cho kẻ tấn công chiếm quyền, đọc dữ liệu, thực thi mã hoặc làm gián đoạn workload. Vì vậy, bảo mật workload compute cần kiểm tra thường xuyên những thành phần đang được cài đặt và sử dụng.

**Quét lỗ hổng (vulnerability scanning)** là quá trình kiểm kê thành phần, đối chiếu phiên bản và cấu hình với thông tin lỗ hổng đã công bố, sau đó đánh giá mức độ rủi ro để khắc phục. Quét hệ điều hành tập trung vào kernel và package của hệ điều hành; quét dependency tập trung vào thư viện, module và package mà ứng dụng sử dụng. Hai loại quét bổ sung cho nhau và cần được áp dụng cho cả image trước khi triển khai lẫn workload đang chạy.

Trong **CLOUD_CORE_SERVICES_COMPUTE**, kết quả quét giúp đội vận hành quyết định khi nào cần cập nhật base image, vá máy ảo, nâng thư viện, rebuild container image hoặc cô lập workload. Một quy trình hiệu quả cần kết hợp dữ liệu CVE, inventory/SBOM, khả năng khai thác, mức độ phơi lộ, tính quan trọng của dịch vụ và thời hạn khắc phục.

## 1. Lỗ hổng phần mềm và các nguồn rủi ro

Lỗ hổng (vulnerability) là điểm yếu trong phần mềm hoặc cấu hình có thể bị khai thác để ảnh hưởng đến tính bảo mật, toàn vẹn hoặc sẵn sàng của hệ thống. Lỗ hổng có thể nằm trong:

- **Hệ điều hành:** kernel, thư viện hệ thống, dịch vụ mạng, trình quản lý gói và công cụ quản trị.
- **Runtime:** Java runtime, .NET runtime, Node.js, Python interpreter hoặc thành phần thực thi khác.
- **Dependency trực tiếp:** package mà ứng dụng khai báo và gọi trực tiếp.
- **Dependency gián tiếp (transitive):** package được một dependency khác kéo vào.
- **Thành phần nền:** web server, reverse proxy, agent giám sát, SSH server, database client hoặc công cụ backup.
- **Image và artifact:** package nằm trong layer của container image hoặc machine image, kể cả khi không được dùng ở đường chạy chính.

Một workload có thể có hàng trăm hoặc hàng nghìn package. Nếu chỉ kiểm tra mã nguồn ứng dụng mà bỏ qua hệ điều hành, runtime và package được đóng gói trong image, nhiều rủi ro sẽ không được phát hiện.

### 1.1. Quét lỗ hổng khác với kiểm tra cấu hình

Các hoạt động bảo mật liên quan nhưng trả lời những câu hỏi khác nhau:

| Hoạt động | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Vulnerability scanning | Thành phần nào có phiên bản bị ảnh hưởng bởi lỗ hổng đã biết? | Package OpenSSL nằm trong dải phiên bản bị ảnh hưởng |
| Configuration/compliance scanning | Hệ thống có cấu hình theo baseline không? | SSH cho phép đăng nhập root hoặc firewall mở quá rộng |
| Malware scanning | Có mã độc hoặc dấu hiệu thực thi độc hại không? | File chứa trojan hoặc cryptominer |
| Secret scanning | Có bí mật bị đưa vào mã nguồn hoặc artifact không? | API key xuất hiện trong repository |
| Penetration testing | Có thể khai thác các điểm yếu trong bối cảnh thực tế không? | Chuỗi tấn công qua ứng dụng và quyền IAM |

Một scanner tìm thấy package có CVE không tự chứng minh hệ thống đã bị xâm nhập. Ngược lại, không có CVE được báo cáo cũng không chứng minh workload an toàn; scanner có thể thiếu inventory, dữ liệu lỗ hổng hoặc khả năng nhận diện package.

## 2. CVE, CVSS và dữ liệu lỗ hổng

Để đối chiếu package với lỗ hổng, scanner thường sử dụng cơ sở dữ liệu và advisory từ nhà cung cấp.

### 2.1. CVE là gì?

**CVE (Common Vulnerabilities and Exposures)** là mã định danh công khai cho một lỗ hổng đã được ghi nhận. Một CVE giúp các nhóm bảo mật, nhà cung cấp và công cụ trao đổi về cùng một vấn đề.

Thông tin một CVE có thể bao gồm:

- Mô tả thành phần và điều kiện bị ảnh hưởng.
- Dải phiên bản bị ảnh hưởng hoặc phiên bản đã khắc phục.
- Tác động có thể xảy ra như thực thi mã, leo thang đặc quyền hoặc từ chối dịch vụ.
- Tham chiếu đến advisory, bản vá và thông tin kỹ thuật.
- Điểm đánh giá mức độ nghiêm trọng nếu đã có.

Không phải mọi lỗ hổng đều có CVE ngay khi được phát hiện. Một số package có advisory riêng của hệ sinh thái hoặc nhà cung cấp. Do đó, công cụ quét cần cập nhật nguồn dữ liệu và hỗ trợ hệ điều hành/package manager đang sử dụng.

### 2.2. CVSS biểu thị mức độ nghiêm trọng

**CVSS (Common Vulnerability Scoring System)** cung cấp cách chấm điểm mức độ nghiêm trọng của lỗ hổng. Điểm CVSS thường nằm trong khoảng 0.0 đến 10.0 và được phân nhóm như sau:

| Điểm CVSS | Nhóm mức độ |
| --- | --- |
| 0.0 | None |
| 0.1–3.9 | Low |
| 4.0–6.9 | Medium |
| 7.0–8.9 | High |
| 9.0–10.0 | Critical |

CVSS Base Score mô tả đặc tính kỹ thuật của lỗ hổng trong một bối cảnh chuẩn hóa. Nó không tự phản ánh đầy đủ workload cụ thể đang chạy trong tổ chức. Một lỗ hổng điểm cao nhưng thành phần không được cài hoặc không thể truy cập có thể có mức ưu tiên thấp hơn một lỗ hổng điểm thấp hơn nhưng đang bị khai thác trên dịch vụ công khai.

Khi đánh giá, cần xem vector CVSS và phiên bản CVSS được dùng. Không chỉ nhìn con số tổng.

### 2.3. Các nguồn bổ sung để ưu tiên

Để quyết định việc nào cần xử lý trước, có thể kết hợp:

- **CISA Known Exploited Vulnerabilities (KEV):** danh mục lỗ hổng được ghi nhận là đã bị khai thác trong thực tế.
- **EPSS (Exploit Prediction Scoring System):** ước lượng xác suất một CVE bị khai thác trong một khoảng thời gian ngắn sắp tới dựa trên mô hình dữ liệu.
- **Vendor advisory:** thông tin của nhà cung cấp hệ điều hành, thư viện hoặc sản phẩm về phiên bản bị ảnh hưởng và bản vá.
- **Exploit intelligence:** thông tin về mã khai thác công khai, điều kiện khai thác và chiến dịch tấn công.
- **Context của workload:** mức độ phơi lộ Internet, dữ liệu được xử lý, quyền của tiến trình và tầm quan trọng của dịch vụ.

KEV và EPSS bổ sung cho CVSS, không thay thế đánh giá rủi ro. EPSS là xác suất dự báo, không phải bằng chứng chắc chắn rằng một hệ thống cụ thể sẽ bị tấn công. KEV cho biết lỗ hổng đã bị khai thác ở đâu đó, không tự khẳng định mọi instance chứa package đều bị khai thác.

## 3. Kiểm kê thành phần trước khi quét

Scanner chỉ có thể đối chiếu những thành phần mà nó nhận diện được. Vì vậy, cần tạo inventory đáng tin cậy cho VM, container image và ứng dụng.

### 3.1. Inventory hệ điều hành

Inventory hệ điều hành nên ghi nhận:

- Tên và phiên bản distribution, edition hoặc release.
- Kernel đang chạy và kernel package đã cài.
- Danh sách package cùng phiên bản và kiến trúc.
- Repository hoặc nguồn package.
- Trạng thái cập nhật và thời điểm kiểm tra gần nhất.
- Agent, dịch vụ nền và phần mềm được cài thêm ngoài package mặc định.

Trên Linux, package manager thường cung cấp dữ liệu package đã cài. Ví dụ:

~~~bash
# Debian/Ubuntu
dpkg-query -W

# RHEL/Fedora và hệ RPM
rpm -qa

# Thông tin hệ điều hành và kernel
cat /etc/os-release
uname -r
~~~

Các lệnh này giúp kiểm kê, không tự kết luận package có lỗ hổng hay đã được vá. Cần đối chiếu với advisory của distribution và nguồn dữ liệu scanner.

### 3.2. Inventory dependency ứng dụng

Ứng dụng thường có file khai báo và lockfile để cố định dependency. Ví dụ:

| Hệ sinh thái | File thường dùng |
| --- | --- |
| Node.js | package.json, package-lock.json, yarn.lock, pnpm-lock.yaml |
| Python | requirements.txt, poetry.lock, Pipfile.lock |
| Java/Maven | pom.xml, dependency tree, lock/version management theo dự án |
| Java/Gradle | build.gradle, build.gradle.kts, dependency locking |
| .NET | .csproj, packages.lock.json, NuGet assets |
| Go | go.mod, go.sum |
| Rust | Cargo.toml, Cargo.lock |

Lockfile giúp xác định phiên bản thực tế được resolve, bao gồm nhiều dependency gián tiếp. Chỉ đọc file khai báo range phiên bản có thể không đủ để biết chính xác package nào được cài trong artifact.

### 3.3. SBOM hỗ trợ kiểm kê

**SBOM (Software Bill of Materials)** là danh mục thành phần phần mềm trong một artifact hoặc sản phẩm. SBOM có thể ghi tên package, phiên bản, nguồn, quan hệ phụ thuộc, license và định danh như PURL hoặc CPE.

SBOM giúp trả lời câu hỏi: “Những image nào có package X phiên bản Y?” khi một CVE mới được công bố. Nó cũng hỗ trợ kiểm tra dependency gián tiếp và so sánh thành phần giữa các bản phát hành.

SBOM không phải báo cáo lỗ hổng. Cần đối chiếu SBOM với dữ liệu advisory/CVE mới nhất để xác định thành phần nào đang bị ảnh hưởng. SBOM cũng chỉ đáng tin khi được tạo từ đúng artifact được triển khai và được lưu cùng ID hoặc digest của artifact đó.

## 4. Quét lỗ hổng hệ điều hành

Quét OS có thể thực hiện trên máy đang chạy, trên root filesystem hoặc trên machine image trước khi phát hành.

### 4.1. Quét package và kernel

Scanner thường so sánh package inventory với advisory của distribution. Nó cần nhận diện đúng distribution, release, repository và phiên bản package. Một số bản phân phối backport bản vá vào package mà không thay đổi số phiên bản upstream theo cách scanner tổng quát mong đợi.

Ví dụ, package của một distribution có thể giữ nguyên phần lớn số phiên bản upstream nhưng bổ sung bản vá bảo mật trong revision của nhà cung cấp. Nếu scanner chỉ so sánh số phiên bản upstream, nó có thể báo false positive. Khi đó cần kiểm tra advisory chính thức và release metadata của distribution.

Kernel là trường hợp cần chú ý riêng:

- Package kernel mới có thể đã cài nhưng máy chưa reboot nên kernel cũ vẫn đang chạy.
- Scanner inventory package có thể thấy bản vá đã cài nhưng runtime scanner vẫn báo kernel đang hoạt động chưa được cập nhật.
- Một số bản vá kernel có cơ chế live patch; cần xác minh trạng thái patch đã được áp dụng và hỗ trợ bởi nhà cung cấp.
- Kernel module bên thứ ba có thể không tương thích với kernel mới.

Vì vậy, cần kiểm tra cả package đã cài và kernel/runtime thực tế đang chạy.

### 4.2. Quét máy ảo đang hoạt động

Có hai cách tiếp cận phổ biến:

- **Authenticated/agent-based scanning:** scanner có agent hoặc thông tin xác thực phù hợp để đọc inventory từ bên trong guest OS. Cách này thường nhận diện package chính xác hơn.
- **Agentless/cloud API scanning:** công cụ lấy metadata, snapshot hoặc inventory qua API của nền tảng. Phạm vi và độ sâu phụ thuộc quyền và khả năng provider.

Quét mạng từ bên ngoài có thể nhận diện dịch vụ, port và phiên bản được công khai, nhưng thường không thấy đầy đủ package cài bên trong VM. Không nên dùng network scan làm phương pháp duy nhất để kiểm tra OS package.

### 4.3. Quét machine image trước khi triển khai

Quét image trước khi tạo VM giúp chặn lỗ hổng ngay tại nguồn. Pipeline có thể:

1. Build image từ base image đã pin.
2. Thu thập package inventory hoặc tạo SBOM.
3. Quét OS package, kernel package và phần mềm cài thêm.
4. Đối chiếu với advisory cập nhật.
5. Chặn phát hành theo chính sách rủi ro.
6. Lưu kết quả quét cùng image ID/digest.

Image đã được quét tại thời điểm build vẫn có thể phát sinh lỗ hổng mới sau đó. Vì vậy, cần quét lại image đã lưu và các VM đang chạy theo lịch hoặc khi có CVE mới quan trọng.

## 5. Quét lỗ hổng dependency của ứng dụng

Quét dependency thường được gọi là **SCA (Software Composition Analysis)**. Công cụ SCA đọc manifest, lockfile, SBOM hoặc artifact để xác định thư viện và đối chiếu với advisory.

### 5.1. Dependency trực tiếp và gián tiếp

Ví dụ ứng dụng khai báo thư viện A. A lại phụ thuộc vào B và C; B tiếp tục phụ thuộc vào D. Một CVE trong D có thể ảnh hưởng ứng dụng dù nhóm phát triển không khai báo D trực tiếp.

SCA cần xây dựng dependency graph để chỉ ra:

- Package trực tiếp được ứng dụng khai báo.
- Package gián tiếp được kéo vào.
- Phiên bản được resolve trong lockfile.
- Đường phụ thuộc dẫn đến package bị ảnh hưởng.
- Phiên bản thay thế hoặc bản vá được khuyến nghị.

Khi nâng dependency, cần kiểm tra tương thích API và thay đổi hành vi. Không phải lúc nào cũng có thể nâng một package độc lập nếu package đó bị ràng buộc bởi framework hoặc runtime.

### 5.2. Kiểm tra dependency theo hệ sinh thái

Ví dụ một số lệnh có thể dùng trong pipeline hoặc môi trường phát triển:

~~~bash
# Node.js: kiểm tra dependency theo package-lock
npm audit --omit=dev

# Python: kiểm tra dependency được liệt kê trong requirements
pip-audit -r requirements.txt

# OSV-Scanner: quét lockfile của dự án
osv-scanner scan --lockfile=package-lock.json
~~~

Lệnh và tùy chọn có thể thay đổi theo phiên bản công cụ. Với Node.js, tùy chọn --omit=dev chỉ phù hợp khi mục tiêu là tập dependency production; vẫn cần quét dev dependency nếu chúng được dùng trong pipeline build hoặc có thể ảnh hưởng môi trường phát triển. Với Python, cần quét đúng environment hoặc lockfile đại diện cho artifact thực tế.

Đối với Java, .NET, Go và Rust, chọn scanner hỗ trợ định dạng lock/manifest tương ứng. Nếu ứng dụng đóng gói thư viện vào fat JAR, assembly hoặc binary, cần xác minh scanner có phân tích được artifact cuối cùng hay chỉ đọc manifest.

### 5.3. Dependency không còn được dùng

Một package có CVE không nhất thiết có thể bị khai thác qua ứng dụng. Tuy nhiên, không nên bỏ qua chỉ vì nhóm phát triển nghĩ package đó không được gọi.

Đánh giá khả năng ảnh hưởng cần xem:

- Package có nằm trong artifact triển khai không?
- Module có được nạp lúc khởi động hoặc tự động đăng ký không?
- Có đường gọi đến hàm bị lỗi không?
- Package có thể bị truy cập qua plugin, reflection, dynamic loading hoặc cấu hình không?
- Lỗ hổng có thể khai thác trước khi ứng dụng gọi trực tiếp package không?

Một số công cụ hỗ trợ reachability analysis để ước lượng dependency có thể được gọi từ code hay không. Kết quả này giúp ưu tiên nhưng không phải bằng chứng tuyệt đối về khả năng khai thác. Cần lưu lại lý do khi chấp nhận rủi ro của dependency chưa được nâng cấp.

## 6. Quét container image và artifact triển khai

Container image có thể chứa nhiều layer và package hệ điều hành cùng dependency ứng dụng. Quét mã nguồn trước build chưa đủ để kiểm tra chính xác nội dung cuối cùng.

### 6.1. Quét image sau khi build

Quy trình phù hợp thường gồm:

1. Build container image từ Dockerfile và base image có phiên bản cố định.
2. Ghi nhận image digest.
3. Quét OS package và application dependency trong image.
4. Tạo SBOM cho image.
5. Đánh giá lỗ hổng theo policy.
6. Ký hoặc lưu provenance nếu quy trình yêu cầu.
7. Chỉ push/promote image đạt điều kiện vào registry dùng cho triển khai.

Ví dụ với Trivy:

~~~bash
# Quét lỗ hổng trong image
trivy image --scanners vuln my-service:1.4.2

# Xuất SBOM ở định dạng CycloneDX
trivy image --format cyclonedx --output sbom.cdx.json my-service:1.4.2
~~~

Tên image trong ví dụ cần thay bằng image thực tế. Nên quét theo digest thay vì tag có thể thay đổi, để kết quả gắn với đúng nội dung artifact.

### 6.2. Image nhiều stage và package bị bỏ lại

Multi-stage build có thể giúp giảm package không cần thiết trong final image. Tuy nhiên, scanner cần quét image cuối cùng được triển khai. Nếu chỉ quét build stage, kết quả có thể chứa package không có trong production; nếu chỉ quét source mà không quét final image, có thể bỏ sót package được cài thêm ở Dockerfile.

Base image cũng cần được theo dõi. Khi base image có bản vá mới, image ứng dụng phải được rebuild để nhận package đã sửa. Chỉ cập nhật tag base image trong Dockerfile mà không rebuild sẽ không thay đổi image đang chạy.

### 6.3. Quét registry và runtime

Registry scanning có thể quét lại image đã lưu khi nguồn CVE được cập nhật. Điều này giúp phát hiện image từng đạt policy nhưng hiện đã có lỗ hổng mới được công bố.

Runtime scanning bổ sung bối cảnh thực tế:

- Image nào đang chạy trên cluster hoặc VM.
- Container/Pod nào đang dùng digest cũ.
- Workload có phơi ra Internet hoặc nhận dữ liệu không tin cậy không.
- Package nào có thể truy cập qua tiến trình đang chạy.
- Image cũ còn tồn tại trong registry hoặc node cache không.

Không nên chỉ quét image mới nhất trong repository. Các phiên bản cũ vẫn có thể đang chạy hoặc được dùng khi autoscaling, rollback hay khôi phục.

## 7. Đánh giá và ưu tiên phát hiện

Một báo cáo scanner có thể chứa hàng trăm phát hiện. Nếu xử lý theo thứ tự CVSS đơn thuần, đội vận hành có thể dành thời gian cho các package ít ảnh hưởng trong khi bỏ sót lỗ hổng đang bị khai thác trên dịch vụ công khai.

### 7.1. Các yếu tố ưu tiên

| Yếu tố | Câu hỏi cần trả lời |
| --- | --- |
| Mức độ nghiêm trọng | CVSS và tác động kỹ thuật là gì? |
| Khai thác thực tế | CVE có trong KEV hoặc có bằng chứng khai thác không? |
| Khả năng khai thác | EPSS, exploit công khai và điều kiện cần có ra sao? |
| Mức phơi lộ | Workload có Internet-facing, port công khai hoặc nhận dữ liệu không tin cậy không? |
| Khả năng tiếp cận | Package có nằm trên đường chạy hoặc reachable path không? |
| Quyền tiến trình | Dịch vụ chạy với quyền root/admin hay quyền hạn chế? |
| Tác động nghiệp vụ | Workload xử lý dữ liệu quan trọng hoặc hỗ trợ dịch vụ thiết yếu không? |
| Khả năng khắc phục | Có bản vá, workaround hoặc phiên bản thay thế đã kiểm thử không? |

### 7.2. Ma trận xử lý minh họa

| Tình huống | Hướng ưu tiên |
| --- | --- |
| CVE critical đang bị khai thác, package nằm trên VM Internet-facing | Khắc phục khẩn cấp, cô lập hoặc áp dụng biện pháp giảm thiểu ngay nếu chưa vá được |
| CVE high trong dependency reachable của API xử lý dữ liệu nhạy cảm | Ưu tiên nâng dependency và phát hành bản sửa trong thời hạn ngắn |
| CVE high trong package không có trong final image | Xác minh inventory và phạm vi; ghi nhận lý do loại trừ khỏi artifact đang triển khai |
| CVE medium trên máy nội bộ có quyền hạn chế | Xử lý theo SLA và lịch bảo trì dựa trên bối cảnh |
| Package thuộc OS đã hết vòng đời hỗ trợ | Lập kế hoạch nâng OS hoặc chuyển workload; không chỉ bỏ qua cảnh báo |

Ma trận là ví dụ định hướng, không phải SLA áp dụng cho mọi tổ chức. Cần xác định thời hạn theo chính sách bảo mật, yêu cầu pháp lý, độ phơi lộ và khả năng vận hành.

### 7.3. Kiểm tra phiên bản do nhà cung cấp backport

Khi scanner báo một package hệ điều hành có CVE, hãy xác minh:

1. Distribution và release có đúng với advisory không?
2. Package revision đã chứa bản vá backport chưa?
3. Kernel đang chạy có cần reboot để sử dụng bản vá không?
4. Scanner có nhận diện đúng epoch, release và kiến trúc package không?
5. Advisory của vendor có xác nhận trạng thái fixed hoặc not affected không?

Không tự đóng finding chỉ vì số phiên bản nhìn có vẻ mới. Ghi lại advisory hoặc bằng chứng vendor để giải thích quyết định.

## 8. Tích hợp quét vào CI/CD

Quét nên xuất hiện ở nhiều thời điểm trong vòng đời phần mềm, thay vì chỉ chạy một lần trước khi đưa production.

### 8.1. Các điểm quét

- **Pull request/commit:** kiểm tra manifest, lockfile và dependency mới thêm.
- **Build:** quét package OS và dependency trong artifact.
- **Trước publish:** áp dụng policy chặn release khi có finding vượt ngưỡng.
- **Registry:** quét lại image đã lưu khi dữ liệu CVE thay đổi.
- **Runtime:** kiểm kê và quét VM/container đang chạy.
- **Định kỳ:** kiểm tra lại machine image, VM lâu ngày và workload không được rebuild thường xuyên.
- **Khi có cảnh báo khẩn:** truy vấn inventory/SBOM để xác định mọi artifact và workload bị ảnh hưởng.

### 8.2. Pipeline mẫu

~~~yaml
stages:
  - source_scan
  - build
  - artifact_scan
  - publish

dependency-scan:
  stage: source_scan
  script:
    - run-sca --lockfiles
    - export-dependency-report

build-image:
  stage: build
  script:
    - docker build -t app:commit-sha .

scan-final-image:
  stage: artifact_scan
  script:
    - trivy image --scanners vuln --format json --output image-vuln.json app:commit-sha
    - trivy image --format cyclonedx --output sbom.cdx.json app:commit-sha
    - evaluate-vulnerability-policy image-vuln.json
  artifacts:
    paths:
      - image-vuln.json
      - sbom.cdx.json

publish-image:
  stage: publish
  script:
    - publish-image-by-digest
  rules:
    - if: '$VULNERABILITY_POLICY_PASSED == "true"'
~~~

Tên lệnh run-sca, evaluate-vulnerability-policy và publish-image-by-digest là placeholder cho công cụ của tổ chức. Pipeline thật cần truyền kết quả scan giữa các job một cách an toàn và không để job publish chạy nếu bước policy thất bại.

### 8.3. Đặt ngưỡng chặn hợp lý

Không nên chặn mọi finding một cách máy móc vì có thể làm pipeline không khả dụng, nhất là khi dependency có advisory chưa được đánh giá hoặc package hệ điều hành chứa cảnh báo không áp dụng. Ngược lại, bỏ qua mọi cảnh báo để tránh build fail làm mất tác dụng của scanning.

Policy có thể kết hợp:

- Mức CVSS tối thiểu.
- CVE thuộc KEV hoặc có exploit đang hoạt động.
- Package có trong final artifact hay không.
- Dependency có reachable hay không.
- Workload có phơi lộ hoặc xử lý dữ liệu quan trọng không.
- Có bản vá hoặc phiên bản thay thế đã được xác minh không.
- Ngoại lệ có owner và thời hạn hay không.

Nên có chế độ cảnh báo ban đầu để đo chất lượng scanner và điều chỉnh policy trước khi bật enforcement rộng. Khi đã chặn release, phải có quy trình xử lý false positive và exception rõ ràng.

## 9. Khắc phục lỗ hổng

Sau khi xác nhận finding có ảnh hưởng, chọn biện pháp phù hợp với lớp bị lỗi.

### 9.1. Vá hệ điều hành

Với VM có thể cập nhật package bằng package manager hoặc công cụ quản lý patch tập trung. Ví dụ:

~~~bash
# Debian/Ubuntu: cập nhật danh sách và áp dụng package update
sudo apt-get update
sudo apt-get upgrade

# RHEL-family: xem advisory bảo mật và áp dụng bản vá theo policy
sudo dnf updateinfo list --security
sudo dnf update --security
~~~

Lệnh cập nhật cần áp dụng theo distribution, repository và chính sách bảo trì. Không nên chạy nâng cấp lớn không kiểm soát trên production. Trước khi vá cần xem package thay đổi, dependency, yêu cầu reboot và khả năng rollback.

Với fleet VM được quản lý bằng image bất biến, cách bền vững thường là cập nhật base image, build image mới, quét lại rồi thay thế instance theo rolling strategy. Vá trực tiếp máy đang chạy có thể là biện pháp khẩn cấp, nhưng cần đưa thay đổi trở lại pipeline để máy mới không tái tạo từ image dễ bị lỗi.

### 9.2. Nâng cấp dependency

Khi dependency có bản vá:

1. Xác định package và đường phụ thuộc bị ảnh hưởng.
2. Chọn phiên bản đã sửa theo advisory chính thức.
3. Cập nhật manifest và lockfile.
4. Chạy unit, integration, compatibility và security tests.
5. Build lại artifact và quét final artifact.
6. Phát hành theo canary/rolling strategy.
7. Theo dõi lỗi runtime và khả năng tương thích.

Không nên chỉ sửa package trong lockfile bằng tay nếu package manager có thể resolve lại. Dùng công cụ của hệ sinh thái để cập nhật dependency nhất quán và kiểm tra thay đổi transitive.

### 9.3. Khi chưa có bản vá

Nếu chưa có bản vá, có thể cần biện pháp giảm thiểu tạm thời:

- Tắt hoặc giới hạn thành phần bị ảnh hưởng nếu ứng dụng vẫn hoạt động.
- Chặn endpoint hoặc port có thể kích hoạt lỗ hổng.
- Giới hạn nguồn truy cập bằng security group, firewall, WAF hoặc network policy.
- Giảm quyền của tiến trình và tách workload khỏi dữ liệu quan trọng.
- Tắt plugin hoặc feature có lỗi nếu vendor khuyến nghị.
- Tăng giám sát, phát hiện hành vi bất thường và chuẩn bị phương án cô lập.

Biện pháp giảm thiểu không thay thế bản vá lâu dài. Cần ghi owner, thời hạn xem xét và điều kiện gỡ bỏ exception.

### 9.4. Rebuild image và thay thế workload

Với VM/container image, cập nhật package ở máy build không tự sửa các instance hoặc container đã tạo trước đó. Cần:

1. Cập nhật base image hoặc dependency.
2. Build artifact mới.
3. Quét lại OS và dependency.
4. Ghi ID/digest và SBOM.
5. Triển khai canary.
6. Thay thế các instance/pod đang dùng artifact cũ.
7. Xác minh runtime inventory không còn workload dễ bị ảnh hưởng.
8. Thu hồi hoặc đánh dấu deprecated image cũ theo chính sách.

Không xóa image cũ ngay khi phát hành bản mới nếu nó còn cần cho rollback hoặc điều tra. Tuy nhiên, cần ngăn autoscaling hoặc pipeline vô tình tiếp tục tạo máy từ image đã biết có lỗ hổng nghiêm trọng.

## 10. Quản lý false positive và exception

Scanner có thể báo sai do thiếu metadata, package backport, dependency không được đóng gói hoặc nhầm lẫn phiên bản. Mọi quyết định loại trừ cần dựa trên bằng chứng.

### 10.1. Quy trình xác minh false positive

1. Xác minh package có thực sự tồn tại trong artifact hoặc máy đang chạy.
2. Kiểm tra package name, ecosystem, architecture và phiên bản đầy đủ.
3. Đối chiếu advisory của vendor và nguồn CVE.
4. Kiểm tra patch/backport hoặc điều kiện bị ảnh hưởng.
5. Xác minh finding có áp dụng với cấu hình và feature đang bật không.
6. Ghi bằng chứng, người xác minh và ngày xem xét.

Không nên dùng một rule ignore chung cho mọi image hoặc mọi phiên bản package chỉ vì một trường hợp đã được xác minh là false positive.

### 10.2. Exception chấp nhận rủi ro

Khi chưa thể khắc phục trong thời hạn, exception nên ghi:

- CVE/finding và package bị ảnh hưởng.
- Workload, image ID/digest và môi trường liên quan.
- Lý do chưa thể vá.
- Rủi ro còn lại và khả năng khai thác.
- Biện pháp giảm thiểu đang áp dụng.
- Owner chịu trách nhiệm.
- Người phê duyệt.
- Ngày hết hạn và lịch đánh giá lại.

Exception phải có thời hạn. Khi hết hạn, finding cần được đánh giá lại, gia hạn có phê duyệt hoặc chuyển sang khắc phục. Không biến ignore rule thành cách che giấu lỗ hổng lâu dài.

## 11. Theo dõi workload đang chạy và phát hiện drift

Quét trong CI/CD kiểm tra artifact trước khi triển khai. Nhưng sau khi chạy, workload có thể thay đổi do patch thủ công, cài package trực tiếp hoặc cấu hình ngoài IaC. Đây là **configuration drift** và có thể khiến trạng thái runtime khác với image đã quét.

Để phát hiện:

- Thu thập inventory định kỳ từ VM và node.
- So sánh package runtime với image/SBOM đã phê duyệt.
- Theo dõi VM không có agent hoặc không gửi inventory.
- Kiểm kê image digest thực tế của Pod/container.
- Phát hiện máy dùng OS đã hết vòng đời hỗ trợ.
- Quét lại theo lịch và khi có CVE quan trọng mới.
- Kiểm tra máy có bản vá đã cài nhưng chưa reboot.

Đối với Kubernetes, cần xem cả image đang chạy và node OS. Quét Pod image không thay thế quét kernel và package của worker node. Tương tự, quét node không thay thế SCA cho thư viện bên trong ứng dụng.

## 12. Lựa chọn công cụ quét

Không có một scanner duy nhất bao phủ mọi lớp. Có thể kết hợp công cụ theo mục tiêu:

| Lớp cần kiểm tra | Loại công cụ | Ví dụ |
| --- | --- | --- |
| OS package trên VM | Agent hoặc authenticated scanner | Công cụ vulnerability management của cloud/security platform |
| Root filesystem hoặc machine image | Filesystem/image scanner | Trivy, Grype và công cụ image builder tích hợp |
| Dependency ứng dụng | SCA | OSV-Scanner, Dependabot, Snyk hoặc scanner của nền tảng CI |
| Container image | Registry/image scanner | Trivy, Grype hoặc registry scanning |
| SBOM | SBOM generator và analyzer | Syft, Trivy và công cụ hỗ trợ CycloneDX/SPDX |
| Runtime inventory | Cloud security posture/workload protection | Agent, cloud API hoặc Kubernetes integration |

Khi chọn công cụ, đánh giá:

- Hỗ trợ distribution, package manager và ngôn ngữ đang dùng.
- Khả năng quét lockfile, binary, image layer và root filesystem.
- Chất lượng dữ liệu advisory và tần suất cập nhật.
- Nhận diện backport và phiên bản vendor.
- Reachability analysis và khả năng liên kết finding với workload.
- Xuất SBOM, JSON/SARIF hoặc định dạng tích hợp pipeline.
- Cách triển khai agent, quyền cần thiết và ảnh hưởng hiệu năng.
- Khả năng quản lý exception, audit và theo dõi remediation.

Nên thử nghiệm trên một nhóm VM và repository đại diện trước khi triển khai toàn tổ chức. Kiểm tra tỷ lệ false positive, độ bao phủ và chi phí vận hành.

## 13. Đo hiệu quả chương trình vulnerability management

Số lượng finding giảm không nhất thiết có nghĩa rủi ro giảm; scanner có thể ngừng hoạt động hoặc inventory thiếu. Cần đo cả coverage, tốc độ xử lý và mức rủi ro còn lại.

| Chỉ số | Ý nghĩa |
| --- | --- |
| Asset coverage | Tỷ lệ VM, image, node và repository được quét |
| Scan freshness | Thời gian từ lần scan gần nhất và mức cập nhật dữ liệu CVE |
| Critical/High findings | Số finding theo mức độ và theo workload |
| KEV exposure | Số workload chứa lỗ hổng đang được ghi nhận khai thác |
| Mean time to remediate | Thời gian trung bình từ phát hiện đến khắc phục |
| SLA compliance | Tỷ lệ finding được xử lý trong thời hạn |
| Exception age | Tuổi và số lượng exception còn hiệu lực |
| Vulnerable workload count | Số instance/container thực tế vẫn chạy artifact bị ảnh hưởng |
| EOL asset count | Số workload dùng OS/runtime hết hỗ trợ |

Nên phân nhóm theo môi trường, owner, ứng dụng, loại tài sản và mức độ phơi lộ. Một finding xuất hiện trên 100 instance cùng một image cần được xử lý ở nguồn image và rollout, không nên đóng từng finding thủ công mà không sửa artifact gốc.

## 14. Ví dụ: xử lý CVE trong dependency của dịch vụ Java

Một dịch vụ Java chạy trên VM và container. Scanner phát hiện một thư viện HTTP trong dependency tree có phiên bản bị ảnh hưởng bởi CVE. Báo cáo cho thấy package được kéo vào gián tiếp qua framework; image production và một số image cũ trong registry đều chứa phiên bản đó.

Nhóm xử lý:

1. Kiểm tra CVE, advisory của vendor và dải phiên bản bị ảnh hưởng.
2. Dùng dependency tree để xác định package cha kéo thư viện vào.
3. Kiểm tra thư viện có nằm trong artifact production và đường gọi bị ảnh hưởng có reachable không.
4. Chọn phiên bản framework hoặc thư viện đã sửa, cập nhật manifest và lockfile.
5. Chạy unit/integration test, kiểm tra tương thích và build lại JAR/container image.
6. Quét final image, tạo SBOM và xác nhận finding đã được xử lý.
7. Phát hành canary, theo dõi lỗi HTTP, latency và log ứng dụng.
8. Rollout đến fleet, xác minh VM/Pod không còn dùng digest cũ.
9. Đánh dấu image cũ deprecated, ngăn tạo workload mới từ image đó và giữ theo retention phục vụ rollback có kiểm soát.

Nếu chưa thể nâng framework ngay vì tương thích, nhóm có thể giới hạn endpoint hoặc feature liên quan, tăng giám sát và ghi exception có thời hạn. Khi bản vá đã được kiểm thử, exception phải được đóng và workload cũ được thay thế.

## 15. Những sai lầm thường gặp

- Chỉ quét mã nguồn mà không quét OS package và final image.
- Chỉ quét container image mà bỏ qua kernel và worker node.
- Chỉ quét dependency trực tiếp, bỏ qua dependency gián tiếp.
- Dùng CVSS làm tiêu chí duy nhất để sắp xếp ưu tiên.
- Bỏ qua CVE đã bị khai thác hoặc workload đang phơi lộ Internet.
- Cho rằng scanner báo finding đồng nghĩa hệ thống chắc chắn bị khai thác.
- Đóng false positive chỉ dựa trên số phiên bản mà không kiểm tra vendor backport.
- Cập nhật package trên máy build nhưng không rebuild và thay thế workload cũ.
- Không quét lại registry khi dữ liệu CVE mới được công bố.
- Dùng tag image thay đổi được thay cho digest khi lưu kết quả scan.
- Ignore finding vô thời hạn mà không có owner và ngày hết hạn.
- Không theo dõi VM/node không gửi inventory hoặc đã hết hỗ trợ.
- Coi SBOM là bằng chứng rằng artifact không có lỗ hổng.

## 16. Quy trình vận hành đề xuất

1. **Kiểm kê tài sản:** lập danh sách VM, machine image, container image, node, repository và owner.
2. **Thu thập inventory:** package OS, kernel, runtime, lockfile và SBOM theo artifact.
3. **Quét nhiều lớp:** source/dependency, machine image, final container image, VM và node đang chạy.
4. **Cập nhật dữ liệu:** dùng advisory, CVE, vendor bulletin, KEV và nguồn exploit intelligence đáng tin cậy.
5. **Ưu tiên theo bối cảnh:** kết hợp CVSS, exploitability, exposure, reachability, quyền và tác động nghiệp vụ.
6. **Áp dụng policy CI/CD:** chặn release theo ngưỡng đã thống nhất và có quy trình xử lý exception.
7. **Khắc phục:** vá OS, nâng dependency, rebuild image, thay workload hoặc áp dụng mitigation tạm thời.
8. **Xác minh:** quét lại artifact, kiểm tra runtime digest/package và xác nhận finding đã đóng.
9. **Theo dõi drift:** quét định kỳ, phát hiện máy không được quản lý và OS/runtime hết vòng đời.
10. **Báo cáo:** theo dõi coverage, scan freshness, SLA, KEV exposure, remediation time và exception.

## 17. Nguyên tắc cần ghi nhớ

1. Quét OS và quét dependency là hai phần khác nhau; cần kiểm tra cả hai.
2. Inventory chính xác và lockfile/SBOM giúp scanner xác định đúng thành phần.
3. CVE định danh lỗ hổng; CVSS đánh giá mức nghiêm trọng; KEV, EPSS và bối cảnh workload hỗ trợ ưu tiên.
4. Advisory của vendor rất quan trọng vì package có thể chứa bản vá backport dù số phiên bản upstream chưa thay đổi như dự kiến.
5. Quét image trước triển khai phải đi cùng quét lại registry và workload đang chạy.
6. Kết quả scan phải gắn với artifact ID/digest và thời điểm quét.
7. Khắc phục ở nguồn image/dependency rồi rollout để loại bỏ phiên bản dễ bị ảnh hưởng.
8. False positive và exception cần bằng chứng, owner, biện pháp giảm thiểu và thời hạn.
9. SBOM hỗ trợ kiểm kê và truy vết, nhưng không tự chứng minh artifact an toàn.
10. Coverage, scan freshness và thời gian khắc phục quan trọng không kém số finding còn lại.

Quét lỗ hổng hệ điều hành và phần mềm phụ thuộc giúp đội kỹ thuật nhìn thấy rủi ro trong toàn bộ chuỗi thành phần của workload compute. Khi kết hợp inventory chính xác, dữ liệu lỗ hổng cập nhật, ưu tiên theo khả năng khai thác và remediation có kiểm chứng, tổ chức có thể giảm thời gian phơi nhiễm và duy trì VM, container cùng ứng dụng trên nền tảng đám mây an toàn hơn.
