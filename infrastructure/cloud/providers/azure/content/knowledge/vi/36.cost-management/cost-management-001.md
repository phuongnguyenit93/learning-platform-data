# Mô hình tính phí, meter và các thành phần hóa đơn Azure

Trên Microsoft Azure, **tạo một tài nguyên không có nghĩa là chỉ xuất hiện một khoản phí cố định**. Một máy ảo có thể tạo chi phí tính toán theo thời gian chạy, đĩa được cấp phát, địa chỉ IP, lưu lượng truyền dữ liệu và phần mềm đi kèm. Một ứng dụng chạy ít request vẫn có thể phát sinh tiền nếu dịch vụ được cấu hình để duy trì năng lực tính toán hoặc dung lượng lưu trữ liên tục.

Trong chương **Quản lý chi phí** của lộ trình **CLOUD_PROVIDERS_AZURE**, bài học này giải thích cách Azure biến mức sử dụng hạ tầng thành các dòng chi phí và hóa đơn. Chủ đề kết nối với toàn bộ hệ sinh thái Azure: subscription, resource group, Microsoft Entra ID, mạng ảo, compute, storage, database, giám sát, bảo vệ tài nguyên và vận hành ứng dụng.

Mục tiêu của người vận hành là trả lời được ba câu hỏi: **dịch vụ nào tạo ra chi phí, lượng sử dụng nào được ghi nhận theo đơn vị nào và khoản tiền đó xuất hiện trên hóa đơn ra sao?** Khi hiểu những khái niệm này, bạn có thể dự báo, đối soát và kiểm soát chi phí mà không cần đoán dựa trên tổng số tiền cuối tháng.

> **Phạm vi bài học:** Các giá và số tiền trong ví dụ là giả định phục vụ học tập, không phải bảng giá, báo giá, mức thuế hoặc chính sách hiện hành của Azure. Mức phí, tính năng, tên meter và cách phát hành hóa đơn phụ thuộc dịch vụ, vùng, hợp đồng mua hàng, đồng tiền thanh toán và thời điểm sử dụng. Khi lập ngân sách thực tế, phải đối chiếu dữ liệu billing của chính tài khoản.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **pricing model**, **SKU**, **meter**, **unit of measure**, **usage quantity**, **unit price** và **effective price**.
2. Giải thích cách Azure tính tiền theo thời gian, dung lượng, giao dịch, lưu lượng, năng lực dự trữ hoặc cam kết sử dụng.
3. Xác định các loại chi phí thường gặp của compute, storage, database, network, observability và dịch vụ bên thứ ba.
4. Đọc những thành phần quan trọng trên hóa đơn Azure và hiểu phạm vi **billing account**, **billing profile**, **invoice section**, **subscription**.
5. Phân biệt **actual cost**, **amortized cost**, giá niêm yết, giá sau ưu đãi, khoản mua cam kết và số tiền phải thanh toán.
6. Thực hiện đối soát từ hóa đơn đến các dòng mức sử dụng, xử lý sai lệch do thuế, credit, thời gian ghi nhận hoặc phí không thuộc resource usage.
7. Thiết kế quy trình theo dõi ngân sách, gắn nhãn, phân bổ chi phí, xuất dữ liệu và phát hiện bất thường.

## 2. Bản đồ dòng chảy từ tài nguyên đến hóa đơn

Một lần triển khai tạo tài nguyên Azure. Mỗi dịch vụ phát sinh các sự kiện sử dụng hoặc khoản phí theo quy tắc thương mại. Hệ thống billing định lượng mức sử dụng bằng một hoặc nhiều **meter**, xác định đơn giá có hiệu lực và ghi nhận dòng chi phí. Các dòng này được tổng hợp theo tài khoản và kỳ thanh toán để lập hóa đơn, cùng những khoản mua trước, điều chỉnh, thuế hoặc credit phù hợp.

~~~mermaid
flowchart TD
    A["Ứng dụng và tài nguyên Azure"] --> B["Sử dụng: giờ compute, dung lượng, I/O, dữ liệu, request"]
    B --> C["Meter và đơn vị đo"]
    C --> D["Số lượng được ghi nhận"]
    P["Giá, vùng, SKU, hợp đồng, ưu đãi"] --> E["Định giá và áp dụng điều kiện"]
    D --> E
    E --> F["Cost details / Cost Management"]
    F --> G["Tổng hợp theo billing scope và kỳ"]
    H["Mua reservation/savings plan, support, Marketplace, điều chỉnh"] --> G
    I["Credits, thuế, quy đổi tiền tệ theo điều kiện hợp đồng"] --> G
    G --> J["Invoice và khoản phải thanh toán"]
~~~

Luồng trên diễn tả quan hệ khái niệm. **Không phải mọi dòng chi phí đều bắt nguồn từ một resource có Resource ID**: phí hỗ trợ, khoản mua cam kết hoặc một số khoản Marketplace có thể thuộc phạm vi billing khác và không gắn với resource group.

## 3. Từ vựng tính phí bắt buộc nắm vững

| Thuật ngữ | Ý nghĩa thực tế | Ví dụ minh họa |
| --- | --- | --- |
| **Service / product** | Dịch vụ hoặc sản phẩm được tiêu thụ | Virtual Machines, Azure SQL Database, Storage |
| **SKU / tier** | Biến thể tài nguyên có khả năng hoặc mức dịch vụ xác định | VM size, Premium SSD tier, SQL compute tier |
| **Region** | Vùng triển khai hoặc vùng áp dụng giá/tài nguyên | Southeast Asia, East US |
| **Meter** | Định danh thành phần sử dụng được hệ thống billing đo đếm | Giờ compute VM, dung lượng disk, dữ liệu outbound |
| **Meter ID / meter name** | Mã/tên để phân biệt meter trong dữ liệu giá hoặc chi phí | Một meter riêng cho size, vùng hoặc loại sử dụng |
| **Unit of measure** | Đơn vị số lượng của meter | Hour, GiB-month, 10K transactions, GB |
| **Quantity / consumed quantity** | Khối lượng sử dụng được ghi nhận trong đơn vị meter | 720 giờ, 120 GiB-month, 50 đơn vị 10K request |
| **Unit price** | Đơn giá tương ứng đơn vị đo và ngữ cảnh định giá | 0,08 USD/hour theo giả định |
| **Effective price** | Đơn giá hiệu lực cho dòng sau khi áp dụng điều kiện giá phù hợp, tùy schema | Có thể khác giá công khai do hợp đồng/chiết khấu |
| **Cost** | Tiền tính cho dòng sử dụng hoặc khoản phí | 720 × 0,08 = 57,60 USD |
| **Charge type** | Loại bút toán: sử dụng, mua, hoàn tiền, điều chỉnh... | Usage, Purchase, Refund |
| **Billing period** | Chu kỳ để tổng hợp phí và phát hành hóa đơn | Không nhất thiết luôn trùng tháng lịch |

**Meter khác resource.** Một resource có thể tạo nhiều meter, và một dòng chi phí có thể không có Resource ID. **SKU khác meter.** SKU mô tả cấu hình sản phẩm, còn meter mô tả đại lượng tính tiền cụ thể của sản phẩm đó.

Để nhận diện đúng một dòng, đừng chỉ đọc meter name. Hãy xem đồng thời **meter ID, product/service, SKU, region, unit, pricing model, kỳ sử dụng và billing scope**. Tên hiển thị hoặc cấu trúc meter có thể thay đổi theo thời gian; không xây hệ thống đối soát chỉ dựa trên chuỗi tên.

### 3.1. Công thức tính phí cơ bản

Với một meter có giá tuyến tính, chưa xét ưu đãi, số lượng miễn phí, bậc giá hay làm tròn:

\[
\text{Chi phí dòng} = \text{Số lượng theo đơn vị meter} \times \text{Đơn giá/đơn vị}
\]

Ví dụ **720 giờ × 0,08 USD/giờ = 57,60 USD**.

Nhưng không phải mọi dịch vụ có giá tuyến tính duy nhất. Một meter có thể dùng **bậc giá theo mức tiêu thụ**, số lượng miễn phí, phần phí tối thiểu, giá khác theo vùng, mức thanh toán cam kết hoặc những điều kiện riêng trong hợp đồng. Công thức tổng quát hơn:

\[
\text{Chi phí thực tế} =
\sum_i \text{Phí sử dụng có hiệu lực}_i
+ \text{Phí mua/định kỳ}
+ \text{Điều chỉnh có dấu}
\]

Thuế và credit được xử lý theo cấu trúc hóa đơn và điều kiện hợp đồng; không nên mặc định chúng đã nằm trong mọi số liệu Cost Analysis.

## 4. Các mô hình tính phí phổ biến

Azure không có một cách tính phí thống nhất cho tất cả dịch vụ. Nhận diện đúng mô hình là bước đầu để hiểu biến nào làm tăng chi phí.

| Mô hình | Đại lượng đo | Ví dụ thường gặp | Nguyên nhân chi phí tăng |
| --- | --- | --- | --- |
| **Theo thời gian cấp phát/sử dụng** | Giây, phút hoặc giờ, theo quy tắc meter | VM compute, dedicated compute, một số dịch vụ database | Chạy nhiều instance hoặc duy trì lâu hơn |
| **Theo năng lực đã provision** | vCore/DTU, throughput, instance/tier trong thời gian tồn tại | Database provisioned, plan/capacity reservation | Cấp công suất cao hơn nhu cầu |
| **Theo dung lượng lưu** | GB hoặc GiB trong khoảng thời gian quy đổi | Blob, managed disks, backup retention | Dữ liệu tăng hoặc giữ lâu |
| **Theo thao tác/giao dịch** | Số operation, request, transaction, có thể theo đơn vị 10K | Storage operations, API calls | Tần suất truy cập, retry, polling |
| **Theo dữ liệu truyền** | GB/GiB theo chiều và tuyến truyền | Outbound transfer, cross-region transfer tùy dịch vụ | Truyền nhiều dữ liệu hoặc sai kiến trúc vùng |
| **Theo mức tiêu thụ tài nguyên dịch vụ** | RU/s, request units, token, execution duration... | Cosmos DB, một số dịch vụ serverless/AI | Query đắt hoặc số lượt gọi tăng |
| **Theo cam kết/mua trước** | Khoản mua upfront hoặc định kỳ và phạm vi quyền lợi | Reservations, savings plan | Mua cam kết nhưng không sử dụng hết |
| **Theo gói/thuê bao** | Phí định kỳ hoặc bậc dịch vụ | Một số sản phẩm Marketplace, support | Chọn plan hoặc số lượng license cao |

Các tên mô hình là khái niệm để học. **Cách đo cụ thể do từng meter/SKU quyết định**, nên cần kiểm tra tài liệu tính phí chính thức và Cost Details của dịch vụ đang dùng.

### 4.1. Pay-as-you-go không có nghĩa mọi phí chỉ xuất hiện khi request đến

Với pay-as-you-go, khách hàng thanh toán phần sử dụng theo điều kiện giá áp dụng. Tuy nhiên một VM đã được cấp phát có thể phát sinh compute dù CPU rảnh. Database provisioned có thể tính theo năng lực dù ít query. Managed disk có thể tiếp tục tính phí khi VM đã ngừng.

**Phân biệt resource đang tồn tại với resource đang thực sự được tính phí ở từng meter.** Thao tác stop trong hệ điều hành, stop từ Portal và **deallocate** VM có ý nghĩa vận hành khác nhau. Khi VM được deallocate đúng cách, phí compute của VM thông thường có thể dừng, nhưng **disk, snapshot, backup, một số IP hoặc dịch vụ liên quan** vẫn có thể phát sinh phí riêng. Cần kiểm tra trạng thái và meter thực tế.

### 4.2. Serverless và provisioned

Chế độ serverless thường liên kết phí với số lần thực thi, thời gian/memory hoặc mức tiêu thụ tài nguyên cụ thể, nhưng vẫn có thể có **mức tối thiểu, tài nguyên phụ, storage hoặc networking** tính riêng. Chế độ provisioned trả cho năng lực sẵn sàng, thuận lợi hơn với tải ổn định và kiểm soát hiệu năng nhưng dễ lãng phí khi idle.

Ví dụ so sánh một hệ thống xử lý sự kiện:

- Worker chạy liên tục trên máy ảo: cần theo dõi giờ compute, disk, network và chi phí vận hành.
- Worker chạy bằng dịch vụ theo execution: cần theo dõi số lần chạy, duration, memory/CPU, trigger và các tài nguyên liên quan.

Không khẳng định serverless luôn rẻ hơn; phải dùng workload thực, free grant, min instances, cold start, SLO và giá áp dụng để so sánh tổng chi phí.

## 5. Đọc đơn vị meter cho đúng

### 5.1. Hour, GB, GiB, GB-month và nhóm giao dịch

Một số bẫy đơn vị:

- **Giờ:** tháng có số ngày khác nhau; **730 giờ/tháng** chỉ là giả định phổ biến trong mô hình dự toán, không phải mặc định mọi kỳ hóa đơn có 730 giờ.
- **GB và GiB:** 1 GB = \(10^9\) byte, 1 GiB = \(2^{30}\) byte. Meter ghi đơn vị nào thì dùng đúng đơn vị đó.
- **GiB-month hoặc GB-month:** đại diện dung lượng được giữ theo thời gian. 120 GiB tồn tại trọn tháng có thể tương ứng khoảng 120 GiB-month theo cách chuẩn hóa của meter; lưu nửa kỳ có mức sử dụng thấp hơn, theo quy tắc đo thực tế.
- **10K operations:** giá trên 10.000 giao dịch. Nếu có 500.000 giao dịch, quantity theo đơn vị 10K là **50**, không phải 500.000.
- **Data transfer:** kiểm tra chiều vào/ra, tuyến mạng, bậc miễn phí và điểm bắt đầu/kết thúc tính phí; không xem mọi packet là cùng một meter.

### 5.2. Giá theo bậc và theo số lượng

Giả sử một meter **giả định** có giá:

| Mức sử dụng trong kỳ | Đơn giá minh họa |
| --- | ---: |
| 0–100 GB đầu | 0,10 USD/GB |
| 100 GB tiếp theo | 0,08 USD/GB |
| Trên 200 GB | 0,06 USD/GB |

Nếu dùng 250 GB và cách tính là **bậc lũy tiến**:

\[
100 \times 0{,}10 + 100 \times 0{,}08 + 50 \times 0{,}06 = 21\ \text{USD}
\]

Không dùng một đơn giá cuối cùng nhân toàn bộ 250 GB trừ khi **meter/offer** quy định chính xác cách tính đó. Bậc giá, phạm vi cộng dồn usage và thời điểm reset phụ thuộc chính sách sản phẩm.

### 5.3. Mức sử dụng khác số tiền phải thanh toán

Một dòng 100 giờ sử dụng có thể:

1. Được tính theo giá pay-as-you-go.
2. Được chiết khấu theo hợp đồng.
3. Được hưởng quyền lợi từ reservation hoặc savings plan đủ điều kiện.
4. Được trừ credit sau khi định giá, theo điều khoản áp dụng.

Vì vậy cùng một lượng sử dụng có thể tạo ra **chi phí hiệu lực khác nhau** ở hai subscription, tài khoản billing hoặc thời điểm khác nhau.

## 6. Compute: những khoản phí đi cùng máy ảo và ứng dụng

### 6.1. Azure Virtual Machines

Với một VM, tổng chi phí có thể gồm:

| Thành phần | Ví dụ meter | Điều cần kiểm tra |
| --- | --- | --- |
| **Compute** | Giờ/đơn vị thời gian của VM size và hệ điều hành | VM đang allocated/running hay đã deallocated; license phù hợp |
| **Managed disks** | Dung lượng/tier, performance hoặc operation tùy loại disk | Disk còn tồn tại sau khi VM ngừng/xóa hay không |
| **Snapshot / backup** | Dung lượng lưu và các thao tác liên quan | Chính sách giữ bản, redundancy |
| **Public IP / networking** | Địa chỉ IP, NAT, load balancer, transfer tùy cấu hình | Tài nguyên mạng còn tồn tại không |
| **Marketplace image/license** | Phí phần mềm đi kèm theo điều kiện publisher | Có license riêng ngoài VM compute không |
| **Monitoring** | Log ingestion, retention hoặc metrics theo chính sách | Agent có gửi quá nhiều dữ liệu không |

Không dùng câu “VM đã stop nên hết tiền” làm kết luận cho toàn bộ workload. Phải kiểm tra từng meter gắn với VM và các tài nguyên phụ.

### 6.2. App Service, AKS, Container Apps và Functions

Các mô hình triển khai khác nhau có ranh giới tính phí khác nhau:

- **App Service:** một phần chi phí gắn với **App Service plan/compute capacity**. Nhiều app dùng chung plan, nên không nên mặc định có một dòng phí compute tách biệt cho từng app.
- **AKS:** các VM/node pool, disk, load balancer, public IP, lưu lượng, monitoring và những thành phần/tier liên quan có thể tạo chi phí. Pod tăng nhưng chưa cần node mới có tác động chi phí khác so với phải tăng số VM node.
- **Azure Container Apps:** cần xem consumption hoặc workload profile được chọn, min replicas, CPU/memory, request và tài nguyên liên quan theo chính sách tính phí của môi trường.
- **Azure Functions:** chi phí phụ thuộc hosting plan, trigger/execution, tài nguyên và các dịch vụ kèm theo. Không lấy một quy tắc billing duy nhất áp dụng cho mọi Functions plan.

**Mô hình phân bổ chi phí ứng dụng** khác dữ liệu meter. Nếu ba dịch vụ dùng chung một App Service plan hoặc node pool AKS, hóa đơn có thể ghi phí ở tài nguyên chia sẻ; để tính giá thành từng dịch vụ cần thêm quy tắc phân bổ dựa trên CPU, memory, request, thời gian hoặc các nguồn đo khác.

## 7. Storage: dung lượng chỉ là một phần

Azure Storage có thể phát sinh các nhóm phí:

1. **Dung lượng lưu trữ:** dữ liệu đã lưu, tier hot/cool/cold/archive nếu áp dụng, loại redundancy.
2. **Operations:** đọc, ghi, liệt kê hoặc truy xuất, mỗi loại có thể dùng meter và đơn vị riêng.
3. **Retrieval / early deletion:** việc truy xuất hoặc xóa dữ liệu trước thời hạn tối thiểu có thể tạo phụ phí ở một số tier.
4. **Replication / network:** lưu lượng giữa vùng hoặc dịch vụ nếu thuộc loại được tính phí.
5. **Backup / snapshot / data protection:** bản sao, chính sách giữ dữ liệu và các dịch vụ liên quan.

Một hệ thống ghi log liên tục có thể vừa tăng **dung lượng**, vừa tăng **transaction**, vừa tăng **monitoring ingest**. Nếu chỉ nhìn một dòng “Storage Capacity”, bạn sẽ bỏ sót nguồn chi phí khác.

### 7.1. Ví dụ về meter giao dịch

Giả sử dịch vụ Storage trong ví dụ có meter ghi:

~~~text
Meter: Write operations (minh họa)
Unit: 10,000 operations
Observed operations: 500,000
Meter quantity: 500,000 / 10,000 = 50
Illustrative price: 0.004 USD per unit
Cost: 50 × 0.004 = 0.20 USD
~~~

Điểm quan trọng là **50 đơn vị tính phí**, không phải 500.000 đơn vị. Giá 0,004 USD là giá giả định; mức giá Storage thật còn tùy loại storage, tier, redundancy, region và transaction category.

## 8. Dữ liệu, mạng, giám sát và dịch vụ phụ

### 8.1. Database

Với **Azure SQL Database**, meter có thể gắn với compute/service tier, dung lượng dữ liệu và backup hoặc các thành phần tùy mô hình provisioned/serverless và tùy tính năng. Với **Azure Cosmos DB**, cần xem throughput/RU, vùng/replication, dung lượng và backup theo cấu hình.

Ví dụ, **RU/s** là năng lực cấp phát, còn **RU charge** của từng request mô tả lượng tài nguyên một thao tác đã tiêu thụ. Hai chỉ số có liên hệ nhưng không phải một meter tiền tệ đơn giản có thể nhân trực tiếp với nhau trong mọi mô hình Cosmos DB. Cần kiểm tra đó là **provisioned throughput, autoscale hay serverless**.

### 8.2. Networking

Các nhóm phí cần nhận diện: **data transfer outbound**, truyền dữ liệu giữa vùng hoặc vùng sẵn sàng tùy tuyến, NAT Gateway, Load Balancer, Application Gateway, Azure Front Door, VPN Gateway, ExpressRoute và public IP khi có áp dụng.

Không mặc định **ingress luôn có phí** hoặc **egress luôn cùng một giá**. Có những chiều dữ liệu hoặc mức lưu lượng miễn phí/ưu đãi và nhiều tuyến được tính khác nhau. Cần biết dữ liệu đi **từ đâu → đến đâu, qua dịch vụ nào**, đồng thời xem bậc giá và điều kiện của hợp đồng.

### 8.3. Azure Monitor và Log Analytics

Chi phí observability có thể phụ thuộc **log ingestion**, retention, xử lý/truy vấn hoặc tính năng tùy workspace, plan và loại dữ liệu. Các log verbose trong production hoặc thu thập trùng nhiều agent có thể làm tăng chi phí mà không tạo giá trị vận hành tương ứng.

Khi kiểm soát telemetry, không tắt những log bắt buộc cho bảo mật, điều tra sự cố hoặc tuân thủ chỉ để làm thấp hóa đơn. Tốt hơn nên phân loại dữ liệu, giảm trùng lặp và chọn retention/tier phù hợp.

### 8.4. Marketplace và hỗ trợ

Azure Marketplace có sản phẩm của nhà xuất bản bên thứ ba; phí của chúng có thể được ghi nhận, phát hành hóa đơn hoặc áp dụng điều khoản riêng tùy giao dịch. **Support plan** cũng có thể phát sinh phí ngoài resource usage. Không tự suy ra toàn bộ khoản phải trả bằng tổng chi phí compute + storage của resource group.

## 9. Ví dụ tính tiền cho một workload

Giả sử một ứng dụng orders-api chạy cả tháng với mô hình meter rất giản lược. **Tất cả đơn giá sau đây là giả định để luyện tính**, không đại diện cho giá niêm yết của bất cứ Azure SKU nào.

| Dịch vụ/meter minh họa | Quantity tính phí | Đơn giá giả định | Thành tiền |
| --- | ---: | ---: | ---: |
| VM compute | 720 hour | 0,08 USD/hour | 57,60 USD |
| Managed disk | 120 GiB-month | 0,10 USD/GiB-month | 12,00 USD |
| Database compute | 720 hour | 0,15 USD/hour | 108,00 USD |
| Blob capacity | 300 GiB-month | 0,02 USD/GiB-month | 6,00 USD |
| Storage transactions | 50 đơn vị 10K operations | 0,004 USD/đơn vị | 0,20 USD |
| Network outbound | 80 GiB | 0,07 USD/GiB | 5,60 USD |
| Log ingestion | 15 GiB | 2,00 USD/GiB | 30,00 USD |
| **Tổng chi phí sử dụng giả định** | | | **219,40 USD** |

Kiểm tra phép cộng:

\[
57{,}60+12{,}00+108{,}00+6{,}00+0{,}20+5{,}60+30{,}00=219{,}40\ \text{USD}
\]

Đây là **subtotal của những meter được liệt kê**, chưa bao gồm những dịch vụ không xuất hiện trong bảng, khoản mua commitment, Marketplace, support, điều chỉnh, thuế hoặc credit. Giá thực tế có thể dùng bậc giá, điều kiện hợp đồng và các khoản miễn phí, nên không lấy 219,40 USD làm dự báo Azure thật.

### 9.1. Điều gì xảy ra khi giảm compute?

Nếu VM được deallocate sau 15 ngày thay vì chạy trọn 30 ngày, **giờ compute** của VM có thể giảm khoảng một nửa trong giả định đơn giản. Nhưng disk 120 GiB-month vẫn có thể được tính nếu vẫn giữ cả tháng; database có thể tiếp tục chạy và logs trước đó vẫn được lưu.

Vì vậy, một đề xuất tối ưu phải tính từng meter chịu ảnh hưởng. “Tắt máy ban đêm sẽ giảm 50% tổng hóa đơn” là kết luận không có cơ sở khi phần lớn chi phí nằm ở database, storage hoặc cam kết vẫn phải trả.

## 10. Pricing model và purchasing model khác nhau

**Pricing model** mô tả cách giá áp lên mức sử dụng của một dịch vụ, còn **purchasing model** mô tả cách khách hàng mua và trả tiền theo thỏa thuận. Hai điều này có liên quan nhưng không đồng nghĩa.

### 10.1. Các hình thức mua Azure thường gặp

| Hình thức | Đặc điểm ở mức khái niệm | Lưu ý khi đối soát |
| --- | --- | --- |
| **Pay-as-you-go / Microsoft Online Services Program (MOSP), tùy offer** | Thanh toán theo cách dùng và điều khoản đăng ký | Phạm vi hóa đơn, phương thức thanh toán và quyền truy cập phụ thuộc offer |
| **Microsoft Customer Agreement (MCA)** | Có cấu trúc billing account/profile/section và hóa đơn theo billing profile | Xác minh billing profile và invoice section cụ thể |
| **Enterprise Agreement (EA)** | Hợp đồng doanh nghiệp, enrollment và các cấu trúc quản trị phù hợp | Kỳ billing, chiết khấu, quyền xem thông tin tùy enrollment |
| **Cloud Solution Provider (CSP)** | Mua qua đối tác cung cấp dịch vụ | Đối tác có thể là bên phát hành hóa đơn; tham chiếu đơn giá/điều kiện đối tác |
| **Các offer, credit hoặc sponsorship khác** | Quy tắc credit/eligibility riêng | Credit có thể giới hạn dịch vụ, thời hạn hoặc loại phí được áp dụng |

Những hình thức trên có thể khác nhau về cổng xem hóa đơn, định dạng xuất dữ liệu, quyền API và nội dung từng dòng. Không có một cấu trúc hóa đơn duy nhất áp dụng cho mọi tài khoản Azure.

### 10.2. Giá niêm yết và giá hiệu lực

**Azure Pricing Calculator** và bảng giá công khai hữu ích để lập dự toán. **Azure Retail Prices API**, khi sử dụng, cung cấp dữ liệu giá bán lẻ công khai theo thông tin sản phẩm, meter, SKU và vùng. Dữ liệu này **không nhất thiết phản ánh giá thương lượng, ưu đãi, credit hoặc quyền lợi purchasing model** của tổ chức.

Để phân tích tiền thực trả, ưu tiên **Cost Management / Cost Details / hóa đơn và bảng giá hợp đồng** theo đúng billing scope mà bạn có quyền truy cập. Một khoản usage ở một subscription có thể hưởng giá khác với subscription khác dù nhìn cùng dịch vụ và region.

## 11. Reservations, savings plan và các cơ chế giảm chi phí

### 11.1. Azure Reservations

Reservation thường là cam kết mua quyền lợi giá cho một dạng sử dụng hoặc năng lực đủ điều kiện trong một thời hạn. Tính phù hợp phụ thuộc sản phẩm, vùng, SKU, scope chia sẻ và điều khoản cụ thể. Một reservation có thể được thanh toán **upfront** hoặc theo lịch thanh toán khả dụng; tổng lợi ích phụ thuộc tỷ lệ sử dụng và mức giảm thực tế.

**Reservation không nhất thiết làm biến mất mọi meter của workload.** Ví dụ quyền lợi có thể áp cho phần compute được quy định, còn disk, network hoặc license có thể vẫn tính riêng. Khi workload không khớp điều kiện reservation, phần cam kết chưa dùng có thể gây lãng phí.

### 11.2. Azure savings plan for compute

Savings plan for compute là một hình thức cam kết chi tiêu compute theo giờ trong thời hạn được hỗ trợ, đổi lại giá ưu đãi cho usage đủ điều kiện. Khả năng áp dụng còn phụ thuộc sản phẩm, điều kiện và thứ tự áp dụng quyền lợi. **Khoản cam kết vẫn có thể phải thanh toán ngay cả khi mức dùng thấp hơn kế hoạch**.

Reservation và savings plan **không phải** “mã giảm giá” tự động trừ một tỷ lệ cố định trên toàn bộ hóa đơn. Chúng là những quyền lợi có phạm vi áp dụng và cách phân bổ chi phí riêng, nên cần đo:

- **Utilization:** phần cam kết đã được sử dụng.
- **Coverage:** phần usage đủ điều kiện được quyền lợi bao phủ.
- **Unutilized commitment:** chi phí cam kết nhưng chưa tận dụng.
- **Break-even / savings:** so sánh có điều kiện với mô hình trả theo mức dùng, cùng một workload.

### 11.3. Azure Hybrid Benefit, Spot và ưu đãi khác

**Azure Hybrid Benefit** cho một số workload và license đủ điều kiện, theo điều khoản cấp phép. **Spot VMs** có thể cung cấp compute giá thấp hơn nhưng có khả năng bị thu hồi, nên thích hợp với workload có thể gián đoạn. Free tier, trial credit hoặc ưu đãi hợp đồng chỉ áp dụng theo điều kiện cụ thể.

Không nên ghép các tỷ lệ tiết kiệm quảng bá bằng phép cộng đơn giản. Hai ưu đãi có thể không được áp dụng đồng thời, hoặc chỉ áp trên những thành phần khác nhau của chi phí.

## 12. Actual cost, amortized cost và invoice amount

Đây là một trong những chỗ dễ nhầm nhất khi đọc Azure Cost Management.

### 12.1. Actual cost

**Actual cost** phản ánh cách chi phí phát sinh hoặc khoản mua được ghi nhận theo thời điểm billing với cấu trúc dữ liệu đang được sử dụng. Với reservation mua trả trước, khoản mua có thể tạo một khoản chi lớn vào ngày mua trong dữ liệu actual cost, trong khi usage đủ điều kiện nhận quyền lợi có thể được phản ánh theo cách khác.

### 12.2. Amortized cost

**Amortized cost** phân bổ chi phí mua commitment như reservation/savings plan theo thời gian và mức sử dụng cho mục đích phân tích. Dữ liệu này hữu ích để đánh giá chi phí kinh tế của workload hoặc phân bổ nội bộ theo thời gian thay vì dồn toàn bộ tiền mua vào một ngày.

Nhưng **amortized cost không phải luôn bằng số tiền thực xuất hiện trên hóa đơn của một kỳ**. Giá trị và cách phân bổ phụ thuộc loại commitment, phạm vi, dữ liệu hóa đơn và cách hệ thống phân bổ phần dùng/không dùng.

### 12.3. Ví dụ mua commitment

Giả sử một tổ chức mua quyền lợi giá giả định **1.200 USD**, phân bổ kinh tế trong 12 tháng. Để minh họa khái niệm, mức phân bổ đều là:

\[
1.200 / 12 = 100\ \text{USD/tháng}
\]

Nếu thanh toán upfront, hóa đơn kỳ mua có thể chứa khoản **purchase 1.200 USD** (theo điều khoản và các dòng liên quan), còn báo cáo amortized có thể thể hiện chi phí phân bổ theo thời gian. Với billing hàng tháng, lịch thanh toán và cách ghi chi phí khác. Đây chỉ là minh họa nguyên tắc, **không mô phỏng chính xác thuật toán phân bổ reservation/savings plan Azure**.

Không cộng **actual cost + amortized cost** để ra tổng: hai góc nhìn có thể đại diện cùng một chi phí. Chọn đúng góc nhìn trước khi lập biểu đồ và giải thích sự khác biệt với invoice.

## 13. Cấu trúc tổ chức thanh toán và phạm vi nhìn thấy chi phí

Azure quản lý tài nguyên theo cấu trúc quản trị như tenant, management group, subscription và resource group; quản lý thanh toán theo một cấu trúc khác:

~~~mermaid
flowchart TD
    A["Billing account / thỏa thuận mua Azure"] --> B["Billing profile (nếu mô hình hỗ trợ)"]
    B --> C["Invoice section (nếu mô hình hỗ trợ)"]
    C -. "Phân bổ charges" .-> D["Azure subscription"]
    D --> E["Resource group"]
    E --> F["Resource / meter usage"]
    A --> G["Invoice, support, purchases, adjustments"]
~~~

Sơ đồ thể hiện cấu trúc **khái niệm của một số agreement như MCA**. Với EA, CSP hoặc offer khác, tên cấp, quan hệ và phạm vi hóa đơn có thể khác; không phải mọi tài khoản đều có billing profile và invoice section.

### 13.1. Phân biệt các phạm vi

| Phạm vi | Vai trò chính | Dùng để làm gì? |
| --- | --- | --- |
| **Tenant / Microsoft Entra ID** | Danh tính và kiểm soát truy cập | Đăng nhập, phân quyền, quản trị danh tính |
| **Management group** | Nhóm subscription về quản trị | Chính sách, phân quyền, tổng hợp quản trị |
| **Subscription** | Ranh giới quản lý tài nguyên, quota, RBAC và đơn vị tiêu thụ Azure | Theo dõi usage/cost thuộc subscription |
| **Resource group** | Vòng đời và tổ chức tài nguyên | Gắn nhãn, quản trị, xem chi phí resource có ánh xạ |
| **Billing account/profile/section** | Phạm vi thanh toán theo agreement hỗ trợ | Hóa đơn, phân quyền billing, phân bổ và theo dõi charges |

**Một resource group không phải là một hóa đơn riêng.** Một hóa đơn có thể chứa chi phí từ nhiều subscription. Các khoản Marketplace, support, taxes hoặc commitment purchases có thể không nằm trong bộ lọc resource group.

### 13.2. Quyền xem hóa đơn khác quyền xem tài nguyên

Người có quyền **Contributor** trên resource group không mặc nhiên có quyền tải invoice hoặc nhìn thấy mọi điều khoản giá trong billing account. Một số vai trò billing cho phép xem invoice, credit và dữ liệu tài chính, trong khi RBAC của tài nguyên dùng để triển khai, đọc hoặc sửa resource.

Khi thiếu dữ liệu, kiểm tra **agreement type, billing scope, quyền Cost Management/billing và chính sách truy cập** trước khi kết luận dịch vụ không tạo chi phí. Đừng cấp quyền Owner toàn subscription chỉ để giải quyết việc đọc hóa đơn.

## 14. Các thành phần thường gặp trên hóa đơn Azure

Hóa đơn là tài liệu thanh toán theo agreement và invoice period. Các trường cụ thể có thể khác nhau, nhưng khi đọc nên tìm:

| Thành phần | Ý nghĩa | Câu hỏi đối soát |
| --- | --- | --- |
| **Invoice number / invoice ID** | Định danh chứng từ | Có đang đối soát đúng hóa đơn không? |
| **Invoice date / billing period** | Ngày phát hành và kỳ tính tiền | Có trùng kỳ dữ liệu cost được xuất không? |
| **Bill-to / sold-to / payer** | Bên mua và bên thanh toán theo thỏa thuận | Đơn vị pháp lý và thuế có đúng không? |
| **Billing account/profile/section** | Phạm vi gắn chi phí, nếu có | Hóa đơn chứa subscription nào? |
| **Service/usage charges** | Các khoản phí sử dụng dịch vụ | Có thể truy về meter/usage nào? |
| **Purchases / commitments** | Reservation, savings plan hoặc khoản mua phù hợp | Khoản trả trước/định kỳ đã được ghi ở đâu? |
| **Marketplace charges** | Phần mềm hoặc dịch vụ publisher bên ngoài | Có thuộc nhà cung cấp và kỳ đúng không? |
| **Support/other charges** | Gói hỗ trợ hoặc phí khác | Có nằm ngoài resource usage không? |
| **Adjustments/refunds** | Điều chỉnh hoặc hoàn tiền, có thể mang dấu âm | Có đang trừ hai lần không? |
| **Credits** | Khoản credit đủ điều kiện được áp dụng | Credit có áp cho loại dịch vụ này không? |
| **Taxes** | Thuế theo pháp nhân, địa điểm và hợp đồng | Khoản nào là cơ sở tính thuế? |
| **Currency / exchange** | Đồng tiền hóa đơn và cách quy đổi nếu có | Có đang so USD dự toán với đồng tiền billing khác không? |
| **Amount due / balance** | Khoản cần thanh toán, có thể liên quan payment/credit trước đó | Có trùng với tổng resource cost trên dashboard không? |

**Không cộng mọi dòng một cách mù quáng.** Tài liệu hóa đơn có thể gồm **dòng tổng, dòng chi tiết, số dư kỳ trước, khoản thanh toán đã thực hiện hoặc các khoản không phải usage**. Phải xác định cấu trúc và quy ước dấu trước khi đối soát.

### 14.1. Hóa đơn mẫu: nhận diện từng nhóm khoản

Giả sử cùng workload ở phần 9 tạo **219,40 USD** sử dụng và có các dòng sau trong một ví dụ riêng:

| Thành phần giả định | Số tiền minh họa |
| --- | ---: |
| Usage charges được đưa vào hóa đơn | +219,40 USD |
| Khoản mua/định kỳ commitment trong kỳ | +100,00 USD |
| Phí hỗ trợ thuộc hóa đơn | +20,00 USD |
| Điều chỉnh ghi giảm | −5,00 USD |
| Credit áp dụng đủ điều kiện | −25,00 USD |
| **Tạm tính trước thuế** | **309,40 USD** |
| Thuế giả định phục vụ bài toán | +30,94 USD |
| **Tổng minh họa** | **340,34 USD** |

Tính thử:

\[
219{,}40+100+20-5-25=309{,}40
\]

\[
309{,}40+30{,}94=340{,}34\ \text{USD}
\]

Khoản **30,94 USD** được giả định để luyện cộng hóa đơn, **không phải quy tắc tính VAT hay thuế cho Azure/Vietnam**. Trong thực tế, mức thuế, đối tượng chịu thuế, credit và thứ tự tính tùy thỏa thuận, quốc gia, pháp nhân và chứng từ. Đặc biệt, nếu usage đã được phủ bởi một commitment, cần kiểm tra dữ liệu thực để **không tính trùng** cả usage được hưởng quyền lợi và khoản purchase.

## 15. Thời gian ghi nhận: usage date khác invoice date

Cùng một request hoặc giờ compute có thể xuất hiện trong dashboard và trên hóa đơn ở các thời điểm khác nhau do pipeline định lượng/phát hành dữ liệu, thời điểm chốt kỳ hoặc bút toán điều chỉnh.

**Phân biệt:**

1. **Usage date:** ngày tài nguyên được tiêu thụ.
2. **Charge/posting date:** thời điểm chi phí được đưa vào dữ liệu billing, theo schema.
3. **Invoice date:** ngày hóa đơn được phát hành.
4. **Invoice period:** khoảng thời gian/giao dịch mà hóa đơn bao phủ.
5. **Export generation date:** ngày bạn lấy ảnh chụp dữ liệu chi phí.

Một bộ dữ liệu xuất sớm vào ngày cuối tháng có thể chưa chứa đủ charges chưa được xử lý. Một adjustment hoặc refund cũng có thể được ghi ở kỳ sau dù liên quan usage kỳ trước.

**Không ép các trường này thành cùng một ngày** và không mặc định tất cả kỳ thanh toán bắt đầu/ngừng vào 00:00 UTC hoặc ngày đầu/cuối tháng lịch. Khi reconcile, cần chọn billing period chính thức và dữ liệu đã đủ độ trễ cập nhật.

### 15.1. Vì sao số liệu hôm nay chưa chắc bằng hóa đơn chốt kỳ?

- Dữ liệu usage chưa được xử lý hết hoặc có bút toán đến trễ.
- Đồng tiền hiển thị trong cost view khác đồng tiền billing.
- Cost Analysis đang lọc subscription/resource group nhưng hóa đơn gồm phạm vi rộng hơn.
- Actual và amortized cost khác cách thể hiện purchase/cam kết.
- Credit, tax, support, Marketplace hoặc adjustment không có trong phạm vi truy vấn.
- Một số charges thuộc kỳ trước hoặc phát hành ở hóa đơn khác.

Vì vậy phải so sánh **cùng billing scope, cùng kỳ, cùng currency, cùng loại cost** trước khi điều tra chênh lệch.

## 16. Cost Management, Cost Details, Exports và hóa đơn

### 16.1. Dùng công cụ nào cho mục tiêu nào?

| Nhu cầu | Nguồn dữ liệu phù hợp | Lưu ý |
| --- | --- | --- |
| Xem tổng tiền và xu hướng | **Cost Management → Cost Analysis** | Chọn scope, date range, cost type đúng |
| Xem chi phí từng resource/service | Cost Analysis hoặc **Cost Details** | Một số charges không có resource ID |
| Phân tích hàng triệu dòng hoặc nối với dữ liệu nội bộ | **Cost Management Exports** | Kiểm soát schema, lịch chạy, quyền storage và dữ liệu trễ |
| Đối soát số tiền phải trả và thuế | **Invoices / billing documents** | Phù hợp billing account/agreement và quyền truy cập |
| Dự toán sản phẩm mới | Pricing Calculator và giá áp dụng | Giá công khai chưa chắc là giá hiệu lực |
| Kiểm tra ưu đãi/cam kết | Báo cáo reservation/savings plan và Cost Management | Phân biệt utilization, coverage, purchase và amortized |
| Kiểm tra chi phí bất thường | Cost Analysis, budgets, anomaly alerts hoặc logic quan sát riêng | Alert không tự ngừng tài nguyên |

### 16.2. Thao tác đọc dữ liệu trên Azure Portal

Quy trình khái niệm:

1. Đăng nhập Azure Portal bằng tài khoản được phép xem cost/billing.
2. Mở **Cost Management + Billing** hoặc phạm vi Cost Management thích hợp.
3. Xác minh billing account/profile hoặc subscription đang chọn.
4. Trong **Cost Analysis**, chọn khoảng thời gian và loại cost (actual/amortized nếu khả dụng).
5. **Group by** service, resource group, resource, meter hoặc tag phù hợp để tìm nguồn tăng chi phí.
6. Xem **Cost Details/Exports** nếu cần kiểm tra từng dòng; đối với khoản phải trả, mở **Invoices** ở đúng billing scope.
7. Ghi rõ thời gian lấy dữ liệu, loại cost, currency và filters trong bản báo cáo.

Tên menu và quyền truy cập có thể khác theo agreement và trải nghiệm Azure Portal tại thời điểm dùng. Nếu không thấy Invoices, kiểm tra billing role; không suy ra tài khoản không có hóa đơn.

### 16.3. Những cột cần hiểu khi xem dữ liệu chi tiết

Tên cột chính xác thay đổi theo phiên bản xuất, loại hợp đồng và schema (Cost Details truyền thống hoặc chuẩn như FOCUS). Các khái niệm thường cần đối chiếu:

~~~text
UsageDate
BillingPeriod
SubscriptionId
ResourceGroup / ResourceId
ServiceName / Product / SKU
MeterId / MeterName
UnitOfMeasure
Quantity
EffectivePrice
CostInBillingCurrency
ChargeType / PricingModel
Tags
~~~

**Khối trên là danh sách trường khái niệm, không phải một schema CSV/API bảo đảm có đủ các cột đúng nguyên văn.** Trước khi viết script ETL, hãy đọc header dữ liệu được export thực và mapping sang nghĩa nghiệp vụ. Với một số khoản mua hay support, Resource ID hoặc meter có thể trống.

### 16.4. Ví dụ CSV giản lược để luyện đối soát

~~~csv
Date,Service,Meter,Unit,Quantity,UnitPrice,CostUSD
2026-11-01,Compute,VM hours,Hour,720,0.08,57.60
2026-11-01,Storage,Managed disk,GiB-month,120,0.10,12.00
2026-11-01,Database,Database hours,Hour,720,0.15,108.00
2026-11-01,Storage,Blob capacity,GiB-month,300,0.02,6.00
2026-11-01,Storage,Write operations,10K operations,50,0.004,0.20
2026-11-01,Network,Outbound data,GiB,80,0.07,5.60
2026-11-01,Monitor,Log ingestion,GiB,15,2.00,30.00
~~~

CSV trên **do bài học tự xây dựng**, là bảng tình huống với quantity đã chuẩn hóa cho từng meter, không phải export thật từ Azure. Ngày ở cột Date dùng làm nhãn cho bài toán, không có nghĩa tất cả 720 giờ đều được tiêu thụ riêng ngày 01/11.

Để cộng các dòng ở bảng minh họa bằng Python thuần:

~~~python
import csv
from decimal import Decimal

with open("sample-cost.csv", encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f))

expected = Decimal("0")
for row in rows:
    quantity = Decimal(row["Quantity"])
    price = Decimal(row["UnitPrice"])
    line_cost = Decimal(row["CostUSD"])
    if quantity * price != line_cost:
        raise ValueError(f"Cost mismatch: {row['Service']}/{row['Meter']}")
    expected += line_cost

print(f"Illustrative usage subtotal: {expected:.2f} USD")
# Illustrative usage subtotal: 219.40 USD
~~~

Script chỉ kiểm tra phép nhân/cộng của **CSV đơn giản**. Trong dữ liệu Azure thật, không nên khẳng định mọi dòng luôn bằng quantity × effective unit price do **bậc giá, làm tròn, điều chỉnh, commitment, các dòng đặc biệt hoặc biểu diễn dữ liệu**. Đối soát hóa đơn cần dùng **cost amount do hệ thống billing cung cấp** làm nguồn số tiền đã định giá, sau khi phân loại dòng.

## 17. Quy trình đối soát hóa đơn từng bước

Giả sử Finance nhận hóa đơn với tổng lớn hơn con số mà engineering thấy trong dashboard. Một quy trình đối soát có thể kiểm toán:

### Bước 1 — Chốt phạm vi và tài liệu gốc

Ghi **invoice ID, issuer, billing agreement, billing profile/account, kỳ hóa đơn, đồng tiền và ngày chốt**. Tải chứng từ bằng quyền billing phù hợp. Nếu mua qua CSP, đối chiếu hóa đơn và dữ liệu chi phí do đối tác cung cấp theo hợp đồng.

### Bước 2 — Xuất dữ liệu chi phí đúng scope

Lấy Cost Details/Exports cho đúng billing period và scope có sẵn. Ghi loại cost **actual hoặc amortized**, mốc tạo export và schema. Với bài toán khớp hóa đơn, bắt đầu từ số liệu actual/billed và cấu trúc invoice phù hợp; dùng amortized cho phân tích phân bổ sau đó.

### Bước 3 — Phân loại charge types

Chia các khoản theo loại hợp lệ của dữ liệu: usage, purchase/commitment, Marketplace, support, adjustment/refund và các nhóm khác được hóa đơn thể hiện. **Không cộng totals lặp** hoặc cộng thêm purchase vào một tập usage đã biểu diễn lợi ích cam kết theo cách có thể đếm trùng.

### Bước 4 — Cộng theo currency và dấu của dòng

Chỉ cộng các dòng có cùng đơn vị tiền. Quy ước hoàn tiền/adjustment có thể mang dấu âm và phải giữ nguyên ý nghĩa. Nếu dữ liệu nguồn dùng đồng tiền khác, chỉ quy đổi khi hiểu **tỷ giá, thời điểm và quy tắc billing**, không dùng tỷ giá thị trường hiện tại để “chỉnh” một hóa đơn đã phát hành.

### Bước 5 — Khớp các dòng ngoài usage

Kiểm tra **credits, thuế, support, Marketplace, khoản mua commitment, refund, số dư trước và các điều chỉnh**. Mức credit còn lại không phải lúc nào cũng tương ứng ngay một khoản âm trong chi phí ứng dụng.

### Bước 6 — Phân tích chênh lệch

So sánh:

~~~text
Invoice subtotal (theo loại charges)
  - Exported matching charge subtotal
  = Difference cần phân tích

Invoice amount due
  so với:
    tiền hàng/dịch vụ + điều chỉnh - credit + thuế
    +/- số dư/thanhtoán khác theo tài liệu gốc
~~~

Ưu tiên kiểm tra khác biệt về **scope, kỳ, cost type, tiền tệ, dữ liệu đến trễ** trước khi kết luận meter tính sai. Nếu còn chênh lệch đáng kể, lưu danh sách line item, chứng từ và mốc thời gian rồi mở yêu cầu hỗ trợ billing theo quy trình.

### Bước 7 — Lưu bằng chứng và người phê duyệt

Lưu bản tổng hợp (theo quyền hạn), invoice ID, data snapshot, cách mapping charge types, chênh lệch chưa giải thích và người xử lý. Hóa đơn và dữ liệu billing có thể chứa thông tin tài chính/đơn vị pháp lý; hạn chế quyền chia sẻ và thời gian lưu theo chính sách.

## 18. Phân bổ chi phí cho nhóm và sản phẩm

Resource group và tag hỗ trợ quản trị nhưng không tự giải quyết mọi bài toán phân bổ.

### 18.1. Quy tắc tagging

Một bộ tag thường gặp:

~~~yaml
environment: prod
application: orders-api
owner: ecommerce-platform
costCenter: CC-1002
businessUnit: commerce
managedBy: iac
~~~

Đây là ví dụ metadata để gắn lên tài nguyên, không phải YAML tự động triển khai tag. Tags cần được quản lý bằng IaC và Azure Policy phù hợp.

**Giới hạn:** Không phải mọi charge đều có tag; một số tài nguyên/chi phí chia sẻ không gắn trực tiếp với workload; tag thay đổi hôm nay không bảo đảm dữ liệu lịch sử được cập nhật hồi tố. Vì vậy phân bổ nên có thứ tự:

1. Chi phí gắn trực tiếp resource và tag đủ tin cậy.
2. Phần chia sẻ phân bổ theo phép đo hợp lý, ví dụ resource consumption hoặc số giao dịch.
3. Phần không thể quy thuộc hiển thị riêng là **unallocated/shared cost**.

### 18.2. Shared cost và unit economics

Giả sử một cụm AKS phục vụ ba ứng dụng, tổng phí node trong kỳ là 3.000 USD. Nếu có số liệu CPU/memory usage đủ tin cậy và quy tắc nội bộ đã thống nhất, có thể phân bổ **giả định** 50% cho orders, 30% cho catalog, 20% cho analytics:

| Ứng dụng | Tỷ lệ phân bổ giả định | Chi phí node phân bổ |
| --- | ---: | ---: |
| orders | 50% | 1.500 USD |
| catalog | 30% | 900 USD |
| analytics | 20% | 600 USD |

Đây là **chargeback/showback nội bộ**, không làm hóa đơn Azure tự tách thành ba hóa đơn. Quy tắc phải công khai và có thể tái lập; không phân bổ dựa trên số Pod một cách tùy tiện nếu kích thước Pod hoặc workload khác nhau.

Một thước đo hữu ích là **cost per successful business transaction**:

\[
\text{Cost/transaction} = \frac{\text{Chi phí liên quan đã phân bổ}}{\text{Số giao dịch hoàn tất hợp lệ}}
\]

Đừng bỏ qua SLO và tỉ lệ lỗi. Nếu giảm resource làm đơn hàng thất bại tăng, chi phí hạ tầng có thể giảm nhưng chi phí trên giao dịch thành công lại tăng.

## 19. Dự toán, cảnh báo và kiểm soát ngân sách

### 19.1. Dự toán theo meter

Một bảng dự toán có thể gồm:

| Resource / service | Meter chủ yếu | Driver | Forecast | Nguồn kiểm chứng |
| --- | --- | --- | --- | --- |
| App compute | VM/container compute | Replica × thời gian, CPU/memory | Tải thường + peak | Load test, SKU/plan |
| Database | Provisioned compute/storage | Tier, vCore, GB, backup | Growth và query load | DB metrics, Cost Details |
| Blob | Capacity + operations | Dữ liệu/ngày, retention, writes/reads | GB-month, transaction | Storage metrics |
| Network | Outbound / gateway | GiB/client, cross-region traffic | Theo users và topology | Network metrics |
| Monitor | Log ingestion/retention | GB logs/transaction | Theo sampling/retention | Workspace metrics |
| Commitments | Reservation/savings plan | Baseline ổn định, coverage | Khoản mua và amortization | Utilization và hóa đơn |

Dự toán đúng phải bao gồm **headroom, failover capacity, quota, tải theo mùa, support, data transfer** và tác động của commitment. Đối với chi phí biến động, nên có **base / growth / spike** thay vì một số tiền không có điều kiện.

### 19.2. Budgets và alerts

Azure Cost Management Budgets có thể theo dõi chi phí so với ngân sách và phát cảnh báo theo điều kiện được cấu hình, tùy scope và tính năng hỗ trợ. Một ví dụ quy trình:

- Ngân sách tháng của workload: mức được chủ sản phẩm và Finance phê duyệt.
- Cảnh báo khi forecast hoặc actual cost chạm các ngưỡng nội bộ.
- Thông báo cho owner, SRE và FinOps.
- Người chịu trách nhiệm kiểm tra meter/resource gây tăng chi phí, ghi quyết định và thời hạn xử lý.

**Budget alert không phải van khóa chi tiêu cứng.** Việc tạo budget không mặc nhiên dừng VM, khóa subscription hoặc bảo đảm không vượt ngân sách. Muốn tự động hóa hành động phải thiết kế quy trình riêng có kiểm soát quyền, bảo vệ production và tính đúng đắn nghiệp vụ.

### 19.3. Anomaly detection

Một tăng đột biến có thể là:

- VM chạy không được deallocate.
- Snapshot/backup không được dọn theo chính sách.
- Storage operations tăng vì retry/polling vô hạn.
- Egress tăng khi thay đổi tuyến mạng.
- Log ingestion tăng sau bật debug.
- Query database trở nên đắt sau khi phát hành.
- Commitment không được dùng hết vì workload chuyển vùng/SKU.

Phát hiện bất thường cần **so với baseline và sự kiện nghiệp vụ**: tăng chi phí trong ngày sale có thể hợp lý nếu doanh thu/tỷ lệ giao dịch tăng tương ứng, nhưng vẫn phải xác minh không có lỗi kỹ thuật.

## 20. Những lỗi hiểu hóa đơn hay gặp

| Tình huống | Cách hiểu sai | Cách kiểm tra chính xác hơn |
| --- | --- | --- |
| VM đã tắt nhưng vẫn có phí | “Azure tính nhầm compute” | Phân biệt stopped/deallocated và kiểm tra disk, IP, backup, license |
| Tổng resource group thấp hơn invoice | “Thiếu dòng usage” | Xem billing scope, support, Marketplace, purchase, tax, credit |
| Giá trên web khác Cost Details | “Hệ thống tính tiền sai” | Xem effective price, region, SKU, hợp đồng, bậc giá, currency |
| 500.000 transactions nhưng đơn giá rất nhỏ | “Hệ thống nhân sai” | Kiểm tra meter unit là mỗi transaction hay mỗi 10K |
| Actual cao bất thường vào ngày mua reservation | “Ứng dụng đột nhiên dùng nhiều” | Tách purchase upfront khỏi chi phí vận hành; xem amortized |
| Báo cáo amortized và hóa đơn khác nhau | “Một báo cáo không chính xác” | Hiểu khác biệt giữa phân bổ kinh tế và bút toán thanh toán |
| Không thấy invoice dù xem được VM | “Không có hóa đơn” | Kiểm tra billing account role và agreement |
| Cost hôm nay thấp hơn sau vài ngày | “Azure sửa ngược dữ liệu” | Xem reporting latency và adjustments |
| Cùng mức usage, giá tháng này khác | “Meter không ổn định” | Kiểm tra tier, currency, discount, contract, promotion, price change |
| Tổng USD dự toán khác tiền tệ hóa đơn | “Tỉ giá sai” | Đối chiếu currency và quy tắc tỷ giá trên agreement/invoice |
| Thêm tag hôm nay nhưng báo cáo tháng trước vẫn trống | “Hệ thống tags bị lỗi” | Tag không nhất thiết hồi tố; xem data coverage |
| Tạo budget nhưng vẫn vượt ngưỡng | “Budget thất bại” | Budget là cảnh báo theo cấu hình, không tự dừng tiêu thụ |
| Xóa resource mà vẫn phát sinh phí | “Xóa không thành công” | Kiểm kê disk, snapshot, backup, reserved commitment, resource phụ |
| Một dòng có Quantity nhưng EffectivePrice = 0 | “Dịch vụ miễn phí vĩnh viễn” | Kiểm tra quyền lợi/discount, amortization và chu kỳ ưu đãi |

## 21. Bài thực hành: từ meter đến hóa đơn

**Bối cảnh:** Đội phát triển orders-api đang chuyển từ một môi trường thử nghiệm sang production trên Azure. Mục tiêu là hiểu hóa đơn mà không cần dùng dữ liệu tài chính thật của tổ chức.

### Bài A — Phân loại meter

Một workload có VM, disk, Azure SQL, Blob, outbound traffic và Application Insights. Hãy lập bảng cho mỗi thành phần: **resource, meter, unit, quantity driver, điều kiện có thể tiếp tục bị tính phí khi ứng dụng không hoạt động**.

**Tiêu chí đạt:** Giải thích vì sao xóa hoặc deallocate VM chưa chắc xóa hết chi phí và nhận diện tối thiểu hai khoản không phải compute.

### Bài B — Tính chi phí theo đơn vị

Dùng bảng giả định ở phần 9:

1. Tính VM cost từ 720 hour × 0,08.
2. Tính Storage transactions từ 500.000 operations, đơn vị giá 10K.
3. Cộng subtotal bảy meter.
4. Xem khoản credit 25 USD và adjustment −5 USD ở phần 14 khác chiết khấu trực tiếp lên đơn giá thế nào.
5. Giải thích vì sao không thể suy ra thuế thật từ subtotal.

**Kết quả mong đợi:** 57,60 USD cho VM, 0,20 USD cho operations và 219,40 USD usage subtotal, với các giả định như đã nêu.

### Bài C — Đối soát Cost Management với invoice

Trong môi trường được phép đọc dữ liệu:

1. Xác định agreement type và billing scope của subscription.
2. Mở Cost Analysis cho một kỳ đã chốt và ghi actual cost, currency, date filters.
3. Xuất dữ liệu chi tiết nếu có quyền, nhóm theo charge type, service/meter.
4. Đối chiếu khoản mua, credit, support, Marketplace, tax và adjustments trên invoice thật.
5. Viết một bản ghi đối soát nêu tổng invoice, các nhóm được khớp, chênh lệch còn lại và nguyên nhân.

**Tiêu chí đạt:** Đối chiếu trên **cùng phạm vi và kỳ hóa đơn**, không công bố tên pháp nhân, số chứng từ, giá hợp đồng hay thông tin nhạy cảm ra ngoài nhóm được phép.

### Bài D — Đề xuất tối ưu

Một workload có đặc điểm giả định:

- VM chạy 24/7 nhưng traffic chỉ cao từ 8h đến 18h các ngày làm việc.
- Managed disks và database vẫn được sử dụng bởi tác vụ ngoài giờ.
- Log ingestion tăng gấp ba sau một release.
- Hai reservation hiện chỉ đạt 40% utilization.

Hãy xác định **meter nào có thể giảm thật**, cách kiểm tra không làm hỏng dịch vụ, và vì sao vẫn cần giữ phần disk, database hoặc commitment cost. Xếp ưu tiên dựa trên tác động đến SLO, khả năng rollback và mức tiết kiệm đã kiểm chứng.

**Tiêu chí đạt:** Mỗi đề xuất có baseline, công thức dự báo, điều kiện kiểm chứng và owner; không chỉ ghi “tắt máy” hoặc “mua reservation”.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Một Azure VM có một hay nhiều meter?  
**Đáp án:** Một VM và workload liên quan có thể tạo nhiều meter: compute, disk, networking, backup, phần mềm/monitoring... tùy cấu hình.

**Câu 2.** Tại sao phải xem UnitOfMeasure trước khi nhân đơn giá?  
**Đáp án:** Giá có thể tính trên hour, GiB-month, 10K transactions hoặc đơn vị khác. Nhân sai unit làm dự toán chênh lệch rất lớn.

**Câu 3.** Nếu 500.000 operation được tính theo đơn vị 10.000 operation, quantity là bao nhiêu?  
**Đáp án:** 50 đơn vị.

**Câu 4.** Một hệ thống có giá niêm yết 0,08 USD/hour, nhưng Cost Details hiển thị giá khác. Có nhất thiết là lỗi không?  
**Đáp án:** Không. Có thể do vùng, SKU, hợp đồng, bậc giá, ưu đãi, commitment hoặc cách dữ liệu biểu diễn chi phí.

**Câu 5.** Actual cost và amortized cost có nên cộng để tính invoice?  
**Đáp án:** Không. Chúng có thể là hai cách biểu diễn cùng khoản chi, nhất là với commitment. Phải bắt đầu từ dữ liệu invoice/actual phù hợp.

**Câu 6.** Vì sao hóa đơn lớn hơn tổng cost của một resource group?  
**Đáp án:** Hóa đơn có thể bao gồm nhiều resource group/subscription, commitment purchases, support, Marketplace, taxes và điều chỉnh.

**Câu 7.** Subscription và billing profile có phải một thứ không?  
**Đáp án:** Không. Subscription quản lý phạm vi tài nguyên/tiêu thụ, còn billing profile thuộc cấu trúc thanh toán trong những agreement hỗ trợ.

**Câu 8.** Azure Cost Management Budget có tự chặn mọi khoản phát sinh vượt ngân sách không?  
**Đáp án:** Không. Budget là cơ chế theo dõi/cảnh báo, còn hành động giới hạn chi tiêu cần quy trình khác phù hợp.

**Câu 9.** Xóa VM sẽ làm hết mọi chi phí của ứng dụng ngay lập tức?  
**Đáp án:** Không chắc. Disk, snapshot, IP, database, logs, backup và commitments còn tồn tại có thể tiếp tục tạo phí.

**Câu 10.** Tại sao cần lưu ngày xuất Cost Details khi reconcile?  
**Đáp án:** Vì usage, adjustments và invoice data có thể được ghi nhận trễ hoặc cập nhật, khiến hai bản xuất ở hai thời điểm khác nhau.

**Câu 11.** Một AKS node pool dùng chung cho ba nhóm có thể chia chi phí trực tiếp theo số namespace trên hóa đơn không?  
**Đáp án:** Thông thường không. Phí tài nguyên chia sẻ cần một phương pháp showback/chargeback dựa trên metrics và quy tắc nội bộ.

**Câu 12.** Pricing Calculator có thay thế hóa đơn chính thức khi quyết toán không?  
**Đáp án:** Không. Calculator phục vụ dự toán; thanh toán phải theo chứng từ, giá và điều kiện áp dụng cho khách hàng.

## 23. Checklist vận hành chi phí trên Azure

- [ ] Phân biệt resource, SKU, meter, unit, quantity, unit price và effective price.
- [ ] Kiểm tra pricing model của compute, storage, database, network và monitoring.
- [ ] Biết tài nguyên nào tiếp tục tính phí sau stop/deallocate/xóa ứng dụng.
- [ ] Xác định đúng agreement, billing scope, kỳ và đồng tiền của hóa đơn.
- [ ] Đọc được usage, purchase, adjustments/refunds, credit, tax, support và Marketplace.
- [ ] Không cộng actual cost với amortized cost hoặc đếm trùng commitment.
- [ ] Dùng Cost Analysis cho xu hướng, Cost Details/Exports cho đối soát chi tiết và invoice cho thanh toán.
- [ ] Có quy trình reconciliation với invoice ID, data snapshot, chênh lệch và người phê duyệt.
- [ ] Tags/owner/cost center được quản trị, nhưng chi phí không tag và shared cost vẫn được theo dõi.
- [ ] Đã kiểm tra utilization/coverage trước khi mua reservation hoặc savings plan.
- [ ] Có budgets, alerts và quy trình xử lý tăng chi phí bất thường.
- [ ] Dự toán mới dựa trên giá đúng vùng, SKU, offer, currency và workload thật.
- [ ] Chia sẻ dữ liệu billing đúng quyền, không lộ giá hợp đồng hoặc chứng từ nhạy cảm.

Hiểu đúng chi phí Azure bắt đầu từ **meter nào đang đo cái gì**, rồi đến **điều kiện giá và quyền lợi nào được áp dụng**, và cuối cùng là **khoản phí nào thực sự xuất hiện trên hóa đơn của billing account**. Khi phân biệt rõ ba tầng này, đội kỹ thuật và tài chính có thể đối soát minh bạch, tìm chi phí bất thường và tối ưu kiến trúc mà vẫn bảo đảm hiệu năng, độ tin cậy và an toàn của ứng dụng.
