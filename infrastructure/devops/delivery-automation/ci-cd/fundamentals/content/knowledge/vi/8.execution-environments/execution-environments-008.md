# Kiểm soát quyền của máy chạy và khả năng truy cập mạng

Máy chạy CI/CD (runner hoặc agent) là nơi pipeline thực thi mã nguồn, cài dependency, chạy kiểm thử, tạo artifact và đôi khi triển khai phần mềm. Vì runner trực tiếp xử lý mã và thông tin xác thực, quyền của nó cùng khả năng truy cập mạng quyết định phạm vi ảnh hưởng nếu một job bị lỗi hoặc chạy mã không đáng tin cậy.

Một runner có thể đọc repository, truy cập registry, gọi dịch vụ kiểm thử, tải dependency, kết nối cloud hoặc triển khai đến môi trường đích. Nếu mọi job đều dùng chung một máy có quyền rộng và mạng mở, một thay đổi nhỏ trong pull request có thể trở thành đường dẫn đến tài nguyên nhạy cảm. Vì vậy, cần thiết kế môi trường thực thi theo nguyên tắc quyền tối thiểu, cô lập theo mức độ tin cậy, giới hạn mạng theo nhu cầu và thu hồi tài nguyên sau khi job kết thúc.

Bài học này tập trung vào hai mặt kiểm soát gắn chặt với nhau: **runner được phép làm gì** và **runner được phép kết nối đến đâu**. Nội dung bao gồm danh tính máy chạy, quyền theo job, mạng vào/ra, cô lập runner, quản lý secret, self-hosted runner, xử lý sự cố và lộ trình thực hành trong một hệ thống CI/CD.

## 1. Vai trò và ranh giới tin cậy của runner

Runner là môi trường thực thi một hoặc nhiều job. Tùy nền tảng, runner có thể là máy ảo do nhà cung cấp quản lý, máy chủ tự quản lý, container, Kubernetes pod hoặc một môi trường tạm được tạo cho từng job.

Một job thường thực hiện một số công việc:

- Lấy mã nguồn từ repository.
- Tải dependency và toolchain.
- Chạy script build hoặc test.
- Khởi tạo container và dịch vụ phụ thuộc.
- Đọc hoặc ghi artifact vào registry.
- Gọi API của cloud hoặc nền tảng triển khai.
- Kết nối đến môi trường test, staging hoặc production.
- Gửi log và trạng thái về control plane của CI/CD.

Mỗi hoạt động đều có thể cần quyền hệ điều hành, quyền repository, credential ứng dụng hoặc kết nối mạng. Vì vậy, cần xác định rõ ranh giới tin cậy giữa các thành phần:

| Thành phần | Vai trò | Rủi ro cần kiểm soát |
|---|---|---|
| Control plane CI/CD | Lập lịch, cấp job, lưu trạng thái và quản lý cấu hình | Quyền điều phối, token và cấu hình workflow |
| Runner host | Cấp CPU, bộ nhớ, filesystem và mạng cho job | Quyền hệ điều hành, tiến trình còn sót, truy cập mạng |
| Job process | Chạy script, build và test | Mã độc hoặc lệnh ngoài dự kiến |
| Container / VM của job | Cô lập tiến trình và phụ thuộc | Chia sẻ kernel, volume, socket hoặc credential |
| Secret manager / identity provider | Cấp thông tin xác thực | Lạm dụng token, phạm vi và thời hạn credential |
| Registry / artifact store | Lưu dependency và đầu ra build | Ghi đè artifact, truy cập trái phép, cache poisoning |
| Môi trường triển khai | Chạy ứng dụng | Thay đổi ngoài phạm vi, lộ dữ liệu hoặc gián đoạn |

Một điểm quan trọng: repository, pull request, pipeline definition và script được thực thi đều có thể ảnh hưởng đến hành vi của runner. Job chạy mã từ nhánh chưa được tin cậy phải được xem là có khả năng thực thi lệnh tùy ý trong phạm vi quyền mà runner cung cấp.

## 2. Xác định mức độ tin cậy trước khi cấp runner

Không phải mọi job đều có cùng mức độ tin cậy. Có thể phân nhóm theo nguồn mã và quyền mà công việc cần:

| Nhóm công việc | Nguồn mã / mức tin cậy | Quyền phù hợp |
|---|---|---|
| Kiểm tra PR từ fork | Có thể chứa mã chưa được tin cậy | Runner tạm, quyền đọc tối thiểu, không có secret nhạy cảm |
| Build nhánh tính năng nội bộ | Được kiểm soát trong repository nhưng vẫn cần giới hạn | Runner dùng chung đã cô lập, quyền đọc dependency |
| Kiểm thử tích hợp | Cần kết nối dịch vụ test | Runner thuộc mạng test, dữ liệu và credential riêng |
| Build artifact phát hành | Commit đã qua cổng tích hợp | Quyền ghi registry có giới hạn và danh tính xác định |
| Triển khai staging | Đầu vào đã được xác minh | Quyền triển khai staging, mạng chỉ đến đích cần thiết |
| Triển khai production | Mức ảnh hưởng cao | Runner hoặc job riêng, phê duyệt và credential ngắn hạn |

Một pull request nội bộ không tự động an toàn tuyệt đối. Tài khoản có quyền trong repository có thể bị xâm phạm, dependency có thể bị đầu độc hoặc workflow có thể bị thay đổi ngoài ý muốn. Vì vậy, quyền của runner cần dựa trên chính sách và ranh giới kỹ thuật, không chỉ dựa trên giả định rằng người gửi commit là đáng tin.

Nên phân tách ít nhất các nhóm sau khi rủi ro đủ lớn:

- Runner xử lý mã chưa được tin cậy.
- Runner build và test cho nhánh dùng chung.
- Runner có quyền publish artifact.
- Runner hoặc job có quyền triển khai môi trường nhạy cảm.

Sự phân tách có thể được thực hiện bằng pool runner, nhãn, nhóm máy, tài khoản hệ điều hành, network segment hoặc môi trường tạm. Cách triển khai cụ thể tùy quy mô và nền tảng, nhưng ranh giới quyền phải có thể kiểm tra được.

## 3. Cấp quyền cho máy chạy theo nguyên tắc tối thiểu

Quyền tối thiểu có nghĩa là mỗi runner và job chỉ nhận quyền cần cho công việc hiện tại, trong phạm vi và thời gian cần thiết.

### 3.1. Phân biệt quyền của host và quyền của job

Có hai lớp quyền cần xem xét:

- **Quyền của runner host:** quyền quản trị hệ điều hành, cài phần mềm, quản lý dịch vụ, truy cập filesystem và cấu hình mạng.
- **Quyền của job:** quyền đọc mã nguồn, ghi artifact, gọi API, truy cập secret hoặc triển khai ứng dụng.

Job thông thường không nên chạy với quyền quản trị host. Nếu job cần Docker, Kubernetes hoặc thao tác hệ thống đặc biệt, cần đánh giá riêng vì một số cách cấp quyền có thể cho phép job kiểm soát host.

Không cấp tài khoản quản trị chỉ để tránh lỗi permission trong quá trình build. Hãy xác định chính xác thư mục, socket hoặc thao tác cần thiết rồi cấp quyền hẹp hơn.

### 3.2. Phân tách danh tính theo chức năng

Không nên dùng một tài khoản máy duy nhất có quyền đọc mọi repository, ghi mọi registry và triển khai mọi môi trường. Có thể tạo danh tính hoặc credential riêng cho:

- Checkout repository.
- Đọc package và dependency.
- Publish artifact.
- Đọc secret của môi trường test.
- Triển khai staging.
- Triển khai production.

Một job unit test thường chỉ cần đọc mã nguồn và dependency. Job publish cần quyền ghi vào đúng repository hoặc package namespace. Job deploy staging cần quyền triển khai vào staging, không cần quyền production.

### 3.3. Token ngắn hạn và workload identity

Khi nền tảng hỗ trợ, nên dùng thông tin xác thực ngắn hạn hoặc cơ chế workload identity thay cho khóa dài hạn được lưu cố định trên runner.

Ví dụ, job có thể nhận token tạm thời thông qua OIDC hoặc cơ chế liên kết danh tính tương đương. Hệ thống đích xác minh issuer, audience, subject và điều kiện trust trước khi cấp quyền. Cấu hình cần giới hạn token theo repository, branch, environment hoặc workflow được phép.

Không nên chỉ bật OIDC rồi cấp quyền rộng. Trust policy phải xác định chính xác workload nào được phép nhận danh tính và quyền nào được cấp. Khi job kết thúc, credential ngắn hạn hết hiệu lực theo thời hạn đã cấu hình.

### 3.4. Giới hạn quyền ghi

Quyền ghi thường có tác động lớn hơn quyền đọc. Một job có quyền ghi vào repository, package registry hoặc môi trường triển khai có thể thay đổi đầu ra mà người khác tin cậy.

Hãy:

- Chỉ cấp quyền ghi cho job thực sự cần publish hoặc deploy.
- Giới hạn package namespace và repository đích.
- Dùng protection rule cho môi trường cần phê duyệt.
- Không truyền token ghi cho bước chạy test từ mã chưa được tin cậy.
- Ghi nhận danh tính đã thực hiện thao tác và artifact liên quan.

## 4. Kiểm soát khả năng truy cập mạng

Runner cần mạng để giao tiếp với control plane, tải dependency, gọi dịch vụ test và có thể triển khai ứng dụng. Tuy nhiên, mạng mở không giới hạn làm tăng phạm vi mà mã chạy trong job có thể tiếp cận.

Cần phân biệt hai hướng:

- **Outbound (egress):** kết nối do runner hoặc job khởi tạo ra ngoài, ví dụ tải dependency, gửi log hoặc gọi API.
- **Inbound (ingress):** kết nối từ hệ thống khác khởi tạo vào runner, ví dụ truy cập dịch vụ đang chạy trong job hoặc điều khiển máy từ xa.

Sơ đồ luồng mạng khái quát:

~~~mermaid
flowchart LR
    B["Runner"] -->|"Agent mở kênh outbound hai chiều"| A["Control plane CI/CD"]
    B -->|"HTTPS / API theo allowlist"| C["Dependency registry"]
    B -->|"Kết nối giới hạn"| D["Dịch vụ kiểm thử"]
    B -->|"Credential ngắn hạn"| E["Identity / secret service"]
    B -->|"Publish theo quyền"| F["Artifact registry"]
    B -->|"Deploy theo môi trường"| G["Staging / Production"]
    H["Internet hoặc mạng nội bộ khác"] -. "Bị chặn nếu không cần" .-> B
~~~

Trong nhiều nền tảng, runner agent chủ động kết nối outbound đến control plane để nhận job và gửi trạng thái. Cơ chế cụ thể tùy nhà cung cấp. Không nên mở cổng inbound rộng chỉ vì runner cần giao tiếp với nền tảng CI/CD; hãy xác nhận yêu cầu mạng chính thức của nền tảng và chỉ mở đúng đích, giao thức, cổng cần thiết.

### 4.1. Lập danh sách đích mạng cần thiết

Trước khi cấu hình firewall hoặc network policy, hãy liệt kê các đích mà job thực sự cần:

| Đích mạng | Mục đích | Chính sách gợi ý |
|---|---|---|
| Control plane CI/CD | Nhận job và gửi trạng thái | Chỉ cho phép endpoint, giao thức và cổng theo tài liệu nền tảng |
| Git repository | Checkout source và lấy metadata | Chỉ cho phép host hoặc endpoint cần thiết |
| Package registry | Tải dependency | Giới hạn domain/namespace và dùng TLS |
| Artifact registry | Publish hoặc tải artifact | Quyền theo repository, xác thực riêng |
| Secret / identity provider | Nhận credential được phép | Chỉ cho job và danh tính hợp lệ |
| Dịch vụ test | Integration test hoặc smoke test | Chỉ kết nối mạng test cần thiết |
| Cloud / deployment API | Triển khai tài nguyên | Giới hạn endpoint, role và môi trường |
| Dịch vụ giám sát | Gửi log, metric và trạng thái | Dùng endpoint nội bộ hoặc được phê duyệt |

Danh sách này nên được xác nhận từ log mạng và tài liệu nền tảng. Không nên cho phép toàn bộ Internet chỉ vì chưa biết job cần những endpoint nào. Khi cần cập nhật dependency từ Internet công cộng, có thể dùng proxy hoặc mirror nội bộ để kiểm soát nguồn và lưu lượng.

### 4.2. Egress filtering

Egress filtering giới hạn kết nối đi ra từ runner. Có thể áp dụng theo:

- Domain hoặc FQDN.
- Địa chỉ IP hoặc dải mạng.
- Cổng và giao thức.
- Network segment hoặc security group.
- Proxy có xác thực và ghi log.
- Chính sách DNS và danh sách resolver được phép.

Lọc theo IP có thể khó duy trì với dịch vụ cloud dùng địa chỉ động. Lọc theo domain cần hiểu cách firewall hoặc proxy xử lý DNS, TLS và redirect. Hãy dùng cơ chế được nền tảng mạng hỗ trợ, cập nhật danh sách đích có kiểm soát và kiểm thử khi endpoint thay đổi.

Không nên chỉ dựa vào DNS allowlist nếu job có thể kết nối trực tiếp đến IP hoặc dùng resolver khác. Chính sách cần được áp dụng tại điểm mạng có thể thực thi và quan sát được.

### 4.3. Ingress filtering

Runner thường không cần nhận kết nối tùy ý từ Internet. Nếu cần truy cập runner để điều tra, hãy dùng kênh quản trị được kiểm soát, danh tính cá nhân, xác thực mạnh và ghi log.

Các nguyên tắc:

- Không phơi bày cổng quản trị runner ra Internet công cộng.
- Giới hạn nguồn mạng có thể truy cập dịch vụ nội bộ.
- Dùng bastion hoặc cơ chế truy cập quản trị được tổ chức phê duyệt nếu cần.
- Không để job PR mở dịch vụ test trên địa chỉ có thể truy cập từ mạng không liên quan.
- Đóng hoặc xóa endpoint tạm sau khi job hoàn tất.
- Tránh dùng chung cổng hoặc dịch vụ giữa các job không cùng mức tin cậy.

Nếu nền tảng cần callback hoặc kết nối inbound đặc biệt, hãy xác minh endpoint, nguồn, xác thực và thời hạn mở cổng. Không dùng một rule ingress rộng để giải quyết lỗi kết nối chưa được điều tra.

### 4.4. Phân đoạn mạng

Runner có thể được đặt trong các network segment khác nhau:

- Segment build: truy cập repository và package registry.
- Segment integration: truy cập các dịch vụ test cần thiết.
- Segment release: truy cập artifact registry và hệ thống phát hành.
- Segment deployment: truy cập API hoặc endpoint của môi trường đích.

Không phải mọi tổ chức đều cần bốn mạng riêng. Tuy nhiên, runner có quyền production nên được giới hạn đường đi mạng rõ ràng và không dùng chung segment với job xử lý mã chưa tin cậy.

### 4.5. Bảo vệ endpoint metadata và mạng quản trị

Job chạy trên cloud có thể ở gần endpoint metadata của máy ảo hoặc workload identity. Nếu mã trong job có thể gửi yêu cầu tùy ý đến các endpoint này, nó có thể tìm cách lấy thông tin danh tính hoặc credential mà host được phép sử dụng. Hãy giới hạn quyền truy cập metadata theo nền tảng, chỉ bật cơ chế token hoặc workload identity cần thiết và không để job chưa được tin cậy truy cập danh tính của host.

Đồng thời, không cho runner truy cập tùy ý vào mạng quản trị, control plane của cluster, dịch vụ cấu hình nội bộ hoặc các máy chủ khác chỉ vì chúng nằm cùng mạng riêng. Nếu một job cần gọi API nội bộ, hãy xác định đúng endpoint, danh tính và thao tác cần thiết rồi tạo rule riêng. Điều này giảm rủi ro khi một dependency hoặc script build cố truy cập các dịch vụ không liên quan.

## 5. Cô lập runner và job

Giới hạn quyền mạng sẽ không đủ nếu các job có thể đọc dữ liệu hoặc credential còn sót từ job trước. Cần cô lập cả tiến trình, filesystem, container, tài khoản và vòng đời runner.

### 5.1. Runner tạm thời và runner dùng lâu dài

| Mô hình | Đặc điểm | Phù hợp khi |
|---|---|---|
| Ephemeral runner | Tạo cho một job hoặc một lần chạy rồi hủy | Xử lý mã chưa tin cậy, job nhạy cảm, cần giảm tồn dư |
| Persistent runner | Máy chạy được tái sử dụng qua nhiều job | Công việc ổn định, có yêu cầu phần cứng hoặc cache lớn |
| Autoscaled runner | Tạo/hủy theo hàng đợi và nhu cầu | Tải thay đổi, cần cân bằng chi phí và thời gian chờ |
| Containerized job | Job chạy trong container trên host hoặc cluster | Cần môi trường nhất quán và cô lập ở mức tiến trình |
| VM-per-job | Mỗi job có VM riêng | Cần ranh giới cô lập mạnh hơn hoặc kernel riêng |

Runner tạm thời giảm nguy cơ credential, file và tiến trình từ job cũ ảnh hưởng job mới. Tuy nhiên, việc hủy runner phải bao gồm cả volume, disk, cache cục bộ, network attachment và credential được cấp. Chỉ xóa tiến trình agent chưa chắc đã xóa toàn bộ dữ liệu còn lại.

Runner lâu dài có thể tiết kiệm thời gian khởi tạo và giữ cache, nhưng cần quy trình dọn dẹp, vá lỗi, kiểm tra trạng thái và phân quyền nghiêm ngặt.

### 5.2. Container không thay thế hoàn toàn ranh giới máy ảo

Container giúp đóng gói runtime và phụ thuộc, đồng thời cô lập filesystem, process và network namespace ở mức cấu hình. Tuy nhiên, container thường chia sẻ kernel với host. Nếu job được cấp quyền đặc biệt, mount Docker socket hoặc mount thư mục nhạy cảm, ranh giới cô lập có thể bị suy yếu đáng kể.

VM có kernel riêng và có thể tạo ranh giới mạnh hơn, nhưng vẫn cần cấu hình mạng, quyền, image và credential đúng cách. Lựa chọn phụ thuộc mức độ tin cậy của mã, yêu cầu hiệu năng và mô hình hạ tầng.

### 5.3. Cẩn trọng với Docker socket và privileged container

Cho job quyền truy cập Docker daemon của host có thể cho phép job tạo container với quyền rộng, mount filesystem host hoặc điều khiển tài nguyên khác. Tương tự, privileged container có thể làm giảm đáng kể mức cô lập.

Nếu cần build container image, hãy chọn giải pháp build phù hợp với mô hình bảo mật của nền tảng. Nếu bắt buộc dùng Docker daemon trên host, cần cô lập runner, giới hạn nguồn job, quyền truy cập socket và vòng đời máy. Không cấp quyền này cho pipeline xử lý PR không tin cậy.

### 5.4. Dọn dẹp sau job

Sau mỗi job hoặc lần chạy, cần xử lý:

- Workspace và file tạm.
- Credential và token tạm.
- Container, image và network tạm.
- Process nền hoặc service test.
- Volume và dữ liệu kiểm thử.
- Cache có thể chứa dữ liệu nhạy cảm.
- Log hoặc artifact tạm theo chính sách lưu giữ.

Với runner tạm thời, có thể hủy toàn bộ VM hoặc pod sau job. Với runner persistent, cần xác minh cleanup thành công và có cơ chế đưa máy vào trạng thái cách ly nếu cleanup thất bại.

## 6. Quản lý secret và danh tính trong môi trường thực thi

Runner thường là nơi secret được đưa vào job, vì vậy phải kiểm soát cách cấp, sử dụng và thu hồi.

### 6.1. Không lưu secret cố định trên máy chạy

Tránh lưu token, private key, mật khẩu hoặc file cấu hình bí mật trong image runner, workspace dùng chung hoặc biến môi trường cấp toàn cục. Secret nên được lấy từ secret manager khi job cần và chỉ cấp cho job có quyền.

Một quy trình an toàn có thể là:

1. Job được xác định danh tính bằng token của nền tảng.
2. Identity provider xác minh repository, ref, environment và workflow.
3. Secret manager cấp credential đúng phạm vi.
4. Job sử dụng credential trong thời gian ngắn.
5. Credential hết hạn hoặc bị thu hồi sau thời hạn.
6. Log và audit record ghi nhận danh tính, không ghi giá trị secret.

### 6.2. Secret theo môi trường

Tách secret development, test, staging và production. Job kiểm thử không cần quyền đọc secret production. Job deploy staging không cần quyền ghi production registry nếu không có mục đích đó.

Secret cần có người sở hữu, chính sách luân chuyển, thời hạn và quy trình thu hồi khi nghi ngờ bị lộ. Masking log là lớp bảo vệ bổ sung; không thay thế việc ngăn job không tin cậy tiếp cận secret.

### 6.3. Tránh credential tồn dư

Với runner persistent, cần đặc biệt chú ý credential được lưu trong:

- Credential helper của Git.
- File cấu hình cloud CLI.
- Environment variable toàn máy.
- Docker config.
- Package manager config.
- SSH agent hoặc file private key.
- Cache build và thư mục workspace.

Hãy dùng tài khoản riêng cho runner, thư mục HOME riêng cho job khi phù hợp và cleanup sau mỗi lần chạy. Nếu không thể chứng minh credential đã được xóa, nên tái tạo runner hoặc đưa máy ra khỏi pool trước khi nhận job tiếp theo.

## 7. Truy cập dependency, artifact và dịch vụ nội bộ

Mạng của runner thường cần kết nối đến nhiều hệ thống. Mỗi kết nối phải có mục đích, danh tính và quyền riêng.

### 7.1. Dependency registry

Khi tải dependency từ Internet, job có thể tiếp nhận package bị thay thế, nguồn không đáng tin hoặc phiên bản thay đổi ngoài dự kiến. Nên:

- Dùng lockfile hoặc khai báo phiên bản cụ thể.
- Ưu tiên registry hoặc proxy nội bộ đã được quản lý khi phù hợp.
- Xác minh checksum hoặc chữ ký nếu hệ sinh thái hỗ trợ.
- Giới hạn nguồn package được phép.
- Ghi lại dependency và toolchain trong metadata build.
- Không cấp quyền publish cho job chỉ cần tải package.

### 7.2. Artifact registry

Job publish artifact cần quyền ghi vào đúng repository hoặc namespace. Job triển khai chỉ cần quyền đọc artifact đã được phê duyệt. Tách quyền này giúp giảm nguy cơ một job test ghi đè artifact phát hành.

Nên sử dụng artifact bất biến hoặc digest để xác định nội dung. Tag dễ đọc giúp con người tìm kiếm nhưng có thể bị thay đổi nếu registry không khóa. Khi triển khai, hãy xác minh digest của artifact được tải đúng với digest đã được kiểm tra.

### 7.3. Dịch vụ test và dữ liệu

Runner integration có thể cần truy cập database, message broker, API giả lập hoặc dịch vụ test. Hãy dùng network segment và credential riêng cho môi trường này. Mỗi job nên có namespace hoặc dữ liệu độc lập để tránh xung đột.

Không dùng dữ liệu production thật chỉ vì nó tiện cho kiểm thử. Nếu cần dữ liệu gần thực tế, hãy tạo bản sao đã được xử lý theo chính sách dữ liệu và giới hạn người/job có quyền truy cập.

## 8. Kiến trúc tham khảo cho các nhóm runner

Sơ đồ dưới đây minh họa cách tách runner theo mức độ tin cậy và đích mạng:

~~~mermaid
flowchart TB
    CP["Control plane CI/CD"]
    DP["Git / dependency proxy"]
    subgraph U["Vùng mã chưa được tin cậy"]
      U1["Ephemeral runner cho PR/fork"]
    end
    subgraph B["Vùng build và kiểm thử"]
      B1["Runner build"]
      B2["Runner integration"]
      T["Dịch vụ test / dữ liệu giả lập"]
    end
    subgraph R["Vùng phát hành"]
      R1["Runner release"]
      AR["Artifact registry"]
    end
    subgraph D["Vùng triển khai"]
      D1["Runner deploy"]
      S["Staging"]
      P["Production"]
    end
    U1 -->|"Agent mở kênh outbound hai chiều"| CP
    B1 -->|"Agent mở kênh outbound hai chiều"| CP
    B2 -->|"Agent mở kênh outbound hai chiều"| CP
    R1 -->|"Agent mở kênh outbound hai chiều"| CP
    D1 -->|"Agent mở kênh outbound hai chiều"| CP
    U1 -->|"Chỉ đọc"| DP
    B1 --> DP
    B2 --> DP
    B1 --> AR
    B2 --> T
    B2 --> AR
    R1 --> AR
    D1 --> AR
    D1 --> S
    D1 --> P
~~~

Mô hình thực tế có thể gộp hoặc tách các vùng tùy quy mô. Tuy nhiên, runner xử lý mã chưa tin cậy không nên có đường truy cập đến secret production hoặc mạng quản trị. Runner release và deploy cần quyền riêng, có audit và được giới hạn vào artifact cùng môi trường được phép.

## 9. Ví dụ chính sách quyền và mạng ở mức khái niệm

Ví dụ sau minh họa cách mô tả chính sách. Đây không phải cú pháp chuẩn của một nền tảng CI/CD, firewall hoặc cloud cụ thể:

~~~yaml
runner_pools:
  untrusted_pr:
    lifecycle: ephemeral
    job_identity: read_only
    secrets:
      production: denied
      test: denied
    network:
      inbound: denied
      outbound:
        - ci_control_plane
        - git_read_endpoint
        - dependency_proxy

  integration:
    lifecycle: ephemeral
    job_identity: integration_test
    secrets:
      test_environment: scoped
    network:
      inbound: denied
      outbound:
        - ci_control_plane
        - git_read_endpoint
        - dependency_proxy
        - test_services

  release:
    lifecycle: isolated
    job_identity: release_publisher
    secrets:
      registry_write: short_lived
    network:
      inbound: denied
      outbound:
        - ci_control_plane
        - artifact_registry
        - identity_provider

  deployment:
    lifecycle: isolated
    job_identity: staging_deployer
    secrets:
      staging_deploy: short_lived
      production_deploy: approval_required
    network:
      inbound: denied
      outbound:
        - ci_control_plane
        - artifact_registry
        - approved_deployment_api
~~~

Khi triển khai, cần ánh xạ chính sách này sang quyền của runner, IAM role, firewall rule, security group, network policy và secret manager cụ thể. Đừng chỉ dựa vào tên pool; cần xác minh job thực tế không thể sử dụng credential hoặc kết nối ngoài phạm vi đã cấp.

## 10. Vận hành self-hosted runner

Self-hosted runner đem lại quyền kiểm soát về phần cứng, mạng nội bộ và cấu hình môi trường. Đồng thời, tổ chức phải tự chịu trách nhiệm về vòng đời máy, vá lỗi, giám sát và ứng phó sự cố.

Một quy trình vận hành nên bao gồm:

- **Đăng ký có kiểm soát:** chỉ máy được phê duyệt mới được đăng ký vào pool runner.
- **Image chuẩn hóa:** dùng image hệ điều hành và toolchain có phiên bản, được cập nhật định kỳ.
- **Cập nhật bảo mật:** vá hệ điều hành, agent CI, runtime, container engine và công cụ build.
- **Giới hạn quyền:** runner service chạy bằng tài khoản riêng, không dùng tài khoản quản trị hằng ngày.
- **Phân nhóm:** tách runner theo trust level, môi trường và nhu cầu mạng.
- **Giám sát:** theo dõi job bất thường, kết nối mạng, CPU, memory, disk và tiến trình kéo dài.
- **Cleanup:** xóa workspace, credential và tài nguyên tạm.
- **Thu hồi:** loại runner khỏi pool khi bị xâm nhập, lỗi cấu hình hoặc không còn được quản lý.
- **Kiểm tra định kỳ:** xác nhận nhãn runner, quyền, network rule và phiên bản phần mềm còn đúng.

Runner đã xử lý mã chưa tin cậy cần được xem là có thể đã bị thay đổi sau job. Nếu dùng persistent runner cho nhóm này, cần cơ chế tái tạo hoặc xác minh trạng thái trước khi nhận job tin cậy tiếp theo.

## 11. Giám sát và ghi nhận bằng chứng

Kiểm soát quyền và mạng cần có bằng chứng để điều tra. Các thông tin nên lưu gồm:

| Nhóm bằng chứng | Thông tin cần ghi |
|---|---|
| Danh tính runner | Runner ID, pool, image/version, host hoặc pod identity |
| Job | Pipeline run ID, job ID, repository, ref và commit SHA |
| Quyền | Role, scope và thời hạn credential được cấp |
| Secret | Secret reference hoặc audit event, không ghi giá trị |
| Mạng | Đích kết nối, giao thức, cổng, thời điểm và kết quả allow/deny |
| Tài nguyên | CPU, memory, disk, thời gian chờ và thời gian chạy |
| Cô lập | Lifecycle, container/VM identity và kết quả cleanup |
| Artifact | Tên, digest, registry và nguồn commit |
| Thao tác triển khai | Môi trường, danh tính thực hiện và kết quả |

Không nên ghi lại nội dung secret, private key hoặc payload nhạy cảm chỉ để phục vụ điều tra. Log mạng cần được bảo vệ theo chính sách dữ liệu và chỉ cho người có thẩm quyền truy cập.

Các cảnh báo hữu ích gồm:

- Runner cố truy cập endpoint không nằm trong allowlist.
- Job PR yêu cầu quyền hoặc secret ngoài chính sách.
- Runner persistent nhận job từ trust level khác.
- Credential tồn tại sau khi job kết thúc.
- Runner chưa vá lỗi hoặc agent quá cũ.
- Cleanup thất bại hoặc runner có process lạ.
- Một lần deploy dùng artifact digest không khớp.
- Job tạo lưu lượng outbound bất thường.

## 12. Xử lý sự cố quyền và mạng

Khi job không thể kết nối hoặc truy cập tài nguyên, hãy điều tra theo thứ tự để tránh mở rộng quyền quá mức.

### Job không checkout được repository

Kiểm tra event, ref, quyền đọc repository, token checkout, DNS, proxy và endpoint của Git. Xác định lỗi xác thực hay lỗi kết nối trước khi thay đổi firewall.

### Job không tải được dependency

Kiểm tra registry URL, lockfile, proxy, DNS, TLS certificate, credential đọc package và chính sách egress. Nếu dùng mirror nội bộ, xác nhận mirror đồng bộ và namespace đúng.

### Job không truy cập được dịch vụ test

Kiểm tra network segment, route, security group, network policy, DNS và cổng dịch vụ. Xác nhận dịch vụ đã sẵn sàng và runner đang dùng đúng môi trường test.

### Job deploy không truy cập được môi trường đích

Kiểm tra role, token, audience, thời hạn credential, endpoint API và rule mạng. Xác nhận job được phép deploy đến môi trường đó và artifact digest đúng với bản đã được duyệt.

### Job có quyền quá rộng

Kiểm tra danh tính host, role của job, token workflow, secret scope, group runner và network route. Thu hồi credential có nguy cơ bị lộ, thu hẹp quyền và tái tạo runner nếu không thể xác nhận máy còn sạch.

### Runner còn dữ liệu sau job

Kiểm tra workspace, volume, cache, container, process nền, file cấu hình và credential helper. Nếu cleanup không đáng tin cậy, đưa runner ra khỏi pool và tái tạo môi trường trước khi nhận job tiếp theo.

Không nên xử lý lỗi kết nối bằng cách mở outbound đến mọi địa chỉ hoặc cấp quyền quản trị cho job. Hãy tìm đúng endpoint và thao tác cần thiết, sau đó bổ sung rule có phạm vi hẹp và ghi lại lý do.

## 13. Tình huống mẫu: PR kiểm thử và release triển khai

Giả sử một nhóm dùng self-hosted runner để build dịch vụ web, chạy integration test và triển khai lên staging, production.

1. Pull request từ fork được đưa vào hàng đợi. Nó chạy trên ephemeral runner trong vùng mã chưa tin cậy, chỉ có quyền đọc source và truy cập dependency proxy. Runner không nhận secret production và không có route đến mạng quản trị.
2. Fast checks hoàn tất. Nếu cần integration test, pipeline tạo một runner hoặc job riêng trong network test, cấp credential test ngắn hạn và chỉ cho phép kết nối đến database cùng service giả lập cần thiết.
3. Sau khi pull request được review và hợp nhất, pipeline nhánh chính build artifact. Job build chỉ có quyền ghi vào vùng artifact ứng viên.
4. Artifact được lưu với commit SHA và digest. Job release xác minh metadata, chạy kiểm tra cần thiết và publish vào registry được bảo vệ.
5. Job deploy staging nhận danh tính ngắn hạn có quyền triển khai staging. Runner chỉ truy cập artifact registry và API của staging.
6. Sau khi staging đạt smoke test và điều kiện phát hành, job production chờ phê duyệt theo chính sách. Job nhận credential production trong thời gian ngắn và chỉ có route đến API triển khai production.
7. Sau khi deploy, pipeline xác minh phiên bản đang chạy, lưu digest, log và kết quả. Runner tạm cùng credential được thu hồi hoặc hủy.

Cách tổ chức này tạo ra các ranh giới rõ ràng: mã chưa tin cậy chỉ có quyền kiểm tra, job tích hợp chỉ truy cập mạng test, job publish chỉ ghi artifact, và job deploy chỉ tác động đến môi trường đã được cho phép.

## 14. Lộ trình thực hành

Có thể thực hành trên một repository mẫu theo các bước:

1. **Kiểm kê runner:** liệt kê runner host, pool, nhãn, hệ điều hành, tài khoản chạy service, lifecycle và các job đang sử dụng.
2. **Lập bản đồ quyền:** ghi lại repository, registry, secret, cloud role và môi trường mà từng nhóm job có thể truy cập.
3. **Lập bản đồ mạng:** liệt kê endpoint outbound và inbound cần thiết, giao thức, cổng, mục đích và chủ sở hữu.
4. **Tách trust level:** tạo nhóm runner hoặc job riêng cho PR chưa tin cậy, build nội bộ, integration, release và deploy.
5. **Giới hạn egress:** thử áp dụng allowlist hoặc proxy cho một nhóm runner, xác nhận checkout, dependency và test vẫn hoạt động.
6. **Loại bỏ ingress thừa:** đóng cổng không cần thiết, giữ kênh quản trị được xác thực và ghi log.
7. **Thay secret dài hạn:** chuyển sang secret manager hoặc workload identity ngắn hạn khi nền tảng hỗ trợ.
8. **Thử nghiệm cleanup:** chạy job tạo file, container và credential tạm; xác nhận chúng được xóa hoặc runner được hủy sau job.
9. **Diễn tập truy cập trái phép:** tạo một job test cố gắng truy cập endpoint ngoài allowlist trong môi trường an toàn; xác nhận kết nối bị chặn và có log.
10. **Đánh giá lại:** so sánh quyền, mạng và bằng chứng trước/sau, ghi nhận ngoại lệ cùng người chịu trách nhiệm.

### Tiêu chí hoàn thành

Người học có thể xem bài thực hành hoàn thành khi chứng minh được:

- Giải thích được vai trò của control plane, runner host và job process.
- Phân nhóm được runner theo mức độ tin cậy của mã nguồn và công việc.
- Phân biệt được quyền của host với quyền của job.
- Cấp được danh tính và credential theo nguyên tắc quyền tối thiểu.
- Lập được danh sách endpoint mạng cần thiết cho từng loại job.
- Thiết kế được egress, ingress và phân đoạn mạng phù hợp.
- Giải thích được giới hạn cô lập của container và khi nào cần VM hoặc runner tạm.
- Bảo vệ secret, registry và môi trường triển khai theo từng trust level.
- Thu thập được bằng chứng quyền, kết nối mạng và cleanup.
- Điều tra được lỗi kết nối mà không mở rộng quyền hoặc mạng quá mức.

## Kết luận

Runner là nơi mã nguồn thực sự được thực thi, vì vậy quyền của máy chạy và khả năng truy cập mạng là một phần cốt lõi của kiến trúc CI/CD. Runner cần có danh tính rõ ràng, quyền tối thiểu, ranh giới cô lập phù hợp và đường mạng chỉ đến các dịch vụ cần thiết. Mã chưa được tin cậy cần chạy trong môi trường có phạm vi ảnh hưởng nhỏ; job publish và deploy cần danh tính, credential và network path riêng.

Một thiết kế đáng tin cậy kết hợp phân nhóm runner, credential ngắn hạn, egress/ingress filtering, network segmentation, cleanup, giám sát và truy vết. Khi các kiểm soát này được thực hiện đồng bộ, pipeline có thể truy cập đúng tài nguyên để build, test và phát hành mà vẫn giới hạn được tác động của một job lỗi hoặc bị lạm dụng.

