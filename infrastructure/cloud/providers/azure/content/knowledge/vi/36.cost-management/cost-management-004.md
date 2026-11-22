# Thiết lập budget và cảnh báo chi phí

## 1. Vì sao cần budget khi vận hành ứng dụng trên Azure?

Trên Azure, ứng dụng có thể tạo chi phí liên tục từ máy ảo, App Service, cơ sở dữ liệu, lưu trữ, lưu lượng mạng, thu thập log và các dịch vụ được quản lý. Những thay đổi tưởng nhỏ như tăng số replica, chọn SKU cao hơn, giữ snapshot quá lâu hoặc mở rộng thời gian lưu log có thể khiến tổng chi phí vượt mức dự kiến. Nếu chỉ xem hóa đơn cuối tháng, đội kỹ thuật thường phát hiện vấn đề quá muộn.

Trong chương **Quản lý chi phí** của module `CLOUD_PROVIDERS_AZURE`, bài học này hướng dẫn sử dụng **Azure Cost Management budgets** để đặt mục tiêu chi phí và cấu hình thông báo khi chi phí thực tế hoặc chi phí dự báo chạm ngưỡng. Kiến thức được gắn với việc tổ chức subscription, resource group, Microsoft Entra ID/RBAC, hạ tầng mạng, compute, storage, database và hệ thống giám sát một ứng dụng Azure.

**Budget là ngưỡng để theo dõi và cảnh báo; mặc định nó không chặn việc sử dụng tài nguyên, không dừng VM và không đặt trần cứng cho hóa đơn.** Khi nhận thông báo, đội vận hành vẫn phải kiểm tra nguyên nhân và chủ động hành động theo quy trình được duyệt.

Sau bài học, bạn có thể:

1. Phân biệt budget, chi phí thực tế, chi phí dự báo, cost analysis, anomaly và invoice.
2. Chọn đúng **scope** ngân sách, chu kỳ, số tiền, bộ lọc và người chịu trách nhiệm.
3. Tạo budget bằng Azure Portal và hiểu cấu hình cảnh báo **Actual** và **Forecasted**.
4. Triển khai một budget mẫu bằng Bicep theo mô hình Infrastructure as Code (IaC).
5. Xây dựng runbook khi chi phí đạt ngưỡng 60%, 80% hoặc dự báo vượt 100%, có kiểm soát quyền, bảo mật và tác động sản xuất.
6. Xác minh thông báo, đánh giá sai lệch dữ liệu và theo dõi hiệu quả kiểm soát chi phí theo thời gian.

## 2. Các khái niệm nền tảng

### 2.1. Azure Cost Management và budget

**Azure Cost Management** giúp xem, phân tích, phân bổ và quản lý chi phí phát sinh ở những phạm vi được hỗ trợ. Hai nhóm công việc khác nhau:

- **Cost analysis:** trả lời “đã phát sinh chi phí ở đâu, vào thời điểm nào, dịch vụ và đội nào đang tạo ra chi phí?”.
- **Budgets:** trả lời “chi phí trong phạm vi này có đang tiến sát hoặc dự kiến vượt mục tiêu hay không, và ai cần được thông báo?”.

Budget thường có các thuộc tính:

| Thuộc tính | Vai trò | Ví dụ |
| --- | --- | --- |
| **Scope** | Phạm vi chi phí được theo dõi | Resource group `rg-orders-dev` |
| **Amount** | Mức ngân sách cho một chu kỳ | 1.200 USD/tháng |
| **Time grain** | Chu kỳ đánh giá ngân sách | Monthly |
| **Time period** | Ngày bắt đầu và kết thúc hiệu lực | Từ tháng 11/2026 đến tháng 10/2027 |
| **Filters** | Giới hạn các khoản chi phí thuộc budget, nếu được hỗ trợ | Service, resource group, tag |
| **Notifications** | Quy tắc kích hoạt thông báo theo ngưỡng | Actual 80%; Forecasted 100% |
| **Recipients** | Người hoặc nhóm nhận cảnh báo | Email và Action Group được hỗ trợ |

Một budget hàng tháng có thể tồn tại qua nhiều tháng: **mức tiền được xét lại theo từng tháng**, còn khoảng hiệu lực quyết định budget hoạt động trong những tháng nào. Không cần tạo một budget mới vào đầu mọi tháng nếu cấu hình đang phù hợp.

### 2.2. Actual cost, forecasted cost và invoice

**Actual cost** là mức chi phí đã được hệ thống Cost Management ghi nhận trong phạm vi và chu kỳ tính đến dữ liệu hiện có. **Forecasted cost** là ước tính chi phí cho phần còn lại của chu kỳ dựa trên dữ liệu và mô hình dự báo của Azure, khi tính năng được hỗ trợ ở scope tương ứng.

Ví dụ vào ngày 20 của một tháng:

~~~text
Ngân sách tháng:               1.200 USD
Actual cost đã ghi nhận:         710 USD
Forecasted cost cả tháng:      1.340 USD

Tỷ lệ actual / budget:        710 / 1.200 = 59,2%
Tỷ lệ forecast / budget:     1.340 / 1.200 = 111,7%
~~~

Ở trường hợp này, chi phí hiện tại chưa vượt ngưỡng **Actual 80%**, nhưng dự báo đã vượt **Forecasted 100%**. Cảnh báo dự báo giúp đội ứng dụng phản ứng sớm hơn so với việc đợi hóa đơn vượt mục tiêu.

**Actual và Forecasted không phải số trên hóa đơn cuối cùng.** Dữ liệu chi phí có độ trễ, có thể có khoản điều chỉnh, điều kiện tính thuế, tín dụng, cam kết chi tiêu, chiết khấu và phương pháp hiển thị khác nhau tùy tài khoản/hợp đồng. Dự báo cũng có sai số; các khoản phát sinh bất thường sau thời điểm ước tính có thể làm kết quả khác đáng kể.

### 2.3. Actual cost và amortized cost

Khi phân tích chi phí, cần biết dashboard đang hiển thị cách tính nào:

- **Actual cost:** tập trung vào khoản chi được ghi nhận theo thời điểm phát sinh hóa đơn/ghi nhận chi phí theo cơ chế của tài khoản.
- **Amortized cost:** phân bổ chi phí mua trước hoặc cam kết đủ điều kiện (ví dụ Reservations) theo thời gian sử dụng, giúp so sánh hiệu quả tiêu thụ tài nguyên giữa các kỳ.

Bộ dữ liệu và cách tính ngân sách phụ thuộc loại tài khoản, scope và tùy chọn Cost Management được hỗ trợ. Khi đối chiếu một budget với Cost Analysis hoặc invoice, **hãy kiểm tra cùng scope, khoảng thời gian, loại chi phí, tiền tệ và bộ lọc**; không kết luận có sai số chỉ vì hai báo cáo đang dùng cách ghi nhận khác nhau.

### 2.4. Budget alert khác gì anomaly detection?

| Cơ chế | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Budget alert** | Chi phí có đạt tỷ lệ so với mục tiêu đã đặt không? | Actual đạt 80% của 1.200 USD |
| **Forecasted budget alert** | Chi phí cả kỳ có khả năng vượt mục tiêu không? | Forecast tháng là 1.340 USD |
| **Cost anomaly detection** | Mẫu chi phí có bất thường so với xu hướng lịch sử không? | Log ingestion tăng đột ngột sau deploy |
| **Azure Monitor metric alert** | Một chỉ số tài nguyên có vượt ngưỡng kỹ thuật không? | CPU cao, số lần autoscale tăng |
| **Invoice/billing review** | Số tiền cuối cùng phải thanh toán hoặc cần đối soát là bao nhiêu? | Xem kỳ hóa đơn và khoản điều chỉnh |

Budget thường hữu ích nhất khi gắn với **chủ sở hữu chi phí và hành động sau thông báo**. Anomaly detection, nếu sẵn có ở scope/tài khoản, bổ sung khả năng phát hiện thay đổi bất thường; nó không thay thế ngưỡng ngân sách đã cam kết.

## 3. Chọn scope: theo dõi ai, dịch vụ nào và ngân sách nào?

Ngân sách có ý nghĩa khi phạm vi của nó khớp trách nhiệm của một người hoặc một nhóm. Trong Azure, chi phí có thể được xem ở các scope khác nhau tùy loại tài khoản và quyền được cấp: subscription, resource group, management group hoặc các billing scope được hỗ trợ.

### 3.1. Các scope thường gặp

| Scope | Phù hợp khi | Điểm cần lưu ý |
| --- | --- | --- |
| **Subscription** | Theo dõi toàn bộ môi trường hoặc một đơn vị có subscription riêng | Bao gồm nhiều resource group; cần tránh trùng khi tổng hợp báo cáo |
| **Resource group** | Một ứng dụng/môi trường nằm chủ yếu trong một resource group | Chi phí phụ thuộc dùng chung ở resource group khác có thể không xuất hiện |
| **Management group** | Tổ chức muốn giám sát nhiều subscription dưới một cấu trúc quản trị | Khả năng tạo/xem budget và loại chi phí phụ thuộc quyền và hỗ trợ ở scope |
| **Billing scope** | FinOps/kế toán theo dõi ngân sách theo cấu trúc thỏa thuận thanh toán | Cách đặt tên và quyền thay đổi theo loại billing account/agreement |

**Không cộng máy móc budget con vào budget cha.** Một subscription budget có thể bao gồm toàn bộ chi phí của resource group budget thuộc nó. Hai số tiền này là **hai mục tiêu quản trị** trên các phạm vi giao nhau, không phải hai khoản chi tiêu độc lập.

### 3.2. Chọn cấu trúc phạm vi trong một dự án

Giả sử hệ thống `orders` có ba môi trường và một nhóm platform dùng chung:

~~~mermaid
flowchart TB
    S["Subscription ứng dụng"] --> P["rg-orders-prod<br/>Budget: 8.000 USD/tháng"]
    S --> D["rg-orders-dev<br/>Budget: 1.200 USD/tháng"]
    S --> T["rg-orders-test<br/>Budget: 900 USD/tháng"]
    S --> O["rg-platform-shared<br/>Chi phí dùng chung"]
    S -. "Theo dõi tổng" .-> B["Subscription budget<br/>Có thể bao gồm tất cả nhóm trên"]
~~~

Nếu platform shared chứa Log Analytics workspace, DNS, firewall hoặc đường mạng chung, ngân sách của `rg-orders-dev` **không nhất thiết phản ánh đầy đủ tổng chi phí sở hữu** của môi trường phát triển. Cần một mô hình phân bổ chi phí dùng chung theo owner, đội, sản phẩm hoặc Cost Allocation phù hợp với dữ liệu tổ chức.

Một chiến lược dễ vận hành:

1. **Subscription budget** để theo dõi trần điều hành tổng thể và xu hướng.
2. **Budget theo môi trường/nhóm** để giao trách nhiệm xử lý.
3. **Báo cáo chia sẻ chi phí** cho networking, monitoring, backup hoặc dịch vụ dùng chung.
4. **Dự báo theo service/SKU** để giải thích thay đổi, không chỉ quan sát tổng tiền.

### 3.3. Tags và filters có giới hạn gì?

Tag như `costCenter`, `environment`, `application` hoặc `owner` giúp lọc/nhóm chi phí khi dữ liệu và resource hỗ trợ. Nhưng:

- Không phải mọi loại charge và tài nguyên đều có tag giống nhau hoặc kế thừa tag theo cách bạn mong đợi.
- Một số khoản chi phí ở billing scope, chi phí cam kết hoặc dịch vụ dùng chung có thể không ánh xạ hoàn toàn về một resource group/tag.
- Tạo tag hôm nay không nhất thiết cập nhật lại toàn bộ dữ liệu chi phí trong quá khứ.
- Bộ lọc của budget và giao diện/API hỗ trợ khác nhau theo scope hoặc điều khoản thanh toán.

Vì vậy, sau khi áp dụng tag filter, hãy **so sánh tổng chi phí được chọn với dữ liệu Cost Analysis** để tránh tạo budget theo dõi thiếu một phần khoản chi đáng kể.

## 4. Thiết kế số tiền budget trước khi thao tác trên Portal

Một ngưỡng không có cơ sở dữ liệu lịch sử hoặc kế hoạch tải thường gây cảnh báo quá sớm hoặc quá muộn. Đầu tiên xác định baseline theo dịch vụ và mức dùng dự kiến.

### 4.1. Ví dụ tính ngân sách hàng tháng

Một môi trường phát triển cho ứng dụng Azure dự kiến có chi phí:

| Hạng mục | Cách phát sinh | Dự kiến mỗi tháng |
| --- | --- | ---: |
| App Service / compute | Instance chạy theo giờ, autoscale | 480 USD |
| Database | SKU, storage, backup/IO | 280 USD |
| Storage và backup | GB lưu trữ, thao tác truy cập | 95 USD |
| Networking | Data transfer, public IP, gateway hoặc NAT | 110 USD |
| Azure Monitor / Log Analytics | Ingestion, retention, truy vấn được tính phí khi áp dụng | 135 USD |
| **Tổng baseline** | | **1.100 USD** |
| **Biên dự phòng ước lượng** | Thay đổi tải, ingest và các biến động khác | **100 USD** |
| **Budget mục tiêu** | | **1.200 USD/tháng** |

Từ budget 1.200 USD, chọn các mức thông báo:

| Ngưỡng | Giá trị tương ứng | Ý nghĩa xử lý |
| --- | ---: | --- |
| **Actual 60%** | 720 USD | Nhắc rà soát xu hướng và phân bổ |
| **Actual 80%** | 960 USD | Điều tra khoản chi lớn, cân nhắc tối ưu |
| **Actual 100%** | 1.200 USD | Kích hoạt quy trình quyết định về chi phí vượt mục tiêu |
| **Forecasted 100%** | Dự báo trên 1.200 USD | Phân tích sớm nguyên nhân dự báo vượt trước cuối kỳ |

Đây là **ngưỡng đề xuất trong ví dụ**, không phải chuẩn bắt buộc của Azure. Một workload phát triển có thể dùng mức 50/75/90, trong khi production có thể sử dụng ngưỡng theo quy mô và yêu cầu kinh doanh khác.

### 4.2. Cân nhắc tính mùa vụ, giá và doanh nghiệp

Cần tính đến:

- **Chi phí cố định hoặc cam kết:** các gói đặt trước hoặc phần chi không thể giảm tức thời.
- **Chi phí biến đổi:** lưu lượng, số lượng instance, dung lượng lưu trữ, hoạt động log và truy vấn.
- **Sự kiện sản phẩm:** chiến dịch, migration, thử tải, DR drill hoặc release lớn có thể tạo tải khác thường.
- **Mức tối thiểu an toàn:** không thể tùy tiện tắt database, backup, giám sát bảo mật hoặc hệ thống production chỉ vì chạm budget.
- **Tiền tệ và điều khoản:** budget nên được đặt cùng đơn vị tiền tệ được giao diện/billing scope hiển thị; không tự quy đổi từ hóa đơn bằng tỷ giá ước lượng.

Có thể đặt ngân sách bằng cách lấy trung bình vài tháng và cộng biên dự phòng, nhưng cần giải thích rõ chi phí nào phát sinh một lần và chi phí nào lặp lại. Mục tiêu là budget **có thể ra quyết định**, không chỉ là một con số tròn.

## 5. Chuẩn bị quyền và dữ liệu trước khi tạo budget

Đăng nhập Azure bằng tài khoản Entra ID được cấp quyền đúng tenant. Trước khi thay đổi, hãy xác minh:

1. **Subscription/billing scope:** account đang xem đúng nơi phát sinh chi phí.
2. **Quyền Cost Management:** vai trò đọc chi phí, tạo/sửa budget hoặc quyền billing phù hợp tại scope; khả năng xem chi phí có thể còn phụ thuộc các cài đặt của thỏa thuận thanh toán.
3. **Khoảng dữ liệu:** có đủ lịch sử và độ trễ chấp nhận được để đặt baseline không?
4. **Người nhận:** địa chỉ email nhóm còn hoạt động, Action Group đúng subscription/scope nếu dùng.
5. **Chủ sở hữu:** ai duyệt thay đổi amount, ai nhận cảnh báo, ai được quyền tối ưu tài nguyên.
6. **Đường escalation:** khi cost vượt mục tiêu thì xử lý qua ticket, chatops hay quy trình change?

Vai trò như **Cost Management Reader** thường phục vụ đọc dữ liệu, còn việc chỉnh budget cần quyền cao hơn tương ứng, chẳng hạn **Cost Management Contributor** tại scope được hỗ trợ. Quyền với billing scope có thể được quản lý bằng các billing roles riêng. Kiểm tra tính năng/entitlement cụ thể thay vì mặc định một vai trò đủ mọi nơi.

**Least privilege:** Người nhận email budget không nhất thiết cần quyền thay đổi VM, Azure SQL hay tài nguyên sản xuất. Người vận hành chịu trách nhiệm budget cũng không nên được cấp quyền Owner subscription chỉ để xem chi phí hoặc sửa thông báo.

## 6. Tạo budget bằng Azure Portal

Giao diện có thể thay đổi theo thời gian, nhưng luồng thực hiện về cơ bản gồm chọn scope, amount, chu kỳ và notification.

### Bước 1 — Mở đúng Cost Management scope

1. Đăng nhập **Azure Portal** và xác nhận tenant/subscription đang chọn.
2. Mở **Cost Management + Billing** hoặc mở **Cost Management** tại subscription/resource group mục tiêu.
3. Trong mục Cost Management, chọn **Budgets**.
4. Kiểm tra nhãn **scope** ở đầu màn hình. Nếu muốn budget chỉ cho `rg-orders-dev`, phải bảo đảm đang ở resource group đó hoặc đặt bộ lọc đúng cách được Portal hỗ trợ.

Đừng tạo một subscription-wide budget rồi mặc định nó chỉ tính resource group đang nhìn trên trang khác.

### Bước 2 — Đặt amount và thời gian

Ví dụ:

~~~text
Name:                 budget-rg-orders-dev
Scope:                Resource group rg-orders-dev
Budget period:        Monthly
Amount:               1200 (đơn vị tiền tệ hiển thị của tài khoản)
Start date:           2026-11-01
End date:             2027-10-31
Owner:                Nhóm Orders / Dev
~~~

`Monthly` nghĩa là ngưỡng 1.200 được xét theo chu kỳ tháng; khoảng start/end xác định thời gian hiệu lực. Khi chọn ngày, tuân theo giới hạn của giao diện và API về đầu kỳ, cuối kỳ, khoảng hiệu lực và timezone. Nếu màn hình hiển thị đơn vị tiền tệ khác USD, **điều chỉnh số tiền theo đơn vị thực**; không sao chép 1.200 một cách mù quáng.

### Bước 3 — Thêm filter nếu cần

Nếu scope đã là `rg-orders-dev`, thường không cần một filter `ResourceGroupName=rg-orders-dev` lặp lại. Chỉ thêm service/tag filter khi cần một budget cho nhóm chi phí con và chắc chắn dữ liệu có thể được phân loại đúng.

Kiểm tra kết quả chi phí được chọn ở phần biểu đồ/dữ liệu mà Portal hiển thị. Nếu một khoản mạng hoặc storage không nằm trong filter, budget có thể không bao phủ toàn bộ hoạt động của ứng dụng.

### Bước 4 — Thêm cảnh báo Actual

Định nghĩa notification cho chi phí thực tế đã ghi nhận trong chu kỳ:

| Tên quy tắc minh họa | Điều kiện | Người nhận |
| --- | --- | --- |
| `actual-60` | Actual vượt 60% budget | Email FinOps / owner |
| `actual-80` | Actual vượt 80% budget | Owner + nhóm vận hành |
| `actual-100` | Actual vượt 100% budget | Owner + người duyệt ngân sách |

Trong Portal, chọn loại **Actual** khi có tùy chọn, nhập threshold tương ứng và thêm **email recipients** hoặc Action Group được hỗ trợ. Kiểm tra rằng các ngưỡng có hiệu lực trên đúng scope và cùng amount.

### Bước 5 — Thêm cảnh báo Forecasted

Tạo một quy tắc **Forecasted 100%** nếu scope và giao diện hỗ trợ. Quy tắc này hữu ích khi tốc độ chi tiêu hiện tại cho thấy khả năng vượt budget dù actual chưa vượt.

Không phải mọi trường hợp đều có đủ dữ liệu để đưa ra forecast đáng tin cậy. Tùy scope và thời điểm trong chu kỳ, ngưỡng dự báo có thể chưa khả dụng hoặc kết quả thay đổi khi có thêm dữ liệu mới.

### Bước 6 — Lưu và kiểm tra

Sau khi lưu, quay lại danh sách budgets ở **chính scope đã chọn** và xác minh:

- Tên, amount, tiền tệ, chu kỳ và khoảng hiệu lực.
- Các filters, loại Actual/Forecasted, thresholds và danh sách người nhận.
- Người/chức năng có quyền bảo trì budget trong tương lai.
- Liên kết đến runbook và chủ sở hữu khi tổ chức có cơ chế tài liệu liên quan.

**Cảnh báo budget không phải cơ chế tức thời theo từng giao dịch hoặc từng phút.** Chi phí cần được đưa vào hệ thống billing/Cost Management, cập nhật và đánh giá ngưỡng; có độ trễ giữa việc dùng tài nguyên và thông báo. Không thiết kế phòng ngừa rủi ro mất tiền rất nhanh chỉ dựa vào budget alert.

## 7. Cảnh báo Actual và Forecasted hoạt động ra sao?

Giả sử budget 1.200 USD/tháng, cấu hình Actual 80%, Actual 100% và Forecasted 100%.

~~~mermaid
flowchart TD
    A["Dữ liệu cost cho scope + kỳ"] --> B["Tính actual / amount"]
    A --> C["Ước tính forecast / amount nếu hỗ trợ"]
    B --> D{"Actual > 80%?"}
    D -->|"Có"| E["Thông báo Actual 80%"]
    B --> F{"Actual > 100%?"}
    F -->|"Có"| G["Thông báo Actual 100%"]
    C --> H{"Forecasted > 100%?"}
    H -->|"Có"| I["Thông báo Forecasted 100%"]
    E --> J["Người nhận / Action Group"]
    G --> J
    I --> J
    J --> K["Runbook phân tích chi phí và quyết định"]
~~~

Sơ đồ mô tả **logic khái niệm**. Thời điểm đánh giá, ngưỡng chính xác, tần suất gửi thông báo và hành vi khi chi phí dao động do nền tảng quyết định. Khi triển khai thực, chọn toán tử ngưỡng theo UI/API (ví dụ **GreaterThan**) và kiểm tra bằng dữ liệu thực tế; không mặc định thông báo chỉ xuất hiện đúng một lần hay lập tức khi chi phí chạm con số tròn.

### 7.1. Minh họa theo từng mốc trong tháng

| Ngày giả định | Actual | Forecast | Nhận định |
| --- | ---: | ---: | --- |
| 05/11 | 220 USD | 1.050 USD | Chưa đạt ngưỡng Actual; dự báo trong mục tiêu |
| 12/11 | 525 USD | 1.270 USD | Có thể kích hoạt Forecasted 100% |
| 20/11 | 970 USD | 1.410 USD | Actual đã vượt 80%; Forecasted tiếp tục vượt |
| 28/11 | 1.230 USD | 1.260 USD | Actual đã vượt 100% |

Ví dụ chỉ minh họa. Vì dữ liệu có độ trễ và forecast biến động theo xu hướng, **ngày thực tế nhận thông báo có thể khác** với ngày một phép tính đơn giản cho thấy ngưỡng bị vượt.

### 7.2. Vì sao một alert có thể không đến?

Có nhiều nguyên nhân cần kiểm tra:

- Budget đặt sai scope hoặc filter làm mất các khoản chi cần theo dõi.
- Đơn vị tiền tệ/amount hoặc thời gian hiệu lực không đúng.
- Chưa đến thời điểm hệ thống cập nhật dữ liệu cost và đánh giá ngưỡng.
- Quy tắc notification bị tắt, người nhận sai địa chỉ hoặc email vào spam/quarantine.
- Action Group bị thay đổi, kênh nhận yêu cầu xác thực hoặc cấu hình không hoạt động.
- Không có forecast/threshold type tại scope hiện tại, hoặc điều kiện forecast chưa được đáp ứng.
- Người dùng đang quan sát biểu đồ Cost Analysis theo cách hiển thị khác budget.

**Cách xử lý:** Đầu tiên xác minh budget tồn tại và điều kiện đã đạt dựa trên cùng dữ liệu scope/kỳ; sau đó kiểm tra cấu hình người nhận và Action Group. Nếu vẫn bất thường, lưu ảnh cấu hình đã che thông tin nhạy cảm, timestamp UTC và mô tả khoảng dữ liệu để điều tra/escalate.

## 8. Email notifications và Azure Monitor Action Groups

### 8.1. Email trực tiếp

Email phù hợp để thông báo cho FinOps, owner hoặc một mailing list của nhóm. Nên ưu tiên **địa chỉ nhóm có người phụ trách** hơn một cá nhân có thể thay đổi vị trí hoặc nghỉ phép. Khi owner chuyển việc, cần có quy trình kiểm tra danh sách người nhận.

Một email cảnh báo nên dẫn người vận hành đến Cost Analysis, scope budget và runbook. Nếu hệ thống không hỗ trợ tùy biến đầy đủ nội dung email do Azure phát ra, hãy đặt tên budget dễ hiểu và duy trì đường dẫn tài liệu nội bộ.

### 8.2. Action Groups

**Azure Monitor Action Groups** có thể cung cấp các kênh nhận thông báo và cơ chế tích hợp workflow được Azure hỗ trợ. Khi được phép ở budget scope, có thể liên kết Action Group để:

- Gửi thông báo đến danh sách người nhận thích hợp.
- Kích hoạt webhook, Logic Apps hoặc workflow theo chính sách tổ chức.
- Chuyển thông tin cảnh báo vào incident/ticket system.
- Yêu cầu người trực phân tích và phê duyệt một thay đổi tiết kiệm chi phí.

Không phải mọi loại Action Group action đều phù hợp mọi bài toán hoặc mọi gói tài khoản. Cần kiểm tra chính xác loại action được giao diện budget cho phép, quyền truy cập và dữ liệu payload trước khi cấu hình. Đường tự động hóa gửi thông báo đến hệ thống ngoài Azure có thể cần xác thực, retry và cơ chế chống gửi trùng.

### 8.3. Budget không tự dừng tài nguyên

Ngưỡng 100% **không tự động thực thi**:

- Dừng App Service hay VM.
- Xóa database, disk, backup hoặc snapshot.
- Từ chối request của khách hàng.
- Ngăn phát sinh chi phí ở resource mới.
- Khóa subscription trên mọi loại tài khoản.

Một số chương trình/subscription có cơ chế **spending limit** riêng, nhưng không nên nhầm với Azure Cost Management budget. Nếu muốn thực thi guardrail, hãy thiết kế **Azure Policy**, quy trình duyệt provisioning, quota, RBAC, autoscale giới hạn hoặc automation có điều kiện phù hợp. Không tự động xóa/dừng tài nguyên production chỉ vì budget alert.

## 9. Triển khai budget bằng Bicep

Khai báo ngân sách bằng IaC giúp có phiên bản, review thay đổi, nhất quán giữa môi trường và dễ khôi phục cấu hình. Azure Resource Manager cung cấp loại tài nguyên **Microsoft.Consumption/budgets** tại các scope được hỗ trợ.

**Ví dụ độc lập:** File `budget.bicep` triển khai **tại resource group** `rg-orders-dev`. Nó tạo budget theo chu kỳ tháng ở scope của deployment. Các tên, thời gian, amount và địa chỉ email là tham số; phải thay theo tổ chức và kiểm tra API version, tính năng được hỗ trợ trước khi chạy.

~~~bicep
targetScope = 'resourceGroup'

@description('Tên ngân sách trong resource group nhận deployment.')
param budgetName string = 'budget-rg-orders-dev'

@description('Ngân sách theo đơn vị tiền tệ của scope billing.')
@minValue(1)
param budgetAmount int = 1200

@description('Ngày bắt đầu, dùng đầu chu kỳ: YYYY-MM-DDT00:00:00Z.')
param budgetStartDate string

@description('Ngày kết thúc hiệu lực theo định dạng ISO 8601 UTC.')
param budgetEndDate string

@description('Email nhóm chịu trách nhiệm theo dõi ngân sách.')
param notificationEmail string

resource monthlyBudget 'Microsoft.Consumption/budgets@2023-05-01' = {
  name: budgetName
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: budgetStartDate
      endDate: budgetEndDate
    }
    notifications: {
      actual80: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 80
        thresholdType: 'Actual'
        contactEmails: [
          notificationEmail
        ]
      }
      actual100: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        thresholdType: 'Actual'
        contactEmails: [
          notificationEmail
        ]
      }
      forecast100: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: [
          notificationEmail
        ]
      }
    }
  }
}

output configuredBudgetName string = monthlyBudget.name
~~~

Ở các phiên bản API hoặc scope khác, schema, trường hỗ trợ và giới hạn notification có thể khác; hãy đối chiếu template với resource provider và phần validate trên tài khoản thực. Đây là **ví dụ cấu hình**, không khẳng định mọi billing scope hỗ trợ giống nhau.

### 9.1. Các điểm cần hiểu trong template

- `targetScope = 'resourceGroup'` gắn ngân sách với resource group được chọn khi deployment.
- `category: 'Cost'` xác định ngân sách theo chi phí, không phải budget dùng để giới hạn số resource.
- `amount` là số tiền tuyệt đối của mỗi chu kỳ theo currency được scope sử dụng.
- `timeGrain: 'Monthly'` điều khiển chu kỳ, khác với `timePeriod` là thời hạn tồn tại.
- `notifications` gồm ba quy tắc riêng: hai Actual và một Forecasted.
- `contactEmails` là email nhận cảnh báo, không phải địa chỉ của Microsoft Support.
- `operator: 'GreaterThan'` là điều kiện *vượt* tỷ lệ. Nếu quy tắc muốn bao gồm đúng giá trị ngưỡng, cần kiểm tra toán tử được API hỗ trợ và chính sách mong muốn.

### 9.2. Kiểm tra template và triển khai có kiểm soát

Sau khi xác nhận đúng subscription và tạo sẵn resource group mục tiêu, sử dụng những lệnh CLI minh họa:

~~~bash
az account show --query "{subscription:id,tenant:tenantId}" -o json

az deployment group validate \
  --resource-group rg-orders-dev \
  --template-file budget.bicep \
  --parameters \
    budgetAmount=1200 \
    budgetStartDate=2026-11-01T00:00:00Z \
    budgetEndDate=2027-10-31T00:00:00Z \
    notificationEmail=finops@example.com

# Chỉ triển khai sau khi validate, scope và quyền đã được kiểm tra.
az deployment group create \
  --resource-group rg-orders-dev \
  --template-file budget.bicep \
  --parameters \
    budgetAmount=1200 \
    budgetStartDate=2026-11-01T00:00:00Z \
    budgetEndDate=2027-10-31T00:00:00Z \
    notificationEmail=finops@example.com
~~~

Các lệnh sử dụng dấu xuống dòng kiểu shell `bash`. Trên PowerShell, điều chỉnh cách xuống dòng phù hợp hoặc nhập một dòng. `finops@example.com` là địa chỉ **minh họa**, không phải địa chỉ cần gửi thông báo trong môi trường thật. Các ngày minh họa phù hợp với bài tập tại thời điểm tháng 11/2026; khi dùng ở kỳ khác, hãy chọn thời gian phù hợp với quy tắc thời gian của budget.

Sau khi triển khai, quay lại Azure Portal ở scope `rg-orders-dev` để **đối chiếu tên, amount, effective period, thresholds và recipients**. Validation template và deployment thành công chưa chứng minh email đến được người nhận hoặc dữ liệu cost sẽ được cập nhật tức thời.

### 9.3. Khi nào dùng Bicep, Portal hay automation?

| Cách tạo | Ưu điểm | Cần chú ý |
| --- | --- | --- |
| **Azure Portal** | Dễ quan sát scope, bảng cost và cấu hình notification | Cấu hình thủ công có thể lệch giữa môi trường |
| **Bicep/ARM** | Version control, review, triển khai lặp lại, đặt chính sách tham số | Cần quản lý API version, quyền và quy tắc time period |
| **REST/API/SDK** | Phù hợp quản lý nhiều budget và tích hợp nền tảng quản trị | Xác thực, retry, rate limit và drift |
| **FinOps reporting** | Tổng hợp nhiều scope, giải thích chênh lệch và xu hướng | Phải giữ nhất quán nguồn dữ liệu, filter và cost type |

Không nên biến mọi thay đổi số tiền budget thành chỉnh sửa thủ công không có lịch sử. Với hệ thống quan trọng, thay đổi amount hoặc người nhận nên đi qua review tương tự thay đổi IaC khác.

## 10. Runbook phản ứng với cảnh báo chi phí

Budget alert sẽ hữu ích hơn khi đi kèm quy trình điều tra và hành động theo ngưỡng. Mẫu sau thiết kế cho môi trường `orders-dev` với budget tháng 1.200 USD.

### 10.1. Quy trình chung

~~~mermaid
flowchart TD
    A["Nhận cảnh báo Actual / Forecasted"] --> B["Xác minh scope, ngày, tiền tệ, threshold"]
    B --> C["Mở Cost Analysis cùng scope và kỳ"]
    C --> D["Nhóm theo service / resource / tag"]
    D --> E["Đối chiếu deployment, scaling, logs, traffic"]
    E --> F{"Tăng chi phí có dự kiến và được duyệt?"}
    F -->|"Có"| G["Ghi nhận lý do, điều chỉnh forecast / ngân sách theo quyền"]
    F -->|"Không hoặc chưa rõ"| H["Chọn biện pháp tối ưu an toàn"]
    H --> I["Review tác động, phê duyệt, triển khai thay đổi"]
    I --> J["Theo dõi chi phí và SLO sau thay đổi"]
    G --> J
    J --> K["Lưu bằng chứng và cập nhật kế hoạch"]
~~~

**Bước 1 — Xác nhận thông báo.** Đọc tên budget, scope, kỳ tháng, amount, loại Actual/Forecasted và ngưỡng. Ghi timestamp UTC khi nhận và người phụ trách. Nếu email không rõ scope, vào Portal để xác minh trước khi thao tác.

**Bước 2 — Xem phân rã chi phí.** Trong Cost Analysis, chọn cùng scope và khoảng thời gian; phân tích theo service, resource, resource group, tag và chi phí hàng ngày. Đối chiếu chi phí đang tăng với baseline và kế hoạch sự kiện.

**Bước 3 — Kiểm tra thay đổi.** Dò scale-out, SKU upgrade, database throughput, snapshot, storage replication, outbound traffic, Log Analytics ingestion/retention và tài nguyên test chưa cleanup. Đối chiếu với Activity Log hoặc pipeline để tìm nguyên nhân.

**Bước 4 — Quyết định.** Phân loại chi phí: phát sinh có kế hoạch, vượt bất thường, sai phân bổ, thiếu tag, do thay đổi kỹ thuật hoặc do báo cáo chậm/điều chỉnh billing.

**Bước 5 — Thực hiện tối ưu khi an toàn.** Điều chỉnh auto-shutdown dev VM, lịch scale, log retention, lưu trữ không dùng, kích cỡ workload và quota khi được duyệt. Không dừng replication, backup, key management, security monitoring hoặc production resource mà chưa đánh giá SLO, RTO/RPO và chính sách tổ chức.

**Bước 6 — Xác minh.** Theo dõi xu hướng cost sau khi dữ liệu mới xuất hiện và xác minh các metric ứng dụng, bảo mật, throughput hoặc availability. Một tối ưu chi phí gây downtime nghiêm trọng không được xem là thành công.

### 10.2. Trách nhiệm theo ngưỡng

| Cảnh báo | Người xử lý chính | Kiểm tra ưu tiên | Đầu ra |
| --- | --- | --- | --- |
| Actual 60% | Service owner | Chi phí lũy kế và nhịp dùng so với số ngày còn lại | Ghi trạng thái, nhận định |
| Actual 80% | Owner + FinOps | Cost driver lớn, các thay đổi gần đây | Ticket có hành động và người phụ trách |
| Forecasted 100% | Owner + người duyệt ngân sách | Dự báo, tải kế hoạch, chi phí không linh hoạt | Phương án tối ưu hoặc duyệt tăng budget |
| Actual 100% | FinOps + chủ trách nhiệm kinh doanh | Phần vượt, nghĩa vụ sản xuất, rủi ro vận hành | Quyết định ngân sách và kế hoạch xử lý |
| Biến động bất thường dù dưới ngưỡng | SRE/FinOps | Cost anomaly, tài nguyên không dự kiến | Điều tra ngắn, chặn tăng trưởng không kiểm soát |

Mức độ quan trọng không chỉ do tỷ lệ phần trăm. Một budget rất nhỏ có thể vượt 100% mà tác động tài chính thấp, trong khi sự tăng chi phí bất thường nhanh ở budget lớn cần xử lý dù mới 50%. Vì vậy kết hợp **absolute amount**, tốc độ tăng, forecast và rủi ro kỹ thuật.

## 11. Tình huống thực tế: Log Analytics làm tăng chi phí

**Bối cảnh:** Nhóm `orders-dev` có budget 1.200 USD/tháng. Sau release, nhóm bật debug logs ở nhiều service và gửi nhiều event vào Log Analytics. Forecast tăng lên 1.500 USD, mặc dù actual hiện tại mới 780 USD.

### 11.1. Câu hỏi điều tra

1. Budget áp dụng cho resource group nào? Chi phí Log Analytics workspace nằm trong resource group đó hay thuộc nền tảng dùng chung?
2. Chi phí tăng ở dịch vụ **Azure Monitor/Log Analytics** hay compute/network? Có data transfer hoặc App Insights ingestion liên quan không?
3. Log volume thay đổi từ phiên bản nào và từ ngày nào?
4. Có hoạt động hợp lệ như DR drill, performance test hoặc incident investigation cần giữ log nhiều hơn không?
5. Nếu giảm sampling/retention, có ảnh hưởng yêu cầu giám sát bảo mật, tuân thủ và khả năng điều tra sự cố không?

### 11.2. Hành động phù hợp

Ví dụ hướng xử lý, tùy chính sách:

- Loại bỏ log mức debug thừa tại môi trường dev sau khi hoàn tất điều tra.
- Thêm filter/sampling ở nguồn phát log nếu có hỗ trợ và đảm bảo không làm mất telemetry quan trọng.
- Đánh giá retention theo loại log, phân biệt log phải lưu dài hạn với log phục vụ debug.
- Thiết lập review log ingestion sau mỗi release và yêu cầu owner xác nhận khi thay đổi telemetry đáng kể.
- So sánh forecast trước/sau ít nhất một lần dữ liệu được cập nhật; không kỳ vọng chi phí giảm ngay trong đồ thị cùng ngày.

**Không nên** tắt toàn bộ Azure Monitor, audit log hoặc log phục vụ phát hiện xâm nhập chỉ để đạt budget. Biện pháp phải giữ các yêu cầu an toàn, điều tra sự cố và compliance.

## 12. Tình huống thực tế: VM test chạy ngoài giờ và không được dọn

**Bối cảnh:** Môi trường thử tải chạy VM và managed disks qua nhiều ngày sau khi bài test kết thúc. Actual vượt 80%, cost driver là compute và disk.

Hướng điều tra:

- Liệt kê tài nguyên tạo mới theo resource group, tag `owner`/`exercise`, thời gian triển khai và lịch test.
- Xác nhận VM có đang phục vụ người dùng hoặc tác vụ batch quan trọng không; đừng giả định tên `test` đồng nghĩa vô hại.
- Xác định stop VM theo cơ chế nào: **guest shutdown** có thể không đồng nghĩa **deallocate** để ngừng phần compute billing. Managed disks, public IP hoặc storage có thể vẫn phát sinh chi phí sau khi VM ngừng.
- Kiểm tra snapshots, unattached disks, retained resources và storage trước khi yêu cầu xóa.
- Với VM dev có lịch làm việc rõ ràng, thiết kế auto-shutdown hoặc lịch tự động trong giới hạn quản trị; đo tác động lên trải nghiệm và yêu cầu backup.

Ví dụ: tắt VM có thể giảm chi phí compute sau khi VM được deallocated, nhưng không làm biến mất mọi khoản chi liên quan. Cần xác minh lại Cost Analysis sau kỳ dữ liệu mới để biết hiệu quả thật.

## 13. Tự động hóa theo Action Group: nên làm tới đâu?

Có thể dùng Action Group kết nối workflow để mở ticket hoặc yêu cầu phê duyệt. Cấu trúc hợp lý:

~~~mermaid
flowchart LR
    B["Budget notification"] --> AG["Action Group / workflow"]
    AG --> T["Tạo ticket chi phí"]
    T --> O["Owner xem Cost Analysis"]
    O --> P{"Phê duyệt phương án?"}
    P -->|"Có"| C["Automation thay đổi tài nguyên có kiểm soát"]
    P -->|"Không"| R["Ghi nhận ngoại lệ / tăng ngân sách có duyệt"]
    C --> V["Xác minh SLO, bảo mật và chi phí"]
    R --> V
~~~

**Chống lỗi khi tự động hóa:**

- Kiểm tra payload, scope và danh tính nguồn; đừng tin request không được xác thực.
- Dùng identity với quyền tối thiểu, không đặt client secret trong source code hoặc webhook URL công khai.
- Có **idempotency** để cùng một alert không tạo hàng chục ticket hoặc lặp lại thao tác nguy hiểm.
- Thao tác chỉ đọc (tạo báo cáo, ticket) có thể tự động hóa trước; hành động thay đổi production cần điều kiện và quyền duyệt phù hợp.
- Lưu audit trail: alert nào dẫn đến quyết định nào, ai duyệt, automation đã làm gì, thành công/thất bại thế nào.
- Có rollback cho thay đổi về SKU/scale; đánh giá tác động tới độ sẵn sàng, backup và dữ liệu.

**Ví dụ phản mẫu:** “Nếu budget 100% thì xóa cả resource group” là một quy tắc gây mất dữ liệu và không phù hợp với yêu cầu availability. Thay bằng cảnh báo, điều tra và phương án tối ưu được duyệt.

## 14. Kiểm tra budget và quy tắc thông báo sau khi thiết lập

Một budget được tạo thành công vẫn có thể không phục vụ mục tiêu nếu scope sai hoặc người nhận không có hành động.

### 14.1. Checklist nghiệm thu

| Kiểm tra | Bằng chứng cần có |
| --- | --- |
| Scope | Tên subscription/resource group hoặc billing scope đúng |
| Amount và currency | Số tiền tương ứng kế hoạch và đơn vị tiền tệ của tài khoản |
| Kỳ và hiệu lực | Monthly và các mốc ngày hợp lệ |
| Filters | Cost Analysis cùng scope cho kết quả đúng phạm vi chi phí |
| Actual notifications | Threshold và operator đúng, quy tắc enabled |
| Forecasted notification | Có và dùng được tại scope/tài khoản đã chọn |
| Recipients | Mailing list hoạt động; owner được xác nhận |
| Action Group nếu dùng | Kênh và quyền kết nối phù hợp, có kiểm tra cấu hình |
| Quyền duy trì | Có người đủ quyền cập nhật và có review process |
| Runbook | Có hướng dẫn xử lý và escalation với owner rõ ràng |

### 14.2. Kiểm tra đường gửi mà không cần gây phát sinh chi phí

Tạo budget thử nghiệm ở scope/môi trường phù hợp, dùng người nhận thử nghiệm và **quy trình kiểm tra thông báo của dịch vụ/kênh nhận** nếu có. Có thể thử riêng Action Group bằng chức năng test được Azure hỗ trợ, nhưng bài test đó chỉ chứng minh kênh Action Group, **không đảm bảo toàn bộ quá trình đánh giá Cost Management budget** đã được kích hoạt.

Không nên cố tạo một khoản chi lớn chỉ để thử alert. Nếu chọn một threshold thử nghiệm dựa trên cost hiện có, phải chấp nhận dữ liệu cập nhật và quy tắc kích hoạt có thể khiến alert không đến ngay, và không nên xem điều này là lỗi chắc chắn của hệ thống.

### 14.3. Kiểm tra việc gửi thông báo

Nếu không thấy email:

1. Xác minh budget còn hiệu lực, đúng scope và có đủ dữ liệu để vượt threshold được chọn.
2. Kiểm tra quy tắc enabled, threshold type, operator và người nhận.
3. Kiểm tra Action Group, inbox, spam/quarantine và mailing list.
4. Chờ chu kỳ cập nhật dữ liệu chi phí phù hợp, đối chiếu mốc UTC đã ghi.
5. Ghi lại cấu hình, khoản chi actual/forecast, thời điểm, dấu hiệu đã thử; escalate qua Azure Support khi có bằng chứng tính năng không hoạt động như mong đợi.

Đừng suy đoán thời gian xử lý chính xác của notification nếu tài liệu/dịch vụ không cam kết. Chi phí của một số resource có thể xuất hiện muộn hoặc điều chỉnh sau đó.

## 15. Lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Budget không hiển thị ở trang đang xem | Đang ở sai subscription, resource group hoặc billing scope | Chọn lại scope và quyền, kiểm tra nơi tạo |
| Không tạo/sửa được budget | Thiếu quyền tại scope; billing policy hoặc entitlement khác | Kiểm tra role và quyền Cost Management/billing tương ứng |
| Forecasted alert không có/không kích hoạt | Scope, API hoặc dữ liệu dự báo không hỗ trợ trường hợp hiện tại | Kiểm tra tính năng tại scope và chọn điều kiện phù hợp |
| Email không đến | Sai recipient, bị chặn hoặc chi phí chưa được đánh giá đến ngưỡng | Kiểm tra cấu hình, cập nhật dữ liệu và kênh gửi |
| Budget 80% nhưng billing chart khác số | Khác kỳ, filter, cost type hoặc độ trễ/điều chỉnh | Đối chiếu cùng scope, tiền tệ, cách tính và timestamp |
| Tag budget thiếu chi phí | Resource chưa có tag, charge không gắn tag hoặc dữ liệu lịch sử | Rà soát phân bổ và giới hạn dữ liệu |
| Vượt 100% nhưng resource vẫn chạy | Budget chỉ cảnh báo | Dùng runbook và guardrail riêng nếu cần |
| Tự động tắt tài nguyên gây downtime | Automation thiếu phê duyệt và kiểm tra phụ thuộc | Bổ sung approval, allowlist, rollback và SLO |
| Cost tăng dù VM đã Stop | VM chưa deallocate hoặc disk/network còn tính phí | Kiểm tra trạng thái và từng meter |
| Budget gây nhiều thông báo nhưng không có phản ứng | Thiếu owner, ưu tiên và hành động theo ngưỡng | Gắn runbook, ticket và lịch review |
| Budget resource group không phản ánh tổng ứng dụng | Chi phí dùng chung nằm ngoài scope | Thiết kế chargeback/showback riêng |

## 16. Bài thực hành tổng hợp: tạo ngân sách cho ứng dụng Azure

**Bối cảnh:** Công ty triển khai `orders-dev` gồm App Service, Azure SQL, Storage, VNet, Log Analytics và dịch vụ dữ liệu dùng chung. Đội phát triển chịu trách nhiệm giới hạn **1.200 USD/tháng** trong phạm vi có thể kiểm soát, và FinOps cần nhận được cảnh báo khi tăng chi phí.

### Nhiệm vụ A — Xác định scope và baseline

1. Chọn resource group `rg-orders-dev` làm budget trực tiếp cho các tài nguyên thuộc môi trường; xác định những dịch vụ dùng chung nằm ngoài scope.
2. Từ Cost Analysis, lập bảng chi phí dự kiến cho compute, dữ liệu, storage, network và monitoring; so với lịch sử và sự kiện dự kiến.
3. Quyết định có cần subscription-level budget để bao phủ phần chi phí dùng chung hay không.
4. Ghi chủ sở hữu, phương pháp phân bổ, đơn vị tiền tệ và hạn chế dữ liệu.

**Đầu ra:** Bảng scope → owner → cost driver → budget target, kèm giải thích các khoản chưa được budget theo dõi.

### Nhiệm vụ B — Tạo budget và notifications

Tại Azure Portal hoặc một resource group thử được phép:

~~~text
Budget name: budget-rg-orders-dev
Period:      Monthly
Amount:      1.200 (currency hiển thị)
Actual:      60%, 80%, 100%
Forecasted:  100% nếu hỗ trợ
Recipients:  Nhóm vận hành và FinOps được duyệt
Time period: Từ đầu tháng hiện tại đến thời điểm hết hiệu lực phù hợp
~~~

Sau khi lưu, kiểm tra lại cấu hình ở đúng scope. Nếu dùng Bicep, điều chỉnh ví dụ mục 9, bảo đảm tất cả tham số, ngày và địa chỉ nhận phù hợp. Không dùng email cá nhân tùy tiện hoặc người nhận chưa được chủ sở hữu xác nhận.

### Nhiệm vụ C — Giả lập cảnh báo mà không phát sinh chi phí thật

Giả sử đến ngày 20 actual là 970 USD, forecast 1.410 USD. Xác định:

- Những ngưỡng Actual nào đã vượt và threshold nào chưa vượt?
- Forecasted 100% có cảnh báo hợp lý không?
- Owner cần phân tích khoản chi nào trước và phải thông báo ai?
- Nếu hóa đơn cuối kỳ khác forecast, cần kiểm tra các điểm nào?

**Đáp án định hướng:** Actual đã vượt 60% và 80%, chưa vượt 100%. Forecast dự kiến vượt 100%. Cần kiểm tra cost driver theo service/resource, thay đổi SKU/log ingest, phạm vi/tài khoản, phương pháp tính và thời điểm dữ liệu; sau đó chọn hành động an toàn.

### Nhiệm vụ D — Viết runbook cho cảnh báo 80%

Tạo một checklist ngắn gồm người nhận, mục tiêu phản ứng, đường dẫn Cost Analysis, cách đối chiếu scope/currency, bằng chứng từ deployment, các biện pháp tối ưu phù hợp, quyền duyệt và tiêu chí xác minh. Giả định phát hiện một VM thử tải chạy ngoài giờ: ghi rõ kiểm tra tính cần thiết, deallocate khi được duyệt và theo dõi disk/network còn phát sinh chi phí.

### Nhiệm vụ E — Đánh giá kết quả và tài liệu hóa

Nộp:

| Hạng mục | Nội dung yêu cầu |
| --- | --- |
| Cấu hình ngân sách | Scope, amount, currency, dates, time grain |
| Các cảnh báo | Actual/Forecasted, thresholds, recipients |
| Nguồn dữ liệu | Cost Analysis và những filter được áp dụng |
| Quyền | Người có quyền đọc/sửa, owner và quy trình review |
| Runbook | Điều kiện xác minh, điều tra, tối ưu, phê duyệt |
| Bằng chứng | Ảnh cấu hình đã ẩn thông tin nhạy cảm, mô tả logic kiểm tra |
| Rủi ro còn lại | Delay cost, chi phí dùng chung, khoản chưa gắn tag, biến động forecast |

**Tiêu chí đạt:** Budget được thiết lập ở đúng phạm vi, có ít nhất hai mức cảnh báo Actual và một dự báo nếu khả dụng, có chủ sở hữu được chỉ định, có hướng xử lý khi vượt ngưỡng và chứng minh hiểu rằng budget không giới hạn chi tiêu tự động.

## 17. Vận hành và rà soát budget dài hạn

Một budget có thể đúng ở thời điểm tạo nhưng trở nên không phù hợp sau khi ứng dụng mở rộng, đổi SKU hoặc chuyển cấu trúc subscription. Nên có nhịp rà soát:

- **Hàng tuần hoặc theo mức rủi ro:** xem actual, forecast, top cost drivers và cảnh báo chưa có owner.
- **Hàng tháng:** so budget với số tiền ghi nhận, giải thích sai lệch, cập nhật kế hoạch workload và tài nguyên không dùng.
- **Khi triển khai thay đổi lớn:** đánh giá chi phí dự kiến của database tier, autoscale, logging, DR, network và storage replication.
- **Khi tái cấu trúc tài nguyên:** kiểm tra scope, filters, tags, quyền và recipients.
- **Khi có incident chi phí:** lưu timeline, phân tích nguyên nhân, hành động khắc phục và điều kiện xác minh.

Các chỉ số nên theo dõi gồm tỷ lệ budget đang có owner, tỷ lệ cảnh báo được phản hồi, độ lệch forecast so thực tế, thời gian phát hiện tăng chi phí, tỷ lệ khoản chi chưa phân bổ và giá trị tiết kiệm sau thay đổi đã được kiểm chứng.

Nếu một alert liên tục gây nhiễu vì threshold quá thấp hoặc không có người xử lý, hãy điều chỉnh dựa trên dữ liệu; đừng tắt nó mà không có phương án quan sát khác.

## 18. Những nguyên tắc cần ghi nhớ

1. **Budget là công cụ cảnh báo**, không phải cơ chế tự dừng chi phí. Mọi biện pháp chặn hoặc thay đổi tài nguyên cần chính sách và quy trình riêng.
2. **Scope đúng quyết định giá trị của ngân sách**: subscription, resource group và billing scope phản ánh các trách nhiệm chi phí khác nhau.
3. **Actual và Forecasted bổ sung cho nhau**: Actual cho biết mức đã ghi nhận, Forecasted giúp dự đoán nguy cơ vượt trong kỳ nếu có dữ liệu phù hợp.
4. **Chi phí Azure có độ trễ và phương pháp tính khác nhau**: so cùng scope, thời gian, loại chi phí, tiền tệ và filter trước khi kết luận.
5. **Thông báo phải có người chịu trách nhiệm**: email hoặc Action Group chỉ hữu ích nếu dẫn tới runbook điều tra, tối ưu có kiểm soát và xác minh kết quả.
6. **IaC giúp cấu hình lặp lại và kiểm soát thay đổi**: Bicep cho phép khai báo amount, kỳ, thresholds và recipients, nhưng cần validate theo API và quyền tại scope triển khai.
7. **Không hy sinh độ tin cậy và bảo mật để giảm cost tức thời**: một thay đổi làm mất dữ liệu, backup hoặc SLO có thể gây thiệt hại lớn hơn khoản tiết kiệm.

Thiết lập budget và cảnh báo chi phí đúng cách giúp đội phát triển, vận hành và FinOps nhận biết sớm xu hướng sử dụng Azure, phân chia trách nhiệm rõ ràng và duy trì kiến trúc ứng dụng phù hợp cả với nhu cầu hiệu năng, bảo mật lẫn khả năng chi trả.
