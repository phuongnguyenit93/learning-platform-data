# Event Threat Detection và phát hiện hành vi bất thường

Một cuộc tấn công trên Google Cloud thường bắt đầu bằng những hành động trông có vẻ hợp lệ: một tài khoản đăng nhập, một service account gọi API, một quyền IAM được cấp hoặc một máy ảo kết nối tới một địa chỉ IP. Khi các hành động này xuất hiện riêng lẻ, chúng có thể khó nhận ra là nguy hiểm. Khi được đặt trong ngữ cảnh của người thực hiện, tài nguyên bị tác động, thời điểm và chuỗi hoạt động trước đó, chúng có thể cho thấy dấu hiệu xâm nhập.

Event Threat Detection (ETD) là dịch vụ phát hiện mối đe dọa dựa trên log của Security Command Center (SCC). Dịch vụ phân tích luồng log của Google Cloud và, khi SCC được kích hoạt ở cấp tổ chức, có thể phân tích thêm log Google Workspace. ETD kết hợp quy tắc phát hiện, threat intelligence, chỉ báo xâm nhập, phân tích theo cửa sổ thời gian, machine learning và phát hiện bất thường để tạo finding gần thời gian thực.

Bài học này tập trung vào cách ETD hoạt động, những loại hành vi có thể được phát hiện, cách chuẩn bị log, đọc và điều tra finding, cũng như cách đưa cảnh báo vào quy trình phản ứng sự cố.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Mô tả vai trò của Event Threat Detection trong Security Command Center.
- Giải thích cách log, chỉ báo xâm nhập và phân tích hành vi được kết hợp để phát hiện mối đe dọa.
- Phân biệt Event Threat Detection với Anomaly Detection và các dịch vụ phát hiện runtime khác.
- Xác định tier, phạm vi kích hoạt, quyền IAM và nguồn log cần thiết.
- Đọc finding, đánh giá mức độ nghiêm trọng và điều tra hoạt động liên quan.
- Thiết lập quy trình chuyển finding tới Pub/Sub, Cloud Logging hoặc hệ thống xử lý sự cố.
- Thiết kế quy tắc phát hiện riêng bằng custom modules khi có mẫu được hỗ trợ.

## 1. Event Threat Detection là gì?

Event Threat Detection là dịch vụ tích hợp trong Security Command Center, được cung cấp ở tier Premium. Dịch vụ liên tục theo dõi luồng Cloud Logging của tổ chức hoặc project trong phạm vi kích hoạt và tìm những sự kiện có dấu hiệu đe dọa. Khi SCC được kích hoạt ở cấp tổ chức, ETD có thể theo dõi thêm log Google Workspace, gồm hoạt động đăng nhập và thao tác trên Admin Console.

ETD là một cơ chế phát hiện dựa trên sự kiện và log. Dịch vụ không yêu cầu cài agent lên mọi máy ảo để phân tích từng tiến trình đang chạy. Nó sử dụng dữ liệu log được các dịch vụ tạo ra, áp dụng logic phát hiện và ghi kết quả thành finding trong Security Command Center.

Các đặc điểm chính:

- **Gần thời gian thực:** ETD tiếp nhận log khi chúng xuất hiện và xử lý theo các detector đã bật. Độ trễ phát hiện thường dưới 15 phút tính từ lúc log được ghi đến khi finding có trong SCC.
- **Phân tích nhiều nguồn:** có thể sử dụng Cloud Audit Logs, log mạng, log xác thực trên máy ảo, log dịch vụ cơ sở dữ liệu và log Google Workspace tùy detector.
- **Kết hợp nhiều kỹ thuật:** quy tắc, chỉ báo xâm nhập (IoC), threat intelligence, profiling theo cửa sổ thời gian, machine learning và anomaly detection.
- **Tập trung kết quả:** finding được hiển thị trong SCC, nơi đội bảo mật có thể lọc, điều tra, đánh dấu và chuyển tiếp tới quy trình xử lý.
- **Có thể mở rộng:** custom modules cho phép tổ chức đặt một số tham số phát hiện, mức độ nghiêm trọng và hướng dẫn khắc phục riêng.

ETD tạo cảnh báo để con người hoặc hệ thống phản ứng. Việc tạo finding không tự động có nghĩa là tài khoản đã bị khóa, IP đã bị chặn hoặc máy ảo đã bị cách ly. Các hành động ngăn chặn cần được thực hiện theo runbook hoặc hệ thống phản ứng được tổ chức cấu hình.

### Phạm vi sản phẩm và tier

Theo tài liệu Security Command Center hiện hành:

| Tier | Event Threat Detection |
|---|---|
| Standard | Không bao gồm ETD |
| Premium | Có ETD |
| Enterprise (Deprecated) | Có ETD; tier này đang trong lộ trình ngừng cung cấp |

Security Command Center Premium có thể được kích hoạt ở cấp project hoặc organization. Phạm vi project phù hợp để thử nghiệm một phần năng lực phát hiện. Tuy nhiên, một số log và detector chỉ hoạt động khi kích hoạt ở cấp organization; log Google Workspace và một số detector tổ chức là ví dụ. Vì vậy, nếu yêu cầu giám sát toàn doanh nghiệp, cần thiết kế phạm vi organization-level activation và kiểm tra từng loại log.

Tài liệu Google Cloud thông báo Enterprise sẽ ngừng hoạt động vào ngày 21-05-2027; tổ chức đang dùng Enterprise sẽ tự động chuyển sang Premium vào hoặc sau ngày đó. Khi lập kế hoạch dài hạn, nên dùng Premium làm cơ sở cho kiến trúc ETD mới và xác nhận điều khoản dịch vụ hiện hành.

## 2. Cách ETD phát hiện hành vi bất thường

ETD nhận log từ các dịch vụ, sau đó phân tích sự kiện dựa trên nội dung log, ngữ cảnh tài nguyên và tín hiệu đe dọa. Các kỹ thuật được Google mô tả gồm:

- **Rule-based detection:** kiểm tra một chuỗi sự kiện hoặc thuộc tính có khớp mẫu nguy hiểm đã biết hay không.
- **Indicator of Compromise (IoC):** so sánh domain, IP hoặc dấu hiệu kỹ thuật trong log với dữ liệu threat intelligence.
- **Sliding-window profiling:** xem xét hoạt động trong một khoảng thời gian để nhận ra chuỗi hoặc tần suất bất thường.
- **Machine learning và anomaly detection:** nhận diện hoạt động khác với mẫu thường thấy hoặc có đặc điểm đáng ngờ theo logic của detector.

Không phải mọi detector đều sử dụng tất cả kỹ thuật trên. Cách phát hiện cụ thể phụ thuộc vào loại detector, nguồn log và quy tắc đang được Google duy trì.

Ví dụ, một lần đăng nhập từ một IP lạ chưa chắc là tấn công. Nhưng nếu cùng danh tính đó vừa đăng nhập bất thường, vừa tạo key cho service account đã lâu không hoạt động, rồi dùng key để truy cập dữ liệu nhạy cảm, chuỗi sự kiện có thể đáng chú ý hơn nhiều. ETD có thể phát hiện các hành vi hoặc tổ hợp sự kiện được detector hỗ trợ và ghi finding để đội bảo mật điều tra.

### Luồng xử lý tổng quát

~~~mermaid
flowchart TD
    A[Người dùng, service account và workload] --> B[Cloud Audit Logs]
    A --> C[Cloud DNS, NAT, VPC Flow và auth logs]
    A --> D[Google Workspace logs]
    B --> E[Cloud Logging streams]
    C --> E
    D --> F[Workspace logging stream]
    E --> G[Event Threat Detection]
    F --> G
    G --> H[Rules, IoC, profiling, ML và anomaly detection]
    H --> I{Có dấu hiệu đe dọa?}
    I -->|Không| J[Tiếp tục theo dõi]
    I -->|Có| K[Finding trong Security Command Center]
    K --> L[Phân loại và điều tra]
    L --> M[Khắc phục hoặc chuyển cấp]
    K --> N[Pub/Sub, Cloud Logging hoặc công cụ SOC]
~~~

Quá trình này giúp tập trung sự kiện bảo mật từ nhiều project. Đội vận hành không phải tự viết một truy vấn riêng cho từng loại hành vi trước khi nhận được cảnh báo cơ bản.

### Ví dụ về nhóm detector

| Nhóm hành vi | Ví dụ detector hoặc dấu hiệu | Điều cần xác minh |
|---|---|---|
| Truy cập ban đầu | Sử dụng service account key đã bị rò rỉ; hoạt động từ tài khoản bất thường | Ai sở hữu danh tính, key nào được dùng và phạm vi truy cập |
| Leo thang đặc quyền | Cấp quyền nhạy cảm cho thành viên bên ngoài; cấp quyền impersonation cho service account | Người cấp quyền, role được cấp, cấp ở organization/folder/project |
| Duy trì quyền truy cập | Tắt xác thực hai bước; tạo key cho service account không hoạt động | Có thay đổi được phê duyệt hay không |
| Mã độc và command-and-control | Truy cập domain/IP đã biết là độc hại, DNS tunneling, cryptomining | VM, workload, tiến trình và kết nối mạng liên quan |
| Tấn công xác thực | SSH brute force dẫn tới đăng nhập thành công; đăng nhập cơ sở dữ liệu từ proxy ẩn danh | IP nguồn, tài khoản, thời điểm và các lần đăng nhập liên tiếp |
| Truy cập dữ liệu | Truy cập hoặc xuất dữ liệu bất thường trong dịch vụ được hỗ trợ | Dataset/bucket/database, danh tính và lượng dữ liệu |
| Tác động tới khả năng phục hồi | Xóa backup, backup plan hoặc thay đổi chính sách bảo vệ | Người thực hiện, tài nguyên bị ảnh hưởng và khả năng khôi phục |

Tên detector, trạng thái khả dụng và mức độ nghiêm trọng mặc định có thể thay đổi theo thời gian. Một số detector được đánh dấu Preview hoặc tạm thời không khả dụng. Khi thiết kế kiểm soát, hãy kiểm tra danh sách Event Threat Detection rules hiện hành thay vì cố định toàn bộ danh sách detector vào runbook.

## 3. Phân biệt Event Threat Detection và Anomaly Detection

Tên gọi gần nhau nhưng hai khả năng này có nguồn tín hiệu và phạm vi khác nhau.

**Event Threat Detection** sử dụng log được tạo bên trong môi trường Google Cloud và, ở cấp tổ chức, log Google Workspace. Dịch vụ tìm các hành vi tấn công hoặc sự kiện đáng ngờ như cấp quyền bất thường, dùng key rò rỉ, truy cập domain độc hại hoặc hành vi xác thực nguy hiểm. ETD thuộc SCC Premium.

**Anomaly Detection** là một khả năng riêng trong Security Command Center. Dịch vụ sử dụng tín hiệu hành vi từ bên ngoài hệ thống để phát hiện một số bất thường liên quan tới service account, ví dụ thông tin xác thực của service account bị phát hiện rò rỉ trên Internet. Một ví dụ là GitHub thông báo credential được dùng trong commit có vẻ là private key của service account GCP. Finding có thể có category là account_has_leaked_credentials và mức Critical. Anomaly Detection có phạm vi tier rộng hơn ETD theo bảng tier hiện hành.

| Tiêu chí | Event Threat Detection | Anomaly Detection |
|---|---|---|
| Nguồn tín hiệu chính | Log nội bộ từ Cloud Logging và Google Workspace | Tín hiệu hành vi bên ngoài hệ thống, ví dụ thông tin credential bị lộ |
| Mục tiêu | Phát hiện nhiều dạng hoạt động đe dọa trong log | Phát hiện một số bất thường liên quan đến tài khoản và credential |
| Ví dụ | IAM grant bất thường, domain độc hại, SSH brute force, truy cập dữ liệu | Service account key bị phát hiện công khai |
| Phạm vi tier | Premium và Enterprise (Deprecated) | Standard-legacy, Standard, Premium và Enterprise (Deprecated), theo bảng tier hiện hành |
| Kết quả | Finding trong Security Command Center | Finding trong Security Command Center |

ETD cũng sử dụng anomaly detection như một kỹ thuật trong một số detector. Điều này không làm cho ETD và dịch vụ Anomaly Detection trở thành cùng một dịch vụ.

Ngoài ra, Security Command Center có các dịch vụ khác với mục tiêu riêng:

- **Sensitive Actions Service** phát hiện những thao tác quản trị nhạy cảm có thể gây hại cho tổ chức.
- **Container Threat Detection** phân tích hoạt động runtime ở cấp container/node theo phạm vi hỗ trợ.
- **Virtual Machine Threat Detection** tìm ứng dụng độc hại trên máy ảo.
- **Cloud Run Threat Detection** phát hiện một số tấn công runtime trên Cloud Run.

Một kiến trúc bảo mật hoàn chỉnh có thể kết hợp nhiều dịch vụ này. ETD là lớp phát hiện từ log; các dịch vụ runtime bổ sung tín hiệu mà log sự kiện quản trị không thể quan sát đầy đủ.

## 4. Nguồn log và điều kiện để detector hoạt động

Chất lượng phát hiện phụ thuộc trực tiếp vào nguồn log. Bật ETD không đồng nghĩa mọi detector sẽ có đầy đủ dữ liệu đầu vào.

### Cloud Audit Logs

Cloud Audit Logs ghi lại hoạt động trên tài nguyên và API:

- **Admin Activity audit logs:** ghi lại thao tác thay đổi cấu hình hoặc metadata. Loại log này luôn được ghi và không thể tắt.
- **Data Access audit logs:** ghi lại thao tác đọc dữ liệu hoặc truy cập dữ liệu. Nhiều dịch vụ không bật loại log này mặc định; tổ chức phải chủ động cấu hình nếu muốn phát hiện các hành vi cần dữ liệu đó.
- **System Event audit logs:** ghi lại hành động hệ thống do Google Cloud thực hiện thay mặt người dùng.

Ví dụ, detector phát hiện cấp quyền IAM có thể sử dụng Admin Activity logs. Detector liên quan đến đọc dữ liệu, truy cập database hoặc sử dụng credential có thể yêu cầu Data Access logs của dịch vụ tương ứng.

Không nên bật Data Access logs cho mọi dịch vụ một cách thiếu chọn lọc. Hãy xác định dịch vụ đang sử dụng, mối đe dọa cần phát hiện và log thực sự được detector tiêu thụ. Nếu một log không có trong danh sách log được ETD hỗ trợ, việc bật log đó cũng không làm detector tự động phân tích nó.

### Log mạng

ETD có thể dùng các nguồn sau cho một số detector mạng:

- Cloud DNS logging.
- Cloud NAT logging.
- Firewall Rules logging.
- VPC Flow Logs.

Đối với phát hiện mã độc dựa trên kết nối mạng, Cloud DNS logging thường đã cung cấp thông tin hữu ích về domain được truy vấn. Nếu cần thêm dữ liệu về luồng kết nối, có thể bật VPC Flow Logs hoặc dùng Cloud NAT/Firewall Rules logging khi phù hợp.

Không cần bật đồng thời Cloud NAT logging, Firewall Rules logging và VPC Flow Logs chỉ để có nhiều nguồn log hơn cho cùng một nhóm detector. Chọn theo yêu cầu điều tra và chi phí.

Một chi tiết vận hành quan trọng: ETD có thể phân tích một luồng VPC Flow Logs nội bộ ngay cả khi tổ chức chưa bật VPC Flow Logs. Tuy nhiên, nếu muốn mở liên kết từ finding sang Logs Explorer và Flow Analyzer để điều tra sâu, cần bật VPC Flow Logs. Khi bật sau thời điểm finding đã được tạo, các finding cũ không tự có lại liên kết điều tra đó.

VPC Flow Logs có thể tạo chi phí. Google khuyến nghị cân nhắc tăng aggregation interval lên 15 phút và giảm sample rate xuống khoảng 5%–10% để kiểm soát chi phí; tỷ lệ lấy mẫu thấp hơn có thể làm giảm khả năng quan sát một số kết nối.

### Log Google Workspace

Khi SCC Premium được kích hoạt ở cấp organization, ETD có thể sử dụng log Google Workspace để phát hiện các hoạt động như đăng nhập đáng ngờ, thay đổi xác thực hai bước hoặc thao tác quản trị. Một số detector Workspace không khả dụng khi chỉ kích hoạt SCC ở cấp project.

### Chọn log theo detector

| Nguồn log | Ví dụ mối đe dọa | Việc cần kiểm tra |
|---|---|---|
| Admin Activity audit logs | Thay đổi IAM, tắt API, thay đổi cấu hình bảo mật | Luôn được ghi; xác minh detector đang bật |
| Data Access audit logs | Truy cập dữ liệu hoặc hành vi bất thường trong dịch vụ | Bật đúng dịch vụ và loại log cần thiết |
| Cloud DNS logs | Kết nối domain độc hại hoặc domain phục vụ cryptomining | Bật DNS query logging cho VPC liên quan |
| VPC Flow Logs / NAT / Firewall logs | Kết nối tới IP đáng ngờ | Chọn nguồn phù hợp, cân nhắc sampling và chi phí |
| VM auth logs | SSH brute force | Cài Ops Agent hoặc Logging agent phù hợp để gửi auth log |
| Google Workspace logs | Đăng nhập và thao tác quản trị Workspace đáng ngờ | Kích hoạt SCC ở cấp tổ chức và cấp quyền phù hợp |

Một số nguồn log và detector chỉ hoạt động ở cấp organization. Nếu SCC chỉ được kích hoạt ở cấp project, ETD sẽ không quét các nguồn log chỉ hỗ trợ cấp organization và không tạo finding từ các nguồn đó. Hãy kiểm tra cột phạm vi trong tài liệu log types and activation requirements.

### Chi phí và khả năng lưu trữ

Theo tài liệu Google Cloud, việc ETD quét log không phát sinh phí quét bổ sung. Tuy nhiên, Cloud Logging có thể tính phí ingestion và storage tùy lượng log tổ chức tạo ra. VPC Flow Logs, Cloud DNS, Data Access logs và các nguồn log có khối lượng lớn cần được đánh giá trước khi bật trên toàn tổ chức.

SCC Premium cũng có cấu trúc giá riêng. Khi thiết kế, cần tính tổng chi phí của tier SCC, Cloud Logging, lưu trữ log, Pub/Sub và hệ thống xử lý cảnh báo. Đặt thời gian lưu log phù hợp yêu cầu điều tra, kiểm toán và chính sách dữ liệu.

## 5. Kích hoạt và cấu hình Event Threat Detection

Quy trình cấu hình nên bắt đầu từ phạm vi bảo vệ và nguồn log cần thiết.

### Bước 1: Xác định phạm vi Security Command Center

Chọn kích hoạt SCC Premium ở cấp project nếu chỉ cần kiểm thử hoặc bảo vệ một project. Chọn cấp organization nếu cần quan sát nhiều project, log Workspace và các detector chỉ có phạm vi tổ chức.

Trước khi kích hoạt, cần chuẩn bị:

- Organization hoặc project cần bảo vệ.
- Quyền IAM để kích hoạt và quản lý dịch vụ.
- Tier và phương thức billing phù hợp.
- Yêu cầu data residency, nếu tổ chức sử dụng.
- Danh sách log và dịch vụ cần bảo vệ.

### Bước 2: Kiểm tra trạng thái dịch vụ

Trong Google Cloud Console:

1. Mở Security Command Center.
2. Chọn đúng organization hoặc project.
3. Mở Settings và vào Services.
4. Tìm Event Threat Detection.
5. Xác minh dịch vụ đang ở trạng thái Enable hoặc Inherit theo chính sách tổ chức.
6. Mở phần Modules để xem các detector có thể cấu hình và trạng thái của chúng.

ETD thường được bật mặc định khi kích hoạt tier phù hợp, nhưng trạng thái thực tế có thể đã bị thay đổi bởi quản trị viên hoặc cấu hình kế thừa. Hãy xác minh trước khi dựa vào finding để kết luận hệ thống đã được giám sát.

### Bước 3: Cấp quyền IAM

Các quyền được phân tách theo công việc:

| Công việc | Vai trò hoặc quyền tham khảo |
|---|---|
| Kích hoạt hoặc thay đổi dịch vụ SCC | Security Center Admin (roles/securitycenter.admin), Security Center Settings Admin (roles/securitycenter.settingsAdmin) hoặc Security Center Settings Editor (roles/securitycenter.settingsEditor) |
| Xem finding | Security Center Findings Viewer (roles/securitycenter.findingsViewer) |
| Cập nhật finding | Security Center Findings Editor (roles/securitycenter.findingsEditor) |
| Quản lý custom modules | Event Threat Detection Custom Modules Editor (roles/securitycentermanagement.etdCustomModulesEditor) hoặc vai trò quản trị tương ứng |

Cấp role ở phạm vi hẹp nhất đáp ứng công việc. Người điều tra thường chỉ cần quyền xem finding và log; không cần quyền quản trị toàn bộ dịch vụ bảo mật. Service agent của SCC được tạo và cấp quyền cần thiết khi kích hoạt tier. Nếu tổ chức dùng VPC Service Controls, có thể cần cấu hình ingress/egress để service agent truy cập dịch vụ trong perimeter theo hướng dẫn của SCC.

### Bước 4: Bật log cần thiết

Dựa vào detector và dịch vụ thực tế:

- Bật Data Access audit logs cho các dịch vụ mà tổ chức cần giám sát hành vi đọc dữ liệu.
- Bật Cloud DNS logging nếu muốn phát hiện malware qua domain.
- Bật một nguồn log mạng bổ sung như VPC Flow Logs, Cloud NAT hoặc Firewall Rules nếu cần dữ liệu điều tra tương ứng.
- Cấu hình auth log trên VM nếu cần phát hiện SSH brute force.
- Xác nhận log Google Workspace có thể được ETD sử dụng khi phạm vi kích hoạt là organization.

Sau khi thay đổi cấu hình log, chờ dữ liệu mới xuất hiện và xác minh bằng cách kiểm tra log thực tế. ETD không thể phân tích sự kiện đã bị loại bỏ trước khi được ghi nhận.

### Bước 5: Xác minh detector và finding

Mở Security Command Center > Findings, chọn đúng organization hoặc project. Trong Quick filters, lọc Source display name:

- Event Threat Detection: finding từ detector có sẵn.
- Event Threat Detection Custom Modules: finding từ custom module.

Khi mở finding, kiểm tra thời điểm sự kiện, nguồn dữ liệu, severity, hành động được phát hiện và principal thực hiện hành động. Nếu có log export, có thể mở Logs Explorer để xem bản ghi liên quan.

## 6. Đọc và điều tra một finding

Finding là bản ghi mô tả vấn đề bảo mật được dịch vụ phát hiện. Finding không phải log thô; nó là kết quả đánh giá có cấu trúc, gắn với một tài nguyên hoặc một phạm vi trong hệ thống.

Một finding thường có các thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| category | Tên nhóm hoặc loại phát hiện, ví dụ Malware: Bad Domain |
| severity | Mức độ nghiêm trọng: LOW, MEDIUM, HIGH hoặc CRITICAL |
| state | Trạng thái xử lý, thường là ACTIVE hoặc INACTIVE |
| eventTime | Thời điểm sự kiện hoặc lần cập nhật finding |
| createTime | Thời điểm finding được tạo |
| resourceName | Tên đầy đủ của tài nguyên liên quan |
| source | Nguồn phát hiện, ví dụ Event Threat Detection |
| sourceProperties | Thuộc tính riêng của detector, có thể chứa IP, domain, method hoặc thông tin ngữ cảnh |
| principal email | Danh tính người dùng hoặc service account thực hiện hành động, nếu có trong finding |

Các trường sourceProperties phụ thuộc vào từng detector và không được chuẩn hóa giống nhau giữa tất cả nguồn finding. Khi tích hợp tự động, nên dựa vào các trường chuẩn của finding và đọc schema của từng detector trước khi phụ thuộc vào một thuộc tính riêng.

### Quy trình điều tra

**1. Xác nhận phạm vi và thời gian**

Ghi lại category, severity, eventTime, resourceName, principal email, source và các thuộc tính liên quan. Xác định project, folder hoặc organization bị ảnh hưởng.

**2. Mở log gốc**

Tìm log tương ứng trong Cloud Logging. Kiểm tra method/API, kết quả, IP nguồn, user agent, danh tính xác thực và tài nguyên đích. Một finding về IAM cần kiểm tra ai đã thay đổi policy, role nào được cấp và policy nằm ở cấp nào.

**3. So sánh với hoạt động hợp lệ**

Đối chiếu với change request, lịch phát hành, công việc quản trị, automation và lịch trực. Một thao tác tạo key hoặc thay đổi IAM có thể hợp lệ nếu được thực hiện bởi pipeline đã phê duyệt. Tuy nhiên, phải xác minh danh tính và phạm vi thay đổi, không chỉ dựa trên việc có ticket.

**4. Tìm hoạt động liên quan**

Tìm các finding khác có cùng principal, IP, service account, project hoặc tài nguyên. Với cùng một principal, có thể lọc các finding và log liên quan để xây dựng timeline. Nếu phát hiện nhiều hành động bất thường nối tiếp nhau, nâng mức ưu tiên điều tra.

**5. Đánh giá và phân loại**

Xác định finding là sự cố đã xác nhận, hoạt động hợp lệ, cảnh báo cần theo dõi thêm hay false positive. Ghi lại bằng chứng, người xác minh, lý do phân loại và hành động tiếp theo.

**6. Phản ứng và khôi phục**

Tùy sự cố, có thể thu hồi quyền IAM, vô hiệu hóa hoặc xoay vòng credential, chặn domain/IP, cô lập VM, thu hồi session hoặc khôi phục cấu hình. Trước khi thực hiện hành động ảnh hưởng tới production, hãy lưu bằng chứng cần thiết, xác định tác động và làm theo quy trình phê duyệt sự cố của tổ chức.

**7. Cập nhật finding và runbook**

Đặt state thành INACTIVE khi vấn đề đã được xử lý. Có thể mute finding khi đã đánh giá và muốn loại khỏi danh sách đang cần xử lý. Mute không sửa tài nguyên hoặc ngăn hành vi tấn công; nó chỉ thay đổi cách finding được hiển thị và quản lý. Ghi lại lý do mute để người khác hiểu quyết định.

### Ví dụ: phát hiện cấp quyền IAM bất thường

Một thành viên bên ngoài tổ chức được cấp role nhạy cảm trong project. Detector có thể tạo finding thuộc nhóm Privilege Escalation hoặc IAM anomalous grant.

Người điều tra nên:

1. Xem principal đã cấp quyền và principal nhận quyền.
2. Xác định role được cấp, ví dụ Owner, Editor hoặc một role cho phép impersonate service account.
3. Kiểm tra policy được thay đổi ở project, folder hay organization.
4. Đối chiếu ticket hoặc thay đổi được phê duyệt.
5. Nếu không hợp lệ, thu hồi binding, rà soát hoạt động của principal nhận quyền và kiểm tra các service account/key liên quan.
6. Tìm các hành động API tiếp theo từ cùng danh tính và ghi lại kết quả điều tra.

Một finding có severity HIGH không tự chứng minh rằng kẻ tấn công đã chiếm quyền. Severity giúp ưu tiên xử lý; kết luận sự cố phải dựa trên log, tài nguyên, danh tính và bằng chứng bổ sung.

## 7. Tìm finding trong Cloud Logging và chuyển tiếp cảnh báo

Security Command Center là nơi xem và quản lý finding. Khi cần tích hợp với hệ thống giám sát hoặc quy trình phản ứng, có thể dùng continuous export.

### Xem finding đã export sang Cloud Logging

Nếu SCC Premium được kích hoạt ở cấp organization và Continuous Exports đã được cấu hình, finding của ETD có thể được ghi vào Cloud Logging. Các log này sử dụng resource type là threat_detector.

Ví dụ truy vấn trong Logs Explorer:

~~~text
resource.type="threat_detector"
~~~

Có thể lọc thêm theo detector hoặc thời gian để thu hẹp kết quả. Việc export finding sang Cloud Logging có thể phát sinh chi phí ingestion và storage, phụ thuộc lượng finding.

### Gửi finding tới Pub/Sub

Continuous Exports cho Pub/Sub cho phép chuyển finding mới tới topic để hệ thống khác xử lý. Quy trình tổng quát:

1. Tạo Pub/Sub topic và subscription.
2. Mở Security Command Center > Findings.
3. Chọn organization, folder hoặc project.
4. Lọc finding theo category, severity, state hoặc nguồn phát hiện.
5. Chọn Export > Continuous > Pub/Sub.
6. Chọn project và topic đích, đặt tên export rồi lưu.
7. Tạo subscription và kiểm tra thông điệp được nhận.

Có thể đặt bộ lọc chỉ gửi finding đang ACTIVE hoặc chỉ gửi nhóm detector cần xử lý nhanh. SCC tạo service account thông báo và cấp role cần thiết để publish vào topic. Nếu bật data residency, continuous export phải được tạo ở cùng location SCC với finding cần export; cần kiểm tra thêm chính sách lưu trữ thông điệp Pub/Sub.

Một kiến trúc phản ứng tham khảo:

~~~mermaid
flowchart LR
    A[Event Threat Detection] --> B[Security Command Center finding]
    B --> C[Continuous export]
    C --> D[Pub/Sub topic]
    D --> E[Cloud Run service]
    E --> F[Enrichment: IAM, Asset, log context]
    F --> G{Severity và điều kiện}
    G -->|Cần xử lý| H[Ticket hoặc SOC queue]
    G -->|Đủ điều kiện tự động| I[Runbook phản ứng có kiểm soát]
    G -->|Chưa rõ| J[Security analyst review]
~~~

Không nên tự động xóa tài khoản, thu hồi mọi quyền hoặc tắt VM chỉ dựa vào một finding. Tự động hóa nên bắt đầu bằng enrich context, tạo ticket, thông báo on-call và đề xuất hành động. Chỉ tự động ngăn chặn khi đã xác định điều kiện, phạm vi và phương án rollback.

## 8. Custom modules cho yêu cầu riêng

Built-in detectors bao phủ nhiều kiểu tấn công phổ biến. Tuy nhiên, tổ chức có thể có quy tắc riêng, ví dụ chỉ cho phép workload kết nối tới một danh sách IP nhất định hoặc chỉ cho phép tạo tài nguyên trong một số region.

Event Threat Detection custom modules cho phép cấu hình thêm detector dựa trên template được hỗ trợ. Một module có thể định nghĩa:

- Tham số dùng để đánh giá log.
- Mức severity cho finding.
- Mô tả sự kiện bị phát hiện.
- Khuyến nghị xử lý để đưa vào next steps của finding.

Ví dụ, module Configurable Bad IP có thể phát hiện kết nối tới IP trong danh sách do tổ chức duy trì. Template JSON minh họa:

~~~json
{
  "metadata": {
    "severity": "HIGH",
    "description": "Workload connected to a restricted IP address",
    "recommendation": "Verify the workload owner and investigate the network connection"
  },
  "ips": [
    "203.0.113.10",
    "198.51.100.20"
  ]
}
~~~

Hai địa chỉ trong ví dụ thuộc dải tài liệu dành riêng, chỉ dùng minh họa. Khi cấu hình thật, thay bằng IP đã được đội bảo mật xác minh và quản lý.

Custom modules chạy cùng built-in detectors. Các module được bật xử lý log mới theo chế độ real-time. Module có thể được tạo ở cấp organization, folder hoặc project; module ở cấp cha có thể được kế thừa xuống cấp con theo cấu hình. Quyền quản lý module cần được giới hạn cho nhóm bảo mật có trách nhiệm.

Không phải mọi kiểu logic đều có template custom module. Nếu cần mô hình phát hiện không được hỗ trợ, có thể export log sang BigQuery rồi xây dựng truy vấn SQL định kỳ hoặc quy trình phân tích riêng. Tránh tạo quá nhiều quy tắc trùng lặp; mỗi module nên có owner, mục tiêu, nguồn log, cách kiểm thử và hướng dẫn xử lý rõ ràng.

## 9. Thực hành: kiểm tra ETD bằng detector Malware: Bad Domain

Bài thực hành sử dụng domain kiểm thử chính thức của Google để xác minh luồng log DNS và finding. Thực hiện trong project thử nghiệm riêng, có quyền kiểm soát và không chứa dữ liệu production.

### Chuẩn bị

- SCC Premium đã được kích hoạt cho project thử nghiệm hoặc organization.
- Event Threat Detection đang Enable.
- Một VPC và một VM dùng cho bài lab.
- Cloud DNS query logging được bật cho VPC.
- Người thực hiện có quyền tạo VM và cấu hình DNS server policy.

### Bước 1: Bật DNS query logging

Trong Google Cloud Console, mở Cloud DNS > DNS server policies. Tạo hoặc chỉnh sửa policy áp dụng cho VPC của VM, bật logging và lưu cấu hình. Xác nhận project của VM nằm trong phạm vi ETD.

### Bước 2: Tạo VM thử nghiệm

Tạo một VM nhỏ trong VPC đã cấu hình DNS logging. Không dùng VM production hoặc VM có dữ liệu nhạy cảm. Xác nhận VM có thể truy cập DNS và log truy vấn được ghi nhận.

### Bước 3: Gửi truy vấn tới domain kiểm thử

Mở terminal trên VM và thực hiện:

~~~bash
curl etd-malware-trigger.goog
~~~

Domain trên là domain kiểm thử được tài liệu Google Cloud chỉ định cho detector Malware: Bad Domain. Đây không phải domain để dùng trong kiểm tra website thông thường.

### Bước 4: Kiểm tra finding

Mở Security Command Center > Findings, lọc Source display name là Event Threat Detection. Tìm finding Malware: Bad Domain và mở chi tiết.

Kiểm tra:

- Category hoặc detector tương ứng.
- Event time và project/resource liên quan.
- Domain trong source properties.
- Severity và nguồn log.
- Log DNS gốc trong Cloud Logging.

Độ trễ phát hiện thường dưới 15 phút từ lúc log được ghi. Nếu không có finding, kiểm tra lần lượt: ETD đã Enable chưa, project có nằm trong phạm vi kích hoạt không, DNS logging có áp dụng cho VPC không, log có được ghi nhận không và detector có yêu cầu nguồn log nào khác không.

### Bước 5: Dọn dẹp

Sau khi xác minh:

- Xóa VM thử nghiệm.
- Xóa hoặc điều chỉnh DNS server policy nếu chỉ dùng cho bài lab.
- Tắt log thử nghiệm nếu không còn nhu cầu.
- Lưu ảnh chụp finding và ghi lại thời gian phát hiện.
- Xác nhận không có tài nguyên hoặc cấu hình thử nghiệm còn tồn tại.

Không sử dụng quy trình kiểm thử này trên production. Nếu muốn thử detector IAM Anomalous Grant hoặc SSH Brute Force, hãy làm theo hướng dẫn kiểm thử chính thức trong một môi trường riêng biệt và xóa quyền/tài nguyên thử nghiệm ngay sau khi xác minh.

## 10. Giới hạn và lỗi cấu hình thường gặp

| Tình huống | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy finding nào | ETD bị disable, sai tier hoặc project không nằm trong phạm vi | Kiểm tra tier, scope và Services settings |
| Không phát hiện hành vi cần theo dõi | Detector yêu cầu log chưa được bật | Đối chiếu rule với log types and activation requirements |
| Không có finding từ Google Workspace | SCC chỉ được kích hoạt ở project-level | Đánh giá organization-level activation |
| Không thấy log Data Access | Data Access audit logs chưa bật cho dịch vụ | Cấu hình audit logs theo dịch vụ và phạm vi cần thiết |
| Không có liên kết Flow Analyzer từ finding | VPC Flow Logs chưa bật khi finding được tạo | Bật VPC Flow Logs để hỗ trợ điều tra các finding tiếp theo |
| Finding xuất hiện chậm | Độ trễ ingest hoặc detector; log chưa tới Cloud Logging | Kiểm tra timestamp, log ingestion và độ trễ thông thường dưới 15 phút |
| Finding bị đánh giá sai mức độ ưu tiên | Severity mặc định chưa phản ánh mức độ ảnh hưởng thực tế | Xem tài nguyên, dữ liệu và ngữ cảnh; dùng enrichment nếu phù hợp |
| Chi phí log tăng bất ngờ | Bật quá nhiều Data Access hoặc network logs | Giảm phạm vi, sampling, thời gian lưu và theo dõi ingestion |
| Pub/Sub không nhận finding | Sai topic, quyền publish, filter hoặc location | Kiểm tra service account thông báo, IAM, export filter và data residency |
| Custom module không tạo finding | Template không phù hợp, log thiếu hoặc module chưa Enable | Validate template, kiểm tra log đầu vào và trạng thái module |

ETD không quét mọi log trong project. Một log có mặt trong Cloud Logging không đồng nghĩa nó nằm trong danh sách nguồn dữ liệu mà detector sử dụng. Đây là nguyên nhân quan trọng khiến một tổ chức có thể bật rất nhiều log nhưng vẫn không có finding cho một hành vi cụ thể.

## 11. Thực hành vận hành tốt

- **Bắt đầu từ rủi ro:** xác định tài khoản, workload, dữ liệu và hành vi cần phát hiện trước khi bật thêm log.
- **Bảo vệ danh tính:** ưu tiên giám sát IAM, service account, key, quyền impersonation và thay đổi xác thực.
- **Duy trì log đủ dùng:** bật log theo detector và yêu cầu điều tra, định kỳ rà soát chi phí.
- **Tập trung finding:** dùng SCC làm nơi tổng hợp, sau đó export tới Pub/Sub hoặc Cloud Logging theo nhu cầu.
- **Có owner và SLA:** mỗi finding HIGH hoặc CRITICAL cần nhóm phụ trách, thời hạn phản hồi và đường escalation.
- **Giảm cảnh báo lặp:** dùng mute có lý do, điều chỉnh custom module và loại bỏ quy tắc trùng lặp.
- **Kiểm thử có kiểm soát:** dùng detector test và tài nguyên riêng, sau đó dọn dẹp đầy đủ.
- **Giữ bằng chứng:** bảo vệ log, thời gian, danh tính, IP và source properties cần cho điều tra.
- **Đánh giá lại định kỳ:** detector và nguồn log thay đổi theo thời gian; cập nhật runbook theo tài liệu Google Cloud hiện hành.

## Kết luận

Event Threat Detection giúp tổ chức phát hiện các hoạt động đáng ngờ từ log Google Cloud và Google Workspace trong phạm vi hỗ trợ. Dịch vụ kết hợp quy tắc, threat intelligence, IoC, profiling theo thời gian, machine learning và phát hiện bất thường để tạo finding gần thời gian thực trong Security Command Center.

Giá trị của ETD phụ thuộc vào ba yếu tố: chọn đúng phạm vi bảo vệ, cung cấp đúng nguồn log và có quy trình điều tra/phản ứng rõ ràng. Finding là điểm khởi đầu cho việc xác minh sự cố; đội bảo mật vẫn cần đối chiếu danh tính, tài nguyên, log gốc và thay đổi được phê duyệt trước khi kết luận hoặc ngăn chặn.

## Tài liệu tham khảo

- [Overview of Event Threat Detection](https://cloud.google.com/security-command-center/docs/concepts-event-threat-detection-overview)
- [Use Event Threat Detection](https://cloud.google.com/security-command-center/docs/how-to-use-event-threat-detection)
- [Test Event Threat Detection](https://cloud.google.com/security-command-center/docs/how-to-test-event-threat-detection)
- [Log types and activation requirements](https://cloud.google.com/security-command-center/docs/concepts-event-threat-detection-overview#log_types_and_activation_requirements)
- [Security Command Center service tiers](https://cloud.google.com/security-command-center/docs/service-tiers)
- [Choose the services to enable](https://cloud.google.com/security-command-center/docs/concepts-security-sources)
- [Review and manage findings](https://cloud.google.com/security-command-center/docs/review-manage-findings)
- [Overview of custom modules for Event Threat Detection](https://cloud.google.com/security-command-center/docs/custom-modules-etd-overview)
- [Create and manage custom modules for Event Threat Detection](https://cloud.google.com/security-command-center/docs/use-custom-modules-etd)
- [Export Security Command Center data](https://cloud.google.com/security-command-center/docs/how-to-export-data)
- [Export logs to Cloud Logging](https://cloud.google.com/security-command-center/docs/export-cloud-logging)

