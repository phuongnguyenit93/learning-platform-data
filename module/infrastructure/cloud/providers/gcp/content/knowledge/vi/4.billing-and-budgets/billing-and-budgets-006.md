# Phân biệt cảnh báo ngân sách với cơ chế giới hạn tài nguyên

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Giải thích sự khác nhau giữa **Cloud Billing budget cảnh báo (alerts-only budget)**, **hạn ngạch tài nguyên (quota)**, **giới hạn hệ thống (system limit)** và **giới hạn do ứng dụng/dịch vụ cấu hình**.
2. Nhận biết trường hợp có thể dùng **spend cap budget** trên một số dịch vụ Google Cloud đủ điều kiện và các giới hạn của cơ chế này.
3. Hiểu vì sao **đặt ngân sách 100 USD không mặc nhiên ngăn hóa đơn vượt 100 USD**, và vì sao chạm quota cũng không có nghĩa chi phí sẽ về 0.
4. Chọn lớp kiểm soát phù hợp cho Compute Engine, Cloud Run, GKE, Cloud Storage, BigQuery và tài nguyên liên quan.
5. Thiết kế cơ chế quản trị chi phí theo nhiều lớp: dự toán, cảnh báo, kiểm soát tài nguyên, phản ứng sự cố, phân quyền và theo dõi thực tế.

## 1. Bối cảnh: cùng một mục tiêu nhưng ba câu hỏi khác nhau

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học triển khai Google Cloud từ cấu trúc organization/project, IAM, VPC tới Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu; đồng thời cần bảo vệ tài nguyên, tự động phát hành, duy trì độ tin cậy và theo dõi chi phí. Chi phí tăng ngoài dự kiến có thể bắt nguồn từ một VM quên tắt, autoscaling tăng mạnh, log phát sinh đột biến, dữ liệu tăng dần hoặc truy vấn phân tích lặp đi lặp lại.

Giả sử nhóm vận hành một API có ngân sách tháng **500 USD**. Họ tạo cảnh báo ở mức 50%, 80% và 100%, rồi tin rằng API sẽ tự dừng khi chi tiêu đạt 500 USD. Giả định này có thể gây rủi ro: **alerts-only budget có chức năng thông báo, không tự khóa dịch vụ hoặc dừng tính phí**.

Để thiết kế đúng, cần phân biệt:

- **Ngân sách cảnh báo** trả lời: *Chi phí đang tiến đến hoặc vượt kế hoạch chưa, ai cần biết để xử lý?*
- **Quota hoặc giới hạn tài nguyên** trả lời: *Được cấp phát bao nhiêu CPU, gửi bao nhiêu yêu cầu hoặc chạy bao nhiêu instance trong một phạm vi cụ thể?*
- **Spend cap budget**, nếu sản phẩm và tài khoản hỗ trợ, trả lời: *Có thể tạm dừng mức sử dụng mới của một dịch vụ đủ điều kiện theo mức chi tiêu ước tính không?*

Một hệ thống an toàn về chi phí thường cần phối hợp cả cảnh báo và các rào chắn kỹ thuật, vì không có một cấu hình duy nhất bao phủ toàn bộ nguồn chi phí và rủi ro vận hành.

## 2. Bảng so sánh các cơ chế

| Cơ chế | Đơn vị chính | Tác dụng khi chạm ngưỡng | Phạm vi điển hình | Có bảo đảm hóa đơn không vượt ngưỡng tiền? |
|---|---|---|---|---|
| **Alerts-only Cloud Billing budget** | Tiền tệ: USD, VND tương ứng tài khoản thanh toán | Gửi thông báo dựa trên chi phí thực tế hoặc dự báo, có thể phát sự kiện Pub/Sub | Billing account, project, folder, service, label theo cấu hình được hỗ trợ | **Không** |
| **Spend cap budget** cho dịch vụ đủ điều kiện | Tổng chi phí gộp *ước tính* của một dịch vụ trong tháng | Tạm dừng phát sinh sử dụng mới của dịch vụ được chọn sau khi cap có hiệu lực | Một project và một dịch vụ đủ điều kiện | **Không tuyệt đối**: có độ trễ, phần sử dụng đang xử lý và chi phí ngoài phạm vi |
| **Allocation quota** | Số lượng tài nguyên/công suất: CPU, địa chỉ IP, instance... | Thường từ chối cấp thêm khi vượt hạn ngạch | Theo project, region/zone, service hoặc chiều khác do dịch vụ định nghĩa | **Không** |
| **Rate quota** | Số yêu cầu hoặc lượng sử dụng trên đơn vị thời gian | Thường từ chối/giới hạn yêu cầu vượt ngưỡng | Theo project, API, khu vực hoặc bên tiêu thụ | **Không** |
| **Concurrent quota** | Số tác vụ đang chạy đồng thời | Hạn chế tác vụ mới vượt mức đồng thời | Theo dịch vụ và phạm vi quota | **Không** |
| **System limit** | Giới hạn kỹ thuật cố định | Ngăn thao tác vượt khả năng do sản phẩm quy định | Theo tài nguyên/dịch vụ | **Không** |
| **Giới hạn cấu hình dịch vụ** | Max instances, số node, số bytes xử lý mỗi truy vấn... | Giảm tốc độ tạo hoặc mức sử dụng của thành phần cụ thể | Theo workload | **Không** |

**Lưu ý về thuật ngữ:** Cloud Billing hiện phân biệt **alerts-only budget** và **spend cap budget**. Vì vậy không nên nói chung chung rằng *mọi loại budget của Google Cloud đều chỉ cảnh báo*. Bài này giải thích cơ chế của từng loại, đồng thời nhấn mạnh rằng không có cơ chế nào là bảo đảm tuyệt đối cho tổng hóa đơn của toàn bộ hệ thống.

## 3. Alerts-only budget: quản lý kế hoạch chi tiêu bằng tín hiệu

### 3.1. Ngân sách cảnh báo hoạt động ra sao?

Cloud Billing cho phép tạo **alerts-only budget** để so sánh mức tiêu dùng ghi nhận với khoản tiền mục tiêu. Một budget thường có:

1. **Phạm vi theo dõi**: toàn bộ billing account hoặc tập project, service, folder/organization, label phù hợp.
2. **Kỳ ngân sách**: ví dụ tháng, quý, năm hoặc một khoảng tùy chỉnh theo khả năng công cụ.
3. **Số tiền ngân sách**: số cố định hoặc dựa trên kỳ trước.
4. **Quy tắc ngưỡng**: chẳng hạn 50%, 80%, 100%; có thể dựa trên **actual cost** hoặc **forecasted cost** khi thiết lập phù hợp.
5. **Người nhận và kênh**: email đến đối tượng được cấu hình, liên kết kênh Cloud Monitoring, hoặc sự kiện Pub/Sub để xử lý bằng phần mềm.

Ví dụ: một budget thử nghiệm **500 USD/tháng** được đặt ngưỡng chi phí thực tế 50%, 80%, 100%.

| Ngưỡng | Mức tiền minh họa | Tín hiệu | Điều **không** xảy ra tự động với alerts-only budget |
|---|---:|---|---|
| 50% | 250 USD | Nhắc nhóm kiểm tra xu hướng sử dụng | Không giảm quota CPU, không xóa VM |
| 80% | 400 USD | Yêu cầu rà soát nguồn tăng chi phí | Không tắt autoscaling, không khóa API |
| 100% | 500 USD | Báo đã đạt/vượt ngân sách dựa trên dữ liệu ghi nhận | Không tự dừng dịch vụ và không bảo đảm dừng hóa đơn ở 500 USD |

Nếu tiêu thụ tiếp tục, tổng chi phí có thể vượt 500 USD. Nếu hóa đơn đã phát sinh nhanh hơn tốc độ tổng hợp dữ liệu, mức chi thực tại thời điểm nhận email có thể cao hơn giá trị vừa được thông báo.

### 3.2. Actual cost và forecasted cost

- **Actual cost threshold**: thông báo khi số tiền đã được hệ thống ghi nhận cho phạm vi/kỳ budget đạt ngưỡng.
- **Forecasted cost threshold**: thông báo khi thuật toán dự báo tổng chi phí kỳ hiện tại sẽ đạt ngưỡng, dù chi phí ghi nhận còn thấp.

Forecast giúp cảnh báo sớm, nhưng chỉ là **ước tính dựa trên thông tin hiện có**. Dự báo có thể thay đổi theo mẫu sử dụng và chưa chắc phản ánh một sự kiện tăng tải bất thường sắp xảy ra.

### 3.3. Độ trễ và các giới hạn cần nhớ

- **Chi phí có độ trễ xử lý và báo cáo**; không xem budget alert như công tắc đóng/mở theo thời gian thực.
- Thông báo **không nhất thiết đến tức thì** ngay khi một request làm vượt ngưỡng.
- Đặt nhiều ngân sách cho những phạm vi giao nhau có thể tạo **nhiều thông báo cho cùng một chi phí**; cần có quy tắc phân loại và người chịu trách nhiệm.
- Budget theo một project không bao phủ chi phí ở project khác nếu không nằm trong phạm vi đã chọn.
- **Cảnh báo là tín hiệu cần hành động**. Nếu không ai nhận, không ai trực, hoặc không có runbook thì cảnh báo ít giá trị.

### 3.4. Thiết lập alerts-only budget trong Console

Quy trình thực hành (tên nút có thể thay đổi theo giao diện):

1. Vào **Google Cloud Console → Billing → Budgets & alerts** và chọn billing account hoặc project có quyền quản trị chi phí thích hợp.
2. Tạo **alerts-only budget**; xác nhận đúng account, project và phạm vi service.
3. Chọn kỳ **Monthly** hoặc kỳ phù hợp; nhập số tiền dự toán được phê duyệt.
4. Cấu hình ngưỡng, chẳng hạn **50%, 80%, 100% actual**, và thêm **100% forecast** nếu có ích.
5. Chọn người nhận email và kênh cảnh báo; cân nhắc tích hợp **Pub/Sub** khi có ứng dụng xử lý sự kiện.
6. Lưu, sau đó kiểm tra lại phạm vi, ngưỡng, danh tính người chịu trách nhiệm và dashboard chi phí.

Để thao tác, người dùng cần các **quyền Cloud Billing thích hợp**. Quyền tạo budget và quyền tạo máy ảo/triển khai ứng dụng là những nhóm quyền khác nhau.

## 4. Spend cap budget: trường hợp ngân sách có cơ chế thực thi

Tài liệu Cloud Billing hiện có loại **spend cap budget** dành cho **dịch vụ đủ điều kiện**, khác với alerts-only budget.

### 4.1. Cơ chế thực thi

- Tạo spend cap cho **một project, một dịch vụ đủ điều kiện**, với **kỳ tháng** bắt đầu từ ngày đầu tháng.
- Google Cloud theo dõi **gross estimated usage costs** (chi phí gộp ước tính, dựa trên giá niêm yết, chưa tính credits/discounts).
- Khi số tiền ước tính vượt 100% cap, hệ thống **tạm dừng sử dụng mới** của dịch vụ đã chọn trong project đó cho tới khi cap được gỡ hoặc kỳ mới bắt đầu.
- Những yêu cầu đang thực thi có thể hoàn tất và tiếp tục phát sinh chi phí. Các chi phí cố định từ tài nguyên tồn tại liên tục có thể **không bị dừng**.
- Quá trình thực thi không tức thời. **Chi phí vượt mức vẫn có thể được tính bình thường**.

Theo danh sách dịch vụ đủ điều kiện được tài liệu Google Cloud công bố khi biên soạn bài này, spend cap hỗ trợ **Gemini API**, **Gemini Enterprise Agent Platform (trước đây là Vertex AI)**, **Cloud Run** và **Cloud Run functions**. Phải kiểm tra danh sách hiện hành và điều kiện áp dụng trước khi lập chính sách; không suy rộng sang Compute Engine, GKE, Cloud Storage, Cloud SQL hoặc toàn bộ Google Cloud.

Spend cap có các giới hạn đáng chú ý: không áp dụng cùng lúc cho nhiều project/dịch vụ, không dùng kỳ tùy chỉnh, không bao trùm ngân sách theo labels/folders/organization; một số nhóm khách hàng hoặc loại chi phí không đủ điều kiện. Nếu cap đã được kích hoạt, **khả năng sẵn sàng của ứng dụng** có thể bị ảnh hưởng vì yêu cầu mới bị chặn.

### 4.2. Ví dụ diễn giải

Một project dùng **Cloud Run** và **Cloud SQL**:

- Nhóm đặt **spend cap 100 USD** cho Cloud Run nếu loại budget này được hỗ trợ trong tài khoản.
- Khi cap được thực thi, **sử dụng mới thuộc Cloud Run** trong project bị tạm dừng theo cơ chế sản phẩm.
- **Cloud SQL, lưu trữ hoặc tài nguyên khác** nằm ngoài phạm vi cap vẫn có thể phát sinh chi phí.
- Chi phí Cloud Run vượt ngưỡng do **độ trễ hoặc request đang xử lý** vẫn có thể được ghi nhận.

Vì vậy, spend cap là **rào chắn chi phí có điều kiện của một dịch vụ**, không phải giới hạn tổng hóa đơn 100 USD cho project.

### 4.3. Khi nào cân nhắc spend cap?

Hữu ích với **môi trường thử nghiệm hoặc workload có thể tạm dừng khi đạt cap**. Với hệ thống production có SLO nghiêm ngặt, cần đánh giá kỹ hậu quả chặn lưu lượng trước khi sử dụng: tiết kiệm được một khoản tiền có thể đi kèm lỗi dịch vụ và mất doanh thu lớn hơn.

## 5. Quotas và system limits: rào chắn tài nguyên thay vì rào chắn tiền

Google Cloud áp dụng **quotas** và **system limits** nhằm chia sẻ tài nguyên công bằng, bảo vệ dịch vụ và giới hạn mức tiêu thụ trong phạm vi kỹ thuật.

### 5.1. Ba loại quota

| Loại | Đặc điểm | Ví dụ minh họa | Khi chạm ngưỡng |
|---|---|---|---|
| **Allocation quota** | Giới hạn lượng tài nguyên được cấp phát | CPU Compute Engine theo region, số lượng địa chỉ IP | Không tạo thêm tài nguyên nếu vượt quota |
| **Rate quota** | Giới hạn sử dụng API hoặc dịch vụ theo một khoảng thời gian | Số request mỗi phút | Request vượt mức có thể bị từ chối/điều tiết; thử lại sau theo hướng dẫn |
| **Concurrent quota** | Giới hạn số tác vụ đang chạy đồng thời | Số tác vụ dài đang được xử lý | Tác vụ mới có thể bị từ chối cho đến khi đủ suất |

Các **system limits** là giới hạn kỹ thuật cố định do dịch vụ đặt ra và thường không thể thay đổi; ngược lại, quota có thể có cơ chế yêu cầu điều chỉnh (tăng hoặc giảm tùy loại và phạm vi).

### 5.2. Ví dụ: CPU quota không phải giới hạn hóa đơn

Giả sử một project có **quota 32 vCPU** trong region đang xét và đã phân bổ 32 vCPU cho VM:

1. Lệnh tạo thêm một VM cần 4 vCPU có thể bị từ chối vì thiếu quota.
2. **32 vCPU đã cấp phát vẫn chạy và được tính phí** theo loại tài nguyên, trạng thái và chính sách giá liên quan.
3. Disk, địa chỉ IP, lưu lượng ra ngoài và dịch vụ khác vẫn có thể phát sinh phí.
4. Việc giảm quota không đồng nghĩa đã dừng VM hiện có; cần xem hành vi của từng quota và dịch vụ.

Với rate quota, một API có giới hạn 1.000 yêu cầu/phút (giả định) có thể từ chối request thứ 1.001, nhưng **chi phí Compute Engine hoặc lưu trữ đang hoạt động không tự giảm**.

### 5.3. Quota khác budget như thế nào?

**Budget** đo số tiền đã ghi nhận/dự báo cho **phạm vi billing**. **Quota** giới hạn **loại và số lượng tài nguyên/hoạt động** trong phạm vi mà API hoặc dịch vụ định nghĩa. Chúng không thể quy đổi trực tiếp:

~~~text
Budget 500 USD/tháng
    Không suy ra:
       CPU quota = 16 vCPU
       Cloud Run max instances = 5
       BigQuery quota = X truy vấn/phút

Muốn đặt giới hạn kỹ thuật:
    Ước tính giá + dự báo tải + đo thực tế
    → chọn quota/giới hạn cho từng tài nguyên
    → đánh giá lại độ tin cậy và ngân sách
~~~

Một quota thấp có thể **ngăn autoscaling cần thiết**, gây lỗi hoặc suy giảm chất lượng phục vụ. Một quota cao giúp ứng dụng đáp ứng tải lớn hơn nhưng không tự cho biết chi phí sẽ là bao nhiêu.

### 5.4. Xem và điều chỉnh quota

Trong Console:

1. Chọn **project** cần kiểm tra.
2. Đi tới **IAM & Admin → Quotas & System Limits**.
3. Lọc theo **Service**, **Quota** và **Location**; quan sát quota hiện tại và mức sử dụng.
4. Xác định quota là **rate/allocation/concurrent**, phạm vi project/region và khả năng thay đổi.
5. Nếu dịch vụ cho phép, gửi **yêu cầu điều chỉnh** qua giao diện hoặc API/CLI phù hợp, dựa trên quyền được cấp.

Đừng mặc định có thể hạ mọi quota: loại quota, mức tối thiểu, giới hạn nền tảng và quyền quản trị có thể khác nhau. Nhiều yêu cầu tăng quota phải được phê duyệt. Thay đổi quota cho production cần đánh giá hiệu năng, hành vi khi bị từ chối và rủi ro gián đoạn trước khi áp dụng.

## 6. Giới hạn cấu hình theo dịch vụ: kiểm soát tốc độ tiêu thụ

Quotas là một lớp. Nhiều dịch vụ còn có **tham số cấu hình riêng** giúp kiểm soát số tài nguyên được tạo hoặc khối lượng công việc.

| Dịch vụ/tình huống | Công cụ giới hạn có thể áp dụng | Điều vẫn có thể phát sinh phí |
|---|---|---|
| **Cloud Run** API tăng traffic | **Maximum instances**, concurrency, CPU/memory, điều chỉnh min instances | Request, CPU/memory, network egress, log và các dịch vụ backend; max instances có thể tạm vượt trong một số tình huống |
| **Compute Engine** | Quota CPU/instance, hạn chế loại máy theo chính sách phù hợp; automation tắt môi trường thử nghiệm | VM đang chạy, disk, snapshot, IP, traffic, license |
| **GKE** | Cluster/node pool autoscaling min/max, resource requests/limits, quota namespace phù hợp | Node đang cấp phát, persistent volume, mạng, logging, cluster management |
| **Cloud Storage** | Object lifecycle, retention, quy tắc quản trị ghi/xóa và phân loại dữ liệu | Dung lượng tồn tại, request, egress, phí liên quan đến lưu trữ/khôi phục/xóa sớm tùy lớp lưu trữ |
| **BigQuery** | **maximum bytes billed** theo truy vấn, quota phù hợp, quyền chạy job/đặt reservation nếu áp dụng | Storage, job khác, slot reservation hoặc các dịch vụ liên quan |
| **Cloud SQL** | Chọn cấu hình kích thước và HA phù hợp, kiểm soát provisioning và backup | Instance, lưu trữ, backup và network liên tục trong phạm vi giá áp dụng |

### 6.1. Cloud Run max instances

Ví dụ đọc trạng thái dịch vụ trước khi quyết định điều chỉnh:

~~~bash
gcloud run services describe SERVICE_NAME \
  --project=PROJECT_ID \
  --region=REGION
~~~

Sau khi được phê duyệt, có thể đặt giới hạn số instance ở cấp dịch vụ:

~~~bash
gcloud run services update SERVICE_NAME \
  --project=PROJECT_ID \
  --region=REGION \
  --max=3
~~~

**Đây là một giới hạn số instance, không phải nút khóa tiền.** Cloud Run có thể tạm vượt mức tối đa trong lúc tăng tải hoặc chuyển phiên bản; việc giới hạn instance có thể khiến request phải chờ hoặc lỗi khi hết khả năng xử lý. Cần kiểm tra SLO, concurrency, thời gian xử lý và phụ thuộc vào Cloud SQL trước khi chọn con số.

### 6.2. GKE autoscaling và requests/limits

Giả sử node pool có thể tự tăng từ 2 đến 6 node. Giới hạn tối đa giúp tránh autoscaler nhân node vô hạn trong nhóm này, nhưng:

- Tối đa 6 node **không có nghĩa tối đa 6 đơn vị chi phí**: loại VM, disk, các node pool khác, lưu trữ và network vẫn ảnh hưởng đến hóa đơn.
- **Kubernetes CPU/memory limits** kiểm soát mức tiêu thụ container; không trực tiếp chặn chi phí toàn cluster.
- Khi không còn đủ node, pod có thể **Pending**. Giảm giới hạn quá thấp có thể làm ứng dụng không đáp ứng tải.

### 6.3. Cloud Storage lifecycle và BigQuery

- **Object lifecycle** hỗ trợ chuyển lớp lưu trữ hoặc xóa object theo điều kiện. Đây là cách giảm tích lũy dung lượng theo thời gian; phải đánh giá yêu cầu retention, khôi phục, chính sách xóa sớm và các chi phí dữ liệu khác.
- **BigQuery maximum bytes billed** có thể chặn một truy vấn on-demand được ước tính xử lý nhiều dữ liệu hơn ngưỡng đã đặt. Nó không ngăn tất cả chi phí BigQuery khác, cũng không tự thay thế kiểm soát tổng chi phí và quyền truy cập.

## 7. Chọn giải pháp nào cho mục tiêu kiểm soát chi phí?

Một cách thiết kế thực tế là chia thành các lớp bổ trợ:

~~~mermaid
flowchart TB
    A["Mục tiêu kinh doanh và mức rủi ro chấp nhận được"] --> B["Dự toán tải và giá thành"]
    B --> C["Alerts-only budget: quan sát và cảnh báo"]
    B --> D["Quota, giới hạn cấu hình: hạn chế tiêu thụ"]
    B --> E["Spend cap nếu dịch vụ và tài khoản đủ điều kiện"]
    C --> F["Runbook và người chịu trách nhiệm"]
    D --> F
    E --> F
    F --> G["Quan sát chi phí, độ tin cậy, điều chỉnh định kỳ"]
    G --> B
~~~

| Nhu cầu | Ưu tiên | Kiểm tra đánh đổi |
|---|---|---|
| Biết trước khi chi phí vượt kế hoạch | Budget forecast/actual alerts, báo cáo chi phí, người nhận | Độ trễ, tín hiệu giả, ai trực xử lý |
| Ngăn autoscaling của một API tăng quá mạnh | Cloud Run max instances hoặc giới hạn autoscaling tương ứng | Request bị lỗi, latency tăng khi chạm trần |
| Ngăn tạo thêm nhiều VM | Allocation quota, IAM/organization policies khi phù hợp | Không chặn VM/disk đang tồn tại; có thể cản vận hành |
| Chặn một số request API tăng đột biến | Rate quota, throttling ở ứng dụng/API gateway | Client cần backoff; nguy cơ từ chối request hợp lệ |
| Kiểm soát dịch vụ trả phí theo truy vấn | Giới hạn bytes billed/query, quyền truy cập và theo dõi job | Chỉ tác động loại truy vấn và mô hình giá được hỗ trợ |
| Muốn dừng sử dụng mới khi đạt một khoản tiền cho **dịch vụ đủ điều kiện** | Spend cap budget nếu đáp ứng điều kiện | Tạm dừng dịch vụ, không khóa chi phí khác hoặc vượt mức do độ trễ |
| Giảm chi phí môi trường dev/test qua đêm | Lịch tắt tài nguyên, autoscaling và xóa tài nguyên tạm theo vòng đời | Phải loại trừ production, giữ dữ liệu cần thiết |

## 8. Tự động hóa phản ứng với cảnh báo: thêm hành động nhưng không có bảo đảm cứng

**Alerts-only budget** có thể gửi thông báo chương trình qua **Pub/Sub**; đội vận hành có thể xây workflow nhận sự kiện, đánh giá và thực hiện hành động được cho phép.

~~~mermaid
flowchart LR
    A["Cloud Billing alerts-only budget"] --> B["Pub/Sub budget notification"]
    B --> C["Cloud Run function / workflow"]
    C --> D{"Đúng phạm vi và điều kiện?"}
    D -->|Chưa rõ| E["Gửi cảnh báo và yêu cầu người duyệt"]
    D -->|Đã xác nhận| F["Hành động đã định nghĩa cho workload"]
    F --> G["Ghi log, xác minh, theo dõi"]
~~~

Ví dụ, sự kiện ngưỡng 80% của **project thử nghiệm** có thể tạo ticket, gửi thông báo và đề xuất tắt một VM lab đã được gắn nhãn tự hủy. Nếu muốn tự dừng, workflow cần xác thực đúng project, nhãn, người sở hữu, loại tài nguyên và có trạng thái **dry-run** để kiểm thử trước.

### Giới hạn và rủi ro

- **Độ trễ báo cáo** có thể khiến chi phí vượt budget trước khi hành động được thực thi.
- Sự kiện có thể được gửi lại; logic xử lý cần **idempotent**, tránh thực hiện lặp thay đổi nguy hiểm.
- Tự động tắt service có thể gây **downtime**, mất luồng dữ liệu hoặc ảnh hưởng người dùng; không áp dụng trực tiếp cho production nếu chưa có chấp thuận và phương án khôi phục.
- Dừng một loại tài nguyên **không dừng tất cả hóa đơn** (disk, snapshot, dữ liệu, tài nguyên khác vẫn có thể tính phí).
- Dùng Cloud Billing API để **disable billing** có thể làm dịch vụ ngừng hoạt động, ảnh hưởng tài nguyên và không bảo đảm hồi phục đầy đủ. Đây là biện pháp rủi ro cao, không phải cách mặc định để bảo vệ ngân sách.

Một workflow chi phí tốt có **mốc cảnh báo**, **người chịu trách nhiệm**, **phạm vi hành động**, **kiểm chứng**, **rollback** và **hồ sơ kiểm toán**. Tạo cảnh báo chưa đồng nghĩa đã có hệ thống tự động hóa.

## 9. Tình huống: dự án bán hàng chạy Cloud Run, Cloud SQL và Cloud Storage

Giả sử startup **Minh An** có project **store-dev** và **store-prod**. API Java/Spring chạy trên Cloud Run, dùng PostgreSQL trên Cloud SQL, ảnh sản phẩm trong Cloud Storage, có cron job tạo báo cáo và pipeline CI/CD. Nhóm muốn ngân sách cho dev ở mức **300 USD/tháng** và theo dõi production ở **2.000 USD/tháng**.

Những con số là **giả định đào tạo**, không phải mức chi phí dự báo của Google Cloud. Để dùng thật phải ước lượng qua công cụ định giá và số liệu tải.

### 9.1. Sai lầm ban đầu

Nhóm đặt budget dev 300 USD với ngưỡng 100%, rồi kết luận: “Dev không thể vượt 300 USD”. Trong khi đó, một vòng CI chạy sai tạo nhiều request, VM dùng cho kiểm thử database quên tắt và dung lượng Cloud Storage tăng mỗi ngày.

Phân tích:

1. Alerts-only budget có thể **gửi tín hiệu khi mức chi ghi nhận đủ cao**, nhưng không chặn workload.
2. VM hiện có vẫn hoạt động dù quota CPU không cho tạo VM mới.
3. Cloud Storage lưu dữ liệu tiếp tục phát sinh phí trong phạm vi áp dụng.
4. Nếu chỉ đặt **Cloud Run max instances**, phần Cloud SQL, Storage, network và CI vẫn nằm ngoài giới hạn đó.
5. Nếu chọn **spend cap** cho Cloud Run (khi đủ điều kiện), cap chỉ áp dụng dịch vụ trong phạm vi đã chọn, không bảo đảm tổng chi phí dev dừng ở 300 USD.

### 9.2. Thiết kế kiểm soát theo lớp

| Lớp | Dev (có thể gián đoạn) | Prod (ưu tiên độ tin cậy) |
|---|---|---|
| **Ngân sách** | Alerts-only 300 USD/tháng; ngưỡng 50/80/100% và forecast | Alerts-only 2.000 USD/tháng; ngưỡng 50/80/100% và forecast |
| **Người xử lý** | Nhóm dev nhận email/ticket; xử lý trong ngày | Người trực vận hành và chủ sản phẩm có escalation |
| **Cloud Run** | Max instances thấp theo tải test; xem xét spend cap nếu dịch vụ/tài khoản hỗ trợ | Max instances theo SLO và tải đỉnh; kiểm thử trước khi giới hạn |
| **Compute Engine** | Quota phù hợp, lịch tắt VM lab, giới hạn quyền tạo máy | Quota đủ dự phòng; đánh giá rủi ro khi thay đổi |
| **Cloud Storage** | Xóa dữ liệu thử nghiệm theo lifecycle và chính sách dữ liệu | Lưu giữ dữ liệu theo nghiệp vụ, backup và yêu cầu pháp lý |
| **Cloud SQL** | Quy mô hợp lý, chỉ bật HA nếu bài toán cần | Khả dụng, khôi phục, backup và cấu hình theo yêu cầu |
| **CI/CD** | Giới hạn quyền deploy, kiểm soát job lặp | Có phê duyệt, kiểm thử, rollout và rollback |
| **Giám sát chi phí** | Dashboard theo service, project, environment | Xu hướng theo service, cost per order, cảnh báo bất thường |

Nhóm cần xác định **chi phí nền** (VM, Cloud SQL, disk, lưu trữ cố định), **chi phí biến đổi** (request, compute theo tải, logging, egress) và **chi phí bị bỏ sót** (snapshot, backup, transfer hoặc môi trường phụ). Chính phần chi phí nền là lý do quotas và giới hạn request không biến thành mức trần hóa đơn.

### 9.3. Một chu kỳ xử lý ví dụ

| Tín hiệu | Kiểm tra | Hành động phù hợp |
|---|---|---|
| Dev 50% budget nhưng mới đầu tháng | Reports theo service, tài nguyên mới tạo | Rà soát xu hướng và người sở hữu |
| Dev 80%, Cloud Run request tăng | Lưu lượng hợp lệ hay job lỗi? Max instances hiện tại? | Giảm lưu lượng thử nghiệm, sửa job, điều chỉnh giới hạn sau kiểm thử |
| Dev 100% | Độ trễ dữ liệu billing, VM lab, Storage, SQL, egress | Ưu tiên xử lý nguồn chi phí lớn; cảnh báo chủ dự án |
| Production cost forecast vượt ngân sách | Đối chiếu nhu cầu kinh doanh và traffic, giá và SLO | Điều tra, tối ưu cấu hình có kiểm soát; không tùy tiện dừng dịch vụ |
| Tăng quota CPU do autoscaling bị chặn | Mức sử dụng, giá VM, yêu cầu khả dụng | Chỉ nâng quota sau khi xác minh năng lực và ngân sách |

### 9.4. Chỉ số cần theo dõi

- **Chi phí theo project, môi trường, dịch vụ và đơn vị sản phẩm** (ví dụ chi phí mỗi 1.000 request hay mỗi đơn hàng).
- **Tốc độ tăng chi phí trong kỳ** và độ lệch so với dự báo.
- **Sử dụng quota và thời điểm chạm quota**, có ảnh hưởng đến lỗi/latency hay không.
- **Số instance thực tế, vCPU, dung lượng lưu trữ và lượng dữ liệu ra ngoài**.
- **Tỷ lệ cảnh báo được xác nhận/xử lý đúng hạn**, nguyên nhân và hành động đã thực hiện.
- **SLO và chất lượng phục vụ** sau khi áp dụng giới hạn.

## 10. Quy trình chọn giới hạn trong một dự án GCP mới

1. **Xác định giá trị kinh doanh và ngưỡng rủi ro:** môi trường nào được phép tạm dừng? Production yêu cầu tính sẵn sàng bao nhiêu?
2. **Ước lượng chi phí:** thành phần cố định, biến đổi, tình huống tải bình thường và tăng đột biến, region, lưu trữ, egress, database.
3. **Đặt alerts-only budget trước:** đúng billing scope và ngưỡng, thêm người nhận có trách nhiệm thực hiện hành động.
4. **Đặt quota và giới hạn dịch vụ:** theo khả năng chịu tải đã thử nghiệm, không lấy số từ budget quy đổi máy móc.
5. **Xác minh khả năng spend cap nếu cần:** chỉ các dịch vụ đủ điều kiện; kiểm tra ảnh hưởng khi cap được thực thi.
6. **Xây runbook:** điều tra, xác định người quyết định, đánh giá rủi ro khi giảm tài nguyên và cách phục hồi.
7. **Kiểm thử hành vi giới hạn:** tạo tải mô phỏng để kiểm tra lỗi, latency, retry, monitoring; không cần cố tạo hóa đơn cao.
8. **Theo dõi định kỳ:** điều chỉnh hạn ngạch, sizing, cảnh báo, chính sách lifecycle và chi phí theo thực tế.

### Một mẫu kiểm soát có thể review

~~~yaml
# Ví dụ đặc tả nội bộ, không phải manifest áp dụng trực tiếp qua Google Cloud API.
environment: development
project_id: store-dev
owner: development-team
monthly_cost_plan:
  currency: USD
  amount: 300
alerts_only_budget:
  actual_threshold_percentages: [50, 80, 100]
  forecast_threshold_percentage: 100
  response_owner: development-team
technical_controls:
  cloud_run_max_instances: "Xac dinh bang thu nghiem tai"
  compute_engine_quota: "Kiem tra va dieu chinh theo khu vuc"
  storage_lifecycle: "Xoa du lieu thu nghiem duoc phep sau N ngay"
spend_cap_budget:
  enabled: false
  decision: "Chi xem xet neu service va billing account du dieu kien"
review:
  cadence: weekly
  check_cost_and_reliability_together: true
~~~

Mẫu trên buộc người duyệt phân biệt **tiền dự toán**, **tín hiệu cảnh báo**, **rào chắn tiêu thụ** và **rủi ro chất lượng dịch vụ**. Các chuỗi mô tả trong mẫu cần được thay bằng thông số đã kiểm chứng nếu triển khai thực tế.

## 11. Sai lầm thường gặp

**“Budget đặt 100 USD thì Google Cloud sẽ không thu thêm.”** Sai đối với **alerts-only budget**. Một số **spend cap budgets** có khả năng tạm dừng sử dụng mới cho dịch vụ đủ điều kiện, nhưng vẫn có độ trễ và phạm vi hẹp.

**“Tăng quota sẽ miễn phí vì quota chỉ là con số.”** Bản thân thay đổi quota không đồng nghĩa đã phát sinh chi phí, nhưng nó **cho phép tăng tiêu thụ** nếu người dùng hay autoscaler sử dụng thêm tài nguyên.

**“Chạm CPU quota thì hóa đơn VM dừng.”** Các VM hiện có có thể vẫn chạy và tính phí; quota thường ngăn **cấp phát mới**, không phải lệnh tắt tài nguyên cũ.

**“Giới hạn Cloud Run max instances = 3 nghĩa là chi phí Cloud Run không vượt giá của đúng ba instance.”** Số instance không quy đổi trực tiếp ra tiền; số request, thời gian xử lý, cấu hình tài nguyên, các bản revision, egress và tài nguyên liên quan đều ảnh hưởng. Max instances có thể tạm vượt trong một số tình huống.

**“Nếu có thông báo Pub/Sub, hệ thống đã tự động khóa billing.”** Pub/Sub cung cấp sự kiện. Muốn thực thi hành động cần xây dựng workflow riêng, đủ quyền và có xử lý lỗi. Tự ngắt billing có rủi ro nghiêm trọng đối với dữ liệu và tính sẵn sàng.

**“Bảo vệ ngân sách đồng nghĩa nên giảm mọi quota xuống thấp nhất.”** Giới hạn thấp có thể khiến workload không phục vụ được traffic hợp lệ, gây lỗi và vi phạm SLO. Kiểm soát chi phí phải được cân bằng với mục tiêu sản phẩm.

## 12. Bài tập thực hành và câu hỏi kiểm tra

### Bài tập A: chọn cơ chế đúng

Với từng yêu cầu, hãy xác định dùng **budget alert**, **quota/system limit**, **giới hạn cấu hình dịch vụ**, **spend cap budget nếu đủ điều kiện**, hoặc **kết hợp**:

1. CFO muốn được báo khi tổng chi phí production dự kiến vượt 20.000 USD/tháng.
2. Nhóm dev muốn VM lab không thể tăng số lượng vô hạn.
3. API Cloud Run ở môi trường thử nghiệm cần giảm khả năng tăng instance bất thường.
4. Người quản lý muốn yêu cầu mới của dịch vụ Cloud Run đủ điều kiện bị tạm dừng khi chi phí gộp ước tính của dịch vụ đó đạt ngưỡng tháng, chấp nhận có thể bị gián đoạn.
5. Hệ thống BigQuery cần ngăn từng truy vấn on-demand xử lý quá nhiều dữ liệu.
6. Nhóm vận hành muốn giảm khả năng thiếu quota khi production tăng tải cao điểm.

### Đáp án gợi ý

| Bài | Cơ chế nên xem xét | Lý do |
|---|---|---|
| 1 | **Alerts-only budget forecast + người nhận** | Theo dõi xu hướng tiền; không tự dừng tài nguyên |
| 2 | **Allocation quota và IAM** | Giới hạn khả năng cấp VM mới và quyền tạo |
| 3 | **Cloud Run max instances + giám sát** | Giới hạn tốc độ tăng instance, phải kiểm thử lỗi khi thiếu năng lực |
| 4 | **Spend cap budget** cho dịch vụ/project đủ điều kiện | Có thể tạm dừng sử dụng mới; kiểm tra kỹ phạm vi và overage |
| 5 | **Maximum bytes billed** và quota/job control nếu thích hợp | Hạn chế truy vấn cụ thể; không thay thế budget |
| 6 | **Theo dõi quota, dự báo tải, yêu cầu điều chỉnh sớm** | Hạn chế chặn autoscaling vì thiếu quota |

### Bài tập B: phân tích tuyên bố

Giả sử project có:

- Alerts-only budget **600 USD/tháng**, actual alert 100%.
- Quota Compute Engine **16 vCPU** trong region A.
- Đang chạy 4 VM, mỗi VM 4 vCPU; ngoài ra có 100 GiB dữ liệu lưu trữ và một Cloud SQL instance.

**Câu hỏi:** Nếu dự báo hóa đơn tháng là **900 USD** và không thể tạo thêm VM ở region A vì hết quota, hãy đánh giá ba câu sau:

1. “Quota CPU đã chạm trần, tổng hóa đơn sẽ dừng ở 600 USD.”
2. “Alerts-only budget chạm 100% sẽ xóa một VM.”
3. “Muốn giảm hóa đơn phải điều tra nguồn chi phí cụ thể, không thể chỉ nhìn quota.”

**Hướng giải:** (1) sai vì quota không khóa chi phí đang phát sinh; (2) sai vì alerts-only budget thông báo chứ không tự xóa VM; (3) đúng. Cần kiểm tra VM, Cloud SQL, dung lượng, network, log, nhu cầu vận hành và phương án giảm có ảnh hưởng dịch vụ hay không.

## 13. Tổng kết và tài liệu tham khảo

**Nguyên tắc cốt lõi:** *Budget alerts cho biết khi nào cần chú ý; quota và giới hạn dịch vụ kiểm soát một phần lượng sử dụng; spend cap budget chỉ tạm dừng sử dụng mới trong phạm vi dịch vụ đủ điều kiện.* Muốn kiểm soát chi phí đáng tin cậy, cần phối hợp chính sách, quyền, giám sát, ước tính và hành động đã kiểm thử.

Tài liệu chính thức nên đọc tiếp:

1. [Create, edit, or delete budgets and budget alerts — Google Cloud Billing](https://docs.cloud.google.com/billing/docs/how-to/budgets) — alerts-only budgets, ngưỡng, phạm vi, email và Pub/Sub.
2. [Manage spend cap budgets — Google Cloud Billing](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps) — dịch vụ đủ điều kiện, cơ chế và giới hạn spend caps.
3. [Cloud Quotas overview](https://docs.cloud.google.com/docs/quotas/overview) — allocation/rate/concurrent quotas và system limits.
4. [View and manage quotas](https://docs.cloud.google.com/docs/quotas/view-manage) — xem mức dùng, điều chỉnh hạn ngạch theo project và service.
5. [Set maximum instances for services — Cloud Run](https://docs.cloud.google.com/run/docs/configuring/max-instances) — max instances cấp dịch vụ và phiên bản.
6. [About maximum instances — Cloud Run](https://docs.cloud.google.com/run/docs/configuring/max-instances-limits) — các ngoại lệ và đánh đổi chi phí/độ tin cậy.
7. [Disable billing usage with notifications — Cloud Billing](https://docs.cloud.google.com/billing/docs/how-to/disable-billing-with-notifications) — cảnh báo về độ trễ và rủi ro khi tự động ngắt billing.
