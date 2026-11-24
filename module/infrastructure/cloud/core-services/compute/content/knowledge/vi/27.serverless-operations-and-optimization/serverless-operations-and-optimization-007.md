# Tối ưu khởi tạo runtime và giảm tác động của cold start

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Giải thích cold start và các giai đoạn khởi tạo của một hàm serverless.
- Nhận diện những thành phần làm tăng thời gian khởi tạo runtime.
- Tối ưu mã khởi tạo, dependency, kết nối và cấu hình tài nguyên.
- Chọn biện pháp giảm cold start phù hợp với yêu cầu độ trễ và ngân sách.
- Đo lường, kiểm thử và xác minh hiệu quả tối ưu trong điều kiện tải thực tế.

## 1. Cold start là gì?

Cold start là độ trễ phát sinh khi nền tảng phải chuẩn bị một execution environment mới trước khi có thể chạy handler của hàm. Việc này thường xảy ra khi hàm được gọi lần đầu, khi hệ thống mở rộng để xử lý thêm concurrency, hoặc khi môi trường cũ đã bị thu hồi. Thời điểm thu hồi và tái sử dụng môi trường do nền tảng quyết định.

Một invocation được xử lý trên environment đã khởi tạo và còn khả dụng thường được gọi là warm invocation. Warm invocation có thể bỏ qua phần lớn công việc khởi tạo runtime, nhưng không được bảo đảm luôn xảy ra. Ứng dụng phải hoạt động đúng cả khi mọi invocation đều chạy trên environment mới.

Cold start thường ảnh hưởng rõ nhất đến độ trễ đầu cuối của request đồng bộ, ví dụ API thanh toán hoặc tra cứu đơn hàng. Với xử lý nền qua hàng đợi, hệ thống có thể hấp thụ một phần độ trễ bằng cách xếp hàng và xử lý bất đồng bộ, miễn là thời gian xử lý vẫn đáp ứng cam kết của nghiệp vụ.

## 2. Các giai đoạn tạo execution environment

Chi tiết triển khai khác nhau giữa AWS Lambda, Azure Functions, Google Cloud Run functions và các dịch vụ khác. Một cold start thường có một số công đoạn sau:

1. **Cấp phát môi trường:** nền tảng chọn máy chủ hoặc tài nguyên thực thi, thiết lập môi trường cô lập và chuẩn bị CPU, bộ nhớ cùng cấu hình mạng.
2. **Chuẩn bị mã:** tải package hoặc container image, giải nén artifact và gắn các thành phần cần thiết.
3. **Khởi động runtime:** chạy interpreter hoặc virtual machine, nạp runtime adapter, extension và thư viện nền.
4. **Khởi tạo ứng dụng:** thực thi mã ở phạm vi module, import package, đọc cấu hình, tạo client, thiết lập kết nối hoặc nạp dữ liệu ban đầu.
5. **Gọi handler:** chuyển event và context vào hàm xử lý. Sau khi hoàn tất, nền tảng có thể giữ environment để phục vụ invocation tiếp theo.

Không phải nhà cung cấp nào cũng hiển thị riêng từng giai đoạn. Một số dịch vụ có thể thực hiện thêm bước thiết lập mạng, giải mã image hoặc khôi phục snapshot. Khi đọc log, hãy dùng tên metric và định nghĩa đúng của nhà cung cấp.

Có thể hình dung đường đi của request như sau:

~~~text
Invocation
   |
   v
Có execution environment sẵn sàng?
   | Có                         | Không
   v                            v
Gọi handler                Cấp phát environment
   |                            |
   v                            v
Trả kết quả                Chuẩn bị mã và runtime
                                |
                                v
                           Khởi tạo ứng dụng
                                |
                                v
                           Gọi handler
                                |
                                v
                           Trả kết quả
~~~

Cold start chủ yếu làm tăng thời gian trước khi handler bắt đầu xử lý. Nếu handler tự thực hiện truy vấn chậm hoặc gọi nhiều dịch vụ ngoài, phần thời gian đó là độ trễ nghiệp vụ của invocation, dù không phải cold start. Cần đo tách biệt hai phần để chọn đúng biện pháp.

## 3. Những nguyên nhân làm runtime khởi tạo chậm

### 3.1. Runtime và framework

Một số runtime hoặc framework cần nhiều thời gian để khởi động, nạp metadata, quét classpath hoặc dựng dependency injection container. Ứng dụng Java có thể mất thời gian nạp class và khởi tạo framework; ứng dụng Node.js hoặc Python có thể chậm khi import nhiều package hoặc tải module lớn.

### 3.2. Package và dependency lớn

Artifact chứa nhiều package không sử dụng, file mẫu, tài liệu, binary dư thừa hoặc nhiều layer có thể làm tăng thời gian tải và khởi tạo. Một package native còn có thể thực hiện công việc khởi tạo riêng khi được nạp.

### 3.3. Mã chạy ngoài handler

Mã ở phạm vi module hoặc static initializer chạy khi environment khởi tạo. Nếu phần này đọc nhiều file, nạp mô hình lớn, phân tích cấu hình phức tạp hoặc tạo hàng loạt client, cold start sẽ kéo dài trước khi handler nhận event.

### 3.4. Kết nối và phụ thuộc mạng

Thiết lập kết nối database, DNS lookup, TLS handshake, lấy secret hoặc gọi API cấu hình từ xa đều có thể thêm độ trễ. Nếu ứng dụng thực hiện tuần tự nhiều lời gọi mạng trong giai đoạn init, tổng thời gian khởi tạo có thể tăng đáng kể.

### 3.5. Cấu hình tài nguyên và concurrency

Mức CPU và bộ nhớ được cấp có thể ảnh hưởng trực tiếp đến tốc độ nạp runtime, giải nén package và chạy mã khởi tạo. Khi lưu lượng tăng đột ngột, nền tảng có thể phải tạo nhiều environment cùng lúc; tổng thời gian khởi tạo và tải lên dịch vụ phụ thuộc có thể tăng.

## 4. Tối ưu mã khởi tạo và dependency

Bước đầu tiên là đo thời gian init, sau đó loại bỏ công việc không cần thiết trước khi handler bắt đầu.

**Giữ phần khởi tạo tối thiểu.** Chỉ tạo những thành phần cần thiết cho hầu hết invocation. Đưa xử lý hiếm dùng vào nhánh thực thi tương ứng. Ví dụ, một hàm xử lý đơn hàng không cần nạp thư viện tạo PDF nếu chỉ một tỷ lệ nhỏ request yêu cầu hóa đơn PDF.

**Dùng lazy initialization có chọn lọc.** Lazy initialization trì hoãn việc tạo một đối tượng cho đến lần đầu nó được dùng. Cách này hữu ích với dependency nặng hoặc chỉ dùng trong một số luồng. Tuy nhiên, nó chuyển chi phí khởi tạo sang invocation đầu tiên sử dụng dependency đó. Nếu mọi request đều cần client database, tạo client một lần trong init có thể cho độ trễ ổn định hơn.

**Giảm kích thước artifact.** Chỉ đóng gói package cần thiết, loại bỏ file test và tài liệu khỏi artifact triển khai, dùng tree shaking hoặc bundling khi phù hợp, và tránh đưa nhiều binary không cần thiết vào image. Với container image, chọn base image phù hợp và giảm các layer dư thừa.

**Tối ưu cách nạp module.** Tránh import toàn bộ framework hoặc thư viện lớn nếu chỉ cần một chức năng nhỏ. Trong Java, xem xét classpath, reflection và việc khởi tạo framework; trong Node.js, tránh nạp đồng bộ các module lớn không cần cho mọi request; trong Python, hạn chế import package nặng ở đường khởi tạo chung nếu chúng chỉ phục vụ một nhánh ít dùng.

**Tái sử dụng đối tượng an toàn.** Có thể tạo client SDK, connection pool hoặc cấu trúc dữ liệu bất biến ở phạm vi module để reuse khi environment còn sống. Không lưu dữ liệu riêng của request, token người dùng hoặc trạng thái nghiệp vụ có thể rò rỉ giữa các invocation trong biến toàn cục. Mọi cache trong bộ nhớ phải có giới hạn, thời hạn và cách xử lý dữ liệu cũ.

Ví dụ dưới đây tạo một client ở phạm vi module để tái sử dụng trong các invocation của cùng environment:

~~~python
from cloud_sdk import StorageClient

# Khởi tạo một lần cho mỗi execution environment.
storage = StorageClient()

def handler(event, context):
    object_key = event["object_key"]
    return storage.read_metadata(object_key)
~~~

Mẫu trên phù hợp khi client nhẹ, không chứa trạng thái riêng của request và được SDK hỗ trợ tái sử dụng. Nếu việc tạo client rất tốn thời gian nhưng chỉ một số request cần dùng, có thể chuyển sang lazy initialization. Cả hai cách đều phải xử lý trường hợp environment mới và kết nối cũ bị đóng hoặc hết hạn.

## 5. Tối ưu kết nối và công việc khởi tạo từ xa

Khởi tạo mạng thường có chi phí khó nhìn thấy trong mã ứng dụng. Hãy xem xét từng lời gọi trong init:

- **DNS và TLS:** tái sử dụng client và connection pool khi an toàn; tránh tạo kết nối mới cho từng thao tác nhỏ. Đặt timeout và retry có giới hạn.
- **Database:** tạo pool có kích thước phù hợp với concurrency; không để mỗi environment mở quá nhiều kết nối. Cân nhắc proxy hoặc dịch vụ quản lý kết nối khi phù hợp với nền tảng.
- **Secret và cấu hình:** gom dữ liệu cấu hình cần thiết, cache có TTL và có cơ chế làm mới. Không tải nhiều secret không liên quan trong mọi lần khởi tạo.
- **API bên ngoài:** nếu không bắt buộc để bắt đầu xử lý, trì hoãn lời gọi đến thời điểm nghiệp vụ cần dùng. Nếu bắt buộc, đặt deadline và xử lý lỗi rõ ràng.
- **Mạng riêng/VPC:** đánh giá thời gian thiết lập đường mạng, DNS, route, NAT và security rule theo mô hình của nhà cung cấp. Không mặc định rằng chuyển hàm vào mạng riêng luôn làm cold start chậm như nhau trên mọi dịch vụ; cần đo trên cấu hình thật.

Không nên bỏ qua kiểm tra bảo mật chỉ để giảm init. Nếu secret, chứng thư hoặc quyền truy cập là điều kiện bắt buộc để xử lý an toàn, ứng dụng vẫn phải xác minh chúng trước khi sử dụng.

## 6. Chọn cấu hình runtime và tài nguyên phù hợp

**Chọn runtime phù hợp với workload.** Ưu tiên runtime được nền tảng hỗ trợ chính thức và tương thích với dependency. Runtime nhẹ hoặc framework ít công việc khởi tạo có thể giảm cold start, nhưng quyết định chuyển ngôn ngữ cần tính cả chi phí phát triển, khả năng bảo trì và hiệu năng khi chạy lâu dài.

**Điều chỉnh memory và CPU.** Trên một số dịch vụ, tăng memory đồng thời tăng lượng CPU được cấp. Điều này có thể làm init và xử lý nhanh hơn, dù chi phí cho mỗi đơn vị thời gian có thể tăng. Hãy benchmark nhiều mức tài nguyên và so sánh tổng chi phí cho một request thành công, thay vì chỉ so sánh đơn giá.

**Kiểm tra kiến trúc CPU.** Một số nền tảng hỗ trợ x86_64 và ARM64. Kiến trúc khác có thể có tỷ lệ giá/hiệu năng tốt hơn, nhưng phải xác minh runtime, extension, package native và image tương thích. Đo cả thời gian khởi tạo lẫn thời gian xử lý nghiệp vụ.

**Giảm công việc trong constructor và static initializer.** Tránh tạo thread, quét toàn bộ classpath hoặc nạp dữ liệu lớn nếu handler chưa cần. Với framework lớn, cân nhắc cấu hình khởi động nhanh hoặc framework được thiết kế cho workload ngắn hạn.

## 7. Biện pháp giữ sẵn năng lực và giảm cold start

Tối ưu mã không phải lúc nào cũng đủ. Với endpoint có yêu cầu độ trễ nghiêm ngặt, có thể cần duy trì sẵn một phần năng lực.

| Biện pháp | Cách hoạt động | Trade-off |
|---|---|---|
| Provisioned concurrency | Chuẩn bị trước một số execution environment ở trạng thái sẵn sàng trên phiên bản/alias được cấu hình. | Có chi phí duy trì năng lực ngay cả khi ít request; burst vượt phần đã chuẩn bị vẫn có thể cần capacity bổ sung. |
| Minimum instances hoặc always-ready instances | Giữ tối thiểu một số instance theo cấu hình của nền tảng. | Tốn chi phí cho instance nhàn rỗi; hành vi và cách tính phí khác nhau theo dịch vụ. |
| Pre-warmed instances | Nền tảng duy trì instance đã khởi tạo để phục vụ lưu lượng. | Số lượng, giới hạn và chính sách scale phụ thuộc gói dịch vụ và cấu hình. |
| Snapshot/restore runtime | Lưu trạng thái đã khởi tạo và khôi phục từ snapshot thay vì thực hiện lại toàn bộ init. | Chỉ hỗ trợ một số runtime; phải xử lý dữ liệu ngẫu nhiên, thời gian, kết nối và trạng thái không nên được đóng băng. |

Ví dụ theo nền tảng:

- **AWS Lambda:** Provisioned Concurrency chuẩn bị environment trước cho function version hoặc alias. Có thể dùng SnapStart với các runtime được hỗ trợ để giảm thời gian khởi tạo bằng cách khôi phục snapshot. Cần kiểm tra runtime và điều kiện hỗ trợ của dịch vụ trước khi chọn.
- **Azure Functions:** gói Premium có thể sử dụng prewarmed instances để giảm độ trễ khởi tạo. Số instance sẵn sàng và cách scale phụ thuộc cấu hình plan.
- **Google Cloud Run functions:** cấu hình minimum instances có thể giữ một số instance sẵn sàng. Cần cân nhắc chi phí nhàn rỗi và cách nền tảng scale khi lưu lượng vượt mức tối thiểu.

Provisioned hoặc pre-warmed capacity nên dựa trên lưu lượng nền và SLO. Nếu chỉ một số endpoint cần độ trễ thấp, hãy áp dụng cho đúng function hoặc alias đó thay vì duy trì toàn bộ workload ở trạng thái sẵn sàng.

Không nên dựa vào scheduled ping hoặc keep-warm request như một cam kết rằng environment cụ thể sẽ luôn sống. Nền tảng có thể thu hồi environment, ping có thể tạo thêm chi phí và không bảo đảm đủ capacity khi traffic tăng đột biến.

## 8. Ví dụ cấu hình Provisioned Concurrency

Ví dụ AWS SAM sau cấu hình alias live với năm đơn vị Provisioned Concurrency. Runtime minh họa cần được xác minh theo danh sách hỗ trợ hiện hành của region và dịch vụ trước khi triển khai.

~~~yaml
Resources:
  CheckoutFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/
      Handler: app.handler
      Runtime: python3.12
      MemorySize: 1024
      Timeout: 10
      AutoPublishAlias: live
      ProvisionedConcurrencyConfig:
        ProvisionedConcurrentExecutions: 5
~~~

Trước khi áp dụng, hãy ước tính concurrency nền, đỉnh tải và thời gian tăng tải. Năm environment có thể đủ cho lưu lượng ổn định thấp, nhưng không nhất thiết đáp ứng burst lớn. Theo dõi lượng invocation vượt capacity đã chuẩn bị, độ trễ p95/p99 và chi phí provisioned capacity để điều chỉnh.

Khi phát hành phiên bản mới, cần bảo đảm cấu hình capacity gắn với alias hoặc version mà production đang gọi. Nếu alias chuyển sang version mới, kiểm tra trạng thái provisioned capacity đã sẵn sàng trước khi chuyển toàn bộ lưu lượng theo kế hoạch.

## 9. Đo lường và kiểm thử cold start

Không đánh giá hiệu quả chỉ bằng một lần gọi thử trên máy phát triển. Cần thu thập số liệu ở môi trường và cấu hình gần production.

**Tách cold và warm invocation.** Ghi nhận thời điểm bắt đầu handler, thời gian init nếu nền tảng cung cấp, thời gian xử lý nghiệp vụ và tổng thời gian phản hồi. Không phải dịch vụ nào cũng cung cấp metric cold start riêng; có thể cần kết hợp log nền tảng, trace và dấu mốc do ứng dụng ghi.

**Theo dõi phân vị độ trễ.** So sánh p50, p95 và p99. p50 có thể tốt trong khi một tỷ lệ nhỏ request vẫn bị cold start và làm p99 tăng cao. Theo dõi cả tỷ lệ lỗi, timeout, throttling, memory, concurrency và thời gian xử lý của dependency.

**Kiểm thử các kiểu tải khác nhau:**

1. Gọi một request sau khi hàm chưa được sử dụng trong khoảng thời gian đủ dài theo môi trường thử nghiệm.
2. Gửi nhiều request đồng thời để quan sát scale-out và số environment mới.
3. Tạo burst theo từng đợt để kiểm tra khả năng mở rộng và độ trễ ở đuôi phân phối.
4. So sánh cấu hình memory/CPU, package, lazy initialization và pre-warmed capacity.
5. Lặp lại thử nghiệm đủ nhiều lần để tránh kết luận từ một cold start đơn lẻ.

Với AWS Lambda, log REPORT có thể chứa trường Init Duration cho lần gọi có khởi tạo mới; một số trường hợp SnapStart có thông tin restore riêng. Các metric Duration, Errors, Throttles và ConcurrentExecutions giúp phân tích thêm. Với nền tảng khác, dùng metric startup, instance count, request latency và log tương ứng.

## 10. Quy trình tối ưu có kiểm soát

1. **Đặt mục tiêu:** xác định SLO về p95/p99, tỷ lệ request được phép vượt ngưỡng và ngân sách cho năng lực luôn sẵn sàng.
2. **Lập baseline:** đo cold start, warm duration, kích thước artifact, memory, concurrency, error rate và chi phí hiện tại.
3. **Tìm phần init tốn thời gian:** phân tích import, static initialization, kết nối, secret, DNS, TLS, image pull và extension.
4. **Tối ưu phần mềm trước:** bỏ dependency không dùng, rút gọn package, trì hoãn thành phần hiếm dùng và tái sử dụng client an toàn.
5. **Benchmark tài nguyên:** thử nhiều mức memory/CPU và kiến trúc được hỗ trợ; so sánh cả độ trễ lẫn tổng chi phí.
6. **Thử capacity có sẵn:** áp dụng provisioned/minimum/pre-warmed instances cho workload cần thiết và đo phần giảm p95/p99 so với chi phí tăng thêm.
7. **Phát hành có kiểm soát:** triển khai canary hoặc chuyển traffic từng phần nếu nền tảng hỗ trợ; giữ phiên bản trước để rollback.
8. **Xác minh sau phát hành:** kiểm tra metric, trace, log, lỗi nghiệp vụ và chi phí trong giờ cao điểm lẫn giờ thấp điểm.
9. **Điều chỉnh định kỳ:** cập nhật capacity theo mẫu lưu lượng, mùa vụ, thay đổi dependency và SLO.

Không tối ưu riêng thời gian init nếu nó làm tăng đáng kể thời gian xử lý warm invocation hoặc tạo thêm lỗi. Một thay đổi tốt phải cải thiện chỉ số mục tiêu mà vẫn giữ độ tin cậy và chi phí trong giới hạn.

## 11. Checklist vận hành

- [ ] Đã phân biệt thời gian cold start với thời gian xử lý của handler.
- [ ] Đã đo p50, p95, p99 và tỷ lệ cold start bằng dữ liệu từ môi trường gần production.
- [ ] Mã khởi tạo chỉ làm những công việc cần thiết cho phần lớn invocation.
- [ ] Dependency, package và container image được giữ ở kích thước hợp lý.
- [ ] Client và connection pool được tái sử dụng an toàn; dữ liệu request không lưu trong trạng thái toàn cục.
- [ ] DNS, TLS, secret, database và API ngoài có timeout cùng retry phù hợp.
- [ ] Memory, CPU và kiến trúc được benchmark bằng tải đại diện.
- [ ] Provisioned/minimum/pre-warmed capacity chỉ áp dụng cho workload cần độ trễ thấp.
- [ ] Đã tính chi phí năng lực nhàn rỗi và khả năng burst vượt capacity đã chuẩn bị.
- [ ] Đã kiểm thử cold start, warm invocation, scale-out và rollback.
- [ ] Có cảnh báo cho p95/p99, lỗi, timeout, throttling và chi phí vượt ngưỡng.

## Kết luận

Cold start là chi phí thời gian khi nền tảng tạo và khởi tạo execution environment mới. Có thể giảm tác động bằng cách tinh gọn runtime và dependency, rút ngắn mã init, tái sử dụng kết nối an toàn, chọn tài nguyên phù hợp và duy trì một phần capacity sẵn sàng khi SLO yêu cầu. Đo cold start cùng warm duration, p95/p99 và chi phí giúp đội phát triển chọn được biện pháp phù hợp với workload và ngân sách.