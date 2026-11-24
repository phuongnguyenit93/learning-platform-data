# Promotion schedule: bảo vệ lịch khuyến mại bằng quy tắc thời gian

## Mục tiêu và phạm vi

Promotion schedule là tập quy tắc xác định một chương trình khuyến mại có thể được sử dụng vào lúc nào. Lịch này có thể là một khoảng liên tục, nhiều khung giờ trong ngày, các ngày lặp lại hoặc một chuỗi đợt mở bán.

Trong bảo mật logic nghiệp vụ, lịch khuyến mại là một điều kiện cấp quyền hưởng lợi. Kiểm tra lịch sai có thể cho phép mua trước giờ mở bán, dùng giá ưu đãi sau khi kết thúc, kéo dài suất đã giữ hoặc sử dụng lịch chưa được phê duyệt. Rủi ro vẫn tồn tại dù mọi request đều có đăng nhập và không chứa mã độc.

Một lịch an toàn cần phối hợp với trạng thái chương trình, quyền theo đối tượng, phiên bản chính sách, transaction, idempotency và xử lý bất đồng bộ. Đồng hồ đếm ngược hay cron job bật chương trình chỉ hỗ trợ trải nghiệm và vận hành; chúng không thay thế kiểm tra nghiệp vụ tại nơi ghi nhận quyền hưởng ưu đãi.

Sau bài này, bạn có thể:

- Biểu diễn khoảng hiệu lực với ranh giới rõ ràng, không tạo khe hở giữa các đợt.
- Chọn nguồn thời gian tin cậy và mốc xét điều kiện trong luồng đặt hàng.
- Phân biệt thời điểm đủ điều kiện với hạn giữ ưu đãi và hạn thanh toán.
- Xử lý múi giờ, lịch lặp, cache cũ và tác vụ chạy trễ.
- Ngăn sửa lịch trái quyền, phát lại yêu cầu và tranh chấp sát giờ kết thúc.
- Thiết kế kiểm thử tình huống tấn công logic dựa trên các bất biến thời gian.

## 1. Vì sao lịch khuyến mại là một ranh giới bảo mật?

Giả sử chương trình giảm 20% chỉ nhận lượt tham gia từ 10:00 đến trước 11:00, theo múi giờ đã công bố. Kẻ lạm dụng có thể thử:

1. Đổi giờ máy hoặc trường thời gian trong request để giả là đang trong khung giờ.
2. Giữ một báo giá trước 11:00 rồi thanh toán nhiều giờ sau.
3. Gửi request vào hàng đợi trước 11:00 nhưng để worker tạo quyền hưởng sau giờ kết thúc.
4. Phát lại request có timestamp cũ với một idempotency key mới.
5. Gọi trực tiếp endpoint checkout dù nút ưu đãi đã bị ẩn.
6. Sửa thời điểm bắt đầu, múi giờ hoặc hạn giữ qua API quản trị thiếu kiểm tra quyền.
7. Lợi dụng cache vẫn báo chương trình hoạt động sau khi lịch được rút ngắn hoặc tạm dừng.

Điểm chung là cố làm cho hệ thống công nhận một quyền hưởng ưu đãi ngoài điều kiện đã được cho phép. Phòng vệ phải nằm ở thao tác chấp nhận nghiệp vụ, không chỉ ở nơi hiển thị banner.

### 1.1. Phân biệt các loại thời hạn

| Thời hạn | Câu hỏi cần trả lời |
| --- | --- |
| Campaign window | Trong khoảng nào hệ thống được chấp nhận lượt hưởng ưu đãi mới? |
| Quote expiry | Báo giá còn tham khảo hoặc được bảo đảm đến lúc nào? |
| Reservation expiry | Một quyền đã giữ được sử dụng đến lúc nào? |
| Payment deadline | Giao dịch thanh toán cần đạt điều kiện nào trước thời điểm nào? |
| Fulfillment window | Khi nào hàng hóa hoặc dịch vụ được thực hiện? |

Các thời hạn có thể liên quan nhưng không tự đồng nhất. Một chương trình kết thúc lúc 11:00 có thể cho quyền đã giữ hợp lệ thanh toán tới 11:05. Cũng có chương trình buộc hoàn tất trước 11:00. Cả hai đều có thể là chính sách hợp lệ nếu được định nghĩa và thực thi nhất quán.

## 2. Bất biến và mô hình khoảng thời gian

### 2.1. Chọn khoảng nửa kín nửa hở

Một cách biểu diễn dễ kết hợp là:

~~~text
[S, E)

S: thời điểm bắt đầu, được tính vào khoảng
E: thời điểm kết thúc, không được tính vào khoảng

eligible(t) = (S <= t) AND (t < E)
~~~

Điều này tạo hành vi rõ ở biên:

| Thời điểm xét | Kết quả theo lịch |
| --- | --- |
| Trước S | Chưa được hưởng |
| Đúng S | Được xét hưởng |
| Giữa S và E | Được xét hưởng |
| Đúng E | Đã hết cửa sổ nhận lượt mới |
| Sau E | Đã hết cửa sổ nhận lượt mới |

“Được xét hưởng” chưa có nghĩa chắc chắn được giảm giá. Còn phải kiểm tra đối tượng, sản phẩm, ngân sách, số lượt, trạng thái quản trị và các điều kiện khác.

Hai đợt liền nhau `[10:00, 11:00)` và `[11:00, 12:00)` không cùng bao gồm thời điểm 11:00. Không cần tự tạo một khoảng hở rất nhỏ để tránh giao nhau.

### 2.2. Không biểu diễn kết thúc bằng “23:59:59.999”

Nếu chương trình có hiệu lực hết một ngày theo lịch địa phương, hãy biểu diễn điểm kết thúc bằng đầu ngày tiếp theo trong múi giờ đó.

~~~text
Bắt đầu: 00:00 ngày D
Kết thúc không bao gồm: 00:00 ngày D + 1
~~~

Một mốc kiểu 23:59:59.999 phụ thuộc độ chính xác của API, runtime và cơ sở dữ liệu. Nếu hệ thống khác giữ độ chính xác cao hơn, phần thời gian còn lại sau mốc ấy có thể bị xử lý không nhất quán.

Quy định rõ độ chính xác lưu trữ và so sánh. Không làm tròn thời điểm xét xuống phút hoặc giây chỉ để request muộn trông như còn hợp lệ.

### 2.3. Các bất biến tối thiểu

Với mỗi phiên bản lịch:

~~~text
S < E
Mọi lượt nhận ưu đãi mới có accepted_at nằm trong [S, E)
Mọi lượt được nhận gắn với đúng phiên bản lịch và chính sách
Không nhận lượt mới khi chương trình bị chặn theo chính sách quản trị
Không gia hạn quyền đã giữ chỉ vì request được gửi lại
~~~

Nếu nhiều khung giờ không được phép chồng nhau, phải bảo đảm điều đó trên phạm vi mà chương trình quy định. Nếu cho phép chồng nhau, cần quy tắc chọn hoặc cộng dồn rõ ràng; không để thứ tự duyệt bản ghi quyết định khách được giảm bao nhiêu.

Đối với chương trình không có ngày kết thúc, hãy mô hình hóa đó là một dạng chính sách được cho phép. Không ngầm coi trường kết thúc bị thiếu trong một payload hỏng là “chạy mãi mãi”.

## 3. Nguồn thời gian và mốc chấp nhận nghiệp vụ

### 3.1. Thời gian từ client là dữ liệu không có thẩm quyền

Không dùng các nguồn sau để quyết định khách có vào đúng khung giờ hay không:

- Đồng hồ thiết bị, JavaScript trong trình duyệt hoặc thời gian trên ứng dụng di động.
- Trường `requestedAt`, `checkoutStartedAt` hoặc `clientTimezone` do client gửi.
- Header `Date` hoặc trường tương tự mà người gọi có thể tự đặt.
- Thời điểm nằm trong URL, local storage hoặc một báo giá không được xác thực.

Client có thể gửi thời gian để chẩn đoán hoặc hiển thị. Quyết định hưởng ưu đãi phải dựa trên nguồn thời gian phía hệ thống được chọn làm nguồn có thẩm quyền.

Một token báo giá có chữ ký chống sửa vẫn có thể đã hết hạn. Chữ ký chứng minh tính toàn vẹn của nội dung, không tự chứng minh nội dung còn được phép dùng.

### 3.2. Chọn mốc xét theo ý nghĩa nghiệp vụ

Một yêu cầu có thể đi qua nhiều thời điểm:

~~~text
T1: khách bấm mua
T2: gateway nhận request
T3: request vào hàng đợi
T4: dịch vụ lấy được khóa và kiểm tra điều kiện
T5: transaction ghi nhận quyền được commit
T6: thanh toán có kết quả
~~~

Không tự động lấy T1, T2 hoặc T3 làm thời điểm hưởng ưu đãi. Nếu chính sách chọn T4, request tới gateway trước giờ kết thúc nhưng chờ khóa tới sau giờ kết thúc phải bị từ chối nhận lượt mới.

Ngược lại, nếu doanh nghiệp chọn “đã được gateway tiếp nhận hợp lệ trước hạn”, cần một bản ghi tiếp nhận bền vững và có xác thực, chống phát lại, giới hạn lưu lượng và quy tắc xử lý hàng đợi. Một timestamp trong payload không đủ để thực thi chính sách đó.

Trong bài này, các ví dụ chọn **thời điểm máy chủ kiểm tra và giữ quyền trong transaction** làm `accepted_at`. Thời gian được lấy sau khi có các khóa cần thiết. Nếu transaction rollback thì chưa có lượt được chấp nhận.

Transaction có thể commit ngay sau biên kết thúc trong khi mốc chấp nhận nằm trước biên. Đó là hệ quả của chính sách chọn mốc quyết định, cần được thống nhất với yêu cầu kinh doanh. Nếu yêu cầu là phải commit trước hạn, cần thiết kế riêng cơ chế thực thi yêu cầu đó; phép đọc đồng hồ một lần không thể chứng minh thời điểm commit tương lai.

### 3.3. Lấy một mốc nhất quán cho một quyết định

Trong một lần xét:

~~~text
t = authoritativeNow()

kiểm tra lịch bằng t
tính hạn giữ từ t
ghi accepted_at = t
ghi lý do và phiên bản đã xét
~~~

Không lấy `now()` riêng tại mỗi phép kiểm tra rồi ghi một thời điểm khác. Ngay tại biên, điều này có thể tạo bản ghi nói rằng lượt được nhận sau giờ kết thúc dù phép kiểm tra trước đó vừa thành công.

Nếu dùng thời gian cơ sở dữ liệu, cần hiểu hàm đang trả thời điểm bắt đầu transaction, bắt đầu câu lệnh hay thời điểm thực tế gọi hàm. Không mặc định mọi biểu thức tên “current time” có cùng ngữ nghĩa.

Một transaction mở từ lâu rồi chờ khóa có thể mang thời gian cũ nếu dùng nguồn được cố định từ lúc mở transaction. Chọn nguồn phù hợp với mốc chấp nhận đã định nghĩa và hạn chế transaction kéo dài.

### 3.4. Nhiều dịch vụ và đồng hồ lệch

Nếu dịch vụ báo giá, checkout và thanh toán tự xét bằng đồng hồ riêng, cùng một request có thể được cho phép ở nơi này và từ chối ở nơi khác.

Nên chỉ định nơi quyết định nhận lượt mới, ghi lại kết quả bền vững, rồi để các dịch vụ sau kiểm tra quyền đã được cấp và hạn của quyền đó. Các đồng hồ vẫn cần được đồng bộ và theo dõi sai lệch, nhưng không dùng việc “đồng hồ chắc gần giống nhau” thay cho mô hình quyền.

Đồng hồ đơn điệu hữu ích khi đo độ dài xử lý trong một tiến trình. Nó không phải timestamp lịch dùng chung giữa máy chủ hoặc qua lần khởi động lại.

Nếu nguồn thời gian không còn đủ tin cậy để xét biên, cần chính sách rõ: tạm dừng nhận lượt mới, chuyển sang nguồn đã được chấp thuận hoặc xử lý qua quy trình vận hành. Không tự bù thêm vài phút cho mọi người gọi mà không giới hạn, vì đó là một thay đổi điều kiện khuyến mại.

## 4. Múi giờ, ngày địa phương và lịch lặp

### 4.1. Tách thời gian hiển thị khỏi thời điểm tuyệt đối

Một mốc giờ địa phương không có múi giờ chưa xác định được một thời điểm tuyệt đối. Trong khi đó, số offset như `+07:00` xác định độ lệch tại mốc cụ thể nhưng không đủ mô tả đầy đủ quy tắc lịch lặp của một vùng.

Ví dụ minh họa một đợt cố định:

~~~text
Bắt đầu hiển thị: 2026-12-01 10:00, offset +07:00
Kết thúc hiển thị: 2026-12-01 11:00, offset +07:00

Bắt đầu tuyệt đối: 2026-12-01T03:00:00Z
Kết thúc tuyệt đối: 2026-12-01T04:00:00Z
~~~

Máy chủ so sánh các thời điểm tuyệt đối. Giao diện có thể hiển thị lại theo múi giờ đã công bố hoặc múi giờ người xem, nhưng không để lựa chọn hiển thị của khách làm thay đổi cửa sổ hưởng ưu đãi.

Tại API quản trị, có thể nhận mốc có offset rõ ràng hoặc nhận ngày giờ địa phương kèm định danh múi giờ. Hợp đồng phải xác định cách diễn giải và xử lý mâu thuẫn; không đoán múi giờ từ cấu hình mặc định của máy chạy dịch vụ.

### 4.2. Lịch theo ngày không phải luôn là cộng số giây cố định

Nếu yêu cầu là “toàn bộ ngày D tại múi giờ Z”, hãy lấy đầu ngày D và đầu ngày kế tiếp theo quy tắc của Z rồi chuyển thành các mốc tuyệt đối. Không mặc định mọi ngày địa phương đều dài đúng 86.400 giây.

Với lịch lặp, cần phân biệt:

| Yêu cầu kinh doanh | Cách mô hình hóa |
| --- | --- |
| Ưu đãi kéo dài đúng hai giờ thực | Khoảng thời gian tuyệt đối có độ dài hai giờ |
| Mỗi ngày từ 09:00 đến 10:00 tại vùng Z | Quy tắc theo giờ địa phương và múi giờ Z |
| Chạy vào ngày nghỉ được chỉ định | Tập ngày theo lịch và nguồn lịch đã xác định |
| Mở ba đợt cố định | Ba khoảng có định danh và phiên bản riêng |

Hai yêu cầu “cùng giờ địa phương mỗi ngày” và “mỗi 24 giờ” có thể cho kết quả khác nhau ở nơi thay đổi offset.

### 4.3. Giờ không tồn tại hoặc xuất hiện hai lần

Khi vùng áp dụng thay đổi giờ mùa, một giờ địa phương có thể:

- Không ánh xạ tới thời điểm nào vì đồng hồ nhảy qua khoảng đó.
- Ánh xạ tới một thời điểm duy nhất.
- Ánh xạ tới hai thời điểm vì đồng hồ lùi lại.

Cần quy định rõ: bỏ qua lượt không tồn tại, dịch sang giờ hợp lệ tiếp theo, từ chối cấu hình hay yêu cầu người quản trị chọn cách xử lý. Với giờ xuất hiện hai lần, phải quyết định chọn lần đầu, lần sau hoặc mở cả hai lượt riêng.

Không để thư viện tự chọn mặc định trong khi mô tả chiến dịch hứa hành vi khác. Nếu mở hai lượt, mỗi lượt cần định danh riêng; một mốc giờ địa phương dạng chuỗi không còn là khóa duy nhất.

Quy tắc múi giờ có thể được cập nhật. Với các lượt tương lai, cần biết đang dùng phiên bản quy tắc nào và có tái tạo lịch hay không. Các lượt đã phát sinh quyền hưởng ưu đãi phải giữ các mốc tuyệt đối đã ghi nhận để truy vết; không viết lại lịch sử theo quy tắc mới.

## 5. Tách trạng thái quản trị khỏi trạng thái theo đồng hồ

### 5.1. Một cờ ACTIVE không mô tả đủ điều kiện

Có thể mô hình hóa trạng thái quản trị:

~~~text
DRAFT → APPROVED → PUBLISHED
PUBLISHED → PAUSED → PUBLISHED
PUBLISHED/PAUSED → CANCELLED
~~~

Đây chỉ là mô hình ví dụ. Luồng phê duyệt có thể đơn giản hơn hoặc nghiêm ngặt hơn tùy quyền hạn của hệ thống.

Trạng thái thời gian được suy ra riêng từ lịch:

~~~text
t < S       : UPCOMING
S <= t < E  : IN_WINDOW
t >= E      : ENDED
~~~

Một chương trình chỉ nhận lượt mới khi đồng thời đáp ứng các điều kiện:

~~~text
đúng tenant và phạm vi áp dụng
AND phiên bản được phép nhận lượt đang PUBLISHED
AND không bị chặn bởi quyết định quản trị có hiệu lực
AND t thuộc ít nhất một cửa sổ hợp lệ
AND đáp ứng điều kiện đối tượng, hàng hóa, ngân sách và lượt dùng
~~~

Chương trình vẫn có thể mang trạng thái quản trị `PUBLISHED` sau giờ kết thúc; phép kiểm tra lịch sẽ từ chối lượt mới. Nhờ đó, việc cron job cập nhật nhãn “đã kết thúc” chạy chậm không tạo thêm quyền hưởng.

Tương tự, một tác vụ “bắt đầu đợt” chạy sớm không được mở bán trước S. Tác vụ chỉ được kích hoạt công việc vận hành; điều kiện thời gian vẫn phải được xét.

### 5.2. Resume không đồng nghĩa với còn hiệu lực

Nếu chương trình đang tạm dừng rồi được mở lại sau E, thao tác resume không được tự làm cửa sổ cũ sống lại. Cần kiểm tra lịch hoặc tạo một phiên bản lịch mới theo quyền hạn được cho phép.

Nếu doanh nghiệp yêu cầu một đợt đã đóng không bao giờ tự mở lại khi đồng hồ hệ thống lùi, có thể bổ sung dấu đóng cuối cùng cho phiên bản hoặc lượt lịch. Khi đã đóng theo cơ chế tin cậy, quyền nhận lượt mới không được khôi phục chỉ vì một máy chủ báo thời gian cũ. Sự cố đồng hồ cần được xử lý riêng, không tự động coi là gia hạn.

### 5.3. Phê duyệt phải gắn với đúng cấu hình

Một phê duyệt nên gắn với phiên bản hoặc dấu vân tay của cấu hình có ý nghĩa nghiệp vụ, bao gồm:

- Điểm bắt đầu, điểm kết thúc và múi giờ.
- Quy tắc lặp, các ngoại lệ và cách xử lý thời gian mơ hồ.
- Loại đối tượng, sản phẩm, ngân sách và cách cộng dồn.
- Thời hạn giữ, khoảng thanh toán bổ sung và quy tắc áp dụng cho quyền đã giữ.

Nếu người quản trị đổi giờ kết thúc sau khi được duyệt, không tiếp tục dùng phê duyệt cũ như thể nội dung chưa thay đổi.

API phải kiểm tra quyền trên chính chương trình và tenant. Quyền xem lịch không đồng nghĩa với quyền kéo dài chương trình; quyền sửa bản nháp không đồng nghĩa với quyền publish hoặc bỏ qua phê duyệt.

## 6. Báo giá, quyền giữ và cửa sổ thanh toán

### 6.1. Chọn một chính sách rõ cho quyền đã giữ

Hai chính sách phổ biến:

| Chính sách | Lượt mới | Quyền đã giữ |
| --- | --- | --- |
| Kết thúc cứng | Chỉ nhận trong [S, E) | Cũng phải hoàn thành bước được quy định trước E |
| Cho hoàn tất quyền đã giữ | Chỉ nhận trong [S, E) | Có thể hoàn tất tới hạn giữ D theo điều kiện đã công bố |

Không được vô tình biến chính sách thứ nhất thành thứ hai chỉ vì báo giá hoặc token có TTL dài hơn E.

Với chính sách cho hoàn tất quyền đã giữ, đặt:

~~~text
t: thời điểm nhận lượt hợp lệ
H: thời lượng giữ tối đa
G: khoảng cho hoàn tất thêm sau E, nếu được phép
P: hạn thanh toán của đơn, nếu có

D = min(t + H, E + G, P)
~~~

Nếu không cho hoàn tất sau E thì dùng `G = 0`. Chỉ tạo quyền khi `D > t`. Các phép tính phải có đơn vị và giới hạn rõ ràng, tránh nhầm giây với mili giây hoặc tràn số khi nhận cấu hình quá lớn.

Ví dụ:

~~~text
E = 11:00:00
t = 10:59:50
H = 5 phút
G = 2 phút
P = 11:10:00

D = min(11:04:50, 11:02:00, 11:10:00)
  = 11:02:00
~~~

Request thử lại lúc 11:01 không được lấy thời điểm mới để tính lại D. Quyền cũ vẫn có hạn 11:02. Nếu quyền hết hạn, việc tạo quyền thay thế là một quyết định mới và phải kiểm tra cửa sổ nhận lượt mới.

### 6.2. Nội dung một quyền giữ phía máy chủ

~~~text
reservation_id
tenant_id
promotion_id
schedule_revision
occurrence_id, nếu là lịch nhiều lượt
owner_id hoặc định danh phiên được phép
order_id và phiên bản nội dung đặt hàng
accepted_at
expires_at
pricing_snapshot
reserved_budget / reserved_usage
status
~~~

Quyền giữ phải được ràng buộc với đúng chủ thể và nội dung. Không cho đổi sản phẩm, số lượng hoặc đơn đích rồi tiếp tục dùng mức giảm của quyền cũ.

Một token có chữ ký có thể là cách mang định danh và dữ liệu xác thực, nhưng vẫn cần kiểm tra hết hạn, đối tượng sử dụng, mục đích và tình trạng tiêu dùng. Chữ ký không ngăn cùng token được tiêu dùng hai lần nếu không có cơ chế chống trùng phù hợp.

### 6.3. Hết hạn quyền giữ không đồng nghĩa an toàn để hoàn ngân sách

Khi chưa có lệnh thanh toán nào được gửi, hệ thống có thể hết hạn quyền theo chính sách và giải phóng phần giữ bằng một chuyển trạng thái nguyên tử.

Khi một yêu cầu thanh toán đang thực hiện hoặc kết quả còn chưa rõ, không giải phóng phần giữ chỉ vì đồng hồ đi qua D rồi cho người khác dùng hết ngân sách. Khoản thanh toán cũ có thể thành công muộn, làm tổng lợi ích vượt giới hạn.

Cần phân biệt trạng thái như `HELD`, `PAYMENT_PENDING`, `REDEEMED`, `EXPIRED` và trạng thái chờ đối soát nếu cần. Quy tắc xử lý thành công muộn phải xác định rõ mốc nào được công nhận: thời điểm khởi tạo, thời điểm thực hiện được xác minh hay thời điểm hệ thống chốt kết quả.

Không tin timestamp trong callback chưa xác thực. Nếu chính sách từ chối một thanh toán thực sự đã thu tiền, phải có luồng bù trừ hoặc giải quyết thích hợp; không chỉ bỏ qua sự kiện và coi như tiền chưa từng được thu.

### 6.4. Báo giá không tự là quyền giữ

Có thể hiển thị giá ưu đãi lúc 10:30 mà chưa giữ ngân sách hoặc lượt dùng. Nếu khách checkout lúc 11:05, báo giá ấy không chứng minh họ đã được cấp quyền trước 11:00.

API cần trả rõ báo giá chỉ tham khảo hay đã có reservation. Khi báo giá hết hiệu lực, máy chủ tính lại và yêu cầu xác nhận thay đổi theo trải nghiệm sản phẩm, thay vì âm thầm tin số tiền client gửi.

## 7. Chấp nhận ưu đãi trong một thao tác nguyên tử

### 7.1. Luồng tạo reservation

Đoạn giả mã sau minh họa chính sách nhận lượt tại lúc kiểm tra trong transaction. Các hàm thể hiện trách nhiệm cần triển khai, không phải API của một framework.

~~~text
reservePromotion(actor, orderId, promotionId, command, idempotencyKey):
    validateRequestShape(command)
    fingerprint = canonicalFingerprint(orderId, promotionId, command)

    begin transaction
        order = lockOrder(orderId)
        authorizeOrderAccess(actor, order)

        previous = findIdempotency(
            tenant = order.tenantId,
            actor = actor.id,
            action = "RESERVE_PROMOTION",
            key = idempotencyKey
        )

        if previous exists:
            requireSameFingerprint(previous, fingerprint)
            requireActorCanReadResult(actor, previous)
            commit
            return currentResult(previous)

        promotion = lockPromotionAndUsageResources(promotionId, actor)
        requireSameTenantAndAllowedScope(order, promotion)

        existing = findGrantForSameBusinessIntent(order, promotion)
        if existing exists:
            saveIdempotencyMapping(idempotencyKey, fingerprint, existing)
            commit
            return currentResult(existing)

        revision = loadCurrentApprovedPublishedRevision(promotion)
        requireNotBlockedForNewGrants(promotion)

        t = authoritativeDecisionTime()
        occurrence = selectAllowedOccurrence(revision, t)
        require(occurrence.startsAt <= t AND t < occurrence.endsAt)

        requireAudienceAndProductsEligible(actor, order, revision)
        price = calculateOnServer(order, revision)
        requireBudgetAndUsageAvailable(price, promotion, actor)

        deadline = calculateReservationDeadline(t, occurrence, revision, order)
        require(t < deadline)

        reservation = insertReservation(
            owner = actor,
            orderVersion = order.version,
            promotion = promotion.id,
            revision = revision.id,
            occurrence = occurrence.id,
            acceptedAt = t,
            expiresAt = deadline,
            pricingSnapshot = price,
            status = HELD
        )

        reserveBudgetAndUsage(reservation)
        saveIdempotencyMapping(idempotencyKey, fingerprint, reservation)
        appendAudit("PROMOTION_RESERVED", reservation)
        insertOutbox("RESERVATION_CREATED", reservation.id)

    commit

    return reservation
~~~

Các điểm cần bảo vệ:

- Mọi đường ghi dùng cùng nguyên tắc, kể cả công cụ quản trị và tác vụ tự động.
- Kiểm tra lịch, chọn phiên bản, giữ ngân sách và tạo reservation nằm trong cùng ranh giới nhất quán.
- Thay đổi lịch phải phối hợp với đường tạo reservation bằng khóa hoặc kiểm tra phiên bản nguyên tử, tránh đọc lịch cũ rồi ghi dưới lịch mới.
- Hạn mức đồng thời phải tính cả phần đang giữ lẫn phần đã tiêu dùng.
- Có khóa nghiệp vụ hoặc ràng buộc dữ liệu để không cấp hai quyền cho cùng ý định đặt hàng chỉ vì đổi idempotency key.
- Nếu transaction xung đột và phải thử lại trước khi có reservation bền vững, lần thử lại lấy mốc thời gian mới. Không dùng lại mốc cũ để lách qua giờ kết thúc.

Giả mã dùng khóa để dễ nhìn thấy ranh giới. Có thể triển khai bằng optimistic locking hoặc cập nhật có điều kiện nếu vẫn bảo vệ được cùng các bất biến. Một lần kiểm tra trước transaction rồi ghi dữ liệu sau đó không đủ.

### 7.2. Chống lỗi time-of-check to time-of-use

Một luồng dễ lỗi:

~~~text
10:59:58  Kiểm tra trong cache: khuyến mại còn hiệu lực
10:59:59  Chờ khóa ngân sách
11:00:02  Lấy được khóa và tạo reservation
~~~

Theo chính sách của bài, mốc chấp nhận ở bước giữ quyền là 11:00:02 nên phải từ chối. Kết quả cache lúc 10:59:58 chỉ là gợi ý ban đầu.

Một dạng lỗi khác:

~~~text
Đọc revision 7, thấy kết thúc 12:00
Quản trị publish revision 8, đổi kết thúc về 11:00
Request cũ tạo reservation lúc 11:30 theo revision 7
~~~

Nếu revision 8 đã được quy định có hiệu lực cho lượt mới, lần ghi dựa trên revision 7 không được thành công. Cần kiểm tra phiên bản hiện hành trong transaction hoặc dùng điều kiện cập nhật bảo đảm phiên bản chưa đổi.

Điều này khác với reservation đã được chấp nhận hợp lệ trước thay đổi: quyền cũ có thể được giữ theo chính sách đã công bố, như phần quản lý phiên bản bên dưới.

### 7.3. Tiêu dùng quyền đã giữ

Khi checkout sử dụng reservation, máy chủ cần kiểm tra:

~~~text
đúng chủ thể, tenant, đơn và phiên bản nội dung
AND trạng thái cho phép tiêu dùng
AND chưa bị tiêu dùng bởi thao tác khác
AND thỏa hạn và mốc thanh toán đã quy định
AND không thuộc trường hợp thu hồi quyền có hiệu lực
~~~

Không mặc định kiểm tra lại cửa sổ nhận lượt mới rồi từ chối mọi reservation sau E. Nếu chính sách cho hoàn tất tới D, quyền cũ được xét theo D và điều kiện của nó. Ngược lại, không coi mọi reservation là được miễn hạn của chiến dịch khi chính sách chọn kết thúc cứng.

Cạnh tranh giữa tiêu dùng và hết hạn cần được phân xử nguyên tử. Hai worker không được cùng chuyển một quyền từ HELD sang REDEEMED và EXPIRED, khiến ngân sách vừa được tiêu dùng vừa được trả lại.

## 8. Scheduler, hàng đợi và cache

### 8.1. Scheduler không cấp quyền thay cho bộ quy tắc

Các tác vụ theo lịch có thể:

- Chuẩn bị nội dung hiển thị và làm nóng cache.
- Gửi thông báo hoặc phát sự kiện bắt đầu, kết thúc.
- Dọn các quyền giữ thực sự đủ điều kiện hết hạn.
- Cập nhật trạng thái phục vụ báo cáo.

Dù tác vụ bắt đầu chưa chạy, request hợp lệ vẫn phải được xét theo nguồn dữ liệu có thẩm quyền. Dù tác vụ kết thúc chạy chậm, request ngoài cửa sổ vẫn phải bị từ chối.

Không thiết kế toàn bộ quyền hưởng dựa trên việc cron đã đổi `active = true` hay chưa. Trạng thái công việc nền có thể trễ, lặp hoặc bị gián đoạn; điều kiện lịch phải tồn tại độc lập.

### 8.2. Tác vụ cũ sau khi lịch được sửa

Một tác vụ nên mang định danh đủ rõ:

~~~text
promotion_id
schedule_revision
occurrence_id
action
scheduled_for
job_key
~~~

Trước khi tạo hiệu ứng, worker đối chiếu phiên bản và trạng thái. Nếu tác vụ revision 7 yêu cầu mở chương trình nhưng revision 8 đã hủy đợt đó, tác vụ cũ phải bỏ qua hoặc ghi nhận không còn áp dụng.

Khóa chống trùng của công việc có thể dựa trên bộ `(promotion_id, revision, occurrence_id, action)`. Một lần retry không được gửi thông báo nhiều lần hoặc gia hạn reservation. Riêng các hiệu ứng bên ngoài còn cần cơ chế chống trùng phù hợp với bên nhận.

Đối với lịch lặp, mỗi occurrence nên có định danh ổn định. Không dùng duy nhất giờ chạy thực tế của worker làm khóa, vì retry vào phút sau sẽ trông như một lượt khác.

### 8.3. Hàng đợi không bảo quản quyền chưa từng được cấp

Một message “khách đã bấm mua lúc 10:59” không tương đương reservation. Nếu worker chỉ bắt đầu xét lúc 11:01, nó phải áp dụng đúng mốc chấp nhận đã được quy định.

Nếu muốn bảo đảm quyền ở thời điểm tiếp nhận, phía tiếp nhận phải thực sự tạo một bản ghi chấp nhận bền vững, kiểm tra hạn mức và giữ tài nguyên. Đưa message vào queue mà không giữ gì chỉ dời race sang một vị trí khác.

### 8.4. Cache phục vụ đọc và quyết định ghi

Có thể cache danh sách, nội dung mô tả và giá dự kiến. Với thao tác cấp lợi ích, dữ liệu dùng để quyết định phải còn có hiệu lực theo chính sách nhất quán.

Những lựa chọn có thể áp dụng:

- Đọc phiên bản và trạng thái có thẩm quyền trong transaction tạo quyền.
- Dùng dữ liệu cache làm đầu vào tính toán, nhưng xác nhận revision hoặc epoch hiện hành khi ghi.
- Thiết kế một quyền đã cấp có hạn và phạm vi rõ ràng, rồi kiểm tra quyền đó ở bước sau.

TTL ngắn không tự bảo đảm “tạm dừng có hiệu lực ngay”. Nếu hệ thống hứa chặn ngay lượt mới, đường ghi phải kiểm tra tín hiệu chặn đủ mạnh; không tiếp tục tin cache dương tính chỉ vì nó chưa hết TTL.

## 9. Thay đổi lịch và phạm vi hiệu lực

### 9.1. Lưu phiên bản thay vì viết đè lịch sử

Mỗi thay đổi cần lưu ai thực hiện, lý do, cấu hình trước/sau, phê duyệt liên quan và mốc hiệu lực. Các reservation cũ vẫn tham chiếu phiên bản đã dùng lúc chấp nhận.

Cần phân biệt:

| Loại thay đổi | Cách xử lý cần xác định |
| --- | --- |
| Kéo dài cửa sổ cho lượt mới | Publish phiên bản mới; không tự tăng hạn mọi reservation cũ |
| Rút ngắn cửa sổ | Chặn lượt mới theo mốc hiệu lực; quyết định riêng về quyền đã giữ |
| Sửa bản nháp chưa publish | Không làm thay đổi phiên bản đang phục vụ |
| Tạm dừng | Xác định ảnh hưởng với lượt mới và quyền cũ |
| Hủy khẩn cấp | Có quy tắc thu hồi, thanh toán đang chạy và xử lý bù trừ |
| Đổi múi giờ hoặc lịch lặp | Tái xác định các lượt tương lai theo chính sách; giữ lịch sử lượt đã nhận |

Nếu chính sách giữ quyền đã cấp, không lấy việc revision hiện hành đã đổi làm lý do tự động phủ nhận mọi reservation cũ. Nếu có quyền thu hồi khẩn cấp, phải mô hình hóa điều kiện ấy và thực thi trên bước tiêu dùng tương ứng.

### 9.2. Phân quyền và phê duyệt thay đổi

Máy chủ cần từ chối các đường như:

- Nhân viên của tenant A sửa lịch của tenant B bằng cách thay ID.
- Người chỉ được sửa nội dung marketing thay thời điểm kết thúc hoặc khoảng thanh toán bổ sung.
- Người được sửa bản nháp trực tiếp publish bản chưa duyệt.
- Request cũ ghi đè một thay đổi mới bằng revision đã lỗi thời.
- Tác vụ tự động cũ mở lại chương trình đã hủy.

Có thể dùng `expected_revision` để phát hiện ghi đè. Việc khớp revision không thay thế kiểm tra quyền và phê duyệt; nó chỉ xác nhận người ghi chưa dựa trên trạng thái lỗi thời.

### 9.3. Khung giờ chồng nhau

Nếu cho phép nhiều đợt hoặc nhiều chương trình cùng áp dụng, cần xác định:

~~~text
Chọn ưu đãi tốt nhất?
Chọn theo độ ưu tiên?
Chỉ một ưu đãi trong nhóm loại trừ?
Cho cộng dồn theo thứ tự đã quy định?
Giới hạn lượt tính theo từng occurrence hay toàn chương trình?
~~~

Thời điểm biên không được làm một đơn nhận hai lần cùng một lợi ích chỉ vì hai worker chọn hai occurrence khác nhau. Khóa nghiệp vụ phải phản ánh phạm vi giới hạn, chẳng hạn theo đơn và nhóm lợi ích, thay vì chỉ chống trùng trong từng occurrence.

Với lịch không được chồng nhau, thao tác kiểm tra xung đột và publish cũng cần bảo vệ trước hai yêu cầu quản trị đồng thời. Hai transaction cùng đọc “chưa có lịch trùng” rồi cùng thêm lịch là một lỗi logic khác của cùng bài toán.

## 10. Kiểm thử tình huống tấn công logic

### 10.1. Kiểm soát thời gian trong bài kiểm thử

Tách nguồn thời gian thành một thành phần có thể thay thế trong kiểm thử. Bộ kiểm thử đặt thời gian ở trước, đúng và sau từng biên mà không phải chờ tới giờ thật.

Nguồn thời gian kiểm thử không được trở thành một tùy chọn để client sản xuất tự đặt giờ xét. Đây là khả năng do môi trường kiểm thử kiểm soát, không phải header công khai để bỏ qua lịch.

Trong bảng dưới, giả định độ chính xác thời gian là mili giây. Hệ thống thực tế phải kiểm thử theo đúng độ chính xác mà nó lưu và so sánh.

### 10.2. Ma trận kiểm thử

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| Xét tại S trừ 1 ms | Không tạo reservation hoặc giữ ngân sách |
| Xét đúng S | Có thể nhận lượt nếu các điều kiện khác hợp lệ |
| Xét tại E trừ 1 ms | Có thể nhận lượt; ghi đúng accepted_at và hạn giữ |
| Xét đúng E hoặc sau E | Không tạo quyền mới |
| Client sửa giờ, múi giờ hoặc requestedAt | Quyết định không thay đổi theo dữ liệu giả |
| Payload quản trị có S bằng hoặc sau E | Từ chối cấu hình |
| Thiếu múi giờ cho giờ địa phương theo hợp đồng yêu cầu | Không tự đoán rồi publish |
| Nhầm đơn vị giây và mili giây, thời lượng quá lớn | Bị kiểm tra và từ chối; không tạo hạn vô lý |
| Múi giờ mặc định của máy chủ thay đổi | Đợt cố định đã lưu bằng thời điểm tuyệt đối không đổi |
| Ngày địa phương có thay đổi offset | Biên ngày được tính theo múi giờ, không cộng cứng 86.400 giây |
| Giờ lặp không tồn tại hoặc xuất hiện hai lần | Hành vi khớp chính sách đã lưu; occurrence có định danh đúng |
| Request chờ khóa qua E | Xét bằng mốc sau khi có khóa; không giữ quyền từ mốc kiểm tra sơ bộ |
| Request chỉ vào queue trước E, worker chạy sau E | Không hưởng quyền cũ nếu chưa có bản ghi chấp nhận hợp lệ |
| Transaction rollback rồi thử lại sau E | Không dùng lại thời điểm cũ để nhận lượt mới |
| Gửi lại cùng khóa sau E | Trả operation cũ và trạng thái hiện tại; không tăng expires_at |
| Cùng khóa nhưng đổi đơn hoặc nội dung | Xung đột, không chuyển quyền sang đối tượng mới |
| Đổi khóa để lấy thêm quyền cho cùng ý định | Khóa nghiệp vụ ngăn cấp lặp |
| Quyền cũ đã EXPIRED được gửi lại | Không hồi sinh; muốn nhận quyền mới phải theo quy trình và lịch hiện hành |
| Hai request tranh lượt cuối cùng | Chỉ số lượt và ngân sách hợp lệ được giữ |
| Tiêu dùng và hết hạn cùng lúc | Một chuyển trạng thái hợp lệ; không vừa tiêu dùng vừa trả ngân sách |
| Thanh toán chưa rõ kết quả khi qua D | Không tự giải phóng phần giữ có thể còn phát sinh hiệu ứng |
| Cron kết thúc chạy trễ | Request ngoài cửa sổ vẫn bị từ chối |
| Job cũ chạy sau khi lịch bị hủy hoặc sửa | Không mở lại chương trình hoặc tạo hiệu ứng của revision cũ |
| Cache còn báo hợp lệ sau tạm dừng có hiệu lực | Đường ghi vẫn tuân thủ quyết định chặn có thẩm quyền |
| Sửa lịch sau khi phê duyệt | Không dùng phê duyệt cũ cho nội dung đã đổi |
| Nhân viên khác tenant sửa hoặc publish lịch | Bị từ chối, không có thay đổi hay tác vụ phát sinh |
| Hai quản trị viên publish hai lịch xung đột | Không phá quy tắc cấm chồng nhau hoặc ghi đè revision |
| Kéo dài chiến dịch sau khi có quyền giữ | Không tự gia hạn quyền cũ ngoài chính sách |
| Hai occurrence chồng nhau áp cùng lợi ích | Quy tắc loại trừ hoặc cộng dồn được thực thi một lần đúng phạm vi |
| Đồng hồ lùi sau khi lượt đã được đóng cuối cùng | Không tự mở lại nếu chính sách quy định đóng không đảo ngược |

### 10.3. Kiểm tra hiệu ứng, không chỉ mã HTTP

Sau mỗi tình huống, cần kiểm tra:

~~~text
Reservation có được tạo hay không?
accepted_at thuộc cửa sổ nào và revision nào?
expires_at có bị tăng ngoài ý muốn không?
Ngân sách đang giữ và đã tiêu dùng có đúng không?
Có bao nhiêu quyền cho cùng ý định nghiệp vụ?
Outbox có phát sinh công việc trái phép không?
Audit có giải thích được quyết định không?
~~~

Một request bị trả lỗi nhưng transaction trước đó đã giữ ngân sách vẫn là lỗi cần phát hiện. Tương tự, trả HTTP thành công cho request thử lại là hợp lệ nếu đó là đọc kết quả đã có, không phát sinh thêm lợi ích.

Với kiểm thử đồng thời, điều phối các tiến trình tới điểm tranh chấp thay vì chỉ thêm khoảng ngủ ngẫu nhiên. Cần kiểm tra sau cùng rằng giới hạn, trạng thái và liên kết quyền vẫn đúng.

## 11. Ví dụ diễn tiến sát giờ kết thúc

Chọn chính sách:

~~~text
Cửa sổ nhận lượt mới: [10:00:00, 11:00:00)
Thời gian giữ tối đa H: 5 phút
Cho hoàn tất thêm sau E: tối đa 2 phút
Hạn thanh toán khác của đơn: không sớm hơn 11:02:00
Mốc nhận lượt: kiểm tra và giữ quyền trong transaction
Mốc hoàn tất quyền: thao tác tiêu dùng hợp lệ trước expires_at
~~~

Tất cả giờ trong ví dụ cùng thuộc múi giờ đã công bố và đã được máy chủ chuyển sang mốc tuyệt đối.

| Thời điểm | Sự kiện | Quyết định |
| --- | --- | --- |
| 10:59:50 | A được giữ quyền thành công | accepted_at = 10:59:50; expires_at = 11:02:00 |
| 10:59:59 | B gửi request vào queue, chưa có reservation | Chưa có bằng chứng B đã được nhận lượt |
| 11:00:00 | C yêu cầu một quyền mới | Từ chối vì đúng biên kết thúc |
| 11:00:02 | Worker xét B lần đầu | Từ chối theo mốc chấp nhận đã chọn |
| 11:00:30 | A thử lại request giữ quyền cùng khóa | Trả quyền A đang có, không đổi hạn 11:02:00 |
| 11:01:30 | A hoàn tất tiêu dùng đúng quyền, đúng đơn và điều kiện thanh toán | Có thể thành công vì còn trước hạn giữ và chính sách cho phép |
| 11:02:10 | Request cũ của A được phát lại | Trả kết quả đã có, không tạo thêm lượt |
| Sau 11:02 | Worker dọn quyền thấy A đã tiêu dùng | Không chuyển A sang hết hạn hoặc trả lại ngân sách |

Nếu chọn chính sách kết thúc cứng thay vì chính sách trên, hạn của A tối đa là 11:00:00 và việc hoàn tất lúc 11:01:30 không được tự chấp nhận. Khác biệt phải xuất phát từ cấu hình chính sách có thẩm quyền, không từ việc endpoint nào được gọi.

## 12. Dữ liệu vận hành và truy vết

Một quyết định nhận hoặc từ chối quan trọng nên truy vết được:

~~~text
promotion_id, revision, occurrence_id
tenant_id, chủ thể và đối tượng nghiệp vụ
decision_time, nguồn thời gian được sử dụng
starts_at, ends_at, expires_at nếu có
kết quả và reason_code
reservation_id, idempotency mapping, correlation_id
~~~

Các mã lý do có thể gồm `NOT_STARTED`, `WINDOW_ENDED`, `PAUSED`, `REVISION_CHANGED`, `RESERVATION_EXPIRED` hoặc `ALREADY_REDEEMED`. Chúng giúp phân biệt lỗi lịch với hết ngân sách hay sai đối tượng.

Các tín hiệu vận hành hữu ích:

- Số lần từ chối gần biên bắt đầu hoặc kết thúc.
- Độ trễ scheduler và tuổi message trong queue.
- Tỷ lệ transaction phải thử lại vì revision đổi hoặc tranh hạn mức.
- Lượng reservation chưa giải quyết sau hạn, nhất là thanh toán chưa rõ kết quả.
- Sự khác nhau giữa giá hiển thị và kết quả xét tại checkout.
- Sai lệch thời gian hoặc việc thay đổi nguồn thời gian có thẩm quyền.

Dùng các tín hiệu này để phát hiện và giải thích sự cố. Không tự mở thêm cửa sổ khuyến mại chỉ vì tỷ lệ từ chối tăng. Nếu doanh nghiệp quyết định gia hạn, đó là một thay đổi lịch có quyền hạn, phiên bản, mốc hiệu lực và audit.

## 13. Câu hỏi tự đánh giá thiết kế

1. Một lượt mới được coi là nhận tại gateway, tại lúc giữ quyền hay tại mốc nào khác?
2. Nguồn nào cung cấp thời gian có thẩm quyền, và có thể bị client tác động không?
3. Điều gì xảy ra đúng tại S và E? Các API có cùng độ chính xác và quy tắc biên không?
4. Báo giá, reservation và thanh toán có các thời hạn riêng được mô tả rõ chưa?
5. Retry hoặc đổi idempotency key có kéo dài thời hạn hay tạo thêm quyền không?
6. Thay đổi lịch có được bảo vệ khỏi ghi đè, vượt quyền và dùng lại phê duyệt cũ không?
7. Request đang chờ khóa hoặc trong queue có thể dùng một timestamp cũ để vượt biên không?
8. Nếu cron dừng hoặc cache cũ, đường ghi có còn từ chối đúng lịch không?
9. Quyền đã giữ chịu ảnh hưởng thế nào khi lịch bị rút ngắn, tạm dừng hoặc hủy?
10. Thanh toán thành công muộn và cạnh tranh hết hạn đã có quy tắc nguyên tử, đối soát và xử lý bù trừ chưa?
