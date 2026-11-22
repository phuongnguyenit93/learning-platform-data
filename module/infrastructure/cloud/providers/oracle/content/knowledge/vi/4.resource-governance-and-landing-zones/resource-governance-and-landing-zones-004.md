# Service limits, compartment quotas và yêu cầu tăng giới hạn

## Mục tiêu bài học

Trong một landing zone Oracle Cloud Infrastructure (OCI), tạo compartment và cấp quyền IAM mới chỉ giải quyết việc tổ chức tài nguyên và xác định ai được thực hiện thao tác nào. Nhóm nền tảng còn phải quản lý lượng tài nguyên mà mỗi môi trường được sử dụng và chuẩn bị đủ phần dư cho tăng trưởng, triển khai phiên bản mới hoặc khôi phục dịch vụ.

Bài học thuộc chủ đề **Tổ chức tài nguyên và landing zone** của module **CLOUD_PROVIDERS_ORACLE**. Sau bài học, bạn có thể phân biệt service limits với compartment quotas, đọc giới hạn theo đúng phạm vi, thiết kế quota cho môi trường OCI và chuẩn bị yêu cầu tăng giới hạn có căn cứ. Các ví dụ liên hệ Compute với VCN, lưu trữ và cơ sở dữ liệu để tránh tình trạng một thành phần đủ hạn mức nhưng toàn bộ hệ thống vẫn không triển khai được.

**Mọi con số về hạn mức trong các tình huống dưới đây đều là giả định phục vụ học tập**, không phải hạn mức mặc định, báo giá hoặc cam kết cấp tài nguyên của Oracle. Hãy lấy giá trị thực tế từ tenancy, đúng region và loại tài nguyên trước khi áp dụng.

## 1. Phân biệt những lớp kiểm soát dễ nhầm lẫn

Oracle thiết lập **service limit** cho tài nguyên của tenancy; quản trị viên thiết lập **compartment quota** để kiểm soát mức tiêu thụ trong tổ chức. Nâng quota nội bộ không làm tăng service limit. Hai cơ chế này giải quyết những trách nhiệm quản trị khác nhau. [Oracle: Service Limits](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm), [Oracle: Overview of Compartment Quotas](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/resourcequotas.htm).

| Cơ chế | Câu hỏi cần trả lời | Ví dụ trong landing zone |
| --- | --- | --- |
| IAM policy | Chủ thể này có quyền thao tác với tài nguyên không? | Nhóm ứng dụng được tạo VM trong compartment của ứng dụng |
| Service limit | Tenancy được sử dụng tối đa bao nhiêu tài nguyên trong phạm vi này? | Giới hạn OCPU của một dòng Compute tại một AD |
| Compartment quota | Môi trường hoặc nhóm này được tiêu thụ tối đa bao nhiêu? | Sandbox được dùng một lượng OCPU nhỏ hơn production |
| Budget và cảnh báo | Chi phí thực tế hoặc dự báo có vượt ngưỡng quản trị không? | Cảnh báo người phụ trách khi chi tiêu đạt ngưỡng |
| Host capacity | Hạ tầng vật lý có đáp ứng yêu cầu triển khai lúc này không? | Còn host phù hợp với shape và AD cần dùng |

Budget là ngưỡng theo dõi chi phí; bản thân budget không ngăn tài nguyên tiếp tục phát sinh chi tiêu. Vì vậy, landing zone nên kết hợp budget với quota, theo dõi sử dụng và quy trình xử lý cảnh báo. [Oracle: Track and Manage Usage and Cost](https://docs.oracle.com/en/solutions/oci-best-practices/track-and-manage-usage-and-cost1.html).

Service limit cũng khác host capacity: tenancy có thể còn hạn mức nhưng thiếu hạ tầng vật lý phù hợp để cấp VM. Khi cần bảo đảm khả năng cấp Compute, cần đánh giá phương án capacity reservation phù hợp; reservation vẫn chịu các giới hạn liên quan. [Oracle: Overview of the Compute Service](https://docs.oracle.com/en-us/iaas/Content/Compute/Concepts/computeoverview.htm).

Từ góc độ vận hành, một yêu cầu cấp tài nguyên cần đồng thời đáp ứng quyền truy cập, các giới hạn số lượng áp dụng và điều kiện triển khai của dịch vụ. Đừng suy ra rằng đã có quyền IAM thì chắc chắn tạo được tài nguyên.

## 2. Đọc đúng phạm vi, đơn vị và tên giới hạn

### 2.1. Một con số phải đi kèm đủ ngữ cảnh

Thay vì ghi “Compute còn 20”, hãy ghi một bản quan sát như sau:

| Thuộc tính | Giá trị minh họa cần ghi nhận |
| --- | --- |
| Tenancy | Tenancy dự kiến triển khai ứng dụng |
| Subscription | Subscription áp dụng nếu loại tài nguyên yêu cầu |
| Service | Compute |
| Limit name | Tên kỹ thuật lấy từ Console hoặc API |
| Đơn vị | OCPU, GB bộ nhớ, số lượng tài nguyên hoặc đơn vị dịch vụ |
| Scope | Global, region, AD hoặc phạm vi được định nghĩa riêng |
| Region và AD | Region đích; tên AD chính xác nếu cần |
| Compartment | Nơi tài nguyên được tạo và các compartment cha liên quan |
| Thời điểm | Thời điểm lấy số liệu sử dụng |

Phạm vi của giới hạn thay đổi theo dịch vụ. Không lấy hạn mức của một AD để suy ra khả năng sử dụng ở AD khác, cũng không lấy số liệu của region chính để kết luận region khôi phục đã sẵn sàng. Giá trị mặc định trong tài liệu còn phụ thuộc loại tài khoản hoặc mô hình thanh toán; giá trị đang áp dụng phải kiểm tra trong tenancy. [Oracle: Limits by Service](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/default.htm).

Ví dụ, dòng E4 có quota OCPU thuộc family `compute-core` và quota bộ nhớ thuộc family `compute-memory`. Tên `standard-e4-core-count` đo OCPU, không đo số VM; tên `standard-e4-memory-count` đo GB bộ nhớ. Các quota này có scope AD. Tài nguyên Container Instances phù hợp cũng có thể dùng chung các quota tương ứng với Compute. [Oracle: Compute Quotas](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/resourcequotas_topic-Compute_Quotas.htm).

### 2.2. Một phép tính cụ thể

Giả sử Sandbox có quota E4 là 16 OCPU và 128 GB bộ nhớ tại AD được chọn. Mỗi VM của bài thực hành dùng 2 OCPU và 16 GB:

```text
Số VM theo OCPU  = floor(16 / 2)  = 8
Số VM theo RAM   = floor(128 / 16) = 8
Trần theo hai quota minh họa     = 8 VM
```

Nếu đổi mỗi VM thành 2 OCPU và 32 GB, quota bộ nhớ chỉ đáp ứng 4 VM dù quota OCPU còn dư. Nếu đổi sang dòng shape khác, phải tra lại những giới hạn áp dụng cho dòng đó; quota E4 không tự giới hạn toàn bộ Compute.

Trong triển khai thực, cần kiểm tra thêm boot volume, block volume, địa chỉ mạng, load balancer và tài nguyên cơ sở dữ liệu mà cấu hình yêu cầu. Tính đủ OCPU không thay thế được việc kiểm tra những phụ thuộc này.

## 3. Tính phần dư theo tất cả ràng buộc áp dụng

Phần dư, hay **headroom**, là lượng còn có thể sử dụng trong một ràng buộc cụ thể. Với một loại tài nguyên và cùng phạm vi, có thể dùng mô hình lập kế hoạch sau:

```text
Phần dư của ràng buộc i = max(0, trần_i - mức_sử_dụng_i)
Phần dư khả dụng theo số lượng = min(các phần dư đang áp dụng)
```

Trong mô hình này, service limit dùng mức sử dụng tương ứng của tenancy; quota compartment cha phải tính mức sử dụng của các compartment con thuộc phạm vi đó. Không trừ mức sử dụng của riêng một ứng dụng khỏi giới hạn dùng chung rồi coi toàn bộ phần còn lại đã được dành cho ứng dụng.

Giả sử mọi hàng dưới đây cùng đo OCPU E4 tại **cùng một AD**, và các quota đều áp dụng cho yêu cầu mới:

| Ràng buộc | Trần giả định | Đã dùng trong phạm vi của ràng buộc | Phần dư |
| --- | ---: | ---: | ---: |
| Service limit của tenancy | 128 | 108 | 20 |
| Quota của compartment cha `Applications` | 64 | 60 | 4 |
| Quota của compartment con `Applications:TeamA` | 24 | 12 | 12 |

`TeamA` muốn thêm một VM 8 OCPU. Mặc dù quota riêng còn 12 và tenancy còn 20, quota của `Applications` chỉ còn 4. Yêu cầu này không đáp ứng giới hạn ở compartment cha. Xin Oracle tăng service limit chưa xử lý được nút thắt đó.

Nếu chỉ cần thêm 4 OCPU, phép tính số lượng cho kết quả đủ điều kiện. Đây vẫn chưa phải bảo đảm cấp phát: IAM, bộ nhớ, các phụ thuộc và host capacity còn phải phù hợp.

Với nhiều chiều tài nguyên, hãy tính riêng từng chiều. Không cộng “4 OCPU còn dư” với “32 GB RAM còn dư” thành một con số headroom chung.

## 4. Viết compartment quota có phạm vi rõ ràng

### 4.1. Ba thao tác cơ bản

Quota dùng ngôn ngữ khai báo riêng, có hình thức gần IAM policy nhưng không phải câu lệnh cấp quyền IAM:

```text
set <family> quota <quota-name> to <value> in compartment <compartment>
zero <family> quota <quota-name> in compartment <compartment>
unset <family> quota <quota-name> in compartment <compartment>
```

`set` đặt trần; `zero` đặt mức sử dụng được phép về không; `unset` gỡ thiết lập quota tương ứng để các giới hạn còn áp dụng tiếp tục quyết định. Điều kiện hỗ trợ gồm `request.region` và `request.ad`. Các statement trong cùng một policy được đánh giá theo thứ tự; statement sau thay thế statement trước khi cùng nhắm một tài nguyên. Giữa các policy cùng áp dụng, ràng buộc chặt hơn có hiệu lực; service limit luôn tiếp tục ràng buộc. [Oracle: Quota Policy Syntax](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/quota_policy_syntax.htm).

### 4.2. Ví dụ giới hạn Sandbox

Giả sử tổ chức có compartment `Sandbox`, được phép thực hành E4 tại Phoenix. Hai statement minh họa:

```text
set compute-core quota standard-e4-core-count to 16 in compartment Sandbox where request.region = 'us-phoenix-1'
set compute-memory quota standard-e4-memory-count to 128 in compartment Sandbox where request.region = 'us-phoenix-1'
```

Ở đây, điều kiện region chỉ chọn nơi statement áp dụng. Do hai quota E4 có scope AD, giá trị được hiểu theo từng AD phù hợp, **không phải một tổng chung 16 OCPU và 128 GB cho cả region**. Nếu mục tiêu quản trị là tổng chi phí toàn region, phải lập kế hoạch theo số AD được sử dụng và bổ sung các kiểm soát phù hợp.

Statement này cũng không chặn E4 ở các region khác. Những region không khớp điều kiện vẫn chịu các policy và service limits khác đang áp dụng. Muốn xây dựng danh sách region được phép, hãy thiết kế đầy đủ các statement chặn và ngoại lệ, rồi kiểm chứng thứ tự và tương tác giữa chúng.

Tên AD trong điều kiện hoặc API phải lấy từ tenancy của bạn; không sao chép tên AD của một tenancy khác. Với compartment lồng nhau, dùng đường dẫn được xác định đúng, chẳng hạn:

```text
set compute-core quota standard-e4-core-count to 12 in compartment Applications:Development
```

Các mẫu quota chính thức của Oracle minh họa cả đường dẫn compartment lồng nhau và cách dùng `zero` kết hợp ngoại lệ trong cùng policy. [Oracle: Sample Quotas](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/sample_quotas.htm).

### 4.3. Đặt thứ tự và ngoại lệ có chủ đích

Trong một **policy duy nhất**, có thể mô tả ý định chặn các quota OCPU thuộc family rồi cấp lại E4 cho Sandbox như sau:

```text
zero compute-core quotas in compartment Sandbox
set compute-core quota standard-e4-core-count to 16 in compartment Sandbox
```

Statement thứ hai tạo ngoại lệ cho E4 trong policy này. Đây là ví dụ cần thử ở môi trường lab: nó chưa giới hạn bộ nhớ, storage hay mọi dịch vụ khác của Sandbox. Nếu hai statement được tách thành hai policy độc lập, không được suy ra rằng ngoại lệ sẽ ghi đè policy chặn.

Tương tự, nếu policy A đặt quota 8 và policy B đặt quota 12 cho cùng tài nguyên, compartment và phạm vi, kết quả bị ràng buộc bởi mức 8. Chỉ sửa policy B lên 24 không giải quyết được giới hạn từ A.

`unset` cũng không phải cách vượt service limit, xóa quota ở mọi policy hay tự nhận hạn mức của compartment khác. Khi thay đổi quota, cần xem toàn bộ các statement liên quan đến đường dẫn compartment và scope của yêu cầu.

### 4.4. Quota không phải cơ chế thu hồi tài nguyên

Đừng dùng việc hạ quota như một phương án dọn môi trường hoặc giảm hóa đơn ngay lập tức. Quy trình thu hồi cần xác định tài nguyên, chủ sở hữu, dữ liệu phải giữ và thao tác vòng đời phù hợp. Quota phục vụ kiểm soát tiêu thụ, còn thay đổi tài nguyên phải được xử lý riêng.

Khi trần thấp hơn mức đang dùng, hãy kiểm tra tác động đến lần tạo mới, scale hoặc thay thế tiếp theo. Console có thể hiển thị usage lớn hơn limit khi giới hạn đã bị hạ sau lúc tài nguyên được tạo. [Oracle: Viewing a Tenancy's Limits and Usage](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/view-tenancy.htm).

Vì vậy, trước khi giảm quota production, phải tính cả lượng tài nguyên tạm thời cho bảo trì và khôi phục. Một môi trường đang chạy ổn vẫn có thể mất khả năng tạo VM thay thế nếu phần dư bị cắt quá sát.

## 5. Đưa quota vào thiết kế landing zone

Một cấu trúc minh họa:

```text
Tenancy
├── SharedServices
├── Applications
│   ├── Production
│   └── NonProduction
│       ├── Development
│       └── Sandbox
└── Recovery
```

Quota nên phản ánh vai trò vận hành của từng nhánh thay vì chia hạn mức bằng nhau:

| Nhánh | Ý định phân bổ | Điều cần bảo vệ |
| --- | --- | --- |
| SharedServices | Đủ cho mạng dùng chung, giám sát và dịch vụ nền tảng | Đợt mở rộng ứng dụng không bị chặn bởi tài nguyên nền tảng |
| Production | Đủ tải mục tiêu, triển khai thay thế và khôi phục cục bộ | Có phần dư khi phiên bản cũ và mới cùng tồn tại |
| Development | Phục vụ công việc thường xuyên với trần có thể dự báo | Tránh môi trường phát triển chiếm hết giới hạn dùng chung |
| Sandbox | Phạm vi thực hành nhỏ, có người chịu trách nhiệm và thời hạn | Có thể kiểm chứng hành vi chặn mà chi phí vẫn kiểm soát được |
| Recovery | Theo nhu cầu khôi phục đã tính toán | Region và tài nguyên khôi phục được kiểm tra độc lập |

Đây là ý định quản trị, không có nghĩa quota tự dành sẵn tài nguyên vật lý cho từng nhánh. Tổ chức cần theo dõi cả tổng sử dụng thực tế và những kịch bản có thể diễn ra đồng thời.

### Tính phần dư cho một đợt triển khai

Giả sử production chạy 12 VM E4, mỗi VM 4 OCPU trong cùng AD. Chiến lược blue/green tạo đủ 12 VM mới trước khi gỡ 12 VM cũ:

```text
Production đang chạy                 = 12 × 4 = 48 OCPU
Production mới chạy song song        = 12 × 4 = 48 OCPU
Dự phòng phục hồi trong ví dụ         =          16 OCPU
Quota production cần cho kịch bản     =         112 OCPU
Các compartment khác cùng phạm vi    =          40 OCPU
Tổng tenancy cần cho kịch bản         =         152 OCPU
```

Nếu service limit hiện tại là 128, quota production đặt 112 chưa đủ giúp đợt triển khai chạy được. Ngay giai đoạn hai phiên bản cùng tồn tại, tổng sử dụng dự kiến đã là `48 + 48 + 40 = 136`, vượt 128.

Nhóm có thể đề xuất giới hạn tổng mới 160 OCPU trong tình huống này, kèm giải thích nhu cầu 152 và phần dư còn lại. Đồng thời, phải tính bộ nhớ, boot volume và các thành phần đi kèm; con số 160 OCPU không tự giải quyết những chiều tài nguyên khác.

Nếu các VM được phân bố qua nhiều AD, hãy lập lại bảng theo từng AD. Nếu phương án triển khai chỉ tạo thêm một số VM mỗi lượt, dùng đỉnh đồng thời của phương án đó thay cho giả định nhân đôi toàn bộ.

## 6. Quan sát bằng Console và tự động hóa bằng API

### 6.1. Kiểm tra đúng dòng giới hạn trên Console

Trong OCI Console, mở **Limits, Quotas and Usage**, chọn region đích rồi lọc service, scope, compartment và subscription nếu tài nguyên áp dụng. Ghi lại tên kỹ thuật, service limit, usage và phần còn lại. Không phải mọi dịch vụ hoặc tài nguyên đều hiển thị đầy đủ thông tin sử dụng trên màn hình này. [Oracle: Viewing a Tenancy's Limits and Usage](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/view-tenancy.htm).

Để tránh chọn nhầm quota, có thể bắt đầu từ dòng tài nguyên phù hợp và chức năng **Create quota policy stub**. Sau đó kiểm tra statement sinh ra với compartment, giá trị và điều kiện mong muốn trước khi lưu. [Oracle: Overview of Compartment Quotas](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/resourcequotas.htm).

Không coi cột phần dư ở một dòng là bản cam kết cho toàn bộ ứng dụng. Hãy đối chiếu thêm quota của các compartment cha và nhu cầu của toàn bộ cấu hình triển khai.

### 6.2. Ví dụ đọc resource availability bằng OCI CLI

Đoạn PowerShell dưới đây là **ví dụ để người học chạy trong tenancy của mình**, sau khi đã cấu hình OCI CLI và quyền đọc. Thay toàn bộ placeholder bằng giá trị thực; không dùng chuỗi tên AD minh họa để gọi API:

```powershell
$ociTargetRegion = '<region-id>'
$ociSandboxId = '<compartment-ocid>'
$ociTargetAd = '<availability-domain-name-from-your-tenancy>'

oci --region $ociTargetRegion limits resource-availability get --compartment-id $ociSandboxId --service-name compute --limit-name standard-e4-core-count --availability-domain $ociTargetAd
```

`GetResourceAvailability` tra thông tin theo compartment, service, limit và scope. Tham số AD là bắt buộc với limit có scope AD; không truyền AD như một quy ước chung cho mọi loại limit. Không phải limit nào cũng hỗ trợ API này; kết quả không có dữ liệu hoặc phản hồi không được hỗ trợ phải được ghi nhận là chưa xác định, không quy đổi thành “còn vô hạn”. [Oracle: OCI CLI resource-availability get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/resource-availability/get.html).

Availability theo hạn mức được tính từ mức sử dụng, service limits và quotas phù hợp; đây không phải kết quả kiểm tra host vật lý. Một số trường có thể trống khi dịch vụ chưa cung cấp được dữ liệu. [Oracle: Resource Availability](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/resource-availability.html).

### 6.3. Phân quyền cho người quan sát và người thay đổi

Có thể tách nhóm chỉ xem khỏi nhóm quản lý quota. Hai statement sau minh họa quyền tra định nghĩa/giá trị giới hạn ở tenancy và quyền đọc availability trong Sandbox:

```text
Allow group LimitsViewers to inspect resource-availability in tenancy
Allow group LimitsViewers to read resource-availability in compartment Sandbox
```

Cần điều chỉnh tham chiếu group theo identity domain và cấu trúc IAM thực tế. Quyền đọc giới hạn không tương đương quyền quản lý quota hoặc quyền tạo Compute. [Oracle: Service Limits — Required IAM Policy](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm).

Người quản lý quota cần các quyền của Quotas service phù hợp. Trong landing zone, nên giao trách nhiệm này cho nhóm nền tảng và giới hạn phạm vi ủy quyền khi có thể. Việc cho một nhóm tự sửa quota mà chính nhóm đó phải tuân thủ cần được xem xét cùng mô hình trách nhiệm của tổ chức. [Oracle: Authentication and Authorization for Quotas](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/resourcequotas_authentication_and_authorization.htm).

### 6.4. Dùng quan sát hạn mức trong pipeline

Một quy trình kiểm tra trước triển khai có thể thực hiện tuần tự:

1. Từ cấu hình dự kiến, tính lượng tài nguyên **tăng thêm ở thời điểm đỉnh**, kể cả tài nguyên tạm cho thay thế.
2. Ánh xạ từng nhu cầu sang service, limit name, đơn vị và scope chính xác.
3. Thu thập giới hạn, usage và quota hiệu lực tại đúng compartment; ghi rõ trường nào chưa có dữ liệu.
4. So sánh nhu cầu với phần dư, cộng biên dự phòng đã thống nhất.
5. Nếu không đủ hoặc chưa xác định, đưa ra nguyên nhân cụ thể và người chịu trách nhiệm xử lý.
6. Sau khi triển khai, ghi nhận usage mới và đối chiếu với dự tính.

Đây là kiểm tra hỗ trợ quyết định, không phải thao tác giữ chỗ. Hai pipeline có thể cùng đọc thấy phần dư rồi cùng tạo tài nguyên. Với môi trường dùng chung, cần điều phối các đợt triển khai lớn; kết quả cấp phát thực tế vẫn quyết định thành công cuối cùng.

Ngưỡng cảnh báo nên bám thời gian chuẩn bị. Ví dụ, cảnh báo khi phần dư thấp hơn nhu cầu của một đợt triển khai đầy đủ có thể hữu ích hơn việc chỉ đặt một tỷ lệ cố định cho mọi tài nguyên. Mức 70% hoặc 85%, nếu dùng, là quy ước vận hành của tổ chức và phải được lựa chọn theo tải cùng thời gian xử lý.

## 7. Chẩn đoán trước khi xin tăng giới hạn

Khi thao tác tạo hoặc mở rộng thất bại, lưu thông báo lỗi đầy đủ, request ID, thời điểm, region, AD, compartment, shape và cấu hình yêu cầu. Sau đó xác định lớp gây chặn:

| Dấu hiệu | Kiểm tra tiếp | Hướng giải quyết phù hợp |
| --- | --- | --- |
| Không được phép hoặc không thấy tài nguyên | Principal, IAM policy, compartment và phạm vi truy cập | Điều chỉnh quyền theo trách nhiệm |
| Quota nội bộ không đủ | Quota tại đích, policy liên quan và usage ở compartment cha | Dọn tài nguyên phù hợp hoặc sửa quota nội bộ |
| Service limit không đủ | Tên limit, scope, subscription và tổng usage tương ứng | Giảm nhu cầu hoặc gửi yêu cầu tăng service limit |
| `Out of host capacity` | Shape, AD, fault domain và khả năng cung ứng | Đánh giá cấu hình hoặc vị trí triển khai khác |
| Bị throttling | Tần suất gọi API, retry và mức song song | Điều chỉnh retry/backoff và cách gọi API |
| Cấu hình không hợp lệ | Các tổ hợp shape, mạng, storage và tham số dịch vụ | Sửa cấu hình theo thông báo lỗi |

Với `Out of host capacity`, Oracle hướng dẫn xem xét đổi shape, fault domain hoặc AD, tùy điều kiện của ứng dụng. Tăng service limit không đồng nghĩa bổ sung host vật lý ở vị trí đang thiếu. [Oracle: Resolving Out of Host Capacity](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/troubleshooting-out-of-host-capacity.htm).

Ví dụ, TeamA bị chặn ở quota của `Applications` như phần 3 thì gửi yêu cầu tăng tenancy limit sẽ không giúp VM 8 OCPU được tạo. Ngược lại, nếu quota riêng còn nhiều nhưng tenancy đã hết hạn mức đúng AD, chỉ sửa quota riêng cũng không giải quyết được.

Đừng dùng việc xóa tài nguyên đang phục vụ tải làm cách thử đầu tiên. Trước khi thu hồi, cần biết tài nguyên đó thuộc ai, ảnh hưởng ứng dụng nào và liệu nhu cầu triển khai tiếp theo còn cần đến nó không.

## 8. Chuẩn bị yêu cầu tăng service limit

### 8.1. Nội dung để Oracle và nhóm nội bộ cùng đánh giá

Một đề nghị hữu ích cần trả lời được ba câu hỏi: đang bị giới hạn ở đâu, cần tổng bao nhiêu và cần từ khi nào. Hồ sơ vận hành có thể gồm:

| Thông tin | Ví dụ minh họa |
| --- | --- |
| Tenancy và subscription áp dụng | Định danh môi trường; subscription nếu tài nguyên yêu cầu |
| Service, limit name, đơn vị | Compute; `standard-e4-core-count`; OCPU |
| Region và AD | Giá trị chính xác của phạm vi triển khai |
| Giới hạn hiện tại | 128 OCPU |
| Usage hiện tại | 88 OCPU tại thời điểm đo |
| Tổng giới hạn mong muốn | 160 OCPU, tức tăng thêm 32 so với hiện tại |
| Nhu cầu ở đỉnh | 152 OCPU gồm tải song song và dự phòng |
| Mốc cần sử dụng | Ngày dự kiến, giai đoạn chuẩn bị và triển khai |
| Căn cứ | Số VM, OCPU mỗi VM, chiến lược triển khai, tải ngoài production |
| Người phụ trách | Đầu mối giải thích cấu hình và theo dõi yêu cầu |
| Phụ thuộc | Bộ nhớ, storage, networking và database cần kiểm tra song song |

Con số cần nhập là **giá trị tổng mới mong muốn** theo ý nghĩa của biểu mẫu, không nhầm với lượng tăng thêm. Trong ví dụ này, `128 → 160` khác hoàn toàn với việc đề nghị tăng thêm 160.

Không chèn khóa API, private key, mật khẩu hoặc dữ liệu ứng dụng vào lý do yêu cầu. Mô tả khối lượng và cấu hình đủ cụ thể để đánh giá mà không đưa nội dung bí mật.

### 8.2. Mẫu lý do yêu cầu

```text
Mục đích: Chuẩn bị triển khai phiên bản mới cho ứng dụng đặt hàng.
Service/limit: Compute / standard-e4-core-count, đơn vị OCPU.
Phạm vi: <region-id>, <availability-domain-name>.
Subscription: <nếu áp dụng>.

Giới hạn hiện tại: 128 OCPU.
Usage quan sát được: 88 OCPU tại <thời điểm đo>.
Đề nghị tổng giới hạn mới: 160 OCPU.

Căn cứ:
- Production hiện có 12 VM E4, mỗi VM 4 OCPU: 48 OCPU.
- Blue/green cần thêm 12 VM cùng cấu hình: thêm 48 OCPU.
- Dự phòng phục hồi trong thời gian triển khai: 16 OCPU.
- Các compartment khác trong cùng phạm vi dùng: 40 OCPU.
- Nhu cầu đỉnh dự kiến: 48 + 48 + 16 + 40 = 152 OCPU.

Mốc dự kiến sử dụng: <ngày và múi giờ>.
Kế hoạch sau triển khai: Gỡ phiên bản cũ sau khi xác nhận ổn định.
Đầu mối: <nhóm chịu trách nhiệm>.
```

Mẫu trên liên kết số liệu ở hiện tại với kịch bản sử dụng. Nó không khẳng định Oracle sẽ phê duyệt mức 160 hoặc đảm bảo capacity tương ứng.

### 8.3. Gửi và theo dõi

Trong Console, luồng **Request a limit increase** cho phép nhập lý do, thêm các requested items, chọn service/limit, điền giá trị theo scope rồi xem lại trước khi gửi. Một số tài nguyên còn yêu cầu subscription hoặc thông tin bổ sung riêng. Thời gian phản hồi có thể từ vài phút đến vài ngày; không lập kế hoạch với giả định mọi đề nghị được xử lý tức thì. [Oracle: Creating a Limit Increase Request](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/create-request.htm).

Tổ chức nên lưu định danh yêu cầu cùng kế hoạch triển khai, theo dõi từng mục và trả lời khi Oracle cần thêm thông tin. Có thể đọc chi tiết yêu cầu trong Console hoặc bằng API/CLI tương ứng. [Oracle: Getting Details for a Limit Increase Request](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/get-request.htm).

Gửi đề nghị không đồng nghĩa đã có hạn mức mới. Khi được phê duyệt, đọc lại đúng giá trị trong tenancy, đối chiếu từng item và kiểm tra quota nội bộ. Một số giới hạn không được phép tăng hoặc đề nghị có thể không được chấp nhận; luôn có phương án điều chỉnh nhu cầu hoặc lịch triển khai. [Oracle: Service Limits](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm).

## 9. Bài thực hành có kiểm soát

Thực hành trong một compartment lab với tài nguyên nhỏ đã được người phụ trách cho phép. Phần này mô tả thao tác học tập; không yêu cầu thử chạm giới hạn của production hoặc gửi đề nghị tăng hạn mức thật chỉ để hoàn tất bài học.

### Phần A — Lập bản quan sát

1. Chọn một region và AD dự kiến thực hành.
2. Chọn một dòng Compute được tenancy hỗ trợ; xác định quota OCPU và bộ nhớ liên quan.
3. Ghi service limit, usage, phần dư và quota của compartment cùng các cha liên quan.
4. Chọn thêm một phụ thuộc như boot volume và ghi đơn vị, scope của nó.
5. Đánh dấu rõ những thông tin chưa lấy được; không tự điền bằng số mặc định.

Kết quả cần giải thích được vì sao một cấu hình VM cụ thể có hoặc chưa có đủ headroom.

### Phần B — Kiểm chứng quota Sandbox

1. Tính trước nhu cầu nhỏ nhất đủ chạy bài lab và chi phí dự kiến.
2. Người có quyền tạo quota ghi lại trạng thái ban đầu, rồi đặt quota hẹp cho đúng tài nguyên và scope.
3. Tạo một cấu hình nằm trong trần và ghi lại mức sử dụng sau thao tác.
4. Trong lab, thử một yêu cầu nhỏ vượt quota có chủ đích; ghi nguyên nhân bị từ chối mà không mở rộng các quyền khác.
5. Xác minh lỗi thuộc quota, không kết luận chỉ dựa trên việc tạo tài nguyên thất bại.
6. Thu hồi tài nguyên do bài lab tạo theo vòng đời phù hợp, kiểm tra tài nguyên lưu trữ còn lại và hoàn nguyên quota về trạng thái đã ghi nhận.

Nếu không được phép cấp tài nguyên, thực hiện bằng phép tính và bản quan sát sẵn có. Nêu rõ phần nào là kiểm chứng thực tế, phần nào là mô phỏng.

### Phần C — Lập yêu cầu trên giấy

Dùng kịch bản 128 OCPU hiện tại và 152 OCPU ở đỉnh để soạn một đề nghị tăng tổng lên 160. Giải thích vì sao quota production cần 112, vì sao usage hiện tại là 88 và tại sao quota 112 không tự làm tăng service limit 128.

Sau đó thay đổi chiến lược: chỉ tạo thêm 3 VM mỗi lượt thay vì 12 VM cùng lúc. Tính lại đỉnh OCPU với các giả định rõ ràng về thời điểm gỡ VM cũ. So sánh tác động lên nhu cầu hạn mức, thời gian triển khai và khả năng quay lại phiên bản trước.

## 10. Tự kiểm tra khả năng áp dụng

| Tình huống | Kết luận cần rút ra |
| --- | --- |
| Sandbox còn OCPU nhưng hết quota bộ nhớ | Kiểm tra giới hạn từng chiều, không chỉ OCPU |
| Quota con còn 12 nhưng quota cha chỉ còn 4 | VM 8 OCPU bị chặn bởi ràng buộc cha |
| Oracle đã tăng limit nhưng tạo VM vẫn bị quota chặn | Đối chiếu và điều chỉnh quota nội bộ phù hợp |
| Service limit và quota đều còn, nhưng thiếu host | Xử lý bài toán capacity theo shape và vị trí |
| Budget cảnh báo vượt ngưỡng | Xử lý chi phí; budget tự nó không dừng tài nguyên |
| Bản triển khai mới cần chạy song song bản cũ | Tính theo đỉnh đồng thời thay vì tải ổn định |
| Region chính đủ headroom | Chưa đủ căn cứ kết luận region khôi phục cũng đủ |
| API không trả availability cho một limit | Ghi nhận chưa xác định và chọn cách kiểm tra bổ sung |

Trong vận hành landing zone, hãy duy trì người chịu trách nhiệm cho từng quota, lịch xem lại phần dư, kế hoạch tăng giới hạn trước các đợt mở rộng và dấu vết của các thay đổi. Service limits giúp xác định trần của tenancy; compartment quotas phân bổ quyền tiêu thụ bên trong trần đó. Kết hợp chúng với IAM, quan sát chi phí và kế hoạch capacity giúp triển khai OCI có kiểm soát, đồng thời giữ đủ khả năng thay thế và khôi phục tài nguyên khi cần.