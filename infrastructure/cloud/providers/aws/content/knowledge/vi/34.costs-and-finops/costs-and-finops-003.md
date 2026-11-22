# Billing, consolidated billing và phân bổ chi phí

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích cách AWS tính phí, lập hóa đơn và cung cấp dữ liệu chi phí.
- Phân biệt AWS account độc lập, AWS Organizations, management account, member account và payer account.
- Mô tả consolidated billing, lợi ích gộp usage, volume discounts, Reserved Instances và Savings Plans.
- Cấu hình mô hình chia sẻ discount phù hợp với cấu trúc tổ chức.
- Phân biệt consolidated billing với Billing Transfer giữa nhiều AWS Organizations.
- Xây dựng taxonomy cost allocation bằng account, resource tags, account tags và AWS Cost Categories.
- Thiết kế showback, chargeback và phân bổ shared costs.
- Chọn AWS Bills, Cost Explorer, AWS Budgets, Cost Anomaly Detection và Data Exports CUR 2.0 theo mục đích.
- Giải thích vai trò của AWS Billing Conductor và dữ liệu pro forma.
- Bảo vệ quyền truy cập billing, dữ liệu CUR và quy trình quản trị tài chính cloud.
- Thiết kế quy trình FinOps từ dự báo, theo dõi, phân bổ, đối soát đến tối ưu chi phí.

## 1. Vì sao Billing và cost allocation quan trọng?

Khi một doanh nghiệp sử dụng AWS cho nhiều sản phẩm, môi trường và đội ngũ, câu hỏi không chỉ là tổng hóa đơn tháng này bao nhiêu. Tổ chức cần biết:

- Tài khoản, sản phẩm, ứng dụng hoặc môi trường nào đang tiêu thụ ngân sách?
- Chi phí nào thuộc trực tiếp một đội, chi phí nào là nền tảng dùng chung?
- Mức tăng chi phí đến từ tăng traffic, thay đổi kiến trúc, giá dịch vụ hay cấu hình chưa tối ưu?
- Discount từ Reserved Instances (RI) và Savings Plans (SP) đang được sử dụng ở đâu?
- Đội nào chịu trách nhiệm cho chi phí chưa có owner?
- Hóa đơn AWS có thể đối soát với ngân sách, purchase order và sổ cái tài chính nội bộ như thế nào?

AWS Billing and Cost Management cung cấp dữ liệu sử dụng, chi phí, hóa đơn và công cụ phân tích. AWS Organizations consolidated billing gom việc thanh toán nhiều tài khoản vào một billing family. Cost allocation giúp ánh xạ các dòng chi phí sang cấu trúc kinh doanh. FinOps kết nối các dữ liệu này với trách nhiệm và quyết định vận hành.

Một hệ thống billing tốt phải trả lời được hai câu hỏi khác nhau:

1. **AWS tính và thu tiền bao nhiêu?** Đây là câu hỏi về billable charges và invoice.
2. **Doanh nghiệp muốn phân bổ số tiền đó cho ai?** Đây là câu hỏi về showback, chargeback và internal cost model.

Hai con số có thể khác nhau vì tổ chức có thể phân bổ shared services, áp dụng internal markup hoặc dùng giá nội bộ. Cần ghi rõ dữ liệu nào là hóa đơn AWS và dữ liệu nào là số liệu phân bổ nội bộ.

## 2. Các thuật ngữ billing cơ bản

| Thuật ngữ | Ý nghĩa |
|---|---|
| AWS account | Ranh giới quản trị, bảo mật, tài nguyên và billing |
| Management account | Tài khoản tạo và sở hữu một AWS Organization |
| Member account | Tài khoản thành viên thuộc Organization |
| Payer account | Tài khoản tạo, quản lý và thanh toán consolidated bill; trong mô hình Organizations thông thường là management account |
| Linked account | Cách gọi phổ biến cho member account khi phân tích billing |
| Billing family | Nhóm tài khoản có usage được tổng hợp cho mục đích billing |
| Billing period | Kỳ tính phí, thường theo tháng |
| Invoice | Chứng từ AWS phát hành để xác định số tiền phải thanh toán |
| Usage | Lượng dịch vụ đã tiêu thụ |
| Charge | Khoản phí phát sinh từ usage, subscription hoặc purchase |
| Credit | Khoản tín dụng được áp dụng để giảm số tiền phải trả theo điều kiện |
| Refund | Khoản hoàn trả được ghi nhận trong billing data |
| Discount | Khoản giảm giá theo pricing tier, RI, SP hoặc thỏa thuận |
| Showback | Báo cáo chi phí cho đội sử dụng để họ thấy mức tiêu thụ |
| Chargeback | Phân bổ chi phí nội bộ vào cost center hoặc ngân sách chịu trách nhiệm |
| Pro forma billing | Dữ liệu billing mô phỏng theo cấu hình giá nội bộ, không phải invoice AWS |

Trong tài liệu AWS, management account và payer account thường trùng nhau khi dùng consolidated billing thông thường. Với Billing Transfer, vai trò thanh toán có thể chuyển sang một bill-transfer account bên ngoài Organization. Cần dùng đúng thuật ngữ theo mô hình đang triển khai.

## 3. Thiết kế account structure cho quản trị chi phí

AWS account là một chiều phân bổ chi phí mạnh vì mỗi account có thể đại diện cho một môi trường, sản phẩm, đội hoặc ranh giới bảo mật.

Một cấu trúc tham khảo:

~~~mermaid
flowchart TD
    P["Management / Payer account"] --> O["AWS Organizations"]
    O --> S["Security OU"]
    O --> I["Infrastructure OU"]
    O --> W["Workloads OU"]
    O --> D["Sandbox OU"]
    S --> SA["Security account"]
    I --> N["Network account"]
    I --> L["Logging account"]
    W --> A["Product A - Production"]
    W --> B["Product B - Production"]
    W --> T["Shared services"]
    D --> X["Developer sandbox accounts"]
~~~

Các account có thể được phân chia theo:

- **Environment:** production, staging, development, sandbox.
- **Business unit:** finance, engineering, marketing, data.
- **Product/application:** storefront, analytics, identity platform.
- **Function:** security, networking, logging, shared platform.

Không cần tạo một account cho mọi project nhỏ. Account sprawl làm tăng công việc quản lý, nhưng gom tất cả workload vào một account làm giảm khả năng cô lập, theo dõi và quy trách nhiệm. Hãy chọn ranh giới có ý nghĩa lâu dài.

### 3.1 Billing boundary và security boundary

Consolidated billing không biến nhiều AWS accounts thành một account duy nhất. Mỗi account vẫn có tài nguyên, credentials, IAM policies và quyền truy cập riêng. Management account chịu trách nhiệm thanh toán cho member accounts, nhưng điều đó không tự động cấp quyền quản trị mọi workload của member account.

Nếu cần quản trị tập trung, tổ chức phải thiết kế AWS Organizations all features, IAM roles, IAM Identity Center, service control policies (SCPs), delegated administration và quy trình truy cập phù hợp. Consolidated billing chỉ giải quyết phần tổng hợp billing.

### 3.2 Bảo vệ management account

Management account có quyền và trách nhiệm đặc biệt. Nên:

- Không triển khai workload ứng dụng vào management account.
- Bật MFA mạnh cho root user và bảo vệ phương thức khôi phục.
- Không tạo root access key.
- Dùng IAM Identity Center hoặc role được cấp quyền có kiểm soát cho công việc thường ngày.
- Tách quyền xem hóa đơn, quản lý thanh toán, quản lý Organizations và quản trị workload.
- Theo dõi CloudTrail cho thay đổi Organizations, billing preferences, cost categories và quyền truy cập billing.

## 4. Consolidated billing với AWS Organizations

Consolidated billing cho phép một AWS Organization gom billing và payment của nhiều accounts. Management account nhận consolidated bill và thanh toán charges phát sinh từ các member accounts.

Các lợi ích chính:

1. **Một hóa đơn tổng hợp:** nhiều accounts trong cùng Seller of Record (SOR) được gom vào một bill. SOR là pháp nhân địa phương bán dịch vụ AWS và là bên ký kết với khách hàng. Nếu Organization có accounts thuộc nhiều SOR, AWS phát hành một bill cho mỗi SOR.
2. **Theo dõi tập trung:** management account xem tổng chi phí và có thể phân tích theo từng member account.
3. **Gộp usage:** AWS kết hợp usage của các accounts để tính volume pricing tiers.
4. **Chia sẻ discount:** RI và Savings Plans có thể được chia sẻ giữa các accounts đủ điều kiện theo billing preferences.
5. **Không thu thêm phí consolidated billing:** tính năng này không có phí riêng.

Member account vẫn có thể xem usage và charges của chính nó, nhưng bill của member account chỉ mang tính thông tin trong billing family. Management account là bên chịu trách nhiệm thanh toán consolidated bill. Chủ tài khoản member không nhìn thấy billing data của management account hoặc các member khác nếu không được cấp quyền thích hợp.

### 4.1 Gộp volume pricing

Một số dịch vụ có pricing tiers giảm giá khi tổng usage tăng. Khi bật consolidated billing, AWS cộng usage của các accounts trong Organization để xác định tier áp dụng.

Ví dụ minh họa:

- Product A sử dụng 7 TB trong tháng.
- Product B sử dụng 5 TB trong tháng.
- Tổng usage của billing family là 12 TB.

Nếu dịch vụ có tier giá thấp hơn sau ngưỡng 10 TB, tổng usage có thể giúp Organization đạt tier tốt hơn so với hai accounts đứng riêng. AWS phân bổ phần discount theo quy tắc billing của dịch vụ và dữ liệu usage.

Không phải mọi dịch vụ hoặc mọi dimension đều có volume discount. Cần xem pricing page của từng dịch vụ.

### 4.2 Thời điểm account tham gia Organization

Khi member account chấp nhận lời mời tham gia, management account bắt đầu chịu trách nhiệm cho charges phát sinh từ thời điểm account gia nhập. Nếu account tham gia giữa tháng, chủ sở hữu cũ vẫn chịu charges phát sinh trước thời điểm gia nhập.

Khi member account rời Organization, account đó có thể mất quyền truy cập Cost Explorer data được tạo trong thời gian nó là member. Dữ liệu không bị xóa; management account cũ vẫn truy cập được. Nếu account gia nhập lại Organization, quyền truy cập dữ liệu trước đó có thể được khôi phục theo hướng dẫn AWS.

### 4.3 Consolidated billing không tự chia chi phí nội bộ

AWS gom bill và áp dụng discount theo billing rules. Việc phân bổ cho Product A, Product B hoặc các phòng ban vẫn cần account dimensions, cost allocation tags, Cost Categories hoặc một hệ thống chargeback riêng.

## 5. Chia sẻ Reserved Instances và Savings Plans

RI và Savings Plans là cam kết sử dụng để đổi lấy giá ưu đãi. Trong Organization, discount sharing cho phép usage ở một account được hưởng lợi từ commitment mua ở account khác nếu thỏa điều kiện dịch vụ, Region, scope và billing preference.

Ví dụ:

- Account A mua Savings Plan nhưng workload sử dụng ít hơn commitment.
- Account B có compute usage phù hợp.
- Nếu discount sharing được bật và usage đáp ứng điều kiện, phần commitment chưa sử dụng có thể áp dụng cho usage của Account B.

Điều này giúp tối ưu utilization toàn Organization, nhưng làm phức tạp việc phân bổ chi phí. Account mua commitment có thể không phải account nhận toàn bộ discount benefit.

### 5.1 Ba chế độ discount sharing

AWS Billing preferences hiện hỗ trợ ba lựa chọn:

| Chế độ | Cách phân bổ | Trường hợp phù hợp |
|---|---|---|
| Open sharing | Discount có thể chia sẻ với mọi account đã bật sharing trong Organization; đây là mặc định | Tối đa hóa tối ưu chi phí toàn Organization |
| Prioritized group sharing | Ưu tiên account mua commitment, sau đó trong các nhóm được định nghĩa, rồi đến các account còn lại đủ điều kiện | Muốn cân bằng giữa kiểm soát và tối ưu |
| Restricted group sharing | Discount chỉ chia sẻ trong các nhóm được định nghĩa | Phân tách discount theo business unit hoặc khách hàng |

Để dùng group sharing, tạo Cost Category xác định các nhóm account. Mỗi account chỉ thuộc một sharing group; các nhóm không được chồng lấn; management account không thuộc sharing group. Tài khoản sở hữu Savings Plan phải được bật discount sharing để benefit có thể được sử dụng.

Nhóm sharing có thể giảm tổng mức tối ưu discount nếu commitment không được sử dụng trong nhóm của nó. Vì vậy, cần mô phỏng ảnh hưởng trước khi chuyển từ open sharing sang restricted group sharing.

### 5.2 Credits có preference riêng

Credit sharing khác RI/SP discount sharing. Payer account có thể chọn account nào được phép chia sẻ hoặc nhận credits trong billing family. Không nên giả định bật RI/SP sharing là credits cũng tự động chia sẻ.

### 5.3 Phân biệt cost và savings

Khi phân tích RI/SP, cần tách:

- Chi phí mua commitment.
- Usage được cover bởi commitment.
- Unused commitment.
- Discount benefit được áp dụng cho account sử dụng.
- Amortized cost để đánh giá hiệu quả kinh tế theo thời gian.

Dùng cash bill để đối soát số tiền AWS thu trong kỳ. Dùng amortized view để đánh giá chi phí kinh tế của workload theo ngày/tháng và tránh hiểu nhầm một khoản upfront lớn là toàn bộ chi phí của riêng tháng mua.

## 6. Billing Transfer giữa nhiều AWS Organizations

Consolidated billing gom accounts trong cùng một Organization. Nếu doanh nghiệp có nhiều Organizations và muốn một tài khoản bên ngoài quản lý, thanh toán các consolidated bills đó, hãy đánh giá **Billing Transfer**.

Trong Billing Transfer:

- **Bill-source account:** management account của Organization tạo consolidated bill.
- **Bill-transfer account:** management account bên ngoài được chỉ định quản lý và thanh toán bill.
- Hai bên là management accounts của các Organizations khác nhau.
- Bill-transfer account gửi invitation; bill-source account chấp nhận.
- Invitation phải được chấp nhận trước thời điểm hiệu lực theo yêu cầu AWS.
- Transfer bắt đầu và kết thúc theo ranh giới tháng, tại thời điểm UTC do AWS quy định.

Billing Transfer tập trung thanh toán và cost management data qua nhiều Organizations. Nó không gộp các Organizations thành một billing computation boundary. Volume discounts, RI và Savings Plans vẫn được tính trong từng AWS Organization riêng. Không nên kỳ vọng RI/SP của Organization A tự cover usage của Organization B chỉ vì hai bên dùng chung bill-transfer account.

### 6.1 Tác động cần đánh giá trước khi chuyển

- Các CUR configurations hiện có có thể trở thành Unhealthy và cần tạo lại.
- Bill-source account có thể mất quyền truy cập lịch sử cost data trong Cost Anomaly Detection.
- Cost Anomaly Detection không hỗ trợ tạo alert cho usage của bill-source account theo mô hình Billing Transfer.
- Một số credit, Free Tier, support charges, tax hoặc refund có thể không xuất hiện trong pro forma data theo cấu hình mặc định.
- Bill-source account cần tải CUR và dữ liệu AWS Budgets cần lưu trước khi chuyển.
- Cost Explorer pro forma có thể không có hourly granularity; dùng CUR để phân tích chi tiết theo giờ.
- Cần kiểm tra lại quyền truy cập, cost categories, cost allocation tags và báo cáo sau khi transfer.

Billing Transfer là thay đổi quan trọng trong trách nhiệm tài chính. Hãy lập kế hoạch đối soát, dữ liệu lịch sử và thông báo cho Finance trước khi kích hoạt.

## 7. Các nguồn dữ liệu billing khác nhau

Không phải mọi trang trong Billing and Cost Management đều hiển thị cùng một con số. Chọn đúng nguồn dữ liệu theo câu hỏi cần trả lời.

| Nguồn | Mục tiêu | Cách sử dụng |
|---|---|---|
| Bills | Xem charges và invoice theo kỳ | Đối soát số tiền phải trả |
| Payments | Xem trạng thái thanh toán và giao dịch | Theo dõi payment |
| Cost Explorer | Phân tích cost/usage theo account, service, Region, tag, category và thời gian | Tìm cost drivers và xu hướng |
| AWS Budgets | Theo dõi chi phí/usage so với ngưỡng hoặc kế hoạch | Cảnh báo và hành động |
| Cost Anomaly Detection | Phát hiện spending pattern bất thường | Điều tra tăng chi phí ngoài dự kiến |
| Cost Categories | Ánh xạ line items vào cấu trúc nội bộ | Phân bổ và báo cáo |
| Cost allocation tags | Phân tích chi phí theo resource metadata | Gắn cost với app/team/environment |
| Data Exports CUR 2.0 | Dữ liệu chi tiết để truy vấn và tích hợp | Athena, QuickSight, data warehouse |
| AWS Billing Conductor | Tạo billing view theo pricing rules nội bộ | Showback/chargeback và billing transfer |

### 7.1 Bills và invoice là nguồn đối soát tài chính

Bills page hiển thị charges theo billing period, service, account, purchase và các khoản thuế liên quan. Với kỳ chưa đóng, số liệu là estimated charges. Khi AWS phát hành invoice, trạng thái billing period chuyển sang Issued và số tiền invoice là căn cứ thanh toán.

Không dùng Cost Explorer làm chứng từ thay cho invoice. Cost Explorer là công cụ phân tích, có cách nhóm dữ liệu và hiển thị discount, credits, refunds, taxes khác với Bills page.

### 7.2 Cash basis và amortized cost

Billing data luôn thể hiện theo cash basis. Ví dụ, doanh nghiệp mua một Savings Plan một năm với hình thức all upfront trong tháng 10. Invoice tháng 10 ghi nhận khoản thanh toán upfront đó.

Cost Explorer có thể hiển thị amortized cost, phân bổ khoản upfront đều trong thời gian cam kết để phân tích hiệu quả workload. Hai cách nhìn trả lời hai câu hỏi khác nhau:

- Cash basis: tháng này AWS thu bao nhiêu?
- Amortized basis: workload đang tiêu thụ bao nhiêu chi phí kinh tế theo thời gian?

### 7.3 Vì sao Bills và Cost Explorer có thể khác nhau?

Một số nguyên nhân:

- Khác thời điểm refresh dữ liệu ước tính trong tháng.
- Cost Explorer có granular dimensions như Availability Zone hoặc operating system.
- Cost Explorer có thể nhóm EC2 Instances và EC2 Other riêng, trong khi invoice nhóm theo service.
- Amortized cost phân bổ commitment theo thời gian.
- Refunds, credits và taxes có thể được trình bày khác.
- Rounding và mức độ chi tiết xử lý dữ liệu khác nhau.

Khi cần biết số tiền phải trả AWS, đối chiếu invoice cuối cùng. Khi cần hiểu workload tiêu thụ tài nguyên nào và tìm cơ hội tối ưu, dùng Cost Explorer hoặc CUR.

## 8. Xây dựng mô hình cost allocation

Cost allocation là quá trình ánh xạ AWS costs vào cấu trúc chịu trách nhiệm của doanh nghiệp. Một mô hình tốt kết hợp nhiều chiều thay vì cố gắng dùng một tag duy nhất.

Các chiều thường dùng:

| Chiều | Ví dụ | Nguồn dữ liệu |
|---|---|---|
| Account | Product A production | AWS account ID/name |
| Business unit | Engineering, Marketing | Account tag hoặc Cost Category |
| Cost center | CC-ENG-001 | Resource tag, account tag |
| Application | storefront, analytics | Resource tag hoặc awsApplication |
| Environment | prod, staging, dev | Resource tag |
| Owner | team-checkout | Resource tag hoặc account metadata |
| Project | migration-2026 | Resource tag |
| Service | EC2, S3, RDS | Billing dimension |
| Region | ap-southeast-1 | Billing dimension |
| Usage type | BoxUsage, DataTransfer | CUR usage dimensions |

Một tài nguyên có thể thuộc nhiều chiều cùng lúc. Ví dụ, EC2 instance có:

- CostCenter = CC-ENG-001
- Application = checkout
- Environment = prod
- Owner = team-commerce

Báo cáo có thể tổng hợp chi phí theo CostCenter để Finance đối soát, theo Application để Product Owner tối ưu, hoặc theo Environment để phát hiện chi phí development còn chạy ngoài giờ.

### 8.1 Chọn ranh giới account trước khi dùng tags

Nếu mỗi product có account production riêng, account dimension đã cung cấp ranh giới rõ ràng. Tags giúp chia nhỏ hơn trong account đó.

Một số charges không gắn được resource tag hoặc không thuộc một resource đơn lẻ, ví dụ shared support, một số credits, tax hoặc network/shared platform costs. Account tags và Cost Categories giúp lấp khoảng trống này.

### 8.2 Showback và chargeback

- **Showback:** gửi báo cáo cho đội sử dụng để họ nhìn thấy chi phí, nhưng không chuyển khoản nội bộ.
- **Chargeback:** phân bổ chi phí vào cost center, ngân sách hoặc sổ cái của đội chịu trách nhiệm.
- **Hybrid:** showback trước để cải thiện độ chính xác, sau đó chargeback khi taxonomy và dữ liệu đã ổn định.

Chargeback cần quy định rõ cách phân bổ discount, shared services, tax, credits, support, Marketplace và chi phí chưa có owner. Nếu chỉ lấy unblended cost rồi chia đều, kết quả có thể không phản ánh economics thực tế.

## 9. Thiết kế tag taxonomy cho cost allocation

Tag là cặp key/value gắn vào resource. Một resource chỉ có một value cho mỗi key. Nên thống nhất key names và value conventions trên toàn Organization.

Một taxonomy tham khảo:

| Key | Ví dụ value | Mục đích |
|---|---|---|
| CostCenter | CC-ENG-001 | Đối soát với Finance |
| BusinessUnit | Engineering | Phòng ban chịu chi phí |
| Application | checkout | Sản phẩm/ứng dụng |
| Environment | prod | Môi trường |
| Owner | team-commerce | Đội chịu trách nhiệm |
| Project | migration-2026 | Dự án có thời hạn |
| DataClass | internal | Phân loại vận hành, không chứa thông tin nhạy cảm |

### 9.1 Nguyên tắc thiết kế

- Chọn một cách viết nhất quán, ví dụ PascalCase cho key và lowercase cho value.
- Chuẩn hóa value bằng danh mục được quản lý.
- Không dùng email cá nhân, customer name, credential hoặc dữ liệu nhạy cảm trong tag.
- Có owner cho mỗi key.
- Xác định tag bắt buộc theo loại resource.
- Dùng Infrastructure as Code để gắn tags ngay khi tạo resource.
- Kiểm tra service có hỗ trợ cost allocation tags cho resource type đó hay không.
- Có default hoặc quy trình xử lý unallocated costs.
- Đánh giá tag coverage hàng tháng.

Tag policy trong AWS Organizations có thể hỗ trợ chuẩn hóa tag keys/values và đánh giá tuân thủ trên các dịch vụ được hỗ trợ. Tuy nhiên, không nên giả định mọi resource đều tự động nhận đủ tags. Cần kiểm tra service support và tích hợp guardrails trong IaC/CI pipeline.

### 9.2 AWS-generated và user-defined tags

AWS hỗ trợ hai loại cost allocation tags:

- **AWS-generated tags:** do AWS hoặc AWS Marketplace tạo và gắn.
- **User-defined tags:** do tổ chức tạo và gắn vào resource.

AWS-generated tag thường dùng prefix aws:. User-defined tag xuất hiện với prefix user: trong cost allocation reports. Prefix aws: được dành riêng cho AWS; không dùng cho tag tự tạo.

Một số tag như awsApplication có thể tự động được gắn cho resources liên kết với applications trong AWS Service Catalog AppRegistry và được tự động activate làm cost allocation tag. Hãy kiểm tra tình trạng của tag này nếu tổ chức dùng AppRegistry.

## 10. Kích hoạt cost allocation tags

Gắn tag lên resource chưa đủ để tag xuất hiện trong billing reports. Cần kích hoạt tag key trong Billing and Cost Management.

Quy trình:

1. Tạo tag key/value trên các resource được hỗ trợ.
2. Chờ tag key xuất hiện trong trang Cost allocation tags.
3. Đăng nhập management account hoặc account độc lập có quyền quản lý billing.
4. Mở Billing and Cost Management.
5. Chọn Cost allocation tags.
6. Chọn user-defined hoặc AWS-generated tag keys cần kích hoạt.
7. Chọn Activate.
8. Xác minh tag xuất hiện trong Cost Explorer hoặc CUR.

Có thể mất tới 24 giờ để tag key xuất hiện sau khi được tạo và áp dụng lên resource. Sau khi kích hoạt, có thể mất thêm tới 24 giờ để tag key hoạt động trong billing data.

Kích hoạt theo tag key, vì vậy thao tác activate/deactivate ảnh hưởng tất cả tag values thuộc key đó. Ví dụ, activate key Environment sẽ áp dụng cho values prod, staging và dev.

### 10.1 Account tags cho cost allocation

Account tags là chiều phân bổ ở cấp AWS account. Usage và costs trong account có thể kế thừa account-level tags trong báo cáo. Cơ chế này hữu ích cho những khoản không thể gắn tag trực tiếp vào resource, bao gồm credits, refunds và một số service charges.

Account tags có thể kết hợp với Cost Explorer, CUR 2.0, FOCUS, AWS Budgets, Cost Categories và Cost Anomaly Detection sau khi được kích hoạt. Đây là lớp bổ sung cho resource tags, không thay thế resource tags khi cần phân tích tới từng application hoặc resource.

### 10.2 Chú ý khi account chuyển Organization

Khi account chuyển sang một Organization khác, trạng thái activated của các cost allocation tags đã bật trước đó có thể mất. Management account mới cần kiểm tra và activate lại các tag keys cần thiết để báo cáo không bị thiếu chiều phân bổ.

## 11. AWS Cost Categories

Cost Categories cho phép ánh xạ billing line items vào các nhóm có ý nghĩa với doanh nghiệp. Một Cost Category là một key/value áp dụng lên cost line items:

- Category name là key.
- Category value là giá trị được gán theo rule.

Ví dụ:

- Cost Category: Department
- Values: Engineering, Marketing, Finance, Shared Platform

Cost Categories được quản lý từ management account của Organization hoặc account độc lập. Với Billing Transfer, bill-source và bill-transfer accounts quản lý categories trong phạm vi Organization của chính họ theo vai trò được AWS hỗ trợ.

### 11.1 Các dimension để nhóm chi phí

Rule có thể dựa trên:

- Account hoặc linked account.
- Cost allocation tags.
- Charge type, ví dụ credits/refunds.
- AWS service.
- Region.
- Usage type.
- Billing entity, ví dụ AWS hoặc AWS Marketplace.
- Một Cost Category khác hoặc inherited values theo thiết kế.

Rules được đánh giá theo thứ tự từ trên xuống. Nếu một line item khớp nhiều rule, rule đầu tiên phù hợp được sử dụng. Hãy đặt rule cụ thể trước rule tổng quát và có default value cho các khoản không khớp.

### 11.2 Ví dụ phân loại

Giả sử công ty có ba product teams:

| Rule | Điều kiện | Cost Category value |
|---|---|---|
| 1 | Account thuộc Product A | Product A |
| 2 | Account thuộc Product B | Product B |
| 3 | Tag CostCenter = CC-ENG-001 | Engineering |
| 4 | Service = AWS Support | Shared Platform |
| Default | Không khớp rule nào | Unallocated |

Trong thực tế, hãy thiết kế rule order để account-level ownership và resource-level tags không ghi đè sai nhau. Có thể tạo nhiều categories như BusinessUnit, Application, Environment để hỗ trợ các góc nhìn khác nhau.

### 11.3 Inherited values và hierarchical categories

Inherited value rule cho phép Cost Category lấy giá trị động từ dimension, ví dụ kế thừa value của tag key Team. Nếu tag values thay đổi theo team, category có thể phản ánh các giá trị mới mà không cần tạo rule tĩnh cho từng team.

Có thể tạo hierarchical relationships giữa categories. Ví dụ:

- Cost Category Team có Engineering, Marketing, Data.
- Cost Category BusinessUnit gom Engineering và Data thành Technology; Marketing thành Growth.

Cost Categories xuất hiện như dimension trong Cost Explorer và Budgets, như column trong CUR, và có thể dùng làm monitor type trong Cost Anomaly Detection.

### 11.4 Thời điểm hiệu lực

Cost Categories thường có hiệu lực từ đầu tháng hiện tại. Khi tạo category, có thể chọn effective date phù hợp và áp dụng rules ngược về thời điểm được hỗ trợ. Hãy xác nhận preview và dữ liệu sau khi category chuyển sang trạng thái Applied trước khi dùng làm căn cứ chargeback.

## 12. Split charges và phân bổ shared costs

Một số chi phí không thuộc riêng một đội:

- Shared networking và NAT Gateway.
- Logging, monitoring và security platform.
- Enterprise support.
- Shared database hoặc data platform.
- Shared CI/CD runners.
- Data transfer giữa nhiều applications.

Cost Categories hỗ trợ split charge rules để chia một category value sang các target values.

Ba phương pháp phân bổ:

| Phương pháp | Cách tính | Ví dụ |
|---|---|---|
| Proportional | Theo tỷ trọng weighted cost của target groups | Chia shared platform theo direct costs |
| Fixed | Theo tỷ lệ phần trăm do tổ chức định nghĩa | Engineering 60%, Marketing 30%, Finance 10% |
| Even | Chia đều cho các target values | Ba team nhận mỗi bên một phần ba |

Ví dụ, Shared Platform có 2.000 USD. Tổ chức quyết định phân bổ cố định:

- Engineering: 60% = 1.200 USD.
- Marketing: 30% = 600 USD.
- Finance: 10% = 200 USD.

Split charge rules chỉ hiển thị phần phân bổ trong Cost Categories details page. Phần split này không xuất hiện và không làm thay đổi AWS CUR hoặc Cost Explorer. Nếu hệ thống tài chính cần dữ liệu chargeback chi tiết trong data warehouse, hãy triển khai phép phân bổ tương ứng trong pipeline nội bộ và giữ công thức có thể kiểm toán.

Một category value chỉ có thể dùng làm source một lần trên toàn bộ split charge rules của category. Giá trị đã dùng làm source không thể đồng thời dùng làm target. AWS giới hạn số split charge rules cho mỗi Cost Category; kiểm tra quota hiện hành trước khi thiết kế nhiều tầng phân bổ.

## 13. Quy trình showback và chargeback

Một quy trình trưởng thành thường có các bước:

1. **Capture:** thu thập usage và charges từ tất cả accounts.
2. **Normalize:** chuẩn hóa account names, tag values, service names và billing dimensions.
3. **Categorize:** áp dụng Cost Categories và mapping nội bộ.
4. **Allocate:** phân bổ shared costs, discounts, credits và support theo chính sách.
5. **Validate:** đối chiếu tổng allocation với invoice và xác định unallocated costs.
6. **Publish:** cung cấp báo cáo theo business unit, product và application.
7. **Review:** họp với owners để giải thích variance và hành động tối ưu.
8. **Reconcile:** lưu snapshot và đối soát cuối kỳ với Finance.

### 13.1 Ví dụ chargeback

Giả sử invoice AWS cuối kỳ là 10.000 USD:

| Nhóm | Direct cost | Shared cost allocation | Tổng nội bộ |
|---|---:|---:|---:|
| Engineering | 4.000 | 1.200 | 5.200 |
| Marketing | 2.000 | 600 | 2.600 |
| Finance | 2.000 | 200 | 2.200 |
| **Tổng** | **8.000** | **2.000** | **10.000** |

Bảng trên là mô hình nội bộ. Nếu doanh nghiệp áp dụng markup, platform fee hoặc internal credits, tổng chargeback có thể khác invoice AWS. Khi đó cần có dòng điều chỉnh rõ ràng và không gọi số liệu nội bộ là AWS invoice.

### 13.2 Quy tắc phân bổ discount

Tổ chức cần quyết định discount được ghi nhận ở:

- Account mua RI/SP.
- Account nhận benefit.
- Shared discount pool.
- Business unit theo tỷ trọng usage.
- Một cost center trung tâm.

Chọn một chính sách và duy trì nhất quán. Nếu thay đổi discount sharing hoặc cách phân bổ giữa tháng, cần ghi nhận thời điểm hiệu lực để giải thích chênh lệch.

## 14. AWS Cost Explorer

Cost Explorer giúp phân tích lịch sử cost và usage, so sánh các giai đoạn, forecast và tìm cost drivers.

Các dimension thường dùng:

- Linked account.
- Service.
- Region.
- Usage type.
- Instance type.
- Availability Zone.
- Purchase option.
- Cost allocation tag.
- Cost Category.

Các metric có thể xem gồm Unblended Cost, Amortized Cost, Net Amortized Cost, Usage Quantity và các lựa chọn phù hợp khác tùy báo cáo.

### 14.1 Các câu hỏi Cost Explorer trả lời

- Account nào tăng chi phí nhiều nhất?
- EC2 hay NAT Gateway đang tạo cost growth?
- Product A production có chi phí cao hơn tháng trước không?
- Savings Plans coverage/utilization có cải thiện không?
- Data transfer tăng ở Region hoặc usage type nào?
- Cost theo tag Owner hoặc Application có thiếu dữ liệu không?

### 14.2 Ví dụ AWS CLI

Lấy chi phí theo linked account và service cho tháng 10/2026:

~~~bash
aws ce get-cost-and-usage \
  --time-period Start=2026-10-01,End=2026-11-01 \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=LINKED_ACCOUNT Type=DIMENSION,Key=SERVICE
~~~

End date của Cost Explorer là exclusive. Ví dụ trên lấy dữ liệu từ đầu ngày 01/10 đến trước 01/11 theo UTC.

Lấy chi phí amortized theo ngày:

~~~bash
aws ce get-cost-and-usage \
  --time-period Start=2026-10-01,End=2026-11-01 \
  --granularity DAILY \
  --metrics AmortizedCost NetAmortizedCost \
  --group-by Type=DIMENSION,Key=LINKED_ACCOUNT
~~~

Các API và metrics có thể có điều kiện hỗ trợ theo loại billing data. Kiểm tra AWS Cost Explorer API Reference và quyền IAM trước khi tự động hóa.

## 15. AWS Data Exports và Cost and Usage Report 2.0

Cost and Usage Report (CUR) cung cấp dữ liệu chi tiết nhất về AWS costs và usage. AWS Data Exports là cách hiện hành để tạo các exports, trong đó CUR 2.0 là lựa chọn được AWS khuyến nghị cho dữ liệu cost/usage chi tiết mới.

CUR 2.0 có các cải tiến:

- Schema ổn định hơn với tập columns nhất quán.
- Dùng nested key-value columns để giảm độ thưa dữ liệu.
- Có thêm các trường nhận diện account, principal và cost analytics.
- Có thể tùy chọn cột, lọc rows và cấu hình export bằng SQL theo khả năng Data Exports.

### 15.1 Luồng dữ liệu

~~~mermaid
flowchart LR
    A["AWS Billing data"] --> B["Data Exports - CUR 2.0"]
    B --> C["Amazon S3"]
    C --> D["AWS Glue Data Catalog"]
    D --> E["Amazon Athena"]
    E --> F["QuickSight / FinOps dashboard"]
    E --> G["Finance data warehouse"]
~~~

Data Exports ghi dữ liệu vào Amazon S3. Có thể dùng Glue Catalog và Athena để truy vấn, QuickSight để trực quan hóa hoặc pipeline nội bộ để tích hợp ERP/finance warehouse.

Sau khi tạo export, AWS có thể mất tới 24 giờ để bắt đầu giao dữ liệu. Khi đã bắt đầu, billing export được refresh ít nhất mỗi ngày. Dữ liệu tháng hiện tại có thể tiếp tục được cập nhật cho đến khi kỳ billing kết thúc và có thể được điều chỉnh sau đó.

### 15.2 Chọn dữ liệu cần export

Tùy mục tiêu, có thể tạo:

- CUR 2.0 standard export.
- Cost and usage dashboard export.
- Cost optimization recommendations export.
- FOCUS exports với AWS columns theo phiên bản được hỗ trợ.
- Carbon emissions data export.
- Legacy CUR export cho pipeline cũ cần migration.

Nếu đang xây mới, ưu tiên CUR 2.0. Nếu pipeline đang dùng CUR schema cũ, hãy kiểm tra migration guide và chọn cấu hình tương thích trước khi chuyển production.

### 15.3 Những trường dữ liệu thường dùng

| Nhóm | Ví dụ trường |
|---|---|
| Billing | Billing period, payer account |
| Identity | Usage account ID, principal |
| Line item | Line item type, usage type, operation |
| Product | Product code, service attributes |
| Pricing | Public on-demand rate, pricing unit |
| Cost | Unblended cost, net unblended cost |
| Reservation | RI ARN, effective cost, unused commitment |
| Savings Plan | SP ARN, covered usage, effective cost |
| Resource tags | Resource tag key/value |
| Cost category | Cost category name/value |
| Split line item | Thông tin split cost allocation nếu có |

Tên cột thực tế phụ thuộc bảng và schema CUR 2.0. Dùng CUR 2.0 table dictionary để xác nhận tên trước khi viết query.

### 15.4 Ví dụ Athena query

Tổng unblended cost theo account và service trong một kỳ:

~~~sql
SELECT
    line_item_usage_account_id AS account_id,
    line_item_product_code AS service,
    SUM(line_item_unblended_cost) AS unblended_cost
FROM cur2_database.cur2_table
WHERE bill_billing_period_start_date >= TIMESTAMP '2026-10-01 00:00:00'
  AND bill_billing_period_start_date < TIMESTAMP '2026-11-01 00:00:00'
GROUP BY
    line_item_usage_account_id,
    line_item_product_code
ORDER BY unblended_cost DESC;
~~~

Tổng chi phí theo cost center tag nếu CUR export có cột tag tương ứng:

~~~sql
SELECT
    resource_tags_user_costcenter AS cost_center,
    SUM(line_item_unblended_cost) AS unblended_cost
FROM cur2_database.cur2_table
WHERE bill_billing_period_start_date >= TIMESTAMP '2026-10-01 00:00:00'
  AND bill_billing_period_start_date < TIMESTAMP '2026-11-01 00:00:00'
GROUP BY resource_tags_user_costcenter
ORDER BY unblended_cost DESC;
~~~

Đây là mẫu minh họa. Thay database/table, tên nested tag column và kiểu dữ liệu theo schema được tạo trong tài khoản. Nếu query có nested columns, Data Exports hỗ trợ cấu hình để chọn nested keys thành columns riêng.

### 15.5 Bảo vệ dữ liệu CUR

CUR có thể chứa thông tin chi tiết về usage, account, resource IDs, tags và pricing. Cần:

- Dùng S3 bucket riêng cho billing exports.
- Bật encryption bằng SSE-S3 hoặc SSE-KMS theo yêu cầu.
- Dùng bucket policy giới hạn AWS delivery và role phân tích.
- Bật versioning nếu cần bảo vệ lịch sử file.
- Dùng lifecycle để chuyển storage class hoặc xóa dữ liệu theo retention.
- Giới hạn quyền Athena/Glue và quyền đọc object.
- Tránh đưa CUR vào public bucket hoặc chia sẻ rộng.
- Ghi nhận thay đổi Data Exports và bucket policies.

## 16. AWS Budgets và Cost Anomaly Detection

Cost allocation cho biết ai đang tiêu tiền. Budgets và Anomaly Detection giúp phát hiện khi spending đi lệch kế hoạch.

### 16.1 AWS Budgets

AWS Budgets có thể theo dõi:

- Cost budgets.
- Usage budgets.
- Savings Plans utilization/coverage budgets.
- Reserved Instances utilization/coverage budgets.

Ví dụ, Product A có monthly budget 8.000 USD. Tạo alert ở 80%, 100% actual và 110% forecast. Gửi thông báo tới SNS topic hoặc email để owner điều tra.

Budget action có thể thực hiện một số hành động được hỗ trợ, như áp dụng IAM policy hoặc SCP, nhưng cần đánh giá kỹ tác động trước khi tự động chặn resource. Không nên dùng budget action như kill switch chung cho mọi production workloads.

### 16.2 Cost Anomaly Detection

Cost Anomaly Detection sử dụng machine learning để phát hiện spending bất thường so với pattern trước đó. Có thể tạo monitor theo AWS services, linked accounts, cost allocation tags hoặc Cost Categories theo loại monitor được hỗ trợ.

Một anomaly không nhất thiết là lỗi. Có thể là traffic tăng hợp lệ, campaign mới, data migration hoặc workload được mở rộng. Quy trình xử lý:

1. Nhận alert.
2. Xác định service, account, Region và cost category liên quan.
3. Mở Cost Explorer hoặc CUR để tìm usage type/resource.
4. So sánh deployment/change events.
5. Xác nhận với owner.
6. Ghi nguyên nhân và hành động.
7. Theo dõi đến khi cost trở về baseline hoặc được phê duyệt.

### 16.3 Billing alerts

Billing preferences cho phép cấu hình các cảnh báo như Free Tier usage alerts và CloudWatch billing alerts. Billing alerts nên bổ sung cho Budgets và Anomaly Detection, không thay thế các monitor theo product/team.

## 17. AWS Billing Conductor cho showback và chargeback

AWS Billing Conductor giúp tạo pro forma billing data bằng cách áp dụng pricing plans, pricing rules và custom line items lên billing groups.

Một số khái niệm:

| Thành phần | Vai trò |
|---|---|
| Billing group | Tập hợp accounts có chung customer hoặc billing view |
| Pricing plan | Bộ quy tắc giá áp dụng cho billing group |
| Pricing rule | Markup, discount hoặc custom pricing theo cấu hình |
| Custom line item | Dòng phí hoặc credit bổ sung trong pro forma bill |
| Pro forma bill | Dữ liệu billing tính theo cấu hình nội bộ |
| Standard bill | Billable charges làm cơ sở phát hành invoice AWS |

### 17.1 Pro forma không phải invoice AWS

Pro forma billing data là một phiên bản billing thay thế, được tạo từ cấu hình Billing Conductor. Nó có thể phục vụ showback/chargeback hoặc phân phối dữ liệu cho end customers.

Pro forma data không thay đổi standard AWS bill và không thay đổi số tiền AWS thu từ payer account. Cần giữ hai miền dữ liệu tách biệt:

- Standard bill: chi phí thực tế phải trả AWS.
- Pro forma bill: giá trị được tính theo pricing plan nội bộ.

### 17.2 Pricing plans

AWS có managed pricing plans như:

- BasicPricingPlan: tính pro forma costs theo base rates, loại trừ một số non-public discounts, credits, taxes và support charges.
- Passthrough: chuyển dữ liệu billable để phản ánh AWS invoice; chỉ áp dụng cho Billing Transfer billing groups.

Customer-managed pricing plans cho phép tạo pricing rules riêng. Một pricing plan có thể dùng cho nhiều billing groups. Khi thay đổi plan, dữ liệu của billing period hiện tại có thể được cập nhật; hãy kiểm tra tác động đến báo cáo và CUR configuration.

### 17.3 Billing groups

Khi dùng Billing Conductor độc lập, billing group là tập hợp accounts trong một consolidated billing family có cùng end customer. Trong pro forma domain, usage được tính như một billing family riêng cho nhóm; RI/SP và volume tiers được tính theo phạm vi group theo quy tắc của dịch vụ.

Khi dùng Billing Transfer, billing group ánh xạ một-một với Organization chuyển bill. Không thay đổi cách tính RI/SP và volume discounts của Organization đó.

### 17.4 Những gì có thể không xuất hiện trong pro forma

Tùy cấu hình và loại billing group, pro forma data có thể không bao gồm đầy đủ:

- Credits.
- Free Tier credits.
- Support plan charges.
- Non-public discounts.
- Usage-based bundled discounts.
- Taxes.
- Refunds.

Do đó, margin nội bộ tính từ pro forma có thể thay đổi và thậm chí âm. Nếu cần đối soát với invoice, phải xác định rõ các khoản bị loại trừ và cách bổ sung chúng.

### 17.5 Khi nào nên dùng Billing Conductor?

- Nhà cung cấp dịch vụ muốn tạo billing view cho nhiều khách hàng.
- Platform team muốn áp dụng internal markup hoặc platform fee.
- Doanh nghiệp cần pro forma showback cho từng business unit.
- Billing Transfer cần cung cấp cost view tùy chỉnh cho bill-source organizations.

Nếu chỉ cần báo cáo chi phí theo account, tag và service, Cost Explorer, Cost Categories và CUR có thể đã đủ. Không nên thêm Billing Conductor khi chưa có yêu cầu pricing/showback riêng.

## 18. Phân biệt consolidated billing, Cost Categories và Billing Conductor

| Công cụ | Giải quyết vấn đề | Có thay đổi invoice AWS không? |
|---|---|---|
| AWS Organizations consolidated billing | Gộp payment và usage của member accounts | Có, management account nhận consolidated bill |
| RI/SP discount sharing | Phân bổ commitment benefits giữa accounts đủ điều kiện | Có ảnh hưởng billable cost |
| Cost allocation tags | Gắn metadata vào resource costs | Không |
| Cost Categories | Phân nhóm cost line items theo rules | Không |
| Cost Category split charges | Hiển thị phân bổ shared costs giữa category values | Không; split view chỉ xuất hiện ở Cost Categories details |
| AWS Billing Conductor | Tạo pro forma pricing và custom line items | Không; standard bill không thay đổi |
| Billing Transfer | Chuyển trách nhiệm quản lý/thanh toán consolidated bill giữa Organizations | Thay đổi account chịu trách nhiệm thanh toán, không gộp discount boundaries |

Đây là những lớp có thể kết hợp nhưng không thay thế nhau. Một Organization có thể dùng consolidated billing, tags, Cost Categories, CUR và Budgets cùng lúc. Billing Conductor chỉ cần thiết khi có yêu cầu pro forma pricing hoặc billing transfer integration.

## 19. Quyền truy cập và bảo mật billing data

Billing data là dữ liệu tài chính nhạy cảm. Nên phân quyền theo vai trò:

| Vai trò | Quyền phù hợp |
|---|---|
| Finance approver | Xem invoice, payment, credits và billing reports |
| FinOps analyst | Cost Explorer, Budgets, Cost Categories, CUR |
| Platform engineer | Xem chi phí account/workload phụ trách, không cần quyền payment |
| Billing administrator | Quản lý billing preferences, exports và cấu hình billing |
| Auditor | Read-only access và lịch sử thay đổi |

Các nguyên tắc:

- Dùng IAM Identity Center và role-based access.
- Cấp quyền Billing and Cost Management fine-grained actions thay vì quyền rộng không cần thiết.
- Tách quyền đọc dữ liệu cost khỏi quyền thay đổi payment methods.
- Giới hạn quyền sửa Cost Categories, Data Exports, billing groups và pricing plans.
- Bảo vệ management account và root user.
- Bảo vệ CUR S3 bucket bằng encryption và least privilege.
- Dùng CloudTrail để audit thay đổi billing preferences, Organizations và IAM.
- Rà soát access định kỳ và khi nhân sự chuyển vai trò.

Member account có thể được cấp quyền xem billing data của chính account đó. Quyền xem dữ liệu của toàn Organization cần được kiểm soát từ management account và các cơ chế Cost Explorer/Billing access tương ứng.

## 20. Quy trình quản trị Billing hàng tháng

Một chu kỳ FinOps có thể gồm:

### Trong tháng

- Theo dõi Cost Explorer và Budgets.
- Nhận Cost Anomaly Detection alerts.
- Kiểm tra tag coverage và unallocated costs.
- Theo dõi RI/SP utilization và coverage.
- Xác nhận owner cho các cost spikes.
- Cập nhật forecast theo release, campaign hoặc migration.

### Cuối tháng

- Chốt billing period và invoice.
- Đối chiếu Bills với Cost Explorer và CUR.
- Kiểm tra credits, refunds, taxes và Marketplace charges.
- Chạy Cost Categories và shared cost allocation.
- Xuất báo cáo theo account, cost center, product và application.
- Phát hành showback/chargeback.
- Ghi nhận variance so với budget.

### Sau đối soát

- Xác nhận khoản tăng/giảm với service owners.
- Tạo action items cho resource optimization.
- Cập nhật budget/forecast nếu workload đã thay đổi.
- Lưu snapshot báo cáo, query, rule version và approval.
- Theo dõi việc thực hiện action items ở kỳ tiếp theo.

## 21. Ví dụ kiến trúc FinOps cho doanh nghiệp nhiều sản phẩm

Một doanh nghiệp có ba product accounts, một shared infrastructure account và một management account.

- Management account thanh toán consolidated bill.
- Product accounts gắn tags Application, Environment, CostCenter và Owner.
- Shared infrastructure account chứa Transit Gateway, NAT, logging và monitoring.
- Cost Category phân nhóm Product A, Product B, Product C và Shared Platform.
- Split charge rules phân bổ shared platform theo tỷ trọng traffic hoặc tỷ lệ cố định.
- CUR 2.0 export vào S3.
- Athena tính direct cost theo account/tag và kết hợp bảng split allocation nội bộ.
- QuickSight hiển thị dashboard theo business unit.
- AWS Budgets và Cost Anomaly Detection gửi cảnh báo đến owners.

~~~mermaid
flowchart TD
    A["AWS Organizations"] --> B["Management account / consolidated bill"]
    A --> C["Product accounts"]
    A --> D["Shared infrastructure account"]
    C --> E["Resource tags"]
    D --> E
    B --> F["Cost Categories"]
    E --> F
    B --> G["CUR 2.0 Data Export"]
    F --> G
    G --> H["S3 + Athena"]
    H --> I["FinOps data model"]
    I --> J["Showback / Chargeback dashboard"]
    B --> K["Budgets / Anomaly Detection"]
    K --> L["Owner alerts"]
~~~

Điểm quan trọng là shared cost allocation phải có công thức và owner. Ví dụ, NAT Gateway có thể phân bổ theo GB processed; logging platform có thể phân bổ theo ingest volume; security platform có thể phân bổ theo số accounts hoặc workloads. Chọn driver gần với mức tiêu thụ thực tế nhất có thể.

## 22. Lab: tạo cost allocation report cho một Organization

Lab dùng tài khoản sandbox hoặc môi trường AWS đã được cấp quyền billing phù hợp. Không thực hiện thay đổi billing preferences trên Organization production nếu chưa có approval.

### Bước 1: xác định account structure

Chọn management account và ít nhất hai member accounts đại diện cho hai products. Ghi lại account IDs và owner.

### Bước 2: thống nhất tag taxonomy

Áp dụng các keys:

- CostCenter
- Application
- Environment
- Owner

Ví dụ cho một resource production:

~~~yaml
CostCenter: CC-ENG-001
Application: storefront
Environment: prod
Owner: team-commerce
~~~

Đảm bảo các tag values tuân theo danh mục được Finance và Platform team phê duyệt.

### Bước 3: kích hoạt cost allocation tags

Trong management account:

1. Mở Billing and Cost Management.
2. Chọn Cost allocation tags.
3. Chọn các user-defined tag keys.
4. Activate keys cần thiết.
5. Chờ dữ liệu xuất hiện và xác minh trong Cost Explorer.

Nếu tag key chưa xuất hiện ngay, kiểm tra resource/service có hỗ trợ tagging và chờ thời gian cập nhật billing data.

### Bước 4: tạo Cost Category

Tạo Cost Category tên BusinessUnit hoặc Product. Dùng linked account để nhóm Product A và Product B. Thêm default value Unallocated cho costs chưa khớp rule.

Nếu có shared platform, tạo value SharedPlatform để phân loại trước khi xây split charge rule.

### Bước 5: tạo CUR 2.0 export

Trong Billing and Cost Management:

1. Chọn Data Exports.
2. Tạo Standard data export.
3. Chọn Cost and Usage Report 2.0.
4. Chọn các columns cần phân tích, bao gồm resource IDs nếu cần.
5. Chọn S3 destination.
6. Cấu hình encryption và bucket policy.
7. Tạo export và chờ AWS bắt đầu delivery.

### Bước 6: phân tích trong Cost Explorer

Tạo report:

- Group by Linked account.
- Filter theo service.
- Group by Cost allocation tag Application.
- Chọn Amortized Cost để đánh giá commitment.
- So sánh tháng hiện tại với cùng khoảng thời gian tháng trước.

### Bước 7: tạo budget và anomaly monitor

Tạo budget cho từng Product hoặc Cost Category. Thiết lập actual/forecast thresholds. Tạo Cost Anomaly Detection monitor phù hợp và subscription gửi alert đến owner.

### Bước 8: tạo showback report

Tổng hợp direct costs, shared costs, discounts và unallocated costs. Nếu dùng split charge rules, xác nhận số liệu trong Cost Categories details page. Đối chiếu tổng allocation với consolidated bill.

### Bước 9: cleanup

Xóa test budgets, anomaly subscriptions, Cost Categories hoặc Data Exports không còn cần. Không xóa bucket CUR production nếu đang được hệ thống tài chính sử dụng. Lưu lại cấu hình và quyền sở hữu báo cáo.

## 23. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Member account không thấy consolidated bill | Đang xem account view thay vì management account | Đăng nhập đúng management account và kiểm tra billing permissions |
| Management account không thấy account mới | Invitation chưa được chấp nhận hoặc account chưa thuộc Organization | Kiểm tra Organizations membership và thời điểm gia nhập |
| Volume discount không như dự kiến | Service không có tier phù hợp hoặc usage dimension khác nhau | Kiểm tra pricing dimension và consolidated usage |
| RI/SP không được chia sẻ | Discount sharing bị tắt hoặc usage không tương thích | Kiểm tra owner account, sharing preference, Region/scope và instance family |
| Cost allocation tag không xuất hiện | Chưa activate, resource không hỗ trợ hoặc chưa đủ thời gian | Kiểm tra tag key, service support và thời gian cập nhật |
| Tag xuất hiện trong resource nhưng không có trong CUR | Tag chưa được kích hoạt cho billing hoặc resource không được metered/taggable | Activate key và xác minh cost allocation report |
| Cost Category gán sai value | Rule order hoặc điều kiện overlap | Đưa rule cụ thể lên trước, kiểm tra preview và Applied status |
| Shared cost không được split | Source value chưa được categorize hoặc rule không hợp lệ | Kiểm tra source/targets, method và category status |
| Split charge không thấy trong CUR | Split allocation chỉ xuất hiện ở Cost Categories details | Dùng details page hoặc tái tạo allocation trong pipeline nội bộ |
| CUR 2.0 chưa có file | Export mới tạo hoặc S3 delivery chưa bắt đầu | Chờ tối đa thời gian khởi tạo và kiểm tra bucket policy |
| Athena query lỗi column not found | Tên nested key hoặc schema khác | Kiểm tra CUR 2.0 table dictionary và Data Export configuration |
| Cost Explorer khác invoice | Khác cash/amortized view, refresh, grouping, refunds hoặc rounding | Đối chiếu đúng cost metric và dùng invoice cuối kỳ làm nguồn thanh toán |
| Pro forma khác standard bill | Pricing plan, excluded credits/tax/support hoặc custom line items | So sánh billing domains và quy tắc Billing Conductor |
| Billing Transfer làm CUR unhealthy | CUR config cũ không còn hiệu lực sau chuyển | Tạo lại Data Exports/CUR theo billing view mới |
| Bill-source account không có Cost Anomaly alerts | Cost Anomaly Detection không hỗ trợ bill-source usage trong Billing Transfer | Dùng monitor phù hợp ở bill-transfer scope và các công cụ bổ sung |
| Chi phí chưa có owner tăng | Thiếu tags, account mapping hoặc default Cost Category | Báo cáo Unallocated và yêu cầu owner bổ sung metadata |

## 24. Best practices cho Billing và FinOps

### Account và Organization

- Dùng management account chỉ cho quản trị Organization và billing.
- Tách workload theo product, environment hoặc security boundary có ý nghĩa.
- Giữ account owner và cost owner rõ ràng.
- Dùng consolidated billing để quản lý payment và gộp usage trong Organization.
- Đánh giá Billing Transfer khi cần tập trung nhiều Organizations.
- Không giả định Billing Transfer gộp RI/SP discount boundaries giữa Organizations.

### Discount và commitment

- Theo dõi RI/SP utilization và coverage.
- Bắt đầu với open sharing nếu mục tiêu là tối đa hóa discount toàn Organization.
- Dùng group sharing khi có yêu cầu phân tách discount theo business unit.
- Mô phỏng tác động trước khi thay đổi sharing preferences.
- Quản lý credit sharing riêng với RI/SP discount sharing.
- Phân bổ discount theo một chính sách nội bộ nhất quán.

### Cost allocation

- Chuẩn hóa tags trước khi scale số accounts.
- Kết hợp account dimensions, resource tags, account tags và Cost Categories.
- Kích hoạt tag keys cần thiết trong Billing console.
- Có default Unallocated value và theo dõi coverage.
- Dùng Cost Categories cho business mapping và shared cost grouping.
- Ghi rõ công thức split charge và owner của shared services.
- Không dùng Cost Category split charge như nguồn CUR thay thế vì split view không được ghi vào CUR/Cost Explorer.

### Data và reporting

- Dùng Bills để đối soát invoice.
- Dùng Cost Explorer để phân tích và forecast.
- Dùng CUR 2.0/Data Exports cho dữ liệu chi tiết và data pipeline.
- Bảo vệ CUR S3 bucket bằng encryption, IAM và retention.
- Lưu query và dashboard trong version control.
- Ghi lại metric type: Unblended, Net Unblended, Amortized hoặc Net Amortized.
- Tránh so sánh các báo cáo có billing period, granularity hoặc cost basis khác nhau.

### Governance

- Tách quyền đọc cost và quyền thanh toán.
- Dùng Budgets, Cost Anomaly Detection và owner alerts.
- Có quy trình review monthly variance.
- Lưu bằng chứng đối soát và approval.
- Kiểm tra tag coverage, unallocated cost và shared cost allocation hàng tháng.
- Thực hiện review định kỳ với Engineering, Product, Finance và Procurement.

## 25. Bài tập tự luyện

1. Consolidated billing trong AWS Organizations là gì?
2. Management account và member account khác nhau như thế nào?
3. Consolidated billing có biến nhiều AWS accounts thành một account không?
4. Vì sao consolidated billing có thể giúp volume discounts tốt hơn?
5. RI và Savings Plans sharing phụ thuộc những điều kiện nào?
6. Open sharing, prioritized group sharing và restricted group sharing khác nhau ra sao?
7. Vì sao credits sharing phải được xem xét riêng?
8. Account tham gia Organization giữa tháng thì charges trước và sau thời điểm gia nhập được xử lý thế nào?
9. Billing Transfer khác consolidated billing ra sao?
10. Billing Transfer có gộp RI/SP discounts giữa hai Organizations không?
11. Showback và chargeback khác nhau thế nào?
12. Vì sao gắn resource tags chưa đủ để xuất hiện trong cost reports?
13. Cost allocation tag cần được activate ở đâu?
14. Account tags bổ sung giá trị gì cho resource tags?
15. Cost Categories có thể group costs theo những dimension nào?
16. Vì sao thứ tự Cost Category rules quan trọng?
17. Proportional, fixed và even split khác nhau thế nào?
18. Vì sao split charge không xuất hiện trong CUR?
19. Bills và Cost Explorer khác nhau về cash basis/amortized basis ra sao?
20. CUR 2.0 được dùng cho mục đích gì?
21. Data Exports có thể mất bao lâu để bắt đầu delivery?
22. Vì sao CUR bucket cần encryption và least privilege?
23. AWS Billing Conductor pro forma có thay đổi invoice AWS không?
24. Khi nào nên dùng Billing Conductor?
25. Nếu Cost Explorer khác invoice cuối tháng, nguồn nào dùng để thanh toán?

### Gợi ý đáp án

1. Cơ chế AWS Organizations gom billing và payment của nhiều accounts về management account.
2. Management account sở hữu Organization và trả consolidated bill; member account chứa workload và có billing riêng trong phạm vi account.
3. Không. Mỗi account vẫn là ranh giới tài nguyên, IAM và bảo mật riêng.
4. AWS kết hợp usage của các accounts để tính volume pricing tiers.
5. Account mua commitment phải đủ điều kiện sharing; usage nhận benefit phải phù hợp scope, Region và dịch vụ.
6. Open chia sẻ cho tất cả accounts bật sharing; prioritized ưu tiên nhóm; restricted chỉ chia sẻ trong nhóm.
7. Vì credit sharing có preference riêng với RI/SP discount sharing.
8. Management account chịu charges từ thời điểm account chấp nhận gia nhập; chủ sở hữu cũ chịu phần trước đó.
9. Consolidated billing gom accounts trong một Organization; Billing Transfer chuyển trách nhiệm quản lý/thanh toán consolidated bill giữa management accounts của nhiều Organizations.
10. Không. Discount computation boundary vẫn là từng Organization.
11. Showback cung cấp visibility; chargeback phân bổ chi phí vào cost center hoặc sổ cái nội bộ.
12. Vì tag key phải được activate trong Billing and Cost Management và cần thời gian cập nhật.
13. Cost allocation tags trong Billing and Cost Management console hoặc API.
14. Account tags giúp phân bổ costs không gắn được resource tags, gồm một số credits/refunds/service charges.
15. Account, tag, charge type, service, Region, usage type, billing entity và các category dimensions được hỗ trợ.
16. Rules được đánh giá top-down; rule đầu tiên khớp quyết định category value.
17. Proportional theo tỷ trọng chi phí target, fixed theo phần trăm định nghĩa, even chia đều.
18. Split charge chỉ hiển thị ở Cost Categories details page và không thay đổi CUR/Cost Explorer.
19. Bills là cash basis và phản ánh số tiền phải trả; Cost Explorer có thể amortize commitment theo thời gian.
20. CUR 2.0 cung cấp cost/usage details để truy vấn và tích hợp hệ thống phân tích.
21. Có thể mất tới 24 giờ để bắt đầu delivery; sau đó refresh ít nhất hằng ngày.
22. Vì CUR chứa dữ liệu chi phí, account, resource và tag có thể nhạy cảm.
23. Không. Pro forma là billing view mô phỏng; standard AWS bill không thay đổi.
24. Khi cần internal pricing, markup, custom line items, billing groups hoặc showback/chargeback qua billing transfer.
25. Invoice AWS cuối cùng là căn cứ thanh toán.

## 26. Câu hỏi phỏng vấn

### Vì sao nên dùng nhiều AWS accounts thay vì chỉ một account lớn?

Nhiều accounts giúp cô lập security boundary, quota, môi trường, ownership và billing dimensions. Consolidated billing vẫn cho phép tổng hợp payment và usage trong Organization.

### Consolidated billing có tự động phân bổ discount cho đúng product owner không?

Không theo mô hình quản trị nội bộ mong muốn. AWS áp dụng discount theo billing rules và sharing preferences. Doanh nghiệp vẫn cần chính sách phân bổ discount và báo cáo theo account/tag/category.

### Khi nào nên dùng Cost Categories thay cho resource tags?

Dùng tags khi cần metadata gắn trực tiếp vào resource. Dùng Cost Categories khi cần phân nhóm line items theo account, service, usage type, charge type hoặc nhiều dimensions kết hợp, và khi cần ánh xạ sang business structure.

### Vì sao cần cả Cost Categories và CUR 2.0?

Cost Categories cung cấp business mapping trong các công cụ Cost Management. CUR 2.0 cung cấp dòng cost/usage chi tiết để truy vấn, đối soát và tích hợp vào data warehouse. Chúng bổ sung cho nhau.

### Có thể dùng split charge để ghi nhận shared cost trong CUR không?

Không. Split charge allocation của Cost Categories hiển thị trên category details page và không làm thay đổi CUR hoặc Cost Explorer. Muốn đưa phép phân bổ vào sổ cái, cần triển khai logic nội bộ và lưu công thức.

### Billing Conductor khác Cost Categories thế nào?

Cost Categories phân loại line items, không thay đổi giá AWS. Billing Conductor tạo pro forma billing theo pricing plans, pricing rules và custom line items để hỗ trợ showback/chargeback. Pro forma không phải invoice AWS.

### Vì sao cần tách cash basis và amortized cost?

Cash basis phục vụ đối soát tiền AWS thu trong kỳ. Amortized basis phân bổ commitment cost theo thời gian để đánh giá economics của workload. Dùng nhầm basis sẽ dẫn đến kết luận sai về cost trend.

### Billing Transfer có phải là cách gộp discount nhiều Organizations không?

Không. Billing Transfer tập trung quản lý và thanh toán bills của nhiều Organizations. RI/SP và volume discounts vẫn được tính trong từng Organization riêng.

### Làm thế nào giảm unallocated costs?

Chuẩn hóa account structure và tag taxonomy, activate cost allocation tags, dùng account tags, tạo Cost Categories với default Unallocated và yêu cầu owners xử lý các dòng chi phí chưa có owner.

### Một dashboard chargeback đáng tin cậy cần có gì?

Nó cần direct cost, shared cost allocation, discount/credit policy, billing period, cost basis, owner, unallocated costs, nguồn dữ liệu và reconciliation với invoice.

## 27. Checklist production cho Billing và FinOps

### Organization và billing

- [ ] Management account được bảo vệ bằng MFA và root security controls.
- [ ] Workloads không chạy trong management account.
- [ ] Member accounts có owner và cost owner.
- [ ] Consolidated billing được cấu hình đúng.
- [ ] SOR và invoice routing đã được xác nhận.
- [ ] RI/SP discount sharing preference được review.
- [ ] Credit sharing preference được review riêng.
- [ ] Billing Transfer chỉ bật sau khi đánh giá dữ liệu lịch sử và discount boundaries.

### Cost allocation

- [ ] Account structure phản ánh product/environment/business boundaries.
- [ ] Tag taxonomy có owner và danh mục value.
- [ ] Tag keys được áp dụng lên resources hỗ trợ.
- [ ] Cost allocation tags đã được activate.
- [ ] Account tags được dùng cho các khoản không gắn resource tags.
- [ ] Cost Categories có rule order và default Unallocated.
- [ ] Shared costs có driver và allocation methodology.
- [ ] Discount allocation policy được ghi lại.

### Reporting và data

- [ ] Bills được dùng để đối soát invoice.
- [ ] Cost Explorer được cấu hình cho các owners.
- [ ] CUR 2.0/Data Exports được delivery vào S3.
- [ ] CUR bucket có encryption, IAM và lifecycle.
- [ ] Athena/QuickSight queries có version control.
- [ ] Cost basis và billing period được ghi trên dashboard.
- [ ] Billing Conductor pro forma được phân biệt với standard bill.

### Governance và FinOps operations

- [ ] AWS Budgets được cấu hình theo business unit/product.
- [ ] Cost Anomaly Detection monitors có owner.
- [ ] Alerts có escalation path.
- [ ] Finance và Engineering có monthly cost review.
- [ ] Unallocated costs được theo dõi.
- [ ] Chargeback totals được reconcile với invoice.
- [ ] Có audit trail cho billing preferences, cost categories và pricing plans.
- [ ] Quyền billing được rà soát định kỳ.

## 28. Tài liệu tham khảo chính thức

- [Consolidating billing for AWS Organizations](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/consolidated-billing.html)
- [Finding the seller of record](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/finding-the-seller-of-record.html)
- [Consolidated billing process](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/useconsolidatedbilling-procedure.html)
- [Effective billing date, account activity, and volume discounts](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/useconsolidatedbilling-effective.html)
- [Understanding consolidated bills](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/con-bill-blended-rates.html)
- [Customizing your Billing preferences](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/billing-pref.html)
- [Applying AWS credits](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/useconsolidatedbilling-credits.html)
- [Transfer billing management to external accounts](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/orgs_transfer_billing.html)
- [Organizing and tracking costs using AWS cost allocation tags](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/cost-alloc-tags.html)
- [Using user-defined cost allocation tags](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/custom-tags.html)
- [Activating user-defined cost allocation tags](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/activating-tags.html)
- [Using account tags for cost allocation](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/account-tags-cost-allocation.html)
- [Organizing costs using AWS Cost Categories](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/manage-cost-categories.html)
- [Creating cost categories](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/create-cost-categories.html)
- [Splitting charges within cost categories](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/splitcharge-cost-categories.html)
- [Knowing the differences between Billing and Cost Explorer data](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/differences-billing-data-cost-explorer-data.html)
- [Understanding your bill](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/getting-viewing-bill.html)
- [AWS Data Exports](https://docs.aws.amazon.com/cur/latest/userguide/)
- [Creating data exports](https://docs.aws.amazon.com/cur/latest/userguide/dataexports-create.html)
- [Migrating from CUR to Data Exports CUR 2.0](https://docs.aws.amazon.com/cur/latest/userguide/dataexports-migrate.html)
- [Understanding the Cost and Usage Report](https://docs.aws.amazon.com/cur/latest/userguide/dataexports-cur-info.html)
- [Cost and Usage Report 2.0 table dictionary](https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2.html)
- [Understanding export delivery](https://docs.aws.amazon.com/cur/latest/userguide/dataexports-export-delivery.html)
- [AWS Billing Conductor - Pro forma billing data](https://docs.aws.amazon.com/billingconductor/latest/userguide/understanding-proforma.html)
- [AWS Billing Conductor - Billing groups](https://docs.aws.amazon.com/billingconductor/latest/userguide/creating-abc.html)
- [AWS Billing Conductor - Pricing plans](https://docs.aws.amazon.com/billingconductor/latest/userguide/abc-pricingplan.html)
- [AWS Cost Explorer User Guide](https://docs.aws.amazon.com/cost-management/latest/userguide/what-is-costmanagement.html)
- [Creating a cost budget](https://docs.aws.amazon.com/cost-management/latest/userguide/create-cost-budget.html)
- [Getting started with AWS Cost Anomaly Detection](https://docs.aws.amazon.com/cost-management/latest/userguide/getting-started-ad.html)


