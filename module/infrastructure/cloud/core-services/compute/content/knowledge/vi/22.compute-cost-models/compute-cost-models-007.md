# Phân bổ chi phí bằng tag, owner và môi trường

Chi phí compute trên cloud thường phát sinh từ nhiều loại tài nguyên: VM, disk, snapshot, load balancer, IP, container node, Kubernetes workload, serverless function, network transfer và dịch vụ hỗ trợ. Một hóa đơn tổng theo account hoặc subscription cho biết tổ chức đã chi bao nhiêu, nhưng chưa trả lời được đội nào, sản phẩm nào hay môi trường nào tạo ra khoản chi đó.

Phân bổ chi phí giúp liên kết từng khoản sử dụng với **dịch vụ, owner, team, cost center và môi trường**. Tag hoặc label cung cấp metadata để nhận diện tài nguyên; owner xác định trách nhiệm quản lý; environment phân biệt production, staging, development và sandbox. Khi taxonomy được chuẩn hóa, tự động gắn vào tài nguyên và đối chiếu với dữ liệu billing, tổ chức có thể thực hiện showback, chargeback, lập ngân sách và tìm cơ hội tối ưu có trách nhiệm.

## 1. Vì sao cần phân bổ chi phí compute?

Cloud cho phép nhiều nhóm tự tạo tài nguyên theo nhu cầu. Tốc độ cấp phát nhanh cũng khiến chi phí tăng nhanh nếu không có thông tin ownership và môi trường. Một VM có thể được tạo bởi pipeline, một nhóm khác có thể gắn thêm disk hoặc snapshot, còn network egress xuất hiện ở hóa đơn cấp project. Nếu thiếu metadata, bộ phận tài chính khó xác định ai cần giải thích hoặc tối ưu khoản chi.

Phân bổ chi phí hỗ trợ:

- **Accountability:** xác định team hoặc owner chịu trách nhiệm cho tài nguyên và mức sử dụng.
- **Budgeting:** lập ngân sách theo sản phẩm, team, cost center và environment.
- **Showback:** cung cấp báo cáo chi phí cho nhóm sử dụng để họ nhìn thấy mức tiêu thụ.
- **Chargeback:** chuyển chi phí nội bộ tới cost center hoặc đơn vị chịu ngân sách theo quy tắc đã thống nhất.
- **Optimization:** tìm VM nhàn rỗi, disk mồ côi, môi trường test tồn tại ngoài giờ hoặc workload có chi phí tăng bất thường.
- **Forecasting:** dự báo chi phí theo kế hoạch phát hành, tăng trưởng người dùng và thay đổi capacity.
- **Governance:** phát hiện tài nguyên thiếu owner, thiếu environment hoặc không tuân thủ chính sách.

Tagging không tự làm giảm chi phí. Nó tạo dữ liệu đáng tin cậy để tổ chức biết chi phí thuộc về đâu và ai có thể hành động. Quy trình phân bổ chỉ có giá trị khi tag chính xác, được duy trì theo vòng đời tài nguyên và được đối chiếu với hóa đơn thực tế.

## 2. Phân biệt tag, label, owner và cost center

Các cloud provider thường dùng thuật ngữ tag hoặc label cho cặp key-value gắn vào tài nguyên. Cách hỗ trợ và giới hạn khác nhau theo dịch vụ, nhưng mục đích chung là cung cấp metadata có cấu trúc.

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| Tag/label | Metadata phân loại tài nguyên | `environment=production` |
| Owner | Team hoặc vai trò chịu trách nhiệm vận hành | `owner=team-checkout` |
| Cost center | Đơn vị ngân sách nhận chi phí | `cost-center=CC-4102` |
| Service/application | Sản phẩm hoặc dịch vụ tạo ra mức sử dụng | `service=order-api` |
| Environment | Mục đích và mức độ quan trọng của môi trường | `environment=staging` |
| Project/workload | Dự án hoặc workload cụ thể | `project=customer-portal` |
| Business unit | Đơn vị kinh doanh sở hữu dịch vụ | `business-unit=commerce` |

Owner và cost center có liên quan nhưng không giống nhau. Owner trả lời ai vận hành và xử lý sự cố; cost center trả lời chi phí được ghi nhận vào ngân sách nào. Một team có thể quản lý nhiều cost center, và một cost center có thể nhận chi phí từ nhiều team theo quy tắc tổ chức.

Environment cũng không phải owner. Một tài nguyên `production` vẫn cần owner cụ thể; một team có thể quản lý cả production và development. Không nên dùng một tag chung như `department` để thay thế tất cả các chiều phân loại.

### Tag khác với tên tài nguyên

Tên tài nguyên hữu ích cho người đọc nhưng không phải nguồn dữ liệu phân bổ đáng tin cậy. Tên có thể thay đổi, bị cắt ngắn hoặc không theo quy ước. Tag có cấu trúc cho phép hệ thống billing lọc và nhóm chi phí ổn định hơn. Có thể dùng cả hai: tên giúp nhận diện nhanh, tag phục vụ policy và báo cáo.

## 3. Xây dựng taxonomy tag tối thiểu

Taxonomy là bộ key, định nghĩa, giá trị được phép và quy tắc áp dụng. Một taxonomy tốt cần đủ nhỏ để nhóm sử dụng nhất quán, nhưng đủ thông tin để trả lời các câu hỏi phân bổ quan trọng.

Một bộ tag nền tảng có thể gồm:

| Key | Bắt buộc? | Mục đích | Giá trị ví dụ |
|---|---|---|---|
| `owner` | Có | Team hoặc nhóm chịu trách nhiệm | `team-platform` |
| `service` | Có | Dịch vụ hoặc ứng dụng | `checkout-api` |
| `environment` | Có | Môi trường chạy | `production`, `staging`, `development`, `sandbox` |
| `cost-center` | Có nếu chargeback | Mã đơn vị ngân sách | `CC-4102` |
| `business-unit` | Nên có | Đơn vị kinh doanh | `commerce` |
| `project` | Theo nhu cầu | Dự án hoặc chương trình | `checkout-modernization` |
| `managed-by` | Nên có | Hệ thống tạo/quản lý tài nguyên | `terraform`, `platform-team` |
| `lifecycle` | Nên có | Vòng đời hoặc chính sách thu hồi | `permanent`, `ephemeral` |
| `data-classification` | Theo chính sách | Mức phân loại dữ liệu | `internal`, `confidential` |

Đây là bộ ví dụ để thiết kế, không phải bộ key chuẩn của mọi provider. Hãy chọn một tên key duy nhất cho mỗi khái niệm và công bố định nghĩa chính thức. Nếu cùng lúc xuất hiện `team`, `owner-team`, `application-owner` và `support-group` với ý nghĩa gần nhau, báo cáo sẽ khó tổng hợp và người dùng không biết phải điền trường nào.

### Định nghĩa từng tag

Với mỗi key, tài liệu taxonomy cần nêu:

- Tên key chính thức và cách viết hoa/thường.
- Mô tả ý nghĩa và câu hỏi mà tag trả lời.
- Có bắt buộc không và áp dụng cho loại tài nguyên nào.
- Giá trị hợp lệ, định dạng và quy tắc đặt tên.
- Nguồn dữ liệu chuẩn, ví dụ danh mục team hoặc cost center.
- Owner chịu trách nhiệm cập nhật.
- Hành vi khi thiếu, sai hoặc hết hiệu lực.
- Có được phép thay đổi sau khi tạo tài nguyên không.

Ví dụ, `owner` nên dùng mã team ổn định thay vì tên cá nhân. Nhân sự có thể chuyển nhóm hoặc nghỉ việc; team alias hoặc group ID thường duy trì lâu hơn và có thể ánh xạ tới contact hiện hành trong hệ thống quản lý danh tính.

### Giá trị có kiểm soát

Giá trị nên được chọn từ danh mục thay vì nhập tự do. Ví dụ environment chỉ nhận các giá trị đã định nghĩa; cost center phải khớp mã ngân sách; owner phải tồn tại trong danh mục team. Có thể giữ thêm tag `owner-contact` cho thông tin liên hệ, nhưng tránh đưa email cá nhân làm khóa phân bổ dài hạn nếu tổ chức có thể dùng team alias.

## 4. Quy ước tag và chuẩn hóa dữ liệu

Tag key/value cần nhất quán để tránh cùng một nhóm bị chia thành nhiều nhóm báo cáo.

### Chuẩn hóa cách viết

Ví dụ quy ước:

- Dùng chữ thường và dấu gạch ngang cho key: `cost-center`, `business-unit`.
- Dùng mã ổn định cho cost center: `CC-4102`.
- Dùng slug team/service không dấu cách: `team-platform`, `order-api`.
- Chỉ định rõ environment: `production`, `staging`, `development`, `sandbox`.
- Không thay đổi nghĩa của key sau khi đã dùng trong báo cáo.
- Không dùng nhiều giá trị tương đương như `prod`, `prd`, `production` nếu chưa có quy tắc mapping.

### Tránh đưa dữ liệu nhạy cảm vào tag

Tag có thể xuất hiện trong billing export, log, inventory, console hoặc API. Không đưa password, token, secret, thông tin cá nhân nhạy cảm, dữ liệu khách hàng hoặc nội dung nghiệp vụ bí mật vào tag. Dùng mã phân loại không nhạy cảm và tra cứu thông tin chi tiết trong hệ thống có kiểm soát quyền.

### Giới hạn của provider

Mỗi dịch vụ cloud có thể giới hạn số lượng tag, độ dài key/value, ký tự được phép hoặc khả năng gắn tag ở cấp tài nguyên con. Một số chi phí như network transfer, support plan hoặc shared service không có tag ở đúng dòng billing. Thiết kế taxonomy cần tính đến giới hạn này và dùng mapping hoặc allocation rule cho phần chi phí không thể gắn tag trực tiếp.

## 5. Owner: xác định người chịu trách nhiệm

Owner là thuộc tính quan trọng nhất để biến báo cáo chi phí thành hành động. Nếu báo cáo chỉ nói `production compute: 20.000 USD` mà không chỉ ra team quản lý, tổ chức khó xác định ai có thể resize, stop, rightsize hoặc giải thích tăng trưởng.

### Chọn owner theo team hoặc service owner

Ưu tiên định danh ổn định như team ID, service team hoặc nhóm vận hành. Tài nguyên dùng chung có thể có owner là platform team, còn phần chi phí được phân bổ tiếp cho consumer theo metric sử dụng.

Một owner cần có:

- Nhóm chịu trách nhiệm kỹ thuật.
- Kênh liên hệ hoặc on-call phù hợp.
- Người chịu trách nhiệm ngân sách hoặc product owner nếu khác nhau.
- Quyền thực hiện hành động tối ưu hoặc đề xuất thay đổi.
- Quy trình bàn giao owner khi team/service thay đổi.

### Phân biệt owner kỹ thuật và budget owner

Trong tổ chức lớn, người quản lý hệ thống không nhất thiết là người duyệt ngân sách. Có thể cần hai trường riêng:

- `owner`: team chịu trách nhiệm vận hành.
- `budget-owner` hoặc `cost-center`: đơn vị chịu trách nhiệm ngân sách.

Không ép một tag `owner` gánh cả trách nhiệm kỹ thuật, tài chính và phê duyệt. Điều đó khiến báo cáo khó sử dụng khi vai trò tách biệt.

### Tài nguyên dùng chung

Load balancer dùng chung, cluster Kubernetes, NAT gateway, logging platform hoặc shared database có thể do platform team quản lý. Gắn owner là `team-platform` giúp xác định người vận hành, nhưng chưa giải thích team sản phẩm nào tạo ra chi phí. Cần có quy tắc phân bổ tiếp theo dựa trên usage, capacity reservation hoặc tỷ lệ đã thống nhất.

## 6. Environment: phân biệt production và non-production

Tag environment giúp so sánh chi phí theo mức độ quan trọng và mục đích sử dụng. Các môi trường thường gặp:

| Environment | Mục đích | Quy tắc chi phí thường áp dụng |
|---|---|---|
| `production` | Phục vụ người dùng hoặc workload thật | Ưu tiên availability, bảo mật và capacity phù hợp SLO |
| `staging` | Kiểm thử trước phát hành | Giới hạn quy mô, lịch bật/tắt và dữ liệu phù hợp |
| `development` | Phát triển tính năng | Tài nguyên nhỏ, có thể tự động dọn khi hết hạn |
| `test` | Kiểm thử tự động hoặc thủ công | Tạo theo nhu cầu, thu hồi sau test |
| `sandbox` | Thử nghiệm độc lập | Budget nhỏ, quota và TTL nghiêm ngặt |
| `shared` | Dịch vụ dùng chung nhiều môi trường | Có allocation rule riêng, không gán nhầm thành production |

Không dùng tag environment để quyết định bảo mật duy nhất. Production cần được bảo vệ bằng IAM, network policy, secret management và deployment control thực sự; tag chỉ là metadata để phân loại và hỗ trợ policy.

### Tách chi phí theo environment

Báo cáo nên cho thấy cả tổng chi phí và tỷ trọng từng environment. Ví dụ, development tăng 40% trong khi production ổn định có thể là dấu hiệu sandbox không được dọn hoặc pipeline tạo môi trường tạm quá nhiều. Production tăng do traffic thực có thể là tăng trưởng hợp lý, nhưng vẫn cần so sánh chi phí trên mỗi request hoặc mỗi người dùng.

### Tài nguyên không có environment rõ ràng

Một số tài nguyên quản trị hoặc shared platform không thuộc riêng production/development. Dùng giá trị như `shared` hoặc `platform` theo taxonomy, kèm service/owner cụ thể. Không để trống environment chỉ vì tài nguyên dùng chung.

## 7. Gắn tag tại thời điểm tạo tài nguyên

Gắn tag khi provision là cách hiệu quả nhất để hạn chế tài nguyên không rõ owner. Nếu chỉ bổ sung tag sau khi tạo, tài nguyên có thể phát sinh chi phí trong nhiều ngày mà chưa được phân bổ.

### Infrastructure as Code

Template hoặc module dùng chung nên nhận các trường owner, service, environment và cost center như input bắt buộc. Các tag nền tảng có thể được hợp nhất với tag riêng của workload.

Ví dụ cấu hình khái niệm:

```hcl
variable "owner" {
  type        = string
  description = "Team responsible for this workload"
}

variable "service" {
  type        = string
  description = "Application or service identifier"
}

variable "environment" {
  type        = string
  description = "Deployment environment"
}

variable "cost_center" {
  type        = string
  description = "Approved finance cost center"
}

locals {
  allocation_tags = {
    owner        = var.owner
    service      = var.service
    environment  = var.environment
    cost-center  = var.cost_center
    managed-by   = "terraform"
  }
}
```

Đây là ví dụ minh họa cho module IaC, không phải cấu hình đầy đủ của một provider. Module thực tế cần áp dụng tag vào từng loại resource và xác minh tên thuộc tính theo provider đang dùng.

### Tag mặc định và tag do workload khai báo

Có thể chia tag thành hai nhóm:

- Tag nền tảng: `managed-by`, `environment`, `owner`, `service`, `cost-center` được pipeline yêu cầu.
- Tag workload: `project`, `component`, `data-classification`, `expiry-date` hoặc metadata đặc thù.

Pipeline nên kiểm tra tag bắt buộc trước khi tạo tài nguyên. Nếu không có thông tin hợp lệ, dừng provisioning hoặc yêu cầu người tạo bổ sung. Với tài nguyên khẩn cấp, có thể dùng owner tạm thời theo quy trình exception có thời hạn và người phê duyệt.

### Kế thừa tag

Một số nền tảng hỗ trợ kế thừa tag từ project, resource group, subscription, folder hoặc organization; một số loại resource không tự kế thừa. Không giả định tag ở parent luôn xuất hiện trong billing line của child. Kiểm tra hành vi theo từng dịch vụ và xác nhận bằng billing export.

## 8. Enforce và kiểm tra tuân thủ tag

Taxonomy chỉ có tác dụng khi có cơ chế ngăn giá trị sai hoặc phát hiện tài nguyên thiếu tag.

### Các lớp kiểm soát

1. **Design-time:** module IaC và template yêu cầu tag.
2. **CI validation:** pipeline kiểm tra key, value, cost center và environment trước khi apply.
3. **Admission/provisioning policy:** policy engine chặn hoặc cảnh báo resource thiếu tag.
4. **Runtime inventory scan:** quét tài nguyên hiện có và phát hiện thiếu/sai tag.
5. **Billing reconciliation:** kiểm tra coverage trên dữ liệu chi phí, bao gồm tài nguyên không hỗ trợ tag.

### Chặn hay cảnh báo?

Với tag bắt buộc như owner và environment, có thể chặn tạo tài nguyên qua template chuẩn. Với tài nguyên legacy hoặc dịch vụ không hỗ trợ tag, dùng cảnh báo và quy trình xử lý ngoại lệ. Không nên chặn toàn bộ provisioning chỉ vì một tag tùy chọn không có, nếu điều đó làm gián đoạn vận hành.

### Exception có thời hạn

Một exception nên có:

- Lý do không thể gắn tag chuẩn.
- Owner tạm thời và người phê duyệt.
- Thời điểm bắt đầu và ngày hết hạn.
- Cách phân bổ chi phí trong thời gian ngoại lệ.
- Hành động cần hoàn tất để trở về trạng thái chuẩn.

Exception không có expiry dễ trở thành cơ chế bỏ qua policy lâu dài.

## 9. Tag coverage: đo mức độ phân bổ được chi phí

Không chỉ đếm số tài nguyên đã gắn tag. Một VM nhỏ và một GPU cluster lớn có giá trị chi phí rất khác nhau. Nên đo coverage theo cả số lượng tài nguyên và tỷ trọng chi phí.

### Resource coverage

\[
\text{Resource coverage} =
\frac{\text{Số tài nguyên có đủ tag bắt buộc}}
{\text{Tổng số tài nguyên thuộc phạm vi}} \times 100\%
\]

### Cost coverage

\[
\text{Cost coverage} =
\frac{\text{Chi phí gắn được owner/service/environment}}
{\text{Tổng chi phí trong phạm vi}} \times 100\%
\]

Cost coverage thường phản ánh chất lượng phân bổ tốt hơn. Ví dụ, 95% VM có đủ tag nhưng 30% chi phí network và shared storage chưa được phân bổ thì báo cáo vẫn thiếu đáng kể.

### Untagged cost và unknown bucket

Giữ một nhóm `unallocated` hoặc `unknown` trong báo cáo để làm rõ phần chi phí chưa gán được. Không phân bổ tùy tiện toàn bộ unknown vào platform team vì sẽ làm sai trách nhiệm. Theo dõi xu hướng unknown theo thời gian và đặt owner xử lý từng nguyên nhân.

## 10. Dữ liệu billing và quy trình phân bổ

Tag phải được nối với dữ liệu sử dụng và billing. Mỗi provider có định dạng export khác nhau, nhưng quy trình tổng quát gồm:

1. Xuất dữ liệu chi phí/usage định kỳ từ billing system.
2. Chuẩn hóa account, project, subscription, resource ID, SKU, region, usage quantity và charge.
3. Nối resource ID với inventory và tag tại thời điểm sử dụng.
4. Chuẩn hóa key/value theo taxonomy.
5. Áp dụng mapping cho chi phí không có tag trực tiếp.
6. Tính chi phí theo owner, service, cost center và environment.
7. Đối chiếu tổng phân bổ với hóa đơn gốc.
8. Phát hành báo cáo và chuyển khoản unknown vào workflow xử lý.

### Dùng tag theo thời điểm phát sinh chi phí

Nếu tag của một resource thay đổi giữa tháng, không nên tự động gán toàn bộ chi phí tháng cho owner mới. Cần dùng resource metadata snapshot hoặc lịch sử thay đổi để phân bổ theo thời gian hiệu lực. Nếu billing export chỉ có tag tại thời điểm export, cần ghi nhận giới hạn và quy định cách xử lý.

### Đối chiếu tổng chi phí

Sau khi phân bổ, tổng các nhóm owner/service/environment cộng với unallocated và các điều chỉnh phải bằng tổng chi phí trong phạm vi billing đã chọn. Nếu không khớp, kiểm tra currency, discount, tax, credit, refund, rounding, shared cost và dòng chưa được map.

Không cộng lẫn chi phí trước thuế với tổng sau thuế hoặc actual cost với amortized cost mà không nêu rõ basis.

## 11. Phân bổ chi phí dùng chung

Không phải mọi khoản chi đều gắn trực tiếp với một resource owner. Một số dịch vụ được nhiều nhóm dùng chung như Kubernetes control plane/node pool, NAT gateway, load balancer, logging, monitoring, backup, security scanning và network transfer.

Có thể dùng các phương pháp:

| Phương pháp | Cách phân bổ | Khi phù hợp |
|---|---|---|
| Direct attribution | Gán trực tiếp theo resource tag | Tài nguyên chỉ phục vụ một service/team |
| Usage-based | Theo request, GB, CPU-hour, GiB-hour hoặc metric thực tế | Có telemetry đáng tin cậy |
| Capacity-based | Theo quota/reservation hoặc capacity đã cấp | Nhóm đặt trước capacity riêng |
| Proportional | Theo tỷ trọng sử dụng hoặc tỷ trọng direct cost | Shared platform có nhiều consumer |
| Equal split | Chia đều cho nhóm được xác định | Chỉ khi các consumer có quyền lợi tương đương và không có metric tốt hơn |
| Central overhead | Giữ ở cost center platform/IT chung | Chi phí nền tảng phục vụ toàn tổ chức |

### Ví dụ phân bổ NAT gateway

Một NAT gateway có chi phí cố định và chi phí theo lượng dữ liệu đi qua. Phần chi phí theo GB có thể phân bổ theo bytes egress của từng service. Phần chi phí cố định có thể phân bổ theo tỷ lệ usage hoặc số workload được phục vụ, tùy chính sách. Cần công bố công thức để team hiểu cách số tiền được tính.

### Ví dụ phân bổ Kubernetes node pool

Chi phí node pool có thể phân bổ theo CPU/memory request, usage thực tế, GPU time hoặc một mô hình kết hợp. CPU/memory request phản ánh capacity được đặt trước; usage phản ánh tài nguyên tiêu thụ. Nếu chỉ phân bổ theo CPU usage, team đặt request cao để bảo đảm headroom có thể bị đánh giá thấp phần capacity họ chiếm. Chọn metric theo mục tiêu công bằng và khả năng đo.

### Không phân bổ hai lần

Nếu chi phí node đã được phân bổ cho namespace/team, không cộng lại cùng khoản vào một dòng shared platform overhead. Thiết kế báo cáo cần phân biệt direct cost, allocated shared cost và unallocated overhead, đồng thời có quy tắc loại trừ khi tính tổng.

## 12. Showback và chargeback

### Showback

Showback cung cấp cho team báo cáo mức chi phí họ tạo ra nhưng chưa chuyển ngân sách chính thức. Đây là bước tốt để kiểm tra taxonomy và allocation rule vì các nhóm có thể phản hồi khi thấy khoản chi không hợp lý.

Showback nên có:

- Tổng chi phí theo tháng và xu hướng.
- Chi phí theo service, environment và cost center.
- Direct và shared cost tách riêng.
- Thay đổi lớn so với kỳ trước.
- Untagged/unallocated cost.
- Usage driver như vCPU-hour, GiB-month, request hoặc egress GB.
- Hành động tối ưu và owner phụ trách.

### Chargeback

Chargeback chuyển khoản chi phí vào ngân sách nội bộ hoặc hệ thống tài chính. Trước khi áp dụng, cần thống nhất phương pháp tính, thời điểm chốt, cách xử lý credit/discount/tax, shared cost và điều chỉnh hồi tố.

Không triển khai chargeback chỉ dựa trên tag mới tạo mà chưa có thời gian chạy thử. Cần một hoặc vài kỳ showback để phát hiện mapping sai, tag thiếu và chi phí dùng chung chưa công bằng.

### Actual cost và amortized cost

Actual cost phản ánh khoản phí theo cách billing provider ghi nhận trong kỳ. Amortized cost phân bổ chi phí cam kết hoặc trả trước theo thời gian sử dụng tương ứng, ví dụ reservation hoặc savings commitment. Hai góc nhìn trả lời câu hỏi khác nhau:

- Actual cost hữu ích để đối chiếu hóa đơn và dòng tiền trong kỳ.
- Amortized cost hữu ích để so sánh chi phí sử dụng theo thời gian và team.

Báo cáo cần ghi rõ loại chi phí đang dùng. Không trộn hai cách tính trong cùng một tổng nếu không có reconciliation.

## 13. Áp dụng tag cho VM, disk và tài nguyên compute liên quan

### VM/instance

Gắn owner, service, environment, cost center và managed-by khi tạo VM. Nếu VM được tạo từ autoscaling group hoặc instance template, đặt tag trong template để mọi instance mới nhận cùng metadata. Với instance thay thế, kiểm tra tag có được kế thừa từ group hay không.

### Disk, snapshot và image

Disk và snapshot có thể phát sinh chi phí độc lập sau khi VM đã bị xóa. Cần tag owner/service/environment và lifecycle. Khi snapshot được tạo tự động, cơ chế backup nên sao chép tag hoặc liên kết tới resource gốc. Khi resource gốc không còn, vẫn phải giữ owner để quyết định retention và xóa an toàn.

### Load balancer, IP và network resource

Các tài nguyên mạng có thể được tạo riêng hoặc chia sẻ. Gắn tag service/owner nếu dùng riêng; với shared resource, gắn owner platform và dùng allocation rule để phân bổ theo usage. Địa chỉ IP tĩnh, NAT gateway, firewall và endpoint có thể tiếp tục tính phí khi không còn workload liên kết.

### GPU và accelerator

GPU instance hoặc accelerator pool thường có chi phí cao. Ngoài tag owner/service/environment, có thể ghi `workload-class`, `model` hoặc `project` nếu taxonomy cho phép. Dùng usage metric như GPU-hour, device count và utilization để phân tích chi phí trên mỗi job hoặc mỗi inference. Tránh đưa dữ liệu model hoặc khách hàng nhạy cảm vào tag.

## 14. Container và Kubernetes

Trong Kubernetes, label của Pod/namespace giúp phân loại workload nhưng không tự động trở thành cloud resource tag trong mọi hệ thống billing.

### Label ở cấp namespace và workload

Một namespace có thể chứa `owner`, `service`, `environment` và `cost-center`. Deployment/StatefulSet/Job có thể kế thừa label theo template. Admission policy có thể yêu cầu các label bắt buộc khi tạo workload.

Ví dụ:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: checkout-production
  labels:
    owner: team-checkout
    service: checkout-api
    environment: production
    cost-center: CC-4102
```

Ví dụ minh họa label Kubernetes; tên và giá trị phải theo taxonomy nội bộ. Label chỉ có thể chứa định dạng hợp lệ theo Kubernetes và không tự gắn tag vào mọi cloud resource liên quan.

### Phân bổ node cost

Một node có thể chạy Pod của nhiều team. Để phân bổ chi phí node, cần một hệ thống cost allocation hiểu được request/usage, node capacity, system overhead và thời gian Pod chạy. Có thể dùng:

- CPU/memory request theo Pod.
- CPU/memory usage thực tế.
- GPU request/usage.
- Persistent volume claim và storage usage.
- Network egress theo namespace/service nếu có telemetry.
- Phần overhead node/system được phân bổ theo quy tắc riêng.

### Tránh nhầm label và cloud tag

Cloud billing có thể ghi chi phí ở cấp node, disk hoặc cluster, trong khi Kubernetes label ở cấp Pod. Cần nối dữ liệu billing với inventory và metric Kubernetes theo thời gian. Nếu chỉ đọc tag trên VM, không thể tự suy ra chính xác team nào dùng CPU bên trong node multi-tenant.

## 15. Serverless và chi phí không gắn với VM

Serverless function hoặc managed compute có thể tính phí theo invocation, duration, memory allocation, concurrency, request hoặc data transfer. Không có VM lâu dài để gắn tag theo cách truyền thống, nhưng service/function/resource vẫn có thể hỗ trợ tag hoặc metadata.

Gắn owner, service, environment và cost center ở cấp function, application, project hoặc resource group nếu provider hỗ trợ. Với chi phí dùng chung như API gateway, event bus hoặc logging, phân bổ theo request count, event volume hoặc usage metric.

Một số dòng billing chỉ thể hiện account/project/SKU mà không có resource tag. Khi đó, dùng usage export, function invocation logs hoặc allocation rule để map chi phí. Ghi rõ độ chính xác và giới hạn của phương pháp.

## 16. Chi phí không thể gắn tag trực tiếp

Một số khoản phí không có resource ID hoặc không hỗ trợ tag:

- Network egress, inter-region transfer hoặc data processing.
- Support plan, enterprise agreement hoặc subscription fee.
- Discount, credit, tax và marketplace charge.
- Shared control plane, security, logging hoặc monitoring.
- Chi phí ở cấp account/project thay vì resource.

Không loại bỏ các khoản này khỏi báo cáo. Tạo nhóm `shared`, `central-overhead` hoặc `unallocated` và áp dụng rule được công bố.

### Ví dụ allocation rule

Giả sử chi phí logging chung là 10.000 đơn vị tiền tệ trong tháng. Telemetry cho thấy service A tạo 50% ingest volume, service B tạo 30%, service C tạo 20%. Nếu chính sách phân bổ theo ingest volume, chi phí lần lượt là 5.000, 3.000 và 2.000. Nếu chi phí có phần cố định lớn, có thể tách fixed component và variable component trước khi phân bổ.

Allocation rule cần có phiên bản, owner phê duyệt, nguồn metric, kỳ áp dụng và cách xử lý khi thiếu dữ liệu. Khi thay đổi rule, giữ lịch sử để so sánh các kỳ trước theo cùng phương pháp hoặc giải thích rõ sự khác biệt.

## 17. Phân bổ discount, commitment và credit

Reservation, savings plan hoặc committed use discount có thể làm thay đổi chi phí hiệu dụng của tài nguyên. Cần xác định tổ chức phân bổ discount cho nhóm tiêu thụ, nhóm mua commitment hay cost center trung tâm.

Các lựa chọn thường gặp:

- **Discount follows usage:** lợi ích được phân bổ cho team sử dụng tài nguyên đủ điều kiện.
- **Commitment owner bears risk:** team mua commitment nhận cả chi phí chưa sử dụng và lợi ích tiết kiệm.
- **Central procurement:** cost center trung tâm giữ commitment và phân bổ chi phí hiệu dụng theo policy.
- **Shared savings:** chia sẻ lợi ích theo tỷ lệ đã thống nhất.

Không có một phương pháp đúng cho mọi tổ chức. Quan trọng là công bố cách tính và dùng nhất quán trong showback/chargeback. Với amortized cost, cần phân biệt phần commitment đã sử dụng và phần chưa sử dụng.

## 18. Quy trình vận hành phân bổ chi phí

Một quy trình FinOps cơ bản có thể chia thành các bước:

1. **Define:** phê duyệt taxonomy, owner directory, cost center và environment values.
2. **Apply:** đưa tag vào module IaC, template, deployment pipeline và provisioning workflow.
3. **Enforce:** kiểm tra bắt buộc, chặn giá trị không hợp lệ hoặc tạo exception có expiry.
4. **Collect:** xuất billing/usage data và resource inventory theo lịch.
5. **Normalize:** chuẩn hóa resource ID, tag key/value, account/project và currency.
6. **Allocate:** gán direct cost, shared cost, discount và unallocated amount theo rule.
7. **Reconcile:** đối chiếu tổng với billing source và xử lý sai lệch.
8. **Report:** phát hành showback/chargeback theo team, service, cost center và environment.
9. **Act:** giao việc tối ưu cho owner và theo dõi kết quả.
10. **Improve:** cập nhật taxonomy và rule dựa trên phản hồi, audit và thay đổi kiến trúc.

### Trách nhiệm các bên

| Vai trò | Trách nhiệm |
|---|---|
| Platform/Cloud team | Cung cấp module, tag policy, inventory và automation |
| Service owner | Đảm bảo tài nguyên có owner/service/environment đúng; hành động tối ưu |
| Finance/FinOps | Định nghĩa cost center, allocation method, showback/chargeback và reconciliation |
| Security/Governance | Kiểm tra quyền, dữ liệu nhạy cảm, policy và audit |
| Procurement | Quản lý commitment, discount và hợp đồng cloud |
| Engineering manager | Xác nhận owner/team, budget và ưu tiên xử lý |

Không nên giao toàn bộ chất lượng tag cho bộ phận FinOps. Người tạo tài nguyên và service owner là nguồn tốt nhất để cung cấp metadata đúng; platform cung cấp cơ chế tự động và FinOps quản lý phương pháp phân bổ.

## 19. Dashboard và chỉ số quản trị

Dashboard phân bổ chi phí nên cho phép drill-down từ tổng chi phí tới team, service, environment, resource và SKU.

Các chỉ số hữu ích:

| Chỉ số | Cách sử dụng |
|---|---|
| Total cloud compute cost | Theo dõi tổng chi phí trong phạm vi |
| Cost by owner/team | Xác định nhóm tạo chi phí và owner hành động |
| Cost by service | So sánh chi phí sản phẩm hoặc ứng dụng |
| Cost by environment | Theo dõi production và non-production |
| Cost by cost center | Đối chiếu ngân sách |
| Tag coverage by resource | Đo mức tuân thủ tài nguyên |
| Tag coverage by spend | Đo tỷ lệ chi phí phân bổ được |
| Unallocated cost | Theo dõi phần chưa có owner hoặc rule |
| Shared cost ratio | Đánh giá chi phí nền tảng dùng chung |
| Cost per unit | So sánh chi phí trên request, job, user hoặc workload unit |
| Month-over-month change | Phát hiện tăng giảm bất thường |
| Budget variance | So sánh actual/forecast với ngân sách |

### Theo dõi chi phí trên mỗi đơn vị công việc

Chi phí tuyệt đối không đủ để đánh giá hiệu quả. Nếu số request tăng gấp đôi và chi phí tăng 50%, hiệu quả đơn vị có thể đã tốt hơn. Có thể dùng:

\[
\text{Cost per request} =
\frac{\text{Chi phí compute được phân bổ}}
{\text{Số request hoàn tất}}
\]

Hoặc với batch:

\[
\text{Cost per job} =
\frac{\text{Chi phí compute được phân bổ}}
{\text{Số job hoàn tất}}
\]

Đảm bảo numerator và denominator cùng phạm vi thời gian, service và environment. Nếu tính chi phí production nhưng chia cho request của cả staging, kết quả sẽ sai.

## 20. Xử lý tag sai, thiếu hoặc lỗi thời

Tài nguyên có thể thiếu tag vì được tạo thủ công, dịch vụ không hỗ trợ tag, pipeline cũ hoặc owner đã rời nhóm. Cần có quy trình remediation thay vì chỉ ghi nhận trong dashboard.

### Phân loại lỗi

- Missing: thiếu key bắt buộc.
- Invalid: key có nhưng value không thuộc danh mục.
- Stale: owner/service/cost center không còn hiệu lực.
- Conflicting: tag giữa resource, parent và inventory không khớp.
- Unallocatable: dòng chi phí không có resource tag và chưa có rule.
- Orphaned: resource không còn workload hoặc owner nhận diện được.

### Quy trình remediation

1. Phát hiện từ inventory hoặc billing report.
2. Xác định resource ID, account/project, service và lịch sử tạo.
3. Tra cứu IaC state, deployment record hoặc resource group để tìm owner.
4. Gửi task tới owner hoặc platform team.
5. Cập nhật tag qua nguồn quản lý chính thức (IaC/API), tránh chỉ sửa thủ công trên console.
6. Kiểm tra billing export kỳ tiếp theo để xác nhận tag xuất hiện.
7. Nếu không xác định được owner, giữ trong unallocated và chuyển cấp xử lý theo policy.

### Không suy đoán owner từ tên tài nguyên

Tên `prod-checkout-vm-03` gợi ý service nhưng không chứng minh owner hoặc cost center. Có thể dùng tên làm tín hiệu điều tra, nhưng cần xác minh bằng deployment record, IaC state hoặc inventory chính thức trước khi gán chi phí.

## 21. Ví dụ tổng hợp phân bổ chi phí một nhóm dịch vụ

Giả sử trong một tháng, một nhóm sản phẩm có các khoản sau:

| Resource/charge | Chi phí | Metadata hoặc rule |
|---|---:|---|
| VM production của checkout API | 4.000 | owner `team-checkout`, environment `production` |
| VM staging của checkout API | 800 | owner `team-checkout`, environment `staging` |
| Disk và snapshot của checkout | 600 | owner `team-checkout`, service `checkout-api` |
| Shared NAT/network | 1.000 | phân bổ theo egress: checkout 40%, catalog 60% |
| Shared logging | 500 | phân bổ theo ingest: checkout 50%, catalog 50% |

Phần chi phí shared của checkout là 400 từ network và 250 từ logging. Tổng checkout được phân bổ là 4.000 + 800 + 600 + 400 + 250 = 6.050. Catalog nhận 600 từ network và 250 từ logging, tổng shared 850 trong ví dụ này. Phần chi phí direct của catalog nằm ngoài bảng và phải được cộng riêng khi lập báo cáo toàn sản phẩm.

Báo cáo có thể hiển thị:

- Checkout production: 4.000 direct compute.
- Checkout staging: 800 direct compute.
- Checkout storage/backup: 600 direct.
- Checkout shared network/logging: 650 allocated.
- Checkout total: 6.050.

Khi chargeback, cần nêu rõ shared cost được phân bổ theo egress và ingest, kỳ dữ liệu, currency và cách xử lý discount/credit. Ví dụ này chỉ minh họa phép tính, không đại diện mức giá của nhà cung cấp.

## 22. Những sai lầm thường gặp

- **Dùng owner là tên cá nhân:** metadata lỗi thời khi nhân sự chuyển nhóm.
- **Gộp owner và cost center:** không phân biệt trách nhiệm kỹ thuật với ngân sách.
- **Environment không chuẩn hóa:** `prod`, `production` và `prd` bị tách thành nhiều nhóm.
- **Chỉ tag VM:** disk, snapshot, IP và load balancer tiếp tục phát sinh chi phí không rõ owner.
- **Chỉ đo resource coverage:** bỏ sót phần chi phí lớn chưa được phân bổ.
- **Cho rằng tag parent luôn kế thừa:** billing export có thể không nhận tag như kỳ vọng.
- **Gán toàn bộ shared cost cho platform:** không phản ánh consumer thực tế.
- **Dùng tag để quyết định bảo mật:** tag là metadata, không thay IAM hoặc network control.
- **Không version allocation rule:** không giải thích được vì sao chargeback kỳ này khác kỳ trước.
- **Trộn actual và amortized cost:** báo cáo không đối chiếu được với hóa đơn.
- **Không giữ unknown bucket:** tổng có thể trông đủ nhưng thực tế bị gán sai.
- **Sửa tag thủ công trên console:** IaC hoặc controller có thể ghi đè lại ở lần deploy sau.

## 23. Checklist triển khai phân bổ chi phí

**Taxonomy và ownership:**

- [ ] Có định nghĩa chính thức cho `owner`, `service`, `environment` và `cost-center`.
- [ ] Owner là team/role ổn định và có kênh liên hệ.
- [ ] Cost center khớp danh mục tài chính.
- [ ] Environment có tập giá trị chuẩn và có giá trị cho shared platform.
- [ ] Tag không chứa secret hoặc dữ liệu nhạy cảm.

**Provisioning và governance:**

- [ ] IaC/template gắn tag bắt buộc khi tạo resource.
- [ ] CI/policy kiểm tra key/value và quyền exception.
- [ ] Tag được áp dụng cho VM, disk, snapshot, network và resource liên quan.
- [ ] Autoscaling/managed resource có cơ chế propagation phù hợp.
- [ ] Có scan định kỳ cho missing, invalid, stale và orphaned tag.

**Billing và allocation:**

- [ ] Billing export được chuẩn hóa và nối với resource inventory.
- [ ] Tag được xét theo thời điểm phát sinh chi phí khi cần.
- [ ] Direct, shared và unallocated cost được tách riêng.
- [ ] Shared cost có allocation rule, nguồn metric và owner phê duyệt.
- [ ] Discount, credit, tax và actual/amortized cost được xử lý nhất quán.
- [ ] Tổng phân bổ đối chiếu được với billing source.

**Báo cáo và hành động:**

- [ ] Có showback theo owner, service, cost center và environment.
- [ ] Theo dõi resource coverage và cost coverage.
- [ ] Có owner xử lý unallocated cost.
- [ ] Có budget/forecast và cảnh báo biến động.
- [ ] Có cost per unit để đánh giá hiệu quả.
- [ ] Phản hồi từ team được dùng để cải tiến taxonomy và rule.

## Kết luận

Phân bổ chi phí compute cần một taxonomy nhất quán để liên kết tài nguyên với owner, service, cost center và environment. Gắn tag ngay khi provision, kiểm soát giá trị qua IaC và policy, duy trì tag cho cả VM lẫn disk, snapshot, network và workload container/serverless. Nối metadata với billing export, đo coverage theo chi phí, phân bổ shared cost bằng rule minh bạch và giữ phần chưa phân bổ trong nhóm unknown cho tới khi xác minh. Showback giúp kiểm tra phương pháp trước chargeback; dashboard cần đối chiếu được hóa đơn và cho thấy cost per unit. Khi ownership và dữ liệu billing đáng tin cậy, mỗi team có thể hiểu phần chi phí mình tạo ra và chịu trách nhiệm cho hành động tối ưu phù hợp.
