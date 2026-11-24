# Distributed limiter state

Một giới hạn “mỗi tài khoản chỉ được gửi một số yêu cầu trong một khoảng thời gian” cần có trạng thái để nhớ những yêu cầu đã xảy ra. Khi dịch vụ khôi phục chạy trên nhiều instance, trạng thái đó phải phản ánh cùng một ngân sách thay vì mỗi instance tự cấp một ngân sách riêng.

**Distributed limiter state** là dữ liệu và cơ chế phối hợp dùng để đưa ra quyết định giới hạn trong hệ thống phân tán. Bài toán không chỉ là đặt một bộ đếm vào Redis hoặc database. Cần xác định ai có quyền cập nhật, thao tác nào phải nguyên tử, dữ liệu tồn tại bao lâu và hệ thống sẽ làm gì khi không biết chắc kết quả của một lần cập nhật.

Trong khôi phục tài khoản, sai lệch trạng thái có thể khiến SMS bị gửi quá mức, mã được thử thêm nhiều lần hoặc người hợp lệ bị hạn chế không đúng. Mức bảo đảm cần được chọn theo ý nghĩa của hành động, không chỉ theo tốc độ xử lý.

## 1. Vì sao trạng thái cục bộ không biểu diễn ngân sách chung?

Giả sử một policy minh họa cho phép tối đa 5 lần gửi trong một cửa sổ cho cùng một đích nhận. Dịch vụ có 3 instance, mỗi instance giữ bộ đếm riêng.

Nếu request được phân phối đều, cả ba instance có thể cho phép 5 lần, tạo ra tổng cộng 15 lần gửi. Khi autoscaling thêm instance hoặc tiến trình khởi động lại, ngân sách cục bộ có thể xuất hiện thêm.

Các con số này chỉ minh họa tác động của việc tách trạng thái, không phải ngưỡng khuyến nghị cho khôi phục.

~~~text
                     ┌─ Instance A: counter A
Các request cùng đích ├─ Instance B: counter B
                     └─ Instance C: counter C

Nếu A, B, C không cùng phối hợp:
  mỗi nơi có thể cho rằng ngân sách vẫn còn.
~~~

Sticky session không giải quyết đầy đủ vấn đề. Client có thể thay kết nối, một đường API khác có thể gọi tới instance khác, và failover có thể chuyển lưu lượng sang nơi chưa có lịch sử.

Trạng thái cục bộ vẫn có ích để bảo vệ tài nguyên của chính instance hoặc giảm tải đầu vào. Cần gọi đúng phạm vi của nó, thay vì coi đó là giới hạn toàn hệ thống.

## 2. Trạng thái nào cần được chia sẻ?

Trước khi chọn kho dữ liệu, hãy định nghĩa ngữ nghĩa của ngân sách:

| Loại ngân sách | Dữ liệu cần biểu diễn | Điều có thể sai nếu mất trạng thái |
| --- | --- | --- |
| Yêu cầu bắt đầu khôi phục | Số yêu cầu theo thực thể và thời gian | Dò hoặc tạo yêu cầu quá mức |
| Gửi email, SMS hoặc cuộc gọi | Lượt gửi đã cấp quyền, đã giữ chỗ hoặc đã thực hiện | Khuếch đại tác dụng phụ và chi phí |
| Thử OTP hoặc mã dự phòng | Lịch sử lần thử theo phạm vi bảo mật | Có thêm cơ hội đoán bằng chứng |
| Resend trong giao dịch | Lần gửi gần nhất, thời điểm được gửi tiếp | Gửi dồn hoặc chặn người dùng quá lâu |
| Ngân sách nhà cung cấp | Phần tài nguyên đã phân bổ hoặc tiêu thụ | Vượt khả năng xử lý hoặc chi phí dự kiến |
| Idempotency của thao tác | Quan hệ giữa thao tác và kết quả đã ghi nhận | Retry làm tính phí hoặc thực hiện lặp |

Không phải tất cả dữ liệu trên phải nằm trong cùng một kho. Một limiter chống tải có thể chấp nhận sai số mà bộ đếm lần thử bảo mật không chấp nhận.

Trạng thái token đã dùng, challenge đã tiêu thụ và session bị thu hồi có ý nghĩa riêng. Không gộp chúng vào một cache bộ đếm rồi mặc nhiên cho phép reset khi cache biến mất.

## 3. Định danh ổn định quyết định khả năng chia sẻ

Hai instance chỉ chia sẻ ngân sách nếu chúng tính ra cùng một thực thể và cùng một quy tắc.

Một khóa khái niệm có thể gồm:

~~~text
namespace / tenant / operation / subjectType / subjectReference
~~~

Ví dụ, giới hạn gửi SMS và giới hạn thử OTP cần mục đích riêng. Ngân sách của tenant này cũng không được vô tình dùng chung với tenant khác.

Các yếu tố cần thống nhất:

- Quy tắc chuẩn hóa định danh của hệ thống tài khoản.
- Nguồn xác định tenant và địa chỉ mạng đáng tin.
- Cách ánh xạ các endpoint tới cùng một thao tác nghiệp vụ.
- Đơn vị chi phí, cửa sổ thời gian và thuật toán.
- Cách diễn giải dữ liệu khi policy hoặc schema thay đổi.

Không tự sửa email bằng quy tắc của một nhà cung cấp khác. Không tin header địa chỉ mạng do client tùy ý khai báo.

Có thể dùng HMAC cho tham chiếu định danh trong tên khóa để tránh đặt email hoặc số điện thoại thô vào kho limiter. Tham chiếu đó vẫn có khả năng liên kết và cần được bảo vệ.

Thay secret HMAC hoặc đổi namespace có thể làm cùng một thực thể nhận một khóa mới và được cấp lại ngân sách. Việc luân chuyển khóa cần kế hoạch chuyển trạng thái; không chỉ đổi cấu hình rồi coi lịch sử cũ không còn liên quan.

## 4. Điểm quyết định phải bao gồm kiểm tra và cập nhật

Mẫu xử lý dưới đây có race condition dù mọi instance đọc cùng một Redis:

~~~text
A đọc số lượt còn lại: 1
B đọc số lượt còn lại: 1

A cho phép và ghi còn 0
B cũng cho phép và ghi còn 0
~~~

Kết quả cuối vẫn là 0 nhưng hai thao tác đã được cấp quyền.

Cần một thao tác có ngữ nghĩa tương đương:

~~~text
tryAcquire(key, cost):
  đọc trạng thái hiện tại
  áp dụng quy tắc thời gian và policy
  kiểm tra ngân sách
  nếu đủ: trừ hoặc dành ngân sách
  ghi trạng thái và thời hạn phù hợp
  trả quyết định
~~~

Phần quyết định này phải được điều phối nguyên tử trong phạm vi mà policy yêu cầu, chẳng hạn bằng transaction với khóa phù hợp, cập nhật có điều kiện hoặc logic thực thi tại kho dữ liệu.

Redis cung cấp thực thi Lua script nguyên tử; trong lúc script chạy, các hoạt động khác trên server bị chặn. Đây là công cụ để kết hợp đọc và ghi, không phải lý do đặt công việc dài hoặc không giới hạn vào script. Xem [Redis: Scripting with Lua](https://redis.io/docs/latest/develop/programmability/eval-intro/).

Tính nguyên tử ở kho limiter không bao trùm một lần gọi SMS bên ngoài hay một transaction ở database khác. Ranh giới đó cần được thiết kế riêng.

## 5. Thuật toán khác nhau cần trạng thái khác nhau

| Thuật toán | Trạng thái cốt lõi | Lưu ý trong môi trường phân tán |
| --- | --- | --- |
| Fixed window | ID cửa sổ và bộ đếm | Tăng bộ đếm phải phối hợp; biên cửa sổ có thể tạo burst |
| Sliding log | Các sự kiện trong khoảng xét | Cần xóa dữ liệu cũ và giới hạn kích thước |
| Sliding window xấp xỉ | Các bộ đếm theo khoảng cùng trọng số | Sai số phải được chấp nhận và hiểu rõ |
| Token bucket | Số token hiện tại và mốc refill | Tính refill, trừ token và ghi mốc phải nhất quán |
| Khoảng chờ resend | Thời điểm được gửi tiếp hoặc lần gửi đã ghi nhận | Không để request đồng thời cùng giành một lượt |

Không thể đổi thuật toán chỉ bằng đổi tên cấu hình nếu dữ liệu cũ vẫn được diễn giải theo thuật toán trước.

Với bộ đếm fixed window, cần định nghĩa rõ đang đếm mọi lần thử hay chỉ thao tác được cấp quyền. Tăng cả request bị từ chối có thể đúng với ngân sách chống thăm dò, nhưng không có cùng ý nghĩa với “đã gửi bao nhiêu SMS”.

## 6. Ví dụ token bucket với thời gian do hệ thống kiểm soát

Mô hình dưới đây minh họa một bucket có capacity, refill rate và cost. Nó không phải mã thư viện hoàn chỉnh:

~~~text
Trong một thao tác nguyên tử:

  kiểm tra policy và cost hợp lệ
  state = đọc bucket

  nếu bucket thực sự được phép khởi tạo:
      tokens = capacity
      lastRefill = trustedNow

  effectiveNow = max(trustedNow, lastRefill)
  elapsed = effectiveNow - lastRefill

  available = min(capacity, tokens + elapsed * refillRate)

  nếu available >= cost:
      available = available - cost
      decision = ALLOW
  ngược lại:
      decision = DENY

  ghi available và effectiveNow
  đặt thời hạn lưu theo ngữ nghĩa bucket
  trả decision
~~~

Thời gian do client gửi không được quyết định refill. Các instance cần dùng nguồn thời gian hoặc cơ chế thời gian được thiết kế nhất quán cho điểm quyết định.

Giữ mốc không lùi giúp tránh một lớp lỗi do đồng hồ lùi, nhưng không xử lý mọi vấn đề về clock. Nếu đồng hồ có thẩm quyền nhảy xa về phía trước, bucket có thể được refill sớm. Kiến trúc cần xét cả sai lệch đồng hồ và hành vi của kho dữ liệu khi đổi node.

Đơn vị tính cũng phải nhất quán. Trộn giây với mili giây hoặc làm tròn token khác nhau giữa các phiên bản có thể tạo ra mức cấp quyền ngoài dự kiến. Nếu dùng đơn vị nguyên để biểu diễn phần nhỏ của token, phải xác định giới hạn và cách làm tròn.

## 7. TTL là một phần của policy

TTL không chỉ là tối ưu dọn bộ nhớ. Khi một khóa biến mất, hệ thống thường khởi tạo trạng thái mới; điều đó có thể cấp lại quyền.

### Fixed window

Thời hạn lưu cần bao phủ cửa sổ mà bộ đếm đại diện. Nếu mỗi lần đọc đều vô tình đẩy thời điểm hết hạn ra xa, policy có thể biến từ cửa sổ cố định thành một dạng chờ kéo dài.

### Token bucket

Nếu khóa hết hạn khi bucket vẫn chưa refill đầy, việc khởi tạo lại với capacity đầy sẽ cấp thêm ngân sách.

Một cách suy nghĩ là chỉ xóa khi trạng thái không còn khác với một bucket được phép khởi tạo đầy. Với refill rate dương và policy không đổi, thời điểm bucket tự đầy phụ thuộc số token còn thiếu. Khoảng lưu cần xét điểm đó cùng yêu cầu vận hành của hệ thống.

### Bộ đếm lần thử bằng chứng

Thời gian giữ trạng thái phải phù hợp vòng đời bằng chứng và policy tổng hợp. Nếu giao dịch hoặc token vẫn còn giá trị nhưng bộ đếm biến mất sớm, bên gọi có thể được thử thêm.

Không đồng nhất “không tìm thấy khóa” với “chưa từng có yêu cầu”. Khóa có thể biến mất do hết hạn đúng policy, eviction, thao tác quản trị hoặc mất dữ liệu. Những nguyên nhân đó có ý nghĩa rất khác với một giới hạn bảo mật.

Tương tự, không nên để mọi request bị từ chối tự kéo dài thời gian hạn chế vô hạn. Người ngoài có thể lợi dụng việc đó để giữ nạn nhân trong trạng thái không thể khôi phục.

## 8. Replication và failover có thể làm mất lịch sử

Một primary có thể ghi nhận lượt đã tiêu thụ nhưng replica chưa nhận được cập nhật. Nếu failover diễn ra trong khoảng đó, primary mới có thể phục vụ trạng thái cũ.

~~~text
Primary P: đã cấp lượt, trạng thái mới là hết ngân sách.
Replica R: vẫn còn bản cũ cho rằng có thể cấp thêm.

P gặp sự cố.
R được nâng lên.
Request tiếp theo có thể được cấp theo lịch sử thiếu.
~~~

Redis sử dụng replication bất đồng bộ. Tài liệu cũng nêu rằng WAIT không biến các instance thành một hệ thống có strong consistency; ghi đã được xác nhận vẫn có thể bị mất khi failover tùy cấu hình. Tham khảo [Redis replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/).

Điều này dẫn tới một quyết định kiến trúc:

- Với bảo vệ tải, có thể chấp nhận một mức sai lệch được đánh giá rõ và có lớp giới hạn bổ sung.
- Với giới hạn số lần thử bảo mật hoặc ngân sách cần bảo đảm nghiêm ngặt, cần kho có bảo đảm phù hợp hoặc một ranh giới kiểm soát bền vững bổ sung.
- Không suy ra một cận sai lệch chắc chắn chỉ từ việc đã bật replica; lỗi lặp lại và phân vùng mạng có thể làm giả định đơn giản không còn đúng.

Đọc replica để vẽ biểu đồ có thể phù hợp. Đọc trạng thái cũ rồi dùng nó cấp quyền mới là một quyết định khác.

## 9. Nhiều chiều giới hạn không tự trở thành một transaction

Một thao tác khôi phục có thể cần đồng thời ngân sách theo nguồn, đích nhận, tenant và toàn nhà cung cấp. Các khóa này thường được phân tán ở những nơi khác nhau.

Trong Redis Cluster, các thao tác nhiều khóa liên quan cần xét hash slot. Hash tag cho phép bố trí các khóa về cùng slot để hỗ trợ trường hợp này, nhưng gom quá nhiều dữ liệu về một slot có thể tạo điểm nóng. Xem [Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/#hash-tags).

Một cách bố trí phù hợp cho bộ đếm theo tài khoản chưa chắc phù hợp cho ngân sách toàn dịch vụ. Không thể giả định một Lua script sẽ bao trùm mọi khóa trên mọi shard.

Các lựa chọn thiết kế có thể gồm:

| Cách tiếp cận | Đánh đổi |
| --- | --- |
| Một dịch vụ điều phối quyết định chung | Có điểm phối hợp rõ nhưng cần quản lý năng lực và sẵn sàng |
| Các lớp limiter độc lập, cấp quyền chỉ khi mọi lớp cho phép | Có thể trừ ngân sách một lớp rồi bị lớp sau từ chối |
| Giữ chỗ theo từng chiều rồi xác nhận | Cần xử lý hết hạn, retry và kết quả chưa rõ |
| Phân bổ ngân sách nhỏ từ trung tâm cho các vùng | Giảm lượt gọi nhưng phải kiểm soát tổng phần đã cấp và vòng đời phân bổ |

Nếu policy đếm mọi lần thử, việc lớp đầu đã tính một request rồi lớp sau từ chối có thể là chủ ý. Nếu policy đếm tác dụng phụ được phép, cần xác định cách hạch toán khác.

Không hoàn ngân sách bằng một lệnh giảm tùy tiện. Chỉ được giải phóng đúng phần giữ chỗ còn thuộc thao tác đó, nếu không các retry đồng thời có thể tạo thêm ngân sách.

## 10. Timeout nghĩa là chưa biết, không nhất thiết là chưa cập nhật

Một request tới kho limiter có thể được thực thi nhưng phản hồi bị mất. Client thấy timeout rồi gọi lại có thể bị tính hai lần.

~~~text
Ứng dụng gửi acquire cho thao tác X.
Kho dữ liệu đã trừ ngân sách.
Phản hồi bị mất.

Ứng dụng chưa biết X đã được cấp hay chưa.
~~~

Với thao tác cần chống tính trùng, có thể dùng ID thao tác được ràng buộc với phạm vi và lưu kết quả quyết định trong khoảng thích hợp. Khi retry cùng thao tác, hệ thống tra kết quả tương ứng thay vì tự động trừ lần nữa.

ID do client cung cấp không được cho phép bỏ qua mọi giới hạn. Cần kiểm soát kích thước, phạm vi, thời gian lưu và việc tạo ID mới liên tục. Một quyết định đã cấp quyền cho một lần gửi cũng không phải giấy phép gửi lại nhiều lần.

Limiter và tác dụng phụ vẫn có hai trạng thái riêng:

- Đã cấp ngân sách chưa chứng minh SMS đã được gửi.
- Timeout từ nhà cung cấp không chứng minh SMS chưa được gửi.
- Hoàn ngân sách quá sớm có thể khiến tổng tác dụng phụ vượt policy.

Với workflow qua queue, giữ chỗ, trạng thái job và cơ chế idempotency phía thực thi cần phối hợp. Không thể suy ra “thực hiện đúng một lần” chỉ vì bộ đếm được cập nhật nguyên tử.

## 11. Chọn hành vi khi không lấy được trạng thái

Hai phản ứng cực đoan đều có rủi ro:

**Luôn cho qua:** lỗi kho limiter có thể biến endpoint gửi hoặc thử mã thành đường không giới hạn.

**Luôn chặn mọi thứ:** một sự cố thành phần có thể làm người đang giữ token hợp lệ mất khả năng hoàn tất, dù kho xác minh token vẫn hoạt động.

Hành vi nên được xác định theo thao tác:

| Thao tác | Hướng dự phòng minh họa |
| --- | --- |
| Tạo thêm lượt gửi tốn chi phí | Tạm từ chối hoặc trì hoãn theo ngân sách dự phòng đã thiết kế |
| Thử mã ngắn khi không kiểm soát được số lần thử | Không bỏ qua điều kiện chống đoán |
| Đọc trạng thái đã được bảo vệ | Có thể tiếp tục trong giới hạn tài nguyên cục bộ phù hợp |
| Dùng token ngẫu nhiên hợp lệ | Chỉ tiếp tục nếu vẫn đáp ứng policy và kiểm tra trạng thái bảo mật có thẩm quyền |
| Thay MFA hoặc passkey | Không giảm điều kiện xác minh chỉ vì limiter bị lỗi |

Bảng này là gợi ý phân loại, không phải quyền tự động cho qua một loại request.

Nếu dùng ngân sách cục bộ dự phòng, cần biết tổng số instance và thời gian nó được dùng. Mỗi instance tự có “một ít lượt” nhưng autoscaling không bị chặn có thể tạo ngân sách tổng không kiểm soát.

Phân vùng mạng cũng không nên khiến mỗi vùng tự khởi tạo toàn bộ ngân sách toàn cục. Nếu ưu tiên tiếp tục phục vụ, phải xác định rõ sai số hoặc cách phân bổ quyền đã được chấp nhận.

## 12. Triển khai policy và bảo vệ kho trạng thái

Một lần rolling deployment có thể làm phiên bản cũ và mới cùng xử lý request. Nếu mỗi phiên bản dùng namespace riêng, tài khoản có thể đồng thời nhận hai ngân sách.

Cần có chiến lược tương thích:

- Cố định định danh thực thể khi thay đổi code không đổi ý nghĩa policy.
- Ghi nhận schema hoặc phiên bản trạng thái khi cần.
- Chuyển đổi dữ liệu bằng quy tắc không tự reset lịch sử.
- Quy định phiên bản nào được phép ghi khi thuật toán thay đổi.
- Xem việc đổi capacity, thời gian cửa sổ và cost là thay đổi ngữ nghĩa.

Bản thân kho limiter cần được bảo vệ khỏi lạm dụng tài nguyên. Hạn chế độ dài đầu vào, thời gian giữ khóa và số giá trị phát sinh. Với khóa nóng, cần đánh giá năng lực điểm điều phối; với khóa phân tán tùy ý, cần tránh cardinality không giới hạn.

Không để client có quyền ghi trực tiếp bộ đếm hoặc TTL. Quyền quản trị xóa dữ liệu cũng cần được kiểm soát vì nó có thể cấp lại ngân sách.

Dữ liệu quan sát có thể gồm độ trễ quyết định, timeout, lỗi failover, số lần khởi tạo bucket, eviction và tỷ lệ người hợp lệ hoàn tất khôi phục. Không đưa email, OTP hoặc token vào nhãn metric hoặc log.

## 13. Ví dụ: resend qua hai instance và một job đến trễ

Mai mất thiết bị xác thực và yêu cầu gửi lại hướng dẫn. Hai request retry đến instance A và B.

Cả hai cùng gọi điểm quyết định cho cùng đích nhận và thao tác. Cơ chế nguyên tử chỉ cấp phần ngân sách phù hợp; nếu hai request thực chất là cùng một thao tác có idempotency được ràng buộc, chúng tham chiếu cùng kết quả thay vì tạo hai quyền gửi độc lập.

Một job đã được cấp quyền bị chậm trong queue. Khi nó chạy, hệ thống kiểm tra trạng thái giữ chỗ và điều kiện hiện tại trước khi gọi nhà cung cấp. Job đến trễ không được tự xem một lượt giữ chỗ đã hết hạn là quyền gửi vĩnh viễn.

Trong lúc đó, nếu kho limiter failover và mất lịch sử gần nhất, hệ thống xử lý theo mức bảo đảm đã chọn cho gửi thông báo. Nó không dùng sự thiếu lịch sử ấy để khởi tạo lại số lần thử OTP hoặc làm token đã dùng trở thành hợp lệ.

Ví dụ cho thấy trạng thái limiter có ý nghĩa khi gắn với cùng thực thể, cùng thuật toán và cùng ranh giới cấp quyền. Kho dùng chung, thao tác nguyên tử, thời hạn và hành vi khi lỗi phải phối hợp để giới hạn vẫn giữ được ý nghĩa khi lưu lượng đi qua nhiều tiến trình.
