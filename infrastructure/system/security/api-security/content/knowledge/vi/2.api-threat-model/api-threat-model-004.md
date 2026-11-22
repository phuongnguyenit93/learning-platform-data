# Lạm dụng tài nguyên, quota và dependency tính phí

## 1. Vì sao cần kiểm soát tài nguyên ở cấp API?

Một API có thể xác thực người gọi đúng, dùng HTTPS và vẫn bị khai thác để gây thiệt hại. Kẻ tấn công không nhất thiết phải chiếm tài khoản hay đọc dữ liệu trái phép. Chỉ cần gửi những yêu cầu hợp lệ về mặt cú pháp nhưng buộc hệ thống làm quá nhiều việc: chạy truy vấn lớn, tạo báo cáo nặng, giải nén tệp, gọi dịch vụ AI, gửi SMS, tra cứu địa chỉ hoặc kích hoạt nhiều dịch vụ phía sau.

Đây là nhóm rủi ro lạm dụng tài nguyên. Hậu quả có thể là:

- CPU, bộ nhớ, kết nối cơ sở dữ liệu hoặc hàng đợi bị chiếm dụng, khiến người dùng bình thường không truy cập được.
- Hóa đơn tăng do mỗi yêu cầu kích hoạt một hay nhiều dịch vụ tính phí.
- Một khách hàng hoặc một API key tiêu thụ phần lớn năng lực dùng chung, làm giảm chất lượng dịch vụ của các tenant khác.
- Hệ thống bên thứ ba bị gọi quá mức, khóa tài khoản tích hợp hoặc áp dụng phụ phí.
- Các luồng nghiệp vụ bị nghẽn: đơn hàng, thông báo, xử lý tệp, thanh toán hoặc tác vụ nền không hoàn tất đúng hạn.

Giới hạn tài nguyên vì thế là một phần của bảo mật API và bảo vệ nghiệp vụ. Nó cần được thiết kế theo endpoint, danh tính, đối tượng dữ liệu và chi phí thực tế của thao tác. Một giới hạn chung kiểu “mỗi IP được gọi 100 lần mỗi phút” thường không đủ: một yêu cầu tìm kiếm có thể rẻ, trong khi một yêu cầu xuất báo cáo có thể tạo hàng nghìn truy vấn và nhiều lần gọi dịch vụ tính phí.

## 2. Phân biệt rate limit, quota, budget và concurrency limit

Các khái niệm này liên quan nhưng giải quyết những vấn đề khác nhau.

| Cơ chế | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Rate limit | Trong một khoảng thời gian ngắn, một chủ thể được gửi bao nhiêu yêu cầu? | Tối đa 20 yêu cầu/giây, cho phép burst ngắn |
| Quota | Trong một chu kỳ, chủ thể được dùng tổng cộng bao nhiêu đơn vị? | 500 lần xuất báo cáo/tháng |
| Budget / spending limit | Có thể phát sinh tối đa bao nhiêu chi phí? | Tối đa 50 USD chi phí nhà cung cấp mỗi ngày cho một tenant |
| Concurrency limit | Có bao nhiêu thao tác được chạy đồng thời? | Tối đa 3 tác vụ xuất dữ liệu đang xử lý |
| Capacity limit | Một thao tác được phép tiêu thụ tối đa bao nhiêu tài nguyên? | Tệp tải lên tối đa 10 MB, truy vấn tối đa 5.000 dòng |

Các con số trong ví dụ chỉ minh họa cách diễn đạt chính sách; giới hạn thực tế phải dựa trên năng lực hệ thống, hợp đồng dịch vụ và mô hình kinh doanh.

Rate limit bảo vệ hệ thống trước lưu lượng dồn dập. Quota kiểm soát mức sử dụng tích lũy. Budget bảo vệ chi phí tiền tệ, đặc biệt khi phụ thuộc nhà cung cấp tính phí theo lượt gọi, dung lượng, thời gian xử lý hoặc token. Concurrency limit ngăn nhiều công việc nặng cùng chiếm tài nguyên tại một thời điểm. Capacity limit chặn một yêu cầu đơn lẻ có kích thước hoặc độ phức tạp quá lớn.

Một endpoint có rủi ro cao thường cần kết hợp nhiều cơ chế. Ví dụ, endpoint tạo bản tóm tắt bằng mô hình AI có thể giới hạn số yêu cầu mỗi phút, số tài liệu mỗi ngày, số tác vụ chạy đồng thời, độ dài đầu vào và tổng ngân sách của tenant.

## 3. Xác định đúng chủ thể và phạm vi áp dụng

Trước khi đặt một con số giới hạn, cần xác định ai đang tiêu thụ tài nguyên và tài nguyên nào đang được chia sẻ. Các khóa giới hạn thường gặp gồm:

- **Tenant hoặc tổ chức:** phù hợp với quota hợp đồng, ngân sách và công bằng giữa khách hàng.
- **Tài khoản người dùng:** kiểm soát mức sử dụng của từng người trong một tổ chức.
- **API key hoặc client:** kiểm soát ứng dụng tích hợp và thông tin xác thực riêng.
- **Địa chỉ IP hoặc dải mạng:** hữu ích cho lưu lượng chưa xác thực và lớp phòng vệ ở biên.
- **Đối tượng nghiệp vụ:** giới hạn số lần thao tác trên một dự án, đơn hàng, hộp thư hoặc tài nguyên cụ thể.
- **Endpoint và nhóm thao tác:** phân biệt API đọc nhẹ với API tìm kiếm, xuất dữ liệu, gửi thông báo hoặc xử lý AI.
- **Nhà cung cấp hoặc tài khoản dependency:** bảo vệ hạn mức và ngân sách của dịch vụ bên ngoài.

Không nên chỉ dựa vào IP. Nhiều người dùng hợp lệ có thể cùng đi qua NAT, proxy doanh nghiệp hoặc mạng di động; ngược lại, một tác nhân có thể đổi IP. IPv6 cũng khiến việc gom nhóm theo địa chỉ cần được cân nhắc cẩn thận. Với API đã xác thực, tenant, user và client thường là các khóa quan trọng hơn. IP nên là một tín hiệu bổ sung, đặc biệt ở lớp chống bot và bảo vệ trước xác thực.

Không nên chỉ dựa vào API key nếu nhiều người hoặc nhiều tenant dùng chung một key. Khi đó, một khách hàng có thể tiêu thụ hết hạn mức của người khác. Cần xác định danh tính nghiệp vụ từ thông tin đã được xác thực và kiểm tra quyền truy cập đối tượng trước khi cho phép thao tác. Không tin tenant ID, user ID hay owner ID do client tự gửi nếu server chưa đối chiếu với principal đã xác thực.

Một chính sách tốt có thể áp dụng đồng thời nhiều chiều: giới hạn tổng theo tenant, giới hạn riêng theo user, giới hạn burst theo client và giới hạn năng lực toàn hệ thống. Điều này giúp vừa công bằng giữa khách hàng vừa ngăn một người dùng trong cùng tổ chức tiêu thụ toàn bộ quota của tổ chức.

## 4. Lập bản đồ tài nguyên và chi phí theo endpoint

Hãy liệt kê các endpoint và mô tả công việc thực tế mà mỗi endpoint kích hoạt. Không đánh giá độ đắt chỉ dựa trên số byte request hoặc số HTTP call.

| Nhóm endpoint | Tài nguyên cần đo | Biện pháp thường cần |
|---|---|---|
| Đọc danh sách, tìm kiếm | Số dòng quét, độ sâu lọc, thời gian truy vấn, kích thước phản hồi | Pagination có giới hạn, timeout, giới hạn độ phức tạp |
| Xuất báo cáo, tải dữ liệu | CPU, bộ nhớ, số dòng, dung lượng lưu trữ và băng thông | Hàng đợi, giới hạn kích thước, concurrency và quota |
| Tải lên, giải nén tệp | Byte truyền, kích thước sau giải nén, số entry, thời gian quét | Giới hạn kích thước, kiểm tra định dạng, giới hạn giải nén |
| Gửi email, SMS, thông báo | Số lần gửi, giá nhà cung cấp, giới hạn tài khoản | Quota theo tenant/người nhận, chống gửi lặp, budget |
| Gọi AI hoặc dịch vụ tính phí | Token, số ảnh/tệp, thời gian xử lý, số lần gọi | Giới hạn đầu vào/đầu ra, weighted quota, budget |
| Tạo tác vụ nền | Độ dài hàng đợi, thời gian chạy, số worker và số lần retry | Admission control, concurrency, timeout, retry budget |
| Thanh toán hoặc thao tác có tác động tiền | Số giao dịch, số lần thử, chi phí xử lý | Idempotency, giới hạn nghiệp vụ, phát hiện bất thường |

Với mỗi endpoint, ghi rõ:

1. Ai được gọi và đối tượng nào họ được phép thao tác?
2. Một yêu cầu có thể kích hoạt bao nhiêu truy vấn, tác vụ nền hoặc lời gọi dependency?
3. Có giới hạn kích thước, số lượng, độ sâu, thời gian và mức đồng thời chưa?
4. Chi phí tăng tuyến tính hay có thể tăng theo cấp số nhân khi đầu vào lớn?
5. Có thể cache, gom lô, trì hoãn hoặc từ chối sớm thao tác không?
6. Khi dependency chậm hoặc hết hạn mức, hệ thống sẽ dừng, xếp hàng hay thử lại?

Đặc biệt chú ý các dạng khuếch đại: một request tạo ra hàng trăm truy vấn; một bản ghi kích hoạt nhiều thông báo; một URL do người dùng cung cấp khiến server tải nhiều tài nguyên; hoặc một lần retry ở nhiều tầng nhân số lần gọi. Đo chi phí ở phía server và dependency adapter, không chỉ đếm request tại API gateway.

## 5. Chọn thuật toán giới hạn phù hợp

### 5.1 Fixed window

Fixed window đếm số yêu cầu trong từng cửa sổ cố định, ví dụ từ 10:00 đến 10:01. Cách này dễ triển khai và tiết kiệm bộ nhớ. Tuy nhiên, người gọi có thể gửi gần hết hạn mức ở cuối cửa sổ rồi gửi tiếp ngay đầu cửa sổ kế tiếp. Nếu giới hạn là 60 yêu cầu/phút, một chủ thể có thể gửi gần 120 yêu cầu trong một khoảng thời gian rất ngắn quanh ranh giới hai phút.

### 5.2 Sliding log và sliding window counter

Sliding log lưu thời điểm từng yêu cầu rồi đếm các yêu cầu trong khoảng thời gian trượt. Nó chính xác nhưng cần lưu và dọn nhiều mốc thời gian. Sliding window counter kết hợp bộ đếm cửa sổ hiện tại với cửa sổ trước đó để ước lượng số yêu cầu trong khoảng trượt; nó tiết kiệm hơn nhưng có sai số nhỏ.

### 5.3 Token bucket

Token bucket phù hợp khi muốn giới hạn tốc độ trung bình nhưng vẫn cho phép burst ngắn. Bucket được nạp token theo tốc độ cố định đến một dung lượng tối đa. Mỗi yêu cầu tiêu thụ một hoặc nhiều token. Nếu không đủ token, yêu cầu bị từ chối hoặc trì hoãn.

Ví dụ: bucket có dung lượng 30 token và được nạp 10 token mỗi giây. Một client có thể gửi nhanh tối đa 30 yêu cầu khi bucket đầy; về lâu dài tốc độ trung bình không vượt quá mức nạp. Với endpoint đắt, mỗi yêu cầu có thể tiêu thụ số token theo trọng số thay vì luôn là một token.

### 5.4 Leaky bucket và giới hạn đồng thời

Leaky bucket đưa công việc vào hàng đợi và xử lý với tốc độ ổn định. Nó hữu ích khi cần làm phẳng lưu lượng, nhưng hàng đợi phải có giới hạn. Hàng đợi không giới hạn chỉ chuyển tình trạng quá tải từ API sang bộ nhớ và thời gian chờ.

Semaphore hoặc bộ đếm concurrency giới hạn số công việc đang chạy cùng lúc. Đây là biện pháp quan trọng với truy vấn lớn, xuất tệp, xử lý ảnh và gọi dependency chậm. Nên có cả giới hạn theo tenant lẫn giới hạn toàn hệ thống để một tenant không chiếm toàn bộ worker.

### 5.5 Quota tích lũy và budget

Quota theo ngày, tháng hoặc chu kỳ hợp đồng cần bộ đếm tích lũy. Với thao tác có chi phí biến thiên, không nên chỉ trừ một đơn vị cho mọi yêu cầu. Hãy ước tính mức tiêu thụ theo đầu vào, độ phức tạp hoặc số token; sau khi xử lý, đối soát với mức dùng thực tế.

Với thao tác tốn phí, quy trình an toàn thường là **ước tính → giữ chỗ → thực hiện → quyết toán**:

1. Xác định principal, tenant, đối tượng và chính sách áp dụng.
2. Ước tính mức tiêu thụ tối đa hoặc hợp lý từ đầu vào đã được xác thực và kiểm tra.
3. Giữ chỗ quota/budget một cách nguyên tử trước khi gọi dependency.
4. Thực hiện thao tác với timeout, giới hạn đầu ra và idempotency phù hợp.
5. Ghi nhận mức sử dụng thực tế; hoàn lại phần giữ chỗ thừa nếu chính sách cho phép.
6. Nếu thất bại, quyết định rõ trường hợp nào được hoàn quota. Không tự động hoàn mọi lỗi nếu nhà cung cấp vẫn tính phí cho yêu cầu đã nhận.

Giữ chỗ giúp tránh nhiều request đồng thời cùng đọc một số dư rồi cùng tiêu vượt hạn mức. Việc quyết toán phải có mã giao dịch hoặc idempotency key để không ghi nhận chi phí hai lần khi callback hay retry được gửi lặp.

## 6. Thiết kế enforcement an toàn trong hệ thống phân tán

### 6.1 Đặt kiểm soát ở nhiều lớp

- **API gateway:** chặn lưu lượng bất thường sớm, áp dụng giới hạn IP/client và giới hạn kích thước cơ bản.
- **Application service:** áp dụng chính sách theo tenant, user, vai trò, đối tượng và nghiệp vụ. Đây là nơi có đủ ngữ cảnh để quyết định quota có ý nghĩa.
- **Dependency adapter:** giới hạn số lần gọi, timeout, kích thước đầu vào/đầu ra và ngân sách theo từng nhà cung cấp.
- **Worker và queue:** kiểm soát độ dài hàng đợi, concurrency, thời gian chạy, retry và công bằng giữa tenant.
- **Hạ tầng:** giới hạn kết nối, CPU, bộ nhớ, dung lượng lưu trữ, egress và ngân sách tài nguyên cloud.

Các lớp phải thống nhất chính sách và không tạo đường vòng. Nếu gateway giới hạn nhưng endpoint nội bộ có thể bị gọi trực tiếp từ mạng khác, giới hạn có thể bị bỏ qua. Nếu application service kiểm tra quota nhưng worker không giới hạn concurrency, hàng đợi vẫn có thể làm cạn tài nguyên.

### 6.2 Cập nhật bộ đếm nguyên tử

Trong môi trường nhiều instance, thao tác đọc số dư rồi ghi số dư mới không an toàn. Hai instance có thể cùng thấy còn một đơn vị quota và cùng chấp nhận yêu cầu. Dùng thao tác nguyên tử ở kho dữ liệu phù hợp: transaction với điều kiện cập nhật, atomic increment có kiểm tra ngưỡng, hoặc script nguyên tử trên hệ thống lưu trữ bộ đếm.

Ví dụ logic giữ chỗ quota:

~~~text
BEGIN TRANSACTION
  đọc quota của tenant và chu kỳ hiện tại
  nếu used + reserved + requested > limit:
      ROLLBACK và từ chối
  ngược lại:
      reserved = reserved + requested
      ghi reservation_id duy nhất
COMMIT
~~~

Đây là mô tả logic, không phải cú pháp SQL dùng trực tiếp. Cần bảo đảm việc kiểm tra và tăng bộ đếm nằm trong cùng transaction hoặc một thao tác nguyên tử tương đương. Khi dùng cache phân tán, phải xác định hành vi khi key hết hạn, node lỗi, đồng hồ lệch và dữ liệu phục hồi.

Không dùng số liệu phân tích có độ trễ làm nguồn quyết định quota tức thời. Dữ liệu analytics có thể tổng hợp bất đồng bộ; enforcement cần nguồn dữ liệu có tính nhất quán đủ mạnh cho chính sách đang áp dụng.

### 6.3 Xác định hành vi khi bộ giới hạn lỗi

Fail-open cho phép yêu cầu đi qua khi hệ thống quota lỗi; fail-closed từ chối yêu cầu. Không có lựa chọn duy nhất đúng cho mọi endpoint:

- Với thao tác rẻ, ít rủi ro và cần tính sẵn sàng cao, có thể dùng hạn mức cục bộ dự phòng trong thời gian ngắn.
- Với thao tác tạo chi phí lớn, gửi thông báo hàng loạt hoặc làm thay đổi trạng thái quan trọng, nên từ chối có kiểm soát hoặc đưa vào hàng đợi giới hạn khi không thể xác minh hạn mức.
- Với giới hạn bảo vệ năng lực toàn hệ thống, cần cơ chế dự phòng để lỗi của dịch vụ quota không khiến toàn bộ bảo vệ biến mất.

Quyết định phải được ghi thành chính sách cho từng nhóm endpoint, có timeout và giới hạn chờ rõ ràng. Không để request chờ vô hạn chỉ vì dịch vụ quota không phản hồi.

## 7. Kiểm soát dependency tính phí

Dependency tính phí bao gồm dịch vụ AI, SMS/email, bản đồ, tìm kiếm, xác minh danh tính, xử lý tệp, lưu trữ, thanh toán và API dữ liệu bên ngoài. Rủi ro xuất hiện khi một endpoint cho phép người gọi kiểm soát số lần gọi, kích thước đầu vào hoặc số lượng kết quả mà server gửi tới nhà cung cấp.

### 7.1 Tính chi phí khuếch đại

Giả sử một API nhận 1.000 yêu cầu. Mỗi yêu cầu gọi ba lần một dịch vụ bên ngoài; mỗi lần có giá 0,002 USD. Chi phí biến đổi ước tính là:

\[
1.000 \times 3 \times 0,002 = 6\ \text{USD}
\]

Nếu một lỗi thiết kế khiến mỗi request gọi 30 lần, chi phí tăng lên 60 USD với cùng số request đầu vào. Con số thực tế còn có thể phụ thuộc kích thước dữ liệu, token, thời gian xử lý, retry và giá theo bậc. Vì vậy, cần theo dõi cả request đầu vào lẫn số lần gọi và mức tiêu thụ ở dependency.

Một mô hình đơn giản để lập ngân sách:

\[
\text{Chi phí dự kiến}
= \text{số request}
\times \text{số lần gọi trung bình mỗi request}
\times \text{chi phí trung bình mỗi lần gọi}
\]

Với dịch vụ tính theo token hoặc dung lượng, thay “chi phí trung bình mỗi lần gọi” bằng mô hình tính phí tương ứng và đo đầu vào/đầu ra riêng.

### 7.2 Giảm số lần gọi và giới hạn đầu vào

- Cache kết quả có thể tái sử dụng; xác định TTL, phạm vi tenant và quy tắc làm mới để tránh trả nhầm dữ liệu giữa khách hàng.
- Gộp nhiều thao tác thành batch khi nhà cung cấp hỗ trợ và khi việc gộp không làm lộ dữ liệu giữa tenant.
- Khử trùng lặp các yêu cầu giống nhau đang chạy; nhiều request đồng thời có thể cùng chờ một kết quả thay vì gọi nhà cung cấp nhiều lần.
- Giới hạn kích thước prompt, số tài liệu, số ảnh, số trang, số người nhận, số địa chỉ và số kết quả.
- Đặt giới hạn đầu ra; một request không được phép yêu cầu nhà cung cấp tạo kết quả không giới hạn.
- Dùng model hoặc gói dịch vụ phù hợp với mức chất lượng cần thiết; không mặc định chuyển mọi yêu cầu sang lựa chọn đắt nhất.
- Tách thao tác đồng bộ khỏi tác vụ dài. Trả mã tác vụ để client truy vấn trạng thái, thay vì giữ kết nối mở trong thời gian dài.

Cache phải có khóa phù hợp với quyền truy cập và ngữ cảnh dữ liệu. Không dùng cache dùng chung chỉ theo URL hoặc prompt nếu kết quả có thể chứa dữ liệu riêng của tenant hay người dùng.

### 7.3 Timeout, retry và circuit breaker

Retry giúp phục hồi lỗi tạm thời nhưng cũng có thể nhân chi phí và tạo retry storm. Cần:

- Chỉ retry lỗi tạm thời có khả năng phục hồi; không retry lỗi xác thực, dữ liệu không hợp lệ hoặc quota đã hết.
- Giới hạn số lần retry, tổng thời gian retry và tổng ngân sách retry cho mỗi request hoặc tác vụ.
- Dùng exponential backoff kèm jitter để nhiều instance không thử lại cùng thời điểm.
- Tôn trọng Retry-After của nhà cung cấp nếu có, đồng thời vẫn áp dụng giới hạn retry nội bộ.
- Đặt timeout kết nối và timeout toàn thao tác; timeout ở client không có nghĩa nhà cung cấp đã hủy công việc.
- Dùng circuit breaker để tạm ngừng gọi dependency đang lỗi liên tục, tránh làm cạn connection pool và chi phí vô ích.
- Dùng bulkhead hoặc pool riêng để sự cố của một dependency không chiếm hết tài nguyên phục vụ các luồng khác.

Chỉ retry thao tác có ngữ nghĩa an toàn. Với thao tác tạo giao dịch, gửi tin nhắn hoặc tạo tài nguyên, dùng idempotency key và cơ chế đối soát để tránh tác động lặp. Nếu nhà cung cấp không hỗ trợ idempotency, cần lưu trạng thái yêu cầu và xử lý tình huống không rõ kết quả sau timeout trước khi gửi lại.

### 7.4 Bảo vệ đường gọi URL do người dùng cung cấp

Một endpoint tải ảnh, xem trước liên kết hoặc nhập dữ liệu từ URL có thể biến server thành công cụ gọi mạng và tiêu thụ băng thông, CPU hoặc dịch vụ tính phí. Chỉ cho phép scheme và đích đến cần thiết; ưu tiên danh sách host cho phép. Chặn địa chỉ loopback, private, link-local và metadata của cloud; kiểm tra lại địa chỉ sau phân giải DNS và tại thời điểm kết nối để hạn chế DNS rebinding. Giới hạn redirect, thời gian, số byte tải về và loại nội dung; kiểm soát egress ở tầng mạng.

Không chỉ kiểm tra chuỗi URL ban đầu rồi tin mọi redirect. Không cho phép URL tùy ý quyết định nơi server kết nối. Đây vừa là kiểm soát SSRF vừa là kiểm soát tài nguyên và chi phí dependency.

## 8. Giới hạn kích thước và độ phức tạp của yêu cầu

Rate limit không thể thay thế giới hạn trên từng request. Một request duy nhất vẫn có thể làm cạn tài nguyên nếu đầu vào quá lớn hoặc biểu thức truy vấn quá phức tạp.

Với API danh sách và tìm kiếm:

- Giới hạn page size tối đa; không cho phép client yêu cầu toàn bộ dữ liệu bằng một tham số limit rất lớn.
- Ưu tiên cursor pagination cho tập dữ liệu lớn hoặc thay đổi liên tục.
- Giới hạn số bộ lọc, độ sâu quan hệ, số trường sắp xếp và thời gian truy vấn.
- Kiểm soát GraphQL query depth, complexity, alias và số lượng node; giới hạn cả batch request.
- Đặt timeout ở tầng ứng dụng và cơ sở dữ liệu; hủy công việc khi client ngắt kết nối nếu an toàn.

Với upload và xử lý tệp:

- Giới hạn byte nhận được và dung lượng sau giải nén; tệp nén nhỏ có thể bung ra rất lớn.
- Giới hạn số entry trong archive, độ sâu thư mục, kích thước ảnh theo pixel và thời gian giải mã.
- Kiểm tra loại nội dung thực tế, không chỉ tin phần mở rộng hoặc Content-Type do client gửi.
- Xử lý theo luồng khi có thể; tránh đọc toàn bộ tệp lớn vào bộ nhớ.
- Đưa quét virus hoặc chuyển đổi tệp vào worker có concurrency và timeout riêng.
- Áp dụng quota lưu trữ, thời gian lưu và giới hạn tải xuống/egress.

Với biểu thức tìm kiếm, bộ lọc và nội dung do người dùng cung cấp, tránh các thao tác có độ phức tạp không giới hạn, chẳng hạn regular expression dễ gây catastrophic backtracking. Nên giới hạn độ dài đầu vào, dùng engine an toàn hoặc timeout thực thi.

## 9. Phản hồi API khi vượt giới hạn

Khi client vượt rate limit hoặc quota, có thể trả HTTP **429 Too Many Requests**. Nếu có thể, gửi Retry-After để client biết khi nào nên thử lại. Ví dụ:

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 30
~~~

~~~json
{
  "code": "RATE_LIMIT_EXCEEDED",
  "message": "Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau.",
  "retryAfterSeconds": 30
}
~~~

Với quota theo chu kỳ đã dùng hết, thông điệp có thể giải thích chu kỳ hoặc hướng dẫn xem mức sử dụng nếu chính sách sản phẩm cho phép. Không trả thông tin nội bộ như số dư của tenant khác, ngưỡng chống gian lận, khóa dependency hoặc chi tiết cấu hình bảo vệ.

Chọn mã trạng thái theo nguyên nhân:

- **429:** chủ thể đã vượt giới hạn tần suất hoặc giới hạn sử dụng.
- **413 Payload Too Large:** nội dung request vượt kích thước cho phép.
- **503 Service Unavailable:** hệ thống tạm thời không đủ năng lực hoặc dependency không sẵn sàng và yêu cầu không thể được xử lý.
- **408 Request Timeout:** thời gian nhận request đã vượt ngưỡng phù hợp.

Không trả 200 với một kết quả thành công giả khi thao tác đã bị từ chối. Với tác vụ bất đồng bộ, chỉ trả 202 Accepted sau khi hệ thống đã chấp nhận và ghi nhận tác vụ vào hàng đợi bền vững; nếu hàng đợi đầy, từ chối có kiểm soát.

Client nên tôn trọng Retry-After, dùng backoff có jitter và tránh vòng lặp retry liên tục. API cần tài liệu hóa giới hạn, đơn vị quota và cách kiểm tra mức sử dụng để tích hợp có thể xử lý đúng.

## 10. Ví dụ thiết kế: API xuất báo cáo

Giả sử endpoint POST /reports/exports cho phép người dùng tạo tệp CSV từ dữ liệu của một dự án. Một request có thể quét nhiều bảng, tạo tệp lớn, lưu tệp và gửi thông báo khi hoàn tất. Chính sách có thể gồm:

| Phạm vi | Kiểm soát |
|---|---|
| Người dùng | Xác thực và kiểm tra quyền truy cập dự án |
| Tenant | Quota số lần xuất trong ngày và tổng dung lượng xuất |
| Một request | Giới hạn bộ lọc, khoảng thời gian và số dòng |
| Một tenant | Giới hạn số tác vụ xuất đồng thời |
| Toàn hệ thống | Giới hạn tổng worker và độ dài hàng đợi |
| Lưu trữ | TTL cho tệp, quota dung lượng và giới hạn tải xuống |
| Thông báo | Chống gửi lặp, quota và giới hạn retry |

Luồng xử lý:

1. Xác thực người gọi; lấy tenant và user từ principal đáng tin cậy.
2. Kiểm tra quyền trên dự án và xác thực các tham số truy vấn.
3. Tính mức tiêu thụ ước tính từ khoảng thời gian, bộ lọc và số dòng tối đa.
4. Giữ chỗ quota và một slot concurrency của tenant bằng thao tác nguyên tử.
5. Ghi tác vụ cùng idempotency key vào hàng đợi có giới hạn. Nếu không ghi được, giải phóng reservation theo quy tắc đã định.
6. Worker kiểm tra reservation, chạy truy vấn có timeout và giới hạn dòng, sau đó ghi tệp vào vùng lưu trữ riêng của tenant.
7. Ghi nhận dung lượng và mức dùng thực tế; giải phóng slot concurrency.
8. Gửi thông báo qua adapter có quota, timeout, idempotency và retry budget.
9. Hết TTL thì xóa tệp và cập nhật dung lượng đã giải phóng.

Luồng này xử lý cả quyền nghiệp vụ, quota tích lũy, concurrency, năng lực hệ thống, lưu trữ và chi phí thông báo. Nếu chỉ giới hạn số POST theo IP, một người dùng vẫn có thể tạo nhiều báo cáo lớn qua nhiều IP hoặc nhiều người dùng trong cùng tenant có thể làm cạn worker.

## 11. Kiểm thử kiểm soát tài nguyên

Kiểm thử cần xác nhận cả trường hợp bình thường, ranh giới và tình huống lỗi:

| Kiểu kiểm thử | Nội dung cần xác minh |
|---|---|
| Boundary test | Yêu cầu ngay dưới, đúng bằng và vượt ngưỡng được xử lý đúng |
| Burst test | Burst được phép trong bucket; lưu lượng kéo dài không vượt tốc độ trung bình |
| Concurrency test | Nhiều request đồng thời không vượt quota do race condition |
| Tenant isolation | Tenant A không dùng hết quota hoặc đọc reservation của tenant B |
| Identity test | Đổi IP, dùng chung NAT hoặc thay API key không làm sai phạm vi quota |
| Input abuse | Page size, batch, query depth, upload và archive đều bị giới hạn |
| Dependency failure | Timeout, 429, 5xx và mất kết nối không tạo retry vô hạn |
| Idempotency test | Gửi lặp không tạo tác vụ, giao dịch hoặc khoản tính phí trùng |
| Queue saturation | Hàng đợi đầy được từ chối có kiểm soát; không tăng bộ nhớ vô hạn |
| Budget test | Reservation, settlement và refund không làm âm hoặc vượt ngân sách |
| Failover test | Hành vi khi kho quota hoặc dịch vụ giới hạn không sẵn sàng đúng chính sách |

Trong kiểm thử tải, theo dõi số request đầu vào cùng số truy vấn, số lần gọi dependency, CPU, bộ nhớ, queue depth và chi phí ước tính. Một bài test chỉ xác nhận API trả 429 chưa chứng minh được hệ thống đã ngăn khuếch đại ở phía sau.

## 12. Giám sát và phát hiện lạm dụng

Theo dõi theo endpoint, tenant, client, dependency và khoảng thời gian:

- Tỷ lệ request được chấp nhận và bị từ chối; số phản hồi 429, 413 và 503.
- Mức sử dụng quota, phần trăm budget đã tiêu thụ và tốc độ cạn ngân sách.
- Số lần gọi dependency trên mỗi request nghiệp vụ; số token, byte hoặc đơn vị tính phí.
- Chi phí trung bình và phân vị cao theo endpoint/tenant; phát hiện tenant có mức tăng đột biến.
- Độ dài hàng đợi, tuổi tác vụ lâu nhất, concurrency và tỷ lệ tác vụ thất bại.
- Số lần retry, circuit breaker mở, timeout và tỷ lệ lỗi theo nhà cung cấp.
- CPU, bộ nhớ, connection pool, dung lượng lưu trữ và băng thông.

Đặt cảnh báo theo ngưỡng và xu hướng, chẳng hạn budget sắp chạm trần, số lần gọi dependency trên mỗi request tăng bất thường, hàng đợi tăng liên tục hoặc một tenant chiếm tỷ lệ lớn năng lực dùng chung. Ngưỡng cần phù hợp với mô hình sử dụng bình thường để tránh cảnh báo giả.

Log nên có correlation ID, endpoint, tenant ID nội bộ, policy ID, reservation ID, số đơn vị tiêu thụ và kết quả quyết định. Không ghi API key, access token, prompt chứa dữ liệu nhạy cảm hoặc nội dung tệp vào log chỉ để phục vụ thống kê quota. Dùng metric có nhãn được kiểm soát; không đưa user ID, URL tùy ý hoặc giá trị đầu vào không giới hạn thành label vì cardinality cao cũng có thể gây quá tải hệ thống giám sát.

Khi phát hiện lạm dụng, đội vận hành có thể hạ hạn mức tạm thời, tắt riêng tính năng đắt, chặn client bị xâm phạm, giảm concurrency, dừng retry hoặc chuyển sang chế độ suy giảm. Mỗi biện pháp nên có phạm vi, thời hạn, người chịu trách nhiệm và cách khôi phục rõ ràng.

## 13. Các lỗi thiết kế thường gặp

1. **Chỉ giới hạn theo IP:** bỏ sót lạm dụng có xác thực và gây ảnh hưởng người dùng chung mạng.
2. **Một giới hạn cho mọi endpoint:** không phản ánh chênh lệch chi phí giữa đọc dữ liệu và xử lý nặng.
3. **Chỉ đếm request:** bỏ qua fan-out, số dòng quét, token, byte và retry ở phía sau.
4. **Kiểm tra quota không nguyên tử:** nhiều request đồng thời cùng vượt ngưỡng.
5. **Hàng đợi không có giới hạn:** chuyển quá tải sang bộ nhớ và worker.
6. **Retry vô hạn hoặc retry ở nhiều tầng:** khuếch đại lưu lượng và hóa đơn khi dependency gặp sự cố.
7. **Không có budget theo tenant:** một khách hàng có thể tiêu thụ ngân sách dùng chung.
8. **Tin dữ liệu giới hạn do client gửi:** client có thể thay tenant ID, user ID hoặc mức tiêu thụ để né chính sách.
9. **Không tính trường hợp timeout mơ hồ:** server có thể đã thực hiện thao tác dù client không nhận được phản hồi.
10. **Không giám sát chi phí thực tế:** phát hiện sự cố khi hóa đơn hoặc hạn mức nhà cung cấp đã tăng mạnh.

## 14. Quy trình xây dựng chính sách cho một endpoint

Khi bổ sung hoặc rà soát endpoint, có thể dùng trình tự sau:

1. Mô tả hành động nghiệp vụ và dữ liệu mà endpoint truy cập; xác định principal và quyền trên từng đối tượng.
2. Vẽ các bước xử lý phía sau, gồm truy vấn, queue, storage và dependency bên ngoài.
3. Ước tính chi phí cho một request ở mức nhỏ, trung bình và cực đại; tìm các điểm có thể khuếch đại.
4. Chọn đơn vị giới hạn phù hợp: request, token, byte, dòng dữ liệu, tác vụ, người nhận, tiền hoặc thời gian xử lý.
5. Đặt rate limit, quota, budget, concurrency và capacity limit theo đúng chủ thể.
6. Xác định cách giữ chỗ, quyết toán, hoàn quota, xử lý idempotency và lỗi của kho giới hạn.
7. Quy định HTTP status, Retry-After và nội dung lỗi an toàn cho client.
8. Kiểm thử burst, đồng thời, tenant isolation, dependency failure và tình huống vượt ngân sách.
9. Thiết lập metric, cảnh báo, log và quy trình ứng phó khi có lạm dụng.
10. Rà soát định kỳ dựa trên mức sử dụng thực tế, thay đổi hợp đồng nhà cung cấp và năng lực hệ thống.

## 15. Checklist rà soát

- [ ] Đã xác định principal, tenant, client và đối tượng nghiệp vụ cần áp dụng giới hạn.
- [ ] Đã phân loại endpoint theo chi phí và mức độ ảnh hưởng khi bị lạm dụng.
- [ ] Có giới hạn cho tần suất, tổng quota, chi phí, concurrency và kích thước/độ phức tạp khi cần.
- [ ] Bộ đếm và reservation được cập nhật nguyên tử trong môi trường nhiều instance.
- [ ] Có giới hạn cho queue, worker, timeout, retry và số lần gọi dependency.
- [ ] Có idempotency hoặc cơ chế chống tác động lặp cho thao tác có side effect.
- [ ] Có chính sách rõ khi dịch vụ quota hoặc dependency không sẵn sàng.
- [ ] Phản hồi 429/413/503 phù hợp và client có hướng dẫn retry an toàn.
- [ ] Có metric về mức tiêu thụ và chi phí thực tế; log không chứa bí mật.
- [ ] Đã kiểm thử burst, race condition, tenant isolation, input cực đại và sự cố dependency.

Kiểm soát tài nguyên hiệu quả bắt đầu từ việc hiểu một endpoint thực sự tiêu thụ những gì. Khi giới hạn được gắn với đúng danh tính, đúng đối tượng, đúng đơn vị chi phí và được thực thi xuyên suốt gateway, service, worker cùng dependency adapter, API có thể duy trì tính sẵn sàng và công bằng ngay cả khi gặp lưu lượng bất thường hoặc hành vi cố ý lạm dụng.
