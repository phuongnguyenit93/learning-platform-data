# Quy trình lựa chọn nền tảng compute theo yêu cầu workload

## 1. Vì sao cần lựa chọn nền tảng compute có quy trình?

Một workload chạy trên đám mây có thể được triển khai bằng máy ảo (virtual machine – VM), container, nền tảng container được quản lý hoặc dịch vụ serverless. Mỗi mô hình cung cấp một mức độ kiểm soát, trách nhiệm vận hành và cách tính chi phí khác nhau. Chọn mô hình chỉ dựa trên mức độ phổ biến của công nghệ thường dẫn đến một trong hai tình huống: hệ thống bị thiếu khả năng kiểm soát cần thiết, hoặc đội ngũ phải vận hành nhiều thành phần hơn mức workload thực sự yêu cầu.

Quyết định compute cần bắt đầu từ đặc điểm của workload và yêu cầu kinh doanh. Một dịch vụ xử lý giao dịch liên tục có thể cần năng lực ổn định, độ trễ thấp và khả năng phục hồi rõ ràng. Một tác vụ xử lý ảnh chỉ chạy khi có sự kiện lại phù hợp với mô hình thực thi theo yêu cầu. Một ứng dụng cũ phụ thuộc vào hệ điều hành hoặc cấu hình phần mềm đặc thù có thể cần VM trong giai đoạn đầu. Không có một mô hình duy nhất phù hợp cho mọi trường hợp.

Trong phạm vi **nền tảng cloud compute**, quy trình lựa chọn cần xem xét đồng thời mô hình thực thi, CPU, bộ nhớ, mạng, bảo mật, khả năng triển khai, mở rộng, tính sẵn sàng và chi phí vận hành. Kết quả cuối cùng không chỉ là tên một dịch vụ cloud; đó là một quyết định kiến trúc có lý do, giả định, giới hạn và cách kiểm chứng.

Sau bài học, người học có thể:

- Thu thập yêu cầu kỹ thuật và kinh doanh của một workload trước khi chọn compute.
- So sánh VM, container và serverless theo mức độ kiểm soát, khả năng mở rộng, vận hành và chi phí.
- Ước lượng nhu cầu CPU, bộ nhớ và mạng dựa trên tải thực tế.
- Đưa ra lựa chọn có xét đến bảo mật, triển khai, tính sẵn sàng và khả năng phục hồi.
- Kiểm chứng lựa chọn bằng thử nghiệm tải, đo lường và đánh giá chi phí.

## 2. Bắt đầu từ hồ sơ workload

Trước khi so sánh dịch vụ, hãy mô tả workload. Một hồ sơ ngắn nhưng có số liệu sẽ hữu ích hơn một danh sách công nghệ mong muốn.

### 2.1. Xác định vai trò và mức độ quan trọng

Làm rõ workload phục vụ chức năng nào: API giao dịch, website, xử lý nền, phân tích dữ liệu, tác vụ định kỳ hay một thành phần của hệ thống cũ. Xác định mức độ ảnh hưởng nếu dịch vụ chậm hoặc ngừng hoạt động. Những thông tin như mục tiêu thời gian hoạt động, thời gian khôi phục (RTO), điểm khôi phục dữ liệu (RPO) và thời gian phản hồi mong muốn sẽ ảnh hưởng trực tiếp đến thiết kế compute.

Ví dụ, một tác vụ tạo báo cáo nội bộ có thể chấp nhận chạy lại khi thất bại. Một dịch vụ xác nhận thanh toán cần kiểm soát chặt chẽ hơn về độ trễ, tính sẵn sàng, xử lý trùng lặp và khả năng phục hồi. Hai workload có mức CPU tương tự vẫn có thể cần nền tảng khác nhau vì yêu cầu vận hành khác nhau.

### 2.2. Mô tả hình dạng tải

Ghi nhận tải trung bình, tải đỉnh, thời gian duy trì đỉnh và mức biến động theo giờ hoặc theo mùa. Phân biệt các dạng tải sau:

| Hình dạng tải | Đặc điểm | Tác động đến lựa chọn |
|---|---|---|
| Ổn định, chạy liên tục | Nhu cầu tương đối đều trong thời gian dài | VM hoặc container chạy liên tục có thể dễ dự toán; cần so sánh mức sử dụng thực tế với công suất cấp phát |
| Theo chu kỳ | Tăng giảm theo giờ, ngày hoặc lịch xử lý | Cần khả năng tăng giảm số instance và lịch tự động điều chỉnh công suất |
| Đột biến | Có các đợt tăng tải nhanh, khó dự báo | Cần kiểm tra tốc độ scale-out, giới hạn quota, hàng đợi và khả năng chịu tải khi scale chưa kịp |
| Theo sự kiện | Chỉ phát sinh khi có thông điệp, tệp hoặc sự kiện | Function hoặc serverless container có thể giảm công suất nhàn rỗi và đơn giản hóa vận hành |
| Theo lô (batch) | Xử lý một lượng công việc hữu hạn rồi kết thúc | Có thể dùng worker container, VM theo phiên hoặc dịch vụ batch; cần tính thời gian hoàn tất và khả năng chạy lại |

Không nên chỉ dùng số request mỗi giây để mô tả tải. Hãy ghi thêm kích thước request, thời gian xử lý, số tác vụ đồng thời, tỷ lệ lỗi, số kết nối mở và lượng dữ liệu đọc ghi. Một API nhận ít request nhưng mỗi request xử lý dữ liệu lớn có thể tiêu thụ nhiều bộ nhớ và I/O hơn một API có lưu lượng cao nhưng xử lý nhẹ.

### 2.3. Xác định đặc điểm thực thi

Trả lời các câu hỏi sau:

- Ứng dụng có chạy liên tục hay chỉ chạy khi được kích hoạt?
- Tiến trình có cần duy trì trạng thái trong bộ nhớ giữa các lần gọi không?
- Thời gian xử lý một tác vụ có thể kéo dài bao lâu? Có giới hạn thời gian thực thi cần lưu ý không?
- Ứng dụng có yêu cầu hệ điều hành, thư viện native, kiến trúc CPU, quyền truy cập kernel hoặc thiết bị đặc thù không?
- Ứng dụng có thể đóng gói thành image container và chạy nhất quán ở nhiều môi trường không?
- Có thể chia workload thành các đơn vị độc lập để mở rộng riêng hay phải mở rộng toàn bộ ứng dụng?

Trạng thái nghiệp vụ lâu dài nên được lưu trong cơ sở dữ liệu, object storage hoặc hệ thống lưu trữ phù hợp. Việc giữ trạng thái trong bộ nhớ của một instance khiến việc thay thế, mở rộng hoặc khởi động lại instance phức tạp hơn. Tuy vậy, một số workload vẫn cần bộ nhớ cục bộ hoặc phiên chạy dài; cần ghi rõ lý do và cách xử lý khi instance bị thay thế.

### 2.4. Xác định phụ thuộc và ràng buộc

Liệt kê cơ sở dữ liệu, message broker, hệ thống tệp, dịch vụ bên ngoài, thư viện, giao thức và vị trí dữ liệu mà workload cần truy cập. Ghi nhận yêu cầu về kết nối riêng, độ trễ mạng, băng thông, địa chỉ IP cố định, vùng triển khai, chủ quyền dữ liệu và khả năng di chuyển giữa các môi trường.

Ràng buộc cũng có thể đến từ đội ngũ: kỹ năng vận hành Kubernetes, khả năng trực ca, quy trình vá hệ điều hành, công cụ quan sát, quy trình phê duyệt thay đổi và ngân sách. Một nền tảng nhiều tính năng nhưng vượt quá năng lực vận hành hiện có có thể làm tăng rủi ro thực tế.

## 3. Hiểu các mô hình compute trước khi so sánh

### 3.1. Máy ảo (VM)

VM cung cấp một môi trường máy tính ảo hóa với hệ điều hành riêng. Người vận hành thường có quyền kiểm soát cao đối với hệ điều hành, gói phần mềm, cấu hình runtime, dung lượng đĩa và một số thiết lập mạng. VM phù hợp khi workload cần môi trường hệ điều hành cụ thể, phần mềm cũ, tiến trình chạy lâu dài hoặc cấu hình đặc thù khó chuyển đổi.

Ưu điểm chính của VM là ranh giới vận hành quen thuộc và mức độ kiểm soát rộng. Có thể lựa chọn họ máy, số CPU ảo, bộ nhớ, loại lưu trữ và cấu hình mạng theo đặc điểm ứng dụng. VM cũng hữu ích khi cần chuyển một ứng dụng hiện hữu lên cloud với thay đổi mã nguồn tối thiểu.

Đổi lại, đội ngũ phải chịu trách nhiệm nhiều hơn cho hệ điều hành khách: cập nhật bảo mật, cấu hình, hardening, giám sát, quản lý dung lượng đĩa, khởi động dịch vụ và xử lý lỗi. VM chạy liên tục có thể phát sinh chi phí ngay cả khi CPU ít được sử dụng. Nếu cần mở rộng, hệ thống phải có cơ chế tạo thêm VM, phân phối tải, khởi tạo cấu hình và loại bỏ instance dư thừa.

**Nên cân nhắc VM khi:** ứng dụng phụ thuộc mạnh vào hệ điều hành; cần quyền kiểm soát cấp máy; có phần mềm thương mại hoặc phần mềm cũ khó đóng gói; workload chạy liên tục và đã có quy trình quản trị máy chủ; hoặc cần một bước chuyển đổi ít thay đổi trước khi hiện đại hóa.

### 3.2. Container

Container đóng gói ứng dụng cùng các phụ thuộc cần thiết thành image để triển khai nhất quán. Container thường chia sẻ kernel của máy chủ hoặc môi trường chạy container, vì vậy không tương đương với một VM có hệ điều hành riêng. Image giúp chuẩn hóa quá trình build, kiểm thử và triển khai, đồng thời hỗ trợ tách ứng dụng thành các dịch vụ có thể phát hành và mở rộng độc lập.

Container có thể chạy trực tiếp trên một máy chủ, trên nền tảng điều phối như Kubernetes hoặc trên dịch vụ container được quản lý. Mức độ vận hành khác nhau đáng kể giữa các lựa chọn này. Khi tự quản lý cụm Kubernetes, đội ngũ còn phải hiểu và vận hành node, control plane (nếu không được quản lý), networking, storage, ingress, policy, nâng cấp và giám sát. Dịch vụ container được quản lý giảm một phần công việc hạ tầng, nhưng ứng dụng vẫn cần được thiết kế, bảo mật và quan sát đúng cách.

Container phù hợp với API, worker, microservice và ứng dụng cần môi trường triển khai nhất quán. Chúng cũng có thể chạy tác vụ nền hoặc batch. Để tận dụng lợi ích, ứng dụng nên hỗ trợ cấu hình qua môi trường hoặc cơ chế quản lý cấu hình, ghi log ra đầu ra chuẩn, xử lý tín hiệu dừng, kiểm tra trạng thái sẵn sàng và lưu trạng thái lâu dài bên ngoài container.

Rủi ro thường gặp gồm image quá lớn, image chứa bí mật, chạy container với quyền cao, dùng tag không cố định, không giới hạn CPU/bộ nhớ, hoặc không có quy trình cập nhật image nền. Việc dùng container không tự động làm ứng dụng an toàn hay có khả năng mở rộng.

**Nên cân nhắc container khi:** cần đóng gói và phát hành nhất quán; có nhiều dịch vụ hoặc worker độc lập; muốn kiểm soát runtime ở cấp ứng dụng; cần khả năng di chuyển giữa các môi trường; và đội ngũ có nền tảng vận hành container hoặc chọn được dịch vụ quản lý phù hợp.

### 3.3. Serverless

Serverless là mô hình trong đó nhà cung cấp cloud quản lý phần lớn hạ tầng thực thi. Người phát triển tập trung vào mã xử lý, cấu hình và sự kiện kích hoạt. Với function-as-a-service (FaaS), một hàm thường được gọi bởi HTTP request, lịch, thông điệp, sự kiện lưu trữ hoặc sự kiện từ dịch vụ khác. Nền tảng tự cấp phát môi trường thực thi và có thể tăng giảm số lần thực thi theo nhu cầu.

Mô hình này phù hợp với xử lý sự kiện, tích hợp giữa dịch vụ, tác vụ tự động hóa và các API nhỏ có tải biến động. Một số nền tảng cũng cung cấp serverless container để chạy image container mà không cần quản lý máy chủ hoặc cụm điều phối. Serverless container hữu ích khi cần môi trường container hoặc tiến trình dài hơn function truyền thống, tùy giới hạn của dịch vụ cụ thể.

Serverless giảm việc quản trị máy chủ và có thể giảm chi phí khi workload không chạy liên tục. Tuy nhiên, cần đánh giá giới hạn thời gian thực thi, bộ nhớ, CPU, kích thước gói triển khai, số lần gọi đồng thời, tốc độ khởi tạo, cold start, giới hạn kết nối và quota. Chi phí có thể tăng nhanh nếu lưu lượng lớn hoặc hàm gọi dịch vụ khác nhiều lần. Một hàm được gọi thường xuyên với thời gian chạy dài không mặc nhiên rẻ hơn container hoặc VM.

Workload serverless nên ưu tiên xử lý không trạng thái, có thể chạy lại an toàn và có cơ chế chống xử lý trùng lặp khi nguồn sự kiện có thể gửi lại. Nếu cần xử lý lâu, điều phối nhiều bước hoặc kiểm soát tiến trình phức tạp, hãy cân nhắc workflow orchestration, worker container hoặc dịch vụ batch.

**Nên cân nhắc serverless khi:** workload được kích hoạt bởi sự kiện; thời gian chạy nằm trong giới hạn dịch vụ; tải biến động hoặc không thường xuyên; có thể thiết kế stateless; và lợi ích giảm vận hành lớn hơn các giới hạn về runtime, khả năng quan sát hoặc chi phí theo lượt gọi.

### 3.4. So sánh nhanh

| Tiêu chí | VM | Container | Serverless |
|---|---|---|---|
| Mức kiểm soát hệ điều hành | Cao | Phụ thuộc nền tảng; thường không quản lý kernel riêng cho từng container | Thấp; nền tảng quản lý môi trường thực thi |
| Đóng gói ứng dụng | Theo máy và cấu hình hệ điều hành | Image chứa ứng dụng và phụ thuộc | Mã/hàm hoặc image theo loại dịch vụ |
| Công việc vận hành | Quản trị OS, vá lỗi, cấu hình và mở rộng máy | Quản lý image, runtime và có thể cả cụm điều phối | Tập trung vào mã, quyền truy cập, trigger và giới hạn dịch vụ |
| Mở rộng | Thường theo VM hoặc nhóm VM | Theo container, pod hoặc service | Thường tự động theo request/sự kiện và quota |
| Tải phù hợp | Liên tục, đặc thù hệ điều hành, ứng dụng cũ | Dịch vụ chạy lâu, API, worker, microservice | Sự kiện, tác vụ ngắn hoặc workload không liên tục |
| Điểm cần kiểm tra | Sử dụng tài nguyên thấp, vá lỗi và thời gian khởi tạo | Độ phức tạp điều phối, giới hạn tài nguyên và bảo mật image | Cold start, timeout, concurrency, quota và chi phí theo lần thực thi |

Các nhóm trên không loại trừ nhau. Một hệ thống có thể dùng VM cho thành phần cũ, container cho API và serverless cho xử lý sự kiện. Lựa chọn theo từng workload hoặc từng thành phần thường hợp lý hơn ép toàn bộ hệ thống vào một mô hình.

## 4. Quy trình lựa chọn nền tảng compute

### Bước 1: Chuyển yêu cầu thành tiêu chí có thể kiểm chứng

Từ hồ sơ workload, chọn các tiêu chí bắt buộc và tiêu chí ưu tiên. Ví dụ:

- Runtime phải hỗ trợ hệ điều hành hoặc thư viện hiện tại.
- Độ trễ p95 hoặc p99 phải nằm trong ngưỡng nghiệp vụ.
- Dịch vụ phải phục hồi trong thời gian mục tiêu khi một instance hoặc một vùng khả dụng gặp lỗi.
- Tải đỉnh phải được xử lý mà không vượt giới hạn CPU, bộ nhớ, kết nối hoặc quota.
- Dữ liệu nhạy cảm phải ở mạng riêng và chỉ được truy cập bởi danh tính workload được cấp quyền.
- Đội ngũ phải triển khai, quan sát, cập nhật và khôi phục được bằng quy trình hiện có.

Phân biệt yêu cầu bắt buộc với mong muốn. Nếu một lựa chọn vi phạm yêu cầu bắt buộc, loại nó khỏi danh sách trước khi chấm điểm. Không nên để một điểm số tổng hợp che khuất một điều kiện bảo mật hoặc tính sẵn sàng không thể thỏa hiệp.

### Bước 2: Lập danh sách mô hình ứng viên

Tạo danh sách ngắn gồm VM, container được quản lý, nền tảng điều phối container và serverless phù hợp với hồ sơ. Không cần đưa mọi dịch vụ của mọi nhà cung cấp vào vòng đầu. Hãy loại sớm những lựa chọn không hỗ trợ runtime, thời gian thực thi, vị trí dữ liệu hoặc giao thức bắt buộc.

Một cách sàng lọc ban đầu:

```text
Workload cần quyền kiểm soát OS, kernel hoặc phần mềm đặc thù?
  Có  -> Đánh giá VM trước.
  Không -> Ứng dụng có thể đóng gói thành container?
            Có  -> Đánh giá dịch vụ container được quản lý.
            Không -> Xem xét khả năng điều chỉnh ứng dụng hoặc VM.

Workload được kích hoạt theo sự kiện, không trạng thái và nằm trong giới hạn runtime?
  Có  -> Đánh giá function/serverless.
  Không -> Ưu tiên VM hoặc container chạy liên tục/worker theo lô.

Đội ngũ có thực sự cần và có khả năng vận hành cụm điều phối?
  Có  -> Có thể đánh giá Kubernetes hoặc nền tảng tương đương.
  Không -> Ưu tiên mức quản lý cao hơn nếu đáp ứng yêu cầu.
```

Sơ đồ này giúp tạo danh sách ứng viên, không thay thế việc xác minh giới hạn dịch vụ và thử nghiệm workload.

### Bước 3: Đánh giá CPU và bộ nhớ

CPU và bộ nhớ cần được chọn theo hành vi ứng dụng, không chỉ theo cấu hình mặc định hoặc cấu hình của môi trường cũ.

**Với CPU:** xác định workload thiên về tính toán, xử lý tuần tự hay xử lý đồng thời. Đo mức sử dụng CPU, thời gian chờ, thời gian xử lý và độ trễ khi tăng số request đồng thời. Một workload CPU-bound thường cải thiện khi tăng năng lực CPU hoặc tối ưu thuật toán. Một workload bị giới hạn bởi I/O có thể không cải thiện đáng kể khi tăng CPU.

**Với bộ nhớ:** đo mức sử dụng thực tế trong tải bình thường và tải đỉnh, bao gồm heap, cache, buffer và mức tăng trong thời gian chạy dài. Thiếu bộ nhớ có thể gây lỗi cấp phát, garbage collection kéo dài hoặc bị nền tảng chấm dứt tiến trình. Cấp quá nhiều bộ nhớ làm tăng chi phí và có thể che giấu rò rỉ bộ nhớ.

Khi đánh giá, hãy xem xét:

- Mức tiêu thụ ở tải trung bình và đỉnh, không chỉ một thời điểm đo.
- Số instance tối thiểu cần giữ để đáp ứng độ trễ và tính sẵn sàng.
- Giới hạn CPU/bộ nhớ của VM, container hoặc function.
- Cách nền tảng phân bổ CPU khi instance nhàn rỗi hoặc khi nhiều workload dùng chung node.
- Dung lượng dự phòng cho tăng trưởng, rolling deployment và tình huống một instance bị mất.
- Tương quan giữa tăng concurrency với mức tiêu thụ CPU, bộ nhớ và kết nối.

Không áp dụng một tỷ lệ dự phòng cố định cho mọi ứng dụng. Hãy dùng tải thử và dữ liệu production để xác định headroom phù hợp với độ biến động và mục tiêu dịch vụ.

### Bước 4: Thiết kế mạng cho đường đi của request và dữ liệu

Mạng ảnh hưởng đến độ trễ, bảo mật, tính sẵn sàng và chi phí. Vẽ đường đi từ người dùng hoặc nguồn sự kiện đến compute, rồi đến cơ sở dữ liệu, storage và dịch vụ phụ thuộc.

Các điểm cần kiểm tra gồm:

1. **Ingress:** dịch vụ có nhận lưu lượng từ Internet, mạng doanh nghiệp hay chỉ từ dịch vụ nội bộ? Có cần load balancer, API gateway, WAF hoặc cơ chế xác thực ở lớp biên không?
2. **Phân đoạn mạng:** workload đặt trong subnet công khai hay riêng? Thành phần nào cần địa chỉ công khai? Có thể giới hạn truy cập theo security group, firewall hoặc network policy không?
3. **Egress:** compute gọi dịch vụ bên ngoài qua đường nào? Có cần NAT, proxy, private endpoint hoặc allowlist IP? Lưu lượng đi ra có phát sinh chi phí đáng kể không?
4. **Kết nối nội bộ:** dịch vụ có nằm gần cơ sở dữ liệu hoặc storage theo vùng triển khai không? Có cần mã hóa kết nối, DNS nội bộ, service discovery hoặc kiểm soát east-west traffic không?
5. **Khả năng chịu lỗi:** đường mạng, load balancer và các phụ thuộc có sẵn ở nhiều vùng khả dụng không? Có điểm lỗi đơn nào khiến nhiều instance cùng mất kết nối không?

Đặt compute gần dữ liệu thường giúp giảm độ trễ và lưu lượng truyền liên vùng. Tuy nhiên, vị trí triển khai phải đồng thời đáp ứng yêu cầu chủ quyền dữ liệu, khả năng phục hồi và chính sách bảo mật. Không nên mở cổng quản trị hoặc SSH/RDP ra Internet chỉ để đơn giản hóa thao tác vận hành; hãy dùng cơ chế truy cập quản trị được kiểm soát và ghi nhật ký.

### Bước 5: Đánh giá bảo mật và ranh giới trách nhiệm

Mỗi mô hình compute chuyển giao một phần công việc hạ tầng cho nhà cung cấp, nhưng trách nhiệm bảo mật của người dùng vẫn còn. Cần xác định rõ ai chịu trách nhiệm cho hệ điều hành, image nền, runtime, mã ứng dụng, danh tính, dữ liệu và cấu hình mạng.

| Lớp kiểm soát | VM | Container | Serverless |
|---|---|---|---|
| Hệ điều hành và bản vá | Đội ngũ thường quản lý OS khách và bản vá | Nhà cung cấp quản lý host; đội ngũ quản lý image/runtime ứng dụng theo nền tảng | Nhà cung cấp quản lý phần lớn OS và runtime nền; đội ngũ cập nhật mã và thư viện |
| Danh tính workload | Gán role/service identity cho VM và ứng dụng | Cấp danh tính cho service/pod; tránh nhúng khóa trong image | Cấp role tối thiểu cho function hoặc service |
| Mạng | Firewall, subnet, security group và cấu hình máy | Thêm network policy, ingress và quyền giữa service | Cấu hình quyền gọi dịch vụ, ingress, egress và endpoint |
| Bí mật | Dùng secret manager; hạn chế file cấu hình và biến môi trường không an toàn | Inject secret khi chạy; không đóng gói secret trong image | Lấy secret từ secret manager theo danh tính workload |
| Giám sát và kiểm toán | Log hệ điều hành, ứng dụng và hoạt động quản trị | Log ứng dụng, runtime, điều phối và thay đổi cấu hình | Log invocation, lỗi, quyền truy cập và hoạt động dịch vụ |

Áp dụng nguyên tắc đặc quyền tối thiểu: mỗi workload chỉ có quyền đọc, ghi hoặc gọi đúng tài nguyên cần thiết. Dùng danh tính workload thay cho khóa truy cập tĩnh khi nền tảng hỗ trợ. Mã hóa dữ liệu khi truyền và khi lưu; quản lý khóa và bí mật qua dịch vụ chuyên dụng. Bật audit log cho thao tác quản trị và thay đổi quyền.

Với VM, cần có lịch vá hệ điều hành, baseline cấu hình, quét lỗ hổng và cách thay thế máy bị lỗi. Với container, cần dùng image tin cậy, quét image, khóa phiên bản hoặc digest, loại bỏ công cụ không cần thiết và chạy với quyền thấp nhất. Với serverless, cần rà soát quyền của từng function, thư viện phụ thuộc, trigger công khai và khả năng dữ liệu nhạy cảm xuất hiện trong log.

### Bước 6: Kiểm tra triển khai, mở rộng và tính sẵn sàng

Một lựa chọn compute chỉ phù hợp khi có thể triển khai và phục hồi theo cách lặp lại được.

**Triển khai:** chuẩn hóa cấu hình bằng Infrastructure as Code nếu phù hợp; tách cấu hình môi trường khỏi image hoặc mã; lưu phiên bản artifact; tự động hóa build, kiểm thử, quét bảo mật và phát hành. Có chiến lược rollback hoặc roll-forward rõ ràng. Với container, kiểm tra readiness/liveness và xử lý graceful shutdown. Với VM, chuẩn hóa image máy và quy trình khởi tạo. Với serverless, quản lý phiên bản, cấu hình trigger và quyền theo môi trường.

**Mở rộng:** chọn tín hiệu scale có liên hệ với nút thắt thật. CPU có thể phù hợp với workload tính toán; độ dài hàng đợi phù hợp với worker xử lý thông điệp; số request hoặc concurrency phù hợp với API; độ trễ có thể là tín hiệu bổ sung. Đặt giới hạn tối thiểu và tối đa để bảo vệ phụ thuộc phía sau và kiểm soát chi phí. Scale-out không giải quyết được giới hạn quota, cơ sở dữ liệu quá tải hoặc một dịch vụ phụ thuộc có concurrency thấp.

**Tính sẵn sàng:** chạy nhiều instance khi cần loại bỏ điểm lỗi đơn; phân bố qua các vùng khả dụng theo yêu cầu; đặt health check và cơ chế loại instance lỗi khỏi phân phối tải. Thiết kế ứng dụng để xử lý retry có backoff, timeout, circuit breaker và thông điệp gửi lặp. Với tác vụ nền, dùng hàng đợi bền vững và cơ chế dead-letter hoặc quy trình xử lý thông điệp lỗi. Đối với dữ liệu, compute đa vùng không tự tạo ra khả năng phục hồi nếu cơ sở dữ liệu hoặc storage vẫn là điểm lỗi đơn.

**Khả năng khôi phục:** xác định cách tái tạo compute từ image, cấu hình và dữ liệu đã lưu. Thử nghiệm việc thay instance, triển khai phiên bản mới, mất một vùng và phục hồi từ bản sao lưu theo mức độ phù hợp. Ghi lại thời gian khôi phục thực tế để so sánh với RTO/RPO.

### Bước 7: Tính tổng chi phí sở hữu

Không so sánh VM, container và serverless chỉ bằng giá của một đơn vị compute. Hãy tính chi phí toàn bộ luồng xử lý và chi phí nhân lực vận hành.

Các thành phần thường cần đưa vào mô hình chi phí:

- Compute chạy liên tục, thời gian chạy theo yêu cầu và dung lượng dự phòng.
- Bộ nhớ, đĩa, snapshot, image registry và lưu trữ tạm.
- Load balancer, NAT, địa chỉ IP, truyền dữ liệu ra Internet hoặc giữa các vùng.
- Log, metric, trace, lưu trữ log và cảnh báo.
- Dịch vụ phụ thuộc như database, queue, cache, secret manager và backup.
- Chi phí môi trường phát triển, kiểm thử, staging và disaster recovery.
- Công sức vá lỗi, nâng cấp, trực vận hành, xử lý sự cố và quản lý nền tảng.

VM hoặc container chạy liên tục có thể có chi phí dự đoán được khi tải ổn định và mức sử dụng cao. Serverless có thể tiết kiệm khi tải thưa hoặc biến động, nhưng cần tính số lần gọi, thời gian thực thi, bộ nhớ, concurrency và chi phí dịch vụ được gọi. Kubernetes có thể tối ưu việc dùng chung tài nguyên ở quy mô lớn, nhưng chi phí vận hành và độ phức tạp của cụm cũng phải được tính vào quyết định.

Đánh giá ít nhất ba kịch bản: tải trung bình, tải đỉnh và tải thấp. Thêm kịch bản tăng trưởng để biết khi nào lựa chọn hiện tại cần được xem xét lại. Sử dụng bảng giá và calculator chính thức của nhà cung cấp tại thời điểm ra quyết định; giá, quota và điều kiện chiết khấu có thể thay đổi theo vùng và loại dịch vụ.

### Bước 8: Chấm điểm và ghi lại quyết định

Sau khi loại các ứng viên không đạt yêu cầu bắt buộc, có thể dùng bảng điểm để làm rõ trade-off. Ví dụ dưới đây dùng thang 1–5, trong đó 5 là phù hợp nhất. Trọng số phải được điều chỉnh theo workload cụ thể.

| Tiêu chí | Trọng số minh họa | VM | Container được quản lý | Serverless |
|---|---:|---:|---:|---:|
| Phù hợp runtime và phụ thuộc | 25% |  |  |  |
| Đáp ứng tải và độ trễ | 20% |  |  |  |
| Bảo mật và khả năng kiểm soát | 15% |  |  |  |
| Tính sẵn sàng và phục hồi | 15% |  |  |  |
| Công sức vận hành | 15% |  |  |  |
| Tổng chi phí dự kiến | 10% |  |  |  |

Điền điểm dựa trên bằng chứng: tài liệu giới hạn dịch vụ, thử nghiệm, số liệu đo, ước tính chi phí và năng lực đội ngũ. Không điền điểm theo cảm tính. Một lựa chọn có điểm tổng cao vẫn phải bị loại nếu không đạt điều kiện bắt buộc.

Ghi lại quyết định trong một bản ghi kiến trúc ngắn (ADR) với các nội dung: bối cảnh, yêu cầu, các lựa chọn đã xét, lựa chọn được chọn, lý do, trade-off, giả định, rủi ro, cách giảm thiểu và điều kiện cần xem xét lại. Điều này giúp đội ngũ hiểu vì sao nền tảng được chọn và tránh lặp lại tranh luận khi người phụ trách thay đổi.

## 5. Kiểm chứng lựa chọn bằng thử nghiệm

Không nên đưa quyết định vào production chỉ dựa trên bảng so sánh. Hãy tạo một thử nghiệm đại diện cho đường đi thực tế của request hoặc tác vụ.

Một vòng thử nghiệm hữu ích gồm:

1. **Chuẩn bị workload:** dùng dữ liệu thử phù hợp, kích thước request, mức đồng thời và phụ thuộc gần với thực tế. Không đưa dữ liệu nhạy cảm production vào môi trường thử nghiệm nếu chưa có cơ chế bảo vệ phù hợp.
2. **Đo baseline:** ghi nhận độ trễ p50/p95/p99, throughput, tỷ lệ lỗi, CPU, bộ nhớ, I/O, kết nối và thời gian khởi tạo.
3. **Tăng tải có kiểm soát:** kiểm tra tải bình thường, tải đỉnh, burst và thời gian duy trì tải. Quan sát cả thời gian scale-out lẫn khả năng scale-in.
4. **Kiểm tra lỗi:** dừng một instance, làm gián đoạn một phụ thuộc hoặc mô phỏng thông điệp lỗi. Xác minh retry, timeout, health check và khả năng phục hồi.
5. **Đo chi phí:** đối chiếu tài nguyên sử dụng và hóa đơn ước tính với số request hoặc số tác vụ hoàn thành. Tính chi phí trên một đơn vị công việc hữu ích.
6. **Ghi kết quả:** so sánh với tiêu chí bắt buộc, ghi rõ giới hạn và quyết định tiếp tục, điều chỉnh hay chọn mô hình khác.

Một phép đo có ý nghĩa nên gắn chi phí với kết quả. Ví dụ, chi phí trên một nghìn request thành công hoặc chi phí trên một nghìn ảnh xử lý xong giúp so sánh dễ hơn chi phí compute mỗi giờ khi các mô hình có mức tự động mở rộng khác nhau.

## 6. Ví dụ áp dụng

### Ví dụ 1: Ứng dụng quản lý cũ cần chuyển lên cloud

Ứng dụng chạy liên tục, phụ thuộc vào phiên bản hệ điều hành và một số thư viện cài trực tiếp trên máy. Mã nguồn khó thay đổi trong ngắn hạn; đội ngũ đã có quy trình quản trị máy chủ.

**Lựa chọn ban đầu:** VM là ứng viên hợp lý vì giữ được môi trường hệ điều hành và giảm phạm vi thay đổi khi di chuyển. Thiết kế nhóm VM sau load balancer, tách dữ liệu bền vững khỏi đĩa cục bộ nếu ứng dụng cho phép, quản lý bản vá và cấu hình bằng quy trình chuẩn. Sau khi ổn định, có thể đánh giá từng thành phần để đóng gói thành container hoặc thay thế dần bằng dịch vụ quản lý.

**Điểm cần xác minh:** khả năng chạy trên nhiều instance, cơ chế session, giấy phép phần mềm, backup, quy trình vá lỗi và khả năng phục hồi khi một VM hoặc vùng khả dụng gặp sự cố.

### Ví dụ 2: API cho ứng dụng di động

API được phát hành thường xuyên, có thể đóng gói thành image, chạy stateless và cần mở rộng theo lưu lượng. Đội ngũ muốn kiểm soát runtime và triển khai đồng nhất giữa môi trường kiểm thử và production.

**Lựa chọn ban đầu:** dịch vụ container được quản lý là ứng viên phù hợp. Đóng gói API thành image bất biến, cấu hình tài nguyên CPU/bộ nhớ, readiness check, autoscaling và load balancing. Dùng danh tính workload để truy cập database hoặc secret manager. Nếu đội ngũ cần chính sách điều phối phức tạp và có năng lực vận hành, Kubernetes có thể là lựa chọn; nếu không, nền tảng container đơn giản hơn thường giảm công việc quản trị.

**Điểm cần xác minh:** p95/p99 khi scale-out, số kết nối database, giới hạn concurrency, thời gian khởi động container, triển khai không gián đoạn và khả năng rollback.

### Ví dụ 3: Tạo ảnh thu nhỏ khi có tệp mới

Khi người dùng tải ảnh lên object storage, hệ thống cần tạo một số kích thước ảnh và ghi kết quả trở lại storage. Công việc chỉ phát sinh khi có tệp mới, mỗi tác vụ tương đối độc lập và có thể chạy lại.

**Lựa chọn ban đầu:** function serverless có thể phù hợp vì sự kiện lưu trữ kích hoạt xử lý và nền tảng quản lý phần lớn hạ tầng thực thi. Function cần quyền đọc tệp nguồn và ghi đúng vùng kết quả; giới hạn bộ nhớ, thời gian chạy, kích thước ảnh và concurrency phải được kiểm tra. Dùng mã định danh tác vụ hoặc quy tắc đặt tên đầu ra để xử lý sự kiện gửi lặp an toàn.

**Điểm cần xác minh:** cold start, giới hạn thời gian, kích thước tệp, thư viện xử lý ảnh native, quota đồng thời, chi phí khi có đợt tải lên lớn và cơ chế xử lý sự kiện thất bại. Nếu ảnh rất lớn hoặc xử lý kéo dài vượt giới hạn function, worker container hoặc dịch vụ batch có thể phù hợp hơn.

## 7. Những sai lầm thường gặp

- **Chọn theo xu hướng:** dùng Kubernetes hoặc serverless chỉ vì đội ngũ khác đang dùng. Hãy bắt đầu từ yêu cầu và chi phí vận hành của workload.
- **Coi container là giải pháp tự động mở rộng:** container chỉ là cách đóng gói và chạy ứng dụng. Cần thêm cơ chế điều phối, health check, autoscaling và giới hạn tài nguyên.
- **Bỏ qua trạng thái:** scale nhiều instance nhưng session hoặc tệp tạm vẫn gắn với một máy. Hãy xác định rõ nơi lưu trạng thái và cách xử lý khi instance bị thay thế.
- **Chỉ đo CPU trung bình:** bỏ qua bộ nhớ, I/O, network, kết nối database và độ trễ ở tải đỉnh. Hãy đo các nút thắt của toàn bộ request path.
- **Mở rộng compute mà không bảo vệ phụ thuộc:** nhiều instance hơn có thể làm database hoặc API phía sau quá tải. Đặt giới hạn concurrency, pool kết nối và backpressure.
- **Quên chi phí mạng và quan sát:** log, NAT, truyền dữ liệu liên vùng và load balancer có thể tạo ra khoản chi đáng kể.
- **Cho rằng serverless luôn rẻ:** tải liên tục, thời gian thực thi dài hoặc số lần gọi lớn có thể khiến mô hình khác kinh tế hơn.
- **Không kiểm tra phục hồi:** có nhiều instance nhưng cùng phụ thuộc vào một vùng, một cấu hình hoặc một dịch vụ dữ liệu duy nhất. Cần thử nghiệm lỗi theo mục tiêu RTO/RPO.
- **Không ghi lại giả định:** khi lưu lượng, đội ngũ hoặc yêu cầu bảo mật thay đổi, quyết định cũ có thể không còn phù hợp. ADR và số liệu vận hành giúp xác định thời điểm đánh giá lại.

## 8. Danh sách kiểm tra trước khi chốt lựa chọn

- [ ] Đã mô tả vai trò, mức độ quan trọng và hình dạng tải của workload.
- [ ] Đã xác định runtime, phụ thuộc, trạng thái, thời gian chạy và ràng buộc dữ liệu.
- [ ] Đã phân biệt điều kiện bắt buộc với tiêu chí ưu tiên.
- [ ] Đã so sánh VM, container và serverless theo mức độ phù hợp thực tế.
- [ ] Đã đo hoặc ước lượng CPU, bộ nhớ, I/O, network và concurrency.
- [ ] Đã thiết kế ingress, egress, phân đoạn mạng và kết nối đến dữ liệu.
- [ ] Đã xác định trách nhiệm bảo mật, danh tính workload, quyền tối thiểu, secret và bản vá.
- [ ] Đã xác định cách triển khai, rollback, autoscaling, health check và phục hồi.
- [ ] Đã tính chi phí compute, lưu trữ, mạng, quan sát, phụ thuộc và vận hành.
- [ ] Đã thử nghiệm tải và lỗi với tiêu chí chấp nhận cụ thể.
- [ ] Đã ghi lại quyết định, trade-off, giả định và điều kiện đánh giá lại.

## 9. Kết luận

Lựa chọn nền tảng compute là quá trình ghép đặc điểm workload với mức kiểm soát và trách nhiệm vận hành mà đội ngũ có thể đảm nhận. VM phù hợp khi cần môi trường máy chủ linh hoạt hoặc tương thích với ứng dụng hiện hữu. Container phù hợp khi cần đóng gói nhất quán, triển khai lặp lại và mở rộng dịch vụ độc lập. Serverless phù hợp với nhiều workload theo sự kiện hoặc không liên tục khi giới hạn thực thi đáp ứng yêu cầu.

Quyết định tốt cần dựa trên hồ sơ workload, tiêu chí bắt buộc, thiết kế CPU/bộ nhớ/mạng, kiểm soát bảo mật, kế hoạch triển khai và phục hồi, cùng mô hình chi phí toàn phần. Sau khi triển khai, tiếp tục theo dõi độ trễ, lỗi, mức sử dụng tài nguyên và chi phí để điều chỉnh cấu hình hoặc đánh giá lại mô hình khi workload thay đổi.
