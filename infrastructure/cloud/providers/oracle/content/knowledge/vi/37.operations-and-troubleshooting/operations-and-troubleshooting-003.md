# Mở support request và thu thập thông tin chẩn đoán

Một support request (SR) hiệu quả giúp Oracle Support biết chính xác dịch vụ nào gặp vấn đề, trong phạm vi nào, từ thời điểm nào và cần điều tra điều gì. “Không tạo được máy ảo” chỉ mô tả triệu chứng; một hồ sơ có region, OCID, thời gian UTC, request ID và kết quả kiểm tra giúp kỹ sư hỗ trợ tìm đúng thao tác trong hệ thống.

Trong vận hành Oracle Cloud Infrastructure (OCI), việc mở SR cần đi cùng phân quyền và bảo vệ dữ liệu chẩn đoán. Tenancy và compartment xác định bối cảnh tài nguyên; VCN, Compute, lưu trữ và các dịch vụ cơ sở dữ liệu cung cấp các lớp bằng chứng khác nhau. Nhóm vận hành vẫn chịu trách nhiệm giảm ảnh hưởng, theo dõi tính sẵn sàng và kiểm soát chi phí trong khi chờ hỗ trợ.

Bài học hướng dẫn chuẩn bị, mở và theo dõi một SR kỹ thuật. Các lệnh minh họa dùng để đọc trạng thái, không được thực thi tự động khi đọc bài. Mọi ID, tên tài nguyên và số liệu tình huống bên dưới đều là dữ liệu minh họa.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

- Phân biệt yêu cầu kỹ thuật, hỗ trợ tài khoản hoặc thanh toán và yêu cầu tăng giới hạn.
- Kiểm tra điều kiện tài khoản, quyền IAM và quyền trong cổng hỗ trợ trước khi có sự cố.
- Mô tả ảnh hưởng bằng số liệu để chọn mức nghiêm trọng phù hợp.
- Liên kết một sự cố với tài nguyên, API request, work request, Audit và các log liên quan.
- Tạo gói chẩn đoán nhỏ, có mốc thời gian và đã loại bỏ thông tin bí mật.
- Theo dõi trao đổi với Oracle Support cho đến khi xác nhận phục hồi và hoàn tất các việc còn lại.

Sản phẩm thực hành là một bản nháp SR cùng danh mục bằng chứng. Với môi trường học tập, không gửi SR giả chỉ để thử giao diện.

## 2. Khi nào nên mở yêu cầu hỗ trợ?

Mở SR khi cần Oracle tham gia điều tra, làm rõ hành vi dịch vụ hoặc thực hiện hỗ trợ thuộc phạm vi tài khoản. Không cần đợi xác định nguyên nhân gốc mới mở SR cho một sự cố có ảnh hưởng lớn; có thể gửi dữ kiện ban đầu rồi bổ sung bằng chứng.

| Tình huống | Hướng xử lý ban đầu | Thông tin cần nhấn mạnh |
| --- | --- | --- |
| API hoặc tài nguyên hoạt động bất thường, chưa giải thích được bằng cấu hình | Yêu cầu hỗ trợ kỹ thuật | Thao tác lỗi, region, tài nguyên, thời gian, request ID |
| Mất quyền truy cập tài khoản hoặc gặp vấn đề quản trị tenancy | Kênh hỗ trợ tài khoản hoặc đăng nhập tương ứng | Định danh tenancy và người liên hệ được ủy quyền |
| Cần giải thích hóa đơn hoặc khoản thu | Hỗ trợ thanh toán | Kỳ thanh toán và mục chi phí cần làm rõ |
| Cần nâng mức tài nguyên được phép sử dụng | Quy trình tăng service limit | Tên limit, region, mức hiện tại, mức cần và lý do |
| Muốn Oracle giải thích một sự cố đã phục hồi | Bổ sung yêu cầu điều tra hoặc RCA vào hồ sơ thích hợp | Cửa sổ sự cố, ảnh hưởng, bằng chứng và câu hỏi còn mở |

Oracle mô tả các loại yêu cầu này trong [Support Requests](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/contactingsupport.htm). Quyền mở SR chính thức áp dụng cho tài khoản trả phí theo điều kiện hỗ trợ của Oracle; người chỉ dùng Always Free hoặc Free Tier cần tham khảo Support Chat và Cloud Customer Connect được nêu tại đây.

Trước khi gửi, kiểm tra thông báo dịch vụ, thông báo bảo trì và sự cố đã được Oracle công bố, nếu truy cập được. Ghi lại nguồn và thời điểm kiểm tra. Việc chưa thấy thông báo không chứng minh dịch vụ hoàn toàn bình thường; sự cố có thể chỉ ảnh hưởng một tài nguyên, một nhóm khách hàng hoặc chưa được công bố.

Cũng cần phân biệt:

- **Service limit** là mức giới hạn dịch vụ áp dụng cho phạm vi tương ứng.
- **Compartment quota** là giới hạn do tổ chức đặt để quản trị tài nguyên.
- **Capacity** là khả năng cấp phát thực tế tại nơi và thời điểm yêu cầu.

Ví dụ, còn hạn mức OCPU không đủ để kết luận mọi shape đều cấp phát được ngay. Trong SR, chép nguyên mã lỗi và kết quả kiểm tra từng yếu tố, thay vì gộp chúng thành “thiếu quota”.

## 3. Chuẩn bị quyền hỗ trợ trước sự cố

### 3.1. Kiểm tra danh tính và quyền trên hai lớp

Người trực vận hành cần biết mình đăng nhập vào tenancy nào, bằng tài khoản hoặc identity domain nào, email liên hệ có hoạt động hay không, và ai là người dự phòng.

Lần đầu sử dụng hỗ trợ trong Console có thể có bước xác minh email và bổ sung thông tin liên hệ để thiết lập tài khoản trên My Oracle Cloud Support. Tổ chức còn quản lý user group và quyền hỗ trợ trong cổng này. Chi tiết ở [Configuring Your Oracle Support Account](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/usingsupport.htm).

Hai lớp quyền cần kiểm tra riêng:

1. **OCI IAM:** quyền gọi các thao tác Support Management và quyền đọc tài nguyên, log, metric cần chẩn đoán.
2. **Cổng hỗ trợ:** quyền tạo, xem hoặc cập nhật SR trong user group được chọn.

Có quyền quản lý tài nguyên Compute không có nghĩa đã được thiết lập đầy đủ để tạo SR. Ngược lại, người có quyền tạo SR cũng có thể chưa được phép đọc Audit hoặc log cơ sở dữ liệu. Chuẩn bị sẵn đầu mối có quyền phù hợp giúp tránh chậm trễ khi cần thu thập dữ liệu.

### 3.2. Ví dụ policy cho Support Management

Với hai nhóm IAM có tên minh họa dưới đây, policy mẫu là:

~~~text
Allow group OCISupportReaders to read tickets in tenancy
Allow group OCISupportOperators to manage tickets in tenancy
~~~

Đây là hai nhóm có trách nhiệm khác nhau: nhóm thứ nhất xem yêu cầu; nhóm thứ hai tạo và cập nhật yêu cầu. Điều chỉnh tên nhóm và cách định danh nhóm theo identity domain thực tế khi triển khai. Tài liệu [Securing Support Management](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/support-management.htm) đưa ra các mẫu policy này.

Theo [Support Management IAM Policy Reference](https://docs.oracle.com/en-us/iaas/Content/GSG/support/policy-reference.htm), resource type là `tickets`; quyền tạo và cập nhật cần mức `manage`, còn mức `read` bao phủ việc đọc và liệt kê. Policy này không cấp quyền quản trị Compute, VCN hay Database.

Khi không tạo được SR hoặc SR chỉ hiển thị để đọc, kiểm tra cả IAM lẫn quyền của user group trong cổng hỗ trợ. Với quyền trong cổng, liên hệ Customer User Administrator (CUA) của tổ chức; không giải quyết bằng cách cấp toàn bộ quyền quản trị tenancy cho người dùng.

## 4. Chọn mức nghiêm trọng bằng ảnh hưởng thực tế

Mức nghiêm trọng cần phản ánh ảnh hưởng hiện tại, tính cấp bách và phương án thay thế. Việc một môi trường được gắn nhãn production là thông tin quan trọng nhưng chưa đủ để mô tả mức ảnh hưởng.

Giao diện tạo SR kỹ thuật hiện mô tả các mức từ **Critical issue**, **Significant impairment**, **Technical issue** đến **General guidance**. Hãy đọc định nghĩa và điều kiện hiển thị khi tạo yêu cầu; mức Critical có phần xác nhận yêu cầu liên quan đến sự cố nghiêm trọng. Tham khảo [Creating a Support Request](https://docs.oracle.com/en-us/iaas/Content/GSG/support/create-incident.htm).

Dùng các câu hỏi sau để chuẩn bị phần business impact:

| Câu hỏi | Cách trả lời có thể kiểm chứng |
| --- | --- |
| Chức năng nào bị ảnh hưởng? | Không xác nhận được đơn hàng, không tạo được Compute mới, backup bị lỗi |
| Phạm vi đến đâu? | Một instance, hai subnet, một region hoặc một nhóm người dùng |
| Bắt đầu từ khi nào? | Thời điểm phát hiện, thời điểm lần cuối hoạt động bình thường và thời gian UTC |
| Ảnh hưởng bao nhiêu? | 420/1.000 giao dịch lỗi trong 10 phút; hai node bổ sung không cấp phát được |
| Có phương án thay thế không? | Đang dùng node dự phòng; đáp ứng được tải hiện tại nhưng giảm dự phòng |
| Có hạn chót nghiệp vụ nào? | Cửa sổ backup sắp kết thúc hoặc cần bổ sung năng lực trước đợt tải đã biết |
| Ai có thể phối hợp? | Đầu mối chính, người dự phòng và khoảng thời gian sẵn sàng làm việc |

Không suy từ mức nghiêm trọng ra một thời gian khắc phục chắc chắn. Điều kiện phản hồi, phối hợp và cam kết dịch vụ cần đối chiếu với thỏa thuận hỗ trợ áp dụng. Khi ảnh hưởng thay đổi, cập nhật SR bằng số liệu mới và đề nghị xem xét lại mức độ nếu cần.

Ví dụ diễn đạt:

> Từ 02:10 UTC, hai lần cấp phát node mới cho hệ thống đặt hàng thất bại. Sáu node hiện hữu vẫn phục vụ lưu lượng; chưa ghi nhận giao dịch thất bại do sự cố này. Khả năng mở rộng và phục hồi dự phòng bị giảm trước đợt tăng tải lúc 06:00 UTC.

Đoạn này giúp người nhận hiểu vấn đề rõ hơn một tiêu đề chỉ ghi “Production down”, đồng thời tránh khẳng định hệ thống đã ngừng phục vụ khi số liệu chưa cho thấy điều đó.

## 5. Bộ thông tin định danh tối thiểu

### 5.1. Tài nguyên, vị trí và thời gian

| Trường | Cần ghi | Lưu ý |
| --- | --- | --- |
| Tenancy | Tenancy OCID và tên nhận biết nếu phù hợp | Xác minh đúng tài khoản tổ chức |
| Compartment | Compartment OCID của tài nguyên hoặc thao tác | Không chỉ dùng tên vì có thể trùng |
| Region | Region nơi thao tác hoặc tài nguyên bị ảnh hưởng | Phân biệt với home region của tenancy |
| Availability domain, fault domain | Giá trị thực tế nếu có và liên quan | Không đoán hoặc tự điền cho dịch vụ không áp dụng |
| Tài nguyên | Loại dịch vụ, tên và OCID | Kèm tài nguyên phụ thuộc có liên quan trực tiếp |
| Thời gian | Lần cuối thành công, lần đầu lỗi, thời điểm mẫu và thời điểm phục hồi | Dùng ISO 8601 có múi giờ, ưu tiên UTC |
| Công cụ | Console, OCI CLI, SDK hoặc công cụ IaC và phiên bản | Phân biệt máy người dùng với môi trường CI/CD |
| Thao tác | Tên API, lệnh hoặc chuỗi thao tác thực tế | Loại bỏ thông tin xác thực khỏi câu lệnh |

Ví dụ, `2026-11-21T09:10:00+07:00` tương ứng `2026-11-21T02:10:00Z`. Ghi “sáng nay” làm mất bối cảnh khi người hỗ trợ làm việc ở múi giờ khác.

Nếu chưa biết thời điểm bắt đầu, ghi rõ “lần đầu quan sát thấy” thay vì coi đó là thời điểm lỗi chắc chắn xuất hiện. Giữ các mốc lấy từ đồng hồ máy khách và máy chủ tách biệt nếu nghi có lệch giờ.

### 5.2. Phân biệt các loại ID

| Loại ID | Dùng để làm gì? | Không thay thế cho |
| --- | --- | --- |
| Resource OCID | Xác định đối tượng như instance, subnet, volume hoặc database | Một lần gọi API cụ thể |
| `opc-request-id` | Liên hệ với một lần xử lý yêu cầu API tại dịch vụ | Toàn bộ vòng đời một tác vụ dài |
| Work request ID | Theo dõi thao tác bất đồng bộ và các lỗi hoặc log của nó | Request ID của từng lần gọi đọc trạng thái |
| Application trace ID | Theo dấu yêu cầu trong ứng dụng khi có thiết lập tracing | Bằng chứng rằng OCI đã nhận API tương ứng |
| SR number | Theo dõi hồ sơ trao đổi với Oracle Support | OCID tài nguyên hoặc mã sự cố nội bộ |

Oracle yêu cầu cung cấp `opc-request-id` của response khi cần hỗ trợ cho một API request cụ thể; xem [REST APIs — Request and Response Format](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/usingapi.htm). Lưu nguyên giá trị ID thực tế trong kênh hỗ trợ được phép.

Với tác vụ bất đồng bộ, phản hồi HTTP thành công ban đầu chưa chứng minh việc cấp phát đã hoàn tất. Lưu thêm `opc-work-request-id`, trạng thái cuối cùng, lỗi và tài nguyên liên quan theo [Asynchronous Work Requests](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/workrequests.htm). Không dùng request ID của lệnh đọc trạng thái để mô tả nhầm thành request ID của thao tác tạo ban đầu.

Nếu một thao tác được retry, lập danh sách các lần thử:

~~~text
attempt | time_utc             | operation      | result          | opc_request_id
1       | 2026-11-21T02:10:00Z | LaunchInstance | accepted        | <response-id-1>
2       | 2026-11-21T02:14:00Z | LaunchInstance | accepted        | <response-id-2>

work_request_id   | related_attempt | final_status | observed_at_utc
<work-request-1>  | 1               | FAILED       | 2026-11-21T02:12:00Z
<work-request-2>  | 2               | FAILED       | 2026-11-21T02:16:00Z
~~~

Bảng minh họa chỉ thể hiện cách liên kết dữ liệu. Không lặp lại thao tác tạo tài nguyên chỉ để điền đủ số dòng.

## 6. Tổ chức công việc khi đang xảy ra sự cố

Trong sự cố lớn, khôi phục dịch vụ và thu thập bằng chứng nên có người phụ trách rõ ràng. Không để toàn bộ nhóm ngừng giảm ảnh hưởng để cùng chờ SR được trả lời.

~~~mermaid
flowchart TD
    A["Phát hiện và xác định ảnh hưởng"] --> B["Ghi mốc UTC, tài nguyên và request ID"]
    B --> C["Giảm ảnh hưởng theo runbook"]
    B --> D["Tạo SR với bằng chứng ban đầu"]
    C --> E["Cập nhật kết quả và thay đổi vào timeline"]
    D --> E
    E --> F["Bổ sung chẩn đoán theo câu hỏi cụ thể"]
    F --> G["Xác nhận phục hồi bằng kiểm thử nghiệp vụ"]
    G --> H["Hoàn tất điều tra, đóng SR và theo dõi việc còn lại"]
~~~

Một cách phân công thực tế:

- Người điều phối giữ timeline, đánh giá ảnh hưởng và quyết định các thay đổi vận hành.
- Người làm kỹ thuật thu thập bằng chứng và thực hiện biện pháp giảm ảnh hưởng theo quyền được giao.
- Người liên hệ Support giữ SR được cập nhật, chuyển câu hỏi đúng nhóm và bảo đảm có người theo dõi.

Nhóm nhỏ có thể kiêm nhiệm, nhưng cần ghi rõ ai đang giữ việc nào. Mọi biện pháp như rollback, đổi route, scale, failover hoặc restart đều phải có thời điểm và kết quả trong timeline. Nếu không ghi, một thay đổi do chính nhóm vận hành thực hiện có thể bị hiểu nhầm là diễn biến tự nhiên của sự cố.

## 7. Chọn bằng chứng đúng lớp

### 7.1. Bắt đầu bằng câu hỏi điều tra

Mỗi tệp nên giúp trả lời một câu hỏi:

- Yêu cầu có đến dịch vụ OCI không?
- Lỗi xảy ra khi xác thực, kiểm tra cấu hình hay khi xử lý bất đồng bộ?
- Ảnh hưởng nằm ở một tài nguyên hay nhiều tài nguyên có chung phụ thuộc?
- Có thay đổi cấu hình nào gần thời điểm bắt đầu không?
- Biện pháp giảm ảnh hưởng có làm thay đổi triệu chứng không?

Từ đó chọn dữ liệu tương ứng:

| Lớp | Bằng chứng ưu tiên | Câu hỏi được hỗ trợ |
| --- | --- | --- |
| IAM và API | Principal, compartment, tên thao tác, HTTP status, error code, request ID | Đúng danh tính, phạm vi và loại lỗi chưa? |
| Work request | ID, loại thao tác, thời điểm, trạng thái, lỗi và log | Công đoạn bất đồng bộ nào thất bại? |
| Audit | Sự kiện liên quan đến API và thay đổi cấu hình | Ai gọi thao tác gì và khi nào? |
| Monitoring | Metric, dimension, khoảng thời gian, bước lấy mẫu và alarm | Mức ảnh hưởng thay đổi ra sao? |
| Service log | Log dịch vụ đã được bật và có liên quan | Dịch vụ quan sát được lỗi gì? |
| Hệ điều hành và ứng dụng | Journal, log ứng dụng, phiên bản triển khai, trace | Có vấn đề bên trong workload không? |

Audit ghi hoạt động API của các dịch vụ được hỗ trợ, theo tenancy và compartment. Sự kiện có thể đến trễ; cần kiểm tra đúng phạm vi và cửa sổ thời gian theo [Viewing Audit Log Events](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/viewinglogevents.htm).

Không dùng việc thiếu một sự kiện Audit làm kết luận duy nhất rằng request chưa tồn tại. Tương tự, log dịch vụ chưa được bật trước sự cố có thể không cung cấp dữ liệu quá khứ mà bạn cần.

### 7.2. Compute

Với lỗi cấp phát hoặc instance không truy cập được, chọn dữ liệu phù hợp với triệu chứng:

- Instance OCID nếu đã được tạo; region, availability domain, fault domain, shape và image.
- Trạng thái lifecycle và các mốc tạo, khởi động hoặc dừng quan sát được.
- Work request và lỗi liên quan nếu thao tác hỗ trợ work request.
- Metric sức khỏe, CPU, bộ nhớ hoặc I/O có sẵn; ghi rõ metric nào không được thu thập.
- Log khởi động hoặc serial console history nếu lấy được bằng quyền hiện có.
- Lần cập nhật OS, thay đổi ứng dụng hoặc cấu hình gần nhất nếu có liên quan.

Trạng thái RUNNING chỉ phản ánh một khía cạnh của instance; cần kiểm tra đường truy cập và sức khỏe workload để đánh giá khả năng phục vụ.

Thu thập chẩn đoán cũng khác với thực hiện hành động chẩn đoán gây gián đoạn. Ví dụ, diagnostic reboot dừng, dựng lại rồi khởi động VM và gây downtime; Oracle hướng dẫn dùng sau các bước xử lý khác trong [Performing a Diagnostic Reboot](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/diagnostic-reboot.htm). Không coi thao tác này là bước đọc log thông thường.

### 7.3. VCN và kết nối mạng

Với lỗi mạng, mô tả **nguồn → đích → giao thức → cổng → thời gian** trước khi đính kèm sơ đồ.

Ví dụ: “Từ private IP của app node A đến private endpoint cơ sở dữ liệu B, TCP cổng đang cấu hình, bắt đầu timeout từ 02:10 UTC; node C trong subnet khác vẫn kết nối được”.

Bằng chứng hữu ích gồm:

- VCN, subnet, VNIC và các NSG hoặc security list thực sự áp dụng.
- Route table gắn với subnet và gateway hoặc DRG liên quan trên đường đi.
- Đường về, phân giải DNS, cấu hình firewall của OS nếu có.
- Kết quả kiểm tra từ từng nguồn cùng thời điểm và loại lỗi: timeout, connection refused hay lỗi TLS.
- VCN Flow Logs nếu đã bật cho phạm vi cần quan sát.
- Trạng thái VPN, FastConnect hoặc thiết bị phía khách hàng nếu đường đi có sử dụng.

Một lần ping thất bại chưa đủ chứng minh cổng ứng dụng bị chặn. Không mở toàn bộ ingress để “thử nhanh”; kiểm tra theo đường đi và chỉ thay đổi rule qua quy trình vận hành phù hợp.

### 7.4. Lưu trữ

Với Block Volume, thu thập volume OCID, attachment liên quan, kiểu gắn và kết quả quan sát I/O của OS. Tách dữ liệu về sức khỏe thiết bị, filesystem và ứng dụng để tránh gộp mọi độ trễ thành lỗi volume.

Với Object Storage, ghi region, namespace, bucket, tên thao tác, object liên quan nếu cần, kích thước và kiểu upload. Chỉ rõ request đang dùng cơ chế xác thực nào mà không gửi thông tin xác thực. Không đính kèm nội dung object nếu metadata và log đã đủ cho câu hỏi đang điều tra.

Với File Storage, ghi filesystem, mount target, đường mount, client bị ảnh hưởng và tùy chọn mount liên quan. Mô tả lỗi tại client cùng cấu hình mạng cần thiết.

### 7.5. Dịch vụ cơ sở dữ liệu Oracle

Trước hết xác định sản phẩm: Autonomous Database, Base Database Service, Exadata Database Service hoặc sản phẩm cụ thể khác. Khả năng truy cập OS, công cụ thu thập và trách nhiệm vận hành khác nhau theo sản phẩm.

Thông tin ban đầu thường gồm:

- OCID của tài nguyên dịch vụ bị ảnh hưởng và tài nguyên liên quan.
- Phiên bản hoặc mức vá nếu xem được và có ý nghĩa với vấn đề.
- Mốc lỗi, thao tác, chuỗi lỗi ORA đầy đủ và ứng dụng bị ảnh hưởng.
- Work request khi thao tác quản trị dịch vụ tạo ra work request.
- Bằng chứng về kết nối, tải hoặc backup liên quan trực tiếp đến sự cố.
- Diagnostic bundle, alert log hoặc trace chỉ khi sản phẩm cho phép và cần cho điều tra.

Với môi trường có công cụ như Autonomous Health Framework hoặc Trace File Analyzer, làm theo hướng dẫn dành cho đúng sản phẩm và yêu cầu cụ thể của Support. Không giả định mọi dịch vụ cơ sở dữ liệu đều cho SSH vào host hoặc dùng chung một quy trình thu thập.

SQL text, bind value, trace và dump có thể chứa dữ liệu nghiệp vụ. Cân nhắc phạm vi trước khi xuất; một log chẩn đoán không tự động trở thành dữ liệu có thể chia sẻ rộng rãi.

## 8. Ví dụ thu thập bằng OCI CLI trên PowerShell

Ví dụ sau phù hợp khi cần đọc một Compute instance và tra Audit trong một compartment. Nó **không thu thập toàn bộ** các loại bằng chứng ở phần trên.

Điều kiện:

- OCI CLI đã được cài đặt và xác thực hợp lệ.
- Profile có sẵn với quyền đọc các dữ liệu cần thiết.
- Người chạy thay region, OCID và thời gian bằng giá trị thật.
- Thư mục đầu ra nằm trong vị trí tổ chức cho phép lưu dữ liệu chẩn đoán.

### 8.1. Tạo thư mục riêng và ghi bối cảnh

~~~powershell
$caseProfile = "SUPPORT_READ"
$caseRegion = "ap-singapore-1"
$caseCompartmentId = "<compartment-ocid>"
$caseInstanceId = "<instance-ocid>"
$caseStartUtc = "2026-11-21T02:00:00Z"
$caseEndUtc = "2026-11-21T02:30:00Z"

$caseSuffix = [guid]::NewGuid().ToString("N").Substring(0, 8)
$caseDirName = "oci-diag-" + $caseSuffix
$caseOutputDir = Join-Path $env:TEMP $caseDirName
New-Item -ItemType Directory -Path $caseOutputDir -ErrorAction Stop |
    Out-Null

$caseContext = [ordered]@{
    collectedAtUtc = (Get-Date).ToUniversalTime().ToString("o")
    region = $caseRegion
    compartmentId = $caseCompartmentId
    instanceId = $caseInstanceId
    startUtc = $caseStartUtc
    endUtc = $caseEndUtc
    purpose = "Read-only collection for a specific incident"
}

$caseContext | ConvertTo-Json |
    Out-File -LiteralPath (Join-Path $caseOutputDir "context.json") -Encoding utf8

oci --version 2>&1 |
    Out-File -LiteralPath (Join-Path $caseOutputDir "oci-version.txt") -Encoding utf8

Write-Output $caseOutputDir
~~~

`SUPPORT_READ` chỉ là tên profile minh họa, không phải cơ chế tự cấp quyền đọc. Cần xác minh quyền thật của danh tính trong profile. Không đưa file cấu hình xác thực vào gói gửi đi.

### 8.2. Đọc trạng thái Compute

~~~powershell
$caseInstanceArgs = @(
    "compute", "instance", "get",
    "--instance-id", $caseInstanceId,
    "--region", $caseRegion,
    "--profile", $caseProfile,
    "--output", "json"
)

& oci @caseInstanceArgs 2> (Join-Path $caseOutputDir "instance-get.stderr.txt") |
    Out-File -LiteralPath (Join-Path $caseOutputDir "instance-get.raw.json") -Encoding utf8

$caseInstanceExitCode = $LASTEXITCODE
Write-Output "instance-get exit code: $caseInstanceExitCode"
~~~

Giữ cả stderr khi lệnh lỗi. Nếu instance không còn tồn tại hoặc chưa từng có OCID, ghi rõ tình trạng đó và ưu tiên dữ liệu từ yêu cầu ban đầu cùng work request, thay vì cố tạo lại tài nguyên chỉ để lấy thông tin.

Output có thể chứa metadata hoặc tên nội bộ; coi đây là dữ liệu thô cần rà soát trước khi chia sẻ.

### 8.3. Đọc Audit trong một cửa sổ thời gian hẹp

~~~powershell
$caseAuditArgs = @(
    "audit", "event", "list",
    "--compartment-id", $caseCompartmentId,
    "--start-time", $caseStartUtc,
    "--end-time", $caseEndUtc,
    "--region", $caseRegion,
    "--profile", $caseProfile,
    "--all",
    "--output", "json"
)

& oci @caseAuditArgs 2> (Join-Path $caseOutputDir "audit.stderr.txt") |
    Out-File -LiteralPath (Join-Path $caseOutputDir "audit.raw.json") -Encoding utf8

$caseAuditExitCode = $LASTEXITCODE
Write-Output "audit-list exit code: $caseAuditExitCode"
~~~

Lệnh chỉ lấy compartment và region được chỉ định. Nó không tự tìm mọi compartment hoặc mọi region trong tenancy. `--all` lấy các trang kết quả của truy vấn; vì vậy giới hạn cửa sổ thời gian theo sự cố trước khi chạy. Tham số thời gian của Audit cần độ chính xác đến phút, với giây bằng 0 theo [OCI CLI — audit event list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/audit/event/list.html).

Nếu dữ liệu chưa xuất hiện, xem xét độ trễ xử lý, quyền và phạm vi truy vấn. Không thay bằng việc xuất vô hạn toàn bộ Audit của tenancy.

### 8.4. Lấy work request và thông tin debug có chủ đích

Từ trang tài nguyên trong Console, tìm work request liên quan, mở trạng thái và lấy lỗi hoặc log được cung cấp. Đường dẫn và khả năng hiển thị khác nhau theo dịch vụ; xem [Work Requests](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/workrequestoverview.htm).

Nếu cần CLI debug để điều tra một lệnh đọc:

1. Chỉ bật `--debug` cho lần chạy được chọn.
2. Thu cả stdout và stderr vào vùng lưu trữ hạn chế truy cập.
3. Ghi thời gian chạy và phân biệt request mới này với request lỗi ban đầu.
4. Rà soát header, payload, metadata và dữ liệu nhận về trước khi gửi.

Debug cho một lệnh `get` không thể khôi phục đầy đủ request ID của lệnh `create` đã chạy trước đó. Tránh chạy lại thao tác có tác dụng phụ chỉ để lấy debug. Với ứng dụng dùng SDK, nên thiết kế logging để ghi request ID và bối cảnh lỗi từ đầu, đồng thời loại trừ credential và dữ liệu nghiệp vụ không cần thiết.

## 9. Đóng gói và bảo vệ thông tin chẩn đoán

### 9.1. Phân biệt bản gốc và bản gửi hỗ trợ

Giữ bản gốc trong kho nội bộ có kiểm soát truy cập. Tạo bản đã làm sạch để gửi Oracle và ghi rõ phần nào đã loại bỏ. Việc che dữ liệu cần giữ được tính liên kết: cùng một địa chỉ hoặc người dùng phải được thay bằng cùng một nhãn nếu chúng cần đối chiếu qua nhiều log.

Các loại thông tin cần đặc biệt rà soát:

| Loại dữ liệu | Cách xử lý trước khi gửi |
| --- | --- |
| Private key, mật khẩu, token, client secret, cookie phiên | Loại bỏ khỏi nội dung; nếu đã lộ thì xử lý thu hồi hoặc thay thế theo quy trình |
| OCI config, biến môi trường, file state IaC | Không gửi nguyên bộ; trích trường cần thiết và rà soát giá trị nhạy cảm |
| Database wallet hoặc tài liệu chứa credential | Không đưa vào gói chẩn đoán thông thường |
| HAR và HTTP trace | Rà soát header xác thực, cookie, query string, request và response body |
| SQL, trace, dump, object hoặc payload ứng dụng | Xác định dữ liệu cá nhân và dữ liệu nghiệp vụ trước khi xuất |
| OCID và địa chỉ mạng | Cung cấp khi cần định danh trong SR được phép; cân nhắc khi đưa lên diễn đàn công khai |

Không che mất toàn bộ OCID hoặc request ID mà Oracle cần dùng để tìm sự kiện trong hồ sơ được phép. Nếu chính sách tổ chức hạn chế chia sẻ, nêu hạn chế với Support để thống nhất cách cung cấp phù hợp.

Đính kèm qua cổng hỗ trợ hoặc kênh upload được xác minh cho SR. Không tạo bucket public hoặc URL truy cập công khai chỉ để chuyển một diagnostic bundle.

### 9.2. Gói nhỏ nhưng có chỉ dẫn

Một gói đã làm sạch có thể tổ chức như sau:

~~~text
diagnostics-sanitized/
  manifest.txt
  timeline.csv
  request-attempts.csv
  instance-summary.json
  work-request-errors.txt
  audit-extract.json
  metrics-window.png
  network-path.txt
~~~

Đây là gợi ý tổ chức, không phải bộ file bắt buộc cho mọi SR. Chỉ giữ tệp liên quan đến câu hỏi điều tra.

Ví dụ nội dung `manifest.txt`:

~~~text
Incident reference: INC-EXAMPLE-001
Affected service: OCI Compute
Region: ap-singapore-1
Incident window UTC: 2026-11-21T02:10:00Z to 2026-11-21T02:25:00Z
Collection time UTC: 2026-11-21T02:28:00Z

timeline.csv:
  Observations and operator actions; all timestamps are UTC.

request-attempts.csv:
  Initial API requests linked to asynchronous work requests.

audit-extract.json:
  Relevant entries from the affected compartment only.

Redaction:
  Customer identifiers replaced with stable labels.
  Authentication material and unrelated payloads removed.

Gaps:
  No guest OS logs: the affected instances did not finish provisioning.
  No complete historical flow logs available for this window.
~~~

Ghi rõ khoảng trống bằng chứng tốt hơn điền suy đoán. Nếu dùng ảnh biểu đồ, giữ tên metric, resource dimension, khoảng thời gian, múi giờ và độ phân giải; ảnh bị cắt mất trục thời gian thường khó sử dụng.

Sau khi hoàn tất bản gửi đi, có thể lập checksum cho các file cuối cùng để đối chiếu khi bàn giao. Nếu tiếp tục chỉnh sửa hoặc che dữ liệu, phải tính lại checksum. Không coi checksum là phương thức che nội dung hay cấp quyền truy cập.

## 10. Soạn nội dung SR để người nhận có thể bắt đầu điều tra

Một bản mô tả tốt tách rõ **dữ kiện**, **giả thuyết** và **đề nghị hỗ trợ**. Không ghi giả thuyết như kết luận đã được xác nhận.

### 10.1. Tiêu đề có phạm vi và triệu chứng

Mẫu:

~~~text
[Service][Region][Environment] Observed symptom since <UTC time>
~~~

Ví dụ:

~~~text
[Compute][ap-singapore-1][Production]
New instance provisioning fails; existing instances remain available
~~~

Không đưa mật khẩu, tên khách hàng hoặc nội dung giao dịch vào tiêu đề.

### 10.2. Mẫu mô tả có thể sử dụng

~~~text
1. Summary
   We observe <specific symptom> on <service> in <region>.

2. Business impact
   Affected function:
   Affected users, requests or resources:
   Current measured error rate or loss of capacity:
   Workaround and remaining risk:
   Relevant business deadline:
   Requested severity and reason:

3. Timeline (UTC)
   Last known successful operation:
   First observed failure:
   Selected failed attempts:
   Mitigation actions and observed results:
   Current status:

4. Environment and identifiers
   Tenancy OCID:
   Compartment OCID:
   Region:
   Availability domain / fault domain, if relevant:
   Resource OCIDs:
   Client or tool version:
   Authentication method (no credentials):

5. Operation and observations
   Expected result:
   Actual result:
   Exact error code and sanitized message:
   Original response opc-request-id:
   Related work request ID and final status:
   Frequency and scope:

6. Checks already performed
   Check:
   Time performed:
   Result:
   Supporting attachment or evidence reference:

7. Recent changes
   Confirmed changes:
   Unknown or unverified items:

8. Evidence
   Attachment manifest:
   Collection window and time zone:
   Redactions and missing data:

9. Assistance requested
   Please investigate <specific unresolved question>.
   Please advise on <safe next diagnostic step or mitigation>.
   RCA requested if appropriate.

10. Contacts
    Primary and backup contacts:
    Time zone and availability:
    Internal incident reference:
~~~

Mẫu dùng tiếng Anh để thuận tiện khi tổ chức cần phối hợp quốc tế; có thể điền ngôn ngữ theo cách làm việc với Support. Giá trị của mẫu nằm ở cấu trúc và dữ kiện, không nằm ở việc dùng một ngôn ngữ cố định.

Phần “Checks already performed” phải có kết quả. “Đã kiểm tra mạng” quá rộng; “02:18 UTC, kiểm tra route table gắn với subnet X, không phát hiện thay đổi so với cấu hình đã phê duyệt; trích xuất ở tệp Y” giúp người nhận quyết định bước tiếp theo.

### 10.3. Yêu cầu hỗ trợ rõ ràng

Các câu hỏi có thể đặt:

- Xin kiểm tra nguyên nhân work request cụ thể thất bại trong cửa sổ đã nêu.
- Xin xác nhận có sự cố dịch vụ hoặc hạn chế đã biết liên quan đến các ID này không.
- Xin hướng dẫn bước chẩn đoán tiếp theo với mức ảnh hưởng và quyền truy cập hiện có.
- Sau khi phục hồi, xin làm rõ nguyên nhân và khuyến nghị phòng ngừa nếu có thể cung cấp.

Không yêu cầu Support xác nhận một nguyên nhân đã đoán trước khi bằng chứng chưa đủ. Chẳng hạn, “xin kiểm tra work request thất bại” tạo phạm vi điều tra tốt hơn “hãy sửa hypervisor lỗi” khi chưa có bằng chứng về host.

## 11. Tạo và xác nhận yêu cầu đã được ghi nhận

Trong OCI Console, mở menu **Help**, chọn **Create a Support request** hoặc đi qua **Support Center**. Chọn loại yêu cầu phù hợp, điền mô tả, mức ảnh hưởng và phân loại dịch vụ. Với SR kỹ thuật, chọn user group hỗ trợ có quyền và khả năng theo dõi hồ sơ. Xem các bước và trường hiện hành trong [Creating a Support Request](https://docs.oracle.com/en-us/iaas/Content/GSG/support/create-incident.htm).

Tên nút và các bước trung gian có thể khác theo luồng hỗ trợ hoặc quá trình chuyển sang My Oracle Cloud Support. Khi giao diện khác bài hướng dẫn, dùng tài liệu Oracle để xác nhận đường đi tương ứng.

Trước khi gửi:

1. Xác nhận đúng tenancy, region, dịch vụ và thông tin liên hệ.
2. Đọc lại mức ảnh hưởng cùng dữ kiện đang có.
3. Kiểm tra tệp đính kèm thuộc bản đã làm sạch và tuân theo giới hạn hiển thị trên cổng.
4. Bảo đảm ít nhất một người có thể theo dõi phản hồi.

Sau khi gửi, lưu SR number và liên kết hồ sơ trong bản ghi sự cố nội bộ. Xác nhận người trực hoặc người dự phòng nhìn thấy yêu cầu và có quyền cập nhật. Đừng coi việc đã bấm nút gửi là bằng chứng duy nhất rằng yêu cầu đã được tiếp nhận.

Khi không thấy SR, kiểm tra tài khoản, user group, bộ lọc và cổng đang sử dụng trước khi tạo thêm hồ sơ. [Listing Support Requests](https://docs.oracle.com/en-us/iaas/Content/GSG/support/list-incidents.htm) giải thích việc hiển thị phụ thuộc user group, quyền và thông tin SR đã được chuyển cổng nếu có.

Nếu không đăng nhập được Console, sử dụng kênh hỗ trợ đăng nhập được Oracle hướng dẫn tại [Troubleshooting Signing In to the Console](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signinginIdentityDomain.htm). Không giao mật khẩu hoặc mã MFA cho người khác để họ mở SR thay.

## 12. Theo dõi SR và làm việc với Support

### 12.1. Mỗi lần cập nhật đều có thông tin mới

Một cập nhật ngắn nên có:

~~~text
Update time UTC: 2026-11-21T02:40:00Z

Current impact:
  Existing application nodes remain available.
  New provisioning remains blocked.

New observation:
  The same work request is still FAILED; no new create attempts were made.

Action performed:
  Compared relevant configuration with the approved deployment baseline.

Result:
  No difference found in the reviewed fields.
  This does not establish the root cause.

Evidence added:
  sanitized-comparison.txt, covering the fields listed in its header.

Assistance needed:
  Please review the asynchronous failure for the work request already provided.

Next coordination:
  Primary and backup contacts are available during the stated support window.
~~~

Phân biệt “không thấy khác biệt trong các trường đã kiểm tra” với “không có thay đổi nào”. Câu đầu nêu được giới hạn của bằng chứng.

Khi Oracle yêu cầu chạy lệnh hoặc thay đổi cấu hình, xác nhận:

- Đúng tài nguyên, sản phẩm, phiên bản và phạm vi môi trường.
- Mục tiêu của thao tác và dữ liệu mong đợi.
- Tác động tới tính sẵn sàng, hiệu năng, dung lượng và chi phí.
- Người thực hiện, cửa sổ thay đổi và cách phục hồi nếu có tác động vận hành.

Nếu hướng dẫn chưa rõ, hỏi lại trên SR trước khi chạy thao tác có thể dừng máy, failover, tạo dump lớn hoặc thay đổi dữ liệu. Ghi cả kết quả thành công và thất bại của bước được yêu cầu.

### 12.2. Escalate bằng lý do cụ thể

Cân nhắc yêu cầu điều phối hoặc escalation khi ảnh hưởng tăng, phương án tạm thời không còn đáp ứng, hoặc quá trình trao đổi chưa đáp ứng điều kiện hỗ trợ áp dụng.

Bổ sung số liệu, hạn chót và hành động mong muốn vào hồ sơ hiện hữu. Dùng quy trình escalation được chỉ định trên cổng hoặc trong thỏa thuận hỗ trợ; tránh mở nhiều SR trùng nhau chỉ để tăng chú ý. Nếu cần nhiều SR cho các vấn đề khác nhau, liên kết chúng và mô tả phạm vi từng hồ sơ.

Bàn giao ca trực cần có SR number, trạng thái ảnh hưởng, câu hỏi đang chờ, người giữ hành động tiếp theo và thời điểm cập nhật gần nhất. Email thông báo không thay thế cho việc có người thực sự theo dõi hồ sơ.

## 13. Tình huống thực hành: cấp phát Compute thất bại

### 13.1. Dữ kiện ban đầu

Một nhóm vận hành hệ thống đặt hàng tại region minh họa `ap-singapore-1`. Sáu instance hiện tại vẫn phục vụ, nhưng hai thao tác bổ sung instance thất bại ở giai đoạn bất đồng bộ.

Timeline được ghi nhận:

| Thời điểm UTC | Quan sát hoặc hành động |
| --- | --- |
| 01:50 | Ghi nhận lần cấp phát thành công gần nhất trong cửa sổ đã kiểm tra |
| 02:10 | Thao tác cấp phát thứ nhất được chấp nhận |
| 02:12 | Work request thứ nhất chuyển FAILED |
| 02:14 | Một thao tác thử lại có kiểm soát được thực hiện |
| 02:16 | Work request thứ hai chuyển FAILED |
| 02:18 | Nhóm ngừng thử tạo thêm và thu thập ID, lỗi cùng cấu hình liên quan |
| 02:25 | Xác nhận sáu node cũ vẫn phục vụ; chưa thấy giao dịch lỗi do sự cố này |

Các thông tin này là dữ kiện của bài thực hành, không mô tả một sự cố thật của Oracle.

### 13.2. Cách xây dựng hồ sơ

Nhóm chuẩn bị:

1. Tenancy, compartment, region và ID của cả hai lần thử.
2. Request ID của phản hồi cấp phát và work request ID tương ứng.
3. Lỗi bất đồng bộ nguyên văn từ work request, đã rà soát dữ liệu nhạy cảm.
4. Shape, image, availability domain, subnet và thông số triển khai liên quan.
5. Kết quả kiểm tra service limit, quota áp dụng và thay đổi cấu hình.
6. Bằng chứng sáu node cũ vẫn phục vụ cùng mức dự phòng còn lại.
7. Câu hỏi yêu cầu Oracle điều tra nguyên nhân thất bại của hai work request.

Nhóm không ghi “chắc chắn thiếu capacity” nếu chỉ có dữ kiện cấp phát thất bại. Không tự nâng severity lên mức cao nhất khi chưa có ảnh hưởng tương ứng.

### 13.3. Giảm ảnh hưởng và kiểm soát chi phí

Người điều phối đánh giá việc dùng năng lực dự phòng đã có hoặc chọn cấu hình thay thế được phê duyệt. Thay đổi shape, vị trí triển khai hay region có thể ảnh hưởng hiệu năng, địa chỉ mạng, giấy phép, kết nối dữ liệu và chi phí; cần xét theo kiến trúc thực tế.

Trong lúc điều tra:

- Giới hạn số lần thử và ghi kết quả từng lần; dừng khi đã có đủ bằng chứng lặp lại.
- Kiểm tra xem lần thử timeout có để lại tài nguyên đang chạy hoặc đang tạo không.
- Ghi nhận tài nguyên tạm được tạo để phục hồi và người chịu trách nhiệm thu hồi.
- Thu hồi log debug bổ sung và điều chỉnh phạm vi thu thập sau khi hết nhu cầu.
- Theo dõi chi phí lưu diagnostic bundle và thời gian giữ theo quy định nội bộ.

Không xóa tài nguyên liên quan một cách vội vàng khi còn cần điều tra. Khi phải dọn dẹp, lưu định danh, cấu hình và bằng chứng cần thiết trước, đồng thời ghi hành động vào timeline.

## 14. Xác nhận phục hồi và đóng hồ sơ

“Không còn nhìn thấy lỗi” là một tín hiệu, nhưng cần kiểm tra lại chức năng đã bị ảnh hưởng.

Với tình huống cấp phát Compute, tiêu chí xác nhận có thể gồm một lần triển khai đã được phê duyệt hoàn tất, instance đạt trạng thái mong muốn, workload kiểm tra đạt và năng lực dự phòng được khôi phục. Nếu việc kiểm chứng phát sinh tài nguyên hoặc chi phí, thực hiện theo nhu cầu triển khai thật hoặc kế hoạch thử được chấp thuận.

Trước khi đóng SR:

- Ghi thời điểm bắt đầu phục hồi và khoảng quan sát ổn định.
- Nêu kết quả kiểm tra nghiệp vụ hoặc hạ tầng liên quan.
- Ghi biện pháp đã giúp phục hồi và mức chắc chắn của nhận định.
- Làm rõ câu hỏi còn mở, nhu cầu RCA và cách theo dõi tiếp theo.
- Thu hồi quyền tạm, cấu hình debug và tài nguyên tạm không còn cần.
- Lưu hồ sơ nội bộ theo thời hạn phù hợp và xác nhận nhóm phụ trách đồng ý kết thúc.

Phân biệt ba trạng thái nhận thức: dịch vụ đã phục hồi; nguyên nhân đã được xác nhận; biện pháp phòng ngừa đã được triển khai. Chúng có thể đạt được ở các thời điểm khác nhau. Nếu phục hồi nhưng nguyên nhân chưa rõ, hãy ghi đúng tình trạng và thống nhất việc điều tra tiếp với Support.

## 15. Những lỗi thường làm hồ sơ bị chậm

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ đính kèm ảnh lỗi | Thiếu ID, mốc thời gian hoặc chuỗi lỗi có thể tìm kiếm | Thêm văn bản và định danh gốc cần thiết |
| Ghi sai region hoặc nhầm compartment | Tìm sai phạm vi | Lấy giá trị từ tài nguyên và request thực tế |
| Gửi request ID của một lệnh đọc mới | Không tìm đúng thao tác lỗi ban đầu | Liên kết từng ID với thao tác và thời điểm |
| Chỉ ghi HTTP thành công ban đầu | Bỏ qua lỗi bất đồng bộ | Thêm trạng thái và lỗi work request |
| Gửi cả log nhiều ngày | Chậm chuyển dữ liệu, tăng phần không liên quan | Lọc theo cửa sổ, tài nguyên và câu hỏi |
| Che mất mọi ID cần tra cứu | Support không đủ dữ liệu để tìm sự kiện | Chia sẻ định danh cần thiết qua kênh được phép |
| Gửi nguyên credential hoặc wallet | Lộ thông tin xác thực | Làm sạch, hạn chế truy cập và xử lý bí mật đã lộ |
| Restart hoặc xóa ngay tài nguyên | Mất bằng chứng, thay đổi triệu chứng | Lưu bằng chứng và đánh giá tác động trước hành động |
| Chỉ ghi “đã kiểm tra” | Khó biết còn cần kiểm tra gì | Ghi phạm vi, thời gian, kết quả và tệp chứng minh |
| Không có người theo dõi SR | Câu hỏi hỗ trợ bị chờ qua nhiều ca | Chỉ định người chính và người dự phòng |

## 16. Thực hành hoàn chỉnh trên môi trường học tập

Chọn một tình huống giả lập phù hợp với tài nguyên bạn được phép quan sát, chẳng hạn một bản ghi lỗi cấp phát đã có hoặc một lỗi kết nối từ log mẫu đã được làm sạch. Không tạo downtime trên môi trường dùng chung để có dữ liệu.

Hoàn thành theo trình tự:

1. Viết mô tả ảnh hưởng trong ba đến năm câu, nêu dữ kiện nào là giả lập.
2. Ghi tenancy, compartment, region và tài nguyên liên quan bằng placeholder nếu chỉ làm tài liệu.
3. Chuẩn hóa timeline sang UTC, giữ lại múi giờ ban đầu nếu cần đối chiếu.
4. Liệt kê request ID, work request ID và khoảng trống thông tin; không tự tạo ID rồi trình bày như dữ kiện thật.
5. Chọn tối đa những bằng chứng trực tiếp trả lời câu hỏi điều tra, lập manifest và rà soát dữ liệu nhạy cảm.
6. Điền mẫu SR ở phần 10, kèm mức nghiêm trọng đề xuất và lý do.
7. Viết một cập nhật giữa sự cố và một bản ghi xác nhận phục hồi.
8. Liệt kê tài nguyên tạm, quyền tạm, log bổ sung và việc dọn dẹp cần theo dõi.

Bản nháp đạt yêu cầu khi người khác có thể xác định đúng phạm vi, hiểu mức ảnh hưởng, tìm từng bằng chứng và biết Oracle cần giúp giải quyết câu hỏi nào. Giữ bài thực hành ở dạng nháp; chỉ mở SR thật cho nhu cầu hỗ trợ thực tế thuộc quyền của tổ chức.
