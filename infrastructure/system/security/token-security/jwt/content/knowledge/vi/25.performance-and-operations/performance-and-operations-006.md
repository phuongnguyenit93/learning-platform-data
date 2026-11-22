# Đồng bộ đồng hồ và giám sát sai lệch giữa các hệ thống

## 1. Vì sao thời gian chính xác quan trọng với JWT?

JWT thường chứa các claim thời gian như iat, nbf và exp. Issuer tạo token dựa trên đồng hồ của nó; Resource Server xác minh token dựa trên đồng hồ của chính nó. Nếu hai đồng hồ lệch nhau, một token hợp lệ có thể bị từ chối sớm, hoặc token đã hết hạn vẫn được chấp nhận lâu hơn dự kiến.

Trong kiến trúc phân tán, mỗi máy chủ, container host, vùng cloud và dịch vụ có thể quan sát thời gian hơi khác nhau. Sai lệch nhỏ thường được xử lý bằng một khoảng dung sai có giới hạn (clock skew/leeway). Sai lệch lớn hoặc không được giám sát có thể gây:

- Token mới phát hành bị từ chối vì nbf nằm trong tương lai.
- Token hết hạn bị từ chối sớm do verifier có đồng hồ chạy nhanh.
- Token hết hạn vẫn được chấp nhận do verifier có đồng hồ chạy chậm.
- Các service đánh giá cùng một token khác nhau.
- Log và trace khó sắp xếp đúng thứ tự sự kiện.
- JWT, TLS certificate, chữ ký request, TOTP, replay window và cache TTL hoạt động không nhất quán.

Đồng bộ đồng hồ là một phần của vận hành bảo mật. Hệ thống cần biết thời gian của từng node đáng tin tới mức nào, phát hiện khi mất đồng bộ và có hành vi rõ ràng khi vượt giới hạn cho phép.

Nội dung thuộc module Security - JSON Web Token (JWT), chương Hiệu năng và vận hành. Phạm vi là bảo mật token và hệ thống phân tán tổng quát, không phụ thuộc Java, Spring Security hoặc một nền tảng cụ thể.

## 2. Các claim thời gian của JWT

RFC 7519 định nghĩa các claim thời gian thường dùng:

| Claim | Ý nghĩa | Quy tắc chính |
| --- | --- | --- |
| iat (Issued At) | Thời điểm token được phát hành | NumericDate; không tự nó làm token hết hạn |
| nbf (Not Before) | Thời điểm token bắt đầu có hiệu lực | Không chấp nhận trước thời điểm này, có thể dùng leeway nhỏ |
| exp (Expiration Time) | Thời điểm token hết hiệu lực | Không chấp nhận tại hoặc sau thời điểm hết hạn, có thể dùng leeway nhỏ |

Các giá trị này dùng kiểu NumericDate: số giây từ Unix epoch 1970-01-01T00:00:00Z, bỏ qua leap seconds theo định nghĩa của RFC 7519. Giá trị có thể là số nguyên hoặc biểu diễn số phù hợp với quy tắc JSON NumericDate; các implementation cần thống nhất độ chính xác và cách xử lý.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.org/",
  "sub": "user-123",
  "aud": "https://api.example.org/invoices",
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893456900
}
~~~

Ví dụ trên minh họa ba thời điểm theo giây epoch. Trong hệ thống thực, thời gian phải được tạo từ clock đáng tin và kiểm tra theo policy của token profile.

### 2.1. Phân biệt thời gian phát hành và thời hạn

- iat cho biết thời điểm phát hành; nó không thay thế exp.
- nbf giới hạn thời điểm bắt đầu sử dụng; không phải thời điểm token được tạo.
- exp xác định thời điểm token không còn được chấp nhận.
- Thời lượng token thường được tính bằng exp trừ iat, nhưng policy còn có thể giới hạn maximum age và thời hạn tuyệt đối.

Không suy ra token còn hợp lệ chỉ vì iat gần hiện tại. Không coi iat là claim tự động bắt buộc cho mọi JWT; profile cụ thể quyết định claim nào phải có và semantics ra sao.

### 2.2. Đơn vị thời gian và lỗi milliseconds

NumericDate dùng giây epoch, trong khi nhiều API hệ điều hành và runtime trả về milliseconds. Nếu đưa trực tiếp millisecond timestamp vào exp, giá trị sẽ lớn hơn khoảng một nghìn lần và token có thể tồn tại lâu bất thường. Nếu chia nhầm hai lần, token có thể hết hạn ngay.

Quy tắc vận hành:

- Ghi rõ đơn vị trong mọi interface và cấu hình.
- Chuyển đổi tại một ranh giới duy nhất.
- Kiểm thử giá trị epoch đã biết.
- Không trộn giây, milliseconds, microseconds và nanoseconds.
- Không parse timestamp JWT bằng timezone cục bộ.

### 2.3. iat ở tương lai

iat là thời điểm phát hành, không phải cơ chế đồng bộ đồng hồ. Một Resource Server có thể áp dụng policy từ chối iat nằm quá xa trong tương lai hoặc token có tuổi vượt maximum age. Đây là kiểm tra theo profile/ứng dụng; không được tự áp dụng một quy tắc tùy ý rồi coi đó là yêu cầu chung của mọi JWT.

## 3. Wall clock và monotonic clock

Hệ điều hành thường cung cấp nhiều loại clock. Cần dùng đúng loại cho đúng mục đích.

| Loại clock | Đặc điểm | Dùng cho |
| --- | --- | --- |
| Wall clock / realtime clock | Biểu diễn thời gian lịch/epoch; có thể được điều chỉnh bởi NTP hoặc quản trị viên | iat, nbf, exp, audit timestamp, certificate validity |
| Monotonic clock | Tăng đều theo thời gian chạy, không lùi khi wall clock bị chỉnh | Timeout, duration, latency, retry interval, elapsed time |
| Process/runtime clock | API thời gian được cung cấp qua runtime; semantics phụ thuộc nền tảng | Chỉ dùng sau khi xác định rõ nó dựa trên clock nào |

JWT NumericDate là thời gian tuyệt đối theo epoch nên phải so sánh với wall clock đã đồng bộ. Không dùng monotonic clock trực tiếp để so exp vì monotonic clock không có mốc Unix epoch có thể so với token.

Ngược lại, không dùng wall clock để đo timeout hoặc thời lượng xử lý nếu clock có thể nhảy tiến/lùi. Ví dụ, đo thời gian một request bằng hai lần đọc wall clock có thể tạo duration âm hoặc tăng đột biến khi NTP điều chỉnh giờ. Dùng monotonic clock cho phép đo elapsed time ổn định hơn.

### 3.1. Wall clock có thể nhảy

Khi hệ thống phát hiện đồng hồ lệch lớn, time daemon có thể:

- **Slew:** điều chỉnh tốc độ clock trong một khoảng thời gian để dần hội tụ, giảm bước nhảy thời gian.
- **Step:** đặt lại wall clock tới thời điểm mới bằng một bước nhảy.

Step có thể làm timestamp đi tiến hoặc lùi. Nếu clock lùi đáng kể, verifier có thể đánh giá một token đã hết hạn như thể vẫn còn hiệu lực. Nếu clock tiến mạnh, token mới có thể bị coi là hết hạn hoặc nbf đã tới sớm hơn thực tế.

Vì vậy, cần theo dõi cả độ lệch và sự kiện clock step. Với môi trường yêu cầu độ ổn định cao, cấu hình đồng bộ nên ưu tiên điều chỉnh có kiểm soát và chỉ step theo quy trình được đánh giá.

### 3.2. Không dùng timezone để sửa clock skew

JWT NumericDate là epoch time, không phải giờ địa phương. Timezone, daylight saving time (DST) và định dạng hiển thị chỉ ảnh hưởng cách trình bày thời gian, không được dùng để bù lệch đồng hồ giữa máy chủ.

Lưu timestamp ở UTC/epoch; chỉ chuyển sang timezone địa phương tại giao diện hoặc báo cáo. Nếu hai node dùng timezone khác nhau nhưng cùng epoch clock chính xác, chúng vẫn có thể xác minh cùng một exp.

## 4. Clock skew là gì và đo như thế nào?

Clock skew là chênh lệch thời gian giữa hai clock. Cần định nghĩa rõ dấu để tránh đọc nhầm metric:

~~~text
offset(A, B) = clock_A - clock_B
~~~

Nếu offset dương, clock A chạy trước clock B theo quy ước trên. Nếu offset âm, clock A chạy sau clock B.

Trong vận hành, cần phân biệt:

- **Offset:** độ lệch ước lượng so với nguồn thời gian tham chiếu.
- **Delay/round-trip delay:** thời gian trao đổi với time server.
- **Jitter:** độ biến thiên của các phép đo hoặc offset qua thời gian, theo định nghĩa công cụ.
- **Root dispersion/error bound:** ước lượng sai số tích lũy so với nguồn tham chiếu.
- **Drift:** tốc độ clock phần cứng sai khác so với thời gian tham chiếu khi không được hiệu chỉnh.
- **Stratum:** cấp trong phân cấp NTP, thể hiện khoảng cách logic tới nguồn tham chiếu; stratum thấp hơn không tự động bảo đảm clock chính xác hơn trong mọi trường hợp.

Không chỉ giám sát trạng thái “synchronized”. Một node có thể báo đã đồng bộ nhưng offset, dispersion hoặc jitter vẫn vượt giới hạn vận hành mà ứng dụng chấp nhận.

### 4.1. So sánh đồng hồ giữa các node

Đối với JWT, hai phép so sánh quan trọng:

1. Clock của issuer so với clock của Resource Server.
2. Clock của các Resource Server với nhau.

Nếu issuer và verifier cùng lệch theo một hướng, kiểm tra exp/nbf có thể vẫn hoạt động tương đối nhất quán trong một số tình huống. Nhưng nếu mỗi service lệch khác nhau, cùng một token có thể được chấp nhận ở node này và bị từ chối ở node khác.

Đừng chỉ đo từng node so với time server. Cũng cần kiểm tra sai lệch giữa các node thuộc cùng trust domain và giữa các vùng triển khai.

## 5. Đồng bộ thời gian bằng NTP

Network Time Protocol (NTP) đồng bộ clock của máy với một hoặc nhiều nguồn thời gian. NTP thường phù hợp cho máy chủ, VM, container host và hệ thống dịch vụ thông thường.

Một phép trao đổi NTP sử dụng bốn timestamp:

- t1: client gửi request.
- t2: server nhận request.
- t3: server gửi response.
- t4: client nhận response.

Ước lượng offset và round-trip delay theo mô hình cơ bản:

~~~text
offset = ((t2 - t1) + (t3 - t4)) / 2
delay  = (t4 - t1) - (t3 - t2)
~~~

Đây là phép ước lượng dựa trên giả định về độ trễ đường đi. Nếu độ trễ chiều đi và chiều về không đối xứng, offset ước lượng có thể sai. Vì vậy, nhiều phép đo và nhiều nguồn thời gian giúp phát hiện bất thường tốt hơn.

### 5.1. Nguồn thời gian và dự phòng

Một thiết kế vận hành nên:

- Dùng time source được tổ chức hoặc cloud provider phê duyệt.
- Có nhiều nguồn độc lập theo chính sách NTP.
- Không phụ thuộc một server duy nhất nếu yêu cầu availability cao.
- Giám sát peer reachability, offset, delay, jitter, dispersion và trạng thái đồng bộ.
- Giới hạn truy cập NTP và cấu hình firewall phù hợp.
- Dùng nguồn tham chiếu có chất lượng và vị trí mạng phù hợp với hệ thống.

Không thêm hàng loạt NTP server không rõ nguồn chỉ để tăng số lượng peer. Nguồn không đáng tin có thể gây sai lệch hoặc làm phức tạp lựa chọn nguồn.

### 5.2. NTP và bảo vệ nguồn thời gian

NTP không được xác thực có thể bị tấn công giả mạo hoặc gây sai lệch nếu kẻ tấn công kiểm soát đường truyền hoặc nguồn time server. Với môi trường yêu cầu bảo vệ cao, xem xét Network Time Security (NTS) theo RFC 8915 để xác thực và bảo vệ trao đổi NTP.

NTS dùng cơ chế thiết lập khóa qua TLS và bảo vệ các gói NTP bằng cơ chế xác thực phù hợp. Việc dùng NTS không loại bỏ nhu cầu giám sát nguồn thời gian, độ trễ, offset và tính sẵn sàng.

### 5.3. NTP không bảo đảm mọi node có thời gian giống hệt nhau

Mạng có độ trễ, jitter, mất gói, CPU contention và sai số phần cứng. Mục tiêu thực tế là giữ sai số trong một ngân sách đã định, không phải đòi hỏi mọi node có cùng timestamp tuyệt đối.

Ngân sách sai số cần nhỏ hơn khoảng leeway mà hệ thống cho phép và phải đủ dư địa cho các nguồn sai số khác.

## 6. Khi nào cần PTP?

Precision Time Protocol (PTP, IEEE 1588) có thể đạt độ chính xác cao hơn NTP trong môi trường mạng được thiết kế phù hợp, đặc biệt khi có hardware timestamping và thiết bị mạng hỗ trợ.

PTP thường được xem xét cho:

- Hệ thống giao dịch hoặc đo lường cần thứ tự thời gian chính xác.
- Hạ tầng viễn thông và công nghiệp.
- Hệ thống đa máy cần đồng bộ rất chặt.
- Môi trường có yêu cầu timestamp ở mức microsecond hoặc tốt hơn.

Không phải mọi ứng dụng JWT đều cần PTP. Với đa số API web và token lifetime tính bằng phút, NTP được cấu hình và giám sát tốt thường đủ. Lựa chọn phụ thuộc yêu cầu latency, độ chính xác, hạ tầng và chi phí vận hành.

## 7. Tác động của clock skew lên exp, nbf và iat

Giả sử issuer và verifier có clock khác nhau:

| Tình huống | Tác động thường gặp |
| --- | --- |
| Issuer chạy trước verifier | iat/nbf có thể bị nhìn như thời điểm tương lai; token mới có thể bị từ chối |
| Issuer chạy sau verifier | exp được tính theo clock issuer; verifier có thể cho rằng token hết hạn sớm hơn so với thời gian issuer dự kiến |
| Verifier chạy trước | Có thể từ chối token sớm theo exp; đồng thời có thể coi nbf đã tới sớm |
| Verifier chạy sau | Có thể tiếp tục chấp nhận token sau thời điểm exp thực tế; nbf cũng được coi là đã tới |
| Các verifier lệch khác nhau | Cùng token có thể được chấp nhận ở một node và từ chối ở node khác |

Tác động chính xác phụ thuộc hướng và độ lớn của từng offset, cách issuer tính exp, leeway và policy của verifier. Cần kiểm thử với clock mô phỏng thay vì chỉ suy luận từ một node.

### 7.1. Ví dụ token bị từ chối sớm

Issuer tạo token với nbf bằng 12:00:00 UTC. Đồng hồ verifier chạy trước 45 giây và cho rằng hiện tại đã là 12:00:45. Với nbf, verifier có thể chấp nhận sớm hơn dự kiến. Nếu ngược lại verifier chạy sau 45 giây, nó có thể vẫn thấy thời gian trước 12:00:00 và từ chối token mới.

Điểm cần nhớ: cách nói “clock chạy nhanh/chậm” phải luôn gắn với bên nào. Clock verifier chạy chậm so với issuer là một nguyên nhân thường gặp khiến nbf bị từ chối.

### 7.2. Ví dụ token bị chấp nhận quá hạn

Issuer phát hành token hết hạn lúc 12:05:00 UTC. Nếu verifier chạy chậm 40 giây, khi thời gian thực đã là 12:05:20, verifier có thể vẫn cho rằng mới 12:04:40 và chấp nhận token.

Đây là lý do clock skew không chỉ là vấn đề availability. Nó còn có thể kéo dài cửa sổ sử dụng bearer token.

## 8. Thiết kế leeway/clock tolerance có giới hạn

RFC 7519 cho phép một khoảng leeway nhỏ khi xử lý exp và nbf để bù sai lệch clock giữa các hệ thống. Leeway không phải cách thay thế đồng bộ thời gian và không nên đặt quá rộng.

Với một policy dùng leeway L:

~~~text
reject if now >= exp + L
reject if now + L < nbf
~~~

Hai điều kiện trên minh họa cách áp dụng dung sai đối với exp và nbf. Chi tiết biên thời gian, độ chính xác số và semantics phải thống nhất giữa các implementation. Không áp dụng leeway để bỏ qua issuer, audience, signature hoặc các ràng buộc khác.

### 8.1. Leeway càng lớn, cửa sổ chấp nhận càng rộng

Nếu token có TTL 120 giây và hệ thống cho leeway 60 giây, dung sai có thể chiếm một phần đáng kể so với thời hạn token. Điều đó làm suy yếu ý nghĩa của TTL ngắn.

Leeway nên:

- Dựa trên offset đo được giữa issuer và verifier.
- Lớn hơn sai số vận hành dự kiến một cách có kiểm soát.
- Nhỏ hơn nhiều so với lifetime của token.
- Được cấu hình nhất quán trên các Resource Server cùng profile.
- Có giới hạn tối đa và cảnh báo khi offset tiến gần giới hạn.
- Không được tăng tự động vô hạn khi NTP mất đồng bộ.

### 8.2. Ví dụ ngân sách sai lệch

Giả sử hệ thống đặt:

| Thành phần | Giá trị minh họa |
| --- | ---: |
| JWT leeway | 60 giây |
| Cảnh báo offset node | 5 giây |
| Cảnh báo nghiêm trọng | 20 giây |
| Ngưỡng ngừng nhận token mới hoặc chuyển trạng thái bảo vệ | 40 giây |

Đây chỉ là ví dụ để minh họa cách tạo khoảng an toàn. Không dùng các con số này như chuẩn chung. Mỗi hệ thống phải tính từ token lifetime, yêu cầu bảo mật, NTP error bound, latency, vùng địa lý và khả năng chịu gián đoạn.

### 8.3. Không dùng leeway để che giấu lỗi đồng hồ

Nếu offset thường xuyên vượt 30 giây, tăng leeway lên 2 phút có thể làm giảm lỗi người dùng nhưng che giấu vấn đề hạ tầng và kéo dài thời gian chấp nhận token. Cần sửa time synchronization, điều tra node lỗi và giữ leeway trong giới hạn đã phê duyệt.

## 9. Kiểm tra iat, maximum age và token lifetime

iat thường được dùng để xác định tuổi token hoặc hỗ trợ audit. Ứng dụng có thể áp dụng:

- Từ chối iat quá xa trong tương lai so với clock hiện tại.
- Giới hạn tuổi token bằng maximum age.
- Kiểm tra exp sau iat.
- Giới hạn TTL tối đa theo token profile.
- Từ chối NumericDate sai kiểu hoặc vượt phạm vi số hợp lý.

Ví dụ policy:

~~~text
require exp exists
require exp > iat
require exp - iat <= configuredMaximumLifetime
require iat <= now + allowedFutureSkew
require now < exp + expirationLeeway
~~~

Đây là policy minh họa; không phải mọi JWT đều bắt buộc có iat hoặc exp. Token profile quyết định claims bắt buộc và quy tắc tương ứng. Không suy ra một token là hợp lệ chỉ vì exp còn ở tương lai nếu issuer/audience/profile sai.

### 9.1. Thời gian phát hành phải lấy từ nguồn thống nhất

Nếu nhiều issuer hoặc nhiều instance cùng phát hành token, cần bảo đảm:

- Tất cả node dùng nguồn thời gian được quản lý.
- Clock health được kiểm tra trước khi cấp token nếu nghiệp vụ yêu cầu.
- Token lifetime được tính theo một policy duy nhất.
- Không lấy timestamp từ client để tạo iat hoặc exp.
- Có thể truy vết issuer instance và thời điểm phát hành qua audit metadata an toàn.

Không đưa thông tin nội bộ nhạy cảm về host hoặc hạ tầng vào claims chỉ để debug. Dùng log correlation ID và metric phù hợp.

## 10. Đồng bộ thời gian trong container, VM và cloud

### 10.1. Container

Container thông thường dùng clock của kernel trên host. NTP được quản lý ở node/host; không nên chạy một time daemon độc lập trong mọi container trừ khi nền tảng có thiết kế đặc biệt.

Nếu nhiều container trên cùng node có timestamp sai giống nhau, kiểm tra clock của host. Nếu chỉ một node lệch, kiểm tra cấu hình time daemon và hypervisor của node đó.

### 10.2. Virtual Machine

VM có thể gặp drift do:

- Host quá tải hoặc tạm dừng.
- VM suspend/resume hoặc snapshot/restore.
- Đồng bộ giữa guest clock và hypervisor không nhất quán.
- Guest NTP và hypervisor time sync cùng điều chỉnh theo cách xung đột.

Chọn một mô hình đồng bộ được hỗ trợ và tránh để nhiều cơ chế độc lập liên tục sửa cùng clock mà không có policy.

### 10.3. Kubernetes và orchestration

Các workload trên cùng node thường chia sẻ clock của node. Cần giám sát từng node, không chỉ một pod đại diện. Pod reschedule sang node khác có thể làm lộ lỗi đồng bộ mà trước đó không xuất hiện.

Trong môi trường nhiều cluster hoặc nhiều region, cần kiểm tra:

- Sai lệch giữa node pools.
- Sai lệch giữa region.
- Nguồn NTP khác nhau.
- Policy leeway khác nhau giữa service.
- Clock health của control plane và data plane nếu chúng tham gia quyết định xác thực.

### 10.4. Cloud time service

Cloud provider có thể cung cấp time service hoặc tài liệu cấu hình riêng. Dùng nguồn thời gian được nền tảng hỗ trợ, nhưng vẫn cần giám sát offset và trạng thái đồng bộ trong workload. Không giả định “chạy trên cloud” đồng nghĩa mọi instance luôn đồng bộ hoàn hảo.

## 11. Giám sát clock health

Chỉ kiểm tra NTP daemon đang chạy là chưa đủ. Cần theo dõi chất lượng thời gian và khả năng phục hồi.

### 11.1. Metric nên thu thập

| Metric | Ý nghĩa | Dùng để phát hiện |
| --- | --- | --- |
| Clock offset | Chênh lệch với nguồn tham chiếu | Node chạy nhanh/chậm |
| Absolute offset | Độ lớn sai lệch không xét dấu | So với ngân sách skew |
| Root dispersion/error bound | Ước lượng sai số thời gian | Nguồn tham chiếu kém hoặc holdover dài |
| NTP peer reachability | Khả năng liên lạc với peer | Mất nguồn thời gian |
| NTP stratum | Cấp nguồn trong phân cấp | Thay đổi topology nguồn |
| Delay | Độ trễ trao đổi | Mạng bất thường |
| Jitter | Độ biến thiên phép đo | Clock/network không ổn định |
| Sync state | Đã đồng bộ, đang holdover hay unsynchronized | Trạng thái tin cậy |
| Clock step events | Số lần wall clock bị nhảy | Điều chỉnh lớn bất thường |
| Drift rate | Tốc độ sai lệch theo thời gian | Phần cứng hoặc cấu hình có vấn đề |
| Last successful sync | Lần đồng bộ thành công gần nhất | Mất kết nối time source |

Tên metric cụ thể phụ thuộc NTP daemon, hệ điều hành hoặc cloud monitoring. Chuẩn hóa tên và đơn vị trong hệ thống quan sát.

### 11.2. Theo dõi theo node và theo trust domain

Dashboard nên có:

- Offset hiện tại của từng node.
- Offset lớn nhất/nhỏ nhất theo cluster và region.
- Phân bố offset giữa issuer và Resource Server.
- Số node unsynchronized.
- Tuổi của lần sync thành công gần nhất.
- Sự kiện clock step.
- Số request JWT thất bại do exp/nbf hoặc iat policy.
- Tỷ lệ lỗi theo node, issuer, audience và token profile.

Không ghi raw JWT vào metric label. Dùng nhãn có cardinality thấp như service, region, node pool và error category.

### 11.3. Synthetic validation

Có thể chạy synthetic check định kỳ:

1. Một issuer test tạo token với thời điểm chuẩn.
2. Các verifier test ở nhiều node xác minh token.
3. Ghi nhận chênh lệch thời gian và kết quả exp/nbf.
4. So sánh kết quả giữa các node.
5. Cảnh báo nếu cùng token có kết quả khác nhau ngoài policy.

Synthetic token phải dùng khóa và audience kiểm thử, không dùng credential người dùng hoặc quyền production.

## 12. Đặt alert và SLO cho thời gian

Ngân sách skew cần được định nghĩa cùng nhóm vận hành, bảo mật và chủ sở hữu dịch vụ.

### 12.1. Ngưỡng cảnh báo

Có thể chia:

- **Healthy:** offset thấp hơn ngưỡng cảnh báo, time source ổn định.
- **Degraded:** offset tăng, jitter cao, mất một số peer hoặc dispersion tăng.
- **Critical:** offset tiến gần leeway hoặc vượt giới hạn được phê duyệt.
- **Unsynchronized:** không còn nguồn thời gian đủ tin cậy hoặc error bound vượt policy.

Alert nên dựa trên cả độ lớn offset và thời gian duy trì. Một spike vài mili giây khác với offset tăng liên tục trong nhiều phút. Với token lifetime ngắn, cần ngưỡng chặt hơn.

### 12.2. SLO gắn với xác thực token

Ví dụ SLO vận hành:

- Tỷ lệ node có absolute offset dưới ngưỡng X.
- Thời gian tối đa một node được phép ở trạng thái holdover.
- Tỷ lệ request bị từ chối do clock-related validation.
- Thời gian phát hiện và khắc phục node lệch.
- Mức nhất quán kết quả validation giữa các replica.

Không chỉ theo dõi availability của API. API vẫn có thể trả response nhưng chấp nhận token hết hạn do clock chậm; đây là lỗi security correctness chứ không chỉ là uptime.

### 12.3. Alert không được chỉ dựa vào JWT error rate

Một đợt nbf failure có thể do issuer clock chạy trước hoặc verifier clock chạy sau. Một đợt exp failure có thể do verifier chạy trước hoặc token lifetime policy thay đổi. Kết hợp metric clock offset với error category giúp khoanh vùng nguyên nhân nhanh hơn.

## 13. Quy trình xử lý khi clock lệch

Khi alert vượt ngưỡng, dùng runbook nhất quán:

1. Xác định node, region, service và thời điểm bắt đầu.
2. Kiểm tra sync state, offset, dispersion, jitter và peer reachability.
3. So sánh với time source và các node khỏe khác.
4. Kiểm tra thay đổi gần đây: reboot, VM migration, snapshot restore, NTP config, firewall hoặc network route.
5. Kiểm tra có clock step hoặc mất nguồn đồng bộ không.
6. Đánh giá token validation error theo issuer, audience và node.
7. Xác định có node nào đang chấp nhận token quá hạn hoặc từ chối token mới.
8. Cô lập hoặc rút node khỏi traffic nếu clock health vượt giới hạn bảo mật.
9. Khôi phục nguồn thời gian tin cậy và chờ clock ổn định theo policy.
10. Chạy synthetic validation và kiểm tra lại trước khi đưa node trở lại.
11. Ghi nhận nguyên nhân, khoảng ảnh hưởng và token/session có thể bị tác động.

Không chỉ restart service để “sửa giờ”. Nếu host clock sai, restart ứng dụng không giải quyết gốc rễ và có thể làm lỗi xuất hiện lại.

### 13.1. Khi time source không khả dụng

Nếu mất NTP:

- Dùng holdover trong giới hạn error bound và thời gian đã phê duyệt.
- Cảnh báo ngay khi sai số ước lượng tiến gần ngân sách skew.
- Không tự động tăng leeway để che giấu mất đồng bộ.
- Khi không thể tin thời gian cho thao tác nhạy cảm, áp dụng failure policy bảo thủ.
- Khôi phục nguồn thời gian độc lập và xác minh clock trước khi phục hồi traffic.

Fail-closed hay bounded degraded mode phụ thuộc mức rủi ro và kiến trúc. Quyết định phải được thiết kế trước; không để từng service tự xử lý khác nhau.

### 13.2. Phát hiện clock đi lùi

Clock đi lùi có thể làm exp/iat và log khó diễn giải. Có thể giám sát chênh lệch giữa wall clock và monotonic elapsed time để phát hiện bước nhảy bất thường.

Ví dụ nguyên tắc:

~~~text
wall_delta = wall_now - wall_previous
mono_delta = monotonic_now - monotonic_previous
unexpected_jump = wall_delta - mono_delta

if abs(unexpected_jump) > configuredStepThreshold:
    mark_clock_health_degraded()
    emit_clock_step_event()
~~~

Đây là phép giám sát cục bộ minh họa, không phải phép đồng bộ thời gian. Không dùng nó thay NTP và không coi một node phát hiện clock step là đã biết thời gian đúng. Cần kết hợp với nguồn tham chiếu tin cậy.

## 14. Kiểm thử clock skew có kiểm soát

Không chờ production bị lệch giờ mới kiểm tra. Tạo test clock hoặc môi trường giả lập để xác minh validator xử lý đúng biên thời gian.

### 14.1. Các ca kiểm thử JWT

| Ca kiểm thử | Clock issuer | Clock verifier | Kết quả mong đợi |
| --- | --- | --- | --- |
| Token hợp lệ | Đồng bộ | Đồng bộ | Chấp nhận |
| nbf vừa ở tương lai trong leeway | Đồng bộ | Lệch nhỏ | Xử lý theo leeway |
| nbf vượt leeway | Đồng bộ | Lệch lớn | Từ chối |
| exp vừa qua trong leeway | Đồng bộ | Lệch nhỏ | Xử lý theo policy leeway |
| exp vượt leeway | Đồng bộ | Lệch lớn | Từ chối |
| iat quá xa trong tương lai | Clock issuer chạy trước | Verifier chuẩn | Từ chối nếu profile policy giới hạn future iat |
| exp nhỏ hơn hoặc bằng iat | Bất kỳ | Bất kỳ | Từ chối theo token profile |
| TTL vượt maximum lifetime | Bất kỳ | Bất kỳ | Từ chối theo policy |
| Milliseconds thay cho seconds | Bất kỳ | Bất kỳ | Phát hiện giá trị sai đơn vị |
| Fractional NumericDate | Đồng bộ | Đồng bộ | Xử lý nhất quán theo độ chính xác được hỗ trợ |
| Clock rollback | Đồng bộ rồi lùi | Verifier bị step lùi | Clock health degraded; áp dụng policy bảo vệ |
| Node không sync | Nguồn thời gian mất | Verifier holdover | Hành vi theo error bound và failure policy |

### 14.2. Kiểm thử nhiều replica

Phát hành cùng một token test tới tất cả replica:

- Tất cả node có clock health tốt phải đưa ra kết quả nhất quán.
- Nếu một node lệch, test phải xác định node đó qua metric và log.
- Node vượt ngưỡng không được tiếp tục xử lý token theo policy đã định.
- Khi clock được khôi phục, kết quả phải nhất quán trở lại.

### 14.3. Chaos và fault injection

Trong môi trường test cô lập, mô phỏng:

- NTP server mất kết nối.
- Một peer trả thời gian bất thường.
- Network delay/jitter tăng.
- VM suspend/resume.
- Node reboot và clock khởi động sai.
- Time source chuyển sang peer dự phòng.
- Clock step tiến hoặc lùi.
- Một region lệch khỏi region khác.
- NTS certificate hoặc key establishment lỗi.

Không thay đổi clock production bằng lệnh thử nghiệm. Fault injection phải có giới hạn và kế hoạch khôi phục.

## 15. Thời gian trong log, trace và audit

JWT validation cần timestamp chính xác, nhưng hệ thống quan sát cũng cần thời gian đáng tin để tái dựng sự kiện.

Nên phân biệt:

- **event_time:** thời điểm sự kiện xảy ra theo clock của nguồn.
- **observed_at/ingested_at:** thời điểm hệ thống thu thập hoặc nhận sự kiện.
- **monotonic duration:** khoảng thời gian đo trong một process hoặc node.

Nếu một node lệch 30 giây, log của nó có thể xuất hiện trước sự kiện thực tế ở node khác. Không suy ra thứ tự nhân quả chỉ bằng timestamp wall clock. Dùng correlation ID, trace/span relationship, sequence number hoặc causal metadata khi cần.

### 15.1. Chuẩn hóa timestamp

- Dùng UTC và định dạng thống nhất như RFC 3339 cho log.
- Ghi rõ timezone hoặc hậu tố Z.
- Giữ độ chính xác nhất quán giữa các collector.
- Không trộn timestamp local với UTC.
- Không dùng thời gian từ client làm nguồn audit có thẩm quyền.
- Giữ event time và ingestion time khi cần điều tra.

## 16. Những hệ thống khác cũng phụ thuộc vào đồng hồ

Clock skew không chỉ ảnh hưởng JWT:

| Thành phần | Rủi ro khi clock lệch |
| --- | --- |
| TLS certificate validation | Chứng thư có thể bị coi là chưa hiệu lực hoặc đã hết hạn |
| Signed HTTP request | Timestamp nằm ngoài acceptance window |
| DPoP proof | iat quá cũ/quá xa trong tương lai hoặc nonce window sai |
| TOTP | Mã xác thực hợp lệ bị từ chối hoặc cửa sổ chấp nhận rộng hơn |
| Replay detection | Timestamp window không nhất quán giữa node |
| Cache TTL | Dữ liệu hết hạn sớm hoặc tồn tại lâu hơn dự kiến |
| Distributed lock/lease | Lease được coi là hết hạn sai thời điểm |
| Certificate/key rotation | Các node chuyển khóa không đồng bộ |
| Audit/log correlation | Thứ tự sự kiện bị sai lệch |

Vì vậy, time synchronization cần được vận hành như một dịch vụ hạ tầng dùng chung và có owner, SLO, alert, runbook rõ ràng.

## 17. Mã giả kiểm tra thời gian token

~~~text
function validateTokenTime(claims, clock, policy):
    now = clock.wallClockEpochSeconds()

    require claims.exp exists if policy.requiresExpiration
    require numericDateIsValid(claims.exp) when present
    require numericDateIsValid(claims.nbf) when present
    require numericDateIsValid(claims.iat) when present

    if claims.nbf exists:
        require now + policy.leewaySeconds >= claims.nbf

    if claims.exp exists:
        require now < claims.exp + policy.leewaySeconds

    if claims.iat exists:
        require claims.iat <= now + policy.allowedFutureIatSeconds
        if policy.maximumTokenAgeSeconds exists:
            require now - claims.iat <= policy.maximumTokenAgeSeconds

    if claims.exp and claims.iat exist:
        require claims.exp > claims.iat
        if policy.maximumLifetimeSeconds exists:
            require claims.exp - claims.iat <= policy.maximumLifetimeSeconds

    return VALID
~~~

Đây là pseudocode minh họa. Policy phải xác định claim nào bắt buộc theo profile, cách xử lý giá trị biên, độ chính xác số và leeway. Không dùng cùng một hàm wall clock để đo timeout mạng; các timeout và duration nên dựa trên monotonic clock.

## 18. Các lỗi vận hành thường gặp

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Không đồng bộ clock giữa issuer và verifier | Token mới bị từ chối hoặc token hết hạn bị chấp nhận | NTP/NTS và giám sát offset |
| Chỉ kiểm tra NTP daemon đang chạy | Không phát hiện offset/dispersion cao | Theo dõi clock health thực tế |
| Dùng leeway quá rộng | Kéo dài cửa sổ chấp nhận token | Leeway nhỏ, có ngân sách và alert |
| Tăng leeway để sửa lỗi hạ tầng | Che giấu node mất đồng bộ | Sửa time source và cô lập node lỗi |
| Dùng timezone địa phương cho NumericDate | Sai exp/nbf khi DST hoặc cấu hình timezone khác | Epoch/UTC |
| Dùng milliseconds thay giây | Token sống quá lâu hoặc hết hạn ngay | Kiểm tra đơn vị và test vector |
| Dùng wall clock đo timeout | Duration âm hoặc nhảy bất thường | Monotonic clock |
| Không giám sát clock step | Clock rollback có thể kéo dài chấp nhận token | Theo dõi step và clock health |
| Container tự chạy nhiều time daemon | Xung đột điều chỉnh clock | Quản lý clock ở host/node theo nền tảng |
| Một NTP peer duy nhất | Mất đồng bộ khi peer lỗi | Nguồn dự phòng được quản lý |
| Tin NTP không xác thực trong threat model nghiêm ngặt | Có thể bị time spoofing | Cân nhắc NTS và bảo vệ mạng |
| Chỉ xem log timestamp | Sắp xếp sai thứ tự sự kiện | Correlation ID, trace và ingestion time |
| Mỗi service cấu hình leeway khác nhau | Cùng token có kết quả khác nhau | Policy thống nhất và kiểm thử liên service |

## 19. Checklist thiết kế và vận hành

1. [ ] Issuer, Resource Server và các node liên quan dùng nguồn thời gian được quản lý.
2. [ ] Có nhiều nguồn thời gian dự phòng phù hợp và giám sát peer reachability.
3. [ ] Đo offset, dispersion/error bound, jitter, delay, stratum và sync state.
4. [ ] Có metric theo từng node, cluster và region.
5. [ ] Dùng NTS khi threat model yêu cầu xác thực nguồn thời gian.
6. [ ] Định nghĩa rõ wall clock cho NumericDate và monotonic clock cho duration/timeout.
7. [ ] Tất cả timestamp JWT dùng NumericDate theo giây epoch; không nhầm milliseconds.
8. [ ] Thời gian log chuẩn hóa UTC; không dùng timezone để bù skew.
9. [ ] Leeway nhỏ, có giới hạn, thống nhất theo token profile và dựa trên sai số đo được.
10. [ ] Ngân sách skew nhỏ hơn đáng kể so với leeway và token lifetime.
11. [ ] Kiểm tra exp, nbf, iat và maximum lifetime theo profile.
12. [ ] Có cảnh báo khi offset tiến gần leeway hoặc node mất sync.
13. [ ] Có phát hiện clock step và clock rollback.
14. [ ] Container/VM/cloud dùng mô hình đồng bộ phù hợp, tránh nhiều time daemon xung đột.
15. [ ] Có runbook cô lập node lỗi và khôi phục time source.
16. [ ] Có bounded holdover/failure policy khi mất NTP; không tự tăng leeway.
17. [ ] Synthetic validation kiểm tra kết quả giữa nhiều verifier.
18. [ ] Có test clock skew, boundary exp/nbf, iat future, milliseconds và rollback.
19. [ ] Có chaos test NTP outage, peer lỗi, VM suspend/resume và region skew.
20. [ ] Audit/log có event time, ingestion time và correlation metadata cần thiết.

## 20. Tài liệu tiêu chuẩn liên quan

- **RFC 7519 — JSON Web Token (JWT):** NumericDate và claims iat, nbf, exp; quy tắc leeway nhỏ cho exp/nbf.
- **RFC 5905 — Network Time Protocol Version 4 (NTPv4):** giao thức đồng bộ thời gian và thuật ngữ offset/delay/dispersion.
- **RFC 8633 — Network Time Protocol Best Current Practices:** khuyến nghị vận hành NTP an toàn và ổn định.
- **RFC 8915 — Network Time Security for the Network Time Protocol:** bảo vệ xác thực và integrity cho trao đổi NTP.
- **RFC 3339 — Date and Time on the Internet: Timestamps:** định dạng timestamp Internet, phù hợp chuẩn hóa log.
- **IEEE 1588 — Precision Time Protocol (PTP):** đồng bộ thời gian chính xác trong hạ tầng hỗ trợ.

**Nguyên tắc ghi nhớ:** JWT dùng thời gian epoch tuyệt đối để đánh giá exp, nbf và iat; vì vậy issuer và verifier cần clock được đồng bộ và giám sát. Dùng wall clock cho timestamp, monotonic clock cho duration, leeway nhỏ theo ngân sách sai lệch và có cảnh báo/runbook khi node mất đồng bộ. Không dùng leeway rộng để che giấu lỗi thời gian của hạ tầng.
