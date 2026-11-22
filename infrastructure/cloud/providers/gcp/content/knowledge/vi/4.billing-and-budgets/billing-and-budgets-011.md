# Quản lý credits, tài nguyên thử nghiệm và chi phí phát sinh trên Google Cloud

Trong quá trình học Google Cloud, bạn có thể tạo VM Compute Engine để thử SSH, triển khai ứng dụng trên Cloud Run, dựng GKE cluster, tạo Cloud SQL database hoặc lưu dữ liệu trên Cloud Storage. Mỗi thao tác giúp thực hành nhưng cũng có khả năng tạo **chi phí sử dụng**. Một khoản tín dụng khuyến mại (credit) hay hạn mức sử dụng miễn phí có thể làm giảm số tiền phải trả, nhưng không có nghĩa mọi tài nguyên đều miễn phí hoặc thử nghiệm luôn an toàn về chi phí.

Bài học thuộc chương **Thanh toán và ngân sách** trong mô-đun `CLOUD_PROVIDERS_GCP`. Khi học về tổ chức project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu và tự động hóa phát hành, bạn cần đồng thời biết chọn phạm vi thử nghiệm, theo dõi độ tin cậy và hiểu những khoản chi phí đi kèm. Mục tiêu thực tế của bài là giúp người học **kiểm soát tín dụng, nhận diện tài nguyên còn tính phí và kết thúc lab có kiểm chứng**.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **credits**, **Free Tier**, **ngân sách (budget)**, **quota** và **chi phí thực tế**.
2. Xác định mối quan hệ giữa project, Cloud Billing account và credits đủ điều kiện áp dụng.
3. Đọc Cloud Billing Reports để phân tích chi phí trước/sau credits, theo project, dịch vụ và SKU.
4. Cấu hình ngân sách, ngưỡng cảnh báo và quy trình ứng phó khi chi phí vượt dự kiến.
5. Nhận diện chi phí tiếp diễn từ VM, disk, IP, GKE, Cloud SQL, lưu trữ, log và truyền dữ liệu.
6. Lập kế hoạch lab, dọn tài nguyên đúng thứ tự và kiểm tra chi phí sau khi dọn.
7. Áp dụng kỷ luật quản lý chi phí vào môi trường phát triển, CI/CD và production.

## 1. Bốn khái niệm thường bị nhầm

| Khái niệm | Ý nghĩa | Điều không nên suy ra |
| --- | --- | --- |
| **Credits** | Khoản tín dụng được Google Cloud hoặc đối tác cấp theo điều kiện cụ thể, có thể bù trừ chi phí đủ điều kiện. | Không phải tiền mặt; không tự động áp dụng cho mọi dịch vụ hoặc mọi billing account. |
| **Free Tier** | Mức sử dụng miễn phí của một số sản phẩm theo điều kiện và giới hạn được công bố. | Không đồng nghĩa mọi lần sử dụng dịch vụ đều miễn phí; vượt giới hạn có thể phát sinh phí. |
| **Budget** | Công cụ theo dõi mức chi phí và gửi thông báo khi đạt các ngưỡng hoặc dự báo chi phí. | **Không phải trần chi phí cứng** và mặc định không dừng tài nguyên. |
| **Quota/limit** | Giới hạn tài nguyên hoặc mức sử dụng API/dịch vụ, thường để bảo vệ năng lực hệ thống và vận hành. | Không bảo đảm tổng chi phí nằm trong ngân sách; vẫn có tài nguyên khác tiếp tục tính phí. |

Một project có thể vừa nhận ưu đãi Free Tier, vừa được khấu trừ credits, đồng thời vượt ngân sách đã đặt. Do đó, khi thấy **số tiền phải trả hiện tại bằng 0**, không nên kết luận **không có mức sử dụng tính phí**.

### 1.1. Chi phí sử dụng và số tiền phải trả là hai góc nhìn

Ví dụ minh họa, tất cả số tiền dưới đây là **giả định**, không phải báo giá Google Cloud:

| Khoản mục trong kỳ | Giá trị giả định |
| --- | ---: |
| Chi phí sử dụng đủ điều kiện được tính trước credit | 32 USD |
| Promotional credits áp dụng cho phần đủ điều kiện | -25 USD |
| Chi phí sử dụng không thuộc phạm vi credit | 4 USD |
| **Số tiền còn lại trước thuế/điều chỉnh khác** | **11 USD** |

Trong ví dụ này, credits không biến mức tiêu thụ thành miễn phí: tổng chi phí sử dụng là 36 USD, credit bù trừ 25 USD và phần còn lại là 11 USD. Hóa đơn thực tế có thể gồm thuế, điều chỉnh, ưu đãi, chênh lệch thời điểm ghi nhận và quy tắc áp dụng credit riêng.

**Cách ghi nhận hiệu quả:** theo dõi đồng thời **gross usage cost** (chi phí sử dụng trước credit) và **net cost** (chi phí sau các khoản bù trừ được áp dụng). Net cost thấp tạm thời có thể che giấu một workload đang tiêu tốn nhiều tài nguyên.

## 2. Credits trên Google Cloud: phân loại, phạm vi và vòng đời

Credits có thể xuất hiện trong những chương trình như dùng thử, chương trình học tập, sự kiện, khuyến mại hoặc ưu đãi của đối tác. Điều kiện từng chương trình có thể khác nhau, vì vậy **không nên cố định số tiền credit, số ngày hiệu lực hoặc danh sách dịch vụ đủ điều kiện** vào quy trình vận hành.

Khi nhận credit, cần đọc và lưu lại các thông tin sau:

| Thông tin phải xác minh | Vì sao quan trọng |
| --- | --- |
| **Chương trình phát hành** | Quyết định điều kiện, giới hạn sử dụng và hỗ trợ liên quan. |
| **Billing account liên quan** | Credit có thể gắn với tài khoản thanh toán hoặc phạm vi được quy định trong chương trình. |
| **Dịch vụ và SKU đủ điều kiện** | Một khoản sử dụng có thể không được bù trừ dù project đang có credit. |
| **Ngày hết hạn** | Credit còn dư có thể hết hiệu lực nếu quá thời hạn chương trình. |
| **Giới hạn/điều kiện sử dụng** | Các loại credit có thể có hạn chế về mục đích, dịch vụ, chuyển đổi hoặc phạm vi địa lý. |
| **Cơ chế khi hết credit** | Ứng dụng có thể tiếp tục tính phí trong tài khoản trả phí; một số chương trình dùng thử có chính sách riêng. |
| **Cách credit xuất hiện trong báo cáo/hóa đơn** | Giúp đối chiếu chi phí gốc, khoản khấu trừ và số phải trả. |

### 2.1. Free Trial, promotional credits và Free Tier

Ba cụm từ thường gặp:

- **Free Trial** là chương trình dùng thử có thời hạn và điều kiện riêng; có thể kèm credit dùng thử. Giới hạn và hành vi sau thời hạn phụ thuộc chương trình/tình trạng chuyển sang tài khoản trả phí.
- **Promotional credits** là khoản tín dụng theo một ưu đãi cụ thể. Có thể chỉ bù trừ một phần dịch vụ hoặc SKU.
- **Free Tier** là mức sử dụng miễn phí có điều kiện của từng sản phẩm. Đây là cơ chế ưu đãi theo mức sử dụng, **không phải một ví tiền credit**.

Với mọi chương trình, hãy kiểm tra trang **Cloud Billing → Credits**, điều khoản áp dụng và tài liệu chính thức trước khi lập ngân sách. Không coi ví dụ hay mức credit từ tài khoản khác là mức áp dụng cho tài khoản của mình.

### 2.2. Credits được quản lý trong phạm vi nào?

Cấu trúc quản trị liên quan:

~~~mermaid
flowchart TD
    O["Organization"]
    F["Folder: Nonproduction"]
    P1["Project: learning-gcp-dev"]
    P2["Project: learning-gcp-lab"]
    B["Cloud Billing account"]
    C["Credits đủ điều kiện theo chương trình"]
    O --> F
    F --> P1
    F --> P2
    P1 -. "Liên kết thanh toán" .-> B
    P2 -. "Liên kết thanh toán" .-> B
    C -->|"Áp dụng theo điều kiện"| B
~~~

Organization và folder giúp quản trị quyền/chính sách; billing account đảm nhiệm phần thanh toán. **Project không phải ví tiền credit độc lập.** Project được liên kết với billing account để ghi nhận chi phí, trong khi việc credit có được trừ hay không phụ thuộc quy tắc ưu đãi và tài khoản thanh toán liên quan.

Một project thường liên kết với **một billing account đang hoạt động tại một thời điểm**. Nhiều project có thể chia sẻ một billing account. Khi đổi liên kết billing, cần đánh giá tác động đến quản trị chi phí, credits, quyền và vận hành; không nên chuyển qua lại chỉ để thử bù trừ ưu đãi.

## 3. Credit không phải bảo đảm không phát sinh phí

Hãy xét ba trạng thái:

1. **Còn credit và mức sử dụng đủ điều kiện:** một phần hoặc toàn bộ chi phí hợp lệ có thể được bù trừ.
2. **Còn credit nhưng có khoản không đủ điều kiện:** vẫn có thể xuất hiện số tiền phải trả ngay.
3. **Hết hạn, hết số dư hoặc chương trình kết thúc:** khoản sử dụng mới có thể trở thành chi phí phải trả theo trạng thái billing account và điều kiện chương trình.

Các trạng thái trên phải được xác minh qua thông tin credit và báo cáo billing thực tế. Không giả định rằng khi credit cạn, Google Cloud **chắc chắn sẽ tự dừng** tất cả máy ảo, database hoặc dịch vụ đang chạy.

### 3.1. Ví dụ dự báo mức tiêu credit

Giả sử nhóm có 60 USD credits đủ điều kiện, sau 6 ngày đã dùng 18 USD chi phí thuộc diện được bù trừ và vẫn còn 24 ngày lab.

Nếu mỗi ngày tiếp tục tiêu thụ 3 USD phần đủ điều kiện:

- Credit còn lại theo mô hình: `60 - 18 = 42 USD`.
- Chi phí đủ điều kiện dự kiến trong 24 ngày: `24 × 3 = 72 USD`.
- Phần chi phí có thể vượt credit theo mô hình: `72 - 42 = 30 USD`.

Ngoài ra, nếu có 5 USD chi phí không đủ điều kiện, tổng khoản phải trả **theo giả định** có thể là 35 USD, chưa tính thuế hoặc điều chỉnh khác. Đây là **bài toán minh họa**, không phải cách Google Cloud cam kết khấu trừ từng khoản. Chi phí và thời điểm áp dụng credits thực tế có thể thay đổi.

Bài học: chỉ nhìn số dư credit hôm nay mà không xem **tốc độ tiêu thụ** và **ngày hết hạn** có thể dẫn đến dự báo sai.

## 4. Xem chi phí và credits trong Cloud Billing

Trong Google Cloud Console, mở khu vực **Billing** và chọn đúng billing account. Người dùng cần quyền xem dữ liệu thanh toán phù hợp; quyền chỉnh sửa tài nguyên của project không tự động cho phép xem mọi thông tin billing account.

### 4.1. Các màn hình hữu ích

| Khu vực | Dùng để làm gì? |
| --- | --- |
| **Billing overview** | Xem thông tin tổng quan của tài khoản thanh toán. |
| **Credits** | Kiểm tra credits hiện có, thời hạn hoặc các thông tin ưu đãi mà giao diện cung cấp. |
| **Reports** | Phân tích chi phí theo thời gian, project, service, SKU và các bộ lọc. |
| **Cost table / Cost breakdown** | Đối chiếu chi tiết mức sử dụng, credits, điều chỉnh theo khả năng hỗ trợ và kỳ dữ liệu. |
| **Budgets & alerts** | Tạo ngân sách, các ngưỡng cảnh báo và thiết lập người nhận/thông báo. |
| **Billing export** | Xuất dữ liệu billing sang BigQuery để phân tích chi tiết, nếu được cấu hình. |

Tên menu hoặc khả năng hiển thị có thể thay đổi theo giao diện, quyền tài khoản và chế độ billing.

### 4.2. Cách đọc một báo cáo chi phí

Thực hiện theo trình tự:

1. Chọn **billing account** và **khoảng thời gian** đang cần phân tích.
2. Lọc theo **project thử nghiệm**, tránh cộng nhầm các project production.
3. Nhóm theo **service** để tìm nhóm tiêu tiền lớn: Compute Engine, GKE, Cloud SQL, Cloud Run, Cloud Storage...
4. Đi sâu đến **SKU** để hiểu loại sử dụng cụ thể: CPU, RAM, disk, storage, network egress, requests hoặc dịch vụ liên quan.
5. Xem cách biểu diễn **credits/discounts** và so sánh chi phí trước và sau áp dụng. Không tự cộng trừ một khoản hai lần.
6. Kiểm tra mốc thời gian, độ trễ cập nhật, loại dữ liệu và các điều chỉnh trước khi kết luận.

Ví dụ: báo cáo cho project lab hiển thị Compute Engine 8 USD, Cloud SQL 12 USD, Cloud Storage 2 USD và network 3 USD. **Tổng chi phí sử dụng 25 USD**. Nếu báo cáo thể hiện 15 USD credits đủ điều kiện đã áp dụng, phần còn lại trong ví dụ là 10 USD trước các yếu tố hóa đơn khác.

### 4.3. Vì sao chi phí có thể xuất hiện muộn?

Dữ liệu billing có thể **không cập nhật theo thời gian thực**. Có độ trễ giữa thời điểm sử dụng tài nguyên, số liệu được đưa lên Reports/Export và khi khoản tiền được tổng hợp vào hóa đơn.

Vì vậy:

- Không coi dashboard vừa hiển thị `0 USD` là bằng chứng vừa tạo VM sẽ không tính phí.
- Không coi việc xóa hết tài nguyên vào lúc 17:00 đồng nghĩa báo cáo tại 17:01 phải dừng thay đổi.
- Kiểm tra lại sau một khoảng thời gian đủ để dữ liệu ghi nhận cập nhật; đối chiếu kỳ billing và thông tin hóa đơn theo chính sách tổ chức.

Nếu cần giám sát gần thời gian thực, phối hợp dữ liệu metric về mức sử dụng tài nguyên với chi phí đã báo cáo, nhưng không tự giả định metrics tương đương số tiền hóa đơn.

## 5. Tạo budget và alerts để giới hạn rủi ro

**Cloud Billing Budgets** giúp theo dõi mức chi phí và gửi thông báo. Budget có thể được đặt cho phạm vi phù hợp với billing account, project, service hoặc các bộ lọc được hỗ trợ trong giao diện. Có thể sử dụng ngưỡng theo chi phí thực tế (actual) và trong một số cấu hình theo dự báo (forecasted).

### 5.1. Tạo ngân sách cho lab

Giả sử một nhóm có kế hoạch thử Cloud Run và Cloud Storage trong 2 tuần, với mức theo dõi mục tiêu **20 USD**. Đây là con số minh họa.

1. Vào **Billing → Budgets & alerts**.
2. Chọn **Create budget**, nhập tên như `lab-commerce-nov`.
3. Chọn billing account và **lọc đúng project lab**; thêm bộ lọc dịch vụ nếu cần.
4. Chọn khoảng thời gian hoặc chu kỳ ngân sách tương ứng với bài lab.
5. Đặt ngân sách mục tiêu `20 USD`.
6. Đặt các ngưỡng ví dụ: **25%, 50%, 80%, 100%** của budget.
7. Cấu hình email hoặc kênh thông báo được tổ chức hỗ trợ, phân công người chịu trách nhiệm phản hồi.
8. Lưu, kiểm tra lại bộ lọc và xác nhận cơ chế nhận cảnh báo.

| Ngưỡng của budget 20 USD | Mức tiền tương ứng | Hành động đề xuất |
| --- | ---: | --- |
| 25% | 5 USD | Kiểm tra dịch vụ đang chạy và đối chiếu kế hoạch lab. |
| 50% | 10 USD | Rà soát VM/SQL/GKE và các tài nguyên lưu trữ còn tồn tại. |
| 80% | 16 USD | Ngừng tạo thêm tài nguyên mới; quyết định nên tiếp tục hay dọn lab. |
| 100% | 20 USD | Kích hoạt quy trình xử lý vượt ngân sách, xem chủ sở hữu và phê duyệt. |

**Lưu ý quan trọng:** 100% budget **không phải công tắc chặn chi tiêu**. Chi phí có thể tiếp tục tăng trước, trong hoặc sau khi cảnh báo gửi tới người nhận. Cảnh báo có thể dựa trên dữ liệu được cập nhật trễ.

### 5.2. Có thể dùng Pub/Sub và tự động hóa không?

Cloud Billing có thể cung cấp thông báo budget qua **Pub/Sub**, tùy cấu hình. Một hệ thống tự động có thể tiêu thụ thông báo rồi gửi cảnh báo tới nhóm hoặc kích hoạt workflow.

~~~mermaid
flowchart LR
    A["Dịch vụ sử dụng tài nguyên"] --> B["Cloud Billing ghi nhận chi phí"]
    B --> C["Budget đánh giá ngưỡng"]
    C --> D["Email / kênh thông báo"]
    C --> E["Pub/Sub (khi cấu hình)"]
    E --> F["Workflow kiểm tra và phê duyệt"]
    F --> G["Điều chỉnh hoặc dọn tài nguyên có kiểm soát"]
~~~

Không nên xây workflow tự động **xóa project, database hoặc tắt billing** ngay khi chạm ngưỡng nếu chưa phân loại môi trường, chủ sở hữu và mức độ quan trọng. Thao tác đó có thể gây gián đoạn hoặc mất dữ liệu. Với lab không dùng dữ liệu thật, có thể thiết kế quy trình tắt tài nguyên có kiểm soát, nhưng phải thử nghiệm và định nghĩa rõ điều kiện.

### 5.3. Khi nào quota giúp kiểm soát chi phí?

Quota tài nguyên có thể giúp ngăn việc tạo quá nhiều VM, số CPU hoặc mức gọi API nhất định. Nhưng một VM được phép chạy suốt nhiều ngày vẫn có thể tiêu tiền, dù không vượt quota. Vì vậy quota là **một lớp bảo vệ bổ sung**, không thay thế budget, giám sát sử dụng và chính sách dọn dẹp.

## 6. Những tài nguyên thử nghiệm thường tiếp tục tính phí

Sai lầm phổ biến là chỉ quan tâm tài nguyên “đang chạy trên màn hình”. Nhiều thành phần có vòng đời và cơ chế tính phí riêng.

| Tài nguyên/dịch vụ | Khi nào cần chú ý? | Hành động kiểm tra trước khi kết thúc lab |
| --- | --- | --- |
| **Compute Engine VM** | CPU/RAM khi VM chạy; một số thành phần liên quan có thể tính phí khi VM dừng. | Kiểm tra trạng thái VM và tài nguyên gắn kèm. |
| **Persistent Disk / Hyperdisk** | Dung lượng được cấp phát có thể tiếp tục tính phí khi VM dừng hoặc bị xóa nhưng disk còn lại. | Liệt kê boot/data disks, xác nhận disk có còn cần giữ. |
| **Snapshots / images** | Bản sao lưu và image được lưu riêng có thể còn tính phí. | Tìm snapshots và images phát sinh từ bài lab. |
| **Địa chỉ IP ngoài / forwarding rules / load balancers** | Phí IP và hạ tầng mạng có thể phát sinh tùy loại và trạng thái. | Kiểm tra reserved addresses, forwarding rules, load balancer. |
| **Cloud NAT / networking** | Có thể có phí theo xử lý lưu lượng, tài nguyên mạng và truyền dữ liệu. | Xem cấu hình NAT, transfer và egress. |
| **GKE** | Cluster, node pool, VM node, disk và networking có các khoản chi phí liên quan. | Kiểm tra cluster, node pool, PV/PVC và disk sau khi xóa workload. |
| **Cloud Run** | Chi phí tùy request, CPU/RAM cấp phát, cấu hình instance tối thiểu, kết nối và dịch vụ phụ trợ. | Kiểm tra service/job, min instances, revision, networking. |
| **Cloud SQL** | Instance, lưu trữ, backup, HA và networking có thể phát sinh phí. | Kiểm tra instance, backups, read replicas, dung lượng. |
| **Cloud Storage** | Dữ liệu object, request, truy xuất và egress tùy storage class/điều kiện. | Kiểm tra bucket, object, phiên bản object, lifecycle và replication. |
| **Artifact Registry** | Image/artifact được lưu sau các lần build/deploy. | Kiểm tra repository và artifact còn cần dùng. |
| **Cloud Logging / Monitoring** | Một số loại ingestion, retention hoặc tính năng có thể phát sinh phí. | Xem sink, bucket lưu log, metric và retention tùy dịch vụ. |

**Stop không đồng nghĩa Delete; Delete không đồng nghĩa hết toàn bộ chi phí.** Ví dụ: dừng một VM có thể giảm phần CPU, nhưng persistent disk, snapshot hoặc IP vẫn được giữ. Xóa một GKE workload có thể không xóa cluster hay node pool. Xóa Cloud Run service không tự xóa mọi image, log hoặc dịch vụ phụ trợ.

### 6.1. Chi phí vô hình khi học mạng VPC

Bản thân việc khai báo một VPC network không có cùng cơ chế tính phí như VM, nhưng **networking không tự động miễn phí**. Network egress, load balancer, NAT, địa chỉ IP ngoài và một số kết nối có thể tạo chi phí. Hãy kiểm tra cả traffic giữa region/zone và việc kéo dữ liệu từ Cloud Storage hoặc database khi tính tổng chi phí lab.

### 6.2. Lập checklist trước khi thử GKE hoặc Cloud SQL

Hai nhóm dịch vụ này thường phức tạp hơn một ứng dụng stateless:

- **GKE:** kiểm tra loại cluster, node pool, VM node, persistent volume, disk, load balancer và các dịch vụ liên quan.
- **Cloud SQL:** kiểm tra instance, storage, backup, HA, read replica và loại cấu hình kết nối.
- Nếu mục tiêu chỉ học cách gọi API hoặc thao tác đơn giản, cân nhắc môi trường giả lập, ví dụ mẫu, sandbox đã được tổ chức duyệt hoặc một dịch vụ nhỏ có chi phí ước lượng thấp hơn.

## 7. Thiết kế lab có kiểm soát: từ trước khi tạo đến khi kết thúc

Ví dụ: nhóm Commerce cần thử một API Java trên Cloud Run, tải ảnh vào Cloud Storage và có thể thử Cloud SQL trong một buổi học. Nhóm chọn một project riêng tên `atlas-commerce-lab` (tên chỉ minh họa), owner rõ ràng và dự kiến kết thúc lab trong ngày.

### 7.1. Trước khi chạy

Chuẩn bị thông tin:

| Mục | Ví dụ |
| --- | --- |
| Chủ sở hữu | Nhóm Commerce, người trực tiếp theo dõi billing |
| Project | `atlas-commerce-lab` |
| Môi trường | `lab`; tách khỏi project production |
| Thời điểm bắt đầu/kết thúc | 09:00–17:00 ngày lab |
| Mức chi phí dự tính | Ví dụ 10 USD, tính theo công cụ ước tính hiện hành |
| Ngân sách cảnh báo | Ví dụ 10 USD với ngưỡng 50%, 80%, 100% |
| Dịch vụ được phép thử | Cloud Run, Cloud Storage; Cloud SQL chỉ khi đã duyệt |
| Nhãn/metadata quản lý | `environment=lab`, `team=commerce`, `owner=...` khi dịch vụ hỗ trợ |
| Phương án dọn dẹp | Chủ sở hữu tài nguyên kiểm tra và dọn theo checklist |

Không sao chép khóa bí mật hoặc dữ liệu khách hàng thật vào project lab. Dùng dữ liệu giả và IAM vừa đủ. Xác nhận project liên kết billing account phù hợp, credit khả dụng nếu dự định dùng credit, và các giới hạn chương trình.

### 7.2. Khi lab đang chạy

Theo dõi hai nhóm tín hiệu:

- **Dịch vụ sử dụng:** số VM, node, instance, bytes storage, request, network egress.
- **Billing:** chi phí theo project/dịch vụ, credits đã áp dụng, budget actual/forecasted và các cảnh báo nhận được.

Một chiến lược đơn giản:

~~~mermaid
flowchart TD
    A["Bắt đầu lab"] --> B["Xác minh credit, billing, budget và owner"]
    B --> C["Tạo tài nguyên có nhãn/quy ước tên"]
    C --> D["Theo dõi mức sử dụng và cảnh báo"]
    D --> E{"Lab xong hoặc đạt ngưỡng xử lý?"}
    E -->|Chưa| D
    E -->|Rồi| F["Kiểm kê tài nguyên và dữ liệu cần giữ"]
    F --> G["Dọn tài nguyên được phép xóa"]
    G --> H["Kiểm tra tài nguyên còn tồn tại"]
    H --> I["Theo dõi báo cáo billing cập nhật và đóng lab"]
~~~

### 7.3. Sau khi lab hoàn tất

Lập biên bản ngắn: project ID, dịch vụ đã tạo, tài nguyên đã dọn, tài nguyên giữ lại cùng lý do, thời điểm kết thúc, chi phí ước tính và lịch kiểm tra báo cáo. Người phụ trách cần biết tài nguyên nào còn tiếp tục phát sinh phí.

Đối với lab có dữ liệu cần giữ, quyết định lưu hay xóa phải được đưa ra trước khi dọn. **Không xóa dữ liệu thật chỉ vì ngân sách đang vượt ngưỡng.**

## 8. Kiểm kê tài nguyên bằng Google Cloud CLI

Các lệnh dưới đây **chỉ đọc**, giúp rà soát tài nguyên. Chạy khi đã đăng nhập Google Cloud CLI và có quyền phù hợp. Thay `PROJECT_ID` bằng project thực tế.

~~~bash
# Xác minh project đang thao tác
gcloud config get-value project

# Kiểm tra thông tin liên kết thanh toán của project
gcloud billing projects describe PROJECT_ID

# Compute Engine instances, disks và IP addresses
gcloud compute instances list --project=PROJECT_ID
gcloud compute disks list --project=PROJECT_ID
gcloud compute addresses list --project=PROJECT_ID

# GKE clusters và Cloud SQL instances
gcloud container clusters list --project=PROJECT_ID
gcloud sql instances list --project=PROJECT_ID

# Cloud Run services và Cloud Storage buckets
gcloud run services list --project=PROJECT_ID
gcloud storage buckets list --project=PROJECT_ID
~~~

Một số lệnh có thể yêu cầu bật API, quyền xem tài nguyên hoặc thêm thông tin location tùy cấu hình. Nếu CLI không hiển thị một tài nguyên do thiếu quyền, **không thể kết luận tài nguyên không tồn tại**.

Các lệnh trên **không bao quát mọi loại tài nguyên tính phí**. Cần kiểm tra thêm snapshots, images, load balancer, Cloud NAT, Artifact Registry, logs, database backups và các tài nguyên của dịch vụ đã thử nghiệm. Với tổ chức lớn, Cloud Asset Inventory và công cụ kiểm kê được quản trị viên cho phép có thể giúp mở rộng phạm vi kiểm tra.

### 8.1. Checklist khi dọn project lab

- [ ] Kiểm tra project ID và người sở hữu; xác minh không phải project production.
- [ ] Ghi nhận tài nguyên/dữ liệu cần bảo lưu và phụ thuộc giữa các dịch vụ.
- [ ] Ngừng luồng tạo mới tài nguyên: CI/CD pipeline, scheduler, automation hoặc job.
- [ ] Dọn workload không còn dùng (VM, Cloud Run, GKE, Cloud SQL...) theo quy trình đã duyệt.
- [ ] Kiểm tra disk, snapshot, reserved IP, load balancer, NAT, bucket, artifact và backup còn sót.
- [ ] Xem lại dịch vụ nào còn tính phí dù không có workload hoạt động.
- [ ] Liệt kê lại tài nguyên bằng CLI/Console sau khi dọn.
- [ ] Kiểm tra Cloud Billing Reports sau khi dữ liệu cập nhật để phát hiện phát sinh còn lại.
- [ ] Ghi rõ người chịu trách nhiệm nếu phải giữ một tài nguyên.

Nếu lab chỉ tồn tại phục vụ một khóa học và có thể xóa toàn bộ project, hãy cân nhắc quy trình **đóng project** theo quyền và chính sách tổ chức. Tuy nhiên, việc đóng/xóa project ảnh hưởng mạnh đến dữ liệu và các dịch vụ; cần xác minh kỹ project đích, phụ thuộc, khả năng phục hồi và thời gian lưu trữ trước khi thực hiện. Thao tác đóng project cũng không bảo đảm mọi khoản phí đã phát sinh lập tức biến mất khỏi báo cáo.

## 9. Tự động hóa phát hành và rủi ro chi phí

Trong mô-đun Google Cloud, bạn sẽ học cách triển khai ứng dụng qua CI/CD. Automation giúp phát hành nhanh nhưng cũng có thể vô tình **tạo tài nguyên lặp lại**.

Những tình huống nên phòng tránh:

1. Pipeline tạo VM hoặc database mỗi lần chạy nhưng không dọn sau khi test.
2. Mỗi pull request dựng một môi trường riêng, nhưng không dọn khi PR đóng.
3. Container image được build liên tục và tồn tại trong Artifact Registry.
4. Cloud Run service có min instances cao hoặc job chạy theo lịch quá dày.
5. GKE cluster test còn node pool sau khi test hoàn thành.
6. Snapshot/backup giữ vô hạn do thiếu lifecycle policy.
7. Log quá chi tiết, lưu trữ dài hạn hoặc chuyển dữ liệu giữa các vùng ngoài dự kiến.

### 9.1. Kiểm soát ở ba lớp

| Lớp kiểm soát | Ví dụ | Mục đích |
| --- | --- | --- |
| **Phòng ngừa** | Project lab riêng, IAM tối thiểu, quota, giới hạn môi trường CI/CD, approval trước khi tạo tài nguyên đắt tiền | Giảm khả năng tạo chi phí ngoài ý muốn |
| **Phát hiện** | Billing Reports, budgets, actual/forecast alerts, metric sử dụng, kiểm kê tài nguyên | Phát hiện sớm việc vượt kế hoạch |
| **Khắc phục** | Tạm dừng pipeline, giảm quy mô, dọn tài nguyên hết hạn, kiểm tra dữ liệu tồn dư | Dừng nguyên nhân làm tăng chi phí |

Với môi trường production, quyết định tối ưu chi phí phải cân bằng **độ tin cậy, hiệu năng, tính sẵn sàng và nghĩa vụ lưu giữ dữ liệu**. Giảm instance hay xóa backup thiếu kiểm soát có thể gây hại nhiều hơn khoản tiết kiệm.

## 10. Chọn cách theo dõi: Reports, Budget hay BigQuery export?

Ba công cụ phục vụ các nhu cầu khác nhau:

| Nhu cầu | Công cụ phù hợp |
| --- | --- |
| Hôm qua project lab tiêu tiền vào dịch vụ nào? | **Cloud Billing Reports** với nhóm theo project/service/SKU |
| Cần nhận cảnh báo khi chi phí tháng này vượt dự kiến | **Budgets & alerts** |
| Muốn phân tích nhiều project, gắn dữ liệu cost center hoặc làm báo cáo định kỳ | **Cloud Billing export to BigQuery** |
| Muốn dự báo trước khi bật GKE/SQL hoặc chọn kích thước VM | **Google Cloud Pricing Calculator** và tài liệu giá hiện hành |
| Muốn biết tài nguyên nào vẫn tồn tại sau lab | **Console/CLI**, Cloud Asset Inventory tùy quyền |

### 10.1. Billing export sang BigQuery

Nếu nhóm có nhu cầu phân tích sâu, có thể cấu hình Cloud Billing export sang một BigQuery dataset đã được quản trị. Dữ liệu xuất giúp phân tích theo thời gian, project, SKU, location, labels và những trường credits nếu có trong kiểu export được chọn.

Các điểm cần lưu ý:

- Export có thể chỉ ghi nhận dữ liệu theo thời điểm kích hoạt hoặc có phạm vi dữ liệu quá khứ khác nhau tùy loại export và cấu hình.
- Export có độ trễ và BigQuery có thể phát sinh chi phí lưu trữ/truy vấn.
- Dữ liệu credits có thể gồm nhiều dòng/loại; khi tổng hợp SQL cần tránh nhân đôi chi phí nếu dùng `UNNEST` sai cách.
- Quyền truy cập billing dataset cần được quản trị vì có thông tin chi phí và cấu trúc hoạt động của tổ chức.
- Khi đánh giá số phải trả, cần đối chiếu hóa đơn và cách Google Cloud áp dụng credit, thuế và điều chỉnh.

Dùng Reports/Budgets là đủ cho nhiều lab nhỏ. BigQuery export phù hợp hơn khi cần **phân tích có thể lặp lại** cho nhiều project hoặc báo cáo quản trị.

## 11. Tình huống: số dư credits còn nhưng chi phí vẫn tăng

Một nhóm thử Cloud SQL và GKE trong project `atlas-learning-lab`. Sau vài ngày, màn hình Credits vẫn cho thấy số dư khuyến mại, nhưng Billing Reports đã có chi phí thực tế.

Hãy xử lý theo thứ tự:

1. **Xác định đúng billing account** của project. Credit đang xem có thực sự thuộc tài khoản/điều kiện áp dụng cho mức sử dụng này không?
2. **Đọc phạm vi credit**: credit có hết hạn, giới hạn dịch vụ/SKU hoặc điều kiện nào chưa đáp ứng không?
3. **Lọc báo cáo theo project, service và SKU**: chi phí đến từ node GKE, Cloud SQL, disk, network hay thành phần khác?
4. **So sánh tổng usage cost và credits đã ghi nhận**: có khoản ineligible nào không, có độ trễ báo cáo không?
5. **Kiểm tra tài nguyên thực tế**: node pool, disk, backups, reserved IP, buckets, artifact.
6. **Đánh giá hành động phù hợp**: dọn tài nguyên lab hết hạn, giảm quy mô, tạm dừng automation hoặc báo chủ sở hữu.
7. **Theo dõi lại sau khi báo cáo cập nhật**: xác nhận không còn mức sử dụng ngoài dự kiến trước khi đóng sự cố.

Không nên mặc định lỗi là do Cloud Billing tính sai hoặc tìm cách chuyển billing account để lấy credit ở tài khoản khác. Phải xác minh điều khoản và dữ liệu trước.

## 12. Bài tập tự kiểm tra

**Câu 1.** Bạn còn 40 USD credits và đã đặt budget 10 USD. Khi Reports chạm 10 USD, Google Cloud có tự động ngừng mọi VM không?

*Đáp án gợi ý:* Không. Budget tạo cảnh báo theo ngưỡng; nó không tự đặt trần cứng. Cần quy trình theo dõi, phản hồi và dọn tài nguyên phù hợp.

**Câu 2.** Bạn dừng VM Compute Engine nhưng vẫn thấy chi phí trong project. Liệt kê ba nguyên nhân có thể có.

*Đáp án gợi ý:* Persistent disk, snapshots, địa chỉ IP ngoài hoặc các tài nguyên mạng, dịch vụ lưu trữ/log liên quan vẫn có thể phát sinh phí. Ngoài ra, dữ liệu billing có thể cập nhật trễ.

**Câu 3.** Free Tier, Free Trial credit và Budget giống nhau không?

*Đáp án gợi ý:* Không. Free Tier là mức sử dụng miễn phí theo điều kiện sản phẩm; Free Trial credit là khoản ưu đãi thuộc chương trình dùng thử; Budget là công cụ theo dõi và cảnh báo chi phí.

**Câu 4.** Sau khi tạo Cloud Run service với lưu trữ ảnh và Cloud SQL, báo cáo chi phí thấp. Có nên dựa vào kết quả đó để ước tính chắc chắn chi phí cả tháng?

*Đáp án gợi ý:* Không. Cần tính tốc độ sử dụng, thời gian chạy, cấu hình min instances, database, storage, network egress, request và độ trễ ghi nhận billing. Dùng công cụ ước tính giá và theo dõi thực tế qua thời gian.

**Câu 5.** Một project production và một project lab cùng billing account. Nên đặt budget trên toàn tài khoản hay riêng project lab?

*Đáp án gợi ý:* Có thể cần **cả hai** với mục đích khác nhau. Budget tổng hỗ trợ giám sát toàn tài khoản; budget lọc project lab cho phép nhận diện chi phí phát sinh từ thử nghiệm mà không bị số liệu production che lấp.

**Câu 6.** GKE test đã xóa Deployment nhưng báo cáo vẫn ghi nhận phí GKE/Compute Engine. Điều gì cần kiểm tra?

*Đáp án gợi ý:* Cluster và node pool có thể còn tồn tại; node VM, persistent disk, IP hoặc load balancer vẫn có thể tính phí. Phải kiểm kê tài nguyên phụ trợ, không chỉ workload Kubernetes.

**Câu 7.** Báo cáo cho biết usage cost 36 USD, credits đủ điều kiện đã áp dụng 25 USD. Không có khoản điều chỉnh khác trong ví dụ, số tiền còn lại là bao nhiêu?

*Đáp án gợi ý:* 11 USD. Tuy nhiên, số tiền trên hóa đơn thật còn phụ thuộc thuế, thời điểm ghi nhận và các điều chỉnh được áp dụng.

## 13. Checklist ghi nhớ khi chuyển sang các bài GCP tiếp theo

- **Chọn project lab riêng** để dễ lọc cost và giới hạn phạm vi quyền.
- **Xem credit đúng billing account**, xác minh điều kiện, thời hạn và phạm vi dịch vụ được bù trừ.
- **Lập dự báo trước khi triển khai**, nhất là VM, GKE, Cloud SQL, networking và dịch vụ lưu trữ lâu dài.
- **Tạo budget và phân công người nhận cảnh báo**, nhưng không xem đó là cơ chế ngăn phí tuyệt đối.
- **Theo dõi cả gross usage cost và net cost**, không chỉ số tiền đang phải trả sau credit.
- **Dọn theo tài nguyên và phụ thuộc**, kiểm tra disk, snapshot, IP, backup, bucket, image, log và automation.
- **Kiểm tra lại khi số liệu billing cập nhật** trước khi xác nhận lab đã hết chi phí phát sinh ngoài dự kiến.
- **Cân bằng chi phí với độ tin cậy và an toàn dữ liệu** khi tối ưu môi trường thực tế.

Khi học đến Compute Engine, GKE, Cloud Run, cơ sở dữ liệu hay tự động hóa phát hành, hãy biến câu hỏi **“Ai sẽ dọn tài nguyên này, vào lúc nào và làm sao xác nhận không còn phát sinh phí?”** thành một phần bắt buộc của kế hoạch triển khai.

## Tài liệu tham khảo chính thức

- [Cloud Billing documentation](https://cloud.google.com/billing/docs)
- [View and manage credits — Google Cloud](https://cloud.google.com/billing/docs/how-to/credits)
- [Cloud Billing Reports](https://cloud.google.com/billing/docs/how-to/reports)
- [Create, edit, or delete budgets and budget alerts](https://cloud.google.com/billing/docs/how-to/budgets)
- [Programmatic notifications for budgets](https://cloud.google.com/billing/docs/how-to/notify)
- [Export Cloud Billing data to BigQuery](https://cloud.google.com/billing/docs/how-to/export-data-bigquery)
- [Google Cloud Free Program](https://cloud.google.com/free/docs/free-cloud-features)
- [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator)

