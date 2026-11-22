# Serverless là gì và trách nhiệm của nhà cung cấp cloud

Trong chương **Nền tảng serverless**, bài học này giúp làm rõ serverless là mô hình vận hành ứng dụng trên cloud như thế nào và phần việc nào thuộc về nhà cung cấp cloud, phần việc nào vẫn thuộc về đội phát triển. Đây là nền tảng để quyết định có nên dùng Function as a Service (FaaS) cho một chức năng Java được kích hoạt bởi HTTP, thông điệp hoặc sự kiện hay không.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích serverless và lý do tên gọi này không có nghĩa là ứng dụng không chạy trên máy chủ.
- Phân biệt FaaS với các dịch vụ backend được quản lý (BaaS).
- Mô tả luồng một yêu cầu hoặc sự kiện đi vào function.
- Xác định ranh giới trách nhiệm giữa nhà cung cấp cloud và đội phát triển.
- Nhận biết những quyết định ứng dụng vẫn phải tự xử lý: quyền truy cập, trạng thái, retry, idempotency, khả năng mở rộng, cold start và chi phí.

## 1. Serverless là gì?

**Serverless** là mô hình sử dụng dịch vụ cloud trong đó nhà cung cấp chịu trách nhiệm vận hành phần lớn hạ tầng nền tảng và tự động phân bổ năng lực xử lý theo nhu cầu. Đội phát triển tập trung vào mã ứng dụng và cấu hình dịch vụ thay vì phải tự tạo máy chủ, cài hệ điều hành, duy trì cụm máy hay lập lịch mở rộng từng máy.

Tên gọi này dễ gây hiểu nhầm: **serverless vẫn chạy trên máy chủ**. Máy chủ vật lý, hệ điều hành, mạng và bộ điều phối vẫn tồn tại trong trung tâm dữ liệu của nhà cung cấp. Chúng được trừu tượng hóa khỏi người dùng dịch vụ. Vì vậy, điều thay đổi là trách nhiệm vận hành và mức độ kiểm soát hạ tầng, chứ không phải máy chủ biến mất.

Một hệ thống serverless thường kết hợp hai nhóm dịch vụ:

- **Function as a Service (FaaS):** triển khai một đơn vị mã nhỏ, thường là một function, để nền tảng gọi khi có HTTP request, message hoặc event. Nền tảng quản lý môi trường thực thi và điều chỉnh số lượng phiên thực thi theo tải trong giới hạn dịch vụ.
- **Backend as a Service (BaaS) hoặc dịch vụ backend được quản lý:** sử dụng các năng lực như cơ sở dữ liệu, lưu trữ đối tượng, xác thực, hàng đợi, event bus hoặc API gateway mà nhà cung cấp vận hành. Ứng dụng gọi các dịch vụ này qua API hoặc SDK.

FaaS và BaaS thường đi cùng nhau. Ví dụ, một function Java xử lý đơn hàng có thể được gọi khi hàng đợi nhận message, kiểm tra dữ liệu, rồi ghi kết quả vào cơ sở dữ liệu được quản lý.

### Serverless khác gì với cách chạy máy chủ truyền thống?

| Mô hình | Đội phát triển thường quản lý | Nền tảng thường quản lý |
|---|---|---|
| Máy ảo (IaaS) | Hệ điều hành khách, runtime, ứng dụng, cấu hình mở rộng và phần lớn vận hành máy | Phần cứng, mạng và lớp ảo hóa |
| Container do đội phát triển vận hành | Image, ứng dụng, cấu hình container, cụm chạy, triển khai và mở rộng theo nền tảng đã chọn | Tùy dịch vụ: có thể chỉ là hạ tầng máy hoặc cả control plane |
| FaaS | Mã function, thư viện, cấu hình, quyền, trigger và hành vi khi lỗi | Hạ tầng thực thi, lập lịch invocation và phần lớn việc cấp phát năng lực |
| BaaS / backend được quản lý | Cách ứng dụng sử dụng dịch vụ, dữ liệu, quyền và cấu hình cần thiết | Vận hành nền tảng của dịch vụ backend theo phạm vi sản phẩm |

Ranh giới cụ thể phụ thuộc dịch vụ. Một dịch vụ container được quản lý có thể gánh nhiều việc hơn container tự vận hành; một cơ sở dữ liệu được quản lý có thể yêu cầu khách hàng tự bật backup hoặc cấu hình mạng. Vì vậy, luôn kiểm tra tài liệu trách nhiệm và cấu hình của sản phẩm cloud đang dùng.

## 2. Một function serverless được kích hoạt như thế nào?

Function thường không chạy một vòng lặp chờ yêu cầu như một ứng dụng server truyền thống. Một dịch vụ khác nhận sự kiện, sau đó yêu cầu nền tảng thực thi function tương ứng.

Các kiểu kích hoạt phổ biến:

- **HTTP:** API gateway hoặc lớp tích hợp HTTP nhận request, kiểm tra và chuyển request thành event đầu vào cho function. Function trả kết quả để lớp tích hợp tạo HTTP response.
- **Message:** hàng đợi hoặc dịch vụ truyền message gọi function khi có message cần xử lý. Cách này giúp tách bên gửi khỏi bên nhận và hấp thụ tải tăng đột biến.
- **Event:** event bus, lịch chạy, dịch vụ lưu trữ hoặc một dịch vụ cloud khác phát event khi trạng thái thay đổi. Function phản ứng với event đó.

Luồng tổng quát:

~~~mermaid
flowchart LR
    A["Client hoặc dịch vụ phát sinh"] --> B["HTTP Gateway / Queue / Event Bus"]
    B --> C["Nền tảng FaaS"]
    C --> D["Function Java"]
    D --> E["Database / Object Storage / API"]
    C --> F["Logs và Metrics"]
~~~

Nhà cung cấp vận hành gateway, queue, event bus và môi trường FaaS theo phạm vi từng sản phẩm. Đội phát triển vẫn phải quyết định event nào kích hoạt function, function được phép làm gì, dữ liệu đầu vào có hợp lệ không và kết quả được lưu ở đâu.

### Ví dụ Java đơn giản

Ví dụ sau minh họa một handler theo API của AWS Lambda. Event đầu vào được đơn giản hóa thành một map; event thực tế do HTTP gateway, queue hoặc nguồn sự kiện chuyển đến có thể có cấu trúc khác.

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import java.util.Map;

public class GreetingHandler
        implements RequestHandler<Map<String, String>, Map<String, String>> {

    @Override
    public Map<String, String> handleRequest(
            Map<String, String> event, Context context) {
        String name = event.getOrDefault("name", "bạn");
        return Map.of("message", "Xin chào " + name);
    }
}
~~~

Khi có invocation, nền tảng khởi tạo hoặc tái sử dụng môi trường thực thi, chuyển event và context cho handler, rồi nhận kết quả. Đội phát triển vẫn cần đóng gói mã và thư viện, chọn runtime được hỗ trợ, cấu hình memory và timeout, gắn trigger, cấp quyền phù hợp và xử lý lỗi. Đoạn code không tự tạo endpoint HTTP; endpoint cần được cấu hình ở lớp tích hợp.

## 3. Nhà cung cấp cloud chịu trách nhiệm về điều gì?

Trong mô hình FaaS được quản lý, nhà cung cấp thường chịu trách nhiệm cho các lớp hạ tầng mà khách hàng không trực tiếp vận hành:

1. **Trung tâm dữ liệu và phần cứng:** cơ sở vật chất, nguồn điện, làm mát, thiết bị mạng, máy chủ vật lý và kiểm soát truy cập vật lý.
2. **Lớp nền tảng:** ảo hóa hoặc cô lập workload, hệ điều hành host, control plane, bộ lập lịch và cơ chế cấp phát môi trường thực thi.
3. **Vận hành dịch vụ FaaS:** nhận yêu cầu invocation, khởi tạo môi trường, chuyển event đến handler, thu hồi hoặc tái sử dụng môi trường và điều chỉnh năng lực xử lý theo cơ chế của dịch vụ.
4. **Bảo trì phần được quản lý:** vá lỗi và bảo trì các thành phần nền tảng mà sản phẩm cam kết quản lý, chẳng hạn host và runtime do nhà cung cấp cung cấp.
5. **Vận hành dịch vụ backend:** duy trì hạ tầng của queue, object storage, API gateway hoặc database được quản lý theo cam kết và cấu hình của từng sản phẩm.
6. **Cung cấp cơ chế đo lường và kiểm soát:** công bố quota, giới hạn, thông tin tính phí, trạng thái dịch vụ, log hoặc metric nền tảng mà khách hàng có thể sử dụng.

Điều này giúp đội phát triển không phải trực tiếp quản lý máy chủ cho từng function. Tuy nhiên, trách nhiệm của nhà cung cấp luôn có ranh giới. Chẳng hạn, nhà cung cấp có thể phát hành runtime đã vá, nhưng đội phát triển vẫn phải cập nhật function sang runtime còn được hỗ trợ và cập nhật thư viện bên thứ ba của ứng dụng.

## 4. Đội phát triển vẫn chịu trách nhiệm về điều gì?

Serverless giảm việc vận hành hạ tầng, nhưng không chuyển quyền sở hữu ứng dụng và dữ liệu sang nhà cung cấp. Những quyết định sau vẫn thuộc về đội phát triển hoặc tổ chức sử dụng cloud.

| Khu vực | Nhà cung cấp cloud | Đội phát triển / khách hàng |
|---|---|---|
| Hạ tầng vật lý | Bảo vệ và vận hành trung tâm dữ liệu, máy chủ, mạng nền | Chọn region và dịch vụ phù hợp với yêu cầu |
| Môi trường FaaS | Vận hành control plane, host và cơ chế thực thi được quản lý | Viết function, đóng gói dependency, theo dõi vòng đời runtime và cập nhật thư viện |
| Mã và dữ liệu ứng dụng | Cung cấp dịch vụ lưu trữ hoặc thực thi | Chịu trách nhiệm về tính đúng đắn của mã, phân loại dữ liệu, chất lượng và quyền sử dụng dữ liệu |
| Danh tính và quyền | Cung cấp IAM, policy engine và cơ chế xác thực | Cấu hình principal, role, policy và quyền tối thiểu cho từng function |
| Mạng và bảo vệ dữ liệu | Vận hành hạ tầng mạng; cung cấp cơ chế mã hóa và kiểm soát | Cấu hình network access, endpoint, firewall, secret, khóa và yêu cầu mã hóa phù hợp |
| Độ tin cậy | Vận hành dịch vụ theo thiết kế và SLA đã công bố | Thiết kế retry, idempotency, timeout, xử lý lỗi, backup và khôi phục theo nhu cầu |
| Quan sát và chi phí | Cung cấp số liệu, log, metric và hóa đơn | Thiết lập cảnh báo, theo dõi hành vi nghiệp vụ, tối ưu tài nguyên và ngân sách |

Đây là mô hình **trách nhiệm chia sẻ**. Tên dịch vụ là “managed” không có nghĩa mọi cấu hình bảo mật, sao lưu, phục hồi hay tuân thủ đều tự động được thiết lập đúng cho ứng dụng. Ví dụ, database được quản lý có thể hỗ trợ mã hóa và backup, nhưng khách hàng phải kiểm tra cấu hình, phạm vi backup, thời hạn lưu và khả năng phục hồi có đáp ứng yêu cầu hay không.

### Quyền truy cập là trách nhiệm quan trọng của khách hàng

Mỗi function nên có danh tính thực thi riêng và chỉ được cấp các quyền cần thiết cho nhiệm vụ của nó. Một function xử lý đơn hàng có thể cần đọc một queue và ghi vào một bảng cụ thể; nó không nên mặc nhiên có quyền quản trị toàn bộ tài khoản cloud.

Cần kiểm tra cả hai chiều:

- **Ai được gọi function?** Ví dụ: API gateway, event source hoặc principal nào được phép kích hoạt function.
- **Function được gọi dịch vụ nào?** Ví dụ: function được phép đọc queue nào, ghi object vào bucket nào hoặc truy cập database nào.

Thông tin xác thực và secret không nên được ghi cứng trong mã nguồn hoặc log. Hãy dùng cơ chế quản lý secret và danh tính do nền tảng cung cấp, giới hạn quyền đọc secret và luân chuyển thông tin xác thực theo chính sách của tổ chức.

## 5. Những hệ quả vận hành cần hiểu khi dùng FaaS

Dù nhà cung cấp quản lý máy chủ, đội phát triển vẫn phải thiết kế function để hoạt động đúng trong môi trường phân tán và có giới hạn.

### Trạng thái: không dựa vào bộ nhớ của một lần chạy

Một môi trường thực thi có thể được tái sử dụng, nhưng nền tảng cũng có thể tạo môi trường mới hoặc thu hồi môi trường cũ bất cứ lúc nào. Biến toàn cục và file tạm có thể hữu ích cho cache ngắn hạn, nhưng không phải nơi lưu trạng thái nghiệp vụ lâu dài.

Nếu function cần nhớ trạng thái giữa các lần gọi, hãy lưu trạng thái vào database, object storage, cache hoặc một dịch vụ phù hợp. Thiết kế function theo hướng nhận đủ dữ liệu đầu vào, thực hiện một bước xử lý có giới hạn và lưu kết quả cần thiết.

### Retry và idempotency: một sự kiện có thể được xử lý nhiều lần

Khi function lỗi hoặc không xác nhận xử lý đúng hạn, dịch vụ nguồn có thể gửi lại event. Nhiều cơ chế tích hợp message/event sử dụng giao nhận ít nhất một lần, nên cùng một message có thể xuất hiện nhiều hơn một lần. Hành vi cụ thể tùy nguồn sự kiện và cấu hình; cần đọc rõ tài liệu của trigger.

**Idempotency** là khả năng nhận cùng một yêu cầu nhiều lần mà kết quả nghiệp vụ cuối cùng vẫn tương đương với việc xử lý một lần. Ví dụ, khi xử lý thanh toán, hãy dùng mã giao dịch duy nhất và kiểm tra giao dịch đã được ghi nhận trước khi tạo một khoản thu mới. Không nên chỉ dựa vào việc function “thường chỉ chạy một lần”.

Cần xác định rõ:

- Điều kiện nào khiến một lần xử lý được xem là thành công.
- Lỗi nào có thể retry và lỗi nào cần đưa vào dead-letter queue (DLQ) hoặc luồng xử lý lỗi.
- Giới hạn số lần retry, khoảng chờ và thời gian xử lý tối đa.
- Cách ghi nhận kết quả để lần giao lại không tạo tác dụng phụ trùng lặp.

### Cold start: lần gọi đầu có thể mất thêm thời gian

Nếu chưa có môi trường thực thi sẵn sàng, nền tảng cần khởi tạo môi trường trước khi chạy handler. Khoảng thời gian khởi tạo bổ sung này thường được gọi là **cold start**. Thời gian phụ thuộc runtime, kích thước package, thư viện cần nạp, cấu hình và nền tảng.

Có thể giảm tác động bằng cách giữ package gọn, tránh khởi tạo không cần thiết và đo thời gian thực tế. Một số nền tảng cung cấp cơ chế giữ sẵn môi trường hoặc provisioned concurrency; cơ chế đó có thể giảm độ trễ khởi tạo nhưng thường phát sinh chi phí. Hãy chọn dựa trên yêu cầu latency và số liệu đo, không mặc định mọi invocation đều có cold start.

### Mở rộng tự động vẫn có giới hạn

FaaS có thể tăng số invocation đồng thời khi tải tăng và giảm khi tải thấp. Điều đó không đồng nghĩa năng lực là vô hạn. Tài khoản và dịch vụ có quota về concurrency, tốc độ gọi, thời gian chạy, kích thước payload hoặc số kết nối.

Một đợt tăng tải có thể khiến function tạo nhiều request đồng thời đến database hoặc API phía sau. Nếu hệ thống đích không chịu được mức tải đó, mở rộng function có thể làm tình hình xấu hơn. Đội phát triển cần đặt giới hạn concurrency phù hợp, dùng queue để hấp thụ tải, kiểm soát backpressure và theo dõi throttling cũng như lỗi từ dịch vụ phụ thuộc.

### Chi phí: trả theo cách sử dụng, nhưng phải tính cả hệ thống

FaaS thường tính phí theo số lần gọi và tài nguyên hoặc thời gian thực thi; cách đo và đơn giá thay đổi theo nhà cung cấp. Tổng chi phí của một luồng serverless còn có thể gồm API gateway, queue/event, database, lưu trữ, truyền dữ liệu, log, metric và các năng lực giữ sẵn.

Vì vậy, một function có đơn giá thấp vẫn có thể tạo ra hóa đơn lớn nếu bị gọi quá thường xuyên, chạy quá lâu, ghi log quá nhiều hoặc truy cập dịch vụ phụ trợ đắt tiền. Nên theo dõi chi phí theo function, môi trường và luồng nghiệp vụ; đặt budget và cảnh báo; đồng thời kiểm tra retry bất thường, vòng lặp event và request không hợp lệ.

## 6. Khi nào nên cân nhắc FaaS?

FaaS thường phù hợp khi:

- Công việc được kích hoạt bởi HTTP request, message, lịch chạy hoặc event rõ ràng.
- Tải biến động mạnh hoặc có khoảng thời gian ít hoạt động.
- Công việc có thể chia thành các bước xử lý tương đối độc lập, thời gian chạy nằm trong giới hạn dịch vụ.
- Đội phát triển muốn giảm công việc vận hành máy chủ và chấp nhận mô hình runtime, quota cùng tích hợp của nhà cung cấp.

Cần cân nhắc kỹ khi:

- Tiến trình phải chạy liên tục hoặc lâu hơn giới hạn thời gian của function.
- Ứng dụng phụ thuộc mạnh vào trạng thái trong bộ nhớ hoặc kết nối dài hạn.
- Tải ổn định ở mức cao và cần so sánh chi phí với container hoặc máy chủ chạy liên tục.
- Yêu cầu latency rất nghiêm ngặt nhưng không thể chấp nhận thời gian khởi tạo.
- Ứng dụng cần quyền kiểm soát sâu đối với hệ điều hành, runtime hoặc môi trường mạng.

Không có mô hình nào luôn rẻ hơn hoặc tốt hơn. Hãy so sánh tổng chi phí, độ trễ, độ tin cậy, công sức vận hành và mức độ kiểm soát cần thiết trên một workload cụ thể.

## 7. Ví dụ tổng hợp: xử lý đơn hàng từ message

Giả sử một ứng dụng thương mại điện tử gửi message **OrderCreated** vào queue. Một function Java được kích hoạt để kiểm tra đơn hàng và ghi trạng thái vào database.

- Nhà cung cấp vận hành queue, hạ tầng FaaS và database được quản lý theo cam kết của từng dịch vụ.
- Đội phát triển cấu hình nguồn sự kiện, quyền để function đọc queue và ghi đúng bảng, timeout, concurrency và chính sách retry.
- Function kiểm tra schema và mã đơn hàng; nếu cùng message được giao lại, khóa idempotency hoặc ràng buộc duy nhất giúp tránh tạo bản ghi hay tác dụng phụ trùng lặp.
- Nếu lỗi có thể phục hồi, chính sách retry cho phép thử lại. Nếu message vẫn thất bại sau giới hạn, hệ thống có thể chuyển message sang DLQ để điều tra.
- Log và metric ghi lại mã tương quan, thời gian xử lý, số lần retry và lỗi. Không ghi dữ liệu nhạy cảm hoặc secret vào log.
- Đội phát triển theo dõi số message tồn, tuổi message cũ nhất, tỷ lệ lỗi, concurrency, throttling và chi phí của toàn luồng.

Ví dụ này cho thấy nhà cung cấp giảm gánh nặng vận hành máy chủ, nhưng tính đúng đắn của nghiệp vụ, quyền truy cập và khả năng phục hồi vẫn cần được thiết kế trong ứng dụng.

## 8. Checklist trước khi đưa một function vào sử dụng

- [ ] Đã xác định trigger, cấu trúc event và bên nào được phép gọi function.
- [ ] Function có quyền tối thiểu để truy cập các dịch vụ cần thiết.
- [ ] Dữ liệu và trạng thái cần giữ lâu dài được lưu ở dịch vụ phù hợp.
- [ ] Đã xác định timeout, retry, DLQ và cách xử lý event lỗi.
- [ ] Các thao tác có thể bị lặp đã có cơ chế idempotency.
- [ ] Đã kiểm tra cold start, concurrency, quota và giới hạn của dịch vụ phụ thuộc.
- [ ] Log, metric, cảnh báo và quy trình điều tra lỗi đã sẵn sàng.
- [ ] Đã xem xét backup, phục hồi, bảo vệ dữ liệu và cấu hình mạng.
- [ ] Đã ước tính chi phí cả function lẫn gateway, queue, lưu trữ, database và log.

## Tự kiểm tra

1. Vì sao nói serverless không có nghĩa là “không có máy chủ”?
2. Với một function Java được gọi từ queue, nhà cung cấp cloud quản lý những lớp nào và đội phát triển phải cấu hình những gì?
3. Vì sao không nên lưu trạng thái nghiệp vụ duy nhất trong biến toàn cục của function?
4. Nếu một message có thể được giao lại, cần thiết kế idempotency như thế nào để tránh tạo đơn hàng hai lần?
5. Những thành phần nào ngoài thời gian chạy function có thể làm tăng chi phí của một hệ thống serverless?

Nếu trả lời được các câu hỏi này, bạn đã nắm được ranh giới trách nhiệm cơ bản của serverless. Các chủ đề trigger, quyền, trạng thái, retry, idempotency, cold start, mở rộng và chi phí sẽ được áp dụng sâu hơn khi thiết kế và triển khai các function Java thực tế.

