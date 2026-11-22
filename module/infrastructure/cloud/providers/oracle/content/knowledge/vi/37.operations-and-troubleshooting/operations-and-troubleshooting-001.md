# Thiết kế runbooks và phân công trách nhiệm vận hành OCI

Trong chương **Vận hành và xử lý sự cố**, một hệ thống Oracle Cloud Infrastructure (OCI) được xem là sẵn sàng vận hành khi người trực có thể trả lời được: dịch vụ nào đang bị ảnh hưởng, ai chịu trách nhiệm, cần thu thập bằng chứng gì, được phép thay đổi những gì và dựa vào đâu để kết luận đã khôi phục.

Bài học này hướng dẫn thiết kế runbook cho hạ tầng OCI gồm tenancy, compartment, IAM, VCN, Compute, lưu trữ và dịch vụ cơ sở dữ liệu Oracle. Trọng tâm là nối tài liệu kỹ thuật với quyền thao tác, lịch trực, giám sát, tự động hóa và giới hạn chi phí, để quy trình có thể thực hiện trong ca trực thực tế.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, người học có thể:

- Xây dựng một runbook có điều kiện kích hoạt, bước chẩn đoán, nhánh quyết định, biện pháp khôi phục và tiêu chí kết thúc.
- Phân biệt trách nhiệm của Oracle với trách nhiệm vận hành workload của tổ chức.
- Lập ma trận RACI, phân công người trực chính, người dự phòng và người có quyền quyết định.
- Gắn alarm, tài nguyên OCI và hồ sơ sự cố với đúng phiên bản runbook.
- Thiết kế thao tác có giới hạn phạm vi, có rollback và có bằng chứng sau khi thực hiện.
- Tổ chức diễn tập, bàn giao và cập nhật tài liệu khi hạ tầng thay đổi.

Người học nên biết cách nhận diện tenancy, compartment, region và OCID; hiểu cơ bản về IAM policy, VCN, Network Security Group (NSG), Compute và Load Balancing. Những kiến thức đó giúp đọc đúng ngữ cảnh thao tác; bài học không yêu cầu triển khai một tenancy mới.

Các tên dịch vụ, địa chỉ IP, ngưỡng cảnh báo và thời hạn phản hồi trong ví dụ là dữ liệu minh họa của một tổ chức giả định. Khi đưa vào sử dụng, đội vận hành phải thay bằng thông tin đã được phê duyệt cho workload của mình.

## 2. Runbook phải giúp người trực đưa ra quyết định

**Runbook** là quy trình thực hiện một công việc vận hành có phạm vi xác định. Công việc có thể là xử lý backend mất health, xoay vòng chứng thư, phục hồi bản sao lưu hoặc kiểm tra sau bảo trì.

Một runbook sử dụng được phải có đầu vào, các bước có thể quan sát kết quả và điều kiện dừng. Câu “kiểm tra mạng rồi khởi động lại máy” chưa đủ vì không cho biết kiểm tra đường nào, ai được restart, tác động tới người dùng ra sao và cần làm gì nếu máy vẫn lỗi.

Cần phân biệt các tài liệu liên quan:

| Thành phần | Câu hỏi được giải quyết | Ví dụ trong OCI |
| --- | --- | --- |
| Hồ sơ dịch vụ | Workload gồm gì, phục vụ ai, ai sở hữu? | API đơn hàng nằm trong compartment nào, phụ thuộc database nào |
| Playbook ứng phó | Điều phối một nhóm tình huống như thế nào? | Quy trình điều hành sự cố ảnh hưởng khách hàng |
| Runbook | Thực hiện tác vụ cụ thể bằng bước nào? | Chẩn đoán backend set không khỏe và khôi phục lưu lượng |
| Infrastructure as Code (IaC) | Trạng thái hạ tầng mong muốn được mô tả ở đâu? | Cấu hình VCN, NSG, Load Balancer bằng Terraform |
| Hồ sơ sự cố | Lần thực hiện này đã xảy ra điều gì? | Timeline, bằng chứng, quyết định, người thao tác, kết quả |

Runbook có thể gọi pipeline hoặc công cụ IaC, nhưng vẫn cần nêu điều kiện chạy, phạm vi thay đổi và cách xác minh. Một script chạy thành công chỉ cho biết script đã hoàn tất theo cách nó được viết; trạng thái phục vụ người dùng phải được kiểm tra riêng.

Một runbook tốt cũng ghi rõ **không áp dụng khi nào**. Quy trình xử lý HTTP backend của OCI Load Balancer không thể dùng nguyên trạng cho Network Load Balancer, OKE hoặc một database đang có dấu hiệu hỏng dữ liệu.

## 3. Xác định ranh giới trách nhiệm trước khi viết lệnh

### 3.1. Trách nhiệm của Oracle và của tổ chức

OCI sử dụng mô hình trách nhiệm chia sẻ. Oracle vận hành hạ tầng nền tảng; khách hàng chịu trách nhiệm bảo vệ workload và cấu hình tài nguyên mình sử dụng. Phạm vi cụ thể còn phụ thuộc loại dịch vụ, đặc biệt khi so sánh phần mềm tự cài trên Compute với dịch vụ được quản lý. [Oracle: Security Overview](https://docs.oracle.com/en-us/iaas/Content/Security/Concepts/security_overview.htm).

Bảng dưới đây là cách phân công nội bộ minh họa, cần được đối chiếu với dịch vụ thực tế:

| Lớp | Trách nhiệm cần có người sở hữu trong tổ chức |
| --- | --- |
| Tenancy, compartment, IAM | Quản lý danh tính, chính sách truy cập, quyền khẩn cấp và phạm vi quản trị |
| VCN, subnet, NSG, route | Cấu hình kết nối, kiểm soát luồng truy cập và duy trì đường quản trị |
| Compute tự quản lý | Vận hành hệ điều hành khách, ứng dụng, cấu hình và bản vá thuộc phạm vi khách hàng |
| Block Volume, Object Storage | Chính sách truy cập, vòng đời dữ liệu, nhu cầu backup và kiểm thử phục hồi |
| Cơ sở dữ liệu Oracle | Phân công theo đúng sản phẩm: cấu hình, dữ liệu, quyền truy cập và tác vụ khách hàng phải thực hiện |
| Ứng dụng | Chất lượng giao dịch, triển khai, dependency, SLO và phục hồi dịch vụ |

Không ghi chung “Oracle chịu trách nhiệm database” rồi bỏ trống chủ sở hữu nội bộ. Với mỗi database, runbook phải nêu rõ đang dùng sản phẩm nào, ai theo dõi trạng thái, ai thay đổi cấu hình, ai yêu cầu hỗ trợ và ai xác nhận ứng dụng đã hoạt động lại.

Tính sẵn sàng cũng là trách nhiệm chia sẻ: tổ chức phải thiết kế và kiểm thử HA, DR, failover và kế hoạch liên tục kinh doanh cho workload. Việc dịch vụ nền tảng có cơ chế dự phòng không tự tạo ra phương án phục hồi hoàn chỉnh cho ứng dụng. [Oracle: Shared Responsibility Model for Resiliency](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/oci-shared-responsibility.htm).

### 3.2. Ba loại quyền cần ghi riêng

Trong một sự cố, ba loại quyền sau có thể thuộc ba người khác nhau:

1. **Quyền kỹ thuật:** IAM, quyền hệ điều hành, quyền database hoặc quyền chạy pipeline cho phép thực hiện thao tác.
2. **Quyền phê duyệt:** cơ chế quản trị nội bộ cho phép chấp nhận rủi ro của thao tác.
3. **Trách nhiệm xác nhận:** người kiểm tra rằng kết quả đã đáp ứng yêu cầu của dịch vụ.

Ví dụ, kỹ sư Platform có thể có quyền cập nhật backend set, nhưng chỉ được thay đổi trong phạm vi khôi phục đã cho phép. Incident Commander điều phối quyết định theo cơ chế sự cố, còn chủ ứng dụng xác nhận luồng nghiệp vụ. Quyền điều hành sự cố không tự cấp quyền IAM và không thay thế phê duyệt chuyên môn cho mọi thay đổi.

## 4. Lập hồ sơ dịch vụ và bản đồ phụ thuộc

Runbook nên tham chiếu một hồ sơ dịch vụ đang được duy trì. Hồ sơ này là điểm tra cứu thống nhất cho tên workload, chủ sở hữu và tài nguyên.

| Thông tin | Nội dung cần có |
| --- | --- |
| Định danh dịch vụ | Tên duy nhất, môi trường, mức độ quan trọng, chủ sở hữu |
| Vị trí OCI | Tenancy, compartment OCID, region, vị trí dự phòng nếu có |
| Tài nguyên | OCID của Load Balancer, Compute, volume, database và các thành phần liên quan |
| Luồng truy cập | DNS, listener, backend set, cổng ứng dụng, NSG, đường tới database |
| Mục tiêu phục vụ | SLI, SLO, khoảng thời gian đo, RTO và RPO đã thống nhất |
| Quan sát | Dashboard, truy vấn log, alarm, kiểm tra từ bên ngoài |
| Triển khai | Pipeline, phiên bản đang chạy, phiên bản có thể quay lại, nơi lưu cấu hình |
| Phục hồi | Vị trí bản sao lưu, lần kiểm thử gần nhất, điều kiện failover và failback |
| Trách nhiệm | Đội chính, đội dự phòng, lịch trực, đầu mối Security và Oracle Support |
| Ràng buộc | Thời gian bảo trì, quyền thay đổi, giới hạn capacity và ngân sách phục hồi |

**SLI** là chỉ số đo chất lượng dịch vụ; **SLO** là mục tiêu cho chỉ số đó. **RTO** là thời gian mục tiêu để khôi phục; **RPO** là mức mất dữ liệu theo thời gian có thể chấp nhận. Chúng cần có phạm vi nghiệp vụ rõ ràng, không thể suy từ việc một instance đang ở trạng thái RUNNING.

Bản đồ phụ thuộc cần thể hiện cả hai phía:

- **Luồng dữ liệu:** người dùng → DNS → Load Balancer → ứng dụng trên Compute → database hoặc storage.
- **Luồng quản trị:** người trực → hệ thống danh tính → OCI API hoặc pipeline → tài nguyên.

Luồng quản trị có thể lỗi trong khi ứng dụng vẫn phục vụ, hoặc ứng dụng có thể lỗi trong khi Console vẫn truy cập được. Vì vậy, một API đọc thành công chưa đủ để kết luận workload khỏe; ngược lại, lỗi truy cập Console chưa chứng minh ứng dụng đã ngừng phục vụ.

Đối với VCN dùng chung hoặc tài nguyên ở nhiều compartment, phải ghi rõ đội chịu trách nhiệm từng phần. Đội ứng dụng không nên phải tự đoán ai quản lý route hay NSG trong lúc xử lý sự cố.

## 5. Phân công trách nhiệm bằng RACI và lịch trực

### 5.1. Vai trò trong vận hành

Một mô hình có thể bắt đầu với các vai trò sau:

- **Service Owner:** chịu trách nhiệm cuối cùng về chất lượng dịch vụ, mục tiêu phục vụ và việc bảo đảm có đủ nhân sự vận hành.
- **Platform/Cloud Operations:** vận hành tài nguyên OCI, công cụ quan sát và đường truy cập quản trị thuộc phạm vi được giao.
- **Application Team:** sở hữu mã nguồn, cấu hình ứng dụng, triển khai và hành vi nghiệp vụ.
- **DBA/Data Operations:** sở hữu tác vụ database và phục hồi dữ liệu thuộc phạm vi tổ chức.
- **Security/IAM:** quản lý kiểm soát danh tính, truy cập và xử lý các vấn đề an ninh.
- **Incident Commander (IC):** điều phối sự cố, ưu tiên hành động, quản lý các thay đổi đồng thời và tổ chức cập nhật tình hình.

Một người có thể đảm nhiệm nhiều vai trò trong đội nhỏ. Khi đó vẫn phải ghi rõ họ đang chịu trách nhiệm nào và cơ chế kiểm tra độc lập áp dụng cho thao tác quan trọng.

### 5.2. Ma trận RACI mẫu

RACI gồm **R — Responsible**: người thực hiện; **A — Accountable**: người chịu trách nhiệm cuối cùng cho đầu việc; **C — Consulted**: người được tham vấn; **I — Informed**: người được thông báo.

Mỗi hàng nên có đúng một A. Ký hiệu A/R nghĩa là cùng một vai trò vừa chịu trách nhiệm cuối cùng vừa thực hiện.

| Đầu việc | Service Owner | Platform | Application | DBA | Security/IAM | IC |
| --- | --- | --- | --- | --- | --- | --- |
| Duy trì hồ sơ dịch vụ và danh mục runbook | A | R | C | C | C | I |
| Viết và kiểm thử runbook Load Balancer | A | R | C | I | C | I |
| Duy trì runbook rollback ứng dụng | A | C | R | C | C | I |
| Thực hiện và kiểm thử phục hồi database | A | C | C | R | C | I |
| Phê duyệt thiết kế quyền truy cập khẩn cấp | C | R | C | C | A | I |
| Kích hoạt điều phối khi có sự cố nghiêm trọng | I | R | C | C | C | A |
| Thực hiện rollback ứng dụng đã được phép | I | C | A/R | C | I | C |
| Thực hiện thay đổi mạng đã được phép | I | A/R | C | I | C | C |
| Phát hành cập nhật tình hình sự cố nội bộ | C | C | C | C | C | A/R |
| Chấp nhận kết quả phục hồi dịch vụ | A | R | R | C | C | C |

Ma trận này là ví dụ tổ chức công việc, không phải tập IAM policy. Mỗi hàng có thay đổi còn phải gắn với quyền thao tác và cơ chế phê duyệt tương ứng.

Nếu điều tra có dấu hiệu xâm nhập, cần kích hoạt quy trình sự cố an ninh riêng với người chỉ huy và quyền quyết định đã xác định trước. Tránh để runbook khôi phục thông thường vô tình xóa bằng chứng cần thiết.

### 5.3. Chuyển vai trò thành người có thể liên hệ

Một ô “Platform: R” chưa bảo đảm có người phản hồi lúc nửa đêm. Mỗi đầu việc quan trọng phải có:

- Lịch trực chính và trực dự phòng, bao gồm múi giờ, ngày nghỉ và thời điểm đổi ca.
- Kênh báo động đã kiểm thử và phương thức xác nhận đã nhận việc.
- Thời hạn chuyển cấp khi không có phản hồi.
- Quy tắc bàn giao cho đội chuyên môn và điều kiện xác nhận đã tiếp nhận.
- Đầu mối quản lý khi không có đội nào nhận trách nhiệm.

Nên tham chiếu lịch trực đang được quản lý thay vì sao chép tên cá nhân vào nhiều runbook. Người đang xử lý giữ trách nhiệm điều phối tới khi người nhận tiếp theo xác nhận; việc gửi một tin nhắn chưa hoàn tất bàn giao.

## 6. Phân loại mức độ ảnh hưởng và thiết kế chuyển cấp

Mức độ nghiêm trọng phải dựa vào ảnh hưởng tới dịch vụ, dữ liệu và khách hàng. Trạng thái của một tài nguyên là một đầu vào để đánh giá ảnh hưởng.

| Mức nội bộ minh họa | Dấu hiệu | Cách tổ chức phản ứng |
| --- | --- | --- |
| SEV1 | Luồng nghiệp vụ trọng yếu ngừng trên diện rộng, hoặc có rủi ro nghiêm trọng với dữ liệu | Kích hoạt trực chính và IC ngay, huy động đội chuyên môn phù hợp |
| SEV2 | Dịch vụ suy giảm đáng kể, một nhóm người dùng bị ảnh hưởng hoặc năng lực dự phòng giảm mạnh | Đội trực xử lý, IC tham gia theo quy trình nội bộ |
| SEV3 | Lỗi cục bộ, có phương án thay thế và ảnh hưởng hạn chế | Đội sở hữu xử lý theo hàng đợi có thời hạn |
| SEV4 | Công việc cải tiến hoặc cảnh báo không gây ảnh hưởng tức thời | Lập kế hoạch và theo dõi tới khi hoàn thành |

Một instance lỗi nhưng dịch vụ còn đủ năng lực phục vụ có thể có mức khác với việc tất cả backend cùng mất health. Ngược lại, mất một bản sao dự phòng vẫn có thể cần ưu tiên cao dù chưa có lỗi người dùng.

Ví dụ chính sách thời gian cho một SEV1:

- Tại T0: mở hồ sơ, gọi trực chính, bắt đầu chỉ định IC.
- Sau 5 phút chưa có xác nhận: gọi trực dự phòng.
- Sau 10 phút vẫn chưa có người tiếp nhận: chuyển quản lý trực.
- Sau 15 phút chưa xác định được hướng khôi phục an toàn: IC tập hợp chuyên gia và đánh giá việc mở yêu cầu hỗ trợ Oracle.
- Trong quá trình xử lý: cập nhật nội bộ mỗi 15 phút hoặc khi có thay đổi đáng kể.

Các mốc này là mục tiêu vận hành giả định của tổ chức, không phải SLA hay cam kết phản hồi của Oracle. Khi có nguy cơ mất dữ liệu hoặc vấn đề an ninh, phải chuyển cấp ngay theo điều kiện đó, không chờ hết mốc thời gian thông thường.

Phân biệt thời gian **xác nhận**, **bắt đầu xử lý**, **giảm ảnh hưởng** và **khôi phục hoàn toàn**. Một đội có thể xác nhận rất nhanh nhưng vẫn cần hỗ trợ chuyên môn để phục hồi.

## 7. Cấu trúc chuẩn của một runbook

### 7.1. Phần nhận diện và điều kiện đầu vào

Mỗi runbook nên có một khối nhận diện ngắn ở đầu:

| Trường | Ý nghĩa |
| --- | --- |
| Mã và tên | Định danh ổn định để gắn từ alarm hoặc phiếu sự cố |
| Phiên bản | Phiên bản tài liệu và phạm vi công cụ đã kiểm thử |
| Chủ sở hữu | Đội bảo trì tài liệu và người chịu trách nhiệm cuối cùng |
| Phạm vi áp dụng | Dịch vụ, môi trường, tài nguyên và kiểu kiến trúc |
| Điều kiện kích hoạt | Tín hiệu nào cho phép bắt đầu, cần xác minh gì trước |
| Trường hợp loại trừ | Khi nào phải chuyển sang runbook hoặc đội khác |
| Quyền cần có | Quyền đọc, quyền thay đổi, đường truy cập và quyền phê duyệt |
| Nguồn dữ liệu | Hồ sơ dịch vụ, dashboard, log, pipeline, cấu hình mong muốn |
| Kiểm thử gần nhất | Ngày, môi trường, kết quả và hạn chế đã biết |

Không đưa mật khẩu, private key, wallet hoặc token vào tài liệu. Chỉ dẫn cách lấy quyền qua cơ chế quản lý danh tính hoặc bí mật đã được tổ chức phê duyệt.

### 7.2. Mỗi bước phải có hợp đồng thực hiện

Một bước có thể viết theo mẫu:

~~~text
Bước: 04 - Đọc health của backend set
Người thực hiện: Platform đang trực
Đầu vào: Region, OCID Load Balancer, tên backend set đã đối chiếu
Quyền: Quyền đọc API tương ứng trong phạm vi tài nguyên
Thao tác: Chạy lệnh đọc được liệt kê
Kết quả cần quan sát: Trạng thái tổng thể và các backend có vấn đề
Bằng chứng: Thời điểm UTC, đầu ra đã xử lý thông tin nhạy cảm
Nhánh tiếp theo:
  - Health bất thường: kiểm tra chi tiết backend và thay đổi gần nhất
  - Health bình thường: tiếp tục điều tra lỗi ở lớp ứng dụng
  - Không đọc được: kiểm tra region, định danh và quyền; không đoán trạng thái
Giới hạn: Đánh giá lần đầu trong 3 phút, sau đó cập nhật IC nếu bị chặn
Điều kiện dừng: Tài nguyên không khớp hồ sơ hoặc không đủ quyền
Rollback: Không áp dụng, vì đây là thao tác chỉ đọc
~~~

Mốc ba phút ở đây là thời hạn tổ chức đánh giá bước, không phải timeout mặc định của OCI CLI.

Với bước thay đổi, bổ sung: trạng thái trước thay đổi, người cho phép, phạm vi ảnh hưởng, điều kiện thao tác an toàn, thời gian chờ, cách xử lý kết quả không xác định và cách quay lại trạng thái trước.

“Thử lại” phải có giới hạn. Nếu yêu cầu thay đổi bị timeout, trước tiên đọc trạng thái tài nguyên hoặc tác vụ liên quan để biết yêu cầu trước đã được áp dụng chưa; tránh gửi lại mù quáng.

## 8. Nối giám sát với runbook và người nhận việc

Một tuyến xử lý cảnh báo có thể được thiết kế như sau:

~~~mermaid
flowchart TD
    A["Metric hoặc kiểm tra giao dịch đã cấu hình"] --> B["OCI Monitoring alarm"]
    B --> C["OCI Notifications topic"]
    C --> D["Tích hợp trực và phiếu sự cố"]
    D --> E["Người trực xác nhận tiếp nhận"]
    E --> F["Xác minh tác động và chọn runbook"]
    F --> G{"Có đủ bằng chứng và quyền xử lý?"}
    G -->|Có| H["Thực hiện nhánh đã cho phép"]
    G -->|Không| I["Chuyển cấp kèm bằng chứng"]
    H --> J["Xác minh phục hồi và bàn giao"]
    I --> F
~~~

OCI Monitoring cung cấp metric và alarm; đích thông báo của alarm phải được cấu hình. Kết nối với lịch trực hoặc hệ thống quản lý sự cố cần tích hợp tương ứng của tổ chức, kiểm thử subscription và xác nhận người nhận. Không mặc định rằng tạo alarm sẽ tự có phiếu sự cố hoặc người trực tiếp nhận. [Oracle: Overview of Monitoring](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Concepts/monitoringoverview.htm), [Oracle: Example Alarm Messages](https://docs.oracle.com/en-us/iaas/Content/Monitoring/alarm-message-examples.htm).

Mỗi thông báo cần cung cấp đủ ngữ cảnh để chọn đúng quy trình:

- Dịch vụ, môi trường, region và compartment liên quan.
- Alarm OCID, thời điểm, trạng thái và tài nguyên hoặc metric stream gây cảnh báo.
- Mô tả ảnh hưởng cần kiểm tra.
- Đội sở hữu, đường dẫn runbook, dashboard và nơi mở hồ sơ sự cố.

Chỉ sử dụng trường hoặc dimension có thật trong dữ liệu; bổ sung thông tin từ hồ sơ dịch vụ tại lớp tích hợp nếu cần. Khi alarm gom nhiều metric stream, phải xác định toàn bộ tài nguyên bị ảnh hưởng trước khi thao tác. Cách nhóm thông báo và nội dung trường phụ thuộc cấu hình alarm. [Oracle: Alarm Message Format](https://docs.oracle.com/en-us/iaas/Content/Monitoring/alarm-message-format.htm).

Nhãn mức độ của alarm và SEV nội bộ cần có quy tắc ánh xạ. Một alarm có severity CRITICAL chưa đủ để tự kết luận mọi trường hợp đều là SEV1.

Để hạn chế báo động trùng, hệ thống tiếp nhận nên liên kết các sự kiện thuộc cùng một sự cố và giữ lịch sử diễn biến. Với cảnh báo thiếu dữ liệu, phải phân biệt workload không phát metric với workload hoạt động bình thường; việc metric biến mất không tự chứng minh đã phục hồi.

## 9. Runbook minh họa: API đơn hàng lỗi sau OCI Load Balancer

### 9.1. Phạm vi và cấu trúc dịch vụ

Dịch vụ giả định có một OCI Load Balancer nhận HTTPS, chuyển tới hai backend ứng dụng Java trên Compute. Ứng dụng kết nối một dịch vụ cơ sở dữ liệu Oracle qua mạng riêng.

| Thuộc tính | Giá trị minh họa |
| --- | --- |
| Runbook | RB-OCI-ORDER-HTTP-001 |
| Tên | Chẩn đoán HTTP 5xx và backend health bất thường |
| Phiên bản ví dụ | 1.0, cần điền kết quả kiểm thử trước khi dùng |
| Chủ sở hữu | Platform, với Service Owner chịu trách nhiệm cuối cùng |
| Môi trường | Production, compartment ProdApps, một region đã xác định |
| Đội phối hợp | Application; Network, DBA và Security khi có dấu hiệu thuộc phạm vi |
| Kích hoạt | Tỷ lệ HTTP 5xx trên 5% trong 5 phút với ít nhất 100 request/phút, hoặc mất mức dự phòng backend đã quy định |
| Giới hạn thao tác | Thu thập bằng chứng; khôi phục cấu hình hoặc rollback qua quy trình đã được phép |
| Loại trừ | Dấu hiệu xâm nhập, nghi ngờ mất dữ liệu, yêu cầu database failover hoặc chuyển region |

Tín hiệu 5xx và lưu lượng tối thiểu phải xuất phát từ nguồn đo đã xác định, có cùng phạm vi và cách tính nhất quán. Đây là điều kiện thiết kế minh họa, không phải một biểu thức MQL có thể sao chép trực tiếp vào mọi tenancy.

Runbook này áp dụng cho **OCI Load Balancer**, với nhóm lệnh **oci lb**. Nếu tài nguyên thực tế là Network Load Balancer hoặc một thành phần khác, dừng và chọn tài liệu phù hợp.

### 9.2. Bước 1 — Nhận việc, xác nhận tác động

**Người thực hiện:** trực chính; IC điều phối nếu mức ảnh hưởng yêu cầu.

1. Mở hoặc nhận hồ sơ sự cố, ghi mã sự cố và thời điểm bắt đầu bằng UTC.
2. Xác nhận dịch vụ, môi trường, region và tài nguyên từ alarm với hồ sơ dịch vụ.
3. Kiểm tra một tín hiệu hướng người dùng: probe từ bên ngoài, tỷ lệ thành công hoặc giao dịch kiểm thử được phép.
4. Ghi nhóm người dùng, endpoint và luồng nghiệp vụ bị ảnh hưởng.
5. Đối chiếu triển khai, thay đổi mạng hoặc bảo trì gần thời điểm phát sinh.

Nếu alarm bị trễ hoặc sự cố đã tự hết, vẫn lưu bằng chứng để xác định đó là cảnh báo thoáng qua, lỗi đo hay gián đoạn có thật. Nếu cần ngăn thay đổi đồng thời, IC thực hiện theo quyền điều phối đã thống nhất và ghi phạm vi tạm dừng.

**Đầu ra:** một mô tả ảnh hưởng có căn cứ, người điều phối đã rõ và danh sách thay đổi liên quan. Chưa thực hiện restart hoặc thay đổi cấu hình ở bước này.

### 9.3. Bước 2 — Đối chiếu tài nguyên và đọc trạng thái

**Người thực hiện:** Platform có quyền đọc phù hợp.

Đoạn lệnh dưới đây dành cho **Bash**, chẳng hạn máy quản trị hoặc OCI Cloud Shell đã cấu hình xác thực. Người thực hiện phải thay các giá trị minh họa, xác nhận profile trỏ tới đúng danh tính và tenancy, rồi đối chiếu region cùng OCID với hồ sơ dịch vụ. Profile trong ví dụ là một cấu hình đã chuẩn bị, không được các lệnh này tự tạo.

~~~bash
RUNBOOK_PROFILE='OPS_READONLY'
RUNBOOK_REGION='ap-singapore-1'
RUNBOOK_LB_OCID='THAY_BANG_OCID_LOAD_BALANCER_DA_XAC_MINH'
RUNBOOK_BACKEND_SET='orders-backend-set'

date -u '+%Y-%m-%dT%H:%M:%SZ'

oci lb load-balancer get --load-balancer-id "$RUNBOOK_LB_OCID" --region "$RUNBOOK_REGION" --profile "$RUNBOOK_PROFILE" --output json

oci lb backend-set get --load-balancer-id "$RUNBOOK_LB_OCID" --backend-set-name "$RUNBOOK_BACKEND_SET" --region "$RUNBOOK_REGION" --profile "$RUNBOOK_PROFILE" --output json

oci lb backend-set-health get --load-balancer-id "$RUNBOOK_LB_OCID" --backend-set-name "$RUNBOOK_BACKEND_SET" --region "$RUNBOOK_REGION" --profile "$RUNBOOK_PROFILE" --output json
~~~

Ba lệnh lần lượt đọc cấu hình Load Balancer, cấu hình backend set và health của backend set. Đối chiếu ID, compartment, backend, cổng và health check với hồ sơ trước khi đi tiếp. [Oracle CLI: Load Balancer Get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/load-balancer/get.html), [Oracle CLI: Backend Set Get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/backend-set/get.html), [Oracle CLI: Backend Set Health Get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/backend-set-health/get.html).

Muốn xem một backend cụ thể, lấy đúng địa chỉ IP và cổng từ cấu hình vừa đọc:

~~~bash
RUNBOOK_BACKEND_NAME='10.20.10.11:8080'

oci lb backend-health get --load-balancer-id "$RUNBOOK_LB_OCID" --backend-set-name "$RUNBOOK_BACKEND_SET" --backend-name "$RUNBOOK_BACKEND_NAME" --region "$RUNBOOK_REGION" --profile "$RUNBOOK_PROFILE" --output json
~~~

Tham số backend-name có dạng địa chỉ IP và cổng; địa chỉ trong ví dụ phải được thay nếu không khớp tài nguyên thực tế. [Oracle CLI: Backend Health Get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/backend-health/get.html).

Nếu lệnh lỗi quyền hoặc không tìm thấy tài nguyên, ghi mã lỗi, request ID nếu có, thời điểm, region và định danh đang dùng. Xác minh lại OCID, compartment, profile và quyền qua đội có thẩm quyền. Không suy ra backend đã mất chỉ vì không đọc được API.

Không gửi toàn bộ đầu ra vào kênh công khai. Lưu phần cần thiết trong hồ sơ có kiểm soát và loại bỏ thông tin nhạy cảm.

### 9.4. Bước 3 — Phân loại bằng chứng và giao đúng đội

| Bằng chứng ban đầu | Hướng kiểm tra tiếp | Đội chủ trì kỹ thuật | Hành động cần tránh khi chưa có bằng chứng |
| --- | --- | --- | --- |
| Tất cả backend lỗi health ngay sau triển khai | Cổng lắng nghe, đường dẫn health, cấu hình và phiên bản ứng dụng | Application, Platform hỗ trợ | Restart đồng loạt để thử |
| Một backend lỗi, backend còn lại phục vụ | Tiến trình, log, tài nguyên hệ điều hành, kết nối của backend lỗi | Platform hoặc Application theo lớp lỗi | Loại backend khỏe khỏi dịch vụ |
| Nhiều backend timeout sau thay đổi NSG hoặc route | Luồng từ Load Balancer tới backend, quy tắc mạng và firewall hệ điều hành | Đội Network/Platform được giao | Mở toàn bộ cổng ra Internet |
| Backend health tốt nhưng người dùng vẫn gặp 5xx | Log ứng dụng, dependency, connection pool, lỗi theo endpoint | Application, gọi DBA nếu bằng chứng liên quan database | Kết luận dịch vụ đã khỏe |
| Có lỗi kết nối database đồng thời ở nhiều instance | Trạng thái dịch vụ database, đường mạng, giới hạn kết nối và thay đổi gần nhất | DBA phối hợp Application | Failover database theo runbook Load Balancer |
| Không có thay đổi nội bộ, nhiều dịch vụ cùng ảnh hưởng | Mức độ ảnh hưởng, trạng thái dịch vụ Oracle và hồ sơ hỗ trợ | IC cùng Platform | Khẳng định nguyên nhân thuộc Oracle chỉ từ trùng thời điểm |

Health check đánh giá điều kiện kiểm tra đã cấu hình. OCI Load Balancer có thể kiểm tra ở mức TCP hoặc HTTP; backend không đạt điều kiện sẽ bị đưa ra khỏi vòng phân phối lưu lượng và có thể được đưa lại khi đạt điều kiện. Do đó cần kiểm tra đúng cổng, URI, giao thức và mã phản hồi mong đợi. Health check TCP thành công không xác nhận đầy đủ một giao dịch nghiệp vụ HTTP. [Oracle: Health Check Policies for Load Balancers](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/load_balancer_health_management.htm).

Một phép kiểm tra từ máy quản trị chỉ có ý nghĩa với đường kết nối thực sự được phép từ máy đó. Nếu cần probe backend private, sử dụng điểm truy cập quản trị đã được cấp quyền và ghi lại nguồn kiểm tra; không mặc định Cloud Shell có kết nối tới mọi subnet riêng.

### 9.5. Bước 4 — Chọn biện pháp giảm ảnh hưởng

Mỗi biện pháp phải có người chịu trách nhiệm kỹ thuật, quyền thực hiện và căn cứ lựa chọn. IC giữ timeline chung để các đội không áp dụng hai thay đổi xung đột.

**Nhánh A — Lỗi xuất hiện sau triển khai ứng dụng**

- Application đối chiếu thời điểm lỗi với deployment và khác biệt cấu hình.
- Xác định phiên bản tốt đã biết và kiểm tra khả năng tương thích với schema, dữ liệu và cấu hình hiện tại.
- Nếu rollback đã có quy trình và đủ điều kiện, thực hiện qua pipeline được duyệt; ghi mã deployment và revision.
- Nếu có migration không thể quay lại an toàn, dừng nhánh rollback đơn giản và huy động DBA cùng người có quyền quyết định.
- Theo dõi backend health, tỷ lệ lỗi và giao dịch nghiệp vụ sau từng đợt.

**Nhánh B — Sai cấu hình mạng hoặc health check đã được chứng minh**

- Đội sở hữu xác định đúng thay đổi gây lỗi và trạng thái trước thay đổi.
- Xem trước phạm vi khôi phục qua quy trình cấu hình/IaC đang dùng.
- Chỉ khôi phục cấu hình liên quan đã được cho phép; kiểm tra để không kéo theo thay đổi khác đang chờ.
- Duy trì đường quản trị và kiểm tra kết nối sau khi áp dụng.
- Nếu phải sửa khẩn cấp ngoài pipeline, ghi lại khác biệt và giao người đồng bộ về cấu hình nguồn sau sự cố.

**Nhánh C — Một instance lỗi trong khi còn năng lực phục vụ**

- Đánh giá tải và năng lực còn lại trước khi cô lập backend lỗi.
- Xác minh yêu cầu về session, kết nối đang mở và trạng thái lưu cục bộ của ứng dụng.
- Chỉ drain hoặc cô lập theo quy trình đã kiểm thử của hệ thống.
- Thu thập log cần thiết, rồi áp dụng runbook sửa chữa hoặc thay thế instance đã được phê duyệt.
- Đưa backend trở lại sau kiểm tra readiness, health và lưu lượng thử phù hợp.

**Nhánh D — Chưa có biện pháp an toàn trong phạm vi**

- Dừng thay đổi mang tính phỏng đoán.
- Bàn giao các giả thuyết, bằng chứng và thao tác đã làm cho đội tiếp theo.
- IC đánh giá kích hoạt quy trình phục hồi cấp dịch vụ, DR hoặc yêu cầu hỗ trợ Oracle.
- Giữ theo dõi tác động và cập nhật tình hình trong khi chờ.

Không dùng một nhánh giảm ảnh hưởng để bỏ qua kiểm soát an ninh hoặc giới hạn dữ liệu. Nếu tăng capacity là phương án được phép, ghi rõ mức tăng tối đa, quota/capacity cần kiểm tra, giới hạn thời gian và người chịu trách nhiệm giảm lại sau sự cố.

### 9.6. Bước 5 — Rollback có điều kiện và xử lý kết quả không rõ

Trước mỗi thay đổi, ghi ít nhất:

~~~text
Mã thay đổi:
Tài nguyên và phạm vi:
Người thực hiện / người cho phép:
Căn cứ lựa chọn:
Trạng thái và cấu hình trước thay đổi:
Thao tác hoặc pipeline, revision cụ thể:
Kết quả mong đợi:
Thời gian theo dõi:
Điều kiện dừng:
Điều kiện và cách rollback:
Người xác minh:
~~~

Ví dụ điều kiện dừng: tỷ lệ lỗi tăng, backend khỏe còn lại mất health, xuất hiện lỗi dữ liệu hoặc thay đổi tác động tài nguyên ngoài phạm vi. Người thực hiện thông báo IC và áp dụng phương án quay lại đã xác định nếu phương án đó vẫn an toàn.

Sau timeout của thao tác, cần đọc lại trạng thái hoặc theo dõi tác vụ bất đồng bộ tương ứng trước khi kết luận thất bại. Ghi rõ “chưa xác định kết quả” khi chưa đủ bằng chứng.

Với thao tác như ghi đè dữ liệu hoặc database failover, việc quay lại có thể cần một quy trình riêng và không bảo đảm hoàn nguyên đơn giản. Runbook hiện tại phải dẫn tới chủ sở hữu quy trình đó, thay vì gọi chung là “undo”.

### 9.7. Bước 6 — Xác minh phục hồi và bàn giao

Ví dụ tiêu chí phục hồi cho dịch vụ giả định:

1. Luồng kiểm thử được phép qua đúng endpoint người dùng thành công.
2. Tỷ lệ 5xx xuống dưới ngưỡng khôi phục minh họa 1% và duy trì ít nhất 15 phút, với lưu lượng đủ để đánh giá.
3. Latency và tỷ lệ thành công trở về mức chấp nhận theo mục tiêu của dịch vụ.
4. Đạt số backend khỏe và mức dự phòng mà kiến trúc yêu cầu; không có backend còn lại bị quá tải.
5. Không còn backlog tăng bất thường hoặc lỗi dependency chưa xử lý.
6. Không có dấu hiệu sai lệch dữ liệu; mọi kiểm tra nghiệp vụ nhạy cảm do đội ứng dụng hoặc DBA phụ trách xác nhận.
7. Alarm đã trở về trạng thái phù hợp và nguồn metric vẫn hoạt động.

Nếu lưu lượng thực tế quá thấp, không kết luận chỉ từ tỷ lệ lỗi bằng không; sử dụng phép kiểm thử được chấp thuận và ghi hạn chế bằng chứng.

Khoảng theo dõi 15 phút và ngưỡng 1% là ví dụ để tạo điều kiện thoát rõ ràng. Mỗi dịch vụ phải chọn giá trị phù hợp với SLO, lưu lượng và đặc điểm lỗi của mình.

Phân biệt hai trạng thái:

- **Đã giảm ảnh hưởng:** khách hàng dùng lại được dịch vụ nhưng vẫn chạy thiếu dự phòng, capacity tạm hoặc cấu hình khẩn cấp.
- **Đã phục hồi đầy đủ:** mục tiêu phục vụ và yêu cầu vận hành đã đạt, phần việc còn lại có chủ sở hữu và thời hạn rõ ràng.

Nếu đang chạy suy giảm, Service Owner phải chấp nhận trạng thái tạm theo cơ chế của tổ chức; duy trì theo dõi và phiếu khắc phục tới khi phục hồi mức dự phòng. Trước khi kết thúc ca, bàn giao revision hiện tại, thay đổi tạm, cảnh báo đang tắt, rủi ro còn lại và hành động tiếp theo.

## 10. Gắn trách nhiệm với quyền IAM và bằng chứng

### 10.1. Thiết kế quyền theo khả năng cần dùng

Runbook cần mô tả quyền theo tác vụ thực tế, rồi đội IAM ánh xạ sang policy đúng với tài nguyên và cơ chế danh tính đang sử dụng.

| Khả năng | Người cần dùng | Ranh giới cần xác định |
| --- | --- | --- |
| Đọc cấu hình và health Load Balancer | Platform đang trực | Đúng tài nguyên hoặc compartment cần hỗ trợ |
| Đọc metric và alarm | Người chẩn đoán | Đúng nguồn metric và phạm vi dịch vụ |
| Đọc log ứng dụng và Audit liên quan | Đội xử lý được phép | Phân loại dữ liệu, vị trí log, phạm vi truy cập |
| Rollback ứng dụng | Application hoặc danh tính pipeline | Chỉ workload và môi trường được giao |
| Thay đổi mạng | Đội Network/Platform có thẩm quyền | VCN, subnet, NSG hoặc route được phân công |
| Phục hồi database | DBA được phân quyền | Đúng dịch vụ database và bộ dữ liệu |
| Sử dụng quyền khẩn cấp | Người được chỉ định | Cơ chế cấp, ghi nhận, thu hồi và kiểm tra sau sử dụng |

OCI IAM có các mức quyền với phạm vi API khác nhau. Ví dụ quyền đọc Load Balancer cần được đối chiếu với bảng quyền của dịch vụ và API thực tế sử dụng, thay vì cấp quyền quản trị toàn tenancy cho người trực. [Oracle: Details for Load Balancing](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/lbpolicyreference.htm).

Cần thử thao tác bằng chính vai trò trực, vì thử bằng tài khoản quản trị không chứng minh vai trò đó đủ quyền. Nếu tài nguyên nằm ở nhiều compartment hoặc đội khác sở hữu log, runbook phải ghi đường phối hợp hoặc quyền đọc đã chuẩn bị.

Quyền khẩn cấp nên có quy trình nhận diện người dùng, ghi lý do, cấp hoặc kích hoạt theo cơ chế đã chọn, theo dõi sử dụng và thu hồi sau khi hoàn tất. Không giả định mọi IAM policy tự có thời hạn nếu tổ chức chưa triển khai cơ chế đó.

### 10.2. Bằng chứng phải nối được quyết định với thao tác

Một bản ghi hành động nên gồm:

- Mã sự cố, thời gian UTC và người thực hiện.
- Danh tính hoặc vai trò dùng để thao tác, cùng tài nguyên mục tiêu.
- Dữ liệu quan sát trước khi ra quyết định.
- Lệnh hoặc pipeline, revision và người cho phép nếu cần.
- Request ID, work request ID hoặc mã tác vụ khi dịch vụ cung cấp.
- Kết quả sau thao tác, quyết định tiếp theo và người xác minh.

OCI Audit ghi nhận hoạt động gọi các API được hỗ trợ và cung cấp ngữ cảnh như thời gian, đích thao tác và phản hồi. Dùng Audit để đối chiếu thay đổi tài nguyên với timeline, đồng thời thu thập log ứng dụng, hệ điều hành, database hoặc pipeline khi cần. Audit không thay thế các nguồn log đó. [Oracle: Overview of Audit](https://docs.oracle.com/en-us/iaas/Content/Audit/Concepts/auditoverview.htm).

Nơi lưu bằng chứng phải có quyền truy cập và thời gian lưu phù hợp với tổ chức. Trước khi gửi dữ liệu cho bên ngoài, thực hiện quy trình phân loại và xử lý thông tin nhạy cảm đã quy định.

## 11. Tự động hóa runbook theo từng mức

Có thể phát triển tự động hóa theo ba mức:

| Mức | Phạm vi | Điều kiện sử dụng |
| --- | --- | --- |
| Thu thập tự động | Lấy health, metric, thay đổi và liên kết dashboard | Định danh tài nguyên chính xác, quyền đọc phù hợp, bảo vệ dữ liệu đầu ra |
| Khắc phục có người cho phép | Chuẩn bị đề xuất, người phụ trách kiểm tra rồi kích hoạt | Có bằng chứng, giới hạn phạm vi, kiểm tra trước và sau |
| Khắc phục tự động có giới hạn | Tự xử lý một lỗi đã hiểu rõ | Có điều kiện kích hoạt chặt, khả năng lặp an toàn, giới hạn số lần và cơ chế dừng |

Trước khi tự động hóa thao tác thay đổi, thiết kế các kiểm soát cụ thể:

1. **Đúng đích:** kiểm tra môi trường, region, compartment và OCID; thiếu thông tin thì dừng.
2. **Không chạy chồng:** một cơ chế điều phối ngăn nhiều tiến trình sửa cùng tài nguyên.
3. **Đọc trước khi ghi:** xác nhận lỗi và trạng thái hiện tại vẫn phù hợp với giả thuyết.
4. **Lặp an toàn:** nêu rõ thao tác có tính idempotent hay cần kiểm tra để tránh tạo hoặc thay đổi trùng.
5. **Giới hạn thử lại:** quy định số lần, khoảng chờ và cách xử lý kết quả không xác định.
6. **Giới hạn ảnh hưởng:** số tài nguyên, mức tăng capacity và thời gian áp dụng tối đa.
7. **Xác minh sau thực hiện:** kiểm tra chất lượng dịch vụ, không chỉ mã thoát của công cụ.
8. **Dừng và chuyển cấp:** có người nhận khi automation thất bại hoặc gặp tình huống ngoài phạm vi.

Danh tính chạy automation phải có chủ sở hữu và quyền theo tác vụ. Việc gọi pipeline không làm mất trách nhiệm của đội vận hành đối với quyết định và kết quả.

Không bắt đầu bằng vòng lặp “alarm còn FIRING thì restart tiếp”. Cách này có thể che nguyên nhân, phá bằng chứng và làm suy giảm thêm dịch vụ nếu chưa hiểu đặc tính lỗi.

## 12. Bảo đảm runbook dùng được khi có gián đoạn

### 12.1. Khả năng truy cập tài liệu và công cụ

Runbook phải còn truy cập được khi một dependency quản trị gặp lỗi. Cần đánh giá các tình huống như hệ thống danh tính không sẵn sàng, repository không truy cập được, VPN quản trị bị gián đoạn hoặc tài liệu chỉ tồn tại trong môi trường đang lỗi.

Giải pháp tùy tổ chức, nhưng cần xác định:

- Nơi có bản tài liệu đã duyệt có thể truy cập trong sự cố.
- Cách biết phiên bản nào đang được sử dụng và giới hạn của bản dự phòng.
- Đường liên lạc khi công cụ chat hoặc lịch trực chính bị gián đoạn.
- Cơ chế truy cập khẩn cấp đã kiểm thử và có kiểm soát.
- Người cập nhật bản dự phòng khi runbook thay đổi.

Không lưu bí mật trong bản sao ngoại tuyến để giải quyết vấn đề khả dụng của tài liệu.

### 12.2. Chi phí và tính sẵn sàng trong biện pháp khôi phục

Các phương án tăng tài nguyên, giữ thêm bản sao hoặc chuyển sang môi trường dự phòng phải có giới hạn vận hành cụ thể. Trước khi đưa vào runbook, xác định:

| Quyết định | Nội dung phải thống nhất |
| --- | --- |
| Tăng capacity | Ai được quyết định, tăng tới đâu, kiểm tra quota và khả năng cấp tài nguyên như thế nào |
| Chạy tài nguyên tạm | Người sở hữu, mục đích, thời hạn xem xét và cách giảm lại |
| Giữ thêm log hoặc snapshot | Mục đích điều tra, quyền truy cập, thời hạn lưu và chi phí liên quan |
| Chuyển sang hệ thống dự phòng | Điều kiện kích hoạt, RTO/RPO, dependency và người chấp nhận rủi ro |
| Quay lại hệ thống chính | Cách đồng bộ, kiểm tra dữ liệu và cửa sổ chuyển đổi |

Đừng xem thao tác xóa tài nguyên tạm là phần việc mặc nhiên của “ai đó sau sự cố”. Mỗi tài nguyên phát sinh và cấu hình tạm phải có chủ sở hữu cùng hạn xử lý.

Với DR, một lệnh failover thành công chưa đủ để chứng minh ứng dụng đã phục hồi. Quy trình cần bao gồm định tuyến, danh tính, bí mật, kết nối, kiểm tra dữ liệu và điều kiện failback phù hợp với kiến trúc.

## 13. Bảo trì runbook như một phần của dịch vụ

### 13.1. Vòng đời đề xuất

Một runbook nên đi qua các trạng thái nội bộ: **bản nháp → đã rà soát → đã diễn tập → đang áp dụng → cần cập nhật → ngừng dùng**.

Chủ sở hữu theo dõi phiên bản tài liệu, người rà soát, lần kiểm thử gần nhất và hạn chế đã biết. Khi ngừng dùng, cần cập nhật alarm và hồ sơ dịch vụ để người trực không tiếp tục truy cập tài liệu cũ.

Những thay đổi sau phải kích hoạt việc kiểm tra lại runbook:

- Chuyển compartment, region hoặc thay OCID tài nguyên.
- Đổi backend set, cổng, health endpoint, NSG hoặc route.
- Đổi cơ chế IAM, profile, pipeline hoặc công cụ triển khai.
- Nâng cấp ứng dụng, schema hoặc đổi sản phẩm database.
- Thay đổi đội sở hữu, lịch trực, SLO, RTO hoặc RPO.
- Một lần thực hiện phát hiện bước thiếu, quyền không đủ hoặc rollback không còn an toàn.

Tần suất kiểm tra định kỳ do tổ chức chọn theo rủi ro; việc có lịch kiểm tra không thay thế cập nhật ngay khi kiến trúc thay đổi.

### 13.2. Diễn tập phải kiểm tra cả con người lẫn kỹ thuật

Một buổi diễn tập nên giao cho người không viết runbook thực hiện trong môi trường cô lập phù hợp. Người quan sát kiểm tra xem họ có tìm được đúng tài nguyên, đủ quyền, hiểu các nhánh và biết lúc nào phải dừng hay không.

Đối với runbook HTTP ở trên, có thể diễn tập:

1. Chuẩn bị môi trường thử nghiệm có Load Balancer, hai backend và giám sát.
2. Xác định phạm vi, thời gian, giới hạn chi phí, người giám sát và cách trả hệ thống về bình thường.
3. Tạo lỗi có kiểm soát ở một backend hoặc cấu hình health trong phạm vi thử nghiệm.
4. Để người trực nhận cảnh báo, xác nhận và chẩn đoán theo tài liệu.
5. Ghi lại chỗ phải hỏi thêm, quyền bị thiếu, kết quả khó hiểu và thời gian chờ.
6. Khôi phục, xác minh đầy đủ và kết thúc tài nguyên thử nghiệm theo kế hoạch.

Có thể bổ sung diễn tập trên bàn cho các tình huống không có người phản hồi, không truy cập được kho tài liệu, API đọc bị từ chối hoặc phát hiện rủi ro dữ liệu. Mục đích là kiểm tra đường quyết định và chuyển cấp trước khi gặp sự cố thật.

## 14. Đo hiệu quả và tránh những lỗi thiết kế thường gặp

### 14.1. Chỉ số cần theo dõi

| Chỉ số | Cách dùng |
| --- | --- |
| Thời gian từ tín hiệu tới xác nhận | Kiểm tra lịch trực và kênh gọi có hoạt động |
| Thời gian xác định đúng đội sở hữu | Phát hiện khoảng trống trong hồ sơ dịch vụ và RACI |
| Thời gian tới biện pháp giảm ảnh hưởng | Đánh giá khả năng chọn và thực hiện nhánh khôi phục |
| Thời gian khôi phục hoàn toàn | Đánh giá cả chất lượng dịch vụ lẫn mức dự phòng |
| Tỷ lệ thực hiện không phải hỏi người viết | Phát hiện bước ngầm và dữ liệu còn thiếu |
| Tỷ lệ runbook đã diễn tập còn phù hợp | Theo dõi khả năng sử dụng thực tế của tài liệu |
| Số thay đổi tạm quá hạn | Phát hiện nợ vận hành, rủi ro và chi phí tồn đọng |

Mỗi chỉ số phải định nghĩa rõ thời điểm bắt đầu và kết thúc. Nếu dùng các thuật ngữ như MTTA hoặc MTTR, cần thống nhất chúng đo xác nhận, giảm ảnh hưởng, sửa chữa hay khôi phục; không so sánh số liệu khi các đội đang dùng định nghĩa khác nhau.

Không dùng tốc độ làm chỉ tiêu duy nhất. Một lần khôi phục nhanh nhưng bỏ qua kiểm tra dữ liệu hoặc để quyền khẩn cấp tồn tại vô thời hạn vẫn tạo ra rủi ro.

### 14.2. Lỗi thường gặp và cách sửa

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Ghi “đội Cloud xử lý” | Không có người nhận việc cụ thể | Gắn đội, lịch trực chính, dự phòng và thời hạn chuyển cấp |
| Chỉ đưa danh sách lệnh | Người trực không biết nhánh nào phù hợp | Thêm bằng chứng, kết quả mong đợi, điều kiện dừng và nhánh tiếp |
| Thử bằng tài khoản quản trị | Không phát hiện vai trò trực thiếu quyền | Diễn tập bằng đúng danh tính và phạm vi dự kiến |
| Cố định OCID hoặc tên người trong nhiều tài liệu | Tài liệu nhanh sai sau thay đổi | Tham chiếu hồ sơ dịch vụ và lịch trực được duy trì |
| Bỏ qua rollback | Khi thay đổi thất bại, người trực phải ứng biến | Xác định trạng thái trước, giới hạn và phương án quay lại trước khi thao tác |
| Coi health check là toàn bộ sức khỏe ứng dụng | Bỏ sót lỗi nghiệp vụ và dependency | Kết hợp health, metric và kiểm tra hướng người dùng |
| Cho rằng API timeout nghĩa là chưa thay đổi | Có thể thao tác lặp hoặc tạo xung đột | Đọc lại trạng thái hoặc tác vụ trước khi thử lại |
| Kết thúc khi mới hết lỗi người dùng | Bỏ quên dự phòng, quyền và tài nguyên tạm | Tách giảm ảnh hưởng với phục hồi đầy đủ, giao việc tồn đọng rõ ràng |

Sau sự cố, phần việc cải tiến cần có chủ sở hữu và hạn hoàn thành: sửa bước sai, bổ sung dashboard, thu hẹp quyền, thêm kiểm thử hoặc sửa automation. Việc cập nhật tài liệu cần được theo dõi tới khi hoàn tất như các thay đổi kỹ thuật khác.

## 15. Danh sách kiểm tra trước khi đưa vào sử dụng

Chủ sở hữu dịch vụ và các đội liên quan có thể dùng danh sách sau để chấp nhận một runbook:

- [ ] Đề bài, phạm vi áp dụng và trường hợp loại trừ đã rõ.
- [ ] Có hồ sơ dịch vụ với tenancy, compartment, region và tài nguyên được xác minh.
- [ ] Có một người chịu trách nhiệm cuối cùng cho từng đầu việc trong RACI.
- [ ] Trực chính, dự phòng, kênh gọi và đường chuyển cấp đã kiểm thử.
- [ ] Các quyền cần dùng đã được thử bằng vai trò thực tế.
- [ ] Mỗi bước có đầu vào, kết quả cần quan sát, bằng chứng và nhánh tiếp theo.
- [ ] Mỗi thay đổi có người cho phép khi cần, giới hạn ảnh hưởng, điều kiện dừng và cách khôi phục.
- [ ] Có hướng xử lý khi API lỗi, timeout, thiếu quyền hoặc thiếu bằng chứng.
- [ ] Có tiêu chí khôi phục dựa trên chất lượng dịch vụ và yêu cầu dữ liệu.
- [ ] Có cách theo dõi quyền khẩn cấp, tài nguyên tạm và chi phí phát sinh.
- [ ] Có phương án truy cập tài liệu và liên lạc khi công cụ chính gián đoạn.
- [ ] Đã diễn tập, ghi nhận hạn chế, chỉ định chủ sở hữu và điều kiện cập nhật phiên bản.
