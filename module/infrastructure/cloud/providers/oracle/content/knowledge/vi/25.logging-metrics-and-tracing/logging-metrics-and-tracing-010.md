# Synthetic monitoring và giám sát giao dịch người dùng

## 1. Mục tiêu và tình huống vận hành

Một cổng đặt hàng chạy trên Oracle Cloud Infrastructure (OCI) có Load Balancer, ứng dụng Java trên Compute và cơ sở dữ liệu Oracle trong mạng riêng. CPU vẫn thấp, các máy chủ vẫn hoạt động, nhưng người dùng đăng nhập xong lại không xem được đơn hàng. Hạ tầng còn hoạt động chưa đủ để kết luận một giao dịch nghiệp vụ còn sử dụng được.

Trong chương **Logs, metrics và tracing** của module **CLOUD_PROVIDERS_ORACLE**, bài này nối trạng thái hạ tầng với trải nghiệm sử dụng ứng dụng. Sau bài học, người học có thể:

- Chọn giao dịch quan trọng để kiểm tra định kỳ và xác định rõ kết quả mong đợi.
- Phân biệt synthetic monitoring với Real User Monitoring (RUM).
- Thiết kế monitor trong OCI APM, chọn điểm đo phù hợp với mạng công khai hoặc VCN.
- Kết hợp kết quả kiểm tra với metrics, trace và log để khoanh vùng sự cố.
- Vận hành monitor với quyền truy cập, dữ liệu kiểm thử và chi phí phù hợp.

Synthetic monitoring tạo lưu lượng kiểm tra có kiểm soát thay cho thao tác thật của khách hàng. Trong OCI Application Performance Monitoring (APM), nhóm tính năng trước đây mang tên **Synthetic Monitoring** đã được đổi tên thành **Availability Monitoring**. Bài học vẫn dùng thuật ngữ synthetic để chỉ phương pháp đo chủ động. [Thông báo đổi tên của Oracle](https://docs.oracle.com/en-us/iaas/releasenotes/apm/availability-monitoring.htm).

Các tên ứng dụng, URL, ngưỡng và lịch chạy trong bài là ví dụ thiết kế. Chúng cần được điều chỉnh theo hệ thống thực tế.

## 2. Ba góc nhìn về một giao dịch

**Synthetic monitoring** trả lời: “Từ vị trí đã chọn, kịch bản chuẩn có hoàn thành được vào thời điểm này không?”. Monitor có thể chạy cả khi ứng dụng chưa có khách truy cập.

**Real User Monitoring** trả lời: “Những người thực sự sử dụng ứng dụng đang gặp trải nghiệm gì?”. Kết quả chịu ảnh hưởng của thiết bị, trình duyệt, mạng và những đường đi mà người dùng thực sự thực hiện.

**Theo dõi phía máy chủ** trả lời: “Yêu cầu đã đi qua những thành phần nào và thời gian bị tiêu tốn ở đâu?”. Trace có thể giải thích một yêu cầu chậm; log bổ sung thông tin xử lý cụ thể.

| Góc nhìn | Dữ liệu đầu vào | Câu hỏi tiêu biểu | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| Synthetic | Một kịch bản và dữ liệu kiểm thử đã chọn | Đăng nhập rồi tra cứu đơn hàng có thành công không? | Chỉ phản ánh đường đi và điểm đo được cấu hình |
| RUM | Hoạt động của người dùng có phát sinh telemetry | Nhóm người dùng nào gặp trang chậm hoặc lỗi JavaScript? | Không có quan sát khi không có lưu lượng hoặc agent bị chặn |
| Trace và log phía máy chủ | Yêu cầu được instrument và dữ liệu vận hành | Lỗi nằm ở xác thực, ứng dụng hay truy vấn Oracle Database? | Không mô tả đầy đủ việc hiển thị và tương tác trong trình duyệt |

Một monitor REST trả HTTP 200 chưa chứng minh nút “Xác nhận” hoạt động. Một monitor trình duyệt chạy thành công từ một trung tâm dữ liệu cũng chưa chứng minh khách dùng mạng di động có trải nghiệm tốt.

Synthetic thường tạo một lượng yêu cầu nhỏ theo lịch để quan sát tình trạng dịch vụ. Kiểm thử tải chủ động tạo mức tải và độ đồng thời nhằm tìm giới hạn năng lực. Không tăng hàng loạt monitor để thay thế một kế hoạch kiểm thử tải.

## 3. Các thành phần trong OCI

Đường đi quan sát có thể được thiết kế như sau:

~~~mermaid
flowchart LR
    PUB["Public Vantage Point"] --> EDGE["WAF / Load Balancer"]
    USER["Trình duyệt người dùng"] --> EDGE

    subgraph VCN["VCN của ứng dụng"]
        DVP["Dedicated Vantage Point"] --> PRIVATE["Endpoint riêng"]
        EDGE --> APP["Ứng dụng Java trên Compute"]
        PRIVATE --> APP
        APP --> DB["Oracle Database"]
    end

    PUB -. "Kết quả monitor" .-> APM["APM domain"]
    DVP -. "Kết quả monitor" .-> APM
    USER -. "APM Browser Agent / RUM" .-> APM
    APP -. "Trace khi đã instrument" .-> APM
    APP -. "Log được thu thập" .-> LOG["OCI Logging"]
    APM -. "Metrics" .-> MON["OCI Monitoring"]
    MON --> ALARM["Alarm"]
    ALARM --> NOTIFY["Notifications"]
~~~

Các mũi tên telemetry biểu diễn những luồng cần cấu hình; tạo monitor không tự động instrument ứng dụng hoặc thu thập toàn bộ log.

**APM domain** là phạm vi tổ chức dữ liệu APM. **Monitor** xác định đối tượng và cách kiểm tra; **script** mô tả các bước cho giao dịch nhiều thao tác; **vantage point** là nơi thực thi kiểm tra. Quy trình thiết lập của Oracle bắt đầu bằng quyền truy cập và APM domain, sau đó chuẩn bị script nếu cần, chọn điểm đo và tạo monitor. [Thiết lập Availability Monitoring](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/synthetic-monitoring.html).

Trong một tenancy có nhiều môi trường, nên làm rõ compartment chứa tài nguyên quan sát, môi trường của endpoint và nhóm chịu trách nhiệm. Một dashboard trộn kết quả staging với production sẽ khiến số liệu khó sử dụng dù dữ liệu vẫn được thu thập đầy đủ.

### Chọn điểm đo theo câu hỏi cần trả lời

- **Public Vantage Point:** phù hợp để quan sát đường truy cập công khai mà khách hàng sử dụng.
- **Dedicated Vantage Point:** đặt trong tenancy để kiểm tra endpoint riêng hoặc đường mạng nội bộ.
- **On-premise Vantage Point:** hữu ích khi cần góc nhìn từ môi trường doanh nghiệp hoặc một môi trường triển khai được kiểm soát. [Các lựa chọn điểm đo](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/synthetic-monitoring.html).

Dedicated Vantage Point có thể được triển khai bằng mẫu của OCI Resource Manager. Đây là một thành phần có hạ tầng và đường mạng riêng cần quản lý. Với DNS riêng, phải kiểm tra khả năng phân giải từ môi trường thực thi monitor; việc một máy quản trị phân giải thành công chưa đủ xác nhận monitor cũng làm được. [Dedicated Vantage Points](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/use-dedicated-vantage-points.html).

Một điểm đo trong VCN gần ứng dụng giúp tách ảnh hưởng mạng Internet, nhưng có thể bỏ qua lỗi DNS công khai, WAF hoặc đường vào Load Balancer. Vì vậy, điểm đo nội bộ và công khai phục vụ hai phép quan sát khác nhau.

## 4. Thiết kế giao dịch trước khi tạo monitor

Hãy bắt đầu bằng kết quả mà người dùng cần đạt được. Với cổng đặt hàng, “xem được chi tiết đơn hàng mẫu sau khi đăng nhập” là một mục tiêu rõ hơn “website còn sống”.

Một hợp đồng kiểm tra có thể gồm:

| Thành phần | Thiết kế minh họa |
| --- | --- |
| Tên giao dịch | Đăng nhập và xem đơn hàng mẫu |
| Đối tượng | Môi trường lab, tài khoản kiểm thử riêng |
| Điểm bắt đầu | Trang đăng nhập chưa có phiên |
| Điểm kết thúc | Chi tiết đúng đơn hàng mẫu đã hiển thị |
| Điều kiện đúng | Đúng người dùng, đúng mã mẫu, trạng thái đơn hàng mong đợi |
| Giới hạn thời gian | Hoàn thành trong 12 giây, timeout kỹ thuật 30 giây |
| Tần suất | Mỗi 5 phút tại hai điểm đo |
| Chủ sở hữu | Nhóm vận hành cổng đặt hàng |
| Dữ liệu bị thay đổi | Không tạo đơn hàng, không gửi thông báo khách hàng |

Các ngưỡng trên là giả định cho lab, không phải giá trị mặc định hay giới hạn của OCI.

### Chia giao dịch thành các checkpoint

| Bước | Thao tác | Điều kiện xác nhận |
| --- | --- | --- |
| 1 | Mở trang đăng nhập | Biểu mẫu có thể tương tác |
| 2 | Đăng nhập bằng tài khoản kiểm thử | Hiển thị khu vực đã xác thực |
| 3 | Mở danh sách đơn hàng | Có đơn hàng mẫu đã chuẩn bị |
| 4 | Mở chi tiết | Đúng mã và trạng thái mẫu |
| 5 | Đăng xuất | Phiên kết thúc theo thiết kế ứng dụng |

Cần xác nhận kết quả sau thao tác. Việc nút đã được nhấn hoặc trang đã đổi URL chưa đủ chứng minh nghiệp vụ thành công.

Nếu kiểm tra luồng tạo dữ liệu, phải thiết kế mã chạy duy nhất, tính lặp an toàn và quy trình dọn dữ liệu. Ví dụ, chỉ tạo đơn hàng trong tenant kiểm thử và dùng cổng thanh toán sandbox. Không để lịch chạy định kỳ tạo thanh toán, email hoặc trừ kho thật ngoài ý muốn.

Một lượt chạy lỗi ở giữa cũng có thể để lại phiên, giỏ hàng hoặc bản ghi tạm. Dọn dữ liệu nên dựa trên nhãn kiểm thử và thời hạn tồn tại, thay vì chỉ dựa vào bước cuối của script.

## 5. Chọn loại monitor theo mức cần xác nhận

Bốn lựa chọn thường dùng cho ứng dụng web và API là:

| Loại | Phạm vi phù hợp |
| --- | --- |
| REST | Một yêu cầu đến URL và kiểm tra phản hồi |
| Scripted REST | Chuỗi lời gọi API có phụ thuộc kết quả |
| Browser | Tải một URL bằng trình duyệt |
| Scripted Browser | Chuỗi thao tác giao diện của một giao dịch |

OCI hỗ trợ các loại này; tài liệu còn liệt kê những monitor khác như Network, DNS, SQL và FTP. Với bài học này, trọng tâm là giao dịch web/API. [Tạo monitor và các loại được hỗ trợ](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/create-monitor.html).

Nên phối hợp kiểm tra đơn giản với kiểm tra nghiệp vụ. Một phép gọi API nhỏ giúp nhận biết lỗi đường vào nhanh hơn; một giao dịch trình duyệt phát hiện thêm lỗi hiển thị, JavaScript và điều hướng. Khi API thành công nhưng giao dịch trình duyệt lỗi, phạm vi điều tra đã được thu hẹp.

### Ví dụ thiết kế kiểm tra REST

Ứng dụng lab cung cấp endpoint đọc dữ liệu mẫu:

~~~http
GET /api/monitoring/sample-order HTTP/1.1
Host: orders.lab.example.com
Accept: application/json
~~~

Phản hồi mong đợi:

~~~json
{
  "orderCode": "SYNTHETIC-DEMO-001",
  "status": "READY",
  "readable": true
}
~~~

Các URL và trường JSON này do ứng dụng lab tự định nghĩa, không phải API của OCI.

Monitor cần xác nhận mã HTTP và nội dung đủ để chứng minh đã đi qua chức năng cần kiểm tra. Nếu endpoint chỉ trả một chuỗi cố định từ bộ nhớ, kết quả của nó không đại diện cho đường đọc dữ liệu Oracle Database.

OCI có tùy chọn xác thực mã phản hồi, kiểm tra nội dung và xác minh SSL cho các loại monitor tương ứng. Giữ xác minh chứng chỉ TLS trong phép đo thông thường; nếu bỏ qua xác minh, monitor có thể không phản ánh lỗi mà trình duyệt khách hàng sẽ gặp. [Các tùy chọn xác thực phản hồi](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/create-monitor.html).

Với nhiều điều kiện JSON hoặc nhiều yêu cầu phụ thuộc nhau, dùng script để diễn đạt kiểm tra rõ ràng. Không chỉ tìm chữ “READY” ở bất kỳ vị trí nào nếu cùng phản hồi có thể chứa thông báo lỗi hoặc nhiều đối tượng.

## 6. Viết kịch bản trình duyệt ít nhiễu

Một kịch bản tốt cần ổn định khi ứng dụng vẫn hoạt động đúng, đồng thời thất bại khi kết quả nghiệp vụ sai.

Có thể dùng Selenium IDE để ghi hành trình và xuất tệp `.side` cho Scripted Browser. Oracle cũng tài liệu hóa lựa chọn script trình duyệt khác, nhưng lab này chọn luồng Selenium để có một quy trình nhất quán. Tham số script có thể được đánh dấu **Value is secret**; vẫn phải tránh đưa bí mật vào log, ảnh hoặc nội dung trang. [Tạo và tham số hóa script](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/create-script.html).

Thuật toán dưới đây là mã giả mô tả yêu cầu, không phải tệp có thể tải trực tiếp vào OCI:

~~~text
Bắt đầu với phiên trình duyệt mới
Mở trang đăng nhập
Chờ biểu mẫu sẵn sàng
Điền tài khoản và mật khẩu kiểm thử từ tham số bí mật
Gửi biểu mẫu
Chờ dấu hiệu xác nhận đã đăng nhập
Mở đơn hàng mẫu
Chờ phần chi tiết xuất hiện
Xác nhận mã đơn hàng và trạng thái mong đợi
Ghi nhận thời gian hoàn thành giao dịch
Đăng xuất
~~~

### Chờ điều kiện thay cho chờ cứng

Giả sử một trang tải trong 0,8–2,5 giây. Chèn lệnh đợi cố định một giây sẽ làm monitor lỗi ngẫu nhiên; đợi cố định mười giây lại kéo dài mọi lần chạy.

Nên chờ một phần tử hoặc điều kiện nghiệp vụ với timeout hữu hạn. Khi điều kiện đạt được, tiếp tục ngay. Dùng thuộc tính kiểm thử ổn định như `data-testid="order-detail"` thay cho vị trí phần tử trong một cây DOM dễ thay đổi. Đây là quy ước cần phối hợp với nhóm phát triển ứng dụng.

Không dùng thời gian chờ thao tác để che một hồi quy hiệu năng. Cần phân biệt:

- **Timeout:** giới hạn để kết thúc một lượt chạy không thể tiếp tục.
- **Ngưỡng chất lượng:** thời gian tối đa mà giao dịch còn đáp ứng kỳ vọng.
- **Thời gian chờ cố ý:** khoảng nghỉ mô phỏng thao tác hoặc đồng bộ, phải được giải thích.

Ví dụ, một giao dịch chạy 18 giây có thể chưa timeout ở giới hạn 30 giây nhưng đã vi phạm mục tiêu 12 giây.

### Kiểm soát trạng thái và danh tính

Mỗi lượt chạy cần có điểm bắt đầu xác định. Nếu monitor luôn kế thừa một phiên còn đăng nhập, nó có thể bỏ qua hoàn toàn lỗi ở bước đăng nhập.

Tài khoản kiểm thử cần quyền nghiệp vụ tối thiểu, dữ liệu mẫu ổn định và quy trình xoay vòng thông tin xác thực. Nếu dùng chung một tài khoản trên nhiều điểm đo, hãy kiểm tra cơ chế khóa tài khoản, giới hạn phiên và thu hồi phiên cũ. Các cơ chế này có thể làm những lượt chạy đồng thời ảnh hưởng lẫn nhau.

Với MFA, CAPTCHA hoặc cơ chế chống bot, thiết kế phương án kiểm thử cùng nhóm bảo mật và nhóm ứng dụng. Không tắt bảo vệ của toàn hệ thống để làm monitor chuyển sang trạng thái thành công.

### Đo từng đoạn có ý nghĩa

Tổng thời gian giao dịch có thể được tách thành mở trang, xác thực và đọc chi tiết. Nếu tổng thời gian tăng, phân đoạn giúp xác định phần cần điều tra trước.

OCI hỗ trợ custom marker trong script để ghi nhận thời lượng tùy chỉnh. Chỉ thêm marker cho các bước cần ra quyết định, với tên ổn định và không chứa dữ liệu cá nhân. [Custom markers trong script](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/create-script.html).

Một lần đo sau đăng nhập không tự động là thời gian xử lý riêng của máy chủ: nó có thể gồm chuyển hướng, tải tài nguyên, thực thi JavaScript và chờ điều kiện giao diện.

## 7. Chuẩn bị compartment, IAM và kết nối

Đối với lab, có thể dùng compartment riêng mang tên minh họa `LearnObservability`. Phân công người tạo APM domain, người sửa monitor và người chỉ xem kết quả.

Ví dụ hai policy cho nhóm chỉ đọc, khi sử dụng identity domain có tên `Default`:

~~~text
Allow group 'Default'/'OciObservers' to read apm-domains in compartment LearnObservability
Allow group 'Default'/'OciObservers' to read metrics in compartment LearnObservability
~~~

Phải thay tên domain, group và compartment bằng tài nguyên của tenancy. Hai policy này dành cho quan sát; việc tạo domain, sửa monitor, quản lý alarm hoặc sử dụng Notifications cần những quyền tương ứng. Oracle phân biệt quyền thao tác APM với quyền Monitoring và Notifications. [Điều kiện tiên quyết và policy APM](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/perform-oracle-cloud-infrastructure-prerequisite-tasks.html).

Danh tính dùng để quản trị OCI và tài khoản đăng nhập ứng dụng là hai lớp quyền riêng. Một người có quyền tạo monitor không vì vậy được cấp quyền xem mọi đơn hàng của ứng dụng.

Với endpoint riêng trong VCN, cần xác nhận lần lượt:

1. Tên miền của endpoint phân giải được từ môi trường chạy monitor.
2. Route đưa lưu lượng đến đúng mạng đích.
3. NSG, security list và firewall cho phép đúng luồng cần thiết.
4. Dịch vụ lắng nghe tại đúng cổng và dùng chứng chỉ phù hợp với hostname.
5. Điểm đo gửi được telemetry về các endpoint OCI cần thiết.

Giới hạn rule theo nguồn, đích và cổng cần dùng. Không công khai một ứng dụng nội bộ chỉ để Public Vantage Point truy cập được.

Cũng cần phân biệt hai đường lỗi: monitor không gọi được ứng dụng và điểm đo không gửi được kết quả. Trường hợp sau có thể chỉ tạo ra khoảng trống dữ liệu.

## 8. Thực hành tạo monitor trên OCI

### 8.1. Điều kiện bắt đầu

Chuẩn bị một ứng dụng lab có HTTPS, tài khoản kiểm thử, đơn hàng mẫu và người có quyền phù hợp trong OCI. Nếu cần điều tra xuyên tầng, chuẩn bị thêm instrumentation phía máy chủ và thu thập log ứng dụng.

Không cần triển khai Dedicated Vantage Point chỉ để thử một endpoint công khai. Chọn loại điểm đo theo đường truy cập cần quan sát và ngân sách của lab.

### 8.2. Tạo phép đo đơn giản trước

Trong OCI Console, mở **Observability & Management → Application Performance Monitoring → Availability Monitoring**. Chọn đúng compartment và APM domain.

Tạo một monitor REST cho endpoint đọc mẫu. Đặt tên mô tả môi trường và chức năng, chẳng hạn `lab-orders-read-api`; cấu hình URL, điều kiện phản hồi, lịch chạy và điểm đo. Các thao tác chọn monitor, domain và cấu hình được mô tả trong [Create a Monitor](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/create-monitor.html).

Sau khi có kết quả, xác nhận monitor đang kiểm tra đúng ứng dụng. Một URL bị chuyển hướng sang trang đăng nhập hoặc trang bảo trì có thể trả phản hồi hợp lệ về mặt HTTP nhưng sai mục tiêu nghiệp vụ.

### 8.3. Thêm giao dịch nhiều bước

1. Ghi hành trình đăng nhập và đọc đơn hàng mẫu bằng Selenium IDE.
2. Loại thao tác dư; bổ sung chờ điều kiện và xác nhận kết quả.
3. Xuất một script `.side`, tạo tài nguyên script trong APM.
4. Cấu hình tham số cho môi trường và dữ liệu kiểm thử; đánh dấu thông tin nhạy cảm là bí mật.
5. Tạo Scripted Browser monitor sử dụng script đó.
6. Thực hiện lượt chạy thử trước khi bật lịch định kỳ.
7. Kiểm tra kết quả tại từng điểm đo rồi mới cấu hình cảnh báo.

Khi thay phiên bản script, ghi nhận người sở hữu và mục đích thay đổi. Một lần sửa selector có thể ảnh hưởng cách diễn giải lịch sử, dù ứng dụng không thay đổi.

### 8.4. Thử lỗi có kiểm soát

Chỉ thực hiện trên ứng dụng lab và tài nguyên thuộc phạm vi kiểm thử:

| Thay đổi thử nghiệm | Tín hiệu kỳ vọng |
| --- | --- |
| Dùng mã đơn hàng mẫu không tồn tại | Assertion nghiệp vụ thất bại |
| Làm chậm endpoint chi tiết | Tăng thời gian giao dịch, có thể vượt ngưỡng |
| Đổi selector của trang lab | Script lỗi tại bước tìm phần tử |
| Ngắt đường mạng riêng của lab | Monitor nội bộ báo lỗi kết nối hoặc mất khả năng chạy |
| Khôi phục cấu hình | Có các lượt chạy thành công trở lại |

Mục tiêu là chứng minh phép đo nhận ra lỗi mà nó được giao phát hiện. Không kết luận cảnh báo hoạt động chỉ vì dashboard từng có một điểm đỏ.

## 9. Đọc metrics và thiết kế cảnh báo

Trong OCI Monitoring, các metrics synthetic thuộc namespace `oracle_apm_synthetics`; RUM dùng `oracle_apm_rum`. Một số trường hữu ích:

| Metric hoặc dimension | Ý nghĩa |
| --- | --- |
| `Availability` | Thành công 1, thất bại 0 |
| `MonitorExecutionTime` | Thời gian chạy monitor, tính bằng mili giây |
| `MonitorLoadTime` | Thời gian chạy không gồm các khoảng pause |
| `CustomMetric` | Giá trị từ custom marker |
| `MonitorId`, `VantagePoint` | Xác định monitor và điểm đo |

Đối chiếu tên, đơn vị và dimension trong [APM Metrics](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/application-performance-monitoring-metrics.html).

Ví dụ biểu thức MQL, sau khi chọn namespace synthetic và thay giá trị dimension bằng giá trị thực:

~~~text
Availability[5m]{MonitorId = "<monitor_ocid>", VantagePoint = "<vantage_point>"}.mean() < 1
~~~

Biểu thức này tìm cửa sổ có tỷ lệ thành công quan sát được dưới 100% cho luồng dữ liệu đã chọn. Nó không có nghĩa là “ba lần chạy liên tiếp thất bại”. Cần kiểm tra dữ liệu thực tế, khoảng tổng hợp và thời gian duy trì điều kiện của alarm trước khi sử dụng.

### Tách lỗi chức năng, lỗi chậm và thiếu dữ liệu

| Nhóm | Điều kiện thiết kế minh họa | Hành động |
| --- | --- | --- |
| Không hoàn thành giao dịch | Lỗi được xác nhận qua nhiều lượt hoặc điểm đo phù hợp | Điều tra khả dụng và kết quả nghiệp vụ |
| Chậm | Giao dịch thành công nhưng vượt mục tiêu trong một khoảng quan sát | Điều tra hiệu năng |
| Thiếu dữ liệu | Không có kết quả sau nhiều chu kỳ dự kiến | Kiểm tra lịch chạy, điểm đo và đường telemetry |

Một cửa sổ không có mẫu không thể được diễn giải thành 100% thành công hoặc 0% thành công. Hãy thiết kế cảnh báo thiếu dữ liệu riêng với độ trễ cho phép.

Với hai điểm đo, có thể tăng mức khẩn cấp khi cả hai cùng báo lỗi; một điểm lỗi vẫn cần được xem xét vì có thể phản ánh sự cố khu vực. Nếu cần phối hợp nhiều alarm để biểu diễn quy tắc này, phải cấu hình cơ chế tổng hợp rõ ràng, thay vì giả định một alarm tự hiểu toàn bộ ma trận điểm đo.

Khi retry thành công, vẫn nên giữ dấu vết lượt lỗi ban đầu để không che sự cố ngắn. Khi bảo trì, dùng kế hoạch giảm hoặc tạm ngưng thông báo có thời hạn, rồi xác nhận tự khôi phục giám sát.

### Tính tỷ lệ thành công có mẫu số rõ ràng

Với một monitor và một điểm đo:

~~~text
Tỷ lệ thành công quan sát được
  = số lượt chạy thành công / số lượt chạy có kết quả hợp lệ × 100%
~~~

Ví dụ, 286 trong 288 lượt có kết quả là thành công thì tỷ lệ quan sát được khoảng 99,31%. Con số này mô tả các mẫu đo; không tự động là tỷ lệ giao dịch thành công của toàn bộ khách hàng.

Luôn trình bày thêm số lượt theo lịch, số lượt có kết quả và số lượt thiếu. Nếu 100% thành công chỉ dựa trên 20 trong 288 lượt dự kiến, dữ liệu chưa đủ để đánh giá tính sẵn sàng cả ngày.

Với chu kỳ 5 phút, một lỗi xảy ra ngay sau lượt kiểm tra có thể chờ gần 5 phút mới được quan sát. Thời gian phát hiện còn gồm thời gian chạy, xuất dữ liệu, đánh giá alarm và gửi thông báo. Không dùng riêng chu kỳ chạy làm cam kết thời gian phát hiện.

## 10. Bổ sung Real User Monitoring

Synthetic cho một đường đi lặp lại được; RUM bổ sung quan sát từ môi trường thật của người sử dụng.

OCI APM Browser Agent thu thập browser span và dữ liệu RUM như tải trang, lỗi JavaScript và lời gọi AJAX. Có thể triển khai Browser Agent mà chưa có APM Java Agent; muốn phân tích đầy đủ phía máy chủ thì cần instrumentation tương ứng. [Cấu hình APM Browser Agent](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/configure-browser-agent-real-user-monitoring.html).

### 10.1. Cấu hình tối thiểu minh họa

Ví dụ sau minh họa cấu hình trong trang của ứng dụng lab. Thay `APM_UPLOAD_ENDPOINT` bằng endpoint HTTPS của APM domain, không thêm dấu gạch chéo cuối; thay `APM_PUBLIC_DATA_KEY` bằng **public data key** được cấp cho thu thập từ trình duyệt.

~~~html
<script>
  window.apmrum = window.apmrum || {};
  window.apmrum.serviceName = "orders-web-lab";
  window.apmrum.webApplication = "Orders-Lab";
  window.apmrum.ociDataUploadEndpoint = "APM_UPLOAD_ENDPOINT";
  window.apmrum.OracleAPMPublicDataKey = "APM_PUBLIC_DATA_KEY";
</script>
<script
  async
  crossorigin="anonymous"
  src="APM_UPLOAD_ENDPOINT/static/jslib/apmrum.min.js">
</script>
~~~

Áp dụng vị trí chèn và cách tích hợp theo cấu trúc ứng dụng trong [Deploy the APM Browser Agent](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/deploy-browser-agent-your-application.html). Không đưa private data key, OCI API signing key hoặc mật khẩu ứng dụng vào mã trình duyệt.

Sau khi triển khai, mở trang lab và kiểm tra thư viện được tải, yêu cầu telemetry không bị chặn và dữ liệu xuất hiện đúng ứng dụng trong APM. Với Content Security Policy, proxy hoặc cơ chế quản lý đồng ý, kiểm tra các cấu hình liên quan thay vì chỉ nhìn thấy thẻ script trong HTML.

### 10.2. Đọc dữ liệu theo nhóm có ý nghĩa

Bắt đầu từ một vài câu hỏi vận hành:

- Người dùng có gặp lỗi ở đúng trang mà synthetic đang kiểm tra không?
- Sự chậm chỉ xuất hiện với một trình duyệt, nhóm mạng hoặc phiên bản giao diện nào?
- Trang chậm vì chờ phản hồi hay vì xử lý và hiển thị ở trình duyệt?
- Lỗi xảy ra trước hay sau đợt triển khai gần nhất?

Khi truy vấn metrics RUM trong OCI Monitoring, tài liệu Oracle yêu cầu chọn `MetricGroupName = "No Group"` và `WebApplicationName` là ứng dụng cần xem hoặc `All Web Applications`. [Yêu cầu dimension khi truy vấn RUM](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/application-performance-monitoring-metrics.html).

Không mặc định rằng dữ liệu RUM đã bao phủ mọi khách hàng. Trình chặn nội dung, thiết bị mất mạng hoặc trang chưa tải tới agent có thể tạo vùng thiếu quan sát. Cần đối chiếu với số yêu cầu máy chủ hoặc dữ liệu nghiệp vụ phù hợp để hiểu độ bao phủ.

Một hệ thống có synthetic thành công nhưng RUM xấu có thể đang gặp vấn đề phụ thuộc thiết bị, kết nối thực hoặc hành trình khác kịch bản mẫu. Ngược lại, synthetic lỗi lúc ít người truy cập vẫn là tín hiệu hữu ích về khả năng phục vụ, dù RUM chưa có đủ mẫu để xác nhận tác động.

Nếu lưu lượng synthetic cũng được Browser Agent quan sát, cần có cách nhận diện dữ liệu kiểm thử khi phân tích trải nghiệm khách hàng. Cách gắn nhãn hoặc lọc phải được kiểm chứng trong ứng dụng; không mặc định mọi lượt synthetic đều tự động bị loại khỏi RUM.

### 10.3. Kiểm soát dữ liệu được thu thập

URL, nội dung hiển thị, ảnh chụp lỗi và dữ liệu chẩn đoán có thể chứa thông tin nhạy cảm. Tránh đưa token hoặc dữ liệu cá nhân vào URL ngay từ thiết kế ứng dụng.

Oracle nêu rõ các quy tắc ẩn PII mặc định không bao phủ mọi trường hợp. Cần kiểm tra quy tắc theo dữ liệu của ứng dụng; cấu hình theo dõi phiên và cơ chế đồng ý cũng phải phù hợp với cách ứng dụng vận hành. [Ẩn thông tin nhận dạng cá nhân trong RUM](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/hide-personally-identifiable-information-pii.html).

Với monitor, ưu tiên dữ liệu mẫu và hạn chế quyền xem kết quả chẩn đoán. Tham số được đánh dấu bí mật không đảm bảo giá trị đó sẽ không xuất hiện ở một màn hình, URL hoặc dòng log do chính ứng dụng tạo ra.

## 11. Từ giao dịch lỗi đến nguyên nhân

Một kết quả synthetic thất bại là điểm bắt đầu điều tra, chưa phải kết luận về thành phần gây lỗi.

Quy trình có thể áp dụng:

1. **Xác định phạm vi:** monitor nào, điểm đo nào, môi trường nào và bước nào thất bại.
2. **Cố định thời gian:** ghi thời điểm UTC, khoảng quan sát và phiên bản triển khai; tránh ghép log theo giờ địa phương chưa quy đổi.
3. **Xem bằng chứng lượt chạy:** thông báo lỗi và các dữ liệu chẩn đoán sẵn có cho loại monitor.
4. **Đối chiếu RUM:** tìm cùng trang hoặc nhóm giao dịch trong khoảng thời gian đó.
5. **Theo trace:** nếu đã instrument và có dữ liệu tương quan, xác định span chậm hoặc lỗi.
6. **Đọc log liên quan:** dùng trace ID, request ID hoặc định danh kiểm thử an toàn để tìm chi tiết xử lý.
7. **Kiểm tra phục hồi:** chạy lại đúng giao dịch và quan sát thêm các chu kỳ sau khi sửa.

APM hỗ trợ việc tương quan kết quả Availability Monitoring với trace được thu thập, nhưng mức quan sát phụ thuộc các nguồn dữ liệu đã cấu hình. [Khả năng của OCI APM](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/application-performance-monitoring.html).

Không tự động có trace xuyên suốt chỉ vì Browser Agent và monitor cùng tồn tại. Cần kiểm tra instrumentation phía máy chủ, truyền ngữ cảnh qua các chặng, cấu hình trình duyệt và chính sách lấy mẫu. Khi không có liên kết trực tiếp, hãy ghi rõ việc đối chiếu mới dựa trên thời gian và request ID.

### Một tình huống phân tích

Giả sử monitor “đăng nhập và xem đơn hàng” tăng từ 3 giây lên 16 giây sau triển khai. Các quan sát gồm:

| Quan sát | Hướng điều tra hợp lý |
| --- | --- |
| Cả điểm đo công khai và nội bộ đều chậm ở bước chi tiết | Ưu tiên phần xử lý chung của ứng dụng |
| REST đọc chi tiết cũng chậm | Tập trung vào API và các phụ thuộc của API |
| Trace cho thấy chờ lấy kết nối cơ sở dữ liệu | Kiểm tra connection pool và đường truy cập cơ sở dữ liệu |
| Log ghi timeout lấy kết nối, CPU Compute còn thấp | Xem giới hạn pool, kết nối bị giữ lâu hoặc phụ thuộc bị nghẽn |

Đây là suy luận từ bằng chứng giả định của tình huống, không phải quy tắc kết luận tự động. Cơ sở dữ liệu có thể chậm, nhưng cũng có thể ứng dụng giữ kết nối quá lâu hoặc thay cấu hình pool sai. Cần kiểm tra phần chờ và dữ liệu liên quan trước khi tăng tài nguyên.

Nếu API ổn nhưng Scripted Browser lỗi ngay sau khi giao diện đổi, kiểm tra assertion và selector. Nếu selector cũ không còn hợp lệ còn chức năng thực vẫn đúng, sửa script theo hợp đồng giao diện mới; giữ lại bản ghi thay đổi để giải thích chuỗi số liệu.

## 12. Lịch chạy, tính sẵn sàng và chi phí

### Ước lượng số lượt chạy

Giả sử mỗi monitor chạy tại **mọi điểm đo trong mỗi chu kỳ**, không retry và không có khoảng tạm dừng:

~~~text
Lượt chạy/ngày
  = số monitor × số điểm đo mỗi monitor × 1.440 / chu kỳ tính bằng phút
~~~

Ví dụ, 4 monitor, mỗi monitor dùng 2 điểm đo, chu kỳ 5 phút:

~~~text
4 × 2 × 1.440 / 5 = 2.304 lượt chạy/ngày
~~~

Đây là phép ước lượng theo giả định lịch chạy trên, không phải công thức tính tiền của OCI. Khi có retry, lịch riêng hoặc cơ chế phân bổ lượt chạy khác, phải tính theo cấu hình và số liệu sử dụng thực tế.

Tổng chi phí quan sát còn có thể gồm dữ liệu APM, hạ tầng điểm đo riêng, log và dữ liệu chẩn đoán. Dedicated Vantage Point được triển khai trên hạ tầng trong tenancy nên cần kiểm kê tài nguyên và vòng đời của stack. [Kiến trúc triển khai Dedicated Vantage Point](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/use-dedicated-vantage-points.html).

Bắt đầu bằng các giao dịch quan trọng nhất. Chạy API đơn giản thường xuyên hơn và hành trình trình duyệt dài ở tần suất phù hợp với mục tiêu phát hiện. Không giảm chi phí bằng cách bỏ assertion làm monitor mất khả năng phát hiện lỗi.

### Quan sát chính hệ thống giám sát

Nếu monitor phụ thuộc hoàn toàn vào cùng miền lỗi với ứng dụng, một sự cố có thể đồng thời làm ứng dụng hỏng và làm phép đo biến mất.

Nên có góc nhìn đủ độc lập, cảnh báo thiếu kết quả và đường nhận thông báo đã được xác nhận. Nhiều điểm đo đặt cạnh nhau chưa chắc mang lại độ độc lập cần thiết; cần xem chúng có chung DNS, đường mạng, danh tính hoặc hạ tầng phụ thuộc hay không.

Tài khoản hết hạn, bí mật chưa xoay vòng, dữ liệu mẫu bị xóa và script không còn phù hợp giao diện đều có thể làm giám sát suy giảm. Đưa các mục này vào trách nhiệm vận hành định kỳ.

### Tự động hóa có kiểm soát

Khi quản lý bằng công cụ hạ tầng dưới dạng mã, nên lưu cấu hình monitor, lịch chạy, điểm đo, chủ sở hữu và ngưỡng cảnh báo theo phiên bản. Bí mật cần được tham chiếu bằng cơ chế phù hợp, không đưa trực tiếp vào kho mã.

Một thay đổi monitor cần có cách so sánh với cấu hình đang chạy, lượt kiểm tra sau triển khai và phương án khôi phục. Thay đổi lịch hoặc thêm điểm đo phải cập nhật luôn ước lượng số lượt chạy.

## 13. Những dấu hiệu dễ diễn giải sai

| Dấu hiệu | Điều chưa thể kết luận | Việc nên làm tiếp |
| --- | --- | --- |
| HTTP 200 | Giao dịch nghiệp vụ đã đúng | Kiểm tra nội dung và kết quả cuối |
| Trang đăng nhập tải được | Người dùng đăng nhập thành công | Thực hiện bước xác thực và kiểm tra phiên |
| Điểm đo nội bộ thành công | Đường truy cập Internet hoạt động tốt | Đối chiếu phép đo công khai |
| Không có dữ liệu | Dịch vụ hoàn toàn ổn hoặc đã hỏng | Kiểm tra lịch và đường telemetry |
| Một lượt lỗi rồi retry thành công | Không có sự cố nào xảy ra | Giữ dấu vết lỗi và xem mức lặp lại |
| Trung bình thời gian còn thấp | Mọi người dùng đều có trải nghiệm tốt | Xem phân bố, nhóm người dùng và số mẫu |
| Không có trace phù hợp | Yêu cầu chưa từng tới hệ thống | Kiểm tra instrumentation, lấy mẫu và độ trễ dữ liệu |
| CPU thấp | Không có nghẽn phía máy chủ | Kiểm tra I/O, khóa, pool và phụ thuộc |
| Monitor thành công sau khi bỏ xác minh TLS | Lỗi chứng chỉ đã được xử lý | Khôi phục xác minh và sửa chuỗi tin cậy phù hợp |

## 14. Bài thực hành và kết quả cần lưu lại

Trên ứng dụng lab, triển khai một REST monitor và một Scripted Browser monitor cho cùng chức năng đọc đơn hàng mẫu. Nếu ứng dụng có thể tích hợp Browser Agent, thêm RUM để quan sát một phiên sử dụng thủ công.

Sản phẩm thực hành gồm:

- Hợp đồng giao dịch: đầu vào, checkpoint, điều kiện đúng, timeout và ngưỡng chất lượng.
- Sơ đồ đường truy cập từ từng điểm đo và phạm vi IAM cần thiết.
- Kết quả chạy thành công, kết quả lỗi có kiểm soát và bằng chứng phục hồi.
- Dashboard hoặc truy vấn cho khả dụng, thời gian giao dịch và dữ liệu thiếu.
- Một mô tả điều tra có mốc thời gian, bằng chứng và giới hạn kết luận.
- Ước lượng lượt chạy mỗi ngày, chủ sở hữu và hướng xử lý khi monitor báo lỗi.

Bài thực hành đạt mục tiêu khi người học giải thích được monitor chứng minh điều gì, còn bỏ sót điều gì, và phải mở dữ liệu nào tiếp theo khi nó thất bại.

Sau lab, tạm dừng hoặc xóa những monitor không còn dùng, thu hồi tài khoản kiểm thử và xử lý dữ liệu mẫu theo kế hoạch. Nếu có triển khai hạ tầng điểm đo riêng, kiểm tra các tài nguyên thuộc stack và các phụ thuộc trước khi kết thúc lab.
