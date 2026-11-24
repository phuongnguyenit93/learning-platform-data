# Runtime được hỗ trợ và trách nhiệm cập nhật mã ứng dụng

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Giải thích runtime đảm nhiệm phần nào khi nền tảng serverless thực thi một hàm.
- Phân biệt runtime ngôn ngữ do nhà cung cấp quản lý, custom runtime và container image.
- Xác định các tiêu chí cần kiểm tra trong danh sách runtime được hỗ trợ.
- Phân định trách nhiệm cập nhật giữa nhà cung cấp cloud và đội phát triển ứng dụng.
- Lập quy trình nâng cấp runtime, kiểm thử tương thích, phát hành phiên bản và rollback an toàn.

## 1. Runtime trong mô hình hàm serverless

Runtime là lớp phần mềm nhận yêu cầu gọi hàm, chuyển sự kiện cho mã xử lý, rồi gửi kết quả về nền tảng. Runtime thường bao gồm bộ thực thi của ngôn ngữ, cơ chế nạp handler và giao thức trao đổi với môi trường thực thi của nhà cung cấp.

Một lần gọi hàm thường đi qua các bước:

1. Nền tảng cấp hoặc chọn một execution environment cho hàm.
2. Runtime khởi tạo tiến trình, nạp mã, thư viện và cấu hình cần thiết.
3. Runtime gọi handler với sự kiện và thông tin ngữ cảnh.
4. Handler thực hiện nghiệp vụ, gọi dịch vụ phụ thuộc và trả kết quả.
5. Nền tảng ghi nhận kết quả, thu thập log/metric và kết thúc hoặc tái sử dụng execution environment.

Execution environment có thể được giữ lại để xử lý nhiều lần gọi tiếp theo. Vì vậy, mã khởi tạo ở phạm vi module hoặc tiến trình có thể chỉ chạy một lần trong vòng đời của environment, trong khi handler chạy ở mỗi lần invocation. Tuy nhiên, không nên dựa vào việc environment luôn được tái sử dụng: nền tảng có thể tạo environment mới hoặc thu hồi environment cũ bất cứ lúc nào.

Ví dụ, một hàm xử lý đơn hàng có thể khởi tạo client kết nối đến dịch vụ lưu trữ ở phạm vi module để tái sử dụng kết nối. Mỗi invocation chỉ đọc sự kiện, xác thực dữ liệu, thực hiện thao tác và trả kết quả. Mã không được giả định rằng biến toàn cục, file tạm hay trạng thái trong bộ nhớ sẽ tồn tại giữa hai lần gọi.

## 2. Các mô hình runtime thường gặp

Các nền tảng serverless hỗ trợ những mô hình runtime khác nhau. Tên gọi và danh sách phiên bản cụ thể thay đổi theo nhà cung cấp, khu vực, kiến trúc CPU và thời điểm.

### 2.1. Runtime ngôn ngữ do nhà cung cấp quản lý

Nhà cung cấp cung cấp sẵn runtime cho các ngôn ngữ phổ biến như Python, Node.js, Java, .NET, Go hoặc Ruby, tùy dịch vụ. Đội phát triển chọn một phiên bản được hỗ trợ, cung cấp handler và gói mã cùng các thư viện cần thiết.

Ưu điểm:

- Bắt đầu nhanh vì không phải tự đóng gói toàn bộ hệ điều hành và bộ thực thi.
- Nhà cung cấp quản lý phần lớn hạ tầng thực thi và cập nhật runtime theo chính sách của dịch vụ.
- Tích hợp trực tiếp với cơ chế triển khai, log, giám sát và quyền truy cập của nền tảng.

Giới hạn:

- Đội phát triển phải tuân theo phiên bản và cấu hình runtime mà nền tảng cung cấp.
- Thư viện native hoặc phần phụ thuộc hệ điều hành có thể bị giới hạn.
- Khi runtime bị ngừng hỗ trợ, ứng dụng cần được kiểm thử và chuyển sang phiên bản khác trong thời hạn của nhà cung cấp.

### 2.2. Custom runtime

Custom runtime cho phép đội phát triển cung cấp bộ thực thi hoặc lớp chuyển tiếp invocation của riêng mình khi runtime có sẵn không đáp ứng yêu cầu. Mã khởi động thường phải thực hiện giao thức mà nền tảng quy định để nhận sự kiện, gọi handler và trả kết quả.

Mô hình này hữu ích khi cần ngôn ngữ ít phổ biến, phiên bản runtime đặc thù hoặc cách thực thi riêng. Đổi lại, đội phát triển phải chịu trách nhiệm nhiều hơn về bootstrap, xử lý lỗi, tương thích giao thức, cập nhật bảo mật và kiểm thử sau mỗi lần thay đổi.

Custom runtime không loại bỏ các giới hạn của nền tảng serverless. Thời gian chạy, tài nguyên, quyền hệ thống, mạng và cách nền tảng khởi tạo invocation vẫn chịu sự chi phối của dịch vụ.

### 2.3. Runtime đóng gói trong container image

Một số nền tảng cho phép triển khai hàm bằng container image. Đội phát triển đóng gói runtime, thư viện hệ thống và mã ứng dụng vào image theo định dạng mà dịch vụ yêu cầu.

Ưu điểm là môi trường phụ thuộc được mô tả rõ trong Dockerfile, dễ dùng thư viện native và có thể tái sử dụng quy trình build image hiện có. Tuy nhiên, image phải tuân theo hợp đồng khởi chạy và giao thức invocation của nền tảng. Container image không đồng nghĩa với quyền quản trị máy chủ hoặc khả năng chạy workload không giới hạn.

Đội phát triển phải xây dựng image tương thích với kiến trúc CPU được chọn, quét lỗ hổng, cập nhật base image và phát hành image mới khi runtime hoặc thư viện hệ thống cần vá lỗi.

## 3. Cách đọc danh sách runtime được hỗ trợ

Trước khi chọn runtime, hãy kiểm tra tài liệu hỗ trợ chính thức của dịch vụ đang dùng. Không suy ra khả năng hỗ trợ chỉ từ việc ngôn ngữ đó có thể cài đặt trên máy phát triển.

Các tiêu chí cần xác minh:

| Tiêu chí | Câu hỏi cần kiểm tra | Tác động |
|---|---|---|
| Ngôn ngữ và phiên bản | Dịch vụ hỗ trợ phiên bản nào? Phiên bản đó đang ở giai đoạn mới, duy trì hay sắp ngừng hỗ trợ? | Quyết định cú pháp, thư viện và thời hạn nâng cấp. |
| Khu vực triển khai | Runtime có sẵn ở tất cả region cần dùng không? | Ảnh hưởng khả năng triển khai đa vùng và khôi phục thảm họa. |
| Kiến trúc CPU | Runtime hỗ trợ x86_64, ARM64 hay cả hai? | Ảnh hưởng image, thư viện native và hiệu năng/chi phí. |
| Handler và package | Cách khai báo handler, cấu trúc gói và giới hạn kích thước là gì? | Quyết định cách build và đóng gói artifact. |
| Thư viện hệ thống | Có sẵn thư viện, chứng thư, binary hoặc package hệ điều hành nào? | Ảnh hưởng khả năng chạy dependency native. |
| Giới hạn thực thi | Thời gian chạy, bộ nhớ, dung lượng tạm và concurrency tối đa là bao nhiêu? | Ảnh hưởng thiết kế tác vụ và phân chia công việc. |
| Chính sách cập nhật | Runtime được vá tự động, theo cấu hình hay theo lịch của người dùng? | Ảnh hưởng kế hoạch kiểm thử và kiểm soát thay đổi. |
| Ngày ngừng hỗ trợ | Khi nào không còn bản vá hoặc không thể tạo hàm mới bằng runtime đó? | Xác định hạn chót nâng cấp. |

Cần phân biệt ba mốc: ngày ngừng tạo hàm mới bằng runtime cũ, ngày ngừng cập nhật bảo mật và ngày runtime không còn được nền tảng thực thi. Chính sách có thể khác nhau giữa nhà cung cấp và từng runtime. Khi nhận thông báo deprecation, hãy kiểm tra mốc áp dụng cho dịch vụ, region và tài khoản của mình.

Runtime được hỗ trợ cũng có thể khác theo mô hình triển khai. Một phiên bản có trong managed runtime chưa chắc được hỗ trợ trong custom runtime hoặc container image theo cùng cách. Hãy xác minh cả runtime, kiến trúc và trigger mà hàm sẽ sử dụng.

## 4. Phân chia trách nhiệm cập nhật

Serverless giảm phần việc vận hành máy chủ, nhưng không chuyển toàn bộ trách nhiệm vận hành ứng dụng sang nhà cung cấp.

| Hạng mục | Nhà cung cấp cloud | Đội phát triển ứng dụng |
|---|---|---|
| Hạ tầng thực thi | Vận hành máy chủ, lập lịch, cô lập và cấp phát execution environment. | Chọn cấu hình tài nguyên và thiết kế ứng dụng phù hợp giới hạn dịch vụ. |
| Managed runtime | Duy trì runtime do dịch vụ cung cấp và áp dụng bản cập nhật theo chính sách công bố. | Theo dõi thông báo, chọn chính sách cập nhật nếu có, kiểm thử tương thích và triển khai thay đổi mã khi cần. |
| Mã hàm và handler | Cung cấp hợp đồng invocation và môi trường để chạy hàm. | Sửa lỗi nghiệp vụ, handler, xử lý sự kiện, timeout và logic retry. |
| Dependency ứng dụng | Có thể cung cấp một số thư viện nền tảng được công bố. | Quản lý phiên bản package, lockfile, thư viện framework và dependency được đóng gói cùng ứng dụng. |
| Native library và container image | Duy trì dịch vụ container/serverless và các giới hạn thực thi. | Build đúng kiến trúc, cập nhật base image, binary và thư viện native. |
| Custom runtime | Cung cấp giao thức và điểm tích hợp được hỗ trợ. | Duy trì bootstrap, runtime tự cung cấp, tương thích giao thức và bản vá của thành phần đó. |
| Kiểm thử và phát hành | Cung cấp cơ chế triển khai, phiên bản và giám sát ở cấp nền tảng. | Chịu trách nhiệm kiểm thử nghiệp vụ, phát hành, theo dõi lỗi và rollback mã ứng dụng. |

Với managed runtime, nhà cung cấp có thể vá runtime nền hoặc hệ điều hành theo lịch và cơ chế của dịch vụ. Đội ứng dụng vẫn phải bảo đảm mã, thư viện và cấu hình tương thích sau cập nhật. Nếu ứng dụng dùng API đã bị loại bỏ, phụ thuộc có hành vi thay đổi hoặc thư viện native không tương thích, bản vá nền tảng có thể làm hàm phát sinh lỗi dù mã nguồn không thay đổi.

Với custom runtime hoặc container image, ranh giới trách nhiệm dịch chuyển nhiều hơn về phía đội phát triển. Đội phải theo dõi lỗ hổng trong runtime tự đóng gói, base image và dependency hệ thống; build lại artifact đã vá và triển khai phiên bản mới.

## 5. Quản lý dependency và tương thích mã ứng dụng

Mã hàm thường phụ thuộc vào nhiều lớp phần mềm:

- Runtime ngôn ngữ và phiên bản interpreter/virtual machine.
- Framework và package bên thứ ba.
- Thư viện native như thư viện xử lý ảnh, mã hóa hoặc kết nối cơ sở dữ liệu.
- Extension hoặc agent phục vụ giám sát, bảo mật và telemetry.
- Biến môi trường, cấu hình endpoint, chứng thư và quyền truy cập.

Để kiểm soát các phụ thuộc này:

1. Khai báo dependency trực tiếp trong file quản lý gói, chẳng hạn requirements.txt, poetry.lock, package-lock.json, go.mod hoặc file tương ứng của ngôn ngữ.
2. Pin phiên bản phù hợp và commit lockfile để các lần build có thể tái lập.
3. Tạo SBOM hoặc báo cáo dependency nếu quy trình bảo mật yêu cầu; quét lỗ hổng trước khi phát hành.
4. Build thư viện native trong môi trường tương thích với runtime và kiến trúc đích. Một package biên dịch trên máy Windows x86_64 có thể không chạy trong Linux ARM64.
5. Kiểm tra giới hạn kích thước gói, số lượng layer, dung lượng giải nén và thư viện được cung cấp sẵn bởi nền tảng.
6. Tránh đưa bí mật như API key hoặc mật khẩu vào image, mã nguồn hay file cấu hình được commit; sử dụng dịch vụ quản lý secret và quyền truy cập tối thiểu.

Ví dụ, hàm Python xử lý ảnh có thể dùng package chứa mã native. Khi chuyển runtime từ một phiên bản Python sang phiên bản mới hoặc chuyển kiến trúc từ x86_64 sang ARM64, đội phát triển cần cài hoặc biên dịch lại package tương ứng, sau đó kiểm thử thao tác giải mã, biến đổi và lưu ảnh trong môi trường gần với môi trường chạy thật.

## 6. Ví dụ cấu hình và cập nhật runtime

Ví dụ AWS SAM dưới đây khai báo một hàm Python. python3.12 chỉ là giá trị minh họa cho cấu hình; trước khi triển khai cần xác minh phiên bản đó còn được dịch vụ hỗ trợ trong region và kiến trúc đã chọn.

~~~yaml
Resources:
  OrderHandler:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: python3.12
      Handler: app.handler
      CodeUri: src/
      Architectures:
        - arm64
      MemorySize: 512
      Timeout: 15
      Environment:
        Variables:
          LOG_LEVEL: INFO
~~~

Handler tương ứng có thể có dạng:

~~~python
def handler(event, context):
    order_id = event.get("order_id")
    if not order_id:
        return {
            "statusCode": 400,
            "body": "order_id is required"
        }

    # Thực hiện nghiệp vụ bằng dependency đã được đóng gói.
    return {
        "statusCode": 200,
        "body": f"accepted: {order_id}"
    }
~~~

Khi nâng cấp runtime, không chỉ thay trường Runtime. Hãy kiểm tra cú pháp và API của ngôn ngữ, phiên bản framework, dependency, thư viện native, biến môi trường, quyền truy cập và hành vi timeout. Nếu đổi kiến trúc CPU cùng lúc, cần build lại các dependency native và kiểm thử riêng ảnh hưởng hiệu năng.

Một quy trình cập nhật điển hình:

1. Xác định runtime đích còn được hỗ trợ và có trong region triển khai.
2. Tạo nhánh thay đổi, cập nhật cấu hình runtime và dependency; lưu lockfile cùng mã nguồn.
3. Build artifact sạch trong môi trường tương thích với runtime/architecture đích.
4. Chạy unit test, integration test và kiểm tra bảo mật dependency.
5. Triển khai lên môi trường thử nghiệm với cấu hình gần production; kiểm tra cold start, thời gian thực thi, memory, log và kết quả nghiệp vụ.
6. Phát hành phiên bản mới. Nếu nền tảng hỗ trợ version/alias hoặc traffic splitting, giữ phiên bản cũ và chuyển một phần lưu lượng sang phiên bản mới trước khi tăng dần.
7. Theo dõi error rate, timeout, độ trễ, throttling và chi phí. Dừng rollout hoặc chuyển alias về phiên bản trước nếu chỉ số vượt ngưỡng đã định.
8. Sau khi ổn định, loại bỏ dependency và cấu hình cũ, cập nhật tài liệu vận hành và lịch nâng cấp tiếp theo.

Ví dụ với AWS Lambda, đội có thể cập nhật code package và cấu hình runtime, chờ trạng thái cập nhật hoàn tất, sau đó publish một function version bất biến và trỏ alias live đến version đó. Alias giúp chuyển lưu lượng và khôi phục nhanh về version trước. Với Azure Functions hoặc Google Cloud Run functions, cơ chế chọn stack/runtime, tạo revision và chuyển traffic có tên gọi khác; nguyên tắc vẫn là kiểm thử artifact mới trước khi đưa toàn bộ lưu lượng vào phiên bản mới.

## 7. Các trade-off khi chọn mô hình runtime

| Lựa chọn | Điểm mạnh | Chi phí và rủi ro |
|---|---|---|
| Managed runtime | Ít công việc vận hành, tích hợp tốt với nền tảng và có lộ trình cập nhật do nhà cung cấp quản lý. | Phụ thuộc phiên bản được hỗ trợ; cần chủ động kiểm thử khi runtime được cập nhật hoặc ngừng hỗ trợ. |
| Custom runtime | Linh hoạt về ngôn ngữ và cách thực thi. | Đội phát triển phải duy trì bootstrap, giao thức, runtime và bản vá bảo mật. |
| Container image | Kiểm soát rõ dependency hệ thống, dễ dùng thư viện native và tái sử dụng quy trình build image. | Image lớn có thể làm tăng thời gian tải/khởi tạo; đội phát triển phải cập nhật base image và quét lỗ hổng. |
| Layer hoặc extension | Tái sử dụng thư viện và agent giữa nhiều hàm. | Có thể tạo xung đột phiên bản, tăng kích thước gói, thời gian khởi tạo và bề mặt tấn công. |

Một runtime mới không tự động là lựa chọn tốt nhất. Hãy cân nhắc mức hỗ trợ còn lại, khả năng tương thích dependency, hiệu năng, thời gian khởi động, kích thước artifact, kiến trúc CPU và năng lực vận hành của đội. Nếu ứng dụng ổn định trên managed runtime, tiếp tục dùng mô hình này thường giảm khối lượng bảo trì. Nếu cần thư viện hệ thống đặc thù, container image có thể phù hợp hơn, nhưng đội phải duy trì chu kỳ cập nhật image.

## 8. Xác minh sau khi cập nhật

Dùng môi trường staging hoặc một alias thử nghiệm để xác minh trước khi chuyển lưu lượng production.

- **Kiểm tra cấu hình:** xác nhận runtime, kiến trúc, handler, timeout, memory, biến môi trường và region đúng với mục tiêu.
- **Kiểm tra khởi tạo:** theo dõi thời gian cold start, lỗi import package, lỗi bootstrap và lỗi extension.
- **Kiểm tra invocation:** gửi sự kiện đại diện cho luồng thành công, dữ liệu thiếu, dữ liệu sai định dạng, lỗi phụ thuộc và retry.
- **Kiểm tra dependency:** xác nhận package native nạp được, chứng thư hợp lệ, kết nối mạng hoạt động và secret được cấp đúng quyền.
- **Kiểm tra tài nguyên:** so sánh duration, memory sử dụng, concurrency, throttling và tỷ lệ timeout trước/sau cập nhật.
- **Kiểm tra bảo mật:** quét dependency và image, xác nhận không có secret bị đóng gói, quyền thực thi tuân theo nguyên tắc tối thiểu.
- **Kiểm tra rollback:** diễn tập chuyển alias hoặc traffic về phiên bản trước và xác nhận invocation hoạt động trở lại.

Với AWS Lambda, có thể dùng log của CloudWatch, metric invocation/error/duration/throttles và trạng thái function update để kiểm tra. Trên Azure Functions hoặc Google Cloud Run functions, dùng log, metric và trạng thái deployment/revision tương ứng. Hãy đối chiếu các chỉ số với baseline trước khi nâng cấp thay vì chỉ dựa vào việc deployment báo thành công.

## 9. Checklist quản lý runtime

- [ ] Runtime và phiên bản nằm trong danh sách hỗ trợ của dịch vụ, region và kiến trúc đích.
- [ ] Đã kiểm tra ngày deprecation, thời hạn cập nhật bảo mật và kế hoạch nâng cấp.
- [ ] Handler, framework và dependency tương thích với runtime đích.
- [ ] Lockfile được lưu và artifact có thể build lại.
- [ ] Thư viện native được build đúng hệ điều hành và kiến trúc.
- [ ] Base image, custom runtime và extension có quy trình vá lỗi rõ ràng.
- [ ] Secret không nằm trong mã nguồn, image hoặc package triển khai.
- [ ] Đã chạy unit test, integration test và kiểm thử invocation thực tế.
- [ ] Đã so sánh cold start, duration, memory, lỗi và throttling với baseline.
- [ ] Có phiên bản cũ hoặc phương án rollback đã được kiểm chứng.
- [ ] Có người chịu trách nhiệm theo dõi thông báo runtime và lịch nâng cấp tiếp theo.

## Kết luận

Runtime quyết định cách mã hàm được khởi tạo và thực thi trong nền tảng serverless. Chọn runtime được hỗ trợ giúp ứng dụng tương thích với dịch vụ và có lộ trình bảo trì rõ ràng. Nhà cung cấp quản lý hạ tầng cùng managed runtime theo chính sách nền tảng; đội phát triển chịu trách nhiệm về mã ứng dụng, dependency, custom runtime hoặc image tự đóng gói, kiểm thử tương thích và phát hành phiên bản an toàn. Một quy trình nâng cấp có kiểm thử, giám sát và rollback giúp giảm rủi ro khi runtime thay đổi hoặc tiến gần ngày ngừng hỗ trợ.