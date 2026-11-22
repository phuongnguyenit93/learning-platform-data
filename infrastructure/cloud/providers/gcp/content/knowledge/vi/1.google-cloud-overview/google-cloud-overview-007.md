# SLA, giai đoạn phát hành và vòng đời dịch vụ GCP

Google Cloud cung cấp nhiều dịch vụ để tổ chức tài nguyên theo organization và project, kiểm soát quyền bằng IAM, xây dựng mạng VPC, chạy ứng dụng trên Compute Engine, Google Kubernetes Engine (GKE) hoặc Cloud Run, và lưu trữ dữ liệu trên Cloud Storage hay các hệ cơ sở dữ liệu được quản lý. Tuy nhiên, chọn đúng loại dịch vụ mới chỉ là một phần của thiết kế hệ thống. Khi đưa ứng dụng vào sản xuất, nhóm vận hành còn phải trả lời ba câu hỏi:

1. **SLA:** Nhà cung cấp cam kết mức dịch vụ nào, đo bằng tiêu chí gì, trong phạm vi nào?
2. **Giai đoạn phát hành:** Tính năng đang ở mức thử nghiệm hay đã phát hành rộng rãi (General Availability, GA)?
3. **Vòng đời:** Dịch vụ, API và phiên bản đang được duy trì đến khi nào, và cần làm gì khi chúng thay đổi hoặc ngừng hỗ trợ?

Ba câu hỏi liên quan chặt chẽ nhưng không thay thế nhau. Một dịch vụ đã GA có thể không phù hợp với mục tiêu sẵn sàng của ứng dụng nếu cấu hình triển khai tạo ra điểm lỗi đơn. Một tính năng đang Preview có thể hấp dẫn nhưng còn thay đổi giao diện và điều kiện hỗ trợ. Một phiên bản đang chạy ổn định hôm nay vẫn có thể tới hạn ngừng hỗ trợ trong tương lai.

## 1. Hiểu đúng SLA, SLO và SLI

### 1.1. Ba khái niệm thường bị nhầm lẫn

| Thuật ngữ | Ý nghĩa | Ai xác định? | Ví dụ |
| --- | --- | --- | --- |
| **SLI – Service Level Indicator** | Chỉ số đo được của một khía cạnh chất lượng dịch vụ, như tỷ lệ yêu cầu thành công, độ trễ hoặc tỷ lệ lỗi. | Nhóm sở hữu dịch vụ xác định cách đo; nhà cung cấp cũng có cách đo riêng trong điều khoản. | 99,97% yêu cầu hợp lệ tới API được xử lý thành công trong 30 ngày. |
| **SLO – Service Level Objective** | Mục tiêu nội bộ hoặc mục tiêu vận hành đặt trên một SLI trong một khoảng thời gian. | Đội sản phẩm, SRE và các bên chịu trách nhiệm vận hành. | Ít nhất 99,95% yêu cầu hợp lệ thành công mỗi tháng. |
| **SLA – Service Level Agreement** | Cam kết dịch vụ theo thỏa thuận với bên sử dụng; thường quy định phạm vi, phép đo, điều kiện áp dụng và khoản tín dụng dịch vụ khi không đạt cam kết. | Nhà cung cấp và khách hàng theo điều khoản có hiệu lực. | Một SLA của sản phẩm GCP quy định tỷ lệ hoạt động hằng tháng và mức service credit khi đạt điều kiện yêu cầu. |

**SLI** cho biết thực tế đang diễn ra, **SLO** cho biết đội vận hành muốn đạt mức nào, còn **SLA** cho biết cam kết hợp đồng cụ thể. SLA không phải lời bảo đảm rằng ứng dụng sẽ không bao giờ gián đoạn. SLO của ứng dụng cũng không tự động bằng SLA của những dịch vụ đám mây mà ứng dụng sử dụng.

Trong Google Cloud, cần tra **SLA của đúng sản phẩm, cấu hình và điều kiện sử dụng**. Không có một tỷ lệ SLA duy nhất áp dụng cho mọi dịch vụ GCP. Các điều khoản có thể khác nhau theo cách triển khai, loại tài nguyên, phạm vi địa lý hoặc phiên bản điều khoản đang có hiệu lực. SLA cũng cần được phân biệt với cam kết về **độ bền dữ liệu (durability)**, độ trễ, thời gian phản hồi hỗ trợ và tính năng bảo mật.

### 1.2. Minh họa cách tính khả dụng

Với một hệ thống tự đo bằng thời gian, công thức đơn giản để hình dung là:

\[
\text{Khả dụng (\%)} = \frac{\text{Tổng thời gian quan sát} - \text{Thời gian gián đoạn}}{\text{Tổng thời gian quan sát}} \times 100
\]

Giả sử một tháng có đúng **30 ngày**, tương đương **43.200 phút**, và coi mọi phút gián đoạn đều được tính:

| Mức khả dụng giả định | Thời gian gián đoạn tối đa tương ứng trong 30 ngày |
| --- | ---: |
| 99% | 432 phút = 7 giờ 12 phút |
| 99,9% | 43,2 phút |
| 99,95% | 21,6 phút |
| 99,99% | 4,32 phút |

Ví dụ, nếu hệ thống gián đoạn 70 phút trong 30 ngày thì tỷ lệ tính theo công thức trên xấp xỉ **99,838%**. Nếu đội vận hành đặt SLO 99,9% theo đúng phép đo này, hệ thống đã bỏ lỡ SLO.

**Lưu ý:** Đây chỉ là bài toán minh họa để hiểu tỷ lệ phần trăm. SLA thực tế của từng sản phẩm Google Cloud có thể quy định “downtime”, thời điểm tính, khu vực, ngưỡng lỗi, thời gian loại trừ và cách làm tròn khác với phép tính đơn giản trên. Không sử dụng bảng này để tự kết luận Google phải cấp service credit.

### 1.3. Khi nào có service credit?

Khi xem một tài liệu SLA của GCP, hãy đọc ít nhất các thành phần sau:

| Thành phần cần kiểm tra | Câu hỏi vận hành |
| --- | --- |
| **Covered service / phạm vi** | Dịch vụ, tài nguyên, khu vực, phiên bản và cấu hình nào được cam kết? |
| **Chỉ số và thời gian đo** | “Monthly uptime percentage” hay chỉ số nào được sử dụng? Gián đoạn được xác định ra sao? |
| **Điều kiện và loại trừ** | Có yêu cầu cấu hình đặc thù không? Trường hợp nào không được tính vào vi phạm SLA? |
| **Mức service credit** | Nếu đáp ứng điều kiện, khoản tín dụng được tính theo bậc nào và trên phần phí đủ điều kiện nào? |
| **Thủ tục yêu cầu** | Có cần gửi yêu cầu với bằng chứng trong thời hạn nhất định không? Gửi qua kênh nào? |
| **Điều khoản hiệu lực** | Thỏa thuận nào áp dụng cho hợp đồng, sản phẩm và thời điểm sử dụng hiện tại? |

Service credit thường là **tín dụng theo điều khoản dịch vụ**, không đồng nghĩa với hoàn trả mọi thiệt hại kinh doanh. Việc nhận được tín dụng cũng không tự động khôi phục dữ liệu, giảm thời gian ngừng hoạt động hoặc đáp ứng các cam kết mà doanh nghiệp đã ký với khách hàng của mình.

### 1.4. SLA của nền tảng không phải SLA đầu cuối của ứng dụng

Giả sử một API đặt hàng hoạt động trên Cloud Run, ghi đơn hàng vào Cloud SQL và tải ảnh sản phẩm từ Cloud Storage. Yêu cầu đặt hàng có thể thất bại khi một trong những thành phần bắt buộc bị lỗi, khi ứng dụng triển khai sai, khi tài khoản dịch vụ thiếu quyền IAM, khi đạt quota, hoặc khi cấu hình mạng gây mất kết nối.

Do đó:

- **Cloud Run:** cần đánh giá điều kiện khả dụng của dịch vụ chạy ứng dụng và khả năng xử lý tải thực tế.
- **Cloud SQL:** cần xem cấu hình cơ sở dữ liệu, khả năng chuyển đổi khi xảy ra lỗi, kết nối và kế hoạch khôi phục.
- **Cloud Storage:** cần phân biệt khả năng truy cập dữ liệu, độ bền lưu trữ và đặc điểm của lớp lưu trữ/vị trí đã chọn.
- **GKE:** độ sẵn sàng của control plane không tự chứng minh rằng mọi Pod, node hoặc API do nhóm tự triển khai đều đạt SLO.
- **Compute Engine:** một máy ảo đơn lẻ vẫn có thể là điểm lỗi đơn dù dịch vụ Compute Engine có SLA; kiến trúc nhiều zone, cân bằng tải và phục hồi mới xử lý được nhiều dạng sự cố ứng dụng.

Không cộng hoặc nhân các con số SLA để khẳng định một SLA pháp lý mới cho ứng dụng. Có thể dùng mô hình xác suất khi đánh giá thiết kế, nhưng kết quả chỉ có ý nghĩa khi giả định về sự độc lập của lỗi, chuỗi phụ thuộc và khả năng dự phòng đúng với hệ thống. **Đo SLI đầu cuối từ góc nhìn người dùng** vẫn là việc bắt buộc.

### 1.5. Từ SLA đến thiết kế độ tin cậy

Khi mục tiêu kinh doanh là giảm gián đoạn, đội kỹ thuật phải thiết kế và vận hành phần mình kiểm soát:

1. Xác định hành trình quan trọng của người dùng, chẳng hạn “tạo đơn hàng thành công”, rồi xây SLI và SLO cho hành trình đó.
2. Lựa chọn kiến trúc phù hợp: nhiều zone, load balancing, dịch vụ quản lý có HA, khả năng tự mở rộng hoặc dự phòng liên vùng khi yêu cầu kinh doanh thực sự cần.
3. Kiểm tra cấu hình mạng VPC, firewall, IAM, service account, quota và giới hạn công suất; đây đều là nguồn lỗi có thể nằm ngoài phạm vi SLA nền tảng.
4. Thiết lập Cloud Monitoring, Cloud Logging, cảnh báo dựa trên SLO, kiểm thử chuyển đổi khi lỗi và quy trình xử lý sự cố.
5. Lập kế hoạch backup và kiểm tra khả năng restore. **HA giúp giảm gián đoạn; backup giúp khôi phục trước mất hoặc hỏng dữ liệu. Hai khả năng không thay thế nhau.**
6. Cân bằng độ tin cậy với chi phí: nhân bản tài nguyên, lưu lượng liên vùng, môi trường dự phòng và giám sát đều có thể tạo thêm chi phí.

Với SLO 99,9% theo tháng 30 ngày, “ngân sách lỗi” (error budget) tương đương 43,2 phút trong cách đo minh họa bằng thời gian. Khi ngân sách lỗi bị tiêu hao nhanh, nhóm có thể hạn chế phát hành nhiều rủi ro và ưu tiên xử lý độ tin cậy trước.

## 2. Các giai đoạn phát hành dịch vụ và tính năng GCP

### 2.1. Pre-GA và GA nói lên điều gì?

Google Cloud phát hành dịch vụ và tính năng theo nhiều giai đoạn. Tên gọi cụ thể có thể thay đổi theo sản phẩm; những thuật ngữ thường gặp gồm **Early Access**, **Alpha**, **Beta**, **Preview** (riêng tư hoặc công khai) và **General Availability (GA)**.

| Giai đoạn/nhãn thường gặp | Đặc điểm cần hiểu | Cách sử dụng phù hợp |
| --- | --- | --- |
| **Early Access / Alpha / Private Preview** | Quyền truy cập có thể giới hạn, cần đăng ký hoặc được mời; API, hành vi, vùng hỗ trợ và tài liệu có thể thay đổi mạnh. | Thử nghiệm ý tưởng, kiểm chứng khả thi, lấy phản hồi; xác nhận điều kiện và quyền truy cập. |
| **Beta / Public Preview / Preview** | Nhiều người dùng có thể thử hơn, nhưng tính năng vẫn thuộc diện chưa GA và có thể thay đổi hoặc có giới hạn sử dụng, hỗ trợ. | Thử nghiệm có kiểm soát, kiểm thử tương thích và đánh giá chi phí/lợi ích trước khi quyết định dùng cho workload quan trọng. |
| **GA – General Availability** | Sản phẩm hoặc tính năng đã được phát hành để sử dụng rộng rãi theo tài liệu và điều khoản hiện hành. | Ứng viên chính cho hệ thống sản xuất, sau khi kiểm tra bảo mật, SLA, khu vực, quota, chi phí và khả năng vận hành. |

Các nhãn Preview/Alpha/Beta không nhất thiết luôn xuất hiện theo đúng một chuỗi hoặc có cùng quyền lợi trên mọi sản phẩm. **Pre-GA** là cách gọi chung cho các đề xuất chưa GA và thường có điều khoản sử dụng riêng. Với tính năng Pre-GA, không được mặc định rằng có SLA, chính sách hỗ trợ, tính tương thích ngược hoặc sự sẵn có ở mọi region tương đương GA; phải xác nhận ở tài liệu sản phẩm và điều khoản áp dụng.

**GA cũng không đồng nghĩa với “chắc chắn có SLA ở mọi cấu hình”.** Một dịch vụ được phát hành rộng rãi chỉ đáp ứng được yêu cầu sản xuất sau khi đội kỹ thuật kiểm tra kỹ điều khoản và thiết kế thực tế. Đồng thời, **một dịch vụ GA có thể cung cấp thêm tính năng Preview**: cần đánh giá giai đoạn phát hành ở cấp tính năng, API hoặc phiên bản đang dùng, thay vì chỉ nhìn tên dịch vụ.

### 2.2. Ba kiểu “phát hành” cần phân biệt

Trong môi trường GCP, từ *release* có thể nói đến ba việc khác nhau:

| Ngữ cảnh | Ví dụ | Quyết định cần đưa ra |
| --- | --- | --- |
| **Giai đoạn sản phẩm/tính năng của Google** | Một API có nhãn Preview, sau đó GA. | Có nên phụ thuộc vào tính năng này trong sản xuất và điều khoản nào đang áp dụng? |
| **Phiên bản và kênh phát hành nền tảng** | GKE có các release channel như Rapid, Regular và Stable. | Nhận bản cập nhật với nhịp độ nào, tương thích ra sao và khi nào cần nâng cấp? |
| **Quy trình phát hành ứng dụng của đội phát triển** | Đưa mã nguồn qua dev, test/staging, canary rồi production. | Khi nào triển khai, kiểm thử và rollback/roll-forward thế nào? |

Các **release channel của GKE** liên quan đến nhịp độ nhận phiên bản Kubernetes và nâng cấp, không phải cách gọi khác của Preview/GA cho chính GKE. Tương tự, việc một ứng dụng đang ở “staging” không cho biết API Cloud Run mà nó sử dụng đang ở giai đoạn phát hành nào.

### 2.3. Quy trình đánh giá một tính năng chưa GA

Ví dụ, nhóm muốn dùng một tính năng mới của BigQuery hoặc Cloud Run đang được gắn nhãn Preview. Trước khi tích hợp vào dịch vụ đang phục vụ khách hàng, hãy trả lời:

1. Tính năng được bật cho project, organization, region và nhóm người dùng nào? Có yêu cầu đăng ký hoặc chấp thuận riêng không?
2. API, sơ đồ dữ liệu, cấu hình và giới hạn hiện có có thể thay đổi như thế nào? Có cách kiểm thử và cập nhật client không?
3. Điều khoản Pre-GA, bảo mật dữ liệu, điều kiện xử lý dữ liệu và cam kết hỗ trợ được mô tả ra sao?
4. Có SLA áp dụng cho **chính tính năng** này không, hay chỉ áp dụng cho phần dịch vụ GA khác?
5. Nếu tính năng bị thay đổi hoặc không tiếp tục phát triển, nhóm có phương án dự phòng hoặc chuyển sang giải pháp GA nào?

Với tính năng chưa GA, có thể dành một project thử nghiệm riêng, áp dụng IAM quyền tối thiểu, dùng dữ liệu thử phù hợp, đặt quota/budget và đo bằng các thử nghiệm thực tế. Chỉ đưa vào luồng quan trọng khi rủi ro, điều khoản và khả năng khôi phục đã được chấp nhận rõ ràng.

## 3. Vòng đời dịch vụ GCP: từ thử nghiệm tới ngừng cung cấp

### 3.1. Vòng đời khái quát

Sơ đồ sau mô tả các **trạng thái có thể gặp**, không phải lộ trình bắt buộc cho mọi dịch vụ:

~~~mermaid
flowchart LR
    A["Ý tưởng / Early Access"] --> B["Pre-GA: Alpha, Beta, Preview"]
    B --> C["GA: vận hành và cải tiến"]
    C --> D["Deprecated / thông báo chuyển đổi"]
    D --> E["Ngừng hỗ trợ hoặc ngừng cung cấp"]
    B -. "Có thể dừng thử nghiệm" .-> E
    C -. "Phiên bản cũ kết thúc hỗ trợ" .-> E
~~~

- **Thử nghiệm, Pre-GA:** phạm vi truy cập và tính năng còn thay đổi; sản phẩm có thể tiếp tục tới GA, đổi thiết kế hoặc dừng phát triển.
- **GA và duy trì:** Google có thể bổ sung tính năng, sửa lỗi, cập nhật API, phát hành phiên bản mới hoặc điều chỉnh thông số vận hành theo chính sách sản phẩm.
- **Deprecated (khuyến nghị ngừng sử dụng hoặc chuyển đổi):** một API, phiên bản hoặc tính năng được thông báo là cũ, cần chuyển sang lựa chọn mới; đôi khi vẫn chạy trong thời gian chuyển tiếp.
- **End of support:** kết thúc phạm vi hỗ trợ của một phiên bản/tính năng theo chính sách liên quan; không nhất thiết có nghĩa là toàn bộ dịch vụ lập tức bị tắt.
- **Shutdown / Discontinued:** chức năng hoặc dịch vụ không còn được cung cấp theo lịch và phạm vi được công bố. Khi đó ứng dụng còn phụ thuộc trực tiếp có thể ngừng hoạt động.

Thời gian thông báo, hỗ trợ chuyển đổi và điều kiện ngừng sử dụng **khác nhau theo dịch vụ, loại API, phiên bản và điều khoản**. Không suy ra một thời hạn chuyển đổi chung cho toàn bộ GCP. Hãy đọc thông báo chính thức cho tài nguyên mà ứng dụng thực sự đang dùng.

### 3.2. Vòng đời ở nhiều cấp độ

Một hệ thống có thể chịu tác động ở nhiều cấp:

| Cấp độ thay đổi | Ví dụ tình huống | Rủi ro đối với ứng dụng |
| --- | --- | --- |
| **Toàn bộ dịch vụ** | Nhà cung cấp công bố dừng một sản phẩm. | Phải chọn kiến trúc hoặc nhà cung cấp thay thế. |
| **Tính năng** | Một tính năng Preview thay đổi cách dùng hoặc không được tiếp tục cung cấp. | Luồng nghiệp vụ sử dụng riêng tính năng đó cần sửa. |
| **API / phiên bản API** | Phiên bản API cũ bị deprecated. | SDK, mã tích hợp hoặc công cụ triển khai phải nâng cấp. |
| **Runtime / phiên bản nền tảng** | Một phiên bản Kubernetes hoặc runtime ứng dụng kết thúc hỗ trợ. | Cần nâng cấp, kiểm tra tương thích và thử lại quy trình triển khai. |
| **Cấu hình / chính sách** | Điều kiện sử dụng, cấu hình bảo mật hoặc khu vực hỗ trợ thay đổi. | Hệ thống có thể cần chỉnh IAM, mạng, tài nguyên hoặc chi phí. |

Ví dụ với GKE, cần theo dõi vòng đời **phiên bản Kubernetes**, lịch nâng cấp cụm và release channel đã chọn. Với Cloud Run, cần quan tâm cả tính năng nền tảng lẫn runtime, container image và các thư viện do nhóm phát triển quản lý. Với Compute Engine, việc một image hệ điều hành hoặc phiên bản phần mềm hết hỗ trợ là vấn đề khác với vòng đời của bản thân dịch vụ máy ảo.

### 3.3. Nguồn thông tin và cách tổ chức theo dõi

Không nên chờ tới khi triển khai lỗi mới tìm hiểu vòng đời. Trong quá trình thiết kế và vận hành, nhóm nên:

- Theo dõi tài liệu sản phẩm và **release notes** để phát hiện bản phát hành mới, thay đổi hành vi, giới hạn, nâng cấp bảo mật và thông báo deprecated.
- Đọc **SLA và Service Terms** theo đúng dịch vụ, thời điểm và hợp đồng áp dụng; lưu ngày kiểm tra cho các quyết định kiến trúc quan trọng.
- Theo dõi thông báo liên quan qua các kênh quản trị, hỗ trợ hoặc trang thông tin của dịch vụ được sử dụng; kiểm tra đầu mối nhận thông báo trong tổ chức.
- Quản lý danh mục tài nguyên theo project, owner, mức độ quan trọng, region, phiên bản, API phụ thuộc và mốc thời gian cần hành động.
- Đưa kiểm tra tương thích, khả năng phục hồi và chi phí vào chu kỳ nâng cấp định kỳ.

Có thể dùng Google Cloud CLI để **bắt đầu** kiểm kê một số phần của project:

~~~bash
# PROJECT_ID là ID project mà người vận hành có quyền xem.
gcloud services list --enabled --project="$PROJECT_ID"
gcloud compute instances list --project="$PROJECT_ID"
gcloud container clusters list --project="$PROJECT_ID"
gcloud run services list --project="$PROJECT_ID"
~~~

Danh sách API được bật **không phải** danh sách đầy đủ dịch vụ đang tiêu thụ tài nguyên hoặc tính năng Preview đang dùng. Các lệnh trên chỉ là điểm khởi đầu; cần bổ sung kiểm kê tài nguyên, cấu hình, phiên bản, hạ tầng dưới dạng mã (IaC), nhật ký thay đổi và các phụ thuộc ứng dụng. Quyền IAM, API bật và phiên bản CLI cũng ảnh hưởng đến kết quả lệnh.

## 4. Ra quyết định triển khai: kết hợp SLA, giai đoạn phát hành và vòng đời

### 4.1. Tình huống: hệ thống đặt hàng trên Google Cloud

Một doanh nghiệp triển khai API đặt hàng bằng **Cloud Run**, dữ liệu giao dịch trong **Cloud SQL**, ảnh sản phẩm trên **Cloud Storage**. Nhóm dùng **Cloud Monitoring** để theo dõi tỷ lệ yêu cầu đặt hàng thành công và đặt SLO nội bộ **99,95% mỗi tháng**. Đây là mục tiêu do nhóm tự chọn, không phải số SLA chung của các sản phẩm GCP.

Khi lựa chọn cấu hình, nhóm thực hiện các quyết định sau:

| Quyết định | Cách đánh giá |
| --- | --- |
| Đưa API đặt hàng vào production | Kiểm tra các thành phần bắt buộc đã GA hay chưa; xem SLA theo đúng dịch vụ, region và cấu hình đã chọn. |
| Tăng khả năng chịu lỗi cơ sở dữ liệu | Đánh giá lựa chọn HA và hành vi failover của Cloud SQL; kiểm tra lại kết nối, giao dịch và thời gian phục hồi của ứng dụng. |
| Sử dụng một tính năng Preview để tạo báo cáo | Cô lập ở luồng báo cáo không chặn giao dịch; xác nhận điều khoản, kế hoạch thay thế và tính tương thích. |
| Cập nhật runtime / API | Theo dõi vòng đời phiên bản, kiểm thử trên staging, phát hành từng bước và chuẩn bị phương án khôi phục. |
| Chứng minh độ tin cậy với khách hàng | Thu thập SLI của chính API, báo cáo SLO, minh bạch sự cố; không xem SLA của từng tài nguyên là lời hứa đầu cuối. |

Nếu Cloud SQL cần khởi động lại hoặc quyền truy cập dữ liệu bị cấu hình sai, các yêu cầu đặt hàng vẫn có thể lỗi dù Cloud Run đang phục vụ HTTP bình thường. Vì vậy, SLI “Cloud Run còn phản hồi” không đầy đủ bằng SLI “tạo đơn hàng thành công”. Ngược lại, một sự cố dịch vụ nền tảng có thể tác động tới sản phẩm mà không nhất thiết đủ điều kiện nhận service credit nếu không thỏa các định nghĩa trong SLA.

### 4.2. Trình tự xử lý khi có thông báo deprecated

Giả sử nhóm nhận thông báo một phiên bản API đang sử dụng sẽ ngừng hỗ trợ:

1. **Xác định tác động:** tìm các project, dịch vụ, SDK, job tự động và hệ thống bên ngoài phụ thuộc phiên bản đó; chỉ định người chịu trách nhiệm.
2. **Xác nhận mốc thời gian:** đọc thông báo gốc, phạm vi ảnh hưởng, ngày thay đổi và phương án được nhà cung cấp khuyến nghị.
3. **Chọn hướng chuyển đổi:** phiên bản API mới, tính năng GA thay thế, cập nhật SDK hoặc thay đổi kiến trúc; xem xét bảo mật, dữ liệu, IAM, mạng và chi phí.
4. **Thử nghiệm:** kiểm thử tương thích, dữ liệu, quyền truy cập, hiệu năng, giới hạn và khôi phục trên môi trường phù hợp; đo các SLI liên quan.
5. **Triển khai có kiểm soát:** rollout từng phần nếu khả thi, theo dõi lỗi, đặt ngưỡng dừng phát hành và chuẩn bị rollback hoặc roll-forward tùy loại thay đổi. Một số nâng cấp trạng thái hoặc phiên bản có thể không cho phép hạ cấp.
6. **Xác minh và đóng việc:** loại bỏ phụ thuộc cũ, cập nhật runbook, tài liệu kiến trúc, cảnh báo và bảng theo dõi vòng đời.

Thay thế API trước hạn không chỉ tránh lỗi khi ngừng hỗ trợ mà còn giúp nhóm chủ động đánh giá thay đổi chi phí, quyền truy cập và hành vi nghiệp vụ thay vì xử lý dưới áp lực sự cố.

### 4.3. Checklist tối thiểu trước khi dùng một dịch vụ GCP trong production

| Nhóm kiểm tra | Tiêu chí hoàn thành |
| --- | --- |
| **Nhu cầu** | Ghi rõ tác vụ, SLI/SLO của người dùng và hậu quả khi dịch vụ gián đoạn. |
| **Maturity** | Xác định GA hay Pre-GA ở cấp tính năng thực dùng; lưu điều khoản và giới hạn tương ứng. |
| **SLA** | Xác định chính xác SLA áp dụng, cấu hình đủ điều kiện, cách đo, loại trừ và thủ tục service credit. |
| **Kiến trúc** | Đánh giá zone/region, HA, phụ thuộc nối tiếp, timeout, retry, idempotency, quota và kịch bản lỗi. |
| **Bảo mật** | Đánh giá IAM, service account, VPC, chính sách dữ liệu, mã hóa và quyền quản trị. |
| **Quan sát** | Có metrics, logs, dashboards, cảnh báo SLO, người nhận cảnh báo và runbook xử lý. |
| **Khôi phục** | Có backup/restore phù hợp, kiểm thử phục hồi và các mục tiêu RTO/RPO nếu cần. |
| **Vòng đời** | Có chủ sở hữu theo dõi release notes, phiên bản và thông báo deprecated/end of support. |
| **Chi phí** | Dự toán tài nguyên, truyền dữ liệu, dự phòng, giám sát; đặt budget và cảnh báo chi phí phù hợp. |

## 5. Những hiểu nhầm cần tránh

**“Có SLA 99,9% thì hệ thống chắc chắn chỉ được downtime 43,2 phút.”** Sai. Con số này là cách chuyển đổi toán học trong ví dụ tháng 30 ngày; phạm vi SLA thực tế có quy tắc riêng, còn downtime của ứng dụng phụ thuộc vào nhiều thành phần do khách hàng vận hành.

**“Dịch vụ GA thì mọi API và tính năng đều GA.”** Sai. Cần kiểm tra từng tính năng, API, phiên bản và region; một dịch vụ GA có thể chứa phần mở rộng Preview.

**“Preview chắc chắn không dùng được trong production.”** Quá tuyệt đối. Việc sử dụng phụ thuộc điều khoản, chính sách, đặc điểm workload và mức rủi ro chấp nhận được. Với luồng quan trọng, ưu tiên phương án GA phù hợp và có kế hoạch thay thế rõ ràng.

**“Deprecated nghĩa là hôm nay dịch vụ đã tắt.”** Không nhất thiết. Deprecated thường báo hiệu cần chuyển đổi, còn ngày kết thúc hỗ trợ hoặc shutdown phải xem theo thông báo cụ thể.

**“Đã có multi-zone là không cần backup.”** Sai. Dự phòng vùng/zone giúp giảm một số loại gián đoạn, nhưng không thay thế khả năng phục hồi dữ liệu bị xóa nhầm, sai logic hoặc bị hỏng.

**“Service credit là biện pháp khôi phục sự cố.”** Sai. Service credit liên quan đến quyền lợi theo SLA; khôi phục dịch vụ vẫn đòi hỏi kiến trúc chịu lỗi, giám sát, thao tác vận hành và quy trình ứng cứu.

## 6. Tài liệu chính thức cần đối chiếu

Điều khoản, nhãn phát hành và lịch ngừng hỗ trợ là thông tin có thể thay đổi. Khi dùng bài học để ra quyết định cho hệ thống thực tế, hãy kiểm tra bản đang có hiệu lực tại:

- **Google Cloud Service Level Agreements:** https://cloud.google.com/terms/sla
- **Google Cloud Service Specific Terms:** https://cloud.google.com/terms/service-terms
- **Google Cloud documentation:** https://cloud.google.com/docs
- **Google Cloud release notes:** https://cloud.google.com/release-notes
- **Tài liệu release channels của GKE:** https://cloud.google.com/kubernetes-engine/docs/concepts/release-channels

Với mỗi lựa chọn dịch vụ, mục tiêu đúng là **biết cam kết được đo như thế nào, đánh giá mức độ sẵn sàng của tính năng và theo dõi thay đổi trong suốt vòng đời**. Những thông tin đó phải được chuyển thành quyết định kiến trúc, SLO đầu cuối, kế hoạch nâng cấp và năng lực ứng phó sự cố có thể kiểm chứng.
