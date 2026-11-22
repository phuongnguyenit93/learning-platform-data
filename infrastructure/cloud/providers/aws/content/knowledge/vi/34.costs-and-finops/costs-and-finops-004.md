# Cost Explorer và phân tích biến động sử dụng

AWS Cost Explorer là công cụ phân tích chi phí và mức sử dụng trong AWS Billing and Cost Management. Công cụ giúp đội kỹ thuật và tài chính trả lời các câu hỏi như: tháng này chi phí tăng ở dịch vụ nào, tài khoản nào tạo ra phần tăng, khu vực hoặc loại tài nguyên nào đang tiêu thụ nhiều hơn, khoản tăng đến từ khối lượng sử dụng hay đơn giá, và xu hướng hiện tại có thể đưa chi phí cuối tháng đến đâu.

Trong thực hành FinOps, Cost Explorer là điểm bắt đầu để quan sát và đặt câu hỏi. Người phân tích cần kết hợp dữ liệu thanh toán với thông tin triển khai, lưu lượng, số giao dịch, lịch phát hành và thay đổi kiến trúc để tìm nguyên nhân. Một biểu đồ tăng chi phí chỉ là tín hiệu; nó chưa phải lời giải thích.

Bài học đặt Cost Explorer trong bối cảnh vận hành AWS gồm Region/AZ, tài khoản, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, mạng và các dịch vụ tích hợp. Mục tiêu là biến dữ liệu chi phí thành quyết định kỹ thuật có thể kiểm chứng, đồng thời giữ được tính bảo mật, khả năng giám sát và kiểm soát chi phí.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Mở Cost Explorer, chọn kỳ phân tích, độ chi tiết, chỉ số chi phí, bộ lọc và nhóm dữ liệu phù hợp.
- Phân biệt các chỉ số UnblendedCost, AmortizedCost, BlendedCost, NetUnblendedCost, NetAmortizedCost và UsageQuantity.
- So sánh hai kỳ, tính mức chênh lệch tuyệt đối và phần trăm, xác định dịch vụ/tài khoản/Region đóng góp nhiều nhất.
- Tách biến động do khối lượng, đơn giá và cơ cấu sử dụng; chuẩn hóa chi phí theo đơn vị nghiệp vụ.
- Đọc xu hướng và dự báo có xét đến độ trễ dữ liệu, mùa vụ và thay đổi cấu hình.
- Phân tích tác động của Reserved Instances và Savings Plans bằng chỉ số phù hợp.
- Kết hợp tag, Cost Categories, AWS Organizations, Cost and Usage Data Exports và quy trình FinOps để phân bổ trách nhiệm.
- Đưa ra hành động tối ưu có chủ sở hữu, giả thuyết, cách đo trước/sau và tiêu chí hoàn tất.

## 2. Cost Explorer nằm ở đâu trong hệ sinh thái quản lý chi phí

Cost Explorer cung cấp giao diện truy vấn và trực quan hóa dữ liệu chi phí, mức sử dụng và một số thông tin liên quan đến cam kết mua trước. Người dùng có thể xem dữ liệu theo thời gian, lọc theo thuộc tính, nhóm theo chiều phân tích và lưu báo cáo để dùng lại.

Cần phân biệt các công cụ thường được sử dụng cùng nhau:

| Công cụ | Câu hỏi chính | Cách sử dụng |
|---|---|---|
| AWS Cost Explorer | Chi phí và mức sử dụng đã thay đổi ở đâu, theo chiều nào? | Phân tích tương tác, so sánh kỳ, nhóm dữ liệu và xem dự báo |
| AWS Budgets | Chi phí hoặc mức sử dụng có vượt ngưỡng đã đặt không? | Ngân sách, ngưỡng cảnh báo và hành động theo cấu hình |
| AWS Cost Anomaly Detection | Có mẫu chi phí bất thường so với hành vi thông thường không? | Phát hiện bất thường bằng mô hình học máy và gửi cảnh báo |
| AWS Data Exports / Cost and Usage Report (CUR) | Những dòng chi tiết nào tạo nên số tiền tổng hợp? | Xuất dữ liệu chi tiết để truy vấn bằng Athena, BI hoặc hệ thống nội bộ |
| Billing console / invoice | Số tiền nào được lập hóa đơn và cần thanh toán? | Đối chiếu hóa đơn, thuế, tín dụng, điều chỉnh và kỳ thanh toán |

Cost Explorer phù hợp để khám phá và định hướng điều tra. Khi cần truy nguyên đến dòng usage cụ thể, resource ID, reservation, Savings Plan hoặc trường dữ liệu chi tiết, hãy dùng Data Exports/CUR nếu báo cáo đã được cấu hình và có các cột cần thiết.

Cost Explorer không thay thế quy trình kiểm soát ngân sách, cảnh báo, phê duyệt thay đổi hạ tầng hoặc đối soát hóa đơn. Một tổ chức thường kết hợp các công cụ này: Cost Explorer giải thích xu hướng, Budgets kiểm soát ngưỡng, Cost Anomaly Detection phát hiện độ lệch đáng chú ý, còn CUR/Data Exports hỗ trợ truy vấn sâu.

## 3. Hiểu phạm vi dữ liệu và độ trễ

Dữ liệu chi phí được tổng hợp từ hoạt động sử dụng dịch vụ AWS và thông tin thanh toán. Phạm vi hiển thị phụ thuộc vào tài khoản đang đăng nhập, quyền truy cập Billing, cấu hình AWS Organizations và việc người dùng đang xem dữ liệu của payer/management account hay linked account.

Trong môi trường nhiều tài khoản:

- Payer account hoặc management account thường là điểm quan sát tổng thể của tổ chức.
- Linked account giúp tách chi phí theo ứng dụng, môi trường, đội hoặc đơn vị kinh doanh.
- Tài khoản thành viên có thể chỉ thấy phạm vi dữ liệu mà quyền và cấu hình Billing cho phép.
- Việc hợp nhất thanh toán không có nghĩa mọi người dùng trong mọi tài khoản đều tự động có quyền xem toàn bộ chi phí.

Dữ liệu Cost Explorer không phải luồng telemetry thời gian thực. Dữ liệu sử dụng và chi phí có thể được cập nhật nhiều lần trong ngày nhưng vẫn có độ trễ; một số khoản điều chỉnh, tín dụng, hoàn tiền hoặc phí cuối kỳ có thể xuất hiện muộn hơn. Vì vậy, khi so sánh một kỳ đang diễn ra với kỳ đã đóng, hãy ghi rõ thời điểm trích xuất và trạng thái dữ liệu.

Các nguyên tắc khi chọn kỳ:

1. Dùng kỳ đã hoàn tất để đánh giá kết quả tài chính đã ổn định hơn.
2. Với tháng hiện tại, so sánh cùng số ngày đã trôi qua hoặc cùng thứ trong tuần nếu mức sử dụng có tính mùa vụ.
3. Tránh so sánh 10 ngày đầu tháng này với cả tháng trước.
4. Ghi rõ múi giờ và ngày bắt đầu/kết thúc của báo cáo. Các truy vấn API sử dụng khoảng thời gian với ngày kết thúc không bao gồm trong kết quả.
5. Khi số liệu khác hóa đơn, kiểm tra metric, kỳ, phạm vi tài khoản, credits/refunds/tax, điều chỉnh và độ trễ trước khi kết luận có lỗi.

Một biểu đồ chỉ có ý nghĩa khi người đọc biết nó bao phủ tài khoản nào, khoảng thời gian nào, metric nào và loại chi phí nào.

## 4. Các chỉ số chi phí cần phân biệt

Cost Explorer hỗ trợ nhiều metric. Chọn sai metric có thể khiến hai báo cáo cùng một kỳ cho ra số khác nhau mà cả hai đều đúng theo định nghĩa của chúng.

| Metric | Ý nghĩa thực hành | Khi nên dùng |
|---|---|---|
| UnblendedCost | Chi phí áp dụng theo mức giá chưa pha trộn cho từng dòng sử dụng/tài khoản | Theo dõi chi phí gắn với mức sử dụng và giá được áp dụng |
| AmortizedCost | Phân bổ dần khoản trả trước của Reserved Instances/Savings Plans trong thời hạn cam kết | Xem run-rate kinh tế theo thời gian, tránh để khoản trả trước làm méo một ngày/tháng |
| BlendedCost | Chi phí theo mức giá pha trộn trong bối cảnh consolidated billing đủ điều kiện | Phân tích theo góc nhìn blended của tổ chức khi mô hình thanh toán sử dụng khái niệm này |
| NetUnblendedCost | Chi phí unblended sau khi tính các khoản giảm giá đủ điều kiện được phản ánh trong dữ liệu net | Đánh giá chi phí sau giảm giá theo cơ sở unblended |
| NetAmortizedCost | Chi phí amortized sau khi tính các khoản giảm giá đủ điều kiện được phản ánh trong dữ liệu net | Theo dõi chi phí kinh tế sau giảm giá và phân bổ cam kết |
| UsageQuantity | Lượng sử dụng được ghi nhận cho các loại usage | Phân tích khối lượng khi đơn vị đo đồng nhất |
| NormalizedUsageAmount | Lượng sử dụng đã chuẩn hóa theo hệ số chuẩn hóa của loại tài nguyên được hỗ trợ | So sánh mức sử dụng của các kích thước instance có thể quy đổi, đặc biệt trong phân tích RI size flexibility |

### 4.1 UnblendedCost và AmortizedCost

Giả sử tổ chức mua một Reserved Instance với khoản trả trước. UnblendedCost có thể ghi nhận khoản phí trả trước tại thời điểm phát sinh. Nếu nhìn riêng tháng mua, biểu đồ có thể tăng mạnh dù năng lực tính toán được sử dụng ổn định trong cả thời hạn cam kết.

AmortizedCost phân bổ khoản trả trước theo thời gian cam kết, giúp phân tích chi phí kinh tế của việc sử dụng năng lực đó trong từng kỳ. Đây thường là metric hữu ích khi đội FinOps muốn so sánh chi phí vận hành theo tháng và đánh giá hiệu quả cam kết dài hạn.

Hai metric trả lời hai câu hỏi khác nhau:

- UnblendedCost: các khoản chi phí được ghi nhận theo cách unblended trong kỳ là bao nhiêu?
- AmortizedCost: phần chi phí cam kết được phân bổ vào kỳ này là bao nhiêu?

Không nên cộng số liệu từ hai metric với nhau hoặc so sánh một báo cáo dùng UnblendedCost với báo cáo dùng AmortizedCost mà không ghi rõ cơ sở.

### 4.2 Net cost và blended cost

Các metric có tiền tố Net phản ánh các khoản giảm giá đủ điều kiện được đưa vào dữ liệu net. Khả năng hiển thị và ý nghĩa của chúng phụ thuộc vào chương trình giá, loại tài khoản và dữ liệu thanh toán. Hãy kiểm tra metric được chọn thay vì giả định Net luôn bằng hóa đơn cuối cùng.

BlendedCost có ý nghĩa trong bối cảnh consolidated billing và cách phân bổ mức giá giữa các tài khoản. Khi cần xác định chi phí kinh tế theo tài khoản sử dụng, hãy thống nhất chính sách nội bộ về việc dùng blended hay unblended. Không dùng blended chỉ vì số liệu có vẻ dễ phân bổ hơn.

### 4.3 UsageQuantity phải đi cùng đơn vị

UsageQuantity có thể chứa giờ instance, GB-month, request, số lần gọi API hoặc các đơn vị khác. Tổng 1.000 giờ instance cộng 2.000 GB-month không tạo thành một đại lượng có ý nghĩa.

Khi phân tích UsageQuantity:

- Nhóm theo Usage Type hoặc loại tài nguyên để bảo đảm cùng đơn vị.
- Kiểm tra đơn vị đo trước khi cộng hoặc tính trung bình.
- Nếu cần tổng lượng sử dụng, chỉ cộng các dòng cùng đơn vị và cùng phạm vi nghiệp vụ.
- Khi có nhiều kích thước instance, cân nhắc NormalizedUsageAmount nếu loại tài nguyên và chương trình RI hỗ trợ quy đổi.

### 4.4 Chọn metric theo câu hỏi

| Câu hỏi | Metric/cách xem phù hợp |
|---|---|
| Tổng chi phí ghi nhận theo cơ sở unblended tăng bao nhiêu? | UnblendedCost |
| Chi phí tháng đã tính phân bổ cam kết thay đổi thế nào? | AmortizedCost |
| Chi phí sau các khoản giảm giá đủ điều kiện là bao nhiêu? | NetUnblendedCost hoặc NetAmortizedCost, tùy mục tiêu |
| Khối lượng EC2 cùng loại tăng hay giảm? | UsageQuantity, lọc đúng Usage Type |
| Mức sử dụng instance quy đổi trong nhóm RI size-flexible thay đổi thế nào? | NormalizedUsageAmount |
| Cần đối chiếu với hóa đơn? | Chọn cơ sở metric và phạm vi phù hợp, sau đó đối chiếu Billing/invoice và CUR |

## 5. Dimension, filter và group by

Dimension là chiều dữ liệu để lọc hoặc nhóm chi phí. Một số chiều thường dùng:

| Dimension | Ý nghĩa | Câu hỏi ví dụ |
|---|---|---|
| SERVICE | Dịch vụ AWS | EC2, S3 hay RDS tạo ra mức tăng? |
| LINKED_ACCOUNT | Tài khoản thành viên | Tài khoản nào chịu phần tăng lớn nhất? |
| REGION | AWS Region | Chi phí ở ap-southeast-1 có tăng không? |
| AZ | Availability Zone | Có mức sử dụng tập trung ở một AZ không? |
| USAGE_TYPE | Loại usage cụ thể | Loại giờ instance, storage hoặc transfer nào tăng? |
| USAGE_TYPE_GROUP | Nhóm loại usage | Chi phí Compute, Data Transfer hoặc Storage thay đổi ra sao? |
| OPERATION | Thao tác/dạng vận hành | Kiểu hoạt động nào đang tạo chi phí? |
| INSTANCE_TYPE | Loại instance | m7i.large hay r7i.xlarge đang chiếm nhiều chi phí? |
| INSTANCE_TYPE_FAMILY | Họ instance | Chi phí theo họ compute thay đổi thế nào? |
| PURCHASE_TYPE | Loại hình mua | On-Demand, Reserved Instance hoặc Savings Plans ảnh hưởng ra sao? |
| RECORD_TYPE | Loại dòng chi phí | Usage, fee, credit, refund hoặc tax đóng góp thế nào? |
| PLATFORM / OPERATING_SYSTEM | Nền tảng hoặc hệ điều hành | License/platform có ảnh hưởng đến đơn giá không? |
| TENANCY | Mô hình tenancy | Dedicated hay shared tenancy có khác biệt không? |
| TAG | Cost allocation tag đã kích hoạt | Môi trường prod, team hoặc application nào chịu chi phí? |

Các dimension có thể xuất hiện tùy dịch vụ, loại dữ liệu và ngữ cảnh báo cáo. Không phải dimension nào cũng có giá trị cho mọi dòng chi phí.

### 5.1 Filter và group by khác nhau

Filter thu hẹp tập dữ liệu. Ví dụ, lọc Region = ap-southeast-1 để chỉ xem chi phí trong một Region.

Group by chia tập dữ liệu thành các nhóm. Ví dụ, sau khi lọc Region = ap-southeast-1, group by SERVICE để thấy EC2, S3, RDS và Data Transfer.

Một quy trình điều tra hữu ích:

1. Bắt đầu ở toàn tổ chức, group by SERVICE.
2. Chọn dịch vụ có biến động lớn.
3. Lọc dịch vụ đó và group by LINKED_ACCOUNT.
4. Chọn tài khoản có biến động lớn rồi group by REGION hoặc USAGE_TYPE.
5. Nếu đã kích hoạt cost allocation tags, group by Environment, Application hoặc Owner.
6. Đối chiếu nhóm usage tăng với thay đổi triển khai, lưu lượng hoặc cấu hình.

Không nên đưa quá nhiều chiều vào một biểu đồ ngay từ đầu. Hãy dùng một chiều để tìm vùng bất thường, sau đó đi sâu có chủ đích.

### 5.2 Cost allocation tags

Tag như Application, Environment, Owner, CostCenter hoặc Product giúp phân bổ chi phí theo ngữ cảnh nội bộ. Tag trên resource không tự động trở thành chiều phân tích chi phí ngay lập tức.

Để sử dụng tag trong Cost Explorer:

- Thống nhất key/value, chữ hoa/thường và quy tắc đặt tên.
- Gắn tag nhất quán vào các tài nguyên có thể gắn tag.
- Kích hoạt các cost allocation tags trong Billing and Cost Management.
- Chờ dữ liệu tag được xử lý và kiểm tra lại trong Cost Explorer.
- Xây quy trình phát hiện tài nguyên thiếu tag.
- Quy định người chịu trách nhiệm sửa tag và thời hạn xử lý.

Tag không thể phân bổ chính xác mọi khoản chi phí dùng chung. Ví dụ, NAT Gateway, shared load balancer, log archive hoặc data transfer có thể phục vụ nhiều ứng dụng. Tổ chức cần quy tắc phân bổ minh bạch như theo số request, GB truyền, tỷ lệ sử dụng, số tenant hoặc một tỷ lệ cố định đã được phê duyệt.

### 5.3 Cost Categories

Cost Categories cho phép nhóm chi phí theo quy tắc nghiệp vụ, ví dụ Production, Non-production, Shared Platform hoặc Business Unit. Quy tắc có thể dựa trên tài khoản, tag, dịch vụ hoặc các thuộc tính hỗ trợ.

Một thiết kế tốt cần:

- Có chủ sở hữu cho từng category và quy tắc.
- Xác định thứ tự và cách xử lý trường hợp một dòng khớp nhiều quy tắc.
- Có nhóm Unallocated/Unclassified để nhìn thấy chi phí chưa phân loại.
- Định kỳ rà soát tài khoản mới, tag mới và thay đổi tổ chức.
- Ghi nhận thay đổi quy tắc để giải thích vì sao số liệu phân bổ giữa các kỳ thay đổi.

Cost Category là lớp phân loại quản trị. Nó không thay đổi việc AWS đã ghi nhận mức sử dụng hoặc khoản phí nào.

## 6. Quy trình phân tích trên giao diện Cost Explorer

Có thể dùng quy trình sau cho một phiên phân tích hàng tháng.

### Bước 1: Mở Cost Explorer

Đăng nhập AWS Management Console bằng vai trò có quyền xem Billing and Cost Management. Mở Billing and Cost Management, chọn Cost Explorer và xác nhận phạm vi tài khoản đang được xem.

Nếu Cost Explorer chưa được bật hoặc dữ liệu chưa sẵn sàng, hãy làm theo hướng dẫn trong Billing console và chờ dữ liệu được khởi tạo. Việc bật công cụ hoặc thay đổi quyền xem dữ liệu cần tuân thủ quy trình quản trị tài khoản của tổ chức.

### Bước 2: Chọn khoảng thời gian

Chọn kỳ hiện tại, kỳ trước hoặc khoảng tùy chỉnh. Với phân tích tháng, nên so sánh các tháng đã hoàn tất. Nếu phân tích tháng đang chạy, dùng cùng số ngày hoặc cùng giai đoạn với tháng trước.

Ghi lại:
- Ngày bắt đầu và ngày kết thúc.
- Kỳ đã hoàn tất hay đang diễn ra.
- Thời điểm xuất báo cáo.
- Phạm vi tài khoản hoặc tổ chức.

### Bước 3: Chọn granularity

- Monthly: phù hợp với báo cáo tài chính, xu hướng và review tháng.
- Daily: phù hợp để tìm ngày phát sinh đột biến, ngày deploy hoặc chiến dịch tăng tải.

Granularity càng chi tiết thì số điểm dữ liệu càng nhiều. Hãy bắt đầu ở Monthly để thấy bức tranh tổng thể, sau đó chuyển Daily khi cần xác định thời điểm.

### Bước 4: Chọn metric

Chọn UnblendedCost, AmortizedCost hoặc metric phù hợp với câu hỏi. Ghi rõ metric trên ảnh chụp hoặc báo cáo. Không so sánh hai biểu đồ nếu metric khác nhau.

### Bước 5: Áp dụng filter

Bắt đầu với các filter có tác dụng thu hẹp phạm vi:

- LINKED_ACCOUNT để chọn ứng dụng hoặc môi trường.
- SERVICE để tập trung vào dịch vụ đang tăng.
- REGION để so sánh nơi triển khai.
- TAG hoặc Cost Category để xem chi phí theo trách nhiệm.
- RECORD_TYPE để tách usage khỏi credits, refunds, tax hoặc fee khi cần.

### Bước 6: Group by

Group by SERVICE để tìm nhóm lớn. Tiếp tục bằng LINKED_ACCOUNT, REGION, USAGE_TYPE hoặc tag để phân rã phần chênh lệch.

### Bước 7: Đọc biểu đồ và bảng

Biểu đồ cho biết xu hướng; bảng cho biết giá trị từng nhóm. Quan sát cả hai:

- Tổng chi phí thay đổi bao nhiêu?
- Nhóm nào đóng góp nhiều nhất vào thay đổi?
- Nhóm nào có phần trăm tăng cao nhưng số tiền tuyệt đối nhỏ?
- Có khoản phí một lần hoặc credit/refund làm lệch biểu đồ không?
- Có ngày tăng đột biến trùng với deploy, batch job hoặc sự kiện kinh doanh không?

### Bước 8: Lưu báo cáo và ghi kết luận

Lưu các cấu hình thường dùng thành báo cáo Cost Explorer để nhóm có thể mở lại. Trong kết luận, ghi metric, kỳ, phạm vi, bộ lọc, nhóm dữ liệu và giả thuyết nguyên nhân. Một ảnh chụp không có cấu hình truy vấn đi kèm thường không đủ để tái lập kết quả.

## 7. Tính biến động chi phí

Phân tích biến động bắt đầu bằng phép so sánh hai kỳ có cùng cơ sở.

Gọi:

- C0 là chi phí kỳ gốc.
- C1 là chi phí kỳ hiện tại.
- ΔC là mức thay đổi tuyệt đối.
- Δ% là tỷ lệ thay đổi so với kỳ gốc.

Công thức:

~~~text
ΔC = C1 - C0

Δ% = (C1 - C0) / C0 × 100%
~~~

Ví dụ: tháng 9 chi phí là 12.000 USD, tháng 10 là 15.000 USD.

~~~text
ΔC = 15.000 - 12.000 = 3.000 USD

Δ% = 3.000 / 12.000 × 100% = 25%
~~~

Chi phí tăng 3.000 USD, tương đương 25% so với tháng gốc.

Nếu C0 = 0, không thể tính phần trăm tăng theo công thức trên. Hãy ghi nhận đây là chi phí mới hoặc nhóm mới xuất hiện, rồi báo cáo số tiền tuyệt đối. Không thay mẫu số bằng một số tùy ý để tạo ra tỷ lệ phần trăm.

Khi chi phí giảm, ΔC và Δ% sẽ âm. Nên giữ dấu âm trong dữ liệu tính toán, sau đó diễn giải bằng từ “giảm” để tránh nhầm lẫn.

### 7.1 So sánh công bằng

Một phép so sánh đáng tin cậy cần bảo đảm:

- Cùng metric.
- Cùng phạm vi tài khoản và tổ chức.
- Cùng đơn vị tiền tệ.
- Cùng cách phân bổ cam kết.
- Cùng trạng thái kỳ (đã hoàn tất hoặc cùng số ngày đã trôi qua).
- Cùng cách xử lý credits, refunds, tax và các khoản điều chỉnh.
- Cùng chính sách phân bổ shared cost.

Nếu một kỳ có thêm tài khoản mới hoặc một tag được kích hoạt giữa kỳ, hãy ghi nhận thay đổi phân loại. Số liệu lịch sử có thể không được phân bổ ngược theo cách mà báo cáo hiện tại đang mong đợi.

### 7.2 Phân biệt số tiền tuyệt đối và phần trăm

Giả sử:

| Dịch vụ | Kỳ gốc | Kỳ hiện tại | Thay đổi | Thay đổi % |
|---|---:|---:|---:|---:|
| EC2 | 6.000 | 8.100 | +2.100 | +35,0% |
| S3 | 2.400 | 2.700 | +300 | +12,5% |
| RDS | 1.800 | 1.900 | +100 | +5,6% |
| Data Transfer | 1.200 | 1.500 | +300 | +25,0% |
| Khác | 600 | 800 | +200 | +33,3% |
| **Tổng** | **12.000** | **15.000** | **+3.000** | **+25,0%** |

EC2 đóng góp 2.100 USD trong tổng mức tăng 3.000 USD. Đây là ưu tiên điều tra đầu tiên vì tác động tuyệt đối lớn nhất.

Nhóm “Khác” tăng 33,3%, cao hơn EC2 về tỷ lệ, nhưng chỉ tăng 200 USD. Tỷ lệ cao không đồng nghĩa tác động tài chính lớn. Khi xếp thứ tự điều tra, hãy xem cả ΔC và Δ%.

## 8. Tìm nguyên nhân: volume, rate và mix

Tổng chi phí thường thay đổi vì một hoặc nhiều yếu tố:

- Volume: số giờ chạy, GB lưu trữ, request, số bản sao, dung lượng truyền hoặc số tài nguyên tăng/giảm.
- Rate: đơn giá thay đổi do Region, loại instance, tier, mô hình mua, discount hoặc hợp đồng.
- Mix: tỷ trọng giữa các loại tài nguyên thay đổi, ví dụ chuyển từ instance nhỏ sang instance lớn hoặc từ một Region sang Region khác.
- One-time items: khoản trả trước, phí một lần, credits, refunds, tax hoặc điều chỉnh.
- Allocation: thay đổi tag, Cost Category hoặc quy tắc phân bổ làm chi phí được gán sang nhóm khác.

Một phép phân rã đơn giản cho cùng một loại usage:

~~~text
Cost = Quantity × Unit Rate

Volume Effect = (Q1 - Q0) × P0

Rate Effect = Q1 × (P1 - P0)

Total Change = Volume Effect + Rate Effect
~~~

Trong đó Q0/P0 là quantity và unit rate kỳ gốc; Q1/P1 là quantity và unit rate kỳ hiện tại. Cách phân rã này tính tác động volume theo đơn giá gốc và tác động rate theo volume hiện tại. Tổ chức có thể chọn quy ước khác, nhưng cần ghi rõ để các báo cáo không cộng trùng.

Ví dụ, một nhóm EC2 có 1.000 instance-hours ở kỳ gốc với đơn giá phân tích 6 USD/giờ quy đổi theo ví dụ. Kỳ hiện tại có 1.350 instance-hours và đơn giá không đổi.

~~~text
Kỳ gốc = 1.000 × 6 = 6.000 USD
Kỳ hiện tại = 1.350 × 6 = 8.100 USD
Volume Effect = (1.350 - 1.000) × 6 = 2.100 USD
Rate Effect = 1.350 × (6 - 6) = 0 USD
~~~

Trong ví dụ, toàn bộ mức tăng đến từ volume. Trong hệ thống thực tế, đơn giá hiệu dụng có thể chịu ảnh hưởng của discount, RI, Savings Plans, free tier, credits, loại operating system, tenancy và Region. Không nên suy ra P chỉ bằng cách lấy tổng chi phí chia tổng usage nếu các dòng usage có đơn vị hoặc mức giá khác nhau.

### 8.1 Phân tích mix

Giả sử trước đây ứng dụng chạy chủ yếu trên instance compute-optimized, sau một lần thay đổi cấu hình chuyển một phần sang memory-optimized. Tổng số instance-hours có thể không đổi, nhưng tổng chi phí vẫn tăng vì cơ cấu và đơn giá thay đổi.

Để phân tích mix:

1. Group by INSTANCE_TYPE hoặc INSTANCE_TYPE_FAMILY.
2. So sánh quantity và cost theo từng nhóm.
3. Kiểm tra Region, platform, tenancy và purchase option.
4. Đối chiếu thời điểm thay đổi cấu hình.
5. Xác định việc thay đổi loại tài nguyên có cải thiện hiệu năng hoặc SLA tương ứng không.

### 8.2 Tách chi phí định kỳ và một lần

Một khoản tăng có thể không phản ánh run-rate mới. Hãy kiểm tra RECORD_TYPE và các dòng liên quan đến fee, upfront, credit, refund hoặc tax.

Ví dụ:
- Mua cam kết trả trước có thể tạo khoản chi phí lớn ở kỳ phát sinh.
- Refund có thể khiến kỳ hiện tại giảm nhưng không có nghĩa workload đã tối ưu.
- Credit có thể che khuất mức tăng của usage.
- Tax hoặc điều chỉnh hóa đơn có thể không liên quan đến thay đổi kiến trúc.

Báo cáo quản trị nên thể hiện cả chi phí gộp theo cơ sở đã chọn và các khoản điều chỉnh liên quan, theo chính sách tài chính của tổ chức.

## 9. Chuẩn hóa chi phí theo hoạt động nghiệp vụ

Tổng chi phí không đủ để đánh giá hiệu quả. Nếu số đơn hàng tăng gấp đôi và chi phí tăng 30%, hiệu quả đơn vị có thể đã cải thiện.

Một số đơn vị chuẩn hóa:

| Đơn vị | Công thức | Phù hợp với |
|---|---|---|
| Cost per request | Tổng chi phí liên quan / số request | API, backend service |
| Cost per order | Chi phí nền tảng / số đơn hàng | Thương mại điện tử |
| Cost per active user | Chi phí / số người dùng hoạt động | SaaS, ứng dụng người dùng |
| Cost per tenant | Chi phí / số tenant | Nền tảng multi-tenant |
| Cost per GB processed | Chi phí xử lý / GB dữ liệu | Data platform, ETL |
| Cost per build | Chi phí CI/CD / số lần build | Pipeline phát triển |

Ví dụ:

~~~text
Tháng A:
Cloud cost = 10.000 USD
Orders = 100.000
Cost per order = 0,10 USD

Tháng B:
Cloud cost = 12.000 USD
Orders = 150.000
Cost per order = 0,08 USD
~~~

Tổng chi phí tăng 20%, nhưng chi phí trên mỗi đơn giảm 20%. Đây có thể là cải thiện hiệu quả. Tuy nhiên, cần kiểm tra chất lượng dịch vụ, độ trễ, tỷ lệ lỗi và mức độ sử dụng để bảo đảm chi phí thấp hơn không đến từ việc giảm chất lượng.

Nguồn dữ liệu nghiệp vụ thường nằm ngoài Cost Explorer. Hãy kết hợp Cost Explorer với CloudWatch, hệ thống analytics, số đơn hàng hoặc dữ liệu sản phẩm. Chọn cùng cửa sổ thời gian và quy tắc loại bỏ dữ liệu thử nghiệm để mẫu số nhất quán.

## 10. Phân tích Reserved Instances và Savings Plans

Reserved Instances (RI) và Savings Plans là cam kết tài chính giúp giảm chi phí khi workload có mức sử dụng ổn định. Chúng cũng làm thay đổi cách đọc báo cáo.

Các câu hỏi cần trả lời:

- Cam kết đã mua có được workload sử dụng đủ không?
- Tỷ lệ utilization có phù hợp với kế hoạch không?
- Coverage của workload có đang tăng hay giảm?
- Cam kết có khớp Region, instance family, operating system và phạm vi áp dụng không?
- Có phần trả trước hoặc phí định kỳ nào làm biến động kỳ?
- Có workload mới đang chạy On-Demand trong khi cam kết còn dư ở phạm vi tương thích không?

Cost Explorer có các báo cáo liên quan đến RI và Savings Plans, bao gồm utilization và coverage. Hãy phân biệt:

- Utilization: mức độ sử dụng cam kết đã mua.
- Coverage: tỷ lệ workload đủ điều kiện đang được cam kết bao phủ.
- Amortized cost: chi phí cam kết được phân bổ theo thời gian.
- On-Demand equivalent: chi phí tham chiếu nếu mức sử dụng đủ điều kiện được tính theo On-Demand; đây là cơ sở so sánh, không phải hóa đơn thực tế.

Ví dụ, một đội có RI utilization thấp nhưng coverage của workload lại thấp. Điều đó có thể cho thấy đội đã mua cam kết sai phạm vi hoặc sai quy mô. Ngược lại, utilization cao nhưng coverage thấp có thể cho thấy workload còn nhiều On-Demand và tổ chức có thể cần đánh giá thêm cam kết.

Không mua thêm RI hoặc Savings Plans chỉ vì biểu đồ cho thấy On-Demand cao trong một tuần. Trước khi cam kết, cần:
1. Xác nhận workload có ổn định trong thời hạn dự kiến.
2. Kiểm tra Region, family, platform và phạm vi áp dụng.
3. Xem lịch sử usage và kế hoạch tăng/giảm tải.
4. So sánh mức tiết kiệm với rủi ro cam kết dư.
5. Kiểm tra tác động đến kiến trúc và khả năng di chuyển workload.
6. Được chủ sở hữu ngân sách phê duyệt.

## 11. Đọc dự báo chi phí

Cost Explorer có thể tạo dự báo dựa trên dữ liệu lịch sử và mô hình của AWS. Dự báo hữu ích để nhận biết xu hướng, nhưng không phải cam kết về hóa đơn cuối cùng.

Khi sử dụng forecast:

- Chọn metric phù hợp với mục tiêu quản trị.
- Xem khoảng thời gian dự báo và phạm vi tài khoản.
- Đọc khoảng dự báo nếu giao diện cung cấp dải ước lượng.
- Kiểm tra mùa vụ, ngày lễ, chiến dịch kinh doanh và lịch batch.
- Ghi nhận các thay đổi đã biết như mở Region mới, tăng số tenant hoặc migration.
- Cập nhật dự báo khi có thông tin vận hành mới.

Dự báo dựa trên lịch sử có thể không biết về một lần triển khai sắp tới, sự kiện marketing, thay đổi giá, mua cam kết, hoặc workload mới. Nếu một ứng dụng chuẩn bị tăng gấp ba lưu lượng, forecast lịch sử có thể đánh giá thấp nhu cầu.

### 11.1 Kết hợp forecast và ngân sách

Một quy trình quản trị có thể dùng:

1. Forecast của Cost Explorer để ước lượng xu hướng.
2. AWS Budgets để đặt ngưỡng chi phí hoặc mức sử dụng.
3. SNS hoặc kênh thông báo đã được phê duyệt để gửi cảnh báo.
4. Runbook để xác minh nguyên nhân trước khi hành động.
5. Báo cáo variance hàng tuần để so sánh forecast với actual.

Cảnh báo vượt ngưỡng không tự chứng minh có lãng phí. Nó là tín hiệu yêu cầu kiểm tra. Tương tự, forecast dưới ngân sách không có nghĩa kiến trúc đã tối ưu.

## 12. Kết hợp Cost Explorer với AWS Organizations và quản trị FinOps

Trong môi trường nhiều tài khoản, cấu trúc tài khoản nên phản ánh ranh giới quản trị hợp lý: workload production, non-production, shared services, security, log archive hoặc từng sản phẩm.

Một quy trình FinOps có thể phân chia trách nhiệm:

| Vai trò | Trách nhiệm |
|---|---|
| Platform/Cloud team | Thiết kế cấu trúc tài khoản, tag, network và công cụ quan sát |
| Application owner | Giải thích workload, lưu lượng, cấu hình và thay đổi triển khai |
| Finance/FinOps | Chuẩn hóa metric, ngân sách, phân bổ và báo cáo |
| Security | Bảo đảm quyền truy cập dữ liệu Billing và kiểm soát thay đổi |
| Engineering manager | Ưu tiên hành động tối ưu và chấp nhận trade-off chi phí/hiệu năng |

Nên có nhịp vận hành rõ ràng:

- Hằng ngày: xem cảnh báo bất thường và kiểm tra đột biến nghiêm trọng.
- Hằng tuần: xem top service/account variance và tiến độ hành động.
- Hằng tháng: đối soát kỳ, review budget/forecast, phân bổ shared cost và cập nhật cam kết.
- Hằng quý: xem lại cấu trúc tài khoản, taxonomy tag, Cost Categories và hiệu quả tối ưu.

Nhịp này là gợi ý vận hành; tần suất thực tế cần phù hợp với tốc độ thay đổi và mức rủi ro của workload.

## 13. Truy vấn Cost Explorer bằng AWS CLI

Cost Explorer API cho phép tự động hóa truy vấn tổng hợp và đưa dữ liệu vào quy trình báo cáo. Ví dụ dưới đây truy vấn chi phí theo dịch vụ và linked account trong hai tháng hoàn tất.

~~~bash
aws ce get-cost-and-usage \
  --region us-east-1 \
  --time-period Start=2026-09-01,End=2026-11-01 \
  --granularity MONTHLY \
  --metrics UnblendedCost AmortizedCost \
  --group-by Type=DIMENSION,Key=SERVICE Type=DIMENSION,Key=LINKED_ACCOUNT
~~~

Giải thích:

- Start là ngày bắt đầu được tính.
- End là ngày kết thúc không bao gồm trong khoảng truy vấn. Với ví dụ trên, dữ liệu bao phủ tháng 9 và tháng 10.
- MONTHLY tạo một nhóm kết quả cho mỗi tháng.
- UnblendedCost và AmortizedCost được trả về riêng.
- Group by SERVICE và LINKED_ACCOUNT giúp xác định dịch vụ theo tài khoản.

Một filter tag có thể được truyền bằng tệp JSON để dễ kiểm soát phiên bản.

Tệp filter.json:

~~~json
{
  "Tags": {
    "Key": "Environment",
    "Values": ["prod"]
  }
}
~~~

Truy vấn chỉ cho môi trường production:

~~~bash
aws ce get-cost-and-usage \
  --region us-east-1 \
  --time-period Start=2026-10-01,End=2026-11-01 \
  --granularity DAILY \
  --metrics UnblendedCost \
  --filter file://filter.json \
  --group-by Type=DIMENSION,Key=SERVICE
~~~

Kết quả API thường có cấu trúc:
- ResultsByTime: các khoảng thời gian được truy vấn.
- Groups: các nhóm theo dimension đã chọn.
- Keys: giá trị của các dimension trong nhóm.
- Metrics: Amount và Unit của metric.

Khi xử lý kết quả, hãy đọc Amount như giá trị số dạng chuỗi và giữ Unit. Không cộng các metric hoặc đơn vị khác nhau. Với dữ liệu nhiều nhóm, hãy lưu raw response cùng tham số truy vấn để có thể tái lập.

### 13.1 Dự báo qua CLI

Ví dụ truy vấn dự báo chi phí unblended cho tháng 12:

~~~bash
aws ce get-cost-forecast \
  --region us-east-1 \
  --time-period Start=2026-12-01,End=2027-01-01 \
  --metric UNBLENDED_COST \
  --granularity MONTHLY
~~~

Dự báo phụ thuộc dữ liệu lịch sử và khả năng hỗ trợ của metric/khoảng thời gian. Hãy kiểm tra response, khoảng ước lượng và lỗi do quyền hoặc khoảng thời gian không hợp lệ trước khi đưa vào báo cáo.

### 13.2 Quyền IAM

Role chạy truy vấn cần các quyền Cost Explorer API tương ứng, ví dụ:

- ce:GetCostAndUsage
- ce:GetCostForecast
- ce:GetDimensionValues
- ce:GetTags
- ce:GetCostCategories

Tên quyền cụ thể cần khớp với API mà ứng dụng gọi. Dùng IAM policy theo nguyên tắc least privilege, gắn role vào workload hoặc người vận hành phù hợp và ghi log truy cập theo chính sách tổ chức. Quyền đọc Billing có thể cần cấu hình bổ sung trong tài khoản; quyền IAM đơn lẻ không đảm bảo người dùng đã được bật quyền xem Billing console.

Không đưa access key dài hạn vào script, notebook hoặc repository. Ưu tiên IAM role và thông tin xác thực tạm thời.

## 14. Khi nào cần Cost and Usage Data Exports hoặc CUR

Cost Explorer phù hợp với phân tích tổng hợp và truy vấn tương tác. Nếu cần chi tiết hơn, hãy cân nhắc AWS Data Exports với Cost and Usage Report (CUR), bao gồm định dạng CUR 2.0 khi phù hợp.

Các tình huống nên chuyển sang dữ liệu xuất chi tiết:

- Cần truy vấn nhiều trường line item.
- Cần phân tích resource ID khi trường đó được hỗ trợ và có trong export.
- Cần kết hợp chi phí với inventory, owner hoặc dữ liệu nội bộ.
- Cần lưu lịch sử dài hạn theo mô hình dữ liệu riêng.
- Cần xử lý hàng triệu dòng bằng Athena, Glue hoặc công cụ BI.
- Cần đối chiếu các khoản RI/Savings Plans hoặc usage cụ thể.

Một pipeline thường có dạng:

~~~text
AWS billing data
       |
       v
Data Exports / CUR
       |
       v
Amazon S3
       |
       +----> AWS Glue Data Catalog
       |
       v
Amazon Athena
       |
       +----> BI dashboard
       |
       +----> FinOps reports
       |
       +----> Cost allocation / unit economics
~~~

Pipeline cần được thiết kế với quyền truy cập S3, mã hóa, retention, phân quyền Athena và kiểm soát dữ liệu nhạy cảm. Báo cáo chi phí có thể tiết lộ cấu trúc tài khoản, tên workload, quy mô kinh doanh và mức độ sử dụng dịch vụ; hãy giới hạn người xem theo vai trò.

Cost Explorer và CUR có thể khác nhau nếu phạm vi, thời điểm cập nhật, metric hoặc cách xử lý dòng dữ liệu khác nhau. Khi đối chiếu, ghi rõ cấu hình của cả hai phía.

## 15. Tình huống thực tế: chi phí tăng 25% trong tháng

Một nền tảng thương mại điện tử chạy trên nhiều AWS account nhận thấy chi phí tháng 10 cao hơn tháng 9. Finance yêu cầu đội kỹ thuật giải thích và đề xuất hành động.

### 15.1 Bước 1: xác nhận số liệu

Đội FinOps mở Cost Explorer và chọn:
- Kỳ gốc: 01/09 đến 01/10.
- Kỳ hiện tại: 01/10 đến 01/11.
- Granularity: Monthly.
- Metric: AmortizedCost để xem xu hướng kinh tế đã phân bổ cam kết.
- Scope: toàn bộ payer account.
- Group by: SERVICE.

Kết quả giả định cho thấy tổng chi phí tăng từ 12.000 lên 15.000 USD, tương đương 25%.

### 15.2 Bước 2: xác định nơi đóng góp

Bảng theo dịch vụ:

| Dịch vụ | Tháng 9 | Tháng 10 | Chênh lệch |
|---|---:|---:|---:|
| EC2 | 6.000 USD | 8.100 USD | +2.100 USD |
| S3 | 2.400 USD | 2.700 USD | +300 USD |
| RDS | 1.800 USD | 1.900 USD | +100 USD |
| Data Transfer | 1.200 USD | 1.500 USD | +300 USD |
| Khác | 600 USD | 800 USD | +200 USD |
| **Tổng** | **12.000 USD** | **15.000 USD** | **+3.000 USD** |

EC2 chiếm 70% tổng phần tăng. Đội quyết định điều tra EC2 trước.

### 15.3 Bước 3: phân rã EC2

Lọc SERVICE = EC2, group by LINKED_ACCOUNT. Một tài khoản production chiếm phần lớn mức tăng. Tiếp tục group by REGION, INSTANCE_TYPE và USAGE_TYPE.

Giả thuyết ban đầu:
- Một đợt phát hành mở rộng số task/instance.
- Autoscaling tăng capacity để đáp ứng lưu lượng.
- Một batch job chạy lâu hơn.
- Instance type hoặc purchase option đã thay đổi.

Đội đối chiếu với lịch deploy, metric CPU/memory, request count và lịch batch. Dữ liệu cho thấy instance-hours tăng 35%, trong khi đơn giá hiệu dụng gần như không đổi. Mức tăng chủ yếu đến từ volume.

### 15.4 Bước 4: kiểm tra hiệu quả nghiệp vụ

Trong cùng kỳ, số đơn hàng tăng 50%. Chi phí EC2 tăng 35%, thấp hơn tốc độ tăng đơn hàng. Cost per order của phần compute đã giảm.

Đội vẫn kiểm tra:
- CPU utilization và memory utilization.
- Số instance nhàn rỗi trong giờ thấp điểm.
- Thời gian scale-in.
- Error rate và latency.
- Batch job có thể chuyển sang lịch chạy phù hợp hơn không.

Kết luận không phải “chi phí tăng là xấu”. Kết luận là “compute tăng do volume phục vụ tăng trưởng; cost per order giảm, nhưng còn một số cửa sổ nhàn rỗi cần tối ưu”.

### 15.5 Bước 5: kiểm tra các nhóm còn lại

- S3 tăng 300 USD: kiểm tra storage class, số version, lifecycle và data retrieval.
- Data Transfer tăng 300 USD: kiểm tra inter-AZ, inter-Region, internet egress và cache hit ratio.
- RDS tăng 100 USD: kiểm tra instance-hours, storage, backup và read replica.
- Khác tăng 200 USD: group by SERVICE và RECORD_TYPE để tìm khoản mới.

Mỗi phát hiện cần một chủ sở hữu và một hành động đo được. Ví dụ: “giảm idle EC2 hours 10% trong môi trường non-production” tốt hơn “tối ưu EC2”.

## 16. Runbook điều tra biến động

Dùng runbook sau khi tổng chi phí vượt ngưỡng hoặc một nhóm có variance bất thường.

### 16.1 Xác nhận

1. Kiểm tra tài khoản và phạm vi organization.
2. Kiểm tra kỳ, metric, granularity và đơn vị tiền.
3. Xác nhận kỳ so sánh có độ dài tương đương.
4. Ghi lại thời điểm dữ liệu được trích xuất.
5. Xác định khoản tăng là usage, fee, credit, refund, tax hay adjustment.

### 16.2 Khoanh vùng

1. Group by SERVICE.
2. Sắp xếp theo chênh lệch tuyệt đối.
3. Chọn top contributor.
4. Group by LINKED_ACCOUNT.
5. Tiếp tục theo REGION, USAGE_TYPE, OPERATION hoặc tag.
6. Kiểm tra resource-level export nếu Cost Explorer chưa đủ chi tiết.

### 16.3 Tìm nguyên nhân

Đối chiếu với:
- Release/deployment timeline.
- Autoscaling events và lịch batch.
- Lưu lượng, request count và số người dùng.
- Thay đổi instance/storage/database/network.
- Thay đổi Region, AZ, replication hoặc backup.
- Mua mới hoặc hết hạn RI/Savings Plans.
- Thay đổi discount, credit hoặc hợp đồng.
- Thay đổi tag, account structure hoặc Cost Categories.

### 16.4 Quyết định hành động

Mỗi hành động cần có:
- Mô tả nguyên nhân đã xác minh.
- Owner chịu trách nhiệm.
- Mức tiết kiệm kỳ vọng và cách tính.
- Tác động đến hiệu năng, độ sẵn sàng, bảo mật và khả năng phục hồi.
- Thời hạn triển khai.
- Chỉ số trước/sau.
- Cách rollback nếu chất lượng dịch vụ giảm.

Không giảm replica, backup, logging, mã hóa hoặc mức sẵn sàng chỉ để đạt mục tiêu chi phí nếu chưa đánh giá rủi ro. Tối ưu chi phí phải giữ các yêu cầu vận hành và bảo mật đã được phê duyệt.

## 17. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| So sánh UnblendedCost với AmortizedCost | Kết luận sai về mức tăng/giảm | Dùng cùng metric và ghi rõ cơ sở |
| So sánh tháng chưa hoàn tất với tháng hoàn tất | Tạo variance giả | So cùng số ngày hoặc dùng kỳ đã đóng |
| Cộng UsageQuantity của nhiều đơn vị | Tổng usage vô nghĩa | Nhóm theo usage type/unit |
| Chỉ nhìn phần trăm tăng | Bỏ qua tác động tiền tuyệt đối | Xem cả ΔC và Δ% |
| Xem forecast như hóa đơn cuối cùng | Lập ngân sách sai | Dùng forecast như ước lượng có điều kiện |
| Cho rằng mọi tag đều có sẵn trong Cost Explorer | Thiếu nhóm hoặc chi phí không phân bổ | Kích hoạt cost allocation tags và kiểm tra dữ liệu |
| Cho rằng tag tự chia shared cost | Phân bổ thiếu hoặc sai | Định nghĩa driver phân bổ có thể kiểm chứng |
| Mua cam kết theo một tuần usage | Rủi ro cam kết dư | Xem xu hướng dài hạn và kế hoạch workload |
| Xem chi phí tăng luôn là lãng phí | Cắt giảm sai chỗ | Chuẩn hóa theo hoạt động nghiệp vụ |
| Dùng Cost Explorer thay CUR cho mọi truy vấn | Thiếu trường line-item | Chuyển sang Data Exports/CUR khi cần chi tiết |
| Bỏ qua credits/refunds/tax | Giải thích sai biến động | Kiểm tra RECORD_TYPE và đối chiếu Billing |
| Không ghi tham số báo cáo | Không thể tái lập | Lưu kỳ, metric, filter, group by và thời điểm trích xuất |

## 18. Kiểm soát truy cập và bảo vệ dữ liệu chi phí

Thông tin chi phí có thể tiết lộ quy mô sản phẩm, tài khoản, Region, hệ thống đang chạy và tốc độ tăng trưởng. Hãy xem dữ liệu Billing là dữ liệu nội bộ cần kiểm soát.

Các nguyên tắc:

- Dùng IAM role và quyền đọc Cost Explorer tối thiểu cho người hoặc workload cần phân tích.
- Quản lý quyền xem Billing theo account governance của tổ chức.
- Tách người có quyền xem chi phí khỏi người có quyền thay đổi billing/payment settings khi cần.
- Không nhúng access key vào dashboard, script hoặc file báo cáo.
- Với CUR/Data Exports, bảo vệ S3 bucket bằng block public access, policy giới hạn principal, mã hóa và logging.
- Chỉ chia sẻ dashboard cho nhóm có nhu cầu công việc.
- Rà soát quyền truy cập khi nhân sự đổi vai trò hoặc rời tổ chức.

Cost Explorer chủ yếu phục vụ đọc và phân tích. Những hành động thay đổi tài nguyên để giảm chi phí vẫn phải đi qua quy trình change management, review bảo mật và kiểm tra ảnh hưởng đến dịch vụ.

## 19. Checklist cho báo cáo variance hàng tháng

Trước khi phát hành báo cáo, xác nhận:

- [ ] Phạm vi account/organization được ghi rõ.
- [ ] Kỳ gốc và kỳ hiện tại có độ dài so sánh hợp lý.
- [ ] Metric và granularity giống nhau.
- [ ] Đã tính ΔC và Δ% đúng công thức.
- [ ] Top contributor được xếp theo tác động tuyệt đối.
- [ ] Có giải thích các nhóm tăng mạnh theo phần trăm.
- [ ] Đã kiểm tra RECORD_TYPE, credit, refund, tax và fee.
- [ ] Đã phân biệt volume, rate, mix và khoản một lần.
- [ ] Đã xem xét ảnh hưởng RI/Savings Plans.
- [ ] Có unit economics khi workload gắn với chỉ số nghiệp vụ.
- [ ] Giả thuyết nguyên nhân đã được đối chiếu với dữ liệu vận hành.
- [ ] Mỗi hành động có owner, deadline và cách đo.
- [ ] Tác động đến hiệu năng, bảo mật, độ sẵn sàng và phục hồi đã được đánh giá.
- [ ] Cấu hình truy vấn và thời điểm trích xuất được lưu để tái lập.

## 20. Bài tập thực hành

### Bài 1: Tính variance

Một workload có AmortizedCost tháng 8 là 8.000 USD và tháng 9 là 9.600 USD.

Yêu cầu:
1. Tính chênh lệch tuyệt đối.
2. Tính phần trăm thay đổi.
3. Viết một câu kết luận có nêu rõ metric và kỳ.

Đáp án:
- ΔC = 9.600 - 8.000 = 1.600 USD.
- Δ% = 1.600 / 8.000 × 100% = 20%.
- Chi phí amortized tháng 9 tăng 1.600 USD, tương đương 20% so với tháng 8.

### Bài 2: Tìm ưu tiên điều tra

Ba dịch vụ thay đổi như sau:

| Dịch vụ | Kỳ gốc | Kỳ hiện tại |
|---|---:|---:|
| Compute | 20.000 USD | 22.000 USD |
| Storage | 1.000 USD | 1.500 USD |
| Network | 500 USD | 700 USD |

Yêu cầu: chọn dịch vụ cần điều tra trước nếu mục tiêu là giải thích phần tăng tổng chi phí.

Đáp án: Compute tăng 2.000 USD, là đóng góp tuyệt đối lớn nhất. Storage tăng 50%, Network tăng 40%; hai tỷ lệ này cao hơn nhưng mức tăng tiền lần lượt là 500 và 200 USD. Nên bắt đầu với Compute, sau đó kiểm tra Storage và Network theo mức độ rủi ro hoặc mục tiêu tối ưu.

### Bài 3: UsageQuantity

Một báo cáo có 500 instance-hours, 800 GB-month và 2 triệu requests.

Yêu cầu: có thể cộng ba lượng này thành một tổng usage không?

Đáp án: Không. Chúng có đơn vị khác nhau. Cần phân tích riêng hoặc quy đổi theo một chỉ số nghiệp vụ có định nghĩa rõ ràng.

### Bài 4: Volume hay rate?

Chi phí compute tăng từ 4.000 lên 5.000 USD. Usage tăng từ 800 lên 1.000 đơn vị cùng loại. Đơn giá hiệu dụng không đổi.

Đáp án: chi phí tăng do volume. Với đơn giá 5 USD/đơn vị, volume effect là (1.000 - 800) × 5 = 1.000 USD; rate effect bằng 0.

### Bài 5: Chọn metric

Tổ chức vừa mua một RI trả trước và muốn đánh giá chi phí kinh tế bình quân theo tháng.

Đáp án: xem AmortizedCost hoặc NetAmortizedCost nếu phù hợp với chính sách net cost. Đồng thời xem UnblendedCost để hiểu khoản ghi nhận theo cơ sở unblended trong kỳ mua. Không so sánh hai metric như thể chúng có cùng ý nghĩa.

### Bài 6: Điều tra Data Transfer

Chi phí Data Transfer tăng 40%. Nêu ba chiều hoặc nguồn dữ liệu cần kiểm tra.

Đáp án gợi ý:
- Group by REGION và AZ để kiểm tra luồng liên Region/liên AZ.
- Group by USAGE_TYPE và OPERATION để xác định loại transfer.
- Đối chiếu network architecture, NAT Gateway, load balancer, cache hit ratio và lưu lượng thực tế.

### Bài 7: Đánh giá cost per order

Chi phí cloud tăng 10%, số đơn hàng tăng 25%.

Đáp án: nếu phạm vi chi phí và số đơn hàng tương thích, cost per order giảm. Chỉ số tương đối mới bằng 1,10 / 1,25 = 0,88, tức giảm khoảng 12%. Cần kiểm tra chất lượng dịch vụ và chi phí của các thành phần khác trước khi kết luận hiệu quả tổng thể đã cải thiện.

### Bài 8: Phân tích forecast

Forecast cuối tháng cao hơn budget 15%, nhưng một chiến dịch marketing lớn sẽ kết thúc sau ba ngày.

Đáp án: kiểm tra lịch chiến dịch và mức tiêu thụ thực tế, xây kịch bản sau chiến dịch, cập nhật dự báo và theo dõi actual. Không bỏ qua cảnh báo chỉ vì kỳ vọng chiến dịch kết thúc; cần xác minh workload có scale-in và chi phí có giảm sau sự kiện hay không.

## 21. Câu hỏi tự kiểm tra

1. Cost Explorer được dùng chủ yếu để làm gì?
2. Vì sao Cost Explorer không phải công cụ telemetry thời gian thực?
3. UnblendedCost và AmortizedCost khác nhau ở điểm nào?
4. Khi nào nên dùng NetAmortizedCost?
5. Vì sao không nên cộng UsageQuantity của nhiều Usage Type?
6. Dimension SERVICE trả lời câu hỏi gì?
7. Filter khác group by như thế nào?
8. Tại sao cost allocation tag cần được kích hoạt trong Billing?
9. Cost Categories giúp ích gì cho FinOps?
10. Công thức tính variance tuyệt đối và phần trăm là gì?
11. Cần làm gì khi chi phí kỳ gốc bằng 0?
12. Vì sao phải xem cả ΔC và Δ%?
13. Volume, rate và mix khác nhau như thế nào?
14. Cost per order có thể giúp giải thích điều gì khi tổng cloud cost tăng?
15. RI utilization và coverage phản ánh hai góc nhìn nào?
16. Vì sao forecast không phải hóa đơn cuối cùng?
17. Khi nào nên dùng Data Exports/CUR thay vì chỉ dùng Cost Explorer?
18. Những thông tin nào cần lưu để tái lập một báo cáo?
19. Vì sao cần kiểm tra RECORD_TYPE khi chi phí biến động?
20. Một hành động tối ưu chi phí cần có những thành phần quản trị nào?

Gợi ý trả lời:

1. Phân tích tương tác chi phí và mức sử dụng theo thời gian và dimension.
2. Dữ liệu Billing được tổng hợp và cập nhật có độ trễ.
3. AmortizedCost phân bổ khoản trả trước theo thời hạn cam kết; UnblendedCost theo cách ghi nhận unblended.
4. Khi muốn xem chi phí amortized sau các khoản giảm giá net đủ điều kiện.
5. Các loại usage có đơn vị đo khác nhau.
6. Dịch vụ nào đóng góp chi phí.
7. Filter giới hạn tập dữ liệu; group by chia dữ liệu thành nhóm.
8. Để tag đủ điều kiện xuất hiện như chiều phân bổ chi phí.
9. Nhóm chi phí theo quy tắc nghiệp vụ như BU, sản phẩm hoặc môi trường.
10. ΔC = C1 - C0; Δ% = ΔC / C0 × 100%.
11. Báo số tiền tuyệt đối và đánh dấu chi phí/nhóm mới, không chia cho 0.
12. Để thấy cả tác động tài chính và mức độ thay đổi tương đối.
13. Volume là lượng dùng; rate là đơn giá; mix là cơ cấu loại tài nguyên/usage.
14. Nó cho biết chi phí trên mỗi đơn hàng cải thiện hay xấu đi.
15. Utilization đo mức dùng cam kết; coverage đo phần workload đủ điều kiện được cam kết bao phủ.
16. Forecast phụ thuộc lịch sử và không biết mọi thay đổi tương lai.
17. Khi cần line item, resource-level detail hoặc phân tích tùy biến.
18. Kỳ, metric, granularity, scope, filter, group by và thời điểm trích xuất.
19. Để phân biệt usage với fee, credit, refund, tax và adjustment.
20. Nguyên nhân đã xác minh, owner, mức tiết kiệm kỳ vọng, thời hạn, cách đo và đánh giá rủi ro.

## 22. Tài liệu tham khảo chính thức

Các tài liệu AWS sau đây là điểm bắt đầu để kiểm tra giao diện, metric, API và thay đổi tính năng:

- [What is AWS Cost Explorer?](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html)
- [Exploring your data using Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-exploring-data.html)
- [Cost Explorer metrics](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-advanced.html)
- [Using the Cost Explorer API](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-api.html)
- [GetCostAndUsage API reference](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_GetCostAndUsage.html)
- [GetCostForecast API reference](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_GetCostForecast.html)
- [Forecasting costs with Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-forecast.html)
- [Cost allocation tags](https://docs.aws.amazon.com/cost-management/latest/userguide/activating-tags.html)
- [Organizing costs using AWS Cost Categories](https://docs.aws.amazon.com/cost-management/latest/userguide/cost-categories.html)
- [Managing your costs with AWS Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)
- [Detecting unusual spend with AWS Cost Anomaly Detection](https://docs.aws.amazon.com/cost-management/latest/userguide/manage-ad.html)
- [What is the AWS Cost and Usage Report?](https://docs.aws.amazon.com/cur/latest/userguide/what-is-cur.html)
- [AWS Data Exports](https://docs.aws.amazon.com/cur/latest/userguide/dataexports.html)
- [AWS Organizations consolidated billing](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/consolidated-billing.html)

Tài liệu AWS có thể thay đổi theo thời gian và theo loại tài khoản. Khi triển khai trong môi trường thật, hãy xác nhận metric, dimension, quyền IAM, phạm vi API và tính năng đang được hỗ trợ trong tài khoản/Region của tổ chức.

