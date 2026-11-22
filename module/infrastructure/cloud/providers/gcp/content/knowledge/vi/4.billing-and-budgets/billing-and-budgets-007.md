# Cloud Billing Reports và phân tích Cost table

> **Chương:** Thanh toán và ngân sách  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

Khi hệ thống chạy trên Google Cloud, biết một VM, dịch vụ Cloud Run hoặc cụm GKE hoạt động ổn định là chưa đủ: đội ngũ còn phải biết **chi phí đang phát sinh ở đâu, vì sao thay đổi, đơn vị nào chịu trách nhiệm, và số liệu vận hành liên hệ thế nào với hóa đơn**. Hai công cụ cơ bản trong Google Cloud console là **Cloud Billing Reports** và **Cost table**.

Bài học tập trung vào cách **đọc, lọc, nhóm, so sánh, giải thích và đối soát chi phí** bằng hai công cụ này. Đây là kỹ năng nền để thiết lập ngân sách, giám sát chi phí và ra quyết định về kiến trúc Compute Engine, GKE, Cloud Run, lưu trữ, database và mạng.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Nêu được mục đích và ranh giới giữa **Billing Reports**, **Cost table**, hóa đơn/statement và **Cloud Billing export to BigQuery**.
2. Chọn đúng cách xem thời gian: **Charge period (trước đây là Usage date)** hoặc **Billing period (trước đây là Invoice month)**.
3. Dùng các chiều **Project, Service, SKU, Location, Label** và bộ lọc để xác định nguồn phát sinh chi phí.
4. Phân biệt **list cost, usage cost, savings/credits, taxes, adjustments, rounding** và tổng tiền trên hóa đơn.
5. Đối soát số liệu của Cost table với một invoice/statement, giải thích được những chênh lệch thường gặp.
6. Xây dựng một quy trình điều tra tăng chi phí, phân bổ chi phí theo nhóm và lập báo cáo FinOps có thể kiểm chứng.

## 1. Bức tranh tổng thể: chi phí đi từ tài nguyên đến hóa đơn

Tài nguyên được tạo trong **project**; project liên kết với một **Cloud Billing account** để ghi nhận chi phí sử dụng các dịch vụ có tính phí. Một billing account có thể thanh toán cho nhiều project. Ngược lại, cấu trúc **organization/folder/project** phục vụ quản trị tài nguyên và không đồng nghĩa với cách chia hóa đơn.

~~~mermaid
flowchart TD
    O["Organization / Folder"] --> P1["Project: shop-dev"]
    O --> P2["Project: shop-prod"]
    O --> P3["Project: analytics"]
    P1 --> R1["Cloud Run / Storage"]
    P2 --> R2["GKE / Cloud SQL"]
    P3 --> R3["BigQuery"]
    B["Cloud Billing account"] -. "Liên kết thanh toán" .-> P1
    B -. "Liên kết thanh toán" .-> P2
    B -. "Liên kết thanh toán" .-> P3
    B --> REP["Billing Reports: xu hướng và cơ cấu"]
    B --> COST["Cost table: chi tiết kỳ hóa đơn"]
    B --> EXP["BigQuery export: phân tích tùy chỉnh"]
    B --> DOC["Invoice / Statement"]
~~~

Điều cần phân biệt:

- **Project ID** giúp xác định nguồn tiêu thụ tài nguyên nhưng không phải mã hóa đơn.
- **Billing account** là phạm vi liên kết chi phí; quyền xem chi phí trên từng project có thể khác quyền xem toàn bộ billing account.
- **Service** là danh mục dịch vụ như Compute Engine, Cloud Storage hoặc Cloud Run.
- **SKU** là đơn vị mô tả loại sử dụng được tính giá trong một dịch vụ; ví dụ một loại năng lực tính toán, lưu lượng mạng hoặc lưu trữ. Cùng một service có thể phát sinh rất nhiều SKU.
- **Invoice/statement** là chứng từ thanh toán của kỳ, có thể bao gồm tiền sử dụng, chiết khấu, tín dụng, điều chỉnh, thuế và làm tròn theo cấu hình tài khoản.

Vì thế, cùng một ứng dụng có thể có chi phí ở **nhiều project, nhiều service và nhiều SKU**. Ví dụ API trên Cloud Run có thể phát sinh phí thực thi, truy cập Cloud SQL, Cloud Storage, log và lưu lượng mạng. Để tối ưu đúng nguyên nhân, không thể chỉ đọc một con số tổng.

## 2. Chọn đúng công cụ trước khi phân tích

| Câu hỏi | Công cụ phù hợp | Lý do |
|---|---|---|
| Chi phí đang tăng ở ngày nào, dịch vụ nào? | **Billing Reports** | Có biểu đồ theo thời gian, bộ lọc và nhóm theo service/project/SKU |
| Project nào tốn kém nhất trong tháng? | **Billing Reports** | So sánh tổng, chọn thời gian và nhóm theo project |
| Dự báo chi phí cuối tháng nếu xu hướng tiếp diễn? | **Billing Reports** | Có forecast khi loại thời gian và bộ lọc cho phép |
| Vì sao số tiền chứng từ kỳ trước là X? | **Cost table** | Có chi tiết theo kỳ hóa đơn, chứng từ, thuế, credits và các dòng phí |
| Cần CSV để giải thích từng SKU trên hóa đơn? | **Cost table** | Có bảng lồng hoặc phẳng, điều chỉnh cột và tải CSV |
| Phân bổ theo nhiều labels và tổng hợp hàng tháng có logic riêng? | **Billing export to BigQuery** | Truy vấn chi tiết, nối dữ liệu bổ sung và xây dashboard |
| Muốn thiết lập ngưỡng chi tiêu và gửi cảnh báo? | **Budgets & alerts** | Theo dõi ngân sách, không mặc nhiên chặn chi tiêu |

**Reports và Cost table không phải hai biểu diễn luôn cho ra đúng một số**. Reports có thể theo ngày sử dụng hoặc kỳ hóa đơn; Cost table được xây dựng để xem các dòng chi phí gắn với **một invoice/statement**. Ngay cả trong Reports, thay đổi bộ lọc hoặc cách tính savings cũng làm tổng khác đi.

### 2.1. Quyền truy cập cần thiết

Để xem toàn bộ dữ liệu của Cloud Billing account, người dùng thường được cấp một vai trò phù hợp như **Billing Account Viewer**, **Billing Account Costs Manager** hoặc **Billing Account Administrator** tại billing account. Quyền nền tảng liên quan đến xem thông tin chi tiêu là **billing.accounts.getSpendingInformation**; việc mở Reports ở cấp account còn tùy các quyền billing account liên quan.

Một số trường hợp có **quyền xem chi phí theo project** và chỉ xem được dữ liệu của project được phép. Khi đó, các tính năng ở cấp account như đối soát hóa đơn đầy đủ, nhóm theo labels hoặc xem khoản phí toàn account có thể không khả dụng. Nếu thiếu dữ liệu, cần kiểm tra **phạm vi quyền** trước khi kết luận chi phí bằng 0.

Quyền xem chi phí nên cấp theo nguyên tắc ít quyền nhất. Báo cáo billing có thể phản ánh các dự án, sản phẩm và hoạt động kinh doanh nhạy cảm; không chia sẻ CSV hoặc URL báo cáo ra ngoài phạm vi được phép.

## 3. Cloud Billing Reports: xem xu hướng và thành phần chi phí

### 3.1. Cách mở và đọc màn hình

Trong **Google Cloud console**, mở **Billing**, chọn billing account được phép truy cập, rồi vào **Reports** trong nhóm quản lý chi phí. Nếu chỉ có quyền xem theo project, cần chọn project phù hợp trước khi vào Billing; giao diện và tính năng khả dụng có thể khác.

Trang Reports gồm các phần quan trọng:

1. **Time range:** chọn khoảng thời gian và cơ sở thời gian ghi nhận chi phí.
2. **Group by:** chọn chiều phân tích, ví dụ Service, Project, SKU, ngày hoặc vị trí.
3. **Filters:** thu hẹp project, service, SKU, location, labels và các loại savings khi được hỗ trợ.
4. **Chart:** quan sát biến động chi phí theo thời gian; có thể hiển thị dự báo khi đủ điều kiện.
5. **Summary table và footer:** đọc số liệu đã nhóm, savings và tổng chi phí thuộc phạm vi lọc.

Theo giao diện phổ biến, preset mặc định là **Services — this month**, hiển thị chi phí từng ngày trong tháng hiện tại và nhóm theo Service. Vì vậy, câu đầu tiên khi mở trang là: **đây là tháng, phạm vi account/project và chế độ savings nào?**

### 3.2. Hiểu Charge period và Billing period

Đây là khác biệt quan trọng nhất khi đối chiếu báo cáo:

| Thuộc tính | **Charge period** (Usage date cũ) | **Billing period** (Invoice month cũ) |
|---|---|---|
| Tư duy phân tích | Khi nào việc sử dụng phát sinh | Khoản phí nằm trên chứng từ phát hành cho kỳ nào |
| Đơn vị chọn thời gian | Ngày hoặc khoảng ngày | Tháng/kỳ hóa đơn |
| Tình huống chính | Tìm ngày bắt đầu tăng chi phí, theo dõi tháng hiện tại | Đối soát hóa đơn, xem thuế/điều chỉnh ở cấp chứng từ |
| Forecast | Có thể xuất hiện nếu phạm vi kết thúc ở tương lai và bộ lọc hỗ trợ | Không có forecast theo kiểu này |
| Thuế, điều chỉnh cấp hóa đơn | Không được hiển thị như tổng của chế độ hóa đơn | Có thể được đưa vào tổng khi chọn đầy đủ phạm vi và quyền tương ứng |
| Số tổng so với invoice | Không nhất thiết khớp | Có thể khớp tổng theo kỳ khi không lọc và có đầy đủ quyền; nếu nhiều invoice cùng tháng thì Reports gộp theo tháng |

Ví dụ sử dụng 10 đơn vị tài nguyên ngày **31/10** nhưng dữ liệu được hoàn tất và đưa vào chứng từ tháng **11**. Báo cáo **Charge period** có thể ghi chi phí theo ngày sử dụng cuối tháng 10, còn Cost table khi xem invoice tháng 11 có dòng phí đó. Đây có thể là **khác biệt hợp lệ về thời điểm ghi nhận**, không nhất thiết là lỗi tính tiền.

Chi phí có độ trễ xử lý và cập nhật. Dữ liệu sử dụng vừa phát sinh không nhất thiết xuất hiện ngay; phần chi phí mới nhất nên được xem là **đang hoàn thiện**, không coi như kết sổ.

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng
    participant M as Hệ thống đo sử dụng
    participant B as Cloud Billing
    participant I as Invoice/Statement
    A->>M: Sử dụng tài nguyên ngày 31/10
    M-->>B: Ghi nhận chi phí sau khi xử lý
    B->>B: Báo cáo Charge period theo ngày sử dụng
    B-->>I: Phân bổ vào kỳ hóa đơn khi được lập
    Note over B,I: Tháng sử dụng có thể khác kỳ hóa đơn
~~~

### 3.3. Nhóm theo Service, Project, SKU và thời gian

**Group by** quyết định các hàng dữ liệu và cách chồng nhóm trên biểu đồ. Các lựa chọn thông dụng:

- **Service:** dịch vụ nào tạo ra phần lớn chi phí, ví dụ Compute Engine hay Cloud Storage.
- **Project:** môi trường hoặc sản phẩm nào đang tiêu thụ.
- **SKU:** khoản phí cụ thể tăng do compute, storage, requests hay egress.
- **Location: Region or multi-region:** quan sát phân bố chi phí theo vùng được hệ thống báo cáo; không suy ra hỗ trợ nhóm theo từng zone.
- **Date > Project / Date > Service / Date > SKU:** xác định ngày bắt đầu thay đổi và thành phần liên quan.
- **Label key:** phân tích chi phí theo giá trị của một nhãn tài nguyên được báo cáo hỗ trợ, khi có quyền và dữ liệu thích hợp.
- **Project hierarchy / ứng dụng:** hữu ích khi môi trường đã tổ chức các cấp quản trị và dùng tính năng hỗ trợ.

**Cách phân tích từ tổng đến nguyên nhân:**

~~~mermaid
flowchart TD
    T["Tổng chi phí tháng tăng"] --> P["Group by Project"]
    P --> S["Chọn project tăng mạnh → Group by Service"]
    S --> K["Chọn service → Group by SKU"]
    K --> D["Group by Date > SKU"]
    D --> Q{"Loại SKU nào tăng?"}
    Q -->|"Compute"| C["Kiểm tra VM/GKE/Cloud Run, CPU, bộ nhớ, giờ chạy"]
    Q -->|"Storage"| ST["Kiểm tra dung lượng, lớp lưu trữ, thao tác"]
    Q -->|"Network"| N["Kiểm tra egress, vị trí, đường đi"]
    C --> F["Đối chiếu triển khai và telemetry"]
    ST --> F
    N --> F
~~~

Nếu chỉ nhóm theo Service, một mức tăng do **Cloud SQL backup storage** có thể bị gộp với những dòng SKU khác của cùng dịch vụ. Phải đi sâu tới SKU và tài nguyên để phân biệt tăng tải hợp lý với cấu hình dư thừa.

### 3.4. Filters và tác động của việc lọc

Một bộ lọc có thể làm báo cáo dễ đọc hơn, nhưng cũng khiến **tổng hiển thị không còn đại diện cho toàn bộ billing account**. Ví dụ chọn project shop-prod thì tổng có thể loại bỏ phí support cấp account hoặc dịch vụ phát sinh trong project khác.

Khi lưu kết quả phân tích, ghi rõ:

~~~text
Billing account: [định danh được phép chia sẻ]
Time range type: Charge period / Billing period
From – To: [ngày hoặc tháng]
Group by: Project / Service / SKU / ...
Filters: [project, service, SKU, location, label, savings]
Currency: [đồng tiền billing account]
Generated at: [thời điểm chụp/xuất báo cáo]
Audience / Owner: [người phụ trách]
~~~

Nếu hai người đưa ra hai số khác nhau, so sánh **cả bộ thông số**, không chỉ so ảnh chụp tổng tiền.

### 3.5. Resource labels và giới hạn phân bổ chi phí

Labels như **team=payments**, **application=checkout**, **environment=production** giúp xem chi phí theo trách nhiệm. Tuy nhiên:

- Báo cáo dùng **resource labels** có thể không hiển thị **project labels** theo cùng một cách.
- Không phải mọi loại chi phí đều có nhãn tài nguyên.
- Nhãn gắn từ ngày nào thường chỉ được dùng để phân tích các khoản sử dụng có nhãn kể từ thời điểm tương ứng; không tự gán ngược cho lịch sử.
- Chi phí hỗ trợ hoặc khoản phí thuộc billing account có thể không gắn với project hoặc resource cụ thể.

Vì vậy một hàng **Charges for other usage / unallocated** không chứng minh toàn bộ tài nguyên đều chưa gắn nhãn; có thể do loại phí không mang nhãn hoặc thiết lập báo cáo.

## 4. Cách đọc số tiền: usage cost, savings, credits và invoice charges

Các hệ thống billing có nhiều loại số tiền. Cần hiểu **tổng nào đang được đọc** trước khi đánh giá một dịch vụ “tốn” hoặc “rẻ”.

| Khái niệm | Ý nghĩa thực tế | Cần lưu ý |
|---|---|---|
| **List cost** | Chi phí tính theo bảng giá công khai, ở ngữ cảnh có trường tương ứng | Chỉ hiển thị ở một số chế độ/tài khoản; không phải số tiền cuối cùng |
| **Usage cost / Cost** | Chi phí sử dụng tính theo giá áp dụng cho billing account | Có thể đã phản ánh giá hợp đồng; cần xem loại báo cáo |
| **Savings / credits** | Các khoản tiết kiệm, tín dụng hoặc ưu đãi khi có | Có thể được trình bày dưới dạng giảm trực tiếp giá hoặc credit tùy cơ chế |
| **Subtotal / Net cost** | Tổng sau những khoản giảm liên quan ở phạm vi đang xem | Cần đọc tên cột và tùy chọn savings thay vì tự suy từ màu biểu đồ |
| **Tax** | Thuế của hóa đơn/chứng từ | Không nhất thiết phân bổ vào từng SKU hoặc hiển thị trong báo cáo lọc |
| **Adjustment / correction** | Điều chỉnh theo nghiệp vụ billing | Có thể thuộc kỳ chứng từ khác với kỳ sử dụng |
| **Rounding** | Sai số làm tròn theo chứng từ | Dòng nhỏ vẫn có thể gây lệch khi đối soát |
| **Currency / exchange rate** | Đồng tiền và tỷ giá áp dụng cho billing account | Không so trực tiếp hai khoản bằng tiền tệ khác nhau |

Một phép tính **minh họa**, không phải công thức áp dụng máy móc cho mọi giao diện:

~~~text
Chi phí sử dụng theo mức giá áp dụng           300,00 USD
Khoản credit giảm chi phí                        -40,00 USD
Phí hỗ trợ/khoản phí cấp account                  15,00 USD
Thuế thuộc hóa đơn                               25,00 USD
Điều chỉnh làm tròn                               0,01 USD
----------------------------------------------------------
Tổng chứng từ minh họa                           300,01 USD
~~~

Số **260,00 USD** (300 - 40) có thể là một tổng sau credit của phần sử dụng; nó không bằng tổng chứng từ **300,01 USD**, vì còn support, tax và rounding. Trong thực tế, khoản support, credit hay thuế có thể xuất hiện dưới **dòng và cách nhóm riêng**; hãy đọc chính các cột và footer của báo cáo thay vì mặc định cộng một lần theo bảng minh họa.

### 4.1. Credits không luôn đồng nghĩa với giảm giá cùng kiểu

Một hệ thống có thể nhận:

- Khuyến mại hoặc trial credit (nếu đủ điều kiện).
- Các loại giảm giá dựa trên mức sử dụng hoặc cam kết, theo chương trình và cách tính hiện hành.
- Ưu đãi theo hợp đồng.
- Điều chỉnh/credit ghi nhận ở cấp hóa đơn.

Cơ chế của một số **committed use discounts (CUDs)** có thể thay đổi giữa **credit-based** và **discount-based consumption model**. Vì vậy đừng mặc định mọi khoản tiết kiệm đều nằm trong cùng một cột “Credits”. Khi phân tích CUD, cần quan sát phí cam kết, lượng sử dụng đủ điều kiện, model đang áp dụng và tác động net cost.

### 4.2. Dự báo không phải hóa đơn

Forecast trên Billing Reports ước lượng chi phí tương lai dựa trên tín hiệu được mô hình sử dụng. Nó giúp nhận biết xu hướng, nhưng có thể thay đổi khi phát sinh chiến dịch bán hàng, thay cấu hình, thêm cụm GKE hoặc mua commitment.

Forecast không thay thế **budget**, không bảo đảm là số cuối tháng và không nên dùng làm số kế toán đã kết sổ. Khi dùng forecast, ghi rõ thời điểm chụp và điều kiện bộ lọc.

## 5. Cost table: đối soát chi tiết với invoice hoặc statement

**Cost table** là báo cáo dạng bảng tập trung vào **chi phí gắn với một invoice/statement của kỳ hóa đơn đã chọn**. Nó phù hợp cho câu hỏi: “Hóa đơn tháng này gồm những khoản gì, từ project/service/SKU nào, có thuế và điều chỉnh nào?”

Đường đi thông thường: **Google Cloud console → Billing → chọn billing account → Cost management → Cost table**. Yêu cầu quyền xem chi phí trên billing account; người chỉ có quyền project sẽ không có cùng góc nhìn đối soát toàn tài khoản.

### 5.1. Các khu vực chính của Cost table

- **Header:** hiển thị thông tin invoice/statement như tài khoản, kỳ, số chứng từ, ngày, tổng tiền, currency; trường khả dụng có thể khác theo loại tài khoản và loại chứng từ.
- **Table:** dòng chi phí theo cấu hình hiển thị, nhóm và bộ lọc.
- **Footer:** tổng của những dòng đang hiện ra, có thể có thuế, điều chỉnh, khoản làm tròn.
- **Table configuration:** chọn nested/flat view, Group by và label key.
- **Columns:** bật/tắt các cột muốn đọc hoặc tải.
- **Download CSV:** xuất dữ liệu đang được giới hạn bởi cấu hình báo cáo.

Theo tài liệu Google Cloud, khi dùng **trạng thái bộ lọc mặc định, đầy đủ**, footer của Cost table khớp với tổng hóa đơn/statement tương ứng. Khi lọc riêng project hoặc service, footer thay đổi; đó là **filtered total**, không còn là tổng chứng từ. Đây là nguyên tắc quan trọng nhất khi đối soát. 

### 5.2. Nested table và flat table

| Chế độ | Cấu trúc | Dùng khi |
|---|---|---|
| **Nested (mặc định)** | Các cấp có thể mở rộng, ví dụ **Project > Service > SKU > Consumption model** | Tìm nhanh project tốn nhất, drill down đến SKU và mô hình sử dụng |
| **Flat (No grouping)** | Mỗi dòng là một mục chi phí/tín dụng đã tổng hợp theo hạt dữ liệu của bảng | Lọc, so sánh cột, tải CSV hoặc dùng Excel/BI |
| **Custom grouping** | Sắp xếp các chiều phân tích được hỗ trợ theo nhu cầu | Phân tích chi phí theo nhãn, SKU hoặc các nhóm nội bộ |

Ví dụ một nhánh của nested table:

~~~text
Project: shop-prod                         150,00 USD
  Service: Compute Engine                  100,00 USD
    SKU: CPU usage                          65,00 USD
    SKU: Memory usage                       20,00 USD
    SKU: Storage                            15,00 USD
  Service: Cloud Storage                    50,00 USD
    SKU: Object storage                     32,00 USD
    SKU: Operations / network               18,00 USD
~~~

Các số chỉ để **minh họa cách phân cấp**, không phải đơn giá hay dữ liệu thực tế. Với dữ liệu thật có thể còn discounts, credits, CUD fees hoặc các dòng điều chỉnh.

### 5.3. Những cột nên biết

| Nhóm | Trường hoặc cột thường gặp | Giúp trả lời |
|---|---|---|
| Tài khoản | Billing account ID / name | Chi phí thuộc account nào? |
| Tài nguyên | Project name, Project ID, Project number, Project hierarchy | Thuộc project hoặc đơn vị nào? |
| Sản phẩm | Service description / ID | Dịch vụ nào tính tiền? |
| Đơn giá/sử dụng | SKU description / ID, Usage amount, Unit | Khoản tiêu thụ là gì, đo bằng đơn vị nào? |
| Thời gian | Invoice month và các trường thời gian khả dụng | Kỳ hóa đơn nào, khoản sử dụng nào? |
| Loại phí | Cost type | Usage, Tax, Adjustment hoặc kiểu dòng khác? |
| Giá và tổng | List cost, Unrounded cost, Cost | Giá theo danh nghĩa hay giá áp dụng, có ảnh hưởng làm tròn? |
| Ưu đãi | Credit type, Credit name, Credit ID / amount theo cấu hình | Mức giảm phát sinh vì lý do nào? |
| Phân loại | Label key/value theo cấu hình | Cost center, environment hoặc team nào? |
| Tiền tệ | Currency; tỷ giá khi có | Tổng đang tính bằng loại tiền nào? |

Không phải mọi cột đều hiển thị sẵn hoặc có dữ liệu cho mọi tài khoản. Ví dụ **List cost** liên quan trường hợp có giá theo hợp đồng tùy thời gian/kế hoạch; muốn xem mức giá **đơn vị SKU** nên tham khảo **Pricing table** hoặc giá xuất BigQuery, vì Cost table không nhất thiết chứa cột đơn giá SKU.

**Unrounded cost** hữu ích khi số tổng có chênh lệch do làm tròn. Tốt nhất hãy so sánh số tiền chính thức ở mức chứng từ trước, rồi dùng số chưa làm tròn để tìm gốc của sai số nhỏ.

### 5.4. Chi phí không gắn với project

Một số chi phí như **support** có thể thuộc billing account chứ không thuộc project cụ thể. Trong Cost table, chúng có thể nằm dưới mục tương đương **Charges not specific to a project**. Vì thế tổng các project lựa chọn không chắc bằng tổng billing account, kể cả khi mọi project “đang chạy” đã được chọn.

### 5.5. Thuế, điều chỉnh và kỳ lập hóa đơn

Thuế và điều chỉnh cấp chứng từ có thể chỉ xuất hiện đầy đủ khi xem theo **Billing period** và không lọc phạm vi; một số phí lại cần hạch toán theo project hoặc loại thuế. Việc tính invoice month khác calendar usage month còn do dữ liệu báo cáo trễ, corrections hoặc khoản điều chỉnh được phát hành sau.

Google Cloud có thể phát hành **nhiều chứng từ trong một kỳ** với một số cấu hình tài khoản/giao dịch. Khi đó Reports theo Billing period có thể gộp mọi khoản cho tháng, còn Cost table giúp xem **chứng từ cụ thể** để đối soát. Luôn kiểm tra số invoice/statement, currency, publisher type (nếu có) và phạm vi đã chọn.

## 6. Quy trình đối soát Cost table với hóa đơn

Một cách làm có thể kiểm chứng:

1. **Xác định chứng từ:** ghi lại billing account, invoice/statement number, invoice month, currency, publisher type nếu có và tổng thanh toán trên chứng từ.
2. **Mở Cost table:** chọn đúng billing account và kỳ chứng từ.
3. **Đưa về bộ lọc mặc định:** không loại trừ project/service/SKU/credits để xem đủ phạm vi của chứng từ.
4. **Đối chiếu header và footer:** xem hai tổng này có bằng tổng chứng từ không; cân nhắc nhiều chứng từ trong kỳ và những khác biệt về quyền xem.
5. **Chọn nested view:** mở từng Project → Service → SKU để giải thích các thành phần lớn.
6. **Chuyển flat view nếu cần:** hiển thị Cost type, SKU ID, Cost, Credits, Tax, Unrounded cost và các cột liên quan.
7. **Xuất CSV:** giữ cả bản không lọc để lưu bằng chứng, sau đó mới xuất các bản đã lọc phục vụ điều tra.
8. **Ghi nhận chênh lệch:** nếu xuất hiện, mô tả rõ công thức, thời gian, kiểu dữ liệu, phép làm tròn và khoản bị loại trừ.
9. **Đối chiếu với Reports:** khi so theo kỳ hóa đơn, chọn Billing period cho đúng tháng và bộ lọc tương ứng; nhớ Reports gộp theo tháng nếu có nhiều invoice.

~~~mermaid
flowchart TD
    I["Invoice/Statement: tổng X"] --> C["Cost table đúng billing account + invoice"]
    C --> F{"Bộ lọc mặc định và đủ quyền?"}
    F -- "Không" --> R["Bỏ lọc / xác minh quyền và chứng từ"]
    R --> F
    F -- "Có" --> M{"Footer khớp tổng chứng từ?"}
    M -- "Có" --> D["Drill down Project > Service > SKU"]
    M -- "Không" --> E["Kiểm tra tháng, nhiều invoice, currency, publisher, credits, tax, rounding"]
    E --> M
    D --> V["Lưu CSV + kết quả đối soát"]
~~~

**Đừng vội so tổng Cost table đã lọc project với tổng invoice.** Khi lọc, những khoản phí toàn account, thuế hoặc các điều chỉnh được phân bổ khác có thể không còn nằm trong tập dữ liệu.

### 6.1. Bảng đối soát minh họa

Giả sử invoice tháng 10 có số liệu giả định:

| Hạng mục | Số tiền (USD) |
|---|---:|
| Compute Engine usage | 140,00 |
| Cloud Run usage | 60,00 |
| Cloud Storage usage | 40,00 |
| Cloud SQL usage | 60,00 |
| Tổng usage cost | **300,00** |
| Credits/savings ghi giảm | -40,00 |
| Phí support toàn account | 15,00 |
| Thuế | 25,00 |
| Rounding | 0,01 |
| Tổng invoice | **300,01** |

Một báo cáo **Charge period** chỉ gồm usage net có thể cho ra 260,00 USD; **Cost table** ở bộ lọc mặc định có thể giải thích 300,01 USD. Nếu lọc Project=shop-prod, một số dòng support/account-level có thể biến mất. Khi ghi báo cáo, phải nêu rõ mỗi số đại diện cho phần nào.

### 6.2. Cách đọc CSV đúng

Khi tải **Download CSV** trên Cost table:

- Dữ liệu chịu tác động của **Group by**, **filters** và **các cột đang chọn hiển thị**.
- CSV là dữ liệu **phẳng**; không có cây thụt đầu dòng như nested view. Việc có hay không một cột có thể làm người đọc hiểu sai grain của dòng.
- Ghi lại tên chứng từ, thời điểm tải, danh sách cột, nhóm và bộ lọc cùng với tệp.
- Nếu xuất tập dữ liệu lớn bị lỗi, dùng bộ lọc phù hợp hoặc chọn nhóm khác; phân tích quy mô lớn lặp lại nên cân nhắc BigQuery export.
- Không cộng một dòng tổng ở cấp Project với các dòng con Service/SKU đã chứa trong tổng đó: sẽ bị **double count**.

CSV chỉ là **bản dữ liệu phân tích**, không tự thay thế chứng từ thanh toán chính thức.

## 7. Kịch bản điều tra chi phí tăng: từ dịch vụ đến nguyên nhân

Giả sử chi phí của project shop-prod trong tháng tăng 35% so với tháng trước. Nhóm không nên kết luận ngay “Google Cloud tăng giá” hoặc “GKE quá đắt” khi chưa biết loại SKU nào thay đổi.

### 7.1. Bước 1: xác lập đường cơ sở

Trong Reports:

1. Chọn billing account và **Charge period** có hai khoảng thời gian so sánh hợp lý.
2. Giới hạn Project=shop-prod, giữ Savings filters nhất quán.
3. Chọn Group by **Date > Service** để biết **ngày bắt đầu tăng**.
4. So sánh với dữ liệu release, lưu lượng request, lịch batch và các thay đổi hạ tầng.
5. Chọn dịch vụ nghi vấn rồi Group by **SKU**.

Nên so sánh cùng số ngày, hoặc điều chỉnh số ngày còn lại của tháng. So tổng **20 ngày tháng này** với **toàn bộ 31 ngày tháng trước** có thể gây kết luận sai.

### 7.2. Bước 2: phân tích theo từng loại workload

| Workload / dịch vụ | SKU/nguồn phí nên kiểm tra | Telemetry nên so |
|---|---|---|
| **Compute Engine** | vCPU, memory, persistent disk, GPU, network | Số VM, loại máy, giờ chạy, CPU utilization, disk |
| **GKE** | Compute Engine ở node, chi phí cụm/management nếu áp dụng, lưu trữ, network | Số node, autoscaler, requests/limits, pod, workload, cluster |
| **Cloud Run** | CPU, memory, request hoặc billing theo model áp dụng; network và dịch vụ phụ thuộc | Request count, concurrency, min instances, timeout, lượng xử lý |
| **Cloud Storage** | GB lưu trữ, lớp lưu, operations, retrieval, egress | Dung lượng, số object, tần suất tải, lifecycle |
| **Cloud SQL** | Instance CPU/memory, storage, backup, network | Tải truy vấn, số kết nối, storage growth, HA, backup |
| **BigQuery** | Compute/analysis, storage, edition/capacity model nếu dùng | Bytes processed, slot utilization, queries, partitions |
| **Networking** | Egress Internet/liên vùng, load balancing, NAT, đường truyền liên quan | Bytes sent, đích traffic, region, kiến trúc kết nối |
| **Observability** | Log ingestion/storage hoặc những khoản được tính theo cấu hình hiện hành | Log volume, retention, sampling, metrics/traces |

**SKU cho biết điều gì được tính tiền; monitoring cho biết vì sao tài nguyên được sử dụng.** Hai nguồn cần được đối chiếu. Ví dụ egress tăng khi traffic tăng là điều có thể dự đoán; egress tăng sau khi chuyển kết nối sang region khác có thể là dấu hiệu thiết kế cần điều chỉnh.

### 7.3. Bước 3: thử giả thuyết

Ví dụ Reports phát hiện chi phí Cloud Storage tăng ở SKU mạng sau bản phát hành mới. Đội phát triển phát hiện ảnh trước đây được cache qua CDN nhưng ứng dụng mới tải trực tiếp từ bucket trong region khác.

Kiểm tra:

- Thời điểm bắt đầu tăng chi phí có khớp thời điểm phát hành không?
- Số byte egress và request count có tăng tương ứng không?
- Lượng người dùng tăng hay chỉ thay đổi đường truyền?
- Nếu sửa cache/routing, độ trễ, bảo mật và chi phí có tốt hơn không?
- Có thể thử nghiệm trên một phần lưu lượng để đo trước khi áp dụng toàn bộ không?

Sau khi xác định nguyên nhân, tạo một thay đổi cấu hình/code có chủ sở hữu và theo dõi Reports ngày tiếp theo. Chi phí có độ trễ ghi nhận, nên tránh đánh giá hiệu quả ngay trong vài phút.

### 7.4. Khi nào cần Cost table?

Nếu đang điều tra **khoản tăng trong hóa đơn đã phát hành**, mở Cost table để xác nhận chính xác SKU và các dòng **tax/credit/adjustment** của chứng từ đó. Một khoản tăng invoice có thể đến từ adjustment hoặc chi phí sử dụng cuối kỳ trước được ghi nhận muộn, thay vì lượng traffic của tháng hiện tại.

## 8. Phân bổ chi phí theo project, team và environment

### 8.1. Project không phải lúc nào cũng là một cost center

Tách project theo ứng dụng/môi trường giúp dễ phân quyền và phân bổ chi phí, nhưng một ứng dụng có thể dùng chung VPC, database hoặc platform services. Ngược lại, một project có thể chứa workload của nhiều nhóm.

Do đó nên kết hợp:

- **Project:** đơn vị đầu tiên để kiểm kê và phân tách môi trường.
- **Labels:** team, application, environment, cost_center trên những tài nguyên hỗ trợ.
- **Quy tắc phân bổ chi phí dùng chung:** định nghĩa cách chia support, network, shared database hoặc resource thiếu nhãn.
- **Billing export:** truy vấn nhiều chiều khi báo cáo mặc định chưa đáp ứng.

Ví dụ báo cáo quản trị tháng:

| Nhóm chi phí | Nguyên tắc phân bổ mẫu | Rủi ro |
|---|---|---|
| Tài nguyên gắn cost_center | Dựa trên label hợp lệ và kỳ chi phí | Thiếu label, label thay đổi giữa kỳ |
| Project dành riêng một team | Dựa theo project ID | Phí hỗ trợ hoặc shared services không thuộc project |
| Shared VPC/network | Phân bổ theo tỷ lệ đo được hoặc chính sách nội bộ | Dữ liệu egress có thể không đủ hạt để chia tuyệt đối |
| Support toàn billing account | Quy định tỷ lệ, không giả định tự thuộc các project | Tổng project không bằng tổng account |
| Credits chung | Có quy tắc chia credit minh bạch | Dễ trình bày sai net cost giữa các team |

### 8.2. Phân biệt cost allocation với invoice reconciliation

**Cost allocation** trả lời “Đội nào chịu khoản chi phí nào?” và có thể áp dụng chính sách nội bộ. **Invoice reconciliation** trả lời “Tổng số tiền chúng ta trả có khớp chứng từ không?”. Hai bảng có thể khác nhau về **cách phân bổ nội bộ**, dù tổng sau đối soát phải giải thích được.

Một team có thể có chi phí gross 100 USD, credit 30 USD và phí shared support được phân bổ 5 USD. Quyết định báo cáo team ở gross 100, net 70 hay net + allocation 75 USD cần được công bố rõ. Không đổi công thức giữa các tháng mà không chú thích.

## 9. Cloud Billing export to BigQuery: khi cần nhiều hơn giao diện

Reports và Cost table phù hợp để điều tra tương tác. Khi cần phân tích định kỳ, truy vấn theo nhiều chiều, tích hợp hệ thống ERP hoặc dashboard tự động, có thể bật **Cloud Billing export to BigQuery** (quyền và phí BigQuery theo cấu hình thực tế).

Các dạng export tiêu biểu:

| Dạng export | Dữ liệu chính | Khi nên dùng |
|---|---|---|
| **Standard usage cost** | Account, invoice month, service/SKU, project, cost, credits, labels và các trường khác | Xu hướng chi phí, tổng theo project/team/service |
| **Detailed usage cost** | Dữ liệu standard và thêm chi tiết tài nguyên cho những dịch vụ hỗ trợ | Tìm nguồn tăng chi phí tới mức VM/ổ đĩa hoặc workload hỗ trợ |
| **Pricing export** | Thông tin giá và các trường định giá tương ứng | Phân tích giá SKU, tối ưu theo model tiêu thụ |

Không giả định detailed export luôn có **ID của mọi tài nguyên thuộc mọi dịch vụ**. Một số tính năng cần cấu hình bổ sung, ví dụ theo dõi cost allocation cho workload GKE. Dữ liệu được xuất liên tục theo quy trình xử lý billing, không phải đồng bộ tức thì. Nên bật export sớm nếu muốn có chuỗi lịch sử đầy đủ; việc bật muộn có thể gây thiếu dữ liệu lịch sử theo loại export/vị trí dataset.

### 9.1. Truy vấn tổng cost và credits theo project

Ví dụ với **standard usage cost export**. Thay tên bảng thật bằng đường dẫn phù hợp trong BigQuery; quyền đọc dataset phải được cấp riêng. Đây là **truy vấn phân tích**, không thay thế bước đối soát chứng từ trong Cost table.

~~~sql
-- Tổng chi phí theo project cho một invoice month cụ thể.
-- Thay BILLING_PROJECT.BILLING_DATASET.EXPORT_TABLE.
WITH line_items AS (
  SELECT
    invoice.month AS invoice_month,
    currency,
    COALESCE(project.id, '(no project)') AS project_id,
    service.description AS service_name,
    cost AS usage_or_charge_cost,
    IFNULL(
      (SELECT SUM(c.amount) FROM UNNEST(credits) AS c),
      0
    ) AS credits_amount
  FROM `BILLING_PROJECT.BILLING_DATASET.EXPORT_TABLE`
  WHERE invoice.month = '202610'
)
SELECT
  invoice_month,
  currency,
  project_id,
  ROUND(SUM(usage_or_charge_cost), 2) AS cost_before_credits,
  ROUND(SUM(credits_amount), 2) AS credits,
  ROUND(SUM(usage_or_charge_cost + credits_amount), 2) AS net_amount
FROM line_items
GROUP BY invoice_month, currency, project_id
ORDER BY net_amount DESC;
~~~

Giải thích:

- **invoice.month = '202610'** là kỳ chứng từ 10/2026, không có nghĩa tất cả usage đều xảy ra trong 10/2026.
- **credits** là mảng lồng nhau; phép **SELECT SUM từ UNNEST** cho mỗi dòng giúp tránh nhân bản chi phí khi một dòng có nhiều credits.
- **project.id** có thể rỗng/null khi khoản phí không gắn project.
- **currency** được giữ trong GROUP BY để không cộng lẫn đơn vị tiền tệ.
- Kết quả cộng **cost + credits** từ các dòng của export; muốn khớp chứng từ phải kiểm tra tiếp loại phí, tax, adjustment, publisher, rounding và mức độ đầy đủ của dữ liệu.

**Lỗi SQL thường gặp:** dùng lệnh **CROSS JOIN UNNEST(credits)** trực tiếp rồi SUM(cost). Dòng có hai credits sẽ nhân đôi cost, còn dòng không có credit có thể bị loại khỏi kết quả. Nên tính tổng credits bằng truy vấn con theo từng dòng như ví dụ.

### 9.2. Truy vấn xác định SKU tăng chi phí theo ngày sử dụng

~~~sql
SELECT
  DATE(usage_start_time) AS usage_date,
  project.id AS project_id,
  service.description AS service_name,
  sku.description AS sku_name,
  ROUND(SUM(cost), 2) AS cost_before_credits
FROM `BILLING_PROJECT.BILLING_DATASET.EXPORT_TABLE`
WHERE usage_start_time >= TIMESTAMP('2026-10-01')
  AND usage_start_time < TIMESTAMP('2026-11-01')
  AND project.id = 'shop-prod'
GROUP BY usage_date, project_id, service_name, sku_name
ORDER BY usage_date, cost_before_credits DESC;
~~~

Truy vấn này cố ý dùng **usage_start_time** thay vì **invoice.month**, nên có thể không ra số khớp chứng từ. Nó phù hợp để điều tra thời điểm tăng chi phí. Ngoài ra **SUM(cost)** không trừ credits và không phản ánh đầy đủ trường savings khác; đặt tên cột **cost_before_credits** để tránh nhầm.

### 9.3. Lưu ý khi làm việc với labels

Có thể truy vấn **UNNEST(labels)** để phân bổ theo nhãn. Tuy nhiên, giống credits, một dòng có nhiều labels sẽ bị nhân bản nếu join sai. Nên chọn đúng key:

~~~sql
SELECT
  COALESCE(
    (SELECT l.value
     FROM UNNEST(labels) AS l
     WHERE l.key = 'cost_center'
     LIMIT 1),
    'unallocated'
  ) AS cost_center,
  ROUND(SUM(cost), 2) AS cost_before_credits
FROM `BILLING_PROJECT.BILLING_DATASET.EXPORT_TABLE`
WHERE invoice.month = '202610'
GROUP BY cost_center
ORDER BY cost_before_credits DESC;
~~~

**Unallocated** nghĩa là bản ghi không có giá trị label cần tìm; không thể kết luận tài nguyên thiếu mọi nhãn. Nếu cùng một key được sử dụng không nhất quán giữa các môi trường, báo cáo còn cần bước chuẩn hóa dữ liệu.

## 10. Các lỗi diễn giải chi phí phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Reports tổng tháng khác invoice | Đang xem Charge period thay vì Billing period; có tax/adjustment hoặc late usage | Chọn cùng kỳ, kiểm tra loại thời gian, thuế và từng chứng từ |
| Reports Billing period vẫn khác Cost table | Reports gộp nhiều invoice trong tháng; filter/savings khác | Kiểm tra số invoice, publisher, bộ lọc, quyền account |
| Cost table footer khác header | Đã lọc project/SKU/service hoặc chỉ xem một phần dữ liệu | Reset filters, chọn đúng chứng từ rồi đối chiếu lại |
| Tổng project không bằng tổng account | Support hoặc khoản phí không gắn project | Tìm Charges not specific to a project, tax, adjustment |
| Dữ liệu ngày gần nhất thấp bất thường | Dữ liệu billing có độ trễ | So với những ngày đã hoàn tất và chờ kỳ xử lý báo cáo phù hợp |
| Gross tăng nhưng net giảm | Credits/discounts hoặc giá hợp đồng thay đổi | Phân tích riêng Cost, List cost, savings và loại credit |
| Label environment=prod không có số lịch sử | Label gắn muộn; service không có nhãn trong dữ liệu export | Kiểm tra ngày bắt đầu gắn nhãn, export schema và phạm vi |
| Chi phí bị gấp đôi trong SQL | UNNEST credits/labels nhân bản dòng | Dùng aggregate truy vấn con theo dòng hoặc chuẩn hóa trước join |
| CSV và bảng trên màn hình không giống mức chi tiết | Group by hoặc các cột tải khác cấu hình | Lưu bộ lọc, nhóm, danh sách cột rồi xuất lại |
| Kết luận sai do đổi tiền tệ | So số USD với số VND hoặc đơn vị tiền tệ billing account khác | Kiểm tra currency/tỷ giá ở kỳ báo cáo |
| SKU network tăng nhưng traffic ứng dụng không tăng | Thay đường truyền, inter-region egress, backup/replication | Kiểm tra region, VPC, topology và lượng dữ liệu đi ra |
| Chi phí GKE khó quy cho microservice | Nhiều workload dùng chung node hoặc thiếu cost allocation | Bật/kiểm tra khả năng phân bổ chi phí và metadata workload khi được hỗ trợ |

Một điều tra đúng cần **bằng chứng đủ hạt**: con số tổng, breakdown project/service/SKU, khoảng thời gian, thay đổi triển khai và chỉ số vận hành. Đừng chỉ tìm một con số khớp mà bỏ qua cách nó được tạo ra.

## 11. Từ phân tích chi phí sang hành động quản trị

### 11.1. Quy trình FinOps định kỳ

| Nhịp | Câu hỏi | Hành động |
|---|---|---|
| Hằng ngày | Có ngày nào tăng đột biến? | Reports theo ngày, service và SKU; đối chiếu deploy/traffic |
| Hằng tuần | Dự báo cuối tháng so với budget thế nào? | Xem Reports forecast khi hỗ trợ, phân công owner điều tra |
| Hằng tháng | Hóa đơn có khớp số liệu chi phí không? | Cost table, invoice, CSV và sổ đối soát |
| Hằng tháng | Chi phí nào chưa phân bổ được? | Project/label report, BigQuery export và quy tắc shared cost |
| Hằng quý | Kiến trúc có dư thừa hoặc thiếu năng lực không? | Xem sizing VM/GKE, Cloud Run concurrency, storage, backup, egress, commitments |

Một báo cáo tốt nên có **một người chịu trách nhiệm cho mỗi hành động**. Ví dụ “Compute Engine tăng 20%” chỉ là quan sát; “do nhóm payments thử chuyển hai VM sang loại lớn từ ngày 12/10, sẽ đo CPU và quyết định giữ hoặc giảm kích thước trước ngày 20/11” là một hành động cụ thể.

### 11.2. Chuyển kết quả thành thay đổi

- **Compute Engine:** kiểm tra VM chạy ngoài giờ, rightsizing và disk không còn dùng.
- **GKE:** đối chiếu nhu cầu requests/limits, autoscaler, mật độ pod, nodepool và chi phí phụ thuộc.
- **Cloud Run:** kiểm tra min instances, concurrency, thời gian chạy, CPU allocation và thiết kế background work.
- **Cloud Storage:** đánh giá lifecycle, lớp lưu trữ, request/retrieval và lưu lượng egress.
- **Cloud SQL:** đánh giá HA, số instance, kích thước máy, storage, backup và lượng kết nối.
- **BigQuery:** đánh giá pruning qua partition/clustering, quét dữ liệu và mô hình capacity.
- **Mạng:** xem traffic theo region và tránh truyền dữ liệu vòng hoặc không cần thiết.

Mọi quyết định tối ưu phải giữ **SLO, bảo mật và khả năng khôi phục**. Không giảm mức dự phòng hoặc xóa backup chỉ vì bảng chi phí cho thấy khoản đó lớn.

### 11.3. Kết nối với Budgets & alerts

Sau khi hiểu baseline qua Reports và Cost table, có thể thiết lập budget theo phạm vi phù hợp để theo dõi ngưỡng chi tiêu. Budget alert tạo **cảnh báo**, thường không tự động là giới hạn cứng dừng dịch vụ. Nếu muốn quy trình phản ứng khi vượt ngưỡng, cần thêm xác nhận tác động lên production, danh tính thực thi và kênh thông báo phù hợp.

## 12. Thực hành có hướng dẫn trong Google Cloud console

Bài thực hành sử dụng tài khoản **đã có quyền đọc billing**; không cần tạo tài nguyên mới. Nếu chưa có quyền trên billing account thật, có thể làm trên ảnh chụp/số liệu giả định do người hướng dẫn cung cấp.

### Phần A — Xem xu hướng

1. Mở **Billing → Reports** ở billing account được cấp.
2. Xác nhận chế độ **Charge period** và chọn **tháng trước**; ghi lại tổng và currency.
3. Chọn **Group by Project**, liệt kê ba project có chi phí lớn nhất.
4. Chọn một project, đổi **Group by Service**; tìm service lớn nhất.
5. Đổi **Group by SKU**, xác định hai SKU lớn nhất của service đó.
6. Dùng **Date > SKU** (nếu giao diện cho phép) để xác định ngày tăng đáng kể.
7. Ghi giả thuyết về nguyên nhân và dữ liệu monitoring cần xác minh.

**Đầu ra mẫu:**

~~~text
Kỳ: Charge period, 01/10–31/10/2026
Account/project: [được cấp]
Currency: [theo account]
Project cao nhất: [tên] — [cost]
Service cao nhất: [tên] — [cost]
SKU cao nhất: [tên] — [cost]
Ngày bắt đầu tăng: [ngày]
Giả thuyết: [mô tả]
Bằng chứng cần đối chiếu: [metric/deploy/traffic]
~~~

### Phần B — Đối soát kỳ hóa đơn

1. Mở **Cost table** trong cùng billing account.
2. Chọn **invoice month** của một chứng từ đã phát hành và ghi invoice number/currency.
3. Đặt lại **bộ lọc mặc định**, kiểm tra header và footer có khớp không.
4. Giữ nested view mặc định, đi sâu **Project → Service → SKU → Consumption model**.
5. Chuyển **No grouping (flat)** để quan sát các dòng Cost type, Credits, Tax, Unrounded cost.
6. Tải CSV ở trạng thái không lọc; ghi lại bộ cột và thời điểm xuất.
7. Lọc một project và ghi **filtered total**, giải thích vì sao nó khác tổng invoice.
8. Mở **Reports** với **Billing period** của cùng tháng; so sánh và ghi chú nếu có nhiều chứng từ hoặc phạm vi quyền khác nhau.

**Đầu ra mẫu:**

| Trường | Giá trị ghi nhận |
|---|---|
| Billing account | … |
| Invoice month | … |
| Invoice/statement number | … |
| Currency | … |
| Total trên chứng từ | … |
| Total Cost table mặc định | … |
| Chênh lệch | … |
| Tổng sau khi lọc một project | … |
| Lý do filtered total khác invoice | … |
| Link/CSV lưu bằng chứng | … |

### Phần C — Đánh giá chất lượng phân bổ chi phí

1. Trong Reports, thử **Group by Label key** nếu quyền và loại dữ liệu cho phép.
2. Chọn key ví dụ **cost_center** hoặc **team**, ghi giá trị không được phân bổ.
3. Kiểm tra danh sách project và tài nguyên liên quan; tìm nhãn thiếu/không nhất quán.
4. Đề xuất một quy tắc bắt buộc gắn label khi tạo tài nguyên (ví dụ qua Terraform module hoặc pipeline).
5. Đề xuất cách phân bổ phí **support** nếu đây là khoản thuộc account, thay vì giả định tự chia cho từng project.

Phần này rèn cách dùng số liệu billing để phát hiện **lỗi quản trị metadata**, ngoài việc tìm cách tiết kiệm đơn thuần.

## 13. Case study: hóa đơn tăng dù lưu lượng ứng dụng ổn định

**Bối cảnh giả định.** Hệ thống thương mại điện tử chạy frontend Cloud Run, backend GKE, database Cloud SQL và lưu hình ảnh ở Cloud Storage. Có ba project **shop-dev**, **shop-prod**, **data-analytics** dùng chung billing account. Tháng trước, invoice tăng 28%; lượng đơn hàng tăng khoảng 3%.

**Dữ kiện điều tra qua Reports (giả định):**

| Bước | Phát hiện | Giải thích sơ bộ |
|---|---|---|
| Group by Project | shop-prod chiếm phần lớn tăng trưởng | Không phải chủ yếu do data-analytics |
| Group by Service | Cloud Storage tăng mạnh; GKE tăng nhẹ | Không nên chỉ tập trung chỉnh node GKE |
| Group by SKU | Nhóm phí network của Cloud Storage tăng | Lưu lượng truyền dữ liệu có thể là tác nhân |
| Date > SKU | Bắt đầu tăng sau bản release frontend | Có tương quan thời gian với thay đổi ứng dụng |
| Đối chiếu Cloud Monitoring | Request count gần ổn định; bytes sent lớn hơn | Có thể ảnh bị tải lặp hoặc đổi đường truyền |
| Xem Cost table | Tháng invoice còn có tax adjustment | Một phần chênh lệch tổng không do mức sử dụng |

**Quyết định:** sửa cơ chế cache và kiểm tra cấu hình phân phối ảnh; theo dõi request/bytes egress trước và sau thay đổi. Đồng thời, ghi riêng tax adjustment trong báo cáo kế toán, không quy nó thành lỗi hiệu năng của backend.

**Bài học:** để tìm cơ hội tối ưu, dùng Reports theo **Charge period + SKU + ngày**; để giải thích hóa đơn, dùng **Cost table theo kỳ và số chứng từ**. Sau đó liên kết với thay đổi triển khai và chỉ số vận hành để xác định nguyên nhân.

## 14. Câu hỏi tự kiểm tra

1. Một chi phí phát sinh cuối ngày 31/10 nhưng xuất hiện trên invoice tháng 11. Nên phân tích bằng chế độ nào khi muốn tìm ngày sử dụng, và bằng công cụ nào khi muốn đối soát hóa đơn?
2. Vì sao tổng **Project A + Project B** có thể nhỏ hơn tổng billing account?
3. Trong Cost table, bạn lọc riêng Compute Engine và thấy tổng nhỏ hơn invoice. Có thể kết luận invoice sai không?
4. Nếu muốn biết Cloud Run tốn nhiều tiền hơn do request hay do thời gian thực thi, nên Group by Service hay SKU?
5. **Cost = 100**, **credits = -20**, **tax = 10**, **support = 5**. Với các số giả định này, usage net và tổng chứng từ lần lượt là bao nhiêu nếu không có khoản nào khác?
6. Khi ghép UNNEST(credits) với SUM(cost) trong BigQuery, rủi ro nào có thể xuất hiện?
7. Có thể dùng forecast trong Reports như giá trị hóa đơn đã chốt không?
8. Để phân bổ chi phí theo cost_center, vì sao chỉ gắn label ở project có thể chưa đủ?

**Gợi ý trả lời:**

- (1) Charge period khi phân tích ngày sử dụng; Billing period/Cost table khi phân tích chứng từ tháng 11.
- (2) Có các khoản phí account-level như support, thuế hoặc những project/dòng chưa được đưa vào phạm vi lọc.
- (3) Không; filtered total không phải invoice total.
- (4) SKU để tìm loại tiêu thụ cụ thể, rồi đối chiếu metric Cloud Run.
- (5) Usage net **80**; tổng giả định **95**.
- (6) Nhân bản cost khi một dòng có nhiều credit, hoặc mất dòng không có credits.
- (7) Không; forecast là ước lượng theo xu hướng và phạm vi bộ lọc.
- (8) Resource labels không tự kế thừa cho từng tài nguyên, và một số phí không mang nhãn.

## 15. Tài liệu tham khảo chính thức

Những đường dẫn dưới đây là tài liệu Google Cloud để đối chiếu giao diện và hành vi theo phiên bản hiện hành:

- [Analyze billing data and cost trends with Reports](https://docs.cloud.google.com/billing/docs/how-to/reports)
- [View and download the cost details of your invoice or statement — Cost table](https://docs.cloud.google.com/billing/docs/how-to/cost-table)
- [Billing reports: View the charges on your invoices](https://docs.cloud.google.com/billing/docs/how-to/reports/charges-on-invoices)
- [Export Cloud Billing data to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery)
- [Structure of Standard usage cost data export](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage)
- [Billing reports: View forecasted costs](https://docs.cloud.google.com/billing/docs/how-to/reports/forecasted-costs)

Tên các bộ lọc, preset, cột dữ liệu và cơ chế discounts có thể được Google Cloud cập nhật. Với hệ thống thật, cần xác minh bằng chính tài khoản, quyền, kỳ chứng từ và tài liệu dịch vụ tương ứng.

---

**Kết nối với lộ trình CLOUD_PROVIDERS_GCP:** tổ chức project, IAM và VPC quyết định **ai có quyền tạo, vận hành và xem chi phí**; Compute Engine, GKE, Cloud Run, storage và database quyết định **những loại tài nguyên/SKU tạo ra chi phí**; Billing Reports cho biết **xu hướng và nguồn tăng chi phí**, Cost table giúp **đối soát số tiền trên chứng từ**, còn export, automation và monitoring giúp **biến kết quả phân tích thành kiểm soát chi phí có thể đo lường**.

